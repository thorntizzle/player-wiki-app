from __future__ import annotations

import re
from typing import Any, Callable

from .xianxia_character_builder import (
    XIANXIA_MARTIAL_ART_IMPORT_RANKS,
    list_xianxia_manual_import_martial_art_options,
)
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_ENERGY_KEYS,
)


def normalize_xianxia_manual_import_values(values: dict[str, object] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in dict(values or {}).items():
        if isinstance(value, list):
            normalized[str(key)] = [str(item or "") for item in value]
        elif value is None:
            normalized[str(key)] = ""
        else:
            normalized[str(key)] = str(value)
    return normalized


def build_xianxia_manual_import_martial_art_rows(values: dict[str, Any]) -> list[dict[str, object]]:
    row_numbers: set[int] = set()
    row_pattern = re.compile(r"^martial_art_(\d+)_(slug|name|rank|teacher|breakthrough|notes)$")
    for key in values:
        match = row_pattern.match(str(key))
        if match:
            row_number = int(match.group(1))
            if row_number > 0:
                row_numbers.add(row_number)
    row_count = max(max(row_numbers, default=0), 3)
    return [
        {
            "index": index,
            "slug_input_name": f"martial_art_{index}_slug",
            "name_input_name": f"martial_art_{index}_name",
            "rank_input_name": f"martial_art_{index}_rank",
            "teacher_input_name": f"martial_art_{index}_teacher",
            "breakthrough_input_name": f"martial_art_{index}_breakthrough",
            "notes_input_name": f"martial_art_{index}_notes",
            "selected_slug": values.get(f"martial_art_{index}_slug", ""),
            "name": values.get(f"martial_art_{index}_name", ""),
            "rank": values.get(f"martial_art_{index}_rank", ""),
            "teacher": values.get(f"martial_art_{index}_teacher", ""),
            "breakthrough": values.get(f"martial_art_{index}_breakthrough", ""),
            "notes": values.get(f"martial_art_{index}_notes", ""),
        }
        for index in range(1, row_count + 1)
    ]


def build_xianxia_manual_import_context(
    *,
    systems_service,
    campaign_slug: str,
    values: dict[str, object] | None = None,
    preview: dict[str, object] | None = None,
    json_safe: Callable[[object], object] | None = None,
) -> dict[str, object]:
    normalized_values = normalize_xianxia_manual_import_values(values)
    martial_art_options = list_xianxia_manual_import_martial_art_options(
        systems_service=systems_service,
        campaign_slug=campaign_slug,
    )
    if json_safe is not None:
        martial_art_options = json_safe(martial_art_options)
    return {
        "values": normalized_values,
        "realm_choices": ("Mortal", "Immortal", "Divine"),
        "honor_choices": ("Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"),
        "martial_art_rank_choices": list(XIANXIA_MARTIAL_ART_IMPORT_RANKS),
        "martial_art_rows": build_xianxia_manual_import_martial_art_rows(normalized_values),
        "attribute_fields": [
            {
                "key": key,
                "label": XIANXIA_ATTRIBUTE_LABELS[key],
                "input_name": f"attribute_{key}",
                "value": normalized_values.get(f"attribute_{key}", "0"),
            }
            for key in XIANXIA_ATTRIBUTE_KEYS
        ],
        "effort_fields": [
            {
                "key": key,
                "label": XIANXIA_EFFORT_LABELS[key],
                "input_name": f"effort_{key}",
                "value": normalized_values.get(f"effort_{key}", "0"),
            }
            for key in XIANXIA_EFFORT_KEYS
        ],
        "energy_fields": [
            {
                "key": key,
                "label": key.title(),
                "max_input_name": f"energy_{key}_max",
                "max_value": normalized_values.get(f"energy_{key}_max", "0"),
            }
            for key in XIANXIA_ENERGY_KEYS
        ],
        "martial_art_options": martial_art_options,
        "preview": preview,
    }


def build_xianxia_manual_import_payload(values: dict[str, object]) -> dict[str, object]:
    ignored_inputs = {"active_stance", "active_aura"}
    normalized_values = {
        key: str(value or "")
        for key, value in dict(values or {}).items()
        if key not in ignored_inputs
    }
    payload: dict[str, object] = dict(normalized_values)
    payload["energy_maxima"] = {
        key: normalized_values.get(f"energy_{key}_max", "")
        for key in XIANXIA_ENERGY_KEYS
    }
    payload["state"] = {
        "xianxia": {
            "currency": {
                "coin": normalized_values.get("coin", ""),
                "supply": normalized_values.get("supply", ""),
                "spirit_stones": normalized_values.get("spirit_stones", ""),
            },
            "notes": {
                "player_notes_markdown": normalized_values.get("player_notes_markdown", ""),
            },
        },
    }
    return payload


def build_xianxia_manual_import_preview(definition, initial_state: dict[str, object]) -> dict[str, object]:
    xianxia = dict(getattr(definition, "xianxia", {}) or {})
    state_xianxia = dict(initial_state.get("xianxia") or {})
    inventory = dict(state_xianxia.get("inventory") or {})
    return {
        "name": definition.name,
        "slug": definition.character_slug,
        "realm": xianxia.get("realm"),
        "actions_per_turn": xianxia.get("actions_per_turn"),
        "trained_skill_count": len(list(dict(xianxia.get("skills") or {}).get("trained") or [])),
        "martial_art_count": len(list(xianxia.get("martial_arts") or [])),
        "inventory_count": len(list(inventory.get("quantities") or [])),
        "hp": dict(state_xianxia.get("vitals") or {}).get("current_hp"),
        "hp_max": dict(xianxia.get("durability") or {}).get("hp_max"),
        "stance": dict(state_xianxia.get("vitals") or {}).get("current_stance"),
        "stance_max": dict(xianxia.get("durability") or {}).get("stance_max"),
    }
