from decimal import Decimal
from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .easyway import EasywayResponseError, EasywayTransportError
from .easyway_shipments import (
    EasywayShipmentError,
    build_easyway_order_payload,
    submit_easyway_shipment,
)
from .models import (
    EasywayShipmentState,
    Order,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderStatus,
)


@override_settings(
    EASYWAY_SENDER_NAME="FlexDrive LLC",
    EASYWAY_SENDER_TAX_CODE="406559040",
    EASYWAY_SENDER_ADDRESS="A. Tvalchrelidze 41",
    EASYWAY_SENDER_PHONE="+995 557 10 61 04",
    EASYWAY_SENDER_REGION_ID=24,
    EASYWAY_SENDER_CITY_ID=20,
    EASYWAY_SENDER_LEGAL_FORM_ID=3,
    EASYWAY_RECEIVER_TAX_CODE_PLACEHOLDER="11111111111",
)
class EasywayShipmentTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            order_number="ORD-EASYWAY-000001",
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PAID,
            status=OrderStatus.NEW,
            subtotal=Decimal("65.00"),
            delivery_price=Decimal("49.00"),
            total=Decimal("114.00"),
            first_name="Nino",
            last_name="Beridze",
            email="nino@example.com",
            phone="+995 555 12 34 56",
            city="Kutaisi",
            address_line="Rustaveli 10",
            delivery_provider="easyway",
            delivery_region_id=2,
            delivery_region_name="Imereti",
            delivery_city_id=30,
            delivery_city_name="Kutaisi",
            carrier_delivery_cost=Decimal("47.00"),
            delivery_margin=Decimal("2.00"),
            shipping_weight_kg=Decimal("8.00"),
            shipping_length_cm=Decimal("100.00"),
            shipping_width_cm=Decimal("50.00"),
            shipping_height_cm=Decimal("35.00"),
            delivery_package_id=2,
            note="Call before arrival",
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product_name="Brake pad",
            sku="BP-100",
            unit_price=Decimal("32.50"),
            quantity=2,
            line_total=Decimal("65.00"),
        )

    def test_payload_uses_confirmed_payment_and_receiver_values(self):
        payload = build_easyway_order_payload(self.order)

        self.assertEqual(payload["payer"], "sender")
        self.assertEqual(payload["pay_method"], "cashless")
        self.assertEqual(payload["cgd"], 0)
        self.assertEqual(payload["receiver_legal_form_id"], 1)
        self.assertEqual(payload["receiver_tax_code"], "11111111111")
        self.assertEqual(payload["sender_phone"], "557106104")
        self.assertEqual(payload["receiver_phone"], "555123456")
        self.assertEqual(payload["quantity"], 2)
        self.assertEqual(
            payload["items"],
            [
                {"code": f"{self.order.order_number}-{self.item.pk}-1"},
                {"code": f"{self.order.order_number}-{self.item.pk}-2"},
            ],
        )

    def test_success_stores_order_id_and_prevents_duplicate_submission(self):
        client = Mock()
        client.create_order.return_value = 987654

        submitted = submit_easyway_shipment(self.order, client=client)

        self.assertEqual(submitted.easyway_order_id, 987654)
        self.assertEqual(
            submitted.easyway_shipment_state,
            EasywayShipmentState.CREATED,
        )
        with self.assertRaises(ValidationError):
            submit_easyway_shipment(self.order, client=client)
        client.create_order.assert_called_once()

    def test_rejected_request_can_be_retried(self):
        client = Mock()
        client.create_order.side_effect = EasywayResponseError(
            "Rejected",
            status_code=422,
        )

        with self.assertRaises(EasywayShipmentError) as caught:
            submit_easyway_shipment(self.order, client=client)

        self.order.refresh_from_db()
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertEqual(
            self.order.easyway_shipment_state,
            EasywayShipmentState.FAILED,
        )

    def test_transport_error_blocks_automatic_retry(self):
        client = Mock()
        client.create_order.side_effect = EasywayTransportError("Timeout")

        with self.assertRaises(EasywayShipmentError) as caught:
            submit_easyway_shipment(self.order, client=client)

        self.order.refresh_from_db()
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(
            self.order.easyway_shipment_state,
            EasywayShipmentState.UNKNOWN,
        )
        with self.assertRaises(ValidationError):
            submit_easyway_shipment(self.order, client=client)
