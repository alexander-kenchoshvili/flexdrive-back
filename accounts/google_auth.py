from django.conf import settings


class GoogleAuthError(Exception):
    pass


class GoogleAuthConfigurationError(GoogleAuthError):
    pass


def verify_google_id_token(credential):
    client_id = str(getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "") or "").strip()
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
        raise GoogleAuthError("Google credential could not be verified.") from exc

    issuer = id_info.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleAuthError("Google credential issuer is invalid.")

    return id_info
