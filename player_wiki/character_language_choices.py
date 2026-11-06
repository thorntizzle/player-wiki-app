"""Shared ordinary-language domains for typed current source choices.

The vocabulary follows the 2014 Basic Rules standard/exotic tables:
https://www.dndbeyond.com/sources/dnd/basic-rules-2014/personality-and-background
This selects a domain, never a grant; the current source and campaign policy
must separately allow the choice. Fixed class communications are not options.
"""
from .character_builder_constants import STANDARD_LANGUAGE_OPTIONS, UNRESTRICTED_LANGUAGE_OPTIONS

PARENT_FRAME = "native_parent_language_choices"


def language_options_for_block(block):
    """Keep anyStandard narrow; any exposes the ordinary complete vocabulary."""
    if not isinstance(block, dict):
        return ()
    if block.get("anyStandard"):
        return tuple(STANDARD_LANGUAGE_OPTIONS)
    if block.get("any"):
        return tuple(UNRESTRICTED_LANGUAGE_OPTIONS)
    return ()


def conditional_language(block):
    """Decode a source-declared replacement, never infer one from prose."""
    if not isinstance(block, dict) or "ifAlreadyProficient" not in block:
        return None
    from .repository import normalize_lookup
    value = block["ifAlreadyProficient"]
    if (set(block) != {"ifAlreadyProficient"} or type(value) is not dict
            or set(value) != {"proficiency", "replacement"}
            or type(value["proficiency"]) is not str
            or type(value["replacement"]) is not dict
            or len(value["replacement"]) != 1
            or next(iter(value["replacement"]), None) not in {"any", "anyStandard"}
            or type(next(iter(value["replacement"].values()), None)) is not int
            or next(iter(value["replacement"].values()), None) != 1):
        raise ValueError("A conditional language requires one named language and one ordinary replacement.")
    names = {normalize_lookup(name): name for name in UNRESTRICTED_LANGUAGE_OPTIONS}
    condition = names.get(normalize_lookup(value["proficiency"]))
    if condition is None:
        raise ValueError("The conditional language is outside the supported ordinary vocabulary.")
    return {"condition": condition, "options": list(language_options_for_block(value["replacement"]))}


def background_language_slots(entry):
    """Ordered native background slots, including an explicit conditional branch."""
    if entry is None:
        return []
    result = []
    for block in entry.metadata.get("language_proficiencies") or []:
        conditional = conditional_language(block)
        if conditional:
            result.append(conditional)
        elif isinstance(block, dict):
            count = block.get("anyStandard", block.get("any", 0))
            if type(count) is not int or not 0 <= count <= 18:
                raise ValueError("Background language choices need a bounded source count.")
            result.extend({"options": list(language_options_for_block(block))} for _ in range(count))
    return result


def resolve_background_languages(entry, selected, prior, *, strict=True):
    """Prior languages must come from the selected species, not current totals."""
    from .repository import normalize_lookup
    slots = background_language_slots(entry)
    if type(selected) is not list or len(selected) != len(slots):
        if strict:
            raise ValueError("Confirm each current background language choice.")
        return []
    known = {normalize_lookup(name) for name in prior}
    result = []
    for slot, value in zip(slots, selected):
        condition = slot.get("condition")
        if condition:
            already = normalize_lookup(condition) in known
            if value == "__grant__" and not already:
                label = condition
            elif value in slot["options"] and already and normalize_lookup(value) not in known:
                label = value
            else:
                if strict:
                    raise ValueError("A replacement language requires an independently owned prior language; otherwise gain the source language.")
                return []
        elif value in slot["options"]:
            label = value
        else:
            if strict:
                raise ValueError("The background language does not belong to its source domain.")
            return []
        if normalize_lookup(label) in {normalize_lookup(name) for name in result}:
            if strict:
                raise ValueError("Background language choices must be distinct.")
            return []
        result.append(label)
    return result


def parent_language_frame(species, background, choices):
    from .character_builder_equipment import _systems_ref_from_entry
    if not any(slot.get("condition") for slot in background_language_slots(background)):
        return None
    return {"schema_version": 1, "species_ref": _systems_ref_from_entry(species),
            "background_ref": _systems_ref_from_entry(background),
            "species_choices": list(choices.get("species_languages", [])),
            "background_choices": list(choices.get("background_languages", []))}


def current_parent_languages(definition, service):
    """Recheck typed acquisition inputs; the native audit still owns custody."""
    from . import character_builder as builder
    from .character_reconstruction_proficiencies import grant_contract
    from .character_builder_equipment import _systems_ref_from_entry
    from .repository import normalize_lookup
    parents = {}
    for role in ("species", "background"):
        ref = definition.profile.get(role + "_ref")
        if type(ref) is not dict or not ref.get("entry_key"):
            raise ValueError("Conditional languages need exact current parent sources.")
        entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if (entry is None or ref != _systems_ref_from_entry(entry)
                or not service.is_entry_enabled_for_campaign(definition.campaign_slug, entry)):
            raise ValueError("A conditional language parent source changed or is unavailable.")
        parents[role] = entry
    required = any(slot.get("condition") for slot in background_language_slots(parents["background"]))
    frame = definition.source.get(PARENT_FRAME)
    if not required and PARENT_FRAME not in definition.source:
        return None
    if (not required or type(frame) is not dict
            or set(frame) != {"schema_version", "species_ref", "background_ref", "species_choices", "background_choices"}
            or type(frame["schema_version"]) is not int or frame["schema_version"] != 1
            or any(frame[role + "_ref"] != definition.profile[role + "_ref"] for role in parents)
            or any(type(frame[key]) is not list or len(frame[key]) > 18
                   or any(type(value) is not str or len(value) > 160 for value in frame[key])
                   for key in ("species_choices", "background_choices"))):
        raise ValueError("Conditional parent language acquisition needs its exact retained choices.")
    fixed, slots = grant_contract(None, [("species", parents["species"])])
    slots = [slot for slot in slots if slot["category"] == "languages"]
    selected = frame["species_choices"]
    if (len(selected) != len(slots) or len(set(selected)) != len(selected)
            or {normalize_lookup(value) for value in selected} & {normalize_lookup(value) for value in fixed["languages"]}
            or any(value not in slot["options"] for value, slot in zip(selected, slots))):
        raise ValueError("The retained species language choices no longer match their source.")
    prior = fixed["languages"] + selected
    return prior + builder._extract_fixed_languages(parents["background"]) + resolve_background_languages(
        parents["background"], frame["background_choices"], prior)
