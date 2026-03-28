from __future__ import annotations

from datetime import datetime, timezone

from player_wiki.character_importer import parse_character_sheet_text
from player_wiki.character_pdf_importer import build_pdf_character_markdown, resolve_definition_systems_links
from player_wiki.systems_models import SystemsEntryRecord


def _sample_pdf_fields() -> dict[str, str]:
    return {
        "CharacterName": "Tobin Slate",
        "CLASS  LEVEL": "Fighter 5",
        "RACE": "Variant Human",
        "BACKGROUND": "Gladiator",
        "EXPERIENCE POINTS": "(Milestone)",
        "ALIGNMENT": "Neutral",
        "SIZE": "Medium",
        "STR": "18",
        "STRmod": "+4",
        "ST Strength": "+7",
        "DEX": "14",
        "DEXmod": "+2",
        "ST Dexterity": "+2",
        "CON": "15",
        "CONmod": "+2",
        "ST Constitution": "+5",
        "INT": "9",
        "INTmod": "-1",
        "ST Intelligence": "-1",
        "WIS": "11",
        "WISmod": "+0",
        "ST Wisdom": "+0",
        "CHA": "14",
        "CHamod": "+2",
        "ST Charisma": "+2",
        "AcrobaticsProf": "P",
        "Acrobatics": "+5",
        "AthleticsProf": "P",
        "Athletics": "+7",
        "PerceptionProf": "P",
        "Perception": "+3",
        "PerformanceProf": "P",
        "Performance": "+5",
        "Stealth": "+2",
        "Passive1": "13",
        "Passive2": "10",
        "Passive3": "9",
        "Init": "+2",
        "AC": "16",
        "ProfBonus": "+3",
        "Speed": "30 ft. (Walking)",
        "MaxHP": "54",
        "ProficienciesLang": (
            "=== ARMOR ===\nHeavy Armor, Light Armor, Medium Armor, Shields\n\n"
            "=== WEAPONS ===\nMartial Weapons, Simple Weapons\n\n"
            "=== TOOLS ===\nDisguise Kit, Zulkoon\n\n"
            "=== LANGUAGES ===\nCommon, Gnomish"
        ),
        "Wpn Name": "Crossbow, Light",
        "Wpn1 AtkBonus": "+5",
        "Wpn1 Damage": "1d8+2 Piercing",
        "Wpn Notes 1": "Simple, Ammunition, Loading, Range, Two-Handed, Slow, Range (80/320)",
        "FeaturesTraits1": (
            "=== FIGHTER FEATURES ===\n\n"
            "* Proficiencies â€¢ PHB 71\n\n"
            "* Fighting Style â€¢ PHB 72\n"
            "You adopt a fighting style specialty.\n\n"
            "| Two-Weapon Fighting â€¢ PHB\n"
            "When you engage in two-weapon fighting, you can add your ability modifier to the damage of the second attack.\n\n"
            "* Martial Archetype â€¢ PHB 72\n\n"
            "| Psi Warrior\n\n"
            "* Psionic Power â€¢ TCoE 43\n"
            "You have 6 Psionic Energy dice (1d8), and they fuel various psionic powers you have.\n\n"
            "* Ability Score Improvement â€¢ PHB 72\n\n"
            "* Extra Attack â€¢ PHB 72\n"
            "You can attack twice whenever you take the Attack action on your turn.\n\n"
            "=== FEATS ===\n\n"
            "* Sentinel â€¢ PHB 169\n\n"
            "* Dual Wielder â€¢ PHB 165\n"
        ),
        "Actions1": (
            "=== ACTIONS ===\n"
            "Standard Actions\n"
            "Attack, Dash\n\n"
            "=== BONUS ACTIONS ===\n"
            "Second Wind â€¢ 1 / Short Rest\n"
        ),
        "Eq Name0": "Longsword",
        "Eq Qty0": "1",
        "Eq Weight0": "3 lb.",
        "Eq Name1": "Backpack",
        "Eq Qty1": "1",
        "Eq Weight1": "5 lb.",
        "Eq Name2": "Clothes, Costume",
        "Eq Qty2": "1",
        "Eq Weight2": "4 lb.",
        "Eq Name3": "Bedroll",
        "Eq Qty3": "1",
        "Eq Weight3": "7 lb.",
        "Eq Name4": "Rations (1 day)",
        "Eq Qty4": "10",
        "Eq Weight4": "20 lb.",
        "Eq Name5": "Rope, Hempen (50 feet)",
        "Eq Qty5": "1",
        "Eq Weight5": "10 lb.",
        "Eq Name6": "Tinderbox",
        "Eq Qty6": "1",
        "Eq Weight6": "1 lb.",
        "Eq Name7": "Torch",
        "Eq Qty7": "10",
        "Eq Weight7": "10 lb.",
        "Eq Name8": "Waterskin",
        "Eq Qty8": "1",
        "Eq Weight8": "5 lb.",
    }


