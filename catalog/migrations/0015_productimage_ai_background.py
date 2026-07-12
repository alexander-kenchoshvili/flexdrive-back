import catalog.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_productimage_image_padding"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="image_ai_background",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=catalog.models.product_image_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="productimage",
            name="use_ai_background",
            field=models.BooleanField(
                "AI-ით თეთრი ფონის გამოყენება",
                default=False,
            ),
        ),
    ]
