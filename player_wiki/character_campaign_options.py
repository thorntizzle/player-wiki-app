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
VALID_CAMPAIGN_MECHANIC_EFFECT_KINDS = {
    "resource_template",
    "stat_adjustment",
    "ability_minimum",
    "spell_grant",
    "spell_manager",
    "attack_reminder",
    "defensive_rule",
    "attack_bonus",
    "damage_bonus",
    "ac_bonus",
    "visibility_gate",
    "state_gate",
    "rule_reference",
}
CAMPAIGN_MECHANIC_EFFECT_KIND_ALIASES = {
    "ability_floor": "ability_minimum",
    "ability_minimums": "ability_minimum",
    "ac": "ac_bonus",
    "armor_class_bonus": "ac_bonus",
    "attack_reminder_rule": "attack_reminder",
    "damage": "damage_bonus",
    "defense": "defensive_rule",
    "defensive": "defensive_rule",
    "resource": "resource_template",
    "resource_bonus": "resource_template",
    "spell": "spell_grant",
    "spell_support": "spell_grant",
    "stat": "stat_adjustment",
    "state": "state_gate",
    "visibility": "visibility_gate",
}
CAMPAIGN_MECHANIC_EFFECT_LEGACY_KEY_FIELDS = (
    "legacy_key",
    "legacyKey",
    "modeled_effect",
    "modeledEffect",
    "effect_key",
    "effectKey",
)
CAMPAIGN_BASE_RULE_REUSE_HOOKS = {
    "character_option": {
        "key": "character_option",
        "label": "Character Option",
        "description": (
            "Reuses the existing page-backed character option contract for structured grants, stat adjustments, "
            "resources, and other supported character-facing payloads."
        ),
    },
    "character_progression": {
        "key": "character_progression",
        "label": "Character Progression",
        "description": (
            "Reuses the existing class/subclass progression overlay lane so the modifier already rides the Systems "
            "and native level-up read path."
        ),
    },
    "spell_support": {
        "key": "spell_support",
        "label": "Spell Support",
        "description": (
            "Reuses the existing spell-support payload for granted, replaced, or otherwise structured spell choices."
        ),
    },
    "spell_manager": {
        "key": "spell_manager",
        "label": "Spell Manager",
        "description": (
            "Reuses the existing spell-manager payload for managed spell sources such as ritual books and similar "
            "tracked spell lists."
        ),
    },
    "modeled_effects": {
        "key": "modeled_effects",
        "label": "Modeled Effects",
        "description": (
            "Reuses the existing modeled-effects keys for downstream derived behavior such as attack, save, speed, "
            "or passive adjustments."
        ),
    },
    "mechanic_effects": {
        "key": "mechanic_effects",
        "label": "Mechanic Effects",
        "description": (
            "Reuses structured mechanic-effect rows while preserving legacy modeled-effect keys where current "
            "downstream builders still need them."
        ),
    },
}
CAMPAIGN_BASE_RULE_MISSING_METADATA = (
    {
        "key": "change_operation",
        "label": "Change Operation",
        "description": (
            "The overlay does not yet say whether it adds to, replaces, removes, or otherwise overrides the linked "
            "baseline rule."
        ),
    },
    {
        "key": "affected_rule_facet",
        "label": "Affected Rule Facet",
        "description": (
            "The overlay does not yet identify which precise baseline subsection, field, or derived behavior it "
            "changes."
        ),
    },
    {
        "key": "baseline_carry_forward",
        "label": "Baseline Carry-Forward",
        "description": (
            "The overlay does not yet say whether unmodified parts of the baseline rule still apply as written."
        ),
    },
)


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


