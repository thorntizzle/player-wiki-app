"""Explicit retained recipe choices; knowledge never establishes an assignment.

Serialized choices are observations until independently recovered reconstruction
custody and current source/class/feature qualification agree.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from .character_parent_facets import digest, exact_ref
from .character_source_repair import SourceRepairError
from .systems_feature_capacities import ARTIFICER, INFUSE

FRAME = "artificer_recipe_choices"
ORIGIN = "artificer_recipe_digest"
CUSTODY = "artificer_recipe_custody"
CONFIRM = "confirm_artificer_recipes"
UNKNOWN = "__unresolved_recipes__"
REPLICATE = "dnd-5e|optionalfeature|tce|replicatemagicitem"


def typed_mode(definition):
    frame = definition.source.get("native_reconstruction_choices")
    origin = definition.source.get("native_reconstruction")
    return (type(frame) is dict and FRAME in frame
            or type(origin) is dict and ORIGIN in origin)


def _ref(entry):
    from .character_builder_equipment import _systems_ref_from_entry
    return _systems_ref_from_entry(entry)


def _entry(definition, service, ref, types):
    from .character_feature_values import _exact_entry
    entry = _exact_entry(service, definition.campaign_slug, ref) if service and exact_ref(ref) else None
    enabled = getattr(service, "is_entry_enabled_for_campaign", None)
    if (entry is None or entry.entry_type not in types or entry.library_slug != "DND-5E"
            or not callable(enabled) or not enabled(definition.campaign_slug, entry)):
        raise SourceRepairError("A recipe source identity is unavailable or changed.")
    return entry


def _features(definition):
    rows = definition.features
    if any(type(row) is not dict or type(row.get("id")) is not str or not row["id"] for row in rows):
        raise SourceRepairError("Recipe ownership needs stable feature identities.")
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise SourceRepairError("Recipe feature identities are ambiguous.")
    return result


def _owner(definition, service):
    rows = [row for row in definition.profile.get("classes", []) if type(row) is dict
            and type(row.get("systems_ref")) is dict and row["systems_ref"].get("entry_key") == ARTIFICER]
    if len(rows) != 1 or type(rows[0].get("row_id")) is not str or not rows[0]["row_id"]:
        raise SourceRepairError("Recipe choices need one exact Artificer class owner.")
    row = rows[0]
    if row.get("page_ref") or type(row.get("level")) is not int or not 2 <= row["level"] <= 20:
        raise SourceRepairError("Recipe choices need an attained Artificer class owner.")
    if sum(type(r) is dict and r.get("row_id") == row["row_id"] for r in definition.profile.get("classes", [])) != 1:
        raise SourceRepairError("Recipe class-row identity is ambiguous.")
    cls = _entry(definition, service, row["systems_ref"], {"class"})
    if cls.source_id != "TCE":
        raise SourceRepairError("Recipe owner is not the supported Artificer publication.")
    progression = cls.metadata.get("optionalfeature_progression")
    matches = [r for r in progression if type(r) is dict and r.get("featureType") == ["AI"]] if type(progression) is list else []
    if len(matches) != 1 or type(matches[0].get("progression")) is not list or len(matches[0]["progression"]) != 20:
        raise SourceRepairError("Known recipes need their current source progression.")
    progression = matches[0]["progression"]
    if any(type(v) is not int or not 0 <= v <= 40 for v in progression):
        raise SourceRepairError("Known recipe progression is malformed.")
    owners = [r for r in _features(definition).values() if type(r.get("systems_ref")) is dict
              and r["systems_ref"].get("entry_key") == INFUSE]
    if len(owners) != 1 or owners[0].get("page_ref") or owners[0].get("class_row_id") not in (None, "", row["row_id"]):
        raise SourceRepairError("Recipe choices need one retained Infuse Item owner.")
    feature = owners[0]
    entry = _entry(definition, service, feature["systems_ref"], {"classfeature"})
    from .systems_feature_capacities import SPECS
    from .systems_feature_values import source_digest
    if source_digest(entry.body) != SPECS[INFUSE]["body_sha256"]:
        raise SourceRepairError("Infuse Item rules need a reviewed ownership contract.")
    if (entry.metadata.get("class_name"), entry.metadata.get("class_source"), entry.metadata.get("level")) != ("Artificer", "TCE", 2):
        raise SourceRepairError("Infuse Item has an incompatible owning source.")
    return row, cls, feature, entry, progression[row["level"] - 1]


def _recipe(definition, service, feature, owner):
    entry = _entry(definition, service, feature.get("systems_ref"), {"optionalfeature"})
    if (entry.source_id != "TCE" or entry.metadata.get("feature_type") != ["AI"] or feature.get("page_ref")
            or feature.get("class_row_id") not in (None, "", owner["row_id"])):
        raise SourceRepairError("Recipe has no exact supported Artificer owner.")
    prerequisites = entry.metadata.get("prerequisite")
    if prerequisites is not None:
        if type(prerequisites) is not list or len(prerequisites) != 1 or type(prerequisites[0]) is not dict:
            raise SourceRepairError("Recipe prerequisite alternatives are unsupported.")
        rule = prerequisites[0]
        if set(rule) - {"item", "level"}:
            raise SourceRepairError("Recipe has an unsupported knowledge prerequisite.")
        if "item" in rule and (type(rule["item"]) is not list or not rule["item"]
                or any(type(v) is not str or not v.strip() for v in rule["item"])):
            raise SourceRepairError("Recipe item prerequisite is malformed.")
        if "level" in rule:
            level = rule["level"]
            if (type(level) is not dict or set(level) != {"class", "level"}
                    or level["class"] != {"name": "Artificer", "source": "TCE"}
                    or type(level["level"]) is not int or not 1 <= level["level"] <= owner["level"]):
                raise SourceRepairError("Recipe class prerequisite is not attained.")
    return entry


def _results(definition, service, entry, level):
    if entry.entry_key != REPLICATE:
        return [None]
    from .repository import normalize_lookup
    result = []
    for table in entry.body.get("entries", []):
        if type(table) is not dict or table.get("type") != "table":
            continue
        match = re.fullmatch(r"Replicable Items \((\d+)(?:nd|th)-Level Artificer\)", str(table.get("caption", "")))
        if not match or int(match[1]) > level:
            continue
        if table.get("colLabels") != ["Magic Item", "Attunement"] or type(table.get("rows")) is not list:
            raise SourceRepairError("Replicate result table has unsupported structure.")
        for row in table["rows"]:
            if type(row) is not list or len(row) != 2 or type(row[0]) is not str:
                raise SourceRepairError("Replicate result cell is malformed.")
            tag = re.fullmatch(r"\{@item ([^{}|]+)(?:\|([^{}|]+))?\}(?: \(detailed in \{@book [^{}]+\}\))?", row[0])
            if not tag:
                raise SourceRepairError("Replicate result needs an explicit supported item reference.")
            source = tag[2] or "DMG"
            key = "dnd-5e|item|" + source.lower() + "|" + normalize_lookup(tag[1])
            item = service.get_entry_for_campaign(definition.campaign_slug, key)
            if item is None:
                continue  # Unadmitted results are not offered.
            ref = _ref(item)
            try:
                _entry(definition, service, ref, {"item"})
            except SourceRepairError:
                continue
            if item.source_id != source or normalize_lookup(item.title) != normalize_lookup(tag[1]):
                raise SourceRepairError("Replicate result identity contradicts its source tag.")
            if ref in result:
                raise SourceRepairError("Replicate result identity is ambiguous.")
            result.append(ref)
    return result


def _context(definition, service):
    owner, cls, parent, parent_entry, capacity = _owner(definition, service)
    loader = getattr(service, "collect_attained_deterministic_feature_entries", None)
    if (not callable(loader) or INFUSE not in {entry.entry_key for entry in
            loader(definition.campaign_slug, cls, attained_level=owner["level"])}):
        raise SourceRepairError("Infuse Item is not a current attained grant of this class.")
    rows = []
    for feature in _features(definition).values():
        ref = feature.get("systems_ref")
        if type(ref) is not dict or ref.get("entry_type") != "optionalfeature":
            continue
        entry = _entry(definition, service, ref, {"optionalfeature"})
        if entry.metadata.get("feature_type") != ["AI"]:
            continue
        entry = _recipe(definition, service, feature, owner)
        rows.append((feature, entry, _results(definition, service, entry, owner["level"])))
    if not rows or len(rows) > capacity:
        raise SourceRepairError("Retained recipes exceed current knowledge capacity or are absent.")
    basis = {"class_row_id": owner["row_id"], "class_ref": _ref(cls), "parent_id": parent["id"],
             "parent_ref": _ref(parent_entry), "recipes": [r[0]["id"] for r in rows],
             "sources": [{"metadata": e.metadata, "body": e.body} for e in [cls, parent_entry, *[r[1] for r in rows]]]}
    return owner, basis, rows


def _field(identity):
    return "artificer_recipe_result_" + digest(identity)[:24]


def is_recipe_input(name):
    """Closed transport names; current form options still own admission."""
    return (type(name) is str and (name == CONFIRM
            or re.fullmatch(r"artificer_recipe_result_[0-9a-f]{24}", name) is not None))


def choice_fields(definition, service, values):
    if definition.system != "DND-5E":
        return []
    try:
        owner, basis, rows = _context(definition, service)
    except (ValueError, TypeError, KeyError):
        return []
    fields = [{"name": CONFIRM, "label": "Known Artificer recipes", "kind": "recipe_ownership",
        "group_key": "reconstruction:artificer_recipes", "selected": values.get(CONFIRM, UNKNOWN),
        "help_text": "Confirm these retained recipes as known. This creates no infused object and changes no counter: " + ", ".join(e.title for _, e, _ in rows),
        "options": [{"label": "Retain unresolved historical knowledge", "value": UNKNOWN},
                    {"label": "Confirm the complete retained recipe set", "value": digest(basis)}]}]
    for feature, entry, options in rows:
        if entry.entry_key == REPLICATE:
            fields.append({"name": _field(feature["id"]), "label": "Replicate result: " + feature["name"],
                "kind": "recipe_result", "group_key": "reconstruction:artificer_recipe:" + feature["id"],
                "selected": values.get(_field(feature["id"]), UNKNOWN),
                "help_text": "Choose the known result type, not a physical item or recipient.",
                "options": [{"label": "Unresolved result", "value": UNKNOWN},
                            *[{"label": ref["title"], "value": digest(ref)} for ref in options]]})
    return fields


def compose(prior, payload, service, values):
    from .character_models import CharacterDefinition
    frame = payload["source"]["native_reconstruction_choices"]
    if values.get(CONFIRM, UNKNOWN) == UNKNOWN:
        if typed_mode(prior):
            raise SourceRepairError("Retain the previously confirmed recipe choices.")
        return
    owner, basis, rows = _context(prior, service)
    if values.get(CONFIRM) != digest(basis):
        raise SourceRepairError("Recipe sources changed; review the current retained choices.")
    choices = []
    for feature, entry, options in rows:
        selected = None
        if entry.entry_key == REPLICATE:
            matches = [ref for ref in options if digest(ref) == values.get(_field(feature["id"]))]
            if len(matches) != 1:
                raise SourceRepairError("Confirm each exact source-backed Replicate result.")
            selected = matches[0]
        choices.append({"schema_version": 1, "feature_id": feature["id"], "class_row_id": owner["row_id"],
                        "systems_ref": _ref(entry), "selected_item_ref": selected,
                        "prior_feature_json": json.dumps(feature, sort_keys=True, ensure_ascii=False, separators=(",", ":"))})
    frame[FRAME] = choices
    validate(prior, CharacterDefinition.from_dict(payload), service)


def stored(definition):
    frame = definition.source.get("native_reconstruction_choices")
    if not typed_mode(definition):
        return ()
    rows = frame.get(FRAME) if type(frame) is dict else None
    if type(rows) is not list or not rows or len(rows) > 40:
        raise SourceRepairError("Typed recipe ownership is missing or malformed.")
    features = _features(definition)
    inputs = frame.get("inputs")
    if (type(inputs) is not dict or type(inputs.get(CONFIRM)) is not str
            or re.fullmatch(r"[0-9a-f]{64}", inputs[CONFIRM]) is None):
        raise SourceRepairError("Recipe acquisition has no explicit source-bound confirmation.")
    ids, selections = set(), set()
    keys = {"schema_version", "feature_id", "class_row_id", "systems_ref", "selected_item_ref", "prior_feature_json"}
    for row in rows:
        if (type(row) is not dict or set(row) != keys or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or type(row["feature_id"]) is not str or row["feature_id"] in ids
                or type(row["class_row_id"]) is not str or not row["class_row_id"]
                or not exact_ref(row["systems_ref"]) or row["systems_ref"]["entry_type"] != "optionalfeature"
                or type(row["prior_feature_json"]) is not str or len(row["prior_feature_json"]) > 100000):
            raise SourceRepairError("Typed recipe acquisition is invalid.")
        original = json.loads(row["prior_feature_json"])
        current = features.get(row["feature_id"])
        if type(original) is not dict or type(current) is not dict or current != original or current.get("systems_ref") != row["systems_ref"]:
            raise SourceRepairError("Typed recipe lost its exact retained feature observation.")
        ref = row["selected_item_ref"]
        if (row["systems_ref"]["entry_key"] == REPLICATE) != (ref is not None):
            raise SourceRepairError("Replicate needs an explicit selected result, and other recipes do not.")
        if ref is not None and (not exact_ref(ref) or ref["entry_type"] != "item"):
            raise SourceRepairError("Recipe result identity is malformed.")
        if ref is not None and inputs.get(_field(row["feature_id"])) != digest(ref):
            raise SourceRepairError("Recipe result has no matching explicit selected input.")
        key = (row["systems_ref"]["entry_key"], ref["entry_key"] if ref else None)
        if key in selections:
            raise SourceRepairError("Duplicate recipe acquisition needs a separate supported choice.")
        ids.add(row["feature_id"]); selections.add(key)
    return tuple(deepcopy(rows))


def validate(prior, candidate, service=None):
    rows, old = stored(candidate), stored(prior)
    if old and old != rows:
        raise SourceRepairError("Recipe adoption cannot replace or drop earlier choices.")
    if not rows:
        return rows
    before = _features(prior)
    for row in rows:
        if before.get(row["feature_id"]) != json.loads(row["prior_feature_json"]):
            raise SourceRepairError("Recipe adoption changed its prior feature.")
    if service is not None:
        owner, basis, options = _context(candidate, service)
        if candidate.source["native_reconstruction_choices"]["inputs"].get(CONFIRM) != digest(basis):
            raise SourceRepairError("Recipe confirmation does not match current source conditions.")
        current = {f["id"]: (entry, results) for f, entry, results in options}
        if set(current) != {r["feature_id"] for r in rows}:
            raise SourceRepairError("Recipe adoption must describe the entire retained source-linked set.")
        for row in rows:
            entry, results = current[row["feature_id"]]
            if row["class_row_id"] != owner["row_id"] or row["systems_ref"] != _ref(entry) or row["selected_item_ref"] not in results:
                raise SourceRepairError("Current recipe ownership or selected result is unsupported.")
    return rows


def custody(definition, origin, rows):
    if not rows:
        return ()
    return ({CUSTODY: {"campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
                      "action_id": origin["action_id"], "digest": digest(list(rows))}},)


def view(definition, state, authority, service):
    frame = {"typed": typed_mode(definition), "available": False, "known": [],
             "reason": "Known recipe ownership is not qualified; current assignments remain unchanged."}
    if not frame["typed"]:
        return frame
    try:
        from .character_source_authority import numeric_value_digest
        if (authority is None or (authority.original_definition_digest or authority.definition_digest) != numeric_value_digest(definition.to_dict())
                or authority.state_digest != numeric_value_digest(state)):
            return frame
        rows = validate(definition, definition, service)
        origin = definition.source.get("native_reconstruction")
        if type(origin) is not dict or origin.get(ORIGIN) != digest(list(rows)):
            return frame
        expected = custody(definition, origin, rows)[0]
        witnesses = [json.loads(raw) for raw in authority.verified_numeric_actions]
        if expected not in witnesses:
            return frame
        owner, cls, parent, parent_entry, capacity = _owner(definition, service)
        if owner["row_id"] not in authority.verified_class_rows or authority.status_for("feature", parent["id"]) != "VERIFIED":
            return frame
        known = []
        for row in rows:
            if authority.status_for("feature", row["feature_id"]) != "VERIFIED":
                return frame
            ref, result = row["systems_ref"], row["selected_item_ref"]
            known.append({"infusion_key": ref["entry_key"] + ("::" + result["entry_key"] if result else ""),
                          "name": ref["title"] + (" (" + result["title"] + ")" if result else ""),
                          "source_feature_id": row["feature_id"], "systems_ref": deepcopy(ref),
                          "selected_item_ref": deepcopy(result)})
        from .systems_feature_capacities import current_capacity
        try:
            active_capacity = current_capacity(parent_entry, cls, owner["level"])
        except ValueError:
            active_capacity = None
        frame.update(available=True, known=known, known_capacity=capacity, active_capacity=active_capacity,
                     class_level=owner["level"], reason="Known recipes verified; active assignments are separate.")
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return frame


def validate_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    old, new = stored(prior_record.definition), stored(candidate)
    if old == new:
        return
    from .character_reconstruction_authority import PendingNativeReconstruction
    if type(proof) is not PendingNativeReconstruction or proof.artificer_recipes != new:
        raise SourceRepairError("Recipe ownership changes require the exact reviewed reconstruction.")
    proof.validate_binding(prior_record, candidate, state, actor_id)
