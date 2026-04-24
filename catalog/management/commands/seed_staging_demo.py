import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Category, Product, ProductSpec, ProductStatus
from pages.models import Component, ComponentType, Page


FEATURED_TITLE = "გამორჩეული პროდუქტები"
FEATURED_SUBTITLE = "ჩვენი ყველაზე პოპულარული და ხშირად შეძენილი პროდუქცია"
FEATURED_BUTTON_TEXT = "ყველა პროდუქტის ნახვა"
FEATURED_COMPONENT_NAME = "FeaturedProducts"

HOME_COMPONENT_ORDER = {
    "HeroSection": 10,
    "FeaturedProducts": 20,
    "ProblemSolving": 30,
    "OrderConfidence": 40,
    "HowItWorks": 50,
    "BlogSection": 60,
}

CATEGORY_SEED_DATA = (
    ("ფილტრები", "filters", 10),
    ("სამუხრუჭე სისტემა", "brake-system", 20),
    ("სავალი ნაწილი", "suspension", 30),
    ("ძრავის ნაწილები", "engine-parts", 40),
    ("გაგრილების სისტემა", "cooling-system", 50),
    ("ელექტროობა", "electrical", 60),
    ("განათება", "lighting", 70),
    ("კუზაოს ნაწილები", "body-parts", 80),
    ("ზეთები და სითხეები", "oils-fluids", 90),
    ("ინტერიერი", "interior-parts", 100),
)

PRODUCT_BLUEPRINTS = {
    "filters": (
        "ჰაერის ფილტრი",
        "ზეთის ფილტრი",
        "სალონის ფილტრი",
        "საწვავის ფილტრი",
    ),
    "brake-system": (
        "სამუხრუჭე ხუნდები",
        "სამუხრუჭე დისკი",
        "სამუხრუჭე ცილინდრი",
        "ABS სენსორი",
    ),
    "suspension": (
        "ამორტიზატორი",
        "სტაბილიზატორის დგარი",
        "ბურთულა საყრდენი",
        "საჭის ღერო",
    ),
    "engine-parts": (
        "ძრავის ბალიში",
        "გენერატორის ღვედი",
        "სანთლები",
        "თერმოსტატი",
    ),
    "cooling-system": (
        "რადიატორი",
        "წყლის ტუმბო",
        "გაგრილების მილი",
        "ვენტილატორის რელე",
    ),
    "electrical": (
        "აკუმულატორის კლემა",
        "გენერატორი",
        "სტარტერი",
        "ანთების კოჭა",
    ),
    "lighting": (
        "წინა ფარი",
        "უკანა ფარი",
        "ნისლის ფარი",
        "LED ნათურა",
    ),
    "body-parts": (
        "ბამპერის სამაგრი",
        "კაპოტის საკეტი",
        "სარკის კორპუსი",
        "კარის სახელური",
    ),
    "oils-fluids": (
        "ძრავის ზეთი",
        "ანტიფრიზი",
        "სამუხრუჭე სითხე",
        "გადაცემათა კოლოფის ზეთი",
    ),
    "interior-parts": (
        "სალონის ხალიჩები",
        "სავარძლის საფარი",
        "საბარგულის საფენი",
        "კლიმატის პანელის ღილაკი",
    ),
}

VEHICLE_MODELS = (
    "Toyota Corolla",
    "Toyota Prius",
    "Honda Fit",
    "Honda CR-V",
    "Nissan X-Trail",
    "Nissan Tiida",
    "Hyundai Tucson",
    "Hyundai Elantra",
    "Kia Sportage",
    "Mercedes-Benz C-Class",
    "BMW 3 Series",
    "Volkswagen Golf",
)

BRANDS = (
    "FlexDrive Select",
    "Taiwan Premium",
    "RoadMax",
    "AutoLine",
    "DriveTech",
    "PartsPro",
)

CONDITIONS = ("ახალი", "ტაივანური ანალოგი", "პრემიუმ ანალოგი")


