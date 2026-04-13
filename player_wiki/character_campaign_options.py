from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .character_adjustments import normalize_manual_stat_adjustments

VALID_CAMPAIGN_OPTION_KINDS = {"feature", "item", "feat", "species", "background"}
FEATURE_LIKE_CAMPAIGN_OPTION_KINDS = {"feature", "feat", "species", "background"}
VALID_CAMPAIGN_FEATURE_ACTIVATION_TYPES = {
    "passive",
    "action",
    "bonus_action",
    "reaction",
    "special",
}
VALID_CAMPAIGN_RESOURCE_RESET_TYPES = {"manual", "short_rest", "long_rest"}
VALID_CAMPAIGN_RESOURCE_SCALING_MODES = {"level", "half_level", "proficiency_bonus", "thresholds"}
VALID_CAMPAIGN_RESOURCE_SCALING_ROUNDS = {"down", "up", "nearest"}
VALID_CAMPAIGN_OVERLAY_SUPPORT_TYPES = {"reference_only", "modeled"}


def normalize_campaign_base_rule_refs(value: Any) -> list[dict[str, Any]]:
    raw_items = [value] if isinstance(value, dict) else list(value or []) if isinstance(value, list) else []
    normalized_refs: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for raw_item in raw_items:
        item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
        if not item:
            continue
        systems_ref = dict(item.get("systems_ref") or {}) if isinstance(item.get("systems_ref"), dict) else {}
        rule_key = _normalize_rule_key(item.get("rule_key", systems_ref.get("rule_key")))
        entry_key = str(item.get("entry_key") or item.get("systems_entry_key") or systems_ref.get("entry_key") or "").strip()
        slug = str(item.get("slug") or item.get("entry_slug") or systems_ref.get("slug") or "").strip()
        source_id = str(item.get("source_id") or item.get("source") or systems_ref.get("source_id") or "").strip().upper()
        entry_type = str(item.get("entry_type") or systems_ref.get("entry_type") or "").strip().lower()
        title = str(item.get("title") or systems_ref.get("title") or "").strip()
        anchor = str(item.get("anchor") or item.get("section_anchor") or "").strip()
        section_title = str(item.get("section_title") or item.get("section") or item.get("anchor_title") or "").strip()
        if not rule_key and not entry_key and not slug:
            continue
        marker = (
            rule_key,
            entry_key.casefold(),
            slug.casefold(),
            anchor.casefold(),
        )
        if marker in seen_keys:
            continue
        seen_keys.add(marker)
        normalized: dict[str, Any] = {}
        if rule_key:
            normalized["rule_key"] = rule_key
        if entry_key:
            normalized["entry_key"] = entry_key
        if slug:
            normalized["slug"] = slug
        if source_id:
            normalized["source_id"] = source_id
        if entry_type:
            normalized["entry_type"] = entry_type
        if title:
            normalized["title"] = title
        if anchor:
            normalized["anchor"] = anchor
        if section_title:
            normalized["section_title"] = section_title
        normalized_refs.append(normalized)
    return normalized_refs


def normalize_campaign_overlay_support(
    value: Any,
    *,
    option: dict[str, Any] | None = None,
) -> str | None:
    normalized_value = _normalize_overlay_support_value(value)
    if normalized_value is not None:
        return normalized_value
    candidate_option = dict(option or {}) if isinstance(option, dict) else {}
    if not normalize_campaign_base_rule_refs(candidate_option.get("base_rule_refs")):
        return None
    return "modeled" if _campaign_option_has_modeled_overlay_content(candidate_option) else "reference_only"


def build_campaign_page_character_option(
    record: Any,
    *,
    default_kind: str,
) -> dict[str, Any] | None:
    metadata = dict(getattr(record, "metadata", {}) or {})
    raw_option = metadata.get("character_option")
    if not isinstance(raw_option, dict):
        return None

    page_ref = str(getattr(record, "page_ref", "") or "").strip()
    page = getattr(record, "page", None)
    title = str(getattr(page, "title", "") or "").strip() or page_ref
    summary = str(getattr(page, "summary", "") or "").strip()
    return normalize_campaign_character_option(
        raw_option,
        page_ref=page_ref,
        title=title,
        summary=summary,
        default_kind=default_kind,
    )


