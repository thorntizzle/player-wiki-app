from __future__ import annotations

import re
from typing import Any, Callable

from .character_campaign_options import collect_campaign_option_spell_grants
from .character_builder_constants import *  # noqa: F403
from .character_builder_foundation import (
    _choice_option,
    _entry_campaign_option,
    _entry_option_slug,
    _entry_option_source_id,
    _entry_page_ref,
    _spellcasting_mode_for_class,
)
from .character_models import CharacterDefinition
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_assign_spell_payload_class_rows",
    "_derive_spell_source_rows",
    "_feat_spell_choice_field_name",
    "_feat_spell_block_options",
    "_structured_spell_manager_option_value",
    "_structured_spell_manager_source_options",
    "_selected_structured_spell_manager_config",
    "_structured_spell_manager_source_row_payload",
    "_structured_spell_manager_payload",
    "_build_feat_spell_source_field",
    "_selected_feat_additional_spell_blocks",
    "_supported_feat_spell_config",
    "_supported_feat_spell_source_options",
    "_selected_supported_feat_spell_config",
    "_supported_feat_spell_source_row_payload",
    "_supported_feat_spell_automatic_grants",
    "_supported_feat_spell_manager_payload",
    "_build_spell_choice_fields",
    "_build_level_one_spell_support_replacement_fields",
    "_build_level_up_spell_choice_fields",
    "_build_level_up_known_spell_replacement_fields",
    "_build_spell_options_from_payload_keys",
    "_build_level_up_spell_payloads",
    "_level_up_slot_progression_for_class",
    "_build_level_one_spell_payloads",
    "_spell_payload_key",
    "_spell_payload_class_row_id",
    "_spell_payload_source_row_id",
    "_spell_payload_management_row",
    "_spell_payload_management_row_id",
    "_spell_payload_management_scope_key",
    "_spell_access_payload",
    "_spell_access_badge_label",
    "_spell_source_support_payload",
    "_merge_spell_support_kwargs",
    "_spell_support_support_kwargs",
    "_spell_payload_support_kwargs",
    "_apply_spell_payload_support_metadata",
    "_spell_payload_map_key",
    "_spell_lookup_key",
    "_spell_selection_values_by_mark",
    "_selected_additional_known_spell_values",
    "_selected_form_spell_values_by_field_prefix",
    "_values_from_selected_choices",
    "_selected_feat_spell_field_values",
    "_apply_selected_feat_spell_fields_to_payloads",
    "_apply_selected_campaign_option_spells_to_payloads",
    "_build_additional_known_spell_choice_fields",
    "_build_spell_support_choice_fields",
    "_build_spell_support_replacement_fields",
    "_build_spell_support_existing_options_from_replacement_spec",
    "_build_spell_support_options_from_spec",
    "_build_spell_options_from_existing_payloads",
    "_spell_payload_matches_replacement_filter",
    "_build_spell_options_from_references",
    "_apply_spell_support_grants_to_payloads",
    "_apply_selected_spell_support_fields_to_payloads",
    "_apply_selected_spell_support_replacements_to_payloads",
    "_build_feat_spell_choice_fields",
    "_build_feat_spell_choice_fields_for_selection",
    "_build_feat_spell_fields_from_spec",
    "_campaign_spell_manager_choice_field_name",
    "_build_structured_spell_choice_fields_from_spec",
    "_feature_entry_spell_manager_config",
    "_campaign_spell_manager_field_prefix",
    "_campaign_spell_manager_source_field_name",
    "_campaign_feature_spell_manager_entries",
    "_selected_campaign_feature_spell_manager_config",
    "_campaign_feature_spell_manager_source_row_payload",
    "_build_campaign_feature_spell_manager_fields",
    "_automatic_campaign_feature_spell_manager_grants",
    "_apply_campaign_feature_spell_manager_payloads",
    "_apply_selected_campaign_feature_spell_manager_fields_to_payloads",
    "_iter_unlocked_additional_spell_values",
    "_extract_feat_known_choice_specs",
    "_extract_feat_prepared_choice_specs",
    "_extract_feat_innate_choice_specs",
    "_extract_additional_known_choice_specs",
    "_extract_choose_additional_spell_specs",
    "_build_additional_spell_filter_options",
    "_parse_additional_spell_filter",
    "_additional_spell_filter_requires_ritual",
    "_spell_entry_matches_additional_filter",
    "_spell_options_are_cantrips",
    "_spell_entry_level",
    "_build_spell_options_from_titles",
    "_expanded_spell_titles_for_level",
    "_extract_expanded_additional_spell_values",
    "_additional_spell_metadata_entries",
    "_spell_support_metadata_entries",
    "_spell_metadata_value",
    "_spell_flag_is_truthy",
    "_raw_spell_grant_is_always_prepared",
    "_spell_payload_has_legacy_always_prepared_source_label",
    "_spell_payload_is_always_prepared",
    "_spell_mark_tokens",
    "_canonicalize_legacy_spell_mark",
    "_spell_payload_spell_level",
    "_canonicalize_legacy_spell_payload_marks",
    "_collect_entry_body_text_fragments",
    "_collect_entry_body_tables",
    "_normalized_entry_body_text",
    "_entry_body_has_self_contained_always_prepared_context",
    "_entry_body_has_domain_spell_grant_context",
    "_feature_entries_have_domain_spell_always_prepared_context",
    "_extract_spell_titles_from_table_cell",
    "_extract_prepared_spells_from_supported_table",
    "_inferred_always_prepared_additional_spell_blocks",
    "_spell_support_choice_field_name",
    "_spell_support_replacement_field_name",
    "_automatic_spell_support_grants",
    "_automatic_spell_support_lookup_keys",
    "_extract_spell_support_grants",
    "_extract_spell_support_grants_from_value",
    "_dedupe_spell_support_grants",
    "_extract_spell_support_choice_specs",
    "_extract_spell_support_choice_specs_from_value",
    "_extract_spell_support_replacement_specs",
    "_extract_spell_support_replacement_specs_from_value",
    "_automatic_feat_known_spell_values",
    "_automatic_feat_prepared_spell_values",
    "_automatic_feat_innate_spell_values",
    "_automatic_known_spell_values",
    "_automatic_known_spell_lookup_keys",
    "_extract_known_additional_spell_values",
    "_automatic_prepared_spell_values",
    "_automatic_prepared_spell_lookup_keys",
    "_automatic_innate_spell_values",
    "_extract_prepared_additional_spell_values",
    "_extract_innate_additional_spell_values",
    "_format_innate_spell_mark",
    "_dedupe_innate_spell_values",
    "_parse_additional_spell_unlock_level",
    "_flatten_additional_spell_values",
    "_resolve_additional_spell_option_titles",
    "_normalize_additional_spell_reference",
    "_summarize_level_up_spell_choices",
    "_add_spell_to_payloads",
    "_add_bonus_known_spell_to_payloads",
    "_resolve_spell_entry",
    "_build_spell_payload",
    "_merge_spell_mark",
    "_MERGE_NAME_ALIASES",
    "_merge_name_candidates",
    "_normalize_spell_payloads",
    "_format_spell_casting_time",
    "_format_spell_range",
    "_format_spell_duration",
    "_format_spell_components",
]


def _builder_dependency(name: str):
    from . import character_builder as character_builder_module

    return getattr(character_builder_module, name)

def _ability_modifier(*args: Any, **kwargs: Any):
    return _builder_dependency("_ability_modifier")(*args, **kwargs)

def _build_spell_options_for_class_level(*args: Any, **kwargs: Any):
    return _builder_dependency("_build_spell_options_for_class_level")(*args, **kwargs)

def _build_spell_options_for_class_levels(*args: Any, **kwargs: Any):
    return _builder_dependency("_build_spell_options_for_class_levels")(*args, **kwargs)

def _clean_embedded_text(*args: Any, **kwargs: Any):
    return _builder_dependency("_clean_embedded_text")(*args, **kwargs)

def _coerce_ability_scores(*args: Any, **kwargs: Any):
    return _builder_dependency("_coerce_ability_scores")(*args, **kwargs)

def _dedupe_campaign_spell_sources(*args: Any, **kwargs: Any):
    return _builder_dependency("_dedupe_campaign_spell_sources")(*args, **kwargs)

def _dedupe_preserve_order(*args: Any, **kwargs: Any):
    return _builder_dependency("_dedupe_preserve_order")(*args, **kwargs)

def _feat_field_name(*args: Any, **kwargs: Any):
    return _builder_dependency("_feat_field_name")(*args, **kwargs)

def _humanize_words(*args: Any, **kwargs: Any):
    return _builder_dependency("_humanize_words")(*args, **kwargs)

def _load_phb_level_one_spell_lists(*args: Any, **kwargs: Any):
    return _builder_dependency("_load_phb_level_one_spell_lists")(*args, **kwargs)

def _normalize_explicit_link_identity(*args: Any, **kwargs: Any):
    return _builder_dependency("_normalize_explicit_link_identity")(*args, **kwargs)

def _normalize_page_ref_payload(*args: Any, **kwargs: Any):
    return _builder_dependency("_normalize_page_ref_payload")(*args, **kwargs)

def _prepared_spell_count_for_level(*args: Any, **kwargs: Any):
    return _builder_dependency("_prepared_spell_count_for_level")(*args, **kwargs)

def _prepared_spell_formula_ability_key(*args: Any, **kwargs: Any):
    return _builder_dependency("_prepared_spell_formula_ability_key")(*args, **kwargs)

def _resolve_builder_choices(*args: Any, **kwargs: Any):
    return _builder_dependency("_resolve_builder_choices")(*args, **kwargs)

def _selected_campaign_option_payloads(*args: Any, **kwargs: Any):
    return _builder_dependency("_selected_campaign_option_payloads")(*args, **kwargs)

def _spell_list_class_name_for_class(*args: Any, **kwargs: Any):
    return _builder_dependency("_spell_list_class_name_for_class")(*args, **kwargs)

def _spell_progression_value(*args: Any, **kwargs: Any):
    return _builder_dependency("_spell_progression_value")(*args, **kwargs)

def _spell_slot_progression_for_class_level(*args: Any, **kwargs: Any):
    return _builder_dependency("_spell_slot_progression_for_class_level")(*args, **kwargs)

def _systems_ref_from_entry(*args: Any, **kwargs: Any):
    return _builder_dependency("_systems_ref_from_entry")(*args, **kwargs)

