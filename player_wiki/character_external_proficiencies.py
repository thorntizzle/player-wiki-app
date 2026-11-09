"""Manager-confirmed permanent acquisitions outside starting source choices.

An observation or copied source record is not a grant. The native editor owns
one explicit addition or confirmation of an existing observation. The durable
reader joins its actual prior/candidate generations and confirmed audit before
issuing current acquisition custody.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from .character_models import CharacterDefinition
from .character_spell_grants import canonical_digest as digest
from .character_source_repair import SourceRepairError

KEY = "external_proficiency_acquisitions"
PROVENANCE = "native_external_proficiency"
ACTION = "editor_action"
PREVIEW = "preview_external_proficiency"
RECORD = "record_external_proficiency"
OPERATION = "external_proficiency_operation"
ADD = "add"
ADOPT_EXISTING = "adopt_existing"
FIELDS = {"schema_version", "id", "category", "name", "kind", "origin", "occurred_at", "evidence"}
PROOF_FIELDS = {"schema_version", "actor_id", "prior_generation", "generation", "prior_definition_digest",
                "definition_digest", "prior_state_revision", "state_revision", "state_digest", "record_id"}
METADATA_FIELDS = {"source", "numeric_actor_id", "numeric_authorizations", "action_id", "source_basis_digests",
                   "source_snapshot_digest", "external_proficiency_confirmation"}
INPUTS = {ACTION, "expected_revision", "expected_generation", "expected_source_digest", "expected_candidate_digest",
          "external_proficiency_category", "external_proficiency_name", "external_proficiency_kind",
          "external_proficiency_origin_status", "external_proficiency_origin", "external_proficiency_occurred_at",
          "external_proficiency_evidence", "external_proficiency_confirmed", OPERATION, "_csrf_token"}


def _operation(value):
    if type(value) is not str or value not in {ADD, ADOPT_EXISTING}:
        raise SourceRepairError("Choose addition or confirmation of an existing proficiency observation.")
    return value


def _proof_operation(proof):
    return ADOPT_EXISTING if proof["schema_version"] == 2 else ADD


def text(value, label, *, limit=512, optional=False):
    if optional and value in (None, ""):
        return None
    if (type(value) is not str or value != value.strip() or not 1 <= len(value) <= limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise SourceRepairError(f"{label} needs a single bounded text value.")
    return value


def _date(value):
    raw = text(value, "Acquisition time", limit=64, optional=True)
    if raw is not None:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise SourceRepairError("Acquisition time needs a valid date with its UTC offset.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise SourceRepairError("Acquisition time needs its UTC offset, or leave unknown time empty.")
    return raw


def stored(definition):
    from .repository import normalize_lookup
    from .character_source_repair import _sha256_hex
    rows = definition.source.get(KEY, [])
    if type(rows) is not list or len(rows) > 32:
        raise SourceRepairError("External proficiency acquisition history exceeds its supported bound.")
    ids, names = set(), set()
    for row in rows:
        if (type(row) is not dict or set(row) != FIELDS or type(row["schema_version"]) is not int
                or row["schema_version"] != 1 or not _sha256_hex(row["id"])
                or type(row["category"]) is not str or row["category"] not in {"tools", "languages"}
                or type(row["kind"]) is not str or row["kind"] not in {"training", "external_grant"}):
            raise SourceRepairError("External proficiency history is malformed.")
        text(row["name"], "Proficiency name", limit=128)
        text(row["evidence"], "Acquisition evidence")
        if (text(row["origin"], "Acquisition origin", optional=True) != row["origin"]
                or _date(row["occurred_at"]) != row["occurred_at"]):
            raise SourceRepairError("Unknown acquisition origin and time must remain explicit null values.")
        if row["kind"] == "training" and row["origin"] is None:
            raise SourceRepairError("A training acquisition needs its known training origin.")
        identity = row["category"], normalize_lookup(row["name"])
        if not identity[1] or row["id"] in ids or identity in names:
            raise SourceRepairError("External proficiency history duplicates an acquisition or proficiency.")
        ids.add(row["id"]); names.add(identity)
        if list(definition.proficiencies.get(row["category"], [])).count(row["name"]) != 1:
            raise SourceRepairError("An acquired proficiency must retain its exact current label once.")
    return tuple(deepcopy(rows))


def target(row):
    return f"proficiencies.{row['category']}.{row['name'].casefold()}"


def basis(row):
    return digest({"target": target(row), "external_acquisition": row})


class ExternalProficiencyCustody(dict):
    """Request-local origin wrapper, never reconstructed from client JSON."""
    def __init__(self, payload: Mapping[str, Any], *, origin: tuple[Any, ...]):
        from .character_source_repair import _sha256_hex
        if (type(payload) is not dict or set(payload) != {"campaign_slug", "character_slug", "acquisition"}
                or type(origin) is not tuple or len(origin) != 5
                or origin[0] != "confirmed_external_proficiency"
                or any(type(value) is not int or value < 1 for value in origin[1:4])
                or not _sha256_hex(origin[4])):
            raise SourceRepairError("The acquisition custody origin is malformed.")
        super().__init__(deepcopy(dict(payload)))
        self.origin = origin


def custody(definition, row, *, origin):
    return ExternalProficiencyCustody({"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "acquisition": deepcopy(row)}, origin=origin)


_PENDING_ISSUER = object()


def _pending_scope(definition, targets):
    """Bind every proposed field except the explicitly renewed language frame."""
    payload = deepcopy(definition.to_dict())
    source = payload["source"]
    source["source_authorizations"] = [row for row in source.get("source_authorizations", [])
        if not (type(row) is dict and row.get("target_kind") == "proficiency"
                and row.get("metric") == "grant" and row.get("target_id") in targets)]
    frame = source["native_reconstruction_choices"]
    frame["unresolved_proficiencies"] = [name for name in frame.get("unresolved_proficiencies", []) if name != "languages"]
    return digest(payload)


class PendingExternalProficiency(dict):
    """Private prospective input, never a confirmed acquisition or JSON receipt."""
    def __init__(self, definition, row, *, state, actor_id, decision_id, prior_identity, _issuer=None):
        from .character_source_repair import _sha256_hex
        if (_issuer is not _PENDING_ISSUER or type(actor_id) is not int or actor_id < 1
                or not _sha256_hex(decision_id) or type(prior_identity) is not dict
                or prior_identity.get("actor_user_id") != actor_id or row["category"] != "languages"
                or type(definition) is not CharacterDefinition or type(state) is not dict
                or prior_identity.get("campaign_slug") != definition.campaign_slug
                or prior_identity.get("character_slug") != definition.character_slug
                or not _sha256_hex(prior_identity.get("prior_state_digest"))
                or digest(state) != prior_identity["prior_state_digest"]):
            raise SourceRepairError("A pending acquisition requires its genuine combined producer.")
        targets = tuple(sorted(f"proficiencies.languages.{name.casefold()}"
                               for name in definition.proficiencies.get("languages", [])))
        if not targets or len(targets) != len(set(targets)):
            raise SourceRepairError("A pending acquisition needs one complete unique language vector.")
        from .character_equipment_activation import effective_definition
        projected, warnings = effective_definition(definition, state)
        if warnings:
            raise SourceRepairError("Equipment activation needs repair before confirming an existing language.")
        super().__init__(campaign_slug=definition.campaign_slug,
                         character_slug=definition.character_slug, acquisition=deepcopy(row))
        # Raw validation and ordinary source authority read different views of
        # the same candidate. Bind both complete views to this exact prior state;
        # no equipment fields are ignored and neither view becomes saved custody.
        self.origin = ("pending_external_proficiency", actor_id, decision_id, row["id"], targets,
                       _pending_scope(definition, targets), _pending_scope(projected, targets),
                       digest(prior_identity))

    def matches(self, definition, row):
        from .character_source_repair import _sha256_hex
        targets = tuple(sorted(f"proficiencies.languages.{name.casefold()}"
                               for name in definition.proficiencies.get("languages", [])))
        return (type(self) is PendingExternalProficiency and type(self.origin) is tuple
            and len(self.origin) == 8 and self.origin[0] == "pending_external_proficiency"
            and type(self.origin[1]) is int and self.origin[1] > 0
            and all(_sha256_hex(self.origin[index]) for index in (2, 3, 5, 6, 7))
            and self.origin[3] == row["id"] and type(self.origin[4]) is tuple and self.origin[4] == targets
            and _pending_scope(definition, self.origin[4]) in (self.origin[5], self.origin[6])
            and dict(self) == {"campaign_slug": definition.campaign_slug,
                "character_slug": definition.character_slug, "acquisition": row})


def resolve(definition, witnesses):
    from .character_language_electives import PendingElectiveOutcome, FRAME_KEY
    rows = stored(definition)
    for row in rows:
        expected = {"campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
                    "acquisition": row}
        matches = [item for item in witnesses if (
            type(item) is ExternalProficiencyCustody and dict(item) == expected
            and type(item.origin) is tuple and len(item.origin) == 5
            and item.origin[0] == "confirmed_external_proficiency") or (
            type(item) is PendingExternalProficiency and item.matches(definition, row)
            and any(type(outcome) is PendingElectiveOutcome and type(outcome.origin) is tuple
                and len(outcome.origin) == 7
                and outcome.origin[:3] == ("pending_language_decision", definition.campaign_slug, definition.character_slug)
                and outcome.origin[3:5] == (item.origin[2], item.origin[1])
                and outcome.get("outcomes") == definition.source["native_reconstruction_choices"].get(FRAME_KEY, [])
                for outcome in witnesses))]
        if len(matches) != 1:
            raise SourceRepairError("An external proficiency needs its independently confirmed acquisition receipt.")
    return rows


def source_bases(definition, witnesses):
    return {target(row): basis(row) for row in resolve(definition, witnesses)}


def _identifier(prior, row, actor_id, *, state_digest=None):
    return _identifier_values(prior.definition, row, actor_id, prior.committed_revision,
        prior.state_record.revision, state_digest if state_digest is not None else digest(prior.state_record.state))


def _identifier_values(definition, row, actor_id, generation, state_revision, state_digest):
    return digest({"campaign": definition.campaign_slug, "character": definition.character_slug,
        "actor": actor_id, "generation": generation,
        "definition": digest(definition.to_dict()), "state_revision": state_revision,
        "state_digest": state_digest,
        "acquisition": {key: value for key, value in row.items() if key != "id"}})


def acquisition_row(values, *, check_future=True):
    """The ordinary editor's bounded declaration, without an issued identity."""
    category, kind = values.get("external_proficiency_category"), values.get("external_proficiency_kind")
    if (type(category) is not str or category not in {"tools", "languages"}
            or type(kind) is not str or kind not in {"training", "external_grant"}):
        raise SourceRepairError("Choose tool or language proficiency and its acquisition kind.")
    if values.get("external_proficiency_confirmed") != "yes":
        raise SourceRepairError("Confirm that this is a full current proficiency, not a rumor or temporary translation.")
    status = values.get("external_proficiency_origin_status")
    origin = text(values.get("external_proficiency_origin"), "Acquisition origin", optional=True)
    if type(status) is not str or status not in {"known", "unrecorded"} or (status == "known") != (origin is not None):
        raise SourceRepairError("Choose a known origin with its evidence, or explicitly retain an unrecorded origin.")
    row = {"schema_version": 1, "category": category,
        "name": text(values.get("external_proficiency_name"), "Proficiency name", limit=128),
        "kind": kind, "origin": origin,
        "occurred_at": _date(values.get("external_proficiency_occurred_at")),
        "evidence": text(values.get("external_proficiency_evidence"), "Acquisition evidence")}
    if kind == "training" and origin is None:
        raise SourceRepairError("A training acquisition needs its known training origin.")
    if check_future and row["occurred_at"] is not None and datetime.fromisoformat(row["occurred_at"]) > datetime.now(timezone.utc):
        raise SourceRepairError("A completed acquisition cannot have a future time.")
    return row


