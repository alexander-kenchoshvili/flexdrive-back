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
