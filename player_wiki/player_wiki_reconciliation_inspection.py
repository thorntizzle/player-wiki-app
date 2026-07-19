from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import sys
from typing import Callable, Iterable, Mapping
from urllib.parse import quote

import yaml

from .input_limits import MAX_CONTENT_LENGTH
from .migrations import MigrationError, inspect_migration_ledger
from .migrations import (
    _PLAYER_WIKI_DELETION_RECONCILIATION_SCHEMA_SQL,
    _PLAYER_WIKI_RECONCILIATION_SCHEMA_SQL,
)
from .runtime_lease import active_restore_journal_path, runtime_state_lock_path


_HEX_32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_CAMPAIGN_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ERROR_CODE = re.compile(r"[a-z0-9_-]{0,80}\Z")
_ACTIVE_STATES = ("prepared", "repository_pending", "conflict")
_PUBLICATION_KINDS = ("create", "update", "unpublish", "api_upsert")
_DELETION_KINDS = ("browser_delete", "api_delete")
_CONFIG_LIMIT = 1024 * 1024


class ReconciliationInspectionError(RuntimeError):
    def __init__(self, reason_code: str, *, exit_code: int = 2) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class InspectionFilters:
    kind: str = "all"
    campaign_slug: str | None = None
    page_ref: str | None = None
    state: str | None = None
    operation_id: str | None = None

    def validate(self) -> None:
        if self.kind not in {"all", "publication", "deletion"}:
            raise ReconciliationInspectionError("invalid_kind_filter")
        if self.state is not None and self.state not in _ACTIVE_STATES:
            raise ReconciliationInspectionError("invalid_state_filter")
        if self.campaign_slug is not None:
            if (
                not isinstance(self.campaign_slug, str)
                or len(self.campaign_slug.encode("utf-8")) > 128
                or _CAMPAIGN_SLUG.fullmatch(self.campaign_slug) is None
            ):
                raise ReconciliationInspectionError("invalid_campaign_filter")
        if self.page_ref is not None:
            _validate_page_ref(self.page_ref, reason_code="invalid_page_ref_filter")
            if self.campaign_slug is None:
                raise ReconciliationInspectionError("page_ref_requires_campaign_filter")
        if self.operation_id is not None and _HEX_32.fullmatch(self.operation_id) is None:
            raise ReconciliationInspectionError("invalid_operation_id_filter")

    def redacted_scope(self) -> dict[str, object]:
        return {
            "campaign_filter_present": self.campaign_slug is not None,
            "kind": self.kind,
            "operation_id_filter_present": self.operation_id is not None,
            "page_ref_filter_present": self.page_ref is not None,
            "state_filter_present": self.state is not None,
        }


@dataclass(frozen=True, slots=True)
class _FileEvidence:
    kind: str
    digest: str
    size: int
    identity: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class _CampaignPaths:
    content_root: Path
    assets_root: Path
    config_evidence: _FileEvidence


@dataclass(frozen=True, slots=True)
class _Snapshot:
    migration: tuple[int, int, bool]
    rows: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]
    file_evidence: tuple[tuple[str, str, _FileEvidence], ...]
    operations: tuple[tuple[tuple[str, object], ...], ...]


def inspect_player_wiki_reconciliation(
    *,
    database_path: Path,
    campaigns_dir: Path,
    filters: InspectionFilters | None = None,
    between_scans: Callable[[], None] | None = None,
) -> tuple[dict[str, object], int]:
    """Inspect active reconciliation state without initializing application state."""

    selected = filters or InspectionFilters()
    scope = selected.redacted_scope()
    try:
        selected.validate()
        database = _validate_database_path(Path(database_path))
        campaigns_root = _validate_directory(Path(campaigns_dir), "campaigns_root_unavailable")
        if os.path.lexists(active_restore_journal_path(database)):
            raise ReconciliationInspectionError("restore_recovery_active")
        before_identity = _state_identity(database)
        _require_wal_read_preconditions(database, before_identity)
        connection = _open_read_only_database(database)
        try:
            first = _collect_snapshot(connection, campaigns_root, selected)
            if between_scans is not None:
                between_scans()
            if os.path.lexists(active_restore_journal_path(database)):
                raise ReconciliationInspectionError(
                    "restore_recovery_appeared_during_inspection",
                    exit_code=3,
                )
            second = _collect_snapshot(connection, campaigns_root, selected)
        finally:
            connection.close()
        if os.path.lexists(active_restore_journal_path(database)):
            raise ReconciliationInspectionError(
                "restore_recovery_appeared_during_inspection",
                exit_code=3,
            )
        after_identity = _state_identity(database)
        if before_identity != after_identity or first != second:
            raise ReconciliationInspectionError("inspection_evidence_changed", exit_code=3)
        report = _stable_report(scope, first)
        exit_code = 1 if first.operations or first.migration[0] == 2 else 0
        return report, exit_code
    except ReconciliationInspectionError as exc:
        consistency = "indeterminate" if exc.exit_code == 3 else "invalid"
        return _failure_report(scope, consistency, exc.reason_code), exc.exit_code
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return _failure_report(scope, "indeterminate", "database_busy_or_changed"), 3
        return _failure_report(scope, "invalid", "database_unavailable_or_invalid"), 2
    except sqlite3.DatabaseError:
        return _failure_report(scope, "invalid", "database_unavailable_or_invalid"), 2
    except (MigrationError, OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, MemoryError):
        return _failure_report(scope, "invalid", "inspection_evidence_untrusted"), 2
    except Exception:
        return _failure_report(scope, "invalid", "inspection_failed_safely"), 2


