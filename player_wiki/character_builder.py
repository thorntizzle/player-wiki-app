from __future__ import annotations

from .character_catalog_operations import (
    native_catalog,catalog_snapshot, catalog_index, catalog_aux,
    catalog_rows, catalog_field, catalog_record, catalog_is_record)

from .character_ability_inputs import advance_inputs, advancement_scores, resolve_inputs, seed_base_inputs, write_inputs
from .character_language_choices import language_options_for_block
from .character_source_reads import source_active, phase_of, builder_source_reader

from copy import deepcopy
from dataclasses import dataclass
import json
from types import MappingProxyType, SimpleNamespace
from typing import Any

from .auth_store import isoformat, utcnow
from .campaign_item_mechanics import (
    campaign_item_character_metadata,
    is_campaign_item_mechanics_metadata,
)
from .character_artificer_infusions import (
    ENHANCED_DEFENSE_INFUSION_KEY,
    active_infusion_armor_class_bonus,
    item_has_active_infusion,
)
from .character_adjustments import (
    apply_manual_stat_adjustments,
    apply_recoverable_ability_score_penalties,
    apply_recoverable_stat_penalties,
    apply_stat_adjustments,
    normalize_recoverable_penalties,
    restore_recoverable_ability_score_penalties,
    strip_recoverable_stat_penalties,
    strip_manual_stat_adjustments,
)
from .character_campaign_options import (
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
    normalize_campaign_mechanic_effects,
)
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_spell_effects import reconcile_formula_row
from .character_spell_grants import (
    ACQUISITION_FIELD, TRUSTED_ACQUISITION_KEY, AcquisitionContext, GrantContractError,
    build_occurrences, canonical_digest, has_native_grants, publication_identity,
)
from .character_profile import (
    ensure_profile_class_rows,
    profile_class_level_text,
    profile_class_rows,
    profile_primary_class_name,
    profile_primary_class_ref,
    profile_primary_subclass_name,
    profile_primary_subclass_ref,
    sync_profile_class_summary,
)
from .character_spell_slots import spell_slot_lanes_from_spellcasting
from .character_source_matrix import PHB_SOURCE_ID
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord
from .system_policy import is_dnd_5e_system
from .character_builder_constants import *  # noqa: F403
from .character_builder_selected_choices import (
    _build_selected_campaign_item_specs,
    _collect_selected_campaign_feature_entries,
    _resolve_choice_label,
    _resolve_choice_option,
    _selected_campaign_choice_options,
    _selected_campaign_option_payloads,
)
from .character_builder_preview import *  # noqa: F403
from .character_builder_foundation import *  # noqa: F403
from .character_builder_spells import *  # noqa: F403
from .character_builder_equipment import *  # noqa: F403
from .character_builder_equipment_catalog import (
    _build_equipment_groups,
    _build_level_one_equipment_catalog as _build_level_one_equipment_catalog_from_specs,
    _collect_currency_seed_from_equipment,
    _currency_seed_from_cp,
    _describe_equipment_spec,
    _format_weight_value,
)
from . import character_builder_derivation as _character_builder_derivation
from .character_builder_derivation import *  # noqa: F403
from .character_builder_catalogs import *  # noqa: F403
from .character_builder_static_bundle import (
    _build_campaign_feature_choice_fields,
    _build_campaign_item_choice_fields,
    _build_campaign_page_choice_options,
    _build_common_builder_static_bundle,
    _campaign_page_option_allowed_for_linked_field,
)
from .character_builder_progression import *  # noqa: F403
from .character_builder_features import *  # noqa: F403


def _derive_definition_core_sheet_payloads(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    resolved_entries: dict[str, Any] | None = None,
    automatic_prepared_spell_flags_func: Any | None = None,
    transient_effects: dict[str, Any] | None = None,
    source_authority: Any | None = None,
    source_read_phase=None, feature_composition=None,
) -> dict[str, Any]:
    return _character_builder_derivation._derive_definition_core_sheet_payloads(
        definition,
        derivation_components=derivation_components,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
        resolved_entries=resolved_entries,
        automatic_prepared_spell_flags_func=(
            automatic_prepared_spell_flags_func
        ),
        transient_effects=transient_effects,
        source_authority=source_authority,
        source_read_phase=source_read_phase if source_read_phase is not None else phase_of(systems_service),
        feature_composition=feature_composition,
        resolve_definition_sheet_entries_func=_resolve_definition_sheet_entries,
        effective_item_catalog_for_definition_func=(
            _selected_read_item_catalog if native_catalog(item_catalog) is not None
            else _effective_item_catalog_for_definition),
        effective_spell_catalog_for_definition_func=(
            _selected_read_spell_catalog if native_catalog(spell_catalog) is not None
            else _effective_spell_catalog_for_definition),
    )


def _selected_read_item_catalog(definition, *, item_catalog, **_unused):
    return catalog_snapshot(item_catalog)


def _selected_read_spell_catalog(definition, *, spell_catalog, **_unused):
    return catalog_snapshot(spell_catalog)


