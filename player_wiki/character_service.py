from __future__ import annotations

from .character_equipment_activation import (activation_marker, activation_frame_digest,
                                             require_activation_values)

from copy import deepcopy
from typing import Any

from .character_artificer_infusions import normalize_active_infusions
from .character_builder_equipment import _normalize_weapon_wield_mode_value
from .character_hit_dice import (
    derive_hit_dice_max_pools,
    normalize_hit_dice_state,
    normalize_hit_dice_state_payload,
    normalize_verified_hit_dice_state_payload,
)
from .character_models import CharacterDefinition
from .character_spell_slots import (
    normalize_spell_slot_lane_id,
    spell_slot_lanes_from_spellcasting,
    spell_slot_state_entries_from_spellcasting,
)
from .system_policy import is_xianxia_system
from .xianxia_character_model import (
    build_xianxia_initial_state_payload,
    normalize_xianxia_inventory_row,
    normalize_xianxia_state_payload,
    xianxia_hp_max,
)

MANAGED_CUSTOM_TRACKER_PREFIX = "manual-feature-tracker:"
SUPPORTED_FEATURE_STATE_KEYS = {"arcane_armor", "divine_avatar_forms"}


class CharacterStateValidationError(ValueError):
    pass


def _require_typed_activation_values(item: Any) -> None:
    require_activation_values(item)


