from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CampaignDMStatblockRecord:
    id: int
    campaign_slug: str
    title: str
    body_markdown: str
    source_filename: str
    armor_class: int | None
    max_hp: int
    speed_text: str
    movement_total: int
    initiative_bonus: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None


@dataclass(slots=True)
class CampaignDMConditionDefinitionRecord:
    id: int
    campaign_slug: str
    name: str
    description_markdown: str
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None
