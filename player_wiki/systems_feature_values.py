"""Versioned, source-owned feature values; no Character or Systems writes.

Only these registered PHB families are supported initially. Import preserves the
actual table cells; reading never invents a missing table or interprets prose.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import re


VERSION = 1
FIELD = "feature_values"
TABLE_FIELD = "feature_value_tables"
SOURCE_TABLE_FIELD = "feature_value_source_tables"
ROGUE = "dnd-5e|class|phb|rogue"
CLERIC = "dnd-5e|class|phb|cleric"
SNEAK = "dnd-5e|classfeature|phb|sneakattack-rogue-phb-1"
DESTROY = {
    f"dnd-5e|classfeature|phb|destroyundead{suffix}-cleric-phb-{level}": level
    for suffix, level in (("cr12", 5), ("cr1", 8), ("cr2", 11), ("cr3", 14), ("cr4", 17))
}
# Explicit PHB2014 publication semantics, verified against each genuine source
# clause during import. A metadata-only edit cannot contradict that rule text.
_DESTROY_CR = {5: (1, 2), 8: (1, 1), 11: (2, 1), 14: (3, 1), 17: (4, 1)}
_ROGUE_TABLE_DIGEST = "1f09a2eb294ef2e7dabfcbc138a53888e29f4c8aa1cfb3606af6436a1bdd15de"
_BODY_DIGESTS = {
    SNEAK: "334b2839d9f4ac878fa1662620d4146f582c4b450f25ff5dddef3084b6b62343",
    **{key: digest for key, digest in zip(DESTROY, (
        "ce814119bc4957d48ecf7ee0535991513e5dbf1fc3f3cf31a49a13e0cc1e5635",
        "14d548488aea0f9bad1b6bcb61bdfba42522aa6f63e370295c4fc802d1d69c15",
        "5e283a1eb6287ca4121afbd64b1d2ea9fec075a719f09896467f9f370ca96c17",
        "46b16b745975b2a872632a7208331ba79d47993e3e27c75f61d63301c01c944e",
        "5b4447902f9b8a1b4de22df967631f4f2a7c93a864a872f14476f8c3d017b4c9",
    ))},
}
_SNEAK_SPEC = {"family": "phb:rogue:sneak-attack", "owner": ROGUE,
               "facet": "damage", "evolution": "level_table", "label": "Current Sneak Attack"}
_DESTROY_SPEC = {"family": "phb:cleric:destroy-undead", "owner": CLERIC,
                 "facet": "maximum_cr", "evolution": "improves_facet", "label": "Destroy Undead maximum CR"}


def source_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def family_spec(entry_key):
    """Exact publication registration, never a display-name equivalence."""
    if not isinstance(entry_key, str):
        return None
    if entry_key == SNEAK:
        return {**_SNEAK_SPEC, "level": 1, "class_name": "Rogue"}
    if entry_key in DESTROY:
        level = DESTROY[entry_key]
        n, d = _DESTROY_CR[level]
        return {**_DESTROY_SPEC, "level": level, "class_name": "Cleric",
                "expected_value": {"kind": "rational", "numerator": n, "denominator": d}}
    return None


def validate_value(value):
    if type(value) is not dict:
        raise ValueError("Feature value is not structured.")
    kind = value.get("kind")
    if kind == "dice" and set(value) == {"kind", "number", "faces"}:
        if type(value["number"]) is int and 1 <= value["number"] <= 100 and type(value["faces"]) is int and 2 <= value["faces"] <= 100:
            return deepcopy(value)
    if kind == "rational" and set(value) == {"kind", "numerator", "denominator"}:
        n, d = value["numerator"], value["denominator"]
        if type(n) is int and type(d) is int and 0 <= n <= 30 and d in {1, 2, 4, 8} and Fraction(n, d) <= 30:
            return deepcopy(value)
    raise ValueError("Feature value type or bounds are unsupported.")


def normalize_sneak_table(group):
    """Read the genuine source's positional rows without generic data cleaning."""
    if type(group) is not dict or group.get("colLabels") != ["Sneak Attack"]:
        raise ValueError("The exact Rogue damage table is unavailable.")
    rows = group.get("rows")
    if type(rows) is not list or len(rows) != 20:
        raise ValueError("Rogue damage requires twenty explicit source levels.")
    result = []
    for level, row in enumerate(rows, 1):
        if type(row) is not list or len(row) != 1 or type(row[0]) is not dict:
            raise ValueError("Rogue damage has an unsupported source cell.")
        cell = row[0]
        if set(cell) != {"type", "toRoll", "rollable"} or cell["type"] != "dice" or cell["rollable"] is not True:
            raise ValueError("Rogue damage is not an explicit dice cell.")
        dice = cell["toRoll"]
        if type(dice) is not list or len(dice) != 1 or type(dice[0]) is not dict or set(dice[0]) != {"number", "faces"}:
            raise ValueError("Rogue damage contains unsupported dice.")
        result.append({"level": level, "value": validate_value({"kind": "dice", **dice[0]})})
    return result


