from __future__ import annotations

from copy import deepcopy
from typing import Any

from .auth_store import isoformat, utcnow
from .character_builder_constants import *  # noqa: F403
from .character_builder_foundation import (
    _choice_option,
    _entry_campaign_option,
    _entry_option,
    _entry_option_label,
    _entry_page_ref,
    _entry_selection_value,
    _evaluate_shared_slot_multiclass_support,
    _native_source_matrix_support_policy,
    _profile_link_subject,
    _resolve_native_character_level,
    _resolve_profile_entry,
    _resolve_profile_entry_match,
    _resolve_selected_entry,
    _sanitize_entry_selection_value,
    _spellcasting_mode_for_class,
    _supports_native_class_entry,
)
from .character_builder_equipment import *  # noqa: F403
from .character_builder_spells import *  # noqa: F403
from .character_builder_derivation import (
    _ability_scores_from_definition,
    _apply_feat_ability_score_bonuses,
    _apply_feat_expertise_to_skill_proficiency_levels,
    _apply_feature_expertise_to_skill_proficiency_levels,
    _build_leveled_stats,
    _build_skills_payload_from_levels,
    _definition_base_stats_without_adjustments,
    _extract_feat_skill_proficiencies,
    _feat_hit_point_bonus,
    _max_skill_proficiency_level,
    _skill_proficiency_levels_from_rows,
    _spell_list_class_name_for_class,
)
from .character_campaign_options import collect_campaign_option_proficiency_grants
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_profile import (
    ensure_profile_class_rows,
    profile_class_level_text,
    profile_primary_class_ref,
    profile_primary_subclass_name,
    profile_primary_subclass_ref,
    sync_profile_class_summary,
)
from .repository import normalize_lookup
from .systems_models import SystemsEntryRecord


__all__ = [
    'CharacterBuildError',
    'supports_native_level_up',
    'native_level_up_readiness',
    '_character_source_type',
    '_native_character_subclass_name',
    '_native_progression_payload',
    '_native_progression_hp_baseline',
    '_ensure_native_progression_hp_baseline',
    '_seed_source_hp_baseline_from_definition',
    '_with_native_progression_event',
    '_build_imported_spell_repair_rows',
    '_spell_mark_is_valid_for_mode',
    '_canonical_automatic_prepared_spell_mark',
    '_automatic_prepared_feature_entries',
    '_automatic_prepared_spell_lookup_keys_for_row',
    '_apply_automatic_prepared_spell_flags',
    '_imported_spell_mark_options_for_rows',
    '_imported_spell_candidate_row_ids',
    '_imported_spell_mark_options',
    '_class_row_level_text',
    '_sync_profile_with_class_rows',
    '_build_resulting_level_up_profile',
    '_build_multiclass_add_choice_sections',
    'build_native_level_up_context',
    'build_native_level_up_character_definition',
    'build_imported_progression_repair_context',
    'apply_imported_progression_repairs',
]


_BUILDER_PROXY_NAMES = (
    '_build_common_builder_static_bundle',
    '_class_progression_for_builder',
    '_subclass_progression_for_builder',
    '_list_supported_class_entries',
    '_list_shared_slot_multiclass_class_entries',
    '_list_shared_slot_multiclass_subclass_options',
    '_list_campaign_enabled_entries',
    '_list_subclass_options',
    '_build_mixed_character_options',
    '_effective_spell_catalog_for_definition',
    '_native_character_class_name',
    '_native_level_up_support_error',
    '_normalize_level_up_values',
    '_sanitize_choice_section_values',
    '_level_up_field_live_preview_metadata',
    '_annotate_builder_choice_sections',
    '_stabilize_choice_section_values',
    '_class_requires_subclass_at_level',
    '_build_level_up_choice_sections',
    '_resolve_level_up_ability_score_choices',
    '_progression_feature_choice_selections',
    '_build_item_catalog',
    '_resolve_level_up_feat_selections',
    '_campaign_option_payloads_from_feat_selections',
    '_campaign_option_payloads_from_feature_entries',
    '_dedupe_spell_feature_entries',
    '_spell_feature_entries_from_progressions',
    '_resolve_builder_choices',
    '_apply_feature_expertise_to_tool_proficiencies',
    '_extract_feat_language_proficiencies',
    '_extract_feat_tool_proficiencies',
    '_extract_feat_armor_proficiencies',
    '_extract_feat_weapon_proficiencies',
    '_collect_feat_optionalfeature_entries',
    '_collect_progression_feature_entries_for_level',
    '_build_feature_payloads',
    '_proficiency_bonus_for_level',
    '_parse_level_up_hit_point_gain',
    '_build_leveled_source',
    '_build_leveled_import_metadata',
    '_merge_feature_payloads',
    '_apply_tracker_templates_to_feature_payloads',
    '_profile_class_row_level_map',
    '_merge_resource_templates',
    '_extract_existing_feature_choice_map',
    '_merge_selected_choice_maps',
    '_build_native_level_up_preview',
    '_build_level_up_spellcasting',
    'normalize_definition_to_native_model',
    '_multiclass_requirement_text',
    '_meets_multiclass_requirements',
    '_extract_multiclass_gained_armor_proficiencies',
    '_extract_multiclass_gained_weapon_proficiencies',
    '_extract_multiclass_gained_tool_proficiencies',
    '_extract_multiclass_gained_language_proficiencies',
    '_multiclass_skill_choice_fields',
    '_multiclass_tool_choice_fields',
    '_multiclass_language_choice_fields',
    '_extract_multiclass_gained_skill_proficiencies',
)


def _builder_dependency(name: str) -> Any:
    from . import character_builder as character_builder_module

    return getattr(character_builder_module, name)


def _builder_proxy(name: str):
    def _proxy(*args: Any, **kwargs: Any) -> Any:
        return _builder_dependency(name)(*args, **kwargs)

    _proxy.__name__ = name
    return _proxy


for _builder_proxy_name in _BUILDER_PROXY_NAMES:
    globals()[_builder_proxy_name] = _builder_proxy(_builder_proxy_name)
del _builder_proxy_name


class CharacterBuildError(ValueError):
    pass


def supports_native_level_up(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_slug: str = "",
    campaign_page_records: list[Any] | None = None,
) -> bool:
    if systems_service is not None and str(campaign_slug or "").strip():
        readiness = native_level_up_readiness(
            systems_service,
            campaign_slug,
            definition,
            campaign_page_records=campaign_page_records,
        )
        return str(readiness.get("status") or "").strip() == NATIVE_LEVEL_UP_READY
    return _native_level_up_support_error(definition) == ""


