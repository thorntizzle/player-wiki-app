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


def activation_marker_kind(state: dict[str, Any]) -> str:
    """Classify retained schema evidence without normalizing it."""
    if "equipment_activation" not in state:
        return "absent"
    marker = state["equipment_activation"]
    if not isinstance(marker, dict):
        return "present_invalid"
    identities = marker.get("known_definition_ids")
    if (type(marker.get("schema_version")) is int
            and marker["schema_version"] == ACTIVATION_SCHEMA_VERSION
            and isinstance(identities, list)
            and all(isinstance(value, str) and value and value == value.strip() for value in identities)
            and len(identities) == len(set(identities))):
        return "valid_v1"
    return "present_invalid"


def activation_value_issue(item: dict[str, Any]) -> str:
    """Classify explicit observations without coercing or repairing their values."""
    for field in ("is_equipped", "is_attuned", "unlinked_activation_discarded"):
        if field in item and type(item[field]) is not bool:
            return "malformed_activation_boolean"
    if "weapon_wield_mode" in item:
        value = item["weapon_wield_mode"]
        if value is not None and (type(value) is not str or value and
                re.sub(r"[^a-z0-9]+", "", value.lower()) not in {"mainhand", "offhand", "twohanded"}):
            return "malformed_wield_mode"
    return ""


def require_activation_values(item: Any) -> None:
    """Reject original malformed observations before a constructor can coerce them."""
    if not isinstance(item, dict) or activation_value_issue(item):
        from .character_service import CharacterStateValidationError
        raise CharacterStateValidationError(
            "Equipment activation values need manager repair before this state can change.")


def effective_inventory_rows(definition: Any, state: dict[str, Any]) -> list[Any]:
    """Detached effective flags for read DTOs; retained raw state is never changed."""
    rows = deepcopy(list((state or {}).get("inventory") or []))
    if is_xianxia_system(getattr(definition, "system", "")):
        return rows
    analysis = analyze_activation(definition, state)
    eligible = {row["index"] for row in analysis["rows"]
                if row["source"] == "sqlite" and row["status"] == "exact"}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row["is_equipped"] = index in eligible and row.get("is_equipped") is True
        row["is_attuned"] = index in eligible and row.get("is_attuned") is True
        mode = row.get("weapon_wield_mode")
        row["weapon_wield_mode"] = mode.strip() if index in eligible and isinstance(mode, str) else ""
    return rows


class ActivationPrerequisiteError(ValueError):
    """An activation prerequisite refused before publication could start."""


