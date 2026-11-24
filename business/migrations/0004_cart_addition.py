import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0003_checkout_progress"),
        ("commerce", "0046_order_personal_number"),
        ("catalog", "0001_initial"),
    ]
    operations = [migrations.CreateModel(
        name="CartAddition",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("event_key", models.CharField(max_length=64, unique=True)),
            ("cart_key", models.CharField(max_length=64)),
            ("source_item_id", models.PositiveBigIntegerField()),
            ("name", models.CharField(max_length=500)),
            ("sku", models.CharField(blank=True, max_length=100)),
            ("quantity", models.PositiveIntegerField()),
            ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
            ("cart", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="commerce.cart")),
            ("product", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="catalog.product")),
        ],
        options={
            "indexes": [models.Index(fields=["cart_key", "created_at"], name="business_cart_add_context")],
            "constraints": [models.CheckConstraint(condition=models.Q(quantity__gte=1), name="business_cart_add_positive")],
        },
    )]
