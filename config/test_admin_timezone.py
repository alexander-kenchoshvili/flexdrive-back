from datetime import datetime, timezone as utc

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from common.admin_timezone import AdminTimezoneMiddleware
from commerce.models import Order, PaymentTransaction

MOMENT = datetime(2026, 11, 20, 6, 19, 43, tzinfo=utc.utc)


class AdminTimezoneScopeTests(SimpleTestCase):
    def test_admin_render_and_form_parse_tbilisi_while_storage_clock_and_default_remain_utc(self):
        def view(request):
            self.assertEqual(timezone.get_current_timezone_name(), "Asia/Tbilisi")
            self.assertEqual(settings.TIME_ZONE, "UTC")
            parsed = forms.DateTimeField().clean("2026-11-20 10:19:43")
            self.assertEqual(parsed.astimezone(utc.utc), MOMENT)
            return HttpResponse(Template('{{ moment|date:"Y-m-d H:i:s O" }}').render(Context({"moment": MOMENT})))

        middleware = AdminTimezoneMiddleware(view)
        for path in ("/manager-fd/", "/manager-fd/commerce/order/2/change/", "/manager-fd/accounting/"):
            with timezone.override("UTC"):
                response = middleware(RequestFactory().get(path))
                self.assertContains(response, "2026-11-20 10:19:43 +0400")
                self.assertEqual(timezone.get_current_timezone_name(), "UTC")

    def test_public_api_and_similar_prefix_keep_request_timezone_and_errors_restore_it(self):
        def public(request):
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")
            return HttpResponse("ok")

        with timezone.override("UTC"):
            for path in ("/api/commerce/", "/catalog/", "/manager-fd-other/"):
                AdminTimezoneMiddleware(public)(RequestFactory().get(path))
            def broken(request):
                raise RuntimeError("test")
            with self.assertRaises(RuntimeError):
                AdminTimezoneMiddleware(broken)(RequestFactory().get("/manager-fd/"))
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")


@override_settings(LANGUAGE_CODE="en-us", STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AdminTimezoneRenderingTests(TestCase):
    def test_actual_order_page_renders_payment_times_in_tbilisi_without_rewriting_records(self):
        admin = get_user_model().objects.create_user("timezone-admin", is_staff=True, is_superuser=True)
        order = Order.objects.create(order_number="TZ-ORDER", subtotal=69, total=69)
        payment = PaymentTransaction.objects.create(order=order, provider="bog", action="sale", status="paid",
                                                    amount=69, captured_at=MOMENT)
        PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=MOMENT)
        before = list(PaymentTransaction.objects.values())
        self.client.force_login(admin)
        page = self.client.get(reverse("admin:commerce_order_change", args=[order.pk]))
        self.assertContains(page, "10:19 a.m.")
        self.assertContains(page, "თბილისის დრო (UTC+04:00)")
        self.assertNotContains(page, "6:19 a.m.")
        self.assertEqual(list(PaymentTransaction.objects.values()), before)
