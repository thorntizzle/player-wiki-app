from __future__ import annotations

from typing import Any

from .character_builder_constants import (
    ABILITY_KEYS,
    ADVANCEMENT_REGION_ID,
    ATTACK_MODE_EFFECT_PREFIX,
    BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
    BUILDER_MODE_PREVIEW_DEBOUNCE_MS,
    BUILDER_TEXT_PREVIEW_DEBOUNCE_MS,
    CHOICE_SECTIONS_REGION_ID,
    LEVEL_ONE_LIVE_REGION_IDS,
    LEVEL_ONE_PREVIEW_REGION_IDS,
    LEVEL_UP_LIVE_REGION_IDS,
    LEVEL_UP_PREVIEW_REGION_IDS,
    PREVIEW_ATTACKS_REGION_ID,
    PREVIEW_EQUIPMENT_REGION_ID,
    PREVIEW_FEATURES_REGION_ID,
    PREVIEW_RESOURCES_REGION_ID,
    PREVIEW_SCOPE_REGION_ID,
    PREVIEW_SPELLS_REGION_ID,
    PREVIEW_SPELL_SLOTS_REGION_ID,
    PREVIEW_SUMMARY_REGION_ID,
)
from .character_campaign_options import collect_mechanic_effect_legacy_keys
from .repository import normalize_lookup


__all__ = [
    "_field_live_preview_region_ids",
    "_live_preview_field_metadata",
    "_top_level_field_live_preview_metadata",
    "_level_one_field_live_preview_metadata",
    "_level_up_field_live_preview_metadata",
    "_annotate_builder_choice_sections",
]