def normalize_campaign_character_option(
    payload: Any,
    *,
    page_ref: str,
    title: str,
    summary: str,
    default_kind: str,
) -> dict[str, Any] | None:
    raw_option = dict(payload or {}) if isinstance(payload, dict) else {}
    if not raw_option:
        return None

    kind = str(raw_option.get("kind") or default_kind or "feature").strip().lower()
    if kind not in VALID_CAMPAIGN_OPTION_KINDS:
        kind = default_kind if default_kind in VALID_CAMPAIGN_OPTION_KINDS else "feature"

    grants = dict(raw_option.get("grants") or {}) if isinstance(raw_option.get("grants"), dict) else {}
    proficiencies = dict(raw_option.get("proficiencies") or {}) if isinstance(raw_option.get("proficiencies"), dict) else {}
    normalized = {
        "kind": kind,
        "page_ref": str(page_ref or "").strip(),
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip(),
        "display_name": str(raw_option.get("name") or "").strip() or str(title or "").strip(),
        "proficiencies": {
            "armor": _normalize_string_list(
                proficiencies.get("armor") if "armor" in proficiencies else grants.get("armor", raw_option.get("armor"))
            ),
            "weapons": _normalize_string_list(
                proficiencies.get("weapons") if "weapons" in proficiencies else grants.get("weapons", raw_option.get("weapons"))
            ),
            "tools": _normalize_string_list(
                proficiencies.get("tools") if "tools" in proficiencies else grants.get("tools", raw_option.get("tools"))
            ),
            "languages": _normalize_string_list(
                proficiencies.get("languages") if "languages" in proficiencies else grants.get("languages", raw_option.get("languages"))
            ),
            "skills": _normalize_string_list(
                proficiencies.get("skills") if "skills" in proficiencies else grants.get("skills", raw_option.get("skills"))
            ),
        },
        "stat_adjustments": normalize_manual_stat_adjustments(
            grants.get("stat_adjustments") if "stat_adjustments" in grants else raw_option.get("stat_adjustments")
        ),
        "spells": _normalize_spell_grants(
            grants.get("spells") if "spells" in grants else raw_option.get("spells")
        ),
    }
    base_rule_refs = normalize_campaign_base_rule_refs(
        raw_option.get("base_rule_refs", raw_option.get("baseRuleRefs"))
    )
    if base_rule_refs:
        normalized["base_rule_refs"] = base_rule_refs
    spell_support = raw_option.get("spell_support", raw_option.get("spellSupport"))
    if spell_support is not None:
        normalized["spell_support"] = deepcopy(spell_support)
    spell_manager = raw_option.get("spell_manager", raw_option.get("spellManager"))
    if spell_manager is not None:
        normalized["spell_manager"] = deepcopy(spell_manager)

    if kind in FEATURE_LIKE_CAMPAIGN_OPTION_KINDS:
        activation_type = str(raw_option.get("activation_type") or "passive").strip().lower()
        if activation_type not in VALID_CAMPAIGN_FEATURE_ACTIVATION_TYPES:
            activation_type = "passive"
        normalized.update(
            {
                "feature_name": str(raw_option.get("name") or "").strip() or str(title or "").strip(),
                "description_markdown": str(
                    raw_option.get("description_markdown")
                    or raw_option.get("description")
                    or summary
                    or ""
                ),
                "activation_type": activation_type,
            }
        )
        resource = _normalize_resource_grant(
            grants.get("resource") if "resource" in grants else raw_option.get("resource")
        )
        if resource is not None:
            normalized["resource"] = resource
        additional_spells = raw_option.get("additional_spells", raw_option.get("additionalSpells"))
        if additional_spells is not None:
            normalized["additional_spells"] = deepcopy(additional_spells)
        modeled_effects = _normalize_modeled_effects(
            raw_option.get("modeled_effects", raw_option.get("modeledEffects"))
        )
        if modeled_effects:
            normalized["modeled_effects"] = modeled_effects
        if kind == "feature":
            return _finalize_campaign_overlay_support(normalized, raw_option)
        if kind == "feat":
            normalized["feat_name"] = str(raw_option.get("name") or "").strip() or str(title or "").strip()
            for key in (
                "ability",
                "skill_proficiencies",
                "expertise",
                "language_proficiencies",
                "tool_proficiencies",
                "weapon_proficiencies",
                "armor_proficiencies",
                "saving_throw_proficiencies",
                "skill_tool_language_proficiencies",
            ):
                if key in raw_option:
                    normalized[key] = deepcopy(raw_option.get(key))
            optionalfeature_progression = raw_option.get(
                "optionalfeature_progression",
                raw_option.get("optionalfeatureProgression"),
            )
            if optionalfeature_progression is not None:
                normalized["optionalfeature_progression"] = deepcopy(optionalfeature_progression)
            additional_spells = raw_option.get("additional_spells", raw_option.get("additionalSpells"))
            if additional_spells is not None:
                normalized["additional_spells"] = deepcopy(additional_spells)
            return _finalize_campaign_overlay_support(normalized, raw_option)
        if kind == "species":
            normalized["species_name"] = str(raw_option.get("name") or "").strip() or str(title or "").strip()
            normalized_size = _normalize_size_value(raw_option.get("size"))
            if normalized_size:
                normalized["size"] = normalized_size
            normalized_speed = _normalize_speed_value(raw_option.get("speed"))
            if normalized_speed is not None:
                normalized["speed"] = normalized_speed
            for key in ("skill_proficiencies", "tool_proficiencies", "feats"):
                if key in raw_option:
                    normalized[key] = deepcopy(raw_option.get(key))
            languages = raw_option.get("languages")
            if _contains_structured_builder_metadata(languages):
                normalized["languages"] = deepcopy(languages)
            language_proficiencies = raw_option.get("language_proficiencies")
            if language_proficiencies is not None and "languages" not in normalized:
                normalized["languages"] = deepcopy(language_proficiencies)
            return _finalize_campaign_overlay_support(normalized, raw_option)
        if kind == "background":
            normalized["background_name"] = str(raw_option.get("name") or "").strip() or str(title or "").strip()
            for key in ("skill_proficiencies", "language_proficiencies", "tool_proficiencies"):
                if key in raw_option:
                    normalized[key] = deepcopy(raw_option.get(key))
            return _finalize_campaign_overlay_support(normalized, raw_option)

    quantity = _normalize_positive_integer(raw_option.get("quantity"), default=1)
    normalized.update(
        {
            "item_name": str(raw_option.get("name") or "").strip() or str(title or "").strip(),
            "quantity": quantity,
            "weight": str(raw_option.get("weight") or "").strip(),
            "notes": str(raw_option.get("notes") or summary or "").strip(),
        }
    )
    return _finalize_campaign_overlay_support(normalized, raw_option)


