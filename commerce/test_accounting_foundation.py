from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from .accounting_calculations import calculate_product_line, split_vat_inclusive
from .accounting_snapshots import build_purchase_snapshot, purchase_snapshot_fields


class AccountingCalculationTests(SimpleTestCase):
    def line(self, purchase, sale, quantity=1):
        return calculate_product_line(unit_purchase_gross=purchase, unit_sale_gross=sale,
                                      quantity=quantity, purchase_vat_rate=18, sale_vat_rate=18)

    def test_user_example(self):
        result = self.line('15', '35')
        self.assertEqual(result.purchase.net, Decimal('12.71'))
        self.assertEqual(result.purchase.vat, Decimal('2.29'))
        self.assertEqual(result.sale.net, Decimal('29.66'))
        self.assertEqual(result.sale.vat, Decimal('5.34'))
        self.assertEqual(result.net_markup, Decimal('16.95'))
        self.assertEqual(result.markup_percent, Decimal('133.3333333333'))

    def test_first_ten_workbook_product_examples(self):
        examples = [('340','410','59.32'), ('80','110','25.42'), ('340','420','67.80'),
                    ('550','650','84.75'), ('900','1100','169.49'), ('1100','1300','169.49'),
                    ('130','170','33.90'), ('135','170','29.66'), ('80','120','33.90'),
                    ('60','90','25.42')]
        for purchase,sale,markup in examples:
            with self.subTest(purchase=purchase,sale=sale):
                result = self.line(purchase,sale)
                self.assertEqual(result.net_markup, Decimal(markup))
                self.assertEqual(result.sale.gross, result.sale.net + result.sale.vat)
                self.assertEqual(result.purchase.gross, result.purchase.net + result.purchase.vat)
                self.assertEqual(result.sale.net, result.purchase.net + result.net_markup + result.net_rounding_adjustment)

    def test_rounding_residual_is_explicit(self):
        result = self.line('340','420')
        self.assertEqual(result.net_rounding_adjustment, Decimal('-.01'))

    def test_quantity_is_applied_before_net_rounding(self):
        result = self.line('15','35',3)
        self.assertEqual(result.purchase.gross, Decimal('45'))
        self.assertEqual(result.purchase.net, Decimal('38.14'))
        self.assertEqual(result.sale.gross, Decimal('105'))
        self.assertEqual(result.net_markup, Decimal('50.85'))

    def test_unknown_cost_is_not_zero_cost(self):
        result = self.line(None,'35')
        self.assertIsNone(result.purchase)
        self.assertIsNone(result.net_markup)
        self.assertIsNone(result.markup_percent)
        self.assertIsNone(result.net_rounding_adjustment)

    def test_zero_cost_does_not_divide_by_zero(self):
        result = self.line('0','35')
        self.assertEqual(result.purchase.net, 0)
        self.assertEqual(result.net_markup, Decimal('29.66'))
        self.assertIsNone(result.markup_percent)

    def test_unknown_tax_is_not_assumed_to_be_eighteen_or_zero(self):
        result = calculate_product_line(unit_purchase_gross='15', unit_sale_gross='35', quantity=1)
        self.assertEqual(result.sale.gross, Decimal('35'))
        self.assertIsNone(result.sale.net)
        self.assertIsNone(result.purchase.vat)
        self.assertIsNone(result.net_markup)
        self.assertIsNone(result.markup_percent)

    def test_explicit_zero_and_different_rates(self):
        zero = split_vat_inclusive('35', vat_rate=0)
        self.assertEqual(zero.net, Decimal('35'))
        self.assertEqual(zero.vat, 0)
        result = calculate_product_line(unit_purchase_gross='15',unit_sale_gross='35',quantity=1,
                                        purchase_vat_rate=0,sale_vat_rate=18)
        self.assertEqual(result.net_markup,Decimal('14.66'))

    def test_losses_and_half_up_rounding(self):
        self.assertEqual(self.line('35','15').net_markup,Decimal('-16.95'))
        self.assertEqual(split_vat_inclusive('.03',vat_rate=20).net,Decimal('.03'))

    def test_invalid_money_and_quantities_are_rejected(self):
        for value in ('NaN','Infinity','-1','0.001',True,1.2,'abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                split_vat_inclusive(value,vat_rate=18)
        for quantity in (0,-1,True,1.5):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.line('15','35',quantity)
        for rate in (-1,101,'NaN',18.0):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                split_vat_inclusive('15',vat_rate=rate)


class PurchaseSnapshotTests(SimpleTestCase):
    def test_known_missing_and_zero_are_distinct(self):
        for amount in (None,Decimal('0'),Decimal('15')):
            with self.subTest(amount=amount):
                block=build_purchase_snapshot(SimpleNamespace(supplier_price=amount))
                fields=purchase_snapshot_fields(block)
                self.assertEqual(fields['purchase_unit_gross'],amount)
                self.assertEqual(fields['purchase_cost_source'],'unavailable' if amount is None else 'catalog_supplier_price')
                self.assertTrue(timezone.is_aware(fields['purchase_cost_recorded_at']))

    def test_legacy_absence_stays_unknown(self):
        self.assertEqual(purchase_snapshot_fields(None), {
            'purchase_unit_gross':None,'purchase_cost_source':'','purchase_cost_recorded_at':None})

    def test_malformed_facts_are_rejected(self):
        valid=build_purchase_snapshot(SimpleNamespace(supplier_price=Decimal('15')))
        for override in ({'version':2},{'version':True},{'source':'invoice_confirmed'},
                         {'purchase_unit_gross':'NaN'},{'purchase_unit_gross':'-1'},
                         {'purchase_unit_gross':'15.001'},{'purchase_unit_gross':None},
                         {'recorded_at':'2026-09-29T10:00:00'},{'recorded_at':None}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                purchase_snapshot_fields({**valid,**override})
