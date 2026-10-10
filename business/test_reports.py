from datetime import date, datetime, timezone as utc
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from commerce.models import (
    Order, OrderItem, OrderItemInventory, OrderReturn, OrderReturnLine, OwnedStockLot, PaymentTransaction,
)
from .reports import ReportPeriod, build_dashboard_report, previous_period


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=utc.utc)


class DashboardReportTests(TestCase):
    def setUp(self):
        self.september = ReportPeriod(date(2026, 9, 1), date(2026, 9, 30))
        self.october = ReportPeriod(date(2026, 10, 1), date(2026, 10, 31))

    def sale(self, *, number="REPORT-1", provider="easyway", cost="59", when="2026-09-15T10:00", quantity=1, unit_price="118"):
        delivery, carrier, buffer = (D(15), D(12), D(3)) if provider == "easyway" else (D(10), D(0), D(0))
        order = Order.objects.create(order_number=number, subtotal=D(unit_price) * quantity,
                                     total=D(unit_price) * quantity + delivery, delivery_provider=provider,
                                     delivery_price=delivery, carrier_delivery_cost=carrier, delivery_margin=buffer,
                                     payment_status="paid", payment_method="card")
        item = OrderItem.objects.create(order=order, product_name="სატესტო ნაწილი", sku="PRIVATE-SUPPLIER",
                                        internal_sku="FD-01-0999", unit_price=D(unit_price), quantity=quantity,
                                        line_total=D(unit_price) * quantity, purchase_unit_gross=None if cost is None else D(cost))
        payment = PaymentTransaction.objects.create(order=order, provider="bog", action="sale", status="paid",
                                                    amount=order.total, captured_at=stamp(when))
        return order, item, payment

    def refund(self, sale, when="2026-10-02T10:00", amount=None):
        return PaymentTransaction.objects.create(order=sale.order, provider="bog", action="refund", status="refunded",
                                                 amount=sale.amount if amount is None else D(amount), refunded_at=stamp(when),
                                                 provider_reference={"refund_request": {"sale_payment_id": sale.pk}})

    def test_exact_vat_product_profit_and_delivery_split_once_per_order(self):
        self.sale(quantity=2)
        with self.assertNumQueries(6):
            report = build_dashboard_report(self.september)
        summary = report["summary"]
        self.assertEqual(summary["received"], "251.00")
        self.assertEqual(summary["product_received"], "236.00")
        self.assertEqual(summary["product_sales_net"], "200.00")
        self.assertEqual(summary["product_cost_net"], "100.00")
        self.assertEqual(summary["product_rounding_net"], "0.00")
        self.assertEqual(summary["product_profit_net"], "100.00")
        self.assertEqual(summary["courier_payable"], "12.00")
        self.assertEqual(summary["buffer_received"], "3.00")
        self.assertEqual(summary["buffer_orders"], 1)
        self.assertEqual(summary["regional_orders"], 1)
        self.assertEqual(summary["sold_units"], 2)
        self.assertEqual(report["deliveries"][0]["carrier"], "12.00")
        self.assertNotIn("PRIVATE-SUPPLIER", str(report))

    def test_profit_bridge_reconciles_both_rounding_directions_and_refund(self):
        _, _, first = self.sale(number="ROUND-DOWN", unit_price="1", cost="0.50")
        self.sale(number="ROUND-UP", unit_price="2", cost="1", when="2026-10-15T10:00")
        self.refund(first, when="2026-11-02T10:00")
        november = ReportPeriod(date(2026, 11, 1), date(2026, 11, 30))
        for period, expected in [
            (self.september, ("0.85", "0.42", "-0.01", "0.42")),
            (self.october, ("1.69", "0.85", "0.01", "0.85")),
            (november, ("-0.85", "-0.42", "0.01", "-0.42")),
        ]:
            with self.subTest(period=period):
                summary = build_dashboard_report(period)["summary"]
                fields = ("product_sales_net", "product_cost_net", "product_rounding_net", "product_profit_net")
                self.assertEqual(tuple(summary[key] for key in fields), expected)
                sales, cost, rounding, profit = (D(summary[key]) for key in fields)
                self.assertEqual(sales - cost + rounding, profit)

    def test_profit_bridge_uses_line_vat_rounding_and_only_sold_inventory(self):
        order, _, sale = self.sale(number="LINE-ROUNDING", unit_price="1", cost="0.50")
        OrderItem.objects.create(order=order, product_name="მეორე ნაწილი", internal_sku="FD-01-0998",
                                 unit_price=D(1), quantity=1, line_total=D(1), purchase_unit_gross=D("0.50"))
        Order.objects.filter(pk=order.pk).update(subtotal=D(2), total=D(17))
        PaymentTransaction.objects.filter(pk=sale.pk).update(amount=D(17))
        # Unsold pending inventory/order costs are not a cost of this period's sales.
        self.sale(number="UNPAID", cost="999", when="2026-09-20T10:00")
        PaymentTransaction.objects.filter(order__order_number="UNPAID").update(status="pending")
        summary = build_dashboard_report(self.september)["summary"]
        self.assertEqual(summary["product_sales_net"], "1.70")
        self.assertEqual(summary["product_cost_net"], "0.84")
        self.assertEqual(summary["product_rounding_net"], "-0.02")
        self.assertEqual(summary["product_profit_net"], "0.84")

    def test_internal_delivery_actual_snapshot_not_hardcoded_ten(self):
        order, _, sale = self.sale(provider="internal")
        Order.objects.filter(pk=order.pk).update(delivery_price=D(17), total=D(135))
        PaymentTransaction.objects.filter(pk=sale.pk).update(amount=D(135))
        summary = build_dashboard_report(self.september)["summary"]
        self.assertEqual(summary["internal_orders"], 1)
        self.assertEqual(summary["internal_delivery_received"], "17.00")
        self.assertEqual(summary["courier_payable"], "0.00")
        self.assertEqual(summary["buffer_received"], "0.00")

    def test_multiple_products_never_duplicate_order_delivery_and_queries_stay_bounded(self):
        order, _, sale = self.sale(quantity=2)
        OrderItem.objects.create(order=order, product_name="მეორე ნაწილი", internal_sku="FD-01-0998",
                                 unit_price=D(236), quantity=1, line_total=D(236), purchase_unit_gross=D(118))
        Order.objects.filter(pk=order.pk).update(subtotal=D(472), total=D(487))
        PaymentTransaction.objects.filter(pk=sale.pk).update(amount=D(487))
        with self.assertNumQueries(6):
            report = build_dashboard_report(self.september)
        self.assertEqual(report["summary"]["product_profit_net"], "200.00")
        self.assertEqual(report["summary"]["sold_units"], 3)
        self.assertEqual(report["summary"]["paid_orders"], 1)
        self.assertEqual(report["summary"]["courier_payable"], "12.00")
        self.assertEqual(report["summary"]["buffer_received"], "3.00")
        self.assertEqual(len(report["products"]), 2)

    def test_duplicate_receipts_are_not_allocated_as_double_product_sales(self):
        order, _, sale = self.sale()
        PaymentTransaction.objects.create(order=order, provider="bog", action="capture", status="paid",
                                          amount=sale.amount, captured_at=sale.captured_at)
        report = build_dashboard_report(self.september)
        self.assertEqual(report["summary"]["received"], "266.00")
        self.assertEqual(report["summary"]["paid_orders"], 1)
        self.assertIsNone(report["summary"]["sold_units"])
        self.assertIsNone(report["summary"]["courier_payable"])
        self.assertEqual(sum(day["paid_orders"] for day in report["daily"]), 1)

    def test_unknown_unsaleable_cost_is_missing_not_zero(self):
        order, item, _ = self.sale(cost=None)
        case = OrderReturn.objects.create(order=order, disposition="from_customer", receipt_status="received",
                                          received_at=stamp("2026-10-02T10:00"))
        OrderReturnLine.objects.create(return_case=case, order_item=item, expected_quantity=1, saleable_quantity=0,
                                       unsaleable_quantity=1, inspected_at=case.received_at)
        report = build_dashboard_report(self.october)
        self.assertEqual(report["summary"]["unsaleable_units"], 1)
        self.assertIsNone(report["summary"]["unsaleable_cost_net"])
        self.assertIsNone(report["losses"][0]["cost_net"])

    def test_cross_month_refund_reverses_original_cost_not_current_price(self):
        order, item, sale = self.sale()
        self.refund(sale)
        Order.objects.filter(pk=order.pk).update(payment_status="refunded", status="delivered")
        # Historical cost cannot be overwritten through model saving.
        item.purchase_unit_gross = D(999)
        item.save()
        september = build_dashboard_report(self.september)["summary"]
        october = build_dashboard_report(self.october)["summary"]
        self.assertEqual(september["received"], "133.00")
        self.assertEqual(september["product_profit_net"], "50.00")
        self.assertEqual(september["courier_payable"], "12.00")
        self.assertEqual(october["refunded"], "133.00")
        self.assertEqual(october["product_profit_net"], "-50.00")
        self.assertEqual(october["returned_units"], 1)
        self.assertEqual(october["net_buffer"], "-3.00")

    def test_completed_pre_dispatch_cancellation_not_in_outward_carrier_total(self):
        _, _, sale = self.sale()
        self.refund(sale, when="2026-09-16T10:00")
        summary = build_dashboard_report(self.september)["summary"]
        self.assertEqual(summary["courier_payable"], "0.00")
        self.assertEqual(summary["net_received"], "0.00")
        self.assertEqual(summary["net_buffer"], "0.00")

    def test_missing_cost_never_zero_cost_profit(self):
        self.sale(cost=None)
        summary = build_dashboard_report(self.september)["summary"]
        self.assertEqual(summary["received"], "133.00")
        self.assertEqual(summary["sold_units"], 1)
        self.assertIsNone(summary["product_profit_net"])
        self.assertIsNone(summary["product_cost_net"])
        self.assertEqual(summary["product_sales_net"], "100.00")
        self.assertIsNone(summary["product_rounding_net"])
        self.assertEqual(summary["unknown_cost_lines"], 1)

    def test_owned_inventory_exact_cost_overrides_supplier_snapshot(self):
        _, item, _ = self.sale(cost="999", quantity=2)
        OrderItemInventory.objects.create(order_item=item, external_quantity=0, external_source="",
                                          purchase_total_gross=D("118.00"))
        self.assertEqual(build_dashboard_report(self.september)["summary"]["product_profit_net"], "100.00")

    def test_partial_or_ambiguous_refund_keeps_cash_but_not_invented_product_reversal(self):
        _, _, sale = self.sale()
        self.refund(sale, amount="20")
        summary = build_dashboard_report(self.october)["summary"]
        self.assertEqual(summary["refunded"], "20.00")
        self.assertEqual(summary["net_received"], "-20.00")
        self.assertIsNone(summary["product_profit_net"])
        self.assertIsNone(summary["returned_units"])
        self.assertIsNone(summary["product_sales_net"])
        self.assertIsNone(summary["product_cost_net"])
        self.assertIsNone(summary["product_rounding_net"])
        self.assertEqual(summary["unallocated_events"], 1)

    def test_pending_failed_authorizations_and_other_currency_excluded(self):
        _, _, sale = self.sale()
        for action, status in [("authorize", "authorized"), ("sale", "pending"), ("sale", "failed")]:
            PaymentTransaction.objects.create(order=sale.order, action=action, status=status, amount=D(133), captured_at=sale.captured_at)
        foreign_order = Order.objects.create(order_number="REPORT-USD", subtotal=D(100), total=D(100))
        PaymentTransaction.objects.create(order=foreign_order, action="sale", status="paid", amount=D(100), currency="USD", captured_at=sale.captured_at)
        report = build_dashboard_report(self.september)
        self.assertEqual(report["summary"]["received"], "133.00")
        self.assertEqual(report["summary"]["paid_orders"], 1)
        self.assertEqual(report["summary"]["sold_units"], 1)

    def test_tbilisi_day_boundary_zero_baseline_and_no_synthetic_chart_values(self):
        self.sale(when="2026-08-31T20:00")
        report = build_dashboard_report(self.september)
        self.assertEqual(report["daily"][0]["received"], "133.00")
        self.assertEqual(report["daily"][1]["received"], "0.00")
        self.assertEqual(report["comparisons"]["received"]["delta"], "133.00")
        self.assertIsNone(report["comparisons"]["received"]["percent"])
        self.assertEqual(len(report["daily"]), 30)

    def test_month_comparison_and_custom_equal_day_range(self):
        self.assertEqual(previous_period(self.september), ReportPeriod(date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(previous_period(ReportPeriod(date(2026, 3, 1), date(2026, 3, 29))), ReportPeriod(date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(previous_period(ReportPeriod(date(2026, 9, 4), date(2026, 9, 6))), ReportPeriod(date(2026, 9, 1), date(2026, 9, 3)))

    def test_unsaleable_actual_remaining_fifo_layer_not_average_cost(self):
        from catalog.models import Category, Product
        category = Category.objects.create(name="Report test", slug="report-test")
        product = Product.objects.create(category=category, name="part", sku="PRIVATE", internal_sku="FD-01-0998",
                                         slug="report-part", price=D(118))
        order, item, _ = self.sale(quantity=2)
        OrderItem.objects.filter(pk=item.pk).update(product=product)
        OrderItemInventory.objects.create(order_item=item, external_quantity=0, external_source="", purchase_total_gross=D(177))
        case = OrderReturn.objects.create(order=order, disposition="from_customer", receipt_status="received",
                                          received_at=stamp("2026-10-02T10:00"))
        line = OrderReturnLine.objects.create(return_case=case, order_item=item, expected_quantity=2, saleable_quantity=1,
                                              unsaleable_quantity=1, inspected_at=case.received_at)
        OwnedStockLot.objects.create(return_line=line, product=product, quantity=1, purchase_unit_gross=D(59))
        report = build_dashboard_report(self.october)
        self.assertEqual(report["summary"]["unsaleable_units"], 1)
        self.assertEqual(report["summary"]["unsaleable_cost_net"], "100.00")
        self.assertEqual(report["losses"][0]["cost_net"], "100.00")
        self.assertEqual(report["summary"]["product_profit_net"], "0.00")

    def test_report_endpoint_access_validation_no_store_and_read_only(self):
        caches["throttling"].clear()
        user = get_user_model().objects.create_superuser("report-owner", "report@example.test", "Report-password-123")
        client = APIClient()
        url = reverse("business:report")
        self.assertEqual(client.get(url).status_code, 401)
        with patch("business.views.validate_recaptcha", return_value=True):
            client.post(reverse("business:login"), {"username": user.username, "password": "Report-password-123", "recaptcha_token": "test"}, format="json")
        order, _, _ = self.sale()
        before = Order.objects.values().get(pk=order.pk)
        response = client.get(url, {"start": "2026-09-01", "end": "2026-09-30"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.data["summary"]["received"], "133.00")
        self.assertEqual(before, Order.objects.values().get(pk=order.pk))
        for query in [{"start": "bad", "end": "2026-09-30"}, {"start": "2026-09-01"},
                      {"start": "2026-10-01", "end": "2026-09-01"}, {"start": "2024-01-01", "end": "2026-01-01"}]:
            self.assertEqual(client.get(url, query).status_code, 400)
