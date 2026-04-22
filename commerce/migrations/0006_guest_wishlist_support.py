from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0005_wishlistitem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="wishlistitem",
            name="commerce_unique_product_per_user_wishlist",
        ),
        migrations.AlterField(
            model_name="wishlistitem",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="wishlist_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="wishlistitem",
            name="guest_token",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="wishlistitem",
            constraint=models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, guest_token__isnull=True)
                    | Q(user__isnull=True, guest_token__isnull=False)
                ),
                name="commerce_wishlist_item_requires_single_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="wishlistitem",
            constraint=models.UniqueConstraint(
                condition=Q(user__isnull=False),
                fields=("user", "product"),
                name="commerce_unique_product_per_user_wishlist",
            ),
        ),
        migrations.AddConstraint(
            model_name="wishlistitem",
            constraint=models.UniqueConstraint(
                condition=Q(guest_token__isnull=False),
                fields=("guest_token", "product"),
                name="commerce_unique_product_per_guest_wishlist",
            ),
        ),
        migrations.AddIndex(
            model_name="wishlistitem",
            index=models.Index(fields=["guest_token", "created_at"], name="commerce_wi_guest_t_44b927_idx"),
        ),
    ]
