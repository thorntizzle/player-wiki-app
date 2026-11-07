"""Current, non-entitling facets of exact selected Character parents.

Historical summary associations require independently recovered reconstruction
custody. A selected background's narrative is an ephemeral read projection.
Neither path supplies a second copy of its parent's mechanical grants.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .character_source_repair import SourceRepairError


FRAME_KEY = "parent_facet_mappings"
CUSTODY_KEY = "parent_facet_custody"
UNRESOLVED = "__unresolved_parent_facet__"
FACETS = {
    "class_hit_points": ("class", "Hit Points", ()),
    "class_proficiencies": ("class", "Proficiencies", ()),
    "species_languages": ("species", "Languages", ("languages", "language")),
    "species_ability": ("species", "Ability Score Increase", ("ability score increase",)),
    "species_skills": ("species", "Skills", ("skills", "skill")),
    "species_feat": ("species", "Feat", ("feat",)),
}
_REF_FIELDS = {"entry_key", "slug", "source_id", "entry_type", "title"}
_INERT_FIELDS = {"id", "name", "category", "source", "description_markdown",
                 "activation_type", "tracker_ref", "systems_ref", "class_row_id"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def exact_ref(ref):
    return (type(ref) is dict and _REF_FIELDS <= set(ref)
            and not set(ref) - _REF_FIELDS - {"library_slug"}
            and all(isinstance(value, str) and value.strip() for value in ref.values()))


def inert(feature, role, *, linked=False):
    # This legacy parent is still consumed by the infusion assignment model.
    # A presentation facet cannot dispose of its mechanical prose dependency.
    from .character_artificer_infusions import ARTIFICER_INFUSIONS_FEATURE_KEY
    from .repository import normalize_lookup
    if isinstance(feature, dict) and normalize_lookup(feature.get("name")) == ARTIFICER_INFUSIONS_FEATURE_KEY:
        return False
    category = {"class": "class_feature", "species": "species_trait",
                "background": "background_feature"}[role]
    return (type(feature) is dict and isinstance(feature.get("id"), str) and bool(feature["id"])
            and isinstance(feature.get("name"), str) and bool(feature["name"].strip())
            and feature.get("category") == category and feature.get("activation_type") == "passive"
            and (feature.get("description_markdown") is None or isinstance(feature.get("description_markdown"), str))
            and (feature.get("source") is None or isinstance(feature.get("source"), str))
            and not feature.get("tracker_ref") and not feature.get("page_ref")
            and (exact_ref(feature.get("systems_ref")) if linked else not feature.get("systems_ref"))
            and all(value in (None, "", [], {}) for key, value in feature.items() if key not in _INERT_FIELDS))


def parent(profile, role, class_row_id=""):
    if role == "class":
        from .character_profile import profile_class_rows
        rows = [row for row in profile_class_rows(profile) if row.get("row_id") == class_row_id]
        return rows[0].get("systems_ref") if len(rows) == 1 else None
    if role not in {"species", "background"} or class_row_id or profile.get(role + "_page_ref"):
        return None
    return profile.get(role + "_ref")


def resolve_parent(campaign, profile, role, class_row_id, service):
    ref = parent(profile, role, class_row_id)
    if not exact_ref(ref) or service is None:
        return None
    entry = service.get_entry_for_campaign(campaign, ref["entry_key"])
    enabled = getattr(service, "is_entry_enabled_for_campaign", None)
    types = {"class": {"class"}, "species": {"race", "subrace"}, "background": {"background"}}
    if (entry is None or entry.entry_type not in types[role]
            or not callable(enabled) or not enabled(campaign, entry)
            or any(value != getattr(entry, key, None) for key, value in ref.items())):
        return None
    return entry


def _markdown(value):
    from .character_builder import _flatten_entry_markdown
    return _flatten_entry_markdown(value)


def _proficiency_values(values):
    if not isinstance(values, list):
        return None
    if not values:
        return "None"
    result = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value)
        elif type(value) is dict and set(value) == {"choose"}:
            choice = value["choose"]
            if (type(choice) is not dict or set(choice) != {"count", "from"}
                    or type(choice["count"]) is not int or choice["count"] < 1
                    or type(choice["from"]) is not list or not choice["from"]
                    or any(not isinstance(item, str) or not item for item in choice["from"])
                    or choice["count"] > len(set(choice["from"]))):
                return None
            result.append(f"Choose {choice['count']} from " + ", ".join(choice["from"]))
        else:
            return None
    return "; ".join(result)


def _ability_rule(blocks):
    from .character_builder_constants import ABILITY_LABELS
    if not isinstance(blocks, list) or not blocks:
        return None
    alternatives = []
    for block in blocks:
        if type(block) is not dict or not block or set(block) - set(ABILITY_LABELS) - {"choose"}:
            return None
        parts = []
        for key in ABILITY_LABELS:
            if key in block:
                if type(block[key]) is not int or not 1 <= block[key] <= 2:
                    return None
                parts.append(f"Increase {ABILITY_LABELS[key]} by {block[key]}")
        if "choose" in block:
            choice = block["choose"]
            if (type(choice) is not dict or set(choice) - {"from", "count", "amount"}
                    or not {"from", "count"} <= set(choice)
                    or type(choice["from"]) is not list or not choice["from"]
                    or any(key not in ABILITY_LABELS for key in choice["from"])
                    or len(choice["from"]) != len(set(choice["from"]))
                    or type(choice["count"]) is not int or not 1 <= choice["count"] <= len(choice["from"])
                    or type(choice.get("amount", 1)) is not int or not 1 <= choice.get("amount", 1) <= 2):
                return None
            parts.append(f"Increase {choice['count']} different ability scores by {choice.get('amount', 1)}; choose from "
                         + ", ".join(ABILITY_LABELS[key] for key in choice["from"]))
        alternatives.append(". ".join(parts) + ".")
    return "\n\nOr: ".join(alternatives)


def current_facet(entry, selector):
    try:
        return _current_facet(entry, selector)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _current_facet(entry, selector):
    """Return one supported current clause; labels alone never supply ownership."""
    if selector not in FACETS or not isinstance(getattr(entry, "metadata", None), dict):
        return None
    role, title, labels = FACETS[selector]
    if entry.entry_type not in ({"class"} if role == "class" else {"race", "subrace"}):
        return None
    metadata, body = entry.metadata, dict(entry.body or {})
    if selector == "class_hit_points":
        die = metadata.get("hit_die")
        if (type(die) is not dict or set(die) != {"number", "faces"}
                or type(die["number"]) is not int or die["number"] != 1
                or type(die["faces"]) is not int or die["faces"] not in {6, 8, 10, 12}):
            return None
        text, location = f"Hit Die: {die['number']}d{die['faces']} per {entry.title} level.", "metadata.hit_die"
    elif selector == "class_proficiencies":
        profs, saves = metadata.get("starting_proficiencies"), metadata.get("proficiency")
        if (type(profs) is not dict or not profs or type(saves) is not list or not saves
                or any(value not in {"str", "dex", "con", "int", "wis", "cha"} for value in saves)
                or set(profs) - {"armor", "weapons", "tools", "toolProficiencies", "skills"}
                or any(_proficiency_values(profs[key]) is None for key in ("armor", "skills") if key in profs)):
            return None
        from . import character_builder as builder
        from .character_reconstruction_proficiencies import grant_contract
        # Use the mechanical typed tool precedence and bounded choice domains.
        # Optional weapons are presented as conditions, never fixed grants.
        fixed, slots = grant_contract(None, [("class", entry)])
        _, optional = builder._class_weapon_proficiency_contract(entry, strict=True)
        parts = []
        for category in ("armor", "weapons", "tools", "skills"):
            if category not in profs and not (category == "tools" and "toolProficiencies" in profs):
                continue
            values = list(fixed[category])
            for slot in slots:
                if slot["category"] == category:
                    values.append("Choose 1 from " + ", ".join(slot["options"]))
            if category == "weapons":
                values += ["Optional " + builder._humanize_proficiency_value(value, category="weapons")
                           + " (requires campaign permission and the source's conditions)" for value in optional]
            parts.append(category.title() + ": " + ("; ".join(values) if values else "None"))
        from .character_builder_constants import ABILITY_LABELS
        text = "Saving throw proficiencies: " + ", ".join(ABILITY_LABELS[value] for value in saves) + ".\n\n"
        text += "\n\n".join(parts)
        location = "metadata.starting_proficiencies+metadata.proficiency"
    elif selector == "species_ability":
        values = [metadata[key] for key in ("ability", "ability_bonuses") if metadata.get(key)]
        if not values or any(value != values[0] for value in values[1:]):
            return None
        text = _ability_rule(values[0])
        if text is None:
            return None
        location = "metadata.ability"
    else:
        keys = {"species_languages": ("languages", "language_proficiencies"),
                "species_ability": ("ability", "ability_bonuses"),
                "species_skills": ("skill_proficiencies",), "species_feat": ("feats",)}[selector]
        values = [metadata[key] for key in keys if metadata.get(key)]
        if not values or any(value != values[0] for value in values[1:]) or not isinstance(values[0], (dict, list)):
            return None
        if selector in {"species_languages", "species_skills"}:
            from .character_reconstruction_proficiencies import grant_contract
            try:
                fixed, slots = grant_contract(None, [("species", entry)])
                from .character_builder_constants import UNRESTRICTED_LANGUAGE_OPTIONS, SKILL_LABELS
                category = "languages" if selector == "species_languages" else "skills"
                vocabulary = UNRESTRICTED_LANGUAGE_OPTIONS if category == "languages" else list(SKILL_LABELS.values())
                if (any(value.casefold() not in {label.casefold() for label in vocabulary} for value in fixed[category])
                        or not fixed[category] and not any(slot["category"] == category for slot in slots)):
                    return None
            except (KeyError, TypeError, ValueError):
                return None
        elif selector == "species_feat":
            if (type(values[0]) is not list or not values[0]
                    or any(type(row) is not dict or set(row) != {"any"}
                           or type(row["any"]) is not int or not 1 <= row["any"] <= 4 for row in values[0])):
                return None
        entries = body.get("entries")
        if not isinstance(entries, list):
            return None
        matches = [(index, row) for index, row in enumerate(entries) if type(row) is dict
                   and str(row.get("name") or "").strip().casefold() in labels]
        if len(matches) != 1:
            return None
        index, row = matches[0]
        text, location = _markdown(row.get("entries")), f"body.entries[{index}]:{str(row['name']).strip().casefold()}"
    if not text.strip():
        return None
    return {"facet": selector, "label": title, "location": location, "description_markdown": text}


def background_facets(entry):
    if getattr(entry, "entry_type", None) != "background":
        return []
    from .character_builder import _extract_background_feature_entries
    try:
        entries = entry.body.get("entries")
        if not isinstance(entries, list):
            return []
        for row in entries:
            if not isinstance(row, dict) or not row.get("data"):
                continue
            data = row["data"]
            if not isinstance(data, dict):
                return []
            if data.get("isFeature") and (data["isFeature"] is not True
                    or row.get("type") != "entries" or not isinstance(row.get("name"), str) or not row["name"].strip()):
                return []
        rows = _extract_background_feature_entries(entry)
    except (AttributeError, KeyError, TypeError, ValueError):
        return []
    labels = [row["label"] for row in rows]
    if len(labels) != len(set(labels)):
        return []
    return [{"facet": "background_feature:" + row["label"], "label": row["label"],
             "location": "body.entries:isFeature:" + row["label"],
             "description_markdown": row["description_markdown"]} for row in rows]


def linked_companion_facet(feature, profile, entry):
    role = {"background": "background", "race": "species", "subrace": "species"}.get(getattr(entry, "entry_type", None))
    if (role is None or not inert(feature, role, linked=True)
            or feature["systems_ref"] != parent(profile, role)
            or feature.get("class_row_id") or feature.get("source") != entry.source_id
            or any(value != getattr(entry, key, None) for key, value in feature["systems_ref"].items())):
        return None
    facets = (background_facets(entry) if role == "background" else
              [facet for selector in FACETS if selector.startswith("species_")
               if (facet := current_facet(entry, selector)) is not None])
    matches = [facet for facet in facets if facet["label"] == feature["name"]]
    return matches[0] if len(matches) == 1 else None


def _features(definition):
    rows = list(definition.features or [])
    ids = [row.get("id") for row in rows if type(row) is dict]
    if len(ids) != len(rows) or any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
        raise SourceRepairError("Parent facets require unique retained feature identities.")
    return {row["id"]: row for row in rows}


def _field(identity):
    return "feature_parent_facet_" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def candidates(definition, feature, service):
    from .character_profile import profile_class_rows
    roles = [("class", row.get("row_id")) for row in profile_class_rows(definition.profile)] + [("species", "")]
    result = []
    for role, row_id in roles:
        if (not isinstance(row_id, str) or not inert(feature, role)
                or feature.get("class_row_id") not in (None, "", row_id)):
            continue
        entry = resolve_parent(definition.campaign_slug, definition.profile, role, row_id, service)
        if entry is None:
            continue
        for selector, (facet_role, _label, _aliases) in FACETS.items():
            if facet_role != role or (facet := current_facet(entry, selector)) is None:
                continue
            if any(linked_companion_facet(other, definition.profile, entry) == facet for other in definition.features):
                continue
            from .character_builder_equipment import _systems_ref_from_entry
            result.append({"schema_version": 1, "feature_id": feature["id"], "prior_feature": deepcopy(feature),
                "parent_role": role, "class_row_id": row_id,
                "systems_ref": _systems_ref_from_entry(entry),
                "facet": selector, "location": facet["location"]})
    return result


def choice_fields(definition, service, values):
    fields = []
    for identity, feature in _features(definition).items():
        options = candidates(definition, feature, service)
        if not options:
            continue
        name = _field(identity)
        fields.append({"name": name, "label": "Historical summary: " + feature["name"] + " (" + identity + ")",
            "help_text": "Explicitly associate this retained row with a current parent rule. Original text remains unchanged; no additional benefit is granted.",
            "options": [{"label": "Unresolved; retain source warning", "value": UNRESOLVED}, *[
                {"label": row["systems_ref"]["title"] + " (" + row["systems_ref"]["source_id"] + "): " + FACETS[row["facet"]][1],
                 "value": digest(row)} for row in options]],
            "selected": values.get(name, UNRESOLVED), "group_key": "reconstruction:parent_facet:" + identity,
            "kind": "parent_facet"})
    return fields


def compose_mappings(definition, service, values):
    result = []
    for identity, feature in _features(definition).items():
        options = candidates(definition, feature, service)
        if not options:
            continue
        selected = values.get(_field(identity), UNRESOLVED)
        if selected == UNRESOLVED:
            continue
        matches = [row for row in options if digest(row) == selected]
        if len(matches) != 1:
            raise SourceRepairError("Choose one exact supported parent facet or leave the historical row unresolved.")
        result.append(matches[0])
    prior = stored_mappings(definition)
    if any(row not in result for row in prior):
        raise SourceRepairError("Retain every prior parent-facet association; reconstruction cannot discard its history.")
    return result


def stored_mappings(definition):
    frame = definition.source.get("native_reconstruction_choices")
    rows = frame.get(FRAME_KEY, []) if isinstance(frame, dict) else []
    if not isinstance(rows, list) or len(rows) > 128:
        raise SourceRepairError("Parent facet evidence exceeds its supported bound.")
    features, seen, facets = _features(definition), set(), set()
    fields = {"schema_version", "feature_id", "prior_feature", "parent_role", "class_row_id", "systems_ref", "facet", "location"}
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or not isinstance(row["feature_id"], str) or row["feature_id"] in seen
                or not isinstance(row["facet"], str) or row["facet"] not in FACETS
                or row["parent_role"] != FACETS[row["facet"]][0]
                or not isinstance(row["class_row_id"], str) or not isinstance(row["location"], str) or not row["location"]
                or not exact_ref(row["systems_ref"]) or not inert(row["prior_feature"], row["parent_role"])
                or row["prior_feature"].get("id") != row["feature_id"]
                or features.get(row["feature_id"]) != row["prior_feature"]
                or parent(definition.profile, row["parent_role"], row["class_row_id"]) != row["systems_ref"]
                or row["prior_feature"].get("class_row_id") not in (None, "", row["class_row_id"])
                or dict(frame.get("inputs") or {}).get(_field(row["feature_id"])) != digest(row)):
            raise SourceRepairError("A parent facet association has no exact retained row, selected owner or explicit input.")
        key = (row["parent_role"], row["class_row_id"], row["facet"])
        if key in facets:
            raise SourceRepairError("A parent facet has duplicate retained summary associations.")
        seen.add(row["feature_id"])
        facets.add(key)
    return tuple(deepcopy(rows))


def validate_mappings(prior, candidate, service=None):
    mappings, old = stored_mappings(candidate), _features(prior)
    for row in mappings:
        if old.get(row["feature_id"]) != row["prior_feature"]:
            raise SourceRepairError("A parent facet association changed its historical feature.")
        if service is not None and resolve_mapping(candidate, row, service) is None:
            raise SourceRepairError("A selected current parent facet is missing or structurally changed.")
    return mappings


def resolve_mapping(definition, row, service):
    entry = resolve_parent(definition.campaign_slug, definition.profile, row["parent_role"], row["class_row_id"], service)
    facet = current_facet(entry, row["facet"]) if entry is not None else None
    if facet is None or facet["location"] != row["location"]:
        return None
    if any(linked_companion_facet(feature, definition.profile, entry) == facet for feature in definition.features):
        return None
    return facet


def custody(definition, origin, mappings):
    if not mappings:
        return ()
    return ({CUSTODY_KEY: {"schema_version": 1, "campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "mapping_digest": digest(list(mappings)), "mappings": deepcopy(list(mappings))}},)


def qualified_mappings(definition, service, witnesses):
    try:
        mappings = stored_mappings(definition)
        origin = definition.source.get("native_reconstruction")
        if not mappings or not isinstance(origin, dict) or origin.get("parent_facet_mapping_digest") != digest(list(mappings)):
            return {}
        expected = custody(definition, origin, mappings)[0]
        if not any(type(witness) is dict and witness == expected for witness in witnesses):
            return {}
        return {row["feature_id"]: {**facet, "systems_ref": deepcopy(row["systems_ref"]), "parent_summary": True}
                for row in mappings if (facet := resolve_mapping(definition, row, service)) is not None}
    except (KeyError, TypeError, ValueError):
        return {}


def presentation(definition, service, authority):
    """A presentation-only packet; never append these rows to a saved definition."""
    witnesses = []
    for raw in getattr(authority, "verified_numeric_actions", ()):
        try:
            witnesses.append(json.loads(raw))
        except (TypeError, ValueError):
            continue
    facets = qualified_mappings(definition, service, witnesses)
    facets = {key: value for key, value in facets.items() if authority.status_for("feature", key) == "VERIFIED"}
    projected = []
    species = None
    for feature in definition.features:
        if type(feature) is not dict or authority.status_for("feature", feature.get("id")) != "VERIFIED":
            continue
        ref = feature.get("systems_ref")
        if isinstance(ref, dict) and ref.get("entry_type") in {"race", "subrace"}:
            if species is None:
                species = resolve_parent(definition.campaign_slug, definition.profile, "species", "", service)
            facet = linked_companion_facet(feature, definition.profile, species) if species else None
            if facet:
                facets[feature["id"]] = {**facet, "systems_ref": deepcopy(ref), "parent_summary": True}
        elif isinstance(ref, dict) and ref.get("entry_type") == "subclass":
            from .character_subclass_companion import selected_subclass_companion_matches
            selected = service.get_entry_for_campaign(definition.campaign_slug, ref.get("entry_key", ""))
            if selected is not None and selected_subclass_companion_matches(
                    feature, definition.profile, selected, service, definition.campaign_slug):
                # The selected subclass is already in the profile. Only the
                # exact proved inert container is hidden, never its members.
                facets[feature["id"]] = {"systems_ref": deepcopy(ref), "parent_summary": True}
    entry = resolve_parent(definition.campaign_slug, definition.profile, "background", "", service)
    if entry is None:
        if definition.profile.get("background_ref"):
            projected.append({"id": "current-background:unavailable", "name": "Background feature unavailable",
                "category": "background_feature", "activation_type": "passive", "parent_facet_presentation": {
                    "description_markdown": "The selected background's current source is unavailable or needs repair.", "available": False}})
        return facets, projected
    current = background_facets(entry)
    for facet in current:
        matches = [row for row in definition.features if type(row) is dict
                   and linked_companion_facet(row, definition.profile, entry) == facet]
        if len(matches) == 1 and authority.status_for("feature", matches[0].get("id")) == "VERIFIED":
            facets[matches[0]["id"]] = {**facet, "systems_ref": deepcopy(definition.profile["background_ref"])}
        elif len(matches) == 0:
            projected.append({"id": "current-background:" + digest([entry.entry_key, facet["facet"]])[:24],
                "name": facet["label"], "category": "background_feature", "activation_type": "passive",
                "systems_ref": deepcopy(definition.profile["background_ref"]),
                "parent_facet_presentation": facet})
    if not current:
        projected.append({"id": "current-background:unavailable", "name": "Background feature unavailable",
            "category": "background_feature", "activation_type": "passive", "parent_facet_presentation": {
                "description_markdown": "The selected background has no unique supported current feature clause.", "available": False}})
    return facets, projected
