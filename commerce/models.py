import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product, TimeStampedModel


class OrderPaymentMethod(models.TextChoices):
    CASH_ON_DELIVERY = "cash_on_delivery", "Cash on delivery"
    CARD = "card", "Card"


class OrderPaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    AUTHORIZED = "authorized", "Authorized"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUND_PENDING = "refund_pending", "Refund pending"
    REFUNDED = "refunded", "Refunded"


class OrderCheckoutSource(models.TextChoices):
    CART = "cart", "Cart"
    BUY_NOW = "buy_now", "Buy now"


class StockReservationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    EXPIRED = "expired", "Expired"
    RELEASED = "released", "Released"


class PaymentProvider(models.TextChoices):
    MOCK = "mock", "Mock"
    MANUAL = "manual", "Manual"


class PaymentTransactionAction(models.TextChoices):
    AUTHORIZE = "authorize", "Authorize"
    CAPTURE = "capture", "Capture"
    SALE = "sale", "Sale"
    CANCEL = "cancel", "Cancel"
    REFUND = "refund", "Refund"


class PaymentTransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    AUTHORIZED = "authorized", "Authorized"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUND_PENDING = "refund_pending", "Refund pending"
    REFUNDED = "refunded", "Refunded"


class OrderStatus(models.TextChoices):
    NEW = "new", "New"
    CONFIRMED = "confirmed", "Confirmed"
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class Cart(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="carts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    guest_token = models.UUIDField(unique=True, null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(user__isnull=False, is_active=True),
                name="commerce_one_active_cart_per_user",
            )
        ]

    def __str__(self):
        owner = self.user_id or self.guest_token or "anonymous"
        return f"Cart {self.pk} ({owner})"

    def _iter_items(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if prefetched is not None:
            return prefetched
        return self.items.select_related("product").all()

    @property
    def item_count(self):
        return sum(item.quantity for item in self._iter_items())

    @property
    def subtotal(self):
        return sum((item.line_total for item in self._iter_items()), Decimal("0.00"))

    @property
    def total(self):
        return self.subtotal

    @property
    def price_change_count(self):
        return sum(1 for item in self._iter_items() if item.price_changed)

    @property
    def has_price_changes(self):
        return self.price_change_count > 0


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(
        Cart,
        related_name="items",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        related_name="cart_items",
        on_delete=models.PROTECT,
    )
    unit_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="commerce_unique_product_per_cart",
            )
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        if self.unit_price_snapshot is None and self.product_id:
            self.unit_price_snapshot = self.product.price
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.product.price * self.quantity

    @property
    def price_changed(self):
        return self.unit_price_snapshot != self.product.price

    @property
    def price_change_direction(self):
        if self.product.price > self.unit_price_snapshot:
            return "increase"
        if self.product.price < self.unit_price_snapshot:
            return "decrease"
        return "same"


class BuyNowSession(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="buy_now_sessions",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    guest_token = models.UUIDField(null=True, blank=True, db_index=True)
    product = models.ForeignKey(
        Product,
        related_name="buy_now_sessions",
        on_delete=models.PROTECT,
    )
    unit_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, guest_token__isnull=True)
                    | Q(user__isnull=True, guest_token__isnull=False)
                ),
                name="commerce_buy_now_session_requires_single_owner",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(user__isnull=False),
                name="commerce_one_buy_now_session_per_user",
            ),
            models.UniqueConstraint(
                fields=["guest_token"],
                condition=Q(guest_token__isnull=False),
                name="commerce_one_buy_now_session_per_guest",
            ),
        ]

    def __str__(self):
        owner = self.user_id or self.guest_token or "anonymous"
        return f"Buy now {self.pk} ({owner})"

    def save(self, *args, **kwargs):
        if self.unit_price_snapshot is None and self.product_id:
            self.unit_price_snapshot = self.product.price
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.product.price * self.quantity

    @property
    def subtotal(self):
        return self.line_total

    @property
    def total(self):
        return self.line_total

    @property
    def price_changed(self):
        return self.unit_price_snapshot != self.product.price

    @property
    def price_change_direction(self):
        if self.product.price > self.unit_price_snapshot:
            return "increase"
        if self.product.price < self.unit_price_snapshot:
            return "decrease"
        return "same"


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="wishlist_items",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    guest_token = models.UUIDField(null=True, blank=True, db_index=True)
    product = models.ForeignKey(
        Product,
        related_name="wishlist_items",
        on_delete=models.CASCADE,
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, guest_token__isnull=True)
                    | Q(user__isnull=True, guest_token__isnull=False)
                ),
                name="commerce_wishlist_item_requires_single_owner",
            ),
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=Q(user__isnull=False),
                name="commerce_unique_product_per_user_wishlist",
            ),
            models.UniqueConstraint(
                fields=["guest_token", "product"],
                condition=Q(guest_token__isnull=False),
                name="commerce_unique_product_per_guest_wishlist",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["guest_token", "created_at"], name="commerce_wi_guest_t_44b927_idx"),
        ]

    def __str__(self):
        owner = self.user_id or self.guest_token or "anonymous"
        return f"{owner}:{self.product_id}"


