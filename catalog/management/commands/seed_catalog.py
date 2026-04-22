import random
import uuid
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from PIL import Image, ImageDraw

from catalog.models import Category, Product, ProductImage, ProductSpec, ProductStatus


CATEGORY_SEED_DATA = (
    ("Interior", "interior"),
    ("Exterior", "exterior"),
    ("Electronics", "electronics"),
    ("Comfort", "comfort"),
    ("Safety", "safety"),
)

PRODUCT_NAME_POOL = (
    "Car Phone Holder",
    "Dash Cam",
    "Seat Organizer",
    "Fast Charger",
    "Air Freshener",
    "Floor Mats",
    "Steering Cover",
    "Trunk Organizer",
    "Mirror Camera",
    "LED Light Kit",
    "Jump Starter",
    "Tire Inflator",
    "Car Vacuum",
    "Sun Shade",
    "Car Bluetooth Adapter",
)

SPEC_VALUE_POOL = {
    "Material": ("ABS", "Aluminum", "Silicone", "TPU", "Leather"),
    "Color": ("Black", "Gray", "Silver", "Red", "Blue"),
    "Voltage": ("5V", "12V", "24V"),
    "Power": ("18W", "30W", "45W", "65W"),
    "Mount Type": ("Magnetic", "Clip", "Suction", "Hook"),
    "Water Resistance": ("IPX4", "IPX5", "IPX6", "IP67"),
    "Compatibility": ("Universal", "Most Cars", "SUV", "Sedan"),
    "Warranty": ("6 months", "12 months", "24 months"),
    "Weight": ("120g", "220g", "340g", "450g"),
    "Package": ("1 piece", "2 pieces", "Full set"),
}


