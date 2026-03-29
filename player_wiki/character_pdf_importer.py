from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .character_importer import (
    initialize_or_reconcile_imported_state,
    parse_character_sheet_text,
    preserve_existing_character_overrides,
    write_yaml,
)
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_repository import load_campaign_character_config
from .character_store import CharacterStateStore
from .repository import normalize_lookup
from .systems_models import SystemsEntryRecord
from .systems_service import SystemsService

PDF_PARSER_VERSION = "2026-03-29.2"
BULLET_CHAR = "\u2022"
EN_DASH_CHAR = "\u2013"

ABILITY_FIELDS = (
    ("Strength", "STR", "STRmod", "ST Strength"),
    ("Dexterity", "DEX", "DEXmod", "ST Dexterity"),
    ("Constitution", "CON", "CONmod", "ST Constitution"),
    ("Intelligence", "INT", "INTmod", "ST Intelligence"),
    ("Wisdom", "WIS", "WISmod", "ST Wisdom"),
    ("Charisma", "CHA", "CHamod", "ST Charisma"),
)

SKILL_FIELDS = (
    ("Acrobatics", "AcrobaticsProf", "Acrobatics"),
    ("Animal Handling", "AnimalHandlingProf", "Animal"),
    ("Arcana", "ArcanaProf", "Arcana"),
    ("Athletics", "AthleticsProf", "Athletics"),
    ("Deception", "DeceptionProf", "Deception"),
    ("History", "HistoryProf", "History"),
    ("Insight", "InsightProf", "Insight"),
    ("Intimidation", "IntimidationProf", "Intimidation"),
    ("Investigation", "InvestigationProf", "Investigation"),
    ("Medicine", "MedicineProf", "Medicine"),
    ("Nature", "NatureProf", "Nature"),
    ("Perception", "PerceptionProf", "Perception"),
    ("Performance", "PerformanceProf", "Performance"),
    ("Persuasion", "PersuasionProf", "Persuasion"),
    ("Religion", "ReligionProf", "Religion"),
    ("Sleight of Hand", "SleightOfHandProf", "SleightofHand"),
    ("Stealth", "StealthProf", "Stealth"),
    ("Survival", "SurvivalProf", "Survival"),
)

MATCH_TYPE_ORDER = {
    "class": 0,
    "subclass": 1,
    "background": 2,
    "race": 3,
    "classfeature": 4,
    "subclassfeature": 5,
    "optionalfeature": 6,
    "feat": 7,
    "spell": 8,
    "item": 9,
    "action": 10,
}

TRACKER_LINE_PATTERN = re.compile(
    r"^\d+\s*/\s*(?:Short Rest|Long Rest)\b|^\w.+:\s*\d+\s*/\s*(?:Short Rest|Long Rest)\b|"
    r"^\w.+:\s*(?:\d+\s*)?(?:Action|Bonus Action|Reaction|Special)$",
    re.IGNORECASE,
)
NON_LINKABLE_FEATURE_TITLES = {"Hit Points", "Proficiencies", "Special"}


@dataclass(slots=True)
class CharacterPdfPilotResult:
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    output_dir: Path
    fields_path: Path
    synthetic_markdown_path: Path
    definition_path: Path
    systems_links_path: Path
    report_path: Path


@dataclass(slots=True)
class CharacterPdfArtifacts:
    field_values: dict[str, str]
    synthetic_markdown: str
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    systems_links: dict[str, Any]


@dataclass(slots=True)
class CharacterPdfImportResult:
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    character_dir: Path
    state_created: bool


def _clean_pdf_text(value: object | None) -> str:
    if value is None:
        return ""
    rendered = str(value).strip()
    if rendered == "/Off":
        return ""
    return rendered.replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_pdf_annotation_fields(pdf_path: Path) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    field_values: dict[str, str] = {}
    for page in reader.pages:
        annots_ref = page.get("/Annots")
        if annots_ref is None:
            continue
        annots = annots_ref.get_object()
        for annot_ref in annots:
            annot = annot_ref.get_object()
            name = _clean_pdf_text(annot.get("/T"))
            if not name:
                continue
            value = _clean_pdf_text(annot.get("/V"))
            if value:
                field_values[name] = value
    return field_values


def _render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("\n", " ").strip() for cell in row) + " |")
    return "\n".join(lines)


def _series_values(field_values: dict[str, str], prefix: str) -> list[str]:
    items: list[tuple[int, str]] = []
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for key, value in field_values.items():
        match = pattern.match(key)
        if match and value.strip():
            items.append((int(match.group(1)), value.strip()))
    return [value for _, value in sorted(items)]


