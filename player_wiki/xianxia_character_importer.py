from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .auth_store import isoformat, utcnow
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_service import build_initial_state
from .repository import slugify
from .system_policy import XIANXIA_SYSTEM_CODE
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_CURRENCY_KEYS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_ENERGY_KEYS,
    normalize_xianxia_state_payload,
    validate_xianxia_definition_payload,
)

XIANXIA_MANUAL_IMPORTER_SOURCE_PATH = "importer://xianxia-manual"
XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE = "xianxia_manual_importer"
XIANXIA_MANUAL_IMPORTER_VERSION = "2026-05-13.0"
XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM = "Manual Xianxia character importer"

_REALM_ACTIONS = {"Mortal": 2, "Immortal": 3, "Divine": 4}
_REALM_LABELS = {"mortal": "Mortal", "immortal": "Immortal", "divine": "Divine"}
_HONOR_LABELS = {
    "venerable": "Venerable",
    "majestic": "Majestic",
    "honorable": "Honorable",
    "disgraced": "Disgraced",
    "demonic": "Demonic",
}
_MARTIAL_ART_RANK_ORDER = ("initiate", "novice", "apprentice", "master", "legendary")
_MARTIAL_ART_RANK_LABELS = {
    "initiate": "Initiate",
    "novice": "Novice",
    "apprentice": "Apprentice",
    "master": "Master",
    "legendary": "Legendary",
}
_INDEX_ROW_PREFIX = re.compile(r"^([a-z_]+)_(\d+)(?:_(.+))?$", re.IGNORECASE)


def build_xianxia_manual_import_character(
    payload: dict[str, Any],
    *,
    campaign_slug: str | None = None,
    martial_art_options: list[dict[str, Any]] | None = None,
    parser_version: str = XIANXIA_MANUAL_IMPORTER_VERSION,
    imported_at_utc: str | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, Any]]:
    raw_payload = _coerce_mapping(payload)
    resolved_campaign_slug = _coerce_text(
        campaign_slug
        or raw_payload.get("campaign_slug")
        or raw_payload.get("campaign")
        or raw_payload.get("campaign_id")
    )
    if not resolved_campaign_slug:
        raise ValueError("campaign_slug is required.")

    character_name = _coerce_text(
        raw_payload.get("name")
        or raw_payload.get("character_name")
        or raw_payload.get("title")
    )
    if not character_name:
        raise ValueError("character name is required.")

    character_slug = _coerce_text(
        raw_payload.get("character_slug")
        or raw_payload.get("slug")
        or slugify(character_name)
    )
    if not character_slug:
        raise ValueError("character_slug is required.")

    imported_at = _coerce_text(imported_at_utc) or isoformat(utcnow())
    base_definition_payload = _coerce_xianxia_definition_payload(raw_payload)
    trained_skills, imported_skill_notes = _coerce_freeform_trained_skills(raw_payload)
    base_definition_payload["skills"] = {"trained": trained_skills}
    base_definition_payload["martial_arts"] = _coerce_martial_arts_payload(
        raw_payload,
        martial_art_options=martial_art_options,
    )

    reference_notes = _coerce_reference_notes(raw_payload)
    if imported_skill_notes:
        reference_notes["additional_notes_markdown"] = _append_notes_section(
            reference_notes["additional_notes_markdown"],
            "Imported skill notes",
            imported_skill_notes,
        )

    state_payload = _coerce_xianxia_state_payload(raw_payload)
    base_definition_payload = _raise_maxima_to_preserve_current_values(
        base_definition_payload,
        state_payload,
    )

    definition_payload: dict[str, Any] = {
        "campaign_slug": resolved_campaign_slug,
        "character_slug": character_slug,
        "name": character_name,
        "status": _coerce_text(raw_payload.get("status")) or "active",
        "system": XIANXIA_SYSTEM_CODE,
        "profile": {
            "class_level_text": _coerce_text(
                _first_present(
                    [raw_payload.get("profile"), raw_payload.get("xianxia")],
                    ("class_level_text",),
                )
            )
            or "Mortal Xianxia Character",
            "realm": base_definition_payload["realm"],
            "honor": base_definition_payload["honor"],
            "reputation": base_definition_payload["reputation"],
        },
        "stats": {},
        "skills": [],
        "proficiencies": {
            "armor": [],
            "weapons": [],
            "tools": [],
            "languages": [],
            "tool_expertise": [],
        },
        "attacks": [],
        "features": [],
        "spellcasting": {},
        "equipment_catalog": [],
        "reference_notes": reference_notes,
        "resource_templates": [],
        "source": {
            "source_path": XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
            "source_type": XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE,
            "imported_from": XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM,
            "imported_at": imported_at,
            "parse_warnings": [],
        },
        "xianxia": base_definition_payload,
    }

    validated_definition_payload = validate_xianxia_definition_payload(definition_payload)
    definition = CharacterDefinition.from_dict(validated_definition_payload)

    initial_state = build_initial_state(definition)
    normalized_state_payload = normalize_xianxia_state_payload(
        definition,
        state_payload,
    )
    initial_state["xianxia"] = normalized_state_payload
    initial_state["vitals"] = {
        "current_hp": int(normalized_state_payload["vitals"]["current_hp"]),
        "temp_hp": int(normalized_state_payload["vitals"]["temp_hp"]),
    }
    initial_state["inventory"] = [
        dict(item) for item in normalized_state_payload["inventory"].get("quantities", [])
    ]
    initial_state["notes"]["player_notes_markdown"] = str(
        normalized_state_payload["notes"].get("player_notes_markdown") or ""
    )

    import_metadata = CharacterImportMetadata(
        campaign_slug=definition.campaign_slug,
        character_slug=definition.character_slug,
        source_path=XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
        imported_at_utc=imported_at,
        parser_version=parser_version,
        import_status="clean",
        warnings=[],
    )

    return definition, import_metadata, initial_state


