from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path
import re
from typing import Any

from .repository import slugify

XIANXIA_HOMEBREW_SOURCE_ID = "XIANXIA-HOMEBREW"
XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY = "curated_seed_data"
XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH = "player_wiki/data/xianxia_systems_seed.json"
_XIANXIA_SYSTEMS_SEED_DATA_PATH = Path(__file__).resolve().parent / "data" / "xianxia_systems_seed.json"
XIANXIA_ENTRY_FACET_KEYS = (
    "rule",
    "attribute",
    "effort",
    "energy",
    "yin_yang",
    "dao",
    "realm",
    "honor_rank",
    "skill_rule",
    "equipment",
    "armor",
    "martial_art",
    "martial_art_rank",
    "technique",
    "maneuver",
    "stance",
    "aura",
    "generic_technique",
    "condition",
    "status",
    "range_rule",
    "timing_rule",
    "critical_hit_rule",
    "sneak_attack_rule",
    "dying_rule",
    "minion_tag",
    "companion_rule",
    "gm_approval_rule",
)
XIANXIA_REFERENCE_ONLY_ENTRY_FACET_KEYS = frozenset({"condition", "status"})
XIANXIA_FACET_SUPPORT_STATES = frozenset({"reference_only", "modeled"})
XIANXIA_EFFORT_KEYS = (
    "basic",
    "weapon",
    "guns_explosive",
    "magic",
    "ultimate",
)
XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL = "Magic Effort"
XIANXIA_MARTIAL_ART_RANK_KEYS = (
    "initiate",
    "novice",
    "apprentice",
    "master",
    "legendary",
)


