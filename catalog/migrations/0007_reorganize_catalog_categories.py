from django.db import migrations
from django.db.models import Q


def _category_by_slug(Category, slug):
    return Category.objects.filter(slug=slug).first()


def _move_products(Product, source, target, query):
    if not source or not target:
        return

    Product.objects.filter(category=source).filter(query).update(category=target)


def reorganize_catalog_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")

    visual = _category_by_slug(Category, "bamperebi-da-tskhaurebi")
    lighting = _category_by_slug(Category, "ganateba")
    uncategorized = _category_by_slug(Category, "dasakategorizebeli")
    suspension = _category_by_slug(Category, "savali-natsilebi")
    engine = _category_by_slug(Category, "dzravi-zetebi-da-filtrebi")
    cooling = _category_by_slug(Category, "radiatorebi-da-gagrileba")
    electrical = _category_by_slug(Category, "eleqtrooba")

    if visual:
        visual.name = "ვიზუალის ნაწილები"
        visual.save(update_fields=["name", "updated_at"])

    if lighting:
        lighting.name = "ფარები და განათება"
        lighting.save(update_fields=["name", "updated_at"])

    _move_products(
        Product,
        lighting,
        visual,
        Q(name__icontains="სანისლე") & Q(name__icontains="ბუდ"),
    )
    _move_products(Product, lighting, visual, Q(name__icontains="სალასკ"))

    _move_products(
        Product,
        uncategorized,
        suspension,
        Q(name__icontains="გიტარ")
        | Q(name__icontains="პადმატორნ")
        | Q(name__icontains="უდარნ")
        | Q(name__icontains="ნაკანეჩნიკ")
        | Q(name__icontains="წერო")
        | Q(name__icontains="ტულკ")
        | Q(name__icontains="ცაბკ")
        | Q(name__icontains="სუხო")
        | Q(name__icontains="რეზინ")
        | Q(name__icontains="ხუნდ")
        | Q(name__icontains="მთვარა")
        | Q(name__icontains="ნახევარმთვარე"),
    )

    _move_products(
        Product,
        uncategorized,
        engine,
        Q(name__icontains="საქშენ")
        | Q(name__icontains="მატორის დამცავ")
        | Q(name__icontains="დროსელ")
        | Q(name__icontains="მატორის პრაკლადკ")
        | Q(name__icontains="კარობკის კარტერ")
        | Q(name__icontains="მატორის კარტერ")
        | Q(name__icontains="წყლის მილ")
        | Q(name__icontains="ხორთუმ")
        | Q(name__icontains="წყლის პომპ")
        | Q(name__icontains="ტემპერატურის დაჩიკ")
        | Q(name__icontains="კოლექტორ"),
    )

    _move_products(Product, uncategorized, lighting, Q(name__icontains="ამრეკლ"))

    _move_products(
        Product,
        uncategorized,
        cooling,
        Q(name__icontains="ვინტილიატორის ზბორ")
        | Q(name__icontains="ჟალუზ")
        | Q(name__icontains="დიფუზორ")
        | Q(name__icontains="რაშირიწელ")
        | Q(name__icontains="რაშირიტელ"),
    )

    _move_products(
        Product,
        uncategorized,
        electrical,
        Q(name__icontains="რულის შლეიფ") | Q(name__icontains="მცველების ყუთ"),
    )

    if uncategorized and visual:
        Product.objects.filter(category=uncategorized).update(category=visual)
        uncategorized.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_category_markup_percent_and_more"),
    ]

    operations = [
        migrations.RunPython(reorganize_catalog_categories, migrations.RunPython.noop),
    ]