def build_campaign_base_rule_modification_summary(
    option: dict[str, Any] | None,
    *,
    extra_hooks: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    candidate_option = dict(option or {}) if isinstance(option, dict) else {}
    if not normalize_campaign_base_rule_refs(candidate_option.get("base_rule_refs")):
        return None
    hook_keys = _campaign_base_rule_reuse_hook_keys(candidate_option, extra_hooks=extra_hooks)
    return {
        "reused_hooks": [deepcopy(CAMPAIGN_BASE_RULE_REUSE_HOOKS[key]) for key in hook_keys],
        "missing_metadata": [deepcopy(item) for item in CAMPAIGN_BASE_RULE_MISSING_METADATA],
    }


def extend_campaign_base_rule_modification_summary(
    summary: Any,
    *hook_keys: str,
) -> dict[str, Any] | None:
    normalized_summary = dict(summary or {}) if isinstance(summary, dict) else {}
    if not normalized_summary:
        return None
    existing_hook_keys: list[str] = []
    for raw_item in list(normalized_summary.get("reused_hooks") or []):
        item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
        hook_key = str(item.get("key") or "").strip().lower().replace("-", "_")
        if hook_key in CAMPAIGN_BASE_RULE_REUSE_HOOKS:
            existing_hook_keys.append(hook_key)
    merged_hook_keys = _merge_campaign_base_rule_reuse_hook_keys(existing_hook_keys, extra_hooks=hook_keys)
    normalized_summary["reused_hooks"] = [deepcopy(CAMPAIGN_BASE_RULE_REUSE_HOOKS[key]) for key in merged_hook_keys]
    normalized_summary["missing_metadata"] = [deepcopy(item) for item in CAMPAIGN_BASE_RULE_MISSING_METADATA]
    return normalized_summary


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
        raw_modeled_effects = _normalize_modeled_effects(
            raw_option.get("modeled_effects", raw_option.get("modeledEffects"))
        )
        mechanic_effects = normalize_campaign_mechanic_effects(
            raw_option.get("mechanic_effects", raw_option.get("mechanicEffects")),
            legacy_modeled_effects=raw_modeled_effects,
        )
        resource_mechanic_effect = _mechanic_effect_from_resource_grant(resource)
        if resource_mechanic_effect:
            mechanic_effects = _dedupe_mechanic_effect_rows([*mechanic_effects, resource_mechanic_effect])
        modeled_effects = _dedupe_string_values(
            [
                *raw_modeled_effects,
                *collect_mechanic_effect_legacy_keys(mechanic_effects),
            ]
        )
        if modeled_effects:
            normalized["modeled_effects"] = modeled_effects
        if mechanic_effects:
            normalized["mechanic_effects"] = mechanic_effects
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
    base_rule_modification_summary = build_campaign_base_rule_modification_summary(normalized)
    if base_rule_modification_summary:
        normalized["base_rule_modification_summary"] = base_rule_modification_summary
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
        "mechanic_effects",
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


def _campaign_base_rule_reuse_hook_keys(
    option: dict[str, Any],
    *,
    extra_hooks: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    hook_keys = ["character_option"]
    if option.get("spell_support") is not None:
        hook_keys.append("spell_support")
    if option.get("spell_manager") is not None:
        hook_keys.append("spell_manager")
    if _campaign_overlay_value_has_content(option.get("modeled_effects")):
        hook_keys.append("modeled_effects")
    if _campaign_overlay_value_has_content(option.get("mechanic_effects")) and _has_explicit_mechanic_effect_rows(
        option.get("mechanic_effects")
    ):
        hook_keys.append("mechanic_effects")
    return _merge_campaign_base_rule_reuse_hook_keys(hook_keys, extra_hooks=extra_hooks)


def _merge_campaign_base_rule_reuse_hook_keys(
    hook_keys: list[str] | tuple[str, ...],
    *,
    extra_hooks: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    merged_keys: list[str] = []
    seen_keys: set[str] = set()
    for raw_key in [*list(hook_keys or []), *list(extra_hooks or [])]:
        hook_key = str(raw_key or "").strip().lower().replace("-", "_")
        if hook_key not in CAMPAIGN_BASE_RULE_REUSE_HOOKS or hook_key in seen_keys:
            continue
        seen_keys.add(hook_key)
        merged_keys.append(hook_key)
    return merged_keys


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


def normalize_campaign_mechanic_effects(
    value: Any,
    *,
    legacy_modeled_effects: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for legacy_key in _normalize_modeled_effects(list(legacy_modeled_effects or [])):
        row = _mechanic_effect_from_legacy_key(legacy_key, source="modeled_effects")
        if row:
            rows.append(row)

    if isinstance(value, dict):
        raw_items = [value]
    elif isinstance(value, str):
        raw_items = value.replace("\r", "").replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    for raw_item in raw_items:
        if isinstance(raw_item, str):
            row = _mechanic_effect_from_legacy_key(raw_item, source="mechanic_effects")
        else:
            row = _normalize_mechanic_effect_row(raw_item)
        if row:
            rows.append(row)
    return _dedupe_mechanic_effect_rows(rows)


def collect_mechanic_effect_legacy_keys(value: Any) -> list[str]:
    raw_rows = normalize_campaign_mechanic_effects(value)
    legacy_keys: list[str] = []
    for raw_row in raw_rows:
        row = dict(raw_row or {}) if isinstance(raw_row, dict) else {}
        legacy_key = str(row.get("legacy_key") or "").strip()
        if not legacy_key:
            continue
        legacy_keys.append(legacy_key)
    return _dedupe_string_values(legacy_keys)


def _normalize_mechanic_effect_row(value: Any) -> dict[str, Any] | None:
    item = deepcopy(value) if isinstance(value, dict) else {}
    if not item:
        return None
    kind = _normalize_mechanic_effect_kind(
        item.get("kind")
        or item.get("effect_kind")
        or item.get("effectKind")
        or item.get("type")
    )
    legacy_key = _mechanic_effect_legacy_key(item, kind=kind)
    if not kind:
        kind = _infer_mechanic_effect_kind_from_legacy_key(legacy_key)
    if not kind:
        kind = "rule_reference"

    normalized: dict[str, Any] = {"kind": kind}
    for raw_key, raw_value in item.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        if key in {
            "kind",
            "effect_kind",
            "effectKind",
            "type",
            "legacyKey",
            "modeledEffect",
            "effectKey",
        }:
            continue
        if key in {"legacy_key", "modeled_effect", "effect_key"}:
            continue
        normalized[key] = deepcopy(raw_value)
    if legacy_key:
        normalized["key"] = str(normalized.get("key") or legacy_key).strip()
        normalized["legacy_key"] = legacy_key
    normalized["source"] = str(normalized.get("source") or "mechanic_effects").strip() or "mechanic_effects"
    return normalized if _campaign_overlay_value_has_content(normalized) else None


def _mechanic_effect_from_legacy_key(value: Any, *, source: str) -> dict[str, Any] | None:
    legacy_key = str(value or "").strip()
    if not legacy_key:
        return None
    kind = _infer_mechanic_effect_kind_from_legacy_key(legacy_key) or "rule_reference"
    return {
        "kind": kind,
        "key": legacy_key,
        "legacy_key": legacy_key,
        "source": source,
    }


def _mechanic_effect_from_resource_grant(resource: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized_resource = deepcopy(resource) if isinstance(resource, dict) else {}
    if not _campaign_overlay_value_has_content(normalized_resource):
        return None
    return {
        "kind": "resource_template",
        "resource": normalized_resource,
        "source": "character_option.resource",
    }


def _normalize_mechanic_effect_kind(value: Any) -> str:
    clean_value = str(value or "").strip().lower()
    if not clean_value:
        return ""
    clean_value = re.sub(r"[\s-]+", "_", clean_value)
    clean_value = re.sub(r"[^a-z0-9_]+", "_", clean_value).strip("_")
    clean_value = CAMPAIGN_MECHANIC_EFFECT_KIND_ALIASES.get(clean_value, clean_value)
    return clean_value if clean_value in VALID_CAMPAIGN_MECHANIC_EFFECT_KINDS else ""


def _mechanic_effect_legacy_key(item: dict[str, Any], *, kind: str) -> str:
    for key in CAMPAIGN_MECHANIC_EFFECT_LEGACY_KEY_FIELDS:
        legacy_key = str(item.get(key) or "").strip()
        if legacy_key:
            return legacy_key
    key_value = str(item.get("key") or "").strip()
    if key_value and _mechanic_effect_key_can_be_legacy(key_value, kind=kind):
        return key_value
    return ""


def _mechanic_effect_key_can_be_legacy(value: str, *, kind: str) -> bool:
    inferred_kind = _infer_mechanic_effect_kind_from_legacy_key(value)
    if inferred_kind and inferred_kind != "rule_reference":
        return True
    return kind in {
        "stat_adjustment",
        "attack_bonus",
        "damage_bonus",
        "ac_bonus",
        "attack_reminder",
        "defensive_rule",
        "visibility_gate",
        "state_gate",
    }


def _infer_mechanic_effect_kind_from_legacy_key(value: Any) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    normalized = clean_value.casefold().replace("_", "-")
    if normalized.startswith(("resource-template", "resource-template:", "resource:")):
        return "resource_template"
    if normalized.startswith(("spell-manager", "spell-manager:")):
        return "spell_manager"
    if normalized.startswith(("spell-grant", "spell-grant:", "spell-support", "spell-support:")):
        return "spell_grant"
    if normalized.startswith(("ability-minimum", "ability-minimum:", "ability-floor", "ability-floor:")):
        return "ability_minimum"
    if normalized.startswith(("attack-bonus", "attack-bonus:")):
        return "attack_bonus"
    if normalized.startswith(("damage-bonus", "damage-bonus:")):
        return "damage_bonus"
    if normalized.startswith(("ac-bonus", "ac-bonus:", "armor-class-bonus", "armor-class-bonus:")):
        return "ac_bonus"
    if normalized.startswith(("visibility-gate", "visibility-gate:")):
        return "visibility_gate"
    if normalized.startswith(("state-gate", "state-gate:")):
        return "state_gate"
    if normalized.startswith(
        (
            "save-bonus:",
            "initiative-bonus",
            "speed-bonus",
            "passive-bonus:",
            "carrying-capacity-multiplier:",
            "half-proficiency:",
        )
    ):
        return "stat_adjustment"
    if normalized.startswith(("armor-dex-cap-bonus:", "defensive-rule", "defensive-rule:")):
        return "defensive_rule"
    if (
        normalized.startswith(("attack-reminder", "attack-reminder:", "effect:attack-mode:"))
        or normalized
        in {
            "charger-phb",
            "charger-xphb",
            "grappler-phb",
            "grappler-xphb",
            "mounted-combatant-phb",
            "mounted-combatant-xphb",
            "squire of solamnia",
            "tavern-brawler",
        }
    ):
        return "attack_reminder"
    return "rule_reference"


def _dedupe_mechanic_effect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    index_by_marker: dict[tuple[str, str], int] = {}
    for row in rows:
        marker = _mechanic_effect_dedupe_marker(row)
        existing_index = index_by_marker.get(marker)
        if existing_index is not None:
            existing_row = deduped[existing_index]
            if (
                str(existing_row.get("source") or "").strip() == "modeled_effects"
                and str(row.get("source") or "").strip() != "modeled_effects"
            ):
                deduped[existing_index] = row
            continue
        index_by_marker[marker] = len(deduped)
        deduped.append(row)
    return deduped


def _mechanic_effect_dedupe_marker(row: dict[str, Any]) -> tuple[str, str]:
    legacy_key = str(row.get("legacy_key") or "").strip().casefold()
    if legacy_key:
        return ("legacy", legacy_key)
    kind = str(row.get("kind") or "").strip()
    if kind == "resource_template":
        resource = dict(row.get("resource") or {}) if isinstance(row.get("resource"), dict) else {}
        label = str(resource.get("label") or row.get("label") or "").strip().casefold()
        reset_on = str(resource.get("reset_on") or row.get("reset_on") or "").strip().casefold()
        if label:
            return ("resource_template", repr((label, reset_on, resource.get("max"), resource.get("scaling"))))
    return (
        "row",
        repr(sorted((str(key), repr(value)) for key, value in row.items())),
    )


def _dedupe_string_values(values: list[str] | tuple[str, ...]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = str(value or "").strip()
        normalized_value = clean_value.casefold()
        if not clean_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        deduped.append(clean_value)
    return deduped


def _has_explicit_mechanic_effect_rows(value: Any) -> bool:
    raw_rows = list(value or []) if isinstance(value, list) else []
    for raw_row in raw_rows:
        row = dict(raw_row or {}) if isinstance(raw_row, dict) else {}
        if str(row.get("source") or "").strip() != "modeled_effects":
            return True
    return False


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