_LANGUAGE_ROW_KEYS = ("category", "name", "kind", "origin", "occurred_at", "evidence")
LANGUAGE_DECLARATION_FIELDS = frozenset({"operation", *_LANGUAGE_ROW_KEYS})


def language_declaration(value):
    if (type(value) is not dict or set(value) != LANGUAGE_DECLARATION_FIELDS
            or value.get("operation") != ADOPT_EXISTING or value.get("category") != "languages"):
        raise SourceRepairError("Combine only one existing language confirmation with unused optional slots.")
    fields = {"external_proficiency_" + key: value[key] or ""
              for key in _LANGUAGE_ROW_KEYS}
    fields.update(external_proficiency_origin_status="known" if value["origin"] is not None else "unrecorded",
                  external_proficiency_confirmed="yes")
    row = acquisition_row(fields, check_future=False)
    expected = {"operation": ADOPT_EXISTING, **{key: row[key] for key in _LANGUAGE_ROW_KEYS}}
    if value != expected:
        raise SourceRepairError("The existing language declaration is not canonical.")
    return deepcopy(expected)


def language_adoption_descriptor(prior, declaration, actor_id, generation, state_revision, state_digest, *, check_future=False):
    declaration = language_declaration(declaration)
    row = {"schema_version": 1, **{key: declaration[key] for key in _LANGUAGE_ROW_KEYS}}
    if check_future and row["occurred_at"] is not None and datetime.fromisoformat(row["occurred_at"]) > datetime.now(timezone.utc):
        raise SourceRepairError("A completed acquisition cannot have a future time.")
    row["id"] = _identifier_values(prior, row, actor_id, generation, state_revision, state_digest)
    return {"operation": ADOPT_EXISTING, "acquisition": row,
            "authorization": _marker(prior, row), "basis_digest": basis(row)}


