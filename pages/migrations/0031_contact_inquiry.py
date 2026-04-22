from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0030_hide_faq_from_footer"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactInquiry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=255)),
                ("phone", models.CharField(max_length=64)),
                ("email", models.EmailField(max_length=254)),
                ("topic_slug", models.SlugField(max_length=255)),
                ("topic_label", models.CharField(max_length=255)),
                ("order_number", models.CharField(blank=True, max_length=120)),
                ("message", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_progress", "In Progress"),
                            ("resolved", "Resolved"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
