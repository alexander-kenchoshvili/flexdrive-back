import logging
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from .bog_payments import BogPaymentError, BogPaymentsClient, BogResponseError
from .models import (
    Order,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderStatus,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
)
from .services import (
    CANCELLABLE_ORDER_STATUSES,
    cancel_refunded_order_and_restore_stock,
    create_payment_transaction,
    transition_order_payment_status,
)


logger = logging.getLogger(__name__)

BOG_REFUND_STATUSES = frozenset(
    {"refund_requested", "refunded", "refunded_partially"}
)
BOG_REFUND_ACTIONS = frozenset({"refund", "partial_refund"})
REFUND_REQUEST_CONTEXT_KEY = "refund_request"


@dataclass(frozen=True)
class BogRefundReconciliationResult:
    refund: PaymentTransaction
    order: Order | None
    result: str


def can_request_bog_full_refund(order):
    if (
        order.payment_method != OrderPaymentMethod.CARD
        or order.payment_status != OrderPaymentStatus.PAID
        or order.status not in CANCELLABLE_ORDER_STATUSES
        or order.stock_restored_at is not None
    ):
        return False
    return _bog_paid_sales_for_order(order).count() == 1


def get_bog_sale_payment_for_order(order):
    payments = list(_bog_paid_sales_for_order(order)[:2])
    if len(payments) != 1:
        raise DjangoValidationError(
            "The order must have exactly one confirmed BOG card payment."
        )
    return payments[0]


def has_bog_refund_activity(details):
    return (
        details.status in BOG_REFUND_STATUSES
        or any(action.action in BOG_REFUND_ACTIONS for action in details.actions)
    )


def request_bog_full_refund(
    *,
    order=None,
    sale_payment=None,
    requested_by=None,
    client=None,
):
    refund, should_submit = _prepare_bog_full_refund(
        order=order,
        sale_payment=sale_payment,
        requested_by=requested_by,
    )
    if not should_submit:
        return refund

    payment_client = client or BogPaymentsClient.from_settings()
    try:
        result = payment_client.refund_full(
            order_id=refund.provider_order_id,
            idempotency_key=refund.idempotency_key,
        )
        if result.key != "request_received":
            raise BogResponseError(
                code="bog_refund_response_unconfirmed",
                retryable=True,
                outcome_unknown=True,
            )
    except BogPaymentError as error:
        _record_refund_request_error(refund, error)
        raise
    except Exception:
        _record_unknown_refund_request_error(refund)
        logger.exception(
            "Unexpected BOG refund request failure.",
            extra={"payment_transaction_id": refund.pk},
        )
        raise

    return _record_refund_request_accepted(refund, result)


