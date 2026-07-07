from collections import defaultdict

import cloudinary
import cloudinary.api
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import models


DEFAULT_PREFIXES = (
    "catalog/",
    "seo/",
    "blog_posts/",
    "content_items/",
    "components/",
)


def normalize_storage_name(name):
    normalized = str(name or "").replace("\\", "/").lstrip("/")
    parts = normalized.split("/", 1)
    if len(parts) == 2 and parts[0].startswith("v") and parts[0][1:].isdigit():
        return parts[1]
    return normalized


def storage_name_to_public_id(name):
    normalized = normalize_storage_name(name)
    if not normalized:
        return ""
    return normalized.rsplit(".", 1)[0] if "." in normalized else normalized


def format_bytes(size):
    size = int(size or 0)
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def top_level_folder(public_id):
    normalized = str(public_id or "").strip("/")
    if not normalized:
        return "(root)"
    return normalized.split("/", 1)[0]


class Command(BaseCommand):
    help = (
        "Audit Cloudinary image upload assets that are not referenced by current "
        "Django ImageField/FileField values. Dry-run/report only by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            action="append",
            dest="prefixes",
            help=(
                "Cloudinary public_id prefix to scan. Can be passed multiple times. "
                f"Defaults to: {', '.join(DEFAULT_PREFIXES)}"
            ),
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Scan all Cloudinary image upload assets instead of the default known prefixes.",
        )
        parser.add_argument(
            "--show",
            type=int,
            default=25,
            help="Number of orphan asset public_ids to print as a sample.",
        )
        parser.add_argument(
            "--breakdown",
            action="store_true",
            help="Print count and size grouped by top-level Cloudinary folder.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Delete orphan Cloudinary assets. Without this flag the command is dry-run only.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of Cloudinary public_ids to delete per API request when --commit is used.",
        )
        parser.add_argument(
            "--max-delete",
            type=int,
            default=None,
            help="Safety limit for --commit. Refuse to delete more than this many orphan assets.",
        )

    def handle(self, *args, **options):
        self._configure_cloudinary()

        scan_all = bool(options["all"])
        if scan_all and options["prefixes"]:
            raise CommandError("Use either --all or --prefix, not both.")

        prefixes = () if scan_all else tuple(options["prefixes"] or DEFAULT_PREFIXES)
        show_count = max(options["show"], 0)
        breakdown = bool(options["breakdown"])
        commit = bool(options["commit"])
        batch_size = max(options["batch_size"], 1)
        max_delete = options["max_delete"]

        used_public_ids_by_model = self._collect_used_public_ids()
        used_public_ids = set()
        for model_values in used_public_ids_by_model.values():
            used_public_ids.update(model_values)

        cloudinary_assets = self._list_cloudinary_assets(prefixes)
        orphan_assets = [
            asset
            for asset in cloudinary_assets
            if asset["public_id"] not in used_public_ids
        ]

        total_bytes = sum(asset["bytes"] for asset in cloudinary_assets)
        orphan_bytes = sum(asset["bytes"] for asset in orphan_assets)

        self.stdout.write(
            "Cloudinary orphan audit: " + ("COMMIT delete enabled" if commit else "dry-run only")
        )
        self.stdout.write(
            "Scanned prefixes: "
            + ("all image upload assets" if scan_all else ", ".join(prefixes))
        )
        self.stdout.write(f"Referenced DB assets: {len(used_public_ids)}")
        self.stdout.write(
            f"Cloudinary assets scanned: {len(cloudinary_assets)} "
            f"({format_bytes(total_bytes)})"
        )
        self.stdout.write(
            f"Orphan assets: {len(orphan_assets)} ({format_bytes(orphan_bytes)})"
        )

        if used_public_ids_by_model:
            self.stdout.write("")
            self.stdout.write("Referenced assets by model field:")
            for label, values in sorted(used_public_ids_by_model.items()):
                self.stdout.write(f"  {label}: {len(values)}")

        if breakdown:
            self._write_folder_breakdown(cloudinary_assets, orphan_assets)

        if orphan_assets and show_count:
            self.stdout.write("")
            self.stdout.write(f"Sample orphan assets, first {min(show_count, len(orphan_assets))}:")
            for asset in orphan_assets[:show_count]:
                self.stdout.write(
                    f"  {asset['public_id']} ({format_bytes(asset['bytes'])})"
                )

        self._write_usage_summary()

        if commit:
            if max_delete is not None and len(orphan_assets) > max_delete:
                raise CommandError(
                    f"Refusing to delete {len(orphan_assets)} assets because --max-delete "
                    f"is {max_delete}."
                )
            self._delete_orphan_assets(orphan_assets, batch_size=batch_size)

    def _configure_cloudinary(self):
        cloud_name = (getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or "").strip()
        api_key = (getattr(settings, "CLOUDINARY_API_KEY", "") or "").strip()
        api_secret = (getattr(settings, "CLOUDINARY_API_SECRET", "") or "").strip()

        missing = [
            name
            for name, value in (
                ("CLOUDINARY_CLOUD_NAME", cloud_name),
                ("CLOUDINARY_API_KEY", api_key),
                ("CLOUDINARY_API_SECRET", api_secret),
            )
            if not value
        ]
        if missing:
            raise CommandError(
                "Missing Cloudinary environment variables: " + ", ".join(missing)
            )

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )

    def _collect_used_public_ids(self):
        used_by_model = defaultdict(set)

        for model in apps.get_models():
            file_fields = [
                field
                for field in model._meta.get_fields()
                if isinstance(field, models.FileField)
            ]
            if not file_fields:
                continue

            values = model.objects.values_list(
                *(field.name for field in file_fields),
                named=False,
            )
            model_label = model._meta.label

            for row in values.iterator():
                for field, value in zip(file_fields, row):
                    public_id = storage_name_to_public_id(value)
                    if public_id:
                        used_by_model[f"{model_label}.{field.name}"].add(public_id)

        return dict(used_by_model)

    def _list_cloudinary_assets(self, prefixes):
        assets_by_public_id = {}
        scan_prefixes = prefixes or (None,)

        for prefix in scan_prefixes:
            next_cursor = None
            while True:
                request_options = {
                    "resource_type": "image",
                    "type": "upload",
                    "max_results": 500,
                    "next_cursor": next_cursor,
                }
                if prefix:
                    request_options["prefix"] = prefix

                response = cloudinary.api.resources(**request_options)
                for resource in response.get("resources", []):
                    public_id = resource.get("public_id")
                    if not public_id:
                        continue
                    assets_by_public_id[public_id] = {
                        "public_id": public_id,
                        "bytes": int(resource.get("bytes") or 0),
                        "format": resource.get("format") or "",
                    }

                next_cursor = response.get("next_cursor")
                if not next_cursor:
                    break

        return sorted(assets_by_public_id.values(), key=lambda asset: asset["public_id"])

    def _write_folder_breakdown(self, cloudinary_assets, orphan_assets):
        orphan_public_ids = {asset["public_id"] for asset in orphan_assets}
        rows = defaultdict(
            lambda: {
                "assets": 0,
                "bytes": 0,
                "orphans": 0,
                "orphan_bytes": 0,
            }
        )

        for asset in cloudinary_assets:
            folder = top_level_folder(asset["public_id"])
            row = rows[folder]
            row["assets"] += 1
            row["bytes"] += asset["bytes"]
            if asset["public_id"] in orphan_public_ids:
                row["orphans"] += 1
                row["orphan_bytes"] += asset["bytes"]

        self.stdout.write("")
        self.stdout.write("Cloudinary folder breakdown:")
        self.stdout.write("  folder | assets | size | orphan assets | orphan size")
        for folder, row in sorted(
            rows.items(),
            key=lambda item: (item[1]["bytes"], item[1]["assets"]),
            reverse=True,
        ):
            self.stdout.write(
                f"  {folder} | {row['assets']} | {format_bytes(row['bytes'])} | "
                f"{row['orphans']} | {format_bytes(row['orphan_bytes'])}"
            )

    def _delete_orphan_assets(self, orphan_assets, *, batch_size):
        if not orphan_assets:
            self.stdout.write("No orphan assets to delete.")
            return

        public_ids = [asset["public_id"] for asset in orphan_assets]
        deleted = 0
        not_found = 0
        failed = {}

        for start in range(0, len(public_ids), batch_size):
            batch = public_ids[start : start + batch_size]
            response = cloudinary.api.delete_resources(
                batch,
                resource_type="image",
                type="upload",
                invalidate=True,
            )
            deleted_rows = response.get("deleted") or {}
            for public_id, status in deleted_rows.items():
                if status == "deleted":
                    deleted += 1
                elif status == "not_found":
                    not_found += 1
                else:
                    failed[public_id] = status

            self.stdout.write(
                f"Deleted batch {start + 1}-{min(start + batch_size, len(public_ids))} "
                f"of {len(public_ids)}."
            )

        self.stdout.write("")
        self.stdout.write(
            f"Delete complete: deleted={deleted}, not_found={not_found}, failed={len(failed)}"
        )
        if failed:
            self.stdout.write("Failed asset statuses:")
            for public_id, status in sorted(failed.items())[:25]:
                self.stdout.write(f"  {public_id}: {status}")

    def _write_usage_summary(self):
        try:
            usage = cloudinary.api.usage()
        except Exception as exc:
            self.stdout.write("")
            self.stdout.write(f"Cloudinary usage summary unavailable: {exc}")
            return

        storage = usage.get("storage") or {}
        credits = usage.get("credits") or {}
        objects = usage.get("objects") or {}

        self.stdout.write("")
        self.stdout.write("Cloudinary account usage:")
        self._write_usage_line("Storage", storage)
        self._write_usage_line("Credits", credits, is_bytes=False)
        self._write_usage_line("Objects", objects, is_bytes=False)

    def _write_usage_line(self, label, data, *, is_bytes=True):
        usage_value = data.get("usage")
        limit_value = data.get("limit")
        if usage_value is None and limit_value is None:
            return

        if is_bytes:
            formatted_usage = format_bytes(usage_value or 0)
            formatted_limit = format_bytes(limit_value or 0) if limit_value else "unknown"
        else:
            formatted_usage = str(usage_value or 0)
            formatted_limit = str(limit_value) if limit_value is not None else "unknown"

        self.stdout.write(f"  {label}: {formatted_usage} / {formatted_limit}")