def _normalize_source_header(value: str) -> str:
    return value.replace(f" {BULLET_CHAR} ", " - ").replace(EN_DASH_CHAR, "-").strip()


def _normalize_pdf_block_to_markdown(raw_text: str) -> str:
    lines: list[str] = []
    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            lines.append("")
            continue
        heading_match = re.match(r"^===\s*(.+?)\s*===$", stripped)
        if heading_match:
            lines.append(f"### {heading_match.group(1).title()}")
            continue
        if stripped.startswith("* "):
            lines.append(f"- {_normalize_source_header(stripped[2:])}")
            continue
        if stripped.startswith("| "):
            lines.append(f"- {_normalize_source_header(stripped[2:])}")
            continue
        lines.append(_normalize_source_header(stripped))
    return "\n".join(lines).strip()


def _parse_named_groups(raw_text: str) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        heading_match = re.match(r"^===\s*(.+?)\s*===$", stripped)
        if heading_match:
            current = heading_match.group(1).strip().title()
            groups[current] = []
            continue
        if current is not None and stripped:
            groups[current].append(stripped)
    return {key: " ".join(value).strip() for key, value in groups.items()}


def _build_sheet_summary_section(field_values: dict[str, str]) -> str:
    rows = [
        ["Sheet Name", field_values.get("CharacterName", "")],
        ["Class & Level", field_values.get("CLASS  LEVEL", "")],
        ["Species", field_values.get("RACE", "")],
        ["Background", field_values.get("BACKGROUND", "")],
        ["Alignment", field_values.get("ALIGNMENT", "")],
        ["Experience", field_values.get("EXPERIENCE POINTS", "")],
        ["Size", field_values.get("SIZE", "")],
        ["Gender", field_values.get("GENDER", "")],
        ["Age", field_values.get("AGE", "")],
        ["Height", field_values.get("HEIGHT", "")],
        ["Weight", field_values.get("WEIGHT", "")],
        ["Eyes", field_values.get("EYES", "")],
        ["Hair", field_values.get("HAIR", "")],
        ["Skin", field_values.get("SKIN", "")],
        ["Faith", field_values.get("FAITH", "")],
    ]
    return _render_markdown_table(["Field", "Value"], rows)


def _build_core_stats_section(field_values: dict[str, str]) -> str:
    rows = [
        ["Armor Class", field_values.get("AC", "")],
        ["Initiative", field_values.get("Init", "")],
        ["Speed", field_values.get("Speed", "")],
        ["Max HP", field_values.get("MaxHP", "")],
        ["Proficiency Bonus", field_values.get("ProfBonus", "")],
        ["Passive Perception", field_values.get("Passive1", "")],
        ["Passive Insight", field_values.get("Passive2", "")],
        ["Passive Investigation", field_values.get("Passive3", "")],
    ]
    return _render_markdown_table(["Metric", "Value"], rows)


def _build_ability_scores_section(field_values: dict[str, str]) -> str:
    rows = [
        [
            ability,
            field_values.get(score_field, ""),
            field_values.get(mod_field, ""),
            field_values.get(save_field, ""),
        ]
        for ability, score_field, mod_field, save_field in ABILITY_FIELDS
    ]
    return _render_markdown_table(["Ability", "Score", "Modifier", "Save"], rows)


def _skill_proficiency_label(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"p", BULLET_CHAR.lower()}:
        return "Proficient"
    if normalized in {"e", "expertise"}:
        return "Expertise"
    return "None"


def _build_skills_section(field_values: dict[str, str]) -> str:
    rows = [
        [skill_name, field_values.get(bonus_field, ""), _skill_proficiency_label(field_values.get(prof_field, ""))]
        for skill_name, prof_field, bonus_field in SKILL_FIELDS
    ]
    return _render_markdown_table(["Skill", "Bonus", "Proficiency"], rows)


def _build_proficiencies_section(field_values: dict[str, str]) -> str:
    raw_groups = _parse_named_groups(field_values.get("ProficienciesLang", ""))
    ordered = ("Armor", "Weapons", "Tools", "Languages")
    lines = [
        f"- {group}: {raw_groups.get(group, '')}"
        for group in ordered
    ]
    return "\n".join(lines)


