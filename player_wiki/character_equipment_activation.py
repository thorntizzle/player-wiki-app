"""DND equipment activation identity and read-only effective projection.

The definition remains historical evidence.  Only exact, unique inventory IDs
can supply activation to a definition row; an absent state field may be seeded
from legacy YAML, while an explicit false or empty value always wins.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from typing import Any

from .system_policy import is_xianxia_system


ACTIVATION_FIELDS = ("is_equipped", "is_attuned", "weapon_wield_mode")
ACTIVATION_SCHEMA_VERSION = 1


def activation_marker(definition: Any) -> dict[str, Any]:
    payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    return {"schema_version": ACTIVATION_SCHEMA_VERSION,
            "known_definition_ids": sorted({str(item.get("id") or "").strip()
                                            for item in list(payload.get("equipment_catalog") or [])
                                            if isinstance(item, dict) and item.get("id") and not item.get("is_currency_only")})}


def definition_digest(definition: Any) -> str:
    payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def update_safe_definition(definition: Any) -> dict[str, Any]:
    payload = deepcopy(definition.to_dict() if hasattr(definition, "to_dict") else definition)
    if not is_xianxia_system(payload.get("system")):
        for item in list(payload.get("equipment_catalog") or []):
            if isinstance(item, dict):
                for field in ACTIVATION_FIELDS:
                    item.pop(field, None)
    return payload


def has_legacy_activation_fields(payload: dict[str, Any]) -> bool:
    if is_xianxia_system(payload.get("system")):
        return False
    return any(
        isinstance(item, dict) and any(field in item for field in ACTIVATION_FIELDS)
        for item in list(payload.get("equipment_catalog") or [])
    )


def analyze_activation(definition: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Report every row and every identity hazard without guessing a remap."""
    definition_payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    if is_xianxia_system(definition_payload.get("system")):
        return {"rows": [], "warnings": [], "blocked": False}
    definition_rows = [item for item in list(definition_payload.get("equipment_catalog") or [])
                       if isinstance(item, dict) and not item.get("is_currency_only")]
    state_rows = list((state or {}).get("inventory") or [])
    marker = dict((state or {}).get("equipment_activation") or {})
    known_ids = marker.get("known_definition_ids")
    marker_valid = (
        marker.get("schema_version") == ACTIVATION_SCHEMA_VERSION
        and isinstance(known_ids, list)
        and all(isinstance(value, str) and value.strip() == value and value for value in known_ids)
        and len(known_ids) == len(set(known_ids))
    )
    definition_ids = [str(item.get("id") or "").strip() for item in definition_rows]
    state_ids = [str(item.get("catalog_ref") or item.get("id") or "").strip()
                 if isinstance(item, dict) else "" for item in state_rows]
    definition_counts, state_counts = Counter(definition_ids), Counter(state_ids)
    definition_by_id = {str(item.get("id") or "").strip(): item for item in definition_rows}
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    if not marker_valid:
        warnings.append({"code": "activation_migration_required", "message":
                         "Equipment activation state needs migration or marker repair before edits."})
    for index, item in enumerate(state_rows):
        if not isinstance(item, dict):
            rows.append({"source": "sqlite", "index": index, "id": "",
                         "definition": None, "state": None, "status": "malformed_inventory_row"})
            warnings.append({"code": "malformed_inventory_row", "message":
                             f"Equipment inventory row {index} is malformed and needs separate repair."})
            continue
        if item.get("unlinked_activation_discarded"):
            rows.append({"source": "sqlite", "index": index,
                         "id": str(item.get("id") or ""), "definition": None,
                         "state": deepcopy(item), "status": "discarded_unlinked"})
            continue
        item_ref = state_ids[index]
        explicit_id = str(item.get("id") or "").strip()
        explicit_ref = str(item.get("catalog_ref") or "").strip()
        reason = ""
        if explicit_id and explicit_ref and explicit_id != explicit_ref:
            reason = "conflicting_id_and_catalog_ref"
        elif not item_ref:
            reason = "missing_state_id"
        elif state_counts[item_ref] != 1:
            reason = "duplicate_state_id"
        elif definition_counts[item_ref] != 1:
            reason = "orphan_or_duplicate_definition_id"
        elif marker_valid and not all(field in item for field in ACTIVATION_FIELDS):
            reason = "partial_activation_row"
        rows.append({"source": "sqlite", "index": index, "id": item_ref,
                     "definition": deepcopy(definition_by_id.get(item_ref)),
                     "state": deepcopy(item), "status": reason or "exact"})
        if reason:
            warnings.append({"code": reason, "message":
                             f"Equipment activation for {item_ref or 'an unnamed row'} needs manager repair."})
    for index, item in enumerate(definition_rows):
        item_ref = definition_ids[index]
        if not item_ref or definition_counts[item_ref] != 1:
            reason = "missing_or_duplicate_definition_id"
        elif state_counts[item_ref] == 0:
            reason = "new_definition_row" if (
                marker_valid and item_ref not in set(known_ids)
            ) else "missing_state_row"
        else:
            continue
        rows.append({"source": "definition", "index": index, "id": item_ref,
                     "definition": deepcopy(item), "state": None, "status": reason})
        warnings.append({"code": reason, "message":
                         f"Equipment activation for {item_ref or 'an unnamed row'} needs manager repair."})
    return {"rows": rows, "warnings": warnings, "blocked": bool(warnings)}


