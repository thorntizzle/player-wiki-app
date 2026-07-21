from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
import re
from functools import lru_cache
from pathlib import Path
from threading import Event, RLock
from typing import Any, Callable, TypeVar

from flask import g, has_request_context

from .auth_store import isoformat
from .character_builder_constants import (
    ABILITY_KEYS,
    BUILDER_PROGRESS_CACHE_MAX_ENTRIES,
    BUILDER_PROGRESS_ENTRY_TYPES,
    BUILDER_STATIC_CACHE_MAX_ENTRIES,
    BUILDER_STATIC_ENTRY_TYPES,
    CAMPAIGN_ITEMS_SECTION,
    CAMPAIGN_MECHANICS_SECTION,
    CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND,
    CAMPAIGN_SESSIONS_SECTION,
    EXTRA_PHB_LEVEL_ONE_SPELL_LISTS,
)
from .character_builder_derivation import _build_campaign_option_entry
from .character_builder_equipment import _load_phb_armor_profiles, _load_phb_weapon_profiles
from .character_builder_foundation import (
    _class_supports_shared_slot_multiclass,
    _entry_page_ref,
    _entry_selection_value,
    _extract_campaign_page_ref,
    _subclass_supports_shared_slot_multiclass,
    _supports_native_class_entry,
    _supports_native_subclass_entry,
)
from .character_builder_spells import _merge_name_candidates
from .character_campaign_options import build_campaign_page_character_option
from .repository import normalize_lookup
from .systems_models import SystemsEntryRecord

__all__ = [
    "_builder_request_cache",
    "_builder_cache_get",
    "_clear_builder_static_bundle_cache",
    "_builder_static_cache_get",
    "_builder_progress_cache_get",
    "_builder_revision_part",
    "_extract_campaign_page_updated_at",
    "_builder_request_page_key",
    "_builder_service_cache_identity",
    "_builder_static_revision_key",
    "_sort_entries_for_builder",
    "_class_progression_for_builder",
    "_subclass_progression_for_builder",
    "_list_supported_class_entries",
    "_list_shared_slot_multiclass_class_entries",
    "_list_shared_slot_multiclass_subclass_options",
    "_list_campaign_enabled_entries",
    "_list_subclass_options",
    "_build_mixed_character_options",
    "_build_campaign_page_entries",
    "_build_campaign_page_entry",
    "_campaign_page_option_allowed_for_mixed_source",
    "_load_phb_level_one_spell_lists",
    "_build_item_catalog",
    "_attach_campaign_item_page_support",
    "_build_campaign_item_page_support",
    "_build_campaign_item_support_metadata",
    "_campaign_item_page_support_metadata",
    "_campaign_item_special_effect_metadata",
    "_merge_campaign_item_support_metadata",
    "_resolve_campaign_item_weapon_title",
    "_build_spell_catalog",
    "_build_feat_catalog",
    "_build_entry_slug_catalog",
]


_BUILDER_STATIC_BUNDLE_CACHE: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
_BUILDER_PROGRESS_CACHE: OrderedDict[tuple[Any, ...], list[dict[str, Any]]] = OrderedDict()
_BUILDER_STATIC_BUNDLE_FLIGHTS: dict[tuple[Any, ...], "_BuilderCacheFlight"] = {}
_BUILDER_PROGRESS_FLIGHTS: dict[tuple[Any, ...], "_BuilderCacheFlight"] = {}
_BUILDER_STATIC_BUNDLE_CACHE_LOCK = RLock()
_BUILDER_CACHE_GENERATION = 0
_BuilderCacheValue = TypeVar("_BuilderCacheValue")


class _BuilderCacheFlight:
    def __init__(self, generation: int) -> None:
        self.generation = generation
        self.event = Event()
        self.value: Any = None
        self.error: BaseException | None = None