def import_class_values(raw):
    if (raw.get("name"), raw.get("source")) != ("Rogue", "PHB"):
        return {}, {}
    groups = raw.get("classTableGroups")
    matches = [(i, g) for i, g in enumerate(groups if type(groups) is list else [])
               if type(g) is dict and g.get("colLabels") == ["Sneak Attack"]]
    if len(matches) != 1:
        raise ValueError("PHB Rogue requires one exact Sneak Attack source table.")
    index, group = matches[0]
    if source_digest(group) != _ROGUE_TABLE_DIGEST:
        raise ValueError("Rogue damage source needs a reviewed versioned scaling contract.")
    table = {"version": VERSION, "owner": ROGUE, "source_path": f"classTableGroups.{index}",
             "source_sha256": source_digest(group), "rows": normalize_sneak_table(group)}
    return {"sneak_attack_damage": table}, {"sneak_attack_damage": deepcopy(group)}


def import_feature_values(raw):
    """Normalize only registered exact source identities during import."""
    owner, name, level = raw.get("className"), raw.get("name"), raw.get("level")
    if raw.get("source") != "PHB" or raw.get("classSource", "PHB") != "PHB" or type(level) is not int:
        return None
    if (owner, name, level) == ("Rogue", "Sneak Attack", 1):
        key = SNEAK
    elif owner == "Cleric" and level in DESTROY.values():
        # A closed member mapping; similarly named features are not included.
        names = {5: "Destroy Undead (CR 1/2)", 8: "Destroy Undead (CR 1)",
                 11: "Destroy Undead (CR 2)", 14: "Destroy Undead (CR 3)", 17: "Destroy Undead (CR 4)"}
        if name != names[level]:
            return None
        key = next(k for k, v in DESTROY.items() if v == level)
    else:
        return None
    spec = family_spec(key)
    contract = {k: spec[k] for k in ("family", "owner", "facet", "evolution")}
    contract.update(version=VERSION, scope="class_row", level=level,
                    body_sha256=source_digest({"entries": raw.get("entries")}))
    if contract["body_sha256"] != _BODY_DIGESTS[key]:
        raise ValueError("Feature source rules need a reviewed versioned scaling contract.")
    if key == SNEAK:
        contract["table_id"] = "sneak_attack_damage"
    else:
        entries = raw.get("entries")
        if type(entries) is not list or len(entries) != 1 or type(entries[0]) is not str:
            raise ValueError("Destroy Undead needs its explicit source rule.")
        rule = entries[0]
        match = re.fullmatch(
            r"Starting at (\d+)(?:st|nd|rd|th) level, when an \{@filter undead of CR ([0-9/]+) or lower\|bestiary\|challenge rating=\[&0;&([0-9/]+)\]\|type=undead\|miscellaneous=!swarm\} fails its saving throw against your Turn Undead feature, the creature is instantly destroyed\.", rule)
        if not match or int(match[1]) != level or match[2] != match[3]:
            raise ValueError("Destroy Undead source semantics require review.")
        cr = Fraction(match[2])
        contract["value"] = validate_value({"kind": "rational", "numerator": cr.numerator, "denominator": cr.denominator})
        if contract["value"] != spec["expected_value"]:
            raise ValueError("Destroy Undead publication semantics require a reviewed contract update.")
    return contract


