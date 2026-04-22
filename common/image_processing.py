import os
from io import BytesIO
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

try:
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLING_LANCZOS = Image.LANCZOS


def _basename_from_storage_name(name):
    raw_name = str(name or "")
    parsed = urlparse(raw_name)
    if parsed.scheme and parsed.netloc:
        raw_name = parsed.path
    return os.path.basename(raw_name)


def build_conversion_update_fields(instance, converted_fields):
    update_fields = set(converted_fields)
    if any(field.name == "updated_at" for field in instance._meta.concrete_fields):
        update_fields.add("updated_at")
    return sorted(update_fields)


def _storage_points_to_same_asset(storage, first_name, second_name):
    identifier = getattr(storage, "identifies_same_asset", None)
    if not callable(identifier):
        return False
    return bool(identifier(first_name, second_name))


def delete_replaced_storage_file(storage, original_name, current_name):
    if not original_name or original_name == current_name:
        return

    if _storage_points_to_same_asset(storage, original_name, current_name):
        return

    try:
        storage.delete(original_name)
    except Exception:
        # Missing old files should not block model saves.
        return


def convert_image_field_to_webp(image_field, *, quality=85):
    if not image_field:
        return False

    original_name = str(image_field.name or "")
    if not original_name or original_name.lower().endswith(".webp"):
        return False

    image_field.open("rb")
    try:
        with Image.open(image_field) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

            output = BytesIO()
            img.save(output, format="WEBP", quality=quality)
            output.seek(0)
    finally:
        image_field.close()

    original_basename = _basename_from_storage_name(original_name)
    webp_filename = f"{os.path.splitext(original_basename)[0]}.webp"
    image_field.save(webp_filename, ContentFile(output.read()), save=False)
    delete_replaced_storage_file(image_field.storage, original_name, image_field.name)
    return True


def build_contained_webp_content(
    source_image_field,
    *,
    size,
    background_color=(255, 255, 255),
    quality=85,
):
    if not source_image_field:
        return None

    width, height = size
    source_image_field.open("rb")
    try:
        with Image.open(source_image_field) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

            source = img.convert("RGBA")
            source.thumbnail((width, height), RESAMPLING_LANCZOS)

            canvas = Image.new("RGBA", (width, height), (*background_color, 255))
            offset = (
                max((width - source.width) // 2, 0),
                max((height - source.height) // 2, 0),
            )
            canvas.alpha_composite(source, offset)

            output = BytesIO()
            canvas.convert("RGB").save(output, format="WEBP", quality=quality)
            output.seek(0)
            return output.read()
    finally:
        source_image_field.close()


def build_resized_webp_content(
    source_image_field,
    *,
    max_size,
    quality=85,
):
    if not source_image_field:
        return None

    max_width, max_height = max_size
    source_image_field.open("rb")
    try:
        with Image.open(source_image_field) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

            source = img.convert("RGBA")
            source.thumbnail((max_width, max_height), RESAMPLING_LANCZOS)

            output = BytesIO()
            source.convert("RGB").save(output, format="WEBP", quality=quality)
            output.seek(0)
            return output.read()
    finally:
        source_image_field.close()


def save_generated_webp_to_field(
    target_field,
    source_name,
    content,
    *,
    suffix,
):
    if content is None:
        return False

    current_name = str(target_field.name or "")
    original_basename = _basename_from_storage_name(source_name)
    stem = os.path.splitext(original_basename)[0] or "image"
    filename = f"{stem}-{suffix}.webp"

    target_field.save(filename, ContentFile(content), save=False)
    delete_replaced_storage_file(target_field.storage, current_name, target_field.name)
    return True
