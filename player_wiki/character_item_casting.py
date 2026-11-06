"""Closed item casting modes and atomic, source-bound item spell operations.

Declarations describe permission and cost, never current availability. The
existing Staff v1 variant remains separate. No item title is an entitlement.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import json
import re

from .character_spell_slots import slot_value_digest

_SEAL = object()
STORAGE_KEY = "item_spell_storage"
_ABILITIES = {"strength": "str", "dexterity": "dex", "constitution": "con",
              "intelligence": "int", "wisdom": "wis", "charisma": "cha"}


def text(value, limit=512):
    return (type(value) is str and 0 < len(value) <= limit and value == value.strip()
            and all(ord(c) >= 32 for c in value))


def integer(value, minimum=0, maximum=9):
    if type(value) is str and re.fullmatch(r"-?[0-9]{1,3}", value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Choose a whole number within the supported range.")
    return value


def normalize_capabilities(value):
    keys = {"schema_version", "effect_id", "counter", "modes", "storage", "focus"}
    if (type(value) is not dict or type(value.get("schema_version")) is not int
            or value["schema_version"] != 2 or set(value) - keys
            or not {"schema_version", "effect_id"} <= set(value)
            or not text(value["effect_id"]) or not set(value) & {"modes", "storage"}):
        raise ValueError("Item spell capabilities need a complete supported v2 contract.")
    if "focus" in value and type(value["focus"]) is not bool:
        raise ValueError("Item focus support must be explicit.")
    counter = value.get("counter")
    if "counter" in value:
        if (type(counter) is not dict or set(counter) != {"maximum", "reset_on", "reset_to", "source_reset"}
                or type(counter.get("maximum")) is not int or not 1 <= counter["maximum"] <= 1000
                or counter.get("reset_on") not in {"long_rest", "short_rest"}
                or counter.get("reset_to") != "max"
                or counter.get("source_reset") not in {"long_rest", "short_rest", "once_per_day", "at_dawn"}
                or (counter["source_reset"] == "short_rest") != (counter["reset_on"] == "short_rest")):
            raise ValueError("Item uses need an exact capacity and recovery rule.")
    modes = value.get("modes", [])
    if type(modes) is not list or "modes" in value and not 1 <= len(modes) <= 8:
        raise ValueError("Declare one to eight distinct item casting modes.")
    ids, free = set(), []
    for mode in modes:
        if (type(mode) is not dict or set(mode) != {"id", "title", "spell_entry_key", "activation",
                "casting_level", "minimum_slot_level", "slot_cost", "counter_cost", "timing", "components", "trigger"}
                or not text(mode.get("id")) or mode["id"] in ids or not text(mode.get("title"))
                or not text(mode.get("spell_entry_key"))
                or re.fullmatch(r"dnd-5e\|(?:spell|custom)\|[^|]+\|[^|]+", mode["spell_entry_key"]) is None
                or mode.get("activation") not in {"attuned", "equipped_attuned"}
                or mode.get("timing") not in {"action", "reaction", "source"}
                or mode.get("components") not in {"source", "none", "item_lens"}
                or mode.get("trigger") not in {"", "first_seen_creature"}
                or type(mode.get("slot_cost")) is not int or mode["slot_cost"] not in {0, 1}
                or type(mode.get("counter_cost")) is not int or mode["counter_cost"] not in {0, 1}
                or mode["slot_cost"] + mode["counter_cost"] != 1):
            raise ValueError("Item casting modes need exact identities, activation, timing and separate costs.")
        ids.add(mode["id"])
        if mode["slot_cost"]:
            if (mode["casting_level"] != "selected_slot" or type(mode["minimum_slot_level"]) is not int
                    or not 1 <= mode["minimum_slot_level"] <= 9):
                raise ValueError("Paid casting needs a qualified slot at or above its declared minimum.")
        else:
            if (counter is None or type(mode["casting_level"]) is not int or not 1 <= mode["casting_level"] <= 9
                    or type(mode["minimum_slot_level"]) is not int or mode["minimum_slot_level"] != 0):
                raise ValueError("Free casting needs an exact spell level and its independent counter.")
            free.append(mode)
    if (counter is not None and len(free) != 1) or len(free) > 1:
        raise ValueError("This contract supports one explicitly owned free-use budget per physical item.")
    if "storage" in value:
        storage = value["storage"]
        if (type(storage) is not dict or set(storage) != {"capacity", "minimum_level", "maximum_level", "activation", "metrics"}
                or any(type(storage.get(k)) is not int for k in ("capacity", "minimum_level", "maximum_level"))
                or not 1 <= storage["minimum_level"] <= storage["maximum_level"] <= storage["capacity"] <= 9
                or storage.get("activation") != "equipped_attuned" or storage.get("metrics") != "original_caster"):
            raise ValueError("Spell storage needs an exact level budget and original-caster metric policy.")
    return deepcopy(value)


def validate_legacy_spell_support(capability, blocks):
    """An optional legacy free-grant projection may not contradict the modes."""
    if not blocks:
        return
    from .item_spell_support import parse_item_spell_support
    parsed = parse_item_spell_support(blocks, strict=True)
    free = [m for m in capability.get("modes", []) if m["counter_cost"]]
    if parsed.diagnostics or len(parsed.records) != len(free):
        raise ValueError("Legacy item spell grants must match the declared free casting mode.")
    for record in parsed.records:
        # A custom entry key contains its campaign, not its source_id or title.
        # Current source binding below resolves selectors to exact entry keys.
        if (record.invalid or record.source_row_kind != "item"
                or record.access_type != "free_cast" or record.access_uses != capability["counter"]["maximum"]
                or record.access_reset_on != capability["counter"]["reset_on"]):
            raise ValueError("Legacy spell access and current item casting modes disagree.")


def validate_mode_sources(capability, blocks, campaign_slug, systems_service):
    """Resolve canonical identities; key shape and a title never prove a spell."""
    from .character_source_authority import _current_systems_entry
    for mode in capability.get("modes", []):
        source = _current_systems_entry(campaign_slug, "systems", mode["spell_entry_key"], systems_service)
        level = mode["minimum_slot_level"] if mode["slot_cost"] else mode["casting_level"]
        if (source is None or source.entry_type != "spell" or type(source.metadata.get("level")) is not int
                or not 1 <= source.metadata["level"] <= level):
            raise ValueError("The current mode spell identity or casting level needs repair.")
    if blocks:
        from .item_spell_support import parse_item_spell_support
        from .character_builder_spells import _resolve_item_spell_selector
        parsed = parse_item_spell_support(blocks, strict=True)
        free = [mode for mode in capability.get("modes", []) if mode["counter_cost"]]
        catalog = {"entries": systems_service.list_enabled_entries_for_campaign(campaign_slug, entry_type="spell")}
        if parsed.diagnostics or len(parsed.records) != len(free):
            raise ValueError("Legacy item spell identity needs repair.")
        for record, mode in zip(parsed.records, free):
            resolved = _resolve_item_spell_selector(record.spell_selector, catalog)
            if resolved is None or resolved.entry_type != "spell" or resolved.entry_key != mode["spell_entry_key"]:
                raise ValueError("Legacy spell access must resolve to the exact current mode spell.")


def context(authority):
    try:
        return json.loads(authority.item_spell_context_json) if authority is not None else {}
    except (AttributeError, TypeError, ValueError):
        return {}


def bind_context(authority, projected, definition, state, systems_service):
    """Bind minimal current source/caster facts, with no display construction."""
    if definition is None or state is None:
        return authority
    entries = [row for row in authority.item_capability_entries(definition)
               if row["capability"].get("schema_version") == 2]
    if not entries:
        return authority
    from .character_source_authority import _current_systems_entry
    from .character_spell_metrics import _metric
    keys = {mode["spell_entry_key"] for row in entries for mode in row["capability"].get("modes", [])}
    storage = any(row["capability"].get("storage") for row in entries)
    catalog = (systems_service.list_enabled_entries_for_campaign(definition.campaign_slug, entry_type="spell")
               if storage else [_current_systems_entry(definition.campaign_slug, "systems", key, systems_service) for key in sorted(keys)])
    spells = {}
    for source in catalog:
        if source is None or source.entry_type != "spell" or type(source.metadata.get("level")) is not int:
            continue
        ref = {key: getattr(source, key) for key in ("entry_key", "entry_type", "library_slug", "source_id", "slug", "title")}
        ref.update(level=source.metadata["level"], body_digest=slot_value_digest(source.body), metadata_digest=slot_value_digest(source.metadata))
        if ref["entry_key"] in spells:
            raise ValueError("Item spell source identity is ambiguous.")
        spells[ref["entry_key"]] = ref
    choices = []
    if storage:
        annotated = authority.annotate_spellcasting(projected.spellcasting, definition=definition)
        for spell in annotated.get("spells", []):
            if type(spell) is not dict or spell.get("authority_status") != "VERIFIED" or spell.get("spell_source_row_id"):
                continue
            if authority.native_grant_view is not None and spell.get("grant_class_choice_counted") is not True:
                # A feature's distinct casting path may use another ability,
                # free budget or ritual-only permission. Do not substitute a
                # class header; external observation remains explicit instead.
                continue
            owner = spell.get("class_row_id")
            rows = [row for row in projected.spellcasting.get("class_rows", []) if row.get("class_row_id") == owner]
            if len(rows) != 1 or not text(owner):
                continue
            row = rows[0]
            if row.get("spell_mode") not in {"wizard", "prepared", "known"}:
                continue
            ref = spells.get((spell.get("systems_ref") or {}).get("entry_key"))
            if ref is None:
                continue
            from .character_mechanics_projection import project_spell_action_state
            action = project_spell_action_state(spell=spell, row_payload=dict(row, row_kind="class"),
                spell_level=ref["level"], mark=str(spell.get("mark") or ""))
            if row.get("spell_mode") in {"wizard", "prepared"} and not action["is_prepared"]:
                continue
            ability = _ABILITIES.get(str(row.get("spellcasting_ability") or "").casefold())
            score = authority.field_status(f"stats.ability_scores.{ability}.score")
            dc = _metric(authority, definition, row, "class", owner, "spell_save_dc")
            attack = _metric(authority, definition, row, "class", owner, "spell_attack_bonus")
            if ref is None or not 1 <= ref["level"] <= 9 or ability is None or not score.is_effective or type(score.effective) is not int or dc is None or attack is None:
                continue
            choice = {"id": str(spell.get("id") or "") + ":" + owner, "spell_ref": ref,
                "label": f"{ref['title']} ({row.get('class_name') or 'Spellcasting'})",
                "class_row_id": owner, "slot_lane_id": row.get("slot_lane_id", ""),
                "ability": ability, "ability_modifier": (score.effective - 10) // 2,
                "save_dc": dc, "attack_bonus": attack}
            if text(choice["id"]):
                choices.append(choice)
        ids = [choice["id"] for choice in choices]
        choices = [choice for choice in choices if ids.count(choice["id"]) == 1]
    from .character_item_storage import load_checkpoints
    checkpoints = load_checkpoints(definition) if storage else {}
    facts = {"spells": spells, "choices": choices, "storage_checkpoints": checkpoints}
    return replace(authority, item_spell_context_json=json.dumps(facts, sort_keys=True, separators=(",", ":")))


def item_entry(authority, definition, physical_id):
    matches = [row for row in authority.item_capability_entries(definition) if row["physical_id"] == physical_id
               and row["capability"].get("schema_version") == 2] if authority is not None else []
    if len(matches) != 1:
        raise ValueError("The exact current physical item/source needs repair.")
    return matches[0]


def slot_options(authority, definition, state, minimum=1):
    from .character_spell_slots import spell_slot_contributions, spell_slot_options_from_contributions
    return [row for row in spell_slot_options_from_contributions(spell_slot_contributions(definition.spellcasting, state, authority))
            if row["level"] >= minimum and type(row.get("available")) is int and row["available"] > 0]


def modes_for_item(authority, definition, state, entry):
    from .character_item_capabilities import active_clause
    result = []
    facts = context(authority)
    for mode in entry["capability"].get("modes", []):
        spell = facts.get("spells", {}).get(mode["spell_entry_key"])
        current = authority.resource_status("item_charge", entry["physical_id"])
        options = slot_options(authority, definition, state, mode["minimum_slot_level"]) if mode["slot_cost"] else []
        reason = ("Item is not currently active." if not active_clause(entry, mode["activation"]) else
                  "Current spell source needs repair." if spell is None else
                  "Declared casting level is below the spell's level." if
                  (mode["minimum_slot_level"] if mode["slot_cost"] else mode["casting_level"]) < spell["level"] else
                  "Free uses are unrecorded or exhausted." if mode["counter_cost"] and
                  (not current.is_effective or type(current.effective) is not dict or current.effective.get("current", 0) < 1) else
                  "No qualified available spell slot." if mode["slot_cost"] and not options else "")
        result.append({**deepcopy(mode), "spell": deepcopy(spell), "enabled": not reason,
            "disabled_reason": reason, "slot_options": options})
    return result


def apply_operation(state, definition, authority, params):
    from .character_item_capabilities import active_clause
    if authority is None or authority.state_digest != slot_value_digest(state):
        raise ValueError("Item spell state changed. Refresh before acting.")
    entry = item_entry(authority, definition, params.get("item_id"))
    if params.get("kind") != "cast":
        from .character_item_storage import apply_storage
        return apply_storage(state, definition, authority, entry, params)
    matches = [mode for mode in modes_for_item(authority, definition, state, entry) if mode["id"] == params.get("mode_id")]
    if len(matches) != 1 or not matches[0]["enabled"]:
        raise ValueError(matches[0]["disabled_reason"] if len(matches) == 1 else "Choose a current casting mode.")
    mode = matches[0]
    if mode["trigger"] and params.get("confirm_trigger") is not True:
        raise ValueError("Confirm the source trigger is satisfied at the table.")
    result = deepcopy(state)
    if mode["slot_cost"]:
        from .character_spell_slots import spend_slot_contribution
        level = integer(params.get("slot_level"), mode["minimum_slot_level"])
        lane = params.get("slot_lane_id", "")
        if not any(row["slot_lane_id"] == lane and row["level"] == level for row in mode["slot_options"]):
            raise ValueError("Choose a qualified available slot for this mode.")
        result = spend_slot_contribution(result, definition.spellcasting, authority, lane, level)
    else:
        rows = [row for row in result["inventory"] if row.get("id") == entry["physical_id"]]
        if len(rows) != 1:
            raise ValueError("Physical item identity is ambiguous.")
        rows[0]["charges_current"] -= 1
    return result


@dataclass(frozen=True, slots=True)
class ItemSpellIntent:
    before_digest: str
    after_digest: str
    params_json: str
    seal: object = field(repr=False)


def prepare_operation(state, definition, authority, params):
    result = apply_operation(state, definition, authority, params)
    return result, ItemSpellIntent(slot_value_digest(state), slot_value_digest(result),
        json.dumps(params, sort_keys=True, separators=(",", ":")), _SEAL)


def require_storage_preserved(prior, result):
    # Presence is meaningful: absent is not an authenticated empty baseline.
    if (STORAGE_KEY in (prior or {})) != (STORAGE_KEY in result) or (prior or {}).get(STORAGE_KEY) != result.get(STORAGE_KEY):
        raise ValueError("Stored spells must be preserved outside their guarded item action.")


def validate_transition(prior, result, definition, authority, intent):
    if intent is None:
        require_storage_preserved(prior, result)
        return
    if (type(intent) is not ItemSpellIntent or intent.seal is not _SEAL
            or intent.before_digest != slot_value_digest(prior) or intent.after_digest != slot_value_digest(result)
            or apply_operation(prior, definition, authority, json.loads(intent.params_json)) != result):
        raise ValueError("The item spell action must remain one exact current atomic transition.")


OPERATIONS = frozenset({"item_cast", "storage_initialize", "storage_store", "storage_external", "storage_release"})


def request_values(payload, *, html=False):
    """One HTML/JSON input adapter; permission decisions remain server-owned."""
    allowed = {"mode_id", "confirm_trigger", "confirm_observation", "slot_level", "slot_lane_id", "slot_selection",
               "choice_id", "stored_id", "spell_entry_key", "caster", "ability", "ability_modifier", "save_dc", "attack_bonus"}
    values = {key: payload.get(key) for key in allowed if key in payload}
    for key, value in values.items():
        if key not in {"confirm_trigger", "confirm_observation"} and (
                type(value) not in {str, int} or type(value) is str and (
                    len(value) > 512 or any(ord(char) < 32 for char in value))):
            raise ValueError("Item spell inputs need bounded text or whole numbers.")
    for key in ("confirm_trigger", "confirm_observation"):
        values[key] = values.get(key) == "yes" if html else values.get(key) is True
    if values.get("slot_selection"):
        from .character_spell_slots import parse_spell_slot_selection
        if "slot_lane_id" in values or "slot_level" in values:
            raise ValueError("Choose one unambiguous spell-slot selection.")
        values["slot_lane_id"], values["slot_level"] = parse_spell_slot_selection(values.pop("slot_selection"))
    return values
