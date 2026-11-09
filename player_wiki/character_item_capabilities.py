"""Finite source-owned item uses and casting/rest clauses.

Physical uses remain on inventory; versioned loads have separate custody. Source rules
never supply current availability, create an inventory row or refill it on read.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any

FIELD = "item_capabilities"
_ABILITIES = frozenset({"str", "dex", "con", "int", "wis", "cha"})


def _text(value: Any) -> bool:
    return (type(value) is str and 0 < len(value) <= 512 and value == value.strip()
            and all(ord(char) >= 32 for char in value))


def _keys(value: Any, keys: set[str]) -> bool:
    return type(value) is dict and set(value) == keys


def normalize_item_capabilities(value: Any) -> dict[str, Any]:
    """Accept a complete versioned contract, never partially trust a clause."""
    if value is None or value == {}:
        return {}
    if type(value) is dict and value.get("schema_version") == 2:
        from .character_item_casting import normalize_capabilities
        return normalize_capabilities(value)
    if type(value) is dict and value.get("schema_version") == 4:
        from .character_item_prepared import normalize_capabilities
        return normalize_capabilities(value)
    if type(value) is dict and value.get("schema_version") == 3:
        from .character_item_actions import normalize_capabilities
        return normalize_capabilities(value)
    if (type(value) is not dict or value.get("schema_version") != 1
            or type(value.get("schema_version")) is not int
            or not {"schema_version", "effect_id"} <= set(value)
            or set(value) - {"schema_version", "effect_id", "counter", "casting", "passive", "self_action", "focus"}
            or not _text(value.get("effect_id"))
            or not set(value) & {"counter", "casting", "passive", "self_action", "focus"}):
        raise ValueError("Item capability declarations need a complete supported contract.")
    if any(key in value and type(value[key]) is not dict
           for key in ("counter", "casting", "passive", "self_action")):
        raise ValueError("Present item capability clauses need complete objects.")
    counter = value.get("counter")
    if counter is not None:
        if (not _keys(counter, {"maximum", "reset_on", "reset_to", "source_reset"})
                or type(counter.get("maximum")) is not int or not 1 <= counter["maximum"] <= 1000
                or counter.get("reset_on") not in {"long_rest", "short_rest"}
                or counter.get("reset_to") != "max"
                or counter.get("source_reset") not in {"long_rest", "short_rest", "once_per_day", "at_dawn"}
                or (counter["source_reset"] in {"once_per_day", "at_dawn", "long_rest"}
                    and counter["reset_on"] != "long_rest")
                or counter["source_reset"] == "short_rest" and counter["reset_on"] != "short_rest"):
            raise ValueError("Item uses need a fixed source capacity and supported recovery rule.")
    casting = value.get("casting")
    if casting is not None:
        if (not _keys(casting, {"source_row_id", "spell_entry_key", "ability", "activation", "level",
                               "slot_cost", "counter_cost", "save_ability", "rider"})
                or not _text(casting.get("source_row_id")) or not _text(casting.get("spell_entry_key"))
                or not casting["spell_entry_key"].startswith("dnd-5e|spell|")
                or casting.get("ability") not in _ABILITIES
                or casting.get("activation") not in {"attuned", "equipped_attuned"}
                or casting.get("level") != "highest_owned_slot"
                or type(casting.get("slot_cost")) is not int or casting["slot_cost"] != 0
                or type(casting.get("counter_cost")) is not int or casting["counter_cost"] != 1
                or counter is None or casting.get("save_ability") not in _ABILITIES):
            raise ValueError("Item casting needs one exact source-spell/counter contract.")
        rider = casting.get("rider")
        if (not _keys(rider, {"dice_per_spell_level", "die_faces", "damage_type", "half_on_save", "damage_ends_spell"})
                or type(rider.get("dice_per_spell_level")) is not int or not 1 <= rider["dice_per_spell_level"] <= 20
                or type(rider.get("die_faces")) is not int or rider["die_faces"] not in {4, 6, 8, 10, 12}
                or rider.get("damage_type") not in {"acid", "bludgeoning", "cold", "fire", "force", "lightning",
                    "necrotic", "piercing", "poison", "psychic", "radiant", "slashing", "thunder"}
                or type(rider.get("half_on_save")) is not bool
                or type(rider.get("damage_ends_spell")) is not bool):
            raise ValueError("Item casting damage needs supported typed source clauses.")
    if counter is not None and casting is None:
        raise ValueError("This item-use contract needs its exact spending clause.")
    passive = value.get("passive")
    if passive is not None:
        if (not _keys(passive, {"activation", "magical_sleep_ward", "self_sleep_exception", "hit_die_recovery_bonus"})
                or passive.get("activation") != "attuned"
                or type(passive.get("magical_sleep_ward")) is not bool
                or type(passive.get("self_sleep_exception")) is not bool
                or type(passive.get("hit_die_recovery_bonus")) is not int
                or not 0 <= passive["hit_die_recovery_bonus"] <= 20
                or passive["self_sleep_exception"] and not passive["magical_sleep_ward"]):
            raise ValueError("Item passive clauses need explicit supported activation and effects.")
    action = value.get("self_action")
    if action is not None and (not _keys(action, {"effect", "timing", "distance_feet"})
            or action.get("effect") != "self_sleep" or action.get("timing") != "action"
            or type(action.get("distance_feet")) is not int or not 0 < action["distance_feet"] <= 60):
        raise ValueError("Item self-action needs its source timing and distance.")
    if passive is not None and passive["self_sleep_exception"] and action is None:
        raise ValueError("The sleep-ward exception needs its actual self-sleep clause.")
    if "focus" in value and type(value["focus"]) is not bool:
        raise ValueError("Item focus support must be explicit.")
    return deepcopy(value)


def validate_capability_source(capability, metadata):
    if capability.get("schema_version") == 3:
        from .character_item_actions import validate_source
        validate_source(capability, metadata)
    elif capability.get("schema_version") == 4:
        from .character_item_prepared import validate_source
        validate_source(capability, metadata)


def validate_capability_spell_support(capability: Any, blocks: Any) -> None:
    """A v1 counter has one spending spell; independent budgets cannot merge."""
    cap = normalize_item_capabilities(capability)
    if cap.get("schema_version") in (3, 4):
        if blocks not in (None, []):
            raise ValueError("Noncasting item actions cannot declare spell access or a spell-spending budget.")
        return
    if cap.get("schema_version") == 2:
        from .character_item_casting import validate_legacy_spell_support
        validate_legacy_spell_support(cap, blocks)
        return
    casting = cap.get("casting")
    if casting is None:
        return
    from .item_spell_support import parse_item_spell_support
    parsed = parse_item_spell_support(blocks, strict=True)
    if parsed.diagnostics or len(parsed.records) != 1:
        raise ValueError("Item use ownership needs one unambiguous current spell declaration.")
    record = parsed.records[0]
    key_parts = casting["spell_entry_key"].split("|")
    selector_parts = record.spell_selector.split("|")
    spell_name_key = re.sub(r"[^a-z0-9]", "", record.spell.casefold())
    if (record.invalid or record.source_row_kind != "item"
            or len(key_parts) != 4 or not key_parts[2] or not key_parts[3]
            or spell_name_key != re.sub(r"[^a-z0-9]", "", key_parts[3].casefold())
            or len(selector_parts) > 1 and selector_parts[1].casefold() != key_parts[2].casefold()
            or record.source_row_id != casting["source_row_id"]
            or record.source_ability_key != casting["ability"]
            or record.access_type != "free_cast" or record.access_uses != cap["counter"]["maximum"]
            or record.access_reset_on != cap["counter"]["reset_on"]):
        raise ValueError("The item use/casting and spell access declarations disagree.")


def _physical_rows(authority: Any) -> list[Any]:
    return [json.loads(row) for row in authority.equipment_hand_rows or ()]


def _qualified_capability_physical_row(physical: list[Any], identity: str) -> dict[str, Any] | None:
    """The existing exact physical contract; activation clauses stay separate."""
    matches = [row for row in physical if type(row) is dict
               and (row.get("catalog_ref") or row.get("id")) == identity]
    if len(matches) != 1:
        return None
    row = matches[0]
    physical_id = row.get("id")
    if (not _text(physical_id) or sum(type(other) is dict and other.get("id") == physical_id
                                    for other in physical) != 1
            or row.get("activation_current") is not True
            or type(row.get("quantity")) is not int or row["quantity"] != 1):
        return None
    return row


def qualified_item_capabilities(authority: Any, definition: Any) -> list[dict[str, Any]]:
    """Detached exact source/physical facts, with activation kept separate."""
    if authority is None:
        return []
    items = definition.equipment_catalog
    physical = _physical_rows(authority)
    result = []
    for item in items:
        if type(item) is not dict or not _text(item.get("id")) or item.get("mechanics_suppressed"):
            continue
        identity = item["id"]
        if (sum(type(other) is dict and other.get("id") == identity for other in items) != 1
                or authority.status_for("item", identity) != "VERIFIED"):
            continue
        payload = authority.approved_payload("item", identity)
        if FIELD not in payload:
            continue
        try:
            capability = normalize_item_capabilities(payload[FIELD])
        except (TypeError, ValueError):
            continue
        ref = item.get("systems_ref")
        sources = {(grant.source_kind, grant.source_key) for grant in authority.grants
                   if grant.kind == "item" and grant.instance_id == identity
                   and FIELD in json.loads(grant.payload_json)}
        if (type(ref) is not dict or not _text(ref.get("entry_key"))
                or sources != {("systems", ref["entry_key"])}):
            continue
        row = _qualified_capability_physical_row(physical, identity)
        if row is None:
            continue
        physical_id = row["id"]
        result.append({"catalog_id": identity, "physical_id": physical_id,
            "name": str(item.get("name") or "Item"), "source_ref": deepcopy(ref),
            "capability": capability, "physical": deepcopy(row),
            "source_basis_digest": hashlib.sha256(json.dumps({"source": ref, "capability": capability},
                sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()})
    return result


def item_counter_rule(authority: Any, definition: Any, physical_id: str) -> dict[str, Any] | None:
    matches = [entry for entry in qualified_item_capabilities(authority, definition)
               if entry["physical_id"] == physical_id and "counter" in entry["capability"]]
    if len(matches) != 1:
        return None
    return {**matches[0], **deepcopy(matches[0]["capability"]["counter"])}


def known_counter(row: Any, maximum: int) -> bool:
    return (type(row) is dict and type(row.get("charges_current")) is int
            and type(row.get("charges_max")) is int and row["charges_max"] == maximum
            and 0 <= row["charges_current"] <= maximum)


def active_clause(entry: dict[str, Any], mode: str) -> bool:
    physical = entry["physical"]
    if mode == "equipped":
        return physical.get("is_equipped") is True
    return (physical.get("is_attuned") is True
            and (mode == "attuned" or mode == "equipped_attuned" and physical.get("is_equipped") is True))


def qualified_hit_die_recovery_bonus(authority: Any, definition: Any) -> int:
    # Identical source/effect copies do not multiply the same passive benefit.
    bonuses = {}
    for entry in qualified_item_capabilities(authority, definition):
        passive = entry["capability"].get("passive")
        if passive is not None and active_clause(entry, passive["activation"]):
            key = (entry["source_ref"]["entry_key"], entry["capability"]["effect_id"])
            bonuses[key] = passive["hit_die_recovery_bonus"]
    return sum(bonuses.values())


def qualified_sleep_ward_rules(authority: Any, definition: Any) -> list[dict[str, Any]]:
    """Current owned ward declarations; generic metadata/flags cannot issue one."""
    rules = []
    seen = set()
    for entry in qualified_item_capabilities(authority, definition):
        passive = entry["capability"].get("passive")
        if (passive is None or not passive["magical_sleep_ward"]
                or not active_clause(entry, passive["activation"])):
            continue
        identity = (entry["source_ref"]["entry_key"], entry["capability"]["effect_id"])
        if identity in seen:
            continue
        seen.add(identity)
        exception = " except this item's voluntary self-sleep action" if passive["self_sleep_exception"] else ""
        rules.append({"id": entry["capability"]["effect_id"] + ":sleep-ward", "title": entry["name"],
            "active": True, "condition": "While attuned; equipment/hand state is not required.", "inactive_reason": "",
            "effects": [{"kind": "immunity", "label": "Magical sleep ward",
                "summary": "You cannot be put to sleep by magical means" + exception + ". Table managed."}]})
    return rules


def _current_defensive_features(features: Any) -> list[dict[str, Any]]:
    """Give slug and structured-effect producers the same current input frame."""
    return [row for row in features or []
            if isinstance(row, dict) and not row.get("mechanics_suppressed")]


def _source_retires_legacy_sleep_ward(rule: dict[str, Any], capability: Any) -> bool:
    """Negative source declaration only; never qualifies or grants a benefit."""
    if type(capability) is not dict or not _text(capability.get("effect_id")):
        return False
    passive = capability.get("passive")
    return (type(passive) is dict and passive.get("magical_sleep_ward") is True
            and rule.get("id") == f"item:{capability['effect_id']}:sleep-ward")


def compose_defensive_rules(authority: Any, definition: Any, rules: list[Any], *,
                            current_definition: Any, item_catalog: Any) -> list[dict[str, Any]]:
    """Compose current producers, never infer ownership from copied display IDs.

    Original DND defensive-state rows are retained history, not grant inputs.
    Reuse the existing producer with the caller's already-current projection and
    catalogue, including its conditional feat and infusion behavior. Non-DND
    readers keep their existing defensive-state presentation boundary.
    """
    if definition.system != "DND-5E":
        return [deepcopy(row) for row in rules if isinstance(row, dict)]
    if authority is None:
        return []
    from .character_builder_equipment import _derive_defensive_state_from_character_inputs
    from .character_source_authority import _source_identity
    produced = _derive_defensive_state_from_character_inputs(
        equipment_catalog=list(current_definition.equipment_catalog or []),
        features=_current_defensive_features(current_definition.features), item_catalog=item_catalog,
    )["rules"]
    items = [row for row in current_definition.equipment_catalog or [] if type(row) is dict]
    original_items = [row for row in definition.equipment_catalog or [] if type(row) is dict]
    owners = set()
    declarations = {}
    for item in items:
        identity = item.get("id")
        if (not _text(identity) or sum(row.get("id") == identity for row in items) != 1
                or item.get("mechanics_suppressed")
                or authority.status_for("item", identity) != "VERIFIED"
                or identity not in authority.active_item_ids):
            continue
        originals = [row for row in original_items if row.get("id") == identity]
        source = _source_identity(item)
        if (len(originals) != 1 or not all(source)
                or _source_identity(originals[0]) != source):
            continue
        sources = {(grant.source_kind, grant.source_key) for grant in authority.grants
                   if grant.kind == "item" and grant.instance_id == identity
                   and "defensive_rules" in json.loads(grant.payload_json)}
        if sources == {source}:
            owners.add(identity)
            capability_sources = {(grant.source_kind, grant.source_key) for grant in authority.grants
                                  if grant.kind == "item" and grant.instance_id == identity
                                  and FIELD in json.loads(grant.payload_json)}
            if capability_sources == {source}:
                declarations[identity] = authority.approved_payload("item", identity).get(FIELD)
    result = []
    for rule in produced:
        if "source_item_id" not in rule:
            # Feature IDs may have any spelling or collide with item IDs. The
            # fresh producer's origin, not that spelling, keeps them distinct.
            result.append(rule)
            continue
        identity = rule["source_item_id"]
        if identity not in owners:
            continue
        if _source_retires_legacy_sleep_ward(rule, declarations.get(identity)):
            # Retire the same source's old rule even if its native benefit
            # cannot qualify physically. Only the passive producer below can
            # grant the current ward, with its full qualification and activation.
            continue
        # This DTO already came from full current metadata in the ordinary
        # producer. An effect-only AuthorityGrant is not full metadata and must
        # not be sent through a second capability/source validator here.
        result.append(rule)
    result.extend(qualified_sleep_ward_rules(authority, definition))
    return result


def item_casting_presentation(authority: Any, definition: Any, spell: dict[str, Any]) -> dict[str, Any] | None:
    """Current formula/rider facts only; never a cast, slot spend or use write."""
    ref = spell.get("systems_ref")
    if type(ref) is not dict:
        return None
    row_id = spell.get("spell_source_row_id") or spell.get("authority_original_source_row_id")
    matches = [entry for entry in qualified_item_capabilities(authority, definition)
               if (entry["capability"].get("casting") or {}).get("source_row_id") == row_id
               and (entry["capability"].get("casting") or {}).get("spell_entry_key") == ref.get("entry_key")]
    if not matches:
        return None
    result = {"status": "UNKNOWN", "reason": "item_casting_owner_unavailable", "label": "Unavailable",
              "options": [], "casting_level": None, "damage": "", "available": False}
    if len(matches) != 1 or authority.spell_status(spell, definition=definition) != "VERIFIED":
        return result
    entry = matches[0]
    casting = entry["capability"]["casting"]
    result.update(physical_id=entry["physical_id"], counter_cost=casting["counter_cost"], slot_cost=0,
                  source_row_id=row_id, source_ref=entry["source_ref"], source_basis_digest=entry["source_basis_digest"])
    if not active_clause(entry, casting["activation"]):
        return dict(result, reason="item_casting_inactive")
    ability = authority.field_status(f"stats.ability_scores.{casting['ability']}.score")
    proficiency = authority.field_status("stats.proficiency_bonus")
    if (not ability.is_effective or not proficiency.is_effective
            or type(ability.effective) is not int or type(proficiency.effective) is not int):
        return dict(result, reason="item_casting_inputs_unavailable")
    slots = [row for row in authority.resource_statuses if row.path.startswith("spell_slot:")]
    if not slots or any(not row.is_effective or type(row.effective) is not dict
                        or type(row.effective.get("max")) is not int or type(row.effective.get("level")) is not int
                        for row in slots):
        return dict(result, reason="item_casting_slot_capacity_unavailable")
    levels = [row.effective["level"] for row in slots if row.effective["max"] > 0
              and 1 <= row.effective["level"] <= 9]
    if not levels:
        return dict(result, reason="item_casting_slot_capacity_unavailable")
    level = max(levels)
    dc = 8 + proficiency.effective + (ability.effective - 10) // 2
    rider = casting["rider"]
    label = f"{casting['save_ability'].upper()} {dc}"
    status = authority.resource_status("item_charge", entry["physical_id"])
    available = status.is_effective and status.effective["current"] >= casting["counter_cost"]
    return {**result, "status": "VERIFIED", "reason": "current_item_rules_and_qualified_inputs", "label": label,
        "casting_level": level, "save_dc": dc, "save_ability": casting["save_ability"],
        "damage": f"{rider['dice_per_spell_level'] * level}d{rider['die_faces']}",
        "damage_type": rider["damage_type"], "half_on_save": rider["half_on_save"],
        "damage_ends_spell": rider["damage_ends_spell"], "available": available,
        "availability_reason": "" if available else "Item uses are unrecorded or exhausted.",
        "options": [{"family": "source", "owner_id": row_id, "kind": "item_casting_variant", "label": label}],
        "table_managed": True}
