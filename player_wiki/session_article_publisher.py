from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .campaign_content_service import write_campaign_page_file
from .campaign_page_store import CampaignPageStore
from .models import Campaign, Page, SECTION_ORDER
from .publisher import summarize_body
from .repository import slugify
from .session_models import SessionArticleImageRecord, SessionArticleRecord

SESSION_ARTICLE_SOURCE_REF_PREFIX = "session-article:"

SESSION_ARTICLE_SECTION_TARGETS = {
    "Overview": {"target_subdir": "overview", "page_type": "page"},
    "Sessions": {"target_subdir": "sessions", "page_type": "session"},
    "Notes": {"target_subdir": "notes", "page_type": "note"},
    "Locations": {"target_subdir": "locations", "page_type": "location"},
    "NPCs": {"target_subdir": "npcs", "page_type": "npc"},
    "Races": {"target_subdir": "races", "page_type": "race"},
    "Factions": {"target_subdir": "factions", "page_type": "faction"},
    "Gods": {"target_subdir": "gods", "page_type": "god"},
    "Discoveries": {"target_subdir": "discoveries", "page_type": "discovery"},
    "Items": {"target_subdir": "items", "page_type": "item"},
    "Spells": {"target_subdir": "spells", "page_type": "spell"},
    "Mechanics": {"target_subdir": "mechanics", "page_type": "mechanic"},
    "Lore": {"target_subdir": "lore", "page_type": "lore"},
}


class SessionArticlePublishError(ValueError):
    pass


@dataclass(slots=True)
class SessionArticlePublishOptions:
    title: str
    slug_leaf: str
    summary: str
    section: str
    page_type: str
    subsection: str
    reveal_after_session: int


@dataclass(slots=True)
class SessionArticlePublishResult:
    destination_path: Path
    route_slug: str
    asset_relative_path: str | None


def build_session_article_source_ref(campaign_slug: str, article_id: int) -> str:
    return f"{SESSION_ARTICLE_SOURCE_REF_PREFIX}{campaign_slug}:{article_id}"


def find_published_page_for_session_article(campaign: Campaign, article_id: int) -> Page | None:
    source_ref = build_session_article_source_ref(campaign.slug, article_id)
    for page in campaign.pages.values():
        if page.source_ref == source_ref:
            return page
    return None


def list_published_pages_for_session_articles(
    campaign: Campaign,
    article_ids: list[int],
) -> dict[int, Page]:
    normalized_ids = {int(article_id) for article_id in article_ids if int(article_id) > 0}
    if not normalized_ids:
        return {}

    prefix = f"{SESSION_ARTICLE_SOURCE_REF_PREFIX}{campaign.slug}:"
    pages_by_article_id: dict[int, Page] = {}
    for page in campaign.pages.values():
        if not page.source_ref.startswith(prefix):
            continue
        article_id_text = page.source_ref[len(prefix) :].strip()
        if not article_id_text.isdigit():
            continue
        article_id = int(article_id_text)
        if article_id in normalized_ids:
            pages_by_article_id[article_id] = page
    return pages_by_article_id


def build_default_publish_options(
    campaign: Campaign,
    article: SessionArticleRecord,
) -> SessionArticlePublishOptions:
    slug_leaf = slugify(article.title).split("/")[-1]
    if not slug_leaf:
        slug_leaf = f"session-article-{article.id}"

    target = SESSION_ARTICLE_SECTION_TARGETS["Notes"]
    return SessionArticlePublishOptions(
        title=article.title,
        slug_leaf=slug_leaf,
        summary=summarize_body(article.body_markdown),
        section="Notes",
        page_type=str(target["page_type"]),
        subsection="",
        reveal_after_session=campaign.current_session,
    )


def list_section_choices() -> list[dict[str, str]]:
    labels = sorted(
        SESSION_ARTICLE_SECTION_TARGETS,
        key=lambda item: (SECTION_ORDER.get(item, 1000), item.lower()),
    )
    return [
        {
            "label": label,
            "default_page_type": str(SESSION_ARTICLE_SECTION_TARGETS[label]["page_type"]),
        }
        for label in labels
    ]


