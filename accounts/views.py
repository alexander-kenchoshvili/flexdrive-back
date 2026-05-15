from datetime import datetime, timezone

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from .serializers import (
    UserCreateSerializer,
    ActivationSerializer,
    GoogleAuthSerializer,
    ResendActivationSerializer,
    UserLoginSerializer,
    UserMeSerializer,
    UserProfileSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)
from .email_delivery import EmailDeliveryError
from .google_auth import GoogleAuthConfigurationError
from .utils import validate_recaptcha


def _serialize_token_expiry(raw_token, token_class):
    if not raw_token:
        return None

    try:
        token = token_class(raw_token)
        token.check_exp()
    except TokenError:
        return None

    exp = token.payload.get("exp")
    if not exp:
        return None

    return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()


def _build_session_payload(*, access_token=None, refresh_token=None):
    access_expires_at = _serialize_token_expiry(access_token, AccessToken)
    refresh_expires_at = _serialize_token_expiry(refresh_token, RefreshToken)

    return {
        "has_access": bool(access_expires_at),
        "has_refresh": bool(refresh_expires_at),
        "access_expires_at": access_expires_at,
        "refresh_expires_at": refresh_expires_at,
    }


def _api_cookie_kwargs(*, httponly=True):
    kwargs = {
        "httponly": httponly,
        "secure": settings.API_COOKIE_SECURE,
        "samesite": settings.API_COOKIE_SAMESITE,
        "path": settings.API_COOKIE_PATH,
    }
    if settings.API_COOKIE_DOMAIN:
        kwargs["domain"] = settings.API_COOKIE_DOMAIN
    return kwargs


def _api_cookie_delete_kwargs():
    kwargs = {
        "path": settings.API_COOKIE_PATH,
    }
    if settings.API_COOKIE_DOMAIN:
        kwargs["domain"] = settings.API_COOKIE_DOMAIN
    return kwargs


def _build_auth_cookie_response(*, access_token, refresh_token, message):
    response = Response(
        {
            "message": message,
            "session": _build_session_payload(
                access_token=access_token,
                refresh_token=refresh_token,
            ),
        },
        status=status.HTTP_200_OK,
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        **_api_cookie_kwargs(),
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        **_api_cookie_kwargs(),
    )
    return response


class RegisterAPIView(generics.CreateAPIView):
    serializer_class = UserCreateSerializer
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        # ჯერ ვამოწმებთ ჩვენს დამატებულ ლოგიკას
        recaptcha_token = request.data.get('recaptcha_token')
        
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="register",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "reCAPTCHA check failed."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # მხოლოდ თუ ზედა პირობა გაიარა, ვაძახებთ Django-ს სტანდარტულ ფუნქციას
        # ეს 'super()' სწორედ იმას აკეთებს, რასაც შენი ძველი კოდი აკეთებდა ავტომატურად
        try:
            return super().create(request, *args, **kwargs)
        except EmailDeliveryError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )



class ActivateAPIView(generics.GenericAPIView):
    serializer_class = ActivationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        user.is_active = True
        user.activation_token = None
        user.activation_token_created_at = None
        user.save(update_fields=["is_active", "activation_token", "activation_token_created_at"])

        return Response({"message": "Your account has been activated. Please log in."}, status=status.HTTP_200_OK)


class ResendActivationAPIView(generics.GenericAPIView):
    serializer_class = ResendActivationSerializer
    throttle_scope = "activation_resend"

    def post(self, request, *args, **kwargs):
        recaptcha_token = request.data.get("recaptcha_token")
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="resend_activation",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "message": "If an account with this email exists and is not activated, a new activation link has been sent."
            },
            status=status.HTTP_200_OK,
        )


# class LoginAPIView(generics.GenericAPIView):
#     serializer_class = UserLoginSerializer

#     def post(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         return Response(serializer.validated_data, status=status.HTTP_200_OK)
    

class LoginAPIView(generics.GenericAPIView):
    serializer_class = UserLoginSerializer
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):

        recaptcha_token = request.data.get('recaptcha_token')
        
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="login",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        

        tokens = serializer.validated_data
        access_token = tokens['access']
        refresh_token = tokens['refresh']

        return _build_auth_cookie_response(
            access_token=access_token,
            refresh_token=refresh_token,
            message="Login successful",
        )


