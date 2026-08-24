from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Any

from .auth_store import isoformat, utcnow
from .character_campaign_options import normalize_campaign_base_rule_refs
from .db import get_db
from .models import Page, page_sort_key
from .repository import build_page_from_content, extract_obsidian_targets, parse_frontmatter
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
        self._content_fingerprints: dict[str, str] = {}
        self._last_check_monotonic: dict[str, float] = {}

    def sync_campaign_pages(self, campaign_slug: str, content_dir: Path | None) -> None:
        if content_dir is None:
            return

        with self._lock:
            self._sync_campaign_pages_locked(campaign_slug, content_dir)

    def ensure_campaign_seeded(self, campaign_slug: str, content_dir: Path | None) -> None:
        self.sync_campaign_pages(campaign_slug, content_dir)

    def count_pages(self, campaign_slug: str) -> int:
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
    ) -> list[CampaignPageRecord]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND searchable_text LIKE ?
            ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
            LIMIT ?
            """,
            (campaign_slug, f"%{normalized_query}%", max(1, limit)),
        ).fetchall()
        records = [self._map_record(row, include_body=include_body) for row in rows]
        return sorted(records, key=lambda item: (*page_sort_key(item.page), item.page_ref))

    def upsert_page(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        metadata: dict[str, Any],
        body_markdown: str,
        commit: bool = True,
    ) -> CampaignPageRecord:
        if not isinstance(metadata, dict):
            raise ValueError("Page metadata must be an object.")
        if not isinstance(body_markdown, str):
            raise ValueError("body_markdown must be a string.")

        connection = get_db()
        payload = self.validate_page_upsert(
            campaign_slug,
            page_ref,
            metadata=metadata,
            body_markdown=body_markdown,
        )

        existing = connection.execute(
            """
            SELECT created_at
            FROM campaign_pages
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (campaign_slug, payload["page_ref"]),
        ).fetchone()
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
        self._mark_sync_state(campaign_slug)
        if commit:
            connection.commit()

        record = self.get_page_record(campaign_slug, payload["page_ref"], include_body=True)
        if record is None:
            raise RuntimeError("Failed to persist campaign page.")
        return record

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
        existing = self.get_page_record(campaign_slug, page_ref, include_body=True)
        if existing is None:
            return None

        connection = get_db()
        connection.execute(
            """
            DELETE FROM campaign_pages
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (campaign_slug, existing.page_ref),
        )
        self._mark_sync_state(campaign_slug)
        if commit:
            connection.commit()
        return existing

    @staticmethod
    def normalize_page_ref(page_ref: str) -> str:
        normalized = str(page_ref or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            raise ValueError("A relative page reference is required.")

        pure_path = PurePosixPath(normalized)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise ValueError("Relative page references must stay within the campaign content tree.")
        if pure_path.suffix and pure_path.suffix.lower() != ".md":
            raise ValueError("Only .md pages are supported.")
        if pure_path.suffix.lower() == ".md":
            pure_path = pure_path.with_suffix("")
        return pure_path.as_posix()

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

    def _ensure_campaign_pages_current(self, campaign_slug: str, content_dir: Path) -> None:
        with self._lock:
            if not self._has_sync_state(campaign_slug):
                self._sync_campaign_pages_locked(campaign_slug, content_dir)
                return
            if not self.reload_enabled:
                return

            now = time.monotonic()
            last_check = self._last_check_monotonic.get(campaign_slug, 0.0)
            if now - last_check < self.scan_interval_seconds:
                return

            self._last_check_monotonic[campaign_slug] = now
            fingerprint = self._build_content_fingerprint(content_dir)
            if self._content_fingerprints.get(campaign_slug) != fingerprint:
                self._sync_campaign_pages_locked(campaign_slug, content_dir)

    def _sync_campaign_pages_locked(self, campaign_slug: str, content_dir: Path) -> None:
        connection = get_db()
        try:
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            existing_page_refs = self._list_existing_page_refs(campaign_slug)
            protected_page_refs = self._list_reconciliation_protected_page_refs(
                campaign_slug
            )
            discovered_page_refs: set[str] = set()
            if content_dir.exists():
                for file_path in sorted(content_dir.rglob("*.md")):
                    page_ref = file_path.relative_to(content_dir).with_suffix("").as_posix()
                    discovered_page_refs.add(page_ref)
                    if page_ref in protected_page_refs:
                        continue
                    raw_text = file_path.read_text(encoding="utf-8")
                    metadata, body_markdown = parse_frontmatter(raw_text)
                    self.upsert_page(
                        campaign_slug,
                        page_ref,
                        metadata=metadata,
                        body_markdown=body_markdown.strip(),
                        commit=False,
                    )

            for page_ref in sorted(existing_page_refs - discovered_page_refs):
                if page_ref in protected_page_refs:
                    continue
                self.delete_page(campaign_slug, page_ref, commit=False)

            self._mark_sync_state(campaign_slug)
            connection.commit()
            self._content_fingerprints[campaign_slug] = self._build_content_fingerprint(content_dir)
            self._last_check_monotonic[campaign_slug] = time.monotonic()
        except Exception:
            connection.rollback()
            raise

    def _list_existing_page_refs(self, campaign_slug: str) -> set[str]:
        rows = get_db().execute(
            """
            SELECT page_ref
            FROM campaign_pages
            WHERE campaign_slug = ?
            """,
            (campaign_slug,),
        ).fetchall()
        return {str(row["page_ref"]) for row in rows}

    @staticmethod
    def _list_reconciliation_protected_page_refs(campaign_slug: str) -> set[str]:
        rows = get_db().execute(
            """
            SELECT page_ref
            FROM player_wiki_reconciliation_operations
            WHERE campaign_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            UNION
            SELECT page_ref
            FROM player_wiki_deletion_operations
            WHERE campaign_slug = ?
              AND state IN ('prepared', 'repository_pending', 'conflict')
            """,
            (campaign_slug, campaign_slug),
        ).fetchall()
        return {str(row["page_ref"]) for row in rows}

    def _mark_sync_state(self, campaign_slug: str) -> None:
        get_db().execute(
            """
            INSERT INTO campaign_page_sync_state (
                campaign_slug,
                seeded_at
            )
            VALUES (?, ?)
            ON CONFLICT(campaign_slug) DO UPDATE SET
                seeded_at = excluded.seeded_at
            """,
            (campaign_slug, isoformat(utcnow())),
        )

    def _build_content_fingerprint(self, content_dir: Path) -> str:
        hasher = hashlib.sha1()
        file_count = 0
        if content_dir.exists():
            for file_path in sorted(content_dir.rglob("*.md")):
                stat = file_path.stat()
                relative_path = file_path.relative_to(content_dir).as_posix()
                hasher.update(relative_path.encode("utf-8"))
                hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
                hasher.update(str(stat.st_size).encode("utf-8"))
                file_count += 1
        return f"{file_count}:{hasher.hexdigest()}"

    def _build_page_payload(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        metadata: dict[str, Any],
        body_markdown: str,
    ) -> dict[str, Any]:
        normalized_page_ref = self.normalize_page_ref(page_ref)
        normalized_metadata = dict(metadata)
        normalized_body = body_markdown.strip()
        page = build_page_from_content(
            source_path=f"db://{campaign_slug}/{normalized_page_ref}",
            default_slug=normalized_page_ref,
            metadata=normalized_metadata,
            body_markdown=normalized_body,
            raw_link_targets=extract_obsidian_targets(normalized_body),
            content_loaded=True,
        )
        searchable_text = " ".join(
            part
            for part in (
                page.title,
                page.subsection,
                page.summary,
                normalized_body,
                " ".join(page.aliases),
            )
            if part
        ).lower()
        return {
            "page_ref": normalized_page_ref,
            "route_slug": page.route_slug,
            "title": page.title,
            "section": page.section,
            "subsection": page.subsection,
            "page_type": page.page_type,
            "display_order": page.display_order,
            "published": int(page.published),
            "aliases_json": json.dumps(list(page.aliases), sort_keys=True),
            "summary": page.summary,
            "image_path": page.image_path,
            "image_alt": page.image_alt,
            "image_caption": page.image_caption,
            "reveal_after_session": page.reveal_after_session,
            "source_ref": page.source_ref,
            "metadata_json": json.dumps(normalized_metadata, sort_keys=True),
            "raw_link_targets_json": json.dumps(list(page.raw_link_targets), sort_keys=True),
            "searchable_text": searchable_text,
            "body_markdown": normalized_body,
            "updated_at": isoformat(utcnow()),
        }

    def _map_page(self, row, *, include_body: bool) -> Page:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        return self._map_page_from_decoded_metadata(
            row,
            include_body=include_body,
            metadata=metadata,
        )

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
