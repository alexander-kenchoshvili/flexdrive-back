"""One bank submission per prepared application; ambiguous outcomes are read back.

No transaction spans HTTP. Claiming 'submitting' is irreversible by checkout:
even a crash before the request is reconciled or reviewed, never blindly retried.
"""

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .checkout_snapshots import is_checkout_snapshot_intact
from .credo_checkout import _request_fingerprint
from .credo_payments import CredoConfigurationError, CredoPaymentError, CredoPaymentsClient, CredoProduct
from .models import CredoApplication
from .services import CheckoutIdempotencyConflict, release_stock_reservation


def configured_credo_client():
    return CredoPaymentsClient(
        merchant_id=getattr(settings, "CREDO_MERCHANT_ID", ""),
        secret_key=getattr(settings, "CREDO_SECRET_KEY", ""),
        order_url=getattr(settings, "CREDO_ORDER_URL", ""),
        status_url=getattr(settings, "CREDO_STATUS_URL", ""),
        redirect_origin=getattr(settings, "CREDO_REDIRECT_ORIGIN", ""),
        connect_timeout=getattr(settings, "CREDO_HTTP_CONNECT_TIMEOUT_SECONDS", 5),
        read_timeout=getattr(settings, "CREDO_HTTP_READ_TIMEOUT_SECONDS", 15),
    )


def credo_start_configuration():
    # Credentials alone never enable financing or background bank requests.
    if (getattr(settings, "CREDO_PAYMENTS_ENABLED", False) is not True
            or getattr(settings, "CREDO_STATUS_CHECK_ENABLED", False) is not True):
        raise CredoConfigurationError(code="credo_disabled")
    ttl = getattr(settings, "CREDO_RESERVATION_TTL_SECONDS", None)
    test_mode = getattr(settings, "CREDO_TEST_MODE", False)
    if type(ttl) is not int or not 1 <= ttl <= 7 * 86400 or type(test_mode) is not bool:
        raise CredoConfigurationError(code="credo_invalid_checkout_configuration")
    return configured_credo_client(), ttl, test_mode


def find_credo_replay(*, key, fingerprints, source, validated_data, requested_offer, merchant_id, is_test):
    application = CredoApplication.objects.select_related("checkout_attempt", "order").filter(
        checkout_attempt__key=key, checkout_attempt__owner_fingerprint__in=fingerprints,
    ).first()
    if application is None:
        return None
    attempt = application.checkout_attempt
    if (attempt.source != source or application.merchant_id != merchant_id or application.is_test != is_test
            or attempt.request_fingerprint != _request_fingerprint(source, validated_data, requested_offer)):
        raise CheckoutIdempotencyConflict()
    return application


def submit_credo_application(application_id, *, client):
    """Return local state, whether POST succeeded, failed locally or is uncertain."""
    with transaction.atomic():
        application = CredoApplication.objects.select_for_update().get(pk=application_id)
        if application.submission_state != "prepared" or application.needs_review or application.bank_status is not None:
            return application
        if application.reservation.expires_at <= timezone.now():
            application.submission_state = "failed"
            application.last_issue = "credo_unsubmitted_reservation_expired"
            release_stock_reservation(application.reservation)
            application.save(update_fields=["submission_state", "last_issue", "updated_at"])
            return application
        snapshot = application.checkout_snapshot
        if (client.merchant_id != application.merchant_id or not is_checkout_snapshot_intact(snapshot)
                or snapshot.get("integrity_hash") != application.snapshot_digest):
            application.needs_review = True
            application.last_issue = "credo_submission_snapshot_invalid"
            application.save(update_fields=["needs_review", "last_issue", "updated_at"])
            return application
        try:
            products = [CredoProduct(
                product_id=item["provider_product_id"], title=item["product_name"],
                quantity=item["quantity"], unit_price=Decimal(item["unit_price"]),
            ) for item in snapshot["items"]]
            total, delivery = application.requested_amount, Decimal(snapshot["totals"]["delivery"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            application.needs_review = True
            application.last_issue = "credo_submission_snapshot_invalid"
            application.save(update_fields=["needs_review", "last_issue", "updated_at"])
            return application
        application.submission_state = "submitting"
        application.start_attempted_at = timezone.now()
        application.save(update_fields=["submission_state", "start_attempted_at", "updated_at"])

    try:
        result = client.create_order(
            order_code=application.order_code, products=products,
            total_amount=total, delivery_amount=delivery, currency=application.currency,
        )
    except CredoPaymentError as error:
        with transaction.atomic():
            current = CredoApplication.objects.select_for_update().get(pk=application_id)
            current.submission_state = "unknown" if error.outcome_unknown else "failed"
            if not current.needs_review:
                current.last_issue = error.code
            if not error.outcome_unknown and current.bank_status is not None:
                current.submission_state = "unknown"
                current.needs_review = True
                current.last_issue = "credo_submission_observation_conflict"
            # Only local preflight rejection proves nothing reached the bank.
            if not error.outcome_unknown and current.bank_status is None and not current.needs_review:
                release_stock_reservation(current.reservation)
            current.save(update_fields=["submission_state", "needs_review", "last_issue", "updated_at"])
        return current
    # Unexpected exceptions/crashes deliberately leave 'submitting' for readback.
    # Do not persist any copy of the private checkout snapshot after HTTP.
    CredoApplication.objects.filter(pk=application_id).update(
        submission_state="submitted", redirect_url=result.redirect_url,
        submitted_at=timezone.now(), updated_at=timezone.now(),
    )
    return CredoApplication.objects.select_related("order").get(pk=application_id)