def activation_frame_digest(value: Any) -> str:
    """Compare JSON observations without bool/int/float or absence coercion."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def native_activation_readiness(prior_record, definition, state, *, final=False):
    """Non-entitling native facts; never repair or initialize activation.

    The producer has to authenticate its original before calling this helper.
    Publication additionally requires the genuine pending native proof. Neither
    these facts nor physical equality establishes current item benefits.
    """
    def fail():
        raise ActivationPrerequisiteError("Native equipment activation needs separate manager repair.")

    def exact_id(value):
        return type(value) is str and bool(value) and value == value.strip()

    def typed_rows(candidate, frame):
        payload = candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
        rows, inventory = payload.get("equipment_catalog"), frame.get("inventory")
        if type(rows) is not list or type(inventory) is not list:
            fail()
        physical = {}
        for item in rows:
            if type(item) is not dict or ("is_currency_only" in item
                    and type(item["is_currency_only"]) is not bool):
                fail()
            for key in ("is_equipped", "is_attuned"):
                if key in item and type(item[key]) is not bool:
                    fail()
            check_mode(item)
            if item.get("is_currency_only", False):
                continue
            identity = item.get("id")
            if not exact_id(identity) or identity in physical:
                fail()
            physical[identity] = item
        seen = set()
        for item in inventory:
            if type(item) is not dict:
                fail()
            identity, reference = item.get("id"), item.get("catalog_ref")
            if (not exact_id(identity) or not exact_id(reference) or identity != reference
                    or identity in seen or identity not in physical):
                fail()
            seen.add(identity)
            if "unlinked_activation_discarded" in item and (
                    type(item["unlinked_activation_discarded"]) is not bool
                    or item["unlinked_activation_discarded"]):
                fail()
            if any(type(item.get(key)) is not bool for key in ("is_equipped", "is_attuned")):
                fail()
            check_mode(item)
        if seen != set(physical):
            fail()
        if "equipment_activation" in frame:
            marker = frame["equipment_activation"]
            if (type(marker) is not dict or type(marker.get("schema_version")) is not int
                    or marker["schema_version"] != ACTIVATION_SCHEMA_VERSION
                    or type(marker.get("known_definition_ids")) is not list):
                fail()
            identities = marker["known_definition_ids"]
            if (any(not exact_id(value) for value in identities)
                    or len(identities) != len(set(identities))):
                fail()
        analysis = analyze_activation(candidate, frame)
        allowed = set() if "equipment_activation" in frame else {"activation_migration_required"}
        if (any(row["status"] != "exact" for row in analysis["rows"])
                or {warning["code"] for warning in analysis["warnings"]} != allowed):
            fail()
        return physical, analysis

    def check_mode(item):
        if "weapon_wield_mode" not in item or item["weapon_wield_mode"] is None:
            return
        value = item["weapon_wield_mode"]
        if type(value) is not str or (value and re.sub(r"[^a-z0-9]+", "", value.lower())
                not in {"mainhand", "offhand", "twohanded"}):
            fail()

    prior_state = prior_record.state_record.state
    if type(state) is not dict or type(prior_state) is not dict:
        fail()
    old, _ = typed_rows(prior_record.definition, prior_state)
    new, analysis = typed_rows(definition, state)
    if (activation_frame_digest(old) != activation_frame_digest(new)
            or activation_frame_digest(prior_state.get("inventory")) != activation_frame_digest(state.get("inventory"))
            or ("equipment_activation" in prior_state) != ("equipment_activation" in state)
            or activation_frame_digest(prior_state.get("equipment_activation"))
               != activation_frame_digest(state.get("equipment_activation"))):
        fail()
    legacy = "equipment_activation" not in prior_state
    if final and legacy and activation_frame_digest(prior_state) != activation_frame_digest(state):
        fail()
    return analysis


def require_update_activation(prior_record, definition, state, *, reconstruction=None,
                              actor_id=None, native_proof=None, source_read_owner=None,
                              feature_class_association=None):
    """Share ordinary readiness and the proof-bound, exact legacy exception.

    Missing schema evidence needs genuine current reconstruction or the full
    signed native proof with an exact retained legacy state.
    This does not project activation, initialize rows, or repair a marker.
    """
    if feature_class_association is not None:
        from .character_feature_class_association import PendingFeatureClassAssociation
        if (type(feature_class_association) is not PendingFeatureClassAssociation
                or reconstruction is not None or native_proof is not None):
            raise ActivationPrerequisiteError("Feature association needs its exact reviewed plan.")
        feature_class_association.validate_binding(prior_record, definition, state, actor_id)
        return native_activation_readiness(prior_record, definition, state, final=True)
    if native_proof is not None:
        from .character_reconciliation import PendingReviewedSourceProof
        if reconstruction is not None or not isinstance(native_proof, PendingReviewedSourceProof):
            raise ActivationPrerequisiteError("Native activation requires its exact reviewed proof.")
        native_proof.native_activation_binding(prior_record, definition, state, actor_id,
                                               source_read_owner=source_read_owner)
        return native_activation_readiness(prior_record, definition, state, final=True)
    analysis = analyze_activation(definition, state)
    if reconstruction is not None:
        from .character_reconstruction_authority import PendingNativeReconstruction
        try:
            if not isinstance(reconstruction, PendingNativeReconstruction):
                raise ValueError("Reconstruction proof is unavailable.")
            reconstruction.validate_binding(prior_record, definition, state, actor_id)
            marker = state.get("equipment_activation")
            # Existing membership/order representations follow analyze_activation;
            # the sorted producer shape is not a retained-state prerequisite.
            if "equipment_activation" in state and (
                    not isinstance(marker, dict)
                    or type(marker.get("schema_version")) is not int
                    or marker.get("schema_version") != ACTIVATION_SCHEMA_VERSION):
                raise ValueError("The retained activation marker needs separate repair.")
        except (ValueError, TypeError, KeyError) as exc:
            raise ActivationPrerequisiteError("Equipment activation is incompatible with exact reconstruction; separate manager repair is required.") from exc
    if not analysis["blocked"]:
        return analysis
    if reconstruction is None:
        raise ActivationPrerequisiteError("Equipment activation identity needs manager repair before this Character update.")
    try:
        if ("equipment_activation" in prior_record.state_record.state
                or "equipment_activation" in state
                or any(row["status"] != "exact" for row in analysis["rows"])
                or {warning["code"] for warning in analysis["warnings"]}
                   != {"activation_migration_required"}):
            raise ValueError("Only an absent legacy activation marker can be retained.")
        prior = analyze_activation(prior_record.definition, prior_record.state_record.state)
        if (any(row["status"] != "exact" for row in prior["rows"])
                or {warning["code"] for warning in prior["warnings"]}
                   != {"activation_migration_required"}):
            raise ValueError("The prior physical activation owners need separate repair.")
        for row in prior["rows"]:
            if row["source"] != "sqlite":
                continue
            item = row["state"]
            if any(key in item and item[key] is not None and (
                    not isinstance(item[key], str) or item[key] != item[key].strip())
                    for key in ("id", "catalog_ref")):
                raise ValueError("A physical owner is not an exact retained identifier.")
            identity = row["definition"].get("id")
            if not isinstance(identity, str) or not identity or identity != identity.strip():
                raise ValueError("A physical definition owner is not exact.")
        old = {row["id"]: row["definition"] for row in prior["rows"] if row["source"] == "sqlite"}
        new = {row["id"]: row["definition"] for row in analysis["rows"] if row["source"] == "sqlite"}
        if set(old) != set(new):
            raise ValueError("Reconstruction cannot change physical activation owners.")
        for identity in old:
            if old[identity] != new[identity] and not reconstruction.permits_item_mapping(prior_record, definition, identity):
                raise ValueError("A changed physical source needs exact reconstruction proof.")
    except (ValueError, TypeError, KeyError) as exc:
        raise ActivationPrerequisiteError("Equipment activation is incompatible with exact reconstruction; separate manager repair is required.") from exc
    return analysis


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
    raw_rows = (state or {}).get("inventory")
    state_rows = raw_rows if isinstance(raw_rows, list) else []
    marker_kind = activation_marker_kind(state or {})
    raw_marker = (state or {}).get("equipment_activation")
    marker_present = marker_kind != "absent"
    marker = raw_marker if isinstance(raw_marker, dict) else {}
    known_ids = marker.get("known_definition_ids")
    marker_valid = marker_kind == "valid_v1"
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
        value_issue = activation_value_issue(item)
        if value_issue:
            rows.append({"source": "sqlite", "index": index, "id": state_ids[index],
                         "definition": deepcopy(definition_by_id.get(state_ids[index])),
                         "state": deepcopy(item), "status": value_issue})
            warnings.append({"code": value_issue, "message":
                             f"Equipment activation for {state_ids[index] or 'an unnamed row'} needs manager repair."})
            continue
        if item.get("unlinked_activation_discarded") is True:
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
        elif marker_kind == "present_invalid":
            reason = "invalid_activation_marker"
        elif marker_present and not all(field in item for field in ACTIVATION_FIELDS):
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
    return {"rows": rows, "warnings": warnings, "blocked": bool(warnings),
            "marker_kind": marker_kind}


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
        item["is_equipped"] = state_item.get("is_equipped", False)
        item["is_attuned"] = state_item.get("is_attuned", False)
        raw_mode = state_item.get("weapon_wield_mode")
        mode = raw_mode.strip() if raw_mode is not None else ""
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
                build_inventory_state(definition_rows[row["index"]], strict_activation=True)
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
            "bonus_weapon", "bonus_weapon_attack", "bonus_weapon_damage", "weapon_extra_damage",
            "defensive_rules", "attack_reminder_rules", "spell_support",
            "spellcasting_modifiers", "spell_property_modifiers",
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
        result.setdefault("inventory", []).append(
            build_inventory_state(definition_rows[row_index], strict_activation=True))
        result["attunement"] = dict(result.get("attunement") or {})
        result["attunement"]["attuned_item_refs"] = [
            str(item.get("catalog_ref") or item.get("id") or "").strip()
            for item in result["inventory"] if item.get("is_attuned") is True
        ]
        if activation_marker_kind(state) == "valid_v1":
            result["equipment_activation"] = activation_marker(definition)
            return result
        from .character_equipment_migration import plan_equipment_activation_migration
        return plan_equipment_activation_migration(definition, result, allow_partial=True)["state"]
    if row_index < 0 or row_index >= len(rows) or not isinstance(rows[row_index], dict):
        raise CharacterStateValidationError("Choose one existing inventory row to repair.")
    row = result["inventory"][row_index]
    if choice in {"preserve", "remap"}:
        require_activation_values(row)
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
        if exact_unique:
            row.pop("unlinked_activation_discarded", None)
        target = None
    if target is not None:
        require_activation_values({field: row[field] if field in row else target.get(
            field, "" if field == "weapon_wield_mode" else False) for field in ACTIVATION_FIELDS})
        for field in ACTIVATION_FIELDS:
            if field not in row:
                row[field] = target.get(field, "" if field == "weapon_wield_mode" else False)
        row["weapon_wield_mode"] = (row["weapon_wield_mode"] or "").strip()
        row.pop("unlinked_activation_discarded", None)
    result["attunement"] = dict(result.get("attunement") or {})
    result["attunement"]["attuned_item_refs"] = [
        str(item.get("catalog_ref") or item.get("id") or "").strip()
        for item in result["inventory"] if item.get("is_attuned") is True
    ]
    if activation_marker_kind(state) == "valid_v1":
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
    require_activation_values(rows[definition_index])
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
        require_activation_values(state_rows[state_index])
        new_state["inventory"][state_index]["id"] = new_id
        new_state["inventory"][state_index]["catalog_ref"] = new_id
        new_state["inventory"][state_index].pop("unlinked_activation_discarded", None)
    new_state["attunement"] = dict(new_state.get("attunement") or {})
    new_state["attunement"]["attuned_item_refs"] = [
        str(item.get("catalog_ref") or item.get("id") or "").strip()
        for item in new_state.get("inventory") or [] if item.get("is_attuned") is True
    ]
    if activation_marker_kind(state) == "valid_v1":
        new_state["equipment_activation"] = activation_marker(new_definition)
    else:
        new_state = plan_equipment_activation_migration(
            new_definition, new_state, allow_partial=True
        )["state"]
    return new_definition, new_state


def validate_activation_repair_intent(prior_definition: Any, prior_state: dict[str, Any],
                                      definition: Any, state: dict[str, Any], intent: Any) -> None:
    """Rebuild a bounded form intent from original evidence, never from desired flags."""
    from .character_service import CharacterStateValidationError
    if (type(intent) is not tuple or len(intent) != 4
            or type(intent[0]) is not str or type(intent[1]) is not int
            or type(intent[2]) is not str or type(intent[3]) is not int
            or intent[1] < 0 or intent[3] < -1 or len(intent[2]) > 160):
        raise CharacterStateValidationError("Activation repair needs its exact reviewed form intent.")
    choice, row_index, target_id, state_index = intent
    if choice == "remap_definition":
        expected_definition, expected_state = repair_definition_identity(
            prior_definition, prior_state,
            definition_index=row_index, state_index=state_index, new_id=target_id)
    else:
        if (choice not in {"preserve", "remap", "discard", "seed_missing"}
                or state_index != -1 or (choice != "remap" and target_id)):
            raise CharacterStateValidationError("Activation repair intent is incompatible with its row choice.")
        expected_definition = prior_definition
        expected_state = repair_activation_state(
            prior_definition, prior_state,
            row_index=row_index, choice=choice, target_id=target_id)
    if (activation_frame_digest(expected_definition.to_dict()) != activation_frame_digest(definition.to_dict())
            or activation_frame_digest(expected_state) != activation_frame_digest(state)):
        raise CharacterStateValidationError("Activation repair differs from its original observations and explicit intent.")


def definition_identity_repair_disposition(prior_definition: Any, prior_state: dict[str, Any],
                                           definition: Any, state: dict[str, Any],
                                           intent: Any) -> tuple[Any, ...] | None:
    """Prove a complete ID-only repair, without qualifying retired item mechanics."""
    if intent is None:
        return None
    validate_activation_repair_intent(prior_definition, prior_state, definition, state, intent)
    if intent[0] != "remap_definition":
        return None
    from .character_service import CharacterStateValidationError

    def refuse() -> None:
        raise CharacterStateValidationError(
            "Definition-ID repair needs complete unambiguous resulting equipment and no affected item custody links.")

    catalog, inventory = definition.equipment_catalog, state.get("inventory")
    if type(catalog) is not list or type(inventory) is not list:
        refuse()
    for row in catalog:
        if (type(row) is not dict or ("is_currency_only" in row
                and type(row["is_currency_only"]) is not bool)):
            refuse()
        if not row.get("is_currency_only"):
            identity = row.get("id")
            if type(identity) is not str or not identity or identity != identity.strip():
                refuse()
    physical_ids = []
    for row in inventory:
        require_activation_values(row)
        identity = row.get("id")
        if type(identity) is not str or not identity or identity != identity.strip():
            refuse()
        physical_ids.append(identity)
        if row.get("unlinked_activation_discarded") is not True:
            refs = [row[key] for key in ("id", "catalog_ref") if key in row]
            if any(type(value) is not str or not value or value != identity for value in refs):
                refuse()
    analysis = analyze_activation(definition, state)
    if (analysis["blocked"] or len(physical_ids) != len(set(physical_ids))
            or any(row["status"] not in {"exact", "discarded_unlinked"} for row in analysis["rows"])):
        refuse()

    old_rows = [row for row in prior_definition.equipment_catalog
                if isinstance(row, dict) and not row.get("is_currency_only")]
    # The validated destination may already name an orphan custody record,
    # even though it is unused by ordinary catalogue/inventory rows.
    affected = {str(old_rows[intent[1]].get("id") or "").strip(), intent[2]}
    if intent[3] >= 0:
        old_row = prior_state["inventory"][intent[3]]
        affected.update(str(old_row.get(key) or "").strip() for key in ("id", "catalog_ref"))
    affected.discard("")
    link_fields = {"equipment_ref", "equipment_refs", "item_ref", "item_refs", "target_item_ref",
                   "catalog_ref", "item_id", "item_owner_ids", "item_transition_cleared_charges",
                   "physical_id", "catalog_id",
                   "source_row_id", "spell_source_row_id"}

    def has_link(value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "target_id" and isinstance(child, str) and any(
                        child == f"item_charge:{identity}" for identity in affected):
                    return True
                if key in link_fields and (
                        isinstance(child, str) and child in affected
                        or isinstance(child, list) and any(isinstance(item, str) and item in affected for item in child)):
                    return True
                if has_link(child):
                    return True
        elif isinstance(value, list):
            return any(has_link(child) for child in value)
        return False

    # Existing native item associations and state ledgers have their own
    # custody protocols. Identity repair neither rewrites nor renews them.
    if has_link(prior_definition.source) or has_link(prior_definition.spellcasting):
        refuse()
    for field in ("item_spell_storage", "item_prepared_ammunition", "artificer_assignments"):
        ledger = prior_state.get(field)
        if (isinstance(ledger, dict) and any(key in affected for key in ledger)
                or has_link(ledger)):
            refuse()
    assignments = prior_state.get("artificer_assignments")
    if isinstance(assignments, dict):
        for kind in ("infusions", "tinkering"):
            member = assignments.get(kind)
            entries = member.get("entries") if isinstance(member, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                obj = entry.get("object") if isinstance(entry, dict) else None
                if isinstance(obj, dict):
                    object_id, physical_id = obj.get("id"), obj.get("physical_id")
                    if (obj.get("mode") == "inventory" and isinstance(object_id, str) and object_id in affected
                            or isinstance(physical_id, str) and physical_id in {
                                f"inventory:{identity}" for identity in affected}):
                        refuse()
    return (intent, activation_frame_digest(prior_definition.to_dict()),
            activation_frame_digest(prior_state), activation_frame_digest(definition.to_dict()),
            activation_frame_digest(state))
