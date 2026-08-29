from __future__ import annotations

import hashlib
import json
import sqlite3

from .auth_store import isoformat, parse_timestamp, utcnow
from .combat_models import (
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatantResourceCounterRecord,
    CampaignCombatantResourceNoteRecord,
    CampaignCombatTrackerRecord,
)
from .db import get_db
from .source_health import (
    SourceHealthConsumer,
    SourceHealthCursorError,
    SourceHealthInventoryPage,
    SourceHealthReference,
)


_SQLITE_MAX_INTEGER = 2**63 - 1


def _parse_combat_source_health_cursor(continuation: str) -> tuple[int, str]:
    if continuation == "":
        return 0, ""
    if not isinstance(continuation, str):
        raise SourceHealthCursorError("Invalid Combat cursor.")
    parts = continuation.split(":")
    if len(parts) != 3 or parts[0] != "ch1":
        raise SourceHealthCursorError("Invalid Combat cursor.")
    offset_text, digest = parts[1:]
    if (
        not offset_text
        or offset_text[0] not in "123456789"
        or any(character not in "0123456789" for character in offset_text[1:])
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SourceHealthCursorError("Invalid Combat cursor.")
    offset = int(offset_text)
    if offset > _SQLITE_MAX_INTEGER:
        raise SourceHealthCursorError("Invalid Combat cursor.")
    return offset, digest


def _combat_source_health_anchor_digest(campaign_slug: str, row) -> str:
    payload = {
        "campaign": campaign_slug,
        "owner": "combat",
        "row": {
            "id": row["id"],
            "source_kind": row["source_kind"],
            "source_ref": row["source_ref"],
        },
        "version": "ch1",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CampaignCombatConflictError(RuntimeError):
    pass


class CampaignCombatRevisionConflictError(CampaignCombatConflictError):
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
        commit: bool = True,
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
                revision,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, 1, NULL, 1, ?, ?)
            """,
            (campaign_slug, isoformat(utcnow()), updated_by_user_id),
        )
        if commit:
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
        commit: bool = True,
    ) -> CampaignCombatTrackerRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                revision = revision + 1,
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
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignCombatConflictError(f"Unable to update combat tracker for {campaign_slug}.")

        tracker = self.get_tracker(campaign_slug)
        if tracker is None:
            raise RuntimeError("Campaign combat tracker disappeared after update.")
        return tracker

    def bump_tracker_revision(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatTrackerRecord:
        self.ensure_tracker(
            campaign_slug,
            updated_by_user_id=updated_by_user_id,
            commit=commit,
        )
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
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
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignCombatConflictError(f"Unable to bump combat tracker revision for {campaign_slug}.")

        tracker = self.get_tracker(campaign_slug)
        if tracker is None:
            raise RuntimeError("Campaign combat tracker disappeared after revision bump.")
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
            ORDER BY
                turn_value DESC,
                dexterity_modifier DESC,
                initiative_priority ASC,
                display_name COLLATE NOCASE ASC,
                id ASC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_combatant(row) for row in rows]

    def list_source_health_consumers(
        self,
        campaign_slug: str,
        *,
        continuation: str = "",
        limit: int = 50,
    ) -> SourceHealthInventoryPage:
        page_limit = min(max(int(limit), 1), 50)
        offset, anchor_digest = _parse_combat_source_health_cursor(continuation)
        query_offset = offset - 1 if offset else 0
        query_limit = page_limit + 2 if offset else page_limit + 1
        rows = get_db().execute(
            """
            SELECT id, source_kind, source_ref
            FROM campaign_combatants
            WHERE campaign_slug = ?
              AND source_kind IN ('systems_monster', 'dm_statblock', 'character')
              AND trim(source_ref) <> ''
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (campaign_slug, query_limit, query_offset),
        ).fetchall()
        if offset:
            if (
                not rows
                or _combat_source_health_anchor_digest(campaign_slug, rows[0])
                != anchor_digest
            ):
                raise SourceHealthCursorError("Combat cursor is stale.")
            candidates = rows[1:]
        else:
            candidates = rows
        has_more = len(candidates) > page_limit
        selected = candidates[:page_limit]
        consumers: list[SourceHealthConsumer] = []
        for row in selected:
            combatant_id = int(row["id"])
            source_kind = str(row["source_kind"])
            source_ref = str(row["source_ref"] or "").strip()
            if source_kind == "systems_monster":
                reference = SourceHealthReference(
                    target_kind="systems",
                    entry_key=source_ref,
                )
                accepted_types = ("monster",)
            elif source_kind == "dm_statblock":
                reference = SourceHealthReference(
                    target_kind="dm_statblock",
                    target_id=source_ref,
                )
                accepted_types = ("dm_statblock",)
            else:
                reference = SourceHealthReference(
                    target_kind="character",
                    target_id=source_ref,
                )
                accepted_types = ("character",)
            consumers.append(
                SourceHealthConsumer(
                    consumer_type="combatant",
                    consumer_key=f"combatant:{combatant_id}",
                    surface="Combat",
                    reference=reference,
                    accepted_target_types=accepted_types,
                    destination=f"/campaigns/{campaign_slug}/combat/dm?combatant={combatant_id}",
                )
            )
        return SourceHealthInventoryPage(
            consumers=tuple(consumers),
            continuation=(
                "ch1:"
                f"{offset + len(selected)}:"
                f"{_combat_source_health_anchor_digest(campaign_slug, selected[-1])}"
                if has_more and selected
                else ""
            ),
        )

    def create_combatant(
        self,
        campaign_slug: str,
        *,
        combatant_type: str,
        display_name: str,
        character_slug: str | None = None,
        player_detail_visible: bool = False,
        source_kind: str = "manual_npc",
        source_ref: str = "",
        turn_value: int = 0,
        initiative_bonus: int = 0,
        dexterity_modifier: int = 0,
        initiative_priority: int = 1,
        current_hp: int = 0,
        max_hp: int = 0,
        temp_hp: int = 0,
        movement_total: int = 0,
        movement_remaining: int | None = None,
        has_action: bool = True,
        has_bonus_action: bool = True,
        has_reaction: bool = True,
        created_by_user_id: int | None = None,
        commit: bool = True,
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
                    player_detail_visible,
                    source_kind,
                    source_ref,
                    display_name,
                    turn_value,
                    initiative_bonus,
                    dexterity_modifier,
                    initiative_priority,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_slug,
                    combatant_type,
                    character_slug,
                    1 if player_detail_visible else 0,
                    source_kind,
                    source_ref,
                    display_name,
                    turn_value,
                    initiative_bonus,
                    dexterity_modifier,
                    initiative_priority,
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
        if commit:
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
        player_detail_visible: bool | None = None,
        source_kind: str | None = None,
        source_ref: str | None = None,
        turn_value: int | None = None,
        initiative_bonus: int | None = None,
        dexterity_modifier: int | None = None,
        initiative_priority: int | None = None,
        current_hp: int | None = None,
        max_hp: int | None = None,
        temp_hp: int | None = None,
        movement_total: int | None = None,
        movement_remaining: int | None = None,
        has_action: bool | None = None,
        has_bonus_action: bool | None = None,
        has_reaction: bool | None = None,
        expected_revision: int | None = None,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatantRecord:
        assignments: list[tuple[str, object]] = []
        if display_name is not None:
            assignments.append(("display_name", display_name))
        if player_detail_visible is not None:
            assignments.append(("player_detail_visible", 1 if player_detail_visible else 0))
        if source_kind is not None:
            assignments.append(("source_kind", source_kind))
        if source_ref is not None:
            assignments.append(("source_ref", source_ref))
        if turn_value is not None:
            assignments.append(("turn_value", turn_value))
        if initiative_bonus is not None:
            assignments.append(("initiative_bonus", initiative_bonus))
        if dexterity_modifier is not None:
            assignments.append(("dexterity_modifier", dexterity_modifier))
        if initiative_priority is not None:
            assignments.append(("initiative_priority", initiative_priority))
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

        set_clauses = [f"{column} = ?" for column, _ in assignments]
        set_clauses.append("revision = revision + 1")
        parameters = [value for _, value in assignments]
        where_clauses = ["campaign_slug = ?", "id = ?"]
        parameters.extend([campaign_slug, combatant_id])
        if expected_revision is not None:
            where_clauses.append("revision = ?")
            parameters.append(expected_revision)

        connection = get_db()
        cursor = connection.execute(
            f"""
            UPDATE campaign_combatants
            SET {", ".join(set_clauses)}
            WHERE {" AND ".join(where_clauses)}
            """,
            parameters,
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            if expected_revision is not None:
                raise CampaignCombatRevisionConflictError(
                    f"Combatant update conflict for {campaign_slug}/{combatant_id}."
                )
            raise CampaignCombatConflictError(f"Unable to update campaign combatant {campaign_slug}/{combatant_id}.")

        combatant = self.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            raise RuntimeError("Campaign combatant disappeared after update.")
        return combatant

    def delete_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        commit: bool = True,
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
        if commit:
            connection.commit()
        return combatant

    def clear_tracker(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatTrackerRecord:
        tracker = self.ensure_tracker(
            campaign_slug,
            updated_by_user_id=updated_by_user_id,
            commit=commit,
        )

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
                revision = revision + 1,
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
        if commit:
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
        commit: bool = True,
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
        if commit:
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

    def update_condition(
        self,
        campaign_slug: str,
        condition_id: int,
        *,
        name: str,
        duration_text: str = "",
        commit: bool = True,
    ) -> CampaignCombatConditionRecord | None:
        condition = self.get_condition(campaign_slug, condition_id)
        if condition is None:
            return None

        connection = get_db()
        connection.execute(
            """
            UPDATE campaign_combat_conditions
            SET name = ?, duration_text = ?
            WHERE id = ?
            """,
            (name, duration_text, condition_id),
        )
        if commit:
            connection.commit()

        return self.get_condition(campaign_slug, condition_id)

    def delete_condition(
        self,
        campaign_slug: str,
        condition_id: int,
        commit: bool = True,
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
        if commit:
            connection.commit()
        return condition

    def list_resource_counters(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> list[CampaignCombatantResourceCounterRecord]:
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
                c.resource_key,
                c.label,
                c.current_value,
                c.max_value,
                c.reset_label,
                c.source_label,
                c.reset_kind,
                c.recharge_threshold,
                c.created_at,
                c.updated_at,
                c.created_by_user_id,
                c.updated_by_user_id
            FROM campaign_combatant_resource_counters AS c
            JOIN campaign_combatants AS e ON e.id = c.combatant_id
            WHERE {' AND '.join(filters)}
            ORDER BY c.id ASC
            """,
            parameters,
        ).fetchall()
        return [self._map_resource_counter(row) for row in rows]

    def list_resource_notes(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> list[CampaignCombatantResourceNoteRecord]:
        filters = ["e.campaign_slug = ?"]
        parameters: list[object] = [campaign_slug]
        if combatant_ids is not None:
            if not combatant_ids:
                return []
            filters.append(f"n.combatant_id IN ({', '.join('?' for _ in combatant_ids)})")
            parameters.extend(combatant_ids)

        rows = get_db().execute(
            f"""
            SELECT
                n.id,
                n.combatant_id,
                e.campaign_slug,
                n.label,
                n.note,
                n.source_label,
                n.created_at,
                n.created_by_user_id
            FROM campaign_combatant_resource_notes AS n
            JOIN campaign_combatants AS e ON e.id = n.combatant_id
            WHERE {' AND '.join(filters)}
            ORDER BY n.id ASC
            """,
            parameters,
        ).fetchall()
        return [self._map_resource_note(row) for row in rows]

    def create_resource_counters(
        self,
        combatant_id: int,
        counter_seeds: list[object],
        *,
        created_by_user_id: int | None = None,
        commit: bool = True,
    ) -> list[CampaignCombatantResourceCounterRecord]:
        if not counter_seeds:
            return []

        connection = get_db()
        now = isoformat(utcnow())
        created_ids: list[int] = []
        try:
            for seed in counter_seeds:
                cursor = connection.execute(
                    """
                    INSERT INTO campaign_combatant_resource_counters (
                        combatant_id,
                        resource_key,
                        label,
                        current_value,
                        max_value,
                        reset_label,
                        source_label,
                        reset_kind,
                        recharge_threshold,
                        created_at,
                        updated_at,
                        created_by_user_id,
                        updated_by_user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        combatant_id,
                        str(getattr(seed, "resource_key")),
                        str(getattr(seed, "label")),
                        int(getattr(seed, "current_value")),
                        int(getattr(seed, "max_value")),
                        str(getattr(seed, "reset_label")),
                        str(getattr(seed, "source_label")),
                        str(getattr(seed, "reset_kind")),
                        getattr(seed, "recharge_threshold"),
                        now,
                        now,
                        created_by_user_id,
                        created_by_user_id,
                    ),
                )
                created_ids.append(int(cursor.lastrowid))
        except sqlite3.IntegrityError as exc:
            raise CampaignCombatConflictError(
                f"Unable to create resource counters for combatant {combatant_id}."
            ) from exc

        if commit:
            connection.commit()

        if not created_ids:
            return []
        rows = get_db().execute(
            f"""
            SELECT
                c.id,
                c.combatant_id,
                e.campaign_slug,
                c.resource_key,
                c.label,
                c.current_value,
                c.max_value,
                c.reset_label,
                c.source_label,
                c.reset_kind,
                c.recharge_threshold,
                c.created_at,
                c.updated_at,
                c.created_by_user_id,
                c.updated_by_user_id
            FROM campaign_combatant_resource_counters AS c
            JOIN campaign_combatants AS e ON e.id = c.combatant_id
            WHERE c.id IN ({', '.join('?' for _ in created_ids)})
            ORDER BY c.id ASC
            """,
            created_ids,
        ).fetchall()
        return [self._map_resource_counter(row) for row in rows]

    def create_resource_notes(
        self,
        combatant_id: int,
        note_seeds: list[object],
        *,
        created_by_user_id: int | None = None,
        commit: bool = True,
    ) -> list[CampaignCombatantResourceNoteRecord]:
        if not note_seeds:
            return []

        connection = get_db()
        now = isoformat(utcnow())
        created_ids: list[int] = []
        try:
            for seed in note_seeds:
                cursor = connection.execute(
                    """
                    INSERT INTO campaign_combatant_resource_notes (
                        combatant_id,
                        label,
                        note,
                        source_label,
                        created_at,
                        created_by_user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        combatant_id,
                        str(getattr(seed, "label")),
                        str(getattr(seed, "note")),
                        str(getattr(seed, "source_label")),
                        now,
                        created_by_user_id,
                    ),
                )
                created_ids.append(int(cursor.lastrowid))
        except sqlite3.IntegrityError as exc:
            raise CampaignCombatConflictError(
                f"Unable to create resource notes for combatant {combatant_id}."
            ) from exc

        if commit:
            connection.commit()

        if not created_ids:
            return []
        rows = get_db().execute(
            f"""
            SELECT
                n.id,
                n.combatant_id,
                e.campaign_slug,
                n.label,
                n.note,
                n.source_label,
                n.created_at,
                n.created_by_user_id
            FROM campaign_combatant_resource_notes AS n
            JOIN campaign_combatants AS e ON e.id = n.combatant_id
            WHERE n.id IN ({', '.join('?' for _ in created_ids)})
            ORDER BY n.id ASC
            """,
            created_ids,
        ).fetchall()
        return [self._map_resource_note(row) for row in rows]

    def update_resource_counter_values(
        self,
        campaign_slug: str,
        combatant_id: int,
        values_by_key: dict[str, int],
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> list[CampaignCombatantResourceCounterRecord]:
        if not values_by_key:
            return self.list_resource_counters(campaign_slug, combatant_ids=[combatant_id])

        connection = get_db()
        now = isoformat(utcnow())
        for resource_key, current_value in values_by_key.items():
            cursor = connection.execute(
                """
                UPDATE campaign_combatant_resource_counters
                SET current_value = ?,
                    updated_at = ?,
                    updated_by_user_id = ?
                WHERE combatant_id = ?
                  AND resource_key = ?
                  AND EXISTS (
                    SELECT 1
                    FROM campaign_combatants AS e
                    WHERE e.id = campaign_combatant_resource_counters.combatant_id
                      AND e.campaign_slug = ?
                  )
                """,
                (
                    current_value,
                    now,
                    updated_by_user_id,
                    combatant_id,
                    resource_key,
                    campaign_slug,
                ),
            )
            if cursor.rowcount != 1:
                raise CampaignCombatConflictError(
                    f"Unable to update resource counter {campaign_slug}/{combatant_id}/{resource_key}."
                )
        if commit:
            connection.commit()
        return self.list_resource_counters(campaign_slug, combatant_ids=[combatant_id])

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
            revision=max(1, int(row["revision"] or 1)),
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
            player_detail_visible=bool(row["player_detail_visible"]),
            source_kind=str(row["source_kind"] or ""),
            source_ref=str(row["source_ref"] or ""),
            display_name=str(row["display_name"]),
            turn_value=int(row["turn_value"] or 0),
            initiative_bonus=int(row["initiative_bonus"] or 0),
            dexterity_modifier=int(row["dexterity_modifier"] or 0),
            initiative_priority=max(1, int(row["initiative_priority"] or 1)),
            current_hp=int(row["current_hp"] or 0),
            max_hp=int(row["max_hp"] or 0),
            temp_hp=int(row["temp_hp"] or 0),
            movement_total=int(row["movement_total"] or 0),
            movement_remaining=int(row["movement_remaining"] or 0),
            has_action=bool(row["has_action"]),
            has_bonus_action=bool(row["has_bonus_action"]),
            has_reaction=bool(row["has_reaction"]),
            revision=max(1, int(row["revision"] or 1)),
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

    def _map_resource_counter(
        self,
        row: sqlite3.Row | None,
    ) -> CampaignCombatantResourceCounterRecord:
        if row is None:
            raise RuntimeError("Failed to map combat resource counter.")
        created_at = parse_timestamp(row["created_at"])
        updated_at = parse_timestamp(row["updated_at"])
        if created_at is None or updated_at is None:
            raise RuntimeError("Failed to map combat resource counter timestamps.")
        return CampaignCombatantResourceCounterRecord(
            id=int(row["id"]),
            combatant_id=int(row["combatant_id"]),
            campaign_slug=str(row["campaign_slug"]),
            resource_key=str(row["resource_key"]),
            label=str(row["label"]),
            current_value=int(row["current_value"] or 0),
            max_value=int(row["max_value"] or 0),
            reset_label=str(row["reset_label"] or ""),
            source_label=str(row["source_label"] or ""),
            reset_kind=str(row["reset_kind"]),
            recharge_threshold=(
                int(row["recharge_threshold"])
                if row["recharge_threshold"] is not None
                else None
            ),
            created_at=created_at,
            updated_at=updated_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_resource_note(
        self,
        row: sqlite3.Row | None,
    ) -> CampaignCombatantResourceNoteRecord:
        if row is None:
            raise RuntimeError("Failed to map combat resource note.")
        created_at = parse_timestamp(row["created_at"])
        if created_at is None:
            raise RuntimeError("Failed to map combat resource note timestamp.")
        return CampaignCombatantResourceNoteRecord(
            id=int(row["id"]),
            combatant_id=int(row["combatant_id"]),
            campaign_slug=str(row["campaign_slug"]),
            label=str(row["label"]),
            note=str(row["note"]),
            source_label=str(row["source_label"] or ""),
            created_at=created_at,
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
        )
