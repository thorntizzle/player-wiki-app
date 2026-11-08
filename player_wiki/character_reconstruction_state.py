"""Validate reconstruction compatibility without normalizing old observations."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character_store import CharacterStateConflictError, PreparedCharacterState


def prepare_exact_reconstruction_state(prior_record, definition, state, authority, *, exact_state_json=None,
                                       mapping_proof=None, actor_id=None, spell_origin_proof=None,
                                       native_result=None, source_read_owner=None):
    """Return the existing tuple's value; absence, null and opaque fields survive.

    This is deliberately not ordinary merge/initial-state validation. Only
    known numeric observations and their exact owner mappings are checked.
    Unknown observations do not become zero or get initialized by this write.
    """
    import json
    from .character_hit_dice import derive_hit_dice_max_pools
    from .character_spell_slots import spell_slot_lanes_from_spellcasting

    def fail(message):
        raise CharacterStateConflictError(message)

    from .character_equipment_activation import activation_frame_digest
    if activation_frame_digest(state) != activation_frame_digest(prior_record.state_record.state) or authority is None:
        fail("Reconstruction requires the exact existing Character state.")
    if (definition.campaign_slug, definition.character_slug) != (
            prior_record.definition.campaign_slug, prior_record.definition.character_slug):
        fail("Reconstruction cannot change Character identity.")
    if native_result is not None and spell_origin_proof is not None:
        fail("Native readiness and reviewed publication require separate proof contexts.")
    if spell_origin_proof is not None:
        from .character_reconciliation import PendingReviewedSourceProof
        if not isinstance(spell_origin_proof, PendingReviewedSourceProof):
            fail("Exact native state requires the reviewed pending proof.")
        spell_origin_proof.require_complete()
    from .character_equipment_activation import require_update_activation
    if native_result is not None:
        # Read-only pre-Review validation of actual producer output. This is
        # not a pending write capability and never replaces one at Apply.
        from .character_native_requalification import NativeRequalification, native_requalification_state
        from .character_equipment_activation import native_activation_readiness
        if mapping_proof is not None or not isinstance(native_result, NativeRequalification):
            fail("Native readiness requires genuine producer output.")
        native_result.validate_binding(prior_record, actor_id)
        if (activation_frame_digest(native_result.candidate.to_dict()) != activation_frame_digest(definition.to_dict())
                or activation_frame_digest(native_requalification_state(prior_record, native_result, actor_id))
                   != activation_frame_digest(state)):
            fail("Native readiness changed before Review.")
        native_activation_readiness(prior_record, definition, state, final=True)
    else:
        require_update_activation(prior_record, definition, state,
            reconstruction=mapping_proof, actor_id=actor_id,
            native_proof=(spell_origin_proof if spell_origin_proof is not None
                and spell_origin_proof.native_result is not None else None),
            source_read_owner=source_read_owner)
    def indexed(rows, key, label, *, observations=None):
        result = {}
        if not isinstance(rows, list):
            return result
        for row in rows:
            if not isinstance(row, dict):
                continue  # Opaque retained observations are not new owners.
            identity = key(row)
            try:
                hash(identity)
                valid = bool(identity) and (not isinstance(identity, tuple) or all(identity))
            except TypeError:
                valid = False
            if not valid:
                if observations is not None and not any(type(row.get(name)) is int for name in observations):
                    continue
                fail(f"Reconstruction found a missing {label} owner.")
            if identity in result:
                fail(f"Reconstruction found an ambiguous {label} owner.")
            result[identity] = row
        return result

    old_items = indexed(prior_record.definition.equipment_catalog, lambda row: row.get("id"), "equipment")
    new_items = indexed(definition.equipment_catalog, lambda row: row.get("id"), "equipment")
    if set(old_items) != set(new_items):
        fail("Reconstruction must retain every physical item owner.")
    for identity in old_items:
        mapped = False
        for key in ("entry_key", "source_id", "slug"):
            if dict(old_items[identity].get("systems_ref") or {}).get(key) != dict(new_items[identity].get("systems_ref") or {}).get(key):
                from .character_reconstruction_authority import PendingNativeReconstruction
                if not (isinstance(mapping_proof, PendingNativeReconstruction)
                        and mapping_proof.permits_item_mapping(prior_record, definition, identity)):
                    fail("An equipment source mapping needs exact authenticated reconstruction proof.")
                mapped = True
        if not mapped and activation_frame_digest(old_items[identity]) != activation_frame_digest(new_items[identity]):
            fail("Reconstruction must preserve every unmapped physical owner's content.")
    inventory = state.get("inventory")
    if isinstance(inventory, list):
        observed = {}
        for item in inventory:
            if not isinstance(item, dict):
                continue
            identity, catalog = item.get("id"), item.get("catalog_ref")
            identity = identity if isinstance(identity, str) and identity.strip() else None
            catalog = catalog if isinstance(catalog, str) and catalog.strip() else None
            if identity and catalog and identity != catalog:
                fail("A retained physical item has conflicting inventory owner identities.")
            owner = catalog or identity
            numeric = any(type(item.get(key)) is int for key in ("quantity", "charges_current", "charges_max"))
            if owner:
                if owner in observed:
                    fail("Retained inventory rows have an ambiguous physical item owner.")
                observed[owner] = item
            if numeric and owner not in new_items:
                fail("A retained numeric inventory observation has no exact physical item owner.")
            for key in ("quantity", "charges_current", "charges_max"):
                if type(item.get(key)) is int and item[key] < 0:
                    fail("A retained inventory observation is negative.")
            if (type(item.get("charges_current")) is int and type(item.get("charges_max")) is int
                    and item["charges_current"] > item["charges_max"]):
                fail("Retained item charges exceed their observed maximum.")
    old_spells = indexed(dict(prior_record.definition.spellcasting or {}).get("spells", []), lambda row: row.get("id"), "spell")
    new_spells = indexed(dict(definition.spellcasting or {}).get("spells", []), lambda row: row.get("id"), "spell")
    plan = native_result.provenance.get("spell_origin_plan") if native_result is not None else None
    if spell_origin_proof is not None:
        from .character_reconciliation import PendingReviewedSourceProof
        if not isinstance(spell_origin_proof, PendingReviewedSourceProof):
            fail("Spell-origin correction requires the exact reviewed pending proof.")
        plan = spell_origin_proof.native_spell_origin_delta(prior_record, definition, state, actor_id,
                                                          source_read_owner=source_read_owner)
    removed = {row["spell_id"] for row in plan["removed"]} if plan is not None else set()
    automatic = {row["spell_id"] for row in plan["automatic"]} if plan is not None else set()
    preparation_ids = set()
    if plan is not None and plan.get("schema_version") in {3, 4, 5}:
        from .character_spell_reconstruction import validate_saved_spell_checkpoint
        validate_saved_spell_checkpoint(prior_record.definition, definition, plan["current_checkpoint"])
        if plan["schema_version"] == 5:
            if plan["current_checkpoint"]["schema_version"] != 3:
                fail("Explicit current preparations need their exact checkpoint.")
            preparation_ids = {entry["spell_id"] for entry in plan["current_checkpoint"]["entries"]
                               if entry["role"] in {"prepared", "available"}}
    if not removed <= set(old_spells) or set(old_spells) - removed != set(new_spells):
        fail("Reconstruction must retain every existing spell identity.")
    for identity, old in old_spells.items():
        if identity in removed:
            continue
        current = new_spells[identity]
        if plan is not None and plan.get("schema_version") == 2 and old != current:
            fail("Feature-grant migration must preserve every raw spell observation.")
        for key in ("class_row_id", "spell_source_row_id", "is_prepared", "prepared", "always_prepared", "is_always_prepared"):
            if identity in preparation_ids and key in {"is_prepared", "prepared"}:
                continue  # Exact alias changes were validated against the real original above.
            if (plan is not None and plan.get("schema_version") == 1
                    and identity in automatic and key in {"always_prepared", "is_always_prepared"}):
                continue  # The authenticated exact whole-book delta checked above owns only these flags.
            if (key in old) != (key in current) or old.get(key) != current.get(key):
                fail("Reconstruction cannot change a spell owner or current prepared selection.")

    def check_number(row, key, maximum, label):
        if key not in row or row[key] is None or type(row[key]) is not int:
            return  # Retain unknown/opaque legacy representations exactly.
        if row[key] < 0 or type(maximum) is int and row[key] > maximum:
            fail(f"The retained {label} is incompatible with its reconstructed maximum.")

    vitals = state.get("vitals")
    if isinstance(vitals, dict):
        hp = authority.field_status("stats.max_hp")
        if not hp.is_effective:
            fail("The reconstructed HP maximum is not qualified.")
        check_number(vitals, "current_hp", hp.effective, "current HP")
        check_number(vitals, "temp_hp", None, "temporary HP")
    templates = indexed(definition.resource_templates, lambda row: row.get("id"), "resource")
    prior_templates = indexed(prior_record.definition.resource_templates, lambda row: row.get("id"), "resource")
    if set(templates) != set(prior_templates):
        fail("Reconstruction needs an exact retained resource-owner mapping.")
    native_owner_result = (native_result if spell_origin_proof is None
                           else spell_origin_proof.native_result)
    for identity, old in prior_templates.items():
        for key in ("class_row_id", "feature_id", "item_id", "page_ref", "systems_ref", "reset_on", "reset_to", "rest_behavior"):
            if (key in old) != (key in templates[identity]) or old.get(key) != templates[identity].get(key):
                if key == "class_row_id":
                    from .character_reconstruction_authority import PendingNativeReconstruction
                    if (isinstance(mapping_proof, PendingNativeReconstruction)
                            and mapping_proof.permits_resource_owner_mapping(prior_record, definition, identity)):
                        continue
                    from .character_native_requalification import NativeRequalification
                    if (type(native_owner_result) is NativeRequalification
                            and native_owner_result.permits_resource_owner_mapping(
                                prior_record, definition, identity, actor_id)):
                        continue
                fail("A resource owner or reset policy needs a separate disposition.")
    resource_rows = state.get("resources") if isinstance(state.get("resources"), list) else []
    # Ownerless opaque rows are retained observations, not automatic resource
    # owners. A numeric counter/capacity still requires an exact owner.
    owned_resource_rows = []
    for row in resource_rows:
        if not isinstance(row, dict):
            continue
        identity = row.get("id")
        numeric = any(type(row.get(key)) is int for key in ("current", "max"))
        if not isinstance(identity, str) or not identity.strip():
            if numeric:
                fail("A retained numeric resource observation has no exact owner.")
            continue
        owned_resource_rows.append(row)
    indexed(owned_resource_rows, lambda row: row["id"], "resource observation")
    for row in resource_rows:
        if isinstance(row, dict):
            identity = row.get("id")
            if not isinstance(identity, str) or identity not in templates:
                if any(type(row.get(key)) is int for key in ("current", "max")):
                    fail("A retained numeric resource observation has no exact owner.")
                continue
            check_number(row, "current", templates[row["id"]].get("max"), "resource use")
    slots = {(lane.get("id"), row.get("level")): row.get("max_slots")
             for lane in spell_slot_lanes_from_spellcasting(definition.spellcasting)
             for row in lane.get("slot_progression", []) if isinstance(row, dict)}
    slot_rows = state.get("spell_slots")
    if isinstance(slot_rows, list):
        def slot_identity(row):
            return ((row["slot_lane_id"], row["level"])
                    if isinstance(row.get("slot_lane_id"), str) and row["slot_lane_id"]
                    and type(row.get("level")) is int and row["level"] > 0 else None)
        indexed(slot_rows, slot_identity, "spell-slot", observations=("used", "max"))
        for row in slot_rows:
            if isinstance(row, dict):
                identity = slot_identity(row)
                if identity in slots:
                    check_number(row, "used", slots[identity], "spent spell slots")
                elif any(type(row.get(key)) is int for key in ("used", "max")):
                    fail("A retained spent-slot observation has no exact owner.")
    maxima = {row["faces"]: row["max"] for row in derive_hit_dice_max_pools(definition)}
    pools = dict(state.get("hit_dice") or {}).get("pools") if isinstance(state.get("hit_dice"), dict) else None
    if isinstance(pools, list):
        def die_identity(row):
            return row["faces"] if type(row.get("faces")) is int and row["faces"] > 0 else None
        indexed(pools, die_identity, "Hit Die", observations=("current", "max"))
        for row in pools:
            if isinstance(row, dict) and die_identity(row) in maxima:
                check_number(row, "current", maxima[row["faces"]], "Hit Dice")
            elif isinstance(row, dict) and any(type(row.get(key)) is int for key in ("current", "max")):
                fail("A retained Hit Die observation has no exact owner.")
    raw = exact_state_json if exact_state_json is not None else json.dumps(state, ensure_ascii=False)
    if activation_frame_digest(json.loads(raw)) != activation_frame_digest(state):
        fail("The exact preserved state serialization changed.")
    return PreparedCharacterState(deepcopy(state), raw)
