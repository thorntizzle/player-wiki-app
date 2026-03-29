from __future__ import annotations

from collections import OrderedDict
from typing import Any

import markdown

from .character_models import CharacterRecord
from .models import Campaign
from .repository import build_alias_index, render_obsidian_links

ABILITY_ORDER = (
    ("str", "strength", "Strength"),
    ("dex", "dexterity", "Dexterity"),
    ("con", "constitution", "Constitution"),
    ("int", "intelligence", "Intelligence"),
    ("wis", "wisdom", "Wisdom"),
    ("cha", "charisma", "Charisma"),
)
PROFICIENCY_TITLES = (
    ("armor", "Armor"),
    ("weapons", "Weapons"),
    ("tools", "Tools"),
    ("languages", "Languages"),
)
FEATURE_GROUP_TITLES = {
    "class_feature": "Class Features",
    "species_trait": "Species Traits",
    "feat": "Feats",
    "background_feature": "Background Features",
    "custom_feature": "Custom Features",
}


def present_character_roster(records: list[CharacterRecord]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for record in records:
        definition = record.definition
        profile = definition.profile
        vitals = dict(record.state_record.state.get("vitals") or {})
        resources = sorted(
            list(record.state_record.state.get("resources") or []),
            key=lambda item: (int(item.get("display_order") or 0), str(item.get("label") or "").lower()),
        )
        resource_preview = [
            {
                "label": str(resource.get("label") or "Resource"),
                "value": summarize_resource_value(resource),
            }
            for resource in resources[:3]
        ]

        search_parts = [
            definition.name,
            str(profile.get("class_level_text") or ""),
            str(profile.get("species") or ""),
            str(profile.get("background") or ""),
        ]

        cards.append(
            {
                "slug": definition.character_slug,
                "name": definition.name,
                "class_level_text": str(profile.get("class_level_text") or "Character"),
                "species": str(profile.get("species") or ""),
                "background": str(profile.get("background") or ""),
                "current_hp": int(vitals.get("current_hp") or 0),
                "max_hp": int(definition.stats.get("max_hp") or 0),
                "temp_hp": int(vitals.get("temp_hp") or 0),
                "resource_preview": resource_preview,
                "search_text": " ".join(part for part in search_parts if part).lower(),
            }
        )
    return cards


def present_character_detail(
    campaign: Campaign,
    record: CharacterRecord,
    *,
    include_player_notes_section: bool = True,
) -> dict[str, Any]:
    definition = record.definition
    state = dict(record.state_record.state or {})
    vitals = dict(state.get("vitals") or {})
    stats = dict(definition.stats or {})
    profile = dict(definition.profile or {})
    classes = list(profile.get("classes") or [])
    first_class = dict(classes[0] or {}) if classes else {}
    resource_lookup = {
        str(resource.get("id") or ""): resource for resource in list(state.get("resources") or [])
    }
    equipment_catalog_lookup = {
        str(item.get("id") or ""): dict(item or {})
        for item in list(definition.equipment_catalog or [])
        if str(item.get("id") or "").strip()
    }

    overview_stats = [
        {"label": "Current HP", "value": f"{int(vitals.get('current_hp') or 0)} / {int(stats.get('max_hp') or 0)}"},
        {"label": "Temp HP", "value": str(int(vitals.get("temp_hp") or 0))},
        {"label": "Armor Class", "value": str(int(stats.get("armor_class") or 0))},
        {"label": "Initiative", "value": format_signed(stats.get("initiative_bonus"))},
        {"label": "Speed", "value": str(stats.get("speed") or "--")},
        {"label": "Proficiency", "value": format_signed(stats.get("proficiency_bonus"))},
        {"label": "Passive Perception", "value": str(int(stats.get("passive_perception") or 0))},
        {"label": "Passive Insight", "value": str(int(stats.get("passive_insight") or 0))},
        {"label": "Passive Investigation", "value": str(int(stats.get("passive_investigation") or 0))},
    ]

    death_saves = dict(vitals.get("death_saves") or {})
    death_save_summary = None
    if int(death_saves.get("successes") or 0) or int(death_saves.get("failures") or 0):
        death_save_summary = (
            f"{int(death_saves.get('successes') or 0)} success"
            f"{'' if int(death_saves.get('successes') or 0) == 1 else 'es'}, "
            f"{int(death_saves.get('failures') or 0)} failure"
            f"{'' if int(death_saves.get('failures') or 0) == 1 else 's'}"
        )

    abilities = []
    ability_scores = dict(stats.get("ability_scores") or {})
    for ability_key, legacy_key, ability_name in ABILITY_ORDER:
        ability = resolve_ability_score_payload(ability_scores, ability_key, legacy_key)
        abilities.append(
            {
                "abbr": ability_key.upper(),
                "name": ability_name,
                "score": int(ability.get("score") or 0),
                "modifier": format_signed(ability.get("modifier")),
                "save_bonus": format_signed(ability.get("save_bonus")),
            }
        )

    skills = [
        {
            "name": str(skill.get("name") or "Skill"),
            "bonus": format_signed(skill.get("bonus")),
            "proficiency_label": humanize_value(skill.get("proficiency_level")),
            "is_proficient": str(skill.get("proficiency_level") or "none") != "none",
        }
        for skill in sorted(list(definition.skills or []), key=lambda item: str(item.get("name") or "").lower())
    ]

    proficiency_groups = []
    proficiencies = dict(definition.proficiencies or {})
    for key, title in PROFICIENCY_TITLES:
        values = [str(value).strip() for value in list(proficiencies.get(key) or []) if str(value).strip()]
        if values:
            proficiency_groups.append({"title": title, "values_list": values})

    resources = [
        {
            "id": str(resource.get("id") or ""),
            "label": str(resource.get("label") or "Resource"),
            "current": int(resource.get("current") or 0),
            "max": int(resource.get("max")) if resource.get("max") is not None else None,
            "value": summarize_resource_value(resource),
            "reset_on": str(resource.get("reset_on") or ""),
            "reset_label": humanize_value(resource.get("reset_on")),
            "is_manual": str(resource.get("reset_on") or "").lower() in {"manual", "other"},
            "notes": str(resource.get("notes") or "").strip(),
        }
        for resource in sorted(
            list(state.get("resources") or []),
            key=lambda item: (int(item.get("display_order") or 0), str(item.get("label") or "").lower()),
        )
    ]

    spellcasting_payload = dict(definition.spellcasting or {})
    spellcasting = None
    if spellcasting_payload.get("spells") or spellcasting_payload.get("slot_progression"):
        slot_lookup = {
            int(slot.get("level") or 0): dict(slot) for slot in list(state.get("spell_slots") or [])
        }
        slots = []
        for slot in list(spellcasting_payload.get("slot_progression") or []):
            level = int(slot.get("level") or 0)
            max_slots = int(slot.get("max_slots") or 0)
            state_slot = slot_lookup.get(level, {})
            used = int(state_slot.get("used") or 0)
            slots.append(
                {
                    "level": level,
                    "label": spell_level_label(level),
                    "available": max_slots - used,
                    "used": used,
                    "max": max_slots,
                }
            )

        spells = []
        for spell in list(spellcasting_payload.get("spells") or []):
            badges = []
            if bool(spell.get("is_always_prepared")):
                badges.append("Always prepared")
            if bool(spell.get("is_ritual")):
                badges.append("Ritual")
            mark = str(spell.get("mark") or "").strip()
            if mark and mark not in badges:
                badges.append(mark)

            spells.append(
                {
                    "name": str(spell.get("name") or "Spell"),
                    "href": build_systems_entry_href(campaign.slug, spell.get("systems_ref")),
                    "casting_time": str(spell.get("casting_time") or "--"),
                    "range": str(spell.get("range") or "--"),
                    "duration": str(spell.get("duration") or "--"),
                    "components": str(spell.get("components") or "--"),
                    "save_or_hit": str(spell.get("save_or_hit") or "--"),
                    "source": str(spell.get("source") or "").strip(),
                    "reference": str(spell.get("reference") or "").strip(),
                    "badges": badges,
                }
            )

        spellcasting = {
            "spellcasting_class": str(spellcasting_payload.get("spellcasting_class") or ""),
            "spellcasting_ability": str(spellcasting_payload.get("spellcasting_ability") or ""),
            "spell_save_dc": spellcasting_payload.get("spell_save_dc"),
            "spell_attack_bonus": format_signed(spellcasting_payload.get("spell_attack_bonus")),
            "slots": slots,
            "spells": spells,
        }

    feature_groups_ordered: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for feature in list(definition.features or []):
        group_title = FEATURE_GROUP_TITLES.get(
            str(feature.get("category") or ""),
            humanize_value(feature.get("category")) or "Features",
        )
        feature_groups_ordered.setdefault(group_title, [])
        tracker_ref = str(feature.get("tracker_ref") or "").strip()
        linked_resource = resource_lookup.get(tracker_ref) if tracker_ref else None
        metadata = [
            str(feature.get("source") or "").strip(),
            humanize_value(feature.get("activation_type")),
            summarize_linked_resource(linked_resource),
        ]
        feature_groups_ordered[group_title].append(
            {
                "name": str(feature.get("name") or "Feature"),
                "href": build_systems_entry_href(campaign.slug, feature.get("systems_ref")),
                "metadata": [part for part in metadata if part],
                "description_html": render_campaign_markdown(
                    campaign, str(feature.get("description_markdown") or "")
                ),
            }
        )

    attacks = [
        {
            "name": str(attack.get("name") or "Attack"),
            "href": build_systems_entry_href(campaign.slug, attack.get("systems_ref")),
            "attack_bonus": format_signed(attack.get("attack_bonus")),
            "damage": str(attack.get("damage") or "--"),
            "category": humanize_value(attack.get("category")),
            "notes": str(attack.get("notes") or "").strip(),
        }
        for attack in list(definition.attacks or [])
    ]

    inventory = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Item"),
            "href": build_systems_entry_href(
                campaign.slug,
                equipment_catalog_lookup.get(str(item.get("catalog_ref") or item.get("id") or ""), {}).get("systems_ref"),
            ),
            "quantity": int(item.get("quantity") or 0),
            "weight": str(item.get("weight") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
            "tags": [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()],
            "is_equipped": bool(item.get("is_equipped", False)),
            "is_attuned": bool(item.get("is_attuned", False)),
        }
        for item in list(state.get("inventory") or [])
    ]

    currency_payload = dict(state.get("currency") or {})
    currency = [
        {"label": label.upper(), "amount": int(currency_payload.get(label) or 0)}
        for label in ("cp", "sp", "ep", "gp", "pp")
    ]
    other_currency = [str(item).strip() for item in list(currency_payload.get("other") or []) if str(item).strip()]

    reference_sections = build_reference_sections(
        campaign,
        definition.to_dict(),
        state,
        include_player_notes=include_player_notes_section,
    )

    feature_groups = [
        {"title": title, "entries": entries} for title, entries in feature_groups_ordered.items() if entries
    ]

    class_level_href = build_systems_entry_href(
        campaign.slug,
        profile.get("class_ref") or first_class.get("systems_ref"),
    )
    subclass_ref = profile.get("subclass_ref") or first_class.get("subclass_ref")
    subclass_label = str(first_class.get("subclass_name") or (subclass_ref or {}).get("title") or "").strip()
    header_segments = [
        {
            "text": str(profile.get("class_level_text") or "Character"),
            "href": class_level_href,
        }
    ]
    if subclass_label:
        header_segments.append(
            {
                "text": subclass_label,
                "href": build_systems_entry_href(campaign.slug, subclass_ref),
            }
        )
    if str(profile.get("species") or "").strip():
        header_segments.append(
            {
                "text": str(profile.get("species") or ""),
                "href": build_systems_entry_href(campaign.slug, profile.get("species_ref")),
            }
        )
    if str(profile.get("background") or "").strip():
        header_segments.append(
            {
                "text": str(profile.get("background") or ""),
                "href": build_systems_entry_href(campaign.slug, profile.get("background_ref")),
            }
        )

    return {
        "slug": definition.character_slug,
        "name": definition.name,
        "state_revision": record.state_record.revision,
        "current_hp": int(vitals.get("current_hp") or 0),
        "max_hp": int(stats.get("max_hp") or 0),
        "temp_hp": int(vitals.get("temp_hp") or 0),
        "player_notes_markdown": str((state.get("notes") or {}).get("player_notes_markdown") or ""),
        "class_level_text": str(profile.get("class_level_text") or "Character"),
        "header_segments": [segment for segment in header_segments if str(segment.get("text") or "").strip()],
        "species": str(profile.get("species") or ""),
        "background": str(profile.get("background") or ""),
        "alignment": str(profile.get("alignment") or ""),
        "identity_details": [
            {"label": "Size", "value": str(profile.get("size") or "").strip()},
            {"label": "Faith", "value": str(profile.get("faith") or "").strip()},
            {"label": "Guild", "value": str(profile.get("guild") or "").strip()},
            {"label": "Experience", "value": str(profile.get("experience_model") or "").strip()},
        ],
        "overview_stats": overview_stats,
        "death_save_summary": death_save_summary,
        "abilities": abilities,
        "skills": skills,
        "proficiency_groups": proficiency_groups,
        "resources": resources,
        "attacks": attacks,
        "feature_groups": feature_groups,
        "spellcasting": spellcasting,
        "inventory": inventory,
        "currency": currency,
        "currency_values": {
            label: int(currency_payload.get(label) or 0) for label in ("cp", "sp", "ep", "gp", "pp")
        },
        "other_currency": other_currency,
        "reference_sections": reference_sections,
    }