def _field_live_preview_region_ids(
    field: dict[str, Any],
    *,
    preview_region_ids: tuple[str, ...],
    live_region_ids: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    field_name = str(field.get("name") or "").strip()
    kind = str(field.get("kind") or "").strip()
    available_live_region_ids = tuple(live_region_ids or preview_region_ids)
    non_scope_preview_region_ids = tuple(
        region_id
        for region_id in preview_region_ids
        if region_id != PREVIEW_SCOPE_REGION_ID
    ) or tuple(preview_region_ids)

    def _matching_region_ids(*region_ids: str) -> tuple[str, ...]:
        ordered_region_ids: list[str] = []
        seen_region_ids: set[str] = set()
        allowed_region_ids = {
            str(region_id or "").strip()
            for region_id in available_live_region_ids
            if str(region_id or "").strip()
        }
        for region_id in region_ids:
            clean_region_id = str(region_id or "").strip()
            if not clean_region_id or clean_region_id not in allowed_region_ids or clean_region_id in seen_region_ids:
                continue
            seen_region_ids.add(clean_region_id)
            ordered_region_ids.append(clean_region_id)
        return tuple(ordered_region_ids)

    if field_name in {"name", "character_slug", "alignment", "experience_model"}:
        return ()
    if field_name == "hp_gain":
        return _matching_region_ids(PREVIEW_SUMMARY_REGION_ID)
    if field_name in ABILITY_KEYS or kind in {"ability", "feat_ability"}:
        return _matching_region_ids(
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if kind in {"language", "feat_language", "skill", "feat_skill", "tool", "feat_tool", "save", "feat_save"}:
        return _matching_region_ids(PREVIEW_SUMMARY_REGION_ID)
    if kind in {"weapon", "feat_weapon", "mixed_proficiency", "feat_mixed_proficiency"}:
        return _matching_region_ids(
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if kind == "equipment":
        return _matching_region_ids(
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_EQUIPMENT_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if kind in {"spell", "spell_support_replace_from", "spell_support_replace_to"} or kind.startswith(
        "spell_support_"
    ) or kind.startswith(
        "feat_spell_"
    ) or field_name.startswith(
        (
            "spell_",
            "wizard_",
            "bonus_spell_known_",
            "levelup_spell_",
            "levelup_wizard_",
            "levelup_prepared_",
            "levelup_bonus_spell_known_",
            "levelup_spell_support_",
        )
    ):
        return _matching_region_ids(PREVIEW_SPELLS_REGION_ID)
    if field_name == "class_slug":
        return _matching_region_ids(
            CHOICE_SECTIONS_REGION_ID,
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_FEATURES_REGION_ID,
            PREVIEW_RESOURCES_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_EQUIPMENT_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if field_name in {"subclass_slug", "new_subclass_slug"}:
        return _matching_region_ids(
            CHOICE_SECTIONS_REGION_ID,
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_FEATURES_REGION_ID,
            PREVIEW_RESOURCES_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
            PREVIEW_SPELL_SLOTS_REGION_ID,
        )
    if field_name == "species_slug":
        return _matching_region_ids(
            CHOICE_SECTIONS_REGION_ID,
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_FEATURES_REGION_ID,
            PREVIEW_RESOURCES_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if field_name == "background_slug":
        return _matching_region_ids(
            CHOICE_SECTIONS_REGION_ID,
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_EQUIPMENT_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if field_name in {"advancement_mode", "target_class_row_id", "new_class_slug"}:
        return _matching_region_ids(
            ADVANCEMENT_REGION_ID,
            CHOICE_SECTIONS_REGION_ID,
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_FEATURES_REGION_ID,
            PREVIEW_RESOURCES_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
            PREVIEW_SPELL_SLOTS_REGION_ID,
        )
    if kind == "campaign_page_item":
        option_payloads = [
            dict(option.get("campaign_option") or {})
            for option in list(field.get("options") or [])
            if isinstance(option.get("campaign_option"), dict)
        ]
        region_ids: list[str] = []
        if any(payload.get("spell_support") or payload.get("additional_spells") or payload.get("spell_manager") for payload in option_payloads):
            region_ids.append(CHOICE_SECTIONS_REGION_ID)
        region_ids.extend(
            [
                PREVIEW_SUMMARY_REGION_ID,
                PREVIEW_EQUIPMENT_REGION_ID,
                PREVIEW_ATTACKS_REGION_ID,
            ]
        )
        if any(
            payload.get("spells") or payload.get("spell_support") or payload.get("additional_spells") or payload.get("spell_manager")
            for payload in option_payloads
        ):
            region_ids.append(PREVIEW_SPELLS_REGION_ID)
        if any(dict(payload.get("stat_adjustments") or {}) for payload in option_payloads):
            region_ids.extend((PREVIEW_ATTACKS_REGION_ID, PREVIEW_SPELLS_REGION_ID))
        return _matching_region_ids(*region_ids)
    if kind == "campaign_page_feature":
        option_payloads = [
            dict(option.get("campaign_option") or {})
            for option in list(field.get("options") or [])
            if isinstance(option.get("campaign_option"), dict)
        ]
        adds_choice_sections = any(
            payload.get("spell_support") or payload.get("additional_spells") or payload.get("spell_manager")
            for payload in option_payloads
        )
        adds_summary = any(
            dict(payload.get("stat_adjustments") or {})
            or payload.get("mechanic_effects")
            or payload.get("modeled_effects")
            or payload.get("size")
            or payload.get("speed") is not None
            or payload.get("languages")
            or payload.get("skill_proficiencies")
            or payload.get("tool_proficiencies")
            or any(
                list(dict(payload.get("proficiencies") or {}).get(key) or [])
                for key in ("armor", "weapons", "tools", "languages", "skills")
            )
            for payload in option_payloads
        )
        adds_spells = any(
            payload.get("spells") or payload.get("spell_support") or payload.get("additional_spells") or payload.get("spell_manager")
            for payload in option_payloads
        )
        adds_resources = any(payload.get("resource") for payload in option_payloads)
        adds_attacks = any(
            dict(payload.get("stat_adjustments") or {})
            or list(dict(payload.get("proficiencies") or {}).get("weapons") or [])
            or any(
                normalize_lookup(effect).startswith(normalize_lookup(ATTACK_MODE_EFFECT_PREFIX))
                for effect in [
                    *list(payload.get("modeled_effects") or []),
                    *collect_mechanic_effect_legacy_keys(payload.get("mechanic_effects")),
                ]
            )
            for payload in option_payloads
        )
        region_ids: list[str] = []
        if adds_choice_sections:
            region_ids.append(CHOICE_SECTIONS_REGION_ID)
        if adds_summary:
            region_ids.append(PREVIEW_SUMMARY_REGION_ID)
        region_ids.append(PREVIEW_FEATURES_REGION_ID)
        if adds_resources:
            region_ids.append(PREVIEW_RESOURCES_REGION_ID)
        if adds_spells:
            region_ids.append(PREVIEW_SPELLS_REGION_ID)
        if adds_attacks:
            region_ids.append(PREVIEW_ATTACKS_REGION_ID)
        return _matching_region_ids(*region_ids)
    if kind in {"subclass", "feat", "optionalfeature", "asi_mode", "feat_spell_source", "campaign_spell_source"} or field_name.startswith(
        (
            "class_option_",
            "levelup_class_option_",
            "levelup_subclass_option_",
            "species_feat_",
            "levelup_feat_",
            "campaign_spell_manager_",
            "levelup_campaign_spell_manager_",
        )
    ):
        return _matching_region_ids(CHOICE_SECTIONS_REGION_ID, *non_scope_preview_region_ids)
    return _matching_region_ids(*non_scope_preview_region_ids)


def _live_preview_field_metadata(
    *,
    trigger: str,
    region_ids: tuple[str, ...],
    debounce_ms: int,
) -> dict[str, Any]:
    return {
        "live_preview_trigger": str(trigger or "").strip(),
        "live_preview_regions": ",".join(region_ids),
        "live_preview_debounce_ms": int(debounce_ms or 0),
    }


def _top_level_field_live_preview_metadata(
    *,
    field_name: str,
    preview_region_ids: tuple[str, ...],
    live_region_ids: tuple[str, ...],
    trigger: str,
    debounce_ms: int,
    kind: str = "",
) -> dict[str, Any]:
    return _live_preview_field_metadata(
        trigger=trigger,
        region_ids=_field_live_preview_region_ids(
            {"name": field_name, "kind": kind},
            preview_region_ids=preview_region_ids,
            live_region_ids=live_region_ids,
        ),
        debounce_ms=debounce_ms,
    )


def _level_one_field_live_preview_metadata() -> dict[str, dict[str, Any]]:
    metadata = {
        "name": _top_level_field_live_preview_metadata(
            field_name="name",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="blur",
            debounce_ms=0,
        ),
        "character_slug": _top_level_field_live_preview_metadata(
            field_name="character_slug",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="blur",
            debounce_ms=0,
        ),
        "alignment": _top_level_field_live_preview_metadata(
            field_name="alignment",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="blur",
            debounce_ms=0,
        ),
        "experience_model": _top_level_field_live_preview_metadata(
            field_name="experience_model",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="blur",
            debounce_ms=0,
        ),
        "class_slug": _top_level_field_live_preview_metadata(
            field_name="class_slug",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
        ),
        "subclass_slug": _top_level_field_live_preview_metadata(
            field_name="subclass_slug",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
        ),
        "species_slug": _top_level_field_live_preview_metadata(
            field_name="species_slug",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
        ),
        "background_slug": _top_level_field_live_preview_metadata(
            field_name="background_slug",
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
        ),
    }
    for ability_key in ABILITY_KEYS:
        metadata[ability_key] = _top_level_field_live_preview_metadata(
            field_name=ability_key,
            preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_ONE_LIVE_REGION_IDS,
            trigger="input",
            debounce_ms=BUILDER_TEXT_PREVIEW_DEBOUNCE_MS,
        )
    return metadata


def _level_up_field_live_preview_metadata() -> dict[str, dict[str, Any]]:
    return {
        "advancement_mode": _top_level_field_live_preview_metadata(
            field_name="advancement_mode",
            preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_UP_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_MODE_PREVIEW_DEBOUNCE_MS,
        ),
        "new_class_slug": _top_level_field_live_preview_metadata(
            field_name="new_class_slug",
            preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_UP_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_MODE_PREVIEW_DEBOUNCE_MS,
        ),
        "new_subclass_slug": _top_level_field_live_preview_metadata(
            field_name="new_subclass_slug",
            preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_UP_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_MODE_PREVIEW_DEBOUNCE_MS,
        ),
        "target_class_row_id": _top_level_field_live_preview_metadata(
            field_name="target_class_row_id",
            preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_UP_LIVE_REGION_IDS,
            trigger="change",
            debounce_ms=BUILDER_MODE_PREVIEW_DEBOUNCE_MS,
        ),
        "hp_gain": _top_level_field_live_preview_metadata(
            field_name="hp_gain",
            preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
            live_region_ids=LEVEL_UP_LIVE_REGION_IDS,
            trigger="input",
            debounce_ms=BUILDER_TEXT_PREVIEW_DEBOUNCE_MS,
        ),
    }


def _annotate_builder_choice_sections(
    choice_sections: list[dict[str, Any]],
    *,
    preview_region_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    live_region_ids = (CHOICE_SECTIONS_REGION_ID, *preview_region_ids)
    annotated_sections: list[dict[str, Any]] = []
    for section in list(choice_sections or []):
        section_copy = dict(section)
        section_copy["fields"] = []
        for raw_field in list(section.get("fields") or []):
            field = dict(raw_field)
            region_ids = _field_live_preview_region_ids(
                field,
                preview_region_ids=preview_region_ids,
                live_region_ids=live_region_ids,
            )
            field.update(
                _live_preview_field_metadata(
                    trigger="change",
                    region_ids=region_ids,
                    debounce_ms=BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS,
                )
            )
            section_copy["fields"].append(field)
        annotated_sections.append(section_copy)
    return annotated_sections
