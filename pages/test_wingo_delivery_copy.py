import importlib
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .models import Content, ContentItem


migration = importlib.import_module("pages.migrations.0083_wingo_delivery_choices_copy")
complete = importlib.import_module("pages.migrations.0084_wingo_delivery_copy_complete")


class WingoDeliveryCopyTests(TestCase):
    def test_only_known_shipping_text_changes_and_repeating_is_a_noop(self):
        content, _ = Content.objects.get_or_create(name="delivery_sections")
        row = ContentItem.objects.create(content=content, content_type="delivery_section", title="Test shipping",
            editor=f"<p>{migration.OLD_TIMING}</p><p>შეუცვლელი ტექსტი</p>")
        other = ContentItem.objects.create(content=content, content_type="delivery_section", title="Other",
                                           editor="<p>მაღაზიის სამუშაო დრო 13:00-მდეა.</p>")
        original_other = ContentItem.objects.values().get(pk=other.pk)
        migration.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        row.refresh_from_db()
        self.assertIn(migration.NEW_TIMING, row.editor)
        self.assertIn("შეუცვლელი ტექსტი", row.editor)
        self.assertNotIn(migration.OLD_TIMING, row.editor)
        first = ContentItem.objects.values().get(pk=row.pk)
        migration.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        self.assertEqual(first, ContentItem.objects.values().get(pk=row.pk))
        self.assertEqual(original_other, ContentItem.objects.values().get(pk=other.pk))

    def test_shipping_faq_is_updated_without_touching_other_answers(self):
        content, _ = Content.objects.get_or_create(name="faq_questions")
        shipping = ContentItem.objects.create(content=content, content_type="faq",
            title="რა ღირს მიწოდება და რამდენ ხანში მივიღებ შეკვეთას?", description="ძველი მიწოდება 13:00-მდე")
        other = ContentItem.objects.create(content=content, content_type="faq", title="სხვა კითხვა", description="სხვა პასუხი")
        before = ContentItem.objects.values().get(pk=other.pk)
        migration.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        shipping.refresh_from_db()
        self.assertEqual(shipping.description, migration.NEW_FAQ)
        self.assertEqual(before, ContentItem.objects.values().get(pk=other.pk))


class WingoCompleteDeliveryCopyTests(TestCase):
    def test_public_delivery_and_terms_responses_have_no_obsolete_1300_promise(self):
        import json
        for slug in ("delivery", "terms"):
            response = self.client.post(reverse("get-current-content"), {"slug": slug}, content_type="application/json")
            self.assertEqual(response.status_code, 200)
            text = json.dumps(response.json(), ensure_ascii=False)
            self.assertIn("1–2 სამუშაო", text)
            self.assertIn("12:30", text)
            self.assertIn("მომდევნო სამუშაო დღეს", text)
            self.assertNotIn("13:00", text)
            self.assertNotIn("ორშაბათიდან შაბათის", text)

    def test_both_visible_descriptions_and_rich_text_are_updated_in_all_known_variants(self):
        for name, kind in (("delivery_sections", "delivery_section"), ("terms_sections", "terms_section")):
            content, _ = Content.objects.get_or_create(name=name)
            for old in (complete.OLD_SHORT, migration.OLD_TIMING, migration.NEW_TIMING,
                        complete.OLD_SHORT.replace("13:00", "14:00")):
                row = ContentItem.objects.create(content=content, content_type=kind,
                    description=old + " რეგიონებში — 3-5 სამუშაო დღე.",
                    editor=f"<p>{old}</p><p>შეუცვლელი პირობა</p>")
                complete.update_delivery_copy(apps, SimpleNamespace(connection=connection))
                row.refresh_from_db()
                self.assertIn(complete.NEW_TIMING, row.description)
                self.assertIn(complete.NEW_TIMING, row.editor)
                self.assertIn("რეგიონებში — 3-5", row.description)
                self.assertIn("შეუცვლელი პირობა", row.editor)
                self.assertNotIn("13:00", row.description)
                self.assertNotIn("14:00", row.description)
            intro = ContentItem.objects.create(content=content, content_type=kind,
                description=complete.OLD_INTRO, editor=f"<p>{complete.OLD_DETAIL_INTRO}</p>")
            complete.update_delivery_copy(apps, SimpleNamespace(connection=connection))
            intro.refresh_from_db()
            self.assertEqual(intro.description, complete.NEW_INTRO)
            self.assertEqual(intro.editor, f"<p>{complete.NEW_INTRO}</p>")

    def test_complete_copy_is_idempotent_and_preserves_unrelated_text(self):
        content, _ = Content.objects.get_or_create(name="delivery_sections")
        row = ContentItem.objects.create(content=content, content_type="delivery_section",
            description="მაღაზიის სამუშაო დრო 13:00-მდეა.", editor="<p>სხვა პირობა</p>")
        before = ContentItem.objects.values().get(pk=row.pk)
        complete.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        self.assertEqual(before, ContentItem.objects.values().get(pk=row.pk))
        snapshot = list(ContentItem.objects.order_by("pk").values())
        complete.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        self.assertEqual(snapshot, list(ContentItem.objects.order_by("pk").values()))

    def test_shipping_faq_and_intro_cover_both_services_and_nonworking_days(self):
        content, _ = Content.objects.get_or_create(name="faq_questions")
        row = ContentItem.objects.create(content=content, content_type="faq",
            title="რა ღირს მიწოდება და რამდენ ხანში მივიღებ შეკვეთას?",
            description=migration.NEW_FAQ, editor=f"<p>{migration.NEW_FAQ}</p>")
        complete.update_delivery_copy(apps, SimpleNamespace(connection=connection))
        row.refresh_from_db()
        for field in (row.description, row.editor):
            self.assertIn("1–2 სამუშაო", field)
            self.assertIn("12:30", field)
            self.assertIn("მომდევნო სამუშაო დღეს", field)
            self.assertIn("შაბათსა და კვირას", field)
            self.assertIn("3–5 სამუშაო", field)
