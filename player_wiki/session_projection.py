from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE, SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    parse_session_article_source_ref,
)


@dataclass(frozen=True, slots=True)
class SessionProjectionDependencies:
    session_service: Any
    list_published_pages_for_session_articles: Callable[..., Any]
    get_page_record: Callable[..., Any]
    resolve_systems_entry: Callable[..., Any]
    url_for: Callable[..., str]
    present_session_messages: Callable[..., Any]
    present_session_record: Callable[..., Any]
    present_session_articles: Callable[..., Any]
    present_session_log_summaries: Callable[..., Any]


def build_session_projection(
    campaign_slug: str, campaign: Any, *, current_user: Any, can_manage_session: bool,
    panel_scope: str, dependencies: SessionProjectionDependencies,
) -> dict[str, Any]:
    """Read and present authorized Session data without constructing Flask.

    The adapter supplies actor policy and source visibility resolvers. A DM live
    projection counts visible messages without enumerating or presenting their
    bodies; player scopes preserve their complete server-filtered history.
    Roster, passive scores and composer options remain adapter-owned and are
    omitted by the existing scope decisions returned here.
    """
    session_service = dependencies.session_service
    normalized_panel_scope = str(panel_scope or "").strip().lower()
    if normalized_panel_scope not in {
        "full_document",
        "session_fragment",
        "dm_live",
        "dm:tools",
        "dm:staged",
        "dm:revealed",
        "dm:article-store",
        "dm:logs",
    }:
        normalized_panel_scope = "full_document"
    scoped_dm_view = (
        normalized_panel_scope.split(":", 1)[1]
        if normalized_panel_scope.startswith("dm:")
        else ""
    )
    build_full_document = normalized_panel_scope == "full_document"
    build_player_panel = build_full_document or normalized_panel_scope == "session_fragment"
    build_all_manager_panels = bool(
        can_manage_session
        and (build_full_document or normalized_panel_scope == "dm_live")
    )
    build_selected_dm_panel = bool(can_manage_session and scoped_dm_view)
    build_manager_article_panels = bool(
        build_all_manager_panels or scoped_dm_view in {"staged", "revealed"}
    )
    need_articles = bool(build_player_panel or build_manager_article_panels)
    all_articles = session_service.list_articles(campaign_slug) if need_articles else []
    article_images = (
        session_service.list_article_images([article.id for article in all_articles])
        if need_articles
        else {}
    )
    converted_pages = (
        dependencies.list_published_pages_for_session_articles(
            campaign,
            [article.id for article in all_articles],
        )
        if build_manager_article_panels
        else {}
    )
    source_items: dict[int, dict[str, str]] = {}
    for article in all_articles if build_manager_article_panels else []:
        source_kind, source_ref = parse_session_article_source_ref(article.source_page_ref)
        if source_kind == SESSION_ARTICLE_SOURCE_KIND_PAGE and source_ref:
            page_record = dependencies.get_page_record(
                campaign.slug,
                source_ref,
                include_body=False,
            )
            source_items[article.id] = {
                "label": "published wiki page",
                "action_label": "View published page",
                "missing_message": "The original published wiki page is not currently visible in the player wiki.",
                "title": page_record.page.title if page_record is not None else "",
                "url": (
                    dependencies.url_for("page_view", campaign_slug=campaign.slug, page_slug=page_record.page.route_slug)
                    if page_record is not None and campaign.is_page_visible(page_record.page)
                    else ""
                ),
            }
        elif source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS and source_ref:
            systems_entry = dependencies.resolve_systems_entry(campaign_slug, source_ref)
            source_items[article.id] = {
                "label": "Systems entry",
                "action_label": "View Systems entry",
                "missing_message": "The original Systems entry is not currently visible in this campaign.",
                "title": systems_entry.title if systems_entry is not None else "",
                "url": (
                    dependencies.url_for(
                        "campaign_systems_entry_detail",
                        campaign_slug=campaign.slug,
                        entry_slug=systems_entry.slug,
                    )
                    if systems_entry is not None
                    else ""
                ),
            }
    image_url_builder = lambda article_id: dependencies.url_for(
        "campaign_session_article_image",
        campaign_slug=campaign.slug,
        article_id=article_id,
    )
    page_url_builder = lambda page_slug: dependencies.url_for(
        "page_view",
        campaign_slug=campaign.slug,
        page_slug=page_slug,
    )

    active_session_record = session_service.get_active_session(campaign_slug)
    session_messages = []
    active_session = None
    if active_session_record is not None:
        if build_player_panel:
            live_messages = session_service.list_messages(
                active_session_record.id,
                viewer_user_id=int(current_user.id if current_user else 0) or None,
                can_manage_session=can_manage_session,
            )
            session_messages = dependencies.present_session_messages(
                campaign,
                live_messages,
                all_articles,
                article_images,
                image_url_builder=image_url_builder,
            )
            visible_message_count = len(live_messages)
        else:
            visible_message_count = session_service.count_visible_messages(
                active_session_record.id,
                viewer_user_id=int(current_user.id if current_user else 0) or None,
                can_manage_session=can_manage_session,
            )
        active_session = dependencies.present_session_record(
            active_session_record,
            message_count=visible_message_count,
        )

    staged_articles = []
    revealed_articles = []
    session_logs = []
    if can_manage_session:
        build_staged_articles = bool(
            build_all_manager_panels or scoped_dm_view == "staged"
        )
        build_revealed_articles = bool(
            build_all_manager_panels or scoped_dm_view == "revealed"
        )
        build_session_logs = bool(
            build_all_manager_panels or scoped_dm_view == "logs"
        )
    else:
        build_staged_articles = False
        build_revealed_articles = False
        build_session_logs = False
    if build_staged_articles:
        staged_articles = dependencies.present_session_articles(
            campaign,
            [article for article in all_articles if not article.is_revealed],
            article_images,
            image_url_builder=image_url_builder,
            converted_pages=converted_pages,
            source_items=source_items,
            page_url_builder=page_url_builder,
        )
        for staged_article in staged_articles:
            staged_article_id = int(staged_article.get("id") or 0)
            staged_image = article_images.get(staged_article_id)
            if staged_image is None:
                staged_article.update(
                    image_updated_at="",
                    image_content_digest="",
                    image_filename="",
                    image_media_type="",
                )
                continue
            staged_image_updated_at = staged_image.updated_at.isoformat()
            staged_image_content_digest = staged_image.content_digest
            staged_image_version_payload = [
                staged_image_updated_at,
                staged_image.filename,
                staged_image.media_type,
                staged_image_content_digest,
            ]
            staged_image_version = hashlib.sha256(
                json.dumps(staged_image_version_payload, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:20]
            staged_article.update(
                image_url=dependencies.url_for(
                    "campaign_session_article_image",
                    campaign_slug=campaign.slug,
                    article_id=staged_article_id,
                    v=staged_image_version,
                ),
                image_updated_at=staged_image_updated_at,
                image_content_digest=staged_image_content_digest,
                image_filename=staged_image.filename,
                image_media_type=staged_image.media_type,
            )
    if build_revealed_articles:
        revealed_articles = dependencies.present_session_articles(
            campaign,
            [article for article in all_articles if article.is_revealed],
            article_images,
            image_url_builder=image_url_builder,
            converted_pages=converted_pages,
            source_items=source_items,
            page_url_builder=page_url_builder,
        )
    if build_session_logs:
        session_logs = dependencies.present_session_log_summaries(
            session_service.list_session_logs(campaign_slug, limit=12)
        )
    return {
        "active_session_record": active_session_record,
        "active_session": active_session,
        "session_messages": session_messages,
        "staged_articles": staged_articles,
        "revealed_articles": revealed_articles,
        "session_logs": session_logs,
        "build_full_document": build_full_document,
        "build_player_panel": build_player_panel,
        "scoped_dm_view": scoped_dm_view,
    }