def pending_language_adoption(definition, descriptor, *, state, actor_id, decision_id, prior_identity):
    return PendingExternalProficiency(definition, descriptor["acquisition"], actor_id=actor_id,
        state=state, decision_id=decision_id, prior_identity=prior_identity, _issuer=_PENDING_ISSUER)


def _candidate(prior_definition, row, marker, *, operation=ADD):
    from .repository import normalize_lookup
    from .character_source_repair import add_numeric_authorization
    old = list(stored(prior_definition))
    operation = _operation(operation)
    if len(old) >= 32:
        raise SourceRepairError("This proficiency is already recorded, or the acquisition bound is full.")
    labels = prior_definition.proficiencies.get(row["category"], [])
    if operation == ADD and normalize_lookup(row["name"]) in {normalize_lookup(name) for name in labels}:
        raise SourceRepairError("This proficiency is already recorded, or the acquisition bound is full.")
    if operation == ADOPT_EXISTING and (type(labels) is not list
            or any(type(name) is not str or not normalize_lookup(name) for name in labels)
            or len({normalize_lookup(name) for name in labels}) != len(labels)
            or labels.count(row["name"]) != 1
            or any(item["category"] == row["category"] and normalize_lookup(item["name"]) == normalize_lookup(row["name"])
                   for item in old)):
        raise SourceRepairError("Confirm one unique existing proficiency without a prior acquisition receipt.")
    payload = deepcopy(prior_definition.to_dict())
    if operation == ADD:
        payload["proficiencies"][row["category"]].append(row["name"])
    payload["source"][KEY] = [*old, deepcopy(row)]
    payload = add_numeric_authorization(payload, marker)
    candidate = CharacterDefinition.from_dict(payload)
    if operation == ADOPT_EXISTING and candidate.to_dict() != payload:
        raise SourceRepairError("Existing proficiency confirmation cannot normalize unrelated Character fields.")
    return candidate


