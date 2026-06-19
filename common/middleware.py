from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _csrf_validation_callback(request):
    return None


class ApiCsrfProtectionMiddleware:
    """
    Enforce Django's CSRF validation for state-changing API requests.

    DRF APIViews are exempt from Django's global CsrfViewMiddleware and our JWT
    authentication reads credentials from HttpOnly cookies. Without an explicit
    check, a browser can attach those cookies to a forged cross-site request.

    Keep exemptions limited to endpoints whose POST method is read-only. New
    API endpoints are protected by default.
    """

    API_PREFIX = "/api/"
    READ_ONLY_POST_PATHS = frozenset(
        {
            "/api/pages/getCurrentContent/",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.csrf_middleware = CsrfViewMiddleware(get_response)

    def __call__(self, request):
        if self._requires_csrf_validation(request):
            rejection = self.csrf_middleware.process_view(
                request,
                _csrf_validation_callback,
                (),
                {},
            )
            if rejection is not None:
                return JsonResponse(
                    {
                        "detail": "CSRF verification failed.",
                        "code": "csrf_failed",
                    },
                    status=403,
                )

        return self.get_response(request)

    def _requires_csrf_validation(self, request):
        return (
            request.method.upper() not in SAFE_HTTP_METHODS
            and request.path.startswith(self.API_PREFIX)
            and request.path not in self.READ_ONLY_POST_PATHS
        )


class NoStorePrivateApiMiddleware:
    PRIVATE_API_PREFIXES = (
        "/api/accounts/",
        "/api/commerce/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.PRIVATE_API_PREFIXES):
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