def _coerce_xianxia_definition_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_xianxia = _coerce_mapping(payload.get("xianxia"))
    raw_profile = _coerce_mapping(payload.get("profile"))
    raw_stats = _coerce_mapping(payload.get("stats"))
    raw_attributes = _coerce_mapping(raw_xianxia.get("attributes"))
    raw_efforts = _coerce_mapping(raw_xianxia.get("efforts"))
    raw_energies = _coerce_mapping(raw_xianxia.get("energies"))
    raw_energy_maxima = _coerce_mapping(raw_xianxia.get("energy_maxima"))
    if not raw_energy_maxima:
        raw_energy_maxima = _coerce_mapping(payload.get("energy_maxima"))
    raw_yin_yang = _coerce_mapping(raw_xianxia.get("yin_yang"))
    if not raw_yin_yang:
        raw_yin_yang = _coerce_mapping(payload.get("yin_yang"))

    raw_dao = _coerce_mapping(raw_xianxia.get("dao"))

    realm = _coerce_choice(
        _first_present_value(
            [raw_xianxia, raw_profile, payload],
            ("realm",),
        ),
        aliases=_REALM_LABELS,
        default="Mortal",
    )
    honor = _coerce_choice(
        _first_present_value(
            [raw_xianxia, raw_profile, payload],
            ("honor",),
        ),
        aliases=_HONOR_LABELS,
        default="Honorable",
    )

    return {
        "schema_version": 1,
        "realm": realm,
        "actions_per_turn": _REALM_ACTIONS[realm],
        "honor": honor,
        "reputation": _coerce_text(
            _first_present_value(
                [raw_xianxia, raw_profile, payload],
                ("reputation",),
            )
            or "Unknown"
        ),
        "attributes": _coerce_int_map(
            [raw_attributes, raw_xianxia, raw_stats, payload],
            keys=XIANXIA_ATTRIBUTE_KEYS,
            aliases=("attribute_",),
        ),
        "efforts": _coerce_int_map(
            [raw_efforts, raw_xianxia, raw_stats, payload],
            keys=XIANXIA_EFFORT_KEYS,
            aliases=("effort_",),
        ),
        "energies": {
            energy_key: {
                "max": _coerce_int(
                    _coerce_energy_maximum(energy_key, [raw_xianxia, raw_energy_maxima, payload], raw_energies),
                    default=0,
                )
            }
            for energy_key in XIANXIA_ENERGY_KEYS
        },
        "yin_yang": {
            "yin_max": _coerce_int(
                _first_present_value(
                    [raw_yin_yang, raw_xianxia, payload],
                    ("yin_max",),
                ),
                default=1,
            ),
            "yang_max": _coerce_int(
                _first_present_value(
                    [raw_yin_yang, raw_xianxia, payload],
                    ("yang_max",),
                ),
                default=1,
            ),
        },
        "dao": {
            "max": _coerce_int(
                _first_present_value(
                    [raw_dao, raw_xianxia, payload],
                    ("max", "dao_max"),
                ),
                default=3,
            )
        },
        "insight": {
            "available": _coerce_int(
                _first_present_value(
                    [raw_xianxia, payload],
                    ("insight_available",),
                ),
                default=0,
            ),
            "spent": _coerce_int(
                _first_present_value(
                    [raw_xianxia, payload],
                    ("insight_spent",),
                ),
                default=0,
            ),
        },
        "durability": {
            "hp_max": _coerce_int(
                _first_present_value(
                    [raw_xianxia, raw_stats, payload],
                    ("hp_max",),
                ),
                default=10,
            ),
            "stance_max": _coerce_int(
                _first_present_value(
                    [raw_xianxia, raw_stats, payload],
                    ("stance_max",),
                ),
                default=10,
            ),
            "manual_armor_bonus": _coerce_int(
                _first_present_value(
                    [raw_xianxia, raw_stats, payload],
                    ("manual_armor_bonus",),
                ),
                default=0,
            ),
        },
        "skills": {"trained": []},
        "equipment": {
            "necessary_weapons": _coerce_named_records(
                _first_present_value(
                    [raw_xianxia, payload],
                    ("necessary_weapons",),
                )
            ),
            "necessary_tools": _coerce_named_records(
                _first_present_value(
                    [raw_xianxia, payload],
                    ("necessary_tools",),
                )
            ),
        },
        "martial_arts": [],
        "generic_techniques": _coerce_named_records(
            _first_present_value(
                [raw_xianxia, payload],
                ("generic_techniques",),
            )
        ),
        "variants": _coerce_named_records(
            _first_present_value(
                [raw_xianxia, payload],
                ("variants",),
            )
        ),
        "dao_immolating_techniques": _coerce_dao_immolating_payload(raw_payload=payload),
        "approval_requests": _coerce_named_records(
            _first_present_value(
                [raw_xianxia, payload],
                ("approval_requests",),
            )
        ),
        "companions": _coerce_named_records(
            _first_present_value(
                [raw_xianxia, payload],
                ("companions",),
            )
        ),
        "advancement_history": _coerce_named_records(
            _first_present_value(
                [raw_xianxia, payload],
                ("advancement_history",),
            )
        ),
    }


