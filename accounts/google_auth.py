from django.conf import settings
import logging
import requests
from urllib.parse import urlencode


logger = logging.getLogger(__name__)
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_SCOPE = "openid email profile"
GOOGLE_OAUTH_TIMEOUT_SECONDS = 10


class GoogleAuthError(Exception):
    pass


class GoogleAuthConfigurationError(GoogleAuthError):
    pass


def get_google_oauth_client_id():
    return str(getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "") or "").strip()


def get_google_oauth_redirect_uri():
    return str(getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "") or "").strip()


def require_google_oauth_redirect_config():
    client_id = get_google_oauth_client_id()
    client_secret = str(
        getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "") or ""
    ).strip()
    redirect_uri = get_google_oauth_redirect_uri()

    if not client_id:
        raise GoogleAuthConfigurationError("Google auth is not configured.")

    if not client_secret:
        raise GoogleAuthConfigurationError("Google OAuth client secret is not configured.")

    if not redirect_uri:
        raise GoogleAuthConfigurationError("Google OAuth redirect URI is not configured.")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def build_google_oauth_authorization_url(*, state):
    config = require_google_oauth_redirect_config()
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": GOOGLE_OAUTH_SCOPE,
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_OAUTH_AUTH_URL}?{query}"


def exchange_google_authorization_code(code):
    if not code:
        raise GoogleAuthError("Google authorization code is missing.")

    config = require_google_oauth_redirect_config()

    try:
        response = requests.post(
            GOOGLE_OAUTH_TOKEN_URL,
            data={
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            },
            timeout=GOOGLE_OAUTH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Google authorization code exchange failed.")
        raise GoogleAuthError("Google authorization could not be completed.") from exc

    token_payload = response.json()
    id_token_value = token_payload.get("id_token")
    if not id_token_value:
        raise GoogleAuthError("Google authorization did not return an ID token.")

    return id_token_value


def verify_google_id_token(credential):
    client_id = get_google_oauth_client_id()
    if not client_id:
        raise GoogleAuthConfigurationError("Google auth is not configured.")

    if not credential:
        raise GoogleAuthError("Google credential is required.")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
    except ImportError as exc:
        raise GoogleAuthConfigurationError(
            "Google auth dependency is not installed."
        ) from exc

    try:
        id_info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=getattr(
                settings,
                "GOOGLE_AUTH_CLOCK_SKEW_SECONDS",
                30,
            ),
        )
    except Exception as exc:
        logger.exception("Google credential verification failed.")
        message = "Google credential could not be verified."
        if settings.DEBUG:
            message = f"{message} {exc.__class__.__name__}: {exc}"
        raise GoogleAuthError(message) from exc

    issuer = id_info.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleAuthError("Google credential issuer is invalid.")

    return id_info
