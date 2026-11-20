import importlib
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from .models import ContentItem


class WaybillPrivacyNoticeTests(TestCase):
    def test_append_preserves_existing_policy_and_admin_edits(self):
        migration = importlib.import_module("pages.migrations.0087_personal_number_waybill_notice")
        section = ContentItem.objects.get(content__name="privacy_policy_sections", slug=migration.SECTION_SLUG)
        content = section.content
        section.delete()
        existing = list(content.items.order_by("pk").values())
        migration.add_waybill_notice(apps, SimpleNamespace(connection=connection))
        section = ContentItem.objects.get(content=content, slug=migration.SECTION_SLUG)
        self.assertIn("11-ნიშნა", section.editor)
        self.assertIn("ზედნადების მოსამზადებლად", section.editor)
        self.assertEqual(list(content.items.exclude(pk=section.pk).order_by("pk").values()), existing)
        section.editor = "Preserved admin edit"
        section.save(update_fields=["editor"])
        migration.add_waybill_notice(apps, SimpleNamespace(connection=connection))
        section.refresh_from_db()
        self.assertEqual(section.editor, "Preserved admin edit")
        self.assertEqual(content.items.filter(slug=migration.SECTION_SLUG).count(), 1)
