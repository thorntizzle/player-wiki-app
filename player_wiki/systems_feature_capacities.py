"""Source-owned simultaneous capacity, never a spendable resource template."""
from __future__ import annotations

from copy import deepcopy

from .systems_feature_values import source_digest


FIELD = "feature_capacity"
TABLE_FIELD = "feature_capacity_tables"
SOURCE_FIELD = "feature_capacity_source_tables"
ARTIFICER = "dnd-5e|class|tce|artificer"
TINKERING = "dnd-5e|classfeature|tce|magicaltinkering-artificer-tce-1"
INFUSE = "dnd-5e|classfeature|tce|infuseitem-artificer-tce-2"
TABLE_ID = "infused_items"
TABLE_DIGEST = "b00f57f212a58c212b25b973dd81e4f68b6909a24f09acbd5b3bc74447cf1a0e"
SPECS = {
    TINKERING: {"level": 1, "name": "Magical Tinkering", "label": "Maximum simultaneous tinkered objects",
               "body_sha256": "8a398f2d17f6ed6613e7eff1282b4bde0cc1f39715dfe6fa43ffffadd3ddc000",
               "formula": {"kind": "ability_modifier", "ability": "int", "minimum": 1}},
    INFUSE: {"level": 2, "name": "Infuse Item", "label": "Maximum simultaneously infused items",
             "body_sha256": "25458bc39caf4b4ba013c38185e49ea2be6158c91f9f3be2b34418ae9808a6dc",
             "formula": {"kind": "class_table", "table_id": TABLE_ID}},
}


def declaration(key):
    spec = SPECS[key]
    return {"version": 1, "owner": ARTIFICER, "scope": "class_row",
            "kind": "simultaneous_objects", "level": spec["level"],
            "body_sha256": spec["body_sha256"], "formula": deepcopy(spec["formula"])}


def normalize_table(raw):
    if type(raw) is not dict or source_digest(raw) != TABLE_DIGEST:
        raise ValueError("Artificer capacity source table needs a reviewed versioned contract.")
    rows = raw.get("rows")
    labels = raw.get("colLabels")
    if (type(labels) is not list or len(labels) != 3 or labels[1] != "Infused Items"
            or type(rows) is not list or len(rows) != 20):
        raise ValueError("Artificer capacity requires the actual Infused Items column.")
    result = []
    for level, row in enumerate(rows, 1):
        if type(row) is not list or len(row) != 3 or type(row[1]) is not int or not 0 <= row[1] <= 20:
            raise ValueError("Artificer capacity source cell is invalid.")
        result.append({"level": level, "maximum": row[1]})
    return result


def import_class_capacities(raw):
    if (raw.get("name"), raw.get("source")) != ("Artificer", "TCE"):
        return {}, {}
    groups = raw.get("classTableGroups")
    matches = [(i, group) for i, group in enumerate(groups if type(groups) is list else [])
               if type(group) is dict and type(group.get("colLabels")) is list
               and "Infused Items" in group["colLabels"]]
    if len(matches) != 1:
        raise ValueError("TCE Artificer needs one explicit Infused Items table.")
    index, group = matches[0]
    table = {"version": 1, "owner": ARTIFICER, "source_path": f"classTableGroups.{index}",
             "source_sha256": TABLE_DIGEST, "rows": normalize_table(group)}
    return {TABLE_ID: table}, {TABLE_ID: deepcopy(group)}


def import_feature_capacity(raw):
    if (raw.get("className"), raw.get("classSource"), raw.get("source")) != ("Artificer", "TCE", "TCE"):
        return None
    for key, spec in SPECS.items():
        if raw.get("name") == spec["name"] and type(raw.get("level")) is int and raw["level"] == spec["level"]:
            if source_digest({"entries": raw.get("entries")}) != spec["body_sha256"]:
                raise ValueError("Feature capacity rules need a reviewed versioned contract.")
            return declaration(key)
    return None


def current_capacity(entry, owner, level, *, ability_scores=None):
    """Caller proves acquisition and owner; this validates actual source semantics."""
    spec = SPECS.get(entry.entry_key)
    if spec is None:
        raise ValueError("This feature has no supported capacity contract.")
    metadata = entry.metadata
    if (type(metadata) is not dict or entry.library_slug != "DND-5E" or entry.source_id != "TCE" or entry.entry_type != "classfeature"
            or metadata.get("class_name") != "Artificer" or metadata.get("class_source") != "TCE"
            or type(metadata.get("level")) is not int or metadata["level"] != spec["level"]
            or source_digest(metadata.get(FIELD)) != source_digest(declaration(entry.entry_key))
            or source_digest(entry.body) != spec["body_sha256"]):
        raise ValueError("Current feature capacity needs source import or repair.")
    if (owner.entry_key != ARTIFICER or owner.library_slug != "DND-5E" or owner.source_id != "TCE"
            or owner.entry_type != "class" or type(owner.metadata) is not dict or type(owner.body) is not dict
            or type(level) is not int or not spec["level"] <= level <= 20):
        raise ValueError("Capacity needs its attained, exact owning class.")
    formula = spec["formula"]
    if formula["kind"] == "ability_modifier":
        score = (ability_scores or {}).get(formula["ability"])
        if type(score) is not int or not 0 <= score <= 30:
            raise ValueError("Capacity needs a qualified current ability score.")
        return max(formula["minimum"], (score - 10) // 2)
    tables, sources = owner.metadata.get(TABLE_FIELD), owner.body.get(SOURCE_FIELD)
    table = tables.get(TABLE_ID) if type(tables) is dict else None
    raw = sources.get(TABLE_ID) if type(sources) is dict else None
    rows = normalize_table(raw)
    import re
    if (type(table) is not dict or set(table) != {"version", "owner", "source_path", "source_sha256", "rows"}
            or type(table.get("version")) is not int or table["version"] != 1 or table.get("owner") != ARTIFICER
            or table.get("source_sha256") != TABLE_DIGEST or type(table.get("source_path")) is not str
            or re.fullmatch(r"classTableGroups\.\d+", table["source_path"]) is None
            or source_digest(table.get("rows")) != source_digest(rows)):
        raise ValueError("Current class capacity table needs source import or repair.")
    return rows[level - 1]["maximum"]
