from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .campaign_combat_store import CampaignCombatConflictError, CampaignCombatStore
from .character_repository import CharacterRepository
from .character_state_service import CharacterStateService
from .combat_models import (
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatTrackerRecord,
)

MOVEMENT_VALUE_PATTERN = re.compile(r"(?P<distance>\d+)")


class CampaignCombatValidationError(ValueError):
    pass


class CampaignCombatService:
    def __init__(
        self,
        store: CampaignCombatStore,
        character_repository: CharacterRepository,
        character_state_service: CharacterStateService,
    ) -> None:
        self.store = store
        self.character_repository = character_repository
        self.character_state_service = character_state_service

    def get_tracker(self, campaign_slug: str) -> CampaignCombatTrackerRecord:
        return self.store.ensure_tracker(campaign_slug)

    def list_combatants(self, campaign_slug: str) -> list[CampaignCombatantRecord]:
        self.sync_player_character_snapshots(campaign_slug)
        return self.store.list_combatants(campaign_slug)

    def get_combatant(self, campaign_slug: str, combatant_id: int) -> CampaignCombatantRecord | None:
        return self.store.get_combatant(campaign_slug, combatant_id)

    def list_conditions_by_combatant(
        self,
        campaign_slug: str,
    ) -> dict[int, list[CampaignCombatConditionRecord]]:
        combatants = self.store.list_combatants(campaign_slug)
        conditions = self.store.list_conditions(
            campaign_slug,
            combatant_ids=[combatant.id for combatant in combatants],
        )
        grouped: dict[int, list[CampaignCombatConditionRecord]] = defaultdict(list)
        for condition in conditions:
            grouped[condition.combatant_id].append(condition)
        return dict(grouped)

    def list_available_player_characters(self, campaign_slug: str):
        existing_slugs = {
            combatant.character_slug
            for combatant in self.store.list_combatants(campaign_slug)
            if combatant.character_slug
        }
        return [
            record
            for record in self.character_repository.list_visible_characters(campaign_slug)
            if record.definition.character_slug not in existing_slugs
        ]

    def add_player_character(
        self,
        campaign_slug: str,
        *,
        character_slug: str,
        turn_value: Any | None = None,
        created_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        record = self.character_repository.get_visible_character(campaign_slug, character_slug)
        if record is None:
            raise CampaignCombatValidationError("Choose a valid player character to add to the tracker.")

        snapshot = self._build_player_character_snapshot(record)
        normalized_turn_value = self._parse_int(
            turn_value,
            label="Turn value",
            default=snapshot["initiative_bonus"],
            minimum=None,
        )

        try:
            self.store.ensure_tracker(campaign_slug, updated_by_user_id=created_by_user_id)
            return self.store.create_combatant(
                campaign_slug,
                combatant_type="player_character",
                character_slug=record.definition.character_slug,
                display_name=record.definition.name,
                turn_value=normalized_turn_value,
                initiative_bonus=snapshot["initiative_bonus"],
                current_hp=snapshot["current_hp"],
                max_hp=snapshot["max_hp"],
                temp_hp=snapshot["temp_hp"],
                movement_total=snapshot["movement_total"],
                movement_remaining=snapshot["movement_total"],
                created_by_user_id=created_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError(
                "That player character is already in the combat tracker."
            ) from exc

    def add_npc_combatant(
        self,
        campaign_slug: str,
        *,
        display_name: str,
        turn_value: Any | None,
        initiative_bonus: Any | None = 0,
        current_hp: Any | None,
        max_hp: Any | None,
        temp_hp: Any | None = 0,
        movement_total: Any | None = 0,
        created_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        normalized_name = (display_name or "").strip()
        if not normalized_name:
            raise CampaignCombatValidationError("NPC name is required.")

        normalized_turn_value = self._parse_int(turn_value, label="Turn value", default=0, minimum=None)
        normalized_initiative_bonus = self._parse_int(
            initiative_bonus,
            label="Initiative bonus",
            default=0,
            minimum=None,
        )
        normalized_max_hp = self._parse_int(max_hp, label="Max HP", default=None, minimum=0)
        normalized_current_hp = self._parse_int(
            current_hp,
            label="Current HP",
            default=normalized_max_hp,
            minimum=0,
        )
        normalized_temp_hp = self._parse_int(temp_hp, label="Temp HP", default=0, minimum=0)
        normalized_movement_total = self._parse_int(
            movement_total,
            label="Movement",
            default=0,
            minimum=0,
        )
        if normalized_current_hp > normalized_max_hp:
            raise CampaignCombatValidationError("Current HP cannot exceed max HP.")

        self.store.ensure_tracker(campaign_slug, updated_by_user_id=created_by_user_id)
        return self.store.create_combatant(
            campaign_slug,
            combatant_type="npc",
            display_name=normalized_name,
            turn_value=normalized_turn_value,
            initiative_bonus=normalized_initiative_bonus,
            current_hp=normalized_current_hp,
            max_hp=normalized_max_hp,
            temp_hp=normalized_temp_hp,
            movement_total=normalized_movement_total,
            movement_remaining=normalized_movement_total,
            created_by_user_id=created_by_user_id,
        )

    def update_turn_value(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        turn_value: Any | None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        normalized_turn_value = self._parse_int(
            turn_value,
            label="Turn value",
            default=combatant.turn_value,
            minimum=None,
        )
        try:
            return self.store.update_combatant(
                campaign_slug,
                combatant_id,
                turn_value=normalized_turn_value,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("That turn value could not be saved.") from exc

    def update_npc_vitals(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        current_hp: Any | None,
        max_hp: Any | None,
        temp_hp: Any | None = 0,
        movement_total: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_npc:
            raise CampaignCombatValidationError("Only NPC vitals can be edited directly here.")

        normalized_max_hp = self._parse_int(max_hp, label="Max HP", default=combatant.max_hp, minimum=0)
        normalized_current_hp = self._parse_int(
            current_hp,
            label="Current HP",
            default=combatant.current_hp,
            minimum=0,
        )
        normalized_temp_hp = self._parse_int(
            temp_hp,
            label="Temp HP",
            default=combatant.temp_hp,
            minimum=0,
        )
        normalized_movement_total = self._parse_int(
            movement_total,
            label="Movement",
            default=combatant.movement_total,
            minimum=0,
        )
        if normalized_current_hp > normalized_max_hp:
            raise CampaignCombatValidationError("Current HP cannot exceed max HP.")

        try:
            return self.store.update_combatant(
                campaign_slug,
                combatant_id,
                current_hp=normalized_current_hp,
                max_hp=normalized_max_hp,
                temp_hp=normalized_temp_hp,
                movement_total=normalized_movement_total,
                movement_remaining=min(combatant.movement_remaining, normalized_movement_total),
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("Those NPC vitals could not be saved.") from exc

    def update_player_character_vitals(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int,
        current_hp: Any | None,
        temp_hp: Any | None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_player_character or not combatant.character_slug:
            raise CampaignCombatValidationError("Only player-character vitals can be edited here.")

        record = self.character_repository.get_visible_character(campaign_slug, combatant.character_slug)
        if record is None:
            raise CampaignCombatValidationError("That player character could not be loaded from the campaign data.")

        state_record = self.character_state_service.update_vitals(
            record,
            expected_revision=expected_revision,
            current_hp=current_hp,
            temp_hp=temp_hp,
            updated_by_user_id=updated_by_user_id,
        )

        movement_total = self._parse_movement_total(record.definition.stats.get("speed"))
        max_hp = int(record.definition.stats.get("max_hp") or 0)
        try:
            return self.store.update_combatant(
                campaign_slug,
                combatant_id,
                display_name=record.definition.name,
                initiative_bonus=int(record.definition.stats.get("initiative_bonus") or 0),
                current_hp=int((state_record.state.get("vitals") or {}).get("current_hp") or 0),
                max_hp=max_hp,
                temp_hp=int((state_record.state.get("vitals") or {}).get("temp_hp") or 0),
                movement_total=movement_total,
                movement_remaining=min(combatant.movement_remaining, movement_total),
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("That combat tracker row could not be updated.") from exc

    def update_resources(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        has_action: bool,
        has_bonus_action: bool,
        has_reaction: bool,
        movement_remaining: Any | None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        normalized_movement_remaining = self._parse_int(
            movement_remaining,
            label="Remaining movement",
            default=combatant.movement_remaining,
            minimum=0,
        )
        if normalized_movement_remaining > combatant.movement_total:
            raise CampaignCombatValidationError("Remaining movement cannot exceed total movement.")

        try:
            return self.store.update_combatant(
                campaign_slug,
                combatant_id,
                has_action=has_action,
                has_bonus_action=has_bonus_action,
                has_reaction=has_reaction,
                movement_remaining=normalized_movement_remaining,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("Those combat resources could not be saved.") from exc

    def add_condition(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        name: str,
        duration_text: str = "",
        created_by_user_id: int | None = None,
    ) -> CampaignCombatConditionRecord:
        self._require_combatant(campaign_slug, combatant_id)
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise CampaignCombatValidationError("Condition name is required.")
        if len(normalized_name) > 80:
            raise CampaignCombatValidationError("Condition names must stay under 80 characters.")

        normalized_duration = (duration_text or "").strip()
        if len(normalized_duration) > 120:
            raise CampaignCombatValidationError("Condition duration text must stay under 120 characters.")

        return self.store.create_condition(
            combatant_id,
            name=normalized_name,
            duration_text=normalized_duration,
            created_by_user_id=created_by_user_id,
        )

    def delete_condition(
        self,
        campaign_slug: str,
        condition_id: int,
    ) -> CampaignCombatConditionRecord:
        condition = self.store.delete_condition(campaign_slug, condition_id)
        if condition is None:
            raise CampaignCombatValidationError("That condition could not be found.")
        return condition

    def delete_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
    ) -> CampaignCombatantRecord:
        combatant = self.store.delete_combatant(campaign_slug, combatant_id)
        if combatant is None:
            raise CampaignCombatValidationError("That combatant could not be found.")
        return combatant

    def clear_tracker(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        try:
            return self.store.clear_tracker(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The combat tracker could not be cleared.") from exc

    def set_current_turn(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        tracker = self.store.ensure_tracker(campaign_slug, updated_by_user_id=updated_by_user_id)
        combatant = self._require_combatant(campaign_slug, combatant_id)
        self._refresh_combatant_turn_resources(
            campaign_slug,
            combatant.id,
            updated_by_user_id=updated_by_user_id,
        )
        try:
            return self.store.update_tracker(
                campaign_slug,
                round_number=max(1, tracker.round_number),
                current_combatant_id=combatant.id,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The current turn could not be updated.") from exc

    def advance_turn(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        tracker = self.store.ensure_tracker(campaign_slug, updated_by_user_id=updated_by_user_id)
        combatants = self.store.list_combatants(campaign_slug)
        if not combatants:
            raise CampaignCombatValidationError("Add combatants before advancing turn order.")

        current_index = next(
            (index for index, combatant in enumerate(combatants) if combatant.id == tracker.current_combatant_id),
            None,
        )
        if current_index is None:
            next_index = 0
            next_round = max(1, tracker.round_number)
        else:
            next_index = (current_index + 1) % len(combatants)
            next_round = tracker.round_number + 1 if next_index == 0 else tracker.round_number

        next_combatant = combatants[next_index]
        self._refresh_combatant_turn_resources(
            campaign_slug,
            next_combatant.id,
            updated_by_user_id=updated_by_user_id,
        )
        try:
            return self.store.update_tracker(
                campaign_slug,
                round_number=max(1, next_round),
                current_combatant_id=next_combatant.id,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The turn order could not be advanced.") from exc

    def sync_player_character_snapshots(self, campaign_slug: str) -> None:
        combatants = self.store.list_combatants(campaign_slug)
        for combatant in combatants:
            if not combatant.is_player_character or not combatant.character_slug:
                continue
            record = self.character_repository.get_visible_character(campaign_slug, combatant.character_slug)
            if record is None:
                continue
            snapshot = self._build_player_character_snapshot(record)
            try:
                self.store.update_combatant(
                    campaign_slug,
                    combatant.id,
                    display_name=record.definition.name,
                    initiative_bonus=snapshot["initiative_bonus"],
                    current_hp=snapshot["current_hp"],
                    max_hp=snapshot["max_hp"],
                    temp_hp=snapshot["temp_hp"],
                    movement_total=snapshot["movement_total"],
                    movement_remaining=min(combatant.movement_remaining, snapshot["movement_total"]),
                )
            except CampaignCombatConflictError as exc:
                raise CampaignCombatValidationError(
                    f"Unable to refresh combat tracker data for {record.definition.name}."
                ) from exc

    def _refresh_combatant_turn_resources(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        return self.store.update_combatant(
            campaign_slug,
            combatant_id,
            has_action=True,
            has_bonus_action=True,
            has_reaction=True,
            movement_remaining=combatant.movement_total,
            updated_by_user_id=updated_by_user_id,
        )

    def _require_combatant(self, campaign_slug: str, combatant_id: int) -> CampaignCombatantRecord:
        combatant = self.store.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            raise CampaignCombatValidationError("That combatant could not be found.")
        return combatant

    def _build_player_character_snapshot(self, record) -> dict[str, int]:
        vitals = dict((record.state_record.state or {}).get("vitals") or {})
        stats = dict(record.definition.stats or {})
        return {
            "initiative_bonus": int(stats.get("initiative_bonus") or 0),
            "current_hp": int(vitals.get("current_hp") or 0),
            "max_hp": int(stats.get("max_hp") or 0),
            "temp_hp": int(vitals.get("temp_hp") or 0),
            "movement_total": self._parse_movement_total(stats.get("speed")),
        }

    def _parse_movement_total(self, value: Any | None) -> int:
        normalized = str(value or "").strip()
        distances = [int(match.group("distance")) for match in MOVEMENT_VALUE_PATTERN.finditer(normalized)]
        if not distances:
            return 0
        return max(distances)

    def _parse_int(
        self,
        value: Any | None,
        *,
        label: str,
        default: int | None,
        minimum: int | None = 0,
    ) -> int:
        normalized = "" if value is None else str(value).strip()
        if not normalized:
            if default is None:
                raise CampaignCombatValidationError(f"{label} is required.")
            parsed = default
        else:
            try:
                parsed = int(normalized)
            except ValueError as exc:
                raise CampaignCombatValidationError(f"{label} must be a whole number.") from exc

        if minimum is not None and parsed < minimum:
            raise CampaignCombatValidationError(f"{label} cannot be less than {minimum}.")
        return parsed
