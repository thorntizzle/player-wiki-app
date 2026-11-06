"""Read-only attack/save labels from current spell rules and qualified owners.

This module grants no spell, numeric authority or casting permission. Saved
``save_or_hit`` text is never an input. Unmodeled rules remain unavailable.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

_ABILITIES = {
    "strength": "STR", "dexterity": "DEX", "constitution": "CON",
    "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA",
}
_ABILITY_KEYS = {name: value.lower() for name, value in _ABILITIES.items()}
_NAMES = "(?:" + "|".join(_ABILITIES) + ")"
_NAMED_SAVE = re.compile(
    _NAMES + r"(?:\s*(?:,\s*(?:or|and)?|or|and)\s*" + _NAMES
    + r")*\s+saving throws?\b", re.I)
_SAVE_INSTRUCTION = re.compile(
    r"(?:^|[.!?]\s+|,\s+)(?:(?:the|each|a|an|that|any) target|"
    r"(?:each|a|an|the|that|any) (?:(?:unwilling|willing|affected) )?creatures?[^.!?;]{0,160}?|it)"
    r"\s+must\s+(?:make|succeed\s+on)\s+(?:(?:a|an|the)\s+)?"
    + r"(?P<save_clause>" + _NAMED_SAVE.pattern + r")", re.I)
_SAVE = re.compile(r"\bsaving throws?\b", re.I)
_SAVE_MODIFIER_REFERENCE = re.compile(
    r"\b(?:(?:advantage|disadvantage)\s+on\s+(?:(?:all|its|their|your)\s+)?|"
    r"(?:a\s+)?(?:[+-]?\d+\s+)?(?:penalty|bonus)\s+to\s+(?:AC\s+and\s+)?)"
    + _NAMED_SAVE.pattern, re.I)
_ATTACK = re.compile(r"\battacks?\b", re.I)
_SPELL_ATTACK = re.compile(r"\b(?:(?:melee|ranged)\s+)?spell attacks?\b", re.I)
_CASTER_ATTACK = re.compile(
    r"(?:\byou\s+(?:can\s+)?make|(?:^|[.!?]\s+)make)\s+"
    r"(?:(?:a|an|one|two|three)\s+)?(?:(?P<attack_mode>melee|ranged)\s+)?spell attacks?\b", re.I)
_CASTER_ATTACK_INSTRUCTION = re.compile(
    r"(?:\byou\s+(?:can\s+)?make|(?:^|[.!?]\s+)make)\s+"
    r"(?:(?:a|an|one|two|three)\s+)?[^.!?;]{0,48}?\battacks?\b", re.I)
_FIXED_DC = re.compile(r"\{@dc\b|\bDC\s*[0-9]|\bDC\s+(?:equals?|is)\b", re.I)
_OTHER_METRIC = re.compile(
    r"\{@hit|\+[0-9][^.!?]{0,80}spell attack|spell attack[^.!?]{0,80}\+[0-9]|"
    r"\b(?:its|their|his|her|creature's|target's)\s+spell save DC\b", re.I)


def _narrative(body: Any) -> list[tuple[str, bool]] | None:
    """Closed narrative containers only; no tables/statblocks/foreign objects."""
    if type(body) is not dict or set(body) - {"entries", "entries_higher_level"} or "entries" not in body:
        return None
    stack = [(body["entries"], 0, False)]
    if body.get("entries_higher_level") is not None:
        stack.append((body["entries_higher_level"], 0, False))
    strings, nodes, characters = [], 0, 0
    while stack:
        value, depth, heading = stack.pop()
        nodes += 1
        if nodes > 256 or depth > 12:
            return None
        if type(value) is str:
            characters += len(value)
            if characters > 65536:
                return None
            strings.append((value, heading))
        elif type(value) is list:
            if len(value) > 128:
                return None
            stack.extend((child, depth + 1, heading) for child in reversed(value))
        elif type(value) is dict:
            if "name" in value:
                if type(value["name"]) is not str:
                    return None
                stack.append((value["name"], depth + 1, True))
            kind = value.get("type", "entries")
            if kind == "entries" and not set(value) - {"type", "name", "entries"} and "entries" in value:
                if "name" in value and type(value["name"]) is not str:
                    return None
                stack.append((value["entries"], depth + 1, False))
            elif kind == "list" and not set(value) - {"type", "items", "style"} and "items" in value:
                if "style" in value and type(value["style"]) is not str:
                    return None
                stack.append((value["items"], depth + 1, False))
            elif kind == "item" and not set(value) - {"type", "name", "entry", "entries"}:
                keys = set(value) & {"entry", "entries"}
                if len(keys) != 1 or "name" in value and type(value["name"]) is not str:
                    return None
                stack.append((value[next(iter(keys))], depth + 1, False))
            else:
                return None
        else:
            return None
    return strings if any(value.strip() and not heading for value, heading in strings) else None


def _roll_rules(entry: Any, *, unavailable_reasons: list[str] | None = None) -> tuple[bool, tuple[str, ...]] | None:
    def unavailable(reason):
        if unavailable_reasons is not None:
            unavailable_reasons.append(reason)
        return None

    metadata = getattr(entry, "metadata", None)
    if type(metadata) is not dict:
        return unavailable("spell_rule_metadata_unavailable")
    declared = {}
    for key, allowed in (("savingThrow", set(_ABILITY_KEYS.values())), ("spellAttack", {"M", "R", "O"})):
        if key not in metadata:
            continue
        values = metadata[key]
        if (type(values) is not list or len(values) > 6
                or any(type(value) is not str or value not in allowed for value in values)
                or len(set(values)) != len(values)):
            return unavailable("spell_metric_declaration_invalid")
        declared[key] = values
    strings = _narrative(getattr(entry, "body", None))
    if strings is None:
        return unavailable("spell_rule_structure_unsupported")
    attack_modes, saves, mentioned_saves = set(), set(), set()
    for text, heading in strings:
        text = " ".join(text.split())
        if heading and re.search(r"\b(?:" + _NAMES + r"|rolls?|saves?|attacks?|DC|difficulty class)\b|[0-9]", text, re.I):
            return unavailable("spell_metric_heading_unsupported")
        # Fixed/external DC contracts and structured action tags require their
        # own interpretation; they must never receive the caster's ordinary DC.
        if _FIXED_DC.search(text) or _OTHER_METRIC.search(text) or "{@act" in text or "{@atk" in text:
            return unavailable("spell_metric_nonstandard_or_external")
        for dc in re.finditer(r"\bDC\b", text, re.I):
            if not re.search(r"\byour\s+(?:spell save|saving throw)\s+$", text[:dc.start()], re.I):
                return unavailable("spell_metric_nonstandard_or_external")
        named = list(_NAMED_SAVE.finditer(text))
        matches = [] if heading else list(_SAVE_INSTRUCTION.finditer(text))
        if any(not any(start <= match.start() and match.end() <= end for start, end in
                       ((value.start(), value.end()) for value in named))
                   for match in _SAVE.finditer(text)):
            return unavailable("spell_save_instruction_unsupported")
        for match in matches:
            saves.update(_ABILITIES[name.casefold()] for name in re.findall(_NAMES, match.group("save_clause"), re.I))
        modifiers = list(_SAVE_MODIFIER_REFERENCE.finditer(text))
        for mention in named:
            # A penalty/advantage reference is not an instruction to roll
            # against this caster's DC. All other named saves must still be
            # accounted for by a recognized actual save instruction.
            if not any(value.start() <= mention.start() and mention.end() <= value.end() for value in modifiers):
                mentioned_saves.update(_ABILITIES[name.casefold()]
                    for name in re.findall(_NAMES, mention.group(), re.I))
        attacks = list(_SPELL_ATTACK.finditer(text))
        caster_attacks = [] if heading else list(_CASTER_ATTACK.finditer(text))
        if any(not any(value.start() <= match.start() and match.end() <= value.end()
                       for value in caster_attacks) for match in attacks):
            return unavailable("spell_attack_instruction_unsupported")
        if any(not any(value.start() <= match.start() and match.end() <= value.end()
                       for value in caster_attacks) for match in _CASTER_ATTACK_INSTRUCTION.finditer(text)):
            return unavailable("spell_attack_instruction_unsupported")
        attack_modes.update({"melee": "M", "ranged": "R"}.get(
            (match.group("attack_mode") or "").casefold(), "O") for match in caster_attacks)
    attack = bool(attack_modes)
    if not mentioned_saves <= saves:
        return unavailable("spell_save_instruction_unsupported")
    if "savingThrow" in declared:
        declared_saves = {name.upper() for name in declared["savingThrow"]}
        if declared_saves != saves:
            return unavailable("spell_metric_declaration_conflict")
    if "spellAttack" in declared and set(declared["spellAttack"]) != attack_modes:
        return unavailable("spell_metric_declaration_conflict")
    # Absence of a recognized clause is not a proof that arbitrary narrative
    # has no roll. Explicit complete source declarations can establish none.
    if not attack and not saves:
        if (not all(key in declared for key in ("savingThrow", "spellAttack"))
                or any(_ATTACK.search(text) for text, _heading in strings)):
            return unavailable("spell_no_roll_declaration_unavailable")
    return attack, tuple(value for value in _ABILITIES.values() if value in saves)


def _exact_spell(spell: dict[str, Any], entry: Any) -> bool:
    ref = spell.get("systems_ref")
    if type(ref) is not dict or getattr(entry, "entry_type", None) != "spell":
        return False
    for key in ("entry_key", "entry_type", "source_id"):
        if type(ref.get(key)) is not str or not ref[key] or ref[key] != getattr(entry, key, None):
            return False
    return all(type(ref[key]) is str and ref[key] and ref[key] == getattr(entry, key, None)
               for key in ("slug", "title", "library_slug") if key in ref)


def _metric(authority: Any, raw_definition: Any, row: dict[str, Any], family: str,
            owner: str, metric: str) -> int | None:
    value = row.get(metric)
    if type(value) is not int:
        return None
    raw_rows = raw_definition.spellcasting.get(family + "_rows", [])
    if type(raw_rows) is not list:
        return None
    id_key = "class_row_id" if family == "class" else "source_row_id"
    originals = [value for value in raw_rows if type(value) is dict and value.get(id_key) == owner]
    if len(originals) != 1:
        return None
    original = originals[0]
    if family == "source":
        manual = raw_definition.spellcasting.get("manual_authorizations", [])
        if type(manual) is list and any(authority.manual_authorization(record,
                character_slug=raw_definition.character_slug, target_kind="source_row",
                target_id=owner, metric=metric, definition=raw_definition) for record in manual):
            return value
    verified = authority.verified_class_rows if family == "class" else authority.verified_source_rows
    provenance = original.get("spell_metric_provenance")
    ability = str(row.get("spellcasting_ability") or "").casefold()
    key = _ABILITY_KEYS.get(ability)
    if (owner not in verified or type(provenance) is not dict
            or type(provenance.get(metric)) is not dict or provenance[metric].get("kind") != "formula"
            or not authority.formula_metric_verified(family, owner, metric) or not key
            or original.get("spellcasting_ability") != row.get("spellcasting_ability")
            or not authority.field_status("stats.proficiency_bonus").is_effective
            or not authority.field_status(f"stats.ability_scores.{key}.score").is_effective):
        return None
    return value


def present_spell_attack_save(spell: dict[str, Any], *, entry: Any,
        effective_spellcasting: dict[str, Any], authority: Any, raw_definition: Any) -> dict[str, Any]:
    """Use qualified effective rows, preserving each independent casting option."""
    result = {"label": "Unavailable", "status": "UNKNOWN", "reason": "spell_rules_unavailable", "options": []}
    if authority is None or spell.get("authority_status") not in {"VERIFIED", "MANUAL"}:
        return dict(result, reason="spell_authority_unavailable")
    if entry is None:
        return dict(result, reason="spell_source_unavailable")
    if not _exact_spell(spell, entry):
        return dict(result, reason="spell_source_mismatched")
    from .character_item_capabilities import item_casting_presentation
    variant = item_casting_presentation(authority, raw_definition, spell)
    if variant is not None:
        return variant
    unavailable_reasons = []
    rules = _roll_rules(entry, unavailable_reasons=unavailable_reasons)
    if rules is None:
        return dict(result, label="See spell rules",
                    reason=unavailable_reasons[0] if unavailable_reasons else "spell_rules_unavailable")
    attack, saves = rules
    if not attack and not saves:
        return dict(result, label="--", status="NOT_REQUIRED", reason="explicit_source_declarations")
    rows = {}
    ids = set()
    collisions = set()
    for family, id_key in (("class", "class_row_id"), ("source", "source_row_id")):
        family_rows = effective_spellcasting.get(family + "_rows", [])
        raw_rows = raw_definition.spellcasting.get(family + "_rows", [])
        if type(family_rows) is not list or type(raw_rows) is not list or len(family_rows) > 128 or len(raw_rows) > 128:
            return dict(result, reason="casting_owner_ambiguous")
        for row in family_rows:
            if type(row) is not dict or type(row.get(id_key)) is not str or not row[id_key]:
                continue
            identity = row[id_key]
            if identity in ids:
                collisions.add(identity)
            ids.add(identity)
            rows.setdefault((family, identity), []).append(row)
    raw_ids = [row.get(key) for family, key in (("class", "class_row_id"), ("source", "source_row_id"))
               for row in raw_definition.spellcasting.get(family + "_rows", [])
               if type(row) is dict and type(row.get(key)) is str and row[key]]
    collisions.update(value for value in raw_ids if raw_ids.count(value) != 1)
    owners = []
    source_owner = spell.get("spell_source_row_id")
    class_owner = spell.get("class_row_id")
    native = spell.get("native_grant_projection") is True
    native_view = authority.native_grant_view if native else None
    if native and native_view is None:
        return dict(result, reason="casting_options_unavailable")
    if source_owner:
        owners.append(("source", source_owner, None, {"kind": "source_row"}))
    elif not native or (spell.get("grant_class_choice_state") == "active"
                        and spell.get("grant_class_choice_counted") is True):
        if native and spell.get("id") not in authority.confirmed_active_spell_choices:
            return dict(result, reason="class_choice_unavailable")
        owners.append(("class", class_owner, None, {"kind": "class_choice"}))
    paths = spell.get("casting_paths", [])
    if type(paths) is not list or len(paths) > 64:
        return dict(result, reason="casting_options_unavailable")
    if paths and (not native or not authority.native_grant_custody_confirmed):
        return dict(result, reason="casting_options_unavailable")
    seen_paths = set()
    for path in paths:
        if (type(path) is not dict or type(path.get("id")) is not str or not path["id"]
                or len(path["id"]) > 512 or path["id"] in seen_paths or path.get("conditions") != []
                or type(path.get("ability")) is not str or not path["ability"]
                or set(path) != {"id", "owner_id", "class_row_id", "ability", "slot_lane_id", "conditions", "usage_ref"}):
            return dict(result, reason="casting_options_unavailable")
        qualified_paths = [occurrence for occurrence in native_view.for_spell(spell.get("id"))
            if occurrence.get("status") == "VERIFIED" and occurrence.get("casting_path") == path]
        if len(qualified_paths) != 1:
            return dict(result, reason="casting_options_unavailable")
        seen_paths.add(path["id"])
        owners.append(("class", path.get("class_row_id"), path.get("ability"),
                       {"kind": "feature_casting_path", "casting_path": deepcopy(path)}))
    if not owners:
        return dict(result, reason="casting_owner_unavailable")
    options, labels = [], []
    for family, owner, ability, origin in owners:
        matches = rows.get((family, owner), []) if type(owner) is str else []
        if type(owner) is not str or not owner or owner in collisions or len(matches) != 1:
            return dict(result, reason="casting_owner_ambiguous")
        row = matches[0]
        if ability is not None and ability != row.get("spellcasting_ability"):
            return dict(result, reason="casting_ability_changed")
        attack_bonus = _metric(authority, raw_definition, row, family, owner, "spell_attack_bonus") if attack else None
        dc = _metric(authority, raw_definition, row, family, owner, "spell_save_dc") if saves else None
        if attack and attack_bonus is None or saves and dc is None:
            return dict(result, reason="casting_metric_unavailable")
        parts = ([f"{attack_bonus:+d} attack"] if attack else []) + [f"{name} {dc}" for name in saves]
        label = " / ".join(parts)
        option = {"family": family, "owner_id": owner, "label": label, **origin}
        if option not in options:
            options.append(option)
        if label not in labels:
            labels.append(label)
    return {"label": " or ".join(labels), "status": "VERIFIED", "reason": "current_rules_and_owner_metrics", "options": options}


def _presentation_key(spell: dict[str, Any]) -> str | None:
    ref = spell.get("systems_ref")
    if type(ref) is not dict:
        return None
    fields = [spell.get("id"), spell.get("class_row_id", ""), spell.get("spell_source_row_id", ""),
              *(ref.get(key) for key in ("entry_key", "entry_type", "source_id"))]
    if any(type(value) is not str or len(value) > 512 or value != value.strip()
           or any(ord(char) < 32 for char in value) for value in fields):
        return None
    if not fields[0] or not all(fields[-3:]):
        return None
    return json.dumps(fields, ensure_ascii=True, separators=(",", ":"))


def spell_attack_save_presentation(presentations: dict[str, Any], spell: dict[str, Any]) -> dict[str, Any]:
    key = _presentation_key(spell)
    value = presentations.get(key) if key is not None else None
    return value if type(value) is dict else {
        "label": "Unavailable", "status": "UNKNOWN", "reason": "spell_observation_unavailable", "options": []}


def build_spell_metric_presentations(*, spellcasting: dict[str, Any], authority: Any,
        raw_definition: Any, systems_service: Any) -> dict[str, Any]:
    """Detached display facts only; never alter a model or an authority digest."""
    if authority is None:
        return {}
    spells = spellcasting.get("spells", [])
    if type(spells) is not list or len(spells) > 512:
        return {}
    ids = [spell.get("id") for spell in spells if type(spell) is dict]
    getter = getattr(systems_service, "get_entry_for_character_read", None)
    entries, result = {}, {}
    for spell in spells:
        if type(spell) is not dict:
            continue
        key = _presentation_key(spell)
        if key is None:
            continue
        ref = spell["systems_ref"]
        entry_key = ref["entry_key"]
        if entry_key not in entries:
            # The explicit read method does not initialize a missing library.
            entries[entry_key] = getter(raw_definition.campaign_slug, entry_key) if callable(getter) else None
        value = present_spell_attack_save(spell, entry=entries[entry_key], effective_spellcasting=spellcasting,
            authority=authority, raw_definition=raw_definition)
        if ids.count(spell.get("id")) != 1 or key in result:
            value = {"label": "Unavailable", "status": "UNKNOWN", "reason": "spell_identity_ambiguous", "options": []}
        result[key] = deepcopy(value)
    return result
