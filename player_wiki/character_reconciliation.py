from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import stat
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable

from flask import has_app_context
import yaml

from .auth_store import AuthStore, isoformat, utcnow
from .character_importer import render_character_yaml
from .character_assets import (
    CHARACTER_PORTRAIT_ASSET_EXTENSIONS,
    CHARACTER_PORTRAIT_MAX_BYTES,
    resolve_character_portrait_asset_path,
)
from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord, CharacterStateRecord
from .character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_path,
    validate_character_slug,
)
from .character_repository import CharacterRepository, load_campaign_character_config
from .character_store import (
    CharacterStateConflictError,
    CharacterStateUnavailableError,
    CharacterStateStore,
    PreparedCharacterState,
)
from .db import get_db, SourceReadConnectionFatal
from .file_publication import (
    atomic_move_file,
    atomic_write_bytes,
    durable_sync_directory,
    durable_unlink_file,
)
from .runtime_lease import (
    RuntimeStateLeaseError, acquire_runtime_state_lease,
    recovery_runtime_state_lease_context,
)


MAX_RECOVERY_PAYLOAD = 100663296
CREATE_OPERATION_KINDS = frozenset(
    {
        "native_create",
        "manual_import",
        "markdown_import",
        "pdf_import",
        "content_api_create",
    }
)
UPDATE_OPERATION_KINDS = frozenset(
    {
        "interactive_update",
        "markdown_import",
        "pdf_import",
        "content_api_update",
        "portrait_upsert",
        "portrait_remove",
        "character_update_apply",
        "activation_repair",
    }
)
OPTIONAL_STATE_UPDATE_OPERATION_KINDS = frozenset(
    {"markdown_import", "pdf_import", "content_api_update", "character_update_apply"}
)
PORTRAIT_OPERATION_KINDS = frozenset({"portrait_upsert", "portrait_remove"})
OPERATION_KINDS = CREATE_OPERATION_KINDS | UPDATE_OPERATION_KINDS
ACTIVE_STATES = frozenset({"prepared", "repository_pending", "conflict"})
DELETE_OPERATION_KINDS = frozenset(
    {"character_controls", "character_controls_api", "content_api"}
)
_CHARACTER_LOCKS_GUARD = Lock()
_CHARACTER_LOCKS: dict[tuple[str, str], RLock] = {}


class CharacterPublicationError(RuntimeError):
    pass


class CharacterPublicationPreflightError(CharacterPublicationError):
    """An anticipated domain refusal before any publication attempt."""


class CharacterPublicationConflict(FileExistsError, CharacterPublicationError):
    pass


class CharacterPublicationExistsError(FileExistsError, CharacterPublicationError):
    pass


class CharacterDeletionError(RuntimeError):
    pass


class CharacterDeletionConflict(CharacterDeletionError):
    pass


