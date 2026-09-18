from django.test import SimpleTestCase, override_settings

from .models import OrderPaymentMethod
from .serializers import CardPaymentCheckoutSerializer, CheckoutSerializer


class CashOnDeliveryToggleTests(SimpleTestCase):
    @override_settings(CASH_ON_DELIVERY_ENABLED=False)
    def test_disabled_cash_is_rejected_before_order_validation(self):
        serializer = CheckoutSerializer(
            data={"payment_method": OrderPaymentMethod.CASH_ON_DELIVERY},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("payment_method", serializer.errors)

    @override_settings(CASH_ON_DELIVERY_ENABLED=True)
    def test_cash_can_be_reenabled(self):
        self.assertEqual(
            CheckoutSerializer().validate_payment_method(OrderPaymentMethod.CASH_ON_DELIVERY),
            OrderPaymentMethod.CASH_ON_DELIVERY,
        )

    @override_settings(CASH_ON_DELIVERY_ENABLED=False)
    def test_card_payment_validation_is_unchanged(self):
        self.assertEqual(
            CardPaymentCheckoutSerializer().validate_payment_method(OrderPaymentMethod.CARD),
            OrderPaymentMethod.CARD,
        )
