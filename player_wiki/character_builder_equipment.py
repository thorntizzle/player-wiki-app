from __future__ import annotations

from copy import deepcopy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .campaign_item_mechanics import (
    campaign_item_character_metadata,
    is_campaign_item_mechanics_metadata,
)
from .character_artificer_infusions import (
    ENHANCED_DEFENSE_INFUSION_KEY,
    active_infusion_armor_class_bonus,
    item_has_active_infusion,
)
from .character_builder_constants import *  # noqa: F403
from .character_builder_foundation import (
    _extract_campaign_page_ref,
    _systems_ref_slug,
)
from .character_builder_spells import _merge_name_candidates
from .character_campaign_options import (
    collect_mechanic_effect_legacy_keys,
    normalize_campaign_mechanic_effects,
)
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_systems_ref_slug",
    "_extract_character_effect_keys",
    "_campaign_option_mechanic_effect_rows",
    "_feature_mechanic_effect_rows",
    "_character_mechanic_effect_rows",
    "_mechanic_effect_numeric_value",
    "_mechanic_effect_targets_weapon_attacks",
    "_structured_weapon_attack_bonus",
    "_structured_weapon_damage_bonus",
    "_structured_attack_reminder_rules_from_features",
    "_structured_defensive_rules_from_features",
    "_split_effect_key",
    "_effect_weapon_attack_bonus",
    "_effect_weapon_damage_bonus",
    "_attack_mode_component_sort_key",
    "_normalize_attack_mode_key",
    "_attack_mode_components",
    "_attack_mode_component_label",
    "_attack_variant_label_from_mode_key",
    "_attack_name_suffix",
    "_extract_attack_name_suffix_label",
    "_legacy_attack_mode_component",
    "_attack_mode_key_from_variant_label",
    "_normalize_attack_variant_label",
    "_effect_attack_mode_component",
    "_normalize_attack_mode_extra_damage",
    "_attack_mode_note_text",
    "_effect_attack_mode_descriptors",
    "_combine_attack_extra_damage",
    "_append_attack_note_text",
    "_attack_mode_descriptor_applies_to_context",
    "_infer_attack_mode_key_from_payload",
    "_extract_feature_slugs",
    "_collect_attack_support_flags",
    "_collect_defensive_support_flags",
    "_collect_attack_reminder_support_flags",
    "_derive_attack_reminder_state_from_character_inputs",
    "_load_phb_weapon_profiles",
    "_load_phb_armor_profiles",
    "_resolve_item_entry",
    "_normalize_weapon_wield_mode_value",
    "weapon_wield_mode_label",
    "_weapon_wield_mode_options_for_profile",
    "explicit_weapon_wield_mode",
    "resolve_weapon_wield_mode",
    "resolve_item_equipped_state",
    "describe_equipment_state_support",
    "_build_level_one_attacks",
    "_effect_keys_for_feature",
    "_qualifies_for_crossbow_expert",
    "_qualifies_for_gunner",
    "_qualifies_for_charger",
    "_qualifies_for_mounted_combatant",
    "_qualifies_for_crossbow_expert_bonus_attack",
    "_resolve_crossbow_expert_bonus_attack_context",
    "_qualifies_for_great_weapon_master",
    "_qualifies_for_polearm_master",
    "_qualifies_for_savage_attacker",
    "_qualifies_for_sharpshooter",
    "_base_attack_feat_notes",
    "_build_weapon_attack_contexts",
    "_build_weapon_attack_payload",
    "_append_weapon_attack_payloads",
    "_resolve_off_hand_attack_context",
    "_resolve_weapon_profile",
    "_resolve_campaign_item_page_support",
    "_resolve_item_support_metadata",
    "_item_effect_metadata",
    "_attack_reminder_rule_save_dc",
    "_format_dynamic_reminder_text",
    "_item_effect_is_active",
    "_active_item_effect_entries",
    "_active_weapon_profile_bonus",
    "_parse_optional_int_value",
    "_build_armor_profile",
    "_armor_profile_from_entry",
    "_split_magic_item_name",
    "_metadata_requires_attunement",
    "_metadata_is_magic_item",
    "_resolve_weapon_bonus_from_metadata",
    "_resolve_armor_profile",
    "_equipped_armor_profiles",
    "_resolved_armor_profiles",
    "_character_has_named_feature",
    "_derive_defensive_state_from_character_inputs",
    "_weapon_attack_ability_key",
    "_is_proficient_with_weapon",
    "_weapon_proficiency_name_candidates",
    "_singularize_lookup_variants",
    "_weapon_uses_firearm_proficiency",
    "_has_fighting_style",
    "_qualifies_for_dueling",
    "_supports_thrown_attack_variant",
    "_supports_versatile_two_handed_attack",
    "_is_shield_item",
    "_weapon_attack_category",
    "_format_weapon_damage",
    "_build_unarmed_attack_payload",
    "_build_special_attack_payload",
    "_build_weapon_attack_notes",
    "_extract_campaign_page_ref",
    "_normalize_attack_payloads",
    "_normalize_attack_equipment_refs",
    "_attack_matches_equipment_catalog",
    "_attack_override_match_keys",
    "_merge_recalculated_attack_overrides",
    "_normalize_equipment_payloads",
    "_recover_equipment_link_payloads",
    "_normalize_page_ref_payload",
    "_normalize_explicit_link_identity",
    "_normalize_merge_text",
    "_normalize_equipment_quantity",
    "_humanize_item_reference",
    "_merge_currency_seed",
    "_format_currency_seed",
    "_systems_ref_from_entry",
    "_ability_modifier",
    "_humanize_words",
    "_dedupe_preserve_order",
]


def _extract_character_effect_keys(features: list[dict[str, Any]] | None) -> list[str]:
    results: list[str] = []
    for feature in list(features or []):
        results.extend(_effect_keys_for_feature(feature))
    return _dedupe_preserve_order(results)


def _campaign_option_mechanic_effect_rows(
    option: dict[str, Any] | None,
    *,
    kind: str = "",
    include_legacy: bool = False,
) -> list[dict[str, Any]]:
    option_payload = dict(option or {}) if isinstance(option, dict) else {}
    normalized_kind = str(kind or "").strip()
    rows: list[dict[str, Any]] = []
    for raw_row in normalize_campaign_mechanic_effects(option_payload.get("mechanic_effects")):
        row = dict(raw_row or {}) if isinstance(raw_row, dict) else {}
        if not row:
            continue
        if normalized_kind and str(row.get("kind") or "").strip() != normalized_kind:
            continue
        if not include_legacy and str(row.get("legacy_key") or "").strip():
            continue
        rows.append(row)
    return rows


def _feature_mechanic_effect_rows(
    feature: dict[str, Any],
    *,
    kind: str = "",
    include_legacy: bool = False,
) -> list[dict[str, Any]]:
    return _campaign_option_mechanic_effect_rows(
        dict(feature.get("campaign_option") or {}),
        kind=kind,
        include_legacy=include_legacy,
    )


