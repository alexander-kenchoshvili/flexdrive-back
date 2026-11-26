import uuid
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from .credo_checkout import apply_credo_observation
from .credo_admin import CredoApplicationAdmin, credo_next_action
from .models import CredoApplication, CheckoutAttempt, OrderReturn, StockReservation, WingoShipment
from .returns import prepare_order_return
from .test_credo_checkout import CredoCheckoutFixture
from .test_wingo_shipments import WingoShipmentFixture
from .wingo_shipments import can_submit


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CredoOperationsTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        self.application = self.prepare().application
        self.staff = get_user_model().objects.create_user(username="credo-ops", email="credo-ops@example.test", is_staff=True)
        self.url = reverse("admin:commerce_credoapplication_change", args=[self.application.pk])
        self.client.force_login(self.staff)

    def grant_view(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="view_credoapplication", content_type__app_label="commerce"))

    def test_application_admin_requires_its_own_view_permission(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.grant_view()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_admin_is_read_only_and_omits_private_snapshot_credentials_and_bank_links(self):
        self.grant_view()
        response = self.client.get(self.url)
        self.assertContains(response, self.application.order_code)
        for private in ("checkout_snapshot", "owner_fingerprint", "request_fingerprint", "buyer@example.test", "00000000001", "redirect_url", "merchant_id"):
            self.assertNotContains(response, private)
        before = list(CredoApplication.objects.values())
        self.assertEqual(self.client.post(self.url, {"bank_status": 12}).status_code, 403)
        self.assertEqual(list(CredoApplication.objects.values()), before)
        model_admin = admin.site._registry[CredoApplication]
        request = RequestFactory().get(self.url); request.user = self.staff
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, self.application))
        self.assertEqual(model_admin.get_actions(request), {})

    def test_next_action_separates_signature_dispatch_delivery_and_funding(self):
        self.assertIn("ხელმოწერას", credo_next_action(self.application))
        application = apply_credo_observation(self.application.pk, 12)
        self.assertIn("მოამზადეთ", credo_next_action(application))
        application.order.status = "shipped"
        self.assertIn("კრედოს კაბინეტშიც", credo_next_action(application))
        application.order.status = "delivered"
        self.assertIn("დაუდასტურებელი მიღება", credo_next_action(application))
        application = apply_credo_observation(application.pk, 5)
        self.assertIn("ამონაწერს", credo_next_action(application))
        self.assertEqual(application.order.payment_status, "pending")

    def test_review_blocks_new_shipping_even_if_order_payment_was_marked_paid(self):
        application = apply_credo_observation(self.application.pk, 12)
        self.assertTrue(can_submit(application.order))
        self.assertFalse(WingoShipment.objects.exists())
        CredoApplication.objects.filter(pk=application.pk).update(needs_review=True)
        application.order.payment_status = "paid"
        self.assertFalse(can_submit(application.order))
        self.assertFalse(WingoShipment.objects.exists())

    def test_unlinked_credo_order_and_ordinary_unpaid_card_cannot_ship(self):
        application = apply_credo_observation(self.application.pk, 12)
        CredoApplication.objects.filter(pk=application.pk).update(order=None)
        self.assertFalse(can_submit(application.order))
        application.order.payment_method = "card"
        self.assertFalse(can_submit(application.order))

    def test_credo_return_cannot_enter_another_banks_refund_workflow(self):
        application = apply_credo_observation(self.application.pk, 12)
        self.staff.is_superuser = True; self.staff.save(update_fields=["is_superuser"])
        with self.assertRaisesMessage(ValidationError, "კრედოს შეკვეთის"):
            prepare_order_return(order=application.order, disposition="on_hand", actor=self.staff)
        self.assertFalse(OrderReturn.objects.exists())


class CredoWingoIntegrationTests(WingoShipmentFixture):
    def setUp(self):
        super().setUp()
        self.order.payment_method = "credo"
        self.order.payment_status = "pending"
        self.order.save(update_fields=["payment_method", "payment_status", "updated_at"])
        attempt = CheckoutAttempt.objects.create(key=uuid.uuid4(), source="cart", owner_fingerprint="a"*64,
                                                request_fingerprint="b"*64, order=self.order)
        reservation = StockReservation.objects.create(guest_token=uuid.uuid4(), source="cart", status="completed",
            completed_order=self.order, expires_at=timezone.now()+timedelta(minutes=20))
        self.application = CredoApplication.objects.create(checkout_attempt=attempt, reservation=reservation,
            order=self.order, merchant_id="999999999999", order_code="TEST"+attempt.key.hex,
            requested_offer="dayavi", requested_amount=self.order.total, bank_status=12)

    def test_signed_pending_credo_can_be_booked_once_with_no_money_due_from_recipient(self):
        self.assertTrue(can_submit(self.order))
        shipment = self.submit()
        self.assertEqual(shipment.order_id, self.order.pk)
        self.assertEqual(self.carrier.create_order.call_args.args[0]["recipientPaymentDue"], 0)
        self.assertFalse(can_submit(self.order))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")
        self.assertEqual(CredoApplication.objects.get(pk=self.application.pk).bank_status, 12)

    def test_needs_signature_is_not_shippable_even_if_payment_flag_is_paid(self):
        CredoApplication.objects.filter(pk=self.application.pk).update(bank_status=4)
        self.order.payment_status = "paid"; self.order.save(update_fields=["payment_status", "updated_at"])
        self.assertFalse(can_submit(self.order))
        self.carrier.create_order.assert_not_called()

    def test_completed_bank_state_does_not_offer_another_outbound_parcel(self):
        CredoApplication.objects.filter(pk=self.application.pk).update(bank_status=5)
        self.assertFalse(can_submit(self.order))
        self.carrier.create_order.assert_not_called()
