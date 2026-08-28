from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

from .character_models import CharacterDefinition, CharacterRecord
from .character_path_safety import resolve_character_definition_import_paths
from .character_reconciliation import CharacterPublicationCoordinator
from .character_repository import load_campaign_character_config
from .character_store import CharacterStateStore, ExactCharacterState
from .character_update_planner import (
    CharacterUpdatePlan,
    PlanStatus,
    SemanticCategory,
    StateImpact,
)
from .db import get_db


TOKEN_PREFIX = "cu1"
TOKEN_TTL_SECONDS = 600
MAX_OPERATIONS = 128
MAX_SINGLE_OPERATION_TOKEN_BYTES = 8 * 1024
MAX_BATCH_TOKEN_BYTES = 384 * 1024
MAX_IDENTITY_BYTES = 512
MAX_QUANTITY = 999

_SIGNING_DOMAIN = b"campaign-player-wiki:character-update-review:v1\x00"
_DIGEST_PATTERN = frozenset("0123456789abcdef")
_OPERATION_KEYS = frozenset(
    {"kind", "source_kind", "source_value", "target_id", "quantity"}
)
_OPERATION_KINDS = frozenset(
    {
        "campaign_feature_grant",
        "campaign_equipment_add",
        "systems_item_add",
        "equipment_safe_relink",
    }
)
_SOURCE_KINDS = frozenset({"campaign_page", "systems_entry"})
_STATE_IMPACTS = frozenset({"preserve_exact", "reconcile_required"})
_PAYLOAD_KEYS = frozenset(
    {
        "version",
        "actor_user_id",
        "campaign_slug",
        "character_slug",
        "operations",
        "definition_digest",
        "import_digest",
        "state_revision",
        "state_digest",
        "state_updated_at",
        "state_updated_by_user_id",
        "source_digest",
        "policy_digest",
        "native_digest",
        "planner_version",
        "state_impact",
        "candidate_digest",
        "semantic_digest",
        "issued_at",
    }
)


class CharacterUpdateTokenError(ValueError):
    """A review token is malformed, untrusted, stale, or outside its bounds."""


class CharacterUpdateStaleError(RuntimeError):
    """Authoritative inputs no longer support the reviewed operation set."""


class CharacterUpdateApplyClassification(str, Enum):
    CONFIRMED_APPLIED = "confirmed_applied"
    UNCHANGED = "unchanged"
    REFUSED_STALE = "refused_stale"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class CharacterUpdateReviewClaims:
    actor_user_id: int
    campaign_slug: str
    character_slug: str
    operations: tuple[Mapping[str, Any], ...]
    definition_digest: str
    import_digest: str
    state_revision: int
    state_digest: str
    state_updated_at: str
    state_updated_by_user_id: int | None
    source_digest: str
    policy_digest: str
    native_digest: str
    planner_version: int
    state_impact: str
    candidate_digest: str
    semantic_digest: str
    issued_at: int


@dataclass(frozen=True, slots=True)
class CharacterUpdateRecompute:
    record: CharacterRecord
    plan: CharacterUpdatePlan
    operations: tuple[Mapping[str, Any], ...]
    source_digest: str
    policy_digest: str
    native_digest: str
    readback_semantic_rows: Callable[[CharacterRecord], Sequence[object]]


@dataclass(frozen=True, slots=True)
class CharacterUpdateReviewIssue:
    token: str | None
    classification: CharacterUpdateApplyClassification | None


@dataclass(frozen=True, slots=True)
class CharacterUpdateApplyResult:
    classification: CharacterUpdateApplyClassification
    candidate_digest: str = ""


@dataclass(frozen=True, slots=True)
class _CurrentEvidence:
    claims: CharacterUpdateReviewClaims
    exact_state: ExactCharacterState


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_b64decode(value: str) -> bytes:
    if not value or "=" in value:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    try:
        return base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise CharacterUpdateTokenError(
            "Character update review token is invalid."
        ) from exc


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CharacterUpdateTokenError(
            "Character update review token is invalid."
        ) from exc


