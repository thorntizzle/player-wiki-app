from __future__ import annotations

from collections.abc import Callable
from typing import Any


def filter_accessible_systems_entries(
    campaign_slug: str,
    entries: list[object],
    *,
    can_access_campaign_systems_entry: Callable[[str, str], bool],
    limit: int | None = None,
) -> list[object]:
    accessible_entries = [
        entry
        for entry in entries
        if can_access_campaign_systems_entry(campaign_slug, str(getattr(entry, "slug", "") or ""))
    ]
    if limit is not None:
        return accessible_entries[:limit]
    return accessible_entries


def list_accessible_campaign_source_entries(
    campaign_slug: str,
    source_id: str,
    *,
    systems_service: Any,
    can_access_campaign_systems_entry: Callable[[str, str], bool],
    entry_type: str | None = None,
    query: str = "",
    limit: int | None = None,
) -> list[object]:
    entries = systems_service.list_entries_for_campaign_source(
        campaign_slug,
        source_id,
        entry_type=entry_type,
        query=query,
        limit=None,
    )
    return filter_accessible_systems_entries(
        campaign_slug,
        entries,
        can_access_campaign_systems_entry=can_access_campaign_systems_entry,
        limit=limit,
    )
