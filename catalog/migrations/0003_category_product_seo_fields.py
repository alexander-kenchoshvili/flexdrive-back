from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_productimage_image_original"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="seo_canonical_url",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="seo_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="seo_image",
            field=models.ImageField(blank=True, null=True, upload_to="seo/"),
        ),
        migrations.AddField(
            model_name="category",
            name="seo_noindex",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="category",
            name="seo_title",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="seo_canonical_url",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="seo_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="seo_image",
            field=models.ImageField(blank=True, null=True, upload_to="seo/"),
        ),
        migrations.AddField(
            model_name="product",
            name="seo_noindex",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="seo_title",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