def normalize_publish_options(
    *,
    title: str,
    slug_leaf: str,
    summary: str,
    section: str,
    page_type: str,
    subsection: str,
    reveal_after_session: str | int,
) -> SessionArticlePublishOptions:
    normalized_title = (title or "").strip()
    if not normalized_title:
        raise SessionArticlePublishError("Wiki pages need a title before they can be published.")
    if len(normalized_title) > 200:
        raise SessionArticlePublishError("Wiki page titles must stay under 200 characters.")

    normalized_slug_leaf = slugify(slug_leaf or "").split("/")[-1]
    if not normalized_slug_leaf:
        raise SessionArticlePublishError("Choose a page slug before publishing this article.")

    normalized_section = (section or "").strip()
    if normalized_section not in SESSION_ARTICLE_SECTION_TARGETS:
        raise SessionArticlePublishError("Choose a supported wiki section for the published page.")

    normalized_page_type = re.sub(r"[^a-z0-9]+", "-", (page_type or "").strip().lower()).strip("-")
    if not normalized_page_type:
        raise SessionArticlePublishError("Enter a page type for the published wiki page.")

    normalized_summary = (summary or "").strip()
    if len(normalized_summary) > 400:
        raise SessionArticlePublishError("Wiki page summaries must stay under 400 characters.")

    normalized_subsection = (subsection or "").strip()

    try:
        normalized_reveal_after_session = int(reveal_after_session)
    except (TypeError, ValueError) as exc:
        raise SessionArticlePublishError("Enter a valid session number for the published page.") from exc
    if normalized_reveal_after_session < 0:
        raise SessionArticlePublishError("Reveal-after-session must be zero or greater.")

    return SessionArticlePublishOptions(
        title=normalized_title,
        slug_leaf=normalized_slug_leaf,
        summary=normalized_summary,
        section=normalized_section,
        page_type=normalized_page_type,
        subsection=normalized_subsection,
        reveal_after_session=normalized_reveal_after_session,
    )


def publish_session_article(
    campaign: Campaign,
    article: SessionArticleRecord,
    *,
    article_image: SessionArticleImageRecord | None,
    options: SessionArticlePublishOptions,
    page_store: CampaignPageStore,
) -> SessionArticlePublishResult:
    existing_page = find_published_page_for_session_article(campaign, article.id)
    if existing_page is not None:
        raise SessionArticlePublishError("This session article has already been converted into wiki content.")

    target = SESSION_ARTICLE_SECTION_TARGETS.get(options.section)
    if target is None:
        raise SessionArticlePublishError("Choose a supported wiki section for the published page.")

    route_slug = f"{target['target_subdir']}/{options.slug_leaf}"
    if route_slug in campaign.pages:
        raise SessionArticlePublishError("That wiki page slug is already in use. Choose a different slug.")

    destination_path = Path(campaign.player_content_dir) / str(target["target_subdir"]) / f"{options.slug_leaf}.md"
    if destination_path.exists():
        raise SessionArticlePublishError("That wiki page file already exists. Choose a different slug.")

    metadata: dict[str, object] = {
        "title": options.title,
        "slug": route_slug,
        "section": options.section,
        "type": options.page_type,
        "summary": options.summary,
        "reveal_after_session": options.reveal_after_session,
        "source_ref": build_session_article_source_ref(campaign.slug, article.id),
        "published": True,
    }
    if options.subsection:
        metadata["subsection"] = options.subsection

    asset_relative_path: str | None = None
    asset_path: Path | None = None
    try:
        if article_image is not None:
            suffix = Path(article_image.filename).suffix.lower() or ".bin"
            asset_relative_path = f"session-articles/article-{article.id}-{options.slug_leaf}{suffix}"
            asset_path = Path(campaign.assets_dir) / asset_relative_path
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(article_image.data_blob)

            metadata["image"] = asset_relative_path.replace("\\", "/")
            if article_image.alt_text:
                metadata["image_alt"] = article_image.alt_text
            if article_image.caption:
                metadata["image_caption"] = article_image.caption

        written_page = write_campaign_page_file(
            campaign,
            route_slug,
            metadata=metadata,
            body_markdown=article.body_markdown.strip(),
            page_store=page_store,
        )
    except Exception:
        if asset_path is not None and asset_path.exists() and not destination_path.exists():
            asset_path.unlink()
        raise

    return SessionArticlePublishResult(
        destination_path=written_page.file_path,
        route_slug=route_slug,
        asset_relative_path=asset_relative_path,
    )
