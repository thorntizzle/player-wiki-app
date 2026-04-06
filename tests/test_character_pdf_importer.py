from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml

from player_wiki.app import create_app
from player_wiki.character_builder import supports_native_level_up
from player_wiki.character_importer import (
    converge_imported_definition,
    extract_trackers_from_text,
    import_character,
    parse_character_sheet_text,
)
from player_wiki.character_models import CharacterDefinition
from player_wiki.character_pdf_importer import (
    apply_systems_links_to_definition,
    build_pdf_character_markdown,
    resolve_definition_campaign_page_links,
    resolve_definition_systems_links,
)
from player_wiki.config import Config
from player_wiki.db import init_database
from player_wiki.systems_models import SystemsEntryRecord
from tests.sample_data import build_test_campaigns_dir


def _minimal_imported_definition(
    *,
    profile: dict[str, object] | None = None,
    attacks: list[dict[str, object]] | None = None,
    features: list[dict[str, object]] | None = None,
    spellcasting: dict[str, object] | None = None,
    equipment_catalog: list[dict[str, object]] | None = None,
    resource_templates: list[dict[str, object]] | None = None,
    source_type: str = "markdown_character_sheet",
) -> CharacterDefinition:
    return CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="tobin-slate",
        name="Tobin Slate",
        status="active",
        profile={
            "sheet_name": "Tobin Slate",
            "display_name": "Tobin Slate",
            "class_level_text": "Wizard 3",
            "classes": [{"class_name": "Wizard", "subclass_name": "", "level": 3}],
            "species": "Human",
            "background": "Sage",
            **dict(profile or {}),
        },
        stats={
            "max_hp": 18,
            "armor_class": 12,
            "initiative_bonus": 2,
            "speed": "30 ft.",
            "proficiency_bonus": 2,
            "passive_perception": 12,
            "passive_insight": 11,
            "passive_investigation": 14,
            "ability_scores": {
                "str": {"score": 8, "modifier": -1, "save_bonus": -1},
                "dex": {"score": 14, "modifier": 2, "save_bonus": 2},
                "con": {"score": 12, "modifier": 1, "save_bonus": 1},
                "int": {"score": 16, "modifier": 3, "save_bonus": 5},
                "wis": {"score": 12, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
            },
        },
        skills=[],
        proficiencies={"armor": [], "weapons": [], "tools": [], "languages": ["Common"]},
        attacks=list(attacks or []),
        features=list(features or []),
        spellcasting={
            "spellcasting_class": "Wizard",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 13,
            "spell_attack_bonus": 5,
            "slot_progression": [{"level": 1, "max_slots": 4}],
            "spells": [],
            **dict(spellcasting or {}),
        },
        equipment_catalog=list(equipment_catalog or []),
        reference_notes={"additional_notes_markdown": "", "allies_and_organizations_markdown": "", "custom_sections": []},
        resource_templates=list(resource_templates or []),
        source={
            "source_path": "Tobin.pdf",
            "source_type": source_type,
            "imported_from": "Tobin.pdf",
            "imported_at": "2026-03-31T00:00:00Z",
            "parse_warnings": [],
        },
    )


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
        "Eq Name9": "Chain Mail",
        "Eq Qty9": "1",
        "Eq Weight9": "55 lb.",
        "Eq Name10": "Crossbow Bolts",
        "Eq Qty10": "1",
        "Eq Weight10": "1.5 lb.",
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


def _sample_split_action_markdown() -> str:
    return """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Zigzag Blackscar |
| Class & Level | Fighter 5 |
| Species | Variant Human |
| Background | Gladiator |
| Alignment | Neutral |
| Experience | (Milestone) |
| Size | Medium |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 16 |
| Initiative | +2 |
| Speed | 30 ft. (Walking) |
| Max HP | 54 |
| Proficiency Bonus | +3 |
| Passive Perception | 13 |
| Passive Insight | 10 |
| Passive Investigation | 9 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 18 | +4 | +7 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 15 | +2 | +5 |
| Intelligence | 9 | -1 | -1 |
| Wisdom | 11 | +0 | +0 |
| Charisma | 14 | +2 | +2 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Athletics | +7 | Proficient |

## Proficiencies And Languages
- Armor: Heavy Armor
- Weapons: Martial Weapons
- Tools: Disguise Kit
- Languages: Common

## Attacks And Cantrips
| Attack | Hit | Damage | Notes |
| --- | --- | --- | --- |
| Huron Blade | +8 | 1d8+5 Slashing | Martial |

## Features And Traits
### Fighter Features

- Second Wind - PHB 72
Once per short rest, you can use a bonus action to regain 1d10 + 5 HP.

- 1 / Short Rest - 1 Bonus Action

- Action Surge - PHB 72
You can take one additional action on your turn.

- 1 / Short Rest - Special

- Psionic Power - TCoE 43
You have 6 Psionic Energy dice (1d8), and they fuel various psionic powers you have.

- Psionic Power: Protective Field: 1 Reaction

- Psionic Power: Psionic Energy: 6 / Long Rest - Special

- Psionic Power: Psionic Strike: Special

- Psionic Power: Telekinetic Movement: 1 / Short Rest - 1 Action

- Psionic Power: Recovery: 1 / Short Rest - 1 Bonus Action

### Feats

- Sentinel - PHB 169
When a creature within 5 ft. of you makes an attack against a target other than you, you can use your reaction to make a melee weapon attack against the attacking creature.

- Sentinel Attack: 1 Reaction

## Actions
### Actions
Standard Actions
Attack, Dash

Psionic Power: Telekinetic Movement - 1 / Short Rest
You can move an object or a creature with your mind.

Once you take this action, you can't do so again until you finish a short or long rest.

### Bonus Actions
Psionic Power: Recovery - 1 / Short Rest
As a bonus action, you can regain one expended Psionic Energy die.

Second Wind - 1 / Short Rest
Once per short rest, you can use a bonus action to regain 1d10 + 5 HP.

### Reactions
Psionic Power: Protective Field

## Personality And Story
### Personality Traits

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class |  |
| Spellcasting Ability |  |
| Spell Save DC |  |
| Spell Attack Bonus |  |

### Slots

### Spells

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Backpack | 1 | 5 lb. |
""".strip()


