import django.contrib.postgres.indexes
from django.db import migrations, models
from django.db.models.functions import Upper


def initialize_cross_motors_stock(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.filter(sku__startswith="CM-").update(
        supplier_source="cross_motors",
        supplier_stock_qty=models.F("stock_qty"),
        supplier_stock_synced_at=models.F("updated_at"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0018_delete_empty_obsolete_glass_category"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="product",
                    name="catalog_product_name_trgm",
                ),
                migrations.RemoveIndex(
                    model_name="product",
                    name="catalog_product_mpn_trgm",
                ),
            ],
        ),
        migrations.AddField(
            model_name="product",
            name="supplier_source",
            field=models.CharField(
                choices=[
                    ("manual", "ხელით დამატებული"),
                    ("cross_motors", "Cross Motors"),
                ],
                db_index=True,
                default="manual",
                max_length=32,
                verbose_name="მომწოდებელი",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="supplier_stock_qty",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Cross Motors-ის ბოლო ნაშთი",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="supplier_stock_synced_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="ბოლო სინქრონიზაცია",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="product",
                    index=django.contrib.postgres.indexes.GinIndex(
                        django.contrib.postgres.indexes.OpClass(
                            Upper("name"),
                            name="gin_trgm_ops",
                        ),
                        name="catalog_product_name_trgm",
                    ),
                ),
                migrations.AddIndex(
                    model_name="product",
                    index=django.contrib.postgres.indexes.GinIndex(
                        django.contrib.postgres.indexes.OpClass(
                            Upper("manufacturer_part_number"),
                            name="gin_trgm_ops",
                        ),
                        name="catalog_product_mpn_trgm",
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            initialize_cross_motors_stock,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
