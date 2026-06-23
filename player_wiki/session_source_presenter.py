from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
)
from .systems_labels import systems_entry_type_label


def build_session_article_source_search_results(
    *,
    campaign: Any,
    campaign_slug: str,
    query: str,
    page_store: Any,
    systems_service: Any,
    can_access_systems: bool,
    can_access_systems_entry: Callable[[str], bool],
    limit: int = 30,
) -> list[dict[str, str]]:
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        return []

    results: list[dict[str, str]] = []
    page_records = page_store.search_page_records(
        campaign.slug,
        normalized_query,
        limit=max(limit, 1) * 2,
        include_body=False,
    )
    for record in page_records:
        if not campaign.is_page_visible(record.page):
            continue
        context_parts = [record.page.section]
        if record.page.subsection:
            context_parts.append(record.page.subsection)
        context_label = " / ".join(part for part in context_parts if part)
        results.append(
            {
                "source_ref": build_session_article_page_source_ref(record.page_ref),
                "source_kind": SESSION_ARTICLE_SOURCE_KIND_PAGE,
                "title": record.page.title,
                "subtitle": context_label,
                "kind_label": "Wiki",
                "select_label": f"{record.page.title} - Wiki - {context_label}",
            }
        )
        if len(results) >= limit:
            return results

    if can_access_systems:
        systems_entries = systems_service.search_entries_for_campaign(
            campaign_slug,
            query=normalized_query,
            limit=max(limit, 1) * 2,
        )
        for entry in systems_entries:
            if not can_access_systems_entry(entry.slug):
                continue
            entry_type_label = systems_entry_type_label(entry.entry_type)
            results.append(
                {
                    "source_ref": build_session_article_systems_source_ref(entry.slug),
                    "source_kind": SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
                    "title": entry.title,
                    "subtitle": f"{entry_type_label} - {entry.source_id}",
                    "kind_label": "Systems",
                    "select_label": f"{entry.title} - Systems - {entry_type_label} - {entry.source_id}",
                }
            )
            if len(results) >= limit:
                break

    return results
