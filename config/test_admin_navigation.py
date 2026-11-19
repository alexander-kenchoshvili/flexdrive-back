from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.test import RequestFactory, SimpleTestCase

from commerce.accounting_access import AccountantAdminMiddleware
from config.admin_site import FlexDriveAdminSite, NAVIGATION
from pages.models import FooterSettings, SiteSettings


class AdminNavigationTests(SimpleTestCase):
    def setUp(self):
        # Only these singleton add checks query data during menu construction.
        # Compare old/new navigation under the same existing-singleton state.
        for model in (FooterSettings, SiteSettings):
            self.enterContext(patch.object(model.objects, "exists", return_value=True))

    def request(self, permissions=None):
        request = RequestFactory().get("/manager-fd/")
        request.user = SimpleNamespace(
            is_active=True, is_staff=True, is_superuser=permissions is None,
            has_perm=lambda permission: permissions is None or permission in permissions,
            has_module_perms=lambda app: permissions is None or any(
                permission.startswith(app + ".") for permission in permissions
            ),
        )
        return request

    def model_entries(self, app_list):
        return {
            (app["app_label"], model["object_name"]): {
                key: value for key, value in model.items() if key != "name"
            }
            for app in app_list for model in app["models"]
        }

    def test_registered_site_keeps_existing_urls_permissions_and_model_identities(self):
        self.assertIsInstance(admin.site, FlexDriveAdminSite)
        request = self.request()
        original = AdminSite.get_app_list(admin.site, request)
        actual = admin.site.get_app_list(request)
        self.assertEqual(self.model_entries(actual), self.model_entries(original))
        original_apps = {app["app_label"]: app for app in original}
        for app in actual:
            for field in ("app_url", "has_module_perms"):
                self.assertEqual(app[field], original_apps[app["app_label"]][field])
        self.assertEqual(actual[0]["app_label"], "commerce")
        self.assertEqual(actual[0]["models"][0]["object_name"], "Order")
        self.assertEqual(actual[0]["models"][0]["name"], "შეკვეთები")

    def test_app_index_still_filters_by_original_app_label(self):
        request = self.request()
        for label in NAVIGATION:
            actual = admin.site.get_app_list(request, label)
            self.assertEqual([app["app_label"] for app in actual], [label])
            original = AdminSite.get_app_list(admin.site, request, label)
            self.assertEqual(self.model_entries(actual), self.model_entries(original))

    def test_restricted_staff_does_not_gain_models_or_actions(self):
        request = self.request({"catalog.view_category"})
        original = AdminSite.get_app_list(admin.site, request)
        actual = admin.site.get_app_list(request)
        self.assertEqual(self.model_entries(actual), self.model_entries(original))
        self.assertEqual(set(self.model_entries(actual)), {("catalog", "Category")})
        category = actual[0]["models"][0]
        self.assertIsNone(category["add_url"])
        self.assertTrue(category["view_only"])

    def test_accountant_still_redirects_to_report_and_has_no_model_menu(self):
        request = self.request({"commerce.view_accounting_report"})
        request.resolver_match = SimpleNamespace(namespaces=["admin"], url_name="index")
        middleware = AccountantAdminMiddleware(lambda request: None)
        response = middleware.process_view(request, None, (), {})
        self.assertEqual(response.url, "/manager-fd/accounting/")
        self.assertEqual(admin.site.get_app_list(request), [])

    def test_navigation_never_changes_model_metadata(self):
        before = {model: (model._meta.label, model._meta.verbose_name_plural)
                  for model in admin.site._registry}
        admin.site.get_app_list(self.request())
        self.assertEqual(before, {model: (model._meta.label, model._meta.verbose_name_plural)
                                  for model in admin.site._registry})
