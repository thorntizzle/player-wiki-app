"""Bounded current-level native reconstruction composition.

The manager supplies typed inputs and confirms current owner choices. No form
field accepts replacement definitions, play state, serialized metadata or proof.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character_models import CharacterDefinition
from .character_source_repair import SourceRepairError


KEYS = ("str", "dex", "con", "int", "wis", "cha")
STATIC_FIELDS = frozenset({"confirm_build", "hp_pool_numerator", "hp_pool_denominator",
    "hp_boundary", "hp_reference_con", "hp_history_start", "confirm_hp_effects",
    "confirm_hp_adjustment_absorbed", "hp_adjustment_absorbed_value"}
    | {f"{prefix}_{key}" for prefix in ("base", "species", "advancement", "provenance") for key in KEYS})


def retain_reconstruction_content(composed, derived):
    """Merge rule outputs onto retained owners, never persist a read projection.

    Definition-owned prepared/equipment flags, descriptions, source selections
    and unknown content stay exactly as composed. SourceAuthority's transient
    suppression/authority annotations are not original observations.
    """
    payload = deepcopy(composed.to_dict())
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not key.startswith("authority_") and key != "mechanics_suppressed"}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return deepcopy(value)
    # Normalization starts from an effective projection and may drop unknown
    # observations. Copy only its owned outputs onto the retained raw frame.
    for field in ("max_hp", "proficiency_bonus", "initiative_bonus", "armor_class", "speed",
                  "passive_perception", "passive_insight", "passive_investigation",
                  "carrying_capacity", "push_drag_lift", "attack_reminder_state", "defensive_state"):
        if field in derived.stats:
            payload["stats"][field] = clean(derived.stats[field])
    for ability, output in dict(derived.stats.get("ability_scores") or {}).items():
        if not isinstance(output, dict):
            continue
        existing = payload["stats"].setdefault("ability_scores", {}).get(ability)
        if existing is None:
            payload["stats"]["ability_scores"][ability] = clean(output)
        elif isinstance(existing, dict):
            for field in ("score", "modifier", "save_bonus"):
                if field in output:
                    existing[field] = clean(output[field])
    def merge_rows(old, new, identity, fields):
        if not isinstance(old, list):
            return deepcopy(old)
        if not isinstance(new, list):
            raise SourceRepairError("Derived rule outputs have an invalid retained owner list.")
        found = {}
        for row in new:
            if not isinstance(row, dict) or not row.get(identity):
                continue
            if row[identity] in found:
                raise SourceRepairError("Derived rule outputs have an ambiguous retained owner.")
            found[row[identity]] = row
        result = deepcopy(old)
        for row in result:
            if not isinstance(row, dict) or row.get(identity) not in found:
                continue
            current = found[row[identity]]
            for field in fields:
                if field in current:
                    row[field] = clean(current[field])
        return result
    payload["skills"] = merge_rows(composed.skills, derived.skills, "name", ("bonus",))
    from .character_skill_adoptions import retain_derived_bonuses
    retain_derived_bonuses(composed, derived, payload)
    payload["attacks"] = merge_rows(composed.attacks, derived.attacks, "id",
        ("attack_bonus", "damage", "damage_type"))
    payload["resource_templates"] = merge_rows(composed.resource_templates, derived.resource_templates, "id", ("max",))
    if not isinstance(composed.spellcasting, dict) or not isinstance(derived.spellcasting, dict):
        return CharacterDefinition.from_dict(payload)
    for family, identity in (("class_rows", "class_row_id"), ("source_rows", "source_row_id")):
        if family == "class_rows" and family not in composed.spellcasting:
            # A flat advancement payload has no saved casting rows to retain.
            # Normalization derived these from the complete current profile and
            # sources, together with its slot lanes. Keep that owned structure;
            # never recover it by copying the prior level's rows or a header.
            payload["spellcasting"][family] = clean(derived.spellcasting.get(family, []))
        if family in composed.spellcasting:
            payload["spellcasting"][family] = merge_rows(composed.spellcasting[family], derived.spellcasting.get(family, []),
                identity, ("spell_save_dc", "spell_attack_bonus", "spellcasting_ability", "slot_progression", "spell_metric_provenance"))
        if family in payload["spellcasting"]:
            # Persist the native base recipe, not a current equipped item's
            # formula bonus. The read projection applies those qualified item
            # effects once. Explicit sourced overrides remain untouched.
            from .character_builder_constants import ABILITY_LABELS
            ability_keys = {label: key for key, label in ABILITY_LABELS.items()}
            for row in payload["spellcasting"][family]:
                if not isinstance(row, dict):
                    continue
                key = ability_keys.get(row.get("spellcasting_ability"))
                score = dict(derived.stats.get("ability_scores", {}).get(key) or {}).get("score")
                pb = derived.stats.get("proficiency_bonus")
                if type(score) is not int or type(pb) is not int:
                    continue
                for metric, offset in (("spell_attack_bonus", 0), ("spell_save_dc", 8)):
                    if dict(row.get("spell_metric_provenance") or {}).get(metric) == {"kind": "formula"}:
                        row[metric] = offset + pb + (score - 10) // 2
    # Slot capacities are rule output, while the SQLite spent observations and
    # every definition-owned spell row/mark remain untouched.
    for field in ("slot_progression", "slot_lanes", "spell_save_dc", "spell_attack_bonus", "spellcasting_ability"):
        if field in derived.spellcasting:
            payload["spellcasting"][field] = clean(derived.spellcasting[field])
    class_rows = payload["spellcasting"].get("class_rows")
    if isinstance(class_rows, list) and len(class_rows) == 1 and isinstance(class_rows[0], dict):
        for field in ("spell_save_dc", "spell_attack_bonus", "spellcasting_ability", "spell_metric_provenance"):
            if field in class_rows[0]:
                payload["spellcasting"][field] = deepcopy(class_rows[0][field])
    return CharacterDefinition.from_dict(payload)


def bounded_inputs(value):
    if (not isinstance(value, dict) or not 1 <= len(value) <= 160
            or any(not isinstance(key, str) or len(key) > 160 or not isinstance(item, str)
                   or len(item) > 512 or "\x00" in item for key, item in value.items())):
        raise SourceRepairError("The reconstruction inputs exceed the bounded choice form.")
    from .character_infusion_recipes import is_recipe_input
    if any(key not in STATIC_FIELDS and not key.startswith(("feature_", "feat_", "item_link_", "skill_adoption_"))
           and not is_recipe_input(key) for key in value):
        raise SourceRepairError("Only explicit reconstruction choices are accepted.")
    return deepcopy(value)


def _number(values, key, low, high):
    raw = values.get(key, "")
    if not raw or not raw.isascii() or not raw.isdecimal() or not low <= int(raw) <= high:
        raise SourceRepairError(f"Enter a whole number from {low} to {high} for {key.replace('_', ' ')}.")
    return int(raw)


def reconstruction_context(definition, service, pages, values=None, *, state=None):
    from . import character_builder as builder
    from .character_profile import profile_class_rows
    from .character_builder_equipment import _systems_ref_from_entry
    rows = profile_class_rows(definition.profile)
    if len(rows) != 1:
        raise SourceRepairError("Native reconstruction currently needs one exact class row.")
    def entry(ref, types):
        if not isinstance(ref, dict) or not ref.get("entry_key"):
            raise SourceRepairError("A reconstruction source needs an exact source identity.")
        result = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if (result is None or result.entry_type not in types
                or any(ref.get(key) and ref[key] != getattr(result, key, None) for key in ("entry_key", "slug", "source_id", "entry_type"))):
            raise SourceRepairError("A reconstruction source is missing, disabled, or belongs to another owner.")
        return result
    cls = entry(rows[0].get("systems_ref"), {"class"})
    species = entry(definition.profile.get("species_ref"), {"race", "subrace"})
    background = entry(definition.profile.get("background_ref"), {"background"})
    subclass = entry(rows[0]["subclass_ref"], {"subclass"}) if rows[0].get("subclass_ref") else None
    choices, feature_selections, feat_selections, owner_entries = [], [], [], {}
    feat_sources = set()
    for feature in definition.features:
        if not isinstance(feature, dict) or not dict(feature.get("systems_ref") or {}).get("entry_key"):
            continue
        current = entry(feature["systems_ref"], {"feature", "classfeature", "subclassfeature", "feat", "optionalfeature", "race", "subrace", "background", "subclass"})
        if current.entry_type == "subclass":
            from .character_subclass_companion import selected_subclass_companion_matches
            if not selected_subclass_companion_matches(feature, definition.profile, current, service, definition.campaign_slug):
                raise SourceRepairError("A retained subclass container is not the exact inert selected subclass.")
        identity = str(feature.get("id") or "")
        if not identity or identity in owner_entries:
            raise SourceRepairError("Feature owner identities are ambiguous.")
        from .character_armor_models import SUMMARY_FIELD, _summary
        if identity == dict(values or {}).get(SUMMARY_FIELD) and _summary(feature):
            continue  # Exact historical row is retained, never canonicalized into a level-15 grant.
        owner_entries[identity] = current
        if current.entry_type == "subclass":
            continue  # Retained context only, never expertise/feat choices.
        if current.entry_type in {"race", "subrace", "background"}:
            from .character_parent_facets import linked_companion_facet
            if linked_companion_facet(feature, definition.profile, current) is None:
                raise SourceRepairError("A retained parent companion has no exact inert current facet.")
            continue  # The selected parent owns choices; this row is narrative only.
        if current.entry_type == "feat":
            if current.entry_key in feat_sources:
                raise SourceRepairError("A repeated feat source needs an explicit supported ownership disposition.")
            feat_sources.add(current.entry_key)
            feat_selections.append({"entry": current, "instance_key": identity})
        elif builder._supported_feature_expertise_blocks(current):
            feature_selections.append({"entry": current, "instance_key": identity})
    fields = builder._build_feature_choice_fields(feature_selections=feature_selections, values=dict(values or {}), include_proficiency_grants=False)
    fields += builder._build_feat_choice_fields(feat_selections=feat_selections, values=dict(values or {}),
        optionalfeature_catalog={}, item_catalog={})
    for field in fields:
        if str(field.get("group_key", "")).endswith(":expertise"):
            field["options"] = [{"label": "Unresolved retained expertise — no dependent grant issued",
                                  "value": "__unresolved_" + field["name"] + "__"}, *field["options"]]
    from .character_reconstruction_proficiencies import current_owners, choice_fields, weapon_mapping_fields
    item_catalog = builder._effective_item_catalog_for_definition(
        definition, systems_service=service, campaign_page_records=pages)
    fields += choice_fields(definition, current_owners(definition, service), dict(values or {}), item_catalog=item_catalog, service=service)
    fields += weapon_mapping_fields(definition, cls, dict(values or {}))
    from .character_reconstruction_instruments import choice_context
    instrument_fields, instrument_catalog = choice_context(
        definition, background, service, pages, dict(values or {}))
    fields += instrument_fields
    from .character_parent_facets import choice_fields as parent_facet_fields
    fields += parent_facet_fields(definition, service, dict(values or {}))
    from .character_infusion_recipes import choice_fields as recipe_fields
    fields += recipe_fields(definition, service, dict(values or {}))
    from .character_armor_models import choice_fields as armor_model_fields
    fields += armor_model_fields(definition, service, dict(values or {}))
    from .character_feature_history import choice_fields as history_fields
    fields += history_fields(definition, service, dict(values or {}))
    if fields:
        choices.append({"title": "Current feature and feat choices", "fields": fields})
    history = dict(definition.source.get("native_progression") or {}).get("history", [])
    boundaries = []
    if isinstance(history, list):
        for index in range(len(history) + 1):
            events = [row for row in history[index:] if isinstance(row, dict) and row.get("kind") == "level_up"]
            boundary = events[0].get("from_level") if events else rows[0].get("level")
            if type(boundary) is not int:
                continue
            cursor = boundary
            for event in events:
                if (event.get("from_level") != cursor or event.get("to_level") != cursor + 1
                        or event.get("target_level") != cursor + 1):
                    break
                cursor += 1
            else:
                if cursor == rows[0].get("level"):
                    date = str(events[0].get("at") or events[0].get("recorded_at_utc") or events[0].get("created_at_utc") or events[0].get("occurred_at") or "date retained in history") if events else ""
                    label = (f"Pool ends at level {boundary}; retain {len(events)} actual later level gain(s), beginning {date}"
                             if events else f"Pool ends at current level {boundary}; no later level gains")
                    # Adjacent non-level events do not create different HP policies.
                    if not any(row["boundary"] == boundary for row in boundaries):
                        boundaries.append({"value": str(index), "boundary": boundary, "label": label})
    from .character_reconstruction_items import choice_fields as item_choice_fields
    from .character_skill_adoptions import choice_fields as skill_adoption_fields
    from .character_tracker_associations import choice_fields as tracker_fields
    from .character_feature_proficiency_grants import automatic_fields
    return {"class": cls, "species": species, "background": background, "subclass": subclass,
            "instrument_catalog": instrument_catalog,
            "skill_adoption_fields": skill_adoption_fields(definition, service),
            "automatic_expertise_fields": automatic_fields(definition, service),
            "tracker_association_fields": tracker_fields(definition, state, service, pages, values) if state is not None else [],
            "item_mapping_fields": item_choice_fields(definition, service, pages, dict(values or {})),
            "row": rows[0], "choice_sections": choices, "feature_selections": feature_selections,
            "hp_boundaries": boundaries,
            "historical_hp_adjustment": dict(definition.stats.get("manual_adjustments") or {}).get("max_hp"),
            "feat_selections": feat_selections, "owner_entries": owner_entries,
            "owners": [{"id": identity, "label": entry.title, "source": entry.source_id}
                       for identity, entry in owner_entries.items()]}


def compose_reconstruction(*, record, inputs, systems_service, campaign_page_records,
                           verified_numeric_actions=()):
    retained = record.definition.source.get("native_reconstruction_choices")
    if isinstance(retained, dict) and retained.get("language_elective_outcomes"):
        raise SourceRepairError("Use the language decision review; full build reconstruction cannot discard elective decision history.")
    from . import character_builder as builder
    from .character_ability_inputs import seed_base_inputs
    from .character_hp_recipe import canonical_recipe, evaluate_recipe
    from .character_hit_dice import _hit_die_faces_for_class_row
    from .character_builder_equipment import _systems_ref_from_entry
    from .character_builder_derivation import _campaign_option_feat_selections_from_features, _campaign_option_feat_selected_choices_from_features
    values = bounded_inputs(inputs)
    context = reconstruction_context(record.definition, systems_service, campaign_page_records, values,
        state=record.state_record.state)
    allowed = (STATIC_FIELDS | {field["name"] for section in context["choice_sections"] for field in section["fields"]}
               | {field["name"] for field in context["item_mapping_fields"]}
               | {field["name"] for field in context["skill_adoption_fields"]}
               | {field["name"] for field in context["tracker_association_fields"]}
               | {field["name"] for field in context["automatic_expertise_fields"]})
    if set(values) - allowed or values.get("confirm_build") != "yes" or values.get("confirm_hp_effects") != "yes":
        raise SourceRepairError("Confirm the complete retained build and the current HP effect ledger.")
    _, choices = builder._resolve_builder_choices(context["choice_sections"], values, strict=True)
    scores = {key: _number(values, f"base_{key}", 1, 30) for key in KEYS}
    species_bonuses = {key: _number(values, f"species_{key}", 0, 2) for key in KEYS}
    advancements = {key: _number(values, f"advancement_{key}", 0, 10) for key in KEYS}
    # Native source ability blocks admit fixed grants or an explicit bounded
    # choice. A displayed final ability never supplies an allocation.
    blocks = context["species"].metadata.get("ability") or context["species"].metadata.get("ability_bonuses") or []
    if isinstance(blocks, dict):
        blocks = [blocks]
    def species_matches(block):
        if not isinstance(block, dict):
            return False
        fixed = {key: block.get(key, 0) for key in KEYS}
        choose = block.get("choose")
        if choose is None:
            return species_bonuses == fixed
        if not isinstance(choose, dict):
            return False
        selected = [key for key in KEYS if species_bonuses[key] != fixed[key]]
        amount, count = choose.get("amount", 1), choose.get("count", 1)
        return (len(selected) == count and all(key in choose.get("from", KEYS)
            and species_bonuses[key] == fixed[key] + amount for key in selected)
            and all(species_bonuses[key] == fixed[key] for key in KEYS if key not in selected))
    if not blocks or not any(species_matches(block) for block in blocks):
        raise SourceRepairError("The explicit species ability allocation does not match its current native source.")
    level = context["row"].get("level")
    if type(level) is not int or not 1 <= level <= 20:
        raise SourceRepairError("The current class level is unavailable.")
    progression = builder._class_progression_for_builder(systems_service, record.definition.campaign_slug,
        context["class"], campaign_page_records=campaign_page_records)
    asi_levels = {row.get("level") for row in progression if type(row.get("level")) is int and row["level"] <= level
                  and any("abilityscoreimprovement" in builder.normalize_lookup(str(feature.get("title") or feature.get("name") or getattr(feature.get("entry"), "title", "")))
                          for feature in row.get("feature_rows", []))}
    if sum(advancements.values()) > 2 * len(asi_levels):
        raise SourceRepairError("The advancement ability allocation exceeds current class advancement choices.")
    payload = deepcopy(record.definition.to_dict())
    profile = payload["profile"]
    profile["classes"] = [deepcopy(context["row"])]
    profile["classes"][0]["systems_ref"] = _systems_ref_from_entry(context["class"])
    profile["class_ref"] = _systems_ref_from_entry(context["class"])
    profile["species_ref"] = _systems_ref_from_entry(context["species"])
    profile["background_ref"] = _systems_ref_from_entry(context["background"])
    from .character_reconstruction_instruments import compose_choice
    compose_choice(record.definition, profile, context["background"], context["instrument_catalog"], choices)
    if context["subclass"] is not None:
        profile["classes"][0]["subclass_ref"] = _systems_ref_from_entry(context["subclass"])
        profile["subclass_ref"] = _systems_ref_from_entry(context["subclass"])
    for feature in payload["features"]:
        current = context["owner_entries"].get(feature.get("id"))
        if current is not None:
            feature["systems_ref"] = _systems_ref_from_entry(current)
    feat_bonuses = builder._apply_feat_ability_score_bonuses({key: 0 for key in KEYS},
        feat_selections=context["feat_selections"], selected_choices=choices, strict=True)
    # Page-native feat effects already participate in ordinary derivation.
    modeled = builder._apply_feat_ability_score_bonuses({key: 0 for key in KEYS},
        feat_selections=_campaign_option_feat_selections_from_features(payload["features"]),
        selected_choices=_campaign_option_feat_selected_choices_from_features(payload["features"]), strict=False)
    seed_base_inputs(payload["stats"], scores, provenance="manager_native_reconstruction",
        fixed_bonuses={key: species_bonuses[key] + advancements[key] + feat_bonuses[key] - modeled[key] for key in KEYS})
    for key in KEYS:
        if values.get(f"provenance_{key}") not in {"original", "confirmed", "reconstructed"}:
            raise SourceRepairError("Choose honest input provenance for every original ability.")
        payload["stats"]["ability_inputs"]["scores"][key]["provenance"] = values[f"provenance_{key}"]
    permanent_scores = {key: min(20, scores[key] + species_bonuses[key] + advancements[key] + feat_bonuses[key]) for key in KEYS}
    boundary = _number(values, "hp_boundary", 4, level)
    history = deepcopy(dict(payload["source"].get("native_progression") or {}).get("history", []))
    start = _number(values, "hp_history_start", 0, len(history))
    if not any(row["value"] == str(start) and row["boundary"] == boundary for row in context["hp_boundaries"]):
        raise SourceRepairError("Choose the actual retained level boundary corresponding to the accepted HP pool.")
    faces = _hit_die_faces_for_class_row(context["row"])
    effects = [{"owner_id": selection["instance_key"], "per_level": amount}
               for selection in context["feat_selections"]
               if (amount := builder._feat_hit_point_bonus([selection], current_level=1))]
    reference_con = _number(values, "hp_reference_con", 1, 30)
    if reference_con != permanent_scores["con"]:
        raise SourceRepairError("The accepted HP reference Constitution must match the explicitly confirmed permanent build.")
    recipe = canonical_recipe({"schema_version": 1, "boundary_level": boundary,
        "reference_constitution": reference_con,
        "history_start": start, "retained_history_end": len(history), "corrections": [],
        "continuing_effects": effects, "pools": [
            {"from_level": 1, "to_level": 3, "aggregate": {"numerator": 3 * faces, "denominator": 1},
             "policy": "maximum", "provenance": "confirmed"},
            {"from_level": 4, "to_level": boundary,
             "aggregate": {"numerator": _number(values, "hp_pool_numerator", 1, 1000),
                           "denominator": _number(values, "hp_pool_denominator", 1, 1000)},
             "policy": "accepted_pool", "provenance": "reconstructed"}]}, faces=faces)
    # A historical correction can already be included in the confirmed pool.
    # Absorb only the exact explicitly confirmed prior adjustment. This is not
    # an automatic normalization of other current manual effects.
    absorption = None
    if "confirm_hp_adjustment_absorbed" in values or values.get("hp_adjustment_absorbed_value", "") != "":
        adjustments = payload["stats"].get("manual_adjustments")
        original = adjustments.get("max_hp") if type(adjustments) is dict else None
        if (values.get("confirm_hp_adjustment_absorbed") != "yes"
                or type(original) is not int or original == 0
                or values.get("hp_adjustment_absorbed_value") != str(original)):
            raise SourceRepairError("Confirm the exact historical HP adjustment already included in this pool.")
        absorption = {"original_adjustment": original, "disposition": "included_in_confirmed_physical_pool"}
        adjustments.pop("max_hp")
    source = payload["source"]
    source["source_type"] = "native_character_builder"
    source["native_progression"] = {**dict(source.get("native_progression") or {}), "hp_recipe": recipe}
    layers = {key: [] for key in KEYS}
    for key in KEYS:
        for owner, amount, entry in (("species", species_bonuses[key], context["species"]),
                                     ("class", advancements[key], context["class"])):
            if amount:
                layers[key].append({"owner_id": owner, "amount": amount, "systems_ref": _systems_ref_from_entry(entry)})
    for selection in context["feat_selections"]:
        bonus = builder._apply_feat_ability_score_bonuses({key: 0 for key in KEYS},
            feat_selections=[selection], selected_choices=choices, strict=True)
        for key in KEYS:
            if bonus[key]:
                layers[key].append({"owner_id": selection["instance_key"], "amount": bonus[key],
                                    "systems_ref": _systems_ref_from_entry(selection["entry"])})
    source["native_reconstruction_choices"] = {"schema_version": 1, "inputs": deepcopy(values),
                                               "choices": choices, "ability_layers": layers}
    from .character_parent_facets import compose_mappings as compose_parent_facets, FRAME_KEY
    source["native_reconstruction_choices"][FRAME_KEY] = compose_parent_facets(
        record.definition, systems_service, values)
    from .character_armor_models import compose as compose_armor_model, FRAME_KEY as ARMOR_MODEL_FRAME
    source["native_reconstruction_choices"][ARMOR_MODEL_FRAME] = compose_armor_model(
        record.definition, systems_service, values)
    if absorption is not None:
        source["native_reconstruction_choices"]["historical_hp_adjustment"] = absorption
    from .character_reconstruction_items import compose_mappings
    source["native_reconstruction_choices"]["item_source_mappings"] = compose_mappings(
        record.definition, payload, systems_service, campaign_page_records, values)
    from .character_reconstruction_proficiencies import apply_weapon_mappings
    mapped_weapons, weapon_mappings = apply_weapon_mappings(record.definition, context["class"], choices)
    payload["proficiencies"]["weapons"] = mapped_weapons
    source["native_reconstruction_choices"]["original_weapon_proficiencies"] = deepcopy(record.definition.proficiencies.get("weapons", []))
    source["native_reconstruction_choices"]["weapon_mappings"] = weapon_mappings
    prior_choices = dict(record.definition.source.get("native_reconstruction_choices") or {})
    if "original_weapon_proficiencies" in prior_choices:
        source["native_reconstruction_choices"]["original_weapon_proficiencies"] = deepcopy(prior_choices["original_weapon_proficiencies"])
        source["native_reconstruction_choices"]["weapon_mappings"] = deepcopy(prior_choices.get("weapon_mappings") or []) + weapon_mappings
    owners = [("class", context["class"]), ("species", context["species"]), ("background", context["background"]),
              *context["owner_entries"].items()]
    from .character_reconstruction_proficiencies import starting_grant
    source["native_reconstruction_choices"]["proficiency_owners"] = [
        {"owner_id": identity, "systems_ref": _systems_ref_from_entry(entry),
         "grant_categories": [category for category, fields in {
             "skills": ("skill_proficiencies", "expertise"), "languages": ("languages", "language_proficiencies", "communication_proficiencies"),
             "tools": ("tool_proficiencies", "expertise"), "tool_expertise": ("expertise",),
             "armor": ("armor_proficiencies",), "weapons": ("weapon_proficiencies",)}.items()
             if any(entry.metadata.get(key) for key in fields)
             or category in {"skills", "tools", "tool_expertise"} and builder._supported_feature_expertise_blocks(entry)
             or starting_grant(entry.metadata, category)]}
        for identity, entry in owners if entry.entry_type != "subclass"
        and (identity in {"class", "species", "background"} or entry.entry_type not in {"race", "subrace", "background"})]
    payload["stats"]["max_hp"] = evaluate_recipe(recipe, history, level=level,
        constitution=permanent_scores["con"], faces=faces)
    payload["stats"]["proficiency_bonus"] = 2 + (level - 1) // 4
    for key, score in permanent_scores.items():
        row = payload["stats"].setdefault("ability_scores", {}).setdefault(key, {})
        row["score"], row["modifier"] = score, (score - 10) // 2
    # Only a separate exact adoption confirmation may change an ordinary
    # none-level skill. Expertise remains a retained, independently owned choice.
    from .character_skill_adoptions import compose as compose_skill_adoptions
    compose_skill_adoptions(record.definition, payload, systems_service, values)
    from .character_tracker_associations import compose as compose_trackers
    compose_trackers(record.definition, payload, record.state_record.state, systems_service, campaign_page_records, values)
    from .character_feature_proficiency_grants import compose_automatic, compose_conditions
    compose_conditions(record.definition, payload, systems_service)
    compose_automatic(record.definition, payload, systems_service, values)
    from .character_infusion_recipes import compose as compose_recipes
    compose_recipes(record.definition, payload, systems_service, values)
    from .character_feature_history import compose as compose_history
    compose_history(record.definition, payload, systems_service, values)
    candidate = CharacterDefinition.from_dict(payload)
    # Selecting the reconstructed native class recipe is an explicit build
    # action. Derive its formula from the confirmed input/owner context rather
    # than treating an imported matching total as formula evidence. Explicit
    # manual/sourced metric records remain outside this replacement.
    from .character_builder_derivation import _spellcasting_row_payload_from_context
    from .character_spell_effects import reconcile_formula_row
    calculated = _spellcasting_row_payload_from_context({"row_id": context["row"]["row_id"],
        "row_level": level, "class_payload": context["row"], "selected_class": context["class"],
        "selected_subclass": context["subclass"]}, ability_scores=permanent_scores,
        proficiency_bonus=payload["stats"]["proficiency_bonus"])
    if calculated is not None:
        fresh = reconcile_formula_row(None, calculated)
        for row in payload["spellcasting"].get("class_rows", []):
            if not isinstance(row, dict) or row.get("class_row_id") != context["row"]["row_id"]:
                continue
            records = row.get("spell_metric_provenance")
            records = deepcopy(records) if isinstance(records, dict) else {}
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                if metric not in records:
                    row[metric] = fresh.get(metric)
                    records[metric] = deepcopy(fresh["spell_metric_provenance"][metric])
            row["spell_metric_provenance"] = records
        candidate = CharacterDefinition.from_dict(payload)
    from .character_reconstruction_authority import attained_reconstruction_features
    attained = attained_reconstruction_features(candidate, systems_service)
    payload["source"]["native_reconstruction_choices"]["initial_unattained_features"] = [
        {"id": row["id"], "name": row.get("name", row["id"])} for row in candidate.features
        if isinstance(row, dict) and dict(row.get("systems_ref") or {}).get("entry_type") in {"classfeature", "subclassfeature"}
        and dict(row.get("systems_ref") or {}).get("entry_key") not in attained]
    candidate = CharacterDefinition.from_dict(payload)
    from .character_native_requalification import _canonical_skill_inputs, _validate_current_proficiencies, _current_background_tools
    _canonical_skill_inputs(candidate)
    from .character_reconstruction_proficiencies import validate_current
    from .character_skill_adoptions import prepare_draft
    skill_draft = prepare_draft(record.definition, candidate, systems_service)
    from .character_feature_proficiency_grants import prepare_reconstruction
    feature_grant_draft = prepare_reconstruction(record.definition, candidate, systems_service)
    payload["source"]["native_reconstruction_choices"]["unresolved_proficiencies"] = validate_current(
        candidate, systems_service, elective_witnesses=verified_numeric_actions,
        skill_adoption_draft=skill_draft, feature_grant_draft=feature_grant_draft)
    candidate = CharacterDefinition.from_dict(payload)
    from .character_reconstruction_authority import reconstruction_source_links
    reconstruction_source_links(candidate, require_origin=False)
    return candidate, context
