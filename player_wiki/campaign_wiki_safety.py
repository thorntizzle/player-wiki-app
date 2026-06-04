from __future__ import annotations

from collections import defaultdict
import re

from .repository import normalize_lookup
from .session_article_publisher import SESSION_ARTICLE_SOURCE_REF_PREFIX
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    parse_session_article_source_ref,
)


def normalize_dm_player_wiki_ref_value(value: object) -> str:
    if isinstance(value, dict):
        for key in ("page_ref", "slug", "page_slug"):
            normalized = normalize_dm_player_wiki_ref_value(value.get(key))
            if normalized:
                return normalized
        return ""

    if value is None:
        return ""

    if isinstance(value, str):
        normalized = value.strip().replace("\\", "/").strip()
        if normalized.lower().endswith(".md"):
            normalized = normalized[:-3]
        return normalized

    return ""


def collect_character_definition_page_refs(value: object) -> set[str]:
    refs: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                normalized_key = str(key or "")
                if normalized_key == "page_ref" or normalized_key.endswith("_page_ref"):
                    normalized_ref = normalize_dm_player_wiki_ref_value(item)
                    if normalized_ref:
                        refs.add(normalized_ref)
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return refs


def format_dm_player_wiki_usage_sample(values: list[str], *, limit: int = 3) -> str:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(cleaned)

    if not unique_values:
        return ""

    shown = unique_values[:limit]
    label = ", ".join(shown)
    remaining = len(unique_values) - len(shown)
    if remaining > 0:
        label = f"{label}, and {remaining} more"
    return label


def build_dm_player_wiki_removal_safety_index(
    campaign_slug: str,
    campaign,
    page_records: list[object],
    *,
    session_articles: list[object],
    character_records: list[object],
) -> dict[str, dict[str, object]]:
    page_ref_lookup: defaultdict[str, set[str]] = defaultdict(set)
    link_lookup: defaultdict[str, set[str]] = defaultdict(set)
    page_titles: dict[str, str] = {}

    for record in page_records:
        page = getattr(record, "page", None)
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not page_ref or page is None:
            continue

        page_titles[page_ref] = str(getattr(page, "title", "") or page_ref).strip()
        for raw_key in (page_ref, getattr(page, "route_slug", "")):
            normalized_ref = normalize_dm_player_wiki_ref_value(raw_key).casefold()
            if normalized_ref:
                page_ref_lookup[normalized_ref].add(page_ref)

        for raw_key in (
            page_ref,
            getattr(page, "route_slug", ""),
            getattr(page, "title", ""),
            *list(getattr(page, "aliases", []) or []),
        ):
            normalized_key = normalize_lookup(str(raw_key or ""))
            if normalized_key:
                link_lookup[normalized_key].add(page_ref)

    backlinks_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for record in page_records:
        source_page = getattr(record, "page", None)
        source_page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not source_page_ref or source_page is None:
            continue

        source_title = str(getattr(source_page, "title", "") or source_page_ref).strip()
        for raw_target in list(getattr(source_page, "raw_link_targets", []) or []):
            normalized_target = normalize_lookup(str(raw_target or ""))
            for target_page_ref in sorted(link_lookup.get(normalized_target, set())):
                if target_page_ref == source_page_ref:
                    continue
                backlinks_by_page_ref[target_page_ref].append(source_title)

    character_hooks_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for record in page_records:
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        metadata = dict(getattr(record, "metadata", {}) or {})
        if not page_ref:
            continue
        if metadata.get("character_option"):
            character_hooks_by_page_ref[page_ref].append("character option metadata")
        if metadata.get("character_progression"):
            character_hooks_by_page_ref[page_ref].append("character progression metadata")

    for character_record in character_records:
        definition = getattr(character_record, "definition", None)
        if definition is None:
            continue

        character_name = str(getattr(definition, "name", "") or "").strip()
        if not character_name:
            character_name = str(getattr(definition, "character_slug", "") or "character").strip()
        for raw_ref in collect_character_definition_page_refs(definition.to_dict()):
            normalized_ref = normalize_dm_player_wiki_ref_value(raw_ref).casefold()
            for page_ref in sorted(page_ref_lookup.get(normalized_ref, set())):
                character_hooks_by_page_ref[page_ref].append(f"{character_name} sheet link")

    session_articles_by_id = {
        int(getattr(article, "id", 0)): article
        for article in session_articles
        if int(getattr(article, "id", 0) or 0) > 0
    }
    session_provenance_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for article in session_articles:
        source_kind, source_ref = parse_session_article_source_ref(
            str(getattr(article, "source_page_ref", "") or "")
        )
        if source_kind != SESSION_ARTICLE_SOURCE_KIND_PAGE:
            continue
        normalized_ref = normalize_dm_player_wiki_ref_value(source_ref).casefold()
        article_title = str(getattr(article, "title", "") or f"Article {getattr(article, 'id', '')}").strip()
        article_status = str(getattr(article, "status", "") or "").strip()
        article_label = f"{article_title} ({article_status})" if article_status else article_title
        for page_ref in sorted(page_ref_lookup.get(normalized_ref, set())):
            session_provenance_by_page_ref[page_ref].append(article_label)

    safety_index: dict[str, dict[str, object]] = {}
    for record in page_records:
        page = getattr(record, "page", None)
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not page_ref or page is None:
            continue

        source_ref = str(getattr(page, "source_ref", "") or "").strip()

        blockers: list[str] = []
        backlink_refs = sorted(set(backlinks_by_page_ref[page_ref]))
        backlink_sample = format_dm_player_wiki_usage_sample(backlink_refs)
        if backlink_sample:
            blockers.append(f"Backlinked from {backlink_sample}.")

        character_ref_blocks = sorted(set(character_hooks_by_page_ref[page_ref]))
        character_hook_sample = format_dm_player_wiki_usage_sample(character_ref_blocks)
        if character_hook_sample:
            blockers.append(f"Character hooks: {character_hook_sample}.")

        session_provenance = list(session_provenance_by_page_ref[page_ref])
        if source_ref.startswith(SESSION_ARTICLE_SOURCE_REF_PREFIX):
            source_tail = source_ref[len(SESSION_ARTICLE_SOURCE_REF_PREFIX) :].strip()
            article_label = "converted session article"
            if ":" in source_tail:
                source_campaign_slug, article_id_text = source_tail.rsplit(":", 1)
                if source_campaign_slug == campaign_slug and article_id_text.isdigit():
                    article = session_articles_by_id.get(int(article_id_text))
                    if article is not None:
                        article_status = str(getattr(article, "status", "") or "").strip()
                        article_label = str(getattr(article, "title", "") or article_label).strip()
                        if article_status:
                            article_label = f"{article_label} ({article_status})"
            session_provenance.append(article_label)

        session_sample = format_dm_player_wiki_usage_sample(session_provenance)
        if session_sample:
            blockers.append(f"Session provenance: {session_sample}.")

        can_hard_delete = not blockers
        safety_index[page_ref] = {
            "can_hard_delete": can_hard_delete,
            "hard_delete_blockers": blockers,
            "removal_status_label": "Hard delete available" if can_hard_delete else "Hard delete blocked",
            "removal_guidance": (
                "Hard delete is available after confirmation."
                if can_hard_delete
                else "Unpublish/archive this page or clear the references before deleting its file."
            ),
            "blockers_by_type": {
                "backlinks": backlink_refs,
                "character_hooks": character_ref_blocks,
                "session_provenance": sorted(set(session_provenance)),
            },
            "samples": {
                "backlinks": backlink_sample,
                "character_hooks": character_hook_sample,
                "session_provenance": session_sample,
            },
            "page_title": page_titles.get(page_ref, page_ref),
        }

    return safety_index


