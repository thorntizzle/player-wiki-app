"""Current local Wizard rule dependencies and nonpersisted read guidance.

No acquisition, casting, item entitlement or resource transition is issued here.
Unrecognized source prose supplies no ritual/recovery benefit.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .system_policy import DND_5E_SYSTEM_CODE

_WIZARD = "dnd-5e|class|phb|wizard"
_SPELLCASTING = "dnd-5e|classfeature|phb|spellcasting-wizard-phb-1"
_RECOVERY = "dnd-5e|classfeature|phb|arcanerecovery-wizard-phb-1"
# Closed normalized source contracts; keep proprietary publication prose out of
# application source. The independent source review owns their derivation.
_RITUAL_DIGEST = "f34763ae041ac1626c781e143a344f56aabb635e068b78edd10fce68e1f4b4ce"
_RECOVERY_DIGEST = "4ce5d9f23b2cbf23c15ae48bf01332610245fbb9a16c5ae237ab92da4623afae"
_RULE_BODIES = {
    _SPELLCASTING: "d66e353a2c7c0ada4baefd68db2af753b72876d142ac3c28e96fe60d4a4b841c",
    _RECOVERY: "a4a9640331ae846767d033b763177c5a4fe5f052c027ead6bb5a44c2ebfc01d5",
}


def _entry_frame(entry):
    return {key: deepcopy(getattr(entry, key, None)) for key in (
        "entry_key", "entry_type", "source_id", "library_slug", "slug", "title", "metadata", "body")}


def spellbook_rule_basis(definition, row, service):
    """Complete local source frame, independent of mutable preparation lists."""
    from .character_builder_foundation import (_effective_spellcasting_profile_for_row,
                                               _spellcasting_mode_from_progression)
    def exact(ref, kind):
        if type(ref) is not dict or not ref.get("entry_key"):
            return None
        entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        return entry if entry is not None and entry.entry_type == kind and all(
            value == getattr(entry, key, None) for key, value in ref.items()) else None
    cls = exact(row.get("systems_ref"), "class")
    sub = exact(row.get("subclass_ref"), "subclass") if row.get("subclass_ref") else None
    level = row.get("level")
    collector = getattr(service, "collect_attained_deterministic_feature_entries", None)
    if (cls is None or row.get("subclass_ref") and sub is None or type(level) is not int
            or not 1 <= level <= 20 or not callable(collector)):
        return None
    profile = _effective_spellcasting_profile_for_row(cls.title, row_level=level,
        selected_class=cls, selected_subclass=sub)
    if _spellcasting_mode_from_progression(profile) != "wizard":
        return None
    rules = {}
    for owner in (cls, sub):
        if owner is not None:
            for feature in collector(definition.campaign_slug, owner, attained_level=level):
                frame = _entry_frame(feature)
                if feature.entry_key in rules and rules[feature.entry_key] != frame:
                    return None
                rules[feature.entry_key] = frame
    return {"recipe": "wizard-spellbook-v2", "class": _entry_frame(cls),
        "subclass": _entry_frame(sub) if sub else None, "profile": deepcopy(profile),
        "attained_rules": [rules[key] for key in sorted(rules)]}


def _plain(text):
    text = re.sub(r"\{@\w+ ([^{}]+)\}", lambda match: match[1].split("|")[0], str(text))
    return " ".join(text.replace("\u2019", "'").split()).casefold()


def _rule_digest(text):
    return hashlib.sha256(_plain(text).encode("utf-8")).hexdigest()


def _sections(value, name):
    if type(value) is dict:
        if value.get("name") == name:
            yield value.get("entries")
        for child in value.values():
            yield from _sections(child, name)
    elif type(value) is list:
        for child in value:
            yield from _sections(child, name)


def qualified_read_context(authority, definition, service):
    """Exact current PHB class/attained owner and closed rule-text contracts."""
    result = {}
    classes = definition.profile.get("classes", [])
    ids = [row.get("row_id") for row in classes if type(row) is dict]
    if any(type(row_id) is not str or not row_id for row_id in ids) or len(ids) != len(set(ids)):
        return result
    spines = []
    for row in classes:
        if (type(row) is not dict or row.get("row_id") not in authority.verified_class_rows
                or dict(row.get("systems_ref") or {}).get("entry_key") != _WIZARD):
            continue
        basis = spellbook_rule_basis(definition, row, service)
        if basis is None or basis["class"]["library_slug"] != DND_5E_SYSTEM_CODE:
            continue
        spines.append((row, basis))
    for row, basis in spines:
        rules = {rule["entry_key"]: rule for rule in basis["attained_rules"]}
        def owned(key):
            rule = rules.get(key)
            owners = [raw for raw in definition.features if type(raw) is dict
                and dict(raw.get("systems_ref") or {}).get("entry_key") == key]
            # Missing imported ownership is not a new raw fact. Only one exact
            # verified attained spine may supply implicit ownership; explicit
            # conflicting owners and duplicate raw feature rows still withhold.
            implicit = [candidate["row_id"] for candidate, frame in spines
                        if any(rule["entry_key"] == key for rule in frame["attained_rules"])]
            owner_matches = len(owners) == 1 and (
                owners[0]["class_row_id"] == row["row_id"] if "class_row_id" in owners[0]
                else key == _SPELLCASTING and implicit == [row["row_id"]])
            return rule if (rule is not None and rule["entry_type"] == "classfeature"
                and rule["source_id"] == "PHB" and rule["library_slug"] == DND_5E_SYSTEM_CODE
                and hashlib.sha256(json.dumps(rule["body"], sort_keys=True, ensure_ascii=False,
                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest() == _RULE_BODIES[key]
                and owner_matches
                and authority.status_for("feature", owners[0].get("id")) == "VERIFIED"
                and all(value == rule.get(field) for field, value in owners[0]["systems_ref"].items())) else None
        casting, recovery = owned(_SPELLCASTING), owned(_RECOVERY)
        sections = list(_sections(casting["body"], "Ritual Casting")) if casting else []
        ritual = (len(sections) == 1 and type(sections[0]) is list
            and all(type(text) is str for text in sections[0])
            and _rule_digest(" ".join(sections[0])) == _RITUAL_DIGEST)
        paragraphs = recovery["body"].get("entries", []) if recovery and type(recovery["body"]) is dict else []
        recovery_rule = bool(paragraphs and type(paragraphs[0]) is str
            and _rule_digest(paragraphs[0]) == _RECOVERY_DIGEST)
        result[row["row_id"]] = {"ritual": ritual,
            "recovery_budget": (row["level"] + 1) // 2 if recovery_rule else None}
    return result
