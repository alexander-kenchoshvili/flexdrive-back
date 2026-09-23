import re

from django.core.validators import RegexValidator
from django.db import migrations, models
import django.db.models.deletion


GROUPS = {
    "01": "ganateba", "02": "sarkeebi", "03": "dzaris-natsilebi",
    "04": "bamperebi-da-tskhaurebi", "05": "dzravi-zetebi-da-filtrebi",
    "06": "eleqtrooba", "07": "radiatorebi-da-gagrileba", "08": "savali-natsilebi",
}


def seed_sequences(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Category = apps.get_model("catalog", "Category")
    Sequence = apps.get_model("catalog", "SkuSequence")
    for code, slug in GROUPS.items():
        highest = 0
        for value in Product.objects.filter(internal_sku__startswith=f"FD-{code}-").values_list("internal_sku", flat=True):
            match = re.fullmatch(r"FD-\d{2}-(\d+)", value)
            if match:
                highest = max(highest, int(match[1]))
        Sequence.objects.create(code=code, last_number=highest)
        Category.objects.filter(slug=slug, parent__isnull=True).update(sku_sequence_id=code)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0022_product_internal_sku")]
    operations = [
        migrations.CreateModel(
            name="SkuSequence",
            fields=[
                ("code", models.CharField(max_length=2, primary_key=True, serialize=False, validators=[RegexValidator(r"\A[0-9]{2}\Z")])),
                ("last_number", models.PositiveIntegerField(default=0, editable=False)),
            ],
        ),
        migrations.AddField(
            model_name="category", name="sku_sequence",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                to="catalog.skusequence", verbose_name="FlexDrive SKU ჯგუფი",
                help_text="ქვეკატეგორია ავტომატურად იყენებს მთავარი კატეგორიის ჯგუფს."),
        ),
        migrations.RunPython(seed_sequences, migrations.RunPython.noop),
    ]
