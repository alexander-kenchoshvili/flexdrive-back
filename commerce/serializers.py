from django.urls import reverse
from rest_framework import serializers

from catalog.models import Product, ProductStatus

from .card_payments import (
    can_redirect_to_bog,
    can_retry_card_payment_start,
    get_provider_order_expires_at,
    get_public_payment_result,
)
from .images import build_product_primary_image_snapshot, empty_image_asset, serialize_image_asset
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    EasywayCity,
    EasywayRegion,
    Order,
    OrderBuyerType,
    OrderItem,
    OrderPaymentMethod,
    PaymentTransaction,
    PaymentTransactionStatus,
    WishlistItem,
)
from .services import (
    build_cart_price_change_message,
    get_buy_now_session_issue_data,
    get_cart_item_availability_issue,
    get_product_availability_issue,
)


class CartItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_product_id(self, value):
        product = (
            Product.objects.filter(
                id=value,
                status=ProductStatus.PUBLISHED,
                category__is_active=True,
            )
            .select_related("category")
            .first()
        )
        if not product:
            raise serializers.ValidationError("Product is not available.")
        self.context["product"] = product
        return value


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class BuyNowSessionCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_product_id(self, value):
        product = (
            Product.objects.filter(
                id=value,
                status=ProductStatus.PUBLISHED,
                category__is_active=True,
            )
            .select_related("category")
            .first()
        )
        if not product:
            raise serializers.ValidationError("Product is not available.")
        self.context["product"] = product
        return value


class WishlistItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        product = (
            Product.objects.filter(
                id=value,
                status=ProductStatus.PUBLISHED,
                category__is_active=True,
            )
            .select_related("category")
            .first()
        )
        if not product:
            raise serializers.ValidationError("Product is not available.")
        self.context["product"] = product
        return value


class CheckoutSerializer(serializers.Serializer):
    buyer_type = serializers.ChoiceField(
        choices=OrderBuyerType.choices,
        default=OrderBuyerType.INDIVIDUAL,
        required=False,
    )
    company_name = serializers.CharField(
        max_length=255,
        allow_blank=True,
        required=False,
        default="",
    )
    company_identification_code = serializers.CharField(
        max_length=32,
        allow_blank=True,
        required=False,
        default="",
    )
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=50)
    delivery_region_id = serializers.IntegerField(min_value=1)
    delivery_city_id = serializers.IntegerField(min_value=1)
    delivery_quote_token = serializers.CharField(write_only=True)
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address_line = serializers.CharField(max_length=255)
    note = serializers.CharField(allow_blank=True, required=False)
    terms_accepted = serializers.BooleanField(
        write_only=True,
        error_messages={
            "required": "შეკვეთის დასადასტურებლად დაეთანხმეთ წესებსა და პირობებს."
        },
    )
    payment_method = serializers.ChoiceField(choices=OrderPaymentMethod.choices)

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "შეკვეთის დასადასტურებლად დაეთანხმეთ წესებსა და პირობებს."
            )
        return value

    def validate_payment_method(self, value):
        if value == OrderPaymentMethod.CARD:
            raise serializers.ValidationError("Card payments are temporarily unavailable.")
        return value

    def validate(self, attrs):
        region = EasywayRegion.objects.filter(
            external_id=attrs["delivery_region_id"],
            is_active=True,
        ).first()
        city = EasywayCity.objects.filter(
            external_id=attrs["delivery_city_id"],
            region=region,
            is_active=True,
        ).first()
        location_errors = {}
        if region is None:
            location_errors["delivery_region_id"] = "არჩეული რეგიონი ვერ მოიძებნა."
        if city is None:
            location_errors["delivery_city_id"] = "არჩეული ქალაქი ვერ მოიძებნა."
        if location_errors:
            raise serializers.ValidationError(location_errors)
        attrs["city"] = city.name

        buyer_type = attrs.get("buyer_type", OrderBuyerType.INDIVIDUAL)

        if buyer_type != OrderBuyerType.LEGAL_ENTITY:
            attrs["company_name"] = ""
            attrs["company_identification_code"] = ""
            return attrs

        company_name = str(attrs.get("company_name", "")).strip()
        company_identification_code = str(
            attrs.get("company_identification_code", "")
        ).strip()

        errors = {}
        if not company_name:
            errors["company_name"] = "შეიყვანე კომპანიის დასახელება."

        if not company_identification_code:
            errors["company_identification_code"] = "შეიყვანე საიდენტიფიკაციო კოდი."
        elif not (
            company_identification_code.isdigit()
            and len(company_identification_code) == 9
        ):
            errors["company_identification_code"] = (
                "შეიყვანე 9-ნიშნა საიდენტიფიკაციო კოდი."
            )

        if errors:
            raise serializers.ValidationError(errors)

        attrs["company_name"] = company_name
        attrs["company_identification_code"] = company_identification_code
        return attrs


class DeliveryQuoteRequestSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=("cart", "buy_now"))
    delivery_region_id = serializers.IntegerField(min_value=1)
    delivery_city_id = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        region = EasywayRegion.objects.filter(
            external_id=attrs["delivery_region_id"],
            is_active=True,
        ).first()
        city = EasywayCity.objects.filter(
            external_id=attrs["delivery_city_id"],
            region=region,
            is_active=True,
        ).first()
        errors = {}
        if region is None:
            errors["delivery_region_id"] = "არჩეული რეგიონი ვერ მოიძებნა."
        if city is None:
            errors["delivery_city_id"] = "არჩეული ქალაქი ვერ მოიძებნა."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["region"] = region
        attrs["city"] = city
        return attrs


class CardPaymentCheckoutSerializer(CheckoutSerializer):
    payment_method = serializers.ChoiceField(
        choices=((OrderPaymentMethod.CARD, "Card"),),
    )

    def validate_payment_method(self, value):
        return value


class CardPaymentSerializer(serializers.ModelSerializer):
    payment_token = serializers.UUIDField(source="public_token", read_only=True)
    result = serializers.SerializerMethodField()
    redirect_url = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    can_retry_start = serializers.SerializerMethodField()
    is_terminal = serializers.SerializerMethodField()
    order_public_token = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()
    status_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = (
            "payment_token",
            "status",
            "result",
            "amount",
            "currency",
            "redirect_url",
            "expires_at",
            "can_retry_start",
            "is_terminal",
            "order_public_token",
            "order_number",
            "status_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_result(self, obj):
        return get_public_payment_result(obj)

    def get_redirect_url(self, obj):
        return obj.redirect_url if can_redirect_to_bog(obj) else None

    def get_expires_at(self, obj):
        return get_provider_order_expires_at(obj)

    def get_can_retry_start(self, obj):
        return can_retry_card_payment_start(obj)

    def get_is_terminal(self, obj):
        return obj.status in {
            PaymentTransactionStatus.PAID,
            PaymentTransactionStatus.FAILED,
            PaymentTransactionStatus.CANCELLED,
            PaymentTransactionStatus.REFUNDED,
        }

    def get_order_public_token(self, obj):
        if not obj.order_id:
            return None
        return obj.order.public_token

    def get_order_number(self, obj):
        if not obj.order_id:
            return None
        return obj.order.order_number

    def get_status_url(self, obj):
        request = self.context.get("request")
        path = reverse(
            "commerce-card-payment-status",
            kwargs={"public_token": obj.public_token},
        )
        return request.build_absolute_uri(path) if request else path


def normalize_order_lookup_phone(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if digits.startswith("995") and len(digits) > 9:
        return digits[3:]
    return digits


class OrderLookupSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32, trim_whitespace=True)
    phone = serializers.CharField(max_length=50, trim_whitespace=True)
    recaptcha_token = serializers.CharField(write_only=True, trim_whitespace=True)

    def validate(self, attrs):
        attrs["normalized_phone"] = normalize_order_lookup_phone(attrs["phone"])
        return attrs


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    slug = serializers.CharField(source="product.slug", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    category = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)
    price_snapshot = serializers.DecimalField(
        source="unit_price_snapshot",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    old_price = serializers.DecimalField(
        source="product.old_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    on_sale = serializers.BooleanField(source="product.on_sale", read_only=True)
    in_stock = serializers.BooleanField(source="product.in_stock", read_only=True)
    stock_qty = serializers.IntegerField(source="product.customer_available_stock_qty", read_only=True)
    is_purchasable = serializers.SerializerMethodField()
    availability_issue = serializers.SerializerMethodField()
    price_changed = serializers.BooleanField(read_only=True)
    price_change_direction = serializers.CharField(read_only=True)
    primary_image = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = (
            "id",
            "product_id",
            "slug",
            "name",
            "sku",
            "category",
            "price",
            "price_snapshot",
            "old_price",
            "on_sale",
            "in_stock",
            "stock_qty",
            "is_purchasable",
            "availability_issue",
            "price_changed",
            "price_change_direction",
            "primary_image",
            "quantity",
            "line_total",
        )

    def get_category(self, obj):
        return {
            "id": obj.product.category_id,
            "name": obj.product.category.name,
            "slug": obj.product.category.slug,
        }

    def get_primary_image(self, obj):
        request = self.context.get("request")
        return serialize_image_asset(
            build_product_primary_image_snapshot(obj.product),
            request=request,
        )

    def get_is_purchasable(self, obj):
        return get_cart_item_availability_issue(obj) == "available"

    def get_availability_issue(self, obj):
        return get_cart_item_availability_issue(obj)


class CartSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_price_changes = serializers.BooleanField(read_only=True)
    price_change_count = serializers.IntegerField(read_only=True)
    price_change_message = serializers.SerializerMethodField()
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = (
            "id",
            "item_count",
            "subtotal",
            "total",
            "has_price_changes",
            "price_change_count",
            "price_change_message",
            "items",
        )

    def get_price_change_message(self, obj):
        if not obj.has_price_changes:
            return None
        return build_cart_price_change_message(obj.price_change_count)


class BuyNowIssueSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    issue_type = serializers.CharField()
    requested_quantity = serializers.IntegerField()
    available_quantity = serializers.IntegerField()
    price_snapshot = serializers.DecimalField(max_digits=10, decimal_places=2)
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class BuyNowSessionSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    slug = serializers.CharField(source="product.slug", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)
    price_snapshot = serializers.DecimalField(
        source="unit_price_snapshot",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    in_stock = serializers.BooleanField(source="product.in_stock", read_only=True)
    stock_qty = serializers.IntegerField(source="product.customer_available_stock_qty", read_only=True)
    is_purchasable = serializers.SerializerMethodField()
    availability_issue = serializers.SerializerMethodField()
    price_changed = serializers.BooleanField(read_only=True)
    price_change_direction = serializers.CharField(read_only=True)
    primary_image = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    issues = serializers.SerializerMethodField()
    requires_confirmation = serializers.SerializerMethodField()
    is_checkout_available = serializers.SerializerMethodField()

    class Meta:
        model = BuyNowSession
        fields = (
            "id",
            "product_id",
            "slug",
            "name",
            "sku",
            "price",
            "price_snapshot",
            "quantity",
            "line_total",
            "subtotal",
            "total",
            "in_stock",
            "stock_qty",
            "is_purchasable",
            "availability_issue",
            "price_changed",
            "price_change_direction",
            "primary_image",
            "issues",
            "requires_confirmation",
            "is_checkout_available",
        )

    def _get_issues(self, obj):
        return get_buy_now_session_issue_data(obj)

    def get_is_purchasable(self, obj):
        return get_product_availability_issue(obj.product) == "available"

    def get_availability_issue(self, obj):
        return get_product_availability_issue(obj.product)

    def get_primary_image(self, obj):
        request = self.context.get("request")
        return serialize_image_asset(
            build_product_primary_image_snapshot(obj.product),
            request=request,
        )

    def get_issues(self, obj):
        return BuyNowIssueSerializer(self._get_issues(obj), many=True).data

    def get_requires_confirmation(self, obj):
        issues = self._get_issues(obj)
        if not issues:
            return False
        return not any(issue["issue_type"] in {"out_of_stock", "unavailable"} for issue in issues)

    def get_is_checkout_available(self, obj):
        return len(self._get_issues(obj)) == 0


class WishlistItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    saved_at = serializers.DateTimeField(source="created_at", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    slug = serializers.CharField(source="product.slug", read_only=True)
    short_description = serializers.CharField(source="product.short_description", read_only=True)
    price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)
    old_price = serializers.DecimalField(
        source="product.old_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    on_sale = serializers.BooleanField(source="product.on_sale", read_only=True)
    is_new = serializers.BooleanField(source="product.is_new", read_only=True)
    is_featured = serializers.BooleanField(source="product.is_featured", read_only=True)
    in_stock = serializers.BooleanField(source="product.in_stock", read_only=True)
    stock_qty = serializers.IntegerField(source="product.customer_available_stock_qty", read_only=True)
    category = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = WishlistItem
        fields = (
            "product_id",
            "saved_at",
            "name",
            "slug",
            "short_description",
            "price",
            "old_price",
            "on_sale",
            "is_new",
            "is_featured",
            "in_stock",
            "stock_qty",
            "category",
            "primary_image",
        )

    def get_category(self, obj):
        return {
            "id": obj.product.category_id,
            "name": obj.product.category.name,
            "slug": obj.product.category.slug,
        }

    def get_primary_image(self, obj):
        request = self.context.get("request")
        return serialize_image_asset(
            build_product_primary_image_snapshot(obj.product),
            request=request,
        )


class OrderItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_name",
            "sku",
            "unit_price",
            "quantity",
            "line_total",
            "primary_image",
        )

    def get_primary_image(self, obj):
        request = self.context.get("request")
        snapshot = obj.primary_image_snapshot or empty_image_asset()
        return serialize_image_asset(snapshot, request=request)


class OrderLookupItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "product_name",
            "sku",
            "unit_price",
            "quantity",
            "line_total",
            "primary_image",
        )

    def get_primary_image(self, obj):
        request = self.context.get("request")
        snapshot = obj.primary_image_snapshot or empty_image_asset()
        return serialize_image_asset(snapshot, request=request)


class OrderListSerializer(serializers.ModelSerializer):
    public_token = serializers.UUIDField(read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "public_token",
            "order_number",
            "status",
            "payment_method",
            "payment_status",
            "total",
            "created_at",
            "item_count",
            "total_quantity",
        )


class OrderListSummarySerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_order_at = serializers.DateTimeField(allow_null=True)


class OrderSummarySerializer(serializers.ModelSerializer):
    public_token = serializers.UUIDField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "public_token",
            "order_number",
            "buyer_type",
            "company_name",
            "company_identification_code",
            "payment_method",
            "payment_status",
            "status",
            "subtotal",
            "delivery_price",
            "total",
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "delivery_provider",
            "delivery_region_id",
            "delivery_region_name",
            "delivery_city_id",
            "delivery_city_name",
            "address_line",
            "note",
            "items",
            "created_at",
        )


class PublicOrderSummarySerializer(serializers.ModelSerializer):
    public_token = serializers.UUIDField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "public_token",
            "order_number",
            "payment_method",
            "payment_status",
            "status",
            "subtotal",
            "delivery_price",
            "total",
            "items",
            "created_at",
        )


class OrderLookupSummarySerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    items = OrderLookupItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "order_number",
            "status",
            "payment_status",
            "payment_method",
            "checkout_source",
            "total",
            "created_at",
            "item_count",
            "total_quantity",
            "items",
        )

    def get_item_count(self, obj):
        return len(obj.items.all())

    def get_total_quantity(self, obj):
        return sum(item.quantity for item in obj.items.all())
