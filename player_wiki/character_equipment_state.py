from __future__ import annotations

from typing import Any

from .character_builder_equipment import (
    _normalize_equipment_payloads,
    _normalize_weapon_wield_mode_value,
    describe_equipment_state_support,
)
from .character_editor import CharacterEditValidationError, apply_equipment_state_edit
from .character_mechanics_projection import build_character_inventory_item_ref


def build_record_equipment_support_lookup(
    record: Any,
    *,
    item_catalog: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    normalized_definition_equipment = _normalize_equipment_payloads(
        list(record.definition.equipment_catalog or []),
        item_catalog=item_catalog,
    )
    definition_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in normalized_definition_equipment
        if str(item.get("id") or "").strip()
    }
    support_lookup: dict[str, dict[str, object]] = {}
    for inventory_item in list((record.state_record.state or {}).get("inventory") or []):
        item_ref = build_character_inventory_item_ref(inventory_item)
        if not item_ref:
            continue
        definition_item = dict(definition_item_lookup.get(item_ref) or {})
        support_item = dict(definition_item or inventory_item or {})
        if not str(support_item.get("name") or "").strip():
            support_item["name"] = str(dict(inventory_item or {}).get("name") or "").strip()
        support_lookup[item_ref] = describe_equipment_state_support(
            support_item,
            item_catalog=item_catalog,
        )
    return definition_item_lookup, support_lookup


def build_equipment_state_update_result(
    campaign_slug: str,
    record: Any,
    item_id: str,
    *,
    item_catalog: dict[str, object],
    systems_service: Any,
    values: dict[str, object],
):
    inventory_by_ref = {
        build_character_inventory_item_ref(item): dict(item)
        for item in list((record.state_record.state or {}).get("inventory") or [])
        if build_character_inventory_item_ref(item)
    }
    if item_id not in inventory_by_ref:
        raise CharacterEditValidationError("Choose a valid equipment entry to update.")
    _, support_lookup = build_record_equipment_support_lookup(
        record,
        item_catalog=item_catalog,
    )
    target_support = dict(support_lookup.get(item_id) or {})
    if not bool(target_support.get("supports_equipped_state")):
        raise CharacterEditValidationError(
            "That inventory row stays on Inventory because it does not support equipment state."
        )

    value_payload = dict(values or {})
    weapon_wield_mode = ""
    if bool(target_support.get("supports_weapon_wield_mode")):
        weapon_wield_mode = _normalize_weapon_wield_mode_value(value_payload.get("weapon_wield_mode"))
        allowed_modes = [
            _normalize_weapon_wield_mode_value(value)
            for value in list(target_support.get("weapon_wield_modes") or [])
            if _normalize_weapon_wield_mode_value(value)
        ]
        allowed_mode_set = set(allowed_modes)
        if weapon_wield_mode and weapon_wield_mode not in allowed_mode_set:
            raise CharacterEditValidationError("Choose a valid wielding mode for that weapon.")
        if not weapon_wield_mode and bool(value_payload.get("is_equipped")) and allowed_modes:
            weapon_wield_mode = allowed_modes[0]
        is_equipped = bool(weapon_wield_mode)
    else:
        is_equipped = bool(value_payload.get("is_equipped"))

    requested_attunement = bool(value_payload.get("is_attuned"))
    if requested_attunement and not bool(target_support.get("supports_attunement")):
        raise CharacterEditValidationError(
            "Only items whose durable metadata explicitly requires attunement can be attuned."
        )
    is_attuned = bool(requested_attunement and target_support.get("supports_attunement"))
    attunement_payload = dict((record.state_record.state or {}).get("attunement") or {})
    max_attuned_items = int(attunement_payload.get("max_attuned_items") or 3)
    currently_attuned_refs = {
        item_ref
        for item_ref, item in inventory_by_ref.items()
        if (
            item_ref != item_id
            and bool(item.get("is_attuned", False))
            and bool(dict(support_lookup.get(item_ref) or {}).get("supports_attunement"))
        )
    }
    next_attuned_count = len(currently_attuned_refs) + (1 if is_attuned else 0)
    if max_attuned_items >= 0 and next_attuned_count > max_attuned_items:
        raise CharacterEditValidationError(
            f"This character already has {max_attuned_items} attuned item"
            f"{'' if max_attuned_items == 1 else 's'}. Clear one first."
        )

    definition, import_metadata = apply_equipment_state_edit(
        campaign_slug,
        record.definition,
        record.import_metadata,
        item_catalog=item_catalog,
        systems_service=systems_service,
        target_item_id=item_id,
        is_equipped=is_equipped,
        is_attuned=is_attuned,
        weapon_wield_mode=weapon_wield_mode,
    )
    return (
        definition,
        import_metadata,
        {},
        {
            item_id: {
                "is_equipped": is_equipped,
                "is_attuned": is_attuned,
                "weapon_wield_mode": weapon_wield_mode,
            }
        },
    )