def native_level_up_readiness(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    source_type = _character_source_type(definition)
    is_native = source_type == "native_character_builder"
    is_imported = source_type in IMPORTED_CHARACTER_SOURCE_TYPES
    current_level = _resolve_native_character_level(definition)

    if not is_native and not is_imported:
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": "Level-up currently supports native in-app characters and imported character sheets only.",
            "reasons": ["This character source is outside the current native progression flow."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    classes = ensure_profile_class_rows(definition.profile)
    if not classes:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"This {character_label} character is missing a valid class row.",
            "reasons": ["The character needs at least one class row before native level-up can continue."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    if current_level < 1:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"This {character_label} character is missing a valid current level.",
            "reasons": ["The character needs a valid level before native level-up can continue."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    if current_level >= 20:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"This {character_label} character is already at level 20.",
            "reasons": ["The current native level-up flow stops at level 20."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    enabled_class_options = _list_campaign_enabled_entries(systems_service, campaign_slug, "class")
    class_options = [entry for entry in enabled_class_options if _supports_native_class_entry(entry)]
    species_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "race"),
        campaign_page_records or [],
        kind="species",
    )
    background_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "background"),
        campaign_page_records or [],
        kind="background",
    )

    selected_species_match = _resolve_profile_entry_match(
        species_options,
        definition.profile.get("species_ref"),
        page_ref=definition.profile.get("species_page_ref"),
        fallback_title=str(definition.profile.get("species") or "").strip(),
    )
    selected_species = selected_species_match.get("entry")
    selected_background_match = _resolve_profile_entry_match(
        background_options,
        definition.profile.get("background_ref"),
        page_ref=definition.profile.get("background_page_ref"),
        fallback_title=str(definition.profile.get("background") or "").strip(),
    )
    selected_background = selected_background_match.get("entry")

    repair_reasons: list[str] = []
    selected_class_rows: list[dict[str, Any]] = []
    shared_slot_multiclass_ready = True
    shared_slot_multiclass_reasons: list[str] = []
    selected_class = None
    selected_subclass = None
    for index, class_payload in enumerate(classes, start=1):
        row_id = str(class_payload.get("row_id") or "").strip() or f"class-row-{index}"
        row_level = max(int(class_payload.get("level") or 0), 0)
        class_row_ref = dict(class_payload.get("systems_ref") or {})
        profile_row_ref = profile_primary_class_ref(definition.profile) if index == 1 else {}
        selected_enabled_class_match = _resolve_profile_entry_match(
            enabled_class_options,
            profile_row_ref or class_row_ref,
            fallback_title=str(class_payload.get("class_name") or _native_character_class_name(definition) or "").strip(),
        )
        selected_enabled_class = selected_enabled_class_match.get("entry")
        if selected_enabled_class is not None and not _supports_native_class_entry(selected_enabled_class):
            character_label = "imported" if is_imported else "native"
            class_policy = _native_source_matrix_support_policy(selected_enabled_class)
            policy_reason = str(class_policy.get("reason") or "").strip()
            message = (
                f"This {character_label} character's base class is outside the current native support lane."
                if index == 1
                else f"This {character_label} character includes a class row outside the current native support lane."
            )
            return {
                "status": NATIVE_LEVEL_UP_UNSUPPORTED,
                "message": message,
                "reasons": [policy_reason] if policy_reason else [],
                "source_type": source_type,
                "is_native": is_native,
                "is_imported": is_imported,
                "current_level": current_level,
                "selected_class": None,
                "selected_species": selected_species,
                "selected_background": selected_background,
                "selected_subclass": None,
                "spell_repair_rows": [],
                "selected_class_rows": [],
            }

        selected_class_match = _resolve_profile_entry_match(
            class_options,
            profile_row_ref or class_row_ref,
            fallback_title=str(class_payload.get("class_name") or _native_character_class_name(definition) or "").strip(),
        )
        selected_row_class = selected_class_match.get("entry")
        if index == 1:
            selected_class = selected_row_class
        if selected_row_class is None:
            subject = "base class" if index == 1 else f"class row {index}"
            repair_reasons.append(
                f"Choose a supported {_profile_link_subject(subject, systems_ref=profile_row_ref or class_row_ref)} link for this character."
            )
            selected_class_rows.append(
                {
                    "row_id": row_id,
                    "row_index": index,
                    "row_level": row_level,
                    "class_payload": dict(class_payload),
                    "selected_class": None,
                    "selected_subclass": None,
                    "class_progression": [],
                    "subclass_progression": [],
                    "requires_subclass": False,
                    "shared_slot_multiclass_supported": False,
                    "spellcasting_row": False,
                    "multiclass_support_reason": "",
                }
            )
            continue

        if is_imported:
            class_row_match = _resolve_profile_entry_match(
                enabled_class_options,
                class_row_ref,
                fallback_title=str(class_payload.get("class_name") or selected_row_class.title or "").strip(),
            )
            if class_row_match.get("entry") is None:
                subject = "class row" if index == 1 else f"class row {index}"
                repair_reasons.append(
                    f"Choose the {_profile_link_subject(subject, systems_ref=class_row_ref, entry=selected_row_class)} link so native level-up can extend the imported class baseline cleanly."
                )

        class_progression = _class_progression_for_builder(
            systems_service,
            campaign_slug,
            selected_row_class,
            campaign_page_records=campaign_page_records,
        )
        subclass_options = _list_subclass_options(systems_service, campaign_slug, selected_row_class)
        profile_subclass_ref = profile_primary_subclass_ref(definition.profile) if index == 1 else {}
        class_row_subclass_ref = dict(class_payload.get("subclass_ref") or {})
        selected_subclass_match = _resolve_profile_entry_match(
            subclass_options,
            profile_subclass_ref or class_row_subclass_ref,
            fallback_title=str(class_payload.get("subclass_name") or (_native_character_subclass_name(definition) if index == 1 else "") or "").strip(),
        )
        selected_row_subclass = selected_subclass_match.get("entry")
        if index == 1:
            selected_subclass = selected_row_subclass
        subclass_label = str(selected_row_class.metadata.get("subclass_title") or "subclass").strip() or "subclass"
        subclass_subject = _profile_link_subject(
            subclass_label,
            systems_ref=profile_subclass_ref or class_row_subclass_ref,
            entry=selected_row_subclass,
        )
        requires_subclass = _class_requires_subclass_at_level(selected_row_class, class_progression, row_level)
        if requires_subclass and selected_row_subclass is None:
            repair_reasons.append(f"Choose a {subclass_subject} link before leveling up.")

        multiclass_support = _evaluate_shared_slot_multiclass_support(
            systems_service,
            campaign_slug,
            selected_class=selected_row_class,
            selected_subclass=selected_row_subclass,
            row_level=row_level,
            campaign_page_records=campaign_page_records,
        )
        row_multiclass_supported = bool(multiclass_support.get("supported"))
        multiclass_support_reason = str(multiclass_support.get("reason") or "").strip()
        if len(classes) > 1:
            if not row_multiclass_supported:
                shared_slot_multiclass_ready = False
                if multiclass_support_reason:
                    shared_slot_multiclass_reasons.append(multiclass_support_reason)

        selected_class_rows.append(
            {
                "row_id": row_id,
                "row_index": index,
                "row_level": row_level,
                "class_payload": dict(class_payload),
                "selected_class": selected_row_class,
                "selected_subclass": selected_row_subclass,
                "class_progression": class_progression,
                "subclass_progression": _subclass_progression_for_builder(
                    systems_service,
                    campaign_slug,
                    selected_row_subclass,
                    campaign_page_records=campaign_page_records,
                ),
                "requires_subclass": requires_subclass,
                "shared_slot_multiclass_supported": row_multiclass_supported,
                "spellcasting_row": bool(multiclass_support.get("spellcasting_row")),
                "multiclass_support_reason": multiclass_support_reason,
            }
        )

    if selected_species is None:
        repair_reasons.append(
            f"Choose a {_profile_link_subject('species', systems_ref=definition.profile.get('species_ref'))} link that the native level-up flow can resolve."
        )
    if selected_background is None:
        repair_reasons.append(
            f"Choose a {_profile_link_subject('background', systems_ref=definition.profile.get('background_ref'))} link that the native level-up flow can resolve."
        )

    if len(classes) > 1 and not shared_slot_multiclass_ready:
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": "This character is outside the current multiclass spellcasting progression lane.",
            "reasons": shared_slot_multiclass_reasons,
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
            "selected_class": selected_class,
            "selected_species": selected_species,
            "selected_background": selected_background,
            "selected_subclass": selected_subclass,
            "spell_repair_rows": [],
            "selected_class_rows": selected_class_rows,
        }

    spell_repair_rows: list[dict[str, Any]] = []
    if is_imported:
        spell_catalog = _effective_spell_catalog_for_definition(
            definition,
            systems_service=systems_service,
        )
        spell_repair_rows = _build_imported_spell_repair_rows(
            definition,
            selected_class_rows=selected_class_rows,
            spell_catalog=spell_catalog,
        )
        if spell_repair_rows:
            repair_reasons.append("Classify the current imported spell rows so native spell progression can trust them.")

    if repair_reasons:
        return {
            "status": NATIVE_LEVEL_UP_REPAIRABLE if is_imported else NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": (
                "This imported character needs a quick progression repair before native level-up."
                if is_imported
                else "This native character is missing enabled links needed for level-up."
            ),
            "reasons": repair_reasons,
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
            "selected_class": selected_class,
            "selected_species": selected_species,
            "selected_background": selected_background,
            "selected_subclass": selected_subclass,
            "spell_repair_rows": spell_repair_rows,
            "selected_class_rows": selected_class_rows,
            "shared_slot_multiclass_ready": shared_slot_multiclass_ready,
        }

    return {
        "status": NATIVE_LEVEL_UP_READY,
        "message": "",
        "reasons": [],
        "source_type": source_type,
        "is_native": is_native,
        "is_imported": is_imported,
        "current_level": current_level,
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "spell_repair_rows": spell_repair_rows,
        "selected_class_rows": selected_class_rows,
        "shared_slot_multiclass_ready": shared_slot_multiclass_ready,
    }


def _character_source_type(definition: CharacterDefinition) -> str:
    return str((definition.source or {}).get("source_type") or "").strip()


def _native_character_subclass_name(definition: CharacterDefinition) -> str:
    return profile_primary_subclass_name(definition.profile)


def _native_progression_payload(source_payload: dict[str, Any] | None) -> dict[str, Any]:
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


def _native_progression_hp_baseline(source_payload: dict[str, Any] | None) -> dict[str, int] | None:
    payload = _native_progression_payload(source_payload)
    hp_baseline = dict(payload.get("hp_baseline") or {})
    try:
        level = int(hp_baseline.get("level") or 0)
        max_hp = int(hp_baseline.get("max_hp") or 0)
    except (TypeError, ValueError):
        return None
    if level <= 0 or max_hp <= 0:
        return None
    return {"level": level, "max_hp": max_hp}


