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
    image_urls = select_campaign_loading_image_urls(
        campaign,
        can_access_wiki=can_access_wiki,
        build_image_url=build_image_url,
        image_exists=image_exists,
        selection_seed=selection_seed,
        selection_date=selection_date,
        max_scanned_pages=max_scanned_pages,
        max_loading_images=1,
    )
    if not image_urls:
        return None
    return image_urls[0]


def select_campaign_loading_image_urls(
    campaign: Campaign | None,
    *,
    can_access_wiki: bool,
    build_image_url: ImageUrlBuilder,
    image_exists: AssetExists,
    selection_seed: str | None = None,
    selection_date: date | None = None,
    max_scanned_pages: int = 200,
    max_loading_images: int = 4,
) -> list[str]:
    if campaign is None or not can_access_wiki:
        return []

    if not callable(build_image_url) or not callable(image_exists):
        return []

    if not isinstance(max_scanned_pages, int) or max_scanned_pages <= 0:
        max_scanned_pages = 200
    if not isinstance(max_loading_images, int) or max_loading_images <= 0:
        return []

    candidates: list[tuple[str, str]] = []
    seen_image_paths: set[str] = set()
    scanned = 0
    for page in campaign.visible_pages():
        if scanned >= max_scanned_pages:
            break
        scanned += 1

        source_path = str(page.source_path or "").replace("\\", "/").lower()
        if source_path.startswith("global/"):
            continue

        image_path = _normalize_image_path(page.image_path)
        if not image_path or not _is_candidate_path(image_path):
            continue
        if image_path in seen_image_paths:
            continue
        try:
            if not image_exists(campaign, image_path):
                continue
        except Exception:
            continue

        seen_image_paths.add(image_path)
        candidates.append((image_path, page.route_slug))

    if not candidates:
        return []

    seed = selection_seed or _selection_day(selection_date)
    ranked_candidates: list[tuple[int, str]] = []
    for image_path, route_slug in candidates:
        digest = blake2s(
            "|".join((campaign.slug, seed, route_slug, image_path)).encode("utf-8"),
            digest_size=8,
        ).hexdigest()
        ranked_candidates.append((int(digest, 16), image_path))

    ranked_candidates.sort(key=lambda item: item[0])
    selected_image_paths = [image_path for _, image_path in ranked_candidates[:max_loading_images]]

    selected_urls: list[str] = []
    for selected_image_path in selected_image_paths:
        try:
            selected_url = build_image_url(campaign, selected_image_path)
        except Exception:
            continue
        if not selected_url:
            continue
        selected_urls.append(str(selected_url))

    return selected_urls
