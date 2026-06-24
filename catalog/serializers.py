from rest_framework import serializers

from .models import (
    Category,
    Product,
    ProductFitment,
    ProductImage,
    ProductPlacement,
    ProductSpec,
    ProductSide,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)


PLACEMENT_LABELS_KA = {
    ProductPlacement.FRONT: "წინა",
    ProductPlacement.REAR: "უკანა",
    ProductPlacement.UPPER: "ზედა",
    ProductPlacement.LOWER: "ქვედა",
    ProductPlacement.INNER: "შიდა",
    ProductPlacement.OUTER: "გარე",
}
SIDE_LABELS_KA = {
    ProductSide.LEFT: "მარცხენა",
    ProductSide.RIGHT: "მარჯვენა",
    ProductSide.BOTH: "ორივე",
    ProductSide.CENTER: "ცენტრი",
}


def _absolute_file_url(request, file_field):
    if not file_field:
        return None
    return request.build_absolute_uri(file_field.url)


def _resolve_category_seo_payload(request, category):
    canonical = category.seo_canonical_url or f"/catalog/category/{category.slug}"
    title = (category.seo_title or "").strip() or f"{category.name} კატეგორია"
    description = (category.seo_description or "").strip() or (
        f"დაათვალიერე {category.name} კატეგორიის ხარისხიანი ავტონაწილები FlexDrive-ზე."
    )

    return {
        "title": title,
        "description": description,
        "image": _absolute_file_url(request, category.seo_image),
        "noindex": bool(category.seo_noindex),
        "canonical": canonical,
    }


def _resolve_product_seo_payload(request, product, primary_image=None):
    title = (product.seo_title or "").strip() or product.name
    description = (
        (product.seo_description or "").strip()
        or (product.short_description or "").strip()
        or (product.description or "").strip()
        or None
    )
    canonical = product.seo_canonical_url or f"/catalog/{product.slug}"
    image = _absolute_file_url(request, product.seo_image)

    if not image and primary_image:
        image = (
            _absolute_file_url(request, primary_image.image_desktop)
            or _absolute_file_url(request, primary_image.image_tablet)
            or _absolute_file_url(request, primary_image.image_mobile)
        )

    return {
        "title": title,
        "description": description,
        "image": image,
        "noindex": bool(product.seo_noindex),
        "canonical": canonical,
    }


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)
    image = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "parent",
            "sort_order",
            "product_count",
            "image",
            "seo",
        )

    def get_image(self, obj):
        request = self.context["request"]
        return {
            "desktop": _absolute_file_url(request, obj.desktop_image),
            "tablet": _absolute_file_url(request, obj.tablet_image),
            "mobile": _absolute_file_url(request, obj.mobile_image),
            "alt_text": (obj.image_alt_text or "").strip() or obj.name,
        }

    def get_seo(self, obj):
        request = self.context["request"]
        return _resolve_category_seo_payload(request, obj)


class VehicleMakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleMake
        fields = ("id", "name", "slug", "sort_order")


class VehicleModelSerializer(serializers.ModelSerializer):
    make = VehicleMakeSerializer(read_only=True)

    class Meta:
        model = VehicleModel
        fields = ("id", "name", "slug", "sort_order", "make")


class VehicleEngineSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleEngine
        fields = ("id", "name", "slug", "sort_order")


class ProductSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpec
        fields = ("key", "value", "sort_order")


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "alt_text", "is_primary", "sort_order", "image")

    def get_image(self, obj):
        request = self.context["request"]
        return {
            "desktop": _absolute_file_url(request, obj.desktop_image),
            "tablet": _absolute_file_url(request, obj.tablet_image),
            "mobile": _absolute_file_url(request, obj.mobile_image),
        }


class ProductFitmentSerializer(serializers.ModelSerializer):
    make = serializers.SerializerMethodField()
    model = serializers.SerializerMethodField()
    engine = serializers.SerializerMethodField()

    class Meta:
        model = ProductFitment
        fields = (
            "id",
            "make",
            "model",
            "engine",
            "year_from",
            "year_to",
            "notes",
        )

    def get_make(self, obj):
        make = obj.vehicle_model.make
        return {"id": make.id, "name": make.name, "slug": make.slug}

    def get_model(self, obj):
        model = obj.vehicle_model
        return {"id": model.id, "name": model.name, "slug": model.slug}

    def get_engine(self, obj):
        if not obj.engine_id:
            return None

        return {"id": obj.engine_id, "name": obj.engine.name, "slug": obj.engine.slug}


