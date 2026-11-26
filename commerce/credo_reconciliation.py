"""Bounded status reads independent of the customer's browser and start flag.

Only GET status requests are made. Callers provide an explicitly configured
client; this module never creates, retries, cancels or refunds a bank loan.
"""

from datetime import timedelta
from uuid import uuid4

from django.db.models import Q
from django.utils import timezone

from .credo_checkout import CredoCheckoutError, apply_credo_observation
from .credo_payments import CredoConfigurationError, CredoPaymentError
from .models import CredoApplication


def due_credo_applications(*, created_before, attempted_before):
    return CredoApplication.objects.filter(
        Q(submission_state__in=("submitting", "submitted", "unknown")) | Q(bank_status__isnull=False),
        created_at__lte=created_before,
    ).filter(
        Q(bank_check_attempted_at__isnull=True) | Q(bank_check_attempted_at__lte=attempted_before),
    ).exclude(Q(bank_status__in=(5, 6, 7), needs_review=False) & (
        Q(order__isnull=False) | Q(bank_status__in=(6, 7))
    ))


def reconcile_credo_application(
    application_id, *, client, created_before, attempted_before, lock_seconds=120,
):
    """Claim one read, perform HTTP outside DB locks, reject stale lease results."""
    if type(lock_seconds) is not int or not 1 <= lock_seconds <= 3600:
        raise ValueError("Invalid status-read lease.")
    now, token = timezone.now(), uuid4()
    claimed = due_credo_applications(
        created_before=created_before, attempted_before=attempted_before,
    ).filter(pk=application_id).filter(
        Q(bank_check_lock_until__isnull=True) | Q(bank_check_lock_until__lte=now),
    ).update(bank_check_token=token, bank_check_lock_until=now+timedelta(seconds=lock_seconds),
             bank_check_attempted_at=now, updated_at=now)
    if not claimed:
        return "skipped"
    application = CredoApplication.objects.only("merchant_id", "order_code").get(pk=application_id)
    try:
        if client.merchant_id != application.merchant_id:
            raise CredoConfigurationError(code="credo_merchant_mismatch")
        result = client.get_status(order_code=application.order_code)
        application = apply_credo_observation(application_id, result.application_status, check_token=token)
    except CredoPaymentError as error:
        updates = {"last_issue": error.code, "updated_at": timezone.now()}
        if error.code in {"credo_unknown_application_status", "credo_duplicate_application", "credo_merchant_mismatch"}:
            updates["needs_review"] = True
        # Keep the original critical incident if this case already needs review.
        CredoApplication.objects.filter(pk=application_id, bank_check_token=token, needs_review=False).update(**updates)
        return "failed"
    except CredoCheckoutError as error:
        if error.code == "credo_stale_status_read":
            return "skipped"
        raise
    finally:
        CredoApplication.objects.filter(pk=application_id, bank_check_token=token).update(
            bank_check_token=None, bank_check_lock_until=None,
        )
    if application.needs_review:
        return "review"
    if application.bank_status in (5, 6, 7):
        return "resolved"
    if application.bank_status == 12 and application.order_id:
        return "ready"
    return "pending"
