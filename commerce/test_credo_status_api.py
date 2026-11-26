import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APIClient

from .credo_checkout import apply_credo_observation
from .models import Cart, CartItem, CredoApplication
from .services import CART_TOKEN_COOKIE_NAME
from .test_credo_checkout import CredoCheckoutFixture


class CredoStatusAPITests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def url(self, application):
        return reverse("commerce-credo-application-status", kwargs={"public_token": application.public_token})

    def test_guest_needs_both_application_token_and_its_checkout_cookie(self):
        application = self.prepare().application
        denied = self.client.get(self.url(application))
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied["Cache-Control"], "no-store")
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(uuid.uuid4())
        self.assertEqual(self.client.get(self.url(application)).status_code, 404)
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        response = self.client.get(self.url(application))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["amount"], "69.00")
        self.assertFalse(response.data["ready_to_ship"])

    def test_logged_in_account_can_read_only_its_own_application(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price_snapshot=self.product.price)
        application = self.prepare(cart=cart, user=self.user).application
        self.client.force_authenticate(user=get_user_model().objects.create_user(username="other@example.test", email="other@example.test"))
        self.assertEqual(self.client.get(self.url(application)).status_code, 404)
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(self.url(application)).status_code, 200)

    def test_response_never_returns_saved_buyer_bank_identity_or_error_payload(self):
        application = self.prepare().application
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        application.needs_review = True
        application.last_issue = "credo_snapshot_integrity_failed"
        application.save()
        response = self.client.get(self.url(application))
        text = response.content.decode()
        for private in ("00000000001", "buyer@example.test", "Test address", "555000001",
                        application.merchant_id, str(self.cart.guest_token), "credo_snapshot_integrity_failed",
                        "checkout_snapshot", "owner_fingerprint", "secret_key"):
            self.assertNotIn(private, text)
        self.assertEqual(response.data["stage"], "review")
        self.assertIsNone(response.data["redirect_url"])

    def test_signed_order_is_ready_but_not_reported_as_funding_completed(self):
        application = apply_credo_observation(self.prepare().application.pk, 12)
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        response = self.client.get(self.url(application))
        self.assertTrue(response.data["ready_to_ship"])
        self.assertFalse(response.data["funding_completed"])
        self.assertEqual(response.data["order_number"], application.order.order_number)

    def test_read_only_status_does_not_claim_or_poll_the_bank(self):
        application = self.prepare().application
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        response = self.client.get(self.url(application))
        application.refresh_from_db()
        self.assertIsNone(application.bank_check_attempted_at)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("Cookie", response["Vary"])
        self.assertIn("Authorization", response["Vary"])

    def test_unknown_token_and_write_request_cannot_change_an_application(self):
        application = self.prepare().application
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        unknown = reverse("commerce-credo-application-status", kwargs={"public_token": uuid.uuid4()})
        self.assertEqual(self.client.get(unknown).status_code, 404)
        self.assertEqual(self.client.post(self.url(application), {"bank_status": 5}, format="json").status_code, 405)
        application.refresh_from_db()
        self.assertIsNone(application.bank_status)

    def test_availability_stays_disabled_until_start_flow_is_implemented(self):
        response = self.client.get(reverse("commerce-credo-availability"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(response.data["offers"], ["installment", "dayavi"])
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(CREDO_REDIRECT_ORIGIN="https://bank.example")
    def test_continuation_link_is_confined_to_the_configured_bank_origin(self):
        application = self.prepare().application
        application.submission_state = "submitted"
        application.redirect_url = "https://bank.example/installment/123"
        application.save()
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        self.assertEqual(self.client.get(self.url(application)).data["redirect_url"], application.redirect_url)
        application.redirect_url = "https://evil.example/installment/123"
        application.save(update_fields=["redirect_url"])
        self.assertIsNone(self.client.get(self.url(application)).data["redirect_url"])
