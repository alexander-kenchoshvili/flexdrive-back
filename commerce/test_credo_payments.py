import hashlib
import traceback
from decimal import Decimal
from unittest.mock import Mock

import requests
from django.test import SimpleTestCase

from .credo_payments import (
    DELIVERY_PRODUCT_ID,
    CredoConfigurationError, CredoPaymentsClient, CredoProduct, CredoResponseError,
    CredoTransportError, CredoValidationError,
)


class CredoPaymentsClientTests(SimpleTestCase):
    def setUp(self):
        self.http = Mock()
        self.options = {
            "merchant_id": "999999999999", "secret_key": "secret!@#",
            "order_url": "https://bank.example/widget_api/order.php",
            "status_url": "https://bank.example/widget/api.php",
            "redirect_origin": "https://bank.example", "http_client": self.http,
        }
        self.client = CredoPaymentsClient(**self.options)
        self.products = [
            CredoProduct("112233", "TEST PRODUCT 1", 1, Decimal("350.00")),
            CredoProduct("112234", "TEST PRODUCT 2", 1, Decimal("200.00")),
        ]
        self.reply({"status": 200, "data": {"URL": "https://bank.example/installment/1590044"}})

    def reply(self, data, *, http_status=200):
        response = Mock()
        response.status_code = http_status
        response.json.return_value = data
        self.http.request.return_value = response
        return response

    def create(self, **overrides):
        values = {"order_code": "ORDER_001", "products": self.products, "total_amount": Decimal("550.00")}
        values.update(overrides)
        return self.client.create_order(**values)

    def test_official_cart_checksum_and_request_match_documentation(self):
        result = self.create()
        self.assertEqual(result.redirect_url, "https://bank.example/installment/1590044")
        call = self.http.request.call_args
        self.assertEqual(call.args, ("POST", self.options["order_url"]))
        self.assertEqual(call.kwargs["timeout"], (5.0, 15.0))
        self.assertIs(call.kwargs["allow_redirects"], False)
        payload = call.kwargs["json"]
        self.assertEqual(payload["check"], "22f7cc3a9f04efa5731b524e812f8e10")
        self.assertEqual(set(payload), {"merchantId", "orderCode", "check", "products"})
        self.assertEqual(payload["products"][0], {
            "id": "112233", "title": "TEST PRODUCT 1", "amount": 1, "price": 35000, "type": "0",
        })
        self.assertNotIn("Authorization", call.kwargs["headers"])
        self.assertNotIn("secret!@#", str(call))
        self.assertNotIn("1590044", repr(result))

    def test_unicode_quantity_and_tetri_preserve_exact_cart_without_surcharge(self):
        self.create(
            products=[CredoProduct("FD-00-0001", "საცდელი ავტონაწილი", 2, Decimal("3.11"))],
            total_amount=Decimal("6.22"),
        )
        payload = self.http.request.call_args.kwargs["json"]
        self.assertEqual(payload["products"], [{
            "id": "FD-00-0001", "title": "საცდელი ავტონაწილი", "amount": 2, "price": 311, "type": "0",
        }])
        expected = hashlib.md5("FD-00-0001საცდელი ავტონაწილი23110secret!@#".encode()).hexdigest()
        self.assertEqual(payload["check"], expected)

    def test_invalid_amounts_and_mismatched_totals_never_reach_bank(self):
        for amount in (True, 550.0, "NaN", "Infinity", "0", "-1", "550.001", "10000000000.00", "549.99"):
            with self.subTest(amount=amount), self.assertRaises(CredoValidationError):
                self.create(total_amount=amount)
        self.http.request.assert_not_called()

    def test_delivery_is_in_the_same_financed_total_without_changing_product_prices(self):
        products = [CredoProduct("FD-00-0001", "საცდელი ავტონაწილი", 2, Decimal("30.00"))]
        self.create(products=products, delivery_amount=Decimal("9.00"), total_amount=Decimal("69.00"))
        payload = self.http.request.call_args.kwargs["json"]
        self.assertEqual(payload["products"], [
            {"id": "FD-00-0001", "title": "საცდელი ავტონაწილი", "amount": 2, "price": 3000, "type": "0"},
            {"id": DELIVERY_PRODUCT_ID, "title": "მიწოდება", "amount": 1, "price": 900, "type": "0"},
        ])
        self.assertEqual(sum(row["amount"] * row["price"] for row in payload["products"]), 6900)
        expected = hashlib.md5(
            ("FD-00-0001საცდელი ავტონაწილი230000" + DELIVERY_PRODUCT_ID + "მიწოდება19000secret!@#").encode()
        ).hexdigest()
        self.assertEqual(payload["check"], expected)
        self.assertEqual(products[0].unit_price, Decimal("30.00"))

    def test_zero_delivery_omits_line_and_preserves_official_example(self):
        self.create(delivery_amount=Decimal("0.00"))
        payload = self.http.request.call_args.kwargs["json"]
        self.assertEqual(len(payload["products"]), 2)
        self.assertEqual(payload["check"], "22f7cc3a9f04efa5731b524e812f8e10")

    def test_invalid_delivery_double_counting_or_reserved_id_never_reaches_bank(self):
        for delivery in ("-1", "NaN", "Infinity", "0.001", True, 9.0):
            with self.subTest(delivery=delivery), self.assertRaises(CredoValidationError):
                self.create(delivery_amount=delivery)
        with self.assertRaises(CredoValidationError):
            self.create(delivery_amount=Decimal("9.00"), total_amount=Decimal("550.00"))
        with self.assertRaises(CredoValidationError):
            self.create(products=[CredoProduct(DELIVERY_PRODUCT_ID, "title", 1, Decimal("550.00"))])
        self.http.request.assert_not_called()

    def test_invalid_products_quantities_and_order_codes_never_reach_bank(self):
        for products in (
            [], None, [{}], [CredoProduct("id", "title", True, Decimal("550"))],
            [CredoProduct("id", "title", 0, Decimal("550"))],
            [CredoProduct("id", "title", Decimal("1"), Decimal("550"))],
            [CredoProduct("id", "title", 1, Decimal("550.001"))],
            [CredoProduct("", "title", 1, Decimal("550"))],
            [CredoProduct("id", "line\nbreak", 1, Decimal("550"))],
        ):
            with self.subTest(products=products), self.assertRaises(CredoValidationError):
                self.create(products=products)
        for code in ("", "a" * 51, "order&hash=bad", "სტატუსი", "\nORDER_001", None):
            with self.subTest(code=code), self.assertRaises(CredoValidationError):
                self.create(order_code=code)
        with self.assertRaises(CredoValidationError):
            self.create(currency="USD")
        self.http.request.assert_not_called()

    def test_official_status_hash_and_response_exclude_bank_pii(self):
        self.reply({"status": 200, "data": 12, "info": {
            "FirstName": "Private buyer", "PersonalNumber": "00000000001", "Mobile": "555000001",
        }})
        result = self.client.get_status(order_code="ORDER_001")
        self.assertEqual(result.application_status, 12)
        call = self.http.request.call_args
        self.assertEqual(call.args, ("GET", self.options["status_url"]))
        self.assertEqual(call.kwargs["params"], {
            "merchantId": "999999999999", "orderCode": "ORDER_001",
            "hash": "8bcb8d7ac37f7ef5a02a166401568677",
        })
        self.assertEqual(set(vars(result)), {"application_status"})
        self.assertNotIn("Private buyer", repr(result))
        self.assertNotIn("00000000001", repr(result))

    def test_all_documented_application_statuses_are_accepted(self):
        for code in (2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14):
            with self.subTest(code=code):
                self.reply({"status": 200, "data": code})
                self.assertEqual(self.client.get_status(order_code="ORDER_001").application_status, code)

    def test_unknown_status_or_wrong_json_type_is_not_guessed(self):
        for code in (200, 999, True, "12", 12.0, None, {}, []):
            with self.subTest(code=code), self.assertRaises(CredoResponseError) as caught:
                self.reply({"status": 200, "data": code})
                self.client.get_status(order_code="ORDER_001")
            self.assertEqual(caught.exception.code, "credo_unknown_application_status")

    def test_status_envelope_errors_are_distinct_from_rejection_or_cancellation(self):
        for envelope, error in (
            (300, "credo_duplicate_application"), (400, "credo_status_request_rejected"),
            (404, "credo_application_not_found"), ("200", "credo_invalid_status_envelope"),
            (True, "credo_invalid_status_envelope"), ([], "credo_invalid_status_envelope"),
        ):
            with self.subTest(envelope=envelope), self.assertRaises(CredoResponseError) as caught:
                self.reply({"status": envelope, "message": "do not log private response", "data": 7})
                self.client.get_status(order_code="ORDER_001")
            self.assertEqual(caught.exception.code, error)
            self.assertNotIn("private response", str(caught.exception))

    def test_post_transport_failure_is_unknown_and_is_never_retried(self):
        self.http.request.side_effect = requests.Timeout("private query hash=DO_NOT_LOG")
        with self.assertRaises(CredoTransportError) as caught:
            self.create()
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertFalse(caught.exception.retryable)
        self.http.request.assert_called_once()
        formatted = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn("DO_NOT_LOG", formatted)

    def test_status_transport_error_can_be_rechecked_without_claiming_rejection(self):
        self.http.request.side_effect = requests.ConnectionError("secret key and query hash")
        with self.assertRaises(CredoTransportError) as caught:
            self.client.get_status(order_code="ORDER_001")
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertTrue(caught.exception.retryable)
        self.http.request.assert_called_once()

    def test_http_errors_and_redirects_are_not_followed_or_retried(self):
        for method in ("create", "status"):
            for code in (301, 302, 307, 400, 404, 429, 500, 503):
                with self.subTest(method=method, code=code):
                    self.http.reset_mock()
                    self.reply({"status": 200, "data": 5}, http_status=code)
                    with self.assertRaises(CredoResponseError) as caught:
                        self.create() if method == "create" else self.client.get_status(order_code="ORDER_001")
                    self.assertEqual(caught.exception.outcome_unknown, method == "create")
                    self.assertEqual(caught.exception.retryable, method == "status" and code in (429, 500, 503))
                    self.http.request.assert_called_once()
                    self.assertFalse(self.http.request.call_args.kwargs["allow_redirects"])

    def test_bad_create_response_never_authorizes_a_new_attempt(self):
        for data in ({}, {"status": "200"}, {"status": 400}, {"status": 200, "data": None}, []):
            with self.subTest(data=data):
                self.reply(data)
                with self.assertRaises(CredoResponseError) as caught:
                    self.create()
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertFalse(caught.exception.retryable)

    def test_invalid_json_is_safe_for_both_operations(self):
        for create in (True, False):
            with self.subTest(create=create):
                self.reply(None).json.side_effect = ValueError("private raw body")
                with self.assertRaises(CredoResponseError) as caught:
                    self.create() if create else self.client.get_status(order_code="ORDER_001")
                self.assertEqual(caught.exception.outcome_unknown, create)
                self.assertNotIn("private raw body", str(caught.exception))

    def test_create_redirect_is_confined_to_configured_https_bank_origin(self):
        for url in (
            "http://bank.example/installment/1", "https://evil.example/installment/1",
            "https://bank.example.evil.example/installment/1", "https://bank.example:444/installment/1",
            "https://user:pass@bank.example/installment/1", "https://bank.example/installment/../admin",
            "https://bank.example/installment/%2e%2e/admin", "https://bank.example/installment/",
            "https://bank.example/other/1", "https://bank.example/installment/1?hash=private",
            "https://bank.example/installment/1#fragment", "https://bank.example/installment/1\n", None,
        ):
            with self.subTest(url=url), self.assertRaises(CredoResponseError) as caught:
                self.reply({"status": 200, "data": {"URL": url}})
                self.create()
            self.assertTrue(caught.exception.outcome_unknown)

    def test_missing_or_unsafe_configuration_fails_before_network(self):
        for overrides in (
            {"merchant_id": ""}, {"merchant_id": "0"}, {"merchant_id": True},
            {"merchant_id": "١٢٣"}, {"secret_key": " "},
            {"order_url": "http://bank.example/order"}, {"status_url": "https://user:pass@bank.example/status"},
            {"order_url": "https://bank.example:bad/order"}, {"order_url": "https://bank.example/order?key=private"},
            {"redirect_origin": "https://bank.example/installment/"},
            {"connect_timeout": 0}, {"read_timeout": True}, {"read_timeout": float("inf")},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(CredoConfigurationError):
                CredoPaymentsClient(**{**self.options, **overrides})
        self.http.request.assert_not_called()

    def test_secret_spaces_are_preserved_and_never_sent_raw(self):
        client = CredoPaymentsClient(**{**self.options, "secret_key": " secret!@# "})
        self.reply({"status": 200, "data": 2})
        client.get_status(order_code="ORDER_001")
        query = self.http.request.call_args.kwargs["params"]
        expected = hashlib.md5(b"999999999999ORDER_001 secret!@# ").hexdigest()
        self.assertEqual(query["hash"], expected)
        self.assertNotIn(" secret!@# ", str(self.http.request.call_args))
