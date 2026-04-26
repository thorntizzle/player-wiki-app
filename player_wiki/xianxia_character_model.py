from __future__ import annotations

from copy import deepcopy
from typing import Any

from .system_policy import is_xianxia_system

XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION = 1

XIANXIA_ATTRIBUTE_KEYS = ("str", "dex", "con", "int", "wis", "cha")
XIANXIA_EFFORT_KEYS = ("basic", "weapon", "guns_explosive", "magic", "ultimate")
XIANXIA_ENERGY_KEYS = ("jing", "qi", "shen")

XIANXIA_DEFINITION_FIELD_KEYS = (
    "schema_version",
    "realm",
    "actions_per_turn",
    "honor",
    "reputation",
    "attributes",
    "efforts",
    "energies",
    "yin_yang",
    "dao",
    "insight",
    "durability",
    "skills",
    "equipment",
    "martial_arts",
    "generic_techniques",
    "variants",
    "dao_immolating_techniques",
    "approval_requests",
    "companions",
    "advancement_history",
)

_REALM_LABELS = {
    "mortal": "Mortal",
    "immortal": "Immortal",
    "divine": "Divine",
}

_REALM_ACTION_DEFAULTS = {
    "Mortal": 2,
    "Immortal": 3,
    "Divine": 4,
}

_HONOR_LABELS = {
    "venerable": "Venerable",
    "majestic": "Majestic",
    "honorable": "Honorable",
    "disgraced": "Disgraced",
    "demonic": "Demonic",
}


