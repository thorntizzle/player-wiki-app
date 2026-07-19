from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .campaign_content_service import (
    CampaignContentError,
    get_campaign_page_file,
    list_campaign_page_files,
    prepare_campaign_page_write,
)
from .campaign_wiki_safety import build_dm_player_wiki_removal_safety_index
from .campaign_session_service import ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS
from .image_publish import prepare_published_article_image
from .input_limits import IngressLimitError, MAX_INGRESS_FILE_BYTES, validate_markdown_value
from .repository import slugify
from .player_wiki_reconciliation import PlayerWikiCreateConflict, PreparedManagedImage
from .session_article_publisher import (
    SESSION_ARTICLE_SECTION_TARGETS,
    SessionArticleAlreadyPublishedError,
    build_default_publish_options,
    build_session_article_source_ref,
    ensure_session_article_conversion_available,
    session_article_conversion_lock,
)


@dataclass(frozen=True)
class PlayerWikiFormInput:
    title: str = ""
    slug_leaf: str = ""
    section: str = ""
    page_type: str = ""
    subsection: str = ""
    summary: str = ""
    aliases: str = ""
    display_order: str = ""
    reveal_after_session: str = ""
    source_ref: str = ""
    image: str = ""
    image_alt: str = ""
    image_caption: str = ""
    body_markdown: str = ""
    published: str = ""
    source_session_article_id: str = ""

    def as_mapping(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RawPlayerWikiImageInput:
    filename: str
    data_blob: bytes
    declared_length: int | None


@dataclass(frozen=True)
class PlayerWikiDeleteInput:
    confirm_delete: str = ""


@dataclass(frozen=True)
class _ValidatedPlayerWikiImage:
    filename: str
    data_blob: bytes


@dataclass(frozen=True)
class PlayerWikiMutationDependencies:
    page_store: Any
    session_service: Any
    character_repository: Any
    refresh_repository: Callable[[], None]
    write_audit_event: Callable[..., None]
    reconciler: Any | None = None


@dataclass(frozen=True)
class PlayerWikiCreateResult:
    record: Any
    uploaded_image_asset_ref: str
    copied_session_article_image_asset_ref: str
    source_session_article_id: int | None


@dataclass(frozen=True)
class PlayerWikiUpdateResult:
    record: Any
    uploaded_image_asset_ref: str


@dataclass(frozen=True)
class PlayerWikiDeleteResult:
    status: str
    record: Any | None = None
    blockers: tuple[str, ...] = ()
    error: str = ""


def parse_dm_player_wiki_aliases(value: str) -> list[str]:
    aliases = []
    for line in str(value or "").replace(",", "\n").splitlines():
        alias = line.strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def _normalize_nonnegative_int(value: str, *, field_label: str, default: int = 0) -> int:
    raw_value = str(value or "").strip()
    if not raw_value:
        return default
    try:
        normalized_value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_label} must be a whole number.") from exc
    if normalized_value < 0:
        raise ValueError(f"{field_label} must be zero or greater.")
    return normalized_value


