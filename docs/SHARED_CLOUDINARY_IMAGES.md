# Staging → production product images

This is a one-time reference transfer, not a supplier cron task. Existing Cloudinary
files are reused; no image uploads or transformations are triggered by the import.
Production galleries are expected to be empty. The importer will never replace a
different existing gallery. No product price, stock, status or category is updated.

## Deploy first

Deploy this revision to **both staging and production before copying references**.
No migration is needed for this change.

`CLOUDINARY_SHARED_MEDIA` defaults to `True`. Keep it enabled in both environments:

- Each new upload or image edit uses a fresh UUID in its Cloudinary public ID and
  `overwrite=False`. Existing image URLs keep working unchanged.
- Django record deletion and image replacement no longer delete Cloudinary files.
  Local filesystem storage retains its existing behavior.
- `audit_cloudinary_orphans --commit` is blocked: a one-database audit cannot know
  whether the other environment still uses a file. Audit-only mode remains available.
- Unreferenced files will accumulate until a separately reviewed cleanup checks all
  sharing databases. This intentionally trades some storage for cross-environment safety.
- Direct deletion/overwrite in the Cloudinary console or another script remains outside
  this protection. Do not delete shared files there based on only one database.

## Production environment

In DigitalOcean's **production backend** component, set the same values as staging:

| Key | Value |
| --- | --- |
| `USE_CLOUDINARY_MEDIA` | `True` |
| `CLOUDINARY_CLOUD_NAME` | Staging cloud name |
| `CLOUDINARY_API_KEY` | Staging API key (encrypted) |
| `CLOUDINARY_API_SECRET` | Staging API secret (encrypted) |

Use the existing environment settings consoles; do not share keys in chat or commit
them. If these are app-level values, components such as the sync job also inherit them.
If they are backend-only, the supplier job can keep its existing media configuration
because it does not upload/download image files. Wait for deployment to complete.

## Export in the staging backend console

```sh
python manage.py export_product_images --output /tmp/flexdrive-images.b64 --encoded
cat /tmp/flexdrive-images.b64
```

Copy the encoded file contents (all lines), not the shell prompt or export summary.
The snapshot includes cloud name, SKU, image paths, primary/order/alt text, crop,
padding and AI background settings. It contains no credentials and no image binaries.
Lines are wrapped to 120 characters to support console paste limits.
Export refuses to overwrite an existing file; use a new filename if rerunning it.

## Import in the production backend console

Create a temporary file by pasting the following first line, the copied data on the
following lines, then `IMAGES` by itself on the last line:

```sh
cat > /tmp/flexdrive-images.b64 <<'IMAGES'
PASTE_THE_ENCODED_DATA_HERE
IMAGES
```

Dry-run (writes nothing):

```sh
python manage.py import_product_images --input /tmp/flexdrive-images.b64 --encoded
```

Check `products_to_add`, `images_to_add`, `unchanged_products` and `missing_skus`.
If staging contains old SKUs absent from production, the default is to stop before
any writes. After reviewing those SKUs, add `--skip-missing` to explicitly leave them
out; this never creates missing products.

Apply the same reviewed command with `--commit`:

```sh
python manage.py import_product_images --input /tmp/flexdrive-images.b64 --encoded --commit
```

Repeat the dry run afterward. Expected: `images_to_add: 0`, and all copied products
counted as `unchanged_products`. This checks stored metadata/paths; open a few actual
production product pages to verify image delivery too. The import does not probe each
remote Cloudinary asset: images already missing at source remain missing at destination.

The snapshot is matched strictly by SKU, not database IDs. All rows are validated
before writes; the import is transactional. Primary flags, stable ordering and all
image processing fields are preserved. Repeating the same import does not duplicate
rows. A cloud-name mismatch, different existing gallery or malformed file stops it.

After verification, remove the temporary transfer file in **each** remote console:

```sh
rm /tmp/flexdrive-images.b64
```

Subsequent staging edits do not update production automatically. This command is for
initial empty galleries, not ongoing gallery replacement.
