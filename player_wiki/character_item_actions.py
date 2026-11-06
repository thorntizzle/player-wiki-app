"""Closed noncasting item choices on the existing physical-use ledger.

A declaration describes a rule, never current availability. Recording the
choice spends a use; attack modifiers, targets and hit results remain external.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json

from .character_spell_slots import slot_value_digest


OPERATION = "item_attack_d20"
REACTION_OPERATION = "item_triggered_reaction"
OPERATIONS = frozenset({OPERATION, REACTION_OPERATION})
EVENT = "character_item_action_applied"
_SEAL = object()


def normalize_capabilities(value):
    from .character_item_capabilities import _keys, _text
    if (type(value) is not dict or set(value) not in ({"schema_version", "effect_id", "counter", "action"},
                {"schema_version", "effect_id", "counter", "action", "conditional_rules"})
            or type(value["schema_version"]) is not int or value["schema_version"] != 3
            or not _text(value["effect_id"])):
        raise ValueError("Noncasting item capabilities need a complete supported v3 contract.")
    counter = value["counter"]
    if (not _keys(counter, {"maximum", "reset_on", "reset_to", "source_reset"})
            or type(counter["maximum"]) is not int or not 1 <= counter["maximum"] <= 1000
            or counter["reset_on"] not in ("long_rest", "short_rest")
            or counter["reset_to"] != "max"
            or counter["source_reset"] not in ("long_rest", "short_rest", "once_per_day", "at_dawn")
            or (counter["source_reset"] == "short_rest") != (counter["reset_on"] == "short_rest")):
        raise ValueError("Noncasting item uses need an exact fixed source capacity and compatible recovery rule.")
    action = value["action"]
    if type(action) is not dict:
        raise ValueError("Declare one complete noncasting action.")
    if action.get("kind") == "attack_d20_substitution":
        if (not _keys(action, {"kind", "activation", "replacement", "counter_cost", "trigger"})
                or action["activation"] != "equipped" or type(action["replacement"]) is not int or action["replacement"] != 10
                or type(action["counter_cost"]) is not int or action["counter_cost"] != 1
                or action["trigger"] != "before_attack_d20"):
            raise ValueError("This item action supports choosing 10 instead of an attack d20, while equipped, for one use.")
    elif action.get("kind") == "prevent_forced_movement":
        if (not _keys(action, {"kind", "activation", "counter_cost", "timing", "triggers", "targets", "range_feet", "effect", "speed", "until"})
                or action["activation"] != "equipped" or action["timing"] != "reaction"
                or type(action["counter_cost"]) is not int or action["counter_cost"] != 1
                or action["triggers"] != ["pushed", "pulled", "knocked_prone", "fall"]
                or action["targets"] != ["self", "willing_visible_creature"]
                or type(action["range_feet"]) is not int or not 1 <= action["range_feet"] <= 120
                or action["effect"] != "prevent_trigger_only" or type(action["speed"]) is not int or action["speed"] != 0
                or action["until"] != "target_next_turn_start"):
            raise ValueError("This reaction needs exact triggering movement, willing visible target, range and temporary speed rules.")
    else:
        raise ValueError("This noncasting action kind is unsupported.")
    if "conditional_rules" in value:
        rules = value["conditional_rules"]
        if (not _keys(rules, {"activation", "terrain", "movement", "obstacles", "check_advantage"})
                or rules["activation"] != "equipped" or rules["terrain"] != "natural_wetlands"
                or rules["movement"] != "ignore_nonmagical_extra_cost"
                or rules["obstacles"] != ["mud", "reeds", "roots", "shallow_water"]
                or rules["check_advantage"] != {"ability": "wis", "skill": "survival", "purposes": ["navigate", "avoid_getting_lost"]}):
            raise ValueError("Conditional item rules need the complete supported natural-wetlands movement and navigation clauses.")
    return deepcopy(value)


def validate_source(capability, metadata):
    """An equipped-only nonspell rule cannot inherit a contradictory budget."""
    if capability.get("schema_version") != 3:
        return
    from .character_builder_equipment import _metadata_requires_attunement
    if (_metadata_requires_attunement(metadata.get("attunement"))
            or metadata.get("requires_attunement") is True
            or metadata.get("item_use_actions") or metadata.get("spell_support")):
        raise ValueError("Noncasting equipped-only item actions cannot require attunement or share a spell-spending clause.")


def validate_json_dispatch(payload, raw_json):
    """Check original field uniqueness before lossy JSON chooses an operation.

    Preserve legitimate legacy inventory object fields and request-size policy;
    action-specific adapters still impose their own tighter scalar/size bounds.
    """
    if type(payload) is not dict or type(raw_json) is not bytes:
        raise ValueError("Submit one inventory action object.")
    if not raw_json and not payload:
        return  # Retain the ordinary empty-body validation path.
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Submit each inventory action field once.")
            result[key] = value
        return result
    try:
        original = json.loads(raw_json, object_pairs_hook=unique_object)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Submit one unambiguous JSON inventory action.") from exc
    if type(original) is not dict or original != payload:
        raise ValueError("The parsed inventory action differs from its request.")


def validate_request(payload, allowed, *, html=False, raw_json=None):
    """Bound exact request fields before interpreting any action-specific inputs."""
    allowed = set(allowed)
    if html:
        from .csrf import CSRF_FIELD_NAME
        allowed |= {CSRF_FIELD_NAME, "mode", "page", "return_view"}
        if not callable(getattr(payload, "getlist", None)) or any(len(payload.getlist(key)) != 1 for key in payload):
            raise ValueError("Submit one unambiguous item action.")
    elif type(payload) is not dict:
        raise ValueError("Submit one item action object.")
    else:
        if type(raw_json) is not bytes or not 1 <= len(raw_json) <= 8192:
            raise ValueError("Submit one bounded JSON item action.")
        validate_json_dispatch(payload, raw_json)
    if set(payload) - allowed:
        raise ValueError("The item action contains unsupported inputs.")
    if not html and any(type(value) not in (str, int, bool, type(None)) or isinstance(value, str) and (len(value) > 512 or any(ord(c) < 32 for c in value)) for value in payload.values()):
        raise ValueError("Item action values must be bounded scalars.")
    revision = payload.get("expected_revision")
    if html:
        if (not isinstance(revision, str) or not revision.isascii() or not revision.isdecimal()
                or not 1 <= len(revision) <= 18):
            raise ValueError("An exact current state revision is required.")
        revision = int(revision)
        if any(type(value) is not str or len(value) > 512 or any(ord(char) < 32 for char in value)
               for value in payload.values()):
            raise ValueError("Item action form values must be bounded text.")
    if type(revision) is not int or not 1 <= revision < 10 ** 18:
        raise ValueError("An exact current state revision is required.")


def request_confirmation(payload, *, html=False, raw_json=None):
    validate_request(payload, {"operation", "expected_revision", "confirm_attack"}, html=html, raw_json=raw_json)
    if payload.get("operation") != OPERATION:
        raise ValueError("Choose the attack-d20 operation explicitly.")
    confirmed = payload.get("confirm_attack") == "yes" if html else payload.get("confirm_attack") is True
    if not confirmed:
        raise ValueError("Confirm choosing 10 instead of rolling this attack's d20.")
    return True


def reaction_values(payload, *, html=False, raw_json=None):
    validate_request(payload, {"operation", "expected_revision", "confirm_reaction", "trigger", "target_kind"}, html=html, raw_json=raw_json)
    confirmed = payload.get("confirm_reaction") == "yes" if html else payload.get("confirm_reaction") is True
    if payload.get("operation") != REACTION_OPERATION or not confirmed:
        raise ValueError("Explicitly confirm this eligible reaction, separately from an attack-d20 choice.")
    return {"confirm_reaction": True, "trigger": payload.get("trigger"), "target_kind": payload.get("target_kind")}


def conditional_notes(entry):
    if entry is None or entry["capability"].get("schema_version") != 3 or not entry["capability"].get("conditional_rules"):
        return []
    return ["While worn in natural marshes, swamps or wetlands, ignore extra movement from nonmagical mud, reeds, roots and shallow water; gain advantage on Wisdom (Survival) checks to navigate or avoid getting lost there. These rules do not spend an item use."]


def item_entry(authority, definition, physical_id):
    from .character_item_capabilities import _text
    if not _text(physical_id):
        raise ValueError("Choose one exact physical item.")
    matches = [entry for entry in authority.item_capability_entries(definition)
               if entry["physical_id"] == physical_id and entry["capability"].get("schema_version") == 3] if authority is not None else []
    if len(matches) != 1:
        raise ValueError("The exact current physical item and noncasting source rule need repair.")
    return matches[0]


def presentation(authority, definition, entry):
    if entry is None or entry["capability"].get("schema_version") != 3:
        return None
    from .character_item_capabilities import active_clause, known_counter
    capability = normalize_capabilities(entry["capability"])
    counter, action, physical = capability["counter"], capability["action"], entry["physical"]
    status = authority.resource_status("item_charge", entry["physical_id"])
    known = (known_counter(physical, counter["maximum"]) and status.is_effective
             and type(status.effective) is dict
             and status.effective.get("current") == physical["charges_current"]
             and status.effective.get("max") == counter["maximum"]
             and status.effective.get("source_basis_digest") == entry["source_basis_digest"])
    reasons = []
    if not active_clause(entry, action["activation"]):
        reasons.append("Wear or equip this item before using it.")
    if not known:
        reasons.append("Current uses are unrecorded or incompatible with the current source.")
    elif physical["charges_current"] < action["counter_cost"]:
        reasons.append("No item uses remain.")
    source_recovery = {"at_dawn": "At dawn", "once_per_day": "Once per day",
                       "long_rest": "Long rest", "short_rest": "Short rest"}[counter["source_reset"]]
    result = {"operation": OPERATION, "effect_id": capability["effect_id"], "kind": action["kind"],
        "physical_id": entry["physical_id"], "replacement": action.get("replacement"),
        "counter_cost": action["counter_cost"], "activation": action["activation"],
        "trigger": action.get("trigger"), "source_reset": counter["source_reset"],
        "reset_on": counter["reset_on"], "source_recovery_label": source_recovery,
        "campaign_recovery_label": "Long rest" if counter["reset_on"] == "long_rest" else "Short rest",
        "enabled": not reasons, "disabled_reason": " ".join(reasons), "table_managed": True,
        "rule": "While worn or equipped, choose 10 instead of rolling an attack's d20. Add the applicable attack modifiers and resolve the target at the table; this does not guarantee a hit."}

    if action["kind"] == "prevent_forced_movement":
        result.update(operation=REACTION_OPERATION, title="Prevent triggering movement", confirmation_name="confirm_reaction",
            confirmation="I use my available reaction for this eligible trigger and target, within the stated range.",
            button="Record reaction and spend one use", triggers=action["triggers"], targets=action["targets"],
            rule=f"Reaction while worn: when you or a willing creature you can see within {action['range_feet']} feet is pushed, pulled, knocked prone or falls, prevent only that triggering effect. The target's speed becomes 0 until the start of its next turn. Check eligibility, reaction availability and turn effects at the table.")
    else:
        result.update(title="Choose 10 instead of an attack d20", confirmation_name="confirm_attack",
            confirmation="I choose 10 instead of rolling this attack's d20, before rolling it.",
            button="Record d20 choice of 10 and spend one use")
    return result


def apply_operation(state, definition, authority, params):
    if type(params) is not dict:
        raise ValueError("Choose one exact physical item action.")
    if authority is None or authority.state_digest != slot_value_digest(state):
        raise ValueError("The item action's Character or state changed. Refresh before acting.")
    definition_digest = slot_value_digest(definition.to_dict())
    if authority.definition_digest != definition_digest:
        from .character_equipment_activation import effective_definition
        if authority.original_definition_digest != definition_digest:
            raise ValueError("The item action's exact Character owner changed.")
        reconciled, _warnings = effective_definition(definition, state)
        if authority.definition_digest != slot_value_digest(reconciled.to_dict()):
            raise ValueError("The current equipment activation no longer matches the item authority.")
    entry = item_entry(authority, definition, params["item_id"])
    action = entry["capability"]["action"]
    if action["kind"] == "attack_d20_substitution":
        if set(params) != {"item_id", "confirm_attack"} or params["confirm_attack"] is not True:
            raise ValueError("Confirm only the exact physical item's attack-d20 choice.")
    elif (set(params) != {"item_id", "confirm_reaction", "trigger", "target_kind"}
            or params["confirm_reaction"] is not True or params["trigger"] not in action["triggers"]
            or params["target_kind"] not in action["targets"]):
        raise ValueError("Confirm the reaction's actual eligible trigger and target kind.")
    offered = presentation(authority, definition, entry)
    if offered is None or not offered["enabled"]:
        raise ValueError(offered["disabled_reason"] if offered else "The current item action is unavailable.")
    result = deepcopy(state)
    rows = [row for row in result.get("inventory", []) if type(row) is dict and row.get("id") == entry["physical_id"]]
    if len(rows) != 1 or (rows[0].get("catalog_ref") or rows[0].get("id")) != entry["catalog_id"]:
        raise ValueError("The exact physical item changed before its use.")
    from .character_item_capabilities import known_counter
    if (not known_counter(rows[0], entry["capability"]["counter"]["maximum"])
            or (rows[0]["charges_current"], rows[0]["charges_max"]) != (
                entry["physical"].get("charges_current"), entry["physical"].get("charges_max"))):
        raise ValueError("The raw item-use observations disagree with their qualified physical owner.")
    rows[0]["charges_current"] -= offered["counter_cost"]
    return result


@dataclass(frozen=True, slots=True)
class ItemActionIntent:
    before_digest: str
    after_digest: str
    definition_digest: str
    source_basis_digest: str
    params_json: str
    seal: object = field(repr=False, compare=False)


def prepare_operation(state, definition, authority, params):
    result = apply_operation(state, definition, authority, params)
    entry = item_entry(authority, definition, params["item_id"])
    return result, ItemActionIntent(slot_value_digest(state), slot_value_digest(result),
        slot_value_digest(definition.to_dict()), entry["source_basis_digest"],
        json.dumps(params, sort_keys=True, separators=(",", ":")), _SEAL)


def validate_transition(prior, result, definition, authority, intent):
    if intent is None:
        return
    if (type(intent) is not ItemActionIntent or intent.seal is not _SEAL
            or intent.before_digest != slot_value_digest(prior) or intent.after_digest != slot_value_digest(result)
            or intent.definition_digest != slot_value_digest(definition.to_dict())):
        raise ValueError("The noncasting item action must preserve its exact current Character and state transition.")
    params = json.loads(intent.params_json)
    entry = item_entry(authority, definition, params.get("item_id"))
    if (intent.source_basis_digest != entry["source_basis_digest"]
            or apply_operation(prior, definition, authority, params) != result):
        raise ValueError("The item rule changed or the action altered unrelated state.")


def audit_metadata(prior, result, definition, authority, intent, prior_revision, revision):
    validate_transition(prior, result, definition, authority, intent)
    if type(prior_revision) is not int or type(revision) is not int or revision != prior_revision + 1:
        raise ValueError("The persisted item action has an unexpected state revision.")
    params = json.loads(intent.params_json)
    entry = item_entry(authority, definition, params["item_id"])
    metadata = {"source": "noncasting_item_action_v1", "kind": entry["capability"]["action"]["kind"],
        "item_id": entry["physical_id"], "catalog_id": entry["catalog_id"], "source_ref": deepcopy(entry["source_ref"]),
        "effect_id": entry["capability"]["effect_id"], "source_basis_digest": intent.source_basis_digest,
        "prior_state_revision": prior_revision, "state_revision": revision,
        "prior_state_digest": intent.before_digest, "state_digest": intent.after_digest,
        "definition_digest": intent.definition_digest, "confirm_attack": True,
        "result": {"choice": entry["capability"]["action"]["kind"],
                   "replacement": entry["capability"]["action"].get("replacement"),
                   "uses_spent": entry["capability"]["action"]["counter_cost"],
                   "table_managed": True, "attack_resolved": False}}

    if entry["capability"]["action"]["kind"] == "prevent_forced_movement":
        metadata.pop("confirm_attack")
        metadata.update(confirm_reaction=True, trigger=params["trigger"], target_kind=params["target_kind"])
        metadata["result"] = {"choice": "prevent_forced_movement", "uses_spent": 1,
            "table_managed": True, "effects_resolved": False, "reaction_economy_tracked": False}
    return metadata
