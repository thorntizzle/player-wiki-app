from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from .db import get_db

from .auth import get_auth_store
from .auth_store import AuthStore
from .campaign_session_store import CampaignSessionConflictError, CampaignSessionStore
from .input_limits import MAX_INGRESS_FILE_BYTES, MAX_MARKDOWN_BYTES, validate_markdown_value
from .repository import normalize_lookup, parse_frontmatter, title_from_slug
from .rich_text import sanitize_rich_markdown
from .session_models import (
    CampaignSessionCloseoutOpenResult,
    CampaignSessionCloseoutRecord,
    CampaignSessionCloseoutSummary,
    CampaignSessionRecord,
    CampaignSessionReadinessSummary,
    CampaignSessionSummary,
    SessionArticleImageRecord,
    SessionArticleRecord,
    SessionMessageRecord,
    SESSION_CLOSEOUT_ITEM_KEYS,
    SESSION_CLOSEOUT_ITEM_STATUSES,
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
    SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
    SESSION_CLOSEOUT_STATUS_COMPLETED,
    SESSION_CLOSEOUT_STATUS_OPEN,
    normalize_session_article_source_ref,
)


class CampaignSessionValidationError(ValueError):
    pass


ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
ALLOWED_SESSION_ARTICLE_MARKDOWN_EXTENSIONS = {".markdown", ".md"}
SESSION_ARTICLE_TITLE_HEADING_PATTERN = re.compile(r"^\s{0,3}#\s+(?P<title>.*?)\s*#*\s*$")
SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+\"(?P<title>[^\"]*)\")?\)"
)
SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN = re.compile(
    r"!\[\[(?P<target>[^\]|#]+)(?:#[^\]|]*)?(?:\|(?P<label>[^\]]+))?\]\]"
)

SESSION_MESSAGE_AUDIENCE_SCOPE_GLOBAL = "global"
SESSION_MESSAGE_AUDIENCE_SCOPE_DM_ONLY = "dm_only"
SESSION_MESSAGE_AUDIENCE_SCOPE_PLAYER = "player"

SESSION_MESSAGE_AUDIENCE_SCOPES = {
    SESSION_MESSAGE_AUDIENCE_SCOPE_GLOBAL,
    SESSION_MESSAGE_AUDIENCE_SCOPE_DM_ONLY,
    SESSION_MESSAGE_AUDIENCE_SCOPE_PLAYER,
}


@dataclass(slots=True)
class SessionArticleMarkdownUpload:
    title: str
    body_markdown: str
    image_reference: str = ""
    image_alt: str = ""
    image_caption: str = ""


@dataclass(slots=True)
class SessionArticleImageUpload:
    filename: str
    media_type: str
    data_blob: bytes
    alt_text: str = ""
    caption: str = ""


