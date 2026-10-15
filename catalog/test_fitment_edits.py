from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .crossmotors_import import build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk
from .fitment_content import replace_years, year_replacements
from .models import Category, Product, ProductFitment, ProductSpec, SkuSequence, VehicleEngine, VehicleMake, VehicleModel
from .test_supplier_sync import feed_item


class FitmentYearTextTests(SimpleTestCase):
    def test_complete_known_ranges_and_open_or_single_years(self):
        for text in ("Lamp 2017-2023", "Lamp 17–23", "Lamp '17 - '23", "Lamp 2017—2023", "Lamp 2017-23"):
            with self.subTest(text=text):
                self.assertEqual(replace_years(text, {(2017, 2023): (2017, 2020)}), "Lamp 2017-2020")
        for text in ("XV 18-", "XV 2018-", "XV 2018", "XV 18"):
            self.assertEqual(replace_years(text, {(2018, 2018): (2018, 2024)}), "XV 2018-2024")

    def test_unrelated_identifiers_and_other_ranges_are_literal(self):
        text = "CX-5 FD-17-23 A2017 2017cc 2017/2023 2012-2016 OEM2017-2023X"
        self.assertEqual(replace_years(text, {(2017, 2023): (2017, 2020)}), text)
        self.assertEqual(replace_years("Peugeot 2008", {(2008, 2008): (2008, 2014)}, {"2008"}), "Peugeot 2008")

    def test_replacements_are_simultaneous_without_cascading(self):
        self.assertEqual(replace_years("2012-2017 / 2018-2020", {
            (2012, 2017): (2018, 2020), (2018, 2020): (2021, 2024),
        }), "2018-2020 / 2021-2024")

    def test_shared_old_range_has_no_invented_merged_range(self):
        old = SimpleNamespace(year_from=2017, year_to=2023)
        changed = SimpleNamespace(year_from=2017, year_to=2020)
        replacements = year_replacements({1: old, 2: old}, {1: changed, 2: old})
        self.assertEqual(replacements, {(2017, 2023): None})
        self.assertEqual(replace_years("Lamp (2017-2023)", replacements), "Lamp")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AdminFitmentEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("fitment-editor", "fitment@example.test", "password")
        cls.category = Category.objects.create(name="Parts", slug="fitment-edit-parts")
        cls.make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        cls.model = VehicleModel.objects.create(make=cls.make, name="XV", slug="xv")

    def setUp(self):
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            name="Lamp Subaru XV 2017–2023 (RH)", sku="CM-000015", internal_sku="FD-01-9000",
            slug="fitment-lamp-cm-000015", category=self.category, supplier_price=100,
            markup_percent_override=20, price=120, stock_qty=9, status="published",
            supplier_source="cross_motors", side="right", manufacturer_part_number="OEM-15",
            short_description="Old short 2017-2023", description="Old description 2017-2023",
            seo_description="Old SEO 2017-2023",
        )
        self.fitment = ProductFitment.objects.create(
            product=self.product, vehicle_model=self.model, year_from=2017, year_to=2023, notes="XV 17-23",
        )
        ProductSpec.objects.create(product=self.product, key="თაობა", value="XV 17-23", sort_order=4)
        ProductSpec.objects.create(product=self.product, key="მანქანა", value="Subaru XV", sort_order=3)
        ProductSpec.objects.create(product=self.product, key="OEM", value="OEM-15", sort_order=1)
        self.url = reverse("admin:catalog_product_change", args=[self.product.pk])

    def data(self, edits=None, **changes):
        product = Product.objects.get(pk=self.product.pk)
        data = {
            "name": product.name, "sku": product.sku, "slug": product.slug,
            "category": product.category_id, "status": product.status,
            "supplier_price": str(product.supplier_price), "price": str(product.price),
            "markup_percent_override": str(product.markup_percent_override),
            "stock_qty": str(product.stock_qty), "side": product.side,
            "manufacturer_part_number": product.manufacturer_part_number,
            "short_description": product.short_description, "description": product.description,
            "seo_description": product.seo_description, "seo_title": product.seo_title or "",
        }
        for prefix in ("images", "supplier_stock_holds"):
            data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
        specs = list(product.specs.all())
        data.update({"specs-TOTAL_FORMS": str(len(specs)), "specs-INITIAL_FORMS": str(len(specs))})
        for index, spec in enumerate(specs):
            for field, value in {"id": spec.pk, "product": product.pk, "key": spec.key,
                                 "value": spec.value, "sort_order": spec.sort_order}.items():
                data[f"specs-{index}-{field}"] = value
        fitments = list(product.fitments.all())
        rows = [{"id": fitment.pk, "product": product.pk, "vehicle_model": fitment.vehicle_model_id,
                 "engine": fitment.engine_id or "", "year_from": fitment.year_from,
                 "year_to": fitment.year_to, "notes": fitment.notes} for fitment in fitments]
        if edits:
            for index, updates in edits.items():
                if index == len(rows):
                    rows.append({"id": "", "product": product.pk, "engine": "", "notes": ""})
                rows[index].update(updates)
        data.update({"fitments-TOTAL_FORMS": str(len(rows)), "fitments-INITIAL_FORMS": str(len(fitments))})
        for index, row in enumerate(rows):
            data.update({f"fitments-{index}-{field}": value for field, value in row.items()})
        data.update(changes)
        return data

    def save(self, edits=None, **changes):
        response = self.client.post(self.url, self.data(edits, **changes))
        self.assertEqual(response.status_code, 302, response.context and (
            response.context["adminform"].form.errors,
            [(inline.formset.errors, inline.formset.non_form_errors()) for inline in response.context["inline_admin_formsets"]],
        ))
        self.product.refresh_from_db()
        return response

    def test_year_edit_updates_name_descriptions_specs_notes_and_auto_seo(self):
        original_identity = (self.product.pk, self.product.sku, self.product.internal_sku, self.product.slug)
        with patch("catalog.signals.invalidate_groups") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                self.save({0: {"year_to": 2020}})
            self.assertTrue(invalidate.called)
        self.fitment.refresh_from_db()
        self.assertEqual(self.fitment.year_to, 2020)
        self.assertEqual(self.fitment.notes, "XV 2017-2020")
        self.assertTrue(self.product.preserve_manual_fitment_content)
        self.assertTrue(self.product.preserve_manual_name)
        self.assertFalse(self.product.preserve_manual_oem)
        self.assertEqual(self.product.name, "Lamp Subaru XV 2017-2020 (RH)")
        for value in (self.product.short_description, self.product.description, self.product.seo_description):
            self.assertIn("2017-2020", value)
            self.assertNotIn("2023", value)
        self.assertIn("2017-2020", self.product.effective_seo_title)
        specs = dict(self.product.specs.values_list("key", "value"))
        self.assertEqual(specs["თაობა"], "XV 2017-2020")
        self.assertEqual(specs["მანქანა"], "Subaru XV")
        self.assertEqual(specs["OEM"], "OEM-15")
        self.assertEqual(original_identity, (self.product.pk, self.product.sku, self.product.internal_sku, self.product.slug))
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="preserve_manual_fitment_content"')

    def test_unrelated_save_does_not_protect_or_regenerate(self):
        self.save(name="A nicer product name")
        self.assertFalse(self.product.preserve_manual_fitment_content)
        self.assertEqual(self.product.short_description, "Old short 2017-2023")
        self.assertEqual(self.product.specs.get(key="თაობა").value, "XV 17-23")

    def test_blank_extra_inline_does_not_enable_protection(self):
        data = self.data()
        data["fitments-TOTAL_FORMS"] = "2"
        for field in ("id", "vehicle_model", "engine", "year_from", "year_to", "notes"):
            data[f"fitments-1-{field}"] = ""
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.preserve_manual_fitment_content)

    def test_stale_generation_notes_are_aligned_without_losing_chassis_and_engine_text(self):
        self.fitment.notes = "XV W212 12-16, 2.0 only"
        self.fitment.save()
        self.save({0: {"year_to": 2020}})
        self.fitment.refresh_from_db()
        self.assertEqual(self.fitment.notes, "XV W212 2017-2020, 2.0 only")
        self.assertEqual(self.product.specs.get(key="თაობა").value, self.fitment.notes)

    def test_deleting_one_range_keeps_other_models_and_ranges(self):
        second = ProductFitment.objects.create(product=self.product, vehicle_model=self.model,
                                              year_from=2025, year_to=2026, notes="XV 25-26")
        self.save({0: {"DELETE": "on"}})
        self.assertEqual(list(self.product.fitments.values_list("pk", flat=True)), [second.pk])
        self.assertNotIn("2017", self.product.description)
        self.assertIn("2025-2026", self.product.description)

    def test_overlong_generated_notes_are_rejected_before_writing(self):
        self.fitment.notes = "A" * 248 + " 17-23"
        self.fitment.save()
        response = self.client.post(self.url, self.data({0: {"year_to": 2020}}))
        self.assertEqual(response.status_code, 200)
        self.fitment.refresh_from_db()
        self.assertEqual(self.fitment.year_to, 2023)
        self.assertEqual(self.fitment.notes, "A" * 248 + " 17-23")

    def test_one_products_correction_does_not_change_another_product(self):
        other = Product.objects.create(category=self.category, name="Another lamp", sku="CM-OTHER",
                                       slug="another-fitment-lamp", price=10)
        other_fitment = ProductFitment.objects.create(product=other, vehicle_model=self.model,
                                                    year_from=2017, year_to=2023, notes="XV 17-23")
        self.save({0: {"year_to": 2020}})
        other_fitment.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((other_fitment.year_to, other_fitment.notes), (2023, "XV 17-23"))
        self.assertFalse(other.preserve_manual_fitment_content)

    def test_repeated_save_is_idempotent_and_cannot_clear_protection(self):
        self.save({0: {"year_to": 2020}})
        before = (self.product.name, self.product.short_description, self.product.description,
                  self.product.seo_description, list(self.product.specs.values_list("key", "value")))
        self.save(preserve_manual_fitment_content="")
        after = (self.product.name, self.product.short_description, self.product.description,
                 self.product.seo_description, list(self.product.specs.values_list("key", "value")))
        self.assertEqual(before, after)
        self.assertTrue(self.product.preserve_manual_fitment_content)

    def test_both_importers_preserve_corrections_while_refreshing_price_stock(self):
        self.save({0: {"year_to": 2020}})
        before = (self.product.name, self.product.short_description, self.product.description,
                  self.product.seo_description, list(self.product.specs.values_list("key", "value")),
                  list(self.product.fitments.values_list("pk", "year_from", "year_to", "notes")))
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            item = feed_item(qty=18)
            item.update(name="Supplier lamp 2017-2023", generation="XV 17-23", dealer_price=110)
            importer(build_crossmotors_report([item]))
            self.product.refresh_from_db()
            self.assertEqual(self.product.supplier_price, Decimal("110"))
            self.assertEqual(self.product.price, Decimal("132"))
            self.assertEqual(self.product.markup_percent_override, Decimal("20"))
            self.assertEqual(self.product.stock_qty, 18)
            after = (self.product.name, self.product.short_description, self.product.description,
                     self.product.seo_description, list(self.product.specs.values_list("key", "value")),
                     list(self.product.fitments.values_list("pk", "year_from", "year_to", "notes")))
            self.assertEqual(before, after)

    def test_public_filters_search_and_year_options_follow_the_new_range(self):
        self.save({0: {"year_to": 2020}})
        for year, expected in ((2017, 1), (2020, 1), (2021, 0), (2023, 0)):
            response = self.client.get(reverse("catalog-product-list"), {"make": "subaru", "model": "xv", "year": year})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], expected)
            for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
                response = self.client.get(reverse(endpoint), {"q": f"Subaru XV {year} Lamp"})
                rows = response.data["results"] if endpoint == "catalog-product-list" else response.data
                self.assertEqual(len(rows), expected)
        response = self.client.get(reverse("catalog-vehicle-year-list"), {"make": "subaru", "model": "xv"})
        self.assertEqual(response.data, [{"year": year} for year in range(2017, 2021)])
        response = self.client.get(reverse("catalog-product-detail", args=[self.product.public_slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fitments"][0]["year_to"], 2020)
        self.assertNotIn("2023", response.data["description"])

    def test_all_ranges_and_models_are_rendered_without_filling_year_gaps(self):
        second = ProductFitment.objects.create(product=self.product, vehicle_model=self.model,
                                              year_from=2022, year_to=2024, notes="XV 22-24")
        model = VehicleModel.objects.create(make=self.make, name="Forester", slug="forester")
        third = ProductFitment.objects.create(product=self.product, vehicle_model=model,
                                             year_from=2014, year_to=2016, notes="Forester 14-16")
        # Model ordering puts Forester first; correct the XV row, not the first row.
        rows = list(self.product.fitments.values_list("pk", flat=True))
        self.save({rows.index(self.fitment.pk): {"year_to": 2020}})
        for value in (self.product.description, self.product.short_description):
            for expected in ("Subaru XV - 2017-2020", "Subaru XV - 2022-2024", "Subaru Forester - 2014-2016"):
                self.assertIn(expected, value)
            self.assertNotIn("2017-2024", value)
        self.assertIn("XV 2017-2020", self.product.specs.get(key="თაობა").value)
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual((second.year_from, second.year_to, second.notes), (2022, 2024, "XV 22-24"))
        self.assertEqual((third.year_from, third.year_to), (2014, 2016))

    def test_shared_old_range_is_removed_from_name_when_models_diverge(self):
        model = VehicleModel.objects.create(make=self.make, name="Forester", slug="forester")
        ProductFitment.objects.create(product=self.product, vehicle_model=model,
                                      year_from=2017, year_to=2023, notes="Forester 17-23")
        rows = list(self.product.fitments.values_list("pk", flat=True))
        self.save({rows.index(self.fitment.pk): {"year_to": 2020}})
        self.assertNotIn("2017", self.product.name)
        self.assertIn("Subaru XV - 2017-2020", self.product.description)
        self.assertIn("Subaru Forester - 2017-2023", self.product.description)

    def test_engines_keep_their_own_year_ranges(self):
        engine = VehicleEngine.objects.create(model=self.model, name="2.0", slug="2-0")
        second = ProductFitment.objects.create(product=self.product, vehicle_model=self.model, engine=engine,
                                              year_from=2017, year_to=2023, notes="2.0 only 17-23")
        rows = list(self.product.fitments.values_list("pk", flat=True))
        self.save({rows.index(second.pk): {"year_to": 2020}})
        self.assertIn("2017-2020 (2.0)", self.product.description)
        self.assertIn("2017-2023", self.product.description)

    def test_deleting_all_fitments_removes_generated_year_content_and_stays_protected(self):
        self.save({0: {"DELETE": "on"}})
        self.assertFalse(self.product.fitments.exists())
        self.assertTrue(self.product.preserve_manual_fitment_content)
        for value in (self.product.name, self.product.description, self.product.short_description, self.product.seo_description):
            self.assertNotIn("2017", value)
            self.assertNotIn("2023", value)
        self.assertFalse(self.product.specs.filter(key__in=["თაობა", "მანქანა"]).exists())
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            importer(build_crossmotors_report([feed_item()]))
            self.assertFalse(self.product.fitments.exists())

    def test_adding_a_fitment_generates_notes_and_protects(self):
        self.save({1: {"vehicle_model": self.model.pk, "year_from": 2025, "year_to": 2026}})
        fitment = self.product.fitments.get(year_from=2025)
        self.assertIn("2025-2026", fitment.notes)
        self.assertTrue(self.product.preserve_manual_fitment_content)
        self.assertIn("2025-2026", self.product.description)

    def test_open_ended_supplier_range_can_be_corrected_without_guessing(self):
        self.product.name = "XV lamp 18-"
        self.product.save(update_fields=["name"])
        self.fitment.year_from = self.fitment.year_to = 2018
        self.fitment.notes = "XV 18-"
        self.fitment.save()
        self.save({0: {"year_to": 2024}})
        self.assertEqual(self.product.name, "XV lamp 2018-2024")
        self.assertEqual(self.product.fitments.get().notes, "XV 2018-2024")

    def test_invalid_ranges_duplicate_rows_and_oem_conflicts_roll_back_all_changes(self):
        for edits, extra in (
            ({0: {"year_to": 2010}}, {}),
            ({1: {"vehicle_model": self.model.pk, "year_from": 2017, "year_to": 2023}}, {}),
            ({0: {"year_to": 2020}}, {"manufacturer_part_number": "TOP", "specs-0-value": "INLINE"}),
        ):
            with self.subTest(edits=edits, extra=extra):
                response = self.client.post(self.url, self.data(edits, **extra))
                self.assertEqual(response.status_code, 200)
                self.product.refresh_from_db()
                self.fitment.refresh_from_db()
                self.assertFalse(self.product.preserve_manual_fitment_content)
                self.assertEqual(self.fitment.year_to, 2023)
                self.assertEqual(self.product.description, "Old description 2017-2023")

    def test_overlong_generated_name_is_an_inline_validation_error(self):
        self.product.name = "A" * 247 + " 17-23"
        self.product.save(update_fields=["name"])
        response = self.client.post(self.url, self.data({0: {"year_to": 2020}}))
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.preserve_manual_fitment_content)
        self.assertTrue(self.product.name.endswith("17-23"))

    def test_explicit_manual_seo_title_survives_and_clearing_restores_auto(self):
        self.product.seo_title = "My explicit title"
        self.product.save(update_fields=["seo_title"])
        self.save({0: {"year_to": 2020}})
        self.assertEqual(self.product.effective_seo_title, "My explicit title")
        self.save(seo_title="")
        self.assertIn("2017-2020", self.product.effective_seo_title)

    def test_stale_unrelated_save_retains_new_protection(self):
        product_admin = admin.site.get_model_admin(Product)
        stale = Product.objects.get(pk=self.product.pk)
        request = RequestFactory().post("/")
        request.user = self.user
        form = product_admin.get_form(request, stale)(data=self.data(), instance=stale)
        self.assertTrue(form.is_valid(), form.errors)
        Product.objects.filter(pk=stale.pk).update(preserve_manual_fitment_content=True)
        product_admin.save_model(request, form.save(commit=False), form, True)
        self.product.refresh_from_db()
        self.assertTrue(self.product.preserve_manual_fitment_content)

    def test_draft_can_correct_years_allocate_sku_and_publish_in_one_save(self):
        self.category.sku_sequence = SkuSequence.objects.get(pk="01")
        self.category.save(update_fields=["sku_sequence"])
        Product.objects.filter(pk=self.product.pk).update(status="draft", internal_sku=None)
        self.save({0: {"year_to": 2020}}, _publish="1")
        self.assertEqual(self.product.status, "published")
        self.assertTrue(self.product.internal_sku.startswith("FD-01-"))
        self.assertTrue(self.product.preserve_manual_fitment_content)
        self.assertIn("2017-2020", self.product.description)

    def test_archived_year_correction_keeps_archive_status_and_supplier_marker(self):
        Product.objects.filter(pk=self.product.pk).update(status="archived", supplier_missing=True)
        self.save({0: {"year_to": 2020}})
        self.assertEqual(self.product.status, "archived")
        self.assertTrue(self.product.supplier_missing)
        self.assertIn("2017-2020", self.product.description)

    def test_aggregate_generation_spec_limit_is_checked_before_any_writes(self):
        self.fitment.notes = "A" * 240 + " 17-23"
        self.fitment.save()
        ProductFitment.objects.create(product=self.product, vehicle_model=self.model,
                                      year_from=2025, year_to=2026, notes="B" * 249 + " 25-26")
        response = self.client.post(self.url, self.data({0: {"year_to": 2020}}))
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.fitment.refresh_from_db()
        self.assertFalse(self.product.preserve_manual_fitment_content)
        self.assertEqual(self.fitment.year_to, 2023)
