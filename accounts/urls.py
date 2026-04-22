from django.urls import path
from .views import (
    RegisterAPIView,
    ActivateAPIView,
    ResendActivationAPIView,
    LoginAPIView,
    MeAPIView,
    ProfileAPIView,
    ForgotPasswordAPIView,
    ResetPasswordAPIView,
    LogoutAPIView,
    CustomTokenRefreshView,
    SessionStatusView,
)
from rest_framework_simplejwt.views import TokenRefreshView



urlpatterns = [
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('activate/', ActivateAPIView.as_view(), name='activate'),
    path('activate/resend/', ResendActivationAPIView.as_view(), name='activate_resend'),
    path('login/', LoginAPIView.as_view(), name='login'),
    path('me/', MeAPIView.as_view(), name='me'),
    path('profile/', ProfileAPIView.as_view(), name='profile'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    # path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("session/", SessionStatusView.as_view(), name="session-status"),
    path('password/forgot/', ForgotPasswordAPIView.as_view(), name='password_forgot'),
    path('password/reset/', ResetPasswordAPIView.as_view(), name='password_reset'),
]