class GoogleAuthAPIView(generics.GenericAPIView):
    serializer_class = GoogleAuthSerializer
    throttle_scope = "google_auth"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            tokens = serializer.save()
        except GoogleAuthConfigurationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return _build_auth_cookie_response(
            access_token=tokens["access"],
            refresh_token=tokens["refresh"],
            message="Google login successful",
        )


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data)


class ProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        request.user.delete()

        response = Response(
            {"message": "Account deleted successfully."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("access_token", **_api_cookie_delete_kwargs())
        response.delete_cookie("refresh_token", **_api_cookie_delete_kwargs())
        return response
    
class ForgotPasswordAPIView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    throttle_scope = 'password_reset'

    def post(self, request, *args, **kwargs):


        recaptcha_token = request.data.get('recaptcha_token')
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="forgot_password",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password reset link has been sent to your email."}, status=status.HTTP_200_OK)
    
class ResetPasswordAPIView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    throttle_scope = 'password_reset'

    def post(self, request, *args, **kwargs):

        recaptcha_token = request.data.get('recaptcha_token')
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="reset_password",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response({"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."}, status=status.HTTP_403_FORBIDDEN)
        
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("access_token", **_api_cookie_delete_kwargs())
        response.delete_cookie("refresh_token", **_api_cookie_delete_kwargs())
        return response


class LogoutAPIView(APIView):
    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        # Best-effort revoke on logout.
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        response = Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)
        # ვშლით ქუქიებს მნიშვნელობის განულებით
        response.delete_cookie("access_token", **_api_cookie_delete_kwargs())
        response.delete_cookie("refresh_token", **_api_cookie_delete_kwargs())
        return response
    

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        # შეცდომა აქ იყო: პატარა ასოებით cookies არ არსებობს
        refresh_token = request.COOKIES.get('refresh_token')

        if refresh_token:
            # DRF-ის მოთხოვნაში მონაცემების ჩასამატებლად
            request.data['refresh'] = refresh_token

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            next_access_token = response.data.get('access')
            next_refresh_token = response.data.get('refresh') or refresh_token
            response.set_cookie(
                key='access_token',
                value=next_access_token,
                **_api_cookie_kwargs(),
            )
            if response.data.get('refresh'):
                response.set_cookie(
                    key='refresh_token',
                    value=response.data['refresh'],
                    **_api_cookie_kwargs(),
                )
            response.data = {
                "message": "Token refreshed",
                "session": _build_session_payload(
                    access_token=next_access_token,
                    refresh_token=next_refresh_token,
                ),
            }

        return response
    

@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            _build_session_payload(
                access_token=request.COOKIES.get("access_token"),
                refresh_token=request.COOKIES.get("refresh_token"),
            )
        )

        # ✅ თუ cookie არ არსებობს
        if not refresh_token:
            return Response({"has_refresh": False})

        # ✅ ვამოწმებთ token-ის ვალიდურობას
        try:
            RefreshToken(refresh_token)  # თუ expired ან invalid → TokenError
            return Response({"has_refresh": True})
        except TokenError:
            # Token არსებობს, მაგრამ expired ან invalid
            return Response({"has_refresh": False})

# class SessionStatusView(APIView):
#     permission_classes = [AllowAny]

#     def get(self, request):
#         refresh_cookie_name = "refresh_token"

#         has_refresh = bool(request.COOKIES.get(refresh_cookie_name))
#         return Response({"has_refresh": has_refresh})



# class CustomTokenRefreshView(TokenRefreshView):
#     def post(self, request, *args, **kwargs):
#         # ვამოწმებთ, თუ გვაქვს რეფრეშ ტოკენი ქუქიში
#         # refresh_token = request.cookies.get('refresh_token')
#         refresh_token = request.COOKIES.get('refresh_token')

#         if refresh_token:
#             # ვაწვდით ტოკენს SimpleJWT-ს ისე, თითქოს body-ში იყოს
#             request.data['refresh'] = refresh_token

#         response = super().post(request, *args, **kwargs)

#         if response.status_code == 200:
#             # ახალ access ტოკენს ისევ ქუქიში ვსვამთ
#             response.set_cookie(
#                 key='access_token',
#                 value=response.data['access'],
#                 httponly=True,
#                 secure=True,
#                 samesite='Lax'
#             )
#             # წავშალოთ access ტექსტური პასუხიდან
#             del response.data['access']

#         return response