def _sample_spell_reimport_markdown(*spell_rows: str) -> str:
    rendered_rows = "\n".join(spell_rows).strip()
    return f"""
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Mira Salt |
| Class & Level | Wizard 3 |
| Species | Human |
| Background | Sage |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 12 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 18 |
| Proficiency Bonus | +2 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 8 | -1 | -1 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 12 | +1 | +1 |
| Intelligence | 16 | +3 | +5 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 10 | +0 | +0 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Arcana | +5 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Attacks And Cantrips
| Attack | Hit | Damage | Notes |
| --- | --- | --- | --- |

## Features And Traits
### Wizard Features

- Arcane Recovery - PHB 115

## Actions
### Actions
Cast a spell

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class | Wizard |
| Spellcasting Ability | Intelligence |
| Spell Save DC | 13 |
| Spell Attack Bonus | +5 |

### Slots
- 4 Slots

### Spells
| Spell | Mark | Save/Hit | Time | Range | Duration | Components | Source | Reference |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{rendered_rows}

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Backpack | 1 | 5 lb. |
""".strip()


def test_parse_character_sheet_text_merges_split_action_cost_lines_into_features():
    markdown = _sample_split_action_markdown()
    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Zigzag.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Zigzag.pdf",
        parser_version="test",
    )

    features_by_name = {feature["name"]: feature for feature in definition.features}
    feature_names = set(features_by_name)
    resource_ids = {resource["id"] for resource in definition.resource_templates}

    assert "1 / Short Rest - 1 Bonus Action" not in feature_names
    assert "1 / Short Rest - Special" not in feature_names
    assert "Psionic Power: Psionic Energy" not in feature_names
    assert "Sentinel Attack" not in feature_names

    assert features_by_name["Second Wind"]["activation_type"] == "bonus_action"
    assert features_by_name["Second Wind"]["tracker_ref"] == "second-wind"
    assert features_by_name["Action Surge"]["activation_type"] == "special"
    assert features_by_name["Action Surge"]["tracker_ref"] == "action-surge"

    assert features_by_name["Psionic Power"]["tracker_ref"] == "psionic-power-psionic-energy"
    assert features_by_name["Psionic Power: Protective Field"]["activation_type"] == "reaction"
    assert features_by_name["Psionic Power: Psionic Strike"]["activation_type"] == "special"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["activation_type"] == "action"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["tracker_ref"] == "psionic-power-telekinetic-movement"
    assert "move an object or a creature with your mind" in features_by_name["Psionic Power: Telekinetic Movement"]["description_markdown"]
    assert features_by_name["Psionic Power: Recovery"]["activation_type"] == "bonus_action"
    assert features_by_name["Psionic Power: Recovery"]["tracker_ref"] == "psionic-power-recovery"
    assert "regain one expended Psionic Energy die" in features_by_name["Psionic Power: Recovery"]["description_markdown"]

    assert features_by_name["Sentinel"]["activation_type"] == "reaction"
    assert "psionic-power-psionic-energy" in resource_ids
    assert "psionic-power-telekinetic-movement" in resource_ids
    assert "psionic-power-recovery" in resource_ids
    assert "action-surge" in resource_ids
    assert "second-wind" in resource_ids


def test_parse_character_sheet_text_normalizes_modeled_feat_trackers_through_native_helpers():
    markdown = """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Mira Salt |
| Class & Level | Fighter 4 |
| Species | Human |
| Background | Sailor |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 15 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 32 |
| Proficiency Bonus | +2 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 14 | +2 | +4 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 14 | +2 | +4 |
| Intelligence | 10 | +0 | +0 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 8 | -1 | -1 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Athletics | +4 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Features And Traits
### Feats

- Lucky - PHB 167
Fortune seems to tilt your way at the worst possible moment.

## Actions
### Actions
Attack

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class |  |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Backpack | 1 | 5 lb. |
""".strip()

    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Mira.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Mira.pdf",
        parser_version="test",
    )

    lucky = next(feature for feature in definition.features if feature["name"] == "Lucky")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert lucky["tracker_ref"] == "lucky"
    assert resources_by_id["lucky"]["max"] == 3
    assert resources_by_id["lucky"]["reset_on"] == "long_rest"


