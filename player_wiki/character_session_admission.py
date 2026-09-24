from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character_models import CharacterRecord


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
