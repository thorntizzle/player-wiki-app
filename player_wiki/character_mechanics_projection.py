from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .character_builder import (
    ATTACK_MODE_WEAPON_OFF_HAND,
    ATTACK_MODE_WEAPON_TWO_HANDED,
    WEAPON_WIELD_MODE_OFF_HAND,
    WEAPON_WIELD_MODE_TWO_HANDED,
    CharacterBuildError,
    _attack_mode_components,
    _infer_attack_mode_key_from_payload,
    _spell_payload_is_always_prepared,
    _spell_payload_map_key,
    describe_equipment_state_support,
    explicit_weapon_wield_mode,
    normalize_definition_to_native_model,
    resolve_item_equipped_state,
)
from .campaign_item_mechanics import campaign_item_character_metadata, is_campaign_item_mechanics_metadata
from .character_service import merge_state_with_definition
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lanes_from_spellcasting
from .models import Campaign
from .repository import normalize_lookup
from .system_policy import is_xianxia_system
from .xianxia_character_model import (
    XIANXIA_DEFENSE_BASE,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    derive_xianxia_actions_per_turn,
    derive_xianxia_check_formula_strings,
    derive_xianxia_defense,
    derive_xianxia_difficulty_state_adjustments,
    derive_xianxia_effort_damage_strings,
    derive_xianxia_honor_interaction_reminders,
)
from .xianxia_systems_seed import XIANXIA_HOMEBREW_SOURCE_ID


ARCANE_ARMOR_STATE_KEY = "arcane_armor"
ARCANE_ARMOR_FEATURE_NAME = "arcane armor"
GUARDIAN_ARMOR_THUNDER_GAUNTLETS_NAME = "guardian armor: thunder gauntlets"
GUARDIAN_ARMOR_DEFENSIVE_FIELD_NAME = "guardian armor: defensive field"
XIANXIA_STANCE_RULE_ENTRY_KEY = f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|stance"
XIANXIA_STANCE_ACTIVATION_RULE_ENTRY_KEY = (
    f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|stance-activation-rules"
)
XIANXIA_AURA_ACTIVATION_RULE_ENTRY_KEY = (
    f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|aura-activation-rules"
)
XIANXIA_HONOR_RULE_ENTRY_KEY = f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|honor"
XIANXIA_SKILLS_RULE_ENTRY_KEY = f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|skills"
XIANXIA_RULE_TEXT_REFERENCE_SPECS = (
    ("Ranges and Distance", "ranges-and-distance"),
    ("Timing and Initiative", "timing-and-initiative"),
    ("Critical Hits", "critical-hits"),
    ("Sneak Attacks", "sneak-attacks"),
    ("Minions", "minions"),
    ("Companion Derivation", "companion-derivation"),
)
ATTACK_NAME_SUFFIX_PATTERN = re.compile(r"\s*\([^)]*\)\s*$")


def build_character_mechanics_projection(
    *,
    campaign: Campaign,
    definition: Any,
    state: dict[str, Any],
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    projected_definition = definition
    projected_state = deepcopy(state or {})
    projection_warnings: list[dict[str, str]] = []
    if systems_service is not None:
        try:
            projected_definition = normalize_definition_to_native_model(
                definition,
                systems_service=systems_service,
                campaign_page_records=campaign_page_records,
            )
            projected_state = merge_state_with_definition(projected_definition, projected_state)
        except (CharacterBuildError, TypeError, ValueError) as exc:
            projected_definition = definition
            projected_state = deepcopy(state or {})
            projection_warnings.append(
                {
                    "code": "read_time_projection_failed",
                    "message": str(exc) or exc.__class__.__name__,
                }
            )

    inventory_lookup = build_inventory_lookup(projected_state)
    equipment_catalog_lookup = build_equipment_catalog_lookup(projected_definition)
    arcane_armor_state = present_arcane_armor_state(
        projected_definition,
        projected_state,
        inventory_lookup=inventory_lookup,
        equipment_catalog_lookup=equipment_catalog_lookup,
    )
    is_xianxia_character = is_xianxia_system(projected_definition.system)
    xianxia_projection = (
        build_xianxia_mechanics_projection(
            campaign,
            projected_definition.xianxia,
            projected_state,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else {}
    )
    attack_visibility = project_attack_visibility(
        projected_definition,
        inventory_lookup=inventory_lookup,
        equipment_catalog_lookup=equipment_catalog_lookup,
        arcane_armor_state=arcane_armor_state,
    )
    visible_attacks = project_visible_attacks(
        attack_visibility,
        campaign_slug=campaign.slug,
    )
    attack_reminders = project_attack_reminders(
        dict(getattr(projected_definition, "stats", {}) or {}),
        visible_attacks,
    )
    defensive_rules = project_defensive_rules(dict(getattr(projected_definition, "stats", {}) or {}))
    item_use_actions = project_item_use_actions(
        campaign,
        projected_definition,
        projected_state,
        inventory_lookup=inventory_lookup,
        equipment_catalog_lookup=equipment_catalog_lookup,
        systems_service=systems_service,
    )

    return {
        "definition": projected_definition,
        "state": projected_state,
        "is_xianxia_character": is_xianxia_character,
        "inventory_lookup": inventory_lookup,
        "equipment_catalog_lookup": equipment_catalog_lookup,
        "arcane_armor_state": arcane_armor_state,
        "attack_visibility": attack_visibility,
        "visible_attacks": visible_attacks,
        "attack_reminders": attack_reminders,
        "defensive_rules": defensive_rules,
        "item_use_actions": item_use_actions,
        "projection_warnings": projection_warnings,
        "xianxia": xianxia_projection,
    }


def build_inventory_lookup(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        build_character_inventory_item_ref(item): dict(item or {})
        for item in list((state or {}).get("inventory") or [])
        if build_character_inventory_item_ref(item)
    }


def build_equipment_catalog_lookup(definition: Any) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): dict(item or {})
        for item in list(getattr(definition, "equipment_catalog", []) or [])
        if str(item.get("id") or "").strip()
    }


def build_character_inventory_item_ref(item: Any) -> str:
    payload = dict(item or {}) if isinstance(item, dict) else {}
    return str(payload.get("catalog_ref") or payload.get("id") or "").strip()


