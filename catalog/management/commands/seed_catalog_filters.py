import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Brand,
    Product,
    ProductFitment,
    ProductPlacement,
    ProductSide,
    ProductStatus,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)


BRAND_DATA = (
    ("TYC", "tyc", 10),
    ("DEPO", "depo", 20),
    ("Eagle Eyes", "eagle-eyes", 30),
    ("Sakura Filter", "sakura-filter", 40),
    ("GMB", "gmb", 50),
    ("CTR", "ctr", 60),
    ("RoadMax Taiwan", "roadmax-taiwan", 70),
    ("DriveTech", "drivetech", 80),
    ("PartsPro", "partspro", 90),
    ("FlexDrive Select", "flexdrive-select", 100),
)

VEHICLE_DATA = (
    (
        "Toyota",
        "toyota",
        10,
        (
            ("Corolla", "corolla", 10, 2008, 2024, (("1.6 Petrol", "16-petrol"), ("1.8 Hybrid", "18-hybrid"))),
            ("Camry", "camry", 20, 2012, 2024, (("2.5 Petrol", "25-petrol"), ("2.5 Hybrid", "25-hybrid"))),
            ("Prius", "prius", 30, 2010, 2022, (("1.8 Hybrid", "18-hybrid"),)),
            ("RAV4", "rav4", 40, 2013, 2024, (("2.0 Petrol", "20-petrol"), ("2.5 Hybrid", "25-hybrid"))),
        ),
    ),
    (
        "Honda",
        "honda",
        20,
        (
            ("Fit", "fit", 10, 2008, 2020, (("1.3 Petrol", "13-petrol"), ("1.5 Petrol", "15-petrol"))),
            ("Civic", "civic", 20, 2010, 2024, (("1.5 Turbo", "15-turbo"), ("1.8 Petrol", "18-petrol"))),
            ("CR-V", "cr-v", 30, 2012, 2024, (("2.0 Petrol", "20-petrol"), ("2.4 Petrol", "24-petrol"))),
        ),
    ),
    (
        "Nissan",
        "nissan",
        30,
        (
            ("Tiida", "tiida", 10, 2007, 2018, (("1.5 Petrol", "15-petrol"), ("1.8 Petrol", "18-petrol"))),
            ("X-Trail", "x-trail", 20, 2010, 2024, (("2.0 Petrol", "20-petrol"), ("2.5 Petrol", "25-petrol"))),
            ("Juke", "juke", 30, 2011, 2022, (("1.6 Petrol", "16-petrol"), ("1.6 Turbo", "16-turbo"))),
        ),
    ),
    (
        "Hyundai",
        "hyundai",
        40,
        (
            ("Elantra", "elantra", 10, 2011, 2024, (("1.6 Petrol", "16-petrol"), ("2.0 Petrol", "20-petrol"))),
            ("Tucson", "tucson", 20, 2010, 2024, (("2.0 Petrol", "20-petrol"), ("2.0 Diesel", "20-diesel"))),
            ("Sonata", "sonata", 30, 2011, 2023, (("2.0 Petrol", "20-petrol"), ("2.4 Petrol", "24-petrol"))),
        ),
    ),
    (
        "Kia",
        "kia",
        50,
        (
            ("Sportage", "sportage", 10, 2010, 2024, (("2.0 Petrol", "20-petrol"), ("2.0 Diesel", "20-diesel"))),
            ("Rio", "rio", 20, 2011, 2022, (("1.4 Petrol", "14-petrol"), ("1.6 Petrol", "16-petrol"))),
            ("Sorento", "sorento", 30, 2012, 2024, (("2.4 Petrol", "24-petrol"), ("2.2 Diesel", "22-diesel"))),
        ),
    ),
    (
        "Mercedes-Benz",
        "mercedes-benz",
        60,
        (
            ("C-Class", "c-class", 10, 2010, 2024, (("1.8 Petrol", "18-petrol"), ("2.0 Petrol", "20-petrol"))),
            ("E-Class", "e-class", 20, 2010, 2024, (("2.0 Petrol", "20-petrol"), ("2.2 Diesel", "22-diesel"))),
        ),
    ),
    (
        "BMW",
        "bmw",
        70,
        (
            ("3 Series", "3-series", 10, 2010, 2024, (("2.0 Petrol", "20-petrol"), ("2.0 Diesel", "20-diesel"))),
            ("X5", "x5", 20, 2011, 2024, (("3.0 Petrol", "30-petrol"), ("3.0 Diesel", "30-diesel"))),
        ),
    ),
    (
        "Volkswagen",
        "volkswagen",
        80,
        (
            ("Golf", "golf", 10, 2009, 2024, (("1.4 TSI", "14-tsi"), ("2.0 TDI", "20-tdi"))),
            ("Jetta", "jetta", 20, 2010, 2022, (("1.4 TSI", "14-tsi"), ("1.6 Petrol", "16-petrol"))),
        ),
    ),
)

