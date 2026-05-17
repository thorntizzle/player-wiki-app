from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .character_models import CharacterRecord, CharacterStateRecord
from .character_spell_slots import normalize_spell_slot_lane_id, spell_slot_lane_title_map
from .character_store import CharacterStateStore
from .repository import slugify
from .system_policy import is_xianxia_system
from .xianxia_character_model import (
    XIANXIA_CURRENCY_KEYS,
    XIANXIA_ENERGY_KEYS,
    xianxia_energy_max,
    xianxia_hp_max,
    xianxia_stance_max,
    xianxia_yang_max,
    xianxia_yin_max,
    normalize_xianxia_inventory_row,
)


_XIANXIA_ENERGY_LABELS = {
    "jing": "Jing",
    "qi": "Qi",
    "shen": "Shen",
}


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
        current_stance: Any | None = None,
        temp_stance: Any | None = None,
        current_jing: Any | None = None,
        current_qi: Any | None = None,
        current_shen: Any | None = None,
        current_yin: Any | None = None,
        current_yang: Any | None = None,
        current_dao: Any | None = None,
        hp_delta: Any | None = None,
        temp_hp_delta: Any | None = None,
        clear_temp_hp: bool = False,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        state = deepcopy(record.state_record.state)
        self._apply_vitals_update(
            state,
            current_hp=current_hp,
            temp_hp=temp_hp,
            hp_delta=hp_delta,
            temp_hp_delta=temp_hp_delta,
            clear_temp_hp=clear_temp_hp,
        )
        if is_xianxia_system(record.definition.system):
            self._apply_xianxia_stance_update(
                state,
                current_stance=current_stance,
                temp_stance=temp_stance,
            )
            self._apply_xianxia_energy_update(
                state,
                current_jing=current_jing,
                current_qi=current_qi,
                current_shen=current_shen,
            )
            self._apply_xianxia_yin_yang_update(
                state,
                current_yin=current_yin,
                current_yang=current_yang,
            )
            self._apply_xianxia_dao_update(
                state,
                current_dao=current_dao,
            )
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_xianxia_active_state(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        active_stance_name: Any | None = None,
        active_aura_name: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        if not is_xianxia_system(record.definition.system):
            raise ValueError(
                "Active Stance and Aura state is only supported for Xianxia characters."
            )

        state = deepcopy(record.state_record.state)
        self._apply_xianxia_active_state_update(
            state,
            active_stance_name=active_stance_name,
            active_aura_name=active_aura_name,
        )
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
        self._apply_resource_update(state, resource_id, current=current, delta=delta)
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
        self._apply_spell_slots_update(
            state,
            level,
            slot_lane_id=slot_lane_id,
            used=used,
            delta_used=delta_used,
        )
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
        self._apply_inventory_quantity_update(state, item_id, quantity=quantity, delta=delta)
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def add_xianxia_inventory_item(
        self,
        record: CharacterRecord,
        item: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        self._require_xianxia_record(record)
        state = deepcopy(record.state_record.state)
        state = self._normalize_xianxia_inventory_state_payload(state)
        self._apply_xianxia_inventory_add_item(state, item)
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_xianxia_inventory_item(
        self,
        record: CharacterRecord,
        item_id: str,
        item: dict[str, Any],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        self._require_xianxia_record(record)
        state = deepcopy(record.state_record.state)
        state = self._normalize_xianxia_inventory_state_payload(state)
        self._apply_xianxia_inventory_edit_item(state, item_id, item)
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def remove_xianxia_inventory_item(
        self,
        record: CharacterRecord,
        item_id: str,
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        self._require_xianxia_record(record)
        state = deepcopy(record.state_record.state)
        state = self._normalize_xianxia_inventory_state_payload(state)
        self._apply_xianxia_inventory_remove_item(state, item_id)
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_xianxia_inventory_quantity(
        self,
        record: CharacterRecord,
        item_id: str,
        *,
        expected_revision: int,
        quantity: Any | None = None,
        delta: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        self._require_xianxia_record(record)
        state = deepcopy(record.state_record.state)
        state = self._normalize_xianxia_inventory_state_payload(state)
        self._apply_xianxia_inventory_quantity_update(state, item_id, quantity=quantity, delta=delta)
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def update_xianxia_inventory_equipped_state(
        self,
        record: CharacterRecord,
        item_id: str,
        *,
        expected_revision: int,
        is_equipped: bool,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        self._require_xianxia_record(record)
        state = deepcopy(record.state_record.state)
        state = self._normalize_xianxia_inventory_state_payload(state)
        self._apply_xianxia_inventory_equipped_state(state, item_id, is_equipped)
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
        if is_xianxia_system(record.definition.system):
            self._apply_xianxia_currency_update(state, values=values, delta=delta)
        else:
            self._apply_currency_update(state, values=values, delta=delta)
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
        self._apply_player_notes_update(state, notes_markdown=notes_markdown)
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
        self._apply_personal_details_update(
            state,
            physical_description_markdown=physical_description_markdown,
            background_markdown=background_markdown,
        )
        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def save_character_sheet_edit(
        self,
        record: CharacterRecord,
        *,
        expected_revision: int,
        vitals: dict[str, Any] | None = None,
        resources: list[dict[str, Any]] | None = None,
        spell_slots: list[dict[str, Any]] | None = None,
        inventory: list[dict[str, Any]] | None = None,
        currency: dict[str, Any] | None = None,
        notes: dict[str, Any] | None = None,
        personal: dict[str, Any] | None = None,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        # The first Character-page batch-save contract is absolute-value only.
        state = deepcopy(record.state_record.state)
        applied_changes = False

        if vitals is not None:
            if not isinstance(vitals, dict):
                raise TypeError("Sheet edit vitals must be an object.")
            if any(key in vitals for key in ("hp_delta", "temp_hp_delta", "clear_temp_hp")):
                raise ValueError("Sheet edit vitals must use absolute current values, not delta actions.")
            if "current_hp" in vitals or "temp_hp" in vitals:
                self._apply_vitals_update(
                    state,
                    current_hp=vitals.get("current_hp"),
                    temp_hp=vitals.get("temp_hp"),
                )
                applied_changes = True

        if resources is not None:
            if not isinstance(resources, list):
                raise TypeError("Sheet edit resources must be a list.")
            for entry in resources:
                if not isinstance(entry, dict):
                    raise TypeError("Each sheet edit resource row must be an object.")
                resource_id = str(entry.get("id") or "").strip()
                if not resource_id:
                    raise ValueError("Each sheet edit resource row needs an id.")
                if "delta" in entry:
                    raise ValueError("Sheet edit resources must use absolute current values, not delta actions.")
                if "current" not in entry:
                    raise ValueError(f"Sheet edit resource '{resource_id}' is missing a current value.")
                self._apply_resource_update(state, resource_id, current=entry.get("current"))
                applied_changes = True

        if spell_slots is not None:
            if not isinstance(spell_slots, list):
                raise TypeError("Sheet edit spell slots must be a list.")
            for entry in spell_slots:
                if not isinstance(entry, dict):
                    raise TypeError("Each sheet edit spell slot row must be an object.")
                if "delta_used" in entry:
                    raise ValueError("Sheet edit spell slots must use absolute used values, not delta actions.")
                if "level" not in entry:
                    raise ValueError("Each sheet edit spell slot row needs a level.")
                if "used" not in entry:
                    raise ValueError("Each sheet edit spell slot row needs a used value.")
                self._apply_spell_slots_update(
                    state,
                    int(entry.get("level")),
                    slot_lane_id=str(entry.get("slot_lane_id") or ""),
                    used=entry.get("used"),
                )
                applied_changes = True

        if inventory is not None:
            if not isinstance(inventory, list):
                raise TypeError("Sheet edit inventory must be a list.")
            for entry in inventory:
                if not isinstance(entry, dict):
                    raise TypeError("Each sheet edit inventory row must be an object.")
                item_id = str(entry.get("id") or "").strip()
                if not item_id:
                    raise ValueError("Each sheet edit inventory row needs an id.")
                if "delta" in entry:
                    raise ValueError("Sheet edit inventory must use absolute quantities, not delta actions.")
                if "quantity" not in entry:
                    raise ValueError(f"Sheet edit inventory row '{item_id}' is missing a quantity.")
                self._apply_inventory_quantity_update(
                    state,
                    item_id,
                    quantity=entry.get("quantity"),
                )
                applied_changes = True

        if currency is not None:
            if not isinstance(currency, dict):
                raise TypeError("Sheet edit currency must be an object.")
            if "delta" in currency:
                raise ValueError("Sheet edit currency must use absolute coin values, not delta actions.")
            if is_xianxia_system(record.definition.system) and any(
                key in currency for key in XIANXIA_CURRENCY_KEYS
            ):
                self._apply_xianxia_currency_update(state, values=currency)
                applied_changes = True
            elif any(key in currency for key in ("cp", "sp", "ep", "gp", "pp")):
                self._apply_currency_update(state, values=currency)
                applied_changes = True

        if notes is not None:
            if not isinstance(notes, dict):
                raise TypeError("Sheet edit notes must be an object.")
            if "player_notes_markdown" in notes:
                self._apply_player_notes_update(
                    state,
                    notes_markdown=str(notes.get("player_notes_markdown") or ""),
                )
                applied_changes = True

        if personal is not None:
            if not isinstance(personal, dict):
                raise TypeError("Sheet edit personal details must be an object.")
            personal_updates: dict[str, str] = {}
            if "physical_description_markdown" in personal:
                personal_updates["physical_description_markdown"] = str(
                    personal.get("physical_description_markdown") or ""
                )
            if "background_markdown" in personal:
                personal_updates["background_markdown"] = str(personal.get("background_markdown") or "")
            if personal_updates:
                self._apply_personal_details_update(state, **personal_updates)
                applied_changes = True

        if not applied_changes:
            raise ValueError("No Character-page sheet edits were provided.")

        return self._replace_state(
            record,
            state,
            expected_revision=expected_revision,
            updated_by_user_id=updated_by_user_id,
        )

    def _apply_vitals_update(
        self,
        state: dict[str, Any],
        *,
        current_hp: Any | None = None,
        temp_hp: Any | None = None,
        hp_delta: Any | None = None,
        temp_hp_delta: Any | None = None,
        clear_temp_hp: bool = False,
    ) -> None:
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

    def _apply_xianxia_stance_update(
        self,
        state: dict[str, Any],
        *,
        current_stance: Any | None = None,
        temp_stance: Any | None = None,
    ) -> None:
        if (
            (current_stance is None or str(current_stance).strip() == "")
            and (temp_stance is None or str(temp_stance).strip() == "")
        ):
            return

        xianxia_state = dict(state.get("xianxia") or {})
        vitals = dict(xianxia_state.get("vitals") or {})
        if current_stance is not None and str(current_stance).strip() != "":
            vitals["current_stance"] = int(current_stance)
        if temp_stance is not None and str(temp_stance).strip() != "":
            vitals["temp_stance"] = int(temp_stance)
        xianxia_state["vitals"] = vitals
        state["xianxia"] = xianxia_state

    def _apply_xianxia_energy_update(
        self,
        state: dict[str, Any],
        *,
        current_jing: Any | None = None,
        current_qi: Any | None = None,
        current_shen: Any | None = None,
    ) -> None:
        submitted = {
            "jing": current_jing,
            "qi": current_qi,
            "shen": current_shen,
        }
        if all(value is None or str(value).strip() == "" for value in submitted.values()):
            return

        xianxia_state = dict(state.get("xianxia") or {})
        energies = dict(xianxia_state.get("energies") or {})
        for key, value in submitted.items():
            if value is None or str(value).strip() == "":
                continue
            energy = dict(energies.get(key) or {})
            energy["current"] = int(value)
            energies[key] = energy
        xianxia_state["energies"] = energies
        state["xianxia"] = xianxia_state

    def _apply_xianxia_yin_yang_update(
        self,
        state: dict[str, Any],
        *,
        current_yin: Any | None = None,
        current_yang: Any | None = None,
    ) -> None:
        if (
            (current_yin is None or str(current_yin).strip() == "")
            and (current_yang is None or str(current_yang).strip() == "")
        ):
            return

        xianxia_state = dict(state.get("xianxia") or {})
        yin_yang = dict(xianxia_state.get("yin_yang") or {})
        if current_yin is not None and str(current_yin).strip() != "":
            yin_yang["yin_current"] = int(current_yin)
        if current_yang is not None and str(current_yang).strip() != "":
            yin_yang["yang_current"] = int(current_yang)
        xianxia_state["yin_yang"] = yin_yang
        state["xianxia"] = xianxia_state

    def _apply_xianxia_dao_update(
        self,
        state: dict[str, Any],
        *,
        current_dao: Any | None = None,
    ) -> None:
        if current_dao is None or str(current_dao).strip() == "":
            return

        xianxia_state = dict(state.get("xianxia") or {})
        dao = dict(xianxia_state.get("dao") or {})
        dao["current"] = int(current_dao)
        xianxia_state["dao"] = dao
        state["xianxia"] = xianxia_state

    def _apply_xianxia_active_state_update(
        self,
        state: dict[str, Any],
        *,
        active_stance_name: Any | None = None,
        active_aura_name: Any | None = None,
    ) -> None:
        if active_stance_name is None and active_aura_name is None:
            return

        xianxia_state = dict(state.get("xianxia") or {})
        if active_stance_name is not None:
            xianxia_state["active_stance"] = self._manual_active_state_record(
                active_stance_name
            )
        if active_aura_name is not None:
            xianxia_state["active_aura"] = self._manual_active_state_record(
                active_aura_name
            )
        state["xianxia"] = xianxia_state

    def _manual_active_state_record(self, value: Any) -> dict[str, str] | None:
        name = " ".join(str(value or "").split()).strip()
        return {"name": name} if name else None

    def _apply_resource_update(
        self,
        state: dict[str, Any],
        resource_id: str,
        *,
        current: Any | None = None,
        delta: Any | None = None,
    ) -> None:
        resource = self._find_by_id(state.get("resources") or [], resource_id, "resource")
        next_current = int(resource.get("current") or 0)
        if current is not None and str(current).strip() != "":
            next_current = int(current)
        if delta is not None and str(delta).strip() != "":
            next_current += int(delta)
        resource["current"] = next_current

    def _apply_spell_slots_update(
        self,
        state: dict[str, Any],
        level: int,
        *,
        slot_lane_id: str = "",
        used: Any | None = None,
        delta_used: Any | None = None,
    ) -> None:
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
        if slot is None and clean_lane_id:
            legacy_slot = next(
                (
                    item
                    for item in slots
                    if int(item.get("level") or 0) == int(level)
                    and not normalize_spell_slot_lane_id(item.get("slot_lane_id"))
                ),
                None,
            )
            if legacy_slot is not None:
                legacy_slot["slot_lane_id"] = clean_lane_id
                slot = legacy_slot
        if slot is None:
            lane_label = f" in slot lane '{clean_lane_id}'" if clean_lane_id else ""
            raise ValueError(f"Unknown spell slot level: {level}{lane_label}")
        next_used = int(slot.get("used") or 0)
        if used is not None and str(used).strip() != "":
            next_used = int(used)
        if delta_used is not None and str(delta_used).strip() != "":
            next_used += int(delta_used)
        slot["used"] = next_used

    def _apply_inventory_quantity_update(
        self,
        state: dict[str, Any],
        item_id: str,
        *,
        quantity: Any | None = None,
        delta: Any | None = None,
    ) -> None:
        item = self._find_by_id(state.get("inventory") or [], item_id, "inventory item")
        next_quantity = int(item.get("quantity") or 0)
        if quantity is not None and str(quantity).strip() != "":
            next_quantity = int(quantity)
        if delta is not None and str(delta).strip() != "":
            next_quantity += int(delta)
        item["quantity"] = next_quantity

    def _require_xianxia_record(self, record: CharacterRecord) -> None:
        if not is_xianxia_system(record.definition.system):
            raise ValueError("Xianxia inventory operations require a Xianxia character.")

    def _coerce_text(self, value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        return self._coerce_text(value).casefold() in {
            "1",
            "true",
            "yes",
            "on",
            "equipped",
            "enabled",
            "used",
            "recorded",
        }

    def _coerce_tags(self, value: Any) -> list[str]:
        if value is None:
            return []
        raw_values: list[Any]
        if isinstance(value, list):
            raw_values = list(value)
        elif isinstance(value, tuple):
            raw_values = list(value)
        elif isinstance(value, str):
            raw_values = value.split(",")
        else:
            raw_values = [value]
        return [self._coerce_text(item) for item in raw_values if self._coerce_text(item)]

    def _normalize_xianxia_inventory_state_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        xianxia_state = dict(state.get("xianxia") or {})
        raw_inventory = dict(xianxia_state.get("inventory") or {})
        raw_quantities = raw_inventory.get("quantities", raw_inventory.get("items", []))
        quantities = (
            [
                {"id": str(key), "quantity": value}
                for key, value in dict(raw_quantities).items()
            ]
            if isinstance(raw_quantities, dict)
            else list(raw_quantities)
        )
        if not isinstance(quantities, list):
            quantities = []
        normalized_quantities = self._coerce_xianxia_inventory_items(quantities)
        xianxia_state["inventory"] = {
            "enabled": bool(normalized_quantities),
            "quantities": normalized_quantities,
        }
        state["xianxia"] = xianxia_state
        self._sync_top_level_xianxia_inventory(state, normalized_quantities)
        return state

    def _coerce_xianxia_inventory_row(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        payload = normalize_xianxia_inventory_row(value)
        if not payload:
            return {}
        quantity = int(payload.get("quantity") or 0)
        payload["quantity"] = quantity
        if "id" not in payload or not payload["id"]:
            return payload
        payload["id"] = self._coerce_text(payload["id"])
        return payload

    def _xianxia_inventory_rows(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        xianxia_state = dict(state.get("xianxia") or {})
        raw_inventory = dict(xianxia_state.get("inventory") or {})
        return [self._coerce_xianxia_inventory_row(item) for item in list(raw_inventory.get("quantities") or [])]

    def _existing_inventory_ids(self, items: list[dict[str, Any]]) -> set[str]:
        return {self._coerce_text(item.get("id")) for item in items if self._coerce_text(item.get("id"))}

    def _derive_inventory_id(self, row: dict[str, Any], existing_ids: set[str]) -> str:
        item_type = self._coerce_text(row.get("item_type"))
        name = self._coerce_text(row.get("name") or row.get("label"))
        catalog_ref = self._coerce_text(row.get("catalog_ref"))
        base = slugify(f"{item_type} {name}" if name else item_type) or slugify(catalog_ref)
        if not base:
            base = "item"
        candidate = base
        if candidate not in existing_ids:
            return candidate
        counter = 2
        while True:
            suffixed = f"{base}-{counter}"
            if suffixed not in existing_ids:
                return suffixed
            counter += 1

    def _sync_top_level_xianxia_inventory(
        self,
        state: dict[str, Any],
        quantities: list[dict[str, Any]],
    ) -> None:
        xianxia_state = dict(state.get("xianxia") or {})
        xianxia_state["inventory"] = {
            "enabled": bool(quantities),
            "quantities": quantities,
        }
        state["xianxia"] = xianxia_state

        top_level_inventory: list[dict[str, Any]] = []
        for item in quantities:
            top_level_inventory.append(
                {
                    "id": item.get("id"),
                    "catalog_ref": item.get("catalog_ref"),
                    "name": item.get("name"),
                    "quantity": int(item.get("quantity") or 0),
                    "item_type": item.get("item_type"),
                    "item_nature": item.get("item_nature"),
                    "equippable": bool(item.get("equippable", False)),
                    "is_equipped": bool(item.get("is_equipped", False)),
                    "weight": item.get("weight"),
                    "is_attuned": bool(item.get("is_attuned", False)),
                    "charges_current": item.get("charges_current"),
                    "charges_max": item.get("charges_max"),
                    "notes": item.get("notes", ""),
                    "tags": list(item.get("tags") or []),
                    "legacy_tags": list(item.get("legacy_tags") or []),
                    "systems_ref": item.get("systems_ref"),
                }
            )
        state["inventory"] = top_level_inventory

    def _coerce_inventory_systems_ref(self, systems_ref: Any) -> dict[str, str] | None:
        if isinstance(systems_ref, dict):
            payload: dict[str, str] = {}
            for key, value in systems_ref.items():
                normalized_key = self._coerce_text(key)
                if not normalized_key:
                    continue
                normalized_value = self._coerce_text(value)
                if not normalized_value:
                    continue
                payload[normalized_key] = normalized_value
            return payload if payload else None
        if not isinstance(systems_ref, str):
            return None
        normalized = self._coerce_text(systems_ref)
        if not normalized:
            return None
        return {"slug": normalized}

    def _payload_to_xianxia_inventory_row(self, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        row = {
            "id": self._coerce_text(item.get("id")),
            "catalog_ref": self._coerce_text(item.get("catalog_ref")),
            "name": self._coerce_text(item.get("name") or item.get("label")),
            "quantity": int(item.get("quantity")) if item.get("quantity") not in (None, "") else 1,
            "notes": self._coerce_text(item.get("notes") or item.get("note")),
            "tags": self._coerce_tags(item.get("tags")),
            "item_type": self._coerce_text(item.get("item_type")),
            "item_nature": self._coerce_text(item.get("item_nature")),
            "equippable": item.get("equippable") if "equippable" in item else None,
            "is_equipped": item.get("is_equipped") if "is_equipped" in item else None,
            "systems_ref": None,
        }
        systems_ref = item.get("systems_ref")
        if isinstance(systems_ref, dict):
            row["systems_ref"] = self._coerce_inventory_systems_ref(systems_ref)
        elif isinstance(systems_ref, str):
            normalized = self._coerce_text(systems_ref)
            if normalized:
                row["systems_ref"] = {"slug": normalized}

        return {key: value for key, value in row.items() if value is not None and value != []}

    def _merge_xianxia_inventory_row(
        self,
        base_row: dict[str, Any],
        update: dict[str, Any],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = dict(base_row)
        explicit_equippable = "equippable" in update
        if "item_type" in update and update["item_type"]:
            merged["item_type"] = update["item_type"]
        if "item_nature" in update:
            merged["item_nature"] = self._coerce_text(update.get("item_nature"))
        if "name" in update:
            merged["name"] = self._coerce_text(update.get("name"))
        if "quantity" in update:
            merged["quantity"] = int(update.get("quantity") or 0)
        if "notes" in update:
            merged["notes"] = self._coerce_text(update.get("notes"))
        if "tags" in update:
            merged["tags"] = self._coerce_tags(update.get("tags"))
        if "catalog_ref" in update:
            merged["catalog_ref"] = self._coerce_text(update.get("catalog_ref"))
        if "equippable" in update:
            merged["equippable"] = self._coerce_bool(update.get("equippable"))
        if "is_equipped" in update:
            merged["is_equipped"] = self._coerce_bool(update.get("is_equipped"))
        if "systems_ref" in update:
            systems_ref = update.get("systems_ref")
            merged["systems_ref"] = (
                self._coerce_inventory_systems_ref(systems_ref)
                if systems_ref is not None
                else None
            )
            if merged.get("systems_ref") is None:
                merged.pop("systems_ref", None)

        if not explicit_equippable:
            merged.pop("equippable", None)

        normalized = normalize_xianxia_inventory_row(merged)
        if not bool(normalized.get("equippable", False)):
            normalized["is_equipped"] = False

        return normalized

    def _apply_xianxia_inventory_add_item(self, state: dict[str, Any], item: dict[str, Any]) -> None:
        payload = self._payload_to_xianxia_inventory_row(item)
        if "name" not in payload and "catalog_ref" not in payload:
            raise ValueError("Inventory item requires a name.")
        if "quantity" not in payload:
            payload["quantity"] = 1

        quantities = self._xianxia_inventory_rows(state)
        existing_ids = self._existing_inventory_ids(quantities)
        if not payload.get("id"):
            payload["id"] = self._derive_inventory_id(payload, existing_ids)
        elif payload["id"] in existing_ids:
            raise ValueError(f"Duplicate inventory item id: {payload['id']}")
        normalized = self._coerce_xianxia_inventory_row(payload)
        if normalized.get("is_equipped") and not bool(normalized.get("equippable", False)):
            raise ValueError("Cannot equip non-equippable item.")

        quantities.append(normalized)
        self._sync_top_level_xianxia_inventory(state, self._coerce_xianxia_inventory_items(quantities))

    def _coerce_xianxia_inventory_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_items: list[dict[str, Any]] = []
        existing_ids: set[str] = set()
        for item in items:
            normalized = self._coerce_xianxia_inventory_row(item)
            if not normalized:
                continue
            row_id = self._coerce_text(normalized.get("id"))
            if row_id and row_id in existing_ids:
                normalized["id"] = self._derive_inventory_id(normalized, existing_ids)
            elif not row_id:
                normalized["id"] = self._derive_inventory_id(normalized, existing_ids)
            existing_ids.add(self._coerce_text(normalized["id"]))
            normalized_items.append(normalize_xianxia_inventory_row(normalized))
        return normalized_items

    def _apply_xianxia_inventory_remove_item(self, state: dict[str, Any], item_id: str) -> None:
        quantities = self._xianxia_inventory_rows(state)
        next_quantities = [item for item in quantities if item.get("id") != item_id]
        if len(next_quantities) == len(quantities):
            raise ValueError(f"Unknown Xianxia inventory item: {item_id}")
        self._sync_top_level_xianxia_inventory(
            state,
            self._coerce_xianxia_inventory_items(next_quantities),
        )

    def _apply_xianxia_inventory_edit_item(self, state: dict[str, Any], item_id: str, item: dict[str, Any]) -> None:
        quantities = self._xianxia_inventory_rows(state)
        for index, existing in enumerate(quantities):
            if existing.get("id") == item_id:
                payload = self._payload_to_xianxia_inventory_row(item)
                merged = self._merge_xianxia_inventory_row(existing, payload)
                merged["id"] = item_id
                quantities[index] = merged
                self._sync_top_level_xianxia_inventory(
                    state,
                    self._coerce_xianxia_inventory_items(quantities),
                )
                return
        raise ValueError(f"Unknown Xianxia inventory item: {item_id}")

    def _apply_xianxia_inventory_quantity_update(
        self,
        state: dict[str, Any],
        item_id: str,
        *,
        quantity: Any | None = None,
        delta: Any | None = None,
    ) -> None:
        quantities = self._xianxia_inventory_rows(state)
        for row in quantities:
            if row.get("id") == item_id:
                next_quantity = int(row.get("quantity") or 0)
                if quantity is not None and str(quantity).strip() != "":
                    next_quantity = int(quantity)
                if delta is not None and str(delta).strip() != "":
                    next_quantity += int(delta)
                row["quantity"] = next_quantity
                self._sync_top_level_xianxia_inventory(
                    state,
                    self._coerce_xianxia_inventory_items(quantities),
                )
                return
        raise ValueError(f"Unknown Xianxia inventory item: {item_id}")

    def _apply_xianxia_inventory_equipped_state(
        self,
        state: dict[str, Any],
        item_id: str,
        is_equipped: bool,
    ) -> None:
        quantities = self._xianxia_inventory_rows(state)
        for row in quantities:
            if row.get("id") == item_id:
                if is_equipped and not bool(row.get("equippable", False)):
                    raise ValueError("Cannot equip a non-equippable item.")
                row["is_equipped"] = bool(is_equipped)
                self._sync_top_level_xianxia_inventory(
                    state,
                    self._coerce_xianxia_inventory_items(quantities),
                )
                return
        raise ValueError(f"Unknown Xianxia inventory item: {item_id}")

    def _apply_currency_update(
        self,
        state: dict[str, Any],
        *,
        values: dict[str, Any],
        delta: Any | None = None,
    ) -> None:
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

    def _apply_xianxia_currency_update(
        self,
        state: dict[str, Any],
        *,
        values: dict[str, Any],
        delta: Any | None = None,
    ) -> None:
        xianxia_state = dict(state.get("xianxia") or {})
        currency = dict(xianxia_state.get("currency") or {})
        delta_key = ""
        delta_amount = 0
        raw_delta = str(delta or "").strip()
        if raw_delta:
            try:
                delta_key, raw_delta_amount = raw_delta.split(":", 1)
            except ValueError as exc:
                raise ValueError("Invalid currency adjustment.") from exc
            delta_key = delta_key.strip().lower()
            if delta_key not in XIANXIA_CURRENCY_KEYS:
                raise ValueError("Invalid currency adjustment.")
            delta_amount = int(raw_delta_amount)
        for key in XIANXIA_CURRENCY_KEYS:
            next_value = int(currency.get(key) or 0)
            raw_value = values.get(key)
            if raw_value is not None and str(raw_value).strip() != "":
                next_value = int(raw_value)
            if delta_key == key:
                next_value += delta_amount
            currency[key] = max(0, next_value)
        xianxia_state["currency"] = currency
        state["xianxia"] = xianxia_state

    def _apply_player_notes_update(
        self,
        state: dict[str, Any],
        *,
        notes_markdown: str,
    ) -> None:
        notes = dict(state.get("notes") or {})
        notes["player_notes_markdown"] = notes_markdown
        state["notes"] = notes

    def _apply_personal_details_update(
        self,
        state: dict[str, Any],
        *,
        physical_description_markdown: str | None = None,
        background_markdown: str | None = None,
    ) -> None:
        notes = dict(state.get("notes") or {})
        if physical_description_markdown is not None:
            notes["physical_description_markdown"] = physical_description_markdown
        if background_markdown is not None:
            notes["background_markdown"] = background_markdown
        state["notes"] = notes

    def preview_rest(self, record: CharacterRecord, rest_type: str) -> CharacterRestPreview:
        normalized_rest = self._normalize_rest_type(rest_type)
        state = deepcopy(record.state_record.state)
        changes = self._collect_rest_changes(
            state,
            normalized_rest,
            definition=record.definition,
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
            if is_xianxia_system(record.definition.system):
                self._apply_xianxia_one_day_rest(state, record.definition)

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
        definition: Any,
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
            if is_xianxia_system(getattr(definition, "system", None)):
                changes.extend(self._collect_xianxia_one_day_rest_changes(state, definition))

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

    def _apply_xianxia_one_day_rest(self, state: dict[str, Any], definition: Any) -> None:
        xianxia_state = dict(state.get("xianxia") or {})
        vitals = dict(xianxia_state.get("vitals") or {})
        hp_max = xianxia_hp_max(definition)
        stance_max = xianxia_stance_max(definition)
        vitals["current_hp"] = hp_max
        vitals["current_stance"] = stance_max
        xianxia_state["vitals"] = vitals

        energies = {
            key: {"current": xianxia_energy_max(definition, key)}
            for key in XIANXIA_ENERGY_KEYS
        }
        xianxia_state["energies"] = energies
        xianxia_state["yin_yang"] = {
            "yin_current": xianxia_yin_max(definition),
            "yang_current": xianxia_yang_max(definition),
        }
        state["xianxia"] = xianxia_state

        shared_vitals = dict(state.get("vitals") or {})
        shared_vitals["current_hp"] = hp_max
        state["vitals"] = shared_vitals

    def _collect_xianxia_one_day_rest_changes(
        self,
        state: dict[str, Any],
        definition: Any,
    ) -> list[CharacterRestChange]:
        changes: list[CharacterRestChange] = []
        xianxia_state = dict(state.get("xianxia") or {})
        vitals = dict(xianxia_state.get("vitals") or {})
        self._append_pool_recovery_change(
            changes,
            label="HP",
            current=vitals.get("current_hp"),
            maximum=xianxia_hp_max(definition),
        )
        self._append_pool_recovery_change(
            changes,
            label="Stance",
            current=vitals.get("current_stance"),
            maximum=xianxia_stance_max(definition),
        )

        energies = dict(xianxia_state.get("energies") or {})
        for key in XIANXIA_ENERGY_KEYS:
            energy = dict(energies.get(key) or {})
            self._append_pool_recovery_change(
                changes,
                label=f"{_XIANXIA_ENERGY_LABELS[key]} Energy",
                current=energy.get("current"),
                maximum=xianxia_energy_max(definition, key),
            )

        yin_yang = dict(xianxia_state.get("yin_yang") or {})
        self._append_pool_recovery_change(
            changes,
            label="Yin",
            current=yin_yang.get("yin_current"),
            maximum=xianxia_yin_max(definition),
        )
        self._append_pool_recovery_change(
            changes,
            label="Yang",
            current=yin_yang.get("yang_current"),
            maximum=xianxia_yang_max(definition),
        )
        return changes

    def _append_pool_recovery_change(
        self,
        changes: list[CharacterRestChange],
        *,
        label: str,
        current: Any,
        maximum: int,
    ) -> None:
        current_value = max(0, int(current or 0))
        max_value = max(0, int(maximum))
        if current_value == max_value:
            return
        changes.append(
            CharacterRestChange(
                label=label,
                from_value=self._resource_value_text(current_value, max_value),
                to_value=self._resource_value_text(max_value, max_value),
            )
        )

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
