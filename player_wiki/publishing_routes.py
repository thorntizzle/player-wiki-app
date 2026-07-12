from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for

from .auth import (
    can_manage_campaign_content,
    can_manage_campaign_session,
    campaign_scope_access_required,
    get_auth_store,
    get_current_user,
)
from .campaign_content_service import CampaignContentError, get_campaign_page_file, guess_campaign_asset_media_type
from .campaign_wiki_safety import build_dm_player_wiki_page_summary
from .input_limits import MAX_INGRESS_FILE_BYTES
from .models import subsection_sort_key
from .publishing_mutations import (
    PlayerWikiFormInput,
    PlayerWikiDeleteInput,
    PlayerWikiMutationDependencies,
    RawPlayerWikiImageInput,
    build_dm_player_wiki_session_article_form_data,
    create_player_wiki_page,
    delete_player_wiki_page,
    update_player_wiki_page,
    unpublish_player_wiki_page,
)
from .session_article_publisher import find_published_page_for_session_article


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


def _load_campaign(campaign_slug: str) -> Any:
    campaign = _get_repository().get_campaign(campaign_slug)
    if campaign is None:
        abort(404)
    return campaign


def _get_page_record(campaign: Any, page_ref: str) -> Any:
    try:
        record = get_campaign_page_file(
            campaign,
            page_ref,
            page_store=current_app.extensions["campaign_page_store"],
        )
    except (CampaignContentError, ValueError):
        abort(404)
    if record is None:
        abort(404)
    return record


def _mutation_dependencies() -> PlayerWikiMutationDependencies:
    return PlayerWikiMutationDependencies(
        page_store=current_app.extensions["campaign_page_store"],
        session_service=current_app.extensions["campaign_session_service"],
        character_repository=current_app.extensions["character_repository"],
        refresh_repository=current_app.extensions["repository_store"].refresh,
        write_audit_event=get_auth_store().write_audit_event,
    )


def _build_dm_content_context(campaign_slug: str, **kwargs: Any) -> dict[str, object]:
    return current_app.extensions["publishing_dm_content_context_builder"](campaign_slug, **kwargs)


def _parse_player_wiki_form() -> PlayerWikiFormInput:
    return PlayerWikiFormInput(
        title=str(request.form.get("title") or ""),
        slug_leaf=str(request.form.get("slug_leaf") or ""),
        section=str(request.form.get("section") or ""),
        page_type=str(request.form.get("page_type") or ""),
        subsection=str(request.form.get("subsection") or ""),
        summary=str(request.form.get("summary") or ""),
        aliases=str(request.form.get("aliases") or ""),
        display_order=str(request.form.get("display_order") or ""),
        reveal_after_session=str(request.form.get("reveal_after_session") or ""),
        source_ref=str(request.form.get("source_ref") or ""),
        image=str(request.form.get("image") or ""),
        image_alt=str(request.form.get("image_alt") or ""),
        image_caption=str(request.form.get("image_caption") or ""),
        body_markdown=str(request.form.get("body_markdown") or ""),
        published=str(request.form.get("published") or ""),
        source_session_article_id=str(request.form.get("source_session_article_id") or ""),
    )


def _capture_player_wiki_image() -> RawPlayerWikiImageInput | None:
    upload = request.files.get("image_file")
    if upload is None:
        return None
    stream = getattr(upload, "stream", upload)
    data_blob = stream.read(MAX_INGRESS_FILE_BYTES + 1)
    declared_length = getattr(upload, "content_length", None)
    try:
        normalized_declared_length = int(declared_length) if declared_length is not None else None
    except (TypeError, ValueError):
        normalized_declared_length = None
    return RawPlayerWikiImageInput(
        filename=str(getattr(upload, "filename", "") or ""),
        data_blob=data_blob,
        declared_length=normalized_declared_length,
    )


def _parse_player_wiki_delete_form() -> PlayerWikiDeleteInput:
    return PlayerWikiDeleteInput(
        confirm_delete=str(request.form.get("confirm_delete") or ""),
    )


