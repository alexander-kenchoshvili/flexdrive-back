"""Scheduled BOG status reads using the existing verified payment finalizer."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.email_delivery import send_transactional_email

from .bog_callbacks import BogCallbackError, reconcile_bog_payment
from .bog_payments import BogPaymentError
from .models import (
    OrderPaymentStatus, PaymentProvider, PaymentTransaction,
    PaymentTransactionAction, PaymentTransactionStatus,
)


REVIEW_CODES = (
    "bog_unknown_status_requires_reconciliation",
    "bog_unexpected_manual_capture_status",
)
ISSUE_MESSAGES = {
    "provider_order_missing": "ბანკის გადახდის ID არ გვაქვს; საჭიროა ხელით გადამოწმება.",
    "paid_without_order": "თანხა გადახდილია, მაგრამ შეკვეთა არ შექმნილა; საჭიროა ყურადღება.",
    "pending_overdue": "გადახდა ვადის შემდეგაც დაუდასტურებელია; საჭიროა გადამოწმება.",
    "provider_review_required": "ბანკის პასუხი ავტომატურად ვერ გადაწყდა; საჭიროა ხელით გადამოწმება.",
    "bank_request_failed": "ბანკთან გადამოწმება ვერ დასრულდა; ხელახლა ვცდით შემდეგ გაშვებაზე.",
    "bank_response_conflict": "ბანკის პასუხი ვერ დადასტურდა; საჭიროა ხელით გადამოწმება.",
    "unexpected_error": "გადამოწმება მოულოდნელი შეცდომით შეწყდა; საჭიროა ტექნიკური შემოწმება.",
}


def bog_sales():
    return PaymentTransaction.objects.filter(
        provider=PaymentProvider.BOG, action=PaymentTransactionAction.SALE,
    )


def payments_requiring_reconciliation():
    # Refund/cancel workflows retain their existing manual reconciliation path.
    return bog_sales().exclude(status__in=[
        PaymentTransactionStatus.REFUNDED, PaymentTransactionStatus.REFUND_PENDING,
        PaymentTransactionStatus.CANCELLED,
    ]).exclude(order__payment_status__in=[
        OrderPaymentStatus.REFUND_PENDING, OrderPaymentStatus.REFUNDED,
        OrderPaymentStatus.CANCELLED,
    ]).filter(
        Q(status__in=[PaymentTransactionStatus.PENDING, PaymentTransactionStatus.AUTHORIZED])
        | Q(status=PaymentTransactionStatus.PAID, order__isnull=True)
        | Q(error_code__in=REVIEW_CODES)
    )


def due_payments(*, created_before, attempted_before):
    # Revisit old monitoring issues even if a callback/manual refresh resolved the
    # payment in the meantime, so stale warnings can be cleared without a bank call.
    return bog_sales().filter(
        Q(pk__in=payments_requiring_reconciliation().values("pk"))
        | ~Q(reconciliation_issue="")
    ).filter(created_at__lte=created_before).filter(
        Q(reconciliation_attempted_at__isnull=True)
        | Q(reconciliation_attempted_at__lte=attempted_before)
    )


def reconcile_scheduled_payment(
    payment_id, *, created_before, attempted_before, notify_email="", client=None,
):
    now = timezone.now()
    token = uuid4()
    claimed = due_payments(
        created_before=created_before, attempted_before=attempted_before,
    ).filter(pk=payment_id).filter(
        Q(reconciliation_lock_until__isnull=True)
        | Q(reconciliation_lock_until__lte=now)
    ).update(
        reconciliation_token=token,
        reconciliation_lock_until=now + timedelta(minutes=10),
        reconciliation_attempted_at=now,
    )
    if not claimed:
        return "skipped"

    try:
        payment = PaymentTransaction.objects.get(pk=payment_id)
        issue = ""
        result = "resolved"
        if payments_requiring_reconciliation().filter(pk=payment_id).exists():
            if payment.status == PaymentTransactionStatus.PAID and not payment.order_id:
                # Already confirmed paid: polling cannot safely invent an order.
                issue = "paid_without_order"
            elif not payment.provider_order_id:
                # Never retry create_order to discover the outcome of an old attempt.
                issue = "provider_order_missing"
            else:
                try:
                    reconciled = reconcile_bog_payment(
                        payment, client=client, reconciliation_token=token,
                    )
                    if reconciled is None:
                        return "skipped"
                    payment.refresh_from_db()
                    if payment.status == PaymentTransactionStatus.PAID and not payment.order_id:
                        issue = "paid_without_order"
                    elif ("required" in reconciled.result or "review" in reconciled.result
                          or payment.error_code in REVIEW_CODES):
                        issue = "provider_review_required"
                    elif payment.status in {
                        PaymentTransactionStatus.PENDING, PaymentTransactionStatus.AUTHORIZED,
                    }:
                        result = "pending"
                        deadline = payment.expires_at or payment.created_at + timedelta(hours=1)
                        if deadline <= timezone.now():
                            issue = "pending_overdue"
                except BogCallbackError:
                    issue, result = "bank_response_conflict", "failed"
                except BogPaymentError:
                    issue, result = "bank_request_failed", "failed"
                except Exception:
                    # Do not persist provider exception text, tokens or customer data.
                    issue, result = "unexpected_error", "failed"

        saved_issue = _record_issue(payment_id, token, issue)
        if saved_issue is None:
            return "skipped"
        if saved_issue and notify_email:
            _notify_operator(payment_id, token, notify_email)
        if saved_issue:
            return "failed" if result == "failed" else "review"
        return result if result != "failed" else "resolved"
    finally:
        PaymentTransaction.objects.filter(pk=payment_id, reconciliation_token=token).update(
            reconciliation_token=None, reconciliation_lock_until=None,
        )


@transaction.atomic
def _record_issue(payment_id, token, issue):
    payment = PaymentTransaction.objects.select_for_update().get(pk=payment_id)
    if (payment.reconciliation_token != token or not payment.reconciliation_lock_until
            or payment.reconciliation_lock_until <= timezone.now()):
        return None
    # A callback could have completed while the network request failed.
    if not payments_requiring_reconciliation().filter(pk=payment_id).exists():
        issue = ""
    fields = ["reconciliation_issue"]
    if payment.reconciliation_issue != issue or not issue:
        payment.reconciliation_notified_at = None
        fields.append("reconciliation_notified_at")
    payment.reconciliation_issue = issue
    payment.save(update_fields=fields)
    return issue


def _notify_operator(payment_id, token, recipient):
    payment = PaymentTransaction.objects.get(pk=payment_id, reconciliation_token=token)
    if not payment.reconciliation_issue:
        return
    if (payment.reconciliation_notified_at
            and payment.reconciliation_notified_at > timezone.now() - timedelta(hours=24)):
        return
    if not payments_requiring_reconciliation().filter(pk=payment_id).exists():
        return
    path = reverse("admin:commerce_paymenttransaction_change", args=[payment_id])
    # Admin path only: no public checkout token, buyer data or bank response body.
    send_transactional_email(
        subject=f"FlexDrive: გადახდა #{payment_id} საჭიროებს ყურადღებას",
        text_content=(
            f"გადახდა #{payment_id}\n"
            f"{ISSUE_MESSAGES[payment.reconciliation_issue]}\n"
            f"გახსენით თქვენი ბექის დომენზე: {path}\n"
            "ეს გადამოწმება თანხას ხელახლა არ ჩამოჭრის."
        ),
        recipients=[recipient],
    )
    PaymentTransaction.objects.filter(
        pk=payment_id, reconciliation_token=token,
        reconciliation_issue=payment.reconciliation_issue,
    ).update(reconciliation_notified_at=timezone.now())