def test_extract_trackers_from_text_skips_invalid_progress_lines_that_look_like_dates():
    warnings: list[str] = []

    trackers = extract_trackers_from_text(
        "2 Favors from downtime 3/1\nRenown 3/5",
        category="custom_progress",
        display_start=0,
        warnings=warnings,
    )

    assert [tracker["label"] for tracker in trackers] == ["Renown"]
    assert trackers[0]["initial_current"] == 3
    assert trackers[0]["max"] == 5
    assert warnings == [
        "Skipped suspicious progress tracker line '2 Favors from downtime 3/1' because current exceeded max."
    ]


def test_parse_character_sheet_text_keeps_additional_notes_out_of_resource_trackers():
    markdown = """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Flair Sparkmantle |
| Class & Level | Artificer 5 |
| Species | Human |
| Background | Sage |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 16 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 40 |
| Proficiency Bonus | +3 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 10 | +0 | +0 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 14 | +2 | +2 |
| Intelligence | 18 | +4 | +7 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 8 | -1 | -1 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Arcana | +7 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Features And Traits
### Artificer Features

- Infuse Item - TCoE 12
You can imbue mundane objects with certain magical infusions.

## Actions
### Actions
Attack

## Personality And Story
### Additional Notes
Progress on resonance research 40/40
29/50 on making gauntlets paid 400/2000

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class | Artificer |
| Spellcasting Ability | Intelligence |
| Spell Save DC | 15 |
| Spell Attack Bonus | +7 |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Backpack | 1 | 5 lb. |
""".strip()

    definition, import_metadata = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Flair.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Flair.pdf",
        parser_version="test",
    )

    resource_labels = {resource["label"] for resource in definition.resource_templates}

    assert "Progress on resonance research" not in resource_labels
    assert "29/50 on making gauntlets paid" not in resource_labels
    assert "Progress on resonance research 40/40" in definition.reference_notes["additional_notes_markdown"]
    assert "29/50 on making gauntlets paid 400/2000" in definition.reference_notes["additional_notes_markdown"]
    assert import_metadata.warnings == []


def test_parse_character_sheet_text_merges_detached_feat_helper_rows_into_their_parent_feature():
    markdown = """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Glenn Hakewood |
| Class & Level | Sorcerer 5 |
| Species | Human |
| Background | Entertainer |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 14 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 32 |
| Proficiency Bonus | +3 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 8 | -1 | -1 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 14 | +2 | +2 |
| Intelligence | 10 | +0 | +0 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 18 | +4 | +7 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Arcana | +3 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Features And Traits
### Feats
- Inspiring Leader - PHB 167
You can spend 10 minutes inspiring your companions. Choose up to 6 allies (including yourself) that can see or hear and can understand you within 30 ft. Each creature gains 9 temp HP once per short rest.

- 10 Minutes

- Wild Magic Mod •

- Wild Die: 3 / Long Rest

## Actions
### Actions
Attack

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class | Sorcerer |
| Spellcasting Ability | Charisma |
| Spell Save DC | 15 |
| Spell Attack Bonus | +7 |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Component Pouch | 1 | 2 lb. |
""".strip()

    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Glenn.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Glenn.pdf",
        parser_version="test",
    )

    feature_names = [feature["name"] for feature in definition.features]
    inspiring_leader = next(feature for feature in definition.features if feature["name"] == "Inspiring Leader")
    wild_magic = next(feature for feature in definition.features if feature["name"] == "Wild Magic Mod •")

    assert "10 Minutes" not in feature_names
    assert "Wild Die" not in feature_names
    assert inspiring_leader["activation_type"] == "special"
    assert wild_magic["tracker_ref"] == "wild-die"
    assert next(template for template in definition.resource_templates if template["id"] == "wild-die")["label"] == "Wild Die"


def test_parse_character_sheet_text_prefers_sourced_feature_row_over_detached_action_alias():
    markdown = """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Glenn Hakewood |
| Class & Level | Sorcerer 5 |
| Species | Human |
| Background | Entertainer |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 14 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 32 |
| Proficiency Bonus | +3 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 8 | -1 | -1 |
| Dexterity | 14 | +2 | +2 |
| Constitution | 14 | +2 | +2 |
| Intelligence | 10 | +0 | +0 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 18 | +4 | +7 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Arcana | +3 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Features And Traits
### Sorcerer Features
- Quickened Spell - PHB
When you cast a spell that has a casting time of 1 action, you can spend 2 sorcery points to change the casting time to 1 bonus action for this casting.

- Metamagic - Quickened Spell: Special

## Actions
### Special
Metamagic - Quickened Spell
When you cast a spell that has a casting time of 1 action, you can spend 2 sorcery points to change the casting time to 1 bonus action for this casting.

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class | Sorcerer |
| Spellcasting Ability | Charisma |
| Spell Save DC | 15 |
| Spell Attack Bonus | +7 |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Component Pouch | 1 | 2 lb. |
""".strip()

    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Glenn.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Glenn.pdf",
        parser_version="test",
    )

    feature_names = [feature["name"] for feature in definition.features]
    quickened_spell = next(feature for feature in definition.features if feature["name"] == "Quickened Spell")

    assert feature_names.count("Quickened Spell") == 1
    assert "Metamagic - Quickened Spell" not in feature_names
    assert quickened_spell["activation_type"] == "special"


