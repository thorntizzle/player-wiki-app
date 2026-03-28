from __future__ import annotations

import sqlite3

from .auth_store import isoformat, parse_timestamp, utcnow
from .combat_models import (
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatTrackerRecord,
)
from .db import get_db


class CampaignCombatConflictError(RuntimeError):
    pass


class CampaignCombatStore:
    def get_tracker(self, campaign_slug: str) -> CampaignCombatTrackerRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_combat_trackers
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        ).fetchone()
        return self._map_tracker(row)

    def ensure_tracker(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        tracker = self.get_tracker(campaign_slug)
        if tracker is not None:
            return tracker

        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_combat_trackers (
                campaign_slug,
                round_number,
                current_combatant_id,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, 1, NULL, ?, ?)
            """,
            (campaign_slug, isoformat(utcnow()), updated_by_user_id),
        )
        connection.commit()

        tracker = self.get_tracker(campaign_slug)
        if tracker is None:
            raise RuntimeError("Failed to persist campaign combat tracker.")
        return tracker

    def update_tracker(
        self,
        campaign_slug: str,
        *,
        round_number: int,
        current_combatant_id: int | None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
            """,
            (
                round_number,
                current_combatant_id,
                isoformat(utcnow()),
                updated_by_user_id,
                campaign_slug,
            ),
        )
        connection.commit()
        if cursor.rowcount != 1:
            raise CampaignCombatConflictError(f"Unable to update combat tracker for {campaign_slug}.")

        tracker = self.get_tracker(campaign_slug)
        if tracker is None:
            raise RuntimeError("Campaign combat tracker disappeared after update.")
        return tracker

    def get_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
    ) -> CampaignCombatantRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_combatants
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, combatant_id),
        ).fetchone()
        return self._map_combatant(row)

    def list_combatants(self, campaign_slug: str) -> list[CampaignCombatantRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_combatants
            WHERE campaign_slug = ?
            ORDER BY turn_value DESC, display_name COLLATE NOCASE ASC, id ASC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_combatant(row) for row in rows]

    def create_combatant(
        self,
        campaign_slug: str,
        *,
        combatant_type: str,
        display_name: str,
        character_slug: str | None = None,
        turn_value: int = 0,
        initiative_bonus: int = 0,
        current_hp: int = 0,
        max_hp: int = 0,
        temp_hp: int = 0,
        movement_total: int = 0,
        movement_remaining: int | None = None,
        has_action: bool = True,
        has_bonus_action: bool = True,
        has_reaction: bool = True,
        created_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        connection = get_db()
        now = isoformat(utcnow())
        try:
            cursor = connection.execute(
                """
                INSERT INTO campaign_combatants (
                    campaign_slug,
                    combatant_type,
                    character_slug,
                    display_name,
                    turn_value,
                    initiative_bonus,
                    current_hp,
                    max_hp,
                    temp_hp,
                    movement_total,
                    movement_remaining,
                    has_action,
                    has_bonus_action,
                    has_reaction,
                    created_at,
                    updated_at,
                    created_by_user_id,
                    updated_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_slug,
                    combatant_type,
                    character_slug,
                    display_name,
                    turn_value,
                    initiative_bonus,
                    current_hp,
                    max_hp,
                    temp_hp,
                    movement_total,
                    movement_total if movement_remaining is None else movement_remaining,
                    1 if has_action else 0,
                    1 if has_bonus_action else 0,
                    1 if has_reaction else 0,
                    now,
                    now,
                    created_by_user_id,
                    created_by_user_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CampaignCombatConflictError(
                f"Unable to create combatant for {campaign_slug}/{character_slug or display_name}."
            ) from exc
        connection.commit()

        combatant = self.get_combatant(campaign_slug, int(cursor.lastrowid))
        if combatant is None:
            raise RuntimeError("Failed to persist campaign combatant.")
        return combatant

    def update_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        display_name: str | None = None,
        turn_value: int | None = None,
        initiative_bonus: int | None = None,
        current_hp: int | None = None,
        max_hp: int | None = None,
        temp_hp: int | None = None,
        movement_total: int | None = None,
        movement_remaining: int | None = None,
        has_action: bool | None = None,
        has_bonus_action: bool | None = None,
        has_reaction: bool | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        assignments: list[tuple[str, object]] = []
        if display_name is not None:
            assignments.append(("display_name", display_name))
        if turn_value is not None:
            assignments.append(("turn_value", turn_value))
        if initiative_bonus is not None:
            assignments.append(("initiative_bonus", initiative_bonus))
        if current_hp is not None:
            assignments.append(("current_hp", current_hp))
        if max_hp is not None:
            assignments.append(("max_hp", max_hp))
        if temp_hp is not None:
            assignments.append(("temp_hp", temp_hp))
        if movement_total is not None:
            assignments.append(("movement_total", movement_total))
        if movement_remaining is not None:
            assignments.append(("movement_remaining", movement_remaining))
        if has_action is not None:
            assignments.append(("has_action", 1 if has_action else 0))
        if has_bonus_action is not None:
            assignments.append(("has_bonus_action", 1 if has_bonus_action else 0))
        if has_reaction is not None:
            assignments.append(("has_reaction", 1 if has_reaction else 0))

        assignments.append(("updated_at", isoformat(utcnow())))
        assignments.append(("updated_by_user_id", updated_by_user_id))

        set_clause = ", ".join(f"{column} = ?" for column, _ in assignments)
        parameters = [value for _, value in assignments]
        parameters.extend([campaign_slug, combatant_id])

        connection = get_db()
        cursor = connection.execute(
            f"""
            UPDATE campaign_combatants
            SET {set_clause}
            WHERE campaign_slug = ? AND id = ?
            """,
            parameters,
        )
        connection.commit()
        if cursor.rowcount != 1:
            raise CampaignCombatConflictError(
                f"Unable to update campaign combatant {campaign_slug}/{combatant_id}."
            )

        combatant = self.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            raise RuntimeError("Campaign combatant disappeared after update.")
        return combatant

    def delete_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
    ) -> CampaignCombatantRecord | None:
        combatant = self.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_combatants
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, combatant_id),
        )
        connection.commit()
        return combatant

    def clear_tracker(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        tracker = self.ensure_tracker(campaign_slug, updated_by_user_id=updated_by_user_id)

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_combatants
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        )
        connection.execute(
            """
            UPDATE campaign_combat_trackers
            SET round_number = 1,
                current_combatant_id = NULL,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
            """,
            (
                isoformat(utcnow()),
                updated_by_user_id,
                campaign_slug,
            ),
        )
        connection.commit()

        refreshed_tracker = self.get_tracker(campaign_slug)
        if refreshed_tracker is None:
            raise RuntimeError("Campaign combat tracker disappeared after clear.")
        return refreshed_tracker

    def get_condition(
        self,
        campaign_slug: str,
        condition_id: int,
    ) -> CampaignCombatConditionRecord | None:
        row = get_db().execute(
            """
            SELECT
                c.id,
                c.combatant_id,
                e.campaign_slug,
                c.name,
                c.duration_text,
                c.created_at,
                c.created_by_user_id
            FROM campaign_combat_conditions AS c
            JOIN campaign_combatants AS e ON e.id = c.combatant_id
            WHERE e.campaign_slug = ? AND c.id = ?
            """,
            (campaign_slug, condition_id),
        ).fetchone()
        return self._map_condition(row)

    def list_conditions(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> list[CampaignCombatConditionRecord]:
        filters = ["e.campaign_slug = ?"]
        parameters: list[object] = [campaign_slug]
        if combatant_ids is not None:
            if not combatant_ids:
                return []
            filters.append(f"c.combatant_id IN ({', '.join('?' for _ in combatant_ids)})")
            parameters.extend(combatant_ids)

        rows = get_db().execute(
            f"""
            SELECT
                c.id,
                c.combatant_id,
                e.campaign_slug,
                c.name,
                c.duration_text,
                c.created_at,
                c.created_by_user_id
            FROM campaign_combat_conditions AS c
            JOIN campaign_combatants AS e ON e.id = c.combatant_id
            WHERE {' AND '.join(filters)}
            ORDER BY c.created_at ASC, c.id ASC
            """,
            parameters,
        ).fetchall()
        return [self._map_condition(row) for row in rows]

    def create_condition(
        self,
        combatant_id: int,
        *,
        name: str,
        duration_text: str = "",
        created_by_user_id: int | None = None,
    ) -> CampaignCombatConditionRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO campaign_combat_conditions (
                combatant_id,
                name,
                duration_text,
                created_at,
                created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                combatant_id,
                name,
                duration_text,
                isoformat(utcnow()),
                created_by_user_id,
            ),
        )
        connection.commit()

        row = get_db().execute(
            """
            SELECT
                c.id,
                c.combatant_id,
                e.campaign_slug,
                c.name,
                c.duration_text,
                c.created_at,
                c.created_by_user_id
            FROM campaign_combat_conditions AS c
            JOIN campaign_combatants AS e ON e.id = c.combatant_id
            WHERE c.id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()
        condition = self._map_condition(row)
        if condition is None:
            raise RuntimeError("Failed to persist combat condition.")
        return condition

    def delete_condition(
        self,
        campaign_slug: str,
        condition_id: int,
    ) -> CampaignCombatConditionRecord | None:
        condition = self.get_condition(campaign_slug, condition_id)
        if condition is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_combat_conditions
            WHERE id = ?
            """,
            (condition_id,),
        )
        connection.commit()
        return condition

    def _map_tracker(self, row: sqlite3.Row | None) -> CampaignCombatTrackerRecord | None:
        if row is None:
            return None
        updated_at = parse_timestamp(row["updated_at"])
        if updated_at is None:
            raise RuntimeError("Failed to map campaign combat tracker timestamp.")
        return CampaignCombatTrackerRecord(
            campaign_slug=str(row["campaign_slug"]),
            round_number=int(row["round_number"] or 1),
            current_combatant_id=int(row["current_combatant_id"]) if row["current_combatant_id"] is not None else None,
            updated_at=updated_at,
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_combatant(self, row: sqlite3.Row | None) -> CampaignCombatantRecord | None:
        if row is None:
            return None
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map campaign combatant timestamps.")
        return CampaignCombatantRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            combatant_type=str(row["combatant_type"]),
            character_slug=str(row["character_slug"]) if row["character_slug"] is not None else None,
            display_name=str(row["display_name"]),
            turn_value=int(row["turn_value"] or 0),
            initiative_bonus=int(row["initiative_bonus"] or 0),
            current_hp=int(row["current_hp"] or 0),
            max_hp=int(row["max_hp"] or 0),
            temp_hp=int(row["temp_hp"] or 0),
            movement_total=int(row["movement_total"] or 0),
            movement_remaining=int(row["movement_remaining"] or 0),
            has_action=bool(row["has_action"]),
            has_bonus_action=bool(row["has_bonus_action"]),
            has_reaction=bool(row["has_reaction"]),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_condition(self, row: sqlite3.Row | None) -> CampaignCombatConditionRecord | None:
        if row is None:
            return None
        created_at = parse_timestamp(row["created_at"])
        if created_at is None:
            raise RuntimeError("Failed to map combat condition timestamp.")
        return CampaignCombatConditionRecord(
            id=int(row["id"]),
            combatant_id=int(row["combatant_id"]),
            campaign_slug=str(row["campaign_slug"]),
            name=str(row["name"]),
            duration_text=str(row["duration_text"] or ""),
            created_at=created_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
        )
