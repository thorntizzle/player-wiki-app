from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import sqlite3
import stat
from threading import Lock
from typing import Any, Callable

from .auth_store import AuthStore, isoformat, utcnow
from .campaign_content_service import (
    CampaignContentError,
    CampaignPageFileRecord,
    PreparedCampaignPageWrite,
    build_campaign_page_file_record,
)
from .db import get_db
from .file_publication import atomic_move_file, atomic_write_bytes, durable_unlink_file
from .input_limits import MAX_CONTENT_LENGTH
from .repository import load_campaign, parse_frontmatter


class PlayerWikiReconciliationConflict(CampaignContentError):
    """Raised when authoritative bytes no longer match either known digest."""


@dataclass(frozen=True, slots=True)
class PreparedManagedImage:
    asset_ref: str
    file_path: Path
    data_blob: bytes = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ReconciliationHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationOperation:
    operation_id: str
    campaign_slug: str
    page_ref: str
    operation_kind: str
    primary_authority: str
    desired_primary_ref: str
    previous_primary_digest: str
    desired_primary_digest: str
    previous_markdown_digest: str
    desired_markdown_digest: str
    desired_markdown: bytes | None = field(repr=False, compare=False)
    audit_event_type: str | None = None
    audit_actor_user_id: int | None = None
    audit_metadata_json: str | None = field(default=None, repr=False, compare=False)
    state: str = "prepared"
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class DeletionOperation:
    operation_id: str
    campaign_slug: str
    page_ref: str
    source_ref: str
    tombstone_ref: str
    source_sha256: str
    source_size: int
    operation_kind: str
    audit_event_type: str | None = None
    audit_actor_user_id: int | None = None
    audit_metadata_json: str | None = field(default=None, repr=False, compare=False)
    state: str = "prepared"
    error_code: str = ""


class _ReconciliationStateChanged(RuntimeError):
    def __init__(self, operation: ReconciliationOperation | None) -> None:
        super().__init__("Player wiki reconciliation ownership changed.")
        self.operation = operation


class _DeletionAuthorityChanged(RuntimeError):
    pass


class _DeletionStateChanged(RuntimeError):
    def __init__(self, operation: DeletionOperation | None) -> None:
        super().__init__("Player wiki deletion ownership changed.")
        self.operation = operation


