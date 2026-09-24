from django.db import migrations
from django.db.models import Max


CONTENT_NAME = "privacy_policy_sections"
SECTION_SLUG = "account-data-deletion"
SECTION_TITLE = "ანგარიშისა და მონაცემების წაშლა"
SECTION_HTML = """
<p>FlexDrive-ის ანგარიშის გაუქმება შეგიძლიათ პირადი პროფილიდან. ეს წესი ვრცელდება ელფოსტით, Google-ით და Facebook-ით შექმნილ ანგარიშებზე.</p>
<ol>
  <li>შედით FlexDrive-ზე იმ მეთოდით, რომელსაც თქვენი ანგარიშისთვის იყენებთ.</li>
  <li>გახსენით <a href="/profile">პირადი პროფილი</a> და მოძებნეთ სექცია „ანგარიშის გაუქმება“.</li>
  <li>დააჭირეთ „ანგარიშის გაუქმება“-ს. თუ ანგარიშისთვის პაროლი გაქვთ დაყენებული, შეიყვანეთ მიმდინარე პაროლი. მხოლოდ Google-ით ან Facebook-ით შექმნილი ანგარიშისთვის, რომელსაც პაროლი არ აქვს დაყენებული, პაროლის შეყვანა საჭირო არ არის.</li>
  <li>დაადასტურეთ ანგარიშის გაუქმება. ეს მოქმედება შეუქცევადია.</li>
</ol>
<p>გაუქმებისას იშლება ანგარიში, პროფილი, ანგარიშთან დაკავშირებული კალათა და სურვილების სია, ასევე Google-ისა და Facebook-ის მიბმის ჩანაწერები. Facebook-ის მიბმის ჩანაწერთან ერთად იშლება მასში შენახული იდენტიფიკატორი, ელფოსტა, სახელი და პროფილის სურათის ბმული. თქვენი Google-ის ან Facebook-ის ანგარიში ამ მოქმედებით არ იშლება.</p>
<p>შეკვეთების ჩანაწერები რჩება ანგარიშისგან განცალკევებული, ხოლო მათ ძირითად ველებში პირადი და საკონტაქტო მონაცემები იწმინდება. ანგარიშის გაუქმება არ ნიშნავს შეკვეთის ავტომატურ გაუქმებას ან თანხის დაბრუნებას. შეკვეთებთან, გადახდებთან, მიწოდებასთან და მხარდაჭერასთან დაკავშირებული სხვა ჩანაწერები შეიძლება დარჩეს; მათი შენახვისა და წაშლის საკითხები აღწერილია ამ პოლიტიკის სექციაში „შენახვა, უსაფრთხოება და უფლებები“.</p>
<p>თუ ანგარიშში ვეღარ შედიხართ ან გსურთ მონაცემების წაშლის მოთხოვნის გამოგზავნა, მოგვწერეთ <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a>-ზე თემით „მონაცემების წაშლა“. მიუთითეთ FlexDrive-ის ანგარიშის ელფოსტა და, თუ Facebook-ით სარგებლობდით, აღნიშნეთ ეს წერილში. პაროლი არ გამოგზავნოთ. მოთხოვნის შესრულებამდე შეიძლება დაგვჭირდეს ანგარიშის მფლობელობის დადასტურება; პასუხში გაცნობებთ მოთხოვნის შედეგსა და მონაცემებს, რომლებიც დარჩება, მათი შენახვის მიზეზთან ერთად.</p>
""".strip()


def add_deletion_instructions(apps, schema_editor):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    alias = schema_editor.connection.alias
    content = Content.objects.using(alias).get(name=CONTENT_NAME)
    items = ContentItem.objects.using(alias).filter(content=content)
    # Append without replacing any existing policy sections or admin edits.
    if items.filter(slug=SECTION_SLUG).exists():
        return
    position = (items.aggregate(last=Max("position"))["last"] or 0) + 1
    items.create(
        content=content,
        slug=SECTION_SLUG,
        position=position,
        content_type="policy_section",
        title=SECTION_TITLE,
        description="როგორ გააუქმოთ FlexDrive-ის ანგარიში ან მოითხოვოთ თქვენი მონაცემების წაშლა, მათ შორის Facebook-ით შესვლისას მიღებული მონაცემების.",
        editor=SECTION_HTML,
        icon_svg=None,
    )


class Migration(migrations.Migration):
    dependencies = [("pages", "0076_sync_staging_cms_texts")]

    operations = [
        migrations.RunPython(add_deletion_instructions, migrations.RunPython.noop),
    ]
