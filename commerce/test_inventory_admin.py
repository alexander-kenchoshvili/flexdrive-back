from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_bog_refunds as fixtures
from .models import OrderItemInventory, OwnedStockAllocation, OwnedStockLot
from .returns import prepare_order_return, receive_order_return


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class InventoryAdminTests(TestCase):
    def setUp(self):
        fixtures.BogRefundFlowTests.setUp(self)
        self.waiting_url = reverse("admin:commerce_orderreturn_changelist")
        self.stock_url = reverse("admin:commerce_ownedstocklot_changelist")

    def test_waiting_receipt_history_and_order_action_link(self):
        self.order.status = "delivered"
        self.order.save(update_fields=["status"])
        case = prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user)
        detail_url = reverse("admin:commerce_orderreturn_change", args=[case.pk])
        self.assertContains(self.admin_client.get(self.waiting_url), self.order.order_number)
        detail = self.admin_client.get(detail_url)
        self.assertContains(detail, self.product.name)
        self.assertContains(detail, reverse("admin:commerce_order_return_receive", args=[self.order.pk]))
        line = case.lines.get()
        receive_order_return(return_case=case, inspection={line.pk: {"saleable": 1, "unsaleable": 0}}, actor=self.admin_user)
        self.assertEqual(self.admin_client.get(self.waiting_url).context["cl"].result_count, 0)
        self.assertContains(self.admin_client.get(self.waiting_url, {"receipt": "received"}), self.order.order_number)
        self.assertContains(self.admin_client.get(self.waiting_url, {"receipt": "all", "q": self.product.name}), self.order.order_number)

    def test_stock_balance_excludes_sales_but_not_restored_allocations(self):
        prepare_order_return(order=self.order, disposition="on_hand", actor=self.admin_user)
        lot = OwnedStockLot.objects.get()
        page = self.admin_client.get(self.stock_url)
        self.assertEqual(page.context["cl"].result_list[0].remaining, 1)
        self.assertContains(page, reverse("admin:commerce_order_change", args=[self.order.pk]))
        record = OrderItemInventory.objects.create(order_item=self.order.items.get(), external_quantity=0, external_source="")
        allocation = OwnedStockAllocation.objects.create(lot=lot, inventory=record, quantity=1)
        self.assertEqual(self.admin_client.get(self.stock_url).context["cl"].result_count, 0)
        page = self.admin_client.get(self.stock_url, {"balance": "empty", "q": self.product.internal_sku})
        self.assertEqual(page.context["cl"].result_list[0].remaining, 0)
        from django.utils import timezone
        OwnedStockAllocation.objects.filter(pk=allocation.pk).update(restored_at=timezone.now())
        self.assertEqual(self.admin_client.get(self.stock_url).context["cl"].result_list[0].remaining, 1)
        detail_url = reverse("admin:commerce_ownedstocklot_change", args=[lot.pk])
        self.assertIn("დარჩენილი რაოდენობა", self.admin_client.get(detail_url).content.decode().lower())
        self.assertEqual(self.admin_client.post(detail_url, {"quantity": 99}).status_code, 403)
        self.assertEqual(self.admin_client.get(reverse("admin:commerce_ownedstocklot_delete", args=[lot.pk])).status_code, 403)

    def test_permissions_keep_accountant_out_and_receipt_actions_order_only(self):
        self.order.status = "delivered"
        self.order.save(update_fields=["status"])
        case = prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user)
        self.admin_user.is_superuser = False
        self.admin_user.save(update_fields=["is_superuser"])
        self.admin_user.user_permissions.add(Permission.objects.get(codename="view_accounting_report"))
        for url in [self.waiting_url, self.stock_url]:
            self.assertEqual(self.admin_client.get(url).status_code, 403)
        # Switch from the dedicated accountant role to an ordinary stock viewer.
        self.admin_user.user_permissions.clear()
        self.admin_user.user_permissions.add(Permission.objects.get(codename="view_orderreturn"), Permission.objects.get(codename="view_ownedstocklot"))
        self.assertEqual(self.admin_client.get(self.stock_url).status_code, 200)
        detail_url = reverse("admin:commerce_orderreturn_change", args=[case.pk])
        self.assertNotContains(self.admin_client.get(detail_url), "მიღება და შემოწმება</a>")
        self.assertEqual(self.admin_client.post(detail_url, {"receipt_status": "received"}).status_code, 403)
        self.admin_user.user_permissions.add(Permission.objects.get(codename="change_order"))
        self.assertContains(self.admin_client.get(detail_url), "მიღება და შემოწმება</a>")
