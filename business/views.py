from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.utils import validate_recaptcha
from .authentication import (
    BUSINESS_COOKIE,
    BUSINESS_COOKIE_PATH,
    SESSION_KIND,
    BusinessSessionAuthentication,
    CanViewDashboard,
    can_view_dashboard,
    get_business_session,
    session_store,
)
from .throttling import BusinessLoginAccountThrottle, BusinessLoginIpThrottle
from .reports import ReportPeriod, TBILISI, build_dashboard_report
from .operations import build_operations_report
from .analytics import build_analytics_report
from .marketing import build_marketing_report


def actor(user):
    return {"id": user.pk, "username": user.username}


def cookie_options():
    options = {
        "path": BUSINESS_COOKIE_PATH,
        "samesite": settings.API_COOKIE_SAMESITE,
        "secure": settings.API_COOKIE_SECURE,
    }
    if settings.API_COOKIE_DOMAIN:
        options["domain"] = settings.API_COOKIE_DOMAIN
    return options


class BusinessLoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)
    recaptcha_token = serializers.CharField(max_length=8192, write_only=True)


class BusinessAPIView(APIView):
    authentication_classes = (BusinessSessionAuthentication,)
    permission_classes = (CanViewDashboard,)
    throttle_scope = "business_dashboard"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class BusinessSessionView(BusinessAPIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        allowed = can_view_dashboard(request.user)
        return Response({"authenticated": allowed, "user": actor(request.user) if allowed else None})


@method_decorator(sensitive_post_parameters("username", "password", "recaptcha_token"), name="dispatch")
class BusinessLoginView(BusinessAPIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (BusinessLoginIpThrottle, BusinessLoginAccountThrottle)

    def post(self, request):
        payload = BusinessLoginInput(data=request.data)
        if not payload.is_valid():
            return Response({"detail": "შეავსეთ შესვლის მონაცემები."}, status=status.HTTP_400_BAD_REQUEST)
        values = payload.validated_data
        if not validate_recaptcha(
            values["recaptcha_token"],
            expected_action="business_login",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა. სცადეთ ხელახლა.", "code": "captcha_failed"},
                status=status.HTTP_403_FORBIDDEN,
            )
        user = authenticate(request=request._request, username=values["username"], password=values["password"])
        if not can_view_dashboard(user):
            return Response(
                {"detail": "შესვლის მონაცემები არასწორია ან წვდომა შეზღუდულია."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rotate this business login only, without touching customer/admin sessions.
        previous = get_business_session(request)
        if previous.get("kind") == SESSION_KIND:
            previous.delete()
        session = session_store()
        session["kind"] = SESSION_KIND
        session["user_id"] = str(user.pk)
        session["auth_hash"] = user.get_session_auth_hash()
        session.set_expiry(settings.SESSION_COOKIE_AGE)
        session.create()
        update_last_login(None, user)
        response = Response({"authenticated": True, "user": actor(user)})
        response.set_cookie(
            BUSINESS_COOKIE,
            session.session_key,
            httponly=True,
            max_age=None if settings.SESSION_EXPIRE_AT_BROWSER_CLOSE else session.get_expiry_age(),
            **cookie_options(),
        )
        return response


class BusinessAccessView(BusinessAPIView):
    def get(self, request):
        return Response({"authenticated": True, "user": actor(request.user), "stage": "foundation"})


class BusinessLogoutView(BusinessAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        session = get_business_session(request)
        if session.get("kind") == SESSION_KIND:
            session.delete()
        response = Response({"authenticated": False, "user": None})
        options = cookie_options()
        options.pop("secure")
        response.delete_cookie(BUSINESS_COOKIE, **options)
        return response


class BusinessReportInput(serializers.Serializer):
    start = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    end = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])


class BusinessOperationsInput(serializers.Serializer):
    returns = serializers.ChoiceField(choices=("awaiting", "received", "not_required", "all"), default="awaiting")
    payments = serializers.ChoiceField(choices=("attention", "pending", "failed", "issues"), default="attention")
    returns_page = serializers.IntegerField(min_value=1, max_value=1000000, default=1)
    stock_page = serializers.IntegerField(min_value=1, max_value=1000000, default=1)
    payments_page = serializers.IntegerField(min_value=1, max_value=1000000, default=1)


class BusinessOperationsView(BusinessAPIView):
    def get(self, request):
        payload = BusinessOperationsInput(data=request.query_params)
        if not payload.is_valid():
            return Response({"detail": "შეამოწმეთ სიის ფილტრი ან გვერდის ნომერი."}, status=400)
        return Response(build_operations_report(payload.validated_data))


class BusinessReportView(BusinessAPIView):
    def get(self, request):
        from django.utils import timezone

        payload = BusinessReportInput(data=request.query_params)
        if not payload.is_valid():
            return Response({"detail": "მიუთითეთ სწორი საწყისი და საბოლოო თარიღები."}, status=400)
        values = payload.validated_data
        if bool("start" in values) != bool("end" in values):
            return Response({"detail": "მიუთითეთ ორივე თარიღი."}, status=400)
        today = timezone.now().astimezone(TBILISI).date()
        try:
            period = ReportPeriod(values.get("start", today.replace(day=1)), values.get("end", today))
            report = build_dashboard_report(period)
        except (ValueError, OverflowError):
            return Response({"detail": "აირჩიეთ სწორი პერიოდი, არაუმეტეს 366 დღისა."}, status=400)
        return Response(report)


class BusinessAnalyticsView(BusinessAPIView):
    def build_report(self, period):
        return build_analytics_report(period)

    def get(self, request):
        from django.utils import timezone

        payload = BusinessReportInput(data=request.query_params)
        if not payload.is_valid():
            return Response({"detail": "მიუთითეთ სწორი საწყისი და საბოლოო თარიღები."}, status=400)
        values = payload.validated_data
        if ("start" in values) != ("end" in values):
            return Response({"detail": "მიუთითეთ ორივე თარიღი."}, status=400)
        today = timezone.now().astimezone(TBILISI).date()
        try:
            period = ReportPeriod(values.get("start", today.replace(day=1)), values.get("end", today))
            if period.end > today or (period.end - period.start).days >= 366:
                raise ValueError("Future report")
        except (ValueError, OverflowError):
            return Response({"detail": "აირჩიეთ სწორი პერიოდი, არაუმეტეს 366 დღისა და დღევანდელ დღემდე."}, status=400)
        return Response(self.build_report(period))


class BusinessMarketingView(BusinessAnalyticsView):
    def build_report(self, period):
        return build_marketing_report(period)