def _require_observation_attribution(definition, row, authority, systems_service, witnesses):
    from .character_reconstruction_proficiencies import require_existing_observation_attribution
    if systems_service is None or authority is None:
        raise SourceRepairError("Existing proficiency confirmation needs fresh source attribution.")
    if authority.field_status(target(row)).is_effective:
        raise SourceRepairError("This proficiency already has an effective owner; no acquisition is needed.")
    try:
        require_existing_observation_attribution(definition, systems_service,
            category=row["category"], name=row["name"], witnesses=witnesses)
    except (KeyError, TypeError) as exc:
        raise SourceRepairError("Complete the native source choices before confirming an observation.") from exc


def _marker(definition, row):
    from .character_source_repair import numeric_authorization_record
    return numeric_authorization_record(character_slug=definition.character_slug,
        target_kind="proficiency", target_id=target(row), metric="grant", raw_value=row["name"],
        action_id=row["id"], provenance=PROVENANCE)


def _integer(value, label):
    if type(value) is bool or type(value) not in (str, int):
        raise SourceRepairError(f"{label} must be a whole revision.")
    try:
        result = int(value)
    except ValueError as exc:
        raise SourceRepairError(f"{label} must be a whole revision.") from exc
    if result < 1:
        raise SourceRepairError(f"{label} must be a positive revision.")
    return result


