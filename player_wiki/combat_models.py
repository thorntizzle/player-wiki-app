from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

COMBAT_SOURCE_KIND_CHARACTER = "character"
COMBAT_SOURCE_KIND_MANUAL_NPC = "manual_npc"
COMBAT_SOURCE_KIND_DM_STATBLOCK = "dm_statblock"
COMBAT_SOURCE_KIND_SYSTEMS_MONSTER = "systems_monster"
COMBAT_SOURCE_KINDS = (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
)


@dataclass(slots=True)
class CampaignCombatTrackerRecord:
    campaign_slug: str
    round_number: int
    current_combatant_id: int | None
    revision: int
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(slots=True)
class CampaignCombatantRecord:
    id: int
    campaign_slug: str
    combatant_type: str
    character_slug: str | None
    player_detail_visible: bool
    source_kind: str
    source_ref: str
    display_name: str
    turn_value: int
    initiative_bonus: int
    current_hp: int
    max_hp: int
    temp_hp: int
    movement_total: int
    movement_remaining: int
    has_action: bool
    has_bonus_action: bool
    has_reaction: bool
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None

    @property
    def is_player_character(self) -> bool:
        return self.combatant_type == "player_character"

    @property
    def is_npc(self) -> bool:
        return self.combatant_type == "npc"


@dataclass(slots=True)
class CampaignCombatConditionRecord:
    id: int
    combatant_id: int
    campaign_slug: str
    name: str
    duration_text: str
    created_at: datetime
    created_by_user_id: int | None
