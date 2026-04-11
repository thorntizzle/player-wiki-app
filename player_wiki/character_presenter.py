from __future__ import annotations

from collections import OrderedDict
import re
from typing import Any

import markdown

from .character_builder import _spell_access_badge_label, _spell_payload_map_key
from .character_models import CharacterRecord
from .character_profile import (
    profile_class_level_text,
    profile_primary_class_ref,
    profile_primary_subclass_name,
    profile_primary_subclass_ref,
)
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lanes_from_spellcasting
from .models import Campaign
from .repository import build_alias_index, normalize_lookup, render_obsidian_links

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
ATTACK_NAME_SUFFIX_PATTERN = re.compile(r"\s*\([^)]*\)\s*$")


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
) -> dict[str, Any]:
    definition = record.definition
    state = dict(record.state_record.state or {})
    vitals = dict(state.get("vitals") or {})
    stats = dict(definition.stats or {})
    profile = dict(definition.profile or {})
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
            badges = []
            if bool(spell.get("is_bonus_known")):
                badges.append("Feature granted")
            if bool(spell.get("is_always_prepared")) or normalize_lookup("Always prepared") in normalize_lookup(str(spell.get("source") or "").strip()):
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
            if bool(spell.get("is_always_prepared")) and source_label:
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
                    bool(spell.get("is_always_prepared"))
                    or "prepared" in normalized_mark
                )
            )
            in_spellbook = bool(not is_cantrip and "spellbook" in normalized_mark)
            is_fixed = bool(spell.get("is_always_prepared") or spell.get("is_bonus_known"))
            can_toggle_prepared = bool(
                row_kind == "class"
                and row_mode == "wizard"
                and not is_cantrip
                and in_spellbook
                and not bool(spell.get("is_always_prepared"))
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
                "metadata": [part for part in metadata if part],
                "description_html": resolve_feature_description_html(
                    campaign,
                    feature,
                    systems_service=systems_service,
                ),
            }
        )

    attacks = []
    hidden_attacks: list[str] = []
    for attack in list(definition.attacks or []):
        linked_item_refs = resolve_attack_linked_item_refs(
            attack,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        attack_is_equipped = resolve_attack_equipped_state(
            linked_item_refs,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=equipment_catalog_lookup,
        )
        if attack_is_equipped is False:
            hidden_attacks.append(str(attack.get("name") or "Attack"))
            continue
        raw_attack_bonus = attack.get("attack_bonus")
        attack_bonus = format_signed(raw_attack_bonus) if raw_attack_bonus not in {"", None} else ""
        damage = str(attack.get("damage") or "").strip()
        attacks.append(
            {
                "name": str(attack.get("name") or "Attack"),
                "href": build_character_entry_href(
                    campaign.slug,
                    systems_ref=attack.get("systems_ref"),
                    page_ref=attack.get("page_ref"),
                ),
                "attack_bonus": attack_bonus,
                "damage": damage,
                "category": humanize_value(attack.get("category")),
                "notes": str(attack.get("notes") or "").strip(),
                "linked_item_refs": linked_item_refs,
                "is_equipped": attack_is_equipped,
            }
        )

    inventory = [
        {
            "id": str(item.get("id") or ""),
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
        "death_save_summary": death_save_summary,
        "abilities": abilities,
        "skills": skills,
        "proficiency_groups": proficiency_groups,
        "resources": resources,
        "attacks": attacks,
        "hidden_attacks": dedupe_values(hidden_attacks),
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


def resolve_attack_equipped_state(
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
        if bool(inventory_item.get("is_equipped", equipment_item.get("is_equipped", False))):
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
        dict(attack.get("page_ref") or {}).get("title"),
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
        dict(equipment_item.get("page_ref") or {}).get("title"),
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


def spell_level_label(level: int) -> str:
    if level == 1:
        return "1st level"
    if level == 2:
        return "2nd level"
    if level == 3:
        return "3rd level"
    return f"{level}th level"
