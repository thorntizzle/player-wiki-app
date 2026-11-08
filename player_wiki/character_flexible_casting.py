"""PHB2014 Flexible Casting: qualified rules, temporary slots and atomic intent.

Class capacity and feature-granted capacity stay distinct. Existing guarded
state actions own exchanges; ordinary publications preserve source pools.
"""
from __future__ import annotations

import hashlib
import json
import re

from .system_policy import DND_5E_SYSTEM_CODE

RULE_KEY = "phb2014.sorcerer.flexible_casting.v1"
COSTS = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}
_BODY_DIGESTS = {
    "phb-classfeature-fontofmagic-sorcerer-phb-2": "d14a2087cb0c2df19250e545b9f25ff7c9a5ebe4c140c8a3886d378dbec50d02",
    "phb-classfeature-sorcerypoints-sorcerer-phb-2": "cc6bc5b3a85c4546b1872c2b668affa31473a419d053135e66b73c41307b03bd",
    "phb-classfeature-flexiblecasting-sorcerer-phb-2": "e309fdaa17c63396a2c1048866383e47b0489fd8e2b104064860bafcae1b2a4b",
}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _integer(value, minimum=1, maximum=9):
    if type(value) is str and value.isascii() and value.isdecimal() and len(value) <= 10:
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Choose a valid spell-slot level or count.")
    return value


def _reference(entry):
    return {**{key: getattr(entry, key) for key in
        ("entry_key", "entry_type", "library_slug", "source_id", "slug")},
        "metadata_digest": _digest(entry.metadata), "body_digest": _digest(entry.body)}


def _rule_basis(rule):
    return _digest({key: rule[key] for key in ("key", "class_row_id", "class_ref", "sources")})


def _valid_rule(rule):
    if (type(rule) is not dict or set(rule) != {"key", "class_row_id", "class_ref", "sources", "feature_ids", "basis"}
            or rule.get("key") != RULE_KEY or type(rule.get("class_row_id")) is not str or not rule["class_row_id"]
            or type(rule.get("feature_ids")) is not list or not rule["feature_ids"]
            or any(type(v) is not str or not v for v in rule["feature_ids"])
            or len(set(rule["feature_ids"])) != len(rule["feature_ids"])
            or type(rule.get("sources")) is not list or len(rule["sources"]) != 3):
        return False
    refs = [rule.get("class_ref"), *rule["sources"]]
    keys = {"entry_key", "entry_type", "library_slug", "source_id", "slug", "metadata_digest", "body_digest"}
    # Library records retain the canonical Systems spelling; entry-key prefixes
    # are a separate normalized representation and are never substituted here.
    if any(type(ref) is not dict or set(ref) != keys or ref.get("library_slug") != DND_5E_SYSTEM_CODE
           or ref.get("source_id") != "PHB"
           or any(type(ref.get(k)) is not str or not ref[k] for k in ("entry_key", "entry_type", "slug"))
           or not _sha(ref.get("metadata_digest")) or not _sha(ref.get("body_digest")) for ref in refs):
        return False
    if refs[0]["entry_type"] != "class" or refs[0]["slug"] != "phb-class-sorcerer":
        return False
    if ({ref["slug"] for ref in refs[1:]} != set(_BODY_DIGESTS)
            or any(ref["entry_type"] != "classfeature" or ref["body_digest"] != _BODY_DIGESTS[ref["slug"]] for ref in refs[1:])):
        return False
    return rule.get("basis") == _rule_basis(rule)


def _source_rule_facts(definition, systems_service, pool, *, verified_feature=None):
    from .character_source_authority import _current_systems_entry, _source_identity
    if pool is None:
        return None
    owner = pool["class"]
    level = owner.get("level")
    parent = _current_systems_entry(definition.campaign_slug, *_source_identity(owner), systems_service)
    collector = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
    if (parent is None or parent.entry_type != "class" or parent.library_slug != DND_5E_SYSTEM_CODE
            or parent.source_id != "PHB" or parent.title.casefold() != "sorcerer"
            or type(level) is not int or not 2 <= level <= 20 or not callable(collector)):
        return None
    members = pool["members"]
    if any(row["canonical"].get("systems_ref", {}).get("slug") not in set(_BODY_DIGESTS) - {
            "phb-classfeature-flexiblecasting-sorcerer-phb-2"} for row in members):
        return None
    attained = collector(definition.campaign_slug, parent, attained_level=level)
    sources = []
    for slug, expected_body in _BODY_DIGESTS.items():
        entry = _current_systems_entry(definition.campaign_slug, "systems_slug", slug, systems_service)
        if (entry is None or entry.entry_type != "classfeature" or entry.source_id != "PHB"
                or entry.library_slug != DND_5E_SYSTEM_CODE or entry.metadata.get("class_name") != "Sorcerer"
                or entry.metadata.get("class_source") != "PHB"
                or type(entry.metadata.get("level")) is not int or entry.metadata["level"] != 2
                or _digest(entry.body) != expected_body
                or sum(row.entry_key == entry.entry_key for row in attained) != 1):
            return None
        retained = [row for row in definition.features if isinstance(row, dict)
            and isinstance(row.get("systems_ref"), dict) and row["systems_ref"].get("slug") == slug]
        if (len(retained) > 1 or any(row.get("mechanics_suppressed")
                or (verified_feature is not None and not verified_feature(row))
                or row.get("class_row_id") != pool["class_row_id"] for row in retained)):
            return None
        sources.append(_reference(entry))
    rule = {"key": RULE_KEY, "class_row_id": pool["class_row_id"], "class_ref": _reference(parent),
        "sources": sources, "feature_ids": sorted(row["feature"]["id"] for row in members)}
    rule["basis"] = _rule_basis(rule)
    return rule if _valid_rule(rule) else None


def source_rule_facts(definition, systems_service, pool):
    """Current source/owner facts only; these issue no mechanical authority.

    Historical classification can bind this same source contract before numeric
    issuance. Only qualify_rule may admit it to an actual slot provider.
    """
    return _source_rule_facts(definition, systems_service, pool)


def qualify_rule(authority, definition, systems_service, pool):
    # Check each retained feature before reading the next source, preserving
    # the qualifier's early-refusal and callback ordering.
    return _source_rule_facts(definition, systems_service, pool,
        verified_feature=lambda row: authority.status_for("feature", str(row.get("id") or "")) == "VERIFIED")



def slot_provider(rule):
    from .character_spell_slots import slot_grant_id
    owner = rule["class_row_id"]
    return {"id": slot_grant_id("feature", RULE_KEY, owner), "source_kind": "feature",
        "source_key": RULE_KEY, "owner": owner, "basis": rule["basis"],
        "lifecycle": "expires_long_rest", "allowed_levels": list(COSTS),
        "required_resources": ["resource:sorcery-points"], "title": "Flexible Casting", "rule": rule}


def _binding(authority):
    from .character_spell_slots import grant_binding
    return grant_binding(authority, "feature", RULE_KEY)


def _points(state, authority):
    rows = [row for row in state.get("resources", []) if type(row) is dict and row.get("id") == "sorcery-points"]
    status = authority.resource_status("resource", "sorcery-points")
    if len(rows) != 1 or not status.is_effective or type(status.effective) is not dict:
        raise ValueError("Sorcery Point ownership needs repair.")
    current, maximum = rows[0].get("current"), status.effective.get("max")
    if type(current) is not int or type(maximum) is not int or not 0 <= current <= maximum:
        raise ValueError("Current Sorcery Points need repair.")
    return rows[0], current, maximum


def apply_conversion(state, definition, authority, params):
    from .character_spell_slots import (slot_value_digest, add_slot_grant_capacity,
        spend_slot_contribution)
    if authority is None or slot_value_digest(state) != authority.state_digest:
        raise ValueError("Flexible Casting state changed. Refresh before acting.")
    binding = _binding(authority)
    if binding is None:
        raise ValueError("Current PHB2014 Flexible Casting source needs repair.")
    level = _integer(params["level"])
    _, current, maximum = _points(state, authority)
    direction = params["direction"]
    if direction == "create":
        if level not in COSTS or current < COSTS[level]:
            raise ValueError("Not enough Sorcery Points for that created slot.")
        result = add_slot_grant_capacity(state, authority, binding, level)
        points, _, _ = _points(result, authority)
        points["current"] = current - COSTS[level]
    elif direction == "convert":
        if current + level > maximum:
            raise ValueError("That conversion would exceed the Sorcery Point maximum.")
        result = spend_slot_contribution(state, definition.spellcasting, authority,
            str(params.get("pool_id") or "").strip(), level)
        points, _, _ = _points(result, authority)
        points["current"] = current + level
    else:
        raise ValueError("Choose a supported Flexible Casting conversion.")
    return result


def prepare_conversion(state, definition, authority, direction, level, pool_id=""):
    from .character_spell_slots import slot_grant_intent
    params = {"kind": "flexible_casting", "direction": str(direction or "").strip(),
        "level": _integer(level), "pool_id": str(pool_id or "").strip()}
    result = apply_conversion(state, definition, authority, params)
    return result, slot_grant_intent(state, result, params)


def presentation(authority, state, options):
    from .character_spell_slots import _grant_context, slot_grant_destination_ready
    candidates = [row for row in _grant_context(authority)["providers"]
        if row["source_kind"] == "feature" and row["source_key"] == RULE_KEY]
    if not candidates:
        return None
    binding = _binding(authority)
    try:
        _, current, maximum = _points(state, authority)
    except ValueError:
        current = maximum = None
    enabled = binding is not None and current is not None
    pool_ready = slot_grant_destination_ready(authority, binding)
    return {"enabled": enabled, "label": "Flexible Casting", "action_cost": "Bonus action on your turn",
        "current": current, "maximum": maximum,
        "expiry": "Created slot capacity, including spent slots, disappears at the end of a long rest.",
        "create_options": [{"level": level, "cost": cost, "enabled": enabled and current >= cost and pool_ready}
            for level, cost in COSTS.items()],
        "convert_options": [{**row, "enabled": enabled and type(row.get("available")) is int
            and row["available"] > 0 and current + row["level"] <= maximum} for row in options],
        "repair_reason": "" if enabled and pool_ready else "Current Flexible Casting source or slot pool needs repair."}
