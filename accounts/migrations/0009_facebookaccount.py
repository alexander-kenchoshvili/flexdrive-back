from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_googleaccount"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacebookAccount",
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
                ("facebook_id", models.CharField(max_length=255, unique=True)),
                ("email", models.EmailField(max_length=254)),
                (
                    "full_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "picture_url",
                    models.URLField(blank=True, default="", max_length=500),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="facebook_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="facebookaccount",
            index=models.Index(
                fields=["email"],
                name="accounts_facebook_email_idx",
            ),
        ),
    ]
