"""Committed-source validation and bounded closed-mode legacy admission.

Admission accepts caller-supplied bytes and an existing SQLite connection; it
never scans campaign files or activates authority. Activated publication owns
its separate transaction path in committed_publication.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

import yaml

from .campaign_page_refresh import build_page_payload, normalize_page_ref
from .models import is_deprecated_wiki_identity
from .repository import parse_frontmatter
from .system_policy import KNOWN_SYSTEM_CODES, normalize_system_code


_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_CAMPAIGN_SLUG = re.compile(r"[a-z0-9-]{1,128}\Z")
_CHARACTER_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}\Z")
_BLOCK_CODES = frozenset({
    "missing_primary", "missing_import", "malformed_primary", "malformed_import",
    "ownership_mismatch", "system_mismatch", "config_not_admitted",
    "page_row_missing", "page_not_published", "page_row_mismatch",
    "page_not_eligible", "page_deprecated", "page_reveal_pending",
    "pending_journal", "mirror_conflict", "existing_generation",
    "legacy_enum_invalid", "oversize_primary", "oversize_import",
    "schema_unavailable",
})


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    status: str
    reason_code: str
    revision: int | None


@dataclass(frozen=True, slots=True)
class _ValidatedConfig:
    system_code: str
    current_session: int
    character_dir: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _receipt_digest(kind: str, primary: bytes, secondary: bytes | None) -> str:
    digest = hashlib.sha256()
    for value in (kind.encode("ascii"), primary, secondary or b""):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _decode_mapping(value: bytes) -> dict[str, Any] | None:
    try:
        parsed = yaml.safe_load(value.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError, ValueError, OverflowError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _legacy_enum_values_valid(connection: sqlite3.Connection) -> bool:
    # Historical ALTER TABLE variants lack these three baseline CHECK predicates.
    checks = (
        ("user_preferences", "session_chat_order", ("newest_first", "oldest_first")),
        ("user_preferences", "frontend_mode", ("flask", "gen2")),
        ("campaign_combatants", "source_kind",
         ("character", "manual_npc", "dm_statblock", "systems_monster")),
    )
    try:
        for table, column, allowed in checks:
            placeholders = ",".join("?" for _ in allowed)
            row = connection.execute(
                f"SELECT 1 FROM {table} WHERE {column} IS NULL "
                f"OR {column} NOT IN ({placeholders}) LIMIT 1", allowed
            ).fetchone()
            if row is not None:
                return False
    except sqlite3.Error:
        return False
    return True


def _validated_character_dir(value: object) -> str | None:
    """Check the Character mirror's relative root without consulting the filesystem."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or path.as_posix() == "."
            or ".." in path.parts):
        return None
    return value


