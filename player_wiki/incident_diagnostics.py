"""Privacy-bounded incident events. Never accept request-derived text as a field."""

from __future__ import annotations

from functools import wraps
import json
import re
import secrets
import time
from typing import Any, Callable

from flask import current_app, g, has_request_context, request


_EVENTS = {"request_start", "request_outcome", "request_exception", "access_decision", "operation_outcome"}
_OPERATIONS = {"http_request", "http_mutation", "wiki_publication", "wiki_deletion", "wiki_recovery", "character_update_apply"}
_DECISIONS = {"allow", "deny", "redirect", "refused", "completed", "confirmed", "unchanged", "uncertain", "failed", "recovered", "pending"}
_REASONS = {"none", "authentication_required", "forbidden", "hidden", "missing", "stale", "conflict", "error", "incomplete"}
_SCOPES = {"none", "campaign", "wiki", "systems", "session", "combat", "dm_content", "admin", "content", "source", "entry", "visibility"}
_ROLES = {"unknown", "anonymous", "admin", "dm", "player", "member"}
_VISIBILITIES = {"unknown", "public", "private", "players", "dm"}
_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}


def _category() -> str:
    endpoint = request.endpoint or ""
    if endpoint.startswith("api.") or endpoint.startswith("api_"):
        return "api"
    if endpoint in {"static", "campaign_asset", "character_portrait_asset", "campaign_session_article_image"}:
        return "asset"
    if endpoint in {"livez", "readyz", "healthz"}:
        return "health"
    if endpoint.startswith("campaign_"):
        return "campaign"
    if endpoint.startswith("character_"):
        return "character"
    if endpoint.startswith("admin_"):
        return "admin"
    return "other"


def _number(value: Any, maximum: int = 1_000_000) -> int:
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def emit_incident(
    event: str,
    *,
    operation: str = "http_request",
    decision: str | None = None,
    reason: str | None = None,
    scope: str | None = None,
    role: str | None = None,
    visibility: str | None = None,
    status: int | None = None,
    counts: dict[str, Any] | None = None,
) -> None:
    """Best effort: malformed inputs and logger failures cannot change a request."""
    try:
        if not has_request_context() or not current_app.config.get("INCIDENT_DIAGNOSTICS_ENABLED", True):
            return
        if event not in _EVENTS or operation not in _OPERATIONS:
            return
        request_id = getattr(g, "incident_request_id", None)
        if not isinstance(request_id, str) or re.fullmatch(r"[0-9a-f]{24}", request_id) is None:
            request_id = secrets.token_hex(12)
            g.incident_request_id = request_id
        from .db import get_db_query_metrics

        metrics = get_db_query_metrics()
        started = getattr(g, "incident_started_at", None)
        duration = (time.perf_counter() - started) * 1000 if isinstance(started, float) else 0
        payload: dict[str, Any] = {
            "schema": "incident_event_v1",
            "event": event,
            "request_id": request_id,
            "endpoint_category": _category(),
            "operation": operation,
            "method": request.method if request.method in _METHODS else "OTHER",
            "duration_ms": _number(duration, 86_400_000),
            "db_query_count": _number(metrics.get("query_count")),
            "db_write_count": _number(metrics.get("write_count")),
            "db_commit_count": _number(metrics.get("commit_count")),
            "db_rollback_count": _number(metrics.get("rollback_count")),
        }
        if status is not None:
            payload["status"] = _number(status, 599)
        for key, value, allowed in (
            ("decision", decision, _DECISIONS),
            ("reason", reason, _REASONS),
            ("scope", scope, _SCOPES),
            ("role", role, _ROLES),
            ("visibility", visibility, _VISIBILITIES),
        ):
            if value is not None:
                payload[key] = value if value in allowed else "unknown" if "unknown" in allowed else "none"
        if counts:
            for key in ("recovered", "aborted", "conflict", "pending"):
                if key in counts:
                    payload[key] = _number(counts[key])
        current_app.logger.warning("incident_event_v1 %s", json.dumps(payload, sort_keys=True, separators=(",", ":")))
    except Exception:
        return


def access_decision(decision: str, reason: str = "none", *, scope: str = "none", visibility: str = "unknown", role: str = "unknown") -> None:
    if role == "unknown" and reason == "authentication_required":
        role = "anonymous"
    emit_incident("access_decision", operation="http_request", decision=decision, reason=reason, scope=scope, visibility=visibility, role=role)


def diagnose_operation(operation: str) -> Callable:
    """Report named outcomes without exposing the result or an exception."""
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            try:
                result = view(*args, **kwargs)
            except BaseException as exc:
                wiki_operation = operation in {"wiki_publication", "wiki_deletion"}
                exception_name = type(exc).__name__
                preflight_conflict = wiki_operation and exception_name == "PlayerWikiCreateConflict"
                reconciliation_conflict = wiki_operation and exception_name == "PlayerWikiReconciliationConflict"
                emit_incident("operation_outcome", operation=operation,
                              decision="refused" if preflight_conflict else "uncertain",
                              reason="conflict" if preflight_conflict or reconciliation_conflict else "error")
                raise
            if operation == "character_update_apply":
                classification = str(getattr(getattr(result, "classification", None), "value", ""))
                decision = {
                    "confirmed_applied": "confirmed",
                    "unchanged": "unchanged",
                    "refused_stale": "refused",
                    "failed": "failed",
                    "uncertain": "uncertain",
                }.get(classification, "failed")
                reason = "stale" if classification == "refused_stale" else "none"
            else:
                decision, reason = "confirmed", "none"
            emit_incident("operation_outcome", operation=operation, decision=decision, reason=reason)
            return result
        return wrapped
    return decorator
