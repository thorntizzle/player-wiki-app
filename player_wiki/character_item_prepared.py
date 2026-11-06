"""Source-owned prepared ammunition; absence is an unknown observation.

Loading owns one atomic slot/ledger transition. Discharge records use of the
load, not a hit or resolved target effect. Current bearer metrics are not stored.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field, replace
import json
import re

from .character_spell_slots import slot_value_digest

KEY = "item_prepared_ammunition"
EVENT = "character_prepared_item_action_applied"
OPERATIONS = frozenset({"prepared_observe", "prepared_load", "prepared_discharge"})
_SEAL = object()
_DAMAGE = {"acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic", "radiant", "slashing", "thunder"}


def normalize_capabilities(value):
    from .character_item_capabilities import _keys, _text
    if (not _keys(value, {"schema_version", "effect_id", "prepared_ammunition"})
            or type(value["schema_version"]) is not int or value["schema_version"] != 4 or not _text(value["effect_id"])):
        raise ValueError("Prepared ammunition needs a complete supported v4 source contract.")
    rule = value["prepared_ammunition"]
    if (not _keys(rule, {"capacity", "required_class_key", "load_activation", "discharge_activation", "slot_cost", "choices"})
            or type(rule["capacity"]) is not int or rule["capacity"] != 1
            or type(rule["slot_cost"]) is not int or rule["slot_cost"] != 1
            or not _text(rule["required_class_key"])
            or re.fullmatch(r"dnd-5e\|class\|[^|]+\|[^|]+", rule["required_class_key"]) is None
            or rule["load_activation"] not in ("attuned", "equipped_attuned")
            or rule["discharge_activation"] != "equipped_attuned"
            or type(rule["choices"]) is not list or not 1 <= len(rule["choices"]) <= 16):
        raise ValueError("Prepared ammunition needs exact class, activation, single-load and slot-cost ownership.")
    seen = set()
    for choice in rule["choices"]:
        if (not _keys(choice, {"id", "title", "damage", "save", "attack_advantage", "hit_rider"})
                or not _text(choice["id"]) or choice["id"] in seen or not _text(choice["title"])):
            raise ValueError("Developed ammunition choices need distinct stable source identities.")
        seen.add(choice["id"])
        damage = choice["damage"]
        if (not _keys(damage, {"dice_per_slot", "die_faces", "type"})
                or type(damage["dice_per_slot"]) is not int or not 1 <= damage["dice_per_slot"] <= 20
                or type(damage["die_faces"]) is not int or damage["die_faces"] not in {4, 6, 8, 10, 12}
                or damage["type"] not in tuple(_DAMAGE)):
            raise ValueError("Prepared damage needs supported source dice per paid slot level.")
        save = choice["save"]
        if save is not None and (not _keys(save, {"ability", "target", "radius_feet", "on_failure"})
                or save["ability"] not in ("str", "dex", "con", "int", "wis", "cha")
                or save["target"] not in ("target", "nearby_creatures")
                or type(save["radius_feet"]) is not int or not 0 <= save["radius_feet"] <= 60
                or (save["target"] == "target") != (save["radius_feet"] == 0)
                or type(save["on_failure"]) is not list or not 1 <= len(save["on_failure"]) <= 3
                or any(not _keys(x, {"effect", "duration_seconds"})
                    or x["effect"] not in ("listed_damage", "deafened", "prone", "blinded")
                    or type(x["duration_seconds"]) is not int or not 0 <= x["duration_seconds"] <= 600
                    or x["effect"] in ("listed_damage", "prone") and x["duration_seconds"] != 0 for x in save["on_failure"])
                or len({x["effect"] for x in save["on_failure"]}) != len(save["on_failure"])):
            raise ValueError("Prepared saves need exact bearer-save, affected creatures and failure clauses.")
        if choice["attack_advantage"] not in ("", "metal_armor"):
            raise ValueError("This ammunition advantage condition is unsupported.")
        rider = choice["hit_rider"]
        if rider is not None and (not _keys(rider, {"target", "range_feet", "damage_type", "ability_modifier"})
                or rider["target"] != "second_enemy" or type(rider["range_feet"]) is not int
                or not 1 <= rider["range_feet"] <= 60 or rider["damage_type"] not in tuple(_DAMAGE)
                or rider["ability_modifier"] not in ("str", "dex", "con", "int", "wis", "cha")):
            raise ValueError("Prepared on-hit riders need exact current-bearer ability and target clauses.")
    return deepcopy(value)


def validate_source(capability, metadata):
    if capability.get("schema_version") != 4:
        return
    from .character_builder_equipment import _metadata_requires_attunement
    if (not (_metadata_requires_attunement(metadata.get("attunement")) or metadata.get("requires_attunement") is True)
            or metadata.get("item_use_actions") or metadata.get("spell_support") or metadata.get("item_uses")):
        raise ValueError("Prepared ammunition requires its attunement rule and cannot share a legacy slot action, spell grant or use budget.")


def context(authority):
    try:
        return json.loads(authority.item_prepared_context_json) if authority is not None else {}
    except (AttributeError, TypeError, ValueError):
        return {}


def load_checkpoints(definition):
    from .db import get_db
    try:
        rows = get_db().execute("SELECT id,actor_user_id,metadata_json FROM auth_audit_log WHERE campaign_slug=? AND character_slug=? AND event_type=? ORDER BY id DESC",
            (definition.campaign_slug, definition.character_slug, EVENT)).fetchall()
    except RuntimeError:
        return {}
    found = {}
    for row in rows:
        try:
            data = json.loads(row["metadata_json"])
            from .character_item_capabilities import _text
            if type(data) is not dict or data.get("source") != "prepared_item_action_v1" or not _text(data.get("item_id")):
                return {}
            identity = data["item_id"]
            if identity in found:
                continue
            found[identity] = None
            if (type(row["actor_user_id"]) is not int or row["actor_user_id"] < 1
                    or type(data.get("state_revision")) is not int or data["state_revision"] < 1
                    or data.get("prior_state_revision") != data["state_revision"] - 1
                    or data.get("ledger_digest") != slot_value_digest(data.get("ledger"))):
                continue
            found[identity] = {"audit_id": row["id"], "state_revision": data["state_revision"],
                "basis": data.get("source_basis_digest"), "ledger_digest": data["ledger_digest"]}
        except (TypeError, ValueError, AttributeError):
            return {}
    return found


def _bearer_save_dc(authority, projected, definition):
    """A generic bearer DC needs one current owner, not one surviving number."""
    from .character_spell_metrics import _metric
    candidates = []
    for family, id_key in (("class", "class_row_id"), ("source", "source_row_id")):
        rows = projected.spellcasting.get(family + "_rows", [])
        if rows is None:
            rows = []
        if type(rows) is not list:
            return None
        seen = set()
        for row in rows:
            if type(row) is not dict:
                return None
            owner = row.get(id_key)
            from .character_item_capabilities import _text
            if not _text(owner) or owner in seen:
                return None
            seen.add(owner)
            if family == "source":
                if owner in authority.disputed_source_rows:
                    return None
                if (owner not in authority.verified_source_rows
                        and not authority._manual_row_authorized(row, definition)):
                    continue  # An unowned historical row is not a current caster.
            # Keep an owned row even if its numeric proof is unavailable. A
            # missing number must not select another owner's DC by elimination.
            candidates.append(_metric(authority, definition, row, family, owner, "spell_save_dc"))
    return candidates[0] if len(candidates) == 1 else None


def bind_context(authority, projected, definition, state):
    if definition is None or state is None or not any(e["capability"].get("schema_version") == 4 for e in authority.item_capability_entries(definition)):
        return authority
    dc = _bearer_save_dc(authority, projected, definition)
    modifiers = {}
    for ability in ("str", "dex", "con", "int", "wis", "cha"):
        status = authority.field_status(f"stats.ability_scores.{ability}.score")
        if status.is_effective and type(status.effective) is int:
            modifiers[ability] = (status.effective - 10) // 2
    facts = {"checkpoints": load_checkpoints(definition), "save_dc": dc, "ability_modifiers": modifiers}
    return replace(authority, item_prepared_context_json=json.dumps(facts, sort_keys=True, separators=(",", ":")))


def item_entry(authority, definition, identity):
    entries = [e for e in authority.item_capability_entries(definition) if e["physical_id"] == identity and e["capability"].get("schema_version") == 4] if authority is not None else []
    if len(entries) != 1:
        raise ValueError("The exact physical item and current prepared-ammunition source need repair.")
    return entries[0]


def _valid_payload(payload, rule):
    if payload is None:
        return True
    if type(payload) is not dict:
        return False
    if payload == {"kind": "mundane"}:
        return True
    return (set(payload) == {"kind", "choice_id", "slot_level"} and payload["kind"] == "enchanted"
        and type(payload["slot_level"]) is int and 1 <= payload["slot_level"] <= 9
        and any(row["id"] == payload["choice_id"] for row in rule["choices"]))


def qualified_ledger(state, authority, entry):
    raw = state.get(KEY)
    if KEY not in state or type(raw) is dict and entry["physical_id"] not in raw:
        return None, "The current load is not recorded."
    ledger = raw.get(entry["physical_id"]) if type(raw) is dict and len(raw) <= 100 else None
    checkpoint = context(authority).get("checkpoints", {}).get(entry["physical_id"])
    if (type(ledger) is not dict or set(ledger) != {"schema_version", "catalog_id", "source_basis_digest", "payload", "provenance"}
            or type(ledger.get("schema_version")) is not int or ledger["schema_version"] != 1
            or ledger.get("catalog_id") != entry["catalog_id"] or ledger.get("source_basis_digest") != entry["source_basis_digest"]
            or ledger.get("provenance") not in ("manager_observed", "qualified_slot_load", "discharged")
            or ledger.get("provenance") == "discharged" and ledger.get("payload") is not None
            or ledger.get("provenance") == "qualified_slot_load" and (type(ledger.get("payload")) is not dict or ledger["payload"].get("kind") != "enchanted")
            or not _valid_payload(ledger.get("payload"), entry["capability"]["prepared_ammunition"])
            or type(checkpoint) is not dict or type(authority.state_revision) is not int
            or checkpoint["state_revision"] > authority.state_revision or checkpoint["basis"] != entry["source_basis_digest"]
            or checkpoint["ledger_digest"] != slot_value_digest(ledger)):
        return None, "The recorded load or its current source needs repair; the observation is preserved."
    return ledger, ""


def owner_available(authority, definition, entry):
    from .character_profile import profile_class_rows
    rows = [r for r in profile_class_rows(definition.profile)
            if (r.get("systems_ref") or {}).get("entry_key") == entry["capability"]["prepared_ammunition"]["required_class_key"]
            and r.get("row_id") in authority.verified_class_rows and type(r.get("level")) is int and r["level"] >= 1]
    return len(rows) == 1


def presentation(state, definition, authority, entry, physical_id):
    if entry is None or entry["capability"].get("schema_version") != 4:
        if type(state.get(KEY)) is dict and physical_id in state[KEY]:
            return {"known": False, "reason": "Recorded ammunition is preserved; current source or physical ownership needs repair.", "can_observe": False}
        return None
    from .character_item_capabilities import active_clause
    from .character_item_casting import slot_options
    ledger, reason = qualified_ledger(state, authority, entry)
    rule = entry["capability"]["prepared_ammunition"]
    owner = owner_available(authority, definition, entry)
    options = slot_options(authority, definition, state)
    choices = deepcopy(rule["choices"])
    facts = context(authority)
    for choice in choices:
        choice["save_dc"] = facts.get("save_dc") if choice["save"] else None
        rider = choice["hit_rider"]
        choice["rider_modifier"] = facts.get("ability_modifiers", {}).get(rider["ability_modifier"]) if rider else None
    payload = deepcopy(ledger["payload"]) if ledger else None
    loaded = next((c for c in choices if payload and c["id"] == payload.get("choice_id")), None)
    raw = state.get(KEY)
    return {"known": ledger is not None, "reason": reason, "payload": payload, "loaded_choice": loaded,
        "can_observe": KEY not in state or type(raw) is dict and physical_id not in raw and len(raw) < 100,
        "choices": choices, "slot_options": options,
        "can_load": ledger is not None and payload is None and owner and active_clause(entry, rule["load_activation"]) and bool(options),
        "can_discharge": ledger is not None and payload is not None and owner and active_clause(entry, rule["discharge_activation"]),
        "activation_note": "Loading requires the qualified source class and attunement; discharging also requires the item equipped. Current bearer DC may be unavailable or ambiguous.",
        "table_managed": True}


def apply_operation(state, definition, authority, params):
    if type(params) is not dict or type(params.get("operation")) is not str or params.get("operation") not in OPERATIONS:
        raise ValueError("Choose one supported prepared-ammunition operation.")
    op = params["operation"]
    specific = {"prepared_observe": {"manager_confirmed", "load_kind", "choice_id", "slot_level"},
        "prepared_load": {"confirm_reload", "choice_id", "slot_level", "slot_lane_id"},
        "prepared_discharge": {"confirm_discharge"}}[op]
    if set(params) != {"item_id", "operation"} | specific:
        raise ValueError("The prepared-ammunition action contains unrelated inputs.")
    if authority is None or authority.state_digest != slot_value_digest(state):
        raise ValueError("The prepared-ammunition state changed. Refresh before acting.")
    raw_digest = slot_value_digest(definition.to_dict())
    if authority.definition_digest != raw_digest:
        from .character_equipment_activation import effective_definition
        reconciled, _ = effective_definition(definition, state)
        if authority.original_definition_digest != raw_digest or authority.definition_digest != slot_value_digest(reconciled.to_dict()):
            raise ValueError("The prepared-ammunition Character or equipment owner changed.")
    entry = item_entry(authority, definition, params["item_id"])
    rule = entry["capability"]["prepared_ammunition"]
    result = deepcopy(state)
    if op == "prepared_observe":
        raw = result.get(KEY)
        if (params["manager_confirmed"] is not True or params["load_kind"] not in ("empty", "mundane", "enchanted")
                or KEY in result and type(raw) is not dict or type(raw) is dict and (entry["physical_id"] in raw or len(raw) >= 100)):
            raise ValueError("A manager may record an explicitly confirmed first load observation, never overwrite an existing one.")
        payload = None if params["load_kind"] == "empty" else {"kind": params["load_kind"]}
        if params["load_kind"] == "enchanted":
            payload.update(choice_id=params["choice_id"], slot_level=params["slot_level"])
        elif params["choice_id"] != "" or params["slot_level"] is not None:
            raise ValueError("Only an observed enchanted load has a developed choice and paid level.")
        if not _valid_payload(payload, rule):
            raise ValueError("Record the actual source-supported load and paid slot level.")
        result.setdefault(KEY, {})[entry["physical_id"]] = {"schema_version": 1, "catalog_id": entry["catalog_id"],
            "source_basis_digest": entry["source_basis_digest"], "payload": payload, "provenance": "manager_observed"}
        return result
    ledger, reason = qualified_ledger(state, authority, entry)
    if ledger is None:
        raise ValueError(reason)
    from .character_item_capabilities import active_clause
    activation = rule["load_activation"] if op == "prepared_load" else rule["discharge_activation"]
    if not owner_available(authority, definition, entry) or not active_clause(entry, activation):
        raise ValueError("The current class, attunement or equipment requirement is not satisfied.")
    if op == "prepared_load":
        if ledger["payload"] is not None or params["confirm_reload"] is not True:
            raise ValueError("Confirm reloading a known empty item; an existing load cannot be overwritten.")
        payload = {"kind": "enchanted", "choice_id": params["choice_id"], "slot_level": params["slot_level"]}
        if not _valid_payload(payload, rule):
            raise ValueError("Choose a currently developed ammunition option and qualified paid slot level.")
        from .character_item_casting import slot_options
        if not any(r["slot_lane_id"] == params["slot_lane_id"] and r["level"] == params["slot_level"] for r in slot_options(authority, definition, state)):
            raise ValueError("Choose one currently qualified available slot.")
        from .character_spell_slots import spend_slot_contribution
        result = spend_slot_contribution(result, definition.spellcasting, authority, params["slot_lane_id"], params["slot_level"])
        result[KEY][entry["physical_id"]].update(payload=payload, provenance="qualified_slot_load")
    else:
        if ledger["payload"] is None or params["confirm_discharge"] is not True:
            raise ValueError("Confirm firing the actual recorded load; an empty item cannot be discharged again.")
        result[KEY][entry["physical_id"]].update(payload=None, provenance="discharged")
    return result


@dataclass(frozen=True, slots=True)
class PreparedItemIntent:
    before_digest: str
    after_digest: str
    definition_digest: str
    source_basis_digest: str
    params_json: str
    seal: object = field(repr=False, compare=False)


def prepare_operation(state, definition, authority, params):
    result = apply_operation(state, definition, authority, params)
    entry = item_entry(authority, definition, params["item_id"])
    return result, PreparedItemIntent(slot_value_digest(state), slot_value_digest(result), slot_value_digest(definition.to_dict()),
        entry["source_basis_digest"], json.dumps(params, sort_keys=True, separators=(",", ":")), _SEAL)


def require_preserved(prior, result):
    if (KEY in (prior or {})) != (KEY in result) or (prior or {}).get(KEY) != result.get(KEY):
        raise ValueError("Prepared ammunition must be preserved outside its exact guarded item operation.")


def validate_transition(prior, result, definition, authority, intent):
    if intent is None:
        require_preserved(prior, result)
        return
    if (type(intent) is not PreparedItemIntent or intent.seal is not _SEAL
            or intent.before_digest != slot_value_digest(prior) or intent.after_digest != slot_value_digest(result)
            or intent.definition_digest != slot_value_digest(definition.to_dict())):
        raise ValueError("Prepared ammunition needs its exact sealed Character/state transition.")
    params = json.loads(intent.params_json)
    entry = item_entry(authority, definition, params["item_id"])
    if entry["source_basis_digest"] != intent.source_basis_digest or apply_operation(prior, definition, authority, params) != result:
        raise ValueError("The prepared-ammunition source changed or unrelated state was altered.")


def audit_metadata(prior, result, definition, authority, intent, prior_revision, revision):
    validate_transition(prior, result, definition, authority, intent)
    if type(prior_revision) is not int or type(revision) is not int or revision != prior_revision + 1:
        raise ValueError("The prepared-ammunition state revision is unexpected.")
    params = json.loads(intent.params_json); entry = item_entry(authority, definition, params["item_id"])
    ledger = result[KEY][entry["physical_id"]]
    return {"source": "prepared_item_action_v1", "operation": params["operation"], "item_id": entry["physical_id"],
        "catalog_id": entry["catalog_id"], "source_basis_digest": intent.source_basis_digest,
        "prior_state_revision": prior_revision, "state_revision": revision, "prior_state_digest": intent.before_digest,
        "state_digest": intent.after_digest, "definition_digest": intent.definition_digest,
        "ledger": deepcopy(ledger), "ledger_digest": slot_value_digest(ledger), "action": params,
        "effects_resolved": False, "table_managed": True}


def request_values(payload, *, html=False, raw_json=None):
    from .character_item_actions import validate_request
    op = payload.get("operation")
    if type(op) is not str or op not in OPERATIONS:
        raise ValueError("Choose one supported prepared-ammunition operation.")
    fields = {"prepared_observe": {"confirm_observation", "load_kind", "choice_id", "slot_level"},
        "prepared_load": {"confirm_reload", "choice_id", "slot_selection", "slot_lane_id", "slot_level"},
        "prepared_discharge": {"confirm_discharge"}}[op]
    validate_request(payload, {"operation", "expected_revision"} | fields, html=html, raw_json=raw_json)
    values = {k: payload[k] for k in fields if k in payload}
    for name in ("confirm_observation", "confirm_reload", "confirm_discharge"):
        if name in fields:
            values[name] = values.get(name) == "yes" if html else values.get(name) is True
            if not values[name]:
                raise ValueError("Explicitly confirm the actual current observation, reload or discharge.")
    if "slot_selection" in values:
        if "slot_lane_id" in values or "slot_level" in values:
            raise ValueError("Choose one unambiguous slot selection.")
        from .character_spell_slots import parse_spell_slot_selection
        values["slot_lane_id"], values["slot_level"] = parse_spell_slot_selection(values.pop("slot_selection"))
    return values
