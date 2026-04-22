from django.db import migrations, models

import catalog.models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="image_original",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.product_image_upload_to,
            ),
        ),
    ]