class _AuthorityConflict(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


_NATIVE_REVIEW_ADMISSION = object()
_NATIVE_REVIEW_RECORD_KEYS = frozenset({
    "issuer", "owner", "request", "token_digest", "actor", "campaign", "character",
    "prior", "phase", "lock",
})
_NATIVE_REVIEW_PHASES = ("REQUEST", "BINDING", "BOUND", "CAPTURING", "COMPLETE", "CLOSED")
_NATIVE_REVIEW_LOCK_TYPE = type(_CHARACTER_LOCKS_GUARD)


@dataclass(frozen=True, slots=True)
class PendingReviewedSourceProof:
    """The source basis observed during an activated prospective review."""

    prior_revision: int
    prior_definition_digest: str
    prior_state_digest: str
    candidate_definition_digest: str
    desired_state_digest: str
    source_snapshot_digest: str
    authority_identity: str
    config_revision: int
    page_feature_markers: tuple[dict[str, Any], ...] = ()
    reviewed_source_digest: str = ""
    reviewed_policy_digest: str = ""
    replacement_relink_target: str = ""
    same_physical_mapping: Any | None = field(default=None, repr=False, compare=False)
    feature_class_association: Any | None = field(default=None, repr=False, compare=False)
    managed_resource_restoration: Any | None = field(default=None, repr=False, compare=False)
    refresh_review_basis: Callable[[], tuple[Any, ...]] | None = field(
        default=None, repr=False, compare=False,
    )
    refresh_numeric_authority: Callable[[], Any] | None = field(
        default=None, repr=False, compare=False,
    )
    native_reconstruction: Any | None = field(default=None, repr=False, compare=False)
    native_elective_decision: Any | None = field(default=None, repr=False, compare=False)
    elective_review_token: str = field(default="", repr=False, compare=False)
    native_requalification_markers: tuple[dict[str, Any], ...] = ()
    native_spell_origin_plan: dict[str, Any] | None = field(default=None, repr=False, compare=False)
    native_actor_id: int | None = None
    native_result: Any | None = field(default=None, repr=False, compare=False)
    native_action_id: str = ""
    native_proof_digest: str = ""
    native_review_token: str = field(default="", repr=False, compare=False)
    _native_admission: dict[str, Any] | None = field(default=None, init=False, repr=False, compare=False)
    _complete: bool = field(default=True, init=False, repr=False, compare=False)

    def require_complete(self):
        try:
            if self._requires_native_custody():
                # Refuse another object's copied slots before even preparing
                # token facts, and recheck after that fallible preparation.
                self._native_phase("COMPLETE")
                record = self._native_record()
                token, actor = self._custody_credentials()
                facts = self._request_admission_facts(
                    token, actor,
                    record["campaign"], record["character"])
                self._native_phase("COMPLETE", request_facts=facts)
            elif self._complete is not True:
                raise CharacterStateConflictError("Reviewed source proof is not complete.")
        except BaseException:
            self.discard_native_admission()
            raise

    def _requires_native_custody(self):
        # Reconstruction has its own proof contract and leaves these native
        # requalification fields at their defaults. Raw Character flags never
        # decide this family. A CLOSED or malformed record cannot fall through.
        return (getattr(self, "_native_admission", None) is not None
                or getattr(self, "native_elective_decision", None) is not None
                or type(getattr(self, "elective_review_token", "")) is not str
                or len(getattr(self, "elective_review_token", "")) != 0
                or self._has_native_payload(
            getattr(self, "native_result", None), getattr(self, "native_spell_origin_plan", None),
            getattr(self, "native_requalification_markers", ()), getattr(self, "native_actor_id", None),
            getattr(self, "native_action_id", ""), getattr(self, "native_proof_digest", ""),
            getattr(self, "native_review_token", "")))

    def _custody_credentials(self):
        elective = getattr(self, "native_elective_decision", None)
        if elective is not None:
            from .character_language_electives import PendingElectiveDecision
            if type(elective) is not PendingElectiveDecision:
                raise CharacterStateConflictError("Language Review custody has an unsupported proof type.")
            return self.elective_review_token, elective.prior_identity["actor_user_id"]
        return self.native_review_token, self.native_actor_id

    @staticmethod
    def _has_native_payload(result, plan, markers, actor, action, digest, token):
        # Exact default types avoid invoking a malformed stand-in's equality.
        return (result is not None or plan is not None or actor is not None
                or type(markers) is not tuple or len(markers) != 0
                or any(type(value) is not str or len(value) != 0 for value in (action, digest, token)))

    def _native_record_structure(self):
        # Revocation must remain possible after a partially advanced phase.
        # This admits no authority: callers still check owner/request identity,
        # and every live consumer additionally uses the strict reader below.
        record = getattr(self, "_native_admission", None)
        if (type(self) is not PendingReviewedSourceProof or type(record) is not dict
                or len(record) != len(_NATIVE_REVIEW_RECORD_KEYS)
                or any(type(key) is not str for key in record)
                or record.keys() != _NATIVE_REVIEW_RECORD_KEYS
                or record["issuer"] is not _NATIVE_REVIEW_ADMISSION
                or type(record["lock"]) is not _NATIVE_REVIEW_LOCK_TYPE
                or (record["owner"] is not None and type(record["owner"]) is not PendingReviewedSourceProof)):
            raise CharacterStateConflictError("Native Review custody is unavailable.")
        return record

    def _native_record(self):
        record = self._native_record_structure()
        if (type(record["phase"]) is not str or record["phase"] not in _NATIVE_REVIEW_PHASES
                or type(record["actor"]) is not int or record["actor"] < 1
                or any(type(record[key]) is not str or not record[key]
                       for key in ("token_digest", "campaign", "character"))
                or len(record["token_digest"]) != 64
                or (record["prior"] is not None and not self._valid_prior_facts(record["prior"]))
                or (record["phase"] in ("REQUEST", "BINDING") and record["prior"] is not None)
                or (record["phase"] in ("BOUND", "CAPTURING", "COMPLETE") and record["prior"] is None)):
            raise CharacterStateConflictError("Native Review custody is unavailable.")
        return record

    @staticmethod
    def _valid_prior_facts(facts):
        return (type(facts) is tuple and len(facts) == 5
                and type(facts[0]) is int and facts[0] > 0
                and type(facts[1]) is int and facts[1] > 0
                and all(type(value) is str and len(value) == 64 for value in facts[2:]))

    def _native_phase(self, expected, *, request_facts=None, prior_facts=None, next_phase=None):
        """Check/claim only fixed facts under the non-reentrant record lock."""
        from flask import request
        record = self._native_record()
        actual_request = request._get_current_object()
        if (request_facts is not None and (
                type(request_facts) is not tuple or len(request_facts) != 4
                or type(request_facts[0]) is not str or len(request_facts[0]) != 64
                or type(request_facts[1]) is not int or request_facts[1] < 1
                or any(type(value) is not str or not value for value in request_facts[2:]))):
            raise CharacterStateConflictError("Native Review request facts are unavailable.")
        if prior_facts is not None and not self._valid_prior_facts(prior_facts):
            raise CharacterStateConflictError("Native Review actual Character facts are unavailable.")
        with record["lock"]:
            if (record["owner"] is not self or record["request"] is not actual_request
                    or record["phase"] != expected
                    or self._complete is not (expected == "COMPLETE")
                    or (request_facts is not None and (
                        record["token_digest"] != request_facts[0]
                        or record["actor"] != request_facts[1]
                        or record["campaign"] != request_facts[2]
                        or record["character"] != request_facts[3]))):
                raise CharacterStateConflictError("Native Review owner, request or phase changed.")
            if expected == "BINDING" and next_phase == "BOUND":
                if record["prior"] is not None or prior_facts is None:
                    raise CharacterStateConflictError("Native Review actual Character binding is unavailable.")
            elif prior_facts is not None and record["prior"] != prior_facts:
                raise CharacterStateConflictError("Native Review actual Character binding changed.")
            if next_phase is not None:
                if (expected, next_phase) not in (
                        ("REQUEST", "BINDING"), ("BINDING", "BOUND"),
                        ("BOUND", "CAPTURING"), ("CAPTURING", "COMPLETE")):
                    raise CharacterStateConflictError("Native Review phase cannot be reopened.")
                if next_phase == "BOUND":
                    record["prior"] = prior_facts
                if next_phase == "COMPLETE":
                    object.__setattr__(self, "_complete", True)
                record["phase"] = next_phase

    def _native_validation_phase(self):
        # Shared field validators accept only the actual owner's private
        # staging phase or its completed phase. Public consumers separately
        # require COMPLETE; this helper never returns a proof or authority.
        from flask import request
        record = self._native_record()
        actual_request = request._get_current_object()
        with record["lock"]:
            phase = record["phase"]
            if (record["owner"] is not self or record["request"] is not actual_request
                    or phase not in ("CAPTURING", "COMPLETE")
                    or self._complete is not (phase == "COMPLETE")):
                raise CharacterStateConflictError("Native Review validation phase is unavailable.")
            return phase

    @staticmethod
    def _new_native_record(owner, facts, prior, phase):
        from flask import request
        return {"issuer": _NATIVE_REVIEW_ADMISSION, "owner": owner,
                "request": request._get_current_object(), "token_digest": facts[0],
                "actor": facts[1], "campaign": facts[2], "character": facts[3],
                "prior": prior, "phase": phase, "lock": Lock()}

    @classmethod
    def admit_native_request(cls, token, actor_id, campaign_slug, character_slug):
        """Admit normal age before unrelated work, without any prior facts."""
        from .character_source_repair_routes import _token_serializer, _TTL
        claims = _token_serializer().loads(token, max_age=_TTL)
        if not isinstance(claims, dict) or claims.get("action") != "native_requalify":
            return claims, None
        cls._require_native_claims(claims, actor_id, campaign_slug, character_slug)
        from flask import request
        from werkzeug.exceptions import BadRequest
        # Only authenticated native classification adds this ambiguity check;
        # ordinary non-native forms retain their existing validation behavior.
        if any(len(request.form.getlist(key)) != 1 for key in request.form):
            raise BadRequest()
        result = object.__new__(cls)
        object.__setattr__(result, "_complete", False)
        object.__setattr__(result, "_native_admission", None)
        try:
            object.__setattr__(result, "_native_admission", cls._new_native_record(
                result, cls._request_admission_facts(token, actor_id, campaign_slug, character_slug),
                None, "REQUEST"))
            return claims, result
        except BaseException:
            result.discard_native_admission()
            raise

    def discard_native_admission(self):
        # A copied slot is not the owner and cannot revoke its genuine issuer.
        # Keep CLOSED attached so old aliases and slot restoration stay closed.
        # Cleanup must never replace an original exception/result, even when
        # invoked without an active Flask request during aborted work. A leaked
        # owner used from another request cannot revoke the original request.
        try:
            from flask import has_request_context, request
            if not has_request_context():
                return
            actual_request = request._get_current_object()
            record = self._native_record_structure()
            with record["lock"]:
                if record["owner"] is self and record["request"] is actual_request:
                    record["phase"] = "CLOSED"
                    object.__setattr__(self, "_complete", False)
                    record["owner"] = None
                    record["request"] = None
        except BaseException:
            pass

    def _require_native_complete_binding(self, prior_record, actor_id):
        self.require_complete()
        if self._requires_native_custody():
            try:
                token, _actor = self._custody_credentials()
                facts = self._request_admission_facts(token, actor_id,
                    prior_record.definition.campaign_slug, prior_record.definition.character_slug)
                prior = self._prior_admission_facts(prior_record)
                self._native_phase("COMPLETE", request_facts=facts, prior_facts=prior)
            except BaseException:
                self.discard_native_admission()
                raise

    @staticmethod
    def _require_native_claims(claims, actor_id, campaign_slug, character_slug):
        if (type(claims) is not dict or claims.get("v") != 1
                or claims.get("action") != "native_requalify"
                or type(actor_id) is not int or actor_id < 1
                or type(claims.get("actor")) is not int or claims["actor"] != actor_id
                or (claims.get("campaign"), claims.get("character")) != (campaign_slug, character_slug)):
            raise CharacterStateConflictError("Native Review belongs to a different manager or Character.")

    @classmethod
    def admit_manager_review(cls, prior_record, token, actor_id, *, native_review_admission=None):
        """Seal normal-age route admission on this existing pending proof.

        The incomplete phase contains no invented authority, revision or
        candidate. Only capture can fill it after genuine native preparation.
        An early native seal is consumed once to bind independently loaded prior
        facts. Default and non-native callers retain normal-expiry verification.
        """
        from .character_source_repair_routes import _token_serializer, _TTL
        if native_review_admission is not None:
            if type(native_review_admission) is not cls:
                raise CharacterStateConflictError("Native Review was not admitted within normal expiry.")
            try:
                native_review_admission._native_phase("REQUEST")
                facts = cls._request_admission_facts(token, actor_id,
                    prior_record.definition.campaign_slug, prior_record.definition.character_slug)
                native_review_admission._native_phase("REQUEST", request_facts=facts, next_phase="BINDING")
                prior = cls._prior_admission_facts(prior_record)
                claims = _token_serializer().loads(token)
                cls._require_native_claims(claims, actor_id, prior_record.definition.campaign_slug,
                                           prior_record.definition.character_slug)
                cls._require_native_prior_claims(claims, prior)
                native_review_admission._native_phase("BINDING", request_facts=facts,
                    prior_facts=prior, next_phase="BOUND")
            except BaseException:
                native_review_admission.discard_native_admission()
                raise
            return claims, native_review_admission
        claims = _token_serializer().loads(token, max_age=_TTL)
        if not isinstance(claims, dict) or claims.get("action") != "native_requalify":
            return claims, None
        cls._require_native_claims(claims, actor_id, prior_record.definition.campaign_slug,
                                   prior_record.definition.character_slug)
        facts = cls._request_admission_facts(token, actor_id,
            prior_record.definition.campaign_slug, prior_record.definition.character_slug)
        prior = cls._prior_admission_facts(prior_record)
        cls._require_native_prior_claims(claims, prior)
        result = object.__new__(cls)
        object.__setattr__(result, "_complete", False)
        object.__setattr__(result, "_native_admission", None)
        try:
            object.__setattr__(result, "_native_admission", cls._new_native_record(result, facts, prior, "BOUND"))
            return claims, result
        except BaseException:
            result.discard_native_admission()
            raise

    @staticmethod
    def _request_admission_facts(token, actor_id, campaign_slug, character_slug):
        if (type(token) is not str or not token or type(actor_id) is not int or actor_id < 1
                or type(campaign_slug) is not str or not campaign_slug
                or type(character_slug) is not str or not character_slug):
            raise CharacterStateConflictError("Native Review request facts are unavailable.")
        return (hashlib.sha256(token.encode("utf-8")).hexdigest(), actor_id, campaign_slug, character_slug)

    @classmethod
    def _prior_admission_facts(cls, prior_record):
        facts = (prior_record.committed_revision, prior_record.state_record.revision,
                cls._digest(prior_record.definition.to_dict()), cls._digest(prior_record.state_record.state),
                cls._digest(prior_record.import_metadata.to_dict()))
        if not cls._valid_prior_facts(facts):
            raise CharacterStateConflictError("Native Review actual Character facts are unavailable.")
        return facts

    @staticmethod
    def _require_native_prior_claims(claims, prior):
        if (claims.get("definition_digest") != prior[2] or claims.get("import_digest") != prior[4]
                or type(claims.get("state_revision")) is not int
                or claims["state_revision"] != prior[1] or claims.get("state_digest") != prior[3]):
            raise CharacterStateConflictError("Character or source changed. Refresh and review again.")

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()

    @classmethod
    def capture(cls, prior_record: CharacterRecord, definition: CharacterDefinition,
                desired_state: dict[str, Any], authority: Any, *,
                config_revision: int | None = None,
                page_feature_markers: tuple[dict[str, Any], ...] = (),
                source_digest: str = "", policy_digest: str = "",
                replacement_relink_target: str = "",
                same_physical_mapping: Any | None = None,
                feature_class_association: Any | None = None,
                managed_resource_restoration: Any | None = None,
                refresh_review_basis: Callable[[], tuple[Any, ...]] | None = None,
                refresh_numeric_authority: Callable[[], Any] | None = None,
                native_reconstruction: Any | None = None,
                native_elective_decision: Any | None = None,
                elective_review_token: str = "",
                elective_review_validator: Callable[[], bool] | None = None,
                native_requalification_markers: tuple[dict[str, Any], ...] = (),
                native_spell_origin_plan: dict[str, Any] | None = None,
                native_actor_id: int | None = None,
                native_result: Any | None = None,
                native_action_id: str = "", native_proof_digest: str = "",
                native_review_token: str = "",
                native_review_admission: PendingReviewedSourceProof | None = None,
                source_read_owner=None,
                ) -> PendingReviewedSourceProof:
        native = (native_review_admission is not None or cls._has_native_payload(
            native_result, native_spell_origin_plan, native_requalification_markers,
            native_actor_id, native_action_id, native_proof_digest, native_review_token))
        if managed_resource_restoration is not None:
            from .character_managed_resource_restoration import PendingManagedResourceRestoration
            if (type(managed_resource_restoration) is not PendingManagedResourceRestoration
                    or native or feature_class_association is not None or same_physical_mapping is not None
                    or native_reconstruction is not None or native_elective_decision is not None
                    or page_feature_markers or replacement_relink_target
                    or not callable(refresh_review_basis) or not callable(refresh_numeric_authority)
                    or not source_digest or not policy_digest):
                raise CharacterStateConflictError("Tracker restoration needs its separate complete source Review.")
            managed_resource_restoration.validate_binding(prior_record, definition, desired_state,
                                                         managed_resource_restoration.actor_id)
        if feature_class_association is not None and (native or native_elective_decision is not None
                or native_reconstruction is not None or same_physical_mapping is not None
                or not callable(refresh_review_basis) or not source_digest or not policy_digest):
            raise CharacterStateConflictError("Class association needs its separate complete source Review.")
        try:
            if native:
                if type(native_review_admission) is not cls:
                    raise CharacterStateConflictError("Native Review was not admitted within normal expiry.")
                native_review_admission._native_phase("BOUND")
                facts = cls._request_admission_facts(native_review_token, native_actor_id,
                    prior_record.definition.campaign_slug, prior_record.definition.character_slug)
                prior = cls._prior_admission_facts(prior_record)
                # Claim before configuration, authority or field construction.
                # Nothing can restore BOUND when any later work fails.
                native_review_admission._native_phase("BOUND", request_facts=facts,
                    prior_facts=prior, next_phase="CAPTURING")
                if native_result is None:
                    raise CharacterStateConflictError("Native Review requires its genuine prepared result.")
            if same_physical_mapping is not None:
                from .character_reconstruction_items import PendingSamePhysicalItemMapping
                if (type(same_physical_mapping) is not PendingSamePhysicalItemMapping or native
                        or native_reconstruction is not None or native_elective_decision is not None
                        or not callable(refresh_review_basis) or not source_digest or not policy_digest):
                    raise CharacterStateConflictError("Same-physical mapping needs its separate complete source Review.")
                same_physical_mapping.validate_binding(prior_record, definition, desired_state, same_physical_mapping.actor_id)
            from .committed_character_publication import config
            revision = (config(definition.campaign_slug)[0]["revision"]
                        if config_revision is None else config_revision)
            if (authority is None or not authority.identity
                    or not authority.source_snapshot_digest or type(revision) is not int):
                raise CharacterStateConflictError("Character source proof is unavailable.")
            values = {
                "prior_revision": prior_record.committed_revision,
                "prior_definition_digest": cls._digest(prior_record.definition.to_dict()),
                "prior_state_digest": cls._digest(prior_record.state_record.state),
                "candidate_definition_digest": cls._digest(definition.to_dict()),
                "desired_state_digest": cls._digest(desired_state),
                "source_snapshot_digest": authority.source_snapshot_digest,
                "authority_identity": authority.identity, "config_revision": revision,
                "page_feature_markers": tuple(json.loads(json.dumps(marker)) for marker in page_feature_markers),
                "reviewed_source_digest": source_digest, "reviewed_policy_digest": policy_digest,
                "replacement_relink_target": replacement_relink_target,
                "same_physical_mapping": same_physical_mapping,
                "feature_class_association": feature_class_association,
                "managed_resource_restoration": managed_resource_restoration,
                "refresh_review_basis": refresh_review_basis, "refresh_numeric_authority": refresh_numeric_authority,
                "native_reconstruction": native_reconstruction,
                "native_elective_decision": native_elective_decision,
                "elective_review_token": elective_review_token,
                "native_requalification_markers": native_requalification_markers,
                "native_spell_origin_plan": (json.loads(json.dumps(native_spell_origin_plan))
                    if native_spell_origin_plan is not None else None),
                "native_actor_id": native_actor_id, "native_result": native_result,
                "native_action_id": native_action_id, "native_proof_digest": native_proof_digest,
                "native_review_token": native_review_token,
            }
            if native_elective_decision is not None:
                from .character_language_electives import PendingElectiveDecision
                if (native or type(native_elective_decision) is not PendingElectiveDecision
                        or not callable(elective_review_validator) or elective_review_validator() is not True):
                    raise CharacterStateConflictError("Language Review requires its genuine normal-age Update token.")
                result = object.__new__(cls)
                object.__setattr__(result, "_complete", False)
                object.__setattr__(result, "_native_admission", None)
                try:
                    for name, value in values.items():
                        object.__setattr__(result, name, value)
                    facts = cls._request_admission_facts(elective_review_token,
                        native_elective_decision.prior_identity["actor_user_id"],
                        definition.campaign_slug, definition.character_slug)
                    prior = cls._prior_admission_facts(prior_record)
                    object.__setattr__(result, "_native_admission", cls._new_native_record(result, facts, prior, "CAPTURING"))
                    result._native_phase("CAPTURING", request_facts=facts, prior_facts=prior, next_phase="COMPLETE")
                    native_elective_decision.bind_review_owner(result)
                    return result
                except BaseException:
                    result.discard_native_admission()
                    raise
            if not native:
                if feature_class_association is not None:
                    from .character_feature_class_association import PendingFeatureClassAssociation
                    if (type(feature_class_association) is not PendingFeatureClassAssociation
                            or same_physical_mapping is not None or native_reconstruction is not None
                            or native_elective_decision is not None):
                        raise CharacterStateConflictError("Feature association cannot borrow another proof family.")
                    feature_class_association.validate_binding(prior_record, definition, desired_state,
                                                               feature_class_association.actor_id)
                return cls(**values)
            # Stage only on the original owner, without constructing any
            # temporary complete native proof or transferring its record.
            for name, value in values.items():
                object.__setattr__(native_review_admission, name, value)
            native_review_admission._validate_native_activation_fields(
                prior_record, definition, desired_state, native_actor_id, source_read_owner=source_read_owner)
            if native_spell_origin_plan is not None:
                native_review_admission._validate_native_spell_origin_fields(
                    prior_record, definition, desired_state, native_actor_id, source_read_owner=source_read_owner)
            if source_read_owner is not None:
                source_read_owner.checkpoint()
            native_review_admission._native_phase("CAPTURING", request_facts=facts,
                prior_facts=prior, next_phase="COMPLETE")
            return native_review_admission
        except BaseException:
            if type(native_review_admission) is cls:
                native_review_admission.discard_native_admission()
            raise

    def native_activation_binding(self, prior_record, definition, state, actor_id, *, source_read_owner=None):
        """Authenticate full native custody, never just its spell subproof.

        Fresh real producer issuance and original/current joins are required at
        each write gate. The early producer itself never depends on this proof.
        """
        try:
            self.require_complete()
            result = self._validate_native_activation_fields(prior_record, definition, state, actor_id, source_read_owner=source_read_owner)
            self.require_complete()
            return result
        except BaseException:
            self.discard_native_admission()
            raise

    def _validate_native_activation_fields(self, prior_record, definition, state, actor_id, *, source_read_owner=None):
        try:
            phase = self._native_validation_phase()
            facts = self._request_admission_facts(self.native_review_token, actor_id,
                prior_record.definition.campaign_slug, prior_record.definition.character_slug)
            prior = self._prior_admission_facts(prior_record)
            self._native_phase(phase, request_facts=facts, prior_facts=prior)
            from .character_native_requalification import NativeRequalification, native_requalification_state
            from .character_equipment_activation import native_activation_readiness
            from .character_source_repair_routes import _token_serializer
            from itsdangerous import BadSignature
            try:
                # The route enforces normal expiry once at Apply admission. Here
                # verify the same signed claims without expiring an admitted write
                # midway through its fresh reserved validation.
                claims = _token_serializer().loads(self.native_review_token)
            except (BadSignature, TypeError, ValueError) as exc:
                raise CharacterStateConflictError("Native activation requires the signed manager Review.") from exc
            if (not isinstance(self.native_result, NativeRequalification)
                    or type(actor_id) is not int or actor_id < 1 or actor_id != self.native_actor_id
                    or not self.native_action_id or not self.native_proof_digest
                    or not callable(self.refresh_review_basis) or not callable(self.refresh_numeric_authority)
                    or not self.reviewed_source_digest or not self.reviewed_policy_digest
                    or prior_record.committed_revision != self.prior_revision
                    or self._digest(prior_record.definition.to_dict()) != self.prior_definition_digest
                    or self._digest(prior_record.state_record.state) != self.prior_state_digest
                    or self._digest(definition.to_dict()) != self.candidate_definition_digest
                    or self._digest(state) != self.desired_state_digest):
                raise CharacterStateConflictError("Native activation requires genuine reviewed custody.")
            if (type(claims) is not dict or claims.get("v") != 1
                    or claims.get("action") != "native_requalify" or type(claims.get("actor")) is not int
                    or claims.get("actor") != actor_id
                    or (claims.get("campaign"), claims.get("character")) != (
                        definition.campaign_slug, definition.character_slug)
                    or claims.get("action_id") != self.native_action_id
                    or claims.get("definition_digest") != self.prior_definition_digest
                    or claims.get("import_digest") != self._digest(prior_record.import_metadata.to_dict())
                    or type(claims.get("state_revision")) is not int
                    or claims["state_revision"] != prior_record.state_record.revision
                    or claims.get("state_digest") != self.prior_state_digest
                    or claims.get("candidate_digest") != self.candidate_definition_digest
                    or claims.get("native_proof_digest") != self.native_proof_digest
                    or claims.get("source_digest") != self.reviewed_source_digest
                    or self._digest({"candidate": definition.to_dict(), "effect_delta": claims.get("effect_delta"),
                                     "context_proof_digest": ""}) != self.reviewed_policy_digest):
                raise CharacterStateConflictError("Signed native custody changed before publication.")
            self.native_result.validate_binding(prior_record, actor_id, self.native_action_id)
            # One real regeneration supplies both the existing source/policy basis
            # and its issued native result. Never run a second producer here.
            refreshed = (self.refresh_review_basis(source_read_owner=source_read_owner)
                         if source_read_owner is not None else self.refresh_review_basis())
            if (type(refreshed) is not tuple or len(refreshed) != 3
                    or refreshed[:2] != (self.reviewed_source_digest, self.reviewed_policy_digest)
                    or not isinstance(refreshed[2], NativeRequalification)):
                raise CharacterStateConflictError("Native activation producer is unavailable.")
            fresh = refreshed[2]
            fresh.validate_binding(prior_record, actor_id, self.native_action_id)
            for result in (self.native_result, fresh):
                desired = native_requalification_state(prior_record, result, actor_id)
                if (self._digest({"provenance": result.provenance, "authorizations": result.authorizations,
                                 "state": desired}) != self.native_proof_digest
                        or self._digest(result.candidate.to_dict()) != self.candidate_definition_digest
                        or self._digest(result.authorizations) != self._digest(self.native_requalification_markers)
                        or self._digest(result.provenance.get("spell_origin_plan")) != self._digest(self.native_spell_origin_plan)
                        or self._digest(desired) != self.desired_state_digest):
                    raise CharacterStateConflictError("Reviewed native result changed before publication.")
            native_activation_readiness(prior_record, definition, state, final=True)
            unchanged_state = self._digest(state) == self.prior_state_digest
            self._native_phase(phase, request_facts=facts, prior_facts=prior)
            if source_read_owner is not None:
                source_read_owner.checkpoint()
            return unchanged_state
        except BaseException:
            self.discard_native_admission()
            raise

    def native_spell_origin_delta(self, prior_record, definition, state, actor_id, *, source_read_owner=None,
                                  source_read_phase=None):
        """Authenticate only this pending actor's exact source-derived delta."""
        try:
            self._require_native_complete_binding(prior_record, actor_id)
            if self.native_spell_origin_plan is None:
                return None
            plan = self._validate_native_spell_origin_fields(prior_record, definition, state, actor_id,
                source_read_owner=source_read_owner, source_read_phase=source_read_phase)
            self.require_complete()
            return plan
        except BaseException:
            self.discard_native_admission()
            raise

    def _validate_native_spell_origin_fields(self, prior_record, definition, state, actor_id, *, source_read_owner=None,
                                             source_read_phase=None):
        try:
            phase = self._native_validation_phase()
            facts = self._request_admission_facts(self.native_review_token, actor_id,
                prior_record.definition.campaign_slug, prior_record.definition.character_slug)
            prior = self._prior_admission_facts(prior_record)
            self._native_phase(phase, request_facts=facts, prior_facts=prior)
            from .auth import get_systems_service
            from .character_native_requalification import prepare_spell_origin_correction
            from .character_spell_grants import grant_model_digest
            if (type(actor_id) is not int or actor_id < 1 or actor_id != self.native_actor_id
                    or prior_record.committed_revision != self.prior_revision
                    or self._digest(prior_record.definition.to_dict()) != self.prior_definition_digest
                    or self._digest(prior_record.state_record.state) != self.prior_state_digest
                    or self._digest(definition.to_dict()) != self.candidate_definition_digest
                    or self._digest(state) != self.desired_state_digest
                    or not callable(self.refresh_review_basis) or not callable(self.refresh_numeric_authority)
                    or not self.native_requalification_markers):
                raise CharacterStateConflictError("Reviewed spell-origin correction changed before publication.")
            try:
                from .character_source_reads import native_character_source_context
                with native_character_source_context(prior_record, source_read_owner=source_read_owner,
                        source_read_phase=source_read_phase,
                        purpose="pending-spell-origin") as (_source_phase, source_service, _pages, _owner):
                    checkpoint_result = None
                    if self.native_spell_origin_plan.get("schema_version") in {3, 4}:
                        from .character_native_requalification import NativeRequalification
                        from .character_spell_reconstruction import PendingSpellCheckpoint, validate_saved_spell_checkpoint
                        result = self.native_result
                        if (type(result) is not NativeRequalification
                                or result.provenance.get("schema_version") not in {5, 6}
                                or result.provenance.get("spell_origin_plan") != self.native_spell_origin_plan
                                or result.candidate.to_dict() != definition.to_dict()
                                or tuple(result.authorizations) != self.native_requalification_markers
                                or type(result.spell_checkpoint) is not PendingSpellCheckpoint
                                or result.spell_checkpoint.checkpoint != self.native_spell_origin_plan.get("current_checkpoint")
                                or not result.spell_checkpoint.matches_definition(definition)):
                            raise ValueError("Current spell confirmation needs its exact reviewed native result.")
                        checkpoint = result.spell_checkpoint.checkpoint
                        if (checkpoint.get("actor_id") != actor_id
                                or checkpoint.get("action_id") != self.native_action_id
                                or checkpoint.get("prior_generation") != prior_record.committed_revision
                                or checkpoint.get("prior_state_revision") != prior_record.state_record.revision
                                or checkpoint.get("prior_definition_digest") != self.prior_definition_digest):
                            raise ValueError("Current spell confirmation changed its original actor or target.")
                        result.validate_binding(prior_record, actor_id, self.native_action_id,
                                                source_read_phase=_source_phase)
                        validate_saved_spell_checkpoint(prior_record.definition, definition, checkpoint)
                        checkpoint_result = result
                    corrected, plan = prepare_spell_origin_correction(
                        prior_record.definition, source_service, self.native_spell_origin_plan.get("request"),
                        prior_generation=prior_record.committed_revision,
                        prior_definition_digest=self.prior_definition_digest,
                        prior_state_revision=prior_record.state_record.revision,
                        actor_id=actor_id, action_id=self.native_action_id)
                    if checkpoint_result is not None:
                        from .character_spell_reconstruction import prepare_current_spell_checkpoint
                        # Reproduce the final normalized input scope only after
                        # authenticating the genuine issuer-bound candidate.
                        # The original generation still supplies every raw row;
                        # fresh sources and the complete new grant mapping own
                        # the recomputed roles. This is not another producer.
                        checkpoint_candidate, checkpoint, pending = prepare_current_spell_checkpoint(
                            prior_record.definition, checkpoint_result.candidate, source_service,
                            actor_id=actor_id, action_id=self.native_action_id,
                            prior_generation=prior_record.committed_revision,
                            prior_state_revision=prior_record.state_record.revision,
                            automatic_ids={row["spell_id"] for row in plan["automatic"]})
                        if (checkpoint_candidate.to_dict() != checkpoint_result.candidate.to_dict()
                                or not pending.matches_definition(checkpoint_candidate)):
                            raise ValueError("The final current spell confirmation changed during reissue.")
                        plan["current_checkpoint"] = checkpoint
                        plan["result_spellcasting_digest"] = self._digest(checkpoint_candidate.spellcasting)
                    if (self._digest(plan) != self._digest(self.native_spell_origin_plan)
                            or self._digest(corrected.spellcasting) != self._digest(definition.spellcasting)
                            or grant_model_digest(corrected) != grant_model_digest(definition)
                            or self._digest(state) != self._digest(prior_record.state_record.state)):
                        raise ValueError("The exact spell-origin delta changed.")
                    if checkpoint_result is not None:
                        validate_saved_spell_checkpoint(prior_record.definition, definition, plan["current_checkpoint"])
                    for row in plan["automatic"]:
                        key = ("spell_choice", f"spell_choice:{row['spell_id']}", "selection")
                        matches = [marker for marker in self.native_requalification_markers
                                   if isinstance(marker, dict)
                                   and (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
                        if matches:
                            raise ValueError("An automatic feature grant cannot mint an elective selection witness.")
                    self._native_phase(phase, request_facts=facts, prior_facts=prior)
                    return plan

            except SourceReadConnectionFatal:
                raise
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                raise CharacterStateConflictError("Reviewed spell-origin sources or witnesses changed.") from exc
        except BaseException:
            self.discard_native_admission()
            raise

    def prospective_authority(self, authority: Any, definition: CharacterDefinition,
                              prior_state: dict[str, Any], *, source_read_owner=None) -> Any:
        try:
            self.require_complete()
            if self.refresh_numeric_authority is not None:
                if self._digest(definition.to_dict()) != self.candidate_definition_digest:
                    raise CharacterStateConflictError("Reviewed native inputs changed before publication.")
                authority = (self.refresh_numeric_authority(source_read_owner=source_read_owner)
                             if source_read_owner is not None else self.refresh_numeric_authority())
            if self.page_feature_markers:
                from .character_source_authority import with_pending_page_feature_witnesses
                authority = with_pending_page_feature_witnesses(
                    authority, definition, prior_state, self.page_feature_markers,
                )
            self.require_complete()
            return authority
        except BaseException:
            self.discard_native_admission()
            raise

    def recheck(self, prior_record: CharacterRecord, definition: CharacterDefinition,
                desired_state: dict[str, Any], authority: Any, config_revision: int, *,
                source_read_owner=None, source_read_refresh=False) -> None:
        try:
            _token, actor = self._custody_credentials()
            self._require_native_complete_binding(prior_record, actor)
            if (prior_record.committed_revision != self.prior_revision
                    or self._digest(prior_record.definition.to_dict()) != self.prior_definition_digest
                    or self._digest(prior_record.state_record.state) != self.prior_state_digest
                    or self._digest(definition.to_dict()) != self.candidate_definition_digest
                    or self._digest(desired_state) != self.desired_state_digest
                    or authority is None or authority.identity != self.authority_identity
                    or authority.source_snapshot_digest != self.source_snapshot_digest
                    or config_revision != self.config_revision):
                raise CharacterStateConflictError("Reviewed Character source changed before publication.")
            if self.native_result is not None:
                self.native_activation_binding(prior_record, definition, desired_state, self.native_actor_id,
                                               source_read_owner=source_read_owner)
            elif self.refresh_review_basis is not None and (
                (self.refresh_review_basis(source_read_owner=source_read_owner)
                 if self.same_physical_mapping is not None or self.feature_class_association is not None or self.managed_resource_restoration is not None or source_read_refresh else self.refresh_review_basis()) != (
                    self.reviewed_source_digest, self.reviewed_policy_digest,
                )
            ):
                raise CharacterStateConflictError("Reviewed Character policy changed before publication.")
            self.require_complete()
        except BaseException:
            self.discard_native_admission()
            raise


@dataclass(frozen=True, slots=True)
class PendingNativeLevelUpAuthority:
    """In-memory proof for one native publication; never journaled as a witness."""

    prior_revision: int
    prior_definition_digest: str
    candidate_definition_digest: str
    desired_state_digest: str
    authority_identity: str
    source_snapshot_digest: str
    markers: tuple[dict[str, Any], ...]
    refresh: Callable[[], Any] = field(repr=False, compare=False)
    claimed: bool = field(default=False, repr=False, compare=False)
    claim_lock: Lock = field(default_factory=Lock, repr=False, compare=False)
    prepare_audit: Callable[[], dict[str, Any]] | None = field(default=None, repr=False, compare=False)
    advancement_intent: Any | None = field(default=None, repr=False, compare=False)

    def claim(self) -> None:
        with self.claim_lock:
            if self.claimed:
                raise CharacterStateConflictError("Native level-up proof was already used.")
            object.__setattr__(self, "claimed", True)

    @classmethod
    def from_proof(
        cls, *, prior_record: CharacterRecord, definition: CharacterDefinition,
        desired_state: dict[str, Any], authority: Any,
        markers: tuple[dict[str, Any], ...], refresh: Callable[[], Any],
        prior_authority: Any | None = None, advancement_intent: Any | None = None,
        actor_id: int | None = None, systems_service: Any | None = None,
        campaign_page_records: list[Any] | None = None,
        prepare_audit: Callable[[], dict[str, Any]] | None = None,
    ) -> PendingNativeLevelUpAuthority:
        from .character_equipment_activation import definition_digest
        from .character_source_authority import numeric_target_values, numeric_value_digest
        from .character_source_authority import (
            NativeAdvancementValidationError, native_advancement_input_target,
        )

        if not markers or not callable(refresh) or authority is None:
            raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
        values = numeric_target_values(definition, desired_state)
        action_ids = {marker.get("action_id") for marker in markers}
        if len(action_ids) != 1 or None in action_ids:
            raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
        # Capacity is a whole-transition claim, independent of whether a typed
        # decision changed or an empty decision envelope will be recorded.
        validate_native_spell_choice_capacity(
            prior_record, definition, desired_state, systems_service=systems_service,
            campaign_page_records=campaign_page_records, advancement_intent=advancement_intent,
        )
        pending_decisions = set()
        if any(isinstance(row, dict) and "native_class_choice_state" in row
               for owner in (prior_record.definition, definition)
               for row in owner.spellcasting.get("spells") or []):
            from .character_source_authority import (
                NativeAdvancementIntent, validate_native_spell_choice_decision_transition,
            )
            if (not isinstance(advancement_intent, NativeAdvancementIntent)
                    or not advancement_intent.matches_resource_readback(prior_record.definition, definition)):
                raise NativeAdvancementValidationError(
                    "This advancement could not be validated. Review its choices.")
            decisions = validate_native_spell_choice_decision_transition(
                prior_record, definition, desired_state, prior_authority=prior_authority,
                actor_id=actor_id, operation_kind="interactive_update", allow_progression=True,
                systems_service=systems_service, campaign_page_records=campaign_page_records,
            )
            pending_decisions = {row["spell_id"] for row in decisions}
        for marker in markers:
            target = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
            target_id = str(marker.get("target_id") or "")
            if (marker.get("provenance") != "native_level_up"
                    or target not in values
                    or marker.get("value_digest") != numeric_value_digest(values[target])):
                raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
            if marker.get("target_kind") == "spell_metric":
                status = None
                if target_id not in authority.verified_formula_rows:
                    raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
            elif marker.get("target_kind") == "spell_choice":
                status = None
                if (target_id.removeprefix("spell_choice:") not in authority.verified_spell_choices
                        and target_id.removeprefix("spell_choice:") not in pending_decisions):
                    raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
            elif marker.get("target_kind") in {"field", "proficiency"}:
                status = authority.field_status(target_id)
            else:
                kind, _, stable_id = target_id.partition(":")
                status = authority.resource_status(kind, stable_id)
            # An ability-base witness authorizes the explicit input. Its final
            # score is projected later from qualified effects, so this status
            # deliberately does not expose that score as an effective total.
            verified_base = (
                status is not None and status.status == "VERIFIED"
                and status.reason == "baseline_authorized"
                and marker.get("metric") == "base"
                and native_advancement_input_target(
                    marker.get("target_kind"), target_id, marker.get("metric"))
            )
            if status is not None and not (status.is_effective or verified_base):
                raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
        return cls(
            prior_record.state_record.revision,
            definition_digest(prior_record.definition), definition_digest(definition),
            numeric_value_digest(desired_state), authority.identity,
            authority.source_snapshot_digest, tuple(markers), refresh,
            prepare_audit=prepare_audit, advancement_intent=advancement_intent,
        )

    def recheck(
        self, prior_record: CharacterRecord, definition: CharacterDefinition,
        desired_state: dict[str, Any],
    ) -> Any:
        from .character_equipment_activation import definition_digest
        from .character_source_authority import numeric_target_values, numeric_value_digest

        if (not self.claimed or prior_record.state_record.revision != self.prior_revision
                or definition_digest(prior_record.definition) != self.prior_definition_digest
                or definition_digest(definition) != self.candidate_definition_digest
                or numeric_value_digest(desired_state) != self.desired_state_digest):
            raise CharacterStateConflictError("Native level-up proof changed before publication.")
        values = numeric_target_values(definition, desired_state)
        if any(
            (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) not in values
            or marker.get("value_digest") != numeric_value_digest(values.get((
                marker.get("target_kind"), marker.get("target_id"), marker.get("metric")
            )))
            for marker in self.markers
        ):
            raise CharacterStateConflictError("Native level-up value changed before publication.")
        authority = self.refresh()
        if (authority is None or authority.identity != self.authority_identity
                or authority.source_snapshot_digest != self.source_snapshot_digest):
            raise CharacterStateConflictError("Native level-up source changed before publication.")
        return authority


def validate_native_spell_choice_capacity(prior_record, definition, state, *,
        systems_service, campaign_page_records, advancement_intent=None, connection=None,
        adoption_proof=None, actor_id=None):
    """Rebuild complete affected pools from actual prior custody and sources."""
    from .character_source_authority import (
        build_reconciled_source_authority, native_spell_choice_capacity_affected,
        numeric_value_digest, validate_native_spell_choice_capacity_transition,
    )
    before = prior_record.definition
    if not native_spell_choice_capacity_affected(before, definition):
        return ()
    if systems_service is None or campaign_page_records is None:
        raise CharacterStateConflictError("The current class choice source context is unavailable.")
    from .character_source_repair import (
        _decision_generation, load_verified_manual_actions, load_verified_numeric_actions,
    )
    db = connection if connection is not None else get_db()
    _decision_generation(db, before.campaign_slug, before.character_slug,
        prior_record.committed_revision, numeric_value_digest(before.to_dict()))
    numeric = load_verified_numeric_actions(
        before.campaign_slug, before.character_slug, connection=db, strict=True)
    manual = load_verified_manual_actions(
        before.campaign_slug, before.character_slug, connection=db, strict=True)
    prior_authority = build_reconciled_source_authority(
        definition=before, state=prior_record.state_record.state,
        state_revision=prior_record.state_record.revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_numeric_actions=numeric, verified_manual_actions=manual,
    )
    return validate_native_spell_choice_capacity_transition(
        before, definition, state, prior_authority=prior_authority,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=numeric, verified_manual_actions=manual,
        advancement_intent=advancement_intent,
        adoption_proof=adoption_proof, prior_record=prior_record, actor_id=actor_id,
    )


def validate_native_grant_transition(prior_record, definition, state, *,
                                     reviewed_source_proof=None, pending_numeric_authority=None,
                                     actor_id=None, connection=None, operation_kind=None,
                                     trusted_spell_choice_authoring=False,
                                     prior_authority_provider=None, source_context_provider=None,
                                     capacity_snapshots=None, source_read_owner=None,
                                     source_read_context_provider=None, _replacement_preview_target=""):
    """Keep ordinary writes from silently erasing or manufacturing grant custody."""
    from .character_spell_grants import grant_model_digest, validate_native_grant_model
    from .character_feature_composition import validate_retained_replacement_transition
    # This preview parameter is supplied only by the read-only Source Repair
    # preflight below. Neither update nor the reserved publisher exposes it.
    relink_target = _replacement_preview_target
    owner_annotations = {}
    if type(reviewed_source_proof) is PendingReviewedSourceProof:
        reviewed_source_proof.require_complete()
        if (reviewed_source_proof.prior_definition_digest != PendingReviewedSourceProof._digest(prior_record.definition.to_dict())
                or reviewed_source_proof.candidate_definition_digest != PendingReviewedSourceProof._digest(definition.to_dict())):
            raise CharacterStateConflictError("Replacement source Review changed before publication.")
        relink_target = reviewed_source_proof.replacement_relink_target
        result = reviewed_source_proof.native_result
        if result is not None:
            from .character_native_requalification import NativeRequalification, _admission_feature_rows
            if type(result) is not NativeRequalification:
                raise CharacterStateConflictError("Replacement owner custody has an unsupported native proof.")
            if result.provenance.get("schema_version") == 6:
                reviewed_source_proof._require_native_complete_binding(prior_record, actor_id)
                result._validate_candidate_binding(prior_record, actor_id, reviewed_source_proof.native_action_id)
                if (result.candidate.to_dict() != definition.to_dict() or state != prior_record.state_record.state
                        or PendingReviewedSourceProof._digest(_admission_feature_rows(prior_record.definition, result.provenance))
                            != PendingReviewedSourceProof._digest(definition.features)):
                    raise CharacterStateConflictError("Replacement owner annotations changed from their exact native result.")
                for admission in result.provenance["current_resource_inputs"]:
                    for identity in admission["feature_ids"]:
                        if identity in owner_annotations and owner_annotations[identity] != admission["class_row_id"]:
                            raise CharacterStateConflictError("Replacement owner annotations conflict.")
                        owner_annotations[identity] = admission["class_row_id"]
        reconstruction = reviewed_source_proof.native_reconstruction
        if reconstruction is not None:
            from .character_reconstruction_authority import PendingNativeReconstruction
            if (type(reconstruction) is not PendingNativeReconstruction
                    or operation_kind != "character_update_apply"
                    or pending_numeric_authority is not None or result is not None
                    or reviewed_source_proof.native_elective_decision is not None):
                raise CharacterStateConflictError("Replacement owner annotations need their separate reconstruction proof.")
            try:
                owner_annotations = reconstruction.replacement_owner_annotations(
                    prior_record, definition, state, actor_id)
            except (TypeError, ValueError) as exc:
                raise CharacterStateConflictError(str(exc)) from exc
    if relink_target and operation_kind != "character_update_apply":
        raise CharacterStateConflictError("Replacement relink needs the reviewed manager Update operation.")
    try:
        validate_retained_replacement_transition(prior_record.definition, definition,
            relink_target=relink_target, owner_annotations=owner_annotations)
    except (TypeError, ValueError) as exc:
        raise CharacterStateConflictError(str(exc)) from exc
    old = prior_record.definition
    present = ("native_spell_grants" in definition.spellcasting
               or "native_acquisitions" in definition.source)
    prior_present = ("native_spell_grants" in old.spellcasting or "native_acquisitions" in old.source)
    try:
        adoption_proof = None
        checkpoint_result = None
        if present and not prior_present:
            if (operation_kind != "character_update_apply"
                    or type(reviewed_source_proof) is not PendingReviewedSourceProof):
                raise CharacterStateConflictError("First native model adoption needs its exact reviewed migration.")
            plan = reviewed_source_proof.native_spell_origin_delta(prior_record, definition, state, actor_id, source_read_owner=source_read_owner)
            if not isinstance(plan, dict) or plan.get("schema_version") not in {2, 3, 4}:
                raise CharacterStateConflictError("First native model adoption needs its exact reviewed migration.")
            if plan.get("schema_version") in {3, 4}:
                from .character_native_requalification import NativeRequalification
                result = reviewed_source_proof.native_result
                if (type(result) is not NativeRequalification or result.provenance.get("schema_version") not in {5, 6}
                        or result.provenance.get("spell_origin_plan") != plan):
                    raise CharacterStateConflictError("Current spell adoption needs its exact reviewed native result.")
                checkpoint_result = result
            adoption_proof = reviewed_source_proof
        if prior_present:
            # Retention is a custody claim even when there are no occurrences
            # or the proposed model has exactly the same digest. Reload the
            # actual saved proof; prospective authority cannot prove old facts.
            from .character_source_repair import require_confirmed_native_grant_custody
            require_confirmed_native_grant_custody(prior_record, connection=connection)
        if present:
            validate_native_grant_model(definition)
        from .character_source_authority import native_spell_choice_capacity_affected
        capacity_affected = native_spell_choice_capacity_affected(old, definition)
        typed = any(isinstance(row, dict) and "native_class_choice_state" in row
                    for owner in (old, definition) for row in owner.spellcasting.get("spells") or [])
        decisions = ()
        if capacity_affected or typed:
            if not callable(source_context_provider):
                raise CharacterStateConflictError("The current class choice source context is unavailable.")
            from contextlib import nullcontext
            source_scope = (source_read_context_provider(prior_record, source_read_owner=source_read_owner)
                if source_read_owner is not None and source_read_context_provider is not None
                else nullcontext(source_context_provider(prior_record)))
            prior_authority = (prior_authority_provider()
                if typed and source_read_owner is not None and prior_authority_provider is not None else None)
            with source_scope as (systems_service, page_records):
                if systems_service is None or page_records is None:
                    raise CharacterStateConflictError("The current class choice source context is unavailable.")
                pools = validate_native_spell_choice_capacity(
                    prior_record, definition, state, systems_service=systems_service,
                    campaign_page_records=page_records, connection=connection,
                    advancement_intent=(pending_numeric_authority.advancement_intent
                        if isinstance(pending_numeric_authority, PendingNativeLevelUpAuthority) else None),
                    adoption_proof=adoption_proof, actor_id=actor_id,
                )
                if capacity_snapshots is not None:
                    capacity_snapshots.extend(pools)
                if typed:
                    from .character_source_authority import validate_native_spell_choice_decision_transition
                    if source_read_owner is None:
                        prior_authority = prior_authority_provider() if prior_authority_provider is not None else None
                    decisions = validate_native_spell_choice_decision_transition(
                        prior_record, definition, state, prior_authority=prior_authority,
                        actor_id=actor_id, operation_kind=operation_kind,
                        allow_management=trusted_spell_choice_authoring and operation_kind == "interactive_update",
                        allow_progression=isinstance(pending_numeric_authority, PendingNativeLevelUpAuthority),
                        systems_service=systems_service, campaign_page_records=page_records, connection=connection,
                        checkpoint_proof=checkpoint_result,
                    )
        if not present and not prior_present:
            return decisions
        if grant_model_digest(old) == grant_model_digest(definition):
            return decisions
        if reviewed_source_proof is not None:
            plan = reviewed_source_proof.native_spell_origin_delta(prior_record, definition, state, actor_id, source_read_owner=source_read_owner)
            if plan is not None and plan.get("schema_version") in {2, 3, 4}:
                return decisions
        if present and isinstance(pending_numeric_authority, PendingNativeLevelUpAuthority):
            pending_numeric_authority.recheck(prior_record, definition, state)
            return decisions
    except SourceReadConnectionFatal:
        raise
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise CharacterStateConflictError("Native grant custody changed before publication.") from exc
    raise CharacterStateConflictError("This update needs an authenticated native grant migration or progression.")


def validate_native_spell_choice_authorizations(prior_record, definition, state, authority, *, actor_id):
    """Constrain guarded authoring to exact changed, currently sourced choices."""
    from .character_source_authority import numeric_target_values, valid_numeric_authorization
    if type(actor_id) is not int or actor_id < 1 or authority is None:
        raise CharacterStateConflictError("Spell choice authority is unavailable for this update.")
    old_values = numeric_target_values(prior_record.definition, prior_record.state_record.state)
    values = numeric_target_values(definition, state)
    old_markers = list(prior_record.definition.source.get("source_authorizations") or [])
    markers = list(definition.source.get("source_authorizations") or [])
    admitted = []
    for marker in markers:
        if not isinstance(marker, dict) or marker.get("provenance") != "native_spell_choice":
            continue
        if marker in old_markers:
            continue
        key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
        matching = [row for row in markers if isinstance(row, dict) and
                    (row.get("target_kind"), row.get("target_id"), row.get("metric")) == key]
        if (not all(isinstance(value, str) for value in key)
                or key[0] != "spell_choice" or key[2] != "selection" or key not in values
                or old_values.get(key) == values[key] or len(matching) != 1
                or marker.get("schema_version") != 2
                or not authority.numeric_basis_digest(key[1])
                or not valid_numeric_authorization(marker, character_slug=definition.character_slug,
                    target_kind=key[0], target_id=key[1], metric=key[2], raw_value=values[key],
                    verified_actions=(marker,))):
            raise CharacterStateConflictError("A spell choice marker needs its exact current selection.")
        admitted.append(marker)
    return tuple(admitted)


@dataclass(frozen=True, slots=True)
class CharacterReconciliationHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class CharacterReconciliationOperation:
    operation_id: str
    campaign_slug: str
    character_slug: str
    operation_kind: str
    previous_definition_digest: str
    desired_definition_digest: str
    previous_import_digest: str
    desired_import_digest: str
    previous_state_digest: str
    desired_state_digest: str
    previous_state_revision: int
    desired_state_revision: int
    desired_definition_yaml: bytes = field(repr=False, compare=False)
    desired_import_yaml: bytes = field(repr=False, compare=False)
    previous_asset_ref: str
    desired_asset_ref: str
    previous_asset_digest: str
    desired_asset_digest: str
    desired_asset_bytes: bytes = field(repr=False, compare=False)
    audit_event_type: str | None
    audit_actor_user_id: int | None
    audit_target_user_id: int | None
    audit_metadata_json: str | None
    state: str
    error_code: str


@dataclass(frozen=True, slots=True)
class CharacterDeletionHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class CharacterDeletionOperation:
    operation_id: str
    campaign_slug: str
    character_slug: str
    operation_kind: str
    definition_present: bool
    definition_digest: str
    definition_size: int
    definition_tombstone_name: str
    import_present: bool
    import_digest: str
    import_size: int
    import_tombstone_name: str
    asset_present: bool
    asset_ref: str
    asset_digest: str
    asset_size: int
    asset_tombstone_name: str
    previous_state_present: bool
    previous_state_revision: int
    previous_state_digest: str
    previous_assignment_present: bool
    previous_assignment_digest: str
    deleted_files: bool
    deleted_state: bool
    deleted_assignment: bool
    deleted_assets: bool
    audit_event_type: str | None
    audit_actor_user_id: int | None
    audit_target_user_id: int | None
    audit_metadata_json: str | None
    state: str
    error_code: str


@dataclass(frozen=True, slots=True)
class CharacterDeletionResult:
    character_slug: str
    deleted_files: bool
    deleted_state: bool
    deleted_assignment: bool
    deleted_assets: bool


@dataclass(frozen=True, slots=True)
class _DeletionFileEvidence:
    present: bool
    digest: str
    size: int
    tombstone_name: str


def is_character_reconciliation_protected(
    campaign_slug: str,
    character_slug: str,
) -> bool:
    if not has_app_context():
        return False
    try:
        row = get_db().execute(
            """
            SELECT 1 FROM (
                SELECT campaign_slug, character_slug, state
                FROM character_reconciliation_operations
                UNION ALL
                SELECT campaign_slug, character_slug, state
                FROM character_deletion_operations
            ) AS active_character_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table: character_deletion_operations" in str(exc).lower():
            row = get_db().execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                LIMIT 1
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            return row is not None
        if "no such table" in str(exc).lower():
            return False
        raise
    return row is not None


def _character_process_lock(key: tuple[str, str]) -> RLock:
    with _CHARACTER_LOCKS_GUARD:
        lock = _CHARACTER_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _CHARACTER_LOCKS[key] = lock
        return lock


def _has_active_character_deletion(
    connection: Any,
    campaign_slug: str,
    character_slug: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM character_deletion_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        is not None
    )


def _has_pending_character_publication_recovery() -> bool:
    return (
        get_db()
        .execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE state IN ('prepared', 'repository_pending')
            LIMIT 1
            """
        )
        .fetchone()
        is not None
    )


def _has_pending_character_deletion_recovery() -> bool:
    return (
        get_db()
        .execute(
            """
            SELECT 1 FROM character_deletion_operations
            WHERE state IN ('prepared', 'repository_pending')
            LIMIT 1
            """
        )
        .fetchone()
        is not None
    )


class CharacterPublicationCoordinator:
    """Commit Character state, then reconcile its YAML pair forward."""

    def __init__(
        self,
        *,
        campaigns_dir: Path,
        database_path: Path,
        state_store: CharacterStateStore,
        repository: CharacterRepository,
        auth_store: AuthStore | None = None,
        hooks: CharacterReconciliationHooks | None = None,
    ) -> None:
        self.campaigns_dir = Path(campaigns_dir)
        self.database_path = Path(database_path)
        self.state_store = state_store
        self.repository = repository
        self.auth_store = auth_store
        self.hooks = hooks or CharacterReconciliationHooks()
        self.numeric_authority_provider: Callable[[CharacterRecord, CharacterDefinition], Any] | None = None
        self.native_choice_source_context_provider: Callable[[CharacterRecord], tuple[Any, list[Any]]] | None = None
        self.source_read_numeric_authority_provider = None
        self.source_read_native_choice_context_provider = None

    def create(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        initial_state: dict[str, Any],
        *,
        operation_kind: str,
        updated_by_user_id: int | None = None,
    ) -> CharacterRecord:
        from .committed_publication import active
        if active():
            from .committed_character_publication import publish_create
            return publish_create(self, definition, import_metadata, initial_state,
                                  operation_kind=operation_kind,
                                  updated_by_user_id=updated_by_user_id)
        self._validate_create_input(definition, import_metadata, operation_kind)
        from .character_equipment_activation import analyze_activation
        from .system_policy import is_dnd_5e_system
        if is_dnd_5e_system(definition.system) and analyze_activation(definition, initial_state)["blocked"]:
            raise CharacterStateConflictError(
                "Equipment activation identity needs repair before this Character can be created."
            )
        key = (definition.campaign_slug, definition.character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._prepare_operation(
                    definition,
                    import_metadata,
                    initial_state,
                    operation_kind=operation_kind,
                    updated_by_user_id=updated_by_user_id,
                )
                self._event("after_commit", operation.operation_id)
                return self._continue_operation(operation.operation_id)

    def _validate_update_preconditions(
        self, prior_record: CharacterRecord, definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata, desired_state: dict[str, Any], *,
        expected_revision: int, updated_by_user_id: int | None,
        operation_kind: str, audit_event_type: str | None,
        audit_actor_user_id: int | None, pending_numeric_authority: Any | None,
        reviewed_source_proof: PendingReviewedSourceProof | None,
        trusted_spell_choice_authoring: bool, reconcile_reimport_state: bool,
        reimport_source_authority: Any | None,
        audit_metadata: dict[str, Any] | None = None,
        _replacement_preview_target: str = "",
        _feature_association_preview: Any | None = None,
        _resource_restoration_preview: Any | None = None,
    ) -> bool:
        """Shared current-input checks; publication still rechecks under reservation."""
        from .character_spell_slots import require_slot_grants_preserved
        from .character_item_casting import require_storage_preserved
        require_slot_grants_preserved(prior_record.state_record.state, desired_state)
        require_storage_preserved(prior_record.state_record.state, desired_state)
        from .character_item_prepared import require_preserved
        require_preserved(prior_record.state_record.state, desired_state)
        self._validate_update_input(
            prior_record,
            definition,
            import_metadata,
            expected_revision=expected_revision,
            operation_kind=operation_kind,
        )
        if audit_event_type == "character_native_edited" and (
            type(updated_by_user_id) is not int or audit_actor_user_id != updated_by_user_id
            or prior_record.definition.system != "DND-5E" or definition.system != "DND-5E"
            or prior_record.definition.source.get("source_type") != "native_character_builder"
            or definition.source.get("source_type") != "native_character_builder"
        ):
            raise CharacterPublicationError("Native edit audit must match the Character and its writing actor.")
        from .committed_publication import active
        committed_mode = active()
        if reimport_source_authority is not None and (
            not committed_mode or not reconcile_reimport_state
            or operation_kind not in {"markdown_import", "pdf_import"}
        ):
            raise CharacterStateConflictError("Reimport source proof is unavailable for this update.")
        if pending_numeric_authority is not None:
            if not committed_mode:
                raise CharacterStateConflictError("Pending authority is unavailable for this update.")
            if operation_kind != "interactive_update" or not isinstance(
                pending_numeric_authority, PendingNativeLevelUpAuthority
            ):
                raise CharacterStateConflictError("Pending authority is unavailable for this update.")
            pending_numeric_authority.claim()
        if reviewed_source_proof is not None and (
            not committed_mode or not isinstance(reviewed_source_proof, PendingReviewedSourceProof)
        ):
            raise CharacterStateConflictError("Reviewed source proof is unavailable for this update.")
        if reviewed_source_proof is not None:
            reviewed_source_proof.require_complete()
        if (reviewed_source_proof is not None and reviewed_source_proof.native_result is not None
                and operation_kind != "character_update_apply"):
            raise CharacterStateConflictError("Native retention is unavailable for this update.")
        from .committed_character_publication import _prior_numeric_authority_loader
        load_prior_authority = _prior_numeric_authority_loader(self, prior_record)
        from .character_external_proficiencies import validate_transition as validate_external_proficiency
        from .auth import get_systems_service
        validate_external_proficiency(prior_record, definition, desired_state,
            actor_id=updated_by_user_id, metadata=audit_metadata,
            audit_event_type=audit_event_type, operation_kind=operation_kind,
            prior_authority=load_prior_authority, import_metadata=import_metadata,
            systems_service_provider=get_systems_service)
        validate_native_grant_transition(prior_record, definition, desired_state,
            reviewed_source_proof=reviewed_source_proof, pending_numeric_authority=pending_numeric_authority,
            actor_id=updated_by_user_id, operation_kind=operation_kind,
            trusted_spell_choice_authoring=trusted_spell_choice_authoring,
            prior_authority_provider=load_prior_authority,
            source_context_provider=self.native_choice_source_context_provider,
            _replacement_preview_target=_replacement_preview_target)
        reconstruction = (reviewed_source_proof.native_reconstruction
                          if reviewed_source_proof is not None else None)
        elective = (reviewed_source_proof.native_elective_decision
                    if reviewed_source_proof is not None else None)
        from .character_language_electives import PendingElectiveDecision, validate_transition
        if elective is not None:
            if operation_kind != "character_update_apply" or type(elective) is not PendingElectiveDecision:
                raise CharacterStateConflictError("Language decision proof is unavailable for this update.")
            elective.recheck(prior_record, definition, desired_state, updated_by_user_id)
        validate_transition(prior_record, definition, elective,
            actor_id=updated_by_user_id, state=desired_state)
        from .character_reconstruction_authority import PendingNativeReconstruction
        if reconstruction is not None:
            if (operation_kind != "character_update_apply"
                    or not isinstance(reconstruction, PendingNativeReconstruction)):
                raise CharacterStateConflictError("Reconstruction proof is unavailable for this update.")
            reconstruction.recheck(prior_record, definition, desired_state, updated_by_user_id)
        from .character_feature_proficiency_grants import validate_native_transition
        validate_native_transition(prior_record, definition, pending_numeric_authority)
        from .character_skill_adoptions import validate_transition as validate_skill_adoption_transition
        from .character_infusion_recipes import validate_transition as validate_recipe_transition
        validate_recipe_transition(prior_record, definition, reconstruction,
            actor_id=updated_by_user_id, state=desired_state)
        validate_skill_adoption_transition(prior_record, definition, reconstruction,
            actor_id=updated_by_user_id, state=desired_state)
        from .character_feature_proficiency_grants import validate_automatic_transition, validate_condition_transition
        validate_automatic_transition(prior_record, definition, reconstruction,
            actor_id=updated_by_user_id, state=desired_state)
        validate_condition_transition(prior_record, definition, reconstruction,
            actor_id=updated_by_user_id, state=desired_state)
        from .character_tracker_associations import validate_transition as validate_tracker_transition
        validate_tracker_transition(prior_record, definition, reconstruction,
            actor_id=updated_by_user_id, state=desired_state)
        prior_origin = dict(prior_record.definition.source or {}).get("native_reconstruction")
        candidate_origin = dict(definition.source or {}).get("native_reconstruction")
        if candidate_origin != prior_origin and reconstruction is None:
            raise CharacterStateConflictError("A native reconstruction origin cannot be copied into this update.")
        if reconstruction is None and elective is None and pending_numeric_authority is None and prior_origin is not None and (
                definition.source.get("native_reconstruction_choices") != prior_record.definition.source.get("native_reconstruction_choices")
                or dict(definition.source.get("native_progression") or {}).get("hp_recipe")
                != dict(prior_record.definition.source.get("native_progression") or {}).get("hp_recipe")):
            raise CharacterStateConflictError("Reviewed reconstruction inputs require a new reconstruction review.")
        from .character_source_authority import numeric_target_values
        reconstruction_values = numeric_target_values(definition, desired_state)
        prior_reconstruction_values = numeric_target_values(prior_record.definition, prior_record.state_record.state)
        for marker in dict(definition.source or {}).get("source_authorizations") or []:
            if isinstance(marker, dict) and marker.get("provenance") == "native_elective_decision":
                old = list(dict(prior_record.definition.source or {}).get("source_authorizations") or [])
                if not (elective is not None and marker in elective.markers) and old.count(marker) != 1:
                    raise CharacterStateConflictError("A language decision authorization cannot be copied or changed.")
            if isinstance(marker, dict) and marker.get("provenance") == "native_requalification":
                key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
                old = list(dict(prior_record.definition.source or {}).get("source_authorizations") or [])
                newly_reviewed = (operation_kind == "character_update_apply" and reviewed_source_proof is not None
                    and marker in reviewed_source_proof.native_requalification_markers)
                if not newly_reviewed and (old.count(marker) != 1 or key not in reconstruction_values
                        or prior_reconstruction_values.get(key) != reconstruction_values[key]):
                    raise CharacterStateConflictError("A native requalification witness cannot be copied or changed.")
            if not isinstance(marker, dict) or marker.get("provenance") != "native_reconstruction":
                continue
            key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
            old = list(dict(prior_record.definition.source or {}).get("source_authorizations") or [])
            if reconstruction is not None and marker in reconstruction.markers:
                continue
            if (old.count(marker) != 1 or key not in reconstruction_values
                    or prior_reconstruction_values.get(key) != reconstruction_values[key]):
                raise CharacterStateConflictError("A reconstruction source authorization cannot be copied or changed.")
        if committed_mode:
            prior_markers = list(dict(prior_record.definition.source or {}).get(
                "source_authorizations") or [])
            candidate_markers = list(dict(definition.source or {}).get(
                "source_authorizations") or [])
            for marker in candidate_markers:
                if not isinstance(marker, dict) or marker.get("provenance") != "page_feature_update":
                    continue
                if marker not in prior_markers and (
                    operation_kind != "character_update_apply"
                    or reviewed_source_proof is None
                    or marker not in reviewed_source_proof.page_feature_markers
                ):
                    raise CharacterStateConflictError(
                        "A page feature resource witness cannot be copied into this update."
                    )
        if trusted_spell_choice_authoring and operation_kind != "interactive_update":
            raise CharacterStateConflictError("Spell choice authority is unavailable for this update.")
        admitted_spell_choice_markers = ()
        if committed_mode and trusted_spell_choice_authoring:
            candidate_authority = (self.numeric_authority_provider(prior_record, definition, desired_state)
                                   if self.numeric_authority_provider is not None else None)
            admitted_spell_choice_markers = validate_native_spell_choice_authorizations(
                prior_record, definition, desired_state, candidate_authority, actor_id=updated_by_user_id)
        if committed_mode and operation_kind != "character_update_apply":
            from .character_source_authority import (
                manual_target_digest, numeric_target_owner_digest, numeric_target_values,
            )
            old_manual = list(dict(prior_record.definition.spellcasting or {}).get("manual_authorizations") or [])
            new_manual = list(dict(definition.spellcasting or {}).get("manual_authorizations") or [])
            for marker in new_manual:
                if not isinstance(marker, dict):
                    continue
                kind, target_id = marker.get("target_kind"), marker.get("target_id")
                if (marker not in old_manual or not isinstance(kind, str) or not isinstance(target_id, str)
                        or manual_target_digest(prior_record.definition, kind, target_id) is None
                        or manual_target_digest(prior_record.definition, kind, target_id)
                        != manual_target_digest(definition, kind, target_id)):
                    raise CharacterStateConflictError("A manager spell authorization cannot be copied into this update.")
            old_numeric = list(dict(prior_record.definition.source or {}).get("source_authorizations") or [])
            new_numeric = list(dict(definition.source or {}).get("source_authorizations") or [])
            old_numeric_values = numeric_target_values(prior_record.definition, prior_record.state_record.state)
            new_numeric_values = numeric_target_values(definition, desired_state)
            for marker in new_numeric:
                if not isinstance(marker, dict):
                    continue
                kind, target_id, metric = (marker.get("target_kind"), marker.get("target_id"),
                                           marker.get("metric"))
                key = (kind, target_id, metric)
                provenance = marker.get("provenance")
                if provenance in {"native_creation", "native_level_up", "native_spell_choice"}:
                    if (pending_numeric_authority is not None and provenance == "native_level_up"
                            and marker in pending_numeric_authority.markers
                            or marker in admitted_spell_choice_markers and provenance == "native_spell_choice"):
                        continue
                    if (marker not in old_numeric or key not in old_numeric_values
                            or key not in new_numeric_values
                            or old_numeric_values[key] != new_numeric_values[key]):
                        if pending_numeric_authority is not None:
                            from .character_source_authority import NativeAdvancementValidationError
                            raise NativeAdvancementValidationError(
                                "This advancement could not be validated. Review its choices.")
                        raise CharacterStateConflictError(
                            "A native source authorization cannot be copied into this update.")
                    continue
                if provenance != "manager":
                    continue
                if (marker not in old_numeric or not all(isinstance(value, str)
                                                         for value in (kind, target_id, metric))
                        or numeric_target_owner_digest(
                            prior_record.definition, prior_record.state_record.state,
                            kind, target_id, metric) is None
                        or numeric_target_owner_digest(
                            prior_record.definition, prior_record.state_record.state,
                            kind, target_id, metric)
                        != numeric_target_owner_digest(definition, desired_state, kind, target_id, metric)):
                    raise CharacterStateConflictError("A manager numeric authorization cannot be copied into this update.")
        if committed_mode and pending_numeric_authority is None and not trusted_spell_choice_authoring:
            from .character_source_authority import numeric_target_values
            old_choices = numeric_target_values(prior_record.definition, prior_record.state_record.state)
            new_choices = numeric_target_values(definition, desired_state)
            markers = list(dict(definition.source or {}).get("source_authorizations") or [])
            origin_plan = (reviewed_source_proof.native_spell_origin_delta(
                prior_record, definition, desired_state, updated_by_user_id)
                if operation_kind == "character_update_apply" and reviewed_source_proof is not None else None)
            automatic_ids = {row["spell_id"] for row in origin_plan["automatic"]} if origin_plan is not None else set()
            from .character_spell_reconstruction import checkpoint_choice_ids
            checkpoint_ids = (checkpoint_choice_ids(origin_plan["current_checkpoint"], definition)
                              if origin_plan is not None and origin_plan.get("schema_version") in {3, 4} else set())
            for key, value in new_choices.items():
                if key[0] != "spell_choice" or old_choices.get(key) == value:
                    continue
                matching = [marker for marker in markers if isinstance(marker, dict) and
                            (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
                if matching and not (len(matching) == 1 and origin_plan is not None
                        and key[1].removeprefix("spell_choice:") in automatic_ids | checkpoint_ids
                        and matching[0] in reviewed_source_proof.native_requalification_markers):
                    raise CharacterStateConflictError(
                        "A copied spell choice authorization cannot accompany a raw edit."
                    )
        from .character_equipment_activation import ActivationPrerequisiteError, require_update_activation
        from .system_policy import is_dnd_5e_system
        association = (reviewed_source_proof.feature_class_association
                       if reviewed_source_proof is not None else _feature_association_preview)
        restoration = (reviewed_source_proof.managed_resource_restoration
                       if reviewed_source_proof is not None else _resource_restoration_preview)
        if restoration is not None:
            from .character_managed_resource_restoration import PendingManagedResourceRestoration
            if (type(restoration) is not PendingManagedResourceRestoration
                    or operation_kind != "character_update_apply" or pending_numeric_authority is not None
                    or reconstruction is not None or elective is not None or association is not None
                    or trusted_spell_choice_authoring or reconcile_reimport_state):
                raise CharacterStateConflictError("Tracker restoration requires its bounded manager operation.")
            restoration.validate_binding(prior_record, definition, desired_state, updated_by_user_id,
                                         import_metadata=import_metadata)
        if association is not None:
            from .character_feature_class_association import PendingFeatureClassAssociation
            if (type(association) is not PendingFeatureClassAssociation
                    or operation_kind != "character_update_apply"
                    or pending_numeric_authority is not None or reconstruction is not None
                    or trusted_spell_choice_authoring or reconcile_reimport_state):
                raise CharacterStateConflictError("Feature association requires its bounded manager operation.")
            association.validate_binding(prior_record, definition, desired_state, updated_by_user_id,
                                         import_metadata=import_metadata)
        if operation_kind != "activation_repair" and is_dnd_5e_system(definition.system):
            try:
                require_update_activation(prior_record, definition, desired_state,
                    reconstruction=reconstruction, actor_id=updated_by_user_id,
                    native_proof=(reviewed_source_proof if reviewed_source_proof is not None
                        and reviewed_source_proof.native_result is not None else None),
                    feature_class_association=association)
            except ActivationPrerequisiteError as exc:
                if operation_kind == "character_update_apply":
                    raise
                raise CharacterStateConflictError(str(exc)) from exc
        return committed_mode

    def prepare_source_repair_item_transition(
        self, prior_record: CharacterRecord, definition: CharacterDefinition,
        desired_state: dict[str, Any], *, actor_id: int, source_read_owner=None,
        source_read_phase=None,
    ) -> tuple[CharacterDefinition, dict[str, Any]]:
        """Issue the publisher's exact item frame before Review/proof sealing.

        This prepares no write authority. Publication still independently
        rebuilds the baseline and normalization, including under reservation.
        Review refresh also reaches this helper under reservation, so both
        authority calls preserve original numeric errors. Only the phase-owning
        publisher may classify a refusal as certainly prepublication; neither
        source-read ownership nor this shared helper establishes that phase.
        """
        if type(actor_id) is not int or actor_id < 1:
            raise CharacterStateConflictError("Item source preparation needs its current actor.")
        from .committed_character_publication import (
            _exact_item_transition_baseline, _prior_numeric_authority_loader,
            _update_numeric_authority, _withhold_item_transition_aggregates,
        )
        from .character_source_reads import native_character_source_context
        with native_character_source_context(prior_record, source_read_owner=source_read_owner,
                source_read_phase=source_read_phase,
                purpose="ordinary-item-normalization") as (phase, _service, _pages, owner):
            phase_owner = owner if phase is not None else source_read_owner
            prior_authority = _prior_numeric_authority_loader(
                self, prior_record, prepublication=False, source_read_owner=phase_owner,
                source_read_phase=phase,
            )
            authority = _update_numeric_authority(
                self, prior_record, definition, desired_state,
                prepublication=False, source_read_owner=phase_owner, source_read_phase=phase,
            )
            if authority is None:
                raise CharacterStateConflictError("Item source preparation needs current source authority.")
            baseline = _exact_item_transition_baseline(
                prior_record.definition, definition, None, authority, prior_record.state_record.state,
                prior_record=prior_record, actor_id=actor_id,
                prior_authority_provider=prior_authority, source_read_owner=phase_owner,
                source_read_phase=phase,
            )
            if not baseline[0]:
                return definition, deepcopy(desired_state)
            return _withhold_item_transition_aggregates(
                prior_record.definition, definition, desired_state, prior_authority(), authority, baseline,
                source_read_phase=phase,
            )

    def source_repair_review_authority(
        self, prior_record: CharacterRecord, definition: CharacterDefinition,
        desired_state: dict[str, Any], *, actor_id: int,
        same_physical_mapping: Any | None = None,
        source_read_owner=None,
    ) -> Any:
        """Detached item authority, matching fresh publication providers."""
        if same_physical_mapping is None and source_read_owner is None:
            return (self.numeric_authority_provider(prior_record, definition, desired_state)
                    if self.numeric_authority_provider is not None else None)
        from .character_reconstruction_items import PendingSamePhysicalItemMapping
        from .character_source_reads import SourceReadOwner
        if same_physical_mapping is not None and type(same_physical_mapping) is not PendingSamePhysicalItemMapping:
            raise CharacterStateConflictError("Same-physical mapping needs its actual source producer.")
        if same_physical_mapping is not None:
            same_physical_mapping.validate_binding(prior_record, definition, desired_state, actor_id)
        provider = getattr(self, "source_read_numeric_authority_provider", None)
        if not callable(provider):
            raise CharacterStateConflictError("Same-physical source authority is unavailable.")
        owned = source_read_owner is None
        owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
            get_db(), definition.campaign_slug, definition.character_slug)
        try:
            authority = provider(prior_record, definition, desired_state, source_read_owner=owner)
            if owner._declined:
                raise CharacterStateConflictError("Same-physical authority requires a current source snapshot.")
            owner.checkpoint()
            return authority
        finally:
            if owned:
                owner.close()

    def check_source_repair_review(
        self, prior_record: CharacterRecord, definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata, desired_state: dict[str, Any], *,
        actor_id: int, replacement_relink_target: str = "",
        same_physical_mapping: Any | None = None,
        source_read_owner=None, feature_class_association=None, managed_resource_restoration=None,
    ) -> None:
        """Check an ordinary source repair without issuing or retaining write authority."""
        if same_physical_mapping is not None:
            from .character_reconstruction_items import PendingSamePhysicalItemMapping
            if type(same_physical_mapping) is not PendingSamePhysicalItemMapping:
                raise CharacterStateConflictError("Same-physical mapping needs its actual source producer.")
            same_physical_mapping.validate_binding(prior_record, definition, desired_state, actor_id)
        self._validate_update_input(prior_record, definition, import_metadata,
            expected_revision=prior_record.state_record.revision,
            operation_kind="character_update_apply")
        from .character_equipment_activation import require_update_activation
        from .system_policy import is_dnd_5e_system
        if is_dnd_5e_system(definition.system):
            require_update_activation(prior_record, definition, desired_state, actor_id=actor_id,
                                      feature_class_association=feature_class_association)
        committed_mode = self._validate_update_preconditions(
            prior_record, definition, import_metadata, desired_state,
            expected_revision=prior_record.state_record.revision,
            updated_by_user_id=actor_id, operation_kind="character_update_apply",
            audit_event_type="character_update_applied", audit_actor_user_id=actor_id,
            pending_numeric_authority=None, reviewed_source_proof=None,
            trusted_spell_choice_authoring=False, reconcile_reimport_state=False,
            reimport_source_authority=None, _replacement_preview_target=replacement_relink_target,
            _feature_association_preview=feature_class_association,
            _resource_restoration_preview=managed_resource_restoration)
        authority = (self.source_repair_review_authority(prior_record, definition, desired_state,
                         actor_id=actor_id, same_physical_mapping=same_physical_mapping,
                         source_read_owner=source_read_owner)
                     if committed_mode else None)
        if committed_mode and authority is None:
            raise CharacterStateConflictError("Character source proof is unavailable.")
        if managed_resource_restoration is not None:
            from .character_managed_resource_restoration import prepare_restoration_state
            prepared = prepare_restoration_state(prior_record, definition, desired_state,
                managed_resource_restoration, actor_id, import_metadata=import_metadata)
        elif feature_class_association is not None:
            from .character_feature_class_association import prepare_association_state
            prepared = prepare_association_state(prior_record, definition, desired_state,
                feature_class_association, actor_id, import_metadata=import_metadata)
        else:
            prepared = self.state_store.prepare_initial_state(definition, desired_state,
                source_authority=authority, previous_state=prior_record.state_record.state)
        from .character_equipment_activation import activation_frame_digest
        if (same_physical_mapping is not None
                and activation_frame_digest(prepared.validated_state) != activation_frame_digest(prior_record.state_record.state)):
            raise CharacterStateConflictError("Same-physical mapping preparation changed retained play facts.")
        if committed_mode:
            from .committed_character_publication import _pair
            from .committed_publication import CommittedSourceConflict
            try:
                _pair(definition, import_metadata)
            except CommittedSourceConflict as exc:
                raise CharacterPublicationError(str(exc)) from exc
        else:
            primary = render_character_yaml("definition.yaml", definition.to_dict()).encode("utf-8")
            secondary = render_character_yaml("import.yaml", import_metadata.to_dict()).encode("utf-8")
            if not primary or not secondary or len(primary) + len(secondary) > MAX_RECOVERY_PAYLOAD:
                raise CharacterPublicationError("Character recovery payload exceeds the durable storage limit.")

    def update(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
        operation_kind: str = "interactive_update",
        audit_event_type: str | None = None,
        audit_actor_user_id: int | None = None,
        audit_target_user_id: int | None = None,
        audit_metadata: dict[str, Any] | None = None,
        pending_numeric_authority: Any | None = None,
        reviewed_source_proof: PendingReviewedSourceProof | None = None,
        trusted_spell_choice_authoring: bool = False,
        native_choice_audit: Callable[[], dict[str, Any]] | None = None,
        explicit_removed_item_id: str | None = None,
        reconcile_reimport_state: bool = False,
        reimport_source_authority: Any | None = None,
        activation_repair_intent: tuple[Any, ...] | None = None,
    ) -> CharacterRecord:
        native_lifetime = False
        try:
            if operation_kind == "activation_repair":
                from .character_equipment_activation import validate_activation_repair_intent
                validate_activation_repair_intent(prior_record.definition, prior_record.state_record.state,
                                                 definition, desired_state,
                                                 activation_repair_intent)
            elif activation_repair_intent is not None:
                raise CharacterStateConflictError("Activation repair intent requires its bounded operation.")
            if type(reviewed_source_proof) is PendingReviewedSourceProof:
                native_lifetime = reviewed_source_proof._requires_native_custody()
                if native_lifetime:
                    reviewed_source_proof._require_native_complete_binding(prior_record, updated_by_user_id)
            committed_mode = self._validate_update_preconditions(
                prior_record, definition, import_metadata, desired_state,
                expected_revision=expected_revision, updated_by_user_id=updated_by_user_id,
                operation_kind=operation_kind, audit_event_type=audit_event_type,
                audit_actor_user_id=audit_actor_user_id,
                pending_numeric_authority=pending_numeric_authority,
                reviewed_source_proof=reviewed_source_proof,
                trusted_spell_choice_authoring=trusted_spell_choice_authoring,
                reconcile_reimport_state=reconcile_reimport_state,
                reimport_source_authority=reimport_source_authority,
                audit_metadata=audit_metadata,
            )
            if committed_mode:
                from .committed_character_publication import publish_update
                return publish_update(
                    self, prior_record, definition, import_metadata, desired_state,
                    expected_revision=expected_revision, updated_by_user_id=updated_by_user_id,
                    operation_kind=operation_kind, audit_event_type=audit_event_type,
                    audit_actor_user_id=audit_actor_user_id,
                    audit_target_user_id=audit_target_user_id, audit_metadata=audit_metadata,
                    pending_numeric_authority=pending_numeric_authority,
                    reviewed_source_proof=reviewed_source_proof,
                    trusted_spell_choice_authoring=trusted_spell_choice_authoring,
                    native_choice_audit=native_choice_audit,
                    explicit_removed_item_id=explicit_removed_item_id,
                    reconcile_reimport_state=reconcile_reimport_state,
                    reimport_source_authority=reimport_source_authority,
                    activation_repair_intent=activation_repair_intent,
                )
            key = (definition.campaign_slug, definition.character_slug)
            with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
                with self._character_lock(key):
                    operation = self._prepare_update_operation(
                        prior_record,
                        definition,
                        import_metadata,
                        desired_state,
                        expected_revision=expected_revision,
                        updated_by_user_id=updated_by_user_id,
                        operation_kind=operation_kind,
                        audit_event_type=audit_event_type,
                        audit_actor_user_id=audit_actor_user_id,
                        audit_target_user_id=audit_target_user_id,
                        audit_metadata=audit_metadata,
                        pending_numeric_authority=pending_numeric_authority,
                        trusted_spell_choice_authoring=trusted_spell_choice_authoring,
                    )
                    self._event("after_commit", operation.operation_id)
                    return self._continue_operation(operation.operation_id)
        finally:
            if native_lifetime:
                reviewed_source_proof.discard_native_admission()

    def update_equipment_activation(
        self,
        prior_record: CharacterRecord,
        build_state: Callable[[CharacterRecord], dict[str, Any]],
        *,
        expected_revision: int,
        updated_by_user_id: int | None,
        item_id: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> CharacterStateRecord:
        """Serialize state activation with structural publication and deletion.

        The callback validates against a fresh definition while the same
        character lock and runtime lease used by journaled writes are held.
        """
        from .character_equipment_activation import definition_digest
        from .character_equipment_migration import _assert_activation_only_delta
        from .character_service import validate_state
        from .committed_publication import active
        from .character_equipment_state import validate_equipment_state_values
        from .system_policy import is_xianxia_system

        # Callback-only legacy callers retain their signature. Explicit raw
        # intent is checked before either dispatch mode can normalize it.
        committed_mode = active()
        if values is not None:
            validate_equipment_state_values(values, strict_wield=(
                committed_mode or not is_xianxia_system(prior_record.definition.system)))

        if committed_mode:
            from .character_store import publication_source_write_transaction
            from .committed_character_publication import load_for_write
            from .character_equipment_state import build_reserved_equipment_state_update_result
            from .character_editor import CharacterEditValidationError
            key = (prior_record.definition.campaign_slug, prior_record.definition.character_slug)
            if (not isinstance(item_id, str) or not item_id.strip()
                    or len(item_id) > 256 or not isinstance(values, dict)):
                raise CharacterEditValidationError("Equipment intent is unavailable.")
            with publication_source_write_transaction() as connection:
                current = load_for_write(self.repository, *key)
                if (current is None or current.committed_revision is None
                        or current.committed_revision != prior_record.committed_revision):
                    raise CharacterStateConflictError("Character definition changed before the action.")
                if (current.state_record.revision != expected_revision
                        or current.state_record.state != prior_record.state_record.state):
                    raise CharacterStateConflictError("Character state changed before the action.")
                desired_state = build_reserved_equipment_state_update_result(
                    current, item_id, values, connection=connection,
                )
                validated_state = validate_state(current.definition, desired_state)
                _assert_activation_only_delta(current.state_record.state, validated_state)
                result = self.state_store.replace_state(
                    current.definition, validated_state, expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id, commit=False,
                )
                return result

        key = (prior_record.definition.campaign_slug, prior_record.definition.character_slug)
        try:
            with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
                with self._character_lock(key):
                    current = self.repository.get_combat_seed_character(*key)
                    if current is None:
                        raise CharacterStateUnavailableError("Character is unavailable for updates.")
                    if (
                        current.state_record.revision != expected_revision
                        or definition_digest(current.definition) != definition_digest(prior_record.definition)
                        or current.committed_revision != prior_record.committed_revision
                    ):
                        raise CharacterStateConflictError("Character definition or state changed before the action.")
                    desired_state = build_state(current)
                    validated_state = validate_state(current.definition, desired_state)
                    try:
                        _assert_activation_only_delta(current.state_record.state, validated_state)
                    except ValueError as exc:
                        raise CharacterStateConflictError(
                            "The Character state needs review before equipment activation can be changed."
                        ) from exc
                    return self.state_store.replace_state(
                        current.definition,
                        validated_state,
                        expected_revision=expected_revision,
                        updated_by_user_id=updated_by_user_id,
                    )
        except RuntimeStateLeaseError as exc:
            raise CharacterStateUnavailableError(str(exc)) from exc

    def update_portrait(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None,
        operation_kind: str,
        desired_asset_ref: str = "",
        desired_asset_bytes: bytes = b"",
        reviewed_source_proof: PendingReviewedSourceProof | None = None,
    ) -> CharacterRecord:
        native_lifetime = False
        try:
            if type(reviewed_source_proof) is PendingReviewedSourceProof:
                native_lifetime = reviewed_source_proof._requires_native_custody()
                if native_lifetime:
                    reviewed_source_proof._require_native_complete_binding(prior_record, updated_by_user_id)
            if operation_kind not in PORTRAIT_OPERATION_KINDS:
                raise CharacterPublicationError("Unsupported character portrait operation.")
            from .committed_publication import active
            if active():
                old_markers = [row for row in list(dict(prior_record.definition.source or {}).get(
                    "source_authorizations") or []) if isinstance(row, dict)
                    and row.get("provenance") == "page_feature_update"]
                new_markers = [row for row in list(dict(definition.source or {}).get(
                    "source_authorizations") or []) if isinstance(row, dict)
                    and row.get("provenance") == "page_feature_update"]
                if new_markers != old_markers:
                    raise CharacterStateConflictError("Portrait updates cannot change page feature witnesses.")
            self._validate_update_input(
                prior_record,
                definition,
                import_metadata,
                expected_revision=expected_revision,
                operation_kind=operation_kind,
            )
            if active():
                from .committed_character_publication import publish_update
                return publish_update(
                    self, prior_record, definition, import_metadata, desired_state,
                    expected_revision=expected_revision, updated_by_user_id=updated_by_user_id,
                    operation_kind=operation_kind, desired_asset_ref=desired_asset_ref,
                    desired_asset_bytes=desired_asset_bytes,
                    reviewed_source_proof=reviewed_source_proof,
                )
            key = (definition.campaign_slug, definition.character_slug)
            with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
                with self._character_lock(key):
                    operation = self._prepare_update_operation(
                        prior_record,
                        definition,
                        import_metadata,
                        desired_state,
                        expected_revision=expected_revision,
                        updated_by_user_id=updated_by_user_id,
                        operation_kind=operation_kind,
                        desired_asset_ref=desired_asset_ref,
                        desired_asset_bytes=desired_asset_bytes,
                    )
                    self._event("after_commit", operation.operation_id)
                    return self._continue_operation(operation.operation_id)
        finally:
            if native_lifetime:
                reviewed_source_proof.discard_native_admission()

    def recover_key(self, campaign_slug: str, character_slug: str) -> bool:
        validate_character_slug(character_slug)
        from .committed_publication import active
        if active():
            from .committed_publication import replay_mirrors
            replay_mirrors(self.campaigns_dir, campaign_slug=campaign_slug)
            return False
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._load_active_operation(campaign_slug, character_slug)
                if operation is None or operation.state == "conflict":
                    return False
                self._continue_operation(operation.operation_id)
                return True

    def recover_pending(
        self,
        *,
        limit: int = 8,
        retained_runtime_state_lease: object | None = None,
        runtime_state_lease_provider: Callable[[], object | None] | None = None,
    ) -> dict[str, int]:
        from .committed_publication import active
        if active():
            from .committed_publication import replay_mirrors
            result = replay_mirrors(self.campaigns_dir, limit=limit)
            return {"recovered": result["recovered"], "conflict": result["conflict"],
                    "pending": result["pending"]}
        if (
            retained_runtime_state_lease is not None
            and runtime_state_lease_provider is not None
        ):
            raise ValueError(
                "Supply either a retained runtime-state lease or its provider, not both."
            )
        counts = {"recovered": 0, "conflict": 0, "pending": 0}
        if runtime_state_lease_provider is not None:
            if not _has_pending_character_publication_recovery():
                return counts
            retained_runtime_state_lease = runtime_state_lease_provider()
        with recovery_runtime_state_lease_context(
            self.database_path,
            retained_lease=retained_runtime_state_lease,
            timeout_seconds=30.0,
        ):
            rows = get_db().execute(
                """
                SELECT operation_id, campaign_slug, character_slug
                FROM character_reconciliation_operations
                WHERE state IN ('prepared', 'repository_pending')
                ORDER BY updated_at, operation_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            for row in rows:
                key = (str(row["campaign_slug"]), str(row["character_slug"]))
                try:
                    with self._character_lock(key):
                        operation = self._load_operation(str(row["operation_id"]))
                        if operation is None:
                            continue
                        if operation.state == "conflict":
                            counts["conflict"] += 1
                            continue
                        self._continue_operation(operation.operation_id)
                        counts["recovered"] += 1
                except CharacterPublicationConflict:
                    counts["conflict"] += 1
                except (OSError, RuntimeError, ValueError):
                    counts["pending"] += 1
        return counts

    def _validate_create_input(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        operation_kind: str,
    ) -> None:
        if operation_kind not in CREATE_OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character publication operation.")
        if (definition.source.get("native_reconstruction") is not None
                or any(isinstance(row, dict) and row.get("provenance") == "native_reconstruction"
                       for row in definition.source.get("source_authorizations", []))):
            raise CharacterPublicationError("An existing-target reconstruction origin cannot be imported into a new Character.")
        self._validate_identity(definition, import_metadata)

    @staticmethod
    def _validate_identity(
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
    ) -> None:
        validate_character_slug(definition.character_slug)
        if len(definition.character_slug.encode("utf-8")) > 255:
            raise CharacterPathSafetyError("Character slugs exceed the durable storage limit.")
        campaign_slug = str(definition.campaign_slug)
        if (
            not campaign_slug
            or campaign_slug != campaign_slug.strip().lower()
            or len(campaign_slug.encode("utf-8")) > 128
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in campaign_slug)
        ):
            raise CharacterPublicationError("Campaign slug is invalid for durable character publication.")
        if (
            import_metadata.campaign_slug != campaign_slug
            or import_metadata.character_slug != definition.character_slug
        ):
            raise CharacterPublicationError("Character definition and import metadata identities differ.")

    def _validate_update_input(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        *,
        expected_revision: int,
        operation_kind: str,
    ) -> None:
        self._validate_identity(definition, import_metadata)
        if operation_kind not in UPDATE_OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character update operation.")
        if (
            prior_record.definition.campaign_slug != definition.campaign_slug
            or prior_record.definition.character_slug != definition.character_slug
            or prior_record.import_metadata.campaign_slug != definition.campaign_slug
            or prior_record.import_metadata.character_slug != definition.character_slug
            or prior_record.state_record.campaign_slug != definition.campaign_slug
            or prior_record.state_record.character_slug != definition.character_slug
        ):
            raise CharacterPublicationError("Character update identities differ.")
        if (
            isinstance(expected_revision, bool)
            or int(expected_revision) < 1
            or prior_record.state_record.revision != int(expected_revision)
        ):
            raise CharacterStateConflictError(
                f"State update conflict for {definition.campaign_slug}/{definition.character_slug}"
            )

    def _prepare_operation(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        initial_state: dict[str, Any],
        *,
        operation_kind: str,
        updated_by_user_id: int | None,
    ) -> CharacterReconciliationOperation:
        definition_yaml = render_character_yaml(
            "definition.yaml",
            definition.to_dict(),
        ).encode("utf-8")
        import_yaml = render_character_yaml(
            "import.yaml",
            import_metadata.to_dict(),
        ).encode("utf-8")
        if (
            not definition_yaml
            or not import_yaml
            or len(definition_yaml) + len(import_yaml) > MAX_RECOVERY_PAYLOAD
        ):
            raise CharacterPublicationError("Character recovery payload exceeds the durable storage limit.")
        prepared_state = self.state_store.prepare_initial_state(definition, initial_state)
        operation_id = secrets.token_hex(16)
        now = isoformat(utcnow())
        operation = CharacterReconciliationOperation(
            operation_id=operation_id,
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            operation_kind=operation_kind,
            previous_definition_digest="",
            desired_definition_digest=_digest_bytes(definition_yaml),
            previous_import_digest="",
            desired_import_digest=_digest_bytes(import_yaml),
            previous_state_digest="",
            desired_state_digest=_digest_bytes(prepared_state.state_json.encode("utf-8")),
            previous_state_revision=0,
            desired_state_revision=1,
            desired_definition_yaml=definition_yaml,
            desired_import_yaml=import_yaml,
            previous_asset_ref="",
            desired_asset_ref="",
            previous_asset_digest="",
            desired_asset_digest="",
            desired_asset_bytes=b"",
            audit_event_type=None,
            audit_actor_user_id=None,
            audit_target_user_id=None,
            audit_metadata_json=None,
            state="prepared",
            error_code="",
        )
        definition_path, import_path = self._paths(operation.campaign_slug, operation.character_slug)
        connection = get_db()
        self._event("before_prepare", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_state = connection.execute(
                """
                SELECT 1 FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            existing_operation = connection.execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            if (
                existing_state is not None
                or existing_operation is not None
                or _has_active_character_deletion(
                    connection,
                    operation.campaign_slug,
                    operation.character_slug,
                )
                or _path_exists(definition_path)
                or _path_exists(import_path)
            ):
                raise CharacterPublicationExistsError(
                    f"A character with slug '{operation.character_slug}' already exists in this campaign."
                )
            self.state_store.insert_initial_state_in_transaction(
                connection,
                definition,
                prepared_state,
                updated_at=now,
                updated_by_user_id=updated_by_user_id,
            )
            connection.execute(
                """
                INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    previous_asset_ref, desired_asset_ref,
                    previous_asset_digest, desired_asset_digest,
                    desired_asset_bytes,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', ?, '', ?, '', ?, 0, 1, ?, ?,
                    '', '', '', '', X'', 'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.operation_kind,
                    operation.desired_definition_digest,
                    operation.desired_import_digest,
                    operation.desired_state_digest,
                    sqlite3.Binary(operation.desired_definition_yaml),
                    sqlite3.Binary(operation.desired_import_yaml),
                    now,
                    now,
                ),
            )
            self._event("before_commit", operation.operation_id)
            connection.commit()
        except CharacterPublicationExistsError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise CharacterPublicationConflict(
                "This character has an active reconciliation operation and requires repair."
            ) from exc
        except BaseException:
            connection.rollback()
            raise
        return operation

    def _prepare_portrait_asset_evidence(
        self,
        prior_record: CharacterRecord,
        *,
        operation_kind: str,
        desired_asset_ref: str,
        desired_asset_bytes: bytes,
    ) -> tuple[str, str, str, str]:
        if operation_kind not in PORTRAIT_OPERATION_KINDS:
            if desired_asset_ref or desired_asset_bytes:
                raise CharacterPublicationError(
                    "Non-portrait updates cannot carry portrait recovery payloads."
                )
            return "", "", "", ""

        previous_asset_ref = str(
            (prior_record.definition.profile or {}).get("portrait_asset_ref") or ""
        ).strip()
        if operation_kind == "portrait_upsert":
            clean_desired_ref = str(desired_asset_ref or "").strip()
            if (
                not clean_desired_ref
                or not desired_asset_bytes
                or len(desired_asset_bytes) > CHARACTER_PORTRAIT_MAX_BYTES
            ):
                raise CharacterPublicationError(
                    "Character portrait recovery payload is invalid."
                )
            self._asset_path(
                prior_record.definition.campaign_slug,
                prior_record.definition.character_slug,
                clean_desired_ref,
            )
        else:
            if desired_asset_ref or desired_asset_bytes or not previous_asset_ref:
                raise CharacterPublicationError(
                    "Character portrait removal evidence is invalid."
                )
            clean_desired_ref = ""

        previous_asset_digest = ""
        if previous_asset_ref:
            previous_path = self._asset_path(
                prior_record.definition.campaign_slug,
                prior_record.definition.character_slug,
                previous_asset_ref,
            )
            previous_asset_digest = _digest_regular_file(previous_path) or ""
            if not previous_asset_digest:
                raise CharacterStateConflictError(
                    "Character portrait changed after it was loaded."
                )

        return (
            previous_asset_ref,
            clean_desired_ref,
            previous_asset_digest,
            _digest_bytes(desired_asset_bytes) if desired_asset_bytes else "",
        )

    def _validate_asset_authority_for_prepare(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if operation.operation_kind not in PORTRAIT_OPERATION_KINDS:
            return
        try:
            if operation.previous_asset_ref:
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                if _digest_regular_file(previous_path) != operation.previous_asset_digest:
                    raise CharacterStateConflictError(
                        "Character portrait changed after it was loaded."
                    )
            if (
                operation.operation_kind == "portrait_upsert"
                and operation.desired_asset_ref != operation.previous_asset_ref
            ):
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                if _digest_regular_file(desired_path) is not None:
                    raise CharacterStateConflictError(
                        "Character portrait target changed after it was loaded."
                    )
        except ValueError as exc:
            raise CharacterStateConflictError(
                "Character portrait changed after it was loaded."
            ) from exc

    def _prepare_update_operation(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None,
        operation_kind: str,
        desired_asset_ref: str = "",
        desired_asset_bytes: bytes = b"",
        audit_event_type: str | None = None,
        audit_actor_user_id: int | None = None,
        audit_target_user_id: int | None = None,
        audit_metadata: dict[str, Any] | None = None,
        pending_numeric_authority: Any | None = None,
        trusted_spell_choice_authoring: bool = False,
    ) -> CharacterReconciliationOperation:
        definition_yaml = render_character_yaml(
            "definition.yaml",
            definition.to_dict(),
        ).encode("utf-8")
        import_yaml = render_character_yaml(
            "import.yaml",
            import_metadata.to_dict(),
        ).encode("utf-8")
        desired_asset_bytes = bytes(desired_asset_bytes)
        if (
            not definition_yaml
            or not import_yaml
            or len(definition_yaml) + len(import_yaml) + len(desired_asset_bytes)
            > MAX_RECOVERY_PAYLOAD
        ):
            raise CharacterPublicationError(
                "Character recovery payload exceeds the durable storage limit."
            )
        from .committed_publication import active
        if active():
            raise CharacterStateConflictError("Character publication mode changed before the legacy write.")
        if pending_numeric_authority is not None:
            raise CharacterStateConflictError("Pending authority is unavailable for this update.")
        numeric_authority = None
        prepared_state = self.state_store.prepare_initial_state(
            definition, desired_state,
            source_authority=numeric_authority,
            previous_state=prior_record.state_record.state,
        )
        definition_path, import_path = self._paths(
            definition.campaign_slug,
            definition.character_slug,
        )
        previous_definition_yaml = self._read_prior_file(
            definition_path,
            prior_record,
            label="definition",
        )
        previous_import_yaml = self._read_prior_file(
            import_path,
            prior_record,
            label="import",
        )
        connection = get_db()
        previous_state_row = connection.execute(
            """
            SELECT revision, state_json
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (definition.campaign_slug, definition.character_slug),
        ).fetchone()
        previous_state_json = self._validate_prior_state_row(
            previous_state_row,
            prior_record,
            expected_revision=expected_revision,
        )
        state_changed = (
            operation_kind not in OPTIONAL_STATE_UPDATE_OPERATION_KINDS
            or desired_state != prior_record.state_record.state
        )
        desired_state_json = prepared_state.state_json if state_changed else previous_state_json
        if (
            operation_kind in PORTRAIT_OPERATION_KINDS
            and desired_state_json == previous_state_json
        ):
            desired_state_json = json.dumps(
                prepared_state.validated_state,
                sort_keys=True,
                ensure_ascii=False,
            )
        desired_state_revision = int(expected_revision) + (1 if state_changed else 0)
        (
            clean_audit_event_type,
            clean_audit_actor_user_id,
            clean_audit_target_user_id,
            audit_metadata_json,
        ) = self._prepare_update_audit(
            operation_kind=operation_kind,
            audit_event_type=audit_event_type,
            audit_actor_user_id=audit_actor_user_id,
            audit_target_user_id=audit_target_user_id,
            audit_metadata=audit_metadata,
        )
        (
            previous_asset_ref,
            clean_desired_asset_ref,
            previous_asset_digest,
            desired_asset_digest,
        ) = self._prepare_portrait_asset_evidence(
            prior_record,
            operation_kind=operation_kind,
            desired_asset_ref=desired_asset_ref,
            desired_asset_bytes=desired_asset_bytes,
        )
        operation_id = secrets.token_hex(16)
        now = isoformat(utcnow())
        operation = CharacterReconciliationOperation(
            operation_id=operation_id,
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            operation_kind=operation_kind,
            previous_definition_digest=_digest_bytes(previous_definition_yaml),
            desired_definition_digest=_digest_bytes(definition_yaml),
            previous_import_digest=_digest_bytes(previous_import_yaml),
            desired_import_digest=_digest_bytes(import_yaml),
            previous_state_digest=_digest_bytes(previous_state_json.encode("utf-8")),
            desired_state_digest=_digest_bytes(desired_state_json.encode("utf-8")),
            previous_state_revision=int(expected_revision),
            desired_state_revision=desired_state_revision,
            desired_definition_yaml=definition_yaml,
            desired_import_yaml=import_yaml,
            previous_asset_ref=previous_asset_ref,
            desired_asset_ref=clean_desired_asset_ref,
            previous_asset_digest=previous_asset_digest,
            desired_asset_digest=desired_asset_digest,
            desired_asset_bytes=desired_asset_bytes,
            audit_event_type=clean_audit_event_type,
            audit_actor_user_id=clean_audit_actor_user_id,
            audit_target_user_id=clean_audit_target_user_id,
            audit_metadata_json=audit_metadata_json,
            state="prepared",
            error_code="",
        )
        self._event("before_prepare", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            active_operation = connection.execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            current_state_row = connection.execute(
                """
                SELECT revision, state_json
                FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            if (
                active_operation is not None
                or _has_active_character_deletion(
                    connection,
                    operation.campaign_slug,
                    operation.character_slug,
                )
                or _classify_update_file(
                    definition_path,
                    operation.previous_definition_digest,
                    operation.desired_definition_digest,
                )
                not in {"previous", "desired"}
                or _digest_path(definition_path) != operation.previous_definition_digest
                or _classify_update_file(
                    import_path,
                    operation.previous_import_digest,
                    operation.desired_import_digest,
                )
                not in {"previous", "desired"}
                or _digest_path(import_path) != operation.previous_import_digest
                or current_state_row is None
                or int(current_state_row["revision"]) != operation.previous_state_revision
                or _digest_bytes(str(current_state_row["state_json"]).encode("utf-8"))
                != operation.previous_state_digest
            ):
                raise CharacterStateConflictError(
                    f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
                )
            self._validate_asset_authority_for_prepare(operation)
            if state_changed:
                cursor = connection.execute(
                    """
                    UPDATE character_state
                    SET revision = ?, state_json = ?, updated_at = ?, updated_by_user_id = ?
                    WHERE campaign_slug = ? AND character_slug = ?
                      AND revision = ? AND state_json = ?
                    """,
                    (
                        operation.desired_state_revision,
                        desired_state_json,
                        now,
                        updated_by_user_id,
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.previous_state_revision,
                        previous_state_json,
                    ),
                )
                if cursor.rowcount != 1:
                    raise CharacterStateConflictError(
                        f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
                    )
            connection.execute(
                """
                INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    previous_asset_ref, desired_asset_ref,
                    previous_asset_digest, desired_asset_digest,
                    desired_asset_bytes,
                    audit_event_type, audit_actor_user_id,
                    audit_target_user_id, audit_metadata_json,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.operation_kind,
                    operation.previous_definition_digest,
                    operation.desired_definition_digest,
                    operation.previous_import_digest,
                    operation.desired_import_digest,
                    operation.previous_state_digest,
                    operation.desired_state_digest,
                    operation.previous_state_revision,
                    operation.desired_state_revision,
                    sqlite3.Binary(operation.desired_definition_yaml),
                    sqlite3.Binary(operation.desired_import_yaml),
                    operation.previous_asset_ref,
                    operation.desired_asset_ref,
                    operation.previous_asset_digest,
                    operation.desired_asset_digest,
                    sqlite3.Binary(operation.desired_asset_bytes),
                    operation.audit_event_type,
                    operation.audit_actor_user_id,
                    operation.audit_target_user_id,
                    operation.audit_metadata_json,
                    now,
                    now,
                ),
            )
            self._event("before_commit", operation.operation_id)
            connection.commit()
        except CharacterStateConflictError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise CharacterStateConflictError(
                f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
            ) from exc
        except BaseException:
            connection.rollback()
            raise
        return operation

    def _prepare_update_audit(
        self,
        *,
        operation_kind: str,
        audit_event_type: str | None,
        audit_actor_user_id: int | None,
        audit_target_user_id: int | None,
        audit_metadata: dict[str, Any] | None,
    ) -> tuple[str | None, int | None, int | None, str | None]:
        supplied = any(
            value is not None
            for value in (
                audit_event_type,
                audit_actor_user_id,
                audit_target_user_id,
                audit_metadata,
            )
        )
        if operation_kind == "interactive_update" and audit_event_type == "character_reference_notes_updated":
            from .committed_publication import active
            from .character_reference_notes import validate_audit_metadata
            if not active() or self.auth_store is None or audit_target_user_id is not None:
                raise CharacterPublicationError("Reference-note audits require committed Character maintenance.")
            validate_audit_metadata(audit_metadata, audit_actor_user_id)
            clean = self.auth_store.sanitize_audit_metadata(audit_metadata)
            encoded = json.dumps(clean, sort_keys=True, allow_nan=False)
            if clean != audit_metadata or len(encoded.encode("utf-8")) > 60000:
                raise CharacterPublicationError("The complete reference-note audit cannot be stored losslessly.")
            return audit_event_type, audit_actor_user_id, None, encoded
        if (operation_kind == "interactive_update" and audit_event_type == "character_native_edited"
                and isinstance(audit_metadata, dict) and "external_proficiency_confirmation" in audit_metadata
                and self.auth_store is not None and audit_target_user_id is None):
            from .character_external_proficiencies import validate_metadata
            validate_metadata(audit_metadata, audit_actor_user_id)
            clean = self.auth_store.sanitize_audit_metadata(audit_metadata)
            encoded = json.dumps(clean, sort_keys=True, allow_nan=False)
            if clean != audit_metadata or len(encoded.encode("utf-8")) > 60000:
                raise CharacterPublicationError("The complete acquisition audit cannot be stored losslessly.")
            return audit_event_type, audit_actor_user_id, None, encoded
        if (operation_kind == "interactive_update"
                and audit_event_type == "character_native_edited"
                and audit_metadata == {"source": "native_edit_confirmed"}
                and self.auth_store is not None
                and type(audit_actor_user_id) is int and audit_actor_user_id > 0
                and audit_target_user_id is None):
            return audit_event_type, audit_actor_user_id, None, json.dumps(audit_metadata, sort_keys=True)
        if operation_kind != "character_update_apply":
            if supplied:
                raise CharacterPublicationError(
                    "Only character update apply may carry publication audit metadata."
                )
            return None, None, None, None
        if (
            self.auth_store is None
            or audit_event_type != "character_update_applied"
            or isinstance(audit_actor_user_id, bool)
            or not isinstance(audit_actor_user_id, int)
            or audit_actor_user_id < 1
            or audit_metadata is None
        ):
            raise CharacterPublicationError(
                "Character update apply audit metadata is invalid."
            )
        sanitized = self.auth_store.sanitize_audit_metadata(dict(audit_metadata))
        metadata_json = json.dumps(sanitized, sort_keys=True)
        if not metadata_json or len(metadata_json.encode("utf-8")) > 65536:
            raise CharacterPublicationError(
                "Character update apply audit metadata is too large."
            )
        return (
            audit_event_type,
            audit_actor_user_id,
            audit_target_user_id,
            metadata_json,
        )

    def _continue_operation(self, operation_id: str) -> CharacterRecord:
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterPublicationError("Character reconciliation operation is unavailable.")
        if operation.state == "conflict":
            raise CharacterPublicationConflict(
                "This character has a reconciliation conflict and requires repair."
            )
        if operation.state == "prepared":
            payload_error = self._recovery_payload_error(operation)
            if payload_error is not None:
                self._raise_conflict(operation.operation_id, payload_error)
        definition_path, import_path = self._paths(
            operation.campaign_slug,
            operation.character_slug,
        )
        if operation.state == "prepared":
            if operation.operation_kind in PORTRAIT_OPERATION_KINDS:
                self._validate_prepublication_asset_authority(
                    operation,
                    definition_path=definition_path,
                    import_path=import_path,
                )
            if operation.operation_kind == "portrait_upsert":
                self._publish_portrait_asset(operation)
            self._publish_file(
                operation,
                definition_path,
                operation.desired_definition_yaml,
                operation.desired_definition_digest,
                label="definition",
            )
            self._publish_file(
                operation,
                import_path,
                operation.desired_import_yaml,
                operation.desired_import_digest,
                label="import",
            )
            self._validate_state(operation)
            if operation.operation_kind in PORTRAIT_OPERATION_KINDS:
                self._unlink_superseded_portrait_asset(operation)
            operation = self._transition_repository_pending(operation)
        return self._refresh_and_cleanup(operation)

    @staticmethod
    def _recovery_payload_error(
        operation: CharacterReconciliationOperation,
    ) -> str | None:
        if (
            not operation.desired_definition_yaml
            or not operation.desired_import_yaml
            or len(operation.desired_definition_yaml)
            + len(operation.desired_import_yaml)
            + len(operation.desired_asset_bytes)
            > MAX_RECOVERY_PAYLOAD
        ):
            return "recovery_payload_invalid"
        if (
            _digest_bytes(operation.desired_definition_yaml)
            != operation.desired_definition_digest
        ):
            return "definition_payload_mismatch"
        if (
            _digest_bytes(operation.desired_import_yaml)
            != operation.desired_import_digest
        ):
            return "import_payload_mismatch"
        if operation.operation_kind == "portrait_upsert":
            if (
                not operation.desired_asset_ref
                or not operation.desired_asset_bytes
                or len(operation.desired_asset_bytes) > CHARACTER_PORTRAIT_MAX_BYTES
                or _digest_bytes(operation.desired_asset_bytes)
                != operation.desired_asset_digest
            ):
                return "asset_payload_mismatch"
        elif operation.operation_kind == "portrait_remove":
            if (
                not operation.previous_asset_ref
                or not operation.previous_asset_digest
                or operation.desired_asset_ref
                or operation.desired_asset_digest
                or operation.desired_asset_bytes
            ):
                return "asset_payload_mismatch"
        elif any(
            (
                operation.previous_asset_ref,
                operation.desired_asset_ref,
                operation.previous_asset_digest,
                operation.desired_asset_digest,
                operation.desired_asset_bytes,
            )
        ):
            return "unexpected_asset_payload"
        return None

    def _validate_prepublication_asset_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        definition_path: Path,
        import_path: Path,
    ) -> None:
        yaml_is_desired = (
            _digest_path(definition_path) == operation.desired_definition_digest
            and _digest_path(import_path) == operation.desired_import_digest
        )
        try:
            if operation.previous_asset_ref:
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                previous_digest = _digest_regular_file(previous_path)
                if previous_digest != operation.previous_asset_digest and not (
                    previous_digest is None
                    and yaml_is_desired
                    and operation.previous_asset_ref != operation.desired_asset_ref
                ):
                    self._raise_conflict(
                        operation.operation_id,
                        "previous_asset_digest_conflict",
                    )
            if operation.operation_kind == "portrait_upsert":
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                desired_digest = _digest_regular_file(desired_path)
                allowed = {operation.desired_asset_digest}
                if operation.desired_asset_ref == operation.previous_asset_ref:
                    allowed.add(operation.previous_asset_digest)
                else:
                    allowed.add(None)
                if desired_digest not in allowed:
                    self._raise_conflict(
                        operation.operation_id,
                        "desired_asset_digest_conflict",
                    )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")

    def _publish_portrait_asset(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        try:
            desired_path = self._asset_path(
                operation.campaign_slug,
                operation.character_slug,
                operation.desired_asset_ref,
            )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")
        try:
            current_digest = _digest_regular_file(desired_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "desired_asset_digest_conflict")
        if current_digest == operation.desired_asset_digest:
            return
        expected_previous = (
            operation.previous_asset_digest
            if operation.desired_asset_ref == operation.previous_asset_ref
            else None
        )
        if current_digest != expected_previous:
            self._raise_conflict(operation.operation_id, "desired_asset_digest_conflict")
        self._event("before_asset_publish", operation.operation_id)
        desired_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(desired_path, operation.desired_asset_bytes)
        self._event("after_asset_publish", operation.operation_id)
        try:
            published_digest = _digest_regular_file(desired_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_publish_mismatch")
        if published_digest != operation.desired_asset_digest:
            self._raise_conflict(operation.operation_id, "asset_publish_mismatch")

    def _unlink_superseded_portrait_asset(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if (
            not operation.previous_asset_ref
            or operation.previous_asset_ref == operation.desired_asset_ref
        ):
            return
        try:
            _, previous_path = resolve_character_portrait_asset_path(
                load_campaign_character_config(
                    self.campaigns_dir,
                    operation.campaign_slug,
                ).campaign_dir,
                operation.character_slug,
                operation.previous_asset_ref,
            )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")
        try:
            current_digest = _digest_regular_file(previous_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "previous_asset_digest_conflict")
        if current_digest is None:
            durable_sync_directory(previous_path.parent)
            return
        if current_digest != operation.previous_asset_digest:
            self._raise_conflict(operation.operation_id, "previous_asset_digest_conflict")
        self._event("before_asset_unlink", operation.operation_id)
        durable_unlink_file(previous_path)
        self._event("after_asset_unlink", operation.operation_id)
        try:
            remaining_digest = _digest_regular_file(previous_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_unlink_mismatch")
        if remaining_digest is not None:
            self._raise_conflict(operation.operation_id, "asset_unlink_mismatch")

    def _publish_file(
        self,
        operation: CharacterReconciliationOperation,
        path: Path,
        payload: bytes,
        desired_digest: str,
        *,
        label: str,
    ) -> None:
        previous_digest = (
            operation.previous_definition_digest
            if label == "definition"
            else operation.previous_import_digest
        )
        is_create = operation.previous_state_revision == 0 and previous_digest == ""
        disposition = _classify_publication_file(
            path,
            previous_digest=previous_digest,
            desired_digest=desired_digest,
            is_create=is_create,
        )
        if disposition == "desired":
            return
        if disposition == "conflict":
            self._raise_conflict(operation.operation_id, f"{label}_digest_conflict")
        self._event(f"before_{label}_publish", operation.operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, payload)
        self._event(f"after_{label}_publish", operation.operation_id)
        if (
            _classify_publication_file(
                path,
                previous_digest=previous_digest,
                desired_digest=desired_digest,
                is_create=is_create,
            )
            != "desired"
        ):
            self._raise_conflict(operation.operation_id, f"{label}_publish_mismatch")

    def _transition_repository_pending(
        self,
        operation: CharacterReconciliationOperation,
    ) -> CharacterReconciliationOperation:
        connection = get_db()
        self._event("before_repository_pending", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if current is None or not self._same_owner(current, operation):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            if current.state == "repository_pending":
                connection.commit()
                return current
            if current.state != "prepared":
                raise CharacterPublicationConflict("Character reconciliation state changed.")
            self._validate_final_authority(operation, connection=connection)
            now = isoformat(utcnow())
            cursor = connection.execute(
                """
                UPDATE character_reconciliation_operations
                SET state = 'repository_pending', error_code = '', updated_at = ?
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'prepared'
                """,
                (
                    now,
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterPublicationConflict("Character reconciliation state changed.")
            if operation.audit_event_type is not None:
                if self.auth_store is None:
                    raise CharacterPublicationError(
                        "Character publication audit storage is unavailable."
                    )
                self.auth_store.insert_audit_event(
                    event_type=operation.audit_event_type,
                    actor_user_id=operation.audit_actor_user_id,
                    target_user_id=operation.audit_target_user_id,
                    campaign_slug=operation.campaign_slug,
                    character_slug=operation.character_slug,
                    metadata=json.loads(operation.audit_metadata_json or "{}"),
                )
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_repository_pending", operation.operation_id)
        refreshed = self._load_operation(operation.operation_id)
        if refreshed is None:
            raise CharacterPublicationError("Character reconciliation operation disappeared.")
        return refreshed

    def _refresh_and_cleanup(
        self,
        operation: CharacterReconciliationOperation,
    ) -> CharacterRecord:
        if operation.state != "repository_pending":
            raise CharacterPublicationError("Character publication has not reached its commit point.")
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            self._validate_final_authority(operation, connection=connection)
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self.repository.invalidate_character(operation.campaign_slug, operation.character_slug)
        self._event("before_refresh", operation.operation_id)
        record = self.repository.load_character_for_reconciliation(
            operation.campaign_slug,
            operation.character_slug,
        )
        if record is None:
            raise CharacterPublicationError("Finalized character files were not readable.")
        self._event("after_refresh", operation.operation_id)

        self._event("before_cleanup", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            self._validate_final_authority(operation, connection=connection)
            cursor = connection.execute(
                """
                DELETE FROM character_reconciliation_operations
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'repository_pending'
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterPublicationConflict("Character reconciliation cleanup changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_cleanup", operation.operation_id)
        self._prune_finalized_portrait_asset_directories(operation)
        return record

    def _prune_finalized_portrait_asset_directories(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if (
            operation.operation_kind not in PORTRAIT_OPERATION_KINDS
            or not operation.previous_asset_ref
            or operation.previous_asset_ref == operation.desired_asset_ref
        ):
            return
        try:
            assets_root, previous_path = resolve_character_portrait_asset_path(
                load_campaign_character_config(
                    self.campaigns_dir,
                    operation.campaign_slug,
                ).campaign_dir,
                operation.character_slug,
                operation.previous_asset_ref,
            )
        except (OSError, ValueError):
            return
        _prune_empty_asset_directories(previous_path.parent, stop_dir=assets_root)

    def _validate_final_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug,
            operation.character_slug,
        )
        if _digest_path(definition_path) != operation.desired_definition_digest:
            if connection is not None:
                raise _AuthorityConflict("definition_digest_conflict")
            self._raise_conflict(operation.operation_id, "definition_digest_conflict")
        if _digest_path(import_path) != operation.desired_import_digest:
            if connection is not None:
                raise _AuthorityConflict("import_digest_conflict")
            self._raise_conflict(operation.operation_id, "import_digest_conflict")
        self._validate_state(operation, connection=connection)
        self._validate_final_asset_authority(operation, connection=connection)

    def _validate_final_asset_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        if operation.operation_kind not in PORTRAIT_OPERATION_KINDS:
            return

        def conflict(error_code: str) -> None:
            if connection is not None:
                raise _AuthorityConflict(error_code)
            self._raise_conflict(operation.operation_id, error_code)

        try:
            if operation.operation_kind == "portrait_upsert":
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                if _digest_regular_file(desired_path) != operation.desired_asset_digest:
                    conflict("desired_asset_digest_conflict")
            if (
                operation.previous_asset_ref
                and operation.previous_asset_ref != operation.desired_asset_ref
            ):
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                if _digest_regular_file(previous_path) is not None:
                    conflict("previous_asset_cleanup_conflict")
        except ValueError:
            conflict("asset_ref_invalid")

    def _validate_state(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        db = connection or get_db()
        row = db.execute(
            """
            SELECT revision, state_json
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        if (
            row is None
            or int(row["revision"]) != operation.desired_state_revision
            or _digest_bytes(str(row["state_json"]).encode("utf-8"))
            != operation.desired_state_digest
        ):
            if connection is not None:
                raise _AuthorityConflict("state_digest_conflict")
            self._raise_conflict(operation.operation_id, "state_digest_conflict")

    def _raise_conflict(self, operation_id: str, error_code: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE character_reconciliation_operations
                SET state = 'conflict', error_code = ?, updated_at = ?
                WHERE operation_id = ?
                  AND state IN ('prepared', 'repository_pending')
                """,
                (error_code, isoformat(utcnow()), operation_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        raise CharacterPublicationConflict(
            "This character has a reconciliation conflict and requires repair."
        )

    def _load_active_operation(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterReconciliationOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return _map_operation(row)

    def _load_operation(
        self,
        operation_id: str,
        *,
        connection: Any | None = None,
    ) -> CharacterReconciliationOperation | None:
        row = (connection or get_db()).execute(
            "SELECT * FROM character_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return _map_operation(row)

    def _paths(self, campaign_slug: str, character_slug: str) -> tuple[Path, Path]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        return (
            resolve_character_path(config.characters_dir, character_slug, "definition.yaml"),
            resolve_character_path(config.characters_dir, character_slug, "import.yaml"),
        )

    def _asset_path(
        self,
        campaign_slug: str,
        character_slug: str,
        asset_ref: str,
    ) -> Path:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        _, asset_path = resolve_character_portrait_asset_path(
            config.campaign_dir,
            character_slug,
            asset_ref,
        )
        return asset_path

    @staticmethod
    def _read_prior_file(
        path: Path,
        prior_record: CharacterRecord,
        *,
        label: str,
    ) -> bytes:
        try:
            payload_bytes = path.read_bytes()
            payload = yaml.safe_load(payload_bytes.decode("utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError("Character YAML must be a mapping.")
            if label == "definition":
                payload.setdefault("system", prior_record.definition.system)
                normalized = CharacterDefinition.from_dict(payload).to_dict()
                expected = prior_record.definition.to_dict()
            else:
                normalized = CharacterImportMetadata.from_dict(payload).to_dict()
                expected = prior_record.import_metadata.to_dict()
            if normalized != expected:
                raise ValueError("Character YAML no longer matches the loaded record.")
            return payload_bytes
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            raise CharacterStateConflictError(
                f"Character {label} changed after it was loaded."
            ) from exc

    @staticmethod
    def _validate_prior_state_row(
        row: sqlite3.Row | None,
        prior_record: CharacterRecord,
        *,
        expected_revision: int,
    ) -> str:
        if row is None:
            raise CharacterStateConflictError("Character state disappeared after it was loaded.")
        state_json = str(row["state_json"])
        try:
            decoded_state = json.loads(state_json)
        except (TypeError, ValueError) as exc:
            raise CharacterStateConflictError("Character state is unreadable.") from exc
        if (
            int(row["revision"]) != int(expected_revision)
            or prior_record.state_record.revision != int(expected_revision)
            or decoded_state != prior_record.state_record.state
        ):
            raise CharacterStateConflictError(
                f"State update conflict for {prior_record.definition.campaign_slug}/"
                f"{prior_record.definition.character_slug}"
            )
        return state_json

    @staticmethod
    def _same_owner(
        current: CharacterReconciliationOperation,
        expected: CharacterReconciliationOperation,
    ) -> bool:
        return (
            current.operation_id == expected.operation_id
            and current.campaign_slug == expected.campaign_slug
            and current.character_slug == expected.character_slug
            and current.operation_kind == expected.operation_kind
            and current.previous_definition_digest
            == expected.previous_definition_digest
            and current.desired_definition_digest == expected.desired_definition_digest
            and current.previous_import_digest == expected.previous_import_digest
            and current.desired_import_digest == expected.desired_import_digest
            and current.previous_state_digest == expected.previous_state_digest
            and current.desired_state_digest == expected.desired_state_digest
            and current.previous_state_revision == expected.previous_state_revision
            and current.desired_state_revision == expected.desired_state_revision
            and current.previous_asset_ref == expected.previous_asset_ref
            and current.desired_asset_ref == expected.desired_asset_ref
            and current.previous_asset_digest == expected.previous_asset_digest
            and current.desired_asset_digest == expected.desired_asset_digest
            and current.audit_event_type == expected.audit_event_type
            and current.audit_actor_user_id == expected.audit_actor_user_id
            and current.audit_target_user_id == expected.audit_target_user_id
            and current.audit_metadata_json == expected.audit_metadata_json
        )

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)

    def _character_lock(self, key: tuple[str, str]) -> RLock:
        return _character_process_lock(key)


class CharacterDeletionCoordinator:
    """Commit a character deletion in SQLite, then reconcile files forward."""

    @staticmethod
    def _reject_activated_legacy_recovery() -> None:
        from .committed_publication import active
        if active():
            raise CharacterDeletionConflict(
                "Legacy Character deletion journal requires manager repair."
            )

    def __init__(
        self,
        *,
        campaigns_dir: Path,
        database_path: Path,
        state_store: CharacterStateStore,
        repository: CharacterRepository,
        auth_store: Any,
        hooks: CharacterDeletionHooks | None = None,
    ) -> None:
        self.campaigns_dir = Path(campaigns_dir)
        self.database_path = Path(database_path)
        self.state_store = state_store
        self.repository = repository
        self.auth_store = auth_store
        self.hooks = hooks or CharacterDeletionHooks()

    def delete(
        self,
        campaign_slug: str,
        character_slug: str,
        *,
        operation_kind: str,
        actor_user_id: int | None = None,
        audit_source: str | None = None,
        expected_definition_revision: int | None = None,
        expected_state_revision: int | None = None,
    ) -> CharacterDeletionResult | None:
        validate_character_slug(character_slug)
        if operation_kind not in DELETE_OPERATION_KINDS:
            raise CharacterDeletionError("Unsupported character deletion operation.")
        if operation_kind == "content_api":
            if actor_user_id is not None or audit_source is not None:
                raise CharacterDeletionError("Raw content deletion cannot create an audit event.")
        elif audit_source != operation_kind:
            raise CharacterDeletionError("Character deletion audit source is invalid.")
        from .committed_publication import active
        if active():
            from .committed_character_publication import publish_delete
            return publish_delete(self, campaign_slug, character_slug,
                                  operation_kind=operation_kind,
                                  actor_user_id=actor_user_id,
                                  audit_source=audit_source,
                                  expected_definition_revision=expected_definition_revision,
                                  expected_state_revision=expected_state_revision)
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with _character_process_lock(key):
                operation = self._prepare_operation(
                    campaign_slug,
                    character_slug,
                    operation_kind=operation_kind,
                    actor_user_id=actor_user_id,
                    audit_source=audit_source,
                )
                if operation is None:
                    return None
                self._event("after_commit", operation.operation_id)
                return self._continue_operation(operation.operation_id)

    def recover_key(self, campaign_slug: str, character_slug: str) -> bool:
        validate_character_slug(character_slug)
        from .committed_publication import active
        if active():
            # A preactivation journal is not a committed deletion. Leave it
            # intact for manager comparison; replay cannot infer a tombstone.
            return False
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with _character_process_lock(key):
                operation = self._load_active_operation(campaign_slug, character_slug)
                if operation is None or operation.state == "conflict":
                    return False
                self._continue_operation(operation.operation_id)
                return True

    def recover_pending(
        self,
        *,
        limit: int = 8,
        retained_runtime_state_lease: object | None = None,
        runtime_state_lease_provider: Callable[[], object | None] | None = None,
    ) -> dict[str, int]:
        from .committed_publication import active
        if active():
            rows = get_db().execute(
                "SELECT state FROM character_deletion_operations "
                "WHERE state IN ('prepared','repository_pending','conflict') "
                "ORDER BY updated_at, operation_id LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return {"recovered": 0,
                    "conflict": sum(row["state"] == "conflict" for row in rows),
                    "pending": sum(row["state"] != "conflict" for row in rows)}
        if (
            retained_runtime_state_lease is not None
            and runtime_state_lease_provider is not None
        ):
            raise ValueError(
                "Supply either a retained runtime-state lease or its provider, not both."
            )
        counts = {"recovered": 0, "conflict": 0, "pending": 0}
        if runtime_state_lease_provider is not None:
            if not _has_pending_character_deletion_recovery():
                return counts
            retained_runtime_state_lease = runtime_state_lease_provider()
        with recovery_runtime_state_lease_context(
            self.database_path,
            retained_lease=retained_runtime_state_lease,
            timeout_seconds=30.0,
        ):
            rows = get_db().execute(
                """
                SELECT operation_id, campaign_slug, character_slug
                FROM character_deletion_operations
                WHERE state IN ('prepared', 'repository_pending')
                ORDER BY updated_at, operation_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            for row in rows:
                key = (str(row["campaign_slug"]), str(row["character_slug"]))
                try:
                    with _character_process_lock(key):
                        operation = self._load_operation(str(row["operation_id"]))
                        if operation is None:
                            continue
                        if operation.state == "conflict":
                            counts["conflict"] += 1
                            continue
                        self._continue_operation(operation.operation_id)
                        counts["recovered"] += 1
                except CharacterDeletionConflict:
                    counts["conflict"] += 1
                except (OSError, RuntimeError, ValueError):
                    counts["pending"] += 1
        return counts

    def _prepare_operation(
        self,
        campaign_slug: str,
        character_slug: str,
        *,
        operation_kind: str,
        actor_user_id: int | None,
        audit_source: str | None,
    ) -> CharacterDeletionOperation | None:
        self._reject_activated_legacy_recovery()
        definition_path, import_path = self._paths(campaign_slug, character_slug)
        operation_id = secrets.token_hex(16)
        connection = get_db()
        self._event("before_prepare", operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if _has_active_character_publication(connection, campaign_slug, character_slug) or (
                _has_active_character_deletion(connection, campaign_slug, character_slug)
            ):
                raise CharacterDeletionConflict(
                    "This character has an active reconciliation operation and requires repair."
                )

            definition = _capture_deletion_file_evidence(
                definition_path,
                operation_id=operation_id,
                artifact_kind="definition",
                max_size=MAX_RECOVERY_PAYLOAD,
            )
            import_metadata = _capture_deletion_file_evidence(
                import_path,
                operation_id=operation_id,
                artifact_kind="import",
                max_size=MAX_RECOVERY_PAYLOAD,
            )
            definition_asset_ref = (
                _managed_portrait_ref(definition_path) if definition.present else ""
            )
            discovered_asset_ref = self._discover_managed_portrait_ref(
                campaign_slug, character_slug
            )
            if (
                definition_asset_ref
                and discovered_asset_ref
                and definition_asset_ref != discovered_asset_ref
            ):
                raise CharacterDeletionConflict(
                    "Character portrait authority does not match its definition."
                )
            asset_ref = definition_asset_ref or discovered_asset_ref
            asset_path = self._asset_path(campaign_slug, character_slug, asset_ref) if asset_ref else None
            asset = (
                _capture_deletion_file_evidence(
                    asset_path,
                    operation_id=operation_id,
                    artifact_kind="asset",
                    max_size=CHARACTER_PORTRAIT_MAX_BYTES,
                )
                if asset_path is not None
                else _DeletionFileEvidence(False, "", 0, "")
            )
            state_row = connection.execute(
                """
                SELECT revision, state_json
                FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            assignment_row = connection.execute(
                """
                SELECT id, user_id, campaign_slug, character_slug, assignment_type,
                       created_at, updated_at
                FROM character_assignments
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            if not any(
                (
                    definition.present,
                    import_metadata.present,
                    asset.present,
                    state_row is not None,
                    assignment_row is not None,
                )
            ):
                connection.rollback()
                return None

            state_revision = int(state_row["revision"]) if state_row is not None else 0
            state_digest = (
                _digest_bytes(str(state_row["state_json"]).encode("utf-8"))
                if state_row is not None
                else ""
            )
            assignment_digest = _digest_sqlite_row(assignment_row) if assignment_row is not None else ""
            deleted_files = definition.present or import_metadata.present
            deleted_state = state_row is not None
            deleted_assignment = assignment_row is not None
            deleted_assets = asset.present
            audit_event_type: str | None = None
            audit_target_user_id: int | None = None
            audit_metadata_json: str | None = None
            if operation_kind != "content_api":
                audit_event_type = "character_deleted"
                audit_target_user_id = (
                    int(assignment_row["user_id"]) if assignment_row is not None else None
                )
                metadata = self.auth_store.sanitize_audit_metadata(
                    {
                        "deleted_files": deleted_files,
                        "deleted_state": deleted_state,
                        "deleted_assignment": deleted_assignment,
                        "deleted_assets": deleted_assets,
                        "source": audit_source,
                    }
                )
                audit_metadata_json = json.dumps(metadata, sort_keys=True)
                if len(audit_metadata_json.encode("utf-8")) > 65536:
                    raise CharacterDeletionError("Character deletion audit metadata is too large.")

            now = isoformat(utcnow())
            connection.execute(
                """
                INSERT INTO character_deletion_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    definition_present, definition_digest, definition_size,
                    definition_tombstone_name,
                    import_present, import_digest, import_size, import_tombstone_name,
                    asset_present, asset_ref, asset_digest, asset_size, asset_tombstone_name,
                    previous_state_present, previous_state_revision, previous_state_digest,
                    previous_assignment_present, previous_assignment_digest,
                    deleted_files, deleted_state, deleted_assignment, deleted_assets,
                    audit_event_type, audit_actor_user_id, audit_target_user_id,
                    audit_metadata_json, state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', '', ?, ?)
                """,
                (
                    operation_id,
                    campaign_slug,
                    character_slug,
                    operation_kind,
                    int(definition.present),
                    definition.digest,
                    definition.size,
                    definition.tombstone_name,
                    int(import_metadata.present),
                    import_metadata.digest,
                    import_metadata.size,
                    import_metadata.tombstone_name,
                    int(asset.present),
                    asset_ref if asset.present else "",
                    asset.digest,
                    asset.size,
                    asset.tombstone_name,
                    int(state_row is not None),
                    state_revision,
                    state_digest,
                    int(assignment_row is not None),
                    assignment_digest,
                    int(deleted_files),
                    int(deleted_state),
                    int(deleted_assignment),
                    int(deleted_assets),
                    audit_event_type,
                    actor_user_id if audit_event_type else None,
                    audit_target_user_id,
                    audit_metadata_json,
                    now,
                    now,
                ),
            )
            prepared_operation = self._load_operation(
                operation_id,
                connection=connection,
            )
            if prepared_operation is None:
                raise CharacterDeletionError("Character deletion operation disappeared.")
            self._validate_initial_file_authority(prepared_operation)
            self._validate_prepared_database_authority(
                campaign_slug,
                character_slug,
                state_present=state_row is not None,
                state_revision=state_revision,
                state_digest=state_digest,
                assignment_present=assignment_row is not None,
                assignment_digest=assignment_digest,
                connection=connection,
            )
            if state_row is not None:
                connection.execute(
                    "DELETE FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
                    (campaign_slug, character_slug),
                )
            if assignment_row is not None:
                connection.execute(
                    "DELETE FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?",
                    (campaign_slug, character_slug),
                )
            if audit_event_type is not None:
                self.auth_store.insert_audit_event(
                    event_type=audit_event_type,
                    actor_user_id=actor_user_id,
                    target_user_id=audit_target_user_id,
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                    metadata=json.loads(audit_metadata_json or "{}"),
                    commit=False,
                )
            self._event("before_commit", operation_id)
            self._validate_initial_file_authority(prepared_operation)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterDeletionError("Character deletion operation disappeared.")
        return operation

    def _validate_initial_file_authority(
        self, operation: CharacterDeletionOperation
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, bool, str, int, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(source.with_name(tombstone_name), max_size=max_size)
                    if tombstone_name
                    else None
                )
            except ValueError:
                raise CharacterDeletionConflict(
                    f"Character {label} changed before deletion commit."
                ) from None
            if present:
                if source_evidence != (digest, size) or tombstone_evidence is not None:
                    raise CharacterDeletionConflict(
                        f"Character {label} changed before deletion commit."
                    )
            elif source_evidence is not None or tombstone_evidence is not None:
                raise CharacterDeletionConflict(
                    f"Character {label} changed before deletion commit."
                )

    def _continue_operation(self, operation_id: str) -> CharacterDeletionResult:
        self._reject_activated_legacy_recovery()
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterDeletionError("Character deletion operation is unavailable.")
        if operation.state == "conflict":
            raise CharacterDeletionConflict(
                "This character has a reconciliation conflict and requires repair."
            )
        if operation.state == "prepared":
            self._move_files(operation)
            operation = self._transition_repository_pending(operation)
        return self._refresh_and_cleanup(operation)

    def _move_files(self, operation: CharacterDeletionOperation) -> None:
        self._reject_activated_legacy_recovery()
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            try:
                asset_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.asset_ref,
                )
            except ValueError:
                self._raise_conflict(operation.operation_id, "asset_ref_invalid")
            resources.append(
                (
                    "asset",
                    asset_path,
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            tombstone = source.with_name(tombstone_name) if tombstone_name else None
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(tombstone, max_size=max_size)
                    if tombstone is not None
                    else None
                )
            except ValueError:
                self._raise_conflict(operation.operation_id, f"{label}_unsafe")
            expected = (digest, size)
            if not present:
                if source_evidence is not None or tombstone_evidence is not None:
                    self._raise_conflict(operation.operation_id, f"{label}_presence_conflict")
                continue
            if source_evidence == expected and tombstone_evidence is None:
                self._event(f"before_{label}_move", operation.operation_id)
                try:
                    atomic_move_file(source, tombstone)
                except (OSError, ValueError):
                    self._raise_conflict(operation.operation_id, f"{label}_move_conflict")
                self._event(f"after_{label}_move", operation.operation_id)
            elif source_evidence is None and tombstone_evidence == expected:
                pass
            else:
                self._raise_conflict(operation.operation_id, f"{label}_digest_conflict")

    def _transition_repository_pending(
        self, operation: CharacterDeletionOperation
    ) -> CharacterDeletionOperation:
        self._reject_activated_legacy_recovery()
        connection = get_db()
        self._event("before_repository_pending", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if current is None or not self._same_owner(current, operation):
                raise CharacterDeletionConflict("Character deletion ownership changed.")
            if current.state == "repository_pending":
                connection.commit()
                return current
            if current.state != "prepared":
                raise CharacterDeletionConflict("Character deletion state changed.")
            self._validate_deleted_database_authority(operation, connection=connection)
            if _has_active_character_publication(
                connection, operation.campaign_slug, operation.character_slug
            ):
                raise _AuthorityConflict("publication_operation_conflict")
            self._validate_moved_file_authority(operation)
            cursor = connection.execute(
                """
                UPDATE character_deletion_operations
                SET state = 'repository_pending', error_code = '', updated_at = ?
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'prepared'
                """,
                (
                    isoformat(utcnow()),
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterDeletionConflict("Character deletion state changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_repository_pending", operation.operation_id)
        refreshed = self._load_operation(operation.operation_id)
        if refreshed is None:
            raise CharacterDeletionError("Character deletion operation disappeared.")
        return refreshed

    def _refresh_and_cleanup(
        self, operation: CharacterDeletionOperation
    ) -> CharacterDeletionResult:
        self._reject_activated_legacy_recovery()
        if operation.state != "repository_pending":
            raise CharacterDeletionError("Character deletion has not reached its commit point.")
        self.repository.invalidate_character(operation.campaign_slug, operation.character_slug)
        self._event("before_refresh", operation.operation_id)
        if self.repository.get_character(operation.campaign_slug, operation.character_slug) is not None:
            self._raise_conflict(operation.operation_id, "repository_refresh_conflict")
        self._event("after_refresh", operation.operation_id)
        connection = get_db()
        self._event("before_cleanup", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterDeletionConflict("Character deletion ownership changed.")
            self._validate_deleted_database_authority(operation, connection=connection)
            if _has_active_character_publication(
                connection, operation.campaign_slug, operation.character_slug
            ):
                raise _AuthorityConflict("publication_operation_conflict")
            self._validate_moved_file_authority(
                operation,
                allow_cleaned_tombstones=True,
            )
            self._cleanup_tombstones(operation)
            self._validate_cleaned_file_authority(operation)
            cursor = connection.execute(
                """
                DELETE FROM character_deletion_operations
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'repository_pending'
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterDeletionConflict("Character deletion cleanup changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_cleanup", operation.operation_id)
        self._prune_empty_directories(operation)
        return CharacterDeletionResult(
            character_slug=operation.character_slug,
            deleted_files=operation.deleted_files,
            deleted_state=operation.deleted_state,
            deleted_assignment=operation.deleted_assignment,
            deleted_assets=operation.deleted_assets,
        )

    def _validate_moved_file_authority(
        self,
        operation: CharacterDeletionOperation,
        *,
        allow_cleaned_tombstones: bool = False,
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, bool, str, int, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            tombstone = source.with_name(tombstone_name) if tombstone_name else None
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(tombstone, max_size=max_size)
                    if tombstone is not None
                    else None
                )
            except ValueError:
                raise _AuthorityConflict(f"{label}_authority_unsafe") from None
            if present:
                if source_evidence is not None or (
                    tombstone_evidence != (digest, size)
                    and not (allow_cleaned_tombstones and tombstone_evidence is None)
                ):
                    raise _AuthorityConflict(f"{label}_tombstone_conflict")
            elif source_evidence is not None or tombstone_evidence is not None:
                raise _AuthorityConflict(f"{label}_presence_conflict")

    def _cleanup_tombstones(self, operation: CharacterDeletionOperation) -> None:
        self._reject_activated_legacy_recovery()
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, str, str, int]] = []
        if operation.definition_present:
            resources.append(
                (
                    "definition",
                    definition_path,
                    operation.definition_tombstone_name,
                    operation.definition_digest,
                    MAX_RECOVERY_PAYLOAD,
                )
            )
        if operation.import_present:
            resources.append(
                (
                    "import",
                    import_path,
                    operation.import_tombstone_name,
                    operation.import_digest,
                    MAX_RECOVERY_PAYLOAD,
                )
            )
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    operation.asset_tombstone_name,
                    operation.asset_digest,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, tombstone_name, digest, max_size in resources:
            tombstone = source.with_name(tombstone_name)
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = _read_deletion_file(tombstone, max_size=max_size)
            except ValueError:
                raise _AuthorityConflict(f"{label}_cleanup_conflict") from None
            if source_evidence is not None:
                raise _AuthorityConflict(f"{label}_source_reappeared")
            if tombstone_evidence is None:
                durable_sync_directory(tombstone.parent)
                continue
            if tombstone_evidence[0] != digest:
                raise _AuthorityConflict(f"{label}_tombstone_conflict")
            self._event(f"before_{label}_unlink", operation.operation_id)
            durable_unlink_file(tombstone)
            self._event(f"after_{label}_unlink", operation.operation_id)

    def _validate_cleaned_file_authority(
        self, operation: CharacterDeletionOperation
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            ("import", import_path, operation.import_tombstone_name, MAX_RECOVERY_PAYLOAD),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, tombstone_name, max_size in resources:
            try:
                if _read_deletion_file(source, max_size=max_size) is not None:
                    raise _AuthorityConflict(f"{label}_source_reappeared")
                if tombstone_name and _read_deletion_file(
                    source.with_name(tombstone_name), max_size=max_size
                ) is not None:
                    raise _AuthorityConflict(f"{label}_tombstone_remained")
            except ValueError:
                raise _AuthorityConflict(f"{label}_cleanup_conflict") from None

    @staticmethod
    def _validate_prepared_database_authority(
        campaign_slug: str,
        character_slug: str,
        *,
        state_present: bool,
        state_revision: int,
        state_digest: str,
        assignment_present: bool,
        assignment_digest: str,
        connection: Any,
    ) -> None:
        state_row = connection.execute(
            "SELECT revision, state_json FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
            (campaign_slug, character_slug),
        ).fetchone()
        assignment_row = connection.execute(
            """
            SELECT id, user_id, campaign_slug, character_slug, assignment_type,
                   created_at, updated_at
            FROM character_assignments
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        if state_present != (state_row is not None) or (
            state_row is not None
            and (
                int(state_row["revision"]) != state_revision
                or _digest_bytes(str(state_row["state_json"]).encode("utf-8")) != state_digest
            )
        ):
            raise CharacterDeletionConflict("Character state changed before deletion commit.")
        if assignment_present != (assignment_row is not None) or (
            assignment_row is not None and _digest_sqlite_row(assignment_row) != assignment_digest
        ):
            raise CharacterDeletionConflict("Character assignment changed before deletion commit.")

    @staticmethod
    def _validate_deleted_database_authority(
        operation: CharacterDeletionOperation,
        *,
        connection: Any,
    ) -> None:
        state_row = connection.execute(
            "SELECT 1 FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        assignment_row = connection.execute(
            "SELECT 1 FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?",
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        if state_row is not None:
            raise _AuthorityConflict("state_reappeared")
        if assignment_row is not None:
            raise _AuthorityConflict("assignment_reappeared")

    def _raise_conflict(self, operation_id: str, error_code: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE character_deletion_operations
                SET state = 'conflict', error_code = ?, updated_at = ?
                WHERE operation_id = ?
                  AND state IN ('prepared', 'repository_pending')
                """,
                (error_code, isoformat(utcnow()), operation_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        raise CharacterDeletionConflict(
            "This character has a reconciliation conflict and requires repair."
        )

    def _load_active_operation(
        self, campaign_slug: str, character_slug: str
    ) -> CharacterDeletionOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM character_deletion_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return _map_deletion_operation(row)

    def _load_operation(
        self, operation_id: str, *, connection: Any | None = None
    ) -> CharacterDeletionOperation | None:
        row = (connection or get_db()).execute(
            "SELECT * FROM character_deletion_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return _map_deletion_operation(row)

    def _paths(self, campaign_slug: str, character_slug: str) -> tuple[Path, Path]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        return (
            resolve_character_path(config.characters_dir, character_slug, "definition.yaml"),
            resolve_character_path(config.characters_dir, character_slug, "import.yaml"),
        )

    def _asset_path(self, campaign_slug: str, character_slug: str, asset_ref: str) -> Path:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        _, asset_path = resolve_character_portrait_asset_path(
            config.campaign_dir, character_slug, asset_ref
        )
        return asset_path

    def _discover_managed_portrait_ref(
        self, campaign_slug: str, character_slug: str
    ) -> str:
        matches: list[str] = []
        for extension in sorted(CHARACTER_PORTRAIT_ASSET_EXTENSIONS):
            asset_ref = f"characters/{character_slug}/portrait{extension}"
            try:
                evidence = _read_deletion_file(
                    self._asset_path(campaign_slug, character_slug, asset_ref),
                    max_size=CHARACTER_PORTRAIT_MAX_BYTES,
                )
            except ValueError:
                raise CharacterDeletionConflict(
                    "Character portrait evidence is unsafe."
                ) from None
            if evidence is not None:
                matches.append(asset_ref)
        if len(matches) > 1:
            raise CharacterDeletionConflict(
                "Character portrait ownership is ambiguous."
            )
        return matches[0] if matches else ""

    @staticmethod
    def _same_owner(
        current: CharacterDeletionOperation, expected: CharacterDeletionOperation
    ) -> bool:
        return current == expected

    def _prune_empty_directories(self, operation: CharacterDeletionOperation) -> None:
        try:
            definition_path, _ = self._paths(
                operation.campaign_slug, operation.character_slug
            )
            _prune_empty_asset_directories(
                definition_path.parent,
                stop_dir=definition_path.parent.parent,
            )
            if operation.asset_present:
                assets_root, asset_path = resolve_character_portrait_asset_path(
                    load_campaign_character_config(
                        self.campaigns_dir, operation.campaign_slug
                    ).campaign_dir,
                    operation.character_slug,
                    operation.asset_ref,
                )
                _prune_empty_asset_directories(asset_path.parent, stop_dir=assets_root)
        except (OSError, ValueError):
            return

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)


def _map_operation(row: sqlite3.Row | None) -> CharacterReconciliationOperation | None:
    if row is None:
        return None
    return CharacterReconciliationOperation(
        operation_id=str(row["operation_id"]),
        campaign_slug=str(row["campaign_slug"]),
        character_slug=str(row["character_slug"]),
        operation_kind=str(row["operation_kind"]),
        previous_definition_digest=str(row["previous_definition_digest"]),
        desired_definition_digest=str(row["desired_definition_digest"]),
        previous_import_digest=str(row["previous_import_digest"]),
        desired_import_digest=str(row["desired_import_digest"]),
        previous_state_digest=str(row["previous_state_digest"]),
        desired_state_digest=str(row["desired_state_digest"]),
        previous_state_revision=int(row["previous_state_revision"]),
        desired_state_revision=int(row["desired_state_revision"]),
        desired_definition_yaml=bytes(row["desired_definition_yaml"]),
        desired_import_yaml=bytes(row["desired_import_yaml"]),
        previous_asset_ref=str(row["previous_asset_ref"]),
        desired_asset_ref=str(row["desired_asset_ref"]),
        previous_asset_digest=str(row["previous_asset_digest"]),
        desired_asset_digest=str(row["desired_asset_digest"]),
        desired_asset_bytes=bytes(row["desired_asset_bytes"]),
        audit_event_type=(
            str(row["audit_event_type"])
            if row["audit_event_type"] is not None
            else None
        ),
        audit_actor_user_id=(
            int(row["audit_actor_user_id"])
            if row["audit_actor_user_id"] is not None
            else None
        ),
        audit_target_user_id=(
            int(row["audit_target_user_id"])
            if row["audit_target_user_id"] is not None
            else None
        ),
        audit_metadata_json=(
            str(row["audit_metadata_json"])
            if row["audit_metadata_json"] is not None
            else None
        ),
        state=str(row["state"]),
        error_code=str(row["error_code"]),
    )


def _map_deletion_operation(row: sqlite3.Row | None) -> CharacterDeletionOperation | None:
    if row is None:
        return None
    return CharacterDeletionOperation(
        operation_id=str(row["operation_id"]),
        campaign_slug=str(row["campaign_slug"]),
        character_slug=str(row["character_slug"]),
        operation_kind=str(row["operation_kind"]),
        definition_present=bool(row["definition_present"]),
        definition_digest=str(row["definition_digest"]),
        definition_size=int(row["definition_size"]),
        definition_tombstone_name=str(row["definition_tombstone_name"]),
        import_present=bool(row["import_present"]),
        import_digest=str(row["import_digest"]),
        import_size=int(row["import_size"]),
        import_tombstone_name=str(row["import_tombstone_name"]),
        asset_present=bool(row["asset_present"]),
        asset_ref=str(row["asset_ref"]),
        asset_digest=str(row["asset_digest"]),
        asset_size=int(row["asset_size"]),
        asset_tombstone_name=str(row["asset_tombstone_name"]),
        previous_state_present=bool(row["previous_state_present"]),
        previous_state_revision=int(row["previous_state_revision"]),
        previous_state_digest=str(row["previous_state_digest"]),
        previous_assignment_present=bool(row["previous_assignment_present"]),
        previous_assignment_digest=str(row["previous_assignment_digest"]),
        deleted_files=bool(row["deleted_files"]),
        deleted_state=bool(row["deleted_state"]),
        deleted_assignment=bool(row["deleted_assignment"]),
        deleted_assets=bool(row["deleted_assets"]),
        audit_event_type=(
            str(row["audit_event_type"]) if row["audit_event_type"] is not None else None
        ),
        audit_actor_user_id=(
            int(row["audit_actor_user_id"])
            if row["audit_actor_user_id"] is not None
            else None
        ),
        audit_target_user_id=(
            int(row["audit_target_user_id"])
            if row["audit_target_user_id"] is not None
            else None
        ),
        audit_metadata_json=(
            str(row["audit_metadata_json"])
            if row["audit_metadata_json"] is not None
            else None
        ),
        state=str(row["state"]),
        error_code=str(row["error_code"]),
    )


def _has_active_character_publication(
    connection: Any,
    campaign_slug: str,
    character_slug: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        is not None
    )


def _capture_deletion_file_evidence(
    path: Path,
    *,
    operation_id: str,
    artifact_kind: str,
    max_size: int,
) -> _DeletionFileEvidence:
    evidence = _read_deletion_file(path, max_size=max_size)
    if evidence is None:
        return _DeletionFileEvidence(False, "", 0, "")
    digest, size = evidence
    return _DeletionFileEvidence(
        True,
        digest,
        size,
        f".character-delete-{operation_id}-{artifact_kind}.tombstone",
    )


def _read_deletion_file(path: Path, *, max_size: int) -> tuple[str, int] | None:
    try:
        details = Path(path).lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Character deletion evidence is unreadable.") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)
        or details.st_size < 1
        or details.st_size > max_size
    ):
        raise ValueError("Character deletion evidence is unsafe.")
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("Character deletion evidence is unreadable.") from exc
    if len(payload) != details.st_size or not payload:
        raise ValueError("Character deletion evidence changed while it was read.")
    return _digest_bytes(payload), len(payload)


def _managed_portrait_ref(definition_path: Path) -> str:
    try:
        payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CharacterDeletionError("Character definition is unreadable.") from exc
    if not isinstance(payload, dict):
        raise CharacterDeletionError("Character definition is unreadable.")
    profile = payload.get("profile") or {}
    if not isinstance(profile, dict):
        raise CharacterDeletionError("Character portrait metadata is invalid.")
    return str(profile.get("portrait_asset_ref") or "").strip()


def _digest_sqlite_row(row: sqlite3.Row) -> str:
    payload = {key: row[key] for key in row.keys()}
    return _digest_bytes(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _classify_create_file(path: Path, desired_digest: str) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return "previous"
    except OSError:
        return "conflict"
    return "desired" if _digest_bytes(data) == desired_digest else "conflict"


def _digest_path(path: Path) -> str | None:
    try:
        return _digest_bytes(path.read_bytes())
    except (FileNotFoundError, OSError):
        return None


def _digest_regular_file(path: Path) -> str | None:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Character portrait asset is unreadable.") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)
    ):
        raise ValueError("Character portrait asset is unsafe.")
    try:
        return _digest_bytes(path.read_bytes())
    except OSError as exc:
        raise ValueError("Character portrait asset is unreadable.") from exc


def _prune_empty_asset_directories(path: Path, *, stop_dir: Path) -> None:
    current = Path(path)
    stop = Path(stop_dir)
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _classify_update_file(
    path: Path,
    previous_digest: str,
    desired_digest: str,
) -> str:
    digest = _digest_path(path)
    if digest == desired_digest:
        return "desired"
    if digest == previous_digest:
        return "previous"
    return "conflict"


def _classify_publication_file(
    path: Path,
    *,
    previous_digest: str,
    desired_digest: str,
    is_create: bool,
) -> str:
    if is_create:
        return _classify_create_file(path, desired_digest)
    return _classify_update_file(path, previous_digest, desired_digest)
