from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0010_productfitment_year_range_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="crop_x",
            field=models.DecimalField(
                blank=True,
                decimal_places=5,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productimage",
            name="crop_y",
            field=models.DecimalField(
                blank=True,
                decimal_places=5,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productimage",
            name="crop_width",
            field=models.DecimalField(
                blank=True,
                decimal_places=5,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productimage",
            name="crop_height",
            field=models.DecimalField(
                blank=True,
                decimal_places=5,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productimage",
            name="replace_background_with_white",
            field=models.BooleanField(default=False),
        ),
    ]