def _inventory_note_target(
    definition: CharacterDefinition, state: dict[str, Any], item_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = [row for row in definition.equipment_catalog if row.get("id") == item_id]
    inventory = [row for row in list(state.get("inventory") or [])
                 if isinstance(row, dict) and item_id in {
                     str(row.get("id") or "").strip(), str(row.get("catalog_ref") or "").strip(),
                 }]
    if (not item_id or len(catalog) != 1 or len(inventory) != 1
            or catalog[0].get("source_kind") != "manual_edit"
            or catalog[0].get("is_currency_only")):
        raise CharacterStateValidationError("Item notes need one exact supplemental inventory identity.")
    row = inventory[0]
    if (str(row.get("catalog_ref") or row.get("id") or "").strip() != item_id
            or any(str(row.get(key) or "").strip() not in {"", item_id}
                   for key in ("id", "catalog_ref"))):
        raise CharacterStateValidationError("Item note inventory identities do not match.")
    return catalog[0], row


def current_inventory_note_values(
    definition: CharacterDefinition, state: dict[str, Any],
) -> dict[str, str]:
    """Display current notes only for unambiguous existing supplemental rows."""
    notes: dict[str, str] = {}
    for item in definition.equipment_catalog:
        item_id = str(item.get("id") or "").strip()
        try:
            catalog, row = _inventory_note_target(definition, state, item_id)
        except CharacterStateValidationError:
            continue
        notes[item_id] = str(row.get("notes", catalog.get("notes", "")) or "")
    return notes


def prepare_inventory_note_overrides(
    definition: CharacterDefinition, state: dict[str, Any], submitted: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Separate explicit current-note edits from omission and unchanged defaults."""
    overrides: dict[str, dict[str, str]] = {}
    for item_id, value in submitted.items():
        if not isinstance(item_id, str) or item_id != item_id.strip() or not isinstance(value, str):
            raise CharacterStateValidationError("Item note intent must contain exact IDs and text.")
        catalog, row = _inventory_note_target(definition, state, item_id)
        current = str(row.get("notes", catalog.get("notes", "")) or "")
        if value == current:
            continue
        edited = value.strip()
        if edited != current:
            overrides[item_id] = {"notes": edited}
    return overrides


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


def build_inventory_state(item: dict[str, Any], *, quantity: int | None = None,
                          strict_activation: bool = False) -> dict[str, Any]:
    if strict_activation:
        _require_typed_activation_values(item)
    resolved_quantity = item.get("default_quantity") if quantity is None else quantity
    payload = {
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
    weapon_wield_mode = _normalize_weapon_wield_mode_value(item.get("weapon_wield_mode"))
    payload["weapon_wield_mode"] = weapon_wield_mode
    active_infusions = normalize_active_infusions(item.get("active_infusions"))
    if active_infusions:
        payload["active_infusions"] = active_infusions
    return payload


def _inventory_item_ref(item: dict[str, Any]) -> str:
    return str(item.get("catalog_ref") or item.get("id") or "").strip()


def _normalize_attunement_state(
    attunement: dict[str, Any] | None,
    inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_max_attuned_items = (attunement or {}).get("max_attuned_items", 3)
    max_attuned_items = int(3 if raw_max_attuned_items is None else raw_max_attuned_items)
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
    if is_xianxia_system(definition.system):
        return _build_xianxia_initial_state(definition)

    max_hp = int(definition.stats.get("max_hp") or 0)
    spell_slots = spell_slot_state_entries_from_spellcasting(definition.spellcasting)

    resources = [build_resource_state(template) for template in definition.resource_templates]

    inventory = []
    currency = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []}
    for item in definition.equipment_catalog:
        item_currency = dict(item.get("currency") or {})
        for denomination in ("cp", "sp", "ep", "gp", "pp"):
            currency[denomination] = int(currency.get(denomination) or 0) + int(
                item_currency.get(denomination) or 0
            )
        if bool(item.get("is_currency_only")):
            continue
        inventory.append(build_inventory_state(item, strict_activation=True))

    return {
        "status": definition.status,
        "vitals": {
            "current_hp": max_hp,
            "temp_hp": 0,
            "death_saves": {"successes": 0, "failures": 0},
        },
        "hit_dice": normalize_hit_dice_state(definition, None),
        "resources": resources,
        "inventory": inventory,
        "equipment_activation": activation_marker(definition),
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


def _build_xianxia_initial_state(definition: CharacterDefinition) -> dict[str, Any]:
    xianxia_state = build_xianxia_initial_state_payload(definition)
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
            "current_hp": int(xianxia_state["vitals"]["current_hp"]),
            "temp_hp": int(xianxia_state["vitals"]["temp_hp"]),
        },
        "resources": [],
        "inventory": inventory,
        "currency": currency,
        "spell_slots": [],
        "attunement": _normalize_attunement_state({"max_attuned_items": 3}, inventory),
        "notes": {
            "player_notes_markdown": "",
            "physical_description_markdown": "",
            "background_markdown": "",
            "session_notes": [],
        },
        "xianxia": xianxia_state,
    }


def prospective_exact_item_removal_state(
    prior_definition: CharacterDefinition,
    definition: CharacterDefinition,
    state: dict[str, Any],
    item_id: str,
) -> dict[str, Any]:
    """Bind a structural removal to one old definition row and one state row."""
    from .character_equipment_activation import analyze_activation

    item_id = str(item_id or "").strip()
    if not item_id or (
        prior_definition.campaign_slug != definition.campaign_slug
        or prior_definition.character_slug != definition.character_slug
    ):
        raise CharacterStateValidationError("Explicit equipment removal needs the prior Character identity.")
    prior_analysis = analyze_activation(prior_definition, state)
    if prior_analysis["blocked"]:
        raise CharacterStateValidationError("Equipment identity needs manager repair before removal.")
    prior_matches = [item for item in prior_definition.equipment_catalog
                     if isinstance(item, dict) and not item.get("is_currency_only")
                     and str(item.get("id") or "").strip() == item_id]
    new_matches = [item for item in definition.equipment_catalog
                   if isinstance(item, dict) and not item.get("is_currency_only")
                   and str(item.get("id") or "").strip() == item_id]
    exact_rows = [row for row in prior_analysis["rows"]
                  if row["source"] == "sqlite" and row["status"] == "exact"
                  and row["id"] == item_id]
    if len(prior_matches) != 1 or new_matches or len(exact_rows) != 1:
        raise CharacterStateValidationError(
            "Removal requires one prior exact inventory ID that is absent from the new definition."
        )
    prospective = deepcopy(state)
    del prospective["inventory"][exact_rows[0]["index"]]
    return prospective


def prospective_inventory_projection_state(
    prior_definition: CharacterDefinition,
    definition: CharacterDefinition,
    state: dict[str, Any],
    *,
    explicit_removed_item_id: str | None = None,
    inventory_quantity_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Give source projection the same physical inventory as the candidate."""
    from .character_equipment_activation import activation_marker, analyze_activation

    prospective = (
        prospective_exact_item_removal_state(
            prior_definition, definition, state, explicit_removed_item_id,
        ) if explicit_removed_item_id else deepcopy(state)
    )
    analysis = analyze_activation(prior_definition, state)
    if analysis["blocked"]:
        raise CharacterStateValidationError("Equipment identity needs manager repair before publication.")
    present_ids = {
        _inventory_item_ref(row) for row in list(prospective.get("inventory") or [])
        if isinstance(row, dict)
    }
    candidate_items = [row for row in list(definition.equipment_catalog or [])
                       if isinstance(row, dict) and not row.get("is_currency_only")]
    candidate_ids = [str(row.get("id") or "").strip() for row in candidate_items]
    if not all(candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        raise CharacterStateValidationError("Equipment identity needs manager repair before publication.")
    for item in candidate_items:
        item_id = str(item["id"]).strip()
        if item_id not in present_ids:
            quantity = (inventory_quantity_overrides or {}).get(item_id)
            prospective.setdefault("inventory", []).append(
                build_inventory_state(item, quantity=quantity, strict_activation=True)
            )
    prospective["equipment_activation"] = activation_marker(definition)
    prospective["attunement"] = _normalize_attunement_state(
        prospective.get("attunement"), list(prospective.get("inventory") or []),
    )
    return prospective


def _reconcile_numeric_pools(
    definition: CharacterDefinition, payload: dict[str, Any], *,
    source_authority: Any | None,
    removed_resource_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Shared numeric calculation; callers own activation and copy boundaries."""
    hit_die_pools = [
        *derive_hit_dice_max_pools(definition),
        *list(dict(payload.get("hit_dice") or {}).get("pools") or []),
    ]
    if source_authority is None:
        payload = normalize_hit_dice_state_payload(definition, payload)
    else:
        verified_faces = {
            int(pool["faces"]) for pool in hit_die_pools
            if isinstance(pool, dict) and type(pool.get("faces")) is int
            and source_authority.resource_status("hit_die", str(pool["faces"])).is_effective
        }
        payload = normalize_verified_hit_dice_state_payload(definition, payload, verified_faces)
    existing_resources = list(payload.get("resources") or [])
    withheld_resources = set(dict(definition.source or {}).get(
        "item_transition_withheld_resources") or [])
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
        if resource_id in withheld_resources:
            existing_resource = existing_by_id.get(resource_id)
            if existing_resource is not None:
                withheld_row = deepcopy(existing_resource)
                withheld_row["current"] = None
                withheld_row["max"] = None
                withheld_row["authority_status"] = "Needs repair"
                merged_resources.append(withheld_row)
            template_resource_ids.add(resource_id)
            continue
        if source_authority is not None and not source_authority.resource_status("resource", resource_id).is_effective:
            merged_resources.extend(
                deepcopy(row) for row in existing_resources
                if str(row.get("id") or "").strip() == resource_id
            )
            template_resource_ids.add(resource_id)
            continue
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
        if resource_id in withheld_resources:
            withheld_row = deepcopy(resource)
            withheld_row["current"] = None
            withheld_row["max"] = None
            withheld_row["authority_status"] = "Needs repair"
            merged_resources.append(withheld_row)
            continue
        if source_authority is not None and not source_authority.resource_status("resource", resource_id).is_effective:
            merged_resources.append(deepcopy(resource))
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
            if source_authority is not None and not source_authority.resource_status(
                "spell_slot", f"{lane_id}:{level}"
            ).is_effective:
                existing_slot = existing_slots_by_key.get(slot_key)
                if existing_slot is not None:
                    merged_slots.append(deepcopy(existing_slot))
                tracked_slot_keys.add(slot_key)
                tracked_slot_levels.add(level)
                continue
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
        if source_authority is not None and not source_authority.resource_status(
            "spell_slot", f"{lane_id}:{level}"
        ).is_effective:
            merged_slots.append(deepcopy(slot))
            continue
        if not lane_id and level in tracked_slot_levels:
            continue
        merged_slots.append(deepcopy(slot))
    payload["spell_slots"] = merged_slots
    return payload


def _reconcile_current_hp(
    definition: CharacterDefinition, payload: dict[str, Any], *,
    source_authority: Any | None, hp_delta: int = 0,
) -> dict[str, Any]:
    """Preserve the ordinary merge's source-qualified HP calculation."""
    vitals = dict(payload.get("vitals") or {})
    current_hp = int(vitals.get("current_hp") or 0)
    max_hp_status = source_authority.field_status("stats.max_hp") if source_authority is not None else None
    if max_hp_status is not None and not max_hp_status.is_effective:
        if hp_delta:
            raise CharacterStateValidationError("HP maximum needs repair before an HP adjustment.")
        return payload
    max_hp = int(max_hp_status.effective if max_hp_status is not None else (definition.stats or {}).get("max_hp") or 0)
    if hp_delta:
        current_hp += int(hp_delta)
    vitals["current_hp"] = max(0, min(current_hp, max_hp))
    payload["vitals"] = vitals
    return payload


def project_legacy_read_state(
    definition: CharacterDefinition, state: dict[str, Any], *,
    incoming_definition: CharacterDefinition, source_authority: Any,
    state_revision: int,
) -> dict[str, Any]:
    """Project numeric values without performing an equipment-state migration.

    Only an absent legacy marker with exact physical owners is eligible. This
    read boundary never grants permission to update the retained state.
    """
    return _project_guarded_equipment_read_state(definition, state,
        incoming_definition=incoming_definition, source_authority=source_authority,
        state_revision=state_revision, quarantine=False)


def project_quarantined_activation_read_state(
    definition: CharacterDefinition, state: dict[str, Any], *,
    incoming_definition: CharacterDefinition, source_authority: Any,
    state_revision: int,
) -> dict[str, Any]:
    """Keep numeric derivation while retaining malformed activation as raw evidence.

    This read-only boundary accepts only bounded activation-value/marker issues;
    physical ambiguity still refuses, and no writer may use it as admission.
    """
    return _project_guarded_equipment_read_state(definition, state,
        incoming_definition=incoming_definition, source_authority=source_authority,
        state_revision=state_revision, quarantine=True)


def _project_guarded_equipment_read_state(
    definition: CharacterDefinition, state: dict[str, Any], *,
    incoming_definition: CharacterDefinition, source_authority: Any,
    state_revision: int, quarantine: bool,
) -> dict[str, Any]:
    import hashlib

    from .committed_publication import active
    from .character_equipment_activation import analyze_activation, effective_definition
    from .character_source_authority import SourceAuthority, _canonical
    from .system_policy import is_dnd_5e_system

    def refuse() -> None:
        raise CharacterStateValidationError("Legacy read projection needs exact retained equipment identity and current source authority.")

    if (not active() or not is_dnd_5e_system(incoming_definition.system)
            or definition.system != incoming_definition.system
            or definition.campaign_slug != incoming_definition.campaign_slug
            or definition.character_slug != incoming_definition.character_slug
            or type(state) is not dict or (not quarantine and "equipment_activation" in state)
            or type(state_revision) is not int or state_revision < 0
            or type(source_authority) is not SourceAuthority
            or source_authority.state_revision != state_revision):
        refuse()
    authority_definition, _ = effective_definition(incoming_definition, state)
    if (source_authority.definition_digest != hashlib.sha256(
            _canonical(authority_definition.to_dict()).encode("utf-8")).hexdigest()
            or source_authority.state_digest != hashlib.sha256(
                _canonical(state).encode("utf-8")).hexdigest()):
        refuse()

    def physical_owners(candidate: CharacterDefinition) -> dict[str, dict[str, Any]]:
        catalog = candidate.equipment_catalog
        inventory = state.get("inventory")
        if type(catalog) is not list or type(inventory) is not list:
            refuse()
        owners: dict[str, dict[str, Any]] = {}
        for item in catalog:
            if (type(item) is not dict or ("is_currency_only" in item
                    and type(item["is_currency_only"]) is not bool)):
                refuse()
            if item.get("is_currency_only"):
                continue
            identity = item.get("id")
            if (type(identity) is not str or not identity or identity != identity.strip()
                    or identity in owners):
                refuse()
            owners[identity] = item
        seen: set[str] = set()
        for item in inventory:
            if type(item) is not dict:
                refuse()
            identifiers = [item[key] for key in ("id", "catalog_ref") if key in item]
            if (not identifiers or any(type(value) is not str or not value
                    or value != value.strip() for value in identifiers)
                    or len(set(identifiers)) != 1):
                refuse()
            identity = identifiers[0]
            discarded = (item.get("unlinked_activation_discarded") is True
                         if quarantine else item.get("unlinked_activation_discarded"))
            if identity in seen or identity not in owners or discarded:
                refuse()
            seen.add(identity)
        if seen != set(owners):
            refuse()
        analysis = analyze_activation(candidate, state)
        codes = {warning["code"] for warning in analysis["warnings"]}
        if quarantine:
            value_issues = {"malformed_activation_boolean", "malformed_wield_mode"}
            marker_issue = {"invalid_activation_marker"}
            if (not codes or codes - (value_issues | marker_issue | {"activation_migration_required"})
                    or any(row["status"] not in ({"exact"} | value_issues | marker_issue) for row in analysis["rows"])
                    or ("invalid_activation_marker" in codes and analysis["marker_kind"] != "present_invalid")
                    or not (codes & value_issues or "equipment_activation" in state
                            and "activation_migration_required" in codes)):
                refuse()
        elif (any(row["status"] != "exact" for row in analysis["rows"])
                or codes != {"activation_migration_required"}):
            refuse()
        return owners

    incoming_owners = physical_owners(incoming_definition)
    normalized_owners = physical_owners(definition)

    def source_binding(item: dict[str, Any]) -> tuple[Any, Any, Any]:
        # Match only the optional representations produced by the normalizer.
        # These local comparison values never replace retained observations.
        kind = item.get("source_kind")
        if kind is None:
            kind = ""
        elif type(kind) is str:
            kind = kind.strip()
        else:
            refuse()
        reference = item.get("systems_ref")
        if reference is None:
            reference = {}
        elif type(reference) is not dict:
            refuse()
        page = item.get("page_ref")
        if type(page) is str:
            page = page.strip() or None
        elif page is not None and type(page) is not dict:
            refuse()
        return kind, reference, page

    def same_typed_reference(left: Any, right: Any) -> bool:
        # Preserve every qualifier, including extra/nested fields, without
        # Python's bool/int equality or coercion of unsupported values.
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            if any(type(key) is not str for key in (*left, *right)):
                refuse()
            return left.keys() == right.keys() and all(
                same_typed_reference(left[key], right[key]) for key in left
            )
        if type(left) is list:
            return len(left) == len(right) and all(
                same_typed_reference(old, new) for old, new in zip(left, right)
            )
        if left is None or type(left) in (str, bool, int, float):
            return left == right
        refuse()

    # Normalization may derive current mechanics, but cannot remap a physical
    # owner or silently acquire a different linked source for this read path.
    for identity, item in incoming_owners.items():
        normalized = normalized_owners[identity]
        try:
            if not all(same_typed_reference(old, new) for old, new in zip(
                    source_binding(item), source_binding(normalized))):
                refuse()
        except RecursionError:
            refuse()

    payload = _reconcile_numeric_pools(
        definition, deepcopy(state), source_authority=source_authority,
    )
    payload = _reconcile_current_hp(definition, payload, source_authority=source_authority)
    if quarantine and (activation_frame_digest(payload.get("inventory")) != activation_frame_digest(state.get("inventory"))
            or ("equipment_activation" in payload) != ("equipment_activation" in state)
            or activation_frame_digest(payload.get("equipment_activation")) != activation_frame_digest(state.get("equipment_activation"))):
        refuse()
    return payload


def merge_state_with_definition(
    definition: CharacterDefinition,
    state: dict[str, Any],
    *,
    hp_delta: int = 0,
    inventory_quantity_overrides: dict[str, int] | None = None,
    inventory_state_overrides: dict[str, dict[str, Any]] | None = None,
    removed_resource_ids: set[str] | None = None,
    prior_definition: CharacterDefinition | None = None,
    explicit_removed_item_id: str | None = None,
    source_authority: Any | None = None,
) -> dict[str, Any]:
    if is_xianxia_system(definition.system):
        if explicit_removed_item_id:
            raise CharacterStateValidationError("DND equipment removal cannot be applied to this system.")
        return _merge_xianxia_state_with_definition(
            definition,
            state,
            inventory_quantity_overrides=inventory_quantity_overrides,
            inventory_state_overrides=inventory_state_overrides,
        )

    from .committed_publication import active
    if source_authority is None and active():
        raise CharacterStateValidationError("Character numeric authority is unavailable.")

    from .character_equipment_activation import activation_marker, analyze_activation
    if explicit_removed_item_id:
        if prior_definition is None:
            raise CharacterStateValidationError("Explicit equipment removal needs the prior Character identity.")
        state = prospective_exact_item_removal_state(
            prior_definition, definition, state, explicit_removed_item_id,
        )

    activation_analysis = analyze_activation(definition, state)
    activation_issues = [row for row in activation_analysis["rows"]
                         if row["status"] not in {"exact", "new_definition_row"}]
    if activation_analysis["blocked"] and (
        activation_issues or any(w["code"] == "activation_migration_required"
                                 for w in activation_analysis["warnings"])
    ):
        raise CharacterStateValidationError(
            "Equipment activation identity needs manager repair before this Character update."
        )

    payload = deepcopy(state)
    payload = _reconcile_numeric_pools(
        definition, payload, source_authority=source_authority,
        removed_resource_ids=removed_resource_ids,
    )

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
    for override in state_overrides.values():
        _require_typed_activation_values(override)
    for item_id, override in dict(inventory_state_overrides or {}).items():
        if "notes" not in override:
            continue
        if (not isinstance(item_id, str) or not item_id or item_id != item_id.strip()
                or not isinstance(override["notes"], str)
                or set(override) - {"notes", "is_equipped", "is_attuned", "weapon_wield_mode", "active_infusions"}):
            raise CharacterStateValidationError("Item note state intent is invalid.")
        _inventory_note_target(definition, state, item_id)
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
        quantity = int(
            quantity_overrides[catalog_ref]
            if catalog_ref in quantity_overrides
            else existing_item["quantity"]
            if existing_item is not None and "quantity" in existing_item
            else catalog_item.get("default_quantity") or 0
        )
        activation_inputs = {
            field: existing_item[field] if existing_item is not None and field in existing_item else catalog_item[field]
            for field in ("is_equipped", "is_attuned", "weapon_wield_mode")
            if (existing_item is not None and field in existing_item) or field in catalog_item
        }
        _require_typed_activation_values(activation_inputs)
        merged_item = build_inventory_state(
            {**catalog_item, **activation_inputs}, quantity=quantity, strict_activation=True)
        if existing_item is not None:
            _require_typed_activation_values(existing_item)
            merged_item["is_equipped"] = bool(existing_item.get("is_equipped", merged_item.get("is_equipped", False)))
            merged_item["is_attuned"] = bool(existing_item.get("is_attuned", merged_item.get("is_attuned", False)))
            merged_item["charges_current"] = existing_item.get("charges_current", merged_item.get("charges_current"))
            merged_item["charges_max"] = existing_item.get("charges_max", merged_item.get("charges_max"))
            if "active_infusions" in existing_item:
                merged_item["active_infusions"] = normalize_active_infusions(
                    existing_item.get("active_infusions")
                )
            if "notes" in existing_item:
                merged_item["notes"] = existing_item["notes"]
            if "tags" in existing_item:
                merged_item["tags"] = list(existing_item.get("tags") or [])
            if "weapon_wield_mode" in existing_item:
                merged_item["weapon_wield_mode"] = _normalize_weapon_wield_mode_value(
                    existing_item.get("weapon_wield_mode")
                )
        item_state_override = state_overrides.get(catalog_ref)
        if item_state_override:
            if "notes" in item_state_override:
                merged_item["notes"] = item_state_override["notes"]
            if "is_equipped" in item_state_override:
                merged_item["is_equipped"] = bool(item_state_override.get("is_equipped"))
            if "is_attuned" in item_state_override:
                merged_item["is_attuned"] = bool(item_state_override.get("is_attuned"))
            if "weapon_wield_mode" in item_state_override:
                override_weapon_wield_mode = _normalize_weapon_wield_mode_value(
                    item_state_override.get("weapon_wield_mode")
                )
                if override_weapon_wield_mode:
                    merged_item["weapon_wield_mode"] = override_weapon_wield_mode
                    merged_item["is_equipped"] = True
                else:
                    merged_item["weapon_wield_mode"] = ""
            if "active_infusions" in item_state_override:
                active_infusions = normalize_active_infusions(item_state_override.get("active_infusions"))
                if active_infusions:
                    merged_item["active_infusions"] = active_infusions
                else:
                    merged_item.pop("active_infusions", None)
        merged_inventory.append(merged_item)

    for item in existing_inventory:
        if item.get("unlinked_activation_discarded"):
            merged_inventory.append(deepcopy(item))
            continue
        catalog_ref = _inventory_item_ref(item)
        if catalog_ref and catalog_ref in tracked_inventory_refs:
            continue
        if catalog_ref:
            continue
        merged_inventory.append(deepcopy(item))
    payload["inventory"] = merged_inventory
    payload["equipment_activation"] = activation_marker(definition)
    payload["attunement"] = _normalize_attunement_state(payload.get("attunement"), merged_inventory)

    return _reconcile_current_hp(
        definition, payload, source_authority=source_authority, hp_delta=hp_delta,
    )


def _merge_xianxia_state_with_definition(
    definition: CharacterDefinition,
    state: dict[str, Any],
    *,
    inventory_quantity_overrides: dict[str, int] | None = None,
    inventory_state_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    initial_state = _build_xianxia_initial_state(definition)
    payload = deepcopy(state or {})

    payload["status"] = str(payload.get("status") or definition.status)
    payload["resources"] = []
    payload["spell_slots"] = []

    existing_inventory = list(payload.get("inventory") or initial_state.get("inventory") or [])
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
    merged_inventory: list[dict[str, Any]] = []
    for item in existing_inventory:
        merged_item = deepcopy(item)
        item_ref = _inventory_item_ref(merged_item)
        if item_ref in quantity_overrides:
            merged_item["quantity"] = quantity_overrides[item_ref]
        item_state_override = state_overrides.get(item_ref)
        if item_state_override:
            if "is_equipped" in item_state_override:
                merged_item["is_equipped"] = bool(item_state_override.get("is_equipped"))
            if "is_attuned" in item_state_override:
                merged_item["is_attuned"] = bool(item_state_override.get("is_attuned"))
            if "weapon_wield_mode" in item_state_override:
                override_weapon_wield_mode = _normalize_weapon_wield_mode_value(
                    item_state_override.get("weapon_wield_mode")
                )
                if override_weapon_wield_mode:
                    merged_item["weapon_wield_mode"] = override_weapon_wield_mode
                    merged_item["is_equipped"] = True
                else:
                    merged_item.pop("weapon_wield_mode", None)
        merged_inventory.append(merged_item)
    payload["inventory"] = merged_inventory
    payload["currency"] = dict(payload.get("currency") or initial_state.get("currency") or {})
    payload["attunement"] = _normalize_attunement_state(payload.get("attunement"), merged_inventory)
    payload["notes"] = _normalize_notes_payload(payload.get("notes"))
    payload["xianxia"] = _normalize_xianxia_state_from_shared_state(definition, payload)
    payload["vitals"] = {
        "current_hp": int(payload["xianxia"]["vitals"]["current_hp"]),
        "temp_hp": int(payload["xianxia"]["vitals"]["temp_hp"]),
    }
    return payload


def validate_state(
    definition: CharacterDefinition, state: dict[str, Any], *,
    source_authority: Any | None = None,
    previous_state: dict[str, Any] | None = None,
    initial_item_charge_id: str | None = None,
) -> dict[str, Any]:
    payload = deepcopy(state)
    is_xianxia = is_xianxia_system(definition.system)
    if not is_xianxia:
        for item in payload.get("inventory") or []:
            _require_typed_activation_values(item)
    from .committed_publication import active
    if source_authority is None and previous_state is not None and not is_xianxia and active():
        raise CharacterStateValidationError("Character numeric authority is unavailable.")
    raw_xianxia_state = dict(payload.get("xianxia") or {}) if is_xianxia else {}
    if is_xianxia and not isinstance(payload.get("vitals"), dict) and isinstance(raw_xianxia_state.get("vitals"), dict):
        payload["vitals"] = raw_xianxia_state.get("vitals")

    vitals = dict(payload.get("vitals") or {})
    hp_status = source_authority.field_status("stats.max_hp") if source_authority is not None and not is_xianxia else None
    max_hp = xianxia_hp_max(definition) if is_xianxia else int(
        hp_status.effective if hp_status is not None and hp_status.is_effective
        else definition.stats.get("max_hp") or 0
    )
    current_hp = int(vitals.get("current_hp") or 0)
    temp_hp = int(vitals.get("temp_hp") or 0)
    if hp_status is not None and not hp_status.is_effective:
        previous_hp = dict((previous_state or {}).get("vitals") or {}).get("current_hp")
        if previous_state is None or vitals.get("current_hp") != previous_hp:
            raise CharacterStateValidationError("HP maximum needs repair before HP can change.")
    elif not is_xianxia and (current_hp < 0 or current_hp > max_hp):
        raise CharacterStateValidationError(
            f"current_hp must be between 0 and {max_hp}, got {current_hp}"
        )
    if not is_xianxia and temp_hp < 0:
        raise CharacterStateValidationError("temp_hp cannot be negative")
    normalized_vitals = {
        "current_hp": current_hp,
        "temp_hp": temp_hp,
    }
    if not is_xianxia:
        normalized_vitals["death_saves"] = {
            "successes": int((vitals.get("death_saves") or {}).get("successes") or 0),
            "failures": int((vitals.get("death_saves") or {}).get("failures") or 0),
        }
    payload["vitals"] = normalized_vitals
    if is_xianxia:
        payload.pop("hit_dice", None)
    elif source_authority is None:
        payload = normalize_hit_dice_state_payload(definition, payload)
    else:
        if previous_state is None:
            raise CharacterStateValidationError("Previous state is required for guarded Hit Dice writes.")
        def disputed_pools(source: dict[str, Any]) -> list[Any]:
            return [deepcopy(pool) for pool in list(dict(source.get("hit_dice") or {}).get("pools") or [])
                    if not isinstance(pool, dict) or not source_authority.resource_status(
                        "hit_die", str(pool.get("faces") or "")
                    ).is_effective]
        if disputed_pools(payload) != disputed_pools(previous_state):
            raise CharacterStateValidationError("An unverified Hit Die pool changed during this write.")
        verified_faces = {
            int(pool["faces"]) for pool in [*derive_hit_dice_max_pools(definition),
                *list(dict(payload.get("hit_dice") or {}).get("pools") or [])]
            if isinstance(pool, dict) and type(pool.get("faces")) is int
            and source_authority.resource_status("hit_die", str(pool["faces"])).is_effective
        }
        payload = normalize_verified_hit_dice_state_payload(definition, payload, verified_faces)
    if is_xianxia:
        payload["resources"] = []
        payload["spell_slots"] = []
    if source_authority is not None and not is_xianxia:
        if previous_state is None:
            raise CharacterStateValidationError("Previous state is required for guarded Character writes.")
        withheld_ids = set(dict(definition.source or {}).get(
            "item_transition_withheld_resources") or [])
        for family in ("resources", "spell_slots"):
            kind = "resource" if family == "resources" else "spell_slot"
            def unknown_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
                selected = []
                for row in rows:
                    stable_id = (str(row.get("id") or "").strip() if family == "resources"
                                 else f"{normalize_spell_slot_lane_id(row.get('slot_lane_id'))}:{int(row.get('level') or 0)}")
                    if family == "resources" and stable_id in withheld_ids:
                        continue
                    if not source_authority.resource_status(kind, stable_id).is_effective:
                        selected.append(row)
                return selected
            prior_rows = list(previous_state.get(family) or [])
            next_rows = list(payload.get(family) or [])
            for resource_id in withheld_ids if family == "resources" else ():
                prior_matches = [row for row in prior_rows if isinstance(row, dict)
                                 and str(row.get("id") or "").strip() == resource_id]
                next_matches = [row for row in next_rows if isinstance(row, dict)
                                and str(row.get("id") or "").strip() == resource_id]
                if len(prior_matches) != 1 or len(next_matches) != 1:
                    raise CharacterStateValidationError("Withheld resource identity changed.")
                expected = dict(prior_matches[0])
                expected.update(current=None, max=None, authority_status="Needs repair")
                if next_matches[0] != expected:
                    raise CharacterStateValidationError("Withheld resource state changed.")
            if unknown_rows(next_rows) != unknown_rows(prior_rows):
                raise CharacterStateValidationError("An unverified Character pool changed during this write.")

    normalized_resources = []
    for resource in payload.get("resources") or []:
        resource_id = str(resource.get("id") or "").strip()
        if resource_id in set(dict(definition.source or {}).get(
                "item_transition_withheld_resources") or []):
            normalized_resources.append(deepcopy(resource))
            continue
        status = source_authority.resource_status("resource", resource_id) if source_authority is not None and not is_xianxia else None
        if status is not None and not status.is_effective:
            normalized_resources.append(deepcopy(resource))
            continue
        current = int(resource.get("current") or 0)
        if status is not None and not isinstance(status.effective, dict):
            raise CharacterStateValidationError("Verified resource metadata is incomplete.")
        max_value = status.effective.get("max") if status is not None else resource.get("max")
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
        status = source_authority.resource_status("spell_slot", f"{lane_id}:{level}") if source_authority is not None and not is_xianxia else None
        if status is not None and not status.is_effective:
            normalized_slots.append(deepcopy(slot))
            continue
        if status is not None and not isinstance(status.effective, dict):
            raise CharacterStateValidationError("Verified spell slot metadata is incomplete.")
        max_slots = int(
            status.effective.get("max") if status is not None
            else slot.get("max") or slot_limits.get((lane_id, level)) or 0
        )
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
    if source_authority is not None and not is_xianxia:
        cleared_charges = set(dict(definition.source or {}).get(
            "item_transition_cleared_charges") or [])
        prior_charges = {
            str(item.get("id") or "").strip(): (item.get("charges_current"), item.get("charges_max"))
            for item in list((previous_state or {}).get("inventory") or []) if isinstance(item, dict)
        }
        for item in list(payload.get("inventory") or []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            catalog_id = str(item.get("catalog_ref") or item_id).strip()
            pair = (item.get("charges_current"), item.get("charges_max"))
            if catalog_id in cleared_charges and pair == (None, None):
                if (sum(1 for row in payload.get("inventory") or []
                        if isinstance(row, dict) and str(row.get("catalog_ref") or row.get("id") or "").strip() == catalog_id) != 1):
                    raise CharacterStateValidationError("Relinked item charges changed.")
                continue
            # A clearing marker records the earlier source transition. It
            # cannot authorize current uses or permanently prevent a later
            # explicit bounded admission to the new qualified source.
            prior_pair = prior_charges.get(item_id, (None, None))
            rule = source_authority.item_counter_rule(definition, item_id)
            if pair != prior_pair and rule is not None:
                from .character_item_capabilities import known_counter
                if (sum(isinstance(other, dict) and other.get("id") == item_id for other in payload.get("inventory", [])) != 1
                        or (item.get("catalog_ref") or item_id) != rule["catalog_id"]
                        or type(item.get("quantity")) is not int or item["quantity"] != 1
                        or not known_counter(item, rule["maximum"])
                        or (prior_pair == (None, None) and initial_item_charge_id != item_id)
                        or (prior_pair != (None, None)
                            and not source_authority.resource_status("item_charge", item_id).is_effective)):
                    raise CharacterStateValidationError("Item uses need a known bounded source-owned count or explicit manager admission.")
                continue
            if rule is None and source_authority.resource_status("item_charge", item_id).is_effective:
                # Preserve the existing qualified numeric-witness receiver for
                # items outside the new source-owned counter contract.
                continue
            if pair != prior_pair:
                raise CharacterStateValidationError("Item charges need manager repair before they can change.")
    for item in payload.get("inventory") or []:
        quantity = int(item.get("quantity") or 0)
        if quantity < 0:
            raise CharacterStateValidationError(
                f"inventory quantity for '{item.get('name')}' cannot be negative"
            )
        if is_xianxia:
            normalized_item = normalize_xianxia_inventory_row(item)
            if not normalized_item:
                continue
            normalized_inventory.append(normalized_item)
            continue
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
        weapon_wield_mode = _normalize_weapon_wield_mode_value(item.get("weapon_wield_mode"))
        normalized_inventory[-1]["weapon_wield_mode"] = weapon_wield_mode
        active_infusions = normalize_active_infusions(item.get("active_infusions"))
        if active_infusions:
            normalized_inventory[-1]["active_infusions"] = active_infusions
        if item.get("unlinked_activation_discarded"):
            normalized_inventory[-1]["unlinked_activation_discarded"] = True
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
    payload["notes"] = _normalize_notes_payload(payload.get("notes"))
    if "feature_states" in payload:
        feature_states = _normalize_feature_states_payload(payload.get("feature_states"))
        if feature_states:
            payload["feature_states"] = feature_states
        else:
            payload.pop("feature_states", None)
    if not is_xianxia and "exhaustion_level" in payload:
        payload["exhaustion_level"] = max(
            0,
            min(6, int(payload.get("exhaustion_level") or 0)),
        )
    if is_xianxia:
        payload["resources"] = []
        payload["spell_slots"] = []
        payload["xianxia"] = _normalize_xianxia_state_from_shared_state(definition, payload)
        payload["vitals"] = {
            "current_hp": int(payload["xianxia"]["vitals"]["current_hp"]),
            "temp_hp": int(payload["xianxia"]["vitals"]["temp_hp"]),
        }
    else:
        payload.pop("xianxia", None)
    payload["status"] = str(payload.get("status") or definition.status)
    if (initial_item_charge_id is not None
            and activation_frame_digest(payload) != activation_frame_digest(state)):
        raise CharacterStateValidationError("Initial item uses cannot normalize unrelated current-state observations.")
    return payload


def _normalize_feature_states_payload(value: Any) -> dict[str, Any]:
    from .divine_avatar_forms import normalize_divine_avatar_forms_state

    payload = dict(value or {}) if isinstance(value, dict) else {}
    normalized: dict[str, Any] = {}
    for key in SUPPORTED_FEATURE_STATE_KEYS:
        if key == "divine_avatar_forms":
            if key in payload:
                normalized[key] = normalize_divine_avatar_forms_state(payload.get(key))
            continue
        state = dict(payload.get(key) or {}) if isinstance(payload.get(key), dict) else {}
        if not state:
            continue
        normalized[key] = {
            "enabled": bool(state.get("enabled")),
        }
    return normalized


def _normalize_notes_payload(value: Any) -> dict[str, Any]:
    notes = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "player_notes_markdown": str(notes.get("player_notes_markdown") or ""),
        "physical_description_markdown": str(notes.get("physical_description_markdown") or ""),
        "background_markdown": str(notes.get("background_markdown") or ""),
        "session_notes": list(notes.get("session_notes") or []),
    }


def _normalize_xianxia_state_from_shared_state(
    definition: CharacterDefinition,
    payload: dict[str, Any],
) -> dict[str, Any]:
    raw_xianxia = dict(payload.get("xianxia") or {})
    raw_vitals = dict(raw_xianxia.get("vitals") or {})
    shared_vitals = dict(payload.get("vitals") or {})
    if "current_hp" in shared_vitals:
        raw_vitals["current_hp"] = int(shared_vitals.get("current_hp") or 0)
    if "temp_hp" in shared_vitals:
        raw_vitals["temp_hp"] = int(shared_vitals.get("temp_hp") or 0)
    raw_xianxia["vitals"] = raw_vitals
    raw_inventory = (
        dict(raw_xianxia.get("inventory") or {})
        if isinstance(raw_xianxia.get("inventory"), dict)
        else {}
    )
    raw_xianxia["inventory"] = {
        **raw_inventory,
        "enabled": bool(raw_inventory.get("enabled")) or bool(payload.get("inventory")),
        "quantities": list(payload.get("inventory") or raw_inventory.get("quantities") or []),
    }
    raw_xianxia["notes"] = {
        **(
            dict(raw_xianxia.get("notes") or {})
            if isinstance(raw_xianxia.get("notes"), dict)
            else {}
        ),
        "player_notes_markdown": str((payload.get("notes") or {}).get("player_notes_markdown") or ""),
    }
    return normalize_xianxia_state_payload(definition, raw_xianxia)