@dataclass(frozen=True, slots=True)
class ExternalProficiencyEdit:
    definition: CharacterDefinition
    metadata: dict[str, Any]
    preview: dict[str, Any]


def prepare(record, values, *, systems_service, item_catalog, campaign_page_records=()):
    from .auth import get_authenticated_user
    from .character_recorded_advancement import manager_allowed
    from .committed_publication import active
    from .character_source_repair import load_verified_manual_actions, load_verified_numeric_actions
    from .character_source_authority import build_reconciled_source_authority
    from .character_store import CharacterStateConflictError
    if (not active() or record.definition.system != "DND-5E"
            or record.definition.source.get("source_type") != "native_character_builder"):
        raise SourceRepairError("External proficiency recording needs the committed native Character model.")
    if not manager_allowed(record.definition.campaign_slug):
        raise PermissionError("Only a current campaign manager can confirm an acquired proficiency.")
    if set(values) - INPUTS or type(values.get(ACTION)) is not str or values.get(ACTION) not in {PREVIEW, RECORD}:
        raise SourceRepairError("Record one acquired proficiency separately from other editor changes.")
    if hasattr(values, "getlist") and any(len(values.getlist(key)) != 1 for key in values):
        raise SourceRepairError("Acquisition fields must occur only once.")
    operation = _operation(values.get(OPERATION, ADD))
    if (_integer(values.get("expected_revision"), "State revision") != record.state_record.revision
            or _integer(values.get("expected_generation"), "Definition generation") != record.committed_revision):
        raise CharacterStateConflictError("The Character changed since the acquisition review.")
    actor = get_authenticated_user().id
    old_witnesses = load_verified_numeric_actions(record.definition.campaign_slug, record.definition.character_slug, strict=True)
    resolve(record.definition, old_witnesses)
    authority = build_reconciled_source_authority(definition=record.definition,
        state=record.state_record.state, state_revision=record.state_record.revision,
        systems_service=systems_service, campaign_page_records=list(campaign_page_records),
        verified_manual_actions=load_verified_manual_actions(record.definition.campaign_slug, record.definition.character_slug),
        verified_numeric_actions=old_witnesses).bind_current_numbers(
            record.definition, record.state_record.state, systems_service=systems_service,
            campaign_page_records=list(campaign_page_records), item_catalog=item_catalog)
    authority.require_authoring_inputs()
    row = acquisition_row(values)
    if operation == ADD:
        category = row["category"]
        for name in record.definition.proficiencies.get(category, []):
            if not authority.field_status(f"proficiencies.{category}.{name.casefold()}").is_effective:
                raise SourceRepairError("Resolve existing proficiency ownership before adding another acquisition.")
    if operation == ADOPT_EXISTING:
        _require_observation_attribution(record.definition, row, authority, systems_service, old_witnesses)
    row["id"] = _identifier(record, row, actor)
    marker = _marker(record.definition, row)
    candidate = _candidate(record.definition, row, marker, operation=operation)
    stored(candidate)
    proof = {"schema_version": 1 if operation == ADD else 2, "actor_id": actor,
        "prior_generation": record.committed_revision, "generation": record.committed_revision + 1,
        "prior_definition_digest": digest(record.definition.to_dict()), "definition_digest": digest(candidate.to_dict()),
        "prior_state_revision": record.state_record.revision, "state_revision": record.state_record.revision,
        "state_digest": digest(record.state_record.state), "record_id": row["id"]}
    if operation == ADOPT_EXISTING:
        proof["operation"] = ADOPT_EXISTING
    metadata = {"source": "native_edit_confirmed", "numeric_actor_id": actor,
        "numeric_authorizations": [marker], "action_id": row["id"],
        "source_basis_digests": {target(row): basis(row)}, "source_snapshot_digest": authority.source_snapshot_digest,
        "external_proficiency_confirmation": proof}
    if values[ACTION] == RECORD and (values.get("expected_source_digest") != authority.source_snapshot_digest
            or values.get("expected_candidate_digest") != proof["definition_digest"]):
        raise CharacterStateConflictError("The acquisition review changed; preview it again before saving.")
    preview = {"category": category, "name": row["name"], "kind": kind, "origin": origin,
        "occurred_at": row["occurred_at"], "evidence": row["evidence"], "current_state_preserved": True,
        "import_preserved": True, "candidate_digest": proof["definition_digest"],
        "source_digest": authority.source_snapshot_digest, "generation": record.committed_revision,
        "state_revision": record.state_record.revision}
    if operation == ADOPT_EXISTING:
        preview["operation"] = ADOPT_EXISTING
    return ExternalProficiencyEdit(candidate, metadata, preview)


