from django.db import migrations, models


def add_guard(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    if Product.objects.filter(status="published").filter(models.Q(internal_sku__isnull=True) | models.Q(internal_sku="")).exists():
        raise RuntimeError("Import FlexDrive SKUs for all published products after catalog.0023, then retry catalog.0024.")
    if schema_editor.connection.vendor == "sqlite":
        # Avoid a table rebuild that would recreate PostgreSQL-only trigram indexes.
        for event in ("INSERT", "UPDATE"):
            schema_editor.execute(f"""
                CREATE TRIGGER catalog_published_sku_{event.lower()}
                BEFORE {event} ON catalog_product
                WHEN NEW.status = 'published' AND (NEW.internal_sku IS NULL OR NEW.internal_sku = '')
                BEGIN SELECT RAISE(ABORT, 'catalog_published_requires_sku'); END
            """)
    else:
        schema_editor.execute("ALTER TABLE catalog_product ADD CONSTRAINT catalog_published_requires_sku CHECK (status <> 'published' OR (internal_sku IS NOT NULL AND internal_sku <> ''))")


def remove_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        for event in ("insert", "update"):
            schema_editor.execute(f"DROP TRIGGER catalog_published_sku_{event}")
    else:
        schema_editor.execute("ALTER TABLE catalog_product DROP CONSTRAINT catalog_published_requires_sku")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0023_sku_sequences")]
    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunPython(add_guard, remove_guard)],
        state_operations=[migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=~models.Q(status="published") | (models.Q(internal_sku__isnull=False) & ~models.Q(internal_sku="")),
                name="catalog_published_requires_sku",
            ),
        )],
    )]