def _assign_spell_payload_class_rows(
    spell_payloads: list[dict[str, Any]],
    *,
    spellcasting_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_rows = [dict(row or {}) for row in list(spellcasting_rows or []) if dict(row or {})]
    if not normalized_rows:
        return _normalize_spell_payloads(spell_payloads)
    if len(normalized_rows) == 1:
        default_row_id = str(normalized_rows[0].get("class_row_id") or "").strip()
        if default_row_id:
            assigned_payloads: list[dict[str, Any]] = []
            for payload in list(spell_payloads or []):
                spell_payload = dict(payload or {})
                if (
                    not str(spell_payload.get("class_row_id") or "").strip()
                    and not _spell_payload_source_row_id(spell_payload)
                ):
                    spell_payload["class_row_id"] = default_row_id
                assigned_payloads.append(spell_payload)
            return _normalize_spell_payloads(assigned_payloads)
    return _normalize_spell_payloads(spell_payloads)


def _derive_spell_source_rows(
    spell_payloads: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> list[dict[str, Any]]:
    source_rows: list[dict[str, Any]] = []
    index_by_id: dict[str, int] = {}
    for spell_payload in list(spell_payloads or []):
        payload = dict(spell_payload or {})
        source_row_id = _spell_payload_source_row_id(payload)
        if not source_row_id:
            continue
        ability_key = _prepared_spell_formula_ability_key(str(payload.get("spell_source_ability_key") or "").strip())
        modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) if ability_key else 0
        row_payload = {
            "source_row_id": source_row_id,
            "source_row_kind": str(payload.get("spell_source_row_kind") or "source").strip() or "source",
            "title": (
                str(payload.get("spell_source_row_title") or "").strip()
                or str(payload.get("grant_source_label") or "").strip()
                or "Feature spells"
            ),
            "spell_mode": str(payload.get("spell_source_mode") or "").strip(),
            "spell_list_class_name": str(payload.get("spell_source_spell_list_class_name") or "").strip(),
            "spellcasting_ability": str(ABILITY_LABELS.get(ability_key, "")).strip(),
            "spell_save_dc": 8 + proficiency_bonus + modifier if ability_key else None,
            "spell_attack_bonus": proficiency_bonus + modifier if ability_key else None,
        }
        existing_index = index_by_id.get(source_row_id)
        if existing_index is None:
            index_by_id[source_row_id] = len(source_rows)
            source_rows.append(row_payload)
            continue
        existing_payload = source_rows[existing_index]
        for key in (
            "source_row_kind",
            "title",
            "spell_mode",
            "spell_list_class_name",
            "spellcasting_ability",
            "spell_save_dc",
            "spell_attack_bonus",
        ):
            if existing_payload.get(key) in {"", None} and row_payload.get(key) not in {"", None}:
                existing_payload[key] = row_payload.get(key)
    return source_rows


def _feat_spell_choice_field_name(instance_key: str, category: str, spec_index: int, choice_index: int) -> str:
    return f"feat_{instance_key}_{category}_{spec_index}_{choice_index}"


def _feat_spell_block_options(feat_entry: SystemsEntryRecord) -> list[dict[str, str]]:
    metadata = dict(feat_entry.metadata or {})
    blocks = [dict(block) for block in list(metadata.get("additional_spells") or []) if isinstance(block, dict)]
    if len(blocks) <= 1:
        return []
    labels: list[str] = []
    for index, block in enumerate(blocks, start=1):
        label = _clean_embedded_text(str(block.get("name") or "").strip()) or f"Spell List {index}"
        labels.append(label)
    if len(set(normalize_lookup(label) for label in labels if label)) != len(labels):
        return []
    return [_choice_option(label, str(index)) for index, label in enumerate(labels, start=1)]


def _structured_spell_manager_option_value(option: dict[str, Any], fallback_index: int) -> str:
    return str(
        option.get("value")
        or option.get("class_name")
        or option.get("source_title")
        or fallback_index
    ).strip()


def _structured_spell_manager_source_options(
    support_config: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for index, raw_option in enumerate(list(support_config.get("source_options") or []), start=1):
        option = dict(raw_option or {})
        value = _structured_spell_manager_option_value(option, index)
        label = str(
            option.get("label")
            or option.get("source_title")
            or option.get("class_name")
            or f"Spell List {index}"
        ).strip()
        if not value or not label:
            continue
        options.append(_choice_option(label, value))
    return options


def _selected_structured_spell_manager_config(
    *,
    support_config: dict[str, Any],
    values: dict[str, str],
    field_name: str,
) -> dict[str, Any]:
    source_options = [dict(option or {}) for option in list(support_config.get("source_options") or [])]
    if not source_options:
        return dict(support_config)
    selected_value = str(values.get(field_name) or "").strip()
    if not selected_value:
        return {}
    selected_option = next(
        (
            option
            for index, option in enumerate(source_options, start=1)
            if selected_value == _structured_spell_manager_option_value(option, index)
        ),
        None,
    )
    if selected_option is None:
        return {}
    return {
        **dict(support_config or {}),
        **selected_option,
    }


def _structured_spell_manager_source_row_payload(
    *,
    source_row_id_prefix: str,
    source_key: str,
    instance_key: str,
    support_config: dict[str, Any],
    source_title: str,
    default_row_kind: str,
) -> dict[str, str]:
    ability_key = _prepared_spell_formula_ability_key(str(support_config.get("ability_key") or "").strip())
    row_slug = slugify(source_key or source_title or default_row_kind or "spell-source")
    instance_slug = slugify(instance_key or row_slug)
    return {
        "spell_source_row_id": f"{source_row_id_prefix}:{row_slug}:{instance_slug}",
        "spell_source_row_kind": str(
            support_config.get("source_row_kind")
            or default_row_kind
            or "source"
        ).strip()
        or "source",
        "spell_source_row_title": source_title,
        "spell_source_ability_key": ability_key,
        "spell_source_mode": str(
            support_config.get("manager_mode")
            or support_config.get("mode")
            or ""
        ).strip(),
        "spell_source_spell_list_class_name": str(
            support_config.get("spell_list_class_name")
            or support_config.get("class_name")
            or ""
        ).strip(),
        "grant_source_label": source_title,
    }


def _structured_spell_manager_payload(
    *,
    support_config: dict[str, Any],
    source_row_payload: dict[str, str],
) -> dict[str, Any] | None:
    manager_mode = str(
        support_config.get("manager_mode")
        or support_config.get("mode")
        or ""
    ).strip()
    if not manager_mode:
        return None
    ability_key = _prepared_spell_formula_ability_key(str(support_config.get("ability_key") or "").strip())
    ability_label = str(ABILITY_LABELS.get(ability_key, "")).strip()
    return {
        "source_row_id": str(source_row_payload.get("spell_source_row_id") or "").strip(),
        "source_row_kind": str(source_row_payload.get("spell_source_row_kind") or "source").strip() or "source",
        "title": str(source_row_payload.get("spell_source_row_title") or "").strip(),
        "mode": manager_mode,
        "spell_list_class_name": str(
            support_config.get("spell_list_class_name")
            or support_config.get("class_name")
            or ""
        ).strip(),
        "spellcasting_ability": ability_label,
        "spellcasting_ability_key": ability_key,
        "max_spell_level_formula": str(support_config.get("max_spell_level_formula") or "").strip(),
    }


def _build_feat_spell_source_field(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any] | None:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return None
    support_config = _supported_feat_spell_config(selection)
    if support_config:
        options = _structured_spell_manager_source_options(support_config)
        if not options:
            return None
        field_name = _feat_field_name(instance_key, "spell_source", 1)
        return {
            "name": field_name,
            "label": str(support_config.get("source_field_label") or f"{feat_entry.title} Spell List").strip(),
            "help_text": str(
                support_config.get("source_field_help_text")
                or f"Choose the spell list used by {feat_entry.title}."
            ).strip(),
            "options": options,
            "selected": str(values.get(field_name) or "").strip(),
            "group_key": field_name,
            "kind": "feat_spell_source",
        }
    options = _feat_spell_block_options(feat_entry)
    if not options:
        return None
    field_name = _feat_field_name(instance_key, "spell_source", 1)
    return {
        "name": field_name,
        "label": f"{feat_entry.title} Spell List",
        "help_text": f"Choose the spell list used by {feat_entry.title}.",
        "options": options,
        "selected": str(values.get(field_name) or "").strip(),
        "group_key": field_name,
        "kind": "feat_spell_source",
    }


def _selected_feat_additional_spell_blocks(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []
    if _supported_feat_spell_config(selection):
        return []
    metadata = dict(feat_entry.metadata or {})
    blocks = [dict(block) for block in list(metadata.get("additional_spells") or []) if isinstance(block, dict)]
    options = _feat_spell_block_options(feat_entry)
    if not options:
        return blocks
    field_name = _feat_field_name(instance_key, "spell_source", 1)
    selected_value = str(values.get(field_name) or "").strip()
    if not selected_value:
        return []
    try:
        selected_index = int(selected_value)
    except ValueError:
        return []
    if 1 <= selected_index <= len(blocks):
        return [blocks[selected_index - 1]]
    return []


def _supported_feat_spell_config(selection: dict[str, Any]) -> dict[str, Any]:
    campaign_option = dict(selection.get("campaign_option") or {})
    structured_spell_manager = dict(campaign_option.get("spell_manager") or {})
    if structured_spell_manager:
        return structured_spell_manager
    feat_entry = selection.get("entry") or selection.get("systems_entry")
    feat_source_id = ""
    feat_slug = ""
    if isinstance(feat_entry, SystemsEntryRecord):
        feat_source_id = str(feat_entry.source_id or "").strip()
        feat_slug = str(feat_entry.slug or "").strip()
    else:
        feat_source_id = str(
            selection.get("source_id")
            or _entry_option_source_id(feat_entry)
            or ""
        ).strip()
        feat_slug = str(
            selection.get("slug")
            or selection.get("selection_value")
            or _entry_option_slug(feat_entry)
            or ""
        ).strip()
        if feat_slug.startswith(SYSTEMS_OPTION_PREFIX):
            feat_slug = feat_slug[len(SYSTEMS_OPTION_PREFIX):]
    if not feat_slug:
        return {}
    return dict(
        SUPPORTED_FREE_CAST_FEAT_SPELLS.get(
            (
                normalize_lookup(feat_source_id),
                normalize_lookup(feat_slug),
            ),
            {},
        )
    )


def _supported_feat_spell_source_options(
    support_config: dict[str, Any],
) -> list[dict[str, str]]:
    return _structured_spell_manager_source_options(support_config)


def _selected_supported_feat_spell_config(
    *,
    selection: dict[str, Any],
    support_config: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any]:
    instance_key = str(selection.get("instance_key") or "").strip()
    if not instance_key:
        return {}
    return _selected_structured_spell_manager_config(
        support_config=support_config,
        values=values,
        field_name=_feat_field_name(instance_key, "spell_source", 1),
    )


def _supported_feat_spell_source_row_payload(
    *,
    selection: dict[str, Any],
    support_config: dict[str, Any],
) -> dict[str, str]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    feat_slug = ""
    if isinstance(feat_entry, SystemsEntryRecord):
        feat_slug = str(feat_entry.slug or "").strip()
    if not feat_slug:
        feat_slug = str(selection.get("slug") or selection.get("selection_value") or "").strip()
    source_title = str(
        support_config.get("source_title")
        or (feat_entry.title if isinstance(feat_entry, SystemsEntryRecord) else selection.get("label") or "")
    ).strip()
    return _structured_spell_manager_source_row_payload(
        source_row_id_prefix="feat-spell-source",
        source_key=feat_slug or source_title or "feat",
        instance_key=instance_key or feat_slug or source_title,
        support_config=support_config,
        source_title=source_title,
        default_row_kind="feat",
    )


def _supported_feat_spell_automatic_grants(
    *,
    feat_selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for selection in feat_selections:
        support_config = _supported_feat_spell_config(selection)
        if not support_config:
            continue
        resolved_support_config = _selected_supported_feat_spell_config(
            selection=selection,
            support_config=support_config,
            values={},
        )
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            continue
        source_row_payload = _supported_feat_spell_source_row_payload(
            selection=selection,
            support_config=resolved_support_config or support_config,
        )
        source_row_id = str(source_row_payload.get("spell_source_row_id") or "").strip()
        for raw_grant in list((resolved_support_config or support_config).get("automatic_grants") or []):
            grant = dict(raw_grant or {})
            spell_name = str(grant.get("spell") or "").strip()
            if not spell_name:
                continue
            marker = (source_row_id, normalize_lookup(spell_name))
            if marker in seen:
                continue
            seen.add(marker)
            grants.append(
                {
                    "name": spell_name,
                    "prefer_known_mark": bool(grant.get("prefer_known_mark", True)),
                    **source_row_payload,
                    "spell_access_type": str(grant.get("access_type") or "").strip(),
                    "spell_access_uses": grant.get("access_uses"),
                    "spell_access_reset_on": str(grant.get("access_reset_on") or "").strip(),
                }
            )
    return grants


def _supported_feat_spell_manager_payload(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any] | None:
    support_config = _supported_feat_spell_config(selection)
    if not support_config:
        return None
    resolved_support_config = _selected_supported_feat_spell_config(
        selection=selection,
        support_config=support_config,
        values=values,
    )
    if list(support_config.get("source_options") or []) and not resolved_support_config:
        return None
    effective_support_config = resolved_support_config or support_config
    source_row_payload = _supported_feat_spell_source_row_payload(
        selection=selection,
        support_config=effective_support_config,
    )
    return _structured_spell_manager_payload(
        support_config=effective_support_config,
        source_row_payload=source_row_payload,
    )


def _build_spell_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    feat_spell_fields = _build_feat_spell_choice_fields(
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        target_level=1,
    )
    campaign_spell_manager_fields = _build_campaign_feature_spell_manager_fields(
        feature_entries=feature_entries,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix_base="campaign_spell_manager",
    )
    spell_support_fields = _build_spell_support_choice_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        group_key_prefix="spell_support",
        feature_entries=feature_entries,
    )
    if selected_class is None:
        return spell_support_fields + campaign_spell_manager_fields + feat_spell_fields
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=1,
    )
    cantrip_count = _spell_progression_value(
        class_name,
        "cantrip_progression",
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    spellbook_count = _spell_progression_value(
        class_name,
        "spells_known_progression_fixed",
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    level_one_count = _spell_progression_value(
        class_name,
        "spells_known_progression",
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    prepared_count = _prepared_spell_count_for_level(
        class_name,
        _coerce_ability_scores(values),
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    has_level_one_spellcasting = bool(slot_progression) or cantrip_count > 0 or level_one_count > 0 or spellbook_count > 0
    fields: list[dict[str, Any]] = []
    if spell_mode and has_level_one_spellcasting:
        automatic_known_lookup_keys = _automatic_known_spell_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        automatic_spell_support_lookup_keys = _automatic_spell_support_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        automatic_campaign_spell_manager_lookup_keys = {
            _spell_lookup_key(str(spell_grant.get("name") or "").strip(), spell_catalog)
            for spell_grant in _automatic_campaign_feature_spell_manager_grants(
                feature_entries=feature_entries,
                values=values,
                field_prefix_base="campaign_spell_manager",
            )
            if _spell_lookup_key(str(spell_grant.get("name") or "").strip(), spell_catalog)
        }
        selected_bonus_known_values = _selected_form_spell_values_by_field_prefix(values, prefix="bonus_spell_known_")

        cantrip_options = [
            option
            for option in _build_spell_options_for_class_level(
                class_name,
                "0",
                spell_catalog,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=1,
                feature_entries=feature_entries,
            )
            if str(option.get("value") or "").strip()
            not in (
                automatic_known_lookup_keys
                | automatic_spell_support_lookup_keys
                | automatic_campaign_spell_manager_lookup_keys
                | selected_bonus_known_values
            )
        ]
        if cantrip_options:
            for index in range(cantrip_count):
                field_name = f"spell_cantrip_{index + 1}"
                fields.append(
                    {
                        "name": field_name,
                        "label": f"Cantrip {index + 1}",
                        "help_text": f"Choose a {class_name} cantrip.",
                        "options": cantrip_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": "spell_cantrips",
                        "kind": "spell",
                    }
                )

        fields.extend(
            _build_additional_known_spell_choice_fields(
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                spell_catalog=spell_catalog,
                target_level=1,
                values=values,
                field_prefix="bonus_spell_known",
                group_key_prefix="bonus_spell_known",
                feature_entries=feature_entries,
            )
        )
        fields.extend(spell_support_fields)
        fields.extend(campaign_spell_manager_fields)
        level_one_options = [
            option
            for option in _build_spell_options_for_class_level(
                class_name,
                "1",
                spell_catalog,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=1,
                feature_entries=feature_entries,
            )
            if str(option.get("value") or "").strip()
            not in (
                automatic_known_lookup_keys
                | automatic_spell_support_lookup_keys
                | automatic_campaign_spell_manager_lookup_keys
                | selected_bonus_known_values
            )
        ]
        automatic_prepared_lookup_keys = _automatic_prepared_spell_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        if spell_mode == "prepared" and automatic_prepared_lookup_keys:
            level_one_options = [
                option
                for option in level_one_options
                if str(option.get("value") or "").strip()
                not in (
                    automatic_prepared_lookup_keys
                    | automatic_spell_support_lookup_keys
                    | automatic_campaign_spell_manager_lookup_keys
                )
            ]
        if level_one_options:
            if spell_mode == "wizard":
                for index in range(spellbook_count):
                    field_name = f"wizard_spellbook_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"Spellbook Spell {index + 1}",
                            "help_text": "Choose a 1st-level wizard spell for your spellbook.",
                            "options": level_one_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "wizard_spellbook",
                            "kind": "spell",
                        }
                    )

                selected_spellbook_values = [
                    str(values.get(f"wizard_spellbook_{index + 1}") or "").strip()
                    for index in range(spellbook_count)
                    if str(values.get(f"wizard_spellbook_{index + 1}") or "").strip()
                ]
                prepared_options = (
                    [option for option in level_one_options if option["value"] in selected_spellbook_values]
                    if selected_spellbook_values
                    else level_one_options
                )
                for index in range(prepared_count):
                    field_name = f"wizard_prepared_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"Prepared Spell {index + 1}",
                            "help_text": "Choose a prepared wizard spell from your selected spellbook spells.",
                            "options": prepared_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "wizard_prepared",
                            "kind": "spell",
                        }
                    )
            else:
                selection_count = level_one_count if spell_mode == "known" else prepared_count
                label_prefix = "Known Spell" if spell_mode == "known" else "Prepared Spell"
                help_text = (
                    f"Choose a {class_name} spell you know."
                    if spell_mode == "known"
                    else f"Choose a {class_name} spell you have prepared."
                )
                for index in range(selection_count):
                    field_name = f"spell_level_one_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"{label_prefix} {index + 1}",
                            "help_text": help_text,
                            "options": level_one_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "spell_level_one",
                            "kind": "spell",
                        }
                    )
    else:
        fields.extend(spell_support_fields)
        fields.extend(campaign_spell_manager_fields)

    replacement_fields = _build_level_one_spell_support_replacement_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        existing_fields=fields + feat_spell_fields,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
    )
    return fields + replacement_fields + feat_spell_fields


def _build_level_one_spell_support_replacement_fields(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    existing_fields: list[dict[str, Any]],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    provisional_choice_sections = [{"title": "Spell Choices", "fields": list(existing_fields or [])}]
    _, provisional_selected_choices = _resolve_builder_choices(provisional_choice_sections, values, strict=False)
    provisional_spell_payloads = _build_level_one_spell_payloads(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=provisional_choice_sections,
        selected_choices=provisional_selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
    )
    return _build_spell_support_replacement_fields(
        existing_spells=provisional_spell_payloads,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )


def _build_level_up_spell_choice_fields(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    target_level: int,
    ability_scores: dict[str, int],
    values: dict[str, str],
    feature_entries: list[dict[str, Any]] | None = None,
    automatic_prepared_feature_entries: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_list_class_name = _spell_list_class_name_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    spell_label_name = spell_list_class_name if spell_list_class_name and spell_list_class_name != class_name else class_name
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    feat_spell_fields = _build_feat_spell_choice_fields(
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        target_level=target_level,
    )
    campaign_spell_manager_fields = _build_campaign_feature_spell_manager_fields(
        feature_entries=feature_entries,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix_base="levelup_campaign_spell_manager",
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        target_level,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    max_spell_level = max((int(slot.get("level") or 0) for slot in slot_progression), default=0)
    existing_spell_rows = [
        dict(row or {})
        for row in list((definition.spellcasting or {}).get("class_rows") or [])
        if isinstance(row, dict)
    ]
    if not existing_spell_rows and class_row_id:
        existing_spell_rows = [{"class_row_id": class_row_id}]
    existing_spells = _assign_spell_payload_class_rows(
        list((definition.spellcasting or {}).get("spells") or []),
        spellcasting_rows=existing_spell_rows,
    )
    existing_row_spells = [
        dict(spell_payload or {})
        for spell_payload in existing_spells
        if not class_row_id or _spell_payload_class_row_id(dict(spell_payload or {})) == class_row_id
    ]
    existing_cantrip_values = _spell_selection_values_by_mark(
        existing_row_spells,
        "Cantrip",
        exclude_bonus_known=True,
        class_row_id=class_row_id,
    )
    existing_known_values = _spell_selection_values_by_mark(
        existing_row_spells,
        "Known",
        exclude_bonus_known=True,
        class_row_id=class_row_id,
    )
    existing_prepared_values = _spell_selection_values_by_mark(
        existing_row_spells,
        "Prepared",
        class_row_id=class_row_id,
    )
    existing_spellbook_values = _spell_selection_values_by_mark(
        existing_row_spells,
        "Spellbook",
        class_row_id=class_row_id,
    )
    existing_always_prepared_values = {
        payload_key
        for spell_payload in existing_row_spells
        if bool(spell_payload.get("is_always_prepared")) and (payload_key := _spell_payload_key(spell_payload))
    }
    target_always_prepared_values = _automatic_prepared_spell_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=automatic_prepared_feature_entries or feature_entries,
    )
    target_known_bonus_values = _automatic_known_spell_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
    )
    target_spell_support_lookup_keys = _automatic_spell_support_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        exact_level=target_level,
        feature_entries=feature_entries,
    )
    target_campaign_spell_manager_lookup_keys = {
        _spell_lookup_key(str(spell_grant.get("name") or "").strip(), spell_catalog)
        for spell_grant in _automatic_campaign_feature_spell_manager_grants(
            feature_entries=feature_entries,
            values=values,
            field_prefix_base="levelup_campaign_spell_manager",
        )
        if _spell_lookup_key(str(spell_grant.get("name") or "").strip(), spell_catalog)
    }
    selected_bonus_known_values = _selected_form_spell_values_by_field_prefix(values, prefix="levelup_bonus_spell_known_")

    fields: list[dict[str, Any]] = []
    fields.extend(
        _build_spell_support_choice_fields(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=target_level,
            exact_level=target_level,
            values=values,
            field_prefix="levelup_spell_support",
            group_key_prefix="levelup_spell_support",
            feature_entries=feature_entries,
        )
    )
    fields.extend(campaign_spell_manager_fields)
    structured_replacement_fields = _build_spell_support_replacement_fields(
        existing_spells=existing_row_spells,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
    )
    fields.extend(structured_replacement_fields)
    if not spell_mode:
        return fields + feat_spell_fields

    target_cantrip_count = _spell_progression_value(
        class_name,
        "cantrip_progression",
        target_level,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    additional_cantrips = max(target_cantrip_count - len(existing_cantrip_values), 0)
    cantrip_options = [
        option
        for option in _build_spell_options_for_class_level(
            class_name,
            "0",
            spell_catalog,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            row_level=target_level,
            feature_entries=feature_entries,
        )
        if option["value"]
        not in (
            existing_cantrip_values
            | target_known_bonus_values
            | target_spell_support_lookup_keys
            | target_campaign_spell_manager_lookup_keys
            | selected_bonus_known_values
        )
    ]
    if cantrip_options:
        for index in range(additional_cantrips):
            field_name = f"levelup_spell_cantrip_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Cantrip {index + 1}",
                    "help_text": f"Choose a new {spell_label_name} cantrip for level {target_level}.",
                    "options": cantrip_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_spell_cantrips",
                    "kind": "spell",
                }
            )

    fields.extend(
        _build_additional_known_spell_choice_fields(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=target_level,
            exact_level=target_level,
            values=values,
            field_prefix="levelup_bonus_spell_known",
            group_key_prefix="levelup_bonus_spell_known",
            feature_entries=feature_entries,
        )
    )

    if max_spell_level <= 0:
        return fields + feat_spell_fields

    spell_level_options = _build_spell_options_for_class_levels(
        class_name,
        range(1, max_spell_level + 1),
        spell_catalog,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
        feature_entries=feature_entries,
    )
    if not spell_level_options and spell_mode != "wizard":
        return fields + feat_spell_fields

    if spell_mode == "known":
        target_known_count = _spell_progression_value(
            class_name,
            "spells_known_progression",
            target_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        additional_known = max(target_known_count - len(existing_known_values), 0)
        options = [
            option
            for option in spell_level_options
            if option["value"]
            not in (
                existing_known_values
                | target_known_bonus_values
                | target_spell_support_lookup_keys
                | target_campaign_spell_manager_lookup_keys
                | selected_bonus_known_values
            )
        ]
        if additional_known > 0 and not options:
            return fields + feat_spell_fields
        for index in range(additional_known):
            field_name = f"levelup_spell_known_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Spell {index + 1}",
                    "help_text": f"Choose a new {spell_label_name} spell for level {target_level}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_spell_known",
                    "kind": "spell",
                }
            )
        fields.extend(
            []
            if structured_replacement_fields
            else _build_level_up_known_spell_replacement_fields(
                existing_spells=existing_row_spells,
                existing_known_values=existing_known_values,
                replacement_options=options,
                spell_catalog=spell_catalog,
                values=values,
            )
        )
        return fields + feat_spell_fields

    if spell_mode == "prepared":
        target_prepared_count = _prepared_spell_count_for_level(
            class_name,
            ability_scores,
            target_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        additional_prepared = max(target_prepared_count - len(existing_prepared_values), 0)
        excluded_values = (
            existing_prepared_values
            | existing_always_prepared_values
            | target_always_prepared_values
            | target_spell_support_lookup_keys
            | target_campaign_spell_manager_lookup_keys
        )
        options = [option for option in spell_level_options if option["value"] not in excluded_values]
        if additional_prepared > 0 and not options:
            return fields + feat_spell_fields
        for index in range(additional_prepared):
            field_name = f"levelup_prepared_spell_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Prepared Spell {index + 1}",
                    "help_text": f"Choose a new prepared {spell_label_name} spell for level {target_level}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_prepared_spells",
                    "kind": "spell",
                }
            )
        return fields + feat_spell_fields

    if spell_mode == "wizard":
        new_spellbook_spells = _spell_progression_value(
            class_name,
            "spells_known_progression_fixed",
            target_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        spellbook_options = [option for option in spell_level_options if option["value"] not in existing_spellbook_values]
        if new_spellbook_spells > 0 and not spellbook_options:
            return fields + feat_spell_fields
        for index in range(new_spellbook_spells):
            field_name = f"levelup_wizard_spellbook_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Spellbook Spell {index + 1}",
                    "help_text": f"Choose a wizard spell of 1st through level {max_spell_level} to add to your spellbook.",
                    "options": spellbook_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_wizard_spellbook",
                    "kind": "spell",
                }
            )
        new_spellbook_values = [
            str(values.get(f"levelup_wizard_spellbook_{index + 1}") or "").strip()
            for index in range(new_spellbook_spells)
            if str(values.get(f"levelup_wizard_spellbook_{index + 1}") or "").strip()
        ]
        prepared_options = [
            option
            for option in spell_level_options
            if option["value"] in (existing_spellbook_values | set(new_spellbook_values))
            and option["value"] not in (
                existing_prepared_values
                | target_always_prepared_values
                | target_spell_support_lookup_keys
                | target_campaign_spell_manager_lookup_keys
            )
        ]
        target_prepared_count = _prepared_spell_count_for_level(
            class_name,
            ability_scores,
            target_level,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
        )
        additional_prepared = max(target_prepared_count - len(existing_prepared_values), 0)
        if additional_prepared > 0 and not prepared_options:
            return fields + feat_spell_fields
        for index in range(additional_prepared):
            field_name = f"levelup_wizard_prepared_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Prepared Spell {index + 1}",
                    "help_text": "Choose an additional prepared wizard spell from your spellbook.",
                    "options": prepared_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_wizard_prepared",
                    "kind": "spell",
                }
            )
        return fields + feat_spell_fields

    return fields + feat_spell_fields


