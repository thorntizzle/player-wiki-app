from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Callable

from .auth_store import utcnow
from .character_adjustments import (
    apply_manual_stat_adjustments,
    apply_recoverable_ability_score_penalties,
    apply_recoverable_stat_penalties,
    apply_stat_adjustments,
    normalize_recoverable_penalties,
    restore_recoverable_ability_score_penalties,
    strip_manual_stat_adjustments,
    strip_recoverable_stat_penalties,
)
from .character_builder_constants import *  # noqa: F403
from .character_builder_equipment import (
    _ability_modifier,
    _active_item_effect_entries,
    _attack_matches_equipment_catalog,
    _attack_mode_components,
    _build_level_one_attacks,
    _character_has_named_feature,
    _character_mechanic_effect_rows,
    _dedupe_preserve_order,
    _derive_attack_reminder_state_from_character_inputs,
    _derive_defensive_state_from_character_inputs,
    _effect_keys_for_feature,
    _equipped_armor_profiles,
    _extract_character_effect_keys,
    _humanize_words,
    _infer_attack_mode_key_from_payload,
    _item_effect_metadata,
    _load_phb_armor_profiles,
    _load_phb_weapon_profiles,
    _mechanic_effect_numeric_value,
    _merge_recalculated_attack_overrides,
    _normalize_attack_equipment_refs,
    _normalize_attack_payloads,
    _normalize_equipment_payloads,
    _normalize_explicit_link_identity,
    _normalize_page_ref_payload,
    _resolve_armor_profile,
    _resolve_item_support_metadata,
    _resolved_armor_profiles,
    _split_effect_key,
    _systems_ref_from_entry,
)
from .character_builder_features import (
    _apply_tracker_templates_to_feature_payloads,
    _merge_resource_templates,
    _normalize_feature_payloads,
    _normalize_resource_template_payloads,
    _profile_class_row_level_map,
    _proficiency_bonus_for_level,
)
from .character_builder_foundation import (
    _class_caster_progression,
    _class_spell_progression,
    _effective_spellcasting_profile_for_row,
    _normalize_caster_progression,
    _resolve_native_character_level,
    _spellcasting_mode_for_class,
)
from .character_builder_spells import (
    _add_spell_to_payloads,
    _apply_spell_support_grants_to_payloads,
    _assign_spell_payload_class_rows,
    _automatic_spell_support_grants,
    _canonicalize_legacy_spell_payload_marks,
    _derive_spell_source_rows,
    _merge_name_candidates,
    _normalize_spell_payloads,
    _spell_payload_map_key,
    _spell_source_support_payload,
)
from .character_campaign_options import (
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
)
from .character_models import CharacterDefinition
from .character_profile import (
    ensure_profile_class_rows,
    profile_primary_class_name,
    profile_primary_subclass_name,
    sync_profile_class_summary,
)
from .character_source_matrix import PHB_SOURCE_ID
from .character_spell_slots import spell_slot_lanes_from_spellcasting
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_build_campaign_option_entry",
    "_campaign_option_feat_selections_from_features",
    "_campaign_option_feat_selected_choices_from_features",
    "_campaign_option_payloads_from_definition",
    "_definition_spellcasting_class_name",
    "_spellcasting_row_payload_from_context",
    "_spellcasting_rows_use_shared_slots",
    "_spell_slot_lane_id_for_row",
    "_spell_slot_lane_title_for_row",
    "_spell_slot_lanes_for_rows",
    "_infer_definition_save_proficiencies",
    "_definition_base_stats_without_adjustments",
    "_strip_definition_campaign_feat_effects",
    "_structured_ac_bonus",
    "_structured_ability_score_minimums",
    "_apply_campaign_option_ability_score_minimums",
    "_parse_effect_skill_names",
    "_parse_effect_ability_keys",
    "_skill_targets_for_effect_key",
    "_initiative_half_proficiency_bonus",
    "_effect_skill_bonus_map",
    "_effect_save_bonus_map",
    "_effect_passive_bonus",
    "_effect_initiative_bonus",
    "_effect_speed_bonus",
    "_effect_carrying_capacity_multiplier",
    "_effect_armor_dex_cap_bonus_map",
    "_derive_definition_max_hp",
    "_derive_definition_skills",
    "_derive_definition_stats",
    "_derive_definition_spellcasting",
    "_derive_definition_core_sheet_payloads",
    "_feature_choice_display_title",
    "_feature_expertise_selected_tool_name",
    "_supported_feature_expertise_blocks",
    "_feat_group_key",
    "_feat_selected_values",
    "_feature_group_key",
    "_feature_selected_values",
    "_apply_feat_ability_score_bonuses",
    "_strip_feat_ability_score_bonuses",
    "_extract_feat_skill_proficiencies",
    "_apply_skill_expertise_level",
    "_apply_feat_expertise_to_skill_proficiency_levels",
    "_apply_feature_expertise_to_skill_proficiency_levels",
    "_extract_feat_expertise_skills",
    "_extract_feat_saving_throw_proficiencies",
    "_feat_initiative_bonus",
    "_feat_speed_bonus",
    "_apply_speed_bonus_to_label",
    "_feat_passive_bonus",
    "_feat_hit_point_bonus",
    "_multiclass_slot_contribution_for_row",
    "_shared_slot_progression_for_caster_level",
    "_spellcasting_ability_name_for_class",
    "_spell_list_class_name_for_class",
    "_spell_progression_value",
    "_spell_slot_progression_for_class_level",
    "_prepared_spell_count_for_level",
    "_evaluate_prepared_spell_formula",
    "_prepared_spell_formula_ability_key",
    "_item_effect_source_row_ids_from_equipment",
    "_apply_item_effect_ability_score_minimums",
    "_apply_item_effect_spell_grants",
    "_apply_campaign_option_spell_grants",
    "_apply_item_effect_resource_template_bonuses",
    "_imported_character_can_prove_plain_unarmored_base",
    "_character_profile_class_names",
    "_character_profile_subclass_names",
    "_derive_armor_class_from_character_inputs",
    "_recalculate_definition_armor_class",
    "_recalculate_definition_attacks",
    "_is_equipment_independent_attack_payload",
    "_normalize_skill_proficiency_level",
    "_skill_proficiency_level_rank",
    "_max_skill_proficiency_level",
    "_skill_proficiency_level_from_bonus",
    "_skill_proficiency_levels_from_rows",
    "_skill_proficiency_levels_from_names",
    "_build_skills_payload_from_levels",
    "_build_skills_payload",
    "_build_level_one_stats",
    "_ability_scores_from_definition",
    "_build_leveled_stats",
    "_class_save_proficiencies",
    "_extract_size_label",
    "_normalize_size_label",
    "_definition_size_label",
    "_extract_speed_label",
    "_size_carrying_capacity_multiplier",
    "_normalize_weight_limit_value",
    "_derive_carrying_capacity_stats",
    "_skill_label",
    "_clean_embedded_text",
    "_replace_inline_tag",
]


def _character_build_error(message: str) -> Exception:
    from .character_builder_progression import CharacterBuildError

    return CharacterBuildError(message)


def _definition_source_type(definition: CharacterDefinition) -> str:
    return str((definition.source or {}).get("source_type") or "").strip()


def _definition_primary_subclass_name(definition: CharacterDefinition) -> str:
    return profile_primary_subclass_name(definition.profile)


def _native_progression_payload_for_derivation(source_payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(source_payload or {})
    payload = dict(source.get("native_progression") or {})
    hp_baseline = dict(payload.get("hp_baseline") or {})
    try:
        baseline_level = int(hp_baseline.get("level") or 0)
        baseline_max_hp = int(hp_baseline.get("max_hp") or 0)
    except (TypeError, ValueError):
        baseline_level = 0
        baseline_max_hp = 0
    if baseline_level > 0 and baseline_max_hp > 0:
        payload["hp_baseline"] = {
            "level": baseline_level,
            "max_hp": baseline_max_hp,
        }
    else:
        payload.pop("hp_baseline", None)
    history = [dict(entry) for entry in list(payload.get("history") or []) if isinstance(entry, dict)]
    if history:
        payload["history"] = history
    return payload


def _native_progression_hp_baseline_for_derivation(source_payload: dict[str, Any] | None) -> dict[str, int] | None:
    payload = _native_progression_payload_for_derivation(source_payload)
    hp_baseline = dict(payload.get("hp_baseline") or {})
    try:
        level = int(hp_baseline.get("level") or 0)
        max_hp = int(hp_baseline.get("max_hp") or 0)
    except (TypeError, ValueError):
        return None
    if level <= 0 or max_hp <= 0:
        return None
    return {"level": level, "max_hp": max_hp}


def _empty_item_catalog() -> dict[str, Any]:
    return {
        "entries": [],
        "by_title": {},
        "by_slug": {},
        "phb_weapon_profiles": _load_phb_weapon_profiles(),
        "phb_armor_profiles": _load_phb_armor_profiles(),
        "campaign_item_support_by_page_ref": {},
        "campaign_item_support_by_title": {},
    }


def _empty_spell_catalog() -> dict[str, Any]:
    return {
        "entries": [],
        "by_title": {},
        "by_slug": {},
        "phb_level_one_lists": {},
    }

def _build_campaign_option_entry(
    *,
    campaign_option: Any,
    page_ref: str,
    title: str,
    summary: str,
    section: str,
    subsection: str,
    kind: str,
) -> SystemsEntryRecord | None:
    option = dict(campaign_option or {}) if isinstance(campaign_option, dict) else {}
    if not option:
        return None
    if str(option.get("kind") or "").strip() != kind:
        return None

    clean_page_ref = str(page_ref or "").strip()
    clean_title = str(option.get("display_name") or title or clean_page_ref).strip() or clean_page_ref
    entry_type = {
        "feat": "feat",
        "species": "race",
        "background": "background",
    }.get(kind, kind)
    metadata: dict[str, Any] = {
        "page_ref": clean_page_ref,
        "campaign_option": deepcopy(option),
    }
    if kind == "feat":
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
            "optionalfeature_progression",
            "additional_spells",
            "spell_support",
            "mechanic_effects",
            "modeled_effects",
        ):
            if key in option:
                metadata[key] = deepcopy(option.get(key))
    elif kind == "species":
        for key in ("size", "speed", "languages", "skill_proficiencies", "tool_proficiencies", "feats", "spell_support"):
            if key in option:
                metadata[key] = deepcopy(option.get(key))
    elif kind == "background":
        for key in ("skill_proficiencies", "language_proficiencies", "tool_proficiencies", "spell_support"):
            if key in option:
                metadata[key] = deepcopy(option.get(key))

    now = utcnow()
    return SystemsEntryRecord(
        id=0,
        library_slug="campaign-pages",
        source_id=CAMPAIGN_PAGE_SOURCE_ID,
        entry_key=f"campaign-page|{entry_type}|{clean_page_ref}",
        entry_type=entry_type,
        slug=f"campaign-page-{slugify(clean_page_ref or clean_title)}",
        title=clean_title,
        source_page="",
        source_path=clean_page_ref,
        search_text=" ".join(
            part
            for part in (
                clean_title,
                str(summary or "").strip(),
                str(section or "").strip(),
                str(subsection or "").strip(),
            )
            if part
        ).casefold(),
        player_safe_default=True,
        dm_heavy=False,
        metadata=metadata,
        body={"entries": []},
        rendered_html="",
        created_at=now,
        updated_at=now,
    )

