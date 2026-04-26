from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from .repository import slugify

XIANXIA_HOMEBREW_SOURCE_ID = "XIANXIA-HOMEBREW"
XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY = "curated_seed_data"
XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH = "player_wiki/data/xianxia_systems_seed.json"
_XIANXIA_SYSTEMS_SEED_DATA_PATH = Path(__file__).resolve().parent / "data" / "xianxia_systems_seed.json"


@lru_cache(maxsize=1)
def _load_xianxia_systems_seed_payload() -> dict[str, Any]:
    payload = json.loads(_XIANXIA_SYSTEMS_SEED_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Xianxia Systems seed payload must be a JSON object.")

    source_id = str(payload.get("source_id") or "").strip()
    source_title = str(payload.get("source_title") or "").strip()
    version = str(payload.get("version") or "").strip()
    storage_strategy = str(payload.get("storage_strategy") or "").strip()
    raw_entries = payload.get("entries")

    if source_id != XIANXIA_HOMEBREW_SOURCE_ID:
        raise ValueError(
            f"Expected Xianxia Systems seed source_id {XIANXIA_HOMEBREW_SOURCE_ID!r}, got {source_id!r}."
        )
    if not source_title:
        raise ValueError("Xianxia Systems seed payload is missing source_title.")
    if not version:
        raise ValueError("Xianxia Systems seed payload is missing version.")
    if storage_strategy != XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY:
        raise ValueError(
            "Xianxia Systems seed payload must use the curated_seed_data storage strategy."
        )
    if not isinstance(raw_entries, list):
        raise ValueError("Xianxia Systems seed payload must include an entries list.")

    return payload


_XIANXIA_SYSTEMS_SEED_PAYLOAD = _load_xianxia_systems_seed_payload()
XIANXIA_SYSTEMS_SEED_SOURCE_TITLE = str(_XIANXIA_SYSTEMS_SEED_PAYLOAD["source_title"])
XIANXIA_SYSTEMS_SEED_VERSION = str(_XIANXIA_SYSTEMS_SEED_PAYLOAD["version"])


def build_xianxia_systems_seed_entries() -> list[dict[str, Any]]:
    payload = _load_xianxia_systems_seed_payload()
    entries: list[dict[str, Any]] = []
    source_path = f"managed:{XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH}#{XIANXIA_SYSTEMS_SEED_VERSION}"
    for index, raw_spec in enumerate(payload["entries"], start=1):
        if not isinstance(raw_spec, dict):
            raise ValueError(f"Xianxia Systems seed entry {index} must be an object.")
        entries.append(_build_seed_entry(raw_spec, index=index, source_path=source_path))
    return entries


def _build_seed_entry(raw_spec: dict[str, Any], *, index: int, source_path: str) -> dict[str, Any]:
    title = str(raw_spec.get("title") or "").strip()
    if not title:
        raise ValueError(f"Xianxia Systems seed entry {index} is missing title.")

    entry_type = str(raw_spec.get("entry_type") or "").strip().lower()
    if not entry_type:
        raise ValueError(f"Xianxia Systems seed entry {index} is missing entry_type.")

    slug = str(raw_spec.get("slug") or "").strip() or slugify(title)
    entry_key = (
        str(raw_spec.get("entry_key") or "").strip()
        or f"xianxia|{entry_type}|{XIANXIA_HOMEBREW_SOURCE_ID.lower()}|{slug}"
    )
    aliases = _normalize_string_list(raw_spec.get("aliases"))
    facets = _normalize_string_list(raw_spec.get("facets"))
    summary = str(raw_spec.get("summary") or "").strip()
    sections = _normalize_sections(raw_spec.get("sections"))
    raw_metadata = raw_spec.get("metadata")
    raw_body = raw_spec.get("body")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    metadata.update(
        {
            "aliases": aliases,
            "facets": facets,
            "seed_version": XIANXIA_SYSTEMS_SEED_VERSION,
            "seed_storage_strategy": XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY,
            "source_kind": "app_reference",
            "source_provenance": {
                "kind": "gm_reviewed_requirements",
                "requirements_report": ".local/xianxia-requirements-report.md",
            },
            "content_origin": "managed_seed_file",
            "content_source_path": XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH,
            "content_migration_stage": "curated_seed_data_to_sqlite",
        }
    )
    body = dict(raw_body) if isinstance(raw_body, dict) else {}
    body.setdefault("summary", summary)
    body.setdefault("aliases", aliases)
    body.setdefault("facets", facets)
    body.setdefault("sections", sections)
    search_parts = [
        title,
        entry_type,
        XIANXIA_HOMEBREW_SOURCE_ID,
        summary,
        *aliases,
        *facets,
        str(raw_spec.get("search_text") or "").strip(),
    ]
    rendered_html = str(raw_spec.get("rendered_html") or "").strip() or _render_seed_entry_html(
        summary=summary,
        aliases=aliases,
        sections=sections,
    )
    return {
        "entry_key": entry_key,
        "entry_type": entry_type,
        "slug": slug,
        "title": title,
        "source_page": str(raw_spec.get("source_page") or "Xianxia curated seed").strip(),
        "source_path": source_path,
        "search_text": " ".join(part for part in search_parts if part).lower(),
        "player_safe_default": bool(raw_spec.get("player_safe_default", True)),
        "dm_heavy": bool(raw_spec.get("dm_heavy", False)),
        "metadata": metadata,
        "body": body,
        "rendered_html": rendered_html,
    }


def _normalize_string_list(raw_values: object) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def _normalize_sections(raw_sections: object) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return []

    sections: list[dict[str, Any]] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            continue
        title = str(raw_section.get("title") or "").strip()
        paragraphs = _normalize_string_list(raw_section.get("paragraphs"))
        bullets = _normalize_string_list(raw_section.get("bullets"))
        if not title and not paragraphs and not bullets:
            continue
        sections.append(
            {
                "title": title,
                "paragraphs": paragraphs,
                "bullets": bullets,
            }
        )
    return sections


def _render_seed_entry_html(
    *,
    summary: str,
    aliases: list[str],
    sections: list[dict[str, Any]],
) -> str:
    parts: list[str] = ['<section class="systems-entry-summary">']
    if aliases:
        parts.append(f"<p><strong>Also covers:</strong> {escape(', '.join(aliases))}</p>")
    if summary:
        parts.append(f"<p>{escape(summary)}</p>")
    parts.append("</section>")

    for section in sections:
        title = str(section.get("title") or "").strip()
        paragraphs = [str(value).strip() for value in list(section.get("paragraphs") or []) if str(value).strip()]
        bullets = [str(value).strip() for value in list(section.get("bullets") or []) if str(value).strip()]
        if not title and not paragraphs and not bullets:
            continue
        parts.append("<section>")
        if title:
            parts.append(f"<h2>{escape(title)}</h2>")
        for paragraph in paragraphs:
            parts.append(f"<p>{escape(paragraph)}</p>")
        if bullets:
            parts.append("<ul>")
            parts.extend(f"<li>{escape(item)}</li>" for item in bullets)
            parts.append("</ul>")
        parts.append("</section>")
    return "".join(parts)
