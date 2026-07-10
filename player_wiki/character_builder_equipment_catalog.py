from __future__ import annotations

from typing import Any

from .character_builder_constants import (
    ITEM_TITLES_BY_EQUIPMENT_TYPE,
    ITEM_TYPE_CODES_BY_EQUIPMENT_TYPE,
)
from .character_builder_derivation import _clean_embedded_text
from .character_builder_equipment import (
    _format_currency_seed,
    _humanize_item_reference,
    _merge_currency_seed,
    _resolve_item_entry,
    _systems_ref_from_entry,
    describe_equipment_state_support,
)
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_build_equipment_groups",
    "_build_starting_equipment_groups",
    "_build_equipment_group_option_bundles",
    "_expand_equipment_bundle_specs",
    "_expand_equipment_spec",
    "_build_equipment_item_spec",
    "_list_item_entries_for_equipment_type",
    "_describe_equipment_bundle",
    "_describe_equipment_spec",
    "_build_level_one_equipment_catalog",
    "_default_equipment_item_equipped",
    "_format_weight_value",
    "_currency_seed_from_cp",
    "_collect_currency_seed_from_equipment",
]


def _build_equipment_groups(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    item_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    class_starting_equipment = dict((selected_class.metadata if selected_class is not None else {}) or {}).get(
        "starting_equipment"
    )
    if isinstance(class_starting_equipment, dict):
        groups.extend(
            _build_starting_equipment_groups(
                prefix="class",
                label_prefix="Class Equipment",
                raw_groups=list(class_starting_equipment.get("defaultData") or []),
                item_catalog=item_catalog,
                values=values,
            )
        )

    background_starting_equipment = dict((selected_background.metadata if selected_background is not None else {}) or {}).get(
        "starting_equipment"
    )
    if isinstance(background_starting_equipment, list):
        groups.extend(
            _build_starting_equipment_groups(
                prefix="background",
                label_prefix="Background Equipment",
                raw_groups=background_starting_equipment,
                item_catalog=item_catalog,
                values=values,
            )
        )
    return groups


def _build_starting_equipment_groups(
    *,
    prefix: str,
    label_prefix: str,
    raw_groups: list[Any],
    item_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    choice_index = 0
    for raw_group in raw_groups:
        option_bundles = _build_equipment_group_option_bundles(raw_group, item_catalog)
        if not option_bundles:
            continue
        field_name = None
        selected = ""
        if len(option_bundles) > 1:
            choice_index += 1
            field_name = f"{prefix}_equipment_{choice_index}"
            for option_index, option in enumerate(option_bundles, start=1):
                option["value"] = f"{field_name}:{option_index}"
            selected = str(values.get(field_name) or "").strip()
        else:
            option_bundles[0]["value"] = f"{prefix}_equipment_fixed_{len(groups) + 1}"
        groups.append(
            {
                "field_name": field_name,
                "field_label": f"{label_prefix} {choice_index}" if field_name else "",
                "help_text": f"Choose {label_prefix.lower()}." if field_name else "",
                "selected": selected,
                "options": option_bundles,
            }
        )
    return groups


def _build_equipment_group_option_bundles(
    raw_group: Any,
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(raw_group, dict):
        return []
    alternatives: list[Any]
    option_keys = [key for key in raw_group.keys() if key != "_"]
    if option_keys:
        alternatives = [raw_group.get(key) for key in option_keys]
    else:
        alternatives = [raw_group.get("_")]

    option_bundles: list[dict[str, Any]] = []
    for alternative in alternatives:
        bundles = _expand_equipment_bundle_specs(alternative, item_catalog)
        for bundle in bundles:
            option_bundles.append(
                {
                    "label": _describe_equipment_bundle(bundle),
                    "value": "",
                    "equipment_bundle": bundle,
                }
            )
    return option_bundles


def _expand_equipment_bundle_specs(
    raw_specs: Any,
    item_catalog: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    specs_list = raw_specs if isinstance(raw_specs, list) else [raw_specs]
    bundles: list[list[dict[str, Any]]] = [[]]
    for raw_spec in specs_list:
        candidate_specs = _expand_equipment_spec(raw_spec, item_catalog)
        if not candidate_specs:
            continue
        next_bundles: list[list[dict[str, Any]]] = []
        for bundle in bundles:
            for candidate in candidate_specs:
                next_bundles.append(bundle + [candidate])
        bundles = next_bundles or bundles
    return bundles


def _expand_equipment_spec(
    raw_spec: Any,
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(raw_spec, str):
        return [_build_equipment_item_spec(raw_spec, item_catalog=item_catalog)]
    if not isinstance(raw_spec, dict):
        return []

    equipment_type = str(raw_spec.get("equipmentType") or "").strip()
    if equipment_type:
        candidates = []
        for entry in _list_item_entries_for_equipment_type(equipment_type, item_catalog):
            candidates.append(
                _build_equipment_item_spec(
                    entry.title,
                    item_catalog=item_catalog,
                    quantity=int(raw_spec.get("quantity") or 1),
                    forced_entry=entry,
                )
            )
        return candidates

    if raw_spec.get("item"):
        return [
            _build_equipment_item_spec(
                str(raw_spec.get("item") or ""),
                item_catalog=item_catalog,
                quantity=int(raw_spec.get("quantity") or 1),
                display_name=str(raw_spec.get("displayName") or "").strip() or None,
                special_text=str(raw_spec.get("special") or "").strip() or None,
                contained_value=raw_spec.get("containsValue"),
            )
        ]

    if raw_spec.get("value") is not None:
        currency = _currency_seed_from_cp(raw_spec.get("value"))
        label = _format_currency_seed(currency)
        if not label:
            return []
        return [
            {
                "name": label,
                "quantity": 1,
                "weight": "",
                "notes": "",
                "systems_ref": None,
                "currency": currency,
                "is_currency_only": True,
            }
        ]

    special_name = str(raw_spec.get("displayName") or raw_spec.get("special") or "").strip()
    if special_name:
        currency = _currency_seed_from_cp(raw_spec.get("containsValue"))
        return [
            {
                "name": special_name,
                "quantity": int(raw_spec.get("quantity") or 1),
                "weight": "",
                "notes": "",
                "systems_ref": None,
                "currency": currency,
                "is_currency_only": False,
            }
        ]
    return []


def _build_equipment_item_spec(
    item_reference: str,
    *,
    item_catalog: dict[str, Any],
    quantity: int = 1,
    display_name: str | None = None,
    special_text: str | None = None,
    contained_value: Any = None,
    forced_entry: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    entry = forced_entry or _resolve_item_entry(item_reference, item_catalog)
    name = display_name or (entry.title if entry is not None else _humanize_item_reference(item_reference))
    currency = _currency_seed_from_cp(contained_value)
    notes_parts = [part for part in (special_text,) if part]
    return {
        "name": name,
        "quantity": max(int(quantity or 1), 1),
        "weight": _format_weight_value((entry.metadata or {}).get("weight")) if entry is not None else "",
        "notes": " ".join(notes_parts).strip(),
        "systems_ref": _systems_ref_from_entry(entry),
        "currency": currency,
        "is_currency_only": False,
    }


def _list_item_entries_for_equipment_type(
    equipment_type: str,
    item_catalog: dict[str, Any],
) -> list[SystemsEntryRecord]:
    by_title = dict(item_catalog.get("by_title") or {})
    exact_titles = list(ITEM_TITLES_BY_EQUIPMENT_TYPE.get(equipment_type) or [])
    if exact_titles:
        return [
            entry
            for title in exact_titles
            for entry in [by_title.get(normalize_lookup(title))]
            if entry is not None
        ]
    type_codes = set(ITEM_TYPE_CODES_BY_EQUIPMENT_TYPE.get(equipment_type) or set())
    if type_codes:
        return sorted(
            [
                entry
                for entry in list(item_catalog.get("entries") or [])
                if str(entry.metadata.get("type") or "").strip() in type_codes
            ],
            key=lambda entry: entry.title.lower(),
        )
    return []


def _describe_equipment_bundle(bundle: list[dict[str, Any]]) -> str:
    return ", ".join(_describe_equipment_spec(spec) for spec in bundle if _describe_equipment_spec(spec))


def _describe_equipment_spec(spec: dict[str, Any]) -> str:
    name = str(spec.get("name") or "").strip()
    quantity = int(spec.get("quantity") or 1)
    if not name:
        return ""
    if quantity > 1:
        return f"{quantity} x {name}"
    return name


def _build_level_one_equipment_catalog(
    equipment_groups: list[dict[str, Any]],
    *,
    selected_campaign_item_specs: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected_specs: list[dict[str, Any]] = []
    for group in equipment_groups:
        options = list(group.get("options") or [])
        if not options:
            continue
        selected_value = str(group.get("selected") or "").strip()
        selected_option = next(
            (option for option in options if str(option.get("value") or "").strip() == selected_value),
            None,
        )
        if selected_option is None:
            selected_option = options[0]
        selected_specs.extend(list(selected_option.get("equipment_bundle") or []))
    selected_specs.extend(list(selected_campaign_item_specs or []))

    merged_catalog: list[dict[str, Any]] = []
    merged_index_by_key: dict[tuple[str, str, str, str, str, bool], int] = {}
    for spec in selected_specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        systems_ref = dict(spec.get("systems_ref") or {})
        page_ref = str(spec.get("page_ref") or "").strip()
        notes = str(spec.get("notes") or "").strip()
        weight = str(spec.get("weight") or "").strip()
        is_currency_only = bool(spec.get("is_currency_only"))
        merge_key = (
            normalize_lookup(name),
            str(systems_ref.get("slug") or ""),
            page_ref,
            notes,
            weight,
            is_currency_only,
        )
        existing_index = merged_index_by_key.get(merge_key)
        if existing_index is None:
            row = {
                "id": f"{slugify(name)}-{len(merged_catalog) + 1}",
                "name": name,
                "default_quantity": max(int(spec.get("quantity") or 1), 1),
                "weight": weight,
                "notes": notes,
                "systems_ref": systems_ref or None,
                "page_ref": page_ref or None,
                "currency": dict(spec.get("currency") or {}),
                "is_currency_only": is_currency_only,
                "source_kind": str(spec.get("source_kind") or "").strip(),
                "campaign_option": dict(spec.get("campaign_option") or {}) or None,
                "is_equipped": _default_equipment_item_equipped(spec, item_catalog=item_catalog),
            }
            merged_index_by_key[merge_key] = len(merged_catalog)
            merged_catalog.append(row)
            continue

        merged_row = merged_catalog[existing_index]
        merged_row["default_quantity"] = int(merged_row.get("default_quantity") or 0) + max(
            int(spec.get("quantity") or 1),
            1,
        )
        merged_row["currency"] = _merge_currency_seed(
            dict(merged_row.get("currency") or {}),
            dict(spec.get("currency") or {}),
        )
    return merged_catalog


def _default_equipment_item_equipped(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
) -> bool:
    if bool(item.get("is_currency_only")):
        return False
    return bool(
        describe_equipment_state_support(
            item,
            item_catalog=item_catalog,
        ).get("supports_equipped_state")
    )


def _format_weight_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, int):
        return f"{value} lb."
    if isinstance(value, float):
        return f"{int(value) if value.is_integer() else value} lb."
    cleaned = _clean_embedded_text(str(value))
    return cleaned


def _currency_seed_from_cp(value: Any) -> dict[str, int]:
    try:
        total_cp = int(value or 0)
    except (TypeError, ValueError):
        return {}
    if total_cp <= 0:
        return {}
    gp, remainder = divmod(total_cp, 100)
    sp, cp = divmod(remainder, 10)
    return {"cp": cp, "sp": sp, "ep": 0, "gp": gp, "pp": 0}


def _collect_currency_seed_from_equipment(equipment_catalog: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}
    for item in equipment_catalog:
        totals = _merge_currency_seed(totals, dict(item.get("currency") or {}))
    return totals
