from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SESSION_ARTICLE_SOURCE_KIND_PAGE = "page"
SESSION_ARTICLE_SOURCE_KIND_SYSTEMS = "systems"

SESSION_CLOSEOUT_STATUS_OPEN = "open"
SESSION_CLOSEOUT_STATUS_COMPLETED = "completed"
SESSION_CLOSEOUT_STATUSES = (
    SESSION_CLOSEOUT_STATUS_OPEN,
    SESSION_CLOSEOUT_STATUS_COMPLETED,
)

SESSION_CLOSEOUT_ITEM_TABLE_NOTES = "table_notes"
SESSION_CLOSEOUT_ITEM_CHARACTER_RESTS = "character_rests"
SESSION_CLOSEOUT_ITEM_REWARDS_AND_BOONS = "rewards_and_boons"
SESSION_CLOSEOUT_ITEM_ENCOUNTER_DISPOSITION = "encounter_disposition"
SESSION_CLOSEOUT_ITEM_SESSION_ARTICLE_PUBLICATION = "session_article_publication"
SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE = "external_archive"
SESSION_CLOSEOUT_ITEM_KEYS = (
    SESSION_CLOSEOUT_ITEM_TABLE_NOTES,
    SESSION_CLOSEOUT_ITEM_CHARACTER_RESTS,
    SESSION_CLOSEOUT_ITEM_REWARDS_AND_BOONS,
    SESSION_CLOSEOUT_ITEM_ENCOUNTER_DISPOSITION,
    SESSION_CLOSEOUT_ITEM_SESSION_ARTICLE_PUBLICATION,
    SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE,
)

SESSION_CLOSEOUT_ITEM_STATUS_PENDING = "pending"
SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE = "complete"
SESSION_CLOSEOUT_ITEM_STATUS_NOT_APPLICABLE = "not_applicable"
SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED = "table_managed"
SESSION_CLOSEOUT_ITEM_STATUSES = (
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
    SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
    SESSION_CLOSEOUT_ITEM_STATUS_NOT_APPLICABLE,
    SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
)


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
class CampaignSessionStateRecord:
    campaign_slug: str
    revision: int
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class CampaignSessionReadinessSummary:
    active_started_at: datetime | None
    staged_count: int
    revealed_count: int


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
    recipient_scope: str
    recipient_user_id: int | None
    author_user_id: int | None
    author_display_name: str
    article_id: int | None
    created_at: datetime


@dataclass(slots=True)
class CampaignSessionSummary:
    session: CampaignSessionRecord
    message_count: int
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class CampaignSessionCloseoutItemRecord:
    closeout_id: int
    campaign_slug: str
    item_key: str
    status: str
    note: str


@dataclass(frozen=True, slots=True)
class CampaignSessionCloseoutRecord:
    id: int
    campaign_slug: str
    session_id: int
    status: str
    revision: int
    created_at: datetime
    created_by_user_id: int | None
    updated_at: datetime
    updated_by_user_id: int | None
    completed_at: datetime | None
    completed_by_user_id: int | None
    items: tuple[CampaignSessionCloseoutItemRecord, ...]

    @property
    def resolved_count(self) -> int:
        return sum(
            item.status != SESSION_CLOSEOUT_ITEM_STATUS_PENDING
            for item in self.items
        )


@dataclass(frozen=True, slots=True)
class CampaignSessionCloseoutSummary:
    closeout_id: int
    session_id: int
    status: str
    revision: int
    updated_at: datetime
    item_count: int
    resolved_count: int


@dataclass(frozen=True, slots=True)
class CampaignSessionCloseoutOpenResult:
    closeout: CampaignSessionCloseoutRecord
    created: bool
