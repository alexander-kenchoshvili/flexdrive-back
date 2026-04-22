# accounts/authenticate.py

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .token_utils import AUTH_TOKEN_VERSION_CLAIM, get_auth_token_version


class CustomAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw_token = (
            request.COOKIES.get("access_token")
            or request._request.COOKIES.get("access_token")
        )

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)

            token_version = int(validated_token.get(AUTH_TOKEN_VERSION_CLAIM, 0) or 0)
            user_token_version = get_auth_token_version(user)
            if token_version != user_token_version:
                raise AuthenticationFailed("Token is no longer valid.")

            return user, validated_token
        except (AuthenticationFailed, InvalidToken, TokenError):
            return None