def _lookup_field(field_values: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        if candidate in field_values:
            return field_values[candidate]
    normalized_values = {normalize_lookup(key): value for key, value in field_values.items()}
    for candidate in candidates:
        value = normalized_values.get(normalize_lookup(candidate))
        if value is not None:
            return value
    return ""


def _build_attacks_section(field_values: dict[str, str]) -> str:
    rows: list[list[str]] = []
    for index in range(1, 7):
        name = _lookup_field(field_values, "Wpn Name" if index == 1 else f"Wpn Name {index}")
        if not name:
            continue
        rows.append(
            [
                name,
                _lookup_field(field_values, f"Wpn{index} AtkBonus"),
                _lookup_field(field_values, f"Wpn{index} Damage"),
                _lookup_field(field_values, f"Wpn Notes {index}"),
            ]
        )
    return _render_markdown_table(["Attack", "Hit", "Damage", "Notes"], rows)


def _build_features_section(field_values: dict[str, str]) -> str:
    combined = "\n\n".join(_series_values(field_values, "FeaturesTraits"))
    return _normalize_pdf_block_to_markdown(combined)


def _build_actions_section(field_values: dict[str, str]) -> str:
    combined = "\n\n".join(_series_values(field_values, "Actions"))
    return _normalize_pdf_block_to_markdown(combined)


def _build_personality_section(field_values: dict[str, str]) -> str:
    sections = [
        ("Personality Traits", field_values.get("PersonalityTraits", "")),
        ("Ideals", field_values.get("Ideals", "")),
        ("Bonds", field_values.get("Bonds", "")),
        ("Flaws", field_values.get("Flaws", "")),
        ("Allies And Organizations", field_values.get("AlliesOrganizations", "")),
        ("Appearance", field_values.get("Appearance", "")),
        ("Additional Notes", "\n\n".join(
            part for part in (field_values.get("AdditionalNotes1", ""), field_values.get("AdditionalNotes2", "")) if part
        )),
        ("Backstory", field_values.get("Backstory", "")),
    ]
    lines: list[str] = []
    for title, body in sections:
        lines.append(f"### {title}")
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _build_spellcasting_section(field_values: dict[str, str]) -> str:
    summary_table = _render_markdown_table(
        ["Field", "Value"],
        [
            ["Spellcasting Class", field_values.get("spellCastingClass0", "")],
            ["Spellcasting Ability", field_values.get("spellCastingAbility0", "")],
            ["Spell Save DC", field_values.get("spellSaveDC0", "")],
            ["Spell Attack Bonus", field_values.get("spellAtkBonus0", "")],
        ],
    )
    spell_rows: list[list[str]] = []
    for index in range(50):
        name = field_values.get(f"SpellName{index}", "")
        if not name:
            continue
        spell_rows.append(
            [
                name,
                field_values.get(f"Prepared{index}", ""),
                field_values.get(f"SaveHit{index}", ""),
                field_values.get(f"CastingTime{index}", ""),
                field_values.get(f"Range{index}", ""),
                field_values.get(f"Duration{index}", ""),
                field_values.get(f"Components{index}", ""),
                field_values.get(f"Source{index}", ""),
                field_values.get(f"SpellSource{index}", ""),
            ]
        )
    parts = [summary_table, "", "### Slots", "", "### Spells"]
    if spell_rows:
        parts.append(
            _render_markdown_table(
                ["Spell", "Mark", "Save/Hit", "Time", "Range", "Duration", "Components", "Source", "Reference"],
                spell_rows,
            )
        )
    return "\n".join(parts).strip()


def _build_equipment_section(field_values: dict[str, str]) -> str:
    rows: list[list[str]] = []
    for index in range(50):
        name = field_values.get(f"Eq Name{index}", "")
        if not name:
            continue
        rows.append(
            [
                name,
                field_values.get(f"Eq Qty{index}", ""),
                field_values.get(f"Eq Weight{index}", ""),
            ]
        )
    return _render_markdown_table(["Item", "Qty", "Weight"], rows)


def build_pdf_character_markdown(field_values: dict[str, str]) -> str:
    sections = [
        ("Sheet Summary", _build_sheet_summary_section(field_values)),
        ("Defenses And Core Stats", _build_core_stats_section(field_values)),
        ("Ability Scores", _build_ability_scores_section(field_values)),
        ("Skills", _build_skills_section(field_values)),
        ("Proficiencies And Languages", _build_proficiencies_section(field_values)),
        ("Attacks And Cantrips", _build_attacks_section(field_values)),
        ("Features And Traits", _build_features_section(field_values)),
        ("Actions", _build_actions_section(field_values)),
        ("Personality And Story", _build_personality_section(field_values)),
        ("Spellcasting", _build_spellcasting_section(field_values)),
        ("Equipment", _build_equipment_section(field_values)),
    ]
    lines: list[str] = []
    for title, body in sections:
        lines.append(f"## {title}")
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _preferred_item_aliases(name: str) -> list[str]:
    aliases = [name]
    if "," in name:
        parts = [part.strip() for part in name.split(",", 1)]
        if len(parts) == 2 and all(parts):
            aliases.append(f"{parts[1]} {parts[0]}")
    alias_map = {
        "Chain Mail": "Chain Mail Armor",
        "Crossbow, Light": "Light Crossbow",
        "Crossbow Bolts": "Crossbow Bolts (20)",
        "Rope, Hempen (50 feet)": "Hempen Rope (50 feet)",
    }
    mapped = alias_map.get(name, "")
    if mapped:
        aliases.append(mapped)
    return [alias for alias in aliases if alias]


def _search_candidates(
    systems_service: SystemsService,
    campaign_slug: str,
    *,
    query: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    return systems_service.search_entries_for_campaign(
        campaign_slug,
        query=query,
        entry_type=entry_type,
        limit=100,
    )


def _entry_sort_key(entry: SystemsEntryRecord) -> tuple[int, str, str]:
    return (MATCH_TYPE_ORDER.get(entry.entry_type, 999), entry.title.lower(), entry.source_id)


def _score_match(
    entry: SystemsEntryRecord,
    *,
    target_name: str,
    class_name: str = "",
    subclass_name: str = "",
    alias_query: str = "",
) -> int:
    score = 0
    target_normalized = normalize_lookup(target_name)
    entry_normalized = normalize_lookup(entry.title)
    alias_normalized = normalize_lookup(alias_query) if alias_query else target_normalized
    if entry_normalized == target_normalized:
        score += 100
    elif alias_normalized and entry_normalized == alias_normalized:
        score += 92
    elif target_normalized and target_normalized in entry_normalized:
        score += 60
    elif alias_normalized and alias_normalized in entry_normalized:
        score += 54

    metadata = dict(entry.metadata or {})
    entry_class_name = str(metadata.get("class_name") or "")
    entry_subclass_name = str(metadata.get("subclass_name") or "")
    if class_name and normalize_lookup(entry_class_name) == normalize_lookup(class_name):
        score += 25
    if subclass_name and normalize_lookup(entry_subclass_name) == normalize_lookup(subclass_name):
        score += 25
    if entry.source_id == "PHB":
        score += 3
    return score


def _pick_best_match(
    entries: list[SystemsEntryRecord],
    *,
    target_name: str,
    class_name: str = "",
    subclass_name: str = "",
    alias_query: str = "",
) -> tuple[SystemsEntryRecord | None, list[SystemsEntryRecord]]:
    ranked = sorted(
        entries,
        key=lambda entry: (
            -_score_match(
                entry,
                target_name=target_name,
                class_name=class_name,
                subclass_name=subclass_name,
                alias_query=alias_query,
            ),
            _entry_sort_key(entry),
        ),
    )
    if not ranked:
        return None, []
    top = ranked[0]
    top_score = _score_match(
        top,
        target_name=target_name,
        class_name=class_name,
        subclass_name=subclass_name,
        alias_query=alias_query,
    )
    contenders = [
        entry
        for entry in ranked
        if _score_match(
            entry,
            target_name=target_name,
            class_name=class_name,
            subclass_name=subclass_name,
            alias_query=alias_query,
        )
        == top_score
    ]
    if top_score < 80 and len(contenders) != 1:
        return None, ranked[:5]
    if top_score < 60:
        return None, ranked[:5]
    return top, ranked[:5]


def _serialize_match(
    entry: SystemsEntryRecord,
    *,
    strategy: str,
    query: str,
) -> dict[str, Any]:
    return {
        "status": "matched",
        "strategy": strategy,
        "query": query,
        "entry_key": entry.entry_key,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "slug": entry.slug,
        "source_id": entry.source_id,
    }


def _serialize_candidates(entries: list[SystemsEntryRecord]) -> list[dict[str, str]]:
    return [
        {
            "title": entry.title,
            "entry_type": entry.entry_type,
            "source_id": entry.source_id,
            "entry_key": entry.entry_key,
        }
        for entry in entries
    ]


def _resolve_named_entry(
    systems_service: SystemsService,
    campaign_slug: str,
    *,
    target_name: str,
    entry_types: list[str],
    class_name: str = "",
    subclass_name: str = "",
    aliases: list[str] | None = None,
    require_exact_title: bool = False,
) -> dict[str, Any]:
    queries = [target_name]
    if aliases:
        queries.extend(alias for alias in aliases if alias and alias not in queries)
    best_candidates: list[SystemsEntryRecord] = []
    best_query = target_name
    for query in queries:
        entries: list[SystemsEntryRecord] = []
        for entry_type in entry_types:
            entries.extend(_search_candidates(systems_service, campaign_slug, query=query, entry_type=entry_type))
        if not entries:
            continue
        best, candidates = _pick_best_match(
            entries,
            target_name=target_name,
            class_name=class_name,
            subclass_name=subclass_name,
            alias_query=query,
        )
        if best is not None:
            acceptable_titles = {normalize_lookup(value) for value in queries if value}
            if require_exact_title and normalize_lookup(best.title) not in acceptable_titles:
                if candidates and not best_candidates:
                    best_candidates = candidates
                    best_query = query
                continue
            strategy = "exact" if normalize_lookup(best.title) == normalize_lookup(target_name) else "alias"
            return _serialize_match(best, strategy=strategy, query=query)
        if candidates and not best_candidates:
            best_candidates = candidates
            best_query = query
    return {
        "status": "unresolved",
        "query": best_query,
        "candidates": _serialize_candidates(best_candidates),
    }


def _feature_name_aliases(name: str) -> list[str]:
    aliases: list[str] = []
    if ":" in name:
        prefix = name.split(":", 1)[0].strip()
        suffix = name.rsplit(":", 1)[1].strip()
        for alias in (suffix, prefix):
            if alias and alias not in aliases:
                aliases.append(alias)
    return aliases


def _infer_subclass_name(
    systems_service: SystemsService,
    campaign_slug: str,
    definition: CharacterDefinition,
    *,
    class_name: str,
) -> str:
    for feature in list(definition.features or []):
        name = str(feature.get("name") or "").strip()
        if not name or name in NON_LINKABLE_FEATURE_TITLES:
            continue
        match = _resolve_named_entry(
            systems_service,
            campaign_slug,
            target_name=name,
            entry_types=["subclass"],
            class_name=class_name,
            require_exact_title=True,
        )
        if match.get("status") == "matched":
            return str(match.get("title") or "").strip()
    return ""


def resolve_definition_systems_links(
    systems_service: SystemsService,
    campaign_slug: str,
    definition: CharacterDefinition,
) -> dict[str, Any]:
    classes = list(definition.profile.get("classes") or [])
    class_name = str(classes[0].get("class_name") or "") if classes else ""
    subclass_name = str(classes[0].get("subclass_name") or "") if classes else ""
    if not subclass_name and class_name:
        subclass_name = _infer_subclass_name(
            systems_service,
            campaign_slug,
            definition,
            class_name=class_name,
        )
    profile_links = {
        "class": _resolve_named_entry(
            systems_service,
            campaign_slug,
            target_name=class_name,
            entry_types=["class"],
        )
        if class_name
        else {"status": "unresolved", "query": "", "candidates": []},
        "subclass": _resolve_named_entry(
            systems_service,
            campaign_slug,
            target_name=subclass_name,
            entry_types=["subclass"],
            class_name=class_name,
        )
        if subclass_name
        else {"status": "unresolved", "query": "", "candidates": []},
        "species": _resolve_named_entry(
            systems_service,
            campaign_slug,
            target_name=str(definition.profile.get("species") or ""),
            entry_types=["race"],
            aliases=[str(definition.profile.get("species") or "").removeprefix("Variant ").strip()],
        )
        if definition.profile.get("species")
        else {"status": "unresolved", "query": "", "candidates": []},
        "background": _resolve_named_entry(
            systems_service,
            campaign_slug,
            target_name=str(definition.profile.get("background") or ""),
            entry_types=["background"],
        )
        if definition.profile.get("background")
        else {"status": "unresolved", "query": "", "candidates": []},
    }

    feature_links: list[dict[str, Any]] = []
    for feature in list(definition.features or []):
        name = str(feature.get("name") or "").strip()
        if not name:
            continue
        category = str(feature.get("category") or "").strip()
        if category == "feat":
            match = _resolve_named_entry(
                systems_service,
                campaign_slug,
                target_name=name,
                entry_types=["feat"],
                require_exact_title=True,
            )
        elif category == "species_trait":
            match = {"status": "unresolved", "query": name, "reason": "no-standalone-racefeature-entry"}
        else:
            if name in NON_LINKABLE_FEATURE_TITLES:
                match = {"status": "unresolved", "query": name, "reason": "generic-sheet-row"}
            elif TRACKER_LINE_PATTERN.search(name):
                match = {"status": "unresolved", "query": name, "reason": "tracker-or-action-line"}
            else:
                entry_types = ["classfeature", "subclassfeature", "optionalfeature", "subclass", "action"]
                if name == subclass_name:
                    entry_types = ["subclass"]
                match = _resolve_named_entry(
                    systems_service,
                    campaign_slug,
                    target_name=name,
                    entry_types=entry_types,
                    class_name=class_name,
                    subclass_name=subclass_name,
                    aliases=_feature_name_aliases(name),
                )
        feature_links.append(
            {
                "name": name,
                "category": category,
                "source": str(feature.get("source") or "").strip(),
                "match": match,
            }
        )

    attack_links = [
        {
            "name": str(attack.get("name") or ""),
            "category": str(attack.get("category") or ""),
            "match": _resolve_named_entry(
                systems_service,
                campaign_slug,
                target_name=str(attack.get("name") or ""),
                entry_types=["item", "action"],
                aliases=_preferred_item_aliases(str(attack.get("name") or "")),
                require_exact_title=True,
            ),
        }
        for attack in list(definition.attacks or [])
        if str(attack.get("name") or "").strip()
    ]

    equipment_links = [
        {
            "name": str(item.get("name") or ""),
            "match": _resolve_named_entry(
                systems_service,
                campaign_slug,
                target_name=str(item.get("name") or ""),
                entry_types=["item"],
                aliases=_preferred_item_aliases(str(item.get("name") or "")),
                require_exact_title=True,
            ),
        }
        for item in list(definition.equipment_catalog or [])
        if str(item.get("name") or "").strip()
    ]

    spell_links = [
        {
            "name": str(spell.get("name") or ""),
            "match": _resolve_named_entry(
                systems_service,
                campaign_slug,
                target_name=str(spell.get("name") or ""),
                entry_types=["spell"],
                require_exact_title=True,
            ),
        }
        for spell in list((definition.spellcasting or {}).get("spells") or [])
        if str(spell.get("name") or "").strip()
    ]

    return {
        "profile": profile_links,
        "features": feature_links,
        "attacks": attack_links,
        "equipment": equipment_links,
        "spells": spell_links,
    }


def _summarize_match_block(entries: list[dict[str, Any]]) -> tuple[int, int]:
    matched = sum(1 for entry in entries if dict(entry.get("match") or {}).get("status") == "matched")
    unresolved = len(entries) - matched
    return matched, unresolved


def render_systems_links_report(
    definition: CharacterDefinition,
    links: dict[str, Any],
) -> str:
    profile = dict(links.get("profile") or {})
    feature_links = list(links.get("features") or [])
    attack_links = list(links.get("attacks") or [])
    equipment_links = list(links.get("equipment") or [])
    spell_links = list(links.get("spells") or [])

    feature_matched, feature_unresolved = _summarize_match_block(feature_links)
    attack_matched, attack_unresolved = _summarize_match_block(attack_links)
    equipment_matched, equipment_unresolved = _summarize_match_block(equipment_links)
    spell_matched, spell_unresolved = _summarize_match_block(spell_links)

    lines = [
        f"# {definition.name} PDF Import Pilot",
        "",
        "## Summary",
        f"- Class: {profile.get('class', {}).get('status', 'unresolved')}",
        f"- Subclass: {profile.get('subclass', {}).get('status', 'unresolved')}",
        f"- Species: {profile.get('species', {}).get('status', 'unresolved')}",
        f"- Background: {profile.get('background', {}).get('status', 'unresolved')}",
        f"- Features: {feature_matched} matched, {feature_unresolved} unresolved",
        f"- Attacks: {attack_matched} matched, {attack_unresolved} unresolved",
        f"- Equipment: {equipment_matched} matched, {equipment_unresolved} unresolved",
        f"- Spells: {spell_matched} matched, {spell_unresolved} unresolved",
        "",
        "## Profile Links",
    ]
    for label in ("class", "subclass", "species", "background"):
        payload = dict(profile.get(label) or {})
        if payload.get("status") == "matched":
            lines.append(
                f"- {label.title()}: {payload.get('title')} ({payload.get('entry_type')} {payload.get('source_id')})"
            )
        else:
            lines.append(f"- {label.title()}: unresolved")

    def _append_block(title: str, entries: list[dict[str, Any]]) -> None:
        lines.extend(["", f"## {title}"])
        if not entries:
            lines.append("- None")
            return
        for entry in entries:
            match = dict(entry.get("match") or {})
            name = str(entry.get("name") or "")
            if match.get("status") == "matched":
                lines.append(
                    f"- {name}: {match.get('title')} ({match.get('entry_type')} {match.get('source_id')})"
                )
                continue
            reason = match.get("reason")
            if reason:
                lines.append(f"- {name}: unresolved ({reason})")
            elif match.get("candidates"):
                candidates = ", ".join(
                    f"{candidate.get('title')} [{candidate.get('entry_type')}]"
                    for candidate in list(match.get("candidates") or [])[:3]
                )
                lines.append(f"- {name}: unresolved; candidates: {candidates}")
            else:
                lines.append(f"- {name}: unresolved")

    _append_block("Feature Links", feature_links)
    _append_block("Attack Links", attack_links)
    _append_block("Equipment Links", equipment_links)
    _append_block("Spell Links", spell_links)
    return "\n".join(lines).strip() + "\n"


def _systems_ref_from_match(match: dict[str, Any]) -> dict[str, Any] | None:
    if str(match.get("status") or "") != "matched":
        return None
    slug = str(match.get("slug") or "").strip()
    if not slug:
        return None
    return {
        "entry_key": str(match.get("entry_key") or "").strip(),
        "entry_type": str(match.get("entry_type") or "").strip(),
        "title": str(match.get("title") or "").strip(),
        "slug": slug,
        "source_id": str(match.get("source_id") or "").strip(),
    }


def apply_systems_links_to_definition(
    definition: CharacterDefinition,
    systems_links: dict[str, Any],
) -> CharacterDefinition:
    linked_definition = CharacterDefinition.from_dict(copy.deepcopy(definition.to_dict()))
    profile_links = dict(systems_links.get("profile") or {})
    profile = dict(linked_definition.profile or {})
    classes = list(profile.get("classes") or [])

    class_ref = _systems_ref_from_match(dict(profile_links.get("class") or {}))
    subclass_ref = _systems_ref_from_match(dict(profile_links.get("subclass") or {}))
    species_ref = _systems_ref_from_match(dict(profile_links.get("species") or {}))
    background_ref = _systems_ref_from_match(dict(profile_links.get("background") or {}))
    if class_ref is not None:
        profile["class_ref"] = class_ref
    if subclass_ref is not None:
        profile["subclass_ref"] = subclass_ref
        if classes:
            first_class = dict(classes[0] or {})
            if not str(first_class.get("subclass_name") or "").strip():
                first_class["subclass_name"] = subclass_ref.get("title", "")
            first_class["subclass_ref"] = subclass_ref
            classes[0] = first_class
    if class_ref is not None and classes:
        first_class = dict(classes[0] or {})
        first_class["systems_ref"] = class_ref
        classes[0] = first_class
    if species_ref is not None:
        profile["species_ref"] = species_ref
    if background_ref is not None:
        profile["background_ref"] = background_ref
    if classes:
        profile["classes"] = classes
    linked_definition.profile = profile

    feature_links = list(systems_links.get("features") or [])
    linked_features: list[dict[str, Any]] = []
    for feature, link in zip(list(linked_definition.features or []), feature_links):
        feature_payload = dict(feature or {})
        systems_ref = _systems_ref_from_match(dict(link.get("match") or {}))
        if systems_ref is not None:
            feature_payload["systems_ref"] = systems_ref
        linked_features.append(feature_payload)
    if len(linked_features) == len(linked_definition.features):
        linked_definition.features = linked_features

    attack_links = list(systems_links.get("attacks") or [])
    linked_attacks: list[dict[str, Any]] = []
    for attack, link in zip(list(linked_definition.attacks or []), attack_links):
        attack_payload = dict(attack or {})
        systems_ref = _systems_ref_from_match(dict(link.get("match") or {}))
        if systems_ref is not None:
            attack_payload["systems_ref"] = systems_ref
        linked_attacks.append(attack_payload)
    if len(linked_attacks) == len(linked_definition.attacks):
        linked_definition.attacks = linked_attacks

    equipment_links = list(systems_links.get("equipment") or [])
    linked_equipment: list[dict[str, Any]] = []
    for item, link in zip(list(linked_definition.equipment_catalog or []), equipment_links):
        item_payload = dict(item or {})
        systems_ref = _systems_ref_from_match(dict(link.get("match") or {}))
        if systems_ref is not None:
            item_payload["systems_ref"] = systems_ref
        linked_equipment.append(item_payload)
    if len(linked_equipment) == len(linked_definition.equipment_catalog):
        linked_definition.equipment_catalog = linked_equipment

    spellcasting = dict(linked_definition.spellcasting or {})
    spell_links = list(systems_links.get("spells") or [])
    linked_spells: list[dict[str, Any]] = []
    for spell, link in zip(list(spellcasting.get("spells") or []), spell_links):
        spell_payload = dict(spell or {})
        systems_ref = _systems_ref_from_match(dict(link.get("match") or {}))
        if systems_ref is not None:
            spell_payload["systems_ref"] = systems_ref
        linked_spells.append(spell_payload)
    if len(linked_spells) == len(list(spellcasting.get("spells") or [])):
        spellcasting["spells"] = linked_spells
    linked_definition.spellcasting = spellcasting

    return linked_definition


def build_pdf_character_artifacts(
    campaign_slug: str,
    pdf_path: Path,
    *,
    character_slug: str | None = None,
) -> CharacterPdfArtifacts:
    from .app import create_app
    from .db import init_database

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    field_values = extract_pdf_annotation_fields(pdf_path)
    synthetic_markdown = build_pdf_character_markdown(field_values)

    app = create_app()
    with app.app_context():
        init_database()
        definition, import_metadata = parse_character_sheet_text(
            campaign_slug,
            synthetic_markdown,
            source_path=pdf_path,
            source_type="pdf_character_sheet_annotations",
            imported_from=pdf_path.name,
            parser_version=PDF_PARSER_VERSION,
            character_slug=character_slug,
        )
        systems_service: SystemsService = app.extensions["systems_service"]
        systems_links = resolve_definition_systems_links(systems_service, campaign_slug, definition)
        linked_definition = apply_systems_links_to_definition(definition, systems_links)

    return CharacterPdfArtifacts(
        field_values=field_values,
        synthetic_markdown=synthetic_markdown,
        definition=linked_definition,
        import_metadata=import_metadata,
        systems_links=systems_links,
    )


def import_pdf_character(
    project_root: Path,
    campaign_slug: str,
    pdf_path: Path,
    *,
    character_slug: str | None = None,
) -> CharacterPdfImportResult:
    from .app import create_app
    from .db import init_database

    artifacts = build_pdf_character_artifacts(
        campaign_slug,
        pdf_path,
        character_slug=character_slug,
    )

    app = create_app()
    with app.app_context():
        init_database()
        state_store: CharacterStateStore = app.extensions["character_state_store"]
        campaigns_dir: Path = app.config["CAMPAIGNS_DIR"]
        config = load_campaign_character_config(campaigns_dir, campaign_slug)
        character_dir = config.characters_dir / artifacts.definition.character_slug
        definition = preserve_existing_character_overrides(artifacts.definition, character_dir)
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", artifacts.import_metadata.to_dict())
        state_result = initialize_or_reconcile_imported_state(state_store, definition)
        return CharacterPdfImportResult(
            definition=definition,
            import_metadata=artifacts.import_metadata,
            character_dir=character_dir,
            state_created=state_result.created,
        )


def run_pdf_pilot(
    project_root: Path,
    campaign_slug: str,
    pdf_path: Path,
    *,
    character_slug: str | None = None,
    output_dir: Path | None = None,
) -> CharacterPdfPilotResult:
    artifacts = build_pdf_character_artifacts(
        campaign_slug,
        pdf_path,
        character_slug=character_slug,
    )

    resolved_output_dir = output_dir or (project_root / ".local" / "character_pdf_pilots" / artifacts.definition.character_slug)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    fields_path = resolved_output_dir / "annotation_fields.yaml"
    synthetic_markdown_path = resolved_output_dir / "synthetic_sheet.md"
    definition_path = resolved_output_dir / "definition.draft.yaml"
    systems_links_path = resolved_output_dir / "systems_links.yaml"
    report_path = resolved_output_dir / "pilot_report.md"

    write_yaml(fields_path, artifacts.field_values)
    synthetic_markdown_path.write_text(artifacts.synthetic_markdown, encoding="utf-8")
    write_yaml(definition_path, artifacts.definition.to_dict())
    write_yaml(systems_links_path, artifacts.systems_links)
    report_path.write_text(
        render_systems_links_report(artifacts.definition, artifacts.systems_links),
        encoding="utf-8",
    )

    return CharacterPdfPilotResult(
        definition=artifacts.definition,
        import_metadata=artifacts.import_metadata,
        output_dir=resolved_output_dir,
        fields_path=fields_path,
        synthetic_markdown_path=synthetic_markdown_path,
        definition_path=definition_path,
        systems_links_path=systems_links_path,
        report_path=report_path,
    )
