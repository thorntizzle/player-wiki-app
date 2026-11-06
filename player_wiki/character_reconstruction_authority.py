"""Target-local issuance and durable validation for native reconstruction.

Only the reviewed manager composer constructs PendingNativeReconstruction.
Stored markers are claims; only the matching actor/generation/audit join is a
durable witness. No new target, migration, or legacy publication is performed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .character_models import CharacterDefinition
from .character_source_repair import SourceRepairError


PROVENANCE = "native_reconstruction"


def _retained_reconstruction_item_mappings(prior, candidate):
    """Compare history from the publisher's exact prior pair; issue no authority.

    Only the guarded publisher supplies the prior record. Generation/audit and
    pending-operation custody remain the coordinator's independent obligations.
    An unrelated new choice must not reclassify an unchanged physical history.
    """
    from .character_reconstruction_items import stored_mappings
    origin = prior.source.get("native_reconstruction")
    if (not isinstance(origin, dict)
            or (prior.campaign_slug, prior.character_slug) != (candidate.campaign_slug, candidate.character_slug)
            or origin.get("campaign_slug") != prior.campaign_slug
            or origin.get("character_slug") != prior.character_slug
            or digest(candidate.source.get("native_reconstruction")) != digest(origin)):
        return ()
    before, after = stored_mappings(prior), stored_mappings(candidate)
    by_id = {row["item_id"]: row for row in after}
    if any(row["item_id"] not in by_id or digest(by_id[row["item_id"]]) != digest(row) for row in before):
        raise SourceRepairError("Retained physical source history cannot be changed or dropped.")
    return tuple(deepcopy(before))


def reconstruction_source_links(definition, *, require_origin=True, retained=False,
                                retained_item_mappings=()):
    """Type only exact retained owners; this is structure, never an audit witness.

    Composer, issuer, historical validator and publisher use the same paths.
    Current source access and subclass metadata are proved by the publisher;
    target-local issuance and durable custody remain separate requirements.
    ``retained`` describes other owners in an unchanged committed frame. Item
    history instead uses exact entries compared against the publisher's prior
    pair, independently of new choices. Neither supplies current mechanics or
    admits a new origin. No serialized candidate flag supplies either context.
    """
    from .character_profile import profile_class_rows
    from .character_source_repair import _sha256_hex
    from .character_reconstruction_items import stored_mappings
    if not isinstance(retained_item_mappings, tuple):
        raise SourceRepairError("Retained item evidence needs the publisher's exact prior context.")
    retained_items = {row["item_id"]: row for row in retained_item_mappings}
    links = {}
    rows = profile_class_rows(definition.profile)
    features = [row for row in definition.features if isinstance(row, dict)]
    ids = [row.get("id") for row in features]

    def exact(ref):
        fields = {"entry_key", "slug", "source_id", "entry_type", "title"}
        if (not isinstance(ref, dict) or not fields <= set(ref)
                or set(ref) - fields - {"library_slug"}
                or any(not isinstance(value, str) or not value.strip() for value in ref.values())):
            raise SourceRepairError("Reconstruction evidence needs an exact typed source identity.")
        return ref

    # The container is retained evidence, not an attained feature grant. Bind
    # its raw payload to the selected row; the real source proof repeats the
    # complete inert-companion predicate with resolved class/subclass records.
    for index, feature in enumerate(definition.features):
        if not isinstance(feature, dict):
            continue
        ref = feature.get("systems_ref")
        if not isinstance(ref, dict) or ref.get("entry_type") != "subclass":
            continue
        exact(ref)
        inert_fields = {"id", "name", "category", "source", "description_markdown",
                       "activation_type", "tracker_ref", "systems_ref"}
        if (feature.get("category") != "class_feature" or feature.get("name") != ref["title"]
                or feature.get("activation_type") != "passive"
                or feature.get("description_markdown") not in (None, "") or feature.get("tracker_ref")
                or feature.get("source") not in (None, "", ref["source_id"])
                or any(value not in (None, "", [], {}) for key, value in feature.items() if key not in inert_fields)):
            raise SourceRepairError("The retained subclass container has independent mechanics or content.")
        selected = [(i, row) for i, row in enumerate(rows) if row.get("subclass_ref") == ref]
        if (not isinstance(feature.get("id"), str) or not feature["id"]
                or ids.count(feature["id"]) != 1 or len(selected) != 1):
            raise SourceRepairError("The retained subclass container has no unique selected owner.")
        parent_index, parent = selected[0]
        if exact(parent.get("systems_ref"))["entry_type"] != "class":
            raise SourceRepairError("The retained subclass container has no typed class parent.")
        links[("definition", "features", index, "systems_ref")] = {
            "kind": "subclass", "parent": f"definition.profile.classes[{parent_index}].systems_ref",
            "companion": deepcopy(feature)}

    acquisitions = definition.source.get("native_feature_proficiency_choices", [])
    if type(acquisitions) is not list or len(acquisitions) > 128:
        raise SourceRepairError("Native feature proficiency acquisitions are malformed.")
    for index, acquisition in enumerate(acquisitions):
        if type(acquisition) is not dict:
            raise SourceRepairError("Native feature acquisition needs a typed source.")
        ref = exact(acquisition.get("systems_ref"))
        matching = [feature for feature in features if feature.get("systems_ref") == acquisition.get("systems_ref")
                    and feature.get("class_row_id") == acquisition.get("class_row_id")]
        if ref["entry_type"] not in {"classfeature", "subclassfeature"} or len(matching) != 1:
            raise SourceRepairError("Native proficiency acquisition needs its exact class feature member.")
        links[("definition", "source", "native_feature_proficiency_choices", index, "systems_ref")] = {"kind": "feature"}
    frame = definition.source.get("native_reconstruction_choices")
    if frame is None:
        return links
    if (definition.system != "DND-5E" or not isinstance(frame, dict)
            or type(frame.get("schema_version")) is not int or frame["schema_version"] != 1
            or not isinstance(frame.get("inputs"), dict) or not isinstance(frame.get("choices"), dict)
            or len(rows) != 1):
        raise SourceRepairError("The reconstruction evidence frame is malformed.")
    if require_origin:
        origin = definition.source.get("native_reconstruction")
        if (not isinstance(origin, dict) or type(origin.get("schema_version")) is not int
                or origin["schema_version"] != 1
                or origin.get("campaign_slug") != definition.campaign_slug
                or origin.get("character_slug") != definition.character_slug
                or type(origin.get("actor_user_id")) is not int or origin["actor_user_id"] < 1
                or type(origin.get("prior_generation")) is not int or origin["prior_generation"] < 1
                or not _sha256_hex(origin.get("action_id"))
                or origin.get("input_digest") != digest(frame["inputs"])):
            raise SourceRepairError("Reconstruction evidence has no matching target-local origin claim.")
    owners = {"class": (rows[0].get("systems_ref"), "class"),
              "species": (definition.profile.get("species_ref"), "species"),
              "background": (definition.profile.get("background_ref"), "background")}
    for feature in features:
        identity, ref = feature.get("id"), feature.get("systems_ref")
        if not isinstance(identity, str) or not identity or not isinstance(ref, dict):
            continue
        if ids.count(identity) != 1 or identity in owners:
            raise SourceRepairError("Reconstruction evidence has an ambiguous retained owner.")
        entry_type = exact(ref)["entry_type"]
        kind = {"race": "species", "subrace": "species", "species": "species", "background": "background"}.get(entry_type)
        if entry_type in {"classfeature", "subclassfeature", "feature", "feat", "optionalfeature"}:
            kind = "feature"
        if kind:
            owners[identity] = (ref, kind)

    def owned(row, path, *, ability=False, current=False):
        identity = row.get("owner_id")
        if retained and not current:
            if not isinstance(identity, str) or not identity:
                raise SourceRepairError("Retained reconstruction evidence has no owner identity.")
            ref = exact(row.get("systems_ref"))
            kind = {"class": "class", "species": "species", "background": "background"}.get(
                identity, "reconstruction_feature")
            if ability and identity not in {"class", "species"} and ref["entry_type"] != "feat":
                raise SourceRepairError("A retained ability layer has no permanent input owner.")
            links[(*path, "systems_ref")] = {"kind": kind}
            return
        if not isinstance(identity, str) or identity not in owners:
            raise SourceRepairError("Reconstruction evidence has no retained source owner.")
        ref, kind = owners[identity]
        if exact(row.get("systems_ref")) != exact(ref):
            raise SourceRepairError("Reconstruction evidence disagrees with its retained source owner.")
        if ability and identity not in {"class", "species"} and ref["entry_type"] != "feat":
            raise SourceRepairError("An ability layer has no permanent class, species or feat owner.")
        links[(*path, "systems_ref")] = {"kind": kind}

    base = ("definition", "source", "native_reconstruction_choices")
    # History stores owner IDs and an opaque exact prior row, not duplicate
    # source links. Normal owner/recipe/model links still own reservation.
    from .character_feature_history import stored as history_relations
    history_relations(definition)
    from .character_infusion_recipes import stored as recipe_choices, FRAME as RECIPE_FRAME
    for index, recipe in enumerate(recipe_choices(definition)):
        links[(*base, RECIPE_FRAME, index, "systems_ref")] = {"kind": "reconstruction_feature"}
        if recipe["selected_item_ref"] is not None:
            links[(*base, RECIPE_FRAME, index, "selected_item_ref")] = {"kind": "item_reference"}
    from .character_armor_models import stored as armor_choices, FRAME_KEY as ARMOR_FRAME
    for index, choice in enumerate(armor_choices(definition)):
        for field, kind in (("class_ref", "class"), ("subclass_ref", "subclass"), ("systems_ref", "feature")):
            exact(choice[field])
            links[(*base, ARMOR_FRAME, index, field)] = {"kind": kind, "armor_model": deepcopy(choice)}
    from .character_parent_facets import stored_mappings as parent_mappings, FRAME_KEY
    for index, mapping in enumerate(parent_mappings(definition)):
        links[(*base, FRAME_KEY, index, "systems_ref")] = {
            "kind": mapping["parent_role"], "parent_facet": deepcopy(mapping)}
    layers = frame.get("ability_layers")
    if not isinstance(layers, dict) or set(layers) != {"str", "dex", "con", "int", "wis", "cha"}:
        raise SourceRepairError("Reconstruction ability evidence is malformed.")
    for ability, values in layers.items():
        if not isinstance(values, list) or len(values) > 40:
            raise SourceRepairError("Reconstruction ability evidence exceeds its bound.")
        for index, row in enumerate(values):
            if (not isinstance(row, dict) or set(row) != {"owner_id", "amount", "systems_ref"}
                    or type(row["amount"]) is not int or not -100 <= row["amount"] <= 100):
                raise SourceRepairError("Reconstruction ability evidence has an invalid layer.")
            owned(row, (*base, "ability_layers", ability, index), ability=True)
    proficiencies = frame.get("proficiency_owners")
    seen = set()
    if not isinstance(proficiencies, list) or len(proficiencies) > 128:
        raise SourceRepairError("Reconstruction proficiency evidence is malformed.")
    for index, row in enumerate(proficiencies):
        if (not isinstance(row, dict) or set(row) != {"owner_id", "systems_ref", "grant_categories"}
                or not isinstance(row["owner_id"], str) or row["owner_id"] in seen
                or not isinstance(row["grant_categories"], list)
                or any(not isinstance(value, str) for value in row["grant_categories"])
                or len(set(row["grant_categories"])) != len(row["grant_categories"])
                or set(row["grant_categories"]) - {"skills", "tools", "languages", "armor", "weapons", "tool_expertise"}):
            raise SourceRepairError("Reconstruction proficiency evidence has an invalid owner.")
        seen.add(row["owner_id"])
        owned(row, (*base, "proficiency_owners", index))
    for index, mapping in enumerate(stored_mappings(definition)):
        items = [row for row in definition.equipment_catalog if isinstance(row, dict)
                 and row.get("id") == mapping["item_id"]]
        mapping_retained = (mapping["item_id"] in retained_items
                            and digest(retained_items[mapping["item_id"]]) == digest(mapping))
        if (exact(mapping["systems_ref"])["entry_type"] != "item" or not mapping_retained and (
                len(items) != 1 or items[0].get("systems_ref") != mapping["systems_ref"]
                or items[0].get("page_ref") != mapping["prior_item"].get("page_ref"))):
            raise SourceRepairError("Reconstruction item evidence disagrees with its physical owner.")
        path = (*base, "item_source_mappings", index)
        links[(*path, "systems_ref")] = {"kind": "item", "dual": True}
        links[(*path, "page_ref")] = {"kind": "item_reference", "dual": True}
        links[(*path, "prior_item", "page_ref")] = {"kind": "item_reference"}
    from .character_skill_adoptions import stored as skill_adoptions, FRAME_KEY as SKILL_FRAME
    for index, row in enumerate(skill_adoptions(definition)):
        owned(row, (*base, SKILL_FRAME, index), current=True)
    from .character_feature_proficiency_grants import automatic_history, conditional_history, HISTORY, CONDITIONS
    for name, history in ((HISTORY, automatic_history(definition)), (CONDITIONS, conditional_history(definition))):
        for index, row in enumerate(history):
            owned(row, (*base, name, index), current=True)
            if name == CONDITIONS:
                for prior_index, prior_owner in enumerate(row["prior_owners"]):
                    owned(prior_owner, (*base, name, index, "prior_owners", prior_index), current=True)
    from .character_tracker_associations import stored as tracker_history, FRAME as TRACKER_FRAME
    for index, row in enumerate(tracker_history(definition)):
        owned({**row, "owner_id": row["feature_id"]}, (*base, TRACKER_FRAME, index), current=True)
    from .character_language_electives import outcome_rows, FRAME_KEY
    for index, row in enumerate(outcome_rows(definition)):
        owned(row, (*base, FRAME_KEY, index), current=True)
    return links


def attained_reconstruction_feature_owners(definition, systems_service, *, armor_selectors=None):
    """Exact deterministic sources and their class owners at the retained level."""
    from .character_profile import profile_class_rows
    from .character_source_authority import _current_reconstruction_subclass
    result = {}
    loader = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
    if not callable(loader):
        return {}
    for row in profile_class_rows(definition.profile):
        level = row.get("level")
        if type(level) is not int or not 1 <= level <= 20:
            continue
        class_ref = row.get("systems_ref")
        class_entry = (systems_service.get_entry_for_campaign(definition.campaign_slug, class_ref["entry_key"])
                       if isinstance(class_ref, dict) and class_ref.get("entry_key") else None)
        if (class_entry is None or class_entry.entry_type != "class"
                or any(class_ref.get(key) and class_ref[key] != getattr(class_entry, key, None)
                       for key in ("entry_key", "source_id", "entry_type", "slug", "title", "library_slug"))):
            class_entry = None
        for field in ("systems_ref", "subclass_ref"):
            ref = row.get(field)
            if not isinstance(ref, dict) or not ref.get("entry_key"):
                continue
            entry = systems_service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
            if entry is None or any(ref.get(key) and ref[key] != getattr(entry, key, None)
                                     for key in ("entry_key", "source_id", "entry_type", "slug")):
                continue
            owner_proved = (entry == class_entry if field == "systems_ref" else
                entry == _current_reconstruction_subclass(definition, row, class_entry, systems_service))
            for item in loader(definition.campaign_slug, entry, attained_level=level,
                               selected_feature_branches=armor_selectors):
                # Reachability compatibility is separate from owning-class proof.
                owners = result.setdefault(item.entry_key, set())
                if owner_proved:
                    owners.add(row.get("row_id"))
    return {key: frozenset(owners) for key, owners in result.items()}


def attained_reconstruction_features(definition, systems_service):
    """Exact deterministic class/subclass ownership at the retained level."""
    return frozenset(attained_reconstruction_feature_owners(definition, systems_service))


def current_reconstruction_feat_choices(definition, systems_service, authority):
    """Resolve retained feat choices only through current, qualified owners."""
    frame = definition.source.get("native_reconstruction_choices")
    if not isinstance(frame, dict) or systems_service is None:
        return [], {}
    selections = []
    for feature in definition.features:
        if not isinstance(feature, dict):
            continue
        ref = feature.get("systems_ref")
        if not isinstance(ref, dict) or ref.get("entry_type") != "feat":
            continue
        if authority is not None and authority.status_for("feature", feature.get("id")) != "VERIFIED":
            continue
        entry = systems_service.get_entry_for_campaign(definition.campaign_slug, ref.get("entry_key", ""))
        if (entry is not None and entry.entry_type == "feat"
                and all(not ref.get(key) or ref[key] == getattr(entry, key, None)
                        for key in ("entry_key", "source_id", "slug", "entry_type"))):
            selections.append({"entry": entry, "instance_key": feature["id"]})
    return selections, deepcopy(frame.get("choices") or {})


def advanced_hp_recipe(prior, features, feat_selections):
    """Prospective HP ledger only; this does not issue source authority."""
    from .character_hp_recipe import recipe_for_source
    from . import character_builder as builder
    recipe = recipe_for_source(prior.source)
    if recipe is None:
        return None
    for selection in feat_selections:
        entry = selection.get("entry")
        per_level = builder._feat_hit_point_bonus([selection], current_level=1)
        if not per_level:
            continue
        matches = [row for row in features if isinstance(row, dict)
                   and dict(row.get("systems_ref") or {}).get("entry_key") == entry.entry_key]
        if len(matches) != 1 or not matches[0].get("id"):
            raise SourceRepairError("Native continuation has an ambiguous continuing HP owner.")
        owner = matches[0]["id"]
        if any(row["owner_id"] == owner for row in recipe["continuing_effects"]):
            raise SourceRepairError("A continuing HP owner was already recorded.")
        recipe["continuing_effects"].append({"owner_id": owner, "per_level": per_level})
    return recipe


def advance_reconstruction_choices(prior, candidate, *, feat_selections, feature_selections,
                                   selected_choices, base_scores, prior_scores, class_entry, systems_service,
                                   elective_witnesses=()):
    """Carry only choices produced by the validated native advancement form."""
    frame = prior.source.get("native_reconstruction_choices")
    if not isinstance(frame, dict):
        return candidate
    from . import character_builder as builder
    from .character_builder_equipment import _systems_ref_from_entry
    payload = deepcopy(candidate.to_dict())
    frame = deepcopy(frame)
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        amount = base_scores[key] - prior_scores[key]
        if amount:
            frame["ability_layers"][key].append({"owner_id": "class", "amount": amount,
                "systems_ref": _systems_ref_from_entry(class_entry)})
    for kind, selections in (("feat", feat_selections), ("feature", feature_selections)):
        for selection in selections:
            entry = selection.get("entry")
            instance = selection.get("instance_key")
            if entry is None or not instance:
                continue
            matches = [row for row in candidate.features if isinstance(row, dict)
                       and dict(row.get("systems_ref") or {}).get("entry_key") == entry.entry_key]
            if len(matches) != 1:
                raise SourceRepairError("Native continuation has an ambiguous retained choice owner.")
            owner = matches[0]["id"]
            for name, values in selected_choices.items():
                prefix = f"{kind}:{instance}:"
                if name.startswith(prefix):
                    frame["choices"][f"{kind}:{owner}:{name[len(prefix):]}"] = deepcopy(values)
            if kind == "feat":
                bonuses = builder._apply_feat_ability_score_bonuses(dict.fromkeys(
                    ("str", "dex", "con", "int", "wis", "cha"), 0),
                    feat_selections=[selection], selected_choices=selected_choices, strict=True)
                for ability, amount in bonuses.items():
                    if amount:
                        frame["ability_layers"][ability].append({"owner_id": owner, "amount": amount,
                            "systems_ref": _systems_ref_from_entry(entry)})
            if not any(row.get("owner_id") == owner for row in frame["proficiency_owners"]):
                frame["proficiency_owners"].append({"owner_id": owner,
                    "systems_ref": _systems_ref_from_entry(entry),
                    "grant_categories": [category for category, names in {
                        "skills": ("skill_proficiencies", "expertise"), "tools": ("tool_proficiencies", "expertise"),
                        "languages": ("languages", "language_proficiencies", "communication_proficiencies"), "tool_expertise": ("expertise",),
                        "armor": ("armor_proficiencies",), "weapons": ("weapon_proficiencies",)}.items()
                        if any(entry.metadata.get(name) for name in names)
                        or category in {"skills", "tools", "tool_expertise"} and builder._supported_feature_expertise_blocks(entry)]})
    payload["source"]["native_progression"]["hp_recipe"] = advanced_hp_recipe(
        prior, candidate.features, feat_selections)
    payload["source"]["native_reconstruction_choices"] = frame
    from .character_reconstruction_proficiencies import refresh_continuation_choices
    return refresh_continuation_choices(CharacterDefinition.from_dict(payload), systems_service,
        elective_witnesses=elective_witnesses)


def reconstructed_input_bases(definition, *, systems_service, statuses=(), elective_witnesses=(),
                              _current_inputs=None):
    """Original typed inputs depend only on their actual permanent owners.

    A different library entry changing must not revoke an unrelated original
    score. Per-owner source payloads, rather than a global revision, bind each
    selected ability layer. Durable audit custody is still required separately.
    """
    from .character_ability_inputs import input_records
    from .character_source_authority import _current_systems_entry, _source_identity, numeric_value_digest
    choice_frame = definition.source.get("native_reconstruction_choices")
    if _current_inputs is not None:
        _current_inputs.check(definition, systems_service, statuses)
    if not isinstance(choice_frame, dict) or choice_frame.get("schema_version") != 1:
        return {}
    layers = choice_frame.get("ability_layers")
    if not isinstance(layers, dict):
        return {}
    result = {}
    from .character_profile import profile_class_rows
    classes = profile_class_rows(definition.profile)
    linked = {"species": definition.profile.get("species_ref"), "background": definition.profile.get("background_ref"),
              "class": classes[0].get("systems_ref") if len(classes) == 1 else None}
    feature_ids = [row.get("id") for row in definition.features if isinstance(row, dict)]
    linked.update({row["id"]: row.get("systems_ref") for row in definition.features
                   if isinstance(row, dict) and row.get("id") and feature_ids.count(row["id"]) == 1})
    feature_status = {row.instance_id: row.status for row in statuses if row.kind == "feature"}
    for ability, value in input_records(definition.stats).items():
        if value.get("stage") not in {"base", "pre_penalty"} or not isinstance(layers.get(ability), list):
            continue
        owners, valid = [], True
        for layer in layers[ability]:
            if not isinstance(layer, dict) or set(layer) != {"owner_id", "amount", "systems_ref"}:
                valid = False
                break
            ref = layer["systems_ref"]
            owner_ref = linked.get(layer["owner_id"])
            if (not isinstance(owner_ref, dict) or not isinstance(ref, dict)
                    or owner_ref.get("entry_key") != ref.get("entry_key")
                    or layer["owner_id"] in feature_ids and feature_status.get(layer["owner_id"]) != "VERIFIED"):
                valid = False
                break
            kind, key = _source_identity({"systems_ref": ref})
            entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
            if entry is None or any(ref.get(field) and ref[field] != getattr(entry, field, None)
                                    for field in ("entry_key", "entry_type", "source_id", "slug")):
                valid = False
                break
            owners.append({"id": layer["owner_id"], "amount": layer["amount"],
                           "source": {"entry_key": entry.entry_key, "metadata": entry.metadata, "body": entry.body}})
        if valid:
            identity = {key: deepcopy(item) for key, item in value.items() if key not in {"layers", "pre_penalty"}}
            if value.get("stage") == "pre_penalty":
                identity["layers"] = deepcopy(value.get("layers"))
            result[f"stats.ability_scores.{ability}.score"] = numeric_value_digest({"input": identity, "owners": owners})
    # This primitive prefix is independent of elective/proficiency witnesses.
    # Publish it only after the complete original main path returns normally.
    constitution_basis = result.get("stats.ability_scores.con.score")
    from .character_source_authority import numeric_target_values
    grant_fields = {"skills": ("skill_proficiencies", "expertise"),
        "languages": ("languages", "language_proficiencies", "communication_proficiencies"), "tools": ("tool_proficiencies", "expertise"),
        "tool_expertise": ("expertise",), "armor": ("armor_proficiencies",), "weapons": ("weapon_proficiencies",)}
    from . import character_builder as builder
    from .character_reconstruction_proficiencies import validate_current
    unresolved = set(choice_frame.get("unresolved_proficiencies", []))
    instrument_basis = None
    optional_weapon_basis = []
    try:
        if _current_inputs is None:
            current_unresolved = validate_current(definition, systems_service, elective_witnesses=elective_witnesses)
            validated = None
        else:
            current_unresolved = validate_current(definition, systems_service,
                elective_witnesses=elective_witnesses, _current_inputs=_current_inputs)
            validated = _current_inputs.validation(definition, systems_service)
        from .character_reconstruction_proficiencies import current_owners, optional_weapon_grants
        if "weapons" not in current_unresolved:
            optional_weapon_basis = (validated[0] if validated is not None else
                optional_weapon_grants(definition, current_owners(definition, systems_service),
                    systems_service, include_basis=True))
        from .character_reconstruction_instruments import current_choice
        if validated is None:
            _, instrument_basis = current_choice(definition, systems_service)
        else:
            instrument_basis = validated[1]
        from .character_language_electives import FRAME_KEY, language_basis
        if choice_frame.get(FRAME_KEY) and "languages" not in current_unresolved:
            unresolved.discard("languages")
        unresolved.update(current_unresolved)
    except (SourceRepairError, ValueError, TypeError, KeyError):
        # Failed current proficiency choices withhold those grants only. The
        # separately authenticated original ability inputs remain independent.
        unresolved.update(grant_fields)
    def prepare_owner_content(category):
        owners, valid = [], True
        for owner in choice_frame.get("proficiency_owners") or []:
            ref = owner.get("systems_ref") if isinstance(owner, dict) else None
            if not isinstance(ref, dict):
                valid = False
                break
            owner_ref = linked.get(owner.get("owner_id"))
            if (not isinstance(owner_ref, dict) or owner_ref.get("entry_key") != ref.get("entry_key")
                    or owner.get("owner_id") in feature_ids and feature_status.get(owner.get("owner_id")) != "VERIFIED"):
                if category in owner.get("grant_categories", []):
                    valid = False
                    break
                continue
            source_kind, source_key = _source_identity({"systems_ref": ref})
            entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
            if entry is None:
                if category in owner.get("grant_categories", []):
                    valid = False
                    break
                continue
            metadata = {key: deepcopy(entry.metadata[key]) for key in grant_fields[category] if key in entry.metadata}
            if category in {"skills", "tools", "tool_expertise"} and builder._supported_feature_expertise_blocks(entry):
                metadata["native_expertise"] = {"blocks": builder._supported_feature_expertise_blocks(entry), "body": entry.body}
            from .character_reconstruction_proficiencies import starting_grant
            starting = starting_grant(entry.metadata, category)
            if starting:
                metadata["starting"] = deepcopy(starting)
            if metadata:
                owners.append({"owner": owner["owner_id"], "entry_key": entry.entry_key, "grants": metadata})
        return owners, valid

    from .character_source_reads import SourceReadPhase
    from .systems_service import PhaseCharacterReadSystemsService
    phase = (systems_service.source_read_phase
             if type(systems_service) is PhaseCharacterReadSystemsService else None)
    reuse_category_content = isinstance(phase, SourceReadPhase)
    # Only owner content is invariant in this proved snapshot. Every target's
    # selection, custody inputs and digest below are still constructed afresh.
    category_content = {}
    for (kind, path, metric), value in numeric_target_values(definition, {}).items():
        if kind != "proficiency":
            continue
        category = "skills" if path.startswith("skills.") else path.split(".")[1]
        if category not in grant_fields:
            continue
        if category in unresolved:
            continue
        if reuse_category_content:
            phase.require_open()
            if category not in category_content:
                category_content[category] = prepare_owner_content(category)
            owners, valid = category_content[category]
        else:
            owners, valid = prepare_owner_content(category)
        if valid:
            selected = ({"name": value.get("name"), "proficiency_level": value.get("proficiency_level")}
                        if isinstance(value, dict) else value)
            basis = {"target": path, "selection": selected,
                "owners": owners, "choices": choice_frame.get("choices", {})}
            if category == "weapons" and optional_weapon_basis:
                basis["optional_rule_decisions"] = optional_weapon_basis
            if definition.source.get("native_feature_proficiency_choices"):
                basis["native_feature_acquisitions"] = deepcopy(definition.source["native_feature_proficiency_choices"])
            if category in {"tools", "tool_expertise"}:
                from .character_feature_proficiency_grants import automatic_history, conditional_history
                if automatic_history(definition):
                    basis["automatic_tool_expertise"] = list(automatic_history(definition))
                if conditional_history(definition):
                    basis["conditional_proficiency_acquisitions"] = list(conditional_history(definition))
            if category in {"tools", "tool_expertise"} and instrument_basis is not None:
                basis["background_instrument"] = instrument_basis
            if category == "skills":
                from .character_skill_adoptions import stored as skill_adoptions
                from .repository import normalize_lookup
                adoption = [row for row in skill_adoptions(definition)
                            if row["skill_key"] == normalize_lookup(value.get("name"))]
                if adoption:
                    basis["skill_adoption"] = adoption[0]
            if category == "languages" and choice_frame.get("language_elective_outcomes"):
                basis["language_elective_outcomes"] = language_basis(definition, systems_service, elective_witnesses)
            result[path] = numeric_value_digest(basis)
    if len(classes) == 1:
        ref = classes[0].get("systems_ref")
        kind, key = _source_identity({"systems_ref": ref})
        entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
        if entry is not None and entry.entry_type == "class":
            result["stats.proficiency_bonus"] = numeric_value_digest({"class": classes[0],
                "source": {"entry_key": entry.entry_key, "metadata": entry.metadata, "body": entry.body}})
    if _current_inputs is not None:
        _current_inputs.complete(definition, systems_service, constitution_basis)
    return result


def digest(value: Any) -> str:
    from .character_update_apply import canonical_digest
    return canonical_digest(value)


def capacity_frame(state: dict[str, Any]) -> dict[str, Any]:
    """Keep only historical rule maxima, never fabricate historical usage."""
    slots = state.get("spell_slots")
    dice = state.get("hit_dice")
    pools = dice.get("pools") if isinstance(dice, dict) else None
    return {"spell_slots": [{key: deepcopy(row[key]) for key in ("slot_lane_id", "level", "max") if key in row}
                            for row in slots if isinstance(row, dict)] if isinstance(slots, list) else [],
            "hit_dice": {"pools": [{key: deepcopy(row[key]) for key in ("faces", "max") if key in row}
                                      for row in pools if isinstance(row, dict)] if isinstance(pools, list) else []}}


def current_target_tuple(campaign, character, *, include_state_identity=False):
    if type(include_state_identity) is not bool:
        raise SourceRepairError("State identity selection has an unsupported type.")
    from .db import get_db
    state = get_db().execute("SELECT revision,state_json,updated_at,updated_by_user_id FROM character_state "
        "WHERE campaign_slug=? AND character_slug=?", (campaign, character)).fetchone()
    assignment = get_db().execute("SELECT id,user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
                                 (campaign, character)).fetchone()
    if state is None:
        raise SourceRepairError("The exact existing state tuple is unavailable.")
    result = digest(dict(state)), digest(dict(assignment) if assignment is not None else None)
    if include_state_identity:
        import hashlib
        import json
        if type(state["state_json"]) is not str:
            raise SourceRepairError("The exact current state serialization is unavailable.")
        return (*result, hashlib.sha256(state["state_json"].encode("utf-8")).hexdigest(),
            digest(json.loads(state["state_json"])), state["revision"])
    return result


def reconstruction_mirrors_match(record, campaigns_dir):
    """Read back the committed pair and portrait; never repair during readback."""
    from .committed_character_publication import character_mirror_comparison, portrait_bytes
    from .character_repository import load_campaign_character_config
    from .character_assets import resolve_character_portrait_asset_path, CHARACTER_PORTRAIT_MAX_BYTES
    from .committed_publication import _safe_mirror_path
    campaign, character = record.definition.campaign_slug, record.definition.character_slug
    settings = load_campaign_character_config(campaigns_dir, campaign)
    if character_mirror_comparison(campaign, character, config_record=settings)["mirror_current_state"] != "matching":
        return False
    portrait = portrait_bytes(campaign, character)
    if portrait is None:
        return not record.definition.profile.get("portrait_asset_ref")
    ref, expected = portrait
    _, path = resolve_character_portrait_asset_path(settings.campaign_dir, character, ref)
    path = _safe_mirror_path(path)
    return path.is_file() and path.stat().st_size <= CHARACTER_PORTRAIT_MAX_BYTES and path.read_bytes() == expected


def _resource_owner_mappings(prior, candidate):
    """Describe only missing-to-typed class ownership in exact generation pairs.

    This is historical structure, not source authority. The issuer separately
    proves every member against current source policy before minting a proof.
    """
    from .character_profile import profile_class_rows
    from .managed_resource_registry import managed_resource_feature_identity
    classes = profile_class_rows(candidate.profile)
    result = []
    for field_name in ("features", "resource_templates"):
        before = [row for row in getattr(prior, field_name) if isinstance(row, dict)]
        after = [row for row in getattr(candidate, field_name) if isinstance(row, dict)]
        old_ids, new_ids = [row.get("id") for row in before], [row.get("id") for row in after]
        if (not all(isinstance(value, str) and value for value in old_ids + new_ids)
                or len(set(old_ids)) != len(old_ids) or len(set(new_ids)) != len(new_ids)
                or set(old_ids) != set(new_ids)):
            raise SourceRepairError("Reconstruction must retain every managed resource and feature identity.")
        for old, new in ((row, after[new_ids.index(row["id"])]) for row in before):
            if ("class_row_id" in old) == ("class_row_id" in new) and old.get("class_row_id") == new.get("class_row_id"):
                continue
            row_id = new.get("class_row_id")
            tracker_id = new.get("tracker_ref") if field_name == "features" else new["id"]
            owner_classes = [row for row in classes if row.get("row_id") == row_id]
            members = [row for row in candidate.features
                       if isinstance(row, dict) and row.get("tracker_ref") == tracker_id]
            identities = []
            for member in members:
                typed = deepcopy(member)
                typed["source"] = dict(member.get("systems_ref") or {}).get("source_id")
                identities.append(managed_resource_feature_identity(typed))
            if (old.get("class_row_id") not in (None, "") or not isinstance(row_id, str) or not row_id
                    or len(owner_classes) != 1 or not members or not all(identities)
                    or len(set(identities)) != 1 or identities[0][1] != row_id
                    or field_name == "features" and new not in members):
                raise SourceRepairError("A retained resource class owner is conflicting or unproved.")
            result.append({"field": field_name, "id": old["id"],
                "prior_present": "class_row_id" in old, "prior_owner": old.get("class_row_id"),
                "class_row_id": row_id, "pool_id": tracker_id, "class": deepcopy(owner_classes[0]),
                "members": sorted(({key: deepcopy(row.get(key)) for key in
                    ("id", "class_row_id", "systems_ref", "source")} for row in members), key=lambda row: row["id"])})
    return tuple(result)


def reconstruct_resource_owners(prior, candidate, *, systems_service, campaign_page_records, tracker_bindings=()):
    from .character_source_authority import _current_managed_pool_owners, _eligible_page_records
    pools = _current_managed_pool_owners(candidate, systems_service=systems_service,
        pages=_eligible_page_records(campaign_page_records), infer_missing=True, tracker_bindings=tracker_bindings)
    payload = deepcopy(candidate.to_dict())
    for tracker_id, pool in pools.items():
        member_ids = {row["feature"]["id"] for row in pool["members"]}
        for field_name in ("features", "resource_templates"):
            for row in payload[field_name]:
                if (isinstance(row, dict) and (row.get("id") in member_ids if field_name == "features"
                                              else row.get("id") == tracker_id)
                        and row.get("class_row_id") in (None, "")):
                    row["class_row_id"] = pool["class_row_id"]
    proposed = CharacterDefinition.from_dict(payload)
    mappings = _resource_owner_mappings(prior, proposed)
    if any(row["pool_id"] not in pools or row["class_row_id"] != pools[row["pool_id"]]["class_row_id"]
           for row in mappings):
        raise SourceRepairError("A reconstructed resource owner has no complete current source proof.")
    return proposed, mappings


@dataclass(frozen=True, slots=True)
class PendingNativeReconstruction:
    candidate: CharacterDefinition
    markers: tuple[dict[str, Any], ...]
    bases: dict[str, str]
    source_snapshot_digest: str
    origin: dict[str, Any]
    authority: Any
    refresh: Callable[[], Any] = field(repr=False, compare=False)
    item_mappings: tuple[dict[str, Any], ...] = ()
    resource_mappings: tuple[dict[str, Any], ...] = ()
    parent_facet_mappings: tuple[dict[str, Any], ...] = ()
    armor_model_choices: tuple[dict[str, Any], ...] = ()
    skill_adoptions: tuple[dict[str, Any], ...] = ()
    tracker_associations: tuple[dict[str, Any], ...] = ()
    automatic_expertise: tuple[dict[str, Any], ...] = ()
    proficiency_conditions: tuple[dict[str, Any], ...] = ()
    artificer_recipes: tuple[dict[str, Any], ...] = ()
    feature_history: tuple[dict[str, Any], ...] = ()

    def permits_resource_owner_mapping(self, prior_record, definition, identity):
        return (definition.to_dict() == self.candidate.to_dict()
                and _resource_owner_mappings(prior_record.definition, definition) == self.resource_mappings
                and any(row["field"] == "resource_templates" and row["id"] == identity
                        for row in self.resource_mappings))

    def permits_item_mapping(self, prior_record, definition, identity):
        from .character_reconstruction_items import mapped_item
        matches = [row for row in self.item_mappings if row["item_id"] == identity]
        old = [row for row in prior_record.definition.equipment_catalog if isinstance(row, dict) and row.get("id") == identity]
        new = [row for row in definition.equipment_catalog if isinstance(row, dict) and row.get("id") == identity]
        return (definition.to_dict() == self.candidate.to_dict() and len(matches) == len(old) == len(new) == 1
                and old[0] == matches[0]["prior_item"] and new[0] == mapped_item(matches[0]))

    def validate_binding(self, prior_record, definition, desired_state, actor_id):
        if (type(actor_id) is not int or actor_id != self.origin.get("actor_user_id")
                or (definition.campaign_slug, definition.character_slug) != (
                    self.origin.get("campaign_slug"), self.origin.get("character_slug"))
                or (prior_record.definition.campaign_slug, prior_record.definition.character_slug) != (
                    definition.campaign_slug, definition.character_slug)
                or definition.to_dict() != self.candidate.to_dict()
                or desired_state != prior_record.state_record.state
                or prior_record.committed_revision != self.origin.get("prior_generation")
                or digest(prior_record.definition.to_dict()) != self.origin.get("prior_definition_digest")
                or digest(prior_record.import_metadata.to_dict()) != self.origin.get("prior_import_digest")
                or prior_record.state_record.revision != self.origin.get("prior_state_revision")
                or digest(desired_state) != self.origin.get("prior_state_digest")):
            raise SourceRepairError("The reconstruction target or exact preserved state changed.")

    def recheck(self, prior_record, definition, desired_state, actor_id):
        self.validate_binding(prior_record, definition, desired_state, actor_id)
        if current_target_tuple(definition.campaign_slug, definition.character_slug) != (
                self.origin["prior_state_tuple_digest"], self.origin["assignment_digest"]):
            raise SourceRepairError("The exact state tuple or Character assignment changed.")
        current = self.refresh()
        if (not isinstance(current, PendingNativeReconstruction)
                or current.candidate.to_dict() != self.candidate.to_dict()
                or current.markers != self.markers or current.bases != self.bases
                or current.origin != self.origin
                or current.item_mappings != self.item_mappings
                or current.resource_mappings != self.resource_mappings
                or current.parent_facet_mappings != self.parent_facet_mappings
                or current.armor_model_choices != self.armor_model_choices
                or current.skill_adoptions != self.skill_adoptions
                or current.tracker_associations != self.tracker_associations
                or current.automatic_expertise != self.automatic_expertise
                or current.proficiency_conditions != self.proficiency_conditions
                or current.artificer_recipes != self.artificer_recipes
                or current.feature_history != self.feature_history
                or current.authority.identity != self.authority.identity
                or current.source_snapshot_digest != self.source_snapshot_digest):
            raise SourceRepairError("The reconstruction choices, access or current sources changed.")
        return current.authority


def issue_reconstruction(*, record, candidate, systems_service, campaign_page_records,
                         actor_id: int, action_id: str, input_digest: str,
                         refresh: Callable[[], Any]) -> PendingNativeReconstruction:
    from .committed_publication import active
    from .character_hp_recipe import recipe_for_source
    from .character_source_authority import (
        build_reconciled_source_authority, numeric_target_values,
        native_baseline_target, native_advancement_input_target,
        validate_native_managed_resource_templates,
    )
    from .character_source_repair import (
        add_numeric_authorization, numeric_authorization_record,
        load_verified_numeric_actions, load_verified_manual_actions, _sha256_hex,
    )
    if (not active() or type(record.committed_revision) is not int
            or candidate.system != "DND-5E" or type(actor_id) is not int or actor_id < 1
            or not _sha256_hex(action_id) or not _sha256_hex(input_digest)
            or not callable(refresh) or recipe_for_source(candidate.source) is None):
        raise SourceRepairError("Reconstruction needs an admitted committed Character and complete native inputs.")
    state = deepcopy(record.state_record.state)
    numeric = load_verified_numeric_actions(candidate.campaign_slug, candidate.character_slug, strict=True)
    from .character_skill_adoptions import validate_history as validate_skills, custody as skill_custody
    skill_adoptions = validate_skills(record.definition, candidate, systems_service, witnesses=numeric)
    from .character_feature_proficiency_grants import (validate_automatic, automatic_custody, validate_conditions, conditional_custody)
    automatic_expertise = validate_automatic(record.definition, candidate, systems_service, witnesses=numeric)
    proficiency_conditions = validate_conditions(record.definition, candidate, systems_service, witnesses=numeric)
    from .character_reconstruction_items import validate_mappings
    item_mappings = validate_mappings(record.definition, candidate, systems_service, campaign_page_records)
    from .character_armor_models import validate as validate_armor, custody as armor_custody, digest as armor_digest
    armor_choices = validate_armor(record.definition, candidate, systems_service)
    from .character_tracker_associations import validate as validate_trackers, custody as tracker_custody
    tracker_associations = validate_trackers(record.definition, candidate, state, witnesses=numeric,
        service=systems_service, pages=campaign_page_records)
    candidate, resource_mappings = reconstruct_resource_owners(record.definition, candidate,
        systems_service=systems_service, campaign_page_records=campaign_page_records, tracker_bindings=tracker_associations)
    from .character_parent_facets import validate_mappings as validate_parent_facets, custody as parent_custody
    parent_facet_mappings = validate_parent_facets(record.definition, candidate, systems_service)
    from .character_infusion_recipes import validate as validate_recipes, custody as recipe_custody
    artificer_recipes = validate_recipes(record.definition, candidate, systems_service)
    from .character_feature_history import validate as validate_history, custody as history_custody, ORIGIN as HISTORY_ORIGIN
    feature_history = validate_history(record.definition, candidate, systems_service)
    state_tuple_digest, assignment_digest = current_target_tuple(candidate.campaign_slug, candidate.character_slug)
    from .character_profile import profile_class_rows
    rows = profile_class_rows(candidate.profile)
    old_rows = profile_class_rows(record.definition.profile)
    if len(rows) != 1 or len(old_rows) != 1 or rows[0].get("row_id") != old_rows[0].get("row_id"):
        raise SourceRepairError("Reconstruction requires the existing single class-row identity.")
    identities = []
    for kind, owners in (("feature", candidate.features), ("item", candidate.equipment_catalog),
                          ("resource", candidate.resource_templates), ("spell", candidate.spellcasting.get("spells", []))):
        identities.extend((kind, row.get("id")) for row in owners if isinstance(row, dict))
    if any(not path for _kind, path in identities) or len(identities) != len(set(identities)):
        raise SourceRepairError("Reconstruction has a missing or duplicate stable owner identity.")
    from .character_reconstruction_proficiencies import current_owners
    # Independent issuance repeats the exact container/type check; composing
    # a candidate is not permission to mint arbitrary subclass feature grants.
    current_owners(candidate, systems_service)
    origin = {"schema_version": 1, "campaign_slug": candidate.campaign_slug,
              "character_slug": candidate.character_slug, "actor_user_id": actor_id,
              "action_id": action_id, "input_digest": input_digest,
              "prior_generation": record.committed_revision,
              "prior_definition_digest": digest(record.definition.to_dict()),
              "prior_import_digest": digest(record.import_metadata.to_dict()),
              "prior_state_revision": record.state_record.revision,
              "prior_state_digest": digest(state),
              "prior_state_tuple_digest": state_tuple_digest, "assignment_digest": assignment_digest,
              "recipe_digest": digest(recipe_for_source(candidate.source))}
    if item_mappings:
        origin["item_mapping_digest"] = digest(list(item_mappings))
    if resource_mappings:
        origin["resource_owner_mapping_digest"] = digest(list(resource_mappings))
    if parent_facet_mappings:
        from .character_parent_facets import digest as facet_digest
        origin["parent_facet_mapping_digest"] = facet_digest(list(parent_facet_mappings))
    if armor_choices:
        origin["armor_model_digest"] = armor_digest(list(armor_choices))
    if skill_adoptions:
        origin["skill_adoption_digest"] = digest(list(skill_adoptions))
    if tracker_associations:
        origin["tracker_association_digest"] = digest(list(tracker_associations))
    if automatic_expertise:
        origin["automatic_expertise_digest"] = digest(list(automatic_expertise))
    if proficiency_conditions:
        origin["feature_proficiency_condition_digest"] = digest(list(proficiency_conditions))
    if artificer_recipes:
        origin["artificer_recipe_digest"] = digest(list(artificer_recipes))
    if feature_history:
        origin[HISTORY_ORIGIN] = digest(list(feature_history))
    payload = deepcopy(candidate.to_dict())
    payload["source"]["native_reconstruction"] = origin
    candidate = CharacterDefinition.from_dict(payload)
    reconstruction_source_links(candidate)
    manual = load_verified_manual_actions(candidate.campaign_slug, candidate.character_slug, strict=True)
    numeric = (*numeric, *parent_custody(candidate, origin, parent_facet_mappings),
               *armor_custody(candidate, origin, armor_choices),
               *skill_custody(candidate, origin, skill_adoptions),
               *tracker_custody(candidate, origin, tracker_associations),
               *automatic_custody(candidate, origin, automatic_expertise),
               *conditional_custody(candidate, origin, proficiency_conditions),
               *recipe_custody(candidate, origin, artificer_recipes),
               *history_custody(candidate, origin, feature_history))
    def authority_for(definition, witnesses):
        return build_reconciled_source_authority(
            definition=definition, state=state, state_revision=record.state_record.revision,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            verified_manual_actions=manual, verified_numeric_actions=tuple(witnesses))
    authority = authority_for(candidate, numeric)
    values = numeric_target_values(candidate, state)
    keys = [key for key in values if native_advancement_input_target(*key)]
    if len(keys) != 7:
        raise SourceRepairError("Confirm all six original ability inputs and the class owner.")
    markers, bases, pending = [], {}, list(numeric)
    for kind, path, metric in keys:
        basis = authority.numeric_basis_digest(path)
        if not _sha256_hex(basis):
            raise SourceRepairError("A native input has no closed current source owner.")
        marker = numeric_authorization_record(character_slug=candidate.character_slug,
            target_kind=kind, target_id=path, metric=metric, raw_value=values[(kind, path, metric)],
            action_id=action_id, provenance=PROVENANCE)
        markers.append(marker)
        bases[path] = basis
        payload = add_numeric_authorization(payload, marker)
        pending.append({"authorization": marker, "source_basis_digest": basis})
    candidate = CharacterDefinition.from_dict(payload)
    authority = authority_for(candidate, pending)
    candidate = reconstruct_source_row_formulas(candidate, authority, systems_service)
    payload = deepcopy(candidate.to_dict())
    values = numeric_target_values(candidate, state)
    authority = authority_for(candidate, pending)
    validate_native_managed_resource_templates(candidate, state, authority=authority,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        prior_definition=record.definition)
    keys = [key for key in values if key not in keys and (
        native_baseline_target(*key) or key[0] in {"resource", "spell_metric", "spell_choice"}
        or key == ("field", "stats.max_hp", "final"))]
    for kind, path, metric in keys:
        basis = (authority.resource_basis_digest(path) if kind == "resource"
                 else authority.numeric_basis_digest(path))
        if basis is None:
            # Retain an unmodeled/manual clause without inventing its authority.
            continue
        if values[(kind, path, metric)] is None or path in bases:
            raise SourceRepairError("Reconstruction numeric owners are incomplete or ambiguous.")
        marker = numeric_authorization_record(character_slug=candidate.character_slug,
            target_kind=kind, target_id=path, metric=metric, raw_value=values[(kind, path, metric)],
            action_id=action_id, provenance=PROVENANCE)
        markers.append(marker)
        bases[path] = basis
        payload = add_numeric_authorization(payload, marker)
        pending.append({"authorization": marker, "source_basis_digest": basis})
    from .character_feature_proficiency_grants import automatic_history
    if len(automatic_expertise) > len(automatic_history(record.definition)):
        if any("proficiencies.tools." + str(tool).casefold() not in bases or
               "proficiencies.tool_expertise." + str(tool).casefold() not in bases
               for tool in candidate.proficiencies.get("tools", [])):
            raise SourceRepairError("Automatic expertise requires every current tool to have qualified source ownership.")
    if not 1 <= len(markers) <= 128 or "stats.max_hp" not in bases:
        raise SourceRepairError("The reconstructed HP or numeric owner closure is unavailable.")
    candidate = CharacterDefinition.from_dict(payload)
    authority = authority_for(candidate, pending)
    if any(authority.status_for("feature", row["feature_id"]) != "VERIFIED" for row in feature_history):
        raise SourceRepairError("A selected historical association has no qualified current owner and custody.")
    return PendingNativeReconstruction(candidate, tuple(markers), bases,
        authority.source_snapshot_digest, origin, authority, refresh, item_mappings, resource_mappings, parent_facet_mappings,
        armor_choices, skill_adoptions, tracker_associations, automatic_expertise, proficiency_conditions, artificer_recipes,
        feature_history)


def reconstruct_source_row_formulas(candidate, authority, systems_service):
    """Propose native source math, retain it only after actual grant closure.

    An imported number is never evidence of a formula. The current approved
    source-row adapter must independently accept the row/ability and exact
    native formula; unproved or explicitly manual records remain unchanged.
    """
    from .character_builder_constants import ABILITY_LABELS
    from .character_source_authority import _source_derived_formula_bases
    payload = deepcopy(candidate.to_dict())
    pb = candidate.stats.get("proficiency_bonus")
    if type(pb) is not int:
        return candidate
    keys = {label: key for key, label in ABILITY_LABELS.items()}
    proposals = []
    for row in payload["spellcasting"].get("source_rows", []):
        if not isinstance(row, dict) or row.get("source_row_id") not in authority.verified_source_rows:
            continue
        ability = keys.get(row.get("spellcasting_ability"))
        score = dict(candidate.stats.get("ability_scores", {}).get(ability) or {}).get("score")
        if type(score) is not int:
            continue
        records = row.get("spell_metric_provenance")
        records = deepcopy(records) if isinstance(records, dict) else {}
        for metric, offset in (("spell_attack_bonus", 0), ("spell_save_dc", 8)):
            if metric in records:
                continue
            row[metric] = offset + pb + (score - 10) // 2
            records[metric] = {"kind": "formula"}
            proposals.append((row["source_row_id"], metric))
        if records:
            row["spell_metric_provenance"] = records
    if not proposals:
        return candidate
    proposed = CharacterDefinition.from_dict(payload)
    bases = _source_derived_formula_bases(proposed, systems_service=systems_service,
        verified_class_rows=authority.verified_class_rows, verified_source_rows=authority.verified_source_rows,
        grants=authority.grants, source_snapshot_digest=authority.source_snapshot_digest)
    result = deepcopy(candidate.to_dict())
    proposed_rows = {row["source_row_id"]: row for row in proposed.spellcasting.get("source_rows", [])
                     if isinstance(row, dict) and row.get("source_row_id")}
    for row in result["spellcasting"].get("source_rows", []):
        if not isinstance(row, dict):
            continue
        identity = row.get("source_row_id")
        for owner, metric in proposals:
            if owner == identity and f"spell_metric:source:{identity}:{metric}" in bases:
                row[metric] = proposed_rows[identity][metric]
                if not isinstance(row.get("spell_metric_provenance"), dict):
                    row["spell_metric_provenance"] = {}
                row["spell_metric_provenance"][metric] = {"kind": "formula"}
    return CharacterDefinition.from_dict(result)


def confirmed_metadata(proof, *, definition, prior_record, state, actor_id, generation):
    # The refreshed source/access check happened under the reservation, before
    # appending. The new generation is now an outcome, not a fresh prior target.
    proof.validate_binding(prior_record, definition, state, actor_id)
    return {"manager_action": "native_reconstruct", "numeric_actor_id": actor_id,
            "action_id": proof.origin["action_id"], "native_reconstruction": deepcopy(proof.origin),
            "numeric_authorizations": deepcopy(list(proof.markers)),
            "source_basis_digests": deepcopy(proof.bases),
            "source_snapshot_digest": proof.source_snapshot_digest,
            "definition_digest": digest(definition.to_dict()), "published_revision": generation,
            "published_state_revision": prior_record.state_record.revision,
            "capacity_frame": capacity_frame(state),
            **({"tracker_association_state": deepcopy(state)} if proof.tracker_associations else {})}


def verified_reconstruction_batch(connection, campaign, character, audit_row, metadata, *, prior_witnesses=()):
    """Independently join a confirmed origin to exact target generations."""
    from .character_native_requalification import _generation
    from .character_hp_recipe import recipe_for_source
    from .character_source_repair import _valid_numeric_witness_marker, _sha256_hex
    from .character_source_authority import numeric_target_values, numeric_value_digest
    actor = audit_row["actor_user_id"]
    origin = metadata.get("native_reconstruction")
    batch, bases = metadata.get("numeric_authorizations"), metadata.get("source_basis_digests")
    origin_fields = {"schema_version", "campaign_slug", "character_slug", "actor_user_id", "action_id",
        "input_digest", "prior_generation", "prior_definition_digest", "prior_import_digest",
        "prior_state_revision", "prior_state_digest", "prior_state_tuple_digest", "assignment_digest", "recipe_digest"}
    if isinstance(origin, dict) and "artificer_recipe_digest" in origin:
        origin_fields.add("artificer_recipe_digest")
        if not _sha256_hex(origin["artificer_recipe_digest"]):
            return ()
    from .character_feature_history import ORIGIN as HISTORY_ORIGIN
    if isinstance(origin, dict) and HISTORY_ORIGIN in origin:
        origin_fields.add(HISTORY_ORIGIN)
        if not _sha256_hex(origin[HISTORY_ORIGIN]):
            return ()
    if isinstance(origin, dict) and "item_mapping_digest" in origin:
        origin_fields.add("item_mapping_digest")
        if not _sha256_hex(origin["item_mapping_digest"]):
            return ()
    if isinstance(origin, dict) and "resource_owner_mapping_digest" in origin:
        origin_fields.add("resource_owner_mapping_digest")
        if not _sha256_hex(origin["resource_owner_mapping_digest"]):
            return ()
    if isinstance(origin, dict) and "parent_facet_mapping_digest" in origin:
        origin_fields.add("parent_facet_mapping_digest")
        if not _sha256_hex(origin["parent_facet_mapping_digest"]):
            return ()
    if isinstance(origin, dict) and "armor_model_digest" in origin:
        origin_fields.add("armor_model_digest")
        if not _sha256_hex(origin["armor_model_digest"]):
            return ()
    if isinstance(origin, dict) and "skill_adoption_digest" in origin:
        origin_fields.add("skill_adoption_digest")
        if not _sha256_hex(origin["skill_adoption_digest"]):
            return ()
    for key in ("automatic_expertise_digest", "feature_proficiency_condition_digest"):
        if isinstance(origin, dict) and key in origin:
            origin_fields.add(key)
            if not _sha256_hex(origin[key]):
                return ()
    if isinstance(origin, dict) and "tracker_association_digest" in origin:
        origin_fields.add("tracker_association_digest")
        if not _sha256_hex(origin["tracker_association_digest"]):
            return ()
    if (type(actor) is not int or actor < 1 or metadata.get("numeric_actor_id") != actor
            or metadata.get("source") != "character_update_preview"
            or metadata.get("manager_action") != "native_reconstruct"
            or not _sha256_hex(metadata.get("review_digest"))
            or not isinstance(origin, dict) or set(origin) != origin_fields
            or type(origin.get("schema_version")) is not int or origin.get("schema_version") != 1
            or origin.get("campaign_slug") != campaign or origin.get("character_slug") != character
            or origin.get("actor_user_id") != actor or origin.get("action_id") != metadata.get("action_id")
            or not isinstance(batch, list) or not 1 <= len(batch) <= 128
            or not isinstance(bases, dict) or len(bases) != len(batch)
            or any(not _sha256_hex(origin.get(key)) for key in ("action_id", "input_digest",
                "prior_definition_digest", "prior_import_digest", "prior_state_digest", "prior_state_tuple_digest", "assignment_digest", "recipe_digest"))
            or type(origin.get("prior_state_revision")) is not int or origin["prior_state_revision"] < 1
            or type(metadata.get("published_revision")) is not int):
        return ()
    try:
        payload, generation = _generation(connection, campaign, character,
            metadata["definition_digest"], actor, metadata["published_revision"])
        definition = CharacterDefinition.from_dict(payload)
        reconstruction_source_links(definition)
        if (definition.source.get("native_reconstruction") != origin
                or digest(recipe_for_source(definition.source)) != origin.get("recipe_digest")
                or digest(dict(definition.source.get("native_reconstruction_choices") or {}).get("inputs")) != origin.get("input_digest")
                or metadata.get("published_state_revision") != origin.get("prior_state_revision")
                or type(origin.get("prior_generation")) is not int
                or origin["prior_generation"] + 1 != generation["revision"]):
            return ()
        from .committed_source_store import _decode_mapping
        from .character_models import CharacterImportMetadata
        prior = connection.execute("SELECT actor_user_id,secondary_bytes FROM committed_source_generations "
            "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=?",
            (campaign, character, origin["prior_generation"])).fetchone()
        if prior is None:
            return ()
        if digest(CharacterImportMetadata.from_dict(_decode_mapping(prior["secondary_bytes"])).to_dict()) != origin["prior_import_digest"]:
            return ()
        prior_payload, _ = _generation(connection, campaign, character, origin["prior_definition_digest"],
                    prior["actor_user_id"], origin["prior_generation"])
        from .character_reconstruction_items import validate_mappings
        mappings = validate_mappings(CharacterDefinition.from_dict(prior_payload), definition)
        if (mappings and digest(list(mappings)) != origin.get("item_mapping_digest")
                or not mappings and "item_mapping_digest" in origin):
            return ()
        resource_mappings = _resource_owner_mappings(CharacterDefinition.from_dict(prior_payload), definition)
        if (resource_mappings and digest(list(resource_mappings)) != origin.get("resource_owner_mapping_digest")
                or not resource_mappings and "resource_owner_mapping_digest" in origin):
            return ()
        from .character_parent_facets import validate_mappings as validate_parent_facets, custody as parent_custody, digest as facet_digest
        facet_mappings = validate_parent_facets(CharacterDefinition.from_dict(prior_payload), definition)
        if (facet_mappings and facet_digest(list(facet_mappings)) != origin.get("parent_facet_mapping_digest")
                or not facet_mappings and "parent_facet_mapping_digest" in origin):
            return ()
        from .character_armor_models import validate as validate_armor, custody as armor_custody, digest as armor_digest
        armor_choices = validate_armor(CharacterDefinition.from_dict(prior_payload), definition)
        if (armor_choices and armor_digest(list(armor_choices)) != origin.get("armor_model_digest")
                or not armor_choices and "armor_model_digest" in origin):
            return ()
        from .character_skill_adoptions import validate_history as validate_skills, custody as skill_custody
        skill_adoptions = validate_skills(CharacterDefinition.from_dict(prior_payload), definition,
            witnesses=prior_witnesses)
        if (skill_adoptions and digest(list(skill_adoptions)) != origin.get("skill_adoption_digest")
                or not skill_adoptions and "skill_adoption_digest" in origin):
            return ()
        from .character_tracker_associations import validate as validate_trackers, custody as tracker_custody, stored as tracker_history
        tracker_state = metadata.get("tracker_association_state", {})
        if tracker_history(definition) and digest(tracker_state) != origin["prior_state_digest"]:
            return ()
        tracker_associations = validate_trackers(CharacterDefinition.from_dict(prior_payload), definition, tracker_state,
            witnesses=prior_witnesses)
        if (tracker_associations and digest(list(tracker_associations)) != origin.get("tracker_association_digest")
                or not tracker_associations and "tracker_association_digest" in origin):
            return ()
        from .character_feature_proficiency_grants import (validate_automatic, automatic_custody, validate_conditions, conditional_custody)
        automatic_expertise = validate_automatic(CharacterDefinition.from_dict(prior_payload), definition, witnesses=prior_witnesses)
        proficiency_conditions = validate_conditions(CharacterDefinition.from_dict(prior_payload), definition, witnesses=prior_witnesses)
        for key, records in (("automatic_expertise_digest", automatic_expertise), ("feature_proficiency_condition_digest", proficiency_conditions)):
            if (records and digest(list(records)) != origin.get(key) or not records and key in origin):
                return ()
        from .character_infusion_recipes import validate as validate_recipes, custody as recipe_custody
        artificer_recipes = validate_recipes(CharacterDefinition.from_dict(prior_payload), definition)
        if (artificer_recipes and digest(list(artificer_recipes)) != origin.get("artificer_recipe_digest")
                or not artificer_recipes and "artificer_recipe_digest" in origin):
            return ()
        from .character_feature_history import validate as validate_history, custody as history_custody
        feature_history = validate_history(CharacterDefinition.from_dict(prior_payload), definition)
        if (feature_history and digest(list(feature_history)) != origin.get(HISTORY_ORIGIN)
                or not feature_history and HISTORY_ORIGIN in origin):
            return ()
        values = numeric_target_values(definition, metadata.get("capacity_frame", {}))
        stored = list(definition.source.get("source_authorizations") or [])
        if len({marker.get("target_id") for marker in batch if isinstance(marker, dict)}) != len(batch):
            return ()
        if set(bases) != {marker.get("target_id") for marker in batch if isinstance(marker, dict)}:
            return ()
        targets = {(marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
                   for marker in batch if isinstance(marker, dict)}
        mandatory = {("field", f"stats.ability_scores.{ability}.score", "base")
                     for ability in ("str", "dex", "con", "int", "wis", "cha")}
        mandatory.update({("field", "stats.proficiency_bonus", "final"), ("field", "stats.max_hp", "final")})
        from .character_skill_adoptions import stored as skill_history
        from .character_builder_constants import SKILL_LABELS
        from .character_feature_proficiency_grants import automatic_history
        if len(automatic_expertise) > len(automatic_history(CharacterDefinition.from_dict(prior_payload))):
            for tool in definition.proficiencies.get("tools", []):
                mandatory.add(("proficiency", "proficiencies.tools." + str(tool).casefold(), "grant"))
                mandatory.add(("proficiency", "proficiencies.tool_expertise." + str(tool).casefold(), "grant"))
        prior_adoptions = skill_history(CharacterDefinition.from_dict(prior_payload))
        for adoption in skill_adoptions[len(prior_adoptions):]:
            key = ("proficiency", "skills." + SKILL_LABELS[adoption["skill_key"]].casefold(), "grant")
            mandatory.add(key)
            observed = values.get(key)
            if (type(observed) is not dict or observed.get("proficiency_level") != "proficient"
                    or type(observed.get("bonus")) is not int):
                return ()
        if not mandatory <= targets or not _sha256_hex(metadata.get("source_snapshot_digest")):
            return ()
        for marker in batch:
            key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
            if (not _valid_numeric_witness_marker(marker, character, PROVENANCE)
                    or marker.get("action_id") != origin.get("action_id") or stored.count(marker) != 1
                    or key not in values or marker.get("value_digest") != numeric_value_digest(values[key])
                    or not _sha256_hex(bases.get(marker["target_id"]))):
                return ()
        return (*tuple({"authorization": deepcopy(marker),
                      "source_basis_digest": bases[marker["target_id"]]} for marker in batch),
                *parent_custody(definition, origin, facet_mappings),
                *armor_custody(definition, origin, armor_choices),
                *skill_custody(definition, origin, skill_adoptions),
                *tracker_custody(definition, origin, tracker_associations),
                *automatic_custody(definition, origin, automatic_expertise),
                *conditional_custody(definition, origin, proficiency_conditions),
                *recipe_custody(definition, origin, artificer_recipes),
                *history_custody(definition, origin, feature_history))
    except (KeyError, TypeError, ValueError):
        return ()


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'deepcopy',
    'reconstructed_input_bases',
))