def _character_mechanic_effect_rows(
    features: list[dict[str, Any]] | None,
    *,
    kind: str = "",
    include_legacy: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in list(features or []):
        rows.extend(
            _feature_mechanic_effect_rows(
                dict(feature or {}),
                kind=kind,
                include_legacy=include_legacy,
            )
        )
    return rows


def _mechanic_effect_numeric_value(row: dict[str, Any], *keys: str) -> int:
    for key in keys or ("bonus", "amount", "value"):
        raw_value = row.get(key)
        if raw_value is None or raw_value == "":
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return 0


def _mechanic_effect_targets_weapon_attacks(row: dict[str, Any]) -> bool:
    raw_target = row.get("target") or row.get("applies_to") or row.get("appliesTo") or row.get("scope")
    if isinstance(raw_target, dict):
        raw_target = raw_target.get("kind") or raw_target.get("target") or raw_target.get("label")
    clean_target = normalize_lookup(str(raw_target or "").strip())
    if not clean_target:
        return True
    return clean_target in {
        "all",
        "attack",
        "attacks",
        "weapon",
        "weapons",
        "weaponattack",
        "weaponattacks",
    }


def _structured_weapon_attack_bonus(features: list[dict[str, Any]] | None) -> int:
    bonus = 0
    for row in _character_mechanic_effect_rows(features, kind="attack_bonus"):
        if not _mechanic_effect_targets_weapon_attacks(row):
            continue
        bonus += _mechanic_effect_numeric_value(row, "bonus", "attack_bonus", "attackBonus", "amount", "value")
    return bonus


def _structured_weapon_damage_bonus(features: list[dict[str, Any]] | None) -> int:
    bonus = 0
    for row in _character_mechanic_effect_rows(features, kind="damage_bonus"):
        if not _mechanic_effect_targets_weapon_attacks(row):
            continue
        bonus += _mechanic_effect_numeric_value(row, "bonus", "damage_bonus", "damageBonus", "amount", "value")
    return bonus


def _structured_attack_reminder_rules_from_features(
    features: list[dict[str, Any]] | None,
    *,
    ability_scores: dict[str, int] | None = None,
    proficiency_bonus: int = 0,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in _character_mechanic_effect_rows(features, kind="attack_reminder"):
        rule = dict(row.get("rule") or row.get("attack_reminder") or row.get("attackReminder") or {})
        for key in ("id", "title", "condition", "attack_scope", "effects", "save_dc_ability_key"):
            if key in row and key not in rule:
                rule[key] = deepcopy(row.get(key))
        effects: list[dict[str, Any]] = []
        save_dc = _attack_reminder_rule_save_dc(
            rule,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
        )
        for effect_payload in list(rule.get("effects") or []):
            if not isinstance(effect_payload, dict):
                continue
            effect = dict(effect_payload)
            effect["summary"] = _format_dynamic_reminder_text(
                effect.get("summary"),
                save_dc=save_dc,
            )
            if not effect["summary"]:
                continue
            effects.append(effect)
        if not effects:
            continue
        rules.append(
            {
                "id": str(rule.get("id") or row.get("key") or f"feature:{slugify(str(rule.get('title') or 'reminder'))}").strip(),
                "title": str(rule.get("title") or row.get("label") or "Combat reminder").strip() or "Combat reminder",
                "condition": _format_dynamic_reminder_text(
                    rule.get("condition"),
                    save_dc=save_dc,
                ),
                "attack_scope": dict(rule.get("attack_scope") or {}),
                "effects": effects,
            }
        )
    return rules


def _structured_defensive_rules_from_features(
    features: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in _character_mechanic_effect_rows(features, kind="defensive_rule"):
        rule = dict(row.get("rule") or row.get("defensive_rule") or row.get("defensiveRule") or {})
        for key in ("id", "title", "active", "condition", "inactive_reason", "effects"):
            if key in row and key not in rule:
                rule[key] = deepcopy(row.get(key))
        effects = [
            dict(effect or {})
            for effect in list(rule.get("effects") or [])
            if isinstance(effect, dict)
        ]
        if not effects:
            continue
        active_value = rule.get("active")
        rules.append(
            {
                "id": str(rule.get("id") or row.get("key") or f"feature:{slugify(str(rule.get('title') or 'rule'))}").strip(),
                "title": str(rule.get("title") or row.get("label") or "Defensive rule").strip() or "Defensive rule",
                "active": active_value if isinstance(active_value, bool) else True,
                "condition": str(rule.get("condition") or "").strip(),
                "inactive_reason": str(rule.get("inactive_reason") or rule.get("inactiveReason") or "").strip(),
                "effects": effects,
            }
        )
    return rules


def _split_effect_key(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").strip().split(":") if part.strip()]


def _effect_weapon_attack_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("weapon-attack-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _effect_weapon_damage_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("weapon-damage-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _attack_mode_component_sort_key(component: str) -> tuple[int, str]:
    clean_component = str(component or "").strip().casefold()
    if clean_component.startswith(f"{ATTACK_MODE_EFFECT_PREFIX}:"):
        return (55, clean_component)
    return (int(ATTACK_MODE_COMPONENT_PRIORITY.get(clean_component, 999)), clean_component)


def _normalize_attack_mode_key(value: Any) -> str:
    if isinstance(value, str):
        raw_components = value.split("|")
    elif isinstance(value, (list, tuple, set)):
        raw_components = list(value)
    else:
        return ""
    components: list[str] = []
    seen: set[str] = set()
    for raw_component in raw_components:
        clean_component = str(raw_component or "").strip().casefold()
        if not clean_component or clean_component in seen:
            continue
        seen.add(clean_component)
        components.append(clean_component)
    return "|".join(sorted(components, key=_attack_mode_component_sort_key))


def _attack_mode_components(mode_key: Any) -> list[str]:
    normalized_mode_key = _normalize_attack_mode_key(mode_key)
    if not normalized_mode_key:
        return []
    return [component for component in normalized_mode_key.split("|") if component]


def _attack_mode_component_label(component: Any) -> str:
    clean_component = str(component or "").strip().casefold()
    label = str(ATTACK_MODE_COMPONENT_LABELS.get(clean_component) or "").strip()
    if label:
        return label
    prefix = f"{ATTACK_MODE_EFFECT_PREFIX}:"
    if clean_component.startswith(prefix):
        parts = clean_component.split(":")
        if len(parts) >= 4:
            return parts[3].replace("-", " ").strip()
    return ""


def _attack_variant_label_from_mode_key(mode_key: Any) -> str:
    labels: list[str] = []
    for component in _attack_mode_components(mode_key):
        label = _attack_mode_component_label(component)
        if not label:
            return ""
        labels.append(label)
    return ", ".join(labels)


def _attack_name_suffix(variant_label: str) -> str:
    clean_label = str(variant_label or "").strip()
    if not clean_label:
        return ""
    return f" ({clean_label})"


def _extract_attack_name_suffix_label(name: Any) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        return ""
    match = ATTACK_NAME_SUFFIX_PATTERN.search(clean_name)
    if match is None:
        return ""
    return str(match.group(1) or "").strip()


def _legacy_attack_mode_component(label: str, *, notes: str = "") -> str:
    normalized_label = normalize_lookup(label)
    if not normalized_label:
        return ""
    component_map = {
        normalize_lookup("thrown"): ATTACK_MODE_WEAPON_THROWN,
        normalize_lookup("two-handed"): ATTACK_MODE_WEAPON_TWO_HANDED,
        normalize_lookup("off-hand"): ATTACK_MODE_WEAPON_OFF_HAND,
        normalize_lookup("crossbow expert"): ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS,
        normalize_lookup("great weapon master"): ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER,
        normalize_lookup("polearm master"): ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS,
        normalize_lookup("sharpshooter"): ATTACK_MODE_FEAT_SHARPSHOOTER,
    }
    if normalized_label == normalize_lookup("charger"):
        normalized_notes = normalize_lookup(notes)
        if normalize_lookup("+1d8 damage") in normalized_notes or normalize_lookup("once per turn") in normalized_notes:
            return ATTACK_MODE_FEAT_CHARGER_XPHB
        return ATTACK_MODE_FEAT_CHARGER_PHB
    return str(component_map.get(normalized_label) or "")


def _attack_mode_key_from_variant_label(variant_label: Any, *, notes: Any = "") -> str:
    raw_label = str(variant_label or "").strip()
    if not raw_label:
        return ""
    components: list[str] = []
    for label in [part.strip() for part in raw_label.split(",") if part.strip()]:
        component = _legacy_attack_mode_component(label, notes=str(notes or ""))
        if not component:
            return ""
        components.append(component)
    return _normalize_attack_mode_key(components)


def _normalize_attack_variant_label(
    *,
    raw_variant_label: Any,
    mode_key: Any,
    attack_name: Any,
    notes: Any,
) -> str:
    clean_variant_label = str(raw_variant_label or "").strip()
    if clean_variant_label:
        inferred_mode_key = _attack_mode_key_from_variant_label(clean_variant_label, notes=notes)
        if inferred_mode_key:
            return _attack_variant_label_from_mode_key(inferred_mode_key)
        return clean_variant_label
    canonical_variant_label = _attack_variant_label_from_mode_key(mode_key)
    if canonical_variant_label:
        return canonical_variant_label
    inferred_suffix_label = _extract_attack_name_suffix_label(attack_name)
    inferred_mode_key = _attack_mode_key_from_variant_label(inferred_suffix_label, notes=notes)
    if inferred_mode_key:
        return _attack_variant_label_from_mode_key(inferred_mode_key)
    return ""


def _effect_attack_mode_component(*, target_kind: str, variant_label: str) -> str:
    clean_target_kind = normalize_lookup(target_kind)
    clean_variant_label = str(variant_label or "").strip()
    if clean_target_kind not in ATTACK_MODE_EFFECT_TARGETS or not clean_variant_label:
        return ""
    label_slug = slugify(clean_variant_label)
    if not label_slug:
        return ""
    return f"{ATTACK_MODE_EFFECT_PREFIX}:{clean_target_kind}:{label_slug}"


def _normalize_attack_mode_extra_damage(value: Any) -> str:
    clean_value = str(value or "").strip()
    if normalize_lookup(clean_value) in {"", "0", "none", "no", "false", "n-a", "na"}:
        return ""
    return clean_value


def _attack_mode_note_text(
    *,
    variant_label: str,
    attack_delta: int,
    damage_delta: int,
    extra_damage: str,
) -> str:
    clean_label = str(variant_label or "").strip()
    adjustments: list[str] = []
    if attack_delta:
        adjustments.append(f"{attack_delta:+d} attack")
    if damage_delta:
        adjustments.append(f"{damage_delta:+d} damage")
    if extra_damage:
        adjustments.append(f"+{extra_damage} damage")
    if not clean_label:
        return ""
    if not adjustments:
        return clean_label.title()
    return f"{clean_label.title()} ({', '.join(adjustments)})"


def _effect_attack_mode_descriptors(effect_keys: list[str]) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    seen_descriptors: set[tuple[str, int, int, str]] = set()
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 6 or normalize_lookup(parts[0]) != normalize_lookup("attack-mode"):
            continue
        target_kind = normalize_lookup(parts[1])
        variant_label = str(parts[2] or "").strip()
        if target_kind not in ATTACK_MODE_EFFECT_TARGETS or not variant_label:
            continue
        try:
            attack_delta = int(parts[3])
            damage_delta = int(parts[4])
        except ValueError:
            continue
        extra_damage = _normalize_attack_mode_extra_damage(parts[5])
        if attack_delta == 0 and damage_delta == 0 and not extra_damage:
            continue
        mode_component = _effect_attack_mode_component(target_kind=target_kind, variant_label=variant_label)
        descriptor_key = (mode_component, attack_delta, damage_delta, extra_damage)
        if not mode_component or descriptor_key in seen_descriptors:
            continue
        seen_descriptors.add(descriptor_key)
        descriptors.append(
            {
                "target_kind": target_kind,
                "variant_label": _attack_mode_component_label(mode_component),
                "attack_delta": attack_delta,
                "damage_delta": damage_delta,
                "extra_damage": extra_damage,
                "mode_component": mode_component,
                "note": _attack_mode_note_text(
                    variant_label=variant_label,
                    attack_delta=attack_delta,
                    damage_delta=damage_delta,
                    extra_damage=extra_damage,
                ),
            }
        )
    return descriptors


def _combine_attack_extra_damage(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        clean_value = _normalize_attack_mode_extra_damage(value)
        if clean_value:
            parts.append(clean_value)
    return "+".join(parts)


def _append_attack_note_text(base_notes: Any, extra_note: Any) -> str:
    base_text = str(base_notes or "").strip().rstrip(".")
    extra_text = str(extra_note or "").strip().rstrip(".")
    if not base_text:
        return f"{extra_text}." if extra_text else ""
    if not extra_text:
        return f"{base_text}."
    if normalize_lookup(extra_text) in normalize_lookup(base_text):
        return f"{base_text}."
    return f"{base_text}, {extra_text}."


def _attack_mode_descriptor_applies_to_context(
    descriptor: dict[str, Any],
    context: dict[str, Any],
    *,
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> bool:
    target_kind = normalize_lookup(str(descriptor.get("target_kind") or "").strip())
    if not target_kind:
        return False
    if target_kind == ATTACK_MODE_TARGET_ALL:
        return True
    profile = dict(profile_override or context.get("profile") or {})
    effective_category = normalize_lookup(category_override or _weapon_attack_category(profile))
    if target_kind == ATTACK_MODE_TARGET_MELEE:
        return effective_category == normalize_lookup("melee weapon")
    if target_kind == ATTACK_MODE_TARGET_RANGED:
        return effective_category == normalize_lookup("ranged weapon")
    if target_kind == ATTACK_MODE_TARGET_FIREARM:
        return _weapon_uses_firearm_proficiency(profile, attack_name=str(context.get("attack_name") or "").strip())
    return False


def _infer_attack_mode_key_from_payload(payload: dict[str, Any]) -> str:
    explicit_mode_key = _normalize_attack_mode_key(payload.get("mode_key"))
    if explicit_mode_key:
        return explicit_mode_key
    variant_label_mode_key = _attack_mode_key_from_variant_label(
        payload.get("variant_label"),
        notes=payload.get("notes"),
    )
    if variant_label_mode_key:
        return variant_label_mode_key
    return _attack_mode_key_from_variant_label(
        _extract_attack_name_suffix_label(payload.get("name")),
        notes=payload.get("notes"),
    )


def _extract_feature_slugs(features: list[dict[str, Any]] | None) -> set[str]:
    slugs: set[str] = set()
    for feature in list(features or []):
        systems_ref = dict(feature.get("systems_ref") or {})
        slug = normalize_lookup(str(systems_ref.get("slug") or "").strip())
        if slug:
            slugs.add(slug)
    return slugs


def _collect_attack_support_flags(features: list[dict[str, Any]] | None) -> dict[str, bool]:
    feature_slugs = _extract_feature_slugs(features)
    effect_keys = {
        normalize_lookup(str(value or "").strip())
        for value in _extract_character_effect_keys(features)
        if str(value or "").strip()
    }

    def has_slug(*raw_slugs: str) -> bool:
        return any(normalize_lookup(raw_slug) in feature_slugs for raw_slug in raw_slugs if str(raw_slug or "").strip())

    def has_effect(*raw_effects: str) -> bool:
        return any(normalize_lookup(raw_effect) in effect_keys for raw_effect in raw_effects if str(raw_effect or "").strip())

    return {
        "charger_phb": has_slug("phb-feat-charger") or normalize_lookup("charger-phb") in effect_keys,
        "charger_xphb": has_slug("xphb-feat-charger") or normalize_lookup("charger-xphb") in effect_keys,
        "crossbow_expert": has_slug("phb-feat-crossbow-expert") or has_effect("Crossbow Expert"),
        "dual_wielder": has_slug("phb-feat-dual-wielder") or has_effect("Dual Wielder"),
        "great_weapon_master": has_slug("phb-feat-great-weapon-master") or has_effect("Great Weapon Master"),
        "grappler_phb": has_slug("phb-feat-grappler") or normalize_lookup("grappler-phb") in effect_keys,
        "mounted_combatant_phb": has_slug("phb-feat-mounted-combatant") or normalize_lookup("mounted-combatant-phb") in effect_keys,
        "gunner": has_slug("tce-feat-gunner") or has_effect("Gunner"),
        "martial_adept": has_slug("phb-feat-martial-adept") or has_effect("Martial Adept"),
        "polearm_master": has_slug("phb-feat-polearm-master") or has_effect("Polearm Master"),
        "savage_attacker": has_slug("phb-feat-savage-attacker") or has_effect("Savage Attacker"),
        "sharpshooter": has_slug("phb-feat-sharpshooter") or has_effect("Sharpshooter"),
        "shield_master": has_slug("phb-feat-shield-master") or has_effect("Shield Master"),
        "tavern_brawler": has_slug("phb-feat-tavern-brawler", "xphb-feat-tavern-brawler") or has_effect("Tavern Brawler"),
    }


def _collect_defensive_support_flags(features: list[dict[str, Any]] | None) -> dict[str, bool]:
    feature_slugs = _extract_feature_slugs(features)
    effect_keys = {
        normalize_lookup(str(value or "").strip())
        for value in _extract_character_effect_keys(features)
        if str(value or "").strip()
    }

    def has_slug(*raw_slugs: str) -> bool:
        return any(normalize_lookup(raw_slug) in feature_slugs for raw_slug in raw_slugs if str(raw_slug or "").strip())

    def has_effect(*raw_effects: str) -> bool:
        return any(normalize_lookup(raw_effect) in effect_keys for raw_effect in raw_effects if str(raw_effect or "").strip())

    return {
        "heavy_armor_master": has_slug("phb-feat-heavy-armor-master") or has_effect("Heavy Armor Master"),
        "mage_slayer": has_slug("phb-feat-mage-slayer") or has_effect("Mage Slayer"),
        "medium_armor_master": has_slug("phb-feat-medium-armor-master") or has_effect("Medium Armor Master"),
        "shield_master": has_slug("phb-feat-shield-master") or has_effect("Shield Master"),
    }


def _collect_attack_reminder_support_flags(features: list[dict[str, Any]] | None) -> dict[str, bool]:
    feature_slugs = _extract_feature_slugs(features)
    effect_keys = {
        normalize_lookup(str(value or "").strip())
        for value in _extract_character_effect_keys(features)
        if str(value or "").strip()
    }

    def has_slug(*raw_slugs: str) -> bool:
        return any(normalize_lookup(raw_slug) in feature_slugs for raw_slug in raw_slugs if str(raw_slug or "").strip())

    def has_effect(*raw_effects: str) -> bool:
        return any(normalize_lookup(raw_effect) in effect_keys for raw_effect in raw_effects if str(raw_effect or "").strip())

    return {
        "crusher": has_slug("tce-feat-crusher") or has_effect("Crusher"),
        "mage_slayer": has_slug("phb-feat-mage-slayer") or has_effect("Mage Slayer"),
        "piercer": has_slug("tce-feat-piercer") or has_effect("Piercer"),
        "sentinel": has_slug("phb-feat-sentinel") or has_effect("Sentinel"),
        "slasher": has_slug("tce-feat-slasher") or has_effect("Slasher"),
    }


def _derive_attack_reminder_state_from_character_inputs(
    *,
    features: list[dict[str, Any]] | None,
    equipment_catalog: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    ability_scores: dict[str, int] | None = None,
    proficiency_bonus: int = 0,
) -> dict[str, Any]:
    support_flags = _collect_attack_reminder_support_flags(features)
    rules: list[dict[str, Any]] = []
    if support_flags.get("sentinel"):
        rules.append(
            {
                "id": "feat:phb-feat-sentinel",
                "title": "Sentinel",
                "condition": "Use these reminders when enemies leave your reach or attack nearby allies.",
                "attack_scope": {
                    "label": "Melee weapon attacks",
                    "categories": ["melee weapon"],
                },
                "effects": [
                    {
                        "kind": "opportunity_attack",
                        "label": "Opportunity attacks",
                        "summary": "Creatures within your reach provoke opportunity attacks from you even if they take the Disengage action.",
                    },
                    {
                        "kind": "speed_control",
                        "label": "On hit",
                        "summary": "When you hit a creature with an opportunity attack, its speed becomes 0 for the rest of the turn.",
                    },
                    {
                        "kind": "reaction",
                        "label": "Adjacent ally trigger",
                        "summary": "When a creature within 5 feet of you attacks a target other than you, you can use your reaction to make a melee weapon attack against that creature.",
                    },
                ],
            }
        )
    if support_flags.get("mage_slayer"):
        rules.append(
            {
                "id": "feat:phb-feat-mage-slayer",
                "title": "Mage Slayer",
                "condition": "Use these reminders when a creature within 5 feet of you casts a spell or is concentrating on one.",
                "attack_scope": {
                    "label": "Melee weapon attacks",
                    "categories": ["melee weapon"],
                },
                "effects": [
                    {
                        "kind": "reaction",
                        "label": "Spellcasting trigger",
                        "summary": "When a creature within 5 feet of you casts a spell, you can use your reaction to make a melee weapon attack against it.",
                    },
                    {
                        "kind": "concentration",
                        "label": "On hit",
                        "summary": "When you damage a creature that is concentrating on a spell, that creature has disadvantage on the saving throw it makes to maintain concentration.",
                    },
                ],
            }
        )
    if support_flags.get("crusher"):
        rules.append(
            {
                "id": "feat:tce-feat-crusher",
                "title": "Crusher",
                "condition": "Use these reminders only when a visible attack deals bludgeoning damage.",
                "attack_scope": {
                    "label": "Bludgeoning attacks",
                    "damage_types": ["Bludgeoning"],
                },
                "effects": [
                    {
                        "kind": "forced_movement",
                        "label": "Once per turn on hit",
                        "summary": "When you hit a creature with bludgeoning damage, you can move it 5 feet to an unoccupied space if it is no more than one size larger than you.",
                    },
                    {
                        "kind": "critical",
                        "label": "On critical hit",
                        "summary": "Attack rolls against that creature have advantage until the start of your next turn.",
                    },
                ],
            }
        )
    if support_flags.get("piercer"):
        rules.append(
            {
                "id": "feat:tce-feat-piercer",
                "title": "Piercer",
                "condition": "Use these reminders only when a visible attack deals piercing damage.",
                "attack_scope": {
                    "label": "Piercing attacks",
                    "damage_types": ["Piercing"],
                },
                "effects": [
                    {
                        "kind": "damage_reroll",
                        "label": "Once per turn on hit",
                        "summary": "You can reroll one of the attack's damage dice.",
                    },
                    {
                        "kind": "critical_damage",
                        "label": "On critical hit",
                        "summary": "Roll one additional damage die when determining the extra piercing damage the target takes.",
                    },
                ],
            }
        )
    if support_flags.get("slasher"):
        rules.append(
            {
                "id": "feat:tce-feat-slasher",
                "title": "Slasher",
                "condition": "Use these reminders only when a visible attack deals slashing damage.",
                "attack_scope": {
                    "label": "Slashing attacks",
                    "damage_types": ["Slashing"],
                },
                "effects": [
                    {
                        "kind": "speed_control",
                        "label": "Once per turn on hit",
                        "summary": "You can reduce the target's speed by 10 feet until the start of your next turn.",
                    },
                    {
                        "kind": "critical",
                        "label": "On critical hit",
                        "summary": "The target has disadvantage on all attack rolls until the start of your next turn.",
                    },
                ],
            }
        )
    for item_effect_entry in _active_item_effect_entries(
        equipment_catalog,
        item_catalog=item_catalog,
    ):
        for rule_payload in list(item_effect_entry.get("attack_reminder_rules") or []):
            rule = dict(rule_payload or {})
            save_dc = _attack_reminder_rule_save_dc(
                rule,
                ability_scores=ability_scores,
                proficiency_bonus=proficiency_bonus,
            )
            effects = []
            for effect_payload in list(rule.get("effects") or []):
                if not isinstance(effect_payload, dict):
                    continue
                effect = dict(effect_payload)
                effect["summary"] = _format_dynamic_reminder_text(
                    effect.get("summary"),
                    save_dc=save_dc,
                )
                if not effect["summary"]:
                    continue
                effects.append(effect)
            if not effects:
                continue
            rules.append(
                {
                    "id": str(rule.get("id") or f"item:{slugify(str(item_effect_entry.get('item_name') or 'reminder'))}").strip(),
                    "title": str(rule.get("title") or item_effect_entry.get("item_name") or "Combat reminder").strip()
                    or "Combat reminder",
                    "condition": _format_dynamic_reminder_text(
                        rule.get("condition"),
                        save_dc=save_dc,
                    ),
                    "attack_scope": dict(rule.get("attack_scope") or {}),
                    "effects": effects,
                }
            )
    rules.extend(
        _structured_attack_reminder_rules_from_features(
            features,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
        )
    )
    return {"rules": rules}


@lru_cache(maxsize=1)
def _load_phb_weapon_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_weapon_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for title, profile in payload.items():
        if not isinstance(profile, dict):
            continue
        normalized[normalize_lookup(title)] = {
            "title": str(title).strip(),
            "type": str(profile.get("type") or "").strip(),
            "weapon_category": str(profile.get("weapon_category") or "").strip(),
            "properties": [str(item).strip() for item in list(profile.get("properties") or []) if str(item).strip()],
            "damage": str(profile.get("damage") or "").strip(),
            "versatile_damage": str(profile.get("versatile_damage") or "").strip(),
            "damage_type": str(profile.get("damage_type") or "").strip(),
            "range": str(profile.get("range") or "").strip(),
        }
    return normalized


@lru_cache(maxsize=1)
def _load_phb_armor_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_armor_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for title, profile in payload.items():
        if not isinstance(profile, dict):
            continue
        dex_cap = profile.get("dex_cap")
        minimum_strength = profile.get("minimum_strength")
        normalized[normalize_lookup(title)] = {
            "title": str(title).strip(),
            "type": str(profile.get("type") or "").strip().upper(),
            "armor_category": str(profile.get("armor_category") or "").strip().lower(),
            "base_ac": int(profile.get("base_ac") or 0),
            "uses_dex": bool(profile.get("uses_dex")),
            "dex_cap": None if dex_cap in (None, "", False) else int(dex_cap),
            "is_shield": bool(profile.get("is_shield")),
            "bonus_ac": int(profile.get("bonus_ac") or 0),
            "minimum_strength": None if minimum_strength in (None, "", False) else int(minimum_strength),
            "stealth_disadvantage": bool(profile.get("stealth_disadvantage")),
        }
    return normalized


def _resolve_item_entry(
    item: Any,
    item_catalog: dict[str, Any] | None,
) -> SystemsEntryRecord | None:
    if not item_catalog:
        return None
    by_title = dict(item_catalog.get("by_title") or {})
    by_slug = dict(item_catalog.get("by_slug") or {})
    candidate_titles: list[str] = []
    if isinstance(item, dict):
        systems_ref = dict(item.get("systems_ref") or {})
        slug = str(systems_ref.get("slug") or "").strip()
        if slug:
            entry = by_slug.get(slug)
            if isinstance(entry, SystemsEntryRecord):
                return entry
        candidate_titles.extend(
            [
                str(systems_ref.get("title") or "").strip(),
                str(item.get("name") or "").strip(),
            ]
        )
    else:
        raw_reference = str(item or "").strip()
        if raw_reference:
            candidate_titles.extend(
                [
                    raw_reference.split("|", 1)[0].strip(),
                    _humanize_item_reference(raw_reference),
                ]
            )
    for title in candidate_titles:
        if not title:
            continue
        for candidate_key in _merge_name_candidates(title):
            entry = by_title.get(candidate_key)
            if isinstance(entry, SystemsEntryRecord):
                return entry
    return None


def _normalize_weapon_wield_mode_value(value: Any) -> str:
    normalized = normalize_lookup(str(value or "").replace("_", " ").replace("-", " "))
    mapping = {
        normalize_lookup("main hand"): WEAPON_WIELD_MODE_MAIN_HAND,
        normalize_lookup("off hand"): WEAPON_WIELD_MODE_OFF_HAND,
        normalize_lookup("two handed"): WEAPON_WIELD_MODE_TWO_HANDED,
    }
    return mapping.get(normalized, "")


def weapon_wield_mode_label(value: Any) -> str:
    return WEAPON_WIELD_MODE_LABELS.get(_normalize_weapon_wield_mode_value(value), "")


def _weapon_wield_mode_options_for_profile(
    profile: dict[str, Any] | None,
) -> list[str]:
    resolved_profile = dict(profile or {})
    if not resolved_profile:
        return []
    weapon_type = str(resolved_profile.get("type") or "").strip().upper()
    properties = {str(property_value).strip().upper() for property_value in list(resolved_profile.get("properties") or [])}
    if "2H" in properties:
        return [WEAPON_WIELD_MODE_TWO_HANDED]
    options = [WEAPON_WIELD_MODE_MAIN_HAND]
    if weapon_type == "M":
        options.append(WEAPON_WIELD_MODE_OFF_HAND)
        if "V" in properties and str(resolved_profile.get("versatile_damage") or "").strip():
            options.append(WEAPON_WIELD_MODE_TWO_HANDED)
    return options


def explicit_weapon_wield_mode(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
    support: dict[str, Any] | None = None,
) -> str:
    resolved_support = dict(support or describe_equipment_state_support(item, item_catalog=item_catalog))
    allowed_modes = {
        _normalize_weapon_wield_mode_value(mode_value)
        for mode_value in list(resolved_support.get("weapon_wield_modes") or [])
        if _normalize_weapon_wield_mode_value(mode_value)
    }
    if not allowed_modes:
        return ""
    normalized_mode = _normalize_weapon_wield_mode_value(dict(item or {}).get("weapon_wield_mode"))
    return normalized_mode if normalized_mode in allowed_modes else ""


def resolve_weapon_wield_mode(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
    support: dict[str, Any] | None = None,
) -> str:
    resolved_support = dict(support or describe_equipment_state_support(item, item_catalog=item_catalog))
    explicit_mode = explicit_weapon_wield_mode(
        item,
        item_catalog=item_catalog,
        support=resolved_support,
    )
    if explicit_mode:
        return explicit_mode
    allowed_modes = [
        _normalize_weapon_wield_mode_value(mode_value)
        for mode_value in list(resolved_support.get("weapon_wield_modes") or [])
        if _normalize_weapon_wield_mode_value(mode_value)
    ]
    if not allowed_modes:
        return ""
    if bool(dict(item or {}).get("is_equipped", False)):
        return allowed_modes[0]
    return ""


def resolve_item_equipped_state(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
    support: dict[str, Any] | None = None,
) -> bool:
    resolved_support = dict(support or describe_equipment_state_support(item, item_catalog=item_catalog))
    if bool(resolved_support.get("supports_weapon_wield_mode")):
        return bool(
            resolve_weapon_wield_mode(
                item,
                item_catalog=item_catalog,
                support=resolved_support,
            )
        )
    return bool(dict(item or {}).get("is_equipped", False))


def describe_equipment_state_support(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
    entry: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    if bool(dict(item or {}).get("is_currency_only")):
        return {
            "supports_equipped_state": False,
            "supports_attunement": False,
            "requires_attunement": False,
            "is_weapon": False,
            "is_armor": False,
            "is_magic_item": False,
        }

    resolved_catalog = dict(item_catalog or {})
    resolved_entry = entry if isinstance(entry, SystemsEntryRecord) else _resolve_item_entry(item, resolved_catalog)
    campaign_item_support = _resolve_campaign_item_page_support(item, resolved_catalog)
    weapon_profile = _resolve_weapon_profile(item, resolved_catalog)
    armor_profile = _resolve_armor_profile(item, resolved_catalog)
    metadata = _resolve_item_support_metadata(
        item,
        resolved_catalog,
        entry=resolved_entry,
        campaign_item_support=campaign_item_support,
    )
    requires_attunement = _metadata_requires_attunement(metadata.get("attunement"))
    is_magic_item = _metadata_is_magic_item(metadata)
    supports_equipped_state = bool(weapon_profile is not None or armor_profile is not None or is_magic_item)
    supports_attunement = bool(supports_equipped_state and requires_attunement)
    weapon_wield_modes = _weapon_wield_mode_options_for_profile(weapon_profile)
    return {
        "supports_equipped_state": supports_equipped_state,
        "supports_attunement": supports_attunement,
        "requires_attunement": supports_attunement,
        "is_weapon": weapon_profile is not None,
        "is_armor": armor_profile is not None,
        "is_magic_item": is_magic_item,
        "supports_weapon_wield_mode": bool(weapon_wield_modes),
        "weapon_wield_modes": weapon_wield_modes,
    }


def _build_level_one_attacks(
    *,
    equipment_catalog: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    weapon_proficiencies: list[str],
    selected_choices: dict[str, list[str]],
    features: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    attack_contexts = _build_weapon_attack_contexts(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        weapon_proficiencies=weapon_proficiencies,
    )
    has_archery = _has_fighting_style(selected_choices, "phb-optionalfeature-archery", "Archery") or _character_has_named_feature(
        features,
        "Archery",
        "phb-optionalfeature-archery",
    )
    has_dueling = _has_fighting_style(selected_choices, "phb-optionalfeature-dueling", "Dueling") or _character_has_named_feature(
        features,
        "Dueling",
        "phb-optionalfeature-dueling",
    )
    has_great_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-great-weapon-fighting",
        "Great Weapon Fighting",
    ) or _character_has_named_feature(
        features,
        "Great Weapon Fighting",
        "phb-optionalfeature-great-weapon-fighting",
    )
    has_two_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-two-weapon-fighting",
        "Two-Weapon Fighting",
    ) or _character_has_named_feature(
        features,
        "Two-Weapon Fighting",
        "phb-optionalfeature-two-weapon-fighting",
    )
    active_effect_keys = list(_extract_character_effect_keys(features))
    attack_support_flags = _collect_attack_support_flags(features)
    shared_weapon_attack_bonus = _effect_weapon_attack_bonus(active_effect_keys) + _structured_weapon_attack_bonus(features)
    shared_weapon_damage_bonus = _effect_weapon_damage_bonus(active_effect_keys) + _structured_weapon_damage_bonus(features)
    structured_mode_descriptors = _effect_attack_mode_descriptors(active_effect_keys)
    has_charger_phb = bool(attack_support_flags.get("charger_phb"))
    has_charger_xphb = bool(attack_support_flags.get("charger_xphb"))
    has_crossbow_expert = bool(attack_support_flags.get("crossbow_expert"))
    has_dual_wielder = bool(attack_support_flags.get("dual_wielder"))
    has_great_weapon_master = bool(attack_support_flags.get("great_weapon_master"))
    has_grappler_phb = bool(attack_support_flags.get("grappler_phb"))
    has_mounted_combatant_phb = bool(attack_support_flags.get("mounted_combatant_phb"))
    has_gunner = bool(attack_support_flags.get("gunner"))
    has_martial_adept = bool(attack_support_flags.get("martial_adept"))
    has_polearm_master = bool(attack_support_flags.get("polearm_master"))
    has_savage_attacker = bool(attack_support_flags.get("savage_attacker"))
    has_sharpshooter = bool(attack_support_flags.get("sharpshooter"))
    has_shield_master = bool(attack_support_flags.get("shield_master"))
    has_tavern_brawler = bool(attack_support_flags.get("tavern_brawler"))
    off_hand_context = _resolve_off_hand_attack_context(
        attack_contexts,
        allow_non_light=has_dual_wielder,
        item_catalog=item_catalog,
    )
    crossbow_expert_bonus_context = _resolve_crossbow_expert_bonus_attack_context(attack_contexts)
    shield_item_refs = [
        str(item.get("id") or "").strip()
        for item in equipment_catalog
        if _is_shield_item(item)
        if str(item.get("id") or "").strip()
    ]
    has_shield = any(
        _is_shield_item(item) and resolve_item_equipped_state(item, item_catalog=item_catalog)
        for item in equipment_catalog
    )

    for context in attack_contexts:
        profile = dict(context["profile"] or {})
        has_thrown_variant = _supports_thrown_attack_variant(profile)
        has_two_handed_variant = _supports_versatile_two_handed_attack(
            profile,
            has_shield=has_shield,
            off_hand_context=off_hand_context,
        )
        attack_bonus = int(context["ability_modifier"] or 0)
        if bool(context["is_proficient"]):
            attack_bonus += proficiency_bonus
        attack_bonus += int(context.get("item_attack_bonus") or 0)
        attack_bonus += shared_weapon_attack_bonus
        if has_archery and str(profile.get("type") or "").strip().upper() == "R":
            attack_bonus += 2
        damage_bonus = int(context["ability_modifier"] or 0)
        damage_bonus += int(context.get("item_damage_bonus") or 0)
        damage_bonus += shared_weapon_damage_bonus
        if has_dueling and _qualifies_for_dueling(context, off_hand_context=off_hand_context):
            damage_bonus += 2
        ignore_loading = (
            (has_crossbow_expert and _qualifies_for_crossbow_expert(context))
            or (has_gunner and _qualifies_for_gunner(context))
        )
        base_attack_notes = _build_weapon_attack_notes(
            profile,
            great_weapon_fighting=has_great_weapon_fighting,
            has_shield=has_shield,
            ignore_loading=ignore_loading,
            off_hand_context=off_hand_context,
            show_range=not has_thrown_variant,
            show_versatile=not has_two_handed_variant,
            extra_notes=_base_attack_feat_notes(
                context,
                has_charger_phb=has_charger_phb,
                has_charger_xphb=has_charger_xphb,
                has_crossbow_expert=has_crossbow_expert,
                has_great_weapon_master=has_great_weapon_master,
                has_gunner=has_gunner,
                has_martial_adept=has_martial_adept,
                has_mounted_combatant_phb=has_mounted_combatant_phb,
                has_polearm_master=has_polearm_master,
                has_savage_attacker=has_savage_attacker,
                has_sharpshooter=has_sharpshooter,
                ranged_attack=False,
            ),
        )
        _append_weapon_attack_payloads(
            attacks,
            context,
            attack_bonus=attack_bonus,
            damage_bonus=damage_bonus,
            extra_damage=None,
            notes=base_attack_notes,
            structured_mode_descriptors=structured_mode_descriptors,
        )
        if has_great_weapon_master and _qualifies_for_great_weapon_master(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus - 5,
                damage_bonus=damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Great Weapon Master (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="great weapon master",
                mode_key=ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER,
            )
        if has_polearm_master and _qualifies_for_polearm_master(context):
            polearm_bonus_profile = dict(profile)
            polearm_bonus_profile["damage"] = "1d4"
            polearm_bonus_profile["damage_type"] = "B"
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    polearm_bonus_profile,
                    bonus_action=True,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=False,
                    show_versatile=False,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                        include_polearm_master_note=False,
                    )
                    + ["Polearm Master bonus attack"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="polearm master",
                mode_key=ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS,
                profile_override=polearm_bonus_profile,
            )
            if has_two_handed_variant:
                polearm_two_handed_profile = dict(polearm_bonus_profile)
                polearm_two_handed_damage_bonus = int(context["ability_modifier"] or 0)
                _append_weapon_attack_payloads(
                    attacks,
                    context,
                    attack_bonus=attack_bonus,
                    damage_bonus=polearm_two_handed_damage_bonus,
                    extra_damage=None,
                    notes=_build_weapon_attack_notes(
                        polearm_two_handed_profile,
                        bonus_action=True,
                        great_weapon_fighting=has_great_weapon_fighting,
                        has_shield=False,
                        off_hand_context=None,
                        show_range=False,
                        show_versatile=False,
                        wielded_two_handed=True,
                        extra_notes=_base_attack_feat_notes(
                            context,
                            has_charger_phb=has_charger_phb,
                            has_charger_xphb=has_charger_xphb,
                            has_crossbow_expert=has_crossbow_expert,
                            has_great_weapon_master=has_great_weapon_master,
                            has_gunner=has_gunner,
                            has_martial_adept=has_martial_adept,
                            has_mounted_combatant_phb=has_mounted_combatant_phb,
                            has_polearm_master=has_polearm_master,
                            has_savage_attacker=has_savage_attacker,
                            has_sharpshooter=has_sharpshooter,
                            ranged_attack=False,
                            include_polearm_master_note=False,
                        )
                        + ["Polearm Master bonus attack"],
                    ),
                    structured_mode_descriptors=structured_mode_descriptors,
                    variant_label="polearm master, two-handed",
                    mode_key=f"{ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS}|{ATTACK_MODE_WEAPON_TWO_HANDED}",
                    profile_override=polearm_two_handed_profile,
                )
        if has_charger_xphb and _qualifies_for_charger(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage="1d8",
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Charger (move 10 feet straight, +1d8 damage, once per turn)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="charger",
                mode_key=ATTACK_MODE_FEAT_CHARGER_XPHB,
            )
        if has_thrown_variant:
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    off_hand_context=off_hand_context,
                    show_versatile=False,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=True,
                    ),
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="thrown",
                mode_key=ATTACK_MODE_WEAPON_THROWN,
                category_override="ranged weapon",
            )
        if has_two_handed_variant:
            two_handed_profile = dict(profile)
            two_handed_profile["damage"] = str(profile.get("versatile_damage") or "").strip()
            two_handed_attack_bonus = int(context["ability_modifier"] or 0)
            if bool(context["is_proficient"]):
                two_handed_attack_bonus += proficiency_bonus
            two_handed_damage_bonus = int(context["ability_modifier"] or 0)
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=two_handed_attack_bonus,
                damage_bonus=two_handed_damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    two_handed_profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=False,
                    off_hand_context=None,
                    show_versatile=False,
                    wielded_two_handed=True,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    ),
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="two-handed",
                mode_key=ATTACK_MODE_WEAPON_TWO_HANDED,
                profile_override=two_handed_profile,
            )
        if has_sharpshooter and _qualifies_for_sharpshooter(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus - 5,
                damage_bonus=damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=True,
                    )
                    + ["Sharpshooter (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="sharpshooter",
                mode_key=ATTACK_MODE_FEAT_SHARPSHOOTER,
            )
        if has_charger_phb and _qualifies_for_charger(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus + 5,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    bonus_action=True,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=False,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_mounted_combatant_phb=has_mounted_combatant_phb,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Charger (after Dash, move 10 feet straight for +5 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="charger",
                mode_key=ATTACK_MODE_FEAT_CHARGER_PHB,
            )

    if off_hand_context is not None:
        off_hand_damage_bonus = (
            int(off_hand_context["ability_modifier"] or 0)
            if has_two_weapon_fighting
            else min(int(off_hand_context["ability_modifier"] or 0), 0)
        )
        off_hand_attack_bonus = int(off_hand_context["ability_modifier"] or 0)
        if bool(off_hand_context["is_proficient"]):
            off_hand_attack_bonus += proficiency_bonus
        _append_weapon_attack_payloads(
            attacks,
            off_hand_context,
            attack_bonus=off_hand_attack_bonus,
            damage_bonus=off_hand_damage_bonus,
            extra_damage=None,
            notes=_build_weapon_attack_notes(
                dict(off_hand_context["profile"] or {}),
                bonus_action=True,
                great_weapon_fighting=False,
                has_shield=False,
                off_hand_context=off_hand_context,
                show_versatile=False,
                extra_notes=_base_attack_feat_notes(
                    off_hand_context,
                    has_charger_phb=has_charger_phb,
                    has_charger_xphb=has_charger_xphb,
                    has_crossbow_expert=has_crossbow_expert,
                    has_great_weapon_master=has_great_weapon_master,
                    has_gunner=has_gunner,
                    has_martial_adept=has_martial_adept,
                    has_mounted_combatant_phb=has_mounted_combatant_phb,
                    has_polearm_master=has_polearm_master,
                    has_savage_attacker=has_savage_attacker,
                    has_sharpshooter=has_sharpshooter,
                    ranged_attack=False,
                ),
            ),
            structured_mode_descriptors=structured_mode_descriptors,
            variant_label="off-hand",
            mode_key=ATTACK_MODE_WEAPON_OFF_HAND,
        )
    if has_crossbow_expert and crossbow_expert_bonus_context is not None:
        crossbow_profile = dict(crossbow_expert_bonus_context["profile"] or {})
        crossbow_attack_bonus = int(crossbow_expert_bonus_context["ability_modifier"] or 0)
        if bool(crossbow_expert_bonus_context["is_proficient"]):
            crossbow_attack_bonus += proficiency_bonus
        if has_archery and str(crossbow_profile.get("type") or "").strip().upper() == "R":
            crossbow_attack_bonus += 2
        crossbow_damage_bonus = int(crossbow_expert_bonus_context["ability_modifier"] or 0)
        crossbow_extra_notes = _base_attack_feat_notes(
            crossbow_expert_bonus_context,
            has_charger_phb=has_charger_phb,
            has_charger_xphb=has_charger_xphb,
            has_crossbow_expert=has_crossbow_expert,
            has_great_weapon_master=has_great_weapon_master,
            has_gunner=has_gunner,
            has_martial_adept=has_martial_adept,
            has_mounted_combatant_phb=has_mounted_combatant_phb,
            has_polearm_master=has_polearm_master,
            has_savage_attacker=has_savage_attacker,
            has_sharpshooter=has_sharpshooter,
            ranged_attack=True,
        ) + ["Crossbow Expert bonus attack"]
        _append_weapon_attack_payloads(
            attacks,
            crossbow_expert_bonus_context,
            attack_bonus=crossbow_attack_bonus,
            damage_bonus=crossbow_damage_bonus,
            extra_damage=None,
            notes=_build_weapon_attack_notes(
                crossbow_profile,
                bonus_action=True,
                great_weapon_fighting=False,
                has_shield=has_shield,
                ignore_loading=True,
                off_hand_context=off_hand_context,
                extra_notes=crossbow_extra_notes,
            ),
            structured_mode_descriptors=structured_mode_descriptors,
            variant_label="crossbow expert",
            mode_key=ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS,
        )
        if has_sharpshooter and _qualifies_for_sharpshooter(crossbow_expert_bonus_context):
            _append_weapon_attack_payloads(
                attacks,
                crossbow_expert_bonus_context,
                attack_bonus=crossbow_attack_bonus - 5,
                damage_bonus=crossbow_damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    crossbow_profile,
                    bonus_action=True,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    ignore_loading=True,
                    off_hand_context=off_hand_context,
                    extra_notes=crossbow_extra_notes + ["Sharpshooter (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="crossbow expert, sharpshooter",
                mode_key=f"{ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS}|{ATTACK_MODE_FEAT_SHARPSHOOTER}",
            )
    if has_shield_master and shield_item_refs:
        attacks.append(
            _build_special_attack_payload(
                name="Shield Shove",
                category="special action",
                notes="Bonus action after taking the Attack action; Shield Master shove within 5 feet.",
                index=len(attacks) + 1,
                mode_key=ATTACK_MODE_FEAT_SHIELD_MASTER_SHOVE,
                equipment_refs=shield_item_refs,
            )
        )
    if has_grappler_phb:
        attacks.append(
            _build_special_attack_payload(
                name="Pin Grappled Creature",
                category="special action",
                notes="Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends.",
                index=len(attacks) + 1,
                mode_key=ATTACK_MODE_FEAT_GRAPPLER_PIN,
            )
        )
    if has_tavern_brawler:
        attacks.append(
            _build_unarmed_attack_payload(
                ability_scores=ability_scores,
                proficiency_bonus=proficiency_bonus,
                index=len(attacks) + 1,
            )
        )
    return attacks


def _effect_keys_for_feature(feature: dict[str, Any]) -> list[str]:
    systems_ref = dict(feature.get("systems_ref") or {})
    campaign_option = dict(feature.get("campaign_option") or {})
    feature_name = str(feature.get("name") or systems_ref.get("title") or "").strip()
    effect_keys: list[str] = []
    if feature_name:
        effect_keys.append(feature_name)
        normalized_name = normalize_lookup(feature_name)
        normalized_slug = normalize_lookup(str(systems_ref.get("slug") or "").strip())
        source_id = str(systems_ref.get("source_id") or feature.get("source") or "").strip().upper()
        if normalized_name == normalize_lookup("Charger"):
            effect_keys.append("charger-xphb" if source_id == "XPHB" else "charger-phb")
        if normalized_name == normalize_lookup("Grappler"):
            effect_keys.append("grappler-xphb" if source_id == "XPHB" else "grappler-phb")
        if normalized_name == normalize_lookup("Mounted Combatant"):
            effect_keys.append("mounted-combatant-xphb" if source_id == "XPHB" else "mounted-combatant-phb")
        if normalized_name == normalize_lookup("Alert"):
            effect_keys.append("initiative-bonus:5")
        if normalized_name == normalize_lookup("Mobile"):
            effect_keys.append("speed-bonus:10")
        if normalized_name == normalize_lookup("Powerful Build"):
            effect_keys.append("carrying-capacity-multiplier:2")
        if normalized_name == normalize_lookup("Observant"):
            effect_keys.extend(
                [
                    "passive-bonus:Perception:5",
                    "passive-bonus:Investigation:5",
                ]
            )
        if normalized_name == normalize_lookup("Jack of All Trades"):
            effect_keys.append("half-proficiency:all")
        if normalized_name == normalize_lookup("Remarkable Athlete"):
            effect_keys.append("half-proficiency:abilities:str,dex,con")
        if normalized_name == normalize_lookup("Temporal Awareness"):
            effect_keys.append("initiative-bonus-ability:int")
        if normalized_slug == normalize_lookup("phb-feat-medium-armor-master") or (
            not normalized_slug and normalized_name == normalize_lookup("Medium Armor Master")
        ):
            effect_keys.append("armor-dex-cap-bonus:medium:1")
        if normalized_name == normalize_lookup("Tavern Brawler"):
            effect_keys.append("tavern-brawler")
    for effect in _dedupe_preserve_order(
        [
            *list(campaign_option.get("modeled_effects") or []),
            *collect_mechanic_effect_legacy_keys(campaign_option.get("mechanic_effects")),
        ]
    ):
        clean_effect = str(effect or "").strip()
        if clean_effect:
            effect_keys.append(clean_effect)
    return effect_keys


def _qualifies_for_crossbow_expert(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if not bool(context.get("is_proficient")):
        return False
    if str(profile.get("type") or "").strip().upper() != "R":
        return False
    return "crossbow" in normalize_lookup(str(context.get("attack_name") or "").strip())


def _qualifies_for_gunner(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if not bool(context.get("is_proficient")):
        return False
    if str(profile.get("type") or "").strip().upper() != "R":
        return False
    return _weapon_uses_firearm_proficiency(profile, attack_name=str(context.get("attack_name") or "").strip())


def _qualifies_for_charger(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "M"


def _qualifies_for_mounted_combatant(
    context: dict[str, Any],
    *,
    ranged_attack: bool,
) -> bool:
    if ranged_attack:
        return False
    profile = dict(context.get("profile") or {})
    return str(profile.get("type") or "").strip().upper() == "M"


def _qualifies_for_crossbow_expert_bonus_attack(context: dict[str, Any]) -> bool:
    if not _qualifies_for_crossbow_expert(context):
        return False
    item = dict(context.get("item") or {})
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(context.get("attack_name") or "").strip(),
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
        str(systems_ref.get("slug") or "").strip(),
    ]
    normalized_candidates = {
        normalize_lookup(value)
        for value in candidate_values
        if str(value or "").strip()
    }
    return bool(
        normalized_candidates
        & {
            normalize_lookup("Hand Crossbow"),
            normalize_lookup("phb-item-hand-crossbow"),
        }
    )


def _resolve_crossbow_expert_bonus_attack_context(
    attack_contexts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for context in attack_contexts:
        if _qualifies_for_crossbow_expert_bonus_attack(context):
            return context
    return None


def _qualifies_for_great_weapon_master(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    properties = set(profile.get("properties") or [])
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "M" and "H" in properties


def _qualifies_for_polearm_master(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if str(profile.get("type") or "").strip().upper() != "M":
        return False
    item = dict(context.get("item") or {})
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(context.get("attack_name") or "").strip(),
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
    ]
    normalized_candidates = {
        normalize_lookup(value)
        for value in candidate_values
        if str(value or "").strip()
    }
    return bool(
        normalized_candidates
        & {
            normalize_lookup("Glaive"),
            normalize_lookup("Halberd"),
            normalize_lookup("Quarterstaff"),
            normalize_lookup("Spear"),
            normalize_lookup("Staff"),
            normalize_lookup("Wooden Staff"),
        }
    )


def _qualifies_for_savage_attacker(context: dict[str, Any], *, ranged_attack: bool) -> bool:
    profile = dict(context.get("profile") or {})
    return not ranged_attack and str(profile.get("type") or "").strip().upper() == "M"


def _qualifies_for_sharpshooter(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "R"


def _base_attack_feat_notes(
    context: dict[str, Any],
    *,
    has_charger_phb: bool = False,
    has_charger_xphb: bool = False,
    has_crossbow_expert: bool,
    has_great_weapon_master: bool,
    has_gunner: bool = False,
    has_martial_adept: bool,
    has_mounted_combatant_phb: bool = False,
    has_polearm_master: bool,
    has_savage_attacker: bool,
    has_sharpshooter: bool,
    ranged_attack: bool,
    include_polearm_master_note: bool = True,
) -> list[str]:
    notes: list[str] = []
    if has_crossbow_expert and _qualifies_for_crossbow_expert(context):
        notes.append("Crossbow Expert (ignore loading, no adjacent disadvantage)")
    if has_gunner and _qualifies_for_gunner(context):
        notes.append("Gunner (ignore loading, no adjacent disadvantage)")
    if has_great_weapon_master and _qualifies_for_great_weapon_master(context):
        notes.append("Great Weapon Master (bonus attack on crit or kill)")
    if has_martial_adept and not ranged_attack:
        notes.append("Martial Adept maneuvers available")
    if has_mounted_combatant_phb and _qualifies_for_mounted_combatant(context, ranged_attack=ranged_attack):
        notes.append("Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)")
    if (
        has_polearm_master
        and include_polearm_master_note
        and not ranged_attack
        and _qualifies_for_polearm_master(context)
    ):
        notes.append("Polearm Master (bonus attack, opportunity attack when creatures enter reach)")
    if has_savage_attacker and _qualifies_for_savage_attacker(context, ranged_attack=ranged_attack):
        notes.append("Savage Attacker (reroll damage once per turn)")
    if has_sharpshooter and _qualifies_for_sharpshooter(context):
        notes.append("Sharpshooter (ignore cover, no long-range disadvantage)")
    return notes


def _build_weapon_attack_contexts(
    *,
    equipment_catalog: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    ability_scores: dict[str, int],
    weapon_proficiencies: list[str],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for item in equipment_catalog:
        profile = _resolve_weapon_profile(item, item_catalog)
        if profile is None:
            continue
        campaign_item_support = _resolve_campaign_item_page_support(item, item_catalog)
        attack_name = str(item.get("name") or profile.get("title") or "").strip()
        if not attack_name:
            continue
        ability_key = _weapon_attack_ability_key(profile, ability_scores)
        contexts.append(
            {
                "item": dict(item),
                "profile": dict(profile),
                "page_ref": (
                    dict(item).get("page_ref")
                    or str((campaign_item_support or {}).get("page_ref") or "").strip()
                    or None
                ),
                "attack_name": attack_name,
                "ability_key": ability_key,
                "ability_modifier": _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)),
                "is_proficient": _is_proficient_with_weapon(profile, weapon_proficiencies, attack_name),
                "quantity": max(int(item.get("default_quantity") or 1), 1),
                "item_attack_bonus": _active_weapon_profile_bonus(item, profile, key="item_attack_bonus"),
                "item_damage_bonus": _active_weapon_profile_bonus(item, profile, key="item_damage_bonus"),
            }
        )
    return contexts


def _build_weapon_attack_payload(
    context: dict[str, Any],
    *,
    attack_bonus: int,
    damage_bonus: int,
    extra_damage: str | None = None,
    notes: str,
    index: int,
    variant_label: str = "",
    mode_key: str = "",
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = dict(profile_override or context["profile"] or {})
    clean_mode_key = _normalize_attack_mode_key(mode_key)
    clean_variant_label = _normalize_attack_variant_label(
        raw_variant_label=variant_label,
        mode_key=clean_mode_key,
        attack_name=context.get("attack_name"),
        notes=notes,
    )
    attack_name = f"{str(context.get('attack_name') or '').strip()}{_attack_name_suffix(clean_variant_label)}"
    equipment_ref = str(dict(context.get("item") or {}).get("id") or "").strip()
    raw_page_ref = context.get("page_ref")
    if raw_page_ref in (None, ""):
        raw_page_ref = dict(context.get("item") or {}).get("page_ref")
    payload = {
        "id": f"{slugify(attack_name)}-{index}",
        "name": attack_name,
        "category": str(category_override or _weapon_attack_category(profile)),
        "attack_bonus": attack_bonus,
        "damage": _format_weapon_damage(profile, damage_bonus, extra_damage=extra_damage),
        "damage_type": DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), ""),
        "notes": notes,
        "systems_ref": dict(dict(context.get("item") or {}).get("systems_ref") or {}) or None,
        "page_ref": dict(raw_page_ref) if isinstance(raw_page_ref, dict) else raw_page_ref or None,
        "equipment_refs": [equipment_ref] if equipment_ref else [],
    }
    if clean_mode_key:
        payload["mode_key"] = clean_mode_key
    if clean_variant_label:
        payload["variant_label"] = clean_variant_label
    return payload


def _append_weapon_attack_payloads(
    attacks: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    attack_bonus: int,
    damage_bonus: int,
    extra_damage: str | None,
    notes: str,
    structured_mode_descriptors: list[dict[str, Any]] | None = None,
    variant_label: str = "",
    mode_key: str = "",
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> None:
    payload = _build_weapon_attack_payload(
        context,
        attack_bonus=attack_bonus,
        damage_bonus=damage_bonus,
        extra_damage=extra_damage,
        notes=notes,
        index=len(attacks) + 1,
        variant_label=variant_label,
        mode_key=mode_key,
        category_override=category_override,
        profile_override=profile_override,
    )
    attacks.append(payload)
    for descriptor in list(structured_mode_descriptors or []):
        if not _attack_mode_descriptor_applies_to_context(
            descriptor,
            context,
            category_override=category_override,
            profile_override=profile_override,
        ):
            continue
        descriptor_mode_component = str(descriptor.get("mode_component") or "").strip()
        if not descriptor_mode_component:
            continue
        combined_mode_key = _normalize_attack_mode_key([payload.get("mode_key"), descriptor_mode_component])
        attacks.append(
            _build_weapon_attack_payload(
                context,
                attack_bonus=attack_bonus + int(descriptor.get("attack_delta") or 0),
                damage_bonus=damage_bonus + int(descriptor.get("damage_delta") or 0),
                extra_damage=_combine_attack_extra_damage(extra_damage, descriptor.get("extra_damage")),
                notes=_append_attack_note_text(notes, descriptor.get("note")),
                index=len(attacks) + 1,
                mode_key=combined_mode_key,
                category_override=category_override,
                profile_override=profile_override,
            )
        )


def _resolve_off_hand_attack_context(
    attack_contexts: list[dict[str, Any]],
    *,
    allow_non_light: bool = False,
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    explicit_contexts: list[dict[str, Any]] = []
    eligible_contexts: list[dict[str, Any]] = []
    for context in attack_contexts:
        item = dict(context.get("item") or {})
        if not resolve_item_equipped_state(item, item_catalog=item_catalog):
            continue
        profile = dict(context.get("profile") or {})
        if str(profile.get("type") or "").strip().upper() != "M":
            continue
        properties = set(profile.get("properties") or [])
        if "2H" in properties:
            continue
        if not allow_non_light and "L" not in properties:
            continue
        if explicit_weapon_wield_mode(item, item_catalog=item_catalog) == WEAPON_WIELD_MODE_OFF_HAND:
            explicit_contexts.append(context)
        quantity = max(int(context.get("quantity") or 1), 1)
        for _ in range(quantity):
            eligible_contexts.append(context)
    if explicit_contexts:
        return explicit_contexts[0]
    if len(eligible_contexts) >= 2:
        return eligible_contexts[1]
    return None


def _resolve_weapon_profile(
    item: dict[str, Any],
    item_catalog: dict[str, Any],
) -> dict[str, Any] | None:
    entry = _resolve_item_entry(item, item_catalog)
    metadata = _resolve_item_support_metadata(item, item_catalog, entry=entry)
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_titles = [
        str(systems_ref.get("title") or "").strip(),
        str(item.get("name") or "").strip(),
        str(metadata.get("base_item") or "").split("|", 1)[0].strip(),
    ]
    profiles = dict(item_catalog.get("phb_weapon_profiles") or _load_phb_weapon_profiles())
    profiles_by_norm = {
        normalize_lookup(title): dict(profile)
        for title, profile in list(profiles.items())
        if str(title or "").strip()
    }
    resolved_requires_attunement = _metadata_requires_attunement(metadata.get("attunement"))
    for title in candidate_titles:
        base_title, parsed_bonus = _split_magic_item_name(title)
        for candidate_key in _merge_name_candidates(base_title):
            profile = profiles_by_norm.get(candidate_key)
            if profile is None:
                continue
            attack_bonus, damage_bonus = _resolve_weapon_bonus_from_metadata(
                metadata,
                fallback_bonus=parsed_bonus,
            )
            resolved_profile = dict(profile)
            resolved_profile["item_attack_bonus"] = attack_bonus
            resolved_profile["item_damage_bonus"] = damage_bonus
            resolved_profile["requires_attunement"] = resolved_requires_attunement
            return resolved_profile
    return None


def _resolve_campaign_item_page_support(
    item: Any,
    item_catalog: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not item_catalog:
        return None
    by_page_ref = dict(item_catalog.get("campaign_item_support_by_page_ref") or {})
    by_title = dict(item_catalog.get("campaign_item_support_by_title") or {})
    if isinstance(item, dict):
        page_ref = _extract_campaign_page_ref(dict(item).get("page_ref"))
        if page_ref:
            support = by_page_ref.get(page_ref)
            if isinstance(support, dict):
                return dict(support)
        candidate_titles = [
            str(dict(item).get("name") or "").strip(),
            str(dict(dict(item).get("systems_ref") or {}).get("title") or "").strip(),
        ]
    else:
        raw_reference = str(item or "").strip()
        candidate_titles = [raw_reference, _humanize_item_reference(raw_reference)] if raw_reference else []
    for title in candidate_titles:
        for candidate_key in _merge_name_candidates(title):
            support = by_title.get(candidate_key)
            if isinstance(support, dict):
                return dict(support)
    return None


def _resolve_item_support_metadata(
    item: Any,
    item_catalog: dict[str, Any] | None,
    *,
    entry: SystemsEntryRecord | None = None,
    campaign_item_support: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_entry = entry if isinstance(entry, SystemsEntryRecord) else _resolve_item_entry(item, item_catalog)
    if isinstance(resolved_entry, SystemsEntryRecord):
        entry_metadata = dict(resolved_entry.metadata or {})
        if is_campaign_item_mechanics_metadata(entry_metadata):
            return campaign_item_character_metadata(entry_metadata)
        return entry_metadata
    resolved_campaign_item_support = (
        dict(campaign_item_support or {})
        if isinstance(campaign_item_support, dict)
        else _resolve_campaign_item_page_support(item, item_catalog)
    )
    return dict(dict(resolved_campaign_item_support or {}).get("metadata") or {})


def _item_effect_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    effect_payload: dict[str, Any] = {}
    spell_support = [dict(item or {}) for item in list(payload.get("spell_support") or []) if isinstance(item, dict)]
    if spell_support:
        effect_payload["spell_support"] = spell_support
    ability_score_minimums = {
        normalize_lookup(ability_key): int(minimum)
        for ability_key, minimum in dict(payload.get("ability_score_minimums") or {}).items()
        if normalize_lookup(ability_key) in ABILITY_KEYS
    }
    if ability_score_minimums:
        effect_payload["ability_score_minimums"] = ability_score_minimums
    resource_template_bonuses = []
    for entry in list(payload.get("resource_template_bonuses") or []):
        bonus_payload = dict(entry or {})
        tracker_id = str(
            bonus_payload.get("id")
            or bonus_payload.get("tracker_id")
            or ""
        ).strip()
        if not tracker_id:
            continue
        try:
            bonus_value = int(bonus_payload.get("bonus") or 0)
        except (TypeError, ValueError):
            continue
        if not bonus_value:
            continue
        resource_template_bonuses.append({"id": tracker_id, "bonus": bonus_value})
    if resource_template_bonuses:
        effect_payload["resource_template_bonuses"] = resource_template_bonuses
    defensive_rules = [dict(rule or {}) for rule in list(payload.get("defensive_rules") or []) if isinstance(rule, dict)]
    if defensive_rules:
        effect_payload["defensive_rules"] = defensive_rules
    attack_reminder_rules = [
        dict(rule or {})
        for rule in list(payload.get("attack_reminder_rules") or [])
        if isinstance(rule, dict)
    ]
    if attack_reminder_rules:
        effect_payload["attack_reminder_rules"] = attack_reminder_rules
    return effect_payload


def _attack_reminder_rule_save_dc(
    rule: dict[str, Any],
    *,
    ability_scores: dict[str, int] | None,
    proficiency_bonus: int,
) -> int | None:
    ability_key = normalize_lookup(str(rule.get("save_dc_ability_key") or "").strip())
    if ability_key not in ABILITY_KEYS:
        return None
    score = int(dict(ability_scores or {}).get(ability_key) or DEFAULT_ABILITY_SCORE)
    return 8 + int(proficiency_bonus or 0) + _ability_modifier(score)


def _format_dynamic_reminder_text(
    value: Any,
    *,
    save_dc: int | None = None,
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if save_dc is not None:
        return text.replace("{save_dc}", str(save_dc))
    return text.replace("{save_dc}", "the current save DC")


def _item_effect_is_active(item: dict[str, Any], *, metadata: dict[str, Any]) -> bool:
    if not bool(item.get("is_equipped", False)):
        return False
    if _metadata_requires_attunement(metadata.get("attunement")) and not bool(item.get("is_attuned", False)):
        return False
    return True


def _active_item_effect_entries(
    equipment_catalog: list[dict[str, Any]] | None,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in list(equipment_catalog or []):
        payload = dict(item or {})
        metadata = _resolve_item_support_metadata(payload, item_catalog)
        effect_payload = _item_effect_metadata(metadata)
        if not effect_payload or not _item_effect_is_active(payload, metadata=metadata):
            continue
        entries.append(
            {
                "item_id": str(payload.get("id") or "").strip(),
                "item_name": str(payload.get("name") or "").strip(),
                "page_ref": str(payload.get("page_ref") or "").strip(),
                **effect_payload,
            }
        )
    return entries


def _active_weapon_profile_bonus(item: dict[str, Any], profile: dict[str, Any], *, key: str) -> int:
    if not bool(item.get("is_equipped", False)):
        return 0
    if bool(profile.get("requires_attunement")) and not bool(item.get("is_attuned", False)):
        return 0
    return int(profile.get(key) or 0)


def _parse_optional_int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"[-+]?\d+", str(value))
    if match is None:
        return None
    return int(match.group(0))


def _build_armor_profile(
    *,
    title: str,
    type_code: str,
    base_ac: int,
    bonus_ac: int = 0,
    minimum_strength: int | None = None,
    stealth_disadvantage: bool = False,
) -> dict[str, Any] | None:
    normalized_type = str(type_code or "").split("|", 1)[0].strip().upper()
    if normalized_type not in {"LA", "MA", "HA", "S"}:
        return None
    armor_category = {
        "LA": "light",
        "MA": "medium",
        "HA": "heavy",
        "S": "shield",
    }[normalized_type]
    return {
        "title": str(title or "").strip(),
        "type": normalized_type,
        "armor_category": armor_category,
        "base_ac": int(base_ac),
        "uses_dex": normalized_type in {"LA", "MA"},
        "dex_cap": 2 if normalized_type == "MA" else None,
        "is_shield": normalized_type == "S",
        "bonus_ac": int(bonus_ac or 0),
        "minimum_strength": minimum_strength,
        "stealth_disadvantage": bool(stealth_disadvantage),
    }


def _armor_profile_from_entry(entry: SystemsEntryRecord | None) -> dict[str, Any] | None:
    if not isinstance(entry, SystemsEntryRecord):
        return None
    metadata = dict(entry.metadata or {})
    type_code = str(metadata.get("type") or "").split("|", 1)[0].strip().upper()
    base_ac = _parse_optional_int_value(metadata.get("ac"))
    if base_ac is None:
        return None
    return _build_armor_profile(
        title=entry.title,
        type_code=type_code,
        base_ac=base_ac,
        bonus_ac=_parse_optional_int_value(metadata.get("bonus_ac")) or 0,
        minimum_strength=_parse_optional_int_value(metadata.get("strength")),
        stealth_disadvantage=bool(metadata.get("stealth_disadvantage")),
    )


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


def _metadata_requires_attunement(value: Any) -> bool:
    if value in (None, "", False, [], {}):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized or normalized in {"false", "none", "no", "not required"}:
            return False
    return True


def _metadata_is_magic_item(metadata: dict[str, Any]) -> bool:
    if _metadata_requires_attunement(metadata.get("attunement")):
        return True
    rarity = str(metadata.get("rarity") or "").strip().lower()
    if not rarity or rarity in {"false", "none", "no", "not required", "unknown", "mundane"}:
        return False
    return True


def _resolve_weapon_bonus_from_metadata(
    metadata: dict[str, Any],
    *,
    fallback_bonus: int = 0,
) -> tuple[int, int]:
    shared_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon"))
        or _parse_optional_int_value(metadata.get("bonus"))
        or fallback_bonus
    )
    attack_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon_attack"))
        or _parse_optional_int_value(metadata.get("bonus_attack_rolls"))
        or shared_bonus
    )
    damage_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon_damage"))
        or _parse_optional_int_value(metadata.get("bonus_damage_rolls"))
        or shared_bonus
    )
    return int(attack_bonus or 0), int(damage_bonus or 0)


def _resolve_armor_profile(
    item: dict[str, Any],
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    infusion_bonus_ac = active_infusion_armor_class_bonus(item)
    entry = _resolve_item_entry(item, item_catalog)
    entry_profile = _armor_profile_from_entry(entry)
    if entry_profile is not None:
        resolved_entry_profile = dict(entry_profile)
        resolved_entry_profile["bonus_ac"] = int(resolved_entry_profile.get("bonus_ac") or 0) + infusion_bonus_ac
        return resolved_entry_profile

    armor_profiles = dict((item_catalog or {}).get("phb_armor_profiles") or _load_phb_armor_profiles())
    metadata = _resolve_item_support_metadata(item, item_catalog, entry=entry)
    bonus_ac = _parse_optional_int_value(metadata.get("bonus_ac")) or 0
    candidate_titles = []
    base_item = str(metadata.get("base_item") or "").split("|", 1)[0].strip()
    if base_item:
        candidate_titles.append(base_item)
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_titles.extend(
        [
            str(systems_ref.get("title") or "").strip(),
            str(item.get("name") or "").strip(),
        ]
    )
    seen_candidates: set[str] = set()
    for raw_title in candidate_titles:
        base_title, parsed_bonus = _split_magic_item_name(raw_title)
        effective_bonus = bonus_ac or parsed_bonus
        for candidate in _merge_name_candidates(base_title):
            if candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)
            profile = armor_profiles.get(candidate)
            if profile is None:
                continue
            resolved_profile = dict(profile)
            resolved_profile["bonus_ac"] = (
                int(resolved_profile.get("bonus_ac") or 0)
                + int(effective_bonus or 0)
                + infusion_bonus_ac
            )
            return resolved_profile
    return None


def _equipped_armor_profiles(
    equipment_catalog: list[dict[str, Any]],
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (dict(item or {}), profile)
        for item in list(equipment_catalog or [])
        if bool(dict(item or {}).get("is_equipped"))
        if (profile := _resolve_armor_profile(dict(item or {}), item_catalog)) is not None
    ]


def _resolved_armor_profiles(
    equipment_catalog: list[dict[str, Any]],
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (dict(item or {}), profile)
        for item in list(equipment_catalog or [])
        if (profile := _resolve_armor_profile(dict(item or {}), item_catalog)) is not None
    ]


def _character_has_named_feature(features: list[dict[str, Any]] | None, *feature_values: str) -> bool:
    normalized_targets = {normalize_lookup(value) for value in feature_values if str(value or "").strip()}
    for feature in list(features or []):
        systems_ref = dict(feature.get("systems_ref") or {})
        candidates = (
            str(feature.get("name") or "").strip(),
            str(systems_ref.get("title") or "").strip(),
            str(systems_ref.get("slug") or "").strip(),
        )
        if any(normalize_lookup(candidate) in normalized_targets for candidate in candidates if candidate):
            return True
    return False


def _derive_defensive_state_from_character_inputs(
    *,
    equipment_catalog: list[dict[str, Any]],
    features: list[dict[str, Any]] | None,
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    support_flags = _collect_defensive_support_flags(features)
    equipped_profiles = _equipped_armor_profiles(equipment_catalog, item_catalog=item_catalog)
    armor_profiles = [
        (item, profile)
        for item, profile in equipped_profiles
        if not bool(profile.get("is_shield"))
    ]
    shield_profiles = [
        (item, profile)
        for item, profile in equipped_profiles
        if bool(profile.get("is_shield"))
    ]
    shield_bonus = max(
        (
            int(profile.get("base_ac") or 0) + int(profile.get("bonus_ac") or 0)
            for _, profile in shield_profiles
        ),
        default=0,
    )
    raw_stealth_disadvantage = any(bool(profile.get("stealth_disadvantage")) for _, profile in armor_profiles)
    stealth_disadvantage = any(
        bool(profile.get("stealth_disadvantage"))
        and not (
            support_flags.get("medium_armor_master")
            and str(profile.get("armor_category") or "").strip().lower() == "medium"
        )
        for _, profile in armor_profiles
    )
    armor_state = {
        "equipped_armor_names": [
            str(item.get("name") or profile.get("title") or "").strip()
            for item, profile in armor_profiles
            if str(item.get("name") or profile.get("title") or "").strip()
        ],
        "equipped_armor_categories": _dedupe_preserve_order(
            [
                str(profile.get("armor_category") or "").strip().lower()
                for _, profile in armor_profiles
                if str(profile.get("armor_category") or "").strip()
            ]
        ),
        "shield_names": [
            str(item.get("name") or profile.get("title") or "").strip()
            for item, profile in shield_profiles
            if str(item.get("name") or profile.get("title") or "").strip()
        ],
        "wearing_shield": bool(shield_profiles),
        "shield_bonus": shield_bonus,
        "stealth_disadvantage": stealth_disadvantage,
        "stealth_disadvantage_suppressed": raw_stealth_disadvantage and not stealth_disadvantage,
    }
    rules: list[dict[str, Any]] = []
    if support_flags.get("medium_armor_master"):
        active = "medium" in set(armor_state.get("equipped_armor_categories") or [])
        rules.append(
            {
                "id": "feat:phb-feat-medium-armor-master",
                "title": "Medium Armor Master",
                "active": active,
                "condition": "Applies only while wearing medium armor.",
                "inactive_reason": "" if active else "Equip medium armor to activate this defensive rule.",
                "effects": [
                    {
                        "kind": "armor_state",
                        "label": "Armor state",
                        "summary": "Medium armor can add up to +3 Dexterity to Armor Class and does not impose Stealth disadvantage.",
                    }
                ],
            }
        )
    if support_flags.get("heavy_armor_master"):
        active = "heavy" in set(armor_state.get("equipped_armor_categories") or [])
        rules.append(
            {
                "id": "feat:phb-feat-heavy-armor-master",
                "title": "Heavy Armor Master",
                "active": active,
                "condition": "Applies only while wearing heavy armor.",
                "inactive_reason": "" if active else "Equip heavy armor to activate this defensive rule.",
                "effects": [
                    {
                        "kind": "damage_mitigation",
                        "label": "Mitigation",
                        "summary": "Reduce nonmagical bludgeoning, piercing, and slashing damage from weapons by 3.",
                    }
                ],
            }
        )
    if support_flags.get("mage_slayer"):
        rules.append(
            {
                "id": "feat:phb-feat-mage-slayer",
                "title": "Mage Slayer",
                "active": True,
                "condition": "Applies against spells cast by creatures within 5 feet of you.",
                "inactive_reason": "",
                "effects": [
                    {
                        "kind": "saving_throw",
                        "label": "Spell saves",
                        "summary": "You have advantage on saving throws against spells cast by creatures within 5 feet of you.",
                    }
                ],
            }
        )
    if support_flags.get("shield_master"):
        active = bool(armor_state.get("wearing_shield"))
        shield_bonus_value = int(armor_state.get("shield_bonus") or 0)
        shield_bonus_text = (
            f"{shield_bonus_value:+d}"
            if shield_bonus_value
            else "your shield's AC bonus"
        )
        rules.append(
            {
                "id": "feat:phb-feat-shield-master",
                "title": "Shield Master",
                "active": active,
                "condition": "Applies only while a shield is equipped and you are not incapacitated.",
                "inactive_reason": "" if active else "Equip a shield to activate these defensive rules.",
                "effects": [
                    {
                        "kind": "saving_throw",
                        "label": "Dex saves",
                        "summary": f"Add {shield_bonus_text} to Dexterity saves against spells or other harmful effects that target only you.",
                    },
                    {
                        "kind": "reaction",
                        "label": "Reaction",
                        "summary": "If an effect lets you make a Dexterity save for half damage, you can use your reaction to take no damage on a success.",
                    },
                ],
            }
        )
    for item, profile in _resolved_armor_profiles(equipment_catalog, item_catalog=item_catalog):
        if not item_has_active_infusion(item, ENHANCED_DEFENSE_INFUSION_KEY):
            continue
        item_name = str(item.get("name") or profile.get("title") or "Infused item").strip()
        is_equipped = bool(item.get("is_equipped"))
        rules.append(
            {
                "id": f"artificer-infusion:enhanced-defense:{slugify(item_name)}",
                "title": "Enhanced Defense",
                "active": is_equipped,
                "condition": "Applies while the infused armor or shield is equipped.",
                "inactive_reason": "" if is_equipped else "Equip the infused armor or shield to apply this Armor Class bonus.",
                "effects": [
                    {
                        "kind": "armor_class",
                        "label": item_name,
                        "summary": f"{item_name} grants a +1 bonus to Armor Class while infused by Enhanced Defense.",
                    }
                ],
            }
        )
    for item_effect_entry in _active_item_effect_entries(
        equipment_catalog,
        item_catalog=item_catalog,
    ):
        for rule_payload in list(item_effect_entry.get("defensive_rules") or []):
            rule = dict(rule_payload or {})
            effects = [
                dict(effect or {})
                for effect in list(rule.get("effects") or [])
                if isinstance(effect, dict)
            ]
            if not effects:
                continue
            rules.append(
                {
                    "id": str(rule.get("id") or f"item:{slugify(str(item_effect_entry.get('item_name') or 'rule'))}").strip(),
                    "title": str(rule.get("title") or item_effect_entry.get("item_name") or "Item rule").strip() or "Item rule",
                    "active": True,
                    "condition": str(rule.get("condition") or "").strip(),
                    "inactive_reason": "",
                    "effects": effects,
                }
            )
    rules.extend(_structured_defensive_rules_from_features(features))
    return {
        "armor_state": armor_state,
        "rules": rules,
    }


def _weapon_attack_ability_key(
    profile: dict[str, Any],
    ability_scores: dict[str, int],
) -> str:
    if str(profile.get("type") or "").strip().upper() == "R":
        return "dex"
    if "F" in set(profile.get("properties") or []):
        str_score = int(ability_scores.get("str", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        dex_score = int(ability_scores.get("dex", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        return "dex" if dex_score > str_score else "str"
    return "str"


def _is_proficient_with_weapon(
    profile: dict[str, Any],
    weapon_proficiencies: list[str],
    attack_name: str,
) -> bool:
    normalized_proficiencies: set[str] = set()
    for value in weapon_proficiencies:
        normalized_proficiencies.update(_weapon_proficiency_name_candidates(value))
    normalized_attack_names = _weapon_proficiency_name_candidates(attack_name)
    normalized_attack_names.update(_weapon_proficiency_name_candidates(profile.get("title")))
    weapon_category = str(profile.get("weapon_category") or "").strip().lower()
    if normalized_attack_names & normalized_proficiencies:
        return True
    if weapon_category == "simple" and normalize_lookup("Simple Weapons") in normalized_proficiencies:
        return True
    if weapon_category == "martial" and normalize_lookup("Martial Weapons") in normalized_proficiencies:
        return True
    if _weapon_uses_firearm_proficiency(profile, attack_name=attack_name):
        return normalize_lookup("Firearms") in normalized_proficiencies
    return False


def _weapon_proficiency_name_candidates(value: Any) -> set[str]:
    base_name, _parsed_bonus = _split_magic_item_name(value)
    candidates: set[str] = set()
    for raw_candidate in (value, base_name):
        for candidate in _merge_name_candidates(raw_candidate):
            if candidate:
                candidates.add(candidate)
            candidates.update(_singularize_lookup_variants(candidate))
    return candidates


def _singularize_lookup_variants(value: Any) -> set[str]:
    normalized = normalize_lookup(value)
    if not normalized:
        return set()
    variants = {normalized}
    if normalized.endswith("ves") and len(normalized) > 3:
        stem = normalized[:-3]
        variants.add(f"{stem}f")
        variants.add(f"{stem}fe")
    if normalized.endswith("ies") and len(normalized) > 3:
        variants.add(f"{normalized[:-3]}y")
    if normalized.endswith("es") and len(normalized) > 2:
        variants.add(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 1:
        variants.add(normalized[:-1])
    return {candidate for candidate in variants if candidate}


def _weapon_uses_firearm_proficiency(profile: dict[str, Any], *, attack_name: str) -> bool:
    weapon_category = str(profile.get("weapon_category") or "").strip().lower()
    if weapon_category == "firearm":
        return True
    candidate_values = [
        str(profile.get("title") or "").strip(),
        str(attack_name or "").strip(),
    ]
    return any(
        normalize_lookup(value)
        in {
            normalize_lookup("Pistol"),
            normalize_lookup("Musket"),
            normalize_lookup("Pepperbox"),
            normalize_lookup("Blunderbuss"),
            normalize_lookup("Firearm"),
        }
        for value in candidate_values
        if str(value or "").strip()
    )


def _has_fighting_style(selected_choices: dict[str, list[str]], *style_values: str) -> bool:
    normalized_targets = {normalize_lookup(value) for value in style_values if str(value or "").strip()}
    for values in selected_choices.values():
        for value in values:
            if normalize_lookup(value) in normalized_targets:
                return True
    return False


def _qualifies_for_dueling(
    context: dict[str, Any],
    *,
    off_hand_context: dict[str, Any] | None,
) -> bool:
    profile = dict(context.get("profile") or {})
    properties = set(profile.get("properties") or [])
    if str(profile.get("type") or "").strip().upper() != "M":
        return False
    if "2H" in properties:
        return False
    if off_hand_context is not None:
        return False
    return True


def _supports_thrown_attack_variant(profile: dict[str, Any]) -> bool:
    properties = set(profile.get("properties") or [])
    return (
        str(profile.get("type") or "").strip().upper() == "M"
        and "T" in properties
        and bool(str(profile.get("range") or "").strip())
    )


def _supports_versatile_two_handed_attack(
    profile: dict[str, Any],
    *,
    has_shield: bool,
    off_hand_context: dict[str, Any] | None,
) -> bool:
    properties = set(profile.get("properties") or [])
    return (
        str(profile.get("type") or "").strip().upper() == "M"
        and "V" in properties
        and bool(str(profile.get("versatile_damage") or "").strip())
        and not has_shield
        and off_hand_context is None
    )


def _is_shield_item(item: dict[str, Any]) -> bool:
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
        str(systems_ref.get("slug") or "").strip(),
    ]
    return any(normalize_lookup(value) in {"shield", "phb item shield"} for value in candidate_values if value)


def _weapon_attack_category(profile: dict[str, Any]) -> str:
    return "ranged weapon" if str(profile.get("type") or "").strip().upper() == "R" else "melee weapon"


def _format_weapon_damage(profile: dict[str, Any], damage_bonus: int, *, extra_damage: str | None = None) -> str:
    base_damage = str(profile.get("damage") or "").strip()
    if not base_damage:
        return "--"
    parts = [base_damage]
    if str(extra_damage or "").strip():
        parts.append(str(extra_damage).strip())
    damage_text = "+".join(parts)
    bonus_text = ""
    if damage_bonus > 0:
        bonus_text = f"+{damage_bonus}"
    elif damage_bonus < 0:
        bonus_text = str(damage_bonus)
    damage_type = DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), "").strip()
    if damage_type:
        return f"{damage_text}{bonus_text} {damage_type}"
    return f"{damage_text}{bonus_text}"


def _build_unarmed_attack_payload(
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    index: int,
) -> dict[str, Any]:
    strength_modifier = _ability_modifier(ability_scores.get("str", DEFAULT_ABILITY_SCORE))
    damage_bonus = strength_modifier
    damage = "1d4"
    if damage_bonus > 0:
        damage = f"{damage}+{damage_bonus}"
    elif damage_bonus < 0:
        damage = f"{damage}{damage_bonus}"
    return {
        "id": f"unarmed-strike-{index}",
        "name": "Unarmed Strike",
        "category": "melee weapon",
        "attack_bonus": proficiency_bonus + strength_modifier,
        "damage": f"{damage} bludgeoning",
        "damage_type": "Bludgeoning",
        "notes": "Tavern Brawler enhanced unarmed strike.",
        "systems_ref": None,
    }


def _build_special_attack_payload(
    *,
    name: str,
    category: str,
    notes: str,
    index: int,
    mode_key: str = "",
    equipment_refs: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": f"{slugify(name)}-{index}",
        "name": str(name or "").strip(),
        "category": str(category or "").strip(),
        "attack_bonus": None,
        "damage": "",
        "damage_type": "",
        "notes": str(notes or "").strip(),
    }
    clean_mode_key = _normalize_attack_mode_key(mode_key)
    if clean_mode_key:
        payload["mode_key"] = clean_mode_key
    normalized_refs = _normalize_attack_equipment_refs(equipment_refs)
    if normalized_refs:
        payload["equipment_refs"] = normalized_refs
    return payload


def _build_weapon_attack_notes(
    profile: dict[str, Any],
    *,
    bonus_action: bool = False,
    extra_notes: list[str] | None = None,
    great_weapon_fighting: bool = False,
    has_shield: bool = False,
    ignore_loading: bool = False,
    off_hand_context: dict[str, Any] | None = None,
    show_range: bool = True,
    show_versatile: bool = True,
    wielded_two_handed: bool = False,
) -> str:
    properties = set(profile.get("properties") or [])
    notes: list[str] = []
    if "A" in properties:
        notes.append("Ammunition")
    if "LD" in properties and not ignore_loading:
        notes.append("loading")
    attack_range = str(profile.get("range") or "").strip()
    if show_range and attack_range:
        notes.append(f"range {attack_range}")
    if show_versatile and "V" in properties and str(profile.get("versatile_damage") or "").strip():
        notes.append(f"Versatile ({str(profile.get('versatile_damage') or '').strip()})")
    if great_weapon_fighting and ("2H" in properties or wielded_two_handed):
        notes.append("Great Weapon Fighting (reroll 1s and 2s)")
    if bonus_action:
        notes.append("Bonus action")
    for note in list(extra_notes or []):
        note_text = str(note or "").strip().rstrip(".")
        if note_text:
            notes.append(note_text)
    if not notes:
        return ""
    return ", ".join(notes) + "."


def _normalize_attack_payloads(
    attack_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_attacks: list[dict[str, Any]] = []
    index_by_key: dict[tuple[Any, ...], int] = {}
    for attack_payload in list(attack_payloads or []):
        payload = dict(attack_payload or {})
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_attacks) + 1}"
        payload["category"] = str(payload.get("category") or "").strip()
        payload["damage"] = str(payload.get("damage") or "").strip()
        payload["damage_type"] = str(payload.get("damage_type") or "").strip()
        payload["notes"] = str(payload.get("notes") or "").strip()
        inferred_mode_key = _infer_attack_mode_key_from_payload(payload)
        if inferred_mode_key:
            payload["mode_key"] = inferred_mode_key
        else:
            payload.pop("mode_key", None)
        normalized_variant_label = _normalize_attack_variant_label(
            raw_variant_label=payload.get("variant_label"),
            mode_key=inferred_mode_key,
            attack_name=name,
            notes=payload.get("notes"),
        )
        if normalized_variant_label:
            payload["variant_label"] = normalized_variant_label
        else:
            payload.pop("variant_label", None)
        attack_bonus = payload.get("attack_bonus")
        if attack_bonus in {"", None}:
            payload["attack_bonus"] = None
        else:
            try:
                payload["attack_bonus"] = int(attack_bonus)
            except (TypeError, ValueError):
                pass
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        equipment_refs = _normalize_attack_equipment_refs(
            payload.get("equipment_refs"),
            fallback=payload.get("equipment_ref"),
        )
        if equipment_refs:
            payload["equipment_refs"] = equipment_refs
        else:
            payload.pop("equipment_refs", None)
        payload.pop("equipment_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        normalized_damage = _normalize_merge_text(payload.get("damage"))
        normalized_damage_type = _normalize_merge_text(payload.get("damage_type"))
        normalized_notes = _normalize_merge_text(payload.get("notes"))
        normalized_category = _normalize_merge_text(payload.get("category"))
        normalized_mode_key = str(payload.get("mode_key") or "").strip()
        normalized_page_identity = _extract_campaign_page_ref(normalized_page_ref)
        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        equipment_identity_keys = [
            f"equipment:{equipment_ref}"
            for equipment_ref in list(equipment_refs or [])
            if str(equipment_ref or "").strip()
        ]
        merge_key_tail = (
            payload.get("attack_bonus"),
            normalized_damage,
            normalized_damage_type,
            normalized_notes,
            normalized_category,
            normalized_mode_key,
            normalized_page_identity,
        )
        candidate_keys = []
        if explicit_identity:
            candidate_keys.append((explicit_identity, *merge_key_tail))
        candidate_keys.extend((equipment_identity, *merge_key_tail) for equipment_identity in equipment_identity_keys)
        candidate_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(name)
        )
        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if (candidate_key[0].startswith("name:") or candidate_key[0].startswith("equipment:")) and explicit_identity:
                existing_payload = normalized_attacks[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break
        if existing_index is None:
            existing_index = len(normalized_attacks)
            normalized_attacks.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload = normalized_attacks[existing_index]
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if not existing_payload.get("mode_key") and payload.get("mode_key"):
            existing_payload["mode_key"] = str(payload.get("mode_key") or "").strip()
        if not existing_payload.get("variant_label") and payload.get("variant_label"):
            existing_payload["variant_label"] = str(payload.get("variant_label") or "").strip()
        merged_equipment_refs = _normalize_attack_equipment_refs(
            [
                *list(existing_payload.get("equipment_refs") or []),
                *list(payload.get("equipment_refs") or []),
            ]
        )
        if merged_equipment_refs:
            existing_payload["equipment_refs"] = merged_equipment_refs
        updated_mode_key = _infer_attack_mode_key_from_payload(existing_payload)
        if updated_mode_key:
            existing_payload["mode_key"] = updated_mode_key
        else:
            existing_payload.pop("mode_key", None)
        updated_variant_label = _normalize_attack_variant_label(
            raw_variant_label=existing_payload.get("variant_label"),
            mode_key=updated_mode_key,
            attack_name=existing_payload.get("name"),
            notes=existing_payload.get("notes"),
        )
        if updated_variant_label:
            existing_payload["variant_label"] = updated_variant_label
        else:
            existing_payload.pop("variant_label", None)
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        updated_merge_key_tail = (
            existing_payload.get("attack_bonus"),
            _normalize_merge_text(existing_payload.get("damage")),
            _normalize_merge_text(existing_payload.get("damage_type")),
            _normalize_merge_text(existing_payload.get("notes")),
            _normalize_merge_text(existing_payload.get("category")),
            str(existing_payload.get("mode_key") or "").strip(),
            _extract_campaign_page_ref(existing_payload.get("page_ref")),
        )
        updated_keys = []
        if updated_explicit_identity:
            updated_keys.append((updated_explicit_identity, *updated_merge_key_tail))
        updated_keys.extend(
            (f"equipment:{equipment_ref}", *updated_merge_key_tail)
            for equipment_ref in list(existing_payload.get("equipment_refs") or [])
            if str(equipment_ref or "").strip()
        )
        updated_keys.extend(
            (f"name:{candidate}", *updated_merge_key_tail)
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_attacks


def _normalize_attack_equipment_refs(
    raw_refs: Any,
    *,
    fallback: Any = None,
) -> list[str]:
    values = raw_refs
    if values is None or values == "" or values == [] or values == ():
        values = fallback
    if values is None or values == "" or values == [] or values == ():
        return []
    if isinstance(values, (list, tuple, set)):
        candidates = list(values)
    else:
        candidates = [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean_value = str(candidate or "").strip()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        normalized.append(clean_value)
    return normalized


def _attack_matches_equipment_catalog(
    attack_payload: dict[str, Any],
    *,
    equipment_catalog: list[dict[str, Any]] | None,
) -> bool:
    linked_equipment_refs = set(
        _normalize_attack_equipment_refs(
            attack_payload.get("equipment_refs"),
            fallback=attack_payload.get("equipment_ref"),
        )
    )
    attack_systems_slug = _systems_ref_slug(attack_payload.get("systems_ref"))
    attack_page_ref = _normalize_page_ref_payload(attack_payload.get("page_ref"))
    attack_page_slug = _extract_campaign_page_ref(attack_page_ref)
    attack_name_candidates = set(_merge_name_candidates(attack_payload.get("name")))

    for equipment_payload in list(equipment_catalog or []):
        equipment_item = dict(equipment_payload or {})
        equipment_id = str(equipment_item.get("id") or "").strip()
        if linked_equipment_refs and equipment_id and equipment_id in linked_equipment_refs:
            return True

        equipment_systems_slug = _systems_ref_slug(equipment_item.get("systems_ref"))
        if attack_systems_slug and attack_systems_slug == equipment_systems_slug:
            return True

        equipment_page_ref = _normalize_page_ref_payload(equipment_item.get("page_ref"))
        equipment_page_slug = _extract_campaign_page_ref(equipment_page_ref)
        if attack_page_slug and attack_page_slug == equipment_page_slug:
            return True

        equipment_name_candidates: set[str] = set()
        for candidate_value in (
            equipment_item.get("name"),
            dict(equipment_item.get("systems_ref") or {}).get("title"),
            dict(equipment_page_ref or {}).get("title"),
        ):
            equipment_name_candidates.update(_merge_name_candidates(candidate_value))
        if attack_name_candidates and equipment_name_candidates and attack_name_candidates.intersection(
            equipment_name_candidates
        ):
            return True
    return False


def _attack_override_match_keys(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    normalized_mode_key = _infer_attack_mode_key_from_payload(payload)
    keys: list[tuple[str, str, str]] = []
    for equipment_ref in _normalize_attack_equipment_refs(
        payload.get("equipment_refs"),
        fallback=payload.get("equipment_ref"),
    ):
        keys.append(("equipment", equipment_ref, normalized_mode_key))
    explicit_identity = _normalize_explicit_link_identity(
        systems_ref=dict(payload.get("systems_ref") or {}),
        page_ref=_normalize_page_ref_payload(payload.get("page_ref")),
    )
    if explicit_identity:
        keys.append(("explicit", explicit_identity, normalized_mode_key))
    for candidate in _merge_name_candidates(payload.get("name")):
        keys.append(("name", candidate, normalized_mode_key))
    return keys


def _merge_recalculated_attack_overrides(
    recalculated_attacks: list[dict[str, Any]],
    existing_attacks: list[dict[str, Any]],
    *,
    equipment_catalog: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    existing_lookup: dict[tuple[str, str, str], tuple[int, dict[str, Any]]] = {}
    for index, attack_payload in enumerate(list(existing_attacks or [])):
        payload = dict(attack_payload or {})
        for key in _attack_override_match_keys(payload):
            existing_lookup.setdefault(key, (index, payload))

    matched_existing_indexes: set[int] = set()
    merged: list[dict[str, Any]] = []
    for attack_payload in list(recalculated_attacks or []):
        payload = dict(attack_payload or {})
        matched_existing = None
        for key in _attack_override_match_keys(payload):
            matched_existing = existing_lookup.get(key)
            if matched_existing is not None:
                break
        if matched_existing is not None:
            existing_index, existing_payload = matched_existing
            matched_existing_indexes.add(existing_index)
            existing_page_ref = _normalize_page_ref_payload(existing_payload.get("page_ref"))
            if existing_page_ref and not payload.get("page_ref"):
                payload["page_ref"] = existing_page_ref
            if dict(existing_payload.get("systems_ref") or {}) and not payload.get("systems_ref") and not payload.get("page_ref"):
                payload["systems_ref"] = dict(existing_payload.get("systems_ref") or {})
            merged_equipment_refs = _normalize_attack_equipment_refs(
                [
                    *list(payload.get("equipment_refs") or []),
                    *_normalize_attack_equipment_refs(
                        existing_payload.get("equipment_refs"),
                        fallback=existing_payload.get("equipment_ref"),
                    ),
                ]
            )
            if merged_equipment_refs:
                payload["equipment_refs"] = merged_equipment_refs
        merged.append(payload)

    for index, attack_payload in enumerate(list(existing_attacks or [])):
        if index in matched_existing_indexes:
            continue
        merged.append(dict(attack_payload or {}))
    return merged


def _normalize_equipment_payloads(
    equipment_payloads: list[dict[str, Any]] | None,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_equipment: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str, str, bool], int] = {}
    for equipment_payload in list(equipment_payloads or []):
        payload = dict(equipment_payload or {})
        currency = dict(payload.get("currency") or {})
        is_currency_only = bool(payload.get("is_currency_only"))
        name = str(payload.get("name") or "").strip() or (_format_currency_seed(currency) if currency else "")
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_equipment) + 1}"
        quantity = payload.get("default_quantity", payload.get("quantity"))
        payload["default_quantity"] = _normalize_equipment_quantity(quantity, fallback=1 if name else 0)
        payload["weight"] = str(payload.get("weight") or "").strip()
        payload["notes"] = str(payload.get("notes") or "").strip()
        payload["source_kind"] = str(payload.get("source_kind") or "").strip()
        payload["equipped_state_explicit"] = bool(payload.get("equipped_state_explicit")) or "is_equipped" in payload
        payload["is_equipped"] = bool(payload.get("is_equipped", False))
        payload["is_attuned"] = bool(payload.get("is_attuned", False))
        payload["charges_current"] = payload.get("charges_current")
        payload["charges_max"] = payload.get("charges_max")
        payload["tags"] = [str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()]
        systems_ref, normalized_page_ref = _recover_equipment_link_payloads(
            payload,
            item_catalog=item_catalog,
        )
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        equipment_support = describe_equipment_state_support(
            payload,
            item_catalog=item_catalog,
        )
        explicit_wield_mode = explicit_weapon_wield_mode(
            payload,
            item_catalog=item_catalog,
            support=equipment_support,
        )
        if explicit_wield_mode:
            payload["weapon_wield_mode"] = explicit_wield_mode
            payload["is_equipped"] = True
        else:
            payload.pop("weapon_wield_mode", None)
        campaign_option = dict(payload.get("campaign_option") or {})
        if campaign_option:
            payload["campaign_option"] = campaign_option
        else:
            payload.pop("campaign_option", None)
        payload["currency"] = currency
        payload["is_currency_only"] = is_currency_only
        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        merge_key_tail = (
            _extract_campaign_page_ref(normalized_page_ref),
            _normalize_merge_text(payload.get("notes")),
            _normalize_merge_text(payload.get("weight")),
            is_currency_only,
        )
        candidate_keys = []
        if explicit_identity:
            candidate_keys.append((explicit_identity, *merge_key_tail))
        candidate_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(name)
        )
        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if candidate_key[0].startswith("name:") and explicit_identity:
                existing_payload = normalized_equipment[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break
        if existing_index is None:
            existing_index = len(normalized_equipment)
            normalized_equipment.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload = normalized_equipment[existing_index]
        existing_payload["default_quantity"] = int(existing_payload.get("default_quantity") or 0) + int(
            payload.get("default_quantity") or 0
        )
        existing_payload["currency"] = _merge_currency_seed(
            dict(existing_payload.get("currency") or {}),
            dict(payload.get("currency") or {}),
        )
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if not existing_payload.get("source_kind") and payload.get("source_kind"):
            existing_payload["source_kind"] = str(payload.get("source_kind") or "").strip()
        if not existing_payload.get("campaign_option") and payload.get("campaign_option"):
            existing_payload["campaign_option"] = dict(payload.get("campaign_option") or {})
        existing_payload["equipped_state_explicit"] = bool(
            existing_payload.get("equipped_state_explicit")
        ) or bool(payload.get("equipped_state_explicit"))
        existing_payload["is_equipped"] = bool(existing_payload.get("is_equipped", False)) or bool(
            payload.get("is_equipped", False)
        )
        if not existing_payload.get("weapon_wield_mode") and payload.get("weapon_wield_mode"):
            existing_payload["weapon_wield_mode"] = str(payload.get("weapon_wield_mode") or "").strip()
            existing_payload["is_equipped"] = True
        existing_payload["is_attuned"] = bool(existing_payload.get("is_attuned", False)) or bool(
            payload.get("is_attuned", False)
        )
        if existing_payload.get("charges_current") in ("", None) and payload.get("charges_current") not in ("", None):
            existing_payload["charges_current"] = payload.get("charges_current")
        if existing_payload.get("charges_max") in ("", None) and payload.get("charges_max") not in ("", None):
            existing_payload["charges_max"] = payload.get("charges_max")
        existing_payload["tags"] = _dedupe_preserve_order(
            list(existing_payload.get("tags") or []) + list(payload.get("tags") or [])
        )
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        updated_keys = []
        if updated_explicit_identity:
            updated_keys.append((updated_explicit_identity, *merge_key_tail))
        updated_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_equipment


def _recover_equipment_link_payloads(
    payload: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None,
) -> tuple[dict[str, Any], Any]:
    systems_ref = dict(payload.get("systems_ref") or {})
    normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
    resolved_page_ref = _extract_campaign_page_ref(normalized_page_ref)
    campaign_item_support = _resolve_campaign_item_page_support(payload, item_catalog)
    if isinstance(campaign_item_support, dict):
        support_page_ref = str(campaign_item_support.get("page_ref") or "").strip()
        support_title = str(campaign_item_support.get("title") or payload.get("name") or "").strip()
        if support_page_ref and (not resolved_page_ref or resolved_page_ref == support_page_ref):
            normalized_page_ref = (
                {
                    "slug": support_page_ref,
                    "title": support_title,
                }
                if support_title
                else support_page_ref
            )
            resolved_page_ref = support_page_ref
    if not systems_ref and not resolved_page_ref:
        recovered_entry = _resolve_item_entry(payload, item_catalog)
        recovered_systems_ref = _systems_ref_from_entry(recovered_entry)
        if recovered_systems_ref:
            systems_ref = recovered_systems_ref
    return systems_ref, normalized_page_ref


def _normalize_page_ref_payload(page_ref: Any) -> Any:
    if isinstance(page_ref, dict):
        return dict(page_ref)
    clean_page_ref = str(page_ref or "").strip()
    if clean_page_ref:
        return clean_page_ref
    return None


def _normalize_explicit_link_identity(*, systems_ref: dict[str, Any] | None, page_ref: Any) -> str:
    page_identity = _extract_campaign_page_ref(page_ref)
    if page_identity:
        return f"page:{normalize_lookup(page_identity)}"
    systems_payload = dict(systems_ref or {})
    systems_slug = str(systems_payload.get("slug") or "").strip()
    if systems_slug:
        return f"systems:{normalize_lookup(systems_slug)}"
    systems_entry_type = normalize_lookup(str(systems_payload.get("entry_type") or "").strip())
    systems_source_id = normalize_lookup(str(systems_payload.get("source_id") or "").strip())
    systems_title = str(systems_payload.get("title") or "").strip()
    if systems_title:
        qualifier = ":".join(part for part in (systems_entry_type, systems_source_id) if part)
        if qualifier:
            return f"systems-title:{qualifier}:{normalize_lookup(systems_title)}"
        return f"systems-title:{normalize_lookup(systems_title)}"
    return ""


def _normalize_merge_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_equipment_quantity(value: Any, *, fallback: int) -> int:
    if value in {"", None}:
        return max(int(fallback or 0), 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return max(int(fallback or 0), 0)


def _humanize_item_reference(value: str) -> str:
    base_value = str(value or "").split("|", 1)[0].strip()
    if not base_value:
        return ""
    if any(character.isupper() for character in base_value):
        return base_value
    return _humanize_words(base_value)


def _merge_currency_seed(existing: dict[str, int], new: dict[str, int]) -> dict[str, int]:
    return {
        denomination: int(existing.get(denomination) or 0) + int(new.get(denomination) or 0)
        for denomination in ("cp", "sp", "ep", "gp", "pp")
    }


def _format_currency_seed(currency: dict[str, int]) -> str:
    parts = [
        f"{int(currency.get(denomination) or 0)} {denomination}"
        for denomination in ("pp", "gp", "ep", "sp", "cp")
        if int(currency.get(denomination) or 0) > 0
    ]
    return ", ".join(parts)


def _systems_ref_from_entry(entry: SystemsEntryRecord | None) -> dict[str, str] | None:
    if entry is None:
        return None
    return {
        "entry_key": entry.entry_key,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "slug": entry.slug,
        "source_id": entry.source_id,
    }


def _ability_modifier(score: int) -> int:
    return (int(score) - 10) // 2


def _humanize_words(value: str) -> str:
    cleaned = str(value or "").replace("_", " ").strip()
    if not cleaned:
        return ""
    return " ".join(part.capitalize() for part in cleaned.split())


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        normalized = normalize_lookup(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped
