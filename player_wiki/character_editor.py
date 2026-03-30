from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .auth_store import isoformat, utcnow
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import slugify

CHARACTER_EDITOR_VERSION = "2026-03-29.01"
CUSTOM_FEATURE_CATEGORY = "custom_feature"
CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"
MIN_CUSTOM_FEATURE_ROWS = 3
MIN_CUSTOM_EQUIPMENT_ROWS = 3
FEATURE_ACTIVATION_OPTIONS = (
    ("passive", "Passive"),
    ("action", "Action"),
    ("bonus_action", "Bonus Action"),
    ("reaction", "Reaction"),
    ("special", "Special"),
)
VALID_FEATURE_ACTIVATION_TYPES = {value for value, _ in FEATURE_ACTIVATION_OPTIONS}


class CharacterEditValidationError(ValueError):
    pass


def build_native_character_edit_context(
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = dict(form_values or {})
    proficiency_lists = dict(definition.proficiencies or {})
    manual_features = _manual_custom_features(definition)
    manual_items = _manual_equipment_entries(definition)
    campaign_page_options = _build_campaign_page_options(campaign_page_records or [])

    proficiency_fields = [
        {
            "name": "languages_text",
            "label": "Languages",
            "help_text": "One entry per line. Save the full list you want on the sheet.",
            "value": str(
                values.get("languages_text")
                or _join_multiline_values(proficiency_lists.get("languages") or [])
            ),
        },
        {
            "name": "armor_proficiencies_text",
            "label": "Armor Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("armor_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("armor") or [])
            ),
        },
        {
            "name": "weapon_proficiencies_text",
            "label": "Weapon Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("weapon_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("weapons") or [])
            ),
        },
        {
            "name": "tool_proficiencies_text",
            "label": "Tool Proficiencies",
            "help_text": "One entry per line. Use this for campaign-granted proficiencies or revisions.",
            "value": str(
                values.get("tool_proficiencies_text")
                or _join_multiline_values(proficiency_lists.get("tools") or [])
            ),
        },
    ]

    feature_row_count = max(
        len(manual_features) + 1,
        _max_row_index(values, "custom_feature"),
        MIN_CUSTOM_FEATURE_ROWS,
    )
    feature_rows = []
    for index in range(1, feature_row_count + 1):
        existing = manual_features[index - 1] if index - 1 < len(manual_features) else {}
        feature_rows.append(
            {
                "index": index,
                "id": str(values.get(f"custom_feature_id_{index}") or existing.get("id") or "").strip(),
                "name": str(values.get(f"custom_feature_name_{index}") or existing.get("name") or "").strip(),
                "page_ref": str(
                    values.get(f"custom_feature_page_ref_{index}")
                    or _extract_page_ref_value(existing.get("page_ref"))
                    or ""
                ).strip(),
                "activation_type": _normalize_activation_type(
                    values.get(f"custom_feature_activation_type_{index}")
                    or existing.get("activation_type")
                    or "passive"
                ),
                "description_markdown": str(
                    values.get(f"custom_feature_description_{index}")
                    or existing.get("description_markdown")
                    or ""
                ),
            }
        )

    equipment_row_count = max(
        len(manual_items) + 1,
        _max_row_index(values, "manual_item"),
        MIN_CUSTOM_EQUIPMENT_ROWS,
    )
    equipment_rows = []
    for index in range(1, equipment_row_count + 1):
        existing = manual_items[index - 1] if index - 1 < len(manual_items) else {}
        equipment_rows.append(
            {
                "index": index,
                "id": str(values.get(f"manual_item_id_{index}") or existing.get("id") or "").strip(),
                "name": str(values.get(f"manual_item_name_{index}") or existing.get("name") or "").strip(),
                "page_ref": str(
                    values.get(f"manual_item_page_ref_{index}")
                    or _extract_page_ref_value(existing.get("page_ref"))
                    or ""
                ).strip(),
                "quantity": str(
                    values.get(f"manual_item_quantity_{index}")
                    or existing.get("default_quantity")
                    or ""
                ).strip(),
                "weight": str(values.get(f"manual_item_weight_{index}") or existing.get("weight") or "").strip(),
                "notes": str(values.get(f"manual_item_notes_{index}") or existing.get("notes") or ""),
            }
        )

    return {
        "values": values,
        "proficiency_fields": proficiency_fields,
        "feature_rows": feature_rows,
        "equipment_rows": equipment_rows,
        "activation_options": [
            {"value": value, "label": label}
            for value, label in FEATURE_ACTIVATION_OPTIONS
        ],
        "campaign_page_options": campaign_page_options,
        "existing_managed_equipment": [
            {
                "name": str(item.get("name") or "Item"),
                "quantity": int(item.get("default_quantity") or 0),
                "weight": str(item.get("weight") or "").strip(),
            }
            for item in list(definition.equipment_catalog or [])
            if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
        ],
    }