class ProductListSerializer(serializers.ModelSerializer):
    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    on_sale = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    price_available = serializers.SerializerMethodField()
    purchasable = serializers.SerializerMethodField()
    placement_label = serializers.SerializerMethodField()
    side_label = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    compatibility = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "manufacturer_part_number",
            "short_description",
            "price",
            "old_price",
            "on_sale",
            "price_available",
            "purchasable",
            "is_new",
            "is_featured",
            "is_universal_fitment",
            "in_stock",
            "brand",
            "category",
            "placement",
            "placement_label",
            "side",
            "side_label",
            "primary_image",
            "compatibility",
            "seo",
        )

    def get_brand(self, obj):
        if not obj.brand_id:
            return None

        return {"id": obj.brand_id, "name": obj.brand.name, "slug": obj.brand.slug}

    def get_category(self, obj):
        return {
            "id": obj.category_id,
            "name": obj.category.name,
            "slug": obj.category.slug,
        }

    def get_on_sale(self, obj):
        return obj.on_sale

    def get_in_stock(self, obj):
        return obj.in_stock

    def get_price_available(self, obj):
        return obj.price_available

    def get_purchasable(self, obj):
        return obj.purchasable

    def get_placement_label(self, obj):
        if not obj.placement:
            return ""
        return PLACEMENT_LABELS_KA.get(obj.placement, obj.get_placement_display())

    def get_side_label(self, obj):
        if not obj.side:
            return ""
        return SIDE_LABELS_KA.get(obj.side, obj.get_side_display())

    def get_primary_image(self, obj):
        primary = self._resolve_primary_image(obj)
        if not primary:
            return {
                "desktop": None,
                "tablet": None,
                "mobile": None,
                "alt_text": "",
            }

        request = self.context["request"]
        return {
            "desktop": _absolute_file_url(request, primary.desktop_image),
            "tablet": _absolute_file_url(request, primary.tablet_image),
            "mobile": _absolute_file_url(request, primary.mobile_image),
            "alt_text": primary.alt_text,
        }

    def get_compatibility(self, obj):
        if not self.context.get("vehicle_filter"):
            return None

        if obj.is_universal_fitment:
            return {
                "matched": True,
                "match_type": "universal",
                "notes": "",
            }

        matching_fitments = getattr(obj, "matching_fitments", None)
        if matching_fitments is None:
            matching_fitments = []

        if not matching_fitments:
            return {
                "matched": False,
                "match_type": "none",
                "notes": "",
            }

        match = matching_fitments[0]
        return {
            "matched": True,
            "match_type": "engine" if match.engine_id else "vehicle_year",
            "notes": match.notes,
        }

    def get_seo(self, obj):
        request = self.context["request"]
        primary = self._resolve_primary_image(obj)
        return _resolve_product_seo_payload(request, obj, primary)

    def _resolve_primary_image(self, obj):
        images = list(obj.images.all())
        if not images:
            return None

        primary = next((image for image in images if image.is_primary), None)
        return primary or images[0]


class ProductSuggestionSerializer(ProductListSerializer):
    fitment_summary = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "manufacturer_part_number",
            "price",
            "price_available",
            "purchasable",
            "in_stock",
            "brand",
            "category",
            "primary_image",
            "fitment_summary",
        )

    def get_fitment_summary(self, obj):
        fitments = list(obj.fitments.all())
        if fitments:
            fitment = fitments[0]
            make = fitment.vehicle_model.make.name
            model = fitment.vehicle_model.name
            years = (
                str(fitment.year_from)
                if fitment.year_from == fitment.year_to
                else f"{fitment.year_from}-{fitment.year_to}"
            )
            return f"{make} {model} · {years}"

        if obj.is_universal_fitment:
            return "უნივერსალური შესაბამისობა"

        return "შესაბამისობა დასაზუსტებელია"


class ProductDetailSerializer(ProductListSerializer):
    description = serializers.CharField()
    sku = serializers.CharField()
    stock_qty = serializers.SerializerMethodField()
    status = serializers.CharField()
    images = ProductImageSerializer(many=True, read_only=True)
    specs = ProductSpecSerializer(many=True, read_only=True)
    fitments = ProductFitmentSerializer(many=True, read_only=True)
    related_products = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description",
            "stock_qty",
            "status",
            "images",
            "specs",
            "fitments",
            "related_products",
            "created_at",
            "updated_at",
        )

    def get_stock_qty(self, obj):
        return obj.customer_available_stock_qty

    def get_related_products(self, obj):
        related_products = self.context.get("related_products") or []
        context = {**self.context, "vehicle_filter": None}
        serializer = ProductListSerializer(
            related_products,
            many=True,
            context=context,
        )
        return serializer.data