def test_parse_character_sheet_text_normalizes_duplicate_attack_and_equipment_rows():
    markdown = """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Mira Salt |
| Class & Level | Fighter 1 |
| Species | Human |
| Background | Sailor |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 15 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 12 |
| Proficiency Bonus | +2 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 16 | +3 | +5 |
| Dexterity | 12 | +1 | +1 |
| Constitution | 14 | +2 | +4 |
| Intelligence | 10 | +0 | +0 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 8 | -1 | -1 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Athletics | +5 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Features And Traits
### Fighter Features

- Second Wind - PHB 72

## Actions
### Actions
Attack

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class |  |

## Attacks And Cantrips
| Attack | Hit | Damage | Notes |
| --- | --- | --- | --- |
| Longsword | +5 | 1d8+3 Slashing | Versatile |
| Longsword | +5 | 1d8+3 Slashing | Versatile |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Longsword | 1 | 3 lb. |
| Longsword | 1 | 3 lb. |
""".strip()

    definition, _ = parse_character_sheet_text(
        "linden-pass",
        markdown,
        source_path="Mira.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Mira.pdf",
        parser_version="test",
    )

    longsword_attacks = [attack for attack in definition.attacks if attack["name"] == "Longsword"]
    longsword_items = [item for item in definition.equipment_catalog if item["name"] == "Longsword"]

    assert len(longsword_attacks) == 1
    assert len(longsword_items) == 1
    assert longsword_items[0]["default_quantity"] == 2


def test_apply_systems_links_to_definition_re_normalizes_duplicate_rows_and_keeps_matches():
    definition = CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="mira-salt",
        name="Mira Salt",
        status="active",
        profile={
            "sheet_name": "Mira Salt",
            "display_name": "Mira Salt",
            "class_level_text": "Fighter 1",
            "classes": [{"class_name": "Fighter", "subclass_name": "", "level": 1}],
            "species": "Human",
            "background": "Sailor",
        },
        stats={
            "ability_scores": {
                "str": {"score": 16, "modifier": 3, "save_bonus": 5},
                "dex": {"score": 12, "modifier": 1, "save_bonus": 1},
                "con": {"score": 14, "modifier": 2, "save_bonus": 4},
                "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                "wis": {"score": 12, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 8, "modifier": -1, "save_bonus": -1},
            }
        },
        skills=[],
        proficiencies={"armor": [], "weapons": [], "tools": [], "languages": ["Common"]},
        attacks=[
            {"id": "longsword-1", "name": "Longsword", "category": "weapon", "attack_bonus": 5, "damage": "1d8+3 Slashing", "damage_type": "", "notes": "Versatile"},
            {"id": "longsword-2", "name": "Longsword", "category": "weapon", "attack_bonus": 5, "damage": "1d8+3 Slashing", "damage_type": "", "notes": "Versatile"},
        ],
        features=[],
        spellcasting={"spellcasting_class": "", "spellcasting_ability": "", "spell_save_dc": None, "spell_attack_bonus": None, "slot_progression": [], "spells": []},
        equipment_catalog=[
            {"id": "longsword-a", "name": "Longsword", "default_quantity": 1, "weight": "3 lb.", "notes": ""},
            {"id": "longsword-b", "name": "Longsword", "default_quantity": 1, "weight": "3 lb.", "notes": ""},
        ],
        reference_notes={"additional_notes_markdown": "", "allies_and_organizations_markdown": "", "custom_sections": []},
        resource_templates=[],
        source={"source_path": "Mira.pdf", "source_type": "pdf_character_sheet_annotations", "imported_from": "Mira.pdf", "imported_at": "2026-03-30T00:00:00Z", "parse_warnings": []},
    )
    linked_definition = apply_systems_links_to_definition(
        definition,
        {
            "profile": {},
            "features": [],
            "attacks": [
                {"match": {"status": "unresolved"}},
                {"match": {"status": "matched", "entry_type": "item", "slug": "phb-item-longsword", "title": "Longsword", "source_id": "PHB"}},
            ],
            "equipment": [
                {"match": {"status": "unresolved"}},
                {"match": {"status": "matched", "entry_type": "item", "slug": "phb-item-longsword", "title": "Longsword", "source_id": "PHB"}},
            ],
            "spells": [],
        },
    )

    longsword_attacks = [attack for attack in linked_definition.attacks if attack["name"] == "Longsword"]
    longsword_items = [item for item in linked_definition.equipment_catalog if item["name"] == "Longsword"]

    assert len(longsword_attacks) == 1
    assert longsword_attacks[0]["systems_ref"]["slug"] == "phb-item-longsword"
    assert len(longsword_items) == 1
    assert longsword_items[0]["default_quantity"] == 2
    assert longsword_items[0]["systems_ref"]["slug"] == "phb-item-longsword"


