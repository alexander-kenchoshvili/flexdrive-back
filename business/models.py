from django.db import models


class DashboardAccess(models.Model):
    """Permission anchor only; no business table or report data is created."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("view_dashboard", "ბიზნესპანელის ნახვა")]
        verbose_name = "ბიზნესპანელის წვდომა"
        verbose_name_plural = "ბიზნესპანელის წვდომა"


class VehicleInterest(models.Model):
    """Consented vehicle interest, not VINs, owners or customer profiles."""
    day = models.DateField(db_index=True)
    session_digest = models.CharField(max_length=64)
    vehicle_key = models.CharField(max_length=64)
    make = models.CharField(max_length=120)
    model = models.CharField(max_length=120)
    year = models.PositiveSmallIntegerField(null=True)
    variant = models.CharField(max_length=100, blank=True)
    via_vin = models.BooleanField(default=False)
    had_no_results = models.BooleanField(default=False)
    missing_catalog = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("day", "session_digest", "vehicle_key"), name="business_unique_vehicle_interest")]
        indexes = [models.Index(fields=("day", "make", "model", "year"), name="business_vehicle_period")]


class CheckoutProgress(models.Model):
    """Small, consented observations from a customer's existing checkout."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    basket_key = models.CharField(max_length=64)
    event_key = models.CharField(max_length=64, unique=True)
    source = models.CharField(max_length=8)
    stage = models.CharField(max_length=24)
    items = models.JSONField()
    delivery_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    delivery_service = models.CharField(max_length=8, blank=True)


class CartAddition(models.Model):
    """Consented successful additions, not visitors or abandoned revenue."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event_key = models.CharField(max_length=64, unique=True)
    cart_key = models.CharField(max_length=64)
    cart = models.ForeignKey("commerce.Cart", null=True, on_delete=models.SET_NULL)
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL)
    source_item_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=500)
    sku = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["cart_key", "created_at"], name="business_cart_add_context")]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=1), name="business_cart_add_positive")]