def project_spell_action_state(
    *,
    spell: dict[str, Any],
    row_payload: dict[str, Any],
    spell_level: int | None,
    mark: str,
    always_prepared: bool | None = None,
) -> dict[str, Any]:
    normalized_mark = normalize_lookup(mark)
    row_mode = str(row_payload.get("spell_mode") or "").strip()
    row_kind = str(row_payload.get("row_kind") or "class").strip() or "class"
    resolved_always_prepared = (
        bool(always_prepared)
        if always_prepared is not None
        else _spell_payload_is_always_prepared(dict(spell or {}))
    )
    is_cantrip = spell_level == 0 or "cantrip" in normalized_mark
    prepared_marked = bool(normalized_mark in {"p", "po"} or "prepared" in normalized_mark)
    is_prepared = bool(
        not is_cantrip
        and (
            resolved_always_prepared
            or prepared_marked
        )
    )
    in_spellbook = bool(not is_cantrip and "spellbook" in normalized_mark)
    is_fixed = bool(resolved_always_prepared or spell.get("is_bonus_known"))
    can_toggle_prepared = bool(
        row_kind == "class"
        and row_mode in {"prepared", "wizard"}
        and not is_cantrip
        and (row_mode != "wizard" or in_spellbook)
        and not resolved_always_prepared
    )
    can_remove = bool(
        not is_cantrip
        and (row_kind == "class" or row_mode == "ritual_book")
        and not is_fixed
        and row_mode != "prepared"
    )
    can_show_in_current_view = bool(
        is_cantrip
        or is_prepared
        or is_fixed
        or row_kind != "class"
        or row_mode in {"known", "ritual_book"}
        or row_mode not in {"prepared", "wizard"}
    )
    return {
        "spell_key": _spell_payload_map_key(dict(spell or {})),
        "is_cantrip": is_cantrip,
        "is_fixed": is_fixed,
        "is_prepared": is_prepared,
        "can_toggle_prepared": can_toggle_prepared,
        "can_show_in_current_view": can_show_in_current_view,
        "can_remove": can_remove,
    }


def _project_rule_effects(payload: dict[str, Any]) -> list[dict[str, str]]:
    effects = []
    for effect in list(payload.get("effects") or []):
        effect_payload = dict(effect or {})
        summary = str(effect_payload.get("summary") or "").strip()
        if not summary:
            continue
        effects.append(
            {
                "kind": str(effect_payload.get("kind") or "").strip(),
                "label": str(effect_payload.get("label") or "Rule").strip() or "Rule",
                "summary": summary,
            }
        )
    return effects


def _attack_matches_reminder_scope(attack: dict[str, Any], scope: dict[str, Any]) -> bool:
    categories = {
        normalize_lookup(value)
        for value in list(scope.get("categories") or [])
        if str(value or "").strip()
    }
    damage_types = {
        normalize_lookup(value)
        for value in list(scope.get("damage_types") or [])
        if str(value or "").strip()
    }
    if categories and normalize_lookup(attack.get("category")) not in categories:
        return False
    if damage_types and normalize_lookup(attack.get("damage_type")) not in damage_types:
        return False
    return True


def _metadata_requires_attunement_for_projection(metadata: dict[str, Any]) -> bool:
    raw_value = metadata.get("attunement")
    if raw_value in (None, "", [], {}):
        return False
    if isinstance(raw_value, bool):
        return raw_value
    return "attun" in str(raw_value or "").lower()