def _sample_system_entry(
    *,
    entry_key: str,
    entry_type: str,
    title: str,
    source_id: str,
    metadata: dict | None = None,
) -> SystemsEntryRecord:
    now = datetime.now(timezone.utc)
    return SystemsEntryRecord(
        id=1,
        library_slug="DND-5E",
        source_id=source_id,
        entry_key=entry_key,
        entry_type=entry_type,
        slug=f"{source_id.lower()}-{entry_type}-{title.lower().replace(' ', '-')}",
        title=title,
        source_page="",
        source_path="",
        search_text=title.lower(),
        player_safe_default=True,
        dm_heavy=False,
        metadata=metadata or {},
        body={},
        rendered_html="",
        created_at=now,
        updated_at=now,
    )


class _FakeSystemsService:
    def __init__(self, entries: list[SystemsEntryRecord]) -> None:
        self.entries = entries

    def search_entries_for_campaign(self, campaign_slug: str, *, query: str, entry_type: str | None = None, limit: int = 100):
        del campaign_slug
        normalized_query = "".join(ch for ch in query.lower() if ch.isalnum())
        matches = []
        for entry in self.entries:
            if entry_type and entry.entry_type != entry_type:
                continue
            normalized_title = "".join(ch for ch in entry.title.lower() if ch.isalnum())
            if normalized_query in normalized_title or normalized_title in normalized_query:
                matches.append(entry)
        return matches[:limit]


def test_build_pdf_character_markdown_parses_into_character_definition():
    markdown = build_pdf_character_markdown(_sample_pdf_fields())
    definition, import_metadata = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Tobin.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Tobin.pdf",
        parser_version="test",
    )

    assert definition.name == "Tobin Slate"
    assert definition.profile["class_level_text"] == "Fighter 5"
    assert definition.profile["species"] == "Variant Human"
    assert definition.stats["ability_scores"]["dexterity"]["modifier"] == 2
    assert next(skill for skill in definition.skills if skill["name"] == "Stealth")["bonus"] == 2
    assert definition.attacks[0]["name"] == "Crossbow, Light"
    assert any(feature["name"].startswith("Fighting Style") for feature in definition.features)
    assert any(feature["name"] == "Psi Warrior" for feature in definition.features)
    assert any(item["name"] == "Backpack" for item in definition.equipment_catalog)
    assert import_metadata.import_status == "clean"


