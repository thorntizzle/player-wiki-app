from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .auth_store import isoformat, utcnow
from .character_campaign_options import normalize_campaign_base_rule_refs
from .db import get_db
from .models import (
    DEPRECATED_WIKI_PAGE_TYPES,
    DEPRECATED_WIKI_SECTIONS,
    Page,
    page_sort_key,
    section_sort_key,
    subsection_sort_key,
)
from .repository import build_page_from_content
from .campaign_page_refresh import (
    CampaignRefreshTransactionError, StaleCampaignRefreshPlan, build_page_payload, capture_source_snapshot,
    discover_source_snapshot, diff_page_payloads, normalize_page_ref,
    plan_campaign_refresh, row_identity, validate_witnesses,
)
from .source_health import (
    SourceHealthConsumer,
    SourceHealthCursorError,
    SourceHealthInventoryPage,
    SourceHealthReference,
    SourceHealthResolution,
    SourceHealthTarget,
)


_SQLITE_MAX_INTEGER = 2**63 - 1


def _parse_mechanics_source_health_cursor(continuation: str) -> tuple[int, str]:
    if continuation == "":
        return 0, ""
    if not isinstance(continuation, str):
        raise SourceHealthCursorError("Invalid Mechanics cursor.")
    parts = continuation.split(":")
    if len(parts) != 3 or parts[0] != "mh1":
        raise SourceHealthCursorError("Invalid Mechanics cursor.")
    offset_text, digest = parts[1:]
    if (
        not offset_text
        or offset_text[0] not in "123456789"
        or any(character not in "0123456789" for character in offset_text[1:])
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SourceHealthCursorError("Invalid Mechanics cursor.")
    offset = int(offset_text)
    if offset > _SQLITE_MAX_INTEGER:
        raise SourceHealthCursorError("Invalid Mechanics cursor.")
    return offset, digest


def _mechanics_source_health_anchor_digest(campaign_slug: str, row) -> str:
    payload = {
        "campaign": campaign_slug,
        "owner": "mechanics",
        "row": {
            "metadata_json": row["metadata_json"],
            "page_ref": row["page_ref"],
            "route_slug": row["route_slug"],
            "updated_at": row["updated_at"],
        },
        "version": "mh1",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(slots=True)
class CampaignPageRecord:
    campaign_slug: str
    page_ref: str
    relative_path: str
    metadata: dict[str, Any]
    body_markdown: str
    page: Page
    updated_at: str


def _mechanics_base_rule_ref_groups(
    metadata: dict[str, Any],
) -> tuple[tuple[str, object], ...]:
    groups: list[tuple[str, object]] = []
    character_option = metadata.get("character_option")
    if isinstance(character_option, dict):
        groups.append(
            (
                "character_option.base_rule_refs",
                character_option.get("base_rule_refs", character_option.get("baseRuleRefs")),
            )
        )
    progression = metadata.get("character_progression")
    progression_rows = progression if isinstance(progression, list) else [progression]
    for progression_index, raw_progression in enumerate(progression_rows):
        if not isinstance(raw_progression, dict):
            continue
        nested_option = raw_progression.get("character_option")
        if not isinstance(nested_option, dict):
            continue
        prefix = (
            f"character_progression[{progression_index}]"
            if isinstance(progression, list)
            else "character_progression"
        )
        groups.append(
            (
                f"{prefix}.character_option.base_rule_refs",
                nested_option.get("base_rule_refs", nested_option.get("baseRuleRefs")),
            )
        )
    return tuple(groups)


def _source_health_reference_from_base_rule_ref(
    raw_ref: dict[str, Any],
) -> SourceHealthReference | None:
    entry_key = str(raw_ref.get("entry_key") or "").strip()
    slug = str(raw_ref.get("slug") or "").strip()
    rule_key = str(raw_ref.get("rule_key") or "").strip()
    if not (entry_key or slug or rule_key):
        return None
    return SourceHealthReference(
        target_kind="systems",
        library_slug=str(raw_ref.get("library_slug") or "").strip(),
        entry_key=entry_key,
        slug=slug,
        rule_key=rule_key,
        source_id=str(raw_ref.get("source_id") or "").strip().upper(),
        system_code=str(raw_ref.get("system_code") or "").strip(),
        consumer_version=str(
            raw_ref.get("source_version") or raw_ref.get("version") or ""
        ).strip(),
        version_scheme=str(raw_ref.get("version_scheme") or "").strip(),
    )


def _normalized_mechanics_base_rule_refs(value: object) -> tuple[dict[str, Any], ...]:
    raw_items = [value] if isinstance(value, dict) else list(value or []) if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    seen: set[SourceHealthReference] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        rows = normalize_campaign_base_rule_refs([raw_item])
        if not rows:
            continue
        row = dict(rows[0])
        systems_ref = dict(raw_item.get("systems_ref") or {}) if isinstance(raw_item.get("systems_ref"), dict) else {}
        for key in ("library_slug", "system_code", "source_version", "version", "version_scheme"):
            value_at_key = raw_item.get(key, systems_ref.get(key))
            if value_at_key not in (None, ""):
                row[key] = value_at_key
        reference = _source_health_reference_from_base_rule_ref(row)
        if reference is None or reference in seen:
            continue
        seen.add(reference)
        normalized.append(row)
    return tuple(normalized)


class CampaignPageStore:
    def __init__(
        self,
        *,
        reload_enabled: bool = True,
        scan_interval_seconds: int = 0,
    ) -> None:
        self.reload_enabled = reload_enabled
        self.scan_interval_seconds = max(scan_interval_seconds, 0)
        self._lock = Lock()
        self._content_fingerprints: dict[str, tuple] = {}
        self._last_check_monotonic: dict[str, float] = {}
        self.mirror_conflicts: dict[str, tuple[str, ...]] = {}

    def sync_campaign_pages(self, campaign_slug: str, content_dir: Path | None) -> None:
        if content_dir is None:
            return

        with self._lock:
            self._sync_campaign_pages_locked(campaign_slug, content_dir)

    def ensure_campaign_seeded(self, campaign_slug: str, content_dir: Path | None) -> None:
        self.sync_campaign_pages(campaign_slug, content_dir)

    def sync_campaign_view(self, campaign_slug: str, content_dir: Path) -> tuple[list[Page], tuple]:
        """Capture finalized page metadata and its exact seed evidence together."""
        with self._lock:
            self._sync_campaign_pages_locked(campaign_slug, content_dir)
            pages = self.list_pages(campaign_slug)
            return pages, self._content_fingerprints[campaign_slug]

    def count_pages(self, campaign_slug: str) -> int:
        from .committed_publication import active, page_rows
        if active():
            return len(page_rows(campaign_slug))
        row = get_db().execute(
            "SELECT COUNT(*) AS count FROM campaign_pages WHERE campaign_slug = ?",
            (campaign_slug,),
        ).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_pages(
        self,
        campaign_slug: str,
        *,
        content_dir: Path | None = None,
    ) -> list[Page]:
        from .committed_publication import active, page_rows, read_snapshot
        if active():
            @read_snapshot
            def committed_pages():
                return sorted([self._map_page(row, include_body=False) for row in page_rows(campaign_slug)], key=page_sort_key)
            return committed_pages()
        if content_dir is not None:
            self._ensure_campaign_pages_current(campaign_slug, content_dir)

        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_pages
            WHERE campaign_slug = ?
            ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
            """,
            (campaign_slug,),
        ).fetchall()
        pages = [self._map_page(row, include_body=False) for row in rows]
        return sorted(pages, key=page_sort_key)

    def list_page_records(
        self,
        campaign_slug: str,
        *,
        content_dir: Path | None = None,
        include_body: bool = False,
    ) -> list[CampaignPageRecord]:
        from .committed_publication import active, page_rows
        if active():
            return sorted([self._map_record(row, include_body=include_body) for row in page_rows(campaign_slug)], key=lambda item: (*page_sort_key(item.page), item.page_ref))
        if content_dir is not None:
            self._ensure_campaign_pages_current(campaign_slug, content_dir)

        if include_body:
            query = """
                SELECT
                    campaign_slug,
                    page_ref,
                    metadata_json,
                    raw_link_targets_json,
                    updated_at,
                    body_markdown
                FROM campaign_pages
                WHERE campaign_slug = ?
                ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
                """
        else:
            query = """
                SELECT
                    campaign_slug,
                    page_ref,
                    metadata_json,
                    raw_link_targets_json,
                    updated_at
                FROM campaign_pages
                WHERE campaign_slug = ?
                ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
                """
        rows = get_db().execute(query, (campaign_slug,)).fetchall()
        records = [self._map_record(row, include_body=include_body) for row in rows]
        return sorted(records, key=lambda item: (*page_sort_key(item.page), item.page_ref))

    def list_source_health_mechanics_consumers(
        self,
        campaign_slug: str,
        *,
        continuation: str = "",
        limit: int = 50,
    ) -> SourceHealthInventoryPage:
        page_limit = min(max(int(limit), 1), 50)
        offset, anchor_digest = _parse_mechanics_source_health_cursor(continuation)
        query_offset = offset - 1 if offset else 0
        query_limit = page_limit + 2 if offset else page_limit + 1
        rows = get_db().execute(
            """
            SELECT page_ref, route_slug, metadata_json, updated_at
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND published = 1
              AND section = 'Mechanics'
            ORDER BY page_ref COLLATE BINARY ASC
            LIMIT ? OFFSET ?
            """,
            (campaign_slug, query_limit, query_offset),
        ).fetchall()
        from .committed_publication import active, page_row, config
        if active():
            _, settings = config(campaign_slug)
            proved = []
            for row in rows:
                try:
                    proof = page_row(campaign_slug, row["page_ref"])
                except ValueError:
                    continue
                if (proof is not None and proof["published"] == 1 and proof["section"] == "Mechanics"
                        and proof["reveal_after_session"] <= int(settings["current_session"])):
                    proved.append(proof)
            rows = proved
        if offset:
            if (
                not rows
                or _mechanics_source_health_anchor_digest(campaign_slug, rows[0])
                != anchor_digest
            ):
                raise SourceHealthCursorError("Mechanics cursor is stale.")
            candidates = rows[1:]
        else:
            candidates = rows
        has_more = len(candidates) > page_limit
        selected = candidates[:page_limit]
        consumers: list[SourceHealthConsumer] = []
        for row in selected:
            page_ref = str(row["page_ref"])
            route_slug = str(row["route_slug"] or page_ref)
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                raise ValueError("Published Mechanics metadata is invalid.") from None
            if not isinstance(metadata, dict):
                raise ValueError("Published Mechanics metadata must be an object.")
            for owner_path, raw_refs in _mechanics_base_rule_ref_groups(metadata):
                for index, raw_ref in enumerate(_normalized_mechanics_base_rule_refs(raw_refs)):
                    reference = _source_health_reference_from_base_rule_ref(raw_ref)
                    if reference is None:
                        continue
                    expected_type = str(raw_ref.get("entry_type") or "").strip().lower()
                    consumers.append(
                        SourceHealthConsumer(
                            consumer_type="mechanics",
                            consumer_key=f"{page_ref}:{owner_path}[{index}]",
                            surface="Mechanics",
                            reference=reference,
                            accepted_target_types=(expected_type,) if expected_type else (),
                            destination=f"/campaigns/{campaign_slug}/pages/{route_slug}",
                        )
                    )
        return SourceHealthInventoryPage(
            consumers=tuple(consumers),
            continuation=(
                "mh1:"
                f"{offset + len(selected)}:"
                f"{_mechanics_source_health_anchor_digest(campaign_slug, selected[-1])}"
                if has_more and selected
                else ""
            ),
        )

    def resolve_source_health_page_targets(
        self,
        campaign_slug: str,
        references: tuple[SourceHealthReference, ...],
    ) -> dict[SourceHealthReference, SourceHealthResolution]:
        page_references = tuple(
            reference
            for reference in references
            if reference.target_kind == "campaign_page" and reference.target_id
        )
        page_refs = sorted({reference.target_id for reference in page_references})
        if not page_refs:
            return {}
        placeholders = ", ".join("?" for _ in page_refs)
        rows = get_db().execute(
            f"""
            SELECT page_ref, route_slug, page_type, published, updated_at
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND page_ref IN ({placeholders})
            ORDER BY page_ref ASC
            """,
            (campaign_slug, *page_refs),
        ).fetchall()
        from .committed_publication import active, page_row, config
        if active():
            _, settings = config(campaign_slug)
            proved = []
            for row in rows:
                try:
                    proof = page_row(campaign_slug, row["page_ref"])
                except ValueError:
                    continue
                if proof is not None and proof["reveal_after_session"] <= int(settings["current_session"]):
                    proved.append(proof)
            rows = proved
        by_page_ref = {str(row["page_ref"]): row for row in rows}
        resolutions: dict[SourceHealthReference, SourceHealthResolution] = {}
        for reference in page_references:
            row = by_page_ref.get(reference.target_id)
            if row is None:
                resolutions[reference] = SourceHealthResolution()
                continue
            target = SourceHealthTarget(
                target_kind="campaign_page",
                canonical_identity=f"page:{campaign_slug}:{reference.target_id}",
                target_type=str(row["page_type"] or "page"),
                enabled=bool(row["published"]),
                accessible=True,
                destination=f"/campaigns/{campaign_slug}/pages/{str(row['route_slug'] or reference.target_id)}",
            )
            resolutions[reference] = SourceHealthResolution(targets=(target,))
        return resolutions

    def get_page_record(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        content_dir: Path | None = None,
        include_body: bool = True,
    ) -> CampaignPageRecord | None:
        from .committed_publication import active, page_row
        if active():
            row = page_row(campaign_slug, self.normalize_page_ref(page_ref))
            return self._map_record(row, include_body=include_body) if row is not None else None
        if content_dir is not None:
            self._ensure_campaign_pages_current(campaign_slug, content_dir)

        normalized_page_ref = self.normalize_page_ref(page_ref)
        if include_body:
            query = """
                SELECT
                    campaign_slug,
                    page_ref,
                    metadata_json,
                    raw_link_targets_json,
                    updated_at,
                    body_markdown
                FROM campaign_pages
                WHERE campaign_slug = ? AND page_ref = ?
                """
        else:
            query = """
                SELECT
                    campaign_slug,
                    page_ref,
                    metadata_json,
                    raw_link_targets_json,
                    updated_at
                FROM campaign_pages
                WHERE campaign_slug = ? AND page_ref = ?
                """
        row = get_db().execute(
            query,
            (campaign_slug, normalized_page_ref),
        ).fetchone()
        if row is None:
            return None
        return self._map_record(row, include_body=include_body)

    def get_page_by_route_slug(
        self,
        campaign_slug: str,
        route_slug: str,
        *,
        include_body: bool = False,
    ) -> Page | None:
        from .committed_publication import active, page_rows, read_snapshot
        if active():
            @read_snapshot
            def committed_route():
                row = next((row for row in page_rows(campaign_slug) if row["route_slug"] == route_slug), None)
                return self._map_page(row, include_body=include_body) if row is not None else None
            return committed_route()
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_pages
            WHERE campaign_slug = ? AND route_slug = ?
            """,
            (campaign_slug, route_slug),
        ).fetchone()
        if row is None:
            return None
        return self._map_page(row, include_body=include_body)

    def get_page_body_markdown(self, campaign_slug: str, route_slug: str) -> str | None:
        from .committed_publication import active
        if active():
            page = self.get_page_by_route_slug(campaign_slug, route_slug, include_body=True)
            return page.body_markdown if page else None
        row = get_db().execute(
            """
            SELECT body_markdown
            FROM campaign_pages
            WHERE campaign_slug = ? AND route_slug = ?
            """,
            (campaign_slug, route_slug),
        ).fetchone()
        if row is None:
            return None
        return str(row["body_markdown"] or "")

    def search_route_slugs(self, campaign_slug: str, query: str) -> list[str]:
        from .committed_publication import active, page_rows
        if active():
            return [row["route_slug"] for row in page_rows(campaign_slug) if query.strip() and query.strip().lower() in row["searchable_text"]]
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        rows = get_db().execute(
            """
            SELECT route_slug
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND searchable_text LIKE ?
            ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
            """,
            (campaign_slug, f"%{normalized_query}%"),
        ).fetchall()
        return [str(row["route_slug"]) for row in rows]

    def search_page_records(
        self,
        campaign_slug: str,
        query: str,
        *,
        limit: int = 30,
        include_body: bool = False,
        current_session: int | None = None,
    ) -> list[CampaignPageRecord]:
        from .committed_publication import active, page_rows, config, read_snapshot
        if active():
            @read_snapshot
            def committed_search():
                _, settings = config(campaign_slug)
                rows = [row for row in page_rows(campaign_slug) if query.strip() and query.strip().lower() in row["searchable_text"]]
                if current_session is not None:
                    rows = [row for row in rows if row["published"] and row["reveal_after_session"] <= int(settings["current_session"])
                            and row["section"].strip().lower() not in DEPRECATED_WIKI_SECTIONS and row["page_type"].strip().lower() not in DEPRECATED_WIKI_PAGE_TYPES]
                return sorted([self._map_record(row, include_body=include_body) for row in rows], key=lambda record: page_sort_key(record.page))[:max(1, limit)]
            return committed_search()
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        connection = get_db()
        # SQLite's built-in LOWER only folds ASCII. Use the owning Python sort
        # semantics on scalar metadata; Page/body hydration remains after LIMIT.
        connection.create_function("cpw_page_lower", 1, lambda value: str(value or "").lower(), deterministic=True)
        connection.create_function("cpw_page_strip_lower", 1, lambda value: str(value or "").strip().lower(), deterministic=True)
        connection.create_function("cpw_page_section_rank", 1, lambda value: section_sort_key(str(value or ""))[0], deterministic=True)
        connection.create_function("cpw_page_subsection_rank", 2, lambda section, subsection: subsection_sort_key(str(section or ""), str(subsection or ""))[0], deterministic=True)
        columns = "campaign_slug, page_ref, metadata_json, raw_link_targets_json, updated_at"
        if include_body:
            columns += ", body_markdown"
        parameters: list[Any] = [campaign_slug, f"%{normalized_query}%"]
        visibility_clause = ""
        if current_session is not None:
            section_placeholders = ", ".join("?" for _ in DEPRECATED_WIKI_SECTIONS)
            type_placeholders = ", ".join("?" for _ in DEPRECATED_WIKI_PAGE_TYPES)
            visibility_clause = f"""
                AND published = 1 AND reveal_after_session <= ?
                AND cpw_page_strip_lower(section) NOT IN ({section_placeholders})
                AND cpw_page_strip_lower(page_type) NOT IN ({type_placeholders})
            """
            parameters.extend([int(current_session), *sorted(DEPRECATED_WIKI_SECTIONS), *sorted(DEPRECATED_WIKI_PAGE_TYPES)])
        parameters.append(max(1, limit))
        rows = connection.execute(
            f"""
            SELECT {columns}
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND searchable_text LIKE ?
              {visibility_clause}
            ORDER BY cpw_page_section_rank(section), cpw_page_lower(section),
                     cpw_page_subsection_rank(section, subsection), cpw_page_strip_lower(subsection),
                     display_order,
                     CASE WHEN section = 'Sessions' AND page_type = 'session'
                               AND reveal_after_session > 0 THEN reveal_after_session ELSE 10000 END,
                     cpw_page_lower(title), page_ref
            LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
        return [self._map_record(row, include_body=include_body) for row in rows]

    def upsert_page(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        metadata: dict[str, Any],
        body_markdown: str,
        commit: bool = True,
    ) -> CampaignPageRecord:
        from .committed_publication import active, CommittedSourceConflict
        if active():
            raise CommittedSourceConflict("Use committed publication; direct row or filesystem ingestion is blocked.")
        if not isinstance(metadata, dict):
            raise ValueError("Page metadata must be an object.")
        if not isinstance(body_markdown, str):
            raise ValueError("body_markdown must be a string.")

        connection = get_db()
        try:
            self._reserve_page_write(connection)
            # The preflight used by file writers is advisory; check route
            # occupancy again after acquiring the SQLite write reservation.
            payload = self.validate_page_upsert(
                campaign_slug,
                page_ref,
                metadata=metadata,
                body_markdown=body_markdown,
            )
            self._persist_page_payload(campaign_slug, payload)
            record = self.get_page_record(campaign_slug, payload["page_ref"], include_body=True)
            if record is None:
                raise RuntimeError("Failed to persist campaign page.")
            if commit:
                connection.commit()
            return record
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _reserve_page_write(connection) -> None:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        else:
            # Reconciliation already owns BEGIN IMMEDIATE. An outer deferred
            # transaction must upgrade before reading the row or high-water;
            # a stale WAL snapshot fails with SQLITE_BUSY_SNAPSHOT here.
            connection.execute(
                "UPDATE campaign_page_sync_state SET seeded_at = seeded_at WHERE 0"
            )

    @staticmethod
    def _revision_datetime(value: str) -> datetime:
        revision = datetime.fromisoformat(value)
        if revision.tzinfo is None or revision.utcoffset() is None:
            raise ValueError("Campaign page revision must include a timezone.")
        return revision.astimezone(timezone.utc)

    def _advance_page_revision(self, campaign_slug: str, prior_revision: str | None = None) -> str:
        """Allocate and persist one campaign revision inside the writer transaction."""
        connection = get_db()
        marker = connection.execute(
            "SELECT seeded_at FROM campaign_page_sync_state WHERE campaign_slug = ?",
            (campaign_slug,),
        ).fetchone()
        floor = utcnow()
        if marker is not None:
            floor = max(floor, self._revision_datetime(str(marker["seeded_at"])))
        if prior_revision is not None:
            floor = max(floor, self._revision_datetime(prior_revision))
        revision = floor + timedelta(microseconds=1)
        if revision.microsecond == 0:
            # C8 page revisions used whole seconds. Even if a deleted
            # legacy row outlived its old marker, it cannot equal this value.
            revision += timedelta(microseconds=1)
        value = revision.isoformat(timespec="microseconds")
        connection.execute(
            """
            INSERT INTO campaign_page_sync_state (campaign_slug, seeded_at)
            VALUES (?, ?)
            ON CONFLICT(campaign_slug) DO UPDATE SET seeded_at = excluded.seeded_at
            """,
            (campaign_slug, value),
        )
        return value

    def _persist_page_payload(self, campaign_slug: str, payload: dict[str, Any]) -> None:
        """Persist an already normalized payload without parsing or collision queries."""
        connection = get_db()
        from .committed_publication import active, _projection_payload, CommittedSourceConflict
        if active() and (not connection.in_transaction or
                         _projection_payload.get() != (campaign_slug, tuple(sorted(payload.items())))):
            raise CommittedSourceConflict("Page projection requires the committed publication reservation.")
        existing = connection.execute(
            """
            SELECT created_at, updated_at
            FROM campaign_pages
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (campaign_slug, payload["page_ref"]),
        ).fetchone()
        payload["updated_at"] = self._advance_page_revision(
            campaign_slug,
            str(existing["updated_at"]) if existing is not None else None,
        )
        created_at = str(existing["created_at"]) if existing is not None else payload["updated_at"]

        connection.execute(
            """
            INSERT INTO campaign_pages (
                campaign_slug,
                page_ref,
                route_slug,
                title,
                section,
                subsection,
                page_type,
                display_order,
                published,
                aliases_json,
                summary,
                image_path,
                image_alt,
                image_caption,
                reveal_after_session,
                source_ref,
                metadata_json,
                raw_link_targets_json,
                searchable_text,
                body_markdown,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug, page_ref) DO UPDATE SET
                route_slug = excluded.route_slug,
                title = excluded.title,
                section = excluded.section,
                subsection = excluded.subsection,
                page_type = excluded.page_type,
                display_order = excluded.display_order,
                published = excluded.published,
                aliases_json = excluded.aliases_json,
                summary = excluded.summary,
                image_path = excluded.image_path,
                image_alt = excluded.image_alt,
                image_caption = excluded.image_caption,
                reveal_after_session = excluded.reveal_after_session,
                source_ref = excluded.source_ref,
                metadata_json = excluded.metadata_json,
                raw_link_targets_json = excluded.raw_link_targets_json,
                searchable_text = excluded.searchable_text,
                body_markdown = excluded.body_markdown,
                updated_at = excluded.updated_at
            """,
            (
                campaign_slug,
                payload["page_ref"],
                payload["route_slug"],
                payload["title"],
                payload["section"],
                payload["subsection"],
                payload["page_type"],
                payload["display_order"],
                payload["published"],
                payload["aliases_json"],
                payload["summary"],
                payload["image_path"],
                payload["image_alt"],
                payload["image_caption"],
                payload["reveal_after_session"],
                payload["source_ref"],
                payload["metadata_json"],
                payload["raw_link_targets_json"],
                payload["searchable_text"],
                payload["body_markdown"],
                created_at,
                payload["updated_at"],
            ),
        )

    def validate_page_upsert(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        metadata: dict[str, Any],
        body_markdown: str,
    ) -> dict[str, Any]:
        """Build and validate a page row without mutating SQLite."""

        if not isinstance(metadata, dict):
            raise ValueError("Page metadata must be an object.")
        if not isinstance(body_markdown, str):
            raise ValueError("body_markdown must be a string.")

        payload = self._build_page_payload(
            campaign_slug,
            page_ref,
            metadata=metadata,
            body_markdown=body_markdown,
        )
        connection = get_db()
        duplicate = connection.execute(
            """
            SELECT page_ref
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND route_slug = ?
              AND page_ref <> ?
            """,
            (campaign_slug, payload["route_slug"], payload["page_ref"]),
        ).fetchone()
        if duplicate is not None:
            raise ValueError("That wiki page slug is already in use. Choose a different slug.")

        return payload

    def delete_page(self, campaign_slug: str, page_ref: str, *, commit: bool = True) -> CampaignPageRecord | None:
        from .committed_publication import active, CommittedSourceConflict
        if active():
            raise CommittedSourceConflict("Use committed publication; direct row or filesystem ingestion is blocked.")
        connection = get_db()
        owned_transaction = not connection.in_transaction
        try:
            self._reserve_page_write(connection)
            existing = self.get_page_record(campaign_slug, page_ref, include_body=True)
            if existing is None:
                if owned_transaction:
                    connection.rollback()
                return None
            # Preserve the deleted revision in durable campaign history before
            # removing the row, so same-ref recreation cannot replay a witness.
            self._advance_page_revision(campaign_slug, existing.updated_at)
            deleted = connection.execute(
                """
                DELETE FROM campaign_pages
                WHERE campaign_slug = ? AND page_ref = ?
                """,
                (campaign_slug, existing.page_ref),
            )
            if deleted.rowcount != 1:
                raise RuntimeError("Campaign page deletion lost its reserved row.")
            if commit:
                connection.commit()
            return existing
        except BaseException:
            connection.rollback()
            raise

    normalize_page_ref = staticmethod(normalize_page_ref)

    def _has_sync_state(self, campaign_slug: str) -> bool:
        row = get_db().execute(
            """
            SELECT 1
            FROM campaign_page_sync_state
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _require_refresh_admission() -> None:
        if get_db().in_transaction:
            raise CampaignRefreshTransactionError("Campaign refresh requires a connection without an active transaction.")

    def _ensure_campaign_pages_current(self, campaign_slug: str, content_dir: Path) -> None:
        from .committed_publication import active, inspect_page_mirrors, config
        if active():
            from flask import current_app
            _, settings = config(campaign_slug)
            asset_root = Path(current_app.config["CAMPAIGNS_DIR"]) / campaign_slug / settings.get("asset_dir", "assets")
            self.mirror_conflicts[campaign_slug] = inspect_page_mirrors(campaign_slug, content_dir, asset_root)
            return
        with self._lock:
            if not self._has_sync_state(campaign_slug):
                self._sync_campaign_pages_locked(campaign_slug, content_dir)
                return
            if not self.reload_enabled:
                return
            now = time.monotonic()
            if now - self._last_check_monotonic.get(campaign_slug, 0.0) < self.scan_interval_seconds:
                return
            fingerprint = self._campaign_freshness_token(campaign_slug, content_dir)
            if self._content_fingerprints.get(campaign_slug) != fingerprint:
                self._sync_campaign_pages_locked(campaign_slug, content_dir)
            else:
                self._last_check_monotonic[campaign_slug] = now

    @staticmethod
    def _row_snapshot(campaign_slug: str):
        return get_db().execute(
            "SELECT * FROM campaign_pages WHERE campaign_slug = ? ORDER BY page_ref",
            (campaign_slug,),
        ).fetchall()

    @staticmethod
    def _sync_snapshot(campaign_slug: str):
        row = get_db().execute(
            "SELECT * FROM campaign_page_sync_state WHERE campaign_slug = ?", (campaign_slug,),
        ).fetchone()
        return tuple(sorted(dict(row).items())) if row is not None else None

    @staticmethod
    def protection_identity(campaign_slug: str) -> tuple[tuple[str, ...], ...]:
        # Explicit non-payload projections: refresh never fetches recovery BLOBs.
        rows = get_db().execute(
            """
            SELECT 'publication' AS journal, operation_id, campaign_slug, page_ref, state, updated_at
            FROM player_wiki_reconciliation_operations
            WHERE campaign_slug = ? AND state IN ('prepared', 'repository_pending', 'conflict')
            UNION ALL
            SELECT 'deletion' AS journal, operation_id, campaign_slug, page_ref, state, updated_at
            FROM player_wiki_deletion_operations
            WHERE campaign_slug = ? AND state IN ('prepared', 'repository_pending', 'conflict')
            ORDER BY journal, operation_id, page_ref
            """, (campaign_slug, campaign_slug),
        ).fetchall()
        return tuple(tuple(str(row[key]) for key in ("journal", "operation_id", "campaign_slug", "page_ref", "state", "updated_at")) for row in rows)

    def _campaign_freshness_token(self, campaign_slug: str, content_dir: Path) -> tuple:
        snapshot = discover_source_snapshot(content_dir)
        return snapshot.witnesses, self.protection_identity(campaign_slug)

    def _prepare_campaign_refresh_locked(self, campaign_slug: str, content_dir: Path):
        self._require_refresh_admission()
        rows = self._row_snapshot(campaign_slug)
        sync_identity = self._sync_snapshot(campaign_slug)
        protection = self.protection_identity(campaign_slug)
        source = capture_source_snapshot(content_dir, protected_page_refs=(row[3] for row in protection))
        plan = plan_campaign_refresh(campaign_slug, source, rows, protection)
        validate_witnesses(source.witnesses)  # Bracket parsing without giving the pure plan filesystem work.
        return replace(plan, sync_identity=sync_identity)

    def _sync_campaign_pages_locked(self, campaign_slug: str, content_dir: Path) -> None:
        from .committed_publication import active, inspect_page_mirrors, config
        if active():
            from flask import current_app
            _, settings = config(campaign_slug)
            asset_root = Path(current_app.config["CAMPAIGNS_DIR"]) / campaign_slug / settings.get("asset_dir", "assets")
            self.mirror_conflicts[campaign_slug] = inspect_page_mirrors(campaign_slug, content_dir, asset_root)
            self._content_fingerprints[campaign_slug] = ((), ())
            return
        plan = self._prepare_campaign_refresh_locked(campaign_slug, content_dir)
        self._apply_campaign_refresh_locked(plan)

    def _apply_campaign_refresh_locked(self, plan) -> None:
        from .committed_publication import active, CommittedSourceConflict
        if active():
            raise CommittedSourceConflict("Use committed publication; direct row or filesystem ingestion is blocked.")
        self._require_refresh_admission()  # Outside rollback/commit ownership.
        connection = get_db()
        # sqlite's connection context rolls back owned DML and failed commits,
        # preserving exception chaining if rollback itself fails.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = self._row_snapshot(plan.campaign_slug)
            if row_identity(rows) != plan.rows:
                raise StaleCampaignRefreshPlan("rows")
            if self._sync_snapshot(plan.campaign_slug) != plan.sync_identity:
                raise StaleCampaignRefreshPlan("sync")
            protection = self.protection_identity(plan.campaign_slug)
            if protection != plan.protection:
                raise StaleCampaignRefreshPlan("protection")
            validate_witnesses(plan.source.witnesses)
            payloads = tuple(dict(payload) for payload in plan.payloads)
            changes, deletions = diff_page_payloads(
                payloads, rows, plan.source.discovered_refs, (row[3] for row in protection),
            )
            changed_refs = frozenset(changes)
            for payload in payloads:
                if payload["page_ref"] in changed_refs:
                    self._persist_page_payload(plan.campaign_slug, payload)
            rows_by_ref = {str(row["page_ref"]): row for row in rows}
            for page_ref in deletions:
                prior = rows_by_ref[page_ref]
                self._advance_page_revision(plan.campaign_slug, str(prior["updated_at"]))
                deleted = connection.execute(
                    "DELETE FROM campaign_pages WHERE campaign_slug = ? AND page_ref = ?",
                    (plan.campaign_slug, page_ref),
                )
                if deleted.rowcount != 1:
                    raise StaleCampaignRefreshPlan("rows")
            self._mark_sync_state(plan.campaign_slug)
        # Publish only consumed observations, never a fresh post-write scan.
        self._content_fingerprints[plan.campaign_slug] = (plan.source.witnesses, plan.protection)
        self._last_check_monotonic[plan.campaign_slug] = time.monotonic()

    @staticmethod
    def _list_reconciliation_protected_page_refs(campaign_slug: str) -> set[str]:
        return {row[3] for row in CampaignPageStore.protection_identity(campaign_slug)}

    def _mark_sync_state(self, campaign_slug: str) -> None:
        get_db().execute(
            """
            INSERT INTO campaign_page_sync_state (campaign_slug, seeded_at)
            VALUES (?, ?)
            ON CONFLICT(campaign_slug) DO NOTHING
            """,
            (campaign_slug, utcnow().isoformat(timespec="microseconds")),
        )

    def _build_page_payload(
        self, campaign_slug: str, page_ref: str, *, metadata: dict[str, Any], body_markdown: str,
    ) -> dict[str, Any]:
        return build_page_payload(campaign_slug, page_ref, metadata=metadata,
                                  body_markdown=body_markdown, updated_at=isoformat(utcnow()))

    def _map_page(self, row, *, include_body: bool) -> Page:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        page = self._map_page_from_decoded_metadata(
            row,
            include_body=include_body,
            metadata=metadata,
        )
        from .committed_publication import active, current
        if active():
            source = current(str(row["campaign_slug"]), "page", str(row["page_ref"]))
            settings = current(str(row["campaign_slug"]), "config")
            if source is None or settings is None:
                raise ValueError("Committed page identity is unavailable.")
            page.committed_revision = int(source["revision"])
            page.committed_config_revision = int(settings["revision"])
        return page

    def _map_page_from_decoded_metadata(
        self,
        row,
        *,
        include_body: bool,
        metadata: dict[str, Any],
    ) -> Page:
        raw_link_targets = json.loads(str(row["raw_link_targets_json"] or "[]"))
        body_markdown = str(row["body_markdown"] or "") if include_body else ""
        return build_page_from_content(
            source_path=f"db://{row['campaign_slug']}/{row['page_ref']}",
            default_slug=str(row["page_ref"]),
            metadata=metadata,
            body_markdown=body_markdown,
            raw_link_targets=raw_link_targets,
            content_loaded=include_body,
        )

    def _map_record(self, row, *, include_body: bool) -> CampaignPageRecord:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        body_markdown = str(row["body_markdown"] or "") if include_body else ""
        return CampaignPageRecord(
            campaign_slug=str(row["campaign_slug"]),
            page_ref=str(row["page_ref"]),
            relative_path=f"{row['page_ref']}.md",
            metadata=metadata,
            body_markdown=body_markdown,
            page=self._map_page_from_decoded_metadata(
                row,
                include_body=include_body,
                metadata=metadata,
            ),
            updated_at=str(row["updated_at"]),
        )
