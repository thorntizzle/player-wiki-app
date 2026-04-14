from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character_models import CharacterDefinition
from .character_spell_slots import (
    normalize_spell_slot_lane_id,
    spell_slot_lanes_from_spellcasting,
    spell_slot_state_entries_from_spellcasting,
)

MANAGED_CUSTOM_TRACKER_PREFIX = "manual-feature-tracker:"


class CharacterStateValidationError(ValueError):
    pass


def build_resource_state(template: dict[str, Any]) -> dict[str, Any]:
    max_value = template.get("max")
    current = template.get("initial_current", max_value if max_value is not None else 0)
    return {
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


def build_inventory_state(item: dict[str, Any], *, quantity: int | None = None) -> dict[str, Any]:
    resolved_quantity = item.get("default_quantity") if quantity is None else quantity
    return {
        "id": item.get("id"),
        "catalog_ref": item.get("id"),
        "name": item.get("name"),
        "quantity": int(resolved_quantity or 0),
        "weight": item.get("weight"),
        "is_equipped": bool(item.get("is_equipped", False)),
        "is_attuned": bool(item.get("is_attuned", False)),
        "charges_current": item.get("charges_current"),
        "charges_max": item.get("charges_max"),
        "notes": item.get("notes", ""),
        "tags": list(item.get("tags") or []),
    }


def _inventory_item_ref(item: dict[str, Any]) -> str:
    return str(item.get("catalog_ref") or item.get("id") or "").strip()


def _normalize_attunement_state(
    attunement: dict[str, Any] | None,
    inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    max_attuned_items = int((attunement or {}).get("max_attuned_items") or 3)
    attuned_item_refs: list[str] = []
    seen_refs: set[str] = set()
    for item in list(inventory or []):
        item_ref = _inventory_item_ref(item)
        if not item_ref or not bool(item.get("is_attuned", False)) or item_ref in seen_refs:
            continue
        seen_refs.add(item_ref)
        attuned_item_refs.append(item_ref)
    return {
        "max_attuned_items": max(0, max_attuned_items),
        "attuned_item_refs": attuned_item_refs,
    }


def build_initial_state(definition: CharacterDefinition) -> dict[str, Any]:
    max_hp = int(definition.stats.get("max_hp") or 0)
    spell_slots = spell_slot_state_entries_from_spellcasting(definition.spellcasting)

    resources = [build_resource_state(template) for template in definition.resource_templates]

    inventory = []
    currency = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []}
    for item in definition.equipment_catalog:
        item_currency = dict(item.get("currency") or {})
        for denomination in ("cp", "sp", "ep", "gp", "pp"):
            currency[denomination] = int(currency.get(denomination) or 0) + int(item_currency.get(denomination) or 0)
        if bool(item.get("is_currency_only")):
            continue
        inventory.append(build_inventory_state(item))

    return {
        "status": definition.status,
        "vitals": {
            "current_hp": max_hp,
            "temp_hp": 0,
            "death_saves": {"successes": 0, "failures": 0},
        },
        "resources": resources,
        "inventory": inventory,
        "currency": currency,
        "spell_slots": spell_slots,
        "attunement": _normalize_attunement_state({"max_attuned_items": 3}, inventory),
        "notes": {
            "player_notes_markdown": "",
            "physical_description_markdown": "",
            "background_markdown": "",
            "session_notes": [],
        },
    }


def merge_state_with_definition(
    definition: CharacterDefinition,
    state: dict[str, Any],
    *,
    hp_delta: int = 0,
    inventory_quantity_overrides: dict[str, int] | None = None,
    inventory_state_overrides: dict[str, dict[str, Any]] | None = None,
    removed_resource_ids: set[str] | None = None,
) -> dict[str, Any]:
    payload = deepcopy(state)
    existing_resources = list(payload.get("resources") or [])
    removed_managed_resources = {
        str(resource_id).strip()
        for resource_id in set(removed_resource_ids or set())
        if str(resource_id).strip()
    }
    template_resource_ids: set[str] = set()
    existing_by_id = {
        str(resource.get("id") or "").strip(): resource
        for resource in existing_resources
        if str(resource.get("id") or "").strip()
    }
    merged_resources: list[dict[str, Any]] = []

    for template in definition.resource_templates:
        template_resource = build_resource_state(template)
        resource_id = str(template_resource.get("id") or "").strip()
        if not resource_id:
            merged_resources.append(template_resource)
            continue
        template_resource_ids.add(resource_id)
        existing_resource = existing_by_id.get(resource_id)
        if existing_resource is None:
            merged_resources.append(template_resource)
            continue

        preserved_current = int(existing_resource.get("current") or 0)
        max_value = template_resource.get("max")
        template_resource["current"] = (
            max(0, min(preserved_current, int(max_value)))
            if max_value is not None
            else max(0, preserved_current)
        )
        merged_resources.append(template_resource)

    for resource in existing_resources:
        resource_id = str(resource.get("id") or "").strip()
        if resource_id and resource_id in template_resource_ids:
            continue
        if resource_id.startswith(MANAGED_CUSTOM_TRACKER_PREFIX):
            continue
        if resource_id and resource_id in removed_managed_resources:
            continue
        merged_resources.append(deepcopy(resource))

    payload["resources"] = merged_resources
    existing_slots = [dict(slot or {}) for slot in list(payload.get("spell_slots") or []) if isinstance(slot, dict)]
    existing_slots_by_key = {
        (
            normalize_spell_slot_lane_id(slot.get("slot_lane_id")),
            int(slot.get("level") or 0),
        ): dict(slot)
        for slot in existing_slots
        if int(slot.get("level") or 0) > 0
    }
    legacy_slots_by_level: dict[int, list[dict[str, Any]]] = {}
    for slot in existing_slots:
        level = int(slot.get("level") or 0)
        if level <= 0 or normalize_spell_slot_lane_id(slot.get("slot_lane_id")):
            continue
        legacy_slots_by_level.setdefault(level, []).append(dict(slot))
    merged_slots: list[dict[str, Any]] = []
    tracked_slot_keys: set[tuple[str, int]] = set()
    tracked_slot_levels: set[int] = set()
    for lane in spell_slot_lanes_from_spellcasting(definition.spellcasting):
        lane_id = normalize_spell_slot_lane_id(lane.get("id"))
        for slot in list(lane.get("slot_progression") or []):
            level = int(slot.get("level") or 0)
            max_slots = int(slot.get("max_slots") or 0)
            slot_key = (lane_id, level)
            tracked_slot_keys.add(slot_key)
            tracked_slot_levels.add(level)
            existing_slot = existing_slots_by_key.get(slot_key)
            if existing_slot is None and legacy_slots_by_level.get(level):
                existing_slot = legacy_slots_by_level[level].pop(0)
            used_slots = int((existing_slot or {}).get("used") or 0)
            merged_slot = {
                "level": level,
                "max": max_slots,
                "used": max(0, min(used_slots, max_slots)),
            }
            if lane_id:
                merged_slot["slot_lane_id"] = lane_id
            merged_slots.append(merged_slot)
    for slot in existing_slots:
        lane_id = normalize_spell_slot_lane_id(slot.get("slot_lane_id"))
        level = int(slot.get("level") or 0)
        slot_key = (lane_id, level)
        if slot_key in tracked_slot_keys:
            continue
        if not lane_id and level in tracked_slot_levels:
            continue
        merged_slots.append(deepcopy(slot))
    payload["spell_slots"] = merged_slots

    quantity_overrides = {
        str(key).strip(): int(value)
        for key, value in dict(inventory_quantity_overrides or {}).items()
        if str(key).strip()
    }
    state_overrides = {
        str(key).strip(): dict(value)
        for key, value in dict(inventory_state_overrides or {}).items()
        if str(key).strip()
    }
    existing_inventory = list(payload.get("inventory") or [])
    existing_inventory_by_ref = {
        _inventory_item_ref(item): dict(item)
        for item in existing_inventory
        if _inventory_item_ref(item)
    }
    tracked_inventory_refs: set[str] = set()
    merged_inventory: list[dict[str, Any]] = []
    for catalog_item in list(definition.equipment_catalog or []):
        if bool(catalog_item.get("is_currency_only")):
            continue
        catalog_ref = str(catalog_item.get("id") or "").strip()
        if not catalog_ref:
            continue
        tracked_inventory_refs.add(catalog_ref)
        existing_item = existing_inventory_by_ref.get(catalog_ref)
        quantity = int(quantity_overrides.get(catalog_ref, (existing_item or {}).get("quantity") or catalog_item.get("default_quantity") or 0))
        merged_item = build_inventory_state(catalog_item, quantity=quantity)
        if existing_item is not None:
            merged_item["is_equipped"] = bool(existing_item.get("is_equipped", merged_item.get("is_equipped", False)))
            merged_item["is_attuned"] = bool(existing_item.get("is_attuned", merged_item.get("is_attuned", False)))
            merged_item["charges_current"] = existing_item.get("charges_current", merged_item.get("charges_current"))
            merged_item["charges_max"] = existing_item.get("charges_max", merged_item.get("charges_max"))
        item_state_override = state_overrides.get(catalog_ref)
        if item_state_override:
            if "is_equipped" in item_state_override:
                merged_item["is_equipped"] = bool(item_state_override.get("is_equipped"))
            if "is_attuned" in item_state_override:
                merged_item["is_attuned"] = bool(item_state_override.get("is_attuned"))
        merged_inventory.append(merged_item)

    for item in existing_inventory:
        catalog_ref = _inventory_item_ref(item)
        if catalog_ref and catalog_ref in tracked_inventory_refs:
            continue
        if catalog_ref:
            continue
        merged_inventory.append(deepcopy(item))
    payload["inventory"] = merged_inventory
    payload["attunement"] = _normalize_attunement_state(payload.get("attunement"), merged_inventory)

    vitals = dict(payload.get("vitals") or {})
    current_hp = int(vitals.get("current_hp") or 0)
    max_hp = int((definition.stats or {}).get("max_hp") or 0)
    if hp_delta:
        current_hp += int(hp_delta)
    vitals["current_hp"] = max(0, min(current_hp, max_hp))
    payload["vitals"] = vitals
    return payload


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
        (
            normalize_spell_slot_lane_id(lane.get("id")),
            int(slot.get("level") or 0),
        ): int(slot.get("max_slots") or 0)
        for lane in spell_slot_lanes_from_spellcasting(definition.spellcasting)
        for slot in list(lane.get("slot_progression") or [])
    }
    normalized_slots = []
    for slot in payload.get("spell_slots") or []:
        lane_id = normalize_spell_slot_lane_id(slot.get("slot_lane_id"))
        level = int(slot.get("level") or 0)
        max_slots = int(slot.get("max") or slot_limits.get((lane_id, level)) or 0)
        used = int(slot.get("used") or 0)
        if used < 0 or used > max_slots:
            lane_label = f" in slot lane '{lane_id}'" if lane_id else ""
            raise CharacterStateValidationError(
                f"spell slot usage for level {level}{lane_label} must be between 0 and {max_slots}"
            )
        normalized_slot = {"level": level, "max": max_slots, "used": used}
        if lane_id:
            normalized_slot["slot_lane_id"] = lane_id
        normalized_slots.append(normalized_slot)
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

    payload["attunement"] = _normalize_attunement_state(payload.get("attunement"), normalized_inventory)
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
