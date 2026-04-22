from django.db import migrations, models


def create_site_settings(apps, schema_editor):
    SiteSettings = apps.get_model("pages", "SiteSettings")
    SiteSettings.objects.update_or_create(
        pk=1,
        defaults={
            "site_name": "AutoMate",
            "default_seo_title": "",
            "default_seo_description": "",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0035_blogpost_cover_image_original_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="seo_canonical_url",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="seo_canonical_url",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="seo_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="seo_image",
            field=models.ImageField(blank=True, null=True, upload_to="seo/"),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="seo_noindex",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="seo_title",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.CreateModel(
            name="SiteSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("site_name", models.CharField(default="AutoMate", max_length=255)),
                ("default_seo_title", models.CharField(blank=True, max_length=255, null=True)),
                ("default_seo_description", models.TextField(blank=True, null=True)),
                ("default_seo_image", models.ImageField(blank=True, null=True, upload_to="seo/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Site Settings",
                "verbose_name_plural": "Site Settings",
            },
        ),
        migrations.RunPython(create_site_settings, migrations.RunPython.noop),
    ]
