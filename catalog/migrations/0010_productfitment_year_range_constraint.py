from django.db import migrations, models
from django.db.models import F, Q


def validate_existing_fitments(apps, schema_editor):
    product_fitment = apps.get_model("catalog", "ProductFitment")
    if product_fitment.objects.filter(year_to__lt=F("year_from")).exists():
        raise RuntimeError(
            "Invalid ProductFitment year ranges exist. Fix them before applying this migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_category_catalog_category_markup_range_and_more"),
    ]

    operations = [
        migrations.RunPython(validate_existing_fitments, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="productfitment",
            constraint=models.CheckConstraint(
                condition=Q(year_to__gte=F("year_from")),
                name="catalog_fitment_year_range_valid",
            ),
        ),
    ]