def build_reference_sections(
    campaign: Campaign,
    definition_payload: dict[str, Any],
    state: dict[str, Any],
    *,
    include_player_notes: bool = True,
) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    profile = dict(definition_payload.get("profile") or {})
    reference_notes = dict(definition_payload.get("reference_notes") or {})

    def add_section(title: str, markdown_text: str) -> None:
        clean_title = title.strip()
        clean_body = markdown_text.strip()
        if not clean_title or not clean_body:
            return
        signature = (clean_title.lower(), clean_body)
        if signature in seen_keys:
            return
        html = render_campaign_markdown(campaign, clean_body)
        if not html:
            return
        seen_keys.add(signature)
        sections.append({"title": clean_title, "html": html})

    add_section("Biography", str(profile.get("biography_markdown") or ""))
    add_section("Personality", str(profile.get("personality_markdown") or ""))

    custom_sections = list(reference_notes.get("custom_sections") or [])
    if not any(str(section.get("title") or "").strip().lower() == "additional notes" for section in custom_sections):
        add_section("Additional Notes", str(reference_notes.get("additional_notes_markdown") or ""))

    add_section(
        "Allies and Organizations",
        str(reference_notes.get("allies_and_organizations_markdown") or ""),
    )

    for section in custom_sections:
        add_section(str(section.get("title") or ""), str(section.get("body_markdown") or ""))

    if include_player_notes:
        add_section("Player Notes", str((state.get("notes") or {}).get("player_notes_markdown") or ""))

    return sections


