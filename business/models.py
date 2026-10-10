from django.db import models


class DashboardAccess(models.Model):
    """Permission anchor only; no business table or report data is created."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("view_dashboard", "ბიზნესპანელის ნახვა")]
        verbose_name = "ბიზნესპანელის წვდომა"
        verbose_name_plural = "ბიზნესპანელის წვდომა"
