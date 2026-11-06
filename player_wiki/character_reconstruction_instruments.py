"""Bind retained background instruments through the native choice contract."""
from __future__ import annotations

from copy import deepcopy

from .character_source_repair import SourceRepairError


def choice_context(definition, background, service, pages, values):
    from . import character_builder as builder

    count = builder._background_instrument_count(background)
    saved = definition.profile.get("background_choices")
    if not count:
        if saved not in (None, {}):
            builder.validated_background_instrument_names(definition, service, strict=True)
        return [], {}
    from .character_read_foundation import read_item_catalog_for_definition
    catalog = read_item_catalog_for_definition(
        definition, systems_service=service, campaign_page_records=pages)
    previous = (builder._background_instrument_saved_values(
        definition, background, catalog, strict=True) if saved not in (None, {}) else {})
    selected = {**previous, **{name.removeprefix("feature_"): value
        for name, value in values.items() if name.startswith("feature_background_instrument_")}}
    fields = []
    for field in builder._build_background_choice_fields(background, selected, item_catalog=catalog):
        if field["name"].startswith("background_instrument_"):
            fields.append({**field, "name": "feature_" + field["name"],
                "help_text": "Confirm this retained instrument proficiency against its current source. No item is granted."})
    return fields, catalog


def compose_choice(definition, profile, background, catalog, choices):
    from . import character_builder as builder
    from .repository import normalize_lookup

    values = {f"background_instrument_{index}": value for index, value in
              enumerate(choices.get("background_instruments", []), start=1)}
    selected, names = builder._background_instrument_payload(background, values, catalog, strict=True)
    previous = definition.profile.get("background_choices")
    if previous not in (None, {}) and previous != selected:
        raise SourceRepairError("Reconstruction must preserve the existing typed background instrument choice.")
    retained = {normalize_lookup(name) for name in definition.proficiencies.get("tools", [])}
    if any(normalize_lookup(name) not in retained for name in names):
        raise SourceRepairError("Choose only an instrument proficiency already retained by this character.")
    if selected is not None:
        profile["background_choices"] = deepcopy(selected)


def current_choice(definition, service):
    """Validate the native payload and reload selected sources for proof binding."""
    from . import character_builder as builder
    from .character_builder_equipment import _systems_ref_from_entry

    background = builder.current_background_entry(definition, service)
    saved = definition.profile.get("background_choices")
    if background is None:
        if saved not in (None, {}):
            raise SourceRepairError("The background instrument owner is unavailable or changed.")
        return [], None
    if not builder._background_instrument_count(background) and saved in (None, {}):
        return [], None
    names = builder.validated_background_instrument_names(definition, service, strict=True)
    refs = saved["instrument"]["entries"]
    # The profile is the native current choice. Original reconstruction inputs
    # remain history if a later reviewed native edit changes that selection.
    # Binding this payload below makes the old proof insufficient for a change.
    sources = []
    for ref in refs:
        entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if (entry is None or _systems_ref_from_entry(entry) != ref
                or not builder._background_instrument_entries({"entries": [entry]})):
            raise SourceRepairError("A retained background instrument source changed during qualification.")
        sources.append({"reference": deepcopy(ref), "metadata": deepcopy(entry.metadata), "body": deepcopy(entry.body)})
    return names, {"selection": deepcopy(saved), "sources": sources}


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'deepcopy',
    'current_choice',
))