def _coerce_xianxia_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_state = _coerce_mapping(payload.get("state"))
    raw_state_xianxia = _coerce_mapping(raw_state.get("xianxia"))
    if not raw_state_xianxia:
        raw_state_xianxia = _coerce_mapping(payload.get("xianxia")) if not raw_state else {}

    raw_vitals = _coerce_mapping(raw_state_xianxia.get("vitals"))
    if not raw_vitals:
        raw_vitals = _coerce_mapping(raw_state.get("vitals"))

    raw_energies = _coerce_mapping(raw_state_xianxia.get("energies"))
    if not raw_energies:
        raw_energies = _coerce_mapping(raw_state.get("energies"))

    raw_energies_current = _coerce_mapping(raw_state_xianxia.get("energies_current"))
    if not raw_energies_current:
        raw_energies_current = _coerce_mapping(raw_state.get("energies_current"))

    raw_yin_yang = _coerce_mapping(raw_state_xianxia.get("yin_yang"))
    if not raw_yin_yang:
        raw_yin_yang = _coerce_mapping(raw_state.get("yin_yang"))

    raw_dao = _coerce_mapping(raw_state_xianxia.get("dao"))
    if not raw_dao:
        raw_dao = _coerce_mapping(raw_state.get("dao"))

    raw_currency = _coerce_mapping(raw_state_xianxia.get("currency"))
    if not raw_currency:
        raw_state_currency = _coerce_mapping(raw_state.get("currency"))
        if _looks_like_xianxia_currency(raw_state_currency):
            raw_currency = raw_state_currency
    if not raw_currency:
        raw_currency = _coerce_mapping(payload.get("currency"))

    raw_inventory = _coerce_mapping(raw_state_xianxia.get("inventory"))
    if not raw_inventory:
        raw_inventory = _coerce_mapping(raw_state.get("inventory"))
    if not raw_inventory and isinstance(payload.get("inventory"), dict):
        raw_inventory = _coerce_mapping(payload.get("inventory"))

    state_payload: dict[str, Any] = {
        "vitals": {
            "current_hp": _coerce_int(
                _first_present_value(
                    [raw_vitals, raw_state],
                    ("current_hp", "hp_current"),
                ),
                default=_coerce_int(
                    _first_present_value([raw_state_xianxia, raw_state], ("hp_current",)),
                    default=None,
                ),
                # Keep None when no value is supplied so model-level defaults can
                # align currents to the adjusted definition maxima.
                # defaulting to a numeric value here can incorrectly pin the state.
            ),
            "temp_hp": _coerce_int(
                _first_present_value([raw_vitals, raw_state], ("temp_hp", "hp_temp")),
                default=0,
            ),
            "current_stance": _coerce_int(
                _first_present_value(
                    [raw_vitals, raw_state],
                    ("current_stance", "stance_current"),
                ),
                default=_coerce_int(
                    _first_present_value([raw_state_xianxia, raw_state], ("stance_current",)),
                    default=None,
                ),
                # Keep None when no explicit value is supplied to preserve state
                # defaults derived from adjusted maxima.
            ),
            "temp_stance": _coerce_int(
                _first_present_value([raw_vitals, raw_state], ("temp_stance", "stance_temp")),
                default=0,
            ),
        },
        "energies": {
            energy_key: {
                "current": _coerce_int(
                    _coerce_energy_current(
                        energy_key,
                        raw_energies,
                        raw_energies_current,
                        raw_state,
                    ),
                    # Leave state current unset when no value is supplied so
                    # normalize_xianxia_state_payload can restore it to
                    # definition maxima.
                    default=None,
                )
            }
            for energy_key in XIANXIA_ENERGY_KEYS
        },
        "yin_yang": {
            "yin_current": _coerce_int(
                _first_present_value(
                    [raw_yin_yang, raw_state],
                    ("yin_current",),
                ),
                default=None,
            ),
            "yang_current": _coerce_int(
                _first_present_value(
                    [raw_yin_yang, raw_state],
                    ("yang_current",),
                ),
                default=None,
            ),
        },
        "dao": {
            "current": _coerce_int(
                _first_present_value([raw_dao, raw_state], ("current", "dao_current")),
                default=0,
            )
        },
        "currency": _coerce_xianxia_currency_payload(
            payload,
            raw_currency=raw_currency,
            raw_state_xianxia=raw_state_xianxia,
        ),
        "inventory": {
            "enabled": False,
            "quantities": [],
        },
        "notes": {
            "player_notes_markdown": _coerce_text(
                _first_present_value(
                    [
                        _coerce_mapping(raw_state_xianxia.get("notes")),
                        _coerce_mapping(raw_state.get("notes")),
                        payload,
                    ],
                    ("player_notes_markdown", "player_notes", "notes_markdown"),
                )
            )
        },
    }
    active_stance = _coerce_text(
        _first_present_value([raw_state_xianxia, raw_state, payload], ("active_stance",))
    )
    if active_stance:
        state_payload["active_stance"] = {"name": active_stance}
    active_aura = _coerce_text(
        _first_present_value([raw_state_xianxia, raw_state, payload], ("active_aura",))
    )
    if active_aura:
        state_payload["active_aura"] = {"name": active_aura}

    raw_quantities = (
        raw_inventory.get("quantities")
        if isinstance(raw_inventory.get("quantities"), (list, tuple, dict, str))
        else raw_inventory.get("item_quantities")
    )
    if not raw_quantities:
        raw_quantities = _coerce_inventory_rows_from_form(payload)
    if not raw_quantities and payload.get("inventory_text") is not None:
        raw_quantities = _parse_inventory_text(payload.get("inventory_text"))
    if raw_quantities is not None:
        quantities = _coerce_inventory_quantities(raw_quantities)
        state_payload["inventory"] = {
            "enabled": bool(quantities),
            "quantities": quantities,
        }

    return state_payload


