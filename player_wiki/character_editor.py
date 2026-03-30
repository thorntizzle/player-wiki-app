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
from .character_builder import _add_spell_to_payloads, _resolve_spell_entry, _spell_payload_key
from .character_campaign_options import (
    build_campaign_page_character_option,
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
)
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import normalize_lookup
from .repository import slugify

CHARACTER_EDITOR_VERSION = "2026-03-30.03"
CUSTOM_FEATURE_CATEGORY = "custom_feature"
CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"
CUSTOM_FEATURE_TRACKER_PREFIX = "manual-feature-tracker"
MIN_CUSTOM_FEATURE_ROWS = 3
MIN_CUSTOM_EQUIPMENT_ROWS = 3
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


def build_native_character_edit_context(
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = dict(form_values or {})
    proficiency_lists = _display_proficiency_lists_for_editor(definition)
    manual_features = _manual_custom_features(definition)
    manual_items = _manual_equipment_entries(definition)
    resource_template_lookup = {
        str(template.get("id") or "").strip(): dict(template)
        for template in list(definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    stat_adjustments = normalize_manual_stat_adjustments((definition.stats or {}).get("manual_adjustments"))
    campaign_page_options = _build_campaign_page_options(campaign_page_records or [])

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
        feature_rows.append(
            {
                "index": index,
                "id": str(values.get(f"custom_feature_id_{index}") or existing.get("id") or "").strip(),
                "name": str(values.get(f"custom_feature_name_{index}") or existing.get("name") or "").strip(),
                "page_ref": str(
                    values.get(f"custom_feature_page_ref_{index}")
                    or _extract_page_ref_value(existing.get("page_ref"))
                    or ""
                ).strip(),
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
            }
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
    spell_catalog: dict[str, Any] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    values = dict(form_values or {})
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
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
    base_stats, _ = strip_manual_stat_adjustments(dict(current_definition.stats or {}))
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
    seen_feature_names: set[str] = set()
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
        resource_reset_on = _normalize_resource_reset_on(
            values.get(f"custom_feature_resource_reset_on_{index}")
            or ((campaign_option or {}).get("resource") or {}).get("reset_on")
            or "manual"
        )
        if page_ref:
            existing["page_ref"] = page_ref
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

    used_item_ids = set(manual_item_lookup.keys())
    inventory_quantity_overrides: dict[str, int] = {}
    manual_items: list[dict[str, Any]] = []
    for index in range(1, max(_max_row_index(values, "manual_item"), MIN_CUSTOM_EQUIPMENT_ROWS) + 1):
        raw_id = str(values.get(f"manual_item_id_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"manual_item_page_ref_{index}") or "",
            campaign_page_lookup,
        )
        campaign_option = _editable_campaign_option_for_page_ref(
            page_ref,
            campaign_page_lookup,
            default_kind="item",
        )
        name = str(
            values.get(f"manual_item_name_{index}")
            or (campaign_option or {}).get("item_name")
            or (campaign_page_lookup.get(page_ref) or {}).get("title")
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
        if not name:
            raise CharacterEditValidationError("Each custom equipment row needs an item name.")
        quantity = _parse_manual_item_quantity(quantity_text)

        existing = deepcopy(manual_item_lookup.get(raw_id) or {})
        existing.pop("campaign_option", None)
        existing.pop("systems_ref", None)
        existing.pop("page_ref", None)
        item_id = raw_id or _build_unique_manual_id("manual-item", name, used_item_ids)
        used_item_ids.add(item_id)
        existing.update(
            {
                "id": item_id,
                "name": name,
                "default_quantity": quantity,
                "weight": weight,
                "notes": notes.strip(),
                "source_kind": CUSTOM_EQUIPMENT_SOURCE_KIND,
                "campaign_option": dict(campaign_option or {}) or None,
            }
        )
        if page_ref:
            existing["page_ref"] = page_ref
        manual_items.append(existing)
        inventory_quantity_overrides[item_id] = quantity

    selected_campaign_option_payloads = _campaign_option_payloads_from_entries(
        manual_features,
        manual_items,
    )
    proficiencies = _merge_editor_proficiencies(
        manual_proficiencies,
        selected_campaign_option_payloads,
    )
    stats = apply_manual_stat_adjustments(base_stats, stat_adjustments)
    campaign_stat_adjustments = collect_campaign_option_stat_adjustments(selected_campaign_option_payloads)
    if campaign_stat_adjustments:
        stats = apply_stat_adjustments(stats, campaign_stat_adjustments)
    spellcasting = _apply_campaign_option_spells_to_spellcasting(
        current_definition.spellcasting,
        existing_campaign_option_payloads=existing_campaign_option_payloads,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        spell_catalog=spell_catalog,
    )

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["profile"] = profile
    payload["stats"] = stats
    payload["proficiencies"] = proficiencies
    payload["spellcasting"] = spellcasting
    payload["reference_notes"] = reference_notes
    payload["features"] = [
        dict(feature)
        for feature in list(current_definition.features or [])
        if str(feature.get("category") or "") != CUSTOM_FEATURE_CATEGORY
    ] + manual_features
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
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=str(current_import_metadata.source_path or f"managed://{campaign_slug}/{current_definition.character_slug}"),
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_EDITOR_VERSION,
        import_status="managed",
        warnings=[],
    )
    return definition, import_metadata, inventory_quantity_overrides


def _manual_custom_features(definition: CharacterDefinition) -> list[dict[str, Any]]:
    return [
        dict(feature)
        for feature in list(definition.features or [])
        if str(feature.get("category") or "") == CUSTOM_FEATURE_CATEGORY
    ]


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
    campaign_grants = collect_campaign_option_proficiency_grants(
        _campaign_option_payloads_from_entries(
            _manual_custom_features(definition),
            _manual_equipment_entries(definition),
        )
    )
    return {
        key: _subtract_casefold_values(proficiencies[key], campaign_grants.get(key) or [])
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
    if kind and kind != default_kind:
        return None
    return option


def _merge_editor_proficiencies(
    manual_proficiencies: dict[str, list[str]],
    option_payloads: list[dict[str, Any]],
) -> dict[str, list[str]]:
    campaign_grants = collect_campaign_option_proficiency_grants(option_payloads)
    return {
        key: _dedupe_casefold_values(list(manual_proficiencies.get(key) or []) + list(campaign_grants.get(key) or []))
        for key in ("languages", "armor", "weapons", "tools")
    }


def _apply_campaign_option_spells_to_spellcasting(
    current_spellcasting: dict[str, Any] | None,
    *,
    existing_campaign_option_payloads: list[dict[str, Any]],
    selected_campaign_option_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> dict[str, Any]:
    spellcasting = dict(current_spellcasting or {})
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in list(spellcasting.get("spells") or []):
        payload = _normalize_spell_payload_for_campaign_option_tracking(spell)
        _reset_spell_payload_to_base(payload)
        payload_key = _spell_payload_key(payload)
        if payload_key:
            spells_by_key[payload_key] = payload

    for spell_grant in _iter_campaign_option_spell_grants(selected_campaign_option_payloads):
        selected_value = str(spell_grant.get("value") or "").strip()
        if not selected_value:
            continue
        spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
        payload_key = str((spell_entry.slug if spell_entry is not None else selected_value) or "").strip()
        if not payload_key:
            continue
        existed_before = payload_key in spells_by_key
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
        )
        payload = spells_by_key.get(payload_key)
        if payload is None:
            continue
        if not existed_before:
            payload["base_mark"] = ""
            payload["base_is_always_prepared"] = False
            payload["base_is_bonus_known"] = False
            payload["base_is_ritual"] = bool(dict((spell_entry.metadata if spell_entry is not None else {}) or {}).get("ritual"))
            payload["has_base_spell"] = False
        existing_sources = [
            dict(source)
            for source in list(payload.get("campaign_option_sources") or [])
            if str(source.get("source_ref") or "").strip()
        ]
        source_ref = str(spell_grant.get("source_ref") or "").strip()
        source_marker = (
            source_ref,
            str(spell_grant.get("mark") or "").strip(),
            bool(spell_grant.get("always_prepared")),
            bool(spell_grant.get("ritual")),
        )
        seen_markers = {
            (
                str(source.get("source_ref") or "").strip(),
                str(source.get("mark") or "").strip(),
                bool(source.get("always_prepared")),
                bool(source.get("ritual")),
            )
            for source in existing_sources
        }
        if source_marker not in seen_markers:
            existing_sources.append(
                {
                    "source_ref": source_ref,
                    "mark": str(spell_grant.get("mark") or "").strip(),
                    "always_prepared": bool(spell_grant.get("always_prepared")),
                    "ritual": bool(spell_grant.get("ritual")),
                }
            )
        payload["campaign_option_sources"] = existing_sources

    spellcasting["spells"] = [
        payload
        for payload in spells_by_key.values()
        if bool(payload.get("has_base_spell")) or list(payload.get("campaign_option_sources") or [])
    ]
    return spellcasting


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
        for source in list(payload.get("campaign_option_sources") or [])
        if isinstance(source, dict)
    ]
    return payload


def _reset_spell_payload_to_base(payload: dict[str, Any]) -> None:
    payload["mark"] = str(payload.get("base_mark") or "").strip()
    payload["is_always_prepared"] = bool(payload.get("base_is_always_prepared"))
    payload["is_bonus_known"] = bool(payload.get("base_is_bonus_known"))
    payload["is_ritual"] = bool(payload.get("base_is_ritual"))
    payload["campaign_option_sources"] = []


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


def _build_campaign_page_options(campaign_page_records: list[Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for record in list(campaign_page_records or []):
        page_ref = _extract_page_ref_value(getattr(record, "page_ref", ""))
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        section = str(getattr(page, "section", "") or "").strip()
        subsection = str(getattr(page, "subsection", "") or "").strip()
        campaign_option = build_campaign_page_character_option(
            record,
            default_kind="item" if section == "Items" else "feature",
        )
        label_parts = [title]
        if section:
            if subsection:
                label_parts.append(f"{section} / {subsection}")
            else:
                label_parts.append(section)
        options.append(
            {
                "value": page_ref,
                "label": " | ".join(label_parts),
                "title": title,
                "campaign_option": dict(campaign_option or {}) or None,
            }
        )
    return options


def _build_campaign_page_lookup(campaign_page_records: list[Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for option in _build_campaign_page_options(campaign_page_records):
        page_ref = str(option.get("value") or "").strip()
        if not page_ref:
            continue
        lookup[page_ref] = {
            "page_ref": page_ref,
            "label": str(option.get("label") or page_ref),
            "title": str(option.get("title") or page_ref),
            "campaign_option": dict(option.get("campaign_option") or {}) or None,
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