def test_apply_systems_links_to_definition_merges_linked_duplicate_attack_rows_with_different_names():
    definition = CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="mira-salt",
        name="Mira Salt",
        status="active",
        profile={
            "sheet_name": "Mira Salt",
            "display_name": "Mira Salt",
            "class_level_text": "Fighter 1",
            "classes": [{"class_name": "Fighter", "subclass_name": "", "level": 1}],
            "species": "Human",
            "background": "Sailor",
        },
        stats={
            "ability_scores": {
                "str": {"score": 16, "modifier": 3, "save_bonus": 5},
                "dex": {"score": 12, "modifier": 1, "save_bonus": 1},
                "con": {"score": 14, "modifier": 2, "save_bonus": 4},
                "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                "wis": {"score": 12, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 8, "modifier": -1, "save_bonus": -1},
            }
        },
        skills=[],
        proficiencies={"armor": [], "weapons": [], "tools": [], "languages": ["Common"]},
        attacks=[
            {"id": "huron-blade-1", "name": "Huron Blade", "category": "weapon", "attack_bonus": 5, "damage": "1d8+3 Slashing", "damage_type": "", "notes": "Versatile"},
            {"id": "longsword-2", "name": "Longsword", "category": "weapon", "attack_bonus": 5, "damage": "1d8+3 Slashing", "damage_type": "", "notes": "Versatile"},
        ],
        features=[],
        spellcasting={"spellcasting_class": "", "spellcasting_ability": "", "spell_save_dc": None, "spell_attack_bonus": None, "slot_progression": [], "spells": []},
        equipment_catalog=[],
        reference_notes={"additional_notes_markdown": "", "allies_and_organizations_markdown": "", "custom_sections": []},
        resource_templates=[],
        source={"source_path": "Mira.pdf", "source_type": "pdf_character_sheet_annotations", "imported_from": "Mira.pdf", "imported_at": "2026-03-30T00:00:00Z", "parse_warnings": []},
    )
    linked_definition = apply_systems_links_to_definition(
        definition,
        {
            "profile": {},
            "features": [],
            "attacks": [
                {"match": {"status": "matched", "entry_type": "item", "slug": "phb-item-longsword", "title": "Longsword", "source_id": "PHB"}},
                {"match": {"status": "matched", "entry_type": "item", "slug": "phb-item-longsword", "title": "Longsword", "source_id": "PHB"}},
            ],
            "equipment": [],
            "spells": [],
        },
    )

    assert len(linked_definition.attacks) == 1
    assert linked_definition.attacks[0]["name"] == "Huron Blade"
    assert linked_definition.attacks[0]["systems_ref"]["slug"] == "phb-item-longsword"


def test_import_character_reconciles_missing_resource_trackers_into_existing_state(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    db_path = tmp_path / "player_wiki.sqlite3"
    source_path = tmp_path / "Zigzag - Character Sheet.md"
    source_path.write_text(_sample_split_action_markdown(), encoding="utf-8")

    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "DB_PATH", db_path)

    project_root = Path(__file__).resolve().parents[1]
    first_import = import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )
    assert first_import.state_created is True

    app = create_app()
    with app.app_context():
        init_database()
        repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", "zigzag-blackscar")
        assert record is not None
        payload = deepcopy(record.state_record.state)
        payload["resources"] = [
            resource
            for resource in payload["resources"]
            if resource.get("id") != "action-surge"
        ]
        second_wind = next(resource for resource in payload["resources"] if resource["id"] == "second-wind")
        second_wind["current"] = 0
        state_store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )

    second_import = import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )
    assert second_import.state_created is False

    app = create_app()
    with app.app_context():
        init_database()
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "zigzag-blackscar")
        assert record is not None
        resources = {resource["id"]: resource for resource in record.state_record.state["resources"]}

    assert resources["action-surge"]["current"] == 1
    assert resources["action-surge"]["max"] == 1
    assert resources["action-surge"]["reset_on"] == "short_rest"
    assert resources["second-wind"]["current"] == 0


def test_import_character_preserves_existing_campaign_page_overrides(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    db_path = tmp_path / "player_wiki.sqlite3"
    source_path = tmp_path / "Zigzag - Character Sheet.md"
    source_markdown = _sample_split_action_markdown().replace(
        "| Backpack | 1 | 5 lb. |",
        "| Huron Blade | 1 | 3 lb. |",
    )
    source_path.write_text(source_markdown, encoding="utf-8")

    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "DB_PATH", db_path)

    project_root = Path(__file__).resolve().parents[1]
    character_dir = campaigns_dir / "linden-pass" / "characters" / "zigzag-blackscar"

    import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )

    definition_path = character_dir / "definition.yaml"
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    attack = next(entry for entry in payload["attacks"] if entry["name"] == "Huron Blade")
    attack["name"] = "Consecrated Huran Blade"
    attack["page_ref"] = {
        "slug": "items/consecrated-huran-blade",
        "title": "Consecrated Huran Blade",
    }
    item = next(entry for entry in payload["equipment_catalog"] if entry["name"] == "Huron Blade")
    item["name"] = "Consecrated Huran Blade"
    item["page_ref"] = {
        "slug": "items/consecrated-huran-blade",
        "title": "Consecrated Huran Blade",
    }
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )

    attack = next(entry for entry in result.definition.attacks if entry["name"] == "Consecrated Huran Blade")
    item = next(entry for entry in result.definition.equipment_catalog if entry["name"] == "Consecrated Huran Blade")

    assert attack["name"] == "Consecrated Huran Blade"
    assert attack["page_ref"]["slug"] == "items/consecrated-huran-blade"
    assert "systems_ref" not in attack
    assert item["name"] == "Consecrated Huran Blade"
    assert item["page_ref"]["slug"] == "items/consecrated-huran-blade"
    assert "systems_ref" not in item


