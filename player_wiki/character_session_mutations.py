from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .character_session_admission import CharacterSessionAdmission, validate_session_admission


@dataclass(frozen=True, slots=True)
class CharacterSessionMutationOutcome:
    kind: str
    response: Any = None
    error: Exception | None = None


def parse_session_expected_revision(raw_value: str) -> int:
    raw_value = raw_value.strip()
    if not raw_value:
        raise ValueError("Missing sheet revision. Refresh the page and try again.")
    return int(raw_value)


def execute_character_session_mutation(
    campaign_slug: str, character_slug: str, *,
    admission: CharacterSessionAdmission, request_identity: object,
    user_id: int | None, issuance_state: Any, raw_expected_revision: str,
    active_session_decision: Callable[[], Any], action: Callable[..., Any],
) -> CharacterSessionMutationOutcome:
    """Consume, decide, validate, dispatch once, and classify known outcomes.

    Access and HTTP responses remain adapter responsibilities. Unexpected
    exceptions propagate: a persistence or commit failure proves neither a
    rollback nor safe replay, and response/invalidation work is outside this
    exception boundary just as it is in the route adapter.
    """
    _, record = validate_session_admission(
        admission, campaign_slug, character_slug,
        request_identity=request_identity, user_id=user_id,
        issuance_state=issuance_state, consume=True,
    )
    inactive_response = active_session_decision()
    if inactive_response is not None:
        return CharacterSessionMutationOutcome("inactive", response=inactive_response)
    try:
        expected_revision = parse_session_expected_revision(raw_expected_revision)
        action(record, expected_revision, user_id)
    except CharacterStateConflictError as exc:
        return CharacterSessionMutationOutcome("conflict", error=exc)
    except (CharacterStateValidationError, ValueError) as exc:
        return CharacterSessionMutationOutcome("invalid", error=exc)
    return CharacterSessionMutationOutcome("success")
