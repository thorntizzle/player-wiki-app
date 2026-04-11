from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .auth_store import isoformat, utcnow
from .character_adjustments import (
    apply_manual_stat_adjustments,
    apply_stat_adjustments,
    normalize_manual_stat_adjustments,
    strip_manual_stat_adjustments,
)
from .character_builder import (
    _add_bonus_known_spell_to_payloads,
    _add_spell_to_payloads,
    _ability_scores_from_definition,
    _apply_feat_ability_score_bonuses,
    _apply_campaign_feature_spell_manager_payloads,
    _campaign_option_feat_selections_from_features,
    _automatic_innate_spell_values,
    _automatic_known_spell_values,
    _automatic_prepared_spell_values,
    _automatic_campaign_feature_spell_manager_grants,
    _automatic_spell_support_grants,
    _build_feat_choice_fields_for_selection,
    _build_campaign_feature_spell_manager_fields,
    _build_campaign_page_entry,
    _build_additional_spell_filter_options,
    _build_feature_payload,
    _build_item_catalog,
    _build_spell_support_choice_fields,
    _build_spell_support_replacement_fields,
    _campaign_option_feat_selected_choices_from_features,
    _extract_additional_known_choice_specs,
    _extract_feat_armor_proficiencies,
    _extract_feat_innate_choice_specs,
    _extract_feat_language_proficiencies,
    _extract_feat_prepared_choice_specs,
    _extract_feat_saving_throw_proficiencies,
    _extract_feat_tool_proficiencies,
    _extract_feat_weapon_proficiencies,
    _feat_optionalfeature_sections,
    _merge_spell_mark,
    _prepared_spell_count_for_level,
    _resolve_builder_choices,
    _resolve_spell_entry,
    _spell_access_badge_label,
    _spell_entry_level,
    _spell_list_class_name_for_class,
    _spell_payload_management_row_id,
    _spell_lookup_key,
    _spell_payload_key,
    _spell_payload_map_key,
    _spell_progression_value,
    _spell_selection_values_by_mark,
    _spell_options_are_cantrips,
    _spell_payload_support_kwargs,
    _spellcasting_mode_for_class,
    _strip_definition_campaign_feat_effects,
    normalize_definition_to_native_model,
)
from .character_campaign_options import (
    FEATURE_LIKE_CAMPAIGN_OPTION_KINDS,
    build_campaign_page_character_option,
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
)
from .character_importer import converge_imported_definition
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_profile import ensure_profile_class_rows, profile_primary_class_name, profile_total_level
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lanes_from_spellcasting
from .repository import normalize_lookup
from .repository import slugify
from .systems_models import SystemsEntryRecord

CHARACTER_EDITOR_VERSION = "2026-04-11.01"
CUSTOM_FEATURE_CATEGORY = "custom_feature"
CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"
CUSTOM_FEATURE_TRACKER_PREFIX = "manual-feature-tracker"
CAMPAIGN_ITEMS_SECTION = "Items"
MIN_CUSTOM_FEATURE_ROWS = 3
MIN_CUSTOM_EQUIPMENT_ROWS = 3
SPELL_MANAGEMENT_QUERY_MIN_LENGTH = 2
NATIVE_EDIT_PARENT_FEATURE_ID_KEY = "native_edit_parent_feature_id"
NATIVE_EDIT_OPTIONALFEATURE_SECTION_KEY = "native_edit_optionalfeature_section_index"
NATIVE_EDIT_OPTIONALFEATURE_CHOICE_KEY = "native_edit_optionalfeature_choice_index"
FEATURE_ACTIVATION_OPTIONS = (
    ("passive", "Passive"),
    ("action", "Action"),
    ("bonus_action", "Bonus Action"),
    ("reaction", "Reaction"),
    ("special", "Special"),
)
VALID_FEATURE_ACTIVATION_TYPES = {value for value, _ in FEATURE_ACTIVATION_OPTIONS}
FEATURE_RESOURCE_RESET_OPTIONS = (
    ("manual", "Manual"),
    ("short_rest", "Short Rest"),
    ("long_rest", "Long Rest"),
)
VALID_FEATURE_RESOURCE_RESET_TYPES = {value for value, _ in FEATURE_RESOURCE_RESET_OPTIONS}
STAT_ADJUSTMENT_FIELDS = (
    ("max_hp", "Max HP Adjustment", "Apply a persistent bonus or penalty to max HP."),
    ("armor_class", "Armor Class Adjustment", "Apply a persistent bonus or penalty to Armor Class."),
    ("initiative_bonus", "Initiative Adjustment", "Apply a persistent bonus or penalty to initiative."),
    ("speed", "Speed Adjustment (ft.)", "Apply a persistent speed change in feet."),
    ("passive_perception", "Passive Perception Adjustment", "Apply a persistent bonus or penalty to passive Perception."),
    ("passive_insight", "Passive Insight Adjustment", "Apply a persistent bonus or penalty to passive Insight."),
    ("passive_investigation", "Passive Investigation Adjustment", "Apply a persistent bonus or penalty to passive Investigation."),
)


class CharacterEditValidationError(ValueError):
    pass


