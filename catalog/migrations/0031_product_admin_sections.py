from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("catalog", "0030_product_preserve_manual_oem")]

    operations = [
        migrations.CreateModel(
            name="DraftProduct",
            fields=[],
            options={
                "proxy": True,
                "verbose_name": "Draft product",
                "verbose_name_plural": "Drafts",
                "default_permissions": (),
                "indexes": [],
                "constraints": [],
            },
            bases=("catalog.product",),
        ),
        migrations.CreateModel(
            name="ArchivedProduct",
            fields=[],
            options={
                "proxy": True,
                "verbose_name": "Archived product",
                "verbose_name_plural": "Archived",
                "default_permissions": (),
                "indexes": [],
                "constraints": [],
            },
            bases=("catalog.product",),
        ),
    ]