class Command(BaseCommand):
    help = "Seed staging demo catalog products and homepage FeaturedProducts component."

    sku_prefix = "FD-STAGE-"

    def add_arguments(self, parser):
        parser.add_argument(
            "--products",
            type=int,
            default=300,
            help="Number of staging demo products to create or update (default: 300).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20260424,
            help="Random seed for stable demo data (default: 20260424).",
        )

    def handle(self, *args, **options):
        product_count = options["products"]
        seed = options["seed"]

        if product_count < 1:
            raise CommandError("--products must be greater than 0.")

        rng = random.Random(seed)
        now = timezone.now()

        with transaction.atomic():
            categories = self._ensure_categories(now)
            created_products, updated_products = self._upsert_products(
                product_count=product_count,
                categories=categories,
                rng=rng,
                now=now,
            )
            created_specs, updated_specs = self._upsert_all_specs(product_count)
            component_created = self._ensure_featured_products_component()

        self.stdout.write(
            self.style.SUCCESS(
                "Staging demo seed completed. "
                f"Products created: {created_products}, updated: {updated_products}. "
                f"Specs created: {created_specs}, updated: {updated_specs}. "
                f"FeaturedProducts component: {'created' if component_created else 'updated'}."
            )
        )

    def _ensure_categories(self, now):
        categories = [
            Category(
                name=name,
                slug=slug,
                sort_order=sort_order,
                is_active=True,
                seo_title=f"{name} | FlexDrive",
                seo_description=(
                    f"დაათვალიერე {name} კატეგორიის ხარისხიანი ავტონაწილები FlexDrive-ზე."
                ),
                created_at=now,
                updated_at=now,
            )
            for name, slug, sort_order in CATEGORY_SEED_DATA
        ]
        Category.objects.bulk_create(
            categories,
            update_conflicts=True,
            unique_fields=["slug"],
            update_fields=[
                "name",
                "sort_order",
                "is_active",
                "seo_title",
                "seo_description",
                "updated_at",
            ],
        )

        category_slugs = [slug for _name, slug, _sort_order in CATEGORY_SEED_DATA]
        categories_by_slug = Category.objects.in_bulk(category_slugs, field_name="slug")
        return [categories_by_slug[slug] for slug in category_slugs]

    def _upsert_products(self, product_count, categories, rng, now):
        skus = [f"{self.sku_prefix}{index:04d}" for index in range(1, product_count + 1)]
        existing_count = Product.objects.filter(sku__in=skus).count()
        products = []
        used_slugs = dict(
            Product.objects
            .filter(slug__startswith="fd-demo-")
            .values_list("slug", "sku")
        )

        for index in range(1, product_count + 1):
            category = categories[(index - 1) % len(categories)]
            products.append(
                self._build_product(
                    index=index,
                    category=category,
                    rng=rng,
                    now=now,
                    used_slugs=used_slugs,
                )
            )

        Product.objects.bulk_create(
            products,
            update_conflicts=True,
            unique_fields=["sku"],
            update_fields=[
                "category",
                "name",
                "slug",
                "seo_title",
                "seo_description",
                "short_description",
                "description",
                "price",
                "old_price",
                "stock_qty",
                "is_new",
                "is_featured",
                "status",
                "updated_at",
            ],
        )

        return product_count - existing_count, existing_count

    def _build_product(self, index, category, rng, now, used_slugs):
        category_products = PRODUCT_BLUEPRINTS.get(category.slug) or PRODUCT_BLUEPRINTS["filters"]
        base_name = category_products[(index - 1) % len(category_products)]
        vehicle = VEHICLE_MODELS[(index - 1) % len(VEHICLE_MODELS)]
        brand = BRANDS[(index - 1) % len(BRANDS)]
        condition = CONDITIONS[(index - 1) % len(CONDITIONS)]
        sku = f"{self.sku_prefix}{index:04d}"
        name = f"{base_name} {vehicle}"
        slug = self._build_stable_slug(index, category.slug, sku, used_slugs)
        price = self._price_for(index, rng)
        on_sale = index % 5 == 0 or index % 11 == 0
        old_price = price + self._discount_delta(index, rng) if on_sale else None
        stock_qty = 0 if index % 17 == 0 else rng.randint(2, 48)
        is_featured = index <= 36 or index % 9 == 0
        is_new = index <= 24 or index % 13 == 0

        short_description = f"{condition} ავტონაწილი {vehicle}-ისთვის."
        description = (
            f"{name} არის staging demo პროდუქტი FlexDrive-ის კატალოგის შესამოწმებლად. "
            f"ბრენდი: {brand}. მდგომარეობა: {condition}. "
            "სურათი შეგნებულად არ არის მიბმული, რომ frontend fallback და admin upload flow შემოწმდეს."
        )

        return Product(
            category=category,
            name=name,
            slug=slug,
            sku=sku,
            seo_title=f"{name} | FlexDrive",
            seo_description=short_description,
            short_description=short_description,
            description=description,
            price=price,
            old_price=old_price,
            stock_qty=stock_qty,
            is_new=is_new,
            is_featured=is_featured,
            status=ProductStatus.PUBLISHED,
            created_at=now,
            updated_at=now,
        )

    def _build_stable_slug(self, index, category_slug, sku, used_slugs):
        base = f"fd-demo-{index:04d}-{category_slug}"
        if used_slugs.get(base) in {None, sku}:
            used_slugs[base] = sku
            return base

        fallback = f"{base}-{sku.lower()}"
        suffix = 2
        candidate = fallback
        while used_slugs.get(candidate) not in {None, sku}:
            candidate = f"{fallback}-{suffix}"
            suffix += 1
        used_slugs[candidate] = sku
        return candidate

    def _upsert_all_specs(self, product_count):
        skus = [f"{self.sku_prefix}{index:04d}" for index in range(1, product_count + 1)]
        product_ids_by_sku = dict(
            Product.objects
            .filter(sku__in=skus)
            .values_list("sku", "id")
        )
        spec_keys = ["ბრენდი", "მდგომარეობა", "თავსებადობა", "კოდი", "გარანტია"]
        existing_count = ProductSpec.objects.filter(
            product_id__in=product_ids_by_sku.values(),
            key__in=spec_keys,
        ).count()
        specs = []

        for index in range(1, product_count + 1):
            sku = f"{self.sku_prefix}{index:04d}"
            product_id = product_ids_by_sku[sku]
            specs.extend(self._build_specs(product_id, sku, index))

        ProductSpec.objects.bulk_create(
            specs,
            update_conflicts=True,
            unique_fields=["product", "key"],
            update_fields=["value", "sort_order", "updated_at"],
        )

        return len(specs) - existing_count, existing_count

    @staticmethod
    def _build_specs(product_id, sku, index):
        now = timezone.now()
        spec_values = (
            ("ბრენდი", BRANDS[(index - 1) % len(BRANDS)], 1),
            ("მდგომარეობა", CONDITIONS[(index - 1) % len(CONDITIONS)], 2),
            ("თავსებადობა", VEHICLE_MODELS[(index - 1) % len(VEHICLE_MODELS)], 3),
            ("კოდი", sku, 4),
            ("გარანტია", f"{6 + (index % 4) * 3} თვე", 5),
        )
        return [
            ProductSpec(
                product_id=product_id,
                key=key,
                value=value,
                sort_order=sort_order,
                created_at=now,
                updated_at=now,
            )
            for key, value, sort_order in spec_values
        ]

    @staticmethod
    def _price_for(index, rng):
        base = Decimal(rng.randint(1800, 95000)) / Decimal("100")
        category_weight = Decimal((index % 7) * 3)
        return (base + category_weight).quantize(Decimal("0.01"))

    @staticmethod
    def _discount_delta(index, rng):
        return (Decimal(rng.randint(500, 22000)) / Decimal("100")).quantize(Decimal("0.01"))

    def _ensure_featured_products_component(self):
        main_page, _page_created = Page.objects.get_or_create(
            slug="main",
            defaults={
                "name": "მთავარი",
                "show_in_menu": True,
                "order": 0,
            },
        )
        component_type, _type_created = ComponentType.objects.get_or_create(
            name=FEATURED_COMPONENT_NAME
        )

        component = (
            Component.objects
            .filter(page=main_page, component_type=component_type)
            .order_by("id")
            .first()
        )
        created = component is None

        if component is None:
            component = Component.objects.create(
                page=main_page,
                component_type=component_type,
                position=HOME_COMPONENT_ORDER[FEATURED_COMPONENT_NAME],
                title=FEATURED_TITLE,
                subtitle=FEATURED_SUBTITLE,
                button_text=FEATURED_BUTTON_TEXT,
                enabled=True,
            )
        else:
            component.title = FEATURED_TITLE
            component.subtitle = FEATURED_SUBTITLE
            component.button_text = FEATURED_BUTTON_TEXT
            component.position = HOME_COMPONENT_ORDER[FEATURED_COMPONENT_NAME]
            component.enabled = True
            component.save(
                update_fields=[
                    "title",
                    "subtitle",
                    "button_text",
                    "position",
                    "enabled",
                    "updated_at",
                ]
            )

        self._update_home_component_positions(main_page)
        return created

    @staticmethod
    def _update_home_component_positions(main_page):
        components = list(
            Component.objects
            .filter(page=main_page)
            .select_related("component_type")
            .order_by("id")
        )
        assigned_ids = set()
        next_position = 10

        for component_name, position in HOME_COMPONENT_ORDER.items():
            matched = next(
                (
                    component for component in components
                    if component.id not in assigned_ids
                    and component.component_type.name == component_name
                ),
                None,
            )
            if matched is None:
                continue

            if matched.position != position:
                Component.objects.filter(pk=matched.pk).update(position=position)
            assigned_ids.add(matched.id)
            next_position = max(next_position, position + 10)

        for component in components:
            if component.id in assigned_ids:
                continue
            Component.objects.filter(pk=component.pk).update(position=next_position)
            next_position += 10