def build_level_one_builder_context(
    systems_service: Any,
    campaign_slug: str,
    form_values: dict[str, str] | None = None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    # Routes supply this request-local typed object after authenticating the
    # signed intent. Never stringify it into public form/context values.
    raw_values = dict(form_values or {})
    acquisition_context = raw_values.pop(TRUSTED_ACQUISITION_KEY, None)
    from .committed_publication import active
    if not source_active(systems_service):
        raw_values.pop(ACQUISITION_FIELD, None)
        acquisition_context = None
    if acquisition_context is not None and not isinstance(acquisition_context, AcquisitionContext):
        raise GrantContractError("Native acquisition context is unavailable.")
    preview_values = _normalize_preview_values(raw_values)
    static_bundle = _build_common_builder_static_bundle(
        builder_source_reader(systems_service),
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
    campaign_feature_options = list(static_bundle.get("campaign_feature_options") or [])
    campaign_item_options = list(static_bundle.get("campaign_item_options") or [])

    preview_values["class_slug"] = _sanitize_entry_selection_value(preview_values.get("class_slug"), class_options)
    preview_values["species_slug"] = _sanitize_entry_selection_value(preview_values.get("species_slug"), species_options)
    preview_values["background_slug"] = _sanitize_entry_selection_value(
        preview_values.get("background_slug"),
        background_options,
    )
    selected_class = _resolve_selected_entry(class_options, preview_values.get("class_slug", ""))
    selected_species = _resolve_selected_entry(species_options, preview_values.get("species_slug", ""))
    selected_background = _resolve_selected_entry(background_options, preview_values.get("background_slug", ""))

    subclass_options = _list_subclass_options(
        systems_service,
        campaign_slug,
        selected_class,
        subclass_entries=list(static_bundle.get("subclass_entries") or []),
    )
    preview_values["subclass_slug"] = _sanitize_entry_selection_value(
        preview_values.get("subclass_slug"),
        subclass_options,
    )
    selected_subclass = _resolve_selected_entry(subclass_options, preview_values.get("subclass_slug", ""))

    class_progression = _class_progression_for_builder(
        systems_service,
        campaign_slug,
        selected_class,
        campaign_page_records=campaign_page_records,
    )
    subclass_progression = _subclass_progression_for_builder(
        systems_service,
        campaign_slug,
        selected_subclass,
        campaign_page_records=campaign_page_records,
    )
    requires_subclass = _class_requires_subclass_at_level_one(selected_class, class_progression)

    equipment_groups = _build_equipment_groups(
        selected_class=selected_class,
        selected_background=selected_background,
        item_catalog=item_catalog,
        values=preview_values,
    )

    preview_values, choice_sections = _stabilize_choice_section_values(
        preview_values,
        static_keys=LEVEL_ONE_BUILDER_STATIC_KEYS,
        build_sections=lambda current_values: _build_choice_sections(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            selected_species=selected_species,
            selected_background=selected_background,
            feat_options=feat_options,
            feat_catalog=feat_catalog,
            optionalfeature_catalog=optionalfeature_catalog,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            equipment_groups=equipment_groups,
            campaign_feature_options=campaign_feature_options,
            campaign_item_options=campaign_item_options,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            values=current_values,
        ),
    )
    choice_sections = _annotate_builder_choice_sections(
        choice_sections,
        preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
    )

    preview = _build_level_one_preview(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        equipment_groups=equipment_groups,
        choice_sections=choice_sections,
        feat_catalog=feat_catalog,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        values=preview_values,
        acquisition_context=acquisition_context,
        systems_service=systems_service,
    )

    return {
        "values": preview_values,
        TRUSTED_ACQUISITION_KEY: acquisition_context,
        "systems_service": systems_service,
        "campaign_page_records": list(campaign_page_records or []),
        "class_options": [_entry_option(entry) for entry in class_options],
        "species_options": [_entry_option(entry) for entry in species_options],
        "background_options": [_entry_option(entry) for entry in background_options],
        "subclass_options": [_entry_option(entry) for entry in subclass_options],
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "requires_subclass": requires_subclass,
        "choice_sections": choice_sections,
        "class_progression": class_progression,
        "subclass_progression": subclass_progression,
        "equipment_groups": equipment_groups,
        "feat_catalog": feat_catalog,
        "optionalfeature_catalog": optionalfeature_catalog,
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
        "limitations": [
            "Base classes now come from the campaign's enabled Systems sources only when they fall inside the current native support lane and expose the needed progression metadata, while older PHB fallback data still covers previously imported local classes.",
            "Species, backgrounds, and feats can come from either enabled Systems entries or structured published Mechanics pages in the matching subsection.",
            "The optional campaign content fields currently accept published Mechanics feature/feat pages for linked rewards and published Items pages for linked equipment.",
            "Enter level-1 ability scores after species bonuses. Native feat-driven ability increases are applied automatically.",
            "Native attack rows now cover basic PHB weapons, off-hand attacks, key level-1 fighting-style adjustments, and the current modeled feat attack variants, but a few advanced riders still need manual follow-up.",
            "Gold-alternative loadouts, non-structured campaign spell access, and a few remaining feat/spell edge cases still need manual follow-up.",
        ],
        "preview": preview,
        "field_live_preview": _level_one_field_live_preview_metadata(),
        "preview_region_ids": list(LEVEL_ONE_PREVIEW_REGION_IDS),
        "preview_regions_csv": ",".join(LEVEL_ONE_PREVIEW_REGION_IDS),
        "live_region_ids": list(LEVEL_ONE_LIVE_REGION_IDS),
        "live_regions_csv": ",".join(LEVEL_ONE_LIVE_REGION_IDS),
    }


def build_level_one_character_definition(
    campaign_slug: str,
    builder_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    selected_class = builder_context.get("selected_class")
    selected_species = builder_context.get("selected_species")
    selected_background = builder_context.get("selected_background")
    selected_subclass = builder_context.get("selected_subclass")
    from .committed_publication import active
    activated = source_active(systems_service)
    acquisition_context = builder_context.get(TRUSTED_ACQUISITION_KEY)
    if not activated:
        acquisition_context = None
    if activated and (not isinstance(acquisition_context, AcquisitionContext)
            or acquisition_context.mode != "create" or acquisition_context.campaign_slug != campaign_slug
            or acquisition_context.prior_definition_digest is not None
            or acquisition_context.prior_revision is not None or acquisition_context.prior_state_revision is not None):
        raise GrantContractError("Refresh the native builder to obtain its acquisition intent.")
    submitted_values = dict(form_values or {})
    submitted_values.pop(TRUSTED_ACQUISITION_KEY, None)
    choice_sections = list(builder_context.get("choice_sections") or [])
    class_progression = list(builder_context.get("class_progression") or [])
    subclass_progression = list(builder_context.get("subclass_progression") or [])
    equipment_groups = list(builder_context.get("equipment_groups") or [])
    feat_catalog = dict(builder_context.get("feat_catalog") or {})
    optionalfeature_catalog = dict(builder_context.get("optionalfeature_catalog") or {})
    item_catalog = dict(builder_context.get("item_catalog") or {})
    spell_catalog = dict(builder_context.get("spell_catalog") or {})
    limitations = list(builder_context.get("limitations") or [])
    context_values = builder_context.get("values")
    values = _normalize_preview_values(
        _sanitize_choice_section_values(
            {
                **(dict(context_values) if isinstance(context_values, dict) else {}),
                **{key: str(value) for key, value in submitted_values.items()},
            },
            choice_sections=choice_sections,
            static_keys=LEVEL_ONE_BUILDER_STATIC_KEYS,
        )
    )

    if selected_class is None:
        raise CharacterBuildError("Choose a class to build the character.")
    if selected_species is None:
        raise CharacterBuildError("Choose a species to build the character.")
    if selected_background is None:
        raise CharacterBuildError("Choose a background to build the character.")
    if builder_context.get("requires_subclass") and selected_subclass is None:
        raise CharacterBuildError("Choose a subclass for this class at level 1.")

    name = str(values.get("name") or "").strip()
    if not name:
        raise CharacterBuildError("Character name is required.")
    character_slug = slugify(str(values.get("character_slug") or "").strip() or name)
    if not character_slug:
        raise CharacterBuildError("Character slug is required.")

    feat_selections = _resolve_builder_feat_selections(values, feat_catalog, selected_species=selected_species)
    feature_choice_selections = _progression_feature_choice_selections(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=1,
        instance_prefix="level1_feature",
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        _parse_ability_scores(values),
        feat_selections=feat_selections,
        selected_choices={},
        strict=False,
    )
    proficiency_bonus = 2
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values)
    ability_scores = _apply_feat_ability_score_bonuses(
        _parse_ability_scores(values),
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    selected_feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_feature_entries = _apply_campaign_feature_spell_manager_payloads(
        selected_feature_entries,
        values=values,
        field_prefix_base="campaign_spell_manager",
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(selected_feature_entries)
    )
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        campaign_option_payloads=selected_campaign_option_payloads,
        item_catalog=item_catalog,
    )
    from .character_feature_proficiency_grants import native_grants
    feature_prior_proficiencies = deepcopy(proficiencies)
    feature_grants = native_grants(feature_choice_selections, selected_choices,
        prior=proficiencies, item_catalog=item_catalog)
    for category, names in feature_grants.items():
        proficiencies[category] = _dedupe_preserve_order(proficiencies.get(category, []) + names)
    tool_expertise = _apply_feature_expertise_to_tool_proficiencies(
        [],
        available_tool_proficiencies=proficiencies["tools"],
        feature_selections=feature_choice_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    skills = _build_skills_payload(
        ability_scores,
        proficiencies["skills"],
        proficiency_bonus,
        feat_selections=feat_selections,
        feature_selections=feature_choice_selections,
        selected_choices=selected_choices,
        strict=True,
    )

    profile = _build_level_one_profile(
        name=name, selected_class=selected_class, selected_subclass=selected_subclass,
        selected_species=selected_species, selected_background=selected_background, values=values,
    )
    class_row_id = ensure_profile_class_rows(profile)[0]["row_id"]
    features, resource_templates = _build_feature_payloads(
        selected_feature_entries,
        ability_scores=ability_scores,
        current_level=1,
        acquisition_context=acquisition_context,
        acquisition_class_row_id=class_row_id,
    )
    equipment_catalog = _build_level_one_equipment_catalog(
        equipment_groups,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        item_catalog=item_catalog,
    )
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
        features=features,
    )

    stats = _build_level_one_stats(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        ability_scores=ability_scores,
        skills=skills,
        proficiency_bonus=proficiency_bonus,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        current_level=1,
        equipment_catalog=equipment_catalog,
        features=features,
        item_catalog=item_catalog,
        campaign_option_payloads=selected_campaign_option_payloads,
    )
    background_choice, _ = _background_instrument_payload(
        selected_background, {**values, **{key: str(value) for key, value in submitted_values.items()
                                          if str(key).startswith("background_instrument_")}},
        item_catalog, strict=True,
    )
    if background_choice is not None:
        profile["background_choices"] = background_choice
    # Creation has one class row. Preserve that owner just as progression does;
    # a tracker cannot prove its reset/level formula from a display label.
    class_row_id = ensure_profile_class_rows(profile)[0]["row_id"]
    class_tracker_ids = set()
    for feature in features:
        if feature.get("category") in {"class_feature", "feat"}:
            feature["class_row_id"] = class_row_id
            if feature.get("tracker_ref"):
                class_tracker_ids.add(feature["tracker_ref"])
    for template in resource_templates:
        if template.get("id") in class_tracker_ids:
            template["class_row_id"] = class_row_id
    spell_output_contributors = [] if activated else None
    spellcasting = _build_level_one_spellcasting(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=selected_feature_entries,
        campaign_option_payloads=selected_campaign_option_payloads,
        canonical_activation=activated,
        acquisition_context=acquisition_context,
        output_contributors=spell_output_contributors,
    )
    for spell in list(spellcasting.get("spells") or []):
        if not spell.get("class_row_id") and not spell.get("spell_source_row_id"):
            spell["class_row_id"] = class_row_id
        if not spell.get("id") and dict(spell.get("systems_ref") or {}).get("entry_key"):
            spell["id"] = "spell:" + canonical_digest([
                spell.get("class_row_id"), spell.get("spell_source_row_id"),
                publication_identity(spell["systems_ref"]),
            ])

    raw_ability_scores = _parse_ability_scores(values)
    selected_feat_features, _ = _build_feature_payloads(
        [_build_feat_feature_entry(selection=selection, values=values) for selection in feat_selections],
        ability_scores=ability_scores,
        current_level=1,
    )
    selected_campaign_bonuses = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ABILITY_KEYS},
        feat_selections=_campaign_option_feat_selections_from_features(selected_feat_features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(selected_feat_features),
        strict=False,
    )
    # Automatic feature grants are modeled independently. Only the selected
    # feats' own unmodeled contributions belong in the fixed input layer.
    seed_base_inputs(
        stats, raw_ability_scores, provenance="native_creation",
        fixed_bonuses={
            key: bonus - selected_campaign_bonuses[key]
            for key, bonus in _apply_feat_ability_score_bonuses(
                {key: 0 for key in ABILITY_KEYS}, feat_selections=feat_selections,
                selected_choices=selected_choices, strict=False,
            ).items()
        },
    )
    source_path = "builder://native-level-1"
    source = {
        "source_path": source_path,
        "source_type": "native_character_builder",
        "imported_from": "In-app Native Level 1 Builder",
        "imported_at": isoformat(utcnow()),
        "parse_warnings": list(limitations),
    }
    from .character_language_choices import parent_language_frame, PARENT_FRAME
    parent_languages = parent_language_frame(selected_species, selected_background, selected_choices)
    if parent_languages is not None:
        source[PARENT_FRAME] = parent_languages
    definition = CharacterDefinition(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        name=name,
        status="active",
        profile=profile,
        stats=stats,
        skills=skills,
        proficiencies={
            "armor": proficiencies["armor"],
            "weapons": proficiencies["weapons"],
            "tools": proficiencies["tools"],
            "languages": proficiencies["languages"],
            "tool_expertise": tool_expertise,
        },
        attacks=attacks,
        features=features,
        spellcasting=spellcasting,
        equipment_catalog=equipment_catalog,
        reference_notes={
            "additional_notes_markdown": "",
            "allies_and_organizations_markdown": "",
            "custom_sections": [],
        },
        resource_templates=resource_templates,
        source=source,
    )
    from .character_feature_proficiency_grants import native_frame
    grant_frame = native_frame(feature_choice_selections, selected_choices, feature_prior_proficiencies, class_row_id)
    if grant_frame:
        definition.source["native_feature_proficiency_choices"] = grant_frame
    if activated:
        grant_model, acquisition_frame = build_occurrences(
            definition, builder_context.get("systems_service"),
            acquisition_context=acquisition_context,
        )
        definition.spellcasting["native_spell_grants"] = grant_model
        definition.source["native_acquisitions"] = acquisition_frame
        from .character_spell_grants import omit_redundant_native_spell_outputs
        for contributor in spell_output_contributors:
            if not contributor["payload"].get("spell_source_row_id"):
                contributor["class_row_id"] = class_row_id
                contributor["payload"]["class_row_id"] = class_row_id
        definition = omit_redundant_native_spell_outputs(
            definition, prior_definition=None, contributors=spell_output_contributors,
            systems_service=builder_context.get("systems_service"),
        )
    definition = normalize_definition_to_native_model(
        definition,
        mode="native_create",
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=builder_context.get("systems_service"),
        campaign_page_records=builder_context.get("campaign_page_records"),
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        source_path=source_path,
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="warning" if limitations else "clean",
        warnings=list(limitations),
    )
    return definition, import_metadata


def _list_phb_entries(
    systems_service: Any,
    campaign_slug: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    return [
        entry
        for entry in _list_campaign_enabled_entries(systems_service, campaign_slug, entry_type)
        if str(entry.source_id or "").strip().upper() == PHB_SOURCE_ID
    ]


def _resolve_definition_sheet_entries(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    static_bundle: dict[str, Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    selected_class = resolved_class if isinstance(resolved_class, SystemsEntryRecord) else None
    selected_subclass = resolved_subclass if isinstance(resolved_subclass, SystemsEntryRecord) else None
    selected_species = resolved_species if isinstance(resolved_species, SystemsEntryRecord) else None
    selected_background = resolved_background if isinstance(resolved_background, SystemsEntryRecord) else None
    if systems_service is None:
        return {
            "selected_class": selected_class,
            "selected_subclass": selected_subclass,
            "selected_species": selected_species,
            "selected_background": selected_background,
            "selected_class_rows": [],
        }

    static_bundle = (
        dict(static_bundle)
        if static_bundle is not None
        else _build_common_builder_static_bundle(
            builder_source_reader(systems_service),
            definition.campaign_slug,
            campaign_page_records=campaign_page_records,
        )
    )
    classes = profile_class_rows(definition.profile)
    class_payload = dict(classes[0] or {}) if classes else {}
    if selected_class is None:
        selected_class = _resolve_profile_entry(
            list(static_bundle.get("supported_class_entries") or []),
            profile_primary_class_ref(definition.profile) or dict(class_payload.get("systems_ref") or {}),
            fallback_title=_native_character_class_name(definition),
        )
    if selected_species is None:
        selected_species = _resolve_profile_entry(
            list(static_bundle.get("species_options") or []),
            (definition.profile or {}).get("species_ref"),
            page_ref=(definition.profile or {}).get("species_page_ref"),
            fallback_title=str((definition.profile or {}).get("species") or "").strip(),
        )
    if selected_background is None:
        selected_background = _resolve_profile_entry(
            list(static_bundle.get("background_options") or []),
            (definition.profile or {}).get("background_ref"),
            page_ref=(definition.profile or {}).get("background_page_ref"),
            fallback_title=str((definition.profile or {}).get("background") or "").strip(),
        )
    if selected_subclass is None and selected_class is not None:
        subclass_options = _list_subclass_options(
            systems_service,
            definition.campaign_slug,
            selected_class,
            subclass_entries=list(static_bundle.get("subclass_entries") or []),
        )
        selected_subclass = _resolve_profile_entry(
            subclass_options,
            profile_primary_subclass_ref(definition.profile) or dict(class_payload.get("subclass_ref") or {}),
            fallback_title=_native_character_subclass_name(definition),
        )
    selected_class_rows: list[dict[str, Any]] = []
    for index, row in enumerate(ensure_profile_class_rows(definition.profile), start=1):
        row_payload = dict(row or {})
        row_id = str(row_payload.get("row_id") or "").strip() or f"class-row-{index}"
        row_class = _resolve_profile_entry(
            list(static_bundle.get("supported_class_entries") or []),
            dict(row_payload.get("systems_ref") or {}),
            fallback_title=str(row_payload.get("class_name") or "").strip(),
        )
        if row_class is None and index == 1 and selected_class is not None:
            row_class = selected_class
        row_subclass = (
            _resolve_profile_entry(
                _list_subclass_options(
                    systems_service,
                    definition.campaign_slug,
                    row_class,
                    subclass_entries=list(static_bundle.get("subclass_entries") or []),
                ),
                dict(row_payload.get("subclass_ref") or {}),
                fallback_title=str(row_payload.get("subclass_name") or "").strip(),
            )
            if row_class is not None
            else None
        )
        if row_subclass is None and index == 1 and selected_subclass is not None:
            row_subclass = selected_subclass
        if index == 1 and selected_class is None:
            selected_class = row_class
        if index == 1 and selected_subclass is None:
            selected_subclass = row_subclass
        selected_class_rows.append(
            {
                "row_id": row_id,
                "row_index": index,
                "row_level": int(row_payload.get("level") or 0),
                "class_payload": row_payload,
                "selected_class": row_class,
                "selected_subclass": row_subclass,
            }
        )
    return {
        "selected_class": selected_class,
        "selected_subclass": selected_subclass,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_class_rows": selected_class_rows,
    }


_TARGETED_PROFILE_ENTRY_SEARCH_LIMIT = 8


def _targeted_profile_entry_is_enabled(
    systems_service: Any,
    campaign_slug: str,
    entry: SystemsEntryRecord,
) -> bool:
    is_entry_enabled = getattr(systems_service, "is_entry_enabled_for_campaign", None)
    return not callable(is_entry_enabled) or bool(
        is_entry_enabled(campaign_slug, entry)
    )


def _targeted_profile_systems_options(
    systems_service: Any,
    campaign_slug: str,
    *,
    entry_type: str,
    systems_ref: Any = None,
    fallback_title: str = "",
) -> tuple[list[SystemsEntryRecord], bool]:
    """Resolve only an explicit or exact-title Systems profile candidate set."""
    ref = dict(systems_ref or {}) if isinstance(systems_ref, dict) else {}
    candidates: list[SystemsEntryRecord] = []

    def add_candidate(value: Any) -> bool:
        if not isinstance(value, SystemsEntryRecord):
            return False
        if str(value.entry_type or "").strip() != entry_type:
            return False
        if not _targeted_profile_entry_is_enabled(
            systems_service,
            campaign_slug,
            value,
        ):
            return False
        if any(
            str(candidate.entry_key or "").strip()
            == str(value.entry_key or "").strip()
            for candidate in candidates
        ):
            return True
        candidates.append(value)
        return True

    entry_key = str(ref.get("entry_key") or "").strip()
    get_entry = getattr(systems_service, "get_entry_for_campaign", None)
    if entry_key and callable(get_entry):
        entry_key_candidate = get_entry(campaign_slug, entry_key)
        if (
            isinstance(entry_key_candidate, SystemsEntryRecord)
            and str(entry_key_candidate.entry_key or "").strip() == entry_key
        ):
            add_candidate(entry_key_candidate)

    entry_slug = str(ref.get("slug") or "").strip()
    get_entry_by_slug = getattr(
        systems_service,
        "get_entry_by_slug_for_campaign",
        None,
    )
    explicit_slug_resolved = False
    if entry_slug and callable(get_entry_by_slug):
        slug_candidate = get_entry_by_slug(campaign_slug, entry_slug)
        if (
            isinstance(slug_candidate, SystemsEntryRecord)
            and str(slug_candidate.slug or "").strip() == entry_slug
        ):
            explicit_slug_resolved = add_candidate(slug_candidate)

    title = str(ref.get("title") or fallback_title or "").strip()
    search_entries = getattr(systems_service, "search_entries_for_campaign", None)
    search_saturated = False
    if title and callable(search_entries) and not explicit_slug_resolved:
        search_kwargs = {
            "query": title,
            "entry_type": entry_type,
            "limit": _TARGETED_PROFILE_ENTRY_SEARCH_LIMIT,
        }
        source_id = _systems_ref_source_id(ref)
        if source_id:
            try:
                search_results = list(
                    search_entries(
                        campaign_slug,
                        include_source_ids=[source_id],
                        **search_kwargs,
                    )
                    or []
                )
            except TypeError as exc:
                if "include_source_ids" not in str(exc):
                    raise
                search_results = list(
                    search_entries(campaign_slug, **search_kwargs) or []
                )
        else:
            search_results = list(
                search_entries(campaign_slug, **search_kwargs) or []
            )
        search_saturated = (
            len(search_results) >= _TARGETED_PROFILE_ENTRY_SEARCH_LIMIT
        )
        for candidate in search_results:
            if (
                isinstance(candidate, SystemsEntryRecord)
                and normalize_lookup(candidate.title) == normalize_lookup(title)
            ):
                add_candidate(candidate)
    return candidates, search_saturated


def _targeted_profile_campaign_page_options(
    campaign_page_records: list[Any] | None,
    *,
    kind: str,
    page_ref: Any = None,
    fallback_title: str = "",
) -> list[SystemsEntryRecord]:
    selected_page_ref = _extract_campaign_page_ref(page_ref)
    normalized_title = normalize_lookup(fallback_title)
    candidates: list[SystemsEntryRecord] = []
    seen_page_refs: set[str] = set()
    for record in list(campaign_page_records or []):
        entry_record = record
        if isinstance(record, dict):
            page = record.get("page")
            page_payload = dict(page or {}) if isinstance(page, dict) else {}
            record_metadata = dict(
                record.get("metadata") or page_payload.get("metadata") or {}
            )
            record_page_ref = str(
                record.get("page_ref") or page_payload.get("page_ref") or ""
            ).strip()
            record_title = str(
                record.get("title") or page_payload.get("title") or ""
            ).strip()
            entry_record = SimpleNamespace(
                page_ref=record_page_ref,
                metadata=record_metadata,
                body_markdown=str(
                    record.get("body_markdown")
                    or page_payload.get("body_markdown")
                    or ""
                ),
                page=SimpleNamespace(
                    title=record_title,
                    section=str(
                        record.get("section") or page_payload.get("section") or ""
                    ).strip(),
                    subsection=str(
                        record.get("subsection")
                        or page_payload.get("subsection")
                        or ""
                    ).strip(),
                    summary=str(
                        record.get("summary") or page_payload.get("summary") or ""
                    ).strip(),
                ),
            )
        else:
            page = getattr(record, "page", None)
            record_metadata = dict(getattr(record, "metadata", {}) or {})
            record_page_ref = str(
                getattr(record, "page_ref", "") or ""
            ).strip()
            record_title = str(getattr(page, "title", "") or "").strip()
        character_option = dict(record_metadata.get("character_option") or {})
        option_title = str(
            character_option.get("display_name")
            or character_option.get("name")
            or ""
        ).strip()
        matches_page_ref = bool(
            selected_page_ref and record_page_ref == selected_page_ref
        )
        matches_title = bool(
            normalized_title
            and normalized_title
            in {
                normalize_lookup(record_title),
                normalize_lookup(option_title),
            }
        )
        if not (matches_page_ref or matches_title):
            continue
        entry = _build_campaign_page_entry(entry_record, kind=kind)
        if entry is None:
            continue
        entry_page_ref = _entry_page_ref(entry)
        if entry_page_ref in seen_page_refs:
            continue
        seen_page_refs.add(entry_page_ref)
        candidates.append(entry)
    return candidates


def _resolve_targeted_profile_entry(
    systems_service: Any,
    campaign_slug: str,
    *,
    entry_type: str,
    systems_ref: Any = None,
    page_ref: Any = None,
    fallback_title: str = "",
    campaign_page_records: list[Any] | None = None,
    campaign_kind: str = "",
    selected_class: SystemsEntryRecord | None = None,
) -> SystemsEntryRecord | None:
    options, systems_search_saturated = _targeted_profile_systems_options(
        systems_service,
        campaign_slug,
        entry_type=entry_type,
        systems_ref=systems_ref,
        fallback_title=fallback_title,
    )
    if campaign_kind:
        options.extend(
            _targeted_profile_campaign_page_options(
                campaign_page_records,
                kind=campaign_kind,
                page_ref=page_ref,
                fallback_title=fallback_title,
            )
        )
    if entry_type == "class":
        options = [entry for entry in options if _supports_native_class_entry(entry)]
    elif entry_type == "subclass":
        options = [
            entry
            for entry in options
            if selected_class is not None
            and str((entry.metadata or {}).get("class_name") or "").strip()
            == selected_class.title
            and str((entry.metadata or {}).get("class_source") or "")
            .strip()
            .upper()
            == str(selected_class.source_id or "").strip().upper()
            and _supports_native_subclass_entry(
                entry,
                selected_class=selected_class,
            )
        ]
    match = _resolve_profile_entry_match(
        options,
        systems_ref,
        page_ref=page_ref,
        fallback_title=fallback_title,
    )
    if systems_search_saturated and match.get("match_mode") not in {
        PROFILE_ENTRY_MATCH_PAGE_REF,
        PROFILE_ENTRY_MATCH_SYSTEMS_SLUG,
    }:
        return None
    entry = match.get("entry")
    return entry if isinstance(entry, SystemsEntryRecord) else None


def _resolve_definition_targeted_sheet_entries(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    """Resolve scoped-read profile links without building campaign catalogs."""
    selected_class = (
        resolved_class if isinstance(resolved_class, SystemsEntryRecord) else None
    )
    selected_subclass = (
        resolved_subclass
        if isinstance(resolved_subclass, SystemsEntryRecord)
        else None
    )
    selected_species = (
        resolved_species if isinstance(resolved_species, SystemsEntryRecord) else None
    )
    selected_background = (
        resolved_background
        if isinstance(resolved_background, SystemsEntryRecord)
        else None
    )
    if systems_service is None:
        return {
            "selected_class": selected_class,
            "selected_subclass": selected_subclass,
            "selected_species": selected_species,
            "selected_background": selected_background,
            "selected_class_rows": [],
        }

    profile = dict(definition.profile or {})
    if selected_class is None:
        selected_class = _resolve_targeted_profile_entry(
            systems_service,
            definition.campaign_slug,
            entry_type="class",
            systems_ref=profile_primary_class_ref(profile),
            fallback_title=_native_character_class_name(definition),
        )
    if selected_subclass is None and selected_class is not None:
        selected_subclass = _resolve_targeted_profile_entry(
            systems_service,
            definition.campaign_slug,
            entry_type="subclass",
            systems_ref=profile_primary_subclass_ref(profile),
            fallback_title=_native_character_subclass_name(definition),
            selected_class=selected_class,
        )
    class_rows = ensure_profile_class_rows(profile)
    selected_class_rows: list[dict[str, Any]] = []
    for index, row in enumerate(class_rows, start=1):
        row_payload = dict(row or {})
        row_id = str(row_payload.get("row_id") or "").strip() or f"class-row-{index}"
        row_class = selected_class if index == 1 and selected_class is not None else None
        if row_class is None:
            row_class = _resolve_targeted_profile_entry(
                systems_service,
                definition.campaign_slug,
                entry_type="class",
                systems_ref=(
                    profile_primary_class_ref(profile)
                    if index == 1
                    else dict(row_payload.get("systems_ref") or {})
                ),
                fallback_title=str(row_payload.get("class_name") or "").strip(),
            )
        row_subclass = (
            selected_subclass
            if index == 1 and selected_subclass is not None
            else None
        )
        if row_subclass is None and row_class is not None:
            row_subclass = _resolve_targeted_profile_entry(
                systems_service,
                definition.campaign_slug,
                entry_type="subclass",
                systems_ref=(
                    profile_primary_subclass_ref(profile)
                    if index == 1
                    else dict(row_payload.get("subclass_ref") or {})
                ),
                fallback_title=str(row_payload.get("subclass_name") or "").strip(),
                selected_class=row_class,
            )
        if index == 1:
            selected_class = row_class
            selected_subclass = row_subclass
        selected_class_rows.append(
            {
                "row_id": row_id,
                "row_index": index,
                "row_level": int(row_payload.get("level") or 0),
                "class_payload": row_payload,
                "selected_class": row_class,
                "selected_subclass": row_subclass,
            }
        )

    if selected_species is None:
        selected_species = _resolve_targeted_profile_entry(
            systems_service,
            definition.campaign_slug,
            entry_type="race",
            systems_ref=profile.get("species_ref"),
            page_ref=profile.get("species_page_ref"),
            fallback_title=str(profile.get("species") or "").strip(),
            campaign_page_records=campaign_page_records,
            campaign_kind="species",
        )
    if selected_background is None:
        selected_background = _resolve_targeted_profile_entry(
            systems_service,
            definition.campaign_slug,
            entry_type="background",
            systems_ref=profile.get("background_ref"),
            page_ref=profile.get("background_page_ref"),
            fallback_title=str(profile.get("background") or "").strip(),
            campaign_page_records=campaign_page_records,
            campaign_kind="background",
        )
    return {
        "selected_class": selected_class,
        "selected_subclass": selected_subclass,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_class_rows": selected_class_rows,
    }


def _persist_resolved_profile_links(
    profile: dict[str, Any] | None,
    *,
    resolved_entries: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_payload = dict(resolved_entries or {})
    updated_profile = dict(profile or {})
    selected_class_rows = [
        dict(row or {})
        for row in list(resolved_payload.get("selected_class_rows") or [])
        if isinstance(row, dict)
    ]
    if updated_profile:
        updated_rows: list[dict[str, Any]] = []
        for index, row in enumerate(ensure_profile_class_rows(updated_profile), start=1):
            row_payload = dict(row or {})
            row_id = str(row_payload.get("row_id") or "").strip() or f"class-row-{index}"
            row_context = next(
                (
                    candidate
                    for candidate in selected_class_rows
                    if str(candidate.get("row_id") or "").strip() == row_id
                ),
                selected_class_rows[index - 1] if index - 1 < len(selected_class_rows) else {},
            )
            selected_row_class = (
                row_context.get("selected_class")
                if isinstance(row_context.get("selected_class"), SystemsEntryRecord)
                else None
            )
            if selected_row_class is not None:
                row_payload["class_name"] = selected_row_class.title
                row_payload["systems_ref"] = _systems_ref_from_entry(selected_row_class)
            selected_row_subclass = (
                row_context.get("selected_subclass")
                if isinstance(row_context.get("selected_subclass"), SystemsEntryRecord)
                else None
            )
            if selected_row_subclass is not None:
                row_payload["subclass_name"] = selected_row_subclass.title
                row_payload["subclass_ref"] = _systems_ref_from_entry(selected_row_subclass)
            updated_rows.append(row_payload)
        updated_profile = _sync_profile_with_class_rows(updated_profile, updated_rows)

    selected_species = (
        resolved_payload.get("selected_species")
        if isinstance(resolved_payload.get("selected_species"), SystemsEntryRecord)
        else None
    )
    if selected_species is not None:
        species_page_ref = _entry_page_ref(selected_species)
        updated_profile["species"] = selected_species.title
        updated_profile["species_ref"] = None if species_page_ref else _systems_ref_from_entry(selected_species)
        updated_profile["species_page_ref"] = species_page_ref or None

    selected_background = (
        resolved_payload.get("selected_background")
        if isinstance(resolved_payload.get("selected_background"), SystemsEntryRecord)
        else None
    )
    if selected_background is not None:
        background_page_ref = _entry_page_ref(selected_background)
        updated_profile["background"] = selected_background.title
        updated_profile["background_ref"] = None if background_page_ref else _systems_ref_from_entry(selected_background)
        updated_profile["background_page_ref"] = background_page_ref or None

    return sync_profile_class_summary(updated_profile)


def _effective_item_catalog_for_definition(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if item_catalog is not None:
        return dict(item_catalog)
    if systems_service is not None:
        static_bundle = _build_common_builder_static_bundle(
            builder_source_reader(systems_service),
            definition.campaign_slug,
            campaign_page_records=campaign_page_records,
        )
        resolved_catalog = dict(static_bundle.get("item_catalog") or {})
        if resolved_catalog:
            return resolved_catalog
    return _build_item_catalog([])


def _effective_spell_catalog_for_definition(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if spell_catalog is not None:
        return dict(spell_catalog)
    if systems_service is not None:
        static_bundle = _build_common_builder_static_bundle(
            builder_source_reader(systems_service),
            definition.campaign_slug,
            campaign_page_records=campaign_page_records,
        )
        resolved_catalog = dict(static_bundle.get("spell_catalog") or {})
        if resolved_catalog:
            return resolved_catalog
    return _build_spell_catalog([])




























































































































def _native_character_class_name(definition: CharacterDefinition) -> str:
    return profile_primary_class_name(definition.profile)


def _native_level_up_support_error(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_slug: str = "",
    campaign_page_records: list[Any] | None = None,
) -> str:
    if systems_service is not None and str(campaign_slug or "").strip():
        readiness = native_level_up_readiness(
            systems_service,
            campaign_slug,
            definition,
            campaign_page_records=campaign_page_records,
        )
        return str(readiness.get("message") or "").strip()

    source_type = _character_source_type(definition)
    if source_type != "native_character_builder":
        return "Level-up currently supports native in-app characters only."
    classes = profile_class_rows(definition.profile)
    if not classes:
        return "This native character is missing the class link needed for level-up."
    class_payload = dict(classes[0] or {})
    class_ref = profile_primary_class_ref(definition.profile) or dict(class_payload.get("systems_ref") or {})
    if not str(class_ref.get("title") or class_payload.get("class_name") or "").strip():
        return "This native character is missing the class link needed for level-up."
    current_level = _resolve_native_character_level(definition)
    if current_level < 1:
        return "This native character is missing a valid current level."
    if current_level >= 20:
        return "This native character is already at level 20."
    return ""


def _normalize_level_up_values(
    definition: CharacterDefinition,
    values: dict[str, str],
) -> dict[str, str]:
    normalized = {key: str(value) for key, value in dict(values or {}).items()}
    normalized.setdefault("hp_gain", "")
    normalized.setdefault("advancement_record_type", "new")
    normalized.setdefault("advancement_mode", "advance_existing")
    normalized.setdefault("target_class_row_id", "")
    normalized.setdefault("new_class_slug", "")
    normalized.setdefault("new_subclass_slug", "")
    existing_subclass_slug = _systems_ref_slug(profile_primary_subclass_ref(definition.profile))
    if existing_subclass_slug and not str(normalized.get("subclass_slug") or "").strip():
        normalized["subclass_slug"] = existing_subclass_slug
    return normalized


def _sanitize_choice_section_values(
    values: dict[str, str],
    *,
    choice_sections: list[dict[str, Any]],
    static_keys: frozenset[str] | set[str],
) -> dict[str, str]:
    sanitized = {key: str(values.get(key) or "") for key in static_keys if key in values}
    if ACQUISITION_FIELD in values:
        sanitized[ACQUISITION_FIELD] = str(values.get(ACQUISITION_FIELD) or "")
    selected_by_group: dict[str, set[str]] = {}
    for section in list(choice_sections or []):
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "").strip()
            if not field_name:
                continue
            allowed_values = {
                str(option.get("value") or "").strip()
                for option in list(field.get("options") or [])
                if str(option.get("value") or "").strip()
            }
            raw_value = str(values.get(field_name) or "").strip()
            selected_value = _normalize_selected_choice_value(raw_value, allowed_values)
            if selected_value not in allowed_values:
                continue
            group_key = str(field.get("group_key") or field_name).strip() or field_name
            if selected_value in selected_by_group.setdefault(group_key, set()):
                continue
            selected_by_group[group_key].add(selected_value)
            sanitized[field_name] = selected_value
    return sanitized


def _stabilize_choice_section_values(
    values: dict[str, str],
    *,
    static_keys: frozenset[str] | set[str],
    build_sections,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    current_values = {key: str(value) for key, value in dict(values or {}).items()}
    section_cache: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}

    def _build_sections(current_snapshot: dict[str, str]) -> list[dict[str, Any]]:
        cache_key = tuple(sorted((str(key), str(value)) for key, value in current_snapshot.items()))
        if cache_key not in section_cache:
            section_cache[cache_key] = list(build_sections(current_snapshot) or [])
        return section_cache[cache_key]

    def _relevant_section_value_key(
        current_snapshot: dict[str, str],
        choice_sections: list[dict[str, Any]],
    ) -> tuple[tuple[str, str], ...]:
        relevant_keys = {str(key) for key in static_keys}
        for section in list(choice_sections or []):
            for field in list(section.get("fields") or []):
                field_name = str(field.get("name") or "").strip()
                if field_name:
                    relevant_keys.add(field_name)
        return tuple(
            sorted(
                (key, str(current_snapshot.get(key) or ""))
                for key in relevant_keys
                if key in current_snapshot
            )
        )

    choice_sections = _build_sections(current_values)
    relevant_value_key = _relevant_section_value_key(current_values, choice_sections)
    for _ in range(4):
        sanitized_values = _sanitize_choice_section_values(
            current_values,
            choice_sections=choice_sections,
            static_keys=static_keys,
        )
        if sanitized_values == current_values:
            break
        current_values = sanitized_values
        choice_sections = _build_sections(current_values)
        relevant_value_key = _relevant_section_value_key(current_values, choice_sections)
    return current_values, choice_sections


def _class_requires_subclass_at_level(
    selected_class: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    target_level: int,
) -> bool:
    if selected_class is None:
        return False
    subclass_title = str(selected_class.metadata.get("subclass_title") or "").strip()
    if not subclass_title:
        return False
    normalized_subclass_title = normalize_lookup(subclass_title)
    for group in class_progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = normalize_lookup(feature_row.get("label"))
            if normalized_subclass_title and normalized_subclass_title in label:
                return True
            if "choose subclass feature" in label:
                return True
    return False


def _class_requires_subclass_at_level_one(
    selected_class: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
) -> bool:
    return _class_requires_subclass_at_level(selected_class, class_progression, 1)


def _build_choice_sections(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    feat_catalog: dict[str, Any],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    equipment_groups: list[dict[str, Any]],
    campaign_feature_options: list[dict[str, str]],
    campaign_item_options: list[dict[str, str]],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    feat_selections = _resolve_builder_feat_selections(values, feat_catalog, selected_species=selected_species)

    class_fields = _build_class_skill_fields(selected_class, values)
    class_option_fields = _build_class_option_fields(class_progression, values)
    class_feature_choice_fields = _build_feature_choice_fields(
        feature_selections=_progression_feature_choice_selections(
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            target_level=1,
            instance_prefix="level1_feature",
        ),
        values=values, item_catalog=item_catalog,
    )
    if class_fields or class_option_fields or class_feature_choice_fields:
        sections.append({"title": "Class Choices", "fields": class_fields + class_option_fields + class_feature_choice_fields})

    species_fields = _build_species_choice_fields(selected_species, feat_options, values)
    if species_fields:
        sections.append({"title": "Species Choices", "fields": species_fields})

    background_fields = _build_background_choice_fields(selected_background, values, item_catalog=item_catalog)
    if background_fields:
        sections.append({"title": "Background Choices", "fields": background_fields})

    feat_fields = _build_feat_choice_fields(
        feat_selections=feat_selections,
        values=values,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
    )
    if feat_fields:
        sections.append({"title": "Feat Choices", "fields": feat_fields})

    equipment_fields = _build_equipment_choice_fields(equipment_groups)
    if equipment_fields:
        sections.append({"title": "Equipment Choices", "fields": equipment_fields})

    campaign_feature_fields = _build_campaign_feature_choice_fields(campaign_feature_options, values)
    if campaign_feature_fields:
        sections.append({"title": "Campaign Features", "fields": campaign_feature_fields})

    campaign_item_fields = _build_campaign_item_choice_fields(campaign_item_options, values)
    if campaign_item_fields:
        sections.append({"title": "Campaign Equipment", "fields": campaign_item_fields})

    preview_choice_sections = list(sections)
    _, preview_selected_choices = _resolve_builder_choices(preview_choice_sections, values, strict=False)
    selected_feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=preview_choice_sections,
        selected_choices=preview_selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    preview_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(selected_feature_entries)
    )
    spell_fields = _build_spell_choice_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        feature_entries=selected_feature_entries,
        campaign_option_payloads=preview_campaign_option_payloads,
    )
    if spell_fields:
        sections.append({"title": "Spell Choices", "fields": spell_fields})

    return sections


def _build_level_up_choice_sections(
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
    target_level: int,
    current_ability_scores: dict[str, int],
    values: dict[str, str],
    class_row_id: str = "",
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    class_fields: list[dict[str, Any]] = []
    ability_fields = _build_level_up_ability_score_fields(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
    )
    preview_ability_scores, level_up_feat_entries, _ = _resolve_level_up_ability_score_choices(
        current_ability_scores=current_ability_scores,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
        strict=False,
    )
    if requires_subclass:
        class_fields.append(
            {
                "name": "subclass_slug",
                "label": str(selected_class.metadata.get("subclass_title") or "Subclass").strip(),
                "help_text": f"Choose your {selected_class.title} subclass.",
                "options": [_choice_option(_entry_option_label(entry), entry.slug) for entry in subclass_options],
                "selected": str(values.get("subclass_slug") or "").strip(),
                "group_key": "subclass_slug",
                "kind": "subclass",
            }
        )
    class_fields.extend(
        _build_progression_option_fields(
            class_progression,
            target_level=target_level,
            values=values,
            field_prefix="levelup_class_option",
            group_key_prefix="levelup_class_options",
        )
    )
    class_fields.extend(
        _build_progression_option_fields(
            subclass_progression,
            target_level=target_level,
            values=values,
            field_prefix="levelup_subclass_option",
            group_key_prefix="levelup_subclass_options",
        )
    )
    class_fields.extend(
        _build_feature_choice_fields(
            feature_selections=_progression_feature_choice_selections(
                class_progression=class_progression,
                subclass_progression=subclass_progression,
                target_level=target_level,
                instance_prefix="levelup_feature",
            ),
            values=values, item_catalog=item_catalog,
        )
    )
    if class_fields:
        sections.append({"title": "Class Choices", "fields": class_fields})
    if ability_fields:
        sections.append({"title": "Ability Score Improvement", "fields": ability_fields})

    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    feat_fields = _build_feat_choice_fields(
        feat_selections=feat_selections,
        values=values,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
    )
    if feat_fields:
        sections.append({"title": "Feat Choices", "fields": feat_fields})

    preview_choice_sections = list(sections)
    _, preview_selected_choices = _resolve_builder_choices(preview_choice_sections, values, strict=False)
    preview_ability_scores = _apply_feat_ability_score_bonuses(
        preview_ability_scores,
        feat_selections=feat_selections,
        selected_choices=preview_selected_choices,
        strict=False,
    )
    preview_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=preview_selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    preview_feature_entries.extend(level_up_feat_entries)
    preview_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=preview_selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    preview_automatic_prepared_feature_entries = _automatic_prepared_feature_entries(
        feature_entries=preview_feature_entries,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=preview_selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    spell_fields = _build_level_up_spell_choice_fields(
        definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        target_level=target_level,
        ability_scores=preview_ability_scores,
        values=values,
        feature_entries=preview_feature_entries,
        automatic_prepared_feature_entries=preview_automatic_prepared_feature_entries,
        class_row_id=class_row_id,
    )
    if spell_fields:
        sections.append({"title": "Spell Choices", "fields": spell_fields})
    return sections


def _build_class_skill_fields(
    selected_class: SystemsEntryRecord | None,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    starting_proficiencies = dict(selected_class.metadata.get("starting_proficiencies") or {})
    skill_blocks = list(starting_proficiencies.get("skills") or [])
    fields: list[dict[str, Any]] = []
    for block in skill_blocks:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        options = [_choice_option(_skill_label(option), option) for option in list(choose.get("from") or [])]
        count = int(choose.get("count") or 0)
        if not options or count <= 0:
            continue
        for index in range(count):
            field_name = f"class_skill_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Class Skill {index + 1}",
                    "help_text": f"Choose {count} skill{'s' if count != 1 else ''} from {selected_class.title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "class_skills",
                    "kind": "skill",
                }
            )
    return fields


def _build_class_option_fields(
    class_progression: list[dict[str, Any]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    return _build_progression_option_fields(
        class_progression,
        target_level=1,
        values=values,
        field_prefix="class_option",
    )


def _build_progression_option_fields(
    progression: list[dict[str, Any]],
    *,
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    index = 0
    for group in progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if not option_groups:
                continue
            feature_label = str(feature_row.get("label") or "Feature").strip()
            for option_group in option_groups:
                index += 1
                field_name = f"{field_prefix}_{index}"
                options = [
                    _choice_option(str(option.get("label") or ""), str(option.get("slug") or ""))
                    for option in list(option_group.get("options") or [])
                    if str(option.get("slug") or "").strip()
                ]
                if not options:
                    continue
                fields.append(
                    {
                        "name": field_name,
                        "label": feature_label,
                        "help_text": f"Choose an option for {feature_label}.",
                        "options": options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": str(group_key_prefix or field_name),
                        "kind": "optionalfeature",
                    }
    )
    return fields


def _count_ability_score_improvements_for_level(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
) -> int:
    count = 0
    for progression in (class_progression, subclass_progression):
        for group in progression:
            if int(group.get("level") or 0) != target_level:
                continue
            for feature_row in list(group.get("feature_rows") or []):
                label = normalize_lookup(feature_row.get("label"))
                if label in ABILITY_SCORE_IMPROVEMENT_NAMES:
                    count += 1
    return count


def _build_level_up_ability_score_fields(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[Any],
    target_level: int,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    if improvement_count <= 0:
        return []

    ability_options = [_choice_option(label, key) for key, label in ABILITY_LABELS.items()]
    feat_field_options = [
        _choice_option(_entry_option_label(entry), _entry_selection_value(entry) or _entry_option_slug(entry))
        for entry in feat_options
        if _entry_selection_value(entry) or _entry_option_slug(entry)
    ]
    mode_options = [
        _choice_option("Ability Scores", "ability_scores"),
        _choice_option("Feat", "feat"),
    ]

    fields: list[dict[str, Any]] = []
    for index in range(1, improvement_count + 1):
        mode_field_name = f"levelup_asi_mode_{index}"
        selected_mode = str(values.get(mode_field_name) or "ability_scores").strip() or "ability_scores"
        fields.append(
            {
                "name": mode_field_name,
                "label": f"Improvement {index}",
                "help_text": "Choose whether this advancement is an ability score increase or a feat.",
                "options": mode_options,
                "selected": selected_mode,
                "group_key": mode_field_name,
                "kind": "asi_mode",
            }
        )
        if selected_mode == "feat":
            feat_field_name = f"levelup_feat_{index}"
            fields.append(
                {
                    "name": feat_field_name,
                    "label": f"Feat {index}",
                    "help_text": "Choose the feat gained from this ability score improvement.",
                    "options": feat_field_options,
                    "selected": str(values.get(feat_field_name) or "").strip(),
                    "group_key": feat_field_name,
                    "kind": "feat",
                }
            )
            continue

        first_field_name = f"levelup_asi_ability_{index}_1"
        second_field_name = f"levelup_asi_ability_{index}_2"
        fields.append(
            {
                "name": first_field_name,
                "label": f"Ability Increase {index}.1",
                "help_text": "Choose the first +1 ability increase. Pick the same ability twice to gain +2.",
                "options": ability_options,
                "selected": str(values.get(first_field_name) or "").strip(),
                "group_key": first_field_name,
                "kind": "ability",
            }
        )
        fields.append(
            {
                "name": second_field_name,
                "label": f"Ability Increase {index}.2",
                "help_text": "Choose the second +1 ability increase. Pick the same ability twice to gain +2.",
                "options": ability_options,
                "selected": str(values.get(second_field_name) or "").strip(),
                "group_key": second_field_name,
                "kind": "ability",
            }
        )
    return fields


def _resolve_level_up_ability_score_choices(
    *,
    current_ability_scores: dict[str, int],
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[Any],
    target_level: int,
    values: dict[str, str],
    strict: bool,
) -> tuple[dict[str, int], list[dict[str, Any]], list[str]]:
    updated_scores = dict(current_ability_scores)
    feat_entries: list[dict[str, Any]] = []
    summaries: list[str] = []
    feat_lookup = {
        candidate: _entry_option_title(entry)
        for entry in feat_options
        for candidate in (
            _entry_selection_value(entry),
            _entry_option_slug(entry),
            _entry_page_ref(entry),
        )
        if candidate
    }

    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    for index in range(1, improvement_count + 1):
        mode_field_name = f"levelup_asi_mode_{index}"
        mode = str(values.get(mode_field_name) or "ability_scores").strip() or "ability_scores"
        if mode == "feat":
            feat_field_name = f"levelup_feat_{index}"
            feat_slug = str(values.get(feat_field_name) or "").strip()
            if not feat_slug:
                if strict:
                    raise CharacterBuildError("Choose a feat or ability score increase for this level.")
                continue
            feat_title = feat_lookup.get(feat_slug)
            if not feat_title:
                if strict:
                    raise CharacterBuildError("Choose a valid feat for this ability score improvement.")
                continue
            feat_entry = next(
                (
                    entry
                    for entry in feat_options
                    if feat_slug in {
                        _entry_selection_value(entry),
                        _entry_option_slug(entry),
                        _entry_page_ref(entry),
                    }
                ),
                None,
            )
            feat_entries.append(
                _build_feat_feature_entry(
                    selection={
                        "instance_key": feat_field_name,
                        "native_acquisition": _level_up_feat_acquisition(
                            class_progression, subclass_progression,
                            target_level=target_level, selection_index=index,
                        ),
                        "selection_value": feat_slug,
                        "slug": _entry_option_slug(feat_entry)
                        or (
                            feat_slug[len(SYSTEMS_OPTION_PREFIX):]
                            if feat_slug.startswith(SYSTEMS_OPTION_PREFIX)
                            else feat_slug
                        ),
                        "entry": feat_entry,
                        "label": feat_title,
                        "page_ref": _entry_page_ref(feat_entry),
                        "source_id": _entry_option_source_id(feat_entry) or PHB_SOURCE_ID,
                        "campaign_option": _entry_campaign_option(feat_entry) or None,
                    },
                    values=values,
                    fallback_title=feat_title,
                )
            )
            summaries.append(feat_title)
            continue

        first_field_name = f"levelup_asi_ability_{index}_1"
        second_field_name = f"levelup_asi_ability_{index}_2"
        selected_keys = [
            str(values.get(first_field_name) or "").strip(),
            str(values.get(second_field_name) or "").strip(),
        ]
        if not all(selected_keys):
            if strict:
                raise CharacterBuildError("Choose both ability score increases for this level.")
            continue
        for ability_key in selected_keys:
            if ability_key not in ABILITY_KEYS:
                if strict:
                    raise CharacterBuildError("Choose valid abilities for this ability score improvement.")
                break
        else:
            increments: dict[str, int] = {}
            for ability_key in selected_keys:
                increments[ability_key] = increments.get(ability_key, 0) + 1
            for ability_key, increment in increments.items():
                next_score = int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + increment
                if next_score > 20:
                    if strict:
                        raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} cannot exceed 20 from an ability score improvement.")
                    break
            else:
                for ability_key, increment in increments.items():
                    updated_scores[ability_key] = int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + increment
                if selected_keys[0] == selected_keys[1]:
                    summaries.append(f"{ABILITY_LABELS[selected_keys[0]]} +2")
                else:
                    summaries.append(
                        f"{ABILITY_LABELS[selected_keys[0]]} +1, {ABILITY_LABELS[selected_keys[1]]} +1"
                    )
                continue
        if not strict:
            continue
        raise CharacterBuildError("Choose valid ability score increases for this level.")
    return updated_scores, feat_entries, summaries


def _build_species_choice_fields(
    selected_species: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_species is None:
        return []
    fields: list[dict[str, Any]] = []
    metadata = dict(selected_species.metadata or {})

    skill_blocks = list(metadata.get("skill_proficiencies") or [])
    species_skill_count = 0
    for block in skill_blocks:
        if not isinstance(block, dict):
            continue
        any_count = int(block.get("any") or 0)
        for _ in range(any_count):
            species_skill_count += 1
            field_name = f"species_skill_{species_skill_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Species Skill {species_skill_count}",
                    "help_text": "Choose a species-granted skill proficiency.",
                    "options": [_choice_option(label, token) for token, label in _all_skill_options()],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_skills",
                    "kind": "skill",
                }
            )

    language_blocks = list(metadata.get("languages") or [])
    species_language_count = 0
    for block in language_blocks:
        if not isinstance(block, dict):
            continue
        any_standard = int(block.get("anyStandard") or 0)
        for _ in range(any_standard):
            species_language_count += 1
            field_name = f"species_language_{species_language_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Species Language {species_language_count}",
                    "help_text": "Choose an extra standard language.",
                    "options": [_choice_option(label, label) for label in language_options_for_block(block)],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_languages",
                    "kind": "language",
                }
            )

    feat_blocks = list(metadata.get("feats") or [])
    feat_count = 0
    for block in feat_blocks:
        if not isinstance(block, dict):
            continue
        any_count = int(block.get("any") or 0)
        for _ in range(any_count):
            feat_count += 1
            field_name = f"species_feat_{feat_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": "Species Feat",
                    "help_text": "Choose a feat granted by your species.",
                    "options": [
                        _choice_option(_entry_option_label(entry), _entry_selection_value(entry) or entry.slug)
                        for entry in feat_options
                        if _entry_selection_value(entry) or entry.slug
                    ],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_feats",
                    "kind": "feat",
                }
            )

    return fields


def _build_background_choice_fields(
    selected_background: SystemsEntryRecord | None,
    values: dict[str, str],
    *, item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if selected_background is None:
        return []
    fields: list[dict[str, Any]] = []
    metadata = dict(selected_background.metadata or {})
    from .character_language_choices import background_language_slots
    try:
        language_slots = background_language_slots(selected_background)
    except ValueError as exc:
        raise CharacterBuildError(str(exc)) from exc
    background_language_count = 0
    for slot in language_slots:
        background_language_count += 1
        field_name = f"background_language_{background_language_count}"
        fields.append(
            {
                "name": field_name,
                "label": f"Background Language {background_language_count}",
                "help_text": ("Choose a replacement only if your selected species already grants " + slot["condition"] + "."
                              if slot.get("condition") else "Choose a background language."),
                "options": ([_choice_option("Gain " + slot["condition"] + " (not previously known)", "__grant__")]
                            if slot.get("condition") else [])
                           + [_choice_option(label, label) for label in slot["options"]],
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": "background_languages",
                "kind": "language",
            }
        )
    instruments = _background_instrument_entries(catalog_snapshot(item_catalog or {}))
    equipment_note = str(dict(metadata.get("background_copy") or {}).get("equipment_note") or "")
    for index in range(1, _background_instrument_count(selected_background) + 1):
        name = f"background_instrument_{index}"
        fields.append({
            "name": name, "label": f"Background Instrument {index}",
            "help_text": "Choose an enabled source-backed musical instrument proficiency; this does not grant an item." + (f" {equipment_note}" if equipment_note else ""),
            "options": [_choice_option(_entry_option_label(entry), entry.entry_key) for entry in instruments],
            "selected": str(values.get(name) or ""), "group_key": "background_instruments", "kind": "tool",
        })
    return fields


def _background_instrument_count(background: SystemsEntryRecord | None) -> int:
    if background is None:
        return 0
    blocks = [block for block in list(dict(background.metadata or {}).get("tool_proficiencies") or [])
              if isinstance(block, dict) and "anyMusicalInstrument" in block]
    if not blocks:
        return 0
    count = blocks[0]["anyMusicalInstrument"]
    if len(blocks) != 1 or type(count) is not int or not 1 <= count <= 8:
        raise CharacterBuildError("This background's musical instrument choices need source repair.")
    return count


def _background_instrument_entries(item_catalog: dict[str, Any]) -> list[SystemsEntryRecord]:
    field = lambda entry, name: catalog_field(item_catalog, entry, name)
    rows = [entry for entry in catalog_rows(item_catalog)
               if catalog_is_record(item_catalog, entry) and field(entry, "entry_type") == "item"
               and _item_type_code(entry, _field=field) == "INS" and field(entry, "entry_key") and field(entry, "title")]
    entries = [catalog_record(item_catalog, row) for row in rows]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.entry_key] = counts.get(entry.entry_key, 0) + 1
    return [entry for entry in entries if counts[entry.entry_key] == 1]


def _background_instrument_payload(
    background: SystemsEntryRecord | None, values: dict[str, str], item_catalog: dict[str, Any], *, strict: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    count = _background_instrument_count(background)
    allowed_fields = {f"background_instrument_{index}" for index in range(1, count + 1)}
    if strict and any(str(key).startswith("background_instrument_") and key not in allowed_fields for key in values):
        raise CharacterBuildError("A background instrument choice does not belong to the current background.")
    if not count:
        return None, []
    entries = {entry.entry_key: entry for entry in _background_instrument_entries(item_catalog)}
    selected: list[SystemsEntryRecord] = []
    for index in range(1, count + 1):
        entry = entries.get(str(values.get(f"background_instrument_{index}") or "").strip())
        if entry is None:
            if strict:
                raise CharacterBuildError("Choose every background instrument from the enabled musical instrument sources.")
            return None, []
        selected.append(entry)
    if (len({entry.entry_key for entry in selected}) != count
            or len({normalize_lookup(entry.title) for entry in selected}) != count):
        if strict:
            raise CharacterBuildError("Choose distinct background instruments.")
        return None, []
    return {"schema_version": 1, "owner": _systems_ref_from_entry(background),
            "instrument": {"category": "INS", "count": count,
                           "entries": [_systems_ref_from_entry(entry) for entry in selected]}}, [entry.title for entry in selected]


def _background_instrument_saved_values(
    definition: CharacterDefinition, background: SystemsEntryRecord | None, item_catalog: dict[str, Any], *, strict: bool = False,
) -> dict[str, str]:
    saved = dict(definition.profile or {}).get("background_choices")
    count = _background_instrument_count(background)
    if saved in (None, {}):
        if strict and count:
            raise CharacterBuildError("Choose the missing background instrument in Advanced Edit before continuing.")
        return {}
    try:
        if (not isinstance(saved, dict) or set(saved) != {"schema_version", "owner", "instrument"}
                or type(saved.get("schema_version")) is not int or saved["schema_version"] != 1
                or saved.get("owner") != _systems_ref_from_entry(background)):
            raise ValueError
        instrument = saved["instrument"]
        if (not isinstance(instrument, dict) or set(instrument) != {"category", "count", "entries"}
                or instrument.get("category") != "INS" or type(instrument.get("count")) is not int
                or instrument["count"] != count or not isinstance(instrument.get("entries"), list)
                or len(instrument["entries"]) != count):
            raise ValueError
        lookup = {entry.entry_key: entry for entry in _background_instrument_entries(item_catalog)}
        values = {}
        for index, ref in enumerate(instrument["entries"], start=1):
            entry = lookup.get(str(ref.get("entry_key") or "")) if isinstance(ref, dict) else None
            if entry is None or ref != _systems_ref_from_entry(entry):
                raise ValueError
            values[f"background_instrument_{index}"] = entry.entry_key
        _background_instrument_payload(background, values, item_catalog, strict=True)
        return values
    except (TypeError, ValueError, CharacterBuildError):
        if strict:
            raise CharacterBuildError("The saved background instrument source changed. Review its choice in Advanced Edit.") from None
        return {}


def current_background_entry(definition: CharacterDefinition, systems_service: Any) -> SystemsEntryRecord | None:
    ref = dict(definition.profile or {}).get("background_ref")
    if not isinstance(ref, dict):
        return None
    key = str(ref.get("entry_key") or "")
    entry = systems_service.get_entry_for_campaign(definition.campaign_slug, key) if key else None
    return (entry if isinstance(entry, SystemsEntryRecord) and entry.entry_type == "background"
            and ref == _systems_ref_from_entry(entry) else None)


def validated_background_instrument_names(
    definition: CharacterDefinition, systems_service: Any, item_catalog: dict[str, Any] | None = None, *, strict: bool = True,
) -> list[str]:
    """Reconstruct this bounded background entitlement from current exact sources."""
    try:
        background = current_background_entry(definition, systems_service)
        if background is None:
            if dict(definition.profile or {}).get("background_choices"):
                raise CharacterBuildError("The background instrument owner is unavailable or changed.")
            return []
        saved = dict(definition.profile or {}).get("background_choices")
        instrument = saved.get("instrument") if isinstance(saved, dict) else None
        refs = instrument.get("entries", []) if isinstance(instrument, dict) else []
        if not isinstance(refs, list) or len(refs) > 8:
            raise CharacterBuildError("The saved background instrument selection is invalid.")
        # Reload every selected source independently; a caller's item subset is
        # only a presentation optimization, never source-currentness authority.
        current = []
        for ref in refs:
            key = str(ref.get("entry_key") or "") if isinstance(ref, dict) else ""
            entry = systems_service.get_entry_for_campaign(definition.campaign_slug, key) if key else None
            if not isinstance(entry, SystemsEntryRecord) or ref != _systems_ref_from_entry(entry):
                raise CharacterBuildError("A selected background instrument source is unavailable or changed.")
            current.append(entry)
        catalog = {"entries": current}
        values = _background_instrument_saved_values(definition, background, catalog, strict=True)
        return _background_instrument_payload(background, values, catalog, strict=True)[1]
    except CharacterBuildError:
        if strict:
            raise
        return []




def _feature_expertise_tool_value(tool_name: Any) -> str:
    cleaned = _clean_embedded_text(str(tool_name or "")).strip()
    if not cleaned:
        return ""
    return f"{FEATURE_EXPERTISE_TOOL_VALUE_PREFIX}{cleaned}"




def _feature_expertise_supports_thieves_tools(entry: SystemsEntryRecord | None) -> bool:
    if not isinstance(entry, SystemsEntryRecord):
        return False
    for block in list(dict(entry.metadata or {}).get("expertise") or []):
        if not isinstance(block, dict):
            continue
        for expertise_name, value in dict(block).items():
            if expertise_name == "anyProficientSkill" or value is not True:
                continue
            if normalize_lookup(expertise_name) == normalize_lookup(THIEVES_TOOLS_PROFICIENCY):
                return True
    return normalize_lookup(THIEVES_TOOLS_PROFICIENCY) in _normalized_entry_body_text(entry)




def _progression_feature_choice_selections(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
    instance_prefix: str,
) -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    seen_instance_keys: set[str] = set()
    for scope, progression in (("class", class_progression), ("subclass", subclass_progression)):
        for group in list(progression or []):
            if int(group.get("level") or 0) != target_level:
                continue
            for feature_row in list(group.get("feature_rows") or []):
                entry = feature_row.get("entry")
                if not isinstance(entry, SystemsEntryRecord):
                    continue
                from .character_feature_proficiency_grants import contract
                fixed_grants, grant_slots = contract(entry)
                if not (_supported_feature_expertise_blocks(entry) or any(fixed_grants.values()) or grant_slots):
                    continue
                instance_token = (
                    str(entry.slug or "").strip()
                    or str(entry.entry_key or "").strip()
                    or slugify(str(entry.title or "").strip())
                )
                if not instance_token:
                    continue
                instance_key = f"{instance_prefix}_{scope}_{target_level}_{slugify(instance_token)}"
                if instance_key in seen_instance_keys:
                    continue
                seen_instance_keys.add(instance_key)
                selections.append({"instance_key": instance_key, "entry": entry})
    return selections


def _build_feature_choice_fields(
    *,
    feature_selections: list[dict[str, Any]],
    values: dict[str, str],
    include_proficiency_grants: bool = True,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from .character_feature_proficiency_grants import choice_fields
    fields: list[dict[str, Any]] = choice_fields(feature_selections, values, item_catalog=item_catalog) if include_proficiency_grants else []
    skill_options = [_choice_option(label, token) for token, label in _all_skill_options()]
    for selection in feature_selections:
        feature_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feature_entry, SystemsEntryRecord) or not instance_key:
            continue
        expertise_blocks = _supported_feature_expertise_blocks(feature_entry)
        if not expertise_blocks:
            continue
        expertise_choice_count = sum(int(block.get("anyProficientSkill") or 0) for block in expertise_blocks)
        if expertise_choice_count <= 0:
            continue
        feature_title = _feature_choice_display_title(feature_entry)
        expertise_options = list(skill_options)
        help_text = f"Choose a skill that already has proficiency so {feature_title} can grant expertise."
        if _feature_expertise_supports_thieves_tools(feature_entry):
            expertise_options.append(
                _choice_option(
                    THIEVES_TOOLS_PROFICIENCY,
                    _feature_expertise_tool_value(THIEVES_TOOLS_PROFICIENCY),
                )
            )
            help_text = (
                f"Choose a skill or tool proficiency that already has proficiency so {feature_title} can grant expertise."
            )
        expertise_choice_index = 0
        for block in expertise_blocks:
            count = int(block.get("anyProficientSkill") or 0)
            if count <= 0:
                continue
            for _ in range(count):
                expertise_choice_index += 1
                label_suffix = f" {expertise_choice_index}" if expertise_choice_count > 1 else ""
                field_name = _feature_field_name(instance_key, "expertise", expertise_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feature_title}{label_suffix}",
                        "help_text": help_text,
                        "options": expertise_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feature_group_key(instance_key, "expertise"),
                        "kind": "feature_skill",
                    }
                )
    return fields


def _build_feat_choice_fields(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for selection in feat_selections:
        fields.extend(
            _build_feat_choice_fields_for_selection(
                selection=selection,
                values=values,
                optionalfeature_catalog=optionalfeature_catalog,
                item_catalog=item_catalog,
            )
        )
    return fields


def _build_feat_choice_fields_for_selection(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []

    metadata = dict(feat_entry.metadata or {})
    feat_title = feat_entry.title
    fields: list[dict[str, Any]] = []
    ability_options = [_choice_option(label, key) for key, label in ABILITY_LABELS.items()]
    skill_options = [_choice_option(label, token) for token, label in _all_skill_options()]
    language_options = [_choice_option(label, label) for label in UNRESTRICTED_LANGUAGE_OPTIONS]
    tool_options = _tool_proficiency_options(item_catalog)
    weapon_options = _weapon_proficiency_options(item_catalog)

    ability_choice_index = 0
    for block in list(metadata.get("ability") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        options = [
            _choice_option(ABILITY_LABELS.get(str(option), _humanize_words(str(option))), str(option))
            for option in list(choose.get("from") or [])
            if str(option) in ABILITY_KEYS
        ]
        count = max(int(choose.get("count") or 1), 0)
        if not options or count <= 0:
            continue
        for _ in range(count):
            ability_choice_index += 1
            field_name = _feat_field_name(instance_key, "ability", ability_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Ability",
                    "help_text": f"Choose the ability increased by {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "ability"),
                    "kind": "feat_ability",
                }
            )

    skill_choice_index = 0
    for block in list(metadata.get("skill_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        options = [
            _choice_option(_skill_label(option), str(option))
            for option in list(choose.get("from") or [])
            if normalize_lookup(str(option)) in SKILL_LABELS
        ]
        count = int(choose.get("count") or 1)
        if not options and int(block.get("any") or 0) > 0:
            options = skill_options
            count = int(block.get("any") or 0)
        if not options or count <= 0:
            continue
        for _ in range(count):
            skill_choice_index += 1
            field_name = _feat_field_name(instance_key, "skills", skill_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Skill {skill_choice_index}",
                    "help_text": f"Choose a skill granted by {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "skills"),
                    "kind": "feat_skill",
                }
            )

    expertise_choice_count = sum(
        int(dict(block).get("anyProficientSkill") or 0)
        for block in list(metadata.get("expertise") or [])
        if isinstance(block, dict)
    )
    expertise_choice_index = 0
    for block in list(metadata.get("expertise") or []):
        if not isinstance(block, dict):
            continue
        count = int(block.get("anyProficientSkill") or 0)
        if count <= 0:
            continue
        for _ in range(count):
            expertise_choice_index += 1
            field_name = _feat_field_name(instance_key, "expertise", expertise_choice_index)
            label_suffix = f" {expertise_choice_index}" if expertise_choice_count > 1 else ""
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Expertise{label_suffix}",
                    "help_text": f"Choose a skill that already has proficiency so {feat_title} can grant expertise.",
                    "options": skill_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "expertise"),
                    "kind": "feat_skill",
                }
            )

    language_choice_index = 0
    for block in list(metadata.get("language_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        count = int(block.get("anyStandard") or block.get("any") or 0)
        if count <= 0:
            continue
        for _ in range(count):
            language_choice_index += 1
            field_name = _feat_field_name(instance_key, "languages", language_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Language {language_choice_index}",
                    "help_text": f"Choose a language granted by {feat_title}.",
                    "options": [_choice_option(label, label) for label in language_options_for_block(block)],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "languages"),
                    "kind": "feat_language",
                }
            )

    tool_choice_index = 0
    for block in list(metadata.get("tool_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        any_artisan_count = int(block.get("anyArtisansTool") or 0)
        any_tool_count = int(block.get("any") or block.get("anyTool") or 0)
        if any_artisan_count > 0:
            for _ in range(any_artisan_count):
                tool_choice_index += 1
                field_name = _feat_field_name(instance_key, "tools", tool_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Tool {tool_choice_index}",
                        "help_text": f"Choose an artisan's tool granted by {feat_title}.",
                        "options": _tool_proficiency_options(item_catalog, artisan_only=True),
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "tools"),
                        "kind": "feat_tool",
                    }
                )
        if any_tool_count > 0:
            for _ in range(any_tool_count):
                tool_choice_index += 1
                field_name = _feat_field_name(instance_key, "tools", tool_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Tool {tool_choice_index}",
                        "help_text": f"Choose a tool granted by {feat_title}.",
                        "options": tool_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "tools"),
                        "kind": "feat_tool",
                    }
                )

    weapon_choice_index = 0
    for block in list(metadata.get("weapon_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        count = int(choose.get("count") or 0)
        if count <= 0:
            continue
        for _ in range(count):
            weapon_choice_index += 1
            field_name = _feat_field_name(instance_key, "weapons", weapon_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Weapon {weapon_choice_index}",
                    "help_text": f"Choose a weapon granted by {feat_title}.",
                    "options": weapon_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "weapons"),
                    "kind": "feat_weapon",
                }
            )

    mixed_choice_index = 0
    for block in list(metadata.get("skill_tool_language_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        for choose_block in list(block.get("choose") or []):
            if not isinstance(choose_block, dict):
                continue
            count = int(choose_block.get("count") or 0)
            if count <= 0:
                continue
            options: list[dict[str, str]] = []
            from_values = [str(value or "").strip() for value in list(choose_block.get("from") or [])]
            if "anySkill" in from_values:
                options.extend(
                    _choice_option(f"Skill: {label}", f"skill:{token}")
                    for token, label in _all_skill_options()
                )
            if "anyTool" in from_values:
                options.extend(
                    _choice_option(f"Tool: {option['label']}", f"tool:{option['value']}")
                    for option in tool_options
                )
            if "anyLanguage" in from_values:
                options.extend(
                    _choice_option(f"Language: {option['label']}", f"language:{option['value']}")
                    for option in language_options
                )
            if not options:
                continue
            for _ in range(count):
                mixed_choice_index += 1
                field_name = _feat_field_name(instance_key, "skill_tool_language", mixed_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Choice {mixed_choice_index}",
                        "help_text": f"Choose a skill, tool, or language granted by {feat_title}.",
                        "options": options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "skill_tool_language"),
                        "kind": "feat_mixed_proficiency",
                    }
                )

    if normalize_lookup(feat_title) != normalize_lookup("Resilient"):
        save_choice_index = 0
        for block in list(metadata.get("saving_throw_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            choose = dict(block.get("choose") or {})
            options = [
                _choice_option(ABILITY_LABELS.get(str(option), _humanize_words(str(option))), str(option))
                for option in list(choose.get("from") or [])
                if str(option) in ABILITY_KEYS
            ]
            count = max(int(choose.get("count") or 1), 0)
            if not options or count <= 0:
                continue
            for _ in range(count):
                save_choice_index += 1
                field_name = _feat_field_name(instance_key, "saving_throws", save_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Saving Throw",
                        "help_text": f"Choose the saving throw proficiency granted by {feat_title}.",
                        "options": ability_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "saving_throws"),
                        "kind": "feat_save",
                    }
                )

    for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
        section_index = int(section.get("index") or 0)
        if section_index <= 0:
            continue
        category = _feat_optionalfeature_category(section_index)
        options = [dict(option) for option in list(section.get("options") or []) if str(option.get("value") or "").strip()]
        if not options:
            continue
        choice_count = max(int(section.get("count") or 0), 0)
        if choice_count <= 0:
            continue
        section_title = str(section.get("title") or "Optional Feature").strip() or "Optional Feature"
        for choice_index in range(1, choice_count + 1):
            field_name = _feat_field_name(instance_key, category, choice_index)
            label_suffix = f" {choice_index}" if choice_count > 1 else ""
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} {section_title}{label_suffix}",
                    "help_text": f"Choose an option for {section_title} from {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, category),
                    "kind": "feat_optionalfeature",
                }
            )

    spell_source_field = _build_feat_spell_source_field(
        selection=selection,
        values=values,
    )
    if spell_source_field is not None:
        fields.append(spell_source_field)

    return fields


