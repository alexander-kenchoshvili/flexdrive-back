import os

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage


class CloudinaryMediaStorage(Storage):
    VERSION_PREFIX_RESERVED_CHARS = 16
    REQUEST_TIMEOUT_SECONDS = 15

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cloud_name = (getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or "").strip()
        self.api_key = (getattr(settings, "CLOUDINARY_API_KEY", "") or "").strip()
        self.api_secret = (getattr(settings, "CLOUDINARY_API_SECRET", "") or "").strip()

        missing = [
            name
            for name, value in (
                ("CLOUDINARY_CLOUD_NAME", self.cloud_name),
                ("CLOUDINARY_API_KEY", self.api_key),
                ("CLOUDINARY_API_SECRET", self.api_secret),
            )
            if not value
        ]
        if missing:
            missing_list = ", ".join(missing)
            raise ImproperlyConfigured(
                f"Cloudinary media storage requires these settings: {missing_list}"
            )

    def _cloudinary_modules(self):
        import cloudinary
        import cloudinary.api
        import cloudinary.uploader
        from cloudinary.utils import cloudinary_url

        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            secure=True,
        )
        return cloudinary.api, cloudinary.uploader, cloudinary_url

    def _normalize_name(self, name):
        return str(name or "").replace("\\", "/").lstrip("/")

    def _trim_name_to_max_length(self, name, max_length):
        if not max_length or len(name) <= max_length:
            return name

        directory, filename = os.path.split(name)
        stem, extension = os.path.splitext(filename)
        directory_prefix = f"{directory}/" if directory else ""
        allowed_stem_length = max_length - len(directory_prefix) - len(extension)

        if allowed_stem_length <= 0:
            raise SuspiciousFileOperation("Cloudinary storage path exceeds max_length.")

        trimmed_name = f"{directory_prefix}{stem[:allowed_stem_length]}{extension}"
        if len(trimmed_name) > max_length:
            raise SuspiciousFileOperation("Cloudinary storage path exceeds max_length.")
        return trimmed_name

    def _reserve_version_space(self, max_length):
        if max_length is None:
            return None
        return max(max_length - self.VERSION_PREFIX_RESERVED_CHARS, 1)

    def _split_versioned_name(self, name):
        normalized = self._normalize_name(name)
        parts = normalized.split("/", 1)
        if len(parts) == 2 and parts[0].startswith("v") and parts[0][1:].isdigit():
            return parts[0][1:], parts[1]
        return None, normalized

    def _parse_name(self, name):
        version, asset_path = self._split_versioned_name(name)
        public_id, extension = os.path.splitext(asset_path)
        return {
            "asset_path": asset_path,
            "public_id": public_id,
            "format": extension.lstrip("."),
            "resource_type": "image",
            "type": "upload",
            "version": version,
        }

    def _build_stored_name(self, asset_path, version=None):
        normalized = self._normalize_name(asset_path)
        if version:
            # Keep the Cloudinary version in the stored name so URLs can bust caches
            # without needing a separate DB field.
            return f"v{version}/{normalized}"
        return normalized

    def get_available_name(self, name, max_length=None):
        normalized = self._normalize_name(name)
        max_length = self._reserve_version_space(max_length)
        return self._trim_name_to_max_length(normalized, max_length)

    def save(self, name, content, max_length=None):
        normalized_name = self.get_available_name(name, max_length=max_length)
        stored_name = self._save(normalized_name, content)
        if max_length and len(stored_name) > max_length:
            return normalized_name
        return stored_name

    def _save(self, name, content):
        _, uploader, _ = self._cloudinary_modules()
        metadata = self._parse_name(name)

        if hasattr(content, "seek"):
            content.seek(0)

        result = uploader.upload(
            content,
            public_id=metadata["public_id"],
            resource_type=metadata["resource_type"],
            type=metadata["type"],
            overwrite=True,
            invalidate=True,
        )

        uploaded_format = (result.get("format") or metadata["format"]).strip(".")
        asset_path = f"{metadata['public_id']}.{uploaded_format}" if uploaded_format else metadata["public_id"]
        return self._build_stored_name(asset_path, version=result.get("version"))

    def _open(self, name, mode="rb"):
        response = requests.get(self.url(name), timeout=self.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        basename = os.path.basename(self._parse_name(name)["asset_path"])
        return ContentFile(response.content, name=basename)

    def delete(self, name):
        _, uploader, _ = self._cloudinary_modules()
        metadata = self._parse_name(name)
        try:
            uploader.destroy(
                metadata["public_id"],
                resource_type=metadata["resource_type"],
                type=metadata["type"],
                invalidate=True,
            )
        except Exception:
            return

    def exists(self, name):
        api, _, _ = self._cloudinary_modules()
        metadata = self._parse_name(name)
        try:
            api.resource(
                metadata["public_id"],
                resource_type=metadata["resource_type"],
                type=metadata["type"],
            )
        except Exception:
            return False
        return True

    def size(self, name):
        api, _, _ = self._cloudinary_modules()
        metadata = self._parse_name(name)
        resource = api.resource(
            metadata["public_id"],
            resource_type=metadata["resource_type"],
            type=metadata["type"],
        )
        return resource.get("bytes")

    def url(self, name):
        _, _, cloudinary_url = self._cloudinary_modules()
        metadata = self._parse_name(name)
        url, _ = cloudinary_url(
            metadata["public_id"],
            resource_type=metadata["resource_type"],
            type=metadata["type"],
            secure=True,
            format=metadata["format"] or None,
            version=metadata["version"] or None,
        )
        return url

    def identifies_same_asset(self, first_name, second_name):
        first = self._parse_name(first_name)
        second = self._parse_name(second_name)
        return (
            first["public_id"] == second["public_id"]
            and first["resource_type"] == second["resource_type"]
            and first["type"] == second["type"]
        )

    def path(self, name):
        raise NotImplementedError("Cloudinary-backed media files do not have a local filesystem path.")