def publish(record, edit, coordinator):
    """Use ordinary native publication; reserved validation repeats the proof."""
    return coordinator.update(record, edit.definition, record.import_metadata,
        deepcopy(record.state_record.state), expected_revision=record.state_record.revision,
        updated_by_user_id=edit.metadata["numeric_actor_id"], operation_kind="interactive_update",
        audit_event_type="character_native_edited", audit_actor_user_id=edit.metadata["numeric_actor_id"],
        audit_metadata=edit.metadata)


def validate_metadata(metadata, actor_id):
    from .character_source_repair import _sha256_hex
    if (type(metadata) is not dict or set(metadata) != METADATA_FIELDS
            or metadata["source"] != "native_edit_confirmed" or type(actor_id) is not int or actor_id < 1
            or type(metadata["numeric_actor_id"]) is not int or metadata["numeric_actor_id"] != actor_id
            or not _sha256_hex(metadata["action_id"])
            or not _sha256_hex(metadata["source_snapshot_digest"])):
        raise SourceRepairError("The external proficiency audit envelope is malformed.")
    proof = metadata["external_proficiency_confirmation"]
    if (type(proof) is not dict or type(proof.get("schema_version")) is not int
            or not (proof["schema_version"] == 1 and set(proof) == PROOF_FIELDS
                    or proof["schema_version"] == 2 and set(proof) == PROOF_FIELDS | {"operation"}
                    and type(proof["operation"]) is str and proof["operation"] == ADOPT_EXISTING)
            or proof["actor_id"] != actor_id or type(proof["actor_id"]) is not int
            or any(type(proof[key]) is not int or proof[key] < 1 for key in
                   ("prior_generation", "generation", "prior_state_revision", "state_revision"))
            or proof["generation"] != proof["prior_generation"] + 1
            or proof["state_revision"] != proof["prior_state_revision"]
            or any(not _sha256_hex(proof[key]) for key in
                   ("prior_definition_digest", "definition_digest", "state_digest", "record_id"))
            or proof["record_id"] != metadata["action_id"]
            or type(metadata["numeric_authorizations"]) is not list or len(metadata["numeric_authorizations"]) != 1
            or type(metadata["source_basis_digests"]) is not dict or len(metadata["source_basis_digests"]) != 1):
        raise SourceRepairError("The external proficiency confirmation is malformed.")
    return proof


