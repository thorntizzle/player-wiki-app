from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable

from flask import has_app_context

from .auth_store import isoformat, utcnow
from .character_importer import render_character_yaml
from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_path,
    validate_character_slug,
)
from .character_repository import CharacterRepository, load_campaign_character_config
from .character_store import CharacterStateStore, PreparedCharacterState
from .db import get_db
from .file_publication import atomic_write_bytes
from .runtime_lease import acquire_runtime_state_lease


MAX_RECOVERY_PAYLOAD = 100663296
OPERATION_KINDS = frozenset(
    {
        "native_create",
        "manual_import",
        "markdown_import",
        "pdf_import",
        "content_api_create",
    }
)
ACTIVE_STATES = frozenset({"prepared", "repository_pending", "conflict"})


class CharacterPublicationError(RuntimeError):
    pass


class CharacterPublicationConflict(FileExistsError, CharacterPublicationError):
    pass


class CharacterPublicationExistsError(FileExistsError, CharacterPublicationError):
    pass


class _AuthorityConflict(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class CharacterReconciliationHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class CharacterReconciliationOperation:
    operation_id: str
    campaign_slug: str
    character_slug: str
    operation_kind: str
    desired_definition_digest: str
    desired_import_digest: str
    desired_state_digest: str
    desired_definition_yaml: bytes = field(repr=False, compare=False)
    desired_import_yaml: bytes = field(repr=False, compare=False)
    state: str
    error_code: str


def is_character_reconciliation_protected(
    campaign_slug: str,
    character_slug: str,
) -> bool:
    if not has_app_context():
        return False
    try:
        row = get_db().execute(
            """
            SELECT 1
            FROM character_reconciliation_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return False
        raise
    return row is not None


class CharacterPublicationCoordinator:
    """Atomically commit new Character state, then reconcile its YAML pair forward."""

    def __init__(
        self,
        *,
        campaigns_dir: Path,
        database_path: Path,
        state_store: CharacterStateStore,
        repository: CharacterRepository,
        hooks: CharacterReconciliationHooks | None = None,
    ) -> None:
        self.campaigns_dir = Path(campaigns_dir)
        self.database_path = Path(database_path)
        self.state_store = state_store
        self.repository = repository
        self.hooks = hooks or CharacterReconciliationHooks()
        self._locks_guard = Lock()
        self._character_locks: dict[tuple[str, str], RLock] = {}

    def create(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        initial_state: dict[str, Any],
        *,
        operation_kind: str,
        updated_by_user_id: int | None = None,
    ) -> CharacterRecord:
        self._validate_create_input(definition, import_metadata, operation_kind)
        key = (definition.campaign_slug, definition.character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._prepare_operation(
                    definition,
                    import_metadata,
                    initial_state,
                    operation_kind=operation_kind,
                    updated_by_user_id=updated_by_user_id,
                )
                self._event("after_commit", operation.operation_id)
                return self._continue_operation(operation.operation_id)

    def recover_key(self, campaign_slug: str, character_slug: str) -> bool:
        validate_character_slug(character_slug)
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._load_active_operation(campaign_slug, character_slug)
                if operation is None or operation.state == "conflict":
                    return False
                self._continue_operation(operation.operation_id)
                return True

    def recover_pending(self, *, limit: int = 8) -> dict[str, int]:
        counts = {"recovered": 0, "conflict": 0, "pending": 0}
        with acquire_runtime_state_lease(
            self.database_path,
            timeout_seconds=30.0,
        ):
            rows = get_db().execute(
                """
                SELECT operation_id, campaign_slug, character_slug
                FROM character_reconciliation_operations
                WHERE state IN ('prepared', 'repository_pending')
                ORDER BY updated_at, operation_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            for row in rows:
                key = (str(row["campaign_slug"]), str(row["character_slug"]))
                try:
                    with self._character_lock(key):
                        operation = self._load_operation(str(row["operation_id"]))
                        if operation is None:
                            continue
                        if operation.state == "conflict":
                            counts["conflict"] += 1
                            continue
                        self._continue_operation(operation.operation_id)
                        counts["recovered"] += 1
                except CharacterPublicationConflict:
                    counts["conflict"] += 1
                except (OSError, RuntimeError, ValueError):
                    counts["pending"] += 1
        return counts

    def _validate_create_input(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        operation_kind: str,
    ) -> None:
        if operation_kind not in OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character publication operation.")
        validate_character_slug(definition.character_slug)
        if len(definition.character_slug.encode("utf-8")) > 255:
            raise CharacterPathSafetyError("Character slugs exceed the durable storage limit.")
        campaign_slug = str(definition.campaign_slug)
        if (
            not campaign_slug
            or campaign_slug != campaign_slug.strip().lower()
            or len(campaign_slug.encode("utf-8")) > 128
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in campaign_slug)
        ):
            raise CharacterPublicationError("Campaign slug is invalid for durable character publication.")
        if (
            import_metadata.campaign_slug != campaign_slug
            or import_metadata.character_slug != definition.character_slug
        ):
            raise CharacterPublicationError("Character definition and import metadata identities differ.")

    def _prepare_operation(
        self,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        initial_state: dict[str, Any],
        *,
        operation_kind: str,
        updated_by_user_id: int | None,
    ) -> CharacterReconciliationOperation:
        definition_yaml = render_character_yaml(
            "definition.yaml",
            definition.to_dict(),
        ).encode("utf-8")
        import_yaml = render_character_yaml(
            "import.yaml",
            import_metadata.to_dict(),
        ).encode("utf-8")
        if (
            not definition_yaml
            or not import_yaml
            or len(definition_yaml) + len(import_yaml) > MAX_RECOVERY_PAYLOAD
        ):
            raise CharacterPublicationError("Character recovery payload exceeds the durable storage limit.")
        prepared_state = self.state_store.prepare_initial_state(definition, initial_state)
        operation_id = secrets.token_hex(16)
        now = isoformat(utcnow())
        operation = CharacterReconciliationOperation(
            operation_id=operation_id,
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            operation_kind=operation_kind,
            desired_definition_digest=_digest_bytes(definition_yaml),
            desired_import_digest=_digest_bytes(import_yaml),
            desired_state_digest=_digest_bytes(prepared_state.state_json.encode("utf-8")),
            desired_definition_yaml=definition_yaml,
            desired_import_yaml=import_yaml,
            state="prepared",
            error_code="",
        )
        definition_path, import_path = self._paths(operation.campaign_slug, operation.character_slug)
        connection = get_db()
        self._event("before_prepare", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_state = connection.execute(
                """
                SELECT 1 FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            existing_operation = connection.execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            if (
                existing_state is not None
                or existing_operation is not None
                or _path_exists(definition_path)
                or _path_exists(import_path)
            ):
                raise CharacterPublicationExistsError(
                    f"A character with slug '{operation.character_slug}' already exists in this campaign."
                )
            self.state_store.insert_initial_state_in_transaction(
                connection,
                definition,
                prepared_state,
                updated_at=now,
                updated_by_user_id=updated_by_user_id,
            )
            connection.execute(
                """
                INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    desired_definition_yaml, desired_import_yaml,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', ?, '', ?, '', ?, ?, ?, 'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.operation_kind,
                    operation.desired_definition_digest,
                    operation.desired_import_digest,
                    operation.desired_state_digest,
                    sqlite3.Binary(operation.desired_definition_yaml),
                    sqlite3.Binary(operation.desired_import_yaml),
                    now,
                    now,
                ),
            )
            self._event("before_commit", operation.operation_id)
            connection.commit()
        except CharacterPublicationExistsError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise CharacterPublicationConflict(
                "This character has an active reconciliation operation and requires repair."
            ) from exc
        except BaseException:
            connection.rollback()
            raise
        return operation

    def _continue_operation(self, operation_id: str) -> CharacterRecord:
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterPublicationError("Character reconciliation operation is unavailable.")
        if operation.state == "conflict":
            raise CharacterPublicationConflict(
                "This character has a reconciliation conflict and requires repair."
            )
        if operation.state == "prepared":
            payload_error = self._recovery_payload_error(operation)
            if payload_error is not None:
                self._raise_conflict(operation.operation_id, payload_error)
        definition_path, import_path = self._paths(
            operation.campaign_slug,
            operation.character_slug,
        )
        if operation.state == "prepared":
            self._publish_file(
                operation,
                definition_path,
                operation.desired_definition_yaml,
                operation.desired_definition_digest,
                label="definition",
            )
            self._publish_file(
                operation,
                import_path,
                operation.desired_import_yaml,
                operation.desired_import_digest,
                label="import",
            )
            self._validate_state(operation)
            operation = self._transition_repository_pending(operation)
        return self._refresh_and_cleanup(operation)

    @staticmethod
    def _recovery_payload_error(
        operation: CharacterReconciliationOperation,
    ) -> str | None:
        if (
            not operation.desired_definition_yaml
            or not operation.desired_import_yaml
            or len(operation.desired_definition_yaml)
            + len(operation.desired_import_yaml)
            > MAX_RECOVERY_PAYLOAD
        ):
            return "recovery_payload_invalid"
        if (
            _digest_bytes(operation.desired_definition_yaml)
            != operation.desired_definition_digest
        ):
            return "definition_payload_mismatch"
        if (
            _digest_bytes(operation.desired_import_yaml)
            != operation.desired_import_digest
        ):
            return "import_payload_mismatch"
        return None

    def _publish_file(
        self,
        operation: CharacterReconciliationOperation,
        path: Path,
        payload: bytes,
        desired_digest: str,
        *,
        label: str,
    ) -> None:
        disposition = _classify_create_file(path, desired_digest)
        if disposition == "desired":
            return
        if disposition == "conflict":
            self._raise_conflict(operation.operation_id, f"{label}_digest_conflict")
        self._event(f"before_{label}_publish", operation.operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, payload)
        self._event(f"after_{label}_publish", operation.operation_id)
        if _classify_create_file(path, desired_digest) != "desired":
            self._raise_conflict(operation.operation_id, f"{label}_publish_mismatch")

    def _transition_repository_pending(
        self,
        operation: CharacterReconciliationOperation,
    ) -> CharacterReconciliationOperation:
        connection = get_db()
        self._event("before_repository_pending", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if current is None or not self._same_owner(current, operation):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            if current.state == "repository_pending":
                connection.commit()
                return current
            if current.state != "prepared":
                raise CharacterPublicationConflict("Character reconciliation state changed.")
            self._validate_final_authority(operation, connection=connection)
            now = isoformat(utcnow())
            cursor = connection.execute(
                """
                UPDATE character_reconciliation_operations
                SET state = 'repository_pending', error_code = '', updated_at = ?
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'prepared'
                """,
                (
                    now,
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterPublicationConflict("Character reconciliation state changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_repository_pending", operation.operation_id)
        refreshed = self._load_operation(operation.operation_id)
        if refreshed is None:
            raise CharacterPublicationError("Character reconciliation operation disappeared.")
        return refreshed

    def _refresh_and_cleanup(
        self,
        operation: CharacterReconciliationOperation,
    ) -> CharacterRecord:
        if operation.state != "repository_pending":
            raise CharacterPublicationError("Character publication has not reached its commit point.")
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            self._validate_final_authority(operation, connection=connection)
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self.repository.invalidate_character(operation.campaign_slug, operation.character_slug)
        self._event("before_refresh", operation.operation_id)
        record = self.repository.load_character_for_reconciliation(
            operation.campaign_slug,
            operation.character_slug,
        )
        if record is None:
            raise CharacterPublicationError("Finalized character files were not readable.")
        self._event("after_refresh", operation.operation_id)

        self._event("before_cleanup", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterPublicationConflict("Character reconciliation ownership changed.")
            self._validate_final_authority(operation, connection=connection)
            cursor = connection.execute(
                """
                DELETE FROM character_reconciliation_operations
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'repository_pending'
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterPublicationConflict("Character reconciliation cleanup changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_cleanup", operation.operation_id)
        return record

    def _validate_final_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug,
            operation.character_slug,
        )
        if _classify_create_file(definition_path, operation.desired_definition_digest) != "desired":
            if connection is not None:
                raise _AuthorityConflict("definition_digest_conflict")
            self._raise_conflict(operation.operation_id, "definition_digest_conflict")
        if _classify_create_file(import_path, operation.desired_import_digest) != "desired":
            if connection is not None:
                raise _AuthorityConflict("import_digest_conflict")
            self._raise_conflict(operation.operation_id, "import_digest_conflict")
        self._validate_state(operation, connection=connection)

    def _validate_state(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        db = connection or get_db()
        row = db.execute(
            """
            SELECT revision, state_json
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        if (
            row is None
            or int(row["revision"]) != 1
            or _digest_bytes(str(row["state_json"]).encode("utf-8"))
            != operation.desired_state_digest
        ):
            if connection is not None:
                raise _AuthorityConflict("state_digest_conflict")
            self._raise_conflict(operation.operation_id, "state_digest_conflict")

    def _raise_conflict(self, operation_id: str, error_code: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE character_reconciliation_operations
                SET state = 'conflict', error_code = ?, updated_at = ?
                WHERE operation_id = ?
                  AND state IN ('prepared', 'repository_pending')
                """,
                (error_code, isoformat(utcnow()), operation_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        raise CharacterPublicationConflict(
            "This character has a reconciliation conflict and requires repair."
        )

    def _load_active_operation(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterReconciliationOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return _map_operation(row)

    def _load_operation(
        self,
        operation_id: str,
        *,
        connection: Any | None = None,
    ) -> CharacterReconciliationOperation | None:
        row = (connection or get_db()).execute(
            "SELECT * FROM character_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return _map_operation(row)

    def _paths(self, campaign_slug: str, character_slug: str) -> tuple[Path, Path]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        return (
            resolve_character_path(config.characters_dir, character_slug, "definition.yaml"),
            resolve_character_path(config.characters_dir, character_slug, "import.yaml"),
        )

    @staticmethod
    def _same_owner(
        current: CharacterReconciliationOperation,
        expected: CharacterReconciliationOperation,
    ) -> bool:
        return (
            current.operation_id == expected.operation_id
            and current.campaign_slug == expected.campaign_slug
            and current.character_slug == expected.character_slug
            and current.desired_definition_digest == expected.desired_definition_digest
            and current.desired_import_digest == expected.desired_import_digest
            and current.desired_state_digest == expected.desired_state_digest
        )

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)

    def _character_lock(self, key: tuple[str, str]) -> RLock:
        with self._locks_guard:
            lock = self._character_locks.get(key)
            if lock is None:
                lock = RLock()
                self._character_locks[key] = lock
            return lock


def _map_operation(row: sqlite3.Row | None) -> CharacterReconciliationOperation | None:
    if row is None:
        return None
    return CharacterReconciliationOperation(
        operation_id=str(row["operation_id"]),
        campaign_slug=str(row["campaign_slug"]),
        character_slug=str(row["character_slug"]),
        operation_kind=str(row["operation_kind"]),
        desired_definition_digest=str(row["desired_definition_digest"]),
        desired_import_digest=str(row["desired_import_digest"]),
        desired_state_digest=str(row["desired_state_digest"]),
        desired_definition_yaml=bytes(row["desired_definition_yaml"]),
        desired_import_yaml=bytes(row["desired_import_yaml"]),
        state=str(row["state"]),
        error_code=str(row["error_code"]),
    )


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _classify_create_file(path: Path, desired_digest: str) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return "previous"
    except OSError:
        return "conflict"
    return "desired" if _digest_bytes(data) == desired_digest else "conflict"
