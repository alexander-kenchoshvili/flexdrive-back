import os
import os
from io import BytesIO
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from PIL import Image, ImageChops, ImageDraw, ImageOps

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
    crop_box=None,
    padding_ratio=0,
    replace_background=False,
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
            if crop_box:
                source = source.crop(crop_box)
            if replace_background:
                source = replace_flat_background_with_white(source)
            padding_ratio = max(min(float(padding_ratio or 0), 0.45), 0)
            inner_width = max(int(round(max_width * (1 - 2 * padding_ratio))), 1)
            inner_height = max(int(round(max_height * (1 - 2 * padding_ratio))), 1)
            scale = min(inner_width / source.width, inner_height / source.height)
            resized_size = (
                max(int(round(source.width * scale)), 1),
                max(int(round(source.height * scale)), 1),
            )
            if resized_size != source.size:
                source = source.resize(resized_size, RESAMPLING_LANCZOS)

            output = BytesIO()
            canvas = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
            offset = ((max_width - source.width) // 2, (max_height - source.height) // 2)
            canvas.alpha_composite(source, offset)
            canvas.convert("RGB").save(output, format="WEBP", quality=quality)
            output.seek(0)
            return output.read()
    finally:
        source_image_field.close()


def replace_flat_background_with_white(
    image,
    *,
    tolerance=26,
):
    source = image.convert("RGBA")
    width, height = source.size
    if width <= 1 or height <= 1:
        return source

    background_color = _estimate_edge_background_color(source)
    rgb = source.convert("RGB")
    background = Image.new("RGB", source.size, background_color)
    diff = ImageChops.difference(rgb, background)
    channel_masks = [
        channel.point(lambda value: 255 if value <= tolerance else 0)
        for channel in diff.split()
    ]
    candidate_mask = ImageChops.multiply(
        ImageChops.multiply(channel_masks[0], channel_masks[1]),
        channel_masks[2],
    )
    background_mask = _edge_connected_mask(candidate_mask)
    if not background_mask.getbbox():
        return source

    result = source.copy()
    white = Image.new("RGBA", source.size, (255, 255, 255, 255))
    result.paste(white, mask=background_mask)
    return result


def _estimate_edge_background_color(source):
    width, height = source.size
    sample_points = []
    sample_size = max(min(width, height) // 24, 1)
    corners = (
        (0, 0),
        (max(width - sample_size, 0), 0),
        (0, max(height - sample_size, 0)),
        (max(width - sample_size, 0), max(height - sample_size, 0)),
    )
    rgb = source.convert("RGB")
    for start_x, start_y in corners:
        for x in range(start_x, min(start_x + sample_size, width)):
            for y in range(start_y, min(start_y + sample_size, height)):
                sample_points.append(rgb.getpixel((x, y)))

    if not sample_points:
        return rgb.getpixel((0, 0))

    channels = list(zip(*sample_points))
    return tuple(int(sum(channel) / len(channel)) for channel in channels)


def _edge_connected_mask(candidate_mask):
    width, height = candidate_mask.size
    marker = candidate_mask.copy()

    def flood_if_candidate(point):
        if marker.getpixel(point) == 255:
            ImageDraw.floodfill(marker, point, 128, thresh=0)

    for x in range(width):
        flood_if_candidate((x, 0))
        flood_if_candidate((x, height - 1))

    for y in range(height):
        flood_if_candidate((0, y))
        flood_if_candidate((width - 1, y))

    return marker.point(lambda value: 255 if value == 128 else 0)


def detect_content_crop_box(
    source_image_field,
    *,
    tolerance=12,
    padding_ratio=0.12,
):
    if not source_image_field:
        return None

    source_image_field.open("rb")
    try:
        with Image.open(source_image_field) as img:
            img = ImageOps.exif_transpose(img)
            source = img.convert("RGBA")
            width, height = source.size
            if width <= 1 or height <= 1:
                return None

            background = Image.new("RGBA", source.size, source.getpixel((0, 0)))
            diff = ImageChops.difference(source, background).convert("L")
            mask = diff.point(lambda value: 255 if value > tolerance else 0)
            bbox = mask.getbbox()
            if not bbox:
                return None

            left, top, right, bottom = bbox
            content_width = right - left
            content_height = bottom - top
            if content_width <= 0 or content_height <= 0:
                return None

            pad_x = max(int(round(content_width * padding_ratio)), 1)
            pad_y = max(int(round(content_height * padding_ratio)), 1)
            left = max(left - pad_x, 0)
            top = max(top - pad_y, 0)
            right = min(right + pad_x, width)
            bottom = min(bottom + pad_y, height)

            if right <= left or bottom <= top:
                return None

            return (left, top, right, bottom)
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