class PlayerWikiReconciler:
    """Publish authoritative wiki files and finish derived state forward."""

    def __init__(
        self,
        *,
        page_store: Any,
        repository_store: Any,
        auth_store: AuthStore,
        hooks: ReconciliationHooks | None = None,
    ) -> None:
        self.page_store = page_store
        self.repository_store = repository_store
        self.auth_store = auth_store
        self.hooks = hooks or ReconciliationHooks()
        self._locks_guard = Lock()
        self._page_locks: dict[tuple[str, str], Lock] = {}

    def mutate(
        self,
        campaign: Any,
        prepared_page: PreparedCampaignPageWrite,
        *,
        operation_kind: str,
        prepared_image: PreparedManagedImage | None = None,
        audit_event_type: str | None = None,
        audit_actor_user_id: int | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> CampaignPageFileRecord:
        key = (prepared_page.campaign_slug, prepared_page.page_ref)
        with self._page_lock(key):
            operation, primary_path, primary_payload = self._prepare_operation(
                campaign,
                prepared_page,
                operation_kind=operation_kind,
                prepared_image=prepared_image,
                audit_event_type=audit_event_type,
                audit_actor_user_id=audit_actor_user_id,
                audit_metadata=audit_metadata,
            )
            self._event("after_prepare", operation.operation_id)

            actual_primary_digest = _digest_file(primary_path)
            if actual_primary_digest != operation.desired_primary_digest:
                self._event("before_primary_publish", operation.operation_id)
                primary_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    atomic_write_bytes(primary_path, primary_payload)
                except BaseException:
                    disposition = self._classify_digest(
                        _digest_file(primary_path),
                        previous=operation.previous_primary_digest,
                        desired=operation.desired_primary_digest,
                    )
                    if disposition == "previous":
                        self._delete_precommit(operation.operation_id)
                    elif disposition == "conflict":
                        self._mark_conflict(operation.operation_id, "primary_digest_conflict")
                    else:
                        return self._continue_prepared(campaign, operation.operation_id)
                    raise
                self._event("after_primary_publish", operation.operation_id)

            result = self._continue_prepared(campaign, operation.operation_id)
            if result is None:
                raise CampaignContentError("The wiki publication did not reach its commit point.")
            return result

    def delete(
        self,
        campaign: Any,
        existing_record: CampaignPageFileRecord,
        *,
        operation_kind: str,
        audit_event_type: str | None = None,
        audit_actor_user_id: int | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> CampaignPageFileRecord:
        key = (str(campaign.slug), existing_record.page_ref)
        with self._page_lock(key):
            operation, source_path, tombstone_path = self._prepare_deletion_operation(
                campaign,
                existing_record,
                operation_kind=operation_kind,
                audit_event_type=audit_event_type,
                audit_actor_user_id=audit_actor_user_id,
                audit_metadata=audit_metadata,
            )
            self._event("after_delete_prepare", operation.operation_id)
            try:
                self._event("before_tombstone_move", operation.operation_id)
                atomic_move_file(source_path, tombstone_path)
                self._event("after_tombstone_move", operation.operation_id)
            except BaseException:
                disposition = self._classify_deletion_files(
                    source_path,
                    tombstone_path,
                    operation,
                )
                if disposition == "precommit":
                    self._delete_deletion_precommit(operation.operation_id)
                elif disposition != "committed":
                    self._mark_deletion_conflict(
                        operation.operation_id,
                        "delete_move_state_conflict",
                        expected_state="prepared",
                    )
                raise
            if not self._continue_deletion(campaign, operation.operation_id):
                raise CampaignContentError("The wiki deletion did not reach its commit point.")
            return existing_record

    def recover_pending(self, *, limit: int = 8) -> dict[str, int]:
        rows = get_db().execute(
            """
            SELECT operation_id, campaign_slug, page_ref, state
            FROM player_wiki_reconciliation_operations
            WHERE state IN ('prepared', 'repository_pending')
            ORDER BY updated_at ASC, operation_id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit), 64)),),
        ).fetchall()
        counts = {"recovered": 0, "aborted": 0, "conflict": 0, "pending": 0}
        for row in rows:
            operation_id = str(row["operation_id"])
            campaign_slug = str(row["campaign_slug"])
            page_ref = str(row["page_ref"])
            state = str(row["state"])
            campaign = self._load_campaign_for_recovery(campaign_slug)
            if campaign is None:
                if state == "prepared":
                    current = self._mark_conflict(operation_id, "campaign_missing")
                    if current is not None and current.state == "conflict":
                        counts["conflict"] += 1
                    elif current is not None and current.state == "repository_pending":
                        counts["pending"] += 1
                else:
                    counts["pending"] += 1
                continue
            key = (campaign_slug, page_ref)
            with self._page_lock(key):
                try:
                    result = self._continue_prepared(campaign, operation_id)
                except PlayerWikiReconciliationConflict:
                    counts["conflict"] += 1
                except Exception:
                    counts["pending"] += 1
                else:
                    if result is None:
                        counts["aborted"] += 1
                    else:
                        counts["recovered"] += 1
        deletion_rows = get_db().execute(
            """
            SELECT operation_id, campaign_slug, page_ref, state
            FROM player_wiki_deletion_operations
            WHERE state IN ('prepared', 'repository_pending')
            ORDER BY updated_at ASC, operation_id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit), 64)),),
        ).fetchall()
        for row in deletion_rows:
            operation_id = str(row["operation_id"])
            campaign_slug = str(row["campaign_slug"])
            page_ref = str(row["page_ref"])
            state = str(row["state"])
            campaign = self._load_campaign_for_recovery(campaign_slug)
            if campaign is None:
                if state == "prepared":
                    _, transitioned = self._mark_deletion_conflict(
                        operation_id,
                        "campaign_missing",
                        expected_state="prepared",
                    )
                    if transitioned:
                        counts["conflict"] += 1
                else:
                    counts["pending"] += 1
                continue
            with self._page_lock((campaign_slug, page_ref)):
                try:
                    recovered = self._continue_deletion(
                        campaign,
                        operation_id,
                        selected_state=state,
                    )
                except PlayerWikiReconciliationConflict:
                    counts["conflict"] += 1
                except Exception:
                    counts["pending"] += 1
                else:
                    if recovered is not None:
                        counts["recovered" if recovered else "aborted"] += 1
        return counts

    def _load_campaign_for_recovery(self, campaign_slug: str) -> Any | None:
        """Load campaign paths/config without synchronizing the page read model."""

        config_path = Path(self.repository_store.campaigns_dir) / campaign_slug / "campaign.yaml"
        if not config_path.is_file():
            return None
        return load_campaign(config_path, _RecoveryCampaignPageStore())

    def _prepare_operation(
        self,
        campaign: Any,
        prepared_page: PreparedCampaignPageWrite,
        *,
        operation_kind: str,
        prepared_image: PreparedManagedImage | None,
        audit_event_type: str | None,
        audit_actor_user_id: int | None,
        audit_metadata: dict[str, Any] | None,
    ) -> tuple[ReconciliationOperation, Path, bytes]:
        if operation_kind not in {"create", "update", "unpublish", "api_upsert"}:
            raise CampaignContentError("Unsupported player wiki reconciliation operation.")
        if prepared_page.campaign_slug != str(campaign.slug):
            raise CampaignContentError("Prepared wiki content belongs to a different campaign.")
        expected_markdown_path = _resolve_under(
            Path(campaign.player_content_dir),
            prepared_page.relative_path,
        )
        if (
            prepared_page.relative_path != f"{prepared_page.page_ref}.md"
            or prepared_page.file_path.resolve() != expected_markdown_path
        ):
            raise CampaignContentError("Prepared wiki Markdown path is invalid.")
        desired_markdown = bytes(prepared_page.rendered_markdown)
        if not desired_markdown or len(desired_markdown) > MAX_CONTENT_LENGTH:
            raise CampaignContentError("Rendered wiki Markdown exceeds the recovery payload limit.")
        desired_markdown.decode("utf-8", errors="strict")

        previous_markdown_digest = _digest_file(prepared_page.file_path)
        desired_markdown_digest = _digest_bytes(desired_markdown)
        primary_authority = "markdown"
        desired_primary_ref = prepared_page.relative_path
        previous_primary_digest = previous_markdown_digest
        desired_primary_digest = desired_markdown_digest
        primary_path = prepared_page.file_path
        primary_payload = desired_markdown

        if prepared_image is not None:
            _validate_relative_ref(prepared_image.asset_ref)
            expected_image_path = _resolve_under(
                Path(campaign.assets_dir),
                prepared_image.asset_ref,
            )
            if prepared_image.file_path.resolve() != expected_image_path:
                raise CampaignContentError("Prepared wiki image path is invalid.")
            desired_image_digest = _digest_bytes(prepared_image.data_blob)
            previous_image_digest = _digest_file(prepared_image.file_path)
            if desired_image_digest != previous_image_digest:
                primary_authority = "image"
                desired_primary_ref = prepared_image.asset_ref
                previous_primary_digest = previous_image_digest
                desired_primary_digest = desired_image_digest
                primary_path = prepared_image.file_path
                primary_payload = bytes(prepared_image.data_blob)

        normalized_audit_event, normalized_actor_id, audit_metadata_json = self._prepare_audit(
            audit_event_type,
            audit_actor_user_id,
            audit_metadata,
        )
        now = isoformat(utcnow())
        operation = ReconciliationOperation(
            operation_id=secrets.token_hex(16),
            campaign_slug=prepared_page.campaign_slug,
            page_ref=prepared_page.page_ref,
            operation_kind=operation_kind,
            primary_authority=primary_authority,
            desired_primary_ref=desired_primary_ref,
            previous_primary_digest=previous_primary_digest,
            desired_primary_digest=desired_primary_digest,
            previous_markdown_digest=previous_markdown_digest,
            desired_markdown_digest=desired_markdown_digest,
            desired_markdown=desired_markdown,
            audit_event_type=normalized_audit_event,
            audit_actor_user_id=normalized_actor_id,
            audit_metadata_json=audit_metadata_json,
        )
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            deletion_guard = connection.execute(
                """
                SELECT 1
                FROM player_wiki_deletion_operations
                WHERE campaign_slug = ? AND page_ref = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (operation.campaign_slug, operation.page_ref),
            ).fetchone()
            if deletion_guard is not None:
                raise PlayerWikiReconciliationConflict(
                    "This wiki page has a pending deletion operation and requires repair."
                )
            connection.execute(
                """
                INSERT INTO player_wiki_reconciliation_operations (
                    operation_id, campaign_slug, page_ref, operation_kind,
                    primary_authority, desired_primary_ref,
                    previous_primary_digest, desired_primary_digest,
                    previous_markdown_digest, desired_markdown_digest,
                    desired_markdown, audit_event_type, audit_actor_user_id,
                    audit_metadata_json, state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.page_ref,
                    operation.operation_kind,
                    operation.primary_authority,
                    operation.desired_primary_ref,
                    operation.previous_primary_digest,
                    operation.desired_primary_digest,
                    operation.previous_markdown_digest,
                    operation.desired_markdown_digest,
                    sqlite3.Binary(desired_markdown),
                    operation.audit_event_type,
                    operation.audit_actor_user_id,
                    operation.audit_metadata_json,
                    now,
                    now,
                ),
            )
            connection.commit()
        except PlayerWikiReconciliationConflict:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise PlayerWikiReconciliationConflict(
                "This wiki page has a pending reconciliation operation and requires repair."
            ) from exc
        return operation, primary_path, primary_payload

    def _continue_prepared(
        self,
        campaign: Any,
        operation_id: str,
    ) -> CampaignPageFileRecord | None:
        try:
            return self._continue_prepared_once(campaign, operation_id)
        except _ReconciliationStateChanged as exc:
            operation = exc.operation
            if operation is not None and operation.state == "repository_pending":
                return self._refresh_and_cleanup(campaign, operation)
            if operation is not None and operation.state == "conflict":
                raise PlayerWikiReconciliationConflict(
                    "This wiki page has a reconciliation conflict and requires repair."
                )
            if operation is None:
                return None
            page_record = self.page_store.get_page_record(
                str(campaign.slug),
                operation.page_ref,
                include_body=True,
            )
            if page_record is None:
                return None
            return build_campaign_page_file_record(campaign, page_record)

    def _continue_prepared_once(
        self,
        campaign: Any,
        operation_id: str,
    ) -> CampaignPageFileRecord | None:
        operation = self._load_operation(operation_id)
        if operation is None:
            return None
        if operation.state == "repository_pending":
            return self._refresh_and_cleanup(campaign, operation)
        if operation.state == "conflict":
            raise PlayerWikiReconciliationConflict(
                "This wiki page has a reconciliation conflict and requires repair."
            )
        if operation.state != "prepared":
            return None

        primary_path = self._resolve_primary_path(campaign, operation)
        primary_disposition = self._classify_digest(
            _digest_file(primary_path),
            previous=operation.previous_primary_digest,
            desired=operation.desired_primary_digest,
        )
        if primary_disposition == "previous":
            self._delete_precommit(operation.operation_id)
            return None
        if primary_disposition == "conflict":
            self._raise_conflict(operation.operation_id, "primary_digest_conflict")

        desired_markdown = operation.desired_markdown
        if desired_markdown is None:
            self._raise_conflict(operation.operation_id, "recovery_payload_missing")
        try:
            desired_text = desired_markdown.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            self._raise_conflict(operation.operation_id, "recovery_payload_invalid_utf8")
        if _digest_bytes(desired_markdown) != operation.desired_markdown_digest:
            self._raise_conflict(operation.operation_id, "recovery_payload_digest_mismatch")

        markdown_path = self._resolve_markdown_path(campaign, operation.page_ref)
        if operation.primary_authority == "image":
            if _digest_file(primary_path) != operation.desired_primary_digest:
                self._raise_conflict(operation.operation_id, "required_image_changed")
            markdown_disposition = self._classify_digest(
                _digest_file(markdown_path),
                previous=operation.previous_markdown_digest,
                desired=operation.desired_markdown_digest,
            )
            if markdown_disposition == "previous":
                self._event("before_markdown_publish", operation.operation_id)
                markdown_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_bytes(markdown_path, desired_markdown)
                self._event("after_markdown_publish", operation.operation_id)
            elif markdown_disposition == "conflict":
                self._raise_conflict(operation.operation_id, "markdown_digest_conflict")

        if _digest_file(markdown_path) != operation.desired_markdown_digest:
            self._raise_conflict(operation.operation_id, "markdown_not_desired")
        if (
            operation.primary_authority == "image"
            and _digest_file(primary_path) != operation.desired_primary_digest
        ):
            self._raise_conflict(operation.operation_id, "required_image_changed")

        metadata, body_markdown = parse_frontmatter(desired_text)
        self.page_store.validate_page_upsert(
            operation.campaign_slug,
            operation.page_ref,
            metadata=metadata,
            body_markdown=body_markdown.strip(),
        )
        self._event("before_sqlite_finalize", operation.operation_id)
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            guard = connection.execute(
                """
                SELECT state
                FROM player_wiki_reconciliation_operations
                WHERE operation_id = ?
                """,
                (operation.operation_id,),
            ).fetchone()
            if guard is None or str(guard["state"]) != "prepared":
                connection.rollback()
                current_operation = self._load_operation(operation.operation_id)
                if current_operation is not None and current_operation.state == "repository_pending":
                    return self._refresh_and_cleanup(campaign, current_operation)
                if current_operation is not None and current_operation.state == "conflict":
                    raise PlayerWikiReconciliationConflict(
                        "This wiki page has a reconciliation conflict and requires repair."
                    )
                page_record = self.page_store.get_page_record(
                    operation.campaign_slug,
                    operation.page_ref,
                    include_body=True,
                )
                if page_record is None:
                    return None
                return build_campaign_page_file_record(campaign, page_record)
            page_record = self.page_store.upsert_page(
                operation.campaign_slug,
                operation.page_ref,
                metadata=metadata,
                body_markdown=body_markdown.strip(),
                commit=False,
            )
            self._event("after_page_upsert", operation.operation_id)
            if operation.audit_event_type is not None:
                audit_metadata = json.loads(operation.audit_metadata_json or "{}")
                self.auth_store.insert_audit_event(
                    event_type=operation.audit_event_type,
                    actor_user_id=operation.audit_actor_user_id,
                    campaign_slug=operation.campaign_slug,
                    metadata=audit_metadata,
                    commit=False,
                )
                self._event("after_audit_insert", operation.operation_id)
            transition = connection.execute(
                """
                UPDATE player_wiki_reconciliation_operations
                SET state = 'repository_pending', desired_markdown = NULL,
                    error_code = '', updated_at = ?
                WHERE operation_id = ? AND state = 'prepared'
                """,
                (isoformat(utcnow()), operation.operation_id),
            )
            if transition.rowcount != 1:
                raise RuntimeError("Player wiki reconciliation finalization lost journal ownership.")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        self._event("after_repository_pending", operation.operation_id)
        pending_operation = self._load_operation(operation.operation_id)
        if pending_operation is None:
            raise RuntimeError("Player wiki reconciliation state disappeared before refresh.")
        return self._refresh_and_cleanup(
            campaign,
            pending_operation,
            page_record=page_record,
        )

    def _refresh_and_cleanup(
        self,
        campaign: Any,
        operation: ReconciliationOperation,
        *,
        page_record: Any | None = None,
    ) -> CampaignPageFileRecord:
        self._validate_repository_pending_authority(campaign, operation)
        self._event("before_repository_refresh", operation.operation_id)
        self.repository_store.refresh_from_database()
        self._event("after_repository_refresh", operation.operation_id)
        if page_record is None:
            page_record = self.page_store.get_page_record(
                operation.campaign_slug,
                operation.page_ref,
                include_body=True,
            )
        if page_record is None:
            raise RuntimeError("Campaign page was not readable after forward reconciliation.")

        self._validate_repository_pending_authority(campaign, operation)
        self._event("before_journal_cleanup", operation.operation_id)
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            final_error = self._repository_pending_authority_error(campaign, operation)
            if final_error is not None:
                connection.rollback()
                self._mark_repository_pending_retry(
                    operation.operation_id,
                    final_error,
                )
                raise RuntimeError(
                    "Player wiki authority changed before journal cleanup."
                )
            connection.execute(
                """
                DELETE FROM player_wiki_reconciliation_operations
                WHERE operation_id = ? AND state = 'repository_pending'
                """,
                (operation.operation_id,),
            )
            self._event("after_journal_delete", operation.operation_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return build_campaign_page_file_record(campaign, page_record)

    def _validate_repository_pending_authority(
        self,
        campaign: Any,
        operation: ReconciliationOperation,
    ) -> None:
        error_code = self._repository_pending_authority_error(campaign, operation)
        if error_code is None:
            return
        self._mark_repository_pending_retry(operation.operation_id, error_code)
        raise RuntimeError("Player wiki authority changed before repository refresh.")

    def _repository_pending_authority_error(
        self,
        campaign: Any,
        operation: ReconciliationOperation,
    ) -> str | None:
        markdown_path = self._resolve_markdown_path(campaign, operation.page_ref)
        if _digest_file(markdown_path) != operation.desired_markdown_digest:
            return "markdown_authority_changed"
        if operation.primary_authority == "image":
            image_path = _resolve_under(
                Path(campaign.assets_dir),
                operation.desired_primary_ref,
            )
            if _digest_file(image_path) != operation.desired_primary_digest:
                return "image_authority_changed"
        return None

    @staticmethod
    def _mark_repository_pending_retry(operation_id: str, error_code: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE player_wiki_reconciliation_operations
                SET error_code = ?, updated_at = ?
                WHERE operation_id = ? AND state = 'repository_pending'
                """,
                (error_code, isoformat(utcnow()), operation_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def _prepare_deletion_operation(
        self,
        campaign: Any,
        existing_record: CampaignPageFileRecord,
        *,
        operation_kind: str,
        audit_event_type: str | None,
        audit_actor_user_id: int | None,
        audit_metadata: dict[str, Any] | None,
    ) -> tuple[DeletionOperation, Path, Path]:
        if operation_kind not in {"browser_delete", "api_delete"}:
            raise CampaignContentError("Unsupported player wiki deletion operation.")
        campaign_slug = str(campaign.slug)
        page_ref = self.page_store.normalize_page_ref(existing_record.page_ref)
        source_ref = f"{page_ref}.md"
        if existing_record.relative_path != source_ref:
            raise CampaignContentError("Player wiki deletion source reference is invalid.")
        source_path = _resolve_private_path(Path(campaign.player_content_dir), source_ref)
        if Path(existing_record.file_path).absolute() != source_path.absolute():
            raise CampaignContentError("Player wiki deletion source path is invalid.")
        source_kind, source_digest, source_size = _snapshot_regular_file(source_path)
        if source_kind != "regular" or source_size < 1 or source_size > MAX_CONTENT_LENGTH:
            raise CampaignContentError("Player wiki deletion requires a bounded regular Markdown file.")

        normalized_event, normalized_actor, metadata_json = self._prepare_audit(
            audit_event_type,
            audit_actor_user_id,
            audit_metadata,
        )
        if operation_kind == "browser_delete" and normalized_event is None:
            raise CampaignContentError("Player wiki browser deletion requires audit metadata.")
        if operation_kind == "api_delete" and normalized_event is not None:
            raise CampaignContentError("Player wiki API deletion cannot create a browser audit event.")

        operation_id = secrets.token_hex(16)
        tombstone_ref = _deletion_tombstone_ref(source_ref, operation_id)
        tombstone_path = _resolve_private_path(
            Path(campaign.player_content_dir),
            tombstone_ref,
        )
        if tombstone_path.parent != source_path.parent or tombstone_path.suffix.lower() == ".md":
            raise CampaignContentError("Player wiki deletion tombstone path is invalid.")
        operation = DeletionOperation(
            operation_id=operation_id,
            campaign_slug=campaign_slug,
            page_ref=page_ref,
            source_ref=source_ref,
            tombstone_ref=tombstone_ref,
            source_sha256=source_digest,
            source_size=source_size,
            operation_kind=operation_kind,
            audit_event_type=normalized_event,
            audit_actor_user_id=normalized_actor,
            audit_metadata_json=metadata_json,
        )
        now = isoformat(utcnow())
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            publication_guard = connection.execute(
                """
                SELECT 1
                FROM player_wiki_reconciliation_operations
                WHERE campaign_slug = ? AND page_ref = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (campaign_slug, page_ref),
            ).fetchone()
            if publication_guard is not None:
                raise PlayerWikiReconciliationConflict(
                    "This wiki page has a pending publication operation and requires repair."
                )
            connection.execute(
                """
                INSERT INTO player_wiki_deletion_operations (
                    operation_id, campaign_slug, page_ref, source_ref,
                    tombstone_ref, source_sha256, source_size, operation_kind,
                    audit_event_type, audit_actor_user_id, audit_metadata_json,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.page_ref,
                    operation.source_ref,
                    operation.tombstone_ref,
                    operation.source_sha256,
                    operation.source_size,
                    operation.operation_kind,
                    operation.audit_event_type,
                    operation.audit_actor_user_id,
                    operation.audit_metadata_json,
                    now,
                    now,
                ),
            )
            connection.commit()
        except PlayerWikiReconciliationConflict:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise PlayerWikiReconciliationConflict(
                "This wiki page has a pending reconciliation operation and requires repair."
            ) from exc
        return operation, source_path, tombstone_path

    def _continue_deletion(
        self,
        campaign: Any,
        operation_id: str,
        *,
        selected_state: str | None = None,
    ) -> bool | None:
        try:
            return self._continue_deletion_once(
                campaign,
                operation_id,
                selected_state=selected_state,
            )
        except _DeletionStateChanged as exc:
            operation = exc.operation
            if operation is None or operation.state == "conflict":
                return None
            if operation.state == "repository_pending":
                source_path, tombstone_path = self._resolve_deletion_paths(
                    campaign,
                    operation,
                )
                try:
                    cleaned = self._refresh_and_cleanup_deletion(
                        campaign,
                        operation,
                        source_path,
                        tombstone_path,
                    )
                except _DeletionStateChanged:
                    return None
                return True if cleaned else None
            return None

    def _continue_deletion_once(
        self,
        campaign: Any,
        operation_id: str,
        *,
        selected_state: str | None,
    ) -> bool | None:
        if selected_state not in {None, "prepared", "repository_pending"}:
            raise RuntimeError("Player wiki deletion selected state is invalid.")
        operation = self._load_deletion_operation(operation_id)
        if operation is None:
            return None if selected_state is not None else False
        if selected_state is not None:
            if operation.state == "conflict":
                return None
            if selected_state == "repository_pending" and operation.state == "prepared":
                raise RuntimeError("Player wiki deletion state moved backward during recovery.")
        source_path, tombstone_path = self._resolve_deletion_paths(campaign, operation)
        if operation.state == "conflict":
            raise PlayerWikiReconciliationConflict(
                "This wiki page has a deletion conflict and requires repair."
            )
        if operation.state == "repository_pending":
            cleaned = self._refresh_and_cleanup_deletion(
                campaign,
                operation,
                source_path,
                tombstone_path,
            )
            return True if cleaned else None
        if operation.state != "prepared":
            return False

        disposition = self._classify_deletion_files(
            source_path,
            tombstone_path,
            operation,
        )
        if disposition == "precommit":
            precommit_state = self._delete_deletion_precommit(operation.operation_id)
            if precommit_state == "aborted":
                return False
            if precommit_state == "repository_pending":
                current = self._load_deletion_operation(operation.operation_id)
                if current is None:
                    return None
                cleaned = self._refresh_and_cleanup_deletion(
                    campaign,
                    current,
                    source_path,
                    tombstone_path,
                )
                return True if cleaned else None
            return None
        if disposition != "committed":
            self._raise_deletion_conflict(
                operation.operation_id,
                "delete_prepared_state_conflict",
                expected_state="prepared",
            )

        page_record = self.page_store.get_page_record(
            operation.campaign_slug,
            operation.page_ref,
            include_body=True,
        )
        if page_record is None:
            self._raise_deletion_conflict(
                operation.operation_id,
                "delete_page_row_missing",
                expected_state="prepared",
            )

        self._event("before_delete_sqlite_finalize", operation.operation_id)
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            guard = connection.execute(
                """
                SELECT state
                FROM player_wiki_deletion_operations
                WHERE operation_id = ?
                """,
                (operation.operation_id,),
            ).fetchone()
            if guard is None or str(guard["state"]) != "prepared":
                connection.rollback()
                current = self._load_deletion_operation(operation.operation_id)
                if current is not None and current.state == "repository_pending":
                    cleaned = self._refresh_and_cleanup_deletion(
                        campaign,
                        current,
                        source_path,
                        tombstone_path,
                    )
                    return True if cleaned else None
                if current is not None and current.state == "conflict":
                    raise _DeletionStateChanged(current)
                return None
            if self._classify_deletion_files(source_path, tombstone_path, operation) != "committed":
                raise _DeletionAuthorityChanged(
                    "Player wiki deletion authority changed before SQLite finalization."
                )
            deleted = self.page_store.delete_page(
                operation.campaign_slug,
                operation.page_ref,
                commit=False,
            )
            if deleted is None:
                raise RuntimeError("Player wiki deletion page row disappeared before finalization.")
            self._event("after_delete_page_row", operation.operation_id)
            if operation.audit_event_type is not None:
                self.auth_store.insert_audit_event(
                    event_type=operation.audit_event_type,
                    actor_user_id=operation.audit_actor_user_id,
                    campaign_slug=operation.campaign_slug,
                    metadata=json.loads(operation.audit_metadata_json or "{}"),
                    commit=False,
                )
                self._event("after_delete_audit_insert", operation.operation_id)
            if self._classify_deletion_files(source_path, tombstone_path, operation) != "committed":
                raise _DeletionAuthorityChanged(
                    "Player wiki deletion authority changed during SQLite finalization."
                )
            transition = connection.execute(
                """
                UPDATE player_wiki_deletion_operations
                SET state = 'repository_pending', error_code = '', updated_at = ?
                WHERE operation_id = ? AND state = 'prepared'
                """,
                (isoformat(utcnow()), operation.operation_id),
            )
            if transition.rowcount != 1:
                raise RuntimeError("Player wiki deletion finalization lost journal ownership.")
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            if isinstance(exc, _DeletionAuthorityChanged):
                self._raise_deletion_conflict(
                    operation.operation_id,
                    "delete_finalize_state_conflict",
                    expected_state="prepared",
                )
            raise
        self._event("after_delete_repository_pending", operation.operation_id)
        pending = self._load_deletion_operation(operation.operation_id)
        if pending is None:
            raise RuntimeError("Player wiki deletion journal disappeared before refresh.")
        self._refresh_and_cleanup_deletion(
            campaign,
            pending,
            source_path,
            tombstone_path,
        )
        return True

    def _refresh_and_cleanup_deletion(
        self,
        campaign: Any,
        operation: DeletionOperation,
        source_path: Path,
        tombstone_path: Path,
    ) -> bool:
        cleanup_state = self._deletion_cleanup_state(source_path, tombstone_path, operation)
        if cleanup_state == "conflict":
            self._raise_deletion_conflict(
                operation.operation_id,
                "delete_repository_state_conflict",
                expected_state="repository_pending",
            )
        self._event("before_delete_repository_refresh", operation.operation_id)
        self.repository_store.refresh_from_database()
        self._event("after_delete_repository_refresh", operation.operation_id)

        cleanup_state = self._deletion_cleanup_state(source_path, tombstone_path, operation)
        if cleanup_state == "conflict":
            self._raise_deletion_conflict(
                operation.operation_id,
                "delete_repository_state_conflict",
                expected_state="repository_pending",
            )
        if cleanup_state == "tombstone":
            self._event("before_tombstone_cleanup", operation.operation_id)
            _unlink_expected_regular_file(
                tombstone_path,
                operation.source_sha256,
                operation.source_size,
            )
            self._event("after_tombstone_cleanup", operation.operation_id)

        self._event("before_delete_journal_cleanup", operation.operation_id)
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT state
                FROM player_wiki_deletion_operations
                WHERE operation_id = ?
                """,
                (operation.operation_id,),
            ).fetchone()
            if current is None:
                connection.rollback()
                return False
            if str(current["state"]) != "repository_pending":
                raise RuntimeError("Player wiki deletion cleanup lost journal ownership.")
            if self._deletion_cleanup_state(source_path, tombstone_path, operation) != "complete":
                raise RuntimeError("Player wiki deletion authority changed before journal cleanup.")
            deleted = connection.execute(
                """
                DELETE FROM player_wiki_deletion_operations
                WHERE operation_id = ? AND state = 'repository_pending'
                """,
                (operation.operation_id,),
            )
            if deleted.rowcount != 1:
                raise RuntimeError("Player wiki deletion journal cleanup lost ownership.")
            self._event("after_delete_journal_cleanup", operation.operation_id)
            if self._deletion_cleanup_state(source_path, tombstone_path, operation) != "complete":
                raise _DeletionAuthorityChanged(
                    "Player wiki deletion authority changed during journal cleanup."
                )
            connection.commit()
            return True
        except BaseException:
            connection.rollback()
            cleanup_state = self._deletion_cleanup_state(source_path, tombstone_path, operation)
            if cleanup_state == "conflict":
                self._mark_deletion_conflict(
                    operation.operation_id,
                    "delete_cleanup_state_conflict",
                    expected_state="repository_pending",
                )
            raise

    @staticmethod
    def _deletion_cleanup_state(
        source_path: Path,
        tombstone_path: Path,
        operation: DeletionOperation,
    ) -> str:
        source_kind, _, _ = _snapshot_regular_file(source_path)
        tombstone_kind, tombstone_digest, tombstone_size = _snapshot_regular_file(tombstone_path)
        if source_kind != "absent":
            return "conflict"
        if tombstone_kind == "absent":
            return "complete"
        if (
            tombstone_kind == "regular"
            and tombstone_digest == operation.source_sha256
            and tombstone_size == operation.source_size
        ):
            return "tombstone"
        return "conflict"

    @staticmethod
    def _classify_deletion_files(
        source_path: Path,
        tombstone_path: Path,
        operation: DeletionOperation,
    ) -> str:
        source_kind, source_digest, source_size = _snapshot_regular_file(source_path)
        tombstone_kind, tombstone_digest, tombstone_size = _snapshot_regular_file(tombstone_path)
        source_expected = (
            source_kind == "regular"
            and source_digest == operation.source_sha256
            and source_size == operation.source_size
        )
        tombstone_expected = (
            tombstone_kind == "regular"
            and tombstone_digest == operation.source_sha256
            and tombstone_size == operation.source_size
        )
        if source_expected and tombstone_kind == "absent":
            return "precommit"
        if source_kind == "absent" and tombstone_expected:
            return "committed"
        return "conflict"

    def _resolve_deletion_paths(
        self,
        campaign: Any,
        operation: DeletionOperation,
    ) -> tuple[Path, Path]:
        expected_source_ref = f"{operation.page_ref}.md"
        expected_tombstone_ref = _deletion_tombstone_ref(
            expected_source_ref,
            operation.operation_id,
        )
        if (
            operation.source_ref != expected_source_ref
            or operation.tombstone_ref != expected_tombstone_ref
        ):
            self._raise_deletion_conflict(
                operation.operation_id,
                "delete_ref_mismatch",
                expected_state=operation.state,
            )
        root = Path(campaign.player_content_dir)
        return (
            _resolve_private_path(root, operation.source_ref),
            _resolve_private_path(root, operation.tombstone_ref),
        )

    @staticmethod
    def _delete_deletion_precommit(operation_id: str) -> str | None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            deleted = connection.execute(
                """
                DELETE FROM player_wiki_deletion_operations
                WHERE operation_id = ? AND state = 'prepared'
                """,
                (operation_id,),
            )
            if deleted.rowcount == 1:
                connection.commit()
                return "aborted"
            current = connection.execute(
                """
                SELECT state
                FROM player_wiki_deletion_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            connection.commit()
            return str(current["state"]) if current is not None else None
        except BaseException:
            connection.rollback()
            raise

    def _raise_deletion_conflict(
        self,
        operation_id: str,
        error_code: str,
        *,
        expected_state: str,
    ) -> None:
        operation, transitioned = self._mark_deletion_conflict(
            operation_id,
            error_code,
            expected_state=expected_state,
        )
        if transitioned:
            raise PlayerWikiReconciliationConflict(
                "Player wiki authority changed during deletion and requires repair."
            )
        raise _DeletionStateChanged(operation)

    def _mark_deletion_conflict(
        self,
        operation_id: str,
        error_code: str,
        *,
        expected_state: str,
    ) -> tuple[DeletionOperation | None, bool]:
        if expected_state not in {"prepared", "repository_pending"}:
            raise RuntimeError("Player wiki deletion conflict state is invalid.")
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            transition = connection.execute(
                """
                UPDATE player_wiki_deletion_operations
                SET state = 'conflict', error_code = ?, updated_at = ?
                WHERE operation_id = ?
                  AND state = ?
                """,
                (error_code, isoformat(utcnow()), operation_id, expected_state),
            )
            transitioned = transition.rowcount == 1
            row = connection.execute(
                """
                SELECT * FROM player_wiki_deletion_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        operation = self._map_deletion_operation(row) if row is not None else None
        if transitioned and (operation is None or operation.state != "conflict"):
            raise RuntimeError("Player wiki deletion conflict transition was not durable.")
        return operation, transitioned

    @staticmethod
    def _load_deletion_operation(operation_id: str) -> DeletionOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM player_wiki_deletion_operations
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return PlayerWikiReconciler._map_deletion_operation(row)

    @staticmethod
    def _map_deletion_operation(row: Any) -> DeletionOperation:
        return DeletionOperation(
            operation_id=str(row["operation_id"]),
            campaign_slug=str(row["campaign_slug"]),
            page_ref=str(row["page_ref"]),
            source_ref=str(row["source_ref"]),
            tombstone_ref=str(row["tombstone_ref"]),
            source_sha256=str(row["source_sha256"]),
            source_size=int(row["source_size"]),
            operation_kind=str(row["operation_kind"]),
            audit_event_type=(
                str(row["audit_event_type"])
                if row["audit_event_type"] is not None
                else None
            ),
            audit_actor_user_id=(
                int(row["audit_actor_user_id"])
                if row["audit_actor_user_id"] is not None
                else None
            ),
            audit_metadata_json=(
                str(row["audit_metadata_json"])
                if row["audit_metadata_json"] is not None
                else None
            ),
            state=str(row["state"]),
            error_code=str(row["error_code"]),
        )

    def _prepare_audit(
        self,
        event_type: str | None,
        actor_user_id: int | None,
        metadata: dict[str, Any] | None,
    ) -> tuple[str | None, int | None, str | None]:
        if event_type is None:
            if actor_user_id is not None or metadata is not None:
                raise CampaignContentError("Incomplete player wiki audit metadata.")
            return None, None, None
        normalized_event_type = str(event_type).strip()
        if not normalized_event_type or len(normalized_event_type.encode("utf-8")) > 128:
            raise CampaignContentError("Player wiki audit event type is invalid.")
        if actor_user_id is None:
            raise CampaignContentError("Player wiki browser audit actor is required.")
        sanitized = self.auth_store.sanitize_audit_metadata(metadata or {})
        metadata_json = json.dumps(sanitized, sort_keys=True)
        if len(metadata_json.encode("utf-8")) > 65536:
            raise CampaignContentError("Player wiki audit metadata is too large.")
        return normalized_event_type, int(actor_user_id), metadata_json

    def _load_operation(self, operation_id: str) -> ReconciliationOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM player_wiki_reconciliation_operations
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        raw_payload = row["desired_markdown"]
        payload = bytes(raw_payload) if raw_payload is not None else None
        return ReconciliationOperation(
            operation_id=str(row["operation_id"]),
            campaign_slug=str(row["campaign_slug"]),
            page_ref=str(row["page_ref"]),
            operation_kind=str(row["operation_kind"]),
            primary_authority=str(row["primary_authority"]),
            desired_primary_ref=str(row["desired_primary_ref"]),
            previous_primary_digest=str(row["previous_primary_digest"]),
            desired_primary_digest=str(row["desired_primary_digest"]),
            previous_markdown_digest=str(row["previous_markdown_digest"]),
            desired_markdown_digest=str(row["desired_markdown_digest"]),
            desired_markdown=payload,
            audit_event_type=(
                str(row["audit_event_type"])
                if row["audit_event_type"] is not None
                else None
            ),
            audit_actor_user_id=(
                int(row["audit_actor_user_id"])
                if row["audit_actor_user_id"] is not None
                else None
            ),
            audit_metadata_json=(
                str(row["audit_metadata_json"])
                if row["audit_metadata_json"] is not None
                else None
            ),
            state=str(row["state"]),
            error_code=str(row["error_code"]),
        )

    def _resolve_primary_path(self, campaign: Any, operation: ReconciliationOperation) -> Path:
        if operation.primary_authority == "markdown":
            expected_ref = f"{operation.page_ref}.md"
            if operation.desired_primary_ref != expected_ref:
                self._raise_conflict(operation.operation_id, "primary_ref_mismatch")
            return self._resolve_markdown_path(campaign, operation.page_ref)
        return _resolve_under(Path(campaign.assets_dir), operation.desired_primary_ref)

    @staticmethod
    def _resolve_markdown_path(campaign: Any, page_ref: str) -> Path:
        return _resolve_under(Path(campaign.player_content_dir), f"{page_ref}.md")

    def _delete_precommit(self, operation_id: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                DELETE FROM player_wiki_reconciliation_operations
                WHERE operation_id = ? AND state = 'prepared'
                """,
                (operation_id,),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def _raise_conflict(self, operation_id: str, error_code: str) -> None:
        operation = self._mark_conflict(operation_id, error_code)
        if operation is not None and operation.state == "conflict":
            raise PlayerWikiReconciliationConflict(
                "Player wiki authority changed during reconciliation and requires repair."
            )
        raise _ReconciliationStateChanged(operation)

    def _mark_conflict(
        self,
        operation_id: str,
        error_code: str,
    ) -> ReconciliationOperation | None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            transition = connection.execute(
                """
                UPDATE player_wiki_reconciliation_operations
                SET state = 'conflict', error_code = ?, updated_at = ?
                WHERE operation_id = ? AND state = 'prepared'
                """,
                (error_code, isoformat(utcnow()), operation_id),
            )
            owns_prepared = transition.rowcount == 1
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        operation = self._load_operation(operation_id)
        if owns_prepared and (operation is None or operation.state != "conflict"):
            raise RuntimeError("Player wiki reconciliation conflict transition was not durable.")
        return operation

    @staticmethod
    def _classify_digest(actual: str, *, previous: str, desired: str) -> str:
        if actual == desired:
            return "desired"
        if actual == previous:
            return "previous"
        return "conflict"

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)

    def _page_lock(self, key: tuple[str, str]) -> Lock:
        with self._locks_guard:
            lock = self._page_locks.get(key)
            if lock is None:
                lock = Lock()
                self._page_locks[key] = lock
            return lock


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return ""
    return _digest_bytes(data)


def _validate_relative_ref(relative_ref: str) -> PurePosixPath:
    normalized = str(relative_ref or "").strip().replace("\\", "/").strip("/")
    pure_path = PurePosixPath(normalized)
    if (
        not normalized
        or pure_path.is_absolute()
        or ".." in pure_path.parts
        or "." in pure_path.parts
    ):
        raise CampaignContentError("Player wiki reconciliation path is invalid.")
    return pure_path


def _resolve_under(root: Path, relative_ref: str) -> Path:
    pure_path = _validate_relative_ref(relative_ref)
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*pure_path.parts)).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise CampaignContentError("Player wiki reconciliation path escapes its campaign root.")
    return resolved


def _deletion_tombstone_ref(source_ref: str, operation_id: str) -> str:
    source = _validate_relative_ref(source_ref)
    if (
        len(operation_id) != 32
        or operation_id != operation_id.lower()
        or any(character not in "0123456789abcdef" for character in operation_id)
    ):
        raise CampaignContentError("Player wiki deletion operation identity is invalid.")
    tombstone_name = f".{operation_id}.del"
    if len(tombstone_name.encode("utf-8")) > 40:
        raise CampaignContentError("Player wiki deletion tombstone name is too long.")
    return source.with_name(tombstone_name).as_posix()


def _resolve_private_path(root: Path, relative_ref: str) -> Path:
    pure_path = _validate_relative_ref(relative_ref)
    root = Path(root).absolute()
    try:
        root_details = root.lstat()
    except FileNotFoundError:
        raise CampaignContentError("Player wiki content root is missing.") from None
    if (
        not stat.S_ISDIR(root_details.st_mode)
        or stat.S_ISLNK(root_details.st_mode)
        or _is_reparse_stat(root_details)
    ):
        raise CampaignContentError("Player wiki content root is unsafe.")
    current = root
    for part in pure_path.parts[:-1]:
        current = current / part
        try:
            details = current.lstat()
        except FileNotFoundError:
            raise CampaignContentError("Player wiki deletion parent path is missing.") from None
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or _is_reparse_stat(details)
        ):
            raise CampaignContentError("Player wiki deletion parent path is unsafe.")
    return root.joinpath(*pure_path.parts)


def _snapshot_regular_file(path: Path) -> tuple[str, str, int]:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return "absent", "", 0
    except OSError:
        return "unsafe", "", 0
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or _is_reparse_stat(before)
    ):
        return "unsafe", "", 0
    try:
        data = path.read_bytes()
        after = path.lstat()
    except FileNotFoundError:
        return "unsafe", "", 0
    except OSError:
        return "unsafe", "", 0
    before_identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
    )
    after_identity = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_size),
        int(after.st_mtime_ns),
    )
    if (
        before_identity != after_identity
        or not stat.S_ISREG(after.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or _is_reparse_stat(after)
        or len(data) != int(after.st_size)
    ):
        return "unsafe", "", 0
    return "regular", _digest_bytes(data), len(data)


def _unlink_expected_regular_file(path: Path, expected_digest: str, expected_size: int) -> None:
    kind, digest, size = _snapshot_regular_file(path)
    if kind != "regular" or digest != expected_digest or size != expected_size:
        raise PlayerWikiReconciliationConflict(
            "Player wiki deletion tombstone changed before cleanup."
        )
    durable_unlink_file(path)
    try:
        details = path.lstat()
    except FileNotFoundError:
        return
    if details is not None:
        raise OSError("Player wiki deletion tombstone cleanup was not durable.")


def _is_reparse_stat(value: os.stat_result) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0)) & 0x400)


class _RecoveryCampaignPageStore:
    """Metadata-only adapter that prevents pre-finalization page synchronization."""

    @staticmethod
    def ensure_campaign_seeded(_campaign_slug: str, _content_dir: Path) -> None:
        return None

    @staticmethod
    def list_pages(_campaign_slug: str) -> list[Any]:
        return []
