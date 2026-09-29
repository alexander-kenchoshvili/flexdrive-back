from datetime import date, datetime, timezone
from decimal import Decimal as D

from django.test import SimpleTestCase, TestCase

from .accounting_reports import (
    ReportPeriod, build_cash_report, build_order_report,
)
from .models import Order, OrderItem, PaymentTransaction, StockReservation


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class ReportPeriodTests(SimpleTestCase):
    def test_tbilisi_inclusive_days(self):
        period = ReportPeriod(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(period.bounds, (stamp("2026-08-31T20:00"), stamp("2026-09-30T20:00")))

    def test_months_and_leap_year(self):
        self.assertEqual(ReportPeriod.months("2024-02", "2024-02").end, date(2024, 2, 29))
        self.assertEqual(ReportPeriod.months("2025-12", "2026-01").start, date(2025, 12, 1))

    def test_invalid_ranges(self):
        for start, end in [("2026-02", "2026-01"), ("2026-1", "2026-02"), ("bad", "2026-02"), (None, "2026-01")]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                ReportPeriod.months(start, end)
        with self.assertRaises(ValueError):
            ReportPeriod(datetime.now(), date.today())


class AccountingReportTests(TestCase):
    def setUp(self):
        self.september = ReportPeriod.months("2026-09", "2026-09")
        self.october = ReportPeriod.months("2026-10", "2026-10")
        self.order = Order.objects.create(
            order_number="ACC-1", subtotal=D("70"), total=D("93"),
            delivery_provider="easyway", carrier_delivery_cost=D("20"),
            delivery_margin=D("3"), delivery_price=D("23"),
            payment_method="card", payment_status="paid",
        )
        Order.objects.filter(pk=self.order.pk).update(created_at=stamp("2026-09-15T10:00"))
        for i in range(2):
            OrderItem.objects.create(
                order=self.order, product_name=f"Part {i}", sku=f"PRIVATE-{i}",
                internal_sku=f"FD-01-000{i + 1}", unit_price=D("35"), quantity=1,
                line_total=D("35"), purchase_unit_gross=D("15"),
                purchase_cost_source="catalog_supplier_price",
            )
        self.sale = self.payment()

    def payment(self, **kwargs):
        fields = dict(order=self.order, provider="bog", action="sale", status="paid",
                      amount=D("93"), captured_at=stamp("2026-09-16T10:00"))
        fields.update(kwargs)
        return PaymentTransaction.objects.create(**fields)

    def refund(self, **kwargs):
        fields = dict(action="refund", status="refunded", captured_at=None,
                      refunded_at=stamp("2026-10-02T10:00"),
                      provider_reference={"refund_request": {"sale_payment_id": self.sale.pk}})
        fields.update(kwargs)
        return self.payment(**fields)

    def test_delivery_once_and_explicit_vat(self):
        with self.assertNumQueries(2):
            report = build_order_report(self.september, tax_rates=lambda item: (D(18), D(18)))
        summary = report["summary"]
        self.assertEqual(summary["delivery_gross"], D(23))
        self.assertEqual(summary["regional_buffer"], D(3))
        self.assertEqual(summary["known_purchase_gross"], D(30))
        self.assertEqual(summary["known_net_markup"], D("33.90"))
        self.assertEqual(summary["markup_covered_line_count"], 2)
        self.assertEqual(report["orders"][0]["issues"], ())
        self.assertNotIn("delivery_price", report["orders"][0]["lines"][0])

    def test_unknown_tax_never_assumed(self):
        summary = build_order_report(self.september)["summary"]
        self.assertEqual(summary["markup_covered_line_count"], 0)
        self.assertEqual(summary["line_issue_count"], 2)

    def test_missing_cost_and_zero_are_different(self):
        OrderItem.objects.create(order=self.order, product_name="Legacy", sku="L", unit_price=D(10), quantity=1, line_total=D(10))
        OrderItem.objects.create(order=self.order, product_name="Free", sku="F", unit_price=D(10), quantity=1, line_total=D(10), purchase_unit_gross=D(0))
        Order.objects.filter(pk=self.order.pk).update(subtotal=D(90), total=D(113))
        summary = build_order_report(self.september, tax_rates=lambda item: (D(18), D(18)))["summary"]
        self.assertEqual(summary["unknown_cost_line_count"], 1)
        self.assertEqual(summary["unknown_cost_sale_gross"], D(10))
        self.assertEqual(summary["markup_covered_line_count"], 3)

    def test_cross_month_refund_keeps_original_receipt(self):
        self.refund()
        Order.objects.filter(pk=self.order.pk).update(payment_status="refunded", status="cancelled")
        with self.assertNumQueries(3):
            september = build_cash_report(self.september)
        october = build_cash_report(self.october)
        self.assertEqual(september["currencies"]["GEL"]["received"], D(93))
        self.assertEqual(october["currencies"]["GEL"]["refunded"], D(93))
        self.assertEqual(october["currencies"]["GEL"]["net_received"], D(-93))
        self.assertEqual(october["currencies"]["GEL"]["buffer_refunded"], D(3))
        self.assertEqual(october["events"][0]["issues"], ())

    def test_failed_pending_authorizations_are_not_receipts(self):
        self.payment(status="failed")
        self.payment(status="pending")
        self.payment(action="authorize", status="authorized")
        self.assertEqual(len(build_cash_report(self.september)["events"]), 1)

    def test_unknown_event_date_is_global_exception(self):
        payment = self.payment(captured_at=None)
        report = build_cash_report(self.october)
        self.assertEqual(report["events"], [])
        self.assertNotIn("undated_event_count_global", report)

    def test_exact_local_boundaries(self):
        PaymentTransaction.objects.filter(pk=self.sale.pk).update(captured_at=stamp("2026-08-31T19:59:59"))
        included = self.payment(captured_at=stamp("2026-08-31T20:00"))
        self.payment(captured_at=stamp("2026-09-30T20:00"))
        self.assertEqual([e["transaction_id"] for e in build_cash_report(self.september)["events"]], [included.pk])

    def test_partial_or_unlinked_refund_not_guessed(self):
        refund = self.refund(amount=D(20))
        report = build_cash_report(self.october)
        self.assertIsNone(report["events"][0]["allocation"])
        self.assertEqual(report["currencies"]["GEL"]["unallocated_refunded"], D(20))
        PaymentTransaction.objects.filter(pk=refund.pk).update(amount=D(93), provider_reference={})
        self.assertIsNone(build_cash_report(self.october)["events"][0]["allocation"])

    def test_duplicate_payment_does_not_double_order_allocation(self):
        self.payment(action="capture")
        report = build_cash_report(self.september)
        self.assertEqual(report["currencies"]["GEL"]["received"], D(186))
        self.assertEqual(report["currencies"]["GEL"]["delivery_received"], D(0))
        self.assertTrue(all(e["issues"] == ("ambiguous_order_payments",) for e in report["events"]))

    def test_internal_delivery_not_profit_or_known_carrier_cost(self):
        Order.objects.filter(pk=self.order.pk).update(delivery_provider="internal", delivery_price=D(10), delivery_margin=D(0), carrier_delivery_cost=D(0), total=D(80))
        row = build_order_report(self.september)["orders"][0]
        self.assertIsNone(row["carrier_quote"])
        self.assertIsNone(row["actual_delivery_cost"])
        self.assertEqual(row["regional_buffer"], D(0))

    def test_mismatched_delivery_is_review_case(self):
        Order.objects.filter(pk=self.order.pk).update(delivery_margin=D(4))
        self.assertIsNone(build_cash_report(self.september)["events"][0]["allocation"])

    def test_currency_totals_never_mixed(self):
        self.payment(currency="USD", amount=D(5))
        report = build_cash_report(self.september)
        self.assertEqual(report["currencies"]["USD"]["received"], D(5))
        self.assertEqual(report["currencies"]["GEL"]["received"], D(93))

    def test_limits_fail_instead_of_silent_partial_totals(self):
        self.payment()
        with self.assertRaises(ValueError):
            build_cash_report(self.september, limit=1)
        with self.assertRaises(ValueError):
            build_order_report(self.september, limit=0)

    def test_order_dates_are_independent_of_cash_dates(self):
        PaymentTransaction.objects.filter(pk=self.sale.pk).update(captured_at=stamp("2026-10-01T10:00"))
        self.assertEqual(build_order_report(self.september)["summary"]["order_count"], 1)
        self.assertEqual(build_cash_report(self.september)["events"], [])
        self.assertEqual(len(build_cash_report(self.october)["events"]), 1)

    def test_paid_without_order_stays_cash_not_invented_product_sale(self):
        reservation = StockReservation.objects.create(status="expired", expires_at=stamp("2026-09-01T00:00"))
        self.payment(order=None, reservation=reservation, amount=D(17))
        report = build_cash_report(self.september)
        self.assertEqual(report["currencies"]["GEL"]["received"], D(110))
        self.assertEqual(report["currencies"]["GEL"]["unallocated_received"], D(17))
        self.assertEqual(report["currencies"]["GEL"]["product_received"], D(70))
        self.assertEqual(report["events"][-1]["issues"], ("payment_without_order",))

    def test_full_refund_reuses_original_cost_and_rounding_components(self):
        self.refund()
        policy = lambda item: (D(18), D(18))
        receipt = build_cash_report(self.september, tax_rates=policy)
        refund = build_cash_report(self.october, tax_rates=policy)
        self.assertEqual(receipt["events"][0]["allocation"], refund["events"][0]["allocation"])
        self.assertEqual(refund["currencies"]["GEL"]["known_markup_refunded"], D("33.90"))
        self.assertEqual(refund["currencies"]["GEL"]["markup_covered_lines_refunded"], 2)
        combined = build_cash_report(ReportPeriod.months("2026-09", "2026-10"), tax_rates=policy)
        self.assertEqual(combined["currencies"]["GEL"]["net_received"], D(0))
        self.assertEqual(combined["currencies"]["GEL"]["net_buffer"], D(0))

    def test_multiple_refunds_not_allocated_as_multiple_full_reversals(self):
        self.refund()
        self.refund()
        report = build_cash_report(self.october)
        self.assertEqual(report["currencies"]["GEL"]["refunded"], D(186))
        self.assertTrue(all(event["allocation"] is None for event in report["events"]))

    def test_invalid_refund_link_provider_and_chronology(self):
        refund = self.refund()
        for changes in (
            {"provider_reference": {"refund_request": {"sale_payment_id": "bad"}}},
            {"provider_reference": {"refund_request": {"sale_payment_id": self.sale.pk}}, "provider": "manual"},
            {"provider": "bog", "refunded_at": stamp("2026-09-01T00:00")},
        ):
            PaymentTransaction.objects.filter(pk=refund.pk).update(**changes)
            report = build_cash_report(ReportPeriod.months("2026-09", "2026-10"))
            event = next(event for event in report["events"] if event["kind"] == "refund")
            self.assertEqual(event["issues"], ("refund_allocation_requires_review",))

    def test_query_count_does_not_grow_with_order_count(self):
        for i in range(5):
            order = Order.objects.create(order_number=f"MANY-{i}", subtotal=D(0), total=D(0))
            self.payment(order=order)
        with self.assertNumQueries(3):
            report = build_cash_report(self.september)
        self.assertEqual(len(report["events"]), 6)

    def test_bad_line_total_excluded_from_margin_and_cash_allocation(self):
        OrderItem.objects.filter(order=self.order).update(line_total=D(34))
        report = build_order_report(self.september, tax_rates=lambda item: (D(18), D(18)))
        self.assertIn("line_total_mismatch", report["orders"][0]["issues"])
        self.assertEqual(report["summary"]["markup_covered_line_count"], 0)
        self.assertIsNone(build_cash_report(self.september)["events"][0]["allocation"])

    def test_empty_period(self):
        report = build_order_report(self.october)
        self.assertEqual(report["summary"]["order_count"], 0)
        self.assertEqual(report["orders"], [])
        self.assertEqual(build_cash_report(self.october)["currencies"], {})