def validate_transition(prior_record, definition, state, *, actor_id, metadata=None,
                        audit_event_type=None, operation_kind=None, prior_authority=None, witnesses=None,
                        import_metadata=None, systems_service_provider=None, language_proof=None):
    from .character_recorded_advancement import manager_allowed
    from .character_source_repair import load_verified_numeric_actions
    from .character_store import CharacterStateConflictError
    old, rows = stored(prior_record.definition), stored(definition)
    old_markers = prior_record.definition.source.get("source_authorizations") or []
    new_markers = [item for item in definition.source.get("source_authorizations") or []
                   if type(item) is dict and item.get("provenance") == PROVENANCE and item not in old_markers]
    if rows == old and not new_markers:
        if isinstance(metadata, dict) and "external_proficiency_confirmation" in metadata:
            raise CharacterStateConflictError("An acquisition confirmation must publish its one new acquisition receipt.")
        return False
    from .committed_publication import active
    if language_proof is not None and getattr(language_proof, "external_adoption", None) is not None:
        from .character_language_electives import PendingElectiveDecision
        if (type(language_proof) is not PendingElectiveDecision or not active()
                or operation_kind != "character_update_apply" or audit_event_type != "character_update_applied"
                or not manager_allowed(definition.campaign_slug)
                or import_metadata is not None and import_metadata.to_dict() != prior_record.import_metadata.to_dict()):
            raise CharacterStateConflictError("A combined acquisition needs its manager-owned language Review.")
        language_proof.recheck(prior_record, definition, state, actor_id)
        language_proof.validate_external_delta(prior_record, definition)
        return True
    if (not active() or operation_kind != "interactive_update" or audit_event_type != "character_native_edited"
            or not manager_allowed(definition.campaign_slug)):
        raise CharacterStateConflictError("An acquired proficiency needs its manager-owned native editor confirmation.")
    proof = validate_metadata(metadata, actor_id)
    operation = _proof_operation(proof)
    if (definition.system != "DND-5E" or definition.source.get("source_type") != "native_character_builder"
            or prior_record.definition.source.get("source_type") != "native_character_builder"
            or len(rows) != len(old) + 1 or rows[:-1] != old
            or proof["prior_generation"] != prior_record.committed_revision
            or proof["prior_state_revision"] != prior_record.state_record.revision
            or proof["prior_definition_digest"] != digest(prior_record.definition.to_dict())
            or proof["definition_digest"] != digest(definition.to_dict())
            or proof["state_digest"] != digest(state) or state != prior_record.state_record.state
            or import_metadata is not None and import_metadata.to_dict() != prior_record.import_metadata.to_dict()):
        raise CharacterStateConflictError("The acquisition no longer matches its exact prior Character and play state.")
    row = rows[-1]; marker = _marker(definition, row)
    if (row["id"] != _identifier(prior_record, row, actor_id) or row["id"] != proof["record_id"]
            or new_markers != [marker] or metadata["numeric_authorizations"] != [marker]
            or metadata["source_basis_digests"] != {target(row): basis(row)}
            or _candidate(prior_record.definition, row, marker, operation=operation).to_dict() != definition.to_dict()):
        raise CharacterStateConflictError("Only the single confirmed proficiency may change in this editor action.")
    prior_witnesses = (witnesses if witnesses is not None else load_verified_numeric_actions(
        definition.campaign_slug, definition.character_slug, strict=True))
    resolve(prior_record.definition, prior_witnesses)
    authority = None
    if prior_authority is not None:
        authority = prior_authority() if callable(prior_authority) else prior_authority
        if authority.source_snapshot_digest != metadata["source_snapshot_digest"]:
            raise CharacterStateConflictError("Character source policy changed since the acquisition review.")
    if operation == ADOPT_EXISTING:
        if authority is None:
            raise CharacterStateConflictError("Existing proficiency confirmation needs its current numeric authority.")
        authority.require_authoring_inputs()
        if not callable(systems_service_provider):
            raise CharacterStateConflictError("Existing proficiency confirmation needs its current source provider.")
        systems_service = systems_service_provider()
        _require_observation_attribution(prior_record.definition, row, authority, systems_service, prior_witnesses)
    return True


