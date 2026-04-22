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
