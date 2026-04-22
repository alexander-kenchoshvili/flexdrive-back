from django.urls import path
from .contact_views import ContactInquiryCreateAPIView
from .views import (
    BlogPostListAPIView,
    FooterAPIView,
    GetCurrentContentAPIView,
    MenuListAPIView,
    PageDetailAPIView,
    SitemapEntriesAPIView,
    SiteSettingsAPIView,
)

urlpatterns = [
    path("blog/posts/", BlogPostListAPIView.as_view(), name="blog-post-list"),
    path("footer/", FooterAPIView.as_view(), name="footer"),
    path("sitemap/", SitemapEntriesAPIView.as_view(), name="sitemap-entries"),
    path("site-settings/", SiteSettingsAPIView.as_view(), name="site-settings"),
    path("getCurrentContent/", GetCurrentContentAPIView.as_view(), name="get-current-content"),
    path("menu/", MenuListAPIView.as_view(), name="menu"),
    path("contact/inquiries/", ContactInquiryCreateAPIView.as_view(), name="contact-inquiry-create"),
    path("<slug:slug>/", PageDetailAPIView.as_view(), name="page-detail"),
]

