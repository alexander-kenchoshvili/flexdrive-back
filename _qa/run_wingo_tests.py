"""Run Wingo checks on disposable SQLite with outbound network disabled."""

import argparse
import os
from pathlib import Path
import sys
from unittest.mock import patch


parser = argparse.ArgumentParser()
parser.add_argument("labels", nargs="*", default=["commerce.test_wingo"])
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--make-migrations", action="store_true")
mode.add_argument("--check-migrations", action="store_true")
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({
    "APP_ENV": "development", "DJANGO_DEBUG": "False",
    "DATABASE_URL": "sqlite:///:memory:", "CACHE_ENABLED": "False",
    "USE_CLOUDINARY_MEDIA": "False", "BOG_PAYMENTS_ENABLED": "False",
    "META_CAPI_ENABLED": "False", "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DJANGO_SETTINGS_MODULE": "config.settings", "WINGO_API_KEY": "", "WINGO_ACCOUNT_MODE": "test",
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
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
with patch("socket.socket.connect", side_effect=AssertionError("Network disabled in tests")):
    if args.make_migrations:
        call_command("makemigrations", "commerce", name="wingo_reference_data", interactive=False)
    elif args.check_migrations:
        call_command("makemigrations", check=True, dry_run=True, interactive=False)
    else:
        failures = get_runner(settings)(verbosity=1, interactive=False).run_tests(args.labels)
        sys.exit(bool(failures))