def _build_level_up_known_spell_replacement_fields(
    *,
    existing_spells: list[dict[str, Any]],
    existing_known_values: set[str],
    replacement_options: list[dict[str, str]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not existing_known_values or not replacement_options:
        return []
    replace_from_options = _build_spell_options_from_payload_keys(
        payload_keys=existing_known_values,
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
    )
    if not replace_from_options:
        return []
    return [
        {
            "name": "levelup_spell_replace_from_1",
            "label": "Replace Known Spell",
            "help_text": "Optionally choose a spell you are replacing this level.",
            "options": replace_from_options,
            "selected": str(values.get("levelup_spell_replace_from_1") or "").strip(),
            "group_key": "levelup_spell_replace_from_1",
            "kind": "spell",
            "required": False,
        },
        {
            "name": "levelup_spell_replace_to_1",
            "label": "Replacement Spell",
            "help_text": "Choose the new spell that replaces your selected known spell.",
            "options": replacement_options,
            "selected": str(values.get("levelup_spell_replace_to_1") or "").strip(),
            "group_key": "levelup_spell_replace_to_1",
            "kind": "spell",
            "required": False,
        },
    ]


def _build_spell_options_from_payload_keys(
    *,
    payload_keys: set[str],
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    remaining_keys = set(payload_keys)
    for spell_payload in existing_spells:
        payload_key = _spell_payload_key(spell_payload)
        if not payload_key or payload_key not in remaining_keys:
            continue
        entry = _resolve_spell_entry(payload_key, spell_catalog)
        value = entry.slug if entry is not None else payload_key
        label = entry.title if entry is not None else str(spell_payload.get("name") or payload_key).strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        remaining_keys.discard(payload_key)
        options.append(_choice_option(label, value))
    for payload_key in sorted(remaining_keys):
        entry = _resolve_spell_entry(payload_key, spell_catalog)
        value = entry.slug if entry is not None else payload_key
        label = entry.title if entry is not None else payload_key
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _build_level_up_spell_payloads(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    automatic_prepared_feature_entries: list[dict[str, Any]] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    existing_spell_rows = [
        dict(row or {})
        for row in list((current_definition.spellcasting or {}).get("class_rows") or [])
        if isinstance(row, dict)
    ]
    if not existing_spell_rows and class_row_id:
        existing_spell_rows = [{"class_row_id": class_row_id}]
    existing_spells = _assign_spell_payload_class_rows(
        list((current_definition.spellcasting or {}).get("spells") or []),
        spellcasting_rows=existing_spell_rows,
    )
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in existing_spells:
        payload_key = _spell_payload_map_key(spell)
        if payload_key:
            spells_by_key[payload_key] = dict(spell)
    values = _values_from_selected_choices(choice_sections, selected_choices)

    for selected_value in selected_choices.get("levelup_spell_cantrips", []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark="Cantrip",
            class_row_id=class_row_id,
        )
    for selected_value in _selected_additional_known_spell_values(selected_choices, prefix="levelup_bonus_spell_known"):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            class_row_id=class_row_id,
        )

    if spell_mode in {"known", "prepared"}:
        mark = "Known" if spell_mode == "known" else "Prepared"
        group_key = "levelup_spell_known" if spell_mode == "known" else "levelup_prepared_spells"
        if spell_mode == "known":
            replacement_from = str(values.get("levelup_spell_replace_from_1") or "").strip()
            replacement_to = str(values.get("levelup_spell_replace_to_1") or "").strip()
            if replacement_from and replacement_to:
                spells_by_key.pop(
                    _spell_payload_map_key(
                        {
                            "systems_ref": {"slug": _spell_lookup_key(replacement_from, spell_catalog)},
                            "class_row_id": class_row_id,
                        }
                    ),
                    None,
                )
                _add_spell_to_payloads(
                    spells_by_key,
                    selected_value=replacement_to,
                    spell_catalog=spell_catalog,
                    mark="Known",
                    class_row_id=class_row_id,
                )
        for selected_value in selected_choices.get(group_key, []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark=mark,
                class_row_id=class_row_id,
            )
    elif spell_mode == "wizard":
        existing_prepared = _spell_selection_values_by_mark(
            existing_spells,
            "Prepared",
            class_row_id=class_row_id,
        )
        new_spellbook_values = list(selected_choices.get("levelup_wizard_spellbook", []))
        new_prepared_values = set(selected_choices.get("levelup_wizard_prepared", []))
        for selected_value in new_spellbook_values:
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared + Spellbook" if selected_value in new_prepared_values else "Spellbook",
                class_row_id=class_row_id,
            )
        for selected_value in new_prepared_values:
            payload_key = _spell_payload_map_key(
                {
                    "systems_ref": {"slug": _spell_lookup_key(selected_value, spell_catalog)},
                    "class_row_id": class_row_id,
                }
            )
            existing_payload = spells_by_key.get(payload_key)
            if existing_payload is None:
                _add_spell_to_payloads(
                    spells_by_key,
                    selected_value=selected_value,
                    spell_catalog=spell_catalog,
                    mark="Prepared + Spellbook",
                    class_row_id=class_row_id,
                )
                continue
            if "Prepared" not in str(existing_payload.get("mark") or ""):
                existing_payload["mark"] = _merge_spell_mark(str(existing_payload.get("mark") or "").strip(), "Prepared")
        for selected_value in existing_prepared:
            payload_key = _spell_payload_map_key(
                {
                    "systems_ref": {"slug": _spell_lookup_key(selected_value, spell_catalog)},
                    "class_row_id": class_row_id,
                }
            )
            existing_payload = spells_by_key.get(payload_key)
            if existing_payload is not None and "Prepared" not in str(existing_payload.get("mark") or ""):
                existing_payload["mark"] = _merge_spell_mark(str(existing_payload.get("mark") or "").strip(), "Prepared")

    for selected_value in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=feature_entries,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            class_row_id=class_row_id,
        )
    for selected_value in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=automatic_prepared_feature_entries or feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
            class_row_id=class_row_id,
        )
    _apply_spell_support_grants_to_payloads(
        spells_by_key,
        grants=_automatic_spell_support_grants(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            target_level=target_level,
            exact_level=target_level,
            feature_entries=feature_entries,
        ),
        spell_catalog=spell_catalog,
        class_row_id=class_row_id,
    )
    for spell_grant in _automatic_campaign_feature_spell_manager_grants(
        feature_entries=feature_entries,
        values=values,
        field_prefix_base="levelup_campaign_spell_manager",
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            class_row_id=class_row_id,
            prefer_known_mark=bool(spell_grant.get("prefer_known_mark", True)),
            **_spell_payload_support_kwargs(spell_grant),
        )
    _apply_selected_spell_support_fields_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
        class_row_id=class_row_id,
    )
    _apply_selected_campaign_feature_spell_manager_fields_to_payloads(
        spells_by_key,
        feature_entries=feature_entries,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix_base="levelup_campaign_spell_manager",
        class_row_id=class_row_id,
    )
    _apply_selected_feat_spell_fields_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        class_row_id=class_row_id,
    )
    _apply_selected_campaign_option_spells_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        extra_option_payloads=selected_campaign_option_payloads,
        class_row_id=class_row_id,
    )
    for spell_grant in _supported_feat_spell_automatic_grants(feat_selections=feat_selections):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            class_row_id=class_row_id,
            prefer_known_mark=bool(spell_grant.get("prefer_known_mark", True)),
            **_spell_payload_support_kwargs(spell_grant),
        )
    for spell_title in _automatic_feat_known_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            class_row_id=class_row_id,
        )
    for spell_title in _automatic_feat_prepared_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
            class_row_id=class_row_id,
        )
    for spell_grant in _automatic_feat_innate_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
            class_row_id=class_row_id,
        )
    for spell_grant in _automatic_innate_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
            class_row_id=class_row_id,
        )
    _apply_selected_spell_support_replacements_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
        class_row_id=class_row_id,
    )

    return list(spells_by_key.values())


def _level_up_slot_progression_for_class(
    class_name: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
) -> list[dict[str, Any]]:
    return _spell_slot_progression_for_class_level(
        class_name,
        target_level,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )


def _build_level_one_spell_payloads(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=1,
    )
    spells_by_key: dict[str, dict[str, Any]] = {}
    values = _values_from_selected_choices(choice_sections, selected_choices)
    for selected_value in selected_choices.get("spell_cantrips", []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark="Cantrip",
        )
    for selected_value in _selected_additional_known_spell_values(selected_choices, prefix="bonus_spell_known"):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
        )

    if spell_mode == "known":
        for selected_value in selected_choices.get("spell_level_one", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Known",
            )
    elif spell_mode == "prepared":
        for selected_value in selected_choices.get("spell_level_one", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared",
            )
    elif spell_mode == "wizard":
        prepared_values = set(selected_choices.get("wizard_prepared", []))
        for selected_value in selected_choices.get("wizard_spellbook", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared + Spellbook" if selected_value in prepared_values else "Spellbook",
            )

    for spell_title in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
        )

    for spell_title in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )

    _apply_spell_support_grants_to_payloads(
        spells_by_key,
        grants=_automatic_spell_support_grants(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            target_level=1,
            feature_entries=feature_entries,
        ),
        spell_catalog=spell_catalog,
    )
    for spell_grant in _automatic_campaign_feature_spell_manager_grants(
        feature_entries=feature_entries,
        values=values,
        field_prefix_base="campaign_spell_manager",
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            prefer_known_mark=bool(spell_grant.get("prefer_known_mark", True)),
            **_spell_payload_support_kwargs(spell_grant),
        )
    _apply_selected_spell_support_fields_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )
    _apply_selected_campaign_feature_spell_manager_fields_to_payloads(
        spells_by_key,
        feature_entries=feature_entries,
        spell_catalog=spell_catalog,
        values=values,
        field_prefix_base="campaign_spell_manager",
    )
    for spell_title in _automatic_feat_known_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
        )
    for spell_title in _automatic_feat_prepared_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )
    for spell_grant in _automatic_feat_innate_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    for spell_grant in _automatic_innate_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    _apply_selected_feat_spell_fields_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
    )
    for spell_grant in _supported_feat_spell_automatic_grants(feat_selections=feat_selections):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            prefer_known_mark=bool(spell_grant.get("prefer_known_mark", True)),
            **_spell_payload_support_kwargs(spell_grant),
        )
    _apply_selected_campaign_option_spells_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        extra_option_payloads=campaign_option_payloads,
    )
    _apply_selected_spell_support_replacements_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )

    return list(spells_by_key.values())


def _spell_payload_key(spell_payload: dict[str, Any]) -> str:
    systems_ref = dict(spell_payload.get("systems_ref") or {})
    return str(systems_ref.get("slug") or spell_payload.get("name") or "").strip()


def _spell_payload_class_row_id(spell_payload: dict[str, Any]) -> str:
    return str(spell_payload.get("class_row_id") or "").strip()


def _spell_payload_source_row_id(spell_payload: dict[str, Any]) -> str:
    return str(spell_payload.get("spell_source_row_id") or "").strip()


def _spell_payload_management_row(spell_payload: dict[str, Any]) -> tuple[str, str]:
    class_row_id = _spell_payload_class_row_id(spell_payload)
    if class_row_id:
        return "class", class_row_id
    source_row_id = _spell_payload_source_row_id(spell_payload)
    if source_row_id:
        return str(spell_payload.get("spell_source_row_kind") or "source").strip() or "source", source_row_id
    return "", ""


def _spell_payload_management_row_id(spell_payload: dict[str, Any]) -> str:
    return _spell_payload_management_row(spell_payload)[1]


def _spell_payload_management_scope_key(spell_payload: dict[str, Any]) -> str:
    row_kind, row_id = _spell_payload_management_row(spell_payload)
    if not row_id:
        return ""
    if row_kind == "class":
        return row_id
    return f"{row_kind}:{row_id}"


def _spell_access_payload(raw_value: Any) -> dict[str, Any]:
    payload = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    access_type = str(payload.get("spell_access_type") or payload.get("access_type") or "").strip()
    if access_type not in {SPELL_ACCESS_TYPE_AT_WILL, SPELL_ACCESS_TYPE_FREE_CAST}:
        return {}
    normalized = {"spell_access_type": access_type}
    if access_type == SPELL_ACCESS_TYPE_FREE_CAST:
        try:
            uses = int(payload.get("spell_access_uses", payload.get("access_uses")) or 0)
        except (TypeError, ValueError):
            uses = 0
        if uses > 0:
            normalized["spell_access_uses"] = uses
        reset_on = str(payload.get("spell_access_reset_on") or payload.get("access_reset_on") or "").strip()
        if reset_on:
            normalized["spell_access_reset_on"] = reset_on
    return normalized


def _spell_access_badge_label(raw_value: Any) -> str:
    access_payload = _spell_access_payload(raw_value)
    access_type = str(access_payload.get("spell_access_type") or "").strip()
    if access_type == SPELL_ACCESS_TYPE_AT_WILL:
        return "At will"
    if access_type != SPELL_ACCESS_TYPE_FREE_CAST:
        return ""
    reset_on = str(access_payload.get("spell_access_reset_on") or "").strip()
    reset_label = SPELL_ACCESS_RESET_LABELS.get(reset_on, _humanize_words(reset_on))
    try:
        uses = int(access_payload.get("spell_access_uses") or 0)
    except (TypeError, ValueError):
        uses = 0
    if uses > 0 and reset_label:
        return f"{uses} / {reset_label}"
    if reset_label:
        return f"Free cast ({reset_label})"
    return "Free cast"


def _spell_source_support_payload(raw_value: Any) -> dict[str, Any]:
    payload = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    raw_source = payload.get("spell_source", payload.get("source"))
    source_payload = dict(raw_source or {}) if isinstance(raw_source, dict) else {}
    source_row_id = str(
        payload.get("spell_source_row_id")
        or source_payload.get("row_id")
        or source_payload.get("id")
        or ""
    ).strip()
    source_row_title = str(
        payload.get("spell_source_row_title")
        or source_payload.get("title")
        or source_payload.get("label")
        or ""
    ).strip()
    if not source_row_id and source_row_title:
        source_row_id = f"spell-source:{slugify(source_row_title)}"

    grant_source_label = str(
        payload.get("grant_source_label")
        or source_payload.get("grant_source_label")
        or source_row_title
        or ""
    ).strip()
    if not source_row_id:
        return {"grant_source_label": grant_source_label} if grant_source_label else {}

    support_payload: dict[str, Any] = {
        "spell_source_row_id": source_row_id,
        "spell_source_row_kind": str(
            payload.get("spell_source_row_kind")
            or source_payload.get("row_kind")
            or source_payload.get("kind")
            or "source"
        ).strip()
        or "source",
    }
    if source_row_title:
        support_payload["spell_source_row_title"] = source_row_title
    ability_key = _prepared_spell_formula_ability_key(
        str(
            payload.get("spell_source_ability_key")
            or source_payload.get("ability_key")
            or source_payload.get("spellcasting_ability_key")
            or ""
        ).strip()
    )
    if ability_key:
        support_payload["spell_source_ability_key"] = ability_key
    source_mode = str(
        payload.get("spell_source_mode")
        or source_payload.get("mode")
        or ""
    ).strip()
    if source_mode:
        support_payload["spell_source_mode"] = source_mode
    spell_list_class_name = str(
        payload.get("spell_source_spell_list_class_name")
        or source_payload.get("spell_list_class_name")
        or source_payload.get("class_name")
        or ""
    ).strip()
    if spell_list_class_name:
        support_payload["spell_source_spell_list_class_name"] = spell_list_class_name
    if grant_source_label:
        support_payload["grant_source_label"] = grant_source_label
    return support_payload


