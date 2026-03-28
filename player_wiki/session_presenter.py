from __future__ import annotations

import markdown

from .models import Campaign
from .repository import build_alias_index, render_obsidian_links
from .session_models import (
    CampaignSessionRecord,
    CampaignSessionSummary,
    SessionArticleImageRecord,
    SessionArticleRecord,
    SessionMessageRecord,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    parse_session_article_source_ref,
)


def format_session_timestamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def render_session_article_html(campaign: Campaign, body_markdown: str) -> str:
    alias_index = build_alias_index(campaign)
    resolved_links: list[str] = []
    linked_markdown = render_obsidian_links(body_markdown, alias_index, resolved_links)
    body_html = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(linked_markdown)
    return body_html.replace("/campaigns/{campaign_slug}/", f"/campaigns/{campaign.slug}/")


def render_presented_session_article_body(campaign: Campaign, article: SessionArticleRecord) -> str:
    source_kind, _ = parse_session_article_source_ref(article.source_page_ref)
    if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
        return article.body_markdown
    return render_session_article_html(campaign, article.body_markdown)


def present_session_record(session_record: CampaignSessionRecord, *, message_count: int) -> dict[str, object]:
    return {
        "id": session_record.id,
        "status": session_record.status,
        "is_active": session_record.is_active,
        "started_at_label": format_session_timestamp(session_record.started_at),
        "ended_at_label": format_session_timestamp(session_record.ended_at) if session_record.ended_at else "",
        "message_count": message_count,
    }


def present_session_articles(
    campaign: Campaign,
    articles: list[SessionArticleRecord],
    article_images: dict[int, SessionArticleImageRecord],
    *,
    image_url_builder,
    converted_pages: dict[int, object] | None = None,
    source_items: dict[int, dict[str, object]] | None = None,
    page_url_builder=None,
) -> list[dict[str, object]]:
    presented_articles: list[dict[str, object]] = []
    converted_pages = converted_pages or {}
    source_items = source_items or {}

    for article in articles:
        image = article_images.get(article.id)
        converted_page = converted_pages.get(article.id)
        converted_page_is_visible = campaign.is_page_visible(converted_page) if converted_page is not None else False
        source_item = source_items.get(article.id, {})
        source_kind, _ = parse_session_article_source_ref(article.source_page_ref)
        presented_articles.append(
            {
                "id": article.id,
                "title": article.title,
                "status": article.status,
                "created_at_label": format_session_timestamp(article.created_at),
                "revealed_at_label": format_session_timestamp(article.revealed_at) if article.revealed_at else "",
                "revealed_in_session_id": article.revealed_in_session_id,
                "source_page_ref": article.source_page_ref,
                "source_kind": source_kind,
                "source_title": str(source_item.get("title") or ""),
                "source_label": str(source_item.get("label") or ""),
                "source_url": str(source_item.get("url") or ""),
                "source_action_label": str(source_item.get("action_label") or ""),
                "source_missing_message": str(source_item.get("missing_message") or ""),
                "body_html": render_presented_session_article_body(campaign, article),
                "image_url": image_url_builder(article.id) if image is not None else "",
                "image_alt": (image.alt_text or article.title) if image is not None else "",
                "image_caption": image.caption if image is not None else "",
                "converted_page_title": converted_page.title if converted_page is not None else "",
                "converted_page_is_visible": converted_page_is_visible,
                "converted_page_reveal_after_session": (
                    converted_page.reveal_after_session if converted_page is not None else None
                ),
                "converted_page_url": (
                    page_url_builder(converted_page.route_slug)
                    if converted_page is not None and converted_page_is_visible and page_url_builder is not None
                    else ""
                ),
            }
        )

    return presented_articles


def present_session_messages(
    campaign: Campaign,
    messages: list[SessionMessageRecord],
    articles: list[SessionArticleRecord],
    article_images: dict[int, SessionArticleImageRecord],
    *,
    image_url_builder,
) -> list[dict[str, object]]:
    article_lookup = {article.id: article for article in articles}
    presented_messages: list[dict[str, object]] = []

    for message in messages:
        article = article_lookup.get(message.article_id or -1)
        article_image = article_images.get(article.id) if article is not None else None
        presented_messages.append(
            {
                "id": message.id,
                "message_type": message.message_type,
                "author_label": message.author_display_name,
                "timestamp_label": format_session_timestamp(message.created_at),
                "body_text": message.body_text,
                "kind_label": (
                    "Revealed article" if message.message_type == "article_reveal" else message.message_type.title()
                ),
                "article_title": article.title if article is not None else "",
                "article_html": render_presented_session_article_body(campaign, article) if article is not None else "",
                "article_image_url": image_url_builder(article.id) if article is not None and article_image is not None else "",
                "article_image_alt": (
                    article_image.alt_text or article.title
                    if article is not None and article_image is not None
                    else ""
                ),
                "article_image_caption": article_image.caption if article_image is not None else "",
            }
        )

    return presented_messages


def present_session_log_summaries(
    summaries: list[CampaignSessionSummary],
) -> list[dict[str, object]]:
    return [
        {
            "id": summary.session.id,
            "started_at_label": format_session_timestamp(summary.session.started_at),
            "ended_at_label": format_session_timestamp(summary.session.ended_at) if summary.session.ended_at else "",
            "message_count": summary.message_count,
            "last_message_at_label": format_session_timestamp(summary.last_message_at) if summary.last_message_at else "",
        }
        for summary in summaries
    ]
