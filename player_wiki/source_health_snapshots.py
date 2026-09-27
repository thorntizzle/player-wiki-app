"""Bounded, process-local Source Health browser reports.

The kernel still owns inventory and classification. This owner keeps only
immutable safe presentation bytes after a complete bounded collection, never
definitions, state, or the transient kernel continuation chain.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import math
import re
import secrets
from threading import Lock
import time
from typing import Callable

from .source_health import (
    SOURCE_HEALTH_ACTION_LABELS,
    SOURCE_HEALTH_CLASSIFICATION_LABELS,
    SOURCE_HEALTH_FINDING_LIMIT,
    SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES,
    SOURCE_HEALTH_SEVERITIES,
    SourceHealthCursorError,
    SourceHealthDenied,
    SourceHealthReport,
    present_source_health_report,
    serialize_source_health_report,
    source_health_action_destination,
)

TTL_SECONDS = 600
HANDLE_MAX_BYTES = 512
BUILD_CALL_LIMIT = 24
BUILD_CHECK_LIMIT = 1_000
REPORT_MAX_BYTES = 1_048_576
STORE_MAX_BYTES = 16 * REPORT_MAX_BYTES
BUILD_QUERY_LIMIT = 512
BUILD_SECONDS = 10
_HEX = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"shs1\.([0-9a-f]{32})\.([0-9]{1,2})\.([0-9]{1,12})\.([A-Za-z0-9_-]{43})")


class SourceHealthSnapshotUnavailable(ValueError):
    """Sanitized failure; an old handle must never trigger a replacement build."""


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshotContext:
    binding: str
    actor: str
    campaign: str

    def __post_init__(self) -> None:
        if any(type(value) is not str or _HEX.fullmatch(value) is None
               for value in (self.binding, self.actor, self.campaign)):
            raise SourceHealthSnapshotUnavailable()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode("utf-8")


def _bounded_text(value: object, limit: int) -> str:
    if type(value) is not str or len(value) > limit:
        raise SourceHealthSnapshotUnavailable()
    return value


def _safe_rows(rows: object, campaign_slug: str) -> list[dict[str, object]]:
    """Allowlist and reapply sink policy on collection and selected-page decode."""
    if not isinstance(rows, (tuple, list)) or len(rows) > SOURCE_HEALTH_FINDING_LIMIT:
        raise SourceHealthSnapshotUnavailable()
    safe = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "classification", "classification_label", "severity", "consumer",
            "target", "action", "action_label", "destination",
        }:
            raise SourceHealthSnapshotUnavailable()
        classification = row["classification"]
        action = row["action"]
        if (type(classification) is not str or classification not in SOURCE_HEALTH_CLASSIFICATION_LABELS
                or type(action) is not str or action not in SOURCE_HEALTH_ACTION_LABELS
                or row["severity"] not in SOURCE_HEALTH_SEVERITIES
                or row["classification_label"] != SOURCE_HEALTH_CLASSIFICATION_LABELS[classification]
                or row["action_label"] != SOURCE_HEALTH_ACTION_LABELS[action]):
            raise SourceHealthSnapshotUnavailable()
        consumer = row["consumer"]
        if not isinstance(consumer, dict) or set(consumer) != {"type", "key", "surface"}:
            raise SourceHealthSnapshotUnavailable()
        consumer = {key: _bounded_text(consumer[key], limit)
                    for key, limit in (("type", 48), ("key", 160), ("surface", 64))}
        target = row["target"]
        if target is not None:
            # The kernel presenter also supplies source_id; omit it from custody.
            if not isinstance(target, dict) or set(target) not in (
                    {"kind", "identity", "type", "source_id"}, {"kind", "identity", "type"}):
                raise SourceHealthSnapshotUnavailable()
            target = {key: _bounded_text(target[key], limit)
                      for key, limit in (("kind", 48), ("identity", 192), ("type", 48))}
        destination = _bounded_text(row["destination"], 256)
        if classification == "inaccessible":
            target, action, destination = None, "none", ""
        else:
            destination = source_health_action_destination(campaign_slug, action, destination)
        safe.append({
            "classification": classification,
            "classification_label": SOURCE_HEALTH_CLASSIFICATION_LABELS[classification],
            "severity": row["severity"], "consumer": consumer, "target": target,
            "action": action, "action_label": SOURCE_HEALTH_ACTION_LABELS[action],
            "destination": destination,
        })
    return safe


def _advance_cursor(previous: dict | None, current: object, row_count: int) -> dict:
    """Check the existing authenticated kernel sequence without retaining it.

    The codec validates the kernel schema; this adds replay-window and
    monotonic outcome/exhaustion checks across the bounded collection.
    """
    if not isinstance(current, dict):
        raise SourceHealthSnapshotUnavailable()
    window = current["window"]
    old_window = previous["window"] if previous else None
    if window is not None:
        if row_count != 50 or window["offset"] != (old_window["offset"] if old_window else 0) + 50:
            raise SourceHealthSnapshotUnavailable()
        if old_window and any(window[key] != old_window[key] for key in ("digest", "count")):
            raise SourceHealthSnapshotUnavailable()
        if previous and current["adapters"] != previous["adapters"]:
            raise SourceHealthSnapshotUnavailable()
    elif old_window and row_count != old_window["count"] - old_window["offset"]:
        raise SourceHealthSnapshotUnavailable()
    if previous:
        for key in ("saw_any_consumer", "saw_nonhealthy"):
            if previous["outcome"][key] and not current["outcome"][key]:
                raise SourceHealthSnapshotUnavailable()
        for before, after in zip(previous["adapters"], current["adapters"], strict=True):
            if before["exhausted"] and before != after:
                raise SourceHealthSnapshotUnavailable()
        # Outcome flags alone cannot constitute progress through inventory.
        if current["adapters"] == previous["adapters"] and current["window"] == previous["window"]:
            raise SourceHealthSnapshotUnavailable()
    return current


def unavailable_source_health_view() -> dict[str, object]:
    return {
        "state": "error", "state_label": "Source Health unavailable",
        "message": "This report is unavailable, expired, or could not finish within its limits. Refresh the report to retry.",
        "findings": [], "total": None, "generation_utc": "",
        "page_number": 0, "page_count": 0, "range_start": 0, "range_end": 0,
        "previous_continuation": "", "next_continuation": "", "first_continuation": "",
    }


@dataclass(frozen=True, slots=True)
class _Snapshot:
    context: SourceHealthSnapshotContext
    pages: tuple[bytes, ...]
    metadata: bytes
    size: int
    expires_monotonic: float
    expires_signed: int


class SourceHealthSnapshotService:
    def __init__(self, *, signing_key: bytes, authorize: Callable,
                 build_report: Callable, validate_continuation: Callable,
                 query_count: Callable[[], int]) -> None:
        if len(signing_key) < 16:
            raise ValueError("Source Health snapshot key is unavailable.")
        self._key = bytes(signing_key)
        self._authorize = authorize
        self._build_report = build_report
        self._validate_continuation = validate_continuation
        self._query_count = query_count
        self._lock = Lock()
        self._snapshots: dict[str, _Snapshot] = {}
        self._reservations: set[SourceHealthSnapshotContext] = set()
        self._bytes = 0

    def identity(self, purpose: str, value: object) -> str:
        """Opaque keyed context/quota identity; no raw actors or campaign data stored."""
        return hmac.new(self._key, purpose.encode("ascii") + b"\0" + _json_bytes(value), sha256).hexdigest()

    def _current_context(self, campaign_slug: str) -> SourceHealthSnapshotContext:
        context = self._authorize(campaign_slug)
        if context is None:
            raise SourceHealthDenied()
        if not isinstance(context, SourceHealthSnapshotContext):
            raise SourceHealthSnapshotUnavailable()
        return context

    def _remove(self, report_id: str) -> None:
        self._bytes -= self._snapshots.pop(report_id).size

    def _expire(self, now: float) -> None:
        for report_id, snapshot in tuple(self._snapshots.items()):
            if snapshot.expires_monotonic <= now:
                self._remove(report_id)

    def _evict(self, context: SourceHealthSnapshotContext, size: int) -> None:
        # Insertion order is successful-publication order; reads never renew it.
        for key, cap in (("actor", 2), ("campaign", 4)):
            matching = [report_id for report_id, snapshot in self._snapshots.items()
                        if getattr(snapshot.context, key) == getattr(context, key)]
            while len(matching) >= cap:
                self._remove(matching.pop(0))
        while self._snapshots and (len(self._snapshots) >= 16 or self._bytes + size > STORE_MAX_BYTES):
            self._remove(next(iter(self._snapshots)))

    def _reserve(self, context: SourceHealthSnapshotContext) -> None:
        with self._lock:
            self._expire(time.monotonic())
            if (len(self._reservations) >= 2 or any(
                    item.actor == context.actor or item.campaign == context.campaign
                    for item in self._reservations)):
                raise SourceHealthSnapshotUnavailable()
            # A rejected build must not destroy a previously usable report.
            # Completed-state quotas are enforced only on publication.
            self._reservations.add(context)

    def _check_budget(self, start: float, initial_queries: int) -> None:
        current_queries = self._query_count()
        if (time.monotonic() - start >= BUILD_SECONDS
                or type(current_queries) is not int
                or current_queries < initial_queries
                or current_queries - initial_queries > BUILD_QUERY_LIMIT):
            raise SourceHealthSnapshotUnavailable()

    def _handle(self, report_id: str, page: int, snapshot: _Snapshot) -> str:
        body = f"shs1.{report_id}.{page}.{snapshot.expires_signed}"
        signature = hmac.new(self._key, body.encode("ascii") + b"\0" + snapshot.context.binding.encode("ascii"), sha256).digest()
        token = body + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        if len(token) > HANDLE_MAX_BYTES:
            raise SourceHealthSnapshotUnavailable()
        return token

    def _parse_handle(self, token: str, context: SourceHealthSnapshotContext) -> tuple[str, int, int]:
        if type(token) is not str or len(token.encode("utf-8")) > HANDLE_MAX_BYTES:
            raise SourceHealthCursorError("Invalid Source Health handle.")
        match = _TOKEN.fullmatch(token)
        if match is None:
            raise SourceHealthCursorError("Invalid Source Health handle.")
        report_id, page_text, expiry_text, supplied = match.groups()
        page, expiry = int(page_text), int(expiry_text)
        if str(page) != page_text or str(expiry) != expiry_text or page >= 20:
            raise SourceHealthCursorError("Invalid Source Health handle.")
        body = token.rsplit(".", 1)[0]
        expected = base64.urlsafe_b64encode(hmac.new(
            self._key, body.encode("ascii") + b"\0" + context.binding.encode("ascii"), sha256,
        ).digest()).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(supplied, expected):
            raise SourceHealthCursorError("Invalid Source Health handle.")
        if time.time() >= expiry:
            raise SourceHealthSnapshotUnavailable()
        return report_id, page, expiry

    def _view(self, report_id: str, snapshot: _Snapshot, page: int, campaign_slug: str) -> dict[str, object]:
        if not 0 <= page < len(snapshot.pages):
            raise SourceHealthSnapshotUnavailable()
        rows = _safe_rows(json.loads(snapshot.pages[page]), campaign_slug)
        metadata = json.loads(snapshot.metadata)
        total = metadata["total"]
        return {
            **metadata, "findings": rows, "page_number": page + 1,
            "page_count": len(snapshot.pages), "range_start": page * 50 + 1 if total else 0,
            "range_end": page * 50 + len(rows),
            "previous_continuation": self._handle(report_id, page - 1, snapshot) if page else "",
            "next_continuation": self._handle(report_id, page + 1, snapshot) if page + 1 < len(snapshot.pages) else "",
            "first_continuation": self._handle(report_id, 0, snapshot) if page else "",
        }

    def open_report(self, campaign_slug: str, *, continuation_loader: Callable[[], str]) -> dict[str, object]:
        start, initial_queries = time.monotonic(), self._query_count()
        context = self._current_context(campaign_slug)  # Before grammar, authentication, or storage lookup.
        continuation = continuation_loader()
        if continuation:
            report_id, page, expiry = self._parse_handle(continuation, context)
            with self._lock:
                self._expire(time.monotonic())
                snapshot = self._snapshots.get(report_id)
            if (snapshot is None or snapshot.context != context or snapshot.expires_signed != expiry):
                raise SourceHealthSnapshotUnavailable()
            return self._view(report_id, snapshot, page, campaign_slug)
        self._check_budget(start, initial_queries)
        self._reserve(context)
        try:
            return self._collect(campaign_slug, context, start, initial_queries)
        finally:
            with self._lock:
                self._reservations.discard(context)

    def _collect(self, campaign_slug: str, context: SourceHealthSnapshotContext,
                 start: float, initial_queries: int) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        row_bytes = 0
        seen_cursors: set[str] = set()
        continuation = ""
        cursor_state = None
        final_state = ""
        definition_count = definition_bytes = 0
        for _call in range(BUILD_CALL_LIMIT):
            self._check_budget(start, initial_queries)
            report = self._build_report(campaign_slug, continuation=continuation)
            self._check_budget(start, initial_queries)
            if (not isinstance(report, SourceHealthReport) or report.campaign_slug != campaign_slug
                    or type(report.complete) is not bool
                    or report.state not in {"partial", "empty", "healthy", "findings"}
                    or (report.complete != (report.state != "partial"))):
                raise SourceHealthSnapshotUnavailable()
            serialize_source_health_report(report)  # Preserve the original per-call JSON cap.
            measurements = report.measurements
            if (type(measurements.definition_file_count) is not int
                    or type(measurements.definition_bytes) is not int
                    or not 0 <= measurements.definition_file_count <= 50
                    or not 0 <= measurements.definition_bytes <= 8_388_608):
                raise SourceHealthSnapshotUnavailable()
            definition_count += measurements.definition_file_count
            definition_bytes += measurements.definition_bytes
            if definition_count > 1_200 or definition_bytes > 201_326_592:
                raise SourceHealthSnapshotUnavailable()
            safe = _safe_rows(present_source_health_report(report, campaign_slug=campaign_slug)["findings"], campaign_slug)
            row_bytes += len(_json_bytes(safe))
            if len(rows) + len(safe) > BUILD_CHECK_LIMIT or row_bytes > REPORT_MAX_BYTES:
                raise SourceHealthSnapshotUnavailable()
            rows.extend(safe)
            if report.complete:
                if report.continuations or (cursor_state and cursor_state["window"] is not None
                        and len(safe) != cursor_state["window"]["count"] - cursor_state["window"]["offset"]):
                    raise SourceHealthSnapshotUnavailable()
                final_state = report.state
                break
            if len(report.continuations) != 1 or type(report.continuations[0]) is not str:
                raise SourceHealthSnapshotUnavailable()
            next_cursor = report.continuations[0]
            decoded = self._validate_continuation(next_cursor, campaign_slug=campaign_slug)
            cursor_state = _advance_cursor(cursor_state, decoded, len(safe))
            digest = sha256(next_cursor.encode("utf-8")).hexdigest()
            if not next_cursor or next_cursor == continuation or digest in seen_cursors:
                raise SourceHealthSnapshotUnavailable()
            seen_cursors.add(digest)
            continuation = next_cursor
        else:
            raise SourceHealthSnapshotUnavailable()
        nonhealthy = any(row["classification"] != "healthy" for row in rows)
        expected_state = "empty" if not rows else "findings" if nonhealthy else "healthy"
        if final_state != expected_state:
            raise SourceHealthSnapshotUnavailable()
        pages = tuple(_json_bytes(rows[offset:offset + 50]) for offset in range(0, len(rows), 50)) or (b"[]",)
        if any(len(page) > SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES for page in pages):
            raise SourceHealthSnapshotUnavailable()
        metadata = _json_bytes({
            "state": expected_state,
            "state_label": {"empty": "No reference checks", "healthy": "All generated checks are healthy", "findings": "Checks need attention"}[expected_state],
            "message": "This report shows reference checks collected when it was generated. Refresh to check later changes.",
            "generation_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total": len(rows),
        })
        size = len(metadata) + sum(map(len, pages))
        if size > REPORT_MAX_BYTES:
            raise SourceHealthSnapshotUnavailable()
        report_id = secrets.token_hex(16)
        # Check every prospective browser page before retaining any report.
        # Navigation and metadata count toward the original JSON page ceiling.
        preview = _Snapshot(context, pages, metadata, size, 0, math.ceil(time.time() + TTL_SECONDS))
        for page in range(len(pages)):
            validate_source_health_view(self._view(report_id, preview, page, campaign_slug), campaign_slug)
        if self._current_context(campaign_slug) != context:
            raise SourceHealthSnapshotUnavailable()
        self._check_budget(start, initial_queries)
        with self._lock:
            # Check again after lock acquisition: collection must never publish late.
            self._check_budget(start, initial_queries)
            now = time.monotonic()
            self._expire(now)
            if report_id in self._snapshots:
                raise SourceHealthSnapshotUnavailable()
            self._evict(context, size)
            snapshot = _Snapshot(context, pages, metadata, size, now + TTL_SECONDS, math.ceil(time.time() + TTL_SECONDS))
            self._snapshots[report_id] = snapshot
            self._bytes += size
        return self._view(report_id, snapshot, 0, campaign_slug)


def validate_source_health_view(view: object, campaign_slug: str) -> dict[str, object]:
    """Bound the final browser view, even when an injected owner is malformed."""
    fallback = unavailable_source_health_view()
    if not isinstance(view, dict) or set(view) != set(fallback):
        raise SourceHealthSnapshotUnavailable()
    if view["state"] == "error":
        return fallback
    if view["state"] not in {"empty", "healthy", "findings"}:
        raise SourceHealthSnapshotUnavailable()
    total, page, count = view["total"], view["page_number"], view["page_count"]
    if (any(type(value) is not int for value in (total, page, count, view["range_start"], view["range_end"]))
            or not 0 <= total <= BUILD_CHECK_LIMIT or count != max(1, (total + 49) // 50)
            or not 1 <= page <= count):
        raise SourceHealthSnapshotUnavailable()
    rows = _safe_rows(view["findings"], campaign_slug)
    expected_rows = min(50, max(0, total - (page - 1) * 50))
    if (len(rows) != expected_rows or view["range_start"] != ((page - 1) * 50 + 1 if total else 0)
            or view["range_end"] != (page - 1) * 50 + expected_rows
            or (view["state"] == "empty") != (total == 0)):
        raise SourceHealthSnapshotUnavailable()
    for key, limit in (("state_label", 80), ("message", 256), ("generation_utc", 32)):
        _bounded_text(view[key], limit)
    for key, required in (("previous_continuation", page > 1), ("first_continuation", page > 1), ("next_continuation", page < count)):
        token = _bounded_text(view[key], HANDLE_MAX_BYTES)
        if bool(token) != required or (token and _TOKEN.fullmatch(token) is None):
            raise SourceHealthSnapshotUnavailable()
    result = {**view, "findings": rows}
    if len(_json_bytes(result)) > SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES:
        raise SourceHealthSnapshotUnavailable()
    return result
