from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from hashlib import blake2s

from .models import Campaign

AssetExists = Callable[[Campaign, str], bool]
ImageUrlBuilder = Callable[[Campaign, str], str]


def _normalize_image_path(raw_path: str) -> str:
    return str(raw_path or "").strip().replace("\\", "/")


def _is_candidate_path(raw_path: str) -> bool:
    normalized = _normalize_image_path(raw_path)
    if not normalized:
        return False
    if normalized.startswith("/"):
        return False
    if normalized.startswith("//"):
        return False
    lowered = normalized.lower()
    if lowered.startswith(("http://", "https://", "ftp://", "mailto:", "javascript:")):
        return False
    if ":" in normalized:
        return False
    return ".." not in normalized.split("/")


def _selection_day(selection_date: date | None = None) -> str:
    selected_day = selection_date or datetime.now(timezone.utc).date()
    return selected_day.strftime("%Y%m%d")


def select_campaign_loading_image_url(
    campaign: Campaign | None,
    *,
    can_access_wiki: bool,
    build_image_url: ImageUrlBuilder,
    image_exists: AssetExists,
    selection_seed: str | None = None,
    selection_date: date | None = None,
    max_scanned_pages: int = 200,
) -> str | None:
    if campaign is None or not can_access_wiki:
        return None

    if not callable(build_image_url) or not callable(image_exists):
        return None

    if not isinstance(max_scanned_pages, int) or max_scanned_pages <= 0:
        max_scanned_pages = 200

    candidates: list[tuple[str, str]] = []
    scanned = 0
    for page in campaign.visible_pages():
        if scanned >= max_scanned_pages:
            break
        scanned += 1

        image_path = _normalize_image_path(page.image_path)
        if not image_path or not _is_candidate_path(image_path):
            continue
        try:
            if not image_exists(campaign, image_path):
                continue
        except Exception:
            continue

        candidates.append((image_path, page.route_slug))

    if not candidates:
        return None

    seed = selection_seed or _selection_day(selection_date)
    key_components = [campaign.slug, seed]
    key_components.extend(route_slug for _, route_slug in candidates)
    digest = blake2s("|".join(key_components).encode("utf-8"), digest_size=8).hexdigest()
    index = int(digest, 16) % len(candidates)
    selected_image_path = candidates[index][0]

    try:
        selected_url = build_image_url(campaign, selected_image_path)
    except Exception:
        return None
    if not selected_url:
        return None
    return str(selected_url)
