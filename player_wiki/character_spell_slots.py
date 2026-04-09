from __future__ import annotations

from typing import Any

DEFAULT_SPELL_SLOT_LANE_ID = ""


def normalize_spell_slot_lane_id(value: Any) -> str:
    return str(value or "").strip()


def normalize_spell_slot_progression(raw_progression: Any) -> list[dict[str, int]]:
    progression: list[dict[str, int]] = []
    for raw_slot in list(raw_progression or []):
        slot = dict(raw_slot or {})
        level = int(slot.get("level") or 0)
        max_slots = int(slot.get("max_slots") or 0)
        if level <= 0:
            continue
        progression.append(
            {
                "level": level,
                "max_slots": max(0, max_slots),
            }
        )
    return progression


def spell_slot_lanes_from_spellcasting(spellcasting: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = dict(spellcasting or {})
    raw_lanes = [dict(lane or {}) for lane in list(payload.get("slot_lanes") or []) if isinstance(lane, dict)]
    if raw_lanes:
        lanes: list[dict[str, Any]] = []
        for index, raw_lane in enumerate(raw_lanes, start=1):
            lane_id = normalize_spell_slot_lane_id(
                raw_lane.get("id") or raw_lane.get("slot_lane_id") or f"slot-lane-{index}"
            )
            lanes.append(
                {
                    "id": lane_id,
                    "title": str(raw_lane.get("title") or "").strip() or "Spell slots",
                    "shared": bool(raw_lane.get("shared")),
                    "row_ids": [
                        str(row_id).strip()
                        for row_id in list(raw_lane.get("row_ids") or [])
                        if str(row_id).strip()
                    ],
                    "slot_progression": normalize_spell_slot_progression(raw_lane.get("slot_progression")),
                }
            )
        return lanes

    legacy_progression = normalize_spell_slot_progression(payload.get("slot_progression"))
    if not legacy_progression:
        return []
    return [
        {
            "id": DEFAULT_SPELL_SLOT_LANE_ID,
            "title": "Spell slots",
            "shared": False,
            "row_ids": [],
            "slot_progression": legacy_progression,
        }
    ]


def spell_slot_state_entries_from_spellcasting(spellcasting: dict[str, Any] | None) -> list[dict[str, int | str]]:
    entries: list[dict[str, int | str]] = []
    for lane in spell_slot_lanes_from_spellcasting(spellcasting):
        lane_id = normalize_spell_slot_lane_id(lane.get("id"))
        for slot in list(lane.get("slot_progression") or []):
            entry: dict[str, int | str] = {
                "level": int(slot.get("level") or 0),
                "max": int(slot.get("max_slots") or 0),
                "used": 0,
            }
            if lane_id:
                entry["slot_lane_id"] = lane_id
            entries.append(entry)
    return entries


def spell_slot_lane_title_map(spellcasting: dict[str, Any] | None) -> dict[str, str]:
    return {
        normalize_spell_slot_lane_id(lane.get("id")): str(lane.get("title") or "").strip() or "Spell slots"
        for lane in spell_slot_lanes_from_spellcasting(spellcasting)
    }
