from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SESSION_ARTICLE_SOURCE_KIND_PAGE = "page"
SESSION_ARTICLE_SOURCE_KIND_SYSTEMS = "systems"


def normalize_session_article_source_ref(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/")


def build_session_article_page_source_ref(page_ref: str) -> str:
    return normalize_session_article_source_ref(page_ref)


def build_session_article_systems_source_ref(entry_slug: str) -> str:
    normalized_entry_slug = normalize_session_article_source_ref(entry_slug)
    return f"{SESSION_ARTICLE_SOURCE_KIND_SYSTEMS}:{normalized_entry_slug}" if normalized_entry_slug else ""


def parse_session_article_source_ref(value: str) -> tuple[str, str]:
    normalized = normalize_session_article_source_ref(value)
    if not normalized:
        return "", ""

    if ":" in normalized:
        source_kind, source_ref = normalized.split(":", 1)
        source_kind = source_kind.strip().lower()
        source_ref = normalize_session_article_source_ref(source_ref)
        if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS and source_ref:
            return SESSION_ARTICLE_SOURCE_KIND_SYSTEMS, source_ref
        if source_kind == SESSION_ARTICLE_SOURCE_KIND_PAGE and source_ref:
            return SESSION_ARTICLE_SOURCE_KIND_PAGE, source_ref

    return SESSION_ARTICLE_SOURCE_KIND_PAGE, normalized


@dataclass(slots=True)
class CampaignSessionRecord:
    id: int
    campaign_slug: str
    status: str
    started_at: datetime
    started_by_user_id: int | None
    ended_at: datetime | None
    ended_by_user_id: int | None

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(slots=True)
class SessionArticleRecord:
    id: int
    campaign_slug: str
    title: str
    body_markdown: str
    source_page_ref: str
    status: str
    created_at: datetime
    created_by_user_id: int | None
    revealed_at: datetime | None
    revealed_by_user_id: int | None
    revealed_in_session_id: int | None

    @property
    def is_revealed(self) -> bool:
        return self.status == "revealed"


@dataclass(slots=True)
class SessionArticleImageRecord:
    article_id: int
    filename: str
    media_type: str
    alt_text: str
    caption: str
    data_blob: bytes
    updated_at: datetime


@dataclass(slots=True)
class SessionMessageRecord:
    id: int
    session_id: int
    campaign_slug: str
    message_type: str
    body_text: str
    author_user_id: int | None
    author_display_name: str
    article_id: int | None
    created_at: datetime


@dataclass(slots=True)
class CampaignSessionSummary:
    session: CampaignSessionRecord
    message_count: int
    last_message_at: datetime | None
