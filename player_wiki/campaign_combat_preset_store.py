from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .auth_store import isoformat, parse_timestamp, utcnow
from .combat_preset_models import (
    CampaignCombatPresetEntryInput,
    CampaignCombatPresetEntryRecord,
    CampaignCombatPresetRecord,
)
from .db import get_db
from .source_health import (
    SourceHealthConsumer,
    SourceHealthCursorError,
    SourceHealthInventoryPage,
    SourceHealthReference,
)
from .character_path_safety import CharacterPathSafetyError, validate_character_slug


_COMBAT_SEED_VERSION_SCHEME = "combat-seed-v1-sha256"
_SOURCE_HEALTH_VERSION_RE = re.compile(r"^[0-9a-f]{64}$")
_SQLITE_MAX_INTEGER = 2**63 - 1


def _parse_preset_source_health_cursor(continuation: str) -> tuple[int, str]:
    if continuation == "":
        return 0, ""
    if not isinstance(continuation, str):
        raise SourceHealthCursorError("Invalid encounter preset cursor.")
    parts = continuation.split(":")
    if len(parts) != 3 or parts[0] != "ph1":
        raise SourceHealthCursorError("Invalid encounter preset cursor.")
    offset_text, digest = parts[1:]
    if (
        not offset_text
        or offset_text[0] not in "123456789"
        or any(character not in "0123456789" for character in offset_text[1:])
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SourceHealthCursorError("Invalid encounter preset cursor.")
    offset = int(offset_text)
    if offset > _SQLITE_MAX_INTEGER:
        raise SourceHealthCursorError("Invalid encounter preset cursor.")
    return offset, digest


def _preset_source_health_anchor_digest(campaign_slug: str, row) -> str:
    payload = {
        "campaign": campaign_slug,
        "owner": "presets",
        "row": {
            "id": row["id"],
            "preset_id": row["preset_id"],
            "source_kind": row["source_kind"],
            "source_ref": row["source_ref"],
            "source_version": row["source_version"],
            "version_scheme": row["version_scheme"],
        },
        "version": "ph1",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _preset_source_health_consumer_key(
    campaign_slug: str,
    preset_id: int,
    entry_id: int,
) -> str:
    encoded = json.dumps(
        {
            "campaign": campaign_slug,
            "entry_id": entry_id,
            "owner": "presets",
            "preset_id": preset_id,
            "version": 1,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"preset-entry:{hashlib.sha256(encoded).hexdigest()}"


class CampaignCombatPresetConflictError(RuntimeError):
    """A bounded aggregate conflict, including stale, missing, or invalid input."""


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetStoreHooks:
    before_entry_write: Callable[[str, int], None] | None = None


class CampaignCombatPresetStore:
    def __init__(self, *, hooks: CampaignCombatPresetStoreHooks | None = None) -> None:
        self._hooks = hooks or CampaignCombatPresetStoreHooks()

    def list_presets(
        self,
        campaign_slug: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CampaignCombatPresetRecord]:
        if limit is None:
            rows = get_db().execute(
                """
                SELECT *
                FROM campaign_encounter_presets
                WHERE campaign_slug = ?
                ORDER BY name_key, id
                """,
                (campaign_slug,),
            ).fetchall()
        else:
            rows = get_db().execute(
                """
                SELECT *
                FROM campaign_encounter_presets
                WHERE campaign_slug = ?
                ORDER BY name_key, id
                LIMIT ? OFFSET ?
                """,
                (campaign_slug, limit, offset),
            ).fetchall()
        return [self._map_preset(row, ()) for row in rows]

    def count_presets_up_to(
        self,
        campaign_slug: str,
        *,
        limit: int,
    ) -> int:
        rows = get_db().execute(
            """
            SELECT 1
            FROM campaign_encounter_presets
            WHERE campaign_slug = ?
            ORDER BY id
            LIMIT ?
            """,
            (campaign_slug, limit),
        ).fetchall()
        return len(rows)

    def list_source_health_consumers(
        self,
        campaign_slug: str,
        *,
        continuation: str = "",
        limit: int = 50,
        library_slug: str = "",
        system_code: str = "",
    ) -> SourceHealthInventoryPage:
        """Read one stable, campaign-confined page of source-backed preset rows."""

        page_limit = min(max(int(limit), 1), 50)
        offset, anchor_digest = _parse_preset_source_health_cursor(continuation)
        query_offset = offset - 1 if offset else 0
        query_limit = page_limit + 2 if offset else page_limit + 1
        rows = get_db().execute(
            """
            SELECT id, preset_id, source_kind, source_ref,
                   source_version, version_scheme
            FROM campaign_encounter_preset_entries
            WHERE campaign_slug = ?
              AND source_kind IN ('character', 'dm_statblock', 'systems_monster')
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (campaign_slug, query_limit, query_offset),
        ).fetchall()
        if offset:
            if (
                not rows
                or _preset_source_health_anchor_digest(campaign_slug, rows[0])
                != anchor_digest
            ):
                raise SourceHealthCursorError("Encounter preset cursor is stale.")
            candidates = rows[1:]
        else:
            candidates = rows

        has_more = len(candidates) > page_limit
        selected = candidates[:page_limit]
        consumers: list[SourceHealthConsumer] = []
        for row in selected:
            entry_id = int(row["id"])
            preset_id = int(row["preset_id"])
            source_kind = str(row["source_kind"] or "")
            source_ref = str(row["source_ref"] or "")
            source_version = row["source_version"]
            version_scheme = row["version_scheme"]
            if (
                not source_ref
                or source_ref != source_ref.strip()
                or version_scheme != _COMBAT_SEED_VERSION_SCHEME
                or not isinstance(source_version, str)
                or _SOURCE_HEALTH_VERSION_RE.fullmatch(source_version) is None
            ):
                raise ValueError("Invalid durable encounter preset source reference.")
            if source_kind == "character":
                try:
                    validate_character_slug(source_ref)
                except CharacterPathSafetyError as exc:
                    raise ValueError(
                        "Invalid durable encounter preset source reference."
                    ) from exc
                reference = SourceHealthReference(
                    target_kind="character",
                    target_id=source_ref,
                    consumer_version=source_version,
                    version_scheme=version_scheme,
                )
                accepted_types = ("character",)
            elif source_kind == "dm_statblock":
                if (
                    not source_ref.isdecimal()
                    or str(int(source_ref)) != source_ref
                    or int(source_ref) < 1
                ):
                    raise ValueError("Invalid durable encounter preset source reference.")
                reference = SourceHealthReference(
                    target_kind="dm_statblock",
                    target_id=source_ref,
                    consumer_version=source_version,
                    version_scheme=version_scheme,
                )
                accepted_types = ("dm_statblock",)
            else:
                reference = SourceHealthReference(
                    target_kind="systems",
                    library_slug=str(library_slug or "").strip(),
                    entry_key=source_ref,
                    system_code=str(system_code or "").strip(),
                    consumer_version=source_version,
                    version_scheme=version_scheme,
                )
                accepted_types = ("monster",)
            consumers.append(
                SourceHealthConsumer(
                    consumer_type="encounter-preset-entry",
                    consumer_key=_preset_source_health_consumer_key(
                        campaign_slug,
                        preset_id,
                        entry_id,
                    ),
                    surface="Encounter preset",
                    reference=reference,
                    accepted_target_types=accepted_types,
                )
            )

        return SourceHealthInventoryPage(
            consumers=tuple(consumers),
            continuation=(
                "ph1:"
                f"{offset + len(selected)}:"
                f"{_preset_source_health_anchor_digest(campaign_slug, selected[-1])}"
                if has_more and selected
                else ""
            ),
        )

    def get_preset(
        self,
        campaign_slug: str,
        preset_id: int,
    ) -> CampaignCombatPresetRecord | None:
        connection = get_db()
        row = connection.execute(
            """
            SELECT *
            FROM campaign_encounter_presets
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, preset_id),
        ).fetchone()
        if row is None:
            return None
        entry_rows = connection.execute(
            """
            SELECT *
            FROM campaign_encounter_preset_entries
            WHERE campaign_slug = ? AND preset_id = ?
            ORDER BY position, id
            """,
            (campaign_slug, preset_id),
        ).fetchall()
        entries = tuple(self._map_entry(entry_row) for entry_row in entry_rows)
        return self._map_preset(row, entries)

    def create_preset(
        self,
        campaign_slug: str,
        *,
        name: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
        created_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatPresetRecord:
        normalized_name, name_key = normalize_preset_name(name)
        normalized_entries = tuple(_coerce_entry_input(entry) for entry in entries)
        if any(entry.id is not None for entry in normalized_entries):
            raise CampaignCombatPresetConflictError("Unable to create encounter preset.")
        connection = get_db()
        now_text = isoformat(utcnow())
        try:
            if commit:
                connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO campaign_encounter_presets (
                    campaign_slug, name, name_key, revision,
                    created_at, updated_at, created_by_user_id, updated_by_user_id
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    campaign_slug,
                    normalized_name,
                    name_key,
                    now_text,
                    now_text,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
            preset_id = int(cursor.lastrowid)
            entry_records = tuple(
                self._insert_entry(
                    connection,
                    operation="create",
                    campaign_slug=campaign_slug,
                    preset_id=preset_id,
                    position=position,
                    entry=entry,
                    now_text=now_text,
                    created_by_user_id=created_by_user_id,
                    updated_by_user_id=created_by_user_id,
                )
                for position, entry in enumerate(normalized_entries)
            )
            if commit:
                connection.commit()
        except sqlite3.IntegrityError as exc:
            if commit:
                connection.rollback()
            raise CampaignCombatPresetConflictError(
                "Unable to create encounter preset."
            ) from exc
        except BaseException:
            if commit:
                connection.rollback()
            raise

        created_at = parse_timestamp(now_text)
        if created_at is None:
            raise RuntimeError("Failed to map encounter preset timestamp.")
        return CampaignCombatPresetRecord(
            id=preset_id,
            campaign_slug=campaign_slug,
            name=normalized_name,
            name_key=name_key,
            revision=1,
            created_at=created_at,
            updated_at=created_at,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=created_by_user_id,
            entries=entry_records,
        )

    def update_preset(
        self,
        campaign_slug: str,
        preset_id: int,
        *,
        expected_revision: int,
        name: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatPresetRecord:
        normalized_name, name_key = normalize_preset_name(name)
        normalized_entries = tuple(_coerce_entry_input(entry) for entry in entries)
        retained_ids = [entry.id for entry in normalized_entries if entry.id is not None]
        if len(retained_ids) != len(set(retained_ids)):
            raise CampaignCombatPresetConflictError("Unable to update encounter preset.")

        connection = get_db()
        now_text = isoformat(utcnow())
        try:
            if commit:
                connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT id
                FROM campaign_encounter_presets
                WHERE campaign_slug = ? AND id = ? AND revision = ?
                """,
                (campaign_slug, preset_id, expected_revision),
            ).fetchone()
            if parent is None:
                raise CampaignCombatPresetConflictError(
                    "Unable to update encounter preset."
                )
            existing_rows = connection.execute(
                """
                SELECT id, position
                FROM campaign_encounter_preset_entries
                WHERE campaign_slug = ? AND preset_id = ?
                ORDER BY id
                """,
                (campaign_slug, preset_id),
            ).fetchall()
            existing_ids = {int(row["id"]) for row in existing_rows}
            if any(entry_id not in existing_ids for entry_id in retained_ids):
                raise CampaignCombatPresetConflictError(
                    "Unable to update encounter preset."
                )

            cursor = connection.execute(
                """
                UPDATE campaign_encounter_presets
                SET name = ?, name_key = ?, revision = revision + 1,
                    updated_at = ?, updated_by_user_id = ?
                WHERE campaign_slug = ? AND id = ? AND revision = ?
                """,
                (
                    normalized_name,
                    name_key,
                    now_text,
                    updated_by_user_id,
                    campaign_slug,
                    preset_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CampaignCombatPresetConflictError(
                    "Unable to update encounter preset."
                )

            if existing_rows:
                max_position = max(int(row["position"]) for row in existing_rows)
                offset = max_position + len(existing_rows) + 1
                connection.execute(
                    """
                    UPDATE campaign_encounter_preset_entries
                    SET position = position + ?
                    WHERE campaign_slug = ? AND preset_id = ?
                    """,
                    (offset, campaign_slug, preset_id),
                )

            if retained_ids:
                placeholders = ", ".join("?" for _ in retained_ids)
                connection.execute(
                    f"""
                    DELETE FROM campaign_encounter_preset_entries
                    WHERE campaign_slug = ? AND preset_id = ?
                      AND id NOT IN ({placeholders})
                    """,
                    (campaign_slug, preset_id, *retained_ids),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM campaign_encounter_preset_entries
                    WHERE campaign_slug = ? AND preset_id = ?
                    """,
                    (campaign_slug, preset_id),
                )

            for position, entry in enumerate(normalized_entries):
                self._invoke_entry_hook("update", position)
                if entry.id is None:
                    self._insert_entry(
                        connection,
                        operation=None,
                        campaign_slug=campaign_slug,
                        preset_id=preset_id,
                        position=position,
                        entry=entry,
                        now_text=now_text,
                        created_by_user_id=updated_by_user_id,
                        updated_by_user_id=updated_by_user_id,
                    )
                    continue
                updated = connection.execute(
                    """
                    UPDATE campaign_encounter_preset_entries
                    SET position = ?, source_kind = ?, source_ref = ?,
                        source_version = ?, version_scheme = ?, quantity = ?,
                        turn_value = ?, initiative_priority = ?, custom_name = ?,
                        initiative_bonus = ?, dexterity_modifier = ?, max_hp = ?,
                        movement_total = ?, updated_at = ?, updated_by_user_id = ?
                    WHERE campaign_slug = ? AND preset_id = ? AND id = ?
                    """,
                    (
                        position,
                        entry.source_kind,
                        entry.source_ref.strip(),
                        _strip_optional(entry.source_version),
                        _strip_optional(entry.version_scheme),
                        entry.quantity,
                        entry.turn_value,
                        entry.initiative_priority,
                        entry.custom_name.strip(),
                        entry.initiative_bonus,
                        entry.dexterity_modifier,
                        entry.max_hp,
                        entry.movement_total,
                        now_text,
                        updated_by_user_id,
                        campaign_slug,
                        preset_id,
                        entry.id,
                    ),
                )
                if updated.rowcount != 1:
                    raise CampaignCombatPresetConflictError(
                        "Unable to update encounter preset."
                    )

            refreshed = self.get_preset(campaign_slug, preset_id)
            if refreshed is None:
                raise RuntimeError("Encounter preset disappeared during update.")
            if commit:
                connection.commit()
        except sqlite3.IntegrityError as exc:
            if commit:
                connection.rollback()
            raise CampaignCombatPresetConflictError(
                "Unable to update encounter preset."
            ) from exc
        except BaseException:
            if commit:
                connection.rollback()
            raise
        return refreshed

    def delete_preset(
        self,
        campaign_slug: str,
        preset_id: int,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> None:
        connection = get_db()
        try:
            if commit:
                connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                DELETE FROM campaign_encounter_presets
                WHERE campaign_slug = ? AND id = ? AND revision = ?
                """,
                (campaign_slug, preset_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise CampaignCombatPresetConflictError(
                    "Unable to delete encounter preset."
                )
            if commit:
                connection.commit()
        except sqlite3.IntegrityError as exc:
            if commit:
                connection.rollback()
            raise CampaignCombatPresetConflictError(
                "Unable to delete encounter preset."
            ) from exc
        except BaseException:
            if commit:
                connection.rollback()
            raise

    def _insert_entry(
        self,
        connection,
        *,
        operation: str | None,
        campaign_slug: str,
        preset_id: int,
        position: int,
        entry: CampaignCombatPresetEntryInput,
        now_text: str,
        created_by_user_id: int | None,
        updated_by_user_id: int | None,
    ) -> CampaignCombatPresetEntryRecord:
        if operation is not None:
            self._invoke_entry_hook(operation, position)
        source_ref = entry.source_ref.strip()
        source_version = _strip_optional(entry.source_version)
        version_scheme = _strip_optional(entry.version_scheme)
        custom_name = entry.custom_name.strip()
        cursor = connection.execute(
            """
            INSERT INTO campaign_encounter_preset_entries (
                campaign_slug, preset_id, position, source_kind, source_ref,
                source_version, version_scheme, quantity, turn_value,
                initiative_priority, custom_name, initiative_bonus,
                dexterity_modifier, max_hp, movement_total, created_at,
                updated_at, created_by_user_id, updated_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_slug,
                preset_id,
                position,
                entry.source_kind,
                source_ref,
                source_version,
                version_scheme,
                entry.quantity,
                entry.turn_value,
                entry.initiative_priority,
                custom_name,
                entry.initiative_bonus,
                entry.dexterity_modifier,
                entry.max_hp,
                entry.movement_total,
                now_text,
                now_text,
                created_by_user_id,
                updated_by_user_id,
            ),
        )
        timestamp = parse_timestamp(now_text)
        if timestamp is None:
            raise RuntimeError("Failed to map encounter preset entry timestamp.")
        return CampaignCombatPresetEntryRecord(
            id=int(cursor.lastrowid),
            campaign_slug=campaign_slug,
            preset_id=preset_id,
            position=position,
            source_kind=entry.source_kind,
            source_ref=source_ref,
            source_version=source_version,
            version_scheme=version_scheme,
            quantity=entry.quantity,
            turn_value=entry.turn_value,
            initiative_priority=entry.initiative_priority,
            custom_name=custom_name,
            initiative_bonus=entry.initiative_bonus,
            dexterity_modifier=entry.dexterity_modifier,
            max_hp=entry.max_hp,
            movement_total=entry.movement_total,
            created_at=timestamp,
            updated_at=timestamp,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=updated_by_user_id,
        )

    def _invoke_entry_hook(self, operation: str, position: int) -> None:
        if self._hooks.before_entry_write is not None:
            self._hooks.before_entry_write(operation, position)

    def _map_preset(
        self,
        row: sqlite3.Row,
        entries: tuple[CampaignCombatPresetEntryRecord, ...],
    ) -> CampaignCombatPresetRecord:
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map encounter preset timestamps.")
        return CampaignCombatPresetRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            name=str(row["name"]),
            name_key=str(row["name_key"]),
            revision=int(row["revision"]),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=(
                int(row["created_by_user_id"])
                if row["created_by_user_id"] is not None
                else None
            ),
            updated_by_user_id=(
                int(row["updated_by_user_id"])
                if row["updated_by_user_id"] is not None
                else None
            ),
            entries=entries,
        )

    def _map_entry(self, row: sqlite3.Row) -> CampaignCombatPresetEntryRecord:
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map encounter preset entry timestamps.")
        return CampaignCombatPresetEntryRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            preset_id=int(row["preset_id"]),
            position=int(row["position"]),
            source_kind=str(row["source_kind"]),
            source_ref=str(row["source_ref"]),
            source_version=(
                str(row["source_version"]) if row["source_version"] is not None else None
            ),
            version_scheme=(
                str(row["version_scheme"]) if row["version_scheme"] is not None else None
            ),
            quantity=int(row["quantity"]),
            turn_value=int(row["turn_value"]) if row["turn_value"] is not None else None,
            initiative_priority=int(row["initiative_priority"]),
            custom_name=str(row["custom_name"]),
            initiative_bonus=(
                int(row["initiative_bonus"])
                if row["initiative_bonus"] is not None
                else None
            ),
            dexterity_modifier=(
                int(row["dexterity_modifier"])
                if row["dexterity_modifier"] is not None
                else None
            ),
            max_hp=int(row["max_hp"]) if row["max_hp"] is not None else None,
            movement_total=(
                int(row["movement_total"]) if row["movement_total"] is not None else None
            ),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=(
                int(row["created_by_user_id"])
                if row["created_by_user_id"] is not None
                else None
            ),
            updated_by_user_id=(
                int(row["updated_by_user_id"])
                if row["updated_by_user_id"] is not None
                else None
            ),
        )


def normalize_preset_name(name: str) -> tuple[str, str]:
    normalized_name = unicodedata.normalize("NFKC", str(name)).strip()
    return normalized_name, normalized_name.casefold()


def _coerce_entry_input(
    entry: CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord,
) -> CampaignCombatPresetEntryInput:
    if isinstance(entry, CampaignCombatPresetEntryInput):
        return entry
    if isinstance(entry, CampaignCombatPresetEntryRecord):
        return entry.as_input()
    raise CampaignCombatPresetConflictError("Unable to persist encounter preset entry.")


def _strip_optional(value: str | None) -> str | None:
    return value.strip() if value is not None else None