def current_contract(entry):
    """Fail closed if a publication or its source-owned declaration changed."""
    spec = family_spec(entry.entry_key)
    if spec is None:
        return None
    metadata = entry.metadata
    c = metadata.get(FIELD)
    common = {"version", "family", "owner", "facet", "evolution", "scope", "level", "body_sha256"}
    extra = {"table_id"} if entry.entry_key == SNEAK else {"value"}
    if (entry.library_slug != "DND-5E" or entry.source_id != "PHB" or entry.entry_type != "classfeature"
            or metadata.get("class_name") != spec["class_name"] or metadata.get("class_source") != "PHB"
            or type(metadata.get("level")) is not int or metadata["level"] != spec["level"]
            or type(c) is not dict or set(c) != common | extra
            or type(c.get("version")) is not int or c["version"] != VERSION
            or c.get("scope") != "class_row" or type(c.get("level")) is not int or c["level"] != spec["level"]
            or any(c.get(k) != spec[k] for k in ("family", "owner", "facet", "evolution"))
            or c.get("body_sha256") != _BODY_DIGESTS[entry.entry_key]
            or source_digest(entry.body) != _BODY_DIGESTS[entry.entry_key]):
        raise ValueError("Current source scaling data needs import or repair.")
    if entry.entry_key == SNEAK:
        if c["table_id"] != "sneak_attack_damage":
            raise ValueError("The source scaling table is unsupported.")
    else:
        if validate_value(c["value"]) != spec["expected_value"]:
            raise ValueError("The source scaling value contradicts its registered publication.")
    return deepcopy(c)


def value_for_level(contract, owner_entry, level):
    if type(level) is not int or not contract["level"] <= level <= 20:
        raise ValueError("Feature scaling needs its attained owning class level.")
    if owner_entry.entry_key != contract["owner"] or owner_entry.library_slug != "DND-5E" or owner_entry.source_id != "PHB" or owner_entry.entry_type != "class":
        raise ValueError("Feature scaling class publication does not match.")
    if contract["evolution"] == "improves_facet":
        return validate_value(contract["value"])
    tables = owner_entry.metadata.get(TABLE_FIELD)
    sources = owner_entry.body.get(SOURCE_TABLE_FIELD)
    table_id = contract["table_id"]
    t = tables.get(table_id) if type(tables) is dict else None
    raw = sources.get(table_id) if type(sources) is dict else None
    if (type(t) is not dict or set(t) != {"version", "owner", "source_path", "source_sha256", "rows"}
            or type(t.get("version")) is not int or t["version"] != VERSION or t.get("owner") != contract["owner"]
            or not isinstance(t.get("source_path"), str) or re.fullmatch(r"classTableGroups\.\d+", t["source_path"]) is None
            or t.get("source_sha256") != _ROGUE_TABLE_DIGEST or source_digest(raw) != _ROGUE_TABLE_DIGEST
            or source_digest(t.get("rows")) != source_digest(normalize_sneak_table(raw))):
        raise ValueError("Current owning-class scaling table needs import or repair.")
    return validate_value(t["rows"][level - 1]["value"])


def value_label(value):
    value = validate_value(value)
    if value["kind"] == "dice":
        return f"{value['number']}d{value['faces']}"
    return str(Fraction(value["numerator"], value["denominator"]))
