from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .session_presenter import format_session_timestamp


READINESS_STATES = (
    "ready",
    "needs review",
    "not configured",
    "unavailable",
    "not applicable",
)


@dataclass(frozen=True, slots=True)
class SessionReadinessRow:
    slug: str
    title: str
    state: str
    detail: str
    action: str
    href: str

    def __post_init__(self) -> None:
        if self.state not in READINESS_STATES:
            raise ValueError("Invalid Session readiness state.")


def present_bounded_count(value: int) -> str:
    count = max(0, int(value))
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count >= 26:
        return "25+"
    return "2-25"


def present_active_session(
    started_at: datetime | None,
    *,
    href: str,
) -> SessionReadinessRow:
    return SessionReadinessRow(
        slug="active-session",
        title="Active Session",
        state="ready" if started_at is not None else "not configured",
        detail=(
            f"Started {format_session_timestamp(started_at)}."
            if started_at is not None
            else "No active Session is configured."
        ),
        action="Open Session controls",
        href=href,
    )


def present_session_characters(
    *,
    available_count: int,
    valid_assignment_count: int,
    has_dangling_assignments: bool,
    href: str,
) -> SessionReadinessRow:
    available = max(0, int(available_count))
    valid = max(0, int(valid_assignment_count))
    if has_dangling_assignments or (available > 0 and valid == 0):
        state = "needs review"
    elif valid > 0:
        state = "ready"
    else:
        state = "not configured"
    detail = f"Available Characters: {available}. Valid assignments: {valid}."
    if has_dangling_assignments:
        detail += " One or more assignments need review."
    return SessionReadinessRow(
        slug="session-characters",
        title="Session Characters",
        state=state,
        detail=detail,
        action="Open Session Characters",
        href=href,
    )


def present_session_content(
    *,
    staged_count: int,
    revealed_count: int,
    href: str,
) -> SessionReadinessRow:
    if int(revealed_count) > 0:
        state = "needs review"
    elif int(staged_count) > 0:
        state = "ready"
    else:
        state = "not configured"
    return SessionReadinessRow(
        slug="session-content",
        title="Session content",
        state=state,
        detail=(
            f"Staged: {present_bounded_count(staged_count)}. "
            f"Revealed: {present_bounded_count(revealed_count)}."
        ),
        action="Open Session content",
        href=href,
    )


def present_source_health(*, report_state: str, complete: bool, href: str) -> SessionReadinessRow:
    normalized = str(report_state or "").strip()
    if normalized == "healthy" and complete:
        state = "ready"
    elif normalized in {"findings", "partial", "report_stale"} or (
        normalized == "healthy" and not complete
    ):
        state = "needs review"
    elif normalized == "empty":
        state = "not applicable"
    else:
        state = "unavailable"
    return SessionReadinessRow(
        slug="source-health",
        title="Source Health",
        state=state,
        detail="Open the bounded first-page report for advisory source details.",
        action="Open Source Health",
        href=href,
    )


def present_encounter_presets(*, count: int, supported: bool, href: str) -> SessionReadinessRow:
    if not supported:
        state = "not applicable"
        detail = "This campaign does not support Combat."
    else:
        parsed_count = max(0, int(count))
        state = "ready" if parsed_count > 0 else "not configured"
        detail = f"Saved presets: {present_bounded_count(parsed_count)}."
    return SessionReadinessRow(
        slug="encounter-presets",
        title="Encounter Presets",
        state=state,
        detail=detail,
        action="Open Encounter Presets",
        href=href,
    )


def unavailable_row(*, slug: str, title: str, action: str, href: str) -> SessionReadinessRow:
    return SessionReadinessRow(
        slug=slug,
        title=title,
        state="unavailable",
        detail="This check could not be completed. Open its owning workflow to review it.",
        action=action,
        href=href,
    )
