import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from commerce.meta_conversions import (
    build_marketing_context, build_meta_purchase_payload, has_marketing_consent,
    send_meta_purchase_event,
)


FBP = "fb.1.1700000000000.12345"
FBC = "fb.1.1700000000000.MetaClick_CaseSensitive"


def request(consent="granted", cookies=None, **headers):
    return SimpleNamespace(
        headers={"X-FlexDrive-Marketing-Consent": consent, **headers},
        COOKIES=cookies or {}, META={"REMOTE_ADDR": "192.0.2.1", "HTTP_USER_AGENT": "Test browser"},
    )


def order(**changes):
    item = SimpleNamespace(internal_sku="FD-TEST", quantity=1, unit_price=Decimal("12"))
    return SimpleNamespace(**{
        **dict(order_number="ORD-META-TEST", public_token="private-order-access-token",
               marketing_consent=True, marketing_context={"fbp": FBP, "fbc": FBC},
               email="test@example.com", phone="555111222", first_name="Test", last_name="Buyer",
               city="Tbilisi", user_id=None, total=Decimal("12"), items=SimpleNamespace(all=lambda: [item])),
        **changes,
    })


@override_settings(FRONTEND_BASE_URL="https://flexdrive.ge", META_CAPI_TEST_EVENT_CODE="")
class MetaMarketingTests(SimpleTestCase):
    def test_context_preserves_existing_identifiers_and_never_invents_ad_click(self):
        context = build_marketing_context(request(cookies={"_fbp": FBP, "_fbc": FBC, "sessionid": "private"}))
        self.assertEqual((context["fbp"], context["fbc"]), (FBP, FBC))
        self.assertNotIn("sessionid", context)
        self.assertNotIn("fbc", build_marketing_context(request(cookies={"_fbp": FBP})))

    def test_explicit_denial_wins_over_old_granted_cookie(self):
        req = request("denied", cookies={"_fbp": FBP, "_fbc": FBC,
                      "flexdrive_cookie_consent": json.dumps({"version": 1, "marketing": True})})
        self.assertFalse(has_marketing_consent(req))
        self.assertNotIn("fbp", build_marketing_context(req))
        self.assertNotIn("fbc", build_marketing_context(req))

    def test_checkout_headers_are_validated_and_case_is_preserved(self):
        req = request(**{"X-FlexDrive-Meta-Fbp": FBP, "X-FlexDrive-Meta-Fbc": FBC})
        self.assertEqual(build_marketing_context(req)["fbc"], FBC)
        for value in ("private@example.com", "fb.1.1700000000000." + "a" * 401, "fb.1.123.bad\nheader"):
            self.assertNotIn("fbc", build_marketing_context(request(**{"X-FlexDrive-Meta-Fbc": value})))

    def test_callback_payload_uses_original_checkout_ids_and_unchanged_event_id(self):
        event = build_meta_purchase_payload(order=order())["data"][0]
        self.assertEqual(event["event_name"], "Purchase")
        self.assertEqual(event["event_id"], "purchase-ORD-META-TEST")
        self.assertEqual(event["user_data"]["fbp"], FBP)
        self.assertEqual(event["user_data"]["fbc"], FBC)
        self.assertEqual(event["custom_data"]["content_ids"], ["FD-TEST"])
        self.assertEqual(event["custom_data"]["value"], 12)
        self.assertNotIn("private-order-access-token", str(event))
        self.assertNotIn("test@example.com", str(event))

    def test_phone_hash_uses_georgian_country_code_consistently(self):
        expected = hashlib.sha256(b"995555111222").hexdigest()
        for phone in ("555111222", "+995 555 11 12 22", "00995555111222"):
            event = build_meta_purchase_payload(order=order(phone=phone))["data"][0]
            self.assertEqual(event["user_data"]["ph"], [expected])

    @override_settings(META_CAPI_ENABLED=True, META_PIXEL_ID="test-pixel", META_CAPI_ACCESS_TOKEN="test-secret", META_CAPI_TIMEOUT_SECONDS=1)
    @patch("commerce.meta_conversions.requests.post")
    def test_denied_send_is_skipped_and_approved_snapshot_is_sent_without_new_provider_calls(self, post):
        self.assertFalse(send_meta_purchase_event(order=order(marketing_consent=False)))
        post.assert_not_called()
        post.return_value = Mock()
        self.assertTrue(send_meta_purchase_event(order=order()))
        self.assertEqual(post.call_args.kwargs["json"]["data"][0]["user_data"]["fbc"], FBC)
        payload = build_meta_purchase_payload(order=order(marketing_context={}))["data"][0]
        self.assertNotIn("fbp", payload["user_data"])
        self.assertNotIn("fbc", payload["user_data"])