def extract_session_article_title_heading(markdown_text: str) -> tuple[str, str]:
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    line_index = 0
    while line_index < len(lines) and not lines[line_index].strip():
        line_index += 1

    if line_index >= len(lines):
        return "", markdown_text.strip()

    match = SESSION_ARTICLE_TITLE_HEADING_PATTERN.match(lines[line_index])
    if match is None:
        return "", markdown_text.strip()

    title = match.group("title").strip()
    if not title:
        return "", markdown_text.strip()

    body_lines = lines[line_index + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return title, "\n".join(body_lines).strip()


def strip_markdown_image_token(markdown_text: str, start: int, end: int) -> str:
    updated_text = markdown_text[:start] + markdown_text[end:]
    updated_text = re.sub(r"\n{3,}", "\n\n", updated_text)
    return updated_text.strip()


def normalize_image_reference(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized.startswith("<") and normalized.endswith(">"):
        normalized = normalized[1:-1].strip()
    return normalized.replace("\\", "/")


def normalize_obsidian_image_label(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if re.fullmatch(r"\d+(?:x\d+)?", normalized):
        return ""
    return normalized


def extract_markdown_image_reference(markdown_text: str) -> tuple[SessionArticleMarkdownUpload, str]:
    obsidian_match = SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN.search(markdown_text)
    markdown_match = SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN.search(markdown_text)

    chosen_kind = ""
    chosen_match = None
    if obsidian_match is not None and markdown_match is not None:
        if obsidian_match.start() <= markdown_match.start():
            chosen_kind = "obsidian"
            chosen_match = obsidian_match
        else:
            chosen_kind = "markdown"
            chosen_match = markdown_match
    elif obsidian_match is not None:
        chosen_kind = "obsidian"
        chosen_match = obsidian_match
    elif markdown_match is not None:
        chosen_kind = "markdown"
        chosen_match = markdown_match

    if chosen_match is None:
        return SessionArticleMarkdownUpload(title="", body_markdown=markdown_text.strip()), markdown_text.strip()

    image_reference = normalize_image_reference(chosen_match.group("target"))
    if not image_reference:
        return SessionArticleMarkdownUpload(title="", body_markdown=markdown_text.strip()), markdown_text.strip()

    if chosen_kind == "obsidian":
        image_alt = normalize_obsidian_image_label(chosen_match.group("label") or "")
        image_caption = ""
    else:
        image_alt = str(chosen_match.group("alt") or "").strip()
        image_caption = str(chosen_match.group("title") or "").strip()

    stripped_body = strip_markdown_image_token(markdown_text, chosen_match.start(), chosen_match.end())
    return (
        SessionArticleMarkdownUpload(
            title="",
            body_markdown=stripped_body,
            image_reference=image_reference,
            image_alt=image_alt,
            image_caption=image_caption,
        ),
        stripped_body,
    )


def strip_matching_body_image_reference(markdown_text: str, image_reference: str) -> str:
    normalized_reference = normalize_image_reference(image_reference)
    if not normalized_reference:
        return markdown_text.strip()

    normalized_basename = Path(normalized_reference).name.lower()
    for pattern in (SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN, SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN):
        for match in pattern.finditer(markdown_text):
            target = normalize_image_reference(match.group("target"))
            if not target:
                continue
            if target == normalized_reference or Path(target).name.lower() == normalized_basename:
                return strip_markdown_image_token(markdown_text, match.start(), match.end())
    return markdown_text.strip()


class CampaignSessionService:
    def __init__(self, store: CampaignSessionStore) -> None:
        self.store = store

    def _normalize_article_fields(
        self,
        *,
        title: str,
        body_markdown: str,
        has_content_image: bool = False,
    ) -> tuple[str, str]:
        try:
            validate_markdown_value(body_markdown)
        except ValueError as exc:
            raise CampaignSessionValidationError(str(exc)) from exc
        normalized_title = (title or "").strip()
        normalized_body = sanitize_rich_markdown(body_markdown).strip()
        if not normalized_title:
            raise CampaignSessionValidationError("Session articles need a title.")
        if not normalized_body and not has_content_image:
            raise CampaignSessionValidationError("Session articles need body text or an image before they can be saved.")
        if len(normalized_title) > 200:
            raise CampaignSessionValidationError("Session article titles must stay under 200 characters.")
        if len(normalized_body) > 40_000:
            raise CampaignSessionValidationError("Session articles must stay under 40,000 characters.")
        return normalized_title, normalized_body

    def prepare_article_image_upload(
        self,
        *,
        filename: str,
        media_type: str | None,
        data_blob: bytes,
        alt_text: str = "",
        caption: str = "",
    ) -> SessionArticleImageUpload:
        normalized_filename = Path(filename or "").name.strip()
        if not normalized_filename:
            raise CampaignSessionValidationError("Choose an image file before saving the session article.")

        extension = Path(normalized_filename).suffix.lower()
        allowed_media_type = ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS.get(extension)
        if allowed_media_type is None:
            raise CampaignSessionValidationError(
                "Session article images must be PNG, JPG, GIF, or WEBP files."
            )

        normalized_media_type = (media_type or "").strip().lower() or allowed_media_type
        if normalized_media_type != allowed_media_type:
            normalized_media_type = allowed_media_type

        if not data_blob:
            raise CampaignSessionValidationError("Uploaded image files cannot be empty.")
        if len(data_blob) > MAX_INGRESS_FILE_BYTES:
            raise CampaignSessionValidationError("Session article images must stay under 8 MB.")

        return SessionArticleImageUpload(
            filename=normalized_filename,
            media_type=normalized_media_type,
            data_blob=data_blob,
            alt_text=(alt_text or "").strip(),
            caption=(caption or "").strip(),
        )

    def get_live_revision(self, campaign_slug: str) -> int:
        return self.store.get_live_revision(campaign_slug)

    def get_readiness_summary(
        self,
        campaign_slug: str,
        *,
        count_limit: int = 26,
    ) -> CampaignSessionReadinessSummary:
        return self.store.get_readiness_summary(
            campaign_slug,
            count_limit=count_limit,
        )

    def bump_live_state_revision(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> None:
        self.store.bump_state_revision(
            campaign_slug,
            updated_by_user_id=updated_by_user_id,
            commit=commit,
        )

    def get_active_session(self, campaign_slug: str) -> CampaignSessionRecord | None:
        return self.store.get_active_session(campaign_slug)

    def get_session_log(self, campaign_slug: str, session_id: int) -> CampaignSessionRecord | None:
        return self.store.get_session(campaign_slug, session_id)

    def get_article(self, campaign_slug: str, article_id: int) -> SessionArticleRecord | None:
        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            return None
        return article

    def list_session_logs(self, campaign_slug: str, *, limit: int = 10) -> list[CampaignSessionSummary]:
        return self.store.list_session_summaries(campaign_slug, statuses=("closed",), limit=limit)

    def list_articles(
        self,
        campaign_slug: str,
        *,
        statuses: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> list[SessionArticleRecord]:
        return self.store.list_articles(campaign_slug, statuses=statuses, limit=limit)

    def list_article_images(self, article_ids: list[int]) -> dict[int, SessionArticleImageRecord]:
        return self.store.list_article_images(article_ids)

    def get_article_image(self, campaign_slug: str, article_id: int) -> SessionArticleImageRecord | None:
        if self.get_article(campaign_slug, article_id) is None:
            return None
        return self.store.get_article_image(article_id)

    def list_messages(
        self,
        session_id: int,
        *,
        viewer_user_id: int | None = None,
        can_manage_session: bool = False,
    ) -> list[SessionMessageRecord]:
        return self.store.list_messages(
            session_id,
            viewer_user_id=viewer_user_id,
            include_private_messages=can_manage_session,
        )

    def count_visible_messages(
        self,
        session_id: int,
        *,
        viewer_user_id: int | None = None,
        can_manage_session: bool = False,
    ) -> int:
        return self.store.count_messages(
            session_id,
            viewer_user_id=viewer_user_id,
            include_private_messages=can_manage_session,
        )

    def build_session_message_recipient(
        self,
        campaign_slug: str,
        *,
        recipient_scope: str,
        recipient_user_id: int | str | None = None,
    ) -> tuple[str, int | None]:
        normalized_scope = str(recipient_scope or SESSION_MESSAGE_AUDIENCE_SCOPE_GLOBAL).strip().lower()
        if normalized_scope not in SESSION_MESSAGE_AUDIENCE_SCOPES:
            raise CampaignSessionValidationError(
                "Message audience must be global, dm_only, or player."
            )
        if normalized_scope != SESSION_MESSAGE_AUDIENCE_SCOPE_PLAYER:
            return normalized_scope, None

        if recipient_user_id is None:
            raise CampaignSessionValidationError("Choose a player when sending a targeted player message.")
        if isinstance(recipient_user_id, bool):
            raise CampaignSessionValidationError("Choose a valid player for the targeted message.")

        try:
            selected_user_id = int(recipient_user_id)
        except (TypeError, ValueError):
            raise CampaignSessionValidationError("Choose a valid player for the targeted message.")
        if selected_user_id <= 0:
            raise CampaignSessionValidationError("Choose a valid player for the targeted message.")

        store = get_auth_store()
        membership = store.get_membership(selected_user_id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            raise CampaignSessionValidationError("Choose an active campaign player for the targeted message.")

        return normalized_scope, selected_user_id

    def begin_session(
        self,
        campaign_slug: str,
        *,
        started_by_user_id: int | None = None,
    ) -> CampaignSessionRecord:
        if self.store.get_active_session(campaign_slug) is not None:
            raise CampaignSessionValidationError("A live session is already running for this campaign.")
        with get_db() as connection:
            session_record = self.store.create_session(
                campaign_slug,
                started_by_user_id=started_by_user_id,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=started_by_user_id,
                commit=False,
            )
        return session_record

    def close_session(
        self,
        campaign_slug: str,
        *,
        ended_by_user_id: int | None = None,
    ) -> CampaignSessionRecord:
        active_session = self.store.get_active_session(campaign_slug)
        if active_session is None:
            raise CampaignSessionValidationError("There is no active session to close.")
        with get_db() as connection:
            session_record = self.store.close_session(
                campaign_slug,
                active_session.id,
                ended_by_user_id=ended_by_user_id,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=ended_by_user_id,
                commit=False,
            )
        return session_record

    def delete_session_log(
        self,
        campaign_slug: str,
        session_id: int,
        *,
        updated_by_user_id: int | None = None,
    ) -> None:
        session_record = self.store.get_session(campaign_slug, session_id)
        if session_record is None:
            raise CampaignSessionValidationError("That chat log could not be found.")
        if session_record.is_active:
            raise CampaignSessionValidationError("Close the live session before deleting its chat log.")
        if self.store.has_closeout(campaign_slug, session_id):
            raise CampaignSessionValidationError(
                "This session has closeout records. Use confirmed Session-history deletion instead."
            )

        try:
            with get_db() as connection:
                self.store.delete_session(campaign_slug, session_id, commit=False)
                self.store.bump_state_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That chat log could not be deleted. Refresh the page and try again."
            ) from exc

    def post_message(
        self,
        campaign_slug: str,
        *,
        body_text: str,
        author_display_name: str,
        author_user_id: int | None = None,
        recipient_scope: str = SESSION_MESSAGE_AUDIENCE_SCOPE_GLOBAL,
        recipient_user_id: int | None = None,
    ) -> SessionMessageRecord:
        normalized_body = (body_text or "").strip()
        if not normalized_body:
            raise CampaignSessionValidationError("Enter a message before posting it to the chat.")
        if len(normalized_body) > 4000:
            raise CampaignSessionValidationError("Session chat messages must stay under 4,000 characters.")

        active_session = self.store.get_active_session(campaign_slug)
        if active_session is None:
            raise CampaignSessionValidationError("The chat window opens when the DM begins a session.")

        normalized_scope, normalized_recipient_user_id = self.build_session_message_recipient(
            campaign_slug,
            recipient_scope=recipient_scope,
            recipient_user_id=recipient_user_id,
        )

        with get_db() as connection:
            message = self.store.create_message(
                active_session.id,
                campaign_slug,
                message_type="chat",
                body_text=normalized_body,
                author_display_name=author_display_name,
                author_user_id=author_user_id,
                recipient_scope=normalized_scope,
                recipient_user_id=normalized_recipient_user_id,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=author_user_id,
                commit=False,
            )
        return message

    def create_article(
        self,
        campaign_slug: str,
        *,
        title: str,
        body_markdown: str,
        source_page_ref: str = "",
        has_content_image: bool = False,
        created_by_user_id: int | None = None,
    ) -> SessionArticleRecord:
        normalized_title, normalized_body = self._normalize_article_fields(
            title=title,
            body_markdown=body_markdown,
            has_content_image=has_content_image,
        )
        normalized_source_page_ref = normalize_session_article_source_ref(source_page_ref)
        if len(normalized_source_page_ref) > 400:
            raise CampaignSessionValidationError("Session article source references must stay under 400 characters.")

        with get_db() as connection:
            article = self.store.create_article(
                campaign_slug,
                title=normalized_title,
                body_markdown=normalized_body,
                source_page_ref=normalized_source_page_ref,
                created_by_user_id=created_by_user_id,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=created_by_user_id,
                commit=False,
            )
        return article

    def update_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        title: str,
        body_markdown: str,
        has_content_image: bool = False,
        updated_by_user_id: int | None = None,
    ) -> SessionArticleRecord:
        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionValidationError("That session article could not be found.")
        if article.is_revealed:
            raise CampaignSessionValidationError(
                "Revealed session articles cannot be edited in the prep queue."
            )

        normalized_title, normalized_body = self._normalize_article_fields(
            title=title,
            body_markdown=body_markdown,
            has_content_image=has_content_image,
        )
        try:
            with get_db() as connection:
                updated_article = self.store.update_article(
                    campaign_slug,
                    article_id,
                    title=normalized_title,
                    body_markdown=normalized_body,
                    commit=False,
                )
                self.store.bump_state_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be updated. Refresh the page and try again."
            ) from exc
        return updated_article

    def parse_article_markdown_upload(
        self,
        *,
        filename: str,
        data_blob: bytes,
    ) -> SessionArticleMarkdownUpload:
        normalized_filename = Path(filename or "").name.strip()
        if not normalized_filename:
            raise CampaignSessionValidationError("Choose a markdown file before saving the session article.")

        extension = Path(normalized_filename).suffix.lower()
        if extension not in ALLOWED_SESSION_ARTICLE_MARKDOWN_EXTENSIONS:
            raise CampaignSessionValidationError(
                "Session article uploads must be Markdown files with .md or .markdown extensions."
            )

        if len(data_blob) > MAX_MARKDOWN_BYTES:
            raise CampaignSessionValidationError("Session article markdown files must stay under 1 MB.")
        if not data_blob:
            raise CampaignSessionValidationError("Uploaded markdown files cannot be empty.")

        try:
            raw_text = data_blob.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CampaignSessionValidationError("Uploaded markdown files must be valid UTF-8 text.") from exc

        try:
            metadata, body_markdown = parse_frontmatter(raw_text)
        except yaml.YAMLError as exc:
            raise CampaignSessionValidationError("Uploaded markdown frontmatter must be valid YAML.") from exc

        if not isinstance(metadata, dict):
            raise CampaignSessionValidationError("Uploaded markdown frontmatter must be a YAML object.")

        fallback_title = title_from_slug(Path(normalized_filename).stem)
        normalized_title = str(metadata.get("title") or "").strip()
        normalized_body = body_markdown.strip()
        heading_title, body_without_heading = extract_session_article_title_heading(normalized_body)
        image_reference = normalize_image_reference(metadata.get("image", ""))
        image_alt = str(metadata.get("image_alt") or "").strip()
        image_caption = str(metadata.get("image_caption") or "").strip()

        if normalized_title:
            if heading_title and normalize_lookup(heading_title) == normalize_lookup(normalized_title):
                normalized_body = body_without_heading
        elif heading_title:
            normalized_title = heading_title
            normalized_body = body_without_heading
        else:
            normalized_title = fallback_title

        if image_reference:
            normalized_body = strip_matching_body_image_reference(normalized_body, image_reference)
        else:
            extracted_image, stripped_body = extract_markdown_image_reference(normalized_body)
            image_reference = extracted_image.image_reference
            image_alt = image_alt or extracted_image.image_alt
            image_caption = image_caption or extracted_image.image_caption
            normalized_body = stripped_body

        return SessionArticleMarkdownUpload(
            title=normalized_title,
            body_markdown=normalized_body,
            image_reference=image_reference,
            image_alt=image_alt,
            image_caption=image_caption,
        )

    def delete_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        updated_by_user_id: int | None = None,
    ) -> SessionArticleRecord:
        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionValidationError("That session article could not be found.")

        try:
            with get_db() as connection:
                deleted_article = self.store.delete_article(
                    campaign_slug,
                    article_id,
                    commit=False,
                )
                self.store.bump_state_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be deleted. Refresh the page and try again."
            ) from exc
        return deleted_article

    def delete_revealed_articles(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> list[SessionArticleRecord]:
        revealed_articles = self.store.list_articles(campaign_slug, statuses=("revealed",))
        deleted_articles: list[SessionArticleRecord] = []
        try:
            with get_db() as connection:
                for article in revealed_articles:
                    deleted_article = self.store.delete_article(
                        campaign_slug,
                        article.id,
                        commit=False,
                    )
                    deleted_articles.append(deleted_article)
                if deleted_articles:
                    self.store.bump_state_revision(
                        campaign_slug,
                        updated_by_user_id=updated_by_user_id,
                        commit=False,
                    )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be deleted. Refresh the page and try again."
            ) from exc
        return deleted_articles

    def attach_article_image(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        filename: str,
        media_type: str | None,
        data_blob: bytes,
        alt_text: str = "",
        caption: str = "",
        updated_by_user_id: int | None = None,
    ) -> SessionArticleImageRecord:
        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionValidationError("That session article could not be found.")

        image_upload = self.prepare_article_image_upload(
            filename=filename,
            media_type=media_type,
            data_blob=data_blob,
            alt_text=alt_text,
            caption=caption,
        )

        with get_db() as connection:
            image = self.store.upsert_article_image(
                article_id,
                filename=image_upload.filename,
                media_type=image_upload.media_type,
                data_blob=image_upload.data_blob,
                alt_text=image_upload.alt_text,
                caption=image_upload.caption,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
                commit=False,
            )
        return image

    def update_article_image_metadata(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        alt_text: str = "",
        caption: str = "",
        updated_by_user_id: int | None = None,
    ) -> SessionArticleImageRecord:
        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionValidationError("That session article could not be found.")
        if article.is_revealed:
            raise CampaignSessionValidationError(
                "Revealed session article images cannot be edited in the prep queue."
            )
        if self.store.get_article_image(article_id) is None:
            raise CampaignSessionValidationError("That session article does not have an image to update.")

        try:
            with get_db() as connection:
                image = self.store.update_article_image_metadata(
                    article_id,
                    alt_text=(alt_text or "").strip(),
                    caption=(caption or "").strip(),
                    commit=False,
                )
                self.store.bump_state_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article image could not be updated. Refresh the page and try again."
            ) from exc
        return image

    def reveal_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        revealed_by_user_id: int | None = None,
        author_display_name: str,
    ) -> tuple[SessionArticleRecord, SessionMessageRecord]:
        active_session = self.store.get_active_session(campaign_slug)
        if active_session is None:
            raise CampaignSessionValidationError("Begin a session before revealing articles in the chat.")

        article = self.store.get_article(article_id)
        if article is None or article.campaign_slug != campaign_slug:
            raise CampaignSessionValidationError("That session article could not be found.")
        if article.is_revealed:
            raise CampaignSessionValidationError("That session article has already been revealed.")

        try:
            with get_db() as connection:
                article_record, message_record = self.store.reveal_article_in_session(
                    article_id,
                    campaign_slug=campaign_slug,
                    session_id=active_session.id,
                    revealed_by_user_id=revealed_by_user_id,
                    author_display_name=author_display_name,
                    commit=False,
                )
                self.store.bump_state_revision(
                    campaign_slug,
                    updated_by_user_id=revealed_by_user_id,
                    commit=False,
                )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be revealed. Refresh the page and try again."
            ) from exc
        return article_record, message_record


