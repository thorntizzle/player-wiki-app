from __future__ import annotations

from typing import Any
from copy import deepcopy

from .character_builder_equipment import (
    _normalize_equipment_payloads,
    _normalize_weapon_wield_mode_value,
    describe_equipment_state_support,
)
from .character_editor import CharacterEditValidationError
from .character_equipment_activation import (
    analyze_activation, effective_definition, suppress_unresolved_linked_sources,
)
from .character_mechanics_projection import build_character_inventory_item_ref
from .character_store import CharacterStateConflictError


def build_reserved_equipment_state_update_result(record: Any, item_id: str,
                                                  values: dict[str, object], *, connection: Any):
    """Resolve activation support from sources selected on the writer connection."""
    import json
    from .character_builder_catalogs import _build_item_catalog
    from .committed_character_publication import (
        _create_source_proof, _exact_page_link, _exact_systems_link,
    )
    from .committed_publication import CommittedSourceConflict, page_row
    from .repository import normalize_lookup
    from .systems_store import SystemsStore

    state_rows = list((record.state_record.state or {}).get("inventory") or [])
    if any(not isinstance(row, dict) for row in state_rows):
        raise CharacterStateConflictError("Equipment state needs manager repair.")
    relevant_refs = {item_id}
    relevant_refs.update(
        ref for row in state_rows if bool(row.get("is_attuned"))
        if (ref := build_character_inventory_item_ref(row))
    )
    definition_rows = list(record.definition.equipment_catalog or [])
    if any(not isinstance(row, dict) for row in definition_rows):
        raise CharacterStateConflictError("Equipment definition needs manager repair.")
    definition_relevant = [
        row for row in definition_rows
        if str(row.get("id") or "").strip() in relevant_refs
    ]
    state_relevant = [
        row for row in state_rows
        if build_character_inventory_item_ref(row) in relevant_refs
    ]
    relevant_rows = [
        (str(row.get("id") or "").strip(), row) for row in definition_relevant
    ] + [
        (build_character_inventory_item_ref(row), row) for row in state_relevant
    ]
    pages, entries = set(), set()
    identities: dict[str, set[tuple[str, str]]] = {}
    page_titles: dict[str, list[str]] = {}
    try:
        for index, (ref, row) in enumerate(relevant_rows):
            owner = f"equipment[{index}]"
            page_value, systems_value = row.get("page_ref"), row.get("systems_ref")
            page_claim = "page_ref" in row and page_value not in (None, "", {})
            systems_claim = "systems_ref" in row and systems_value not in (None, "", {})
            if page_claim and systems_claim:
                raise CommittedSourceConflict("Equipment has conflicting source links.")
            if page_claim:
                link = _exact_page_link(page_value, owner, "item")
                pages.add(link)
                identities.setdefault(ref, set()).add(("page", link.identity))
                if isinstance(page_value, dict) and "title" in page_value:
                    title = page_value["title"]
                    if not isinstance(title, str):
                        raise CommittedSourceConflict("Equipment page title is malformed.")
                    if title.strip():
                        page_titles.setdefault(link.identity, []).append(title.strip())
            elif systems_claim:
                link = _exact_systems_link(systems_value, owner, "item")
                entries.add(link)
                identities.setdefault(ref, set()).add((link.source_kind, link.identity))
            elif str(row.get("source_kind") or "").strip().lower() in {
                "page", "campaign_page", "systems", "system"
            }:
                raise CommittedSourceConflict("Equipment source identity is missing.")
        if len(pages) > 64 or len(pages) + len(entries) > 256:
            raise CommittedSourceConflict("Equipment source proof exceeds its bound.")
        proof = (_create_source_proof(record.definition.campaign_slug,
                                     tuple(sorted(pages)), tuple(sorted(entries)),
                                     connection=connection)
                 if pages or entries else None)
        catalog_entries = []
        if proof is not None:
            store = SystemsStore()
            for link in sorted(entries):
                column = "entry_key" if link.source_kind == "systems_key" else "slug"
                rows = connection.execute(
                    f"SELECT * FROM systems_entries WHERE library_slug=? AND {column}=?",
                    (proof.library_slug, link.identity),
                ).fetchall()
                if len(rows) != 1:
                    raise CommittedSourceConflict("Equipment Systems identity is ambiguous.")
                catalog_entries.append(store._map_entry(rows[0]))
        catalog = _build_item_catalog(catalog_entries)
        builtin_names = (set(catalog["phb_weapon_profiles_normalized"])
                         | set(catalog["phb_armor_profiles_normalized"]))
        for is_definition, ref, row in [
            (True, str(item.get("id") or "").strip(), item) for item in definition_relevant
        ] + [
            (False, build_character_inventory_item_ref(item), item) for item in state_relevant
        ]:
            if row.get("page_ref") not in (None, "", {}) or row.get("systems_ref") not in (None, "", {}):
                continue
            if not is_definition and ref in identities:
                if str(row.get("source_kind") or "").strip():
                    raise CommittedSourceConflict("Equipment source identity is contradictory.")
                # Durable inventory state may omit the definition's exact link.
                intrinsic_claims = {identity for kind, identity in identities[ref] if kind == "intrinsic"}
                if intrinsic_claims and normalize_lookup(str(row.get("name") or "")) not in intrinsic_claims:
                    raise CommittedSourceConflict("Equipment intrinsic identity is contradictory.")
                continue
            name_key = normalize_lookup(str(row.get("name") or ""))
            if str(row.get("source_kind") or "").strip() or name_key not in builtin_names:
                raise CommittedSourceConflict("Unlinked equipment has no intrinsic support proof.")
            identities.setdefault(ref, set()).add(("intrinsic", name_key))
        if any(len(claims) != 1 for claims in identities.values()):
            raise CommittedSourceConflict("Equipment source identity is contradictory.")
        trusted_sources = {ref: next(iter(claims)) for ref, claims in identities.items()}
        page_support = {}
        if proof is not None:
            from .character_builder_catalogs import _CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS
            for link in sorted(pages):
                row = page_row(record.definition.campaign_slug, link.identity,
                               connection=connection)
                if row is None:
                    raise CommittedSourceConflict("Equipment Items page is unavailable.")
                if any(title != row["title"] for title in page_titles.get(link.identity, [])):
                    raise CommittedSourceConflict("Equipment Items page identity changed.")
                metadata = json.loads(row["metadata_json"] or "{}")
                page_support[link.identity] = {
                    "page_ref": link.identity, "title": row["title"],
                    "metadata": {key: deepcopy(metadata[key])
                                 for key in _CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS
                                 if key in metadata and metadata[key] not in (None, "", [], {})},
                }
        catalog["campaign_item_support_by_page_ref"] = page_support
        # A row's title is never a source identity in this mutation path.
        catalog["campaign_item_support_by_title"] = {}
    except (CommittedSourceConflict, TypeError, ValueError, KeyError) as exc:
        raise CharacterStateConflictError(
            "Equipment source changed or needs manager repair. Refresh and try again."
        ) from exc
    return build_equipment_state_update_result(
        record.definition.campaign_slug, record, item_id,
        item_catalog=catalog, systems_service=None,
        campaign_page_records=None, values=values,
        reserved_source_proof=True,
        trusted_sources=trusted_sources,
    )


