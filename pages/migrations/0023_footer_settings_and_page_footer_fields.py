from django.db import migrations, models


def seed_footer_defaults(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    FooterSettings = apps.get_model("pages", "FooterSettings")

    FooterSettings.objects.update_or_create(
        pk=1,
        defaults={
            "brand_name": "AutoMate",
            "brand_description": "AutoMate გაძლევს ავტომობილის აქსესუარების დათვალიერებისა და შეძენის მარტივ, გასაგებ და სანდო გზას.",
            "trust_item_1": "მარტივი შეკვეთა",
            "trust_item_2": "სწრაფი მიწოდება",
            "trust_item_3": "უსაფრთხო გადახდა",
            "phone": "+995 5XX XX XX XX",
            "email": "support@automate.ge",
            "working_hours": "ორშ-პარ, 10:00 - 19:00",
            "city": "თბილისი, საქართველო",
            "instagram_url": "",
            "facebook_url": "",
            "copyright_text": "© 2026 AutoMate. ყველა უფლება დაცულია.",
        },
    )

    footer_pages = [
        {
            "slug": "main",
            "name": "მთავარი",
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 10,
            "show_in_menu": True,
            "seo_noindex": False,
        },
        {
            "slug": "catalog",
            "name": "კატალოგი",
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 20,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "blogs",
            "name": "ბლოგი",
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 30,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "faq",
            "name": "ხშირად დასმული კითხვები",
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 40,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "contact",
            "name": "კონტაქტი",
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 50,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "delivery",
            "name": "მიწოდება",
            "show_in_footer": True,
            "footer_group": "help",
            "footer_order": 10,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "payment-methods",
            "name": "გადახდის მეთოდები",
            "show_in_footer": True,
            "footer_group": "help",
            "footer_order": 20,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "returns",
            "name": "დაბრუნება",
            "show_in_footer": True,
            "footer_group": "help",
            "footer_order": 30,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "warranty",
            "name": "გარანტია",
            "show_in_footer": False,
            "footer_group": "help",
            "footer_order": 40,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "privacy-policy",
            "name": "კონფიდენციალურობა",
            "show_in_footer": True,
            "footer_group": "legal",
            "footer_order": 10,
            "show_in_menu": False,
            "seo_noindex": True,
        },
        {
            "slug": "terms",
            "name": "წესები და პირობები",
            "show_in_footer": True,
            "footer_group": "legal",
            "footer_order": 20,
            "show_in_menu": False,
            "seo_noindex": True,
        },
    ]

    for config in footer_pages:
        page, created = Page.objects.get_or_create(
            slug=config["slug"],
            defaults={
                "name": config["name"],
                "show_in_menu": config["show_in_menu"],
                "show_in_footer": config["show_in_footer"],
                "footer_group": config["footer_group"],
                "footer_order": config["footer_order"],
                "seo_noindex": config["seo_noindex"],
            },
        )

        update_fields = []

        if page.show_in_footer != config["show_in_footer"]:
            page.show_in_footer = config["show_in_footer"]
            update_fields.append("show_in_footer")

        if page.footer_group != config["footer_group"]:
            page.footer_group = config["footer_group"]
            update_fields.append("footer_group")

        if page.footer_order != config["footer_order"]:
            page.footer_order = config["footer_order"]
            update_fields.append("footer_order")

        if created:
            if page.show_in_menu != config["show_in_menu"]:
                page.show_in_menu = config["show_in_menu"]
                update_fields.append("show_in_menu")
            if page.seo_noindex != config["seo_noindex"]:
                page.seo_noindex = config["seo_noindex"]
                update_fields.append("seo_noindex")

        if update_fields:
            page.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0022_seed_order_confidence_component"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="footer_group",
            field=models.CharField(
                blank=True,
                choices=[("navigation", "Navigation"), ("help", "Help"), ("legal", "Legal")],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="footer_label",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="page",
            name="footer_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="page",
            name="show_in_footer",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="FooterSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("brand_name", models.CharField(default="AutoMate", max_length=255)),
                ("brand_description", models.TextField(blank=True, null=True)),
                ("trust_item_1", models.CharField(blank=True, max_length=255, null=True)),
                ("trust_item_2", models.CharField(blank=True, max_length=255, null=True)),
                ("trust_item_3", models.CharField(blank=True, max_length=255, null=True)),
                ("phone", models.CharField(blank=True, max_length=255, null=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("working_hours", models.CharField(blank=True, max_length=255, null=True)),
                ("city", models.CharField(blank=True, max_length=255, null=True)),
                ("instagram_url", models.URLField(blank=True, null=True)),
                ("facebook_url", models.URLField(blank=True, null=True)),
                ("copyright_text", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Footer Settings",
                "verbose_name_plural": "Footer Settings",
            },
        ),
        migrations.RunPython(seed_footer_defaults, migrations.RunPython.noop),
    ]
