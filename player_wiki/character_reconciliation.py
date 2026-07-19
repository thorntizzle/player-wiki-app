from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import stat
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable

from flask import has_app_context
import yaml

from .auth_store import isoformat, utcnow
from .character_importer import render_character_yaml
from .character_assets import (
    CHARACTER_PORTRAIT_ASSET_EXTENSIONS,
    CHARACTER_PORTRAIT_MAX_BYTES,
    resolve_character_portrait_asset_path,
)
from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_path,
    validate_character_slug,
)
from .character_repository import CharacterRepository, load_campaign_character_config
from .character_store import (
    CharacterStateConflictError,
    CharacterStateStore,
    PreparedCharacterState,
)
from .db import get_db
from .file_publication import (
    atomic_move_file,
    atomic_write_bytes,
    durable_sync_directory,
    durable_unlink_file,
)
from .runtime_lease import acquire_runtime_state_lease


MAX_RECOVERY_PAYLOAD = 100663296
CREATE_OPERATION_KINDS = frozenset(
    {
        "native_create",
        "manual_import",
        "markdown_import",
        "pdf_import",
        "content_api_create",
    }
)
UPDATE_OPERATION_KINDS = frozenset(
    {
        "interactive_update",
        "markdown_import",
        "pdf_import",
        "content_api_update",
        "portrait_upsert",
        "portrait_remove",
    }
)
OPTIONAL_STATE_UPDATE_OPERATION_KINDS = frozenset(
    {"markdown_import", "pdf_import", "content_api_update"}
)
PORTRAIT_OPERATION_KINDS = frozenset({"portrait_upsert", "portrait_remove"})
OPERATION_KINDS = CREATE_OPERATION_KINDS | UPDATE_OPERATION_KINDS
ACTIVE_STATES = frozenset({"prepared", "repository_pending", "conflict"})
DELETE_OPERATION_KINDS = frozenset(
    {"character_controls", "character_controls_api", "content_api"}
)
_CHARACTER_LOCKS_GUARD = Lock()
_CHARACTER_LOCKS: dict[tuple[str, str], RLock] = {}


class CharacterPublicationError(RuntimeError):
    pass


class CharacterPublicationConflict(FileExistsError, CharacterPublicationError):
    pass


class CharacterPublicationExistsError(FileExistsError, CharacterPublicationError):
    pass


class CharacterDeletionError(RuntimeError):
    pass


class CharacterDeletionConflict(CharacterDeletionError):
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
    previous_definition_digest: str
    desired_definition_digest: str
    previous_import_digest: str
    desired_import_digest: str
    previous_state_digest: str
    desired_state_digest: str
    previous_state_revision: int
    desired_state_revision: int
    desired_definition_yaml: bytes = field(repr=False, compare=False)
    desired_import_yaml: bytes = field(repr=False, compare=False)
    previous_asset_ref: str
    desired_asset_ref: str
    previous_asset_digest: str
    desired_asset_digest: str
    desired_asset_bytes: bytes = field(repr=False, compare=False)
    state: str
    error_code: str


@dataclass(frozen=True, slots=True)
class CharacterDeletionHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class CharacterDeletionOperation:
    operation_id: str
    campaign_slug: str
    character_slug: str
    operation_kind: str
    definition_present: bool
    definition_digest: str
    definition_size: int
    definition_tombstone_name: str
    import_present: bool
    import_digest: str
    import_size: int
    import_tombstone_name: str
    asset_present: bool
    asset_ref: str
    asset_digest: str
    asset_size: int
    asset_tombstone_name: str
    previous_state_present: bool
    previous_state_revision: int
    previous_state_digest: str
    previous_assignment_present: bool
    previous_assignment_digest: str
    deleted_files: bool
    deleted_state: bool
    deleted_assignment: bool
    deleted_assets: bool
    audit_event_type: str | None
    audit_actor_user_id: int | None
    audit_target_user_id: int | None
    audit_metadata_json: str | None
    state: str
    error_code: str


@dataclass(frozen=True, slots=True)
class CharacterDeletionResult:
    character_slug: str
    deleted_files: bool
    deleted_state: bool
    deleted_assignment: bool
    deleted_assets: bool


@dataclass(frozen=True, slots=True)
class _DeletionFileEvidence:
    present: bool
    digest: str
    size: int
    tombstone_name: str


