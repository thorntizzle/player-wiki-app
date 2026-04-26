from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import re
from typing import Any

import markdown

from .character_builder import (
    ATTACK_MODE_WEAPON_OFF_HAND,
    ATTACK_MODE_WEAPON_TWO_HANDED,
    WEAPON_WIELD_MODE_OFF_HAND,
    WEAPON_WIELD_MODE_TWO_HANDED,
    _attack_mode_components,
    CharacterBuildError,
    _format_weight_value,
    _infer_attack_mode_key_from_payload,
    _spell_access_badge_label,
    _spell_payload_is_always_prepared,
    _spell_payload_map_key,
    describe_equipment_state_support,
    explicit_weapon_wield_mode,
    normalize_definition_to_native_model,
    resolve_item_equipped_state,
)
from .character_models import CharacterRecord
from .character_profile import (
    profile_class_level_text,
    profile_primary_class_ref,
    profile_primary_subclass_name,
    profile_primary_subclass_ref,
)
from .character_service import merge_state_with_definition
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lanes_from_spellcasting
from .models import Campaign
from .repository import build_alias_index, normalize_lookup, render_obsidian_links
from .system_policy import is_xianxia_system
from .xianxia_systems_seed import XIANXIA_HOMEBREW_SOURCE_ID
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_ENERGY_KEYS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_DEFENSE_BASE,
    derive_xianxia_actions_per_turn,
    derive_xianxia_check_formula_strings,
    derive_xianxia_defense,
    derive_xianxia_difficulty_state_adjustments,
    derive_xianxia_effort_damage_strings,
    derive_xianxia_honor_interaction_reminders,
)

ABILITY_ORDER = (
    ("str", "strength", "Strength"),
    ("dex", "dexterity", "Dexterity"),
    ("con", "constitution", "Constitution"),
    ("int", "intelligence", "Intelligence"),
    ("wis", "wisdom", "Wisdom"),
    ("cha", "charisma", "Charisma"),
)
PROFICIENCY_TITLES = (
    ("armor", "Armor"),
    ("weapons", "Weapons"),
    ("tools", "Tools"),
    ("languages", "Languages"),
)
FEATURE_GROUP_TITLES = {
    "class_feature": "Class Features",
    "species_trait": "Species Traits",
    "feat": "Feats",
    "background_feature": "Background Features",
    "custom_feature": "Custom Features",
}
REDUNDANT_FEATURE_CHOICE_NAMES = {
    "ability score increase",
    "ability score improvement",
}
REDUNDANT_PASSIVE_FEATURE_NAMES = {
    "fighting style",
    "martial archetype",
    "psi warrior",
}
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
XIANXIA_READ_SUBPAGE_LABELS = (
    ("quick", "Quick Reference"),
    ("martial_arts", "Martial Arts"),
    ("techniques", "Techniques"),
    ("resources", "Resources"),
    ("skills", "Skills"),
    ("equipment", "Equipment"),
    ("inventory", "Inventory"),
    ("personal", "Personal"),
    ("notes", "Notes"),
    ("controls", "Controls"),
)
XIANXIA_ENERGY_LABELS = {
    "jing": "Jing",
    "qi": "Qi",
    "shen": "Shen",
}
ATTACK_NAME_SUFFIX_PATTERN = re.compile(r"\s*\([^)]*\)\s*$")


