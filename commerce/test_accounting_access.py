from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from .test_accounting_admin import AccountingAdminTests


class AccountingAccessTests(AccountingAdminTests):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.accountant = get_user_model().objects.create_user(
            username="accountant-test", email="accountant-test@example.invalid",
            password="Local-test-only-Pass928!", is_staff=True, is_superuser=False,
        )
        cls.group = Group.objects.create(name="Test accounting read-only")
        cls.permission = Permission.objects.get(content_type__app_label="commerce", codename="view_accounting_report")
        cls.group.permissions.add(cls.permission)
        cls.accountant.groups.add(cls.group)

    def test_login_redirects_to_accounting_only(self):
        response = self.client.post(reverse("admin:login"), {
            "username": self.accountant.username, "password": "Local-test-only-Pass928!", "next": reverse("admin:index"),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], self.url)
        self.assertNotContains(response, 'id="nav-sidebar"')
        self.assertNotContains(response, reverse("admin:accounts_customuser_changelist"))

    def test_accountant_reports_and_export_are_allowed(self):
        self.client.force_login(self.accountant)
        self.assertEqual(self.get().status_code, 200)
        response = self.get(export="xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_direct_admin_models_and_actions_are_forbidden(self):
        self.client.force_login(self.accountant)
        urls = [reverse(name) for name in (
            "admin:commerce_order_changelist", "admin:commerce_paymenttransaction_changelist",
            "admin:catalog_product_changelist", "admin:accounts_customuser_changelist", "admin:auth_group_changelist",
            "admin:autocomplete")]
        urls += [reverse("admin:commerce_order_change", args=[self.order.pk]),
                 reverse("admin:commerce_order_bog_refund", args=[self.order.pk]),
                 reverse("admin:commerce_order_easyway_submit", args=[self.order.pk])]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"action": "delete_selected"}).status_code, 403)

    def test_even_accidental_extra_model_permission_does_not_open_admin(self):
        self.accountant.user_permissions.set(Permission.objects.filter(content_type__app_label="catalog"))
        self.client.force_login(self.accountant)
        self.assertEqual(self.client.get(reverse("admin:catalog_product_changelist")).status_code, 403)

    def test_revoking_permission_or_staff_disables_report(self):
        self.client.force_login(self.accountant)
        self.group.permissions.clear()
        self.assertEqual(self.get().status_code, 403)
        self.group.permissions.add(self.permission)
        get_user_model().objects.filter(pk=self.accountant.pk).update(is_staff=False)
        self.assertEqual(self.get().status_code, 302)

    def test_own_password_change_and_logout(self):
        self.client.force_login(self.accountant)
        self.assertEqual(self.client.get(reverse("admin:password_change")).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:logout")).status_code, 200)
        self.assertEqual(self.get().status_code, 302)
