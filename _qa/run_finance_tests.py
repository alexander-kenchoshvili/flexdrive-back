"""Run shared financial/courier reporting regressions with no external access."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({
    "APP_ENV": "development", "DJANGO_DEBUG": "False", "DATABASE_URL": "sqlite:///:memory:",
    "CACHE_ENABLED": "False", "USE_CLOUDINARY_MEDIA": "False", "BOG_PAYMENTS_ENABLED": "False",
    "META_CAPI_ENABLED": "False", "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DJANGO_SETTINGS_MODULE": "config.settings", "WINGO_API_KEY": "",
})
import django
django.setup()
from django.conf import settings
from django.test.utils import get_runner

assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
assert settings.DATABASES["default"]["NAME"] == ":memory:"
settings.DATABASES["default"]["TEST"]["NAME"] = ":memory:"
settings.ALLOWED_HOSTS = ["testserver", "localhost"]
settings.SECURE_SSL_REDIRECT = settings.SESSION_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE = False
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
with patch("socket.socket.connect", side_effect=AssertionError("Network disabled in tests")):
    failures = get_runner(settings)(verbosity=1, interactive=False).run_tests([
        "commerce.test_bog_callback_flow", "commerce.test_bog_refunds", "commerce.test_partial_refunds",
        "commerce.test_delivery_deductions", "commerce.test_bog_payments", "commerce.test_payment_reconciliation",
        "commerce.test_accounting_reports", "commerce.test_accounting_access", "commerce.test_wingo_accounting",
        "commerce.test_accounting_admin", "commerce.test_accounting_export", "commerce.test_returns_foundation",
        "business.test_reports", "business.test_operations", "business.test_wingo_panel",
    ])
sys.exit(bool(failures))