def test_resolve_definition_campaign_page_links_matches_homebrew_feature_shorthand(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    db_path = tmp_path / "player_wiki.sqlite3"
    mechanics_dir = campaigns_dir / "linden-pass" / "content" / "mechanics"
    mechanics_dir.mkdir(parents=True, exist_ok=True)
    (mechanics_dir / "wild-magic-modification.md").write_text(
        (
            "---\n"
            "title: Wild Magic Modification\n"
            "section: Mechanics\n"
            "type: mechanic\n"
            "---\n\n"
            "You gain a number of Wild Die equal to half your level.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "DB_PATH", db_path)

    definition = _minimal_imported_definition(
        features=[
            {
                "id": "wild-magic-mod",
                "name": "Wild Magic Mod •",
                "category": "feat",
                "source": "",
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": "wild-die",
            }
        ],
        resource_templates=[
            {
                "id": "wild-die",
                "label": "Wild Die",
                "category": "feat",
                "initial_current": 3,
                "max": 3,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
                "notes": "Wild Die: 3 / Long Rest",
                "display_order": 0,
            }
        ],
    )

    app = create_app()
    with app.app_context():
        init_database()
        page_links = resolve_definition_campaign_page_links(
            app.extensions["repository_store"],
            app.extensions["campaign_page_store"],
            "linden-pass",
            definition,
        )
        linked_definition = apply_systems_links_to_definition(
            definition,
            {
                "profile": {},
                "features": [{"match": {"status": "unresolved"}}],
                "attacks": [],
                "equipment": [],
                "spells": [],
            },
            campaign_page_links=page_links,
        )

    assert page_links["features"][0]["match"]["page_ref"] == "mechanics/wild-magic-modification"
    assert linked_definition.features[0]["page_ref"]["slug"] == "mechanics/wild-magic-modification"
    assert linked_definition.features[0]["page_ref"]["title"] == "Wild Magic Modification"


def test_resolve_definition_systems_links_falls_back_to_parent_feature_for_nested_rows():
    definition, _ = parse_character_sheet_text(
        "linden-pass",
        _sample_split_action_markdown(),
        source_path="Zigzag.pdf",
        source_type="pdf_character_sheet_annotations",
        imported_from="Zigzag.pdf",
        parser_version="test",
    )
    systems_service = _FakeSystemsService(
        [
            _sample_system_entry(
                entry_key="scf-psionic-power",
                entry_type="subclassfeature",
                title="Psionic Power",
                source_id="TCE",
                metadata={"class_name": "Fighter", "subclass_name": "Psi Warrior"},
            ),
        ]
    )

    links = resolve_definition_systems_links(systems_service, "linden-pass", definition)
    recovery = next(entry for entry in links["features"] if entry["name"] == "Psionic Power: Recovery")

    assert recovery["match"]["status"] == "matched"
    assert recovery["match"]["title"] == "Psionic Power"
    assert recovery["match"]["strategy"] == "alias"
    assert recovery["match"]["query"] == "Psionic Power"


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
                entry_key="item-longsword",
                entry_type="item",
                title="Longsword",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-chain-mail",
                entry_type="item",
                title="Chain Mail",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-light-crossbow",
                entry_type="item",
                title="Light Crossbow",
                source_id="PHB",
            ),
            _sample_system_entry(
                entry_key="item-crossbow-bolts",
                entry_type="item",
                title="Crossbow Bolts (20)",
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

    attacks_by_name = {entry["name"]: entry for entry in links["attacks"]}
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
    assert attacks_by_name["Crossbow, Light"]["match"]["title"] == "Light Crossbow"
    assert equipment_by_name["Backpack"]["match"]["title"] == "Backpack"
    assert equipment_by_name["Longsword"]["match"]["title"] == "Longsword"
    assert equipment_by_name["Chain Mail"]["match"]["title"] == "Chain Mail"
    assert equipment_by_name["Crossbow Bolts"]["match"]["title"] == "Crossbow Bolts (20)"


def test_converge_imported_definition_preserves_existing_spell_links_when_duplicates_collapse():
    existing_definition = _minimal_imported_definition(
        spellcasting={
            "spells": [
                {
                    "id": "light-1",
                    "name": "Beacon Spark",
                    "mark": "Known",
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "1 hour",
                    "components": "V, M",
                    "save_or_hit": "",
                    "source": "PHB",
                    "reference": "p. 255",
                    "page_ref": {
                        "slug": "spells/beacon-spark",
                        "title": "Beacon Spark",
                    },
                    "systems_ref": {
                        "entry_type": "spell",
                        "slug": "phb-spell-light",
                        "title": "Light",
                        "source_id": "PHB",
                    },
                }
            ]
        },
    )
    incoming_definition = _minimal_imported_definition(
        spellcasting={
            "spells": [
                {
                    "id": "light-a",
                    "name": "Light",
                    "mark": "Known",
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "1 hour",
                    "components": "V, M",
                    "save_or_hit": "",
                    "source": "PHB",
                    "reference": "p. 255",
                },
                {
                    "id": "light-b",
                    "name": "LIGHT",
                    "mark": "",
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "1 hour",
                    "components": "V, M",
                    "save_or_hit": "",
                    "source": "PHB",
                    "reference": "p. 255",
                    "systems_ref": {
                        "entry_type": "spell",
                        "slug": "phb-spell-light",
                        "title": "Light",
                        "source_id": "PHB",
                    },
                },
            ]
        },
    )

    converged = converge_imported_definition(
        incoming_definition,
        existing_definition=existing_definition,
    )

    assert len(converged.spellcasting["spells"]) == 1
    spell = converged.spellcasting["spells"][0]
    assert spell["id"] == "light-1"
    assert spell["name"] == "Beacon Spark"
    assert spell["page_ref"]["slug"] == "spells/beacon-spark"
    assert spell["systems_ref"]["slug"] == "phb-spell-light"


def test_converge_imported_definition_preserves_feature_tracker_identity():
    existing_definition = _minimal_imported_definition(
        features=[
            {
                "id": "psi-power",
                "name": "Psionic Power",
                "category": "class_feature",
                "source": "TCE 43",
                "description_markdown": "You have a reserve of psionic energy.",
                "activation_type": "special",
                "tracker_ref": "harbor-energy",
            }
        ],
        resource_templates=[
            {
                "id": "harbor-energy",
                "label": "Harbor Energy",
                "category": "class_feature",
                "initial_current": 4,
                "max": 4,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
                "notes": "Psionic Power",
                "display_order": 0,
            }
        ],
    )
    incoming_definition = _minimal_imported_definition(
        features=[
            {
                "id": "psi-power-new",
                "name": "Psionic Power",
                "category": "class_feature",
                "source": "TCE 43",
                "description_markdown": "You have a reserve of psionic energy.",
                "activation_type": "special",
                "tracker_ref": "psionic-power-energy",
            }
        ],
        resource_templates=[
            {
                "id": "psionic-power-energy",
                "label": "Harbor Energy",
                "category": "class_feature",
                "initial_current": 5,
                "max": 5,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
                "notes": "Psionic Power",
                "display_order": 0,
            }
        ],
    )

    converged = converge_imported_definition(
        incoming_definition,
        existing_definition=existing_definition,
    )

    assert converged.features[0]["id"] == "psi-power"
    assert converged.features[0]["tracker_ref"] == "harbor-energy"
    assert converged.resource_templates[0]["id"] == "harbor-energy"
    assert converged.resource_templates[0]["max"] == 5


def test_apply_systems_links_to_definition_merges_alias_equipment_rows_with_quantity():
    definition = _minimal_imported_definition(
        equipment_catalog=[
            {
                "id": "bolts-a",
                "name": "Crossbow Bolts",
                "default_quantity": 1,
                "weight": "1 lb.",
                "notes": "",
                "tags": [],
            },
            {
                "id": "bolts-b",
                "name": "Crossbow Bolts (20)",
                "default_quantity": 2,
                "weight": "1 lb.",
                "notes": "",
                "tags": [],
            },
        ],
    )

    linked_definition = apply_systems_links_to_definition(
        definition,
        {
            "profile": {},
            "features": [],
            "attacks": [],
            "equipment": [
                {"match": {"status": "unresolved"}},
                {
                    "match": {
                        "status": "matched",
                        "entry_type": "item",
                        "slug": "phb-item-crossbow-bolts",
                        "title": "Crossbow Bolts (20)",
                        "source_id": "PHB",
                    }
                },
            ],
            "spells": [],
        },
    )

    assert len(linked_definition.equipment_catalog) == 1
    item = linked_definition.equipment_catalog[0]
    assert item["default_quantity"] == 3
    assert item["systems_ref"]["slug"] == "phb-item-crossbow-bolts"


def test_import_character_reimport_removes_missing_trackers_and_preserves_surviving_state(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    db_path = tmp_path / "player_wiki.sqlite3"
    source_path = tmp_path / "Zigzag - Character Sheet.md"
    source_path.write_text(_sample_split_action_markdown(), encoding="utf-8")

    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "DB_PATH", db_path)

    project_root = Path(__file__).resolve().parents[1]
    import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )

    app = create_app()
    with app.app_context():
        init_database()
        repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", "zigzag-blackscar")
        assert record is not None
        payload = deepcopy(record.state_record.state)
        second_wind = next(resource for resource in payload["resources"] if resource["id"] == "second-wind")
        second_wind["current"] = 0
        state_store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )

    updated_source = _sample_split_action_markdown().replace(
        "- Action Surge - PHB 72\nYou can take one additional action on your turn.\n\n",
        "",
    )
    updated_source = updated_source.replace("- 1 / Short Rest - Special\n\n", "", 1)
    source_path.write_text(updated_source, encoding="utf-8")

    result = import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )
    assert result.state_created is False

    app = create_app()
    with app.app_context():
        init_database()
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "zigzag-blackscar")
        assert record is not None
        resources = {resource["id"]: resource for resource in record.state_record.state["resources"]}

    assert "action-surge" not in resources
    assert resources["second-wind"]["current"] == 0