class Command(BaseCommand):
    help = "Generate fake catalog products, specs and optional images for development/testing."

    fake_sku_prefix = "FAKE-"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=30,
            help="Number of fake products to create (default: 30).",
        )
        parser.add_argument(
            "--with-images",
            action="store_true",
            help="Attach generated placeholder images to fake products.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously generated fake products before seeding.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for repeatable generation (default: 42).",
        )

    def handle(self, *args, **options):
        count = options["count"]
        with_images = options["with_images"]
        reset = options["reset"]
        seed = options["seed"]

        if count < 0:
            raise CommandError("--count must be greater than or equal to 0.")

        rng = random.Random(seed)

        if reset:
            deleted_products = Product.objects.filter(sku__startswith=self.fake_sku_prefix).count()
            Product.objects.filter(sku__startswith=self.fake_sku_prefix).delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted_products} fake product(s) with prefix '{self.fake_sku_prefix}'.")
            )

        categories = self._ensure_categories()
        created_products = 0
        created_images = 0
        created_specs = 0

        for i in range(count):
            category = rng.choice(categories)
            base_name = rng.choice(PRODUCT_NAME_POOL)
            name = f"{base_name} {i + 1}"
            slug = self._build_unique_slug(name)
            sku = self._build_unique_sku()

            price = self._random_price(rng)
            old_price = None
            if rng.random() < 0.4:
                old_price = price + self._random_discount_delta(rng)

            product = Product.objects.create(
                category=category,
                name=name,
                slug=slug,
                sku=sku,
                short_description=f"{base_name} for everyday driving.",
                description=(
                    f"{name} is a seeded demo product. "
                    "This content is generated for frontend/backend integration testing."
                ),
                price=price,
                old_price=old_price,
                stock_qty=rng.randint(0, 40),
                is_new=rng.random() < 0.25,
                is_featured=rng.random() < 0.2,
                status=ProductStatus.PUBLISHED,
            )
            created_products += 1

            created_specs += self._create_product_specs(product, rng)

            if with_images:
                created_images += self._create_product_images(product, rng)

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog seed completed. "
                f"Created products: {created_products}, specs: {created_specs}, images: {created_images}."
            )
        )

    def _ensure_categories(self):
        categories = []
        for index, (name, slug) in enumerate(CATEGORY_SEED_DATA, start=1):
            category, created = Category.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "sort_order": index, "is_active": True},
            )
            if not created:
                changed = False
                if category.name != name:
                    category.name = name
                    changed = True
                if category.sort_order != index:
                    category.sort_order = index
                    changed = True
                if not category.is_active:
                    category.is_active = True
                    changed = True
                if changed:
                    category.save()
            categories.append(category)
        return categories

    def _build_unique_slug(self, value):
        base = slugify(value)[:230] or f"product-{uuid.uuid4().hex[:8]}"
        candidate = base
        suffix = 2
        while Product.objects.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _build_unique_sku(self):
        while True:
            candidate = f"{self.fake_sku_prefix}{uuid.uuid4().hex[:10].upper()}"
            if not Product.objects.filter(sku=candidate).exists():
                return candidate

    @staticmethod
    def _random_price(rng):
        return Decimal(rng.randint(1200, 45000)) / Decimal("100")

    @staticmethod
    def _random_discount_delta(rng):
        return Decimal(rng.randint(200, 12000)) / Decimal("100")

    @staticmethod
    def _create_product_specs(product, rng):
        keys = list(SPEC_VALUE_POOL.keys())
        spec_count = rng.randint(4, 6)
        selected_keys = rng.sample(keys, k=spec_count)

        for index, key in enumerate(selected_keys, start=1):
            ProductSpec.objects.create(
                product=product,
                key=key,
                value=rng.choice(SPEC_VALUE_POOL[key]),
                sort_order=index,
            )
        return spec_count

    def _create_product_images(self, product, rng):
        created = 0

        primary = ProductImage(
            product=product,
            alt_text=f"{product.name} main image",
            is_primary=True,
            sort_order=1,
        )
        primary.image_desktop.save(
            f"{product.slug}-desktop.jpg",
            self._build_placeholder_image_file(product.name, "DESKTOP", rng),
            save=False,
        )
        if rng.random() < 0.5:
            primary.image_tablet.save(
                f"{product.slug}-tablet.jpg",
                self._build_placeholder_image_file(product.name, "TABLET", rng),
                save=False,
            )
        if rng.random() < 0.35:
            primary.image_mobile.save(
                f"{product.slug}-mobile.jpg",
                self._build_placeholder_image_file(product.name, "MOBILE", rng),
                save=False,
            )
        primary.save()
        created += 1

        extra_count = rng.randint(0, 2)
        for offset in range(extra_count):
            sort_order = offset + 2
            extra = ProductImage(
                product=product,
                alt_text=f"{product.name} gallery image {sort_order}",
                is_primary=False,
                sort_order=sort_order,
            )
            extra.image_desktop.save(
                f"{product.slug}-gallery-{sort_order}.jpg",
                self._build_placeholder_image_file(product.name, f"GALLERY {sort_order}", rng),
                save=False,
            )
            extra.save()
            created += 1

        return created

    @staticmethod
    def _build_placeholder_image_file(title, label, rng):
        width = 1200
        height = 900
        base_color = (
            rng.randint(20, 80),
            rng.randint(80, 160),
            rng.randint(120, 220),
        )
        image = Image.new("RGB", (width, height), color=base_color)
        draw = ImageDraw.Draw(image)

        draw.rectangle((0, int(height * 0.72), width, height), fill=(18, 20, 26))
        draw.rectangle((50, 60, width - 50, 130), outline=(255, 255, 255), width=2)
        draw.text((70, 80), f"SHOPBACK DEMO - {label}", fill=(255, 255, 255))
        draw.text((70, int(height * 0.78)), title[:42], fill=(255, 255, 255))

        stream = BytesIO()
        image.save(stream, format="JPEG", quality=88)
        stream.seek(0)
        return ContentFile(stream.read())
