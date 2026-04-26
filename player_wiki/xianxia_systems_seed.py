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
XIANXIA_ENERGY_KEYS = ("jing", "qi", "shen")
XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL = "Magic Effort"
XIANXIA_MARTIAL_ART_RANK_KEYS = (
    "initiate",
    "novice",
    "apprentice",
    "master",
    "legendary",
)
XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED = (
    "rank_advancement_metadata_seeded"
)
XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED = (
    "energy_maximum_increases_seeded"
)
XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED = (
    "ability_kind_tags_seeded"
)
XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED = (
    "cost_range_damage_duration_support_seeded"
)
XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE = "complete"
XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT = "intentional_incomplete_draft"
XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT = "intentional_draft_content"
XIANXIA_MARTIAL_ART_RANK_STATUS_PRESENT = "present"
XIANXIA_MARTIAL_ART_RANK_STATUS_MISSING_INTENTIONAL_DRAFT = "missing_intentional_draft"
XIANXIA_MARTIAL_ART_ABILITY_KIND_KEYS = ("technique", "maneuver", "stance", "aura", "other")
XIANXIA_MARTIAL_ART_ABILITY_KIND_LABELS = {
    "technique": "Technique",
    "maneuver": "Maneuver",
    "stance": "Stance",
    "aura": "Aura",
    "other": "Other",
}
XIANXIA_MARTIAL_ART_ABILITY_SUPPORT_STATES = frozenset({"reference_only", "modeled"})
XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE = "reference_only"
XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED = (
    "cost_prerequisite_resource_range_effort_reset_support_seeded"
)
XIANXIA_GENERIC_TECHNIQUE_SUPPORT_STATES = frozenset({"reference_only", "modeled"})
XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE = "reference_only"
XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT = (
    "unavailable_by_default"
)
XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_REASON_INSIGHT_STARTS_AT_0 = (
    "insight_starts_at_0"
)
XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_NOTE_INSIGHT_STARTS_AT_0 = (
    "Generic Techniques require spending Insight, and Insight starts at 0."
)
XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_STATUS_SEEDED = (
    "unavailable_by_default_insight_starts_at_0"
)
XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE = "none"
XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_REASON_NO_MASTER_REQUIRED = (
    "generic_techniques_do_not_require_master"
)
XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NOTE_NO_MASTER_REQUIRED = (
    "Generic Techniques do not require a Master."
)
XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_STATUS_LEARNABLE_WITHOUT_MASTER = (
    "learnable_without_master"
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
    raw_martial_art_rank_resource_grants = payload.get("martial_art_rank_resource_grants")
    raw_martial_art_rank_ability_grants = payload.get("martial_art_rank_ability_grants")
    raw_martial_art_rank_ability_effects = payload.get("martial_art_rank_ability_effects")
    raw_generic_technique_details = payload.get("generic_technique_details")
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
    payload["martial_art_rank_resource_grants"] = _normalize_martial_art_rank_resource_grants(
        raw_martial_art_rank_resource_grants
    )
    payload["martial_art_rank_ability_grants"] = _normalize_martial_art_rank_ability_grants(
        raw_martial_art_rank_ability_grants
    )
    payload["martial_art_rank_ability_effects"] = _normalize_martial_art_rank_ability_effects(
        raw_martial_art_rank_ability_effects,
        payload["martial_art_rank_ability_grants"],
    )
    if not isinstance(raw_entries, list):
        raise ValueError("Xianxia Systems seed payload must include an entries list.")
    payload["generic_technique_details"] = _normalize_generic_technique_details(
        raw_generic_technique_details
    )
    _validate_martial_art_rank_resource_grants_cover_entries(
        payload["martial_art_rank_resource_grants"],
        raw_entries,
        payload["martial_art_rank_sets"],
    )
    _validate_martial_art_rank_ability_grants_cover_entries(
        payload["martial_art_rank_ability_grants"],
        raw_entries,
        payload["martial_art_rank_sets"],
    )
    _validate_generic_technique_details_cover_entries(
        payload["generic_technique_details"],
        raw_entries,
    )

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


def build_xianxia_martial_art_rank_resource_grants() -> dict[str, dict[str, dict[str, int]]]:
    return {
        martial_art_key: {
            rank_key: dict(grants)
            for rank_key, grants in rank_grants.items()
        }
        for martial_art_key, rank_grants in _XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS.items()
    }


def build_xianxia_martial_art_rank_ability_grants() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        martial_art_key: {
            rank_key: [dict(grant) for grant in grants]
            for rank_key, grants in rank_grants.items()
        }
        for martial_art_key, rank_grants in _XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS.items()
    }


def build_xianxia_martial_art_rank_ability_effects() -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    return {
        martial_art_key: {
            rank_key: {
                ability_key: {
                    key: (
                        [dict(item) for item in value]
                        if key == "resource_costs"
                        else list(value)
                        if key in {"range_tags", "damage_effort_tags", "duration_tags"}
                        else value
                    )
                    for key, value in effect.items()
                }
                for ability_key, effect in rank_effects.items()
            }
            for rank_key, rank_effects in rank_effects_by_art.items()
        }
        for martial_art_key, rank_effects_by_art in _XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS.items()
    }


def build_xianxia_generic_technique_details() -> dict[str, dict[str, Any]]:
    return {
        generic_technique_key: _copy_generic_technique_detail(detail)
        for generic_technique_key, detail in _XIANXIA_GENERIC_TECHNIQUE_DETAILS.items()
    }


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
    if entry_type == "generic_technique":
        _stamp_generic_technique_details(metadata, body, slug=slug)
    search_parts = [
        title,
        entry_type,
        XIANXIA_HOMEBREW_SOURCE_ID,
        summary,
        *aliases,
        *facets,
        str(raw_spec.get("search_text") or "").strip(),
    ]
    if entry_type == "martial_art":
        search_parts.extend(_martial_art_draft_search_parts(body))
        search_parts.extend(_martial_art_ability_search_parts(body))
    if entry_type == "generic_technique":
        search_parts.extend(_generic_technique_details_search_parts(body))
    rendered_html = str(raw_spec.get("rendered_html") or "").strip() or _render_seed_entry_html(
        summary=summary,
        aliases=aliases,
        sections=sections,
    )
    if entry_type == "martial_art":
        rendered_html += _render_martial_art_rank_records_html(body)
        rendered_html += _render_martial_art_draft_marker_html(body)
    if entry_type == "generic_technique":
        rendered_html += _render_generic_technique_details_html(body)
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


def _normalize_non_negative_int(value: object, *, context: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a non-negative integer.")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a non-negative integer.") from exc
    if normalized < 0:
        raise ValueError(f"{context} must be a non-negative integer.")
    return normalized


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
        rank_order = _normalize_non_negative_int(
            raw_rank.get("rank_order"),
            context=f"Xianxia Martial Art rank definition {key!r} rank_order",
        )
        if rank_order != index:
            raise ValueError(
                f"Xianxia Martial Art rank definition {key!r} must use rank_order {index}."
            )
        prerequisite_rank_key = _normalize_identifier(raw_rank.get("prerequisite_rank_key"))
        expected_prerequisite_key = definitions[-1]["key"] if definitions else ""
        if prerequisite_rank_key != expected_prerequisite_key:
            expected_label = expected_prerequisite_key or "no prerequisite"
            raise ValueError(
                f"Xianxia Martial Art rank definition {key!r} must use prerequisite "
                f"{expected_label!r}."
            )
        insight_cost = _normalize_non_negative_int(
            raw_rank.get("insight_cost"),
            context=f"Xianxia Martial Art rank definition {key!r} insight_cost",
        )
        teacher_breakthrough_requirement = (
            _normalize_identifier(raw_rank.get("teacher_breakthrough_requirement")) or "none"
        )
        teacher_breakthrough_note = str(raw_rank.get("teacher_breakthrough_note") or "").strip()
        advancement_note = str(raw_rank.get("advancement_note") or "").strip()
        legendary_prerequisite_note = str(raw_rank.get("legendary_prerequisite_note") or "").strip()
        definitions.append(
            {
                "key": key,
                "rank_name": rank_name,
                "rank_order": rank_order,
                "prerequisite_rank_key": prerequisite_rank_key or None,
                "insight_cost": insight_cost,
                "teacher_breakthrough_requirement": teacher_breakthrough_requirement,
                "teacher_breakthrough_note": teacher_breakthrough_note,
                "advancement_note": advancement_note,
                "legendary_prerequisite_note": legendary_prerequisite_note,
            }
        )

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