def apply_native_character_edits(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    values = dict(form_values or {})
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    manual_feature_lookup = {
        str(feature.get("id") or "").strip(): dict(feature)
        for feature in _manual_custom_features(current_definition)
        if str(feature.get("id") or "").strip()
    }
    manual_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in _manual_equipment_entries(current_definition)
        if str(item.get("id") or "").strip()
    }

    proficiencies = {
        "languages": _parse_multiline_values(values.get("languages_text", "")),
        "armor": _parse_multiline_values(values.get("armor_proficiencies_text", "")),
        "weapons": _parse_multiline_values(values.get("weapon_proficiencies_text", "")),
        "tools": _parse_multiline_values(values.get("tool_proficiencies_text", "")),
    }

    used_feature_ids = set(manual_feature_lookup.keys())
    manual_features: list[dict[str, Any]] = []
    seen_feature_names: set[str] = set()
    for index in range(1, max(_max_row_index(values, "custom_feature"), MIN_CUSTOM_FEATURE_ROWS) + 1):
        raw_id = str(values.get(f"custom_feature_id_{index}") or "").strip()
        name = str(values.get(f"custom_feature_name_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"custom_feature_page_ref_{index}") or "",
            campaign_page_lookup,
        )
        if not name and page_ref:
            name = str((campaign_page_lookup.get(page_ref) or {}).get("title") or "").strip()
        description_markdown = str(values.get(f"custom_feature_description_{index}") or "")
        activation_type = _normalize_activation_type(values.get(f"custom_feature_activation_type_{index}") or "passive")
        has_content = bool(raw_id or name or page_ref or description_markdown.strip())
        if not has_content:
            continue
        if not name:
            raise CharacterEditValidationError("Each custom feature needs a name.")
        if activation_type not in VALID_FEATURE_ACTIVATION_TYPES:
            raise CharacterEditValidationError("Choose a valid activation type for each custom feature.")
        normalized_name = slugify(name)
        if normalized_name in seen_feature_names:
            raise CharacterEditValidationError(f"Custom feature '{name}' is listed more than once.")
        seen_feature_names.add(normalized_name)

        existing = deepcopy(manual_feature_lookup.get(raw_id) or {})
        existing.pop("systems_ref", None)
        existing.pop("page_ref", None)
        feature_id = raw_id or _build_unique_manual_id("custom-feature", name, used_feature_ids)
        used_feature_ids.add(feature_id)
        existing.update(
            {
                "id": feature_id,
                "name": name,
                "category": CUSTOM_FEATURE_CATEGORY,
                "source": str(existing.get("source") or "Campaign").strip() or "Campaign",
                "description_markdown": description_markdown.strip(),
                "activation_type": activation_type,
                "tracker_ref": existing.get("tracker_ref"),
            }
        )
        if page_ref:
            existing["page_ref"] = page_ref
        manual_features.append(existing)

    used_item_ids = set(manual_item_lookup.keys())
    inventory_quantity_overrides: dict[str, int] = {}
    manual_items: list[dict[str, Any]] = []
    for index in range(1, max(_max_row_index(values, "manual_item"), MIN_CUSTOM_EQUIPMENT_ROWS) + 1):
        raw_id = str(values.get(f"manual_item_id_{index}") or "").strip()
        name = str(values.get(f"manual_item_name_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"manual_item_page_ref_{index}") or "",
            campaign_page_lookup,
        )
        if not name and page_ref:
            name = str((campaign_page_lookup.get(page_ref) or {}).get("title") or "").strip()
        quantity_text = str(values.get(f"manual_item_quantity_{index}") or "").strip()
        weight = str(values.get(f"manual_item_weight_{index}") or "").strip()
        notes = str(values.get(f"manual_item_notes_{index}") or "")
        has_content = bool(raw_id or name or page_ref or quantity_text or weight or notes.strip())
        if not has_content:
            continue
        if not name:
            raise CharacterEditValidationError("Each custom equipment row needs an item name.")
        quantity = _parse_manual_item_quantity(quantity_text)

        existing = deepcopy(manual_item_lookup.get(raw_id) or {})
        existing.pop("systems_ref", None)
        existing.pop("page_ref", None)
        item_id = raw_id or _build_unique_manual_id("manual-item", name, used_item_ids)
        used_item_ids.add(item_id)
        existing.update(
            {
                "id": item_id,
                "name": name,
                "default_quantity": quantity,
                "weight": weight,
                "notes": notes.strip(),
                "source_kind": CUSTOM_EQUIPMENT_SOURCE_KIND,
            }
        )
        if page_ref:
            existing["page_ref"] = page_ref
        manual_items.append(existing)
        inventory_quantity_overrides[item_id] = quantity

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["proficiencies"] = proficiencies
    payload["features"] = [
        dict(feature)
        for feature in list(current_definition.features or [])
        if str(feature.get("category") or "") != CUSTOM_FEATURE_CATEGORY
    ] + manual_features
    payload["equipment_catalog"] = [
        dict(item)
        for item in list(current_definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
    ] + manual_items

    definition = CharacterDefinition.from_dict(payload)
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=str(current_import_metadata.source_path or f"managed://{campaign_slug}/{current_definition.character_slug}"),
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_EDITOR_VERSION,
        import_status="managed",
        warnings=[],
    )
    return definition, import_metadata, inventory_quantity_overrides


def _manual_custom_features(definition: CharacterDefinition) -> list[dict[str, Any]]:
    return [
        dict(feature)
        for feature in list(definition.features or [])
        if str(feature.get("category") or "") == CUSTOM_FEATURE_CATEGORY
    ]


def _manual_equipment_entries(definition: CharacterDefinition) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") == CUSTOM_EQUIPMENT_SOURCE_KIND
    ]


def _build_campaign_page_options(campaign_page_records: list[Any]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for record in list(campaign_page_records or []):
        page_ref = _extract_page_ref_value(getattr(record, "page_ref", ""))
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        section = str(getattr(page, "section", "") or "").strip()
        subsection = str(getattr(page, "subsection", "") or "").strip()
        label_parts = [title]
        if section:
            if subsection:
                label_parts.append(f"{section} / {subsection}")
            else:
                label_parts.append(section)
        options.append({"value": page_ref, "label": " | ".join(label_parts), "title": title})
    return options


def _build_campaign_page_lookup(campaign_page_records: list[Any]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for option in _build_campaign_page_options(campaign_page_records):
        page_ref = str(option.get("value") or "").strip()
        if not page_ref:
            continue
        lookup[page_ref] = {
            "page_ref": page_ref,
            "label": str(option.get("label") or page_ref),
            "title": str(option.get("title") or page_ref),
        }
    return lookup


def _extract_page_ref_value(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("page_ref") or payload.get("slug") or "").strip()
    return str(payload or "").strip()


def _normalize_selected_campaign_page_ref(
    raw_value: Any,
    campaign_page_lookup: dict[str, dict[str, str]],
) -> str:
    page_ref = _extract_page_ref_value(raw_value)
    if not page_ref:
        return ""
    if page_ref not in campaign_page_lookup:
        raise CharacterEditValidationError("Choose a valid linked campaign page.")
    return page_ref


def _join_multiline_values(values: list[str]) -> str:
    return "\n".join(str(value).strip() for value in list(values or []) if str(value).strip())


def _parse_multiline_values(raw_value: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in str(raw_value or "").replace("\r", "").split("\n"):
        for fragment in str(line).split(","):
            value = str(fragment).strip()
            normalized_value = value.casefold()
            if not value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            values.append(value)
    return values


def _parse_manual_item_quantity(raw_value: str) -> int:
    if not str(raw_value or "").strip():
        return 1
    try:
        quantity = int(str(raw_value).strip())
    except ValueError as exc:
        raise CharacterEditValidationError("Custom equipment quantities must be whole numbers.") from exc
    if quantity < 0:
        raise CharacterEditValidationError("Custom equipment quantities cannot be negative.")
    return quantity


def _normalize_activation_type(raw_value: Any) -> str:
    value = str(raw_value or "passive").strip().lower()
    return value if value in VALID_FEATURE_ACTIVATION_TYPES else "passive"


def _build_unique_manual_id(prefix: str, name: str, used_ids: set[str]) -> str:
    base = slugify(name) or prefix
    candidate = f"{prefix}-{base}"
    index = 2
    while candidate in used_ids:
        candidate = f"{prefix}-{base}-{index}"
        index += 1
    return candidate


def _max_row_index(values: dict[str, str], prefix: str) -> int:
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_[a-z_]+_(\d+)$")
    for key in dict(values or {}):
        match = pattern.match(str(key))
        if match is None:
            continue
        highest = max(highest, int(match.group(1)))
    return highest
