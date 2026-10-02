from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .repository import normalize_lookup


def _normalized_sections(sections: Iterable[str] | None) -> frozenset[str]:
    return frozenset(str(section or "").strip() for section in sections or () if str(section or "").strip())


def _committed_visible_records(page_store: Any, campaign_slug: str, *, include_body: bool) -> list[Any]:
    """Select config, page proofs, and projections in one short SQLite read view."""
    from .committed_publication import (
        CommittedSourceConflict, config, current, page_rows, read_snapshot,
    )
    from .models import page_sort_key

    mapper = getattr(page_store, "_map_record", None)
    if not callable(mapper):
        mapper = getattr(getattr(page_store, "page_store", None), "_map_record", None)
    if not callable(mapper):
        raise CommittedSourceConflict("Committed Character page projection is unavailable.")

    @read_snapshot
    def select() -> list[Any]:
        settings_source, settings = config(campaign_slug)
        records = []
        for row in page_rows(campaign_slug):
            record = mapper(row, include_body=include_body)
            page = getattr(record, "page", None)
            if (page is None or not page.published or page.is_deprecated_wiki_overview
                    or page.reveal_after_session > int(settings["current_session"])):
                continue
            source = current(campaign_slug, "page", record.page_ref)
            if source is None:
                continue
            page.committed_revision = int(source["revision"])
            page.committed_config_revision = int(settings_source["revision"])
            records.append(record)
        return sorted(records, key=lambda record: (*page_sort_key(record.page), record.page_ref))

    return select()


def list_builder_campaign_page_records(
    page_store: Any,
    campaign_slug: str,
    campaign: Any,
    *,
    relevant_sections: Iterable[str],
) -> list[object]:
    from .committed_publication import active

    allowed_sections = _normalized_sections(relevant_sections)
    if active():
        return [record for record in _committed_visible_records(page_store, campaign_slug, include_body=False)
                if str(record.page.section or "").strip() in allowed_sections]
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
    from .committed_publication import active

    ignored_sections = _normalized_sections(excluded_sections)
    if active():
        return [record for record in _committed_visible_records(page_store, campaign_slug, include_body=include_body)
                if str(record.page.section or "").strip() not in ignored_sections]
    return [
        page_record
        for page_record in page_store.list_page_records(campaign_slug, include_body=include_body)
        if getattr(page_record, "page", None) is not None
        and campaign.is_page_visible(page_record.page)
        and str(page_record.page.section or "").strip() not in ignored_sections
    ]


_ACTIVE_ITEM_BODY_SECTIONS = frozenset(
    {
        "shell",
        "overview",
        "spellcasting",
        "resources",
        "features",
        "abilities_skills",
    }
)
_ALL_CARRIED_ITEM_BODY_SECTIONS = frozenset(
    {"quick", "equipment", "inventory"}
)


def _page_ref(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("page_ref")
            or value.get("slug")
            or value.get("page_slug")
            or ""
        ).strip()
    return str(value or "").strip()


def _normalized_page_ref(value: Any) -> str:
    normalized = _page_ref(value).replace("\\", "/").strip().strip("/")
    if normalized.lower().endswith(".md"):
        normalized = normalized[:-3]
    return normalized.casefold()


def _record_ref_aliases(record: Any) -> frozenset[str]:
    page = getattr(record, "page", None)
    return frozenset(
        ref
        for raw_ref in (
            getattr(record, "page_ref", ""),
            getattr(page, "route_slug", ""),
        )
        if (ref := _normalized_page_ref(raw_ref))
    )


def _definition_page_refs(values: Iterable[Any]) -> set[str]:
    return {
        normalized
        for value in values
        if isinstance(value, dict)
        and (normalized := _normalized_page_ref(value.get("page_ref")))
    }


def _inventory_ref(value: dict[str, Any]) -> str:
    return str(value.get("catalog_ref") or value.get("id") or "").strip()