class Order(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="orders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    order_number = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    checkout_source = models.CharField(
        max_length=20,
        choices=OrderCheckoutSource.choices,
        default=OrderCheckoutSource.CART,
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=32,
        choices=OrderPaymentMethod.choices,
        default=OrderPaymentMethod.CASH_ON_DELIVERY,
    )
    payment_status = models.CharField(
        max_length=32,
        choices=OrderPaymentStatus.choices,
        default=OrderPaymentStatus.PENDING,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.NEW,
        db_index=True,
    )
    stock_restored_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50)
    city = models.CharField(max_length=120)
    address_line = models.CharField(max_length=255)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["payment_method", "created_at"]),
            models.Index(fields=["payment_status", "created_at"]),
        ]

    def __str__(self):
        return self.order_number or f"Order {self.pk}"


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        related_name="order_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    primary_image_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class StockReservation(TimeStampedModel):
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="stock_reservations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    guest_token = models.UUIDField(null=True, blank=True, db_index=True)
    source = models.CharField(
        max_length=20,
        choices=OrderCheckoutSource.choices,
        default=OrderCheckoutSource.CART,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=StockReservationStatus.choices,
        default=StockReservationStatus.ACTIVE,
        db_index=True,
    )
    expires_at = models.DateTimeField(db_index=True)
    completed_order = models.ForeignKey(
        Order,
        related_name="stock_reservations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, guest_token__isnull=True)
                    | Q(user__isnull=True, guest_token__isnull=False)
                ),
                name="commerce_stock_reservation_requires_single_owner",
            )
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["source", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["guest_token", "status"], name="commerce_sr_gst_st_idx"),
        ]

    def __str__(self):
        return f"Reservation {self.token} ({self.status})"

    @property
    def is_active(self):
        return self.status == StockReservationStatus.ACTIVE and self.expires_at > timezone.now()


class StockReservationItem(TimeStampedModel):
    reservation = models.ForeignKey(
        StockReservation,
        related_name="items",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        related_name="stock_reservation_items",
        on_delete=models.PROTECT,
    )
    unit_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "product"],
                name="commerce_unique_product_per_stock_reservation",
            )
        ]

    def __str__(self):
        return f"{self.product_id} x {self.quantity}"

    @property
    def line_total(self):
        return self.unit_price_snapshot * self.quantity


class PaymentTransaction(TimeStampedModel):
    order = models.ForeignKey(
        Order,
        related_name="payment_transactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reservation = models.ForeignKey(
        StockReservation,
        related_name="payment_transactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    provider = models.CharField(
        max_length=32,
        choices=PaymentProvider.choices,
        default=PaymentProvider.MOCK,
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=32,
        choices=OrderPaymentMethod.choices,
        default=OrderPaymentMethod.CARD,
    )
    action = models.CharField(
        max_length=32,
        choices=PaymentTransactionAction.choices,
        default=PaymentTransactionAction.AUTHORIZE,
        db_index=True,
    )
    status = models.CharField(
        max_length=32,
        choices=PaymentTransactionStatus.choices,
        default=PaymentTransactionStatus.PENDING,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="GEL")
    provider_transaction_id = models.CharField(max_length=120, blank=True, db_index=True)
    provider_reference = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["provider", "status", "created_at"]),
            models.Index(fields=["order", "status"]),
            models.Index(fields=["reservation", "status"]),
        ]

    def __str__(self):
        target = self.order_id or self.reservation_id or "unbound"
        return f"{self.provider}:{self.action}:{self.status} ({target})"
