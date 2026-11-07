"""Narrow manager maintenance of current reference prose, without derivation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_spell_grants import canonical_digest as digest
from .character_store import CharacterStateConflictError

ACTION = "reference_notes_action"
PREVIEW = "preview"
SAVE = "save"
SOURCE = "reference_notes_only"
EVENT = "character_reference_notes_updated"
FIELDS = frozenset({"additional_notes_markdown", "allies_and_organizations_markdown"})
INPUTS = frozenset({ACTION, "reference_notes", "expected_revision", "expected_generation",
                    "expected_source_digest", "expected_candidate_digest", "_csrf_token"})
AUDIT_FIELDS = frozenset({"source", "actor_id", "fields", "prior_generation", "state_revision",
    "prior_definition_digest", "definition_digest", "state_digest", "source_snapshot_digest"})


def validate_audit_metadata(metadata, actor_id):
    """The ordinary coordinator admits this one lossless notes envelope only."""
    from .character_source_repair import _sha256_hex
    if (type(metadata) is not dict or set(metadata) != AUDIT_FIELDS
            or metadata.get("source") != SOURCE or type(actor_id) is not int or actor_id < 1
            or type(metadata.get("actor_id")) is not int or metadata["actor_id"] != actor_id
            or type(metadata.get("fields")) is not list or not 1 <= len(metadata["fields"]) <= len(FIELDS)
            or any(type(field) is not str or field not in FIELDS for field in metadata["fields"])
            or metadata["fields"] != sorted(set(metadata["fields"]))
            or type(metadata.get("prior_generation")) is not int or metadata["prior_generation"] < 1
            or type(metadata.get("state_revision")) is not int or metadata["state_revision"] < 0
            or any(not _sha256_hex(metadata.get(key)) for key in (
                "prior_definition_digest", "definition_digest", "state_digest", "source_snapshot_digest"))):
        raise CharacterStateConflictError("Reference-note audit metadata is invalid.")


def _text(value):
    if (type(value) is not str or len(value) > 16384 or len(value.encode("utf-8")) > 65536
            or any(ord(char) < 32 and char not in "\r\n\t" for char in value)):
        raise ValueError("Reference notes require bounded Markdown text.")
    return value


def _manager(campaign, actor_id=None):
    from .auth import get_authenticated_user
    from .character_recorded_advancement import manager_allowed
    from .committed_publication import active
    user = get_authenticated_user()
    if (not active() or not manager_allowed(campaign) or user is None
            or actor_id is not None and (type(actor_id) is not int or user.id != actor_id)):
        raise CharacterStateConflictError("Reference-note maintenance needs current manager authority.")
    return user.id


def _metadata(record, candidate, fields, actor_id, source_digest):
    return {"source": SOURCE, "actor_id": actor_id, "fields": list(fields),
        "prior_generation": record.committed_revision, "state_revision": record.state_record.revision,
        "prior_definition_digest": digest(record.definition.to_dict()),
        "definition_digest": digest(candidate.to_dict()), "state_digest": digest(record.state_record.state),
        "source_snapshot_digest": source_digest}


@dataclass(frozen=True)
class ReferenceNotesEdit:
    definition: CharacterDefinition
    metadata: dict
    preview: dict


def prepare(record, values, *, systems_service, campaign_page_records):
    from .character_source_authority import build_reconciled_source_authority
    from .character_source_repair import load_verified_manual_actions, load_verified_numeric_actions
    if (type(values) is not dict or set(values) - INPUTS or values.get(ACTION) not in {PREVIEW, SAVE}
            or type(values.get("reference_notes")) is not dict
            or not 1 <= len(values["reference_notes"]) <= len(FIELDS)
            or set(values["reference_notes"]) - FIELDS):
        raise ValueError("Use a flat reference-notes preview/save with supported note fields only.")
    actor = _manager(record.definition.campaign_slug)
    if any(type(values.get(key)) is not int or values[key] != expected for key, expected in (
            ("expected_revision", record.state_record.revision), ("expected_generation", record.committed_revision))):
        raise CharacterStateConflictError("The Character changed since the reference-note review.")
    payload = deepcopy(record.definition.to_dict())
    notes = payload["reference_notes"]
    changes = []
    for field, raw in sorted(values["reference_notes"].items()):
        text = _text(raw)
        if field not in notes or notes[field] != text:
            changes.append({"field": field, "before_present": field in notes,
                            "before": deepcopy(notes.get(field)), "after": text})
            notes[field] = text
    candidate = CharacterDefinition.from_dict(payload)
    if candidate.to_dict() != payload:
        raise ValueError("Reference-note maintenance cannot normalize unrelated Character fields.")
    authority = build_reconciled_source_authority(definition=record.definition,
        state=record.state_record.state, state_revision=record.state_record.revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_manual_actions=load_verified_manual_actions(record.definition.campaign_slug, record.definition.character_slug),
        verified_numeric_actions=load_verified_numeric_actions(record.definition.campaign_slug, record.definition.character_slug, strict=True))
    metadata = _metadata(record, candidate, [row["field"] for row in changes], actor, authority.source_snapshot_digest)
    if values[ACTION] == SAVE and (values.get("expected_source_digest") != metadata["source_snapshot_digest"]
            or values.get("expected_candidate_digest") != metadata["definition_digest"]):
        raise CharacterStateConflictError("The reference-note review changed; preview it again.")
    preview = {"changes": changes, "no_changes": not changes,
        "generation": record.committed_revision, "state_revision": record.state_record.revision,
        "candidate_digest": metadata["definition_digest"], "source_digest": metadata["source_snapshot_digest"],
        "current_state_preserved": True, "import_preserved": True}
    return ReferenceNotesEdit(candidate, metadata, preview)


def publish(record, edit, coordinator):
    if edit.preview["no_changes"]:
        return None
    return coordinator.update(record, edit.definition, record.import_metadata,
        deepcopy(record.state_record.state), expected_revision=record.state_record.revision,
        updated_by_user_id=edit.metadata["actor_id"], operation_kind="interactive_update",
        audit_event_type=EVENT, audit_actor_user_id=edit.metadata["actor_id"], audit_metadata=edit.metadata)


def validate_transition(record, definition, state, *, actor_id, metadata=None,
                        audit_event_type=None, audit_actor_id=None, operation_kind=None,
                        prior_authority=None, import_metadata=None):
    """Repeat the closed prose-only delta at preflight and under reservation."""
    if type(metadata) is not dict or metadata.get("source") != SOURCE:
        return False
    validate_audit_metadata(metadata, actor_id)
    if type(definition) is not CharacterDefinition:
        raise CharacterStateConflictError("Reference notes require the exact Character definition.")
    _manager(definition.campaign_slug, actor_id)
    fields = metadata.get("fields")
    if (operation_kind != "interactive_update" or audit_event_type != EVENT
            or type(audit_actor_id) is not int or audit_actor_id != actor_id
            or type(fields) is not list or not 1 <= len(fields) <= len(FIELDS)
            or any(type(field) is not str or field not in FIELDS for field in fields)
            or fields != sorted(set(fields)) or type(definition) is not CharacterDefinition
            or definition.system != "DND-5E" or state != record.state_record.state
            or type(import_metadata) is not CharacterImportMetadata
            or import_metadata.to_dict() != record.import_metadata.to_dict()):
        raise CharacterStateConflictError("Reference notes lost their exact prose-only Character frame.")
    payload = deepcopy(record.definition.to_dict())
    for field in fields:
        if field not in definition.reference_notes:
            raise CharacterStateConflictError("A reference-note change is missing its reviewed text.")
        text = _text(definition.reference_notes[field])
        if field in payload["reference_notes"] and payload["reference_notes"][field] == text:
            raise CharacterStateConflictError("A reference-note audit must identify actual changes.")
        payload["reference_notes"][field] = text
    if definition.to_dict() != payload or metadata != _metadata(
            record, definition, fields, actor_id, metadata.get("source_snapshot_digest")):
        raise CharacterStateConflictError("Only the reviewed reference-note fields may change.")
    if prior_authority is None:
        raise CharacterStateConflictError("Reference notes need their current source qualification.")
    authority = prior_authority() if callable(prior_authority) else prior_authority
    if authority.source_snapshot_digest != metadata["source_snapshot_digest"]:
        raise CharacterStateConflictError("Character sources changed since the reference-note review.")
    return True
