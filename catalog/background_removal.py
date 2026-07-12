import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

MODEL_NAME = "u2netp"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / ".u2net"
os.environ.setdefault("U2NET_HOME", str(DEFAULT_MODEL_DIR))


@lru_cache(maxsize=1)
def _session():
    from rembg import new_session

    return new_session(MODEL_NAME)


def preload_model():
    return _session()


def remove_background_to_white(image_file):
    from rembg import remove

    with Image.open(image_file) as image:
        source = ImageOps.exif_transpose(image).convert("RGBA")
        result = remove(
            source,
            session=_session(),
            bgcolor=(255, 255, 255, 255),
        ).convert("RGB")
        output = BytesIO()
        result.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()