MAX_SESSION_CLOSEOUT_NOTE_CHARACTERS = 500
MAX_SESSION_CLOSEOUT_NOTE_BYTES = 2_000
MAX_SESSION_CLOSEOUT_SUMMARIES = 26


class CampaignSessionCloseoutAuthorizationError(PermissionError):
    """The effective request identity may not access Session closeout state."""


class CampaignSessionCloseoutValidationError(ValueError):
    """Session closeout input or lifecycle state is invalid."""


class CampaignSessionCloseoutConflictError(RuntimeError):
    """Session closeout state changed after the caller's expected revision."""


@dataclass(frozen=True, slots=True)
class CampaignSessionCloseoutAuthorizationContext:
    campaign_slug: str
    actor_user_id: int | None
    can_manage_campaign_content: bool
    can_manage_session: bool
    is_view_as: bool = False
    is_read_only: bool = False


CampaignSessionCloseoutAuthorizationAdapter = Callable[
    [str], CampaignSessionCloseoutAuthorizationContext
]


class CampaignSessionCloseoutService:
    def __init__(
        self,
        store: CampaignSessionStore,
        auth_store: AuthStore,
        *,
        authorization_adapter: CampaignSessionCloseoutAuthorizationAdapter,
        pre_commit_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.auth_store = auth_store
        self._authorization_adapter = authorization_adapter
        self._pre_commit_hook = pre_commit_hook

    def get_closeout(
        self,
        campaign_slug: str,
        session_id: Any,
    ) -> CampaignSessionCloseoutRecord | None:
        self._authorize(campaign_slug, mutation=False)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        session_record = self.store.get_session(campaign_slug, parsed_session_id)
        if session_record is None:
            return None
        closeout = self.store.get_closeout(campaign_slug, parsed_session_id)
        if closeout is not None:
            self._validate_closeout_shape(closeout)
        return closeout

    def list_summaries(
        self,
        campaign_slug: str,
        *,
        limit: Any = MAX_SESSION_CLOSEOUT_SUMMARIES,
    ) -> list[CampaignSessionCloseoutSummary]:
        self._authorize(campaign_slug, mutation=False)
        parsed_limit = self._parse_positive_int("limit", limit)
        if parsed_limit > MAX_SESSION_CLOSEOUT_SUMMARIES:
            raise CampaignSessionCloseoutValidationError(
                "Session closeout summary limit must not exceed 26."
            )
        summaries = self.store.list_closeout_summaries(
            campaign_slug,
            limit=parsed_limit,
        )
        if any(
            summary.item_count != len(SESSION_CLOSEOUT_ITEM_KEYS)
            or not 0 <= summary.resolved_count <= summary.item_count
            for summary in summaries
        ):
            raise RuntimeError("Session closeout summary state is invalid.")
        return summaries

    def open_or_create(
        self,
        campaign_slug: str,
        session_id: Any,
    ) -> CampaignSessionCloseoutOpenResult:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_closed_session(campaign_slug, parsed_session_id)
            existing = self.store.get_closeout(campaign_slug, parsed_session_id)
            if existing is not None:
                self._validate_closeout_shape(existing)
                connection.rollback()
                return CampaignSessionCloseoutOpenResult(
                    closeout=existing,
                    created=False,
                )
            created = self.store.create_closeout(
                campaign_slug,
                parsed_session_id,
                actor_user_id=self._actor_id(context),
                commit=False,
            )
            self._validate_closeout_shape(created)
            self.auth_store.insert_audit_event(
                event_type="campaign_session_closeout_opened",
                actor_user_id=self._actor_id(context),
                campaign_slug=campaign_slug,
                metadata={
                    "closeout_id": created.id,
                    "session_id": parsed_session_id,
                    "revision": created.revision,
                    "item_count": len(created.items),
                    "resolved_count": created.resolved_count,
                },
                commit=False,
            )
            self._before_commit("open")
            connection.commit()
            return CampaignSessionCloseoutOpenResult(
                closeout=created,
                created=True,
            )
        except BaseException as exc:
            connection.rollback()
            self._raise_mapped_conflict(exc)
            raise

    def update_item(
        self,
        campaign_slug: str,
        session_id: Any,
        *,
        expected_revision: Any,
        item_key: Any,
        status: Any,
        note: Any = "",
    ) -> CampaignSessionCloseoutRecord:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        parsed_revision = self._parse_positive_int(
            "expected_revision", expected_revision
        )
        parsed_item_key = str(item_key or "").strip()
        if parsed_item_key not in SESSION_CLOSEOUT_ITEM_KEYS:
            raise CampaignSessionCloseoutValidationError(
                "Session closeout item key is invalid."
            )
        parsed_status = str(status or "").strip().lower()
        if parsed_status not in SESSION_CLOSEOUT_ITEM_STATUSES:
            raise CampaignSessionCloseoutValidationError(
                "Session closeout item status is invalid."
            )
        parsed_note = self._normalize_note(note)
        if parsed_item_key == "external_archive":
            if parsed_status not in {
                SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
                SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
            }:
                raise CampaignSessionCloseoutValidationError(
                    "External archive closeout may only be pending or table-managed."
                )
            if "http://" in parsed_note.casefold() or "https://" in parsed_note.casefold():
                raise CampaignSessionCloseoutValidationError(
                    "External archive URLs are not stored in Session closeout notes."
                )

        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_closed_session(campaign_slug, parsed_session_id)
            current = self._require_closeout(campaign_slug, parsed_session_id)
            if current.revision != parsed_revision:
                raise CampaignSessionCloseoutConflictError(
                    "Session closeout revision is stale."
                )
            if current.status != SESSION_CLOSEOUT_STATUS_OPEN:
                raise CampaignSessionCloseoutConflictError(
                    "Completed Session closeouts must be reopened before editing."
                )
            current_item = next(
                item for item in current.items if item.item_key == parsed_item_key
            )
            if current_item.status == parsed_status and current_item.note == parsed_note:
                connection.rollback()
                return current

            updated = self.store.update_closeout_item(
                campaign_slug,
                parsed_session_id,
                expected_revision=parsed_revision,
                item_key=parsed_item_key,
                status=parsed_status,
                note=parsed_note,
                actor_user_id=self._actor_id(context),
                commit=False,
            )
            self._validate_closeout_shape(updated)
            self.auth_store.insert_audit_event(
                event_type="campaign_session_closeout_item_updated",
                actor_user_id=self._actor_id(context),
                campaign_slug=campaign_slug,
                metadata={
                    "closeout_id": updated.id,
                    "session_id": parsed_session_id,
                    "item_key": parsed_item_key,
                    "previous_status": current_item.status,
                    "new_status": parsed_status,
                    "previous_revision": parsed_revision,
                    "new_revision": updated.revision,
                    "item_count": len(updated.items),
                    "resolved_count": updated.resolved_count,
                    "note_present": bool(parsed_note),
                    "note_changed": current_item.note != parsed_note,
                },
                commit=False,
            )
            self._before_commit("item_update")
            connection.commit()
            return updated
        except BaseException as exc:
            connection.rollback()
            self._raise_mapped_conflict(exc)
            raise

    def complete(
        self,
        campaign_slug: str,
        session_id: Any,
        *,
        expected_revision: Any,
    ) -> CampaignSessionCloseoutRecord:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        parsed_revision = self._parse_positive_int(
            "expected_revision", expected_revision
        )
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_closed_session(campaign_slug, parsed_session_id)
            current = self._require_closeout(campaign_slug, parsed_session_id)
            if current.revision != parsed_revision:
                raise CampaignSessionCloseoutConflictError(
                    "Session closeout revision is stale."
                )
            if current.status != SESSION_CLOSEOUT_STATUS_OPEN:
                raise CampaignSessionCloseoutConflictError(
                    "Session closeout is already completed."
                )
            if current.resolved_count != len(SESSION_CLOSEOUT_ITEM_KEYS):
                raise CampaignSessionCloseoutValidationError(
                    "Resolve every Session closeout item before completion."
                )
            updated = self.store.complete_closeout(
                campaign_slug,
                parsed_session_id,
                expected_revision=parsed_revision,
                actor_user_id=self._actor_id(context),
                commit=False,
            )
            self._validate_closeout_shape(updated)
            self.auth_store.insert_audit_event(
                event_type="campaign_session_closeout_completed",
                actor_user_id=self._actor_id(context),
                campaign_slug=campaign_slug,
                metadata={
                    "closeout_id": updated.id,
                    "session_id": parsed_session_id,
                    "previous_status": current.status,
                    "new_status": updated.status,
                    "previous_revision": parsed_revision,
                    "new_revision": updated.revision,
                    "item_count": len(updated.items),
                    "resolved_count": updated.resolved_count,
                },
                commit=False,
            )
            self._before_commit("complete")
            connection.commit()
            return updated
        except BaseException as exc:
            connection.rollback()
            self._raise_mapped_conflict(exc)
            raise

    def reopen(
        self,
        campaign_slug: str,
        session_id: Any,
        *,
        expected_revision: Any,
    ) -> CampaignSessionCloseoutRecord:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        parsed_revision = self._parse_positive_int(
            "expected_revision", expected_revision
        )
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_closed_session(campaign_slug, parsed_session_id)
            current = self._require_closeout(campaign_slug, parsed_session_id)
            if current.revision != parsed_revision:
                raise CampaignSessionCloseoutConflictError(
                    "Session closeout revision is stale."
                )
            if current.status != SESSION_CLOSEOUT_STATUS_COMPLETED:
                raise CampaignSessionCloseoutConflictError(
                    "Only completed Session closeouts can be reopened."
                )
            updated = self.store.reopen_closeout(
                campaign_slug,
                parsed_session_id,
                expected_revision=parsed_revision,
                actor_user_id=self._actor_id(context),
                commit=False,
            )
            self._validate_closeout_shape(updated)
            self.auth_store.insert_audit_event(
                event_type="campaign_session_closeout_reopened",
                actor_user_id=self._actor_id(context),
                campaign_slug=campaign_slug,
                metadata={
                    "closeout_id": updated.id,
                    "session_id": parsed_session_id,
                    "previous_status": current.status,
                    "new_status": updated.status,
                    "previous_revision": parsed_revision,
                    "new_revision": updated.revision,
                    "item_count": len(updated.items),
                    "resolved_count": updated.resolved_count,
                },
                commit=False,
            )
            self._before_commit("reopen")
            connection.commit()
            return updated
        except BaseException as exc:
            connection.rollback()
            self._raise_mapped_conflict(exc)
            raise

    def delete_confirmed_session_history(
        self,
        campaign_slug: str,
        session_id: Any,
        *,
        expected_revision: Any,
    ) -> None:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_session_id = self._parse_positive_int("session_id", session_id)
        parsed_revision = self._parse_positive_int(
            "expected_revision", expected_revision
        )
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_closed_session(campaign_slug, parsed_session_id)
            current = self._require_closeout(campaign_slug, parsed_session_id)
            if current.revision != parsed_revision:
                raise CampaignSessionCloseoutConflictError(
                    "Session closeout revision is stale."
                )
            self.store.delete_closeout(
                campaign_slug,
                parsed_session_id,
                expected_revision=parsed_revision,
                commit=False,
            )
            self.store.delete_session(
                campaign_slug,
                parsed_session_id,
                commit=False,
            )
            self.store.bump_state_revision(
                campaign_slug,
                updated_by_user_id=self._actor_id(context),
                commit=False,
            )
            self.auth_store.insert_audit_event(
                event_type="campaign_session_closeout_deleted_with_history",
                actor_user_id=self._actor_id(context),
                campaign_slug=campaign_slug,
                metadata={
                    "closeout_id": current.id,
                    "session_id": parsed_session_id,
                    "previous_status": current.status,
                    "revision": current.revision,
                    "item_count": len(current.items),
                    "resolved_count": current.resolved_count,
                },
                commit=False,
            )
            self._before_commit("delete_with_history")
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            self._raise_mapped_conflict(exc)
            raise

    def _authorize(
        self,
        campaign_slug: str,
        *,
        mutation: bool,
    ) -> CampaignSessionCloseoutAuthorizationContext:
        context = self._authorization_adapter(campaign_slug)
        if (
            not isinstance(context, CampaignSessionCloseoutAuthorizationContext)
            or context.campaign_slug != campaign_slug
            or not context.can_manage_campaign_content
            or not context.can_manage_session
        ):
            raise CampaignSessionCloseoutAuthorizationError(
                "Session closeout access is not authorized."
            )
        if mutation and (context.is_view_as or context.is_read_only):
            raise CampaignSessionCloseoutAuthorizationError(
                "Session closeout changes are unavailable in read-only mode."
            )
        if mutation and context.actor_user_id is None:
            raise CampaignSessionCloseoutAuthorizationError(
                "Session closeout changes require an authenticated actor."
            )
        return context

    def _require_closed_session(
        self,
        campaign_slug: str,
        session_id: int,
    ) -> CampaignSessionRecord:
        session_record = self.store.get_session(campaign_slug, session_id)
        if session_record is None:
            raise CampaignSessionCloseoutValidationError(
                "That closed Session could not be found."
            )
        if session_record.is_active:
            raise CampaignSessionCloseoutValidationError(
                "Close the live Session before opening its closeout."
            )
        return session_record

    def _require_closeout(
        self,
        campaign_slug: str,
        session_id: int,
    ) -> CampaignSessionCloseoutRecord:
        closeout = self.store.get_closeout(campaign_slug, session_id)
        if closeout is None:
            raise CampaignSessionCloseoutValidationError(
                "That Session closeout could not be found."
            )
        self._validate_closeout_shape(closeout)
        return closeout

    @staticmethod
    def _validate_closeout_shape(closeout: CampaignSessionCloseoutRecord) -> None:
        if (
            closeout.revision < 1
            or closeout.status
            not in {SESSION_CLOSEOUT_STATUS_OPEN, SESSION_CLOSEOUT_STATUS_COMPLETED}
            or tuple(item.item_key for item in closeout.items)
            != SESSION_CLOSEOUT_ITEM_KEYS
            or any(item.status not in SESSION_CLOSEOUT_ITEM_STATUSES for item in closeout.items)
        ):
            raise RuntimeError("Session closeout state is invalid.")

    @staticmethod
    def _parse_positive_int(field_name: str, value: Any) -> int:
        if isinstance(value, bool):
            raise CampaignSessionCloseoutValidationError(
                f"{field_name} must be a positive integer."
            )
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise CampaignSessionCloseoutValidationError(
                f"{field_name} must be a positive integer."
            ) from exc
        if parsed < 1:
            raise CampaignSessionCloseoutValidationError(
                f"{field_name} must be a positive integer."
            )
        return parsed

    @staticmethod
    def _normalize_note(value: Any) -> str:
        normalized = str(value or "")
        if "\x00" in normalized:
            raise CampaignSessionCloseoutValidationError(
                "Session closeout notes cannot contain NUL characters."
            )
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
        if (
            len(normalized) > MAX_SESSION_CLOSEOUT_NOTE_CHARACTERS
            or len(normalized.encode("utf-8")) > MAX_SESSION_CLOSEOUT_NOTE_BYTES
        ):
            raise CampaignSessionCloseoutValidationError(
                "Session closeout notes must stay within 500 characters and 2,000 UTF-8 bytes."
            )
        return normalized

    @staticmethod
    def _actor_id(context: CampaignSessionCloseoutAuthorizationContext) -> int:
        if context.actor_user_id is None:
            raise CampaignSessionCloseoutAuthorizationError(
                "Session closeout changes require an authenticated actor."
            )
        return context.actor_user_id

    def _before_commit(self, operation: str) -> None:
        if self._pre_commit_hook is not None:
            self._pre_commit_hook(operation)

    @staticmethod
    def _raise_mapped_conflict(exc: BaseException) -> None:
        if isinstance(exc, CampaignSessionConflictError):
            raise CampaignSessionCloseoutConflictError(
                "Session closeout state changed. Refresh and try again."
            ) from exc