def build_character_spell_management_context(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
    selected_class_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    spellcasting = dict(definition.spellcasting or {})

    spell_catalog = dict(spell_catalog or {})
    class_row_payloads = _spell_management_class_rows(
        definition,
        spellcasting=spellcasting,
        selected_class=selected_class,
        selected_class_rows=selected_class_rows,
    )
    if not class_row_payloads:
        return None
    managed_class_rows = [
        row_payload
        for row_payload in class_row_payloads
        if str(row_payload.get("row_kind") or "class").strip() == "class"
    ]
    slot_lanes = spell_slot_lanes_from_spellcasting(spellcasting)
    slot_lanes_by_id = {
        normalize_spell_slot_lane_id(lane.get("id")): dict(lane or {})
        for lane in slot_lanes
    }
    sections = [
        _build_spell_management_section(
            definition,
            spell_catalog=spell_catalog,
            slot_lane=dict(slot_lanes_by_id.get(normalize_spell_slot_lane_id(row_payload.get("slot_lane_id"))) or {}),
            row_payload=row_payload,
            total_spell_rows=len(managed_class_rows),
        )
        for row_payload in class_row_payloads
    ]
    return {
        "sections": sections,
        "is_multiclass": len(managed_class_rows) > 1,
        "shared_slot_label": (
            str((slot_lanes[0] or {}).get("title") or "Spell slots")
            if len(slot_lanes) == 1
            else "Spell slot pools"
        ),
        "slot_progression": list((slot_lanes[0] or {}).get("slot_progression") or []) if len(slot_lanes) == 1 else [],
        "slot_lanes": slot_lanes,
    }


def _feature_spell_management_rows(
    definition: CharacterDefinition,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ability_scores = _spell_management_ability_scores(definition)
    proficiency_bonus = int((definition.stats or {}).get("proficiency_bonus") or 0)
    current_level = max(int(profile_total_level(definition.profile) or 0), 1)

    for feature in list(definition.features or []):
        spell_manager = dict(feature.get("spell_manager") or {})
        source_row_id = str(spell_manager.get("source_row_id") or "").strip()
        if not source_row_id:
            continue
        ability_key = normalize_lookup(str(spell_manager.get("spellcasting_ability_key") or "").strip())
        ability_score = int(ability_scores.get(ability_key, 10) or 10) if ability_key else 10
        ability_modifier = (ability_score - 10) // 2 if ability_key else 0
        max_spell_level_override = None
        formula = str(spell_manager.get("max_spell_level_formula") or "").strip()
        if formula == "ritual_caster_half_level_rounded_up":
            max_spell_level_override = max((current_level + 1) // 2, 1)
        rows.append(
            {
                "class_row_id": source_row_id,
                "class_name": str(spell_manager.get("title") or feature.get("name") or "Feature spells").strip() or "Feature spells",
                "spell_list_class_name": str(spell_manager.get("spell_list_class_name") or "").strip(),
                "level": 0,
                "mode": str(spell_manager.get("mode") or "").strip(),
                "spellcasting_ability": str(spell_manager.get("spellcasting_ability") or "").strip(),
                "spellcasting_ability_key": ability_key,
                "spell_save_dc": 8 + proficiency_bonus + ability_modifier if ability_key else None,
                "spell_attack_bonus": proficiency_bonus + ability_modifier if ability_key else None,
                "selected_class": None,
                "selected_subclass": None,
                "slot_lane_id": "",
                "row_kind": str(spell_manager.get("source_row_kind") or "source").strip() or "source",
                "max_spell_level_override": max_spell_level_override,
            }
        )
    return rows


def _spell_management_class_rows(
    definition: CharacterDefinition,
    *,
    spellcasting: dict[str, Any],
    selected_class: Any | None = None,
    selected_class_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    resolved_rows = {
        str(dict(row or {}).get("class_row_id") or dict(row or {}).get("row_id") or "").strip(): dict(row or {})
        for row in list(selected_class_rows or [])
        if str(dict(row or {}).get("class_row_id") or dict(row or {}).get("row_id") or "").strip()
    }
    results: list[dict[str, Any]] = []
    row_payloads = [dict(row or {}) for row in list(spellcasting.get("class_rows") or []) if isinstance(row, dict)]
    if row_payloads:
        for index, row in enumerate(row_payloads, start=1):
            row_id = str(row.get("class_row_id") or "").strip() or f"class-row-{index}"
            resolved_row = dict(resolved_rows.get(row_id) or {})
            resolved_class = resolved_row.get("selected_class")
            resolved_subclass = resolved_row.get("selected_subclass")
            row_level = int(row.get("level") or 0)
            results.append(
                {
                    "class_row_id": row_id,
                    "class_name": str(row.get("class_name") or "").strip(),
                    "spell_list_class_name": (
                        str(row.get("spell_list_class_name") or "").strip()
                        or _spell_list_class_name_for_class(
                            str(row.get("class_name") or "").strip(),
                            selected_class=resolved_class if isinstance(resolved_class, SystemsEntryRecord) else None,
                            selected_subclass=(
                                resolved_subclass if isinstance(resolved_subclass, SystemsEntryRecord) else None
                            ),
                            row_level=row_level,
                        )
                    ),
                    "level": int(row.get("level") or 0),
                    "mode": str(row.get("spell_mode") or "").strip(),
                    "spellcasting_ability": str(row.get("spellcasting_ability") or "").strip(),
                    "spellcasting_ability_key": "",
                    "spell_save_dc": row.get("spell_save_dc"),
                    "spell_attack_bonus": row.get("spell_attack_bonus"),
                    "selected_class": resolved_class,
                    "selected_subclass": resolved_subclass,
                    "slot_lane_id": normalize_spell_slot_lane_id(row.get("slot_lane_id")),
                    "row_kind": "class",
                }
            )
    else:
        class_name = _spell_management_class_name(definition, spellcasting=spellcasting)
        first_resolved_row = dict(next(iter(resolved_rows.values()), {}) or {})
        selected_subclass = (
            first_resolved_row.get("selected_subclass")
            if isinstance(first_resolved_row.get("selected_subclass"), SystemsEntryRecord)
            else None
        )
        current_level = _character_total_level(definition)
        mode = (
            _spellcasting_mode_for_class(
                class_name,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=current_level,
            )
            if class_name
            else ""
        )
        if class_name and mode:
            first_profile_row = dict((ensure_profile_class_rows(definition.profile) or [{}])[0] or {})
            results.append(
                {
                    "class_row_id": str(first_profile_row.get("row_id") or "class-row-1"),
                    "class_name": class_name,
                    "spell_list_class_name": _spell_list_class_name_for_class(
                        class_name,
                        selected_class=selected_class if isinstance(selected_class, SystemsEntryRecord) else None,
                        selected_subclass=selected_subclass,
                        row_level=current_level,
                    ),
                    "level": current_level,
                    "mode": mode,
                    "spellcasting_ability": str(spellcasting.get("spellcasting_ability") or "").strip(),
                    "spellcasting_ability_key": "",
                    "spell_save_dc": spellcasting.get("spell_save_dc"),
                    "spell_attack_bonus": spellcasting.get("spell_attack_bonus"),
                    "selected_class": selected_class if isinstance(selected_class, SystemsEntryRecord) else None,
                    "selected_subclass": selected_subclass,
                    "slot_lane_id": "",
                    "row_kind": "class",
                }
            )

    for row in list(spellcasting.get("source_rows") or []):
        payload = dict(row or {})
        source_row_id = str(payload.get("source_row_id") or "").strip()
        if not source_row_id:
            continue
        results.append(
            {
                "class_row_id": source_row_id,
                "class_name": str(payload.get("title") or "").strip() or "Feature spells",
                "spell_list_class_name": str(payload.get("spell_list_class_name") or "").strip(),
                "level": 0,
                "mode": str(payload.get("spell_mode") or "").strip(),
                "spellcasting_ability": str(payload.get("spellcasting_ability") or "").strip(),
                "spellcasting_ability_key": "",
                "spell_save_dc": payload.get("spell_save_dc"),
                "spell_attack_bonus": payload.get("spell_attack_bonus"),
                "selected_class": None,
                "selected_subclass": None,
                "slot_lane_id": "",
                "row_kind": str(payload.get("source_row_kind") or "source").strip() or "source",
                "max_spell_level_override": payload.get("max_spell_level_override"),
            }
        )
    row_index_by_id = {
        str(row.get("class_row_id") or "").strip(): index
        for index, row in enumerate(results)
        if str(row.get("class_row_id") or "").strip()
    }
    for row_payload in _feature_spell_management_rows(definition):
        row_id = str(row_payload.get("class_row_id") or "").strip()
        if not row_id:
            continue
        existing_index = row_index_by_id.get(row_id)
        if existing_index is None:
            row_index_by_id[row_id] = len(results)
            results.append(row_payload)
            continue
        existing_payload = results[existing_index]
        if str(existing_payload.get("row_kind") or "source").strip() == "source" and str(
            row_payload.get("row_kind") or ""
        ).strip():
            existing_payload["row_kind"] = str(row_payload.get("row_kind") or "").strip()
        for key in (
            "class_name",
            "spell_list_class_name",
            "mode",
            "spellcasting_ability",
            "spellcasting_ability_key",
            "spell_save_dc",
            "spell_attack_bonus",
            "max_spell_level_override",
        ):
            if existing_payload.get(key) in {"", None} and row_payload.get(key) not in {"", None}:
                existing_payload[key] = row_payload.get(key)
    return results


def _build_spell_management_section(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any],
    slot_lane: dict[str, Any],
    row_payload: dict[str, Any],
    total_spell_rows: int,
) -> dict[str, Any]:
    class_name = str(row_payload.get("class_name") or "").strip()
    spell_list_class_name = str(row_payload.get("spell_list_class_name") or class_name).strip()
    mode = str(row_payload.get("mode") or "").strip()
    row_kind = str(row_payload.get("row_kind") or "class").strip() or "class"
    current_level = int(row_payload.get("level") or 0)
    selected_class = row_payload.get("selected_class")
    selected_subclass = row_payload.get("selected_subclass")
    class_row_id = str(row_payload.get("class_row_id") or "").strip()
    slot_progression = [dict(slot or {}) for slot in list(slot_lane.get("slot_progression") or [])]
    max_spell_level = int(row_payload.get("max_spell_level_override") or 0)
    if max_spell_level <= 0:
        max_spell_level = max((int(slot.get("level") or 0) for slot in slot_progression), default=0)
    unavailable_message = ""
    if mode == "ritual_book":
        if not spell_list_class_name:
            unavailable_message = "This ritual book does not currently have a valid class spell list to manage."
    elif row_kind != "class":
        unavailable_message = "Feat-granted spells stay read-only here in this slice."
    elif not class_name or not mode:
        unavailable_message = "This sheet does not currently have a supported class spellcasting model to edit here."

    rows = _build_spell_management_rows(
        definition,
        spell_catalog=spell_catalog,
        mode=mode,
        class_name=class_name,
        class_row_id=class_row_id,
        total_spell_rows=total_spell_rows,
        row_kind=row_kind,
    )

    mutable_cantrip_count = sum(1 for row in rows if row["counts_against_cantrip_limit"])
    mutable_known_count = sum(1 for row in rows if row["counts_against_known_limit"])
    mutable_prepared_count = sum(1 for row in rows if row["counts_against_prepared_limit"])
    mutable_spellbook_count = sum(1 for row in rows if row["counts_against_spellbook_total"])
    mutable_ritual_book_count = sum(1 for row in rows if row["counts_against_ritual_book_total"])
    fixed_spell_count = sum(1 for row in rows if row["is_fixed"])

    ability_scores = _spell_management_ability_scores(definition)
    target_cantrip_count = (
        _spell_progression_value(
            class_name,
            "cantrip_progression",
            current_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        if class_name and mode
        else 0
    )
    target_known_count = (
        _spell_progression_value(
            class_name,
            "spells_known_progression",
            current_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        if mode == "known"
        else 0
    )
    target_prepared_count = (
        _prepared_spell_count_for_level(
            class_name,
            ability_scores,
            current_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        if mode in {"prepared", "wizard"}
        else 0
    )

    counts: list[dict[str, str]] = []
    if target_cantrip_count:
        counts.append({"label": "Cantrips", "value": f"{mutable_cantrip_count} / {target_cantrip_count}"})
    if mode == "known":
        counts.append({"label": "Known spells", "value": f"{mutable_known_count} / {target_known_count}"})
    elif mode == "prepared":
        counts.append({"label": "Prepared spells", "value": f"{mutable_prepared_count} / {target_prepared_count}"})
    elif mode == "wizard":
        counts.append({"label": "Prepared spells", "value": f"{mutable_prepared_count} / {target_prepared_count}"})
        counts.append({"label": "Spellbook spells", "value": str(mutable_spellbook_count)})
    elif mode == "ritual_book":
        counts.append({"label": "Ritual book spells", "value": str(mutable_ritual_book_count)})
    if fixed_spell_count:
        counts.append({"label": "Fixed feature spells", "value": str(fixed_spell_count)})

    can_manage = bool(
        mode
        and (class_name or spell_list_class_name)
        and not unavailable_message
        and list(spell_catalog.get("entries") or [])
        and (
            row_kind == "class"
            or mode == "ritual_book"
        )
    )
    if not can_manage and not unavailable_message and mode:
        unavailable_message = "Enable Systems spell entries in this campaign to manage spells from the character sheet."

    spell_add_label = {
        "known": "Add known spell",
        "prepared": "Prepare spell",
        "wizard": "Add spellbook spell",
        "ritual_book": "Add ritual spell",
    }.get(mode, "Add spell")
    rules_note = {
        "known": (
            "Classic known-spell casters keep a fixed list of leveled spells they know. "
            "Use this manager to maintain that durable list and its cantrips."
        ),
        "prepared": (
            "Classic prepared casters choose daily prepared spells from their class list. "
            "Always-prepared feature spells stay fixed and do not count against the prepared total shown here."
        ),
        "wizard": (
            "Wizards prepare spells from their spellbook. Add new spells to the spellbook here, "
            "then mark which spellbook spells are currently prepared."
        ),
        "ritual_book": (
            f"This ritual book draws from the {spell_list_class_name} ritual list. "
            f"Add ritual spells up through level {max_spell_level} as the character earns or finds them."
            if spell_list_class_name and max_spell_level > 0
            else "This ritual book holds ritual spells from one chosen class list."
        ),
    }.get(mode, "")
    if row_kind == "feat" and mode != "ritual_book":
        rules_note = "Feat-granted spell packages are preserved on the sheet here, but stay read-only in this slice."
    elif row_kind != "class" and mode != "ritual_book":
        rules_note = "Feature-granted spell packages are preserved on the sheet here, but stay read-only in this slice."

    return {
        "class_row_id": class_row_id,
        "class_name": class_name,
        "spell_list_class_name": spell_list_class_name,
        "mode": mode,
        "row_kind": row_kind,
        "mode_label": (
            "Ritual book"
            if mode == "ritual_book"
            else (
                "Feat spells"
                if row_kind == "feat"
                else (
                    "Feature spells"
                    if row_kind != "class"
                    else {
                        "known": "Known spells",
                        "prepared": "Prepared spells",
                        "wizard": "Wizard spellbook",
                    }.get(mode, "Spellcasting")
                )
            )
        ),
        "title": f"{class_name} {current_level}" if class_name and current_level > 0 else class_name or "Spellcasting",
        "current_level": current_level,
        "max_spell_level": max_spell_level,
        "target_cantrip_count": target_cantrip_count,
        "target_known_count": target_known_count,
        "target_prepared_count": target_prepared_count,
        "current_cantrip_count": mutable_cantrip_count,
        "current_known_count": mutable_known_count,
        "current_prepared_count": mutable_prepared_count,
        "current_spellbook_count": mutable_spellbook_count,
        "current_ritual_book_count": mutable_ritual_book_count,
        "counts": counts,
        "rows": rows,
        "can_manage": can_manage,
        "unavailable_message": unavailable_message,
        "rules_note": rules_note,
        "show_cantrip_form": bool(mode and target_cantrip_count),
        "can_add_cantrip": bool(can_manage and mutable_cantrip_count < target_cantrip_count),
        "show_spell_form": bool(mode and max_spell_level > 0),
        "can_add_spell": bool(
            can_manage
            and max_spell_level > 0
            and (
                mode in {"wizard", "ritual_book"}
                or (mode == "known" and mutable_known_count < target_known_count)
                or (mode == "prepared" and mutable_prepared_count < target_prepared_count)
            )
        ),
        "spell_add_kind": (
            "spellbook"
            if mode == "wizard"
            else ("ritual_book" if mode == "ritual_book" else "spell")
        ),
        "spell_add_label": spell_add_label,
        "spellcasting_ability": str(row_payload.get("spellcasting_ability") or "").strip(),
        "spellcasting_ability_key": str(row_payload.get("spellcasting_ability_key") or "").strip(),
        "spell_save_dc": row_payload.get("spell_save_dc"),
        "spell_attack_bonus": row_payload.get("spell_attack_bonus"),
    }


def search_character_spell_management_options(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
    selected_class_rows: list[dict[str, Any]] | None = None,
    query: str,
    kind: str,
    target_class_row_id: str = "",
    limit: int = 20,
) -> tuple[list[dict[str, str]], str]:
    manager = build_character_spell_management_context(
        definition,
        spell_catalog=spell_catalog,
        selected_class=selected_class,
        selected_class_rows=selected_class_rows,
    )
    if manager is None:
        return [], "This sheet does not currently have spellcasting content."
    section = _resolve_spell_management_section(manager, target_class_row_id)
    if section is None:
        return [], "Choose a valid spellcasting class row."
    if not section.get("can_manage"):
        return [], str(section.get("unavailable_message") or "This sheet cannot manage spells here yet.")

    clean_kind = str(kind or "").strip().lower()
    if clean_kind not in {"cantrip", "spell", "spellbook", "ritual_book"}:
        return [], "Choose a valid spell search type."
    if clean_kind == "spellbook" and section.get("mode") != "wizard":
        return [], "Only wizard sheets use spellbook additions."
    if clean_kind == "ritual_book" and section.get("mode") != "ritual_book":
        return [], "Only ritual-book sheets use ritual spell additions."

    clean_query = normalize_lookup(query)
    if len(clean_query) < SPELL_MANAGEMENT_QUERY_MIN_LENGTH:
        return [], "Type at least 2 letters to search eligible spells."

    class_name = str(section.get("spell_list_class_name") or section.get("class_name") or "").strip()
    max_spell_level = int(section.get("max_spell_level") or 0)
    existing_keys = {
        str(row.get("catalog_key") or row.get("spell_key") or "").strip()
        for row in list(section.get("rows") or [])
        if str(row.get("catalog_key") or row.get("spell_key") or "").strip()
    }
    results: list[dict[str, str]] = []
    catalog_entries = sorted(
        list((spell_catalog or {}).get("entries") or []),
        key=lambda entry: (int(_spell_entry_level(entry)), str(entry.title or "").lower()),
    )
    for entry in catalog_entries:
        if not _spell_entry_matches_management_class_list(entry, class_name):
            continue
        level = _spell_entry_level(entry)
        if clean_kind == "cantrip":
            if level != 0:
                continue
        else:
            if level <= 0 or level > max_spell_level:
                continue
        if clean_kind == "ritual_book" and not bool(dict(getattr(entry, "metadata", {}) or {}).get("ritual")):
            continue
        if str(entry.slug or "").strip() in existing_keys:
            continue
        searchable_text = normalize_lookup(f"{entry.title} {entry.search_text}")
        if clean_query not in searchable_text:
            continue
        level_label = _spell_management_level_label(level)
        subtitle = " - ".join(part for part in (level_label, str(entry.source_id or "").strip()) if part)
        select_label = f"{entry.title} - {subtitle}" if subtitle else entry.title
        results.append(
            {
                "entry_slug": str(entry.slug or "").strip(),
                "title": str(entry.title or "").strip(),
                "level_label": level_label,
                "source_id": str(entry.source_id or "").strip(),
                "select_label": select_label,
            }
        )
        if len(results) >= limit:
            break

    if results:
        label = "cantrips" if clean_kind == "cantrip" else ("ritual spells" if clean_kind == "ritual_book" else "spells")
        return results, f"Found {len(results)} matching {label}."
    if clean_kind == "ritual_book":
        return [], "No eligible ritual spells matched that search."
    return [], "No eligible class spells matched that search."


def apply_character_spell_management_edit(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
    selected_class_rows: list[dict[str, Any]] | None = None,
    systems_service: Any | None = None,
    operation: str,
    spell_key: str = "",
    selected_value: str = "",
    kind: str = "",
    prepared_value: str = "",
    target_class_row_id: str = "",
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    manager = build_character_spell_management_context(
        current_definition,
        spell_catalog=spell_catalog,
        selected_class=selected_class,
        selected_class_rows=selected_class_rows,
    )
    if manager is None:
        raise CharacterEditValidationError("This sheet does not currently have spellcasting content.")
    section = _resolve_spell_management_section(manager, target_class_row_id)
    if section is None:
        raise CharacterEditValidationError("Choose a valid spellcasting class row.")
    if not section.get("can_manage"):
        raise CharacterEditValidationError(
            str(section.get("unavailable_message") or "This sheet cannot manage spells here yet.")
        )

    rows_by_key = {
        str(row.get("spell_key") or "").strip(): dict(row)
        for section_rows in [list(candidate.get("rows") or []) for candidate in list(manager.get("sections") or [])]
        for row in section_rows
        if str(row.get("spell_key") or "").strip()
    }
    spells_by_key = {
        key: deepcopy(dict(row.get("payload") or {}))
        for key, row in rows_by_key.items()
    }
    catalog_keys = {
        str(row.get("catalog_key") or row.get("spell_key") or "").strip()
        for row in list(section.get("rows") or [])
        if str(row.get("catalog_key") or row.get("spell_key") or "").strip()
    }
    clean_operation = str(operation or "").strip().lower()
    clean_kind = str(kind or "").strip().lower()
    clean_spell_key = str(spell_key or "").strip()
    clean_selected_value = str(selected_value or "").strip()
    clean_mode = str(section.get("mode") or "").strip()
    clean_target_class_row_id = str(section.get("class_row_id") or target_class_row_id or "").strip()
    support_kwargs = _spell_management_section_support_kwargs(section)
    if clean_spell_key and clean_spell_key not in rows_by_key and clean_target_class_row_id and "::" not in clean_spell_key:
        fallback_key = f"{clean_target_class_row_id}::{clean_spell_key}"
        if fallback_key in rows_by_key:
            clean_spell_key = fallback_key

    if clean_operation == "add":
        if not clean_selected_value:
            raise CharacterEditValidationError("Choose a spell to add.")
        resolved_entry = _resolve_spell_entry(clean_selected_value, dict(spell_catalog or {}))
        resolved_key = (
            str(resolved_entry.slug or "").strip()
            if resolved_entry is not None
            else _spell_lookup_key(clean_selected_value, dict(spell_catalog or {}))
        )
        if resolved_key in catalog_keys:
            raise CharacterEditValidationError("That spell is already on this sheet.")
        if clean_kind == "cantrip":
            if not bool(section.get("can_add_cantrip")):
                raise CharacterEditValidationError("This sheet is already at its current cantrip count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Cantrip",
                class_row_id=clean_target_class_row_id,
            )
        elif clean_kind == "spell" and clean_mode == "known":
            if not bool(section.get("can_add_spell")):
                raise CharacterEditValidationError("This sheet is already at its current known-spell count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Known",
                class_row_id=clean_target_class_row_id,
            )
        elif clean_kind == "spell" and clean_mode == "prepared":
            if not bool(section.get("can_add_spell")):
                raise CharacterEditValidationError("This sheet is already at its current prepared-spell count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Prepared",
                class_row_id=clean_target_class_row_id,
            )
        elif clean_kind == "spellbook" and clean_mode == "wizard":
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Spellbook",
                class_row_id=clean_target_class_row_id,
            )
        elif clean_kind == "ritual_book" and clean_mode == "ritual_book":
            if not bool(section.get("can_add_spell")):
                raise CharacterEditValidationError("This ritual book cannot add more spells right now.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Ritual Book",
                is_ritual=True,
                class_row_id=clean_target_class_row_id,
                **support_kwargs,
            )
        else:
            raise CharacterEditValidationError("Choose a valid spell-management action.")
    elif clean_operation == "remove":
        row = rows_by_key.get(clean_spell_key)
        if row is None:
            raise CharacterEditValidationError("Choose a valid spell to remove.")
        if not bool(row.get("can_remove")):
            raise CharacterEditValidationError("That spell is fixed by class or feature rules and cannot be removed here.")
        spells_by_key.pop(clean_spell_key, None)
    elif clean_operation == "update":
        row = rows_by_key.get(clean_spell_key)
        if row is None:
            raise CharacterEditValidationError("Choose a valid spell to update.")
        if not bool(row.get("can_toggle_prepared")):
            raise CharacterEditValidationError("That spell cannot have its prepared state changed here.")
        set_prepared = str(prepared_value or "").strip() in {"1", "true", "yes", "on"}
        if (
            set_prepared
            and not bool(row.get("is_prepared"))
            and clean_mode == "wizard"
            and int(section.get("current_prepared_count") or 0) >= int(section.get("target_prepared_count") or 0)
        ):
            raise CharacterEditValidationError("This wizard is already at the current prepared-spell count.")
        payload = deepcopy(spells_by_key.get(clean_spell_key) or {})
        payload["mark"] = "Prepared + Spellbook" if set_prepared else "Spellbook"
        spells_by_key[clean_spell_key] = payload
    else:
        raise CharacterEditValidationError("Choose a valid spell-management action.")

    payload = deepcopy(current_definition.to_dict())
    next_spellcasting = dict(payload.get("spellcasting") or {})
    next_spellcasting["spells"] = sorted(
        list(spells_by_key.values()),
        key=lambda value: _spell_management_payload_sort_key(value, dict(spell_catalog or {})),
    )
    payload["spellcasting"] = next_spellcasting

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            resolved_class=selected_class if isinstance(selected_class, SystemsEntryRecord) else None,
        )
    else:
        definition = normalize_definition_to_native_model(
            definition,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            resolved_class=selected_class if isinstance(selected_class, SystemsEntryRecord) else None,
        )
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata, {}


def _spell_management_section_support_kwargs(section: dict[str, Any]) -> dict[str, Any]:
    row_kind = str(section.get("row_kind") or "class").strip() or "class"
    if row_kind == "class":
        return {}
    source_row_id = str(section.get("class_row_id") or "").strip()
    if not source_row_id:
        return {}
    support_kwargs = {
        "spell_source_row_id": source_row_id,
        "spell_source_row_kind": row_kind,
        "spell_source_row_title": str(section.get("class_name") or "").strip(),
        "spell_source_ability_key": str(section.get("spellcasting_ability_key") or "").strip(),
        "spell_source_mode": str(section.get("mode") or "").strip(),
        "spell_source_spell_list_class_name": str(section.get("spell_list_class_name") or "").strip(),
        "grant_source_label": str(section.get("class_name") or "").strip(),
    }
    return {
        key: value
        for key, value in support_kwargs.items()
        if value not in {"", None}
    }


def _resolve_spell_management_section(
    manager: dict[str, Any],
    target_class_row_id: str,
) -> dict[str, Any] | None:
    sections = [dict(section or {}) for section in list(manager.get("sections") or []) if isinstance(section, dict)]
    if not sections:
        return None
    clean_target = str(target_class_row_id or "").strip()
    if clean_target:
        for section in sections:
            if str(section.get("class_row_id") or "").strip() == clean_target:
                return section
        return None
    return dict(sections[0] or {})


def _spell_management_class_name(
    definition: CharacterDefinition,
    *,
    spellcasting: dict[str, Any],
) -> str:
    clean_spellcasting_class = str(spellcasting.get("spellcasting_class") or "").strip()
    if clean_spellcasting_class:
        return clean_spellcasting_class

    return profile_primary_class_name(definition.profile)


def _spell_management_ability_scores(definition: CharacterDefinition) -> dict[str, int]:
    ability_scores_payload = dict((definition.stats or {}).get("ability_scores") or {})
    return {
        ability_key: int(dict(ability_scores_payload.get(ability_key) or {}).get("score") or 10)
        for ability_key in ("str", "dex", "con", "int", "wis", "cha")
    }


def _build_spell_management_rows(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any],
    mode: str,
    class_name: str,
    class_row_id: str,
    total_spell_rows: int,
    row_kind: str = "class",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_spell_payload in list((definition.spellcasting or {}).get("spells") or []):
        payload_row_id = _spell_payload_management_row_id(dict(raw_spell_payload or {}))
        if class_row_id:
            if payload_row_id and payload_row_id != class_row_id:
                continue
            if not payload_row_id and total_spell_rows > 1:
                continue
        normalized_payload, spell_entry, spell_level = _normalize_spell_management_payload(
            raw_spell_payload,
            spell_catalog=spell_catalog,
            mode=mode,
            class_name=class_name,
        )
        if class_row_id and row_kind == "class" and not _spell_payload_management_row_id(normalized_payload):
            normalized_payload["class_row_id"] = class_row_id
        spell_key = _spell_payload_map_key(normalized_payload)
        if not spell_key:
            continue

        normalized_mark = normalize_lookup(str(normalized_payload.get("mark") or "").strip())
        source_label = str(
            normalized_payload.get("grant_source_label")
            or normalized_payload.get("source")
            or ""
        ).strip()
        is_cantrip = spell_level == 0
        is_prepared = bool(
            not is_cantrip
            and (
                bool(normalized_payload.get("is_always_prepared"))
                or "prepared" in normalized_mark
            )
        )
        in_spellbook = bool(not is_cantrip and "spellbook" in normalized_mark)
        in_ritual_book = bool(
            not is_cantrip
            and (
                "ritual book" in normalized_mark
                or mode == "ritual_book"
            )
        )
        is_fixed = bool(normalized_payload.get("is_always_prepared") or normalized_payload.get("is_bonus_known"))

        managed_group = ""
        if is_cantrip:
            managed_group = "cantrip"
        elif mode == "known":
            managed_group = "known"
        elif mode == "prepared":
            managed_group = "prepared"
        elif mode == "wizard":
            managed_group = "spellbook"
        elif mode == "ritual_book":
            managed_group = "ritual_book"

        badges: list[str] = []
        if is_cantrip:
            badges.append("Cantrip")
        elif mode == "wizard" and in_spellbook:
            badges.append("Spellbook")
        elif mode == "ritual_book" and in_ritual_book:
            badges.append("Ritual book")
        elif mode == "known":
            badges.append("Known")
        elif mode == "prepared" or is_prepared:
            badges.append("Prepared")
        if bool(normalized_payload.get("is_always_prepared")):
            badges.append("Always prepared")
        elif bool(normalized_payload.get("is_bonus_known")):
            badges.append("Feature granted")
        access_badge = _spell_access_badge_label(normalized_payload)
        if access_badge and access_badge not in badges:
            badges.append(access_badge)
        mark = str(normalized_payload.get("mark") or "").strip()
        if mark and mark not in {"Cantrip", "Known", "Prepared", "Spellbook", "Prepared + Spellbook"} and mark not in badges:
            badges.append(mark)

        management_note = ""
        if bool(normalized_payload.get("is_always_prepared")) and source_label:
            management_note = f"Always prepared from {source_label}."
        elif bool(normalized_payload.get("is_bonus_known")) and source_label:
            management_note = f"Granted by {source_label}."

        rows.append(
            {
                "spell_key": spell_key,
                "catalog_key": (
                    str(spell_entry.slug or "").strip()
                    if spell_entry is not None
                    else spell_key
                ),
                "name": str(normalized_payload.get("name") or spell_key).strip() or spell_key,
                "payload": normalized_payload,
                "spell_level": spell_level,
                "level_label": _spell_management_level_label(spell_level),
                "is_cantrip": is_cantrip,
                "is_fixed": is_fixed,
                "is_prepared": is_prepared,
                "in_spellbook": in_spellbook,
                "managed_group": managed_group,
                "badges": badges,
                "management_note": management_note,
                "counts_against_cantrip_limit": bool(is_cantrip and not bool(normalized_payload.get("is_bonus_known"))),
                "counts_against_known_limit": bool(
                    not is_cantrip
                    and managed_group == "known"
                    and not bool(normalized_payload.get("is_bonus_known"))
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "counts_against_prepared_limit": bool(
                    not is_cantrip
                    and is_prepared
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "counts_against_spellbook_total": bool(not is_cantrip and in_spellbook),
                "counts_against_ritual_book_total": bool(not is_cantrip and in_ritual_book),
                "can_remove": bool((row_kind == "class" or mode == "ritual_book") and not is_fixed),
                "can_toggle_prepared": bool(
                    row_kind == "class"
                    and mode == "wizard"
                    and not is_cantrip
                    and in_spellbook
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "remove_label": _spell_management_remove_label(
                    mode=mode,
                    is_cantrip=is_cantrip,
                    is_prepared=is_prepared,
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: _spell_management_payload_sort_key(dict(row.get("payload") or {}), spell_catalog),
    )


def _normalize_spell_management_payload(
    raw_spell_payload: dict[str, Any],
    *,
    spell_catalog: dict[str, Any],
    mode: str,
    class_name: str,
) -> tuple[dict[str, Any], Any | None, int]:
    payload = deepcopy(dict(raw_spell_payload or {}))
    spell_entry = _spell_management_entry_for_payload(payload, spell_catalog)
    if spell_entry is not None and not dict(payload.get("systems_ref") or {}):
        payload["systems_ref"] = {
            "entry_key": str(spell_entry.entry_key or "").strip(),
            "entry_type": str(spell_entry.entry_type or "").strip(),
            "title": str(spell_entry.title or "").strip(),
            "slug": str(spell_entry.slug or "").strip(),
            "source_id": str(spell_entry.source_id or "").strip(),
        }

    spell_level = _spell_entry_level(spell_entry) if spell_entry is not None else int(payload.get("level") or 0)
    source_label = str(payload.get("source") or "").strip()
    normalized_source = normalize_lookup(source_label)
    normalized_mark = normalize_lookup(str(payload.get("mark") or "").strip())
    always_prepared = bool(payload.get("is_always_prepared")) or normalize_lookup("always prepared") in normalized_source
    feature_grant = _spell_management_is_feature_grant_source(
        source_label,
        class_name=class_name,
        spell_payload=payload,
    )
    bonus_known = bool(payload.get("is_bonus_known")) or feature_grant

    payload["is_always_prepared"] = always_prepared
    payload["is_bonus_known"] = bonus_known

    if spell_level == 0:
        payload["mark"] = "Cantrip"
        return payload, spell_entry, spell_level

    if mode == "wizard":
        if "spellbook" in normalized_mark:
            payload["mark"] = "Prepared + Spellbook" if "prepared" in normalized_mark else "Spellbook"
        elif normalized_mark in {"o", "p", "po"} or not normalized_mark:
            payload["mark"] = "Prepared + Spellbook"
        elif "prepared" in normalized_mark:
            payload["mark"] = "Prepared + Spellbook"
        else:
            payload["mark"] = "Spellbook"
        if always_prepared and "prepared" not in normalize_lookup(str(payload.get("mark") or "")):
            payload["mark"] = "Prepared + Spellbook"
        return payload, spell_entry, spell_level

    if mode == "ritual_book":
        payload["mark"] = "Ritual Book"
        if spell_level > 0:
            payload["is_ritual"] = bool(payload.get("is_ritual") or dict((spell_entry.metadata if spell_entry is not None else {}) or {}).get("ritual"))
        return payload, spell_entry, spell_level

    if mode == "prepared":
        payload["mark"] = "Prepared"
        return payload, spell_entry, spell_level

    if mode == "known":
        payload["mark"] = "Known"
        return payload, spell_entry, spell_level

    if normalized_mark == "o":
        payload["mark"] = ""
    elif normalized_mark == "p":
        payload["mark"] = "Prepared"
    elif normalized_mark == "po":
        payload["mark"] = "Prepared"
    return payload, spell_entry, spell_level


def _spell_management_entry_for_payload(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
):
    payload_key = _spell_payload_key(spell_payload)
    if payload_key:
        spell_entry = _resolve_spell_entry(payload_key, spell_catalog)
        if spell_entry is not None:
            return spell_entry
    spell_name = str(spell_payload.get("name") or "").strip()
    if spell_name:
        return _resolve_spell_entry(spell_name, spell_catalog)
    return None


def _spell_management_is_feature_grant_source(
    source_label: str,
    *,
    class_name: str,
    spell_payload: dict[str, Any],
) -> bool:
    clean_source = normalize_lookup(source_label)
    clean_class_name = normalize_lookup(class_name)
    clean_systems_source = normalize_lookup(str(dict(spell_payload.get("systems_ref") or {}).get("source_id") or ""))
    if not clean_source or not clean_class_name:
        return False
    if clean_systems_source and clean_source == clean_systems_source:
        return False
    if clean_source == clean_class_name:
        return False
    if clean_source.startswith(f"{clean_class_name} "):
        return False
    return True


def _spell_entry_matches_management_class_list(entry, class_name: str) -> bool:
    metadata = dict((getattr(entry, "metadata", {}) or {}))
    class_lists = dict(metadata.get("class_lists") or {})
    clean_class_name = normalize_lookup(class_name)
    for class_names in class_lists.values():
        for candidate in list(class_names or []):
            if normalize_lookup(candidate) == clean_class_name:
                return True
    return False


def _spell_management_payload_sort_key(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> tuple[int, str]:
    spell_entry = _spell_management_entry_for_payload(spell_payload, spell_catalog)
    spell_level = _spell_entry_level(spell_entry) if spell_entry is not None else int(spell_payload.get("level") or 0)
    spell_name = str((spell_entry.title if spell_entry is not None else spell_payload.get("name")) or "").strip()
    return spell_level, spell_name.lower(), spell_name


def _spell_management_level_label(level: int) -> str:
    clean_level = int(level or 0)
    if clean_level <= 0:
        return "Cantrip"
    if clean_level == 1:
        return "1st-level"
    if clean_level == 2:
        return "2nd-level"
    if clean_level == 3:
        return "3rd-level"
    return f"{clean_level}th-level"


def _spell_management_remove_label(*, mode: str, is_cantrip: bool, is_prepared: bool) -> str:
    if is_cantrip:
        return "Remove cantrip"
    if mode == "prepared" and is_prepared:
        return "Unprepare spell"
    if mode == "wizard":
        return "Remove from spellbook"
    if mode == "ritual_book":
        return "Remove from ritual book"
    return "Remove spell"


def build_managed_character_import_metadata(
    campaign_slug: str,
    character_slug: str,
    current_import_metadata: CharacterImportMetadata,
    *,
    parser_version: str = CHARACTER_EDITOR_VERSION,
) -> CharacterImportMetadata:
    return CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        source_path=str(
            current_import_metadata.source_path or f"managed://{campaign_slug}/{character_slug}"
        ),
        imported_at_utc=isoformat(utcnow()),
        parser_version=parser_version,
        import_status="managed",
        warnings=[],
    )


def normalize_custom_equipment_entry(
    *,
    name: str,
    quantity: str | int,
    weight: str = "",
    notes: str = "",
    existing_item: dict[str, Any] | None = None,
    raw_id: str = "",
    used_item_ids: set[str] | None = None,
    page_ref: str = "",
    campaign_option: dict[str, Any] | None = None,
    systems_ref: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise CharacterEditValidationError("Each custom equipment row needs an item name.")

    parsed_quantity = _parse_manual_item_quantity(str(quantity or "").strip())
    normalized_page_ref = str(page_ref or "").strip()
    normalized_campaign_option = dict(campaign_option or {})
    normalized_systems_ref = {
        key: value
        for key, value in dict(systems_ref or {}).items()
        if str(key or "").strip() and value not in (None, "", [], {})
    }

    existing = deepcopy(existing_item or {})
    existing.pop("campaign_option", None)
    existing.pop("systems_ref", None)
    existing.pop("page_ref", None)

    reserved_ids = set(used_item_ids or set())
    preserved_id = str(raw_id or existing.get("id") or "").strip()
    if preserved_id:
        reserved_ids.discard(preserved_id)
    item_id = preserved_id or _build_unique_manual_id("manual-item", clean_name, reserved_ids)
    reserved_ids.add(item_id)

    existing.update(
        {
            "id": item_id,
            "name": clean_name,
            "default_quantity": parsed_quantity,
            "weight": str(weight or "").strip(),
            "notes": str(notes or "").strip(),
            "source_kind": CUSTOM_EQUIPMENT_SOURCE_KIND,
            "campaign_option": normalized_campaign_option or None,
        }
    )
    if normalized_page_ref:
        existing["page_ref"] = normalized_page_ref
    if normalized_systems_ref:
        existing["systems_ref"] = normalized_systems_ref
    return existing, parsed_quantity


def apply_equipment_catalog_edit(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    item_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    target_item_id: str | None = None,
    remove_item_id: str | None = None,
    name: str = "",
    quantity: str | int = "",
    weight: str = "",
    notes: str = "",
    page_ref: str = "",
    systems_ref: dict[str, Any] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    manual_items = _manual_equipment_entries(current_definition)
    manual_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in manual_items
        if str(item.get("id") or "").strip()
    }

    normalized_remove_item_id = str(remove_item_id or "").strip()
    if normalized_remove_item_id:
        if normalized_remove_item_id not in manual_item_lookup:
            raise CharacterEditValidationError("Choose a valid supplemental equipment entry to remove.")
        next_manual_items = [
            dict(item)
            for item in manual_items
            if str(item.get("id") or "").strip() != normalized_remove_item_id
        ]
        quantity_overrides: dict[str, int] = {}
    else:
        normalized_target_item_id = str(target_item_id or "").strip()
        existing_item = manual_item_lookup.get(normalized_target_item_id) if normalized_target_item_id else None
        if normalized_target_item_id and existing_item is None:
            raise CharacterEditValidationError("Choose a valid supplemental equipment entry to update.")

        normalized_page_ref = _normalize_selected_campaign_page_ref(page_ref, campaign_page_lookup)
        campaign_option = _editable_campaign_option_for_page_ref(
            normalized_page_ref,
            campaign_page_lookup,
            default_kind="item",
        )
        resolved_name = str(
            name
            or (campaign_option or {}).get("item_name")
            or (campaign_page_lookup.get(normalized_page_ref) or {}).get("title")
            or ""
        ).strip()
        used_item_ids = set(manual_item_lookup.keys())
        if normalized_target_item_id:
            used_item_ids.discard(normalized_target_item_id)
        next_item, parsed_quantity = normalize_custom_equipment_entry(
            name=resolved_name,
            quantity=quantity,
            weight=weight,
            notes=notes,
            existing_item=existing_item,
            raw_id=normalized_target_item_id,
            used_item_ids=used_item_ids,
            page_ref=normalized_page_ref,
            campaign_option=campaign_option,
            systems_ref=systems_ref,
        )
        next_manual_items = [
            dict(item)
            for item in manual_items
            if str(item.get("id") or "").strip() != str(next_item.get("id") or "").strip()
        ]
        next_manual_items.append(next_item)
        quantity_overrides = {str(next_item.get("id") or "").strip(): parsed_quantity}

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["equipment_catalog"] = [
        dict(item)
        for item in list(current_definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
    ] + next_manual_items

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
            item_catalog=item_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
    else:
        definition = normalize_definition_to_native_model(
            definition,
            item_catalog=item_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata, quantity_overrides


def apply_equipment_state_edit(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    item_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    target_item_id: str,
    is_equipped: bool,
    is_attuned: bool,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    normalized_target_item_id = str(target_item_id or "").strip()
    if not normalized_target_item_id:
        raise CharacterEditValidationError("Choose a valid equipment entry to update.")

    found_target = False
    next_equipment_catalog: list[dict[str, Any]] = []
    for item in list(current_definition.equipment_catalog or []):
        item_payload = dict(item or {})
        if str(item_payload.get("id") or "").strip() == normalized_target_item_id:
            item_payload["is_equipped"] = bool(is_equipped)
            item_payload["is_attuned"] = bool(is_attuned)
            found_target = True
        next_equipment_catalog.append(item_payload)

    if not found_target:
        raise CharacterEditValidationError("Choose a valid equipment entry to update.")

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["equipment_catalog"] = next_equipment_catalog

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
            item_catalog=item_catalog,
            systems_service=systems_service,
        )
    else:
        definition = normalize_definition_to_native_model(
            definition,
            item_catalog=item_catalog,
            systems_service=systems_service,
        )
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata


def build_native_character_edit_context(
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = dict(form_values or {})
    optionalfeature_catalog = dict(optionalfeature_catalog or {})
    spell_catalog = dict(spell_catalog or {})
    item_catalog = dict(item_catalog or _build_item_catalog([]))
    proficiency_lists = _display_proficiency_lists_for_editor(definition)
    manual_features = _manual_custom_features(definition)
    manual_items = _manual_equipment_entries(definition)
    resource_template_lookup = {
        str(template.get("id") or "").strip(): dict(template)
        for template in list(definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    stat_adjustments = normalize_manual_stat_adjustments((definition.stats or {}).get("manual_adjustments"))
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    generated_optionalfeature_selections = _native_edit_optionalfeature_selection_lookup(definition)
    campaign_page_options = _build_campaign_page_options(campaign_page_records or [])
    equipment_linked_page_refs = {
        _extract_page_ref_value(item.get("page_ref"))
        for item in list(manual_items or [])
        if _extract_page_ref_value(item.get("page_ref"))
    }
    equipment_page_options = _build_campaign_page_options(
        campaign_page_records or [],
        allowed_sections={CAMPAIGN_ITEMS_SECTION},
        include_page_refs=equipment_linked_page_refs,
    )
    current_level = _character_total_level(definition)

    proficiency_fields = [
        {
            "name": "languages_text",
            "label": "Languages",
            "help_text": "One entry per line. Save the full list you want on the sheet.",
            "value": str(
                values.get("languages_text")
                or _join_multiline_values(proficiency_lists.get("languages") or [])
            ),
        },
        {
            "name": "armor_proficiencies_text",
            "label": "Armor Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("armor_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("armor") or [])
            ),
        },
        {
            "name": "weapon_proficiencies_text",
            "label": "Weapon Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("weapon_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("weapons") or [])
            ),
        },
        {
            "name": "tool_proficiencies_text",
            "label": "Tool Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("tool_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("tools") or [])
            ),
        },
    ]
    reference_fields = [
        {
            "name": "biography_markdown",
            "label": "Biography",
            "help_text": "Markdown shown on the Notes page for reference-level character history.",
            "value": str(values.get("biography_markdown") or (definition.profile or {}).get("biography_markdown") or ""),
        },
        {
            "name": "personality_markdown",
            "label": "Personality",
            "help_text": "Markdown shown on the Notes page for personality traits, ideals, bonds, flaws, or similar notes.",
            "value": str(values.get("personality_markdown") or (definition.profile or {}).get("personality_markdown") or ""),
        },
        {
            "name": "additional_notes_markdown",
            "label": "Additional Notes",
            "help_text": "Markdown shown on the Notes page for other persistent reference material.",
            "value": str(
                values.get("additional_notes_markdown")
                or (definition.reference_notes or {}).get("additional_notes_markdown")
                or ""
            ),
        },
        {
            "name": "allies_and_organizations_markdown",
            "label": "Allies and Organizations",
            "help_text": "Markdown shown on the Notes page for friendly factions, patrons, allies, or affiliations.",
            "value": str(
                values.get("allies_and_organizations_markdown")
                or (definition.reference_notes or {}).get("allies_and_organizations_markdown")
                or ""
            ),
        },
    ]
    stat_adjustment_fields = [
        {
            "name": f"stat_adjustment_{key}",
            "label": label,
            "help_text": help_text,
            "value": str(values.get(f"stat_adjustment_{key}") or stat_adjustments.get(key) or "").strip(),
        }
        for key, label, help_text in STAT_ADJUSTMENT_FIELDS
    ]

    feature_row_count = max(
        len(manual_features) + 1,
        _max_row_index(values, "custom_feature"),
        MIN_CUSTOM_FEATURE_ROWS,
    )
    feature_rows = []
    for index in range(1, feature_row_count + 1):
        existing = manual_features[index - 1] if index - 1 < len(manual_features) else {}
        tracker = resource_template_lookup.get(str(existing.get("tracker_ref") or "").strip(), {})
        page_ref = str(
            values.get(f"custom_feature_page_ref_{index}")
            or _extract_page_ref_value(existing.get("page_ref"))
            or ""
        ).strip()
        campaign_option = dict(
            _editable_campaign_option_for_page_ref(
                page_ref,
                campaign_page_lookup,
                default_kind="feature",
            )
            or {}
        )
        stored_selected_choices = dict(dict(existing.get("campaign_option") or {}).get("selected_choices") or {})
        if stored_selected_choices:
            campaign_option["selected_choices"] = stored_selected_choices
        feature_rows.append(
            {
                "index": index,
                "id": str(values.get(f"custom_feature_id_{index}") or existing.get("id") or "").strip(),
                "name": str(values.get(f"custom_feature_name_{index}") or existing.get("name") or "").strip(),
                "page_ref": page_ref,
                "activation_type": _normalize_activation_type(
                    values.get(f"custom_feature_activation_type_{index}")
                    or existing.get("activation_type")
                    or "passive"
                ),
                "description_markdown": str(
                    values.get(f"custom_feature_description_{index}")
                    or existing.get("description_markdown")
                    or ""
                ),
                "resource_max": str(
                    values.get(f"custom_feature_resource_max_{index}")
                    or tracker.get("max")
                    or ""
                ).strip(),
                "resource_reset_on": _normalize_resource_reset_on(
                    values.get(f"custom_feature_resource_reset_on_{index}")
                    or tracker.get("reset_on")
                    or "manual"
                ),
                "spell_manager": dict(existing.get("spell_manager") or {}),
                "campaign_option": campaign_option,
            }
        )

    equipment_row_count = max(
        len(manual_items) + 1,
        _max_row_index(values, "manual_item"),
        MIN_CUSTOM_EQUIPMENT_ROWS,
    )
    equipment_rows = []
    for index in range(1, equipment_row_count + 1):
        existing = manual_items[index - 1] if index - 1 < len(manual_items) else {}
        equipment_rows.append(
            {
                "index": index,
                "id": str(values.get(f"manual_item_id_{index}") or existing.get("id") or "").strip(),
                "name": str(values.get(f"manual_item_name_{index}") or existing.get("name") or "").strip(),
                "page_ref": str(
                    values.get(f"manual_item_page_ref_{index}")
                    or _extract_page_ref_value(existing.get("page_ref"))
                    or ""
                ).strip(),
                "quantity": str(
                    values.get(f"manual_item_quantity_{index}")
                    or existing.get("default_quantity")
                    or ""
                ).strip(),
                "weight": str(values.get(f"manual_item_weight_{index}") or existing.get("weight") or "").strip(),
                "notes": str(values.get(f"manual_item_notes_{index}") or existing.get("notes") or ""),
                "campaign_option": dict(_editable_campaign_option_for_page_ref(
                    str(
                        values.get(f"manual_item_page_ref_{index}")
                        or _extract_page_ref_value(existing.get("page_ref"))
                        or ""
                    ).strip(),
                    campaign_page_lookup,
                    default_kind="item",
                ) or {}),
            }
        )

    feature_rows = _attach_spell_fields_to_feature_rows(
        feature_rows=feature_rows,
        equipment_rows=equipment_rows,
        current_spellcasting=definition.spellcasting,
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
    )
    for row in feature_rows:
        existing_selection_map = generated_optionalfeature_selections.get(str(row.get("id") or "").strip(), {})
        feat_choice_fields = _build_editor_feat_choice_fields_for_row(
            row=row,
            values=values,
            item_catalog=item_catalog,
        )
        optionalfeature_fields = _build_editor_optionalfeature_fields_for_row(
            row=row,
            campaign_page_lookup=campaign_page_lookup,
            optionalfeature_catalog=optionalfeature_catalog,
            values=values,
            selected_choices=existing_selection_map,
        )
        row["choice_fields"] = (
            feat_choice_fields
            + optionalfeature_fields
            + list(row.get("spell_fields") or [])
        )

    return {
        "values": values,
        "proficiency_fields": proficiency_fields,
        "reference_fields": reference_fields,
        "stat_adjustment_fields": stat_adjustment_fields,
        "feature_rows": feature_rows,
        "equipment_rows": equipment_rows,
        "activation_options": [
            {"value": value, "label": label}
            for value, label in FEATURE_ACTIVATION_OPTIONS
        ],
        "resource_reset_options": [
            {"value": value, "label": label}
            for value, label in FEATURE_RESOURCE_RESET_OPTIONS
        ],
        "campaign_page_options": campaign_page_options,
        "equipment_page_options": equipment_page_options,
        "existing_managed_equipment": [
            {
                "name": str(item.get("name") or "Item"),
                "quantity": int(item.get("default_quantity") or 0),
                "weight": str(item.get("weight") or "").strip(),
            }
            for item in list(definition.equipment_catalog or [])
            if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
        ],
    }


def apply_native_character_edits(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    item_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    values = dict(form_values or {})
    optionalfeature_catalog = dict(optionalfeature_catalog or {})
    item_catalog = dict(item_catalog or _build_item_catalog([]))
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    equipment_linked_page_refs = {
        _extract_page_ref_value(item.get("page_ref"))
        for item in _manual_equipment_entries(current_definition)
        if _extract_page_ref_value(item.get("page_ref"))
    }
    equipment_campaign_page_lookup = _build_campaign_page_lookup(
        campaign_page_records or [],
        allowed_sections={CAMPAIGN_ITEMS_SECTION},
        include_page_refs=equipment_linked_page_refs,
    )
    manual_feature_lookup = {
        str(feature.get("id") or "").strip(): dict(feature)
        for feature in _manual_custom_features(current_definition)
        if str(feature.get("id") or "").strip()
    }
    existing_manual_tracker_ids = {
        _manual_feature_tracker_id(str(feature.get("id") or "").strip())
        for feature in _manual_custom_features(current_definition)
        if str(feature.get("id") or "").strip()
    }
    resource_template_lookup = {
        str(template.get("id") or "").strip(): dict(template)
        for template in list(current_definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    manual_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in _manual_equipment_entries(current_definition)
        if str(item.get("id") or "").strip()
    }
    existing_campaign_option_payloads = _campaign_option_payloads_from_entries(
        _manual_custom_features(current_definition),
        _manual_equipment_entries(current_definition),
    )
    spell_catalog = dict(spell_catalog or {})
    current_level = _character_total_level(current_definition)
    stripped_definition = _strip_definition_campaign_feat_effects(
        current_definition,
        selected_class=None,
    )

    manual_proficiencies = {
        "languages": _parse_multiline_values(values.get("languages_text", "")),
        "armor": _parse_multiline_values(values.get("armor_proficiencies_text", "")),
        "weapons": _parse_multiline_values(values.get("weapon_proficiencies_text", "")),
        "tools": _parse_multiline_values(values.get("tool_proficiencies_text", "")),
    }
    reference_notes = dict(current_definition.reference_notes or {})
    reference_notes["additional_notes_markdown"] = str(values.get("additional_notes_markdown") or "")
    reference_notes["allies_and_organizations_markdown"] = str(values.get("allies_and_organizations_markdown") or "")
    profile = dict(current_definition.profile or {})
    profile["biography_markdown"] = str(values.get("biography_markdown") or "")
    profile["personality_markdown"] = str(values.get("personality_markdown") or "")
    base_stats, _ = strip_manual_stat_adjustments(dict(stripped_definition.stats or {}))
    existing_campaign_stat_adjustments = collect_campaign_option_stat_adjustments(existing_campaign_option_payloads)
    if existing_campaign_stat_adjustments:
        base_stats = apply_stat_adjustments(
            base_stats,
            {key: -int(value) for key, value in existing_campaign_stat_adjustments.items()},
        )
    stat_adjustments = _parse_stat_adjustments(values)

    used_feature_ids = set(manual_feature_lookup.keys())
    manual_features: list[dict[str, Any]] = []
    manual_resource_templates: list[dict[str, Any]] = []
    generated_optionalfeature_features: list[dict[str, Any]] = []
    selected_additional_spell_entries: list[dict[str, Any]] = []
    selected_spell_support_entries: list[dict[str, Any]] = []
    selected_spell_manager_entries: list[dict[str, Any]] = []
    seen_feature_names: set[str] = set()
    feat_selected_choices: dict[str, list[str]] = {}
    for index in range(1, max(_max_row_index(values, "custom_feature"), MIN_CUSTOM_FEATURE_ROWS) + 1):
        raw_id = str(values.get(f"custom_feature_id_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"custom_feature_page_ref_{index}") or "",
            campaign_page_lookup,
        )
        campaign_option = _editable_campaign_option_for_page_ref(
            page_ref,
            campaign_page_lookup,
            default_kind="feature",
        )
        name = str(
            values.get(f"custom_feature_name_{index}")
            or (campaign_option or {}).get("feature_name")
            or (campaign_page_lookup.get(page_ref) or {}).get("title")
            or ""
        ).strip()
        description_markdown = str(
            values.get(f"custom_feature_description_{index}")
            or (campaign_option or {}).get("description_markdown")
            or ""
        )
        activation_type = _normalize_activation_type(
            values.get(f"custom_feature_activation_type_{index}")
            or (campaign_option or {}).get("activation_type")
            or "passive"
        )
        resource_max = _parse_optional_nonnegative_integer(
            values.get(f"custom_feature_resource_max_{index}")
            or ((campaign_option or {}).get("resource") or {}).get("max")
            or "",
            field_label=f"resource max for '{name or f'custom feature {index}'}'",
        )
        has_content = bool(name or page_ref or description_markdown.strip() or resource_max)
        if not has_content:
            continue
        if not name:
            raise CharacterEditValidationError("Each custom feature needs a name.")
        if activation_type not in VALID_FEATURE_ACTIVATION_TYPES:
            raise CharacterEditValidationError("Choose a valid activation type for each custom feature.")
        normalized_name = slugify(name)
        if normalized_name in seen_feature_names:
            raise CharacterEditValidationError(f"Custom feature '{name}' is listed more than once.")
        seen_feature_names.add(normalized_name)

        existing = deepcopy(manual_feature_lookup.get(raw_id) or {})
        existing.pop("campaign_option", None)
        existing.pop("systems_ref", None)
        existing.pop("page_ref", None)
        feature_id = raw_id or _build_unique_manual_id("custom-feature", name, used_feature_ids)
        used_feature_ids.add(feature_id)
        existing.update(
            {
                "id": feature_id,
                "name": name,
                "category": CUSTOM_FEATURE_CATEGORY,
                "source": str(existing.get("source") or "Campaign").strip() or "Campaign",
                "description_markdown": description_markdown.strip(),
                "activation_type": activation_type,
                "tracker_ref": None,
                "campaign_option": dict(campaign_option or {}) or None,
            }
        )
        feat_choice_fields = _build_editor_feat_choice_fields_for_row(
            row=existing,
            values=values,
            item_catalog=item_catalog,
        )
        if feat_choice_fields:
            _unused_fixed_proficiencies, selected_feat_choices = _resolve_builder_choices(
                [{"fields": feat_choice_fields}],
                values,
            )
            serialized_feat_choices = _serialize_editor_feat_selected_choices(
                selection=_editor_feat_choice_selection(existing),
                selected_choices=selected_feat_choices,
            )
            if dict(existing.get("campaign_option") or {}) is not None:
                campaign_option_payload = dict(existing.get("campaign_option") or {})
                if serialized_feat_choices:
                    campaign_option_payload["selected_choices"] = serialized_feat_choices
                else:
                    campaign_option_payload.pop("selected_choices", None)
                existing["campaign_option"] = campaign_option_payload or None
            feat_selected_choices.update(selected_feat_choices)
        resource_reset_on = _normalize_resource_reset_on(
            values.get(f"custom_feature_resource_reset_on_{index}")
            or ((campaign_option or {}).get("resource") or {}).get("reset_on")
            or "manual"
        )
        if page_ref:
            existing["page_ref"] = page_ref
        if dict(campaign_option or {}).get("additional_spells"):
            selected_additional_spell_entries.append(
                {
                    "field_prefix": _editor_additional_spell_field_prefix(index),
                    "campaign_option": dict(campaign_option or {}),
                    "source_ref": str(page_ref or (campaign_option or {}).get("title") or name).strip(),
                }
            )
        if dict(campaign_option or {}).get("spell_support"):
            selected_spell_support_entries.append(
                {
                    "field_prefix": f"custom_feature_spell_support_{index}",
                    "campaign_option": dict(campaign_option or {}),
                    "source_ref": str(page_ref or (campaign_option or {}).get("title") or name).strip(),
                }
            )
        if dict(campaign_option or {}).get("spell_manager"):
            selected_spell_manager_entries.append(
                {
                    "field_prefix": _editor_spell_manager_field_prefix(index),
                    "campaign_option": dict(campaign_option or {}),
                    "page_ref": page_ref,
                    "feature_name": name,
                    "source_ref": str(page_ref or (campaign_option or {}).get("title") or name).strip(),
                }
            )
            spell_manager_feature_entry = _apply_campaign_feature_spell_manager_payloads(
                [
                    {
                        "campaign_option": dict(campaign_option or {}),
                        "page_ref": page_ref,
                        "name": name,
                        "label": name,
                    }
                ],
                values=values,
                field_prefix_base=_editor_spell_manager_field_prefix(index),
            )
            spell_manager_payload = dict((spell_manager_feature_entry[0] if spell_manager_feature_entry else {}).get("spell_manager") or {})
            if spell_manager_payload:
                existing["spell_manager"] = spell_manager_payload
        if resource_max:
            tracker_id = _manual_feature_tracker_id(feature_id)
            existing["tracker_ref"] = tracker_id
            manual_resource_templates.append(
                _build_manual_feature_resource_template(
                    tracker_id=tracker_id,
                    feature_name=name,
                    max_value=resource_max,
                    reset_on=resource_reset_on,
                    existing_template=resource_template_lookup.get(tracker_id),
                    display_order=len(manual_resource_templates),
                )
            )
        manual_features.append(existing)
        generated_optionalfeature_features.extend(
            _build_editor_selected_optionalfeature_features(
                row_index=index,
                parent_feature_id=feature_id,
                campaign_page_lookup=campaign_page_lookup,
                optionalfeature_catalog=optionalfeature_catalog,
                values=values,
                page_ref=page_ref,
            )
        )

    used_item_ids = set(manual_item_lookup.keys())
    inventory_quantity_overrides: dict[str, int] = {}
    manual_items: list[dict[str, Any]] = []
    for index in range(1, max(_max_row_index(values, "manual_item"), MIN_CUSTOM_EQUIPMENT_ROWS) + 1):
        raw_id = str(values.get(f"manual_item_id_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"manual_item_page_ref_{index}") or "",
            equipment_campaign_page_lookup,
        )
        campaign_option = _editable_campaign_option_for_page_ref(
            page_ref,
            equipment_campaign_page_lookup,
            default_kind="item",
        )
        name = str(
            values.get(f"manual_item_name_{index}")
            or (campaign_option or {}).get("item_name")
            or (equipment_campaign_page_lookup.get(page_ref) or {}).get("title")
            or ""
        ).strip()
        quantity_text = str(
            values.get(f"manual_item_quantity_{index}")
            or (campaign_option or {}).get("quantity")
            or ""
        ).strip()
        weight = str(
            values.get(f"manual_item_weight_{index}")
            or (campaign_option or {}).get("weight")
            or ""
        ).strip()
        notes = str(
            values.get(f"manual_item_notes_{index}")
            or (campaign_option or {}).get("notes")
            or ""
        )
        has_content = bool(name or page_ref or quantity_text or weight or notes.strip())
        if not has_content:
            continue
        next_item, quantity = normalize_custom_equipment_entry(
            name=name,
            quantity=quantity_text,
            weight=weight,
            notes=notes,
            existing_item=manual_item_lookup.get(raw_id),
            raw_id=raw_id,
            used_item_ids=used_item_ids,
            page_ref=page_ref,
            campaign_option=campaign_option,
        )
        used_item_ids.add(str(next_item.get("id") or "").strip())
        manual_items.append(next_item)
        inventory_quantity_overrides[str(next_item.get("id") or "").strip()] = quantity

    selected_campaign_option_payloads = _campaign_option_payloads_from_entries(
        manual_features,
        manual_items,
    )
    campaign_feat_selections = _campaign_option_feat_selections_from_features(manual_features)
    proficiencies = _merge_editor_proficiencies(
        manual_proficiencies,
        selected_campaign_option_payloads,
        feat_selections=campaign_feat_selections,
        feat_selected_choices=feat_selected_choices,
    )
    stats = apply_manual_stat_adjustments(base_stats, stat_adjustments)
    campaign_stat_adjustments = collect_campaign_option_stat_adjustments(selected_campaign_option_payloads)
    if campaign_stat_adjustments:
        stats = apply_stat_adjustments(stats, campaign_stat_adjustments)
    updated_ability_scores = _apply_feat_ability_score_bonuses(
        _ability_scores_from_definition(stripped_definition),
        feat_selections=campaign_feat_selections,
        selected_choices=feat_selected_choices,
        strict=False,
    )
    ability_payloads = dict(stats.get("ability_scores") or {})
    for ability_key, score in updated_ability_scores.items():
        ability_payload = dict(ability_payloads.get(ability_key) or {})
        modifier = (int(score) - 10) // 2
        ability_payload["score"] = int(score)
        ability_payload["modifier"] = modifier
        ability_payloads[ability_key] = ability_payload
    proficiency_bonus = int(stats.get("proficiency_bonus") or 0)
    for ability_key in _extract_feat_saving_throw_proficiencies(
        campaign_feat_selections,
        feat_selected_choices,
    ):
        ability_payload = dict(ability_payloads.get(ability_key) or {})
        modifier = int(ability_payload.get("modifier") or 0)
        try:
            current_save_bonus = int(ability_payload.get("save_bonus"))
        except (TypeError, ValueError):
            current_save_bonus = modifier
        if proficiency_bonus > 0 and current_save_bonus - modifier < proficiency_bonus:
            ability_payload["save_bonus"] = modifier + proficiency_bonus
        else:
            ability_payload["save_bonus"] = current_save_bonus
        ability_payloads[ability_key] = ability_payload
    if ability_payloads:
        stats["ability_scores"] = ability_payloads
    spellcasting = _apply_campaign_option_spells_to_spellcasting(
        current_definition.spellcasting,
        existing_campaign_option_payloads=existing_campaign_option_payloads,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
        selected_additional_spell_entries=selected_additional_spell_entries,
        selected_spell_support_entries=selected_spell_support_entries,
        selected_spell_manager_entries=selected_spell_manager_entries,
    )

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["profile"] = profile
    payload["stats"] = stats
    payload["proficiencies"] = proficiencies
    payload["skills"] = [dict(row or {}) for row in list(stripped_definition.skills or [])]
    payload["spellcasting"] = spellcasting
    payload["reference_notes"] = reference_notes
    payload["features"] = [
        dict(feature)
        for feature in list(current_definition.features or [])
        if str(feature.get("category") or "") != CUSTOM_FEATURE_CATEGORY
        and not _is_native_edit_generated_feature(feature)
    ] + manual_features + generated_optionalfeature_features
    payload["equipment_catalog"] = [
        dict(item)
        for item in list(current_definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
    ] + manual_items
    payload["resource_templates"] = [
        dict(template)
        for template in list(current_definition.resource_templates or [])
        if str(template.get("id") or "").strip() not in existing_manual_tracker_ids
    ] + manual_resource_templates

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
    else:
        definition = normalize_definition_to_native_model(
            definition,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata, inventory_quantity_overrides


def _manual_custom_features(definition: CharacterDefinition) -> list[dict[str, Any]]:
    return [
        dict(feature)
        for feature in list(definition.features or [])
        if str(feature.get("category") or "") == CUSTOM_FEATURE_CATEGORY
    ]


def _is_native_edit_generated_feature(feature: dict[str, Any]) -> bool:
    return bool(str(feature.get(NATIVE_EDIT_PARENT_FEATURE_ID_KEY) or "").strip())


def _native_edit_optionalfeature_selection_lookup(
    definition: CharacterDefinition,
) -> dict[str, dict[tuple[int, int], str]]:
    selections: dict[str, dict[tuple[int, int], str]] = {}
    for feature in list(definition.features or []):
        parent_feature_id = str(feature.get(NATIVE_EDIT_PARENT_FEATURE_ID_KEY) or "").strip()
        if not parent_feature_id:
            continue
        systems_ref = dict(feature.get("systems_ref") or {})
        selected_slug = str(systems_ref.get("slug") or "").strip()
        if not selected_slug:
            continue
        try:
            section_index = int(feature.get(NATIVE_EDIT_OPTIONALFEATURE_SECTION_KEY) or 0)
            choice_index = int(feature.get(NATIVE_EDIT_OPTIONALFEATURE_CHOICE_KEY) or 0)
        except (TypeError, ValueError):
            continue
        if section_index <= 0 or choice_index <= 0:
            continue
        selections.setdefault(parent_feature_id, {})[(section_index, choice_index)] = selected_slug
    return selections


def _manual_equipment_entries(definition: CharacterDefinition) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") == CUSTOM_EQUIPMENT_SOURCE_KIND
    ]


def _campaign_option_payloads_from_entries(
    features: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in list(features or []) + list(items or []):
        option = dict(entry.get("campaign_option") or {})
        if option:
            payloads.append(option)
    return payloads


def _display_proficiency_lists_for_editor(definition: CharacterDefinition) -> dict[str, list[str]]:
    proficiencies = {
        key: list((definition.proficiencies or {}).get(key) or [])
        for key in ("languages", "armor", "weapons", "tools")
    }
    manual_features = _manual_custom_features(definition)
    campaign_grants = collect_campaign_option_proficiency_grants(
        _campaign_option_payloads_from_entries(
            manual_features,
            _manual_equipment_entries(definition),
        )
    )
    campaign_feat_selections = _campaign_option_feat_selections_from_features(manual_features)
    feat_selected_choices = _campaign_option_feat_selected_choices_from_features(manual_features)
    campaign_feat_proficiencies = {
        "armor": _extract_feat_armor_proficiencies(campaign_feat_selections, feat_selected_choices),
        "weapons": _extract_feat_weapon_proficiencies(campaign_feat_selections, feat_selected_choices),
        "tools": _extract_feat_tool_proficiencies(campaign_feat_selections, feat_selected_choices),
        "languages": _extract_feat_language_proficiencies(campaign_feat_selections, feat_selected_choices),
    }
    return {
        key: _subtract_casefold_values(
            _subtract_casefold_values(proficiencies[key], campaign_grants.get(key) or []),
            campaign_feat_proficiencies.get(key) or [],
        )
        for key in proficiencies
    }


def _editable_campaign_option_for_page_ref(
    page_ref: str,
    campaign_page_lookup: dict[str, dict[str, Any]],
    *,
    default_kind: str,
) -> dict[str, Any] | None:
    option = dict((campaign_page_lookup.get(page_ref) or {}).get("campaign_option") or {})
    if not option:
        return None
    kind = str(option.get("kind") or default_kind or "").strip().lower()
    allowed_kinds = (
        FEATURE_LIKE_CAMPAIGN_OPTION_KINDS
        if default_kind == "feature"
        else {default_kind}
    )
    if kind and kind not in allowed_kinds:
        return None
    return option


def _editable_campaign_feat_entry_for_page_ref(
    page_ref: str,
    campaign_page_lookup: dict[str, dict[str, Any]],
) -> SystemsEntryRecord | None:
    record = (campaign_page_lookup.get(page_ref) or {}).get("record")
    if record is None:
        return None
    entry = _build_campaign_page_entry(record, kind="feat")
    return entry if isinstance(entry, SystemsEntryRecord) else None


def _merge_editor_proficiencies(
    manual_proficiencies: dict[str, list[str]],
    option_payloads: list[dict[str, Any]],
    *,
    feat_selections: list[dict[str, Any]] | None = None,
    feat_selected_choices: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    campaign_grants = collect_campaign_option_proficiency_grants(option_payloads)
    campaign_feat_selections = list(feat_selections or [])
    selected_choices = dict(feat_selected_choices or {})
    campaign_feat_proficiencies = {
        "armor": _extract_feat_armor_proficiencies(campaign_feat_selections, selected_choices),
        "weapons": _extract_feat_weapon_proficiencies(campaign_feat_selections, selected_choices),
        "tools": _extract_feat_tool_proficiencies(campaign_feat_selections, selected_choices),
        "languages": _extract_feat_language_proficiencies(campaign_feat_selections, selected_choices),
    }
    return {
        key: _dedupe_casefold_values(
            list(manual_proficiencies.get(key) or [])
            + list(campaign_grants.get(key) or [])
            + list(campaign_feat_proficiencies.get(key) or [])
        )
        for key in ("languages", "armor", "weapons", "tools")
    }


def _attach_spell_fields_to_feature_rows(
    *,
    feature_rows: list[dict[str, Any]],
    equipment_rows: list[dict[str, Any]],
    current_spellcasting: dict[str, Any] | None,
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(feature_rows or [])]
    if not rows or not spell_catalog:
        for row in rows:
            row["spell_fields"] = []
        return rows

    tracked_spell_payloads = [
        _normalize_spell_payload_for_campaign_option_tracking(payload)
        for payload in _campaign_option_tracked_spell_payloads(current_spellcasting)
    ]
    provisional_values = dict(values)
    for row in rows:
        additional_fields = _build_editor_additional_spell_choice_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"] = additional_fields
        for field in additional_fields:
            field_name = str(field.get("name") or "").strip()
            selected_value = str(field.get("selected") or "").strip()
            if field_name and selected_value and not str(provisional_values.get(field_name) or "").strip():
                provisional_values[field_name] = selected_value
        choice_fields = _build_editor_spell_support_choice_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"].extend(choice_fields)
        for field in choice_fields:
            field_name = str(field.get("name") or "").strip()
            selected_value = str(field.get("selected") or "").strip()
            if field_name and selected_value and not str(provisional_values.get(field_name) or "").strip():
                provisional_values[field_name] = selected_value
        manager_fields = _build_editor_spell_manager_choice_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"].extend(manager_fields)
        for field in manager_fields:
            field_name = str(field.get("name") or "").strip()
            selected_value = str(field.get("selected") or "").strip()
            if field_name and selected_value and not str(provisional_values.get(field_name) or "").strip():
                provisional_values[field_name] = selected_value

    provisional_spell_payloads = _build_provisional_editor_spell_payloads(
        current_spellcasting=current_spellcasting,
        feature_rows=rows,
        equipment_rows=equipment_rows,
        spell_catalog=spell_catalog,
        values=provisional_values,
        current_level=current_level,
    )
    for row in rows:
        replacement_fields = _build_editor_spell_support_replacement_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            provisional_spell_payloads=provisional_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"].extend(replacement_fields)
    return rows


def _editor_optionalfeature_field_name(
    row_index: int,
    section_index: int,
    choice_index: int,
) -> str:
    return f"custom_feature_optionalfeature_{row_index}_{section_index}_{choice_index}"


def _editor_feat_choice_selection(row: dict[str, Any]) -> dict[str, Any] | None:
    feature_payload = dict(row or {})
    if not str(feature_payload.get("id") or "").strip():
        provisional_name = str(feature_payload.get("name") or "").strip()
        provisional_slug = slugify(provisional_name)
        if provisional_slug:
            feature_payload["id"] = f"custom-feature-{provisional_slug}"
    selections = _campaign_option_feat_selections_from_features([feature_payload])
    return dict(selections[0] or {}) if selections else None


def _build_editor_feat_choice_fields_for_row(
    *,
    row: dict[str, Any],
    values: dict[str, str],
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    selection = _editor_feat_choice_selection(row)
    if not selection:
        return []
    stored_choice_map = _campaign_option_feat_selected_choices_from_features([dict(row or {})])
    raw_fields = _build_feat_choice_fields_for_selection(
        selection=selection,
        values={},
        optionalfeature_catalog={},
        item_catalog=item_catalog,
    )
    fields = [
        dict(field)
        for field in raw_fields
        if str(field.get("kind") or "").strip()
        not in {"feat_optionalfeature", "feat_spell_source"}
    ]
    group_positions: dict[str, int] = {}
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        selected_value = str(values.get(field_name) or "").strip()
        if not selected_value:
            group_key = str(field.get("group_key") or field_name).strip()
            choice_index = int(group_positions.get(group_key) or 0)
            selected_values = list(stored_choice_map.get(group_key) or [])
            if choice_index < len(selected_values):
                selected_value = str(selected_values[choice_index] or "").strip()
            group_positions[group_key] = choice_index + 1
        field["selected"] = selected_value
    return fields


def _serialize_editor_feat_selected_choices(
    *,
    selection: dict[str, Any] | None,
    selected_choices: dict[str, list[str]],
) -> dict[str, list[str]]:
    instance_key = str((selection or {}).get("instance_key") or "").strip()
    if not instance_key:
        return {}
    prefix = f"feat:{instance_key}:"
    serialized: dict[str, list[str]] = {}
    for raw_group_key, raw_values in dict(selected_choices or {}).items():
        group_key = str(raw_group_key or "").strip()
        if not group_key.startswith(prefix):
            continue
        category = group_key[len(prefix) :].strip()
        values = [
            str(raw_value).strip()
            for raw_value in list(raw_values or [])
            if str(raw_value or "").strip()
        ]
        if category and values:
            serialized[category] = values
    return serialized


def _build_editor_optionalfeature_fields_for_row(
    *,
    row: dict[str, Any],
    campaign_page_lookup: dict[str, dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    values: dict[str, str],
    selected_choices: dict[tuple[int, int], str] | None = None,
) -> list[dict[str, Any]]:
    page_ref = str(row.get("page_ref") or "").strip()
    if not page_ref or not optionalfeature_catalog:
        return []
    feat_entry = _editable_campaign_feat_entry_for_page_ref(page_ref, campaign_page_lookup)
    if not isinstance(feat_entry, SystemsEntryRecord):
        return []
    row_index = max(int(row.get("index") or 0), 0)
    if row_index <= 0:
        return []
    feature_title = str(row.get("name") or feat_entry.title or "Linked Feature").strip() or "Linked Feature"
    existing_selections = dict(selected_choices or {})
    fields: list[dict[str, Any]] = []
    for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
        section_index = int(section.get("index") or 0)
        options = [dict(option) for option in list(section.get("options") or []) if str(option.get("value") or "").strip()]
        choice_count = max(int(section.get("count") or 0), 0)
        if section_index <= 0 or choice_count <= 0 or not options:
            continue
        section_title = str(section.get("title") or "Optional Feature").strip() or "Optional Feature"
        for choice_index in range(1, choice_count + 1):
            field_name = _editor_optionalfeature_field_name(row_index, section_index, choice_index)
            selected_value = str(values.get(field_name) or existing_selections.get((section_index, choice_index)) or "").strip()
            label_suffix = f" {choice_index}" if choice_count > 1 else ""
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feature_title} {section_title}{label_suffix}",
                    "help_text": f"Choose the {section_title.lower()} granted by {feature_title}.",
                    "options": options,
                    "selected": selected_value,
                    "group_key": field_name,
                    "kind": "feat_optionalfeature",
                }
            )
    return fields


def _build_editor_selected_optionalfeature_features(
    *,
    row_index: int,
    parent_feature_id: str,
    campaign_page_lookup: dict[str, dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    values: dict[str, str],
    page_ref: str,
) -> list[dict[str, Any]]:
    feat_entry = _editable_campaign_feat_entry_for_page_ref(page_ref, campaign_page_lookup)
    if not isinstance(feat_entry, SystemsEntryRecord):
        return []
    features: list[dict[str, Any]] = []
    for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
        section_index = int(section.get("index") or 0)
        choice_count = max(int(section.get("count") or 0), 0)
        if section_index <= 0 or choice_count <= 0:
            continue
        section_title = str(section.get("title") or "optional feature").strip() or "optional feature"
        for choice_index in range(1, choice_count + 1):
            field_name = _editor_optionalfeature_field_name(row_index, section_index, choice_index)
            selected_slug = str(values.get(field_name) or "").strip()
            if not selected_slug:
                raise CharacterEditValidationError(
                    f"Choose an option for {feat_entry.title} {section_title}."
                )
            selected_entry = optionalfeature_catalog.get(selected_slug)
            if not isinstance(selected_entry, SystemsEntryRecord):
                raise CharacterEditValidationError(f"Choose a valid option for {feat_entry.title}.")
            feature_payload = _build_feature_payload(
                {
                    "kind": "optionalfeature",
                    "entry": selected_entry,
                    "name": selected_entry.title,
                    "label": selected_entry.title,
                    "slug": str(selected_entry.slug or "").strip(),
                },
                index=len(features) + 1,
            )
            if feature_payload is None:
                continue
            feature_payload[NATIVE_EDIT_PARENT_FEATURE_ID_KEY] = parent_feature_id
            feature_payload[NATIVE_EDIT_OPTIONALFEATURE_SECTION_KEY] = section_index
            feature_payload[NATIVE_EDIT_OPTIONALFEATURE_CHOICE_KEY] = choice_index
            features.append(feature_payload)
    return features


def _build_editor_additional_spell_choice_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    additional_spells = list(option.get("additional_spells") or [])
    if not additional_spells:
        return []
    field_prefix = _editor_additional_spell_field_prefix(int(row.get("index") or 0))
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    fields = _build_editor_additional_spell_choice_fields(
        additional_spells=additional_spells,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix=field_prefix,
        current_level=current_level,
    )
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        field["selected"] = _infer_editor_additional_spell_choice_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _build_editor_additional_spell_choice_fields(
    *,
    additional_spells: list[Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    field_prefix: str,
    current_level: int,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    known_specs = _extract_additional_known_choice_specs(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=[{"campaign_option": {"additional_spells": additional_spells}}],
    )
    prepared_specs: list[dict[str, Any]] = []
    granted_specs: list[dict[str, Any]] = []
    for block in additional_spells:
        if not isinstance(block, dict):
            continue
        prepared_specs.extend(_extract_feat_prepared_choice_specs(block, target_level=current_level))
        granted_specs.extend(_extract_feat_innate_choice_specs(block, target_level=current_level))
    fields.extend(
        _build_editor_additional_spell_fields_from_specs(
            specs=known_specs,
            spell_catalog=spell_catalog,
            values=values,
            field_prefix=field_prefix,
            category="known",
            default_help_text="Choose a feature-granted bonus spell.",
        )
    )
    fields.extend(
        _build_editor_additional_spell_fields_from_specs(
            specs=prepared_specs,
            spell_catalog=spell_catalog,
            values=values,
            field_prefix=field_prefix,
            category="prepared",
            default_help_text="Choose a feature-granted spell.",
        )
    )
    fields.extend(
        _build_editor_additional_spell_fields_from_specs(
            specs=granted_specs,
            spell_catalog=spell_catalog,
            values=values,
            field_prefix=field_prefix,
            category="granted",
            default_help_text="Choose a feature-granted spell.",
        )
    )
    return fields


def _build_editor_additional_spell_fields_from_specs(
    *,
    specs: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    field_prefix: str,
    category: str,
    default_help_text: str,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for spec_index, spec in enumerate(specs, start=1):
        options = _build_additional_spell_filter_options(str(spec.get("filter") or ""), spell_catalog)
        if not options:
            continue
        count = max(int(spec.get("count") or 1), 1)
        is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
        label_prefix = str(spec.get("label_prefix") or "").strip() or (
            "Granted Cantrip" if is_cantrip else "Granted Spell"
        )
        help_text = str(spec.get("help_text") or "").strip() or (
            "Choose a feature-granted cantrip." if is_cantrip else default_help_text
        )
        group_key = f"{field_prefix}_{category}_{spec_index}"
        for choice_index in range(1, count + 1):
            field_name = f"{field_prefix}_{category}_{spec_index}_{choice_index}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"{label_prefix} {choice_index}",
                    "help_text": help_text,
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": group_key,
                    "kind": f"additional_spell_{category}",
                    "spell_mark": str(spec.get("spell_mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("spell_is_always_prepared")),
                    "spell_is_ritual": bool(spec.get("spell_is_ritual")),
                }
            )
    return fields


def _build_editor_spell_support_choice_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    if not option.get("spell_support"):
        return []
    field_prefix = _editor_spell_support_field_prefix(int(row.get("index") or 0))
    fields = _build_spell_support_choice_fields(
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        group_key_prefix=field_prefix,
        feature_entries=[{"campaign_option": option}],
    )
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        field["selected"] = _infer_editor_spell_support_choice_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _build_editor_spell_support_replacement_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    provisional_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    if not option.get("spell_support"):
        return []
    field_prefix = _editor_spell_support_field_prefix(int(row.get("index") or 0))
    fields = _build_spell_support_replacement_fields(
        existing_spells=provisional_spell_payloads,
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        feature_entries=[{"campaign_option": option}],
    )
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        field["selected"] = _infer_editor_spell_support_replacement_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _build_editor_spell_manager_choice_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    if not option.get("spell_manager"):
        return []
    feature_entry = {
        "campaign_option": option,
        "page_ref": str(row.get("page_ref") or option.get("page_ref") or "").strip(),
        "name": str(row.get("name") or option.get("feature_name") or option.get("title") or "Feature").strip() or "Feature",
        "label": str(row.get("name") or option.get("feature_name") or option.get("title") or "Feature").strip() or "Feature",
    }
    field_prefix_base = _editor_spell_manager_field_prefix(int(row.get("index") or 0))
    manager_values = dict(values)
    fields = _build_campaign_feature_spell_manager_fields(
        feature_entries=[feature_entry],
        spell_catalog=spell_catalog,
        values=manager_values,
        field_prefix_base=field_prefix_base,
    )
    inferred_source = False
    for field in fields:
        if str(field.get("kind") or "").strip() != "campaign_spell_source":
            continue
        field_name = str(field.get("name") or "").strip()
        if field_name and not str(manager_values.get(field_name) or "").strip():
            selected_value = _infer_editor_spell_manager_source_value(row=row, field=field)
            if selected_value:
                manager_values[field_name] = selected_value
                inferred_source = True
    if inferred_source:
        fields = _build_campaign_feature_spell_manager_fields(
            feature_entries=[feature_entry],
            spell_catalog=spell_catalog,
            values=manager_values,
            field_prefix_base=field_prefix_base,
        )
    field_prefix = _editor_spell_manager_built_field_prefix(fields)
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        if field_name and str(manager_values.get(field_name) or "").strip():
            field["selected"] = str(manager_values.get(field_name) or "").strip()
            continue
        if str(field.get("kind") or "").strip() == "campaign_spell_source":
            field["selected"] = _infer_editor_spell_manager_source_value(
                row=row,
                field=field,
            )
            continue
        field["selected"] = _infer_editor_spell_manager_choice_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _editor_spell_manager_feature_entry(entry: dict[str, Any]) -> dict[str, Any]:
    option = dict(entry.get("campaign_option") or {})
    feature_name = str(entry.get("feature_name") or option.get("feature_name") or option.get("title") or "Feature").strip() or "Feature"
    return {
        "campaign_option": option,
        "page_ref": str(entry.get("page_ref") or option.get("page_ref") or "").strip(),
        "name": feature_name,
        "label": feature_name,
    }


def _infer_editor_spell_manager_source_value(
    *,
    row: dict[str, Any],
    field: dict[str, Any],
) -> str:
    spell_manager = dict(row.get("spell_manager") or {})
    if not spell_manager:
        return ""
    spell_list_class_name = normalize_lookup(str(spell_manager.get("spell_list_class_name") or "").strip())
    title = normalize_lookup(str(spell_manager.get("title") or "").strip())
    for option in list(field.get("options") or []):
        option_value = str(option.get("value") or "").strip()
        option_label = normalize_lookup(str(option.get("label") or "").strip())
        if spell_list_class_name and spell_list_class_name in {normalize_lookup(option_value), option_label}:
            return option_value
        if title and title == option_label:
            return option_value
    return ""


def _editor_spell_manager_built_field_prefix(fields: list[dict[str, Any]]) -> str:
    for field in list(fields or []):
        field_name = str(field.get("name") or "").strip()
        if field_name.endswith("_source_1"):
            return field_name[: -len("_source_1")]
        parts = field_name.rsplit("_", 3)
        if len(parts) == 4:
            return parts[0]
    return ""


def _build_provisional_editor_spell_payloads(
    *,
    current_spellcasting: dict[str, Any] | None,
    feature_rows: list[dict[str, Any]],
    equipment_rows: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in _campaign_option_tracked_spell_payloads(current_spellcasting):
        payload = _normalize_spell_payload_for_campaign_option_tracking(spell)
        _reset_spell_payload_to_base(payload)
        payload_key = _campaign_option_spell_map_key(payload, spell_catalog)
        if payload_key:
            spells_by_key[payload_key] = payload

    selected_option_payloads = _campaign_option_payloads_from_entries(feature_rows, equipment_rows)
    _apply_editor_legacy_campaign_option_grants(
        spells_by_key,
        selected_campaign_option_payloads=selected_option_payloads,
        spell_catalog=spell_catalog,
    )
    for entry in _editor_additional_spell_entries_from_feature_rows(feature_rows):
        _apply_editor_additional_spell_grants_and_choices(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )
    for entry in _editor_spell_support_entries_from_feature_rows(feature_rows):
        _apply_editor_spell_support_grants_and_choices(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )
    for entry in _editor_spell_manager_entries_from_feature_rows(feature_rows):
        _apply_editor_spell_manager_grants_and_choices(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )
    return list(spells_by_key.values())


def _editor_additional_spell_entries_from_feature_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in list(feature_rows or []):
        option = dict(row.get("campaign_option") or {})
        if not option.get("additional_spells"):
            continue
        entries.append(
            {
                "field_prefix": _editor_additional_spell_field_prefix(int(row.get("index") or 0)),
                "campaign_option": option,
                "source_ref": str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip(),
            }
        )
    return entries


def _editor_additional_spell_field_prefix(row_index: int) -> str:
    return f"custom_feature_additional_spells_{row_index}"


def _editor_spell_support_entries_from_feature_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in list(feature_rows or []):
        option = dict(row.get("campaign_option") or {})
        if not option.get("spell_support"):
            continue
        entries.append(
            {
                "field_prefix": _editor_spell_support_field_prefix(int(row.get("index") or 0)),
                "campaign_option": option,
                "source_ref": str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip(),
            }
        )
    return entries


def _editor_spell_support_field_prefix(row_index: int) -> str:
    return f"custom_feature_spell_support_{row_index}"


def _editor_spell_manager_entries_from_feature_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in list(feature_rows or []):
        option = dict(row.get("campaign_option") or {})
        if not option.get("spell_manager"):
            continue
        entries.append(
            {
                "field_prefix": _editor_spell_manager_field_prefix(int(row.get("index") or 0)),
                "campaign_option": option,
                "page_ref": str(row.get("page_ref") or option.get("page_ref") or "").strip(),
                "feature_name": str(row.get("name") or option.get("feature_name") or option.get("title") or "Feature").strip() or "Feature",
                "source_ref": str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip(),
            }
        )
    return entries


def _editor_spell_manager_field_prefix(row_index: int) -> str:
    return f"custom_feature_spell_manager_{row_index}"


def _parse_editor_additional_spell_choice_field_identity(
    field_name: str,
    field_prefix: str,
) -> tuple[str, int, int] | None:
    prefix = f"{field_prefix}_"
    if not field_name.startswith(prefix):
        return None
    parts = field_name[len(prefix):].split("_")
    if len(parts) != 3:
        return None
    category, spec_index, choice_index = parts
    if not spec_index.isdigit() or not choice_index.isdigit():
        return None
    return category, int(spec_index), int(choice_index)


def _parse_editor_spell_support_choice_field_identity(
    field_name: str,
    field_prefix: str,
) -> tuple[str, int, int] | None:
    prefix = f"{field_prefix}_"
    if not field_name.startswith(prefix):
        return None
    parts = field_name[len(prefix):].split("_")
    if len(parts) != 3:
        return None
    category, spec_index, choice_index = parts
    if not spec_index.isdigit() or not choice_index.isdigit():
        return None
    return category, int(spec_index), int(choice_index)


def _parse_editor_spell_support_replacement_field_identity(
    field_name: str,
    field_prefix: str,
) -> tuple[str, int, str, int] | None:
    prefix = f"{field_prefix}_replace_"
    if not field_name.startswith(prefix):
        return None
    parts = field_name[len(prefix):].split("_")
    if len(parts) != 4:
        return None
    category, spec_index, part, choice_index = parts
    if not spec_index.isdigit() or not choice_index.isdigit():
        return None
    return category, int(spec_index), part, int(choice_index)


def _infer_editor_additional_spell_choice_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_additional_spell_choice_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, choice_index = identity
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key="campaign_option_sources",
            source_ref=source_ref,
            mode="additional_spell_choice",
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _infer_editor_spell_support_choice_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_spell_support_choice_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, choice_index = identity
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key="campaign_option_sources",
            source_ref=source_ref,
            mode="spell_support_choice",
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _infer_editor_spell_manager_choice_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_additional_spell_choice_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, choice_index = identity
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key="campaign_option_sources",
            source_ref=source_ref,
            mode="spell_manager_choice",
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _infer_editor_spell_support_replacement_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_spell_support_replacement_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, part, choice_index = identity
    annotation_key = "campaign_option_replaced_by" if part == "from" else "campaign_option_sources"
    mode = "spell_support_replacement"
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key=annotation_key,
            source_ref=source_ref,
            mode=mode,
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _payload_has_campaign_option_annotation(
    payload: dict[str, Any],
    *,
    annotation_key: str,
    source_ref: str,
    mode: str,
    category: str,
    spec_index: int,
    choice_index: int,
) -> bool:
    for annotation in list(payload.get(annotation_key) or []):
        if not isinstance(annotation, dict):
            continue
        if str(annotation.get("source_ref") or "").strip() != source_ref:
            continue
        if str(annotation.get("mode") or "").strip() != mode:
            continue
        if str(annotation.get("category") or "").strip() != category:
            continue
        if int(annotation.get("spec_index") or 0) != spec_index:
            continue
        if int(annotation.get("choice_index") or 0) != choice_index:
            continue
        return True
    return False


def _campaign_option_tracked_spell_payloads(current_spellcasting: dict[str, Any] | None) -> list[dict[str, Any]]:
    spellcasting = dict(current_spellcasting or {})
    return [
        dict(payload)
        for payload in list(spellcasting.get("spells") or []) + list(spellcasting.get("campaign_option_replacement_bases") or [])
        if isinstance(payload, dict)
    ]


def _campaign_option_spell_map_key(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> str:
    payload_key = _spell_payload_key(spell_payload)
    if not payload_key:
        return ""
    return _spell_lookup_key(payload_key, spell_catalog)


def _character_total_level(definition: CharacterDefinition) -> int:
    return profile_total_level(definition.profile, default=1)


def _apply_campaign_option_spells_to_spellcasting(
    current_spellcasting: dict[str, Any] | None,
    *,
    existing_campaign_option_payloads: list[dict[str, Any]],
    selected_campaign_option_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
    selected_additional_spell_entries: list[dict[str, Any]] | None = None,
    selected_spell_support_entries: list[dict[str, Any]] | None = None,
    selected_spell_manager_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spellcasting = dict(current_spellcasting or {})
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in _campaign_option_tracked_spell_payloads(spellcasting):
        payload = _normalize_spell_payload_for_campaign_option_tracking(spell)
        _reset_spell_payload_to_base(payload)
        payload_key = _campaign_option_spell_map_key(payload, spell_catalog)
        if payload_key:
            spells_by_key[payload_key] = payload

    _apply_editor_legacy_campaign_option_grants(
        spells_by_key,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        spell_catalog=spell_catalog,
    )

    choice_fields: list[dict[str, Any]] = []
    replacement_fields: list[dict[str, Any]] = []
    for entry in list(selected_additional_spell_entries or []):
        choice_fields.extend(
            _apply_editor_additional_spell_grants_and_choices(
                spells_by_key,
                entry=entry,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    for entry in list(selected_spell_support_entries or []):
        choice_fields.extend(
            _apply_editor_spell_support_grants_and_choices(
                spells_by_key,
                entry=entry,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    for entry in list(selected_spell_manager_entries or []):
        choice_fields.extend(
            _apply_editor_spell_manager_grants_and_choices(
                spells_by_key,
                entry=entry,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    provisional_spell_payloads = list(spells_by_key.values())
    for entry in list(selected_spell_support_entries or []):
        replacement_fields.extend(
            _build_editor_spell_support_replacement_fields_for_entry(
                entry=entry,
                existing_spells=provisional_spell_payloads,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    if choice_fields or replacement_fields:
        _resolve_builder_choices(
            [{"title": "Spell Choices", "fields": choice_fields + replacement_fields}],
            values,
            strict=True,
        )
    for entry in list(selected_spell_support_entries or []):
        _apply_editor_spell_support_replacements(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )

    visible_spells: list[dict[str, Any]] = []
    hidden_spells: list[dict[str, Any]] = []
    for payload in spells_by_key.values():
        if list(payload.get("campaign_option_replaced_by") or []):
            hidden_spells.append(payload)
            continue
        if bool(payload.get("has_base_spell")) or list(payload.get("campaign_option_sources") or []):
            visible_spells.append(payload)
    spellcasting["spells"] = visible_spells
    if hidden_spells:
        spellcasting["campaign_option_replacement_bases"] = hidden_spells
    else:
        spellcasting.pop("campaign_option_replacement_bases", None)
    return spellcasting


def _apply_editor_legacy_campaign_option_grants(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_campaign_option_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> None:
    for spell_grant in _iter_campaign_option_spell_grants(selected_campaign_option_payloads):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(spell_grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": str(spell_grant.get("source_ref") or "").strip(),
                "mode": "legacy_grant",
                "mark": str(spell_grant.get("mark") or "").strip(),
                "always_prepared": bool(spell_grant.get("always_prepared")),
                "ritual": bool(spell_grant.get("ritual")),
            },
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
        )


def _apply_editor_additional_spell_grants_and_choices(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    feature_entries = [{"campaign_option": dict(entry.get("campaign_option") or {})}]
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix = str(entry.get("field_prefix") or "").strip()
    for selected_value in _automatic_known_spell_values(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=feature_entries,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "additional_spell_grant",
                "category": "known",
            },
            bonus_known=True,
        )
    for selected_value in _automatic_prepared_spell_values(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=feature_entries,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "additional_spell_grant",
                "category": "prepared",
                "always_prepared": True,
            },
            is_always_prepared=True,
        )
    for spell_grant in _automatic_innate_spell_values(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=feature_entries,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "additional_spell_grant",
                "category": "granted",
                "mark": str(spell_grant.get("mark") or "").strip(),
                "ritual": bool(spell_grant.get("is_ritual")),
            },
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )

    choice_fields = _build_editor_additional_spell_choice_fields_for_entry(
        entry=entry,
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
    )
    for field in choice_fields:
        selected_value = str(values.get(str(field.get("name") or "")) or "").strip()
        if not selected_value:
            continue
        identity = _parse_editor_additional_spell_choice_field_identity(
            str(field.get("name") or ""),
            field_prefix,
        )
        category, spec_index, choice_index = identity or ("", 0, 0)
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "additional_spell_choice",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(field.get("spell_mark") or "").strip(),
                "always_prepared": bool(field.get("spell_is_always_prepared")),
                "ritual": bool(field.get("spell_is_ritual")),
            },
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
            bonus_known=str(category or "").strip() == "known",
        )
    return choice_fields


def _build_editor_additional_spell_choice_fields_for_entry(
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(entry.get("campaign_option") or {})
    return _build_editor_additional_spell_choice_fields(
        additional_spells=list(option.get("additional_spells") or []),
        spell_catalog=spell_catalog,
        values=values,
        field_prefix=str(entry.get("field_prefix") or "").strip(),
        current_level=current_level,
    )


def _apply_editor_spell_support_grants_and_choices(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    feature_entries = [{"campaign_option": dict(entry.get("campaign_option") or {})}]
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix = str(entry.get("field_prefix") or "").strip()
    for grant in _automatic_spell_support_grants(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=feature_entries,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_grant",
                "mark": str(grant.get("mark") or "").strip(),
                "always_prepared": bool(grant.get("always_prepared")),
                "ritual": bool(grant.get("ritual")),
            },
            mark=str(grant.get("mark") or "").strip(),
            is_always_prepared=bool(grant.get("always_prepared")),
            is_ritual=bool(grant.get("ritual")),
            bonus_known=bool(grant.get("bonus_known")),
            support_kwargs=_spell_payload_support_kwargs(grant),
        )

    choice_fields = _build_spell_support_choice_fields(
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        group_key_prefix=field_prefix,
        feature_entries=feature_entries,
    )
    for field in choice_fields:
        selected_value = str(values.get(str(field.get("name") or "")) or "").strip()
        if not selected_value:
            continue
        identity = _parse_editor_spell_support_choice_field_identity(str(field.get("name") or ""), field_prefix)
        category, spec_index, choice_index = identity or ("", 0, 0)
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_choice",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(field.get("spell_mark") or "").strip(),
                "always_prepared": bool(field.get("spell_is_always_prepared")),
                "ritual": bool(field.get("spell_is_ritual")),
            },
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
            bonus_known=str(category or "").strip() == "known",
            support_kwargs=_spell_payload_support_kwargs(field),
        )
    return choice_fields


def _apply_editor_spell_manager_grants_and_choices(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    feature_entries = [_editor_spell_manager_feature_entry(entry)]
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix_base = str(entry.get("field_prefix") or "").strip()
    for grant in _automatic_campaign_feature_spell_manager_grants(
        feature_entries=feature_entries,
        values=values,
        field_prefix_base=field_prefix_base,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_manager_grant",
            },
            bonus_known=True,
            support_kwargs=_spell_payload_support_kwargs(grant),
        )

    choice_fields = _build_campaign_feature_spell_manager_fields(
        feature_entries=feature_entries,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix_base=field_prefix_base,
    )
    field_prefix = _editor_spell_manager_built_field_prefix(choice_fields)
    for field in choice_fields:
        if str(field.get("kind") or "").strip() == "campaign_spell_source":
            continue
        selected_value = str(values.get(str(field.get("name") or "")) or "").strip()
        if not selected_value:
            continue
        identity = _parse_editor_additional_spell_choice_field_identity(str(field.get("name") or ""), field_prefix)
        category, spec_index, choice_index = identity or ("", 0, 0)
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_manager_choice",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(field.get("spell_mark") or "").strip(),
                "always_prepared": bool(field.get("spell_is_always_prepared")),
                "ritual": bool(field.get("spell_is_ritual")),
            },
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
            bonus_known=str(category or "").strip() == "known",
            support_kwargs=_spell_payload_support_kwargs(field),
        )
    return choice_fields


def _build_editor_spell_support_replacement_fields_for_entry(
    *,
    entry: dict[str, Any],
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    return _build_spell_support_replacement_fields(
        existing_spells=existing_spells,
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=str(entry.get("field_prefix") or "").strip(),
        feature_entries=[{"campaign_option": dict(entry.get("campaign_option") or {})}],
    )


def _apply_editor_spell_support_replacements(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> None:
    replacement_fields = _build_editor_spell_support_replacement_fields_for_entry(
        entry=entry,
        existing_spells=list(spells_by_key.values()),
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
    )
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix = str(entry.get("field_prefix") or "").strip()
    replacement_specs: dict[tuple[str, int, int], dict[str, Any]] = {}
    for field in replacement_fields:
        identity = _parse_editor_spell_support_replacement_field_identity(str(field.get("name") or ""), field_prefix)
        if identity is None:
            continue
        category, spec_index, _, choice_index = identity
        replacement_specs[(category, spec_index, choice_index)] = {
            "mark": str(field.get("spell_mark") or "").strip(),
            "always_prepared": bool(field.get("spell_is_always_prepared")),
            "ritual": bool(field.get("spell_is_ritual")),
        }
    for field in replacement_fields:
        field_name = str(field.get("name") or "").strip()
        identity = _parse_editor_spell_support_replacement_field_identity(field_name, field_prefix)
        if identity is None:
            continue
        category, spec_index, part, choice_index = identity
        if part != "from":
            continue
        replacement_from = str(values.get(field_name) or "").strip()
        to_field_name = str(field.get("paired_field_name") or "").strip()
        replacement_to = str(values.get(to_field_name) or "").strip()
        if not replacement_from or not replacement_to:
            continue
        payload_key = _spell_lookup_key(replacement_from, spell_catalog)
        payload = spells_by_key.get(payload_key)
        if payload is not None:
            _add_campaign_option_source_annotation(
                payload,
                annotation_key="campaign_option_replaced_by",
                annotation={
                    "source_ref": source_ref,
                    "mode": "spell_support_replacement",
                    "category": category,
                    "spec_index": spec_index,
                    "choice_index": choice_index,
                },
            )
        replacement_metadata = dict(replacement_specs.get((category, spec_index, choice_index)) or {})
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=replacement_to,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_replacement",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(replacement_metadata.get("mark") or "").strip(),
                "always_prepared": bool(replacement_metadata.get("always_prepared")),
                "ritual": bool(replacement_metadata.get("ritual")),
            },
            mark=str(replacement_metadata.get("mark") or "").strip(),
            is_always_prepared=bool(replacement_metadata.get("always_prepared")),
            is_ritual=bool(replacement_metadata.get("ritual")),
            bonus_known=category == "known",
        )


def _add_editor_campaign_option_spell(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    annotation: dict[str, Any],
    mark: str = "",
    is_always_prepared: bool = False,
    is_ritual: bool = False,
    bonus_known: bool = False,
    support_kwargs: dict[str, Any] | None = None,
) -> None:
    clean_value = str(selected_value or "").strip()
    if not clean_value:
        return
    spell_entry = _resolve_spell_entry(clean_value, spell_catalog)
    normalized_support_kwargs = dict(support_kwargs or {})
    payload_key = _spell_payload_map_key(
        {
            "systems_ref": (
                {"slug": str(spell_entry.slug or "").strip()}
                if spell_entry is not None
                else {}
            ),
            "name": clean_value,
            **normalized_support_kwargs,
        }
    )
    if not payload_key:
        return
    existed_before = payload_key in spells_by_key
    if bonus_known:
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=clean_value,
            spell_catalog=spell_catalog,
            **normalized_support_kwargs,
        )
    else:
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=clean_value,
            spell_catalog=spell_catalog,
            mark=mark,
            is_always_prepared=is_always_prepared,
            is_ritual=is_ritual,
            **normalized_support_kwargs,
        )
    payload = spells_by_key.get(payload_key)
    if payload is None:
        return
    if not existed_before:
        payload["base_mark"] = ""
        payload["base_is_always_prepared"] = False
        payload["base_is_bonus_known"] = False
        payload["base_is_ritual"] = bool(dict((spell_entry.metadata if spell_entry is not None else {}) or {}).get("ritual"))
        payload["has_base_spell"] = False
    _add_campaign_option_source_annotation(
        payload,
        annotation_key="campaign_option_sources",
        annotation=annotation,
    )


def _normalize_spell_payload_for_campaign_option_tracking(spell_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spell_payload or {})
    payload["base_mark"] = str(
        payload.get("base_mark")
        if "base_mark" in payload
        else payload.get("mark", "")
    ).strip()
    payload["base_is_always_prepared"] = bool(
        payload.get("base_is_always_prepared")
        if "base_is_always_prepared" in payload
        else payload.get("is_always_prepared")
    )
    payload["base_is_bonus_known"] = bool(
        payload.get("base_is_bonus_known")
        if "base_is_bonus_known" in payload
        else payload.get("is_bonus_known")
    )
    payload["base_is_ritual"] = bool(
        payload.get("base_is_ritual")
        if "base_is_ritual" in payload
        else payload.get("is_ritual")
    )
    payload["has_base_spell"] = bool(
        payload.get("has_base_spell")
        if "has_base_spell" in payload
        else True
    )
    payload["campaign_option_sources"] = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get("campaign_option_sources"))
    ]
    payload["campaign_option_replaced_by"] = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get("campaign_option_replaced_by"))
    ]
    return payload


def _reset_spell_payload_to_base(payload: dict[str, Any]) -> None:
    payload["mark"] = str(payload.get("base_mark") or "").strip()
    payload["is_always_prepared"] = bool(payload.get("base_is_always_prepared"))
    payload["is_bonus_known"] = bool(payload.get("base_is_bonus_known"))
    payload["is_ritual"] = bool(payload.get("base_is_ritual"))
    payload["campaign_option_sources"] = []
    payload["campaign_option_replaced_by"] = []


def _normalize_campaign_option_source_annotations(value: Any) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for raw_annotation in list(value or []):
        if not isinstance(raw_annotation, dict):
            continue
        annotations.append(
            {
                "source_ref": str(raw_annotation.get("source_ref") or "").strip(),
                "mode": str(raw_annotation.get("mode") or "").strip(),
                "category": str(raw_annotation.get("category") or "").strip(),
                "spec_index": int(raw_annotation.get("spec_index") or 0),
                "choice_index": int(raw_annotation.get("choice_index") or 0),
                "mark": str(raw_annotation.get("mark") or "").strip(),
                "always_prepared": bool(raw_annotation.get("always_prepared")),
                "ritual": bool(raw_annotation.get("ritual")),
            }
        )
    return [annotation for annotation in annotations if annotation.get("source_ref")]


def _campaign_option_source_marker(annotation: dict[str, Any]) -> tuple[str, str, str, int, int, str, bool, bool]:
    return (
        str(annotation.get("source_ref") or "").strip(),
        str(annotation.get("mode") or "").strip(),
        str(annotation.get("category") or "").strip(),
        int(annotation.get("spec_index") or 0),
        int(annotation.get("choice_index") or 0),
        str(annotation.get("mark") or "").strip(),
        bool(annotation.get("always_prepared")),
        bool(annotation.get("ritual")),
    )


def _add_campaign_option_source_annotation(
    payload: dict[str, Any],
    *,
    annotation_key: str,
    annotation: dict[str, Any],
) -> None:
    normalized_entries = _normalize_campaign_option_source_annotations([annotation]) if annotation else []
    normalized_annotation = dict(normalized_entries[0]) if normalized_entries else {}
    if not normalized_annotation:
        return
    existing_annotations = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get(annotation_key))
    ]
    marker = _campaign_option_source_marker(normalized_annotation)
    seen = {_campaign_option_source_marker(source) for source in existing_annotations}
    if marker not in seen:
        existing_annotations.append(normalized_annotation)
    payload[annotation_key] = existing_annotations


def _iter_campaign_option_spell_grants(option_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for option in list(option_payloads or []):
        source_ref = str(option.get("page_ref") or option.get("title") or option.get("display_name") or "").strip()
        if not source_ref:
            continue
        for grant in list(option.get("spells") or []):
            payload = dict(grant or {})
            value = str(payload.get("value") or "").strip()
            if not value:
                continue
            grants.append(
                {
                    "source_ref": source_ref,
                    "value": value,
                    "mark": str(payload.get("mark") or "").strip(),
                    "always_prepared": bool(payload.get("always_prepared")),
                    "ritual": bool(payload.get("ritual")),
                    **_spell_payload_support_kwargs(payload),
                }
            )
    return grants


def _dedupe_casefold_values(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        clean_value = str(value or "").strip()
        normalized_value = normalize_lookup(clean_value)
        if not clean_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        deduped.append(clean_value)
    return deduped


def _subtract_casefold_values(values: list[str], removals: list[str]) -> list[str]:
    removal_keys = {
        normalize_lookup(value)
        for value in list(removals or [])
        if str(value or "").strip()
    }
    return [
        str(value).strip()
        for value in list(values or [])
        if str(value or "").strip() and normalize_lookup(value) not in removal_keys
    ]


def _manual_feature_tracker_id(feature_id: str) -> str:
    return f"{CUSTOM_FEATURE_TRACKER_PREFIX}:{feature_id}"


def _build_manual_feature_resource_template(
    *,
    tracker_id: str,
    feature_name: str,
    max_value: int,
    reset_on: str,
    existing_template: dict[str, Any] | None,
    display_order: int,
) -> dict[str, Any]:
    current_template = dict(existing_template or {})
    clean_reset_on = _normalize_resource_reset_on(reset_on)
    return {
        "id": tracker_id,
        "label": feature_name,
        "category": "custom_feature",
        "initial_current": min(
            int(current_template.get("initial_current") or max_value),
            int(max_value),
        ),
        "max": int(max_value),
        "reset_on": clean_reset_on,
        "reset_to": "max" if clean_reset_on in {"short_rest", "long_rest"} else "unchanged",
        "rest_behavior": "confirm_before_reset" if clean_reset_on in {"short_rest", "long_rest"} else "manual_only",
        "notes": str(current_template.get("notes") or "").strip(),
        "display_order": int(display_order),
    }


def _build_campaign_page_options(
    campaign_page_records: list[Any],
    *,
    allowed_sections: set[str] | None = None,
    include_page_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_allowed_sections = {
        str(value or "").strip()
        for value in set(allowed_sections or set())
        if str(value or "").strip()
    }
    normalized_include_page_refs = {
        (str(value.get("page_ref") or value.get("slug") or "").strip() if isinstance(value, dict) else str(value or "").strip())
        for value in set(include_page_refs or set())
        if (str(value.get("page_ref") or value.get("slug") or "").strip() if isinstance(value, dict) else str(value or "").strip())
    }
    options: list[dict[str, Any]] = []
    for record in list(campaign_page_records or []):
        page_ref = _extract_page_ref_value(getattr(record, "page_ref", ""))
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        section = str(getattr(page, "section", "") or "").strip()
        subsection = str(getattr(page, "subsection", "") or "").strip()
        if normalized_allowed_sections and section not in normalized_allowed_sections and page_ref not in normalized_include_page_refs:
            continue
        campaign_option = build_campaign_page_character_option(
            record,
            default_kind="item" if section == "Items" else "feature",
        )
        option_title = str((campaign_option or {}).get("display_name") or title).strip() or title
        label_parts = [option_title]
        if section:
            if subsection:
                label_parts.append(f"{section} / {subsection}")
            else:
                label_parts.append(section)
        options.append(
            {
                "value": page_ref,
                "label": " | ".join(label_parts),
                "title": option_title,
                "campaign_option": dict(campaign_option or {}) or None,
                "record": record,
            }
        )
    return options


def _build_campaign_page_lookup(
    campaign_page_records: list[Any],
    *,
    allowed_sections: set[str] | None = None,
    include_page_refs: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for option in _build_campaign_page_options(
        campaign_page_records,
        allowed_sections=allowed_sections,
        include_page_refs=include_page_refs,
    ):
        page_ref = str(option.get("value") or "").strip()
        if not page_ref:
            continue
        lookup[page_ref] = {
            "page_ref": page_ref,
            "label": str(option.get("label") or page_ref),
            "title": str(option.get("title") or page_ref),
            "campaign_option": dict(option.get("campaign_option") or {}) or None,
            "record": option.get("record"),
        }
    return lookup


def _extract_page_ref_value(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("page_ref") or payload.get("slug") or "").strip()
    return str(payload or "").strip()


def _normalize_selected_campaign_page_ref(
    raw_value: Any,
    campaign_page_lookup: dict[str, dict[str, Any]],
) -> str:
    page_ref = _extract_page_ref_value(raw_value)
    if not page_ref:
        return ""
    if page_ref not in campaign_page_lookup:
        raise CharacterEditValidationError("Choose a valid linked campaign page.")
    return page_ref


def _join_multiline_values(values: list[str]) -> str:
    return "\n".join(str(value).strip() for value in list(values or []) if str(value).strip())


def _parse_multiline_values(raw_value: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in str(raw_value or "").replace("\r", "").split("\n"):
        for fragment in str(line).split(","):
            value = str(fragment).strip()
            normalized_value = value.casefold()
            if not value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            values.append(value)
    return values


def _parse_manual_item_quantity(raw_value: str) -> int:
    if not str(raw_value or "").strip():
        return 1
    try:
        quantity = int(str(raw_value).strip())
    except ValueError as exc:
        raise CharacterEditValidationError("Custom equipment quantities must be whole numbers.") from exc
    if quantity < 0:
        raise CharacterEditValidationError("Custom equipment quantities cannot be negative.")
    return quantity


def _parse_optional_nonnegative_integer(raw_value: str, *, field_label: str) -> int | None:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return None
    try:
        value = int(clean_value)
    except ValueError as exc:
        raise CharacterEditValidationError(f"The {field_label} must be a whole number.") from exc
    if value < 0:
        raise CharacterEditValidationError(f"The {field_label} cannot be negative.")
    return value


def _parse_optional_integer(raw_value: str, *, field_label: str) -> int | None:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return None
    try:
        return int(clean_value)
    except ValueError as exc:
        raise CharacterEditValidationError(f"The {field_label} must be a whole number.") from exc


def _parse_stat_adjustments(values: dict[str, str]) -> dict[str, int]:
    adjustments: dict[str, int] = {}
    for key, label, _ in STAT_ADJUSTMENT_FIELDS:
        value = _parse_optional_integer(values.get(f"stat_adjustment_{key}") or "", field_label=label.lower())
        if value:
            adjustments[key] = value
    return adjustments


def _normalize_activation_type(raw_value: Any) -> str:
    value = str(raw_value or "passive").strip().lower()
    return value if value in VALID_FEATURE_ACTIVATION_TYPES else "passive"


def _normalize_resource_reset_on(raw_value: Any) -> str:
    value = str(raw_value or "manual").strip().lower()
    return value if value in VALID_FEATURE_RESOURCE_RESET_TYPES else "manual"


def _build_unique_manual_id(prefix: str, name: str, used_ids: set[str]) -> str:
    base = slugify(name) or prefix
    candidate = f"{prefix}-{base}"
    index = 2
    while candidate in used_ids:
        candidate = f"{prefix}-{base}-{index}"
        index += 1
    return candidate


def _max_row_index(values: dict[str, str], prefix: str) -> int:
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_[a-z_]+_(\d+)$")
    for key in dict(values or {}):
        match = pattern.match(str(key))
        if match is None:
            continue
        highest = max(highest, int(match.group(1)))
    return highest