def test_import_character_reimport_preserves_spell_links_and_removes_missing_spells(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    db_path = tmp_path / "player_wiki.sqlite3"
    source_path = tmp_path / "Mira - Character Sheet.md"
    source_path.write_text(
        _sample_spell_reimport_markdown(
            "| Light | Known | | 1 action | Touch | 1 hour | V, M | PHB | p. 255 |",
            "| Message | Known | | 1 action | 120 feet | 1 round | V, S, M | PHB | p. 259 |",
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "DB_PATH", db_path)

    project_root = Path(__file__).resolve().parents[1]
    character_dir = campaigns_dir / "linden-pass" / "characters" / "mira-salt"
    import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="mira-salt",
    )

    definition_path = character_dir / "definition.yaml"
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    light = next(spell for spell in payload["spellcasting"]["spells"] if spell["name"] == "Light")
    light["name"] = "Beacon Spark"
    light["page_ref"] = {"slug": "spells/beacon-spark", "title": "Beacon Spark"}
    light["systems_ref"] = {
        "entry_type": "spell",
        "slug": "phb-spell-light",
        "title": "Light",
        "source_id": "PHB",
    }
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    source_path.write_text(
        _sample_spell_reimport_markdown(
            "| Light | Known | | 1 action | Touch | 1 hour | V, M | PHB | p. 255 |",
            "| Mage Hand | Known | | 1 action | 30 feet | 1 minute | V, S | PHB | p. 256 |",
        ),
        encoding="utf-8",
    )

    result = import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="mira-salt",
    )
    spells_by_name = {spell["name"]: spell for spell in result.definition.spellcasting["spells"]}

    assert "Message" not in spells_by_name
    assert "Mage Hand" in spells_by_name
    assert spells_by_name["Beacon Spark"]["page_ref"]["slug"] == "spells/beacon-spark"
    assert spells_by_name["Beacon Spark"]["systems_ref"]["slug"] == "phb-spell-light"