def _normalize_martial_art_rank_resource_grants(
    raw_resource_grants: object,
) -> dict[str, dict[str, dict[str, int]]]:
    if not isinstance(raw_resource_grants, dict):
        raise ValueError(
            "Xianxia Systems seed payload must include a martial_art_rank_resource_grants object."
        )

    normalized: dict[str, dict[str, dict[str, int]]] = {}
    for raw_martial_art_key, raw_rank_grants in raw_resource_grants.items():
        martial_art_key = _normalize_identifier(raw_martial_art_key)
        if not martial_art_key:
            raise ValueError(
                "Xianxia Martial Art rank resource grants are missing a Martial Art key."
            )
        if martial_art_key in normalized:
            raise ValueError(
                f"Xianxia Martial Art rank resource grants for {martial_art_key!r} are duplicated."
            )
        if not isinstance(raw_rank_grants, dict):
            raise ValueError(
                f"Xianxia Martial Art rank resource grants for {martial_art_key!r} must be an object."
            )

        normalized_rank_grants: dict[str, dict[str, int]] = {}
        for raw_rank_key, raw_grants in raw_rank_grants.items():
            rank_key = _normalize_identifier(raw_rank_key)
            if rank_key not in XIANXIA_MARTIAL_ART_RANK_KEYS:
                raise ValueError(
                    f"Xianxia Martial Art rank resource grants for {martial_art_key!r} "
                    f"use unknown rank {rank_key!r}."
                )
            if rank_key in normalized_rank_grants:
                raise ValueError(
                    f"Xianxia Martial Art rank resource grants for {martial_art_key!r} "
                    f"duplicate rank {rank_key!r}."
                )
            normalized_rank_grants[rank_key] = _normalize_energy_maximum_increases(
                raw_grants,
                context=(
                    f"Xianxia Martial Art rank resource grants for {martial_art_key!r} "
                    f"rank {rank_key!r}"
                ),
            )

        normalized[martial_art_key] = normalized_rank_grants

    return normalized


