from django.urls import path
from .views import BusinessDecisionView, BusinessSearchConsoleView
from .views import BusinessAccessView, BusinessLoginView, BusinessLogoutView, BusinessSessionView, BusinessReportView, BusinessOperationsView, BusinessAnalyticsView, BusinessMarketingView

app_name = "business"

urlpatterns = [
    path("search-console/", BusinessSearchConsoleView.as_view(), name="search-console"),
    path("decisions/<str:source>/", BusinessDecisionView.as_view(), name="decisions"),
    path("session/", BusinessSessionView.as_view(), name="session"),
    path("login/", BusinessLoginView.as_view(), name="login"),
    path("access/", BusinessAccessView.as_view(), name="access"),
    path("logout/", BusinessLogoutView.as_view(), name="logout"),
    path("report/", BusinessReportView.as_view(), name="report"),
    path("operations/", BusinessOperationsView.as_view(), name="operations"),
    path("analytics/", BusinessAnalyticsView.as_view(), name="analytics"),
    path("marketing/", BusinessMarketingView.as_view(), name="marketing"),
]