def build_record_equipment_support_lookup(
    record: Any,
    *,
    item_catalog: dict[str, object],
    systems_service: Any,
    campaign_page_records: list[Any] | None = None,
    reserved_source_proof: bool = False,
    reserved_item_id: str = "",
    trusted_sources: dict[str, tuple[str, str]] | None = None,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    projected_definition, _ = effective_definition(record.definition, record.state_record.state)
    if not reserved_source_proof:
        projected_definition, _ = suppress_unresolved_linked_sources(
            projected_definition, record.definition.campaign_slug, systems_service,
            campaign_page_records,
        )
    selected_definition_equipment = list(projected_definition.equipment_catalog or [])
    if reserved_source_proof:
        relevant_refs = {reserved_item_id}
        relevant_refs.update({
            build_character_inventory_item_ref(row)
            for row in list((record.state_record.state or {}).get("inventory") or [])
            if isinstance(row, dict) and bool(row.get("is_attuned"))
        })
        selected_definition_equipment = [
            row for row in selected_definition_equipment
            if str(row.get("id") or "").strip() in relevant_refs
        ]
        if not trusted_sources or any(ref not in trusted_sources for ref in relevant_refs):
            raise CharacterStateConflictError("Equipment source proof is incomplete.")
    normalized_definition_equipment = (
        [normalized for row in selected_definition_equipment
         for normalized in _normalize_equipment_payloads(
             [row], item_catalog=item_catalog,
             trusted_source=(trusted_sources or {}).get(str(row.get("id") or "").strip()),
         )]
        if reserved_source_proof else
        _normalize_equipment_payloads(selected_definition_equipment, item_catalog=item_catalog)
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
            trusted_source=(trusted_sources or {}).get(item_ref) if reserved_source_proof else None,
        )
    return definition_item_lookup, support_lookup


def build_equipment_state_update_result(
    campaign_slug: str,
    record: Any,
    item_id: str,
    *,
    item_catalog: dict[str, object],
    systems_service: Any,
    campaign_page_records: list[Any] | None = None,
    values: dict[str, object],
    reserved_source_proof: bool = False,
    trusted_sources: dict[str, tuple[str, str]] | None = None,
):
    identity = analyze_activation(record.definition, record.state_record.state)
    if identity["blocked"]:
        raise CharacterEditValidationError(
            "Equipment activation identity needs manager repair before updating this item."
        )
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
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        reserved_source_proof=reserved_source_proof,
        reserved_item_id=item_id,
        trusted_sources=trusted_sources,
    )
    target_support = dict(support_lookup.get(item_id) or {})
    if not bool(target_support.get("supports_equipped_state")):
        if reserved_source_proof:
            raise CharacterStateConflictError("Equipment source changed or needs manager repair.")
        raise CharacterEditValidationError(
            "That inventory row stays on Inventory because it does not support equipment state."
        )

    value_payload = dict(values or {})
    for field in ("is_equipped", "is_attuned"):
        if field in value_payload and not isinstance(value_payload[field], bool):
            raise CharacterEditValidationError(f"{field} must be a boolean.")
    weapon_wield_mode = ""
    if bool(target_support.get("supports_weapon_wield_mode")):
        raw_wield_mode = value_payload.get("weapon_wield_mode")
        weapon_wield_mode = _normalize_weapon_wield_mode_value(raw_wield_mode)
        if str(raw_wield_mode or "").strip() and not weapon_wield_mode:
            raise CharacterEditValidationError("Choose a valid wielding mode for that weapon.")
        allowed_modes = [
            _normalize_weapon_wield_mode_value(value)
            for value in list(target_support.get("weapon_wield_modes") or [])
            if _normalize_weapon_wield_mode_value(value)
        ]
        allowed_mode_set = set(allowed_modes)
        if weapon_wield_mode and weapon_wield_mode not in allowed_mode_set:
            if reserved_source_proof:
                raise CharacterStateConflictError("Equipment wielding support changed. Refresh and try again.")
            raise CharacterEditValidationError("Choose a valid wielding mode for that weapon.")
        if not weapon_wield_mode and bool(value_payload.get("is_equipped")) and allowed_modes:
            weapon_wield_mode = allowed_modes[0]
        is_equipped = bool(weapon_wield_mode)
    else:
        is_equipped = bool(value_payload.get("is_equipped"))

    requested_attunement = bool(value_payload.get("is_attuned"))
    if requested_attunement and not bool(target_support.get("supports_attunement")):
        if reserved_source_proof:
            raise CharacterStateConflictError("Equipment attunement support changed. Refresh and try again.")
        raise CharacterEditValidationError(
            "Only items whose durable metadata explicitly requires attunement can be attuned."
        )
    is_attuned = bool(requested_attunement and target_support.get("supports_attunement"))
    attunement_payload = dict((record.state_record.state or {}).get("attunement") or {})
    max_attuned_items = int(attunement_payload.get("max_attuned_items", 3))
    unresolved_attuned_refs = {
        item_ref for item_ref, item in inventory_by_ref.items()
        if item_ref != item_id and bool(item.get("is_attuned", False))
        and not bool(dict(support_lookup.get(item_ref) or {}).get("supports_attunement"))
    }
    if reserved_source_proof and requested_attunement and unresolved_attuned_refs:
        raise CharacterStateConflictError("Attuned equipment support changed or needs manager repair.")
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

    state = deepcopy(record.state_record.state)
    for item in list(state.get("inventory") or []):
        if build_character_inventory_item_ref(item) == item_id:
            item["is_equipped"] = is_equipped
            item["is_attuned"] = is_attuned
            item["weapon_wield_mode"] = weapon_wield_mode
            break
    attunement = dict(state.get("attunement") or {})
    attunement["attuned_item_refs"] = [
        build_character_inventory_item_ref(item)
        for item in list(state.get("inventory") or [])
        if bool(item.get("is_attuned")) and build_character_inventory_item_ref(item)
    ]
    state["attunement"] = attunement
    return state
