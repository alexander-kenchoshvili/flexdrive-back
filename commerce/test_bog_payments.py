import uuid
from decimal import Decimal
from unittest.mock import Mock

import requests
from django.test import SimpleTestCase
from django.test.utils import override_settings

from .bog_payments import (
    BOG_CAPTURE_MODE,
    BOG_CURRENCY,
    BOG_PAYMENT_METHOD,
    BogAuthenticationError,
    BogConfigurationError,
    BogPaymentsClient,
    BogResponseError,
    BogTransportError,
    BogValidationError,
    redact_bog_provider_data,
)


class FakeResponse:
    def __init__(self, status_code, data=None, *, json_error=None):
        self.status_code = status_code
        self._data = data
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._data


class BogPaymentsClientTests(SimpleTestCase):
    def setUp(self):
        self.http = Mock()
        self.clock_value = 1000.0
        self.client = BogPaymentsClient(
            client_id="public-client-id",
            client_secret="private-client-secret",
            oauth_url=(
                "https://oauth2.bog.ge/auth/realms/bog/"
                "protocol/openid-connect/token"
            ),
            api_base_url="https://api.bog.ge",
            connect_timeout=5,
            read_timeout=15,
            token_refresh_skew_seconds=30,
            http_client=self.http,
            clock=lambda: self.clock_value,
        )
        self.http.post.return_value = FakeResponse(
            200,
            {
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
            },
        )

    def test_oauth_token_uses_basic_auth_and_is_cached(self):
        first = self.client._get_access_token()
        second = self.client._get_access_token()

        self.assertEqual(first, "access-token")
        self.assertEqual(second, "access-token")
        self.http.post.assert_called_once_with(
            (
                "https://oauth2.bog.ge/auth/realms/bog/"
                "protocol/openid-connect/token"
            ),
            auth=("public-client-id", "private-client-secret"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=(5.0, 15.0),
        )

    def test_oauth_token_refreshes_before_expiry(self):
        self.http.post.side_effect = [
            FakeResponse(
                200,
                {
                    "access_token": "first-token",
                    "token_type": "Bearer",
                    "expires_in": 60,
                },
            ),
            FakeResponse(
                200,
                {
                    "access_token": "second-token",
                    "token_type": "Bearer",
                    "expires_in": 60,
                },
            ),
        ]

        self.assertEqual(self.client._get_access_token(), "first-token")
        self.clock_value += 31
        self.assertEqual(self.client._get_access_token(), "second-token")
        self.assertEqual(self.http.post.call_count, 2)

    def test_create_order_sends_only_card_automatic_gel_contract(self):
        order_id = "f07f4144-1f45-4f2e-9547-38c7907a8672"
        idempotency_key = uuid.uuid4()
        self.http.request.return_value = FakeResponse(
            200,
            {
                "id": order_id,
                "_links": {
                    "details": {
                        "href": (
                            "https://api.bog.ge/payments/v1/receipt/"
                            f"{order_id}"
                        )
                    },
                    "redirect": {
                        "href": f"https://payment.bog.ge/?order_id={order_id}"
                    },
                },
            },
        )

        result = self.client.create_order(
            callback_url="https://flexdrive-back.onrender.com/api/payments/callback/",
            success_url="https://flexdrive-front.vercel.app/payment/success",
            fail_url="https://flexdrive-front.vercel.app/payment/fail",
            external_order_id="checkout-123",
            basket=[
                {
                    "product_id": "SKU-1",
                    "description": "Brake pad",
                    "quantity": 2,
                    "unit_price": Decimal("30.00"),
                }
            ],
            delivery_amount=Decimal("5.00"),
            total_amount=Decimal("65.00"),
            idempotency_key=idempotency_key,
            ttl_minutes=15,
        )

        self.assertEqual(result.order_id, order_id)
        request_call = self.http.request.call_args
        self.assertEqual(
            request_call.args,
            ("POST", "https://api.bog.ge/payments/v1/ecommerce/orders"),
        )
        self.assertEqual(
            request_call.kwargs["headers"],
            {
                "Accept": "application/json",
                "Authorization": "Bearer access-token",
                "Content-Type": "application/json",
                "Idempotency-Key": str(idempotency_key),
                "Accept-Language": "ka",
            },
        )
        payload = request_call.kwargs["json"]
        self.assertEqual(payload["capture"], BOG_CAPTURE_MODE)
        self.assertEqual(payload["payment_method"], [BOG_PAYMENT_METHOD])
        self.assertEqual(payload["purchase_units"]["currency"], BOG_CURRENCY)
        self.assertEqual(payload["purchase_units"]["total_amount"], 65.0)
        self.assertEqual(
            payload["purchase_units"]["delivery"],
            {"amount": 5.0},
        )
        self.assertNotIn("buyer", payload)
        self.assertNotIn("config", payload)
        self.assertNotIn("application_type", payload)

    def test_create_order_rejects_mismatched_total_before_network_call(self):
        with self.assertRaises(BogValidationError) as context:
            self.client.create_order(
                callback_url="https://backend.example/callback",
                success_url="https://frontend.example/success",
                fail_url="https://frontend.example/fail",
                external_order_id="checkout-123",
                basket=[
                    {
                        "product_id": "SKU-1",
                        "description": "Brake pad",
                        "quantity": 1,
                        "unit_price": "30.00",
                    }
                ],
                total_amount="31.00",
                idempotency_key=uuid.uuid4(),
            )

        self.assertEqual(context.exception.code, "bog_total_amount_mismatch")
        self.http.post.assert_not_called()
        self.http.request.assert_not_called()

    def test_create_order_rejects_sub_cent_amounts(self):
        with self.assertRaises(BogValidationError) as context:
            self.client.create_order(
                callback_url="https://backend.example/callback",
                success_url="https://frontend.example/success",
                fail_url="https://frontend.example/fail",
                external_order_id="checkout-123",
                basket=[
                    {
                        "product_id": "SKU-1",
                        "description": "Brake pad",
                        "quantity": 1,
                        "unit_price": "30.001",
                    }
                ],
                total_amount="30.001",
                idempotency_key=uuid.uuid4(),
            )

        self.assertEqual(context.exception.code, "bog_invalid_total_amount")
        self.http.post.assert_not_called()
        self.http.request.assert_not_called()

    def test_create_order_requires_https_urls_and_uuid4_idempotency(self):
        common_values = {
            "success_url": "https://frontend.example/success",
            "fail_url": "https://frontend.example/fail",
            "external_order_id": "checkout-123",
            "basket": [
                {
                    "product_id": "SKU-1",
                    "description": "Brake pad",
                    "quantity": 1,
                    "unit_price": "30.00",
                }
            ],
            "total_amount": "30.00",
        }
        with self.assertRaises(BogValidationError):
            self.client.create_order(
                callback_url="http://backend.example/callback",
                idempotency_key=uuid.uuid4(),
                **common_values,
            )
        with self.assertRaises(BogValidationError):
            self.client.create_order(
                callback_url="https://backend.example/callback",
                idempotency_key=uuid.uuid1(),
                **common_values,
            )

        self.http.post.assert_not_called()
        self.http.request.assert_not_called()

    def test_unauthorized_api_response_refreshes_token_once(self):
        order_id = "provider-order-1"
        idempotency_key = uuid.uuid4()
        self.http.post.side_effect = [
            FakeResponse(
                200,
                {
                    "access_token": "expired-token",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            ),
            FakeResponse(
                200,
                {
                    "access_token": "fresh-token",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            ),
        ]
        self.http.request.side_effect = [
            FakeResponse(401, {"key": "invalid_token"}),
            FakeResponse(
                200,
                {
                    "id": order_id,
                    "_links": {
                        "details": {
                            "href": (
                                "https://api.bog.ge/payments/v1/receipt/"
                                f"{order_id}"
                            )
                        },
                        "redirect": {
                            "href": (
                                "https://payment.bog.ge/"
                                f"?order_id={order_id}"
                            )
                        },
                    },
                },
            ),
        ]

        self.client.create_order(
            callback_url="https://backend.example/callback",
            success_url="https://frontend.example/success",
            fail_url="https://frontend.example/fail",
            external_order_id="checkout-123",
            basket=[
                {
                    "product_id": "SKU-1",
                    "description": "",
                    "quantity": 1,
                    "unit_price": "30.00",
                }
            ],
            total_amount="30.00",
            idempotency_key=idempotency_key,
        )

        first_headers = self.http.request.call_args_list[0].kwargs["headers"]
        second_headers = self.http.request.call_args_list[1].kwargs["headers"]
        self.assertEqual(first_headers["Authorization"], "Bearer expired-token")
        self.assertEqual(second_headers["Authorization"], "Bearer fresh-token")
        self.assertEqual(
            first_headers["Idempotency-Key"],
            second_headers["Idempotency-Key"],
        )

    def test_create_order_timeout_is_safe_and_marks_outcome_unknown(self):
        self.http.request.side_effect = requests.Timeout(
            "private-client-secret and access-token must not leak"
        )

        with self.assertRaises(BogTransportError) as context:
            self.client.create_order(
                callback_url="https://backend.example/callback",
                success_url="https://frontend.example/success",
                fail_url="https://frontend.example/fail",
                external_order_id="checkout-123",
                basket=[
                    {
                        "product_id": "SKU-1",
                        "description": "",
                        "quantity": 1,
                        "unit_price": "30.00",
                    }
                ],
                total_amount="30.00",
                idempotency_key=uuid.uuid4(),
            )

        error = context.exception
        self.assertTrue(error.retryable)
        self.assertTrue(error.outcome_unknown)
        self.assertNotIn("private-client-secret", str(error))
        self.assertNotIn("access-token", str(error))
        self.assertEqual(self.http.request.call_count, 1)

    def test_error_response_does_not_expose_provider_body(self):
        self.http.request.return_value = FakeResponse(
            400,
            {
                "message": (
                    "request contained private-client-secret "
                    "and customer card data"
                )
            },
        )

        with self.assertRaises(BogResponseError) as context:
            self.client.get_payment_details("provider-order-1")

        self.assertEqual(context.exception.status_code, 400)
        self.assertNotIn("private-client-secret", str(context.exception))
        self.assertNotIn("customer card data", str(context.exception))

    def test_get_payment_details_returns_only_required_normalized_fields(self):
        self.http.request.return_value = FakeResponse(
            200,
            {
                "order_id": "provider-order-1",
                "capture": "automatic",
                "external_order_id": "checkout-123",
                "order_status": {"key": "completed", "value": "Paid"},
                "buyer": {
                    "full_name": "Customer Name",
                    "email": "customer@example.com",
                    "phone_number": "+995555000000",
                },
                "purchase_units": {
                    "request_amount": "65",
                    "transfer_amount": "65.00",
                    "refund_amount": "0",
                    "currency_code": "GEL",
                },
                "payment_detail": {
                    "transfer_method": {"key": "card", "value": "Card"},
                    "transaction_id": "transaction-1",
                    "payer_identifier": "548888xxxxxx9893",
                    "card_expiry_date": "03/30",
                    "auth_code": "123456",
                },
                "actions": [
                    {
                        "action_id": "refund-action-1",
                        "action": "refund",
                        "status": "completed",
                        "code": "100",
                        "amount": "65.00",
                    }
                ],
            },
        )

        details = self.client.get_payment_details("provider-order-1")

        self.assertEqual(details.status, "completed")
        self.assertEqual(details.request_amount, Decimal("65.00"))
        self.assertEqual(details.transfer_amount, Decimal("65.00"))
        self.assertEqual(details.refund_amount, Decimal("0.00"))
        self.assertEqual(details.currency, "GEL")
        self.assertEqual(details.payment_method, "card")
        self.assertEqual(details.transaction_id, "transaction-1")
        self.assertEqual(details.actions[0].action_id, "refund-action-1")
        self.assertEqual(details.actions[0].action, "refund")
        self.assertEqual(details.actions[0].amount, Decimal("65.00"))
        self.assertEqual(details.provider_reference["buyer"], "[REDACTED]")
        self.assertEqual(
            details.provider_reference["payment_detail"]["payer_identifier"],
            "[REDACTED]",
        )
        self.assertEqual(
            details.provider_reference["payment_detail"]["card_expiry_date"],
            "[REDACTED]",
        )

    def test_get_payment_details_rejects_order_id_mismatch(self):
        self.http.request.return_value = FakeResponse(
            200,
            {"order_id": "different-provider-order"},
        )

        with self.assertRaises(BogResponseError) as context:
            self.client.get_payment_details("expected-provider-order")

        self.assertEqual(
            context.exception.code,
            "bog_payment_details_order_mismatch",
        )

    def test_full_refund_omits_amount_and_uses_idempotency_key(self):
        idempotency_key = uuid.uuid4()
        self.http.request.return_value = FakeResponse(
            202,
            {
                "key": "request_received",
                "message": "Refund request received",
                "action_id": "refund-action-1",
            },
        )

        result = self.client.refund_full(
            order_id="provider/order",
            idempotency_key=idempotency_key,
        )

        self.assertEqual(result.key, "request_received")
        self.assertEqual(result.action_id, "refund-action-1")
        self.http.request.assert_called_once_with(
            "POST",
            "https://api.bog.ge/payments/v1/payment/refund/provider%2Forder",
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer access-token",
                "Content-Type": "application/json",
                "Idempotency-Key": str(idempotency_key),
            },
            json={},
            timeout=(5.0, 15.0),
        )

    def test_invalid_authentication_response_is_rejected(self):
        self.http.post.return_value = FakeResponse(
            200,
            {
                "access_token": "",
                "expires_in": 300,
            },
        )

        with self.assertRaises(BogResponseError):
            self.client._get_access_token()

    def test_authentication_rejection_is_classified_without_body_leak(self):
        self.http.post.return_value = FakeResponse(
            401,
            {
                "message": "private-client-secret is invalid",
            },
        )

        with self.assertRaises(BogAuthenticationError) as context:
            self.client._get_access_token()

        self.assertEqual(context.exception.status_code, 401)
        self.assertNotIn("private-client-secret", str(context.exception))

    def test_non_json_success_response_is_rejected(self):
        self.http.request.return_value = FakeResponse(
            200,
            json_error=ValueError("not json"),
        )

        with self.assertRaises(BogResponseError) as context:
            self.client.get_payment_details("provider-order-1")

        self.assertEqual(context.exception.code, "bog_invalid_json_response")

    def test_configuration_requires_credentials_and_https(self):
        with self.assertRaises(BogConfigurationError):
            BogPaymentsClient(
                client_id="",
                client_secret="",
                oauth_url="https://oauth.example/token",
                api_base_url="https://api.example",
                connect_timeout=5,
                read_timeout=15,
            )
        with self.assertRaises(BogConfigurationError):
            BogPaymentsClient(
                client_id="client",
                client_secret="secret",
                oauth_url="http://oauth.example/token",
                api_base_url="https://api.example",
                connect_timeout=5,
                read_timeout=15,
            )

    @override_settings(BOG_PAYMENTS_ENABLED=False)
    def test_settings_factory_refuses_to_run_while_feature_is_disabled(self):
        with self.assertRaises(BogConfigurationError) as context:
            BogPaymentsClient.from_settings()

        self.assertEqual(context.exception.code, "bog_payments_disabled")

    def test_redaction_recurses_through_objects_and_lists(self):
        redacted = redact_bog_provider_data(
            {
                "order_id": "order-1",
                "buyer": {"email": "customer@example.com"},
                "actions": [
                    {
                        "action_id": "action-1",
                        "payer_identifier": "masked-pan",
                    }
                ],
            }
        )

        self.assertEqual(redacted["order_id"], "order-1")
        self.assertEqual(redacted["buyer"], "[REDACTED]")
        self.assertEqual(
            redacted["actions"][0]["payer_identifier"],
            "[REDACTED]",
        )