FITMENT_NOTE_PREFIX = "Seeded catalog filter demo"

PRODUCT_BLUEPRINTS = {
    "filters": ("ჰაერის ფილტრი", "ზეთის ფილტრი", "სალონის ფილტრი", "საწვავის ფილტრი"),
    "brake-system": ("სამუხრუჭე ხუნდები", "სამუხრუჭე დისკი", "ABS სენსორი", "სამუხრუჭე ცილინდრი"),
    "suspension": ("ამორტიზატორი", "სტაბილიზატორის დგარი", "ბურთულა საყრდენი", "საჭის ღერო"),
    "engine-parts": ("ძრავის ბალიში", "გენერატორის ღვედი", "თერმოსტატი", "ანთების კოჭა"),
    "cooling-system": ("რადიატორი", "წყლის ტუმბო", "გაგრილების მილი", "ვენტილატორის რელე"),
    "electrical": ("გენერატორი", "სტარტერი", "აკუმულატორის კლემა", "ანთების კოჭა"),
    "lighting": ("წინა ფარი", "უკანა ფარი", "ნისლის ფარი", "LED ნათურა"),
    "body-parts": ("ბამპერის სამაგრი", "კაპოტის საკეტი", "სარკის კორპუსი", "კარის სახელური"),
    "oils-fluids": ("ძრავის ზეთი", "ანტიფრიზი", "სამუხრუჭე სითხე", "გადაცემათა კოლოფის ზეთი"),
    "interior-parts": ("სალონის ხალიჩები", "საბარგულის საფენი", "კლიმატის პანელის ღილაკი", "სავარძლის საფარი"),
    "interior": ("სალონის ფილტრი", "სალონის ხალიჩები", "საბარგულის საფენი", "სავარძლის საფარი"),
    "exterior": ("წინა ფარი", "უკანა ფარი", "ბამპერის სამაგრი", "სარკის კორპუსი"),
    "electronics": ("ABS სენსორი", "გენერატორი", "სტარტერი", "ანთების კოჭა"),
    "comfort": ("სალონის ხალიჩები", "საბარგულის საფენი", "სავარძლის საფარი", "კლიმატის პანელის ღილაკი"),
    "safety": ("სამუხრუჭე ხუნდები", "სამუხრუჭე დისკი", "ABS სენსორი", "ნისლის ფარი"),
}
FALLBACK_PRODUCT_NAMES = (
    "ჰაერის ფილტრი",
    "სამუხრუჭე ხუნდები",
    "ამორტიზატორი",
    "თერმოსტატი",
    "წინა ფარი",
    "რადიატორი",
)