def _feat_optionalfeature_category(section_index: int) -> str:
    return f"optionalfeature_{section_index}"


def _feat_optionalfeature_sections(
    feat_entry: SystemsEntryRecord,
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    metadata = dict(feat_entry.metadata or {})
    sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(list(metadata.get("optionalfeature_progression") or []), start=1):
        if not isinstance(raw_section, dict):
            continue
        feature_types = {
            normalize_lookup(value)
            for value in list(raw_section.get("featureType") or [])
            if str(value or "").strip()
        }
        if not feature_types:
            continue
        count = _optionalfeature_progression_choice_count(raw_section.get("progression"))
        if count <= 0:
            continue
        options: list[dict[str, str]] = []
        seen_values: set[str] = set()
        for entry in sorted(
            list(optionalfeature_catalog.values()),
            key=lambda candidate: (normalize_lookup(candidate.title), str(candidate.slug or "").strip()),
        ):
            entry_feature_types = {
                normalize_lookup(value)
                for value in list(dict(entry.metadata or {}).get("feature_type") or [])
                if str(value or "").strip()
            }
            if not entry_feature_types or not (entry_feature_types & feature_types):
                continue
            value = str(entry.slug or "").strip()
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            options.append(_choice_option(entry.title, value))
        if not options:
            continue
        title = _clean_embedded_text(str(raw_section.get("name") or "").strip()) or "Optional Feature"
        sections.append(
            {
                "index": index,
                "title": title,
                "count": count,
                "options": options,
            }
        )
    return sections


def _optionalfeature_progression_choice_count(raw_progression: Any) -> int:
    if isinstance(raw_progression, (int, float)):
        return max(int(raw_progression), 0)
    if not isinstance(raw_progression, dict):
        return 0
    count = 0
    for raw_value in raw_progression.values():
        try:
            count = max(count, int(raw_value or 0))
        except (TypeError, ValueError):
            continue
    return count


def _item_type_code(entry: SystemsEntryRecord, *, _field=getattr) -> str:
    raw_value = str((_field(entry, "metadata") or {}).get("type") or "").strip()
    return raw_value.split("|", 1)[0].strip().upper()


def _tool_proficiency_options(
    item_catalog: dict[str, Any],
    *,
    artisan_only: bool = False,
) -> list[dict[str, str]]:
    field = lambda entry, name: catalog_field(item_catalog, entry, name)
    allowed_type_codes = {"AT"} if artisan_only else {"AT", "GS", "INS"}
    dynamic_titles = [
        field(entry, "title")
        for entry in catalog_rows(item_catalog)
        if _item_type_code(entry, _field=field) in allowed_type_codes and str(field(entry, "title") or "").strip()
    ]
    artisan_titles = {
        "Alchemist's Supplies", "Brewer's Supplies", "Calligrapher's Supplies",
        "Carpenter's Tools", "Cartographer's Tools", "Cobbler's Tools", "Cook's Utensils",
        "Glassblower's Tools", "Jeweler's Tools", "Leatherworker's Tools", "Mason's Tools",
        "Painter's Supplies", "Potter's Tools", "Smith's Tools", "Tinker's Tools",
        "Weaver's Tools", "Woodcarver's Tools",
    }
    fallback_titles = [
        title
        for title in COMMON_TOOL_PROFICIENCY_OPTIONS
        if not artisan_only
        or title in artisan_titles
    ]
    merged_titles = _dedupe_preserve_order(dynamic_titles + fallback_titles)
    return [_choice_option(title, title) for title in merged_titles]


def _weapon_proficiency_options(item_catalog: dict[str, Any]) -> list[dict[str, str]]:
    profile_titles = [
        str(dict(profile or {}).get("title") or "").strip()
        for profile in list(dict(catalog_aux(item_catalog, "phb_weapon_profiles") or {}).values())
    ]
    return [_choice_option(title, title) for title in _dedupe_preserve_order(profile_titles)]


def _resolve_builder_feat_selections(
    values: dict[str, str],
    feat_catalog: dict[str, Any],
    *, selected_species: SystemsEntryRecord | None = None,
) -> list[dict[str, Any]]:
    by_value = dict(feat_catalog.get("by_value") or {})
    selections: list[dict[str, Any]] = []
    for field_name in sorted(values.keys()):
        if not str(field_name).startswith("species_feat_"):
            continue
        feat_slug = str(values.get(field_name) or "").strip()
        feat_entry = by_value.get(feat_slug)
        if feat_entry is None and feat_slug and SYSTEMS_OPTION_PREFIX not in feat_slug and CAMPAIGN_PAGE_OPTION_PREFIX not in feat_slug:
            feat_entry = by_value.get(f"{SYSTEMS_OPTION_PREFIX}{feat_slug}")
        if feat_entry is None:
            continue
        authored = None
        if isinstance(selected_species, SystemsEntryRecord) and selected_species.entry_key:
            feat_rules = selected_species.metadata.get("feats")
            if (isinstance(feat_rules, list) and len(feat_rules) == 1
                    and isinstance(feat_rules[0], dict) and set(feat_rules[0]) == {"any"}
                    and type(feat_rules[0]["any"]) is int and feat_rules[0]["any"] == 1
                    and field_name == "species_feat_1"):
                authored = {"grant_rule_id": selected_species.entry_key, "choice_slot_id": "feat"}
        selections.append(
            {
                "instance_key": str(field_name),
                "native_acquisition": authored,
                "selection_value": feat_slug,
                "slug": _entry_option_slug(feat_entry) or feat_slug,
                "entry": feat_entry,
                "label": _entry_option_title(feat_entry) or feat_slug,
                "page_ref": _entry_page_ref(feat_entry),
                "campaign_option": _entry_campaign_option(feat_entry) or None,
            }
        )
    return selections


def _resolve_level_up_feat_selections(
    values: dict[str, str],
    feat_catalog: dict[str, Any],
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
) -> list[dict[str, Any]]:
    by_value = dict(feat_catalog.get("by_value") or {})
    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    selections: list[dict[str, Any]] = []
    for index in range(1, improvement_count + 1):
        if str(values.get(f"levelup_asi_mode_{index}") or "ability_scores").strip() != "feat":
            continue
        field_name = f"levelup_feat_{index}"
        feat_slug = str(values.get(field_name) or "").strip()
        feat_entry = by_value.get(feat_slug)
        if feat_entry is None and feat_slug and SYSTEMS_OPTION_PREFIX not in feat_slug and CAMPAIGN_PAGE_OPTION_PREFIX not in feat_slug:
            feat_entry = by_value.get(f"{SYSTEMS_OPTION_PREFIX}{feat_slug}")
        if feat_entry is None:
            continue
        selections.append(
            {
                "instance_key": field_name,
                "native_acquisition": _level_up_feat_acquisition(
                    class_progression, subclass_progression,
                    target_level=target_level, selection_index=index,
                ),
                "selection_value": feat_slug,
                "slug": _entry_option_slug(feat_entry) or feat_slug,
                "entry": feat_entry,
                "label": _entry_option_title(feat_entry) or feat_slug,
                "page_ref": _entry_page_ref(feat_entry),
                "campaign_option": _entry_campaign_option(feat_entry) or None,
            }
        )
    return selections


def _level_up_feat_acquisition(
    class_progression: list[dict[str, Any]], subclass_progression: list[dict[str, Any]],
    *, target_level: int, selection_index: int,
) -> dict[str, str] | None:
    """Bind the existing form witness to its actual attained ASI source rule.

    The ordinal retrieves the already-authored branch; it is never included in
    occurrence identity. Missing/duplicate source rules remain unsupported.
    """
    branches = [row.get("entry")
        for progression in (class_progression, subclass_progression)
        for group in progression if int(group.get("level") or 0) == target_level
        for row in list(group.get("feature_rows") or [])
        if normalize_lookup(row.get("label")) in ABILITY_SCORE_IMPROVEMENT_NAMES]
    if not 1 <= selection_index <= len(branches):
        return None
    rule = branches[selection_index - 1]
    if (not isinstance(rule, SystemsEntryRecord) or not rule.entry_key
            or sum(isinstance(entry, SystemsEntryRecord) and entry.entry_key == rule.entry_key
                   for entry in branches) != 1):
        return None
    return {"grant_rule_id": rule.entry_key, "choice_slot_id": "feat"}


def _feat_field_name(instance_key: str, category: str, index: int) -> str:
    return f"feat_{instance_key}_{category}_{index}"






def _feature_field_name(instance_key: str, category: str, index: int) -> str:
    return f"feature_{instance_key}_{category}_{index}"






def _build_feat_feature_entry(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
    fallback_title: str = "",
) -> dict[str, Any]:
    feat_entry = selection.get("entry") or selection.get("systems_entry")
    feat_slug = str(selection.get("slug") or selection.get("selection_value") or "").strip()
    feat_title = (
        str(selection.get("label") or selection.get("title") or "").strip()
        or (feat_entry.title if isinstance(feat_entry, SystemsEntryRecord) else "")
        or fallback_title
        or feat_slug
    )
    feature_entry: dict[str, Any] = {
        "kind": "feat",
        "entry": None,
        "name": feat_title,
        "title": feat_title,
        "label": feat_title,
        "slug": feat_slug,
        "source_kind": NATIVE_PROGRESSION_FEATURE_SOURCE_KIND,
        "systems_entry": feat_entry if isinstance(feat_entry, SystemsEntryRecord) else None,
        "page_ref": str(selection.get("page_ref") or "").strip(),
        "campaign_option": dict(selection.get("campaign_option") or {}) or None,
    }
    # This is a choice witness, not acquisition authority. The canonical
    # producer binds it to the authenticated acquisition and granting rule.
    instance_key = str(selection.get("instance_key") or "").strip()
    if instance_key:
        feature_entry["instance_key"] = instance_key
    if isinstance(selection.get("native_acquisition"), dict):
        feature_entry["native_acquisition"] = deepcopy(selection["native_acquisition"])
    spell_manager = _supported_feat_spell_manager_payload(selection=selection, values=values)
    if spell_manager:
        feature_entry["spell_manager"] = spell_manager
    source_id = str(selection.get("source_id") or "").strip()
    if source_id:
        feature_entry["source_id"] = source_id
    return feature_entry


def _build_level_one_equipment_catalog(
    equipment_groups: list[dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]] | None = None,
    selected_choices: dict[str, list[str]] | None = None,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected_campaign_item_specs: list[dict[str, Any]] = []
    if choice_sections and selected_choices:
        selected_campaign_item_specs = _build_selected_campaign_item_specs(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
        )
    return _build_level_one_equipment_catalog_from_specs(
        equipment_groups,
        selected_campaign_item_specs=selected_campaign_item_specs,
        item_catalog=item_catalog,
    )


















def _extract_feat_effect_keys(features: list[dict[str, Any]] | None) -> list[str]:
    results: list[str] = []
    for feature in list(features or []):
        category = normalize_lookup(str(feature.get("category") or "").strip())
        systems_ref = dict(feature.get("systems_ref") or {})
        entry_type = normalize_lookup(str(systems_ref.get("entry_type") or "").strip())
        if category != normalize_lookup("feat") and entry_type != normalize_lookup("feat"):
            continue
        results.extend(_effect_keys_for_feature(feature))
    return _dedupe_preserve_order(results)























































































def _build_equipment_choice_fields(equipment_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for group in equipment_groups:
        field_name = str(group.get("field_name") or "").strip()
        if not field_name:
            continue
        fields.append(
            {
                "name": field_name,
                "label": str(group.get("field_label") or "Equipment Choice"),
                "help_text": str(group.get("help_text") or "Choose your starting equipment."),
                "options": [
                    _choice_option(str(option.get("label") or ""), str(option.get("value") or ""))
                    for option in list(group.get("options") or [])
                    if str(option.get("value") or "").strip()
                ],
                "selected": str(group.get("selected") or "").strip(),
                "group_key": field_name,
                "kind": "equipment",
            }
        )
    return fields


def _campaign_option_payloads_from_selected_entries(entries: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in list(entries or []):
        campaign_option = _entry_campaign_option(entry)
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _campaign_option_payloads_from_feat_selections(
    feat_selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for selection in list(feat_selections or []):
        campaign_option = dict(selection.get("campaign_option") or {})
        if not campaign_option:
            campaign_option = _entry_campaign_option(selection.get("entry"))
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _campaign_option_payloads_from_feature_entries(
    feature_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            continue
        campaign_option = _entry_campaign_option(entry)
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _spell_feature_entry_identity(feature_entry: dict[str, Any]) -> tuple[str, str]:
    entry = feature_entry.get("entry") or feature_entry.get("systems_entry")
    choice_slot = str(feature_entry.get("instance_key") or "").strip()
    if isinstance(entry, SystemsEntryRecord):
        return ("systems", json.dumps(
            [entry.library_slug, entry.entry_type, entry.source_id, entry.entry_key, choice_slot],
            ensure_ascii=False, separators=(",", ":"),
        ))
    campaign_option = dict(feature_entry.get("campaign_option") or {})
    if campaign_option:
        return (
            "campaign",
            str(
                campaign_option.get("page_ref")
                or campaign_option.get("id")
                or feature_entry.get("page_ref")
                or feature_entry.get("label")
                or feature_entry.get("name")
                or ""
            ).strip(),
        )
    return (
        "label",
        str(feature_entry.get("page_ref") or feature_entry.get("label") or feature_entry.get("name") or "").strip(),
    )


def _dedupe_spell_feature_entries(feature_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for feature_entry in list(feature_entries or []):
        payload = dict(feature_entry or {})
        marker = _spell_feature_entry_identity(payload)
        if not marker[1] or marker in seen:
            continue
        seen.add(marker)
        deduped.append(payload)
    return deduped


def _spell_feature_entries_from_progressions(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []

    def append_entry(entry: SystemsEntryRecord | None) -> None:
        if not isinstance(entry, SystemsEntryRecord):
            return
        if normalize_lookup(entry.entry_type) not in {
            normalize_lookup("classfeature"),
            normalize_lookup("subclassfeature"),
            normalize_lookup("optionalfeature"),
        }:
            return
        feature_entries.append({"entry": entry})

    for progression in (class_progression, subclass_progression):
        for group in list(progression or []):
            if int(group.get("level") or 0) > target_level:
                continue
            for feature_row in list(group.get("feature_rows") or []):
                append_entry(feature_row.get("entry"))
    if selected_choices:
        for feature_entry in _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_class_options",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_subclass_options",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="class_option",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="subclass_option",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
    return _dedupe_spell_feature_entries(feature_entries)




















def _build_spell_options_for_class_level(
    class_name: str,
    level_key: str,
    spell_catalog: dict[str, Any],
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    try:
        spell_level = int(str(level_key or "0").strip())
    except ValueError:
        spell_level = 0
    effective_row_level = max(int(row_level or 0), spell_level if spell_level > 0 else 0)
    spell_list_class_name = _spell_list_class_name_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=effective_row_level,
    )
    field = lambda entry, name: catalog_field(spell_catalog, entry, name)
    titles: list[str] = []
    if selected_class is not None:
        titles.extend(
            field(entry, "title")
            for entry in catalog_rows(spell_catalog)
            if int((field(entry, "metadata") or {}).get("level") if (field(entry, "metadata") or {}).get("level") is not None else -1) == spell_level
            and _spell_entry_matches_class_list(
                entry,
                selected_class,
                class_list_name=spell_list_class_name,
                _field=field,
            )
        )
    if not titles:
        titles.extend(
            dict(dict(catalog_aux(spell_catalog, "phb_level_one_lists") or {}).get(spell_list_class_name or class_name) or {}).get(
                str(level_key)
            )
            or []
        )
    titles.extend(
        _expanded_spell_titles_for_level(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            spell_level=spell_level,
            feature_entries=feature_entries,
        )
    )
    return _build_spell_options_from_titles(titles, spell_catalog)


def _spell_entry_matches_class_list(
    spell_entry: SystemsEntryRecord,
    selected_class: SystemsEntryRecord,
    *,
    class_list_name: str = "",
    _field=getattr,
) -> bool:
    class_lists = dict((_field(spell_entry, "metadata") or {}).get("class_lists") or {})
    selected_source_id = str(selected_class.source_id or "").strip().upper()
    selected_title = normalize_lookup(class_list_name or selected_class.title)
    if selected_source_id:
        source_titles = [
            normalize_lookup(title)
            for title in list(class_lists.get(selected_source_id) or [])
            if str(title).strip()
        ]
        if selected_title and selected_title in source_titles:
            return True
    for titles in class_lists.values():
        normalized_titles = [normalize_lookup(title) for title in list(titles or []) if str(title).strip()]
        if selected_title and selected_title in normalized_titles:
            return True
    return False


def _build_spell_options_for_class_levels(
    class_name: str,
    level_keys: range | list[int],
    spell_catalog: dict[str, Any],
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for level_key in level_keys:
        for option in _build_spell_options_for_class_level(
            class_name,
            str(level_key),
            spell_catalog,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            row_level=row_level,
            feature_entries=feature_entries,
        ):
            value = str(option.get("value") or "").strip()
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            options.append(dict(option))
    return options


def _level_one_spell_selection_count(spell_rules: dict[str, Any], values: dict[str, str]) -> int:
    explicit_count = spell_rules.get("level_one_count")
    if explicit_count is not None:
        return max(int(explicit_count or 0), 0)
    ability_key = str(spell_rules.get("ability_key") or "").strip()
    if ability_key and ability_key in ABILITY_KEYS:
        modifier = _ability_modifier(_coerce_ability_scores(values).get(ability_key, DEFAULT_ABILITY_SCORE))
        return max(1 + modifier, 1)
    return 0


def _normalize_preview_values(values: dict[str, str]) -> dict[str, str]:
    normalized = {key: str(value) for key, value in dict(values or {}).items()}
    normalized.setdefault("name", "")
    normalized.setdefault("character_slug", "")
    normalized.setdefault("alignment", "")
    normalized.setdefault("experience_model", DEFAULT_EXPERIENCE_MODEL)
    for ability_key in ABILITY_KEYS:
        normalized.setdefault(ability_key, str(DEFAULT_ABILITY_SCORE))
    return normalized


def _build_level_one_preview(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    equipment_groups: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    feat_catalog: dict[str, Any],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    acquisition_context: AcquisitionContext | None = None,
    systems_service: Any | None = None,
) -> dict[str, Any]:
    feat_selections = _resolve_builder_feat_selections(values, feat_catalog, selected_species=selected_species)
    feature_choice_selections = _progression_feature_choice_selections(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=1,
        instance_prefix="level1_feature",
    )
    ability_scores = _coerce_ability_scores(values)
    proficiency_bonus = 2
    class_name = selected_class.title if selected_class is not None else ""
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values, strict=False)
    feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=False,
    )
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        campaign_option_payloads=selected_campaign_option_payloads,
        item_catalog=item_catalog,
        strict=False,
    )
    skills = _build_skills_payload(
        ability_scores,
        proficiencies["skills"],
        proficiency_bonus,
        feat_selections=feat_selections,
        feature_selections=feature_choice_selections,
        selected_choices=selected_choices,
        strict=False,
    )
    equipment_catalog = _build_level_one_equipment_catalog(
        equipment_groups,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        item_catalog=item_catalog,
    )
    spellcasting = (
        _build_level_one_spellcasting(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feat_selections=feat_selections,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            spell_catalog=spell_catalog,
            feature_entries=feature_entries,
            campaign_option_payloads=selected_campaign_option_payloads,
            canonical_activation=acquisition_context is not None,
            acquisition_context=acquisition_context,
        )
        if selected_class is not None
        else {"spells": []}
    )
    feature_payloads, resource_templates = _build_feature_payloads(
        feature_entries,
        ability_scores=ability_scores,
        current_level=1,
        acquisition_context=acquisition_context,
        acquisition_class_row_id=(
            ensure_profile_class_rows({"classes": [{
                "systems_ref": _systems_ref_from_entry(selected_class), "level": 1,
            }]})[0]["row_id"] if selected_class is not None else ""
        ),
    )
    stats = (
        _build_level_one_stats(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            selected_species=selected_species,
            ability_scores=ability_scores,
            skills=skills,
            proficiency_bonus=proficiency_bonus,
            feat_selections=feat_selections,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            current_level=1,
            equipment_catalog=equipment_catalog,
            features=feature_payloads,
            item_catalog=item_catalog,
            campaign_option_payloads=selected_campaign_option_payloads,
        )
        if selected_class is not None and selected_species is not None
        else {}
    )
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
        features=feature_payloads,
    )
    feature_names = [
        str(feature.get("name") or feature.get("label") or "").strip()
        for feature in feature_payloads
        if str(feature.get("name") or feature.get("label") or "").strip()
    ]
    save_proficiencies = _dedupe_preserve_order(
        _class_save_proficiencies(selected_class)
        + _extract_feat_saving_throw_proficiencies(feat_selections, selected_choices)
    )
    proposed_spells: list[str] = []
    if selected_class is not None and selected_species is not None and selected_background is not None:
        prospective_profile = _build_level_one_profile(
            name=str(values.get("name") or ""), selected_class=selected_class,
            selected_subclass=selected_subclass, selected_species=selected_species,
            selected_background=selected_background, values=values,
        )
        owner_row = ensure_profile_class_rows(prospective_profile)[0]["row_id"]
        proposed_features = deepcopy(feature_payloads)
        for feature in proposed_features:
            if feature.get("category") in {"class_feature", "feat"}:
                feature["class_row_id"] = owner_row
        prospective = CharacterDefinition(
            campaign_slug=acquisition_context.campaign_slug if acquisition_context is not None else "",
            character_slug=slugify(str(values.get("character_slug") or values.get("name") or "")),
            name=str(values.get("name") or ""),
            status="active", profile=prospective_profile, stats=stats, skills=skills,
            proficiencies=proficiencies, attacks=attacks, features=proposed_features,
            spellcasting=spellcasting, equipment_catalog=equipment_catalog,
            reference_notes={}, resource_templates=resource_templates, source={},
        )
        if prospective.name.strip() and prospective.character_slug:
            proposed_spells = _proposed_native_spell_summaries(
                prospective, systems_service=systems_service, spell_catalog=spell_catalog,
                acquisition_context=acquisition_context,
            )
        else:
            proposed_spells = ["Feature grants pending a character name."]
    else:
        missing = [label for label, entry in (("class", selected_class), ("species", selected_species),
                                             ("background", selected_background)) if entry is None]
        proposed_spells = [f"Feature grants pending {', '.join(missing)} selections."]
    return {
        "class_level_text": f"{class_name} 1" if class_name else "Level 1",
        "max_hp": int(stats.get("max_hp") or 0),
        "speed": str(stats.get("speed") or _extract_speed_label(selected_species)),
        "size": _extract_size_label(selected_species),
        "carrying_capacity": _format_weight_value(stats.get("carrying_capacity")),
        "push_drag_lift": _format_weight_value(stats.get("push_drag_lift")),
        "proficiency_bonus": proficiency_bonus,
        "saving_throws": [_humanize_saving_throw(code) for code in save_proficiencies],
        "languages": list(proficiencies["languages"]),
        "features": feature_names,
        "resources": [
            _summarize_preview_resource(template)
            for template in resource_templates
            if _summarize_preview_resource(template)
        ],
        "equipment": [
            _describe_equipment_spec(item)
            for item in equipment_catalog
            if not bool(item.get("is_currency_only")) and _describe_equipment_spec(item)
        ],
        "attacks": [
            summary
            for attack in attacks
            if (summary := _summarize_preview_attack(attack))
        ],
        "starting_currency": _format_currency_seed(_collect_currency_seed_from_equipment(equipment_catalog)),
        "spells": [_summarize_preview_spell(spell) for spell in list(spellcasting.get("spells") or [])] + proposed_spells,
        "background": selected_background.title if selected_background is not None else "",
        "subclass": selected_subclass.title if selected_subclass is not None else "",
    }


def _proposed_native_spell_summaries(
    definition: CharacterDefinition, *, systems_service: Any, spell_catalog: dict[str, Any],
    acquisition_context: AcquisitionContext | None, prior_definition: CharacterDefinition | None = None,
    prior_custody: tuple[Any, ...] = (),
) -> list[str]:
    """Display draft source names; never pass this view to effective mechanics."""
    from .character_spell_grants import build_native_grant_draft, validate_native_grant_model

    from .committed_publication import active
    if not source_active(systems_service):
        return ["Automatic feature spell grants are unavailable here."]
    if acquisition_context is None or systems_service is None:
        return ["Feature grants pending an authenticated acquisition intent."]
    if prior_definition is not None and not has_native_grants(prior_definition):
        return ["Proposed feature grants require a native spell-grant migration review."]
    try:
        draft = build_native_grant_draft(
            definition, systems_service, acquisition_context=acquisition_context,
            prior_definition=prior_definition, prior_custody=prior_custody,
        )
        previous_ids = ({row["id"] for row in validate_native_grant_model(prior_definition)["occurrences"]}
                        if prior_definition is not None else set())
        summaries = []
        for occurrence in draft.occurrences:
            if occurrence.get("status") != "DRAFT" or occurrence["id"] in previous_ids:
                continue
            entry = _resolve_spell_entry(occurrence["spell_ref"]["entry_key"], spell_catalog)
            if entry is not None and publication_identity(_systems_ref_from_entry(entry)) == publication_identity(occurrence["spell_ref"]):
                summaries.append(f"{entry.title} (Proposed feature grant)")
            else:
                summaries.append("Proposed feature grant pending its exact spell catalog entry.")
        if draft.diagnostics:
            summaries.append("Some proposed feature grants need source or acquisition review.")
        return _dedupe_preserve_order(summaries)
    except GrantContractError as exc:
        return [f"Feature grants pending review: {exc}"]


def _parse_ability_scores(values: dict[str, str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for ability_key in ABILITY_KEYS:
        raw_value = str(values.get(ability_key) or "").strip()
        if not raw_value:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} score is required.")
        try:
            score = int(raw_value)
        except ValueError as exc:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} must be a whole number.") from exc
        if score < 1 or score > 30:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} must be between 1 and 30.")
        scores[ability_key] = score
    return scores


def _coerce_ability_scores(values: dict[str, str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for ability_key in ABILITY_KEYS:
        try:
            scores[ability_key] = int(str(values.get(ability_key) or DEFAULT_ABILITY_SCORE).strip() or DEFAULT_ABILITY_SCORE)
        except ValueError:
            scores[ability_key] = DEFAULT_ABILITY_SCORE
    return scores


def _resolve_builder_choices(
    choice_sections: list[dict[str, Any]],
    values: dict[str, str],
    *,
    strict: bool = True,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    selected_choices: dict[str, list[str]] = {}
    paired_field_metadata: dict[str, dict[str, str]] = {}
    for section in choice_sections:
        grouped_values: dict[str, list[str]] = {}
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "")
            group_key = str(field.get("group_key") or field_name)
            is_required = bool(field.get("required", True))
            paired_field_name = str(field.get("paired_field_name") or "").strip()
            if paired_field_name:
                paired_field_metadata[field_name] = {
                    "label": str(field.get("label") or field_name).strip() or field_name,
                    "paired_field_name": paired_field_name,
                    "paired_label": str(field.get("paired_field_label") or paired_field_name).strip() or paired_field_name,
                }
            raw_value = str(values.get(field_name) or "").strip()
            allowed_values = {str(option.get("value") or "").strip() for option in list(field.get("options") or [])}
            selected_value = _normalize_selected_choice_value(raw_value, allowed_values)
            if not raw_value:
                if strict and is_required:
                    raise CharacterBuildError(f"{field.get('label') or 'A required choice'} is required.")
                continue
            if selected_value not in allowed_values:
                if strict:
                    raise CharacterBuildError(f"{field.get('label') or 'A choice'} is not valid for the current selection.")
                continue
            if selected_value:
                grouped_values.setdefault(group_key, []).append(selected_value)
        for group_key, group_values in grouped_values.items():
            if strict and len(group_values) != len(set(group_values)):
                raise CharacterBuildError("Choose distinct options when a choice group grants more than one selection.")
            selected_choices[group_key] = group_values
    if strict:
        _validate_paired_choice_fields(values, paired_field_metadata)

    fixed_proficiencies = {
        "skills": [],
        "languages": [],
        "tools": [],
    }
    return fixed_proficiencies, selected_choices


def _validate_paired_choice_fields(
    values: dict[str, str],
    paired_field_metadata: dict[str, dict[str, str]],
) -> None:
    seen_pairs: set[tuple[str, str]] = set()
    for field_name, metadata in paired_field_metadata.items():
        paired_field_name = str(metadata.get("paired_field_name") or "").strip()
        if not paired_field_name:
            continue
        pair_key = tuple(sorted((field_name, paired_field_name)))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        left_value = str(values.get(field_name) or "").strip()
        right_value = str(values.get(paired_field_name) or "").strip()
        if bool(left_value) == bool(right_value):
            continue
        left_label = str(metadata.get("label") or field_name).strip() or field_name
        right_label = str(metadata.get("paired_label") or paired_field_name).strip() or paired_field_name
        raise CharacterBuildError(f"{left_label} and {right_label} must both be chosen together.")














def _apply_tool_expertise_level(
    tool_expertise: list[str],
    *,
    available_tool_proficiencies: list[str],
    tool_name: Any,
    feature_title: str,
    strict: bool,
) -> None:
    resolved_tool_name = _feature_expertise_selected_tool_name(tool_name) or _clean_embedded_text(str(tool_name or "")).strip()
    normalized_tool_name = normalize_lookup(resolved_tool_name)
    if not normalized_tool_name:
        if strict:
            raise CharacterBuildError(f"Choose a valid expertise proficiency for {feature_title}.")
        return
    available_lookup = {
        normalize_lookup(tool): str(tool).strip()
        for tool in list(available_tool_proficiencies or [])
        if str(tool).strip()
    }
    proficient_tool_name = available_lookup.get(normalized_tool_name)
    if not proficient_tool_name:
        if strict:
            raise CharacterBuildError(f"{feature_title} requires choosing a tool that already has proficiency.")
        return
    existing_lookup = {
        normalize_lookup(tool): str(tool).strip()
        for tool in list(tool_expertise or [])
        if str(tool).strip()
    }
    if normalized_tool_name in existing_lookup:
        if strict:
            raise CharacterBuildError(
                f"{feature_title} requires choosing a tool that does not already have expertise."
            )
        return
    tool_expertise.append(proficient_tool_name)


def _apply_feature_expertise_to_tool_proficiencies(
    tool_expertise: list[str],
    *,
    available_tool_proficiencies: list[str],
    feature_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]] | None = None,
    strict: bool = False,
) -> list[str]:
    available_tools = _dedupe_preserve_order(list(available_tool_proficiencies or []))
    available_lookup = {
        normalize_lookup(tool): str(tool).strip()
        for tool in available_tools
        if str(tool).strip()
    }
    updated_tools = _dedupe_preserve_order(
        [
            available_lookup.get(normalize_lookup(tool), str(tool).strip())
            for tool in list(tool_expertise or [])
            if str(tool).strip()
        ]
    )
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
            for expertise_name, value in dict(block).items():
                if expertise_name == "allProficientTools":
                    from .character_feature_proficiency_grants import automatic
                    if automatic(feature_entry) and selection.get("automatic_tools", True):
                        automatic_tools = selection.get("automatic_tool_proficiencies", available_tools)
                        updated_tools = _dedupe_preserve_order(updated_tools + [tool for tool in automatic_tools
                            if normalize_lookup(tool) in available_lookup])
                    continue
                if expertise_name == "anyProficientSkill" or value is not True:
                    continue
                if normalize_lookup(expertise_name) in SKILL_LABELS:
                    continue
                _apply_tool_expertise_level(
                    updated_tools,
                    available_tool_proficiencies=available_tools,
                    tool_name=expertise_name,
                    feature_title=feature_title,
                    strict=strict,
                )
        any_proficient_skill_count = sum(int(block.get("anyProficientSkill") or 0) for block in expertise_blocks)
        if any_proficient_skill_count <= 0:
            continue
        if not instance_key:
            if strict:
                raise CharacterBuildError(f"{feature_title} is missing the expertise choice metadata needed to save.")
            continue
        selected_expertise_values = _feature_selected_values(choice_map, instance_key, "expertise")
        for selected_value in selected_expertise_values[:any_proficient_skill_count]:
            if not _feature_expertise_selected_tool_name(selected_value):
                continue
            _apply_tool_expertise_level(
                updated_tools,
                available_tool_proficiencies=available_tools,
                tool_name=selected_value,
                feature_title=feature_title,
                strict=strict,
            )
    return _dedupe_preserve_order(updated_tools)




def _extract_feat_language_proficiencies(
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
        for block in list(metadata.get("language_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if int(block.get("anyStandard") or block.get("any") or 0) > 0:
                results.extend(_feat_selected_values(selected_choices, instance_key, "languages"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="languages"))
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("language:"):
                results.append(str(value).split(":", 1)[1])
    return _dedupe_preserve_order(results)


def _extract_feat_tool_proficiencies(
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
        for block in list(metadata.get("tool_proficiencies") or []):
            if isinstance(block, str):
                cleaned = _clean_embedded_text(block)
                if cleaned:
                    results.append(cleaned)
                continue
            if not isinstance(block, dict):
                continue
            if int(block.get("any") or block.get("anyTool") or block.get("anyArtisansTool") or 0) > 0:
                results.extend(_feat_selected_values(selected_choices, instance_key, "tools"))
                continue
            for key, value in block.items():
                if value is True:
                    cleaned = _clean_embedded_text(key)
                    if cleaned:
                        results.append(cleaned)
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("tool:"):
                results.append(str(value).split(":", 1)[1])
    return _dedupe_preserve_order(results)


def _extract_feat_armor_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    del selected_choices
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("armor_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="armor"))
    return _dedupe_preserve_order(results)


def _extract_feat_weapon_proficiencies(
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
        for block in list(metadata.get("weapon_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block:
                results.extend(_feat_selected_values(selected_choices, instance_key, "weapons"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="weapons"))
    return _dedupe_preserve_order(results)














def _build_level_one_proficiencies(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    fixed_proficiencies: dict[str, list[str]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    feat_selections: list[dict[str, Any]],
    campaign_option_payloads: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    strict: bool = True,
) -> dict[str, list[str]]:
    del fixed_proficiencies
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(
        _selected_campaign_option_payloads(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            extra_option_payloads=campaign_option_payloads,
        )
    )
    armor = _dedupe_preserve_order(
        _extract_class_armor_proficiencies(selected_class)
        + _extract_feat_armor_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("armor") or [])
    )
    weapons = _dedupe_preserve_order(
        _extract_class_weapon_proficiencies(selected_class)
        + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("weapons") or [])
    )
    tools = _dedupe_preserve_order(
        _extract_class_tool_proficiencies(selected_class)
        + _extract_fixed_tool_proficiencies(selected_species)
        + _extract_fixed_tool_proficiencies(selected_background)
        + _background_instrument_payload(
            selected_background, {f"background_instrument_{index}": value
                                  for index, value in enumerate(selected_choices.get("background_instruments", []), start=1)},
            catalog_snapshot(item_catalog), strict=False,
        )[1]
        + _extract_feat_tool_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("tools") or [])
    )
    from .character_language_choices import resolve_background_languages
    species_languages = _extract_fixed_languages(selected_species) + selected_choices.get("species_languages", [])
    try:
        background_languages = resolve_background_languages(selected_background,
            selected_choices.get("background_languages", []), species_languages, strict=strict)
    except ValueError as exc:
        raise CharacterBuildError(str(exc)) from exc
    languages = _dedupe_preserve_order(
        _extract_fixed_languages(selected_species)
        + _extract_fixed_languages(selected_background)
        + selected_choices.get("species_languages", [])
        + background_languages
        + _extract_feat_language_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("languages") or [])
    )
    skills = _dedupe_preserve_order(
        _extract_fixed_skills(selected_species)
        + _extract_fixed_skills(selected_background)
        + selected_choices.get("class_skills", [])
        + selected_choices.get("species_skills", [])
        + _extract_feat_skill_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("skills") or [])
    )
    return {
        "armor": armor,
        "weapons": weapons,
        "tools": tools,
        "languages": languages,
        "skills": skills,
    }


















def _collect_level_one_feature_entries(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    feat_selections: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    del selected_class
    feature_entries: list[dict[str, Any]] = []
    selected_values = _values_from_selected_choices(choice_sections, selected_choices)

    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=class_progression,
            target_level=1,
            selected_choices=selected_choices,
            group_key="class_option",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=1,
            selected_choices=selected_choices,
            group_key="subclass_option",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )

    if selected_species is not None:
        feature_entries.extend(_extract_species_feature_entries(selected_species))
        species_page_ref = _entry_page_ref(selected_species)
        if species_page_ref:
            feature_entries.append(
                {
                    "kind": "species_trait",
                    "label": selected_species.title,
                    "description_markdown": str(
                        (_entry_campaign_option(selected_species) or {}).get("description_markdown") or ""
                    ).strip(),
                    "page_ref": species_page_ref,
                    "campaign_option": _entry_campaign_option(selected_species) or None,
                }
            )
    if selected_background is not None:
        feature_entries.extend(_extract_background_feature_entries(selected_background))
        background_page_ref = _entry_page_ref(selected_background)
        if background_page_ref:
            feature_entries.append(
                {
                    "kind": "background_feature",
                    "label": selected_background.title,
                    "description_markdown": str(
                        (_entry_campaign_option(selected_background) or {}).get("description_markdown") or ""
                    ).strip(),
                    "page_ref": background_page_ref,
                    "campaign_option": _entry_campaign_option(selected_background) or None,
                }
            )

    for selection in feat_selections:
        feat_entry = selection.get("entry")
        feat_slug = str(selection.get("slug") or selection.get("selection_value") or "").strip()
        feat_title = (
            str(selection.get("label") or "").strip()
            or (
                feat_entry.title
                if isinstance(feat_entry, SystemsEntryRecord)
                else _resolve_choice_label(choice_sections, "species_feats", feat_slug) or feat_slug
            )
        )
        feature_entries.append(
            _build_feat_feature_entry(
                selection=selection,
                values=selected_values,
                fallback_title=feat_title,
            )
        )

    feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )

    feature_entries.extend(
        _collect_selected_campaign_feature_entries(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
        )
    )

    return feature_entries


def _collect_feat_optionalfeature_entries(
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
            section_index = int(section.get("index") or 0)
            if section_index <= 0:
                continue
            category = _feat_optionalfeature_category(section_index)
            for selected_value in _feat_selected_values(selected_choices, instance_key, category):
                selected_entry = optionalfeature_catalog.get(str(selected_value or "").strip())
                if not isinstance(selected_entry, SystemsEntryRecord):
                    continue
                feature_entries.append(
                    {
                        "kind": "optionalfeature",
                        "entry": selected_entry,
                        "name": selected_entry.title,
                        "label": selected_entry.title,
                        "slug": str(selected_entry.slug or "").strip(),
                    }
                )
    return feature_entries


def _collect_progression_feature_entries_for_level(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_class_options",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_subclass_options",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    return feature_entries


def _collect_progression_feature_entries(
    *,
    progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]],
    group_key: str,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> list[dict[str, Any]]:
    from .character_armor_models import model_member_allowed
    feature_entries: list[dict[str, Any]] = []
    selected_values = list(selected_choices.get(group_key) or [])
    if not selected_values:
        selected_value_lookup: dict[str, list[str]] = {}
        for key, values in selected_choices.items():
            clean_key = str(key or "").strip()
            if clean_key == group_key or clean_key.startswith(f"{group_key}_"):
                selected_value_lookup[clean_key] = list(values or [])
        for key in sorted(selected_value_lookup):
            selected_values.extend(selected_value_lookup[key])
    selected_index = 0
    for group in progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = str(feature_row.get("label") or "").strip()
            normalized_label = normalize_lookup(label)
            if "choose subclass feature" in normalized_label:
                continue
            if normalized_label in ABILITY_SCORE_IMPROVEMENT_NAMES:
                continue
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if option_groups:
                for option_group in option_groups:
                    selected_slug = selected_values[selected_index] if selected_index < len(selected_values) else ""
                    selected_index += 1
                    selected_option = next(
                        (
                            option
                            for option in list(option_group.get("options") or [])
                            if str(option.get("slug") or "").strip() == selected_slug
                        ),
                        None,
                    )
                    if selected_option is None:
                        continue
                    selected_entry = selected_option.get("entry")
                    if not isinstance(selected_entry, SystemsEntryRecord):
                        selected_entry = dict(optionalfeature_catalog or {}).get(
                            str(selected_option.get("slug") or "").strip()
                        )
                    if not model_member_allowed(selected_entry):
                        continue
                    feature_entries.append(
                        {
                            "kind": "optionalfeature",
                            "entry": selected_entry if isinstance(selected_entry, SystemsEntryRecord) else None,
                            "name": str(selected_option.get("label") or "").strip(),
                            "label": str(selected_option.get("label") or "").strip(),
                            "slug": str(selected_option.get("slug") or "").strip(),
                        }
                    )
                if not feature_row.get("has_bundled_grants"):
                    continue
            if feature_row.get("deterministic_grant") is False:
                continue
            entry = feature_row.get("entry")
            if isinstance(entry, SystemsEntryRecord):
                if not model_member_allowed(entry):
                    # Only the independently authenticated attained collector
                    # may append the selected model's mechanical members.
                    continue
                feature_entries.append(
                    {
                        "kind": "systems",
                        "entry": entry,
                        "name": entry.title,
                        "label": entry.title,
                        **({"native_acquisition": {
                            "grant_rule_id": entry.entry_key,
                            "choice_slot_id": entry.entry_key,
                        }} if entry.entry_type in {"classfeature", "subclassfeature"} else {}),
                    }
                )
    return feature_entries


def _build_level_one_profile(
    *,
    name: str,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord,
    selected_background: SystemsEntryRecord,
    values: dict[str, str],
) -> dict[str, Any]:
    species_page_ref = _entry_page_ref(selected_species)
    background_page_ref = _entry_page_ref(selected_background)
    class_payload = {
        "class_name": selected_class.title,
        "subclass_name": selected_subclass.title if selected_subclass is not None else "",
        "level": 1,
        "systems_ref": _systems_ref_from_entry(selected_class),
    }
    if selected_subclass is not None:
        class_payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
    return sync_profile_class_summary(
        {
            "sheet_name": name,
            "display_name": name,
            "class_level_text": f"{selected_class.title} 1",
            "classes": [class_payload],
            "class_ref": _systems_ref_from_entry(selected_class),
            "subclass_ref": _systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None,
            "species": selected_species.title,
            "species_ref": None if species_page_ref else _systems_ref_from_entry(selected_species),
            "species_page_ref": species_page_ref or None,
            "background": selected_background.title,
            "background_ref": None if background_page_ref else _systems_ref_from_entry(selected_background),
            "background_page_ref": background_page_ref or None,
            "alignment": str(values.get("alignment") or "").strip(),
            "experience_model": str(values.get("experience_model") or DEFAULT_EXPERIENCE_MODEL).strip(),
            "size": _extract_size_label(selected_species),
            "biography_markdown": "",
            "personality_markdown": "",
        }
    )




def _parse_level_up_hit_point_gain(values: dict[str, str]) -> int:
    raw_value = str(values.get("hp_gain") or "").strip()
    if not raw_value:
        raise CharacterBuildError("Hit point gain is required to level up this character.")
    try:
        hp_gain = int(raw_value)
    except ValueError as exc:
        raise CharacterBuildError("Hit point gain must be a whole number.") from exc
    if hp_gain < 1:
        raise CharacterBuildError("Hit point gain must be at least 1.")
    return hp_gain




def _build_leveled_profile(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
) -> dict[str, Any]:
    profile = dict(current_definition.profile or {})
    classes = list(profile.get("classes") or [])
    class_payload = dict(classes[0] or {}) if classes else {}
    class_payload["class_name"] = selected_class.title
    class_payload["level"] = target_level
    class_payload["systems_ref"] = _systems_ref_from_entry(selected_class)
    class_payload["subclass_name"] = selected_subclass.title if selected_subclass is not None else ""
    if selected_subclass is not None:
        class_payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
    else:
        class_payload.pop("subclass_ref", None)
    profile["classes"] = [class_payload]
    profile["class_ref"] = _systems_ref_from_entry(selected_class)
    profile["subclass_ref"] = _systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None
    return sync_profile_class_summary(profile)


def _build_leveled_source(
    source_payload: dict[str, Any],
    target_level: int,
    *,
    current_level: int | None = None,
    current_definition: CharacterDefinition | None = None,
    hp_gain: int | None = None,
    max_hp_delta: int | None = None,
    action: str | None = None,
    class_row_id: str | None = None,
    class_ref: dict[str, Any] | None = None,
    subclass_ref: dict[str, Any] | None = None,
    row_from_level: int | None = None,
    row_to_level: int | None = None,
    preserve_import_provenance: bool = False,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    if current_definition is not None:
        source = _seed_source_hp_baseline_from_definition(source, current_definition)
    source_type = str(source.get("source_type") or "").strip()
    if source_type in IMPORTED_CHARACTER_SOURCE_TYPES:
        if not preserve_import_provenance:
            source["imported_at"] = isoformat(utcnow())
            source["parse_warnings"] = list(source.get("parse_warnings") or [])
        source = _with_native_progression_event(
            source,
            kind="level_up",
            previous_level=current_level,
            target_level=target_level,
            hp_gain=hp_gain,
            max_hp_delta=max_hp_delta,
            action=action,
            class_row_id=class_row_id,
            class_ref=class_ref,
            subclass_ref=subclass_ref,
            row_from_level=row_from_level,
            row_to_level=row_to_level,
        )
        return source
    if not preserve_import_provenance:
        source.update(
            {
                "source_path": f"builder://native-level-{target_level}",
                "source_type": "native_character_builder",
                "imported_from": f"In-app Native Level {target_level} Builder",
                "imported_at": isoformat(utcnow()),
                "parse_warnings": [],
            }
        )
    return _with_native_progression_event(
        source,
        kind="level_up",
        previous_level=current_level,
        target_level=target_level,
        hp_gain=hp_gain,
        max_hp_delta=max_hp_delta,
        action=action,
        class_row_id=class_row_id,
        class_ref=class_ref,
        subclass_ref=subclass_ref,
        row_from_level=row_from_level,
        row_to_level=row_to_level,
    )


def _build_leveled_import_metadata(
    *,
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata | None,
    target_level: int,
) -> CharacterImportMetadata:
    source_type = _character_source_type(current_definition)
    if source_type in IMPORTED_CHARACTER_SOURCE_TYPES:
        existing_import = current_import_metadata
        return CharacterImportMetadata(
            campaign_slug=campaign_slug,
            character_slug=current_definition.character_slug,
            source_path=str(
                (existing_import.source_path if existing_import is not None else "")
                or (current_definition.source or {}).get("source_path")
                or f"managed://{campaign_slug}/{current_definition.character_slug}"
            ),
            imported_at_utc=isoformat(utcnow()),
            parser_version=CHARACTER_BUILDER_VERSION,
            import_status="managed",
            warnings=list(existing_import.warnings if existing_import is not None else []),
        )
    return CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=f"builder://native-level-{target_level}",
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="clean",
        warnings=[],
    )


def _prospective_native_level_up_abilities(
    definition: CharacterDefinition,
    *,
    base_ability_scores: dict[str, int],
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    selected_feat_features: list[dict[str, Any]],
    features: list[dict[str, Any]],
    item_catalog: dict[str, Any],
) -> tuple[dict[str, int], dict[str, Any]]:
    """Project validated ability choices through the ordinary durable layers."""
    stats = deepcopy(definition.stats)
    equipment = _normalize_equipment_payloads(list(definition.equipment_catalog or []), item_catalog=item_catalog)
    item_effects = _character_builder_derivation._active_item_effect_entries_with_legacy_spell_review(
        equipment, item_catalog=item_catalog,
    )
    prior_features = list(definition.features or [])
    prior_bonuses = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ABILITY_KEYS},
        feat_selections=_campaign_option_feat_selections_from_features(prior_features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(prior_features), strict=False,
    )
    prior_minimums = _apply_item_effect_ability_score_minimums(
        {**dict.fromkeys(ABILITY_KEYS, 0), **_structured_ability_score_minimums(prior_features)},
        item_effect_entries=item_effects,
    )
    _, prior_records = resolve_inputs(stats, bonuses=prior_bonuses, minimums=prior_minimums)
    write_inputs(stats, prior_records)
    prior_scores = advancement_scores(stats)
    campaign_bonus = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ABILITY_KEYS},
        feat_selections=_campaign_option_feat_selections_from_features(selected_feat_features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(selected_feat_features), strict=False,
    )
    fixed_bonus = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ABILITY_KEYS}, feat_selections=feat_selections,
        selected_choices=selected_choices, strict=False,
    )
    advance_inputs(
        stats, {key: base_ability_scores[key] - prior_scores[key] for key in ABILITY_KEYS},
        fixed_bonuses={key: fixed_bonus[key] - campaign_bonus[key] for key in ABILITY_KEYS},
    )
    bonuses = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ABILITY_KEYS},
        feat_selections=_campaign_option_feat_selections_from_features(features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(features), strict=False,
    )
    minimums = _apply_item_effect_ability_score_minimums(
        {**dict.fromkeys(ABILITY_KEYS, 0), **_structured_ability_score_minimums(features)},
        item_effect_entries=item_effects,
    )
    scores, records = resolve_inputs(stats, bonuses=bonuses, minimums=minimums)
    scores = apply_recoverable_ability_score_penalties(
        scores, normalize_recoverable_penalties(stats.get("recoverable_penalties")),
    )
    return scores, {"version": 1, "scores": records}


def _prospective_native_level_up_numbers(
    *, definition: CharacterDefinition, profile: dict[str, Any],
    selected_class: SystemsEntryRecord, selected_subclass: SystemsEntryRecord | None,
    ability_scores: dict[str, int], skills: list[dict[str, Any]],
    features: list[dict[str, Any]], feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]], hp_gain: int, total_character_level: int,
    item_catalog: dict[str, Any], selected_campaign_option_payloads: list[dict[str, Any]],
    weapon_proficiencies: list[str], attack_choices: dict[str, list[str]],
    preview_only: bool = False,
    recorded_advancement_values: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Shared, side-effect-free prospective sheet math for preview and save."""
    proficiency_bonus = _proficiency_bonus_for_level(total_character_level)
    stats = _build_leveled_stats(
        current_definition=definition, selected_class=selected_class, selected_subclass=selected_subclass,
        ability_scores=ability_scores, skills=skills, proficiency_bonus=proficiency_bonus,
        hp_gain=hp_gain, feat_selections=feat_selections, selected_choices=selected_choices,
        current_level=total_character_level, equipment_catalog=list(definition.equipment_catalog or []),
        features=features, item_catalog=item_catalog,
        selected_campaign_option_payloads=selected_campaign_option_payloads, resulting_profile=profile,
    )
    from .character_hp_recipe import next_level_maximum, recorded_level_maximum
    from .character_reconstruction_authority import advanced_hp_recipe
    if dict(definition.source.get("native_progression") or {}).get("hp_recipe") is not None:
        from .character_hit_dice import _hit_die_faces_for_class_row
        try:
            recipe = advanced_hp_recipe(definition, features, feat_selections)
            faces = _hit_die_faces_for_class_row({
                "systems_ref": _systems_ref_from_entry(selected_class), "metadata": selected_class.metadata})
            history = dict(definition.source.get("native_progression") or {}).get("history", [])
            if recorded_advancement_values is not None:
                from .character_recorded_advancement import parse_recorded
                parse_recorded(recorded_advancement_values, allowed=True)
                stats["max_hp"], _recipe = recorded_level_maximum(recipe, history,
                    level=total_character_level, constitution=ability_scores["con"],
                    faces=faces, whole_hp_gain=hp_gain)
            else:
                stats["max_hp"] = next_level_maximum(recipe, history,
                    level=total_character_level, constitution=ability_scores["con"],
                    faces=faces, physical_hp_gain=hp_gain)
        except ValueError as exc:
            if not preview_only:
                raise CharacterBuildError(str(exc)) from exc
            # An empty/invalid physical input has no prospective maximum.
            # Keep the form editable without presenting an invented number.
            stats["max_hp"] = None
    elif recorded_advancement_values is not None:
        if not preview_only:
            raise CharacterBuildError("Recording a whole HP gain needs the reconstructed retained recipe.")
        stats["max_hp"] = None
    attacks = _build_level_one_attacks(
        equipment_catalog=list(definition.equipment_catalog or []), item_catalog=item_catalog,
        ability_scores=ability_scores, proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=weapon_proficiencies, selected_choices=attack_choices, features=features,
    )
    return stats, attacks


def _preserve_native_level_up_resource_observations(
    templates: list[dict[str, Any]], previous_templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Capacity derivation does not create a new historical bootstrap count."""
    previous_ids = [row.get("id") for row in previous_templates]
    candidate_ids = [row.get("id") for row in templates]
    if (len(previous_ids) != len(set(previous_ids))
            or len(candidate_ids) != len(set(candidate_ids))):
        raise CharacterBuildError("Resource identity needs manager repair before level-up.")
    previous = {row.get("id"): row for row in previous_templates}
    retained_templates = deepcopy(templates)
    for template in retained_templates:
        retained = previous.get(template.get("id"))
        if (retained is None or "initial_current" not in retained
                or any(template.get(key) != retained.get(key) for key in
                       ("class_row_id", "reset_on", "reset_to", "rest_behavior"))):
            continue
        initial = retained["initial_current"]
        if type(initial) is not int or initial < 0:
            raise CharacterBuildError("A retained resource observation needs manager repair before level-up.")
        # A prior item capacity can exceed today's maximum. Native issuance
        # separately proves exact audited custody of this retained observation.
        template["initial_current"] = initial
    return retained_templates


def _build_native_level_up_preview(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[dict[str, str]],
    feat_catalog: dict[str, Any],
    choice_sections: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    spell_catalog: dict[str, Any],
    target_level: int,
    total_character_level: int,
    current_ability_scores: dict[str, int],
    values: dict[str, str],
    class_row_id: str | None = None,
    resulting_profile: dict[str, Any] | None = None,
    item_catalog: dict[str, Any] | None = None,
    attained_feature_entries: list[dict[str, Any]] | None = None,
    tracker_authority_inputs: dict[str, Any] | None = None,
    acquisition_context: AcquisitionContext | None = None,
    acquisition_prior_definition: CharacterDefinition | None = None,
    spell_choice_definition: CharacterDefinition | None = None,
) -> dict[str, Any]:
    _, selected_choices = _resolve_builder_choices(choice_sections, values, strict=False)
    base_ability_scores, level_up_feat_entries, asi_summaries = _resolve_level_up_ability_score_choices(
        current_ability_scores=advancement_scores(definition.stats),
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
        strict=False,
    )
    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    gained_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    gained_feature_entries.extend(list(attained_feature_entries or []))
    gained_feature_entries.extend(level_up_feat_entries)
    gained_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    gained_automatic_prepared_feature_entries = _automatic_prepared_feature_entries(
        feature_entries=gained_feature_entries,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(gained_feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        base_ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=False,
    )
    hp_gain = 0
    try:
        hp_gain = _parse_level_up_hit_point_gain(values)
    except CharacterBuildError:
        hp_gain = 0
    gained_features = [
        str(entry.get("label") or entry.get("name") or "").strip()
        for entry in gained_feature_entries
        if str(entry.get("label") or entry.get("name") or "").strip()
    ]
    gained_features.extend(summary for summary in asi_summaries if summary)
    gained_features = _dedupe_preserve_order(gained_features)
    new_spell_names = _summarize_level_up_spell_choices(
        definition=spell_choice_definition if spell_choice_definition is not None else definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        values=values,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=gained_feature_entries,
        automatic_prepared_feature_entries=gained_automatic_prepared_feature_entries,
        extra_option_payloads=selected_campaign_option_payloads,
        class_row_id=class_row_id or "",
    )
    preview_profile = sync_profile_class_summary(resulting_profile or dict(definition.profile or {}))
    slot_lanes = _preview_level_up_slot_lanes(
        definition,
        resulting_profile=preview_profile,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        class_row_id=str(class_row_id or "").strip(),
    )
    slot_summary: list[str] = []
    for lane in slot_lanes:
        lane_title = str(lane.get("title") or "").strip() or "Spell slots"
        lane_progression = [dict(slot or {}) for slot in list(lane.get("slot_progression") or [])]
        for slot in lane_progression:
            if int(slot.get("max_slots") or 0) <= 0:
                continue
            line = f"Level {int(slot.get('level') or 0)}: {int(slot.get('max_slots') or 0)} slots"
            if len(slot_lanes) > 1:
                line = f"{lane_title}: {line}"
            slot_summary.append(line)
    preview_feature_payloads, _ = _build_feature_payloads(
        gained_feature_entries,
        ability_scores=ability_scores,
        current_level=total_character_level,
        class_row_id=class_row_id,
        class_row_levels=_profile_class_row_level_map(preview_profile),
        defer_trackers=True,
        acquisition_context=acquisition_context,
    )
    merged_features = _merge_feature_payloads(list(definition.features or []), preview_feature_payloads,
                                             preserve_source_aliases=True)
    selected_feat_features, _ = _build_feature_payloads(
        level_up_feat_entries, ability_scores=ability_scores, current_level=total_character_level,
        class_row_id=class_row_id, class_row_levels=_profile_class_row_level_map(preview_profile),
        defer_trackers=True,
    )
    ability_scores, _ = _prospective_native_level_up_abilities(
        definition, base_ability_scores=base_ability_scores, feat_selections=feat_selections,
        selected_choices=selected_choices, selected_feat_features=selected_feat_features,
        features=merged_features, item_catalog=dict(item_catalog or {}),
    )
    merged_features, preview_resource_templates = _derive_continuation_tracker_templates(
        definition, merged_features, profile=preview_profile,
        ability_scores=ability_scores,
        current_level=total_character_level,
        **dict(tracker_authority_inputs or {}),
    )
    merged_resource_templates = _merge_resource_templates(
        list(definition.resource_templates or []),
        preview_resource_templates,
        preserve_observation_ids=_continuation_pool_ids(merged_features),
    )
    merged_resource_templates = _apply_item_effect_resource_template_bonuses(
        merged_resource_templates,
        item_effect_entries=_character_builder_derivation._active_item_effect_entries_with_legacy_spell_review(
            _normalize_equipment_payloads(list(definition.equipment_catalog or []), item_catalog=dict(item_catalog or {})),
            item_catalog=dict(item_catalog or {}),
        ),
    )
    merged_resource_templates = _preserve_native_level_up_resource_observations(
        merged_resource_templates, list(definition.resource_templates or []),
    )
    preview_stats, merged_attacks = _prospective_native_level_up_numbers(
        definition=definition, profile=preview_profile, selected_class=selected_class,
        selected_subclass=selected_subclass, ability_scores=ability_scores,
        skills=list(definition.skills or []), features=merged_features, feat_selections=feat_selections,
        selected_choices=selected_choices, hp_gain=hp_gain, total_character_level=total_character_level,
        item_catalog=dict(item_catalog or {}), selected_campaign_option_payloads=selected_campaign_option_payloads,
        weapon_proficiencies=_dedupe_preserve_order(
            list((definition.proficiencies or {}).get("weapons") or [])
            + (_extract_multiclass_gained_weapon_proficiencies(selected_class)
               if class_row_id and not any(str(row.get("row_id") or "") == class_row_id
                                          for row in ensure_profile_class_rows(definition.profile)) else [])
            + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
            + list(collect_campaign_option_proficiency_grants(selected_campaign_option_payloads).get("weapons") or [])
        ),
        attack_choices=_merge_selected_choice_maps(_extract_existing_feature_choice_map(definition), selected_choices),
        preview_only=True,
        recorded_advancement_values=(values if values.get("advancement_record_type") == "completed" else None),
    )
    preview_carrying_stats = _derive_carrying_capacity_stats(
        strength_score=ability_scores["str"],
        size_label=_definition_size_label(definition, profile=preview_profile),
        effect_keys=_extract_character_effect_keys(merged_features),
    )
    typed_sources = [row.get("entry") or row.get("systems_entry") for row in gained_feature_entries]
    typed_sources += [row.get("entry") for progression in (class_progression, subclass_progression)
        for group in progression for row in list(group.get("feature_rows") or [])]
    if acquisition_context is not None and (
        has_native_grants(definition) or any(isinstance(entry, SystemsEntryRecord)
            and "native_spell_grants" in entry.metadata for entry in typed_sources)
    ):
        prospective_payload = deepcopy(definition.to_dict())
        prospective_payload["profile"] = preview_profile
        prospective_payload["features"] = merged_features
        new_spell_names += _proposed_native_spell_summaries(
            CharacterDefinition.from_dict(prospective_payload),
            systems_service=dict(tracker_authority_inputs or {}).get("systems_service"),
            spell_catalog=spell_catalog, acquisition_context=acquisition_context,
            prior_definition=acquisition_prior_definition,
            prior_custody=tuple(dict(tracker_authority_inputs or {}).get("verified_numeric_actions") or ()),
        )
    return {
        "class_level_text": str(preview_profile.get("class_level_text") or f"{selected_class.title} {target_level}"),
        "class_rows": [_class_row_level_text(row) for row in ensure_profile_class_rows(preview_profile)],
        "max_hp": (int(preview_stats["max_hp"]) if preview_stats.get("max_hp") is not None
                   else "Pending valid completed advancement" if values.get("advancement_record_type") == "completed"
                   else "Pending valid physical HP input"),
        "_resource_templates": merged_resource_templates,
        "_slot_lanes": slot_lanes,
        "carrying_capacity": _format_weight_value(preview_carrying_stats.get("carrying_capacity")),
        "push_drag_lift": _format_weight_value(preview_carrying_stats.get("push_drag_lift")),
        "gained_features": gained_features,
        "resources": [
            _summarize_preview_resource(template)
            for template in merged_resource_templates
            if _summarize_preview_resource(template)
        ],
        "attacks": [summary for attack in merged_attacks if (summary := _summarize_preview_attack(attack))],
        "spell_slots": slot_summary,
        "new_spells": new_spell_names,
    }


def _preview_level_up_slot_lanes(
    definition: CharacterDefinition,
    *,
    resulting_profile: dict[str, Any],
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    class_row_id: str,
) -> list[dict[str, Any]]:
    current_spell_rows = {
        str(row.get("class_row_id") or "").strip(): dict(row or {})
        for row in list((definition.spellcasting or {}).get("class_rows") or [])
        if str(dict(row or {}).get("class_row_id") or "").strip()
    }
    preview_spell_rows: list[dict[str, Any]] = []
    profile_rows = ensure_profile_class_rows(resulting_profile)
    for index, row in enumerate(profile_rows, start=1):
        row_payload = dict(row or {})
        row_id = str(row_payload.get("row_id") or "").strip() or f"class-row-{index}"
        if row_id == class_row_id:
            class_name = str(selected_class.title or row_payload.get("class_name") or "").strip()
            caster_progression = _class_caster_progression(
                class_name,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=target_level,
            )
            spell_mode = _spellcasting_mode_for_class(
                class_name,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=target_level,
            )
            if spell_mode or caster_progression:
                preview_spell_rows.append(
                    {
                        "class_row_id": row_id,
                        "class_name": class_name,
                        "level": target_level,
                        "caster_progression": caster_progression,
                        "selected_class": selected_class,
                        "selected_subclass": selected_subclass,
                    }
                )
            continue

        existing_row = dict(current_spell_rows.get(row_id) or {})
        class_name = str(existing_row.get("class_name") or row_payload.get("class_name") or "").strip()
        caster_progression = str(existing_row.get("caster_progression") or "").strip()
        spell_mode = str(existing_row.get("spell_mode") or "").strip()
        if not spell_mode and class_name:
            spell_mode = _spellcasting_mode_for_class(class_name)
        if not caster_progression and class_name:
            caster_progression = _class_caster_progression(class_name)
        if spell_mode or caster_progression:
            preview_spell_rows.append(
                {
                    "class_row_id": row_id,
                    "class_name": class_name,
                    "level": int(row_payload.get("level") or existing_row.get("level") or 0),
                    "caster_progression": caster_progression,
                    "selected_class": None,
                }
            )

    preview_row_contexts = [
        {
            "row_id": str(row.get("class_row_id") or "").strip(),
            "selected_class": row.get("selected_class"),
            "selected_subclass": row.get("selected_subclass"),
        }
        for row in preview_spell_rows
    ]
    _preview_rows, slot_lanes = _spell_slot_lanes_for_rows(
        preview_spell_rows,
        row_contexts=preview_row_contexts,
        total_class_rows=len(profile_rows),
        current_level=target_level,
    )
    return slot_lanes


def _build_level_one_spellcasting(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
    canonical_activation: bool = False,
    acquisition_context: AcquisitionContext | None = None,
    output_contributors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_name = selected_class.title
    ability_name = _spellcasting_ability_name_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=1,
    )
    spell_payloads = _build_level_one_spell_payloads(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
        canonical_activation=canonical_activation,
        acquisition_context=acquisition_context,
        output_contributors=output_contributors,
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        1,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    if not ability_name and not slot_progression and not spell_payloads:
        return {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "spells": [],
        }
    if not ability_name:
        return {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": slot_progression,
            "spells": spell_payloads,
        }
    ability_key = next(key for key, label in ABILITY_LABELS.items() if label == ability_name)
    modifier = _ability_modifier(ability_scores[ability_key])
    return {
        "spellcasting_class": class_name,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "spell_metric_provenance": {
            "spell_save_dc": {"kind": "formula"},
            "spell_attack_bonus": {"kind": "formula"},
        },
        "slot_progression": slot_progression,
        "spells": spell_payloads,
    }


def _build_level_up_spellcasting(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    automatic_prepared_feature_entries: list[dict[str, Any]] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
    class_row_id: str = "",
    source_authority: Any | None = None,
    output_contributors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_name = selected_class.title
    ability_name = _spellcasting_ability_name_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=target_level,
    )
    slot_progression = _level_up_slot_progression_for_class(
        class_name,
        target_level,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
    )
    spell_payloads = _build_level_up_spell_payloads(
        current_definition=current_definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
        automatic_prepared_feature_entries=automatic_prepared_feature_entries,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        class_row_id=class_row_id,
        source_authority=source_authority,
        output_contributors=output_contributors,
    )

    if not ability_name:
        if not slot_progression and not spell_payloads:
            return dict(current_definition.spellcasting or {})
        return {
            "spellcasting_class": str((current_definition.spellcasting or {}).get("spellcasting_class") or ""),
            "spellcasting_ability": str((current_definition.spellcasting or {}).get("spellcasting_ability") or ""),
            "spell_save_dc": (current_definition.spellcasting or {}).get("spell_save_dc"),
            "spell_attack_bonus": (current_definition.spellcasting or {}).get("spell_attack_bonus"),
            "slot_progression": slot_progression,
            "spells": spell_payloads,
        }

    ability_key = next(key for key, label in ABILITY_LABELS.items() if label == ability_name)
    modifier = _ability_modifier(ability_scores[ability_key])
    return reconcile_formula_row(dict(current_definition.spellcasting or {}), {
        "spellcasting_class": class_name,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "spell_metric_provenance": {
            "spell_save_dc": {"kind": "formula"},
            "spell_attack_bonus": {"kind": "formula"},
        },
        "slot_progression": slot_progression,
        "spells": spell_payloads,
    })




















def _dedupe_campaign_spell_sources(sources: list[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool, bool]] = set()
    for source in list(sources or []):
        payload = dict(source or {})
        marker = (
            str(payload.get("source_ref") or "").strip(),
            str(payload.get("mark") or "").strip(),
            bool(payload.get("always_prepared")),
            bool(payload.get("ritual")),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(payload)
    return deduped


@dataclass(frozen=True, slots=True)
class PreparedNativeDerivationFoundation:
    campaign_slug: str
    character_slug: str
    system: str
    profile_identity: str
    derivation_components: frozenset[str] | None
    _campaign_page_records: tuple[Any, ...]
    _resolved_entries: dict[str, Any]
    _item_catalog: dict[str, Any]
    _spell_catalog: dict[str, Any]
    _automatic_prepared_lookup_keys_by_row: dict[str, frozenset[str]]


def _deep_detach_native_derivation_value(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType)):
        return {
            deepcopy(key): _deep_detach_native_derivation_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_deep_detach_native_derivation_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_deep_detach_native_derivation_value(item) for item in value)
    if isinstance(value, set):
        return {_deep_detach_native_derivation_value(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(
            _deep_detach_native_derivation_value(item) for item in value
        )
    return deepcopy(value)


def _native_derivation_profile_identity(profile: dict[str, Any] | None) -> str:
    return json.dumps(
        deepcopy(dict(profile or {})),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def _prepare_native_spellcasting_profiles(
    resolved_entries: dict[str, Any],
) -> dict[str, Any]:
    prepared_entries = _deep_detach_native_derivation_value(resolved_entries)
    effective_profiles_by_row: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(
        list(prepared_entries.get("selected_class_rows") or []),
        start=1,
    ):
        row_context = dict(row or {})
        row_id = str(row_context.get("row_id") or "").strip() or f"class-row-{index}"
        class_payload = dict(row_context.get("class_payload") or {})
        selected_class = (
            row_context.get("selected_class")
            if isinstance(row_context.get("selected_class"), SystemsEntryRecord)
            else None
        )
        selected_subclass = (
            row_context.get("selected_subclass")
            if isinstance(row_context.get("selected_subclass"), SystemsEntryRecord)
            else None
        )
        class_name = str(
            (selected_class.title if selected_class is not None else "")
            or class_payload.get("class_name")
            or ""
        ).strip()
        row_level = max(
            int(row_context.get("row_level") or class_payload.get("level") or 0),
            0,
        )
        effective_profiles_by_row[row_id] = _deep_detach_native_derivation_value(
            _effective_spellcasting_profile_for_row(
                class_name,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                row_level=row_level,
            )
        )

    prepared_entries["effective_spellcasting_profiles_by_row"] = (
        effective_profiles_by_row
    )
    prepared_entries["shared_multiclass_slot_progression"] = (
        _deep_detach_native_derivation_value(
            _class_spell_progression(
                MULTICLASS_SHARED_SLOT_REFERENCE_CLASS
            ).get("slot_progression")
            or []
        )
    )
    return prepared_entries


def _prepare_native_foundation_impl(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    _read_source=None,
    _foundation_type=None,
) -> PreparedNativeDerivationFoundation:
    def detach(value):
        if _read_source is None:
            return _deep_detach_native_derivation_value(value)
        from .character_read_foundation import detach_read_preparation
        return detach_read_preparation(value, _read_source.phase)

    detached_definition = CharacterDefinition.from_dict(
        deepcopy(definition.to_dict())
    )
    selected_derivation_components = (
        FULL_DND_DERIVATION_COMPONENTS
        if derivation_components is None
        else frozenset(derivation_components)
    )
    detached_page_records = deepcopy(list(campaign_page_records or []))
    static_bundle: dict[str, Any] | None = None
    needs_static_bundle = bool(
        systems_service is not None
        and (
            (
                "sheet_entries" in selected_derivation_components
                and derivation_components is None
            )
            or item_catalog is None
            or (
                "spellcasting" in selected_derivation_components
                and spell_catalog is None
            )
        )
    )
    if needs_static_bundle:
        static_bundle = detach(
            (_build_common_builder_static_bundle(
                builder_source_reader(systems_service), detached_definition.campaign_slug,
                campaign_page_records=detached_page_records,
            ) if _read_source is None else _read_source.bundle(detached_page_records))
        )

    resolved_entries: dict[str, Any] = {}
    if "sheet_entries" in selected_derivation_components:
        if derivation_components is None:
            resolved_entries = _resolve_definition_sheet_entries(
                detached_definition,
                systems_service=builder_source_reader(systems_service),
                campaign_page_records=detached_page_records,
                static_bundle=static_bundle,
                resolved_class=resolved_class,
                resolved_subclass=resolved_subclass,
                resolved_species=resolved_species,
                resolved_background=resolved_background,
            )
        else:
            resolved_entries = _resolve_definition_targeted_sheet_entries(
                detached_definition,
                systems_service=builder_source_reader(systems_service),
                campaign_page_records=detached_page_records,
                resolved_class=resolved_class,
                resolved_subclass=resolved_subclass,
                resolved_species=resolved_species,
                resolved_background=resolved_background,
            )

    resolved_item_catalog = (
        detach(item_catalog)
        if item_catalog is not None
        else detach(
            (static_bundle or {}).get("item_catalog") or {}
        )
        if static_bundle is not None
        else detach(_build_item_catalog([]))
    )
    resolved_spell_catalog = (
        detach(spell_catalog)
        if spell_catalog is not None
        else detach(
            (static_bundle or {}).get("spell_catalog") or {}
        )
        if static_bundle is not None
        else detach(_build_spell_catalog([]))
    )
    automatic_prepared_lookup_keys_by_row: dict[str, frozenset[str]] = {}
    if "spellcasting" in selected_derivation_components:
        resolved_entries = _prepare_native_spellcasting_profiles(resolved_entries)
        automatic_prepared_lookup_keys_by_row = (
            _prepare_automatic_prepared_spell_lookup_keys(
                campaign_slug=detached_definition.campaign_slug,
                systems_service=builder_source_reader(systems_service),
                resolved_class_rows=list(
                    resolved_entries.get("selected_class_rows") or []
                ),
                spell_catalog=resolved_spell_catalog,
                campaign_page_records=detached_page_records,
            )
        )

    return (PreparedNativeDerivationFoundation if _foundation_type is None else _foundation_type)(
        campaign_slug=str(detached_definition.campaign_slug or ""),
        character_slug=str(detached_definition.character_slug or ""),
        system=str(detached_definition.system or ""),
        profile_identity=_native_derivation_profile_identity(
            detached_definition.profile
        ),
        derivation_components=(
            None
            if derivation_components is None
            else frozenset(derivation_components)
        ),
        _campaign_page_records=tuple(detached_page_records),
        _resolved_entries=deepcopy(resolved_entries),
        # These locals were detached on acquisition and have not escaped.
        # Consumers still detach independently before every normalization.
        _item_catalog=resolved_item_catalog,
        _spell_catalog=resolved_spell_catalog,
        _automatic_prepared_lookup_keys_by_row=deepcopy(
            automatic_prepared_lookup_keys_by_row
        ),
    )


def prepare_native_derivation_foundation(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> PreparedNativeDerivationFoundation:
    return _prepare_native_foundation_impl(
        definition,
        derivation_components=derivation_components,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
    )


def normalize_definition_with_prepared_native_foundation(
    definition: CharacterDefinition,
    foundation: PreparedNativeDerivationFoundation,
    *,
    source_authority: Any | None = None,
    mode: str = "historical",
    source_read_phase=None,
    transient_effects: dict[str, Any] | None = None,
) -> CharacterDefinition:
    return _normalize_definition_with_native_foundation(
        definition,
        foundation,
        consume_owned_catalogs=False,
        source_authority=source_authority,
        mode=mode,
        source_read_phase=source_read_phase,
        transient_effects=transient_effects,
    )


def _normalize_definition_with_native_foundation(
    definition: CharacterDefinition,
    foundation: PreparedNativeDerivationFoundation,
    *,
    consume_owned_catalogs: bool,
    source_authority: Any | None = None,
    mode: str = "historical",
    source_read_phase=None,
    transient_effects: dict[str, Any] | None = None,
) -> CharacterDefinition:
    if mode not in {"historical", "authoring", "effective", "native_create"}:
        raise ValueError("Unknown character normalization mode")
    if transient_effects is not None and (mode != "effective" or type(transient_effects) is not dict):
        raise ValueError("Transient effects require effective normalization and a plain effect mapping")
    if mode == "historical":
        from .committed_publication import active

        if source_active(phase=source_read_phase):
            return CharacterDefinition.from_dict(deepcopy(definition.to_dict()))
    if mode in {"authoring", "effective"} and source_authority is None:
        raise ValueError("Derived normalization requires reconciled source authority")
    payload = deepcopy(definition.to_dict())
    if (
        str(definition.campaign_slug or "") != foundation.campaign_slug
        or str(definition.character_slug or "") != foundation.character_slug
        or str(definition.system or "") != foundation.system
        or _native_derivation_profile_identity(definition.profile)
        != foundation.profile_identity
    ):
        raise ValueError(
            "The prepared native derivation foundation does not match the character baseline."
        )
    if not is_dnd_5e_system(payload.get("system")):
        return CharacterDefinition.from_dict(payload)

    payload["source"] = _seed_source_hp_baseline_from_definition(
        payload.get("source"), definition
    )
    seeded_definition = CharacterDefinition.from_dict(payload)
    from .character_feature_composition import resolve_feature_composition
    composition = getattr(source_authority, "feature_composition", None)
    if composition is None:
        composition = resolve_feature_composition(seeded_definition,
            source_read_phase.systems_view() if source_read_phase is not None else None)
    resolved_entries = deepcopy(foundation._resolved_entries)
    automatic_prepared_lookup_keys_by_row = deepcopy(
        foundation._automatic_prepared_lookup_keys_by_row
    )

    def apply_prepared_automatic_spell_flags(
        spell_payloads: list[dict[str, Any]],
        *,
        resolved_class_rows: list[dict[str, Any]],
        **_unused: Any,
    ) -> list[dict[str, Any]]:
        return _apply_prepared_automatic_prepared_spell_flags(
            spell_payloads,
            resolved_class_rows=resolved_class_rows,
            row_lookup_keys=automatic_prepared_lookup_keys_by_row,
        )

    payload.update(
        _derive_definition_core_sheet_payloads(
            seeded_definition,
            derivation_components=foundation.derivation_components,
            item_catalog=(
                foundation._item_catalog
                if consume_owned_catalogs
                else _deep_detach_native_derivation_value(foundation._item_catalog)
            ),
            spell_catalog=(
                foundation._spell_catalog
                if consume_owned_catalogs
                else _deep_detach_native_derivation_value(foundation._spell_catalog)
            ),
            campaign_page_records=deepcopy(
                list(foundation._campaign_page_records)
            ),
            resolved_entries=resolved_entries,
            automatic_prepared_spell_flags_func=(
                apply_prepared_automatic_spell_flags
            ),
            source_authority=source_authority,
            source_read_phase=source_read_phase,
            feature_composition=composition,
            transient_effects=deepcopy(transient_effects),
        )
    )
    selected_derivation_components = (
        FULL_DND_DERIVATION_COMPONENTS
        if foundation.derivation_components is None
        else frozenset(foundation.derivation_components)
    )
    if "sheet_entries" in selected_derivation_components:
        payload["profile"] = _persist_resolved_profile_links(
            payload.get("profile"),
            resolved_entries=resolved_entries,
        )
    if has_native_grants(definition) and mode in {"historical", "authoring", "native_create"}:
        # Deliberate candidate choices are the input to normalization. Legacy
        # derivation may rebuild flags/marks, but may not replace those retained
        # observations with a projected entitlement or lose an UNKNOWN field.
        payload["spellcasting"]["spells"] = deepcopy(definition.spellcasting.get("spells", []))
        payload["spellcasting"]["native_spell_grants"] = deepcopy(
            definition.spellcasting["native_spell_grants"]
        )
    if mode != "effective":
        from .character_feature_composition import retain_replaced_observations, retain_replacement_claims
        payload["features"] = retain_replaced_observations(definition.features, payload["features"], composition)
        payload["features"] = retain_replacement_claims(definition.features, payload["features"])
    return CharacterDefinition.from_dict(payload)


def _normalize_native_entry(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    source_authority: Any | None = None,
    mode: str = "historical",
    transient_effects: dict[str, Any] | None = None,
    _private_read=False,
) -> CharacterDefinition:
    if mode not in {"historical", "authoring", "effective", "native_create"}:
        raise ValueError("Unknown character normalization mode")
    if transient_effects is not None and (mode != "effective" or type(transient_effects) is not dict):
        raise ValueError("Transient effects require effective normalization and a plain effect mapping")
    if mode == "historical":
        from .committed_publication import active

        if source_active(systems_service):
            return CharacterDefinition.from_dict(deepcopy(definition.to_dict()))
    if mode in {"authoring", "effective"} and source_authority is None:
        raise ValueError("Derived normalization requires reconciled source authority")
    if not is_dnd_5e_system(definition.system):
        return CharacterDefinition.from_dict(deepcopy(definition.to_dict()))
    foundation = None
    if _private_read and mode in {"effective", "historical"}:
        from .character_read_foundation import prepare_read_foundation
        foundation = prepare_read_foundation(
            definition, derivation_components=derivation_components,
            item_catalog=item_catalog, spell_catalog=spell_catalog,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            resolved_class=resolved_class, resolved_subclass=resolved_subclass,
            resolved_species=resolved_species, resolved_background=resolved_background,
        )
    if foundation is None:
        foundation = prepare_native_derivation_foundation(
            definition,
            derivation_components=derivation_components,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            resolved_class=resolved_class,
            resolved_subclass=resolved_subclass,
            resolved_species=resolved_species,
            resolved_background=resolved_background,
        )
    # This foundation is local, unexposed and consumed exactly once. The public
    # reusable-foundation entry point always keeps independent catalog copies.
    return _normalize_definition_with_native_foundation(
        definition,
        foundation,
        consume_owned_catalogs=True,
        source_authority=source_authority,
        mode=mode,
        source_read_phase=phase_of(systems_service),
        transient_effects=transient_effects,
    )


def normalize_definition_to_native_model(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    source_authority: Any | None = None,
    mode: str = "historical",
    transient_effects: dict[str, Any] | None = None,
) -> CharacterDefinition:
    return _normalize_native_entry(
        definition,
        derivation_components=derivation_components,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
        source_authority=source_authority,
        mode=mode,
        transient_effects=transient_effects,
    )


def normalize_definition_for_source_read(
    definition: CharacterDefinition,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
    source_authority: Any | None = None,
    mode: str = "historical",
    transient_effects: dict[str, Any] | None = None,
) -> CharacterDefinition:
    return _normalize_native_entry(
        definition,
        derivation_components=derivation_components,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
        source_authority=source_authority,
        mode=mode,
        transient_effects=transient_effects,
        _private_read=True,
    )


def project_definition_with_transient_effects(
    definition: CharacterDefinition,
    transient_effects: dict[str, Any] | None,
    *,
    derivation_components: frozenset[str] | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    source_authority: Any | None = None,
) -> CharacterDefinition:
    """Re-derive a read-only D&D projection from a canonical definition.

    Transient effects are deliberately excluded from persisted definitions and
    the normalized-definition cache. Callers must pass the canonical base for
    each projection so active/inactive state changes cannot stack or go stale.
    """
    effects = deepcopy(transient_effects) if isinstance(transient_effects, dict) else {}
    if not effects or not is_dnd_5e_system(definition.system):
        return definition
    selected_derivation_components = (
        FULL_DND_DERIVATION_COMPONENTS
        if derivation_components is None
        else frozenset(derivation_components)
    )
    resolved_entries = (
        (
            _resolve_definition_sheet_entries
            if derivation_components is None
            else _resolve_definition_targeted_sheet_entries
        )(
            definition,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        if "sheet_entries" in selected_derivation_components
        else {}
    )
    payload = deepcopy(definition.to_dict())
    payload.update(
        _derive_definition_core_sheet_payloads(
            definition,
            derivation_components=derivation_components,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            resolved_entries=resolved_entries,
            transient_effects=effects,
            source_authority=source_authority,
        )
    )
    return CharacterDefinition.from_dict(payload)


def _summarize_preview_spell(spell: dict[str, Any]) -> str:
    name = str(spell.get("name") or "").strip()
    badges = []
    if bool(spell.get("is_always_prepared")):
        badges.append("Always prepared")
    elif bool(spell.get("is_bonus_known")):
        badges.append("Granted")
    access_badge = _spell_access_badge_label(spell)
    if access_badge:
        badges.append(access_badge)
    mark = str(spell.get("mark") or "").strip()
    if mark:
        badges.append(mark)
    if not name:
        return ""
    if badges:
        return f"{name} ({', '.join(badges)})"
    return name




def _format_contained_value(value: Any) -> str:
    label = _format_currency_seed(_currency_seed_from_cp(value))
    if not label:
        return ""
    return f"Contains {label}."


def _extract_class_armor_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    raw_values = list(dict(selected_class.metadata.get("starting_proficiencies") or {}).get("armor") or [])
    return [_humanize_proficiency_value(value, category="armor") for value in raw_values]


def _fixed_class_weapon_proficiency_entries(
    selected_class: SystemsEntryRecord | None, *, strict: bool = False,
) -> list[str]:
    """Separate fixed strings from the supported optional source clause.

    Reconstruction refuses unsupported shape. Ordinary native reads withhold
    this class's fixed grants instead of raising or stringifying source objects.
    Neither mode supplies permission for an optional proficiency.
    """
    return _class_weapon_proficiency_contract(selected_class, strict=strict)[0]


def _class_weapon_proficiency_contract(selected_class, *, strict=False):
    """Closed fixed/optional source contract; optional never means permitted."""
    def unsupported():
        if strict:
            raise ValueError("A class weapon proficiency has an unsupported source shape.")
        return [], []

    if selected_class is None:
        return [], []
    metadata = selected_class.metadata
    if type(metadata) is not dict:
        return unsupported()
    starting = metadata.get("starting_proficiencies")
    if starting is None:
        return [], []
    if type(starting) is not dict:
        return unsupported()
    values = starting.get("weapons")
    if values is None:
        return [], []
    if type(values) is not list:
        return unsupported()
    fixed, optional = [], []
    for value in values:
        if isinstance(value, str) and value.strip():
            fixed.append(value)
        elif (type(value) is dict and set(value) == {"optional", "proficiency"}
                and value["optional"] is True and value["proficiency"] == "firearms"):
            if value["proficiency"] in optional:
                return unsupported()
            optional.append(value["proficiency"])
        else:
            return unsupported()
    return fixed, optional


def _extract_class_weapon_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    return [_humanize_proficiency_value(value, category="weapons")
            for value in _fixed_class_weapon_proficiency_entries(selected_class)]


def _extract_class_tool_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    raw_values = list(dict(selected_class.metadata.get("starting_proficiencies") or {}).get("tools") or [])
    return [_clean_embedded_text(str(value or "")) for value in raw_values if _clean_embedded_text(str(value or ""))]


def _multiclassing_payload(selected_class: SystemsEntryRecord | None) -> dict[str, Any]:
    if selected_class is None:
        return {}
    return dict(selected_class.metadata.get("multiclassing") or {})


def _multiclass_requirement_blocks(requirements: Any) -> list[dict[str, int]]:
    if not isinstance(requirements, dict):
        return []
    if "or" in requirements:
        blocks: list[dict[str, int]] = []
        for block in list(requirements.get("or") or []):
            blocks.extend(_multiclass_requirement_blocks(block))
        return blocks
    normalized: dict[str, int] = {}
    for ability_key, minimum in requirements.items():
        clean_key = normalize_lookup(str(ability_key or "").strip())
        if clean_key not in ABILITY_KEYS:
            continue
        try:
            normalized[clean_key] = int(minimum)
        except (TypeError, ValueError):
            continue
    return [normalized] if normalized else []


def _multiclass_requirement_text(selected_class: SystemsEntryRecord | None) -> str:
    blocks = _multiclass_requirement_blocks(_multiclassing_payload(selected_class).get("requirements"))
    if not blocks:
        return ""
    rendered_blocks = []
    for block in blocks:
        parts = [
            f"{ABILITY_LABELS.get(ability_key, ability_key.title())} {minimum}"
            for ability_key, minimum in block.items()
        ]
        if parts:
            rendered_blocks.append(" and ".join(parts))
    return " or ".join(rendered_blocks)


def _meets_multiclass_requirements(
    selected_class: SystemsEntryRecord | None,
    *,
    ability_scores: dict[str, int],
) -> bool:
    blocks = _multiclass_requirement_blocks(_multiclassing_payload(selected_class).get("requirements"))
    if not blocks:
        return True
    for block in blocks:
        if all(int(ability_scores.get(ability_key, 0) or 0) >= int(minimum or 0) for ability_key, minimum in block.items()):
            return True
    return False


def _extract_multiclass_gained_armor_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    raw_values = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("armor") or [])
    return [_humanize_proficiency_value(value, category="armor") for value in raw_values]


def _extract_multiclass_gained_weapon_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    raw_values = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("weapons") or [])
    return [_humanize_proficiency_value(value, category="weapons") for value in raw_values]


def _extract_multiclass_gained_tool_proficiencies(
    selected_class: SystemsEntryRecord | None,
    selected_choices: dict[str, list[str]] | None = None,
) -> list[str]:
    raw_blocks = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("tools") or [])
    results: list[str] = []
    for block in raw_blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                results.append(_humanize_words(cleaned))
            continue
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        for value in list((selected_choices or {}).get("multiclass_tools", []) or []):
            cleaned = _clean_embedded_text(value)
            if cleaned:
                results.append(_humanize_words(cleaned))
    return _dedupe_preserve_order(results)


def _extract_multiclass_gained_language_proficiencies(
    selected_class: SystemsEntryRecord | None,
    selected_choices: dict[str, list[str]] | None = None,
) -> list[str]:
    raw_blocks = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("languages") or [])
    results: list[str] = []
    for block in raw_blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                results.append(cleaned)
            continue
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        if choose:
            for value in list((selected_choices or {}).get("multiclass_languages", []) or []):
                cleaned = _humanize_proficiency_value(value, category="languages")
                if cleaned:
                    results.append(cleaned)
            continue
        for key, value in block.items():
            if value is True:
                results.append(_humanize_proficiency_value(key, category="languages"))
    return _dedupe_preserve_order(results)


def _multiclass_skill_choice_fields(
    selected_class: SystemsEntryRecord | None,
    *,
    definition: CharacterDefinition,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    existing_levels = _skill_proficiency_levels_from_rows(
        list(definition.skills or []),
        ability_scores=_ability_scores_from_definition(definition),
        proficiency_bonus=int((definition.stats or {}).get("proficiency_bonus") or _proficiency_bonus_for_level(_resolve_native_character_level(definition))),
        prefer_explicit=(_character_source_type(definition) == "native_character_builder"),
    )
    raw_blocks = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("skills") or [])
    fields: list[dict[str, Any]] = []
    for block in raw_blocks:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        options = [
            _choice_option(_skill_label(option), option)
            for option in list(choose.get("from") or [])
            if not existing_levels.get(normalize_lookup(option))
        ]
        count = int(choose.get("count") or 0)
        if not options or count <= 0:
            continue
        for index in range(count):
            field_name = f"multiclass_skill_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Added Class Skill {index + 1}",
                    "help_text": f"Choose {count} skill{'s' if count != 1 else ''} gained from {selected_class.title} multiclassing.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "multiclass_skills",
                    "kind": "skill",
                }
            )
    return fields


def _multiclass_tool_choice_fields(
    selected_class: SystemsEntryRecord | None,
    *,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    raw_blocks = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("tools") or [])
    fields: list[dict[str, Any]] = []
    for block in raw_blocks:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        options = [
            _choice_option(_clean_embedded_text(option), option)
            for option in list(choose.get("from") or [])
            if _clean_embedded_text(option)
        ]
        count = int(choose.get("count") or 0)
        if not options or count <= 0:
            continue
        for index in range(count):
            field_name = f"multiclass_tool_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Added Class Tool {index + 1}",
                    "help_text": f"Choose {count} tool option{'s' if count != 1 else ''} gained from {selected_class.title} multiclassing.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "multiclass_tools",
                    "kind": "tool",
                }
            )
    return fields


