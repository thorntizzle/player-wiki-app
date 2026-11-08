"""One additive physical-source link inside first current spell adoption.

The pending object preserves exact non-entitling observations. It cannot issue
native grant custody or authorize a publication independently of its enclosing
NativeRequalification result.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import json

from .character_reconstruction_items import PendingSamePhysicalItemMapping, _candidates, _items, _mapping_digest
from .character_source_repair import SourceRepairError


_ISSUER = object()


def adoption_options(definition, service, pages):
    """Opaque, indivisible physical-item/current-source pairs; no default."""
    result = []
    for identity, item in _items(definition).items():
        if item.get("systems_ref") or not item.get("page_ref"):
            continue
        for choice in _candidates(definition, item, service, pages):
            ref = choice["systems_ref"]
            result.append({"value": _mapping_digest([identity, ref["entry_key"]]),
                "item_id": identity, "source_key": ref["entry_key"],
                "label": f"{item.get('name') or identity} — {ref['title']} ({ref['source_id']})"})
    return result


def _fail():
    raise SourceRepairError("Atomic item-source and current-spell adoption lost its exact preservation proof.")


def _validate_history_wrappers(history):
    """Close our envelope while leaving authenticated raw row contents intact."""
    from .character_spell_grants import publication_identity
    if type(history) is not list or len(history) > 16:
        _fail()
    fields = {"reason", "item_id", "source_ref", "source_row_id", "source_row", "observation"}
    def identifier(value, maximum=512):
        return (type(value) is str and bool(value) and value == value.strip()
            and len(value.encode("utf-8")) <= maximum and all(ord(char) >= 32 for char in value))
    observations, sources, owner = set(), set(), None
    for row in history:
        if (type(row) is not dict or set(row) != fields
                or type(row["reason"]) is not str or row["reason"] != "modifier_not_entitlement"
                or not identifier(row["item_id"]) or not identifier(row["source_row_id"], 200)
                or not row["source_row_id"].startswith("spell-source:item:")
                or type(row["source_ref"]) is not dict
                or type(row["source_row"]) is not dict or type(row["observation"]) is not dict):
            _fail()
        if publication_identity(row["source_ref"])["entry_type"] != "item":
            _fail()
        observation, source = row["observation"], row["source_row"]
        if (not identifier(observation.get("id")) or observation["id"] in observations
                or row["source_row_id"] in sources
                or source.get("source_row_id") != row["source_row_id"]
                or source.get("source_row_kind") != "item"
                or observation.get("spell_source_row_id") != row["source_row_id"]
                or observation.get("spell_source_row_kind") != "item"
                or observation.get("class_row_id")
                or observation.get("item_owner_ids") not in (None, [row["item_id"]])
                or owner is not None and owner != (row["item_id"], row["source_ref"])):
            _fail()
        observations.add(observation["id"]); sources.add(row["source_row_id"])
        owner = (row["item_id"], row["source_ref"])


def _validate_empty_history_relations(history, entries, edges):
    if not history and (entries != [] or edges != []):
        _fail()


def _history(authority, prior, candidate, item_id, checkpoint, draft):
    from .character_spell_grants import publication_identity, canonical_digest, DraftGrantView
    from .character_spell_properties import FIELD, normalize_item_spell_properties
    from .character_source_authority import _modifier_retention_entries, _modifier_retention_edges, _require_modifier_retention_rows
    if (authority.native_grant_custody_confirmed or type(draft) is not DraftGrantView
            or checkpoint is None or not checkpoint.matches_definition(candidate)):
        _fail()
    entries = authority.spell_property_item_entries(candidate)
    selected = [row for row in entries if row["item_id"] == item_id]
    if authority.status_for("item", item_id) != "VERIFIED" or len(selected) > 1:
        _fail()
    if not selected:
        if FIELD in authority.approved_payload("item", item_id):
            _fail()
        _validate_history_wrappers([])
        _validate_empty_history_relations([], [], [])
        return [], [], []
    history = []
    for effect in normalize_item_spell_properties(selected[0][FIELD]):
        legacy = effect.get("legacy_source_row_id")
        if legacy is None:
            continue
        observations = [row for row in prior.spellcasting.get("spells", [])
            if type(row) is dict and row.get("spell_source_row_id") == legacy]
        sources = [row for row in prior.spellcasting.get("source_rows", [])
            if type(row) is dict and row.get("source_row_id") == legacy]
        if not observations and not sources:
            continue  # This character has no legacy representation to retain.
        owners = [row for row in entries if any(rule.get("legacy_source_row_id") == legacy
            for rule in normalize_item_spell_properties(row[FIELD]))]
        if (len(observations) != 1 or len(sources) != 1 or len(owners) != 1
                or observations[0].get("class_row_id") or not observations[0].get("id")
                or observations[0].get("spell_source_row_kind") != "item"
                or sources[0].get("source_row_kind") != "item"
                or observations[0].get("item_owner_ids") not in (None, [item_id])
                or publication_identity(observations[0].get("systems_ref")) != effect["spell_ref"]):
            _fail()
        # The separate current class spell is source-backed by the real draft
        # and checkpoint. No DRAFT occurrence is promoted into live authority.
        related = [row for row in draft.occurrences
            if row.get("status") == "DRAFT" and row.get("class_row_id") in authority.verified_class_rows
            and publication_identity(row.get("spell_ref")) == effect["spell_ref"]]
        if not related:
            _fail()
        history.append({"reason": "modifier_not_entitlement", "item_id": item_id,
            "source_ref": deepcopy(selected[0]["source_ref"]), "source_row_id": legacy,
            "source_row": deepcopy(sources[0]), "observation": deepcopy(observations[0])})
    _validate_history_wrappers(history)
    _require_modifier_retention_rows(candidate, history)
    entries = _modifier_retention_entries(authority, candidate, history)
    edges = _modifier_retention_edges(authority, history)
    _validate_empty_history_relations(history, entries, edges)
    return history, entries, edges


@dataclass(frozen=True, slots=True)
class PendingAtomicItemSpellAdoption:
    mapping: PendingSamePhysicalItemMapping
    prior_json: str
    state_json: str
    _issuer: object = field(repr=False, compare=False)

    @classmethod
    def prepare(cls, record, request, *, actor_id, action_id, service, pages):
        from .character_spell_grants import has_native_grants
        if (type(request) is not dict or set(request) != {"option"}
                or type(request["option"]) is not str or len(request["option"]) != 64
                or has_native_grants(record.definition)):
            _fail()
        choices = [row for row in adoption_options(record.definition, service, pages)
                   if row["value"] == request["option"]]
        if len(choices) != 1:
            _fail()
        choice = choices[0]
        mapping = PendingSamePhysicalItemMapping.prepare(record, choice["item_id"], choice["source_key"],
            actor_id=actor_id, action_id=action_id, service=service, pages=pages)
        if type(mapping) is not PendingSamePhysicalItemMapping:
            _fail()
        mapping.validate_sources(record, service, pages)
        return cls(mapping, json.dumps(record.definition.to_dict(), sort_keys=True),
                   json.dumps(record.state_record.state, sort_keys=True), _ISSUER)

    def compose(self, record, candidate):
        if self._issuer is not _ISSUER:
            _fail()
        linked = self.mapping.candidate(record)  # Validate its item-only projection unchanged.
        if candidate.equipment_catalog != record.definition.equipment_catalog:
            _fail()
        payload = deepcopy(candidate.to_dict())
        payload["equipment_catalog"] = linked["equipment_catalog"]
        return type(candidate).from_dict(payload)

    def request(self):
        if self._issuer is not _ISSUER:
            _fail()
        ref = json.loads(self.mapping.reference_json)
        return {"option": _mapping_digest([self.mapping.target_id, ref["entry_key"]])}

    def expected_activation_items(self, record, candidate, state):
        """The complete permitted physical catalogue, never a linked prior."""
        if self._issuer is not _ISSUER or type(self.mapping) is not PendingSamePhysicalItemMapping:
            _fail()
        payload = self.mapping.candidate(record)
        self.mapping.validate_binding(record, type(record.definition).from_dict(payload), state, self.mapping.actor_id)
        validate_item_delta(record.definition, candidate, self.mapping.descriptor())
        return {row["id"]: deepcopy(row) for row in payload["equipment_catalog"]
                if not row.get("is_currency_only", False)}

    def bind_authority(self, authority, candidate, plan, checkpoint, systems_service):
        from .character_models import CharacterDefinition
        from .character_source_authority import (_ModifierHistoryRetention, _MODIFIER_RETENTION_ISSUER,
            numeric_value_digest, _canonical)
        if self._issuer is not _ISSUER or plan.get("schema_version") != 5:
            _fail()
        prior = CharacterDefinition.from_dict(json.loads(self.prior_json))
        validate_item_delta(prior, candidate, self.mapping.descriptor())
        state = json.loads(self.state_json)
        if (authority.state_revision != self.mapping.state_revision
                or authority.state_digest != numeric_value_digest(state)
                or authority.original_definition_digest != numeric_value_digest(candidate.to_dict())
                or plan.get("prior_definition_digest") != self.mapping.prior_digest
                or plan.get("prior_generation") != self.mapping.prior_revision
                or plan.get("prior_state_revision") != self.mapping.state_revision
                or plan.get("current_checkpoint") != checkpoint.checkpoint):
            _fail()
        from .character_spell_grants import inspect_native_grant_proposal
        draft = inspect_native_grant_proposal(candidate, systems_service,
            prior_definition=prior, prior_generation=self.mapping.prior_revision,
            prior_definition_digest=self.mapping.prior_digest, prior_state_revision=self.mapping.state_revision)
        if draft.source_digest != plan.get("proposal_source_digest"):
            _fail()
        history, entries, edges = _history(authority, prior, candidate, self.mapping.target_id, checkpoint, draft)
        _validate_history_wrappers(history)
        _validate_empty_history_relations(history, entries, edges)
        return replace(authority, modifier_history_retention=_ModifierHistoryRetention(
            authority.definition_digest, numeric_value_digest(candidate.to_dict()), authority.state_digest,
            authority.state_revision, authority.source_snapshot_digest,
            _canonical(entries), _canonical(edges), _canonical(history), _MODIFIER_RETENTION_ISSUER))

    def descriptor(self, candidate, authority):
        if self._issuer is not _ISSUER:
            _fail()
        retention = authority.modifier_history_retention
        history = authority.retained_spell_modifier_history(candidate)
        _validate_history_wrappers(history)
        entries, edges = json.loads(retention.entries_json), json.loads(retention.edges_json)
        _validate_empty_history_relations(history, entries, edges)
        return {"schema_version": 1, "mapping": self.mapping.descriptor(),
            "history": deepcopy(history), "entries_digest": _mapping_digest(entries),
            "edges_digest": _mapping_digest(edges)}


def validate_item_delta(prior, candidate, mapping):
    """Historical or pending comparison: the sole item delta is one added ref."""
    from .character_models import CharacterDefinition
    from .character_source_repair import _sha256_hex
    keys = {"schema_version", "actor_id", "action_id", "item_id", "prior_revision", "state_revision",
        "prior_definition_digest", "state_digest", "candidate_digest", "systems_ref", "review_source_digest"}
    if (type(mapping) is not dict or set(mapping) != keys or type(mapping["schema_version"]) is not int
            or mapping["schema_version"] != 1 or type(mapping["actor_id"]) is not int or mapping["actor_id"] < 1
            or type(mapping["action_id"]) is not str or not mapping["action_id"]
            or type(mapping["prior_revision"]) is not int or mapping["prior_revision"] < 1
            or type(mapping["state_revision"]) is not int or mapping["state_revision"] < 0
            or any(not _sha256_hex(mapping[key]) for key in (
                "prior_definition_digest", "state_digest", "candidate_digest", "review_source_digest"))
            or mapping["prior_definition_digest"] != _mapping_digest(prior.to_dict())):
        _fail()
    expected = deepcopy(prior.to_dict())
    rows = [row for row in expected["equipment_catalog"] if row.get("id") == mapping["item_id"]]
    if len(rows) != 1 or rows[0].get("systems_ref") or not rows[0].get("page_ref"):
        _fail()
    from .character_spell_grants import publication_identity
    if publication_identity(mapping["systems_ref"])["entry_type"] != "item":
        _fail()
    rows[0]["systems_ref"] = deepcopy(mapping["systems_ref"])
    if (_mapping_digest(expected) != mapping["candidate_digest"]
            or candidate.equipment_catalog != expected["equipment_catalog"]):
        _fail()
    return CharacterDefinition.from_dict(expected)


def validate_saved_adoption(prior, candidate, proof, *, actor_id, action_id):
    """Authenticate the exact allowed delta inside the enclosing audited proof."""
    from .character_source_authority import _require_modifier_retention_rows
    from .character_spell_grants import validate_native_grant_model, canonical_digest
    descriptor = proof.get("atomic_item_adoption")
    if (proof.get("schema_version") != 7 or type(descriptor) is not dict
            or set(descriptor) != {"schema_version", "mapping", "history", "entries_digest", "edges_digest"}
            or type(descriptor["schema_version"]) is not int or descriptor["schema_version"] != 1
            or type(descriptor["history"]) is not list or len(descriptor["history"]) > 16):
        _fail()
    mapping = descriptor["mapping"]
    linked = validate_item_delta(prior, candidate, mapping)
    if any(mapping.get(key) != value for key, value in (
            ("actor_id", actor_id), ("action_id", action_id),
            ("prior_revision", proof.get("prior_generation")),
            ("state_revision", proof.get("prior_state_revision")),
            ("state_digest", proof.get("prior_state_digest")))):
        _fail()
    plan = proof.get("spell_origin_plan")
    if type(plan) is not dict or plan.get("schema_version") != 5:
        _fail()
    _validate_history_wrappers(descriptor["history"])
    _require_modifier_retention_rows(prior, descriptor["history"])
    _require_modifier_retention_rows(candidate, descriptor["history"])
    model = validate_native_grant_model(candidate)
    edges = []
    for row in descriptor["history"]:
        if row["item_id"] != mapping["item_id"] or row["source_ref"] != mapping["systems_ref"]:
            _fail()
        matches = [edge for edge in model["migration_edges"] if edge["old_spell_id"] == row["observation"]["id"]]
        if (len(matches) != 1 or matches[0]["grant_ids"]
                or matches[0]["unresolved_observation_digest"] != canonical_digest(row["observation"])):
            _fail()
        edges += matches
    if _mapping_digest(edges) != descriptor["edges_digest"]:
        _fail()
    from .character_source_repair import _sha256_hex
    if not _sha256_hex(descriptor["entries_digest"]):
        _fail()
    if not descriptor["history"] and any(descriptor[key] != _mapping_digest([])
            for key in ("entries_digest", "edges_digest")):
        _fail()
    return linked
