from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
)
from .systems_labels import systems_entry_type_label


@dataclass(frozen=True)
class SessionWikiArticlePayload:
    title: str
    body_markdown: str
    source_page_ref: str
    image_upload: Any | None
    legacy_image_omitted: bool = False


LEGACY_WIKI_IMAGE_OMISSION_NOTICE = (
    "The wiki page's legacy image was omitted. To include an image, convert the page image "
    "to managed form and pull again, or upload one separately to this staged article."
)


def get_pullable_session_wiki_page_record(
    campaign: Any,
    page_ref: str,
    *,
    page_store: Any,
    include_body: bool = False,
):
    from .committed_publication import active, config, current, page_row, read_snapshot

    if active():
        @read_snapshot
        def select():
            settings_source, settings = config(campaign.slug)
            try:
                row = page_row(campaign.slug, page_store.normalize_page_ref(page_ref))
            except ValueError:
                return None
            if (row is None or not row["published"]
                    or row["reveal_after_session"] > int(settings["current_session"])):
                return None
            record = page_store._map_record(row, include_body=include_body)
            if record.page.is_deprecated_wiki_overview:
                return None
            source = current(campaign.slug, "page", record.page_ref)
            if source is None:
                return None
            record.page.committed_revision = int(source["revision"])
            record.page.committed_config_revision = int(settings_source["revision"])
            # The supplied Campaign is only an identity holder in activated mode.
            # The selected projection and visibility come from this read view.
            return record

        return select()
    try:
        record = page_store.get_page_record(
            campaign.slug,
            page_ref,
            include_body=include_body,
        )
    except ValueError:
        return None
    if record is None or not campaign.is_page_visible(record.page):
        return None
    return record


def get_pullable_session_wiki_article_payload(
    campaign: Any, page_ref: str, *, page_store: Any, session_service: Any,
    get_campaign_asset_file: Callable[..., Any],
    guess_campaign_asset_media_type: Callable[..., str],
    read_bounded_file: Callable[..., bytes], max_ingress_file_bytes: int,
) -> SessionWikiArticlePayload | None:
    """Build browser/API wiki handoffs from one selected page and image proof."""
    from pathlib import Path
    from .campaign_session_service import CampaignSessionValidationError
    from .committed_publication import (
        CommittedSourceConflict, active, page_image_payload,
        read_snapshot,
    )
    from .managed_wiki_images import is_managed_wiki_asset_target

    def select():
        record = get_pullable_session_wiki_page_record(
            campaign, page_ref, page_store=page_store, include_body=True,
        )
        if record is None:
            return None
        managed_image = None
        asset_ref = record.page.image_path
        managed_target = bool(
            asset_ref and activated
            and is_managed_wiki_asset_target(campaign.assets_dir, asset_ref)
        )
        if managed_target:
            managed_image = page_image_payload(
                campaign.slug, record.page_ref, record.page.committed_revision,
                record.page.committed_config_revision, asset_ref,
            )
        return record, managed_image, bool(asset_ref and activated and not managed_target)

    try:
        activated = active()
        if activated:
            @read_snapshot
            def committed_select():
                return select()

            selected = committed_select()
        else:
            selected = select()
    except CommittedSourceConflict as exc:
        raise CampaignSessionValidationError(str(exc)) from exc

    if selected is None:
        return None
    record, managed_image, legacy_image_omitted = selected
    image_upload = None
    asset_ref = record.page.image_path
    if managed_image is not None:
        data_blob, media_type = managed_image
        image_upload = session_service.prepare_article_image_upload(
            filename=Path(asset_ref).name, media_type=media_type,
            data_blob=data_blob, alt_text=record.page.image_alt,
            caption=record.page.image_caption,
        )
    elif asset_ref and not activated:
        image_path = get_campaign_asset_file(campaign, asset_ref)
        if image_path is not None:
            image_upload = session_service.prepare_article_image_upload(
                filename=image_path.name,
                media_type=guess_campaign_asset_media_type(image_path),
                data_blob=read_bounded_file(
                    image_path, max_bytes=max_ingress_file_bytes,
                    message="Wiki page images must stay under 8 MB.",
                ),
                alt_text=record.page.image_alt,
                caption=record.page.image_caption,
            )
    body = record.body_markdown.strip() or record.page.summary.strip()
    if not body and image_upload is None:
        if legacy_image_omitted:
            raise CampaignSessionValidationError(
                "This wiki page has only a legacy image, which cannot be pulled into a session article. "
                "Convert the page image to managed form and pull again, or create a manual "
                "Session article with a separate image upload."
            )
        raise CampaignSessionValidationError(
            "The selected wiki page does not have any body text, summary, or image to pull into the session store."
        )
    return SessionWikiArticlePayload(
        title=record.page.title, body_markdown=body,
        source_page_ref=build_session_article_page_source_ref(record.page_ref),
        image_upload=image_upload,
        legacy_image_omitted=legacy_image_omitted,
    )


def get_pullable_session_systems_entry(
    campaign_slug: str,
    entry_slug: str,
    *,
    systems_service: Any,
    can_access_systems: bool,
    can_access_systems_entry: Callable[[str], bool],
):
    normalized_entry_slug = str(entry_slug or "").strip()
    if not normalized_entry_slug:
        return None
    if not can_access_systems:
        return None

    entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, normalized_entry_slug)
    if entry is None or not can_access_systems_entry(entry.slug):
        return None
    return entry


def build_session_article_source_search_results(
    *,
    campaign: Any,
    campaign_slug: str,
    query: str,
    page_store: Any,
    systems_service: Any,
    can_access_systems: bool,
    can_access_systems_entry: Callable[[str], bool],
    systems_search_visibilities: tuple[str, ...],
    limit: int = 30,
) -> list[dict[str, str]]:
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        return []

    results: list[dict[str, str]] = []
    page_records = page_store.search_page_records(
        campaign.slug,
        normalized_query,
        limit=max(limit, 1),
        include_body=False,
        current_session=campaign.current_session,
    )
    for record in page_records:
        if not campaign.is_page_visible(record.page):
            continue
        context_parts = [record.page.section]
        if record.page.subsection:
            context_parts.append(record.page.subsection)
        context_label = " / ".join(part for part in context_parts if part)
        results.append(
            {
                "source_ref": build_session_article_page_source_ref(record.page_ref),
                "source_kind": SESSION_ARTICLE_SOURCE_KIND_PAGE,
                "title": record.page.title,
                "subtitle": context_label,
                "kind_label": "Wiki",
                "select_label": f"{record.page.title} - Wiki - {context_label}",
            }
        )
        if len(results) >= limit:
            return results

    if can_access_systems:
        systems_entries = systems_service.search_entries_for_campaign(
            campaign_slug,
            query=normalized_query,
            limit=max(limit - len(results), 1),
            visible_to=systems_search_visibilities,
        )
        for entry in systems_entries:
            if not can_access_systems_entry(entry.slug):
                continue
            entry_type_label = systems_entry_type_label(entry.entry_type)
            results.append(
                {
                    "source_ref": build_session_article_systems_source_ref(entry.slug),
                    "source_kind": SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
                    "title": entry.title,
                    "subtitle": f"{entry_type_label} - {entry.source_id}",
                    "kind_label": "Systems",
                    "select_label": f"{entry.title} - Systems - {entry_type_label} - {entry.source_id}",
                }
            )
            if len(results) >= limit:
                break

    return results