def _multiclass_language_choice_fields(
    selected_class: SystemsEntryRecord | None,
    *,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    raw_blocks = list(dict(_multiclassing_payload(selected_class).get("proficienciesGained") or {}).get("languages") or [])
    fields: list[dict[str, Any]] = []
    for block in raw_blocks:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        options = [
            _choice_option(_humanize_proficiency_value(option, category="languages"), option)
            for option in list(choose.get("from") or [])
            if _humanize_proficiency_value(option, category="languages")
        ]
        count = int(choose.get("count") or 0)
        if not options or count <= 0:
            continue
        for index in range(count):
            field_name = f"multiclass_language_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Added Class Language {index + 1}",
                    "help_text": f"Choose {count} language{'s' if count != 1 else ''} gained from {selected_class.title} multiclassing.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "multiclass_languages",
                    "kind": "language",
                }
            )
    return fields


def _extract_multiclass_gained_skill_proficiencies(selected_choices: dict[str, list[str]] | None = None) -> list[str]:
    return [_skill_label(value) for value in list((selected_choices or {}).get("multiclass_skills", []) or []) if _skill_label(value)]


def _extract_fixed_skills(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("skill_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        if "choose" in block or "any" in block:
            continue
        for key, value in block.items():
            if value is True:
                results.append(_skill_label(key))
    return results


def _extract_fixed_languages(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("languages") or metadata.get("language_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if value is True:
                results.append(_humanize_proficiency_value(key, category="languages"))
    return results


def _extract_fixed_tool_proficiencies(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("tool_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                results.append(cleaned)
            continue
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if value is True:
                results.append(_clean_embedded_text(key))
    return results


def _extract_species_feature_entries(entry: SystemsEntryRecord) -> list[dict[str, Any]]:
    raw_entries = list((entry.body or {}).get("entries") or [])
    feature_entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        raw_name = str(raw_entry.get("name") or "").strip()
        normalized_name = normalize_lookup(raw_name.replace("Feature:", "").strip())
        if not raw_name or normalized_name in REDUNDANT_SPECIES_TRAIT_NAMES:
            continue
        description_markdown = _flatten_entry_markdown(raw_entry.get("entries"))
        if not description_markdown:
            continue
        feature_entries.append(
            {
                "kind": "species_trait",
                "label": raw_name.replace("Feature:", "").strip(),
                "description_markdown": description_markdown,
                "systems_entry": entry,
            }
        )
    return feature_entries


def _extract_background_feature_entries(entry: SystemsEntryRecord) -> list[dict[str, Any]]:
    raw_entries = list((entry.body or {}).get("entries") or [])
    feature_entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        if not bool(dict(raw_entry.get("data") or {}).get("isFeature")):
            continue
        raw_name = str(raw_entry.get("name") or "").strip()
        label = raw_name.replace("Feature:", "").strip() or entry.title
        description_markdown = _flatten_entry_markdown(raw_entry.get("entries"))
        if not description_markdown:
            continue
        feature_entries.append(
            {
                "kind": "background_feature",
                "label": label,
                "description_markdown": description_markdown,
                "systems_entry": entry,
            }
        )
    return feature_entries


def _flatten_entry_markdown(value: Any) -> str:
    blocks: list[str] = []
    if isinstance(value, str):
        return _clean_embedded_text(value)
    if isinstance(value, list):
        for item in value:
            rendered = _flatten_entry_markdown(item)
            if rendered:
                blocks.append(rendered)
        return "\n\n".join(blocks).strip()
    if isinstance(value, dict):
        nested_entries = value.get("entries")
        if nested_entries is not None:
            return _flatten_entry_markdown(nested_entries)
        if value.get("entry"):
            return _clean_embedded_text(str(value.get("entry") or ""))
    return ""




def _summarize_preview_attack(attack: dict[str, Any]) -> str:
    name = str(attack.get("name") or "").strip()
    if not name:
        return ""
    attack_bonus = attack.get("attack_bonus")
    damage = str(attack.get("damage") or "").strip()
    parts: list[str] = []
    if attack_bonus not in {"", None}:
        parts.append(f"{int(attack_bonus):+d}")
    if damage:
        parts.append(damage)
    if parts:
        return f"{name} ({', '.join(parts)})"
    category = str(attack.get("category") or "").strip()
    if category:
        return f"{name} ({category})"
    return name




















def _humanize_saving_throw(ability_key: str) -> str:
    return f"{ABILITY_LABELS.get(ability_key, ability_key.title())} Save"


def _all_skill_options() -> list[tuple[str, str]]:
    return [(token, label) for token, label in SKILL_LABELS.items()]




def _humanize_proficiency_value(value: str, *, category: str) -> str:
    cleaned = _clean_embedded_text(value)
    normalized = normalize_lookup(cleaned)
    if category == "armor":
        return {
            "light": "Light Armor",
            "medium": "Medium Armor",
            "heavy": "Heavy Armor",
            "shield": "Shields",
        }.get(normalized, _humanize_words(cleaned))
    if category == "weapons":
        return {
            "simple": "Simple Weapons",
            "martial": "Martial Weapons",
            "firearms": "Firearms",
            "improvised": "Improvised Weapons",
        }.get(normalized, _humanize_words(cleaned))
    return _humanize_words(cleaned)


# Actual ordinary providers/type boundaries bypassed by private read preparation.
# Public preparation still resolves its current foundation factory at return.
_NATIVE_READ_PREPARATION_RECIPE = tuple((name, globals()[name]) for name in (
    "_effective_item_catalog_for_definition", "_effective_spell_catalog_for_definition",
    "_build_common_builder_static_bundle", "prepare_native_derivation_foundation",
    "_deep_detach_native_derivation_value", "normalize_definition_to_native_model",
    "PreparedNativeDerivationFoundation", "_prepare_native_foundation_impl",
    "_derive_definition_core_sheet_payloads", "_normalize_definition_with_native_foundation",
    "_resolve_definition_sheet_entries", "_prepare_automatic_prepared_spell_lookup_keys",
))


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'deepcopy',
    '_systems_ref_from_entry',
    '_class_weapon_proficiency_contract',
    '_humanize_proficiency_value',
    'current_background_entry',
    'validated_background_instrument_names',
    '_background_instrument_count',
    '_background_instrument_entries',
    '_background_instrument_saved_values',
    '_background_instrument_payload',
    '_fixed_class_weapon_proficiency_entries',
    '_extract_class_armor_proficiencies',
    '_tool_proficiency_options',
    '_supported_feature_expertise_blocks',
    '_extract_feat_skill_proficiencies',
    '_extract_feat_tool_proficiencies',
    '_extract_feat_language_proficiencies',
    '_extract_feat_armor_proficiencies',
    '_extract_feat_weapon_proficiencies',
    '_apply_feature_expertise_to_skill_proficiency_levels',
    '_apply_feat_expertise_to_skill_proficiency_levels',
    '_apply_feature_expertise_to_tool_proficiencies',
    '_extract_character_effect_keys',
    '_skill_targets_for_effect_key',
    '_max_skill_proficiency_level',
    '_flatten_entry_markdown',
))
