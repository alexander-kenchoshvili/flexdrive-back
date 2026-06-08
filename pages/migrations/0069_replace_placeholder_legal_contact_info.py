from django.db import migrations


SUPPORT_EMAIL = "support@flexdrive.ge"
RETURN_EMAIL = "return@flexdrive.ge"
INFO_EMAIL = "info@flexdrive.ge"
PHONE_DISPLAY = "+995 557 10 61 04"
PHONE_TEL = "+995557106104"
IDENTIFICATION_CODE = "406559040"


CONTENT_REPLACEMENTS = (
    ("საიდენტიფიკაციო კოდი: 000000000", f"საიდენტიფიკაციო კოდი: {IDENTIFICATION_CODE}"),
    ("იურიდიული მისამართი: საქართველო, თბილისი, დასაზუსტებელია", "იურიდიული მისამართი: თბილისი, საქართველო"),
    ("მხარდაჭერა: <a href=\"mailto:support@flexdrive.ge\">support@flexdrive.ge</a>", f"მხარდაჭერა: <a href=\"mailto:{SUPPORT_EMAIL}\">{SUPPORT_EMAIL}</a>"),
    ("დაბრუნების მოთხოვნები: <a href=\"mailto:returns@flexdrive.ge\">returns@flexdrive.ge</a>", f"დაბრუნების მოთხოვნები: <a href=\"mailto:{RETURN_EMAIL}\">{RETURN_EMAIL}</a>"),
    ("დაბრუნების მოთხოვნა იგზავნება: <a href=\"mailto:returns@flexdrive.ge\">returns@flexdrive.ge</a>", f"დაბრუნების მოთხოვნა იგზავნება: <a href=\"mailto:{RETURN_EMAIL}\">{RETURN_EMAIL}</a>"),
    ("დაბრუნებასთან დაკავშირებული შეკითხვებისთვის გამოიყენეთ <a href=\"mailto:returns@flexdrive.ge\">returns@flexdrive.ge</a>", f"დაბრუნებასთან დაკავშირებული შეკითხვებისთვის გამოიყენეთ <a href=\"mailto:{RETURN_EMAIL}\">{RETURN_EMAIL}</a>"),
    ("<a href=\"mailto:returns@flexdrive.ge\">returns@flexdrive.ge</a>", f"<a href=\"mailto:{RETURN_EMAIL}\">{RETURN_EMAIL}</a>"),
    ("returns@flexdrive.ge", RETURN_EMAIL),
    ("<a href=\"mailto:privacy@flexdrive.ge\">privacy@flexdrive.ge</a>", f"<a href=\"mailto:{INFO_EMAIL}\">{INFO_EMAIL}</a>"),
    ("privacy@flexdrive.ge", INFO_EMAIL),
    ("<a href=\"mailto:legal@flexdrive.ge\">legal@flexdrive.ge</a>", f"<a href=\"mailto:{INFO_EMAIL}\">{INFO_EMAIL}</a>"),
    ("legal@flexdrive.ge", INFO_EMAIL),
    ("legal@Flexdrive.ge", INFO_EMAIL),
    ("<a href=\"tel:+995000000000\">+995 000 00 00 00</a>", f"<a href=\"tel:{PHONE_TEL}\">{PHONE_DISPLAY}</a>"),
    ("<a href=\"tel:+995555010203\">+995 555 01 02 03</a>", f"<a href=\"tel:{PHONE_TEL}\">{PHONE_DISPLAY}</a>"),
    ("+995 000 00 00 00", PHONE_DISPLAY),
    ("+995 555 01 02 03", PHONE_DISPLAY),
    (
        "მოვაჭრის იურიდიული მონაცემები რეგისტრაციის დასრულებისთანავე განახლდება რეალური ინფორმაციით. ამ ეტაპზე გვერდზე მითითებული მონაცემები გამოიყენება დროებით, ტექსტის სტრუქტურისა და პროცესების მოსამზადებლად.",
        "მოვაჭრის ძირითადი იურიდიული და საკონტაქტო მონაცემები მოცემულია ქვემოთ.",
    ),
    (
        "FlexDrive-ის ვებგვერდზე პერსონალური მონაცემების დამუშავებაზე პასუხისმგებელია შპს FlexDrive, საიდენტიფიკაციო კოდი: 000000000. ეს მონაცემები დროებითი placeholder-ია და კომპანიის რეგისტრაციის შემდეგ რეალური ინფორმაციით ჩანაცვლდება.",
        f"FlexDrive-ის ვებგვერდზე პერსონალური მონაცემების დამუშავებაზე პასუხისმგებელია შპს FlexDrive, საიდენტიფიკაციო კოდი: {IDENTIFICATION_CODE}.",
    ),
    ("დროებითი placeholder-ია და კომპანიის რეგისტრაციის შემდეგ რეალური ინფორმაციით ჩანაცვლდება", "განახლებულია FlexDrive-ის მოქმედი საკონტაქტო ინფორმაციით"),
    ("placeholder", "მონაცემი"),
)


REVERSE_REPLACEMENTS = tuple((new, old) for old, new in reversed(CONTENT_REPLACEMENTS))


def apply_replacements_to_text(value, replacements):
    next_value = value
    for old, new in replacements:
        next_value = next_value.replace(old, new)
    return next_value


def update_content_items(apps, replacements):
    ContentItem = apps.get_model("pages", "ContentItem")

    for item in ContentItem.objects.all():
        changed_fields = []

        for field_name in ("title", "description", "editor"):
            current_value = getattr(item, field_name)
            if not current_value:
                continue

            next_value = apply_replacements_to_text(current_value, replacements)
            if next_value != current_value:
                setattr(item, field_name, next_value)
                changed_fields.append(field_name)

        if changed_fields:
            item.save(update_fields=[*changed_fields, "updated_at"])


def update_footer_settings(apps, *, reverse=False):
    FooterSettings = apps.get_model("pages", "FooterSettings")

    defaults = {
        "email": SUPPORT_EMAIL,
        "phone": PHONE_DISPLAY,
    }
    if reverse:
        defaults = {
            "email": SUPPORT_EMAIL,
            "phone": "+995 5XX XX XX XX",
        }

    FooterSettings.objects.update_or_create(pk=1, defaults=defaults)


def replace_placeholder_legal_contact_info(apps, schema_editor):
    update_content_items(apps, CONTENT_REPLACEMENTS)
    update_footer_settings(apps, reverse=False)


def revert_placeholder_legal_contact_info(apps, schema_editor):
    update_content_items(apps, REVERSE_REPLACEMENTS)
    update_footer_settings(apps, reverse=True)


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0068_seed_vehicle_brand_swiper_component"),
    ]

    operations = [
        migrations.RunPython(
            replace_placeholder_legal_contact_info,
            revert_placeholder_legal_contact_info,
        ),
    ]
