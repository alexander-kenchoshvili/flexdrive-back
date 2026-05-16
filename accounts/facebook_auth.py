from django.conf import settings
import hashlib
import hmac
import logging
import requests
from urllib.parse import urlencode


logger = logging.getLogger(__name__)
FACEBOOK_OAUTH_SCOPE = "email,public_profile"
FACEBOOK_OAUTH_TIMEOUT_SECONDS = 10


class FacebookAuthError(Exception):
    pass


class FacebookAuthConfigurationError(FacebookAuthError):
    pass


def _graph_api_version():
    version = str(getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "") or "").strip()
    return version.strip("/") or "v25.0"


def _facebook_dialog_url():
    return f"https://www.facebook.com/{_graph_api_version()}/dialog/oauth"


def _facebook_graph_url(path):
    normalized_path = str(path or "").strip("/")
    return f"https://graph.facebook.com/{_graph_api_version()}/{normalized_path}"


def get_facebook_app_id():
    return str(getattr(settings, "FACEBOOK_APP_ID", "") or "").strip()


def get_facebook_app_secret():
    return str(getattr(settings, "FACEBOOK_APP_SECRET", "") or "").strip()


def get_facebook_oauth_redirect_uri():
    return str(getattr(settings, "FACEBOOK_OAUTH_REDIRECT_URI", "") or "").strip()


def require_facebook_oauth_config():
    app_id = get_facebook_app_id()
    app_secret = get_facebook_app_secret()
    redirect_uri = get_facebook_oauth_redirect_uri()

    if not app_id:
        raise FacebookAuthConfigurationError("Facebook auth is not configured.")

    if not app_secret:
        raise FacebookAuthConfigurationError("Facebook app secret is not configured.")

    if not redirect_uri:
        raise FacebookAuthConfigurationError("Facebook OAuth redirect URI is not configured.")

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "redirect_uri": redirect_uri,
    }


def build_facebook_oauth_authorization_url(*, state):
    config = require_facebook_oauth_config()
    query = urlencode(
        {
            "client_id": config["app_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": FACEBOOK_OAUTH_SCOPE,
            "state": state,
        }
    )
    return f"{_facebook_dialog_url()}?{query}"


def _build_appsecret_proof(access_token, app_secret):
    return hmac.new(
        app_secret.encode("utf-8"),
        msg=str(access_token or "").encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def exchange_facebook_authorization_code(code):
    if not code:
        raise FacebookAuthError("Facebook authorization code is missing.")

    config = require_facebook_oauth_config()

    try:
        response = requests.get(
            _facebook_graph_url("oauth/access_token"),
            params={
                "client_id": config["app_id"],
                "redirect_uri": config["redirect_uri"],
                "client_secret": config["app_secret"],
                "code": code,
            },
            timeout=FACEBOOK_OAUTH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Facebook authorization code exchange failed.")
        raise FacebookAuthError("Facebook authorization could not be completed.") from exc

    token_payload = response.json()
    access_token = token_payload.get("access_token")
    if not access_token:
        raise FacebookAuthError("Facebook authorization did not return an access token.")

    return access_token


def fetch_facebook_profile(access_token):
    if not access_token:
        raise FacebookAuthError("Facebook access token is missing.")

    config = require_facebook_oauth_config()

    try:
        response = requests.get(
            _facebook_graph_url("me"),
            params={
                "fields": "id,name,first_name,last_name,email,picture.type(large)",
                "access_token": access_token,
                "appsecret_proof": _build_appsecret_proof(
                    access_token,
                    config["app_secret"],
                ),
            },
            timeout=FACEBOOK_OAUTH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Facebook profile fetch failed.")
        raise FacebookAuthError("Facebook profile could not be loaded.") from exc

    return response.json()
