from django.test import SimpleTestCase

from pages.svg_safety import sanitize_editor_html, sanitize_svg_markup


class ContentSanitizationTests(SimpleTestCase):
    def test_rich_text_removes_executable_markup(self):
        value = '<p onclick="alert(1)">Safe</p><script>alert(1)</script>'

        sanitized = sanitize_editor_html(value)

        self.assertEqual(sanitized, "<p>Safe</p>alert(1)")

    def test_svg_keeps_shapes_and_removes_executable_markup(self):
        value = (
            '<svg viewBox="0 0 10 10" onload="alert(1)">'
            '<script>alert(1)</script><path d="M0 0h10v10z" fill="currentColor"/>'
            "</svg>"
        )

        sanitized = sanitize_svg_markup(value)

        self.assertIn('viewBox="0 0 10 10"', sanitized)
        self.assertIn("<path", sanitized)
        self.assertNotIn("script", sanitized)
        self.assertNotIn("onload", sanitized)
