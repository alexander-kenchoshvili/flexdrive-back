from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from pages.models import Content, ContentItem


class DeliveryCutoffCopyTests(TestCase):
    def test_only_delivery_times_change_and_admin_copy_is_preserved(self):
        targets = []
        for name, kind in (("delivery_sections", "delivery_section"), ("terms_sections", "terms_section")):
            content, _ = Content.objects.get_or_create(name=name)
            targets.append(ContentItem.objects.create(
                content=content, content_type=kind, title="Custom delivery title",
                description="Admin copy: 14:00 before; 14:00 after; 4-5 days.",
                editor="<p>Saturday 14:00; Sunday unchanged.</p>",
            ))
        other_content, _ = Content.objects.get_or_create(name="unrelated_cutoff_copy")
        other = ContentItem.objects.create(content=other_content, description="14:00", editor="<p>14:00</p>")
        migration = import_module("pages.migrations.0079_delivery_cutoff_1300")
        migration.update_delivery_cutoff(apps, SimpleNamespace(connection=connection))
        for item in targets:
            item.refresh_from_db()
            self.assertEqual(item.title, "Custom delivery title")
            self.assertEqual(item.description, "Admin copy: 13:00 before; 13:00 after; 4-5 days.")
            self.assertEqual(item.editor, "<p>Saturday 13:00; Sunday unchanged.</p>")
        other.refresh_from_db()
        self.assertEqual(other.description, "14:00")
        self.assertEqual(other.editor, "<p>14:00</p>")
        updated_dates = list(ContentItem.objects.filter(pk__in=[item.pk for item in targets]).values_list("updated_at", flat=True))
        migration.update_delivery_cutoff(apps, SimpleNamespace(connection=connection))
        self.assertEqual(list(ContentItem.objects.filter(pk__in=[item.pk for item in targets]).values_list("updated_at", flat=True)), updated_dates)