def _redirect_to_player_wiki(campaign_slug: str, *, anchor: str | None = None):
    return redirect(
        url_for(
            "campaign_dm_content_subpage_view",
            campaign_slug=campaign_slug,
            dm_content_subpage="player-wiki",
            _anchor=anchor,
        )
    )


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


@campaign_scope_access_required("dm_content")
def campaign_dm_content_edit_player_wiki_page(campaign_slug: str, page_ref: str):
    if not can_manage_campaign_content(campaign_slug):
        abort(403)
    campaign = _load_campaign(campaign_slug)
    record = _get_page_record(campaign, page_ref)
    context = _build_dm_content_context(
        campaign_slug,
        dm_content_subpage="player-wiki",
        player_wiki_edit_record=record,
    )
    return render_template("dm_content.html", **context)


@campaign_scope_access_required("dm_content")
def campaign_dm_content_new_player_wiki_page_from_session_article(campaign_slug: str, article_id: int):
    if not can_manage_campaign_content(campaign_slug) or not can_manage_campaign_session(campaign_slug):
        abort(403)
    campaign = _load_campaign(campaign_slug)
    session_service = current_app.extensions["campaign_session_service"]
    article = session_service.get_article(campaign_slug, article_id)
    if article is None:
        abort(404)
    existing_page = find_published_page_for_session_article(campaign, article_id)
    if existing_page is not None:
        flash("This session article already has a wiki page. Edit the published page here.", "info")
        return redirect(
            url_for(
                "campaign_dm_content_edit_player_wiki_page",
                campaign_slug=campaign_slug,
                page_ref=existing_page.route_slug,
                _anchor="dm-content-player-wiki-editor",
            )
        )
    article_image = session_service.get_article_image(campaign_slug, article_id)
    context = _build_dm_content_context(
        campaign_slug,
        dm_content_subpage="player-wiki",
        player_wiki_form_data=build_dm_player_wiki_session_article_form_data(
            campaign,
            article,
            article_image=article_image,
        ),
    )
    return render_template("dm_content.html", **context)


