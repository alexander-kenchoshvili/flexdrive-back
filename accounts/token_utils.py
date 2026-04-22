from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken


AUTH_TOKEN_VERSION_CLAIM = "token_version"


def get_auth_token_version(user):
    return int(getattr(user, "auth_token_version", 0) or 0)


def build_refresh_token_for_user(user):
    refresh = RefreshToken.for_user(user)
    refresh[AUTH_TOKEN_VERSION_CLAIM] = get_auth_token_version(user)
    return refresh


def revoke_user_refresh_tokens(user):
    active_tokens = OutstandingToken.objects.filter(
        user=user,
        expires_at__gt=timezone.now(),
    )
    for token in active_tokens.iterator():
        BlacklistedToken.objects.get_or_create(token=token)
