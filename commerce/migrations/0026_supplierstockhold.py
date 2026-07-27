import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0019_product_supplier_stock_tracking"),
        ("commerce", "0025_alter_order_easyway_shipment_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplierStockHold",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="რაოდენობა",
                    ),
                ),
                (
                    "supplier_stock_at_sale",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Cross Motors-ის ნაშთი გაყიდვისას",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "მოქმედი"),
                            ("expired", "ვადაგასული"),
                            ("manually_released", "ხელით მოხსნილი"),
                            ("order_cancelled", "შეკვეთა გაუქმდა"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=32,
                        verbose_name="მდგომარეობა",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="მოქმედებს თარიღამდე",
                    ),
                ),
                (
                    "released_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="მოხსნის დრო",
                    ),
                ),
                (
                    "release_note",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="მოხსნის მიზეზი",
                    ),
                ),
                (
                    "order_item",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supplier_stock_hold",
                        to="commerce.orderitem",
                        verbose_name="შეკვეთის პროდუქტი",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supplier_stock_holds",
                        to="catalog.product",
                        verbose_name="პროდუქტი",
                    ),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="released_supplier_stock_holds",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ვინ მოხსნა",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "verbose_name": "Cross Motors-ის დროებითი ჩამოკლება",
                "verbose_name_plural": "Cross Motors-ის დროებითი ჩამოკლებები",
                "indexes": [
                    models.Index(
                        fields=["status", "expires_at"],
                        name="commerce_su_status_bf9938_idx",
                    ),
                    models.Index(
                        fields=["product", "status"],
                        name="commerce_su_product_32580b_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gte", 1)),
                        name="commerce_supplier_hold_quantity_positive",
                    ),
                ],
            },
        ),
    ]