def _merge_spell_support_kwargs(
    base: dict[str, Any] | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(overrides or {}).items():
        if value in {"", None}:
            continue
        merged[key] = value
    return merged


def _spell_support_support_kwargs(
    raw_value: Any,
    *,
    inherited_support_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    support_kwargs = _merge_spell_support_kwargs(
        inherited_support_kwargs,
        _spell_source_support_payload(raw_value),
    )
    return _merge_spell_support_kwargs(support_kwargs, _spell_access_payload(raw_value))


def _spell_payload_support_kwargs(raw_value: Any) -> dict[str, Any]:
    payload = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    support_kwargs: dict[str, Any] = {}
    source_row_id = _spell_payload_source_row_id(payload)
    if source_row_id:
        support_kwargs["spell_source_row_id"] = source_row_id
        support_kwargs["spell_source_row_kind"] = (
            str(payload.get("spell_source_row_kind") or "source").strip() or "source"
        )
        support_kwargs["spell_source_row_title"] = str(payload.get("spell_source_row_title") or "").strip()
        support_kwargs["spell_source_ability_key"] = str(payload.get("spell_source_ability_key") or "").strip()
        support_kwargs["spell_source_mode"] = str(payload.get("spell_source_mode") or "").strip()
        support_kwargs["spell_source_spell_list_class_name"] = str(
            payload.get("spell_source_spell_list_class_name") or ""
        ).strip()
    grant_source_label = str(payload.get("grant_source_label") or "").strip()
    if grant_source_label:
        support_kwargs["grant_source_label"] = grant_source_label
    support_kwargs.update(_spell_access_payload(payload))
    return support_kwargs


def _apply_spell_payload_support_metadata(
    spell_payload: dict[str, Any],
    support_payload: dict[str, Any],
) -> None:
    source_row_id = str(support_payload.get("spell_source_row_id") or "").strip()
    if source_row_id:
        spell_payload["spell_source_row_id"] = source_row_id
        spell_payload["spell_source_row_kind"] = (
            str(support_payload.get("spell_source_row_kind") or "source").strip() or "source"
        )
        spell_source_row_title = str(support_payload.get("spell_source_row_title") or "").strip()
        if spell_source_row_title:
            spell_payload["spell_source_row_title"] = spell_source_row_title
        spell_source_ability_key = _prepared_spell_formula_ability_key(
            str(support_payload.get("spell_source_ability_key") or "").strip()
        )
        if spell_source_ability_key:
            spell_payload["spell_source_ability_key"] = spell_source_ability_key
        spell_source_mode = str(support_payload.get("spell_source_mode") or "").strip()
        if spell_source_mode:
            spell_payload["spell_source_mode"] = spell_source_mode
        spell_source_spell_list_class_name = str(
            support_payload.get("spell_source_spell_list_class_name") or ""
        ).strip()
        if spell_source_spell_list_class_name:
            spell_payload["spell_source_spell_list_class_name"] = spell_source_spell_list_class_name
        spell_payload.pop("class_row_id", None)
    grant_source_label = str(support_payload.get("grant_source_label") or "").strip()
    if grant_source_label:
        spell_payload["grant_source_label"] = grant_source_label
    access_payload = _spell_access_payload(support_payload)
    if access_payload:
        spell_payload.update(access_payload)


def _spell_payload_map_key(spell_payload: dict[str, Any]) -> str:
    payload_key = _spell_payload_key(spell_payload)
    if not payload_key:
        return ""
    scope_key = _spell_payload_management_scope_key(spell_payload)
    return f"{scope_key}::{payload_key}" if scope_key else payload_key


def _spell_lookup_key(selected_value: str, spell_catalog: dict[str, Any]) -> str:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    if spell_entry is not None:
        return spell_entry.slug
    return str(selected_value or "").strip()


def _spell_selection_values_by_mark(
    spell_payloads: list[dict[str, Any]],
    mark_fragment: str,
    *,
    exclude_bonus_known: bool = False,
    class_row_id: str = "",
) -> set[str]:
    values: set[str] = set()
    normalized_mark = normalize_lookup(mark_fragment)
    clean_class_row_id = str(class_row_id or "").strip()
    for spell_payload in spell_payloads:
        if exclude_bonus_known and bool(spell_payload.get("is_bonus_known")):
            continue
        if clean_class_row_id and _spell_payload_class_row_id(dict(spell_payload or {})) != clean_class_row_id:
            continue
        if normalized_mark not in normalize_lookup(str(spell_payload.get("mark") or "")):
            continue
        payload_key = _spell_payload_key(spell_payload)
        if payload_key:
            values.add(payload_key)
    return values


def _selected_additional_known_spell_values(
    selected_choices: dict[str, list[str]],
    *,
    prefix: str,
) -> list[str]:
    values: list[str] = []
    for group_key, group_values in selected_choices.items():
        if not str(group_key).startswith(prefix):
            continue
        values.extend(str(value).strip() for value in group_values if str(value).strip())
    return _dedupe_preserve_order(values)


def _selected_form_spell_values_by_field_prefix(
    values: dict[str, str],
    *,
    prefix: str,
) -> set[str]:
    return {
        str(value).strip()
        for key, value in dict(values or {}).items()
        if str(key).startswith(prefix) and str(value).strip()
    }


def _values_from_selected_choices(
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "").strip()
            group_key = str(field.get("group_key") or field_name).strip()
            selected_value = next((value for value in list(selected_choices.get(group_key) or []) if str(value).strip()), "")
            if field_name and selected_value:
                values[field_name] = str(selected_value).strip()
    return values


def _selected_feat_spell_field_values(
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[tuple[dict[str, Any], str]]:
    values: list[tuple[dict[str, Any], str]] = []
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            kind = str(field.get("kind") or "").strip()
            if kind not in {"feat_spell_known", "feat_spell_prepared", "feat_spell_granted", "feat_spell_managed"}:
                continue
            group_key = str(field.get("group_key") or field.get("name") or "").strip()
            for selected_value in list(selected_choices.get(group_key) or []):
                clean_value = str(selected_value).strip()
                if clean_value:
                    values.append((dict(field), clean_value))
    return values


def _apply_selected_feat_spell_fields_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    class_row_id: str = "",
) -> None:
    for field, selected_value in _selected_feat_spell_field_values(choice_sections, selected_choices):
        kind = str(field.get("kind") or "").strip()
        support_kwargs = _spell_payload_support_kwargs(field)
        if kind == "feat_spell_known":
            _add_bonus_known_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                class_row_id=class_row_id,
                prefer_known_mark=bool(field.get("prefer_known_mark", True)),
                **support_kwargs,
            )
            continue
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
            class_row_id=class_row_id,
            **support_kwargs,
        )


def _apply_selected_campaign_option_spells_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    extra_option_payloads: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> None:
    for spell_grant in collect_campaign_option_spell_grants(
        _selected_campaign_option_payloads(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            extra_option_payloads=extra_option_payloads,
        )
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
            class_row_id=class_row_id,
        )


def _build_additional_known_spell_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_additional_known_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        options = _build_additional_spell_filter_options(str(spec.get("filter") or ""), spell_catalog)
        if not options:
            continue
        count = max(int(spec.get("count") or 1), 1)
        is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
        label_prefix = "Granted Cantrip" if is_cantrip else "Granted Spell"
        help_text = (
            "Choose a feature-granted bonus cantrip."
            if is_cantrip
            else "Choose a feature-granted bonus spell."
        )
        group_key = f"{group_key_prefix}_{spec_index}"
        for choice_index in range(count):
            field_name = f"{field_prefix}_{spec_index}_{choice_index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"{label_prefix} {choice_index + 1}",
                    "help_text": help_text,
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": group_key,
                    "kind": "spell",
                }
            )
    return fields


def _build_spell_support_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_spell_support_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        options = _build_spell_support_options_from_spec(spec, spell_catalog)
        if not options:
            continue
        category = str(spec.get("category") or "").strip()
        count = max(int(spec.get("count") or 1), 1)
        is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
        label_prefix = str(spec.get("label_prefix") or "").strip()
        if not label_prefix:
            label_prefix = "Granted Cantrip" if is_cantrip else "Granted Spell"
        help_text = str(spec.get("help_text") or "").strip()
        if not help_text:
            help_text = (
                "Choose a feature-granted cantrip."
                if is_cantrip
                else "Choose a feature-granted spell."
            )
        group_key = f"{group_key_prefix}_{category}_{spec_index}"
        for choice_index in range(1, count + 1):
            field_name = _spell_support_choice_field_name(field_prefix, category, spec_index, choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{label_prefix} {choice_index}",
                    "help_text": help_text,
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": group_key,
                    "kind": f"spell_support_{category}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                    "spell_source_row_id": str(spec.get("spell_source_row_id") or "").strip(),
                    "spell_source_row_kind": str(spec.get("spell_source_row_kind") or "").strip(),
                    "spell_source_row_title": str(spec.get("spell_source_row_title") or "").strip(),
                    "spell_source_ability_key": str(spec.get("spell_source_ability_key") or "").strip(),
                    "spell_source_mode": str(spec.get("spell_source_mode") or "").strip(),
                    "spell_source_spell_list_class_name": str(
                        spec.get("spell_source_spell_list_class_name") or ""
                    ).strip(),
                    "grant_source_label": str(spec.get("grant_source_label") or "").strip(),
                    "spell_access_type": str(spec.get("spell_access_type") or "").strip(),
                    "spell_access_uses": spec.get("spell_access_uses"),
                    "spell_access_reset_on": str(spec.get("spell_access_reset_on") or "").strip(),
                }
            )
    return fields


def _build_spell_support_replacement_fields(
    *,
    existing_spells: list[dict[str, Any]],
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_spell_support_replacement_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        to_options = _build_spell_support_options_from_spec(
            {
                "filter": str(spec.get("to_filter") or "").strip(),
                "options": list(spec.get("to_options") or []),
            },
            spell_catalog,
        )
        from_options = _build_spell_support_existing_options_from_replacement_spec(
            existing_spells=existing_spells,
            spell_catalog=spell_catalog,
            spec=spec,
        )
        if not from_options or not to_options:
            continue
        category = str(spec.get("category") or "known").strip() or "known"
        count = max(int(spec.get("count") or 1), 1)
        from_group_key = f"{field_prefix}_replace_{category}_{spec_index}_from"
        to_group_key = f"{field_prefix}_replace_{category}_{spec_index}_to"
        from_help_text = str(spec.get("help_text_from") or "").strip() or "Choose the spell you are replacing."
        to_help_text = str(spec.get("help_text_to") or "").strip() or "Choose the replacement spell."
        for choice_index in range(1, count + 1):
            from_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "from",
            )
            to_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "to",
            )
            fields.append(
                {
                    "name": from_name,
                    "label": f"Replace Spell {choice_index}",
                    "help_text": from_help_text,
                    "options": from_options,
                    "selected": str(values.get(from_name) or "").strip(),
                    "group_key": from_group_key,
                    "kind": "spell_support_replace_from",
                    "required": False,
                    "paired_field_name": to_name,
                    "paired_field_label": f"Replacement Spell {choice_index}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                }
            )
            fields.append(
                {
                    "name": to_name,
                    "label": f"Replacement Spell {choice_index}",
                    "help_text": to_help_text,
                    "options": to_options,
                    "selected": str(values.get(to_name) or "").strip(),
                    "group_key": to_group_key,
                    "kind": "spell_support_replace_to",
                    "required": False,
                    "paired_field_name": from_name,
                    "paired_field_label": f"Replace Spell {choice_index}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                }
            )
    return fields


def _build_spell_support_existing_options_from_replacement_spec(
    *,
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    spec: dict[str, Any],
) -> list[dict[str, str]]:
    allowed_payload_keys: set[str] = set()
    if list(spec.get("from_options") or []) or str(spec.get("from_filter") or "").strip():
        allowed_payload_keys = {
            str(option.get("value") or "").strip()
            for option in _build_spell_support_options_from_spec(
                {
                    "filter": str(spec.get("from_filter") or "").strip(),
                    "options": list(spec.get("from_options") or []),
                },
                spell_catalog,
            )
            if str(option.get("value") or "").strip()
        }
    return _build_spell_options_from_existing_payloads(
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
        filter_spec={
            "mark": str(spec.get("from_mark") or "").strip(),
            "level": int(spec.get("from_level") or 0),
            "payload_keys": allowed_payload_keys,
        },
    )


def _build_spell_support_options_from_spec(
    spec: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    option_values = list(spec.get("options") or [])
    filter_expression = str(spec.get("filter") or "").strip()
    options = _build_spell_options_from_references(option_values, spell_catalog)
    if filter_expression:
        options.extend(_build_additional_spell_filter_options(filter_expression, spell_catalog))
    deduped_options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for option in options:
        value = str(option.get("value") or "").strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        deduped_options.append(dict(option))
    return deduped_options


def _build_spell_options_from_existing_payloads(
    *,
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    filter_spec: dict[str, Any],
) -> list[dict[str, str]]:
    payload_keys: set[str] = set()
    for spell_payload in list(existing_spells or []):
        payload_key = _spell_payload_key(spell_payload)
        if not payload_key:
            continue
        spell_entry = _resolve_spell_entry(payload_key, spell_catalog)
        if not _spell_payload_matches_replacement_filter(
            spell_payload,
            spell_entry=spell_entry,
            filter_spec=filter_spec,
        ):
            continue
        payload_keys.add(payload_key)
    return _build_spell_options_from_payload_keys(
        payload_keys=payload_keys,
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
    )


def _spell_payload_matches_replacement_filter(
    spell_payload: dict[str, Any],
    *,
    spell_entry: SystemsEntryRecord | None,
    filter_spec: dict[str, Any],
) -> bool:
    allowed_payload_keys = {
        str(payload_key or "").strip()
        for payload_key in list(filter_spec.get("payload_keys") or [])
        if str(payload_key or "").strip()
    }
    payload_key = str((spell_entry.slug if spell_entry is not None else _spell_payload_key(spell_payload)) or "").strip()
    if allowed_payload_keys and payload_key not in allowed_payload_keys:
        return False
    mark_filter = normalize_lookup(str(filter_spec.get("mark") or "").strip())
    if mark_filter and mark_filter not in normalize_lookup(str(spell_payload.get("mark") or "").strip()):
        return False
    spell_level = int(filter_spec.get("level") or 0)
    if spell_level > 0 and (spell_entry is None or _spell_entry_level(spell_entry) != spell_level):
        return False
    return True


def _build_spell_options_from_references(
    values: list[str],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for raw_value in list(values or []):
        clean_value = str(raw_value or "").strip()
        if not clean_value:
            continue
        entry = _resolve_spell_entry(clean_value, spell_catalog)
        value = entry.slug if entry is not None else _normalize_additional_spell_reference(clean_value)
        label = entry.title if entry is not None else _normalize_additional_spell_reference(clean_value)
        if not value or not label or value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _apply_spell_support_grants_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    grants: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    class_row_id: str = "",
) -> None:
    for grant in list(grants or []):
        selected_value = str(grant.get("value") or "").strip()
        if not selected_value:
            continue
        support_kwargs = _spell_payload_support_kwargs(grant)
        if bool(grant.get("bonus_known")):
            _add_bonus_known_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                class_row_id=class_row_id,
                **support_kwargs,
            )
            continue
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark=str(grant.get("mark") or "").strip(),
            is_always_prepared=bool(grant.get("always_prepared")),
            is_ritual=bool(grant.get("ritual")),
            class_row_id=class_row_id,
            **support_kwargs,
        )


def _apply_selected_spell_support_fields_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> None:
    specs = _extract_spell_support_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        category = str(spec.get("category") or "").strip()
        count = max(int(spec.get("count") or 1), 1)
        for choice_index in range(1, count + 1):
            field_name = _spell_support_choice_field_name(field_prefix, category, spec_index, choice_index)
            selected_value = str(values.get(field_name) or "").strip()
            if not selected_value:
                continue
            if category == "known":
                _add_bonus_known_spell_to_payloads(
                    spells_by_key,
                    selected_value=selected_value,
                    spell_catalog=spell_catalog,
                    class_row_id=class_row_id,
                    spell_source_row_id=str(spec.get("spell_source_row_id") or "").strip(),
                    spell_source_row_kind=str(spec.get("spell_source_row_kind") or "").strip(),
                    spell_source_row_title=str(spec.get("spell_source_row_title") or "").strip(),
                    spell_source_ability_key=str(spec.get("spell_source_ability_key") or "").strip(),
                    spell_source_mode=str(spec.get("spell_source_mode") or "").strip(),
                    spell_source_spell_list_class_name=str(
                        spec.get("spell_source_spell_list_class_name") or ""
                    ).strip(),
                    grant_source_label=str(spec.get("grant_source_label") or "").strip(),
                    spell_access_type=str(spec.get("spell_access_type") or "").strip(),
                    spell_access_uses=spec.get("spell_access_uses"),
                    spell_access_reset_on=str(spec.get("spell_access_reset_on") or "").strip(),
                )
                continue
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark=str(spec.get("mark") or "").strip(),
                is_always_prepared=bool(spec.get("always_prepared")),
                is_ritual=bool(spec.get("ritual")),
                class_row_id=class_row_id,
                spell_source_row_id=str(spec.get("spell_source_row_id") or "").strip(),
                spell_source_row_kind=str(spec.get("spell_source_row_kind") or "").strip(),
                spell_source_row_title=str(spec.get("spell_source_row_title") or "").strip(),
                spell_source_ability_key=str(spec.get("spell_source_ability_key") or "").strip(),
                spell_source_mode=str(spec.get("spell_source_mode") or "").strip(),
                spell_source_spell_list_class_name=str(
                    spec.get("spell_source_spell_list_class_name") or ""
                ).strip(),
                grant_source_label=str(spec.get("grant_source_label") or "").strip(),
                spell_access_type=str(spec.get("spell_access_type") or "").strip(),
                spell_access_uses=spec.get("spell_access_uses"),
                spell_access_reset_on=str(spec.get("spell_access_reset_on") or "").strip(),
            )


