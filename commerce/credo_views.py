"""Owner-bound local state and gated financing start; no browser bank evidence."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_vary_headers
from django.utils.timezone import now as timezone_now
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.utils import validate_recaptcha
from .credo_checkout import prepare_cart_credo_application, prepare_buy_now_credo_application, CredoCheckoutError
from .credo_access import (
    ACCESS_MAX_AGE, credo_access_cookie_name as _access_cookie_name,
    has_credo_access_cookie as _has_access_cookie,
)
from .credo_status import describe_credo_status
from .credo_guards import unresolved_credo_applications
from .credo_payments import CredoPaymentError, is_allowed_credo_redirect
from .credo_submission import configured_credo_client, credo_start_configuration, find_credo_replay, submit_credo_application
from .credo_reconciliation import due_credo_applications, reconcile_credo_application
from .delivery_quotes import DeliveryQuoteError
from .legal import build_terms_acceptance_snapshot
from .meta_conversions import has_marketing_consent, build_marketing_context
from .models import CredoApplication
from .serializers import CredoCheckoutSerializer
from .services import (
    BUY_NOW_TOKEN_COOKIE_NAME, CART_TOKEN_COOKIE_NAME,
    build_checkout_owner_fingerprint, parse_guest_token,
    resolve_cart, resolve_buy_now_session, BuyNowSessionStateError,
    BuyNowConflictError, StockReservationError,
    CheckoutPaymentInProgress,
)
from .views import (
    CartResponseMixin, BuyNowSessionResponseMixin, _api_cookie_kwargs,
    _required_checkout_idempotency_key, _delivery_quote_error_response,
)


def _owner_fingerprints(request):
    fingerprints = []
    if request.user.is_authenticated:
        fingerprints.append(build_checkout_owner_fingerprint(user=request.user))
    for name in (CART_TOKEN_COOKIE_NAME, BUY_NOW_TOKEN_COOKIE_NAME):
        token = parse_guest_token(request.COOKIES.get(name))
        if token is not None:
            fingerprints.append(build_checkout_owner_fingerprint(guest_token=token))
    return fingerprints


def credo_application_payload(application):
    state = describe_credo_status(application.bank_status) if application.bank_status is not None else None
    if application.needs_review:
        stage, label = "review", "განაცხადის მდგომარეობა მოწმდება."
    elif state is not None:
        stage, label = state.stage, state.label
    elif application.submission_state == "failed":
        stage, label = "start_failed", "განაცხადის დაწყება ვერ მოხერხდა."
    else:
        stage, label = "processing", "განაცხადი მუშავდება."
    can_continue = (
        not application.needs_review and application.submission_state == "submitted"
        and application.bank_status not in (5, 6, 7, 12) and bool(application.redirect_url)
        and is_allowed_credo_redirect(application.redirect_url, origin=getattr(settings, "CREDO_REDIRECT_ORIGIN", ""))
    )
    return {
        "application_token": str(application.public_token), "stage": stage, "label": label,
        "amount": format(application.requested_amount, ".2f"), "currency": application.currency,
        "requested_offer": application.requested_offer, "source": application.checkout_attempt.source,
        "ready_to_ship": bool(state and state.fulfillment_authorized and application.order_id and not application.needs_review),
        "funding_completed": bool(state and state.funding_completed and not application.needs_review),
        "redirect_url": application.redirect_url if can_continue else None,
        "can_restart_checkout": bool(not application.needs_review and not application.order_id
            and (application.bank_status in (6, 7) or
                 (application.submission_state == "failed" and application.bank_status is None))),
        "order_public_token": str(application.order.public_token) if application.order_id else None,
        "order_number": application.order.order_number if application.order_id else None,
        "checked_at": application.bank_checked_at, "updated_at": application.updated_at,
    }


class CredoReadOnlyAPIView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        patch_vary_headers(response, ("Cookie", "Authorization"))
        return response


class CredoAvailabilityAPIView(CredoReadOnlyAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            credo_start_configuration()
            enabled = True
        except CredoPaymentError:
            enabled = False
        return Response({
            "enabled": enabled, "provider": "credo", "currency": "GEL",
            "offers": ["installment", "dayavi"], "redirect_checkout": True,
        })


def _owned_application(request, public_token):
    access = Q(checkout_attempt__owner_fingerprint__in=_owner_fingerprints(request))
    if _has_access_cookie(request, public_token):
        access |= Q(public_token=public_token)
    return get_object_or_404(
        CredoApplication.objects.select_related("order", "checkout_attempt").filter(access),
        public_token=public_token,
    )


class CredoApplicationStatusAPIView(CredoReadOnlyAPIView):
    permission_classes = [AllowAny]
    throttle_scope = "checkout"

    def get(self, request, public_token):
        application = _owned_application(request, public_token)
        return Response(credo_application_payload(application))


class CredoApplicationRefreshAPIView(CredoReadOnlyAPIView):
    """CSRF-protected owner POST; trusted server GET at most once per 30s.

    Uses the same database cooldown/lease as cron. UUID alone is never access;
    browser payload/status never becomes bank evidence. The local GET stays pure.
    """
    permission_classes = [AllowAny]
    throttle_scope = "checkout"

    def post(self, request, public_token):
        application = _owned_application(request, public_token)
        if (getattr(settings, "CREDO_STATUS_CHECK_ENABLED", False) is not True
            or application.needs_review or application.bank_status in (5, 6, 7, 12)):
            return Response(credo_application_payload(application))
        now = timezone_now()
        timing = {"created_before": now, "attempted_before": now-timedelta(seconds=30)}
        if not due_credo_applications(**timing).filter(pk=application.pk).exists():
            return Response(credo_application_payload(application))
        try:
            result = reconcile_credo_application(application.pk, client=configured_credo_client(), **timing)
        except CredoPaymentError:
            result = "failed"
        if result == "failed":
            return Response({"detail": "სტატუსის განახლება დროებით ვერ მოხერხდა. სცადეთ მოგვიანებით."}, status=503)
        # Re-read related order after reconciliation may have created it.
        application = _owned_application(request, public_token)
        return Response(credo_application_payload(application))


class CredoApplicationStartAPIView(CartResponseMixin, BuyNowSessionResponseMixin, CredoReadOnlyAPIView):
    permission_classes = [AllowAny]
    throttle_scope = "checkout"
    source = "cart"

    def post(self, request):
        try:
            client, ttl, test_mode = credo_start_configuration()
        except CredoPaymentError:
            return Response({"code": "credo_unavailable", "detail": "კრედოს დაფინანსება ამჟამად მიუწვდომელია."}, status=503)
        if not validate_recaptcha(request.data.get("recaptcha_token"), expected_action="checkout", remote_ip=request.META.get("REMOTE_ADDR")):
            return Response({"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."}, status=403)
        serializer = CredoCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        offer = data.pop("requested_offer")
        key = _required_checkout_idempotency_key(request)
        fingerprints = _owner_fingerprints(request)
        # A signed application cookie survives the shorter Buy Now source session.
        stub = CredoApplication.objects.select_related("checkout_attempt").filter(checkout_attempt__key=key).first()
        if stub is not None and _has_access_cookie(request, stub.public_token):
            fingerprints.append(stub.checkout_attempt.owner_fingerprint)
        application = find_credo_replay(
            key=key, fingerprints=fingerprints, source=self.source, validated_data=data,
            requested_offer=offer, merchant_id=client.merchant_id, is_test=test_mode,
        )
        resolved, created = None, False
        try:
            if application is None:
                resolved = resolve_cart(request) if self.source == "cart" else resolve_buy_now_session(request)
                options = dict(
                    user=request.user if request.user.is_authenticated else None, validated_data=data,
                    terms_acceptance=build_terms_acceptance_snapshot(request=request, accepted_at=timezone_now()),
                    idempotency_key=key, requested_offer=offer, merchant_id=client.merchant_id,
                    reservation_ttl_seconds=ttl, is_test=test_mode,
                    marketing_consent=has_marketing_consent(request), marketing_context=build_marketing_context(request),
                )
                prepared = (prepare_cart_credo_application(cart=resolved.cart, **options) if self.source == "cart"
                    else prepare_buy_now_credo_application(session=resolved.session, **options))
                application, created = prepared.application, prepared.created
            application = submit_credo_application(application.pk, client=client)
            response = Response(credo_application_payload(application), status=201 if created else 200)
            if not created:
                response["Idempotency-Replayed"] = "true"
            response.set_signed_cookie(
                _access_cookie_name(application.public_token), str(application.public_token), salt="credo-application",
                **_api_cookie_kwargs(max_age=ACCESS_MAX_AGE),
            )
        except StockReservationError as error:
            response = Response({"detail": error.detail, "code": "cart_availability_changed", "cart_issues": error.issues}, status=400)
        except DeliveryQuoteError as error:
            response = _delivery_quote_error_response(error)
        except (BuyNowSessionStateError, BuyNowConflictError) as error:
            response = Response(error.to_response_data(), status=error.status_code)
        except CredoCheckoutError:
            response = Response({"detail": "განაცხადის მდგომარეობა მოწმდება.", "code": "credo_review_required"}, status=409)
        except CheckoutPaymentInProgress:
            products = (resolved.cart.items.values_list("product_id", flat=True) if self.source == "cart"
                else [resolved.session.product_id])
            active = unresolved_credo_applications().select_related("order", "checkout_attempt").filter(
                checkout_attempt__source=self.source, checkout_attempt__owner_fingerprint__in=fingerprints,
                reservation__items__product_id__in=products,
            ).order_by("pk").first()
            payload = {"detail": "ამ შეძენისთვის ონლაინ გადახდა უკვე დაწყებულია.", "code": "credo_already_active"}
            if active is not None:
                payload["application"] = credo_application_payload(active)
            response = Response(payload, status=409)
            if active is not None:
                response.set_signed_cookie(
                    _access_cookie_name(active.public_token), str(active.public_token), salt="credo-application",
                    **_api_cookie_kwargs(max_age=ACCESS_MAX_AGE),
                )
        if resolved is not None:
            return (self.apply_cart_cookie(response, resolved) if self.source == "cart"
                else self.apply_buy_now_cookie(response, resolved))
        return response


class BuyNowCredoApplicationStartAPIView(CredoApplicationStartAPIView):
    source = "buy_now"
