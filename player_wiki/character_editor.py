from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .auth_store import isoformat, utcnow
from .character_adjustments import (
    apply_manual_stat_adjustments,
    apply_stat_adjustments,
    normalize_manual_stat_adjustments,
    strip_manual_stat_adjustments,
)
from .character_builder import (
    _add_bonus_known_spell_to_payloads,
    _add_spell_to_payloads,
    _automatic_spell_support_grants,
    _build_spell_support_choice_fields,
    _build_spell_support_replacement_fields,
    _merge_spell_mark,
    _prepared_spell_count_for_level,
    _resolve_builder_choices,
    _resolve_spell_entry,
    _spell_entry_level,
    _spell_lookup_key,
    _spell_payload_key,
    _spell_progression_value,
    _spell_selection_values_by_mark,
    _spellcasting_mode_for_class,
    normalize_definition_to_native_model,
)
from .character_campaign_options import (
    FEATURE_LIKE_CAMPAIGN_OPTION_KINDS,
    build_campaign_page_character_option,
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
)
from .character_importer import converge_imported_definition
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import normalize_lookup
from .repository import slugify

CHARACTER_EDITOR_VERSION = "2026-04-06.01"
CUSTOM_FEATURE_CATEGORY = "custom_feature"
CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"
CUSTOM_FEATURE_TRACKER_PREFIX = "manual-feature-tracker"
CAMPAIGN_ITEMS_SECTION = "Items"
MIN_CUSTOM_FEATURE_ROWS = 3
MIN_CUSTOM_EQUIPMENT_ROWS = 3
SPELL_MANAGEMENT_QUERY_MIN_LENGTH = 2
FEATURE_ACTIVATION_OPTIONS = (
    ("passive", "Passive"),
    ("action", "Action"),
    ("bonus_action", "Bonus Action"),
    ("reaction", "Reaction"),
    ("special", "Special"),
)
VALID_FEATURE_ACTIVATION_TYPES = {value for value, _ in FEATURE_ACTIVATION_OPTIONS}
FEATURE_RESOURCE_RESET_OPTIONS = (
    ("manual", "Manual"),
    ("short_rest", "Short Rest"),
    ("long_rest", "Long Rest"),
)
VALID_FEATURE_RESOURCE_RESET_TYPES = {value for value, _ in FEATURE_RESOURCE_RESET_OPTIONS}
STAT_ADJUSTMENT_FIELDS = (
    ("max_hp", "Max HP Adjustment", "Apply a persistent bonus or penalty to max HP."),
    ("armor_class", "Armor Class Adjustment", "Apply a persistent bonus or penalty to Armor Class."),
    ("initiative_bonus", "Initiative Adjustment", "Apply a persistent bonus or penalty to initiative."),
    ("speed", "Speed Adjustment (ft.)", "Apply a persistent speed change in feet."),
    ("passive_perception", "Passive Perception Adjustment", "Apply a persistent bonus or penalty to passive Perception."),
    ("passive_insight", "Passive Insight Adjustment", "Apply a persistent bonus or penalty to passive Insight."),
    ("passive_investigation", "Passive Investigation Adjustment", "Apply a persistent bonus or penalty to passive Investigation."),
)


class CharacterEditValidationError(ValueError):
    pass


def build_character_spell_management_context(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
) -> dict[str, Any] | None:
    spellcasting = dict(definition.spellcasting or {})
    if not spellcasting:
        return None

    spell_catalog = dict(spell_catalog or {})
    class_name = _spell_management_class_name(definition, spellcasting=spellcasting)
    mode = _spellcasting_mode_for_class(class_name, selected_class=selected_class) if class_name else ""
    current_level = _character_total_level(definition)
    slot_progression = [
        dict(slot or {})
        for slot in list(spellcasting.get("slot_progression") or [])
    ]
    max_spell_level = max((int(slot.get("level") or 0) for slot in slot_progression), default=0)

    class_names = [
        str(dict(row or {}).get("class_name") or "").strip()
        for row in list((definition.profile or {}).get("classes") or [])
        if str(dict(row or {}).get("class_name") or "").strip()
    ]
    distinct_class_names = {
        normalize_lookup(name)
        for name in class_names
        if str(name).strip()
    }
    unavailable_message = ""
    if len(distinct_class_names) > 1:
        unavailable_message = "Spell management on the sheet currently supports single-class casters only."
    elif not class_name or not mode:
        unavailable_message = "This sheet does not currently have a supported class spellcasting model to edit here."

    rows = _build_spell_management_rows(
        definition,
        spell_catalog=spell_catalog,
        mode=mode,
        class_name=class_name,
    )

    mutable_cantrip_count = sum(1 for row in rows if row["counts_against_cantrip_limit"])
    mutable_known_count = sum(1 for row in rows if row["counts_against_known_limit"])
    mutable_prepared_count = sum(1 for row in rows if row["counts_against_prepared_limit"])
    mutable_spellbook_count = sum(1 for row in rows if row["counts_against_spellbook_total"])
    fixed_spell_count = sum(1 for row in rows if row["is_fixed"])

    ability_scores = _spell_management_ability_scores(definition)
    target_cantrip_count = (
        _spell_progression_value(class_name, "cantrip_progression", current_level, selected_class=selected_class)
        if class_name and mode
        else 0
    )
    target_known_count = (
        _spell_progression_value(class_name, "spells_known_progression", current_level, selected_class=selected_class)
        if mode == "known"
        else 0
    )
    target_prepared_count = (
        _prepared_spell_count_for_level(class_name, ability_scores, current_level, selected_class=selected_class)
        if mode in {"prepared", "wizard"}
        else 0
    )

    counts: list[dict[str, str]] = []
    if target_cantrip_count:
        counts.append(
            {
                "label": "Cantrips",
                "value": f"{mutable_cantrip_count} / {target_cantrip_count}",
            }
        )
    if mode == "known":
        counts.append(
            {
                "label": "Known spells",
                "value": f"{mutable_known_count} / {target_known_count}",
            }
        )
    elif mode == "prepared":
        counts.append(
            {
                "label": "Prepared spells",
                "value": f"{mutable_prepared_count} / {target_prepared_count}",
            }
        )
    elif mode == "wizard":
        counts.append(
            {
                "label": "Prepared spells",
                "value": f"{mutable_prepared_count} / {target_prepared_count}",
            }
        )
        counts.append(
            {
                "label": "Spellbook spells",
                "value": str(mutable_spellbook_count),
            }
        )
    if fixed_spell_count:
        counts.append(
            {
                "label": "Fixed feature spells",
                "value": str(fixed_spell_count),
            }
        )

    can_manage = bool(mode and class_name and not unavailable_message and list(spell_catalog.get("entries") or []))
    if not can_manage and not unavailable_message and mode:
        unavailable_message = "Enable Systems spell entries in this campaign to manage spells from the character sheet."

    spell_add_label = {
        "known": "Add known spell",
        "prepared": "Prepare spell",
        "wizard": "Add spellbook spell",
    }.get(mode, "Add spell")
    rules_note = {
        "known": (
            "Classic known-spell casters keep a fixed list of leveled spells they know. "
            "Use this manager to maintain that durable list and its cantrips."
        ),
        "prepared": (
            "Classic prepared casters choose daily prepared spells from their class list. "
            "Always-prepared feature spells stay fixed and do not count against the prepared total shown here."
        ),
        "wizard": (
            "Wizards prepare spells from their spellbook. Add new spells to the spellbook here, "
            "then mark which spellbook spells are currently prepared."
        ),
    }.get(mode, "")

    return {
        "class_name": class_name,
        "mode": mode,
        "mode_label": {
            "known": "Known spells",
            "prepared": "Prepared spells",
            "wizard": "Wizard spellbook",
        }.get(mode, "Spellcasting"),
        "current_level": current_level,
        "max_spell_level": max_spell_level,
        "target_cantrip_count": target_cantrip_count,
        "target_known_count": target_known_count,
        "target_prepared_count": target_prepared_count,
        "current_cantrip_count": mutable_cantrip_count,
        "current_known_count": mutable_known_count,
        "current_prepared_count": mutable_prepared_count,
        "current_spellbook_count": mutable_spellbook_count,
        "counts": counts,
        "rows": rows,
        "can_manage": can_manage,
        "unavailable_message": unavailable_message,
        "rules_note": rules_note,
        "show_cantrip_form": bool(mode and target_cantrip_count),
        "can_add_cantrip": bool(can_manage and mutable_cantrip_count < target_cantrip_count),
        "show_spell_form": bool(mode and max_spell_level > 0),
        "can_add_spell": bool(
            can_manage
            and max_spell_level > 0
            and (
                mode == "wizard"
                or (mode == "known" and mutable_known_count < target_known_count)
                or (mode == "prepared" and mutable_prepared_count < target_prepared_count)
            )
        ),
        "spell_add_kind": "spellbook" if mode == "wizard" else "spell",
        "spell_add_label": spell_add_label,
    }