def canonical_digest(value: Any) -> str:
    """Return a bounded canonical digest without exposing the digested payload."""

    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _bounded_text(value: Any, *, maximum: int = MAX_IDENTITY_BYTES) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    if "\x00" in value or len(value.encode("utf-8")) > maximum:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return value


def _digest(value: Any) -> str:
    digest = _bounded_text(value, maximum=64)
    if len(digest) != 64 or any(character not in _DIGEST_PATTERN for character in digest):
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return digest


def _positive_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return value


def _optional_positive_integer(value: Any) -> int | None:
    if value is None:
        return None
    return _positive_integer(value)


def _operation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OPERATION_KEYS:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    kind = _bounded_text(value["kind"])
    source_kind = _bounded_text(value["source_kind"])
    if kind not in _OPERATION_KINDS or source_kind not in _SOURCE_KINDS:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    quantity = _positive_integer(value["quantity"])
    if quantity > MAX_QUANTITY:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return {
        "kind": kind,
        "source_kind": source_kind,
        "source_value": _bounded_text(value["source_value"]),
        "target_id": _bounded_text(value["target_id"]),
        "quantity": quantity,
    }


def _claims_payload(claims: CharacterUpdateReviewClaims) -> dict[str, Any]:
    if not isinstance(claims, CharacterUpdateReviewClaims):
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    operations = tuple(_operation(item) for item in claims.operations)
    if not 1 <= len(operations) <= MAX_OPERATIONS:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    actor_user_id = _positive_integer(claims.actor_user_id)
    state_revision = _positive_integer(claims.state_revision)
    planner_version = _positive_integer(claims.planner_version)
    if isinstance(claims.issued_at, bool) or not isinstance(claims.issued_at, int):
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    if claims.issued_at < 0:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    state_impact = _bounded_text(claims.state_impact)
    if state_impact not in _STATE_IMPACTS:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return {
        "version": 1,
        "actor_user_id": actor_user_id,
        "campaign_slug": _bounded_text(claims.campaign_slug, maximum=128),
        "character_slug": _bounded_text(claims.character_slug, maximum=255),
        "operations": list(operations),
        "definition_digest": _digest(claims.definition_digest),
        "import_digest": _digest(claims.import_digest),
        "state_revision": state_revision,
        "state_digest": _digest(claims.state_digest),
        "state_updated_at": _bounded_text(claims.state_updated_at, maximum=64),
        "state_updated_by_user_id": _optional_positive_integer(
            claims.state_updated_by_user_id
        ),
        "source_digest": _digest(claims.source_digest),
        "policy_digest": _digest(claims.policy_digest),
        "native_digest": _digest(claims.native_digest),
        "planner_version": planner_version,
        "state_impact": state_impact,
        "candidate_digest": _digest(claims.candidate_digest),
        "semantic_digest": _digest(claims.semantic_digest),
        "issued_at": claims.issued_at,
    }


def _claims_from_payload(payload: Any) -> CharacterUpdateReviewClaims:
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    if payload.get("version") != 1:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    operations_value = payload.get("operations")
    if not isinstance(operations_value, list):
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    claims = CharacterUpdateReviewClaims(
        actor_user_id=payload.get("actor_user_id"),
        campaign_slug=payload.get("campaign_slug"),
        character_slug=payload.get("character_slug"),
        operations=tuple(operations_value),
        definition_digest=payload.get("definition_digest"),
        import_digest=payload.get("import_digest"),
        state_revision=payload.get("state_revision"),
        state_digest=payload.get("state_digest"),
        state_updated_at=payload.get("state_updated_at"),
        state_updated_by_user_id=payload.get("state_updated_by_user_id"),
        source_digest=payload.get("source_digest"),
        policy_digest=payload.get("policy_digest"),
        native_digest=payload.get("native_digest"),
        planner_version=payload.get("planner_version"),
        state_impact=payload.get("state_impact"),
        candidate_digest=payload.get("candidate_digest"),
        semantic_digest=payload.get("semantic_digest"),
        issued_at=payload.get("issued_at"),
    )
    normalized = _claims_payload(claims)
    if normalized != payload:
        raise CharacterUpdateTokenError("Character update review token is invalid.")
    return CharacterUpdateReviewClaims(
        **{
            key: (tuple(value) if key == "operations" else value)
            for key, value in normalized.items()
            if key != "version"
        },
    )


