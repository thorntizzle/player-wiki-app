from __future__ import annotations

from .character_models import CharacterRecord
from .combat_models import (
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
        character_record = (
            character_records_by_slug.get(combatant.character_slug or "")
            if combatant.character_slug
            else None
        )
        profile = dict(character_record.definition.profile or {}) if character_record is not None else {}
        stats = dict(character_record.definition.stats or {}) if character_record is not None else {}
        conditions = conditions_by_combatant.get(combatant.id, [])
        presented_combatants.append(
            {
                "id": combatant.id,
                "name": combatant.display_name,
                "character_slug": combatant.character_slug or "",
                "type_label": "Player character" if combatant.is_player_character else "NPC",
                "subtitle": (
                    str(profile.get("class_level_text") or "").strip()
                    if character_record is not None
                    else "Statblock import TODO"
                ),
                "turn_value": combatant.turn_value,
                "initiative_bonus_label": format_signed(combatant.initiative_bonus),
                "current_hp": combatant.current_hp,
                "max_hp": combatant.max_hp,
                "temp_hp": combatant.temp_hp,
                "movement_total": combatant.movement_total,
                "movement_remaining": combatant.movement_remaining,
                "speed_label": str(stats.get("speed") or f"{combatant.movement_total} ft.").strip(),
                "has_action": combatant.has_action,
                "has_bonus_action": combatant.has_bonus_action,
                "has_reaction": combatant.has_reaction,
                "is_current_turn": combatant.id == tracker.current_combatant_id,
                "can_edit_vitals": can_manage_combat
                or (
                    combatant.is_player_character
                    and bool(combatant.character_slug)
                    and combatant.character_slug in owned_character_slugs
                ),
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

    return {
        "round_number": tracker.round_number,
        "current_turn_label": current_combatant.display_name if current_combatant is not None else "",
        "has_current_turn": current_combatant is not None,
        "combatant_count": len(combatants),
        "combatants": presented_combatants,
    }
