from __future__ import annotations

from typing import Any

SESSION_CHARACTER_SECTION_LABELS = {
    "overview": "Overview",
    "spells": "Spells",
    "resources": "Resources",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "abilities_skills": "Abilities and Skills",
    "notes": "Notes",
    "personal": "Personal",
}

COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS = {
    "actions": "Actions",
    "bonus_actions": "Bonus Actions",
    "reactions": "Reactions",
    "attacks": "Attacks",
    "spells": "Spells",
    "resources": "Resources",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "abilities_skills": "Abilities and Skills",
}


def iter_feature_entries(entries: object):
    for item in list(entries or []):
        if not isinstance(item, dict):
            continue
        yield item
        yield from iter_feature_entries(item.get("children"))


def build_session_character_sections(
    character_detail: dict[str, object],
    *,
    equipment_state_manager: dict[str, object] | None = None,
    include_spellcasting: bool = False,
    session_character_subpage_labels: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    xianxia_read = (
        dict(character_detail.get("xianxia_read") or {})
        if isinstance(character_detail.get("xianxia_read"), dict)
        else None
    )
    spellcasting = dict(character_detail.get("spellcasting") or {})
    resources = [dict(item or {}) for item in list(character_detail.get("resources") or [])]
    feature_groups = [dict(group or {}) for group in list(character_detail.get("feature_groups") or [])]
    overview_stats = [dict(item or {}) for item in list(character_detail.get("overview_stats") or [])]
    overview_stat_rows = [
        list(row or []) for row in list(character_detail.get("overview_stat_rows") or [])
    ]
    defensive_rules = [dict(item or {}) for item in list(character_detail.get("defensive_rules") or [])]
    equipment_rows = [
        dict(item or {})
        for item in list((equipment_state_manager or {}).get("rows") or [])
    ]
    item_use_actions = [
        dict(item or {}) for item in list(character_detail.get("item_use_actions") or [])
    ]
    arcane_armor_available = bool(
        dict(character_detail.get("arcane_armor_state") or {}).get("available")
        if isinstance(character_detail.get("arcane_armor_state"), dict)
        else False
    )
    inventory_rows = [dict(item or {}) for item in list(character_detail.get("inventory") or [])]
    skills = [dict(item or {}) for item in list(character_detail.get("skills") or [])]
    reference_sections = [
        dict(item or {}) for item in list(character_detail.get("reference_sections") or [])
    ]
    spell_count = sum(
        len(list(section.get("spells") or []))
        for section in list(spellcasting.get("row_sections") or [])
        if isinstance(section, dict)
    )
    if xianxia_read:
        xianxia_resources = dict(xianxia_read.get("resources") or {})
        xianxia_approval = dict(xianxia_read.get("approval") or {})
        xianxia_equipment = dict(xianxia_read.get("equipment") or {})
        xianxia_inventory = dict(xianxia_read.get("inventory") or {})
        xianxia_quick_reference = dict(xianxia_read.get("quick_reference") or {})
        xianxia_status_groups = [
            dict(group or {})
            for group in list(xianxia_approval.get("status_groups") or [])
            if isinstance(group, dict)
        ]
        xianxia_counts = {
            "quick": (
                len(overview_stats)
                + int(bool(xianxia_quick_reference.get("check_formula")))
                + int(bool(xianxia_quick_reference.get("difficulty_states")))
                + int(bool(xianxia_quick_reference.get("honor_interactions")))
                + int(bool(xianxia_quick_reference.get("skill_use_guardrails")))
                + len(list(xianxia_quick_reference.get("rule_text_references") or []))
                + int(bool(xianxia_quick_reference.get("actions")))
                + int(bool(xianxia_quick_reference.get("defense")))
                + int(bool(xianxia_quick_reference.get("effort_damage")))
                + len(list(xianxia_quick_reference.get("active_state_reminders") or []))
                + int(bool(xianxia_quick_reference.get("stance_break")))
            ),
            "martial_arts": len(list(xianxia_read.get("martial_arts") or [])),
            "techniques": (
                len(list(xianxia_read.get("generic_techniques") or []))
                + len(list(xianxia_read.get("basic_actions") or []))
                + sum(len(list(group.get("records") or [])) for group in xianxia_status_groups)
                + len(list(xianxia_approval.get("dao_immolating_prepared") or []))
            ),
            "resources": (
                len(list(xianxia_resources.get("durability") or []))
                + len(list(xianxia_resources.get("energies") or []))
                + len(list(xianxia_resources.get("yin_yang") or []))
                + int(bool(xianxia_resources.get("dao")))
                + int(bool(xianxia_resources.get("insight")))
            ),
            "skills": len(list(dict(xianxia_read.get("skills") or {}).get("trained") or [])),
            "equipment": (
                1
                + len(list(xianxia_equipment.get("necessary_weapons") or []))
                + len(list(xianxia_equipment.get("necessary_tools") or []))
            ),
            "inventory": len(list(xianxia_inventory.get("quantities") or [])),
            "personal": (
                int(bool(character_detail.get("portrait")))
                + int(bool(character_detail.get("physical_description_html")))
                + int(bool(character_detail.get("personal_background_html")))
            ),
            "notes": int(bool(character_detail.get("player_notes_html"))) + len(reference_sections),
        }
        return [
            {
                "slug": slug,
                "label": label,
                "count": int(xianxia_counts.get(slug) or 0),
            }
            for slug, label in dict(session_character_subpage_labels or {}).items()
        ]

    labels = dict(session_character_subpage_labels or {})
    sections = [
        {
            "slug": "overview",
            "label": labels.get("overview", SESSION_CHARACTER_SECTION_LABELS["overview"]),
            "count": (
                sum(len(row) for row in overview_stat_rows)
                if overview_stat_rows
                else len(overview_stats)
            )
            + len(defensive_rules),
        },
    ]
    if include_spellcasting:
        sections.append(
            {
                "slug": "spells",
                "label": labels.get("spells", SESSION_CHARACTER_SECTION_LABELS["spells"]),
                "count": spell_count,
            }
        )
    sections.extend(
        [
            {
                "slug": "resources",
                "label": labels.get("resources", SESSION_CHARACTER_SECTION_LABELS["resources"]),
                "count": len(resources),
            },
            {
                "slug": "features",
                "label": labels.get("features", SESSION_CHARACTER_SECTION_LABELS["features"]),
                "count": sum(
                    len(list(group.get("entries") or [])) for group in feature_groups
                ),
            },
            {
                "slug": "equipment",
                "label": labels.get("equipment", SESSION_CHARACTER_SECTION_LABELS["equipment"]),
                "count": len(equipment_rows) + len(item_use_actions) + int(arcane_armor_available),
            },
            {
                "slug": "inventory",
                "label": labels.get("inventory", SESSION_CHARACTER_SECTION_LABELS["inventory"]),
                "count": len(inventory_rows),
            },
            {
                "slug": "abilities_skills",
                "label": labels.get(
                    "abilities_skills",
                    SESSION_CHARACTER_SECTION_LABELS["abilities_skills"],
                ),
                "count": len(skills),
            },
            {
                "slug": "notes",
                "label": labels.get("notes", SESSION_CHARACTER_SECTION_LABELS["notes"]),
                "count": int(bool(character_detail.get("player_notes_html")))
                + len(reference_sections),
            },
            {
                "slug": "personal",
                "label": labels.get("personal", SESSION_CHARACTER_SECTION_LABELS["personal"]),
                "count": (
                    int(bool(character_detail.get("portrait")))
                    + int(bool(character_detail.get("physical_description_html")))
                    + int(bool(character_detail.get("personal_background_html")))
                ),
            },
        ]
    )
    return sections


def build_combat_character_workspace_sections(
    character_detail: dict[str, object],
    equipment_state_manager: dict[str, object],
) -> tuple[list[dict[str, object]], str]:
    action_features: list[dict[str, object]] = []
    bonus_action_features: list[dict[str, object]] = []
    reaction_features: list[dict[str, object]] = []
    feature_groups = [dict(group or {}) for group in list(character_detail.get("feature_groups") or [])]

    for group in feature_groups:
        group_title = str(group.get("title") or "Features").strip() or "Features"
        for feature in iter_feature_entries(group.get("entries")):
            feature_payload = dict(feature or {})
            feature_payload.pop("children", None)
            feature_payload["group_title"] = group_title
            combat_availability = dict(feature_payload.get("combat_availability") or {})
            if combat_availability and not bool(combat_availability.get("available", True)):
                continue
            activation_type = str(feature_payload.get("activation_type") or "").strip().lower()
            if activation_type == "action":
                action_features.append(feature_payload)
            elif activation_type == "bonus_action":
                bonus_action_features.append(feature_payload)
            elif activation_type == "reaction":
                reaction_features.append(feature_payload)

    attack_reminders = [dict(item or {}) for item in list(character_detail.get("attack_reminders") or [])]
    defensive_rules = [dict(item or {}) for item in list(character_detail.get("defensive_rules") or [])]
    spellcasting = dict(character_detail.get("spellcasting") or {})
    resources = [dict(item or {}) for item in list(character_detail.get("resources") or [])]
    attacks = [dict(item or {}) for item in list(character_detail.get("attacks") or [])]
    hidden_attacks = []
    for item in list(character_detail.get("hidden_attacks") or []):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            hidden_attacks.append(
                {
                    "name": name,
                    "href": str(item.get("href") or "").strip(),
                }
            )
            continue
        name = str(item).strip()
        if not name:
            continue
        hidden_attacks.append({"name": name, "href": ""})
    equipment_rows = [dict(item or {}) for item in list(equipment_state_manager.get("rows") or [])]
    item_use_actions = [dict(item or {}) for item in list(character_detail.get("item_use_actions") or [])]
    arcane_armor_state = (
        dict(character_detail.get("arcane_armor_state") or {})
        if isinstance(character_detail.get("arcane_armor_state"), dict)
        else {}
    )
    inventory_rows = [dict(item or {}) for item in list(character_detail.get("inventory") or [])]
    equipment_item_refs = {
        str(item_ref).strip()
        for item_ref in list(equipment_state_manager.get("equipment_item_refs") or [])
        if str(item_ref).strip()
    }
    attunable_item_refs = {
        str(item_ref).strip()
        for item_ref in list(equipment_state_manager.get("attunable_item_refs") or [])
        if str(item_ref).strip()
    }
    for item in inventory_rows:
        item_ref = str(item.get("item_ref") or item.get("id") or "").strip()
        item["show_equipped_badge"] = bool(item_ref in equipment_item_refs and item.get("is_equipped"))
        item["show_attuned_badge"] = bool(item_ref in attunable_item_refs and item.get("is_attuned"))
    currency_rows = [dict(item or {}) for item in list(character_detail.get("currency") or [])]
    other_currency = [str(item).strip() for item in list(character_detail.get("other_currency") or []) if str(item).strip()]
    abilities = [dict(item or {}) for item in list(character_detail.get("abilities") or [])]
    skills = [dict(item or {}) for item in list(character_detail.get("skills") or [])]
    proficiency_groups = [dict(item or {}) for item in list(character_detail.get("proficiency_groups") or [])]

    spell_count = sum(
        len(list(section.get("spells") or []))
        for section in list(spellcasting.get("row_sections") or [])
        if isinstance(section, dict)
    )
    sections = [
        {
            "slug": "actions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["actions"],
            "count": len(action_features),
            "has_content": bool(action_features),
            "features": action_features,
            "empty_message": "No action-specific features are recorded on this sheet yet.",
        },
        {
            "slug": "bonus_actions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["bonus_actions"],
            "count": len(bonus_action_features),
            "has_content": bool(bonus_action_features),
            "features": bonus_action_features,
            "empty_message": "No bonus-action features are recorded on this sheet yet.",
        },
        {
            "slug": "reactions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["reactions"],
            "count": len(reaction_features),
            "has_content": bool(reaction_features),
            "features": reaction_features,
            "empty_message": "No reaction features are recorded on this sheet yet.",
        },
        {
            "slug": "attacks",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["attacks"],
            "count": len(attacks),
            "has_content": bool(attacks or hidden_attacks or attack_reminders),
            "attacks": attacks,
            "hidden_attacks": hidden_attacks,
            "attack_reminders": attack_reminders,
            "empty_message": "No attacks are currently active on this sheet.",
        },
        {
            "slug": "spells",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["spells"],
            "count": spell_count,
            "has_content": bool(spellcasting),
            "spellcasting": spellcasting,
            "empty_message": "No spellcasting details are recorded on this sheet.",
        },
        {
            "slug": "resources",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["resources"],
            "count": len(resources),
            "has_content": bool(resources),
            "resources": resources,
            "empty_message": "No tracked limited-use resources are recorded on this sheet.",
        },
        {
            "slug": "features",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["features"],
            "count": sum(len(list(group.get("entries") or [])) for group in feature_groups),
            "has_content": bool(feature_groups or defensive_rules),
            "feature_groups": feature_groups,
            "defensive_rules": defensive_rules,
            "empty_message": "No feature details are recorded on this sheet yet.",
        },
        {
            "slug": "equipment",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["equipment"],
            "count": len(equipment_rows) + len(item_use_actions) + int(bool(arcane_armor_state.get("available"))),
            "has_content": bool(equipment_rows or item_use_actions or arcane_armor_state.get("available")),
            "equipment_state_manager": equipment_state_manager,
            "arcane_armor_state": arcane_armor_state,
            "item_use_actions": item_use_actions,
            "empty_message": "No equipment is listed on this sheet yet.",
        },
        {
            "slug": "inventory",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["inventory"],
            "count": len(inventory_rows),
            "has_content": bool(
                inventory_rows
                or any(int(item.get("amount") or 0) for item in currency_rows)
                or other_currency
            ),
            "inventory": inventory_rows,
            "currency": currency_rows,
            "other_currency": other_currency,
            "empty_message": "No inventory or currency is listed on this sheet yet.",
        },
        {
            "slug": "abilities_skills",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["abilities_skills"],
            "count": len(skills),
            "has_content": bool(abilities or skills or proficiency_groups),
            "abilities": abilities,
            "skills": skills,
            "proficiency_groups": proficiency_groups,
            "empty_message": "No ability or skill details are recorded on this sheet yet.",
        },
    ]
    sections = [section for section in sections if section["has_content"]]
    default_section = next((section["slug"] for section in sections), "")
    for section in sections:
        section["is_default"] = section["slug"] == default_section
    return sections, default_section


def serialize_combat_workspace_feature(feature: dict[str, Any], *, group_title: str) -> dict[str, Any]:
    return {
        "name": str(feature.get("name") or "").strip(),
        "href": str(feature.get("href") or "").strip(),
        "group_title": group_title,
        "metadata": [str(item).strip() for item in list(feature.get("metadata") or []) if str(item).strip()],
        "description_html": str(feature.get("description_html") or "").strip(),
    }


def build_combat_character_workspace_sections_payload(
    character_detail: dict[str, object],
) -> list[dict[str, Any]]:
    action_features: list[dict[str, Any]] = []
    bonus_action_features: list[dict[str, Any]] = []
    reaction_features: list[dict[str, Any]] = []
    feature_groups = [
        dict(group or {})
        for group in list(character_detail.get("feature_groups") or [])
        if isinstance(group, dict)
    ]
    for group in feature_groups:
        group_title = str(group.get("title") or "Features").strip() or "Features"
        for feature in iter_feature_entries(group.get("entries")):
            feature_payload = dict(feature or {})
            combat_availability = dict(feature_payload.get("combat_availability") or {})
            if combat_availability and not bool(combat_availability.get("available", True)):
                continue
            activation_type = str(feature_payload.get("activation_type") or "").strip().lower()
            serialized = serialize_combat_workspace_feature(feature_payload, group_title=group_title)
            if not serialized["name"]:
                continue
            if activation_type == "action":
                action_features.append(serialized)
            elif activation_type == "bonus_action":
                bonus_action_features.append(serialized)
            elif activation_type == "reaction":
                reaction_features.append(serialized)

    attacks = [
        {
            "name": str(item.get("name") or "").strip(),
            "attack_bonus": str(item.get("attack_bonus") or item.get("to_hit") or "").strip(),
            "damage": str(item.get("damage") or item.get("damage_label") or "").strip(),
            "range": str(item.get("range") or item.get("range_label") or "").strip(),
            "notes": str(item.get("notes") or item.get("description") or "").strip(),
        }
        for item in list(character_detail.get("attacks") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    hidden_attacks = []
    for item in list(character_detail.get("hidden_attacks") or []):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            href = str(item.get("href") or "").strip()
        else:
            name = str(item or "").strip()
            href = ""
        if name:
            hidden_attacks.append({"name": name, "href": href})

    feature_group_summaries = [
        {
            "title": str(group.get("title") or "Features").strip() or "Features",
            "features": [
                serialize_combat_workspace_feature(
                    dict(feature or {}),
                    group_title=str(group.get("title") or "Features").strip() or "Features",
                )
                for feature in iter_feature_entries(group.get("entries"))
                if str(dict(feature or {}).get("name") or "").strip()
            ],
        }
        for group in feature_groups
    ]

    sections = [
        {
            "slug": "actions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["actions"],
            "count": len(action_features),
            "features": action_features,
            "empty_message": "No action-specific features are recorded on this sheet yet.",
        },
        {
            "slug": "bonus_actions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["bonus_actions"],
            "count": len(bonus_action_features),
            "features": bonus_action_features,
            "empty_message": "No bonus-action features are recorded on this sheet yet.",
        },
        {
            "slug": "reactions",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["reactions"],
            "count": len(reaction_features),
            "features": reaction_features,
            "empty_message": "No reaction features are recorded on this sheet yet.",
        },
        {
            "slug": "attacks",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["attacks"],
            "count": len(attacks),
            "attacks": attacks,
            "hidden_attacks": hidden_attacks,
            "empty_message": "No attacks are currently active on this sheet.",
        },
        {
            "slug": "features",
            "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["features"],
            "count": sum(len(group["features"]) for group in feature_group_summaries),
            "feature_groups": feature_group_summaries,
            "empty_message": "No feature details are recorded on this sheet yet.",
        },
    ]
    return [
        section
        for section in sections
        if int(section.get("count") or 0) > 0 or section.get("hidden_attacks")
    ]