@lru_cache(maxsize=1)
def _load_xianxia_systems_seed_payload() -> dict[str, Any]:
    payload = json.loads(_XIANXIA_SYSTEMS_SEED_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Xianxia Systems seed payload must be a JSON object.")

    source_id = str(payload.get("source_id") or "").strip()
    source_title = str(payload.get("source_title") or "").strip()
    version = str(payload.get("version") or "").strip()
    storage_strategy = str(payload.get("storage_strategy") or "").strip()
    raw_entry_facets = payload.get("entry_facets")
    raw_efforts = payload.get("efforts")
    raw_martial_art_ranks = payload.get("martial_art_ranks")
    raw_martial_art_rank_sets = payload.get("martial_art_rank_sets")
    raw_entries = payload.get("entries")

    if source_id != XIANXIA_HOMEBREW_SOURCE_ID:
        raise ValueError(
            f"Expected Xianxia Systems seed source_id {XIANXIA_HOMEBREW_SOURCE_ID!r}, got {source_id!r}."
        )
    if not source_title:
        raise ValueError("Xianxia Systems seed payload is missing source_title.")
    if not version:
        raise ValueError("Xianxia Systems seed payload is missing version.")
    if storage_strategy != XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY:
        raise ValueError(
            "Xianxia Systems seed payload must use the curated_seed_data storage strategy."
        )
    payload["entry_facets"] = _normalize_facet_definitions(raw_entry_facets)
    payload["efforts"] = _normalize_effort_definitions(raw_efforts)
    payload["martial_art_ranks"] = _normalize_martial_art_rank_definitions(raw_martial_art_ranks)
    payload["martial_art_rank_sets"] = _normalize_martial_art_rank_sets(raw_martial_art_rank_sets)
    if not isinstance(raw_entries, list):
        raise ValueError("Xianxia Systems seed payload must include an entries list.")

    return payload


def build_xianxia_entry_facet_definitions() -> list[dict[str, Any]]:
    return [dict(facet) for facet in _XIANXIA_ENTRY_FACET_DEFINITIONS]


def get_xianxia_entry_facet_definition(facet_key: str) -> dict[str, Any] | None:
    normalized_key = _normalize_identifier(facet_key)
    definition = _XIANXIA_ENTRY_FACET_LOOKUP.get(normalized_key)
    return dict(definition) if definition is not None else None


def build_xianxia_effort_definitions() -> list[dict[str, Any]]:
    return [dict(effort) for effort in _XIANXIA_EFFORT_DEFINITIONS]


def get_xianxia_effort_definition(effort_key: str) -> dict[str, Any] | None:
    normalized_key = _normalize_identifier(effort_key)
    definition = _XIANXIA_EFFORT_LOOKUP.get(normalized_key)
    return dict(definition) if definition is not None else None


def build_xianxia_martial_art_rank_definitions() -> list[dict[str, Any]]:
    return [dict(rank) for rank in _XIANXIA_MARTIAL_ART_RANK_DEFINITIONS]


def get_xianxia_martial_art_rank_definition(rank_key: str) -> dict[str, Any] | None:
    normalized_key = _normalize_identifier(rank_key)
    definition = _XIANXIA_MARTIAL_ART_RANK_LOOKUP.get(normalized_key)
    return dict(definition) if definition is not None else None


def build_xianxia_systems_seed_entries() -> list[dict[str, Any]]:
    payload = _load_xianxia_systems_seed_payload()
    entries: list[dict[str, Any]] = []
    source_path = f"managed:{XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH}#{XIANXIA_SYSTEMS_SEED_VERSION}"
    for index, raw_spec in enumerate(payload["entries"], start=1):
        if not isinstance(raw_spec, dict):
            raise ValueError(f"Xianxia Systems seed entry {index} must be an object.")
        entries.append(_build_seed_entry(raw_spec, index=index, source_path=source_path))
    return entries


def _build_seed_entry(raw_spec: dict[str, Any], *, index: int, source_path: str) -> dict[str, Any]:
    title = str(raw_spec.get("title") or "").strip()
    if not title:
        raise ValueError(f"Xianxia Systems seed entry {index} is missing title.")

    entry_type = str(raw_spec.get("entry_type") or "").strip().lower()
    if not entry_type:
        raise ValueError(f"Xianxia Systems seed entry {index} is missing entry_type.")

    slug = str(raw_spec.get("slug") or "").strip() or slugify(title)
    entry_key = (
        str(raw_spec.get("entry_key") or "").strip()
        or f"xianxia|{entry_type}|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|{slug}"
    )
    aliases = _normalize_string_list(raw_spec.get("aliases"))
    facets = _normalize_entry_facets(raw_spec.get("facets"), entry_type=entry_type)
    reference_only_facets = [
        facet for facet in facets if facet in XIANXIA_REFERENCE_ONLY_ENTRY_FACET_KEYS
    ]
    summary = str(raw_spec.get("summary") or "").strip()
    sections = _normalize_sections(raw_spec.get("sections"))
    raw_metadata = raw_spec.get("metadata")
    raw_body = raw_spec.get("body")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    body = dict(raw_body) if isinstance(raw_body, dict) else {}
    if reference_only_facets:
        _reject_modeled_support_state(
            metadata.get("support_state"),
            facets=reference_only_facets,
        )
        _reject_modeled_support_state(
            metadata.get("xianxia_support_state"),
            facets=reference_only_facets,
        )
        _reject_modeled_support_state(body.get("support_state"), facets=reference_only_facets)
        _reject_modeled_support_state(
            body.get("xianxia_support_state"),
            facets=reference_only_facets,
        )
        metadata["support_state"] = "reference_only"
        metadata["xianxia_support_state"] = "reference_only"
        body["support_state"] = "reference_only"
        body["xianxia_support_state"] = "reference_only"
    if "effort" in facets:
        effort_definitions = build_xianxia_effort_definitions()
        effort_labels = _build_effort_label_map(effort_definitions)
        metadata.setdefault("effort_labels", effort_labels)
        metadata.setdefault("xianxia_efforts", effort_definitions)
        body.setdefault("effort_labels", effort_labels)
        body.setdefault("xianxia_efforts", effort_definitions)
    metadata.update(
        {
            "aliases": aliases,
            "facets": facets,
            "xianxia_entry_facets": facets,
            "seed_version": XIANXIA_SYSTEMS_SEED_VERSION,
            "seed_storage_strategy": XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY,
            "source_kind": "app_reference",
            "source_provenance": {
                "kind": "gm_reviewed_requirements",
                "requirements_report": ".local/xianxia-requirements-report.md",
            },
            "content_origin": "managed_seed_file",
            "content_source_path": XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH,
            "content_migration_stage": "curated_seed_data_to_sqlite",
        }
    )
    body.setdefault("summary", summary)
    body.setdefault("aliases", aliases)
    body.setdefault("facets", facets)
    body.setdefault("xianxia_entry_facets", facets)
    body.setdefault("sections", sections)
    if entry_type == "martial_art":
        _stamp_martial_art_rank_records(metadata, body, slug=slug)
    search_parts = [
        title,
        entry_type,
        XIANXIA_HOMEBREW_SOURCE_ID,
        summary,
        *aliases,
        *facets,
        str(raw_spec.get("search_text") or "").strip(),
    ]
    rendered_html = str(raw_spec.get("rendered_html") or "").strip() or _render_seed_entry_html(
        summary=summary,
        aliases=aliases,
        sections=sections,
    )
    return {
        "entry_key": entry_key,
        "entry_type": entry_type,
        "slug": slug,
        "title": title,
        "source_page": str(raw_spec.get("source_page") or "Xianxia curated seed").strip(),
        "source_path": source_path,
        "search_text": " ".join(part for part in search_parts if part).lower(),
        "player_safe_default": bool(raw_spec.get("player_safe_default", True)),
        "dm_heavy": bool(raw_spec.get("dm_heavy", False)),
        "metadata": metadata,
        "body": body,
        "rendered_html": rendered_html,
    }


def _normalize_string_list(raw_values: object) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def _normalize_identifier(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def _normalize_facet_definitions(raw_facets: object) -> list[dict[str, Any]]:
    if not isinstance(raw_facets, list):
        raise ValueError("Xianxia Systems seed payload must include an entry_facets list.")

    definitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_facet in enumerate(raw_facets, start=1):
        if not isinstance(raw_facet, dict):
            raise ValueError(f"Xianxia entry facet {index} must be an object.")
        key = _normalize_identifier(raw_facet.get("key"))
        if not key:
            raise ValueError(f"Xianxia entry facet {index} is missing key.")
        if key in seen:
            raise ValueError(f"Xianxia entry facet {key!r} is duplicated.")
        seen.add(key)
        label = str(raw_facet.get("label") or "").strip()
        group = _normalize_identifier(raw_facet.get("group"))
        default_entry_type = _normalize_identifier(raw_facet.get("default_entry_type"))
        summary = str(raw_facet.get("summary") or "").strip()
        support_state = _normalize_identifier(raw_facet.get("support_state"))
        if not label:
            raise ValueError(f"Xianxia entry facet {key!r} is missing label.")
        if not group:
            raise ValueError(f"Xianxia entry facet {key!r} is missing group.")
        if not default_entry_type:
            raise ValueError(f"Xianxia entry facet {key!r} is missing default_entry_type.")
        if not summary:
            raise ValueError(f"Xianxia entry facet {key!r} is missing summary.")
        if support_state and support_state not in XIANXIA_FACET_SUPPORT_STATES:
            raise ValueError(
                f"Xianxia entry facet {key!r} uses unsupported support_state "
                f"{support_state!r}."
            )
        if key in XIANXIA_REFERENCE_ONLY_ENTRY_FACET_KEYS and support_state != "reference_only":
            raise ValueError(
                f"Xianxia entry facet {key!r} must remain reference_only in Milestone 1."
            )
        definition = {
            "key": key,
            "label": label,
            "group": group,
            "default_entry_type": default_entry_type,
            "summary": summary,
        }
        if support_state:
            definition["support_state"] = support_state
        definitions.append(definition)

    expected = set(XIANXIA_ENTRY_FACET_KEYS)
    actual = {definition["key"] for definition in definitions}
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError("Xianxia entry facets do not match the Milestone 1 facet set: " + "; ".join(details) + ".")
    return definitions


def _normalize_effort_definitions(raw_efforts: object) -> list[dict[str, Any]]:
    if not isinstance(raw_efforts, list):
        raise ValueError("Xianxia Systems seed payload must include an efforts list.")

    definitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_effort in enumerate(raw_efforts, start=1):
        if not isinstance(raw_effort, dict):
            raise ValueError(f"Xianxia effort definition {index} must be an object.")
        key = _normalize_identifier(raw_effort.get("key"))
        if not key:
            raise ValueError(f"Xianxia effort definition {index} is missing key.")
        if key in seen:
            raise ValueError(f"Xianxia effort definition {key!r} is duplicated.")
        seen.add(key)

        label = str(raw_effort.get("label") or "").strip()
        canonical_label = str(raw_effort.get("canonical_label") or "").strip()
        die = str(raw_effort.get("die") or "").strip()
        damage_bonus_key = _normalize_identifier(raw_effort.get("damage_bonus_key") or key)
        damage_expression = str(raw_effort.get("damage_expression") or "").strip()
        if not label:
            raise ValueError(f"Xianxia effort definition {key!r} is missing label.")
        if not canonical_label:
            raise ValueError(f"Xianxia effort definition {key!r} is missing canonical_label.")
        if not die:
            raise ValueError(f"Xianxia effort definition {key!r} is missing die.")
        if not damage_bonus_key:
            raise ValueError(f"Xianxia effort definition {key!r} is missing damage_bonus_key.")
        if not damage_expression:
            raise ValueError(f"Xianxia effort definition {key!r} is missing damage_expression.")
        if not canonical_label.endswith(" Effort"):
            raise ValueError(
                f"Xianxia effort definition {key!r} canonical_label must end with ' Effort'."
            )
        if key == "magic" and canonical_label != XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL:
            raise ValueError(
                f"Xianxia magic effort canonical_label must be "
                f"{XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL!r}."
            )

        definitions.append(
            {
                "key": key,
                "label": label,
                "canonical_label": canonical_label,
                "die": die,
                "damage_bonus_key": damage_bonus_key,
                "damage_expression": damage_expression,
            }
        )

    actual_keys = tuple(definition["key"] for definition in definitions)
    if actual_keys != XIANXIA_EFFORT_KEYS:
        raise ValueError(
            "Xianxia effort definitions do not match the Milestone 1 effort set: "
            + ", ".join(actual_keys)
            + "."
        )
    return definitions


def _normalize_martial_art_rank_definitions(raw_ranks: object) -> list[dict[str, Any]]:
    if not isinstance(raw_ranks, list):
        raise ValueError("Xianxia Systems seed payload must include a martial_art_ranks list.")

    definitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_rank in enumerate(raw_ranks, start=1):
        if not isinstance(raw_rank, dict):
            raise ValueError(f"Xianxia Martial Art rank definition {index} must be an object.")
        key = _normalize_identifier(raw_rank.get("key"))
        if not key:
            raise ValueError(f"Xianxia Martial Art rank definition {index} is missing key.")
        if key in seen:
            raise ValueError(f"Xianxia Martial Art rank definition {key!r} is duplicated.")
        seen.add(key)
        rank_name = str(raw_rank.get("rank_name") or raw_rank.get("label") or "").strip()
        if not rank_name:
            raise ValueError(f"Xianxia Martial Art rank definition {key!r} is missing rank_name.")
        definitions.append({"key": key, "rank_name": rank_name})

    actual_keys = tuple(definition["key"] for definition in definitions)
    if actual_keys != XIANXIA_MARTIAL_ART_RANK_KEYS:
        raise ValueError(
            "Xianxia Martial Art rank definitions do not match the Milestone 1 rank set: "
            + ", ".join(actual_keys)
            + "."
        )
    return definitions


def _normalize_martial_art_rank_sets(raw_rank_sets: object) -> dict[str, Any]:
    if not isinstance(raw_rank_sets, dict):
        raise ValueError("Xianxia Systems seed payload must include a martial_art_rank_sets object.")

    default_rank_keys = _normalize_rank_key_sequence(raw_rank_sets.get("default"), context="default")
    if tuple(default_rank_keys) != XIANXIA_MARTIAL_ART_RANK_KEYS:
        raise ValueError("Xianxia Martial Art default rank set must include all Milestone 1 ranks in order.")

    by_martial_art_key: dict[str, list[str]] = {}
    raw_by_key = raw_rank_sets.get("by_martial_art_key")
    if raw_by_key is not None and not isinstance(raw_by_key, dict):
        raise ValueError("Xianxia Martial Art rank-set overrides must be an object.")
    if isinstance(raw_by_key, dict):
        for raw_key, raw_rank_keys in raw_by_key.items():
            martial_art_key = _normalize_identifier(raw_key)
            if not martial_art_key:
                raise ValueError("Xianxia Martial Art rank-set override is missing a Martial Art key.")
            if martial_art_key in by_martial_art_key:
                raise ValueError(f"Xianxia Martial Art rank-set override {martial_art_key!r} is duplicated.")
            rank_keys = _normalize_rank_key_sequence(raw_rank_keys, context=martial_art_key)
            if tuple(rank_keys) != XIANXIA_MARTIAL_ART_RANK_KEYS[: len(rank_keys)]:
                raise ValueError(
                    f"Xianxia Martial Art rank-set override {martial_art_key!r} must be a prefix of the "
                    "Milestone 1 rank set."
                )
            by_martial_art_key[martial_art_key] = rank_keys

    return {
        "default": default_rank_keys,
        "by_martial_art_key": by_martial_art_key,
    }


def _normalize_rank_key_sequence(raw_rank_keys: object, *, context: str) -> list[str]:
    rank_keys = [_normalize_identifier(value) for value in _normalize_string_list(raw_rank_keys)]
    rank_keys = [rank_key for rank_key in rank_keys if rank_key]
    if not rank_keys:
        raise ValueError(f"Xianxia Martial Art rank set {context!r} must include at least one rank.")
    unknown = sorted({rank_key for rank_key in rank_keys if rank_key not in XIANXIA_MARTIAL_ART_RANK_KEYS})
    if unknown:
        raise ValueError(
            f"Xianxia Martial Art rank set {context!r} uses unknown ranks: "
            + ", ".join(unknown)
            + "."
        )
    deduped: list[str] = []
    for rank_key in rank_keys:
        if rank_key not in deduped:
            deduped.append(rank_key)
    return deduped


def _normalize_entry_facets(raw_facets: object, *, entry_type: str) -> list[str]:
    facets = [_normalize_identifier(value) for value in _normalize_string_list(raw_facets)]
    facets = [facet for facet in facets if facet]
    if not facets and entry_type in _XIANXIA_ENTRY_FACET_LOOKUP:
        facets = [entry_type]
    if not facets:
        raise ValueError("Xianxia Systems seed entries must include at least one defined facet.")

    unknown = sorted({facet for facet in facets if facet not in _XIANXIA_ENTRY_FACET_LOOKUP})
    if unknown:
        raise ValueError("Xianxia Systems seed entry uses unknown facets: " + ", ".join(unknown) + ".")

    normalized: list[str] = []
    for facet in facets:
        if facet not in normalized:
            normalized.append(facet)
    return normalized


def _reject_modeled_support_state(value: object, *, facets: list[str]) -> None:
    normalized = _normalize_identifier(value)
    if not normalized or normalized == "reference_only":
        return
    raise ValueError(
        "Xianxia Systems seed entries using reference-only facets "
        + ", ".join(facets)
        + " cannot declare modeled support in Milestone 1."
    )


def _build_effort_label_map(effort_definitions: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(effort["key"]): str(effort["canonical_label"])
        for effort in effort_definitions
    }


def _stamp_martial_art_rank_records(metadata: dict[str, Any], body: dict[str, Any], *, slug: str) -> None:
    martial_art_key = _normalize_identifier(
        metadata.get("martial_art_key") or metadata.get("xianxia_martial_art_key") or slug
    )
    rank_records = _build_martial_art_rank_records(
        martial_art_key=martial_art_key,
        martial_art_slug=slug,
        rank_keys=_martial_art_rank_keys_for(martial_art_key),
    )
    metadata_rank_records = [dict(record) for record in rank_records]
    body_rank_records = [dict(record) for record in rank_records]
    metadata["rank_records_seeded"] = True
    metadata["rank_records_status"] = "present_rank_names_seeded"
    metadata["martial_art_rank_records"] = metadata_rank_records
    metadata["xianxia_martial_art_rank_records"] = [dict(record) for record in rank_records]

    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        martial_art_body = {}
        body["xianxia_martial_art"] = martial_art_body
    martial_art_body["rank_records_seeded"] = True
    martial_art_body["rank_records_status"] = "present_rank_names_seeded"
    martial_art_body["rank_records"] = body_rank_records
    martial_art_body["xianxia_martial_art_rank_records"] = [dict(record) for record in rank_records]


def _build_martial_art_rank_records(
    *,
    martial_art_key: str,
    martial_art_slug: str,
    rank_keys: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rank_key in rank_keys:
        rank_definition = _XIANXIA_MARTIAL_ART_RANK_LOOKUP[rank_key]
        records.append(
            {
                "martial_art_key": martial_art_key,
                "martial_art_slug": martial_art_slug,
                "rank_key": rank_key,
                "rank_name": str(rank_definition["rank_name"]),
                "rank_ref": f"xianxia:{martial_art_slug}:{rank_key}",
            }
        )
    return records


def _martial_art_rank_keys_for(martial_art_key: str) -> list[str]:
    override = _XIANXIA_MARTIAL_ART_RANK_SETS["by_martial_art_key"].get(martial_art_key)
    return list(override or _XIANXIA_MARTIAL_ART_RANK_SETS["default"])


_XIANXIA_SYSTEMS_SEED_PAYLOAD = _load_xianxia_systems_seed_payload()
XIANXIA_SYSTEMS_SEED_SOURCE_TITLE = str(_XIANXIA_SYSTEMS_SEED_PAYLOAD["source_title"])
XIANXIA_SYSTEMS_SEED_VERSION = str(_XIANXIA_SYSTEMS_SEED_PAYLOAD["version"])
_XIANXIA_EFFORT_DEFINITIONS = tuple(
    dict(effort) for effort in _XIANXIA_SYSTEMS_SEED_PAYLOAD["efforts"]
)
_XIANXIA_EFFORT_LOOKUP = {
    str(effort["key"]): dict(effort) for effort in _XIANXIA_EFFORT_DEFINITIONS
}
_XIANXIA_MARTIAL_ART_RANK_DEFINITIONS = tuple(
    dict(rank) for rank in _XIANXIA_SYSTEMS_SEED_PAYLOAD["martial_art_ranks"]
)
_XIANXIA_MARTIAL_ART_RANK_LOOKUP = {
    str(rank["key"]): dict(rank) for rank in _XIANXIA_MARTIAL_ART_RANK_DEFINITIONS
}
_XIANXIA_MARTIAL_ART_RANK_SETS = {
    "default": list(_XIANXIA_SYSTEMS_SEED_PAYLOAD["martial_art_rank_sets"]["default"]),
    "by_martial_art_key": dict(
        _XIANXIA_SYSTEMS_SEED_PAYLOAD["martial_art_rank_sets"]["by_martial_art_key"]
    ),
}
_XIANXIA_ENTRY_FACET_DEFINITIONS = tuple(
    dict(facet) for facet in _XIANXIA_SYSTEMS_SEED_PAYLOAD["entry_facets"]
)
_XIANXIA_ENTRY_FACET_LOOKUP = {
    str(facet["key"]): dict(facet) for facet in _XIANXIA_ENTRY_FACET_DEFINITIONS
}


def _normalize_sections(raw_sections: object) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return []

    sections: list[dict[str, Any]] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            continue
        title = str(raw_section.get("title") or "").strip()
        paragraphs = _normalize_string_list(raw_section.get("paragraphs"))
        bullets = _normalize_string_list(raw_section.get("bullets"))
        if not title and not paragraphs and not bullets:
            continue
        sections.append(
            {
                "title": title,
                "paragraphs": paragraphs,
                "bullets": bullets,
            }
        )
    return sections


def _render_seed_entry_html(
    *,
    summary: str,
    aliases: list[str],
    sections: list[dict[str, Any]],
) -> str:
    parts: list[str] = ['<section class="systems-entry-summary">']
    if aliases:
        parts.append(f"<p><strong>Also covers:</strong> {escape(', '.join(aliases))}</p>")
    if summary:
        parts.append(f"<p>{escape(summary)}</p>")
    parts.append("</section>")

    for section in sections:
        title = str(section.get("title") or "").strip()
        paragraphs = [str(value).strip() for value in list(section.get("paragraphs") or []) if str(value).strip()]
        bullets = [str(value).strip() for value in list(section.get("bullets") or []) if str(value).strip()]
        if not title and not paragraphs and not bullets:
            continue
        parts.append("<section>")
        if title:
            parts.append(f"<h2>{escape(title)}</h2>")
        for paragraph in paragraphs:
            parts.append(f"<p>{escape(paragraph)}</p>")
        if bullets:
            parts.append("<ul>")
            parts.extend(f"<li>{escape(item)}</li>" for item in bullets)
            parts.append("</ul>")
        parts.append("</section>")
    return "".join(parts)