def _coerce_xianxia_currency_payload(
    payload: dict[str, Any],
    *,
    raw_currency: dict[str, Any],
    raw_state_xianxia: dict[str, Any],
) -> dict[str, int]:
    mappings = [raw_currency, raw_state_xianxia, payload]
    aliases = {
        "coin": ("coin", "coins"),
        "supply": ("supply", "supplies"),
        "spirit_stones": ("spirit_stones", "spirit_stone", "spiritStones", "spirit stones"),
    }
    currency: dict[str, int] = {}
    for key in XIANXIA_CURRENCY_KEYS:
        currency[key] = _coerce_int(
            _first_present_value(mappings, aliases.get(key, (key,))),
            default=0,
        )
    return currency


def _looks_like_xianxia_currency(value: dict[str, Any]) -> bool:
    aliases = {
        "coin",
        "coins",
        "supply",
        "supplies",
        "spirit_stone",
        "spiritstones",
        "spirit_stones",
        "spirit stones",
        "spiritstones",
    }
    normalized_keys = {
        str(key or "").strip().casefold().replace(" ", "_")
        for key in dict(value or {})
    }
    return bool(normalized_keys & {alias.replace(" ", "_") for alias in aliases})


def _coerce_freeform_trained_skills(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    raw_xianxia = _coerce_mapping(payload.get("xianxia"))
    raw_skills = _coerce_mapping(raw_xianxia.get("skills"))
    rows: list[Any] = []
    rows.extend(_coerce_record_values(payload.get("trained_skills")))
    rows.extend(_parse_skill_text(payload.get("trained_skills_text")))
    rows.extend(_parse_skill_text(payload.get("skills_text")))
    rows.extend(_coerce_record_values(raw_xianxia.get("trained_skills")))
    rows.extend(_coerce_record_values(raw_skills.get("trained")))
    rows.extend(_collect_indexed_records(payload, "trained_skill"))

    names: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()

    for row in rows:
        if isinstance(row, dict):
            name = _coerce_text(row.get("name") or row.get("label") or row.get("skill"))
            if not name:
                continue
            if name.casefold() not in seen:
                seen.add(name.casefold())
                names.append(name)
            note = _coerce_text(
                row.get("notes")
                or row.get("note")
                or row.get("description")
                or row.get("source_notes")
                or row.get("text"),
            )
            if note:
                notes.append(f"{name}: {note}")
            continue

        name = _coerce_text(row)
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)

    return names, notes