@transaction.atomic
def _prepare_bog_full_refund(
    *,
    order=None,
    sale_payment=None,
    requested_by=None,
):
    if (order is None) == (sale_payment is None):
        raise ValueError("Provide either order or sale_payment.")

    locked_order = None
    if order is not None:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        locked_sale = PaymentTransaction.objects.select_for_update().get(
            pk=get_bog_sale_payment_for_order(locked_order).pk
        )
    else:
        locked_sale = PaymentTransaction.objects.select_for_update().get(
            pk=sale_payment.pk
        )
        if locked_sale.order_id:
            locked_order = Order.objects.select_for_update().get(
                pk=locked_sale.order_id
            )

    _validate_refundable_sale(locked_sale, locked_order)

    existing = (
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.REFUND,
            provider_order_id=locked_sale.provider_order_id,
            status__in={
                PaymentTransactionStatus.REFUND_PENDING,
                PaymentTransactionStatus.REFUNDED,
            },
        )
        .filter(
            order=locked_order
            if locked_order is not None
            else None,
            reservation=locked_sale.reservation
            if locked_order is None
            else locked_sale.reservation,
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if existing is not None:
        should_submit = (
            existing.status == PaymentTransactionStatus.REFUND_PENDING
            and not existing.provider_action_id
        )
        return existing, should_submit

    if (
        locked_order is not None
        and (
            locked_order.payment_status != OrderPaymentStatus.PAID
            or locked_order.status not in CANCELLABLE_ORDER_STATUSES
            or locked_order.stock_restored_at is not None
        )
    ):
        raise DjangoValidationError(
            "Only a paid BOG card order in new, confirmed, or processing "
            "status can start this full refund flow."
        )

    request_context = {
        "sale_payment_id": locked_sale.pk,
        "restore_stock_on_success": locked_order is not None,
        "source": "admin" if requested_by is not None else "system",
    }
    if requested_by is not None and getattr(requested_by, "pk", None):
        request_context["requested_by_user_id"] = requested_by.pk

    refund = create_payment_transaction(
        order=locked_order,
        reservation=locked_sale.reservation,
        amount=locked_sale.amount,
        provider=PaymentProvider.BOG,
        payment_method=OrderPaymentMethod.CARD,
        action=PaymentTransactionAction.REFUND,
        status=PaymentTransactionStatus.REFUND_PENDING,
        currency=locked_sale.currency,
        provider_order_id=locked_sale.provider_order_id,
        provider_reference={REFUND_REQUEST_CONTEXT_KEY: request_context},
    )
    if locked_order is not None:
        transition_order_payment_status(
            locked_order,
            OrderPaymentStatus.REFUND_PENDING,
        )
    return refund, True


def _validate_refundable_sale(sale, order):
    if (
        sale.provider != PaymentProvider.BOG
        or sale.action != PaymentTransactionAction.SALE
        or sale.status != PaymentTransactionStatus.PAID
        or sale.payment_method != OrderPaymentMethod.CARD
        or sale.currency != "GEL"
        or not sale.provider_order_id
    ):
        raise DjangoValidationError(
            "A confirmed BOG card sale with a provider order ID is required."
        )
    if order is not None:
        if (
            sale.order_id != order.pk
            or order.payment_method != OrderPaymentMethod.CARD
            or order.total != sale.amount
        ):
            raise DjangoValidationError(
                "The BOG sale does not match the card order."
            )
    elif sale.order_id is not None:
        raise DjangoValidationError("The payment target is inconsistent.")


@transaction.atomic
def _record_refund_request_accepted(refund, result):
    locked_refund = PaymentTransaction.objects.select_for_update().get(
        pk=refund.pk
    )
    duplicate_action = (
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            provider_action_id=result.action_id,
        )
        .exclude(pk=locked_refund.pk)
        .exists()
    )
    if duplicate_action:
        locked_refund.error_code = "bog_refund_action_id_duplicate"
        locked_refund.error_message = (
            "BOG returned an action ID already linked to another payment record."
        )
        locked_refund.save(
            update_fields=["error_code", "error_message", "updated_at"]
        )
        raise DjangoValidationError(
            "BOG refund action ID conflicts with another payment record."
        )

    locked_refund.provider_action_id = result.action_id
    locked_refund.provider_reference = _merge_provider_reference(
        locked_refund,
        {"source": "refund_request", "details": result.provider_reference},
    )
    locked_refund.error_code = ""
    locked_refund.error_message = ""
    locked_refund.save(
        update_fields=[
            "provider_action_id",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return locked_refund


@transaction.atomic
def _record_refund_request_error(refund, error):
    locked_refund = PaymentTransaction.objects.select_for_update().get(
        pk=refund.pk
    )
    outcome_unknown = bool(error.outcome_unknown or error.retryable)
    locked_refund.error_code = str(error.code or "bog_refund_error")[:80]
    locked_refund.error_message = (
        "BOG refund result is not yet known; reconcile or retry with the same "
        "request."
        if outcome_unknown
        else "BOG rejected the refund request before it was accepted."
    )
    if not outcome_unknown:
        locked_refund.status = PaymentTransactionStatus.FAILED
    update_fields = [
        "status",
        "error_code",
        "error_message",
        "updated_at",
    ]
    locked_refund.save(update_fields=update_fields)
    if not outcome_unknown:
        _return_order_to_paid(locked_refund.order)
    return locked_refund


@transaction.atomic
def _record_unknown_refund_request_error(refund):
    locked_refund = PaymentTransaction.objects.select_for_update().get(
        pk=refund.pk
    )
    locked_refund.error_code = "bog_refund_unexpected_error"
    locked_refund.error_message = (
        "BOG refund result is not known; reconcile before retrying."
    )
    locked_refund.save(
        update_fields=["error_code", "error_message", "updated_at"]
    )
    return locked_refund


@transaction.atomic
def reconcile_bog_refund_details(
    sale_payment,
    details,
    *,
    provider_reference,
):
    sale = PaymentTransaction.objects.select_for_update().get(
        pk=sale_payment.pk
    )
    _validate_refundable_sale(sale, sale.order)
    action = _matching_refund_action(sale, details)
    refund = _lock_or_create_refund_from_details(sale, details, action)

    if _is_partial_refund(sale, details, action):
        return _mark_partial_refund_for_review(
            refund,
            sale,
            provider_reference,
            action,
        )

    if action is not None and action.status == "rejected":
        if (
            details.status == "refunded"
            or details.refund_amount > Decimal("0.00")
        ):
            return _mark_refund_ambiguous(
                refund,
                provider_reference,
                "bog_refund_status_conflict",
            )
        return _mark_refund_rejected(
            refund,
            provider_reference,
            action,
        )

    if details.status == "refunded":
        if (
            details.refund_amount != sale.amount
            or (
                action is not None
                and (
                    action.action != "refund"
                    or action.status != "completed"
                    or action.amount != sale.amount
                )
            )
        ):
            return _mark_refund_ambiguous(
                refund,
                provider_reference,
                "bog_refund_amount_mismatch",
            )
        return _mark_refund_completed(
            refund,
            provider_reference,
            action,
        )

    return _mark_refund_pending(
        refund,
        provider_reference,
        action,
    )


def _matching_refund_action(sale, details):
    actions = [
        action
        for action in details.actions
        if action.action in BOG_REFUND_ACTIONS
    ]
    if not actions:
        return None

    pending_refund = (
        PaymentTransaction.objects.filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.REFUND,
            provider_order_id=sale.provider_order_id,
            status__in={
                PaymentTransactionStatus.REFUND_PENDING,
                PaymentTransactionStatus.REFUNDED,
            },
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if pending_refund is not None and pending_refund.provider_action_id:
        for action in actions:
            if action.action_id == pending_refund.provider_action_id:
                return action

    full_actions = [
        action
        for action in actions
        if action.action == "refund" and action.amount == sale.amount
    ]
    return (full_actions or actions)[-1]


def _lock_or_create_refund_from_details(sale, details, action):
    query = PaymentTransaction.objects.select_for_update().filter(
        provider=PaymentProvider.BOG,
        action=PaymentTransactionAction.REFUND,
        provider_order_id=sale.provider_order_id,
    )
    refund = None
    if action is not None:
        refund = query.filter(provider_action_id=action.action_id).first()
    if refund is None:
        refund = (
            query.filter(
                status__in={
                    PaymentTransactionStatus.REFUND_PENDING,
                    PaymentTransactionStatus.REFUNDED,
                }
            )
            .order_by("-created_at", "-pk")
            .first()
        )
    if refund is not None:
        return refund

    amount = details.refund_amount
    if amount <= Decimal("0.00") and action is not None:
        amount = action.amount
    if amount <= Decimal("0.00"):
        amount = sale.amount
    return create_payment_transaction(
        order=sale.order,
        reservation=sale.reservation,
        amount=amount,
        provider=PaymentProvider.BOG,
        payment_method=OrderPaymentMethod.CARD,
        action=PaymentTransactionAction.REFUND,
        status=PaymentTransactionStatus.REFUND_PENDING,
        currency=sale.currency,
        provider_order_id=sale.provider_order_id,
        provider_action_id=action.action_id if action is not None else "",
        provider_reference={
            REFUND_REQUEST_CONTEXT_KEY: {
                "sale_payment_id": sale.pk,
                "restore_stock_on_success": False,
                "source": "external",
            }
        },
    )


def _is_partial_refund(sale, details, action):
    return (
        details.status == "refunded_partially"
        or Decimal("0.00") < details.refund_amount < sale.amount
        or (action is not None and action.action == "partial_refund")
    )


def _mark_partial_refund_for_review(
    refund,
    sale,
    provider_reference,
    action,
):
    refund.status = PaymentTransactionStatus.REFUND_PENDING
    refund.provider_reference = _merge_provider_reference(
        refund,
        provider_reference,
    )
    _bind_refund_action(refund, action)
    refund.error_code = "bog_partial_refund_requires_manual_reconciliation"
    refund.error_message = (
        "BOG reports a partial refund. FlexDrive full-refund automation did "
        "not mark the order as fully refunded or restore stock."
    )
    refund.save(
        update_fields=[
            "status",
            "provider_action_id",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    if sale.order_id and sale.order.payment_status == OrderPaymentStatus.PAID:
        transition_order_payment_status(
            sale.order,
            OrderPaymentStatus.REFUND_PENDING,
        )
    return BogRefundReconciliationResult(
        refund=refund,
        order=sale.order,
        result="partial_refund_requires_manual_reconciliation",
    )


def _mark_refund_rejected(refund, provider_reference, action):
    refund.status = PaymentTransactionStatus.FAILED
    refund.provider_reference = _merge_provider_reference(
        refund,
        provider_reference,
    )
    _bind_refund_action(refund, action)
    refund.error_code = _safe_provider_code(
        action.code,
        fallback="bog_refund_rejected",
    )
    refund.error_message = "BOG rejected the refund action."
    refund.save(
        update_fields=[
            "status",
            "provider_action_id",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    _return_order_to_paid(refund.order)
    return BogRefundReconciliationResult(
        refund=refund,
        order=refund.order,
        result="refund_rejected",
    )


def _mark_refund_ambiguous(refund, provider_reference, error_code):
    refund.status = PaymentTransactionStatus.REFUND_PENDING
    refund.provider_reference = _merge_provider_reference(
        refund,
        provider_reference,
    )
    refund.error_code = error_code
    refund.error_message = (
        "BOG refund details do not safely match the original full payment."
    )
    refund.save(
        update_fields=[
            "status",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return BogRefundReconciliationResult(
        refund=refund,
        order=refund.order,
        result="refund_reconciliation_required",
    )


def _mark_refund_pending(refund, provider_reference, action):
    refund.status = PaymentTransactionStatus.REFUND_PENDING
    refund.provider_reference = _merge_provider_reference(
        refund,
        provider_reference,
    )
    _bind_refund_action(refund, action)
    refund.error_code = ""
    refund.error_message = ""
    refund.save(
        update_fields=[
            "status",
            "provider_action_id",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    if (
        refund.order_id
        and refund.order.payment_status == OrderPaymentStatus.PAID
    ):
        transition_order_payment_status(
            refund.order,
            OrderPaymentStatus.REFUND_PENDING,
        )
    return BogRefundReconciliationResult(
        refund=refund,
        order=refund.order,
        result="refund_pending",
    )


def _mark_refund_completed(refund, provider_reference, action):
    was_refunded = refund.status == PaymentTransactionStatus.REFUNDED
    refund.status = PaymentTransactionStatus.REFUNDED
    refund.provider_reference = _merge_provider_reference(
        refund,
        provider_reference,
    )
    _bind_refund_action(refund, action)
    refund.error_code = ""
    refund.error_message = ""
    refund.refunded_at = refund.refunded_at or timezone.now()
    refund.save(
        update_fields=[
            "status",
            "provider_action_id",
            "provider_reference",
            "error_code",
            "error_message",
            "refunded_at",
            "updated_at",
        ]
    )

    order = refund.order
    if order is None:
        return BogRefundReconciliationResult(
            refund=refund,
            order=None,
            result="refunded",
        )
    if order.payment_status != OrderPaymentStatus.REFUNDED:
        transition_order_payment_status(order, OrderPaymentStatus.REFUNDED)
        order.refresh_from_db()

    request_context = refund.provider_reference.get(
        REFUND_REQUEST_CONTEXT_KEY,
        {},
    )
    if (
        was_refunded
        and order.payment_status == OrderPaymentStatus.REFUNDED
        and (
            not request_context.get("restore_stock_on_success")
            or (
                order.status == OrderStatus.CANCELLED
                and order.stock_restored_at is not None
            )
        )
    ):
        return BogRefundReconciliationResult(
            refund=refund,
            order=order,
            result="already_refunded",
        )
    if request_context.get("restore_stock_on_success"):
        try:
            order = cancel_refunded_order_and_restore_stock(order)
        except DjangoValidationError as error:
            refund.error_code = "bog_refund_completed_stock_restore_required"
            refund.error_message = error.messages[0][:2000]
            refund.save(
                update_fields=[
                    "error_code",
                    "error_message",
                    "updated_at",
                ]
            )
            return BogRefundReconciliationResult(
                refund=refund,
                order=order,
                result="refunded_stock_review_required",
            )
        return BogRefundReconciliationResult(
            refund=refund,
            order=order,
            result="refunded_and_cancelled",
        )

    refund.error_code = "bog_external_refund_requires_order_review"
    refund.error_message = (
        "The refund was confirmed without a local cancel-and-refund request; "
        "staff must review order and stock state."
    )
    refund.save(
        update_fields=["error_code", "error_message", "updated_at"]
    )
    return BogRefundReconciliationResult(
        refund=refund,
        order=order,
        result="refunded_order_review_required",
    )


def _bind_refund_action(refund, action):
    if action is None or refund.provider_action_id == action.action_id:
        return
    if refund.provider_action_id:
        raise DjangoValidationError(
            "BOG refund action ID does not match the local refund request."
        )
    duplicate = (
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            provider_action_id=action.action_id,
        )
        .exclude(pk=refund.pk)
        .exists()
    )
    if duplicate:
        raise DjangoValidationError(
            "BOG refund action ID is already linked to another record."
        )
    refund.provider_action_id = action.action_id


def _return_order_to_paid(order):
    if (
        order is not None
        and order.payment_status == OrderPaymentStatus.REFUND_PENDING
    ):
        transition_order_payment_status(order, OrderPaymentStatus.PAID)


def _merge_provider_reference(refund, provider_reference):
    current = refund.provider_reference or {}
    request_context = current.get(REFUND_REQUEST_CONTEXT_KEY, {})
    return {
        REFUND_REQUEST_CONTEXT_KEY: request_context,
        "provider": provider_reference,
    }


def _safe_provider_code(value, *, fallback):
    normalized = "".join(
        character
        for character in str(value or "").strip().lower()
        if character.isalnum() or character in {"_", "-"}
    )
    return f"bog_{normalized[:60]}" if normalized else fallback


def _bog_paid_sales_for_order(order):
    return PaymentTransaction.objects.filter(
        order=order,
        provider=PaymentProvider.BOG,
        payment_method=OrderPaymentMethod.CARD,
        action=PaymentTransactionAction.SALE,
        status=PaymentTransactionStatus.PAID,
    )
