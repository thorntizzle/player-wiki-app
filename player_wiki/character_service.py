from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character_models import CharacterDefinition


class CharacterStateValidationError(ValueError):
    pass


def build_initial_state(definition: CharacterDefinition) -> dict[str, Any]:
    max_hp = int(definition.stats.get("max_hp") or 0)
    spell_slots = [
        {
            "level": int(slot.get("level") or 0),
            "max": int(slot.get("max_slots") or 0),
            "used": 0,
        }
        for slot in definition.spellcasting.get("slot_progression", [])
    ]

    resources = []
    for template in definition.resource_templates:
        max_value = template.get("max")
        current = template.get("initial_current", max_value if max_value is not None else 0)
        resources.append(
            {
                "id": template.get("id"),
                "label": template.get("label"),
                "category": template.get("category", "custom_progress"),
                "current": int(current or 0),
                "max": int(max_value) if max_value is not None else None,
                "reset_on": template.get("reset_on", "manual"),
                "reset_to": template.get("reset_to", "unchanged"),
                "rest_behavior": template.get("rest_behavior", "manual_only"),
                "notes": template.get("notes", ""),
                "display_order": int(template.get("display_order") or 0),
            }
        )

    inventory = []
    for item in definition.equipment_catalog:
        inventory.append(
            {
                "id": item.get("id"),
                "catalog_ref": item.get("id"),
                "name": item.get("name"),
                "quantity": int(item.get("default_quantity") or 0),
                "weight": item.get("weight"),
                "is_equipped": bool(item.get("is_equipped", False)),
                "is_attuned": bool(item.get("is_attuned", False)),
                "charges_current": item.get("charges_current"),
                "charges_max": item.get("charges_max"),
                "notes": item.get("notes", ""),
                "tags": list(item.get("tags") or []),
            }
        )

    return {
        "status": definition.status,
        "vitals": {
            "current_hp": max_hp,
            "temp_hp": 0,
            "death_saves": {"successes": 0, "failures": 0},
        },
        "resources": resources,
        "inventory": inventory,
        "currency": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []},
        "spell_slots": spell_slots,
        "attunement": {"max_attuned_items": 3, "attuned_item_refs": []},
        "notes": {
            "player_notes_markdown": "",
            "physical_description_markdown": "",
            "background_markdown": "",
            "session_notes": [],
        },
    }


def validate_state(definition: CharacterDefinition, state: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(state)
    vitals = dict(payload.get("vitals") or {})
    max_hp = int(definition.stats.get("max_hp") or 0)
    current_hp = int(vitals.get("current_hp") or 0)
    temp_hp = int(vitals.get("temp_hp") or 0)
    if current_hp < 0 or current_hp > max_hp:
        raise CharacterStateValidationError(
            f"current_hp must be between 0 and {max_hp}, got {current_hp}"
        )
    if temp_hp < 0:
        raise CharacterStateValidationError("temp_hp cannot be negative")
    payload["vitals"] = {
        "current_hp": current_hp,
        "temp_hp": temp_hp,
        "death_saves": {
            "successes": int((vitals.get("death_saves") or {}).get("successes") or 0),
            "failures": int((vitals.get("death_saves") or {}).get("failures") or 0),
        },
    }

    normalized_resources = []
    for resource in payload.get("resources") or []:
        current = int(resource.get("current") or 0)
        max_value = resource.get("max")
        max_int = int(max_value) if max_value is not None else None
        if current < 0:
            raise CharacterStateValidationError(
                f"resource '{resource.get('label')}' current value cannot be negative"
            )
        if max_int is not None and current > max_int:
            raise CharacterStateValidationError(
                f"resource '{resource.get('label')}' current value cannot exceed max"
            )
        normalized_resources.append(
            {
                "id": resource.get("id"),
                "label": resource.get("label"),
                "category": resource.get("category"),
                "current": current,
                "max": max_int,
                "reset_on": resource.get("reset_on", "manual"),
                "reset_to": resource.get("reset_to", "unchanged"),
                "rest_behavior": resource.get("rest_behavior", "manual_only"),
                "notes": resource.get("notes", ""),
                "display_order": int(resource.get("display_order") or 0),
            }
        )
    payload["resources"] = normalized_resources

    slot_limits = {
        int(slot.get("level") or 0): int(slot.get("max_slots") or 0)
        for slot in definition.spellcasting.get("slot_progression", [])
    }
    normalized_slots = []
    for slot in payload.get("spell_slots") or []:
        level = int(slot.get("level") or 0)
        max_slots = int(slot.get("max") or slot_limits.get(level) or 0)
        used = int(slot.get("used") or 0)
        if used < 0 or used > max_slots:
            raise CharacterStateValidationError(
                f"spell slot usage for level {level} must be between 0 and {max_slots}"
            )
        normalized_slots.append({"level": level, "max": max_slots, "used": used})
    payload["spell_slots"] = normalized_slots

    normalized_inventory = []
    for item in payload.get("inventory") or []:
        quantity = int(item.get("quantity") or 0)
        if quantity < 0:
            raise CharacterStateValidationError(
                f"inventory quantity for '{item.get('name')}' cannot be negative"
            )
        normalized_inventory.append(
            {
                "id": item.get("id"),
                "catalog_ref": item.get("catalog_ref"),
                "name": item.get("name"),
                "quantity": quantity,
                "weight": item.get("weight"),
                "is_equipped": bool(item.get("is_equipped", False)),
                "is_attuned": bool(item.get("is_attuned", False)),
                "charges_current": item.get("charges_current"),
                "charges_max": item.get("charges_max"),
                "notes": item.get("notes", ""),
                "tags": list(item.get("tags") or []),
            }
        )
    payload["inventory"] = normalized_inventory

    currency = dict(payload.get("currency") or {})
    normalized_currency = {
        "cp": int(currency.get("cp") or 0),
        "sp": int(currency.get("sp") or 0),
        "ep": int(currency.get("ep") or 0),
        "gp": int(currency.get("gp") or 0),
        "pp": int(currency.get("pp") or 0),
        "other": list(currency.get("other") or []),
    }
    for key in ("cp", "sp", "ep", "gp", "pp"):
        if normalized_currency[key] < 0:
            raise CharacterStateValidationError(f"currency '{key}' cannot be negative")
    payload["currency"] = normalized_currency

    payload["attunement"] = {
        "max_attuned_items": int((payload.get("attunement") or {}).get("max_attuned_items") or 3),
        "attuned_item_refs": list((payload.get("attunement") or {}).get("attuned_item_refs") or []),
    }
    payload["notes"] = {
        "player_notes_markdown": str((payload.get("notes") or {}).get("player_notes_markdown") or ""),
        "physical_description_markdown": str(
            (payload.get("notes") or {}).get("physical_description_markdown") or ""
        ),
        "background_markdown": str((payload.get("notes") or {}).get("background_markdown") or ""),
        "session_notes": list((payload.get("notes") or {}).get("session_notes") or []),
    }
    payload["status"] = str(payload.get("status") or definition.status)
    return payload
