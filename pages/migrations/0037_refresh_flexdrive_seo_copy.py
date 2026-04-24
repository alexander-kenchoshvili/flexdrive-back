from django.db import migrations


SITE_SETTINGS_DEFAULTS = {
    "site_name": "FlexDrive",
    "default_seo_title": "პრემიუმ ხარისხის ავტონაწილების ონლაინ მაღაზია საქართველოში",
    "default_seo_description": (
        "შეიძინე ხარისხიანი ტაივანური ანალოგი ავტონაწილები FlexDrive-ზე. "
        "ონლაინ შეკვეთა, ნაღდი ან ბარათით გადახდა, ონლაინ განვადება და 0% ნაწილ-ნაწილ გადახდა."
    ),
}


PAGE_SEO_BY_SLUG = {
    "main": {
        "seo_title": "პრემიუმ ხარისხის ავტონაწილების ონლაინ მაღაზია საქართველოში",
        "seo_description": (
            "შეიძინე ხარისხიანი ტაივანური ანალოგი ავტონაწილები FlexDrive-ზე. "
            "ონლაინ შეკვეთა, ნაღდი ან ბარათით გადახდა, ონლაინ განვადება და 0% ნაწილ-ნაწილ გადახდა."
        ),
    },
    "contact": {
        "seo_title": "კონტაქტი | FlexDrive",
        "seo_description": (
            "დაუკავშირდი FlexDrive-ს შეკვეთის, ავტონაწილის, მიწოდების ან დაბრუნების საკითხებზე. "
            "საკონტაქტო ფორმა, არხები და სასარგებლო ბმულები ერთ გვერდზე."
        ),
    },
    "faq": {
        "seo_title": "ხშირად დასმული კითხვები | FlexDrive",
        "seo_description": (
            "FlexDrive-ის ხშირად დასმული კითხვები ავტონაწილებზე, შეკვეთაზე, "
            "მიწოდებასა და გადახდის პირობებზე."
        ),
    },
    "delivery": {
        "seo_title": "მიწოდების პირობები | FlexDrive",
        "seo_description": (
            "გაიგე როგორ მუშაობს FlexDrive-ის მიწოდება: შეკვეთის დამუშავება, "
            "თბილისში და რეგიონებში მიწოდების ვადები და შეკვეთის სტატუსთან დაკავშირებული მხარდაჭერა."
        ),
    },
    "payment-methods": {
        "seo_title": "გადახდის მეთოდები | FlexDrive",
        "seo_description": (
            "გაიგე რომელი გადახდის მეთოდებია ხელმისაწვდომი FlexDrive-ზე: "
            "ნაღდი ანგარიშსწორება, ბარათით გადახდა, ონლაინ განვადება და 0% ნაწილ-ნაწილ გადახდა."
        ),
    },
    "returns": {
        "seo_title": "დაბრუნება და თანხის დაბრუნება | FlexDrive",
        "seo_description": (
            "გაიგე როგორ მუშაობს FlexDrive-ზე დაბრუნება: მოთხოვნის გაგზავნა, დაბრუნების პირობები, "
            "დეფექტიანი ან არასწორი ნაწილის პროცესი და თანხის დაბრუნების ვადები."
        ),
    },
    "privacy-policy": {
        "seo_title": "კონფიდენციალურობის პოლიტიკა | FlexDrive",
        "seo_description": (
            "გაიგეთ რა მონაცემებს აგროვებს FlexDrive, როგორ ვიყენებთ მათ და როგორ შეგიძლიათ "
            "მოითხოვოთ თქვენი ინფორმაციის მართვა, განახლება ან წაშლა."
        ),
    },
    "terms": {
        "seo_title": "წესები და პირობები | FlexDrive",
        "seo_description": (
            "გაიგე რა წესები ვრცელდება FlexDrive-ის საიტის გამოყენებაზე, შეკვეთებზე, "
            "გადახდაზე, მიწოდებასა და დაბრუნების ძირითად პირობებზე."
        ),
    },
}


def refresh_flexdrive_seo_copy(apps, schema_editor):
    SiteSettings = apps.get_model("pages", "SiteSettings")
    Page = apps.get_model("pages", "Page")

    SiteSettings.objects.update_or_create(pk=1, defaults=SITE_SETTINGS_DEFAULTS)

    for slug, values in PAGE_SEO_BY_SLUG.items():
        page = Page.objects.filter(slug=slug).first()
        if not page:
            continue

        update_fields = []
        for field_name, field_value in values.items():
            if getattr(page, field_name) != field_value:
                setattr(page, field_name, field_value)
                update_fields.append(field_name)

        if update_fields:
            page.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0036_sitesettings_and_seo_expansion"),
    ]

    operations = [
        migrations.RunPython(refresh_flexdrive_seo_copy, migrations.RunPython.noop),
    ]
