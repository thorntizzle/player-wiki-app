from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .auth_store import isoformat, utcnow
from .db import get_db
from .models import Page, page_sort_key
from .repository import build_page_from_content, extract_obsidian_targets, parse_frontmatter


@dataclass(slots=True)
class CampaignPageRecord:
    campaign_slug: str
    page_ref: str
    relative_path: str
    metadata: dict[str, Any]
    body_markdown: str
    page: Page
    updated_at: str


class CampaignPageStore:
    def sync_campaign_pages(self, campaign_slug: str, content_dir: Path | None) -> None:
        if content_dir is None:
            return

        connection = get_db()
        try:
            existing_page_refs = self._list_existing_page_refs(campaign_slug)
            discovered_page_refs: set[str] = set()
            if content_dir is not None and content_dir.exists():
                for file_path in sorted(content_dir.rglob("*.md")):
                    raw_text = file_path.read_text(encoding="utf-8")
                    metadata, body_markdown = parse_frontmatter(raw_text)
                    page_ref = file_path.relative_to(content_dir).with_suffix("").as_posix()
                    discovered_page_refs.add(page_ref)
                    self.upsert_page(
                        campaign_slug,
                        page_ref,
                        metadata=metadata,
                        body_markdown=body_markdown.strip(),
                        commit=False,
                    )

                for page_ref in sorted(existing_page_refs - discovered_page_refs):
                    self.delete_page(campaign_slug, page_ref, commit=False)

            self._mark_sync_state(campaign_slug)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

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
            self.sync_campaign_pages(campaign_slug, content_dir)

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
            self.sync_campaign_pages(campaign_slug, content_dir)

        rows = get_db().execute(
            """
            SELECT *
            FROM campaign_pages
            WHERE campaign_slug = ?
            ORDER BY section ASC, subsection ASC, display_order ASC, title ASC, page_ref ASC
            """,
            (campaign_slug,),
        ).fetchall()
        records = [self._map_record(row, include_body=include_body) for row in rows]
        return sorted(records, key=lambda item: (*page_sort_key(item.page), item.page_ref))

    def get_page_record(
        self,
        campaign_slug: str,
        page_ref: str,
        *,
        content_dir: Path | None = None,
        include_body: bool = True,
    ) -> CampaignPageRecord | None:
        if content_dir is not None:
            self.sync_campaign_pages(campaign_slug, content_dir)

        normalized_page_ref = self.normalize_page_ref(page_ref)
        row = get_db().execute(
            """
            SELECT *
            FROM campaign_pages
            WHERE campaign_slug = ? AND page_ref = ?
            """,
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
        payload = self._build_page_payload(
            campaign_slug,
            page_ref,
            metadata=metadata,
            body_markdown=body_markdown,
        )
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
            page=self._map_page(row, include_body=include_body),
            updated_at=str(row["updated_at"]),
        )