def test_resolve_definition_systems_links_prefers_contextual_matches():
    markdown = build_pdf_character_markdown(_sample_pdf_fields())
    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Tobin.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Tobin.pdf",
        parser_version="test",
    )
    systems_service = _FakeSystemsService(
        [
            _sample_system_entry(entry_key="class-fighter", entry_type="class", title="Fighter", source_id="PHB"),
            _sample_system_entry(
                entry_key="subclass-psi-warrior",
                entry_type="subclass",
                title="Psi Warrior",
                source_id="TCE",
                metadata={"class_name": "Fighter"},
            ),
            _sample_system_entry(entry_key="race-human", entry_type="race", title="Human", source_id="PHB"),
            _sample_system_entry(
                entry_key="bg-gladiator",
                entry_type="background",
                title="Variant Entertainer (Gladiator)",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="cf-fighting-style",
                entry_type="classfeature",
                title="Fighting Style",
                source_id="PHB",
                metadata={"class_name": "Fighter"},
            ),
            _sample_system_entry(
                entry_key="of-two-weapon-fighting",
                entry_type="optionalfeature",
                title="Two-Weapon Fighting",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="cf-martial-archetype",
                entry_type="classfeature",
                title="Martial Archetype",
                source_id="PHB",
                metadata={"class_name": "Fighter"},
            ),
            _sample_system_entry(
                entry_key="scf-psionic-power",
                entry_type="subclassfeature",
                title="Psionic Power",
                source_id="TCE",
                metadata={"class_name": "Fighter", "subclass_name": "Psi Warrior"},
            ),
            _sample_system_entry(
                entry_key="cf-ability-score-improvement-fighter",
                entry_type="classfeature",
                title="Ability Score Improvement",
                source_id="PHB",
                metadata={"class_name": "Fighter"},
            ),
            _sample_system_entry(
                entry_key="cf-ability-score-improvement-barbarian",
                entry_type="classfeature",
                title="Ability Score Improvement",
                source_id="PHB",
                metadata={"class_name": "Barbarian"},
            ),
            _sample_system_entry(
                entry_key="cf-extra-attack-fighter",
                entry_type="classfeature",
                title="Extra Attack",
                source_id="PHB",
                metadata={"class_name": "Fighter"},
            ),
            _sample_system_entry(entry_key="feat-sentinel", entry_type="feat", title="Sentinel", source_id="PHB"),
            _sample_system_entry(
                entry_key="feat-dual-wielder",
                entry_type="feat",
                title="Dual Wielder",
                source_id="PHB",
            ),
            _sample_system_entry(entry_key="item-backpack", entry_type="item", title="Backpack", source_id="PHB"),
            _sample_system_entry(
                entry_key="item-costume-clothes",
                entry_type="item",
                title="Costume Clothes",
                source_id="PHB",
            ),
            _sample_system_entry(entry_key="item-bedroll", entry_type="item", title="Bedroll", source_id="PHB"),
            _sample_system_entry(
                entry_key="item-rations",
                entry_type="item",
                title="Rations (1 day)",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-rope",
                entry_type="item",
                title="Hempen Rope (50 feet)",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-tinderbox",
                entry_type="item",
                title="Tinderbox",
                source_id="PHB",
            ),
            _sample_system_entry(entry_key="item-torch", entry_type="item", title="Torch", source_id="PHB"),
            _sample_system_entry(
                entry_key="item-waterskin",
                entry_type="item",
                title="Waterskin",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-longsword-fancy",
                entry_type="item",
                title="Silver-plated steel longsword with jet set in hilt",
                source_id="DMG",
            ),
        ]
    )

    links = resolve_definition_systems_links(systems_service, "linden-pass", definition)

    assert links["profile"]["class"]["title"] == "Fighter"
    assert links["profile"]["subclass"]["title"] == "Psi Warrior"
    assert links["profile"]["background"]["title"] == "Variant Entertainer (Gladiator)"

    def _feature_starting_with(prefix: str):
        return next(entry for entry in links["features"] if entry["name"].startswith(prefix))

    equipment_by_name = {entry["name"]: entry for entry in links["equipment"]}

    fighting_style = _feature_starting_with("Fighting Style")
    two_weapon = _feature_starting_with("Two-Weapon Fighting")
    psi_warrior = _feature_starting_with("Psi Warrior")
    ability_score_improvement = _feature_starting_with("Ability Score Improvement")
    proficiencies = _feature_starting_with("Proficiencies")

    assert fighting_style["match"]["status"] == "unresolved"
    assert fighting_style["match"]["candidates"][0]["entry_type"] == "classfeature"
    assert two_weapon["match"]["status"] == "unresolved"
    assert two_weapon["match"]["candidates"][0]["entry_type"] == "optionalfeature"
    assert psi_warrior["match"]["entry_type"] == "subclass"
    assert ability_score_improvement["match"]["status"] == "unresolved"
    assert ability_score_improvement["match"]["candidates"][0]["entry_key"] == "cf-ability-score-improvement-fighter"
    assert proficiencies["match"]["status"] == "unresolved"
    assert equipment_by_name["Backpack"]["match"]["title"] == "Backpack"
    assert equipment_by_name["Longsword"]["match"]["status"] == "unresolved"