def build_systems_entry_href(campaign_slug: str, systems_ref: Any) -> str:
    payload = dict(systems_ref or {})
    slug = str(payload.get("slug") or "").strip()
    if not slug or not campaign_slug.strip():
        return ""
    return f"/campaigns/{campaign_slug}/systems/entries/{slug}"


def render_campaign_markdown(campaign: Campaign, markdown_text: str) -> str:
    clean_text = markdown_text.strip()
    if not clean_text:
        return ""

    alias_index = build_alias_index(campaign)
    resolved_links: list[str] = []
    linked_markdown = render_obsidian_links(clean_text, alias_index, resolved_links)
    renderer = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    html = renderer.convert(linked_markdown)
    return html.replace("/campaigns/{campaign_slug}/", f"/campaigns/{campaign.slug}/")


def summarize_resource_value(resource: dict[str, Any]) -> str:
    current = int(resource.get("current") or 0)
    max_value = resource.get("max")
    if max_value is None:
        return str(current)
    return f"{current} / {int(max_value)}"


def summarize_linked_resource(resource: dict[str, Any] | None) -> str:
    if resource is None:
        return ""
    label = str(resource.get("label") or "Resource")
    summary = summarize_resource_value(resource)
    reset_label = humanize_value(resource.get("reset_on"))
    if reset_label and reset_label not in {"Manual", "Never", "Other"}:
        return f"{label}: {summary} ({reset_label})"
    return f"{label}: {summary}"


def resolve_ability_score_payload(
    ability_scores: dict[str, Any],
    ability_key: str,
    legacy_key: str,
) -> dict[str, Any]:
    payload = ability_scores.get(ability_key)
    if isinstance(payload, dict):
        return dict(payload)
    legacy_payload = ability_scores.get(legacy_key)
    if isinstance(legacy_payload, dict):
        return dict(legacy_payload)
    return {}


def format_signed(value: Any) -> str:
    return f"{int(value or 0):+d}"


def humanize_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").title()


def spell_level_label(level: int) -> str:
    if level == 1:
        return "1st level"
    if level == 2:
        return "2nd level"
    if level == 3:
        return "3rd level"
    return f"{level}th level"