def collect_campaign_option_stat_adjustments(option_payloads: list[Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for payload in list(option_payloads or []):
        option = dict(payload or {}) if isinstance(payload, dict) else {}
        for key, value in normalize_manual_stat_adjustments(option.get("stat_adjustments")).items():
            totals[key] = int(totals.get(key) or 0) + int(value)
    return totals


def collect_campaign_option_proficiency_grants(option_payloads: list[Any]) -> dict[str, list[str]]:
    grants = {
        "armor": [],
        "weapons": [],
        "tools": [],
        "languages": [],
        "skills": [],
    }
    seen_by_key = {key: set() for key in grants}
    for payload in list(option_payloads or []):
        option = dict(payload or {}) if isinstance(payload, dict) else {}
        proficiency_payload = dict(option.get("proficiencies") or {})
        for key in grants:
            for value in _normalize_string_list(proficiency_payload.get(key)):
                normalized_value = value.casefold()
                if normalized_value in seen_by_key[key]:
                    continue
                seen_by_key[key].add(normalized_value)
                grants[key].append(value)
    return grants


def collect_campaign_option_spell_grants(option_payloads: list[Any]) -> list[dict[str, Any]]:
    spell_grants: list[dict[str, Any]] = []
    seen_values: set[tuple[str, str, bool, bool]] = set()
    for payload in list(option_payloads or []):
        option = dict(payload or {}) if isinstance(payload, dict) else {}
        for spell_grant in list(option.get("spells") or []):
            grant = dict(spell_grant or {}) if isinstance(spell_grant, dict) else {}
            value = str(grant.get("value") or "").strip()
            if not value:
                continue
            marker = (
                value.casefold(),
                str(grant.get("mark") or "").strip().casefold(),
                bool(grant.get("always_prepared")),
                bool(grant.get("ritual")),
            )
            if marker in seen_values:
                continue
            seen_values.add(marker)
            spell_grants.append(
                {
                    "value": value,
                    "mark": str(grant.get("mark") or "").strip(),
                    "always_prepared": bool(grant.get("always_prepared")),
                    "ritual": bool(grant.get("ritual")),
                }
            )
    return spell_grants


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace("\r", "").replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    values: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if isinstance(raw_item, (dict, list, tuple, set)):
            continue
        clean_item = str(raw_item or "").strip()
        normalized_item = clean_item.casefold()
        if not clean_item or normalized_item in seen:
            continue
        seen.add(normalized_item)
        values.append(clean_item)
    return values


def _normalize_overlay_support_value(value: Any) -> str | None:
    normalized_value = str(value or "").strip().lower().replace("-", "_")
    if not normalized_value:
        return None
    alias_map = {
        "display_only": "reference_only",
        "mechanically_modeled": "modeled",
        "mechanical": "modeled",
        "reference": "reference_only",
    }
    normalized_value = alias_map.get(normalized_value, normalized_value)
    if normalized_value not in VALID_CAMPAIGN_OVERLAY_SUPPORT_TYPES:
        return None
    return normalized_value


def _finalize_campaign_overlay_support(
    normalized: dict[str, Any],
    raw_option: dict[str, Any],
) -> dict[str, Any]:
    overlay_support = normalize_campaign_overlay_support(
        raw_option.get("overlay_support", raw_option.get("overlaySupport")),
        option=normalized,
    )
    if overlay_support:
        normalized["overlay_support"] = overlay_support
    return normalized


def _campaign_option_has_modeled_overlay_content(option: dict[str, Any]) -> bool:
    modeled_fields = (
        "ability",
        "additional_spells",
        "armor_proficiencies",
        "expertise",
        "feats",
        "language_proficiencies",
        "languages",
        "modeled_effects",
        "optionalfeature_progression",
        "proficiencies",
        "resource",
        "saving_throw_proficiencies",
        "size",
        "skill_proficiencies",
        "skill_tool_language_proficiencies",
        "spell_manager",
        "spell_support",
        "speed",
        "spells",
        "stat_adjustments",
        "tool_proficiencies",
        "weapon_proficiencies",
    )
    return any(_campaign_overlay_value_has_content(option.get(field_name)) for field_name in modeled_fields)


def _campaign_overlay_value_has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return any(_campaign_overlay_value_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_campaign_overlay_value_has_content(item) for item in value)
    return bool(value)


def _normalize_modeled_effects(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace("\r", "").replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    values: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if isinstance(raw_item, (dict, list, tuple, set)):
            continue
        clean_item = str(raw_item or "").strip()
        normalized_item = clean_item.casefold()
        if not clean_item or normalized_item in seen:
            continue
        seen.add(normalized_item)
        values.append(clean_item)
    return values


def _normalize_spell_grants(value: Any) -> list[dict[str, Any]]:
    raw_items = list(value or []) if isinstance(value, list) else []
    grants: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            clean_value = str(raw_item or "").strip()
            if clean_value:
                grants.append(
                    {
                        "value": clean_value,
                        "mark": "Granted",
                        "always_prepared": False,
                        "ritual": False,
                    }
                )
            continue
        if not isinstance(raw_item, dict):
            continue
        clean_value = str(
            raw_item.get("value")
            or raw_item.get("spell")
            or raw_item.get("title")
            or raw_item.get("slug")
            or ""
        ).strip()
        if not clean_value:
            continue
        grants.append(
            {
                "value": clean_value,
                "mark": str(raw_item.get("mark") or "").strip(),
                "always_prepared": bool(raw_item.get("always_prepared") or raw_item.get("prepared")),
                "ritual": bool(raw_item.get("ritual") or raw_item.get("is_ritual")),
            }
        )
    return grants


def _normalize_resource_grant(value: Any) -> dict[str, Any] | None:
    resource = dict(value or {}) if isinstance(value, dict) else {}
    if not resource:
        return None
    max_value = _normalize_positive_integer(resource.get("max"), default=0)
    scaling = _normalize_resource_scaling(resource.get("scaling"))
    if max_value <= 0 and scaling is None:
        return None
    reset_on = str(resource.get("reset_on") or "manual").strip().lower()
    if reset_on not in VALID_CAMPAIGN_RESOURCE_RESET_TYPES:
        reset_on = "manual"
    normalized = {
        "label": str(resource.get("label") or "").strip(),
        "reset_on": reset_on,
    }
    if max_value > 0:
        normalized["max"] = max_value
    if scaling is not None:
        normalized["scaling"] = scaling
    return normalized


def _normalize_resource_scaling(value: Any) -> dict[str, Any] | None:
    scaling = dict(value or {}) if isinstance(value, dict) else {}
    if not scaling:
        return None
    mode = str(scaling.get("mode") or "").strip().lower()
    if mode not in VALID_CAMPAIGN_RESOURCE_SCALING_MODES:
        return None
    normalized: dict[str, Any] = {"mode": mode}
    minimum = _normalize_nonnegative_integer(scaling.get("minimum"), default=0)
    maximum = _normalize_nonnegative_integer(scaling.get("maximum"), default=0)
    if minimum > 0:
        normalized["minimum"] = minimum
    if maximum > 0:
        normalized["maximum"] = maximum
    round_mode = str(scaling.get("round") or "").strip().lower()
    if round_mode in VALID_CAMPAIGN_RESOURCE_SCALING_ROUNDS:
        normalized["round"] = round_mode
    if mode == "thresholds":
        thresholds = _normalize_resource_scaling_thresholds(scaling.get("thresholds") or scaling.get("levels"))
        if not thresholds:
            return None
        normalized["thresholds"] = thresholds
    return normalized


def _normalize_resource_scaling_thresholds(value: Any) -> list[dict[str, int]]:
    thresholds: list[dict[str, int]] = []
    for raw_item in list(value or []):
        item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
        level = _normalize_positive_integer(item.get("level"), default=0)
        scaled_value = _normalize_positive_integer(item.get("value"), default=0)
        if level <= 0 or scaled_value <= 0:
            continue
        thresholds.append({"level": level, "value": scaled_value})
    return sorted(thresholds, key=lambda item: (item["level"], item["value"]))


def _normalize_positive_integer(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return int(default)
    if normalized <= 0:
        return int(default)
    return normalized


def _normalize_nonnegative_integer(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return int(default)
    if normalized < 0:
        return int(default)
    return normalized


def _normalize_size_value(value: Any) -> list[str]:
    if isinstance(value, str):
        clean_value = str(value or "").strip()
        return [clean_value] if clean_value else []
    if isinstance(value, list):
        values: list[str] = []
        for raw_item in value:
            clean_item = str(raw_item or "").strip()
            if clean_item:
                values.append(clean_item)
        return values
    return []


def _normalize_speed_value(value: Any) -> int | str | None:
    if isinstance(value, (int, float)):
        return int(value)
    clean_value = str(value or "").strip()
    return clean_value or None


def _contains_structured_builder_metadata(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, dict) for item in value)


def _normalize_rule_key(value: Any) -> str:
    clean_value = str(value or "").strip().lower()
    if not clean_value:
        return ""
    clean_value = clean_value.replace("_", "-")
    clean_value = re.sub(r"\s+", "-", clean_value)
    clean_value = re.sub(r"[^a-z0-9-]+", "-", clean_value)
    clean_value = re.sub(r"-{2,}", "-", clean_value)
    return clean_value.strip("-")