def _collect_snapshot(
    connection: sqlite3.Connection,
    campaigns_root: Path,
    filters: InspectionFilters,
) -> _Snapshot:
    try:
        ledger = inspect_migration_ledger(connection)
    except MigrationError as exc:
        raise ReconciliationInspectionError("migration_ledger_untrusted") from exc
    if not ledger.ledger_exists or ledger.applied_version not in {2, 3, 4, 5, 6, 7, 8, 9}:
        raise ReconciliationInspectionError("migration_version_unsupported")
    if ledger.current_version != 9:
        raise ReconciliationInspectionError("migration_registry_unsupported")
    _validate_versioned_inventory(connection, ledger.applied_version)
    if ledger.applied_version == 2 and filters.kind == "deletion":
        raise ReconciliationInspectionError("deletion_inspection_requires_current_schema")

    kinds = (
        ("publication",)
        if filters.kind == "publication"
        else ("deletion",)
        if filters.kind == "deletion"
        else ("publication", "deletion")
        if ledger.applied_version in {3, 4, 5, 6, 7, 8, 9}
        else ("publication",)
    )
    raw_rows: list[tuple[str, Mapping[str, object]]] = []
    for kind in kinds:
        raw_rows.extend((kind, row) for row in _read_rows(connection, kind, filters))
    raw_rows.sort(key=lambda item: (str(item[1]["operation_id"]), item[0]))
    active_pages: set[tuple[object, object]] = set()
    for _kind, row in raw_rows:
        active_page = (row["campaign_slug"], row["page_ref"])
        if active_page in active_pages:
            raise ReconciliationInspectionError("cross_journal_active_page_conflict")
        active_pages.add(active_page)

    campaigns: dict[str, _CampaignPaths] = {}
    file_evidence: list[tuple[str, str, _FileEvidence]] = []
    operations: list[dict[str, object]] = []
    row_evidence: list[tuple[str, tuple[tuple[str, object], ...]]] = []
    for kind, row in raw_rows:
        normalized = _normalize_row(kind, row)
        row_evidence.append((kind, tuple(sorted(normalized.items()))))
        campaign_slug = str(normalized["campaign_slug"])
        paths = campaigns.get(campaign_slug)
        if paths is None:
            paths = _load_campaign_paths(campaigns_root, campaign_slug)
            campaigns[campaign_slug] = paths
            file_evidence.append((campaign_slug, "config", paths.config_evidence))
        operation, evidence = (
            _classify_publication(normalized, paths)
            if kind == "publication"
            else _classify_deletion(normalized, paths)
        )
        operations.append(operation)
        file_evidence.extend((str(normalized["operation_id"]), label, value) for label, value in evidence)

    operations.sort(key=lambda item: (str(item["operation_id"]), str(item["kind"])))
    file_evidence.sort(key=lambda item: (item[0], item[1]))
    return _Snapshot(
        migration=(ledger.applied_version, ledger.current_version, ledger.is_current),
        rows=tuple(row_evidence),
        file_evidence=tuple(file_evidence),
        operations=tuple(tuple(sorted(operation.items())) for operation in operations),
    )


