"""Explicit additive authentication of an existing physical item's source.

This is not item recovery: no title matching, owner replacement or state change.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from dataclasses import dataclass, field

from .character_source_repair import SourceRepairError


_SAME_PHYSICAL_ISSUER = object()


def _mapping_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PendingSamePhysicalItemMapping:
    """One explicit current source link; no historical choice or state issuance."""
    actor_id: int
    action_id: str
    target_id: str
    prior_revision: int
    state_revision: int
    prior_digest: str
    state_digest: str
    candidate_digest: str
    reference_json: str
    source_digest: str
    _issuer: object = field(repr=False, compare=False)

    @classmethod
    def prepare(cls, record, target_id, selected_key, *, actor_id, action_id, service, pages):
        items = _items(record.definition)
        original = items.get(target_id)
        if original is None or original.get("systems_ref") or not original.get("page_ref"):
            return None
        choices = _candidates(record.definition, original, service, pages)
        if len(choices) != 1 or choices[0]["systems_ref"]["entry_key"] != selected_key:
            return None  # This remains an ordinary source replacement, never an exemption.
        inventory = record.state_record.state.get("inventory")
        matches = [row for row in inventory if isinstance(row, dict)
                   and (row.get("catalog_ref") or row.get("id")) == target_id] if isinstance(inventory, list) else []
        if (len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not matches[0]["id"]
                or sum(isinstance(row, dict) and row.get("id") == matches[0]["id"] for row in inventory) != 1
                or type(actor_id) is not int or actor_id <= 0
                or not isinstance(action_id, str) or not action_id or len(action_id) > 128):
            raise SourceRepairError("Same-physical source adoption needs exact current actor and inventory identity.")
        candidate = deepcopy(record.definition.to_dict())
        selected = next(row for row in candidate["equipment_catalog"] if row["id"] == target_id)
        selected["systems_ref"] = deepcopy(choices[0]["systems_ref"])
        return cls(actor_id, action_id, target_id, record.committed_revision, record.state_record.revision,
            _mapping_digest(record.definition.to_dict()), _mapping_digest(record.state_record.state),
            _mapping_digest(candidate), json.dumps(choices[0]["systems_ref"], sort_keys=True),
            choices[0]["review_source_digest"], _SAME_PHYSICAL_ISSUER)

    def descriptor(self):
        if self._issuer is not _SAME_PHYSICAL_ISSUER:
            raise SourceRepairError("The same-physical source proposal lacks its producer.")
        return {"schema_version": 1, "actor_id": self.actor_id, "action_id": self.action_id,
            "item_id": self.target_id, "prior_revision": self.prior_revision, "state_revision": self.state_revision,
            "prior_definition_digest": self.prior_digest, "state_digest": self.state_digest,
            "candidate_digest": self.candidate_digest, "systems_ref": json.loads(self.reference_json),
            "review_source_digest": self.source_digest}

    @property
    def digest(self):
        return _mapping_digest(self.descriptor())

    def candidate(self, record):
        payload = deepcopy(record.definition.to_dict())
        rows = [row for row in payload["equipment_catalog"] if isinstance(row, dict) and row.get("id") == self.target_id]
        if len(rows) != 1:
            raise SourceRepairError("The same physical owner changed.")
        rows[0]["systems_ref"] = json.loads(self.reference_json)
        self.validate_binding(record, type(record.definition).from_dict(payload), record.state_record.state, self.actor_id)
        return payload

    def validate_binding(self, record, candidate, state, actor_id):
        self.descriptor()
        if (actor_id != self.actor_id or record.committed_revision != self.prior_revision
                or record.state_record.revision != self.state_revision
                or _mapping_digest(record.definition.to_dict()) != self.prior_digest
                or _mapping_digest(record.state_record.state) != self.state_digest
                or _mapping_digest(state) != self.state_digest
                or _mapping_digest(candidate.to_dict()) != self.candidate_digest):
            raise SourceRepairError("The exact same-physical source proposal or retained state changed.")
        expected = deepcopy(record.definition.to_dict())
        rows = [row for row in expected["equipment_catalog"] if isinstance(row, dict) and row.get("id") == self.target_id]
        if len(rows) != 1 or rows[0].get("systems_ref") or not rows[0].get("page_ref"):
            raise SourceRepairError("This is not an additive page-only physical source link.")
        rows[0]["systems_ref"] = json.loads(self.reference_json)
        if candidate.to_dict() != expected:
            raise SourceRepairError("Same-physical adoption cannot change other definition or play facts.")

    def validate_sources(self, record, service, pages):
        self.validate_binding(record, type(record.definition).from_dict(self.candidate(record)),
                              record.state_record.state, self.actor_id)
        original = _items(record.definition)[self.target_id]
        choices = _candidates(record.definition, original, service, pages)
        if (len(choices) != 1 or choices[0]["systems_ref"] != json.loads(self.reference_json)
                or choices[0]["review_source_digest"] != self.source_digest):
            raise SourceRepairError("The current approved physical item/page relation changed.")


def field_name(identity):
    return "item_link_" + hashlib.sha256(identity.encode()).hexdigest()


def _items(definition):
    result = {}
    for row in definition.equipment_catalog:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise SourceRepairError("Physical source mapping needs exact retained item identities.")
        if row["id"] in result:
            raise SourceRepairError("Physical source mapping has an ambiguous item identity.")
        result[row["id"]] = row
    return result


def _candidates(definition, item, service, records):
    from .character_source_authority import _page_ref, _eligible_page_records, _field, _current_systems_entry
    from .campaign_item_mechanics import campaign_item_mechanics_is_approved
    from .character_builder_equipment import _systems_ref_from_entry
    from .character_reconstruction_authority import digest

    page_ref = _page_ref(item.get("page_ref"))
    pages = _eligible_page_records(records).get(page_ref, [])
    if not page_ref or len(pages) != 1:
        return []
    page = _field(pages[0], "page")
    if (_field(page, "section") != "Items" or type(_field(page, "committed_revision")) is not int
            or _field(page, "committed_revision") < 1):
        return []
    loader = getattr(service, "list_enabled_entries_for_campaign", None)
    if not callable(loader):
        return []
    found = {}
    def relation(metadata):
        if not isinstance(metadata, dict) or not campaign_item_mechanics_is_approved(metadata):
            return False
        details = metadata.get("campaign_item_mechanics")
        if details is not None and not isinstance(details, dict):
            return False
        primary = _page_ref(metadata.get("linked_published_page_ref"))
        declarations = [metadata.get("page_ref"), (details or {}).get("source_page_ref")]
        return primary == page_ref and all(not value or _page_ref(value) == page_ref for value in declarations)
    from .character_read_catalogs import read_catalog_source, _CatalogObservation
    source = read_catalog_source(service, definition.campaign_slug, records)
    observation = None if source is None else source.capture("item", builder=False)
    if type(observation) is _CatalogObservation:
        entries = range(len(observation.records))
        entry_field = observation.field
    else:
        entries = (loader(definition.campaign_slug, entry_type="item")
                   if source is None else observation)
        entry_field = getattr
    for entry in entries:
        # Preserve the complete source observation and exact reload of every
        # declared candidate; unrelated records need no mutable construction.
        if entry_field(entry, "entry_type") != "item" or not relation(entry_field(entry, "metadata")):
            continue
        current = _current_systems_entry(definition.campaign_slug, "systems", entry_field(entry, "entry_key"), service)
        if current is None or current.entry_type != "item" or not relation(current.metadata):
            continue
        details = current.metadata.get("campaign_item_mechanics") or {}
        support = {"state": details.get("support_state", current.metadata.get("campaign_item_mechanics_support_state")),
            "modeled_fields": deepcopy(details.get("modeled_fields") or []),
            "pending_clauses": deepcopy(details.get("flags", current.metadata.get("campaign_item_mechanics_flags", [])))}
        found[current.entry_key] = {"systems_ref": _systems_ref_from_entry(current),
            "support_summary": support,
            "review_source_digest": digest({"metadata": current.metadata, "body": current.body,
                "page_ref": page_ref, "page_revision": _field(page, "committed_revision")})}
    return list(found.values()) if len(found) == 1 else []


def choice_fields(definition, service, pages, values):
    from .character_source_authority import _page_ref
    result = []
    for identity, item in _items(definition).items():
        if item.get("systems_ref") or not item.get("page_ref"):
            continue
        candidates = _candidates(definition, item, service, pages)
        options = [{"value": "retain_unqualified", "label": "Retain page evidence; item mechanics remain unqualified"}]
        for candidate in candidates:
            ref = candidate["systems_ref"]
            options.append({"value": ref["entry_key"], "label": f"Authenticate the same physical owner: {ref['title']} · {ref['source_id']} · {ref['entry_key']} ({candidate['support_summary']['state'] or 'supported clauses only'})"})
        result.append({"name": field_name(identity), "item_id": identity,
            "label": str(item.get("name") or identity), "page_ref": _page_ref(item["page_ref"]), "options": options,
            "value": values.get(field_name(identity), ""), "available": bool(candidates)})
    return result


def compose_mappings(prior, payload, service, pages, values):
    from .character_source_authority import _page_ref
    mappings = deepcopy(dict(prior.source.get("native_reconstruction_choices") or {}).get("item_source_mappings") or [])
    items = {row["id"]: row for row in payload["equipment_catalog"]}
    for field in choice_fields(prior, service, pages, values):
        selected = values.get(field["name"])
        if selected not in {option["value"] for option in field["options"]}:
            raise SourceRepairError("Choose explicitly whether to authenticate or retain each page-only physical item.")
        if selected == "retain_unqualified":
            continue
        original = _items(prior)[field["item_id"]]
        candidates = _candidates(prior, original, service, pages)
        if len(candidates) != 1 or candidates[0]["systems_ref"]["entry_key"] != selected:
            raise SourceRepairError("The exact approved item/page relation is unavailable or ambiguous.")
        mapping = {"schema_version": 1, "item_id": field["item_id"], "page_ref": _page_ref(original["page_ref"]),
            "prior_item": deepcopy(original), **deepcopy(candidates[0])}
        items[field["item_id"]]["systems_ref"] = deepcopy(mapping["systems_ref"])
        mappings.append(mapping)
    return mappings


def mapping_shape(mapping):
    from .character_source_authority import _page_ref
    from .character_source_repair import _sha256_hex
    if (not isinstance(mapping, dict) or set(mapping) != {"schema_version", "item_id", "page_ref", "prior_item", "systems_ref", "review_source_digest", "support_summary"}
            or type(mapping.get("schema_version")) is not int or mapping["schema_version"] != 1
            or not isinstance(mapping.get("item_id"), str) or not mapping["item_id"]
            or not isinstance(mapping.get("prior_item"), dict) or mapping["prior_item"].get("id") != mapping["item_id"]
            or mapping["prior_item"].get("systems_ref")
            or not mapping.get("page_ref") or _page_ref(mapping["prior_item"].get("page_ref")) != mapping["page_ref"]
            or not isinstance(mapping.get("systems_ref"), dict) or not mapping["systems_ref"].get("entry_key")
            or not isinstance(mapping.get("support_summary"), dict)
            or not _sha256_hex(mapping.get("review_source_digest"))):
        return False
    return True


def stored_mappings(definition):
    frame = definition.source.get("native_reconstruction_choices")
    mappings = frame.get("item_source_mappings", []) if isinstance(frame, dict) else []
    if not isinstance(mappings, list) or any(not mapping_shape(row) for row in mappings):
        raise SourceRepairError("The retained physical source mappings are invalid.")
    identities = [row["item_id"] for row in mappings]
    if len(identities) != len(set(identities)):
        raise SourceRepairError("The retained physical source mappings are ambiguous.")
    return mappings


def mapped_item(mapping):
    result = deepcopy(mapping["prior_item"])
    result["systems_ref"] = deepcopy(mapping["systems_ref"])
    return result


def validate_mappings(prior, candidate, service=None, pages=None):
    """Independently check the only allowed physical-owner metadata change."""
    old, new = _items(prior), _items(candidate)
    if set(old) != set(new):
        raise SourceRepairError("Reconstruction cannot add or remove a physical owner.")
    before = {row["item_id"]: row for row in stored_mappings(prior)}
    after = {row["item_id"]: row for row in stored_mappings(candidate)}
    if any(after.get(identity) != mapping for identity, mapping in before.items()):
        raise SourceRepairError("An existing authenticated physical mapping cannot be rewritten.")
    for identity, mapping in after.items():
        if identity not in new or (identity not in before and new[identity] != mapped_item(mapping)):
            raise SourceRepairError("A physical source mapping changed its retained owner or content.")
        if identity in before and new[identity] != old[identity]:
            raise SourceRepairError("Reconstruction cannot rewrite an already authenticated physical owner.")
        if identity not in before and old[identity] != mapping["prior_item"]:
            raise SourceRepairError("The physical source mapping does not match the exact prior owner.")
        if service is not None:
            candidates = _candidates(candidate, mapping["prior_item"], service, pages)
            if len(candidates) != 1 or candidates[0]["systems_ref"] != mapping["systems_ref"]:
                raise SourceRepairError("The physical item's current approved page relation is unavailable.")
            if identity not in before and candidates[0]["review_source_digest"] != mapping["review_source_digest"]:
                raise SourceRepairError("The physical item's reviewed source changed.")
            if identity not in before and candidates[0]["support_summary"] != mapping["support_summary"]:
                raise SourceRepairError("The physical item's supported/pending clause review changed.")
    if any(new[identity] != old[identity] for identity in old if identity not in after):
        raise SourceRepairError("Reconstruction cannot rewrite an unmapped physical item.")
    return tuple(deepcopy(list(after.values())))


def current_mapping_matches(definition, item, service, pages):
    """A mapped source still needs its actual current approved page relation."""
    try:
        matches = [row for row in stored_mappings(definition) if row["item_id"] == item.get("id")]
        if not matches:
            return True
        if (len(matches) != 1 or item.get("systems_ref") != matches[0]["systems_ref"]
                or item.get("page_ref") != matches[0]["prior_item"].get("page_ref")):
            return False
        candidates = _candidates(definition, matches[0]["prior_item"], service, pages)
        return len(candidates) == 1 and candidates[0]["systems_ref"] == matches[0]["systems_ref"]
    except (SourceRepairError, TypeError, ValueError):
        return False