def _builder_request_cache() -> dict[tuple[Any, ...], Any] | None:
    if not has_request_context():
        return None
    cache = getattr(g, "_character_builder_request_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    g._character_builder_request_cache = cache
    return cache


def _builder_cache_get(cache_key: tuple[Any, ...], build_value):
    cache = _builder_request_cache()
    if cache is None:
        return build_value()
    if cache_key not in cache:
        cache[cache_key] = build_value()
    return cache[cache_key]


def _clear_builder_static_bundle_cache() -> None:
    global _BUILDER_CACHE_GENERATION
    with _BUILDER_STATIC_BUNDLE_CACHE_LOCK:
        _BUILDER_CACHE_GENERATION += 1
        _BUILDER_STATIC_BUNDLE_CACHE.clear()
        _BUILDER_PROGRESS_CACHE.clear()
        # Existing builders still wake their existing waiters, but cannot
        # repopulate a cache after this clear. New callers start fresh flights.
        _BUILDER_STATIC_BUNDLE_FLIGHTS.clear()
        _BUILDER_PROGRESS_FLIGHTS.clear()


def _builder_process_cache_get(
    cache: OrderedDict[tuple[Any, ...], _BuilderCacheValue],
    flights: dict[tuple[Any, ...], _BuilderCacheFlight],
    cache_key: tuple[Any, ...],
    build_value: Callable[[], _BuilderCacheValue],
    *,
    max_entries: int,
) -> _BuilderCacheValue:
    with _BUILDER_STATIC_BUNDLE_CACHE_LOCK:
        if cache_key in cache:
            cache.move_to_end(cache_key)
            return cache[cache_key]
        flight = flights.get(cache_key)
        is_builder = flight is None
        if flight is None:
            flight = _BuilderCacheFlight(_BUILDER_CACHE_GENERATION)
            flights[cache_key] = flight

    if not is_builder:
        flight.event.wait()
        if flight.error is not None:
            raise flight.error
        return flight.value

    try:
        value = build_value()
    except BaseException as exc:
        with _BUILDER_STATIC_BUNDLE_CACHE_LOCK:
            flight.error = exc
            if flights.get(cache_key) is flight:
                flights.pop(cache_key, None)
            flight.event.set()
        raise

    with _BUILDER_STATIC_BUNDLE_CACHE_LOCK:
        flight.value = value
        if (
            flights.get(cache_key) is flight
            and flight.generation == _BUILDER_CACHE_GENERATION
        ):
            cache[cache_key] = value
            cache.move_to_end(cache_key)
            while len(cache) > max_entries:
                cache.popitem(last=False)
            flights.pop(cache_key, None)
        flight.event.set()
    return value


def _builder_static_cache_get(
    cache_key: tuple[Any, ...],
    build_value: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return _builder_process_cache_get(
        _BUILDER_STATIC_BUNDLE_CACHE,
        _BUILDER_STATIC_BUNDLE_FLIGHTS,
        cache_key,
        build_value,
        max_entries=BUILDER_STATIC_CACHE_MAX_ENTRIES,
    )


def _builder_progress_cache_get(
    cache_key: tuple[Any, ...],
    build_value: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return _builder_process_cache_get(
        _BUILDER_PROGRESS_CACHE,
        _BUILDER_PROGRESS_FLIGHTS,
        cache_key,
        lambda: list(build_value() or []),
        max_entries=BUILDER_PROGRESS_CACHE_MAX_ENTRIES,
    )


def _builder_revision_part(value: Any) -> str:
    if value is None:
        return ""
    try:
        if hasattr(value, "astimezone"):
            return isoformat(value)
    except (TypeError, ValueError, AttributeError):
        pass
    return str(value or "").strip()


def _extract_campaign_page_updated_at(payload: Any) -> str:
    if isinstance(payload, dict):
        return _builder_revision_part(
            payload.get("updated_at")
            or payload.get("page_updated_at")
            or payload.get("last_modified")
        )
    page = getattr(payload, "page", None)
    return _builder_revision_part(
        getattr(payload, "updated_at", "")
        or getattr(page, "updated_at", "")
    )


def _builder_request_page_key(campaign_page_records: list[Any] | None) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            {
                (
                    page_ref,
                    _extract_campaign_page_updated_at(record),
                )
                for record in list(campaign_page_records or [])
                for page_ref in [_extract_campaign_page_ref(record)]
                if page_ref
            }
        )
    )


def _builder_service_cache_identity(systems_service: Any) -> tuple[Any, ...]:
    try:
        hash(systems_service)
    except TypeError:
        return (
            "service-id",
            type(systems_service).__module__,
            type(systems_service).__qualname__,
            id(systems_service),
        )
    return ("service-object", systems_service)


def _builder_static_revision_key(
    systems_service: Any,
    campaign_slug: str,
    *,
    entry_types: tuple[str, ...] = BUILDER_STATIC_ENTRY_TYPES,
) -> tuple[Any, ...] | None:
    normalized_entry_types = tuple(sorted(str(entry_type or "").strip() for entry_type in entry_types))

    def _load_revision_key() -> tuple[Any, ...] | None:
        revision_loader = getattr(systems_service, "get_builder_static_revision", None)
        if not callable(revision_loader):
            return None
        revision = revision_loader(campaign_slug, entry_types=normalized_entry_types)
        if revision is None:
            return None
        if isinstance(revision, tuple):
            return revision
        if isinstance(revision, list):
            return tuple(revision)
        return (revision,)

    return _builder_cache_get(
        (
            "builder-static-revision",
            _builder_service_cache_identity(systems_service),
            campaign_slug,
            normalized_entry_types,
        ),
        _load_revision_key,
    )


def _sort_entries_for_builder(entries: list[SystemsEntryRecord]) -> list[SystemsEntryRecord]:
    deduped_entries: list[SystemsEntryRecord] = []
    seen_entry_keys: set[str] = set()
    for entry in list(entries or []):
        entry_key = str(entry.entry_key or "").strip()
        if entry_key and entry_key in seen_entry_keys:
            continue
        if entry_key:
            seen_entry_keys.add(entry_key)
        deduped_entries.append(entry)
    return sorted(
        deduped_entries,
        key=lambda entry: (
            normalize_lookup(entry.title),
            str(entry.source_id or "").strip().upper(),
            str(entry.slug or "").strip(),
        ),
    )


def _class_progression_for_builder(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    service_key = _builder_service_cache_identity(systems_service)
    revision_key = _builder_static_revision_key(
        systems_service,
        campaign_slug,
        entry_types=BUILDER_PROGRESS_ENTRY_TYPES,
    )
    page_key = _builder_request_page_key(campaign_page_records)
    entry_key = str(selected_class.entry_key or "").strip()

    def _load_progression() -> list[dict[str, Any]]:
        return list(
            systems_service.build_class_feature_progression_for_class_entry(
                campaign_slug,
                selected_class,
            )
            or []
        )

    def _load_or_cache_progression() -> list[dict[str, Any]]:
        if revision_key is None or campaign_page_records is None:
            return _load_progression()
        return _builder_progress_cache_get(
            (
                "class-progression",
                service_key,
                campaign_slug,
                revision_key,
                page_key,
                entry_key,
            ),
            _load_progression,
        )

    return list(
        _builder_cache_get(
            (
                "class-progression",
                service_key,
                campaign_slug,
                revision_key,
                page_key,
                entry_key,
            ),
            _load_or_cache_progression,
        )
        or []
    )


def _subclass_progression_for_builder(
    systems_service: Any,
    campaign_slug: str,
    selected_subclass: SystemsEntryRecord | None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if selected_subclass is None:
        return []
    service_key = _builder_service_cache_identity(systems_service)
    revision_key = _builder_static_revision_key(
        systems_service,
        campaign_slug,
        entry_types=BUILDER_PROGRESS_ENTRY_TYPES,
    )
    page_key = _builder_request_page_key(campaign_page_records)
    entry_key = str(selected_subclass.entry_key or "").strip()

    def _load_progression() -> list[dict[str, Any]]:
        return list(
            systems_service.build_subclass_feature_progression_for_subclass_entry(
                campaign_slug,
                selected_subclass,
            )
            or []
        )

    def _load_or_cache_progression() -> list[dict[str, Any]]:
        if revision_key is None or campaign_page_records is None:
            return _load_progression()
        return _builder_progress_cache_get(
            (
                "subclass-progression",
                service_key,
                campaign_slug,
                revision_key,
                page_key,
                entry_key,
            ),
            _load_progression,
        )

    return list(
        _builder_cache_get(
            (
                "subclass-progression",
                service_key,
                campaign_slug,
                revision_key,
                page_key,
                entry_key,
            ),
            _load_or_cache_progression,
        )
        or []
    )


def _list_supported_class_entries(
    systems_service: Any,
    campaign_slug: str,
) -> list[SystemsEntryRecord]:
    class_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "class")
    return [entry for entry in class_entries if _supports_native_class_entry(entry)]


def _list_shared_slot_multiclass_class_entries(
    systems_service: Any,
    campaign_slug: str,
    *,
    campaign_page_records: list[Any] | None = None,
) -> list[SystemsEntryRecord]:
    return [
        entry
        for entry in _list_supported_class_entries(systems_service, campaign_slug)
        if _class_supports_shared_slot_multiclass(
            systems_service,
            campaign_slug,
            entry,
            campaign_page_records=campaign_page_records,
        )
    ]


def _list_shared_slot_multiclass_subclass_options(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    subclass_entries: list[SystemsEntryRecord] | None = None,
    campaign_page_records: list[Any] | None = None,
) -> list[SystemsEntryRecord]:
    return [
        entry
        for entry in _list_subclass_options(
            systems_service,
            campaign_slug,
            selected_class,
            subclass_entries=subclass_entries,
        )
        if _subclass_supports_shared_slot_multiclass(
            systems_service,
            campaign_slug,
            entry,
            selected_class=selected_class,
            campaign_page_records=campaign_page_records,
        )
    ]


def _list_campaign_enabled_entries(
    systems_service: Any,
    campaign_slug: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    def _load_entries() -> list[SystemsEntryRecord]:
        list_enabled_entries = getattr(systems_service, "list_enabled_entries_for_campaign", None)
        if callable(list_enabled_entries):
            return _sort_entries_for_builder(
                list_enabled_entries(
                    campaign_slug,
                    entry_type=entry_type,
                    limit=None,
                )
            )

        library = systems_service.get_campaign_library(campaign_slug)
        if library is None:
            return []
        enabled_source_ids = [
            str(row.source.source_id or "").strip()
            for row in list(systems_service.list_campaign_source_states(campaign_slug) or [])
            if getattr(row, "is_enabled", False) and str(getattr(row.source, "source_id", "") or "").strip()
        ]
        if not enabled_source_ids:
            return []

        entries: list[SystemsEntryRecord] = []
        for source_id in enabled_source_ids:
            entries.extend(
                systems_service.list_entries_for_campaign_source(
                    campaign_slug,
                    source_id,
                    entry_type=entry_type,
                    limit=None,
                )
            )
        is_entry_enabled = getattr(systems_service, "is_entry_enabled_for_campaign", None)
        if callable(is_entry_enabled):
            entries = [
                entry
                for entry in entries
                if is_entry_enabled(campaign_slug, entry)
            ]
        return _sort_entries_for_builder(entries)

    return list(
        _builder_cache_get(
            ("enabled-entries", campaign_slug, entry_type),
            _load_entries,
        )
        or []
    )


def _list_subclass_options(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    subclass_entries: list[SystemsEntryRecord] | None = None,
) -> list[SystemsEntryRecord]:
    if selected_class is None:
        return []
    options = list(
        subclass_entries
        if subclass_entries is not None
        else _list_campaign_enabled_entries(systems_service, campaign_slug, "subclass")
    )
    return [
        entry
        for entry in options
        if str(entry.metadata.get("class_name") or "").strip() == selected_class.title
        and str(entry.metadata.get("class_source") or "").strip().upper() == selected_class.source_id
        and _supports_native_subclass_entry(entry, selected_class=selected_class)
    ]


def _build_mixed_character_options(
    systems_entries: list[SystemsEntryRecord],
    campaign_page_records: list[Any],
    *,
    kind: str,
) -> list[SystemsEntryRecord]:
    options = list(systems_entries or [])
    options.extend(_build_campaign_page_entries(campaign_page_records, kind=kind))
    return options


def _build_campaign_page_entries(
    campaign_page_records: list[Any],
    *,
    kind: str,
) -> list[SystemsEntryRecord]:
    entries: list[SystemsEntryRecord] = []
    seen_page_refs: set[str] = set()
    for record in list(campaign_page_records or []):
        entry = _build_campaign_page_entry(record, kind=kind)
        if entry is None:
            continue
        page_ref = _entry_page_ref(entry)
        if page_ref in seen_page_refs:
            continue
        seen_page_refs.add(page_ref)
        entries.append(entry)
    return sorted(entries, key=lambda entry: (normalize_lookup(entry.title), _entry_page_ref(entry)))


def _build_campaign_page_entry(
    record: Any,
    *,
    kind: str,
) -> SystemsEntryRecord | None:
    page_ref = _extract_campaign_page_ref(record)
    page = getattr(record, "page", None)
    if not page_ref or page is None:
        return None
    section = str(getattr(page, "section", "") or "").strip()
    if section == CAMPAIGN_SESSIONS_SECTION:
        return None

    campaign_option = build_campaign_page_character_option(
        record,
        default_kind="item" if section == CAMPAIGN_ITEMS_SECTION else "feature",
    )
    if not _campaign_page_option_allowed_for_mixed_source(
        record,
        kind=kind,
    ):
        return None

    return _build_campaign_option_entry(
        campaign_option=campaign_option,
        page_ref=page_ref,
        title=str(getattr(page, "title", "") or ""),
        summary=str(getattr(page, "summary", "") or ""),
        section=section,
        subsection=str(getattr(page, "subsection", "") or ""),
        kind=kind,
    )


def _campaign_page_option_allowed_for_mixed_source(
    record: Any,
    *,
    kind: str,
) -> bool:
    if kind not in CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND:
        return True
    page = getattr(record, "page", None)
    if page is None:
        return False
    section = str(getattr(page, "section", "") or "").strip()
    if section != CAMPAIGN_MECHANICS_SECTION:
        return False
    subsection = normalize_lookup(str(getattr(page, "subsection", "") or "").strip())
    if not subsection:
        return True
    return subsection in CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND.get(kind, set())


@lru_cache(maxsize=1)
def _load_phb_level_one_spell_lists() -> dict[str, dict[str, list[str]]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_level_one_spell_lists.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, list[str]]] = {}
    for class_name, levels in payload.items():
        if not isinstance(levels, dict):
            continue
        normalized[str(class_name)] = {
            str(level_key): [str(item).strip() for item in list(level_values or []) if str(item).strip()]
            for level_key, level_values in levels.items()
        }
    for class_name, levels in EXTRA_PHB_LEVEL_ONE_SPELL_LISTS.items():
        class_payload = normalized.setdefault(str(class_name), {})
        for level_key, titles in levels.items():
            existing_titles = list(class_payload.get(str(level_key)) or [])
            merged_titles = existing_titles + [title for title in titles if title not in existing_titles]
            class_payload[str(level_key)] = merged_titles
    return normalized


def _build_item_catalog(item_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_title: dict[str, SystemsEntryRecord] = {}
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in item_entries:
        normalized_title = normalize_lookup(entry.title)
        if normalized_title and normalized_title not in by_title:
            by_title[normalized_title] = entry
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
    return {
        "entries": list(item_entries),
        "by_title": by_title,
        "by_slug": by_slug,
        "phb_weapon_profiles": _load_phb_weapon_profiles(),
        "phb_armor_profiles": _load_phb_armor_profiles(),
        "campaign_item_support_by_page_ref": {},
        "campaign_item_support_by_title": {},
    }


_CAMPAIGN_ITEM_CLASSIFICATION_RARITY_PATTERN = re.compile(
    r"\b(very rare|legendary|artifact|uncommon|common|rare)\b",
    re.IGNORECASE,
)
_CAMPAIGN_ITEM_CLASSIFICATION_WEAPON_PATTERN = re.compile(
    r"\bweapon(?:\s*\(([^)]+)\)|\s*,\s*([^,]+))",
    re.IGNORECASE,
)
_CAMPAIGN_ITEM_BODY_WEAPON_PATTERNS = (
    re.compile(r"\bcan be wielded as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
    re.compile(r"\bcan be used as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
    re.compile(r"\bfunctions as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
)
_CAMPAIGN_ITEM_SHARED_WEAPON_BONUS_PATTERNS = (
    re.compile(r"\+(\d+)\s+bonus to attack and damage rolls", re.IGNORECASE),
    re.compile(r"\+(\d+)\s+bonus to attack rolls and damage rolls", re.IGNORECASE),
)
_CAMPAIGN_ITEM_ATTACK_BONUS_PATTERN = re.compile(r"\+(\d+)\s+bonus to attack rolls", re.IGNORECASE)
_CAMPAIGN_ITEM_DAMAGE_BONUS_PATTERN = re.compile(r"\+(\d+)\s+bonus to damage rolls", re.IGNORECASE)
_CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS = (
    "ability_score_minimums",
    "attack_reminder_rules",
    "attunement",
    "base_item",
    "bonus_weapon",
    "bonus_weapon_attack",
    "bonus_weapon_damage",
    "defensive_rules",
    "item_use_actions",
    "rarity",
    "resource_template_bonuses",
    "spell_support",
)


def _attach_campaign_item_page_support(
    item_catalog: dict[str, Any] | None,
    campaign_page_records: list[Any] | None,
) -> dict[str, Any]:
    resolved_catalog = dict(item_catalog or _build_item_catalog([]))
    by_page_ref = dict(resolved_catalog.get("campaign_item_support_by_page_ref") or {})
    by_title = dict(resolved_catalog.get("campaign_item_support_by_title") or {})
    weapon_profiles = dict(resolved_catalog.get("phb_weapon_profiles") or _load_phb_weapon_profiles())
    for page_record in list(campaign_page_records or []):
        support = _build_campaign_item_page_support(page_record, weapon_profiles=weapon_profiles)
        if support is None:
            continue
        page_ref = str(support.get("page_ref") or "").strip()
        title_key = normalize_lookup(str(support.get("title") or "").strip())
        if page_ref and page_ref not in by_page_ref:
            by_page_ref[page_ref] = support
        if title_key and title_key not in by_title:
            by_title[title_key] = support
    resolved_catalog["campaign_item_support_by_page_ref"] = by_page_ref
    resolved_catalog["campaign_item_support_by_title"] = by_title
    return resolved_catalog


def _build_campaign_item_page_support(
    page_record: Any,
    *,
    weapon_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    page = getattr(page_record, "page", None)
    page_ref = str(getattr(page_record, "page_ref", "") or "").strip()
    title = str(getattr(page, "title", "") or "").strip()
    section = str(getattr(page, "section", "") or "").strip()
    if not page_ref or not title or section != CAMPAIGN_ITEMS_SECTION:
        return None
    metadata = _build_campaign_item_support_metadata(
        title,
        str(getattr(page_record, "body_markdown", "") or ""),
        weapon_profiles=weapon_profiles,
    )
    page_support_metadata = _campaign_item_page_support_metadata(page_record)
    if page_support_metadata:
        metadata = _merge_campaign_item_support_metadata(metadata, page_support_metadata)
    if not metadata:
        return None
    return {
        "page_ref": page_ref,
        "title": title,
        "metadata": metadata,
    }


def _build_campaign_item_support_metadata(
    title: str,
    body_markdown: str,
    *,
    weapon_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lines = [str(line or "").strip() for line in str(body_markdown or "").splitlines() if str(line or "").strip()]
    classification_line = ""
    for line in lines:
        if line.startswith("*") and line.endswith("*"):
            classification_line = line.strip("*").strip()
            break
    if not classification_line and lines:
        classification_line = lines[0]

    metadata: dict[str, Any] = {}
    if classification_line:
        rarity_match = _CAMPAIGN_ITEM_CLASSIFICATION_RARITY_PATTERN.search(classification_line)
        if rarity_match is not None:
            metadata["rarity"] = rarity_match.group(1).strip().lower()
        if "requires attunement" in classification_line.lower():
            metadata["attunement"] = classification_line
        weapon_match = _CAMPAIGN_ITEM_CLASSIFICATION_WEAPON_PATTERN.search(classification_line)
        if weapon_match is not None:
            base_weapon = _resolve_campaign_item_weapon_title(
                weapon_match.group(1) or weapon_match.group(2) or "",
                weapon_profiles=weapon_profiles,
            )
            if base_weapon:
                metadata["base_item"] = base_weapon

    body_text = " ".join(lines)
    if "attunement" not in metadata and "requires attunement" in body_text.lower():
        metadata["attunement"] = "requires attunement"
    if "base_item" not in metadata:
        for pattern in _CAMPAIGN_ITEM_BODY_WEAPON_PATTERNS:
            match = pattern.search(body_text)
            if match is None:
                continue
            base_weapon = _resolve_campaign_item_weapon_title(match.group(1) or "", weapon_profiles=weapon_profiles)
            if base_weapon:
                metadata["base_item"] = base_weapon
                break

    shared_bonus_match = None
    for pattern in _CAMPAIGN_ITEM_SHARED_WEAPON_BONUS_PATTERNS:
        shared_bonus_match = pattern.search(body_text)
        if shared_bonus_match is not None:
            break
    if shared_bonus_match is not None:
        metadata["bonus_weapon"] = int(shared_bonus_match.group(1) or 0)
        return metadata

    attack_bonus_match = _CAMPAIGN_ITEM_ATTACK_BONUS_PATTERN.search(body_text)
    if attack_bonus_match is not None:
        metadata["bonus_weapon_attack"] = int(attack_bonus_match.group(1) or 0)
    damage_bonus_match = _CAMPAIGN_ITEM_DAMAGE_BONUS_PATTERN.search(body_text)
    if damage_bonus_match is not None:
        metadata["bonus_weapon_damage"] = int(damage_bonus_match.group(1) or 0)
    return metadata


def _campaign_item_page_support_metadata(page_record: Any) -> dict[str, Any]:
    metadata = dict(getattr(page_record, "metadata", {}) or {})
    support_metadata: dict[str, Any] = {}
    for key in _CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS:
        value = metadata.get(key)
        if value is None or value == "" or value == [] or value == {}:
            continue
        support_metadata[key] = deepcopy(value)
    return support_metadata


def _campaign_item_special_effect_metadata(title: str) -> dict[str, Any]:
    return {}


def _merge_campaign_item_support_metadata(
    base_metadata: dict[str, Any],
    extra_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base_metadata or {})
    for key, value in dict(extra_metadata or {}).items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if key in {
            "spell_support",
            "defensive_rules",
            "resource_template_bonuses",
            "attack_reminder_rules",
            "item_use_actions",
        }:
            merged[key] = [
                dict(item or {}) if isinstance(item, dict) else item
                for item in list(merged.get(key) or [])
            ] + [
                dict(item or {}) if isinstance(item, dict) else item
                for item in list(value or [])
            ]
            continue
        if key == "ability_score_minimums":
            merged[key] = {
                **{
                    normalize_lookup(ability_key): int(minimum)
                    for ability_key, minimum in dict(merged.get(key) or {}).items()
                    if normalize_lookup(ability_key) in ABILITY_KEYS
                },
                **{
                    normalize_lookup(ability_key): int(minimum)
                    for ability_key, minimum in dict(value or {}).items()
                    if normalize_lookup(ability_key) in ABILITY_KEYS
                },
            }
            continue
        merged[key] = deepcopy(value)
    return merged


def _resolve_campaign_item_weapon_title(
    raw_value: Any,
    *,
    weapon_profiles: dict[str, dict[str, Any]],
) -> str:
    profiles_by_norm = {
        normalize_lookup(title): str(title or "").strip()
        for title in list(weapon_profiles.keys())
        if str(title or "").strip()
    }
    for candidate_key in _merge_name_candidates(raw_value):
        title = profiles_by_norm.get(candidate_key)
        if title:
            return title
    return ""


def _build_spell_catalog(spell_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_title: dict[str, SystemsEntryRecord] = {}
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in spell_entries:
        normalized_title = normalize_lookup(entry.title)
        if normalized_title and normalized_title not in by_title:
            by_title[normalized_title] = entry
        if entry.slug:
            by_slug[entry.slug] = entry
    return {
        "entries": list(spell_entries),
        "by_title": by_title,
        "by_slug": by_slug,
        "phb_level_one_lists": _load_phb_level_one_spell_lists(),
    }


def _build_feat_catalog(feat_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_slug: dict[str, SystemsEntryRecord] = {}
    by_value: dict[str, SystemsEntryRecord] = {}
    for entry in feat_entries:
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
        for candidate in (_entry_selection_value(entry), _entry_page_ref(entry), slug):
            clean_candidate = str(candidate or "").strip()
            if clean_candidate and clean_candidate not in by_value:
                by_value[clean_candidate] = entry
    return {
        "entries": list(feat_entries),
        "by_slug": by_slug,
        "by_value": by_value,
    }


def _build_entry_slug_catalog(entries: list[SystemsEntryRecord]) -> dict[str, SystemsEntryRecord]:
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in list(entries or []):
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
    return by_slug