def search_character_spell_management_options(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
    query: str,
    kind: str,
    limit: int = 20,
) -> tuple[list[dict[str, str]], str]:
    manager = build_character_spell_management_context(
        definition,
        spell_catalog=spell_catalog,
        selected_class=selected_class,
    )
    if manager is None:
        return [], "This sheet does not currently have spellcasting content."
    if not manager.get("can_manage"):
        return [], str(manager.get("unavailable_message") or "This sheet cannot manage spells here yet.")

    clean_kind = str(kind or "").strip().lower()
    if clean_kind not in {"cantrip", "spell", "spellbook"}:
        return [], "Choose a valid spell search type."
    if clean_kind == "spellbook" and manager.get("mode") != "wizard":
        return [], "Only wizard sheets use spellbook additions."

    clean_query = normalize_lookup(query)
    if len(clean_query) < SPELL_MANAGEMENT_QUERY_MIN_LENGTH:
        return [], "Type at least 2 letters to search eligible class spells."

    class_name = str(manager.get("class_name") or "").strip()
    max_spell_level = int(manager.get("max_spell_level") or 0)
    existing_keys = {
        str(row.get("catalog_key") or row.get("spell_key") or "").strip()
        for row in list(manager.get("rows") or [])
        if str(row.get("catalog_key") or row.get("spell_key") or "").strip()
    }
    results: list[dict[str, str]] = []
    catalog_entries = sorted(
        list((spell_catalog or {}).get("entries") or []),
        key=lambda entry: (int(_spell_entry_level(entry)), str(entry.title or "").lower()),
    )
    for entry in catalog_entries:
        if not _spell_entry_matches_management_class_list(entry, class_name):
            continue
        level = _spell_entry_level(entry)
        if clean_kind == "cantrip":
            if level != 0:
                continue
        else:
            if level <= 0 or level > max_spell_level:
                continue
        if str(entry.slug or "").strip() in existing_keys:
            continue
        searchable_text = normalize_lookup(f"{entry.title} {entry.search_text}")
        if clean_query not in searchable_text:
            continue
        level_label = _spell_management_level_label(level)
        subtitle = " - ".join(part for part in (level_label, str(entry.source_id or "").strip()) if part)
        select_label = f"{entry.title} - {subtitle}" if subtitle else entry.title
        results.append(
            {
                "entry_slug": str(entry.slug or "").strip(),
                "title": str(entry.title or "").strip(),
                "level_label": level_label,
                "source_id": str(entry.source_id or "").strip(),
                "select_label": select_label,
            }
        )
        if len(results) >= limit:
            break

    if results:
        label = "cantrips" if clean_kind == "cantrip" else "spells"
        return results, f"Found {len(results)} matching {label}."
    return [], "No eligible class spells matched that search."


def apply_character_spell_management_edit(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    spell_catalog: dict[str, Any] | None = None,
    selected_class: Any | None = None,
    operation: str,
    spell_key: str = "",
    selected_value: str = "",
    kind: str = "",
    prepared_value: str = "",
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    manager = build_character_spell_management_context(
        current_definition,
        spell_catalog=spell_catalog,
        selected_class=selected_class,
    )
    if manager is None:
        raise CharacterEditValidationError("This sheet does not currently have spellcasting content.")
    if not manager.get("can_manage"):
        raise CharacterEditValidationError(
            str(manager.get("unavailable_message") or "This sheet cannot manage spells here yet.")
        )

    rows_by_key = {
        str(row.get("spell_key") or "").strip(): dict(row)
        for row in list(manager.get("rows") or [])
        if str(row.get("spell_key") or "").strip()
    }
    spells_by_key = {
        key: deepcopy(dict(row.get("payload") or {}))
        for key, row in rows_by_key.items()
    }
    catalog_keys = {
        str(row.get("catalog_key") or row.get("spell_key") or "").strip()
        for row in list(rows_by_key.values())
        if str(row.get("catalog_key") or row.get("spell_key") or "").strip()
    }
    clean_operation = str(operation or "").strip().lower()
    clean_kind = str(kind or "").strip().lower()
    clean_spell_key = str(spell_key or "").strip()
    clean_selected_value = str(selected_value or "").strip()
    clean_mode = str(manager.get("mode") or "").strip()

    if clean_operation == "add":
        if not clean_selected_value:
            raise CharacterEditValidationError("Choose a spell to add.")
        resolved_entry = _resolve_spell_entry(clean_selected_value, dict(spell_catalog or {}))
        resolved_key = (
            str(resolved_entry.slug or "").strip()
            if resolved_entry is not None
            else _spell_lookup_key(clean_selected_value, dict(spell_catalog or {}))
        )
        if resolved_key in catalog_keys:
            raise CharacterEditValidationError("That spell is already on this sheet.")
        if clean_kind == "cantrip":
            if not bool(manager.get("can_add_cantrip")):
                raise CharacterEditValidationError("This sheet is already at its current cantrip count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Cantrip",
            )
        elif clean_kind == "spell" and clean_mode == "known":
            if not bool(manager.get("can_add_spell")):
                raise CharacterEditValidationError("This sheet is already at its current known-spell count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Known",
            )
        elif clean_kind == "spell" and clean_mode == "prepared":
            if not bool(manager.get("can_add_spell")):
                raise CharacterEditValidationError("This sheet is already at its current prepared-spell count.")
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Prepared",
            )
        elif clean_kind == "spellbook" and clean_mode == "wizard":
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=clean_selected_value,
                spell_catalog=dict(spell_catalog or {}),
                mark="Spellbook",
            )
        else:
            raise CharacterEditValidationError("Choose a valid spell-management action.")
    elif clean_operation == "remove":
        row = rows_by_key.get(clean_spell_key)
        if row is None:
            raise CharacterEditValidationError("Choose a valid spell to remove.")
        if not bool(row.get("can_remove")):
            raise CharacterEditValidationError("That spell is fixed by class or feature rules and cannot be removed here.")
        spells_by_key.pop(clean_spell_key, None)
    elif clean_operation == "update":
        row = rows_by_key.get(clean_spell_key)
        if row is None:
            raise CharacterEditValidationError("Choose a valid spell to update.")
        if not bool(row.get("can_toggle_prepared")):
            raise CharacterEditValidationError("That spell cannot have its prepared state changed here.")
        set_prepared = str(prepared_value or "").strip() in {"1", "true", "yes", "on"}
        if (
            set_prepared
            and not bool(row.get("is_prepared"))
            and clean_mode == "wizard"
            and int(manager.get("current_prepared_count") or 0) >= int(manager.get("target_prepared_count") or 0)
        ):
            raise CharacterEditValidationError("This wizard is already at the current prepared-spell count.")
        payload = deepcopy(spells_by_key.get(clean_spell_key) or {})
        payload["mark"] = "Prepared + Spellbook" if set_prepared else "Spellbook"
        spells_by_key[clean_spell_key] = payload
    else:
        raise CharacterEditValidationError("Choose a valid spell-management action.")

    payload = deepcopy(current_definition.to_dict())
    next_spellcasting = dict(payload.get("spellcasting") or {})
    next_spellcasting["spells"] = sorted(
        list(spells_by_key.values()),
        key=lambda value: _spell_management_payload_sort_key(value, dict(spell_catalog or {})),
    )
    payload["spellcasting"] = next_spellcasting

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
        )
    else:
        definition = normalize_definition_to_native_model(definition)
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata, {}


def _spell_management_class_name(
    definition: CharacterDefinition,
    *,
    spellcasting: dict[str, Any],
) -> str:
    clean_spellcasting_class = str(spellcasting.get("spellcasting_class") or "").strip()
    if clean_spellcasting_class:
        return clean_spellcasting_class

    profile = dict(definition.profile or {})
    class_ref = dict(profile.get("class_ref") or {})
    class_ref_title = str(class_ref.get("title") or "").strip()
    if class_ref_title:
        return class_ref_title

    for row in list(profile.get("classes") or []):
        class_name = str(dict(row or {}).get("class_name") or "").strip()
        if class_name:
            return class_name

    class_level_text = str(profile.get("class_level_text") or "").strip()
    match = re.match(r"([A-Za-z][A-Za-z' -]+)", class_level_text)
    return str(match.group(1) or "").strip() if match is not None else ""


def _spell_management_ability_scores(definition: CharacterDefinition) -> dict[str, int]:
    ability_scores_payload = dict((definition.stats or {}).get("ability_scores") or {})
    return {
        ability_key: int(dict(ability_scores_payload.get(ability_key) or {}).get("score") or 10)
        for ability_key in ("str", "dex", "con", "int", "wis", "cha")
    }


