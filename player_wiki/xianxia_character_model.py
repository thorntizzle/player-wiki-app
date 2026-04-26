from __future__ import annotations

from copy import deepcopy
from typing import Any

from .system_policy import is_xianxia_system, normalize_system_code

XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION = 1
XIANXIA_CHARACTER_STATE_SCHEMA_VERSION = 1

XIANXIA_ATTRIBUTE_KEYS = ("str", "dex", "con", "int", "wis", "cha")
XIANXIA_ATTRIBUTE_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}
XIANXIA_EFFORT_KEYS = ("basic", "weapon", "guns_explosive", "magic", "ultimate")
XIANXIA_EFFORT_LABELS = {
    "basic": "Basic",
    "weapon": "Weapon",
    "guns_explosive": "Guns/Explosive",
    "magic": "Magic",
    "ultimate": "Ultimate",
}
XIANXIA_EFFORT_DAMAGE_DICE = {
    "basic": "1d4",
    "weapon": "1d6",
    "guns_explosive": "1d8",
    "magic": "1d10",
    "ultimate": "1d12",
}
XIANXIA_ENERGY_KEYS = ("jing", "qi", "shen")
XIANXIA_DEFENSE_BASE = 10
XIANXIA_CHECK_FORMULA = "1d20 + Attribute + Realm modifier + situational modifiers"
XIANXIA_CHECK_SPEND_BONUS = "+1d6"
XIANXIA_CHECK_SPEND_BONUS_DETAIL = "per spent Energy/Yin/Yang point"
XIANXIA_DIFFICULTY_STATE_ADJUSTMENTS = (
    ("easy", "EASY", -3),
    ("normal", "Normal", 0),
    ("hard", "HARD", 3),
)

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

