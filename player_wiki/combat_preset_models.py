from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetEntryInput:
    source_kind: str
    source_ref: str = ""
    source_version: str | None = None
    version_scheme: str | None = None
    quantity: int = 1
    turn_value: int | None = None
    initiative_priority: int = 1
    custom_name: str = ""
    initiative_bonus: int | None = None
    dexterity_modifier: int | None = None
    max_hp: int | None = None
    movement_total: int | None = None
    id: int | None = None

    @classmethod
    def from_record(
        cls,
        record: "CampaignCombatPresetEntryRecord",
        *,
        id: int | None = None,
    ) -> "CampaignCombatPresetEntryInput":
        return cls(
            id=record.id if id is None else id,
            source_kind=record.source_kind,
            source_ref=record.source_ref,
            source_version=record.source_version,
            version_scheme=record.version_scheme,
            quantity=record.quantity,
            turn_value=record.turn_value,
            initiative_priority=record.initiative_priority,
            custom_name=record.custom_name,
            initiative_bonus=record.initiative_bonus,
            dexterity_modifier=record.dexterity_modifier,
            max_hp=record.max_hp,
            movement_total=record.movement_total,
        )


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetEntryRecord:
    id: int
    campaign_slug: str
    preset_id: int
    position: int
    source_kind: str
    source_ref: str
    source_version: str | None
    version_scheme: str | None
    quantity: int
    turn_value: int | None
    initiative_priority: int
    custom_name: str
    initiative_bonus: int | None
    dexterity_modifier: int | None
    max_hp: int | None
    movement_total: int | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None

    def as_input(self) -> CampaignCombatPresetEntryInput:
        return CampaignCombatPresetEntryInput.from_record(self)


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetRecord:
    id: int
    campaign_slug: str
    name: str
    name_key: str
    revision: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None
    entries: tuple[CampaignCombatPresetEntryRecord, ...] = ()

    def without_entries(self) -> "CampaignCombatPresetRecord":
        return replace(self, entries=())
