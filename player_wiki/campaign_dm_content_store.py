from __future__ import annotations

import sqlite3

from .auth_store import isoformat, parse_timestamp, utcnow
from .db import get_db
from .dm_content_models import (
    CampaignDMConditionDefinitionRecord,
    CampaignDMStatblockRecord,
)


class CampaignDMContentConflictError(RuntimeError):
    pass


class CampaignDMContentStore:
    def list_statblocks(self, campaign_slug: str) -> list[CampaignDMStatblockRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_dm_statblocks
            WHERE campaign_slug = ?
            ORDER BY updated_at DESC, title COLLATE NOCASE ASC, id DESC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_statblock(row) for row in rows]

    def get_statblock(self, campaign_slug: str, statblock_id: int) -> CampaignDMStatblockRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_dm_statblocks
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, statblock_id),
        ).fetchone()
        return self._map_statblock(row)

    def create_statblock(
        self,
        campaign_slug: str,
        *,
        title: str,
        body_markdown: str,
        source_filename: str,
        subsection: str,
        armor_class: int | None,
        max_hp: int,
        speed_text: str,
        movement_total: int,
        initiative_bonus: int,
        created_by_user_id: int | None = None,
    ) -> CampaignDMStatblockRecord:
        connection = get_db()
        now = isoformat(utcnow())
        try:
            cursor = connection.execute(
                """
                INSERT INTO campaign_dm_statblocks (
                    campaign_slug,
                    title,
                    body_markdown,
                    source_filename,
                    subsection,
                    armor_class,
                    max_hp,
                    speed_text,
                    movement_total,
                    initiative_bonus,
                    created_at,
                    updated_at,
                    created_by_user_id,
                    updated_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_slug,
                    title,
                    body_markdown,
                    source_filename,
                    subsection,
                    armor_class,
                    max_hp,
                    speed_text,
                    movement_total,
                    initiative_bonus,
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CampaignDMContentConflictError(
                f"Unable to create statblock for {campaign_slug}/{title}."
            ) from exc
        connection.commit()

        statblock = self.get_statblock(campaign_slug, int(cursor.lastrowid))
        if statblock is None:
            raise RuntimeError("Failed to persist DM statblock.")
        return statblock

    def delete_statblock(
        self,
        campaign_slug: str,
        statblock_id: int,
    ) -> CampaignDMStatblockRecord | None:
        statblock = self.get_statblock(campaign_slug, statblock_id)
        if statblock is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_dm_statblocks
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, statblock_id),
        )
        connection.commit()
        return statblock

    def list_condition_definitions(self, campaign_slug: str) -> list[CampaignDMConditionDefinitionRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_dm_condition_definitions
            WHERE campaign_slug = ?
            ORDER BY name COLLATE NOCASE ASC, id ASC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_condition_definition(row) for row in rows]

    def get_condition_definition(
        self,
        campaign_slug: str,
        condition_definition_id: int,
    ) -> CampaignDMConditionDefinitionRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_dm_condition_definitions
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, condition_definition_id),
        ).fetchone()
        return self._map_condition_definition(row)

    def create_condition_definition(
        self,
        campaign_slug: str,
        *,
        name: str,
        description_markdown: str,
        created_by_user_id: int | None = None,
    ) -> CampaignDMConditionDefinitionRecord:
        connection = get_db()
        now = isoformat(utcnow())
        try:
            cursor = connection.execute(
                """
                INSERT INTO campaign_dm_condition_definitions (
                    campaign_slug,
                    name,
                    description_markdown,
                    created_at,
                    updated_at,
                    created_by_user_id,
                    updated_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_slug,
                    name,
                    description_markdown,
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CampaignDMContentConflictError(
                f"Unable to create custom condition for {campaign_slug}/{name}."
            ) from exc
        connection.commit()

        condition_definition = self.get_condition_definition(campaign_slug, int(cursor.lastrowid))
        if condition_definition is None:
            raise RuntimeError("Failed to persist DM condition definition.")
        return condition_definition

    def delete_condition_definition(
        self,
        campaign_slug: str,
        condition_definition_id: int,
    ) -> CampaignDMConditionDefinitionRecord | None:
        condition_definition = self.get_condition_definition(campaign_slug, condition_definition_id)
        if condition_definition is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_dm_condition_definitions
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, condition_definition_id),
        )
        connection.commit()
        return condition_definition

    def _map_statblock(self, row: sqlite3.Row | None) -> CampaignDMStatblockRecord | None:
        if row is None:
            return None
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map DM statblock timestamps.")
        return CampaignDMStatblockRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            title=str(row["title"]),
            body_markdown=str(row["body_markdown"] or ""),
            source_filename=str(row["source_filename"] or ""),
            subsection=str(row["subsection"] or ""),
            armor_class=int(row["armor_class"]) if row["armor_class"] is not None else None,
            max_hp=int(row["max_hp"] or 0),
            speed_text=str(row["speed_text"] or ""),
            movement_total=int(row["movement_total"] or 0),
            initiative_bonus=int(row["initiative_bonus"] or 0),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_condition_definition(
        self,
        row: sqlite3.Row | None,
    ) -> CampaignDMConditionDefinitionRecord | None:
        if row is None:
            return None
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map DM condition timestamps.")
        return CampaignDMConditionDefinitionRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            name=str(row["name"]),
            description_markdown=str(row["description_markdown"] or ""),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )
