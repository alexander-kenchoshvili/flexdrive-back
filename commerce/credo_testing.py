"""Local pilot operations. Never cancels a bank loan or fabricates bank evidence."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone

from .models import (
    CheckoutAttempt, CredoApplication, CredoStatementSettlement, Order,
    OrderPaymentMethod, OrderPaymentStatus, OrderReturn, OrderStatus,
    PaymentTransaction, StockReservation, WingoShipment,
)


def require_local_credo_test_environment():
    """Do not make a local pilot tool usable against a remote/production DB."""
    database = connection.settings_dict
    if not (
        settings.DEBUG and getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "CREDO_TEST_MODE", False)
        and connection.vendor == "sqlite"
        and Path(str(database["NAME"])).resolve() == (Path(settings.BASE_DIR) / "db.sqlite3").resolve()
    ):
        raise ValidationError("This operation requires the local development SQLite database and Credo test mode.")


@transaction.atomic
def close_cancelled_credo_test(*, application_id, actor, bank_reference, confirmed_unshipped, commit=False):
    """Explicit, audited stock restoration after a fresh trusted bank cancellation.

    The normal signed-status conflict policy stays unchanged. The bank must
    cancel first; a human additionally confirms that the test item never left.
    """
    require_local_credo_test_environment()
    if not actor.is_active or not actor.is_staff or not all(actor.has_perm(p) for p in (
        "commerce.view_credoapplication", "commerce.change_order",
    )):
        raise PermissionDenied
    if confirmed_unshipped is not True or not isinstance(bank_reference, str) or not bank_reference.strip() or len(bank_reference) > 120:
        raise ValidationError("Confirm no dispatch and supply a short internal bank cancellation reference (no customer data).")
    stub = CredoApplication.objects.only("checkout_attempt_id").get(pk=application_id)
    attempt = CheckoutAttempt.objects.select_for_update().get(pk=stub.checkout_attempt_id)
    application = CredoApplication.objects.select_for_update().get(pk=application_id)
    reservation = StockReservation.objects.select_for_update().get(pk=application.reservation_id)
    if not application.is_test or not application.order_id:
        raise ValidationError("Only a test application with an existing order can use this closure.")
    order = Order.objects.select_for_update().get(pk=application.order_id)
    if order.payment_method != OrderPaymentMethod.CREDO or attempt.order_id != order.pk or reservation.completed_order_id != order.pk:
        raise ValidationError("Checkout/order links do not match.")
    if (application.funding_completed_at or application.purchase_queued_at
        or CredoStatementSettlement.objects.filter(application=application).exists()
        or PaymentTransaction.objects.filter(order=order).exists()
        or WingoShipment.objects.filter(order=order).exists()
        or OrderReturn.objects.filter(order=order).exists()):
        raise ValidationError("Shipment, return or financial evidence prevents test stock restoration.")
    if (application.bank_status == 7 and application.last_observed_status == 7 and not application.needs_review
        and order.status == OrderStatus.CANCELLED and order.payment_status == OrderPaymentStatus.CANCELLED
        and order.stock_restored_at):
        return {"closed": True, "changed": False, "order_number": order.order_number}
    if (application.bank_status != 12 or application.last_observed_status != 7
        or not application.needs_review or application.last_issue != "credo_signed_status_conflict"
        or not application.signed_at or not application.bank_checked_at
        or application.bank_checked_at < timezone.now() - timedelta(minutes=5)
        or order.status not in (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.PROCESSING)
        or order.payment_status != OrderPaymentStatus.PENDING or order.stock_restored_at):
        raise ValidationError("A fresh bank cancellation of an unshipped signed test order is required.")
    if not commit:
        return {"closed": False, "changed": False, "order_number": order.order_number}
    from .services import _restore_order_stock_and_cancel
    _restore_order_stock_and_cancel(order)
    order.payment_status = OrderPaymentStatus.CANCELLED
    order.save(update_fields=["payment_status", "updated_at"])
    application.bank_status = 7
    application.needs_review = False
    application.last_issue = ""
    # Invalidate any in-flight older status read, preserving the original links.
    application.bank_check_token = None
    application.bank_check_lock_until = None
    application.save(update_fields=["bank_status", "needs_review", "last_issue", "bank_check_token", "bank_check_lock_until", "updated_at"])
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=CredoApplication.objects.filter(pk=application.pk),
        action_flag=CHANGE, change_message="Local unshipped test closed after bank cancellation; stock restored once. Reference: " + bank_reference.strip())
    return {"closed": True, "changed": True, "order_number": order.order_number}
