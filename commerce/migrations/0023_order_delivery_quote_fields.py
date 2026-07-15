from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0022_easywayregion_easywaycity")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivery_provider",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_region_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_region_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_city_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_city_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="order",
            name="carrier_delivery_cost",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12, validators=[MinValueValidator(Decimal("0.00"))]),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_margin",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12, validators=[MinValueValidator(Decimal("0.00"))]),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_price",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12, validators=[MinValueValidator(Decimal("0.00"))]),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_weight_kg",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_length_cm",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_width_cm",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_height_cm",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_package_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