def normalize_dm_player_wiki_page_type(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Page type is required.")
    return normalized


def build_dm_player_wiki_form(campaign: Any, *, record: Any = None, form_data: Mapping[str, Any] | None = None) -> dict[str, object]:
    data = form_data if form_data is not None else {}
    if data:
        return {
            "title": str(data.get("title") or ""),
            "slug_leaf": str(data.get("slug_leaf") or ""),
            "section": str(data.get("section") or "Notes"),
            "page_type": str(data.get("page_type") or "note"),
            "subsection": str(data.get("subsection") or ""),
            "summary": str(data.get("summary") or ""),
            "aliases": str(data.get("aliases") or ""),
            "display_order": str(data.get("display_order") or "10000"),
            "reveal_after_session": str(data.get("reveal_after_session") or campaign.current_session),
            "source_ref": str(data.get("source_ref") or ""),
            "image": str(data.get("image") or ""),
            "image_alt": str(data.get("image_alt") or ""),
            "image_caption": str(data.get("image_caption") or ""),
            "body_markdown": str(data.get("body_markdown") or ""),
            "published": str(data.get("published") or "") == "1",
            "source_session_article_id": str(data.get("source_session_article_id") or ""),
        }

    if record is not None:
        page = record.page
        metadata = dict(record.metadata or {})
        return {
            "title": page.title,
            "slug_leaf": record.page_ref.rsplit("/", 1)[-1],
            "section": page.section,
            "page_type": page.page_type,
            "subsection": page.subsection,
            "summary": page.summary,
            "aliases": "\n".join(page.aliases),
            "display_order": str(page.display_order),
            "reveal_after_session": str(page.reveal_after_session),
            "source_ref": page.source_ref,
            "image": page.image_path,
            "image_alt": page.image_alt,
            "image_caption": page.image_caption,
            "body_markdown": record.body_markdown,
            "published": bool(metadata.get("published", page.published)),
            "source_session_article_id": "",
        }

    target = SESSION_ARTICLE_SECTION_TARGETS["Notes"]
    return {
        "title": "",
        "slug_leaf": "",
        "section": "Notes",
        "page_type": str(target["page_type"]),
        "subsection": "",
        "summary": "",
        "aliases": "",
        "display_order": "10000",
        "reveal_after_session": str(campaign.current_session),
        "source_ref": "",
        "image": "",
        "image_alt": "",
        "image_caption": "",
        "body_markdown": "",
        "published": True,
        "source_session_article_id": "",
    }


def normalize_dm_player_wiki_form(campaign: Any, *, form_data: PlayerWikiFormInput, existing_record: Any = None) -> tuple[str, dict[str, object], str]:
    title = form_data.title.strip()
    if not title:
        raise ValueError("Wiki pages need a title.")
    if len(title) > 200:
        raise ValueError("Wiki page titles must stay under 200 characters.")

    section = form_data.section.strip()
    if section not in SESSION_ARTICLE_SECTION_TARGETS:
        raise ValueError("Choose a supported wiki section.")

    page_type = normalize_dm_player_wiki_page_type(form_data.page_type)
    summary = form_data.summary.strip()
    if len(summary) > 400:
        raise ValueError("Wiki page summaries must stay under 400 characters.")

    display_order = _normalize_nonnegative_int(form_data.display_order, field_label="Display order", default=10_000)
    reveal_after_session = _normalize_nonnegative_int(
        form_data.reveal_after_session,
        field_label="Reveal after session",
        default=campaign.current_session,
    )
    body_markdown = form_data.body_markdown.strip()
    validate_markdown_value(body_markdown)
    published = form_data.published == "1"

    if existing_record is None:
        slug_leaf = slugify(form_data.slug_leaf)
        if not slug_leaf:
            raise ValueError("Choose a page slug before saving this wiki page.")
        target = SESSION_ARTICLE_SECTION_TARGETS[section]
        page_ref = f"{target['target_subdir']}/{slug_leaf}"
        metadata: dict[str, object] = {"slug": page_ref}
    else:
        page_ref = existing_record.page_ref
        metadata = dict(existing_record.metadata or {})
        metadata.setdefault("slug", existing_record.page.route_slug or existing_record.page_ref)

    metadata.update(
        {
            "title": title,
            "section": section,
            "type": page_type,
            "summary": summary,
            "aliases": parse_dm_player_wiki_aliases(form_data.aliases),
            "display_order": display_order,
            "reveal_after_session": reveal_after_session,
            "published": published,
        }
    )
    optional_text_fields = {
        "subsection": form_data.subsection.strip(),
        "source_ref": form_data.source_ref.strip(),
        "image": form_data.image.strip(),
        "image_alt": form_data.image_alt.strip(),
        "image_caption": form_data.image_caption.strip(),
    }
    for key, value in optional_text_fields.items():
        if value:
            metadata[key] = value
        else:
            metadata.pop(key, None)
    return page_ref, metadata, body_markdown


def build_dm_player_wiki_image_asset_ref(page_ref: str, extension: str) -> str:
    normalized_page_ref = slugify(page_ref).strip("/") or "wiki-page"
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    return f"wiki-pages/{normalized_page_ref}{normalized_extension.lower()}"


def _validate_player_wiki_image_upload(
    raw_upload: RawPlayerWikiImageInput | None,
) -> _ValidatedPlayerWikiImage | None:
    if raw_upload is None:
        return None
    filename = Path(raw_upload.filename.strip()).name
    if not filename:
        return None
    if Path(filename).suffix.lower() not in ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS:
        raise ValueError("Wiki page images must be PNG, JPG, GIF, or WEBP files.")
    if (
        raw_upload.declared_length is not None
        and raw_upload.declared_length > MAX_INGRESS_FILE_BYTES
    ) or len(raw_upload.data_blob) > MAX_INGRESS_FILE_BYTES:
        raise IngressLimitError("Wiki page images must stay under 8 MB.")
    if not raw_upload.data_blob:
        raise ValueError("Uploaded wiki page images cannot be empty.")
    return _ValidatedPlayerWikiImage(filename=filename, data_blob=raw_upload.data_blob)


def prepare_dm_player_wiki_image_upload(
    campaign: Any,
    page_ref: str,
    metadata: dict[str, object],
    raw_upload: RawPlayerWikiImageInput | None,
) -> PreparedManagedImage | None:
    upload = _validate_player_wiki_image_upload(raw_upload)
    if upload is None:
        return None
    converted_filename, data_blob = prepare_published_article_image(upload.filename, upload.data_blob)
    asset_ref = build_dm_player_wiki_image_asset_ref(page_ref, Path(converted_filename).suffix)
    metadata["image"] = asset_ref
    return PreparedManagedImage(
        asset_ref=asset_ref,
        file_path=Path(campaign.assets_dir) / Path(*asset_ref.split("/")),
        data_blob=data_blob,
    )


def normalize_dm_player_wiki_source_session_article_id(value: object) -> int | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        article_id = int(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError("Session article provenance is invalid.") from exc
    if article_id <= 0:
        raise ValueError("Session article provenance is invalid.")
    return article_id


def build_dm_player_wiki_session_article_form_data(campaign: Any, article: Any, article_image: Any = None) -> dict[str, object]:
    default_options = build_default_publish_options(campaign, article)
    return {
        "title": default_options.title,
        "slug_leaf": default_options.slug_leaf,
        "section": default_options.section,
        "page_type": default_options.page_type,
        "subsection": default_options.subsection,
        "summary": default_options.summary,
        "aliases": "",
        "display_order": "10000",
        "reveal_after_session": str(default_options.reveal_after_session),
        "source_ref": build_session_article_source_ref(campaign.slug, article.id),
        "image": "",
        "image_alt": article_image.alt_text if article_image is not None else "",
        "image_caption": article_image.caption if article_image is not None else "",
        "body_markdown": article.body_markdown,
        "published": "1",
        "source_session_article_id": str(article.id),
    }


def prepare_dm_player_wiki_session_article_image(
    campaign: Any,
    page_ref: str,
    metadata: dict[str, object],
    article_image: Any,
) -> PreparedManagedImage | None:
    if article_image is None or metadata.get("image"):
        return None
    if len(article_image.data_blob) > MAX_INGRESS_FILE_BYTES:
        raise ValueError("Session article images must stay under 8 MB.")
    converted_filename, data_blob = prepare_published_article_image(article_image.filename, article_image.data_blob)
    asset_ref = build_dm_player_wiki_image_asset_ref(page_ref, Path(converted_filename).suffix)
    metadata["image"] = asset_ref
    return PreparedManagedImage(
        asset_ref=asset_ref,
        file_path=Path(campaign.assets_dir) / Path(*asset_ref.split("/")),
        data_blob=data_blob,
    )


def create_player_wiki_page(campaign: Any, actor_user_id: int, form_data: PlayerWikiFormInput, image_upload: RawPlayerWikiImageInput | None, dependencies: PlayerWikiMutationDependencies) -> PlayerWikiCreateResult:
    page_ref, metadata, body_markdown = normalize_dm_player_wiki_form(campaign, form_data=form_data)
    source_session_article_id = normalize_dm_player_wiki_source_session_article_id(form_data.source_session_article_id)
    conversion_lock = (
        session_article_conversion_lock(campaign.slug, source_session_article_id)
        if source_session_article_id is not None
        else nullcontext()
    )
    with conversion_lock:
        source_session_article_image = None
        if source_session_article_id is not None:
            session_article = dependencies.session_service.get_article(
                campaign.slug,
                source_session_article_id,
            )
            if session_article is None:
                raise ValueError("The source session article could not be found.")
            try:
                ensure_session_article_conversion_available(
                    campaign.slug,
                    source_session_article_id,
                    page_store=dependencies.page_store,
                )
            except SessionArticleAlreadyPublishedError as exc:
                raise ValueError(
                    "This session article already has a wiki page. Edit that page instead."
                ) from exc
            metadata["source_ref"] = build_session_article_source_ref(
                campaign.slug,
                source_session_article_id,
            )
            source_session_article_image = dependencies.session_service.get_article_image(
                campaign.slug,
                source_session_article_id,
            )
        existing_record = get_campaign_page_file(campaign, page_ref, page_store=dependencies.page_store)
        if existing_record is not None:
            raise ValueError("That page slug is already in use. Choose a different slug.")
        prepared_image = prepare_dm_player_wiki_image_upload(
            campaign,
            page_ref,
            metadata,
            image_upload,
        )
        uploaded_image_asset_ref = prepared_image.asset_ref if prepared_image is not None else ""
        copied_session_article_image_asset_ref = ""
        if prepared_image is None:
            prepared_image = prepare_dm_player_wiki_session_article_image(
                campaign,
                page_ref,
                metadata,
                source_session_article_image,
            )
            if prepared_image is not None:
                copied_session_article_image_asset_ref = prepared_image.asset_ref
        prepared_page = prepare_campaign_page_write(
            campaign,
            page_ref,
            metadata=metadata,
            body_markdown=body_markdown,
            page_store=dependencies.page_store,
        )
        if dependencies.reconciler is None:
            raise RuntimeError("Player wiki forward reconciliation is not configured.")
        audit_metadata = {
            "page_ref": prepared_page.page_ref,
            "route_slug": prepared_page.route_slug,
            "source": "dm_content_player_wiki",
            "uploaded_image_asset_ref": uploaded_image_asset_ref,
            "copied_session_article_image_asset_ref": copied_session_article_image_asset_ref,
            "source_session_article_id": source_session_article_id,
        }
        try:
            record = dependencies.reconciler.mutate(
                campaign,
                prepared_page,
                operation_kind="create",
                prepared_image=prepared_image,
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=actor_user_id,
                audit_metadata=audit_metadata,
            )
        except PlayerWikiCreateConflict as exc:
            raise ValueError("That page slug is already in use. Choose a different slug.") from exc
        return PlayerWikiCreateResult(
            record,
            uploaded_image_asset_ref,
            copied_session_article_image_asset_ref,
            source_session_article_id,
        )


def update_player_wiki_page(campaign: Any, actor_user_id: int, existing_record: Any, form_data: PlayerWikiFormInput, image_upload: RawPlayerWikiImageInput | None, dependencies: PlayerWikiMutationDependencies) -> PlayerWikiUpdateResult:
    page_ref, metadata, body_markdown = normalize_dm_player_wiki_form(
        campaign, form_data=form_data, existing_record=existing_record
    )
    prepared_image = prepare_dm_player_wiki_image_upload(
        campaign,
        page_ref,
        metadata,
        image_upload,
    )
    uploaded_image_asset_ref = prepared_image.asset_ref if prepared_image is not None else ""
    prepared_page = prepare_campaign_page_write(
        campaign,
        page_ref,
        metadata=metadata,
        body_markdown=body_markdown,
        page_store=dependencies.page_store,
    )
    if dependencies.reconciler is None:
        raise RuntimeError("Player wiki forward reconciliation is not configured.")
    record = dependencies.reconciler.mutate(
        campaign,
        prepared_page,
        operation_kind="update",
        prepared_image=prepared_image,
        audit_event_type="campaign_wiki_page_updated",
        audit_actor_user_id=actor_user_id,
        audit_metadata={
            "page_ref": prepared_page.page_ref,
            "route_slug": prepared_page.route_slug,
            "source": "dm_content_player_wiki",
            "uploaded_image_asset_ref": uploaded_image_asset_ref,
        },
    )
    return PlayerWikiUpdateResult(record, uploaded_image_asset_ref)


def unpublish_player_wiki_page(campaign: Any, actor_user_id: int, existing_record: Any, dependencies: PlayerWikiMutationDependencies) -> Any:
    metadata = dict(existing_record.metadata or {})
    metadata["published"] = False
    prepared_page = prepare_campaign_page_write(
        campaign,
        existing_record.page_ref,
        metadata=metadata,
        body_markdown=existing_record.body_markdown,
        page_store=dependencies.page_store,
    )
    if dependencies.reconciler is None:
        raise RuntimeError("Player wiki forward reconciliation is not configured.")
    record = dependencies.reconciler.mutate(
        campaign,
        prepared_page,
        operation_kind="unpublish",
        audit_event_type="campaign_wiki_page_unpublished",
        audit_actor_user_id=actor_user_id,
        audit_metadata={
            "page_ref": prepared_page.page_ref,
            "route_slug": prepared_page.route_slug,
            "source": "dm_content_player_wiki",
        },
    )
    return record


def delete_player_wiki_page(campaign: Any, campaign_slug: str, actor_user_id: int, existing_record: Any, *, form_data: PlayerWikiDeleteInput, dependencies: PlayerWikiMutationDependencies) -> PlayerWikiDeleteResult:
    if form_data.confirm_delete != "1":
        return PlayerWikiDeleteResult("confirmation-required", record=existing_record)
    records = list_campaign_page_files(campaign, page_store=dependencies.page_store)
    safety = build_dm_player_wiki_removal_safety_index(
        campaign_slug,
        campaign,
        records,
        session_articles=dependencies.session_service.list_articles(campaign_slug),
        character_records=dependencies.character_repository.list_characters(campaign_slug),
    ).get(existing_record.page_ref, {})
    blockers = tuple(safety.get("hard_delete_blockers", []) or [])
    if blockers:
        return PlayerWikiDeleteResult("blocked", record=existing_record, blockers=blockers)
    if dependencies.reconciler is None:
        raise RuntimeError("Player wiki forward reconciliation is not configured.")
    try:
        deleted = dependencies.reconciler.delete(
            campaign,
            existing_record,
            operation_kind="browser_delete",
            audit_event_type="campaign_wiki_page_deleted",
            audit_actor_user_id=actor_user_id,
            audit_metadata={
                "page_ref": existing_record.page_ref,
                "route_slug": existing_record.page.route_slug,
                "source": "dm_content_player_wiki",
            },
        )
    except CampaignContentError as exc:
        return PlayerWikiDeleteResult("error", record=existing_record, error=str(exc))
    if deleted is None:
        return PlayerWikiDeleteResult("not-found")
    return PlayerWikiDeleteResult("deleted", record=deleted)
