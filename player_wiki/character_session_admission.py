from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character_models import CharacterRecord


class CharacterSessionAdmissionError(PermissionError):
    """A context cannot authorize this request's mutation."""


@dataclass(frozen=True, slots=True)
class LoadedCharacterSessionContext:
    """Reusable target context with no actor or mutation authority."""

    campaign_slug: str
    character_slug: str
    campaign: Any
    record: CharacterRecord


def validate_loaded_context(context, campaign_slug: str, character_slug: str):
    if (
        not isinstance(context, (LoadedCharacterSessionContext, CharacterSessionAdmission))
        or context.campaign_slug != campaign_slug
        or context.character_slug != character_slug
        or context.campaign.slug != campaign_slug
        or context.record.definition.campaign_slug != campaign_slug
        or context.record.definition.character_slug != character_slug
        or context.record.state_record.campaign_slug != campaign_slug
        or context.record.state_record.character_slug != character_slug
    ):
        raise CharacterSessionAdmissionError("Character context target mismatch.")
    return context.campaign, context.record


@dataclass(frozen=True, slots=True)
class CharacterSessionAdmission:
    """Server-issued context; possession alone does not authorize execution.

    The application verifies issuance, the concrete request and all target/actor
    identities before using it. The same admission can construct the response
    after its one mutation attempt, but cannot authorize another attempt.
    """

    campaign_slug: str
    character_slug: str
    campaign: Any
    record: CharacterRecord
    user_id: int
    request_identity: object


def issue_session_admission(
    context: LoadedCharacterSessionContext, *, request_identity: object,
    user_id: int | None, previous_admission: CharacterSessionAdmission | None,
) -> CharacterSessionAdmission:
    if (
        user_id is None
        or (previous_admission is not None and previous_admission.request_identity is request_identity)
    ):
        raise CharacterSessionAdmissionError("Character admission already issued or actor unavailable.")
    validate_loaded_context(context, context.campaign_slug, context.character_slug)
    return CharacterSessionAdmission(
        campaign_slug=context.campaign_slug,
        character_slug=context.character_slug,
        campaign=context.campaign,
        record=context.record,
        user_id=user_id,
        request_identity=request_identity,
    )


def validate_session_admission(
    admission: CharacterSessionAdmission, campaign_slug: str, character_slug: str,
    *, request_identity: object, user_id: int | None,
    issuance_state: Any, consume: bool = False,
):
    """Validate exact issuance; consumption precedes every mutation attempt.

    issuance_state explicitly owns the current request's pointer and consumed
    flag. Flask's request-local g is one adapter; standalone callers can inject
    an ordinary object with the same two attributes.
    """
    if (
        not isinstance(admission, CharacterSessionAdmission)
        or getattr(issuance_state, "character_session_admission", None) is not admission
        or admission.request_identity is not request_identity
        or user_id is None
        or user_id != admission.user_id
    ):
        raise CharacterSessionAdmissionError("Character admission binding mismatch.")
    campaign, record = validate_loaded_context(admission, campaign_slug, character_slug)
    if consume:
        if getattr(issuance_state, "character_session_mutation_started", False):
            raise CharacterSessionAdmissionError("Character admission already consumed.")
        issuance_state.character_session_mutation_started = True
    return campaign, record
