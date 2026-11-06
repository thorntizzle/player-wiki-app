"""Bounded source-owned proficiency choices for retained native builds.

This consumes structured grants only. It does not infer inheritance, parse a
named feature's prose, or turn a retained label into evidence of a grant.
"""
from __future__ import annotations

from .character_source_repair import SourceRepairError


def source_weapon_labels(entry):
    """Use a structured item's identity rather than its plural display alias."""
    import re
    from . import character_builder as builder
    labels = []
    for value in builder._fixed_class_weapon_proficiency_entries(entry, strict=True):
        match = re.fullmatch(r"\{@item ([^{}]+)\}", value.strip())
        identity = match.group(1).split("|", 1)[0] if match else value
        labels.append(builder._humanize_proficiency_value(identity, category="weapons"))
    return labels


def compound_weapon_mappings(definition, class_entry):
    """Nominate only a unique complete pair of retained compound fragments."""
    import re
    from .repository import normalize_lookup
    raw = list(definition.proficiencies.get("weapons") or [])
    canonical = source_weapon_labels(class_entry)
    allowed = {normalize_lookup(name) for name in canonical}
    unknown = [(index, name) for index, name in enumerate(raw) if normalize_lookup(name) not in allowed]
    candidates = []
    for name in canonical:
        if normalize_lookup(name) in {normalize_lookup(value) for value in raw}:
            continue
        words = re.findall(r"[A-Za-z]+", name)
        if len(words) != 2:
            continue
        first = [index for index, value in unknown if normalize_lookup(value) == normalize_lookup(words[0])]
        second = [index for index, value in unknown if normalize_lookup(value) == normalize_lookup(words[1])]
        if len(first) == len(second) == 1 and first[0] != second[0]:
            candidates.append({"indices": sorted([first[0], second[0]]), "canonical": name,
                "raw": [raw[index] for index in sorted([first[0], second[0]])], "source_entry": class_entry.entry_key})
    return [row for row in candidates if not any(other is not row and set(row["indices"]) & set(other["indices"])
                                                  for other in candidates)]


def weapon_mapping_fields(definition, class_entry, values):
    fields = []
    for index, row in enumerate(compound_weapon_mappings(definition, class_entry)):
        name = f"feature_weapon_mapping_{index}"
        fields.append({"name": name, "label": "Retained compound weapon proficiency: " + ", ".join(row["raw"]),
            "help_text": "Review the exact current class item reference; original imported labels remain in provenance.",
            "options": [{"label": "Unresolved; keep raw labels without a grant", "value": f"__unresolved_weapon_{index}__"},
                        {"label": "Map to " + row["canonical"], "value": row["canonical"]}],
            "selected": values.get(name, ""), "group_key": f"reconstruction:class:weapon_mapping_{index}", "kind": "weapon"})
    return fields


def apply_weapon_mappings(definition, class_entry, choices):
    raw = list(definition.proficiencies.get("weapons") or [])
    mapped, removed, replacements = [], set(), {}
    for index, row in enumerate(compound_weapon_mappings(definition, class_entry)):
        selected = choices.get(f"reconstruction:class:weapon_mapping_{index}")
        if selected == [f"__unresolved_weapon_{index}__"]:
            continue
        if selected != [row["canonical"]]:
            raise SourceRepairError("Confirm the exact current source mapping for the compound weapon labels.")
        mapped.append(row)
        replacements[row["indices"][0]] = row["canonical"]
        removed.update(row["indices"][1:])
    return [replacements.get(index, value) for index, value in enumerate(raw) if index not in removed], mapped