def _filter_item_action_slot_options(
    spell_slot_options: list[dict[str, Any]],
    slot_cost: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed_levels: set[int] = set()
    for value in list(slot_cost.get("allowed_levels") or []):
        try:
            level = int(value)
        except (TypeError, ValueError):
            continue
        if level > 0:
            allowed_levels.add(level)
    requested_lane = normalize_spell_slot_lane_id(slot_cost.get("slot_lane_id") or slot_cost.get("lane_id"))
    lane_kind = normalize_lookup(slot_cost.get("lane"))
    filtered_options: list[dict[str, Any]] = []
    for option in list(spell_slot_options or []):
        level = int(dict(option or {}).get("level") or 0)
        lane_id = normalize_spell_slot_lane_id(dict(option or {}).get("slot_lane_id"))
        if allowed_levels and level not in allowed_levels:
            continue
        if requested_lane and lane_id != requested_lane:
            continue
        if lane_kind and lane_kind not in {"spellcasting", "spell slots", "spell_slots"}:
            if normalize_lookup(lane_id) != lane_kind:
                continue
        filtered_options.append(dict(option or {}))
    return filtered_options


def _character_spell_save_dc(spellcasting: dict[str, Any]) -> int | None:
    for row in list(spellcasting.get("class_rows") or []):
        try:
            value = int(dict(row or {}).get("spell_save_dc") or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    try:
        value = int(spellcasting.get("spell_save_dc") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else None


def _support_state_label(value: Any) -> str:
    normalized = normalize_lookup(value)
    if normalized in {"modeled", "supported", "approved"}:
        return "Modeled"
    if normalized in {"needs implementation", "needs_implementation"}:
        return "Needs implementation"
    if normalized in {"manual review", "manual_review"}:
        return "Manual review"
    if normalized in {"reference only", "reference_only"}:
        return "Reference only"
    if normalized:
        return str(value or "").strip().replace("_", " ").title()
    return ""


def project_attack_visibility(
    definition: Any,
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
    arcane_armor_state: dict[str, Any],
) -> list[dict[str, Any]]:
    projected_attacks: list[dict[str, Any]] = []
    for attack in list(getattr(definition, "attacks", []) or []):
        attack_payload = dict(attack or {})
        attack_name = str(attack_payload.get("name") or "Attack")
        linked_item_refs = resolve_attack_linked_item_refs(
            attack_payload,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        attack_is_equipped = resolve_attack_equipped_state(
            attack_payload,
            linked_item_refs,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        hidden_reason = ""
        if (
            bool(arcane_armor_state.get("available"))
            and is_guardian_thunder_gauntlets_name(attack_name)
            and not bool(arcane_armor_state.get("thunder_gauntlets_available"))
        ):
            hidden_reason = "arcane_armor_unavailable"
        elif attack_is_equipped is False:
            hidden_reason = "linked_item_not_equipped"

        projected_attacks.append(
            {
                "attack": attack_payload,
                "name": attack_name,
                "linked_item_refs": linked_item_refs,
                "is_equipped": attack_is_equipped,
                "hidden": bool(hidden_reason),
                "hidden_reason": hidden_reason,
            }
        )
    return projected_attacks


def project_visible_attacks(
    attack_visibility: list[dict[str, Any]],
    *,
    campaign_slug: str = "",
) -> list[dict[str, Any]]:
    visible_attacks: list[dict[str, Any]] = []
    for projected_attack in list(attack_visibility or []):
        if bool(dict(projected_attack or {}).get("hidden")):
            continue
        attack = dict(dict(projected_attack or {}).get("attack") or {})
        if not attack:
            continue
        visible_attacks.append(
            {
                "name": str(attack.get("name") or "Attack").strip() or "Attack",
                "category": str(attack.get("category") or "").strip(),
                "damage_type": str(attack.get("damage_type") or "").strip(),
                "systems_ref": dict(attack.get("systems_ref") or {}),
                "page_ref": attack.get("page_ref"),
                "href": build_character_entry_href(
                    campaign_slug,
                    systems_ref=attack.get("systems_ref"),
                    page_ref=attack.get("page_ref"),
                ),
            }
        )
    return visible_attacks


def project_attack_reminders(stats: dict[str, Any], attacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reminder_state = dict(stats.get("attack_reminder_state") or {})
    reminders = []
    for rule in list(reminder_state.get("rules") or []):
        rule_payload = dict(rule or {})
        effects = _project_rule_effects(rule_payload)
        if not effects:
            continue
        scope = dict(rule_payload.get("attack_scope") or {})
        scope_label = str(scope.get("label") or "").strip()
        eligible_attacks = dedupe_values(
            attack.get("name")
            for attack in attacks
            if _attack_matches_reminder_scope(attack, scope)
        )
        availability_note = ""
        if scope_label and not eligible_attacks:
            availability_note = f"No visible attacks on this sheet currently match {scope_label.lower()}."
        reminders.append(
            {
                "title": str(rule_payload.get("title") or "Combat reminder").strip() or "Combat reminder",
                "status_label": "Linked attacks" if eligible_attacks else "Reminder only",
                "condition": str(rule_payload.get("condition") or "").strip(),
                "scope_label": scope_label,
                "eligible_attacks": eligible_attacks,
                "availability_note": availability_note,
                "effects": effects,
            }
        )
    return reminders


def project_defensive_rules(stats: dict[str, Any]) -> list[dict[str, Any]]:
    defensive_state = dict(stats.get("defensive_state") or {})
    defensive_rules = []
    for rule in list(defensive_state.get("rules") or []):
        rule_payload = dict(rule or {})
        effects = _project_rule_effects(rule_payload)
        if not effects:
            continue
        is_active = bool(rule_payload.get("active"))
        defensive_rules.append(
            {
                "title": str(rule_payload.get("title") or "Defensive rule").strip() or "Defensive rule",
                "is_active": is_active,
                "status_label": "Active" if is_active else "Inactive",
                "condition": str(rule_payload.get("condition") or "").strip(),
                "inactive_reason": str(rule_payload.get("inactive_reason") or "").strip(),
                "effects": effects,
            }
        )
    return defensive_rules


def project_item_use_actions(
    campaign: Campaign,
    definition: Any,
    state: dict[str, Any],
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
    systems_service: Any | None = None,
) -> list[dict[str, Any]]:
    spell_slot_options = project_spell_slot_options(
        dict(getattr(definition, "spellcasting", {}) or {}),
        state,
    )
    character_spell_save_dc = _character_spell_save_dc(
        dict(getattr(definition, "spellcasting", {}) or {})
    )
    actions: list[dict[str, Any]] = []
    for item_ref, inventory_item in inventory_lookup.items():
        equipment_item = dict(equipment_catalog_lookup.get(item_ref) or {})
        if not equipment_item:
            continue
        quantity = int(inventory_item.get("quantity") or equipment_item.get("default_quantity") or 0)
        if quantity <= 0:
            continue
        item_metadata = resolve_projected_item_metadata(
            campaign,
            equipment_item,
            systems_service=systems_service,
        )
        for raw_action in list(item_metadata.get("item_use_actions") or []):
            action_payload = dict(raw_action or {})
            projected_action = project_item_use_action(
                action_payload,
                item_ref=item_ref,
                item_name=str(inventory_item.get("name") or equipment_item.get("name") or "Item").strip() or "Item",
                inventory_item=inventory_item,
                equipment_item=equipment_item,
                requires_attunement=_metadata_requires_attunement_for_projection(item_metadata),
                spell_slot_options=spell_slot_options,
                character_spell_save_dc=character_spell_save_dc,
            )
            if projected_action is not None:
                actions.append(projected_action)
    return actions


def project_item_use_action(
    action_payload: dict[str, Any],
    *,
    item_ref: str,
    item_name: str,
    inventory_item: dict[str, Any],
    equipment_item: dict[str, Any],
    requires_attunement: bool,
    spell_slot_options: list[dict[str, Any]],
    character_spell_save_dc: int | None,
) -> dict[str, Any] | None:
    action_id = str(action_payload.get("id") or "").strip()
    if not action_id:
        return None
    kind = str(action_payload.get("kind") or "").strip()
    if kind != "spell_slot_item_attack":
        return None
    requires_equipped = bool(action_payload.get("requires_equipped", True))
    requires_attunement = bool(action_payload.get("requires_attunement", requires_attunement))
    is_equipped = bool(inventory_item.get("is_equipped") or equipment_item.get("is_equipped"))
    is_attuned = bool(inventory_item.get("is_attuned") or equipment_item.get("is_attuned"))
    enabled = True
    disabled_reason = ""
    if requires_equipped and not is_equipped:
        enabled = False
        disabled_reason = "Equip this item before using this action."
    elif requires_attunement and not is_attuned:
        enabled = False
        disabled_reason = "Attune this item before using this action."

    filtered_slot_options = _filter_item_action_slot_options(
        spell_slot_options,
        dict(action_payload.get("slot_cost") or {}),
    )
    if enabled and not any(int(option.get("available") or 0) > 0 for option in filtered_slot_options):
        enabled = False
        disabled_reason = "No matching spell slots are available."

    choices = project_item_action_choices(
        action_payload,
        character_spell_save_dc=character_spell_save_dc,
    )
    if enabled and not any(bool(choice.get("is_supported")) for choice in choices):
        enabled = False
        disabled_reason = "No modeled choices are available for this action."

    return {
        "id": action_id,
        "kind": kind,
        "label": str(action_payload.get("label") or "Use item").strip() or "Use item",
        "item_ref": item_ref,
        "item_name": item_name,
        "requires_equipped": requires_equipped,
        "is_equipped": is_equipped,
        "requires_attunement": requires_attunement,
        "is_attuned": is_attuned,
        "choices": choices,
        "slot_cost": dict(action_payload.get("slot_cost") or {}),
        "slot_options": filtered_slot_options,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
    }


def project_item_action_choices(
    action_payload: dict[str, Any],
    *,
    character_spell_save_dc: int | None,
) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    for raw_choice in list(action_payload.get("choices") or []):
        choice = dict(raw_choice or {})
        choice_id = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or choice_id).strip()
        if not choice_id or not label:
            continue
        support_state = str(choice.get("support_state") or choice.get("status") or "modeled").strip()
        is_supported = normalize_lookup(support_state) in {"modeled", "supported", "approved"}
        save_payload = dict(choice.get("save") or {})
        if str(save_payload.get("dc_source") or "").strip() == "character_spell_save_dc":
            save_payload["dc"] = character_spell_save_dc
            if character_spell_save_dc is not None:
                save_payload["label"] = f"{str(save_payload.get('ability') or '').upper()} save DC {character_spell_save_dc}".strip()
        choices.append(
            {
                "id": choice_id,
                "label": label,
                "support_state": support_state,
                "support_label": _support_state_label(support_state),
                "is_supported": is_supported,
                "damage_scaling": dict(choice.get("damage_scaling") or {}),
                "save": save_payload,
                "area": dict(choice.get("area") or {}),
                "target_effect": dict(choice.get("target_effect") or {}),
                "condition": dict(choice.get("condition") or {}),
                "summary": str(choice.get("summary") or "").strip(),
            }
        )
    return choices


def project_spell_slot_options(spellcasting: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    slot_lookup = {
        (
            normalize_spell_slot_lane_id(slot.get("slot_lane_id")),
            int(slot.get("level") or 0),
        ): dict(slot)
        for slot in list(dict(state or {}).get("spell_slots") or [])
    }
    legacy_slots_by_level: dict[int, list[dict[str, Any]]] = {}
    for slot in list(dict(state or {}).get("spell_slots") or []):
        lane_id = normalize_spell_slot_lane_id(slot.get("slot_lane_id"))
        level = int(slot.get("level") or 0)
        if lane_id or level <= 0:
            continue
        legacy_slots_by_level.setdefault(level, []).append(dict(slot))

    lanes = spell_slot_lanes_from_spellcasting(spellcasting)
    multiple_lanes = len(lanes) > 1
    options: list[dict[str, Any]] = []
    for lane in lanes:
        lane_id = normalize_spell_slot_lane_id(lane.get("id"))
        lane_title = str(lane.get("title") or "Spell slots").strip() or "Spell slots"
        for slot in list(lane.get("slot_progression") or []):
            level = int(slot.get("level") or 0)
            if level <= 0:
                continue
            max_slots = int(slot.get("max_slots") or 0)
            state_slot = slot_lookup.get((lane_id, level))
            if state_slot is None and lane_id and legacy_slots_by_level.get(level):
                state_slot = legacy_slots_by_level[level].pop(0)
            state_slot = state_slot or {}
            used = int(state_slot.get("used") or 0)
            available = max(max_slots - used, 0)
            level_label = spell_level_label(level)
            options.append(
                {
                    "level": level,
                    "level_label": level_label,
                    "slot_lane_id": lane_id,
                    "lane_title": lane_title,
                    "label": f"{lane_title}: {level_label}" if multiple_lanes else level_label,
                    "used": used,
                    "max": max_slots,
                    "available": available,
                    "selection": f"{lane_id}|{level}",
                }
            )
    return options


def resolve_projected_item_metadata(
    campaign: Campaign,
    equipment_item: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> dict[str, Any]:
    systems_ref = dict(equipment_item.get("systems_ref") or {})
    entry = None
    if systems_service is not None:
        entry_key = str(systems_ref.get("entry_key") or "").strip()
        slug = str(systems_ref.get("slug") or "").strip()
        if entry_key and hasattr(systems_service, "get_entry_for_campaign"):
            entry = systems_service.get_entry_for_campaign(campaign.slug, entry_key)
        if entry is None and slug and hasattr(systems_service, "get_entry_by_slug_for_campaign"):
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, slug)
        if entry is None and hasattr(systems_service, "get_campaign_item_entry_by_page_ref"):
            page_ref = normalize_page_ref_slug(equipment_item.get("page_ref"))
            if page_ref:
                entry = systems_service.get_campaign_item_entry_by_page_ref(campaign.slug, page_ref)
    if entry is not None:
        metadata = dict(getattr(entry, "metadata", {}) or {})
        if metadata:
            return campaign_item_character_metadata(metadata)
    if is_campaign_item_mechanics_metadata(equipment_item):
        return campaign_item_character_metadata(equipment_item)
    return {}


def find_item_use_action(
    item_use_actions: list[dict[str, Any]],
    action_id: Any,
) -> dict[str, Any] | None:
    normalized_action_id = str(action_id or "").strip()
    if not normalized_action_id:
        return None
    for action in list(item_use_actions or []):
        action_payload = dict(action or {})
        if str(action_payload.get("id") or "").strip() == normalized_action_id:
            return action_payload
    return None


def parse_item_action_slot_selection(value: Any) -> tuple[str, int]:
    raw_value = str(value or "").strip()
    if "|" in raw_value:
        lane_id, level = raw_value.rsplit("|", 1)
        return normalize_spell_slot_lane_id(lane_id), int(level or 0)
    return "", int(raw_value or 0)


def resolve_attack_linked_item_refs(
    attack: dict[str, Any],
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    explicit_refs = normalize_attack_equipment_refs(attack)
    if explicit_refs:
        return explicit_refs
    linked_refs: list[str] = []
    attack_systems_slug = str(dict(attack.get("systems_ref") or {}).get("slug") or "").strip()
    attack_page_slug = normalize_page_ref_slug(attack.get("page_ref"))
    attack_name_candidates = build_attack_name_candidates(attack)
    for item_ref, equipment_item in equipment_catalog_lookup.items():
        if not item_ref:
            continue
        inventory_item = dict(inventory_lookup.get(item_ref) or {})
        item_systems_slug = str(dict(equipment_item.get("systems_ref") or {}).get("slug") or "").strip()
        item_page_slug = normalize_page_ref_slug(equipment_item.get("page_ref"))
        if attack_systems_slug and attack_systems_slug == item_systems_slug:
            linked_refs.append(item_ref)
            continue
        if attack_page_slug and attack_page_slug == item_page_slug:
            linked_refs.append(item_ref)
            continue
        item_name_candidates = build_equipment_name_candidates(equipment_item, inventory_item)
        if attack_name_candidates and item_name_candidates and attack_name_candidates.intersection(item_name_candidates):
            linked_refs.append(item_ref)
    return dedupe_values(linked_refs)


def _attack_matches_weapon_wield_mode(
    attack: dict[str, Any],
    *,
    equipment_item: dict[str, Any],
    inventory_item: dict[str, Any],
) -> bool:
    support_item = {
        **dict(equipment_item or {}),
        **dict(inventory_item or {}),
    }
    support = describe_equipment_state_support(support_item)
    if not resolve_item_equipped_state(support_item, support=support):
        return False
    if not bool(support.get("supports_weapon_wield_mode")):
        return True

    mode_components = set(_attack_mode_components(_infer_attack_mode_key_from_payload(attack)))
    explicit_mode = explicit_weapon_wield_mode(support_item, support=support)
    if ATTACK_MODE_WEAPON_OFF_HAND in mode_components:
        return explicit_mode == WEAPON_WIELD_MODE_OFF_HAND if explicit_mode else True
    if ATTACK_MODE_WEAPON_TWO_HANDED in mode_components:
        return explicit_mode == WEAPON_WIELD_MODE_TWO_HANDED if explicit_mode else True
    if explicit_mode == WEAPON_WIELD_MODE_TWO_HANDED:
        allowed_modes = {
            str(value).strip()
            for value in list(support.get("weapon_wield_modes") or [])
            if str(value).strip()
        }
        return allowed_modes == {WEAPON_WIELD_MODE_TWO_HANDED}
    return True


def resolve_attack_equipped_state(
    attack: dict[str, Any],
    linked_item_refs: list[str],
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
) -> bool | None:
    if not linked_item_refs:
        return None
    saw_linked_item = False
    for item_ref in linked_item_refs:
        inventory_item = dict(inventory_lookup.get(item_ref) or {})
        equipment_item = dict(equipment_catalog_lookup.get(item_ref) or {})
        quantity = int(
            inventory_item.get("quantity")
            or equipment_item.get("default_quantity")
            or 0
        )
        if quantity <= 0:
            continue
        saw_linked_item = True
        if _attack_matches_weapon_wield_mode(
            attack,
            equipment_item=equipment_item,
            inventory_item=inventory_item,
        ):
            return True
    if not saw_linked_item:
        return None
    return False


def present_arcane_armor_state(
    definition: Any,
    state: dict[str, Any],
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not character_has_feature(definition, ARCANE_ARMOR_FEATURE_NAME):
        return {"available": False}

    feature_states = dict(state.get("feature_states") or {})
    arcane_armor_payload = dict(feature_states.get(ARCANE_ARMOR_STATE_KEY) or {})
    enabled = bool(arcane_armor_payload.get("enabled"))
    hands_free = armorer_thunder_gauntlets_have_free_hands(
        inventory_lookup=inventory_lookup,
        equipment_catalog_lookup=equipment_catalog_lookup,
    )
    return {
        "available": True,
        "feature_key": ARCANE_ARMOR_STATE_KEY,
        "label": "Arcane Armor",
        "enabled": enabled,
        "status_label": "Enabled" if enabled else "Disabled",
        "hands_free": hands_free,
        "hands_label": "Hands free" if hands_free else "Hands occupied",
        "thunder_gauntlets_available": bool(enabled and hands_free),
        "defensive_field_available": enabled,
    }


def character_has_feature(definition: Any, feature_name: str) -> bool:
    target = normalize_feature_name(feature_name)
    return any(
        normalize_feature_name(feature.get("name")) == target
        for feature in list(getattr(definition, "features", []) or [])
        if isinstance(feature, dict)
    )


def armorer_thunder_gauntlets_have_free_hands(
    *,
    inventory_lookup: dict[str, dict[str, Any]],
    equipment_catalog_lookup: dict[str, dict[str, Any]],
) -> bool:
    for item_ref, inventory_item in inventory_lookup.items():
        equipment_item = dict(equipment_catalog_lookup.get(item_ref) or {})
        quantity = int(
            inventory_item.get("quantity")
            or equipment_item.get("default_quantity")
            or 0
        )
        if quantity <= 0:
            continue
        support_item = {
            **equipment_item,
            **dict(inventory_item or {}),
        }
        support = describe_equipment_state_support(support_item)
        if not resolve_item_equipped_state(support_item, support=support):
            continue
        if bool(support.get("is_weapon")) or armorer_item_occupies_hand(support_item):
            return False
    return True


def armorer_item_occupies_hand(item: dict[str, Any]) -> bool:
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
        str(systems_ref.get("slug") or "").strip(),
    ]
    return any(normalize_lookup(value) in {"shield", "phb item shield"} for value in candidate_values if value)


def is_guardian_thunder_gauntlets_name(value: Any) -> bool:
    return normalize_feature_name(value) == GUARDIAN_ARMOR_THUNDER_GAUNTLETS_NAME


def is_guardian_defensive_field_name(value: Any) -> bool:
    return normalize_feature_name(value) == GUARDIAN_ARMOR_DEFENSIVE_FIELD_NAME


def build_armorer_combat_availability(
    name: Any,
    arcane_armor_state: dict[str, Any],
) -> dict[str, Any]:
    if not bool(arcane_armor_state.get("available")):
        return {"available": True, "reason": ""}
    if is_guardian_thunder_gauntlets_name(name):
        if not bool(arcane_armor_state.get("enabled")):
            return {"available": False, "reason": "Arcane Armor is disabled."}
        if not bool(arcane_armor_state.get("hands_free")):
            return {"available": False, "reason": "Hands are occupied."}
    if is_guardian_defensive_field_name(name) and not bool(arcane_armor_state.get("enabled")):
        return {"available": False, "reason": "Arcane Armor is disabled."}
    return {"available": True, "reason": ""}


def normalize_attack_equipment_refs(attack: dict[str, Any]) -> list[str]:
    raw_refs = attack.get("equipment_refs")
    if raw_refs is None:
        raw_refs = attack.get("equipment_ref")
    if raw_refs is None or raw_refs == "" or raw_refs == [] or raw_refs == ():
        return []
    if isinstance(raw_refs, (list, tuple, set)):
        candidates = list(raw_refs)
    else:
        candidates = [raw_refs]
    return dedupe_values(str(candidate or "").strip() for candidate in candidates if str(candidate or "").strip())


def build_attack_name_candidates(attack: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for value in (
        attack.get("name"),
        dict(attack.get("systems_ref") or {}).get("title"),
        normalize_page_ref_title(attack.get("page_ref")),
    ):
        candidates.update(build_name_lookup_candidates(value))
    return candidates


def build_equipment_name_candidates(
    equipment_item: dict[str, Any],
    inventory_item: dict[str, Any],
) -> set[str]:
    candidates: set[str] = set()
    for value in (
        equipment_item.get("name"),
        inventory_item.get("name"),
        dict(equipment_item.get("systems_ref") or {}).get("title"),
        normalize_page_ref_title(equipment_item.get("page_ref")),
    ):
        candidates.update(build_name_lookup_candidates(value))
    return candidates


def build_name_lookup_candidates(value: Any) -> set[str]:
    clean_value = strip_attack_name_suffixes(value)
    if not clean_value:
        return set()
    candidates = {normalize_lookup(clean_value)}
    if "," in clean_value:
        comma_parts = [part.strip() for part in clean_value.split(",") if part.strip()]
        if len(comma_parts) >= 2:
            candidates.add(normalize_lookup(" ".join([*comma_parts[1:], comma_parts[0]])))
    return {candidate for candidate in candidates if candidate}


def strip_attack_name_suffixes(value: Any) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    previous_value = None
    while clean_value and previous_value != clean_value:
        previous_value = clean_value
        clean_value = ATTACK_NAME_SUFFIX_PATTERN.sub("", clean_value).strip()
    return clean_value


def normalize_page_ref_slug(page_ref: Any) -> str:
    payload = dict(page_ref or {}) if isinstance(page_ref, dict) else {}
    slug = str(payload.get("slug") or payload.get("page_slug") or "").strip()
    if slug:
        return slug
    return str(page_ref or "").strip()


def normalize_page_ref_title(page_ref: Any) -> str:
    payload = dict(page_ref or {}) if isinstance(page_ref, dict) else {}
    return str(payload.get("title") or "").strip()


def dedupe_values(values: Any) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = str(value or "").strip()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        ordered.append(clean_value)
    return ordered


def normalize_feature_name(value: Any) -> str:
    return str(value or "").strip().lower()


def build_xianxia_mechanics_projection(
    campaign: Campaign,
    xianxia_definition: dict[str, Any],
    state: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> dict[str, Any]:
    defense = present_xianxia_defense_derivation(xianxia_definition)
    actions = present_xianxia_action_count_derivation(xianxia_definition)
    effort_damage = present_xianxia_effort_damage_derivation(xianxia_definition)
    check_formula = present_xianxia_check_formula()
    difficulty_states = present_xianxia_difficulty_states()
    return {
        "defense": defense,
        "actions": actions,
        "effort_damage": effort_damage,
        "check_formula": check_formula,
        "difficulty_states": difficulty_states,
        "honor_interactions": present_xianxia_honor_interactions(
            campaign,
            xianxia_definition,
            systems_service=systems_service,
        ),
        "skill_use_guardrails": present_xianxia_skill_use_guardrails(
            campaign,
            systems_service=systems_service,
        ),
        "rule_text_references": present_xianxia_rule_text_references(
            campaign,
            systems_service=systems_service,
        ),
        "active_state_reminders": present_xianxia_active_state_reminders(
            campaign,
            state,
            systems_service=systems_service,
        ),
        "stance_break": present_xianxia_stance_break_reference(
            campaign,
            state,
            systems_service=systems_service,
        ),
    }


def present_xianxia_defense_derivation(xianxia_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(xianxia_payload or {})
    attributes = dict(payload.get("attributes") or {})
    durability = dict(payload.get("durability") or {})
    manual_armor_bonus = _coerce_int(durability.get("manual_armor_bonus"), default=0)
    constitution = _coerce_int(attributes.get("con"), default=0)
    value = derive_xianxia_defense(
        attributes=attributes,
        manual_armor_bonus=manual_armor_bonus,
    )
    return {
        "value": value,
        "base": XIANXIA_DEFENSE_BASE,
        "manual_armor_bonus": manual_armor_bonus,
        "constitution": constitution,
        "formula": f"{XIANXIA_DEFENSE_BASE} + {manual_armor_bonus} + {constitution}",
    }


def present_xianxia_action_count_derivation(xianxia_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(xianxia_payload or {})
    realm = str(payload.get("realm") or "Mortal").strip() or "Mortal"
    actions_per_turn = derive_xianxia_actions_per_turn(realm)
    return {
        "realm": realm,
        "actions_per_turn": actions_per_turn,
        "formula": f"{realm} -> {actions_per_turn} actions per turn",
    }


def present_xianxia_effort_damage_derivation(xianxia_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(xianxia_payload or {})
    efforts = dict(payload.get("efforts") or {})
    damage_strings = derive_xianxia_effort_damage_strings()
    entries = [
        {
            "key": key,
            "label": XIANXIA_EFFORT_LABELS[key],
            "score": _coerce_int(efforts.get(key), default=0),
            "damage": damage_strings[key],
        }
        for key in XIANXIA_EFFORT_KEYS
    ]
    return {"entries": entries}


def present_xianxia_check_formula() -> dict[str, str]:
    return derive_xianxia_check_formula_strings()


def present_xianxia_difficulty_states() -> dict[str, Any]:
    return derive_xianxia_difficulty_state_adjustments()


def present_xianxia_honor_interactions(
    campaign: Campaign,
    xianxia_payload: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> dict[str, Any]:
    payload = dict(xianxia_payload or {})
    presentation = derive_xianxia_honor_interaction_reminders(payload.get("honor"))
    entry = None
    if systems_service is not None:
        entry = systems_service.get_entry_for_campaign(
            campaign.slug,
            XIANXIA_HONOR_RULE_ENTRY_KEY,
        )
        if entry is None:
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, "honor")

    rule_title = str(getattr(entry, "title", "") or "Honor")
    metadata = dict(getattr(entry, "metadata", {}) or {}) if entry is not None else {}
    body = dict(getattr(entry, "body", {}) or {}) if entry is not None else {}
    support_state = str(
        metadata.get("support_state") or body.get("support_state") or ""
    ).strip()
    presentation.update(
        {
            "status_label": f"Current Honor: {presentation['honor']}",
            "rule_title": rule_title,
            "rule_href": build_systems_entry_href(
                campaign.slug,
                {
                    "slug": str(getattr(entry, "slug", "") or "honor"),
                    "title": rule_title,
                    "entry_type": "rule",
                    "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                },
            ),
            "support_label": "Reference only" if support_state == "reference_only" else "",
            "reference_lines": (
                _extract_xianxia_rule_reference_lines(entry, facet_name="quick_reference")
                if entry is not None
                else []
            ),
        }
    )
    return presentation


def present_xianxia_skill_use_guardrails(
    campaign: Campaign,
    *,
    systems_service: Any | None = None,
) -> dict[str, Any] | None:
    if systems_service is None:
        return None

    entry = systems_service.get_entry_for_campaign(
        campaign.slug,
        XIANXIA_SKILLS_RULE_ENTRY_KEY,
    )
    if entry is None:
        entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, "skills")
    if entry is None:
        return None

    reference_lines = _extract_xianxia_rule_facet_lines(
        entry,
        "guardrails",
        fallback_to_body=False,
    )
    if not reference_lines:
        return None

    rule_title = str(getattr(entry, "title", "") or "Skills")
    return {
        "rule_title": rule_title,
        "rule_href": build_systems_entry_href(
            campaign.slug,
            {
                "slug": str(getattr(entry, "slug", "") or "skills"),
                "title": rule_title,
                "entry_type": "rule",
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            },
        ),
        "reference_lines": reference_lines,
    }


def present_xianxia_rule_text_references(
    campaign: Campaign,
    *,
    systems_service: Any | None = None,
) -> list[dict[str, Any]]:
    if systems_service is None:
        return []

    references: list[dict[str, Any]] = []
    for default_title, slug in XIANXIA_RULE_TEXT_REFERENCE_SPECS:
        entry_key = f"xianxia|rule|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|{slug}"
        entry = systems_service.get_entry_for_campaign(campaign.slug, entry_key)
        if entry is None:
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, slug)
        if entry is None:
            continue

        reference_lines = _extract_xianxia_rule_reference_lines(entry, facet_name="quick_reference")
        if not reference_lines:
            continue

        metadata = dict(getattr(entry, "metadata", {}) or {})
        body = dict(getattr(entry, "body", {}) or {})
        support_state = str(
            metadata.get("support_state") or body.get("support_state") or ""
        ).strip()
        title = str(getattr(entry, "title", "") or default_title)
        references.append(
            {
                "title": title,
                "support_label": "Reference only"
                if support_state == "reference_only"
                else "",
                "reference_lines": reference_lines,
                "rule_href": build_systems_entry_href(
                    campaign.slug,
                    {
                        "slug": str(getattr(entry, "slug", "") or slug),
                        "title": title,
                        "entry_type": "rule",
                        "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                    },
                ),
            }
        )

    return references


def present_xianxia_active_state_reminders(
    campaign: Campaign,
    state: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> list[dict[str, Any]]:
    if systems_service is None:
        return []

    xianxia_state = dict(state.get("xianxia") or {})
    specs = [
        {
            "label": "Stance",
            "state_key": "active_stance",
            "entry_key": XIANXIA_STANCE_ACTIVATION_RULE_ENTRY_KEY,
            "slug": "stance-activation-rules",
        },
        {
            "label": "Aura",
            "state_key": "active_aura",
            "entry_key": XIANXIA_AURA_ACTIVATION_RULE_ENTRY_KEY,
            "slug": "aura-activation-rules",
        },
    ]
    reminders: list[dict[str, Any]] = []
    for spec in specs:
        entry = systems_service.get_entry_for_campaign(campaign.slug, spec["entry_key"])
        if entry is None:
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, spec["slug"])
        if entry is None:
            continue

        reminder_facet = _xianxia_rule_facet_payload(entry, "active_state_reminders")
        label = str(reminder_facet.get("label") or spec["label"])
        state_key = str(reminder_facet.get("state_key") or spec["state_key"])
        active_record = coerce_xianxia_active_state_record(
            xianxia_state.get(state_key)
        )
        active_name = str(active_record.get("name") or "").strip()
        active_status_template = str(
            reminder_facet.get("active_status_label_template") or f"Active {label}: {{name}}"
        ).strip()
        empty_status_label = str(
            reminder_facet.get("empty_status_label") or f"No active {label} recorded"
        ).strip()
        metadata = dict(getattr(entry, "metadata", {}) or {})
        body = dict(getattr(entry, "body", {}) or {})
        support_state = str(
            metadata.get("support_state") or body.get("support_state") or ""
        ).strip()

        reminders.append(
            {
                "label": label,
                "title": str(getattr(entry, "title", "") or f"{label} Activation Rules"),
                "status_label": (
                    active_status_template.replace("{name}", active_name)
                    if active_name
                    else empty_status_label
                ),
                "support_label": "Reference only"
                if support_state == "reference_only"
                else "",
                "reference_lines": _extract_xianxia_rule_reference_lines(
                    entry,
                    facet_name="active_state_reminders",
                ),
                "rule_href": build_systems_entry_href(
                    campaign.slug,
                    {
                        "slug": str(getattr(entry, "slug", "") or spec["slug"]),
                        "title": str(getattr(entry, "title", "") or ""),
                        "entry_type": "rule",
                        "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                    },
                ),
            }
        )

    return reminders


def coerce_xianxia_active_state_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _extract_xianxia_rule_reference_lines(
    entry: Any,
    *,
    facet_name: str = "",
    fallback_to_body: bool = True,
) -> list[str]:
    if facet_name:
        facet_lines = _extract_xianxia_rule_facet_lines(
            entry,
            facet_name,
            fallback_to_body=False,
        )
        if facet_lines:
            return facet_lines
        if not fallback_to_body:
            return []

    body = dict(getattr(entry, "body", {}) or {})
    raw_lines: list[str] = []
    summary = str(body.get("summary") or "").strip()
    if summary:
        raw_lines.append(summary)
    for section in list(body.get("sections") or []):
        section_payload = dict(section or {})
        raw_lines.extend(
            str(paragraph or "").strip()
            for paragraph in list(section_payload.get("paragraphs") or [])
        )
        raw_lines.extend(
            str(bullet or "").strip()
            for bullet in list(section_payload.get("bullets") or [])
        )

    lines: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        normalized = line.casefold()
        if not line or normalized in seen:
            continue
        seen.add(normalized)
        lines.append(line)
    return lines


def _extract_xianxia_rule_facet_lines(
    entry: Any,
    facet_name: str,
    *,
    fallback_to_body: bool = False,
) -> list[str]:
    facet_payload = _xianxia_rule_facet_payload(entry, facet_name)
    raw_lines = _xianxia_rule_facet_string_list(facet_payload, "reference_lines")
    if not raw_lines:
        raw_lines = _xianxia_rule_facet_string_list(facet_payload, "lines")
    if not raw_lines:
        raw_lines = _xianxia_rule_facet_string_list(facet_payload, "bullets")
    lines = dedupe_values(raw_lines)
    if lines or not fallback_to_body:
        return lines
    return _extract_xianxia_rule_reference_lines(entry)


def _extract_xianxia_rule_break_reference(entry: Any) -> dict[str, Any]:
    facet_payload = _xianxia_rule_facet_payload(entry, "break_reference")
    if not facet_payload:
        return {}
    return {
        "status_label": str(facet_payload.get("status_label") or "").strip(),
        "reference_lines": dedupe_values(
            _xianxia_rule_facet_string_list(facet_payload, "reference_lines")
        ),
        "recovery_lines": dedupe_values(
            _xianxia_rule_facet_string_list(facet_payload, "recovery_lines")
        ),
    }


def _xianxia_rule_facet_payload(entry: Any, facet_name: str) -> dict[str, Any]:
    normalized_name = str(facet_name or "").strip()
    if not normalized_name:
        return {}
    for source in (
        dict(getattr(entry, "metadata", {}) or {}),
        dict(getattr(entry, "body", {}) or {}),
    ):
        facets = source.get("xianxia_rule_facets")
        if not isinstance(facets, dict):
            continue
        payload = facets.get(normalized_name)
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, list):
            return {"reference_lines": list(payload)}
    return {}


def _xianxia_rule_facet_string_list(payload: Any, key: str) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_value = payload.get(key)
    if raw_value in (None, "", [], ()):
        return []
    if isinstance(raw_value, str):
        candidates = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        candidates = list(raw_value)
    else:
        candidates = [raw_value]
    return [str(value or "").strip() for value in candidates if str(value or "").strip()]


def present_xianxia_stance_break_reference(
    campaign: Campaign,
    state: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> dict[str, Any] | None:
    xianxia_state = dict(state.get("xianxia") or {})
    xianxia_vitals = dict(xianxia_state.get("vitals") or {})
    current_stance = _coerce_int(xianxia_vitals.get("current_stance"), default=0)
    if current_stance != 0:
        return None

    entry = None
    if systems_service is not None:
        entry = systems_service.get_entry_for_campaign(
            campaign.slug,
            XIANXIA_STANCE_RULE_ENTRY_KEY,
        )
        if entry is None:
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, "stance")

    reference_lines: list[str] = []
    recovery_lines: list[str] = []
    status_label = "Current Stance 0"
    if entry is not None:
        break_reference = _extract_xianxia_rule_break_reference(entry)
        reference_lines = list(break_reference.get("reference_lines") or [])
        recovery_lines = list(break_reference.get("recovery_lines") or [])
        status_label = str(break_reference.get("status_label") or status_label).strip()

    if not reference_lines:
        reference_lines.append("Current Stance is 0.")

    systems_ref = {
        "slug": "stance",
        "title": str(getattr(entry, "title", "") or "Stance"),
        "entry_type": "rule",
        "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
    }
    return {
        "current_stance": current_stance,
        "status_label": status_label,
        "reference_lines": reference_lines,
        "recovery_lines": recovery_lines,
        "rule_title": systems_ref["title"],
        "rule_href": build_systems_entry_href(campaign.slug, systems_ref),
    }


def build_systems_entry_href(campaign_slug: str, systems_ref: Any) -> str:
    payload = dict(systems_ref or {})
    slug = str(payload.get("slug") or "").strip()
    if not slug or not campaign_slug.strip():
        return ""
    return f"/campaigns/{campaign_slug}/systems/entries/{slug}"


def build_character_entry_href(campaign_slug: str, *, systems_ref: Any = None, page_ref: Any = None) -> str:
    systems_href = build_systems_entry_href(campaign_slug, systems_ref)
    if systems_href:
        return systems_href
    page_slug = normalize_page_ref_slug(page_ref)
    if page_slug and campaign_slug.strip():
        return f"/campaigns/{campaign_slug}/pages/{page_slug}"
    return ""


def spell_level_label(level: int) -> str:
    if int(level or 0) == 0:
        return "Cantrip"
    suffix = "th"
    if int(level) % 10 == 1 and int(level) % 100 != 11:
        suffix = "st"
    elif int(level) % 10 == 2 and int(level) % 100 != 12:
        suffix = "nd"
    elif int(level) % 10 == 3 and int(level) % 100 != 13:
        suffix = "rd"
    return f"{int(level)}{suffix} level"


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