def _validate_config_payload(
    payload: dict[str, Any] | None, campaign_slug: str,
) -> tuple[str | None, _ValidatedConfig | None]:
    if payload is None:
        return "malformed_primary", None
    if payload.get("slug") != campaign_slug:
        return "ownership_mismatch", None
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return "malformed_primary", None
    system = payload.get("system")
    if not isinstance(system, str):
        return "system_mismatch", None
    system_code = normalize_system_code(system)
    if system_code not in KNOWN_SYSTEM_CODES:
        return "system_mismatch", None
    raw_session = payload.get("current_session", 0)
    if type(raw_session) is int:
        current_session = raw_session
    elif isinstance(raw_session, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", raw_session.strip()):
        try:
            current_session = int(raw_session.strip())
        except ValueError:
            return "malformed_primary", None
    else:
        return "malformed_primary", None
    if current_session < 0:
        return "malformed_primary", None
    for key in ("summary", "source_wiki_root", "systems_library", "player_content_dir", "asset_dir"):
        if key in payload and not isinstance(payload[key], str):
            return "malformed_primary", None
    character_dir = _validated_character_dir(payload.get("character_dir", "characters"))
    if character_dir is None or not isinstance(payload.get("character_source_root", ""), str):
        return "malformed_primary", None
    if "systems_sources" in payload and not isinstance(payload["systems_sources"], list):
        return "malformed_primary", None
    return None, _ValidatedConfig(system_code, current_session, character_dir)


def _current_config(connection: sqlite3.Connection, campaign_slug: str) -> _ValidatedConfig | None:
    current = read_current_committed_bytes(
        connection, campaign_slug=campaign_slug, object_kind="config",
    )
    if current is None:
        return None
    payload = _decode_mapping(current[1])
    _, validated = _validate_config_payload(payload, campaign_slug)
    return validated


def _pending_journal(connection: sqlite3.Connection, campaign_slug: str,
                     kind: str, ref: str) -> bool:
    if kind == "character":
        for table in ("character_reconciliation_operations", "character_deletion_operations"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE campaign_slug = ? AND character_slug = ? "
                "AND state IN ('prepared', 'repository_pending', 'conflict') LIMIT 1",
                (campaign_slug, ref),
            ).fetchone():
                return True
    if kind == "page":
        for table in ("player_wiki_reconciliation_operations", "player_wiki_deletion_operations"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE campaign_slug = ? AND page_ref = ? "
                "AND state IN ('prepared', 'repository_pending', 'conflict') LIMIT 1",
                (campaign_slug, ref),
            ).fetchone():
                return True
    return connection.execute(
        """SELECT 1 FROM committed_source_publications
           WHERE campaign_slug = ? AND object_kind = ? AND object_ref = ?
             AND state IN ('prepared', 'conflict') LIMIT 1""",
        (campaign_slug, kind, ref),
    ).fetchone() is not None


def _mirror_blocked(connection: sqlite3.Connection, campaign_slug: str,
                    kind: str, ref: str) -> bool:
    if connection.execute(
        """SELECT 1 FROM committed_source_mirrors
           WHERE campaign_slug = ? AND object_kind = ? AND object_ref = ?
             AND state IN ('conflict', 'missing', 'unknown') LIMIT 1""",
        (campaign_slug, kind, ref),
    ).fetchone():
        return True
    return connection.execute(
        """SELECT 1 FROM committed_source_outbox
           WHERE campaign_slug = ? AND object_kind = ? AND object_ref = ?
             AND state = 'conflict' LIMIT 1""",
        (campaign_slug, kind, ref),
    ).fetchone() is not None


def _page_parity(connection: sqlite3.Connection, campaign_slug: str,
                 page_ref: str, source: bytes, current_session: int) -> str | None:
    row = connection.execute(
        "SELECT * FROM campaign_pages WHERE campaign_slug = ? AND page_ref = ?",
        (campaign_slug, page_ref),
    ).fetchone()
    if row is None:
        return "page_row_missing"
    actual = dict(zip((column[0] for column in connection.execute(
        "SELECT * FROM campaign_pages LIMIT 0").description), row))
    if is_deprecated_wiki_identity(actual["section"], actual["page_type"]):
        return "page_deprecated"
    if actual["published"] not in (0, 1) or type(actual["reveal_after_session"]) is not int or actual["reveal_after_session"] < 0:
        return "malformed_primary"
    try:
        metadata, body = parse_frontmatter(source.decode("utf-8"))
        if not isinstance(metadata, dict) or not metadata:
            return "malformed_primary"
        projected = build_page_payload(
            campaign_slug, page_ref, metadata=metadata, body_markdown=body,
            updated_at=actual["updated_at"],
        )
    except (UnicodeError, ValueError, TypeError, yaml.YAMLError, OverflowError, RecursionError):
        return "malformed_primary"
    for key, value in projected.items():
        if key == "updated_at":
            continue
        if actual.get(key) != value:
            return "page_row_mismatch"
    return None


def _classify(connection: sqlite3.Connection, campaign_slug: str, kind: str,
              ref: str, primary: bytes | None, secondary: bytes | None) -> str | None:
    if primary is None:
        return "missing_primary"
    if not isinstance(primary, bytes) or not primary or len(primary) > _MAX_SOURCE_BYTES:
        return "oversize_primary"
    if kind == "character":
        if secondary is None:
            return "missing_import"
        if not isinstance(secondary, bytes) or not secondary or len(secondary) > _MAX_SOURCE_BYTES:
            return "oversize_import"
    elif secondary is not None:
        return "malformed_import"
    if kind == "page":
        config = _current_config(connection, campaign_slug)
        if config is None:
            return "config_not_admitted"
        return _page_parity(connection, campaign_slug, ref, primary, config.current_session)
    payload = _decode_mapping(primary)
    if payload is None:
        return "malformed_primary"
    if kind == "config":
        reason, _ = _validate_config_payload(payload, campaign_slug)
        return reason
    if payload.get("campaign_slug") != campaign_slug or payload.get("character_slug") != ref:
        return "ownership_mismatch"
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        return "malformed_primary"
    if not isinstance(payload.get("status"), str) or not payload["status"].strip():
        return "malformed_primary"
    system = payload.get("system")
    config = _current_config(connection, campaign_slug)
    if config is None:
        return "config_not_admitted"
    if not isinstance(system, str) or normalize_system_code(system) != config.system_code:
        return "system_mismatch"
    imported = _decode_mapping(secondary)
    if imported is None:
        return "malformed_import"
    if imported.get("campaign_slug") != campaign_slug or imported.get("character_slug") != ref:
        return "ownership_mismatch"
    if not all(isinstance(imported.get(key), str) for key in
               ("source_path", "imported_at_utc", "parser_version", "import_status")):
        return "malformed_import"
    if not isinstance(imported.get("warnings"), list) or not all(
        isinstance(warning, str) for warning in imported["warnings"]
    ):
        return "malformed_import"
    return None


def _record_status(connection: sqlite3.Connection, campaign_slug: str, kind: str,
                   ref: str, status: str, code: str, revision: int | None) -> None:
    connection.execute(
        """INSERT INTO committed_source_admission
           (campaign_slug, object_kind, object_ref, status, reason_code, revision, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(campaign_slug, object_kind, object_ref) DO UPDATE SET
           status = excluded.status, reason_code = excluded.reason_code,
           revision = excluded.revision, updated_at = excluded.updated_at""",
        (campaign_slug, kind, ref, status, code, revision, _now()),
    )


def admit_legacy_object(
    connection: sqlite3.Connection, *, campaign_slug: str, object_kind: str,
    object_ref: str = "", primary_bytes: bytes | None,
    secondary_bytes: bytes | None = None, pending_journal: bool = False,
    mirror_conflict: bool = False, actor_user_id: int | None = None,
) -> AdmissionResult:
    """Admit one complete synthetic legacy object, or persist an actionable block.

    The caller supplies exact observed bytes. This function owns one short SQLite
    writer transaction and deliberately has no file or route access.
    """
    if not isinstance(campaign_slug, str) or not _CAMPAIGN_SLUG.fullmatch(campaign_slug):
        raise ValueError("Invalid campaign slug.")
    if object_kind not in {"config", "character", "page"}:
        raise ValueError("Invalid source kind.")
    if object_kind == "config":
        if object_ref != "":
            raise ValueError("Config reference must be empty.")
    elif object_kind == "character":
        if not isinstance(object_ref, str) or not _CHARACTER_SLUG.fullmatch(object_ref):
            raise ValueError("Invalid character reference.")
    elif not isinstance(object_ref, str) or len(object_ref.encode("utf-8")) > 512 or normalize_page_ref(object_ref) != object_ref:
        raise ValueError("Invalid page reference.")
    if type(pending_journal) is not bool or type(mirror_conflict) is not bool:
        raise ValueError("Journal and conflict flags must be boolean.")
    if actor_user_id is not None and (type(actor_user_id) is not int or actor_user_id < 1):
        raise ValueError("Invalid actor.")
    if connection.in_transaction:
        raise ValueError("Admission needs its own SQLite transaction.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        marker = connection.execute(
            "SELECT activated, schema_version FROM committed_source_activation WHERE singleton = 1"
        ).fetchone()
        from .committed_publication import active
        if marker is None or tuple(marker) not in ((0, 15), (0, 18)) or active(connection):
            raise ValueError("Committed-source admission requires trusted closed authority.")
        reason = None
        if not _legacy_enum_values_valid(connection):
            reason = "legacy_enum_invalid"
        elif pending_journal or _pending_journal(connection, campaign_slug, object_kind, object_ref):
            reason = "pending_journal"
        elif mirror_conflict or _mirror_blocked(
            connection, campaign_slug, object_kind, object_ref,
        ):
            reason = "mirror_conflict"
        else:
            reason = _classify(connection, campaign_slug, object_kind, object_ref,
                               primary_bytes, secondary_bytes)
        current = connection.execute(
            """SELECT revision FROM committed_source_current
               WHERE campaign_slug = ? AND object_kind = ? AND object_ref = ?""",
            (campaign_slug, object_kind, object_ref),
        ).fetchone()
        receipt = None
        if reason is None:
            receipt = _receipt_digest(object_kind, primary_bytes, secondary_bytes)
            prior = connection.execute(
                """SELECT revision FROM committed_source_admission_receipts
                   WHERE campaign_slug = ? AND object_kind = ? AND object_ref = ?
                     AND receipt_sha256 = ?""",
                (campaign_slug, object_kind, object_ref, receipt),
            ).fetchone()
            if prior is not None and current is not None and int(current[0]) == int(prior[0]):
                stored = connection.execute(
                    """SELECT primary_bytes, secondary_bytes, primary_sha256, secondary_sha256
                       FROM committed_source_generations WHERE campaign_slug = ?
                         AND object_kind = ? AND object_ref = ? AND revision = ?""",
                    (campaign_slug, object_kind, object_ref, int(prior[0])),
                ).fetchone()
                if (stored is not None and bytes(stored[0]) == primary_bytes
                        and (bytes(stored[1]) if stored[1] is not None else None) == secondary_bytes
                        and stored[2] == _digest(primary_bytes)
                        and stored[3] == (_digest(secondary_bytes) if secondary_bytes is not None else None)):
                    result = AdmissionResult("admitted", "already_admitted", int(prior[0]))
                    _record_status(connection, campaign_slug, object_kind, object_ref,
                                   result.status, result.reason_code, result.revision)
                    connection.commit()
                    return result
            if current is not None or prior is not None:
                reason = "existing_generation"
        if reason is not None:
            assert reason in _BLOCK_CODES
            _record_status(connection, campaign_slug, object_kind, object_ref,
                           "blocked", reason, None)
            connection.commit()
            return AdmissionResult("blocked", reason, None)
        system = (
            normalize_system_code(_decode_mapping(primary_bytes)["system"])
            if object_kind == "config"
            else _current_config(connection, campaign_slug).system_code
        )
        timestamp = _now()
        connection.execute(
            """INSERT INTO committed_source_generations
               (campaign_slug, object_kind, object_ref, revision, system_code,
                primary_bytes, secondary_bytes, primary_sha256, secondary_sha256,
                tombstone, actor_user_id, reason, committed_at)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 0, ?, 'legacy_admission', ?)""",
            (campaign_slug, object_kind, object_ref, system, primary_bytes,
             secondary_bytes, _digest(primary_bytes),
             _digest(secondary_bytes) if secondary_bytes is not None else None,
             actor_user_id, timestamp),
        )
        connection.execute(
            """INSERT INTO committed_source_current
               (campaign_slug, object_kind, object_ref, revision) VALUES (?, ?, ?, 1)""",
            (campaign_slug, object_kind, object_ref),
        )
        connection.execute(
            """INSERT INTO committed_source_admission_receipts
               (campaign_slug, object_kind, object_ref, receipt_sha256, revision, admitted_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (campaign_slug, object_kind, object_ref, receipt, timestamp),
        )
        _record_status(connection, campaign_slug, object_kind, object_ref,
                       "admitted", "admitted", 1)
        connection.commit()
        return AdmissionResult("admitted", "admitted", 1)
    except Exception:
        connection.rollback()
        raise


def read_current_committed_bytes(
    connection: sqlite3.Connection, *, campaign_slug: str,
    object_kind: str, object_ref: str = "",
) -> tuple[int, bytes, bytes | None] | None:
    """Read exact bytes only while the marker is closed and source proof is healthy."""
    marker = connection.execute(
        "SELECT activated, schema_version FROM committed_source_activation WHERE singleton = 1"
    ).fetchone()
    from .committed_publication import active
    if (marker is None or tuple(marker) not in ((0, 15), (0, 18))
            or active(connection) or not _legacy_enum_values_valid(connection)):
        return None
    if _pending_journal(connection, campaign_slug, object_kind, object_ref):
        return None
    if _mirror_blocked(connection, campaign_slug, object_kind, object_ref):
        return None
    row = connection.execute(
        """SELECT g.revision, g.primary_bytes, g.secondary_bytes, g.primary_sha256,
                  g.secondary_sha256, g.tombstone, a.status
           FROM committed_source_current AS c
           JOIN committed_source_generations AS g
             ON (g.campaign_slug, g.object_kind, g.object_ref, g.revision)
              = (c.campaign_slug, c.object_kind, c.object_ref, c.revision)
           JOIN committed_source_admission AS a
             ON (a.campaign_slug, a.object_kind, a.object_ref)
              = (c.campaign_slug, c.object_kind, c.object_ref)
           WHERE c.campaign_slug = ? AND c.object_kind = ? AND c.object_ref = ?""",
        (campaign_slug, object_kind, object_ref),
    ).fetchone()
    if row is None or row[5] or row[6] != "admitted" or row[1] is None:
        return None
    primary = bytes(row[1]); secondary = bytes(row[2]) if row[2] is not None else None
    if _digest(primary) != row[3] or (secondary is None) != (row[4] is None):
        return None
    if secondary is not None and _digest(secondary) != row[4]:
        return None
    return int(row[0]), primary, secondary
