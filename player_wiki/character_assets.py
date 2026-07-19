from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .campaign_session_service import ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS
from .character_builder import (
    CAMPAIGN_ITEMS_SECTION,
    _attach_campaign_item_page_support,
    _build_item_catalog,
    _list_campaign_enabled_entries,
)
from .image_publish import prepare_published_article_image
from .input_limits import MAX_INGRESS_FILE_BYTES

CHARACTER_PORTRAIT_ALT_MAX_LENGTH = 200
CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH = 300
CHARACTER_PORTRAIT_MAX_BYTES = MAX_INGRESS_FILE_BYTES
CHARACTER_PORTRAIT_ASSET_REF_MAX_BYTES = 512
CHARACTER_PORTRAIT_ASSET_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp"}
)


def build_character_item_catalog(systems_service, page_store, campaign_slug: str) -> dict[str, object]:
    return _attach_campaign_item_page_support(
        _build_item_catalog(
            _list_campaign_enabled_entries(
                systems_service,
                campaign_slug,
                "item",
            )
        ),
        [
            page_record
            for page_record in page_store.list_page_records(campaign_slug, include_body=True)
            if str(getattr(getattr(page_record, "page", None), "section", "") or "").strip()
            == CAMPAIGN_ITEMS_SECTION
        ],
    )


def build_character_portrait_asset_ref(character_slug: str, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"characters/{character_slug}/portrait{extension}"


def resolve_character_portrait_asset_path(
    campaign_dir: Path,
    character_slug: str,
    asset_ref: str,
) -> tuple[Path, Path]:
    """Resolve the exact portrait asset location without following unsafe paths."""

    clean_ref = str(asset_ref or "").strip()
    if (
        not clean_ref
        or len(clean_ref.encode("utf-8")) > CHARACTER_PORTRAIT_ASSET_REF_MAX_BYTES
        or "\\" in clean_ref
    ):
        raise ValueError("Character portrait asset references are invalid.")
    pure_ref = PurePosixPath(clean_ref)
    parts = pure_ref.parts
    if (
        pure_ref.is_absolute()
        or len(parts) != 3
        or parts[0] != "characters"
        or parts[1] != character_slug
        or not parts[2].startswith("portrait.")
        or Path(parts[2]).suffix.lower() not in CHARACTER_PORTRAIT_ASSET_EXTENSIONS
        or pure_ref.as_posix() != clean_ref
    ):
        raise ValueError("Character portrait asset references are invalid.")

    assets_root = (Path(campaign_dir) / "assets").resolve()
    candidate = assets_root.joinpath(*parts)
    resolved = candidate.resolve()
    if assets_root not in resolved.parents or resolved != candidate:
        raise ValueError("Character portrait asset references are invalid.")
    return assets_root, candidate


def prepare_character_portrait_file(filename: str, data_blob: bytes) -> tuple[str, bytes]:
    clean_filename = Path(str(filename or "").strip()).name
    if not clean_filename:
        raise ValueError("Choose an image file before saving the portrait.")
    extension = Path(clean_filename).suffix.lower()
    if extension not in ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS:
        raise ValueError("Character portraits must be PNG, JPG, GIF, or WEBP files.")
    if not data_blob:
        raise ValueError("Uploaded portrait files cannot be empty.")
    if len(data_blob) > CHARACTER_PORTRAIT_MAX_BYTES:
        raise ValueError("Character portraits must stay under 8 MB.")
    try:
        return prepare_published_article_image(clean_filename, data_blob)
    except ValueError as exc:
        message = str(exc)
        message = message.replace("Wiki page images", "Character portraits")
        message = message.replace("Uploaded wiki page images", "Uploaded portrait files")
        raise ValueError(message) from exc


def validate_character_portrait_text(alt_text: str, caption: str) -> tuple[str, str]:
    clean_alt_text = str(alt_text or "").strip()
    clean_caption = str(caption or "").strip()
    if len(clean_alt_text) > CHARACTER_PORTRAIT_ALT_MAX_LENGTH:
        raise ValueError(f"Portrait alt text must stay under {CHARACTER_PORTRAIT_ALT_MAX_LENGTH} characters.")
    if len(clean_caption) > CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH:
        raise ValueError(f"Portrait captions must stay under {CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH} characters.")
    return clean_alt_text, clean_caption


def update_character_portrait_profile(
    definition,
    *,
    asset_ref: str = "",
    alt_text: str = "",
    caption: str = "",
):
    payload = definition.to_dict()
    profile = dict(payload.get("profile") or {})
    clean_asset_ref = str(asset_ref or "").strip()
    clean_alt_text = str(alt_text or "").strip()
    clean_caption = str(caption or "").strip()
    if clean_asset_ref:
        profile["portrait_asset_ref"] = clean_asset_ref
        profile["portrait_alt"] = clean_alt_text
        profile["portrait_caption"] = clean_caption
    else:
        profile.pop("portrait_asset_ref", None)
        profile.pop("portrait_alt", None)
        profile.pop("portrait_caption", None)
    payload["profile"] = profile
    return definition.__class__.from_dict(payload)


def character_portrait_profile(definition) -> dict[str, Any]:
    profile = dict(definition.profile or {})
    return {
        "asset_ref": str(profile.get("portrait_asset_ref") or "").strip(),
        "alt_text": str(profile.get("portrait_alt") or definition.name).strip() or definition.name,
        "caption": str(profile.get("portrait_caption") or "").strip(),
    }