def _coerce_martial_arts_payload(
    payload: dict[str, Any],
    *,
    martial_art_options: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw_xianxia = _coerce_mapping(payload.get("xianxia"))
    rows: list[Any] = []
    rows.extend(_coerce_record_values(raw_xianxia.get("martial_arts")))
    rows.extend(_coerce_record_values(payload.get("martial_arts")))
    rows.extend(_parse_martial_arts_text(payload.get("martial_arts_text")))
    rows.extend(_collect_indexed_records(payload, "martial_art"))
    option_map = _build_martial_art_option_lookup(martial_art_options or [])

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, str):
            normalized.append({"name": _coerce_text(row)})
            continue
        if not isinstance(row, dict):
            continue
        source_row = deepcopy(row)
        selected_option = _match_martial_art_option(source_row, option_map)
        name = _coerce_text(
            source_row.get("name") or source_row.get("label") or source_row.get("title")
        )
        if selected_option and not name:
            name = _coerce_text(selected_option.get("title"))
        if not name:
            continue
        source_row["name"] = name

        systems_ref = source_row.get("systems_ref")
        if selected_option:
            name = _coerce_text(selected_option.get("title")) or name
            source_row["name"] = name
            source_row["systems_ref"] = _systems_ref_for_martial_art_option(selected_option)
            if selected_option.get("rank_records_status"):
                source_row["rank_records_status"] = _coerce_text(
                    selected_option.get("rank_records_status")
                )
            if selected_option.get("custom_martial_art"):
                source_row["custom_martial_art"] = True
                source_row["xianxia_custom_martial_art"] = True
            systems_ref = source_row["systems_ref"]
        if systems_ref is None and source_row.get("systems_ref_slug"):
            source_row["systems_ref"] = {"slug": _coerce_text(source_row.get("systems_ref_slug"))}
        elif isinstance(systems_ref, str):
            source_row["systems_ref"] = {"slug": _coerce_text(systems_ref)}

        rank_key = _coerce_text(
            source_row.get("current_rank_key")
            or source_row.get("current_rank")
            or source_row.get("rank")
            or source_row.get("rank_key"),
        )
        if rank_key:
            source_row["current_rank_key"] = _coerce_rank_key(rank_key)
            source_row["current_rank"] = _MARTIAL_ART_RANK_LABELS.get(
                source_row["current_rank_key"],
                _coerce_text(source_row.get("current_rank") or rank_key),
            )

        if source_row.get("learned_rank_refs") is not None:
            source_row["learned_rank_refs"] = [
                _coerce_text(item)
                for item in _coerce_record_values(source_row.get("learned_rank_refs"))
                if _coerce_text(item)
            ]
        elif selected_option and source_row.get("current_rank_key"):
            source_row["learned_rank_refs"] = _learned_rank_refs_for_option(
                selected_option,
                source_row["current_rank_key"],
            )

        notes = _coerce_text(
            source_row.get("notes")
            or source_row.get("note")
            or source_row.get("description")
            or source_row.get("source_notes"),
        )
        if notes:
            source_row["notes"] = notes

        teacher = _coerce_text(source_row.get("teacher"))
        if teacher:
            source_row["teacher"] = teacher
        breakthrough = _coerce_text(source_row.get("breakthrough"))
        if breakthrough:
            source_row["breakthrough"] = breakthrough

        normalized.append(source_row)

    return normalized