def _present_tool_proficiency_values(proficiencies: dict[str, Any]) -> list[str]:
    tools = [str(value).strip() for value in list(proficiencies.get("tools") or []) if str(value).strip()]
    tool_expertise = [str(value).strip() for value in list(proficiencies.get("tool_expertise") or []) if str(value).strip()]
    expertise_lookup = {
        normalize_lookup(value): value
        for value in tool_expertise
        if normalize_lookup(value)
    }
    presented: list[str] = []
    seen: set[str] = set()
    for value in tools + tool_expertise:
        cleaned = str(value).strip()
        normalized = normalize_lookup(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        label = cleaned
        if normalized in expertise_lookup:
            label = f"{label} (Expertise)"
        presented.append(label)
    return presented


def _presented_spell_remove_label(*, mode: str, is_cantrip: bool, is_prepared: bool) -> str:
    if is_cantrip:
        return "Remove cantrip"
    if mode == "prepared" and is_prepared:
        return "Unprepare spell"
    if mode == "wizard":
        return "Remove from spellbook"
    if mode == "ritual_book":
        return "Remove from ritual book"
    return "Remove spell"


def present_character_roster(records: list[CharacterRecord]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for record in records:
        definition = record.definition
        profile = definition.profile
        vitals = dict(record.state_record.state.get("vitals") or {})
        resources = sorted(
            list(record.state_record.state.get("resources") or []),
            key=lambda item: (int(item.get("display_order") or 0), str(item.get("label") or "").lower()),
        )
        resource_preview = [
            {
                "label": str(resource.get("label") or "Resource"),
                "value": summarize_resource_value(resource),
            }
            for resource in resources[:3]
        ]

        search_parts = [
            definition.name,
            profile_class_level_text(profile, default=""),
            str(profile.get("species") or ""),
            str(profile.get("background") or ""),
        ]

        cards.append(
            {
                "slug": definition.character_slug,
                "name": definition.name,
                "class_level_text": profile_class_level_text(profile),
                "species": str(profile.get("species") or ""),
                "background": str(profile.get("background") or ""),
                "current_hp": int(vitals.get("current_hp") or 0),
                "max_hp": int(definition.stats.get("max_hp") or 0),
                "temp_hp": int(vitals.get("temp_hp") or 0),
                "resource_preview": resource_preview,
                "search_text": " ".join(part for part in search_parts if part).lower(),
            }
        )
    return cards


def present_character_detail(
    campaign: Campaign,
    record: CharacterRecord,
    *,
    include_player_notes_section: bool = True,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    definition = record.definition
    state = deepcopy(record.state_record.state or {})
    if systems_service is not None:
        try:
            definition = normalize_definition_to_native_model(
                definition,
                systems_service=systems_service,
                campaign_page_records=campaign_page_records,
            )
            state = merge_state_with_definition(definition, state)
        except (CharacterBuildError, TypeError, ValueError):
            definition = record.definition
            state = deepcopy(record.state_record.state or {})
    vitals = dict(state.get("vitals") or {})
    stats = dict(definition.stats or {})
    profile = dict(definition.profile or {})
    is_xianxia_character = is_xianxia_system(definition.system)
    xianxia_defense = (
        present_xianxia_defense_derivation(definition.xianxia)
        if is_xianxia_character
        else None
    )
    xianxia_actions = (
        present_xianxia_action_count_derivation(definition.xianxia)
        if is_xianxia_character
        else None
    )
    xianxia_effort_damage = (
        present_xianxia_effort_damage_derivation(definition.xianxia)
        if is_xianxia_character
        else None
    )
    xianxia_check_formula = (
        present_xianxia_check_formula()
        if is_xianxia_character
        else None
    )
    xianxia_difficulty_states = (
        present_xianxia_difficulty_states()
        if is_xianxia_character
        else None
    )
    xianxia_honor_interactions = (
        present_xianxia_honor_interactions(
            campaign,
            definition.xianxia,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else None
    )
    xianxia_skill_use_guardrails = (
        present_xianxia_skill_use_guardrails(
            campaign,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else None
    )
    xianxia_rule_text_references = (
        present_xianxia_rule_text_references(
            campaign,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else []
    )
    xianxia_active_state_reminders = (
        present_xianxia_active_state_reminders(
            campaign,
            state,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else []
    )
    xianxia_stance_break = (
        present_xianxia_stance_break_reference(
            campaign,
            state,
            systems_service=systems_service,
        )
        if is_xianxia_character
        else None
    )
    xianxia_read_context = (
        present_xianxia_read_context(
            campaign,
            definition.xianxia,
            state,
            xianxia_defense=xianxia_defense,
            xianxia_actions=xianxia_actions,
            xianxia_effort_damage=xianxia_effort_damage,
            xianxia_check_formula=xianxia_check_formula,
            xianxia_difficulty_states=xianxia_difficulty_states,
            xianxia_honor_interactions=xianxia_honor_interactions,
            xianxia_skill_use_guardrails=xianxia_skill_use_guardrails,
            xianxia_rule_text_references=xianxia_rule_text_references,
            xianxia_active_state_reminders=xianxia_active_state_reminders,
            xianxia_stance_break=xianxia_stance_break,
        )
        if is_xianxia_character
        else None
    )
    notes_payload = dict(state.get("notes") or {})
    resource_lookup = {
        str(resource.get("id") or ""): resource for resource in list(state.get("resources") or [])
    }
    equipment_catalog_lookup = {
        str(item.get("id") or ""): dict(item or {})
        for item in list(definition.equipment_catalog or [])
        if str(item.get("id") or "").strip()
    }
    inventory_lookup = {
        build_character_inventory_item_ref(item): dict(item or {})
        for item in list(state.get("inventory") or [])
        if build_character_inventory_item_ref(item)
    }

    if is_xianxia_character:
        xianxia_payload = dict(definition.xianxia or {})
        xianxia_durability = dict(xianxia_payload.get("durability") or {})
        overview_stats = [
            {
                "label": "Current HP",
                "value": (
                    f"{int(vitals.get('current_hp') or 0)} / "
                    f"{_coerce_int(xianxia_durability.get('hp_max'), default=10)}"
                ),
            },
            {"label": "Temp HP", "value": str(int(vitals.get("temp_hp") or 0))},
            {
                "label": "Realm",
                "value": str((xianxia_actions or {}).get("realm") or "Mortal"),
            },
            {
                "label": "Actions per turn",
                "value": str((xianxia_actions or {}).get("actions_per_turn") or 2),
            },
            {
                "label": "Defense",
                "value": str((xianxia_defense or {}).get("value", 0)),
            },
        ]
    else:
        overview_stats = [
            {"label": "Current HP", "value": f"{int(vitals.get('current_hp') or 0)} / {int(stats.get('max_hp') or 0)}"},
            {"label": "Temp HP", "value": str(int(vitals.get("temp_hp") or 0))},
            {"label": "Armor Class", "value": str(int(stats.get("armor_class") or 0))},
            {"label": "Initiative", "value": format_signed(stats.get("initiative_bonus"))},
            {"label": "Speed", "value": str(stats.get("speed") or "--")},
            {"label": "Proficiency", "value": format_signed(stats.get("proficiency_bonus"))},
            {"label": "Passive Perception", "value": str(int(stats.get("passive_perception") or 0))},
            {"label": "Passive Insight", "value": str(int(stats.get("passive_insight") or 0))},
            {"label": "Passive Investigation", "value": str(int(stats.get("passive_investigation") or 0))},
        ]
        if stats.get("carrying_capacity") not in (None, ""):
            overview_stats.append(
                {
                    "label": "Carrying Capacity",
                    "value": _format_weight_value(stats.get("carrying_capacity")) or "--",
                }
            )
        if stats.get("push_drag_lift") not in (None, ""):
            overview_stats.append(
                {
                    "label": "Push / Drag / Lift",
                    "value": _format_weight_value(stats.get("push_drag_lift")) or "--",
                }
            )
    death_saves = dict(vitals.get("death_saves") or {})
    death_save_summary = None
    if int(death_saves.get("successes") or 0) or int(death_saves.get("failures") or 0):
        death_save_summary = (
            f"{int(death_saves.get('successes') or 0)} success"
            f"{'' if int(death_saves.get('successes') or 0) == 1 else 'es'}, "
            f"{int(death_saves.get('failures') or 0)} failure"
            f"{'' if int(death_saves.get('failures') or 0) == 1 else 's'}"
        )

    abilities = []
    ability_scores = dict(stats.get("ability_scores") or {})
    for ability_key, legacy_key, ability_name in ABILITY_ORDER:
        ability = resolve_ability_score_payload(ability_scores, ability_key, legacy_key)
        abilities.append(
            {
                "abbr": ability_key.upper(),
                "name": ability_name,
                "score": int(ability.get("score") or 0),
                "modifier": format_signed(ability.get("modifier")),
                "save_bonus": format_signed(ability.get("save_bonus")),
            }
        )

    skills = [
        {
            "name": str(skill.get("name") or "Skill"),
            "bonus": format_signed(skill.get("bonus")),
            "proficiency_label": humanize_value(skill.get("proficiency_level")),
            "is_proficient": str(skill.get("proficiency_level") or "none") != "none",
        }
        for skill in sorted(list(definition.skills or []), key=lambda item: str(item.get("name") or "").lower())
    ]

    proficiency_groups = []
    proficiencies = dict(definition.proficiencies or {})
    for key, title in PROFICIENCY_TITLES:
        if key == "tools":
            values = _present_tool_proficiency_values(proficiencies)
        else:
            values = [str(value).strip() for value in list(proficiencies.get(key) or []) if str(value).strip()]
        if values:
            proficiency_groups.append({"title": title, "values_list": values})

    resources = [
        {
            "id": str(resource.get("id") or ""),
            "label": str(resource.get("label") or "Resource"),
            "current": int(resource.get("current") or 0),
            "max": int(resource.get("max")) if resource.get("max") is not None else None,
            "value": summarize_resource_value(resource),
            "reset_on": str(resource.get("reset_on") or ""),
            "reset_label": humanize_value(resource.get("reset_on")),
            "is_manual": str(resource.get("reset_on") or "").lower() in {"manual", "other"},
            "notes": str(resource.get("notes") or "").strip(),
        }
        for resource in sorted(
            list(state.get("resources") or []),
            key=lambda item: (int(item.get("display_order") or 0), str(item.get("label") or "").lower()),
        )
    ]

    spellcasting_payload = dict(definition.spellcasting or {})
    spellcasting = None
    slot_lanes = spell_slot_lanes_from_spellcasting(spellcasting_payload)
    if spellcasting_payload.get("spells") or slot_lanes:
        slot_lookup = {
            (
                normalize_spell_slot_lane_id(slot.get("slot_lane_id")),
                int(slot.get("level") or 0),
            ): dict(slot)
            for slot in list(state.get("spell_slots") or [])
        }
        slot_pools = []
        for lane in slot_lanes:
            lane_id = normalize_spell_slot_lane_id(lane.get("id"))
            pool_slots = []
            for slot in list(lane.get("slot_progression") or []):
                level = int(slot.get("level") or 0)
                max_slots = int(slot.get("max_slots") or 0)
                state_slot = slot_lookup.get((lane_id, level), {})
                used = int(state_slot.get("used") or 0)
                pool_slots.append(
                    {
                        "level": level,
                        "label": spell_level_label(level),
                        "available": max_slots - used,
                        "used": used,
                        "max": max_slots,
                        "slot_lane_id": lane_id,
                    }
                )
            slot_pools.append(
                {
                    "id": lane_id,
                    "title": str(lane.get("title") or "").strip() or "Spell slots",
                    "shared": bool(lane.get("shared")),
                    "row_ids": [
                        str(row_id).strip()
                        for row_id in list(lane.get("row_ids") or [])
                        if str(row_id).strip()
                    ],
                    "slots": pool_slots,
                }
            )

        class_spell_rows = [
            dict(row or {})
            for row in list(spellcasting_payload.get("class_rows") or [])
            if isinstance(row, dict)
        ]
        source_spell_rows = [
            {
                "class_row_id": str(dict(row or {}).get("source_row_id") or "").strip(),
                "class_name": str(dict(row or {}).get("title") or "").strip() or "Feature spells",
                "level": 0,
                "spellcasting_ability": str(dict(row or {}).get("spellcasting_ability") or "").strip(),
                "spell_save_dc": dict(row or {}).get("spell_save_dc"),
                "spell_attack_bonus": dict(row or {}).get("spell_attack_bonus"),
                "spell_mode": str(dict(row or {}).get("spell_mode") or "").strip(),
                "row_kind": str(dict(row or {}).get("source_row_kind") or "source").strip() or "source",
            }
            for row in list(spellcasting_payload.get("source_rows") or [])
            if str(dict(row or {}).get("source_row_id") or "").strip()
        ]
        if not class_spell_rows and not source_spell_rows and (
            spellcasting_payload.get("spellcasting_class") or spellcasting_payload.get("spells")
        ):
            class_spell_rows = [
                {
                    "class_row_id": "class-row-1",
                    "class_name": str(spellcasting_payload.get("spellcasting_class") or "Spellcasting").strip() or "Spellcasting",
                    "level": 0,
                    "spellcasting_ability": str(spellcasting_payload.get("spellcasting_ability") or "").strip(),
                    "spell_save_dc": spellcasting_payload.get("spell_save_dc"),
                    "spell_attack_bonus": spellcasting_payload.get("spell_attack_bonus"),
                    "spell_mode": "",
                }
            ]
        spell_rows = class_spell_rows + source_spell_rows
        spell_rows_by_id = {
            str(row.get("class_row_id") or "").strip(): dict(row or {})
            for row in spell_rows
            if str(row.get("class_row_id") or "").strip()
        }
        if len(class_spell_rows) > 1 and len(slot_pools) == 1 and not bool((slot_pools[0] or {}).get("shared")):
            slot_pools[0]["shared"] = True
            slot_pools[0]["title"] = "Shared spell slots"

        spells_by_row_id: dict[str, list[dict[str, Any]]] = {
            str(row.get("class_row_id") or "").strip(): []
            for row in spell_rows
            if str(row.get("class_row_id") or "").strip()
        }
        fallback_row_id = (
            str((class_spell_rows[0] or {}).get("class_row_id") or "").strip()
            if len(class_spell_rows) == 1
            else ""
        )
        for spell in list(spellcasting_payload.get("spells") or []):
            always_prepared = _spell_payload_is_always_prepared(dict(spell or {}))
            badges = []
            if bool(spell.get("is_bonus_known")):
                badges.append("Feature granted")
            if always_prepared:
                badges.append("Always prepared")
            if bool(spell.get("is_ritual")):
                badges.append("Ritual")
            access_badge = _spell_access_badge_label(dict(spell or {}))
            if access_badge and access_badge not in badges:
                badges.append(access_badge)
            mark = str(spell.get("mark") or "").strip()
            if mark and mark not in badges:
                badges.append(mark)
            source_label = str(spell.get("grant_source_label") or spell.get("source") or "").strip()
            management_note = ""
            if always_prepared and source_label:
                management_note = f"Always prepared from {source_label}."
            elif bool(spell.get("is_bonus_known")) and source_label:
                management_note = f"Granted by {source_label}."

            presented_spell = (
                {
                    "name": str(spell.get("name") or "Spell"),
                    "href": build_character_entry_href(
                        campaign.slug,
                        systems_ref=spell.get("systems_ref"),
                        page_ref=spell.get("page_ref"),
                    ),
                    "casting_time": str(spell.get("casting_time") or "--"),
                    "range": str(spell.get("range") or "--"),
                    "duration": str(spell.get("duration") or "--"),
                    "components": str(spell.get("components") or "--"),
                    "save_or_hit": str(spell.get("save_or_hit") or "--"),
                    "source": str(spell.get("source") or "").strip(),
                    "reference": str(spell.get("reference") or "").strip(),
                    "badges": badges,
                    "class_row_id": str(
                        spell.get("class_row_id") or spell.get("spell_source_row_id") or fallback_row_id
                    ).strip(),
                    "management_note": management_note,
                }
            )
            target_row_id = str(presented_spell.get("class_row_id") or "").strip()
            row_payload = dict(spell_rows_by_id.get(target_row_id) or {})
            row_mode = str(row_payload.get("spell_mode") or "").strip()
            row_kind = str(row_payload.get("row_kind") or "class").strip() or "class"
            normalized_mark = normalize_lookup(mark)
            is_cantrip = "cantrip" in normalized_mark
            is_prepared = bool(
                not is_cantrip
                and (
                    always_prepared
                    or "prepared" in normalized_mark
                )
            )
            in_spellbook = bool(not is_cantrip and "spellbook" in normalized_mark)
            is_fixed = bool(always_prepared or spell.get("is_bonus_known"))
            can_toggle_prepared = bool(
                row_kind == "class"
                and row_mode == "wizard"
                and not is_cantrip
                and in_spellbook
                and not always_prepared
            )
            can_remove = bool((row_kind == "class" or row_mode == "ritual_book") and not is_fixed)
            presented_spell["spell_key"] = _spell_payload_map_key(dict(spell or {}))
            presented_spell["is_prepared"] = is_prepared
            presented_spell["can_toggle_prepared"] = can_toggle_prepared
            presented_spell["can_remove"] = can_remove
            presented_spell["remove_label"] = _presented_spell_remove_label(
                mode=row_mode,
                is_cantrip=is_cantrip,
                is_prepared=is_prepared,
            )
            if target_row_id and target_row_id in spells_by_row_id:
                spells_by_row_id[target_row_id].append(presented_spell)
            else:
                spells_by_row_id.setdefault("", []).append(presented_spell)

        row_sections = []
        for row in spell_rows:
            row_id = str(row.get("class_row_id") or "").strip()
            row_spells = list(spells_by_row_id.get(row_id) or [])
            counts = []
            cantrip_count = sum(1 for spell in row_spells if "Cantrip" in list(spell.get("badges") or []))
            prepared_count = sum(1 for spell in row_spells if any("Prepared" in badge for badge in list(spell.get("badges") or [])))
            spellbook_count = sum(1 for spell in row_spells if any("Spellbook" in badge for badge in list(spell.get("badges") or [])))
            ritual_book_count = sum(1 for spell in row_spells if any("Ritual book" in badge for badge in list(spell.get("badges") or [])))
            known_count = sum(1 for spell in row_spells if "Known" in list(spell.get("badges") or []))
            if cantrip_count:
                counts.append({"label": "Cantrips", "value": str(cantrip_count)})
            if str(row.get("row_kind") or "class").strip() != "class":
                if str(row.get("spell_mode") or "").strip() == "ritual_book":
                    counts.append({"label": "Ritual book spells", "value": str(ritual_book_count or len(row_spells))})
                elif row_spells:
                    counts.append({"label": "Feature spells", "value": str(len(row_spells))})
            elif str(row.get("spell_mode") or "").strip() == "known" and known_count:
                counts.append({"label": "Known spells", "value": str(known_count)})
            elif str(row.get("spell_mode") or "").strip() == "prepared" and prepared_count:
                counts.append({"label": "Prepared spells", "value": str(prepared_count)})
            elif str(row.get("spell_mode") or "").strip() == "wizard":
                if prepared_count:
                    counts.append({"label": "Prepared spells", "value": str(prepared_count)})
                if spellbook_count:
                    counts.append({"label": "Spellbook spells", "value": str(spellbook_count)})
            elif str(row.get("spell_mode") or "").strip() == "ritual_book":
                counts.append({"label": "Ritual book spells", "value": str(ritual_book_count)})
            row_sections.append(
                {
                    "class_row_id": row_id,
                    "title": (
                        f"{row.get('class_name')} {int(row.get('level') or 0)}"
                        if int(row.get("level") or 0) > 0
                        else str(row.get("class_name") or "Spellcasting").strip()
                    ),
                    "spellcasting_ability": str(row.get("spellcasting_ability") or "").strip(),
                    "spell_save_dc": row.get("spell_save_dc"),
                    "spell_attack_bonus": format_signed(row.get("spell_attack_bonus")),
                    "counts": counts,
                    "spells": row_spells,
                }
            )
        if list(spells_by_row_id.get("") or []):
            row_sections.append(
                {
                    "class_row_id": "",
                    "title": "Unassigned spells",
                    "spellcasting_ability": "",
                    "spell_save_dc": None,
                    "spell_attack_bonus": "",
                    "counts": [],
                    "spells": list(spells_by_row_id.get("") or []),
                }
            )

        spellcasting = {
            "spellcasting_class": str(spellcasting_payload.get("spellcasting_class") or ""),
            "spellcasting_ability": str(spellcasting_payload.get("spellcasting_ability") or ""),
            "spell_save_dc": spellcasting_payload.get("spell_save_dc"),
            "spell_attack_bonus": format_signed(spellcasting_payload.get("spell_attack_bonus")),
            "slots": list((slot_pools[0] or {}).get("slots") or []) if len(slot_pools) == 1 else [],
            "slots_title": str((slot_pools[0] or {}).get("title") or "Spell slots") if len(slot_pools) == 1 else "",
            "slot_pools": slot_pools,
            "multiclass_summary": (
                "Shared spell slots are shown once below, with spells grouped by class row."
                if len(class_spell_rows) > 1 and len(slot_pools) == 1 and bool((slot_pools[0] or {}).get("shared"))
                else (
                    "Spell slot pools are shown below, with spells grouped by class row."
                    if len(class_spell_rows) > 1 and len(slot_pools) > 1
                    else "Spell slots are shown below, with spells grouped by class row."
                )
            ),
            "row_sections": row_sections,
            "is_multiclass": len(class_spell_rows) > 1,
        }

    feature_groups_ordered: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    has_hit_point_details = int(stats.get("max_hp") or 0) > 0
    has_language_details = any(group["title"] == "Languages" and group["values_list"] for group in proficiency_groups)
    has_proficiency_details = bool(proficiency_groups)
    has_skill_details = bool(skills)
    has_named_feats = any(
        normalize_feature_name(feature.get("name")) != "feat"
        for feature in list(definition.features or [])
        if str(feature.get("category") or "").strip() == "feat"
    )
    for feature in list(definition.features or []):
        if should_hide_redundant_choice_feature(
            feature,
            has_hit_point_details=has_hit_point_details,
            has_language_details=has_language_details,
            has_proficiency_details=has_proficiency_details,
            has_skill_details=has_skill_details,
            has_named_feats=has_named_feats,
        ):
            continue
        group_title = FEATURE_GROUP_TITLES.get(
            str(feature.get("category") or ""),
            humanize_value(feature.get("category")) or "Features",
        )
        feature_groups_ordered.setdefault(group_title, [])
        tracker_ref = str(feature.get("tracker_ref") or "").strip()
        linked_resource = resource_lookup.get(tracker_ref) if tracker_ref else None
        metadata = [
            humanize_value(feature.get("activation_type")),
            summarize_linked_resource(linked_resource),
        ]
        feature_groups_ordered[group_title].append(
            {
                "name": str(feature.get("name") or "Feature"),
                "href": build_character_entry_href(
                    campaign.slug,
                    systems_ref=feature.get("systems_ref"),
                    page_ref=feature.get("page_ref"),
                ),
                "activation_type": str(feature.get("activation_type") or "").strip().lower(),
                "metadata": [part for part in metadata if part],
                "description_html": resolve_feature_description_html(
                    campaign,
                    feature,
                    systems_service=systems_service,
                ),
            }
        )

    attacks = []
    hidden_attacks: list[dict[str, str]] = []
    for attack in list(definition.attacks or []):
        attack_name = str(attack.get("name") or "Attack")
        attack_href = build_character_entry_href(
            campaign.slug,
            systems_ref=attack.get("systems_ref"),
            page_ref=attack.get("page_ref"),
        )
        linked_item_refs = resolve_attack_linked_item_refs(
            attack,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        attack_is_equipped = resolve_attack_equipped_state(
            attack,
            linked_item_refs,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        if attack_is_equipped is False:
            hidden_attacks.append(
                {
                    "name": attack_name,
                    "href": attack_href,
                }
            )
            continue
        raw_attack_bonus = attack.get("attack_bonus")
        attack_bonus = format_signed(raw_attack_bonus) if raw_attack_bonus not in {"", None} else ""
        damage = str(attack.get("damage") or "").strip()
        attacks.append(
            {
                "name": attack_name,
                "href": attack_href,
                "attack_bonus": attack_bonus,
                "damage": damage,
                "damage_type": str(attack.get("damage_type") or "").strip(),
                "category": humanize_value(attack.get("category")),
                "notes": str(attack.get("notes") or "").strip(),
                "linked_item_refs": linked_item_refs,
                "is_equipped": attack_is_equipped,
            }
        )

    attack_reminders = present_attack_reminders(stats, attacks)
    defensive_rules = present_defensive_rules(stats)

    inventory = [
        {
            "id": str(item.get("id") or ""),
            "item_ref": str(item.get("catalog_ref") or item.get("id") or "").strip(),
            "name": str(item.get("name") or "Item"),
            "href": build_character_entry_href(
                campaign.slug,
                systems_ref=equipment_catalog_lookup.get(str(item.get("catalog_ref") or item.get("id") or ""), {}).get(
                    "systems_ref"
                ),
                page_ref=equipment_catalog_lookup.get(str(item.get("catalog_ref") or item.get("id") or ""), {}).get(
                    "page_ref"
                ),
            ),
            "quantity": int(item.get("quantity") or 0),
            "weight": str(item.get("weight") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
            "tags": [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()],
            "is_equipped": bool(item.get("is_equipped", False)),
            "is_attuned": bool(item.get("is_attuned", False)),
        }
        for item in list(state.get("inventory") or [])
    ]

    currency_payload = dict(state.get("currency") or {})
    currency = [
        {"label": label.upper(), "amount": int(currency_payload.get(label) or 0)}
        for label in ("cp", "sp", "ep", "gp", "pp")
    ]
    other_currency = [str(item).strip() for item in list(currency_payload.get("other") or []) if str(item).strip()]

    reference_sections = build_reference_sections(
        campaign,
        definition.to_dict(),
        state,
        include_player_notes=include_player_notes_section,
    )
    player_notes_markdown = str(notes_payload.get("player_notes_markdown") or "")
    physical_description_markdown = str(notes_payload.get("physical_description_markdown") or "")
    personal_background_markdown = str(notes_payload.get("background_markdown") or "")

    feature_groups = [
        {"title": title, "entries": entries} for title, entries in feature_groups_ordered.items() if entries
    ]

    class_level_href = build_systems_entry_href(
        campaign.slug,
        profile_primary_class_ref(profile),
    )
    subclass_ref = profile_primary_subclass_ref(profile)
    subclass_label = profile_primary_subclass_name(profile)
    header_segments = [
        {
            "text": profile_class_level_text(profile),
            "href": class_level_href,
        }
    ]
    if subclass_label:
        header_segments.append(
            {
                "text": subclass_label,
                "href": build_systems_entry_href(campaign.slug, subclass_ref),
            }
        )
    if str(profile.get("species") or "").strip():
        header_segments.append(
            {
                "text": str(profile.get("species") or ""),
                "href": build_character_entry_href(
                    campaign.slug,
                    systems_ref=profile.get("species_ref"),
                    page_ref=profile.get("species_page_ref"),
                ),
            }
        )
    if str(profile.get("background") or "").strip():
        header_segments.append(
            {
                "text": str(profile.get("background") or ""),
                "href": build_character_entry_href(
                    campaign.slug,
                    systems_ref=profile.get("background_ref"),
                    page_ref=profile.get("background_page_ref"),
                ),
            }
        )

    return {
        "slug": definition.character_slug,
        "name": definition.name,
        "state_revision": record.state_record.revision,
        "current_hp": int(vitals.get("current_hp") or 0),
        "max_hp": int(stats.get("max_hp") or 0),
        "temp_hp": int(vitals.get("temp_hp") or 0),
        "player_notes_markdown": player_notes_markdown,
        "player_notes_html": render_campaign_markdown(campaign, player_notes_markdown)
        if player_notes_markdown.strip()
        else "",
        "physical_description_markdown": physical_description_markdown,
        "physical_description_html": render_campaign_markdown(campaign, physical_description_markdown)
        if physical_description_markdown.strip()
        else "",
        "personal_background_markdown": personal_background_markdown,
        "personal_background_html": render_campaign_markdown(campaign, personal_background_markdown)
        if personal_background_markdown.strip()
        else "",
        "class_level_text": profile_class_level_text(profile),
        "header_segments": [segment for segment in header_segments if str(segment.get("text") or "").strip()],
        "species": str(profile.get("species") or ""),
        "background": str(profile.get("background") or ""),
        "alignment": str(profile.get("alignment") or ""),
        "identity_details": [
            {"label": "Size", "value": str(profile.get("size") or "").strip()},
            {"label": "Faith", "value": str(profile.get("faith") or "").strip()},
            {"label": "Guild", "value": str(profile.get("guild") or "").strip()},
            {"label": "Experience", "value": str(profile.get("experience_model") or "").strip()},
        ],
        "overview_stats": overview_stats,
        "xianxia_defense": xianxia_defense,
        "xianxia_actions": xianxia_actions,
        "xianxia_effort_damage": xianxia_effort_damage,
        "xianxia_check_formula": xianxia_check_formula,
        "xianxia_difficulty_states": xianxia_difficulty_states,
        "xianxia_honor_interactions": xianxia_honor_interactions,
        "xianxia_skill_use_guardrails": xianxia_skill_use_guardrails,
        "xianxia_rule_text_references": xianxia_rule_text_references,
        "xianxia_active_state_reminders": xianxia_active_state_reminders,
        "xianxia_stance_break": xianxia_stance_break,
        "xianxia_read": xianxia_read_context,
        "attack_reminders": attack_reminders,
        "defensive_rules": defensive_rules,
        "death_save_summary": death_save_summary,
        "abilities": abilities,
        "skills": skills,
        "proficiency_groups": proficiency_groups,
        "resources": resources,
        "attacks": attacks,
        "hidden_attacks": dedupe_hidden_attacks(hidden_attacks),
        "feature_groups": feature_groups,
        "spellcasting": spellcasting,
        "inventory": inventory,
        "currency": currency,
        "currency_values": {
            label: int(currency_payload.get(label) or 0) for label in ("cp", "sp", "ep", "gp", "pp")
        },
        "other_currency": other_currency,
        "reference_sections": reference_sections,
    }


def build_character_inventory_item_ref(item: Any) -> str:
    payload = dict(item or {}) if isinstance(item, dict) else {}
    return str(payload.get("catalog_ref") or payload.get("id") or "").strip()


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


def dedupe_hidden_attacks(values: Any) -> list[dict[str, str]]:
    ordered: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in list(values or []):
        payload = dict(value or {}) if isinstance(value, dict) else {"name": str(value or "").strip(), "href": ""}
        name = str(payload.get("name") or "").strip()
        href = str(payload.get("href") or "").strip()
        if not name:
            continue
        key = (name, href)
        if key in seen:
            continue
        seen.add(key)
        ordered.append({"name": name, "href": href})
    return ordered


def _present_rule_effects(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def present_attack_reminders(stats: dict[str, Any], attacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reminder_state = dict(stats.get("attack_reminder_state") or {})
    reminders = []
    for rule in list(reminder_state.get("rules") or []):
        rule_payload = dict(rule or {})
        effects = _present_rule_effects(rule_payload)
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


def present_defensive_rules(stats: dict[str, Any]) -> list[dict[str, Any]]:
    defensive_state = dict(stats.get("defensive_state") or {})
    defensive_rules = []
    for rule in list(defensive_state.get("rules") or []):
        rule_payload = dict(rule or {})
        effects = _present_rule_effects(rule_payload)
        if not effects:
            continue
        defensive_rules.append(
            {
                "title": str(rule_payload.get("title") or "Defensive rule").strip() or "Defensive rule",
                "is_active": bool(rule_payload.get("active")),
                "status_label": "Active" if bool(rule_payload.get("active")) else "Inactive",
                "condition": str(rule_payload.get("condition") or "").strip(),
                "inactive_reason": str(rule_payload.get("inactive_reason") or "").strip(),
                "effects": effects,
            }
        )
    return defensive_rules


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
                _extract_xianxia_rule_reference_lines(entry)
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

    reference_lines = _extract_xianxia_skill_guardrail_lines(entry)
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

        reference_lines = _extract_xianxia_rule_reference_lines(entry)
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

        label = str(spec["label"])
        active_record = _coerce_xianxia_active_state_record(
            xianxia_state.get(str(spec["state_key"]))
        )
        active_name = str(active_record.get("name") or "").strip()
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
                    f"Active {label}: {active_name}"
                    if active_name
                    else f"No active {label} recorded"
                ),
                "support_label": "Reference only"
                if support_state == "reference_only"
                else "",
                "reference_lines": _extract_xianxia_rule_reference_lines(entry),
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


def _coerce_xianxia_active_state_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _extract_xianxia_rule_reference_lines(entry: Any) -> list[str]:
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


def _extract_xianxia_skill_guardrail_lines(entry: Any) -> list[str]:
    guardrail_lines: list[str] = []
    for line in _extract_xianxia_rule_reference_lines(entry):
        normalized = line.casefold()
        if (
            "active battle" in normalized
            or "pre-battle" in normalized
            or "surroundings" in normalized
        ):
            guardrail_lines.append(line)
    return guardrail_lines


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
    if entry is not None:
        for section in list(dict(entry.body or {}).get("sections") or []):
            section_payload = dict(section or {})
            for raw_bullet in list(section_payload.get("bullets") or []):
                bullet = str(raw_bullet or "").strip()
                if not bullet:
                    continue
                normalized = bullet.lower()
                if (
                    "current stance reaches 0" in normalized
                    or "stance breaks" in normalized
                    or "stance break" in normalized
                ):
                    reference_lines.append(bullet)
                elif "stance recovers" in normalized:
                    recovery_lines.append(bullet)

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
        "status_label": "Current Stance 0",
        "reference_lines": reference_lines,
        "recovery_lines": recovery_lines,
        "rule_title": systems_ref["title"],
        "rule_href": build_systems_entry_href(campaign.slug, systems_ref),
    }


def present_xianxia_read_context(
    campaign: Campaign,
    xianxia_definition: dict[str, Any],
    state: dict[str, Any],
    *,
    xianxia_defense: dict[str, Any] | None = None,
    xianxia_actions: dict[str, Any] | None = None,
    xianxia_effort_damage: dict[str, Any] | None = None,
    xianxia_check_formula: dict[str, Any] | None = None,
    xianxia_difficulty_states: dict[str, Any] | None = None,
    xianxia_honor_interactions: dict[str, Any] | None = None,
    xianxia_skill_use_guardrails: dict[str, Any] | None = None,
    xianxia_rule_text_references: list[dict[str, Any]] | None = None,
    xianxia_active_state_reminders: list[dict[str, Any]] | None = None,
    xianxia_stance_break: dict[str, Any] | None = None,
) -> dict[str, Any]:
    xianxia = dict(xianxia_definition or {})
    xianxia_state = dict(state.get("xianxia") or {})
    shared_vitals = dict(state.get("vitals") or {})
    xianxia_vitals = dict(xianxia_state.get("vitals") or {})
    durability = dict(xianxia.get("durability") or {})
    hp_max = _coerce_int(durability.get("hp_max"), default=10)
    stance_max = _coerce_int(durability.get("stance_max"), default=10)
    current_hp = _coerce_int(
        shared_vitals.get("current_hp", xianxia_vitals.get("current_hp")),
        default=hp_max,
    )
    temp_hp = _coerce_int(
        shared_vitals.get("temp_hp", xianxia_vitals.get("temp_hp")),
        default=0,
    )
    current_stance = _coerce_int(xianxia_vitals.get("current_stance"), default=stance_max)
    temp_stance = _coerce_int(xianxia_vitals.get("temp_stance"), default=0)
    energy_definition = dict(xianxia.get("energies") or {})
    energy_state = dict(xianxia_state.get("energies") or {})
    yin_yang_definition = dict(xianxia.get("yin_yang") or {})
    yin_yang_state = dict(xianxia_state.get("yin_yang") or {})
    dao_definition = dict(xianxia.get("dao") or {})
    dao_state = dict(xianxia_state.get("dao") or {})
    insight = dict(xianxia.get("insight") or {})
    effort_damage = dict(xianxia_effort_damage or {})
    effort_damage_entries = {
        str(entry.get("key") or ""): dict(entry or {})
        for entry in list(effort_damage.get("entries") or [])
        if str(entry.get("key") or "").strip()
    }
    active_stance = _coerce_xianxia_active_state_record(xianxia_state.get("active_stance"))
    active_aura = _coerce_xianxia_active_state_record(xianxia_state.get("active_aura"))
    dao_immolating = dict(xianxia.get("dao_immolating_techniques") or {})

    return {
        "system_label": "Xianxia",
        "subpages": [
            {"slug": slug, "label": label}
            for slug, label in XIANXIA_READ_SUBPAGE_LABELS
        ],
        "identity": {
            "realm": str((xianxia_actions or {}).get("realm") or xianxia.get("realm") or "Mortal"),
            "actions_per_turn": _coerce_int(
                (xianxia_actions or {}).get("actions_per_turn"),
                default=_coerce_int(xianxia.get("actions_per_turn"), default=2),
            ),
            "honor": str(xianxia.get("honor") or "Honorable"),
            "reputation": str(xianxia.get("reputation") or "Unknown"),
        },
        "attributes": [
            {
                "key": key,
                "label": XIANXIA_ATTRIBUTE_LABELS[key],
                "score": _coerce_int(dict(xianxia.get("attributes") or {}).get(key), default=0),
            }
            for key in XIANXIA_ATTRIBUTE_KEYS
        ],
        "efforts": [
            {
                "key": key,
                "label": XIANXIA_EFFORT_LABELS[key],
                "score": _coerce_int(dict(xianxia.get("efforts") or {}).get(key), default=0),
                "damage": str(effort_damage_entries.get(key, {}).get("damage") or ""),
            }
            for key in XIANXIA_EFFORT_KEYS
        ],
        "resources": {
            "durability": [
                {
                    "key": "hp",
                    "label": "HP",
                    "current": current_hp,
                    "max": hp_max,
                    "temp": temp_hp,
                },
                {
                    "key": "stance",
                    "label": "Stance",
                    "current": current_stance,
                    "max": stance_max,
                    "temp": temp_stance,
                },
            ],
            "energies": [
                {
                    "key": key,
                    "label": XIANXIA_ENERGY_LABELS[key],
                    "current": _coerce_int(
                        dict(energy_state.get(key) or {}).get("current"),
                        default=_coerce_int(dict(energy_definition.get(key) or {}).get("max"), default=0),
                    ),
                    "max": _coerce_int(dict(energy_definition.get(key) or {}).get("max"), default=0),
                }
                for key in XIANXIA_ENERGY_KEYS
            ],
            "yin_yang": [
                {
                    "key": "yin",
                    "label": "Yin",
                    "current": _coerce_int(
                        yin_yang_state.get("yin_current"),
                        default=_coerce_int(yin_yang_definition.get("yin_max"), default=1),
                    ),
                    "max": _coerce_int(yin_yang_definition.get("yin_max"), default=1),
                },
                {
                    "key": "yang",
                    "label": "Yang",
                    "current": _coerce_int(
                        yin_yang_state.get("yang_current"),
                        default=_coerce_int(yin_yang_definition.get("yang_max"), default=1),
                    ),
                    "max": _coerce_int(yin_yang_definition.get("yang_max"), default=1),
                },
            ],
            "dao": {
                "current": _coerce_int(dao_state.get("current"), default=0),
                "max": _coerce_int(dao_definition.get("max"), default=3),
            },
            "insight": {
                "available": _coerce_int(insight.get("available"), default=0),
                "spent": _coerce_int(insight.get("spent"), default=0),
            },
        },
        "skills": {
            "trained": [
                {"name": skill}
                for skill in _text_list(dict(xianxia.get("skills") or {}).get("trained"))
            ],
        },
        "equipment": {
            "manual_armor_bonus": _coerce_int(durability.get("manual_armor_bonus"), default=0),
            "defense": _coerce_int(durability.get("defense"), default=0),
            "necessary_weapons": _present_xianxia_named_records(
                dict(xianxia.get("equipment") or {}).get("necessary_weapons")
            ),
            "necessary_tools": _present_xianxia_named_records(
                dict(xianxia.get("equipment") or {}).get("necessary_tools")
            ),
        },
        "martial_arts": _present_xianxia_linked_records(
            campaign.slug,
            xianxia.get("martial_arts"),
            default_name="Martial Art",
            include_rank_refs=True,
        ),
        "generic_techniques": _present_xianxia_linked_records(
            campaign.slug,
            xianxia.get("generic_techniques"),
            default_name="Generic Technique",
        ),
        "inventory": {
            "enabled": bool(dict(xianxia_state.get("inventory") or {}).get("enabled")),
            "quantities": _present_xianxia_inventory_records(
                dict(xianxia_state.get("inventory") or {}).get("quantities")
            ),
        },
        "approval": {
            "variants": _present_xianxia_named_records(xianxia.get("variants")),
            "dao_immolating_prepared": _present_xianxia_named_records(
                dao_immolating.get("prepared")
            ),
            "dao_immolating_use_history": _present_xianxia_named_records(
                dao_immolating.get("use_history")
            ),
            "approval_requests": _present_xianxia_named_records(xianxia.get("approval_requests")),
        },
        "active_state": {
            "stance": _present_xianxia_active_state(active_stance, label="Stance"),
            "aura": _present_xianxia_active_state(active_aura, label="Aura"),
        },
        "quick_reference": {
            "defense": xianxia_defense,
            "actions": xianxia_actions,
            "effort_damage": xianxia_effort_damage,
            "check_formula": xianxia_check_formula,
            "difficulty_states": xianxia_difficulty_states,
            "honor_interactions": xianxia_honor_interactions,
            "skill_use_guardrails": xianxia_skill_use_guardrails,
            "rule_text_references": list(xianxia_rule_text_references or []),
            "active_state_reminders": list(xianxia_active_state_reminders or []),
            "stance_break": xianxia_stance_break,
        },
    }


def _text_list(values: Any) -> list[str]:
    return [str(value).strip() for value in list(values or []) if str(value).strip()]


def _present_xianxia_named_records(values: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        payload = dict(value or {}) if isinstance(value, dict) else {"name": value}
        name = str(payload.get("name") or payload.get("title") or "").strip()
        if not name and not payload:
            continue
        records.append(
            {
                "name": name or "Unnamed record",
                "reason": str(payload.get("reason") or "").strip(),
                "status": str(
                    payload.get("status")
                    or payload.get("approval_status")
                    or payload.get("request_status")
                    or ""
                ).strip(),
                "type": str(
                    payload.get("type")
                    or payload.get("variant_type")
                    or payload.get("request_type")
                    or ""
                ).strip(),
                "notes": str(payload.get("notes") or payload.get("approval_notes") or "").strip(),
            }
        )
    return records


def _present_xianxia_inventory_records(values: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        payload = dict(value or {}) if isinstance(value, dict) else {"name": value}
        name = str(
            payload.get("name")
            or payload.get("label")
            or payload.get("id")
            or payload.get("catalog_ref")
            or ""
        ).strip()
        if not name and not payload:
            continue
        records.append(
            {
                "name": name or "Unnamed item",
                "quantity": _coerce_int(payload.get("quantity"), default=0),
                "id": str(payload.get("id") or "").strip(),
                "catalog_ref": str(payload.get("catalog_ref") or "").strip(),
                "notes": str(payload.get("notes") or "").strip(),
            }
        )
    return records


def _present_xianxia_linked_records(
    campaign_slug: str,
    values: Any,
    *,
    default_name: str,
    include_rank_refs: bool = False,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        payload = dict(value or {}) if isinstance(value, dict) else {"name": value}
        systems_ref = dict(payload.get("systems_ref") or {})
        name = str(payload.get("name") or systems_ref.get("title") or default_name).strip()
        href = build_character_entry_href(
            campaign_slug,
            systems_ref=systems_ref,
            page_ref=payload.get("page_ref"),
        )
        record = {
            "name": name or default_name,
            "href": href,
            "systems_ref": systems_ref,
            "current_rank": str(
                payload.get("current_rank")
                or humanize_value(payload.get("current_rank_key"))
                or ""
            ).strip(),
            "current_rank_key": str(payload.get("current_rank_key") or "").strip(),
            "rank_records_status": str(payload.get("rank_records_status") or "").strip(),
            "custom": bool(payload.get("custom_martial_art") or payload.get("xianxia_custom_martial_art")),
            "starting_package": bool(payload.get("starting_package")),
        }
        if include_rank_refs:
            record["learned_rank_refs"] = _present_xianxia_rank_refs(
                list(payload.get("learned_rank_refs") or []),
                parent_href=href,
            )
        records.append(record)
    return records


def _present_xianxia_rank_refs(values: list[Any], *, parent_href: str) -> list[dict[str, str]]:
    rank_refs: list[dict[str, str]] = []
    for value in values:
        ref = str(value or "").strip()
        if not ref:
            continue
        href = f"{parent_href}#{_xianxia_anchor_id_for_ref(ref)}" if parent_href else ""
        rank_refs.append(
            {
                "ref": ref,
                "label": humanize_value(ref.rsplit(":", 1)[-1]) or ref,
                "href": href,
            }
        )
    return rank_refs


def _xianxia_anchor_id_for_ref(value: str) -> str:
    anchor = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower()
    return anchor or "xianxia-ref"


def _present_xianxia_active_state(record: dict[str, Any], *, label: str) -> dict[str, Any]:
    name = str(record.get("name") or "").strip()
    return {
        "label": label,
        "name": name,
        "status_label": f"Active {label}: {name}" if name else f"No active {label} recorded",
        "systems_ref": dict(record.get("systems_ref") or {}),
    }


def build_reference_sections(
    campaign: Campaign,
    definition_payload: dict[str, Any],
    state: dict[str, Any],
    *,
    include_player_notes: bool = True,
) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    profile = dict(definition_payload.get("profile") or {})
    reference_notes = dict(definition_payload.get("reference_notes") or {})

    def add_section(title: str, markdown_text: str) -> None:
        clean_title = title.strip()
        clean_body = markdown_text.strip()
        if not clean_title or not clean_body:
            return
        signature = (clean_title.lower(), clean_body)
        if signature in seen_keys:
            return
        html = render_campaign_markdown(campaign, clean_body)
        if not html:
            return
        seen_keys.add(signature)
        sections.append({"title": clean_title, "html": html})

    add_section("Biography", str(profile.get("biography_markdown") or ""))
    add_section("Personality", str(profile.get("personality_markdown") or ""))

    custom_sections = list(reference_notes.get("custom_sections") or [])
    if not any(str(section.get("title") or "").strip().lower() == "additional notes" for section in custom_sections):
        add_section("Additional Notes", str(reference_notes.get("additional_notes_markdown") or ""))

    add_section(
        "Allies and Organizations",
        str(reference_notes.get("allies_and_organizations_markdown") or ""),
    )

    for section in custom_sections:
        title = str(section.get("title") or "")
        if title.strip().lower().startswith("actions:"):
            continue
        add_section(title, str(section.get("body_markdown") or ""))

    return sections


def build_systems_entry_href(campaign_slug: str, systems_ref: Any) -> str:
    payload = dict(systems_ref or {})
    slug = str(payload.get("slug") or "").strip()
    if not slug or not campaign_slug.strip():
        return ""
    return f"/campaigns/{campaign_slug}/systems/entries/{slug}"


def build_campaign_page_href(campaign_slug: str, page_ref: Any) -> str:
    payload = dict(page_ref or {}) if isinstance(page_ref, dict) else {}
    slug = str(payload.get("slug") or payload.get("page_slug") or "").strip()
    if not slug:
        slug = str(page_ref or "").strip()
    if not slug or not campaign_slug.strip():
        return ""
    return f"/campaigns/{campaign_slug}/pages/{slug}"


def build_character_entry_href(
    campaign_slug: str,
    *,
    systems_ref: Any = None,
    page_ref: Any = None,
) -> str:
    systems_href = build_systems_entry_href(campaign_slug, systems_ref)
    if systems_href:
        return systems_href
    return build_campaign_page_href(campaign_slug, page_ref)


def resolve_feature_description_html(
    campaign: Campaign,
    feature: dict[str, Any],
    *,
    systems_service: Any | None = None,
) -> str:
    description_markdown = str(feature.get("description_markdown") or "").strip()
    if description_markdown:
        return render_campaign_markdown(campaign, description_markdown)
    if systems_service is None:
        return ""
    systems_ref = dict(feature.get("systems_ref") or {})
    slug = str(systems_ref.get("slug") or "").strip()
    if not slug:
        return ""
    entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, slug)
    if entry is None:
        return ""
    return str(systems_service.build_character_sheet_entry_body_html(campaign.slug, entry) or "").strip()


def should_hide_redundant_choice_feature(
    feature: dict[str, Any],
    *,
    has_hit_point_details: bool,
    has_language_details: bool,
    has_proficiency_details: bool,
    has_skill_details: bool,
    has_named_feats: bool,
) -> bool:
    if str(feature.get("tracker_ref") or "").strip():
        return False
    activation_type = str(feature.get("activation_type") or "").strip().lower()
    if activation_type and activation_type != "passive":
        return False

    feature_name = normalize_feature_name(feature.get("name"))
    if feature_name in REDUNDANT_FEATURE_CHOICE_NAMES:
        return True
    if feature_name in REDUNDANT_PASSIVE_FEATURE_NAMES:
        return True
    if feature_name == "hit points":
        return has_hit_point_details
    if feature_name == "proficiencies":
        return has_proficiency_details
    if feature_name == "languages":
        return has_language_details
    if feature_name == "skills":
        return has_skill_details
    if feature_name == "feat":
        return has_named_feats
    return False


def normalize_feature_name(value: Any) -> str:
    return str(value or "").strip().lower()


def render_campaign_markdown(campaign: Campaign, markdown_text: str) -> str:
    clean_text = markdown_text.strip()
    if not clean_text:
        return ""

    alias_index = build_alias_index(campaign)
    resolved_links: list[str] = []
    linked_markdown = render_obsidian_links(clean_text, alias_index, resolved_links)
    renderer = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    html = renderer.convert(linked_markdown)
    return html.replace("/campaigns/{campaign_slug}/", f"/campaigns/{campaign.slug}/")


def summarize_resource_value(resource: dict[str, Any]) -> str:
    current = int(resource.get("current") or 0)
    max_value = resource.get("max")
    if max_value is None:
        return str(current)
    return f"{current} / {int(max_value)}"


def summarize_linked_resource(resource: dict[str, Any] | None) -> str:
    if resource is None:
        return ""
    label = str(resource.get("label") or "Resource")
    summary = summarize_resource_value(resource)
    reset_label = humanize_value(resource.get("reset_on"))
    if reset_label and reset_label not in {"Manual", "Never", "Other"}:
        return f"{label}: {summary} ({reset_label})"
    return f"{label}: {summary}"


def resolve_ability_score_payload(
    ability_scores: dict[str, Any],
    ability_key: str,
    legacy_key: str,
) -> dict[str, Any]:
    payload = ability_scores.get(ability_key)
    if isinstance(payload, dict):
        return dict(payload)
    legacy_payload = ability_scores.get(legacy_key)
    if isinstance(legacy_payload, dict):
        return dict(legacy_payload)
    return {}


def format_signed(value: Any) -> str:
    return f"{int(value or 0):+d}"


def humanize_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").title()


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def spell_level_label(level: int) -> str:
    if level == 1:
        return "1st level"
    if level == 2:
        return "2nd level"
    if level == 3:
        return "3rd level"
    return f"{level}th level"