def is_character_reconciliation_protected(
    campaign_slug: str,
    character_slug: str,
) -> bool:
    if not has_app_context():
        return False
    try:
        row = get_db().execute(
            """
            SELECT 1 FROM (
                SELECT campaign_slug, character_slug, state
                FROM character_reconciliation_operations
                UNION ALL
                SELECT campaign_slug, character_slug, state
                FROM character_deletion_operations
            ) AS active_character_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table: character_deletion_operations" in str(exc).lower():
            row = get_db().execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                LIMIT 1
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            return row is not None
        if "no such table" in str(exc).lower():
            return False
        raise
    return row is not None


def _character_process_lock(key: tuple[str, str]) -> RLock:
    with _CHARACTER_LOCKS_GUARD:
        lock = _CHARACTER_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _CHARACTER_LOCKS[key] = lock
        return lock


def _has_active_character_deletion(
    connection: Any,
    campaign_slug: str,
    character_slug: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM character_deletion_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        is not None
    )


class CharacterPublicationCoordinator:
    """Commit Character state, then reconcile its YAML pair forward."""

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

    def update(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
        operation_kind: str = "interactive_update",
    ) -> CharacterRecord:
        self._validate_update_input(
            prior_record,
            definition,
            import_metadata,
            expected_revision=expected_revision,
            operation_kind=operation_kind,
        )
        key = (definition.campaign_slug, definition.character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._prepare_update_operation(
                    prior_record,
                    definition,
                    import_metadata,
                    desired_state,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    operation_kind=operation_kind,
                )
                self._event("after_commit", operation.operation_id)
                return self._continue_operation(operation.operation_id)

    def update_portrait(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None,
        operation_kind: str,
        desired_asset_ref: str = "",
        desired_asset_bytes: bytes = b"",
    ) -> CharacterRecord:
        if operation_kind not in PORTRAIT_OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character portrait operation.")
        self._validate_update_input(
            prior_record,
            definition,
            import_metadata,
            expected_revision=expected_revision,
            operation_kind=operation_kind,
        )
        key = (definition.campaign_slug, definition.character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with self._character_lock(key):
                operation = self._prepare_update_operation(
                    prior_record,
                    definition,
                    import_metadata,
                    desired_state,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    operation_kind=operation_kind,
                    desired_asset_ref=desired_asset_ref,
                    desired_asset_bytes=desired_asset_bytes,
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
        if operation_kind not in CREATE_OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character publication operation.")
        self._validate_identity(definition, import_metadata)

    @staticmethod
    def _validate_identity(
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
    ) -> None:
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

    def _validate_update_input(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        *,
        expected_revision: int,
        operation_kind: str,
    ) -> None:
        self._validate_identity(definition, import_metadata)
        if operation_kind not in UPDATE_OPERATION_KINDS:
            raise CharacterPublicationError("Unsupported character update operation.")
        if (
            prior_record.definition.campaign_slug != definition.campaign_slug
            or prior_record.definition.character_slug != definition.character_slug
            or prior_record.import_metadata.campaign_slug != definition.campaign_slug
            or prior_record.import_metadata.character_slug != definition.character_slug
            or prior_record.state_record.campaign_slug != definition.campaign_slug
            or prior_record.state_record.character_slug != definition.character_slug
        ):
            raise CharacterPublicationError("Character update identities differ.")
        if (
            isinstance(expected_revision, bool)
            or int(expected_revision) < 1
            or prior_record.state_record.revision != int(expected_revision)
        ):
            raise CharacterStateConflictError(
                f"State update conflict for {definition.campaign_slug}/{definition.character_slug}"
            )

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
            previous_definition_digest="",
            desired_definition_digest=_digest_bytes(definition_yaml),
            previous_import_digest="",
            desired_import_digest=_digest_bytes(import_yaml),
            previous_state_digest="",
            desired_state_digest=_digest_bytes(prepared_state.state_json.encode("utf-8")),
            previous_state_revision=0,
            desired_state_revision=1,
            desired_definition_yaml=definition_yaml,
            desired_import_yaml=import_yaml,
            previous_asset_ref="",
            desired_asset_ref="",
            previous_asset_digest="",
            desired_asset_digest="",
            desired_asset_bytes=b"",
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
                or _has_active_character_deletion(
                    connection,
                    operation.campaign_slug,
                    operation.character_slug,
                )
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
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    previous_asset_ref, desired_asset_ref,
                    previous_asset_digest, desired_asset_digest,
                    desired_asset_bytes,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', ?, '', ?, '', ?, 0, 1, ?, ?,
                    '', '', '', '', X'', 'prepared', '', ?, ?)
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

    def _prepare_portrait_asset_evidence(
        self,
        prior_record: CharacterRecord,
        *,
        operation_kind: str,
        desired_asset_ref: str,
        desired_asset_bytes: bytes,
    ) -> tuple[str, str, str, str]:
        if operation_kind not in PORTRAIT_OPERATION_KINDS:
            if desired_asset_ref or desired_asset_bytes:
                raise CharacterPublicationError(
                    "Non-portrait updates cannot carry portrait recovery payloads."
                )
            return "", "", "", ""

        previous_asset_ref = str(
            (prior_record.definition.profile or {}).get("portrait_asset_ref") or ""
        ).strip()
        if operation_kind == "portrait_upsert":
            clean_desired_ref = str(desired_asset_ref or "").strip()
            if (
                not clean_desired_ref
                or not desired_asset_bytes
                or len(desired_asset_bytes) > CHARACTER_PORTRAIT_MAX_BYTES
            ):
                raise CharacterPublicationError(
                    "Character portrait recovery payload is invalid."
                )
            self._asset_path(
                prior_record.definition.campaign_slug,
                prior_record.definition.character_slug,
                clean_desired_ref,
            )
        else:
            if desired_asset_ref or desired_asset_bytes or not previous_asset_ref:
                raise CharacterPublicationError(
                    "Character portrait removal evidence is invalid."
                )
            clean_desired_ref = ""

        previous_asset_digest = ""
        if previous_asset_ref:
            previous_path = self._asset_path(
                prior_record.definition.campaign_slug,
                prior_record.definition.character_slug,
                previous_asset_ref,
            )
            previous_asset_digest = _digest_regular_file(previous_path) or ""
            if not previous_asset_digest:
                raise CharacterStateConflictError(
                    "Character portrait changed after it was loaded."
                )

        return (
            previous_asset_ref,
            clean_desired_ref,
            previous_asset_digest,
            _digest_bytes(desired_asset_bytes) if desired_asset_bytes else "",
        )

    def _validate_asset_authority_for_prepare(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if operation.operation_kind not in PORTRAIT_OPERATION_KINDS:
            return
        try:
            if operation.previous_asset_ref:
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                if _digest_regular_file(previous_path) != operation.previous_asset_digest:
                    raise CharacterStateConflictError(
                        "Character portrait changed after it was loaded."
                    )
            if (
                operation.operation_kind == "portrait_upsert"
                and operation.desired_asset_ref != operation.previous_asset_ref
            ):
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                if _digest_regular_file(desired_path) is not None:
                    raise CharacterStateConflictError(
                        "Character portrait target changed after it was loaded."
                    )
        except ValueError as exc:
            raise CharacterStateConflictError(
                "Character portrait changed after it was loaded."
            ) from exc

    def _prepare_update_operation(
        self,
        prior_record: CharacterRecord,
        definition: CharacterDefinition,
        import_metadata: CharacterImportMetadata,
        desired_state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None,
        operation_kind: str,
        desired_asset_ref: str = "",
        desired_asset_bytes: bytes = b"",
    ) -> CharacterReconciliationOperation:
        definition_yaml = render_character_yaml(
            "definition.yaml",
            definition.to_dict(),
        ).encode("utf-8")
        import_yaml = render_character_yaml(
            "import.yaml",
            import_metadata.to_dict(),
        ).encode("utf-8")
        desired_asset_bytes = bytes(desired_asset_bytes)
        if (
            not definition_yaml
            or not import_yaml
            or len(definition_yaml) + len(import_yaml) + len(desired_asset_bytes)
            > MAX_RECOVERY_PAYLOAD
        ):
            raise CharacterPublicationError(
                "Character recovery payload exceeds the durable storage limit."
            )
        prepared_state = self.state_store.prepare_initial_state(definition, desired_state)
        definition_path, import_path = self._paths(
            definition.campaign_slug,
            definition.character_slug,
        )
        previous_definition_yaml = self._read_prior_file(
            definition_path,
            prior_record,
            label="definition",
        )
        previous_import_yaml = self._read_prior_file(
            import_path,
            prior_record,
            label="import",
        )
        connection = get_db()
        previous_state_row = connection.execute(
            """
            SELECT revision, state_json
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (definition.campaign_slug, definition.character_slug),
        ).fetchone()
        previous_state_json = self._validate_prior_state_row(
            previous_state_row,
            prior_record,
            expected_revision=expected_revision,
        )
        state_changed = (
            operation_kind not in OPTIONAL_STATE_UPDATE_OPERATION_KINDS
            or desired_state != prior_record.state_record.state
        )
        desired_state_json = prepared_state.state_json if state_changed else previous_state_json
        if (
            operation_kind in PORTRAIT_OPERATION_KINDS
            and desired_state_json == previous_state_json
        ):
            desired_state_json = json.dumps(
                prepared_state.validated_state,
                sort_keys=True,
                ensure_ascii=False,
            )
        desired_state_revision = int(expected_revision) + (1 if state_changed else 0)
        (
            previous_asset_ref,
            clean_desired_asset_ref,
            previous_asset_digest,
            desired_asset_digest,
        ) = self._prepare_portrait_asset_evidence(
            prior_record,
            operation_kind=operation_kind,
            desired_asset_ref=desired_asset_ref,
            desired_asset_bytes=desired_asset_bytes,
        )
        operation_id = secrets.token_hex(16)
        now = isoformat(utcnow())
        operation = CharacterReconciliationOperation(
            operation_id=operation_id,
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            operation_kind=operation_kind,
            previous_definition_digest=_digest_bytes(previous_definition_yaml),
            desired_definition_digest=_digest_bytes(definition_yaml),
            previous_import_digest=_digest_bytes(previous_import_yaml),
            desired_import_digest=_digest_bytes(import_yaml),
            previous_state_digest=_digest_bytes(previous_state_json.encode("utf-8")),
            desired_state_digest=_digest_bytes(desired_state_json.encode("utf-8")),
            previous_state_revision=int(expected_revision),
            desired_state_revision=desired_state_revision,
            desired_definition_yaml=definition_yaml,
            desired_import_yaml=import_yaml,
            previous_asset_ref=previous_asset_ref,
            desired_asset_ref=clean_desired_asset_ref,
            previous_asset_digest=previous_asset_digest,
            desired_asset_digest=desired_asset_digest,
            desired_asset_bytes=desired_asset_bytes,
            state="prepared",
            error_code="",
        )
        self._event("before_prepare", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            active_operation = connection.execute(
                """
                SELECT 1 FROM character_reconciliation_operations
                WHERE campaign_slug = ? AND character_slug = ?
                  AND state IN ('prepared', 'repository_pending', 'conflict')
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            current_state_row = connection.execute(
                """
                SELECT revision, state_json
                FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (operation.campaign_slug, operation.character_slug),
            ).fetchone()
            if (
                active_operation is not None
                or _has_active_character_deletion(
                    connection,
                    operation.campaign_slug,
                    operation.character_slug,
                )
                or _classify_update_file(
                    definition_path,
                    operation.previous_definition_digest,
                    operation.desired_definition_digest,
                )
                not in {"previous", "desired"}
                or _digest_path(definition_path) != operation.previous_definition_digest
                or _classify_update_file(
                    import_path,
                    operation.previous_import_digest,
                    operation.desired_import_digest,
                )
                not in {"previous", "desired"}
                or _digest_path(import_path) != operation.previous_import_digest
                or current_state_row is None
                or int(current_state_row["revision"]) != operation.previous_state_revision
                or _digest_bytes(str(current_state_row["state_json"]).encode("utf-8"))
                != operation.previous_state_digest
            ):
                raise CharacterStateConflictError(
                    f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
                )
            self._validate_asset_authority_for_prepare(operation)
            if state_changed:
                cursor = connection.execute(
                    """
                    UPDATE character_state
                    SET revision = ?, state_json = ?, updated_at = ?, updated_by_user_id = ?
                    WHERE campaign_slug = ? AND character_slug = ?
                      AND revision = ? AND state_json = ?
                    """,
                    (
                        operation.desired_state_revision,
                        desired_state_json,
                        now,
                        updated_by_user_id,
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.previous_state_revision,
                        previous_state_json,
                    ),
                )
                if cursor.rowcount != 1:
                    raise CharacterStateConflictError(
                        f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
                    )
            connection.execute(
                """
                INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    previous_asset_ref, desired_asset_ref,
                    previous_asset_digest, desired_asset_digest,
                    desired_asset_bytes,
                    state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'prepared', '', ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.operation_kind,
                    operation.previous_definition_digest,
                    operation.desired_definition_digest,
                    operation.previous_import_digest,
                    operation.desired_import_digest,
                    operation.previous_state_digest,
                    operation.desired_state_digest,
                    operation.previous_state_revision,
                    operation.desired_state_revision,
                    sqlite3.Binary(operation.desired_definition_yaml),
                    sqlite3.Binary(operation.desired_import_yaml),
                    operation.previous_asset_ref,
                    operation.desired_asset_ref,
                    operation.previous_asset_digest,
                    operation.desired_asset_digest,
                    sqlite3.Binary(operation.desired_asset_bytes),
                    now,
                    now,
                ),
            )
            self._event("before_commit", operation.operation_id)
            connection.commit()
        except CharacterStateConflictError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise CharacterStateConflictError(
                f"State update conflict for {operation.campaign_slug}/{operation.character_slug}"
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
            if operation.operation_kind in PORTRAIT_OPERATION_KINDS:
                self._validate_prepublication_asset_authority(
                    operation,
                    definition_path=definition_path,
                    import_path=import_path,
                )
            if operation.operation_kind == "portrait_upsert":
                self._publish_portrait_asset(operation)
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
            if operation.operation_kind in PORTRAIT_OPERATION_KINDS:
                self._unlink_superseded_portrait_asset(operation)
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
            + len(operation.desired_asset_bytes)
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
        if operation.operation_kind == "portrait_upsert":
            if (
                not operation.desired_asset_ref
                or not operation.desired_asset_bytes
                or len(operation.desired_asset_bytes) > CHARACTER_PORTRAIT_MAX_BYTES
                or _digest_bytes(operation.desired_asset_bytes)
                != operation.desired_asset_digest
            ):
                return "asset_payload_mismatch"
        elif operation.operation_kind == "portrait_remove":
            if (
                not operation.previous_asset_ref
                or not operation.previous_asset_digest
                or operation.desired_asset_ref
                or operation.desired_asset_digest
                or operation.desired_asset_bytes
            ):
                return "asset_payload_mismatch"
        elif any(
            (
                operation.previous_asset_ref,
                operation.desired_asset_ref,
                operation.previous_asset_digest,
                operation.desired_asset_digest,
                operation.desired_asset_bytes,
            )
        ):
            return "unexpected_asset_payload"
        return None

    def _validate_prepublication_asset_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        definition_path: Path,
        import_path: Path,
    ) -> None:
        yaml_is_desired = (
            _digest_path(definition_path) == operation.desired_definition_digest
            and _digest_path(import_path) == operation.desired_import_digest
        )
        try:
            if operation.previous_asset_ref:
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                previous_digest = _digest_regular_file(previous_path)
                if previous_digest != operation.previous_asset_digest and not (
                    previous_digest is None
                    and yaml_is_desired
                    and operation.previous_asset_ref != operation.desired_asset_ref
                ):
                    self._raise_conflict(
                        operation.operation_id,
                        "previous_asset_digest_conflict",
                    )
            if operation.operation_kind == "portrait_upsert":
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                desired_digest = _digest_regular_file(desired_path)
                allowed = {operation.desired_asset_digest}
                if operation.desired_asset_ref == operation.previous_asset_ref:
                    allowed.add(operation.previous_asset_digest)
                else:
                    allowed.add(None)
                if desired_digest not in allowed:
                    self._raise_conflict(
                        operation.operation_id,
                        "desired_asset_digest_conflict",
                    )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")

    def _publish_portrait_asset(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        try:
            desired_path = self._asset_path(
                operation.campaign_slug,
                operation.character_slug,
                operation.desired_asset_ref,
            )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")
        try:
            current_digest = _digest_regular_file(desired_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "desired_asset_digest_conflict")
        if current_digest == operation.desired_asset_digest:
            return
        expected_previous = (
            operation.previous_asset_digest
            if operation.desired_asset_ref == operation.previous_asset_ref
            else None
        )
        if current_digest != expected_previous:
            self._raise_conflict(operation.operation_id, "desired_asset_digest_conflict")
        self._event("before_asset_publish", operation.operation_id)
        desired_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(desired_path, operation.desired_asset_bytes)
        self._event("after_asset_publish", operation.operation_id)
        try:
            published_digest = _digest_regular_file(desired_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_publish_mismatch")
        if published_digest != operation.desired_asset_digest:
            self._raise_conflict(operation.operation_id, "asset_publish_mismatch")

    def _unlink_superseded_portrait_asset(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if (
            not operation.previous_asset_ref
            or operation.previous_asset_ref == operation.desired_asset_ref
        ):
            return
        try:
            _, previous_path = resolve_character_portrait_asset_path(
                load_campaign_character_config(
                    self.campaigns_dir,
                    operation.campaign_slug,
                ).campaign_dir,
                operation.character_slug,
                operation.previous_asset_ref,
            )
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_ref_invalid")
        try:
            current_digest = _digest_regular_file(previous_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "previous_asset_digest_conflict")
        if current_digest is None:
            durable_sync_directory(previous_path.parent)
            return
        if current_digest != operation.previous_asset_digest:
            self._raise_conflict(operation.operation_id, "previous_asset_digest_conflict")
        self._event("before_asset_unlink", operation.operation_id)
        durable_unlink_file(previous_path)
        self._event("after_asset_unlink", operation.operation_id)
        try:
            remaining_digest = _digest_regular_file(previous_path)
        except ValueError:
            self._raise_conflict(operation.operation_id, "asset_unlink_mismatch")
        if remaining_digest is not None:
            self._raise_conflict(operation.operation_id, "asset_unlink_mismatch")

    def _publish_file(
        self,
        operation: CharacterReconciliationOperation,
        path: Path,
        payload: bytes,
        desired_digest: str,
        *,
        label: str,
    ) -> None:
        previous_digest = (
            operation.previous_definition_digest
            if label == "definition"
            else operation.previous_import_digest
        )
        is_create = operation.previous_state_revision == 0 and previous_digest == ""
        disposition = _classify_publication_file(
            path,
            previous_digest=previous_digest,
            desired_digest=desired_digest,
            is_create=is_create,
        )
        if disposition == "desired":
            return
        if disposition == "conflict":
            self._raise_conflict(operation.operation_id, f"{label}_digest_conflict")
        self._event(f"before_{label}_publish", operation.operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, payload)
        self._event(f"after_{label}_publish", operation.operation_id)
        if (
            _classify_publication_file(
                path,
                previous_digest=previous_digest,
                desired_digest=desired_digest,
                is_create=is_create,
            )
            != "desired"
        ):
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
        self._prune_finalized_portrait_asset_directories(operation)
        return record

    def _prune_finalized_portrait_asset_directories(
        self,
        operation: CharacterReconciliationOperation,
    ) -> None:
        if (
            operation.operation_kind not in PORTRAIT_OPERATION_KINDS
            or not operation.previous_asset_ref
            or operation.previous_asset_ref == operation.desired_asset_ref
        ):
            return
        try:
            assets_root, previous_path = resolve_character_portrait_asset_path(
                load_campaign_character_config(
                    self.campaigns_dir,
                    operation.campaign_slug,
                ).campaign_dir,
                operation.character_slug,
                operation.previous_asset_ref,
            )
        except (OSError, ValueError):
            return
        _prune_empty_asset_directories(previous_path.parent, stop_dir=assets_root)

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
        if _digest_path(definition_path) != operation.desired_definition_digest:
            if connection is not None:
                raise _AuthorityConflict("definition_digest_conflict")
            self._raise_conflict(operation.operation_id, "definition_digest_conflict")
        if _digest_path(import_path) != operation.desired_import_digest:
            if connection is not None:
                raise _AuthorityConflict("import_digest_conflict")
            self._raise_conflict(operation.operation_id, "import_digest_conflict")
        self._validate_state(operation, connection=connection)
        self._validate_final_asset_authority(operation, connection=connection)

    def _validate_final_asset_authority(
        self,
        operation: CharacterReconciliationOperation,
        *,
        connection: Any | None = None,
    ) -> None:
        if operation.operation_kind not in PORTRAIT_OPERATION_KINDS:
            return

        def conflict(error_code: str) -> None:
            if connection is not None:
                raise _AuthorityConflict(error_code)
            self._raise_conflict(operation.operation_id, error_code)

        try:
            if operation.operation_kind == "portrait_upsert":
                desired_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.desired_asset_ref,
                )
                if _digest_regular_file(desired_path) != operation.desired_asset_digest:
                    conflict("desired_asset_digest_conflict")
            if (
                operation.previous_asset_ref
                and operation.previous_asset_ref != operation.desired_asset_ref
            ):
                previous_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.previous_asset_ref,
                )
                if _digest_regular_file(previous_path) is not None:
                    conflict("previous_asset_cleanup_conflict")
        except ValueError:
            conflict("asset_ref_invalid")

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
            or int(row["revision"]) != operation.desired_state_revision
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

    def _asset_path(
        self,
        campaign_slug: str,
        character_slug: str,
        asset_ref: str,
    ) -> Path:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        _, asset_path = resolve_character_portrait_asset_path(
            config.campaign_dir,
            character_slug,
            asset_ref,
        )
        return asset_path

    @staticmethod
    def _read_prior_file(
        path: Path,
        prior_record: CharacterRecord,
        *,
        label: str,
    ) -> bytes:
        try:
            payload_bytes = path.read_bytes()
            payload = yaml.safe_load(payload_bytes.decode("utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError("Character YAML must be a mapping.")
            if label == "definition":
                payload.setdefault("system", prior_record.definition.system)
                normalized = CharacterDefinition.from_dict(payload).to_dict()
                expected = prior_record.definition.to_dict()
            else:
                normalized = CharacterImportMetadata.from_dict(payload).to_dict()
                expected = prior_record.import_metadata.to_dict()
            if normalized != expected:
                raise ValueError("Character YAML no longer matches the loaded record.")
            return payload_bytes
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            raise CharacterStateConflictError(
                f"Character {label} changed after it was loaded."
            ) from exc

    @staticmethod
    def _validate_prior_state_row(
        row: sqlite3.Row | None,
        prior_record: CharacterRecord,
        *,
        expected_revision: int,
    ) -> str:
        if row is None:
            raise CharacterStateConflictError("Character state disappeared after it was loaded.")
        state_json = str(row["state_json"])
        try:
            decoded_state = json.loads(state_json)
        except (TypeError, ValueError) as exc:
            raise CharacterStateConflictError("Character state is unreadable.") from exc
        if (
            int(row["revision"]) != int(expected_revision)
            or prior_record.state_record.revision != int(expected_revision)
            or decoded_state != prior_record.state_record.state
        ):
            raise CharacterStateConflictError(
                f"State update conflict for {prior_record.definition.campaign_slug}/"
                f"{prior_record.definition.character_slug}"
            )
        return state_json

    @staticmethod
    def _same_owner(
        current: CharacterReconciliationOperation,
        expected: CharacterReconciliationOperation,
    ) -> bool:
        return (
            current.operation_id == expected.operation_id
            and current.campaign_slug == expected.campaign_slug
            and current.character_slug == expected.character_slug
            and current.operation_kind == expected.operation_kind
            and current.previous_definition_digest
            == expected.previous_definition_digest
            and current.desired_definition_digest == expected.desired_definition_digest
            and current.previous_import_digest == expected.previous_import_digest
            and current.desired_import_digest == expected.desired_import_digest
            and current.previous_state_digest == expected.previous_state_digest
            and current.desired_state_digest == expected.desired_state_digest
            and current.previous_state_revision == expected.previous_state_revision
            and current.desired_state_revision == expected.desired_state_revision
            and current.previous_asset_ref == expected.previous_asset_ref
            and current.desired_asset_ref == expected.desired_asset_ref
            and current.previous_asset_digest == expected.previous_asset_digest
            and current.desired_asset_digest == expected.desired_asset_digest
        )

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)

    def _character_lock(self, key: tuple[str, str]) -> RLock:
        return _character_process_lock(key)


class CharacterDeletionCoordinator:
    """Commit a character deletion in SQLite, then reconcile files forward."""

    def __init__(
        self,
        *,
        campaigns_dir: Path,
        database_path: Path,
        state_store: CharacterStateStore,
        repository: CharacterRepository,
        auth_store: Any,
        hooks: CharacterDeletionHooks | None = None,
    ) -> None:
        self.campaigns_dir = Path(campaigns_dir)
        self.database_path = Path(database_path)
        self.state_store = state_store
        self.repository = repository
        self.auth_store = auth_store
        self.hooks = hooks or CharacterDeletionHooks()

    def delete(
        self,
        campaign_slug: str,
        character_slug: str,
        *,
        operation_kind: str,
        actor_user_id: int | None = None,
        audit_source: str | None = None,
    ) -> CharacterDeletionResult | None:
        validate_character_slug(character_slug)
        if operation_kind not in DELETE_OPERATION_KINDS:
            raise CharacterDeletionError("Unsupported character deletion operation.")
        if operation_kind == "content_api":
            if actor_user_id is not None or audit_source is not None:
                raise CharacterDeletionError("Raw content deletion cannot create an audit event.")
        elif audit_source != operation_kind:
            raise CharacterDeletionError("Character deletion audit source is invalid.")
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with _character_process_lock(key):
                operation = self._prepare_operation(
                    campaign_slug,
                    character_slug,
                    operation_kind=operation_kind,
                    actor_user_id=actor_user_id,
                    audit_source=audit_source,
                )
                if operation is None:
                    return None
                self._event("after_commit", operation.operation_id)
                return self._continue_operation(operation.operation_id)

    def recover_key(self, campaign_slug: str, character_slug: str) -> bool:
        validate_character_slug(character_slug)
        key = (campaign_slug, character_slug)
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            with _character_process_lock(key):
                operation = self._load_active_operation(campaign_slug, character_slug)
                if operation is None or operation.state == "conflict":
                    return False
                self._continue_operation(operation.operation_id)
                return True

    def recover_pending(self, *, limit: int = 8) -> dict[str, int]:
        counts = {"recovered": 0, "conflict": 0, "pending": 0}
        with acquire_runtime_state_lease(self.database_path, timeout_seconds=30.0):
            rows = get_db().execute(
                """
                SELECT operation_id, campaign_slug, character_slug
                FROM character_deletion_operations
                WHERE state IN ('prepared', 'repository_pending')
                ORDER BY updated_at, operation_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            for row in rows:
                key = (str(row["campaign_slug"]), str(row["character_slug"]))
                try:
                    with _character_process_lock(key):
                        operation = self._load_operation(str(row["operation_id"]))
                        if operation is None:
                            continue
                        if operation.state == "conflict":
                            counts["conflict"] += 1
                            continue
                        self._continue_operation(operation.operation_id)
                        counts["recovered"] += 1
                except CharacterDeletionConflict:
                    counts["conflict"] += 1
                except (OSError, RuntimeError, ValueError):
                    counts["pending"] += 1
        return counts

    def _prepare_operation(
        self,
        campaign_slug: str,
        character_slug: str,
        *,
        operation_kind: str,
        actor_user_id: int | None,
        audit_source: str | None,
    ) -> CharacterDeletionOperation | None:
        definition_path, import_path = self._paths(campaign_slug, character_slug)
        operation_id = secrets.token_hex(16)
        connection = get_db()
        self._event("before_prepare", operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if _has_active_character_publication(connection, campaign_slug, character_slug) or (
                _has_active_character_deletion(connection, campaign_slug, character_slug)
            ):
                raise CharacterDeletionConflict(
                    "This character has an active reconciliation operation and requires repair."
                )

            definition = _capture_deletion_file_evidence(
                definition_path,
                operation_id=operation_id,
                artifact_kind="definition",
                max_size=MAX_RECOVERY_PAYLOAD,
            )
            import_metadata = _capture_deletion_file_evidence(
                import_path,
                operation_id=operation_id,
                artifact_kind="import",
                max_size=MAX_RECOVERY_PAYLOAD,
            )
            definition_asset_ref = (
                _managed_portrait_ref(definition_path) if definition.present else ""
            )
            discovered_asset_ref = self._discover_managed_portrait_ref(
                campaign_slug, character_slug
            )
            if (
                definition_asset_ref
                and discovered_asset_ref
                and definition_asset_ref != discovered_asset_ref
            ):
                raise CharacterDeletionConflict(
                    "Character portrait authority does not match its definition."
                )
            asset_ref = definition_asset_ref or discovered_asset_ref
            asset_path = self._asset_path(campaign_slug, character_slug, asset_ref) if asset_ref else None
            asset = (
                _capture_deletion_file_evidence(
                    asset_path,
                    operation_id=operation_id,
                    artifact_kind="asset",
                    max_size=CHARACTER_PORTRAIT_MAX_BYTES,
                )
                if asset_path is not None
                else _DeletionFileEvidence(False, "", 0, "")
            )
            state_row = connection.execute(
                """
                SELECT revision, state_json
                FROM character_state
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            assignment_row = connection.execute(
                """
                SELECT id, user_id, campaign_slug, character_slug, assignment_type,
                       created_at, updated_at
                FROM character_assignments
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (campaign_slug, character_slug),
            ).fetchone()
            if not any(
                (
                    definition.present,
                    import_metadata.present,
                    asset.present,
                    state_row is not None,
                    assignment_row is not None,
                )
            ):
                connection.rollback()
                return None

            state_revision = int(state_row["revision"]) if state_row is not None else 0
            state_digest = (
                _digest_bytes(str(state_row["state_json"]).encode("utf-8"))
                if state_row is not None
                else ""
            )
            assignment_digest = _digest_sqlite_row(assignment_row) if assignment_row is not None else ""
            deleted_files = definition.present or import_metadata.present
            deleted_state = state_row is not None
            deleted_assignment = assignment_row is not None
            deleted_assets = asset.present
            audit_event_type: str | None = None
            audit_target_user_id: int | None = None
            audit_metadata_json: str | None = None
            if operation_kind != "content_api":
                audit_event_type = "character_deleted"
                audit_target_user_id = (
                    int(assignment_row["user_id"]) if assignment_row is not None else None
                )
                metadata = self.auth_store.sanitize_audit_metadata(
                    {
                        "deleted_files": deleted_files,
                        "deleted_state": deleted_state,
                        "deleted_assignment": deleted_assignment,
                        "deleted_assets": deleted_assets,
                        "source": audit_source,
                    }
                )
                audit_metadata_json = json.dumps(metadata, sort_keys=True)
                if len(audit_metadata_json.encode("utf-8")) > 65536:
                    raise CharacterDeletionError("Character deletion audit metadata is too large.")

            now = isoformat(utcnow())
            connection.execute(
                """
                INSERT INTO character_deletion_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    definition_present, definition_digest, definition_size,
                    definition_tombstone_name,
                    import_present, import_digest, import_size, import_tombstone_name,
                    asset_present, asset_ref, asset_digest, asset_size, asset_tombstone_name,
                    previous_state_present, previous_state_revision, previous_state_digest,
                    previous_assignment_present, previous_assignment_digest,
                    deleted_files, deleted_state, deleted_assignment, deleted_assets,
                    audit_event_type, audit_actor_user_id, audit_target_user_id,
                    audit_metadata_json, state, error_code, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', '', ?, ?)
                """,
                (
                    operation_id,
                    campaign_slug,
                    character_slug,
                    operation_kind,
                    int(definition.present),
                    definition.digest,
                    definition.size,
                    definition.tombstone_name,
                    int(import_metadata.present),
                    import_metadata.digest,
                    import_metadata.size,
                    import_metadata.tombstone_name,
                    int(asset.present),
                    asset_ref if asset.present else "",
                    asset.digest,
                    asset.size,
                    asset.tombstone_name,
                    int(state_row is not None),
                    state_revision,
                    state_digest,
                    int(assignment_row is not None),
                    assignment_digest,
                    int(deleted_files),
                    int(deleted_state),
                    int(deleted_assignment),
                    int(deleted_assets),
                    audit_event_type,
                    actor_user_id if audit_event_type else None,
                    audit_target_user_id,
                    audit_metadata_json,
                    now,
                    now,
                ),
            )
            prepared_operation = self._load_operation(
                operation_id,
                connection=connection,
            )
            if prepared_operation is None:
                raise CharacterDeletionError("Character deletion operation disappeared.")
            self._validate_initial_file_authority(prepared_operation)
            self._validate_prepared_database_authority(
                campaign_slug,
                character_slug,
                state_present=state_row is not None,
                state_revision=state_revision,
                state_digest=state_digest,
                assignment_present=assignment_row is not None,
                assignment_digest=assignment_digest,
                connection=connection,
            )
            if state_row is not None:
                connection.execute(
                    "DELETE FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
                    (campaign_slug, character_slug),
                )
            if assignment_row is not None:
                connection.execute(
                    "DELETE FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?",
                    (campaign_slug, character_slug),
                )
            if audit_event_type is not None:
                self.auth_store.insert_audit_event(
                    event_type=audit_event_type,
                    actor_user_id=actor_user_id,
                    target_user_id=audit_target_user_id,
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                    metadata=json.loads(audit_metadata_json or "{}"),
                    commit=False,
                )
            self._event("before_commit", operation_id)
            self._validate_initial_file_authority(prepared_operation)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterDeletionError("Character deletion operation disappeared.")
        return operation

    def _validate_initial_file_authority(
        self, operation: CharacterDeletionOperation
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, bool, str, int, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(source.with_name(tombstone_name), max_size=max_size)
                    if tombstone_name
                    else None
                )
            except ValueError:
                raise CharacterDeletionConflict(
                    f"Character {label} changed before deletion commit."
                ) from None
            if present:
                if source_evidence != (digest, size) or tombstone_evidence is not None:
                    raise CharacterDeletionConflict(
                        f"Character {label} changed before deletion commit."
                    )
            elif source_evidence is not None or tombstone_evidence is not None:
                raise CharacterDeletionConflict(
                    f"Character {label} changed before deletion commit."
                )

    def _continue_operation(self, operation_id: str) -> CharacterDeletionResult:
        operation = self._load_operation(operation_id)
        if operation is None:
            raise CharacterDeletionError("Character deletion operation is unavailable.")
        if operation.state == "conflict":
            raise CharacterDeletionConflict(
                "This character has a reconciliation conflict and requires repair."
            )
        if operation.state == "prepared":
            self._move_files(operation)
            operation = self._transition_repository_pending(operation)
        return self._refresh_and_cleanup(operation)

    def _move_files(self, operation: CharacterDeletionOperation) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            try:
                asset_path = self._asset_path(
                    operation.campaign_slug,
                    operation.character_slug,
                    operation.asset_ref,
                )
            except ValueError:
                self._raise_conflict(operation.operation_id, "asset_ref_invalid")
            resources.append(
                (
                    "asset",
                    asset_path,
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            tombstone = source.with_name(tombstone_name) if tombstone_name else None
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(tombstone, max_size=max_size)
                    if tombstone is not None
                    else None
                )
            except ValueError:
                self._raise_conflict(operation.operation_id, f"{label}_unsafe")
            expected = (digest, size)
            if not present:
                if source_evidence is not None or tombstone_evidence is not None:
                    self._raise_conflict(operation.operation_id, f"{label}_presence_conflict")
                continue
            if source_evidence == expected and tombstone_evidence is None:
                self._event(f"before_{label}_move", operation.operation_id)
                try:
                    atomic_move_file(source, tombstone)
                except (OSError, ValueError):
                    self._raise_conflict(operation.operation_id, f"{label}_move_conflict")
                self._event(f"after_{label}_move", operation.operation_id)
            elif source_evidence is None and tombstone_evidence == expected:
                pass
            else:
                self._raise_conflict(operation.operation_id, f"{label}_digest_conflict")

    def _transition_repository_pending(
        self, operation: CharacterDeletionOperation
    ) -> CharacterDeletionOperation:
        connection = get_db()
        self._event("before_repository_pending", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if current is None or not self._same_owner(current, operation):
                raise CharacterDeletionConflict("Character deletion ownership changed.")
            if current.state == "repository_pending":
                connection.commit()
                return current
            if current.state != "prepared":
                raise CharacterDeletionConflict("Character deletion state changed.")
            self._validate_deleted_database_authority(operation, connection=connection)
            if _has_active_character_publication(
                connection, operation.campaign_slug, operation.character_slug
            ):
                raise _AuthorityConflict("publication_operation_conflict")
            self._validate_moved_file_authority(operation)
            cursor = connection.execute(
                """
                UPDATE character_deletion_operations
                SET state = 'repository_pending', error_code = '', updated_at = ?
                WHERE operation_id = ? AND campaign_slug = ? AND character_slug = ?
                  AND state = 'prepared'
                """,
                (
                    isoformat(utcnow()),
                    operation.operation_id,
                    operation.campaign_slug,
                    operation.character_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CharacterDeletionConflict("Character deletion state changed.")
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
            raise CharacterDeletionError("Character deletion operation disappeared.")
        return refreshed

    def _refresh_and_cleanup(
        self, operation: CharacterDeletionOperation
    ) -> CharacterDeletionResult:
        if operation.state != "repository_pending":
            raise CharacterDeletionError("Character deletion has not reached its commit point.")
        self.repository.invalidate_character(operation.campaign_slug, operation.character_slug)
        self._event("before_refresh", operation.operation_id)
        if self.repository.get_character(operation.campaign_slug, operation.character_slug) is not None:
            self._raise_conflict(operation.operation_id, "repository_refresh_conflict")
        self._event("after_refresh", operation.operation_id)
        connection = get_db()
        self._event("before_cleanup", operation.operation_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_operation(operation.operation_id, connection=connection)
            if (
                current is None
                or not self._same_owner(current, operation)
                or current.state != "repository_pending"
            ):
                raise CharacterDeletionConflict("Character deletion ownership changed.")
            self._validate_deleted_database_authority(operation, connection=connection)
            if _has_active_character_publication(
                connection, operation.campaign_slug, operation.character_slug
            ):
                raise _AuthorityConflict("publication_operation_conflict")
            self._validate_moved_file_authority(
                operation,
                allow_cleaned_tombstones=True,
            )
            self._cleanup_tombstones(operation)
            self._validate_cleaned_file_authority(operation)
            cursor = connection.execute(
                """
                DELETE FROM character_deletion_operations
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
                raise CharacterDeletionConflict("Character deletion cleanup changed.")
            connection.commit()
        except _AuthorityConflict as exc:
            connection.rollback()
            self._raise_conflict(operation.operation_id, exc.error_code)
        except BaseException:
            connection.rollback()
            raise
        self._event("after_cleanup", operation.operation_id)
        self._prune_empty_directories(operation)
        return CharacterDeletionResult(
            character_slug=operation.character_slug,
            deleted_files=operation.deleted_files,
            deleted_state=operation.deleted_state,
            deleted_assignment=operation.deleted_assignment,
            deleted_assets=operation.deleted_assets,
        )

    def _validate_moved_file_authority(
        self,
        operation: CharacterDeletionOperation,
        *,
        allow_cleaned_tombstones: bool = False,
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, bool, str, int, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_present,
                operation.definition_digest,
                operation.definition_size,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            (
                "import",
                import_path,
                operation.import_present,
                operation.import_digest,
                operation.import_size,
                operation.import_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    True,
                    operation.asset_digest,
                    operation.asset_size,
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, present, digest, size, tombstone_name, max_size in resources:
            tombstone = source.with_name(tombstone_name) if tombstone_name else None
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = (
                    _read_deletion_file(tombstone, max_size=max_size)
                    if tombstone is not None
                    else None
                )
            except ValueError:
                raise _AuthorityConflict(f"{label}_authority_unsafe") from None
            if present:
                if source_evidence is not None or (
                    tombstone_evidence != (digest, size)
                    and not (allow_cleaned_tombstones and tombstone_evidence is None)
                ):
                    raise _AuthorityConflict(f"{label}_tombstone_conflict")
            elif source_evidence is not None or tombstone_evidence is not None:
                raise _AuthorityConflict(f"{label}_presence_conflict")

    def _cleanup_tombstones(self, operation: CharacterDeletionOperation) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, str, str, int]] = []
        if operation.definition_present:
            resources.append(
                (
                    "definition",
                    definition_path,
                    operation.definition_tombstone_name,
                    operation.definition_digest,
                    MAX_RECOVERY_PAYLOAD,
                )
            )
        if operation.import_present:
            resources.append(
                (
                    "import",
                    import_path,
                    operation.import_tombstone_name,
                    operation.import_digest,
                    MAX_RECOVERY_PAYLOAD,
                )
            )
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    operation.asset_tombstone_name,
                    operation.asset_digest,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, tombstone_name, digest, max_size in resources:
            tombstone = source.with_name(tombstone_name)
            try:
                source_evidence = _read_deletion_file(source, max_size=max_size)
                tombstone_evidence = _read_deletion_file(tombstone, max_size=max_size)
            except ValueError:
                raise _AuthorityConflict(f"{label}_cleanup_conflict") from None
            if source_evidence is not None:
                raise _AuthorityConflict(f"{label}_source_reappeared")
            if tombstone_evidence is None:
                durable_sync_directory(tombstone.parent)
                continue
            if tombstone_evidence[0] != digest:
                raise _AuthorityConflict(f"{label}_tombstone_conflict")
            self._event(f"before_{label}_unlink", operation.operation_id)
            durable_unlink_file(tombstone)
            self._event(f"after_{label}_unlink", operation.operation_id)

    def _validate_cleaned_file_authority(
        self, operation: CharacterDeletionOperation
    ) -> None:
        definition_path, import_path = self._paths(
            operation.campaign_slug, operation.character_slug
        )
        resources: list[tuple[str, Path, str, int]] = [
            (
                "definition",
                definition_path,
                operation.definition_tombstone_name,
                MAX_RECOVERY_PAYLOAD,
            ),
            ("import", import_path, operation.import_tombstone_name, MAX_RECOVERY_PAYLOAD),
        ]
        if operation.asset_present:
            resources.append(
                (
                    "asset",
                    self._asset_path(
                        operation.campaign_slug,
                        operation.character_slug,
                        operation.asset_ref,
                    ),
                    operation.asset_tombstone_name,
                    CHARACTER_PORTRAIT_MAX_BYTES,
                )
            )
        for label, source, tombstone_name, max_size in resources:
            try:
                if _read_deletion_file(source, max_size=max_size) is not None:
                    raise _AuthorityConflict(f"{label}_source_reappeared")
                if tombstone_name and _read_deletion_file(
                    source.with_name(tombstone_name), max_size=max_size
                ) is not None:
                    raise _AuthorityConflict(f"{label}_tombstone_remained")
            except ValueError:
                raise _AuthorityConflict(f"{label}_cleanup_conflict") from None

    @staticmethod
    def _validate_prepared_database_authority(
        campaign_slug: str,
        character_slug: str,
        *,
        state_present: bool,
        state_revision: int,
        state_digest: str,
        assignment_present: bool,
        assignment_digest: str,
        connection: Any,
    ) -> None:
        state_row = connection.execute(
            "SELECT revision, state_json FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
            (campaign_slug, character_slug),
        ).fetchone()
        assignment_row = connection.execute(
            """
            SELECT id, user_id, campaign_slug, character_slug, assignment_type,
                   created_at, updated_at
            FROM character_assignments
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        if state_present != (state_row is not None) or (
            state_row is not None
            and (
                int(state_row["revision"]) != state_revision
                or _digest_bytes(str(state_row["state_json"]).encode("utf-8")) != state_digest
            )
        ):
            raise CharacterDeletionConflict("Character state changed before deletion commit.")
        if assignment_present != (assignment_row is not None) or (
            assignment_row is not None and _digest_sqlite_row(assignment_row) != assignment_digest
        ):
            raise CharacterDeletionConflict("Character assignment changed before deletion commit.")

    @staticmethod
    def _validate_deleted_database_authority(
        operation: CharacterDeletionOperation,
        *,
        connection: Any,
    ) -> None:
        state_row = connection.execute(
            "SELECT 1 FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        assignment_row = connection.execute(
            "SELECT 1 FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?",
            (operation.campaign_slug, operation.character_slug),
        ).fetchone()
        if state_row is not None:
            raise _AuthorityConflict("state_reappeared")
        if assignment_row is not None:
            raise _AuthorityConflict("assignment_reappeared")

    def _raise_conflict(self, operation_id: str, error_code: str) -> None:
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE character_deletion_operations
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
        raise CharacterDeletionConflict(
            "This character has a reconciliation conflict and requires repair."
        )

    def _load_active_operation(
        self, campaign_slug: str, character_slug: str
    ) -> CharacterDeletionOperation | None:
        row = get_db().execute(
            """
            SELECT * FROM character_deletion_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return _map_deletion_operation(row)

    def _load_operation(
        self, operation_id: str, *, connection: Any | None = None
    ) -> CharacterDeletionOperation | None:
        row = (connection or get_db()).execute(
            "SELECT * FROM character_deletion_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return _map_deletion_operation(row)

    def _paths(self, campaign_slug: str, character_slug: str) -> tuple[Path, Path]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        return (
            resolve_character_path(config.characters_dir, character_slug, "definition.yaml"),
            resolve_character_path(config.characters_dir, character_slug, "import.yaml"),
        )

    def _asset_path(self, campaign_slug: str, character_slug: str, asset_ref: str) -> Path:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        _, asset_path = resolve_character_portrait_asset_path(
            config.campaign_dir, character_slug, asset_ref
        )
        return asset_path

    def _discover_managed_portrait_ref(
        self, campaign_slug: str, character_slug: str
    ) -> str:
        matches: list[str] = []
        for extension in sorted(CHARACTER_PORTRAIT_ASSET_EXTENSIONS):
            asset_ref = f"characters/{character_slug}/portrait{extension}"
            try:
                evidence = _read_deletion_file(
                    self._asset_path(campaign_slug, character_slug, asset_ref),
                    max_size=CHARACTER_PORTRAIT_MAX_BYTES,
                )
            except ValueError:
                raise CharacterDeletionConflict(
                    "Character portrait evidence is unsafe."
                ) from None
            if evidence is not None:
                matches.append(asset_ref)
        if len(matches) > 1:
            raise CharacterDeletionConflict(
                "Character portrait ownership is ambiguous."
            )
        return matches[0] if matches else ""

    @staticmethod
    def _same_owner(
        current: CharacterDeletionOperation, expected: CharacterDeletionOperation
    ) -> bool:
        return current == expected

    def _prune_empty_directories(self, operation: CharacterDeletionOperation) -> None:
        try:
            definition_path, _ = self._paths(
                operation.campaign_slug, operation.character_slug
            )
            _prune_empty_asset_directories(
                definition_path.parent,
                stop_dir=definition_path.parent.parent,
            )
            if operation.asset_present:
                assets_root, asset_path = resolve_character_portrait_asset_path(
                    load_campaign_character_config(
                        self.campaigns_dir, operation.campaign_slug
                    ).campaign_dir,
                    operation.character_slug,
                    operation.asset_ref,
                )
                _prune_empty_asset_directories(asset_path.parent, stop_dir=assets_root)
        except (OSError, ValueError):
            return

    def _event(self, event: str, operation_id: str) -> None:
        if self.hooks.on_event is not None:
            self.hooks.on_event(event, operation_id)


def _map_operation(row: sqlite3.Row | None) -> CharacterReconciliationOperation | None:
    if row is None:
        return None
    return CharacterReconciliationOperation(
        operation_id=str(row["operation_id"]),
        campaign_slug=str(row["campaign_slug"]),
        character_slug=str(row["character_slug"]),
        operation_kind=str(row["operation_kind"]),
        previous_definition_digest=str(row["previous_definition_digest"]),
        desired_definition_digest=str(row["desired_definition_digest"]),
        previous_import_digest=str(row["previous_import_digest"]),
        desired_import_digest=str(row["desired_import_digest"]),
        previous_state_digest=str(row["previous_state_digest"]),
        desired_state_digest=str(row["desired_state_digest"]),
        previous_state_revision=int(row["previous_state_revision"]),
        desired_state_revision=int(row["desired_state_revision"]),
        desired_definition_yaml=bytes(row["desired_definition_yaml"]),
        desired_import_yaml=bytes(row["desired_import_yaml"]),
        previous_asset_ref=str(row["previous_asset_ref"]),
        desired_asset_ref=str(row["desired_asset_ref"]),
        previous_asset_digest=str(row["previous_asset_digest"]),
        desired_asset_digest=str(row["desired_asset_digest"]),
        desired_asset_bytes=bytes(row["desired_asset_bytes"]),
        state=str(row["state"]),
        error_code=str(row["error_code"]),
    )


def _map_deletion_operation(row: sqlite3.Row | None) -> CharacterDeletionOperation | None:
    if row is None:
        return None
    return CharacterDeletionOperation(
        operation_id=str(row["operation_id"]),
        campaign_slug=str(row["campaign_slug"]),
        character_slug=str(row["character_slug"]),
        operation_kind=str(row["operation_kind"]),
        definition_present=bool(row["definition_present"]),
        definition_digest=str(row["definition_digest"]),
        definition_size=int(row["definition_size"]),
        definition_tombstone_name=str(row["definition_tombstone_name"]),
        import_present=bool(row["import_present"]),
        import_digest=str(row["import_digest"]),
        import_size=int(row["import_size"]),
        import_tombstone_name=str(row["import_tombstone_name"]),
        asset_present=bool(row["asset_present"]),
        asset_ref=str(row["asset_ref"]),
        asset_digest=str(row["asset_digest"]),
        asset_size=int(row["asset_size"]),
        asset_tombstone_name=str(row["asset_tombstone_name"]),
        previous_state_present=bool(row["previous_state_present"]),
        previous_state_revision=int(row["previous_state_revision"]),
        previous_state_digest=str(row["previous_state_digest"]),
        previous_assignment_present=bool(row["previous_assignment_present"]),
        previous_assignment_digest=str(row["previous_assignment_digest"]),
        deleted_files=bool(row["deleted_files"]),
        deleted_state=bool(row["deleted_state"]),
        deleted_assignment=bool(row["deleted_assignment"]),
        deleted_assets=bool(row["deleted_assets"]),
        audit_event_type=(
            str(row["audit_event_type"]) if row["audit_event_type"] is not None else None
        ),
        audit_actor_user_id=(
            int(row["audit_actor_user_id"])
            if row["audit_actor_user_id"] is not None
            else None
        ),
        audit_target_user_id=(
            int(row["audit_target_user_id"])
            if row["audit_target_user_id"] is not None
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


def _has_active_character_publication(
    connection: Any,
    campaign_slug: str,
    character_slug: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE campaign_slug = ? AND character_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            LIMIT 1
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        is not None
    )


def _capture_deletion_file_evidence(
    path: Path,
    *,
    operation_id: str,
    artifact_kind: str,
    max_size: int,
) -> _DeletionFileEvidence:
    evidence = _read_deletion_file(path, max_size=max_size)
    if evidence is None:
        return _DeletionFileEvidence(False, "", 0, "")
    digest, size = evidence
    return _DeletionFileEvidence(
        True,
        digest,
        size,
        f".character-delete-{operation_id}-{artifact_kind}.tombstone",
    )


def _read_deletion_file(path: Path, *, max_size: int) -> tuple[str, int] | None:
    try:
        details = Path(path).lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Character deletion evidence is unreadable.") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)
        or details.st_size < 1
        or details.st_size > max_size
    ):
        raise ValueError("Character deletion evidence is unsafe.")
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("Character deletion evidence is unreadable.") from exc
    if len(payload) != details.st_size or not payload:
        raise ValueError("Character deletion evidence changed while it was read.")
    return _digest_bytes(payload), len(payload)


def _managed_portrait_ref(definition_path: Path) -> str:
    try:
        payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CharacterDeletionError("Character definition is unreadable.") from exc
    if not isinstance(payload, dict):
        raise CharacterDeletionError("Character definition is unreadable.")
    profile = payload.get("profile") or {}
    if not isinstance(profile, dict):
        raise CharacterDeletionError("Character portrait metadata is invalid.")
    return str(profile.get("portrait_asset_ref") or "").strip()


def _digest_sqlite_row(row: sqlite3.Row) -> str:
    payload = {key: row[key] for key in row.keys()}
    return _digest_bytes(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
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


def _digest_path(path: Path) -> str | None:
    try:
        return _digest_bytes(path.read_bytes())
    except (FileNotFoundError, OSError):
        return None


def _digest_regular_file(path: Path) -> str | None:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Character portrait asset is unreadable.") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)
    ):
        raise ValueError("Character portrait asset is unsafe.")
    try:
        return _digest_bytes(path.read_bytes())
    except OSError as exc:
        raise ValueError("Character portrait asset is unreadable.") from exc


def _prune_empty_asset_directories(path: Path, *, stop_dir: Path) -> None:
    current = Path(path)
    stop = Path(stop_dir)
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _classify_update_file(
    path: Path,
    previous_digest: str,
    desired_digest: str,
) -> str:
    digest = _digest_path(path)
    if digest == desired_digest:
        return "desired"
    if digest == previous_digest:
        return "previous"
    return "conflict"


def _classify_publication_file(
    path: Path,
    *,
    previous_digest: str,
    desired_digest: str,
    is_create: bool,
) -> str:
    if is_create:
        return _classify_create_file(path, desired_digest)
    return _classify_update_file(path, previous_digest, desired_digest)
