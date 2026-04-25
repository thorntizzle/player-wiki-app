from __future__ import annotations

import json
import sqlite3
from typing import Any

from .auth_store import isoformat, parse_timestamp, utcnow
from .db import get_db
from .systems_models import (
    CampaignEnabledSourceRecord,
    CampaignEntryOverrideRecord,
    CampaignSystemsPolicyRecord,
    SystemsEntryRecord,
    SystemsImportRunRecord,
    SystemsLibraryRecord,
    SystemsSharedEntryEditEventRecord,
    SystemsSourceRecord,
)


class SystemsStore:
    def _coerce_int(self, value: Any, *, default: int) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError, AttributeError):
            return default

    def _entry_source_browse_sort_key(self, entry: SystemsEntryRecord) -> tuple[int, int, int, int, str, int]:
        if entry.entry_type == "book":
            metadata = dict(entry.metadata or {})
            return (
                0,
                self._coerce_int(metadata.get("chapter_index"), default=10_000),
                self._coerce_int(metadata.get("target_order"), default=10_000),
                self._coerce_int(entry.source_page, default=10_000),
                entry.title.lower(),
                entry.id,
            )
        return (
            1,
            10_000,
            10_000,
            self._coerce_int(entry.source_page, default=10_000),
            entry.title.lower(),
            entry.id,
        )

    def _sort_entries_for_source_browse(self, entries: list[SystemsEntryRecord]) -> list[SystemsEntryRecord]:
        if not any(entry.entry_type == "book" for entry in entries):
            return entries
        return sorted(entries, key=self._entry_source_browse_sort_key)

    def upsert_library(
        self,
        library_slug: str,
        *,
        title: str,
        system_code: str,
        status: str = "active",
    ) -> SystemsLibraryRecord:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO systems_libraries (
                library_slug,
                title,
                system_code,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(library_slug) DO UPDATE SET
                title = excluded.title,
                system_code = excluded.system_code,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (library_slug, title, system_code, status, now, now),
        )
        connection.commit()
        library = self.get_library(library_slug)
        if library is None:
            raise RuntimeError("Failed to persist systems library.")
        return library

    def get_library(self, library_slug: str) -> SystemsLibraryRecord | None:
        row = get_db().execute(
            "SELECT * FROM systems_libraries WHERE library_slug = ?",
            (library_slug,),
        ).fetchone()
        return self._map_library(row)

    def upsert_source(
        self,
        library_slug: str,
        source_id: str,
        *,
        title: str,
        license_class: str,
        license_url: str = "",
        attribution_text: str = "",
        public_visibility_allowed: bool = False,
        requires_unofficial_notice: bool = True,
        status: str = "active",
    ) -> SystemsSourceRecord:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO systems_sources (
                library_slug,
                source_id,
                title,
                license_class,
                license_url,
                attribution_text,
                public_visibility_allowed,
                requires_unofficial_notice,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(library_slug, source_id) DO UPDATE SET
                title = excluded.title,
                license_class = excluded.license_class,
                license_url = excluded.license_url,
                attribution_text = excluded.attribution_text,
                public_visibility_allowed = excluded.public_visibility_allowed,
                requires_unofficial_notice = excluded.requires_unofficial_notice,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                library_slug,
                source_id,
                title,
                license_class,
                license_url,
                attribution_text,
                int(public_visibility_allowed),
                int(requires_unofficial_notice),
                status,
                now,
                now,
            ),
        )
        connection.commit()
        source = self.get_source(library_slug, source_id)
        if source is None:
            raise RuntimeError("Failed to persist systems source.")
        return source

    def get_source(self, library_slug: str, source_id: str) -> SystemsSourceRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM systems_sources
            WHERE library_slug = ? AND source_id = ?
            """,
            (library_slug, source_id),
        ).fetchone()
        return self._map_source(row)

    def list_sources(self, library_slug: str) -> list[SystemsSourceRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM systems_sources
            WHERE library_slug = ?
            ORDER BY title ASC, source_id ASC
            """,
            (library_slug,),
        ).fetchall()
        return [self._map_source(row) for row in rows]

    def get_campaign_policy(self, campaign_slug: str) -> CampaignSystemsPolicyRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_system_policies
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        ).fetchone()
        return self._map_campaign_policy(row)

    def upsert_campaign_policy(
        self,
        campaign_slug: str,
        *,
        library_slug: str,
        status: str = "active",
        proprietary_acknowledged_at: str | None = None,
        proprietary_acknowledged_by_user_id: int | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignSystemsPolicyRecord:
        existing = self.get_campaign_policy(campaign_slug)
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_system_policies (
                campaign_slug,
                library_slug,
                status,
                proprietary_acknowledged_at,
                proprietary_acknowledged_by_user_id,
                created_at,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug) DO UPDATE SET
                library_slug = excluded.library_slug,
                status = excluded.status,
                proprietary_acknowledged_at = excluded.proprietary_acknowledged_at,
                proprietary_acknowledged_by_user_id = excluded.proprietary_acknowledged_by_user_id,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                campaign_slug,
                library_slug,
                status,
                proprietary_acknowledged_at if proprietary_acknowledged_at is not None else (
                    isoformat(existing.proprietary_acknowledged_at) if existing and existing.proprietary_acknowledged_at else None
                ),
                proprietary_acknowledged_by_user_id if proprietary_acknowledged_by_user_id is not None else (
                    existing.proprietary_acknowledged_by_user_id if existing else None
                ),
                isoformat(existing.created_at) if existing is not None else now,
                now,
                updated_by_user_id,
            ),
        )
        connection.commit()
        policy = self.get_campaign_policy(campaign_slug)
        if policy is None:
            raise RuntimeError("Failed to persist campaign systems policy.")
        return policy

    def get_campaign_enabled_source(
        self,
        campaign_slug: str,
        source_id: str,
    ) -> CampaignEnabledSourceRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_enabled_sources
            WHERE campaign_slug = ? AND source_id = ?
            """,
            (campaign_slug, source_id),
        ).fetchone()
        return self._map_campaign_enabled_source(row)

    def list_campaign_enabled_sources(self, campaign_slug: str) -> list[CampaignEnabledSourceRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_enabled_sources
            WHERE campaign_slug = ?
            ORDER BY source_id ASC
            """,
            (campaign_slug,),
        ).fetchall()
        return [self._map_campaign_enabled_source(row) for row in rows]

    def upsert_campaign_enabled_source(
        self,
        campaign_slug: str,
        *,
        library_slug: str,
        source_id: str,
        is_enabled: bool,
        default_visibility: str,
        updated_by_user_id: int | None = None,
    ) -> CampaignEnabledSourceRecord:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_enabled_sources (
                campaign_slug,
                library_slug,
                source_id,
                is_enabled,
                default_visibility,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug, source_id) DO UPDATE SET
                library_slug = excluded.library_slug,
                is_enabled = excluded.is_enabled,
                default_visibility = excluded.default_visibility,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                campaign_slug,
                library_slug,
                source_id,
                int(is_enabled),
                default_visibility,
                now,
                updated_by_user_id,
            ),
        )
        connection.commit()
        record = self.get_campaign_enabled_source(campaign_slug, source_id)
        if record is None:
            raise RuntimeError("Failed to persist campaign source policy.")
        return record

    def get_campaign_entry_override(
        self,
        campaign_slug: str,
        entry_key: str,
    ) -> CampaignEntryOverrideRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_entry_overrides
            WHERE campaign_slug = ? AND entry_key = ?
            """,
            (campaign_slug, entry_key),
        ).fetchone()
        return self._map_campaign_entry_override(row)

    def list_campaign_entry_overrides(
        self,
        campaign_slug: str,
        library_slug: str,
    ) -> list[CampaignEntryOverrideRecord]:
        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_entry_overrides
            WHERE campaign_slug = ?
              AND library_slug = ?
            ORDER BY entry_key ASC
            """,
            (campaign_slug, library_slug),
        ).fetchall()
        records: list[CampaignEntryOverrideRecord] = []
        for row in rows:
            record = self._map_campaign_entry_override(row)
            if record is not None:
                records.append(record)
        return records

    def upsert_campaign_entry_override(
        self,
        campaign_slug: str,
        *,
        library_slug: str,
        entry_key: str,
        visibility_override: str | None,
        is_enabled_override: bool | None,
        updated_by_user_id: int | None = None,
    ) -> CampaignEntryOverrideRecord:
        now = isoformat(utcnow())
        connection = get_db()
        connection.execute(
            """
            INSERT INTO campaign_entry_overrides (
                campaign_slug,
                library_slug,
                entry_key,
                visibility_override,
                is_enabled_override,
                updated_at,
                updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug, entry_key) DO UPDATE SET
                library_slug = excluded.library_slug,
                visibility_override = excluded.visibility_override,
                is_enabled_override = excluded.is_enabled_override,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                campaign_slug,
                library_slug,
                entry_key,
                visibility_override,
                None if is_enabled_override is None else int(is_enabled_override),
                now,
                updated_by_user_id,
            ),
        )
        connection.commit()
        record = self.get_campaign_entry_override(campaign_slug, entry_key)
        if record is None:
            raise RuntimeError("Failed to persist campaign entry override.")
        return record

    def get_entry(self, library_slug: str, entry_key: str) -> SystemsEntryRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM systems_entries
            WHERE library_slug = ? AND entry_key = ?
            """,
            (library_slug, entry_key),
        ).fetchone()
        return self._map_entry(row)

    def get_entry_by_slug(self, library_slug: str, slug: str) -> SystemsEntryRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM systems_entries
            WHERE library_slug = ? AND slug = ?
            """,
            (library_slug, slug),
        ).fetchone()
        return self._map_entry(row)

    def upsert_entry(
        self,
        library_slug: str,
        source_id: str,
        *,
        entry_key: str,
        entry_type: str,
        slug: str,
        title: str,
        source_page: str = "",
        source_path: str = "",
        search_text: str = "",
        player_safe_default: bool = False,
        dm_heavy: bool = False,
        metadata: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        rendered_html: str = "",
    ) -> SystemsEntryRecord:
        normalized_entry_key = str(entry_key or "").strip()
        if not normalized_entry_key:
            raise ValueError("Systems entries need an entry key.")
        existing = self.get_entry(library_slug, normalized_entry_key)
        now = isoformat(utcnow())
        created_at = isoformat(existing.created_at) if existing is not None else now
        connection = get_db()
        connection.execute(
            """
            INSERT INTO systems_entries (
                library_slug,
                source_id,
                entry_key,
                entry_type,
                slug,
                title,
                source_page,
                source_path,
                search_text,
                player_safe_default,
                dm_heavy,
                metadata_json,
                body_json,
                rendered_html,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(library_slug, entry_key) DO UPDATE SET
                source_id = excluded.source_id,
                entry_type = excluded.entry_type,
                slug = excluded.slug,
                title = excluded.title,
                source_page = excluded.source_page,
                source_path = excluded.source_path,
                search_text = excluded.search_text,
                player_safe_default = excluded.player_safe_default,
                dm_heavy = excluded.dm_heavy,
                metadata_json = excluded.metadata_json,
                body_json = excluded.body_json,
                rendered_html = excluded.rendered_html,
                updated_at = excluded.updated_at
            """,
            (
                library_slug,
                source_id,
                normalized_entry_key,
                str(entry_type),
                str(slug),
                str(title),
                str(source_page or ""),
                str(source_path or ""),
                str(search_text or ""),
                int(bool(player_safe_default)),
                int(bool(dm_heavy)),
                json.dumps(metadata or {}, sort_keys=True),
                json.dumps(body or {}, sort_keys=True),
                str(rendered_html or ""),
                created_at,
                now,
            ),
        )
        connection.commit()
        entry = self.get_entry(library_slug, normalized_entry_key)
        if entry is None:
            raise RuntimeError("Failed to persist systems entry.")
        return entry

    def record_shared_entry_edit_event(
        self,
        *,
        campaign_slug: str,
        library_slug: str,
        source_id: str,
        entry_key: str,
        entry_slug: str,
        original_source_identity: dict[str, Any],
        edited_fields: list[str],
        actor_user_id: int | None,
        audit_event_type: str,
        audit_metadata: dict[str, Any],
    ) -> SystemsSharedEntryEditEventRecord:
        now = isoformat(utcnow())
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO systems_shared_entry_edit_events (
                campaign_slug,
                library_slug,
                source_id,
                entry_key,
                entry_slug,
                original_source_identity_json,
                edited_fields_json,
                actor_user_id,
                audit_event_type,
                audit_metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(campaign_slug),
                str(library_slug),
                str(source_id),
                str(entry_key),
                str(entry_slug),
                json.dumps(original_source_identity or {}, sort_keys=True),
                json.dumps([str(field) for field in edited_fields], sort_keys=True),
                actor_user_id,
                str(audit_event_type),
                json.dumps(audit_metadata or {}, sort_keys=True),
                now,
            ),
        )
        connection.commit()
        event = self.get_shared_entry_edit_event(int(cursor.lastrowid))
        if event is None:
            raise RuntimeError("Failed to persist shared Systems entry edit event.")
        return event

    def get_shared_entry_edit_event(self, event_id: int) -> SystemsSharedEntryEditEventRecord | None:
        row = get_db().execute(
            """
            SELECT *
            FROM systems_shared_entry_edit_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        return self._map_shared_entry_edit_event(row)

    def list_shared_entry_edit_events(
        self,
        *,
        library_slug: str,
        entry_key: str,
        limit: int | None = None,
    ) -> list[SystemsSharedEntryEditEventRecord]:
        parameters: list[object] = [str(library_slug), str(entry_key)]
        query = """
            SELECT *
            FROM systems_shared_entry_edit_events
            WHERE library_slug = ? AND entry_key = ?
            ORDER BY created_at DESC, id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(max(1, int(limit)))
        rows = get_db().execute(query, tuple(parameters)).fetchall()
        return [event for row in rows if (event := self._map_shared_entry_edit_event(row)) is not None]

    def list_entries_for_source(
        self,
        library_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[SystemsEntryRecord]:
        normalized_query = query.strip().lower()
        parameters: list[Any] = [library_slug, source_id]
        apply_post_sort_limit = entry_type == "book" and (limit is not None or offset != 0)
        entry_type_clause = ""
        if entry_type:
            entry_type_clause = " AND entry_type = ?"
            parameters.append(entry_type)
        query_clause, query_parameters = self._build_entry_search_clause(
            normalized_query,
            include_source_id=False,
        )
        parameters.extend(query_parameters)
        limit_clause = ""
        if limit is not None and not apply_post_sort_limit:
            limit_clause = " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        rows = get_db().execute(
            f"""
            SELECT *
            FROM systems_entries
            WHERE library_slug = ? AND source_id = ?{entry_type_clause}{query_clause}
            ORDER BY title ASC, id ASC
            {limit_clause}
            """,
            tuple(parameters),
        ).fetchall()
        entries = self._sort_entries_for_source_browse([self._map_entry(row) for row in rows])
        if apply_post_sort_limit:
            end = None if limit is None else offset + limit
            return entries[offset:end]
        return entries

    def list_entries_for_campaign_source(
        self,
        campaign_slug: str,
        library_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[SystemsEntryRecord]:
        normalized_query = query.strip().lower()
        parameters: list[Any] = [campaign_slug, library_slug, source_id]
        apply_post_sort_limit = entry_type == "book" and (limit is not None or offset != 0)
        entry_type_clause = ""
        if entry_type:
            entry_type_clause = " AND systems_entries.entry_type = ?"
            parameters.append(entry_type)
        query_clause, query_parameters = self._build_entry_search_clause(
            normalized_query,
            include_source_id=False,
        )
        parameters.extend(query_parameters)
        limit_clause = ""
        if limit is not None and not apply_post_sort_limit:
            limit_clause = " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        rows = get_db().execute(
            f"""
            SELECT systems_entries.*
            FROM systems_entries
            LEFT JOIN campaign_entry_overrides
              ON campaign_entry_overrides.campaign_slug = ?
             AND campaign_entry_overrides.library_slug = systems_entries.library_slug
             AND campaign_entry_overrides.entry_key = systems_entries.entry_key
            WHERE systems_entries.library_slug = ?
              AND systems_entries.source_id = ?{entry_type_clause}{query_clause}
              AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
            ORDER BY systems_entries.title ASC, systems_entries.id ASC
            {limit_clause}
            """,
            tuple(parameters),
        ).fetchall()
        entries = self._sort_entries_for_source_browse([self._map_entry(row) for row in rows])
        if apply_post_sort_limit:
            end = None if limit is None else offset + limit
            return entries[offset:end]
        return entries

    def list_entries_for_campaign(
        self,
        campaign_slug: str,
        library_slug: str,
        source_ids: list[str],
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[SystemsEntryRecord]:
        normalized_source_ids = [
            str(source_id or "").strip()
            for source_id in list(source_ids or [])
            if str(source_id or "").strip()
        ]
        if not normalized_source_ids:
            return []

        placeholders = ", ".join("?" for _ in normalized_source_ids)
        normalized_query = query.strip().lower()
        parameters: list[Any] = [campaign_slug, library_slug, *normalized_source_ids]
        apply_post_sort_limit = entry_type == "book" and (limit is not None or offset != 0)
        entry_type_clause = ""
        if entry_type:
            entry_type_clause = " AND systems_entries.entry_type = ?"
            parameters.append(entry_type)
        query_clause = ""
        if normalized_query:
            query_clause, query_parameters = self._build_entry_search_clause(
                normalized_query,
                include_source_id=False,
            )
            parameters.extend(query_parameters)
        limit_clause = ""
        if limit is not None and not apply_post_sort_limit:
            limit_clause = " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        rows = get_db().execute(
            f"""
            SELECT systems_entries.*
            FROM systems_entries
            LEFT JOIN campaign_entry_overrides
              ON campaign_entry_overrides.campaign_slug = ?
             AND campaign_entry_overrides.library_slug = systems_entries.library_slug
             AND campaign_entry_overrides.entry_key = systems_entries.entry_key
            WHERE systems_entries.library_slug = ?
              AND systems_entries.source_id IN ({placeholders}){entry_type_clause}{query_clause}
              AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
            ORDER BY systems_entries.title ASC, systems_entries.id ASC
            {limit_clause}
            """,
            tuple(parameters),
        ).fetchall()
        entries = self._sort_entries_for_source_browse([self._map_entry(row) for row in rows])
        if apply_post_sort_limit:
            end = None if limit is None else offset + limit
            return entries[offset:end]
        return entries

    def list_entries(
        self,
        library_slug: str,
        *,
        source_ids: list[str] | None = None,
        entry_type: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[SystemsEntryRecord]:
        filters = ["library_slug = ?"]
        parameters: list[Any] = [library_slug]
        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            filters.append(f"source_id IN ({placeholders})")
            parameters.extend(source_ids)
        if entry_type:
            filters.append("entry_type = ?")
            parameters.append(entry_type)
        parameters.extend([limit, offset])
        rows = get_db().execute(
            f"""
            SELECT *
            FROM systems_entries
            WHERE {' AND '.join(filters)}
            ORDER BY title ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            tuple(parameters),
        ).fetchall()
        return [self._map_entry(row) for row in rows]

    def search_entries(
        self,
        library_slug: str,
        *,
        query: str,
        source_ids: list[str] | None = None,
        entry_type: str | None = None,
        limit: int | None = 100,
        offset: int = 0,
    ) -> list[SystemsEntryRecord]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        parameters: list[Any] = [library_slug]
        entry_type_clause = ""
        if entry_type:
            entry_type_clause = " AND entry_type = ?"
            parameters.append(entry_type)
        query_clause, query_parameters = self._build_entry_search_clause(
            normalized_query,
            include_source_id=True,
        )
        parameters.extend(query_parameters)
        source_clause = ""
        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            source_clause = f" AND source_id IN ({placeholders})"
            parameters.extend(source_ids)
        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        rows = get_db().execute(
            f"""
            SELECT *
            FROM systems_entries
            WHERE library_slug = ?{entry_type_clause}{query_clause}{source_clause}
            ORDER BY title ASC, id ASC
            {limit_clause}
            """,
            tuple(parameters),
        ).fetchall()
        return [self._map_entry(row) for row in rows]

    def count_entries_for_source(self, library_slug: str, source_id: str) -> int:
        row = get_db().execute(
            """
            SELECT COUNT(*) AS count
            FROM systems_entries
            WHERE library_slug = ? AND source_id = ?
            """,
            (library_slug, source_id),
        ).fetchone()
        return int(row["count"]) if row is not None else 0

    def count_entries_for_campaign_source(
        self,
        campaign_slug: str,
        library_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
    ) -> int:
        parameters: list[Any] = [campaign_slug, library_slug, source_id]
        entry_type_clause = ""
        if entry_type:
            entry_type_clause = " AND systems_entries.entry_type = ?"
            parameters.append(entry_type)
        row = get_db().execute(
            f"""
            SELECT COUNT(*) AS count
            FROM systems_entries
            LEFT JOIN campaign_entry_overrides
              ON campaign_entry_overrides.campaign_slug = ?
             AND campaign_entry_overrides.library_slug = systems_entries.library_slug
             AND campaign_entry_overrides.entry_key = systems_entries.entry_key
            WHERE systems_entries.library_slug = ?
              AND systems_entries.source_id = ?{entry_type_clause}
              AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
            """,
            tuple(parameters),
        ).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_entry_type_counts_for_campaign_source(
        self,
        campaign_slug: str,
        library_slug: str,
        source_id: str,
    ) -> list[tuple[str, int]]:
        rows = get_db().execute(
            """
            SELECT systems_entries.entry_type AS entry_type, COUNT(*) AS count
            FROM systems_entries
            LEFT JOIN campaign_entry_overrides
              ON campaign_entry_overrides.campaign_slug = ?
             AND campaign_entry_overrides.library_slug = systems_entries.library_slug
             AND campaign_entry_overrides.entry_key = systems_entries.entry_key
            WHERE systems_entries.library_slug = ?
              AND systems_entries.source_id = ?
              AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
            GROUP BY systems_entries.entry_type
            ORDER BY systems_entries.entry_type ASC
            """,
            (campaign_slug, library_slug, source_id),
        ).fetchall()
        return [
            (str(row["entry_type"]), int(row["count"]))
            for row in rows
        ]

    def get_campaign_entries_revision(
        self,
        campaign_slug: str,
        library_slug: str,
        source_ids: list[str],
        entry_types: list[str],
    ) -> tuple[tuple[str, int, str], ...]:
        normalized_source_ids = [
            str(source_id or "").strip()
            for source_id in list(source_ids or [])
            if str(source_id or "").strip()
        ]
        normalized_entry_types = [
            str(entry_type or "").strip()
            for entry_type in list(entry_types or [])
            if str(entry_type or "").strip()
        ]
        if not normalized_source_ids or not normalized_entry_types:
            return ()

        source_placeholders = ", ".join("?" for _ in normalized_source_ids)
        entry_type_placeholders = ", ".join("?" for _ in normalized_entry_types)
        rows = get_db().execute(
            f"""
            SELECT
                systems_entries.entry_type AS entry_type,
                COUNT(*) AS count,
                COALESCE(MAX(systems_entries.updated_at), '') AS updated_at
            FROM systems_entries
            LEFT JOIN campaign_entry_overrides
              ON campaign_entry_overrides.campaign_slug = ?
             AND campaign_entry_overrides.library_slug = systems_entries.library_slug
             AND campaign_entry_overrides.entry_key = systems_entries.entry_key
            WHERE systems_entries.library_slug = ?
              AND systems_entries.source_id IN ({source_placeholders})
              AND systems_entries.entry_type IN ({entry_type_placeholders})
              AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
            GROUP BY systems_entries.entry_type
            ORDER BY systems_entries.entry_type ASC
            """,
            (
                campaign_slug,
                library_slug,
                *normalized_source_ids,
                *normalized_entry_types,
            ),
        ).fetchall()
        return tuple(
            (
                str(row["entry_type"]),
                int(row["count"]),
                str(row["updated_at"] or ""),
            )
            for row in rows
        )

    def get_campaign_entry_overrides_revision(
        self,
        campaign_slug: str,
        library_slug: str,
    ) -> tuple[int, str]:
        row = get_db().execute(
            """
            SELECT
                COUNT(*) AS count,
                COALESCE(MAX(updated_at), '') AS updated_at
            FROM campaign_entry_overrides
            WHERE campaign_slug = ?
              AND library_slug = ?
            """,
            (campaign_slug, library_slug),
        ).fetchone()
        if row is None:
            return (0, "")
        return (int(row["count"]), str(row["updated_at"] or ""))

    def replace_entries_for_source(
        self,
        library_slug: str,
        source_id: str,
        *,
        entries: list[dict[str, Any]],
        entry_types: list[str] | None = None,
    ) -> int:
        now = isoformat(utcnow())
        connection = get_db()
        entry_type_clause = ""
        entry_type_parameters: list[str] = []
        if entry_types:
            placeholders = ", ".join("?" for _ in entry_types)
            entry_type_clause = f" AND entry_type IN ({placeholders})"
            entry_type_parameters = [str(entry_type) for entry_type in entry_types]
        existing_keys = [
            str(row["entry_key"])
            for row in connection.execute(
                f"""
                SELECT entry_key
                FROM systems_entries
                WHERE library_slug = ? AND source_id = ?{entry_type_clause}
                """,
                (library_slug, source_id, *entry_type_parameters),
            ).fetchall()
        ]
        if existing_keys:
            placeholders = ", ".join("?" for _ in existing_keys)
            connection.execute(
                f"""
                DELETE FROM systems_entry_links
                WHERE library_slug = ?
                  AND (
                    from_entry_key IN ({placeholders})
                    OR to_entry_key IN ({placeholders})
                  )
                """,
                (library_slug, *existing_keys, *existing_keys),
            )

        connection.execute(
            f"""
            DELETE FROM systems_entries
            WHERE library_slug = ? AND source_id = ?{entry_type_clause}
            """,
            (library_slug, source_id, *entry_type_parameters),
        )

        if entries:
            rows = [
                (
                    library_slug,
                    source_id,
                    str(entry["entry_key"]),
                    str(entry["entry_type"]),
                    str(entry["slug"]),
                    str(entry["title"]),
                    str(entry.get("source_page", "") or ""),
                    str(entry.get("source_path", "") or ""),
                    str(entry.get("search_text", "") or ""),
                    int(bool(entry.get("player_safe_default", False))),
                    int(bool(entry.get("dm_heavy", False))),
                    json.dumps(entry.get("metadata", {}), sort_keys=True),
                    json.dumps(entry.get("body", {}), sort_keys=True),
                    str(entry.get("rendered_html", "") or ""),
                    now,
                    now,
                )
                for entry in entries
            ]
            connection.executemany(
                """
                INSERT INTO systems_entries (
                    library_slug,
                    source_id,
                    entry_key,
                    entry_type,
                    slug,
                    title,
                    source_page,
                    source_path,
                    search_text,
                    player_safe_default,
                    dm_heavy,
                    metadata_json,
                    body_json,
                    rendered_html,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        connection.commit()
        return len(entries)

    def create_import_run(
        self,
        *,
        library_slug: str,
        source_id: str,
        import_version: str = "",
        source_path: str = "",
        summary: dict[str, Any] | None = None,
        started_by_user_id: int | None = None,
    ) -> SystemsImportRunRecord:
        now = isoformat(utcnow())
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO systems_import_runs (
                library_slug,
                source_id,
                status,
                import_version,
                source_path,
                summary_json,
                started_at,
                started_by_user_id
            )
            VALUES (?, ?, 'started', ?, ?, ?, ?, ?)
            """,
            (
                library_slug,
                source_id,
                import_version,
                source_path,
                json.dumps(summary or {}, sort_keys=True),
                now,
                started_by_user_id,
            ),
        )
        connection.commit()
        row = get_db().execute(
            "SELECT * FROM systems_import_runs WHERE id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create import run.")
        return self._map_import_run(row)

    def get_import_run(self, import_run_id: int) -> SystemsImportRunRecord | None:
        row = get_db().execute(
            "SELECT * FROM systems_import_runs WHERE id = ?",
            (import_run_id,),
        ).fetchone()
        return self._map_import_run(row)

    def list_import_runs(
        self,
        *,
        library_slug: str | None = None,
        source_id: str | None = None,
        limit: int | None = 20,
    ) -> list[SystemsImportRunRecord]:
        clauses: list[str] = []
        parameters: list[object] = []
        if library_slug:
            clauses.append("library_slug = ?")
            parameters.append(str(library_slug).strip())
        if source_id:
            clauses.append("source_id = ?")
            parameters.append(str(source_id).strip().upper())

        query = "SELECT * FROM systems_import_runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(max(1, int(limit)))

        rows = get_db().execute(query, tuple(parameters)).fetchall()
        return [record for row in rows if (record := self._map_import_run(row)) is not None]

    def complete_import_run(self, import_run_id: int, *, summary: dict[str, Any] | None = None) -> None:
        now = isoformat(utcnow())
        get_db().execute(
            """
            UPDATE systems_import_runs
            SET status = 'completed',
                summary_json = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (json.dumps(summary or {}, sort_keys=True), now, import_run_id),
        )
        get_db().commit()

    def fail_import_run(self, import_run_id: int, *, summary: dict[str, Any] | None = None) -> None:
        now = isoformat(utcnow())
        get_db().execute(
            """
            UPDATE systems_import_runs
            SET status = 'failed',
                summary_json = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (json.dumps(summary or {}, sort_keys=True), now, import_run_id),
        )
        get_db().commit()

    def _map_library(self, row: sqlite3.Row | None) -> SystemsLibraryRecord | None:
        if row is None:
            return None
        return SystemsLibraryRecord(
            library_slug=str(row["library_slug"]),
            title=str(row["title"]),
            system_code=str(row["system_code"]),
            status=str(row["status"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_source(self, row: sqlite3.Row | None) -> SystemsSourceRecord | None:
        if row is None:
            return None
        return SystemsSourceRecord(
            id=int(row["id"]),
            library_slug=str(row["library_slug"]),
            source_id=str(row["source_id"]),
            title=str(row["title"]),
            license_class=str(row["license_class"]),
            license_url=str(row["license_url"] or ""),
            attribution_text=str(row["attribution_text"] or ""),
            public_visibility_allowed=bool(row["public_visibility_allowed"]),
            requires_unofficial_notice=bool(row["requires_unofficial_notice"]),
            status=str(row["status"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_import_run(self, row: sqlite3.Row | None) -> SystemsImportRunRecord | None:
        if row is None:
            return None
        return SystemsImportRunRecord(
            id=int(row["id"]),
            library_slug=str(row["library_slug"]),
            source_id=str(row["source_id"]),
            status=str(row["status"]),
            import_version=str(row["import_version"] or ""),
            source_path=str(row["source_path"] or ""),
            summary=self._load_json_object(row["summary_json"]),
            started_at=parse_timestamp(row["started_at"]) or utcnow(),
            completed_at=parse_timestamp(row["completed_at"]),
            started_by_user_id=int(row["started_by_user_id"]) if row["started_by_user_id"] is not None else None,
        )

    def _map_entry(self, row: sqlite3.Row | None) -> SystemsEntryRecord | None:
        if row is None:
            return None
        return SystemsEntryRecord(
            id=int(row["id"]),
            library_slug=str(row["library_slug"]),
            source_id=str(row["source_id"]),
            entry_key=str(row["entry_key"]),
            entry_type=str(row["entry_type"]),
            slug=str(row["slug"]),
            title=str(row["title"]),
            source_page=str(row["source_page"] or ""),
            source_path=str(row["source_path"] or ""),
            search_text=str(row["search_text"] or ""),
            player_safe_default=bool(row["player_safe_default"]),
            dm_heavy=bool(row["dm_heavy"]),
            metadata=self._load_json_object(row["metadata_json"]),
            body=self._load_json_object(row["body_json"]),
            rendered_html=str(row["rendered_html"] or ""),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
        )

    def _map_shared_entry_edit_event(
        self,
        row: sqlite3.Row | None,
    ) -> SystemsSharedEntryEditEventRecord | None:
        if row is None:
            return None
        return SystemsSharedEntryEditEventRecord(
            id=int(row["id"]),
            campaign_slug=str(row["campaign_slug"]),
            library_slug=str(row["library_slug"]),
            source_id=str(row["source_id"]),
            entry_key=str(row["entry_key"]),
            entry_slug=str(row["entry_slug"]),
            original_source_identity=self._load_json_object(row["original_source_identity_json"]),
            edited_fields=self._load_json_string_list(row["edited_fields_json"]),
            actor_user_id=int(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
            audit_event_type=str(row["audit_event_type"]),
            audit_metadata=self._load_json_object(row["audit_metadata_json"]),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
        )

    def _map_campaign_policy(self, row: sqlite3.Row | None) -> CampaignSystemsPolicyRecord | None:
        if row is None:
            return None
        return CampaignSystemsPolicyRecord(
            campaign_slug=str(row["campaign_slug"]),
            library_slug=str(row["library_slug"]),
            status=str(row["status"]),
            proprietary_acknowledged_at=parse_timestamp(row["proprietary_acknowledged_at"]),
            proprietary_acknowledged_by_user_id=(
                int(row["proprietary_acknowledged_by_user_id"])
                if row["proprietary_acknowledged_by_user_id"] is not None
                else None
            ),
            created_at=parse_timestamp(row["created_at"]) or utcnow(),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_campaign_enabled_source(
        self,
        row: sqlite3.Row | None,
    ) -> CampaignEnabledSourceRecord | None:
        if row is None:
            return None
        return CampaignEnabledSourceRecord(
            campaign_slug=str(row["campaign_slug"]),
            library_slug=str(row["library_slug"]),
            source_id=str(row["source_id"]),
            is_enabled=bool(row["is_enabled"]),
            default_visibility=str(row["default_visibility"]),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _map_campaign_entry_override(
        self,
        row: sqlite3.Row | None,
    ) -> CampaignEntryOverrideRecord | None:
        if row is None:
            return None
        raw_enabled = row["is_enabled_override"]
        return CampaignEntryOverrideRecord(
            campaign_slug=str(row["campaign_slug"]),
            library_slug=str(row["library_slug"]),
            entry_key=str(row["entry_key"]),
            visibility_override=str(row["visibility_override"]) if row["visibility_override"] is not None else None,
            is_enabled_override=(bool(raw_enabled) if raw_enabled is not None else None),
            updated_at=parse_timestamp(row["updated_at"]) or utcnow(),
            updated_by_user_id=int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        )

    def _load_json_object(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _load_json_string_list(self, raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(value) for value in parsed if str(value)]

    def _build_entry_search_clause(
        self,
        normalized_query: str,
        *,
        include_source_id: bool,
    ) -> tuple[str, list[str]]:
        search_terms = [term for term in normalized_query.split() if term]
        if not search_terms:
            return "", []

        clauses: list[str] = []
        parameters: list[str] = []
        for term in search_terms:
            like_value = f"%{term}%"
            term_clauses = [
                "LOWER(title) LIKE ?",
                "LOWER(entry_type) LIKE ?",
            ]
            parameters.extend([like_value, like_value])
            if include_source_id:
                term_clauses.append("LOWER(source_id) LIKE ?")
                parameters.append(like_value)
            clauses.append(f"({' OR '.join(term_clauses)})")
        return f" AND {' AND '.join(clauses)}", parameters
