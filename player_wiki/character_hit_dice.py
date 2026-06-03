from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .system_policy import is_xianxia_system


STANDARD_DND_CLASS_HIT_DICE: dict[str, int] = {
    "artificer": 8,
    "barbarian": 12,
    "bard": 8,
    "cleric": 8,
    "druid": 8,
    "fighter": 10,
    "monk": 8,
    "paladin": 10,
    "ranger": 10,
    "rogue": 8,
    "sorcerer": 6,
    "warlock": 8,
    "wizard": 6,
}

VALID_HIT_DIE_FACES = {4, 6, 8, 10, 12}
HIT_DICE_STATE_KEY = "hit_dice"


def derive_hit_dice_max_pools(definition: Any) -> list[dict[str, int]]:
    if is_xianxia_system(getattr(definition, "system", None)):
        return []

    profile = dict(getattr(definition, "profile", {}) or {})
    max_by_faces: dict[int, int] = {}
    for class_row in _profile_class_rows(profile):
        level = _coerce_nonnegative_int(class_row.get("level"))
        if level <= 0:
            continue
        faces = _hit_die_faces_for_class_row(class_row)
        if faces <= 0:
            continue
        max_by_faces[faces] = max_by_faces.get(faces, 0) + level

    return [
        {"faces": faces, "max": max_count}
        for faces, max_count in sorted(max_by_faces.items())
        if max_count > 0
    ]


def normalize_hit_dice_state(definition: Any, raw_state: Any) -> dict[str, Any]:
    max_pools = derive_hit_dice_max_pools(definition)
    if not max_pools:
        return {"pools": []}

    existing_by_faces = _existing_current_by_faces(raw_state)
    normalized_pools: list[dict[str, int]] = []
    for pool in max_pools:
        faces = int(pool["faces"])
        max_count = max(0, int(pool["max"]))
        current = existing_by_faces.get(faces)
        if current is None:
            current = max_count
        normalized_pools.append(
            {
                "faces": faces,
                "current": max(0, min(int(current), max_count)),
                "max": max_count,
            }
        )

    return {"pools": normalized_pools}


