from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .crossmotors_import import (
    build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk,
)
from .models import ArchivedProduct, Category, DraftProduct, Product, ProductSpec, SkuSequence
from .test_supplier_sync import feed_item


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ProductAdminSectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("sections", "sections@example.test", "password")
        cls.category = Category.objects.create(
            name="Section lights", slug="section-lights", sku_sequence=SkuSequence.objects.get(pk="01"),
        )
        cls.draft = cls.product("draft", "draft")
        cls.published = cls.product("published", "published", internal_sku="FD-01-0100")
        cls.manual = cls.product("manual", "archived", internal_sku="FD-01-0101")
        cls.missing = cls.product("missing", "archived", internal_sku="FD-01-0102", supplier_missing=True)

    @classmethod
    def product(cls, code, status, **kwargs):
        return Product.objects.create(
            name=f"Section {code}", sku=f"CM-{code}", slug=f"section-{code}",
            category=cls.category, price=10, supplier_price=10, stock_qty=5,
            status=status, **kwargs,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def listing(self, model="product", **query):
        return self.client.get(reverse(f"admin:catalog_{model}_changelist"), query)

    def editor(self, product):
        return reverse("admin:catalog_product_change", args=[product.pk])

    def data(self, product, **updates):
        data = {
            "name": product.name, "slug": product.slug, "sku": product.sku,
            "category": product.category_id, "status": product.status,
            "supplier_price": "10", "price": "10", "markup_percent_override": "0",
            "stock_qty": "5", "side": product.side,
            "manufacturer_part_number": product.manufacturer_part_number,
        }
        for prefix in ("images", "specs", "fitments", "supplier_stock_holds"):
            data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
        data.update(updates)
        return data

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset.values_list("pk", flat=True))

    def test_three_lists_are_disjoint_with_scoped_counts_and_navigation(self):
        for model, expected in (
            ("product", {self.published.pk}), ("draftproduct", {self.draft.pk}),
            ("archivedproduct", {self.manual.pk, self.missing.pk}),
        ):
            with self.subTest(model=model):
                response = self.listing(model)
                self.assertEqual(self.ids(response), expected)
                self.assertEqual(response.context["cl"].full_result_count, len(expected))
                self.assertContains(response, "Drafts")
                self.assertContains(response, "Archived")
                self.assertNotIn("status", response.context["cl"].list_filter)
        index = self.client.get(reverse("admin:index"))
        for model in ("product", "draftproduct", "archivedproduct"):
            self.assertContains(index, reverse(f"admin:catalog_{model}_changelist"))

    def test_crafted_status_query_cannot_cross_sections(self):
        self.assertEqual(self.ids(self.listing("product", status__exact="draft")), set())
        self.assertEqual(self.ids(self.listing("draftproduct", status__exact="published")), set())

    def test_search_and_explicit_filters_stay_within_section(self):
        Product.objects.filter(pk__in=[self.draft.pk, self.published.pk]).update(manufacturer_part_number="17A853651")
        self.assertEqual(self.ids(self.listing("draftproduct", q="17A 853 651", category__id__exact=self.category.pk)), {self.draft.pk})
        self.assertEqual(self.ids(self.listing("product", q="17A 853 651")), {self.published.pk})

    def test_archive_reasons_are_visible_filterable_and_readonly(self):
        response = self.listing("archivedproduct")
        self.assertContains(response, "მომწოდებლის სიიდან გამქრალი")
        self.assertContains(response, "ხელით დაარქივებული")
        self.assertEqual(self.ids(self.listing("archivedproduct", archive_reason="supplier")), {self.missing.pk})
        self.assertEqual(self.ids(self.listing("archivedproduct", archive_reason="manual")), {self.manual.pk})
        response = self.client.get(self.editor(self.missing))
        self.assertContains(response, "მომწოდებლის სიიდან გამქრალი")
        self.assertNotContains(response, 'name="supplier_missing"')
        self.assertEqual(response.context["product_section_label"], "Archived")

    def test_section_edit_and_history_links_open_shared_product_editor(self):
        for model, product in (("draftproduct", self.draft), ("archivedproduct", self.missing)):
            for action in ("change", "history"):
                response = self.client.get(reverse(f"admin:catalog_{model}_{action}", args=[product.pk]))
                self.assertRedirects(response, reverse(f"admin:catalog_product_{action}", args=[product.pk]))
            self.assertRedirects(self.client.get(reverse(f"admin:catalog_{model}_add")), reverse("admin:catalog_product_add"))

    def test_publish_button_saves_edits_allocates_sku_and_moves_to_products(self):
        self.assertContains(self.client.get(self.editor(self.draft)), 'name="_publish"')
        with patch("catalog.signals.invalidate_groups") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.editor(self.draft), self.data(
                    self.draft, _publish="1", name="Processed lamp", manufacturer_part_number="MANUAL-OEM",
                ))
            self.assertTrue(invalidate.called)
        self.assertRedirects(response, reverse("admin:catalog_product_changelist"))
        product = Product.objects.get(pk=self.draft.pk)
        self.assertEqual(product.name, "Processed lamp")
        self.assertEqual(product.status, "published")
        self.assertTrue(product.internal_sku.startswith("FD-01-"))
        self.assertTrue(product.preserve_manual_name)
        self.assertTrue(product.preserve_manual_oem)
        self.assertEqual(ProductSpec.objects.get(product=product, key="OEM").value, "MANUAL-OEM")
        self.assertNotIn(product.pk, self.ids(self.listing("draftproduct")))
        self.assertIn(product.pk, self.ids(self.listing()))
        self.assertNotContains(self.client.get(self.editor(product)), 'name="_publish"')

    def test_invalid_publication_keeps_draft_and_all_edits_uncommitted(self):
        category = Category.objects.create(name="Unmapped", slug="section-unmapped")
        response = self.client.post(self.editor(self.draft), self.data(
            self.draft, category=category.pk, _publish="1", name="Invalid edit",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "გამოქვეყნებამდე საჭიროა FlexDrive SKU.")
        self.assertContains(response, 'name="_publish"')
        product = Product.objects.get(pk=self.draft.pk)
        self.assertEqual(product.status, "draft")
        self.assertEqual(product.name, self.draft.name)
        self.assertIsNone(product.internal_sku)

    def test_inline_errors_prevent_publication_and_sku_allocation(self):
        response = self.client.post(self.editor(self.draft), self.data(self.draft, _publish="1", **{
            "specs-TOTAL_FORMS": "1", "specs-0-key": "OEM", "specs-0-value": "X" * 121,
            "specs-0-sort_order": "0",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OEM უნდა შეიცავდეს მაქსიმუმ 120 სიმბოლოს.")
        product = Product.objects.get(pk=self.draft.pk)
        self.assertEqual(product.status, "draft")
        self.assertIsNone(product.internal_sku)

    def test_save_routes_to_current_status_and_continue_keeps_editor(self):
        for status, model in (("draft", "draftproduct"), ("archived", "archivedproduct"), ("published", "product")):
            response = self.client.post(self.editor(self.missing), self.data(self.missing, status=status))
            self.assertRedirects(response, reverse(f"admin:catalog_{model}_changelist"))
            self.assertFalse(Product.objects.get(pk=self.missing.pk).supplier_missing)
        response = self.client.post(self.editor(self.draft), self.data(self.draft, _continue="1"))
        self.assertRedirects(response, self.editor(self.draft))

    def test_new_manual_product_saves_to_drafts(self):
        response = self.client.post(reverse("admin:catalog_product_add"), self.data(
            self.draft, name="New draft", sku="MANUAL-NEW", slug="section-new",
        ))
        self.assertRedirects(response, reverse("admin:catalog_draftproduct_changelist"))
        self.assertEqual(Product.objects.get(sku="MANUAL-NEW").status, "draft")

    def test_unrelated_save_keeps_supplier_archive_reason(self):
        response = self.client.post(self.editor(self.missing), self.data(self.missing, name="Updated archived name"))
        self.assertRedirects(response, reverse("admin:catalog_archivedproduct_changelist"))
        self.assertTrue(Product.objects.get(pk=self.missing.pk).supplier_missing)

    def test_product_editor_permission_is_sufficient_for_draft_and_archive_actions(self):
        user = get_user_model().objects.create_user("editor", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="change_product"))
        self.client.force_login(user)
        response = self.client.post(reverse("admin:catalog_draftproduct_change", args=[self.draft.pk]),
                                    self.data(self.draft, _publish="1"))
        self.assertRedirects(response, reverse("admin:catalog_product_changelist"))
        self.assertEqual(Product.objects.get(pk=self.draft.pk).status, "published")
        response = self.client.post(reverse("admin:catalog_archivedproduct_changelist"), {
            "action": "action_unpublish", "_selected_action": [self.missing.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(pk=self.missing.pk).status, "draft")
        self.assertFalse(Product.objects.get(pk=self.missing.pk).supplier_missing)

    def test_bulk_deletion_in_drafts_uses_product_signals_and_leaves_published(self):
        with patch("catalog.signals.invalidate_groups") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("admin:catalog_draftproduct_changelist"), {
                    "action": "delete_selected", "post": "yes", "select_across": "1",
                    "_selected_action": [self.draft.pk, self.published.pk],
                })
            self.assertTrue(invalidate.called)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.draft.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.published.pk).exists())

    def test_bulk_publish_and_manual_archive_cannot_affect_another_section(self):
        Product.objects.filter(pk=self.draft.pk).update(internal_sku="FD-01-0103")
        response = self.client.post(reverse("admin:catalog_draftproduct_changelist"), {
            "action": "action_publish", "select_across": "1", "_selected_action": [self.missing.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(pk=self.draft.pk).status, "published")
        self.assertEqual(Product.objects.get(pk=self.missing.pk).status, "archived")
        self.assertTrue(Product.objects.get(pk=self.missing.pk).supplier_missing)
        response = self.client.post(reverse("admin:catalog_product_changelist"), {
            "action": "action_archive", "_selected_action": [self.published.pk, self.missing.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(pk=self.published.pk).status, "archived")
        self.assertFalse(Product.objects.get(pk=self.published.pk).supplier_missing)
        self.assertTrue(Product.objects.get(pk=self.missing.pk).supplier_missing)

    def test_existing_product_permissions_apply_to_all_sections_without_new_grants(self):
        user = get_user_model().objects.create_user("viewer", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_product"))
        self.client.force_login(user)
        for model in ("product", "draftproduct", "archivedproduct"):
            response = self.listing(model)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["cl"].model_admin.get_actions(response.wsgi_request), {})
            response = self.client.post(reverse(f"admin:catalog_{model}_changelist"), {
                "action": "action_publish", "_selected_action": [self.draft.pk],
            })
            self.assertEqual(Product.objects.get(pk=self.draft.pk).status, "draft")
        response = self.client.post(self.editor(self.draft), self.data(self.draft, _publish="1"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Permission.objects.filter(content_type__model__in=["draftproduct", "archivedproduct"]).exists())

    def test_staff_without_product_access_cannot_access_sections(self):
        user = get_user_model().objects.create_user("unrelated", is_staff=True)
        self.client.force_login(user)
        for model in ("product", "draftproduct", "archivedproduct"):
            self.assertEqual(self.listing(model).status_code, 403)

    def test_product_editor_and_related_queries_remain_unfiltered(self):
        product_admin = admin.site.get_model_admin(Product)
        request = self.listing().wsgi_request
        self.assertEqual(product_admin.get_queryset(request).count(), 4)
        for product in (self.draft, self.missing, self.manual):
            self.assertEqual(self.client.get(self.editor(product)).status_code, 200)
        self.assertIs(admin.site.get_model_admin(DraftProduct).get_queryset(request).model, Product)
        self.assertIs(admin.site.get_model_admin(ArchivedProduct).get_queryset(request).model, Product)

    def test_supplier_imports_route_new_missing_and_returned_products_in_both_paths(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                Product.objects.all().delete()
                importer(build_crossmotors_report([feed_item()]))
                product = Product.objects.get(sku="CM-000015")
                self.assertEqual(self.ids(self.listing("draftproduct")), {product.pk})
                Product.objects.filter(pk=product.pk).update(status="published", internal_sku="FD-01-0200")
                importer(build_crossmotors_report([feed_item("000016")]), archive_missing=True, max_missing_percent=100)
                self.assertEqual(self.ids(self.listing("archivedproduct", archive_reason="supplier")), {product.pk})
                importer(build_crossmotors_report([feed_item()]))
                self.assertIn(product.pk, self.ids(self.listing()))
                self.client.post(reverse("admin:catalog_product_changelist"), {
                    "action": "action_archive", "_selected_action": [product.pk],
                })
                importer(build_crossmotors_report([feed_item()]))
                self.assertEqual(self.ids(self.listing("archivedproduct", archive_reason="manual")), {product.pk})
