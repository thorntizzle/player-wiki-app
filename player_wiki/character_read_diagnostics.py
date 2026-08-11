from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
import math
import time
from typing import Iterator

from flask import current_app, g, request


CHARACTER_READ_COMPONENTS = (
    "access",
    "admission",
    "page-records",
    "readiness",
    "presentation",
    "catalogs",
    "managers",
    "template",
)
CHARACTER_READ_ROUTE_CLASSES = frozenset(
    {
        "character-document",
        "character-fetch",
        "session-character-document",
        "session-character-fragment",
    }
)
CHARACTER_READ_OUTCOMES = frozenset(
    {
        "pending",
        "ok",
        "redirect",
        "access-denied",
        "not-found",
        "admission-503",
        "client-error",
        "server-error",
    }
)
_DIAGNOSTICS_G_KEY = "character_read_diagnostics"


def classify_character_read_route(
    endpoint: str | None,
    *,
    fragment: str | None = None,
    requested_with: str | None = None,
) -> str | None:
    if endpoint == "character_read_view":
        if str(requested_with or "").strip().lower() == "xmlhttprequest":
            return "character-fetch"
        return "character-document"
    if endpoint != "campaign_session_character_view":
        return None
    if fragment == "1":
        return "session-character-fragment"
    return "session-character-document"


def _safe_milliseconds(value: object) -> float:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(milliseconds) or milliseconds < 0:
        return 0.0
    return milliseconds


def _safe_nonnegative_integer(value: object) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, integer)


@dataclass
class CharacterReadDiagnostics:
    route_class: str
    started_at: float
    access_started_at: float
    component_ms: dict[str, float] = field(
        default_factory=lambda: {component: 0.0 for component in CHARACTER_READ_COMPONENTS}
    )
    outcome: str = "pending"
    access_complete: bool = False

    def __post_init__(self) -> None:
        if self.route_class not in CHARACTER_READ_ROUTE_CLASSES:
            raise ValueError("Unsupported Character read route class.")

    @contextmanager
    def measure(self, component: str) -> Iterator[None]:
        if component not in self.component_ms:
            raise ValueError("Unsupported Character read timing component.")
        started_at = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000)
            self.component_ms[component] += elapsed_ms

    def mark_access_complete(self) -> None:
        if self.access_complete:
            return
        self.component_ms["access"] = max(
            0.0,
            (time.perf_counter() - self.access_started_at) * 1000,
        )
        self.access_complete = True

    def set_outcome(self, outcome: str) -> None:
        if outcome not in CHARACTER_READ_OUTCOMES:
            raise ValueError("Unsupported Character read outcome.")
        self.outcome = outcome


def initialize_character_read_diagnostics(
    *,
    request_started_at: float | None = None,
) -> CharacterReadDiagnostics | None:
    if not current_app.config.get("LIVE_DIAGNOSTICS", False):
        return None
    route_class = classify_character_read_route(
        request.endpoint,
        fragment=request.args.get("fragment"),
        requested_with=request.headers.get("X-Requested-With"),
    )
    if route_class is None:
        return None
    now = time.perf_counter()
    access_started_at = (
        request_started_at
        if isinstance(request_started_at, float) and math.isfinite(request_started_at)
        else now
    )
    diagnostics = CharacterReadDiagnostics(
        route_class=route_class,
        started_at=access_started_at,
        access_started_at=access_started_at,
    )
    setattr(g, _DIAGNOSTICS_G_KEY, diagnostics)
    return diagnostics


def get_character_read_diagnostics() -> CharacterReadDiagnostics | None:
    return getattr(g, _DIAGNOSTICS_G_KEY, None)


def mark_character_read_access_complete() -> None:
    diagnostics = get_character_read_diagnostics()
    if diagnostics is not None:
        diagnostics.mark_access_complete()


def measure_character_read_component(component: str):
    diagnostics = get_character_read_diagnostics()
    if diagnostics is None:
        return nullcontext()
    return diagnostics.measure(component)


def set_character_read_outcome(outcome: str) -> None:
    diagnostics = get_character_read_diagnostics()
    if diagnostics is not None:
        diagnostics.set_outcome(outcome)


def _response_outcome(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "ok"
    if 300 <= status_code < 400:
        return "redirect"
    if status_code in {401, 403}:
        return "access-denied"
    if status_code == 404:
        return "not-found"
    if 400 <= status_code < 500:
        return "client-error"
    return "server-error"


def attach_character_read_diagnostics(
    response,
    *,
    query_count: int = 0,
    db_time_ms: float = 0.0,
):
    diagnostics = get_character_read_diagnostics()
    if diagnostics is None:
        return response

    diagnostics.mark_access_complete()
    if diagnostics.outcome == "pending":
        diagnostics.set_outcome(_response_outcome(int(response.status_code or 0)))

    query_count = _safe_nonnegative_integer(query_count)
    query_time_ms = _safe_milliseconds(db_time_ms)
    response_bytes = _safe_nonnegative_integer(response.calculate_content_length())
    values = {
        **{
            component: _safe_milliseconds(diagnostics.component_ms.get(component, 0.0))
            for component in CHARACTER_READ_COMPONENTS
        },
        "db": query_time_ms,
        # Total is wall-clock request duration. Component spans may overlap and
        # are intentionally never summed to produce it.
        "total": max(0.0, (time.perf_counter() - diagnostics.started_at) * 1000),
    }
    server_timing = ", ".join(
        f"character-{component};dur={duration_ms:.2f}"
        for component, duration_ms in values.items()
    )
    existing_server_timing = response.headers.get("Server-Timing", "").strip()
    response.headers["Server-Timing"] = (
        f"{existing_server_timing}, {server_timing}"
        if existing_server_timing
        else server_timing
    )
    response.headers["X-Character-Read-Route"] = diagnostics.route_class
    response.headers["X-Character-Read-Outcome"] = diagnostics.outcome
    response.headers["X-Character-Read-Query-Count"] = str(query_count)
    response.headers["X-Character-Read-Query-Time-Ms"] = f"{query_time_ms:.2f}"
    response.headers["X-Character-Read-Response-Bytes"] = str(response_bytes)
    for component, duration_ms in values.items():
        header_component = component.title().replace("-", "-")
        response.headers[f"X-Character-Read-{header_component}-Ms"] = f"{duration_ms:.2f}"
    return response