def _build_spell_management_rows(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any],
    mode: str,
    class_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_spell_payload in list((definition.spellcasting or {}).get("spells") or []):
        normalized_payload, spell_entry, spell_level = _normalize_spell_management_payload(
            raw_spell_payload,
            spell_catalog=spell_catalog,
            mode=mode,
            class_name=class_name,
        )
        spell_key = _spell_payload_key(normalized_payload)
        if not spell_key:
            continue

        normalized_mark = normalize_lookup(str(normalized_payload.get("mark") or "").strip())
        source_label = str(normalized_payload.get("source") or "").strip()
        is_cantrip = spell_level == 0
        is_prepared = bool(
            not is_cantrip
            and (
                bool(normalized_payload.get("is_always_prepared"))
                or "prepared" in normalized_mark
            )
        )
        in_spellbook = bool(not is_cantrip and "spellbook" in normalized_mark)
        is_fixed = bool(normalized_payload.get("is_always_prepared") or normalized_payload.get("is_bonus_known"))

        managed_group = ""
        if is_cantrip:
            managed_group = "cantrip"
        elif mode == "known":
            managed_group = "known"
        elif mode == "prepared":
            managed_group = "prepared"
        elif mode == "wizard":
            managed_group = "spellbook"

        badges: list[str] = []
        if is_cantrip:
            badges.append("Cantrip")
        elif mode == "wizard" and in_spellbook:
            badges.append("Spellbook")
        elif mode == "known":
            badges.append("Known")
        elif mode == "prepared" or is_prepared:
            badges.append("Prepared")
        if bool(normalized_payload.get("is_always_prepared")):
            badges.append("Always prepared")
        elif bool(normalized_payload.get("is_bonus_known")):
            badges.append("Feature granted")

        management_note = ""
        if bool(normalized_payload.get("is_always_prepared")) and source_label:
            management_note = f"Always prepared from {source_label}."
        elif bool(normalized_payload.get("is_bonus_known")) and source_label:
            management_note = f"Granted by {source_label}."

        rows.append(
            {
                "spell_key": spell_key,
                "catalog_key": (
                    str(spell_entry.slug or "").strip()
                    if spell_entry is not None
                    else spell_key
                ),
                "name": str(normalized_payload.get("name") or spell_key).strip() or spell_key,
                "payload": normalized_payload,
                "spell_level": spell_level,
                "level_label": _spell_management_level_label(spell_level),
                "is_cantrip": is_cantrip,
                "is_fixed": is_fixed,
                "is_prepared": is_prepared,
                "in_spellbook": in_spellbook,
                "managed_group": managed_group,
                "badges": badges,
                "management_note": management_note,
                "counts_against_cantrip_limit": bool(is_cantrip and not bool(normalized_payload.get("is_bonus_known"))),
                "counts_against_known_limit": bool(
                    not is_cantrip
                    and managed_group == "known"
                    and not bool(normalized_payload.get("is_bonus_known"))
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "counts_against_prepared_limit": bool(
                    not is_cantrip
                    and is_prepared
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "counts_against_spellbook_total": bool(not is_cantrip and in_spellbook),
                "can_remove": not is_fixed,
                "can_toggle_prepared": bool(
                    mode == "wizard"
                    and not is_cantrip
                    and in_spellbook
                    and not bool(normalized_payload.get("is_always_prepared"))
                ),
                "remove_label": _spell_management_remove_label(
                    mode=mode,
                    is_cantrip=is_cantrip,
                    is_prepared=is_prepared,
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: _spell_management_payload_sort_key(dict(row.get("payload") or {}), spell_catalog),
    )


def _normalize_spell_management_payload(
    raw_spell_payload: dict[str, Any],
    *,
    spell_catalog: dict[str, Any],
    mode: str,
    class_name: str,
) -> tuple[dict[str, Any], Any | None, int]:
    payload = deepcopy(dict(raw_spell_payload or {}))
    spell_entry = _spell_management_entry_for_payload(payload, spell_catalog)
    if spell_entry is not None and not dict(payload.get("systems_ref") or {}):
        payload["systems_ref"] = {
            "entry_key": str(spell_entry.entry_key or "").strip(),
            "entry_type": str(spell_entry.entry_type or "").strip(),
            "title": str(spell_entry.title or "").strip(),
            "slug": str(spell_entry.slug or "").strip(),
            "source_id": str(spell_entry.source_id or "").strip(),
        }

    spell_level = _spell_entry_level(spell_entry) if spell_entry is not None else int(payload.get("level") or 0)
    source_label = str(payload.get("source") or "").strip()
    normalized_source = normalize_lookup(source_label)
    normalized_mark = normalize_lookup(str(payload.get("mark") or "").strip())
    always_prepared = bool(payload.get("is_always_prepared")) or normalize_lookup("always prepared") in normalized_source
    feature_grant = _spell_management_is_feature_grant_source(
        source_label,
        class_name=class_name,
        spell_payload=payload,
    )
    bonus_known = bool(payload.get("is_bonus_known")) or feature_grant

    payload["is_always_prepared"] = always_prepared
    payload["is_bonus_known"] = bonus_known

    if spell_level == 0:
        payload["mark"] = "Cantrip"
        return payload, spell_entry, spell_level

    if mode == "wizard":
        if "spellbook" in normalized_mark:
            payload["mark"] = "Prepared + Spellbook" if "prepared" in normalized_mark else "Spellbook"
        elif normalized_mark in {"o", "p", "po"} or not normalized_mark:
            payload["mark"] = "Prepared + Spellbook"
        elif "prepared" in normalized_mark:
            payload["mark"] = "Prepared + Spellbook"
        else:
            payload["mark"] = "Spellbook"
        if always_prepared and "prepared" not in normalize_lookup(str(payload.get("mark") or "")):
            payload["mark"] = "Prepared + Spellbook"
        return payload, spell_entry, spell_level

    if mode == "prepared":
        payload["mark"] = "Prepared"
        return payload, spell_entry, spell_level

    if mode == "known":
        payload["mark"] = "Known"
        return payload, spell_entry, spell_level

    if normalized_mark == "o":
        payload["mark"] = ""
    elif normalized_mark == "p":
        payload["mark"] = "Prepared"
    elif normalized_mark == "po":
        payload["mark"] = "Prepared"
    return payload, spell_entry, spell_level


def _spell_management_entry_for_payload(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
):
    payload_key = _spell_payload_key(spell_payload)
    if payload_key:
        spell_entry = _resolve_spell_entry(payload_key, spell_catalog)
        if spell_entry is not None:
            return spell_entry
    spell_name = str(spell_payload.get("name") or "").strip()
    if spell_name:
        return _resolve_spell_entry(spell_name, spell_catalog)
    return None


def _spell_management_is_feature_grant_source(
    source_label: str,
    *,
    class_name: str,
    spell_payload: dict[str, Any],
) -> bool:
    clean_source = normalize_lookup(source_label)
    clean_class_name = normalize_lookup(class_name)
    clean_systems_source = normalize_lookup(str(dict(spell_payload.get("systems_ref") or {}).get("source_id") or ""))
    if not clean_source or not clean_class_name:
        return False
    if clean_systems_source and clean_source == clean_systems_source:
        return False
    if clean_source == clean_class_name:
        return False
    if clean_source.startswith(f"{clean_class_name} "):
        return False
    return True


def _spell_entry_matches_management_class_list(entry, class_name: str) -> bool:
    metadata = dict((getattr(entry, "metadata", {}) or {}))
    class_lists = dict(metadata.get("class_lists") or {})
    clean_class_name = normalize_lookup(class_name)
    for class_names in class_lists.values():
        for candidate in list(class_names or []):
            if normalize_lookup(candidate) == clean_class_name:
                return True
    return False


def _spell_management_payload_sort_key(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> tuple[int, str]:
    spell_entry = _spell_management_entry_for_payload(spell_payload, spell_catalog)
    spell_level = _spell_entry_level(spell_entry) if spell_entry is not None else int(spell_payload.get("level") or 0)
    spell_name = str((spell_entry.title if spell_entry is not None else spell_payload.get("name")) or "").strip()
    return spell_level, spell_name.lower(), spell_name


def _spell_management_level_label(level: int) -> str:
    clean_level = int(level or 0)
    if clean_level <= 0:
        return "Cantrip"
    if clean_level == 1:
        return "1st-level"
    if clean_level == 2:
        return "2nd-level"
    if clean_level == 3:
        return "3rd-level"
    return f"{clean_level}th-level"


def _spell_management_remove_label(*, mode: str, is_cantrip: bool, is_prepared: bool) -> str:
    if is_cantrip:
        return "Remove cantrip"
    if mode == "prepared" and is_prepared:
        return "Unprepare spell"
    if mode == "wizard":
        return "Remove from spellbook"
    return "Remove spell"


def build_managed_character_import_metadata(
    campaign_slug: str,
    character_slug: str,
    current_import_metadata: CharacterImportMetadata,
    *,
    parser_version: str = CHARACTER_EDITOR_VERSION,
) -> CharacterImportMetadata:
    return CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        source_path=str(
            current_import_metadata.source_path or f"managed://{campaign_slug}/{character_slug}"
        ),
        imported_at_utc=isoformat(utcnow()),
        parser_version=parser_version,
        import_status="managed",
        warnings=[],
    )


def normalize_custom_equipment_entry(
    *,
    name: str,
    quantity: str | int,
    weight: str = "",
    notes: str = "",
    existing_item: dict[str, Any] | None = None,
    raw_id: str = "",
    used_item_ids: set[str] | None = None,
    page_ref: str = "",
    campaign_option: dict[str, Any] | None = None,
    systems_ref: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise CharacterEditValidationError("Each custom equipment row needs an item name.")

    parsed_quantity = _parse_manual_item_quantity(str(quantity or "").strip())
    normalized_page_ref = str(page_ref or "").strip()
    normalized_campaign_option = dict(campaign_option or {})
    normalized_systems_ref = {
        key: value
        for key, value in dict(systems_ref or {}).items()
        if str(key or "").strip() and value not in (None, "", [], {})
    }

    existing = deepcopy(existing_item or {})
    existing.pop("campaign_option", None)
    existing.pop("systems_ref", None)
    existing.pop("page_ref", None)

    reserved_ids = set(used_item_ids or set())
    preserved_id = str(raw_id or existing.get("id") or "").strip()
    if preserved_id:
        reserved_ids.discard(preserved_id)
    item_id = preserved_id or _build_unique_manual_id("manual-item", clean_name, reserved_ids)
    reserved_ids.add(item_id)

    existing.update(
        {
            "id": item_id,
            "name": clean_name,
            "default_quantity": parsed_quantity,
            "weight": str(weight or "").strip(),
            "notes": str(notes or "").strip(),
            "source_kind": CUSTOM_EQUIPMENT_SOURCE_KIND,
            "campaign_option": normalized_campaign_option or None,
        }
    )
    if normalized_page_ref:
        existing["page_ref"] = normalized_page_ref
    if normalized_systems_ref:
        existing["systems_ref"] = normalized_systems_ref
    return existing, parsed_quantity


def apply_equipment_catalog_edit(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    *,
    campaign_page_records: list[Any] | None = None,
    target_item_id: str | None = None,
    remove_item_id: str | None = None,
    name: str = "",
    quantity: str | int = "",
    weight: str = "",
    notes: str = "",
    page_ref: str = "",
    systems_ref: dict[str, Any] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    manual_items = _manual_equipment_entries(current_definition)
    manual_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in manual_items
        if str(item.get("id") or "").strip()
    }

    normalized_remove_item_id = str(remove_item_id or "").strip()
    if normalized_remove_item_id:
        if normalized_remove_item_id not in manual_item_lookup:
            raise CharacterEditValidationError("Choose a valid supplemental equipment entry to remove.")
        next_manual_items = [
            dict(item)
            for item in manual_items
            if str(item.get("id") or "").strip() != normalized_remove_item_id
        ]
        quantity_overrides: dict[str, int] = {}
    else:
        normalized_target_item_id = str(target_item_id or "").strip()
        existing_item = manual_item_lookup.get(normalized_target_item_id) if normalized_target_item_id else None
        if normalized_target_item_id and existing_item is None:
            raise CharacterEditValidationError("Choose a valid supplemental equipment entry to update.")

        normalized_page_ref = _normalize_selected_campaign_page_ref(page_ref, campaign_page_lookup)
        campaign_option = _editable_campaign_option_for_page_ref(
            normalized_page_ref,
            campaign_page_lookup,
            default_kind="item",
        )
        resolved_name = str(
            name
            or (campaign_option or {}).get("item_name")
            or (campaign_page_lookup.get(normalized_page_ref) or {}).get("title")
            or ""
        ).strip()
        used_item_ids = set(manual_item_lookup.keys())
        if normalized_target_item_id:
            used_item_ids.discard(normalized_target_item_id)
        next_item, parsed_quantity = normalize_custom_equipment_entry(
            name=resolved_name,
            quantity=quantity,
            weight=weight,
            notes=notes,
            existing_item=existing_item,
            raw_id=normalized_target_item_id,
            used_item_ids=used_item_ids,
            page_ref=normalized_page_ref,
            campaign_option=campaign_option,
            systems_ref=systems_ref,
        )
        next_manual_items = [
            dict(item)
            for item in manual_items
            if str(item.get("id") or "").strip() != str(next_item.get("id") or "").strip()
        ]
        next_manual_items.append(next_item)
        quantity_overrides = {str(next_item.get("id") or "").strip(): parsed_quantity}

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["equipment_catalog"] = [
        dict(item)
        for item in list(current_definition.equipment_catalog or [])
        if str(item.get("source_kind") or "") != CUSTOM_EQUIPMENT_SOURCE_KIND
    ] + next_manual_items

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
        )
    else:
        definition = normalize_definition_to_native_model(definition)
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
    )
    return definition, import_metadata, quantity_overrides


def build_native_character_edit_context(
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
    form_values: dict[str, str] | None = None,
    spell_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = dict(form_values or {})
    spell_catalog = dict(spell_catalog or {})
    proficiency_lists = _display_proficiency_lists_for_editor(definition)
    manual_features = _manual_custom_features(definition)
    manual_items = _manual_equipment_entries(definition)
    resource_template_lookup = {
        str(template.get("id") or "").strip(): dict(template)
        for template in list(definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    stat_adjustments = normalize_manual_stat_adjustments((definition.stats or {}).get("manual_adjustments"))
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    campaign_page_options = _build_campaign_page_options(campaign_page_records or [])
    equipment_linked_page_refs = {
        _extract_page_ref_value(item.get("page_ref"))
        for item in list(manual_items or [])
        if _extract_page_ref_value(item.get("page_ref"))
    }
    equipment_page_options = _build_campaign_page_options(
        campaign_page_records or [],
        allowed_sections={CAMPAIGN_ITEMS_SECTION},
        include_page_refs=equipment_linked_page_refs,
    )
    current_level = _character_total_level(definition)

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
    reference_fields = [
        {
            "name": "biography_markdown",
            "label": "Biography",
            "help_text": "Markdown shown on the Notes page for reference-level character history.",
            "value": str(values.get("biography_markdown") or (definition.profile or {}).get("biography_markdown") or ""),
        },
        {
            "name": "personality_markdown",
            "label": "Personality",
            "help_text": "Markdown shown on the Notes page for personality traits, ideals, bonds, flaws, or similar notes.",
            "value": str(values.get("personality_markdown") or (definition.profile or {}).get("personality_markdown") or ""),
        },
        {
            "name": "additional_notes_markdown",
            "label": "Additional Notes",
            "help_text": "Markdown shown on the Notes page for other persistent reference material.",
            "value": str(
                values.get("additional_notes_markdown")
                or (definition.reference_notes or {}).get("additional_notes_markdown")
                or ""
            ),
        },
        {
            "name": "allies_and_organizations_markdown",
            "label": "Allies and Organizations",
            "help_text": "Markdown shown on the Notes page for friendly factions, patrons, allies, or affiliations.",
            "value": str(
                values.get("allies_and_organizations_markdown")
                or (definition.reference_notes or {}).get("allies_and_organizations_markdown")
                or ""
            ),
        },
    ]
    stat_adjustment_fields = [
        {
            "name": f"stat_adjustment_{key}",
            "label": label,
            "help_text": help_text,
            "value": str(values.get(f"stat_adjustment_{key}") or stat_adjustments.get(key) or "").strip(),
        }
        for key, label, help_text in STAT_ADJUSTMENT_FIELDS
    ]

    feature_row_count = max(
        len(manual_features) + 1,
        _max_row_index(values, "custom_feature"),
        MIN_CUSTOM_FEATURE_ROWS,
    )
    feature_rows = []
    for index in range(1, feature_row_count + 1):
        existing = manual_features[index - 1] if index - 1 < len(manual_features) else {}
        tracker = resource_template_lookup.get(str(existing.get("tracker_ref") or "").strip(), {})
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
                "resource_max": str(
                    values.get(f"custom_feature_resource_max_{index}")
                    or tracker.get("max")
                    or ""
                ).strip(),
                "resource_reset_on": _normalize_resource_reset_on(
                    values.get(f"custom_feature_resource_reset_on_{index}")
                    or tracker.get("reset_on")
                    or "manual"
                ),
                "campaign_option": dict(_editable_campaign_option_for_page_ref(
                    str(
                        values.get(f"custom_feature_page_ref_{index}")
                        or _extract_page_ref_value(existing.get("page_ref"))
                        or ""
                    ).strip(),
                    campaign_page_lookup,
                    default_kind="feature",
                ) or {}),
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
                "campaign_option": dict(_editable_campaign_option_for_page_ref(
                    str(
                        values.get(f"manual_item_page_ref_{index}")
                        or _extract_page_ref_value(existing.get("page_ref"))
                        or ""
                    ).strip(),
                    campaign_page_lookup,
                    default_kind="item",
                ) or {}),
            }
        )

    feature_rows = _attach_spell_support_fields_to_feature_rows(
        feature_rows=feature_rows,
        equipment_rows=equipment_rows,
        current_spellcasting=definition.spellcasting,
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
    )

    return {
        "values": values,
        "proficiency_fields": proficiency_fields,
        "reference_fields": reference_fields,
        "stat_adjustment_fields": stat_adjustment_fields,
        "feature_rows": feature_rows,
        "equipment_rows": equipment_rows,
        "activation_options": [
            {"value": value, "label": label}
            for value, label in FEATURE_ACTIVATION_OPTIONS
        ],
        "resource_reset_options": [
            {"value": value, "label": label}
            for value, label in FEATURE_RESOURCE_RESET_OPTIONS
        ],
        "campaign_page_options": campaign_page_options,
        "equipment_page_options": equipment_page_options,
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
    spell_catalog: dict[str, Any] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, dict[str, int]]:
    values = dict(form_values or {})
    campaign_page_lookup = _build_campaign_page_lookup(campaign_page_records or [])
    equipment_linked_page_refs = {
        _extract_page_ref_value(item.get("page_ref"))
        for item in _manual_equipment_entries(current_definition)
        if _extract_page_ref_value(item.get("page_ref"))
    }
    equipment_campaign_page_lookup = _build_campaign_page_lookup(
        campaign_page_records or [],
        allowed_sections={CAMPAIGN_ITEMS_SECTION},
        include_page_refs=equipment_linked_page_refs,
    )
    manual_feature_lookup = {
        str(feature.get("id") or "").strip(): dict(feature)
        for feature in _manual_custom_features(current_definition)
        if str(feature.get("id") or "").strip()
    }
    existing_manual_tracker_ids = {
        _manual_feature_tracker_id(str(feature.get("id") or "").strip())
        for feature in _manual_custom_features(current_definition)
        if str(feature.get("id") or "").strip()
    }
    resource_template_lookup = {
        str(template.get("id") or "").strip(): dict(template)
        for template in list(current_definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    manual_item_lookup = {
        str(item.get("id") or "").strip(): dict(item)
        for item in _manual_equipment_entries(current_definition)
        if str(item.get("id") or "").strip()
    }
    existing_campaign_option_payloads = _campaign_option_payloads_from_entries(
        _manual_custom_features(current_definition),
        _manual_equipment_entries(current_definition),
    )
    spell_catalog = dict(spell_catalog or {})
    current_level = _character_total_level(current_definition)

    manual_proficiencies = {
        "languages": _parse_multiline_values(values.get("languages_text", "")),
        "armor": _parse_multiline_values(values.get("armor_proficiencies_text", "")),
        "weapons": _parse_multiline_values(values.get("weapon_proficiencies_text", "")),
        "tools": _parse_multiline_values(values.get("tool_proficiencies_text", "")),
    }
    reference_notes = dict(current_definition.reference_notes or {})
    reference_notes["additional_notes_markdown"] = str(values.get("additional_notes_markdown") or "")
    reference_notes["allies_and_organizations_markdown"] = str(values.get("allies_and_organizations_markdown") or "")
    profile = dict(current_definition.profile or {})
    profile["biography_markdown"] = str(values.get("biography_markdown") or "")
    profile["personality_markdown"] = str(values.get("personality_markdown") or "")
    base_stats, _ = strip_manual_stat_adjustments(dict(current_definition.stats or {}))
    existing_campaign_stat_adjustments = collect_campaign_option_stat_adjustments(existing_campaign_option_payloads)
    if existing_campaign_stat_adjustments:
        base_stats = apply_stat_adjustments(
            base_stats,
            {key: -int(value) for key, value in existing_campaign_stat_adjustments.items()},
        )
    stat_adjustments = _parse_stat_adjustments(values)

    used_feature_ids = set(manual_feature_lookup.keys())
    manual_features: list[dict[str, Any]] = []
    manual_resource_templates: list[dict[str, Any]] = []
    selected_spell_support_entries: list[dict[str, Any]] = []
    seen_feature_names: set[str] = set()
    for index in range(1, max(_max_row_index(values, "custom_feature"), MIN_CUSTOM_FEATURE_ROWS) + 1):
        raw_id = str(values.get(f"custom_feature_id_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"custom_feature_page_ref_{index}") or "",
            campaign_page_lookup,
        )
        campaign_option = _editable_campaign_option_for_page_ref(
            page_ref,
            campaign_page_lookup,
            default_kind="feature",
        )
        name = str(
            values.get(f"custom_feature_name_{index}")
            or (campaign_option or {}).get("feature_name")
            or (campaign_page_lookup.get(page_ref) or {}).get("title")
            or ""
        ).strip()
        description_markdown = str(
            values.get(f"custom_feature_description_{index}")
            or (campaign_option or {}).get("description_markdown")
            or ""
        )
        activation_type = _normalize_activation_type(
            values.get(f"custom_feature_activation_type_{index}")
            or (campaign_option or {}).get("activation_type")
            or "passive"
        )
        resource_max = _parse_optional_nonnegative_integer(
            values.get(f"custom_feature_resource_max_{index}")
            or ((campaign_option or {}).get("resource") or {}).get("max")
            or "",
            field_label=f"resource max for '{name or f'custom feature {index}'}'",
        )
        has_content = bool(name or page_ref or description_markdown.strip() or resource_max)
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
        existing.pop("campaign_option", None)
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
                "tracker_ref": None,
                "campaign_option": dict(campaign_option or {}) or None,
            }
        )
        resource_reset_on = _normalize_resource_reset_on(
            values.get(f"custom_feature_resource_reset_on_{index}")
            or ((campaign_option or {}).get("resource") or {}).get("reset_on")
            or "manual"
        )
        if page_ref:
            existing["page_ref"] = page_ref
        if dict(campaign_option or {}).get("spell_support"):
            selected_spell_support_entries.append(
                {
                    "field_prefix": f"custom_feature_spell_support_{index}",
                    "campaign_option": dict(campaign_option or {}),
                    "source_ref": str(page_ref or (campaign_option or {}).get("title") or name).strip(),
                }
            )
        if resource_max:
            tracker_id = _manual_feature_tracker_id(feature_id)
            existing["tracker_ref"] = tracker_id
            manual_resource_templates.append(
                _build_manual_feature_resource_template(
                    tracker_id=tracker_id,
                    feature_name=name,
                    max_value=resource_max,
                    reset_on=resource_reset_on,
                    existing_template=resource_template_lookup.get(tracker_id),
                    display_order=len(manual_resource_templates),
                )
            )
        manual_features.append(existing)

    used_item_ids = set(manual_item_lookup.keys())
    inventory_quantity_overrides: dict[str, int] = {}
    manual_items: list[dict[str, Any]] = []
    for index in range(1, max(_max_row_index(values, "manual_item"), MIN_CUSTOM_EQUIPMENT_ROWS) + 1):
        raw_id = str(values.get(f"manual_item_id_{index}") or "").strip()
        page_ref = _normalize_selected_campaign_page_ref(
            values.get(f"manual_item_page_ref_{index}") or "",
            equipment_campaign_page_lookup,
        )
        campaign_option = _editable_campaign_option_for_page_ref(
            page_ref,
            equipment_campaign_page_lookup,
            default_kind="item",
        )
        name = str(
            values.get(f"manual_item_name_{index}")
            or (campaign_option or {}).get("item_name")
            or (equipment_campaign_page_lookup.get(page_ref) or {}).get("title")
            or ""
        ).strip()
        quantity_text = str(
            values.get(f"manual_item_quantity_{index}")
            or (campaign_option or {}).get("quantity")
            or ""
        ).strip()
        weight = str(
            values.get(f"manual_item_weight_{index}")
            or (campaign_option or {}).get("weight")
            or ""
        ).strip()
        notes = str(
            values.get(f"manual_item_notes_{index}")
            or (campaign_option or {}).get("notes")
            or ""
        )
        has_content = bool(name or page_ref or quantity_text or weight or notes.strip())
        if not has_content:
            continue
        next_item, quantity = normalize_custom_equipment_entry(
            name=name,
            quantity=quantity_text,
            weight=weight,
            notes=notes,
            existing_item=manual_item_lookup.get(raw_id),
            raw_id=raw_id,
            used_item_ids=used_item_ids,
            page_ref=page_ref,
            campaign_option=campaign_option,
        )
        used_item_ids.add(str(next_item.get("id") or "").strip())
        manual_items.append(next_item)
        inventory_quantity_overrides[str(next_item.get("id") or "").strip()] = quantity

    selected_campaign_option_payloads = _campaign_option_payloads_from_entries(
        manual_features,
        manual_items,
    )
    proficiencies = _merge_editor_proficiencies(
        manual_proficiencies,
        selected_campaign_option_payloads,
    )
    stats = apply_manual_stat_adjustments(base_stats, stat_adjustments)
    campaign_stat_adjustments = collect_campaign_option_stat_adjustments(selected_campaign_option_payloads)
    if campaign_stat_adjustments:
        stats = apply_stat_adjustments(stats, campaign_stat_adjustments)
    spellcasting = _apply_campaign_option_spells_to_spellcasting(
        current_definition.spellcasting,
        existing_campaign_option_payloads=existing_campaign_option_payloads,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
        selected_spell_support_entries=selected_spell_support_entries,
    )

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["profile"] = profile
    payload["stats"] = stats
    payload["proficiencies"] = proficiencies
    payload["spellcasting"] = spellcasting
    payload["reference_notes"] = reference_notes
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
    payload["resource_templates"] = [
        dict(template)
        for template in list(current_definition.resource_templates or [])
        if str(template.get("id") or "").strip() not in existing_manual_tracker_ids
    ] + manual_resource_templates

    definition = CharacterDefinition.from_dict(payload)
    source_type = str((current_definition.source or {}).get("source_type") or "").strip()
    if source_type and source_type != "native_character_builder":
        definition = converge_imported_definition(
            definition,
            existing_definition=current_definition,
        )
    import_metadata = build_managed_character_import_metadata(
        campaign_slug,
        current_definition.character_slug,
        current_import_metadata,
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


def _campaign_option_payloads_from_entries(
    features: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in list(features or []) + list(items or []):
        option = dict(entry.get("campaign_option") or {})
        if option:
            payloads.append(option)
    return payloads


def _display_proficiency_lists_for_editor(definition: CharacterDefinition) -> dict[str, list[str]]:
    proficiencies = {
        key: list((definition.proficiencies or {}).get(key) or [])
        for key in ("languages", "armor", "weapons", "tools")
    }
    campaign_grants = collect_campaign_option_proficiency_grants(
        _campaign_option_payloads_from_entries(
            _manual_custom_features(definition),
            _manual_equipment_entries(definition),
        )
    )
    return {
        key: _subtract_casefold_values(proficiencies[key], campaign_grants.get(key) or [])
        for key in proficiencies
    }


def _editable_campaign_option_for_page_ref(
    page_ref: str,
    campaign_page_lookup: dict[str, dict[str, Any]],
    *,
    default_kind: str,
) -> dict[str, Any] | None:
    option = dict((campaign_page_lookup.get(page_ref) or {}).get("campaign_option") or {})
    if not option:
        return None
    kind = str(option.get("kind") or default_kind or "").strip().lower()
    allowed_kinds = (
        FEATURE_LIKE_CAMPAIGN_OPTION_KINDS
        if default_kind == "feature"
        else {default_kind}
    )
    if kind and kind not in allowed_kinds:
        return None
    return option


def _merge_editor_proficiencies(
    manual_proficiencies: dict[str, list[str]],
    option_payloads: list[dict[str, Any]],
) -> dict[str, list[str]]:
    campaign_grants = collect_campaign_option_proficiency_grants(option_payloads)
    return {
        key: _dedupe_casefold_values(list(manual_proficiencies.get(key) or []) + list(campaign_grants.get(key) or []))
        for key in ("languages", "armor", "weapons", "tools")
    }


def _attach_spell_support_fields_to_feature_rows(
    *,
    feature_rows: list[dict[str, Any]],
    equipment_rows: list[dict[str, Any]],
    current_spellcasting: dict[str, Any] | None,
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(feature_rows or [])]
    if not rows or not spell_catalog:
        for row in rows:
            row["spell_fields"] = []
        return rows

    tracked_spell_payloads = [
        _normalize_spell_payload_for_campaign_option_tracking(payload)
        for payload in _campaign_option_tracked_spell_payloads(current_spellcasting)
    ]
    provisional_values = dict(values)
    for row in rows:
        choice_fields = _build_editor_spell_support_choice_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"] = choice_fields
        for field in choice_fields:
            field_name = str(field.get("name") or "").strip()
            selected_value = str(field.get("selected") or "").strip()
            if field_name and selected_value and not str(provisional_values.get(field_name) or "").strip():
                provisional_values[field_name] = selected_value

    provisional_spell_payloads = _build_provisional_editor_spell_payloads(
        current_spellcasting=current_spellcasting,
        feature_rows=rows,
        equipment_rows=equipment_rows,
        spell_catalog=spell_catalog,
        values=provisional_values,
        current_level=current_level,
    )
    for row in rows:
        replacement_fields = _build_editor_spell_support_replacement_fields_for_row(
            row=row,
            tracked_spell_payloads=tracked_spell_payloads,
            provisional_spell_payloads=provisional_spell_payloads,
            spell_catalog=spell_catalog,
            values=provisional_values,
            current_level=current_level,
        )
        row["spell_fields"].extend(replacement_fields)
    return rows


def _build_editor_spell_support_choice_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    if not option.get("spell_support"):
        return []
    field_prefix = _editor_spell_support_field_prefix(int(row.get("index") or 0))
    fields = _build_spell_support_choice_fields(
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        group_key_prefix=field_prefix,
        feature_entries=[{"campaign_option": option}],
    )
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        field["selected"] = _infer_editor_spell_support_choice_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _build_editor_spell_support_replacement_fields_for_row(
    *,
    row: dict[str, Any],
    tracked_spell_payloads: list[dict[str, Any]],
    provisional_spell_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    option = dict(row.get("campaign_option") or {})
    if not option.get("spell_support"):
        return []
    field_prefix = _editor_spell_support_field_prefix(int(row.get("index") or 0))
    fields = _build_spell_support_replacement_fields(
        existing_spells=provisional_spell_payloads,
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        feature_entries=[{"campaign_option": option}],
    )
    source_ref = str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip()
    for field in fields:
        field_name = str(field.get("name") or "").strip()
        if field_name and str(values.get(field_name) or "").strip():
            field["selected"] = str(values.get(field_name) or "").strip()
            continue
        field["selected"] = _infer_editor_spell_support_replacement_value(
            tracked_spell_payloads=tracked_spell_payloads,
            source_ref=source_ref,
            field_name=field_name,
            field_prefix=field_prefix,
        )
    return fields


def _build_provisional_editor_spell_payloads(
    *,
    current_spellcasting: dict[str, Any] | None,
    feature_rows: list[dict[str, Any]],
    equipment_rows: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in _campaign_option_tracked_spell_payloads(current_spellcasting):
        payload = _normalize_spell_payload_for_campaign_option_tracking(spell)
        _reset_spell_payload_to_base(payload)
        payload_key = _campaign_option_spell_map_key(payload, spell_catalog)
        if payload_key:
            spells_by_key[payload_key] = payload

    selected_option_payloads = _campaign_option_payloads_from_entries(feature_rows, equipment_rows)
    _apply_editor_legacy_campaign_option_grants(
        spells_by_key,
        selected_campaign_option_payloads=selected_option_payloads,
        spell_catalog=spell_catalog,
    )
    for entry in _editor_spell_support_entries_from_feature_rows(feature_rows):
        _apply_editor_spell_support_grants_and_choices(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )
    return list(spells_by_key.values())


def _editor_spell_support_entries_from_feature_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in list(feature_rows or []):
        option = dict(row.get("campaign_option") or {})
        if not option.get("spell_support"):
            continue
        entries.append(
            {
                "field_prefix": _editor_spell_support_field_prefix(int(row.get("index") or 0)),
                "campaign_option": option,
                "source_ref": str(option.get("page_ref") or row.get("page_ref") or option.get("title") or "").strip(),
            }
        )
    return entries


def _editor_spell_support_field_prefix(row_index: int) -> str:
    return f"custom_feature_spell_support_{row_index}"


def _parse_editor_spell_support_choice_field_identity(
    field_name: str,
    field_prefix: str,
) -> tuple[str, int, int] | None:
    prefix = f"{field_prefix}_"
    if not field_name.startswith(prefix):
        return None
    parts = field_name[len(prefix):].split("_")
    if len(parts) != 3:
        return None
    category, spec_index, choice_index = parts
    if not spec_index.isdigit() or not choice_index.isdigit():
        return None
    return category, int(spec_index), int(choice_index)


def _parse_editor_spell_support_replacement_field_identity(
    field_name: str,
    field_prefix: str,
) -> tuple[str, int, str, int] | None:
    prefix = f"{field_prefix}_replace_"
    if not field_name.startswith(prefix):
        return None
    parts = field_name[len(prefix):].split("_")
    if len(parts) != 4:
        return None
    category, spec_index, part, choice_index = parts
    if not spec_index.isdigit() or not choice_index.isdigit():
        return None
    return category, int(spec_index), part, int(choice_index)


def _infer_editor_spell_support_choice_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_spell_support_choice_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, choice_index = identity
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key="campaign_option_sources",
            source_ref=source_ref,
            mode="spell_support_choice",
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _infer_editor_spell_support_replacement_value(
    *,
    tracked_spell_payloads: list[dict[str, Any]],
    source_ref: str,
    field_name: str,
    field_prefix: str,
) -> str:
    identity = _parse_editor_spell_support_replacement_field_identity(field_name, field_prefix)
    if identity is None:
        return ""
    category, spec_index, part, choice_index = identity
    annotation_key = "campaign_option_replaced_by" if part == "from" else "campaign_option_sources"
    mode = "spell_support_replacement"
    for payload in tracked_spell_payloads:
        if _payload_has_campaign_option_annotation(
            payload,
            annotation_key=annotation_key,
            source_ref=source_ref,
            mode=mode,
            category=category,
            spec_index=spec_index,
            choice_index=choice_index,
        ):
            return _spell_payload_key(payload)
    return ""


def _payload_has_campaign_option_annotation(
    payload: dict[str, Any],
    *,
    annotation_key: str,
    source_ref: str,
    mode: str,
    category: str,
    spec_index: int,
    choice_index: int,
) -> bool:
    for annotation in list(payload.get(annotation_key) or []):
        if not isinstance(annotation, dict):
            continue
        if str(annotation.get("source_ref") or "").strip() != source_ref:
            continue
        if str(annotation.get("mode") or "").strip() != mode:
            continue
        if str(annotation.get("category") or "").strip() != category:
            continue
        if int(annotation.get("spec_index") or 0) != spec_index:
            continue
        if int(annotation.get("choice_index") or 0) != choice_index:
            continue
        return True
    return False


def _campaign_option_tracked_spell_payloads(current_spellcasting: dict[str, Any] | None) -> list[dict[str, Any]]:
    spellcasting = dict(current_spellcasting or {})
    return [
        dict(payload)
        for payload in list(spellcasting.get("spells") or []) + list(spellcasting.get("campaign_option_replacement_bases") or [])
        if isinstance(payload, dict)
    ]


def _campaign_option_spell_map_key(
    spell_payload: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> str:
    payload_key = _spell_payload_key(spell_payload)
    if not payload_key:
        return ""
    return _spell_lookup_key(payload_key, spell_catalog)


def _character_total_level(definition: CharacterDefinition) -> int:
    class_rows = list((definition.profile or {}).get("classes") or [])
    total_level = sum(int(dict(row).get("level") or 0) for row in class_rows if isinstance(row, dict))
    if total_level > 0:
        return total_level
    class_level_text = str((definition.profile or {}).get("class_level_text") or "").strip()
    match = re.search(r"(\d+)", class_level_text)
    return int(match.group(1)) if match else 1


def _apply_campaign_option_spells_to_spellcasting(
    current_spellcasting: dict[str, Any] | None,
    *,
    existing_campaign_option_payloads: list[dict[str, Any]],
    selected_campaign_option_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
    selected_spell_support_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spellcasting = dict(current_spellcasting or {})
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in _campaign_option_tracked_spell_payloads(spellcasting):
        payload = _normalize_spell_payload_for_campaign_option_tracking(spell)
        _reset_spell_payload_to_base(payload)
        payload_key = _campaign_option_spell_map_key(payload, spell_catalog)
        if payload_key:
            spells_by_key[payload_key] = payload

    _apply_editor_legacy_campaign_option_grants(
        spells_by_key,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
        spell_catalog=spell_catalog,
    )

    choice_fields: list[dict[str, Any]] = []
    replacement_fields: list[dict[str, Any]] = []
    for entry in list(selected_spell_support_entries or []):
        choice_fields.extend(
            _apply_editor_spell_support_grants_and_choices(
                spells_by_key,
                entry=entry,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    provisional_spell_payloads = list(spells_by_key.values())
    for entry in list(selected_spell_support_entries or []):
        replacement_fields.extend(
            _build_editor_spell_support_replacement_fields_for_entry(
                entry=entry,
                existing_spells=provisional_spell_payloads,
                spell_catalog=spell_catalog,
                values=values,
                current_level=current_level,
            )
        )
    if choice_fields or replacement_fields:
        _resolve_builder_choices(
            [{"title": "Spell Choices", "fields": choice_fields + replacement_fields}],
            values,
            strict=True,
        )
    for entry in list(selected_spell_support_entries or []):
        _apply_editor_spell_support_replacements(
            spells_by_key,
            entry=entry,
            spell_catalog=spell_catalog,
            values=values,
            current_level=current_level,
        )

    visible_spells: list[dict[str, Any]] = []
    hidden_spells: list[dict[str, Any]] = []
    for payload in spells_by_key.values():
        if list(payload.get("campaign_option_replaced_by") or []):
            hidden_spells.append(payload)
            continue
        if bool(payload.get("has_base_spell")) or list(payload.get("campaign_option_sources") or []):
            visible_spells.append(payload)
    spellcasting["spells"] = visible_spells
    if hidden_spells:
        spellcasting["campaign_option_replacement_bases"] = hidden_spells
    else:
        spellcasting.pop("campaign_option_replacement_bases", None)
    return spellcasting


def _apply_editor_legacy_campaign_option_grants(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_campaign_option_payloads: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> None:
    for spell_grant in _iter_campaign_option_spell_grants(selected_campaign_option_payloads):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(spell_grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": str(spell_grant.get("source_ref") or "").strip(),
                "mode": "legacy_grant",
                "mark": str(spell_grant.get("mark") or "").strip(),
                "always_prepared": bool(spell_grant.get("always_prepared")),
                "ritual": bool(spell_grant.get("ritual")),
            },
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
        )


def _apply_editor_spell_support_grants_and_choices(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    feature_entries = [{"campaign_option": dict(entry.get("campaign_option") or {})}]
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix = str(entry.get("field_prefix") or "").strip()
    for grant in _automatic_spell_support_grants(
        selected_class=None,
        selected_subclass=None,
        target_level=current_level,
        feature_entries=feature_entries,
    ):
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=str(grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_grant",
                "mark": str(grant.get("mark") or "").strip(),
                "always_prepared": bool(grant.get("always_prepared")),
                "ritual": bool(grant.get("ritual")),
            },
            mark=str(grant.get("mark") or "").strip(),
            is_always_prepared=bool(grant.get("always_prepared")),
            is_ritual=bool(grant.get("ritual")),
            bonus_known=bool(grant.get("bonus_known")),
        )

    choice_fields = _build_spell_support_choice_fields(
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=field_prefix,
        group_key_prefix=field_prefix,
        feature_entries=feature_entries,
    )
    for field in choice_fields:
        selected_value = str(values.get(str(field.get("name") or "")) or "").strip()
        if not selected_value:
            continue
        identity = _parse_editor_spell_support_choice_field_identity(str(field.get("name") or ""), field_prefix)
        category, spec_index, choice_index = identity or ("", 0, 0)
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_choice",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(field.get("spell_mark") or "").strip(),
                "always_prepared": bool(field.get("spell_is_always_prepared")),
                "ritual": bool(field.get("spell_is_ritual")),
            },
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
            bonus_known=str(category or "").strip() == "known",
        )
    return choice_fields


def _build_editor_spell_support_replacement_fields_for_entry(
    *,
    entry: dict[str, Any],
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> list[dict[str, Any]]:
    return _build_spell_support_replacement_fields(
        existing_spells=existing_spells,
        selected_class=None,
        selected_subclass=None,
        spell_catalog=spell_catalog,
        target_level=current_level,
        values=values,
        field_prefix=str(entry.get("field_prefix") or "").strip(),
        feature_entries=[{"campaign_option": dict(entry.get("campaign_option") or {})}],
    )


def _apply_editor_spell_support_replacements(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    entry: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    current_level: int,
) -> None:
    replacement_fields = _build_editor_spell_support_replacement_fields_for_entry(
        entry=entry,
        existing_spells=list(spells_by_key.values()),
        spell_catalog=spell_catalog,
        values=values,
        current_level=current_level,
    )
    source_ref = str(entry.get("source_ref") or "").strip()
    field_prefix = str(entry.get("field_prefix") or "").strip()
    replacement_specs: dict[tuple[str, int, int], dict[str, Any]] = {}
    for field in replacement_fields:
        identity = _parse_editor_spell_support_replacement_field_identity(str(field.get("name") or ""), field_prefix)
        if identity is None:
            continue
        category, spec_index, _, choice_index = identity
        replacement_specs[(category, spec_index, choice_index)] = {
            "mark": str(field.get("spell_mark") or "").strip(),
            "always_prepared": bool(field.get("spell_is_always_prepared")),
            "ritual": bool(field.get("spell_is_ritual")),
        }
    for field in replacement_fields:
        field_name = str(field.get("name") or "").strip()
        identity = _parse_editor_spell_support_replacement_field_identity(field_name, field_prefix)
        if identity is None:
            continue
        category, spec_index, part, choice_index = identity
        if part != "from":
            continue
        replacement_from = str(values.get(field_name) or "").strip()
        to_field_name = str(field.get("paired_field_name") or "").strip()
        replacement_to = str(values.get(to_field_name) or "").strip()
        if not replacement_from or not replacement_to:
            continue
        payload_key = _spell_lookup_key(replacement_from, spell_catalog)
        payload = spells_by_key.get(payload_key)
        if payload is not None:
            _add_campaign_option_source_annotation(
                payload,
                annotation_key="campaign_option_replaced_by",
                annotation={
                    "source_ref": source_ref,
                    "mode": "spell_support_replacement",
                    "category": category,
                    "spec_index": spec_index,
                    "choice_index": choice_index,
                },
            )
        replacement_metadata = dict(replacement_specs.get((category, spec_index, choice_index)) or {})
        _add_editor_campaign_option_spell(
            spells_by_key,
            selected_value=replacement_to,
            spell_catalog=spell_catalog,
            annotation={
                "source_ref": source_ref,
                "mode": "spell_support_replacement",
                "category": category,
                "spec_index": spec_index,
                "choice_index": choice_index,
                "mark": str(replacement_metadata.get("mark") or "").strip(),
                "always_prepared": bool(replacement_metadata.get("always_prepared")),
                "ritual": bool(replacement_metadata.get("ritual")),
            },
            mark=str(replacement_metadata.get("mark") or "").strip(),
            is_always_prepared=bool(replacement_metadata.get("always_prepared")),
            is_ritual=bool(replacement_metadata.get("ritual")),
            bonus_known=category == "known",
        )


def _add_editor_campaign_option_spell(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    annotation: dict[str, Any],
    mark: str = "",
    is_always_prepared: bool = False,
    is_ritual: bool = False,
    bonus_known: bool = False,
) -> None:
    clean_value = str(selected_value or "").strip()
    if not clean_value:
        return
    spell_entry = _resolve_spell_entry(clean_value, spell_catalog)
    payload_key = str((spell_entry.slug if spell_entry is not None else clean_value) or "").strip()
    if not payload_key:
        return
    existed_before = payload_key in spells_by_key
    if bonus_known:
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=clean_value,
            spell_catalog=spell_catalog,
        )
    else:
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=clean_value,
            spell_catalog=spell_catalog,
            mark=mark,
            is_always_prepared=is_always_prepared,
            is_ritual=is_ritual,
        )
    payload = spells_by_key.get(payload_key)
    if payload is None:
        return
    if not existed_before:
        payload["base_mark"] = ""
        payload["base_is_always_prepared"] = False
        payload["base_is_bonus_known"] = False
        payload["base_is_ritual"] = bool(dict((spell_entry.metadata if spell_entry is not None else {}) or {}).get("ritual"))
        payload["has_base_spell"] = False
    _add_campaign_option_source_annotation(
        payload,
        annotation_key="campaign_option_sources",
        annotation=annotation,
    )


def _normalize_spell_payload_for_campaign_option_tracking(spell_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spell_payload or {})
    payload["base_mark"] = str(
        payload.get("base_mark")
        if "base_mark" in payload
        else payload.get("mark", "")
    ).strip()
    payload["base_is_always_prepared"] = bool(
        payload.get("base_is_always_prepared")
        if "base_is_always_prepared" in payload
        else payload.get("is_always_prepared")
    )
    payload["base_is_bonus_known"] = bool(
        payload.get("base_is_bonus_known")
        if "base_is_bonus_known" in payload
        else payload.get("is_bonus_known")
    )
    payload["base_is_ritual"] = bool(
        payload.get("base_is_ritual")
        if "base_is_ritual" in payload
        else payload.get("is_ritual")
    )
    payload["has_base_spell"] = bool(
        payload.get("has_base_spell")
        if "has_base_spell" in payload
        else True
    )
    payload["campaign_option_sources"] = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get("campaign_option_sources"))
    ]
    payload["campaign_option_replaced_by"] = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get("campaign_option_replaced_by"))
    ]
    return payload


def _reset_spell_payload_to_base(payload: dict[str, Any]) -> None:
    payload["mark"] = str(payload.get("base_mark") or "").strip()
    payload["is_always_prepared"] = bool(payload.get("base_is_always_prepared"))
    payload["is_bonus_known"] = bool(payload.get("base_is_bonus_known"))
    payload["is_ritual"] = bool(payload.get("base_is_ritual"))
    payload["campaign_option_sources"] = []
    payload["campaign_option_replaced_by"] = []


def _normalize_campaign_option_source_annotations(value: Any) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for raw_annotation in list(value or []):
        if not isinstance(raw_annotation, dict):
            continue
        annotations.append(
            {
                "source_ref": str(raw_annotation.get("source_ref") or "").strip(),
                "mode": str(raw_annotation.get("mode") or "").strip(),
                "category": str(raw_annotation.get("category") or "").strip(),
                "spec_index": int(raw_annotation.get("spec_index") or 0),
                "choice_index": int(raw_annotation.get("choice_index") or 0),
                "mark": str(raw_annotation.get("mark") or "").strip(),
                "always_prepared": bool(raw_annotation.get("always_prepared")),
                "ritual": bool(raw_annotation.get("ritual")),
            }
        )
    return [annotation for annotation in annotations if annotation.get("source_ref")]


def _campaign_option_source_marker(annotation: dict[str, Any]) -> tuple[str, str, str, int, int, str, bool, bool]:
    return (
        str(annotation.get("source_ref") or "").strip(),
        str(annotation.get("mode") or "").strip(),
        str(annotation.get("category") or "").strip(),
        int(annotation.get("spec_index") or 0),
        int(annotation.get("choice_index") or 0),
        str(annotation.get("mark") or "").strip(),
        bool(annotation.get("always_prepared")),
        bool(annotation.get("ritual")),
    )


def _add_campaign_option_source_annotation(
    payload: dict[str, Any],
    *,
    annotation_key: str,
    annotation: dict[str, Any],
) -> None:
    normalized_entries = _normalize_campaign_option_source_annotations([annotation]) if annotation else []
    normalized_annotation = dict(normalized_entries[0]) if normalized_entries else {}
    if not normalized_annotation:
        return
    existing_annotations = [
        dict(source)
        for source in _normalize_campaign_option_source_annotations(payload.get(annotation_key))
    ]
    marker = _campaign_option_source_marker(normalized_annotation)
    seen = {_campaign_option_source_marker(source) for source in existing_annotations}
    if marker not in seen:
        existing_annotations.append(normalized_annotation)
    payload[annotation_key] = existing_annotations


def _iter_campaign_option_spell_grants(option_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for option in list(option_payloads or []):
        source_ref = str(option.get("page_ref") or option.get("title") or option.get("display_name") or "").strip()
        if not source_ref:
            continue
        for grant in list(option.get("spells") or []):
            payload = dict(grant or {})
            value = str(payload.get("value") or "").strip()
            if not value:
                continue
            grants.append(
                {
                    "source_ref": source_ref,
                    "value": value,
                    "mark": str(payload.get("mark") or "").strip(),
                    "always_prepared": bool(payload.get("always_prepared")),
                    "ritual": bool(payload.get("ritual")),
                }
            )
    return grants


def _dedupe_casefold_values(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        clean_value = str(value or "").strip()
        normalized_value = normalize_lookup(clean_value)
        if not clean_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        deduped.append(clean_value)
    return deduped


def _subtract_casefold_values(values: list[str], removals: list[str]) -> list[str]:
    removal_keys = {
        normalize_lookup(value)
        for value in list(removals or [])
        if str(value or "").strip()
    }
    return [
        str(value).strip()
        for value in list(values or [])
        if str(value or "").strip() and normalize_lookup(value) not in removal_keys
    ]


def _manual_feature_tracker_id(feature_id: str) -> str:
    return f"{CUSTOM_FEATURE_TRACKER_PREFIX}:{feature_id}"


def _build_manual_feature_resource_template(
    *,
    tracker_id: str,
    feature_name: str,
    max_value: int,
    reset_on: str,
    existing_template: dict[str, Any] | None,
    display_order: int,
) -> dict[str, Any]:
    current_template = dict(existing_template or {})
    clean_reset_on = _normalize_resource_reset_on(reset_on)
    return {
        "id": tracker_id,
        "label": feature_name,
        "category": "custom_feature",
        "initial_current": min(
            int(current_template.get("initial_current") or max_value),
            int(max_value),
        ),
        "max": int(max_value),
        "reset_on": clean_reset_on,
        "reset_to": "max" if clean_reset_on in {"short_rest", "long_rest"} else "unchanged",
        "rest_behavior": "confirm_before_reset" if clean_reset_on in {"short_rest", "long_rest"} else "manual_only",
        "notes": str(current_template.get("notes") or "").strip(),
        "display_order": int(display_order),
    }


def _build_campaign_page_options(
    campaign_page_records: list[Any],
    *,
    allowed_sections: set[str] | None = None,
    include_page_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_allowed_sections = {
        str(value or "").strip()
        for value in set(allowed_sections or set())
        if str(value or "").strip()
    }
    normalized_include_page_refs = {
        (str(value.get("page_ref") or value.get("slug") or "").strip() if isinstance(value, dict) else str(value or "").strip())
        for value in set(include_page_refs or set())
        if (str(value.get("page_ref") or value.get("slug") or "").strip() if isinstance(value, dict) else str(value or "").strip())
    }
    options: list[dict[str, Any]] = []
    for record in list(campaign_page_records or []):
        page_ref = _extract_page_ref_value(getattr(record, "page_ref", ""))
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        section = str(getattr(page, "section", "") or "").strip()
        subsection = str(getattr(page, "subsection", "") or "").strip()
        if normalized_allowed_sections and section not in normalized_allowed_sections and page_ref not in normalized_include_page_refs:
            continue
        campaign_option = build_campaign_page_character_option(
            record,
            default_kind="item" if section == "Items" else "feature",
        )
        option_title = str((campaign_option or {}).get("display_name") or title).strip() or title
        label_parts = [option_title]
        if section:
            if subsection:
                label_parts.append(f"{section} / {subsection}")
            else:
                label_parts.append(section)
        options.append(
            {
                "value": page_ref,
                "label": " | ".join(label_parts),
                "title": option_title,
                "campaign_option": dict(campaign_option or {}) or None,
            }
        )
    return options


def _build_campaign_page_lookup(
    campaign_page_records: list[Any],
    *,
    allowed_sections: set[str] | None = None,
    include_page_refs: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for option in _build_campaign_page_options(
        campaign_page_records,
        allowed_sections=allowed_sections,
        include_page_refs=include_page_refs,
    ):
        page_ref = str(option.get("value") or "").strip()
        if not page_ref:
            continue
        lookup[page_ref] = {
            "page_ref": page_ref,
            "label": str(option.get("label") or page_ref),
            "title": str(option.get("title") or page_ref),
            "campaign_option": dict(option.get("campaign_option") or {}) or None,
        }
    return lookup


def _extract_page_ref_value(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("page_ref") or payload.get("slug") or "").strip()
    return str(payload or "").strip()


def _normalize_selected_campaign_page_ref(
    raw_value: Any,
    campaign_page_lookup: dict[str, dict[str, Any]],
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


def _parse_optional_nonnegative_integer(raw_value: str, *, field_label: str) -> int | None:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return None
    try:
        value = int(clean_value)
    except ValueError as exc:
        raise CharacterEditValidationError(f"The {field_label} must be a whole number.") from exc
    if value < 0:
        raise CharacterEditValidationError(f"The {field_label} cannot be negative.")
    return value


def _parse_optional_integer(raw_value: str, *, field_label: str) -> int | None:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return None
    try:
        return int(clean_value)
    except ValueError as exc:
        raise CharacterEditValidationError(f"The {field_label} must be a whole number.") from exc


def _parse_stat_adjustments(values: dict[str, str]) -> dict[str, int]:
    adjustments: dict[str, int] = {}
    for key, label, _ in STAT_ADJUSTMENT_FIELDS:
        value = _parse_optional_integer(values.get(f"stat_adjustment_{key}") or "", field_label=label.lower())
        if value:
            adjustments[key] = value
    return adjustments


def _normalize_activation_type(raw_value: Any) -> str:
    value = str(raw_value or "passive").strip().lower()
    return value if value in VALID_FEATURE_ACTIVATION_TYPES else "passive"


def _normalize_resource_reset_on(raw_value: Any) -> str:
    value = str(raw_value or "manual").strip().lower()
    return value if value in VALID_FEATURE_RESOURCE_RESET_TYPES else "manual"


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
