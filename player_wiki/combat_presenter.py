from __future__ import annotations

from .character_models import CharacterRecord
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatTrackerRecord,
)

DND_5E_CONDITION_OPTIONS = (
    "Blinded",
    "Charmed",
    "Deafened",
    "Exhaustion",
    "Frightened",
    "Grappled",
    "Incapacitated",
    "Invisible",
    "Paralyzed",
    "Petrified",
    "Poisoned",
    "Prone",
    "Restrained",
    "Stunned",
    "Unconscious",
)
COMBAT_SOURCE_LABELS = {
    COMBAT_SOURCE_KIND_CHARACTER: "Character",
    COMBAT_SOURCE_KIND_MANUAL_NPC: "Manual NPC",
    COMBAT_SOURCE_KIND_DM_STATBLOCK: "DM Content",
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER: "Systems",
}


def format_signed(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def present_combat_tracker(
    tracker: CampaignCombatTrackerRecord,
    combatants: list[CampaignCombatantRecord],
    conditions_by_combatant: dict[int, list[CampaignCombatConditionRecord]],
    *,
    character_records_by_slug: dict[str, CharacterRecord],
    owned_character_slugs: set[str],
    can_manage_combat: bool,
) -> dict[str, object]:
    current_combatant = next(
        (combatant for combatant in combatants if combatant.id == tracker.current_combatant_id),
        None,
    )
    presented_combatants: list[dict[str, object]] = []
    for combatant in combatants:
        viewer_owns_character = (
            combatant.is_player_character
            and bool(combatant.character_slug)
            and combatant.character_slug in owned_character_slugs
        )
        can_open_character_page = viewer_owns_character and not can_manage_combat
        player_detail_visible = combatant.player_detail_visible or combatant.is_player_character
        show_detail = can_manage_combat or combatant.is_player_character or player_detail_visible
        character_record = (
            character_records_by_slug.get(combatant.character_slug or "")
            if combatant.character_slug
            else None
        )
        profile = dict(character_record.definition.profile or {}) if character_record is not None else {}
        stats = dict(character_record.definition.stats or {}) if character_record is not None else {}
        conditions = conditions_by_combatant.get(combatant.id, [])
        source_kind = combatant.source_kind or (
            COMBAT_SOURCE_KIND_CHARACTER if combatant.character_slug else COMBAT_SOURCE_KIND_MANUAL_NPC
        )
        presented_combatants.append(
            {
                "id": combatant.id,
                "name": combatant.display_name,
                "character_slug": combatant.character_slug or "",
                "source_kind": source_kind if show_detail else "",
                "source_ref": (combatant.source_ref or "") if show_detail else "",
                "source_label": COMBAT_SOURCE_LABELS.get(source_kind, "Unknown source") if show_detail else "",
                "type_label": "Player character" if combatant.is_player_character else "NPC",
                "subtitle": (
                    str(profile.get("class_level_text") or "").strip()
                    if character_record is not None
                    else COMBAT_SOURCE_LABELS.get(source_kind, "NPC")
                ),
                "show_detail": show_detail,
                "player_detail_visible": player_detail_visible,
                "turn_value": combatant.turn_value,
                "initiative_bonus_label": format_signed(combatant.initiative_bonus) if show_detail else "",
                "current_hp": combatant.current_hp if show_detail else None,
                "max_hp": combatant.max_hp if show_detail else None,
                "temp_hp": combatant.temp_hp if show_detail else None,
                "movement_total": combatant.movement_total if show_detail else None,
                "movement_remaining": combatant.movement_remaining if show_detail else None,
                "speed_label": (
                    str(stats.get("speed") or f"{combatant.movement_total} ft.").strip()
                    if show_detail
                    else ""
                ),
                "has_action": combatant.has_action if show_detail else False,
                "has_bonus_action": combatant.has_bonus_action if show_detail else False,
                "has_reaction": combatant.has_reaction if show_detail else False,
                "is_current_turn": combatant.id == tracker.current_combatant_id,
                "can_edit_vitals": can_manage_combat
                or (
                    combatant.is_player_character
                    and viewer_owns_character
                ),
                "can_edit_resources": can_manage_combat
                or (
                    combatant.is_player_character
                    and viewer_owns_character
                ),
                "can_open_character_page": can_open_character_page,
                "can_open_status_page": can_manage_combat,
                "can_toggle_player_detail_visibility": can_manage_combat and combatant.is_npc,
                "can_manage_combat": can_manage_combat,
                "state_revision": (
                    character_record.state_record.revision if character_record is not None else None
                ),
                "conditions": [
                    {
                        "id": condition.id,
                        "name": condition.name,
                        "duration_text": condition.duration_text,
                    }
                    for condition in conditions
                ],
            }
        )
        if not show_detail:
            presented_combatants[-1]["subtitle"] = ""

    return {
        "round_number": tracker.round_number,
        "current_turn_label": current_combatant.display_name if current_combatant is not None else "",
        "has_current_turn": current_combatant is not None,
        "combatant_count": len(combatants),
        "combatants": presented_combatants,
    }
