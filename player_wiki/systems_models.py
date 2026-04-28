from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SystemsLibraryRecord:
    library_slug: str
    title: str
    system_code: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SystemsSourceRecord:
    id: int
    library_slug: str
    source_id: str
    title: str
    license_class: str
    license_url: str
    attribution_text: str
    public_visibility_allowed: bool
    requires_unofficial_notice: bool
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SystemsImportRunRecord:
    id: int
    library_slug: str
    source_id: str
    status: str
    import_version: str
    source_path: str
    summary: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
    started_by_user_id: int | None


@dataclass(slots=True)
class SystemsEntryRecord:
    id: int
    library_slug: str
    source_id: str
    entry_key: str
    entry_type: str
    slug: str
    title: str
    source_page: str
    source_path: str
    search_text: str
    player_safe_default: bool
    dm_heavy: bool
    metadata: dict[str, Any]
    body: dict[str, Any]
    rendered_html: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SystemsSharedEntryEditEventRecord:
    id: int
    campaign_slug: str
    library_slug: str
    source_id: str
    entry_key: str
    entry_slug: str
    original_source_identity: dict[str, Any]
    edited_fields: list[str]
    actor_user_id: int | None
    audit_event_type: str
    audit_metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class CampaignSystemsPolicyRecord:
    campaign_slug: str
    library_slug: str
    status: str
    allow_dm_shared_core_entry_edits: bool
    proprietary_acknowledged_at: datetime | None
    proprietary_acknowledged_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(slots=True)
class CampaignEnabledSourceRecord:
    campaign_slug: str
    library_slug: str
    source_id: str
    is_enabled: bool
    default_visibility: str
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(slots=True)
class CampaignEntryOverrideRecord:
    campaign_slug: str
    library_slug: str
    entry_key: str
    visibility_override: str | None
    is_enabled_override: bool | None
    updated_at: datetime
    updated_by_user_id: int | None