class CharacterUpdateTokenCodec:
    def __init__(
        self,
        secret: str | bytes,
        *,
        now: Callable[[], int | float] | None = None,
    ) -> None:
        if isinstance(secret, str):
            secret_bytes = secret.encode("utf-8")
        elif isinstance(secret, bytes):
            secret_bytes = bytes(secret)
        else:
            secret_bytes = b""
        if not secret_bytes:
            raise ValueError("Character update token signing secret is required.")
        self._secret = secret_bytes
        self._now = now or time.time

    def issue(self, claims: CharacterUpdateReviewClaims) -> str:
        payload = _claims_payload(claims)
        body = _canonical_json(payload)
        signature = hmac.new(
            self._secret,
            _SIGNING_DOMAIN + body,
            hashlib.sha256,
        ).digest()
        token = f"{TOKEN_PREFIX}.{_urlsafe_b64encode(body)}.{_urlsafe_b64encode(signature)}"
        maximum = (
            MAX_SINGLE_OPERATION_TOKEN_BYTES
            if len(payload["operations"]) == 1
            else MAX_BATCH_TOKEN_BYTES
        )
        if len(token.encode("utf-8")) > maximum:
            raise CharacterUpdateTokenError(
                "Character update review token exceeds its size bound."
            )
        return token

    def verify(
        self,
        token: str,
        *,
        actor_user_id: int,
        campaign_slug: str,
        character_slug: str,
        now: int | float | None = None,
    ) -> CharacterUpdateReviewClaims:
        if not isinstance(token, str) or not token or len(token.encode("utf-8")) > MAX_BATCH_TOKEN_BYTES:
            raise CharacterUpdateTokenError("Character update review token is invalid.")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
            raise CharacterUpdateTokenError("Character update review token is invalid.")
        body = _urlsafe_b64decode(parts[1])
        supplied_signature = _urlsafe_b64decode(parts[2])
        if (
            _urlsafe_b64encode(body) != parts[1]
            or _urlsafe_b64encode(supplied_signature) != parts[2]
        ):
            raise CharacterUpdateTokenError("Character update review token is invalid.")
        expected_signature = hmac.new(
            self._secret,
            _SIGNING_DOMAIN + body,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise CharacterUpdateTokenError("Character update review token is invalid.")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CharacterUpdateTokenError(
                "Character update review token is invalid."
            ) from exc
        if _canonical_json(payload) != body:
            raise CharacterUpdateTokenError("Character update review token is invalid.")
        claims = _claims_from_payload(payload)
        effective_now = int(self._now() if now is None else now)
        age = effective_now - claims.issued_at
        if age < 0 or age > TOKEN_TTL_SECONDS:
            raise CharacterUpdateTokenError("Character update review token is stale.")
        if (
            claims.actor_user_id != actor_user_id
            or claims.campaign_slug != campaign_slug
            or claims.character_slug != character_slug
        ):
            raise CharacterUpdateTokenError("Character update review token is stale.")
        return claims


def _semantic_rows_payload(rows: Sequence[object]) -> dict[str, Any]:
    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        category = str(getattr(getattr(row, "category", ""), "value", getattr(row, "category", "")))
        if category not in {item.value for item in SemanticCategory}:
            raise ValueError("Character update semantic readback is invalid.")
        change = str(getattr(getattr(row, "change", ""), "value", getattr(row, "change", "")))
        normalized_rows.append(
            {
                "category": category,
                "identity": str(getattr(row, "identity", "")),
                "label": str(getattr(row, "label", "")),
                "change": change,
                "before": str(getattr(row, "before", "")),
                "after": str(getattr(row, "after", "")),
            }
        )
    return {
        "categories": [category.value for category in SemanticCategory],
        "rows": normalized_rows,
    }


def _same(left: Any, right: Any) -> bool:
    return canonical_digest(left) == canonical_digest(right)


def _row_identity(row: Mapping[str, Any], family: str) -> str:
    if family == "resources":
        return str(row.get("id") or "").strip()
    return str(row.get("catalog_ref") or row.get("id") or "").strip()


def _validated_desired_state(recompute: CharacterUpdateRecompute) -> dict[str, Any]:
    baseline = deepcopy(dict(recompute.record.state_record.state or {}))
    impact = StateImpact(recompute.plan.state_impact)
    if impact is StateImpact.PRESERVE_EXACT:
        return baseline
    derived = dict(recompute.plan.derived_character or {})
    desired_value = derived.get("state")
    if not isinstance(desired_value, Mapping):
        raise ValueError("Character update state reconciliation is unavailable.")
    desired = deepcopy(dict(desired_value))
    baseline_other = deepcopy(baseline)
    desired_other = deepcopy(desired)
    expected_by_family = {
        "resources": {
            item.resource_id: item.initial_value
            for item in recompute.plan.reconciliation.resources
        },
        "inventory": dict(recompute.plan.reconciliation.inventory),
    }
    for family, expected in expected_by_family.items():
        before_rows = list(baseline_other.pop(family, []) or [])
        after_rows = list(desired_other.pop(family, []) or [])
        if not all(isinstance(row, Mapping) for row in before_rows + after_rows):
            raise ValueError("Character update state reconciliation is invalid.")
        before = [dict(row) for row in before_rows]
        after = [dict(row) for row in after_rows]
        before_ids = [_row_identity(row, family) for row in before]
        after_ids = [_row_identity(row, family) for row in after]
        if (
            any(not identity for identity in before_ids + after_ids)
            or len(set(before_ids)) != len(before_ids)
            or len(set(after_ids)) != len(after_ids)
            or after[: len(before)] != before
        ):
            raise ValueError("Character update state reconciliation changed existing rows.")
        additions = after[len(before) :]
        if {_row_identity(row, family) for row in additions} != set(expected):
            raise ValueError("Character update state reconciliation added unreviewed rows.")
        for row in additions:
            identity = _row_identity(row, family)
            actual = row.get("current") if family == "resources" else row.get("quantity")
            if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected[identity]:
                raise ValueError("Character update state reconciliation changed reviewed values.")
    if not _same(baseline_other, desired_other):
        raise ValueError("Character update state reconciliation changed opaque state.")
    return desired


class CharacterUpdateApplyEngine:
    """Issue READY review tokens and cross the publication boundary at most once."""

    def __init__(
        self,
        *,
        campaigns_dir: Path,
        state_store: CharacterStateStore,
        coordinator: CharacterPublicationCoordinator,
        secret: str | bytes,
        now: Callable[[], int | float] | None = None,
    ) -> None:
        self.campaigns_dir = Path(campaigns_dir)
        self.state_store = state_store
        self.coordinator = coordinator
        self._now = now or time.time
        self.codec = CharacterUpdateTokenCodec(secret, now=self._now)

    def issue_review(
        self,
        recompute: CharacterUpdateRecompute,
        *,
        actor_user_id: int,
    ) -> CharacterUpdateReviewIssue:
        status = PlanStatus(recompute.plan.status)
        if status is PlanStatus.NO_OP:
            return CharacterUpdateReviewIssue(
                None,
                CharacterUpdateApplyClassification.UNCHANGED,
            )
        if status is not PlanStatus.READY:
            return CharacterUpdateReviewIssue(None, None)
        evidence = self._current_evidence(
            recompute,
            actor_user_id=actor_user_id,
            issued_at=int(self._now()),
        )
        return CharacterUpdateReviewIssue(self.codec.issue(evidence.claims), None)

    def apply(
        self,
        token: str,
        *,
        actor_user_id: int,
        campaign_slug: str,
        character_slug: str,
        recompute: Callable[[tuple[Mapping[str, Any], ...]], CharacterUpdateRecompute],
    ) -> CharacterUpdateApplyResult:
        try:
            reviewed = self.codec.verify(
                token,
                actor_user_id=actor_user_id,
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        except CharacterUpdateTokenError:
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.REFUSED_STALE
            )

        try:
            current = recompute(reviewed.operations)
            if PlanStatus(current.plan.status) is not PlanStatus.READY:
                raise CharacterUpdateStaleError("Reviewed plan is no longer ready.")
            evidence = self._current_evidence(
                current,
                actor_user_id=actor_user_id,
                issued_at=reviewed.issued_at,
            )
            if evidence.claims != reviewed:
                raise CharacterUpdateStaleError("Reviewed inputs changed.")
            desired_state = _validated_desired_state(current)
            candidate_payload = current.plan.candidate_definition
            if not isinstance(candidate_payload, Mapping):
                raise ValueError("Character update candidate is unavailable.")
            desired_definition = CharacterDefinition.from_dict(dict(candidate_payload))
            review_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if self._audit_rows(review_digest):
                raise CharacterUpdateStaleError("Reviewed update was already used.")
        except CharacterUpdateStaleError:
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.REFUSED_STALE
            )
        except Exception:
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.FAILED
            )

        audit_metadata = {
            "source": "character_update_preview",
            "planner_version": reviewed.planner_version,
            "candidate_digest": reviewed.candidate_digest,
            "review_digest": review_digest,
            "state_impact": reviewed.state_impact,
            "operation_count": len(reviewed.operations),
        }
        try:
            result_record = self.coordinator.update(
                current.record,
                desired_definition,
                current.record.import_metadata,
                desired_state,
                expected_revision=reviewed.state_revision,
                updated_by_user_id=actor_user_id,
                operation_kind="character_update_apply",
                audit_event_type="character_update_applied",
                audit_actor_user_id=actor_user_id,
                audit_metadata=audit_metadata,
            )
        except BaseException:
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.UNCERTAIN,
                reviewed.candidate_digest,
            )

        try:
            if not self._readback_matches(
                current,
                result_record,
                before_state=evidence.exact_state,
                desired_state=desired_state,
                review_digest=review_digest,
                actor_user_id=actor_user_id,
            ):
                raise ValueError("Character update readback did not confirm the candidate.")
        except Exception:
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.UNCERTAIN,
                reviewed.candidate_digest,
            )
        return CharacterUpdateApplyResult(
            CharacterUpdateApplyClassification.CONFIRMED_APPLIED,
            reviewed.candidate_digest,
        )

    def _current_evidence(
        self,
        recompute: CharacterUpdateRecompute,
        *,
        actor_user_id: int,
        issued_at: int,
    ) -> _CurrentEvidence:
        record = recompute.record
        campaign_slug = record.definition.campaign_slug
        character_slug = record.definition.character_slug
        exact_state = self.state_store.get_exact_state(campaign_slug, character_slug)
        if exact_state is None:
            raise CharacterUpdateStaleError("Character state is unavailable.")
        if (
            exact_state.revision != record.state_record.revision
            or exact_state.state != record.state_record.state
        ):
            raise CharacterUpdateStaleError("Character state changed.")
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        definition_path, import_path = resolve_character_definition_import_paths(
            config.characters_dir,
            character_slug,
        )
        definition_bytes = definition_path.read_bytes()
        import_bytes = import_path.read_bytes()
        plan = recompute.plan
        candidate_digest = str(plan.digest or "")
        semantic_digest = canonical_digest(_semantic_rows_payload(plan.semantic_diff))
        claims = CharacterUpdateReviewClaims(
            actor_user_id=actor_user_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            operations=tuple(dict(item) for item in recompute.operations),
            definition_digest=hashlib.sha256(definition_bytes).hexdigest(),
            import_digest=hashlib.sha256(import_bytes).hexdigest(),
            state_revision=exact_state.revision,
            state_digest=exact_state.state_digest,
            state_updated_at=exact_state.updated_at,
            state_updated_by_user_id=exact_state.updated_by_user_id,
            source_digest=recompute.source_digest,
            policy_digest=recompute.policy_digest,
            native_digest=recompute.native_digest,
            planner_version=int(plan.version),
            state_impact=StateImpact(plan.state_impact).value,
            candidate_digest=candidate_digest,
            semantic_digest=semantic_digest,
            issued_at=issued_at,
        )
        _claims_payload(claims)
        return _CurrentEvidence(claims, exact_state)

    @staticmethod
    def _audit_rows(review_digest: str) -> list[object]:
        rows = get_db().execute(
            """
            SELECT actor_user_id, campaign_slug, character_slug, metadata_json
            FROM auth_audit_log
            WHERE event_type = 'character_update_applied'
              AND metadata_json LIKE ?
            ORDER BY id ASC
            """,
            (f'%"review_digest": "{review_digest}"%',),
        ).fetchall()
        return list(rows)

    def _readback_matches(
        self,
        recompute: CharacterUpdateRecompute,
        result_record: CharacterRecord,
        *,
        before_state: ExactCharacterState,
        desired_state: Mapping[str, Any],
        review_digest: str,
        actor_user_id: int,
    ) -> bool:
        plan = recompute.plan
        if (
            not _same(result_record.definition.to_dict(), plan.candidate_definition)
            or not _same(
                result_record.import_metadata.to_dict(),
                recompute.record.import_metadata.to_dict(),
            )
        ):
            return False
        after_state = self.state_store.get_exact_state(
            result_record.definition.campaign_slug,
            result_record.definition.character_slug,
        )
        if after_state is None or after_state.state != dict(desired_state):
            return False
        if StateImpact(plan.state_impact) is StateImpact.PRESERVE_EXACT:
            if after_state != before_state:
                return False
        elif (
            after_state.revision != before_state.revision + 1
            or after_state.updated_by_user_id != actor_user_id
        ):
            return False
        audit_rows = self._audit_rows(review_digest)
        if len(audit_rows) != 1:
            return False
        audit = audit_rows[0]
        if (
            int(audit["actor_user_id"]) != actor_user_id
            or str(audit["campaign_slug"]) != result_record.definition.campaign_slug
            or str(audit["character_slug"]) != result_record.definition.character_slug
        ):
            return False
        readback_rows = tuple(recompute.readback_semantic_rows(result_record))
        return canonical_digest(_semantic_rows_payload(readback_rows)) == canonical_digest(
            _semantic_rows_payload(plan.semantic_diff)
        )


__all__ = [
    "CharacterUpdateApplyClassification",
    "CharacterUpdateApplyEngine",
    "CharacterUpdateApplyResult",
    "CharacterUpdateRecompute",
    "CharacterUpdateReviewClaims",
    "CharacterUpdateReviewIssue",
    "CharacterUpdateStaleError",
    "CharacterUpdateTokenCodec",
    "CharacterUpdateTokenError",
    "MAX_BATCH_TOKEN_BYTES",
    "MAX_SINGLE_OPERATION_TOKEN_BYTES",
    "TOKEN_TTL_SECONDS",
    "canonical_digest",
]
