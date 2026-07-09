from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from typing import Any

from .character_models import CharacterRecord
from .character_presenter import present_character_detail
from .models import Campaign
from .system_policy import is_dnd_5e_system


class CharacterMarkdownExportError(ValueError):
    pass


def export_filename_for_character(record: CharacterRecord) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", record.definition.character_slug).strip("-")
    return f"{slug or 'character'}.md"


def render_dnd_character_markdown(
    campaign: Campaign,
    record: CharacterRecord,
    *,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> str:
    if not is_dnd_5e_system(record.definition.system):
        raise CharacterMarkdownExportError(
            f"Markdown export is currently supported for DND-5E characters only: {record.definition.name}"
        )

    character = present_character_detail(
        campaign,
        record,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    lines: list[str] = []
    definition = record.definition

    _heading(lines, 1, character.get("name") or definition.name)
    _key_values(
        lines,
        [
            ("Campaign", campaign.title),
            ("Campaign slug", campaign.slug),
            ("Character slug", definition.character_slug),
            ("System", definition.system),
            ("Status", definition.status),
            ("State revision", character.get("state_revision")),
        ],
    )

    _write_identity_section(lines, character)
    _write_overview_section(lines, character)
    _write_abilities_section(lines, character)
    _write_proficiencies_section(lines, character)
    _write_resources_section(lines, character)
    _write_spellcasting_section(lines, character)
    _write_attacks_section(lines, character)
    _write_features_section(lines, character, definition.features)
    _write_inventory_section(lines, character)
    _write_notes_section(lines, character)
    _write_source_section(lines, record)

    return _normalize_markdown("\n".join(lines))


def _write_identity_section(lines: list[str], character: dict[str, Any]) -> None:
    _heading(lines, 2, "Identity")
    values = [
        ("Class / level", character.get("class_level_text")),
        ("Species", character.get("species")),
        ("Background", character.get("background")),
        ("Alignment", character.get("alignment")),
    ]
    for detail in list(character.get("identity_details") or []):
        values.append((detail.get("label"), detail.get("value")))
    _key_values(lines, values)


def _write_overview_section(lines: list[str], character: dict[str, Any]) -> None:
    _heading(lines, 2, "At a Glance")
    _table(
        lines,
        ["Statistic", "Value"],
        [
            [stat.get("label"), stat.get("value")]
            for stat in list(character.get("overview_stats") or [])
        ],
    )
    death_save_summary = _clean_text(character.get("death_save_summary"))
    if death_save_summary:
        lines.append(f"- Death saves: {death_save_summary}")
        lines.append("")
    _write_named_rule_cards(lines, "Defensive Rules", character.get("defensive_rules"))
    _write_named_rule_cards(lines, "Attack Reminders", character.get("attack_reminders"))


def _write_abilities_section(lines: list[str], character: dict[str, Any]) -> None:
    _heading(lines, 2, "Abilities and Skills")
    ability_rows = []
    for ability in list(character.get("abilities") or []):
        skill_text = "; ".join(
            _format_skill(skill) for skill in list(ability.get("skills") or [])
        )
        ability_rows.append(
            [
                ability.get("name"),
                ability.get("score"),
                ability.get("modifier"),
                ability.get("save_bonus"),
                skill_text,
            ]
        )
    _table(lines, ["Ability", "Score", "Mod", "Save", "Skills"], ability_rows)

    all_skills = list(character.get("skills") or [])
    if all_skills:
        lines.append("All skills:")
        lines.append("")
        _table(
            lines,
            ["Skill", "Bonus", "Proficiency"],
            [
                [skill.get("name"), skill.get("bonus"), skill.get("proficiency_label")]
                for skill in all_skills
            ],
        )


def _write_proficiencies_section(lines: list[str], character: dict[str, Any]) -> None:
    _heading(lines, 2, "Proficiencies")
    groups = list(character.get("proficiency_groups") or [])
    if not groups:
        lines.append("None.")
        lines.append("")
        return
    for group in groups:
        values = ", ".join(_clean_text(value) for value in list(group.get("values_list") or []))
        lines.append(f"- **{_clean_text(group.get('title'))}:** {values}")
    lines.append("")


def _write_resources_section(lines: list[str], character: dict[str, Any]) -> None:
    resources = list(character.get("resources") or [])
    if not resources:
        return
    _heading(lines, 2, "Resources")
    _table(
        lines,
        ["Resource", "Current", "Maximum", "Reset", "Notes"],
        [
            [
                resource.get("label"),
                resource.get("current"),
                _display_optional(resource.get("max")),
                resource.get("reset_label"),
                resource.get("notes"),
            ]
            for resource in resources
        ],
    )


def _write_spellcasting_section(lines: list[str], character: dict[str, Any]) -> None:
    spellcasting = character.get("spellcasting")
    if not spellcasting:
        return

    _heading(lines, 2, "Spellcasting")
    _key_values(
        lines,
        [
            ("Class", spellcasting.get("spellcasting_class")),
            ("Ability", spellcasting.get("spellcasting_ability")),
            ("Save DC", spellcasting.get("spell_save_dc")),
            ("Attack bonus", spellcasting.get("spell_attack_bonus")),
        ],
    )

    slot_pools = list(spellcasting.get("slot_pools") or [])
    for pool in slot_pools:
        if not list(pool.get("slots") or []):
            continue
        title = _clean_text(pool.get("title")) or "Spell slots"
        _heading(lines, 3, title)
        _table(
            lines,
            ["Slot", "Available", "Used", "Maximum"],
            [
                [slot.get("label"), slot.get("available"), slot.get("used"), slot.get("max")]
                for slot in list(pool.get("slots") or [])
            ],
        )

    _write_spell_rows(lines, "Current Spells", spellcasting.get("current_row_sections"))
    preparation_sections = list(spellcasting.get("preparation_row_sections") or [])
    if preparation_sections:
        _write_spell_rows(lines, "Preparation and Spellbook", preparation_sections)


def _write_spell_rows(lines: list[str], title: str, sections: Any) -> None:
    row_sections = list(sections or [])
    if not row_sections:
        return
    _heading(lines, 3, title)
    for section in row_sections:
        _heading(lines, 4, section.get("title") or "Spellcasting")
        _key_values(
            lines,
            [
                ("Ability", section.get("spellcasting_ability")),
                ("Save DC", section.get("spell_save_dc")),
                ("Attack bonus", section.get("spell_attack_bonus")),
            ],
        )
        counts = list(section.get("counts") or [])
        if counts:
            lines.append(
                "- "
                + "; ".join(
                    f"{_clean_text(count.get('label'))}: {_clean_text(count.get('value'))}"
                    for count in counts
                )
            )
            lines.append("")

        spells = list(section.get("spells") or [])
        _table(
            lines,
            ["Spell", "Level", "Casting", "Range", "Duration", "Components", "Save / attack", "Tags"],
            [
                [
                    _format_link(spell.get("name"), spell.get("href")),
                    _spell_level_text(spell),
                    spell.get("casting_time"),
                    spell.get("range"),
                    spell.get("duration"),
                    spell.get("components"),
                    spell.get("save_or_hit"),
                    _spell_tags(spell),
                ]
                for spell in spells
            ],
        )

        for spell in spells:
            details = _spell_detail_markdown(spell)
            if not details:
                continue
            _heading(lines, 5, spell.get("name") or "Spell Details")
            lines.extend(details)
            lines.append("")


def _write_attacks_section(lines: list[str], character: dict[str, Any]) -> None:
    attacks = list(character.get("attacks") or [])
    hidden_attacks = list(character.get("hidden_attacks") or [])
    if not attacks and not hidden_attacks:
        return
    _heading(lines, 2, "Attacks")
    _table(
        lines,
        ["Attack", "Bonus", "Damage", "Type", "Category", "Equipped", "Notes"],
        [
            [
                _format_link(attack.get("name"), attack.get("href")),
                attack.get("attack_bonus"),
                attack.get("damage"),
                attack.get("damage_type"),
                attack.get("category"),
                _yes_no(attack.get("is_equipped")),
                attack.get("notes"),
            ]
            for attack in attacks
        ],
    )
    if hidden_attacks:
        lines.append("Hidden attacks:")
        lines.append("")
        for attack in hidden_attacks:
            lines.append(f"- {_format_link(attack.get('name'), attack.get('href'))}")
        lines.append("")


def _write_features_section(
    lines: list[str],
    character: dict[str, Any],
    definition_features: list[dict[str, Any]],
) -> None:
    feature_groups = list(character.get("feature_groups") or [])
    if not feature_groups:
        return
    raw_lookup = _build_raw_feature_lookup(definition_features)
    _heading(lines, 2, "Features")
    for group in feature_groups:
        _heading(lines, 3, group.get("title") or "Features")
        for feature in list(group.get("entries") or []):
            _write_feature_entry(lines, feature, raw_lookup=raw_lookup, level=4)


def _write_feature_entry(
    lines: list[str],
    feature: dict[str, Any],
    *,
    raw_lookup: dict[str, dict[str, Any]],
    level: int,
) -> None:
    _heading(lines, level, _format_link(feature.get("name"), feature.get("href")))
    metadata = [item for item in list(feature.get("metadata") or []) if _clean_text(item)]
    if metadata:
        lines.append("- " + " | ".join(_clean_text(item) for item in metadata))
    availability = dict(feature.get("combat_availability") or {})
    if availability and not bool(availability.get("available", True)):
        reason = _clean_text(availability.get("reason"))
        lines.append(f"- Availability: {reason or 'Unavailable'}")
    if metadata or availability:
        lines.append("")

    description = _feature_description_markdown(feature, raw_lookup)
    if description:
        lines.append(description)
        lines.append("")

    for child in list(feature.get("children") or []):
        _write_feature_entry(lines, child, raw_lookup=raw_lookup, level=min(level + 1, 6))


def _write_inventory_section(lines: list[str], character: dict[str, Any]) -> None:
    inventory = list(character.get("inventory") or [])
    currency = list(character.get("currency") or [])
    other_currency = list(character.get("other_currency") or [])
    if not inventory and not currency and not other_currency:
        return

    _heading(lines, 2, "Equipment and Inventory")
    _table(
        lines,
        ["Item", "Quantity", "Weight", "Equipped", "Attuned", "Tags", "Notes"],
        [
            [
                _format_link(item.get("name"), item.get("href")),
                item.get("quantity"),
                item.get("weight"),
                _yes_no(item.get("is_equipped")),
                _yes_no(item.get("is_attuned")),
                ", ".join(_clean_text(tag) for tag in list(item.get("tags") or [])),
                item.get("notes"),
            ]
            for item in inventory
        ],
    )

    if currency or other_currency:
        _heading(lines, 3, "Currency")
        _table(
            lines,
            ["Coin", "Amount"],
            [[entry.get("label"), entry.get("amount")] for entry in currency],
        )
        if other_currency:
            lines.append("Other currency:")
            lines.append("")
            for value in other_currency:
                lines.append(f"- {_clean_text(value)}")
            lines.append("")


def _write_notes_section(lines: list[str], character: dict[str, Any]) -> None:
    _heading(lines, 2, "Character Notes and Reference")
    wrote_any = False

    note_sections = [
        ("Player Notes", character.get("player_notes_markdown")),
        ("Physical Description", character.get("physical_description_markdown")),
        ("Background", character.get("personal_background_markdown")),
    ]
    for title, body in note_sections:
        markdown = _clean_block(body)
        if not markdown:
            continue
        _heading(lines, 3, title)
        lines.append(markdown)
        lines.append("")
        wrote_any = True

    for section in list(character.get("reference_sections") or []):
        body = _html_to_markdown(section.get("html"))
        if not body:
            continue
        _heading(lines, 3, section.get("title") or "Reference")
        lines.append(body)
        lines.append("")
        wrote_any = True

    if not wrote_any:
        lines.append("None.")
        lines.append("")


def _write_source_section(lines: list[str], record: CharacterRecord) -> None:
    _heading(lines, 2, "Source")
    definition_source = dict(record.definition.source or {})
    import_metadata = record.import_metadata
    _key_values(
        lines,
        [
            ("Sheet name", definition_source.get("sheet_name")),
            ("Imported from", definition_source.get("imported_from")),
            ("Source path", import_metadata.source_path),
            ("Imported at", import_metadata.imported_at_utc),
            ("Parser version", import_metadata.parser_version),
            ("Import status", import_metadata.import_status),
        ],
    )
    if import_metadata.warnings:
        lines.append("Import warnings:")
        lines.append("")
        for warning in import_metadata.warnings:
            lines.append(f"- {_clean_text(warning)}")
        lines.append("")


def _write_named_rule_cards(lines: list[str], title: str, records: Any) -> None:
    cards = list(records or [])
    if not cards:
        return
    _heading(lines, 3, title)
    for card in cards:
        name = _clean_text(card.get("title") or card.get("name") or card.get("label") or "Rule")
        lines.append(f"- **{name}**")
        effects = list(card.get("effects") or [])
        for effect in effects:
            effect_label = _clean_text(effect.get("label") or effect.get("name"))
            effect_value = _clean_text(effect.get("value") or effect.get("text"))
            if effect_label and effect_value:
                lines.append(f"  - {effect_label}: {effect_value}")
            elif effect_value:
                lines.append(f"  - {effect_value}")
        note = _clean_text(card.get("note") or card.get("description"))
        if note:
            lines.append(f"  - {note}")
    lines.append("")


def _build_raw_feature_lookup(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for feature in list(features or []):
        payload = dict(feature or {})
        feature_id = _clean_text(payload.get("id"))
        if feature_id:
            lookup[f"id:{feature_id}"] = payload
        name = _clean_text(payload.get("name")).casefold()
        if name:
            lookup.setdefault(f"name:{name}", payload)
    return lookup


def _feature_description_markdown(
    feature: dict[str, Any],
    raw_lookup: dict[str, dict[str, Any]],
) -> str:
    raw = raw_lookup.get(f"id:{_clean_text(feature.get('id'))}")
    if raw is None:
        raw = raw_lookup.get(f"name:{_clean_text(feature.get('name')).casefold()}")
    for key in ("description_markdown", "body_markdown", "markdown"):
        text = _clean_block((raw or {}).get(key))
        if text:
            return text
    return _html_to_markdown(feature.get("description_html"))


def _spell_detail_markdown(spell: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    management_note = _clean_text(spell.get("management_note"))
    if management_note:
        lines.append(f"- {management_note}")
    source_parts = [
        _clean_text(spell.get("source")),
        _clean_text(spell.get("reference")),
    ]
    source_text = " | ".join(part for part in source_parts if part)
    if source_text:
        lines.append(f"- Source: {source_text}")
    if spell.get("at_higher_levels"):
        lines.append(f"- At higher levels: {_clean_text(spell.get('at_higher_levels'))}")

    description = _html_to_markdown(spell.get("description_html"))
    if description:
        if lines:
            lines.append("")
        lines.append(description)
    return lines


def _spell_level_text(spell: dict[str, Any]) -> str:
    level = _clean_text(spell.get("level_label"))
    school = _clean_text(spell.get("school"))
    if level and school:
        return f"{level} ({school})"
    return level


def _spell_tags(spell: dict[str, Any]) -> str:
    badges = [_clean_text(value) for value in list(spell.get("badges") or []) if _clean_text(value)]
    return ", ".join(badges)


def _format_skill(skill: dict[str, Any]) -> str:
    proficiency = _clean_text(skill.get("proficiency_label"))
    suffix = "" if not proficiency or proficiency == "None" else f" ({proficiency})"
    return f"{_clean_text(skill.get('name'))} {_clean_text(skill.get('bonus'))}{suffix}"


def _key_values(lines: list[str], rows: list[tuple[Any, Any]]) -> None:
    wrote_any = False
    for label, value in rows:
        clean_label = _clean_text(label)
        clean_value = _clean_text(value)
        if not clean_label or not clean_value:
            continue
        lines.append(f"- **{clean_label}:** {clean_value}")
        wrote_any = True
    if wrote_any:
        lines.append("")


def _heading(lines: list[str], level: int, value: Any) -> None:
    text = _clean_text(value)
    if not text:
        return
    if lines and lines[-1] != "":
        lines.append("")
    prefix = "#" * max(1, min(level, 6))
    lines.append(f"{prefix} {text}")
    lines.append("")


def _table(lines: list[str], headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        lines.append("None.")
        lines.append("")
        return
    lines.append("| " + " | ".join(_table_cell(header) for header in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(_table_cell(value) for value in padded[: len(headers)]) + " |")
    lines.append("")


def _format_link(label: Any, href: Any) -> str:
    text = _clean_text(label)
    url = _clean_text(href)
    if not text:
        return ""
    if not url:
        return text
    return f"[{text}]({url})"


def _table_cell(value: Any) -> str:
    text = _clean_text(value)
    text = text.replace("\n", "<br>")
    return text.replace("|", "\\|")


def _display_optional(value: Any) -> str:
    return "--" if value in {None, ""} else _clean_text(value)


def _yes_no(value: Any) -> str:
    if value is None:
        return ""
    return "yes" if bool(value) else "no"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r\n", "\n").replace("\r", "\n").split())


def _clean_block(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize_markdown(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _html_to_markdown(value: Any) -> str:
    html = str(value or "").strip()
    if not html:
        return ""
    parser = _SimpleHtmlToMarkdown()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _SimpleHtmlToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._links: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"p", "div", "section", "article", "ul", "ol"}:
            self._blank_line()
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self._line()
            self.parts.append("- ")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._blank_line()
            level = int(tag[1])
            self.parts.append("#" * min(level + 2, 6) + " ")
        elif tag == "a":
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = value
                    break
            self._links.append(href or None)
            if href:
                self.parts.append("[")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a":
            href = self._links.pop() if self._links else None
            if href:
                self.parts.append(f"]({href})")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag in {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._blank_line()

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data)
        if text:
            self.parts.append(text)

    def _line(self) -> None:
        current = "".join(self.parts)
        if current and not current.endswith("\n"):
            self.parts.append("\n")

    def _blank_line(self) -> None:
        current = "".join(self.parts)
        if not current:
            return
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self.parts.append("\n")
        else:
            self.parts.append("\n\n")
