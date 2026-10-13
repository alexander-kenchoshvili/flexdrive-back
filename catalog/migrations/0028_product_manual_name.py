from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0027_owned_stock_allocation")]

    operations = [
        # Add in place; rebuilding SQLite would recreate PostgreSQL trigram indexes.
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(
                "ALTER TABLE catalog_product ADD COLUMN preserve_manual_name boolean NOT NULL DEFAULT FALSE",
                "ALTER TABLE catalog_product DROP COLUMN preserve_manual_name",
            )],
            state_operations=[migrations.AddField(
                model_name="product",
                name="preserve_manual_name",
                field=models.BooleanField(
                    default=False, db_default=False, editable=False,
                    verbose_name="ხელით შეცვლილი დასახელება დაცულია",
                    help_text="ადმინისტრატორში სახელის შეცვლისას ავტომატურად ირთვება; იმპორტი ფასსა და მარაგს კვლავ აახლებს.",
                ),
            )],
        ),
    ]