def _read_rows(
    connection: sqlite3.Connection,
    kind: str,
    filters: InspectionFilters,
) -> list[sqlite3.Row]:
    if kind == "publication":
        table = "player_wiki_reconciliation_operations"
        columns = (
            "operation_id,campaign_slug,page_ref,operation_kind,primary_authority,"
            "desired_primary_ref,previous_primary_digest,desired_primary_digest,"
            "previous_markdown_digest,desired_markdown_digest,desired_markdown,"
            "audit_event_type,audit_actor_user_id,audit_metadata_json,state,error_code,"
            "created_at,updated_at"
        )
    else:
        table = "player_wiki_deletion_operations"
        columns = (
            "operation_id,campaign_slug,page_ref,source_ref,tombstone_ref,source_sha256,"
            "source_size,operation_kind,audit_event_type,audit_actor_user_id,"
            "audit_metadata_json,state,error_code,created_at,updated_at"
        )
    clauses = ["state IN ('prepared','repository_pending','conflict')"]
    parameters: list[object] = []
    for column, value in (
        ("campaign_slug", filters.campaign_slug),
        ("page_ref", filters.page_ref),
        ("state", filters.state),
        ("operation_id", filters.operation_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            parameters.append(value)
    query = f"SELECT {columns} FROM {table} WHERE {' AND '.join(clauses)} ORDER BY operation_id"
    return list(connection.execute(query, tuple(parameters)).fetchall())


def _normalize_row(kind: str, row: Mapping[str, object]) -> dict[str, object]:
    values = {key: row[key] for key in row.keys()}
    operation_id = _required_text(values, "operation_id")
    if _HEX_32.fullmatch(operation_id) is None:
        raise ReconciliationInspectionError("journal_operation_identity_invalid")
    campaign_slug = _required_text(values, "campaign_slug")
    if len(campaign_slug.encode("utf-8")) > 128 or _CAMPAIGN_SLUG.fullmatch(campaign_slug) is None:
        raise ReconciliationInspectionError("journal_campaign_identity_invalid")
    page_ref = _required_text(values, "page_ref")
    _validate_page_ref(page_ref, reason_code="journal_page_identity_invalid")
    state = _required_text(values, "state")
    if state not in _ACTIVE_STATES:
        raise ReconciliationInspectionError("journal_state_invalid")
    error_code = _required_text(values, "error_code", allow_empty=True)
    if _ERROR_CODE.fullmatch(error_code) is None:
        raise ReconciliationInspectionError("journal_error_code_invalid")
    _validate_audit(values, kind)
    values.update(
        operation_id=operation_id,
        campaign_slug=campaign_slug,
        page_ref=page_ref,
        state=state,
        error_code=error_code,
    )
    if kind == "publication":
        operation_kind = _required_text(values, "operation_kind")
        primary_authority = _required_text(values, "primary_authority")
        if operation_kind not in _PUBLICATION_KINDS or primary_authority not in {"markdown", "image"}:
            raise ReconciliationInspectionError("publication_journal_structure_invalid")
        for field, allow_empty in (
            ("previous_primary_digest", True),
            ("desired_primary_digest", False),
            ("previous_markdown_digest", True),
            ("desired_markdown_digest", False),
        ):
            digest = _required_text(values, field, allow_empty=allow_empty)
            if (allow_empty and digest == ""):
                continue
            if _HEX_64.fullmatch(digest) is None:
                raise ReconciliationInspectionError("publication_digest_invalid")
        desired_ref = _required_text(values, "desired_primary_ref")
        _validate_relative_ref(desired_ref, "publication_primary_ref_invalid")
        if primary_authority == "markdown" and (
            desired_ref != f"{page_ref}.md"
            or values["previous_primary_digest"] != values["previous_markdown_digest"]
            or values["desired_primary_digest"] != values["desired_markdown_digest"]
        ):
            raise ReconciliationInspectionError("publication_primary_evidence_inconsistent")
        payload = values.get("desired_markdown")
        if state in {"prepared", "conflict"}:
            if not isinstance(payload, bytes) or not payload or len(payload) > MAX_CONTENT_LENGTH:
                raise ReconciliationInspectionError("publication_recovery_payload_invalid")
            try:
                payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ReconciliationInspectionError("publication_recovery_payload_invalid") from exc
            if hashlib.sha256(payload).hexdigest() != values["desired_markdown_digest"]:
                raise ReconciliationInspectionError("publication_recovery_payload_invalid")
        elif payload is not None:
            raise ReconciliationInspectionError("publication_recovery_payload_invalid")
    else:
        if _required_text(values, "operation_kind") not in _DELETION_KINDS:
            raise ReconciliationInspectionError("deletion_journal_structure_invalid")
        source_ref = _required_text(values, "source_ref")
        tombstone_ref = _required_text(values, "tombstone_ref")
        _validate_relative_ref(source_ref, "deletion_source_ref_invalid")
        _validate_relative_ref(tombstone_ref, "deletion_tombstone_ref_invalid")
        source_digest = _required_text(values, "source_sha256")
        if _HEX_64.fullmatch(source_digest) is None:
            raise ReconciliationInspectionError("deletion_digest_invalid")
        source_size = values.get("source_size")
        if (
            not isinstance(source_size, int)
            or isinstance(source_size, bool)
            or not (1 <= source_size <= MAX_CONTENT_LENGTH)
        ):
            raise ReconciliationInspectionError("deletion_size_invalid")
    return values


def _classify_publication(
    row: Mapping[str, object],
    paths: _CampaignPaths,
) -> tuple[dict[str, object], list[tuple[str, _FileEvidence]]]:
    page_ref = str(row["page_ref"])
    markdown_ref = f"{page_ref}.md"
    markdown_path = _path_under(paths.content_root, markdown_ref, "publication_markdown_path_unsafe")
    markdown = _snapshot_file(markdown_path, "publication_markdown_file_unsafe")
    evidence = [("markdown", markdown)]
    primary_authority = str(row["primary_authority"])
    if primary_authority == "markdown":
        if row["desired_primary_ref"] != markdown_ref:
            raise ReconciliationInspectionError("publication_primary_ref_invalid")
        primary = markdown
    else:
        primary_path = _path_under(
            paths.assets_root,
            str(row["desired_primary_ref"]),
            "publication_image_path_unsafe",
        )
        primary = _snapshot_file(primary_path, "publication_image_file_unsafe")
        evidence.append(("primary", primary))

    state = str(row["state"])
    if state == "conflict":
        return (
            _operation(
                row,
                "publication",
                "manual_repair_or_abandon",
                "journal_marked_conflict",
                "repair_or_abandon_after_backup",
            ),
            evidence,
        )
    if state == "repository_pending":
        desired = markdown.digest == row["desired_markdown_digest"]
        if primary_authority == "image":
            desired = desired and primary.digest == row["desired_primary_digest"]
        if desired:
            return (
                _operation(
                    row,
                    "publication",
                    "refresh_cleanup_retryable",
                    "final_authority_desired",
                    "retry_refresh_cleanup_after_backup",
                ),
                evidence,
            )
        return (
            _operation(
                row,
                "publication",
                "manual_attention",
                "final_authority_changed",
                "inspect_and_repair_after_backup",
            ),
            evidence,
        )

    primary_disposition = _digest_disposition(
        primary.digest,
        previous=str(row["previous_primary_digest"]),
        desired=str(row["desired_primary_digest"]),
    )
    if primary_disposition == "previous":
        return (
            _operation(
                row,
                "publication",
                "precommit_abortable",
                "primary_matches_previous",
                "abandon_precommit_after_backup",
            ),
            evidence,
        )
    if primary_disposition == "conflict":
        return (
            _operation(
                row,
                "publication",
                "manual_conflict",
                "primary_digest_conflict",
                "repair_or_abandon_after_backup",
            ),
            evidence,
        )
    if primary_authority == "image":
        markdown_disposition = _digest_disposition(
            markdown.digest,
            previous=str(row["previous_markdown_digest"]),
            desired=str(row["desired_markdown_digest"]),
        )
        if markdown_disposition == "previous":
            return (
                _operation(
                    row,
                    "publication",
                    "forward_recoverable_requires_markdown_publish",
                    "image_desired_markdown_previous",
                    "resume_forward_publish_markdown_after_backup",
                ),
                evidence,
            )
        if markdown_disposition == "conflict":
            return (
                _operation(
                    row,
                    "publication",
                    "manual_conflict",
                    "markdown_digest_conflict",
                    "repair_or_abandon_after_backup",
                ),
                evidence,
            )
    return (
        _operation(
            row,
            "publication",
            "forward_recoverable",
            "primary_and_markdown_desired",
            "resume_forward_after_backup",
        ),
        evidence,
    )


def _classify_deletion(
    row: Mapping[str, object],
    paths: _CampaignPaths,
) -> tuple[dict[str, object], list[tuple[str, _FileEvidence]]]:
    expected_source = f"{row['page_ref']}.md"
    expected_tombstone = PurePosixPath(expected_source).with_name(f".{row['operation_id']}.del").as_posix()
    if row["source_ref"] != expected_source or row["tombstone_ref"] != expected_tombstone:
        raise ReconciliationInspectionError("deletion_refs_inconsistent")
    source_path = _path_under(paths.content_root, expected_source, "deletion_source_path_unsafe")
    tombstone_path = _path_under(paths.content_root, expected_tombstone, "deletion_tombstone_path_unsafe")
    source = _snapshot_file(source_path, "deletion_source_file_unsafe")
    tombstone = _snapshot_file(tombstone_path, "deletion_tombstone_file_unsafe")
    evidence = [("source", source), ("tombstone", tombstone)]
    state = str(row["state"])
    if state == "conflict":
        return (
            _operation(
                row,
                "deletion",
                "manual_repair_or_abandon",
                "journal_marked_conflict",
                "repair_or_abandon_after_backup",
            ),
            evidence,
        )
    source_expected = (
        source.kind == "regular"
        and source.digest == row["source_sha256"]
        and source.size == row["source_size"]
    )
    tombstone_expected = (
        tombstone.kind == "regular"
        and tombstone.digest == row["source_sha256"]
        and tombstone.size == row["source_size"]
    )
    if state == "prepared":
        if source_expected and tombstone.kind == "absent":
            classification = "precommit_abortable"
            reason = "source_present_tombstone_absent"
            action = "abandon_precommit_after_backup"
        elif source.kind == "absent" and tombstone_expected:
            classification = "forward_recoverable"
            reason = "source_absent_tombstone_desired"
            action = "resume_forward_after_backup"
        else:
            classification = "manual_conflict"
            reason = "deletion_file_state_conflict"
            action = "repair_or_abandon_after_backup"
    elif source.kind == "absent" and (tombstone.kind == "absent" or tombstone_expected):
        classification = "refresh_cleanup_retryable"
        reason = "deletion_commit_authority_present"
        action = "retry_refresh_cleanup_after_backup"
    else:
        classification = "manual_attention"
        reason = "deletion_final_authority_changed"
        action = "inspect_and_repair_after_backup"
    return _operation(row, "deletion", classification, reason, action), evidence


def _operation(
    row: Mapping[str, object],
    kind: str,
    classification: str,
    reason_code: str,
    action: str,
) -> dict[str, object]:
    return {
        "backup_required": True,
        "classification": classification,
        "kind": kind,
        "operation_id": str(row["operation_id"]),
        "operation_kind": str(row["operation_kind"]),
        "reason_code": reason_code,
        "recommended_action": action,
        "state": str(row["state"]),
    }


def _load_campaign_paths(campaigns_root: Path, campaign_slug: str) -> _CampaignPaths:
    campaign_dir = _validate_directory(campaigns_root / campaign_slug, "campaign_root_unavailable")
    config_path = campaign_dir / "campaign.yaml"
    config_evidence, raw = _read_regular_file(config_path, "campaign_config_unavailable", max_bytes=_CONFIG_LIMIT)
    try:
        config = yaml.safe_load(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ReconciliationInspectionError("campaign_config_invalid") from exc
    if not isinstance(config, dict) or config.get("slug") != campaign_slug:
        raise ReconciliationInspectionError("campaign_config_invalid")
    content_ref = config.get("player_content_dir", "content")
    assets_ref = config.get("asset_dir", "assets")
    if not isinstance(content_ref, str) or not isinstance(assets_ref, str):
        raise ReconciliationInspectionError("campaign_config_invalid")
    content_root = _validate_directory(
        _path_under(campaign_dir, content_ref, "campaign_content_root_unsafe"),
        "campaign_content_root_unavailable",
    )
    assets_root = _validate_directory(
        _path_under(campaign_dir, assets_ref, "campaign_assets_root_unsafe"),
        "campaign_assets_root_unavailable",
    )
    return _CampaignPaths(content_root, assets_root, config_evidence)


def _validate_required_tables(connection: sqlite3.Connection, kinds: Iterable[str]) -> None:
    expected = {
        "publication": (
            "player_wiki_reconciliation_operations",
            (
                "operation_id", "campaign_slug", "page_ref", "operation_kind", "primary_authority",
                "desired_primary_ref", "previous_primary_digest", "desired_primary_digest",
                "previous_markdown_digest", "desired_markdown_digest", "desired_markdown",
                "audit_event_type", "audit_actor_user_id", "audit_metadata_json", "state",
                "error_code", "created_at", "updated_at",
            ),
            "idx_player_wiki_reconciliation_active_page",
            _PLAYER_WIKI_RECONCILIATION_SCHEMA_SQL,
        ),
        "deletion": (
            "player_wiki_deletion_operations",
            (
                "operation_id", "campaign_slug", "page_ref", "source_ref", "tombstone_ref",
                "source_sha256", "source_size", "operation_kind", "audit_event_type",
                "audit_actor_user_id", "audit_metadata_json", "state", "error_code",
                "created_at", "updated_at",
            ),
            "idx_player_wiki_deletion_active_page",
            _PLAYER_WIKI_DELETION_RECONCILIATION_SCHEMA_SQL,
        ),
    }
    for kind in kinds:
        table, column_names, unique_index, schema_sql = expected[kind]
        table_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if table_row is None or not isinstance(table_row[0], str):
            raise ReconciliationInspectionError("reconciliation_table_missing")
        expected_table_sql = _schema_statement(schema_sql, f"CREATE TABLE IF NOT EXISTS {table}")
        if _canonical_structural_sql(str(table_row[0])) != _canonical_structural_sql(expected_table_sql):
            raise ReconciliationInspectionError("reconciliation_table_shape_invalid")
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if tuple(str(column[1]) for column in columns) != column_names:
            raise ReconciliationInspectionError("reconciliation_table_shape_invalid")
        index_rows = connection.execute(f"PRAGMA index_list({table})").fetchall()
        matching = [row for row in index_rows if str(row[1]) == unique_index]
        if len(matching) != 1 or int(matching[0][2]) != 1 or int(matching[0][4]) != 1:
            raise ReconciliationInspectionError("reconciliation_table_shape_invalid")
        index_columns = connection.execute(f"PRAGMA index_info({unique_index})").fetchall()
        if tuple(str(row[2]) for row in index_columns) != ("campaign_slug", "page_ref"):
            raise ReconciliationInspectionError("reconciliation_table_shape_invalid")
        index_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (unique_index,),
        ).fetchone()
        expected_index_sql = _schema_statement(
            schema_sql,
            f"CREATE UNIQUE INDEX IF NOT EXISTS {unique_index}",
        )
        if (
            index_sql_row is None
            or not isinstance(index_sql_row[0], str)
            or _canonical_structural_sql(str(index_sql_row[0]))
            != _canonical_structural_sql(expected_index_sql)
        ):
            raise ReconciliationInspectionError("reconciliation_table_shape_invalid")


def _validate_versioned_inventory(
    connection: sqlite3.Connection,
    applied_version: int,
) -> None:
    if applied_version == 2:
        _validate_required_tables(connection, ("publication",))
        unledgered_deletion = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE (type = 'table' AND name = 'player_wiki_deletion_operations')
               OR (type = 'index' AND name = 'idx_player_wiki_deletion_active_page')
            LIMIT 1
            """
        ).fetchone()
        if unledgered_deletion is not None:
            raise ReconciliationInspectionError("reconciliation_inventory_inconsistent")
        return
    if applied_version in {3, 4, 5, 6, 7, 8, 9}:
        _validate_required_tables(connection, ("publication", "deletion"))
        return
    raise ReconciliationInspectionError("migration_version_unsupported")


def _schema_statement(schema_sql: str, prefix: str) -> str:
    for statement in schema_sql.split(";"):
        if statement.strip().startswith(prefix):
            return statement.strip()
    raise ReconciliationInspectionError("migration_registry_unsupported")


def _canonical_structural_sql(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().rstrip(";")).lower()
    return normalized.replace(" if not exists", "")


def _validate_audit(values: Mapping[str, object], kind: str) -> None:
    event = values.get("audit_event_type")
    actor = values.get("audit_actor_user_id")
    metadata = values.get("audit_metadata_json")
    operation_kind = values.get("operation_kind")
    if event is None and actor is None and metadata is None:
        if kind == "deletion" and operation_kind == "browser_delete":
            raise ReconciliationInspectionError("journal_audit_structure_invalid")
        return
    if not isinstance(event, str) or not event or len(event.encode("utf-8")) > 128:
        raise ReconciliationInspectionError("journal_audit_structure_invalid")
    if actor is not None and (not isinstance(actor, int) or isinstance(actor, bool)):
        raise ReconciliationInspectionError("journal_audit_structure_invalid")
    if not isinstance(metadata, str) or len(metadata.encode("utf-8")) > 65536:
        raise ReconciliationInspectionError("journal_audit_structure_invalid")
    try:
        decoded = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise ReconciliationInspectionError("journal_audit_structure_invalid") from exc
    if not isinstance(decoded, dict):
        raise ReconciliationInspectionError("journal_audit_structure_invalid")
    if kind == "deletion" and operation_kind == "api_delete":
        raise ReconciliationInspectionError("journal_audit_structure_invalid")


def _required_text(values: Mapping[str, object], field: str, *, allow_empty: bool = False) -> str:
    value = values.get(field)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ReconciliationInspectionError("journal_structure_invalid")
    return value


def _validate_page_ref(value: str, *, reason_code: str) -> PurePosixPath:
    if len(value.encode("utf-8")) > 2048 or value.endswith(".md"):
        raise ReconciliationInspectionError(reason_code)
    return _validate_relative_ref(value, reason_code)


def _validate_relative_ref(value: str, reason_code: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise ReconciliationInspectionError(reason_code)
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ReconciliationInspectionError(reason_code)
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ReconciliationInspectionError(reason_code)
    return path


def _path_under(root: Path, relative_ref: str, reason_code: str) -> Path:
    relative = _validate_relative_ref(relative_ref, reason_code)
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ReconciliationInspectionError(reason_code) from exc
        if not _is_plain_directory(details):
            raise ReconciliationInspectionError(reason_code)
    return candidate


def _validate_database_path(path: Path) -> Path:
    database = path.expanduser().absolute()
    _validate_directory(database.parent, "database_parent_unavailable")
    try:
        details = os.lstat(database)
    except FileNotFoundError as exc:
        raise ReconciliationInspectionError("database_missing") from exc
    except OSError as exc:
        raise ReconciliationInspectionError("database_unavailable") from exc
    if not _is_plain_regular(details):
        raise ReconciliationInspectionError("database_identity_unsafe")
    return database


def _validate_directory(path: Path, reason_code: str) -> Path:
    candidate = path.expanduser().absolute()
    try:
        details = os.lstat(candidate)
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    if not _is_plain_directory(details):
        raise ReconciliationInspectionError(reason_code)
    return candidate


def _snapshot_file(path: Path, reason_code: str) -> _FileEvidence:
    try:
        details = os.lstat(path)
    except FileNotFoundError:
        return _FileEvidence("absent", "", 0, (0, 0, 0, 0))
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    if not _is_plain_regular(details) or details.st_size > MAX_CONTENT_LENGTH:
        raise ReconciliationInspectionError(reason_code)
    evidence, _ = _read_regular_file(path, reason_code, max_bytes=MAX_CONTENT_LENGTH)
    return evidence


def _read_regular_file(
    path: Path,
    reason_code: str,
    *,
    max_bytes: int,
) -> tuple[_FileEvidence, bytes]:
    try:
        named_before = os.lstat(path)
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    if not _is_plain_regular(named_before) or named_before.st_size > max_bytes:
        raise ReconciliationInspectionError(reason_code)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    try:
        before = os.fstat(descriptor)
        if not _is_plain_regular(before) or before.st_size > max_bytes:
            raise ReconciliationInspectionError(reason_code)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(max_bytes + 1)
        after = os.fstat(descriptor)
        named = os.lstat(path)
    finally:
        os.close(descriptor)
    if (
        len(payload) > max_bytes
        or not _is_plain_regular(named)
        or _stat_identity(named_before) != _stat_identity(before)
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(after) != _stat_identity(named)
    ):
        raise ReconciliationInspectionError(reason_code, exit_code=3)
    return (
        _FileEvidence(
            "regular",
            hashlib.sha256(payload).hexdigest(),
            len(payload),
            _stat_identity(after),
        ),
        payload,
    )


def _is_plain_regular(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISREG(details.st_mode) and details.st_nlink == 1 and not (attributes & reparse)


def _is_plain_directory(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISDIR(details.st_mode) and not (attributes & reparse)


def _stat_identity(details: os.stat_result) -> tuple[int, int, int, int]:
    return (int(details.st_dev), int(details.st_ino), int(details.st_size), int(details.st_mtime_ns))


def _state_identity(database: Path) -> tuple[tuple[str, bool, tuple[int, int, int, int], str], ...]:
    paths = (
        ("database", database),
        ("wal", Path(f"{database}-wal")),
        ("shm", Path(f"{database}-shm")),
        ("runtime_lock", runtime_state_lock_path(database)),
        ("restore_journal", active_restore_journal_path(database)),
    )
    result: list[tuple[str, bool, tuple[int, int, int, int], str]] = []
    for label, path in paths:
        try:
            details = os.lstat(path)
        except FileNotFoundError:
            result.append((label, False, (0, 0, 0, 0), ""))
            continue
        except OSError as exc:
            raise ReconciliationInspectionError("state_identity_unavailable") from exc
        if not _is_plain_regular(details):
            raise ReconciliationInspectionError("state_identity_unsafe")
        digest = ""
        if label in {"wal", "shm", "runtime_lock", "restore_journal"}:
            evidence = _stream_regular_file_evidence(path, "state_identity_unavailable")
            digest = evidence.digest
            details = os.lstat(path)
        result.append((label, True, _stat_identity(details), digest))
    return tuple(result)


def _require_wal_read_preconditions(
    database: Path,
    identity: tuple[tuple[str, bool, tuple[int, int, int, int], str], ...],
) -> None:
    present = {label: exists for label, exists, _details, _digest in identity}
    if present.get("wal") and not present.get("shm"):
        raise ReconciliationInspectionError("wal_shared_memory_missing")
    if present.get("shm") and not present.get("wal"):
        raise ReconciliationInspectionError("wal_identity_inconsistent")
    if present.get("wal") and not _wal_has_reusable_read_mark(Path(f"{database}-shm")):
        raise ReconciliationInspectionError("wal_read_mark_unavailable", exit_code=3)
    if database.parent != database.parent.absolute():
        raise ReconciliationInspectionError("database_identity_unsafe")


def _open_read_only_database(database: Path) -> sqlite3.Connection:
    uri = f"file:{quote(database.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=0.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 0")
    connection.execute("PRAGMA query_only = ON")
    query_only = connection.execute("PRAGMA query_only").fetchone()
    if query_only is None or int(query_only[0]) != 1:
        connection.close()
        raise ReconciliationInspectionError("database_read_only_mode_unavailable")
    return connection


def _stream_regular_file_evidence(path: Path, reason_code: str) -> _FileEvidence:
    try:
        named_before = os.lstat(path)
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    if not _is_plain_regular(named_before):
        raise ReconciliationInspectionError(reason_code)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReconciliationInspectionError(reason_code) from exc
    try:
        before = os.fstat(descriptor)
        if not _is_plain_regular(before):
            raise ReconciliationInspectionError(reason_code)
        hasher = hashlib.sha256()
        byte_count = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                byte_count += len(chunk)
                hasher.update(chunk)
        after = os.fstat(descriptor)
        named = os.lstat(path)
    finally:
        os.close(descriptor)
    if (
        byte_count != int(after.st_size)
        or not _is_plain_regular(named)
        or _stat_identity(named_before) != _stat_identity(before)
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(after) != _stat_identity(named)
    ):
        raise ReconciliationInspectionError(reason_code, exit_code=3)
    return _FileEvidence("regular", hasher.hexdigest(), byte_count, _stat_identity(after))


def _wal_has_reusable_read_mark(shm_path: Path) -> bool:
    evidence, header = _read_regular_file(shm_path, "wal_identity_inconsistent", max_bytes=32768)
    if evidence.size < 120:
        raise ReconciliationInspectionError("wal_identity_inconsistent")
    byte_order = sys.byteorder
    first_header = header[:48]
    second_header = header[48:96]
    if first_header != second_header or first_header[12] != 1:
        raise ReconciliationInspectionError("wal_identity_inconsistent", exit_code=3)
    maximum_frame = int.from_bytes(first_header[16:20], byte_order)
    if maximum_frame == 0:
        return True
    read_marks = [
        int.from_bytes(header[offset : offset + 4], byte_order)
        for offset in range(100, 120, 4)
    ]
    return maximum_frame in read_marks[1:]


def _digest_disposition(actual: str, *, previous: str, desired: str) -> str:
    if actual == desired:
        return "desired"
    if actual == previous:
        return "previous"
    return "conflict"


def _stable_report(scope: dict[str, object], snapshot: _Snapshot) -> dict[str, object]:
    applied, current, is_current = snapshot.migration
    operations = [dict(operation) for operation in snapshot.operations]
    by_classification: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_state: dict[str, int] = {}
    for operation in operations:
        for target, key in (
            (by_classification, "classification"),
            (by_kind, "kind"),
            (by_state, "state"),
        ):
            value = str(operation[key])
            target[value] = target.get(value, 0) + 1
    return {
        "consistency": "stable",
        "counts": {
            "by_classification": by_classification,
            "by_kind": by_kind,
            "by_state": by_state,
            "total": len(operations),
        },
        "migration": {
            "applied_version": applied,
            "compatibility": "current" if is_current else "legacy_supported",
            "current_version": current,
            "evidence_status": "verified",
            "migration_required": not is_current,
        },
        "operations": operations,
        "schema_version": 1,
        "scope": scope,
    }


def _failure_report(scope: dict[str, object], consistency: str, reason_code: str) -> dict[str, object]:
    return {
        "consistency": consistency,
        "counts": {"by_classification": {}, "by_kind": {}, "by_state": {}, "total": 0},
        "error": {"reason_code": reason_code},
        "migration": {
            "compatibility": "untrusted",
            "evidence_status": "failed",
            "migration_required": False,
        },
        "operations": [],
        "schema_version": 1,
        "scope": scope,
    }