def test_converged_imported_definitions_keep_profile_refs_but_remain_level_up_ineligible():
    existing_definition = _minimal_imported_definition(
        profile={
            "class_ref": {"slug": "phb-class-wizard", "title": "Wizard", "entry_type": "class", "source_id": "PHB"},
            "subclass_ref": {"slug": "phb-subclass-evocation", "title": "School of Evocation", "entry_type": "subclass", "source_id": "PHB"},
            "species_ref": {"slug": "phb-race-human", "title": "Human", "entry_type": "race", "source_id": "PHB"},
            "background_ref": {"slug": "phb-background-sage", "title": "Sage", "entry_type": "background", "source_id": "PHB"},
            "classes": [
                {
                    "class_name": "Wizard",
                    "subclass_name": "School of Evocation",
                    "level": 3,
                    "systems_ref": {"slug": "phb-class-wizard", "title": "Wizard", "entry_type": "class", "source_id": "PHB"},
                    "subclass_ref": {"slug": "phb-subclass-evocation", "title": "School of Evocation", "entry_type": "subclass", "source_id": "PHB"},
                }
            ],
        },
    )
    incoming_definition = _minimal_imported_definition()

    converged = converge_imported_definition(
        incoming_definition,
        existing_definition=existing_definition,
    )

    assert converged.profile["class_ref"]["slug"] == "phb-class-wizard"
    assert converged.profile["subclass_ref"]["slug"] == "phb-subclass-evocation"
    assert converged.profile["species_ref"]["slug"] == "phb-race-human"
    assert converged.profile["background_ref"]["slug"] == "phb-background-sage"
    assert converged.profile["classes"][0]["systems_ref"]["slug"] == "phb-class-wizard"
    assert converged.profile["classes"][0]["subclass_ref"]["slug"] == "phb-subclass-evocation"
    assert supports_native_level_up(converged) is False


def test_converge_imported_definition_does_not_downgrade_native_progression_from_stale_reimport():
    existing_definition = _minimal_imported_definition(
        profile={
            "class_level_text": "Wizard 4",
            "class_ref": {"slug": "phb-class-wizard", "title": "Wizard", "entry_type": "class", "source_id": "PHB"},
            "subclass_ref": {"slug": "phb-subclass-evocation", "title": "School of Evocation", "entry_type": "subclass", "source_id": "PHB"},
            "species_ref": {"slug": "phb-race-human", "title": "Human", "entry_type": "race", "source_id": "PHB"},
            "background_ref": {"slug": "phb-background-sage", "title": "Sage", "entry_type": "background", "source_id": "PHB"},
            "classes": [
                {
                    "class_name": "Wizard",
                    "subclass_name": "School of Evocation",
                    "level": 4,
                    "systems_ref": {"slug": "phb-class-wizard", "title": "Wizard", "entry_type": "class", "source_id": "PHB"},
                    "subclass_ref": {"slug": "phb-subclass-evocation", "title": "School of Evocation", "entry_type": "subclass", "source_id": "PHB"},
                }
            ],
        },
        features=[
            {
                "id": "wizard-asi",
                "name": "Ability Score Improvement",
                "category": "class_feature",
                "source": "PHB",
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": None,
            }
        ],
    )
    existing_definition.stats["max_hp"] = 24
    existing_definition.source["native_progression"] = {
        "baseline_repaired_at": "2026-03-31T00:00:00Z",
        "history": [
            {"kind": "repair", "at": "2026-03-31T00:00:00Z", "target_level": 3},
            {"kind": "level_up", "at": "2026-03-31T01:00:00Z", "from_level": 3, "to_level": 4, "target_level": 4},
        ],
    }
    incoming_definition = _minimal_imported_definition()

    converged = converge_imported_definition(
        incoming_definition,
        existing_definition=existing_definition,
    )

    assert converged.profile["class_level_text"] == "Wizard 4"
    assert converged.profile["classes"][0]["level"] == 4
    assert converged.stats["max_hp"] == 24
    assert converged.source["native_progression"]["history"][-1]["to_level"] == 4


