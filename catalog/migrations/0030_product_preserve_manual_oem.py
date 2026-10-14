from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0029_auto_product_seo_titles")]

    operations = [
        # Add in place, preserving SQLite compatibility with the PostgreSQL indexes.
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(
                "ALTER TABLE catalog_product ADD COLUMN preserve_manual_oem boolean NOT NULL DEFAULT FALSE",
                "ALTER TABLE catalog_product DROP COLUMN preserve_manual_oem",
            )],
            state_operations=[migrations.AddField(
                model_name="product",
                name="preserve_manual_oem",
                field=models.BooleanField(
                    default=False, db_default=False, editable=False,
                    verbose_name="ხელით შეცვლილი OEM დაცულია",
                    help_text="ადმინისტრატორში OEM-ის შეცვლისას ავტომატურად ირთვება; ფასი და მარაგი კვლავ განახლდება.",
                ),
            )],
        ),
    ]
