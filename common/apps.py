from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common"

    def ready(self):
        # Register JPEG XL before Django validates uploads or opens source images.
        # Existing image processing continues to generate WebP output.
        import pillow_jxl  # noqa: F401
