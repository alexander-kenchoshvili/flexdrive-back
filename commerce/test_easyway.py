from unittest.mock import Mock
from decimal import Decimal

import requests
from django.test import SimpleTestCase, override_settings

from commerce.easyway import (
    EasywayClient,
    EasywayConfigurationError,
    EasywayResponseError,
    EasywayTransportError,
)


class EasywayClientTests(SimpleTestCase):
    def build_client(self, http_client):
        return EasywayClient(
            api_user="12345",
            api_key="secret-key",
            api_base_url="https://easyway.example/api/",
            connect_timeout=5,
            read_timeout=15,
            http_client=http_client,
        )

    def test_regions_request_uses_documented_authorization_format(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "region": [{"id": 1, "name": "თბილისი"}],
        }
        http_client = Mock()
        http_client.request.return_value = response

        result = self.build_client(http_client).get_regions()

        self.assertEqual(result, [{"id": 1, "name": "თბილისი"}])
        http_client.request.assert_called_once_with(
            "GET",
            "https://easyway.example/api/region",
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer 12345:secret-key",
            },
            params={"lang": "ka"},
            timeout=(5.0, 15.0),
        )

    def test_transport_errors_are_normalized(self):
        http_client = Mock()
        http_client.request.side_effect = requests.Timeout("timed out")

        with self.assertRaises(EasywayTransportError):
            self.build_client(http_client).get_server_time()

    def test_cities_request_uses_region_id(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "city": [{"id": 11, "name": "საბურთალო"}],
        }
        http_client = Mock()
        http_client.request.return_value = response

        result = self.build_client(http_client).get_cities(24)

        self.assertEqual(result, [{"id": 11, "name": "საბურთალო"}])
        self.assertEqual(
            http_client.request.call_args.args[:2],
            ("GET", "https://easyway.example/api/city/24"),
        )

    def test_http_errors_are_normalized_without_exposing_response_body(self):
        response = Mock(status_code=401)
        http_client = Mock()
        http_client.request.return_value = response

        with self.assertRaises(EasywayResponseError) as caught:
            self.build_client(http_client).get_packages()

        self.assertEqual(caught.exception.status_code, 401)
        self.assertNotIn("secret", str(caught.exception))

    def test_server_error_marks_order_outcome_as_unknown(self):
        response = Mock(status_code=500)
        http_client = Mock()
        http_client.request.return_value = response

        with self.assertRaises(EasywayResponseError) as caught:
            self.build_client(http_client).create_order({"tracking_code": "TEST-1"})

        self.assertTrue(caught.exception.outcome_unknown)

    def test_create_order_returns_easyway_order_id(self):
        response = Mock(status_code=200)
        response.json.return_value = {"order_id": 123456}
        http_client = Mock()
        http_client.request.return_value = response

        order_id = self.build_client(http_client).create_order(
            {"tracking_code": "TEST-1"}
        )

        self.assertEqual(order_id, 123456)
        self.assertEqual(
            http_client.request.call_args.args[:2],
            ("POST", "https://easyway.example/api/order/insert"),
        )

    def test_create_order_accepts_single_order_id_list(self):
        response = Mock(status_code=200)
        response.json.return_value = {"order_id": [123456]}
        http_client = Mock()
        http_client.request.return_value = response

        order_id = self.build_client(http_client).create_order(
            {"tracking_code": "TEST-1"}
        )

        self.assertEqual(order_id, 123456)

    def test_explicit_provider_error_is_preserved_without_unknown_outcome(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "error": "invalid_order_date",
            "message": "Order date must be tomorrow",
        }
        http_client = Mock()
        http_client.request.return_value = response

        with self.assertRaises(EasywayResponseError) as caught:
            self.build_client(http_client).create_order(
                {"tracking_code": "TEST-1"}
            )

        self.assertFalse(caught.exception.outcome_unknown)
        self.assertIn("invalid_order_date", str(caught.exception))
        self.assertIn("Order date must be tomorrow", str(caught.exception))

    def test_cancel_order_uses_documented_get_endpoint(self):
        response = Mock(status_code=200)
        http_client = Mock()
        http_client.request.return_value = response

        self.build_client(http_client).cancel_order(1689531)

        http_client.request.assert_called_once_with(
            "GET",
            "https://easyway.example/api/order/cancel/1689531",
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer 12345:secret-key",
            },
            params=None,
            timeout=(5.0, 15.0),
        )
        response.json.assert_not_called()

    def test_http_error_preserves_safe_provider_message(self):
        response = Mock(status_code=422)
        response.json.return_value = {
            "message": "receiver_phone is invalid",
            "request": {"api_key": "must-not-appear"},
        }
        http_client = Mock()
        http_client.request.return_value = response

        with self.assertRaises(EasywayResponseError) as caught:
            self.build_client(http_client).create_order(
                {"tracking_code": "TEST-1"}
            )

        self.assertIn("receiver_phone is invalid", str(caught.exception))
        self.assertNotIn("api_key", str(caught.exception))

    def test_shipping_price_uses_documented_payload_and_returns_decimal(self):
        response = Mock(status_code=200)
        response.json.return_value = {"price": 9}
        http_client = Mock()
        http_client.request.return_value = response

        result = self.build_client(http_client).get_shipping_price(
            length=20,
            width=30,
            height=10,
            weight=2.5,
            from_city_id=11,
            to_city_id=21,
            package_id=2,
        )

        self.assertEqual(result, Decimal("9.00"))
        http_client.request.assert_called_once_with(
            "POST",
            "https://easyway.example/api/price",
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer 12345:secret-key",
            },
            params=None,
            json={
                "length": 20.0,
                "width": 30.0,
                "height": 10.0,
                "weight": 2.5,
                "from_city_id": 11,
                "to_city_id": 21,
                "package_id": 2,
            },
            timeout=(5.0, 15.0),
        )

    @override_settings(
        EASYWAY_API_USER="",
        EASYWAY_API_KEY="",
        EASYWAY_API_BASE_URL="https://easyway.ge/api",
        EASYWAY_HTTP_CONNECT_TIMEOUT_SECONDS=5,
        EASYWAY_HTTP_READ_TIMEOUT_SECONDS=15,
    )
    def test_missing_credentials_fail_before_request(self):
        with self.assertRaises(EasywayConfigurationError):
            EasywayClient.from_settings()
