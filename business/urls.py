from django.urls import path
from .checkout_views import BusinessCartView, BusinessCheckoutView, CheckoutProgressView
from .views import BusinessAudienceView, BusinessMetaEventsView
from .views import BusinessDecisionView, BusinessSearchConsoleView, BusinessPagesView, BusinessDevicesView
from .views import BusinessVehicleDemandView
from .views import BusinessAccessView, BusinessLoginView, BusinessLogoutView, BusinessSessionView, BusinessReportView, BusinessOperationsView, BusinessAnalyticsView, BusinessMarketingView

app_name = "business"

urlpatterns = [
    path("meta-events/", BusinessMetaEventsView.as_view(), name="meta-events"),
    path("carts/", BusinessCartView.as_view(), name="carts"),
    path("audience/", BusinessAudienceView.as_view(), name="audience"),
    path("checkout/", BusinessCheckoutView.as_view(), name="checkout"),
    path("checkout-progress/", CheckoutProgressView.as_view(), name="checkout-progress"),
    path("devices/", BusinessDevicesView.as_view(), name="devices"),
    path("vehicle-demand/", BusinessVehicleDemandView.as_view(), name="vehicle-demand"),
    path("pages/", BusinessPagesView.as_view(), name="pages"),
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
