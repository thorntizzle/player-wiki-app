from __future__ import annotations

import sqlite3

from .auth_store import isoformat, parse_timestamp, utcnow
from .db import get_db
from .session_models import (
    CampaignSessionCloseoutItemRecord,
    CampaignSessionCloseoutRecord,
    CampaignSessionCloseoutSummary,
    CampaignSessionRecord,
    CampaignSessionReadinessSummary,
    CampaignSessionStateRecord,
    CampaignSessionSummary,
    SessionArticleRecord,
    SessionArticleImageRecord,
    SessionMessageRecord,
    SESSION_CLOSEOUT_ITEM_KEYS,
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
)


class CampaignSessionConflictError(RuntimeError):
    pass


class CampaignSessionStore:
    def get_readiness_summary(
        self,
        campaign_slug: str,
        *,
        count_limit: int = 26,
    ) -> CampaignSessionReadinessSummary:
        parsed_limit = int(count_limit)
        if parsed_limit != 26:
            raise ValueError("Session readiness count limit is invalid.")
        row = get_db().execute(
            """
            WITH staged AS (
                SELECT 1
                FROM campaign_session_articles
                WHERE campaign_slug = ? AND status = 'staged'
                LIMIT ?
            ),
            revealed AS (
                SELECT 1
                FROM campaign_session_articles
                WHERE campaign_slug = ? AND status = 'revealed'
                LIMIT ?
            )
            SELECT
                (
                    SELECT started_at
                    FROM campaign_sessions
                    WHERE campaign_slug = ? AND status = 'active'
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                ) AS active_started_at,
                (SELECT COUNT(*) FROM staged) AS staged_count,
                (SELECT COUNT(*) FROM revealed) AS revealed_count
            """,
            (
                campaign_slug,
                parsed_limit,
                campaign_slug,
                parsed_limit,
                campaign_slug,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("Session readiness aggregate was unavailable.")
        raw_started_at = row["active_started_at"]
        active_started_at = parse_timestamp(raw_started_at)
        if raw_started_at is not None and active_started_at is None:
            raise RuntimeError("Session readiness active timestamp is invalid.")
        staged_count = int(row["staged_count"])
        revealed_count = int(row["revealed_count"])
        if not (0 <= staged_count <= parsed_limit and 0 <= revealed_count <= parsed_limit):
            raise RuntimeError("Session readiness aggregate count is invalid.")
        return CampaignSessionReadinessSummary(
            active_started_at=active_started_at,
            staged_count=staged_count,
            revealed_count=revealed_count,
        )

    def get_state(self, campaign_slug: str) -> CampaignSessionStateRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_session_states
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        ).fetchone()
        return self._map_state(row)

    def get_live_revision(self, campaign_slug: str) -> int:
        state = self.get_state(campaign_slug)
        return state.revision if state is not None else 0

    def ensure_state(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignSessionStateRecord:
        state = self.get_state(campaign_slug)
        if state is not None:
            return state

        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_session_states (
                campaign_slug,
                revision,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, 1, ?, ?)
            """,
            (campaign_slug, isoformat(utcnow()), updated_by_user_id),
        )
        if commit:
            connection.commit()

        state = self.get_state(campaign_slug)
        if state is None:
            raise RuntimeError("Failed to persist campaign session state.")
        return state

    def bump_state_revision(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignSessionStateRecord:
        state = self.get_state(campaign_slug)
        if state is None:
            return self.ensure_state(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
                commit=commit,
            )

        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_session_states
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
            raise CampaignSessionConflictError(f"Unable to bump session state for {campaign_slug}.")

        refreshed = self.get_state(campaign_slug)
        if refreshed is None:
            raise RuntimeError("Campaign session state disappeared after revision bump.")
        return refreshed

    def get_active_session(self, campaign_slug: str) -> CampaignSessionRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_sessions
            WHERE campaign_slug = ? AND status = 'active'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (campaign_slug,),
        ).fetchone()
        return self._map_session(row)

    def get_session(self, campaign_slug: str, session_id: int) -> CampaignSessionRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_sessions
            WHERE campaign_slug = ? AND id = ?
            """,
            (campaign_slug, session_id),
        ).fetchone()
        return self._map_session(row)

    def has_closeout(self, campaign_slug: str, session_id: int) -> bool:
        row = get_db().execute(
            """
            SELECT 1
            FROM campaign_session_closeouts
            WHERE campaign_slug = ? AND session_id = ?
            """,
            (campaign_slug, session_id),
        ).fetchone()
        return row is not None

    def get_closeout(
        self,
        campaign_slug: str,
        session_id: int,
    ) -> CampaignSessionCloseoutRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_session_closeouts
            WHERE campaign_slug = ? AND session_id = ?
            """,
            (campaign_slug, session_id),
        ).fetchone()
        if row is None:
            return None
        item_rows = get_db().execute(
            """
            SELECT closeout_id, campaign_slug, item_key, status, note
            FROM campaign_session_closeout_items
            WHERE campaign_slug = ? AND closeout_id = ?
            ORDER BY CASE item_key
                WHEN 'table_notes' THEN 1
                WHEN 'character_rests' THEN 2
                WHEN 'rewards_and_boons' THEN 3
                WHEN 'encounter_disposition' THEN 4
                WHEN 'session_article_publication' THEN 5
                WHEN 'external_archive' THEN 6
                ELSE 7
            END
            """,
            (campaign_slug, int(row["id"])),
        ).fetchall()
        return self._map_closeout(row, item_rows)

    def list_closeout_summaries(
        self,
        campaign_slug: str,
        *,
        limit: int = 26,
    ) -> list[CampaignSessionCloseoutSummary]:
        parsed_limit = int(limit)
        if not 1 <= parsed_limit <= 26:
            raise ValueError("Session closeout summary limit is invalid.")
        rows = get_db().execute(
            """
            SELECT
                c.id AS closeout_id,
                c.session_id,
                c.status,
                c.revision,
                c.updated_at,
                COUNT(i.item_key) AS item_count,
                SUM(CASE WHEN i.status <> 'pending' THEN 1 ELSE 0 END) AS resolved_count
            FROM campaign_session_closeouts AS c
            JOIN campaign_sessions AS s
              ON s.campaign_slug = c.campaign_slug AND s.id = c.session_id
            LEFT JOIN campaign_session_closeout_items AS i
              ON i.campaign_slug = c.campaign_slug AND i.closeout_id = c.id
            WHERE c.campaign_slug = ? AND s.status = 'closed'
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            (campaign_slug, parsed_limit),
        ).fetchall()
        return [self._map_closeout_summary(row) for row in rows]

    def create_closeout(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        actor_user_id: int,
        commit: bool = True,
    ) -> CampaignSessionCloseoutRecord:
        connection = get_db()
        now = isoformat(utcnow())
        try:
            cursor = connection.execute(
                """
                INSERT INTO campaign_session_closeouts (
                    campaign_slug,
                    session_id,
                    status,
                    revision,
                    created_at,
                    created_by_user_id,
                    updated_at,
                    updated_by_user_id,
                    completed_at,
                    completed_by_user_id
                )
                VALUES (?, ?, 'open', 1, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    campaign_slug,
                    session_id,
                    now,
                    actor_user_id,
                    now,
                    actor_user_id,
                ),
            )
            closeout_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO campaign_session_closeout_items (
                    closeout_id,
                    campaign_slug,
                    item_key,
                    status,
                    note
                )
                VALUES (?, ?, ?, ?, '')
                """,
                (
                    (
                        closeout_id,
                        campaign_slug,
                        item_key,
                        SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
                    )
                    for item_key in SESSION_CLOSEOUT_ITEM_KEYS
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CampaignSessionConflictError(
                f"Unable to create session closeout {campaign_slug}/{session_id}"
            ) from exc
        if commit:
            connection.commit()
        closeout = self.get_closeout(campaign_slug, session_id)
        if closeout is None:
            raise RuntimeError("Failed to persist campaign session closeout.")
        return closeout

    def update_closeout_item(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        expected_revision: int,
        item_key: str,
        status: str,
        note: str,
        actor_user_id: int,
        commit: bool = True,
    ) -> CampaignSessionCloseoutRecord:
        connection = get_db()
        closeout_row = connection.execute(
            """
            SELECT id
            FROM campaign_session_closeouts
            WHERE campaign_slug = ? AND session_id = ?
              AND status = 'open' AND revision = ?
            """,
            (campaign_slug, session_id, expected_revision),
        ).fetchone()
        if closeout_row is None:
            raise CampaignSessionConflictError(
                f"Unable to update session closeout {campaign_slug}/{session_id}"
            )
        closeout_id = int(closeout_row["id"])
        item_cursor = connection.execute(
            """
            UPDATE campaign_session_closeout_items
            SET status = ?, note = ?
            WHERE campaign_slug = ? AND closeout_id = ? AND item_key = ?
            """,
            (status, note, campaign_slug, closeout_id, item_key),
        )
        if item_cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to update session closeout item {campaign_slug}/{session_id}/{item_key}"
            )
        aggregate_cursor = connection.execute(
            """
            UPDATE campaign_session_closeouts
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND session_id = ?
              AND status = 'open' AND revision = ?
            """,
            (
                isoformat(utcnow()),
                actor_user_id,
                campaign_slug,
                session_id,
                expected_revision,
            ),
        )
        if aggregate_cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to update session closeout {campaign_slug}/{session_id}"
            )
        if commit:
            connection.commit()
        closeout = self.get_closeout(campaign_slug, session_id)
        if closeout is None:
            raise RuntimeError("Session closeout disappeared after item update.")
        return closeout

    def complete_closeout(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        expected_revision: int,
        actor_user_id: int,
        commit: bool = True,
    ) -> CampaignSessionCloseoutRecord:
        now = isoformat(utcnow())
        cursor = get_db().execute(
            """
            UPDATE campaign_session_closeouts
            SET status = 'completed',
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?,
                completed_at = ?,
                completed_by_user_id = ?
            WHERE campaign_slug = ? AND session_id = ?
              AND status = 'open' AND revision = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM campaign_session_closeout_items AS i
                  WHERE i.campaign_slug = campaign_session_closeouts.campaign_slug
                    AND i.closeout_id = campaign_session_closeouts.id
                    AND i.status = 'pending'
              )
            """,
            (
                now,
                actor_user_id,
                now,
                actor_user_id,
                campaign_slug,
                session_id,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to complete session closeout {campaign_slug}/{session_id}"
            )
        if commit:
            get_db().commit()
        closeout = self.get_closeout(campaign_slug, session_id)
        if closeout is None:
            raise RuntimeError("Session closeout disappeared after completion.")
        return closeout

    def reopen_closeout(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        expected_revision: int,
        actor_user_id: int,
        commit: bool = True,
    ) -> CampaignSessionCloseoutRecord:
        cursor = get_db().execute(
            """
            UPDATE campaign_session_closeouts
            SET status = 'open',
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?,
                completed_at = NULL,
                completed_by_user_id = NULL
            WHERE campaign_slug = ? AND session_id = ?
              AND status = 'completed' AND revision = ?
            """,
            (
                isoformat(utcnow()),
                actor_user_id,
                campaign_slug,
                session_id,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to reopen session closeout {campaign_slug}/{session_id}"
            )
        if commit:
            get_db().commit()
        closeout = self.get_closeout(campaign_slug, session_id)
        if closeout is None:
            raise RuntimeError("Session closeout disappeared after reopen.")
        return closeout

    def delete_closeout(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> None:
        cursor = get_db().execute(
            """
            DELETE FROM campaign_session_closeouts
            WHERE campaign_slug = ? AND session_id = ? AND revision = ?
            """,
            (campaign_slug, session_id, expected_revision),
        )
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to delete session closeout {campaign_slug}/{session_id}"
            )
        if commit:
            get_db().commit()

    def list_session_summaries(
        self,
        campaign_slug: str,
        *,
        statuses: tuple[str, ...] | None = ("closed",),
        limit: int = 10,
    ) -> list[CampaignSessionSummary]:
        filters = ["s.campaign_slug = ?"]
        parameters: list[object] = [campaign_slug]

        if statuses:
            filters.append(f"s.status IN ({', '.join('?' for _ in statuses)})")
            parameters.extend(statuses)

        rows = get_db().execute(
            f"""
            SELECT
                s.*,
                COUNT(m.id) AS message_count,
                MAX(m.created_at) AS last_message_at
            FROM campaign_sessions AS s
            LEFT JOIN campaign_session_messages AS m ON m.session_id = s.id
            WHERE {' AND '.join(filters)}
            GROUP BY s.id
            ORDER BY s.started_at DESC, s.id DESC
            LIMIT ?
            """,
            (*parameters, max(1, limit)),
        ).fetchall()
        return [self._map_session_summary(row) for row in rows]

    def create_session(
        self,
        campaign_slug: str,
        *,
        started_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignSessionRecord:
        connection = get_db()
        now = isoformat(utcnow())
        try:
            cursor = connection.execute(
                """
                INSERT INTO campaign_sessions (
                    campaign_slug,
                    status,
                    started_at,
                    started_by_user_id,
                    ended_at,
                    ended_by_user_id
                )
                VALUES (?, 'active', ?, ?, NULL, NULL)
                """,
                (campaign_slug, now, started_by_user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise CampaignSessionConflictError(
                f"An active session already exists for {campaign_slug}"
            ) from exc
        if commit:
            connection.commit()

        session_record = self.get_session(campaign_slug, int(cursor.lastrowid))
        if session_record is None:
            raise RuntimeError("Failed to persist campaign session.")
        return session_record

    def close_session(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        ended_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignSessionRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_sessions
            SET status = 'closed',
                ended_at = ?,
                ended_by_user_id = ?
            WHERE campaign_slug = ? AND id = ? AND status = 'active'
            """,
            (
                isoformat(utcnow()),
                ended_by_user_id,
                campaign_slug,
                session_id,
            ),
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to close campaign session {campaign_slug}/{session_id}"
            )

        session_record = self.get_session(campaign_slug, session_id)
        if session_record is None:
            raise RuntimeError("Campaign session disappeared after close.")
        return session_record

    def delete_session(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        commit: bool = True,
    ) -> None:
        connection = get_db()
        session_record = self.get_session(campaign_slug, session_id)
        if session_record is None or session_record.is_active:
            raise CampaignSessionConflictError(
                f"Unable to delete campaign session {campaign_slug}/{session_id}"
            )

        connection.execute(
            """
            UPDATE campaign_session_articles
            SET revealed_in_session_id = NULL
            WHERE revealed_in_session_id = ?
            """,
            (session_id,),
        )
        connection.execute(
            """
            DELETE FROM campaign_session_messages
            WHERE session_id = ?
            """,
            (session_id,),
        )
        cursor = connection.execute(
            """
            DELETE FROM campaign_sessions
            WHERE campaign_slug = ? AND id = ? AND status = 'closed'
            """,
            (campaign_slug, session_id),
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to delete campaign session {campaign_slug}/{session_id}"
            )

    def get_article(self, article_id: int) -> SessionArticleRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_session_articles
            WHERE id = ?
            """,
            (article_id,),
        ).fetchone()
        return self._map_article(row)

    def list_articles(
        self,
        campaign_slug: str,
        *,
        statuses: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> list[SessionArticleRecord]:
        filters = ["campaign_slug = ?"]
        parameters: list[object] = [campaign_slug]

        if statuses:
            filters.append(f"status IN ({', '.join('?' for _ in statuses)})")
            parameters.extend(statuses)

        query = f"""
        SELECT *
        FROM campaign_session_articles
        WHERE {' AND '.join(filters)}
        ORDER BY created_at DESC, id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(max(1, limit))

        rows = get_db().execute(query, parameters).fetchall()
        return [self._map_article(row) for row in rows]

    def create_article(
        self,
        campaign_slug: str,
        *,
        title: str,
        body_markdown: str,
        source_page_ref: str = "",
        created_by_user_id: int | None = None,
        commit: bool = True,
    ) -> SessionArticleRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO campaign_session_articles (
                campaign_slug,
                title,
                body_markdown,
                source_page_ref,
                status,
                created_at,
                created_by_user_id,
                revealed_at,
                revealed_by_user_id,
                revealed_in_session_id
            )
            VALUES (?, ?, ?, ?, 'staged', ?, ?, NULL, NULL, NULL)
            """,
            (
                campaign_slug,
                title,
                body_markdown,
                source_page_ref,
                isoformat(utcnow()),
                created_by_user_id,
            ),
        )
        if commit:
            connection.commit()

        article = self.get_article(int(cursor.lastrowid))
        if article is None:
            raise RuntimeError("Failed to persist session article.")
        return article

    def update_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        title: str,
        body_markdown: str,
        commit: bool = True,
    ) -> SessionArticleRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_session_articles
            SET title = ?,
                body_markdown = ?
            WHERE id = ? AND campaign_slug = ? AND status = 'staged'
            """,
            (
                title,
                body_markdown,
                article_id,
                campaign_slug,
            ),
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to update session article {campaign_slug}/{article_id}"
            )

        article = self.get_article(article_id)
        if article is None:
            raise RuntimeError("Session article disappeared after update.")
        return article

    def delete_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        commit: bool = True,
    ) -> SessionArticleRecord:
        connection = get_db()
        article = self.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionConflictError(
                f"Unable to delete session article {campaign_slug}/{article_id}"
            )

        connection.execute(
            """
            DELETE FROM campaign_session_messages
            WHERE campaign_slug = ? AND article_id = ?
            """,
            (campaign_slug, article_id),
        )
        cursor = connection.execute(
            """
            DELETE FROM campaign_session_articles
            WHERE id = ? AND campaign_slug = ?
            """,
            (article_id, campaign_slug),
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to delete session article {campaign_slug}/{article_id}"
            )
        return article

    def get_article_image(self, article_id: int) -> SessionArticleImageRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_session_article_images
            WHERE article_id = ?
            """,
            (article_id,),
        ).fetchone()
        return self._map_article_image(row)

    def list_article_images(self, article_ids: list[int]) -> dict[int, SessionArticleImageRecord]:
        normalized_ids = sorted({int(article_id) for article_id in article_ids if int(article_id) > 0})
        if not normalized_ids:
            return {}

        placeholders = ", ".join("?" for _ in normalized_ids)
        rows = get_db().execute(
            f"""
            SELECT *
            FROM campaign_session_article_images
            WHERE article_id IN ({placeholders})
            """,
            normalized_ids,
        ).fetchall()
        images = [self._map_article_image(row) for row in rows]
        return {
            image.article_id: image
            for image in images
            if image is not None
        }

    def upsert_article_image(
        self,
        article_id: int,
        *,
        filename: str,
        media_type: str,
        data_blob: bytes,
        alt_text: str = "",
        caption: str = "",
        commit: bool = True,
    ) -> SessionArticleImageRecord:
        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_session_article_images (
                article_id,
                filename,
                media_type,
                alt_text,
                caption,
                data_blob,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                filename = excluded.filename,
                media_type = excluded.media_type,
                alt_text = excluded.alt_text,
                caption = excluded.caption,
                data_blob = excluded.data_blob,
                updated_at = excluded.updated_at
            """,
            (
                article_id,
                filename,
                media_type,
                alt_text,
                caption,
                sqlite3.Binary(data_blob),
                isoformat(utcnow()),
            ),
        )
        if commit:
            connection.commit()

        image = self.get_article_image(article_id)
        if image is None:
            raise RuntimeError("Failed to persist session article image.")
        return image

    def update_article_image_metadata(
        self,
        article_id: int,
        *,
        alt_text: str = "",
        caption: str = "",
        commit: bool = True,
    ) -> SessionArticleImageRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            UPDATE campaign_session_article_images
            SET alt_text = ?,
                caption = ?,
                updated_at = ?
            WHERE article_id = ?
            """,
            (
                alt_text,
                caption,
                isoformat(utcnow()),
                article_id,
            ),
        )
        if commit:
            connection.commit()
        if cursor.rowcount != 1:
            raise CampaignSessionConflictError(
                f"Unable to update session article image {article_id}"
            )

        image = self.get_article_image(article_id)
        if image is None:
            raise RuntimeError("Session article image disappeared after update.")
        return image

    def list_messages(
        self,
        session_id: int,
        *,
        viewer_user_id: int | None = None,
        include_private_messages: bool = False,
    ) -> list[SessionMessageRecord]:
        if include_private_messages:
            rows = get_db().execute(
                """
                SELECT *
                FROM campaign_session_messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        else:
            viewer_id = int(viewer_user_id or 0)
            rows = get_db().execute(
                """
                SELECT *
                FROM campaign_session_messages
                WHERE session_id = ?
                  AND (
                    COALESCE(recipient_scope, 'global') = 'global'
                    OR (recipient_scope = 'player' AND recipient_user_id = ?)
                    OR author_user_id = ?
                  )
                ORDER BY created_at ASC, id ASC
                """,
                (session_id, viewer_id, viewer_id),
            ).fetchall()
        return [self._map_message(row) for row in rows]

    def count_messages(
        self,
        session_id: int,
        *,
        viewer_user_id: int | None = None,
        include_private_messages: bool = False,
    ) -> int:
        if include_private_messages:
            row = get_db().execute(
                """
                SELECT COUNT(*) AS message_count
                FROM campaign_session_messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        else:
            viewer_id = int(viewer_user_id or 0)
            row = get_db().execute(
                """
                SELECT COUNT(*) AS message_count
                FROM campaign_session_messages
                WHERE session_id = ?
                  AND (
                    COALESCE(recipient_scope, 'global') = 'global'
                    OR (recipient_scope = 'player' AND recipient_user_id = ?)
                    OR author_user_id = ?
                  )
                """,
                (session_id, viewer_id, viewer_id),
            ).fetchone()
        return int(row["message_count"] or 0) if row is not None else 0

    def create_message(
        self,
        session_id: int,
        campaign_slug: str,
        *,
        message_type: str,
        body_text: str,
        author_display_name: str,
        author_user_id: int | None = None,
        article_id: int | None = None,
        recipient_scope: str = "global",
        recipient_user_id: int | None = None,
        commit: bool = True,
    ) -> SessionMessageRecord:
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO campaign_session_messages (
                session_id,
                campaign_slug,
                message_type,
                body_text,
                recipient_scope,
                recipient_user_id,
                author_user_id,
                author_display_name,
                article_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                campaign_slug,
                message_type,
                body_text,
                recipient_scope,
                recipient_user_id,
                author_user_id,
                author_display_name,
                article_id,
                isoformat(utcnow()),
            ),
        )
        if commit:
            connection.commit()

        message = self._get_message(int(cursor.lastrowid))
        if message is None:
            raise RuntimeError("Failed to persist session message.")
        return message

    def reveal_article_in_session(
        self,
        article_id: int,
        *,
        campaign_slug: str,
        session_id: int,
        revealed_by_user_id: int | None,
        author_display_name: str,
        commit: bool = True,
    ) -> tuple[SessionArticleRecord, SessionMessageRecord]:
        connection = get_db()
        revealed_at = isoformat(utcnow())
        cursor = connection.execute(
            """
            UPDATE campaign_session_articles
            SET status = 'revealed',
                revealed_at = ?,
                revealed_by_user_id = ?,
                revealed_in_session_id = ?
            WHERE id = ? AND campaign_slug = ? AND status = 'staged'
            """,
            (
                revealed_at,
                revealed_by_user_id,
                session_id,
                article_id,
                campaign_slug,
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise CampaignSessionConflictError(
                f"Unable to reveal session article {campaign_slug}/{article_id}"
            )

        message_cursor = connection.execute(
            """
            INSERT INTO campaign_session_messages (
                session_id,
                campaign_slug,
                message_type,
                body_text,
                recipient_scope,
                recipient_user_id,
                author_user_id,
                author_display_name,
                article_id,
                created_at
            )
            VALUES (?, ?, 'article_reveal', '', 'global', NULL, ?, ?, ?, ?)
            """,
            (
                session_id,
                campaign_slug,
                revealed_by_user_id,
                author_display_name,
                article_id,
                revealed_at,
            ),
        )
        if commit:
            connection.commit()

        article = self.get_article(article_id)
        message = self._get_message(int(message_cursor.lastrowid))
        if article is None or message is None:
            raise RuntimeError("Failed to persist revealed session article.")
        return article, message

    def _get_message(self, message_id: int) -> SessionMessageRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_session_messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
        return self._map_message(row)

    def _map_session(self, row: sqlite3.Row | None) -> CampaignSessionRecord | None:
        if row is None:
            return None
        return CampaignSessionRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            status=str(row["status"]),
            started_at=parse_timestamp(row["started_at"]) or utcnow(),
            started_by_user_id=int(row["started_by_user_id"]) if row["started_by_user_id"] is not None else None,
            ended_at=parse_timestamp(row["ended_at"]),
            ended_by_user_id=int(row["ended_by_user_id"]) if row["ended_by_user_id"] is not None else None,
        )

    def _map_state(self, row: sqlite3.Row | None) -> CampaignSessionStateRecord | None:
        if row is None:
            return None
        return CampaignSessionStateRecord(
            campaign_slug=str(row["campaign_slug"]),
            revision=max(1, int(row["revision"] or 1)),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_article(self, row: sqlite3.Row | None) -> SessionArticleRecord | None:
        if row is None:
            return None
        return SessionArticleRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            title=str(row["title"]),
            body_markdown=str(row["body_markdown"]),
            source_page_ref=str(row["source_page_ref"] or ""),
            status=str(row["status"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            revealed_at=parse_timestamp(row["revealed_at"]),
            revealed_by_user_id=int(row["revealed_by_user_id"]) if row["revealed_by_user_id"] is not None else None,
            revealed_in_session_id=int(row["revealed_in_session_id"]) if row["revealed_in_session_id"] is not None else None,
        )

    def _map_message(self, row: sqlite3.Row | None) -> SessionMessageRecord | None:
        if row is None:
            return None
        return SessionMessageRecord(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            campaign_slug=str(row["campaign_slug"]),
            message_type=str(row["message_type"]),
            body_text=str(row["body_text"]),
            recipient_scope=str(row["recipient_scope"] or "global"),
            recipient_user_id=int(row["recipient_user_id"]) if row["recipient_user_id"] is not None else None,
            author_user_id=int(row["author_user_id"]) if row["author_user_id"] is not None else None,
            author_display_name=str(row["author_display_name"]),
            article_id=int(row["article_id"]) if row["article_id"] is not None else None,
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
        )

    def _map_article_image(self, row: sqlite3.Row | None) -> SessionArticleImageRecord | None:
        if row is None:
            return None
        return SessionArticleImageRecord(
            article_id=int(row["article_id"]),
            filename=str(row["filename"]),
            media_type=str(row["media_type"]),
            alt_text=str(row["alt_text"]),
            caption=str(row["caption"]),
            data_blob=bytes(row["data_blob"]),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_session_summary(self, row: sqlite3.Row) -> CampaignSessionSummary:
        session_record = self._map_session(row)
        if session_record is None:
            raise RuntimeError("Failed to map campaign session summary.")
        return CampaignSessionSummary(
            session=session_record,
            message_count=int(row["message_count"] or 0),
            last_message_at=parse_timestamp(row["last_message_at"]),
        )

    def _map_closeout(
        self,
        row: sqlite3.Row,
        item_rows: list[sqlite3.Row],
    ) -> CampaignSessionCloseoutRecord:
        return CampaignSessionCloseoutRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            session_id=int(row["session_id"]),
            status=str(row["status"]),
            revision=int(row["revision"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            created_by_user_id=(
                int(row["created_by_user_id"])
                if row["created_by_user_id"] is not None
                else None
            ),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=(
                int(row["updated_by_user_id"])
                if row["updated_by_user_id"] is not None
                else None
            ),
            completed_at=parse_timestamp(row["completed_at"]),
            completed_by_user_id=(
                int(row["completed_by_user_id"])
                if row["completed_by_user_id"] is not None
                else None
            ),
            items=tuple(self._map_closeout_item(item_row) for item_row in item_rows),
        )

    @staticmethod
    def _map_closeout_item(row: sqlite3.Row) -> CampaignSessionCloseoutItemRecord:
        return CampaignSessionCloseoutItemRecord(
            closeout_id=int(row["closeout_id"]),
            campaign_slug=str(row["campaign_slug"]),
            item_key=str(row["item_key"]),
            status=str(row["status"]),
            note=str(row["note"] or ""),
        )

    @staticmethod
    def _map_closeout_summary(row: sqlite3.Row) -> CampaignSessionCloseoutSummary:
        return CampaignSessionCloseoutSummary(
            closeout_id=int(row["closeout_id"]),
            session_id=int(row["session_id"]),
            status=str(row["status"]),
            revision=int(row["revision"]),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            item_count=int(row["item_count"] or 0),
            resolved_count=int(row["resolved_count"] or 0),
        )