def _apply_selected_spell_support_replacements_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> None:
    specs = _extract_spell_support_replacement_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        category = str(spec.get("category") or "known").strip() or "known"
        count = max(int(spec.get("count") or 1), 1)
        for choice_index in range(1, count + 1):
            from_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "from",
            )
            to_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "to",
            )
            replacement_from = str(values.get(from_name) or "").strip()
            replacement_to = str(values.get(to_name) or "").strip()
            if not replacement_from or not replacement_to:
                continue
            spells_by_key.pop(
                _spell_payload_map_key(
                    {
                        "systems_ref": {"slug": _spell_lookup_key(replacement_from, spell_catalog)},
                        "class_row_id": class_row_id,
                    }
                ),
                None,
            )
            if category == "known":
                _add_bonus_known_spell_to_payloads(
                    spells_by_key,
                    selected_value=replacement_to,
                    spell_catalog=spell_catalog,
                    class_row_id=class_row_id,
                )
                continue
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=replacement_to,
                spell_catalog=spell_catalog,
                mark=str(spec.get("mark") or "").strip(),
                is_always_prepared=bool(spec.get("always_prepared")),
                is_ritual=bool(spec.get("ritual")),
                class_row_id=class_row_id,
            )


def _build_feat_spell_choice_fields(
    *,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for selection in feat_selections:
        fields.extend(
            _build_feat_spell_choice_fields_for_selection(
                selection=selection,
                spell_catalog=spell_catalog,
                values=values,
                target_level=target_level,
            )
        )
    return fields


def _build_feat_spell_choice_fields_for_selection(
    *,
    selection: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []

    fields: list[dict[str, Any]] = []
    support_config = _supported_feat_spell_config(selection)
    if support_config:
        resolved_support_config = _selected_supported_feat_spell_config(
            selection=selection,
            support_config=support_config,
            values=values,
        )
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            return []
        source_row_payload = _supported_feat_spell_source_row_payload(
            selection=selection,
            support_config=resolved_support_config or support_config,
        )
        for spec_index, raw_spec in enumerate(list((resolved_support_config or support_config).get("choice_fields") or []), start=1):
            spec = dict(raw_spec or {})
            filter_expression = str(spec.get("filter") or "").strip()
            if filter_expression and "{" in filter_expression:
                try:
                    spec["filter"] = filter_expression.format(**(resolved_support_config or support_config))
                except (IndexError, KeyError, ValueError):
                    spec["filter"] = filter_expression
            fields.extend(
                _build_feat_spell_fields_from_spec(
                    feat_title=feat_entry.title,
                    instance_key=instance_key,
                    category=str(spec.get("category") or "spell_known").strip() or "spell_known",
                    spec_index=spec_index,
                    spec={
                        **spec,
                        **source_row_payload,
                        "spell_access_type": str(spec.get("access_type") or "").strip(),
                        "spell_access_uses": spec.get("access_uses"),
                        "spell_access_reset_on": str(spec.get("access_reset_on") or "").strip(),
                    },
                    spell_catalog=spell_catalog,
                    values=values,
                    default_label_prefix="Granted Spell",
                    default_help_text="Choose a feat-granted spell.",
                    kind=str(spec.get("kind") or "feat_spell_known").strip() or "feat_spell_known",
                )
            )
        return fields

    known_specs: list[dict[str, Any]] = []
    prepared_specs: list[dict[str, Any]] = []
    granted_specs: list[dict[str, Any]] = []
    for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
        known_specs.extend(_extract_feat_known_choice_specs(block, target_level=target_level))
        prepared_specs.extend(_extract_feat_prepared_choice_specs(block, target_level=target_level))
        granted_specs.extend(_extract_feat_innate_choice_specs(block, target_level=target_level))

    for spec_index, spec in enumerate(known_specs, start=1):
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_known",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_known",
            )
        )
    for spec_index, spec in enumerate(prepared_specs, start=1):
        spec = {
            **spec,
            "spell_mark": str(spec.get("spell_mark") or "").strip(),
            "spell_is_always_prepared": bool(spec.get("spell_is_always_prepared", True)),
        }
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_prepared",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_prepared",
            )
        )
    for spec_index, spec in enumerate(granted_specs, start=1):
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_granted",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_granted",
            )
        )
    return fields


def _build_feat_spell_fields_from_spec(
    *,
    feat_title: str,
    instance_key: str,
    category: str,
    spec_index: int,
    spec: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    default_label_prefix: str,
    default_help_text: str,
    kind: str,
) -> list[dict[str, Any]]:
    return _build_structured_spell_choice_fields_from_spec(
        title=feat_title,
        category=category,
        spec_index=spec_index,
        spec=spec,
        spell_catalog=spell_catalog,
        values=values,
        default_label_prefix=default_label_prefix,
        default_help_text=default_help_text,
        kind=kind,
        field_name_builder=lambda field_category, current_spec_index, choice_index: _feat_spell_choice_field_name(
            instance_key,
            field_category,
            current_spec_index,
            choice_index,
        ),
    )


def _campaign_spell_manager_choice_field_name(field_prefix: str, category: str, spec_index: int, choice_index: int) -> str:
    return f"{field_prefix}_{category}_{spec_index}_{choice_index}"


def _build_structured_spell_choice_fields_from_spec(
    *,
    title: str,
    category: str,
    spec_index: int,
    spec: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    default_label_prefix: str,
    default_help_text: str,
    kind: str,
    field_name_builder: Callable[[str, int, int], str],
) -> list[dict[str, Any]]:
    options = _build_additional_spell_filter_options(str(spec.get("filter") or ""), spell_catalog)
    if not options:
        return []
    count = max(int(spec.get("count") or 1), 1)
    is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
    label_prefix = str(spec.get("label_prefix") or "").strip() or ("Granted Cantrip" if is_cantrip else default_label_prefix)
    help_text = str(spec.get("help_text") or "").strip() or (
        "Choose a feat-granted cantrip." if is_cantrip else default_help_text
    )
    fields: list[dict[str, Any]] = []
    for choice_index in range(1, count + 1):
        field_name = field_name_builder(category, spec_index, choice_index)
        fields.append(
            {
                "name": field_name,
                "label": f"{title} {label_prefix} {choice_index}",
                "help_text": help_text,
                "options": options,
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": kind,
                "spell_mark": str(spec.get("spell_mark") or spec.get("mark") or "").strip(),
                "spell_is_always_prepared": bool(
                    spec.get("spell_is_always_prepared", spec.get("always_prepared"))
                ),
                "spell_is_ritual": bool(spec.get("spell_is_ritual", spec.get("ritual"))),
                "prefer_known_mark": bool(spec.get("prefer_known_mark", True)),
                "spell_source_row_id": str(spec.get("spell_source_row_id") or "").strip(),
                "spell_source_row_kind": str(spec.get("spell_source_row_kind") or "").strip(),
                "spell_source_row_title": str(spec.get("spell_source_row_title") or "").strip(),
                "spell_source_ability_key": str(spec.get("spell_source_ability_key") or "").strip(),
                "spell_source_mode": str(spec.get("spell_source_mode") or "").strip(),
                "spell_source_spell_list_class_name": str(
                    spec.get("spell_source_spell_list_class_name") or ""
                ).strip(),
                "grant_source_label": str(spec.get("grant_source_label") or "").strip(),
                "spell_access_type": str(
                    spec.get("spell_access_type")
                    or spec.get("access_type")
                    or ""
                ).strip(),
                "spell_access_uses": spec.get("spell_access_uses", spec.get("access_uses")),
                "spell_access_reset_on": str(
                    spec.get("spell_access_reset_on")
                    or spec.get("access_reset_on")
                    or ""
                ).strip(),
            }
        )
    return fields


def _feature_entry_spell_manager_config(
    feature_entry: dict[str, Any],
) -> dict[str, Any]:
    if normalize_lookup(str(feature_entry.get("kind") or "").strip()) == "feat":
        return {}
    campaign_option = dict(feature_entry.get("campaign_option") or {})
    if not campaign_option:
        entry = feature_entry.get("entry")
        if isinstance(entry, SystemsEntryRecord):
            campaign_option = dict(_entry_campaign_option(entry) or {})
    return dict(campaign_option.get("spell_manager") or {})


def _campaign_spell_manager_field_prefix(field_prefix_base: str, manager_index: int) -> str:
    if int(manager_index or 0) <= 1:
        return str(field_prefix_base or "").strip()
    return f"{field_prefix_base}_{manager_index}"


def _campaign_spell_manager_source_field_name(field_prefix: str) -> str:
    return f"{field_prefix}_source_1"


def _campaign_feature_spell_manager_entries(
    feature_entries: list[dict[str, Any]] | None,
    *,
    field_prefix_base: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, str, str]] = set()
    manager_index = 0
    for feature_index, feature_entry in enumerate(list(feature_entries or [])):
        support_config = _feature_entry_spell_manager_config(dict(feature_entry or {}))
        if not support_config:
            continue
        entry = feature_entry.get("entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(entry)).strip()
        title = str(
            feature_entry.get("title")
            or feature_entry.get("label")
            or feature_entry.get("name")
            or (entry.title if isinstance(entry, SystemsEntryRecord) else "")
            or page_ref
            or "Feature spells"
        ).strip() or "Feature spells"
        source_key = (
            page_ref
            or str(feature_entry.get("slug") or "").strip()
            or (str(entry.slug or "").strip() if isinstance(entry, SystemsEntryRecord) else "")
            or title
        )
        instance_key = (
            str(feature_entry.get("instance_key") or "").strip()
            or (str(entry.entry_key or entry.slug or "").strip() if isinstance(entry, SystemsEntryRecord) else "")
            or page_ref
            or title
        )
        source_ref = page_ref or title
        identity = (
            normalize_lookup(source_key),
            normalize_lookup(instance_key),
            normalize_lookup(title),
        )
        if not source_key or identity in seen_identities:
            continue
        seen_identities.add(identity)
        manager_index += 1
        entries.append(
            {
                "feature_index": feature_index,
                "feature_entry": dict(feature_entry or {}),
                "support_config": support_config,
                "title": title,
                "source_key": source_key,
                "instance_key": instance_key,
                "source_ref": source_ref,
                "field_prefix": _campaign_spell_manager_field_prefix(field_prefix_base, manager_index),
                "default_row_kind": str(support_config.get("source_row_kind") or "feature").strip() or "feature",
            }
        )
    return entries


def _selected_campaign_feature_spell_manager_config(
    manager_entry: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any]:
    return _selected_structured_spell_manager_config(
        support_config=dict(manager_entry.get("support_config") or {}),
        values=values,
        field_name=_campaign_spell_manager_source_field_name(str(manager_entry.get("field_prefix") or "").strip()),
    )


def _campaign_feature_spell_manager_source_row_payload(
    manager_entry: dict[str, Any],
    *,
    support_config: dict[str, Any],
) -> dict[str, str]:
    return _structured_spell_manager_source_row_payload(
        source_row_id_prefix="feature-spell-source",
        source_key=str(manager_entry.get("source_key") or "").strip(),
        instance_key=str(manager_entry.get("instance_key") or "").strip(),
        support_config=support_config,
        source_title=str(
            support_config.get("source_title")
            or manager_entry.get("title")
            or "Feature spells"
        ).strip()
        or "Feature spells",
        default_row_kind=str(manager_entry.get("default_row_kind") or "feature").strip() or "feature",
    )


def _build_campaign_feature_spell_manager_fields(
    *,
    feature_entries: list[dict[str, Any]] | None,
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    field_prefix_base: str,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for manager_entry in _campaign_feature_spell_manager_entries(
        feature_entries,
        field_prefix_base=field_prefix_base,
    ):
        support_config = dict(manager_entry.get("support_config") or {})
        field_prefix = str(manager_entry.get("field_prefix") or "").strip()
        source_options = _structured_spell_manager_source_options(support_config)
        if source_options:
            field_name = _campaign_spell_manager_source_field_name(field_prefix)
            fields.append(
                {
                    "name": field_name,
                    "label": str(
                        support_config.get("source_field_label")
                        or f"{manager_entry.get('title') or 'Feature'} Spell List"
                    ).strip(),
                    "help_text": str(
                        support_config.get("source_field_help_text")
                        or f"Choose the spell list used by {manager_entry.get('title') or 'this feature'}."
                    ).strip(),
                    "options": source_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": field_name,
                    "kind": "campaign_spell_source",
                }
            )
        resolved_support_config = _selected_campaign_feature_spell_manager_config(manager_entry, values)
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            continue
        effective_support_config = resolved_support_config or support_config
        source_row_payload = _campaign_feature_spell_manager_source_row_payload(
            manager_entry,
            support_config=effective_support_config,
        )
        for spec_index, raw_spec in enumerate(list(effective_support_config.get("choice_fields") or []), start=1):
            spec = dict(raw_spec or {})
            filter_expression = str(spec.get("filter") or "").strip()
            if filter_expression and "{" in filter_expression:
                try:
                    spec["filter"] = filter_expression.format(**effective_support_config)
                except (IndexError, KeyError, ValueError):
                    spec["filter"] = filter_expression
            category = str(spec.get("category") or "spell_known").strip() or "spell_known"
            fields.extend(
                _build_structured_spell_choice_fields_from_spec(
                    title=str(manager_entry.get("title") or "Feature").strip() or "Feature",
                    category=category,
                    spec_index=spec_index,
                    spec={
                        **spec,
                        **source_row_payload,
                        "spell_access_type": str(spec.get("access_type") or "").strip(),
                        "spell_access_uses": spec.get("access_uses"),
                        "spell_access_reset_on": str(spec.get("access_reset_on") or "").strip(),
                    },
                    spell_catalog=spell_catalog,
                    values=values,
                    default_label_prefix="Granted Spell",
                    default_help_text="Choose a feature-granted spell.",
                    kind=str(
                        spec.get("kind")
                        or ("campaign_spell_managed" if category == "spell_managed" else f"campaign_spell_{category}")
                    ).strip()
                    or ("campaign_spell_managed" if category == "spell_managed" else f"campaign_spell_{category}"),
                    field_name_builder=lambda field_category, current_spec_index, choice_index, field_prefix=field_prefix: _campaign_spell_manager_choice_field_name(
                        field_prefix,
                        field_category,
                        current_spec_index,
                        choice_index,
                    ),
                )
            )
    return fields


def _automatic_campaign_feature_spell_manager_grants(
    *,
    feature_entries: list[dict[str, Any]] | None,
    values: dict[str, str],
    field_prefix_base: str,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for manager_entry in _campaign_feature_spell_manager_entries(
        feature_entries,
        field_prefix_base=field_prefix_base,
    ):
        support_config = dict(manager_entry.get("support_config") or {})
        resolved_support_config = _selected_campaign_feature_spell_manager_config(manager_entry, values)
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            continue
        effective_support_config = resolved_support_config or support_config
        source_row_payload = _campaign_feature_spell_manager_source_row_payload(
            manager_entry,
            support_config=effective_support_config,
        )
        source_row_id = str(source_row_payload.get("spell_source_row_id") or "").strip()
        for raw_grant in list(effective_support_config.get("automatic_grants") or []):
            grant = dict(raw_grant or {})
            spell_name = str(grant.get("spell") or "").strip()
            if not spell_name:
                continue
            marker = (source_row_id, normalize_lookup(spell_name))
            if marker in seen:
                continue
            seen.add(marker)
            grants.append(
                {
                    "name": spell_name,
                    "prefer_known_mark": bool(grant.get("prefer_known_mark", True)),
                    **source_row_payload,
                    "spell_access_type": str(grant.get("access_type") or "").strip(),
                    "spell_access_uses": grant.get("access_uses"),
                    "spell_access_reset_on": str(grant.get("access_reset_on") or "").strip(),
                }
            )
    return grants


def _apply_campaign_feature_spell_manager_payloads(
    feature_entries: list[dict[str, Any]] | None,
    *,
    values: dict[str, str],
    field_prefix_base: str,
) -> list[dict[str, Any]]:
    next_entries = [dict(feature_entry or {}) for feature_entry in list(feature_entries or [])]
    for manager_entry in _campaign_feature_spell_manager_entries(
        next_entries,
        field_prefix_base=field_prefix_base,
    ):
        support_config = dict(manager_entry.get("support_config") or {})
        resolved_support_config = _selected_campaign_feature_spell_manager_config(manager_entry, values)
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            continue
        effective_support_config = resolved_support_config or support_config
        spell_manager = _structured_spell_manager_payload(
            support_config=effective_support_config,
            source_row_payload=_campaign_feature_spell_manager_source_row_payload(
                manager_entry,
                support_config=effective_support_config,
            ),
        )
        if not spell_manager:
            continue
        feature_index = int(manager_entry.get("feature_index") or 0)
        if 0 <= feature_index < len(next_entries):
            next_entries[feature_index]["spell_manager"] = spell_manager
    return next_entries


def _apply_selected_campaign_feature_spell_manager_fields_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    feature_entries: list[dict[str, Any]] | None,
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    field_prefix_base: str,
    class_row_id: str = "",
) -> None:
    for manager_entry in _campaign_feature_spell_manager_entries(
        feature_entries,
        field_prefix_base=field_prefix_base,
    ):
        support_config = dict(manager_entry.get("support_config") or {})
        resolved_support_config = _selected_campaign_feature_spell_manager_config(manager_entry, values)
        if list(support_config.get("source_options") or []) and not resolved_support_config:
            continue
        effective_support_config = resolved_support_config or support_config
        source_row_payload = _campaign_feature_spell_manager_source_row_payload(
            manager_entry,
            support_config=effective_support_config,
        )
        field_prefix = str(manager_entry.get("field_prefix") or "").strip()
        for spec_index, raw_spec in enumerate(list(effective_support_config.get("choice_fields") or []), start=1):
            spec = dict(raw_spec or {})
            filter_expression = str(spec.get("filter") or "").strip()
            if filter_expression and "{" in filter_expression:
                try:
                    spec["filter"] = filter_expression.format(**effective_support_config)
                except (IndexError, KeyError, ValueError):
                    spec["filter"] = filter_expression
            category = str(spec.get("category") or "spell_known").strip() or "spell_known"
            count = max(int(spec.get("count") or 1), 1)
            for choice_index in range(1, count + 1):
                field_name = _campaign_spell_manager_choice_field_name(
                    field_prefix,
                    category,
                    spec_index,
                    choice_index,
                )
                selected_value = str(values.get(field_name) or "").strip()
                if not selected_value:
                    continue
                support_kwargs = {
                    **source_row_payload,
                    "spell_access_type": str(spec.get("access_type") or "").strip(),
                    "spell_access_uses": spec.get("access_uses"),
                    "spell_access_reset_on": str(spec.get("access_reset_on") or "").strip(),
                }
                if category == "known":
                    _add_bonus_known_spell_to_payloads(
                        spells_by_key,
                        selected_value=selected_value,
                        spell_catalog=spell_catalog,
                        class_row_id=class_row_id,
                        prefer_known_mark=bool(spec.get("prefer_known_mark", True)),
                        **_spell_payload_support_kwargs(support_kwargs),
                    )
                    continue
                _add_spell_to_payloads(
                    spells_by_key,
                    selected_value=selected_value,
                    spell_catalog=spell_catalog,
                    mark=str(spec.get("spell_mark") or spec.get("mark") or "").strip(),
                    is_always_prepared=bool(
                        spec.get("spell_is_always_prepared", spec.get("always_prepared"))
                    ),
                    is_ritual=bool(spec.get("spell_is_ritual", spec.get("ritual"))),
                    class_row_id=class_row_id,
                    **_spell_payload_support_kwargs(support_kwargs),
                )


def _iter_unlocked_additional_spell_values(
    raw_map: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[Any]:
    values: list[Any] = []
    for raw_unlock_level, raw_value in dict(raw_map or {}).items():
        if str(raw_unlock_level).strip() == "_":
            values.append(raw_value)
            continue
        unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
        if unlock_level is None:
            continue
        if exact_level is not None:
            if unlock_level != exact_level:
                continue
        elif unlock_level > target_level:
            continue
        values.append(raw_value)
    return values


def _extract_feat_known_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("known"), target_level=target_level):
        specs.extend(_extract_choose_additional_spell_specs(raw_value))
    return specs


def _extract_feat_prepared_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("prepared"), target_level=target_level):
        for spec in _extract_choose_additional_spell_specs(raw_value):
            specs.append({**spec, "spell_is_always_prepared": True})
    return specs


def _extract_feat_innate_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("innate"), target_level=target_level):
        innate_block = dict(raw_value or {})
        daily_map = dict(innate_block.get("daily") or {})
        for raw_daily_uses, daily_values in daily_map.items():
            ritual_filter = False
            for spec in _extract_choose_additional_spell_specs(daily_values):
                ritual_filter = _additional_spell_filter_requires_ritual(str(spec.get("filter") or ""))
                specs.append(
                    {
                        **spec,
                        "spell_mark": _format_innate_spell_mark(raw_daily_uses, is_ritual=ritual_filter),
                        "spell_is_ritual": ritual_filter,
                    }
                )
    return specs


def _extract_additional_known_choice_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(additional_spells or []):
            if not isinstance(block, dict):
                continue
            known_map = dict(block.get("known") or {})
            for raw_unlock_level, known_values in known_map.items():
                unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
                if unlock_level is None:
                    continue
                if exact_level is not None:
                    if unlock_level != exact_level:
                        continue
                elif unlock_level > target_level:
                    continue
                specs.extend(_extract_choose_additional_spell_specs(known_values))
    return specs


def _extract_choose_additional_spell_specs(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(_extract_choose_additional_spell_specs(item))
        return specs
    if not isinstance(raw_value, dict):
        return []
    specs: list[dict[str, Any]] = []
    choose_filter = str(raw_value.get("choose") or "").strip()
    if choose_filter:
        specs.append({"filter": choose_filter, "count": max(int(raw_value.get("count") or 1), 1)})
    if "_" in raw_value:
        specs.extend(_extract_choose_additional_spell_specs(raw_value.get("_")))
    return specs


def _build_additional_spell_filter_options(
    filter_expression: str,
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    criteria = _parse_additional_spell_filter(filter_expression)
    if not criteria:
        return []
    entries = list(spell_catalog.get("entries") or [])
    class_name = str(criteria.get("class_name") or "").strip()
    level = criteria.get("level")
    if class_name and level is not None:
        titles = list(
            dict(dict(spell_catalog.get("phb_level_one_lists") or {}).get(class_name) or {}).get(str(level)) or []
        )
        options = (
            _build_spell_options_from_titles(titles, spell_catalog)
            if titles
            else [
                _choice_option(entry.title, entry.slug or entry.title)
                for entry in entries
                if _spell_entry_matches_additional_filter(entry, criteria)
            ]
        )
    else:
        options = [
            _choice_option(entry.title, entry.slug or entry.title)
            for entry in entries
            if _spell_entry_matches_additional_filter(entry, criteria)
        ]
    seen_values: set[str] = set()
    filtered_options: list[dict[str, str]] = []
    for option in options:
        value = str(option.get("value") or "").strip()
        if not value:
            continue
        entry = _resolve_spell_entry(value, spell_catalog)
        if entry is None:
            entry = _resolve_spell_entry(str(option.get("label") or "").strip(), spell_catalog)
        if entry is None:
            continue
        if entry is not None and not _spell_entry_matches_additional_filter(entry, criteria):
            continue
        if value in seen_values:
            continue
        seen_values.add(value)
        filtered_options.append(dict(option))
    return filtered_options


def _parse_additional_spell_filter(filter_expression: str) -> dict[str, Any]:
    criteria: dict[str, Any] = {}
    for fragment in str(filter_expression or "").split("|"):
        key, _, value = fragment.partition("=")
        normalized_key = normalize_lookup(key).replace(" ", "_")
        clean_value = str(value or "").strip()
        if not normalized_key or not clean_value:
            continue
        if normalized_key == "level":
            try:
                criteria["level"] = int(clean_value)
            except ValueError:
                continue
        elif normalized_key == "class":
            criteria["class_name"] = _humanize_words(clean_value)
        elif normalized_key == "school":
            criteria["school"] = clean_value.upper()
        elif normalized_key in {"components_miscellaneous", "miscellaneous"} and normalize_lookup(clean_value) == "ritual":
            criteria["ritual"] = True
    return criteria


def _additional_spell_filter_requires_ritual(filter_expression: str) -> bool:
    return bool(_parse_additional_spell_filter(filter_expression).get("ritual"))


def _spell_entry_matches_additional_filter(entry: SystemsEntryRecord, criteria: dict[str, Any]) -> bool:
    metadata = dict(entry.metadata or {})
    level = criteria.get("level")
    if level is not None and _spell_entry_level(entry) != int(level):
        return False
    school = str(criteria.get("school") or "").strip().upper()
    if school and str(metadata.get("school") or "").strip().upper() != school:
        return False
    if bool(criteria.get("ritual")) and not bool(metadata.get("ritual")):
        return False
    class_name = str(criteria.get("class_name") or "").strip()
    if class_name:
        normalized_class_name = normalize_lookup(class_name)
        class_lists = dict(metadata.get("class_lists") or {})
        has_dynamic_match = any(
            normalized_class_name in {normalize_lookup(title) for title in list(titles or []) if str(title).strip()}
            for titles in class_lists.values()
        )
        if not has_dynamic_match:
            allowed_titles = set(
                dict(dict(_load_phb_level_one_spell_lists() or {}).get(class_name) or {}).get(str(_spell_entry_level(entry))) or []
            )
            if entry.title not in allowed_titles:
                return False
    return True


def _spell_options_are_cantrips(options: list[dict[str, str]], spell_catalog: dict[str, Any]) -> bool:
    if not options:
        return False
    for option in options:
        entry = _resolve_spell_entry(str(option.get("value") or "").strip(), spell_catalog)
        if entry is None or _spell_entry_level(entry) != 0:
            return False
    return True


def _spell_entry_level(entry: SystemsEntryRecord) -> int:
    return int(dict(entry.metadata or {}).get("level") or 0)


def _build_spell_options_from_titles(
    titles: list[str],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    by_title = dict(spell_catalog.get("by_title") or {})
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for title in titles:
        entry = by_title.get(normalize_lookup(title))
        value = entry.slug if entry is not None else title
        label = entry.title if entry is not None else title
        if value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _expanded_spell_titles_for_level(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    spell_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    titles: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        titles.extend(
            _extract_expanded_additional_spell_values(
                additional_spells,
                spell_catalog=spell_catalog,
                spell_level=spell_level,
            )
        )
    return _dedupe_preserve_order(titles)


def _extract_expanded_additional_spell_values(
    additional_spells: Any,
    *,
    spell_catalog: dict[str, Any],
    spell_level: int,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        expanded_map = dict(block.get("expanded") or {})
        for raw_spell_level, expanded_values in expanded_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_spell_level)
            if unlock_level != spell_level:
                continue
            values.extend(_resolve_additional_spell_option_titles(expanded_values, spell_catalog))
    return _dedupe_preserve_order(values)


def _additional_spell_metadata_entries(
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    *,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[Any]:
    values: list[Any] = []
    seen_entries: set[str] = set()
    for entry in (selected_class, selected_subclass):
        metadata = dict((entry.metadata if entry is not None else {}) or {})
        additional_spells = _spell_metadata_value(metadata, "additional_spells", "additionalSpells")
        if additional_spells:
            values.append(additional_spells)
        if isinstance(entry, SystemsEntryRecord):
            seen_entries.add(str(entry.entry_key or entry.slug or entry.title or ""))
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            campaign_option = dict(feature_entry.get("campaign_option") or {})
            additional_spells = _spell_metadata_value(campaign_option, "additional_spells", "additionalSpells")
            if additional_spells:
                values.append(additional_spells)
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if not entry_key or entry_key in seen_entries:
            continue
        additional_spells = _spell_metadata_value(dict(entry.metadata or {}), "additional_spells", "additionalSpells")
        if not additional_spells:
            continue
        values.append(additional_spells)
        seen_entries.add(entry_key)
    inferred_blocks = _inferred_always_prepared_additional_spell_blocks(feature_entries)
    if inferred_blocks:
        values.append(inferred_blocks)
    return values


def _spell_support_metadata_entries(
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    *,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[Any]:
    values: list[Any] = []
    seen_entries: set[str] = set()
    for entry in (selected_class, selected_subclass):
        metadata = dict((entry.metadata if entry is not None else {}) or {})
        spell_support = _spell_metadata_value(metadata, "spell_support", "spellSupport")
        if spell_support:
            values.append(spell_support)
        if isinstance(entry, SystemsEntryRecord):
            seen_entries.add(str(entry.entry_key or entry.slug or entry.title or ""))
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            campaign_option = dict(feature_entry.get("campaign_option") or {})
            spell_support = _spell_metadata_value(campaign_option, "spell_support", "spellSupport")
            if spell_support:
                values.append(spell_support)
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if entry_key and entry_key not in seen_entries:
            spell_support = _spell_metadata_value(dict(entry.metadata or {}), "spell_support", "spellSupport")
            if spell_support:
                values.append(spell_support)
                seen_entries.add(entry_key)
    return values


def _spell_metadata_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _spell_flag_is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        return normalize_lookup(value) in {"1", "true", "yes", "always", "prepared", "always prepared"}
    return False


def _raw_spell_grant_is_always_prepared(raw_value: Any, *, category: str = "") -> bool:
    payload = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    if not payload:
        return normalize_lookup(category) == "prepared"
    for key in (
        "is_always_prepared",
        "always_prepared",
        "isAlwaysPrepared",
        "alwaysPrepared",
        "prepared",
    ):
        if _spell_flag_is_truthy(payload.get(key)):
            return True
    return normalize_lookup(category) == "prepared"


def _spell_payload_has_legacy_always_prepared_source_label(spell_payload: dict[str, Any]) -> bool:
    source_label = str(
        spell_payload.get("grant_source_label")
        or spell_payload.get("source")
        or ""
    ).strip()
    return normalize_lookup("always prepared") in normalize_lookup(source_label)


def _spell_payload_is_always_prepared(spell_payload: dict[str, Any]) -> bool:
    return bool(spell_payload.get("is_always_prepared")) or _spell_payload_has_legacy_always_prepared_source_label(
        spell_payload
    )


def _spell_mark_tokens(mark: str) -> set[str]:
    tokens: set[str] = set()
    for part in re.split(r"\+", str(mark or "")):
        normalized_part = normalize_lookup(part)
        if normalized_part:
            tokens.add(normalized_part)
    return tokens


def _canonicalize_legacy_spell_mark(
    *,
    mark: str,
    spell_level: int | None,
    spell_mode: str = "",
) -> str:
    clean_mark = str(mark or "").strip()
    tokens = _spell_mark_tokens(clean_mark)
    if "granted" in tokens:
        return "Granted"
    if spell_level == 0 or "cantrip" in tokens:
        return "Cantrip"
    if spell_mode == "ritual_book":
        return "Ritual Book"
    if not clean_mark:
        return ""
    if spell_mode == "wizard":
        if "spellbook" in tokens:
            return "Prepared + Spellbook" if "prepared" in tokens else "Spellbook"
        if tokens & {"o", "p", "po", "prepared"}:
            return "Prepared + Spellbook"
        return "Spellbook"
    if spell_mode == "prepared":
        if "known" in tokens:
            return "Known"
        if tokens & {"o", "p", "po", "prepared"}:
            return "Prepared"
        return clean_mark
    if spell_mode == "known":
        return "Known"
    if spell_mode == "ritual_book":
        return "Ritual Book"
    if "spellbook" in tokens:
        return "Prepared + Spellbook" if "prepared" in tokens else "Spellbook"
    if "ritual book" in tokens:
        return "Ritual Book"
    if "known" in tokens:
        return "Known"
    if tokens == {"o"}:
        return ""
    if tokens & {"p", "po", "prepared"}:
        return "Prepared"
    return clean_mark


def _spell_payload_spell_level(
    spell_payload: dict[str, Any],
    *,
    spell_catalog: dict[str, Any] | None = None,
) -> int | None:
    spell_entry = _resolve_spell_entry(_spell_payload_key(spell_payload), dict(spell_catalog or {}))
    if spell_entry is None:
        spell_name = str(spell_payload.get("name") or "").strip()
        if spell_name:
            spell_entry = _resolve_spell_entry(spell_name, dict(spell_catalog or {}))
    if spell_entry is not None:
        metadata = dict(spell_entry.metadata or {})
        if "level" in metadata:
            try:
                return int(metadata.get("level") or 0)
            except (TypeError, ValueError):
                return None
    for key in ("spell_level", "level"):
        if key not in spell_payload:
            continue
        raw_level = spell_payload.get(key)
        if raw_level in {"", None}:
            return None
        try:
            return int(raw_level)
        except (TypeError, ValueError):
            return None
    return None


def _canonicalize_legacy_spell_payload_marks(
    spell_payloads: list[dict[str, Any]] | None,
    *,
    spell_catalog: dict[str, Any] | None = None,
    spellcasting_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    row_modes_by_id = {
        str(row.get("class_row_id") or "").strip(): str(row.get("spell_mode") or "").strip()
        for row in list(spellcasting_rows or [])
        if str(row.get("class_row_id") or "").strip()
    }
    canonicalized_payloads: list[dict[str, Any]] = []
    for raw_payload in list(spell_payloads or []):
        spell_payload = dict(raw_payload or {})
        class_row_id = _spell_payload_class_row_id(spell_payload)
        spell_mode = str(
            spell_payload.get("spell_source_mode")
            or row_modes_by_id.get(class_row_id)
            or ""
        ).strip()
        canonical_mark = _canonicalize_legacy_spell_mark(
            mark=str(spell_payload.get("mark") or "").strip(),
            spell_level=_spell_payload_spell_level(spell_payload, spell_catalog=spell_catalog),
            spell_mode=spell_mode,
        )
        if canonical_mark or "mark" in spell_payload:
            spell_payload["mark"] = canonical_mark
        canonicalized_payloads.append(spell_payload)
    return _normalize_spell_payloads(canonicalized_payloads)


def _collect_entry_body_text_fragments(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        cleaned = _clean_embedded_text(raw_value)
        return [cleaned] if cleaned else []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_collect_entry_body_text_fragments(item))
        return values
    if not isinstance(raw_value, dict):
        return []
    values: list[str] = []
    for key in ("name", "caption"):
        cleaned = _clean_embedded_text(str(raw_value.get(key) or ""))
        if cleaned:
            values.append(cleaned)
    for key in ("entries", "entry", "items"):
        if key in raw_value:
            values.extend(_collect_entry_body_text_fragments(raw_value.get(key)))
    return values


def _collect_entry_body_tables(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        tables: list[dict[str, Any]] = []
        for item in raw_value:
            tables.extend(_collect_entry_body_tables(item))
        return tables
    if not isinstance(raw_value, dict):
        return []
    tables: list[dict[str, Any]] = []
    if normalize_lookup(str(raw_value.get("type") or "")) == "table":
        tables.append(dict(raw_value))
    for key in ("entries", "entry", "items"):
        if key in raw_value:
            tables.extend(_collect_entry_body_tables(raw_value.get(key)))
    return tables


def _normalized_entry_body_text(entry: SystemsEntryRecord | None) -> str:
    if not isinstance(entry, SystemsEntryRecord):
        return ""
    return normalize_lookup(" ".join(_collect_entry_body_text_fragments((entry.body or {}).get("entries"))))


def _entry_body_has_self_contained_always_prepared_context(entry: SystemsEntryRecord | None) -> bool:
    body_text = _normalized_entry_body_text(entry)
    if not body_text:
        return False
    return normalize_lookup("always have it prepared") in body_text or (
        normalize_lookup("always have") in body_text
        and normalize_lookup("prepared") in body_text
        and normalize_lookup("spell") in body_text
    )


def _entry_body_has_domain_spell_grant_context(entry: SystemsEntryRecord | None) -> bool:
    body_text = _normalized_entry_body_text(entry)
    if normalize_lookup("domain spell") not in body_text:
        return False
    return (
        normalize_lookup("add the listed spells to your spells prepared") in body_text
        or normalize_lookup("you gain domain spells") in body_text
        or normalize_lookup("see the divine domain class feature") in body_text
    )


def _feature_entries_have_domain_spell_always_prepared_context(
    feature_entries: list[dict[str, Any]] | None,
    *,
    excluded_entry_key: str = "",
) -> bool:
    excluded_key = str(excluded_entry_key or "").strip()
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if entry_key and entry_key == excluded_key:
            continue
        body_text = _normalized_entry_body_text(entry)
        if normalize_lookup("domain spell") not in body_text:
            continue
        if normalize_lookup("always have it prepared") in body_text or (
            normalize_lookup("always have") in body_text and normalize_lookup("prepared") in body_text
        ):
            return True
    return False


def _extract_spell_titles_from_table_cell(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_extract_spell_titles_from_table_cell(item))
        return _dedupe_preserve_order(values)
    if isinstance(raw_value, dict):
        values: list[str] = []
        for key in ("_", "entries", "entry", "items"):
            if key in raw_value:
                values.extend(_extract_spell_titles_from_table_cell(raw_value.get(key)))
        return _dedupe_preserve_order(values)
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return []
    matches = re.findall(r"\{@spell ([^}]+)\}", clean_value)
    if matches:
        return _dedupe_preserve_order([_normalize_additional_spell_reference(match) for match in matches])
    cleaned = _clean_embedded_text(clean_value)
    if not cleaned:
        return []
    return _dedupe_preserve_order([part.strip() for part in re.split(r"[,;]", cleaned) if part.strip()])


def _extract_prepared_spells_from_supported_table(raw_table: dict[str, Any] | None) -> dict[str, list[str]]:
    table = dict(raw_table or {})
    if normalize_lookup(str(table.get("type") or "")) != "table":
        return {}
    labels = [
        normalize_lookup(_clean_embedded_text(str(label or "")))
        for label in list(table.get("colLabels") or [])
    ]
    level_index = next((index for index, label in enumerate(labels) if "level" in label), -1)
    spell_indices = [index for index, label in enumerate(labels) if label in {"spell", "spells"} or "spell" in label]
    if level_index < 0 or not spell_indices:
        return {}
    prepared: dict[str, list[str]] = {}
    for raw_row in list(table.get("rows") or []):
        if not isinstance(raw_row, (list, tuple)):
            continue
        row = list(raw_row)
        if level_index >= len(row):
            continue
        unlock_level = _parse_additional_spell_unlock_level(row[level_index])
        if unlock_level is None:
            continue
        values: list[str] = []
        for spell_index in spell_indices:
            if spell_index >= len(row):
                continue
            values.extend(_extract_spell_titles_from_table_cell(row[spell_index]))
        if not values:
            continue
        prepared.setdefault(str(unlock_level), [])
        prepared[str(unlock_level)].extend(values)
    return {level: _dedupe_preserve_order(values) for level, values in prepared.items() if values}


def _inferred_always_prepared_additional_spell_blocks(
    feature_entries: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    inferred_blocks: list[dict[str, Any]] = []
    seen_entries: set[str] = set()
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            continue
        if normalize_lookup(entry.entry_type) not in {
            normalize_lookup("classfeature"),
            normalize_lookup("subclassfeature"),
        }:
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if not entry_key or entry_key in seen_entries:
            continue
        seen_entries.add(entry_key)
        metadata = dict(entry.metadata or {})
        if _spell_metadata_value(metadata, "additional_spells", "additionalSpells") or _spell_metadata_value(
            metadata,
            "spell_support",
            "spellSupport",
        ):
            continue
        prepared: dict[str, list[str]] = {}
        for table in _collect_entry_body_tables((entry.body or {}).get("entries")):
            for level, values in _extract_prepared_spells_from_supported_table(table).items():
                prepared.setdefault(level, [])
                prepared[level].extend(values)
        prepared = {level: _dedupe_preserve_order(values) for level, values in prepared.items() if values}
        if not prepared:
            continue
        if not (
            _entry_body_has_self_contained_always_prepared_context(entry)
            or (
                _entry_body_has_domain_spell_grant_context(entry)
                and _feature_entries_have_domain_spell_always_prepared_context(
                    feature_entries,
                    excluded_entry_key=entry_key,
                )
            )
        ):
            continue
        inferred_blocks.append({"prepared": prepared})
    return inferred_blocks


def _spell_support_choice_field_name(
    field_prefix: str,
    category: str,
    spec_index: int,
    choice_index: int,
) -> str:
    return f"{field_prefix}_{category}_{spec_index}_{choice_index}"


def _spell_support_replacement_field_name(
    field_prefix: str,
    category: str,
    spec_index: int,
    choice_index: int,
    part: str,
) -> str:
    return f"{field_prefix}_replace_{category}_{spec_index}_{part}_{choice_index}"


def _automatic_spell_support_grants(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        grants.extend(
            _extract_spell_support_grants(
                spell_support,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_spell_support_grants(grants)


def _automatic_spell_support_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for grant in _automatic_spell_support_grants(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(str(grant.get("value") or "").strip(), spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _extract_spell_support_grants(
    spell_support: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for block in list(spell_support or []):
        if not isinstance(block, dict):
            continue
        block_support_kwargs = _spell_support_support_kwargs(block)
        for raw_value in _iter_unlocked_additional_spell_values(
            block.get("grants", block.get("fixed")),
            target_level=target_level,
            exact_level=exact_level,
        ):
            grants.extend(
                _extract_spell_support_grants_from_value(
                    raw_value,
                    inherited_support_kwargs=block_support_kwargs,
                )
            )
    return grants


def _extract_spell_support_grants_from_value(
    raw_value: Any,
    *,
    inherited_support_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        grants: list[dict[str, Any]] = []
        for item in raw_value:
            grants.extend(
                _extract_spell_support_grants_from_value(
                    item,
                    inherited_support_kwargs=inherited_support_kwargs,
                )
            )
        return grants
    if isinstance(raw_value, str):
        clean_value = _normalize_additional_spell_reference(raw_value)
        return (
            [
                {
                    "value": clean_value,
                    "mark": "Granted",
                    "always_prepared": False,
                    "ritual": False,
                    "bonus_known": False,
                    **dict(inherited_support_kwargs or {}),
                }
            ]
            if clean_value
            else []
        )
    if not isinstance(raw_value, dict):
        return []

    grants: list[dict[str, Any]] = []
    if "_" in raw_value:
        grants.extend(
            _extract_spell_support_grants_from_value(
                raw_value.get("_"),
                inherited_support_kwargs=inherited_support_kwargs,
            )
        )
    clean_value = _normalize_additional_spell_reference(
        str(
            raw_value.get("spell")
            or raw_value.get("value")
            or raw_value.get("title")
            or raw_value.get("slug")
            or ""
        )
    )
    if not clean_value:
        return grants
    normalized_mark = str(raw_value.get("mark") or "").strip()
    bonus_known = bool(raw_value.get("bonus_known") or raw_value.get("is_bonus_known"))
    grant_category = normalize_lookup(str(raw_value.get("category") or raw_value.get("kind") or "").strip())
    if not bonus_known and normalize_lookup(normalized_mark) in {"known", "cantrip"}:
        bonus_known = True
        normalized_mark = ""
    support_kwargs = _spell_support_support_kwargs(
        raw_value,
        inherited_support_kwargs=inherited_support_kwargs,
    )
    grants.append(
        {
            "value": clean_value,
            "mark": normalized_mark,
            "always_prepared": _raw_spell_grant_is_always_prepared(raw_value, category=grant_category),
            "ritual": bool(raw_value.get("ritual") or raw_value.get("is_ritual")),
            "bonus_known": bonus_known,
            **support_kwargs,
        }
    )
    return grants


def _dedupe_spell_support_grants(grants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool, bool, bool, str, str, str, str, str, str, str, str, int, str]] = set()
    for grant in list(grants or []):
        payload = dict(grant or {})
        value = str(payload.get("value") or "").strip()
        if not value:
            continue
        support_payload = _spell_payload_support_kwargs(payload)
        marker = (
            value.casefold(),
            str(payload.get("mark") or "").strip().casefold(),
            bool(payload.get("always_prepared")),
            bool(payload.get("ritual")),
            bool(payload.get("bonus_known")),
            str(support_payload.get("spell_source_row_id") or "").strip(),
            str(support_payload.get("spell_source_row_kind") or "").strip(),
            str(support_payload.get("spell_source_row_title") or "").strip(),
            str(support_payload.get("spell_source_ability_key") or "").strip(),
            str(support_payload.get("spell_source_mode") or "").strip(),
            str(support_payload.get("spell_source_spell_list_class_name") or "").strip(),
            str(support_payload.get("grant_source_label") or "").strip(),
            str(support_payload.get("spell_access_type") or "").strip(),
            int(support_payload.get("spell_access_uses") or 0),
            str(support_payload.get("spell_access_reset_on") or "").strip(),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(payload)
    return deduped


def _extract_spell_support_choice_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(spell_support or []):
            if not isinstance(block, dict):
                continue
            block_support_kwargs = _spell_support_support_kwargs(block)
            for raw_value in _iter_unlocked_additional_spell_values(
                block.get("choices", block.get("select")),
                target_level=target_level,
                exact_level=exact_level,
            ):
                specs.extend(
                    _extract_spell_support_choice_specs_from_value(
                        raw_value,
                        inherited_support_kwargs=block_support_kwargs,
                    )
                )
    return specs


def _extract_spell_support_choice_specs_from_value(
    raw_value: Any,
    *,
    inherited_support_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(
                _extract_spell_support_choice_specs_from_value(
                    item,
                    inherited_support_kwargs=inherited_support_kwargs,
                )
            )
        return specs
    if not isinstance(raw_value, dict):
        return []

    specs: list[dict[str, Any]] = []
    if "_" in raw_value:
        specs.extend(
            _extract_spell_support_choice_specs_from_value(
                raw_value.get("_"),
                inherited_support_kwargs=inherited_support_kwargs,
            )
        )
    category = normalize_lookup(str(raw_value.get("category") or raw_value.get("kind") or "").strip())
    if category not in {"known", "prepared", "granted"}:
        return specs
    filter_expression = str(raw_value.get("filter") or raw_value.get("choose") or "").strip()
    option_values = _flatten_additional_spell_values(raw_value.get("options", raw_value.get("spells")))
    if not filter_expression and not option_values:
        return specs
    support_kwargs = _spell_support_support_kwargs(
        raw_value,
        inherited_support_kwargs=inherited_support_kwargs,
    )
    specs.append(
        {
            "category": category,
            "filter": filter_expression,
            "options": option_values,
            "count": max(int(raw_value.get("count") or 1), 1),
            "label_prefix": str(raw_value.get("label_prefix") or "").strip(),
            "help_text": str(raw_value.get("help_text") or "").strip(),
            "always_prepared": _raw_spell_grant_is_always_prepared(raw_value, category=category),
            "ritual": bool(raw_value.get("ritual") or raw_value.get("is_ritual")),
            "mark": str(raw_value.get("mark") or ("Granted" if category == "granted" else "")).strip(),
            "spell_source_row_id": str(support_kwargs.get("spell_source_row_id") or "").strip(),
            "spell_source_row_kind": str(support_kwargs.get("spell_source_row_kind") or "").strip(),
            "spell_source_row_title": str(support_kwargs.get("spell_source_row_title") or "").strip(),
            "spell_source_ability_key": str(support_kwargs.get("spell_source_ability_key") or "").strip(),
            "spell_source_mode": str(support_kwargs.get("spell_source_mode") or "").strip(),
            "spell_source_spell_list_class_name": str(
                support_kwargs.get("spell_source_spell_list_class_name") or ""
            ).strip(),
            "grant_source_label": str(support_kwargs.get("grant_source_label") or "").strip(),
            "spell_access_type": str(support_kwargs.get("spell_access_type") or "").strip(),
            "spell_access_uses": support_kwargs.get("spell_access_uses"),
            "spell_access_reset_on": str(support_kwargs.get("spell_access_reset_on") or "").strip(),
        }
    )
    return specs


def _extract_spell_support_replacement_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(spell_support or []):
            if not isinstance(block, dict):
                continue
            for raw_value in _iter_unlocked_additional_spell_values(
                block.get("replacement", block.get("replacements")),
                target_level=target_level,
                exact_level=exact_level,
            ):
                specs.extend(_extract_spell_support_replacement_specs_from_value(raw_value))
    return specs


def _extract_spell_support_replacement_specs_from_value(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(_extract_spell_support_replacement_specs_from_value(item))
        return specs
    if not isinstance(raw_value, dict):
        return []

    specs: list[dict[str, Any]] = []
    if "_" in raw_value:
        specs.extend(_extract_spell_support_replacement_specs_from_value(raw_value.get("_")))
    category = normalize_lookup(str(raw_value.get("category") or raw_value.get("kind") or "known").strip()) or "known"
    if category not in {"known", "prepared", "granted"}:
        return specs
    to_payload = dict(raw_value.get("to") or {}) if isinstance(raw_value.get("to"), dict) else {}
    if not to_payload:
        to_payload = dict(raw_value)
    from_payload = dict(raw_value.get("from") or {}) if isinstance(raw_value.get("from"), dict) else {}
    from_filter = str(from_payload.get("filter") or from_payload.get("choose") or "").strip()
    from_options = _flatten_additional_spell_values(from_payload.get("options", from_payload.get("spells")))
    to_filter = str(to_payload.get("filter") or to_payload.get("choose") or "").strip()
    to_options = _flatten_additional_spell_values(to_payload.get("options", to_payload.get("spells")))
    if not to_filter and not to_options:
        return specs
    specs.append(
        {
            "category": category,
            "count": max(int(raw_value.get("count") or 1), 1),
            "from_mark": str(from_payload.get("mark") or "").strip(),
            "from_level": int(from_payload.get("level") or 0),
            "from_filter": from_filter,
            "from_options": from_options,
            "to_filter": to_filter,
            "to_options": to_options,
            "mark": str(raw_value.get("mark") or to_payload.get("mark") or "").strip(),
            "always_prepared": (
                _raw_spell_grant_is_always_prepared(raw_value, category=category)
                or _raw_spell_grant_is_always_prepared(to_payload, category=category)
            ),
            "ritual": bool(raw_value.get("ritual") or to_payload.get("ritual")),
            "help_text_from": str(raw_value.get("help_text_from") or "").strip(),
            "help_text_to": str(raw_value.get("help_text_to") or "").strip(),
        }
    )
    return specs


def _automatic_feat_known_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[str]:
    spell_values: list[str] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_known_additional_spell_values([block], target_level=target_level))
    return _dedupe_preserve_order(spell_values)


def _automatic_feat_prepared_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[str]:
    spell_values: list[str] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_prepared_additional_spell_values([block], target_level=target_level))
    return _dedupe_preserve_order(spell_values)


def _automatic_feat_innate_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    spell_values: list[dict[str, Any]] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_innate_additional_spell_values([block], target_level=target_level))
    return _dedupe_innate_spell_values(spell_values)


def _automatic_known_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    values: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_known_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_preserve_order(values)


def _automatic_known_spell_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for selected_value in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(selected_value, spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _extract_known_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        known_map = dict(block.get("known") or {})
        for raw_unlock_level, known_values in known_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
            if unlock_level is None:
                continue
            if exact_level is not None:
                if unlock_level != exact_level:
                    continue
            elif unlock_level > target_level:
                continue
            values.extend(_flatten_additional_spell_values(known_values))
    return _dedupe_preserve_order(values)


def _automatic_prepared_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    values: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_prepared_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    for grant in _automatic_spell_support_grants(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        if not bool(grant.get("always_prepared")):
            continue
        grant_value = str(grant.get("value") or "").strip()
        if grant_value:
            values.append(grant_value)
    return _dedupe_preserve_order(values)


def _automatic_prepared_spell_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for selected_value in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(selected_value, spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _automatic_innate_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_innate_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_innate_spell_values(values)


def _extract_prepared_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        prepared_map = dict(block.get("prepared") or {})
        for raw_unlock_level, prepared_values in prepared_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
            if unlock_level is None:
                continue
            if exact_level is not None:
                if unlock_level != exact_level:
                    continue
            elif unlock_level > target_level:
                continue
            values.extend(_flatten_additional_spell_values(prepared_values))
    return _dedupe_preserve_order(values)


def _extract_innate_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        for raw_value in _iter_unlocked_additional_spell_values(
            block.get("innate"),
            target_level=target_level,
            exact_level=exact_level,
        ):
            innate_block = dict(raw_value or {})
            for raw_daily_uses, daily_values in dict(innate_block.get("daily") or {}).items():
                ritual = False
                for spec in _extract_choose_additional_spell_specs(daily_values):
                    ritual = ritual or _additional_spell_filter_requires_ritual(str(spec.get("filter") or ""))
                for spell_name in _flatten_additional_spell_values(daily_values):
                    values.append(
                        {
                            "name": spell_name,
                            "mark": _format_innate_spell_mark(raw_daily_uses, is_ritual=ritual),
                            "is_ritual": ritual,
                        }
                    )
    return _dedupe_innate_spell_values(values)


def _format_innate_spell_mark(raw_daily_uses: Any, *, is_ritual: bool) -> str:
    if is_ritual:
        return "Ritual"
    uses_match = re.search(r"(\d+)", str(raw_daily_uses or "").strip())
    if uses_match is not None:
        return f"{int(uses_match.group(1))} / Long Rest"
    clean_uses = str(raw_daily_uses or "").strip()
    if clean_uses:
        return f"{clean_uses} / Long Rest"
    return "Granted"


def _dedupe_innate_spell_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool]] = set()
    for spell_payload in list(values or []):
        payload = dict(spell_payload or {})
        spell_name = str(payload.get("name") or "").strip()
        mark = str(payload.get("mark") or "").strip()
        is_ritual = bool(payload.get("is_ritual"))
        marker = (normalize_lookup(spell_name), mark, is_ritual)
        if not spell_name or marker in seen:
            continue
        seen.add(marker)
        deduped.append(
            {
                "name": spell_name,
                "mark": mark,
                "is_ritual": is_ritual,
            }
        )
    return deduped


def _parse_additional_spell_unlock_level(raw_value: Any) -> int | None:
    if isinstance(raw_value, int):
        return raw_value
    match = re.search(r"(\d+)", str(raw_value or "").strip())
    if match is None:
        return None
    return int(match.group(1))


def _flatten_additional_spell_values(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        normalized_value = _normalize_additional_spell_reference(raw_value)
        return [normalized_value] if normalized_value else []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_flatten_additional_spell_values(item))
        return values
    if isinstance(raw_value, dict):
        values: list[str] = []
        for key in ("_", "all"):
            if key in raw_value:
                values.extend(_flatten_additional_spell_values(raw_value.get(key)))
        return values
    return []


def _resolve_additional_spell_option_titles(raw_value: Any, spell_catalog: dict[str, Any]) -> list[str]:
    if isinstance(raw_value, str):
        normalized_value = _normalize_additional_spell_reference(raw_value)
        return [normalized_value] if normalized_value else []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_resolve_additional_spell_option_titles(item, spell_catalog))
        return values
    if isinstance(raw_value, dict):
        values: list[str] = []
        if "all" in raw_value:
            values.extend(
                option["label"]
                for option in _build_additional_spell_filter_options(str(raw_value.get("all") or ""), spell_catalog)
            )
        if "_" in raw_value:
            values.extend(_resolve_additional_spell_option_titles(raw_value.get("_"), spell_catalog))
        return values
    return []


def _normalize_additional_spell_reference(raw_value: str) -> str:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return ""
    spell_tag_match = re.fullmatch(r"\{@spell ([^}]+)\}", clean_value)
    if spell_tag_match is not None:
        clean_value = spell_tag_match.group(1)
    if "|" in clean_value:
        clean_value = clean_value.split("|", 1)[0]
    if "#" in clean_value:
        clean_value = clean_value.split("#", 1)[0]
    return clean_value.replace("_", " ").strip()


def _summarize_level_up_spell_choices(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    values: dict[str, str],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    automatic_prepared_feature_entries: list[dict[str, Any]] | None = None,
    extra_option_payloads: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
) -> list[str]:
    existing_spell_rows = [
        dict(row or {})
        for row in list((definition.spellcasting or {}).get("class_rows") or [])
        if isinstance(row, dict)
    ]
    if not existing_spell_rows and class_row_id:
        existing_spell_rows = [{"class_row_id": class_row_id}]
    existing_spell_payload_keys = {
        payload_key
        for spell_payload in _assign_spell_payload_class_rows(
            list((definition.spellcasting or {}).get("spells") or []),
            spellcasting_rows=existing_spell_rows,
        )
        if (payload_key := _spell_payload_map_key(spell_payload))
    }
    simulated_payloads = _build_level_up_spell_payloads(
        current_definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
        automatic_prepared_feature_entries=automatic_prepared_feature_entries,
        selected_campaign_option_payloads=extra_option_payloads,
        class_row_id=class_row_id,
    )

    summaries: list[str] = []
    seen: set[str] = set()
    for spell_payload in simulated_payloads:
        payload_key = _spell_payload_map_key(spell_payload)
        if payload_key and payload_key in existing_spell_payload_keys:
            continue
        label = str(spell_payload.get("name") or "").strip()
        normalized_label = normalize_lookup(label)
        if not label or normalized_label in seen:
            continue
        seen.add(normalized_label)
        summaries.append(label)
    return summaries


def _add_spell_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    mark: str = "",
    is_always_prepared: bool = False,
    is_bonus_known: bool = False,
    is_ritual: bool = False,
    class_row_id: str = "",
    spell_source_row_id: str = "",
    spell_source_row_kind: str = "",
    spell_source_row_title: str = "",
    spell_source_ability_key: str = "",
    spell_source_mode: str = "",
    spell_source_spell_list_class_name: str = "",
    grant_source_label: str = "",
    spell_access_type: str = "",
    spell_access_uses: Any = None,
    spell_access_reset_on: str = "",
) -> None:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    spell_payload = _build_spell_payload(selected_value, spell_entry)
    support_payload = _spell_payload_support_kwargs(
        {
            "spell_source_row_id": spell_source_row_id,
            "spell_source_row_kind": spell_source_row_kind,
            "spell_source_row_title": spell_source_row_title,
            "spell_source_ability_key": spell_source_ability_key,
            "spell_source_mode": spell_source_mode,
            "spell_source_spell_list_class_name": spell_source_spell_list_class_name,
            "grant_source_label": grant_source_label,
            "spell_access_type": spell_access_type,
            "spell_access_uses": spell_access_uses,
            "spell_access_reset_on": spell_access_reset_on,
        }
    )
    if support_payload:
        _apply_spell_payload_support_metadata(spell_payload, support_payload)
    elif str(class_row_id or "").strip():
        spell_payload["class_row_id"] = str(class_row_id or "").strip()
    payload_key = _spell_payload_map_key(
        {
            "systems_ref": _systems_ref_from_entry(spell_entry),
            "name": selected_value,
            **support_payload,
            "class_row_id": "" if support_payload else class_row_id,
        }
    )
    if not payload_key:
        return

    existing_payload = spells_by_key.get(payload_key)
    if existing_payload is None:
        if mark:
            spell_payload["mark"] = mark
        if is_always_prepared:
            spell_payload["is_always_prepared"] = True
        if is_bonus_known:
            spell_payload["is_bonus_known"] = True
        if is_ritual:
            spell_payload["is_ritual"] = True
        if support_payload:
            _apply_spell_payload_support_metadata(spell_payload, support_payload)
        spells_by_key[payload_key] = spell_payload
        return

    existing_payload["mark"] = _merge_spell_mark(
        str(existing_payload.get("mark") or "").strip(),
        mark,
    )
    if is_always_prepared:
        existing_payload["is_always_prepared"] = True
    if is_bonus_known:
        existing_payload["is_bonus_known"] = True
    if is_ritual:
        existing_payload["is_ritual"] = True
    if support_payload:
        _apply_spell_payload_support_metadata(existing_payload, support_payload)


def _add_bonus_known_spell_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    class_row_id: str = "",
    prefer_known_mark: bool = True,
    spell_source_row_id: str = "",
    spell_source_row_kind: str = "",
    spell_source_row_title: str = "",
    spell_source_ability_key: str = "",
    spell_source_mode: str = "",
    spell_source_spell_list_class_name: str = "",
    grant_source_label: str = "",
    spell_access_type: str = "",
    spell_access_uses: Any = None,
    spell_access_reset_on: str = "",
) -> None:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    mark = (
        "Cantrip"
        if spell_entry is not None and _spell_entry_level(spell_entry) == 0
        else ("Known" if prefer_known_mark else "")
    )
    _add_spell_to_payloads(
        spells_by_key,
        selected_value=selected_value,
        spell_catalog=spell_catalog,
        mark=mark,
        is_bonus_known=True,
        class_row_id=class_row_id,
        spell_source_row_id=spell_source_row_id,
        spell_source_row_kind=spell_source_row_kind,
        spell_source_row_title=spell_source_row_title,
        spell_source_ability_key=spell_source_ability_key,
        spell_source_mode=spell_source_mode,
        spell_source_spell_list_class_name=spell_source_spell_list_class_name,
        grant_source_label=grant_source_label,
        spell_access_type=spell_access_type,
        spell_access_uses=spell_access_uses,
        spell_access_reset_on=spell_access_reset_on,
    )


def _resolve_spell_entry(
    selected_value: str,
    spell_catalog: dict[str, Any],
) -> SystemsEntryRecord | None:
    clean_value = str(selected_value or "").strip()
    if not clean_value:
        return None
    by_slug = dict(spell_catalog.get("by_slug") or {})
    if clean_value in by_slug:
        return by_slug[clean_value]
    return dict(spell_catalog.get("by_title") or {}).get(normalize_lookup(clean_value))


def _build_spell_payload(
    selected_value: str,
    spell_entry: SystemsEntryRecord | None,
) -> dict[str, Any]:
    metadata = dict((spell_entry.metadata if spell_entry is not None else {}) or {})
    title = spell_entry.title if spell_entry is not None else str(selected_value or "").strip()
    source = spell_entry.source_id if spell_entry is not None else PHB_SOURCE_ID
    reference = (
        f"p. {spell_entry.source_page}"
        if spell_entry is not None and str(spell_entry.source_page or "").strip()
        else ""
    )
    return {
        "name": title,
        "casting_time": _format_spell_casting_time(metadata.get("casting_time")),
        "range": _format_spell_range(metadata.get("range")),
        "duration": _format_spell_duration(metadata.get("duration")),
        "components": _format_spell_components(metadata.get("components")),
        "save_or_hit": "",
        "source": source,
        "reference": reference,
        "mark": "",
        "is_always_prepared": False,
        "is_bonus_known": False,
        "is_ritual": bool(metadata.get("ritual")),
        "systems_ref": _systems_ref_from_entry(spell_entry),
    }


def _merge_spell_mark(existing_mark: str, new_mark: str) -> str:
    marks: list[str] = []
    for candidate in (existing_mark, new_mark):
        clean_candidate = str(candidate or "").strip()
        if not clean_candidate:
            continue
        for part in [part.strip() for part in clean_candidate.split("+")]:
            if part and part not in marks:
                marks.append(part)
    return " + ".join(marks)


_MERGE_NAME_ALIASES = {
    "chain mail": "chain mail armor",
    "chain mail armor": "chain mail armor",
    "crossbow, light": "light crossbow",
    "light crossbow": "light crossbow",
    "crossbow bolts": "crossbow bolts (20)",
    "crossbow bolts (20)": "crossbow bolts (20)",
    "rope, hempen (50 feet)": "hempen rope (50 feet)",
    "hempen rope (50 feet)": "hempen rope (50 feet)",
    "rations": "rations (1 day)",
    "rations (1 day)": "rations (1 day)",
}


def _merge_name_candidates(name: Any) -> list[str]:
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        return []
    candidates = [cleaned_name]
    if "," in cleaned_name:
        parts = [part.strip() for part in cleaned_name.split(",", 1)]
        if len(parts) == 2 and all(parts):
            candidates.append(f"{parts[1]} {parts[0]}")
    alias_variants = [_MERGE_NAME_ALIASES.get(candidate.lower(), "") for candidate in list(candidates)]
    candidates.extend(alias for alias in alias_variants if alias)

    normalized_candidates: list[str] = []
    for candidate in candidates:
        normalized = normalize_lookup(candidate)
        if normalized and normalized not in normalized_candidates:
            normalized_candidates.append(normalized)
    return normalized_candidates


def _normalize_spell_payloads(
    spell_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_spells: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for spell_payload in list(spell_payloads or []):
        payload = dict(spell_payload or {})
        name = str(payload.get("name") or "").strip()
        payload_key = _spell_payload_key(payload) or name
        if not payload_key:
            continue
        payload["name"] = name
        payload["is_always_prepared"] = _spell_payload_is_always_prepared(payload)
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_spells) + 1}"
        class_row_id = _spell_payload_class_row_id(payload)
        if class_row_id:
            payload["class_row_id"] = class_row_id
        else:
            payload.pop("class_row_id", None)
        source_row_id = _spell_payload_source_row_id(payload)
        if source_row_id:
            payload["spell_source_row_id"] = source_row_id
            payload["spell_source_row_kind"] = (
                str(payload.get("spell_source_row_kind") or "source").strip() or "source"
            )
            source_row_title = str(payload.get("spell_source_row_title") or "").strip()
            if source_row_title:
                payload["spell_source_row_title"] = source_row_title
            else:
                payload.pop("spell_source_row_title", None)
            source_ability_key = _prepared_spell_formula_ability_key(
                str(payload.get("spell_source_ability_key") or "").strip()
            )
            if source_ability_key:
                payload["spell_source_ability_key"] = source_ability_key
            else:
                payload.pop("spell_source_ability_key", None)
            source_mode = str(payload.get("spell_source_mode") or "").strip()
            if source_mode:
                payload["spell_source_mode"] = source_mode
            else:
                payload.pop("spell_source_mode", None)
            source_spell_list_class_name = str(payload.get("spell_source_spell_list_class_name") or "").strip()
            if source_spell_list_class_name:
                payload["spell_source_spell_list_class_name"] = source_spell_list_class_name
            else:
                payload.pop("spell_source_spell_list_class_name", None)
            payload.pop("class_row_id", None)
        else:
            payload.pop("spell_source_row_id", None)
            payload.pop("spell_source_row_kind", None)
            payload.pop("spell_source_row_title", None)
            payload.pop("spell_source_ability_key", None)
            payload.pop("spell_source_mode", None)
            payload.pop("spell_source_spell_list_class_name", None)
        grant_source_label = str(payload.get("grant_source_label") or "").strip()
        if grant_source_label:
            payload["grant_source_label"] = grant_source_label
        else:
            payload.pop("grant_source_label", None)
        access_payload = _spell_access_payload(payload)
        if access_payload:
            payload.update(access_payload)
        else:
            payload.pop("spell_access_type", None)
            payload.pop("spell_access_uses", None)
            payload.pop("spell_access_reset_on", None)
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)

        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        scope_key = _spell_payload_management_scope_key(payload)
        candidate_keys: list[str] = []
        if explicit_identity:
            candidate_keys.append(f"{scope_key}|{explicit_identity}" if scope_key else explicit_identity)
        candidate_keys.extend(
            f"{scope_key}|name:{candidate}" if scope_key else f"name:{candidate}"
            for candidate in _merge_name_candidates(name)
        )

        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if candidate_key.startswith("name:") and explicit_identity:
                existing_payload = normalized_spells[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break

        existing_payload = normalized_spells[existing_index] if existing_index is not None else None
        if existing_payload is None:
            existing_index = len(normalized_spells)
            normalized_spells.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload["mark"] = _merge_spell_mark(
            str(existing_payload.get("mark") or "").strip(),
            str(payload.get("mark") or "").strip(),
        )
        for key in ("is_always_prepared", "is_bonus_known", "is_ritual"):
            if bool(payload.get(key)):
                existing_payload[key] = True
        for key in ("casting_time", "range", "duration", "components", "save_or_hit", "source", "reference"):
            if not str(existing_payload.get(key) or "").strip() and str(payload.get(key) or "").strip():
                existing_payload[key] = payload.get(key)
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if list(payload.get("campaign_option_sources") or []):
            existing_payload["campaign_option_sources"] = _dedupe_campaign_spell_sources(
                list(existing_payload.get("campaign_option_sources") or [])
                + list(payload.get("campaign_option_sources") or [])
            )
        if payload.get("spell_source_row_id") or payload.get("grant_source_label") or payload.get("spell_access_type"):
            _apply_spell_payload_support_metadata(existing_payload, payload)
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        existing_scope_key = _spell_payload_management_scope_key(existing_payload)
        updated_keys: list[str] = []
        if updated_explicit_identity:
            updated_keys.append(
                f"{existing_scope_key}|{updated_explicit_identity}" if existing_scope_key else updated_explicit_identity
            )
        updated_keys.extend(
            (
                f"{existing_scope_key}|name:{candidate}"
                if existing_scope_key
                else f"name:{candidate}"
            )
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_spells


def _format_spell_casting_time(value: Any) -> str:
    blocks = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            cleaned = _clean_embedded_text(str(block or ""))
            if cleaned:
                parts.append(cleaned)
            continue
        amount = int(block.get("number") or 1)
        unit = str(block.get("unit") or "").replace("_", " ").strip()
        if not unit:
            continue
        label = unit if amount == 1 else f"{unit}s"
        parts.append(f"{amount} {label}")
    return ", ".join(parts) or "--"


def _format_spell_range(value: Any) -> str:
    if isinstance(value, str):
        return _clean_embedded_text(value) or "--"
    if not isinstance(value, dict):
        return "--"
    range_type = str(value.get("type") or "").strip().lower()
    if range_type == "point":
        distance = dict(value.get("distance") or {})
        distance_type = str(distance.get("type") or "").strip().lower()
        amount = distance.get("amount")
        if distance_type == "self":
            return "Self"
        if distance_type == "touch":
            return "Touch"
        if amount is not None:
            if distance_type == "feet":
                return f"{int(amount)} feet"
            if distance_type:
                return f"{amount} {distance_type}"
            return str(amount)
    if range_type == "special":
        return "Special"
    if range_type == "self":
        return "Self"
    return "--"


def _format_spell_duration(value: Any) -> str:
    blocks = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                parts.append(cleaned)
            continue
        if not isinstance(block, dict):
            continue
        duration_type = str(block.get("type") or "").strip().lower()
        if duration_type == "instant":
            parts.append("Instantaneous")
            continue
        if duration_type == "permanent":
            parts.append("Permanent")
            continue
        if duration_type == "special":
            parts.append("Special")
            continue
        if duration_type == "timed":
            duration = dict(block.get("duration") or {})
            amount = int(duration.get("amount") or 1)
            unit = str(duration.get("type") or "").replace("_", " ").strip()
            if unit:
                label = unit if amount == 1 else f"{unit}s"
                prefix = "Concentration, up to " if bool(block.get("concentration")) else ""
                parts.append(f"{prefix}{amount} {label}")
    return ", ".join(parts) or "--"


def _format_spell_components(value: Any) -> str:
    if isinstance(value, str):
        return _clean_embedded_text(value) or "--"
    if not isinstance(value, dict):
        return "--"
    parts: list[str] = []
    if value.get("v"):
        parts.append("V")
    if value.get("s"):
        parts.append("S")
    material = value.get("m")
    if material:
        if isinstance(material, str):
            parts.append(f"M ({_clean_embedded_text(material)})")
        else:
            parts.append("M")
    return ", ".join(parts) or "--"
