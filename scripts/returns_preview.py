"""Isolated, offline return demo. Run with venv Python; never imported by the app.

Fresh SQLite per launch, loopback-only server, outbound sockets disabled, fake BOG.
"""
import os
from pathlib import Path
import socket
import sys
import tempfile
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE RETURN DEMO: outbound network is blocked")


def disable_network():
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.socket.sendto = blocked
    socket.create_connection = blocked
    original_lookup = socket.getaddrinfo

    def local_lookup(host, *args, **kwargs):
        if host not in {None, "localhost", "127.0.0.1", "::1"}:
            return blocked()
        return original_lookup(host, *args, **kwargs)

    socket.getaddrinfo = local_lookup
    socket.gethostbyname = blocked
    socket.gethostbyname_ex = blocked
    socket.gethostbyaddr = lambda host: ("localhost", [], [host])


class PreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib.auth import get_user_model, login
        from django.http import HttpResponseRedirect
        if not request.user.is_authenticated:
            login(request, get_user_model().objects.get(username="offline-demo"),
                  backend="django.contrib.auth.backends.ModelBackend")
        if request.path == "/":
            return HttpResponseRedirect("/manager-fd/commerce/order/")
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-src 'none'"
        )
        if "text/html" in response.get("Content-Type", "") and not response.streaming:
            banner = ('<div style="background:#ffe08a;color:#241c00;padding:14px;font-weight:bold">'
                      'სატესტო გარემო — ბანკის პასუხები იმიტირებულია. გარე კავშირები დაბლოკილია. '
                      'მხოლოდ ცალკე სატესტო მონაცემები.</div>')
            response.content = response.content.replace(b'<div id="container">',
                                                        banner.encode() + b'<div id="container">', 1)
            if "Content-Length" in response:
                response["Content-Length"] = len(response.content)
        return response


class FakeBank:
    def refund_full(self, *, order_id, idempotency_key):
        from commerce.bog_payments import BogRefundResult
        assert order_id.startswith("offline-return-")
        return BogRefundResult(key="request_received", message="Offline simulation",
                               action_id=f"offline-action-{order_id}", provider_reference={"offline": True})

    def get_payment_details(self, order_id):
        from commerce.bog_payments import BogPaymentDetails, BogPaymentAction
        from commerce.models import PaymentTransaction
        assert order_id.startswith("offline-return-")
        sale = PaymentTransaction.objects.get(provider_order_id=order_id, action="sale")
        refund = PaymentTransaction.objects.filter(provider_order_id=order_id, action="refund").first()
        return BogPaymentDetails(
            order_id=order_id, industry="ecommerce", status="refunded" if refund else "completed",
            external_order_id=f"FD-{sale.public_token}", capture="automatic", request_amount=sale.amount,
            transfer_amount=Decimal("0") if refund else sale.amount,
            refund_amount=sale.amount if refund else Decimal("0"), currency="GEL", payment_method="card",
            payment_option="direct_debit", transaction_id=sale.provider_transaction_id,
            response_code="100", reject_reason="", provider_reference={"offline": True},
            actions=(BogPaymentAction(action_id=f"offline-action-{order_id}", action="refund",
                                      status="completed", code="100", amount=sale.amount),) if refund else (),
        )


def seed():
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from catalog.models import Category, Product
    from commerce.models import Order, OrderItem, PaymentTransaction, OrderItemInventory
    from commerce.supplier_stock import create_supplier_stock_holds_for_order
    user = get_user_model().objects.create_superuser(username="offline-demo", email="offline@example.invalid", password=None)
    category = Category.objects.create(name="სატესტო დაბრუნებები", slug="offline-returns")
    scenarios = [
        ("01", "ჯერ არ შეგვიძენია", "სატესტო ფარი", "processing"),
        ("02", "შეძენილია და ჩვენთანაა", "სატესტო ბამპერი", "processing"),
        ("03", "მომხმარებელთანაა", "სატესტო სარკე", "delivered"),
    ]
    for number, label, name, status in scenarios:
        product = Product.objects.create(category=category, name=name, sku=f"OFFLINE-{number}",
            internal_sku=f"FD-01-90{number}", slug=f"offline-{number}", price=Decimal("150"),
            supplier_price=Decimal("100"), stock_qty=9, supplier_stock_qty=10,
            supplier_source="cross_motors", status="published")
        order = Order.objects.create(order_number=f"TEST-{number}", payment_method="card", payment_status="paid",
            status=status, subtotal=Decimal("150"), total=Decimal("150"), first_name=label, last_name="ტესტი",
            email="offline@example.invalid", phone="555000000", city="თბილისი", address_line="სატესტო მისამართი")
        item = OrderItem.objects.create(order=order, product=product, product_name=name,
            sku=product.sku, internal_sku=product.internal_sku, quantity=1, unit_price=Decimal("150"),
            line_total=Decimal("150"), purchase_unit_gross=Decimal("100"), purchase_cost_recorded_at=timezone.now())
        OrderItemInventory.objects.create(order_item=item, external_quantity=1, external_source="cross_motors",
                                          purchase_total_gross=Decimal("100"))
        create_supplier_stock_holds_for_order(order=order)
        PaymentTransaction.objects.create(order=order, provider="bog", payment_method="card", action="sale",
            status="paid", amount=Decimal("150"), currency="GEL", provider_order_id=f"offline-return-{number}",
            provider_transaction_id=f"offline-sale-{number}", captured_at=timezone.now())
    return user