def _normalize_martial_art_rank_ability_grants(
    raw_ability_grants: object,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not isinstance(raw_ability_grants, dict):
        raise ValueError(
            "Xianxia Systems seed payload must include a martial_art_rank_ability_grants object."
        )

    normalized: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for raw_martial_art_key, raw_rank_grants in raw_ability_grants.items():
        martial_art_key = _normalize_identifier(raw_martial_art_key)
        if not martial_art_key:
            raise ValueError(
                "Xianxia Martial Art rank ability grants are missing a Martial Art key."
            )
        if martial_art_key in normalized:
            raise ValueError(
                f"Xianxia Martial Art rank ability grants for {martial_art_key!r} are duplicated."
            )
        if not isinstance(raw_rank_grants, dict):
            raise ValueError(
                f"Xianxia Martial Art rank ability grants for {martial_art_key!r} must be an object."
            )

        normalized_rank_grants: dict[str, list[dict[str, Any]]] = {}
        for raw_rank_key, raw_grants in raw_rank_grants.items():
            rank_key = _normalize_identifier(raw_rank_key)
            if rank_key not in XIANXIA_MARTIAL_ART_RANK_KEYS:
                raise ValueError(
                    f"Xianxia Martial Art rank ability grants for {martial_art_key!r} "
                    f"use unknown rank {rank_key!r}."
                )
            if rank_key in normalized_rank_grants:
                raise ValueError(
                    f"Xianxia Martial Art rank ability grants for {martial_art_key!r} "
                    f"duplicate rank {rank_key!r}."
                )
            if not isinstance(raw_grants, list) or not raw_grants:
                raise ValueError(
                    f"Xianxia Martial Art rank ability grants for {martial_art_key!r} "
                    f"rank {rank_key!r} must be a non-empty list."
                )

            normalized_rank_grants[rank_key] = _normalize_rank_ability_grants(
                raw_grants,
                context=(
                    f"Xianxia Martial Art rank ability grants for {martial_art_key!r} "
                    f"rank {rank_key!r}"
                ),
            )

        normalized[martial_art_key] = normalized_rank_grants

    return normalized


def _normalize_martial_art_rank_ability_effects(
    raw_ability_effects: object,
    ability_grants: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    if not isinstance(raw_ability_effects, dict):
        raise ValueError(
            "Xianxia Systems seed payload must include a martial_art_rank_ability_effects object."
        )

    normalized: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for raw_martial_art_key, raw_rank_effects in raw_ability_effects.items():
        martial_art_key = _normalize_identifier(raw_martial_art_key)
        if martial_art_key not in ability_grants:
            raise ValueError(
                f"Xianxia Martial Art ability effects include unknown Martial Art {martial_art_key!r}."
            )
        if martial_art_key in normalized:
            raise ValueError(
                f"Xianxia Martial Art ability effects for {martial_art_key!r} are duplicated."
            )
        if not isinstance(raw_rank_effects, dict):
            raise ValueError(
                f"Xianxia Martial Art ability effects for {martial_art_key!r} must be an object."
            )

        normalized_rank_effects: dict[str, dict[str, dict[str, Any]]] = {}
        for raw_rank_key, raw_effects_by_ability in raw_rank_effects.items():
            rank_key = _normalize_identifier(raw_rank_key)
            if rank_key not in ability_grants[martial_art_key]:
                raise ValueError(
                    f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                    f"use unknown rank {rank_key!r}."
                )
            if rank_key in normalized_rank_effects:
                raise ValueError(
                    f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                    f"duplicate rank {rank_key!r}."
                )
            if not isinstance(raw_effects_by_ability, dict):
                raise ValueError(
                    f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                    f"rank {rank_key!r} must be an object."
                )

            known_ability_keys = {
                str(grant["ability_key"])
                for grant in ability_grants[martial_art_key][rank_key]
            }
            normalized_ability_effects: dict[str, dict[str, Any]] = {}
            for raw_ability_key, raw_effect in raw_effects_by_ability.items():
                ability_key = _normalize_identifier(raw_ability_key)
                if ability_key not in known_ability_keys:
                    raise ValueError(
                        f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                        f"rank {rank_key!r} include unknown ability {ability_key!r}."
                    )
                if ability_key in normalized_ability_effects:
                    raise ValueError(
                        f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                        f"rank {rank_key!r} duplicate ability {ability_key!r}."
                    )
                normalized_ability_effects[ability_key] = _normalize_rank_ability_effect(
                    raw_effect,
                    context=(
                        f"Xianxia Martial Art ability effects for {martial_art_key!r} "
                        f"rank {rank_key!r} ability {ability_key!r}"
                    ),
                )
            normalized_rank_effects[rank_key] = normalized_ability_effects

        normalized[martial_art_key] = normalized_rank_effects

    return normalized


def _normalize_rank_ability_effect(
    raw_effect: object,
    *,
    context: str,
) -> dict[str, Any]:
    if raw_effect is None:
        raw_effect = {}
    if not isinstance(raw_effect, dict):
        raise ValueError(f"{context} must be an object.")

    support_state = _normalize_identifier(
        raw_effect.get("support_state")
        or raw_effect.get("support")
        or XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
    )
    if support_state not in XIANXIA_MARTIAL_ART_ABILITY_SUPPORT_STATES:
        raise ValueError(f"{context} uses unsupported support_state {support_state!r}.")

    return {
        "resource_costs": _normalize_ability_resource_costs(
            raw_effect.get("resource_costs", raw_effect.get("costs")),
            context=f"{context} resource_costs",
        ),
        "range_tags": _normalize_ability_tag_list(
            raw_effect.get("range_tags", raw_effect.get("ranges")),
            context=f"{context} range_tags",
        ),
        "damage_effort_tags": _normalize_ability_tag_list(
            raw_effect.get("damage_effort_tags", raw_effect.get("damage")),
            context=f"{context} damage_effort_tags",
        ),
        "duration_tags": _normalize_ability_tag_list(
            raw_effect.get("duration_tags", raw_effect.get("durations")),
            context=f"{context} duration_tags",
        ),
        "support_state": support_state,
        "xianxia_support_state": support_state,
    }


def _normalize_ability_resource_costs(raw_costs: object, *, context: str) -> list[dict[str, Any]]:
    if raw_costs is None:
        return []
    if not isinstance(raw_costs, list):
        raise ValueError(f"{context} must be a list.")

    normalized: list[dict[str, Any]] = []
    for index, raw_cost in enumerate(raw_costs, start=1):
        if isinstance(raw_cost, str):
            raw_cost_text = raw_cost.strip()
            raw_resource, _, raw_amount = raw_cost_text.partition(":")
            resource_key = _normalize_identifier(raw_resource)
            amount = _normalize_resource_cost_amount(raw_amount or 1, context=f"{context} {index}")
            record: dict[str, Any] = {"resource_key": resource_key, "amount": amount}
        elif isinstance(raw_cost, dict):
            resource_key = _normalize_identifier(
                raw_cost.get("resource_key") or raw_cost.get("resource")
            )
            amount = _normalize_resource_cost_amount(
                raw_cost.get("amount", 1),
                context=f"{context} {index}",
            )
            record = {"resource_key": resource_key, "amount": amount}
            timing = _normalize_identifier(raw_cost.get("timing"))
            if timing:
                record["timing"] = timing
            note = str(raw_cost.get("note") or "").strip()
            if note:
                record["note"] = note
        else:
            raise ValueError(f"{context} {index} must be a string or object.")

        if not resource_key:
            raise ValueError(f"{context} {index} is missing a resource key.")
        normalized.append(record)

    return normalized


def _normalize_resource_cost_amount(value: object, *, context: str) -> int | str:
    if isinstance(value, bool):
        raise ValueError(f"{context} amount must be a positive integer or text token.")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{context} amount must be positive.")
        return value
    amount_text = str(value or "").strip()
    if not amount_text:
        return 1
    if amount_text.isdigit():
        amount = int(amount_text)
        if amount <= 0:
            raise ValueError(f"{context} amount must be positive.")
        return amount
    normalized = _normalize_identifier(amount_text)
    if not normalized:
        raise ValueError(f"{context} amount must be a positive integer or text token.")
    return normalized


def _normalize_ability_tag_list(raw_tags: object, *, context: str) -> list[str]:
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, list):
        raise ValueError(f"{context} must be a list.")
    normalized: list[str] = []
    for index, raw_tag in enumerate(raw_tags, start=1):
        tag = _normalize_identifier(raw_tag)
        if not tag:
            raise ValueError(f"{context} {index} is missing a tag.")
        if tag not in normalized:
            normalized.append(tag)
    return normalized


def _normalize_generic_technique_details(raw_details: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_details, dict):
        raise ValueError(
            "Xianxia Systems seed payload must include a generic_technique_details object."
        )

    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_detail in raw_details.items():
        generic_technique_key = _normalize_identifier(raw_key)
        if not generic_technique_key:
            raise ValueError("Xianxia Generic Technique details include a blank key.")
        if generic_technique_key in normalized:
            raise ValueError(
                f"Xianxia Generic Technique details for {generic_technique_key!r} are duplicated."
            )
        if not isinstance(raw_detail, dict):
            raise ValueError(
                f"Xianxia Generic Technique details for {generic_technique_key!r} must be an object."
            )

        insight_cost = _normalize_non_negative_int(
            raw_detail.get("insight_cost"),
            context=f"Xianxia Generic Technique {generic_technique_key!r} insight_cost",
        )
        if insight_cost <= 0:
            raise ValueError(
                f"Xianxia Generic Technique {generic_technique_key!r} insight_cost must be positive."
            )
        support_state = _normalize_identifier(
            raw_detail.get("support_state")
            or raw_detail.get("support")
            or XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE
        )
        if support_state not in XIANXIA_GENERIC_TECHNIQUE_SUPPORT_STATES:
            raise ValueError(
                f"Xianxia Generic Technique {generic_technique_key!r} uses unsupported "
                f"support_state {support_state!r}."
            )

        reset_cadence = _normalize_identifier(
            raw_detail.get("reset_cadence") or raw_detail.get("reset")
        )
        available_at_character_creation = bool(
            raw_detail.get("available_at_character_creation")
            or raw_detail.get("character_creation_available")
        )
        if available_at_character_creation:
            raise ValueError(
                f"Xianxia Generic Technique {generic_technique_key!r} must be unavailable "
                "at character creation because Insight starts at 0."
            )
        requires_master = bool(
            raw_detail.get("requires_master") or raw_detail.get("master_required")
        )
        master_requirement = _normalize_identifier(
            raw_detail.get("master_requirement")
            or raw_detail.get("teacher_requirement")
            or XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE
        )
        if requires_master or master_requirement != XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE:
            raise ValueError(
                f"Xianxia Generic Technique {generic_technique_key!r} must be "
                "learnable without a Master."
            )
        normalized[generic_technique_key] = {
            "insight_cost": insight_cost,
            "prerequisites": _normalize_generic_technique_prerequisites(
                raw_detail.get("prerequisites"),
                context=f"Xianxia Generic Technique {generic_technique_key!r} prerequisites",
            ),
            "resource_costs": _normalize_ability_resource_costs(
                raw_detail.get("resource_costs", raw_detail.get("costs")),
                context=f"Xianxia Generic Technique {generic_technique_key!r} resource_costs",
            ),
            "range_tags": _normalize_ability_tag_list(
                raw_detail.get("range_tags", raw_detail.get("ranges")),
                context=f"Xianxia Generic Technique {generic_technique_key!r} range_tags",
            ),
            "effort_tags": _normalize_ability_tag_list(
                raw_detail.get("effort_tags", raw_detail.get("efforts")),
                context=f"Xianxia Generic Technique {generic_technique_key!r} effort_tags",
            ),
            "reset_cadence": reset_cadence or None,
            "support_state": support_state,
            "xianxia_support_state": support_state,
            "available_at_character_creation": False,
            "character_creation_availability": (
                XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT
            ),
            "character_creation_availability_reason": (
                XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_REASON_INSIGHT_STARTS_AT_0
            ),
            "character_creation_availability_note": (
                XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_NOTE_INSIGHT_STARTS_AT_0
            ),
            "character_creation_availability_status": (
                XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_STATUS_SEEDED
            ),
            "learnable_without_master": True,
            "requires_master": False,
            "master_requirement": XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE,
            "master_requirement_reason": (
                XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_REASON_NO_MASTER_REQUIRED
            ),
            "master_requirement_note": (
                XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NOTE_NO_MASTER_REQUIRED
            ),
            "master_requirement_status": (
                XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_STATUS_LEARNABLE_WITHOUT_MASTER
            ),
        }
    return normalized


def _normalize_generic_technique_prerequisites(
    raw_prerequisites: object,
    *,
    context: str,
) -> list[dict[str, str]]:
    if raw_prerequisites is None:
        return []
    if not isinstance(raw_prerequisites, list):
        raise ValueError(f"{context} must be a list.")

    normalized: list[dict[str, str]] = []
    for index, raw_prerequisite in enumerate(raw_prerequisites, start=1):
        if isinstance(raw_prerequisite, str):
            label = raw_prerequisite.strip()
            kind = "requirement"
            value = _normalize_identifier(label)
            note = ""
        elif isinstance(raw_prerequisite, dict):
            label = str(raw_prerequisite.get("label") or raw_prerequisite.get("name") or "").strip()
            kind = _normalize_identifier(raw_prerequisite.get("kind") or "requirement")
            value = _normalize_identifier(raw_prerequisite.get("value") or label)
            note = str(raw_prerequisite.get("note") or "").strip()
        else:
            raise ValueError(f"{context} {index} must be a string or object.")

        if not label:
            raise ValueError(f"{context} {index} is missing a label.")
        if not kind:
            raise ValueError(f"{context} {index} is missing a kind.")
        if not value:
            raise ValueError(f"{context} {index} is missing a value.")
        record = {
            "kind": kind,
            "value": value,
            "label": label,
        }
        if note:
            record["note"] = note
        normalized.append(record)
    return normalized


def _normalize_rank_ability_grants(
    raw_grants: list[object],
    *,
    context: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, raw_grant in enumerate(raw_grants, start=1):
        if isinstance(raw_grant, str):
            name = raw_grant.strip()
            raw_kind: object = None
            raw_key: object = None
        elif isinstance(raw_grant, dict):
            name = str(raw_grant.get("name") or raw_grant.get("title") or "").strip()
            raw_kind = raw_grant.get("kind")
            raw_key = raw_grant.get("ability_key") or raw_grant.get("key")
        else:
            raise ValueError(f"{context} ability grant {index} must be a string or object.")

        if not name:
            raise ValueError(f"{context} ability grant {index} is missing a name.")
        ability_key = _normalize_identifier(raw_key) or _normalize_identifier(name)
        if not ability_key:
            raise ValueError(f"{context} ability grant {index} is missing an ability key.")
        if ability_key in seen_keys:
            raise ValueError(f"{context} ability grant {ability_key!r} is duplicated.")
        seen_keys.add(ability_key)

        kind_key = _normalize_ability_kind(raw_kind, name=name)
        normalized.append(
            {
                "ability_key": ability_key,
                "name": name,
                "kind": XIANXIA_MARTIAL_ART_ABILITY_KIND_LABELS[kind_key],
                "kind_key": kind_key,
                "ability_kind": XIANXIA_MARTIAL_ART_ABILITY_KIND_LABELS[kind_key],
                "ability_kind_key": kind_key,
            }
        )

    return normalized


def _normalize_ability_kind(raw_kind: object, *, name: str) -> str:
    kind_key = _normalize_identifier(raw_kind)
    if not kind_key:
        lowered_name = name.strip().lower()
        if lowered_name.endswith(" technique"):
            kind_key = "technique"
        elif lowered_name.endswith(" maneuver"):
            kind_key = "maneuver"
        elif lowered_name.endswith(" stance"):
            kind_key = "stance"
        elif lowered_name.endswith(" aura"):
            kind_key = "aura"
        else:
            kind_key = "other"
    if kind_key not in XIANXIA_MARTIAL_ART_ABILITY_KIND_KEYS:
        raise ValueError(f"Xianxia Martial Art ability kind {kind_key!r} is not supported.")
    return kind_key


def _normalize_energy_maximum_increases(
    raw_grants: object,
    *,
    context: str,
) -> dict[str, int]:
    if not isinstance(raw_grants, dict):
        raise ValueError(f"{context} must be an object.")

    normalized_keys = {_normalize_identifier(key): key for key in raw_grants}
    unknown = sorted(key for key in normalized_keys if key not in XIANXIA_ENERGY_KEYS)
    if unknown:
        raise ValueError(f"{context} uses unknown Energy keys: " + ", ".join(unknown) + ".")
    missing = [key for key in XIANXIA_ENERGY_KEYS if key not in normalized_keys]
    if missing:
        raise ValueError(f"{context} is missing Energy keys: " + ", ".join(missing) + ".")

    return {
        energy_key: _normalize_non_negative_int(
            raw_grants[normalized_keys[energy_key]],
            context=f"{context} {energy_key}",
        )
        for energy_key in XIANXIA_ENERGY_KEYS
    }


def _validate_martial_art_rank_resource_grants_cover_entries(
    resource_grants: dict[str, dict[str, dict[str, int]]],
    raw_entries: list[Any],
    rank_sets: dict[str, Any],
) -> None:
    expected_martial_art_keys: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        if _normalize_identifier(raw_entry.get("entry_type")) != "martial_art":
            continue
        raw_metadata = raw_entry.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        martial_art_key = _normalize_identifier(
            metadata.get("martial_art_key")
            or metadata.get("xianxia_martial_art_key")
            or raw_entry.get("slug")
            or raw_entry.get("title")
        )
        if not martial_art_key:
            raise ValueError("Xianxia Martial Art seed entry is missing a Martial Art key.")
        expected_martial_art_keys.add(martial_art_key)
        expected_rank_keys = tuple(
            rank_sets["by_martial_art_key"].get(martial_art_key)
            or rank_sets["default"]
        )
        actual_rank_keys = tuple(resource_grants.get(martial_art_key, {}))
        if actual_rank_keys != expected_rank_keys:
            raise ValueError(
                f"Xianxia Martial Art rank resource grants for {martial_art_key!r} "
                "must match the ranks present in the seed."
            )

    extra_martial_art_keys = sorted(set(resource_grants) - expected_martial_art_keys)
    if extra_martial_art_keys:
        raise ValueError(
            "Xianxia Martial Art rank resource grants include unknown Martial Arts: "
            + ", ".join(extra_martial_art_keys)
            + "."
        )


def _validate_martial_art_rank_ability_grants_cover_entries(
    ability_grants: dict[str, dict[str, list[dict[str, Any]]]],
    raw_entries: list[Any],
    rank_sets: dict[str, Any],
) -> None:
    expected_martial_art_keys: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        if _normalize_identifier(raw_entry.get("entry_type")) != "martial_art":
            continue
        raw_metadata = raw_entry.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        martial_art_key = _normalize_identifier(
            metadata.get("martial_art_key")
            or metadata.get("xianxia_martial_art_key")
            or raw_entry.get("slug")
            or raw_entry.get("title")
        )
        if not martial_art_key:
            raise ValueError("Xianxia Martial Art seed entry is missing a Martial Art key.")
        expected_martial_art_keys.add(martial_art_key)
        expected_rank_keys = tuple(
            rank_sets["by_martial_art_key"].get(martial_art_key)
            or rank_sets["default"]
        )
        actual_rank_keys = tuple(ability_grants.get(martial_art_key, {}))
        if actual_rank_keys != expected_rank_keys:
            raise ValueError(
                f"Xianxia Martial Art rank ability grants for {martial_art_key!r} "
                "must match the ranks present in the seed."
            )

    extra_martial_art_keys = sorted(set(ability_grants) - expected_martial_art_keys)
    if extra_martial_art_keys:
        raise ValueError(
            "Xianxia Martial Art rank ability grants include unknown Martial Arts: "
            + ", ".join(extra_martial_art_keys)
            + "."
        )


def _validate_generic_technique_details_cover_entries(
    generic_technique_details: dict[str, dict[str, Any]],
    raw_entries: list[Any],
) -> None:
    expected_generic_technique_keys: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        if _normalize_identifier(raw_entry.get("entry_type")) != "generic_technique":
            continue
        raw_metadata = raw_entry.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        generic_technique_key = _normalize_identifier(
            metadata.get("generic_technique_key")
            or metadata.get("xianxia_generic_technique_key")
            or raw_entry.get("slug")
            or raw_entry.get("title")
        )
        if not generic_technique_key:
            raise ValueError(
                "Xianxia Generic Technique seed entry is missing a Generic Technique key."
            )
        expected_generic_technique_keys.add(generic_technique_key)
        if generic_technique_key not in generic_technique_details:
            raise ValueError(
                f"Xianxia Generic Technique details are missing {generic_technique_key!r}."
            )

    extra_generic_technique_keys = sorted(
        set(generic_technique_details) - expected_generic_technique_keys
    )
    if extra_generic_technique_keys:
        raise ValueError(
            "Xianxia Generic Technique details include unknown Generic Techniques: "
            + ", ".join(extra_generic_technique_keys)
            + "."
        )


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
    rank_keys = _martial_art_rank_keys_for(martial_art_key)
    rank_resource_grants = _martial_art_rank_resource_grants_for(martial_art_key, rank_keys)
    rank_ability_grants = _martial_art_rank_ability_grants_for(martial_art_key, rank_keys)
    rank_ability_effects = _martial_art_rank_ability_effects_for(martial_art_key, rank_keys)
    rank_records = _build_martial_art_rank_records(
        martial_art_key=martial_art_key,
        martial_art_slug=slug,
        rank_keys=rank_keys,
        rank_available=True,
        rank_resource_grants=rank_resource_grants,
        rank_ability_grants=rank_ability_grants,
        rank_ability_effects=rank_ability_effects,
    )
    missing_rank_keys = [
        rank_key for rank_key in XIANXIA_MARTIAL_ART_RANK_KEYS if rank_key not in rank_keys
    ]
    missing_rank_records = _build_martial_art_rank_records(
        martial_art_key=martial_art_key,
        martial_art_slug=slug,
        rank_keys=missing_rank_keys,
        rank_available=False,
        rank_resource_grants={},
        rank_ability_grants={},
        rank_ability_effects={},
    )
    missing_rank_names = [
        str(_XIANXIA_MARTIAL_ART_RANK_LOOKUP[rank_key]["rank_name"])
        for rank_key in missing_rank_keys
    ]
    incomplete_rank_flags = {
        rank_key: rank_key in set(missing_rank_keys)
        for rank_key in XIANXIA_MARTIAL_ART_RANK_KEYS
    }
    rank_completion_status = (
        XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
        if missing_rank_keys
        else XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE
    )
    metadata_rank_records = [dict(record) for record in rank_records]
    body_rank_records = [dict(record) for record in rank_records]
    metadata_missing_rank_records = [dict(record) for record in missing_rank_records]
    body_missing_rank_records = [dict(record) for record in missing_rank_records]
    metadata["rank_records_seeded"] = True
    metadata["rank_records_status"] = (
        XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED
    )
    metadata["rank_completion_status"] = rank_completion_status
    metadata["xianxia_rank_completion_status"] = rank_completion_status
    metadata["has_incomplete_ranks"] = bool(missing_rank_keys)
    metadata["incomplete_rank_flags"] = incomplete_rank_flags
    metadata["martial_art_rank_records"] = metadata_rank_records
    metadata["xianxia_martial_art_rank_records"] = [dict(record) for record in rank_records]
    metadata["rank_resource_grants_seeded"] = True
    metadata["rank_resource_grants_status"] = (
        XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED
    )
    metadata["martial_art_rank_resource_grants"] = {
        rank_key: dict(rank_resource_grants[rank_key])
        for rank_key in rank_keys
    }
    metadata["xianxia_martial_art_rank_resource_grants"] = {
        rank_key: dict(rank_resource_grants[rank_key])
        for rank_key in rank_keys
    }
    metadata["rank_ability_grants_seeded"] = True
    metadata["rank_ability_grants_status"] = (
        XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED
    )
    metadata["rank_ability_effects_seeded"] = True
    metadata["rank_ability_effects_status"] = (
        XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
    )
    metadata["martial_art_rank_ability_grants"] = {
        rank_key: [dict(grant) for grant in _rank_record_ability_grants(rank_records, rank_key)]
        for rank_key in rank_keys
    }
    metadata["xianxia_martial_art_rank_ability_grants"] = {
        rank_key: [dict(grant) for grant in grants]
        for rank_key, grants in metadata["martial_art_rank_ability_grants"].items()
    }
    metadata["martial_art_missing_rank_records"] = metadata_missing_rank_records
    metadata["xianxia_martial_art_missing_rank_records"] = [
        dict(record) for record in missing_rank_records
    ]
    if missing_rank_keys:
        rank_completion_note = _build_martial_art_draft_note(missing_rank_names)
        metadata["missing_rank_keys"] = missing_rank_keys
        metadata["missing_rank_names"] = missing_rank_names
        metadata["missing_rank_reason"] = XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        metadata["rank_completion_note"] = rank_completion_note
        metadata["source_draft_status"] = (
            XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        )

    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        martial_art_body = {}
        body["xianxia_martial_art"] = martial_art_body
    martial_art_body["rank_records_seeded"] = True
    martial_art_body["rank_records_status"] = (
        XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED
    )
    martial_art_body["rank_completion_status"] = rank_completion_status
    martial_art_body["has_incomplete_ranks"] = bool(missing_rank_keys)
    martial_art_body["incomplete_rank_flags"] = dict(incomplete_rank_flags)
    martial_art_body["rank_records"] = body_rank_records
    martial_art_body["xianxia_martial_art_rank_records"] = [dict(record) for record in rank_records]
    martial_art_body["rank_resource_grants_seeded"] = True
    martial_art_body["rank_resource_grants_status"] = (
        XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED
    )
    martial_art_body["rank_resource_grants"] = {
        rank_key: dict(rank_resource_grants[rank_key])
        for rank_key in rank_keys
    }
    martial_art_body["xianxia_martial_art_rank_resource_grants"] = {
        rank_key: dict(rank_resource_grants[rank_key])
        for rank_key in rank_keys
    }
    martial_art_body["rank_ability_grants_seeded"] = True
    martial_art_body["rank_ability_grants_status"] = (
        XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED
    )
    martial_art_body["rank_ability_effects_seeded"] = True
    martial_art_body["rank_ability_effects_status"] = (
        XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
    )
    martial_art_body["rank_ability_grants"] = {
        rank_key: [dict(grant) for grant in _rank_record_ability_grants(rank_records, rank_key)]
        for rank_key in rank_keys
    }
    martial_art_body["xianxia_martial_art_rank_ability_grants"] = {
        rank_key: [dict(grant) for grant in grants]
        for rank_key, grants in martial_art_body["rank_ability_grants"].items()
    }
    martial_art_body["missing_rank_records"] = body_missing_rank_records
    martial_art_body["xianxia_martial_art_missing_rank_records"] = [
        dict(record) for record in missing_rank_records
    ]
    if missing_rank_keys:
        martial_art_body["missing_rank_keys"] = missing_rank_keys
        martial_art_body["missing_rank_names"] = missing_rank_names
        martial_art_body["missing_rank_reason"] = (
            XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        )
        martial_art_body["rank_completion_note"] = rank_completion_note
        martial_art_body["source_draft_status"] = (
            XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        )


def _stamp_generic_technique_details(
    metadata: dict[str, Any],
    body: dict[str, Any],
    *,
    slug: str,
) -> None:
    generic_technique_key = _normalize_identifier(
        metadata.get("generic_technique_key")
        or metadata.get("xianxia_generic_technique_key")
        or slug
    )
    details = _generic_technique_details_for(generic_technique_key)
    metadata["generic_technique_details_seeded"] = True
    metadata["generic_technique_details_status"] = (
        XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED
    )
    metadata["insight_cost"] = int(details["insight_cost"])
    metadata["prerequisites"] = [
        dict(prerequisite) for prerequisite in details["prerequisites"]
    ]
    metadata["resource_costs"] = [dict(cost) for cost in details["resource_costs"]]
    metadata["range_tags"] = list(details["range_tags"])
    metadata["effort_tags"] = list(details["effort_tags"])
    metadata["reset_cadence"] = details["reset_cadence"]
    metadata["support_state"] = str(details["support_state"])
    metadata["xianxia_support_state"] = str(details["xianxia_support_state"])
    metadata["available_at_character_creation"] = bool(
        details["available_at_character_creation"]
    )
    metadata["character_creation_availability"] = str(
        details["character_creation_availability"]
    )
    metadata["character_creation_availability_reason"] = str(
        details["character_creation_availability_reason"]
    )
    metadata["character_creation_availability_note"] = str(
        details["character_creation_availability_note"]
    )
    metadata["character_creation_availability_status"] = str(
        details["character_creation_availability_status"]
    )
    metadata["learnable_without_master"] = bool(details["learnable_without_master"])
    metadata["requires_master"] = bool(details["requires_master"])
    metadata["master_requirement"] = str(details["master_requirement"])
    metadata["master_requirement_reason"] = str(details["master_requirement_reason"])
    metadata["master_requirement_note"] = str(details["master_requirement_note"])
    metadata["master_requirement_status"] = str(details["master_requirement_status"])

    generic_technique_body = body.get("xianxia_generic_technique")
    if not isinstance(generic_technique_body, dict):
        generic_technique_body = {}
        body["xianxia_generic_technique"] = generic_technique_body
    generic_technique_body["details_seeded"] = True
    generic_technique_body["details_status"] = (
        XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED
    )
    generic_technique_body["insight_cost"] = int(details["insight_cost"])
    generic_technique_body["prerequisites"] = [
        dict(prerequisite) for prerequisite in details["prerequisites"]
    ]
    generic_technique_body["resource_costs"] = [
        dict(cost) for cost in details["resource_costs"]
    ]
    generic_technique_body["range_tags"] = list(details["range_tags"])
    generic_technique_body["effort_tags"] = list(details["effort_tags"])
    generic_technique_body["reset_cadence"] = details["reset_cadence"]
    generic_technique_body["support_state"] = str(details["support_state"])
    generic_technique_body["xianxia_support_state"] = str(details["xianxia_support_state"])
    generic_technique_body["available_at_character_creation"] = bool(
        details["available_at_character_creation"]
    )
    generic_technique_body["character_creation_availability"] = str(
        details["character_creation_availability"]
    )
    generic_technique_body["character_creation_availability_reason"] = str(
        details["character_creation_availability_reason"]
    )
    generic_technique_body["character_creation_availability_note"] = str(
        details["character_creation_availability_note"]
    )
    generic_technique_body["character_creation_availability_status"] = str(
        details["character_creation_availability_status"]
    )
    generic_technique_body["learnable_without_master"] = bool(
        details["learnable_without_master"]
    )
    generic_technique_body["requires_master"] = bool(details["requires_master"])
    generic_technique_body["master_requirement"] = str(details["master_requirement"])
    generic_technique_body["master_requirement_reason"] = str(
        details["master_requirement_reason"]
    )
    generic_technique_body["master_requirement_note"] = str(
        details["master_requirement_note"]
    )
    generic_technique_body["master_requirement_status"] = str(
        details["master_requirement_status"]
    )
    body["support_state"] = str(details["support_state"])
    body["xianxia_support_state"] = str(details["xianxia_support_state"])


def _build_martial_art_draft_note(missing_rank_names: list[str]) -> str:
    missing_label = ", ".join(missing_rank_names)
    return (
        "The reviewed source intentionally stops before the following higher "
        f"rank records: {missing_label}. These missing higher ranks are intentional draft content, "
        "not an import failure."
    )


def _martial_art_draft_search_parts(body: dict[str, Any]) -> list[str]:
    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        return []
    return [
        str(martial_art_body.get("rank_completion_status") or ""),
        str(martial_art_body.get("missing_rank_reason") or ""),
        str(martial_art_body.get("rank_completion_note") or ""),
        " ".join(str(value) for value in martial_art_body.get("missing_rank_names") or []),
    ]


def _martial_art_ability_search_parts(body: dict[str, Any]) -> list[str]:
    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        return []
    rank_ability_grants = martial_art_body.get("rank_ability_grants")
    if not isinstance(rank_ability_grants, dict):
        return []

    parts: list[str] = []
    for grants in rank_ability_grants.values():
        if not isinstance(grants, list):
            continue
        for grant in grants:
            if not isinstance(grant, dict):
                continue
            parts.extend(
                [
                    str(grant.get("name") or ""),
                    str(grant.get("kind") or ""),
                    str(grant.get("kind_key") or ""),
                    str(grant.get("ability_ref") or ""),
                    str(grant.get("support_state") or ""),
                ]
            )
            parts.extend(str(value) for value in grant.get("range_tags") or [])
            parts.extend(str(value) for value in grant.get("damage_effort_tags") or [])
            parts.extend(str(value) for value in grant.get("duration_tags") or [])
            for cost in grant.get("resource_costs") or []:
                if not isinstance(cost, dict):
                    continue
                parts.extend(
                    [
                        str(cost.get("resource_key") or ""),
                        str(cost.get("amount") or ""),
                    ]
                )
    return parts


def _generic_technique_details_search_parts(body: dict[str, Any]) -> list[str]:
    generic_technique_body = body.get("xianxia_generic_technique")
    if not isinstance(generic_technique_body, dict):
        return []

    parts = [
        str(generic_technique_body.get("insight_cost") or ""),
        str(generic_technique_body.get("reset_cadence") or ""),
        str(generic_technique_body.get("support_state") or ""),
        str(generic_technique_body.get("character_creation_availability") or ""),
        str(generic_technique_body.get("character_creation_availability_reason") or ""),
        str(generic_technique_body.get("character_creation_availability_note") or ""),
        str(generic_technique_body.get("character_creation_availability_status") or ""),
        str(generic_technique_body.get("master_requirement") or ""),
        str(generic_technique_body.get("master_requirement_reason") or ""),
        str(generic_technique_body.get("master_requirement_note") or ""),
        str(generic_technique_body.get("master_requirement_status") or ""),
    ]
    parts.extend(str(value) for value in generic_technique_body.get("range_tags") or [])
    parts.extend(str(value) for value in generic_technique_body.get("effort_tags") or [])
    for prerequisite in generic_technique_body.get("prerequisites") or []:
        if not isinstance(prerequisite, dict):
            continue
        parts.extend(
            [
                str(prerequisite.get("kind") or ""),
                str(prerequisite.get("value") or ""),
                str(prerequisite.get("label") or ""),
                str(prerequisite.get("note") or ""),
            ]
        )
    for cost in generic_technique_body.get("resource_costs") or []:
        if not isinstance(cost, dict):
            continue
        parts.extend(
            [
                str(cost.get("resource_key") or ""),
                str(cost.get("amount") or ""),
                str(cost.get("timing") or ""),
                str(cost.get("note") or ""),
            ]
        )
    return parts


def _render_martial_art_draft_marker_html(body: dict[str, Any]) -> str:
    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        return ""
    if (
        martial_art_body.get("rank_completion_status")
        != XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
    ):
        return ""
    note = str(martial_art_body.get("rank_completion_note") or "").strip()
    missing_rank_names = [
        str(value).strip()
        for value in martial_art_body.get("missing_rank_names") or []
        if str(value).strip()
    ]
    missing_ranks = ", ".join(missing_rank_names)
    parts = ["<section>", "<h2>Intentional Draft Content</h2>"]
    if note:
        parts.append(f"<p>{escape(note)}</p>")
    if missing_ranks:
        parts.append(f"<p><strong>Missing higher ranks:</strong> {escape(missing_ranks)}</p>")
    parts.append("</section>")
    return "".join(parts)


def _render_generic_technique_details_html(body: dict[str, Any]) -> str:
    generic_technique_body = body.get("xianxia_generic_technique")
    if not isinstance(generic_technique_body, dict):
        return ""
    if not generic_technique_body.get("details_seeded"):
        return ""

    parts = ["<section>", "<h2>Technique Details</h2>"]
    insight_cost = generic_technique_body.get("insight_cost")
    if insight_cost is not None:
        parts.append(f"<p><strong>Insight Cost:</strong> {escape(str(insight_cost))}</p>")

    prerequisites = _format_generic_technique_prerequisites(
        generic_technique_body.get("prerequisites")
    )
    if prerequisites:
        parts.append(f"<p><strong>Prerequisites:</strong> {prerequisites}</p>")

    character_creation_availability = str(
        generic_technique_body.get("character_creation_availability") or ""
    ).strip()
    if character_creation_availability:
        character_creation_note = str(
            generic_technique_body.get("character_creation_availability_note") or ""
        ).strip()
        character_creation_label = character_creation_availability.replace("_", " ")
        character_creation_text = escape(character_creation_label)
        if character_creation_note:
            character_creation_text += f" ({escape(character_creation_note)})"
        parts.append(
            f"<p><strong>Character Creation:</strong> {character_creation_text}</p>"
        )

    master_requirement = str(
        generic_technique_body.get("master_requirement") or ""
    ).strip()
    if master_requirement:
        master_requirement_note = str(
            generic_technique_body.get("master_requirement_note") or ""
        ).strip()
        if generic_technique_body.get("learnable_without_master"):
            master_requirement_text = "learnable without a Master"
        else:
            master_requirement_text = master_requirement.replace("_", " ")
        learning_text = escape(master_requirement_text)
        if master_requirement_note:
            learning_text += f" ({escape(master_requirement_note)})"
        parts.append(f"<p><strong>Learning:</strong> {learning_text}</p>")

    resource_costs = _format_resource_costs(generic_technique_body.get("resource_costs"))
    if resource_costs:
        parts.append(f"<p><strong>Resource Costs:</strong> {resource_costs}</p>")

    ranges = _format_string_tags(generic_technique_body.get("range_tags"))
    if ranges:
        parts.append(f"<p><strong>Ranges:</strong> {ranges}</p>")

    effort_tags = _format_string_tags(generic_technique_body.get("effort_tags"))
    if effort_tags:
        parts.append(f"<p><strong>Effort Tags:</strong> {effort_tags}</p>")

    reset_cadence = str(generic_technique_body.get("reset_cadence") or "").strip()
    if reset_cadence:
        parts.append(
            "<p><strong>Reset Cadence:</strong> "
            f"{escape(reset_cadence.replace('_', ' '))}</p>"
        )

    support_state = str(generic_technique_body.get("support_state") or "").strip()
    if support_state:
        parts.append(
            f"<p><strong>Support State:</strong> {escape(support_state.replace('_', ' '))}</p>"
        )
    parts.append("</section>")
    return "".join(parts)


def _render_martial_art_rank_records_html(body: dict[str, Any]) -> str:
    martial_art_body = body.get("xianxia_martial_art")
    if not isinstance(martial_art_body, dict):
        return ""
    rank_records = [
        record for record in martial_art_body.get("rank_records") or [] if isinstance(record, dict)
    ]
    if not rank_records:
        return ""

    parts = ["<section>", "<h2>Rank Records</h2>"]
    for record in rank_records:
        rank_name = str(record.get("rank_name") or "").strip()
        rank_ref = str(record.get("rank_ref") or "").strip()
        rank_anchor = _anchor_id_for_ref(rank_ref)
        parts.append(f'<section id="{escape(rank_anchor)}">')
        if rank_name:
            parts.append(f"<h3>{escape(rank_name)}</h3>")
        if rank_ref:
            parts.append(
                f'<p><strong>Rank Ref:</strong> <a href="#{escape(rank_anchor)}">{escape(rank_ref)}</a></p>'
            )

        energy_grants = _format_energy_maximum_increases(
            record.get("energy_maximum_increases")
        )
        if energy_grants:
            parts.append(f"<p><strong>Energy Maximum Increases:</strong> {energy_grants}</p>")

        insight_cost = record.get("insight_cost")
        prerequisite_rank = str(record.get("prerequisite_rank_name") or "None").strip()
        if insight_cost is not None:
            parts.append(
                "<p><strong>Advancement:</strong> "
                f"{escape(str(insight_cost))} Insight; prerequisite rank {escape(prerequisite_rank)}.</p>"
            )

        teacher_note = str(record.get("teacher_breakthrough_note") or "").strip()
        if teacher_note:
            parts.append(f"<p><strong>Teacher/Breakthrough:</strong> {escape(teacher_note)}</p>")
        legendary_note = str(record.get("legendary_prerequisite_note") or "").strip()
        if legendary_note:
            parts.append(f"<p><strong>Legendary Requirement:</strong> {escape(legendary_note)}</p>")

        ability_grants = [
            grant for grant in record.get("ability_grants") or [] if isinstance(grant, dict)
        ]
        if ability_grants:
            parts.append("<h4>Ability Refs</h4>")
            parts.append("<ul>")
            for grant in ability_grants:
                ability_ref = str(grant.get("ability_ref") or "").strip()
                ability_anchor = _anchor_id_for_ref(ability_ref)
                ability_name = str(grant.get("name") or "").strip()
                kind = str(grant.get("kind") or "").strip()
                support_state = str(grant.get("support_state") or "").strip()
                parts.append(f'<li id="{escape(ability_anchor)}">')
                if ability_ref:
                    parts.append(
                        f'<a href="#{escape(ability_anchor)}">{escape(ability_ref)}</a>'
                    )
                if ability_name:
                    parts.append(f" - {escape(ability_name)}")
                if kind:
                    parts.append(f" ({escape(kind)})")
                ability_tags = _format_ability_metadata_tags(grant)
                if ability_tags:
                    parts.append(f" - {ability_tags}")
                if support_state:
                    parts.append(f" - {escape(support_state.replace('_', ' '))}")
                parts.append("</li>")
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</section>")
    return "".join(parts)


def _anchor_id_for_ref(value: str) -> str:
    anchor = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower()
    return anchor or "xianxia-ref"


def _format_energy_maximum_increases(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for energy_key in XIANXIA_ENERGY_KEYS:
        amount = value.get(energy_key)
        if amount is None:
            continue
        label = energy_key.capitalize()
        prefix = "+" if isinstance(amount, int) and amount >= 0 else ""
        parts.append(f"{label} {prefix}{amount}")
    return ", ".join(parts)


def _format_ability_metadata_tags(grant: dict[str, Any]) -> str:
    tag_groups = [
        ("Costs", _format_resource_costs(grant.get("resource_costs"))),
        ("Ranges", _format_string_tags(grant.get("range_tags"))),
        ("Damage/Effort", _format_string_tags(grant.get("damage_effort_tags"))),
        ("Duration", _format_string_tags(grant.get("duration_tags"))),
    ]
    return "; ".join(f"{label}: {value}" for label, value in tag_groups if value)


def _format_resource_costs(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for cost in value:
        if not isinstance(cost, dict):
            continue
        resource_key = str(cost.get("resource_key") or "").strip()
        amount = cost.get("amount")
        if not resource_key or amount is None:
            continue
        parts.append(f"{resource_key.replace('_', ' ')} {amount}")
    return ", ".join(escape(part) for part in parts)


def _format_generic_technique_prerequisites(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for prerequisite in value:
        if not isinstance(prerequisite, dict):
            continue
        label = str(prerequisite.get("label") or "").strip()
        note = str(prerequisite.get("note") or "").strip()
        if not label:
            continue
        parts.append(f"{label} ({note})" if note else label)
    return ", ".join(escape(part) for part in parts)


def _format_string_tags(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(
        escape(str(item).replace("_", " "))
        for item in value
        if str(item).strip()
    )


def _build_martial_art_rank_records(
    *,
    martial_art_key: str,
    martial_art_slug: str,
    rank_keys: list[str],
    rank_available: bool,
    rank_resource_grants: dict[str, dict[str, int]],
    rank_ability_grants: dict[str, list[dict[str, Any]]],
    rank_ability_effects: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rank_key in rank_keys:
        rank_definition = _XIANXIA_MARTIAL_ART_RANK_LOOKUP[rank_key]
        energy_maximum_increases = (
            dict(rank_resource_grants[rank_key])
            if rank_available
            else None
        )
        ability_grants = (
            _build_rank_ability_grants(
                martial_art_key=martial_art_key,
                martial_art_slug=martial_art_slug,
                rank_key=rank_key,
                grants=rank_ability_grants[rank_key],
                ability_effects=rank_ability_effects.get(rank_key, {}),
            )
            if rank_available
            else []
        )
        prerequisite_rank_key = rank_definition.get("prerequisite_rank_key")
        prerequisite_rank_name = (
            str(_XIANXIA_MARTIAL_ART_RANK_LOOKUP[str(prerequisite_rank_key)]["rank_name"])
            if prerequisite_rank_key
            else None
        )
        records.append(
            {
                "martial_art_key": martial_art_key,
                "martial_art_slug": martial_art_slug,
                "rank_key": rank_key,
                "rank_name": str(rank_definition["rank_name"]),
                "rank_order": int(rank_definition["rank_order"]),
                "rank_ref": f"xianxia:{martial_art_slug}:{rank_key}",
                "prerequisite_rank_key": prerequisite_rank_key,
                "prerequisite_rank_name": prerequisite_rank_name,
                "insight_cost": int(rank_definition["insight_cost"]),
                "teacher_breakthrough_requirement": str(
                    rank_definition["teacher_breakthrough_requirement"]
                ),
                "teacher_breakthrough_note": str(rank_definition["teacher_breakthrough_note"]),
                "advancement_note": str(rank_definition["advancement_note"]),
                "legendary_prerequisite_note": str(rank_definition["legendary_prerequisite_note"]),
                "energy_maximum_increases": energy_maximum_increases,
                "xianxia_energy_maximum_increases": (
                    dict(energy_maximum_increases)
                    if isinstance(energy_maximum_increases, dict)
                    else None
                ),
                "rank_resource_grants_status": (
                    XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED
                    if rank_available
                    else None
                ),
                "ability_grants": ability_grants,
                "xianxia_ability_grants": [dict(grant) for grant in ability_grants],
                "rank_ability_grants_status": (
                    XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED
                    if rank_available
                    else None
                ),
                "rank_ability_effects_status": (
                    XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
                    if rank_available
                    else None
                ),
                "rank_available_in_seed": rank_available,
                "is_incomplete_rank": not rank_available,
                "rank_completion_status": (
                    XIANXIA_MARTIAL_ART_RANK_STATUS_PRESENT
                    if rank_available
                    else XIANXIA_MARTIAL_ART_RANK_STATUS_MISSING_INTENTIONAL_DRAFT
                ),
                "incomplete_rank_reason": (
                    None
                    if rank_available
                    else XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
                ),
            }
        )
    return records


def _build_rank_ability_grants(
    *,
    martial_art_key: str,
    martial_art_slug: str,
    rank_key: str,
    grants: list[dict[str, Any]],
    ability_effects: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for grant in grants:
        ability_key = str(grant["ability_key"])
        ability_slug = ability_key.replace("_", "-")
        ability_ref = f"xianxia:{martial_art_slug}:{rank_key}:{ability_slug}"
        effect_metadata = _copy_rank_ability_effect(
            ability_effects.get(ability_key) or _default_rank_ability_effect()
        )
        records.append(
            {
                "martial_art_key": martial_art_key,
                "martial_art_slug": martial_art_slug,
                "rank_key": rank_key,
                "ability_key": ability_key,
                "ability_slug": ability_slug,
                "ability_ref": ability_ref,
                "name": str(grant["name"]),
                "kind": str(grant["kind"]),
                "kind_key": str(grant["kind_key"]),
                "ability_kind": str(grant["ability_kind"]),
                "ability_kind_key": str(grant["ability_kind_key"]),
                "resource_costs": effect_metadata["resource_costs"],
                "range_tags": effect_metadata["range_tags"],
                "damage_effort_tags": effect_metadata["damage_effort_tags"],
                "duration_tags": effect_metadata["duration_tags"],
                "support_state": str(effect_metadata["support_state"]),
                "xianxia_support_state": str(effect_metadata["xianxia_support_state"]),
            }
        )
    return records


def _default_rank_ability_effect() -> dict[str, Any]:
    return {
        "resource_costs": [],
        "range_tags": [],
        "damage_effort_tags": [],
        "duration_tags": [],
        "support_state": XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE,
        "xianxia_support_state": XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE,
    }


def _copy_rank_ability_effect(effect: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_costs": [
            dict(cost)
            for cost in effect.get("resource_costs", [])
            if isinstance(cost, dict)
        ],
        "range_tags": list(effect.get("range_tags", [])),
        "damage_effort_tags": list(effect.get("damage_effort_tags", [])),
        "duration_tags": list(effect.get("duration_tags", [])),
        "support_state": str(
            effect.get("support_state") or XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
        ),
        "xianxia_support_state": str(
            effect.get("xianxia_support_state")
            or effect.get("support_state")
            or XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
        ),
    }


def _copy_generic_technique_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "insight_cost": int(detail["insight_cost"]),
        "prerequisites": [
            dict(prerequisite)
            for prerequisite in detail.get("prerequisites", [])
            if isinstance(prerequisite, dict)
        ],
        "resource_costs": [
            dict(cost)
            for cost in detail.get("resource_costs", [])
            if isinstance(cost, dict)
        ],
        "range_tags": list(detail.get("range_tags", [])),
        "effort_tags": list(detail.get("effort_tags", [])),
        "reset_cadence": detail.get("reset_cadence"),
        "support_state": str(
            detail.get("support_state") or XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE
        ),
        "xianxia_support_state": str(
            detail.get("xianxia_support_state")
            or detail.get("support_state")
            or XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE
        ),
        "available_at_character_creation": bool(
            detail.get("available_at_character_creation", False)
        ),
        "character_creation_availability": str(
            detail.get("character_creation_availability")
            or XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT
        ),
        "character_creation_availability_reason": str(
            detail.get("character_creation_availability_reason")
            or XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_REASON_INSIGHT_STARTS_AT_0
        ),
        "character_creation_availability_note": str(
            detail.get("character_creation_availability_note")
            or XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_NOTE_INSIGHT_STARTS_AT_0
        ),
        "character_creation_availability_status": str(
            detail.get("character_creation_availability_status")
            or XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_STATUS_SEEDED
        ),
        "learnable_without_master": bool(detail.get("learnable_without_master", True)),
        "requires_master": bool(detail.get("requires_master", False)),
        "master_requirement": str(
            detail.get("master_requirement")
            or XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE
        ),
        "master_requirement_reason": str(
            detail.get("master_requirement_reason")
            or XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_REASON_NO_MASTER_REQUIRED
        ),
        "master_requirement_note": str(
            detail.get("master_requirement_note")
            or XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NOTE_NO_MASTER_REQUIRED
        ),
        "master_requirement_status": str(
            detail.get("master_requirement_status")
            or XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_STATUS_LEARNABLE_WITHOUT_MASTER
        ),
    }


def _rank_record_ability_grants(
    rank_records: list[dict[str, Any]],
    rank_key: str,
) -> list[dict[str, Any]]:
    for record in rank_records:
        if record.get("rank_key") == rank_key:
            raw_grants = record.get("ability_grants")
            if isinstance(raw_grants, list):
                return [dict(grant) for grant in raw_grants if isinstance(grant, dict)]
            return []
    return []


def _martial_art_rank_keys_for(martial_art_key: str) -> list[str]:
    override = _XIANXIA_MARTIAL_ART_RANK_SETS["by_martial_art_key"].get(martial_art_key)
    return list(override or _XIANXIA_MARTIAL_ART_RANK_SETS["default"])


def _martial_art_rank_resource_grants_for(
    martial_art_key: str,
    rank_keys: list[str],
) -> dict[str, dict[str, int]]:
    rank_resource_grants = _XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS.get(martial_art_key)
    if rank_resource_grants is None:
        raise ValueError(
            f"Xianxia Martial Art {martial_art_key!r} is missing rank resource grants."
        )
    actual_rank_keys = tuple(rank_resource_grants)
    if actual_rank_keys != tuple(rank_keys):
        raise ValueError(
            f"Xianxia Martial Art {martial_art_key!r} rank resource grants do not match its rank set."
        )
    return {
        rank_key: dict(rank_resource_grants[rank_key])
        for rank_key in rank_keys
    }


def _martial_art_rank_ability_grants_for(
    martial_art_key: str,
    rank_keys: list[str],
) -> dict[str, list[dict[str, Any]]]:
    rank_ability_grants = _XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS.get(martial_art_key)
    if rank_ability_grants is None:
        raise ValueError(
            f"Xianxia Martial Art {martial_art_key!r} is missing rank ability grants."
        )
    actual_rank_keys = tuple(rank_ability_grants)
    if actual_rank_keys != tuple(rank_keys):
        raise ValueError(
            f"Xianxia Martial Art {martial_art_key!r} rank ability grants do not match its rank set."
        )
    return {
        rank_key: [dict(grant) for grant in rank_ability_grants[rank_key]]
        for rank_key in rank_keys
    }


def _martial_art_rank_ability_effects_for(
    martial_art_key: str,
    rank_keys: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    raw_rank_effects = _XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS.get(martial_art_key, {})
    return {
        rank_key: {
            ability_key: _copy_rank_ability_effect(effect)
            for ability_key, effect in raw_rank_effects.get(rank_key, {}).items()
        }
        for rank_key in rank_keys
    }


def _generic_technique_details_for(generic_technique_key: str) -> dict[str, Any]:
    details = _XIANXIA_GENERIC_TECHNIQUE_DETAILS.get(generic_technique_key)
    if details is None:
        raise ValueError(
            f"Xianxia Generic Technique {generic_technique_key!r} is missing details metadata."
        )
    return _copy_generic_technique_detail(details)


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
_XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS = {
    str(martial_art_key): {
        str(rank_key): dict(grants)
        for rank_key, grants in rank_grants.items()
    }
    for martial_art_key, rank_grants in _XIANXIA_SYSTEMS_SEED_PAYLOAD[
        "martial_art_rank_resource_grants"
    ].items()
}
_XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS = {
    str(martial_art_key): {
        str(rank_key): [dict(grant) for grant in grants]
        for rank_key, grants in rank_grants.items()
    }
    for martial_art_key, rank_grants in _XIANXIA_SYSTEMS_SEED_PAYLOAD[
        "martial_art_rank_ability_grants"
    ].items()
}
_XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS = {
    str(martial_art_key): {
        str(rank_key): {
            str(ability_key): _copy_rank_ability_effect(effect)
            for ability_key, effect in rank_effects.items()
        }
        for rank_key, rank_effects in rank_effects_by_art.items()
    }
    for martial_art_key, rank_effects_by_art in _XIANXIA_SYSTEMS_SEED_PAYLOAD[
        "martial_art_rank_ability_effects"
    ].items()
}
_XIANXIA_GENERIC_TECHNIQUE_DETAILS = {
    str(generic_technique_key): _copy_generic_technique_detail(detail)
    for generic_technique_key, detail in _XIANXIA_SYSTEMS_SEED_PAYLOAD[
        "generic_technique_details"
    ].items()
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
