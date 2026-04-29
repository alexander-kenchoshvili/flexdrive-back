from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductSpec


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


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    on_sale = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "short_description",
            "price",
            "old_price",
            "on_sale",
            "is_new",
            "is_featured",
            "in_stock",
            "category",
            "primary_image",
            "seo",
        )

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
    class Meta(ProductListSerializer.Meta):
        fields = (
            "id",
            "name",
            "slug",
            "price",
            "in_stock",
            "category",
            "primary_image",
        )


class ProductDetailSerializer(ProductListSerializer):
    description = serializers.CharField()
    sku = serializers.CharField()
    stock_qty = serializers.IntegerField()
    status = serializers.CharField()
    images = ProductImageSerializer(many=True, read_only=True)
    specs = ProductSpecSerializer(many=True, read_only=True)
    related_products = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description",
            "sku",
            "stock_qty",
            "status",
            "images",
            "specs",
            "related_products",
            "created_at",
            "updated_at",
        )

    def get_related_products(self, obj):
        related_products = self.context.get("related_products") or []
        serializer = ProductListSerializer(
            related_products,
            many=True,
            context=self.context,
        )
        return serializer.data