XIANXIA_STATE_FIELD_KEYS = (
    "schema_version",
    "vitals",
    "energies",
    "yin_yang",
    "dao",
    "active_stance",
    "active_aura",
    "inventory",
    "notes",
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

_DEFERRED_DEFINITION_KEYS = {
    "dying": "Dying Rounds belong to a future combat-state shape.",
    "dying_rounds": "Dying Rounds belong to a future combat-state shape.",
    "dying_rounds_remaining": "Dying Rounds belong to a future combat-state shape.",
}


class XianxiaDefinitionValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


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
    actions_per_turn = derive_xianxia_actions_per_turn(realm)

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
    attributes = _normalize_int_key_map(
        _first_mapping(raw_xianxia, normalized_payload, raw_stats, key="attributes"),
        XIANXIA_ATTRIBUTE_KEYS,
    )

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
        "attributes": attributes,
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
            "defense": derive_xianxia_defense(
                attributes=attributes,
                manual_armor_bonus=manual_armor_bonus,
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


def derive_xianxia_defense(
    *,
    attributes: dict[str, Any] | None = None,
    manual_armor_bonus: Any = 0,
) -> int:
    """Return Xianxia Defense from base 10, manual armor bonus, and Constitution."""

    raw_attributes = dict(attributes or {})
    constitution = _normalize_int(raw_attributes.get("con"), default=0)
    armor_bonus = _normalize_int(manual_armor_bonus, default=0)
    return XIANXIA_DEFENSE_BASE + armor_bonus + constitution


def derive_xianxia_actions_per_turn(realm: Any) -> int:
    """Return the fixed Xianxia action count for a normalized Realm."""

    normalized_realm = _normalize_choice(
        realm,
        choices=_REALM_LABELS,
        default="Mortal",
    )
    return _REALM_ACTION_DEFAULTS.get(normalized_realm, _REALM_ACTION_DEFAULTS["Mortal"])


def derive_xianxia_effort_damage_strings() -> dict[str, str]:
    """Return Xianxia effort damage expressions keyed by effort identifier."""

    return {
        key: f"{XIANXIA_EFFORT_DAMAGE_DICE[key]} + {XIANXIA_EFFORT_LABELS[key]}"
        for key in XIANXIA_EFFORT_KEYS
    }


def derive_xianxia_check_formula_strings() -> dict[str, str]:
    """Return the first-pass Xianxia check formula reminder strings."""

    return {
        "formula": XIANXIA_CHECK_FORMULA,
        "spend_bonus": XIANXIA_CHECK_SPEND_BONUS,
        "spend_bonus_detail": XIANXIA_CHECK_SPEND_BONUS_DETAIL,
        "summary": (
            f"{XIANXIA_CHECK_FORMULA}, plus "
            f"{XIANXIA_CHECK_SPEND_BONUS} {XIANXIA_CHECK_SPEND_BONUS_DETAIL}."
        ),
    }


def derive_xianxia_difficulty_state_adjustments() -> dict[str, Any]:
    """Return the capped final Xianxia DC states for sheet presentation."""

    states = [
        {
            "key": key,
            "label": label,
            "adjustment": adjustment,
            "adjustment_label": _format_dc_adjustment(adjustment),
        }
        for key, label, adjustment in XIANXIA_DIFFICULTY_STATE_ADJUSTMENTS
    ]
    return {
        "states": states,
        "summary": "EASY -3, Normal 0, HARD +3",
        "resolution_note": (
            "Resolve EASY/HARD influences to one final DC state before applying "
            "the listed adjustment."
        ),
    }


def validate_xianxia_definition_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized Xianxia definition payload or raise with validation details."""

    errors = xianxia_definition_validation_errors(payload)
    if errors:
        raise XianxiaDefinitionValidationError(errors)
    return _normalized_definition_validation_payload(payload)


def xianxia_definition_validation_errors(payload: dict[str, Any]) -> list[str]:
    normalized_payload = _normalized_definition_validation_payload(payload)
    if not is_xianxia_system(normalized_payload.get("system")):
        return []

    errors: list[str] = []
    _collect_deferred_definition_key_errors(payload, errors)

    xianxia = dict(normalized_payload.get("xianxia") or {})
    if tuple(xianxia) != XIANXIA_DEFINITION_FIELD_KEYS:
        expected = ", ".join(XIANXIA_DEFINITION_FIELD_KEYS)
        errors.append(f"xianxia must use the stable definition field order: {expected}.")

    _require_exact_int(
        errors,
        "xianxia.schema_version",
        xianxia.get("schema_version"),
        XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
    )

    realm = xianxia.get("realm")
    if realm not in _REALM_ACTION_DEFAULTS:
        allowed = ", ".join(_REALM_ACTION_DEFAULTS)
        errors.append(f"xianxia.realm must be one of: {allowed}.")

    actions_per_turn = xianxia.get("actions_per_turn")
    _require_non_negative_int(errors, "xianxia.actions_per_turn", actions_per_turn)
    if realm in _REALM_ACTION_DEFAULTS and actions_per_turn != _REALM_ACTION_DEFAULTS[realm]:
        errors.append(
            f"xianxia.actions_per_turn must match the {realm} realm default of "
            f"{_REALM_ACTION_DEFAULTS[realm]}."
        )

    if xianxia.get("honor") not in set(_HONOR_LABELS.values()):
        allowed = ", ".join(_HONOR_LABELS.values())
        errors.append(f"xianxia.honor must be one of: {allowed}.")
    if not _normalize_text(xianxia.get("reputation")):
        errors.append("xianxia.reputation is required.")

    _validate_int_key_map(errors, "xianxia.attributes", xianxia.get("attributes"), XIANXIA_ATTRIBUTE_KEYS)
    _validate_int_key_map(errors, "xianxia.efforts", xianxia.get("efforts"), XIANXIA_EFFORT_KEYS)
    _validate_energy_maxima(errors, xianxia.get("energies"))
    _validate_yin_yang(errors, xianxia.get("yin_yang"))
    _validate_dao_definition(errors, xianxia.get("dao"))
    _validate_insight_definition(errors, xianxia.get("insight"))
    _validate_durability_definition(errors, xianxia.get("durability"))
    _validate_skills_definition(errors, xianxia.get("skills"))
    _validate_equipment_definition(errors, xianxia.get("equipment"))

    for path in (
        "xianxia.martial_arts",
        "xianxia.generic_techniques",
        "xianxia.variants",
        "xianxia.approval_requests",
        "xianxia.companions",
        "xianxia.advancement_history",
    ):
        _validate_record_list(errors, path, _value_at_path(xianxia, path.removeprefix("xianxia.")))

    _validate_dao_immolating_definition(errors, xianxia.get("dao_immolating_techniques"))
    return errors


def build_xianxia_initial_state_payload(definition: Any) -> dict[str, Any]:
    return normalize_xianxia_state_payload(definition, {})


def normalize_xianxia_state_payload(definition: Any, state_payload: dict[str, Any] | None) -> dict[str, Any]:
    raw_state = dict(state_payload or {})
    raw_vitals = _first_mapping(raw_state, key="vitals")
    raw_energies = _first_mapping(raw_state, key="energies")
    raw_energies_current = _first_mapping(raw_state, key="energies_current")
    raw_yin_yang = _first_mapping(raw_state, key="yin_yang")
    raw_dao = _first_mapping(raw_state, key="dao")

    normalized_state = {
        "schema_version": XIANXIA_CHARACTER_STATE_SCHEMA_VERSION,
        "vitals": {
            "current_hp": _normalize_int(
                raw_vitals.get("current_hp")
                if "current_hp" in raw_vitals
                else _first_present(raw_state, key="hp_current")
                if _has_any(raw_state, key="hp_current")
                else _first_present(raw_state, key="current_hp"),
                default=xianxia_hp_max(definition),
            ),
            "temp_hp": _normalize_int(
                raw_vitals.get("temp_hp")
                if "temp_hp" in raw_vitals
                else _first_present(raw_state, key="hp_temp")
                if _has_any(raw_state, key="hp_temp")
                else _first_present(raw_state, key="temp_hp"),
                default=0,
            ),
            "current_stance": _normalize_int(
                raw_vitals.get("current_stance")
                if "current_stance" in raw_vitals
                else raw_vitals.get("stance_current")
                if "stance_current" in raw_vitals
                else _first_present(raw_state, key="stance_current"),
                default=xianxia_stance_max(definition),
            ),
            "temp_stance": _normalize_int(
                raw_vitals.get("temp_stance")
                if "temp_stance" in raw_vitals
                else raw_vitals.get("stance_temp")
                if "stance_temp" in raw_vitals
                else _first_present(raw_state, key="stance_temp"),
                default=0,
            ),
        },
        "energies": _normalize_xianxia_energy_current(definition, raw_energies, raw_energies_current),
        "yin_yang": {
            "yin_current": _normalize_int(
                raw_yin_yang.get("yin_current")
                if "yin_current" in raw_yin_yang
                else _first_present(raw_state, key="yin_current"),
                default=xianxia_yin_max(definition),
            ),
            "yang_current": _normalize_int(
                raw_yin_yang.get("yang_current")
                if "yang_current" in raw_yin_yang
                else _first_present(raw_state, key="yang_current"),
                default=xianxia_yang_max(definition),
            ),
        },
        "dao": {
            "current": _normalize_int(
                raw_dao.get("current") if "current" in raw_dao else _first_present(raw_state, key="dao_current"),
                default=0,
            )
        },
        "active_stance": _normalize_active_state_record(_first_present(raw_state, key="active_stance")),
        "active_aura": _normalize_active_state_record(_first_present(raw_state, key="active_aura")),
        "inventory": _normalize_xianxia_inventory_state(
            _first_present(raw_state, key="inventory"),
            definition=definition,
        ),
        "notes": _normalize_xianxia_notes_state(_first_present(raw_state, key="notes")),
    }
    return clamp_xianxia_mutable_pools(definition, normalized_state)


def xianxia_hp_max(definition: Any) -> int:
    return _normalize_non_negative_int(_definition_durability(definition).get("hp_max"), default=10)


def xianxia_stance_max(definition: Any) -> int:
    return _normalize_non_negative_int(_definition_durability(definition).get("stance_max"), default=10)


def xianxia_yin_max(definition: Any) -> int:
    return _normalize_non_negative_int(_definition_yin_yang(definition).get("yin_max"), default=1)


def xianxia_yang_max(definition: Any) -> int:
    return _normalize_non_negative_int(_definition_yin_yang(definition).get("yang_max"), default=1)


def xianxia_energy_max(definition: Any, energy_key: str) -> int:
    key = str(energy_key or "").strip().casefold()
    if key not in XIANXIA_ENERGY_KEYS:
        return 0
    energy = dict(_definition_energies(definition).get(key) or {})
    return _normalize_non_negative_int(energy.get("max"), default=0)


def xianxia_dao_max(definition: Any) -> int:
    dao = dict(_definition_xianxia(definition).get("dao") or {})
    return _normalize_non_negative_int(dao.get("max"), default=3)


def clamp_xianxia_mutable_pools(definition: Any, state_payload: dict[str, Any]) -> dict[str, Any]:
    """Clamp current Xianxia mutable pools to the definition's current maxima."""

    payload = deepcopy(state_payload or {})
    vitals = dict(payload.get("vitals") or {})
    vitals["current_hp"] = _clamp_int(
        vitals.get("current_hp"),
        default=xianxia_hp_max(definition),
        maximum=xianxia_hp_max(definition),
    )
    vitals["temp_hp"] = _clamp_int(vitals.get("temp_hp"), default=0)
    vitals["current_stance"] = _clamp_int(
        vitals.get("current_stance"),
        default=xianxia_stance_max(definition),
        maximum=xianxia_stance_max(definition),
    )
    vitals["temp_stance"] = _clamp_int(vitals.get("temp_stance"), default=0)
    payload["vitals"] = vitals

    raw_energies = dict(payload.get("energies") or {})
    energies: dict[str, dict[str, int]] = {}
    for key in XIANXIA_ENERGY_KEYS:
        energy = dict(raw_energies.get(key) or {})
        max_value = xianxia_energy_max(definition, key)
        energies[key] = {
            "current": _clamp_int(
                energy.get("current"),
                default=max_value,
                maximum=max_value,
            )
        }
    payload["energies"] = energies

    yin_yang = dict(payload.get("yin_yang") or {})
    payload["yin_yang"] = {
        "yin_current": _clamp_int(
            yin_yang.get("yin_current"),
            default=xianxia_yin_max(definition),
            maximum=xianxia_yin_max(definition),
        ),
        "yang_current": _clamp_int(
            yin_yang.get("yang_current"),
            default=xianxia_yang_max(definition),
            maximum=xianxia_yang_max(definition),
        ),
    }

    dao = dict(payload.get("dao") or {})
    payload["dao"] = {
        "current": _clamp_int(
            dao.get("current"),
            default=0,
            maximum=xianxia_dao_max(definition),
        )
    }
    return payload


def _normalized_definition_validation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_system = normalize_system_code(payload.get("system") or payload.get("system_code"))
    validation_payload = deepcopy(payload)
    if normalized_system:
        validation_payload["system"] = normalized_system
    return normalize_xianxia_definition_payload(validation_payload)


def _collect_deferred_definition_key_errors(payload: dict[str, Any], errors: list[str]) -> None:
    raw_xianxia = payload.get("xianxia") if isinstance(payload.get("xianxia"), dict) else {}
    for path, mapping in (("", payload), ("xianxia.", raw_xianxia)):
        if not isinstance(mapping, dict):
            continue
        for key, reason in _DEFERRED_DEFINITION_KEYS.items():
            if key in mapping:
                errors.append(f"{path}{key} is not valid Xianxia definition data. {reason}")


def _value_at_path(mapping: dict[str, Any], path: str) -> Any:
    current: Any = mapping
    for part in path.split("."):
        current = dict(current or {}).get(part) if isinstance(current, dict) else None
    return current


def _require_exact_int(errors: list[str], path: str, value: Any, expected: int) -> None:
    if not isinstance(value, int):
        errors.append(f"{path} must be a whole number.")
        return
    if value != expected:
        errors.append(f"{path} must be {expected}.")


def _require_non_negative_int(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, int):
        errors.append(f"{path} must be a whole number.")
        return
    if value < 0:
        errors.append(f"{path} cannot be negative.")


def _validate_int_key_map(
    errors: list[str],
    path: str,
    value: Any,
    keys: tuple[str, ...],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object.")
        return
    for key in keys:
        _require_non_negative_int(errors, f"{path}.{key}", value.get(key))
    unknown = sorted(set(value) - set(keys))
    if unknown:
        errors.append(f"{path} uses unsupported keys: {', '.join(unknown)}.")


def _validate_energy_maxima(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.energies must be an object.")
        return
    for key in XIANXIA_ENERGY_KEYS:
        energy = value.get(key)
        if not isinstance(energy, dict):
            errors.append(f"xianxia.energies.{key} must be an object.")
            continue
        _require_non_negative_int(errors, f"xianxia.energies.{key}.max", energy.get("max"))
        unknown = sorted(set(energy) - {"max"})
        if unknown:
            errors.append(f"xianxia.energies.{key} uses unsupported keys: {', '.join(unknown)}.")
    unknown = sorted(set(value) - set(XIANXIA_ENERGY_KEYS))
    if unknown:
        errors.append(f"xianxia.energies uses unsupported keys: {', '.join(unknown)}.")


def _validate_yin_yang(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.yin_yang must be an object.")
        return
    for key in ("yin_max", "yang_max"):
        _require_non_negative_int(errors, f"xianxia.yin_yang.{key}", value.get(key))
    unknown = sorted(set(value) - {"yin_max", "yang_max"})
    if unknown:
        errors.append(f"xianxia.yin_yang uses unsupported keys: {', '.join(unknown)}.")


def _validate_dao_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.dao must be an object.")
        return
    _require_exact_int(errors, "xianxia.dao.max", value.get("max"), 3)
    unknown = sorted(set(value) - {"max"})
    if unknown:
        errors.append(f"xianxia.dao uses unsupported keys: {', '.join(unknown)}.")


def _validate_insight_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.insight must be an object.")
        return
    for key in ("available", "spent"):
        _require_non_negative_int(errors, f"xianxia.insight.{key}", value.get(key))
    unknown = sorted(set(value) - {"available", "spent"})
    if unknown:
        errors.append(f"xianxia.insight uses unsupported keys: {', '.join(unknown)}.")


def _validate_durability_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.durability must be an object.")
        return
    for key in ("hp_max", "stance_max", "manual_armor_bonus", "defense"):
        _require_non_negative_int(errors, f"xianxia.durability.{key}", value.get(key))
    unknown = sorted(set(value) - {"hp_max", "stance_max", "manual_armor_bonus", "defense"})
    if unknown:
        errors.append(f"xianxia.durability uses unsupported keys: {', '.join(unknown)}.")


def _validate_skills_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.skills must be an object.")
        return
    trained = value.get("trained")
    if not isinstance(trained, list):
        errors.append("xianxia.skills.trained must be a list.")
    else:
        for index, skill in enumerate(trained):
            if not isinstance(skill, str) or not skill.strip():
                errors.append(f"xianxia.skills.trained[{index}] must be a non-empty string.")
    unknown = sorted(set(value) - {"trained"})
    if unknown:
        errors.append(f"xianxia.skills uses unsupported keys: {', '.join(unknown)}.")


def _validate_equipment_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.equipment must be an object.")
        return
    for key in ("necessary_weapons", "necessary_tools"):
        _validate_record_list(errors, f"xianxia.equipment.{key}", value.get(key), require_name=True)
    unknown = sorted(set(value) - {"necessary_weapons", "necessary_tools"})
    if unknown:
        errors.append(f"xianxia.equipment uses unsupported keys: {', '.join(unknown)}.")


def _validate_dao_immolating_definition(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("xianxia.dao_immolating_techniques must be an object.")
        return
    for key in ("prepared", "use_history"):
        _validate_record_list(errors, f"xianxia.dao_immolating_techniques.{key}", value.get(key))
    unknown = sorted(set(value) - {"prepared", "use_history"})
    if unknown:
        errors.append(f"xianxia.dao_immolating_techniques uses unsupported keys: {', '.join(unknown)}.")


def _validate_record_list(
    errors: list[str],
    path: str,
    value: Any,
    *,
    require_name: bool = False,
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list.")
        return
    for index, record in enumerate(value):
        if not isinstance(record, dict) or not record:
            errors.append(f"{path}[{index}] must be a non-empty object.")
            continue
        if require_name and not _normalize_text(record.get("name")):
            errors.append(f"{path}[{index}].name is required.")


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


def _format_dc_adjustment(value: int) -> str:
    if value == 0:
        return "0"
    return f"{value:+d}"


def _normalize_non_negative_int(value: Any, *, default: int = 0) -> int:
    return max(0, _normalize_int(value, default=default))


def _clamp_int(
    value: Any,
    *,
    default: int = 0,
    maximum: int | None = None,
) -> int:
    normalized = _normalize_non_negative_int(value, default=default)
    if maximum is None:
        return normalized
    return min(normalized, max(0, int(maximum)))


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


def _definition_xianxia(definition: Any) -> dict[str, Any]:
    if isinstance(definition, dict):
        return dict(definition.get("xianxia") or {})
    return dict(getattr(definition, "xianxia", {}) or {})


def _definition_durability(definition: Any) -> dict[str, Any]:
    return dict(_definition_xianxia(definition).get("durability") or {})


def _definition_yin_yang(definition: Any) -> dict[str, Any]:
    return dict(_definition_xianxia(definition).get("yin_yang") or {})


def _definition_energies(definition: Any) -> dict[str, Any]:
    return dict(_definition_xianxia(definition).get("energies") or {})


def _normalize_xianxia_energy_current(
    definition: Any,
    raw_energies: dict[str, Any],
    raw_energies_current: dict[str, Any],
) -> dict[str, dict[str, int]]:
    definition_energies = _definition_energies(definition)
    normalized: dict[str, dict[str, int]] = {}
    for key in XIANXIA_ENERGY_KEYS:
        raw_value = raw_energies_current.get(key)
        if raw_value is None or raw_value == "":
            raw_energy = raw_energies.get(key)
            raw_value = dict(raw_energy or {}).get("current") if isinstance(raw_energy, dict) else raw_energy
        max_value = dict(definition_energies.get(key) or {}).get("max")
        normalized[key] = {"current": _normalize_int(raw_value, default=_normalize_int(max_value, default=0))}
    return normalized


def _normalize_active_state_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        record = deepcopy(value)
        name = _normalize_text(record.get("name") or record.get("label"))
        if name:
            record["name"] = name
        systems_ref = record.get("systems_ref")
        if systems_ref is not None and not isinstance(systems_ref, dict):
            record.pop("systems_ref", None)
        return record if record else None

    name = _normalize_text(value)
    return {"name": name} if name else None


def _normalize_xianxia_inventory_state(value: Any, *, definition: Any) -> dict[str, Any]:
    raw_inventory = dict(value or {}) if isinstance(value, dict) else {}
    raw_quantities = (
        raw_inventory.get("quantities")
        if "quantities" in raw_inventory
        else raw_inventory.get("item_quantities")
        if "item_quantities" in raw_inventory
        else raw_inventory.get("items")
        if "items" in raw_inventory
        else value
    )
    quantities = _normalize_xianxia_inventory_quantities(raw_quantities)
    if not quantities:
        equipment_catalog = list(getattr(definition, "equipment_catalog", []) or [])
        quantities = _normalize_xianxia_inventory_quantities(equipment_catalog)
    enabled = bool(raw_inventory.get("enabled", False)) or bool(quantities)
    return {"enabled": enabled, "quantities": quantities if enabled else []}


def _normalize_xianxia_inventory_quantities(values: Any) -> list[dict[str, Any]]:
    if isinstance(values, dict):
        values = [
            {"id": str(key), "quantity": quantity}
            for key, quantity in values.items()
            if str(key).strip()
        ]
    if isinstance(values, str):
        values = [{"name": values, "quantity": 1}]
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        if not isinstance(value, dict):
            value = {"name": value, "quantity": 1}
        item_id = _normalize_text(value.get("id"))
        catalog_ref = _normalize_text(value.get("catalog_ref"))
        name = _normalize_text(value.get("name") or value.get("label"))
        if not item_id and not catalog_ref and not name:
            continue
        quantity = value.get("quantity") if "quantity" in value else value.get("default_quantity")
        record: dict[str, Any] = {"quantity": _normalize_int(quantity, default=0)}
        if item_id:
            record["id"] = item_id
        if catalog_ref:
            record["catalog_ref"] = catalog_ref
        if name:
            record["name"] = name
        records.append(record)
    return records


def _normalize_xianxia_notes_state(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {"player_notes_markdown": str(value.get("player_notes_markdown") or "")}
    return {"player_notes_markdown": str(value or "")}