def effective_definition(definition: Any, state: dict[str, Any]) -> tuple[Any, list[dict[str, str]]]:
    """Overlay only unambiguous SQLite activation on an unsaved definition copy."""
    from .character_models import CharacterDefinition

    payload = deepcopy(definition.to_dict() if hasattr(definition, "to_dict") else definition)
    if is_xianxia_system(payload.get("system")):
        return definition, []
    analysis = analyze_activation(payload, state)
    exact = {row["id"]: row["state"] for row in analysis["rows"]
             if row["source"] == "sqlite" and row["status"] == "exact"}
    for item in list(payload.get("equipment_catalog") or []):
        if not isinstance(item, dict):
            continue
        item_ref = str(item.get("id") or "").strip()
        state_item = exact.get(item_ref)
        if state_item is None:
            # An unresolved source cannot retain automatic YAML activation.
            item["is_equipped"] = False
            item["is_attuned"] = False
            item.pop("weapon_wield_mode", None)
            continue
        item["is_equipped"] = bool(state_item.get("is_equipped", False))
        item["is_attuned"] = bool(state_item.get("is_attuned", False))
        mode = str(state_item.get("weapon_wield_mode") or "").strip()
        if mode:
            item["weapon_wield_mode"] = mode
        else:
            item.pop("weapon_wield_mode", None)
    return CharacterDefinition.from_dict(payload), analysis["warnings"]