@campaign_scope_access_required("dm_content")
def campaign_dm_content_create_player_wiki_page(campaign_slug: str):
    if not can_manage_campaign_content(campaign_slug):
        abort(403)
    user = get_current_user()
    if user is None:
        abort(403)
    campaign = _load_campaign(campaign_slug)
    form_data = _parse_player_wiki_form()
    if form_data.source_session_article_id.strip() and not can_manage_campaign_session(
        campaign_slug
    ):
        abort(403)
    image_upload = _capture_player_wiki_image()
    try:
        result = create_player_wiki_page(
            campaign,
            user.id,
            form_data,
            image_upload,
            _mutation_dependencies(),
        )
    except (CampaignContentError, ValueError) as exc:
        flash(str(exc), "error")
        context = _build_dm_content_context(
            campaign_slug,
            dm_content_subpage="player-wiki",
            player_wiki_form_data=form_data.as_mapping(),
        )
        return render_template("dm_content.html", **context), 400
    flash(f"Created wiki page {result.record.page.title}.", "success")
    return redirect(
        url_for(
            "campaign_dm_content_edit_player_wiki_page",
            campaign_slug=campaign_slug,
            page_ref=result.record.page_ref,
            _anchor="dm-content-player-wiki-editor",
        )
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_update_player_wiki_page(campaign_slug: str, page_ref: str):
    if not can_manage_campaign_content(campaign_slug):
        abort(403)
    user = get_current_user()
    if user is None:
        abort(403)
    campaign = _load_campaign(campaign_slug)
    existing_record = _get_page_record(campaign, page_ref)
    form_data = _parse_player_wiki_form()
    image_upload = _capture_player_wiki_image()
    try:
        result = update_player_wiki_page(
            campaign,
            user.id,
            existing_record,
            form_data,
            image_upload,
            _mutation_dependencies(),
        )
    except (CampaignContentError, ValueError) as exc:
        flash(str(exc), "error")
        context = _build_dm_content_context(
            campaign_slug,
            dm_content_subpage="player-wiki",
            player_wiki_edit_record=existing_record,
            player_wiki_form_data=form_data.as_mapping(),
        )
        return render_template("dm_content.html", **context), 400
    flash(f"Updated wiki page {result.record.page.title}.", "success")
    return redirect(
        url_for(
            "campaign_dm_content_edit_player_wiki_page",
            campaign_slug=campaign_slug,
            page_ref=result.record.page_ref,
            _anchor="dm-content-player-wiki-editor",
        )
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_unpublish_player_wiki_page(campaign_slug: str, page_ref: str):
    if not can_manage_campaign_content(campaign_slug):
        abort(403)
    user = get_current_user()
    if user is None:
        abort(403)
    campaign = _load_campaign(campaign_slug)
    existing_record = _get_page_record(campaign, page_ref)
    record = unpublish_player_wiki_page(
        campaign,
        user.id,
        existing_record,
        _mutation_dependencies(),
    )
    flash(f"Unpublished wiki page {record.page.title}.", "success")
    return _redirect_to_player_wiki(
        campaign_slug,
        anchor=f"wiki-page-{build_dm_player_wiki_page_summary(campaign, record)['dom_id']}",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_delete_player_wiki_page(campaign_slug: str, page_ref: str):
    if not can_manage_campaign_content(campaign_slug):
        abort(403)
    user = get_current_user()
    if user is None:
        abort(403)
    campaign = _load_campaign(campaign_slug)
    existing_record = _get_page_record(campaign, page_ref)
    result = delete_player_wiki_page(
        campaign,
        campaign_slug,
        user.id,
        existing_record,
        form_data=_parse_player_wiki_delete_form(),
        dependencies=_mutation_dependencies(),
    )
    if result.status == "confirmation-required":
        flash("Confirm hard delete before removing a wiki page file.", "error")
        return redirect(
            url_for(
                "campaign_dm_content_edit_player_wiki_page",
                campaign_slug=campaign_slug,
                page_ref=page_ref,
                _anchor="dm-content-player-wiki-editor",
            )
        )
    if result.status == "blocked":
        flash(
            "Hard delete blocked. Unpublish/archive the page or remove: " + " ".join(result.blockers),
            "error",
        )
        return _redirect_to_player_wiki(
            campaign_slug,
            anchor=f"wiki-page-{build_dm_player_wiki_page_summary(campaign, existing_record)['dom_id']}",
        )
    if result.status == "error":
        flash(result.error, "error")
        return _redirect_to_player_wiki(campaign_slug)
    if result.status == "not-found":
        abort(404)
    flash(f"Deleted wiki page {result.record.page.title}.", "success")
    return _redirect_to_player_wiki(campaign_slug)


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
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/edit",
            "campaign_dm_content_edit_player_wiki_page",
            campaign_dm_content_edit_player_wiki_page,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/session-articles/<int:article_id>/new",
            "campaign_dm_content_new_player_wiki_page_from_session_article",
            campaign_dm_content_new_player_wiki_page_from_session_article,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages",
            "campaign_dm_content_create_player_wiki_page",
            campaign_dm_content_create_player_wiki_page,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>",
            "campaign_dm_content_update_player_wiki_page",
            campaign_dm_content_update_player_wiki_page,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/unpublish",
            "campaign_dm_content_unpublish_player_wiki_page",
            campaign_dm_content_unpublish_player_wiki_page,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/delete",
            "campaign_dm_content_delete_player_wiki_page",
            campaign_dm_content_delete_player_wiki_page,
            ("POST",),
        ),
    )
    for registration in registrations:
        rule, endpoint, view_func, *explicit_methods = registration
        methods = explicit_methods[0] if explicit_methods else ("GET",)
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def register_publishing_routes(app: Any, *, dm_content_context_builder: Callable[..., dict[str, object]]) -> None:
    app.extensions["publishing_dm_content_context_builder"] = dm_content_context_builder
    app.register_blueprint(publishing)