def build_dm_player_wiki_page_summary(campaign, record, *, removal_safety=None) -> dict[str, object]:
    page = record.page
    route_slug = page.route_slug
    route_page = campaign.pages.get(route_slug)
    is_visible = campaign.is_page_visible(route_page or page)
    removal_safety = dict(removal_safety or {})
    search_text = " ".join(
        str(part or "")
        for part in (
            record.page_ref,
            page.title,
            page.section,
            page.subsection,
            page.page_type,
            page.summary,
            page.source_ref,
        )
    ).lower()
    status_label = (
        "Visible"
        if is_visible
        else "Unpublished"
        if not page.published
        else f"Reveals after session {page.reveal_after_session}"
    )
    return {
        "page_ref": record.page_ref,
        "dom_id": re.sub(r"[^a-zA-Z0-9_-]+", "-", record.page_ref).strip("-") or "page",
        "title": page.title,
        "section": page.section,
        "subsection": page.subsection,
        "page_type": page.page_type,
        "summary": page.summary,
        "source_ref": page.source_ref,
        "image_path": page.image_path,
        "published": page.published,
        "is_visible": is_visible,
        "status_label": status_label,
        "route_slug": route_slug,
        "search_text": search_text,
        "can_hard_delete": bool(removal_safety.get("can_hard_delete", True)),
        "hard_delete_blockers": list(removal_safety.get("hard_delete_blockers", []) or []),
        "removal_status_label": str(removal_safety.get("removal_status_label") or "Hard delete available"),
        "removal_guidance": str(removal_safety.get("removal_guidance") or "Hard delete is available after confirmation."),
        "removal_safety": {
            "can_hard_delete": bool(removal_safety.get("can_hard_delete", True)),
            "blockers_by_type": dict(removal_safety.get("blockers_by_type") or {}),
            "samples": dict(removal_safety.get("samples") or {}),
            "hard_delete_blockers": list(removal_safety.get("hard_delete_blockers", []) or []),
        },
    }
