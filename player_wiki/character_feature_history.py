"""Two explicit historical relations; neither supplies a mechanical owner.

Owner IDs refer to existing source-linked features. History stays byte-for-byte
in the definition; current source and recovered custody qualify only its citation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

from .character_parent_facets import digest
from .character_source_repair import SourceRepairError

FRAME = "feature_history_relations"
ORIGIN = "feature_history_digest"
CUSTODY = "feature_history_custody"
UNKNOWN = "__unresolved_feature_history__"
RECIPES = "artificer_recipe_summary"
STR_ACTION = "guardian_strength_alternative"
_FIELDS = {"schema_version", "feature_id", "prior_feature_json", "relation",
           "owner_feature_id", "class_row_id", "source_digest", "dependency_digest"}


def _features(definition):
    from .character_infusion_recipes import _features as exact_features
    return exact_features(definition)


def _field(identity):
    return "feature_history_" + digest(identity)[:24]


def _relation(feature):
    allowed = {"id", "name", "category", "source", "description_markdown",
               "activation_type", "class_row_id"}
    if (type(feature) is not dict or set(feature) - allowed
            or type(feature.get("id")) is not str or not feature["id"]
            or feature.get("category") != "class_feature"
            or any(feature.get(key) is not None and type(feature[key]) is not str
                   for key in ("source", "description_markdown", "class_row_id"))):
        return None
    # Labels discover a bounded choice; they never authorize the association.
    if feature.get("name") == "Artificer Infusions" and feature.get("activation_type") == "passive":
        return RECIPES
    if (feature.get("name") == "Guardian Armor: Thunder Gauntlets (STR)"
            and feature.get("activation_type") == "action"):
        return STR_ACTION
    return None


def _unique_owner(definition, service, key, class_id):
    from .character_builder_equipment import _systems_ref_from_entry
    rows = [row for row in _features(definition).values()
            if type(row.get("systems_ref")) is dict and row["systems_ref"].get("entry_key") == key]
    entry = service.get_entry_for_campaign(definition.campaign_slug, key)
    enabled = getattr(service, "is_entry_enabled_for_campaign", None)
    if (len(rows) != 1 or entry is None or not callable(enabled)
            or not enabled(definition.campaign_slug, entry)
            or rows[0].get("systems_ref") != _systems_ref_from_entry(entry)
            or rows[0].get("page_ref") or rows[0].get("class_row_id") not in (None, "", class_id)):
        raise SourceRepairError("Historical relation needs a unique current mechanical owner.")
    return rows[0]


def _base(definition, feature, service):
    relation = _relation(feature)
    if relation == RECIPES:
        from .character_infusion_recipes import _owner, _context
        owner, cls, parent, entry, _ = _owner(definition, service)
        _, basis, _ = _context(definition, service)
        source_basis = {"recipes": basis, "parent_metadata": entry.metadata,
                        "parent_body": entry.body, "class_metadata": cls.metadata}
        class_id = owner["row_id"]
    elif relation == STR_ACTION:
        from .character_armor_models import current_contract, MODEL, ARCANE, GAUNTLETS, FIELD
        contract = current_contract(definition, service)
        if not contract:
            raise SourceRepairError("Historical alternative needs the current Guardian source contract.")
        class_id = contract["class_row_id"]
        owners = [_unique_owner(definition, service, key, class_id) for key in (MODEL, ARCANE, GAUNTLETS, FIELD)]
        parent, source_basis = owners[2], contract
    else:
        raise SourceRepairError("This historical relation is unsupported.")
    if feature.get("class_row_id") not in (None, "", class_id) or feature["id"] == parent["id"]:
        raise SourceRepairError("Historical row and current owner must remain distinct in the same class.")
    return {"schema_version": 1, "feature_id": feature["id"],
            "prior_feature_json": json.dumps(feature, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            "relation": relation, "owner_feature_id": parent["id"], "class_row_id": class_id,
            "source_digest": digest(source_basis)}


def _dependency(definition, relation, service=None):
    if relation == RECIPES:
        from .character_infusion_recipes import validate
    else:
        from .character_armor_models import validate
    rows = validate(definition, definition, service)
    if not rows:
        raise SourceRepairError("Confirm the current recipe or model choices before associating their history.")
    return digest(list(rows))


def choice_fields(definition, service, values):
    result = []
    for feature in _features(definition).values():
        if not _relation(feature):
            continue
        try:
            row = _base(definition, feature, service)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        result.append({"name": _field(feature["id"]), "label": "Historical association: " + feature["name"],
            "kind": "feature_history", "group_key": "reconstruction:feature_history:" + feature["id"],
            "selected": values.get(_field(feature["id"]), UNKNOWN),
            "help_text": "Retain this row as history of the current owner. It supplies no additional benefit or action. Confirm the owning recipe/model choices separately.",
            "options": [{"label": "Unresolved; retain source warning", "value": UNKNOWN},
                        {"label": "Associate with the current owner as history only", "value": digest(row)}]})
    return result


def compose(prior, payload, service, values):
    from .character_models import CharacterDefinition
    definition = CharacterDefinition.from_dict(payload)
    rows = []
    for feature in _features(prior).values():
        selected = values.get(_field(feature["id"]), UNKNOWN)
        if selected == UNKNOWN:
            continue
        row = _base(definition, feature, service)
        if selected != digest(row):
            raise SourceRepairError("Historical association no longer matches its current offered owner.")
        rows.append({**row, "dependency_digest": _dependency(definition, row["relation"], service)})
    payload["source"]["native_reconstruction_choices"][FRAME] = rows
    validate(prior, CharacterDefinition.from_dict(payload), service)


def stored(definition):
    frame = definition.source.get("native_reconstruction_choices")
    origin = definition.source.get("native_reconstruction")
    rows = frame.get(FRAME, []) if type(frame) is dict else []
    if (type(rows) is not list or len(rows) > 2
            or not rows and type(origin) is dict and ORIGIN in origin):
        raise SourceRepairError("Historical associations are missing or malformed.")
    if not rows:
        # Unadopted history adds no identity requirement to ordinary reads/writes.
        return ()
    features, seen, relations = _features(definition), set(), set()
    for row in rows:
        if (type(row) is not dict or set(row) != _FIELDS
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or any(type(row[key]) is not str or not row[key] for key in _FIELDS - {"schema_version"})
                or row["relation"] not in {RECIPES, STR_ACTION}
                or row["feature_id"] in seen or row["relation"] in relations
                or len(row["prior_feature_json"]) > 100000
                or row["owner_feature_id"] == row["feature_id"]):
            raise SourceRepairError("Historical associations require distinct, bounded identities.")
        from .character_source_repair import _sha256_hex
        prior = json.loads(row["prior_feature_json"])
        base = {key: value for key, value in row.items() if key != "dependency_digest"}
        if (not _sha256_hex(row["source_digest"]) or not _sha256_hex(row["dependency_digest"])
                or _relation(prior) != row["relation"] or prior.get("id") != row["feature_id"]
                or features.get(row["feature_id"]) != prior or row["owner_feature_id"] not in features
                or prior.get("class_row_id") not in (None, "", row["class_row_id"])
                or type(frame.get("inputs")) is not dict
                or frame["inputs"].get(_field(row["feature_id"])) != digest(base)
                or _dependency(definition, row["relation"]) != row["dependency_digest"]):
            raise SourceRepairError("Historical association lost its exact row, explicit input or dependency frame.")
        seen.add(row["feature_id"]); relations.add(row["relation"])
    return tuple(deepcopy(rows))


def validate(prior, candidate, service=None):
    rows, old = stored(candidate), stored(prior)
    if any(row not in rows for row in old):
        raise SourceRepairError("Historical associations cannot be removed or replaced by this operation.")
    if not rows:
        return rows
    before = _features(prior)
    for row in rows:
        if before.get(row["feature_id"]) != json.loads(row["prior_feature_json"]):
            raise SourceRepairError("Historical association changed its original row.")
        if service is not None:
            current = _base(candidate, before[row["feature_id"]], service)
            if current != {key: value for key, value in row.items() if key != "dependency_digest"}:
                raise SourceRepairError("Historical association sources or owning feature changed.")
            if _dependency(candidate, row["relation"], service) != row["dependency_digest"]:
                raise SourceRepairError("Historical association choices changed.")
    return rows


def custody(definition, origin, rows):
    return ({CUSTODY: {"campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
        "action_id": origin["action_id"], "digest": digest(list(rows)), "relations": deepcopy(list(rows))}},) if rows else ()


def declared_ids(definition, witnesses=(), *, relation=None):
    """Intent only withholds mechanics; malformed/stale intent never grants them."""
    frame = definition.source.get("native_reconstruction_choices")
    rows = frame.get(FRAME, []) if type(frame) is dict else []
    rows = list(rows) if type(rows) is list else []
    for raw in witnesses:
        try:
            witness = json.loads(raw) if type(raw) is str else raw
            packet = witness.get(CUSTODY) if type(witness) is dict else None
            if (type(packet) is dict and packet.get("campaign_slug") == definition.campaign_slug
                    and packet.get("character_slug") == definition.character_slug and type(packet.get("relations")) is list):
                rows.extend(packet["relations"])
        except (TypeError, ValueError):
            continue
    return frozenset(row["feature_id"] for row in rows
                     if type(row) is dict and type(row.get("feature_id")) is str and row["feature_id"]
                     and (relation is None or row.get("relation") == relation))


def qualified(definition, state, authority, service):
    try:
        from .character_source_authority import numeric_value_digest
        if (authority is None or (authority.original_definition_digest or authority.definition_digest)
                != numeric_value_digest(definition.to_dict()) or authority.state_digest != numeric_value_digest(state)):
            return {}
        rows = validate(definition, definition, service)
        origin = definition.source.get("native_reconstruction")
        if not rows or type(origin) is not dict or origin.get(ORIGIN) != digest(list(rows)):
            return {}
        witnesses = [json.loads(raw) for raw in authority.verified_numeric_actions]
        if custody(definition, origin, rows)[0] not in witnesses:
            return {}
        result = {}
        for row in rows:
            if (row["class_row_id"] not in authority.verified_class_rows
                    or authority.status_for("feature", row["owner_feature_id"]) != "VERIFIED"):
                continue
            if row["relation"] == RECIPES:
                from .character_infusion_recipes import view
                if not view(definition, state, authority, service)["available"]:
                    continue
            else:
                from .character_armor_models import qualified as armor_qualified, MODEL, ARCANE, GAUNTLETS, FIELD
                choices = armor_qualified(definition, service, witnesses)
                if len(choices) != 1 or choices[0]["class_row_id"] != row["class_row_id"]:
                    continue
                owners = [_unique_owner(definition, service, key, row["class_row_id"])
                          for key in (MODEL, ARCANE, GAUNTLETS, FIELD)]
                if any(authority.status_for("feature", owner["id"]) != "VERIFIED" for owner in owners):
                    continue
            result[row["feature_id"]] = row
        return result
    except (ValueError, TypeError, KeyError, AttributeError):
        return {}


def qualify_authority(authority, definition, state, service):
    """Final status-only pass. These rows never enter the grant producer."""
    rows = qualified(definition, state, authority, service)
    statuses = tuple(replace(status, status="VERIFIED", reason="authenticated_history_only")
                     if status.kind == "feature" and status.instance_id in rows else status
                     for status in authority.statuses)
    removed = {("source_needs_repair", f"Feature {identity} needs source repair.") for identity in rows}
    return replace(authority, statuses=statuses, warnings=tuple(w for w in authority.warnings if w not in removed))


def presentation(definition, state, authority, service):
    witnesses = getattr(authority, "verified_numeric_actions", ())
    ids = declared_ids(definition, witnesses)
    if not ids:
        return {}
    rows = qualified(definition, state, authority, service)
    try:
        features = _features(definition)
    except (ValueError, TypeError, KeyError, AttributeError):
        # Ambiguous owners cannot supply citations. Every claimed history ID
        # remains nonoperative, including all rows sharing a duplicate ID.
        features, rows = {}, {}
    result = {}
    for identity in ids:
        row = rows.get(identity)
        owner = features.get(row["owner_feature_id"]) if row else None
        result[identity] = {"historical_only": True, "available": bool(row),
            "systems_ref": deepcopy(owner.get("systems_ref")) if owner else {},
            "description_markdown": (
                "Historical association to " + str(owner.get("name") or "the current owner") + ". Current rules and benefits belong to that owner; this saved row adds no benefit or action."
                if owner else "Historical association unavailable. Current source or ownership needs repair; this saved row supplies no benefit or action.")}
    return result


def validate_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    old, new = stored(prior_record.definition), stored(candidate)
    if old == new:
        return
    from .character_reconstruction_authority import PendingNativeReconstruction
    if type(proof) is not PendingNativeReconstruction or proof.feature_history != new:
        raise SourceRepairError("Historical association changes require the exact reviewed reconstruction.")
    proof.validate_binding(prior_record, candidate, state, actor_id)
