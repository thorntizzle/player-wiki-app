from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .auth_store import isoformat, parse_timestamp, utcnow
from .character_models import CharacterDefinition, CharacterStateRecord
from .character_service import validate_state
from .db import get_db


class CharacterStateConflictError(RuntimeError):
    pass


@dataclass(slots=True)
class CharacterStateWriteResult:
    record: CharacterStateRecord
    created: bool


class CharacterStateStore:
    def get_state(self, campaign_slug: str, character_slug: str) -> CharacterStateRecord | None:
        row = get_db().execute(
            """
            SELECT campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return self._map_state(row)

    def initialize_state_if_missing(
        self,
        definition: CharacterDefinition,
        state: dict[str, Any],
        *,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateWriteResult:
        existing = self.get_state(definition.campaign_slug, definition.character_slug)
        if existing is not None:
            return CharacterStateWriteResult(record=existing, created=False)

        validated = validate_state(definition, state)
        connection = get_db()
        connection.execute(
            """
            INSERT INTO character_state (
                campaign_slug,
                character_slug,
                revision,
                state_json,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, ?, 1, ?, ?, ?)
            """,
            (
                definition.campaign_slug,
                definition.character_slug,
                json.dumps(validated, sort_keys=True),
                isoformat(utcnow()),
                updated_by_user_id,
            ),
        )
        connection.commit()
        created = self.get_state(definition.campaign_slug, definition.character_slug)
        if created is None:
            raise RuntimeError("Failed to initialize character state")
        return CharacterStateWriteResult(record=created, created=True)

    def replace_state(
        self,
        definition: CharacterDefinition,
        state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        validated = validate_state(definition, state)
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE character_state
            SET revision = revision + 1,
                state_json = ?,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND character_slug = ? AND revision = ?
            """,
            (
                json.dumps(validated, sort_keys=True),
                isoformat(utcnow()),
                updated_by_user_id,
                definition.campaign_slug,
                definition.character_slug,
                expected_revision,
            ),
        )
        connection.commit()
        if cursor.rowcount != 1:
            raise CharacterStateConflictError(
                f"State update conflict for {definition.campaign_slug}/{definition.character_slug}"
            )
        record = self.get_state(definition.campaign_slug, definition.character_slug)
        if record is None:
            raise RuntimeError("Character state disappeared after update")
        return record

    def delete_state(self, campaign_slug: str, character_slug: str) -> CharacterStateRecord | None:
        existing = self.get_state(campaign_slug, character_slug)
        if existing is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        )
        connection.commit()
        return existing

    def _map_state(self, row: sqlite3.Row | None) -> CharacterStateRecord | None:
        if row is None:
            return None
        return CharacterStateRecord(
            campaign_slug=str(row["campaign_slug"]),
            character_slug=str(row["character_slug"]),
            revision=int(row["revision"]),
            state=json.loads(row["state_json"]),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )
