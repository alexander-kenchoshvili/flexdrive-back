"""Run the focused courier checks with a disposable database and no network."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update({
    "APP_ENV": "development", "DJANGO_DEBUG": "False",
    "DATABASE_URL": "sqlite:///:memory:", "CACHE_ENABLED": "False",
    "USE_CLOUDINARY_MEDIA": "False", "BOG_PAYMENTS_ENABLED": "False",
    "META_CAPI_ENABLED": "False", "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DJANGO_SETTINGS_MODULE": "config.settings",
})
make_migrations = "--make-migrations" in sys.argv
check_migrations = "--check-migrations" in sys.argv
sys.argv = [sys.argv[0], "test"]
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test.utils import get_runner

assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
assert settings.DATABASES["default"]["NAME"] == ":memory:"
settings.DATABASES["default"]["TEST"]["NAME"] = ":memory:"
settings.ALLOWED_HOSTS = ["testserver", "localhost"]
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
with patch("socket.socket.connect", side_effect=AssertionError("Network disabled in tests")):
    if make_migrations:
        call_command("makemigrations", "commerce", name="redcap_reference_data", interactive=False)
    elif check_migrations:
        call_command("makemigrations", check=True, dry_run=True, interactive=False)
    else:
        runner = get_runner(settings)(verbosity=1, interactive=False)
        failures = runner.run_tests([
            "commerce.test_redcap", "commerce.test_redcap_flow", "commerce.test_bog_callback_flow",
            "commerce.test_bog_refunds", "commerce.test_partial_refunds", "commerce.test_delivery_deductions", "commerce.test_bog_payments", "commerce.test_payment_reconciliation",
            "commerce.test_accounting_reports", "commerce.test_accounting_access",
            "commerce.test_redcap_accounting", "commerce.test_accounting_admin",
            "commerce.test_accounting_export",
            "commerce.test_returns_foundation",
            "business.test_reports", "business.test_operations", "business.test_redcap_panel",
        ])
        sys.exit(bool(failures))
