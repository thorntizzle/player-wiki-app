"""Exact, read-only proof for one operator-marked deprecated page.

The marker is a sealed custody claim, never an admission or a publication.
Callers supply a pinned SQLite connection and a scanned file inventory; this
module neither discovers candidates nor writes the marker.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Mapping

import yaml

from .campaign_page_refresh import build_page_payload, normalize_page_ref
from .models import is_deprecated_wiki_identity
from .repository import parse_frontmatter


_MARKER = re.compile(r"legacy_excluded:[0-9a-f]{64}\Z")
_CAMPAIGN_SLUG = re.compile(r"[a-z0-9-]{1,128}\Z")
_DOMAIN = b"cpw:excluded-legacy-page:v1\x00"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024


def is_exclusion_claim(reason: object) -> bool:
    return isinstance(reason, str) and reason.startswith("legacy_excluded:")


def has_exclusion_claim(connection: sqlite3.Connection, campaign_slug: str,
                        page_ref: str) -> bool:
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' "
        "AND name='committed_source_admission'"
    ).fetchone() is None:
        return False
    row = connection.execute(
        "SELECT reason_code FROM committed_source_admission WHERE campaign_slug=? "
        "AND object_kind='page' AND object_ref=?", (campaign_slug, page_ref),
    ).fetchone()
    return row is not None and is_exclusion_claim(row[0])


def _row_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def marker_digest(campaign_slug: str, page_ref: str, file_sha256: str,
                  row: sqlite3.Row) -> str:
    """Bind the normalized key, exact source SHA, and every row/route column."""
    payload = {
        "campaign_slug": campaign_slug,
        "object_kind": "page",
        "object_ref": page_ref,
        "source_sha256": file_sha256,
        "campaign_pages": sorted(_row_dict(row).items()),
    }
    return hashlib.sha256(_DOMAIN + json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def proved_exclusions(connection: sqlite3.Connection,
                      files: Mapping[str, tuple[int, str]], *,
                      source_files: Mapping[str, Path] | None = None,
                      visible_campaigns: set[str] | None = None,
                      ) -> dict[tuple[str, str, str], dict[str, str]]:
    """Return only the unique, exact claim. Invalid claims retain ordinary blockers."""
    claims = connection.execute(
        "SELECT * FROM committed_source_admission WHERE object_kind='page' "
        "AND reason_code LIKE 'legacy_excluded:%' ORDER BY campaign_slug,object_ref"
    ).fetchall()
    if len(claims) != 1:
        return {}
    claim = claims[0]
    slug, ref, reason = claim["campaign_slug"], claim["object_ref"], claim["reason_code"]
    if visible_campaigns is not None and slug not in visible_campaigns:
        return {}
    if (claim["status"] != "blocked" or claim["revision"] is not None
            or not isinstance(reason, str) or not _MARKER.fullmatch(reason)
            or not isinstance(slug, str) or not _CAMPAIGN_SLUG.fullmatch(slug)
            or ref != "index" or normalize_page_ref(ref) != ref):
        return {}
    row = connection.execute(
        "SELECT * FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",
        (slug, ref),
    ).fetchone()
    if (row is None or row["campaign_slug"] != slug or row["page_ref"] != ref
            or row["route_slug"] != "index"
            or not isinstance(row["section"], str)
            or not isinstance(row["page_type"], str)
            or not is_deprecated_wiki_identity(row["section"], row["page_type"])
            or row["published"] not in (0, 1)
            or type(row["reveal_after_session"]) is not int
            or row["reveal_after_session"] < 0):
        return {}
    config = connection.execute(
        "SELECT primary_bytes FROM committed_source_current c JOIN committed_source_generations g "
        "USING(campaign_slug,object_kind,object_ref,revision) JOIN committed_source_admission a "
        "USING(campaign_slug,object_kind,object_ref) WHERE c.campaign_slug=? "
        "AND c.object_kind='config' AND c.object_ref='' AND a.status='admitted' "
        "AND a.revision=c.revision AND g.tombstone=0", (slug,),
    ).fetchone()
    if config is None:
        return {}
    try:
        settings = yaml.safe_load(config[0].decode("utf-8"))
        content_dir = settings.get("player_content_dir", "content")
        if not isinstance(content_dir, str) or not content_dir or "\\" in content_dir or any(
            part in ("", ".", "..") for part in content_dir.split("/")
        ) or content_dir.startswith("/") or ":" in content_dir:
            return {}
        path = f"{slug}/{content_dir}/index.md"
        file_record = files.get(path)
        if (file_record is None or type(file_record[0]) is not int
                or not 0 < file_record[0] <= _MAX_SOURCE_BYTES
                or not isinstance(file_record[1], str)
                or not re.fullmatch(r"[0-9a-f]{64}", file_record[1])):
            return {}
        # The scanned file map proves a regular, unlinked source in the caller.
        source = connection.execute("SELECT 1 FROM committed_source_current WHERE "
                                    "campaign_slug=? AND object_kind='page' AND object_ref=?",
                                    (slug, ref)).fetchone()
        if source is not None:
            return {}
        for table in ("committed_source_generations", "committed_source_admission_receipts",
                      "committed_source_publications", "committed_source_outbox",
                      "committed_source_mirrors"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE campaign_slug=? AND object_kind='page' "
                "AND object_ref=? LIMIT 1", (slug, ref),
            ).fetchone():
                return {}
        for table in ("player_wiki_reconciliation_operations", "player_wiki_deletion_operations"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE campaign_slug=? AND page_ref=? LIMIT 1",
                (slug, ref),
            ).fetchone():
                return {}
        if source_files is not None:
            source_path = source_files.get(path)
            if source_path is None or source_path.is_symlink() or not source_path.is_file():
                return {}
            source_bytes = source_path.read_bytes()
            if (len(source_bytes) != file_record[0]
                    or hashlib.sha256(source_bytes).hexdigest() != file_record[1]):
                return {}
            metadata, body = parse_frontmatter(source_bytes.decode("utf-8"))
            if not isinstance(metadata, dict) or not metadata:
                return {}
            projected = build_page_payload(
                slug, ref, metadata=metadata, body_markdown=body,
                updated_at=row["updated_at"],
            )
            if any(row[key] != value for key, value in projected.items()):
                return {}
        if reason != "legacy_excluded:" + marker_digest(slug, ref, file_record[1], row):
            return {}
    except (AttributeError, TypeError, ValueError, UnicodeError, OSError,
            yaml.YAMLError, sqlite3.Error):
        return {}
    return {(slug, "page", ref): {"path": path, "sha256": file_record[1],
                                  "marker": reason}}