def _effective_inventory_items(definition: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    state_items = [
        dict(value)
        for value in list(dict(state or {}).get("inventory") or [])
        if isinstance(value, dict)
    ]
    state_by_ref = {
        item_ref: item
        for item in state_items
        if (item_ref := _inventory_ref(item))
    }
    effective: list[dict[str, Any]] = []
    matched_state_refs: set[str] = set()
    for raw_item in list(getattr(definition, "equipment_catalog", None) or []):
        item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
        item_ref = _inventory_ref(item)
        state_item = dict(state_by_ref.get(item_ref) or {}) if item_ref else {}
        if item_ref and state_item:
            matched_state_refs.add(item_ref)
        merged = {**item, **state_item}
        if not merged.get("name"):
            merged["name"] = item.get("name")
        if not merged.get("page_ref"):
            merged["page_ref"] = item.get("page_ref")
        if not merged.get("systems_ref"):
            merged["systems_ref"] = item.get("systems_ref")
        if "quantity" not in merged:
            merged["quantity"] = item.get("default_quantity", 0)
        effective.append(merged)

    for state_item in state_items:
        item_ref = _inventory_ref(state_item)
        if item_ref and item_ref in matched_state_refs:
            continue
        effective.append(dict(state_item))
    return effective


def _item_is_carried(item: dict[str, Any]) -> bool:
    try:
        return int(item.get("quantity") or item.get("default_quantity") or 0) > 0
    except (TypeError, ValueError):
        return False


def _item_is_active(item: dict[str, Any]) -> bool:
    return _item_is_carried(item) and bool(
        item.get("is_equipped") or str(item.get("weapon_wield_mode") or "").strip()
    )


def _matching_ref_indexes(
    campaign_page_records: list[Any],
    normalized_ref: str,
) -> list[int]:
    return [
        index
        for index, record in enumerate(campaign_page_records)
        if normalized_ref in _record_ref_aliases(record)
    ]


def _matching_item_title_indexes(
    campaign_page_records: list[Any],
    normalized_title: str,
) -> list[int]:
    return [
        index
        for index, record in enumerate(campaign_page_records)
        if str(getattr(getattr(record, "page", None), "section", "") or "").strip()
        == "Items"
        and normalize_lookup(
            str(getattr(getattr(record, "page", None), "title", "") or "").strip()
        )
        == normalized_title
    ]


def _item_title_candidates(item: dict[str, Any]) -> tuple[str, ...]:
    systems_ref = (
        dict(item.get("systems_ref") or {})
        if isinstance(item.get("systems_ref"), dict)
        else {}
    )
    candidates: list[str] = []
    for title in (item.get("name"), systems_ref.get("title")):
        normalized_title = normalize_lookup(str(title or "").strip())
        if normalized_title and normalized_title not in candidates:
            candidates.append(normalized_title)
    return tuple(candidates)


def _resolve_item_body_candidate_index(
    item: dict[str, Any],
    campaign_page_records: list[Any],
) -> int | None:
    normalized_ref = _normalized_page_ref(item.get("page_ref"))
    if normalized_ref:
        direct_candidates = _matching_ref_indexes(
            campaign_page_records,
            normalized_ref,
        )
        if len(direct_candidates) == 1:
            return direct_candidates[0]

    for normalized_title in _item_title_candidates(item):
        title_candidates = _matching_item_title_indexes(
            campaign_page_records,
            normalized_title,
        )
        if len(title_candidates) == 1:
            return title_candidates[0]
    return None


def materialize_dnd_character_read_page_records(
    page_store: Any,
    campaign_slug: str,
    campaign_page_records: list[Any],
    definition: Any,
    state: dict[str, Any] | None = None,
    *,
    section: str,
    campaign: Any | None = None,
) -> list[object]:
    """Load only bodies that the selected DND sheet section can consume.

    Direct refs and item-title fallbacks must resolve to exactly one metadata
    record. Ambiguous candidates retain metadata-only records instead of
    selecting an arbitrary campaign body.
    """

    from .committed_publication import active, config, current, page_row, read_snapshot

    if active():
        @read_snapshot
        def materialize_committed() -> list[object]:
            settings_source, settings = config(campaign_slug)
            for record in campaign_page_records:
                page = getattr(record, "page", None)
                if (page is None or page.committed_config_revision != settings_source["revision"]
                        or not page.committed_revision or not page.published
                        or page.is_deprecated_wiki_overview
                        or page.reveal_after_session > int(settings["current_session"])):
                    return []
                proved = page_row(campaign_slug, record.page_ref)
                source = current(campaign_slug, "page", record.page_ref)
                if (proved is None or source is None or source["revision"] != page.committed_revision):
                    return []
            return _materialize_dnd_character_read_page_records(
                page_store, campaign_slug, campaign_page_records, definition, state,
                section=section, campaign=None, committed=True,
            )

        return materialize_committed()
    return _materialize_dnd_character_read_page_records(
        page_store, campaign_slug, campaign_page_records, definition, state,
        section=section, campaign=campaign, committed=False,
    )


def _materialize_dnd_character_read_page_records(
    page_store: Any, campaign_slug: str, campaign_page_records: list[Any],
    definition: Any, state: dict[str, Any] | None, *, section: str,
    campaign: Any | None, committed: bool,
) -> list[object]:
    from .committed_publication import current

    normalized_section = str(section or "").strip().lower()
    refs: set[str] = set()
    selected_items: list[dict[str, Any]] = []

    if normalized_section == "features":
        refs.update(_definition_page_refs(list(definition.features or [])))
    if normalized_section in {"spells", "spellcasting"}:
        spellcasting = dict(definition.spellcasting or {})
        refs.update(_definition_page_refs(list(spellcasting.get("spells") or [])))
    if normalized_section in _ACTIVE_ITEM_BODY_SECTIONS:
        effective_items = _effective_inventory_items(definition, dict(state or {}))
        selected_items = [item for item in effective_items if _item_is_active(item)]
    elif normalized_section in _ALL_CARRIED_ITEM_BODY_SECTIONS:
        effective_items = _effective_inventory_items(definition, dict(state or {}))
        selected_items = [item for item in effective_items if _item_is_carried(item)]

    matched_indexes: set[int] = set()
    for normalized_ref in refs:
        candidates = _matching_ref_indexes(campaign_page_records, normalized_ref)
        if len(candidates) == 1:
            matched_indexes.add(candidates[0])

    for item in selected_items:
        candidate_index = _resolve_item_body_candidate_index(
            item,
            campaign_page_records,
        )
        if candidate_index is not None:
            matched_indexes.add(candidate_index)

    materialized_by_index: dict[int, Any] = {}
    for index in sorted(matched_indexes):
        metadata_record = campaign_page_records[index]
        metadata_page = getattr(metadata_record, "page", None)
        if bool(getattr(metadata_page, "content_loaded", False)):
            continue
        canonical_ref = str(getattr(metadata_record, "page_ref", "") or "").strip()
        if not canonical_ref:
            continue
        full_record = page_store.get_page_record(
            campaign_slug,
            canonical_ref,
            include_body=True,
        )
        full_source = current(campaign_slug, "page", canonical_ref) if committed else None
        if (
            full_record is not None
            and _normalized_page_ref(getattr(full_record, "page_ref", ""))
            == _normalized_page_ref(canonical_ref)
            and str(getattr(full_record, "updated_at", "") or "").strip()
            == str(getattr(metadata_record, "updated_at", "") or "").strip()
            and (not committed or (
                full_source is not None
                and full_source["revision"] == getattr(metadata_page, "committed_revision", None)
            ))
            and (
                campaign is None
                or (
                    getattr(full_record, "page", None) is not None
                    and campaign.is_page_visible(full_record.page)
                )
            )
        ):
            if committed:
                full_record.page.committed_revision = metadata_page.committed_revision
                full_record.page.committed_config_revision = metadata_page.committed_config_revision
            materialized_by_index[index] = full_record

    return [
        materialized_by_index.get(index, record)
        for index, record in enumerate(campaign_page_records)
    ]
