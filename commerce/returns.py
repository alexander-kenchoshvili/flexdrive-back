"""Physical receipt and refund finalization services for the admin return flow.

All writers lock the original order first. Physical receipts do not change payment
state or external Product.stock_qty. Receipts now credit the owned balance.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from .models import (
    Order, OrderPaymentStatus, OrderReturn, OrderReturnLine, OrderStatus,
    OrderItemInventory, OwnedStockLot, ReturnDisposition, ReturnReceiptStatus,
)


def has_external_items(order):
    for item in order.items.select_related("inventory"):
        try:
            if item.inventory.external_quantity:
                return True
        except OrderItemInventory.DoesNotExist:
            return True
    return False


@transaction.atomic
def finalize_return_refund(*, order, case_id):
    locked = Order.objects.select_for_update().get(pk=order.pk)
    case = OrderReturn.objects.get(pk=case_id, order=locked)
    if locked.payment_status != OrderPaymentStatus.REFUNDED:
        raise ValidationError("ბანკს თანხის დაბრუნება ჯერ არ დაუდასტურებია.")
    if locked.stock_restored_at:
        return locked
    permitted = ({OrderStatus.SHIPPED, OrderStatus.DELIVERED}
                 if case.disposition == ReturnDisposition.FROM_CUSTOMER else
                 {OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.PROCESSING})
    if locked.status not in permitted:
        raise ValidationError("შეკვეთა უკვე გაგზავნილია; საჭიროა ნივთის მიღების შემოწმება.")
    if case.disposition == ReturnDisposition.NOT_PURCHASED:
        from .services import _restore_order_stock_and_cancel
        return _restore_order_stock_and_cancel(locked, return_case=case)
    if case.disposition not in {ReturnDisposition.ON_HAND, ReturnDisposition.FROM_CUSTOMER} or case.receipt_status != ReturnReceiptStatus.RECEIVED:
        raise ValidationError("ნივთების მიღება არ არის დადასტურებული.")
    # The physical receipt already credited owned stock. Keep supplier holds:
    # an old supplier feed may still include the units we actually bought.
    locked.status = OrderStatus.CANCELLED
    locked.stock_restored_at = timezone.now()
    locked.save(update_fields=["status", "stock_restored_at", "updated_at"])
    return locked


def _validate_actor(actor):
    if not actor or not actor.pk or not actor.is_active or not actor.is_staff:
        raise ValidationError("მოქმედება მხოლოდ აქტიურ თანამშრომელს შეუძლია.")


@transaction.atomic
def prepare_order_return(*, order, disposition, actor):
    """Record full-order intent; on-hand means explicitly confirmed saleable receipt.

    The eventual action endpoint must additionally enforce its action permission,
    bank eligibility, and the operator's explicit non-dispatch confirmation.
    """
    _validate_actor(actor)
    if disposition not in ReturnDisposition.values:
        raise ValidationError("აირჩიეთ ნივთების მდგომარეობა.")
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    existing = OrderReturn.objects.filter(order=locked_order).first()
    if existing:
        if existing.disposition != disposition:
            raise ValidationError("დაბრუნება უკვე სხვა მდგომარეობით არის დაფიქსირებული.")
        return existing
    if locked_order.payment_status != OrderPaymentStatus.PAID or locked_order.stock_restored_at:
        raise ValidationError("დაბრუნებისთვის საჭიროა გადახდილი, ჯერ დაუბრუნებელი შეკვეთა.")
    dispatched = locked_order.status in {OrderStatus.SHIPPED, OrderStatus.DELIVERED}
    if disposition == ReturnDisposition.FROM_CUSTOMER:
        if not dispatched:
            raise ValidationError("ეს მოქმედება გაგზავნილ ან ჩაბარებულ შეკვეთას სჭირდება.")
    elif locked_order.status not in {OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.PROCESSING}:
        raise ValidationError("პირდაპირი დაბრუნება მხოლოდ გაგზავნამდეა შესაძლებელი.")

    items = list(locked_order.items.order_by("product_id", "pk"))
    if not items or any(item.product_id is None for item in items):
        raise ValidationError("შეკვეთის ყველა პროდუქტი კატალოგთან უნდა იყოს დაკავშირებული.")
    product_ids = sorted({item.product_id for item in items})
    if list(Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk").values_list("pk", flat=True)) != product_ids:
        raise ValidationError("შეკვეთის პროდუქტი ვეღარ მოიძებნა.")

    now = timezone.now()
    on_hand = disposition == ReturnDisposition.ON_HAND
    receipt_status = (
        ReturnReceiptStatus.RECEIVED if on_hand else
        ReturnReceiptStatus.NOT_REQUIRED if disposition == ReturnDisposition.NOT_PURCHASED else
        ReturnReceiptStatus.AWAITING
    )
    case = OrderReturn.objects.create(
        order=locked_order, disposition=disposition, receipt_status=receipt_status,
        requested_by=actor, received_by=actor if on_hand else None,
        received_at=now if on_hand else None,
    )
    for item in items:
        line = OrderReturnLine(
            return_case=case, order_item=item, expected_quantity=item.quantity,
            saleable_quantity=item.quantity if on_hand else 0,
            inspected_at=now if on_hand else None,
        )
        line.full_clean()
        line.save()
        if on_hand:
            _create_receipt_lot(line)
    return case


def _create_receipt_lot(line):
    if not line.saleable_quantity:
        return
    item = line.order_item
    try:
        inventory = item.inventory
    except OrderItemInventory.DoesNotExist:
        batches = [(None, item.quantity, item.purchase_unit_gross, item.purchase_cost_recorded_at)]
    else:
        allocations = list(inventory.allocations.select_related("lot").order_by("lot__created_at", "lot_id"))
        if any(row.restored_at for row in allocations):
            raise ValidationError("ამ შეკვეთის საკუთარი მარაგი უკვე აღდგენილია.")
        batches = [(row.lot, row.quantity, row.lot.purchase_unit_gross, row.lot.purchase_cost_recorded_at)
                   for row in allocations]
        if inventory.external_quantity:
            batches.append((None, inventory.external_quantity, item.purchase_unit_gross, item.purchase_cost_recorded_at))
    # Deterministic FIFO cost attribution for fungible units of the same product.
    # All physical units are inspected; remaining cost layers belong to rejects.
    remaining = line.saleable_quantity
    for number, (source, quantity, cost, recorded_at) in enumerate(batches, 1):
        take = min(quantity, remaining)
        if take:
            OwnedStockLot.objects.create(
                return_line=line, batch_number=number, product_id=item.product_id,
                quantity=take, source_lot=source, purchase_unit_gross=cost,
                purchase_cost_recorded_at=recorded_at,
            )
            remaining -= take
    if remaining:
        raise ValidationError("დაბრუნების რაოდენობა გაყიდვის მარაგის ისტორიას არ ემთხვევა.")


@transaction.atomic
def receive_order_return(*, return_case, inspection, actor):
    """inspection = {line_id: {'saleable': int, 'unsaleable': int}} for ALL lines.

    Physical inspection is independent of bank refund success. Identical retries
    preserve the original receipt, actor and timestamp; conflicting retries fail.
    """
    _validate_actor(actor)
    # Resolve the order from persisted state, not a caller's mutable model instance.
    order_id = OrderReturn.objects.values_list("order_id", flat=True).get(pk=return_case.pk)
    Order.objects.select_for_update().get(pk=order_id)
    case = OrderReturn.objects.select_for_update().get(pk=return_case.pk)
    if case.disposition != ReturnDisposition.FROM_CUSTOMER:
        raise ValidationError("ეს დაბრუნება მომხმარებლისგან მიღებას არ ელოდება.")
    lines = list(case.lines.select_related("order_item").order_by("pk"))
    if not isinstance(inspection, dict) or set(inspection) != {line.pk for line in lines}:
        raise ValidationError("შეამოწმეთ დაბრუნების ყველა პროდუქტი.")
    for line in lines:
        counts = inspection[line.pk]
        if not isinstance(counts, dict) or set(counts) != {"saleable", "unsaleable"}:
            raise ValidationError("მიუთითეთ ვარგისი და უვარგისი რაოდენობები.")
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValidationError("რაოდენობა უნდა იყოს არაუარყოფითი მთელი რიცხვი.")
        if counts["saleable"] + counts["unsaleable"] != line.expected_quantity:
            raise ValidationError("სრული დაბრუნებისთვის საჭიროა ყველა ნივთის მიღება.")
    if case.receipt_status == ReturnReceiptStatus.RECEIVED:
        if any(
            (line.saleable_quantity, line.unsaleable_quantity)
            != (inspection[line.pk]["saleable"], inspection[line.pk]["unsaleable"])
            for line in lines
        ):
            raise ValidationError("მიღება უკვე სხვა რაოდენობებით არის დადასტურებული.")
        return case
    if case.receipt_status != ReturnReceiptStatus.AWAITING:
        raise ValidationError("დაბრუნება მიღების მოლოდინში არ არის.")
    if any(line.order_item.product_id is None for line in lines):
        raise ValidationError("შეკვეთის პროდუქტი ვეღარ მოიძებნა.")
    # Same product lock order as checkout. All lines validate before any write.
    list(Product.objects.select_for_update().filter(
        pk__in=[line.order_item.product_id for line in lines],
    ).order_by("pk"))
    now = timezone.now()
    for line in lines:
        line.saleable_quantity = inspection[line.pk]["saleable"]
        line.unsaleable_quantity = inspection[line.pk]["unsaleable"]
        line.inspected_at = now
        line.full_clean()
        line.save(update_fields=["saleable_quantity", "unsaleable_quantity", "inspected_at", "updated_at"])
        _create_receipt_lot(line)
    case.receipt_status = ReturnReceiptStatus.RECEIVED
    case.received_by = actor
    case.received_at = now
    case.save(update_fields=["receipt_status", "received_by", "received_at", "updated_at"])
    return case
