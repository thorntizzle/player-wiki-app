from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _normalized_sections(sections: Iterable[str] | None) -> frozenset[str]:
    return frozenset(str(section or "").strip() for section in sections or () if str(section or "").strip())


def list_builder_campaign_page_records(
    page_store: Any,
    campaign_slug: str,
    campaign: Any,
    *,
    relevant_sections: Iterable[str],
) -> list[object]:
    allowed_sections = _normalized_sections(relevant_sections)
    return [
        page_record
        for page_record in page_store.list_page_records(campaign_slug)
        if campaign.is_page_visible(page_record.page)
        and str(page_record.page.section or "").strip() in allowed_sections
    ]


def list_visible_character_page_records(
    page_store: Any,
    campaign_slug: str,
    campaign: Any,
    *,
    include_body: bool = True,
    excluded_sections: Iterable[str] | None = None,
) -> list[object]:
    ignored_sections = _normalized_sections(excluded_sections)
    return [
        page_record
        for page_record in page_store.list_page_records(campaign_slug, include_body=include_body)
        if getattr(page_record, "page", None) is not None
        and campaign.is_page_visible(page_record.page)
        and str(page_record.page.section or "").strip() not in ignored_sections
    ]
