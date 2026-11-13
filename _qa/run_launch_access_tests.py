"""Exercise the launch gate and its auth/provider boundaries on disposable SQLite."""

import argparse
import os
from pathlib import Path
import sys
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument("labels", nargs="*", default=[
    "pages.test_launch_access", "accounts.tests", "business.tests", "common.tests",
    "commerce.test_wingo_tracking", "commerce.test_accounting_access",
])
parser.add_argument("--check-migrations", action="store_true")
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The project config recognizes this flag to isolate cache/rate limits in tests.
sys.argv = ["manage.py", "test"]
os.environ.update({
    "APP_ENV": "development", "DJANGO_DEBUG": "False", "DATABASE_URL": "sqlite:///:memory:",
    "CACHE_ENABLED": "False", "USE_CLOUDINARY_MEDIA": "False", "BOG_PAYMENTS_ENABLED": "False",
    "META_CAPI_ENABLED": "False", "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DJANGO_SETTINGS_MODULE": "config.settings", "WINGO_API_KEY": "", "WINGO_ACCOUNT_MODE": "test",
    "WINGO_DELIVERY_BUFFER_GEL": "0.00", "STOREFRONT_ACCESS_GUARD_ENABLED": "False",
})
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test.utils import get_runner

assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
assert settings.DATABASES["default"]["NAME"] == ":memory:"
settings.DATABASES["default"]["TEST"]["NAME"] = ":memory:"
settings.ALLOWED_HOSTS = ["testserver", "localhost"]
settings.SECURE_SSL_REDIRECT = settings.SESSION_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE = False
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
with patch("socket.socket.connect", side_effect=AssertionError("Network disabled in launch tests")):
    if args.check_migrations:
        call_command("makemigrations", check=True, dry_run=True, interactive=False)
    else:
        sys.exit(bool(get_runner(settings)(verbosity=1, interactive=False).run_tests(args.labels)))
