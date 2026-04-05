from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db
from .themes import DEFAULT_THEME_KEY, normalize_theme_key

SESSION_CHAT_ORDER_NEWEST_FIRST = "newest_first"
SESSION_CHAT_ORDER_OLDEST_FIRST = "oldest_first"
DEFAULT_SESSION_CHAT_ORDER = SESSION_CHAT_ORDER_NEWEST_FIRST
VALID_SESSION_CHAT_ORDERS = frozenset(
    {
        SESSION_CHAT_ORDER_NEWEST_FIRST,
        SESSION_CHAT_ORDER_OLDEST_FIRST,
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_session_chat_order(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_SESSION_CHAT_ORDERS:
        return normalized
    return DEFAULT_SESSION_CHAT_ORDER


def is_valid_session_chat_order(value: str | None) -> bool:
    return str(value or "").strip().lower() in VALID_SESSION_CHAT_ORDERS


@dataclass(slots=True)
class UserAccount:
    id: int
    email: str
    display_name: str
    is_admin: bool
    status: str
    password_hash: str | None
    auth_version: int
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(slots=True)
class CampaignMembership:
    id: int
    user_id: int
    campaign_slug: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class UserPreferences:
    user_id: int
    theme_key: str
    session_chat_order: str
    updated_at: datetime


@dataclass(slots=True)
class CampaignVisibilitySetting:
    campaign_slug: str
    scope: str
    visibility: str
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(slots=True)
class CharacterAssignment:
    id: int
    user_id: int
    campaign_slug: str
    character_slug: str
    assignment_type: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class InviteTokenRecord:
    id: int
    user_id: int
    expires_at: datetime
    used_at: datetime | None
    created_by_user_id: int | None
    created_at: datetime


@dataclass(slots=True)
class PasswordResetTokenRecord:
    id: int
    user_id: int
    expires_at: datetime
    used_at: datetime | None
    created_by_user_id: int | None
    created_at: datetime


@dataclass(slots=True)
class SessionRecord:
    id: int
    user_id: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip_address: str | None


@dataclass(slots=True)
class ApiTokenRecord:
    id: int
    user_id: int
    label: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    created_by_user_id: int | None

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= utcnow():
            return False
        return True


@dataclass(slots=True)
class AuditEventRecord:
    id: int
    actor_user_id: int | None
    target_user_id: int | None
    campaign_slug: str | None
    character_slug: str | None
    event_type: str
    metadata: dict[str, Any]
    created_at: datetime
    actor_display_name: str | None
    actor_email: str | None
    target_display_name: str | None
    target_email: str | None


SENSITIVE_AUDIT_METADATA_KEYS = frozenset({"invite_url", "reset_url", "raw_token", "token"})


class AuthStore:
    def _ensure_user_preferences_schema(self) -> None:
        connection = get_db()
        columns = {
            str(row["name"] or "")
            for row in connection.execute("PRAGMA table_info(user_preferences)").fetchall()
        }
        if "session_chat_order" in columns:
            return

        connection.execute(
            """
            ALTER TABLE user_preferences
            ADD COLUMN session_chat_order TEXT NOT NULL DEFAULT 'newest_first'
            """
        )
        connection.commit()

    def create_user(
        self,
        email: str,
        display_name: str,
        *,
        is_admin: bool = False,
        status: str = "invited",
        password_hash: str | None = None,
    ) -> UserAccount:
        normalized_email = normalize_email(email)
        now = isoformat(utcnow())
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO users (
                email,
                display_name,
                is_admin,
                status,
                password_hash,
                auth_version,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                normalized_email,
                display_name.strip(),
                int(is_admin),
                status,
                password_hash,
                now,
                now,
            ),
        )
        connection.commit()
        return self.get_user_by_id(int(cursor.lastrowid))

    def get_user_by_email(self, email: str) -> UserAccount | None:
        row = get_db().execute(
            "SELECT * FROM users WHERE email = ?",
            (normalize_email(email),),
        ).fetchone()
        return self._map_user(row)

    def get_user_by_id(self, user_id: int) -> UserAccount | None:
        row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._map_user(row)

    def list_users(self) -> list[UserAccount]:
        rows = get_db().execute("SELECT * FROM users ORDER BY email ASC").fetchall()
        return [self._map_user(row) for row in rows]

    def get_user_preferences(self, user_id: int) -> UserPreferences:
        self._ensure_user_preferences_schema()
        row = get_db().execute(
            """
            SELECT *
            FROM user_preferences
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return self._map_user_preferences(row, user_id=user_id)

    def set_user_theme_key(self, user_id: int, theme_key: str) -> UserPreferences:
        self._ensure_user_preferences_schema()
        normalized_theme_key = normalize_theme_key(theme_key)
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO user_preferences (
                user_id,
                theme_key,
                session_chat_order,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                theme_key = excluded.theme_key,
                updated_at = excluded.updated_at
            """,
            (user_id, normalized_theme_key, DEFAULT_SESSION_CHAT_ORDER, now),
        )
        connection.commit()
        return self.get_user_preferences(user_id)

    def set_user_session_chat_order(self, user_id: int, session_chat_order: str) -> UserPreferences:
        self._ensure_user_preferences_schema()
        normalized_order = normalize_session_chat_order(session_chat_order)
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO user_preferences (
                user_id,
                theme_key,
                session_chat_order,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                session_chat_order = excluded.session_chat_order,
                updated_at = excluded.updated_at
            """,
            (user_id, DEFAULT_THEME_KEY, normalized_order, now),
        )
        connection.commit()
        return self.get_user_preferences(user_id)

    def list_recent_audit_events(
        self,
        *,
        limit: int = 40,
        offset: int = 0,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
    ) -> list[AuditEventRecord]:
        return self._list_audit_events(
            limit=limit,
            offset=offset,
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
        )

    def count_recent_audit_events(
        self,
        *,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
    ) -> int:
        return self._count_audit_events(
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
        )

    def list_audit_events_for_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
    ) -> list[AuditEventRecord]:
        return self._list_audit_events(
            limit=limit,
            offset=offset,
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
            actor_or_target_user_id=user_id,
        )

    def count_audit_events_for_user(
        self,
        user_id: int,
        *,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
    ) -> int:
        return self._count_audit_events(
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
            actor_or_target_user_id=user_id,
        )

    def activate_user(self, user_id: int, *, display_name: str, password_hash: str) -> UserAccount:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            UPDATE users
            SET display_name = ?, status = 'active', password_hash = ?, auth_version = auth_version + 1, updated_at = ?
            WHERE id = ?
            """,
            (display_name.strip(), password_hash, now, user_id),
        )
        connection.commit()
        return self.get_user_by_id(user_id)

    def set_password(self, user_id: int, password_hash: str) -> UserAccount:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, auth_version = auth_version + 1, updated_at = ?
            WHERE id = ?
            """,
            (password_hash, now, user_id),
        )
        connection.commit()
        return self.get_user_by_id(user_id)

    def disable_user(self, user_id: int) -> UserAccount:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            "UPDATE users SET status = 'disabled', auth_version = auth_version + 1, updated_at = ? WHERE id = ?",
            (now, user_id),
        )
        connection.commit()
        return self.get_user_by_id(user_id)

    def enable_user(self, user_id: int) -> UserAccount:
        user = self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("Cannot enable a missing user.")

        restored_status = "active" if user.password_hash else "invited"
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            "UPDATE users SET status = ?, auth_version = auth_version + 1, updated_at = ? WHERE id = ?",
            (restored_status, now, user_id),
        )
        connection.commit()
        enabled_user = self.get_user_by_id(user_id)
        if enabled_user is None:
            raise RuntimeError("Failed to re-enable user.")
        return enabled_user

    def delete_user(self, user_id: int) -> UserAccount | None:
        user = self.get_user_by_id(user_id)
        if user is None:
            return None

        connection = get_db()
        with connection:
            connection.execute("DELETE FROM campaign_memberships WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM character_assignments WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM invite_tokens WHERE user_id = ?", (user_id,))
            connection.execute(
                "UPDATE invite_tokens SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            connection.execute(
                "UPDATE password_reset_tokens SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,))
            connection.execute(
                "UPDATE api_tokens SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE auth_audit_log SET actor_user_id = NULL WHERE actor_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE auth_audit_log SET target_user_id = NULL WHERE target_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_visibility_settings SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE character_state SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_sessions SET started_by_user_id = NULL WHERE started_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_sessions SET ended_by_user_id = NULL WHERE ended_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_session_states SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_session_articles SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_session_articles SET revealed_by_user_id = NULL WHERE revealed_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_session_messages SET author_user_id = NULL WHERE author_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_dm_statblocks SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_dm_statblocks SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_dm_condition_definitions SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_dm_condition_definitions SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_combatants SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_combatants SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_combat_trackers SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_combat_conditions SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE systems_import_runs SET started_by_user_id = NULL WHERE started_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                """
                UPDATE campaign_system_policies
                SET proprietary_acknowledged_by_user_id = NULL
                WHERE proprietary_acknowledged_by_user_id = ?
                """,
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_system_policies SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_enabled_sources SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE campaign_entry_overrides SET updated_by_user_id = NULL WHERE updated_by_user_id = ?",
                (user_id,),
            )
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("Failed to delete user.")

        return user

    def list_memberships_for_user(
        self,
        user_id: int,
        *,
        statuses: tuple[str, ...] = ("active",),
    ) -> list[CampaignMembership]:
        rows = get_db().execute(
            "SELECT * FROM campaign_memberships WHERE user_id = ? ORDER BY campaign_slug ASC",
            (user_id,),
        ).fetchall()
        memberships = [self._map_membership(row) for row in rows]
        return [membership for membership in memberships if membership.status in statuses]

    def get_membership(
        self,
        user_id: int,
        campaign_slug: str,
        *,
        statuses: tuple[str, ...] | None = ("active",),
    ) -> CampaignMembership | None:
        row = get_db().execute(
            "SELECT * FROM campaign_memberships WHERE user_id = ? AND campaign_slug = ?",
            (user_id, campaign_slug),
        ).fetchone()
        membership = self._map_membership(row)
        if membership is None:
            return None
        if statuses is not None and membership.status not in statuses:
            return None
        return membership

    def upsert_membership(
        self,
        user_id: int,
        campaign_slug: str,
        *,
        role: str,
        status: str = "active",
    ) -> CampaignMembership:
        now = isoformat(utcnow())
        existing = self.get_membership(user_id, campaign_slug, statuses=None)
        connection = get_db()
        if existing is None:
            connection.execute(
                """
                INSERT INTO campaign_memberships (
                    user_id,
                    campaign_slug,
                    role,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, campaign_slug, role, status, now, now),
            )
        else:
            connection.execute(
                """
                UPDATE campaign_memberships
                SET role = ?, status = ?, updated_at = ?
                WHERE user_id = ? AND campaign_slug = ?
                """,
                (role, status, now, user_id, campaign_slug),
            )
        connection.commit()
        membership = self.get_membership(user_id, campaign_slug, statuses=None)
        if membership is None:
            raise RuntimeError("Failed to persist campaign membership.")
        return membership

    def list_campaign_visibility_settings(self, campaign_slug: str) -> list[CampaignVisibilitySetting]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_visibility_settings
            WHERE campaign_slug = ?
            ORDER BY scope ASC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_visibility_setting(row) for row in rows]

    def get_campaign_visibility_setting(
        self,
        campaign_slug: str,
        scope: str,
    ) -> CampaignVisibilitySetting | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_visibility_settings
            WHERE campaign_slug = ? AND scope = ?
            """,
            (campaign_slug, scope),
        ).fetchone()
        return self._map_visibility_setting(row)

    def upsert_campaign_visibility_setting(
        self,
        campaign_slug: str,
        scope: str,
        *,
        visibility: str,
        updated_by_user_id: int | None = None,
    ) -> CampaignVisibilitySetting:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_visibility_settings (
                campaign_slug,
                scope,
                visibility,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug, scope) DO UPDATE SET
                visibility = excluded.visibility,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                campaign_slug,
                scope,
                visibility,
                now,
                updated_by_user_id,
            ),
        )
        connection.commit()
        setting = self.get_campaign_visibility_setting(campaign_slug, scope)
        if setting is None:
            raise RuntimeError("Failed to persist campaign visibility setting.")
        return setting

    def get_character_assignment(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterAssignment | None:
        row = get_db().execute(
            """
            SELECT * FROM character_assignments
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        ).fetchone()
        return self._map_assignment(row)

    def list_character_assignments_for_user(
        self,
        user_id: int,
        *,
        campaign_slug: str | None = None,
    ) -> list[CharacterAssignment]:
        if campaign_slug is None:
            rows = get_db().execute(
                "SELECT * FROM character_assignments WHERE user_id = ? ORDER BY campaign_slug, character_slug",
                (user_id,),
            ).fetchall()
        else:
            rows = get_db().execute(
                """
                SELECT * FROM character_assignments
                WHERE user_id = ? AND campaign_slug = ?
                ORDER BY character_slug
                """,
                (user_id, campaign_slug),
            ).fetchall()
        return [self._map_assignment(row) for row in rows]

    def upsert_character_assignment(
        self,
        user_id: int,
        campaign_slug: str,
        character_slug: str,
        *,
        assignment_type: str = "owner",
    ) -> CharacterAssignment:
        now = isoformat(utcnow())
        existing = self.get_character_assignment(campaign_slug, character_slug)
        connection = get_db()
        if existing is None:
            connection.execute(
                """
                INSERT INTO character_assignments (
                    user_id,
                    campaign_slug,
                    character_slug,
                    assignment_type,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, campaign_slug, character_slug, assignment_type, now, now),
            )
        else:
            connection.execute(
                """
                UPDATE character_assignments
                SET user_id = ?, assignment_type = ?, updated_at = ?
                WHERE campaign_slug = ? AND character_slug = ?
                """,
                (user_id, assignment_type, now, campaign_slug, character_slug),
            )
        connection.commit()
        assignment = self.get_character_assignment(campaign_slug, character_slug)
        if assignment is None:
            raise RuntimeError("Failed to persist character assignment.")
        return assignment

    def delete_character_assignment(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterAssignment | None:
        assignment = self.get_character_assignment(campaign_slug, character_slug)
        if assignment is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM character_assignments
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (campaign_slug, character_slug),
        )
        connection.commit()
        return assignment

    def issue_invite_token(
        self,
        user_id: int,
        *,
        expires_in: timedelta,
        created_by_user_id: int | None = None,
    ) -> str:
        return self._issue_token(
            "invite_tokens",
            user_id,
            expires_in=expires_in,
            created_by_user_id=created_by_user_id,
        )

    def issue_password_reset_token(
        self,
        user_id: int,
        *,
        expires_in: timedelta,
        created_by_user_id: int | None = None,
    ) -> str:
        return self._issue_token(
            "password_reset_tokens",
            user_id,
            expires_in=expires_in,
            created_by_user_id=created_by_user_id,
        )

    def get_valid_invite(
        self,
        raw_token: str,
    ) -> tuple[InviteTokenRecord, UserAccount] | None:
        row = self._get_valid_token_row("invite_tokens", raw_token)
        if row is None:
            return None

        token_record = self._map_invite_token(row)
        user = self.get_user_by_id(token_record.user_id)
        if user is None or user.status == "disabled":
            return None
        return token_record, user

    def get_valid_password_reset(
        self,
        raw_token: str,
    ) -> tuple[PasswordResetTokenRecord, UserAccount] | None:
        row = self._get_valid_token_row("password_reset_tokens", raw_token)
        if row is None:
            return None

        token_record = self._map_password_reset_token(row)
        user = self.get_user_by_id(token_record.user_id)
        if user is None or not user.is_active:
            return None
        return token_record, user

    def consume_invite(self, token_id: int) -> None:
        self._consume_token("invite_tokens", token_id)

    def consume_password_reset(self, token_id: int) -> None:
        self._consume_token("password_reset_tokens", token_id)

    def create_session(
        self,
        user_id: int,
        *,
        expires_in: timedelta,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, SessionRecord]:
        raw_token = generate_token()
        token_hash = hash_token(raw_token)
        now = utcnow()
        expires_at = now + expires_in
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO sessions (
                user_id,
                token_hash,
                created_at,
                last_seen_at,
                expires_at,
                revoked_at,
                user_agent,
                ip_address
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                user_id,
                token_hash,
                isoformat(now),
                isoformat(now),
                isoformat(expires_at),
                user_agent,
                ip_address,
            ),
        )
        connection.commit()
        session_record = self.get_active_session(raw_token)
        if session_record is None:
            raise RuntimeError("Failed to persist session.")
        return raw_token, session_record

    def get_active_session(self, raw_token: str) -> SessionRecord | None:
        row = get_db().execute(
            """
            SELECT * FROM sessions
            WHERE token_hash = ?
            """,
            (hash_token(raw_token),),
        ).fetchone()
        session_record = self._map_session(row)
        if session_record is None:
            return None
        if session_record.revoked_at is not None:
            return None
        if session_record.expires_at <= utcnow():
            return None
        return session_record

    def touch_session(self, session_id: int, *, at: datetime | None = None) -> None:
        connection = get_db()
        connection.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
            (isoformat(at or utcnow()), session_id),
        )
        connection.commit()

    def revoke_session(self, session_id: int) -> None:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            "UPDATE sessions SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
            (now, session_id),
        )
        connection.commit()

    def revoke_all_user_sessions(self, user_id: int) -> None:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            "UPDATE sessions SET revoked_at = COALESCE(revoked_at, ?) WHERE user_id = ?",
            (now, user_id),
        )
        connection.commit()

    def create_api_token(
        self,
        user_id: int,
        *,
        label: str,
        expires_in: timedelta | None = None,
        created_by_user_id: int | None = None,
    ) -> tuple[str, ApiTokenRecord]:
        normalized_label = label.strip()
        if not normalized_label:
            raise ValueError("API token label is required.")

        raw_token = generate_token()
        token_hash = hash_token(raw_token)
        now = utcnow()
        expires_at = now + expires_in if expires_in is not None else None
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO api_tokens (
                user_id,
                label,
                token_hash,
                created_at,
                last_used_at,
                expires_at,
                revoked_at,
                created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                user_id,
                normalized_label,
                token_hash,
                isoformat(now),
                isoformat(now),
                isoformat(expires_at) if expires_at is not None else None,
                created_by_user_id,
            ),
        )
        connection.commit()
        token_record = self.get_api_token_by_id(int(cursor.lastrowid))
        if token_record is None:
            raise RuntimeError("Failed to persist API token.")
        return raw_token, token_record

    def get_api_token_by_id(self, token_id: int) -> ApiTokenRecord | None:
        row = get_db().execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
        return self._map_api_token(row)

    def list_api_tokens_for_user(self, user_id: int) -> list[ApiTokenRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM api_tokens
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
        return [self._map_api_token(row) for row in rows]

    def get_active_api_token(self, raw_token: str) -> ApiTokenRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM api_tokens
            WHERE token_hash = ?
            """,
            (hash_token(raw_token),),
        ).fetchone()
        token_record = self._map_api_token(row)
        if token_record is None or not token_record.is_active:
            return None
        return token_record

    def touch_api_token(self, token_id: int, *, at: datetime | None = None) -> None:
        connection = get_db()
        connection.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
            (isoformat(at or utcnow()), token_id),
        )
        connection.commit()

    def revoke_api_token(self, token_id: int) -> ApiTokenRecord | None:
        token_record = self.get_api_token_by_id(token_id)
        if token_record is None:
            return None

        connection = get_db()
        connection.execute(
            "UPDATE api_tokens SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
            (isoformat(utcnow()), token_id),
        )
        connection.commit()
        return self.get_api_token_by_id(token_id)

    def revoke_all_user_api_tokens(self, user_id: int) -> None:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            "UPDATE api_tokens SET revoked_at = COALESCE(revoked_at, ?) WHERE user_id = ?",
            (now, user_id),
        )
        connection.commit()

    def write_audit_event(
        self,
        *,
        event_type: str,
        actor_user_id: int | None = None,
        target_user_id: int | None = None,
        campaign_slug: str | None = None,
        character_slug: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        sanitized_metadata = self._sanitize_audit_metadata(metadata or {})
        connection = get_db()
        connection.execute(
            """
            INSERT INTO auth_audit_log (
                actor_user_id,
                target_user_id,
                campaign_slug,
                character_slug,
                event_type,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_user_id,
                target_user_id,
                campaign_slug,
                character_slug,
                event_type,
                json.dumps(sanitized_metadata, sort_keys=True),
                isoformat(utcnow()),
            ),
        )
        connection.commit()

    def _list_audit_events(
        self,
        *,
        limit: int,
        offset: int = 0,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
        actor_or_target_user_id: int | None = None,
    ) -> list[AuditEventRecord]:
        where_clause, parameters = self._build_audit_filter_clause(
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
            actor_or_target_user_id=actor_or_target_user_id,
        )
        rows = get_db().execute(
            f"""
            SELECT
                log.*,
                actor.display_name AS actor_display_name,
                actor.email AS actor_email,
                target.display_name AS target_display_name,
                target.email AS target_email
            FROM auth_audit_log AS log
            LEFT JOIN users AS actor ON actor.id = log.actor_user_id
            LEFT JOIN users AS target ON target.id = log.target_user_id
            {where_clause}
            ORDER BY log.created_at DESC, log.id DESC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, max(0, offset)),
        ).fetchall()
        return [self._map_audit_event(row) for row in rows]

    def _count_audit_events(
        self,
        *,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
        actor_or_target_user_id: int | None = None,
    ) -> int:
        where_clause, parameters = self._build_audit_filter_clause(
            query=query,
            event_type=event_type,
            campaign_slug=campaign_slug,
            actor_or_target_user_id=actor_or_target_user_id,
        )
        row = get_db().execute(
            f"""
            SELECT COUNT(*) AS count
            FROM auth_audit_log AS log
            LEFT JOIN users AS actor ON actor.id = log.actor_user_id
            LEFT JOIN users AS target ON target.id = log.target_user_id
            {where_clause}
            """,
            parameters,
        ).fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def _build_audit_filter_clause(
        self,
        *,
        query: str | None = None,
        event_type: str | None = None,
        campaign_slug: str | None = None,
        actor_or_target_user_id: int | None = None,
    ) -> tuple[str, list[Any]]:
        filters: list[str] = []
        parameters: list[Any] = []

        if actor_or_target_user_id is not None:
            filters.append("(log.actor_user_id = ? OR log.target_user_id = ?)")
            parameters.extend((actor_or_target_user_id, actor_or_target_user_id))

        normalized_query = (query or "").strip().lower()
        if normalized_query:
            like_query = f"%{normalized_query}%"
            filters.append(
                """
                (
                    LOWER(log.event_type) LIKE ?
                    OR LOWER(COALESCE(log.campaign_slug, '')) LIKE ?
                    OR LOWER(COALESCE(log.character_slug, '')) LIKE ?
                    OR LOWER(COALESCE(actor.display_name, '')) LIKE ?
                    OR LOWER(COALESCE(actor.email, '')) LIKE ?
                    OR LOWER(COALESCE(target.display_name, '')) LIKE ?
                    OR LOWER(COALESCE(target.email, '')) LIKE ?
                    OR LOWER(COALESCE(log.metadata_json, '')) LIKE ?
                )
                """
            )
            parameters.extend([like_query] * 8)

        normalized_event_type = (event_type or "").strip()
        if normalized_event_type:
            filters.append("log.event_type = ?")
            parameters.append(normalized_event_type)

        normalized_campaign_slug = (campaign_slug or "").strip()
        if normalized_campaign_slug:
            filters.append("log.campaign_slug = ?")
            parameters.append(normalized_campaign_slug)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        return where_clause, parameters

    def _issue_token(
        self,
        table_name: str,
        user_id: int,
        *,
        expires_in: timedelta,
        created_by_user_id: int | None = None,
    ) -> str:
        raw_token = generate_token()
        now = utcnow()
        connection = get_db()
        connection.execute(
            f"UPDATE {table_name} SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
            (isoformat(now), user_id),
        )
        connection.execute(
            f"""
            INSERT INTO {table_name} (
                user_id,
                token_hash,
                expires_at,
                used_at,
                created_by_user_id,
                created_at
            )
            VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (
                user_id,
                hash_token(raw_token),
                isoformat(now + expires_in),
                created_by_user_id,
                isoformat(now),
            ),
        )
        connection.commit()
        return raw_token

    def _get_valid_token_row(self, table_name: str, raw_token: str) -> sqlite3.Row | None:
        row = get_db().execute(
            f"SELECT * FROM {table_name} WHERE token_hash = ?",
            (hash_token(raw_token),),
        ).fetchone()
        if row is None:
            return None
        used_at = parse_timestamp(row["used_at"])
        expires_at = parse_timestamp(row["expires_at"])
        if used_at is not None or expires_at is None or expires_at <= utcnow():
            return None
        return row

    def _consume_token(self, table_name: str, token_id: int) -> None:
        connection = get_db()
        connection.execute(
            f"UPDATE {table_name} SET used_at = COALESCE(used_at, ?) WHERE id = ?",
            (isoformat(utcnow()), token_id),
        )
        connection.commit()

    def _map_user(self, row: sqlite3.Row | None) -> UserAccount | None:
        if row is None:
            return None
        return UserAccount(
            id=int(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            is_admin=bool(row["is_admin"]),
            status=str(row["status"]),
            password_hash=row["password_hash"],
            auth_version=int(row["auth_version"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_membership(self, row: sqlite3.Row | None) -> CampaignMembership | None:
        if row is None:
            return None
        return CampaignMembership(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            campaign_slug=str(row["campaign_slug"]),
            role=str(row["role"]),
            status=str(row["status"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_user_preferences(
        self,
        row: sqlite3.Row | None,
        *,
        user_id: int,
    ) -> UserPreferences:
        if row is None:
            return UserPreferences(
                user_id=user_id,
                theme_key=DEFAULT_THEME_KEY,
                session_chat_order=DEFAULT_SESSION_CHAT_ORDER,
                updated_at=utcnow(),
            )
        row_keys = set(row.keys())
        return UserPreferences(
            user_id=int(row["user_id"]),
            theme_key=normalize_theme_key(row["theme_key"]),
            session_chat_order=normalize_session_chat_order(
                row["session_chat_order"] if "session_chat_order" in row_keys else DEFAULT_SESSION_CHAT_ORDER
            ),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_assignment(self, row: sqlite3.Row | None) -> CharacterAssignment | None:
        if row is None:
            return None
        return CharacterAssignment(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            campaign_slug=str(row["campaign_slug"]),
            character_slug=str(row["character_slug"]),
            assignment_type=str(row["assignment_type"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_visibility_setting(self, row: sqlite3.Row | None) -> CampaignVisibilitySetting | None:
        if row is None:
            return None
        return CampaignVisibilitySetting(
            campaign_slug=str(row["campaign_slug"]),
            scope=str(row["scope"]),
            visibility=str(row["visibility"]),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_invite_token(self, row: sqlite3.Row) -> InviteTokenRecord:
        return InviteTokenRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            expires_at=parse_timestamp(row["expires_at"]) or utcnow(),
            used_at=parse_timestamp(row["used_at"]),
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
        )

    def _map_password_reset_token(self, row: sqlite3.Row) -> PasswordResetTokenRecord:
        return PasswordResetTokenRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            expires_at=parse_timestamp(row["expires_at"]) or utcnow(),
            used_at=parse_timestamp(row["used_at"]),
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
        )

    def _map_session(self, row: sqlite3.Row | None) -> SessionRecord | None:
        if row is None:
            return None
        return SessionRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            last_seen_at=parse_timestamp(row["last_seen_at"]) or utcnow(),
            expires_at=parse_timestamp(row["expires_at"]) or utcnow(),
            revoked_at=parse_timestamp(row["revoked_at"]),
            user_agent=row["user_agent"],
            ip_address=row["ip_address"],
        )

    def _map_api_token(self, row: sqlite3.Row | None) -> ApiTokenRecord | None:
        if row is None:
            return None
        return ApiTokenRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            label=str(row["label"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            last_used_at=parse_timestamp(row["last_used_at"]) or utcnow(),
            expires_at=parse_timestamp(row["expires_at"]),
            revoked_at=parse_timestamp(row["revoked_at"]),
            created_by_user_id=int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
        )

    def _map_audit_event(self, row: sqlite3.Row) -> AuditEventRecord:
        return AuditEventRecord(
            id=int(row["id"]),
            actor_user_id=int(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
            target_user_id=int(row["target_user_id"]) if row["target_user_id"] is not None else None,
            campaign_slug=str(row["campaign_slug"]) if row["campaign_slug"] is not None else None,
            character_slug=str(row["character_slug"]) if row["character_slug"] is not None else None,
            event_type=str(row["event_type"]),
            metadata=self._load_audit_metadata(row["metadata_json"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            actor_display_name=str(row["actor_display_name"]) if row["actor_display_name"] is not None else None,
            actor_email=str(row["actor_email"]) if row["actor_email"] is not None else None,
            target_display_name=str(row["target_display_name"]) if row["target_display_name"] is not None else None,
            target_email=str(row["target_email"]) if row["target_email"] is not None else None,
        )

    def _load_audit_metadata(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        sanitized = self._sanitize_audit_metadata(parsed)
        return {str(key): value for key, value in sanitized.items()}

    def _sanitize_audit_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            str(key): value
            for key, value in metadata.items()
            if str(key) not in SENSITIVE_AUDIT_METADATA_KEYS
        }
