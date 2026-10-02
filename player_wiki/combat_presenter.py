from __future__ import annotations

from flask import current_app, has_app_context

from .character_hit_dice import hit_dice_summary_from_state
from .character_models import CharacterRecord
from .character_profile import profile_class_level_text
from .db import get_db
from .system_policy import is_dnd_5e_system
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatantResourceCounterRecord,
    CampaignCombatantResourceNoteRecord,
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
    resource_counters_by_combatant: dict[int, list[CampaignCombatantResourceCounterRecord]] | None = None,
    resource_notes_by_combatant: dict[int, list[CampaignCombatantResourceNoteRecord]] | None = None,
    *,
    character_records_by_slug: dict[str, CharacterRecord],
    owned_character_slugs: set[str],
    can_manage_combat: bool,
) -> dict[str, object]:
    resource_counters_by_combatant = resource_counters_by_combatant or {}
    resource_notes_by_combatant = resource_notes_by_combatant or {}
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
        historical_snapshot = combatant.is_player_character and character_record is None
        movement_safe = not historical_snapshot
        hp_safe = not historical_snapshot
        authority = None
        if (combatant.is_player_character and character_record is not None
                and is_dnd_5e_system(character_record.definition.system)):
            historical_snapshot = True
            movement_safe = False
            if character_record is not None and has_app_context():
                try:
                    from .committed_publication import active
                    if not active(get_db()):
                        historical_snapshot = False
                        movement_safe = True
                        hp_safe = True
                    else:
                        state_service = current_app.extensions["character_state_service"]
                        authority = state_service.current_authority(character_record)
                        movement_safe = authority is not None and authority.field_status("stats.speed").is_effective
                        hp_safe = authority is not None and authority.field_status("stats.max_hp").is_effective
                        historical_snapshot = authority is None or any(
                            not authority.field_status(path).is_effective
                            for path in (
                                "stats.initiative_bonus", "stats.ability_scores.dex.modifier",
                                "stats.max_hp", "stats.speed",
                            )
                        )
                except (KeyError, RuntimeError, TypeError, ValueError):
                    historical_snapshot = True
                    movement_safe = False
                    hp_safe = False
                    authority = None
        profile = dict(character_record.definition.profile or {}) if character_record is not None else {}
        stats = dict(character_record.definition.stats or {}) if character_record is not None else {}
        hit_dice = (
            hit_dice_summary_from_state(character_record.definition, character_record.state_record.state)
            if character_record is not None
            else {"pools": [], "value": "", "full_value": "", "regain_on_long_rest": 0}
        )
        if combatant.is_player_character and authority is not None:
            hit_dice = dict(hit_dice)
            hit_dice["pools"] = [
                {**pool, "raw_max": pool["max"],
                 "max": pool["max"] if authority.resource_status("hit_die", str(pool["faces"])).is_effective else None,
                 "can_edit": authority.resource_status("hit_die", str(pool["faces"])).is_effective}
                for pool in hit_dice["pools"]
            ]
            if any(not pool["can_edit"] for pool in hit_dice["pools"]):
                hit_dice["value"] = f"Raw {hit_dice['value']} · NEEDS REPAIR"
        elif combatant.is_player_character and not historical_snapshot:
            hit_dice = dict(hit_dice)
            hit_dice["pools"] = [{**pool, "can_edit": True} for pool in hit_dice["pools"]]
        elif combatant.is_player_character and historical_snapshot:
            hit_dice = dict(hit_dice)
            hit_dice["pools"] = [{**pool, "raw_max": pool["max"], "max": None, "can_edit": False}
                                 for pool in hit_dice["pools"]]
            if hit_dice["pools"]:
                hit_dice["value"] = f"Raw {hit_dice['value']} · NEEDS REPAIR"
        conditions = conditions_by_combatant.get(combatant.id, [])
        resource_counters = resource_counters_by_combatant.get(combatant.id, []) if show_detail else []
        resource_notes = resource_notes_by_combatant.get(combatant.id, []) if show_detail else []
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
                    profile_class_level_text(profile, default="").strip()
                    if character_record is not None
                    else COMBAT_SOURCE_LABELS.get(source_kind, "NPC")
                ),
                "show_detail": show_detail,
                "player_detail_visible": player_detail_visible,
                "turn_value": combatant.turn_value,
                "initiative_bonus_label": format_signed(combatant.initiative_bonus) if show_detail else "",
                "historical_snapshot": historical_snapshot,
                "snapshot_note": (
                    "Historical table-managed Combat snapshot; Character numeric owners need repair before automatic refresh."
                    if historical_snapshot and show_detail else ""
                ),
                "dexterity_modifier": combatant.dexterity_modifier if can_manage_combat else None,
                "dexterity_modifier_label": (
                    format_signed(combatant.dexterity_modifier) if can_manage_combat else ""
                ),
                "initiative_priority": combatant.initiative_priority if can_manage_combat else 0,
                "initiative_priority_label": (
                    str(combatant.initiative_priority)
                    if can_manage_combat and combatant.initiative_priority > 0
                    else ""
                ),
                "current_hp": combatant.current_hp if show_detail else None,
                "max_hp": combatant.max_hp if show_detail else None,
                "temp_hp": combatant.temp_hp if show_detail else None,
                "hit_dice": hit_dice if show_detail and character_record is not None else None,
                "movement_total": combatant.movement_total if show_detail else None,
                "movement_remaining": combatant.movement_remaining if show_detail else None,
                "speed_label": (
                    (f"Raw {combatant.movement_total} ft. · NEEDS REPAIR" if not movement_safe else
                     str((authority.field_status("stats.speed").effective if authority is not None else
                          stats.get("speed")) or f"{combatant.movement_total} ft.").strip())
                    if show_detail
                    else ""
                ),
                "has_action": combatant.has_action if show_detail else False,
                "has_bonus_action": combatant.has_bonus_action if show_detail else False,
                "has_reaction": combatant.has_reaction if show_detail else False,
                "is_current_turn": combatant.id == tracker.current_combatant_id,
                "can_edit_vitals": hp_safe and (can_manage_combat
                or (
                    combatant.is_player_character
                    and viewer_owns_character
                )),
                "can_edit_hit_dice": any(pool.get("can_edit", False) for pool in hit_dice.get("pools", []))
                and (can_manage_combat or (combatant.is_player_character and viewer_owns_character)),
                "can_edit_movement": movement_safe and (can_manage_combat
                or (combatant.is_player_character and viewer_owns_character)),
                "can_edit_resources": can_manage_combat
                or (
                    combatant.is_player_character
                    and viewer_owns_character
                ),
                "can_open_character_page": can_open_character_page,
                "can_open_status_page": can_manage_combat,
                "can_toggle_player_detail_visibility": can_manage_combat and combatant.is_npc,
                "can_manage_combat": can_manage_combat,
                "combatant_revision": combatant.revision,
                "state_revision": (
                    character_record.state_record.revision if character_record is not None else None
                ),
                "npc_resource_counters": [
                    {
                        "resource_key": counter.resource_key,
                        "label": counter.label,
                        "current_value": counter.current_value,
                        "max_value": counter.max_value,
                        "reset_label": counter.reset_label,
                        "source_label": counter.source_label,
                        "can_edit": can_manage_combat and combatant.is_npc,
                    }
                    for counter in resource_counters
                ],
                "npc_resource_notes": [
                    {
                        "label": note.label,
                        "note": note.note,
                        "source_label": note.source_label,
                    }
                    for note in resource_notes
                ],
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
