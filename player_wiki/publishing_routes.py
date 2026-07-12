from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, abort, current_app, render_template, send_from_directory, url_for

from .auth import campaign_scope_access_required
from .campaign_content_service import guess_campaign_asset_media_type
from .models import subsection_sort_key


publishing = Blueprint("publishing", __name__)


def resolve_campaign_asset_file(campaign: Any, asset_path: str) -> Path | None:
    """Resolve an existing campaign asset without allowing traversal outside its root."""

    normalized_asset_path = asset_path.strip().replace("\\", "/")
    if not normalized_asset_path:
        return None

    assets_root = Path(campaign.assets_dir).resolve()
    candidate = (assets_root / normalized_asset_path).resolve()
    if assets_root not in candidate.parents and candidate != assets_root:
        return None
    if not candidate.is_file():
        return None
    return candidate


def build_section_view_context(
    repository: Any,
    campaign_slug: str,
    section_slug: str,
) -> dict[str, Any] | None:
    campaign = repository.get_campaign(campaign_slug)
    if campaign is None:
        return None

    pages = repository.get_section_pages(campaign_slug, section_slug)
    if not pages:
        return None

    top_level_pages = [page for page in pages if not page.subsection]
    subsection_groups: dict[str, list[Any]] = defaultdict(list)
    for page in pages:
        if page.subsection:
            subsection_groups[page.subsection].append(page)

    ordered_subsection_groups = [
        (subsection_name, subsection_groups[subsection_name])
        for subsection_name in sorted(
            subsection_groups,
            key=lambda subsection_name: subsection_sort_key(pages[0].section, subsection_name),
        )
    ]
    return {
        "campaign": campaign,
        "section_name": pages[0].section,
        "pages": pages,
        "top_level_pages": top_level_pages,
        "subsection_groups": ordered_subsection_groups,
        "show_subsections": bool(subsection_groups),
        "active_nav": "wiki",
    }


def build_page_view_context(
    repository: Any,
    campaign_slug: str,
    page_slug: str,
    *,
    build_asset_url: Callable[[Any, str], str],
) -> dict[str, Any] | None:
    campaign = repository.get_campaign(campaign_slug)
    if campaign is None:
        return None

    page = repository.get_page(campaign_slug, page_slug)
    if page is None:
        return None

    backlinks = repository.get_backlinks(campaign_slug, page_slug)
    body_html = repository.get_page_body_html(campaign_slug, page_slug)
    if body_html is None:
        return None
    body_html = body_html.replace(
        "/campaigns/{campaign_slug}/",
        f"/campaigns/{campaign.slug}/",
    )

    page_image_url = None
    if page.image_path and resolve_campaign_asset_file(campaign, page.image_path) is not None:
        page_image_url = build_asset_url(campaign, page.image_path)

    return {
        "campaign": campaign,
        "page": page,
        "body_html": body_html,
        "page_image_url": page_image_url,
        "backlinks": backlinks,
        "active_nav": "wiki",
    }


def _get_repository() -> Any:
    return current_app.extensions["repository_store"].get()


@campaign_scope_access_required("wiki")
def campaign_asset(campaign_slug: str, asset_path: str):
    campaign = _get_repository().get_campaign(campaign_slug)
    if campaign is None:
        abort(404)

    asset_file = resolve_campaign_asset_file(campaign, asset_path)
    if asset_file is None:
        abort(404)

    return send_from_directory(
        asset_file.parent,
        asset_file.name,
        mimetype=guess_campaign_asset_media_type(asset_file),
    )


@campaign_scope_access_required("wiki")
def section_view(campaign_slug: str, section_slug: str):
    context = build_section_view_context(_get_repository(), campaign_slug, section_slug)
    if context is None:
        abort(404)
    return render_template("section.html", **context)


@campaign_scope_access_required("wiki")
def page_view(campaign_slug: str, page_slug: str):
    context = build_page_view_context(
        _get_repository(),
        campaign_slug,
        page_slug,
        build_asset_url=lambda campaign, asset_path: url_for(
            "campaign_asset",
            campaign_slug=campaign.slug,
            asset_path=asset_path,
        ),
    )
    if context is None:
        abort(404)
    return render_template("page.html", **context)


@publishing.record_once
def _register_legacy_endpoints(state: Any) -> None:
    """Register supported legacy endpoint IDs without duplicate Blueprint aliases."""

    registrations = (
        (
            "/campaigns/<campaign_slug>/assets/<path:asset_path>",
            "campaign_asset",
            campaign_asset,
        ),
        (
            "/campaigns/<campaign_slug>/sections/<section_slug>",
            "section_view",
            section_view,
        ),
        (
            "/campaigns/<campaign_slug>/pages/<path:page_slug>",
            "page_view",
            page_view,
        ),
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=("GET",))


def register_publishing_routes(app: Any) -> None:
    app.register_blueprint(publishing)
