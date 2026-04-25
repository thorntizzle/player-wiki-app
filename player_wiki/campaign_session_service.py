from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .campaign_session_store import CampaignSessionConflictError, CampaignSessionStore
from .repository import normalize_lookup, parse_frontmatter, title_from_slug
from .session_models import (
    CampaignSessionRecord,
    CampaignSessionSummary,
    SessionArticleImageRecord,
    SessionArticleRecord,
    SessionMessageRecord,
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


@dataclass(slots=True)
class SessionArticleMarkdownUpload:
    title: str
    body_markdown: str
    image_reference: str = ""
    image_alt: str = ""
    image_caption: str = ""


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

    def _normalize_article_fields(self, *, title: str, body_markdown: str) -> tuple[str, str]:
        normalized_title = (title or "").strip()
        normalized_body = (body_markdown or "").strip()
        if not normalized_title:
            raise CampaignSessionValidationError("Session articles need a title.")
        if not normalized_body:
            raise CampaignSessionValidationError("Session articles need body text before they can be saved.")
        if len(normalized_title) > 200:
            raise CampaignSessionValidationError("Session article titles must stay under 200 characters.")
        if len(normalized_body) > 40_000:
            raise CampaignSessionValidationError("Session articles must stay under 40,000 characters.")
        return normalized_title, normalized_body

    def get_live_revision(self, campaign_slug: str) -> int:
        return self.store.get_live_revision(campaign_slug)

    def bump_live_state_revision(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> None:
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)

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

    def list_messages(self, session_id: int) -> list[SessionMessageRecord]:
        return self.store.list_messages(session_id)

    def begin_session(
        self,
        campaign_slug: str,
        *,
        started_by_user_id: int | None = None,
    ) -> CampaignSessionRecord:
        if self.store.get_active_session(campaign_slug) is not None:
            raise CampaignSessionValidationError("A live session is already running for this campaign.")
        session_record = self.store.create_session(campaign_slug, started_by_user_id=started_by_user_id)
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=started_by_user_id)
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
        session_record = self.store.close_session(
            campaign_slug,
            active_session.id,
            ended_by_user_id=ended_by_user_id,
        )
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=ended_by_user_id)
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

        try:
            self.store.delete_session(campaign_slug, session_id)
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That chat log could not be deleted. Refresh the page and try again."
            ) from exc
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)

    def post_message(
        self,
        campaign_slug: str,
        *,
        body_text: str,
        author_display_name: str,
        author_user_id: int | None = None,
    ) -> SessionMessageRecord:
        normalized_body = (body_text or "").strip()
        if not normalized_body:
            raise CampaignSessionValidationError("Enter a message before posting it to the chat.")
        if len(normalized_body) > 4000:
            raise CampaignSessionValidationError("Session chat messages must stay under 4,000 characters.")

        active_session = self.store.get_active_session(campaign_slug)
        if active_session is None:
            raise CampaignSessionValidationError("The chat window opens when the DM begins a session.")

        message = self.store.create_message(
            active_session.id,
            campaign_slug,
            message_type="chat",
            body_text=normalized_body,
            author_display_name=author_display_name,
            author_user_id=author_user_id,
        )
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=author_user_id)
        return message

    def create_article(
        self,
        campaign_slug: str,
        *,
        title: str,
        body_markdown: str,
        source_page_ref: str = "",
        created_by_user_id: int | None = None,
    ) -> SessionArticleRecord:
        normalized_title, normalized_body = self._normalize_article_fields(
            title=title,
            body_markdown=body_markdown,
        )
        normalized_source_page_ref = normalize_session_article_source_ref(source_page_ref)
        if len(normalized_source_page_ref) > 400:
            raise CampaignSessionValidationError("Session article source references must stay under 400 characters.")

        article = self.store.create_article(
            campaign_slug,
            title=normalized_title,
            body_markdown=normalized_body,
            source_page_ref=normalized_source_page_ref,
            created_by_user_id=created_by_user_id,
        )
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=created_by_user_id)
        return article

    def update_article(
        self,
        campaign_slug: str,
        article_id: int,
        *,
        title: str,
        body_markdown: str,
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
        )
        try:
            updated_article = self.store.update_article(
                campaign_slug,
                article_id,
                title=normalized_title,
                body_markdown=normalized_body,
            )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be updated. Refresh the page and try again."
            ) from exc
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)
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
            deleted_article = self.store.delete_article(campaign_slug, article_id)
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be deleted. Refresh the page and try again."
            ) from exc
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)
        return deleted_article

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
        if len(data_blob) > 8 * 1024 * 1024:
            raise CampaignSessionValidationError("Session article images must stay under 8 MB.")

        image = self.store.upsert_article_image(
            article_id,
            filename=normalized_filename,
            media_type=normalized_media_type,
            data_blob=data_blob,
            alt_text=(alt_text or "").strip(),
            caption=(caption or "").strip(),
        )
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)
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
            image = self.store.update_article_image_metadata(
                article_id,
                alt_text=(alt_text or "").strip(),
                caption=(caption or "").strip(),
            )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article image could not be updated. Refresh the page and try again."
            ) from exc
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=updated_by_user_id)
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
            article_record, message_record = self.store.reveal_article_in_session(
                article_id,
                campaign_slug=campaign_slug,
                session_id=active_session.id,
                revealed_by_user_id=revealed_by_user_id,
                author_display_name=author_display_name,
            )
        except CampaignSessionConflictError as exc:
            raise CampaignSessionValidationError(
                "That session article could not be revealed. Refresh the page and try again."
            ) from exc
        self.store.bump_state_revision(campaign_slug, updated_by_user_id=revealed_by_user_id)
        return article_record, message_record