def current_owners(definition, service):
    from .character_profile import profile_class_rows
    rows = profile_class_rows(definition.profile)
    if len(rows) != 1:
        raise SourceRepairError("Proficiency reconstruction needs one current class owner.")
    refs = [("class", rows[0].get("systems_ref")), ("species", definition.profile.get("species_ref")),
            ("background", definition.profile.get("background_ref"))]
    from .character_armor_models import historical_ids
    summaries = historical_ids(definition)
    refs += [(row.get("id"), row.get("systems_ref")) for row in definition.features
             if isinstance(row, dict) and isinstance(row.get("systems_ref"), dict) and row.get("id") not in summaries]
    owners, seen = [], set()
    for identity, ref in refs:
        if not identity or not isinstance(ref, dict) or not ref.get("entry_key"):
            raise SourceRepairError("A retained proficiency source has no exact owner.")
        entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if entry is None or any(ref.get(key) and ref[key] != getattr(entry, key, None)
                                for key in ("entry_key", "source_id", "entry_type", "slug")):
            raise SourceRepairError("A retained proficiency source is unavailable or changed owner.")
        if entry.entry_type == "subclass":
            from .character_subclass_companion import selected_subclass_companion_matches
            feature = next((row for row in definition.features if isinstance(row, dict) and row.get("id") == identity), None)
            if not selected_subclass_companion_matches(feature, definition.profile, entry, service, definition.campaign_slug):
                raise SourceRepairError("A retained subclass container is not the exact inert selected subclass.")
            continue  # The container is evidence, never a proficiency grant.
        if identity not in {"class", "species", "background"} and entry.entry_type in {"race", "subrace", "background"}:
            from .character_parent_facets import linked_companion_facet
            feature = next((row for row in definition.features if isinstance(row, dict) and row.get("id") == identity), None)
            if linked_companion_facet(feature, definition.profile, entry) is None:
                raise SourceRepairError("A retained parent companion has no exact inert current facet.")
            continue  # The selected parent already owns every proficiency grant.
        if entry.entry_key not in seen:
            owners.append((identity, entry))
            seen.add(entry.entry_key)
    return owners


def starting_grant(metadata, category):
    """Use the same typed class source in parsing, bookkeeping and bases."""
    starting = dict(metadata.get("starting_proficiencies") or {})
    if category == "tools" and "toolProficiencies" in starting:
        if type(starting["toolProficiencies"]) is not list:
            raise SourceRepairError("Typed class tool proficiencies must be an explicit list.")
        return starting["toolProficiencies"]
    return starting.get(category)