def normalize_hit_dice_state_payload(definition: Any, state: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(state or {})
    normalized = normalize_hit_dice_state(definition, payload.get(HIT_DICE_STATE_KEY))
    if normalized["pools"]:
        payload[HIT_DICE_STATE_KEY] = normalized
    else:
        payload.pop(HIT_DICE_STATE_KEY, None)
    return payload


def hit_dice_total_level(definition: Any) -> int:
    return sum(int(pool["max"]) for pool in derive_hit_dice_max_pools(definition))


def hit_dice_long_rest_regain_amount(definition: Any) -> int:
    total_level = hit_dice_total_level(definition)
    if total_level <= 0:
        return 0
    return max(1, total_level // 2)


def apply_long_rest_hit_dice_recovery(definition: Any, state: dict[str, Any]) -> dict[str, Any]:
    payload = normalize_hit_dice_state_payload(definition, state)
    hit_dice = dict(payload.get(HIT_DICE_STATE_KEY) or {})
    pools = [dict(pool) for pool in list(hit_dice.get("pools") or [])]
    remaining = hit_dice_long_rest_regain_amount(definition)
    if remaining <= 0:
        return payload

    for pool in sorted(pools, key=lambda item: int(item.get("faces") or 0), reverse=True):
        if remaining <= 0:
            break
        current = max(0, int(pool.get("current") or 0))
        maximum = max(0, int(pool.get("max") or 0))
        missing = max(0, maximum - current)
        if missing <= 0:
            continue
        recovered = min(missing, remaining)
        pool["current"] = current + recovered
        remaining -= recovered

    hit_dice["pools"] = sorted(pools, key=lambda item: int(item.get("faces") or 0))
    payload[HIT_DICE_STATE_KEY] = hit_dice
    return payload


def set_hit_dice_current_values(
    definition: Any,
    state: dict[str, Any],
    values_by_faces: dict[int, Any],
) -> dict[str, Any]:
    payload = normalize_hit_dice_state_payload(definition, state)
    hit_dice = dict(payload.get(HIT_DICE_STATE_KEY) or {})
    pools: list[dict[str, int]] = []
    for pool in list(hit_dice.get("pools") or []):
        faces = int(pool.get("faces") or 0)
        maximum = max(0, int(pool.get("max") or 0))
        if faces in values_by_faces and str(values_by_faces[faces]).strip() != "":
            current = int(values_by_faces[faces])
        else:
            current = int(pool.get("current") or 0)
        pools.append(
            {
                "faces": faces,
                "current": max(0, min(current, maximum)),
                "max": maximum,
            }
        )
    if pools:
        payload[HIT_DICE_STATE_KEY] = {"pools": pools}
    return payload


def hit_dice_summary_from_state(definition: Any, state: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_hit_dice_state(definition, (state or {}).get(HIT_DICE_STATE_KEY))
    pools = [
        {
            "faces": int(pool.get("faces") or 0),
            "label": f"d{int(pool.get('faces') or 0)}",
            "current": int(pool.get("current") or 0),
            "max": int(pool.get("max") or 0),
            "input_name": f"hit_dice_d{int(pool.get('faces') or 0)}",
        }
        for pool in list(normalized.get("pools") or [])
        if int(pool.get("faces") or 0) > 0
    ]
    value = " | ".join(
        f"{pool['label']} {pool['current']}/{pool['max']}" for pool in pools
    )
    full_value = " + ".join(
        f"{pool['max']}d{pool['faces']}" for pool in pools if int(pool["max"]) > 0
    )
    return {
        "pools": pools,
        "value": value or "--",
        "full_value": full_value or "--",
        "regain_on_long_rest": hit_dice_long_rest_regain_amount(definition),
    }


def hit_dice_rest_changes(
    definition: Any,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> list[dict[str, str]]:
    before = hit_dice_summary_from_state(definition, before_state)
    after = hit_dice_summary_from_state(definition, after_state)
    if before["value"] == after["value"]:
        return []
    return [
        {
            "label": "Hit Dice",
            "from_value": str(before["value"]),
            "to_value": str(after["value"]),
        }
    ]


def _profile_class_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row or {}) for row in list(profile.get("classes") or []) if isinstance(row, dict)]
    if rows:
        return rows

    class_level_text = str(profile.get("class_level_text") or "").strip()
    match = re.fullmatch(r"(?P<class_name>[A-Za-z][A-Za-z '\-]*)\s+(?P<level>\d+)", class_level_text)
    if not match:
        return []
    return [
        {
            "class_name": match.group("class_name").strip(),
            "level": int(match.group("level")),
        }
    ]


def _hit_die_faces_for_class_row(class_row: dict[str, Any]) -> int:
    for key in ("hit_die_faces", "hit_die_face", "hit_die"):
        faces = _extract_faces(class_row.get(key))
        if faces:
            return faces

    metadata = class_row.get("metadata")
    if isinstance(metadata, dict):
        faces = _extract_faces(metadata.get("hit_die") or metadata.get("hitDie"))
        if faces:
            return faces

    systems_ref = class_row.get("systems_ref")
    if isinstance(systems_ref, dict):
        faces = _extract_faces(systems_ref.get("hit_die") or systems_ref.get("hitDie"))
        if faces:
            return faces
        ref_metadata = systems_ref.get("metadata")
        if isinstance(ref_metadata, dict):
            faces = _extract_faces(ref_metadata.get("hit_die") or ref_metadata.get("hitDie"))
            if faces:
                return faces

    class_name = _normalize_class_name(class_row.get("class_name") or class_row.get("name"))
    return STANDARD_DND_CLASS_HIT_DICE.get(class_name, 8 if class_name else 0)


def _extract_faces(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, dict):
        return _extract_faces(value.get("faces") or value.get("face") or value.get("die"))
    text = str(value).strip().lower()
    if text.startswith("d"):
        text = text[1:]
    try:
        faces = int(text)
    except ValueError:
        return 0
    return faces if faces in VALID_HIT_DIE_FACES else 0


def _existing_current_by_faces(raw_state: Any) -> dict[int, int]:
    if not isinstance(raw_state, dict):
        return {}

    existing: dict[int, int] = {}
    for pool in list(raw_state.get("pools") or []):
        if not isinstance(pool, dict):
            continue
        faces = _extract_faces(pool.get("faces") or pool.get("die") or pool.get("label"))
        if not faces:
            continue
        existing[faces] = _coerce_nonnegative_int(pool.get("current"))

    for key, value in raw_state.items():
        faces = _extract_faces(key)
        if faces:
            existing[faces] = _coerce_nonnegative_int(value)

    return existing


def _coerce_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_class_name(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").casefold())