class Command(BaseCommand):
    help = "Seed realistic brands, vehicle selector data and product fitments for catalog filter development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--product-limit",
            type=int,
            default=0,
            help="Number of published products to enrich. 0 means all published products.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20260506,
            help="Random seed for stable demo assignments (default: 20260506).",
        )
        parser.add_argument(
            "--reset-fitments",
            action="store_true",
            help="Delete previously seeded demo fitments before creating new ones.",
        )

    def handle(self, *args, **options):
        product_limit = options["product_limit"]
        seed = options["seed"]
        reset_fitments = options["reset_fitments"]

        if product_limit < 0:
            raise CommandError("--product-limit must be greater than or equal to 0.")

        rng = random.Random(seed)

        with transaction.atomic():
            brands = self._ensure_brands()
            models, engines_by_model_id, year_ranges_by_model_id = self._ensure_vehicles()
            products = self._published_products(product_limit)

            if not products:
                raise CommandError(
                    "No published products found. Run seed_staging_demo or seed_catalog first."
                )

            if reset_fitments:
                deleted_count, _deleted_by_model = ProductFitment.objects.filter(
                    notes__startswith=FITMENT_NOTE_PREFIX
                ).delete()
            else:
                deleted_count = 0

            assignments = self._build_product_assignments(
                products=products,
                models=models,
                engines_by_model_id=engines_by_model_id,
                year_ranges_by_model_id=year_ranges_by_model_id,
            )
            updated_products = self._enrich_products(
                products=products,
                brands=brands,
                assignments=assignments,
                rng=rng,
            )
            created_fitments, updated_fitments = self._seed_fitments(
                products=products,
                assignments=assignments,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog filter seed completed. "
                f"Brands: {len(brands)}. Vehicle models: {len(models)}. "
                f"Products enriched: {updated_products}. "
                f"Fitments created: {created_fitments}, updated: {updated_fitments}. "
                f"Seeded fitments deleted first: {deleted_count}."
            )
        )

    def _ensure_brands(self):
        now = timezone.now()
        Brand.objects.bulk_create(
            [
                Brand(
                    name=name,
                    slug=slug,
                    sort_order=sort_order,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                for name, slug, sort_order in BRAND_DATA
            ],
            update_conflicts=True,
            unique_fields=["slug"],
            update_fields=["name", "sort_order", "is_active", "updated_at"],
        )
        brand_slugs = [slug for _name, slug, _sort_order in BRAND_DATA]
        brands_by_slug = Brand.objects.in_bulk(brand_slugs, field_name="slug")
        return [brands_by_slug[slug] for slug in brand_slugs]

    def _ensure_vehicles(self):
        now = timezone.now()
        VehicleMake.objects.bulk_create(
            [
                VehicleMake(
                    name=name,
                    slug=slug,
                    sort_order=sort_order,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                for name, slug, sort_order, _models in VEHICLE_DATA
            ],
            update_conflicts=True,
            unique_fields=["slug"],
            update_fields=["name", "sort_order", "is_active", "updated_at"],
        )

        make_slugs = [slug for _name, slug, _sort_order, _models in VEHICLE_DATA]
        makes_by_slug = VehicleMake.objects.in_bulk(make_slugs, field_name="slug")

        model_rows = []
        for _make_name, make_slug, _make_sort_order, model_data in VEHICLE_DATA:
            make = makes_by_slug[make_slug]
            for name, slug, sort_order, _year_from, _year_to, _engines in model_data:
                model_rows.append(
                    VehicleModel(
                        make=make,
                        name=name,
                        slug=slug,
                        sort_order=sort_order,
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )

        VehicleModel.objects.bulk_create(
            model_rows,
            update_conflicts=True,
            unique_fields=["make", "slug"],
            update_fields=["name", "sort_order", "is_active", "updated_at"],
        )

        models = list(
            VehicleModel.objects.filter(
                make__slug__in=make_slugs,
                slug__in=[row.slug for row in model_rows],
            )
            .select_related("make")
            .order_by("make__sort_order", "sort_order")
        )
        models_by_make_and_slug = {
            (model.make.slug, model.slug): model
            for model in models
        }

        engine_rows = []
        year_ranges_by_model_id = {}
        for _make_name, make_slug, _make_sort_order, model_data in VEHICLE_DATA:
            for _name, model_slug, _sort_order, year_from, year_to, engine_data in model_data:
                model = models_by_make_and_slug[(make_slug, model_slug)]
                year_ranges_by_model_id[model.id] = (year_from, year_to)
                for index, (engine_name, engine_slug) in enumerate(engine_data, start=1):
                    engine_rows.append(
                        VehicleEngine(
                            model=model,
                            name=engine_name,
                            slug=engine_slug,
                            sort_order=index * 10,
                            is_active=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )

        VehicleEngine.objects.bulk_create(
            engine_rows,
            update_conflicts=True,
            unique_fields=["model", "slug"],
            update_fields=["name", "sort_order", "is_active", "updated_at"],
        )

        engines = VehicleEngine.objects.filter(
            model_id__in=[model.id for model in models]
        ).order_by("model_id", "sort_order")
        engines_by_model_id = {}
        for engine in engines:
            engines_by_model_id.setdefault(engine.model_id, []).append(engine)

        return models, engines_by_model_id, year_ranges_by_model_id

    @staticmethod
    def _published_products(product_limit):
        queryset = (
            Product.objects
            .filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category")
            .order_by("id")
        )
        if product_limit:
            queryset = queryset[:product_limit]
        return list(queryset)

    @staticmethod
    def _build_product_assignments(
        products,
        models,
        engines_by_model_id,
        year_ranges_by_model_id,
    ):
        assignments = {}

        for index, product in enumerate(products, start=1):
            model = models[(index - 1) % len(models)]
            engines = engines_by_model_id.get(model.id, [])
            engine = None
            if engines and index % 2 == 0:
                engine = engines[(index // 2) % len(engines)]

            year_from, year_to = year_ranges_by_model_id[model.id]
            assignments[product.id] = {
                "model": model,
                "engine": engine,
                "year_from": year_from,
                "year_to": year_to,
            }

        return assignments

    @staticmethod
    def _enrich_products(products, brands, assignments, rng):
        now = timezone.now()
        placements = [
            ProductPlacement.FRONT,
            ProductPlacement.REAR,
            ProductPlacement.UPPER,
            ProductPlacement.LOWER,
            ProductPlacement.INNER,
            ProductPlacement.OUTER,
        ]
        sides = [
            ProductSide.LEFT,
            ProductSide.RIGHT,
            ProductSide.BOTH,
            ProductSide.CENTER,
        ]

        for index, product in enumerate(products, start=1):
            brand = brands[(index - 1) % len(brands)]
            assignment = assignments[product.id]
            model = assignment["model"]
            engine = assignment["engine"]
            year_from = assignment["year_from"]
            year_to = assignment["year_to"]
            part_name = Command._part_name_for(product.category.slug, index)
            is_universal = index % 19 == 0
            compatibility_label = (
                "ყველა მოდელისთვის"
                if is_universal
                else f"{model.make.name} {model.name} {year_from}-{year_to}"
            )
            engine_label = f", ძრავი: {engine.name}" if engine else ""

            product.brand = brand
            product.name = (
                f"უნივერსალური {part_name}"
                if is_universal
                else f"{part_name} {model.make.name} {model.name}"
            )
            product.manufacturer_part_number = f"{brand.slug.replace('-', '').upper()}-{index:05d}"
            product.short_description = (
                f"{brand.name} ანალოგი. თავსებადობა: {compatibility_label}{engine_label}."
            )
            product.description = (
                f"{product.name} არის development demo ავტონაწილი FlexDrive-ის "
                f"catalog filter flow-ის შესამოწმებლად. ბრენდი: {brand.name}. "
                f"თავსებადობა: {compatibility_label}{engine_label}. "
                "მონაცემი generated არის და რეალურ მარაგს არ წარმოადგენს."
            )
            product.seo_title = f"{product.name} | FlexDrive"
            product.seo_description = product.short_description
            product.placement = placements[(index - 1) % len(placements)]
            product.side = sides[(index + rng.randint(0, len(sides) - 1)) % len(sides)]
            product.is_universal_fitment = is_universal
            product.updated_at = now

        Product.objects.bulk_update(
            products,
            [
                "brand",
                "name",
                "manufacturer_part_number",
                "short_description",
                "description",
                "seo_title",
                "seo_description",
                "placement",
                "side",
                "is_universal_fitment",
                "updated_at",
            ],
        )
        return len(products)

    @staticmethod
    def _part_name_for(category_slug, index):
        names = PRODUCT_BLUEPRINTS.get(category_slug) or FALLBACK_PRODUCT_NAMES
        return names[(index - 1) % len(names)]

    def _seed_fitments(
        self,
        products,
        assignments,
    ):
        created_count = 0
        updated_count = 0

        for product in products:
            if product.is_universal_fitment:
                continue

            assignment = assignments[product.id]
            model = assignment["model"]
            engine = assignment["engine"]
            year_from = assignment["year_from"]
            year_to = assignment["year_to"]

            _fitment, created = ProductFitment.objects.update_or_create(
                product=product,
                vehicle_model=model,
                engine=engine,
                year_from=year_from,
                year_to=year_to,
                defaults={
                    "notes": (
                        f"{FITMENT_NOTE_PREFIX}: primary "
                        f"{model.make.name} {model.name} {year_from}-{year_to}"
                    )
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        return created_count, updated_count
