from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from .repository import slugify

DND5E_RULES_REFERENCE_SOURCE_ID = "RULES"
_RULES_REFERENCE_DATA_RELATIVE_PATH = "player_wiki/data/dnd5e_rules_reference.json"
_RULES_REFERENCE_DATA_PATH = Path(__file__).resolve().parent / "data" / "dnd5e_rules_reference.json"


@lru_cache(maxsize=1)
def _load_rules_reference_payload() -> dict[str, Any]:
    # Keep the reference text in managed seed data so SQLite reseeding does not depend on Python literals.
    payload = json.loads(_RULES_REFERENCE_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("DND 5E rules reference payload must be a JSON object.")

    source_id = str(payload.get("source_id") or "").strip()
    source_title = str(payload.get("source_title") or "").strip()
    version = str(payload.get("version") or "").strip()
    raw_entries = payload.get("entries")

    if source_id != DND5E_RULES_REFERENCE_SOURCE_ID:
        raise ValueError(
            f"Expected DND 5E rules reference source_id {DND5E_RULES_REFERENCE_SOURCE_ID!r}, got {source_id!r}."
        )
    if not source_title:
        raise ValueError("DND 5E rules reference payload is missing source_title.")
    if not version:
        raise ValueError("DND 5E rules reference payload is missing version.")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("DND 5E rules reference payload must include at least one entry.")

    return payload


_RULES_REFERENCE_PAYLOAD = _load_rules_reference_payload()
DND5E_RULES_REFERENCE_SOURCE_TITLE = str(_RULES_REFERENCE_PAYLOAD["source_title"])
DND5E_RULES_REFERENCE_VERSION = str(_RULES_REFERENCE_PAYLOAD["version"])
_FIRST_ENTRY_TITLE = str(
    (dict(_RULES_REFERENCE_PAYLOAD["entries"][0]).get("title") or "")
).strip()
if not _FIRST_ENTRY_TITLE:
    raise ValueError("DND 5E rules reference payload is missing the first entry title.")
DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY = (
    f"{DND5E_RULES_REFERENCE_SOURCE_ID.lower()}-rule-{slugify(_FIRST_ENTRY_TITLE)}"
)


def build_dnd5e_rules_reference_entries() -> list[dict[str, Any]]:
    payload = _load_rules_reference_payload()
    entries: list[dict[str, Any]] = []
    source_path = f"managed:{_RULES_REFERENCE_DATA_RELATIVE_PATH}#{DND5E_RULES_REFERENCE_VERSION}"
    for index, raw_spec in enumerate(payload["entries"], start=1):
        if not isinstance(raw_spec, dict):
            raise ValueError(f"DND 5E rules reference entry {index} must be an object.")

        title = str(raw_spec.get("title") or "").strip()
        if not title:
            raise ValueError(f"DND 5E rules reference entry {index} is missing title.")
        rule_key = str(raw_spec.get("rule_key") or slugify(title)).strip() or slugify(title)
        slug = f"{DND5E_RULES_REFERENCE_SOURCE_ID.lower()}-rule-{slugify(title)}"
        aliases = _normalize_string_list(raw_spec.get("aliases"))
        rule_facets = _normalize_string_list(raw_spec.get("rule_facets"))
        formula = str(raw_spec.get("formula") or "").strip()
        summary = str(raw_spec.get("summary") or "").strip()
        sections = _normalize_sections(raw_spec.get("sections"))
        source_provenance = _normalize_source_provenance(raw_spec.get("source_provenance"))
        body = {
            "summary": summary,
            "formula": formula,
            "aliases": aliases,
            "sections": sections,
        }
        metadata = {
            "summary": summary,
            "formula": formula,
            "aliases": aliases,
            "rule_key": rule_key,
            "rule_facets": rule_facets,
            "seed_version": DND5E_RULES_REFERENCE_VERSION,
            "source_kind": "app_reference",
            "source_provenance": source_provenance,
            "content_origin": "managed_seed_file",
            "content_source_path": _RULES_REFERENCE_DATA_RELATIVE_PATH,
            "content_migration_stage": "seed_file_to_sqlite",
        }
        search_parts = [title, formula, summary, *aliases, *rule_facets]
        entries.append(
            {
                "entry_key": slug,
                "entry_type": "rule",
                "slug": slug,
                "title": title,
                "source_page": "Rules reference",
                "source_path": source_path,
                "search_text": " ".join(part for part in search_parts if part).lower(),
                "player_safe_default": True,
                "dm_heavy": False,
                "metadata": metadata,
                "body": body,
                "rendered_html": _render_rule_entry_html(
                    summary=summary,
                    formula=formula,
                    aliases=aliases,
                    sections=sections,
                ),
            }
        )
    return entries


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


def _normalize_source_provenance(raw_provenance: object) -> dict[str, Any]:
    if not isinstance(raw_provenance, dict) or not raw_provenance:
        return {
            "kind": "normalized_reference",
            "source_ids": ["PHB"],
        }

    normalized: dict[str, Any] = {}
    kind = str(raw_provenance.get("kind") or "").strip()
    if kind:
        normalized["kind"] = kind
    source_ids = _normalize_string_list(raw_provenance.get("source_ids"))
    if source_ids:
        normalized["source_ids"] = source_ids
    if normalized:
        return normalized
    return {
        "kind": "normalized_reference",
        "source_ids": ["PHB"],
    }


def _render_rule_entry_html(
    *,
    summary: str,
    formula: str,
    aliases: list[str],
    sections: list[dict[str, Any]],
) -> str:
    parts: list[str] = ['<section class="systems-entry-summary">']
    if formula:
        parts.append(f"<p><strong>Formula:</strong> {escape(formula)}</p>")
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
