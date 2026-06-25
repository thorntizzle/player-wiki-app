from __future__ import annotations

from io import BytesIO
from pathlib import Path

PUBLISHED_ARTICLE_WEBP_QUALITY = 82
CONVERTIBLE_ARTICLE_IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png"}
PASSTHROUGH_ARTICLE_IMAGE_EXTENSIONS = {".gif", ".webp"}
ALLOWED_ARTICLE_IMAGE_EXTENSIONS = CONVERTIBLE_ARTICLE_IMAGE_EXTENSIONS | PASSTHROUGH_ARTICLE_IMAGE_EXTENSIONS


def prepare_published_article_image(
    filename: str,
    data_blob: bytes | bytearray,
    *,
    quality: int = PUBLISHED_ARTICLE_WEBP_QUALITY,
) -> tuple[str, bytes]:
    extension = Path(str(filename or "")).suffix.lower()
    if extension not in ALLOWED_ARTICLE_IMAGE_EXTENSIONS:
        raise ValueError("Wiki page images must be PNG, JPG, GIF, or WEBP files.")

    if not data_blob:
        raise ValueError("Uploaded wiki page images cannot be empty.")
    if len(data_blob) > 8 * 1024 * 1024:
        raise ValueError("Wiki page images must stay under 8 MB.")
    if quality < 0 or quality > 100:
        raise ValueError("Image quality must be between 0 and 100.")

    try:
        from PIL import Image, UnidentifiedImageError
    except ModuleNotFoundError as exc:
        raise ValueError("Image conversion is unavailable; install pillow to enable image publishing.") from exc

    raw_bytes = bytes(data_blob)
    try:
        image = Image.open(BytesIO(raw_bytes))
    except UnidentifiedImageError as exc:
        raise ValueError("Uploaded wiki page images must be valid image files.") from exc

    try:
        with image:
            if extension in PASSTHROUGH_ARTICLE_IMAGE_EXTENSIONS:
                image.verify()
                return Path(str(filename or "image")).name, raw_bytes

            mode = image.mode
            if mode in {"RGBA", "RGB", "P", "LA", "L"}:
                source_image = image.convert("RGBA" if mode in {"RGBA", "LA"} else "RGB")
            else:
                source_image = image.convert("RGBA")

            output = BytesIO()
            source_image.save(output, format="WEBP", quality=quality)
            output_bytes = output.getvalue()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Uploaded wiki page images must be valid image files.") from exc

    converted_filename = Path(str(filename or "image")).with_suffix(".webp").name
    return converted_filename, output_bytes
