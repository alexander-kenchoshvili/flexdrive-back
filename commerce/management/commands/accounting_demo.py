"""Isolated accounting examples for local or explicitly selected staging."""
from datetime import datetime
from decimal import Decimal as D

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from commerce.accounting_reports import TBILISI
from commerce.models import Order, OrderItem, PaymentTransaction

PREFIX = "FD-DEMO-202609-"
EMAIL = "accounting-demo@example.invalid"
STAGING_HOST = "ep-little-paper-al0gr1fd-pooler.c-3.eu-central-1.aws.neon.tech"


class Command(BaseCommand):
    help = "Create or delete marked accounting examples locally or on the approved staging host."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true")
        parser.add_argument("--staging", action="store_true", help="Allow the explicitly approved Neon staging database only.")

    @transaction.atomic
    def handle(self, *args, **options):
        staging = (options.get("staging") and connection.vendor == "postgresql"
                   and connection.settings_dict.get("HOST") == STAGING_HOST
                   and connection.settings_dict.get("NAME") == "neondb")
        if connection.vendor != "sqlite" and not staging:
            raise CommandError("Local SQLite only; remote databases are not allowed.")
        existing = Order.objects.filter(order_number__startswith=PREFIX)
        if options["delete"]:
            orders = list(existing)
            ids = [o.pk for o in orders]
            payments = PaymentTransaction.objects.filter(order_id__in=ids)
            if (any(o.email != EMAIL or o.first_name != "DEMO" or o.user_id or o.easyway_order_id for o in orders)
                    or payments.exclude(provider="mock", provider_order_id="", provider_transaction_id="", provider_action_id="", reservation=None).exists()
                    or OrderItem.objects.filter(order_id__in=ids, product__isnull=False).exists()):
                raise CommandError("Demo records were linked to real data; automatic deletion refused.")
            payments.hard_delete()
            OrderItem.objects.filter(order_id__in=ids).hard_delete()
            existing.hard_delete()
            self.stdout.write(f"Deleted {len(ids)} demo orders only.")
            return
        if existing.exists():
            raise CommandError("Demo batch already exists; delete it explicitly before recreating.")
        names = ("წინა ფარი", "გვერდითი სარკე", "სამუხრუჭე ხუნდი", "ჰაერის ფილტრი", "ბამპერი", "რადიატორი")
        prices = ((15, 35), (80, 110), (130, 170), (10, 25), (340, 420), (135, 170))
        for index in range(1, 37):
            month = 4 + (index - 1) // 6
            moment = datetime(2026, month, ((index - 1) % 6 + 1) * 3, 12, tzinfo=TBILISI)
            regional = index % 2 == 0
            carrier = D(12 + index % 5 * 3) if regional else D(0)
            margin = D(3) if regional else D(0)
            delivery = carrier + margin if regional else D(10)
            parts = []
            for part in range((index - 1) % 3 + 1):
                kind = (index + part - 1) % len(names)
                purchase, sale = map(D, prices[kind])
                quantity = 2 if index % 5 == 0 and part == 0 else 1
                parts.append((part, names[kind], purchase, sale, quantity))
            subtotal = sum((sale * quantity for _, _, _, sale, quantity in parts), D(0))
            order = Order.objects.create(
                order_number=f"{PREFIX}{index:02}", first_name="DEMO", last_name="სატესტო შეკვეთა",
                email=EMAIL, phone="DEMO", city="ბათუმი" if regional else "თბილისი",
                address_line="სატესტო მონაცემი — არ გაიგზავნოს", payment_method="card",
                payment_status="paid", status="new", subtotal=subtotal, total=subtotal + delivery,
                delivery_provider="easyway" if regional else "internal", carrier_delivery_cost=carrier,
                delivery_margin=margin, delivery_price=delivery,
            )
            Order.objects.filter(pk=order.pk).update(created_at=moment)
            for part, name, purchase, sale_price, quantity in parts:
                OrderItem.objects.create(order=order, product=None, product_name=f"DEMO — {name} {index}-{part + 1}",
                    sku=f"DEMO-SUP-{index:02}-{part + 1}", internal_sku=f"DEMO-FD-{index:02}-{part + 1}",
                    unit_price=sale_price, line_total=sale_price * quantity, quantity=quantity,
                    purchase_unit_gross=purchase, purchase_cost_source="catalog_supplier_price", purchase_cost_recorded_at=moment)
            sale = PaymentTransaction.objects.create(order=order, provider="mock", action="sale", status="paid",
                amount=order.total, captured_at=moment)
            if index % 6 == 0:
                returned = datetime(2026, month + 1, 3, 12, tzinfo=TBILISI) if month < 9 else datetime(2026, 9, 28, 12, tzinfo=TBILISI)
                PaymentTransaction.objects.create(order=order, provider="mock", action="refund", status="refunded",
                    amount=order.total, refunded_at=returned, provider_reference={"refund_request": {"sale_payment_id": sale.pk}})
                Order.objects.filter(pk=order.pk).update(payment_status="refunded", status="cancelled")
        self.stdout.write("Created 36 demo orders / 72 unique product lines / 42 transactions, April-September 2026.")