def reconcile_equipment_state_for_raw_update(definition: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Add only proven new DND inventory rows to an otherwise unchanged state."""
    from .character_service import CharacterStateValidationError, build_inventory_state

    analysis = analyze_activation(definition, state)
    unresolved = [warning for warning in analysis["warnings"]
                  if warning["code"] != "new_definition_row"]
    if unresolved:
        raise CharacterStateValidationError(
            "Equipment activation identity needs manager repair before this raw Character update."
        )
    result = deepcopy(state)
    definition_rows = [item for item in list(definition.equipment_catalog or [])
                       if isinstance(item, dict) and not item.get("is_currency_only")]
    for row in analysis["rows"]:
        if row["source"] == "definition" and row["status"] == "new_definition_row":
            result.setdefault("inventory", []).append(
                build_inventory_state(definition_rows[row["index"]])
            )
    result["equipment_activation"] = activation_marker(definition)
    if analyze_activation(definition, result)["blocked"]:
        raise CharacterStateValidationError("Equipment activation identity changed during raw update preparation.")
    return result


def _normalized_item_page_ref(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("page_ref") or value.get("slug") or value.get("page_slug")
    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    if normalized.lower().endswith(".md"):
        normalized = normalized[:-3]
    return normalized.casefold()


def _eligible_item_page_refs(records: list[Any] | None) -> set[str]:
    from .campaign_item_mechanics import (
        campaign_item_mechanics_is_approved, is_campaign_item_mechanics_metadata,
    )

    eligible: set[str] = set()
    for record in list(records or []):
        page = record.get("page") if isinstance(record, dict) else getattr(record, "page", None)
        section = page.get("section") if isinstance(page, dict) else getattr(page, "section", "")
        published = page.get("published") if isinstance(page, dict) else getattr(page, "published", False)
        if str(section or "").strip() != "Items" or not bool(published):
            continue
        metadata = record.get("metadata") if isinstance(record, dict) else getattr(record, "metadata", {})
        metadata = dict(metadata or {})
        if is_campaign_item_mechanics_metadata(metadata) and not campaign_item_mechanics_is_approved(metadata):
            continue
        raw_refs = (
            record.get("page_ref") if isinstance(record, dict) else getattr(record, "page_ref", ""),
            page.get("route_slug") if isinstance(page, dict) else getattr(page, "route_slug", ""),
        )
        eligible.update(ref for raw in raw_refs if (ref := _normalized_item_page_ref(raw)))
    return eligible


def suppress_unresolved_linked_sources(
    definition: Any, campaign_slug: str, systems_service: Any | None,
    campaign_page_records: list[Any] | None = None,
) -> tuple[Any, list[dict[str, str]]]:
    """Prevent a disabled linked item from using embedded automatic effects."""
    from .character_models import CharacterDefinition
    from .campaign_item_mechanics import CAMPAIGN_ITEM_METADATA_KEYS

    payload = deepcopy(definition.to_dict())
    if is_xianxia_system(payload.get("system")):
        return definition, []
    warnings: list[dict[str, str]] = []
    eligible_page_refs = _eligible_item_page_refs(campaign_page_records)
    for item in list(payload.get("equipment_catalog") or []):
        if not isinstance(item, dict):
            continue
        ref = dict(item.get("systems_ref") or {})
        entry = None
        page_ref = _normalized_item_page_ref(item.get("page_ref"))
        page_unavailable = bool(page_ref and page_ref not in eligible_page_refs)
        if systems_service is not None:
            key = str(ref.get("entry_key") or "").strip()
            slug = str(ref.get("slug") or "").strip()
            if key and hasattr(systems_service, "get_entry_for_campaign"):
                entry = systems_service.get_entry_for_campaign(campaign_slug, key)
            if not key and slug and hasattr(systems_service, "get_entry_by_slug_for_campaign"):
                entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, slug)
                if entry is not None and (not hasattr(systems_service, "is_entry_enabled_for_campaign")
                                          or not systems_service.is_entry_enabled_for_campaign(campaign_slug, entry)):
                    entry = None
            if entry is not None:
                actual_key = str(getattr(entry, "entry_key", "") or "").strip()
                actual_slug = str(getattr(entry, "slug", "") or "").strip()
                if (key and actual_key and key != actual_key) or (slug and actual_slug and slug != actual_slug):
                    entry = None
        if not ref and not page_ref:
            continue
        if not page_unavailable and (not ref or entry is not None):
            continue
        item["mechanics_suppressed"] = True
        sourced_bonus_fields = {
            "bonus", "bonus_ac", "bonus_attack_rolls", "bonus_damage_rolls",
            "bonus_weapon", "bonus_weapon_attack", "bonus_weapon_damage",
            "defensive_rules", "attack_reminder_rules", "spell_support",
            "resource_template_bonuses", "item_use_actions", "item_uses",
        }
        for field in CAMPAIGN_ITEM_METADATA_KEYS:
            if field in sourced_bonus_fields:
                item.pop(field, None)
        warnings.append({"code": "linked_item_source_unavailable", "message":
                         f"Automatic effects for {str(item.get('name') or item.get('id') or 'an item')} are unavailable because a linked Items page or Systems source is unavailable."})
    return CharacterDefinition.from_dict(payload), warnings


def repair_activation_state(
    definition: Any, state: dict[str, Any], *, row_index: int,
    choice: str, target_id: str = "",
) -> dict[str, Any]:
    """Apply one explicitly reviewed row choice without losing nonactivation state."""
    from .character_service import CharacterStateValidationError

    rows = list((state or {}).get("inventory") or [])
    if any(not isinstance(item, dict) for item in rows):
        raise CharacterStateValidationError(
            "Malformed inventory rows require separate operator reconciliation."
        )
    if choice not in {"preserve", "remap", "discard", "seed_missing"}:
        raise CharacterStateValidationError("Choose preserve, remap, discard, or seed missing state.")
    result = deepcopy(state)
    definition_payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    definition_rows = [item for item in list(definition_payload.get("equipment_catalog") or [])
                       if isinstance(item, dict) and not item.get("is_currency_only")]
    definition_ids = [str(item.get("id") or "").strip() for item in definition_rows]
    if choice == "seed_missing":
        from .character_service import build_inventory_state
        if row_index < 0 or row_index >= len(definition_rows):
            raise CharacterStateValidationError("Choose one definition row to seed.")
        item_id = definition_ids[row_index]
        if not item_id or definition_ids.count(item_id) != 1 or any(
            str(item.get("catalog_ref") or item.get("id") or "").strip() == item_id
            for item in rows
        ):
            raise CharacterStateValidationError("Missing state can be seeded only for one unique, unused ID.")
        result.setdefault("inventory", []).append(build_inventory_state(definition_rows[row_index]))
        result["attunement"] = dict(result.get("attunement") or {})
        result["attunement"]["attuned_item_refs"] = [
            str(item.get("catalog_ref") or item.get("id") or "").strip()
            for item in result["inventory"] if bool(item.get("is_attuned"))
        ]
        if dict(state.get("equipment_activation") or {}).get("schema_version") == ACTIVATION_SCHEMA_VERSION:
            result["equipment_activation"] = activation_marker(definition)
            return result
        from .character_equipment_migration import plan_equipment_activation_migration
        return plan_equipment_activation_migration(definition, result, allow_partial=True)["state"]
    if row_index < 0 or row_index >= len(rows) or not isinstance(rows[row_index], dict):
        raise CharacterStateValidationError("Choose one existing inventory row to repair.")
    row = result["inventory"][row_index]
    original_id = str(row.get("catalog_ref") or row.get("id") or "").strip()
    if choice == "preserve":
        if not original_id or definition_ids.count(original_id) != 1:
            raise CharacterStateValidationError("Preserve requires one exact definition ID.")
        if sum(1 for item in rows if str(item.get("catalog_ref") or item.get("id") or "").strip() == original_id) != 1:
            raise CharacterStateValidationError("Preserve requires one exact state ID.")
        target = definition_rows[definition_ids.index(original_id)]
    elif choice == "remap":
        if not target_id or definition_ids.count(target_id) != 1:
            raise CharacterStateValidationError("Remap requires a selected unique definition ID.")
        if any(index != row_index and str(item.get("catalog_ref") or item.get("id") or "").strip() == target_id
               for index, item in enumerate(rows)):
            raise CharacterStateValidationError("The selected definition ID already has state.")
        row["id"] = target_id
        row["catalog_ref"] = target_id
        target = definition_rows[definition_ids.index(target_id)]
    else:
        exact_unique = (
            original_id and definition_ids.count(original_id) == 1
            and sum(1 for item in rows
                    if str(item.get("catalog_ref") or item.get("id") or "").strip() == original_id) == 1
        )
        if not exact_unique:
            # Keep quantities and notes as inventory-only evidence.
            retained_id = "retained-inventory-" + hashlib.sha256(
                f"{original_id}:{row_index}:{definition_digest(definition)}".encode("utf-8")
            ).hexdigest()[:20]
            if retained_id in definition_ids or any(
                index != row_index and str(item.get("id") or "") == retained_id
                for index, item in enumerate(rows)
            ):
                raise CharacterStateValidationError("Retained inventory identity collided.")
            row["id"] = retained_id
            row["catalog_ref"] = ""
            row["unlinked_activation_discarded"] = True
        row["is_equipped"] = False
        row["is_attuned"] = False
        row["weapon_wield_mode"] = ""
        target = None
    if target is not None:
        for field in ACTIVATION_FIELDS:
            if field not in row:
                row[field] = target.get(field, "" if field == "weapon_wield_mode" else False)
        row["is_equipped"] = bool(row["is_equipped"])
        row["is_attuned"] = bool(row["is_attuned"])
        row["weapon_wield_mode"] = str(row["weapon_wield_mode"] or "").strip()
        row.pop("unlinked_activation_discarded", None)
    result["attunement"] = dict(result.get("attunement") or {})
    result["attunement"]["attuned_item_refs"] = [
        str(item.get("catalog_ref") or item.get("id") or "").strip()
        for item in result["inventory"] if bool(item.get("is_attuned"))
    ]
    if dict(state.get("equipment_activation") or {}).get("schema_version") == ACTIVATION_SCHEMA_VERSION:
        result["equipment_activation"] = activation_marker(definition)
        return result
    from .character_equipment_migration import plan_equipment_activation_migration
    return plan_equipment_activation_migration(definition, result, allow_partial=True)["state"]


def repair_definition_identity(
    definition: Any, state: dict[str, Any], *, definition_index: int,
    state_index: int, new_id: str,
) -> tuple[Any, dict[str, Any]]:
    """Manager-selected definition ID and optional explicit SQLite row remap."""
    from .character_models import CharacterDefinition
    from .character_service import CharacterStateValidationError
    from .character_equipment_migration import plan_equipment_activation_migration

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", new_id or ""):
        raise CharacterStateValidationError("Enter a unique stable item ID using letters, digits, dot, colon, underscore, or dash.")
    payload = deepcopy(definition.to_dict())
    rows = [item for item in list(payload.get("equipment_catalog") or [])
            if isinstance(item, dict) and not item.get("is_currency_only")]
    if definition_index < 0 or definition_index >= len(rows):
        raise CharacterStateValidationError("Choose a definition row to repair.")
    all_ids = {str(item.get("id") or "").strip() for item in rows}
    state_rows = list(state.get("inventory") or [])
    if any(not isinstance(item, dict) for item in state_rows):
        raise CharacterStateValidationError(
            "Malformed inventory rows require separate operator reconciliation."
        )
    state_ids = {str(item.get("catalog_ref") or item.get("id") or "").strip()
                 for item in state_rows if isinstance(item, dict)}
    if new_id in all_ids or new_id in state_ids:
        raise CharacterStateValidationError("The selected item ID is already in use.")
    old_id = str(rows[definition_index].get("id") or "").strip()
    linked_keys = {"equipment_ref", "equipment_refs", "item_ref", "item_refs", "target_item_ref", "catalog_ref"}

    def has_other_link(value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in linked_keys:
                    if isinstance(child, list) and old_id in child:
                        return True
                    if isinstance(child, str) and child == old_id:
                        return True
                if has_other_link(child):
                    return True
        elif isinstance(value, list):
            return any(has_other_link(child) for child in value)
        return False

    if old_id and has_other_link({key: value for key, value in payload.items()
                                  if key not in {"equipment_catalog", "attacks"}}):
        raise CharacterStateValidationError(
            "Other Character links still reference this item ID; reconcile those links before changing it."
        )
    for attack in list(payload.get("attacks") or []):
        if not isinstance(attack, dict):
            continue
        if old_id and has_other_link({key: value for key, value in attack.items()
                                      if key not in {"equipment_ref", "equipment_refs"}}):
            raise CharacterStateValidationError(
                "An unsupported attack link still references this item ID; reconcile it before changing the ID."
            )
        raw_attack_refs = attack.get("equipment_refs")
        if old_id and isinstance(raw_attack_refs, str) and raw_attack_refs == old_id:
            raise CharacterStateValidationError(
                "An attack has a non-list equipment reference; reconcile it before changing the item ID."
            )
        linked = (old_id and (
            attack.get("equipment_ref") == old_id
            or (isinstance(raw_attack_refs, list) and old_id in raw_attack_refs)
        ))
        if linked and sum(1 for row in rows if str(row.get("id") or "").strip() == old_id) != 1:
            raise CharacterStateValidationError(
                "Attack links use a duplicate item ID; resolve the attack mapping before changing this definition ID."
            )
        if linked:
            if attack.get("equipment_ref") == old_id:
                attack["equipment_ref"] = new_id
            if isinstance(attack.get("equipment_refs"), list):
                attack["equipment_refs"] = [new_id if ref == old_id else ref
                                            for ref in attack["equipment_refs"]]
    rows[definition_index]["id"] = new_id
    new_definition = CharacterDefinition.from_dict(payload)
    new_state = deepcopy(state)
    if state_index >= 0:
        if state_index >= len(state_rows) or not isinstance(state_rows[state_index], dict):
            raise CharacterStateValidationError("Choose a valid SQLite row to remap.")
        new_state["inventory"][state_index]["id"] = new_id
        new_state["inventory"][state_index]["catalog_ref"] = new_id
        new_state["inventory"][state_index].pop("unlinked_activation_discarded", None)
    new_state["attunement"] = dict(new_state.get("attunement") or {})
    new_state["attunement"]["attuned_item_refs"] = [
        str(item.get("catalog_ref") or item.get("id") or "").strip()
        for item in new_state.get("inventory") or [] if bool(item.get("is_attuned"))
    ]
    if dict(state.get("equipment_activation") or {}).get("schema_version") == ACTIVATION_SCHEMA_VERSION:
        new_state["equipment_activation"] = activation_marker(new_definition)
    else:
        new_state = plan_equipment_activation_migration(
            new_definition, new_state, allow_partial=True
        )["state"]
    return new_definition, new_state
