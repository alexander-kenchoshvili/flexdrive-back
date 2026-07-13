from django.db import migrations


def delete_empty_obsolete_glass_category(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    category = Category.objects.filter(slug="shushebi").first()

    if category is None:
        return
    if category.products.exists() or category.children.exists():
        return

    category.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0017_seed_category_shipping_defaults"),
    ]

    operations = [
        migrations.RunPython(
            delete_empty_obsolete_glass_category,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