def normalize_xianxia_definition_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a definition payload with a stable Xianxia-only definition block."""

    normalized_payload = deepcopy(payload)
    if not is_xianxia_system(normalized_payload.get("system")):
        normalized_payload.pop("xianxia", None)
        return normalized_payload

    raw_xianxia = dict(normalized_payload.get("xianxia") or {})
    raw_profile = dict(normalized_payload.get("profile") or {})
    raw_stats = dict(normalized_payload.get("stats") or {})

    realm = _normalize_choice(
        _first_present(raw_xianxia, normalized_payload, raw_profile, key="realm"),
        choices=_REALM_LABELS,
        default="Mortal",
    )
    actions_per_turn = _normalize_int(
        _first_present(raw_xianxia, normalized_payload, raw_profile, key="actions_per_turn")
        if _has_any(raw_xianxia, normalized_payload, raw_profile, key="actions_per_turn")
        else _first_present(raw_xianxia, normalized_payload, raw_profile, key="action_count"),
        default=_REALM_ACTION_DEFAULTS.get(realm, 2),
    )
    if actions_per_turn < 0:
        actions_per_turn = _REALM_ACTION_DEFAULTS.get(realm, 2)

    raw_durability = _first_mapping(raw_xianxia, raw_stats, key="durability")
    raw_equipment = _first_mapping(raw_xianxia, normalized_payload, key="equipment")
    raw_armor = dict(raw_equipment.get("armor") or {}) if isinstance(raw_equipment.get("armor"), dict) else {}

    raw_manual_armor_bonus = _first_present(
        raw_durability,
        raw_xianxia,
        normalized_payload,
        raw_armor,
        key="manual_armor_bonus",
    )
    if raw_manual_armor_bonus is None:
        raw_manual_armor_bonus = _first_present(
            raw_durability,
            raw_xianxia,
            normalized_payload,
            raw_armor,
            key="armor_bonus",
        )
    if raw_manual_armor_bonus is None:
        raw_manual_armor_bonus = _first_present(
            raw_durability,
            raw_xianxia,
            normalized_payload,
            raw_armor,
            key="defense_bonus",
        )
    manual_armor_bonus = _normalize_int(raw_manual_armor_bonus, default=0)

    xianxia_definition = {
        "schema_version": XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
        "realm": realm,
        "actions_per_turn": actions_per_turn,
        "honor": _normalize_choice(
            _first_present(raw_xianxia, normalized_payload, raw_profile, key="honor"),
            choices=_HONOR_LABELS,
            default="Honorable",
        ),
        "reputation": _normalize_text(
            _first_present(raw_xianxia, normalized_payload, raw_profile, key="reputation"),
            default="Unknown",
        ),
        "attributes": _normalize_int_key_map(
            _first_mapping(raw_xianxia, normalized_payload, raw_stats, key="attributes"),
            XIANXIA_ATTRIBUTE_KEYS,
        ),
        "efforts": _normalize_int_key_map(
            _first_mapping(raw_xianxia, normalized_payload, raw_stats, key="efforts"),
            XIANXIA_EFFORT_KEYS,
        ),
        "energies": _normalize_energy_maxima(
            _first_mapping(raw_xianxia, normalized_payload, raw_stats, key="energies"),
            _first_mapping(raw_xianxia, normalized_payload, raw_stats, key="energy_maxima"),
        ),
        "yin_yang": _normalize_yin_yang(raw_xianxia, normalized_payload, raw_stats),
        "dao": {
            "max": _normalize_int(
                _first_present(raw_xianxia, normalized_payload, key="dao_max"),
                default=3,
            )
        },
        "insight": _normalize_insight(raw_xianxia, normalized_payload),
        "durability": {
            "hp_max": _normalize_int(
                _first_present(raw_durability, raw_xianxia, normalized_payload, key="hp_max"),
                default=10,
            ),
            "stance_max": _normalize_int(
                _first_present(raw_durability, raw_xianxia, normalized_payload, key="stance_max"),
                default=10,
            ),
            "manual_armor_bonus": manual_armor_bonus,
            "defense": _normalize_int(
                _first_present(raw_durability, raw_xianxia, normalized_payload, key="defense"),
                default=10,
            ),
        },
        "skills": {
            "trained": _normalize_text_list(
                _first_present(raw_xianxia, normalized_payload, key="trained_skills")
                if _has_any(raw_xianxia, normalized_payload, key="trained_skills")
                else dict(raw_xianxia.get("skills") or {}).get("trained")
            )
        },
        "equipment": {
            "necessary_weapons": _normalize_named_records(
                _first_present(raw_xianxia, normalized_payload, raw_equipment, key="necessary_weapons")
            ),
            "necessary_tools": _normalize_named_records(
                _first_present(raw_xianxia, normalized_payload, raw_equipment, key="necessary_tools")
            ),
        },
        "martial_arts": _normalize_record_list(
            _first_present(raw_xianxia, normalized_payload, key="martial_arts")
        ),
        "generic_techniques": _normalize_record_list(
            _first_present(raw_xianxia, normalized_payload, key="generic_techniques")
        ),
        "variants": _normalize_record_list(_first_present(raw_xianxia, normalized_payload, key="variants")),
        "dao_immolating_techniques": _normalize_dao_immolating_records(raw_xianxia, normalized_payload),
        "approval_requests": _normalize_record_list(
            _first_present(raw_xianxia, normalized_payload, key="approval_requests")
        ),
        "companions": _normalize_record_list(_first_present(raw_xianxia, normalized_payload, key="companions")),
        "advancement_history": _normalize_record_list(
            _first_present(raw_xianxia, normalized_payload, key="advancement_history")
        ),
    }

    normalized_payload["xianxia"] = xianxia_definition
    return normalized_payload


def _has_any(*mappings: dict[str, Any], key: str) -> bool:
    return any(isinstance(mapping, dict) and key in mapping for mapping in mappings)


def _first_present(*mappings: dict[str, Any], key: str) -> Any:
    for mapping in mappings:
        if isinstance(mapping, dict) and key in mapping:
            return mapping.get(key)
    return None


def _first_mapping(*mappings: dict[str, Any], key: str) -> dict[str, Any]:
    value = _first_present(*mappings, key=key)
    return dict(value or {}) if isinstance(value, dict) else {}


def _normalize_text(value: Any, *, default: str = "") -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    return cleaned or default


def _normalize_choice(value: Any, *, choices: dict[str, str], default: str) -> str:
    cleaned = _normalize_text(value)
    if not cleaned:
        return default
    return choices.get(cleaned.casefold(), cleaned)


def _normalize_int(value: Any, *, default: int = 0) -> int:
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_int_key_map(raw_values: dict[str, Any], keys: tuple[str, ...]) -> dict[str, int]:
    return {key: _normalize_int(raw_values.get(key), default=0) for key in keys}


def _normalize_energy_maxima(
    raw_energies: dict[str, Any],
    raw_energy_maxima: dict[str, Any],
) -> dict[str, dict[str, int]]:
    maxima: dict[str, dict[str, int]] = {}
    for key in XIANXIA_ENERGY_KEYS:
        raw_value = raw_energy_maxima.get(key)
        if raw_value is None or raw_value == "":
            raw_energy = raw_energies.get(key)
            raw_value = dict(raw_energy or {}).get("max") if isinstance(raw_energy, dict) else raw_energy
        maxima[key] = {"max": _normalize_int(raw_value, default=0)}
    return maxima


def _normalize_yin_yang(
    raw_xianxia: dict[str, Any],
    payload: dict[str, Any],
    raw_stats: dict[str, Any],
) -> dict[str, int]:
    raw_yin_yang = _first_mapping(raw_xianxia, payload, raw_stats, key="yin_yang")
    return {
        "yin_max": _normalize_int(
            raw_yin_yang.get("yin_max")
            if "yin_max" in raw_yin_yang
            else _first_present(raw_xianxia, payload, key="yin_max"),
            default=1,
        ),
        "yang_max": _normalize_int(
            raw_yin_yang.get("yang_max")
            if "yang_max" in raw_yin_yang
            else _first_present(raw_xianxia, payload, key="yang_max"),
            default=1,
        ),
    }


def _normalize_insight(raw_xianxia: dict[str, Any], payload: dict[str, Any]) -> dict[str, int]:
    raw_insight = _first_mapping(raw_xianxia, payload, key="insight")
    return {
        "available": _normalize_int(
            raw_insight.get("available")
            if "available" in raw_insight
            else _first_present(raw_xianxia, payload, key="insight_available"),
            default=0,
        ),
        "spent": _normalize_int(
            raw_insight.get("spent")
            if "spent" in raw_insight
            else _first_present(raw_xianxia, payload, key="insight_spent"),
            default=0,
        ),
    }


def _normalize_text_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    deduped: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        if isinstance(value, dict):
            value = value.get("name") or value.get("label")
        cleaned = _normalize_text(value)
        marker = cleaned.casefold()
        if not cleaned or marker in seen:
            continue
        seen.add(marker)
        deduped.append(cleaned)
    return deduped


def _normalize_named_records(values: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in _normalize_record_list(values):
        name = _normalize_text(record.get("name") or record.get("label"))
        if name:
            record["name"] = name
        reason = _normalize_text(record.get("reason"))
        if reason:
            record["reason"] = reason
        elif "reason" in record:
            record.pop("reason", None)
        if record:
            records.append(record)
    return records


def _normalize_record_list(values: Any) -> list[dict[str, Any]]:
    if isinstance(values, str):
        values = [values]
    if isinstance(values, dict):
        values = [values]
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        if isinstance(value, dict):
            records.append(deepcopy(value))
            continue
        cleaned = _normalize_text(value)
        if cleaned:
            records.append({"name": cleaned})
    return records


def _normalize_dao_immolating_records(
    raw_xianxia: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    raw_records = (
        _first_present(raw_xianxia, payload, key="dao_immolating_techniques")
        if _has_any(raw_xianxia, payload, key="dao_immolating_techniques")
        else _first_present(raw_xianxia, payload, key="dao_immolating_records")
    )
    if not isinstance(raw_records, dict):
        raw_records = {}
    return {
        "prepared": _normalize_record_list(raw_records.get("prepared")),
        "use_history": _normalize_record_list(
            raw_records.get("use_history") if "use_history" in raw_records else raw_records.get("history")
        ),
    }
