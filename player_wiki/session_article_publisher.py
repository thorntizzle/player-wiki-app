from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterator

from .campaign_content_service import prepare_campaign_page_write
from .campaign_page_store import CampaignPageStore
from .db import get_db
from .image_publish import prepare_published_article_image
from .models import Campaign, Page, SECTION_ORDER
from .player_wiki_reconciliation import (
    PlayerWikiCreateConflict,
    PlayerWikiReconciler,
    PreparedManagedImage,
)
from .publisher import summarize_body
from .repository import parse_frontmatter, slugify
from .session_models import SessionArticleImageRecord, SessionArticleRecord

SESSION_ARTICLE_SOURCE_REF_PREFIX = "session-article:"

_conversion_locks_guard = Lock()
_conversion_locks: dict[tuple[str, int], Lock] = {}
_RENDERED_FRONTMATTER_ENVELOPE = re.compile(
    r"\A---\n.*?\n---\n(?:\n|\Z)",
    re.DOTALL,
)

SESSION_ARTICLE_SECTION_TARGETS = {
    "Sessions": {"target_subdir": "sessions", "page_type": "session"},
    "Notes": {"target_subdir": "notes", "page_type": "note"},
    "Bestiary": {"target_subdir": "bestiary", "page_type": "monster"},
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


class SessionArticleAlreadyPublishedError(SessionArticlePublishError):
    pass


class SessionArticleReconciliationRepairError(SessionArticlePublishError):
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


@contextmanager
def session_article_conversion_lock(
    campaign_slug: str,
    article_id: int,
) -> Iterator[None]:
    key = (str(campaign_slug), int(article_id))
    with _conversion_locks_guard:
        lock = _conversion_locks.setdefault(key, Lock())
    with lock:
        yield


def _find_persisted_page_for_session_article(
    campaign_slug: str,
    article_id: int,
    *,
    page_store: CampaignPageStore,
):
    source_ref = build_session_article_source_ref(campaign_slug, article_id)
    for record in page_store.list_page_records(campaign_slug, include_body=False):
        if record.page.source_ref == source_ref:
            return record
    return None


def _has_active_persisted_provenance(campaign_slug: str, source_ref: str) -> bool:
    rows = get_db().execute(
        """
        SELECT desired_markdown
        FROM player_wiki_reconciliation_operations
        WHERE campaign_slug = ?
          AND state IN ('prepared', 'conflict')
        """,
        (campaign_slug,),
    ).fetchall()
    for row in rows:
        desired_markdown = row["desired_markdown"]
        if desired_markdown is None:
            continue
        try:
            rendered_markdown = bytes(desired_markdown).decode("utf-8", errors="strict")
            normalized_markdown = rendered_markdown.replace("\r\n", "\n")
            if _RENDERED_FRONTMATTER_ENVELOPE.match(normalized_markdown) is None:
                raise ValueError("untrusted recovery frontmatter envelope")
            metadata, _body_markdown = parse_frontmatter(rendered_markdown)
            if not isinstance(metadata, dict):
                raise ValueError("invalid reconciliation metadata")
            active_source_ref = metadata.get("source_ref")
            if not isinstance(active_source_ref, str) or not active_source_ref.strip():
                raise ValueError("untrusted reconciliation provenance")
        except Exception:
            raise SessionArticleReconciliationRepairError(
                "Player wiki reconciliation requires repair before converting this session article."
            ) from None
        if active_source_ref.strip() == source_ref:
            return True
    return False


def ensure_session_article_conversion_available(
    campaign_slug: str,
    article_id: int,
    *,
    page_store: CampaignPageStore,
) -> None:
    source_ref = build_session_article_source_ref(campaign_slug, article_id)
    if _find_persisted_page_for_session_article(
        campaign_slug,
        article_id,
        page_store=page_store,
    ) is not None or _has_active_persisted_provenance(campaign_slug, source_ref):
        raise SessionArticleAlreadyPublishedError(
            "This session article has already been converted into wiki content."
        )


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
    reconciler: PlayerWikiReconciler,
) -> SessionArticlePublishResult:
    target = SESSION_ARTICLE_SECTION_TARGETS.get(options.section)
    if target is None:
        raise SessionArticlePublishError("Choose a supported wiki section for the published page.")
    route_slug = f"{target['target_subdir']}/{options.slug_leaf}"

    with session_article_conversion_lock(campaign.slug, article.id):
        source_ref = build_session_article_source_ref(campaign.slug, article.id)
        ensure_session_article_conversion_available(
            campaign.slug,
            article.id,
            page_store=page_store,
        )

        if page_store.get_page_record(campaign.slug, route_slug, include_body=False) is not None:
            raise SessionArticlePublishError("That wiki page slug is already in use. Choose a different slug.")

        destination_path = (
            Path(campaign.player_content_dir)
            / str(target["target_subdir"])
            / f"{options.slug_leaf}.md"
        )
        if destination_path.exists():
            raise SessionArticlePublishError("That wiki page file already exists. Choose a different slug.")

        metadata: dict[str, object] = {
            "title": options.title,
            "slug": route_slug,
            "section": options.section,
            "type": options.page_type,
            "summary": options.summary,
            "reveal_after_session": options.reveal_after_session,
            "source_ref": source_ref,
            "published": True,
        }
        if options.subsection:
            metadata["subsection"] = options.subsection

        asset_relative_path: str | None = None
        prepared_image: PreparedManagedImage | None = None
        if article_image is not None:
            image_filename, image_data = prepare_published_article_image(
                filename=article_image.filename,
                data_blob=article_image.data_blob,
            )
            asset_relative_path = (
                f"session-articles/article-{article.id}-{options.slug_leaf}{Path(image_filename).suffix.lower()}"
            )
            asset_path = Path(campaign.assets_dir) / asset_relative_path
            prepared_image = PreparedManagedImage(
                asset_ref=asset_relative_path,
                file_path=asset_path,
                data_blob=image_data,
            )

            metadata["image"] = asset_relative_path.replace("\\", "/")
            if article_image.alt_text:
                metadata["image_alt"] = article_image.alt_text
            if article_image.caption:
                metadata["image_caption"] = article_image.caption

        prepared_page = prepare_campaign_page_write(
            campaign,
            route_slug,
            metadata=metadata,
            body_markdown=article.body_markdown.strip(),
            page_store=page_store,
        )
        try:
            written_page = reconciler.mutate(
                campaign,
                prepared_page,
                operation_kind="create",
                prepared_image=prepared_image,
                audit_event_type=None,
            )
        except PlayerWikiCreateConflict as exc:
            raise SessionArticlePublishError(
                "That wiki page slug is already in use. Choose a different slug."
            ) from exc

        return SessionArticlePublishResult(
            destination_path=written_page.file_path,
            route_slug=route_slug,
            asset_relative_path=asset_relative_path,
        )
