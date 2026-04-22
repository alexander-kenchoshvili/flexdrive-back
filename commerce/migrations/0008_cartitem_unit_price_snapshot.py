from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def populate_unit_price_snapshot(apps, schema_editor):
    CartItem = apps.get_model("commerce", "CartItem")

    for cart_item in CartItem.objects.select_related("product").all().iterator():
        cart_item.unit_price_snapshot = cart_item.product.price
        cart_item.save(update_fields=["unit_price_snapshot"])


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0007_orderitem_primary_image_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="unit_price_snapshot",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
            preserve_default=False,
        ),
        migrations.RunPython(populate_unit_price_snapshot, migrations.RunPython.noop),
    ]
