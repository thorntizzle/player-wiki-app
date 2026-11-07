"""Explicit inputs for recording a completed advancement, never a die roll.

The transports grant manager access. The compiler still validates the current
owned class spine and the deliberately bounded retained-whole HP recipe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from copy import deepcopy
from hashlib import sha256
from typing import Mapping, Any

from .character_hp_recipe import HitPointRecipeError

RECORD_TYPE = "advancement_record_type"
RECORDED_AT = "advancement_recorded_at"
EVIDENCE = "advancement_evidence"
SLOT_PREFIX = "advancement_slot_used__"


def manager_allowed(campaign_slug: str) -> bool:
    """Use current authenticated authority; View As cannot supply it."""
    from .auth import (can_manage_campaign_session, get_authenticated_user,
                       get_current_user, get_view_as_user, get_auth_store)
    actor, current = get_authenticated_user(), get_current_user()
    if (actor is None or current is None or actor.id != current.id or get_view_as_user() is not None
            or not can_manage_campaign_session(campaign_slug)):
        return False
    store = get_auth_store()
    fresh = store.get_user_by_id(actor.id)
    membership = store.get_membership(actor.id, campaign_slug)
    return bool(fresh is not None and fresh.is_active
                and (fresh.is_admin or membership is not None and membership.role == "dm"))


def require_single_fields(values: Mapping[str, Any]) -> None:
    for key in (RECORD_TYPE, RECORDED_AT, EVIDENCE):
        if hasattr(values, "getlist") and len(values.getlist(key)) > 1:
            raise HitPointRecipeError("Recorded advancement fields must occur only once.")
        if key in values and type(values[key]) is not str:
            raise HitPointRecipeError("Recorded advancement fields must be single text values.")
    if is_recorded(values):
        if hasattr(values, "getlist") and len(values.getlist("hp_gain")) > 1:
            raise HitPointRecipeError("The recorded HP gain must occur only once.")
        if "hp_gain" in values and type(values["hp_gain"]) not in (str, int):
            raise HitPointRecipeError("The recorded HP gain must be a whole number.")
        for key in values:
            if type(key) is str and key.startswith(SLOT_PREFIX):
                if ((hasattr(values, "getlist") and len(values.getlist(key)) != 1)
                        or type(values[key]) not in (str, int)):
                    raise HitPointRecipeError("Recorded slot use needs one whole number per new pool.")


def slot_fields(lanes, prior_state, values):
    """New class-slot pools need an observed spent count, never a default rest."""
    old = prior_state.get("spell_slots", [])
    if type(old) is not list or any(type(row) is not dict for row in old):
        raise HitPointRecipeError("Resolve the existing spell-slot observations before recording advancement.")
    result, seen = [], set()
    for lane in lanes:
        lane_id = lane.get("id")
        if type(lane_id) is not str or not lane_id:
            raise HitPointRecipeError("Recorded slot ownership is unavailable.")
        for slot in lane.get("slot_progression") or []:
            level, maximum = slot.get("level"), slot.get("max_slots")
            if type(level) is not int or not 1 <= level <= 9 or type(maximum) is not int or not 0 <= maximum <= 100:
                raise HitPointRecipeError("Recorded slot capacity is unavailable.")
            key = lane_id, level
            if key in seen:
                raise HitPointRecipeError("Recorded slot ownership is ambiguous.")
            seen.add(key)
            matches = [row for row in old if isinstance(row, dict)
                       and row.get("slot_lane_id") == lane_id and row.get("level") == level]
            if len(matches) > 1 or any(isinstance(row, dict) and row.get("level") == level
                                      and not row.get("slot_lane_id") for row in old):
                raise HitPointRecipeError("Resolve the existing spell-slot owner before recording advancement.")
            if matches:
                continue
            name = SLOT_PREFIX + sha256(lane_id.encode("utf-8")).hexdigest()[:24] + "__" + str(level)
            result.append({"name": name, "slot_lane_id": lane_id, "level": level, "max": maximum,
                "label": f"{lane.get('title') or 'Spell slots'}, level {level}: already used",
                "value": values.get(name, "")})
    return result


def slot_observations(definition, prior_state, values):
    from .character_spell_slots import spell_slot_lanes_from_spellcasting
    fields = slot_fields(spell_slot_lanes_from_spellcasting(definition.spellcasting), prior_state, values)
    if any(type(key) is str and key.startswith(SLOT_PREFIX) and key not in {field["name"] for field in fields}
           for key in values):
        raise HitPointRecipeError("The new spell-slot owner changed since review.")
    result = []
    for field in fields:
        value = field["value"]
        if type(value) not in (str, int) or value == "":
            raise HitPointRecipeError("Enter the recorded used count for every new spell-slot pool; zero must be explicit.")
        try:
            used = int(value)
        except ValueError as exc:
            raise HitPointRecipeError("Recorded slot use must be a whole number.") from exc
        if not 0 <= used <= field["max"]:
            raise HitPointRecipeError("Recorded slot use exceeds the current source capacity.")
        result.append((field["slot_lane_id"], field["level"], field["max"], used))
    return tuple(result)


def apply_slot_observations(prior_state, merged_state, observations):
    result = deepcopy(merged_state)
    if any(type(row) is not dict for row in [*(prior_state.get("spell_slots") or []), *(result.get("spell_slots") or [])]):
        raise HitPointRecipeError("The spell-slot observations changed shape before saving.")
    for lane_id, level, maximum, used in observations:
        old = [row for row in prior_state.get("spell_slots") or []
               if row.get("slot_lane_id") == lane_id and row.get("level") == level]
        rows = [row for row in result.get("spell_slots") or []
                if row.get("slot_lane_id") == lane_id and row.get("level") == level]
        if old or len(rows) != 1 or rows[0].get("max") != maximum:
            raise HitPointRecipeError("The recorded new slot pool changed before saving.")
        rows[0]["used"] = used
    for old in prior_state.get("spell_slots") or []:
        rows = [row for row in result.get("spell_slots") or []
                if row.get("slot_lane_id") == old.get("slot_lane_id") and row.get("level") == old.get("level")]
        if len(rows) != 1 or {k: v for k, v in rows[0].items() if k != "max"} != {k: v for k, v in old.items() if k != "max"}:
            raise HitPointRecipeError("Recording advancement cannot change existing slot spending.")
    return result


def is_recorded(values: Mapping[str, Any]) -> bool:
    kind = values.get(RECORD_TYPE, "new")
    if type(kind) is not str or kind not in {"new", "completed"}:
        raise HitPointRecipeError("Choose a new advancement or record a completed advancement.")
    return kind == "completed"


@dataclass(frozen=True, slots=True)
class RecordedAdvancement:
    occurred_at: str
    evidence: str

    def history_note(self) -> dict[str, Any]:
        return {"schema_version": 1, "kind": "completed_whole_hp", "evidence": self.evidence}


def parse_recorded(values: Mapping[str, Any], *, allowed: bool) -> RecordedAdvancement | None:
    if not is_recorded(values):
        return None
    if not allowed:
        raise HitPointRecipeError("Only a current campaign manager can record a completed advancement.")
    raw = values.get(RECORDED_AT)
    evidence = values.get(EVIDENCE)
    if type(raw) is not str or not 1 <= len(raw) <= 64 or raw != raw.strip():
        raise HitPointRecipeError("Enter the original completed advancement time, including its UTC offset.")
    try:
        occurred = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HitPointRecipeError("Enter a valid original advancement time, including its UTC offset.") from exc
    if occurred.tzinfo is None or occurred.utcoffset() is None or occurred > datetime.now(timezone.utc):
        raise HitPointRecipeError("A completed advancement needs a past time with its UTC offset.")
    if (type(evidence) is not str or evidence != evidence.strip() or not 1 <= len(evidence) <= 512
            or any(ord(char) < 32 or ord(char) == 127 for char in evidence)):
        raise HitPointRecipeError("Describe the recorded advancement evidence in one line, up to 512 characters.")
    return RecordedAdvancement(raw, evidence)


def require_spine(definition, *, selected_class, selected_subclass, class_row_id, mode):
    from .character_profile import profile_class_rows
    rows = profile_class_rows(definition.profile)
    if (definition.system != "DND-5E" or mode != "advance_existing" or len(rows) != 1
            or rows[0].get("row_id") != class_row_id
            or not isinstance(definition.source.get("native_reconstruction_choices"), dict)):
        raise HitPointRecipeError("Recorded advancement currently supports one existing reconstructed class row.")
    row = rows[0]
    ref = row.get("systems_ref") or {}
    subclass = row.get("subclass_ref") or {}
    if (ref.get("entry_key") != getattr(selected_class, "entry_key", None)
            or ref.get("source_id") != getattr(selected_class, "source_id", None)
            or bool(subclass) != (selected_subclass is not None)
            or subclass and (subclass.get("entry_key") != getattr(selected_subclass, "entry_key", None)
                             or subclass.get("source_id") != getattr(selected_subclass, "source_id", None))):
        raise HitPointRecipeError("Recording advancement must preserve its existing class and subclass sources.")


def audit_note(definition) -> dict[str, Any] | None:
    progression = definition.source.get("native_progression") or {}
    history = progression.get("history") or []
    event = history[-1] if history else None
    if not isinstance(event, dict) or "recorded_advancement" not in event:
        return None
    return {"schema_version": 1, "occurred_at": event["at"],
            "whole_hp_gain": event["max_hp_delta"], "class_row_id": event["class_row_id"],
            "from_level": event["from_level"], "to_level": event["to_level"],
            "evidence": event["recorded_advancement"]["evidence"]}
