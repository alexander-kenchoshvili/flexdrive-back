from django.db import models

from common.image_processing import build_conversion_update_fields, convert_image_field_to_webp


class WebPImageMixin(models.Model):
    image_desktop = models.ImageField(upload_to="", blank=True, null=True)
    image_tablet = models.ImageField(upload_to="", blank=True, null=True)
    image_mobile = models.ImageField(upload_to="", blank=True, null=True)

    class Meta:
        abstract = True

    def get_upload_path(self, field_name):
        if self.__class__.__name__ == "ContentItem":
            return "content_items/"
        if self.__class__.__name__ == "Component":
            return "components/"
        return ""

    def save(self, *args, **kwargs):
        for field_name in ("image_desktop", "image_tablet", "image_mobile"):
            field = self._meta.get_field(field_name)
            field.upload_to = self.get_upload_path(field_name)

        tracked_fields = {"image_desktop", "image_tablet", "image_mobile"}
        update_fields = kwargs.get("update_fields")

        super().save(*args, **kwargs)

        if update_fields is not None and tracked_fields.isdisjoint(set(update_fields)):
            return

        converted_fields = []
        for field_name in ("image_desktop", "image_tablet", "image_mobile"):
            image_field = getattr(self, field_name)
            if convert_image_field_to_webp(image_field, quality=80):
                converted_fields.append(field_name)

        if converted_fields:
            super().save(update_fields=build_conversion_update_fields(self, converted_fields))