def verified_batch(connection, campaign, character, audit, metadata, prior_witnesses):
    from types import SimpleNamespace
    from .character_source_repair import _decision_generation
    if audit["event_type"] != "character_native_edited":
        raise SourceRepairError("External proficiency custody needs a native editor audit.")
    metadata = deepcopy(metadata)
    published = {key: metadata.pop(key) for key in
                 ("published_revision", "published_state_revision", "published_definition_digest") if key in metadata}
    proof = validate_metadata(metadata, audit["actor_user_id"])
    if published != {"published_revision": proof["generation"], "published_state_revision": proof["state_revision"],
                     "published_definition_digest": proof["definition_digest"]}:
        raise SourceRepairError("The acquisition audit is not the actual published generation.")
    before, _ = _decision_generation(connection, campaign, character,
        proof["prior_generation"], proof["prior_definition_digest"])
    after, _ = _decision_generation(connection, campaign, character,
        proof["generation"], proof["definition_digest"], audit["actor_user_id"])
    prior, candidate = CharacterDefinition.from_dict(before), CharacterDefinition.from_dict(after)
    old, rows = resolve(prior, prior_witnesses), stored(candidate)
    if len(rows) != len(old) + 1 or rows[:-1] != old:
        raise SourceRepairError("The acquisition audit changed earlier acquisition history.")
    row = rows[-1]; marker = _marker(candidate, row)
    proxy = SimpleNamespace(definition=prior, committed_revision=proof["prior_generation"],
                            state_record=SimpleNamespace(revision=proof["prior_state_revision"]))
    if (row["id"] != _identifier(proxy, row, audit["actor_user_id"], state_digest=proof["state_digest"]) or row["id"] != proof["record_id"]
            or metadata["numeric_authorizations"] != [marker]
            or metadata["source_basis_digests"] != {target(row): basis(row)}
            or _candidate(prior, row, marker, operation=_proof_operation(proof)).to_dict() != candidate.to_dict()):
        raise SourceRepairError("The acquisition receipt differs from its exact historical Character pair.")
    origin = ("confirmed_external_proficiency", audit["id"], audit["actor_user_id"],
              proof["generation"], proof["definition_digest"])
    return (custody(candidate, row, origin=origin), {"authorization": marker, "source_basis_digest": basis(row)})


def historical_marker(entry, accepted):
    metadata = deepcopy(entry["metadata"])
    for key in ("published_revision", "published_state_revision", "published_definition_digest"):
        metadata.pop(key, None)
    proof = validate_metadata(metadata, entry["actor_user_id"])
    definition = CharacterDefinition.from_dict(entry["definition"])
    if digest(definition.to_dict()) != proof["definition_digest"]:
        raise SourceRepairError("The historical acquisition definition changed.")
    rows = stored(definition)
    matching = [item for item in accepted if type(item) is ExternalProficiencyCustody
        and item.origin == ("confirmed_external_proficiency", entry["audit_id"], entry["actor_user_id"],
                            proof["generation"], proof["definition_digest"])
        and item.get("acquisition") in rows and item["acquisition"]["id"] == proof["record_id"]]
    if len(matching) != 1:
        raise SourceRepairError("The historical proficiency grant has no independently recovered receipt.")
    return metadata["numeric_authorizations"]
