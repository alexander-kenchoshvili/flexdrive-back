"""Use Tbilisi for admin rendering/forms without changing UTC storage or public requests."""
from django.utils import timezone


class AdminTimezoneMiddleware:
    sync_capable = True
    async_capable = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == "/manager-fd" or request.path_info.startswith("/manager-fd/"):
            # Django renders TemplateResponse inside get_response, before exiting.
            with timezone.override("Asia/Tbilisi"):
                return self.get_response(request)
        return self.get_response(request)
