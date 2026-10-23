"""Make-list optimization must preserve the existing option eligibility."""
from decimal import Decimal

from django.db import connection
from django.db.models import Q
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory

from .models import (
    Category, Product, ProductFitment, ProductStatus,
    VehicleEngine, VehicleMake, VehicleModel,
)
from .views import VehicleMakeListAPIView


@override_settings(CACHE_ENABLED=False)
class VehicleMakeQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Visible", slug="visible-makes")
        cls.hidden_category = Category.objects.create(
            name="Hidden", slug="hidden-makes", is_active=False,
        )
        cls.expected = set()

        def add_case(slug, *, published=True, category=None, model_active=True,
                     make_active=True, engine_status="generic", extra=None):
            make = VehicleMake.objects.create(
                name=slug, slug=slug, sort_order=2 if slug.startswith("valid") else 1,
                is_active=make_active,
            )
            model = VehicleModel.objects.create(
                make=make, name=slug, slug=slug, is_active=model_active,
            )
            product = Product.objects.create(
                category=category or cls.category, name=slug, slug=slug, sku="PRIVATE-" + slug,
                internal_sku=f"FD-01-{Product.objects.count() + 1:04d}",
                price=Decimal("10.00"), stock_qty=1,
                status=ProductStatus.PUBLISHED if published else ProductStatus.DRAFT,
            )
            engine = None
            if engine_status != "generic":
                engine = VehicleEngine.objects.create(
                    model=model, name=slug, slug=slug,
                    is_active=engine_status == "active",
                )
            ProductFitment.objects.create(
                product=product, vehicle_model=model, engine=engine,
                year_from=2018, year_to=2020,
            )
            if extra == "empty-model":
                VehicleModel.objects.create(make=make, name="Empty", slug=slug + "-empty")
            elif extra == "draft-generic":
                draft = Product.objects.create(
                    category=cls.category, name=slug + " draft", slug=slug + "-draft", sku="PRIVATE-" + slug + "-draft",
                    internal_sku=f"FD-01-{Product.objects.count() + 1:04d}",
                    price=Decimal("10.00"), status=ProductStatus.DRAFT,
                )
                ProductFitment.objects.create(
                    product=draft, vehicle_model=model, year_from=2010, year_to=2010,
                )
            elif extra == "inactive-model":
                inactive = VehicleModel.objects.create(
                    make=make, name="Inactive", slug=slug + "-inactive", is_active=False,
                )
                ProductFitment.objects.create(
                    product=product, vehicle_model=inactive, year_from=2010, year_to=2010,
                )
            return make, model, product

        for slug, kwargs in (
            ("valid-generic", {}),
            ("valid-engine", {"engine_status": "active"}),
            ("independent-empty", {"engine_status": "inactive", "extra": "empty-model"}),
            ("independent-draft", {"engine_status": "inactive", "extra": "draft-generic"}),
            ("independent-inactive-model", {"engine_status": "inactive", "extra": "inactive-model"}),
        ):
            make, _model, _product = add_case(slug, **kwargs)
            cls.expected.add(make.pk)
        for slug, kwargs in (
            ("draft-only", {"published": False}),
            ("hidden-category", {"category": cls.hidden_category}),
            ("inactive-model-only", {"model_active": False}),
            ("inactive-make", {"make_active": False}),
            ("inactive-engine-only", {"engine_status": "inactive"}),
        ):
            add_case(slug, **kwargs)
        VehicleMake.objects.create(name="No models", slug="no-models")
        empty = VehicleMake.objects.create(name="No fitments", slug="no-fitments")
        VehicleModel.objects.create(make=empty, name="Empty", slug="empty")
        cls.many_make, cls.many_model, cls.many_product = add_case("valid-many")
        cls.expected.add(cls.many_make.pk)
        ProductFitment.objects.bulk_create([
            ProductFitment(
                product=cls.many_product, vehicle_model=cls.many_model,
                year_from=year, year_to=year,
            )
            for year in range(1900, 2018)
        ])

    @staticmethod
    def previous_queryset():
        # Independent legacy checks are an intentional compatibility constraint.
        return VehicleMake.objects.filter(
            is_active=True, models__is_active=True,
            models__product_fitments__product__status=ProductStatus.PUBLISHED,
            models__product_fitments__product__category__is_active=True,
        ).filter(
            Q(models__product_fitments__engine__isnull=True)
            | Q(models__product_fitments__engine__is_active=True)
        ).distinct().order_by("sort_order", "name")

    def test_make_options_match_previous_conditions_and_ordering(self):
        previous = list(self.previous_queryset().values_list("pk", flat=True))
        self.assertEqual(set(previous), self.expected)
        current = list(VehicleMakeListAPIView().get_queryset().values_list("pk", flat=True))
        self.assertEqual(current, previous)

    def test_duplicate_fitments_do_not_duplicate_options_or_add_queries(self):
        request = APIRequestFactory().get("/api/catalog/vehicles/makes/")
        with CaptureQueriesContext(connection) as queries:
            response = VehicleMakeListAPIView.as_view()(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data]
        self.assertEqual(set(ids), self.expected)
        self.assertEqual(len(ids), len(self.expected))
        self.assertEqual(len(queries), 1)
        self.assertEqual(set(response.data[0]), {"id", "name", "slug", "sort_order"})

    def test_saved_product_visibility_and_vehicle_changes_are_seen_immediately(self):
        self.many_product.status = ProductStatus.DRAFT
        self.many_product.save(update_fields=["status"])
        self.assertNotIn(self.many_make.pk, VehicleMakeListAPIView().get_queryset().values_list("pk", flat=True))
        self.many_product.status = ProductStatus.PUBLISHED
        self.many_product.save(update_fields=["status"])
        self.assertIn(self.many_make.pk, VehicleMakeListAPIView().get_queryset().values_list("pk", flat=True))
        self.many_model.is_active = False
        self.many_model.save(update_fields=["is_active"])
        self.assertNotIn(self.many_make.pk, VehicleMakeListAPIView().get_queryset().values_list("pk", flat=True))
