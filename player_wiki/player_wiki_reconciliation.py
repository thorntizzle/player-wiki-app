from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import secrets
import sqlite3
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
from .file_publication import atomic_write_bytes
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


class _ReconciliationStateChanged(RuntimeError):
    def __init__(self, operation: ReconciliationOperation | None) -> None:
        super().__init__("Player wiki reconciliation ownership changed.")
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
        self.repository_store.refresh()
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
        markdown_path = self._resolve_markdown_path(campaign, operation.page_ref)
        if _digest_file(markdown_path) != operation.desired_markdown_digest:
            self._mark_repository_pending_retry(
                operation.operation_id,
                "markdown_authority_changed",
            )
            raise RuntimeError(
                "Player wiki Markdown authority changed before repository refresh."
            )
        if operation.primary_authority == "image":
            image_path = _resolve_under(
                Path(campaign.assets_dir),
                operation.desired_primary_ref,
            )
            if _digest_file(image_path) != operation.desired_primary_digest:
                self._mark_repository_pending_retry(
                    operation.operation_id,
                    "image_authority_changed",
                )
                raise RuntimeError(
                    "Player wiki image authority changed before repository refresh."
                )

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


class _RecoveryCampaignPageStore:
    """Metadata-only adapter that prevents pre-finalization page synchronization."""

    @staticmethod
    def ensure_campaign_seeded(_campaign_slug: str, _content_dir: Path) -> None:
        return None

    @staticmethod
    def list_pages(_campaign_slug: str) -> list[Any]:
        return []
