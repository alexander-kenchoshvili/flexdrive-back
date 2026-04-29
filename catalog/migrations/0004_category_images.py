import catalog.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_category_product_seo_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="image_alt_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="category",
            name="image_desktop",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.category_image_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="image_mobile",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.category_image_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="image_original",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.category_image_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="image_tablet",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.category_image_upload_to,
            ),
        ),
    ]
