"""Source-owned spell storage, with latest actor-bound audit custody.

Absence is unknown. An empty ledger is an explicit observation, never a read
default. Spell snapshots retain original caster values after later changes.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from .character_item_casting import STORAGE_KEY, context, integer, text
from .character_spell_slots import slot_value_digest

EVENT = "character_item_spell_action_applied"


def load_checkpoints(definition):
    from .db import get_db
    rows = get_db().execute("""SELECT id,actor_user_id,metadata_json FROM auth_audit_log
        WHERE campaign_slug=? AND character_slug=? AND event_type=? ORDER BY id DESC""",
        (definition.campaign_slug, definition.character_slug, EVENT)).fetchall()
    found = {}
    for row in rows:
        try:
            data = json.loads(row["metadata_json"])
            if data.get("source") != "item_spell_action_v1":
                return {}
            item_id = data.get("item_id")
            if not text(item_id):
                return {}
            if item_id in found:
                continue
            # Select the latest event for the physical ID first, across bases.
            # A malformed latest checkpoint must never reveal an older one.
            found[item_id] = None
            if (type(row["actor_user_id"]) is not int or row["actor_user_id"] < 1
                    or type(data.get("state_revision")) is not int or data["state_revision"] < 1
                    or data.get("prior_state_revision") != data["state_revision"] - 1
                    or data.get("ledger_digest") != slot_value_digest(data.get("ledger"))):
                continue
            found[item_id] = {"audit_id": row["id"], "actor_user_id": row["actor_user_id"],
                "state_revision": data["state_revision"], "basis": data.get("source_basis_digest"),
                "ledger_digest": data["ledger_digest"]}
        except (TypeError, ValueError, AttributeError):
            return {}
    return found


def _valid_metrics(metrics):
    return (type(metrics) is dict and set(metrics) == {"ability", "ability_modifier", "save_dc", "attack_bonus"}
            and metrics["ability"] in {"str", "dex", "con", "int", "wis", "cha"}
            and type(metrics["ability_modifier"]) is int and -10 <= metrics["ability_modifier"] <= 30
            and type(metrics["save_dc"]) is int and 0 <= metrics["save_dc"] <= 99
            and type(metrics["attack_bonus"]) is int and -30 <= metrics["attack_bonus"] <= 99)


def _valid_ledger(ledger, entry, facts):
    rule = entry["capability"]["storage"]
    if (type(ledger) is not dict or set(ledger) != {"schema_version", "catalog_id", "source_basis_digest", "spells"}
            or type(ledger.get("schema_version")) is not int or ledger["schema_version"] != 1
            or ledger.get("catalog_id") != entry["catalog_id"]
            or ledger.get("source_basis_digest") != entry["source_basis_digest"]
            or type(ledger.get("spells")) is not list or len(ledger["spells"]) > rule["capacity"]):
        return False
    ids, total = set(), 0
    for spell in ledger["spells"]:
        if (type(spell) is not dict or set(spell) != {"id", "spell_ref", "slot_level", "caster", "metrics", "provenance"}
                or not text(spell.get("id")) or spell["id"] in ids or type(spell.get("slot_level")) is not int
                or not rule["minimum_level"] <= spell["slot_level"] <= rule["maximum_level"]
                or not _valid_metrics(spell.get("metrics")) or not text(spell.get("caster"), 120)
                or type(spell.get("provenance")) is not dict
                or spell["provenance"].get("kind") not in {"qualified_character_cast", "manager_observed_external_cast"}):
            return False
        ref = spell.get("spell_ref")
        current = facts.get("spells", {}).get(ref.get("entry_key")) if type(ref) is dict else None
        if current is None or current != ref or not 1 <= ref["level"] <= spell["slot_level"]:
            return False
        total += spell["slot_level"]
        ids.add(spell["id"])
    return total <= rule["capacity"]


def qualified_ledger(state, definition, authority, entry):
    facts = context(authority)
    storage = state.get(STORAGE_KEY)
    if storage is None and STORAGE_KEY not in state:
        return None, "Stored spells are not recorded."
    if type(storage) is not dict or len(storage) > 100:
        return None, "Spell storage needs manager repair."
    ledger = storage.get(entry["physical_id"])
    if entry["physical_id"] not in storage:
        return None, "Stored spells are not recorded."
    checkpoint = facts.get("storage_checkpoints", {}).get(entry["physical_id"])
    if (type(checkpoint) is not dict or type(authority.state_revision) is not int
            or checkpoint["state_revision"] > authority.state_revision
            or checkpoint["basis"] != entry["source_basis_digest"]
            or checkpoint["ledger_digest"] != slot_value_digest(ledger)
            or not _valid_ledger(ledger, entry, facts)):
        return None, "Stored spell custody or current source needs repair; observations are preserved."
    return ledger, ""


def present_storage(state, definition, authority, entry, *, include_external_choices=False):
    from .character_item_capabilities import active_clause
    rule = entry["capability"].get("storage")
    if rule is None:
        return None
    ledger, reason = qualified_ledger(state, definition, authority, entry)
    active = active_clause(entry, rule["activation"])
    facts = context(authority)
    choices = [deepcopy(choice) for choice in facts.get("choices", [])
               if rule["minimum_level"] <= choice["spell_ref"]["level"] <= rule["maximum_level"]]
    from .character_item_casting import slot_options
    options = [row for row in slot_options(authority, definition, state, rule["minimum_level"])
               if row["level"] <= rule["maximum_level"]]
    raw = state.get(STORAGE_KEY)
    can_initialize = (STORAGE_KEY not in state or type(raw) is dict and entry["physical_id"] not in raw)
    return {"known": ledger is not None, "reason": reason, "active": active, "can_initialize": can_initialize,
        "capacity": rule["capacity"], "occupied": sum(s["slot_level"] for s in ledger["spells"]) if ledger is not None else None,
        "spells": deepcopy(ledger["spells"]) if ledger is not None else [], "choices": choices, "slot_options": options,
        "external_spell_options": [deepcopy(ref) for ref in facts.get("spells", {}).values()
            if rule["minimum_level"] <= ref["level"] <= rule["maximum_level"]] if include_external_choices else []}


def apply_storage(state, definition, authority, entry, params):
    from .character_item_capabilities import active_clause
    rule = entry["capability"].get("storage")
    if rule is None:
        raise ValueError("This item has no current spell-storage capability.")
    result = deepcopy(state)
    kind = params.get("kind")
    if kind == "initialize":
        if params.get("manager_confirmed") is not True:
            raise ValueError("A manager must explicitly confirm an empty storage baseline.")
        storage = result.get(STORAGE_KEY)
        if (STORAGE_KEY in result and type(storage) is not dict) or type(storage) is dict and entry["physical_id"] in storage:
            raise ValueError("Existing storage observations need a separate repair; they cannot be reset.")
        if type(storage) is dict and len(storage) >= 100:
            raise ValueError("The item storage observation limit has been reached.")
        result.setdefault(STORAGE_KEY, {})[entry["physical_id"]] = {"schema_version": 1,
            "catalog_id": entry["catalog_id"], "source_basis_digest": entry["source_basis_digest"], "spells": []}
        return result
    ledger, reason = qualified_ledger(state, definition, authority, entry)
    if ledger is None:
        raise ValueError(reason)
    target = result[STORAGE_KEY][entry["physical_id"]]
    if kind == "release":
        if not active_clause(entry, rule["activation"]):
            raise ValueError("Casting from storage requires the qualified worn and attuned item.")
        matches = [spell for spell in target["spells"] if spell["id"] == params.get("stored_id")]
        if len(matches) != 1:
            raise ValueError("Choose one currently stored spell.")
        target["spells"].remove(matches[0])
        return result
    if kind not in {"store", "observe_external"}:
        raise ValueError("Choose a supported item spell operation.")
    facts = context(authority)
    level = integer(params.get("slot_level"), rule["minimum_level"], rule["maximum_level"])
    if sum(spell["slot_level"] for spell in ledger["spells"]) + level > rule["capacity"]:
        raise ValueError("The ring cannot hold that spell; no slot or ledger change was made.")
    identity = params.get("stored_id")
    if not text(identity) or re.fullmatch(r"[0-9a-f]{32}", identity) is None or any(spell["id"] == identity for spell in ledger["spells"]):
        raise ValueError("The new stored spell identity is invalid.")
    if kind == "store":
        choices = [choice for choice in facts.get("choices", []) if choice["id"] == params.get("choice_id")]
        if len(choices) != 1:
            raise ValueError("Choose a currently castable spell with qualified original-caster metrics.")
        choice = choices[0]
        ref = choice["spell_ref"]
        metrics = {k: choice[k] for k in ("ability", "ability_modifier", "save_dc", "attack_bonus")}
        caster = definition.character_slug
        lane = params.get("slot_lane_id", "")
        from .character_item_casting import slot_options
        options = slot_options(authority, definition, state, ref["level"])
        from .character_spell_slots import spell_slot_contributions
        pools = [pool for pool in spell_slot_contributions(
            definition.spellcasting, state, authority) if pool["id"] == lane]
        if (len(pools) != 1 or pools[0]["source_kind"] == "class" and choice["class_row_id"] not in pools[0]["row_ids"]
                or not any(row["slot_lane_id"] == lane and row["level"] == level for row in options)):
            raise ValueError("Choose a compatible qualified available slot for this caster.")
        from .character_spell_slots import spend_slot_contribution
        result = spend_slot_contribution(result, definition.spellcasting, authority, lane, level)
        target = result[STORAGE_KEY][entry["physical_id"]]
        provenance = {"kind": "qualified_character_cast", "class_row_id": choice["class_row_id"],
            "authority": authority.identity, "slot_lane_id": lane}
    else:
        if params.get("manager_confirmed") is not True:
            raise ValueError("An external casting needs explicit manager confirmation of its original facts.")
        ref = facts.get("spells", {}).get(params.get("spell_entry_key"))
        metrics = params.get("metrics")
        caster = params.get("caster")
        if ref is None or not _valid_metrics(metrics) or not text(caster, 120):
            raise ValueError("Record the actual original caster and complete casting metrics; no values are inferred.")
        provenance = {"kind": "manager_observed_external_cast"}
    if not rule["minimum_level"] <= ref["level"] <= level:
        raise ValueError("The stored slot must support the exact spell's current level.")
    target["spells"].append({"id": identity, "spell_ref": deepcopy(ref), "slot_level": level,
        "caster": caster, "metrics": deepcopy(metrics), "provenance": provenance})
    if not _valid_ledger(target, entry, facts):
        raise ValueError("The proposed stored spell ledger needs repair.")
    return result


def audit_metadata(prior, result, definition, authority, params, expected_revision):
    from .character_item_casting import item_entry
    entry = item_entry(authority, definition, params["item_id"])
    ledger = result.get(STORAGE_KEY, {}).get(params["item_id"])
    return {"source": "item_spell_action_v1", "item_id": params["item_id"], "kind": params["kind"],
        "mode_id": params.get("mode_id", ""), "prior_state_revision": expected_revision,
        "action": deepcopy(params),
        "state_revision": expected_revision + 1, "source_basis_digest": entry["source_basis_digest"],
        "prior_state_digest": slot_value_digest(prior), "state_digest": slot_value_digest(result),
        "ledger": deepcopy(ledger), "ledger_digest": slot_value_digest(ledger)}
