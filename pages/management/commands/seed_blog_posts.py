import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from pages.models import BlogPost, BlogStatus, Content, ContentItem, Page


TITLE_PARTS = (
    "როგორ შევინარჩუნოთ მანქანა",
    "საბურავების მოვლა ზამთარში",
    "ძრავის ზეთის სწორად შერჩევა",
    "როგორ გავზარდოთ უსაფრთხოება გზაზე",
    "სალონის მოვლის მარტივი რჩევები",
    "მუხრუჭების სისტემის კონტროლი",
    "ელექტრო სისტემის დიაგნოსტიკა",
    "ფარების გასწორება და ხილვადობა",
    "როგორ ავიცილოთ ზედმეტი ხარჯი",
    "ქალაქში ეკონომიური მართვის ტექნიკა",
)

AUTHOR_NAMES = (
    "ნინო გაბაშვილი",
    "გიორგი ბერიძე",
    "ანა კალანდაძე",
    "ლევან ქავთარაძე",
    "მარიამ ქარჩავა",
)

AUTHOR_ROLES = (
    "ავტომოყვარული",
    "მექანიკოსი",
    "ტექ-ბლოგერი",
    "უსაფრთხოების სპეციალისტი",
)

CATEGORIES = (
    "მოვლა",
    "უსაფრთხოება",
    "დიაგნოსტიკა",
    "ეკონომია",
    "პრაქტიკული რჩევები",
)

TAG_GROUPS = (
    "მანქანა, მოვლა, რჩევები",
    "უსაფრთხოება, საბურავი, გზა",
    "ძრავი, ზეთი, სერვისი",
    "ელექტროობა, დიაგნოსტიკა, შემოწმება",
    "სალონი, კომფორტი, წმენდა",
)

EXCERPT_TEMPLATES = (
    "ამ სტატიაში მოკლედ განვიხილავთ პრაქტიკულ ნაბიჯებს, რომლებიც დაგეხმარება ავტომობილის უკეთ შენარჩუნებაში.",
    "თუ გინდა ავტომობილი სტაბილურად მუშაობდეს, ეს სწრაფი რჩევები ყოველდღიურ მოვლაში ნამდვილად გამოგადგება.",
    "ქვემოთ ნახავ კონკრეტულ რეკომენდაციებს, რომ თავიდან აიცილო გავრცელებული შეცდომები და ზედმეტი ხარჯი.",
    "სტატია აერთიანებს მოკლე, გასაგებ და პრაქტიკულ ინსტრუქციებს, რომელიც რეალურ გამოყენებაში მუშაობს.",
)

EDITOR_BLOCKS = (
    "<p>პირველი ნაბიჯია რეგულარული ვიზუალური შემოწმება. მცირე პრობლემის დროულად აღმოჩენა მნიშვნელოვნად ამცირებს მომავალ ხარჯს.</p>",
    "<p>ყურადღება მიაქციე ზეთის დონეს, საბურავის წნევას და მუხრუჭების რეაგირებას. ეს სამი პუნქტი ყველაზე ხშირად ახდენს გავლენას უსაფრთხოებაზე.</p>",
    "<p>ქალაქურ რეჟიმში ხშირი გაჩერება-გაშვება დეტალებს უფრო სწრაფად ცვეთს, ამიტომ სერვისის ინტერვალი ინდივიდუალურად მოარგე.</p>",
    "<p>თუ უცნაური ხმა ან ვიბრაცია გამოჩნდა, დიაგნოსტიკა არ გადადო. ადრეული რეაგირება თითქმის ყოველთვის იაფია.</p>",
)


class Command(BaseCommand):
    help = "Generate fake blog posts (ContentItem + BlogPost) for development/testing."

    fake_slug_prefix = "fake-blog-post-"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=50,
            help="Number of fake blog posts to create (default: 50).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously generated fake blog posts before seeding.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for repeatable generation (default: 42).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        reset = options["reset"]
        seed = options["seed"]

        if count < 0:
            raise CommandError("--count must be greater than or equal to 0.")

        rng = random.Random(seed)

        blog_content = self._ensure_blog_content()
        blogs_page = self._resolve_blogs_page()

        if reset:
            deleted = self._delete_old_fake_posts()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} old fake blog post(s)."))

        start_position = (
            ContentItem.objects.filter(content=blog_content).order_by("-position", "-id").values_list("position", flat=True).first()
            or 0
        )

        created_content_items = 0
        created_blog_posts = 0
        now = timezone.now()

        for index in range(count):
            position = start_position + index + 1
            title = f"{rng.choice(TITLE_PARTS)} #{index + 1}"
            slug = self._build_unique_slug(f"{self.fake_slug_prefix}{index + 1}-{title}")

            editor_html = "".join(rng.sample(EDITOR_BLOCKS, k=2))
            created_at = now - timedelta(days=index)

            item = ContentItem(
                content=blog_content,
                title=title,
                description=rng.choice(EXCERPT_TEMPLATES),
                editor=editor_html,
                slug=slug,
                singlePageRoute=blogs_page,
                content_type="blogs",
                position=position,
            )
            item.save()
            created_content_items += 1

            BlogPost.objects.create(
                content_item=item,
                excerpt=rng.choice(EXCERPT_TEMPLATES),
                read_time_minutes=rng.randint(3, 10),
                author_name=rng.choice(AUTHOR_NAMES),
                author_role=rng.choice(AUTHOR_ROLES),
                category=rng.choice(CATEGORIES),
                tags=rng.choice(TAG_GROUPS),
                status=BlogStatus.PUBLISHED,
                published_at=created_at,
                is_featured=index < 8,
            )
            created_blog_posts += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Blog seed completed. "
                f"Created ContentItems: {created_content_items}, BlogPosts: {created_blog_posts}."
            )
        )

    @staticmethod
    def _ensure_blog_content():
        content, _ = Content.objects.get_or_create(name="bloglist")
        return content

    @staticmethod
    def _resolve_blogs_page():
        blogs_page = Page.objects.filter(slug="blogs").first()
        if blogs_page:
            return blogs_page
        return Page.objects.filter(slug="main").first()

    def _build_unique_slug(self, source):
        base = slugify(source)[:220] or f"{self.fake_slug_prefix}{timezone.now().timestamp():.0f}"
        candidate = base
        suffix = 2
        while ContentItem.objects.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _delete_old_fake_posts(self):
        fake_items = ContentItem.objects.filter(slug__startswith=self.fake_slug_prefix)
        ids = list(fake_items.values_list("id", flat=True))
        if not ids:
            return 0
        BlogPost.objects.filter(content_item_id__in=ids).delete()
        deleted_count, _ = ContentItem.objects.filter(id__in=ids).delete()
        return deleted_count