def _ensure_native_progression_hp_baseline(
    source_payload: dict[str, Any] | None,
    *,
    level: int,
    max_hp: int,
    baseline_repaired: bool = False,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    if _native_progression_hp_baseline(source) is not None:
        if baseline_repaired:
            native_progression = _native_progression_payload(source)
            native_progression["baseline_repaired_at"] = isoformat(utcnow())
            source["native_progression"] = native_progression
        return source
    clean_level = max(int(level or 0), 0)
    clean_max_hp = max(int(max_hp or 0), 0)
    if clean_level <= 0 or clean_max_hp <= 0:
        return source
    native_progression = _native_progression_payload(source)
    native_progression["hp_baseline"] = {"level": clean_level, "max_hp": clean_max_hp}
    if baseline_repaired:
        native_progression["baseline_repaired_at"] = isoformat(utcnow())
    source["native_progression"] = native_progression
    return source


def _seed_source_hp_baseline_from_definition(
    source_payload: dict[str, Any] | None,
    definition: CharacterDefinition,
    *,
    baseline_repaired: bool = False,
) -> dict[str, Any]:
    current_level = _resolve_native_character_level(definition)
    base_stats = _definition_base_stats_without_adjustments(definition)
    try:
        max_hp = int(base_stats.get("max_hp") or 0)
    except (TypeError, ValueError):
        max_hp = 0
    return _ensure_native_progression_hp_baseline(
        source_payload,
        level=current_level,
        max_hp=max_hp,
        baseline_repaired=baseline_repaired,
    )


def _with_native_progression_event(
    source_payload: dict[str, Any] | None,
    *,
    kind: str,
    target_level: int,
    previous_level: int | None = None,
    baseline_repaired: bool = False,
    hp_gain: int | None = None,
    max_hp_delta: int | None = None,
    action: str | None = None,
    class_row_id: str | None = None,
    class_ref: dict[str, Any] | None = None,
    subclass_ref: dict[str, Any] | None = None,
    row_from_level: int | None = None,
    row_to_level: int | None = None,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    native_progression = _native_progression_payload(source)
    if baseline_repaired:
        native_progression["baseline_repaired_at"] = isoformat(utcnow())
    history = [dict(entry) for entry in list(native_progression.get("history") or []) if isinstance(entry, dict)]
    event: dict[str, Any] = {
        "kind": str(kind or "").strip() or "managed",
        "at": isoformat(utcnow()),
        "target_level": int(target_level or 0),
    }
    if previous_level is not None:
        event["from_level"] = int(previous_level)
        event["to_level"] = int(target_level or 0)
    if hp_gain is not None:
        event["hp_gain"] = int(hp_gain)
    if max_hp_delta is not None:
        event["max_hp_delta"] = int(max_hp_delta)
    if str(action or "").strip():
        event["action"] = str(action or "").strip()
    if str(class_row_id or "").strip():
        event["class_row_id"] = str(class_row_id or "").strip()
    if isinstance(class_ref, dict) and class_ref:
        event["class_ref"] = dict(class_ref)
    if isinstance(subclass_ref, dict) and subclass_ref:
        event["subclass_ref"] = dict(subclass_ref)
    if row_from_level is not None:
        event["row_from_level"] = int(row_from_level)
    if row_to_level is not None:
        event["row_to_level"] = int(row_to_level)
    history.append(event)
    native_progression["history"] = history
    source["native_progression"] = native_progression
    return source


def _build_imported_spell_repair_rows(
    definition: CharacterDefinition,
    *,
    selected_class_rows: list[dict[str, Any]] | None,
    spell_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    spell_row_contexts: list[dict[str, Any]] = []
    for row in list(selected_class_rows or []):
        row_context = dict(row or {})
        selected_class = row_context.get("selected_class")
        if not isinstance(selected_class, SystemsEntryRecord):
            continue
        selected_subclass = (
            row_context.get("selected_subclass")
            if isinstance(row_context.get("selected_subclass"), SystemsEntryRecord)
            else None
        )
        row_level = int(row_context.get("row_level") or 0)
        spell_mode = _spellcasting_mode_for_class(
            selected_class.title,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            row_level=row_level,
        )
        if not spell_mode:
            continue
        spell_row_contexts.append(
            {
                "row_id": str(row_context.get("row_id") or "").strip(),
                "class_name": str(selected_class.title or "").strip(),
                "spell_list_class_name": _spell_list_class_name_for_class(
                    selected_class.title,
                    selected_class=selected_class,
                    selected_subclass=selected_subclass,
                    row_level=row_level,
                ),
                "spell_mode": spell_mode,
                "class_entry": selected_class,
                "subclass_entry": selected_subclass,
                "row_level": row_level,
                "class_progression": list(row_context.get("class_progression") or []),
                "subclass_progression": list(row_context.get("subclass_progression") or []),
            }
        )
    if not spell_row_contexts:
        return []

    automatic_prepared_lookup_keys_by_row: dict[str, set[str]] = {}
    resolved_spell_catalog = dict(spell_catalog or {})
    for row_context in spell_row_contexts:
        row_id = str(row_context.get("row_id") or "").strip()
        if not row_id:
            continue
        automatic_prepared_lookup_keys_by_row[row_id] = _automatic_prepared_spell_lookup_keys_for_row(
            selected_class=row_context.get("class_entry"),
            selected_subclass=row_context.get("subclass_entry"),
            spell_catalog=resolved_spell_catalog,
            target_level=int(row_context.get("row_level") or 0),
            class_progression=list(row_context.get("class_progression") or []),
            subclass_progression=list(row_context.get("subclass_progression") or []),
        )

    rows: list[dict[str, Any]] = []
    row_option_lookup = {
        str(row.get("row_id") or "").strip(): {
            "value": str(row.get("row_id") or "").strip(),
            "label": str(row.get("class_name") or "Spellcasting").strip(),
            "spell_mode": str(row.get("spell_mode") or "").strip(),
        }
        for row in spell_row_contexts
        if str(row.get("row_id") or "").strip()
    }
    for index, spell in enumerate(list((definition.spellcasting or {}).get("spells") or []), start=1):
        payload = dict(spell or {})
        name = str(payload.get("name") or "").strip()
        mark = str(payload.get("mark") or "").strip()
        if not name:
            continue
        if _spell_payload_source_row_id(payload):
            continue
        candidate_row_ids = _imported_spell_candidate_row_ids(
            payload,
            spell_row_contexts=spell_row_contexts,
            spell_catalog=spell_catalog,
        )
        if not candidate_row_ids:
            candidate_row_ids = list(row_option_lookup.keys())
        payload_key = _spell_payload_key(payload)
        automatic_prepared_row_ids = [
            row_id
            for row_id in candidate_row_ids
            if payload_key and payload_key in automatic_prepared_lookup_keys_by_row.get(row_id, set())
        ]
        if len(automatic_prepared_row_ids) == 1:
            continue
        selected_row_id = str(payload.get("class_row_id") or "").strip()
        candidate_row_id_set = set(candidate_row_ids)
        has_resolved_class_row = selected_row_id in candidate_row_id_set
        if selected_row_id not in candidate_row_ids:
            selected_row_id = candidate_row_ids[0] if len(candidate_row_ids) == 1 else ""
        option_rows = [
            dict(row_option_lookup[row_id])
            for row_id in candidate_row_ids
            if row_id in row_option_lookup
        ]
        mark_options = _imported_spell_mark_options_for_rows(
            spell_row_contexts,
            selected_row_id=selected_row_id,
            candidate_row_ids=candidate_row_ids,
        )
        selected_row_mode = next(
            (str(option.get("spell_mode") or "").strip() for option in option_rows if option.get("value") == selected_row_id),
            "",
        )
        if (
            bool(payload.get("is_always_prepared"))
            or (mark and _spell_mark_is_valid_for_mode(mark, selected_row_mode or ""))
            or (
                not mark
                and has_resolved_class_row
                and selected_row_mode == "prepared"
                and (_spell_payload_spell_level(payload, spell_catalog=spell_catalog) or 0) > 0
            )
        ) and (selected_row_id or len(option_rows) <= 1):
            continue
        rows.append(
            {
                "index": index,
                "name": name,
                "field_name": f"repair_spell_mark_{index}",
                "class_row_field_name": f"repair_spell_class_row_{index}",
                "class_row_selected": selected_row_id,
                "class_row_options": option_rows,
                "selected": mark if _spell_mark_is_valid_for_mode(mark, selected_row_mode or "") else "",
                "options": [_choice_option(label, value) for value, label in mark_options],
                "selected_row_mode": selected_row_mode,
            }
        )
    return rows


def _spell_mark_is_valid_for_mode(mark: str, spell_mode: str) -> bool:
    clean_mark = str(mark or "").strip()
    if not clean_mark or not spell_mode:
        return False
    valid_marks = {value for value, _label in _imported_spell_mark_options(spell_mode)}
    return clean_mark in valid_marks


def _canonical_automatic_prepared_spell_mark(mark: str) -> str:
    parts: list[str] = []
    for part in [part.strip() for part in str(mark or "").split("+")]:
        normalized_part = normalize_lookup(part)
        if normalized_part == "cantrip" and "Cantrip" not in parts:
            parts.append("Cantrip")
        elif normalized_part == "spellbook" and "Spellbook" not in parts:
            parts.append("Spellbook")
        elif normalized_part == "ritual book" and "Ritual book" not in parts:
            parts.append("Ritual book")
    return " + ".join(parts)


def _automatic_prepared_feature_entries(
    *,
    feature_entries: list[dict[str, Any]] | None = None,
    class_progression: list[dict[str, Any]] | None = None,
    subclass_progression: list[dict[str, Any]] | None = None,
    target_level: int,
    selected_choices: dict[str, list[str]] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> list[dict[str, Any]]:
    merged_feature_entries = [dict(feature_entry or {}) for feature_entry in list(feature_entries or [])]
    if class_progression or subclass_progression:
        merged_feature_entries.extend(
            _spell_feature_entries_from_progressions(
                class_progression=list(class_progression or []),
                subclass_progression=list(subclass_progression or []),
                target_level=target_level,
                selected_choices=selected_choices,
                optionalfeature_catalog=optionalfeature_catalog,
            )
        )
    return _dedupe_spell_feature_entries(merged_feature_entries)


def _automatic_prepared_spell_lookup_keys_for_row(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    class_progression: list[dict[str, Any]] | None = None,
    subclass_progression: list[dict[str, Any]] | None = None,
    selected_choices: dict[str, list[str]] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> set[str]:
    return _automatic_prepared_spell_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=_automatic_prepared_feature_entries(
            feature_entries=feature_entries,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        ),
    )


def _apply_automatic_prepared_spell_flags(
    spell_payloads: list[dict[str, Any]],
    *,
    campaign_slug: str,
    systems_service: Any | None,
    resolved_class_rows: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    row_lookup_keys: dict[str, set[str]] = {}
    for row in resolved_class_rows:
        row_id = str(row.get("row_id") or "").strip()
        selected_class = row.get("selected_class")
        if not row_id or not isinstance(selected_class, SystemsEntryRecord):
            continue
        selected_subclass = (
            row.get("selected_subclass")
            if isinstance(row.get("selected_subclass"), SystemsEntryRecord)
            else None
        )
        row_level = max(int(row.get("row_level") or 0), 0)
        class_progression = []
        subclass_progression = []
        if systems_service is not None:
            class_progression = _class_progression_for_builder(
                systems_service,
                campaign_slug,
                selected_class,
            )
            subclass_progression = _subclass_progression_for_builder(
                systems_service,
                campaign_slug,
                selected_subclass,
            )
        row_lookup_keys[row_id] = _automatic_prepared_spell_lookup_keys_for_row(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=row_level,
            feature_entries=feature_entries,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
        )

    if not row_lookup_keys:
        return _normalize_spell_payloads(spell_payloads)

    assigned_payloads = _assign_spell_payload_class_rows(
        spell_payloads,
        spellcasting_rows=[
            {"class_row_id": str(row.get("row_id") or "").strip()}
            for row in resolved_class_rows
            if str(row.get("row_id") or "").strip()
        ],
    )
    updated_payloads: list[dict[str, Any]] = []
    for payload in assigned_payloads:
        spell_payload = dict(payload or {})
        row_id = _spell_payload_class_row_id(spell_payload)
        payload_key = _spell_payload_key(spell_payload)
        if payload_key and payload_key in row_lookup_keys.get(row_id, set()):
            spell_payload["is_always_prepared"] = True
            spell_payload["mark"] = _canonical_automatic_prepared_spell_mark(
                str(spell_payload.get("mark") or "").strip()
            )
        updated_payloads.append(spell_payload)
    return _normalize_spell_payloads(updated_payloads)


def _imported_spell_mark_options_for_rows(
    spell_row_contexts: list[dict[str, Any]],
    *,
    selected_row_id: str,
    candidate_row_ids: list[str],
) -> list[tuple[str, str]]:
    if selected_row_id:
        selected_mode = next(
            (
                str(row.get("spell_mode") or "").strip()
                for row in spell_row_contexts
                if str(row.get("row_id") or "").strip() == selected_row_id
            ),
            "",
        )
        if selected_mode:
            return _imported_spell_mark_options(selected_mode)
    merged: list[tuple[str, str]] = []
    seen_values: set[str] = set()
    for row_id in candidate_row_ids:
        spell_mode = next(
            (
                str(row.get("spell_mode") or "").strip()
                for row in spell_row_contexts
                if str(row.get("row_id") or "").strip() == row_id
            ),
            "",
        )
        for value, label in _imported_spell_mark_options(spell_mode):
            if value in seen_values:
                continue
            seen_values.add(value)
            merged.append((value, label))
    return merged


def _imported_spell_candidate_row_ids(
    spell_payload: dict[str, Any],
    *,
    spell_row_contexts: list[dict[str, Any]],
    spell_catalog: dict[str, Any] | None = None,
) -> list[str]:
    explicit_row_id = str(spell_payload.get("class_row_id") or "").strip()
    known_row_ids = [
        str(row.get("row_id") or "").strip()
        for row in spell_row_contexts
        if str(row.get("row_id") or "").strip()
    ]
    if explicit_row_id and explicit_row_id in set(known_row_ids):
        return [explicit_row_id]

    matched_row_ids: list[str] = []
    spell_entry = None
    payload_key = _spell_payload_key(spell_payload)
    if payload_key:
        spell_entry = _resolve_spell_entry(payload_key, dict(spell_catalog or {}))
    if spell_entry is None:
        spell_name = str(spell_payload.get("name") or "").strip()
        if spell_name:
            spell_entry = _resolve_spell_entry(spell_name, dict(spell_catalog or {}))
    if spell_entry is not None:
        class_lists = dict((getattr(spell_entry, "metadata", {}) or {})).get("class_lists") or {}
        allowed_class_names = {
            normalize_lookup(candidate)
            for class_names in dict(class_lists).values()
            for candidate in list(class_names or [])
            if str(candidate or "").strip()
        }
        matched_row_ids = [
            str(row.get("row_id") or "").strip()
            for row in spell_row_contexts
            if normalize_lookup(str(row.get("spell_list_class_name") or row.get("class_name") or "").strip())
            in allowed_class_names
        ]
        if len(matched_row_ids) == 1:
            return matched_row_ids

    source_label = normalize_lookup(str(spell_payload.get("source") or "").strip())
    if source_label:
        matched_row_ids = [
            str(row.get("row_id") or "").strip()
            for row in spell_row_contexts
            if normalize_lookup(str(row.get("class_name") or "").strip()) == source_label
            or normalize_lookup(str(row.get("spell_list_class_name") or "").strip()) == source_label
            or source_label.startswith(f"{normalize_lookup(str(row.get('class_name') or '').strip())} ")
            or source_label.startswith(f"{normalize_lookup(str(row.get('spell_list_class_name') or '').strip())} ")
        ]
        if matched_row_ids:
            return matched_row_ids

    if len(spell_row_contexts) == 1:
        return [str(spell_row_contexts[0].get("row_id") or "").strip()]
    return list(known_row_ids)


def _imported_spell_mark_options(spell_mode: str) -> list[tuple[str, str]]:
    if spell_mode == "known":
        return [("Cantrip", "Cantrip"), ("Known", "Known")]
    if spell_mode == "prepared":
        return [("Cantrip", "Cantrip"), ("Prepared", "Prepared"), ("Known", "Known")]
    if spell_mode == "wizard":
        return [
            ("Cantrip", "Cantrip"),
            ("Spellbook", "Spellbook"),
            ("Prepared + Spellbook", "Prepared + Spellbook"),
            ("Prepared", "Prepared"),
            ("Known", "Known"),
        ]
    return []


def _class_row_level_text(class_payload: dict[str, Any]) -> str:
    payload = dict(class_payload or {})
    class_name = str(
        payload.get("class_name")
        or dict(payload.get("systems_ref") or {}).get("title")
        or ""
    ).strip()
    level = int(payload.get("level") or 0)
    if class_name and level > 0:
        return f"{class_name} {level}"
    if class_name:
        return class_name
    if level > 0:
        return f"Level {level}"
    return "Class Row"


def _sync_profile_with_class_rows(profile: dict[str, Any], class_rows: list[dict[str, Any]]) -> dict[str, Any]:
    updated_profile = dict(profile or {})
    updated_profile["classes"] = ensure_profile_class_rows({"classes": class_rows})
    first_row = dict(updated_profile["classes"][0] or {}) if updated_profile["classes"] else {}
    updated_profile["class_ref"] = dict(first_row.get("systems_ref") or {}) or None
    updated_profile["subclass_ref"] = dict(first_row.get("subclass_ref") or {}) or None
    return sync_profile_class_summary(updated_profile)


def _build_resulting_level_up_profile(
    current_definition: CharacterDefinition,
    *,
    action: str,
    target_class_row_id: str,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    row_target_level: int,
) -> dict[str, Any]:
    classes = ensure_profile_class_rows(current_definition.profile)
    updated_rows: list[dict[str, Any]] = []
    if action == "add_class":
        updated_rows = [dict(row) for row in classes]
        new_row = {
            "row_id": target_class_row_id or f"class-row-{len(updated_rows) + 1}",
            "class_name": selected_class.title,
            "subclass_name": selected_subclass.title if selected_subclass is not None else "",
            "level": row_target_level,
            "systems_ref": _systems_ref_from_entry(selected_class),
        }
        if selected_subclass is not None:
            new_row["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
        updated_rows.append(new_row)
    else:
        for row in classes:
            payload = dict(row or {})
            if str(payload.get("row_id") or "").strip() != str(target_class_row_id or "").strip():
                updated_rows.append(payload)
                continue
            payload["class_name"] = selected_class.title
            payload["level"] = row_target_level
            payload["systems_ref"] = _systems_ref_from_entry(selected_class)
            payload["subclass_name"] = selected_subclass.title if selected_subclass is not None else ""
            if selected_subclass is not None:
                payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
            else:
                payload.pop("subclass_ref", None)
            updated_rows.append(payload)
    return _sync_profile_with_class_rows(dict(current_definition.profile or {}), updated_rows)


def _build_multiclass_add_choice_sections(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    feat_catalog: dict[str, Any],
    subclass_options: list[SystemsEntryRecord],
    requires_subclass: bool,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    sections = _build_level_up_choice_sections(
        definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_options=feat_options,
        feat_catalog=feat_catalog,
        subclass_options=subclass_options,
        requires_subclass=requires_subclass,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        target_level=1,
        current_ability_scores=_ability_scores_from_definition(definition),
        values=values,
    )
    multiclass_fields = (
        _multiclass_skill_choice_fields(selected_class, definition=definition, values=values)
        + _multiclass_tool_choice_fields(selected_class, values=values)
        + _multiclass_language_choice_fields(selected_class, values=values)
    )
    if not multiclass_fields:
        return sections
    if sections and str(sections[0].get("title") or "").strip() == "Class Choices":
        first_section = dict(sections[0] or {})
        first_section["fields"] = multiclass_fields + list(first_section.get("fields") or [])
        return [first_section, *sections[1:]]
    return [{"title": "Class Choices", "fields": multiclass_fields}, *sections]


def build_native_level_up_context(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    form_values: dict[str, str] | None = None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    readiness = native_level_up_readiness(
        systems_service,
        campaign_slug,
        definition,
        campaign_page_records=campaign_page_records,
    )
    if str(readiness.get("status") or "").strip() != NATIVE_LEVEL_UP_READY:
        raise CharacterBuildError(str(readiness.get("message") or "This character is not ready for native level-up."))

    values = _normalize_level_up_values(definition, form_values or {})
    current_level = int(readiness.get("current_level") or _resolve_native_character_level(definition))
    next_level = current_level + 1
    static_bundle = _build_common_builder_static_bundle(
        systems_service,
        campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    class_options = list(static_bundle.get("supported_class_entries") or [])
    species_options = list(static_bundle.get("species_options") or [])
    background_options = list(static_bundle.get("background_options") or [])
    feat_options = list(static_bundle.get("feat_options") or [])
    feat_catalog = dict(static_bundle.get("feat_catalog") or {})
    optionalfeature_catalog = dict(static_bundle.get("optionalfeature_catalog") or {})
    item_catalog = dict(static_bundle.get("item_catalog") or {})
    spell_catalog = dict(static_bundle.get("spell_catalog") or {})
    row_contexts = [
        dict(row or {})
        for row in list(readiness.get("selected_class_rows") or [])
        if isinstance(row, dict)
    ]
    current_class_rows = ensure_profile_class_rows(definition.profile)
    target_row_options = [
        {
            "value": str(row.get("row_id") or "").strip(),
            "label": _class_row_level_text(dict(row.get("class_payload") or {})),
        }
        for row in row_contexts
    ]
    shared_slot_ready_for_add_class = bool(readiness.get("shared_slot_multiclass_ready"))
    shared_slot_ready_for_add_class = shared_slot_ready_for_add_class and all(
        bool(row.get("shared_slot_multiclass_supported"))
        for row in row_contexts
        if row.get("selected_class") is not None
    )
    values["advancement_mode"] = str(values.get("advancement_mode") or "advance_existing").strip() or "advance_existing"
    if values["advancement_mode"] not in {"advance_existing", "add_class"}:
        values["advancement_mode"] = "advance_existing"
    if values["advancement_mode"] == "add_class" and not shared_slot_ready_for_add_class:
        values["advancement_mode"] = "advance_existing"
    default_target_row_id = str((row_contexts[0] or {}).get("row_id") or "").strip() if row_contexts else ""
    if not str(values.get("target_class_row_id") or "").strip():
        values["target_class_row_id"] = default_target_row_id
    allowed_target_row_ids = {str(option.get("value") or "").strip() for option in target_row_options}
    if str(values.get("target_class_row_id") or "").strip() not in allowed_target_row_ids:
        values["target_class_row_id"] = default_target_row_id

    selected_species = readiness.get("selected_species")
    selected_background = readiness.get("selected_background")
    if selected_species is None or selected_background is None:
        raise CharacterBuildError("This character is missing the species or background needed for level-up.")

    ability_scores = _ability_scores_from_definition(definition)
    selected_class: SystemsEntryRecord | None = None
    selected_subclass: SystemsEntryRecord | None = None
    class_progression: list[dict[str, Any]] = []
    subclass_progression: list[dict[str, Any]] = []
    subclass_options: list[SystemsEntryRecord] = []
    requires_subclass = False
    acted_row_id = str(values.get("target_class_row_id") or "").strip()
    row_current_level = current_level
    row_target_level = next_level
    new_class_options = [
        entry
        for entry in _list_shared_slot_multiclass_class_entries(
            systems_service,
            campaign_slug,
            campaign_page_records=campaign_page_records,
        )
        if (
            str(entry.slug or "").strip(),
            str(entry.source_id or "").strip().upper(),
        )
        not in {
            (
                str((row.get("selected_class").slug if isinstance(row.get("selected_class"), SystemsEntryRecord) else "")).strip(),
                str((row.get("selected_class").source_id if isinstance(row.get("selected_class"), SystemsEntryRecord) else "")).strip().upper(),
            )
            for row in row_contexts
        }
    ]
    if values["advancement_mode"] == "add_class" and not new_class_options:
        values["advancement_mode"] = "advance_existing"
    if values["advancement_mode"] == "add_class":
        values["new_class_slug"] = _sanitize_entry_selection_value(values.get("new_class_slug"), new_class_options)
        selected_class = _resolve_selected_entry(new_class_options, values.get("new_class_slug", ""))
        acted_row_id = f"class-row-{len(current_class_rows) + 1}"
        row_current_level = 0
        row_target_level = 1
        if selected_class is not None:
            subclass_options = _list_shared_slot_multiclass_subclass_options(
                systems_service,
                campaign_slug,
                selected_class,
                subclass_entries=list(static_bundle.get("subclass_entries") or []),
                campaign_page_records=campaign_page_records,
            )
            class_progression = _class_progression_for_builder(
                systems_service,
                campaign_slug,
                selected_class,
                campaign_page_records=campaign_page_records,
            )
            values["new_subclass_slug"] = _sanitize_entry_selection_value(values.get("new_subclass_slug"), subclass_options)
            selected_subclass = _resolve_selected_entry(subclass_options, values.get("new_subclass_slug", ""))
            requires_subclass = _class_requires_subclass_at_level(selected_class, class_progression, 1) and selected_subclass is None
            subclass_progression = _subclass_progression_for_builder(
                systems_service,
                campaign_slug,
                selected_subclass,
                campaign_page_records=campaign_page_records,
            )
            values, choice_sections = _stabilize_choice_section_values(
                values,
                static_keys=LEVEL_UP_BUILDER_STATIC_KEYS,
                build_sections=lambda current_values: _build_multiclass_add_choice_sections(
                    definition=definition,
                    selected_class=selected_class,
                    selected_subclass=selected_subclass,
                    feat_options=feat_options,
                    feat_catalog=feat_catalog,
                    subclass_options=subclass_options,
                    requires_subclass=requires_subclass,
                    class_progression=class_progression,
                    subclass_progression=subclass_progression,
                    optionalfeature_catalog=optionalfeature_catalog,
                    item_catalog=item_catalog,
                    spell_catalog=spell_catalog,
                    values=current_values,
                ),
            )
        else:
            choice_sections = []
    else:
        values["new_class_slug"] = ""
        values["new_subclass_slug"] = ""
        target_row_context = next(
            (
                dict(row)
                for row in row_contexts
                if str(row.get("row_id") or "").strip() == str(values.get("target_class_row_id") or "").strip()
            ),
            dict(row_contexts[0] or {}) if row_contexts else {},
        )
        if not target_row_context:
            raise CharacterBuildError("This character is missing the class row needed for level-up.")
        acted_row_id = str(target_row_context.get("row_id") or "").strip()
        row_current_level = int(target_row_context.get("row_level") or 0)
        row_target_level = row_current_level + 1
        selected_class = target_row_context.get("selected_class")
        selected_subclass = target_row_context.get("selected_subclass")
        if not isinstance(selected_class, SystemsEntryRecord):
            raise CharacterBuildError("This character is missing the class row needed for level-up.")
        subclass_options = _list_subclass_options(
            systems_service,
            campaign_slug,
            selected_class,
            subclass_entries=list(static_bundle.get("subclass_entries") or []),
        )
        existing_subclass_slug = _systems_ref_slug(dict((target_row_context.get("class_payload") or {}).get("subclass_ref") or {}))
        if existing_subclass_slug and not str(values.get("subclass_slug") or "").strip():
            values["subclass_slug"] = existing_subclass_slug
        values["subclass_slug"] = _sanitize_entry_selection_value(values.get("subclass_slug"), subclass_options)
        selected_subclass = _resolve_selected_entry(subclass_options, values.get("subclass_slug", ""))
        class_progression = list(target_row_context.get("class_progression") or [])
        requires_subclass = _class_requires_subclass_at_level(selected_class, class_progression, row_target_level) and selected_subclass is None
        subclass_progression = _subclass_progression_for_builder(
            systems_service,
            campaign_slug,
            selected_subclass,
            campaign_page_records=campaign_page_records,
        )
        values, choice_sections = _stabilize_choice_section_values(
            values,
            static_keys=LEVEL_UP_BUILDER_STATIC_KEYS,
            build_sections=lambda current_values: _build_level_up_choice_sections(
                definition=definition,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                feat_options=feat_options,
                feat_catalog=feat_catalog,
                subclass_options=subclass_options,
                requires_subclass=requires_subclass,
                class_progression=class_progression,
                subclass_progression=subclass_progression,
                optionalfeature_catalog=optionalfeature_catalog,
                item_catalog=item_catalog,
                spell_catalog=spell_catalog,
                target_level=row_target_level,
                current_ability_scores=ability_scores,
                values=current_values,
                class_row_id=acted_row_id,
            ),
        )
    choice_sections = _annotate_builder_choice_sections(
        choice_sections,
        preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
    )
    preview_profile = (
        _build_resulting_level_up_profile(
            definition,
            action="add_class" if values["advancement_mode"] == "add_class" else "advance_existing",
            target_class_row_id=acted_row_id,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            row_target_level=row_target_level,
        )
        if isinstance(selected_class, SystemsEntryRecord)
        else sync_profile_class_summary(dict(definition.profile or {}))
    )
    if isinstance(selected_class, SystemsEntryRecord):
        preview = _build_native_level_up_preview(
            definition=definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            feat_options=feat_options,
            feat_catalog=feat_catalog,
            choice_sections=choice_sections,
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            target_level=row_target_level,
            total_character_level=next_level,
            current_ability_scores=ability_scores,
            values=values,
            class_row_id=acted_row_id,
            resulting_profile=preview_profile,
        )
    else:
        try:
            preview_max_hp = max(int((definition.stats or {}).get("max_hp") or 0) + _parse_level_up_hit_point_gain(values), 1)
        except CharacterBuildError:
            preview_max_hp = max(int((definition.stats or {}).get("max_hp") or 0), 1)
        preview = {
            "class_level_text": str(preview_profile.get("class_level_text") or profile_class_level_text(definition.profile)),
            "class_rows": [_class_row_level_text(row) for row in ensure_profile_class_rows(preview_profile)],
            "max_hp": preview_max_hp,
            "gained_features": [],
            "resources": [],
            "spell_slots": [],
            "new_spells": [],
        }
    return {
        "values": values,
        "character_name": definition.name,
        "current_level": current_level,
        "next_level": next_level,
        "campaign_slug": campaign_slug,
        "campaign_page_records": list(campaign_page_records or []),
        "systems_service": systems_service,
        "advancement_mode": values["advancement_mode"],
        "mode_options": [
            {"value": "advance_existing", "label": "Advance existing class"},
            *(
                [{"value": "add_class", "label": "Add new class"}]
                if shared_slot_ready_for_add_class and new_class_options
                else []
            ),
        ],
        "can_add_class": bool(shared_slot_ready_for_add_class and new_class_options),
        "current_class_rows": [_class_row_level_text(row) for row in current_class_rows],
        "target_row_options": target_row_options,
        "target_class_row_id": acted_row_id,
        "row_current_level": row_current_level,
        "row_target_level": row_target_level,
        "new_class_options": [_entry_option(entry) for entry in new_class_options],
        "new_subclass_options": [_entry_option(entry) for entry in subclass_options] if values["advancement_mode"] == "add_class" else [],
        "multiclass_requirement_text": _multiclass_requirement_text(selected_class) if values["advancement_mode"] == "add_class" else "",
        "multiclass_requirements_met": (
            _meets_multiclass_requirements(selected_class, ability_scores=ability_scores)
            if values["advancement_mode"] == "add_class" and isinstance(selected_class, SystemsEntryRecord)
            else True
        ),
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "subclass_options": [_entry_option(entry) for entry in subclass_options],
        "feat_options": [_entry_option(entry) for entry in feat_options],
        "feat_catalog": feat_catalog,
        "optionalfeature_catalog": optionalfeature_catalog,
        "requires_subclass": requires_subclass,
        "choice_sections": choice_sections,
        "class_progression": class_progression,
        "subclass_progression": subclass_progression,
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
        "limitations": list(NATIVE_LEVEL_UP_LIMITATIONS),
        "preview": preview,
        "selected_class_rows": row_contexts,
        "field_live_preview": _level_up_field_live_preview_metadata(),
        "preview_region_ids": list(LEVEL_UP_PREVIEW_REGION_IDS),
        "preview_regions_csv": ",".join(LEVEL_UP_PREVIEW_REGION_IDS),
        "live_region_ids": list(LEVEL_UP_LIVE_REGION_IDS),
        "live_regions_csv": ",".join(LEVEL_UP_LIVE_REGION_IDS),
    }


def build_native_level_up_character_definition(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    level_up_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
    *,
    current_import_metadata: CharacterImportMetadata | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, int]:
    support_error = _native_level_up_support_error(
        current_definition,
        systems_service=level_up_context.get("systems_service"),
        campaign_slug=str(level_up_context.get("campaign_slug") or campaign_slug or "").strip(),
        campaign_page_records=level_up_context.get("campaign_page_records"),
    )
    if support_error:
        raise CharacterBuildError(support_error)

    advancement_mode = str(level_up_context.get("advancement_mode") or "advance_existing").strip() or "advance_existing"
    selected_class = level_up_context.get("selected_class")
    selected_species = level_up_context.get("selected_species")
    selected_background = level_up_context.get("selected_background")
    selected_subclass = level_up_context.get("selected_subclass")
    choice_sections = list(level_up_context.get("choice_sections") or [])
    class_progression = list(level_up_context.get("class_progression") or [])
    subclass_progression = list(level_up_context.get("subclass_progression") or [])
    feat_options = list(level_up_context.get("feat_options") or [])
    feat_catalog = dict(level_up_context.get("feat_catalog") or {})
    optionalfeature_catalog = dict(level_up_context.get("optionalfeature_catalog") or {})
    spell_catalog = dict(level_up_context.get("spell_catalog") or {})
    context_values = level_up_context.get("values")
    values = _normalize_level_up_values(
        current_definition,
        _sanitize_choice_section_values(
            {
                **(dict(context_values) if isinstance(context_values, dict) else {}),
                **{key: str(value) for key, value in dict(form_values or {}).items()},
            },
            choice_sections=choice_sections,
            static_keys=LEVEL_UP_BUILDER_STATIC_KEYS,
        ),
    )
    if selected_class is None or selected_species is None or selected_background is None:
        raise CharacterBuildError("This native character is missing the class, species, or background needed for level-up.")
    if level_up_context.get("requires_subclass") and selected_subclass is None:
        raise CharacterBuildError("Choose a subclass before leveling up this character.")

    current_level = int(level_up_context.get("current_level") or _resolve_native_character_level(current_definition))
    target_level = int(level_up_context.get("next_level") or (current_level + 1))
    if target_level != current_level + 1:
        raise CharacterBuildError("Level-up currently advances one level at a time.")
    target_class_row_id = str(level_up_context.get("target_class_row_id") or values.get("target_class_row_id") or "").strip()
    raw_row_current_level = level_up_context.get("row_current_level")
    raw_row_target_level = level_up_context.get("row_target_level")
    row_current_level = int(current_level if raw_row_current_level is None else raw_row_current_level)
    row_target_level = int((row_current_level + 1) if raw_row_target_level is None else raw_row_target_level)
    if advancement_mode == "add_class":
        if not _meets_multiclass_requirements(selected_class, ability_scores=_ability_scores_from_definition(current_definition)):
            requirement_text = _multiclass_requirement_text(selected_class)
            if requirement_text:
                raise CharacterBuildError(f"{selected_class.title} requires {requirement_text} before multiclassing.")
            raise CharacterBuildError(f"{selected_class.title} does not meet this character's multiclass requirements.")
        if row_target_level != 1:
            raise CharacterBuildError("New multiclass rows currently enter at level 1.")
    elif row_target_level != row_current_level + 1:
        raise CharacterBuildError("This class row can only advance one level at a time.")

    hp_gain = _parse_level_up_hit_point_gain(values)
    _, selected_choices = _resolve_builder_choices(choice_sections, values)
    base_ability_scores, level_up_feat_entries, _ = _resolve_level_up_ability_score_choices(
        current_ability_scores=_ability_scores_from_definition(current_definition),
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=row_target_level,
        values=values,
        strict=True,
    )
    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=row_target_level,
    )
    feature_choice_selections = _progression_feature_choice_selections(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=row_target_level,
        instance_prefix="levelup_feature",
    )
    new_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=row_target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    new_feature_entries.extend(level_up_feat_entries)
    new_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    new_feature_entries = _apply_campaign_feature_spell_manager_payloads(
        new_feature_entries,
        values=values,
        field_prefix_base="levelup_campaign_spell_manager",
    )
    new_automatic_prepared_feature_entries = _automatic_prepared_feature_entries(
        feature_entries=new_feature_entries,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=row_target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(new_feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        base_ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    proficiency_bonus = _proficiency_bonus_for_level(target_level)
    existing_skill_proficiency_levels = _skill_proficiency_levels_from_rows(
        list(current_definition.skills or []),
        ability_scores=_ability_scores_from_definition(current_definition),
        proficiency_bonus=int(
            (current_definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(current_level)
        ),
    )
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(selected_campaign_option_payloads)
    for skill_name in (
        _extract_feat_skill_proficiencies(feat_selections, selected_choices)
        + (_extract_multiclass_gained_skill_proficiencies(selected_choices) if advancement_mode == "add_class" else [])
        + list(campaign_option_proficiencies.get("skills") or [])
    ):
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        existing_skill_proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
            existing_skill_proficiency_levels.get(normalized_skill),
            "proficient",
        )
    existing_skill_proficiency_levels = _apply_feat_expertise_to_skill_proficiency_levels(
        existing_skill_proficiency_levels,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    existing_skill_proficiency_levels = _apply_feature_expertise_to_skill_proficiency_levels(
        existing_skill_proficiency_levels,
        feature_selections=feature_choice_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    skills = _build_skills_payload_from_levels(
        ability_scores,
        existing_skill_proficiency_levels,
        proficiency_bonus,
    )

    new_features, _ = _build_feature_payloads(
        new_feature_entries,
        ability_scores=ability_scores,
        current_level=row_target_level,
        class_row_id=target_class_row_id,
    )
    resulting_profile = _build_resulting_level_up_profile(
        current_definition,
        action=advancement_mode,
        target_class_row_id=target_class_row_id,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_target_level=row_target_level,
    )
    merged_features = _merge_feature_payloads(list(current_definition.features or []), new_features)
    merged_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        merged_features,
        ability_scores=ability_scores,
        current_level=target_level,
        class_row_levels=_profile_class_row_level_map(resulting_profile),
    )

    combined_selected_choices = _merge_selected_choice_maps(
        _extract_existing_feature_choice_map(current_definition),
        selected_choices,
    )
    item_catalog = _build_item_catalog([])
    item_catalog = dict(level_up_context.get("item_catalog") or item_catalog)
    resulting_armor_proficiencies = _dedupe_preserve_order(
        list((current_definition.proficiencies or {}).get("armor") or [])
        + (_extract_multiclass_gained_armor_proficiencies(selected_class) if advancement_mode == "add_class" else [])
        + _extract_feat_armor_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("armor") or [])
    )
    resulting_weapon_proficiencies = _dedupe_preserve_order(
        list((current_definition.proficiencies or {}).get("weapons") or [])
        + (_extract_multiclass_gained_weapon_proficiencies(selected_class) if advancement_mode == "add_class" else [])
        + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("weapons") or [])
    )
    resulting_tool_proficiencies = _dedupe_preserve_order(
        list((current_definition.proficiencies or {}).get("tools") or [])
        + (
            _extract_multiclass_gained_tool_proficiencies(selected_class, selected_choices)
            if advancement_mode == "add_class"
            else []
        )
        + _extract_feat_tool_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("tools") or [])
    )
    resulting_language_proficiencies = _dedupe_preserve_order(
        list((current_definition.proficiencies or {}).get("languages") or [])
        + (
            _extract_multiclass_gained_language_proficiencies(selected_class, selected_choices)
            if advancement_mode == "add_class"
            else []
        )
        + _extract_feat_language_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("languages") or [])
    )
    resulting_tool_expertise = _apply_feature_expertise_to_tool_proficiencies(
        list((current_definition.proficiencies or {}).get("tool_expertise") or []),
        available_tool_proficiencies=resulting_tool_proficiencies,
        feature_selections=feature_choice_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    attacks = _build_level_one_attacks(
        equipment_catalog=list(current_definition.equipment_catalog or []),
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=_dedupe_preserve_order(
            list((current_definition.proficiencies or {}).get("weapons") or [])
            + (_extract_multiclass_gained_weapon_proficiencies(selected_class) if advancement_mode == "add_class" else [])
            + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
        ),
        selected_choices=combined_selected_choices,
        features=merged_features,
    )
    total_hp_delta = hp_gain + _feat_hit_point_bonus(
        feat_selections,
        current_level=target_level,
    )
    definition = CharacterDefinition(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        name=current_definition.name,
        status=current_definition.status,
        profile=resulting_profile,
        stats=_build_leveled_stats(
            current_definition=current_definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            ability_scores=ability_scores,
            skills=skills,
            proficiency_bonus=proficiency_bonus,
            hp_gain=hp_gain,
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            current_level=target_level,
            equipment_catalog=list(current_definition.equipment_catalog or []),
            features=merged_features,
            item_catalog=item_catalog,
            selected_campaign_option_payloads=selected_campaign_option_payloads,
            resulting_profile=resulting_profile,
        ),
        skills=skills,
        proficiencies={
            "armor": resulting_armor_proficiencies,
            "weapons": resulting_weapon_proficiencies,
            "tools": resulting_tool_proficiencies,
            "languages": resulting_language_proficiencies,
            "tool_expertise": resulting_tool_expertise,
        },
        attacks=attacks,
        features=merged_features,
        spellcasting=_build_level_up_spellcasting(
            current_definition=current_definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feat_selections=feat_selections,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            spell_catalog=spell_catalog,
            target_level=row_target_level,
            feature_entries=new_feature_entries,
            automatic_prepared_feature_entries=new_automatic_prepared_feature_entries,
            selected_campaign_option_payloads=selected_campaign_option_payloads,
            class_row_id=target_class_row_id,
        ),
        equipment_catalog=list(current_definition.equipment_catalog or []),
        reference_notes=dict(current_definition.reference_notes or {}),
        resource_templates=_merge_resource_templates(
            list(current_definition.resource_templates or []),
            derived_resource_templates,
        ),
        source=_build_leveled_source(
            current_definition.source,
            target_level,
            current_level=current_level,
            current_definition=current_definition,
            hp_gain=hp_gain,
            max_hp_delta=total_hp_delta,
            action=advancement_mode,
            class_row_id=target_class_row_id,
            class_ref=_systems_ref_from_entry(selected_class),
            subclass_ref=_systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None,
            row_from_level=row_current_level,
            row_to_level=row_target_level,
        ),
    )
    definition = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=level_up_context.get("systems_service"),
        campaign_page_records=level_up_context.get("campaign_page_records"),
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = _build_leveled_import_metadata(
        campaign_slug=campaign_slug,
        current_definition=current_definition,
        current_import_metadata=current_import_metadata,
        target_level=target_level,
    )
    return definition, import_metadata, total_hp_delta


def build_imported_progression_repair_context(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    *,
    form_values: dict[str, str] | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if _character_source_type(definition) not in IMPORTED_CHARACTER_SOURCE_TYPES:
        raise CharacterBuildError("Only imported character sheets use the progression repair flow.")

    values = {key: str(value) for key, value in dict(form_values or {}).items()}
    current_level = max(_resolve_native_character_level(definition), 1)
    readiness = native_level_up_readiness(
        systems_service,
        campaign_slug,
        definition,
        campaign_page_records=campaign_page_records,
    )
    static_bundle = _build_common_builder_static_bundle(
        systems_service,
        campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    item_catalog = dict(static_bundle.get("item_catalog") or {})
    spell_catalog = dict(static_bundle.get("spell_catalog") or {})

    all_class_options = _list_supported_class_entries(systems_service, campaign_slug)
    shared_slot_class_options = _list_shared_slot_multiclass_class_entries(systems_service, campaign_slug)
    species_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "race"),
        campaign_page_records or [],
        kind="species",
    )
    background_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "background"),
        campaign_page_records or [],
        kind="background",
    )
    feat_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "feat"),
        campaign_page_records or [],
        kind="feat",
    )
    optionalfeature_options = list(_list_campaign_enabled_entries(systems_service, campaign_slug, "optionalfeature"))
    classes = ensure_profile_class_rows(definition.profile)
    selected_class_rows = [
        dict(row or {})
        for row in list(readiness.get("selected_class_rows") or [])
        if isinstance(row, dict)
    ]

    selected_class = readiness.get("selected_class") if isinstance(readiness.get("selected_class"), SystemsEntryRecord) else None
    if selected_class is None and selected_class_rows:
        first_row_class = selected_class_rows[0].get("selected_class")
        if isinstance(first_row_class, SystemsEntryRecord):
            selected_class = first_row_class
    selected_species = readiness.get("selected_species") if isinstance(readiness.get("selected_species"), SystemsEntryRecord) else None
    if selected_species is None:
        selected_species = _resolve_profile_entry(
            species_options,
            definition.profile.get("species_ref"),
            page_ref=definition.profile.get("species_page_ref"),
            fallback_title=str(definition.profile.get("species") or "").strip(),
        )
    selected_background = (
        readiness.get("selected_background") if isinstance(readiness.get("selected_background"), SystemsEntryRecord) else None
    )
    if selected_background is None:
        selected_background = _resolve_profile_entry(
            background_options,
            definition.profile.get("background_ref"),
            page_ref=definition.profile.get("background_page_ref"),
            fallback_title=str(definition.profile.get("background") or "").strip(),
        )

    repair_class_rows: list[dict[str, Any]] = []
    multiclass_context = len(classes) > 1
    for index, class_payload in enumerate(classes, start=1):
        row_id = str(class_payload.get("row_id") or "").strip() or f"class-row-{index}"
        row_context = next(
            (
                dict(candidate)
                for candidate in selected_class_rows
                if str(candidate.get("row_id") or "").strip() == row_id
            ),
            dict(selected_class_rows[index - 1] or {}) if index - 1 < len(selected_class_rows) else {},
        )
        class_entries = shared_slot_class_options if multiclass_context else all_class_options
        row_selected_class = row_context.get("selected_class") if isinstance(row_context.get("selected_class"), SystemsEntryRecord) else None
        if row_selected_class is None:
            row_selected_class = _resolve_profile_entry(
                class_entries,
                dict(class_payload.get("systems_ref") or {}),
                fallback_title=str(class_payload.get("class_name") or "").strip(),
            )
        subclass_entries = (
            _list_shared_slot_multiclass_subclass_options(systems_service, campaign_slug, row_selected_class)
            if multiclass_context
            else _list_subclass_options(systems_service, campaign_slug, row_selected_class)
        ) if row_selected_class is not None else []
        row_selected_subclass = (
            row_context.get("selected_subclass")
            if isinstance(row_context.get("selected_subclass"), SystemsEntryRecord)
            else None
        )
        if row_selected_subclass is None and row_selected_class is not None:
            row_selected_subclass = _resolve_profile_entry(
                subclass_entries,
                dict(class_payload.get("subclass_ref") or {}),
                fallback_title=str(class_payload.get("subclass_name") or "").strip(),
            )
        class_field_name = f"repair_class_slug_{row_id}"
        subclass_field_name = f"repair_subclass_slug_{row_id}"
        values.setdefault(
            class_field_name,
            _entry_selection_value(row_selected_class) if row_selected_class is not None else "",
        )
        values.setdefault(
            subclass_field_name,
            _entry_selection_value(row_selected_subclass) if row_selected_subclass is not None else "",
        )
        repair_class_rows.append(
            {
                "row_id": row_id,
                "row_index": index,
                "row_level": int(class_payload.get("level") or 0),
                "class_name": str(class_payload.get("class_name") or "").strip(),
                "subclass_name": str(class_payload.get("subclass_name") or "").strip(),
                "class_field_name": class_field_name,
                "subclass_field_name": subclass_field_name,
                "class_selected": str(values.get(class_field_name) or "").strip(),
                "subclass_selected": str(values.get(subclass_field_name) or "").strip(),
                "class_options": [_entry_option(entry) for entry in class_entries],
                "subclass_options": [_entry_option(entry) for entry in subclass_entries],
                "class_entries": class_entries,
                "subclass_entries": subclass_entries,
            }
        )

    if repair_class_rows:
        values.setdefault("repair_class_slug", str(repair_class_rows[0].get("class_selected") or "").strip())
        values.setdefault("repair_subclass_slug", str(repair_class_rows[0].get("subclass_selected") or "").strip())
    values.setdefault(
        "repair_species_slug",
        _entry_selection_value(selected_species)
        if species_options
        else "",
    )
    values.setdefault(
        "repair_background_slug",
        _entry_selection_value(selected_background)
        if background_options
        else "",
    )

    feat_row_count = 2 if current_level >= 4 or any(str((feature.get("category") or "")).strip() == "feat" for feature in list(definition.features or [])) else 0
    optionalfeature_row_count = 3 if current_level >= 2 else 0
    feat_rows = []
    for index in range(1, feat_row_count + 1):
        field_name = f"repair_feat_{index}"
        feat_rows.append(
            {
                "index": index,
                "name": field_name,
                "selected": str(values.get(field_name) or "").strip(),
                "options": [_choice_option(_entry_option_label(entry), _entry_selection_value(entry) or entry.slug) for entry in feat_options],
            }
        )
    optionalfeature_rows = []
    for index in range(1, optionalfeature_row_count + 1):
        field_name = f"repair_optionalfeature_{index}"
        optionalfeature_rows.append(
            {
                "index": index,
                "name": field_name,
                "selected": str(values.get(field_name) or "").strip(),
                "options": [_choice_option(entry.title, str(entry.slug or "").strip()) for entry in optionalfeature_options if str(entry.slug or "").strip()],
            }
        )

    spell_rows = []
    for row in _build_imported_spell_repair_rows(
        definition,
        selected_class_rows=selected_class_rows,
        spell_catalog=spell_catalog,
    ):
        field_name = str(row.get("field_name") or "").strip()
        if field_name:
            row = dict(row)
            row["selected"] = str(values.get(field_name) or row.get("selected") or "").strip()
            class_row_field_name = str(row.get("class_row_field_name") or "").strip()
            if class_row_field_name:
                row["class_row_selected"] = str(values.get(class_row_field_name) or row.get("class_row_selected") or "").strip()
                row["options"] = [
                    _choice_option(label, value)
                    for value, label in _imported_spell_mark_options_for_rows(
                        [
                            {
                                "row_id": str(option.get("value") or "").strip(),
                                "spell_mode": str(option.get("spell_mode") or "").strip(),
                            }
                            for option in list(row.get("class_row_options") or [])
                        ],
                        selected_row_id=str(row.get("class_row_selected") or "").strip(),
                        candidate_row_ids=[
                            str(option.get("value") or "").strip()
                            for option in list(row.get("class_row_options") or [])
                            if str(option.get("value") or "").strip()
                        ],
                    )
                ]
            spell_rows.append(row)

    return {
        "values": values,
        "character_name": definition.name,
        "current_level": current_level,
        "readiness": readiness,
        "class_rows": repair_class_rows,
        "class_options": [_entry_option(entry) for entry in all_class_options],
        "species_options": [_entry_option(entry) for entry in species_options],
        "background_options": [_entry_option(entry) for entry in background_options],
        "subclass_options": [_entry_option(entry) for entry in (repair_class_rows[0].get("subclass_entries") if repair_class_rows else [])],
        "feat_rows": feat_rows,
        "optionalfeature_rows": optionalfeature_rows,
        "spell_rows": spell_rows,
        "class_entries": all_class_options,
        "species_entries": species_options,
        "background_entries": background_options,
        "subclass_entries": list(repair_class_rows[0].get("subclass_entries") or []) if repair_class_rows else [],
        "feat_entries": feat_options,
        "optionalfeature_entries": optionalfeature_options,
        "systems_service": systems_service,
        "campaign_page_records": list(campaign_page_records or []),
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
    }


def apply_imported_progression_repairs(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    repair_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    if _character_source_type(current_definition) not in IMPORTED_CHARACTER_SOURCE_TYPES:
        raise CharacterBuildError("Only imported character sheets can use progression repair.")

    values = {key: str(value) for key, value in dict(form_values or {}).items()}
    class_entries = list(repair_context.get("class_entries") or [])
    species_entries = list(repair_context.get("species_entries") or [])
    background_entries = list(repair_context.get("background_entries") or [])
    repair_class_rows = [dict(row or {}) for row in list(repair_context.get("class_rows") or []) if isinstance(row, dict)]
    feat_entries = list(repair_context.get("feat_entries") or [])
    optionalfeature_entries = list(repair_context.get("optionalfeature_entries") or [])
    spell_catalog = dict(repair_context.get("spell_catalog") or {})

    selected_species = _resolve_selected_entry(species_entries, values.get("repair_species_slug", ""))
    selected_background = _resolve_selected_entry(background_entries, values.get("repair_background_slug", ""))

    resolved_class_rows: list[dict[str, Any]] = []
    missing_refs = []
    for row in repair_class_rows:
        class_field_name = str(row.get("class_field_name") or "").strip()
        subclass_field_name = str(row.get("subclass_field_name") or "").strip()
        row_class_entries = list(row.get("class_entries") or class_entries)
        row_subclass_entries = list(row.get("subclass_entries") or [])
        selected_row_class = _resolve_selected_entry(row_class_entries, values.get(class_field_name, ""))
        selected_row_subclass = _resolve_selected_entry(row_subclass_entries, values.get(subclass_field_name, ""))
        if selected_row_class is None:
            missing_refs.append("class")
            continue
        resolved_class_rows.append(
            {
                "row_id": str(row.get("row_id") or "").strip(),
                "row_level": int(row.get("row_level") or 0),
                "selected_class": selected_row_class,
                "selected_subclass": selected_row_subclass,
            }
        )

    if selected_species is None:
        missing_refs.append("species")
    if selected_background is None:
        missing_refs.append("background")
    if missing_refs:
        joined = ", ".join(_dedupe_preserve_order(missing_refs))
        raise CharacterBuildError(f"Choose the missing {joined} links before saving progression repair.")
    if len(resolved_class_rows) != len(repair_class_rows):
        raise CharacterBuildError("Choose the missing class links before saving progression repair.")

    seen_row_identities: set[tuple[str, str]] = set()
    for row in resolved_class_rows:
        selected_row_class = row.get("selected_class")
        selected_row_subclass = row.get("selected_subclass")
        row_identity = (
            str(selected_row_class.slug if isinstance(selected_row_class, SystemsEntryRecord) else "").strip(),
            str(selected_row_subclass.slug if isinstance(selected_row_subclass, SystemsEntryRecord) else "").strip(),
        )
        if row_identity in seen_row_identities:
            raise CharacterBuildError("Choose distinct class/subclass repairs for each class row before saving.")
        seen_row_identities.add(row_identity)

    selected_class = resolved_class_rows[0]["selected_class"] if resolved_class_rows else None
    selected_subclass = resolved_class_rows[0]["selected_subclass"] if resolved_class_rows else None

    ability_scores = _ability_scores_from_definition(current_definition)
    current_level = max(_resolve_native_character_level(current_definition), 1)

    repaired_feature_entries: list[dict[str, Any]] = []
    for row in list(repair_context.get("feat_rows") or []):
        selected_value = str(values.get(str(row.get("name") or "").strip()) or "").strip()
        selected_entry = _resolve_selected_entry(feat_entries, selected_value)
        if selected_entry is None:
            continue
        repaired_feature_entries.append(
            {
                "kind": "feat",
                "slug": str(selected_entry.slug or "").strip(),
                "title": selected_entry.title,
                "label": selected_entry.title,
                "systems_entry": selected_entry,
                "page_ref": _entry_page_ref(selected_entry),
                "campaign_option": _entry_campaign_option(selected_entry) or None,
            }
        )
    optionalfeature_lookup = {
        str(entry.slug or "").strip(): entry
        for entry in optionalfeature_entries
        if str(entry.slug or "").strip()
    }
    for row in list(repair_context.get("optionalfeature_rows") or []):
        selected_value = str(values.get(str(row.get("name") or "").strip()) or "").strip()
        selected_entry = optionalfeature_lookup.get(selected_value)
        if selected_entry is None:
            continue
        repaired_feature_entries.append(
            {
                "kind": "optionalfeature",
                "slug": str(selected_entry.slug or "").strip(),
                "label": selected_entry.title,
                "systems_entry": selected_entry,
                "page_ref": _entry_page_ref(selected_entry),
                "campaign_option": _entry_campaign_option(selected_entry) or None,
            }
        )

    profile = dict(current_definition.profile or {})
    classes = ensure_profile_class_rows(profile)
    updated_classes: list[dict[str, Any]] = []
    for index, resolved_row in enumerate(resolved_class_rows):
        existing_row = dict(classes[index] or {}) if index < len(classes) else {}
        selected_row_class = resolved_row["selected_class"]
        selected_row_subclass = resolved_row.get("selected_subclass")
        class_payload = dict(existing_row)
        class_payload["row_id"] = str(resolved_row.get("row_id") or class_payload.get("row_id") or f"class-row-{index + 1}").strip()
        class_payload["class_name"] = selected_row_class.title
        class_payload["level"] = int(resolved_row.get("row_level") or class_payload.get("level") or current_level)
        class_payload["systems_ref"] = _systems_ref_from_entry(selected_row_class)
        class_payload["subclass_name"] = selected_row_subclass.title if selected_row_subclass is not None else ""
        if selected_row_subclass is not None:
            class_payload["subclass_ref"] = _systems_ref_from_entry(selected_row_subclass)
        else:
            class_payload.pop("subclass_ref", None)
        updated_classes.append(class_payload)
    classes = updated_classes
    profile["classes"] = classes
    profile["class_ref"] = _systems_ref_from_entry(selected_class)
    profile["subclass_ref"] = _systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None
    profile = sync_profile_class_summary(profile)

    species_page_ref = _entry_page_ref(selected_species)
    profile["species"] = selected_species.title
    profile["species_ref"] = None if species_page_ref else _systems_ref_from_entry(selected_species)
    profile["species_page_ref"] = species_page_ref or None

    background_page_ref = _entry_page_ref(selected_background)
    profile["background"] = selected_background.title
    profile["background_ref"] = None if background_page_ref else _systems_ref_from_entry(selected_background)
    profile["background_page_ref"] = background_page_ref or None

    repaired_features, _unused_templates = _build_feature_payloads(
        repaired_feature_entries,
        ability_scores=ability_scores,
        current_level=current_level,
    )
    merged_features = _merge_feature_payloads(list(current_definition.features or []), repaired_features)
    merged_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        merged_features,
        ability_scores=ability_scores,
        current_level=current_level,
        class_row_levels=_profile_class_row_level_map(profile),
    )

    spellcasting = dict(current_definition.spellcasting or {})
    repaired_spells = [dict(payload or {}) for payload in list(spellcasting.get("spells") or [])]
    for row in list(repair_context.get("spell_rows") or []):
        field_name = str(row.get("field_name") or "").strip()
        if not field_name:
            continue
        class_row_field_name = str(row.get("class_row_field_name") or "").strip()
        selected_row_id = str(
            values.get(class_row_field_name)
            or row.get("class_row_selected")
            or ""
        ).strip()
        selected_mark = str(values.get(field_name) or "").strip()
        spell_index = max(int(row.get("index") or 0) - 1, 0)
        if spell_index >= len(repaired_spells):
            continue
        row_options = {
            str(option.get("value") or "").strip(): dict(option or {})
            for option in list(row.get("class_row_options") or [])
            if str(option.get("value") or "").strip()
        }
        if row_options and not selected_row_id:
            raise CharacterBuildError(f"Choose which class row owns {row.get('name') or 'this spell'} before saving progression repair.")
        if row_options and selected_row_id not in row_options:
            raise CharacterBuildError(f"Choose a valid class row for {row.get('name') or 'this spell'}.")
        selected_row_mode = str(
            row_options.get(selected_row_id, {}).get("spell_mode")
            or row.get("selected_row_mode")
            or ""
        ).strip()
        if not selected_mark:
            raise CharacterBuildError(f"Choose a spell mark for {row.get('name') or 'this spell'} before saving progression repair.")
        if not _spell_mark_is_valid_for_mode(selected_mark, selected_row_mode):
            raise CharacterBuildError(f"{row.get('name') or 'This spell'} needs a mark that matches the selected class row.")
        if selected_row_id:
            repaired_spells[spell_index]["class_row_id"] = selected_row_id
        repaired_spells[spell_index]["mark"] = selected_mark
    spellcasting["spells"] = _apply_automatic_prepared_spell_flags(
        repaired_spells,
        campaign_slug=campaign_slug,
        systems_service=repair_context.get("systems_service"),
        resolved_class_rows=resolved_class_rows,
        spell_catalog=spell_catalog,
        feature_entries=[
            {"entry": feature_entry.get("systems_entry"), "campaign_option": feature_entry.get("campaign_option")}
            for feature_entry in repaired_feature_entries
            if feature_entry.get("systems_entry") or feature_entry.get("campaign_option")
        ],
    )

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["profile"] = profile
    payload["features"] = merged_features
    payload["resource_templates"] = _merge_resource_templates(
        list(current_definition.resource_templates or []),
        derived_resource_templates,
    )
    payload["spellcasting"] = spellcasting
    payload["source"] = _with_native_progression_event(
        _seed_source_hp_baseline_from_definition(
            current_definition.source,
            current_definition,
            baseline_repaired=True,
        ),
        kind="repair",
        target_level=current_level,
        baseline_repaired=True,
        action="repair",
    )

    definition = normalize_definition_to_native_model(
        CharacterDefinition.from_dict(payload),
        item_catalog=dict(repair_context.get("item_catalog") or {}),
        spell_catalog=spell_catalog,
        systems_service=repair_context.get("systems_service"),
        campaign_page_records=list(repair_context.get("campaign_page_records") or []),
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=str(
            current_import_metadata.source_path
            or (current_definition.source or {}).get("source_path")
            or f"managed://{campaign_slug}/{current_definition.character_slug}"
        ),
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="managed",
        warnings=list(current_import_metadata.warnings or []),
    )
    return definition, import_metadata