def grant_contract(definition, owners, *, item_catalog=None):
    from . import character_builder as builder
    from .character_builder_constants import SKILL_LABELS, STANDARD_LANGUAGE_OPTIONS, UNRESTRICTED_LANGUAGE_OPTIONS, COMMON_TOOL_PROFICIENCY_OPTIONS
    from .repository import normalize_lookup
    fixed = {key: [] for key in ("skills", "tools", "languages", "armor", "weapons")}
    slots = []
    communications = []
    for _identity, entry in owners:
        for block in entry.metadata.get("communication_proficiencies") or []:
            if not isinstance(block, dict) or any(value is not True for value in block.values()):
                raise SourceRepairError("Communication grants must be fixed and source-owned.")
            communications.extend(builder._humanize_proficiency_value(name, category="languages") for name in block)
    ordinary_languages = [name for name in UNRESTRICTED_LANGUAGE_OPTIONS
                          if normalize_lookup(name) not in {normalize_lookup(value) for value in communications}]
    domains = {"skills": list(SKILL_LABELS.values()), "tools": list(COMMON_TOOL_PROFICIENCY_OPTIONS),
               "languages": ordinary_languages}
    gaming = [name for name in COMMON_TOOL_PROFICIENCY_OPTIONS
              if normalize_lookup(name) in {"diceset", "dragonchessset", "playingcardset", "threedragonanteset"}]

    def blocks(value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise SourceRepairError("A proficiency source has an unsupported grant shape.")
        return value

    def add(identity, category, values):
        for block in blocks(values):
            if isinstance(block, str):
                if not block.strip():
                    raise SourceRepairError("A proficiency source contains a blank grant.")
                fixed[category].append(block)
                continue
            if not isinstance(block, dict):
                raise SourceRepairError("A proficiency source has a malformed grant block.")
            for key, value in block.items():
                if not isinstance(key, str) or not key.strip():
                    raise SourceRepairError("A proficiency source contains a blank grant name.")
                if key == "ifAlreadyProficient" and identity == "background" and category == "languages":
                    from .character_language_choices import conditional_language
                    rule = conditional_language(block)
                    slots.append({"owner": identity, "category": category,
                                  "options": rule["options"], "language_condition": rule["condition"]})
                    continue
                if value is True and key not in {"any", "anyTool", "anyArtisansTool", "anyStandard", "anyGamingSet", "anyMusicalInstrument", "choose"}:
                    fixed[category].append(builder._humanize_proficiency_value(key, category=category))
                    continue
                if key == "choose":
                    if not isinstance(value, dict) or set(value) - {"from", "count", "amount"}:
                        raise SourceRepairError("A proficiency choice needs an exact supported source domain.")
                    domain, count = value.get("from"), value.get("count", 1)
                    if value.get("amount", 1) != 1:
                        raise SourceRepairError("A proficiency choice has an unsupported grant amount.")
                elif key in {"any", "anyTool"} and category in domains:
                    domain, count = domains[category], value
                elif key == "anyStandard" and category == "languages":
                    domain, count = STANDARD_LANGUAGE_OPTIONS, value
                elif key == "anyGamingSet" and category == "tools":
                    domain, count = gaming, value
                elif key == "anyArtisansTool" and category == "tools":
                    domain = [row["value"] for row in builder._tool_proficiency_options(
                        item_catalog or {}, artisan_only=True)]
                    count = value
                elif key == "anyMusicalInstrument" and identity == "background" and category == "tools":
                    # The shared native instrument contract owns its typed INS
                    # choices; a static tool-name domain cannot authenticate them.
                    continue
                else:
                    raise SourceRepairError("A proficiency source contains an unsupported choice family.")
                if (type(count) is not int or not 0 <= count <= 18 or not isinstance(domain, list)
                        or not domain or len(domain) > 128
                        or any(not isinstance(name, str) or not name.strip() or not 1 <= len(name) <= 160 for name in domain)):
                    raise SourceRepairError("A proficiency choice exceeds its bounded source domain.")
                labels = [builder._humanize_proficiency_value(name, category=category) for name in domain]
                for _ in range(count):
                    slots.append({"owner": identity, "category": category, "options": labels})

    for identity, entry in owners:
        if entry.entry_type == "feat":
            continue  # Existing feat choice fields/extractors own these grants.
        for block in entry.metadata.get("communication_proficiencies") or []:
            fixed["languages"] += [builder._humanize_proficiency_value(name, category="languages") for name in block]
        if entry.entry_type in {"classfeature", "subclassfeature"}:
            from .character_feature_proficiency_grants import contract
            feature_fixed, feature_slots = contract(entry, item_catalog=item_catalog)
            for category, names in feature_fixed.items():
                fixed[category].extend(names)
            slots.extend({**slot, "owner": identity} for slot in feature_slots)
            continue
        metadata = dict(entry.metadata or {})
        if identity == "background":
            builder._background_instrument_count(entry)
        if identity == "class":
            for category, extractor in (("armor", builder._extract_class_armor_proficiencies),
                                        ("weapons", source_weapon_labels)):
                fixed[category] += extractor(entry)
            starting = dict(metadata.get("starting_proficiencies") or {})
            add(identity, "skills", starting.get("skills"))
            add(identity, "tools", starting_grant(metadata, "tools"))
        for category, fields in {"skills": ("skill_proficiencies",), "tools": ("tool_proficiencies",),
                "languages": ("languages", "language_proficiencies"),
                "armor": ("armor_proficiencies",), "weapons": ("weapon_proficiencies",)}.items():
            for field in fields:
                add(identity, category, metadata.get(field))
    return fixed, slots


def choice_fields(definition, owners, values, *, item_catalog=None, service=None):
    _fixed, slots = grant_contract(definition, owners, item_catalog=item_catalog)
    fields = []
    for index, slot in enumerate(slots):
        name = f"feature_proficiency_{index}"
        condition = slot.get("condition") or slot.get("language_condition")
        fields.append({"name": name, "label": f"{slot['owner']} {slot['category']} choice {index + 1}",
            "help_text": ("Confirm whether you already had " + condition
                          + " when this feature was acquired. A replacement needs an independently owned prior proficiency."
                          if condition else "Confirm this retained choice and its current source owner."),
            "options": [{"label": "Unresolved retained choice — no grant issued", "value": f"__unresolved_{index}__"}]
                       + ([{"label": "Gain " + condition + " (not previously proficient)", "value": "__grant__"}]
                          if condition else [])
                       + [{"label": label, "value": label} for label in slot["options"]],
            "selected": str(values.get(name) or ""),
            "group_key": f"reconstruction:{slot['owner']}:{slot['category']}", "kind": slot["category"]})
    for identity, entry in owners:
        if identity != "class":
            continue
        from . import character_builder as builder
        for index, option in enumerate(builder._class_weapon_proficiency_contract(entry, strict=True)[1]):
            name = f"feature_optional_weapon_{index}"
            label = builder._humanize_proficiency_value(option, category="weapons")
            rule = optional_weapon_rule(definition, entry, option, service)
            fields.append({"name": name, "label": entry.title + " optional " + label,
                "help_text": ("Manager decision for this baseline: confirm campaign permission and every current source condition. Existing labels and equipment do not establish permission. Current rule: " + rule["text"]
                              if rule else "The exact governing optional rule is unavailable or ambiguous; retain this observation unqualified."),
                "options": [{"label": "Keep unqualified; permission or conditions unresolved", "value": "__unresolved_optional__"}]
                           + ([{"label": "Authorize " + label + " under this current rule and confirm its conditions", "value": rule["decision"]}] if rule else []),
                "selected": str(values.get(name) or ""), "group_key": "reconstruction:class:optional_weapons", "kind": "weapon"})
    return fields


def optional_weapon_rule(definition, class_entry, option, service):
    """Closed source relation for the supported clause, not a title inference.

    Other classes/homebrew need an explicit supported relation. A title-only
    match or an unmatched progression extra cannot acquire this authority.
    """
    from copy import deepcopy
    from .character_profile import profile_class_rows
    from .character_builder_equipment import _systems_ref_from_entry
    from .character_skill_adoptions import digest
    from . import character_builder as builder
    class_key = "dnd-5e|class|tce|artificer"
    rule_key = "dnd-5e|classfeature|tce|optionalrulefirearmproficiency-artificer-tce-1"
    if (definition is None or definition.system != "DND-5E" or service is None
            or option != "firearms" or class_entry.entry_key != class_key):
        return None
    rows = profile_class_rows(definition.profile)
    if (len(rows) != 1 or not rows[0].get("row_id")
            or type(rows[0].get("level")) is not int or not 1 <= rows[0]["level"] <= 20
            or rows[0].get("systems_ref") != _systems_ref_from_entry(class_entry)):
        return None
    current = service.get_entry_for_campaign(definition.campaign_slug, class_key)
    rule = service.get_entry_for_campaign(definition.campaign_slug, rule_key)
    if (current is None or current != class_entry or current.entry_type != "class"
            or type(current.body) is not dict
            or current.library_slug != "DND-5E" or current.source_id != "TCE"
            or rule is None or rule.entry_key != rule_key or rule.entry_type != "classfeature"
            or rule.library_slug != current.library_slug or rule.source_id != current.source_id
            or not service.is_entry_enabled_for_campaign(definition.campaign_slug, current)
            or not service.is_entry_enabled_for_campaign(definition.campaign_slug, rule)
            or type(rule.metadata) is not dict or type(rule.body) is not dict
            or rule.metadata.get("class_name") != current.title
            or rule.metadata.get("class_source") != current.source_id
            or type(rule.metadata.get("level")) is not int or rule.metadata["level"] != 1):
        return None
    raw = current.body.get("feature_progression")
    if type(raw) is not list:
        return None
    declared = [group for group in raw if isinstance(group, dict) and type(group.get("entries")) is list
                for label in group["entries"] if label == rule.title]
    if len(declared) != 1 or declared[0].get("name") != "Level 1":
        return None
    progression = service.build_class_feature_progression_for_class_entry(
        definition.campaign_slug, current, include_embedded_cards=False)
    if type(progression) is not list:
        return None
    members = [(group, member) for group in progression if isinstance(group, dict) and type(group.get("feature_rows")) is list
               for member in group["feature_rows"] if isinstance(member, dict)
               and getattr(member.get("entry"), "entry_key", None) == rule_key]
    if (len(members) != 1 or members[0][0].get("level") != 1
            or members[0][1].get("is_progression_spine") is not True
            or members[0][1].get("entry") != rule):
        return None
    text = builder._flatten_entry_markdown(rule.body.get("entries")).strip()
    if not text:
        return None
    basis = {"class_row_id": rows[0]["row_id"], "class_ref": _systems_ref_from_entry(current),
             "option": option, "membership": {"level": 1, "label": rule.title},
             "rule_ref": _systems_ref_from_entry(rule),
             "rule_metadata": deepcopy(rule.metadata), "rule_body": deepcopy(rule.body)}
    return {"basis": basis, "text": text, "decision": "authorize:" + option + ":" + digest(basis)}


def optional_weapon_grants(definition, owners, service, *, include_basis=False):
    """An explicit manager Review decision; never a fixed-class fallback."""
    return _optional_weapon_inputs(definition, owners, service, include_basis=include_basis)[0]


def _optional_weapon_inputs(definition, owners, service, *, include_basis=False, capture_basis=False):
    """Same original decision loop; native validation can retain both outputs."""
    from . import character_builder as builder
    from .repository import normalize_lookup
    frame = definition.source.get("native_reconstruction_choices") or {}
    choices = frame.get("choices", {})
    selected = choices.get("reconstruction:class:optional_weapons", [])
    classes = [entry for identity, entry in owners if identity == "class"]
    options = builder._class_weapon_proficiency_contract(classes[0], strict=True)[1] if len(classes) == 1 else []
    if not selected:
        return [], []  # Older frames retain their unqualified observation.
    if type(selected) is not list or len(selected) != len(options):
        raise SourceRepairError("The optional class proficiency declaration changed; review it again.")
    result, bases = [], []
    observed = {normalize_lookup(name) for name in definition.proficiencies.get("weapons", [])}
    for index, (value, option) in enumerate(zip(selected, options)):
        if frame.get("inputs", {}).get(f"feature_optional_weapon_{index}") != value:
            raise SourceRepairError("Optional proficiency needs its explicit reviewed manager input.")
        if value == "__unresolved_optional__":
            continue
        label = builder._humanize_proficiency_value(option, category="weapons")
        rule = optional_weapon_rule(definition, classes[0], option, service)
        if (rule is None or value != rule["decision"] or normalize_lookup(label) not in observed):
            raise SourceRepairError("Optional qualification needs an existing observation and a fresh decision on the exact governing rule.")
        result.append(rule["basis"] if include_basis else label)
        if capture_basis:
            bases.append(rule["basis"])
    return result, bases


def refresh_continuation_choices(definition, service, *, elective_witnesses=()):
    """Keep validated selections and make genuinely new slots explicit.

    A current native advance may introduce an owner whose supported generic
    tool/language choice has no selection in the older reconstruction frame.
    Record the missing slot; never infer it from a raw label or another owner.
    This changes no proficiency observation or original input/history record.
    """
    from copy import deepcopy
    from .character_models import CharacterDefinition
    from .character_builder_equipment import _systems_ref_from_entry
    from . import character_builder as builder
    from .repository import normalize_lookup

    frame = definition.source.get("native_reconstruction_choices")
    if not isinstance(frame, dict):
        return definition
    payload = deepcopy(definition.to_dict())
    frame = deepcopy(frame)
    from .character_language_electives import outcome_rows
    outcome_positions = {(row["owner_id"], "languages", row["position"]) for row in outcome_rows(definition)}
    owners = current_owners(definition, service)
    from .character_read_foundation import read_item_catalog_for_definition
    catalog = read_item_catalog_for_definition(definition, systems_service=service, campaign_page_records=[])
    _fixed, slots = grant_contract(definition, owners, item_catalog=catalog)
    counts = {}
    refreshed = {}
    for index, slot in enumerate(slots):
        group = f"reconstruction:{slot['owner']}:{slot['category']}"
        position = counts.get(group, 0)
        previous = frame.get("choices", {}).get(group, [])
        if not isinstance(previous, list):
            raise SourceRepairError("A retained native proficiency choice has an invalid owner frame.")
        marker = f"__unresolved_{index}__"
        if position < len(previous):
            value = previous[position]
            value = (marker if str(value).startswith("__unresolved_")
                     and (slot["owner"], slot["category"], position) not in outcome_positions else value)
        else:
            # Existing native forms use singular choice family names. Only a
            # selection already carried by that validated form can fill a slot.
            family = {"languages": "language", "tools": "tool", "skills": "skill"}.get(slot["category"], slot["category"])
            native_family = (f"grant_{slot['category']}_{slot['feature_index']}" if "feature_index" in slot else family)
            selected = frame.get("choices", {}).get(f"feature:{slot['owner']}:{native_family}", [])
            native_position = 0 if "feature_index" in slot else position
            value = selected[native_position] if isinstance(selected, list) and native_position < len(selected) else marker
            labels = (definition.proficiencies.get(slot["category"], []) if slot["category"] != "skills" else
                      [row.get("name") for row in definition.skills if row.get("proficiency_level") in {"proficient", "expertise"}])
            label = slot["condition"] if slot.get("condition") and value == "__grant__" else value
            if ((normalize_lookup(value) not in {normalize_lookup(name) for name in slot["options"]}
                     and not (slot.get("condition") and value == "__grant__"))
                    or normalize_lookup(label) not in {normalize_lookup(name) for name in labels}):
                value = marker
        refreshed.setdefault(group, []).append(value)
        counts[group] = position + 1
    for group, previous in frame.get("choices", {}).items():
        if (group.startswith("reconstruction:") and ":weapon_mapping_" not in group
                and group != "reconstruction:class:optional_weapons"):
            if not isinstance(previous, list) or len(previous) > counts.get(group, 0):
                raise SourceRepairError("A retained source choice changed shape; use a new reconstruction review.")
    frame.setdefault("choices", {}).update(refreshed)
    frame["proficiency_owners"] = [{"owner_id": identity, "systems_ref": _systems_ref_from_entry(entry),
        "grant_categories": [category for category, fields in {
            "skills": ("skill_proficiencies", "expertise"),
            "tools": ("tool_proficiencies", "expertise"),
            "languages": ("languages", "language_proficiencies", "communication_proficiencies"),
            "tool_expertise": ("expertise",), "armor": ("armor_proficiencies",),
            "weapons": ("weapon_proficiencies",)}.items()
            if any(entry.metadata.get(key) for key in fields)
            or starting_grant(entry.metadata, category)
            or category in {"skills", "tools", "tool_expertise"} and builder._supported_feature_expertise_blocks(entry)]}
        for identity, entry in owners]
    payload["source"]["native_reconstruction_choices"] = frame
    candidate = CharacterDefinition.from_dict(payload)
    frame["unresolved_proficiencies"] = validate_current(candidate, service, elective_witnesses=elective_witnesses)
    payload["source"]["native_reconstruction_choices"] = frame
    return CharacterDefinition.from_dict(payload)


def validate_current(definition, service, *, elective_witnesses=(), skill_adoption_draft=None, feature_grant_draft=None,
                     _current_inputs=None):
    from . import character_builder as builder
    from .repository import normalize_lookup
    owners = current_owners(definition, service)
    from .character_read_foundation import read_item_catalog_for_definition
    catalog = read_item_catalog_for_definition(definition, systems_service=service, campaign_page_records=[])
    fixed, slots = grant_contract(definition, owners, item_catalog=catalog)
    optional_weapons_invalid = False
    optional_basis = []
    try:
        if _current_inputs is None:
            fixed["weapons"] += optional_weapon_grants(definition, owners, service)
        else:
            _current_inputs.check(definition, service)
            labels, optional_basis = _optional_weapon_inputs(definition, owners, service, capture_basis=True)
            fixed["weapons"] += labels
    except (SourceRepairError, ValueError, TypeError, KeyError):
        # A stale optional decision must not invalidate unrelated language,
        # armor or tool ownership. The strict form already rejects stale picks.
        optional_weapons_invalid = True
    from .character_feature_proficiency_grants import resolve_reconstruction
    resolve_reconstruction(definition, service, elective_witnesses, prepared=feature_grant_draft, owners=owners, slots=slots)
    from .character_skill_adoptions import resolve as resolve_skill_adoptions
    resolve_skill_adoptions(definition, service, elective_witnesses,
        owners=owners, slots=slots, prepared=skill_adoption_draft)
    choices = dict(definition.source["native_reconstruction_choices"].get("choices") or {})
    # Only the selected species can prove this bounded starting-background
    # prerequisite. Later languages or the observed total cannot supply origin.
    conditional_languages = [slot for slot in slots if slot.get("language_condition")]
    prior_languages = []
    species_slots_complete = True
    if conditional_languages:
        species = [(identity, entry) for identity, entry in owners if identity == "species"]
        species_fixed, species_slots = grant_contract(definition, species, item_catalog=catalog)
        prior_languages = list(species_fixed["languages"])
        language_slots = [slot for slot in species_slots if slot["category"] == "languages"]
        selected = choices.get("reconstruction:species:languages", [])
        species_slots_complete = (type(selected) is list and len(selected) == len(language_slots)
            and all(value in slot["options"] for value, slot in zip(selected, language_slots)))
        if species_slots_complete:
            prior_languages += selected
    from .character_reconstruction_instruments import current_choice
    instrument_names, instrument_basis = current_choice(definition, service)
    fixed["tools"] += instrument_names
    from .character_language_electives import resolve_outcomes
    try:
        elective_outcomes = resolve_outcomes(definition, service, elective_witnesses,
            owners=owners, slots=slots)
        elective_invalid = False
    except (SourceRepairError, ValueError, TypeError, KeyError):
        elective_outcomes, elective_invalid = {}, True
    selections = [{"entry": entry, "instance_key": identity} for identity, entry in owners if entry.entry_type == "feat"]
    for category, extractor in (("skills", builder._extract_feat_skill_proficiencies),
            ("tools", builder._extract_feat_tool_proficiencies), ("languages", builder._extract_feat_language_proficiencies),
            ("armor", builder._extract_feat_armor_proficiencies), ("weapons", builder._extract_feat_weapon_proficiencies)):
        fixed[category] += extractor(selections, choices)
    counts, unresolved = {}, set()
    if optional_weapons_invalid:
        unresolved.add("weapons")
    selected_names = {category: {normalize_lookup(name) for name in names} for category, names in fixed.items()}
    actual_names = {category: {normalize_lookup(name) for name in definition.proficiencies.get(category, [])}
                    for category in fixed if category != "skills"}
    actual_names["skills"] = {normalize_lookup(row["name"]) for row in definition.skills
                             if row.get("proficiency_level") in {"proficient", "expertise"}}
    for index, slot in enumerate(slots):
        group = f"reconstruction:{slot['owner']}:{slot['category']}"
        position = counts.get(group, 0)
        values = choices.get(group)
        if not isinstance(values, list) or position >= len(values):
            raise SourceRepairError("Confirm every current proficiency choice against its exact source owner.")
        outcome = elective_outcomes.get((slot["owner"], position)) if slot["category"] == "languages" else None
        if outcome is not None and outcome["outcome"] == "declined":
            pass  # This exact authenticated optional slot consumes no grant.
        elif outcome is not None and outcome["outcome"] in {"selected", "adopted"}:
            selected = normalize_lookup(outcome["selected_value"])
            if selected not in actual_names["languages"] or selected in selected_names["languages"]:
                raise SourceRepairError("A decided language must have one unique retained source owner.")
            selected_names["languages"].add(selected)
            fixed["languages"].append(outcome["selected_value"])
        elif values[position] == f"__unresolved_{index}__":
            unresolved.add(slot["category"])
        elif (normalize_lookup(values[position]) in {normalize_lookup(name) for name in slot["options"]}
              or (slot.get("condition") or slot.get("language_condition")) and values[position] == "__grant__"):
            condition = slot.get("condition") or slot.get("language_condition")
            label = condition if condition and values[position] == "__grant__" else values[position]
            if slot.get("language_condition"):
                already = normalize_lookup(condition) in {normalize_lookup(name) for name in prior_languages}
                if (not species_slots_complete or (values[position] == "__grant__") == already):
                    raise SourceRepairError("Confirm the prior species language before choosing the background grant or replacement.")
            selected = normalize_lookup(label)
            if selected not in actual_names[slot["category"]]:
                raise SourceRepairError("A reconstruction choice must identify a retained proficiency; leave an unknown choice unresolved.")
            if selected in selected_names[slot["category"]]:
                raise SourceRepairError("Distinct source choice slots cannot claim the same retained proficiency.")
            selected_names[slot["category"]].add(selected)
            fixed[slot["category"]].append(label)
        else:
            raise SourceRepairError("A retained proficiency choice does not belong to its source domain.")
        counts[group] = position + 1
    if elective_invalid:
        unresolved.add("languages")
    if any(len(choices[group]) != count or len({normalize_lookup(x) for x in choices[group]}) != count
           for group, count in counts.items()):
        raise SourceRepairError("A source-owned proficiency choice is duplicated or incomplete.")
    actual = {category: {normalize_lookup(name) for name in definition.proficiencies.get(category, [])}
              for category in fixed if category != "skills"}
    actual["skills"] = {normalize_lookup(row["name"]) for row in definition.skills
                        if row.get("proficiency_level") in {"proficient", "expertise"}}
    for category, names in fixed.items():
        if actual[category] != {normalize_lookup(name) for name in names}:
            # Preserve an incomplete/manual observation without issuing its
            # dependent grant. Never complete it from another target or totals.
            unresolved.add(category)
    unresolved_expertise = {group.split(":")[1] for group, values in choices.items()
                           if group.endswith(":expertise") and any(str(value).startswith("__unresolved_") for value in values)}
    if unresolved_expertise:
        unresolved.update({"skills", "tool_expertise"})
    feature_selections = [{"entry": entry, "instance_key": identity} for identity, entry in owners
                          if entry.entry_type != "feat" and identity not in unresolved_expertise]
    selections = [selection for selection in selections if selection["instance_key"] not in unresolved_expertise]
    from .character_feature_proficiency_grants import automatic, automatic_history
    adopted = {row["owner_id"] for row in automatic_history(definition)}
    from .character_feature_proficiency_grants import native_records_for_owner
    adopted.update(owner for owner, entry in owners if automatic(entry) and len(native_records_for_owner(definition, owner, entry)) == 1)
    for selection in feature_selections:
        if automatic(selection["entry"]) and selection["instance_key"] not in adopted:
            selection["automatic_tools"] = False
            unresolved.add("tool_expertise")
    base = {normalize_lookup(row["name"]): "proficient" if normalize_lookup(row["name"]) in actual["skills"] else "none"
            for row in definition.skills}
    levels = builder._apply_feature_expertise_to_skill_proficiency_levels(base,
        feature_selections=feature_selections, selected_choices=choices, strict=True)
    levels = builder._apply_feat_expertise_to_skill_proficiency_levels(levels,
        feat_selections=selections, selected_choices=choices, strict=True)
    for effect in builder._extract_character_effect_keys(definition.features):
        for target in builder._skill_targets_for_effect_key(effect):
            levels[target] = builder._max_skill_proficiency_level(levels.get(target), "half_proficient")
    if "skills" not in unresolved and any(row.get("proficiency_level") != levels[normalize_lookup(row["name"])] for row in definition.skills):
        raise SourceRepairError("Expertise and half proficiency need their explicit current source choices.")
    tools = builder._apply_feature_expertise_to_tool_proficiencies([], available_tool_proficiencies=definition.proficiencies.get("tools", []),
        feature_selections=feature_selections, selected_choices=choices, strict=True)
    expected_tools = {normalize_lookup(name) for name in tools}
    observed_tools = {normalize_lookup(name) for name in definition.proficiencies.get("tool_expertise", [])}
    if "tool_expertise" not in unresolved and expected_tools != observed_tools:
        if adopted:
            # Adoption authenticates an ongoing rule, not a permanently frozen
            # output list. Current projection adds later qualified tools.
            if not observed_tools <= expected_tools:
                unresolved.add("tool_expertise")
        else:
            raise SourceRepairError("Tool expertise does not match the current qualified feature choices.")
    if "tools" in unresolved:
        unresolved.add("tool_expertise")
    if _current_inputs is not None:
        _current_inputs.validated(optional_basis, instrument_basis)
    return sorted(unresolved)


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'validate_current',
    'current_owners',
    'grant_contract',
    'optional_weapon_grants',
    '_optional_weapon_inputs',
    'optional_weapon_rule',
    'source_weapon_labels',
    'starting_grant',
))
