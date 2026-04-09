from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .character_models import CharacterRecord, CharacterStateRecord
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lane_title_map
from .character_store import CharacterStateStore


@dataclass(slots=True)
class CharacterRestChange:
    label: str
    from_value: str
    to_value: str


@dataclass(slots=True)
class CharacterRestPreview:
    rest_type: str
    label: str
    changes: list[CharacterRestChange]


class CharacterStateService:
    def __init__(self, state_store: CharacterStateStore) -> None:
        self.state_store = state_store

    def update_vitals(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        current_hp: Any | None = None,
        temp_hp: Any | None = None,
        hp_delta: Any | None = None,
        temp_hp_delta: Any | None = None,
        clear_temp_hp: bool = False,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        vitals = dict(state.get("vitals") or {})
        next_current_hp = int(vitals.get("current_hp") or 0)
        next_temp_hp = int(vitals.get("temp_hp") or 0)

        if current_hp is not None and str(current_hp).strip() != "":
            next_current_hp = int(current_hp)
        if hp_delta is not None and str(hp_delta).strip() != "":
            next_current_hp += int(hp_delta)

        if clear_temp_hp:
            next_temp_hp = 0
        elif temp_hp is not None and str(temp_hp).strip() != "":
            next_temp_hp = int(temp_hp)
        if temp_hp_delta is not None and str(temp_hp_delta).strip() != "":
            next_temp_hp += int(temp_hp_delta)

        vitals["current_hp"] = next_current_hp
        vitals["temp_hp"] = next_temp_hp
        state["vitals"] = vitals
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_resource(
        self,
        record: CharacterRecord,
        resource_id: str,
        *,
        expected_revision: int,
        current: Any | None = None,
        delta: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        resource = self._find_by_id(state.get("resources") or [], resource_id, "resource")
        next_current = int(resource.get("current") or 0)
        if current is not None and str(current).strip() != "":
            next_current = int(current)
        if delta is not None and str(delta).strip() != "":
            next_current += int(delta)
        resource["current"] = next_current
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_spell_slots(
        self,
        record: CharacterRecord,
        level: int,
        *,
        slot_lane_id: str = "",
        expected_revision: int,
        used: Any | None = None,
        delta_used: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        slots = list(state.get("spell_slots") or [])
        clean_lane_id = normalize_spell_slot_lane_id(slot_lane_id)
        slot = next(
            (
                item
                for item in slots
                if int(item.get("level") or 0) == int(level)
                and normalize_spell_slot_lane_id(item.get("slot_lane_id")) == clean_lane_id
            ),
            None,
        )
        if slot is None:
            lane_label = f" in slot lane '{clean_lane_id}'" if clean_lane_id else ""
            raise ValueError(f"Unknown spell slot level: {level}{lane_label}")
        next_used = int(slot.get("used") or 0)
        if used is not None and str(used).strip() != "":
            next_used = int(used)
        if delta_used is not None and str(delta_used).strip() != "":
            next_used += int(delta_used)
        slot["used"] = next_used
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_inventory_quantity(
        self,
        record: CharacterRecord,
        item_id: str,
        *,
        expected_revision: int,
        quantity: Any | None = None,
        delta: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        item = self._find_by_id(state.get("inventory") or [], item_id, "inventory item")
        next_quantity = int(item.get("quantity") or 0)
        if quantity is not None and str(quantity).strip() != "":
            next_quantity = int(quantity)
        if delta is not None and str(delta).strip() != "":
            next_quantity += int(delta)
        item["quantity"] = next_quantity
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_currency(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        values: dict[str, Any],
        delta: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        currency = dict(state.get("currency") or {})
        delta_key = ""
        delta_amount = 0
        raw_delta = str(delta or "").strip()
        if raw_delta:
            try:
                delta_key, raw_delta_amount = raw_delta.split(":", 1)
            except ValueError as exc:
                raise ValueError("Invalid currency adjustment.") from exc
            delta_key = delta_key.strip().lower()
            if delta_key not in {"cp", "sp", "ep", "gp", "pp"}:
                raise ValueError("Invalid currency adjustment.")
            delta_amount = int(raw_delta_amount)
        for key in ("cp", "sp", "ep", "gp", "pp"):
            next_value = int(currency.get(key) or 0)
            raw_value = values.get(key)
            if raw_value is not None and str(raw_value).strip() != "":
                next_value = int(raw_value)
            if delta_key == key:
                next_value = max(0, next_value + delta_amount)
            currency[key] = next_value
        state["currency"] = currency
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_player_notes(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        notes_markdown: str,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        notes = dict(state.get("notes") or {})
        notes["player_notes_markdown"] = notes_markdown
        state["notes"] = notes
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_personal_details(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        physical_description_markdown: str,
        background_markdown: str,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        notes = dict(state.get("notes") or {})
        notes["physical_description_markdown"] = physical_description_markdown
        notes["background_markdown"] = background_markdown
        state["notes"] = notes
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def preview_rest(self, record: CharacterRecord, rest_type: str) -> CharacterRestPreview:
        normalized_rest = self._normalize_rest_type(rest_type)
        state = deepcopy(record.state_record.state)
        changes = self._collect_rest_changes(
            state,
            normalized_rest,
            spellcasting=record.definition.spellcasting,
        )
        return CharacterRestPreview(
            rest_type=normalized_rest,
            label=self._rest_label(normalized_rest),
            changes=changes,
        )

    def apply_rest(
        self,
        record: CharacterRecord,
        rest_type: str,
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        normalized_rest = self._normalize_rest_type(rest_type)
        state = deepcopy(record.state_record.state)

        for resource in list(state.get("resources") or []):
            if not self._should_reset_resource(resource, normalized_rest):
                continue
            resource["current"] = self._reset_resource_value(resource)

        if normalized_rest == "long":
            for slot in list(state.get("spell_slots") or []):
                slot["used"] = 0

        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def _replace_state(
        self,
        record: CharacterRecord,
        state: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        return self.state_store.replace_state(
            record.definition,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def _collect_rest_changes(
        self,
        state: dict[str, Any],
        rest_type: str,
        *,
        spellcasting: dict[str, Any] | None = None,
    ) -> list[CharacterRestChange]:
        changes: list[CharacterRestChange] = []
        for resource in list(state.get("resources") or []):
            if not self._should_reset_resource(resource, rest_type):
                continue
            next_current = self._reset_resource_value(resource)
            current = int(resource.get("current") or 0)
            if current == next_current:
                continue
            changes.append(
                CharacterRestChange(
                    label=str(resource.get("label") or "Resource"),
                    from_value=self._resource_value_text(current, resource.get("max")),
                    to_value=self._resource_value_text(next_current, resource.get("max")),
                )
            )

        if rest_type == "long":
            lane_titles = spell_slot_lane_title_map(spellcasting)
            total_lanes = len(lane_titles)
            for slot in list(state.get("spell_slots") or []):
                used = int(slot.get("used") or 0)
                max_slots = int(slot.get("max") or 0)
                if used <= 0:
                    continue
                lane_id = normalize_spell_slot_lane_id(slot.get("slot_lane_id"))
                lane_title = str(lane_titles.get(lane_id) or "Spell slots").strip()
                label = f"{self._spell_level_label(int(slot.get('level') or 0))} spell slots"
                if total_lanes > 1:
                    label = f"{lane_title}: {label}"
                changes.append(
                    CharacterRestChange(
                        label=label,
                        from_value=f"{max_slots - used} available / {max_slots}",
                        to_value=f"{max_slots} available / {max_slots}",
                    )
                )

        return changes

    def _should_reset_resource(self, resource: dict[str, Any], rest_type: str) -> bool:
        reset_on = str(resource.get("reset_on") or "manual").strip().lower()
        rest_behavior = str(resource.get("rest_behavior") or "").strip().lower()
        if rest_behavior == "manual_only":
            return False
        if rest_type == "short":
            return reset_on == "short_rest"
        return reset_on in {"short_rest", "long_rest"}

    def _reset_resource_value(self, resource: dict[str, Any]) -> int:
        reset_to = str(resource.get("reset_to") or "unchanged").strip().lower()
        current = int(resource.get("current") or 0)
        max_value = resource.get("max")
        if reset_to == "unchanged":
            return current
        if reset_to == "max":
            if max_value is None:
                return current
            return int(max_value)
        if reset_to in {"zero", "0"}:
            return 0
        return int(reset_to)

    def _normalize_rest_type(self, rest_type: str) -> str:
        normalized = rest_type.strip().lower()
        if normalized not in {"short", "long"}:
            raise ValueError(f"Unsupported rest type: {rest_type}")
        return normalized

    def _rest_label(self, rest_type: str) -> str:
        return "Short Rest" if rest_type == "short" else "Long Rest"

    def _resource_value_text(self, current: int, max_value: Any | None) -> str:
        if max_value is None:
            return str(current)
        return f"{current} / {int(max_value)}"

    def _spell_level_label(self, level: int) -> str:
        if level == 1:
            return "1st level"
        if level == 2:
            return "2nd level"
        if level == 3:
            return "3rd level"
        return f"{level}th level"

    def _find_by_id(self, items: list[dict[str, Any]], target_id: str, item_type: str) -> dict[str, Any]:
        match = next((item for item in items if str(item.get("id") or "") == target_id), None)
        if match is None:
            raise ValueError(f"Unknown {item_type}: {target_id}")
        return match