def _campaign_option_feat_selections_from_features(
    features: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    for index, feature in enumerate(list(features or []), start=1):
        feature_payload = dict(feature or {})
        campaign_option = dict(feature_payload.get("campaign_option") or {})
        raw_page_ref = feature_payload.get("page_ref")
        page_ref = (
            str(raw_page_ref.get("page_ref") or raw_page_ref.get("slug") or "").strip()
            if isinstance(raw_page_ref, dict)
            else str(raw_page_ref or "").strip()
        ) or str(campaign_option.get("page_ref") or "").strip()
        entry = _build_campaign_option_entry(
            campaign_option=campaign_option,
            page_ref=page_ref,
            title=str(
                campaign_option.get("display_name")
                or campaign_option.get("feat_name")
                or feature_payload.get("name")
                or campaign_option.get("title")
                or page_ref
            ),
            summary=str(campaign_option.get("summary") or feature_payload.get("description_markdown") or ""),
            section="Mechanics",
            subsection="Feats",
            kind="feat",
        )
        if not isinstance(entry, SystemsEntryRecord):
            continue
        feature_id = str(feature_payload.get("id") or "").strip() or f"campaign-feat-{index}"
        selections.append(
            {
                "entry": entry,
                "instance_key": f"campaign-option-feat-{slugify(feature_id) or index}",
            }
        )
    return selections

def _campaign_option_feat_selected_choices_from_features(
    features: list[dict[str, Any]] | None,
) -> dict[str, list[str]]:
    selected_choices: dict[str, list[str]] = {}
    for feature in list(features or []):
        feature_payload = dict(feature or {})
        selection_list = _campaign_option_feat_selections_from_features([feature_payload])
        if not selection_list:
            continue
        selection = dict(selection_list[0] or {})
        instance_key = str(selection.get("instance_key") or "").strip()
        if not instance_key:
            continue
        campaign_option = dict(feature_payload.get("campaign_option") or {})
        raw_selected_choices = dict(campaign_option.get("selected_choices") or {})
        if not raw_selected_choices:
            continue
        for raw_category, raw_values in raw_selected_choices.items():
            category = str(raw_category or "").strip()
            if not category:
                continue
            values = [
                str(raw_value).strip()
                for raw_value in list(raw_values or [])
                if str(raw_value or "").strip()
            ]
            if not values:
                continue
            selected_choices[_feat_group_key(instance_key, category)] = _dedupe_preserve_order(values)
    return selected_choices


def _campaign_option_payloads_from_definition(definition: CharacterDefinition) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for feature in list(definition.features or []):
        if isinstance(feature.get("campaign_option"), dict):
            payloads.append(dict(feature.get("campaign_option") or {}))
    for item in list(definition.equipment_catalog or []):
        if isinstance(item.get("campaign_option"), dict):
            payloads.append(dict(item.get("campaign_option") or {}))
    return payloads


def _definition_spellcasting_class_name(definition: CharacterDefinition) -> str:
    spellcasting_class = str((definition.spellcasting or {}).get("spellcasting_class") or "").strip()
    if spellcasting_class:
        return spellcasting_class
    class_name = profile_primary_class_name(definition.profile)
    if class_name:
        return class_name
    return ""

def _spellcasting_row_payload_from_context(
    row_context: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> dict[str, Any] | None:
    selected_class = row_context.get("selected_class")
    if not isinstance(selected_class, SystemsEntryRecord):
        return None
    selected_subclass = (
        row_context.get("selected_subclass")
        if isinstance(row_context.get("selected_subclass"), SystemsEntryRecord)
        else None
    )
    class_payload = dict(row_context.get("class_payload") or {})
    class_name = str(selected_class.title or class_payload.get("class_name") or "").strip()
    row_level = max(int(row_context.get("row_level") or class_payload.get("level") or 0), 0)
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    caster_progression = _class_caster_progression(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    if not spell_mode and not caster_progression:
        return None

    ability_name = _spellcasting_ability_name_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    ability_key = next((key for key, label in ABILITY_LABELS.items() if label == ability_name), "")
    modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) if ability_key else 0
    return {
        "class_row_id": str(row_context.get("row_id") or class_payload.get("row_id") or "").strip(),
        "class_name": class_name,
        "spell_list_class_name": _spell_list_class_name_for_class(
            class_name,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            row_level=row_level,
        ),
        "class_ref": _systems_ref_from_entry(selected_class),
        "level": row_level,
        "caster_progression": caster_progression,
        "spell_mode": spell_mode,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier if ability_key else None,
        "spell_attack_bonus": proficiency_bonus + modifier if ability_key else None,
    }

def _spellcasting_rows_use_shared_slots(
    class_rows: list[dict[str, Any]],
    *,
    total_class_rows: int = 0,
) -> bool:
    spell_rows = [dict(row or {}) for row in list(class_rows or []) if dict(row or {})]
    if not spell_rows or int(total_class_rows or 0) <= 1:
        return False
    return all(
        str(row.get("caster_progression") or "").strip() in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS
        for row in spell_rows
    )

def _spell_slot_lane_id_for_row(row_payload: dict[str, Any], *, fallback_index: int) -> str:
    row_id = str(row_payload.get("class_row_id") or "").strip()
    if row_id:
        return f"{row_id}-slots"
    return f"slot-lane-{fallback_index}"

def _spell_slot_lane_title_for_row(
    row_payload: dict[str, Any],
    *,
    total_spell_rows: int,
) -> str:
    class_name = str(row_payload.get("class_name") or "Spellcasting").strip() or "Spellcasting"
    caster_progression = _normalize_caster_progression(row_payload.get("caster_progression"))
    if caster_progression == "pact":
        return f"{class_name} Pact Magic slots" if total_spell_rows > 1 else "Pact Magic slots"
    if total_spell_rows > 1:
        return f"{class_name} spell slots"
    return "Spell slots"

def _spell_slot_lanes_for_rows(
    spellcasting_rows: list[dict[str, Any]],
    *,
    row_contexts: list[dict[str, Any]] | None = None,
    total_class_rows: int = 0,
    current_level: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_rows = [dict(row or {}) for row in list(spellcasting_rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return [], []

    selected_class_by_row_id = {
        str(dict(context or {}).get("row_id") or "").strip(): context.get("selected_class")
        for context in list(row_contexts or [])
        if str(dict(context or {}).get("row_id") or "").strip()
    }
    selected_subclass_by_row_id = {
        str(dict(context or {}).get("row_id") or "").strip(): context.get("selected_subclass")
        for context in list(row_contexts or [])
        if str(dict(context or {}).get("row_id") or "").strip()
    }
    total_spell_rows = len(normalized_rows)
    shareable_row_ids = {
        str(row.get("class_row_id") or "").strip()
        for row in normalized_rows
        if _normalize_caster_progression(row.get("caster_progression")) in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS
    }
    use_shared_lane = bool(total_class_rows > 1 and len(shareable_row_ids) > 1)
    slot_lanes: list[dict[str, Any]] = []
    updated_rows: list[dict[str, Any]] = []
    shared_lane_added = False

    for index, row in enumerate(normalized_rows, start=1):
        row_payload = dict(row or {})
        row_id = str(row_payload.get("class_row_id") or "").strip()
        caster_progression = _normalize_caster_progression(row_payload.get("caster_progression"))
        row_selected_class = selected_class_by_row_id.get(row_id)
        row_selected_subclass = selected_subclass_by_row_id.get(row_id)
        class_name = str(row_payload.get("class_name") or "").strip()
        class_level = max(int(row_payload.get("level") or current_level), 0)

        if use_shared_lane and row_id in shareable_row_ids:
            row_payload["slot_lane_id"] = "shared-multiclass-slots"
            row_payload["slot_lane_title"] = "Shared spell slots"
            if not shared_lane_added:
                total_caster_level = sum(
                    _multiclass_slot_contribution_for_row(
                        int(candidate.get("level") or 0),
                        str(candidate.get("caster_progression") or "").strip(),
                    )
                    for candidate in normalized_rows
                    if str(candidate.get("class_row_id") or "").strip() in shareable_row_ids
                )
                slot_lanes.append(
                    {
                        "id": "shared-multiclass-slots",
                        "title": "Shared spell slots",
                        "shared": True,
                        "row_ids": [candidate_id for candidate_id in shareable_row_ids if candidate_id],
                        "slot_progression": _shared_slot_progression_for_caster_level(total_caster_level),
                    }
                )
                shared_lane_added = True
            updated_rows.append(row_payload)
            continue

        slot_lane_id = _spell_slot_lane_id_for_row(row_payload, fallback_index=index)
        slot_lane_title = _spell_slot_lane_title_for_row(
            row_payload,
            total_spell_rows=total_spell_rows,
        )
        slot_lanes.append(
            {
                "id": slot_lane_id,
                "title": slot_lane_title,
                "shared": False,
                "row_ids": [row_id] if row_id else [],
                "slot_progression": _spell_slot_progression_for_class_level(
                    class_name,
                    class_level,
                    selected_class=row_selected_class if isinstance(row_selected_class, SystemsEntryRecord) else None,
                    selected_subclass=(
                        row_selected_subclass if isinstance(row_selected_subclass, SystemsEntryRecord) else None
                    ),
                ),
            }
        )
        row_payload["slot_lane_id"] = slot_lane_id
        row_payload["slot_lane_title"] = slot_lane_title
        updated_rows.append(row_payload)

    return updated_rows, slot_lanes

def _infer_definition_save_proficiencies(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    selected_class: SystemsEntryRecord | None = None,
) -> set[str]:
    save_proficiencies = set(_class_save_proficiencies(selected_class))
    if proficiency_bonus <= 0:
        return save_proficiencies
    ability_payloads = dict((definition.stats or {}).get("ability_scores") or {})
    save_bonus_map = (
        _effect_save_bonus_map(_extract_character_effect_keys(list(definition.features or [])))
        if selected_class is not None
        else {}
    )
    for ability_key in ABILITY_KEYS:
        try:
            save_bonus = int(
                dict(
                    ability_payloads.get(ability_key)
                    or ability_payloads.get(str(ABILITY_LABELS.get(ability_key, "")).lower())
                    or {}
                ).get("save_bonus")
            )
        except (TypeError, ValueError):
            continue
        inferred_bonus = save_bonus - int(save_bonus_map.get(ability_key) or 0)
        if inferred_bonus - _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) >= proficiency_bonus:
            save_proficiencies.add(ability_key)
    return save_proficiencies

def _definition_base_stats_without_adjustments(definition: CharacterDefinition) -> dict[str, Any]:
    stats, _manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    stats, _recoverable_penalties = strip_recoverable_stat_penalties(stats)
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    return stats

def _strip_definition_campaign_feat_effects(
    definition: CharacterDefinition,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> CharacterDefinition:
    features = [dict(feature or {}) for feature in list(definition.features or [])]
    feat_selections = _campaign_option_feat_selections_from_features(features)
    if not feat_selections:
        return definition
    feat_selected_choices = _campaign_option_feat_selected_choices_from_features(features)
    payload = deepcopy(definition.to_dict())
    stats = deepcopy(payload.get("stats") or {})
    ability_payloads = dict(stats.get("ability_scores") or {})
    stripped_scores = _strip_feat_ability_score_bonuses(
        _ability_scores_from_definition(definition),
        feat_selections=feat_selections,
        selected_choices=feat_selected_choices,
    )
    for ability_key in ABILITY_KEYS:
        payload_key = ability_key
        legacy_key = str(ABILITY_LABELS.get(ability_key, "")).lower()
        ability_payload = dict(
            ability_payloads.get(payload_key)
            or ability_payloads.get(legacy_key)
            or {}
        )
        stripped_score = int(stripped_scores.get(ability_key, DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        ability_payload["score"] = stripped_score
        ability_payload["modifier"] = _ability_modifier(stripped_score)
        ability_payloads[payload_key] = ability_payload
    proficiency_bonus = int(
        stats.get("proficiency_bonus")
        or _proficiency_bonus_for_level(_resolve_native_character_level(definition))
        or 2
    )
    class_save_proficiencies = set(_class_save_proficiencies(selected_class))
    for ability_key in _extract_feat_saving_throw_proficiencies(
        feat_selections,
        feat_selected_choices,
    ):
        if ability_key in class_save_proficiencies:
            continue
        ability_payload = dict(ability_payloads.get(ability_key) or {})
        base_modifier = _ability_modifier(int(stripped_scores.get(ability_key, DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
        try:
            current_save_bonus = int(ability_payload.get("save_bonus"))
        except (TypeError, ValueError):
            current_save_bonus = base_modifier
        if current_save_bonus - base_modifier < proficiency_bonus:
            ability_payload["save_bonus"] = base_modifier
        else:
            ability_payload["save_bonus"] = current_save_bonus - proficiency_bonus
        ability_payloads[ability_key] = ability_payload
    stats["ability_scores"] = ability_payloads
    feat_skill_proficiencies = {
        normalize_lookup(skill_name)
        for skill_name in _extract_feat_skill_proficiencies(
            feat_selections,
            feat_selected_choices,
        )
        if normalize_lookup(skill_name) in SKILL_LABELS
    }
    feat_expertise_skills = {
        normalize_lookup(skill_name)
        for skill_name in _extract_feat_expertise_skills(
            feat_selections,
            feat_selected_choices,
        )
        if normalize_lookup(skill_name) in SKILL_LABELS
    }
    stripped_skill_rows: list[dict[str, Any]] = []
    for row in list(payload.get("skills") or []):
        row_payload = dict(row or {})
        normalized_skill = normalize_lookup(row_payload.get("name"))
        proficiency_level = _normalize_skill_proficiency_level(
            row_payload.get("proficiency_level")
        )
        if normalized_skill in feat_expertise_skills and proficiency_level == "expertise":
            row_payload["proficiency_level"] = "proficient"
            row_payload.pop("bonus", None)
        elif normalized_skill in feat_skill_proficiencies and proficiency_level == "proficient":
            row_payload["proficiency_level"] = "none"
            row_payload.pop("bonus", None)
        stripped_skill_rows.append(row_payload)
    payload["stats"] = stats
    payload["skills"] = stripped_skill_rows
    return CharacterDefinition.from_dict(payload)

def _structured_ac_bonus(features: list[dict[str, Any]] | None) -> int:
    bonus = 0
    for row in _character_mechanic_effect_rows(features, kind="ac_bonus"):
        bonus += _mechanic_effect_numeric_value(row, "bonus", "ac_bonus", "acBonus", "amount", "value")
    return bonus

def _structured_ability_score_minimums(features: list[dict[str, Any]] | None) -> dict[str, int]:
    minimums: dict[str, int] = {}
    for row in _character_mechanic_effect_rows(features, kind="ability_minimum"):
        ability_minimums = row.get("ability_score_minimums") or row.get("abilityScoreMinimums")
        if isinstance(ability_minimums, dict):
            raw_items = list(ability_minimums.items())
        else:
            raw_items = [
                (
                    row.get("ability")
                    or row.get("ability_key")
                    or row.get("abilityKey")
                    or row.get("score"),
                    row.get("minimum") or row.get("min") or row.get("value"),
                )
            ]
        for raw_ability, raw_minimum in raw_items:
            ability_key = normalize_lookup(str(raw_ability or "").strip())
            if ability_key not in ABILITY_KEYS:
                continue
            try:
                minimum_value = int(raw_minimum)
            except (TypeError, ValueError):
                continue
            minimums[ability_key] = max(int(minimums.get(ability_key) or 0), minimum_value)
    return minimums

def _apply_campaign_option_ability_score_minimums(
    ability_scores: dict[str, int],
    *,
    features: list[dict[str, Any]] | None,
) -> dict[str, int]:
    adjusted_scores = {
        ability_key: int(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        for ability_key in ABILITY_KEYS
    }
    for ability_key, minimum in _structured_ability_score_minimums(features).items():
        adjusted_scores[ability_key] = max(adjusted_scores[ability_key], int(minimum or 0))
    return adjusted_scores

def _parse_effect_skill_names(value: Any) -> list[str]:
    results: list[str] = []
    for raw_skill in str(value or "").split(","):
        normalized_skill = normalize_lookup(raw_skill)
        if normalized_skill in SKILL_LABELS:
            results.append(normalized_skill)
    return _dedupe_preserve_order(results)

def _parse_effect_ability_keys(value: Any) -> list[str]:
    results: list[str] = []
    for raw_ability in str(value or "").split(","):
        normalized_ability = normalize_lookup(raw_ability)
        if normalized_ability in ABILITY_KEYS:
            results.append(normalized_ability)
    return _dedupe_preserve_order(results)

def _skill_targets_for_effect_key(effect_key: Any) -> list[str]:
    parts = _split_effect_key(effect_key)
    if len(parts) < 2 or normalize_lookup(parts[0]) != normalize_lookup("half-proficiency"):
        return []
    target_kind = normalize_lookup(parts[1])
    if target_kind == normalize_lookup("all"):
        return list(SKILL_LABELS.keys())
    if target_kind == normalize_lookup("skills") and len(parts) >= 3:
        return _parse_effect_skill_names(parts[2])
    if target_kind == normalize_lookup("abilities") and len(parts) >= 3:
        ability_keys = set(_parse_effect_ability_keys(parts[2]))
        return [
            normalized_skill
            for normalized_skill, ability_key in SKILL_ABILITY_KEYS.items()
            if ability_key in ability_keys
        ]
    return []

def _initiative_half_proficiency_bonus(effect_keys: list[str], *, proficiency_bonus: int) -> int:
    half_bonus = proficiency_bonus // 2
    if half_bonus <= 0:
        return 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) < 2 or normalize_lookup(parts[0]) != normalize_lookup("half-proficiency"):
            continue
        target_kind = normalize_lookup(parts[1])
        if target_kind == normalize_lookup("all"):
            return half_bonus
        if target_kind == normalize_lookup("abilities") and len(parts) >= 3:
            if "dex" in set(_parse_effect_ability_keys(parts[2])):
                return half_bonus
    return 0

def _effect_skill_bonus_map(effect_keys: list[str]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 3 or normalize_lookup(parts[0]) != normalize_lookup("skill-bonus"):
            continue
        normalized_skill = normalize_lookup(parts[1])
        if normalized_skill not in SKILL_LABELS:
            continue
        try:
            bonus = int(parts[2])
        except ValueError:
            continue
        bonuses[normalized_skill] = int(bonuses.get(normalized_skill) or 0) + bonus
    return bonuses

def _effect_save_bonus_map(effect_keys: list[str]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) < 3 or normalize_lookup(parts[0]) != normalize_lookup("save-bonus"):
            continue
        target_kind = normalize_lookup(parts[1])
        target_ability_keys: list[str] = []
        raw_bonus = ""
        if target_kind == normalize_lookup("all") and len(parts) == 3:
            target_ability_keys = list(ABILITY_KEYS)
            raw_bonus = parts[2]
        elif target_kind == normalize_lookup("abilities") and len(parts) == 4:
            target_ability_keys = _parse_effect_ability_keys(parts[2])
            raw_bonus = parts[3]
        if not target_ability_keys:
            continue
        try:
            bonus = int(raw_bonus)
        except ValueError:
            continue
        for ability_key in target_ability_keys:
            bonuses[ability_key] = int(bonuses.get(ability_key) or 0) + bonus
    return bonuses

def _effect_passive_bonus(effect_keys: list[str], *, skill_name: str) -> int:
    normalized_skill = normalize_lookup(skill_name)
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 3 or normalize_lookup(parts[0]) != normalize_lookup("passive-bonus"):
            continue
        if normalize_lookup(parts[1]) != normalized_skill:
            continue
        try:
            bonus += int(parts[2])
        except ValueError:
            continue
    return bonus

def _effect_initiative_bonus(
    effect_keys: list[str],
    *,
    proficiency_bonus: int,
    ability_scores: dict[str, int] | None = None,
) -> int:
    bonus = _initiative_half_proficiency_bonus(effect_keys, proficiency_bonus=proficiency_bonus)
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        effect_kind = normalize_lookup(parts[0]) if parts else ""
        if len(parts) == 2 and effect_kind == normalize_lookup("initiative-bonus"):
            try:
                bonus += int(parts[1])
            except ValueError:
                continue
        if len(parts) == 2 and effect_kind == normalize_lookup("initiative-bonus-ability"):
            ability_key = normalize_lookup(parts[1])
            if ability_key in ABILITY_KEYS:
                bonus += _ability_modifier(dict(ability_scores or {}).get(ability_key, 10))
    return bonus

def _effect_speed_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("speed-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus

def _effect_carrying_capacity_multiplier(effect_keys: list[str]) -> float:
    multiplier = 1.0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("carrying-capacity-multiplier"):
            continue
        try:
            value = float(parts[1])
        except ValueError:
            continue
        if value <= 0:
            continue
        multiplier *= value
    return multiplier

def _effect_armor_dex_cap_bonus_map(effect_keys: list[str]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 3 or normalize_lookup(parts[0]) != normalize_lookup("armor-dex-cap-bonus"):
            continue
        armor_category = normalize_lookup(parts[1])
        if not armor_category:
            continue
        try:
            bonus = int(parts[2])
        except ValueError:
            continue
        bonuses[armor_category] = int(bonuses.get(armor_category) or 0) + bonus
    return bonuses

def _derive_definition_max_hp(
    definition: CharacterDefinition,
    *,
    current_level: int,
) -> int | None:
    hp_baseline = _native_progression_hp_baseline_for_derivation(definition.source)
    if hp_baseline is None:
        return None
    baseline_level = int(hp_baseline.get("level") or 0)
    if current_level < baseline_level or baseline_level <= 0:
        return None
    derived_max_hp = int(hp_baseline.get("max_hp") or 0)
    if current_level == baseline_level:
        return max(derived_max_hp, 1)
    native_progression = _native_progression_payload_for_derivation(definition.source)
    gains_by_level: dict[int, int] = {}
    for event in list(native_progression.get("history") or []):
        if not isinstance(event, dict):
            continue
        try:
            event_level = int(event.get("to_level") or event.get("target_level") or 0)
        except (TypeError, ValueError):
            continue
        if event_level <= baseline_level or event_level > current_level:
            continue
        if "max_hp_delta" in event:
            delta_field = "max_hp_delta"
        elif "hp_gain" in event:
            delta_field = "hp_gain"
        else:
            continue
        try:
            gains_by_level[event_level] = int(event.get(delta_field) or 0)
        except (TypeError, ValueError):
            return None
    for level in range(baseline_level + 1, current_level + 1):
        if level not in gains_by_level:
            return None
        derived_max_hp += gains_by_level[level]
    return max(derived_max_hp, 1)

def _derive_definition_skills(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> list[dict[str, Any]]:
    existing_rows = [dict(row or {}) for row in list(definition.skills or [])]
    if not existing_rows:
        return []
    campaign_feat_selections = _campaign_option_feat_selections_from_features(list(definition.features or []))
    feat_selected_choices = _campaign_option_feat_selected_choices_from_features(
        list(definition.features or [])
    )
    proficiency_levels = _skill_proficiency_levels_from_rows(
        existing_rows,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(
        _campaign_option_payloads_from_definition(definition)
    )
    for skill_name in list(campaign_option_proficiencies.get("skills") or []):
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
            proficiency_levels.get(normalized_skill),
            "proficient",
        )
    for skill_name in _extract_feat_skill_proficiencies(campaign_feat_selections, feat_selected_choices):
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
            proficiency_levels.get(normalized_skill),
            "proficient",
        )
    proficiency_levels = _apply_feat_expertise_to_skill_proficiency_levels(
        proficiency_levels,
        feat_selections=campaign_feat_selections,
        selected_choices=feat_selected_choices,
    )
    effect_keys = _extract_character_effect_keys(list(definition.features or []))
    for effect_key in effect_keys:
        for normalized_skill in _skill_targets_for_effect_key(effect_key):
            proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
                proficiency_levels.get(normalized_skill),
                "half_proficient",
            )
    return _build_skills_payload_from_levels(
        ability_scores,
        proficiency_levels,
        proficiency_bonus,
        skill_bonus_map=_effect_skill_bonus_map(effect_keys),
    )

def _derive_definition_stats(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    skills: list[dict[str, Any]],
    features: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    selected_class: SystemsEntryRecord | None = None,
    selected_species: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    stats, recoverable_penalties = strip_recoverable_stat_penalties(stats)
    existing_ability_scores = dict(stats.get("ability_scores") or {})
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    campaign_feat_selections = _campaign_option_feat_selections_from_features(features)
    feat_selected_choices = _campaign_option_feat_selected_choices_from_features(features)
    save_proficiencies = _infer_definition_save_proficiencies(
        definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        selected_class=selected_class,
    )
    save_proficiencies.update(
        _extract_feat_saving_throw_proficiencies(campaign_feat_selections, feat_selected_choices)
    )
    effect_keys = _extract_character_effect_keys(features)
    save_bonus_map = _effect_save_bonus_map(effect_keys)
    skill_lookup = {normalize_lookup(skill.get("name")): dict(skill) for skill in list(skills or [])}
    if skill_lookup:
        stats["passive_perception"] = 10 + int(
            (skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Perception")
        stats["passive_insight"] = 10 + int(
            (skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Insight")
        stats["passive_investigation"] = 10 + int(
            (skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Investigation")
    stats["proficiency_bonus"] = proficiency_bonus
    stats["initiative_bonus"] = _ability_modifier(ability_scores["dex"]) + _effect_initiative_bonus(
        effect_keys,
        proficiency_bonus=proficiency_bonus,
        ability_scores=ability_scores,
    )
    normalized_ability_scores = {
        ability_key: {
            "score": score,
            "modifier": _ability_modifier(score),
            "save_bonus": _ability_modifier(score)
            + (proficiency_bonus if ability_key in save_proficiencies else 0)
            + int(save_bonus_map.get(ability_key) or 0),
        }
        for ability_key, score in ability_scores.items()
    }
    stats["ability_scores"] = {}
    for ability_key, payload in normalized_ability_scores.items():
        if ability_key in existing_ability_scores or str(ABILITY_LABELS.get(ability_key, "")).lower() not in existing_ability_scores:
            stats["ability_scores"][ability_key] = dict(payload)
        alias_key = str(ABILITY_LABELS.get(ability_key, "")).lower()
        if alias_key in existing_ability_scores:
            stats["ability_scores"][alias_key] = dict(payload)
    derived_armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=list(definition.equipment_catalog or []),
        features=features,
        class_names=_character_profile_class_names(definition),
        subclass_names=_character_profile_subclass_names(definition),
        item_catalog=item_catalog,
        allow_plain_unarmored_base=_definition_source_type(definition) == "native_character_builder",
    )
    if derived_armor_class is not None:
        stats["armor_class"] = derived_armor_class
    stats["attack_reminder_state"] = _derive_attack_reminder_state_from_character_inputs(
        features=features,
        equipment_catalog=list(definition.equipment_catalog or []),
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    stats["defensive_state"] = _derive_defensive_state_from_character_inputs(
        equipment_catalog=list(definition.equipment_catalog or []),
        features=features,
        item_catalog=item_catalog,
    )
    derived_speed = ""
    if selected_species is not None:
        derived_speed = _apply_speed_bonus_to_label(
            _extract_speed_label(selected_species),
            _effect_speed_bonus(effect_keys),
        )
    if derived_speed:
        stats["speed"] = derived_speed
    stats.update(
        _derive_carrying_capacity_stats(
            strength_score=ability_scores["str"],
            size_label=_definition_size_label(definition, selected_species=selected_species),
            effect_keys=effect_keys,
        )
    )
    derived_max_hp = _derive_definition_max_hp(
        definition,
        current_level=max(_resolve_native_character_level(definition), 0),
    )
    if derived_max_hp is not None:
        stats["max_hp"] = derived_max_hp
    stats = apply_stat_adjustments(stats, campaign_option_adjustments)
    stats = apply_recoverable_stat_penalties(stats, recoverable_penalties, adjust_ability_scores=False)
    return apply_manual_stat_adjustments(stats, manual_adjustments)

def _derive_definition_spellcasting(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    current_level: int,
    selected_class: SystemsEntryRecord | None = None,
    selected_class_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spellcasting = dict(definition.spellcasting or {})
    saved_spellcasting_rows = [
        {
            **dict(row or {}),
            "class_row_id": str(
                dict(row or {}).get("class_row_id") or dict(row or {}).get("row_id") or f"class-row-{index}"
            ).strip()
            or f"class-row-{index}",
            "class_name": str(dict(row or {}).get("class_name") or "Spellcasting").strip() or "Spellcasting",
            "spell_list_class_name": str(dict(row or {}).get("spell_list_class_name") or "").strip(),
            "spellcasting_ability": str(dict(row or {}).get("spellcasting_ability") or "").strip(),
            "spell_mode": str(dict(row or {}).get("spell_mode") or "").strip(),
            "caster_progression": str(dict(row or {}).get("caster_progression") or "").strip(),
            "slot_lane_id": str(dict(row or {}).get("slot_lane_id") or "").strip(),
        }
        for index, row in enumerate(list(spellcasting.get("class_rows") or []), start=1)
        if isinstance(row, dict)
    ]
    saved_slot_lanes = (
        spell_slot_lanes_from_spellcasting(spellcasting)
        if saved_spellcasting_rows or list(spellcasting.get("slot_lanes") or [])
        else []
    )
    row_contexts = [dict(row or {}) for row in list(selected_class_rows or []) if isinstance(row, dict)]
    if not row_contexts and selected_class is not None:
        row_contexts = [
            {
                "row_id": str((ensure_profile_class_rows(definition.profile)[0] or {}).get("row_id") or "class-row-1"),
                "row_level": current_level,
                "class_payload": dict((ensure_profile_class_rows(definition.profile)[0] or {})),
                "selected_class": selected_class,
                "selected_subclass": None,
            }
        ]
    spellcasting_rows = [
        row_payload
        for row_payload in (
            _spellcasting_row_payload_from_context(
                row_context,
                ability_scores=ability_scores,
                proficiency_bonus=proficiency_bonus,
            )
            for row_context in row_contexts
        )
        if row_payload is not None
    ]
    total_class_rows = len(ensure_profile_class_rows(definition.profile))
    spellcasting_rows, slot_lanes = _spell_slot_lanes_for_rows(
        spellcasting_rows,
        row_contexts=row_contexts,
        total_class_rows=total_class_rows,
        current_level=current_level,
    )
    if saved_spellcasting_rows and len(spellcasting_rows) < len(saved_spellcasting_rows):
        spellcasting_rows = saved_spellcasting_rows
        slot_lanes = saved_slot_lanes
    elif not spellcasting_rows and saved_slot_lanes:
        slot_lanes = saved_slot_lanes
    spellcasting["class_rows"] = spellcasting_rows
    spellcasting["spells"] = _assign_spell_payload_class_rows(
        list(spellcasting.get("spells") or []),
        spellcasting_rows=spellcasting_rows,
    )
    spellcasting["source_rows"] = _derive_spell_source_rows(
        list(spellcasting.get("spells") or []),
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    spellcasting["slot_lanes"] = slot_lanes
    if not spellcasting_rows:
        spellcasting["slot_progression"] = [
            dict(slot or {})
            for slot in list(spellcasting.get("slot_progression") or [])
        ]
        spellcasting["spellcasting_class"] = str(spellcasting.get("spellcasting_class") or "").strip()
        spellcasting["spellcasting_ability"] = str(spellcasting.get("spellcasting_ability") or "").strip()
        fallback_ability_name = str(spellcasting.get("spellcasting_ability") or "").strip()
        fallback_ability_key = next(
            (key for key, label in ABILITY_LABELS.items() if label == fallback_ability_name),
            "",
        )
        if fallback_ability_key:
            modifier = _ability_modifier(ability_scores.get(fallback_ability_key, DEFAULT_ABILITY_SCORE))
            spellcasting["spell_save_dc"] = 8 + proficiency_bonus + modifier
            spellcasting["spell_attack_bonus"] = proficiency_bonus + modifier
        return spellcasting

    if len(spellcasting_rows) == 1:
        row_payload = dict(spellcasting_rows[0] or {})
        class_name = str(row_payload.get("class_name") or "").strip()
        slot_progression = [dict(slot or {}) for slot in list((slot_lanes[0] or {}).get("slot_progression") or [])]
        spellcasting["spellcasting_class"] = class_name
        spellcasting["spellcasting_ability"] = str(row_payload.get("spellcasting_ability") or "").strip()
        spellcasting["spell_save_dc"] = row_payload.get("spell_save_dc")
        spellcasting["spell_attack_bonus"] = row_payload.get("spell_attack_bonus")
        spellcasting["slot_progression"] = slot_progression
        return spellcasting

    if len(slot_lanes) == 1:
        spellcasting["slot_progression"] = [
            dict(slot or {})
            for slot in list((slot_lanes[0] or {}).get("slot_progression") or [])
        ]
    else:
        spellcasting["slot_progression"] = []

    spellcasting["spellcasting_class"] = ""
    spellcasting["spellcasting_ability"] = ""
    spellcasting["spell_save_dc"] = None
    spellcasting["spell_attack_bonus"] = None
    return spellcasting

def _derive_definition_core_sheet_payloads(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    resolved_entries: dict[str, Any] | None = None,
    resolve_definition_sheet_entries_func: Callable[..., dict[str, Any]] | None = None,
    effective_item_catalog_for_definition_func: Callable[..., dict[str, Any]] | None = None,
    effective_spell_catalog_for_definition_func: Callable[..., dict[str, Any]] | None = None,
    automatic_prepared_spell_flags_func: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    resolved_entries = dict(resolved_entries or {})
    if not resolved_entries and resolve_definition_sheet_entries_func is not None:
        resolved_entries = resolve_definition_sheet_entries_func(
            definition,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            resolved_class=resolved_class,
            resolved_subclass=resolved_subclass,
            resolved_species=resolved_species,
            resolved_background=resolved_background,
        )
    sanitized_definition = _strip_definition_campaign_feat_effects(
        definition,
        selected_class=resolved_entries.get("selected_class"),
    )
    effective_item_catalog = (
        effective_item_catalog_for_definition_func(
            sanitized_definition,
            item_catalog=item_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        if effective_item_catalog_for_definition_func is not None
        else dict(item_catalog or _empty_item_catalog())
    )
    effective_spell_catalog = (
        effective_spell_catalog_for_definition_func(
            sanitized_definition,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        if effective_spell_catalog_for_definition_func is not None
        else dict(spell_catalog or _empty_spell_catalog())
    )
    normalized_equipment = _normalize_equipment_payloads(
        list(sanitized_definition.equipment_catalog or []),
        item_catalog=effective_item_catalog,
    )
    item_effect_entries = _active_item_effect_entries(
        normalized_equipment,
        item_catalog=effective_item_catalog,
    )
    item_effect_source_row_ids = _item_effect_source_row_ids_from_equipment(
        normalized_equipment,
        item_catalog=effective_item_catalog,
    )
    recoverable_penalties = normalize_recoverable_penalties((sanitized_definition.stats or {}).get("recoverable_penalties"))
    ability_scores = _ability_scores_from_definition(
        sanitized_definition,
        include_recoverable_penalties=False,
    )
    campaign_feat_selections = _campaign_option_feat_selections_from_features(
        list(sanitized_definition.features or [])
    )
    feat_selected_choices = _campaign_option_feat_selected_choices_from_features(
        list(sanitized_definition.features or [])
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        ability_scores,
        feat_selections=campaign_feat_selections,
        selected_choices=feat_selected_choices,
        strict=False,
    )
    ability_scores = _apply_campaign_option_ability_score_minimums(
        ability_scores,
        features=list(sanitized_definition.features or []),
    )
    ability_scores = _apply_item_effect_ability_score_minimums(
        ability_scores,
        item_effect_entries=item_effect_entries,
    )
    ability_scores = apply_recoverable_ability_score_penalties(
        ability_scores,
        recoverable_penalties,
    )
    current_level = _resolve_native_character_level(sanitized_definition)
    proficiency_bonus = (
        _proficiency_bonus_for_level(current_level)
        if current_level > 0
        else int((sanitized_definition.stats or {}).get("proficiency_bonus") or 2)
    )
    normalized_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        _normalize_feature_payloads(list(sanitized_definition.features or [])),
        ability_scores=ability_scores,
        current_level=max(current_level, 1),
        class_row_levels=_profile_class_row_level_map(sanitized_definition.profile),
    )
    normalized_payload = deepcopy(sanitized_definition.to_dict())
    normalized_payload["features"] = normalized_features
    normalized_payload["equipment_catalog"] = normalized_equipment
    normalized_definition = CharacterDefinition.from_dict(normalized_payload)
    skills = _derive_definition_skills(
        normalized_definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    stats = _derive_definition_stats(
        normalized_definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        skills=skills,
        features=normalized_features,
        item_catalog=effective_item_catalog,
        selected_class=resolved_entries.get("selected_class"),
        selected_species=resolved_entries.get("selected_species"),
    )
    derived_payload = deepcopy(normalized_payload)
    derived_payload["skills"] = skills
    derived_payload["stats"] = stats
    derived_definition = CharacterDefinition.from_dict(derived_payload)
    derived_spellcasting = _derive_definition_spellcasting(
        derived_definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        current_level=max(current_level, 1),
        selected_class=resolved_entries.get("selected_class"),
        selected_class_rows=list(resolved_entries.get("selected_class_rows") or []),
    )
    if automatic_prepared_spell_flags_func is None:
        from .character_builder_progression import _apply_automatic_prepared_spell_flags

        automatic_prepared_spell_flags_func = _apply_automatic_prepared_spell_flags
    derived_spellcasting["spells"] = automatic_prepared_spell_flags_func(
        list(derived_spellcasting.get("spells") or []),
        campaign_slug=definition.campaign_slug,
        systems_service=systems_service,
        resolved_class_rows=list(resolved_entries.get("selected_class_rows") or []),
        spell_catalog=effective_spell_catalog,
    )
    derived_spellcasting["spells"] = _apply_campaign_option_spell_grants(
        list(derived_spellcasting.get("spells") or []),
        option_payloads=_campaign_option_payloads_from_definition(normalized_definition),
        spell_catalog=effective_spell_catalog,
    )
    derived_spellcasting["spells"] = _apply_item_effect_spell_grants(
        list(derived_spellcasting.get("spells") or []),
        item_effect_entries=item_effect_entries,
        known_source_row_ids=item_effect_source_row_ids,
        spell_catalog=effective_spell_catalog,
        current_level=max(current_level, 1),
    )
    derived_spellcasting["spells"] = _canonicalize_legacy_spell_payload_marks(
        list(derived_spellcasting.get("spells") or []),
        spell_catalog=effective_spell_catalog,
        spellcasting_rows=list(derived_spellcasting.get("class_rows") or []),
    )
    derived_spellcasting["source_rows"] = _derive_spell_source_rows(
        list(derived_spellcasting.get("spells") or []),
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    merged_resource_templates = _merge_resource_templates(
        list(sanitized_definition.resource_templates or []),
        derived_resource_templates,
    )
    merged_resource_templates = _apply_item_effect_resource_template_bonuses(
        merged_resource_templates,
        item_effect_entries=item_effect_entries,
    )
    return {
        "features": normalized_features,
        "equipment_catalog": normalized_equipment,
        "skills": skills,
        "stats": stats,
        "attacks": _recalculate_definition_attacks(
            derived_definition,
            item_catalog=effective_item_catalog,
        ),
        "spellcasting": derived_spellcasting,
        "resource_templates": _normalize_resource_template_payloads(
            merged_resource_templates
        ),
    }

def _feature_choice_display_title(entry: SystemsEntryRecord) -> str:
    feature_title = str(entry.title or "").strip() or "Feature"
    class_name = str((entry.metadata or {}).get("class_name") or "").strip()
    if class_name and normalize_lookup(class_name) not in normalize_lookup(feature_title):
        return f"{class_name} {feature_title}".strip()
    return feature_title

def _feature_expertise_selected_tool_name(value: Any) -> str:
    cleaned = str(value or "").strip()
    prefix = FEATURE_EXPERTISE_TOOL_VALUE_PREFIX
    if not cleaned or cleaned[: len(prefix)].lower() != prefix:
        return ""
    return _clean_embedded_text(cleaned[len(prefix):]).strip()

def _supported_feature_expertise_blocks(entry: SystemsEntryRecord | None) -> list[dict[str, Any]]:
    if not isinstance(entry, SystemsEntryRecord):
        return []
    metadata = dict(entry.metadata or {})
    expertise_blocks = [dict(block) for block in list(metadata.get("expertise") or []) if isinstance(block, dict)]
    if expertise_blocks:
        return expertise_blocks
    if normalize_lookup(entry.title) != normalize_lookup("Expertise"):
        return []
    class_name = normalize_lookup(metadata.get("class_name"))
    class_source = normalize_lookup(metadata.get("class_source"))
    if class_source == normalize_lookup(PHB_SOURCE_ID) and class_name in {
        normalize_lookup("Bard"),
        normalize_lookup("Rogue"),
    }:
        return [{"anyProficientSkill": 2}]
    return []

def _feat_group_key(instance_key: str, category: str) -> str:
    return f"feat:{instance_key}:{category}"

def _feat_selected_values(
    selected_choices: dict[str, list[str]],
    instance_key: str,
    category: str,
) -> list[str]:
    return list(selected_choices.get(_feat_group_key(instance_key, category)) or [])

def _feature_group_key(instance_key: str, category: str) -> str:
    return f"feature:{instance_key}:{category}"

def _feature_selected_values(
    selected_choices: dict[str, list[str]],
    instance_key: str,
    category: str,
) -> list[str]:
    return list(selected_choices.get(_feature_group_key(instance_key, category)) or [])

def _campaign_item_effect_source_row_ids() -> set[str]:
    return set()


def _item_effect_source_row_ids_from_equipment(
    equipment_catalog: list[dict[str, Any]] | None,
    *,
    item_catalog: dict[str, Any] | None,
) -> set[str]:
    source_row_ids = set(_campaign_item_effect_source_row_ids())
    for item in list(equipment_catalog or []):
        payload = dict(item or {})
        metadata = _resolve_item_support_metadata(payload, item_catalog)
        effect_payload = _item_effect_metadata(metadata)
        for block in list(effect_payload.get("spell_support") or []):
            support_payload = _spell_source_support_payload(block)
            source_row_id = str(support_payload.get("spell_source_row_id") or "").strip()
            if source_row_id:
                source_row_ids.add(source_row_id)
    return source_row_ids

def _apply_item_effect_ability_score_minimums(
    ability_scores: dict[str, int],
    *,
    item_effect_entries: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    adjusted_scores = {
        ability_key: int(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        for ability_key in ABILITY_KEYS
    }
    for entry in list(item_effect_entries or []):
        for ability_key, minimum in dict(entry.get("ability_score_minimums") or {}).items():
            normalized_ability = normalize_lookup(ability_key)
            if normalized_ability not in adjusted_scores:
                continue
            adjusted_scores[normalized_ability] = max(adjusted_scores[normalized_ability], int(minimum or 0))
    return adjusted_scores

def _apply_item_effect_spell_grants(
    spell_payloads: list[dict[str, Any]] | None,
    *,
    item_effect_entries: list[dict[str, Any]] | None = None,
    known_source_row_ids: set[str] | None = None,
    spell_catalog: dict[str, Any],
    current_level: int,
) -> list[dict[str, Any]]:
    spells_by_key: dict[str, dict[str, Any]] = {}
    generated_item_source_row_ids = set(known_source_row_ids or set()) | _campaign_item_effect_source_row_ids()
    for spell_payload in _normalize_spell_payloads(list(spell_payloads or [])):
        source_row_id = str(spell_payload.get("spell_source_row_id") or "").strip()
        if source_row_id in generated_item_source_row_ids or source_row_id.startswith("spell-source:item:"):
            continue
        payload_key = _spell_payload_map_key(spell_payload)
        if payload_key:
            spells_by_key[payload_key] = dict(spell_payload)
    feature_entries = [
        {
            "campaign_option": {
                "spell_support": [dict(block or {}) for block in list(entry.get("spell_support") or []) if isinstance(block, dict)]
            }
        }
        for entry in list(item_effect_entries or [])
        if list(entry.get("spell_support") or [])
    ]
    _apply_spell_support_grants_to_payloads(
        spells_by_key,
        grants=_automatic_spell_support_grants(
            selected_class=None,
            selected_subclass=None,
            target_level=max(int(current_level or 1), 1),
            feature_entries=feature_entries,
        ),
        spell_catalog=spell_catalog,
    )
    return _normalize_spell_payloads(list(spells_by_key.values()))

def _apply_campaign_option_spell_grants(
    spell_payloads: list[dict[str, Any]] | None,
    *,
    option_payloads: list[dict[str, Any]] | None = None,
    spell_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell_payload in _normalize_spell_payloads(list(spell_payloads or [])):
        payload_key = _spell_payload_map_key(spell_payload)
        if payload_key:
            spells_by_key[payload_key] = dict(spell_payload)
    for spell_grant in collect_campaign_option_spell_grants(list(option_payloads or [])):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
        )
    return _normalize_spell_payloads(list(spells_by_key.values()))

def _apply_item_effect_resource_template_bonuses(
    resource_templates: list[dict[str, Any]] | None,
    *,
    item_effect_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    adjusted_templates = [dict(template or {}) for template in list(resource_templates or [])]
    bonus_by_template_id: dict[str, int] = {}
    for entry in list(item_effect_entries or []):
        for bonus_payload in list(entry.get("resource_template_bonuses") or []):
            template_id = str(dict(bonus_payload or {}).get("id") or "").strip()
            if not template_id:
                continue
            bonus_by_template_id[template_id] = int(bonus_by_template_id.get(template_id) or 0) + int(
                dict(bonus_payload or {}).get("bonus") or 0
            )
    if not bonus_by_template_id:
        return adjusted_templates
    for template in adjusted_templates:
        template_id = str(template.get("id") or "").strip()
        bonus = int(bonus_by_template_id.get(template_id) or 0)
        if not template_id or not bonus:
            continue
        max_value = template.get("max")
        if max_value in {"", None}:
            continue
        base_max = int(max_value)
        initial_current = template.get("initial_current")
        base_initial = base_max if initial_current in {"", None} else int(initial_current)
        template["max"] = base_max + bonus
        template["initial_current"] = base_initial + bonus
    return adjusted_templates

def _imported_character_can_prove_plain_unarmored_base(
    equipment_catalog: list[dict[str, Any]],
    *,
    item_catalog: dict[str, Any] | None = None,
) -> bool:
    non_shield_profiles = [
        (item, profile)
        for item, profile in _resolved_armor_profiles(equipment_catalog, item_catalog=item_catalog)
        if not bool(profile.get("is_shield"))
    ]
    if not non_shield_profiles:
        return False
    if any(not bool(item.get("equipped_state_explicit")) for item, _ in non_shield_profiles):
        return False
    return not any(bool(item.get("is_equipped")) for item, _ in non_shield_profiles)

def _character_profile_class_names(
    definition: CharacterDefinition,
    *,
    fallback_class_name: str = "",
) -> list[str]:
    classes = []
    for class_payload in list((definition.profile or {}).get("classes") or []):
        class_name = str(dict(class_payload or {}).get("class_name") or "").strip()
        if class_name:
            classes.append(class_name)
    fallback = str(
        fallback_class_name
        or profile_primary_class_name(definition.profile)
        or (definition.profile or {}).get("class_name")
        or ""
    ).strip()
    if fallback and fallback not in classes:
        classes.append(fallback)
    return classes

def _character_profile_subclass_names(
    definition: CharacterDefinition,
    *,
    fallback_subclass_name: str = "",
) -> list[str]:
    subclasses = []
    for class_payload in list((definition.profile or {}).get("classes") or []):
        subclass_name = str(dict(class_payload or {}).get("subclass_name") or "").strip()
        if subclass_name:
            subclasses.append(subclass_name)
    fallback = str(fallback_subclass_name or _definition_primary_subclass_name(definition) or "").strip()
    if fallback and fallback not in subclasses:
        subclasses.append(fallback)
    return subclasses

def _derive_armor_class_from_character_inputs(
    *,
    ability_scores: dict[str, int],
    equipment_catalog: list[dict[str, Any]],
    features: list[dict[str, Any]] | None,
    class_names: list[str] | None,
    subclass_names: list[str] | None,
    item_catalog: dict[str, Any] | None = None,
    allow_plain_unarmored_base: bool,
) -> int | None:
    dex_modifier = _ability_modifier(int(ability_scores.get("dex", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    con_modifier = _ability_modifier(int(ability_scores.get("con", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    wis_modifier = _ability_modifier(int(ability_scores.get("wis", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    normalized_classes = {normalize_lookup(name) for name in list(class_names or []) if str(name or "").strip()}
    normalized_subclasses = {normalize_lookup(name) for name in list(subclass_names or []) if str(name or "").strip()}
    effect_keys = _extract_character_effect_keys(features)
    armor_dex_cap_bonus_map = _effect_armor_dex_cap_bonus_map(effect_keys)
    structured_ac_bonus = _structured_ac_bonus(features)

    all_items = [dict(item or {}) for item in list(equipment_catalog or [])]
    equipped_items = [item for item in all_items if bool(item.get("is_equipped"))]
    equipped_armor_profiles = _equipped_armor_profiles(equipment_catalog, item_catalog=item_catalog)
    proven_plain_unarmored_base = bool(
        not allow_plain_unarmored_base
        and _imported_character_can_prove_plain_unarmored_base(equipment_catalog, item_catalog=item_catalog)
    )
    armor_items = equipped_items
    resolved_profiles = [
        (item, profile)
        for item in armor_items
        if (profile := _resolve_armor_profile(item, item_catalog)) is not None
    ]

    shield_bonus = max(
        (
            int(profile.get("base_ac") or 0) + int(profile.get("bonus_ac") or 0)
            for _, profile in resolved_profiles
            if bool(profile.get("is_shield"))
        ),
        default=0,
    )
    armor_profiles = [profile for _, profile in resolved_profiles if not bool(profile.get("is_shield"))]
    has_armor = bool(armor_profiles)
    has_shield = shield_bonus > 0

    has_barbarian_unarmored_defense = normalize_lookup("Barbarian") in normalized_classes
    has_monk_unarmored_defense = normalize_lookup("Monk") in normalized_classes
    has_draconic_resilience = normalize_lookup("Draconic Bloodline") in normalized_subclasses or _character_has_named_feature(
        features,
        "Draconic Resilience",
    )
    has_defense_fighting_style = _character_has_named_feature(features, "Defense", "phb-optionalfeature-defense")

    candidate_values: list[int] = []
    for profile in armor_profiles:
        base_ac = int(profile.get("base_ac") or 0)
        bonus_ac = int(profile.get("bonus_ac") or 0)
        armor_category = str(profile.get("armor_category") or "").strip().lower()
        total = base_ac + bonus_ac
        if armor_category == "light":
            total += dex_modifier
        elif armor_category == "medium":
            dex_cap = profile.get("dex_cap")
            total += min(
                dex_modifier,
                int(dex_cap if dex_cap is not None else 2) + int(armor_dex_cap_bonus_map.get("medium") or 0),
            )
        if has_defense_fighting_style:
            total += 1
        total += shield_bonus
        candidate_values.append(total)

    if not has_armor:
        if allow_plain_unarmored_base or proven_plain_unarmored_base:
            candidate_values.append(10 + dex_modifier + shield_bonus)
        if has_barbarian_unarmored_defense:
            candidate_values.append(10 + dex_modifier + con_modifier + shield_bonus)
        if has_draconic_resilience:
            candidate_values.append(13 + dex_modifier + shield_bonus)
        if has_monk_unarmored_defense and not has_shield:
            candidate_values.append(10 + dex_modifier + wis_modifier)

    if not candidate_values:
        return None
    return max(candidate_values) + structured_ac_bonus

def _recalculate_definition_armor_class(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    stats, recoverable_penalties = strip_recoverable_stat_penalties(stats)
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    derived_armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=_ability_scores_from_definition(definition),
        equipment_catalog=list(definition.equipment_catalog or []),
        features=list(definition.features or []),
        class_names=_character_profile_class_names(definition),
        subclass_names=_character_profile_subclass_names(definition),
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=_definition_source_type(definition) == "native_character_builder",
    )
    if derived_armor_class is not None:
        stats["armor_class"] = derived_armor_class
    stats["attack_reminder_state"] = _derive_attack_reminder_state_from_character_inputs(
        features=list(definition.features or []),
        equipment_catalog=list(definition.equipment_catalog or []),
        item_catalog=item_catalog or {},
        ability_scores=_ability_scores_from_definition(definition),
        proficiency_bonus=int(
            dict(definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(_resolve_native_character_level(definition))
        ),
    )
    stats["defensive_state"] = _derive_defensive_state_from_character_inputs(
        equipment_catalog=list(definition.equipment_catalog or []),
        features=list(definition.features or []),
        item_catalog=item_catalog or {},
    )
    stats = apply_stat_adjustments(stats, campaign_option_adjustments)
    stats = apply_recoverable_stat_penalties(stats, recoverable_penalties, adjust_ability_scores=False)
    return apply_manual_stat_adjustments(stats, manual_adjustments)

def _recalculate_definition_attacks(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    effective_item_catalog = dict(item_catalog or _empty_item_catalog())
    equipment_catalog = list(definition.equipment_catalog or [])
    existing_attacks = list(definition.attacks or [])
    feature_only_attacks = _build_level_one_attacks(
        equipment_catalog=[],
        item_catalog=effective_item_catalog,
        ability_scores=_ability_scores_from_definition(definition),
        proficiency_bonus=int(
            (definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(_resolve_native_character_level(definition))
        ),
        weapon_proficiencies=[
            str(value).strip()
            for value in list((definition.proficiencies or {}).get("weapons") or [])
            if str(value).strip()
        ],
        selected_choices={},
        features=list(definition.features or []),
    )
    if not equipment_catalog:
        return _normalize_attack_payloads([*existing_attacks, *feature_only_attacks])
    has_structured_equipment = any(
        bool(dict(item.get("systems_ref") or {}))
        or bool(_normalize_page_ref_payload(item.get("page_ref")))
        or bool(item.get("is_equipped", False))
        or bool(item.get("is_attuned", False))
        for item in equipment_catalog
    )
    if not has_structured_equipment:
        return _normalize_attack_payloads([*existing_attacks, *feature_only_attacks])
    recalculated_attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=effective_item_catalog,
        ability_scores=_ability_scores_from_definition(definition),
        proficiency_bonus=int(
            (definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(_resolve_native_character_level(definition))
        ),
        weapon_proficiencies=[
            str(value).strip()
            for value in list((definition.proficiencies or {}).get("weapons") or [])
            if str(value).strip()
        ],
        selected_choices={},
        features=list(definition.features or []),
    )
    if not recalculated_attacks and existing_attacks:
        return _normalize_attack_payloads(existing_attacks)
    if existing_attacks and not any(
        _attack_matches_equipment_catalog(
            dict(attack or {}),
            equipment_catalog=equipment_catalog,
        )
        for attack in existing_attacks
    ) and not all(
        _is_equipment_independent_attack_payload(
            dict(attack or {}),
            feature_only_attacks=feature_only_attacks,
        )
        for attack in existing_attacks
    ):
        return _normalize_attack_payloads(existing_attacks)
    return _normalize_attack_payloads(
        _merge_recalculated_attack_overrides(
            recalculated_attacks,
            existing_attacks,
            equipment_catalog=equipment_catalog,
        )
    )

def _multiclass_slot_contribution_for_row(level: int, caster_progression: str) -> int:
    clean_level = max(int(level or 0), 0)
    clean_progression = _normalize_caster_progression(caster_progression)
    if clean_level <= 0:
        return 0
    if clean_progression == "full":
        return clean_level
    if clean_progression == "1/2":
        return clean_level // 2
    if clean_progression == "1/3":
        return clean_level // 3
    if clean_progression == "artificer":
        return (clean_level + 1) // 2
    return 0

def _shared_slot_progression_for_caster_level(total_caster_level: int) -> list[dict[str, Any]]:
    clean_level = max(int(total_caster_level or 0), 0)
    if clean_level <= 0:
        return []
    slot_rows = list(
        _class_spell_progression(MULTICLASS_SHARED_SLOT_REFERENCE_CLASS).get("slot_progression") or []
    )
    if 1 <= clean_level <= len(slot_rows):
        return [dict(slot or {}) for slot in list(slot_rows[clean_level - 1] or [])]
    return []

def _spellcasting_ability_name_for_class(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
) -> str:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    ability_key = str(progression.get("spellcasting_ability") or "").strip()
    if ability_key in ABILITY_LABELS:
        return ABILITY_LABELS[ability_key]
    return SPELLCASTING_ABILITY_BY_CLASS.get(class_name, "")

def _spell_list_class_name_for_class(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
) -> str:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    return str(progression.get("spell_list_class_name") or class_name or "").strip()

def _spell_progression_value(
    class_name: str,
    key: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
) -> int:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    values = list(progression.get(key) or [])
    if 1 <= target_level <= len(values):
        return max(int(values[target_level - 1] or 0), 0)
    return 0

def _spell_slot_progression_for_class_level(
    class_name: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
) -> list[dict[str, Any]]:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    slot_rows = list(progression.get("slot_progression") or [])
    if 1 <= target_level <= len(slot_rows):
        return [dict(slot) for slot in list(slot_rows[target_level - 1] or [])]
    if target_level == 1:
        return list(LEVEL_ONE_SPELL_SLOTS_BY_CLASS.get(class_name, []))
    return []

def _prepared_spell_count_for_level(
    class_name: str,
    ability_scores: dict[str, int],
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
) -> int:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    prepared_progression = list(progression.get("prepared_spells_progression") or [])
    if 1 <= target_level <= len(prepared_progression):
        return max(int(prepared_progression[target_level - 1] or 0), 0)
    formula = str(progression.get("prepared_spells") or "").strip()
    if formula:
        return _evaluate_prepared_spell_formula(formula, ability_scores, target_level)
    return 0

def _evaluate_prepared_spell_formula(
    formula: str,
    ability_scores: dict[str, int],
    target_level: int,
) -> int:
    clean_formula = str(formula or "").strip()
    match = re.fullmatch(r"<\$level\$>(?:\s*/\s*(\d+))?\s*\+\s*<\$([a-z]+)_mod\$>", clean_formula)
    if match is None:
        match = re.fullmatch(r"level(?:\s*/\s*(\d+))?\s*\+\s*([a-z]+)", clean_formula, flags=re.IGNORECASE)
    if match is None:
        return 0
    divisor_text, ability_key = match.groups()
    clean_ability_key = _prepared_spell_formula_ability_key(ability_key)
    if clean_ability_key not in ABILITY_KEYS:
        return 0
    level_value = int(target_level or 0)
    if divisor_text:
        divisor = max(int(divisor_text or 1), 1)
        level_value //= divisor
    modifier = _ability_modifier(ability_scores.get(clean_ability_key, DEFAULT_ABILITY_SCORE))
    return max(level_value + modifier, 1)

def _prepared_spell_formula_ability_key(raw_ability_key: str) -> str:
    clean_key = normalize_lookup(str(raw_ability_key or "").strip())
    if clean_key in ABILITY_KEYS:
        return clean_key
    return next(
        (
            ability_key
            for ability_key, label in ABILITY_LABELS.items()
            if clean_key == normalize_lookup(label)
        ),
        "",
    )

def _normalize_skill_proficiency_level(value: Any) -> str:
    if value in (None, "", False):
        return "none"
    normalized = normalize_lookup(str(value))
    if normalized == "expertise":
        return "expertise"
    if normalized in {"halfproficient", "halfproficiency"}:
        return "half_proficient"
    if normalized in {"proficient", "proficiency"}:
        return "proficient"
    return "none"

def _skill_proficiency_level_rank(value: Any) -> int:
    return int(SKILL_PROFICIENCY_LEVEL_RANKS.get(_normalize_skill_proficiency_level(value), 0))

def _max_skill_proficiency_level(*levels: Any) -> str:
    best_level = "none"
    best_rank = -1
    for level in levels:
        normalized = _normalize_skill_proficiency_level(level)
        rank = _skill_proficiency_level_rank(normalized)
        if rank > best_rank:
            best_level = normalized
            best_rank = rank
    return best_level

def _skill_proficiency_level_from_bonus(
    skill_name: Any,
    *,
    bonus: Any,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> str:
    normalized_skill = normalize_lookup(skill_name)
    ability_key = SKILL_ABILITY_KEYS.get(normalized_skill)
    if ability_key is None:
        return "none"
    try:
        clean_bonus = int(bonus)
    except (TypeError, ValueError):
        return "none"
    modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
    delta = clean_bonus - modifier
    if proficiency_bonus > 0 and delta >= proficiency_bonus * 2:
        return "expertise"
    if proficiency_bonus > 0 and delta >= proficiency_bonus:
        return "proficient"
    if proficiency_bonus > 1 and delta == (proficiency_bonus // 2):
        return "half_proficient"
    return "none"

def _skill_proficiency_levels_from_rows(
    skills: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> dict[str, str]:
    levels: dict[str, str] = {}
    for row in list(skills or []):
        skill_name = str(row.get("name") or "").strip()
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        explicit_level = _normalize_skill_proficiency_level(row.get("proficiency_level"))
        inferred_level = _skill_proficiency_level_from_bonus(
            skill_name,
            bonus=row.get("bonus"),
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
        )
        levels[normalized_skill] = _max_skill_proficiency_level(
            levels.get(normalized_skill),
            explicit_level,
            inferred_level,
        )
    return levels

def _skill_proficiency_levels_from_names(
    proficient_skills: list[str],
) -> dict[str, str]:
    levels: dict[str, str] = {}
    for skill in list(proficient_skills or []):
        normalized_skill = normalize_lookup(skill)
        if normalized_skill not in SKILL_LABELS:
            continue
        levels[normalized_skill] = _max_skill_proficiency_level(
            levels.get(normalized_skill),
            "proficient",
        )
    return levels

def _build_skills_payload_from_levels(
    ability_scores: dict[str, int],
    proficiency_levels: dict[str, str],
    proficiency_bonus: int,
    *,
    skill_bonus_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    resolved_skill_bonus_map = dict(skill_bonus_map or {})
    for normalized_skill, label in SKILL_LABELS.items():
        ability_key = SKILL_ABILITY_KEYS[normalized_skill]
        modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
        proficiency_level = _normalize_skill_proficiency_level(proficiency_levels.get(normalized_skill))
        if proficiency_level == "expertise":
            proficiency_contribution = proficiency_bonus * 2
        elif proficiency_level == "proficient":
            proficiency_contribution = proficiency_bonus
        elif proficiency_level == "half_proficient":
            proficiency_contribution = proficiency_bonus // 2
        else:
            proficiency_contribution = 0
        rows.append(
            {
                "name": label,
                "bonus": modifier + proficiency_contribution + int(resolved_skill_bonus_map.get(normalized_skill) or 0),
                "proficiency_level": proficiency_level,
            }
        )
    return rows

def _build_skills_payload(
    ability_scores: dict[str, int],
    proficient_skills: list[str],
    proficiency_bonus: int,
    *,
    feat_selections: list[dict[str, Any]] | None = None,
    feature_selections: list[dict[str, Any]] | None = None,
    selected_choices: dict[str, list[str]] | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    proficiency_levels = _skill_proficiency_levels_from_names(proficient_skills)
    if feat_selections:
        proficiency_levels = _apply_feat_expertise_to_skill_proficiency_levels(
            proficiency_levels,
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            strict=strict,
        )
    if feature_selections:
        proficiency_levels = _apply_feature_expertise_to_skill_proficiency_levels(
            proficiency_levels,
            feature_selections=feature_selections,
            selected_choices=selected_choices,
            strict=strict,
        )
    return _build_skills_payload_from_levels(
        ability_scores,
        proficiency_levels,
        proficiency_bonus,
    )

def _build_level_one_stats(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord,
    ability_scores: dict[str, int],
    skills: list[dict[str, Any]],
    proficiency_bonus: int,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    current_level: int,
    equipment_catalog: list[dict[str, Any]] | None = None,
    features: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_metadata = dict(selected_class.metadata or {})
    hit_die_faces = int((class_metadata.get("hit_die") or {}).get("faces") or 0)
    con_modifier = _ability_modifier(ability_scores["con"])
    skill_lookup = {normalize_lookup(skill["name"]): skill for skill in skills}
    passive_perception = 10 + int((skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_insight = 10 + int((skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_investigation = 10 + int((skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"]))
    save_proficiencies = set(
        _class_save_proficiencies(selected_class)
        + _extract_feat_saving_throw_proficiencies(feat_selections, selected_choices)
    )
    effect_keys = _extract_character_effect_keys(features or [])
    save_bonus_map = _effect_save_bonus_map(effect_keys)
    base_speed = _extract_speed_label(selected_species)
    armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=equipment_catalog or [],
        features=features or [],
        class_names=[selected_class.title],
        subclass_names=[selected_subclass.title] if selected_subclass is not None else [],
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=True,
    )

    stats = {
        "max_hp": max(hit_die_faces + con_modifier, 1)
        + _feat_hit_point_bonus(feat_selections, current_level=current_level),
        "armor_class": armor_class,
        "initiative_bonus": _ability_modifier(ability_scores["dex"])
        + _feat_initiative_bonus(feat_selections),
        "speed": _apply_speed_bonus_to_label(base_speed, _feat_speed_bonus(feat_selections)),
        "proficiency_bonus": proficiency_bonus,
        "passive_perception": passive_perception + _feat_passive_bonus(feat_selections, skill_name="Perception"),
        "passive_insight": passive_insight,
        "passive_investigation": passive_investigation + _feat_passive_bonus(feat_selections, skill_name="Investigation"),
        "ability_scores": {
            ability_key: {
                "score": score,
                "modifier": _ability_modifier(score),
                "save_bonus": _ability_modifier(score)
                + (proficiency_bonus if ability_key in save_proficiencies else 0)
                + int(save_bonus_map.get(ability_key) or 0),
            }
            for ability_key, score in ability_scores.items()
        },
        "attack_reminder_state": _derive_attack_reminder_state_from_character_inputs(
            features=features or [],
            equipment_catalog=equipment_catalog or [],
            item_catalog=item_catalog or {},
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
        ),
        "defensive_state": _derive_defensive_state_from_character_inputs(
            equipment_catalog=equipment_catalog or [],
            features=features or [],
            item_catalog=item_catalog or {},
        ),
    }
    stats.update(
        _derive_carrying_capacity_stats(
            strength_score=ability_scores["str"],
            size_label=_extract_size_label(selected_species),
            effect_keys=effect_keys,
        )
    )
    return apply_stat_adjustments(
        stats,
        collect_campaign_option_stat_adjustments(list(campaign_option_payloads or [])),
    )

def _ability_scores_from_definition(
    definition: CharacterDefinition,
    *,
    include_recoverable_penalties: bool = True,
) -> dict[str, int]:
    ability_scores = dict((definition.stats or {}).get("ability_scores") or {})
    resolved_scores = {
        ability_key: int(
            dict(
                ability_scores.get(ability_key)
                or ability_scores.get(ABILITY_LABELS.get(ability_key, "").lower())
                or {}
            ).get("score")
            or DEFAULT_ABILITY_SCORE
        )
        for ability_key in ABILITY_KEYS
    }
    if include_recoverable_penalties:
        return resolved_scores
    return restore_recoverable_ability_score_penalties(
        resolved_scores,
        (definition.stats or {}).get("recoverable_penalties"),
    )

def _build_leveled_stats(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    ability_scores: dict[str, int],
    skills: list[dict[str, Any]],
    proficiency_bonus: int,
    hp_gain: int,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    current_level: int,
    equipment_catalog: list[dict[str, Any]] | None = None,
    features: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
    resulting_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(current_definition.stats or {}))
    stats, recoverable_penalties = strip_recoverable_stat_penalties(stats)
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(current_definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    skill_lookup = {normalize_lookup(skill["name"]): skill for skill in skills}
    save_proficiencies = _infer_definition_save_proficiencies(
        current_definition,
        ability_scores=_ability_scores_from_definition(current_definition),
        proficiency_bonus=int(
            (current_definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(_resolve_native_character_level(current_definition))
        ),
        selected_class=selected_class,
    )
    save_proficiencies.update(_extract_feat_saving_throw_proficiencies(feat_selections, selected_choices))
    effect_keys = _extract_character_effect_keys(features or list(current_definition.features or []))
    save_bonus_map = _effect_save_bonus_map(effect_keys)
    feat_hp_bonus = _feat_hit_point_bonus(feat_selections, current_level=current_level)
    stats["max_hp"] = max(int(stats.get("max_hp") or 0) + hp_gain + feat_hp_bonus, 1)
    stats["proficiency_bonus"] = proficiency_bonus
    stats["passive_perception"] = 10 + int(
        (skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
    ) + _feat_passive_bonus(feat_selections, skill_name="Perception")
    stats["passive_insight"] = 10 + int(
        (skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
    )
    stats["passive_investigation"] = 10 + int(
        (skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"])
    ) + _feat_passive_bonus(feat_selections, skill_name="Investigation")
    preview_profile_definition = CharacterDefinition.from_dict(
        {
            **current_definition.to_dict(),
            "profile": sync_profile_class_summary(resulting_profile or dict(current_definition.profile or {})),
        }
    )
    stats["armor_class"] = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=equipment_catalog or list(current_definition.equipment_catalog or []),
        features=features or list(current_definition.features or []),
        class_names=_character_profile_class_names(
            preview_profile_definition,
            fallback_class_name=selected_class.title,
        ),
        subclass_names=_character_profile_subclass_names(
            preview_profile_definition,
            fallback_subclass_name=selected_subclass.title if selected_subclass is not None else "",
        ),
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=True,
    )
    stats["attack_reminder_state"] = _derive_attack_reminder_state_from_character_inputs(
        features=features or list(current_definition.features or []),
        equipment_catalog=equipment_catalog or list(current_definition.equipment_catalog or []),
        item_catalog=item_catalog or {},
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    stats["defensive_state"] = _derive_defensive_state_from_character_inputs(
        equipment_catalog=equipment_catalog or list(current_definition.equipment_catalog or []),
        features=features or list(current_definition.features or []),
        item_catalog=item_catalog or {},
    )
    stats["initiative_bonus"] = _ability_modifier(ability_scores["dex"]) + _feat_initiative_bonus(feat_selections)
    stats["speed"] = _apply_speed_bonus_to_label(str(stats.get("speed") or ""), _feat_speed_bonus(feat_selections))
    stats.update(
        _derive_carrying_capacity_stats(
            strength_score=ability_scores["str"],
            size_label=_definition_size_label(
                current_definition,
                profile=resulting_profile or dict(current_definition.profile or {}),
            ),
            effect_keys=effect_keys,
        )
    )
    stats["ability_scores"] = {
        ability_key: {
            "score": score,
            "modifier": _ability_modifier(score),
            "save_bonus": _ability_modifier(score)
            + (proficiency_bonus if ability_key in save_proficiencies else 0)
            + int(save_bonus_map.get(ability_key) or 0),
        }
        for ability_key, score in ability_scores.items()
    }
    combined_campaign_option_adjustments = dict(campaign_option_adjustments)
    for key, value in collect_campaign_option_stat_adjustments(selected_campaign_option_payloads or []).items():
        combined_campaign_option_adjustments[key] = int(combined_campaign_option_adjustments.get(key) or 0) + int(value)
    stats = apply_stat_adjustments(stats, combined_campaign_option_adjustments)
    stats = apply_recoverable_stat_penalties(stats, recoverable_penalties, adjust_ability_scores=False)
    return apply_manual_stat_adjustments(stats, manual_adjustments)

def _is_equipment_independent_attack_payload(
    attack_payload: dict[str, Any],
    *,
    feature_only_attacks: list[dict[str, Any]] | None = None,
) -> bool:
    payload = dict(attack_payload or {})
    if _normalize_attack_equipment_refs(
        payload.get("equipment_refs"),
        fallback=payload.get("equipment_ref"),
    ):
        return False
    if _normalize_explicit_link_identity(
        systems_ref=dict(payload.get("systems_ref") or {}),
        page_ref=_normalize_page_ref_payload(payload.get("page_ref")),
    ):
        return False

    mode_key = _infer_attack_mode_key_from_payload(payload)
    if mode_key and not any(
        component.startswith("feat:")
        for component in _attack_mode_components(mode_key)
    ):
        return False

    attack_name_candidates = set(_merge_name_candidates(payload.get("name")))
    if normalize_lookup("Unarmed Strike") in attack_name_candidates:
        return True

    for feature_attack in list(feature_only_attacks or []):
        feature_payload = dict(feature_attack or {})
        feature_name_candidates = set(_merge_name_candidates(feature_payload.get("name")))
        if attack_name_candidates and feature_name_candidates and attack_name_candidates.intersection(
            feature_name_candidates
        ):
            return True
    return False

def _class_save_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    return [
        ability_key
        for ability_key in list(selected_class.metadata.get("proficiency") or [])
        if ability_key in ABILITY_KEYS
    ]

def _extract_size_label(entry: SystemsEntryRecord | None) -> str:
    if entry is None:
        return ""
    size_values = list(dict(entry.metadata or {}).get("size") or [])
    if not size_values:
        return ""
    return SIZE_LABELS.get(str(size_values[0] or "").strip().upper(), str(size_values[0] or "").strip())

def _normalize_size_label(value: Any) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    if clean_value.upper() in SIZE_LABELS:
        return SIZE_LABELS[clean_value.upper()]
    normalized_value = normalize_lookup(clean_value)
    for label in SIZE_LABELS.values():
        if normalize_lookup(label) == normalized_value:
            return label
    return clean_value

def _definition_size_label(
    definition: CharacterDefinition,
    *,
    selected_species: SystemsEntryRecord | None = None,
    profile: dict[str, Any] | None = None,
) -> str:
    species_size = _extract_size_label(selected_species)
    if species_size:
        return species_size
    profile_payload = dict(profile or definition.profile or {})
    return _normalize_size_label(profile_payload.get("size"))

def _extract_speed_label(entry: SystemsEntryRecord | None) -> str:
    if entry is None:
        return ""
    raw_speed = dict(entry.metadata or {}).get("speed")
    if isinstance(raw_speed, (int, float)):
        return f"{int(raw_speed)} ft."
    return str(raw_speed or "").strip()

def _size_carrying_capacity_multiplier(size_label: Any) -> float:
    normalized_size = normalize_lookup(_normalize_size_label(size_label))
    return float(SIZE_CARRYING_CAPACITY_MULTIPLIERS.get(normalized_size) or 1.0)

def _normalize_weight_limit_value(value: float) -> int | float:
    rounded_value = round(float(value), 1)
    if rounded_value.is_integer():
        return int(rounded_value)
    return rounded_value

def _derive_carrying_capacity_stats(
    *,
    strength_score: int,
    size_label: Any,
    effect_keys: list[str] | None = None,
) -> dict[str, int | float]:
    clean_strength_score = max(int(strength_score or 0), 0)
    if clean_strength_score <= 0:
        return {}
    carrying_capacity = clean_strength_score * 15
    carrying_capacity *= _size_carrying_capacity_multiplier(size_label)
    carrying_capacity *= _effect_carrying_capacity_multiplier(list(effect_keys or []))
    if carrying_capacity <= 0:
        return {}
    return {
        "carrying_capacity": _normalize_weight_limit_value(carrying_capacity),
        "push_drag_lift": _normalize_weight_limit_value(carrying_capacity * 2),
    }

def _skill_label(value: str) -> str:
    return SKILL_LABELS.get(normalize_lookup(value), _humanize_words(value))

def _clean_embedded_text(value: str) -> str:
    rendered = str(value or "").strip()
    while True:
        updated = INLINE_TAG_PATTERN.sub(_replace_inline_tag, rendered)
        if updated == rendered:
            break
        rendered = updated
    return re.sub(r"\s+", " ", rendered).strip(" ,;")

def _replace_inline_tag(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    parts = [part.strip() for part in body.split("|")]
    if len(parts) >= 3 and parts[2]:
        return parts[2]
    if parts:
        return parts[0]
    return body

def _apply_feat_ability_score_bonuses(
    base_scores: dict[str, int],
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    strict: bool,
) -> dict[str, int]:
    updated_scores = dict(base_scores)
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        chosen_values = _feat_selected_values(selected_choices, instance_key, "ability")
        chosen_index = 0
        for block in list(metadata.get("ability") or []):
            if not isinstance(block, dict):
                continue
            for ability_key in ABILITY_KEYS:
                raw_bonus = block.get(ability_key)
                if isinstance(raw_bonus, (int, float)) and int(raw_bonus):
                    updated_scores[ability_key] = min(
                        int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + int(raw_bonus),
                        20,
                    )
            choose = dict(block.get("choose") or {})
            options = [str(option) for option in list(choose.get("from") or []) if str(option) in ABILITY_KEYS]
            count = max(int(choose.get("count") or 1), 0)
            amount = max(int(choose.get("amount") or 1), 1)
            if not options or count <= 0:
                continue
            selected_values = chosen_values[chosen_index : chosen_index + count]
            chosen_index += count
            if len(selected_values) < count:
                if strict:
                    raise _character_build_error(f"Choose the ability increase for {feat_entry.title}.")
                continue
            for ability_key in selected_values:
                if ability_key not in options:
                    if strict:
                        raise _character_build_error(f"Choose a valid ability increase for {feat_entry.title}.")
                    continue
                updated_scores[ability_key] = min(
                    int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + amount,
                    20,
                )
    return updated_scores

def _strip_feat_ability_score_bonuses(
    current_scores: dict[str, int],
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> dict[str, int]:
    updated_scores = {
        ability_key: int(current_scores.get(ability_key, DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        for ability_key in ABILITY_KEYS
    }
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        chosen_values = _feat_selected_values(selected_choices, instance_key, "ability")
        chosen_index = 0
        for block in list(metadata.get("ability") or []):
            if not isinstance(block, dict):
                continue
            for ability_key in ABILITY_KEYS:
                raw_bonus = block.get(ability_key)
                if isinstance(raw_bonus, (int, float)) and int(raw_bonus):
                    updated_scores[ability_key] = max(
                        int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) - int(raw_bonus),
                        1,
                    )
            choose = dict(block.get("choose") or {})
            options = [str(option) for option in list(choose.get("from") or []) if str(option) in ABILITY_KEYS]
            count = max(int(choose.get("count") or 1), 0)
            amount = max(int(choose.get("amount") or 1), 1)
            if not options or count <= 0:
                continue
            selected_values = chosen_values[chosen_index : chosen_index + count]
            chosen_index += count
            for ability_key in selected_values:
                if ability_key not in options:
                    continue
                updated_scores[ability_key] = max(
                    int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) - amount,
                    1,
                )
    return updated_scores

def _extract_feat_skill_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("skill_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block or int(block.get("any") or 0) > 0:
                results.extend(_skill_label(value) for value in _feat_selected_values(selected_choices, instance_key, "skills"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_skill_label(key))
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("skill:"):
                results.append(_skill_label(str(value).split(":", 1)[1]))
    return _dedupe_preserve_order(results)

def _apply_skill_expertise_level(
    proficiency_levels: dict[str, str],
    *,
    skill_name: Any,
    feat_title: str,
    strict: bool,
) -> None:
    normalized_skill = normalize_lookup(skill_name)
    if normalized_skill not in SKILL_LABELS:
        if strict:
            raise _character_build_error(f"Choose a valid expertise skill for {feat_title}.")
        return
    current_level = _normalize_skill_proficiency_level(proficiency_levels.get(normalized_skill))
    if current_level == "expertise":
        if strict:
            raise _character_build_error(f"{feat_title} requires choosing a skill that does not already have expertise.")
        return
    if current_level != "proficient":
        if strict:
            raise _character_build_error(f"{feat_title} requires choosing a skill that already has proficiency.")
        return
    proficiency_levels[normalized_skill] = "expertise"

def _apply_feat_expertise_to_skill_proficiency_levels(
    proficiency_levels: dict[str, str],
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]] | None = None,
    strict: bool = False,
) -> dict[str, str]:
    updated_levels = {
        normalized_skill: _normalize_skill_proficiency_level(level)
        for raw_skill, level in dict(proficiency_levels or {}).items()
        if (normalized_skill := normalize_lookup(raw_skill)) in SKILL_LABELS
    }
    choice_map = dict(selected_choices or {})
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        metadata = dict(feat_entry.metadata or {})
        expertise_blocks = [dict(block) for block in list(metadata.get("expertise") or []) if isinstance(block, dict)]
        if not expertise_blocks:
            continue
        feat_title = str(feat_entry.title or "").strip() or "This feat"
        for block in expertise_blocks:
            for key, value in block.items():
                if key == "anyProficientSkill" or value is not True:
                    continue
                _apply_skill_expertise_level(
                    updated_levels,
                    skill_name=key,
                    feat_title=feat_title,
                    strict=strict,
                )
        any_proficient_skill_count = sum(int(block.get("anyProficientSkill") or 0) for block in expertise_blocks)
        if any_proficient_skill_count <= 0:
            continue
        instance_key = str(selection.get("instance_key") or "").strip()
        if not instance_key:
            if strict:
                raise _character_build_error(f"{feat_title} is missing the expertise choice metadata needed to save.")
            continue
        selected_expertise_skills = _feat_selected_values(choice_map, instance_key, "expertise")
        for selected_skill in selected_expertise_skills[:any_proficient_skill_count]:
            _apply_skill_expertise_level(
                updated_levels,
                skill_name=selected_skill,
                feat_title=feat_title,
                strict=strict,
            )
    return updated_levels

def _apply_feature_expertise_to_skill_proficiency_levels(
    proficiency_levels: dict[str, str],
    *,
    feature_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]] | None = None,
    strict: bool = False,
) -> dict[str, str]:
    updated_levels = {
        normalized_skill: _normalize_skill_proficiency_level(level)
        for raw_skill, level in dict(proficiency_levels or {}).items()
        if (normalized_skill := normalize_lookup(raw_skill)) in SKILL_LABELS
    }
    choice_map = dict(selected_choices or {})
    for selection in feature_selections:
        feature_entry = selection.get("entry")
        if not isinstance(feature_entry, SystemsEntryRecord):
            continue
        expertise_blocks = _supported_feature_expertise_blocks(feature_entry)
        if not expertise_blocks:
            continue
        feature_title = _feature_choice_display_title(feature_entry)
        instance_key = str(selection.get("instance_key") or "").strip()
        for block in expertise_blocks:
            for skill_name, value in dict(block).items():
                if skill_name == "anyProficientSkill":
                    continue
                if normalize_lookup(skill_name) == normalize_lookup(THIEVES_TOOLS_PROFICIENCY):
                    continue
                if value is True:
                    _apply_skill_expertise_level(
                        updated_levels,
                        skill_name=skill_name,
                        feat_title=feature_title,
                        strict=strict,
                    )
        any_proficient_skill_count = sum(int(block.get("anyProficientSkill") or 0) for block in expertise_blocks)
        if any_proficient_skill_count <= 0:
            continue
        if not instance_key:
            if strict:
                raise _character_build_error(f"{feature_title} is missing the expertise choice metadata needed to save.")
            continue
        selected_expertise_skills = _feature_selected_values(choice_map, instance_key, "expertise")
        for selected_skill in selected_expertise_skills[:any_proficient_skill_count]:
            if _feature_expertise_selected_tool_name(selected_skill):
                continue
            _apply_skill_expertise_level(
                updated_levels,
                skill_name=selected_skill,
                feat_title=feature_title,
                strict=strict,
            )
    return updated_levels

def _extract_feat_expertise_skills(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]] | None = None,
) -> list[str]:
    results: list[str] = []
    choice_map = dict(selected_choices or {})
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("expertise") or []):
            if not isinstance(block, dict):
                continue
            for key, value in block.items():
                if key == "anyProficientSkill" or value is not True:
                    continue
                normalized_skill = normalize_lookup(key)
                if normalized_skill in SKILL_LABELS:
                    results.append(SKILL_LABELS[normalized_skill])
        instance_key = str(selection.get("instance_key") or "").strip()
        if not instance_key:
            continue
        for selected_skill in _feat_selected_values(choice_map, instance_key, "expertise"):
            normalized_skill = normalize_lookup(selected_skill)
            if normalized_skill in SKILL_LABELS:
                results.append(SKILL_LABELS[normalized_skill])
    return _dedupe_preserve_order(results)

def _extract_feat_saving_throw_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        if normalize_lookup(feat_entry.title) == normalize_lookup("Resilient"):
            results.extend(
                ability_key
                for ability_key in _feat_selected_values(selected_choices, instance_key, "ability")
                if ability_key in ABILITY_KEYS
            )
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("saving_throw_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block:
                results.extend(
                    ability_key
                    for ability_key in _feat_selected_values(selected_choices, instance_key, "saving_throws")
                    if ability_key in ABILITY_KEYS
                )
                continue
            for key, value in block.items():
                if value is True and key in ABILITY_KEYS:
                    results.append(key)
    return _dedupe_preserve_order(results)

def _feat_initiative_bonus(feat_selections: list[dict[str, Any]]) -> int:
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Alert"):
            return 5
    return 0

def _feat_speed_bonus(feat_selections: list[dict[str, Any]]) -> int:
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Mobile"):
            bonus += 10
    return bonus

def _apply_speed_bonus_to_label(speed_label: str, bonus: int) -> str:
    clean_label = str(speed_label or "").strip()
    if not clean_label or not bonus:
        return clean_label
    match = re.search(r"(\d+)", clean_label)
    if not match:
        return clean_label
    return clean_label[: match.start(1)] + str(int(match.group(1)) + int(bonus)) + clean_label[match.end(1) :]

def _feat_passive_bonus(
    feat_selections: list[dict[str, Any]],
    *,
    skill_name: str,
) -> int:
    normalized_skill = normalize_lookup(skill_name)
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        normalized_title = normalize_lookup(feat_entry.title)
        if normalized_title == normalize_lookup("Observant") and normalized_skill in {"perception", "investigation"}:
            bonus += 5
    return bonus

def _feat_hit_point_bonus(
    feat_selections: list[dict[str, Any]],
    *,
    current_level: int,
) -> int:
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Tough"):
            bonus += max(int(current_level or 0), 0) * 2
    return bonus
