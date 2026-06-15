from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .repository import normalize_lookup
from .system_policy import DND_5E_SYSTEM_CODE
from .systems_models import SystemsEntryRecord
from .systems_store import SystemsStore


@dataclass(slots=True)
class SystemsMetadataRepairChange:
    entry_key: str
    slug: str
    title: str
    source_id: str
    fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SystemsMetadataRepairResult:
    scanned_count: int = 0
    repairable_count: int = 0
    repaired_count: int = 0
    changes: list[SystemsMetadataRepairChange] = field(default_factory=list)


def repair_dnd5e_item_metadata(
    store: SystemsStore,
    *,
    dry_run: bool = False,
    source_ids: list[str] | None = None,
) -> SystemsMetadataRepairResult:
    """Backfill stale shared item metadata without changing character derivation rules."""

    result = SystemsMetadataRepairResult()
    offset = 0
    page_size = 500
    normalized_source_ids = [
        str(source_id or "").strip().upper()
        for source_id in list(source_ids or [])
        if str(source_id or "").strip()
    ] or None

    while True:
        entries = store.list_entries(
            DND_5E_SYSTEM_CODE,
            source_ids=normalized_source_ids,
            entry_type="item",
            limit=page_size,
            offset=offset,
        )
        if not entries:
            break
        for entry in entries:
            result.scanned_count += 1
            repaired_metadata, fields = repair_dnd5e_item_metadata_payload(entry)
            if not fields:
                continue
            result.repairable_count += 1
            result.changes.append(
                SystemsMetadataRepairChange(
                    entry_key=entry.entry_key,
                    slug=entry.slug,
                    title=entry.title,
                    source_id=entry.source_id,
                    fields=fields,
                )
            )
            if dry_run:
                continue
            store.upsert_entry(
                entry.library_slug,
                entry.source_id,
                entry_key=entry.entry_key,
                entry_type=entry.entry_type,
                slug=entry.slug,
                title=entry.title,
                source_page=entry.source_page,
                source_path=entry.source_path,
                search_text=entry.search_text,
                player_safe_default=entry.player_safe_default,
                dm_heavy=entry.dm_heavy,
                metadata=repaired_metadata,
                body=entry.body,
                rendered_html=entry.rendered_html,
            )
            result.repaired_count += 1
        offset += len(entries)
    return result


def repair_dnd5e_item_metadata_payload(entry: SystemsEntryRecord) -> tuple[dict[str, Any], list[str]]:
    metadata = dict(entry.metadata or {})
    profile = _resolve_armor_profile_for_entry(entry, metadata)
    if profile is None:
        return metadata, []

    fields: list[str] = []

    def set_if_missing(key: str, value: Any) -> None:
        if _metadata_value_present(metadata.get(key)):
            return
        metadata[key] = value
        fields.append(key)

    set_if_missing("type", profile["type"])
    set_if_missing("ac", int(profile["base_ac"]))
    if metadata.get("armor") is not True:
        metadata["armor"] = True
        fields.append("armor")

    minimum_strength = profile.get("minimum_strength")
    if minimum_strength not in (None, ""):
        set_if_missing("strength", int(minimum_strength))

    stealth_disadvantage = bool(profile.get("stealth_disadvantage"))
    if metadata.get("stealth_disadvantage") != stealth_disadvantage:
        metadata["stealth_disadvantage"] = stealth_disadvantage
        fields.append("stealth_disadvantage")

    parsed_bonus = int(profile.get("parsed_bonus") or 0)
    if parsed_bonus > 0:
        if _parse_optional_int_value(metadata.get("bonus_ac")) != parsed_bonus:
            metadata["bonus_ac"] = f"+{parsed_bonus}"
            fields.append("bonus_ac")
        set_if_missing("base_item", f"{profile['title']}|PHB")

    return metadata, fields


def _metadata_value_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _parse_optional_int_value(value: Any) -> int | None:
    if value in (None, "", [], {}):
        return None
    match = re.search(r"-?\d+", str(value))
    if match is None:
        return None
    return int(match.group(0))


def _resolve_armor_profile_for_entry(
    entry: SystemsEntryRecord,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    profiles = _load_phb_armor_profiles()
    _entry_base_title, entry_title_bonus = _split_magic_item_name(str(entry.title or "").strip())
    candidate_titles = [
        str(metadata.get("base_item") or "").split("|", 1)[0].strip(),
        str(entry.title or "").strip(),
    ]
    seen: set[str] = set()
    for raw_title in candidate_titles:
        if not raw_title:
            continue
        base_title, parsed_bonus = _split_magic_item_name(raw_title)
        for candidate in _title_candidates(base_title):
            if candidate in seen:
                continue
            seen.add(candidate)
            profile = profiles.get(candidate)
            if profile is None:
                continue
            effective_bonus = parsed_bonus or entry_title_bonus
            return {
                "title": str(profile.get("title") or base_title).strip(),
                "type": str(profile.get("type") or "").strip().upper(),
                "base_ac": int(profile.get("base_ac") or 0),
                "minimum_strength": profile.get("minimum_strength"),
                "stealth_disadvantage": bool(profile.get("stealth_disadvantage")),
                "parsed_bonus": effective_bonus,
            }
    return None


def _title_candidates(title: str) -> list[str]:
    candidates = [title]
    if "," in title:
        parts = [part.strip() for part in title.split(",", 1)]
        if len(parts) == 2 and all(parts):
            candidates.append(f"{parts[1]} {parts[0]}")
    if normalize_lookup(title) == normalize_lookup("Chain Mail"):
        candidates.append("Chain Mail Armor")

    normalized: list[str] = []
    for candidate in candidates:
        key = normalize_lookup(candidate)
        if key and key not in normalized:
            normalized.append(key)
    return normalized


def _split_magic_item_name(raw_name: Any) -> tuple[str, int]:
    cleaned = str(raw_name or "").strip()
    if not cleaned:
        return "", 0
    prefix_match = re.match(r"^\+(\d+)\s+(.+)$", cleaned)
    if prefix_match is not None:
        return prefix_match.group(2).strip(), int(prefix_match.group(1))
    suffix_match = re.match(r"^(.+?),\s*\+(\d+)$", cleaned)
    if suffix_match is not None:
        return suffix_match.group(1).strip(), int(suffix_match.group(2))
    return cleaned, 0


def _load_phb_armor_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_armor_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {
        normalize_lookup(str(title)): {"title": str(title).strip(), **dict(profile or {})}
        for title, profile in payload.items()
        if isinstance(profile, dict)
    }
