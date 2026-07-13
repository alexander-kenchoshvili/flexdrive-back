from decimal import Decimal

from django.db import migrations


CATEGORY_SHIPPING_DEFAULTS = {
    "ganateba": ("5.000", "65.00", "45.00", "35.00"),
    "sarkeebi": ("3.000", "45.00", "35.00", "30.00"),
    "dzaris-natsilebi": ("10.000", "110.00", "60.00", "35.00"),
    "bamperebi-da-tskhaurebi": ("8.000", "100.00", "50.00", "35.00"),
    "dzravi-zetebi-da-filtrebi": ("7.000", "55.00", "40.00", "35.00"),
    "eleqtrooba": ("3.000", "45.00", "35.00", "25.00"),
    "radiatorebi-da-gagrileba": ("8.000", "90.00", "60.00", "20.00"),
    "savali-natsilebi": ("10.000", "60.00", "45.00", "35.00"),
}


def seed_category_shipping_defaults(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")

    for slug, values in CATEGORY_SHIPPING_DEFAULTS.items():
        weight, length, width, height = values
        Category.objects.filter(slug=slug).update(
            default_shipping_weight_kg=Decimal(weight),
            default_shipping_length_cm=Decimal(length),
            default_shipping_width_cm=Decimal(width),
            default_shipping_height_cm=Decimal(height),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0016_category_default_shipping_height_cm_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_category_shipping_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