def _coerce_dao_immolating_payload(*, raw_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_xianxia = _coerce_mapping(raw_payload.get("xianxia"))
    raw_records = _coerce_mapping(raw_xianxia.get("dao_immolating_techniques"))
    if not raw_records and raw_xianxia.get("dao_immolating_records") is not None:
        raw_records = _coerce_mapping(raw_xianxia.get("dao_immolating_records"))

    if not isinstance(raw_records, dict):
        raw_records = {}

    return {
        "prepared": _coerce_named_records(raw_records.get("prepared")),
        "use_history": _coerce_named_records(
            raw_records.get("use_history")
            if "use_history" in raw_records
            else raw_records.get("history"),
        ),
    }


def _coerce_inventory_rows_from_form(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _collect_indexed_records(payload, "manual_item")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        name = _coerce_text(row.get("name"))
        if not name:
            continue
        parsed.append(
            {
                "name": name,
                "quantity": _coerce_int(row.get("quantity"), default=1),
                "notes": _coerce_text(row.get("notes")),
                "tags": _coerce_tags(row.get("tags")),
            }
        )
    return parsed


def _parse_skill_text(value: Any) -> list[Any]:
    rows: list[Any] = []
    for line in _split_text_lines(value):
        parts = _split_pipe_row(line)
        if not parts:
            continue
        if len(parts) == 1:
            rows.append(parts[0])
            continue
        rows.append({"name": parts[0], "notes": parts[1]})
    return rows


def _parse_martial_arts_text(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _split_text_lines(value):
        parts = _split_pipe_row(line)
        if not parts:
            continue
        row: dict[str, Any] = {"name": parts[0]}
        if len(parts) > 1:
            row["rank"] = parts[1]
        if len(parts) > 2:
            row["teacher"] = parts[2]
        if len(parts) > 3:
            row["breakthrough"] = parts[3]
        if len(parts) > 4:
            row["notes"] = " | ".join(parts[4:])
        rows.append(row)
    return rows


def _parse_inventory_text(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _split_text_lines(value):
        parts = _split_pipe_row(line)
        if not parts:
            continue
        row: dict[str, Any] = {"name": parts[0]}
        if len(parts) > 1:
            row["quantity"] = parts[1]
        if len(parts) > 2:
            row["tags"] = parts[2]
        if len(parts) > 3:
            row["notes"] = " | ".join(parts[3:])
        rows.append(row)
    return rows


def _coerce_inventory_quantities(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _coerce_record_values(value):
        if isinstance(item, dict):
            normalized = {
                "id": _coerce_text(item.get("id")),
                "catalog_ref": _coerce_text(item.get("catalog_ref")),
                "name": _coerce_text(item.get("name") or item.get("label")),
                "quantity": _coerce_int(item.get("quantity"), default=1),
                "notes": _coerce_text(item.get("notes") or item.get("note")),
                "tags": _coerce_tags(item.get("tags")),
            }
            records.append(
                {
                    key: value for key, value in normalized.items() if value or key == "quantity"
                }
            )
            continue

        records.append(
            {
                "name": _coerce_text(item),
                "quantity": 1,
            }
        )
    return [record for record in records if _coerce_text(record.get("name")) or _coerce_text(record.get("id"))]


def _coerce_named_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _coerce_record_values(value):
        if isinstance(item, dict):
            records.append(_coerce_mapping(item))
            continue
        value_text = _coerce_text(item)
        if value_text:
            records.append({"name": value_text})
    return records


def _coerce_reference_notes(payload: dict[str, Any]) -> dict[str, Any]:
    raw_reference = _coerce_mapping(payload.get("reference_notes"))
    if not raw_reference:
        raw_reference = _coerce_mapping(payload.get("notes"))
    return {
        "additional_notes_markdown": _coerce_text(
            raw_reference.get("additional_notes_markdown")
            or payload.get("additional_notes_markdown")
            or raw_reference.get("description")
            or raw_reference.get("notes")
            or "",
        ),
        "allies_and_organizations_markdown": _coerce_text(
            raw_reference.get("allies_and_organizations_markdown")
            or payload.get("allies_and_organizations_markdown")
            or "",
        ),
        "custom_sections": (
            raw_reference.get("custom_sections")
            if isinstance(raw_reference.get("custom_sections"), list)
            else []
        ),
    }


def _raise_maxima_to_preserve_current_values(
    definition_payload: dict[str, Any],
    state_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(definition_payload)

    payload["durability"] = {
        "hp_max": max(
            _coerce_int(payload.get("durability", {}).get("hp_max"), default=10),
            _coerce_int(state_payload.get("vitals", {}).get("current_hp"), default=0),
        ),
        "stance_max": max(
            _coerce_int(payload.get("durability", {}).get("stance_max"), default=10),
            _coerce_int(state_payload.get("vitals", {}).get("current_stance"), default=0),
        ),
        "manual_armor_bonus": _coerce_int(payload.get("durability", {}).get("manual_armor_bonus"), default=0),
    }

    payload["energies"] = {
        key: {
            "max": max(
                _coerce_int(payload.get("energies", {}).get(key, {}).get("max"), default=0),
                _coerce_int(state_payload.get("energies", {}).get(key, {}).get("current"), default=0),
            )
        }
        for key in XIANXIA_ENERGY_KEYS
    }

    payload["yin_yang"] = {
        "yin_max": max(
            _coerce_int(payload.get("yin_yang", {}).get("yin_max"), default=1),
            _coerce_int(state_payload.get("yin_yang", {}).get("yin_current"), default=0),
        ),
        "yang_max": max(
            _coerce_int(payload.get("yin_yang", {}).get("yang_max"), default=1),
            _coerce_int(state_payload.get("yin_yang", {}).get("yang_current"), default=0),
        ),
    }

    payload["dao"] = {
        "max": max(
            _coerce_int(payload.get("dao", {}).get("max"), default=3),
            _coerce_int(state_payload.get("dao", {}).get("current"), default=0),
        )
    }
    return payload


def _coerce_energy_maximum(
    key: str,
    sources: list[dict[str, Any]],
    energy_source: dict[str, Any],
) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        if key not in source:
            continue
        value = source.get(key)
        if isinstance(value, dict):
            return value.get("max")
        return value

    value = energy_source.get(key)
    if isinstance(value, dict):
        return value.get("max")
    return value


def _coerce_energy_current(
    key: str,
    energy_payload: dict[str, Any],
    energy_current_payload: dict[str, Any],
    raw_state_payload: dict[str, Any],
) -> Any:
    raw_energy = _coerce_mapping(energy_payload.get(key))
    if "current" in raw_energy:
        return raw_energy.get("current")
    if key in raw_energy:
        return raw_energy.get(key)
    if key in energy_current_payload:
        return energy_current_payload.get(key)
    return _first_present_value([raw_state_payload], (f"{key}_current",))


def _coerce_int_map(
    sources: list[dict[str, Any]],
    *,
    keys: tuple[str, ...],
    aliases: tuple[str, ...] = (),
) -> dict[str, int]:
    values: dict[str, int] = {}
    for key in keys:
        candidates = [key]
        candidates.extend(f"{alias}{key}" for alias in aliases)
        values[key] = _coerce_int(_first_present_value(sources, tuple(candidates)), default=0)
    return values


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _coerce_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_record_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    if value is None:
        return []
    return [value]


def _coerce_choice(
    value: Any,
    *,
    aliases: dict[str, str],
    default: str,
) -> str:
    return aliases.get(_coerce_text(value).casefold(), default)


def _coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    raw_values: list[Any]
    if isinstance(value, list):
        raw_values = list(value)
    elif isinstance(value, tuple):
        raw_values = list(value)
    elif isinstance(value, str):
        raw_values = value.split(",")
    else:
        raw_values = [value]
    return [_coerce_text(item) for item in raw_values if _coerce_text(item)]


def _split_text_lines(value: Any) -> list[str]:
    text = str(value or "")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _split_pipe_row(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("|")]


def _build_martial_art_option_lookup(
    options: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for option in options:
        if not isinstance(option, dict):
            continue
        for key in (
            option.get("slug"),
            option.get("title"),
            option.get("entry_key"),
        ):
            normalized = _lookup_key(key)
            if normalized:
                lookup[normalized] = option
    return lookup


def _match_martial_art_option(
    row: dict[str, Any],
    option_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    for key in (
        row.get("systems_ref_slug"),
        row.get("martial_art_slug"),
        row.get("slug"),
        row.get("entry_key"),
        row.get("name"),
    ):
        normalized = _lookup_key(key)
        if normalized and normalized in option_map:
            return option_map[normalized]
    systems_ref = row.get("systems_ref")
    if isinstance(systems_ref, dict):
        for key in (systems_ref.get("slug"), systems_ref.get("entry_key"), systems_ref.get("title")):
            normalized = _lookup_key(key)
            if normalized and normalized in option_map:
                return option_map[normalized]
    return None


def _systems_ref_for_martial_art_option(option: dict[str, Any]) -> dict[str, str]:
    return {
        key: _coerce_text(option.get(key))
        for key in ("library_slug", "source_id", "entry_key", "slug", "title", "entry_type")
        if _coerce_text(option.get(key))
    }


def _learned_rank_refs_for_option(option: dict[str, Any], current_rank_key: str) -> list[str]:
    rank_key = _coerce_rank_key(current_rank_key)
    if rank_key not in _MARTIAL_ART_RANK_ORDER:
        return []
    rank_refs = _coerce_mapping(option.get("rank_refs"))
    selected_index = _MARTIAL_ART_RANK_ORDER.index(rank_key)
    learned_refs: list[str] = []
    slug = _coerce_text(option.get("slug"))
    for learned_key in _MARTIAL_ART_RANK_ORDER[: selected_index + 1]:
        rank_ref = _coerce_text(rank_refs.get(learned_key))
        if not rank_ref and slug:
            rank_ref = f"xianxia:{slug}:{learned_key}"
        if rank_ref:
            learned_refs.append(rank_ref)
    return learned_refs


def _lookup_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _coerce_text(value).casefold())


def _coerce_rank_key(value: str) -> str:
    normalized = _coerce_text(value).replace("-", "_")
    return normalized.replace(" ", "_").lower()


def _collect_indexed_records(payload: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for raw_key, raw_value in payload.items():
        match = _INDEX_ROW_PREFIX.match(str(raw_key))
        if not match:
            continue
        if match.group(1).casefold() != prefix.casefold():
            continue
        row_number = int(match.group(2))
        if row_number <= 0:
            continue
        row = records.setdefault(row_number, {})
        suffix = match.group(3)
        if suffix:
            row[suffix] = raw_value
        else:
            row["name"] = raw_value
    return [records[row_number] for row_number in sorted(records)]


def _first_present_value(sources: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return source.get(key)
    return None


def _first_present(sources: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    return _first_present_value(sources, keys)


def _append_notes_section(base_notes: str, heading: str, lines: list[str]) -> str:
    normalized_lines = [_coerce_text(line) for line in lines if _coerce_text(line)]
    if not normalized_lines:
        return base_notes
    section = f"{heading}:\n" + "\n".join(f"- {line}" for line in normalized_lines)
    if not base_notes:
        return section
    return f"{base_notes}\n\n{section}"
