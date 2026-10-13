import re

from django.db import migrations


def clear_exact_legacy_imported_titles(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    database = schema_editor.connection.alias
    marker = re.compile(r"\(\s*(LH|RH)\s*\)", re.IGNORECASE)
    candidates = Product.objects.using(database).filter(
        supplier_source="cross_motors", preserve_manual_fitment_content=False,
    ).only("pk", "name", "seo_title")
    matched = []
    for product in candidates.iterator(chunk_size=500):
        name = str(product.name or "").strip()
        clean = re.sub(r"\s+", " ", marker.sub("", name)).strip()
        if product.seo_title == f"{clean or name} | FlexDrive":
            matched.append(product.pk)
    for offset in range(0, len(matched), 500):
        Product.objects.using(database).filter(pk__in=matched[offset:offset + 500]).update(seo_title="")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0028_product_manual_name")]

    operations = [migrations.RunPython(
        clear_exact_legacy_imported_titles,
        migrations.RunPython.noop,
    )]