def main():
    disable_network()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["APP_ENV"] = "development"
    os.environ["DJANGO_DEBUG"] = "true"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from django.conf import settings
    preview_dir = Path(tempfile.mkdtemp(prefix="flexdrive-returns-"))
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(preview_dir / "db.sqlite3")}}
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
    settings.SECURE_SSL_REDIRECT = False
    settings.SECURE_HSTS_SECONDS = 0
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.SESSION_COOKIE_DOMAIN = None
    settings.CSRF_COOKIE_DOMAIN = None
    settings.SESSION_COOKIE_NAME = "offline_return_session"
    settings.CSRF_COOKIE_NAME = "offline_return_csrf"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.CACHES = {alias: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": f"offline-{alias}"}
                       for alias in set(settings.CACHES) | {"default", "throttling"}}
    settings.STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                         "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
    settings.MEDIA_ROOT = preview_dir / "media"
    settings.MIDDLEWARE = list(settings.MIDDLEWARE) + ["__main__.PreviewMiddleware"]
    import django
    django.setup()
    # Replace transport in this process only. Real app settings/code stay unchanged.
    from commerce.bog_payments import BogPaymentsClient
    BogPaymentsClient.from_settings = classmethod(lambda cls, **kwargs: FakeBank())
    from django.contrib import admin
    admin.site.site_header = "FlexDrive — უსაფრთხო სატესტო გარემო"
    admin.site.site_title = "დაბრუნების ტესტი"
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    seed()
    if "--check" in sys.argv:
        from django.test import Client
        from commerce.models import Order, OrderReturn
        client = Client()
        for number, disposition in [("01", "not_purchased"), ("02", "on_hand"), ("03", "from_customer")]:
            order = Order.objects.get(order_number=f"TEST-{number}")
            base = f"/manager-fd/commerce/order/{order.pk}/"
            page = client.get(base + "change/")
            assert page.status_code == 200, (page.status_code, page.get("Location"), page.content[:300])
            if number == "03":
                assert client.post(base + "return-start/", {"confirm": "on"}).status_code == 302
                line = OrderReturn.objects.get(order=order).lines.get()
                assert client.post(base + "return-receive/", {"confirm": "on", f"saleable_{line.pk}": 1,
                                                            f"unsaleable_{line.pk}": 0}).status_code == 302
                payload = {"confirm": "on"}
            else:
                payload = {"disposition": disposition, "not_dispatched": "on"}
            assert client.post(base + "bog-refund/", payload).status_code == 302
            assert client.post(base + "bog-reconcile/", {}).status_code == 302
            order.refresh_from_db()
            assert order.payment_status == "refunded", order.payment_status
            product = order.items.get().product
            assert product.owned_stock_qty == (0 if number == "01" else 1)
        for attempt in [lambda: socket.create_connection(("example.com", 443)),
                        lambda: socket.socket().connect(("127.0.0.1", 443)),
                        lambda: socket.getaddrinfo("example.com", 443)]:
            try:
                attempt()
            except RuntimeError:
                pass
            else:
                raise AssertionError("Network guard failed")
        print("OFFLINE CHECK PASSED: 3 complete admin scenarios; outbound connection/DNS guards active.", flush=True)
        return
    print("READY http://127.0.0.1:8011/manager-fd/commerce/order/", flush=True)
    print(f"Isolated database: {preview_dir / 'db.sqlite3'}", flush=True)
    call_command("runserver", "127.0.0.1:8011", use_reloader=False)


if __name__ == "__main__":
    main()
