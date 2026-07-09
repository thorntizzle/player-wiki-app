from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .auth_store import isoformat, utcnow
from .campaign_content_service import list_campaign_asset_files
from .character_markdown_exporter import (
    CharacterMarkdownExportError,
    export_filename_for_character,
    render_dnd_character_markdown,
)
from .character_page_records import list_visible_character_page_records
from .character_presenter import present_character_detail
from .db import get_db
from .models import Campaign, Page, page_sort_key, section_sort_key, subsection_sort_key
from .repository import load_page_content, render_page_content
from .system_policy import is_dnd_5e_system

EXPORT_FORMAT_VERSION = 1
SYSTEM_ENTRY_HREF_PATTERN = re.compile(r"/systems/entries/([a-zA-Z0-9._~/-]+)")


class CampaignPackageExportError(ValueError):
    pass


def export_campaign_package(
    *,
    app: Any,
    campaign_slug: str,
    output_dir: Path,
    image_report_path: Path | None = None,
    base_url: str = "",
    include_inactive_characters: bool = True,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CampaignPackageExportError(f"Output directory is not empty: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")

    repository = app.extensions["repository_store"].get()
    campaign = repository.get_campaign(campaign_slug)
    if campaign is None:
        raise CampaignPackageExportError(f"Unknown campaign slug: {campaign_slug}")

    report_entries = parse_image_association_report(image_report_path) if image_report_path else []
    report_by_page_ref = {
        str(entry.get("page_ref") or ""): entry
        for entry in report_entries
        if str(entry.get("page_ref") or "")
    }

    manifest = _build_manifest(
        app=app,
        campaign=campaign,
        output_dir=output_dir,
        image_report_path=image_report_path,
        base_url=base_url,
        include_inactive_characters=include_inactive_characters,
    )
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "README.md", _render_readme(campaign))

    page_records = _export_campaign_pages(
        app=app,
        campaign=campaign,
        output_dir=output_dir,
        repository=repository,
        base_url=base_url,
    )
    asset_records = _export_asset_metadata(
        campaign=campaign,
        output_dir=output_dir,
        page_records=page_records,
        report_by_page_ref=report_by_page_ref,
        report_entries=report_entries,
        base_url=base_url,
        image_report_path=image_report_path,
    )
    systems_summary = _export_systems(app=app, campaign=campaign, output_dir=output_dir)
    character_summary = _export_characters(
        app=app,
        campaign=campaign,
        output_dir=output_dir,
        include_inactive_characters=include_inactive_characters,
    )
    sqlite_table_summary = _export_campaign_sqlite_rows(campaign.slug, output_dir)
    audit = _build_audit(
        campaign=campaign,
        page_records=page_records,
        asset_records=asset_records,
        report_entries=report_entries,
        systems_summary=systems_summary,
        character_summary=character_summary,
    )
    _write_json(output_dir / "audit" / "unresolved-references.json", audit)
    _write_text(output_dir / "audit" / "export-report.md", _render_audit_report(audit, manifest))

    summary = {
        "output_dir": str(output_dir),
        "campaign_slug": campaign.slug,
        "page_count": len(page_records),
        "visible_page_count": sum(1 for record in page_records if record["is_visible"]),
        "image_association_count": len(asset_records["image_associations"]),
        "systems_entry_count": systems_summary["entry_count"],
        "character_count": character_summary["character_count"],
        "sqlite_table_count": len(sqlite_table_summary),
        "audit_issue_count": _count_audit_issues(audit),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def parse_image_association_report(report_path: Path | None) -> list[dict[str, Any]]:
    if report_path is None:
        return []
    if not report_path.exists():
        raise CampaignPackageExportError(f"Image association report not found: {report_path}")

    entries: list[dict[str, Any]] = []
    current_section = ""
    for raw_line in report_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        section_match = re.match(r"^###\s+(.+?)(?:\s+\(\d+\))?$", line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Article |"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6:
            continue

        article_text, subsection, page_ref_text, live_asset_text, source_png_text, source_match = cells
        article_title, article_url = _parse_markdown_link(article_text)
        live_asset_ref, live_asset_url = _parse_markdown_link(live_asset_text)
        page_ref = _strip_markdown_code(page_ref_text)
        source_png = _strip_markdown_code(source_png_text)
        if not page_ref:
            continue

        entries.append(
            {
                "article": article_title or article_text,
                "article_url": article_url,
                "section": current_section,
                "subsection": subsection,
                "page_ref": page_ref,
                "live_webp_asset_ref": live_asset_ref,
                "live_webp_asset_url": live_asset_url,
                "source_png_path": source_png,
                "source_png_exists": bool(source_png and Path(source_png).exists()),
                "source_match": source_match,
            }
        )
    return entries


def _build_manifest(
    *,
    app: Any,
    campaign: Campaign,
    output_dir: Path,
    image_report_path: Path | None,
    base_url: str,
    include_inactive_characters: bool,
) -> dict[str, Any]:
    config = app.config
    return {
        "export_format": "campaign-player-wiki-campaign-package",
        "export_format_version": EXPORT_FORMAT_VERSION,
        "exported_at": isoformat(utcnow()),
        "campaign": {
            "slug": campaign.slug,
            "title": campaign.title,
            "system": campaign.system,
            "current_session": campaign.current_session,
            "systems_library_slug": campaign.systems_library_slug,
        },
        "source": {
            "campaigns_dir": str(Path(config["CAMPAIGNS_DIR"]).resolve()),
            "db_path": str(Path(config["DB_PATH"]).resolve()),
            "base_url": base_url,
            "image_report_path": str(image_report_path.resolve()) if image_report_path else "",
        },
        "app": {
            "version": str(config.get("APP_VERSION", "")),
            "build_id": str(config.get("APP_BUILD_ID", "")),
            "git_sha": str(config.get("APP_GIT_SHA", "")),
            "git_dirty": bool(config.get("APP_GIT_DIRTY", False)),
            "runtime": str(config.get("APP_RUNTIME", "")),
            "instance_name": str(config.get("APP_INSTANCE_NAME", "")),
        },
        "options": {
            "include_inactive_characters": include_inactive_characters,
            "include_binary_assets": False,
            "image_assets_mode": "metadata-only",
        },
        "output_dir": str(output_dir.resolve()),
    }


def _export_campaign_pages(
    *,
    app: Any,
    campaign: Campaign,
    output_dir: Path,
    repository: Any,
    base_url: str,
) -> list[dict[str, Any]]:
    page_store = app.extensions["campaign_page_store"]
    content_dir = Path(campaign.player_content_dir)
    page_store.sync_campaign_pages(campaign.slug, content_dir)
    records = page_store.list_page_records(
        campaign.slug,
        content_dir=content_dir,
        include_body=True,
    )

    page_payloads: list[dict[str, Any]] = []
    pages_markdown_dir = output_dir / "campaign" / "pages" / "markdown"
    pages_html_dir = output_dir / "campaign" / "pages" / "html"
    pages_source_dir = output_dir / "campaign" / "pages" / "source"

    campaign_config_path = Path(campaign.player_content_dir).parent / "campaign.yaml"
    if campaign_config_path.exists():
        _write_text(output_dir / "campaign" / "campaign.yaml", campaign_config_path.read_text(encoding="utf-8"))

    for record in records:
        page = campaign.pages.get(record.page.route_slug) or record.page
        body_markdown = load_page_content(campaign, page, page_store)
        rendered_html = render_page_content(campaign, page, page_store).replace(
            "{campaign_slug}",
            campaign.slug,
        )
        is_visible = campaign.is_page_visible(page)
        payload = _page_payload(record, page, body_markdown, rendered_html, is_visible, base_url)
        page_payloads.append(payload)

        output_page_path = _safe_relative_output_path(record.page_ref, ".md")
        _write_text(
            pages_markdown_dir / output_page_path,
            _markdown_with_frontmatter(record.metadata, body_markdown),
        )
        _write_text(
            pages_html_dir / output_page_path.with_suffix(".html"),
            rendered_html,
        )
        source_path = Path(campaign.player_content_dir) / Path(*PurePosixPath(record.relative_path).parts)
        if source_path.exists():
            _write_text(
                pages_source_dir / output_page_path,
                source_path.read_text(encoding="utf-8"),
            )

    page_payloads.sort(key=lambda item: item["sort_key"])
    for item in page_payloads:
        item.pop("sort_key", None)

    _write_jsonl(output_dir / "campaign" / "pages.jsonl", page_payloads)
    _write_json(output_dir / "campaign" / "navigation.json", _build_navigation(campaign, page_payloads))
    _write_json(output_dir / "campaign" / "presentation.json", _build_campaign_presentation_contract())
    return page_payloads


def _page_payload(
    record: Any,
    page: Page,
    body_markdown: str,
    rendered_html: str,
    is_visible: bool,
    base_url: str,
) -> dict[str, Any]:
    page_url = f"{base_url}/campaigns/{record.campaign_slug}/pages/{page.route_slug}" if base_url else ""
    asset_url = (
        f"{base_url}/campaigns/{record.campaign_slug}/assets/{page.image_path}"
        if base_url and page.image_path
        else ""
    )
    return {
        "campaign_slug": record.campaign_slug,
        "page_ref": record.page_ref,
        "route_slug": page.route_slug,
        "title": page.title,
        "section": page.section,
        "subsection": page.subsection,
        "page_type": page.page_type,
        "display_order": page.display_order,
        "published": page.published,
        "is_visible": is_visible,
        "is_pinned": page.is_pinned,
        "display_type": page.display_type,
        "aliases": list(page.aliases),
        "summary": page.summary,
        "image": {
            "asset_ref": page.image_path,
            "asset_url": asset_url,
            "alt": page.image_alt,
            "caption": page.image_caption,
        },
        "reveal_after_session": page.reveal_after_session,
        "source_ref": page.source_ref,
        "source": {
            "relative_path": record.relative_path,
            "source_path": str(Path(record.file_path).resolve()) if getattr(record, "file_path", None) else "",
            "updated_at": record.updated_at,
        },
        "metadata": dict(record.metadata),
        "body_markdown": body_markdown,
        "rendered_html": rendered_html,
        "raw_link_targets": list(page.raw_link_targets),
        "resolved_links": list(page.resolved_links),
        "backlinks": list(page.backlinks),
        "url": page_url,
        "sort_key": list(page_sort_key(page)),
    }


def _build_navigation(campaign: Campaign, pages: list[dict[str, Any]]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    pages_by_section: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        pages_by_section.setdefault(page["section"], []).append(page)

    for section_name in sorted(pages_by_section, key=section_sort_key):
        section_pages = pages_by_section[section_name]
        subsections: list[dict[str, Any]] = []
        pages_by_subsection: dict[str, list[dict[str, Any]]] = {}
        for page in section_pages:
            pages_by_subsection.setdefault(page["subsection"], []).append(page)
        for subsection_name in sorted(
            pages_by_subsection,
            key=lambda value: subsection_sort_key(section_name, value),
        ):
            subsection_pages = pages_by_subsection[subsection_name]
            subsections.append(
                {
                    "name": subsection_name,
                    "pages": [_navigation_page(page) for page in subsection_pages],
                }
            )
        sections.append(
            {
                "name": section_name,
                "slug": _section_slug(section_name),
                "pages": [_navigation_page(page) for page in section_pages if not page["subsection"]],
                "subsections": subsections,
            }
        )

    return {
        "campaign_slug": campaign.slug,
        "current_session": campaign.current_session,
        "sections": sections,
    }


def _navigation_page(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": page["title"],
        "page_ref": page["page_ref"],
        "route_slug": page["route_slug"],
        "page_type": page["page_type"],
        "display_type": page["display_type"],
        "is_visible": page["is_visible"],
        "is_pinned": page["is_pinned"],
        "published": page["published"],
        "reveal_after_session": page["reveal_after_session"],
        "summary": page["summary"],
        "image_asset_ref": page["image"]["asset_ref"],
    }


def _build_campaign_presentation_contract() -> dict[str, Any]:
    return {
        "campaign_home": {
            "latest_session_card": "visible pages with section 'Sessions' and type 'session', highest reveal_after_session wins",
            "section_cards": "sections sorted by Campaign Player Wiki SECTION_ORDER, with subsections and pinned pages surfaced first",
        },
        "page_detail": {
            "lead": "title, optional summary, optional page image, rendered body",
            "internal_links": "Obsidian links are resolved through the campaign alias index into page route slugs",
            "backlinks": "visible incoming page links are shown from the read model",
        },
        "visibility": {
            "visible_page_rule": "published, not a legacy overview page, and reveal_after_session <= campaign.current_session",
        },
    }


def _export_asset_metadata(
    *,
    campaign: Campaign,
    output_dir: Path,
    page_records: list[dict[str, Any]],
    report_by_page_ref: dict[str, dict[str, Any]],
    report_entries: list[dict[str, Any]],
    base_url: str,
    image_report_path: Path | None,
) -> dict[str, Any]:
    asset_files = list_campaign_asset_files(campaign)
    asset_by_ref = {asset.asset_ref: asset for asset in asset_files}
    asset_payloads = [
        {
            "asset_ref": asset.asset_ref,
            "relative_path": asset.relative_path,
            "asset_path": str(asset.file_path.resolve()),
            "size_bytes": asset.size_bytes,
            "media_type": asset.media_type,
            "updated_at": asset.updated_at,
        }
        for asset in asset_files
    ]
    _write_jsonl(output_dir / "assets" / "assets-manifest.jsonl", asset_payloads)

    image_associations: list[dict[str, Any]] = []
    for page in page_records:
        asset_ref = str(page["image"].get("asset_ref") or "")
        if not asset_ref:
            continue
        report_entry = report_by_page_ref.get(page["route_slug"]) or report_by_page_ref.get(page["page_ref"])
        asset_record = asset_by_ref.get(asset_ref)
        live_asset_url = (
            str(report_entry.get("live_webp_asset_url") or "")
            if report_entry
            else (f"{base_url}/campaigns/{campaign.slug}/assets/{asset_ref}" if base_url else "")
        )
        source_png = str((report_entry or {}).get("source_png_path") or "")
        image_associations.append(
            {
                "page_ref": page["page_ref"],
                "route_slug": page["route_slug"],
                "article": page["title"],
                "section": page["section"],
                "subsection": page["subsection"],
                "page_url": page["url"],
                "campaign_asset_ref": asset_ref,
                "campaign_asset_path": str(asset_record.file_path.resolve()) if asset_record else "",
                "campaign_asset_exists": asset_record is not None,
                "live_webp_asset_ref": str((report_entry or {}).get("live_webp_asset_ref") or asset_ref),
                "live_webp_asset_url": live_asset_url,
                "source_png_path": source_png,
                "source_png_exists": bool(source_png and Path(source_png).exists()),
                "source_match": str((report_entry or {}).get("source_match") or "unresolved"),
                "image_alt": page["image"].get("alt") or "",
                "image_caption": page["image"].get("caption") or "",
            }
        )

    _write_jsonl(output_dir / "assets" / "image-associations.jsonl", image_associations)
    _write_text(
        output_dir / "assets" / "image-associations.md",
        _render_image_associations_markdown(campaign, image_associations),
    )
    if image_report_path is not None:
        _write_text(
            output_dir / "assets" / "source-image-report.md",
            image_report_path.read_text(encoding="utf-8"),
        )

    return {
        "asset_manifest": asset_payloads,
        "image_associations": image_associations,
        "source_report_entries": report_entries,
    }


def _export_systems(*, app: Any, campaign: Campaign, output_dir: Path) -> dict[str, Any]:
    systems_service = app.extensions["systems_service"]
    systems_store = app.extensions["systems_store"]
    library = systems_service.get_campaign_library(campaign.slug)
    if library is None:
        empty_summary = {
            "library_slug": "",
            "entry_count": 0,
            "entry_keys": [],
            "entry_slugs": [],
        }
        _write_json(output_dir / "systems" / "summary.json", empty_summary)
        return empty_summary

    source_states = systems_service.list_campaign_source_states(campaign.slug)
    sources = systems_store.list_sources(library.library_slug)
    entries = _list_all_systems_entries(systems_store, library.library_slug)
    entry_keys = sorted({entry.entry_key for entry in entries})
    entry_slugs = sorted({entry.slug for entry in entries})
    entry_payloads = [_systems_entry_payload(entry) for entry in entries]

    _write_json(output_dir / "systems" / "library.json", _json_ready(library))
    _write_jsonl(output_dir / "systems" / "sources.jsonl", [_json_ready(source) for source in sources])
    _write_jsonl(
        output_dir / "systems" / "campaign-source-states.jsonl",
        [_campaign_source_state_payload(state) for state in source_states],
    )
    _write_json(
        output_dir / "systems" / "campaign-policy.json",
        _json_ready(systems_service.get_campaign_policy(campaign.slug)),
    )
    _write_jsonl(
        output_dir / "systems" / "campaign-enabled-sources.jsonl",
        _query_table_rows(
            "campaign_enabled_sources",
            "SELECT * FROM campaign_enabled_sources WHERE campaign_slug = ? ORDER BY source_id ASC",
            (campaign.slug,),
        ),
    )
    _write_jsonl(
        output_dir / "systems" / "campaign-entry-overrides.jsonl",
        _query_table_rows(
            "campaign_entry_overrides",
            "SELECT * FROM campaign_entry_overrides WHERE campaign_slug = ? ORDER BY entry_key ASC",
            (campaign.slug,),
        ),
    )
    _write_jsonl(output_dir / "systems" / "entries.jsonl", entry_payloads)
    _write_jsonl(
        output_dir / "systems" / "entry-links.jsonl",
        _query_table_rows(
            "systems_entry_links",
            "SELECT * FROM systems_entry_links WHERE library_slug = ? ORDER BY from_entry_key ASC, to_entry_key ASC, relation_type ASC",
            (library.library_slug,),
        ),
    )
    _write_jsonl(
        output_dir / "systems" / "import-runs.jsonl",
        _query_table_rows(
            "systems_import_runs",
            "SELECT * FROM systems_import_runs WHERE library_slug = ? ORDER BY started_at DESC, id DESC",
            (library.library_slug,),
        ),
    )
    _write_jsonl(
        output_dir / "systems" / "shared-entry-edit-events.jsonl",
        _query_table_rows(
            "systems_shared_entry_edit_events",
            "SELECT * FROM systems_shared_entry_edit_events WHERE campaign_slug = ? OR library_slug = ? ORDER BY created_at DESC, id DESC",
            (campaign.slug, library.library_slug),
        ),
    )
    _write_json(output_dir / "systems" / "indexes.json", _build_systems_indexes(entry_payloads, source_states))
    summary = {
        "library_slug": library.library_slug,
        "source_count": len(sources),
        "configured_source_count": len([state for state in source_states if state.is_configured]),
        "enabled_source_count": len([state for state in source_states if state.is_enabled]),
        "entry_count": len(entries),
        "entry_keys": entry_keys,
        "entry_slugs": entry_slugs,
    }
    _write_json(output_dir / "systems" / "summary.json", summary)
    return summary


def _list_all_systems_entries(systems_store: Any, library_slug: str) -> list[Any]:
    entries: list[Any] = []
    offset = 0
    page_size = 1000
    while True:
        page = systems_store.list_entries(library_slug, limit=page_size, offset=offset)
        if not page:
            break
        entries.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return entries


def _systems_entry_payload(entry: Any) -> dict[str, Any]:
    payload = _json_ready(entry)
    payload["full_text_fields"] = {
        "body_json": payload.get("body", {}),
        "rendered_html": payload.get("rendered_html", ""),
        "search_text": payload.get("search_text", ""),
    }
    return payload


def _campaign_source_state_payload(state: Any) -> dict[str, Any]:
    return {
        "source": _json_ready(state.source),
        "is_enabled": bool(state.is_enabled),
        "default_visibility": state.default_visibility,
        "is_configured": bool(state.is_configured),
    }


def _build_systems_indexes(entries: list[dict[str, Any]], source_states: list[Any]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    by_type: dict[str, int] = {}
    for entry in entries:
        source_id = entry["source_id"]
        entry_type = entry["entry_type"]
        source_bucket = by_source.setdefault(source_id, {"count": 0, "entry_types": {}})
        source_bucket["count"] += 1
        source_bucket["entry_types"][entry_type] = source_bucket["entry_types"].get(entry_type, 0) + 1
        by_type[entry_type] = by_type.get(entry_type, 0) + 1
    enabled_sources = [state.source.source_id for state in source_states if state.is_enabled]
    return {
        "enabled_sources": enabled_sources,
        "entry_counts_by_source": by_source,
        "entry_counts_by_type": dict(sorted(by_type.items())),
    }


def _export_characters(
    *,
    app: Any,
    campaign: Campaign,
    output_dir: Path,
    include_inactive_characters: bool,
) -> dict[str, Any]:
    character_repository = app.extensions["character_repository"]
    records = (
        character_repository.list_characters(campaign.slug)
        if include_inactive_characters
        else character_repository.list_visible_characters(campaign.slug)
    )
    records = sorted(records, key=lambda record: record.definition.character_slug)
    campaign_page_records = list_visible_character_page_records(
        app.extensions["campaign_page_store"],
        campaign.slug,
        campaign,
        include_body=True,
        excluded_sections={"Sessions"},
    )
    systems_service = app.extensions["systems_service"]
    systems_store = app.extensions["systems_store"]
    library = systems_service.get_campaign_library(campaign.slug)

    character_index: list[dict[str, Any]] = []
    unresolved_system_slugs: dict[str, list[str]] = {}
    for record in records:
        slug = record.definition.character_slug
        structured_dir = output_dir / "characters" / "structured" / slug
        _write_yaml(structured_dir / "definition.yaml", record.definition.to_dict())
        _write_yaml(structured_dir / "import.yaml", record.import_metadata.to_dict())
        _write_json(
            structured_dir / "state.json",
            {
                "campaign_slug": record.state_record.campaign_slug,
                "character_slug": record.state_record.character_slug,
                "revision": record.state_record.revision,
                "state": record.state_record.state,
                "updated_at": isoformat(record.state_record.updated_at),
                "updated_by_user_id": record.state_record.updated_by_user_id,
            },
        )
        presented = present_character_detail(
            campaign,
            record,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        _write_json(structured_dir / "presented.json", _json_ready(presented))

        markdown_path = ""
        if is_dnd_5e_system(record.definition.system):
            try:
                markdown = render_dnd_character_markdown(
                    campaign,
                    record,
                    systems_service=systems_service,
                    campaign_page_records=campaign_page_records,
                )
            except CharacterMarkdownExportError:
                markdown = ""
            if markdown:
                markdown_file = output_dir / "characters" / "markdown" / export_filename_for_character(record)
                _write_text(markdown_file, markdown)
                markdown_path = str(markdown_file.relative_to(output_dir).as_posix())

        resolved_entries, unresolved = _resolve_presented_system_entries(
            presented,
            systems_store=systems_store,
            library_slug=library.library_slug if library else "",
        )
        unresolved_system_slugs[slug] = unresolved
        _write_json(
            output_dir / "characters" / "resolved-systems" / f"{slug}.json",
            {
                "character_slug": slug,
                "referenced_entry_slugs": [entry["slug"] for entry in resolved_entries],
                "entries": resolved_entries,
                "unresolved_entry_slugs": unresolved,
            },
        )

        character_index.append(
            {
                "character_slug": slug,
                "name": record.definition.name,
                "status": record.definition.status,
                "system": record.definition.system,
                "state_revision": record.state_record.revision,
                "markdown_path": markdown_path,
                "structured_dir": f"characters/structured/{slug}",
                "resolved_systems_path": f"characters/resolved-systems/{slug}.json",
            }
        )

    _write_jsonl(output_dir / "characters" / "characters.jsonl", character_index)
    return {
        "character_count": len(records),
        "character_slugs": [record.definition.character_slug for record in records],
        "unresolved_system_slugs": unresolved_system_slugs,
    }


def _resolve_presented_system_entries(
    presented: Any,
    *,
    systems_store: Any,
    library_slug: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    slugs = sorted(_collect_system_entry_slugs(presented))
    if not library_slug:
        return [], slugs
    entries: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for slug in slugs:
        entry = systems_store.get_entry_by_slug(library_slug, slug)
        if entry is None:
            unresolved.append(slug)
            continue
        entries.append(_systems_entry_payload(entry))
    return entries, unresolved


def _collect_system_entry_slugs(value: Any) -> set[str]:
    slugs: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            slugs.update(_collect_system_entry_slugs(child))
    elif isinstance(value, list):
        for child in value:
            slugs.update(_collect_system_entry_slugs(child))
    elif isinstance(value, str):
        slugs.update(match.group(1).strip("/") for match in SYSTEM_ENTRY_HREF_PATTERN.finditer(value))
    return slugs


def _export_campaign_sqlite_rows(campaign_slug: str, output_dir: Path) -> dict[str, int]:
    table_exports: dict[str, list[dict[str, Any]]] = {
        "campaign_memberships": _query_table_rows(
            "campaign_memberships",
            "SELECT * FROM campaign_memberships WHERE campaign_slug = ? ORDER BY id ASC",
            (campaign_slug,),
        ),
        "campaign_visibility_settings": _query_table_rows(
            "campaign_visibility_settings",
            "SELECT * FROM campaign_visibility_settings WHERE campaign_slug = ? ORDER BY scope ASC",
            (campaign_slug,),
        ),
        "character_assignments": _query_table_rows(
            "character_assignments",
            "SELECT * FROM character_assignments WHERE campaign_slug = ? ORDER BY character_slug ASC",
            (campaign_slug,),
        ),
        "character_state": _query_table_rows(
            "character_state",
            "SELECT * FROM character_state WHERE campaign_slug = ? ORDER BY character_slug ASC",
            (campaign_slug,),
        ),
        "campaign_pages": _query_table_rows(
            "campaign_pages",
            "SELECT * FROM campaign_pages WHERE campaign_slug = ? ORDER BY page_ref ASC",
            (campaign_slug,),
        ),
        "campaign_page_sync_state": _query_table_rows(
            "campaign_page_sync_state",
            "SELECT * FROM campaign_page_sync_state WHERE campaign_slug = ?",
            (campaign_slug,),
        ),
        "campaign_sessions": _query_table_rows(
            "campaign_sessions",
            "SELECT * FROM campaign_sessions WHERE campaign_slug = ? ORDER BY id ASC",
            (campaign_slug,),
        ),
        "campaign_session_states": _query_table_rows(
            "campaign_session_states",
            "SELECT * FROM campaign_session_states WHERE campaign_slug = ?",
            (campaign_slug,),
        ),
        "campaign_session_articles": _query_table_rows(
            "campaign_session_articles",
            "SELECT * FROM campaign_session_articles WHERE campaign_slug = ? ORDER BY id ASC",
            (campaign_slug,),
        ),
        "campaign_session_messages": _query_table_rows(
            "campaign_session_messages",
            "SELECT * FROM campaign_session_messages WHERE campaign_slug = ? ORDER BY session_id ASC, created_at ASC, id ASC",
            (campaign_slug,),
        ),
        "campaign_session_article_images": _query_table_rows(
            "campaign_session_article_images",
            """
            SELECT
                campaign_session_article_images.article_id,
                campaign_session_article_images.filename,
                campaign_session_article_images.media_type,
                campaign_session_article_images.alt_text,
                campaign_session_article_images.caption,
                LENGTH(campaign_session_article_images.data_blob) AS data_blob_size_bytes,
                campaign_session_article_images.updated_at
            FROM campaign_session_article_images
            JOIN campaign_session_articles
              ON campaign_session_articles.id = campaign_session_article_images.article_id
            WHERE campaign_session_articles.campaign_slug = ?
            ORDER BY campaign_session_article_images.article_id ASC
            """,
            (campaign_slug,),
        ),
        "campaign_dm_statblocks": _query_table_rows(
            "campaign_dm_statblocks",
            "SELECT * FROM campaign_dm_statblocks WHERE campaign_slug = ? ORDER BY title ASC, id ASC",
            (campaign_slug,),
        ),
        "campaign_dm_condition_definitions": _query_table_rows(
            "campaign_dm_condition_definitions",
            "SELECT * FROM campaign_dm_condition_definitions WHERE campaign_slug = ? ORDER BY name ASC, id ASC",
            (campaign_slug,),
        ),
        "campaign_combatants": _query_table_rows(
            "campaign_combatants",
            "SELECT * FROM campaign_combatants WHERE campaign_slug = ? ORDER BY display_name ASC, id ASC",
            (campaign_slug,),
        ),
        "campaign_combat_trackers": _query_table_rows(
            "campaign_combat_trackers",
            "SELECT * FROM campaign_combat_trackers WHERE campaign_slug = ?",
            (campaign_slug,),
        ),
        "campaign_combat_conditions": _query_table_rows(
            "campaign_combat_conditions",
            """
            SELECT campaign_combat_conditions.*
            FROM campaign_combat_conditions
            JOIN campaign_combatants
              ON campaign_combatants.id = campaign_combat_conditions.combatant_id
            WHERE campaign_combatants.campaign_slug = ?
            ORDER BY campaign_combat_conditions.combatant_id ASC, campaign_combat_conditions.id ASC
            """,
            (campaign_slug,),
        ),
        "campaign_combatant_resource_counters": _query_table_rows(
            "campaign_combatant_resource_counters",
            """
            SELECT campaign_combatant_resource_counters.*
            FROM campaign_combatant_resource_counters
            JOIN campaign_combatants
              ON campaign_combatants.id = campaign_combatant_resource_counters.combatant_id
            WHERE campaign_combatants.campaign_slug = ?
            ORDER BY campaign_combatant_resource_counters.combatant_id ASC, campaign_combatant_resource_counters.id ASC
            """,
            (campaign_slug,),
        ),
        "campaign_combatant_resource_notes": _query_table_rows(
            "campaign_combatant_resource_notes",
            """
            SELECT campaign_combatant_resource_notes.*
            FROM campaign_combatant_resource_notes
            JOIN campaign_combatants
              ON campaign_combatants.id = campaign_combatant_resource_notes.combatant_id
            WHERE campaign_combatants.campaign_slug = ?
            ORDER BY campaign_combatant_resource_notes.combatant_id ASC, campaign_combatant_resource_notes.id ASC
            """,
            (campaign_slug,),
        ),
    }

    summary: dict[str, int] = {}
    for table_name, rows in table_exports.items():
        _write_jsonl(output_dir / "state" / "sqlite-tables" / f"{table_name}.jsonl", rows)
        summary[table_name] = len(rows)
    _write_json(output_dir / "state" / "sqlite-table-summary.json", summary)
    return summary


def _query_table_rows(table_name: str, sql: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, parameters).fetchall()
    return [_row_to_dict(row, table_name=table_name) for row in rows]


def _row_to_dict(row: Any, *, table_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, bytes):
            payload[key] = {
                "binary_omitted": True,
                "size_bytes": len(value),
            }
        elif key.endswith("_json") and isinstance(value, str):
            payload[key] = _loads_json(value)
        else:
            payload[key] = value
    payload["_source_table"] = table_name
    return payload


def _build_audit(
    *,
    campaign: Campaign,
    page_records: list[dict[str, Any]],
    asset_records: dict[str, Any],
    report_entries: list[dict[str, Any]],
    systems_summary: dict[str, Any],
    character_summary: dict[str, Any],
) -> dict[str, Any]:
    page_refs = {page["page_ref"] for page in page_records}
    route_slugs = {page["route_slug"] for page in page_records}
    assets_by_ref = {asset["asset_ref"] for asset in asset_records["asset_manifest"]}
    report_refs = {entry["page_ref"] for entry in report_entries}
    exported_entry_keys = set(systems_summary.get("entry_keys") or [])

    unresolved_page_links: list[dict[str, Any]] = []
    for page in page_records:
        resolved_count = len(page.get("resolved_links") or [])
        raw_targets = list(page.get("raw_link_targets") or [])
        if len(raw_targets) > resolved_count:
            unresolved_page_links.append(
                {
                    "page_ref": page["page_ref"],
                    "route_slug": page["route_slug"],
                    "raw_link_targets": raw_targets,
                    "resolved_links": page.get("resolved_links") or [],
                }
            )

    image_associations = list(asset_records["image_associations"])
    missing_asset_files = [
        {
            "page_ref": image["page_ref"],
            "route_slug": image["route_slug"],
            "campaign_asset_ref": image["campaign_asset_ref"],
        }
        for image in image_associations
        if image["campaign_asset_ref"] not in assets_by_ref and not image["live_webp_asset_url"]
    ]
    unresolved_source_pngs = [
        {
            "page_ref": image["page_ref"],
            "route_slug": image["route_slug"],
            "campaign_asset_ref": image["campaign_asset_ref"],
            "source_png_path": image["source_png_path"],
            "source_match": image["source_match"],
        }
        for image in image_associations
        if not image["source_png_path"]
    ]
    missing_source_pngs = [
        {
            "page_ref": image["page_ref"],
            "route_slug": image["route_slug"],
            "source_png_path": image["source_png_path"],
            "source_match": image["source_match"],
        }
        for image in image_associations
        if image["source_png_path"] and not image["source_png_exists"]
    ]
    report_entries_without_pages = sorted(report_refs - page_refs - route_slugs)

    systems_link_targets_missing: list[dict[str, Any]] = []
    for link in _query_table_rows(
        "systems_entry_links",
        "SELECT * FROM systems_entry_links WHERE library_slug = ? ORDER BY from_entry_key ASC, to_entry_key ASC",
        (systems_summary.get("library_slug") or campaign.systems_library_slug,),
    ):
        if link.get("from_entry_key") not in exported_entry_keys or link.get("to_entry_key") not in exported_entry_keys:
            systems_link_targets_missing.append(link)

    return {
        "unresolved_page_links": unresolved_page_links,
        "missing_campaign_asset_files": missing_asset_files,
        "unresolved_source_pngs": unresolved_source_pngs,
        "missing_source_pngs": missing_source_pngs,
        "report_entries_without_pages": report_entries_without_pages,
        "systems_link_targets_missing": systems_link_targets_missing,
        "character_unresolved_system_slugs": {
            slug: unresolved
            for slug, unresolved in character_summary.get("unresolved_system_slugs", {}).items()
            if unresolved
        },
    }


def _count_audit_issues(audit: dict[str, Any]) -> int:
    total = 0
    for value in audit.values():
        if isinstance(value, dict):
            total += sum(len(item) for item in value.values() if isinstance(item, list))
        elif isinstance(value, list):
            total += len(value)
    return total


def _render_audit_report(audit: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# Export Audit Report",
        "",
        f"- Campaign: {manifest['campaign']['title']} (`{manifest['campaign']['slug']}`)",
        f"- Exported at: {manifest['exported_at']}",
        f"- Binary assets included: {str(manifest['options']['include_binary_assets']).lower()}",
        "",
        "## Issue Counts",
        "",
    ]
    for key, value in audit.items():
        count = len(value) if isinstance(value, list) else sum(len(item) for item in value.values())
        lines.append(f"- {key}: {count}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Image binaries are intentionally omitted. `assets/image-associations.jsonl` records page association, live asset location, and source PNG path.",
            "- Campaign Player Wiki auth secrets, password hashes, invite tokens, API tokens, and web sessions are intentionally omitted from this campaign package.",
            "- Systems entries are exported with structured body JSON and rendered HTML so references can be rendered without a second lookup source.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_image_associations_markdown(campaign: Campaign, image_associations: list[dict[str, Any]]) -> str:
    lines = [
        "# Image Associations",
        "",
        f"- Campaign: {campaign.title} (`{campaign.slug}`)",
        "- Binary image assets are not included in this export.",
        "- `Campaign Asset Path` points at the app asset file location from the export source when the source snapshot included binaries.",
        "- `Source PNG` points at the original or canon-linked vault source path when known.",
        "",
        "| Article | Section | Page Ref | Campaign Asset | Campaign Asset Path | Source PNG | Source Match |",
        "|---|---|---|---|---|---|---|",
    ]
    for image in image_associations:
        lines.append(
            "| "
            + " | ".join(
                _markdown_table_cell(value)
                for value in [
                    image["article"],
                    image["section"],
                    f"`{image['route_slug']}`",
                    (
                        f"[`{image['campaign_asset_ref']}`]({image['live_webp_asset_url']})"
                        if image["live_webp_asset_url"]
                        else f"`{image['campaign_asset_ref']}`"
                    ),
                    f"`{image['campaign_asset_path']}`" if image["campaign_asset_path"] else "",
                    f"`{image['source_png_path']}`" if image["source_png_path"] else "",
                    image["source_match"],
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_readme(campaign: Campaign) -> str:
    return f"""# {campaign.title} Campaign Export

This package is a migration-oriented export from Campaign Player Wiki.

It contains both source-shaped data and presentation-shaped data:

- `campaign/` has page metadata, Markdown, rendered HTML, navigation, visibility, and presentation rules.
- `systems/` has the campaign Systems library, sources, source policy, overrides, entries, body JSON, and rendered HTML.
- `characters/` has character definitions, imports, Fly/local state, presented JSON, Markdown sheets when supported, and per-character resolved Systems entries.
- `assets/` has metadata-only image associations and asset locations. Binary images are intentionally not copied.
- `state/sqlite-tables/` has campaign-scoped SQLite rows useful for rebuilding live/session/combat/DM-content state without auth secrets.
- `audit/` records dangling or intentionally unresolved references.
"""


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    text = "".join(json.dumps(_json_ready(row), sort_keys=True) + "\n" for row in rows)
    _write_text(path, text)


def _write_yaml(path: Path, payload: Any) -> None:
    _write_text(
        path,
        yaml.safe_dump(
            _json_ready(payload),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, datetime):
        return isoformat(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(child) for child in value]
    return value


def _loads_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _markdown_with_frontmatter(metadata: dict[str, Any], body_markdown: str) -> str:
    frontmatter = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n{body_markdown.strip()}\n"


def _safe_relative_output_path(ref: str, suffix: str) -> Path:
    pure_path = PurePosixPath(str(ref or "").strip().replace("\\", "/").strip("/"))
    parts = [part for part in pure_path.parts if part not in {"", ".", ".."}]
    if not parts:
        parts = ["index"]
    return Path(*parts).with_suffix(suffix)


def _section_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _parse_markdown_link(value: str) -> tuple[str, str]:
    match = re.match(r"^\[([^\]]*)\]\(([^)]*)\)$", value.strip())
    if not match:
        return (_strip_markdown_code(value), "")
    return match.group(1).strip(), match.group(2).strip()


def _strip_markdown_code(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1].strip()
    return stripped


def _markdown_table_cell(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|")
