from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.systems_importer_fakes import build_test_data_root, write_json

SCAG_CLASSES_TEST_SECTION_DEFINITIONS = (
    ("Barbarians", 121, ("Uthgardt Tribes", "Berserkers of the North")),
    ("Primal Paths", 121, ("Path of the Battlerager", "Path of the Totem Warrior")),
    ("Bards", 122, ("Harpers and Heralds",)),
    ("The Harpers", 123, ("Harper Agent",)),
    ("Bardic Colleges", 123, ("College of Fochlucan", "College of New Olamn", "College of the Herald")),
    ("Musical Instruments", 124, ("Birdpipes", "Longhorn")),
    ("Clerics", 125, ("Priests of Faerun",)),
    ("Divine Domain", 125, ("Arcana Domain",)),
    ("Druids", 126, ("Circle Traditions",)),
    ("Druid Circles", 126, ("Circle of the Land",)),
    ("Fighters", 127, ("Mercenary Companies",)),
    ("Martial Archetype", 128, ("Purple Dragon Knight",)),
    ("Monks", 129, ("Monasteries of the Realms",)),
    ("Monastic Orders", 129, ("Order of the Yellow Rose",)),
    ("Monastic Traditions", 130, ("Way of the Long Death", "Way of the Sun Soul")),
    ("Paladins", 131, ("Knightly Orders",)),
    ("Paladin Orders", 132, ("Order of the Gauntlet",)),
    ("Sacred Oath", 132, ("Oath of the Crown",)),
    ("Rangers", 133, ("Wardens of the North",)),
    ("Rogues", 134, ("Rogues of Faerun",)),
    ("Roguish Archetypes", 135, ("Mastermind", "Swashbuckler")),
    ("Sorcerers", 136, ("Spellscarred Bloodlines",)),
    ("Sorcerous Origin", 137, ("Storm Sorcery",)),
    ("Warlocks", 138, ("Patrons in the Realms", "The Archfey", "The Fiend", "The Great Old One")),
    ("Otherworldly Patron", 139, ("The Undying",)),
    ("Wizards", 140, ("The Art in Faerun",)),
    ("Wizardly Groups", 140, ("War Wizards of Cormyr",)),
    ("Arcane Tradition", 141, ("Bladesinger", "Bladesinger Styles")),
    (
        "Cantrips for Sorcerers, Warlocks, and Wizards",
        142,
        ("Booming Blade", "Green-Flame Blade"),
    ),
)
SCAG_CLASSES_TEST_HEADERS = tuple(name for name, _, _ in SCAG_CLASSES_TEST_SECTION_DEFINITIONS)


XGE_RULES_REFERENCE_TEST_TITLES = (
    "Simultaneous Effects",
    "Falling",
    "Sleep",
    "Waking Someone",
    "Adamantine Weapons",
    "Tying Knots",
    "Tool Proficiencies",
    "Spellcasting",
    "Identifying a Spell",
    "Encounter Building",
    "Random Encounters: A World of Possibilities",
    "Traps Revisited",
    "Downtime Revisited",
    "Awarding Magic Items",
    "Shared Campaigns",
    "Variant Rules",
)


TCE_CLASS_WRAPPER_TEST_TITLES = (
    "Artificer",
    "Barbarian",
    "Bard",
    "Cleric",
    "Druid",
    "Fighter",
    "Monk",
    "Paladin",
    "Ranger",
    "Rogue",
    "Sorcerer",
    "Warlock",
    "Wizard",
)


TCE_RULES_REFERENCE_TEST_TITLES = (
    "Ten Rules to Remember",
    "Customizing Your Origin",
    "Changing a Skill",
    "Changing Your Subclass",
) + TCE_CLASS_WRAPPER_TEST_TITLES + (
    "Group Patrons",
    "Personalizing Spells",
    "Magic Tattoos",
    "Session Zero",
    "Sidekicks",
    "Parleying with Monsters",
    "Environmental Hazards",
    "Puzzles",
)


def build_phb_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Player's Handbook (2014)",
                    "id": "PHB",
                    "source": "PHB",
                    "contents": [
                        {
                            "name": "Introduction",
                            "headers": [
                                "Worlds of Adventure",
                                "How to Play",
                            ],
                        },
                        {
                            "name": "Step-by-Step Characters",
                            "headers": [
                                "1. Choose a Race",
                                "Beyond 1st Level",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 1},
                        },
                        {
                            "name": "Equipment",
                            "headers": ["Armor and Shields"],
                            "ordinal": {"type": "chapter", "identifier": 5},
                        },
                        {
                            "name": "Customization Options",
                            "headers": ["Multiclassing", "Feats"],
                            "ordinal": {"type": "chapter", "identifier": 6},
                        },
                        {
                            "name": "Using Ability Scores",
                            "headers": [
                                "Advantage and Disadvantage",
                                "Ability Checks",
                                "Contests",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 7},
                        },
                        {
                            "name": "Adventuring",
                            "headers": [
                                "Time",
                                "Resting",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 8},
                        },
                        {
                            "name": "Combat",
                            "headers": [
                                "Surprise",
                                "Reactions",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 9},
                        },
                        {
                            "name": "Spellcasting",
                            "headers": [
                                "Casting a Spell",
                                "Components",
                                "Targets",
                                "Areas of Effect",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 10},
                        },
                        {
                            "name": "Conditions",
                            "ordinal": {"type": "appendix", "identifier": "A"},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/variantrules.json",
        {
            "variantrule": [
                {
                    "name": "Encumbrance",
                    "source": "PHB",
                    "page": 176,
                    "ruleType": "O",
                    "entries": ["If you carry weight in excess of 5 times your Strength score, you are encumbered."],
                },
                {
                    "name": "Multiclassing",
                    "source": "PHB",
                    "page": 163,
                    "ruleType": "O",
                    "entries": ["This optional rule lets a character gain levels in multiple classes."],
                },
            ]
        },
    )
    write_json(
        root / "data/book/book-phb.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Introduction",
                    "page": 5,
                    "entries": [
                        "Dungeons & Dragons is a game of shared adventure.",
                        {
                            "type": "section",
                            "name": "How to Play",
                            "page": 6,
                            "entries": [
                                "The DM describes the environment, the players say what they do, and the DM narrates the results.",
                            ],
                        },
                        {
                            "type": "image",
                            "href": {"type": "internal", "path": "book/PHB/intro.webp"},
                            "width": 1200,
                            "height": 800,
                        },
                    ],
                    "id": "phb-intro",
                },
                {
                    "type": "section",
                    "name": "Step-by-Step Characters",
                    "page": 11,
                    "entries": [
                        "Your first step is choosing a race and a class.",
                        {
                            "type": "section",
                            "name": "5. Choose Equipment",
                            "page": 14,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Armor Class",
                                    "page": 14,
                                    "entries": [
                                        "Armor such as {@item chain mail|phb} helps protect you.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Weapons",
                                    "page": 14,
                                    "entries": [
                                        "Martial weapons such as {@item longsword|phb} give you strong options in battle.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Beyond 1st Level",
                            "page": 15,
                            "entries": [
                                "As your character adventures, you gain experience and new features.",
                            ],
                        },
                    ],
                    "id": "phb-step",
                },
                {
                    "type": "section",
                    "name": "Equipment",
                    "page": 143,
                    "entries": [
                        "Equipment includes armor, weapons, and adventuring gear.",
                        {
                            "type": "section",
                            "name": "Armor and Shields",
                            "page": 144,
                            "entries": [
                                "Armor such as {@item chain mail|phb} helps protect you in battle.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Weapons",
                            "page": 146,
                            "entries": [
                                "Weapons such as {@item longsword|phb} and {@item light crossbow|phb} support different fighting styles.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Tools",
                            "page": 154,
                            "entries": [
                                "A set of tools lets you apply a specific craft or trade.",
                            ],
                        },
                    ],
                    "id": "phb-equipment",
                },
                {
                    "type": "section",
                    "name": "Customization Options",
                    "page": 163,
                    "entries": [
                        "Customization options let a group opt into broader character-building rules.",
                        {
                            "type": "section",
                            "name": "Multiclassing",
                            "page": 163,
                            "entries": [
                                "The optional {@variantrule Multiclassing|PHB} rule lets you gain levels in multiple classes.",
                                {
                                    "type": "entries",
                                    "name": "Spell Slots",
                                    "page": 164,
                                    "entries": [
                                        "Multiclass spellcasters combine class levels to determine available spell slots.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Feats",
                            "page": 165,
                            "entries": [
                                "A feat represents talent or expertise beyond standard class progression.",
                                "The {@feat Alert|PHB} feat is one example of the options in this chapter.",
                            ],
                        },
                    ],
                    "id": "phb-customization",
                },
                {
                    "type": "section",
                    "name": "Using Ability Scores",
                    "page": 173,
                    "entries": [
                        "Six abilities describe a creature's physical and mental characteristics.",
                        {
                            "type": "section",
                            "name": "Advantage and Disadvantage",
                            "page": 173,
                            "entries": [
                                "Roll two d20s and use the higher roll for advantage or the lower roll for disadvantage.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Ability Checks",
                            "page": 174,
                            "entries": [
                                "An ability check tests a creature's training and talent.",
                                {
                                    "type": "entries",
                                    "name": "Passive Checks",
                                    "page": 175,
                                    "entries": [
                                        {"type": "abilityGeneric", "text": "10 + all modifiers that normally apply to the check"},
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Contests",
                                    "page": 175,
                                    "entries": [
                                        "A contest pits two creatures' efforts against each other.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Skills",
                                    "page": 174,
                                    "entries": [
                                        "Climbing, jumping, or swimming often calls for {@skill Athletics} checks.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Working Together",
                                    "page": 175,
                                    "entries": [
                                        "When two or more characters team up, one of them can use the {@action Help} action.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "image",
                            "href": {"type": "internal", "path": "book/PHB/ch7.webp"},
                            "width": 1200,
                            "height": 800,
                        },
                    ],
                    "id": "phb-ability",
                },
                {
                    "type": "section",
                    "name": "Adventuring",
                    "page": 181,
                    "entries": [
                        "Adventuring covers exploration, travel, and rest.",
                        {
                            "type": "section",
                            "name": "Movement",
                            "page": 181,
                            "entries": [
                                "Time can be tracked in rounds, minutes, hours, or days.",
                                {
                                    "type": "entries",
                                    "name": "The Environment",
                                    "page": 183,
                                    "entries": [
                                        {
                                            "type": "entries",
                                            "name": "Vision and Light",
                                            "alias": ["Darkvision"],
                                            "page": 183,
                                            "entries": [
                                                "Darkness can leave a creature effectively {@condition blinded}.",
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Resting",
                            "page": 186,
                            "entries": ["Short rests and long rests let characters recover."],
                        },
                    ],
                    "id": "phb-adventuring",
                },
                {
                    "type": "section",
                    "name": "Combat",
                    "page": 189,
                    "entries": [
                        "Combat unfolds in rounds and turns.",
                        {
                            "type": "section",
                            "name": "Actions in Combat",
                            "page": 192,
                            "entries": [
                                "You can use the {@action Help} action to aid an ally.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Surprise",
                            "page": 189,
                            "entries": ["A surprised creature cannot move or act on its first turn."],
                        },
                        {
                            "type": "section",
                            "name": "Reactions",
                            "page": 190,
                            "entries": ["A reaction is an instant response to a trigger."],
                        },
                    ],
                    "id": "phb-combat",
                },
                {
                    "type": "section",
                    "name": "Spellcasting",
                    "page": 201,
                    "entries": [
                        "Spellcasting uses slots, components, and timing rules.",
                        {
                            "type": "section",
                            "name": "Casting a Spell",
                            "page": 202,
                            "entries": [
                                "Casting a spell requires choosing the spell and following its casting time.",
                                {
                                    "type": "entries",
                                    "name": "Components",
                                    "page": 203,
                                    "entries": [
                                        "Verbal, somatic, and material components define what a caster must provide for spells such as {@spell mage hand}.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Targets",
                            "page": 204,
                            "entries": [
                                "A spell's description tells you whether it targets creatures, objects, or points in space.",
                                {
                                    "type": "entries",
                                    "name": "Areas of Effect",
                                    "page": 204,
                                    "entries": [
                                        "Some spells affect an area rather than a single target.",
                                    ],
                                },
                            ],
                        },
                    ],
                    "id": "phb-spellcasting",
                },
                {
                    "type": "section",
                    "name": "Conditions",
                    "page": 289,
                    "entries": [
                        "Conditions alter a creature's capabilities in a variety of ways.",
                        {
                            "type": "inlineBlock",
                            "entries": [
                                "The conditions are:",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@condition blinded}",
                                        "{@condition charmed}",
                                        "{@condition deafened}",
                                    ],
                                },
                            ],
                        },
                    ],
                    "id": "phb-conditions",
                },
            ]
        },
    )
    return data_root


def build_dmg_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/actions.json",
        {
            "action": [
                {
                    "name": "Help",
                    "source": "PHB",
                    "page": 192,
                    "time": [{"number": 1, "unit": "action"}],
                    "entries": ["You can lend your aid to another creature in the completion of a task."],
                },
                {
                    "name": "Overrun",
                    "source": "DMG",
                    "page": 272,
                    "time": [{"number": 1, "unit": "action"}],
                    "entries": ["You can try to force your way through a hostile creature's space by making a contested check."],
                },
            ]
        },
    )
    write_json(
        root / "data/conditionsdiseases.json",
        {
            "condition": [
                {
                    "name": "Blinded",
                    "source": "PHB",
                    "page": 290,
                    "entries": ["A blinded creature can't see."],
                }
            ],
            "disease": [
                {
                    "name": "Cackle Fever",
                    "source": "DMG",
                    "page": 257,
                    "entries": ["This disease manifests in feverish laughter and bouts of disorientation."],
                }
            ],
            "status": [
                {
                    "name": "Concentration",
                    "source": "PHB",
                    "page": 203,
                    "entries": ["You can concentrate on only one spell at a time."],
                }
            ],
        },
    )
    write_json(
        root / "data/variantrules.json",
        {
            "variantrule": [
                {
                    "name": "Encumbrance",
                    "source": "PHB",
                    "page": 176,
                    "ruleType": "O",
                    "entries": ["If you carry weight in excess of 5 times your Strength score, you are encumbered."],
                },
                {
                    "name": "Chases",
                    "source": "DMG",
                    "page": 252,
                    "ruleType": "O",
                    "entries": ["A chase adds complications and escalating pressure while creatures flee or pursue."],
                },
                {
                    "name": "Downtime Activity: Building a Stronghold",
                    "source": "DMG",
                    "page": 128,
                    "ruleType": "O",
                    "entries": ["Characters can invest time and treasure to establish and maintain a stronghold."],
                },
                {
                    "name": "Downtime Activity: Carousing",
                    "source": "DMG",
                    "page": 128,
                    "ruleType": "O",
                    "entries": ["Carousing can build contacts and complications during downtime."],
                },
            ]
        },
    )
    write_json(
        root / "data/items.json",
        {
            "item": [
                {
                    "name": "Longsword",
                    "source": "PHB",
                    "page": 149,
                    "type": "M",
                    "weight": 3,
                    "entries": ["A versatile martial weapon."],
                },
                {
                    "name": "Potion of Healing",
                    "source": "DMG",
                    "page": 187,
                    "type": "P",
                    "weight": 0.5,
                    "entries": ["A character who drinks the magical red fluid regains hit points."],
                },
            ],
            "itemGroup": [],
        },
    )
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Dungeon Master's Guide (2014)",
                    "id": "DMG",
                    "source": "DMG",
                    "contents": [
                        {
                            "name": "Creating a Multiverse",
                            "headers": [
                                "The Planes",
                                "Planar Travel",
                                "Astral Plane",
                                "Ethereal Plane",
                                "Feywild",
                                "Shadowfell",
                                "Inner Planes",
                                "Outer Planes",
                                "Other Planes",
                                "Known Worlds of the Material Plane",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 2},
                        },
                        {
                            "name": "Adventure Environments",
                            "headers": [
                                "Dungeons",
                                "Mapping a Dungeon",
                                "Wilderness",
                                "Mapping a Wilderness",
                                "Wilderness Survival",
                                "Settlement",
                                "Mapping a Settlement",
                                "Urban Encounters",
                                "Unusual Environments",
                                "Traps",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 5},
                        },
                        {
                            "name": "Between Adventures",
                            "headers": ["Linking Adventures", "Campaign Tracking", "Recurring Expenses", "Downtime Activities"],
                            "ordinal": {"type": "chapter", "identifier": 6},
                        },
                        {
                            "name": "Treasure",
                            "headers": ["Random Treasure", "Magic Items", "Artifacts"],
                            "ordinal": {"type": "chapter", "identifier": 7},
                        },
                        {
                            "name": "Running the Game",
                            "headers": ["Using Ability Scores", "Combat", "Chases"],
                            "ordinal": {"type": "chapter", "identifier": 8},
                        },
                        {
                            "name": "Dungeon Master's Workshop",
                            "headers": ["Combat Options", "Creating a Monster"],
                            "ordinal": {"type": "chapter", "identifier": 9},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-dmg.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Creating a Multiverse",
                    "page": 43,
                    "entries": [
                        "The planes form the multiverse that lies beyond the Material Plane.",
                        {
                            "type": "section",
                            "name": "The Planes",
                            "page": 43,
                            "entries": [
                                "The multiverse includes transitive, inner, and outer planes.",
                                {
                                    "type": "entries",
                                    "name": "Planar Categories",
                                    "page": 43,
                                    "entries": [
                                        "Transitive, inner, and outer planes each serve different roles in a cosmology."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Putting the Planes Together",
                                    "page": 44,
                                    "entries": [
                                        "A cosmology can connect the planes in the way that best fits a campaign."
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Planar Travel",
                            "page": 44,
                            "entries": [
                                "Portals, spells, and magical sites can carry travelers between worlds.",
                                {
                                    "type": "entries",
                                    "name": "Planar Portals",
                                    "page": 44,
                                    "entries": ["Portals can be keyed to places, times, or rituals."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Spells",
                                    "page": 45,
                                    "entries": [
                                        "Magic such as plane shift and gate can move creatures across planar boundaries."
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Feywild",
                            "page": 49,
                            "entries": [
                                "The Feywild is a bright echo of the world steeped in emotion and strange magic.",
                                {
                                    "type": "entries",
                                    "name": "Optional Rules: Feywild Magic",
                                    "page": 50,
                                    "entries": ["Feywild regions can twist spells in whimsical ways."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Outer Planes",
                            "page": 57,
                            "entries": [
                                "The Outer Planes align with moral and philosophical principles.",
                                {
                                    "type": "entries",
                                    "name": "Traveling the Outer Planes",
                                    "page": 59,
                                    "entries": [
                                        "Journeys across the Outer Planes reflect belief, petitioners, and planar pathways."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Optional Rules",
                                    "page": 59,
                                    "entries": ["Planar traits and optional rules can reinforce a plane's theme."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Other Planes",
                            "page": 67,
                            "entries": [
                                "Demiplanes and stranger realms sit outside the main planar rings.",
                                {
                                    "type": "entries",
                                    "name": "The Outlands and Sigil",
                                    "page": 67,
                                    "entries": [
                                        "The Outlands connect to every Outer Plane, with Sigil at its spire's crown."
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Known Worlds of the Material Plane",
                            "page": 68,
                            "entries": [
                                "Material worlds such as Toril, Oerth, Krynn, and Athas can anchor distinct campaigns."
                            ],
                        },
                    ],
                    "id": "dmg-multiverse",
                },
                {
                    "type": "section",
                    "name": "Adventure Environments",
                    "page": 99,
                    "entries": [
                        "Adventure locations shape the hazards and pacing of an expedition.",
                        {
                            "type": "section",
                            "name": "Wilderness Survival",
                            "page": 109,
                            "entries": ["The wild demands navigation, supplies, and careful pace management."],
                        },
                        {
                            "type": "section",
                            "name": "Unusual Environments",
                            "page": 116,
                            "entries": ["Odd realms can impose magical or physical pressures on explorers."],
                        },
                        {
                            "type": "section",
                            "name": "Traps",
                            "page": 120,
                            "entries": [
                                "Traps can be found almost anywhere and punish careless adventurers.",
                                {
                                    "type": "entries",
                                    "name": "Traps in Play",
                                    "page": 120,
                                    "entries": [
                                        "A trap needs a trigger, an effect, and a fair chance to notice or foil it.",
                                        {
                                            "type": "entries",
                                            "name": "Triggering a Trap",
                                            "page": 120,
                                            "entries": [
                                                "Pressure plates, trip wires, and magical glyphs are common triggers."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Detecting and Disabling a Trap",
                                            "page": 120,
                                            "entries": [
                                                "Perception, Investigation, and tool use can expose or disarm a trap."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Trap Effects",
                                            "page": 121,
                                            "entries": [
                                                "Trap effects can range from setbacks to deadly hazards."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Complex Traps",
                                            "page": 121,
                                            "entries": [
                                                "Some traps act over multiple rounds and feel more like encounters."
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Sample Traps",
                                    "page": 121,
                                    "entries": ["Sample traps provide reusable patterns for dungeon hazards."],
                                },
                            ],
                            "id": "dmg-traps",
                        },
                    ],
                    "id": "dmg-adventure-environments",
                },
                {
                    "type": "section",
                    "name": "Between Adventures",
                    "page": 125,
                    "entries": [
                        "Campaigns often pause between major adventures.",
                        {
                            "type": "section",
                            "name": "Recurring Expenses",
                            "page": 126,
                            "entries": ["Owning property and hirelings creates continuing upkeep costs."],
                        },
                        {
                            "type": "section",
                            "name": "Downtime Activities",
                            "page": 127,
                            "entries": [
                                "Downtime lets characters craft, train, or pursue contacts.",
                                {
                                    "type": "entries",
                                    "name": "More Downtime Activities",
                                    "page": 128,
                                    "entries": [
                                        "The chapter adds more downtime options for campaigns.",
                                        {
                                            "type": "list",
                                            "items": [
                                                "{@variantrule Downtime Activity: Building a Stronghold||Building a Stronghold}",
                                                "{@variantrule Downtime Activity: Carousing||Carousing}",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Creating Downtime Activities",
                                    "page": 131,
                                    "entries": [
                                        "You can create new downtime activities that fit the campaign.",
                                    ],
                                },
                            ],
                        },
                    ],
                    "id": "dmg-between-adventures",
                },
                        {
                            "type": "section",
                            "name": "Treasure",
                            "page": 133,
                            "entries": [
                                "Treasure rewards adventurers with coins, art objects, and magic.",
                                {
                                    "type": "section",
                                    "name": "Magic Items",
                                    "page": 135,
                                    "entries": [
                                        "Magic items such as {@item Potion of Healing|DMG} can keep an expedition going.",
                                        {
                                            "type": "entries",
                                            "name": "Attunement",
                                            "page": 136,
                                            "entries": ["Some magic items require a creature to attune to them before they work."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Cursed Items",
                                    "page": 138,
                                    "entries": ["Some items carry hidden drawbacks that complicate their use."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Artifacts",
                            "page": 219,
                            "entries": ["Artifacts are unique magic items of legendary power."],
                        },
                    ],
                    "id": "dmg-treasure",
                },
                        {
                            "type": "section",
                            "name": "Running the Game",
                            "page": 235,
                            "entries": [
                                "Running the game means adjudicating uncertain outcomes and pacing scenes.",
                                {
                                    "type": "section",
                                    "name": "Using Ability Scores",
                                    "page": 237,
                                    "entries": [
                                        "Use ability checks and saving throws when outcomes are uncertain.",
                                        "Lingering afflictions such as {@disease Cackle Fever|DMG} can complicate those rulings.",
                                    ],
                                },
                                {
                                    "type": "section",
                                    "name": "Combat",
                                    "page": 247,
                                    "entries": [
                                        "Optional actions such as {@action Overrun|DMG} can shift how melee pressure works.",
                                        {
                                            "type": "entries",
                                            "name": "Chases",
                                            "page": 252,
                                            "entries": ["A chase adds movement pressure and complications to a pursuit scene."],
                                }
                            ],
                        },
                    ],
                    "id": "dmg-running-game",
                },
                {
                    "type": "section",
                    "name": "Dungeon Master's Workshop",
                    "page": 263,
                    "entries": [
                        "The workshop collects optional systems and creation guidance for DMs.",
                        {
                            "type": "section",
                            "name": "Combat Options",
                            "page": 270,
                            "entries": ["Optional combat rules can change how tactical play feels at the table."],
                        },
                        {
                            "type": "section",
                            "name": "Creating a Monster",
                            "page": 273,
                            "entries": ["Monster statistics can be tuned by challenge rating and role."],
                        },
                    ],
                    "id": "dmg-workshop",
                },
            ]
        },
    )
    return data_root


def build_mm_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/actions.json",
        {
            "action": [
                {
                    "name": "Help",
                    "source": "PHB",
                    "page": 192,
                    "time": [{"number": 1, "unit": "action"}],
                    "entries": ["You can lend your aid to another creature in the completion of a task."],
                },
                {
                    "name": "Hide",
                    "source": "PHB",
                    "page": 192,
                    "time": [{"number": 1, "unit": "action"}],
                    "entries": ["You make a Dexterity (Stealth) check in an attempt to conceal yourself."],
                },
            ]
        },
    )
    write_json(
        root / "data/conditionsdiseases.json",
        {
            "condition": [
                {
                    "name": "Blinded",
                    "source": "PHB",
                    "page": 290,
                    "entries": ["A blinded creature can't see."],
                },
                {
                    "name": "Charmed",
                    "source": "PHB",
                    "page": 290,
                    "entries": ["A charmed creature can't attack the charmer or target the charmer with harmful abilities."],
                },
                {
                    "name": "Frightened",
                    "source": "PHB",
                    "page": 290,
                    "entries": ["A frightened creature has disadvantage on ability checks and attack rolls while the source of its fear is in sight."],
                },
                {
                    "name": "Incapacitated",
                    "source": "PHB",
                    "page": 290,
                    "entries": ["An incapacitated creature can't take actions or reactions."],
                },
                {
                    "name": "Invisible",
                    "source": "PHB",
                    "page": 291,
                    "entries": ["An invisible creature is impossible to see without the aid of magic or a special sense."],
                },
                {
                    "name": "Paralyzed",
                    "source": "PHB",
                    "page": 291,
                    "entries": ["A paralyzed creature is incapacitated and can't move or speak."],
                },
            ],
            "disease": [],
            "status": [
                {
                    "name": "Concentration",
                    "source": "PHB",
                    "page": 203,
                    "entries": ["You can concentrate on only one spell at a time."],
                },
                {
                    "name": "Surprised",
                    "source": "PHB",
                    "page": 189,
                    "entries": ["If you're surprised, you can't move or take an action on your first turn of the combat."],
                },
            ],
        },
    )
    write_json(
        root / "data/skills.json",
        {
            "skill": [
                {
                    "name": "Athletics",
                    "source": "PHB",
                    "page": 175,
                    "ability": "str",
                    "entries": ["Your Strength check covers difficult situations you encounter while climbing, jumping, or swimming."],
                },
                {
                    "name": "Acrobatics",
                    "source": "PHB",
                    "page": 176,
                    "ability": "dex",
                    "entries": ["Your Dexterity check covers your attempt to stay on your feet in a tricky situation."],
                },
                {
                    "name": "Perception",
                    "source": "PHB",
                    "page": 178,
                    "ability": "wis",
                    "entries": ["Your Wisdom check lets you spot, hear, or otherwise detect the presence of something."],
                },
                {
                    "name": "Stealth",
                    "source": "PHB",
                    "page": 177,
                    "ability": "dex",
                    "entries": ["Your Dexterity check covers your attempt to conceal yourself."],
                },
            ]
        },
    )
    write_json(
        root / "data/senses.json",
        {
            "sense": [
                {
                    "name": "Blindsight",
                    "source": "PHB",
                    "page": 183,
                    "entries": ["A creature with blindsight can perceive its surroundings without relying on sight."],
                },
                {
                    "name": "Darkvision",
                    "source": "PHB",
                    "page": 183,
                    "entries": ["A creature with darkvision can see in dim light within a specified radius as if it were bright light."],
                },
                {
                    "name": "Tremorsense",
                    "source": "MM",
                    "page": 9,
                    "entries": ["A creature with tremorsense can detect and pinpoint the origin of vibrations within a specific radius."],
                },
                {
                    "name": "Truesight",
                    "source": "PHB",
                    "page": 183,
                    "entries": ["A creature with truesight can, out to a specific range, see in normal and magical darkness and see invisible creatures and objects."],
                },
            ]
        },
    )
    write_json(
        root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Goblin",
                    "source": "MM",
                    "page": 166,
                    "size": ["S"],
                    "type": "humanoid",
                    "alignment": ["N", "E"],
                    "ac": [{"ac": 15, "from": ["leather armor", "shield"]}],
                    "hp": {"average": 7, "formula": "2d6"},
                    "speed": {"walk": 30},
                    "str": 8,
                    "dex": 14,
                    "con": 10,
                    "int": 10,
                    "wis": 8,
                    "cha": 8,
                    "skill": {"stealth": "+6"},
                    "senses": ["darkvision 60 ft."],
                    "passive": 9,
                    "languages": ["Common", "Goblin"],
                    "cr": "1/4",
                    "trait": [
                        {
                            "name": "Nimble Escape",
                            "entries": ["The goblin can take the Disengage or Hide action as a bonus action."],
                        }
                    ],
                    "action": [
                        {
                            "name": "Scimitar",
                            "entries": ["{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."],
                        }
                    ],
                },
                {
                    "name": "Guard",
                    "source": "MM",
                    "page": 347,
                    "size": ["M"],
                    "type": "humanoid",
                    "alignment": ["L", "N"],
                    "ac": [{"ac": 16, "from": ["chain shirt", "shield"]}],
                    "hp": {"average": 11, "formula": "2d8 + 2"},
                    "speed": {"walk": 30},
                    "str": 13,
                    "dex": 12,
                    "con": 12,
                    "int": 10,
                    "wis": 11,
                    "cha": 10,
                    "skill": {"perception": "+2"},
                    "passive": 12,
                    "languages": ["Common"],
                    "cr": "1/8",
                    "action": [
                        {
                            "name": "Spear",
                            "entries": ["{@atk mw,rw} {@hit 3} to hit, reach 5 ft. or range 20/60 ft., one target. {@h}4 ({@damage 1d6 + 1}) piercing damage."],
                        }
                    ],
                },
                {
                    "name": "Veteran",
                    "source": "MM",
                    "page": 350,
                    "size": ["M"],
                    "type": "humanoid",
                    "alignment": ["N"],
                    "ac": [{"ac": 17, "from": ["splint"]}],
                    "hp": {"average": 58, "formula": "9d8 + 18"},
                    "speed": {"walk": 30},
                    "str": 16,
                    "dex": 13,
                    "con": 14,
                    "int": 10,
                    "wis": 11,
                    "cha": 10,
                    "skill": {"athletics": "+5", "perception": "+2"},
                    "passive": 12,
                    "languages": ["Common"],
                    "cr": "3",
                    "action": [
                        {
                            "name": "Longsword",
                            "entries": ["{@atk mw} {@hit 5} to hit, reach 5 ft., one target. {@h}7 ({@damage 1d8 + 3}) slashing damage."],
                        }
                    ],
                },
            ]
        },
    )
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Monster Manual (2014)",
                    "id": "MM",
                    "source": "MM",
                    "contents": [
                        {
                            "name": "Introduction",
                            "headers": [
                                "How to Use This Book",
                                "What Is a Monster?",
                                "Statistics",
                                "Legendary Creatures",
                                "Shadow Dragon Template",
                                "Half-Dragon Template",
                                "Spore Servant Template",
                            ],
                        },
                        {
                            "name": "Nonplayer Characters",
                            "headers": [
                                "Customizing NPCs",
                                "NPC Descriptions",
                            ],
                            "ordinal": {"type": "appendix", "identifier": "B"},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-mm.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Introduction",
                    "page": 4,
                    "entries": [
                        {
                            "type": "section",
                            "name": "How to Use This Book",
                            "page": 4,
                            "entries": ["Use the Monster Manual to populate adventures with memorable creatures."],
                        },
                        {
                            "type": "section",
                            "name": "Statistics",
                            "page": 6,
                            "entries": [
                                "A monster's statistics provide the essential information needed to run it.",
                                {
                                    "type": "entries",
                                    "name": "Size",
                                    "page": 6,
                                    "entries": [
                                        "A monster can be Tiny, Small, Medium, Large, Huge, or Gargantuan.",
                                        {
                                            "type": "table",
                                            "caption": "Size Categories",
                                            "colLabels": ["Size", "Space", "Examples"],
                                            "rows": [
                                                ["Small", "5 by 5 ft.", "{@creature Goblin}"],
                                                ["Medium", "5 by 5 ft.", "{@creature Guard}"],
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Type",
                                    "page": 6,
                                    "entries": [
                                        "A monster's type speaks to its fundamental nature.",
                                        {
                                            "type": "entries",
                                            "name": "Tags",
                                            "page": 7,
                                            "entries": ["Tags provide extra categorization for certain creatures."],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Speed",
                                    "page": 8,
                                    "entries": [
                                        "A monster's speed tells you how far it can move on its turn.",
                                        {
                                            "type": "entries",
                                            "name": "Burrow",
                                            "page": 8,
                                            "entries": ["A burrowing creature can move through sand, earth, mud, or ice."],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Skills",
                                    "page": 8,
                                    "entries": [
                                        "A perceptive scout might have bonuses to Wisdom ({@skill Perception}) and Dexterity ({@skill Stealth}) checks.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Senses",
                                    "page": 8,
                                    "entries": [
                                        "The Senses entry notes a monster's passive Wisdom ({@skill Perception}) score, as well as any special senses the monster might have.",
                                        {
                                            "type": "entries",
                                            "name": "Blindsight",
                                            "page": 8,
                                            "entries": [
                                                "A monster with {@sense blindsight} can perceive its surroundings without relying on sight.",
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Darkvision",
                                            "page": 9,
                                            "entries": ["A monster with {@sense darkvision} can see in the dark within a specific radius."],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Tremorsense",
                                            "page": 9,
                                            "entries": [
                                                "A monster with {@sense tremorsense|MM} can detect and pinpoint the origin of vibrations within a specific radius.",
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Truesight",
                                            "page": 9,
                                            "entries": [
                                                "A monster with {@sense truesight} can see {@condition invisible} creatures and objects within a specific range.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Challenge",
                                    "page": 9,
                                    "entries": [
                                        "Challenge summarizes a monster's overall threat.",
                                        {
                                            "type": "entries",
                                            "name": "Experience Points",
                                            "page": 9,
                                            "entries": ["Challenge Rating maps to an XP award."],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Equipment",
                                    "page": 11,
                                    "entries": ["Equipment carried and used by a monster is noted here."],
                                },
                            ],
                            "id": "mm-statistics",
                        },
                        {
                            "type": "section",
                            "name": "Legendary Creatures",
                            "page": 11,
                            "entries": [
                                "Legendary creatures can take special actions outside their turns.",
                                {
                                    "type": "entries",
                                    "name": "Legendary Actions",
                                    "page": 11,
                                    "entries": [
                                        "A legendary creature can act outside its turn through legendary actions. It can't use them while {@condition incapacitated} or otherwise unable to take actions. If {@status surprised}, it can't use them until after its first turn in the combat."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "A Legendary Creature's Lair",
                                    "page": 11,
                                    "entries": [
                                        "Some legendary creatures reshape the places where they dwell.",
                                        {
                                            "type": "entries",
                                            "name": "Lair Actions",
                                            "page": 11,
                                            "entries": ["Lair actions occur on initiative count 20."],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Regional Effects",
                                            "page": 11,
                                            "entries": [
                                                "Regional effects reflect a legendary creature's magical presence."
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Shadow Dragon Template",
                            "page": 84,
                            "entries": [
                                "Only a true dragon can transform into a shadow dragon, and only if it is born in the Shadowfell or remains there for several years.",
                                {
                                    "type": "entries",
                                    "name": "Damage Resistances",
                                    "page": 85,
                                    "entries": ["The dragon has resistance to necrotic damage."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Skills",
                                    "page": 85,
                                    "entries": [
                                        "The dragon's proficiency bonus is doubled for its Dexterity ({@skill Stealth}) checks."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Living Shadow",
                                    "page": 85,
                                    "entries": [
                                        "While in dim light or darkness, the dragon can take the {@action Hide} action as a bonus action.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Shadow Breath",
                                    "page": 85,
                                    "entries": [
                                        "The dragon's breath weapon deals necrotic damage instead of its normal damage type.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Half-Dragon Template",
                            "page": 180,
                            "entries": [
                                "A beast, humanoid, giant, or monstrosity can become a half-dragon.",
                                {
                                    "type": "entries",
                                    "name": "Challenge",
                                    "page": 180,
                                    "entries": [
                                        "Use the template on a creature that meets the optional prerequisite to avoid recalculating challenge."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Senses",
                                    "page": 180,
                                    "entries": [
                                        "The half-dragon gains {@sense blindsight} with a radius of 10 feet and {@sense darkvision} with a radius of 60 feet."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Resistances",
                                    "page": 180,
                                    "entries": [
                                        "The half-dragon gains resistance based on the color of its draconic ancestry.",
                                        {
                                            "type": "table",
                                            "colLabels": ["Color", "Damage Resistance"],
                                            "rows": [
                                                ["Black or copper", "Acid"],
                                                ["Blue or bronze", "Lightning"],
                                                ["Brass, gold, or red", "Fire"],
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Languages",
                                    "page": 180,
                                    "entries": [
                                        "The half-dragon speaks Draconic in addition to any other languages it knows."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "New Action: Breath Weapon",
                                    "page": 180,
                                    "entries": [
                                        "The half-dragon has the breath weapon of its dragon half.",
                                        {
                                            "type": "table",
                                            "colLabels": ["Size", "Breath Weapon", "Optional Prerequisite"],
                                            "rows": [
                                                ["Large or smaller", "As a wyrmling", "Challenge 2 or higher"],
                                                ["Huge", "As a young dragon", "Challenge 7 or higher"],
                                                ["Gargantuan", "As an adult dragon", "Challenge 8 or higher"],
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Spore Servant Template",
                            "page": 230,
                            "entries": [
                                "A spore servant is any Large or smaller creature brought back to life by the animating spores of a myconid sovereign.",
                                {
                                    "type": "entries",
                                    "name": "Retained Characteristics",
                                    "page": 230,
                                    "entries": [
                                        "The servant retains its Armor Class, hit points, Hit Dice, Strength, Dexterity, Constitution, vulnerabilities, resistances, and immunities."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Lost Characteristics",
                                    "page": 230,
                                    "entries": [
                                        "The servant loses its original saving throw and skill bonuses, special senses, and special traits."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Type",
                                    "page": 230,
                                    "entries": ["The servant's type is plant, and it loses any tags."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Alignment",
                                    "page": 230,
                                    "entries": ["The servant is unaligned."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Speed",
                                    "page": 230,
                                    "entries": ["Reduce all the servant's speeds by 10 feet, to a minimum of 5 feet."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Ability Scores",
                                    "page": 230,
                                    "entries": [
                                        "The servant's ability scores change as follows: Int 2 (-4), Wis 6 (-2), Cha 1 (-5)."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Senses",
                                    "page": 230,
                                    "entries": [
                                        "The servant has {@sense blindsight} with a radius of 30 feet, and it is blind beyond this radius."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Condition Immunities",
                                    "page": 230,
                                    "entries": [
                                        "The servant can't be {@condition blinded}, {@condition charmed}, {@condition frightened}, or {@condition paralyzed}."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Languages",
                                    "page": 230,
                                    "entries": [
                                        "The servant loses all known languages, but it responds to orders given to it by myconids using rapport spores."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Attacks",
                                    "page": 230,
                                    "entries": [
                                        "If the servant has no other means of dealing damage, it can use its fists or limbs to make unarmed strikes."
                                    ],
                                },
                            ],
                        },
                    ],
                    "id": "mm-introduction",
                },
                {
                    "type": "section",
                    "name": "Appendix B: Nonplayer Characters",
                    "page": 342,
                    "entries": [
                        "This appendix contains statistics for humanoid nonplayer characters that adventurers might encounter during a campaign.",
                        {
                            "type": "entries",
                            "name": "Customizing NPCs",
                            "page": 342,
                            "entries": [
                                "There are many easy ways to customize the NPCs in this appendix for a home campaign.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@creature Guard}",
                                        "{@creature Veteran}",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Racial Traits",
                                    "page": 342,
                                    "entries": [
                                        "You can add racial traits to an NPC without changing its challenge rating.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Spell Swaps",
                                    "page": 342,
                                    "entries": [
                                        "Swap a spell on an NPC's spell list with another spell of the same level from the same spell list.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Armor and Weapon Swaps",
                                    "page": 342,
                                    "entries": [
                                        "You can upgrade or downgrade an NPC's armor, or swap weapons, and adjust Armor Class and attack damage accordingly.",
                                    ],
                                },
                            ],
                            "id": "mm-customizing-npcs",
                        },
                        {
                            "type": "entries",
                            "name": "NPC Descriptions",
                            "page": 343,
                            "entries": [
                                "Use these stat blocks as the basis for guards, sages, priests, assassins, and other recurring characters.",
                            ],
                        },
                    ],
                    "id": "mm-appendix-b-npcs",
                }
            ]
        },
    )
    return root


def build_vgm_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/races.json",
        {
            "race": [
                {"name": "Aasimar", "source": "VGM", "page": 104, "entries": ["Celestial-touched wanderers."]},
                {"name": "Firbolg", "source": "VGM", "page": 107, "entries": ["Reclusive forest guardians."]},
                {"name": "Goliath", "source": "VGM", "page": 108, "entries": ["Mountain-dwelling competitors."]},
                {"name": "Kenku", "source": "VGM", "page": 109, "entries": ["Cursed birdfolk mimics."]},
                {"name": "Lizardfolk", "source": "VGM", "page": 111, "entries": ["Pragmatic reptilian hunters."]},
                {"name": "Tabaxi", "source": "VGM", "page": 113, "entries": ["Curious cat folk explorers."]},
                {"name": "Triton", "source": "VGM", "page": 115, "entries": ["Guardians from the ocean depths."]},
                {"name": "Bugbear", "source": "VGM", "page": 119, "entries": ["A monstrous adventurer option."]},
                {"name": "Goblin", "source": "VGM", "page": 119, "entries": ["A monstrous adventurer option."]},
                {"name": "Hobgoblin", "source": "VGM", "page": 119, "entries": ["A monstrous adventurer option."]},
                {"name": "Kobold", "source": "VGM", "page": 119, "entries": ["A monstrous adventurer option."]},
                {"name": "Orc", "source": "VGM", "page": 120, "entries": ["A monstrous adventurer option."]},
                {
                    "name": "Yuan-ti Pureblood",
                    "source": "VGM",
                    "page": 120,
                    "entries": ["A monstrous adventurer option."],
                },
            ],
            "subrace": [
                {
                    "name": "Protector",
                    "source": "VGM",
                    "raceName": "Aasimar",
                    "raceSource": "VGM",
                    "page": 105,
                    "entries": ["Protector aasimar are charged with guarding the weak."],
                },
                {
                    "name": "Scourge",
                    "source": "VGM",
                    "raceName": "Aasimar",
                    "raceSource": "VGM",
                    "page": 105,
                    "entries": ["Scourge aasimar blaze with divine fury."],
                },
                {
                    "name": "Fallen",
                    "source": "VGM",
                    "raceName": "Aasimar",
                    "raceSource": "VGM",
                    "page": 105,
                    "entries": ["Fallen aasimar carry a shadowed celestial spark."],
                },
            ],
        },
    )
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Volo's Guide to Monsters",
                    "id": "VGM",
                    "source": "VGM",
                    "contents": [
                        {
                            "name": "Character Races",
                            "headers": ["Height and Weight"],
                            "ordinal": {"type": "chapter", "identifier": 2},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-vgm.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Character Races",
                    "page": 103,
                    "entries": [
                        "This chapter presents distinctive race options from Volo's Guide to Monsters.",
                        "It also includes monstrous character options for campaigns that want them.",
                        {
                            "type": "section",
                            "name": "Height and Weight",
                            "page": 120,
                            "entries": [
                                "You can determine a character's size with the Random Height and Weight table.",
                                {
                                    "type": "table",
                                    "colLabels": [
                                        "Race",
                                        "Base Height",
                                        "Base Weight",
                                        "Height Modifier",
                                        "Weight Modifier",
                                    ],
                                    "colStyles": [
                                        "col-4",
                                        "col-2",
                                        "col-2",
                                        "col-2",
                                        "col-2",
                                    ],
                                    "rows": [
                                        ["Aasimar", "4'8\"", "110 lb.", "+{@dice 2d10}", "Ã— ({@dice 2d4}) lb."],
                                        ["{@race Firbolg|VGM}", "6'2\"", "175 lb.", "+{@dice 2d12}", "Ã— ({@dice 2d6}) lb."],
                                        ["{@race Triton|VGM}", "4'6\"", "90 lb.", "+{@dice 2d10}", "Ã— ({@dice 2d4}) lb."],
                                        ["{@race Bugbear|VGM}", "6'0\"", "200 lb.", "+{@dice 2d12}", "Ã— ({@dice 2d6}) lb."],
                                        [
                                            "{@race Yuan-ti Pureblood|VGM}",
                                            "4'8\"",
                                            "110 lb.",
                                            "+{@dice 2d10}",
                                            "Ã— ({@dice 2d4}) lb.",
                                        ],
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/fluff-races.json",
        {
            "_meta": {},
            "raceFluff": [
                {
                    "name": "Aasimar",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Aasimar bear within their souls the light of the heavens.",
                                {
                                    "type": "entries",
                                    "name": "Celestial Champions",
                                    "page": 104,
                                    "entries": ["Aasimar are placed in the world to serve as guardians of law and good."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Aasimar Guides",
                                    "page": 105,
                                    "entries": ["Each aasimar can count a celestial being as a guide."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Aasimar (Protector)",
                    "source": "VGM",
                    "_copy": {
                        "name": "Aasimar",
                        "source": "VGM",
                        "_mod": {
                            "entries": {
                                "mode": "prependArr",
                                "items": {
                                    "type": "section",
                                    "entries": [
                                        {
                                            "type": "entries",
                                            "entries": ["Protector aasimar stand vigilant against the darkness."],
                                        }
                                    ],
                                },
                            }
                        },
                    },
                },
                {
                    "name": "Aasimar (Scourge)",
                    "source": "VGM",
                    "_copy": {
                        "name": "Aasimar",
                        "source": "VGM",
                        "_mod": {
                            "entries": {
                                "mode": "prependArr",
                                "items": {
                                    "type": "section",
                                    "entries": [
                                        {
                                            "type": "entries",
                                            "entries": ["Scourge aasimar blaze with divine energy that seeks out evil."],
                                        }
                                    ],
                                },
                            }
                        },
                    },
                },
                {
                    "name": "Aasimar (Fallen)",
                    "source": "VGM",
                    "_copy": {
                        "name": "Aasimar",
                        "source": "VGM",
                        "_mod": {
                            "entries": {
                                "mode": "prependArr",
                                "items": {
                                    "type": "section",
                                    "entries": [
                                        {
                                            "type": "entries",
                                            "entries": ["A fallen aasimar's inner light has been replaced by shadow."],
                                        }
                                    ],
                                },
                            }
                        },
                    },
                },
                {
                    "name": "Firbolg",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Firbolgs are reclusive forest folk who prefer peaceful methods.",
                                {
                                    "type": "entries",
                                    "name": "Outcast Adventurers",
                                    "page": 107,
                                    "entries": ["The Firbolg Adventurers table can inspire a reason to leave home."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Goliath",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Goliaths dwell among the highest mountain peaks.",
                                {
                                    "type": "entries",
                                    "name": "Competition and Conflict",
                                    "page": 108,
                                    "entries": ["Goliaths improve themselves by testing their limits."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Kenku",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Kenku are wingless birdfolk cursed for an ancient betrayal.",
                                {
                                    "type": "entries",
                                    "name": "Kenku Adventurers",
                                    "page": 109,
                                    "entries": ["Kenku adventurers often strike out after a flock suffers heavy losses."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Lizardfolk",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Lizardfolk venture from their swamp homes in search of treasure and glory.",
                                {
                                    "type": "entries",
                                    "name": "Lizardfolk Names",
                                    "page": 111,
                                    "entries": ["Lizardfolk names come from notable deeds and the Draconic language."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Tabaxi",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Tabaxi journey far from home in search of stories and curiosities.",
                                {
                                    "type": "entries",
                                    "name": "Wanderlust",
                                    "page": 113,
                                    "entries": ["Curiosity drives most tabaxi found outside their homeland."],
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "Triton",
                    "source": "VGM",
                    "entries": [
                        {
                            "type": "entries",
                            "entries": [
                                "Tritons guard the ocean depths and battle threats before they reach the land.",
                                {
                                    "type": "entries",
                                    "name": "Triton Society",
                                    "page": 115,
                                    "entries": ["Tritons value duty, order, and service to the wider world."],
                                },
                            ],
                        }
                    ],
                },
            ],
            "raceFluffMeta": {},
            "monstrous": {
                "name": "Monstrous Adventurers",
                "type": "section",
                "entries": [
                    "In some campaigns, humanoids normally regarded as sinister threats can emerge to adventure alongside humans and other folk.",
                    {
                        "type": "entries",
                        "name": "Why a Monstrous Character?",
                        "page": 118,
                        "entries": ["A monstrous character gives a player a chance to take on an unusual challenge."],
                    },
                    {
                        "type": "entries",
                        "name": "Rare or Mundane?",
                        "page": 118,
                        "entries": ["Consider how common orc, goblin, and similar adventurers are in your setting."],
                    },
                    {
                        "type": "entries",
                        "name": "Outcast or Ambassador?",
                        "page": 118,
                        "entries": ["Consider how a monstrous character's native culture views the character."],
                    },
                    {
                        "type": "entries",
                        "name": "Friends or Enemies?",
                        "page": 119,
                        "entries": ["Figure out what special ties the character has to other party members."],
                    },
                ],
            },
        },
    )
    return data_root


def build_mtf_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/races.json",
        {
            "race": [
                {
                    "name": "Elf",
                    "source": "PHB",
                    "page": 23,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"dex": 2}],
                    "entries": [
                        {
                            "name": "Keen Senses",
                            "type": "entries",
                            "entries": ["You have proficiency in the Perception skill."],
                        }
                    ],
                },
                {
                    "name": "Dwarf",
                    "source": "PHB",
                    "page": 18,
                    "size": ["M"],
                    "speed": {"walk": 25},
                    "ability": [{"con": 2}],
                    "entries": [
                        {
                            "name": "Darkvision",
                            "type": "entries",
                            "entries": ["Accustomed to life underground, you have superior vision in dark and dim conditions."],
                        }
                    ],
                },
                {
                    "name": "Gnome",
                    "source": "PHB",
                    "page": 35,
                    "size": ["S"],
                    "speed": {"walk": 25},
                    "ability": [{"int": 2}],
                    "entries": [
                        {
                            "name": "Gnome Cunning",
                            "type": "entries",
                            "entries": ["You have advantage on all Intelligence, Wisdom, and Charisma saving throws against magic."],
                        }
                    ],
                },
                {
                    "name": "Tiefling",
                    "source": "PHB",
                    "page": 42,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"cha": 2}],
                    "entries": [
                        {
                            "name": "Hellish Resistance",
                            "type": "entries",
                            "entries": ["You have resistance to fire damage."],
                        }
                    ],
                },
                {
                    "name": "Gith",
                    "source": "MTF",
                    "page": 96,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Decadent Mastery",
                            "type": "entries",
                            "entries": ["You learn one language of your choice, and you gain proficiency with one skill or tool of your choice."],
                        }
                    ],
                }
            ],
            "subrace": [
                {
                    "name": "Eladrin",
                    "source": "MTF",
                    "raceName": "Elf",
                    "raceSource": "PHB",
                    "page": 61,
                    "ability": [{"cha": 1}],
                    "entries": [
                        {
                            "name": "Fey Step",
                            "type": "entries",
                            "entries": ["You can teleport a short distance in a shimmer of Feywild magic."],
                        }
                    ],
                },
                {
                    "name": "Sea",
                    "source": "MTF",
                    "raceName": "Elf",
                    "raceSource": "PHB",
                    "page": 62,
                    "ability": [{"con": 1}],
                    "entries": [
                        {
                            "name": "Child of the Sea",
                            "type": "entries",
                            "entries": ["Sea elves can breathe water and swim with uncanny grace."],
                        }
                    ],
                },
                {
                    "name": "Shadar-kai",
                    "source": "MTF",
                    "raceName": "Elf",
                    "raceSource": "PHB",
                    "page": 62,
                    "ability": [{"con": 1}],
                    "entries": [
                        {
                            "name": "Blessing of the Raven Queen",
                            "type": "entries",
                            "entries": ["You can step through the shadows under the Raven Queen's blessing."],
                        }
                    ],
                },
                {
                    "name": "Duergar",
                    "source": "MTF",
                    "raceName": "Dwarf",
                    "raceSource": "PHB",
                    "page": 81,
                    "ability": [{"str": 1}],
                    "entries": [
                        {
                            "name": "Duergar Resilience",
                            "type": "entries",
                            "entries": ["You have advantage on saving throws against illusions and against being charmed or paralyzed."],
                        }
                    ],
                },
                {
                    "name": "Deep",
                    "source": "MTF",
                    "raceName": "Gnome",
                    "raceSource": "PHB",
                    "page": 113,
                    "ability": [{"dex": 1}],
                    "entries": [
                        {
                            "name": "Stone Camouflage",
                            "type": "entries",
                            "entries": ["You have advantage on Dexterity (Stealth) checks to hide in rocky terrain."],
                        }
                    ],
                },
                {
                    "name": "Asmodeus",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 21,
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Cania",
                            "type": "entries",
                            "entries": ["You know the thaumaturgy cantrip and channel infernal power through Cania."],
                        }
                    ],
                },
                {
                    "name": "Baalzebul",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 21,
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Maladomini",
                            "type": "entries",
                            "entries": ["Baalzebul tieflings inherit a silver tongue and subtle infernal magic."],
                        }
                    ],
                },
                {
                    "name": "Dispater",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 21,
                    "ability": [{"dex": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Dis",
                            "type": "entries",
                            "entries": ["Dispater tieflings favor secrets, steel, and keen infernal precision."],
                        }
                    ],
                },
                {
                    "name": "Fierna",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 21,
                    "ability": [{"wis": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Phlegethos",
                            "type": "entries",
                            "entries": ["Fierna tieflings are known for beguiling speech and flames touched by desire."],
                        }
                    ],
                },
                {
                    "name": "Glasya",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 22,
                    "ability": [{"dex": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Malbolge",
                            "type": "entries",
                            "entries": ["Glasya tieflings slip through locks, lies, and shadows with infernal ease."],
                        }
                    ],
                },
                {
                    "name": "Levistus",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 22,
                    "ability": [{"con": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Stygia",
                            "type": "entries",
                            "entries": ["Levistus tieflings endure with cold poise and frozen infernal resilience."],
                        }
                    ],
                },
                {
                    "name": "Mammon",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 22,
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Minauros",
                            "type": "entries",
                            "entries": ["Mammon tieflings draw on greed, guile, and infernal command over matter."],
                        }
                    ],
                },
                {
                    "name": "Mephistopheles",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 23,
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Cania",
                            "type": "entries",
                            "entries": ["Mephistopheles tieflings wield hellfire with a scholar's taste for arcana."],
                        }
                    ],
                },
                {
                    "name": "Zariel",
                    "source": "MTF",
                    "raceName": "Tiefling",
                    "raceSource": "PHB",
                    "page": 23,
                    "ability": [{"str": 1}],
                    "entries": [
                        {
                            "name": "Legacy of Avernus",
                            "type": "entries",
                            "entries": ["Zariel tieflings bear martial fury and the battlefield fire of Avernus."],
                        }
                    ],
                },
                {
                    "name": "Githyanki",
                    "source": "MTF",
                    "raceName": "Gith",
                    "raceSource": "MTF",
                    "page": 96,
                    "ability": [{"str": 2}],
                    "entries": [
                        {
                            "name": "Martial Prodigy",
                            "type": "entries",
                            "entries": ["You are proficient with light and medium armor and with shortswords, longswords, and greatswords."],
                        }
                    ],
                },
                {
                    "name": "Githzerai",
                    "source": "MTF",
                    "raceName": "Gith",
                    "raceSource": "MTF",
                    "page": 96,
                    "ability": [{"wis": 2}],
                    "entries": [
                        {
                            "name": "Mental Discipline",
                            "type": "entries",
                            "entries": ["Your innate psychic defenses grant you advantage on saving throws against the charmed and frightened conditions."],
                        }
                    ],
                },
            ],
        },
    )
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Mordenkainen's Tome of Foes",
                    "id": "MTF",
                    "source": "MTF",
                    "contents": [
                        {
                            "name": "The Blood War",
                            "headers": [
                                "Diabolical Cults",
                                "Tiefling Subraces",
                                "Demonic Boons",
                                "Fiendish Cults",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 1},
                        },
                        {
                            "name": "Elves",
                            "headers": ["Elf Subraces"],
                            "ordinal": {"type": "chapter", "identifier": 2},
                        },
                        {
                            "name": "Dwarves and Duergar",
                            "headers": ["Duergar Characters"],
                            "ordinal": {"type": "chapter", "identifier": 3},
                        },
                        {
                            "name": "Gith and Their Endless War",
                            "headers": ["Gith Characters"],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        },
                        {
                            "name": "Halflings and Gnomes",
                            "headers": ["Deep Gnome Characters"],
                            "ordinal": {"type": "chapter", "identifier": 5},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-mtf.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "The Blood War",
                    "page": 11,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Diabolical Cults",
                            "page": 18,
                            "entries": [
                                "Cults dedicated to infernal beings are the foes of adventurers throughout the D&D multiverse.",
                                "Every archdevil attracts a certain type of person based on the gifts the devil offers.",
                                "Each description also includes a list of signature spells associated with the cult.",
                                {
                                    "type": "entries",
                                    "name": "Cult of Glasya",
                                    "page": 19,
                                    "entries": [
                                        "Followers of Glasya delight in secrets, smuggling, and elegant cruelty.",
                                        {
                                            "type": "list",
                                            "items": [
                                                "Typical Cultist: {@creature Spy|MM}",
                                                "Signature Spells: disguise self, invisibility",
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Tiefling Subraces",
                            "page": 21,
                            "entries": [
                                "At the DM's option, you can create a tiefling character who has a special link to one of the Lords of the Nine Hells.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@race Tiefling (Asmodeus)|MTF}",
                                        "{@race Tiefling (Baalzebul)|MTF}",
                                        "{@race Tiefling (Dispater)|MTF}",
                                        "{@race Tiefling (Fierna)|MTF}",
                                        "{@race Tiefling (Glasya)|MTF}",
                                        "{@race Tiefling (Levistus)|MTF}",
                                        "{@race Tiefling (Mammon)|MTF}",
                                        "{@race Tiefling (Mephistopheles)|MTF}",
                                        "{@race Tiefling (Zariel)|MTF}",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Demonic Boons",
                            "page": 30,
                            "entries": [
                                "Wicked folk who seek power from demons are scattered across the multiverse.",
                                "The following entries outline boons that a DM can grant to monsters and NPCs dedicated to a particular demon lord.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@boon Demonic Boon of Baphomet}",
                                        "{@boon Demonic Boon of Demogorgon}",
                                        "{@boon Demonic Boon of Fraz-Urb'luu}",
                                        "{@boon Demonic Boon of Graz'zt}",
                                        "{@boon Demonic Boon of Juiblex}",
                                        "{@boon Demonic Boon of Orcus}",
                                        "{@boon Demonic Boon of Yeenoghu}",
                                        "{@boon Demonic Boon of Zuggtmoy}",
                                    ],
                                },
                                "Boons from demons are fickle gifts that remain only as long as the demon is pleased.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Fiendish Cults",
                            "page": 34,
                            "entries": [
                                "The following tables can be used to generate random cults dedicated to fiends.",
                                {
                                    "type": "entries",
                                    "name": "Cult Goals",
                                    "page": 34,
                                    "entries": [
                                        {
                                            "type": "table",
                                            "colLabels": ["d4", "Goal"],
                                            "rows": [
                                                ["1", "Free a bound fiend."],
                                                ["2", "Spread infernal corruption through a city."],
                                                ["3", "Recover a relic tied to the Lower Planes."],
                                                ["4", "Open a gate to the Abyss or the Nine Hells."],
                                            ],
                                        }
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Elves",
                    "page": 35,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Elf Subraces",
                            "page": 61,
                            "entries": [
                                "At the DM's discretion, you have access to more subraces for elf characters, in addition to the subraces in the Player's Handbook.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@race Elf (Eladrin)|MTF}",
                                        "{@race Elf (Sea)|MTF}",
                                        "{@race Elf (Shadar-kai)|MTF}",
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Dwarves and Duergar",
                    "page": 65,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Duergar Characters",
                            "page": 81,
                            "entries": [
                                "Those duergar who become adventurers are almost invariably exiles from their society.",
                                "At the DM's discretion, you can play a duergar character. When you choose the subrace of your dwarf, you can choose duergar, using the following rules to create your character.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@race Dwarf (Duergar)|MTF}",
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Gith and Their Endless War",
                    "page": 85,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Gith Characters",
                            "page": 96,
                            "entries": [
                                "At the DM's option, you can create a gith character, using the following traits.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@race Gith (Githyanki)|MTF}",
                                        "{@race Gith (Githzerai)|MTF}",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Gith Random Height and Weight",
                                    "page": 96,
                                    "entries": [
                                        {
                                            "type": "table",
                                            "colLabels": [
                                                "Base Height",
                                                "Height Modifier",
                                                "Base Weight",
                                                "Weight Modifier",
                                            ],
                                            "rows": [
                                                ["5 ft.", "+2d12 in.", "100 lb.", "\u00d7 (2d6) lb."],
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Halflings and Gnomes",
                    "page": 113,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Deep Gnome Characters",
                            "page": 113,
                            "entries": [
                                "At the DM's discretion, you can play a deep gnome character. When you choose the subrace of your gnome, you can choose deep gnome, using the following rules to create your character.",
                                {
                                    "type": "list",
                                    "items": [
                                        "{@race Gnome (Deep)|MTF}",
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )
    return data_root


def build_egw_dunamis_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Explorer's Guide to Wildemount",
                    "id": "EGW",
                    "source": "EGW",
                    "contents": [
                        {
                            "name": "Character Options",
                            "headers": ["Hollow One", "Dunamis and Dunamancy", "Heroic Chronicle"],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-egw.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Character Options",
                    "page": 168,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Hollow One",
                            "page": 181,
                            "entries": [
                                (
                                    "The eastern coast of Xhorhas, known to the Kryn as Blightshore, "
                                    "is a land scarred by evil magic. Among the creations of that foul "
                                    "place are the Hollow Ones."
                                ),
                                (
                                    "The transition from life to becoming a Hollow One affects "
                                    "different people to different degrees."
                                ),
                                {
                                    "type": "entries",
                                    "name": "Supernatural Gift: Hollow One",
                                    "page": 182,
                                    "entries": [
                                        (
                                            "The Dungeon Master can allow a character created in a "
                                            "Wildemount campaign to return as a Hollow One."
                                        ),
                                        {
                                            "type": "statblock",
                                            "tag": "charoption",
                                            "source": "EGW",
                                            "name": "Hollow One",
                                            "page": 182,
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Subclasses",
                            "page": 182,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Dunamis and Dunamancy",
                                    "page": 182,
                                    "entries": [
                                        (
                                            "Dunamis studies possibility, probability, and the unseen force "
                                            "that can bend time and gravity."
                                        ),
                                        {
                                            "type": "entries",
                                            "name": "Beyond the Kryn Dynasty",
                                            "page": 182,
                                            "entries": [
                                                (
                                                    "Although the Kryn Dynasty is the best-known home of "
                                                    "dunamancy, its techniques can spread through study, "
                                                    "espionage, or magical experimentation."
                                                )
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Dunamis as a Martial Focus",
                                            "page": 183,
                                            "entries": [
                                                (
                                                    "Warriors and mages alike can turn dunamis toward "
                                                    "mobility, battlefield control, and momentary glimpses of "
                                                    "alternate futures."
                                                )
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Heroic Chronicle",
                                    "page": 196,
                                    "entries": [
                                        (
                                            "The heroic chronicle system lets players and Dungeon Masters "
                                            "build a backstory rooted in Wildemount."
                                        )
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )
    return data_root


def build_egw_character_option_wrapper_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    wrapper_titles = [
        "Elves",
        "Halflings",
        "Dragonborn",
        "Orcs and Half-Orcs",
        "Hollow One",
        "Dunamis and Dunamancy",
        "Fighter",
        "Wizard",
        "Dunamancy Spells",
        "Spell Descriptions",
        "Heroic Chronicle",
        "Backgrounds",
    ]

    def section(name: str, page: int, entries: list[object]) -> dict[str, object]:
        return {"type": "section", "name": name, "page": page, "entries": entries}

    def entries_block(name: str, page: int, entries: list[object]) -> dict[str, object]:
        return {"type": "entries", "name": name, "page": page, "entries": entries}

    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Explorer's Guide to Wildemount",
                    "id": "EGW",
                    "source": "EGW",
                    "contents": [
                        {
                            "name": "Character Options",
                            "headers": wrapper_titles,
                            "ordinal": {"type": "chapter", "identifier": 4},
                        }
                    ],
                }
            ]
        },
    )

    write_json(
        root / "data/book/book-egw.json",
        {
            "data": [
                section(
                    "Character Options",
                    161,
                    [
                        section(
                            "Elves",
                            162,
                            [
                                "Wildemount's elves include secretive pallid communities hidden among the Biting North.",
                                entries_block(
                                    "Elf Subraces",
                                    163,
                                    [
                                        "The following elf heritage appears in this source.",
                                        {"type": "list", "items": ["{@race Elf (Pallid)|EGW}"]},
                                    ],
                                ),
                            ],
                        ),
                        section(
                            "Halflings",
                            164,
                            [
                                "Lotusden clans guard the Vermaloc Wildwood and move with the forest itself.",
                                entries_block(
                                    "Halfling Subraces",
                                    164,
                                    [
                                        "Wildemount presents the following halfling lineage.",
                                        {"type": "list", "items": ["{@race halfling (Lotusden)|EGW|Lotusden halfling}"]},
                                    ],
                                ),
                            ],
                        ),
                        section(
                            "Dragonborn",
                            168,
                            [
                                "Dragonborn in Wildemount carry lineages shaped by draconic empires and scattered exile.",
                                entries_block(
                                    "Dragonborn Variants",
                                    168,
                                    [
                                        "Choose one of the following draconic bloodlines.",
                                        {
                                            "type": "list",
                                            "items": [
                                                "{@race Dragonborn (Draconblood)|EGW}",
                                                "{@race Dragonborn (Ravenite)|EGW}",
                                            ],
                                        },
                                    ],
                                ),
                            ],
                        ),
                        section(
                            "Orcs and Half-Orcs",
                            177,
                            [
                                "The wastes of Xhorhas and the fringes of the empire both make room for fierce orc traditions.",
                                entries_block(
                                    "Orc Traits",
                                    178,
                                    [
                                        "Use the following racial traits for an orc character in Wildemount.",
                                        {"type": "list", "items": ["{@race orc|EGW}"]},
                                    ],
                                ),
                            ],
                        ),
                        section(
                            "Hollow One",
                            181,
                            [
                                "Blightshore's cruelties can return the dead to a cold and haunted semblance of life.",
                                entries_block(
                                    "Supernatural Gift: Hollow One",
                                    182,
                                    ["A Hollow One keeps moving through willpower and unfinished purpose."],
                                ),
                            ],
                        ),
                        section(
                            "Subclasses",
                            182,
                            [
                                entries_block(
                                    "Dunamis and Dunamancy",
                                    182,
                                    [
                                        "Dunamis studies possibility, probability, and the unseen force that can bend time and gravity.",
                                        entries_block(
                                            "Beyond the Kryn Dynasty",
                                            182,
                                            ["Dunamancy can spread through espionage, travel, and magical experimentation."],
                                        ),
                                        entries_block(
                                            "Dunamis as a Martial Focus",
                                            183,
                                            ["Warriors can turn dunamis toward mobility, force, and improbable outcomes."],
                                        ),
                                    ],
                                ),
                                entries_block(
                                    "Fighter",
                                    183,
                                    [
                                        "Wildemount adds a martial archetype touched by unrealized timelines.",
                                        entries_block(
                                            "Echo Knight",
                                            183,
                                            [
                                                "{@class fighter|phb|Echo Knight|Echo Knight|egw} commands a fading duplicate from another possibility."
                                            ],
                                        ),
                                    ],
                                ),
                                entries_block(
                                    "Wizard",
                                    184,
                                    [
                                        "Two arcane traditions from Wildemount channel the study of time and gravity.",
                                        entries_block(
                                            "Chronurgy Magic",
                                            184,
                                            ["{@class wizard|phb|Chronurgy Magic|Chronurgy|egw} bends initiative and probability."],
                                        ),
                                        entries_block(
                                            "Graviturgy Magic",
                                            185,
                                            ["{@class wizard|phb|Graviturgy Magic|Graviturgy|EGW} reshapes weight and force."],
                                        ),
                                    ],
                                ),
                                entries_block(
                                    "Dunamancy Spells",
                                    186,
                                    [
                                        "These spells are the best-known practical expressions of dunamis.",
                                        entries_block(
                                            "Dunamancy Spell List",
                                            186,
                                            [
                                                {
                                                    "type": "list",
                                                    "items": [
                                                        "{@spell Magnify Gravity|EGW}",
                                                        "{@spell Dark Star|EGW}",
                                                        "{@spell Temporal Shunt|EGW}",
                                                    ],
                                                }
                                            ],
                                        ),
                                    ],
                                ),
                                entries_block(
                                    "Spell Descriptions",
                                    186,
                                    [
                                        entries_block(
                                            "Dark Star",
                                            186,
                                            ["{@spell Dark Star|EGW} collapses an area into crushing magical void."],
                                        ),
                                        entries_block(
                                            "Magnify Gravity",
                                            188,
                                            ["{@spell Magnify Gravity|EGW} intensifies weight around your target area."],
                                        ),
                                        entries_block(
                                            "Temporal Shunt",
                                            189,
                                            ["{@spell Temporal Shunt|EGW} flickers a creature out of the current moment."],
                                        ),
                                    ],
                                ),
                                entries_block(
                                    "Heroic Chronicle",
                                    190,
                                    ["The heroic chronicle system lets players and Dungeon Masters build a backstory rooted in Wildemount."],
                                ),
                                entries_block(
                                    "Backgrounds",
                                    200,
                                    [
                                        "Wildemount's factions and scars shape the following backgrounds.",
                                        entries_block(
                                            "Wildemount Backgrounds",
                                            200,
                                            [
                                                {
                                                    "type": "list",
                                                    "items": [
                                                        "{@background Grinner|EGW}",
                                                        "{@background Luxonborn (Acolyte)|EGW}",
                                                        "{@background Volstrucker Agent|EGW}",
                                                    ],
                                                }
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                )
            ]
        },
    )

    write_json(
        root / "data/races.json",
        {
            "race": [
                {"name": "Dragonborn", "source": "PHB", "page": 32, "size": ["M"], "speed": {"walk": 30}, "ability": [{"str": 2, "cha": 1}], "entries": ["Dragonborn trace their bloodlines to mighty dragons."]},
                {"name": "Elf", "source": "PHB", "page": 23, "size": ["M"], "speed": {"walk": 30}, "ability": [{"dex": 2}], "entries": ["Elves bring grace, perception, and long memory to every culture."]},
                {"name": "Halfling", "source": "PHB", "page": 26, "size": ["S"], "speed": {"walk": 25}, "ability": [{"dex": 2}], "entries": ["Halflings move through the world with quickness and stubborn luck."]},
                {"name": "Orc", "source": "EGW", "page": 178, "size": ["M"], "speed": {"walk": 30}, "ability": [{"str": 2, "con": 1}], "entries": ["Orcs of Wildemount endure harsh frontiers and ancestral wars."]},
            ],
            "subrace": [
                {"name": "Pallid", "source": "EGW", "raceName": "Elf", "raceSource": "PHB", "page": 163, "ability": [{"wis": 1}], "entries": ["Pallid elves keep moonlit watch from hidden valleys."]},
                {"name": "Lotusden", "source": "EGW", "raceName": "Halfling", "raceSource": "PHB", "page": 164, "ability": [{"wis": 1}], "entries": ["Lotusden halflings move quietly beneath the forest canopy."]},
                {"name": "Draconblood", "source": "EGW", "raceName": "Dragonborn", "raceSource": "PHB", "page": 168, "ability": [{"int": 2, "cha": 1}], "entries": ["Draconblood dragonborn carry an imperious and analytical bearing."]},
                {"name": "Ravenite", "source": "EGW", "raceName": "Dragonborn", "raceSource": "PHB", "page": 168, "ability": [{"str": 2, "con": 1}], "entries": ["Ravenite dragonborn prize resilience and physical might."]},
            ],
        },
    )

    write_json(
        root / "data/backgrounds.json",
        {
            "background": [
                {"name": "Grinner", "source": "EGW", "page": 200, "skillProficiencies": [{"deception": True, "performance": True}], "entries": ["You spread laughter, rumors, and quiet resistance through every tavern you visit."]},
                {"name": "Luxonborn (Acolyte)", "source": "EGW", "page": 203, "skillProficiencies": [{"insight": True, "religion": True}], "entries": ["You were raised in devotion to the Luxon and its endless cycle of rebirth."]},
                {"name": "Volstrucker Agent", "source": "EGW", "page": 202, "skillProficiencies": [{"deception": True, "stealth": True}], "entries": ["You were trained to serve the empire's darkest covert missions."]},
            ]
        },
    )

    write_json(
        root / "data/spells/spells-egw.json",
        {
            "spell": [
                {"name": "Dark Star", "source": "EGW", "page": 186, "level": 8, "school": "E", "time": [{"number": 1, "unit": "action"}], "range": {"type": "point", "distance": {"type": "feet", "amount": 150}}, "components": {"v": True, "s": True, "m": "a shard of onyx and a drop of the void"}, "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 1}, "concentration": True}], "entries": ["A dark sphere of warped force forms at a point you can see within range."]},
                {"name": "Magnify Gravity", "source": "EGW", "page": 188, "level": 1, "school": "T", "time": [{"number": 1, "unit": "action"}], "range": {"type": "point", "distance": {"type": "feet", "amount": 60}}, "components": {"v": True, "s": True}, "duration": [{"type": "instant"}], "entries": ["You intensify gravity in a 10-foot-radius sphere centered on a point you can see."]},
                {"name": "Temporal Shunt", "source": "EGW", "page": 189, "level": 5, "school": "T", "time": [{"number": 1, "unit": "reaction"}], "range": {"type": "point", "distance": {"type": "feet", "amount": 120}}, "components": {"v": True, "s": True}, "duration": [{"type": "instant"}], "entries": ["You momentarily shift a creature out of time, causing its action to fizzle."]},
            ]
        },
    )

    write_json(root / "data/class/index.json", {"fighter": "class-fighter.json", "wizard": "class-wizard.json"})
    write_json(
        root / "data/class/class-fighter.json",
        {
            "subclass": [
                {"name": "Echo Knight", "source": "EGW", "className": "Fighter", "classSource": "PHB", "page": 183, "subclassFeatures": ["Echo Knight|Fighter|PHB|Echo Knight|EGW|3", "Manifest Echo|Fighter|PHB|Echo Knight|EGW|3"]}
            ],
            "subclassFeature": [
                {"name": "Echo Knight", "source": "EGW", "className": "Fighter", "classSource": "PHB", "subclassShortName": "Echo Knight", "subclassSource": "EGW", "level": 3, "page": 183, "entries": ["You can draw a shadowy echo from a branch of unrealized time."]},
                {"name": "Manifest Echo", "source": "EGW", "className": "Fighter", "classSource": "PHB", "subclassShortName": "Echo Knight", "subclassSource": "EGW", "level": 3, "page": 183, "entries": ["You can manifest your echo in an unoccupied space you can see within 15 feet of you."]},
            ],
        },
    )
    write_json(
        root / "data/class/class-wizard.json",
        {
            "subclass": [
                {"name": "Chronurgy Magic", "source": "EGW", "className": "Wizard", "classSource": "PHB", "page": 184, "subclassFeatures": ["Chronurgy Magic|Wizard|PHB|Chronurgy|EGW|2", "Chronal Shift|Wizard|PHB|Chronurgy|EGW|2"]},
                {"name": "Graviturgy Magic", "source": "EGW", "className": "Wizard", "classSource": "PHB", "page": 185, "subclassFeatures": ["Graviturgy Magic|Wizard|PHB|Graviturgy|EGW|2", "Adjust Density|Wizard|PHB|Graviturgy|EGW|2"]},
            ],
            "subclassFeature": [
                {"name": "Chronurgy Magic", "source": "EGW", "className": "Wizard", "classSource": "PHB", "subclassShortName": "Chronurgy", "subclassSource": "EGW", "level": 2, "page": 184, "entries": ["You learn to peer slightly ahead in time and twist the order of events."]},
                {"name": "Chronal Shift", "source": "EGW", "className": "Wizard", "classSource": "PHB", "subclassShortName": "Chronurgy", "subclassSource": "EGW", "level": 2, "page": 184, "entries": ["As a reaction, you can force a creature to reroll an attack roll, ability check, or saving throw."]},
                {"name": "Graviturgy Magic", "source": "EGW", "className": "Wizard", "classSource": "PHB", "subclassShortName": "Graviturgy", "subclassSource": "EGW", "level": 2, "page": 185, "entries": ["You learn how to alter weight and pressure through arcane study."]},
                {"name": "Adjust Density", "source": "EGW", "className": "Wizard", "classSource": "PHB", "subclassShortName": "Graviturgy", "subclassSource": "EGW", "level": 2, "page": 185, "entries": ["You can alter the weight of a willing creature or object you can see."]},
            ],
        },
    )
    return data_root
SCAG_BACKGROUND_TEST_NAMES = (
    "City Watch",
    "Clan Crafter",
    "Cloistered Scholar",
    "Courtier",
    "Faction Agent",
    "Far Traveler",
    "Inheritor",
    "Knight of the Order",
    "Mercenary Veteran",
    "Uthgardt Tribe Member",
    "Waterdhavian Noble",
    "Urban Bounty Hunter",
)


def build_scag_backgrounds_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Sword Coast Adventurer's Guide",
                    "id": "SCAG",
                    "source": "SCAG",
                    "contents": [
                        {
                            "name": "Backgrounds",
                            "ordinal": {"type": "chapter", "identifier": 5},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-scag.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Backgrounds",
                    "page": 145,
                    "entries": [
                        (
                            "The backgrounds described in the Player's Handbook are all found in "
                            "Faerun's various societies, in some form or another. This chapter "
                            "offers additional backgrounds for characters in a Forgotten Realms "
                            "campaign, many of them specific to Faerun or to the Sword Coast and "
                            "the North in particular."
                        ),
                        (
                            "As in the Player's Handbook, each of the backgrounds presented here "
                            "provides proficiencies, languages, and equipment, as well as a "
                            "background feature and sometimes a variant form."
                        ),
                        {
                            "type": "list",
                            "items": [f"{{@background {name}|SCAG}}" for name in SCAG_BACKGROUND_TEST_NAMES],
                        },
                    ],
                }
            ]
        },
    )
    return data_root


def build_scag_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Sword Coast Adventurer's Guide",
                    "id": "SCAG",
                    "source": "SCAG",
                    "contents": [
                        {
                            "name": "Races of the Realms",
                            "headers": [
                                "Dwarves",
                                "Elves",
                                "Halflings",
                                "Humans",
                                "Dragonborn",
                                "Gnomes",
                                "Half-Elves",
                                "Half-Orcs",
                                "Tieflings",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 3},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-scag.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Races of the Realms",
                    "page": 103,
                    "entries": [
                        "Faerun is home to many peoples and race traditions.",
                        {
                            "type": "section",
                            "name": "Dwarves",
                            "page": 103,
                            "entries": [
                                "The stout folk endure in holds across the North.",
                                {
                                    "type": "entries",
                                    "name": "Shield Dwarves",
                                    "page": 103,
                                    "entries": ["Shield dwarves hold fast to ancient strongholds."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Gold Dwarves",
                                    "page": 103,
                                    "entries": ["Gold dwarves prosper in the southern lands."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Gray Dwarves (Duergar)",
                                    "page": 104,
                                    "entries": ["Duergar survive the Underdark through grim discipline."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Dwarven Deities",
                                    "page": 104,
                                    "entries": ["Moradin and the Morndinsamman remain central to dwarven faith."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Elves",
                            "page": 105,
                            "entries": [
                                "Elves maintain ancient ties to Faerun and its hidden realms.",
                                {
                                    "type": "entries",
                                    "name": "Moon Elves",
                                    "page": 105,
                                    "entries": ["Moon elves are among the most common elves of the Sword Coast."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Sun Elves",
                                    "page": 106,
                                    "entries": ["Sun elves preserve old magical traditions."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Wood Elves",
                                    "page": 106,
                                    "entries": ["Wood elves favor the deep forest and a wandering life."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Dark Elves (Drow)",
                                    "page": 107,
                                    "entries": ["Drow communities endure beneath the surface world."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Elven Deities",
                                    "page": 107,
                                    "entries": ["Corellon and the Seldarine shape elven devotion."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Halflings",
                            "page": 108,
                            "entries": [
                                "Halflings weave themselves into larger realms while keeping close communities.",
                                {
                                    "type": "entries",
                                    "name": "Lightfoot Halflings",
                                    "page": 109,
                                    "entries": ["Lightfoot halflings travel widely and adapt quickly."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Strongheart Halflings",
                                    "page": 109,
                                    "entries": ["Strongheart halflings hold to enduring customs and hearths."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Halfling Deities",
                                    "page": 109,
                                    "entries": ["Yondalla and her kin watch over halfling life."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Humans",
                            "page": 110,
                            "entries": [
                                "Human cultures span every road and coast of Faerun.",
                                {
                                    "type": "entries",
                                    "name": "Human Ethnicities in Faerun",
                                    "page": 110,
                                    "entries": ["Calishite, Chondathan, Illuskan, and Tethyrian peoples are common in the region."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Dragonborn",
                            "page": 112,
                            "entries": [
                                "Dragonborn communities in Faerun carry memories of another world.",
                                {
                                    "type": "entries",
                                    "name": "Uncertain Origins",
                                    "page": 112,
                                    "entries": ["Legends disagree on exactly how dragonborn reached Toril."],
                                },
                                {
                                    "type": "entries",
                                    "name": "The Fight for Freedom",
                                    "page": 113,
                                    "entries": ["Their history is marked by revolt against draconic tyrants."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Honor and Family",
                                    "page": 113,
                                    "entries": ["Honor and clan remain core dragonborn values."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Philosophy and Religion",
                                    "page": 113,
                                    "entries": ["Dragonborn faith and philosophy often emphasize self-mastery."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Gnomes",
                            "page": 114,
                            "entries": [
                                "Gnomes survive through craft, caution, and wit.",
                                {
                                    "type": "entries",
                                    "name": "Forest Gnomes",
                                    "page": 114,
                                    "entries": ["Forest gnomes dwell in quiet woodland enclaves."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Rock Gnomes",
                                    "page": 114,
                                    "entries": ["Rock gnomes prize devices, gems, and ingenious workmanship."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Deep Gnomes (Svirfneblin)",
                                    "page": 115,
                                    "entries": ["Deep gnomes endure the dangers of the Underdark."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Gnomish Deities",
                                    "page": 115,
                                    "entries": ["Garl Glittergold and his circle guide gnomish worship."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Half-Elves",
                            "page": 116,
                            "entries": [
                                "Half-elves bridge communities that rarely see themselves clearly in each other.",
                                {
                                    "type": "entries",
                                    "name": "Young Race, Old Roots",
                                    "page": 116,
                                    "entries": ["Half-elves grew more numerous as human and elven societies intertwined."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Mixed Heritage",
                                    "page": 116,
                                    "entries": ["Their heritage shapes how they move between cultures."],
                                },
                                {
                                    "type": "entries",
                                    "name": "The Gods of Two Peoples",
                                    "page": 116,
                                    "entries": ["Half-elves often inherit spiritual ties from both lineages."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Half-Orcs",
                            "page": 117,
                            "entries": [
                                "Half-orcs carry a long and often difficult history in Faerun.",
                                {
                                    "type": "entries",
                                    "name": "Blood Will Tell",
                                    "page": 117,
                                    "entries": ["Many half-orcs wrestle with others' assumptions about their heritage."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Half-Orc Homelands",
                                    "page": 117,
                                    "entries": ["Communities of half-orcs can be found across the North."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Half-Orc Deities",
                                    "page": 118,
                                    "entries": ["Some half-orcs honor Gruumsh, while others seek different patrons."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Tieflings",
                            "page": 118,
                            "entries": [
                                "Tieflings in Faerun carry infernal blood and a visible burden of suspicion.",
                                {
                                    "type": "entries",
                                    "name": "The Mark of Asmodeus",
                                    "page": 118,
                                    "entries": ["Many tieflings bear the legacy of Asmodeus's claim on their bloodline."],
                                },
                                {
                                    "type": "entries",
                                    "name": "A Race without a Home",
                                    "page": 119,
                                    "entries": ["Tieflings are scattered across cities and hard frontiers alike."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Lone Faithful",
                                    "page": 119,
                                    "entries": ["Tieflings often forge deeply personal religious lives."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Tiefling Names",
                                    "page": 119,
                                    "entries": ["Their names can reflect infernal, virtue-based, or adopted traditions."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Aasimar",
                                    "page": 119,
                                    "entries": ["Aasimar stand as a celestial contrast to tiefling lineages."],
                                },
                            ],
                        },
                    ],
                }
            ]
        },
    )
    return data_root


def build_scag_classes_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Sword Coast Adventurer's Guide",
                    "id": "SCAG",
                    "source": "SCAG",
                    "contents": [
                        {
                            "name": "Classes",
                            "headers": list(SCAG_CLASSES_TEST_HEADERS),
                            "ordinal": {"type": "chapter", "identifier": 4},
                        }
                    ],
                }
            ]
        },
    )
    chapter_entries: list[object] = [
        "The twelve classes of the Player's Handbook appear across the Sword Coast and the North."
    ]
    for title, page, subsection_titles in SCAG_CLASSES_TEST_SECTION_DEFINITIONS:
        section_entries: list[object] = [f"{title} have a distinct place in the Forgotten Realms."]
        for subsection_index, subsection_title in enumerate(subsection_titles):
            section_entries.append(
                {
                    "type": "entries",
                    "name": subsection_title,
                    "page": page + min(subsection_index, 1),
                    "entries": [f"{subsection_title} keeps the source-backed {title.lower()} wrapper readable in book context."],
                }
            )
        chapter_entries.append(
            {
                "type": "section",
                "name": title,
                "page": page,
                "entries": section_entries,
            }
        )
    write_json(
        root / "data/book/book-scag.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Classes",
                    "page": 121,
                    "entries": chapter_entries,
                }
            ]
        },
    )
    return data_root


def build_scag_first_slice_boundary_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Sword Coast Adventurer's Guide",
                    "id": "SCAG",
                    "source": "SCAG",
                    "contents": [
                        {
                            "name": "Welcome to the Realms",
                            "ordinal": {"type": "chapter", "identifier": 1},
                        },
                        {
                            "name": "The Sword Coast and the North",
                            "ordinal": {"type": "chapter", "identifier": 2},
                        },
                        {
                            "name": "Races of the Realms",
                            "headers": ["Dwarves"],
                            "ordinal": {"type": "chapter", "identifier": 3},
                        },
                        {
                            "name": "Classes",
                            "headers": ["Barbarians"],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        },
                        {
                            "name": "Backgrounds",
                            "ordinal": {"type": "chapter", "identifier": 5},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-scag.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Welcome to the Realms",
                    "page": 7,
                    "entries": [
                        "This chapter introduces the broader Forgotten Realms setting and travel context."
                    ],
                },
                {
                    "type": "section",
                    "name": "The Sword Coast and the North",
                    "page": 17,
                    "entries": [
                        "This chapter surveys settlements, frontiers, and regional lore across the Sword Coast."
                    ],
                },
                {
                    "type": "section",
                    "name": "Races of the Realms",
                    "page": 103,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Dwarves",
                            "page": 103,
                            "entries": [
                                "The stout folk endure in holds across the North."
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Classes",
                    "page": 121,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Barbarians",
                            "page": 121,
                            "entries": [
                                "Barbarians keep distinct traditions in the North."
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Backgrounds",
                    "page": 145,
                    "entries": [
                        "This chapter offers additional backgrounds for characters in a Forgotten Realms campaign."
                    ],
                },
            ]
        },
    )
    return data_root


def build_scag_entry_source_context_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Sword Coast Adventurer's Guide",
                    "id": "SCAG",
                    "source": "SCAG",
                    "contents": [
                        {
                            "name": "Races of the Realms",
                            "headers": ["Halflings"],
                            "ordinal": {"type": "chapter", "identifier": 3},
                        },
                        {
                            "name": "Classes",
                            "headers": ["Primal Paths", "Musical Instruments"],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        },
                        {
                            "name": "Backgrounds",
                            "ordinal": {"type": "chapter", "identifier": 5},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-scag.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Races of the Realms",
                    "page": 103,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Halflings",
                            "page": 108,
                            "entries": [
                                "Ghostwise halflings are one of the subraces discussed in this section."
                            ],
                        }
                    ],
                },
                {
                    "type": "section",
                    "name": "Classes",
                    "page": 121,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Primal Paths",
                            "page": 121,
                            "entries": [
                                "Barbarians in the Realms have the following Primal Path options.",
                                "Path of the Battlerager appears here alongside its specialized armor.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Musical Instruments",
                            "page": 124,
                            "entries": [
                                {
                                    "type": "list",
                                    "items": [
                                        {"type": "item", "name": "Birdpipes", "entry": "A Faerunian wind instrument."},
                                        {"type": "item", "name": "Longhorn", "entry": "A favored instrument of elven enclaves."},
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Backgrounds",
                    "page": 145,
                    "entries": [
                        "This chapter offers additional backgrounds for characters in a Forgotten Realms campaign.",
                        {"type": "list", "items": ["{@background Clan Crafter|SCAG}"]},
                    ],
                },
            ]
        },
    )
    write_json(
        root / "data/races.json",
        {
            "race": [
                {
                    "name": "Ghostwise Halfling",
                    "source": "SCAG",
                    "page": 110,
                    "raceName": "Halfling",
                    "subraceName": "Ghostwise",
                    "size": ["S"],
                    "speed": {"walk": 30},
                    "entries": ["Ghostwise halflings keep ancient traditions and quiet settlements."],
                }
            ]
        },
    )
    write_json(
        root / "data/backgrounds.json",
        {
            "background": [
                {
                    "name": "Clan Crafter",
                    "source": "SCAG",
                    "page": 145,
                    "skillProficiencies": [{"history": True, "insight": True}],
                    "entries": ["Clan crafters are respected artisans among dwarven communities."],
                }
            ]
        },
    )
    write_json(
        root / "data/items.json",
        {
            "item": [
                {
                    "name": "Spiked Armor",
                    "source": "SCAG",
                    "page": 121,
                    "type": "MA",
                    "armor": True,
                    "ac": 14,
                    "entries": ["Spiked armor is favored by battleragers."],
                },
                {
                    "name": "Birdpipes",
                    "source": "SCAG",
                    "page": 124,
                    "type": "INS",
                    "entries": ["Birdpipes are also known as satyr pipes."],
                },
            ],
            "itemGroup": [],
        },
    )
    write_json(
        root / "data/class/index.json",
        {"scag": "class-scag.json"},
    )
    write_json(
        root / "data/class/class-scag.json",
        {
            "subclass": [
                {
                    "name": "Path of the Battlerager",
                    "shortName": "Battlerager",
                    "source": "SCAG",
                    "page": 121,
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "subclassFeatures": ["Battlerager Armor|Barbarian|PHB|Battlerager|SCAG|3"],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Battlerager Armor",
                    "source": "SCAG",
                    "page": 121,
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "subclassShortName": "Battlerager",
                    "subclassSource": "SCAG",
                    "level": 3,
                    "entries": ["You can use spiked armor as a weapon while raging."],
                }
            ],
        },
    )
    return data_root


def build_vgm_monster_lore_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)

    def monster(
        name: str,
        *,
        page: int,
        monster_type: str,
        tags: list[str] | None = None,
        group: list[str] | None = None,
        size: str = "M",
        cr: str = "5",
    ) -> dict[str, object]:
        type_value: object = monster_type
        if tags:
            type_value = {"type": monster_type, "tags": tags}
        payload: dict[str, object] = {
            "name": name,
            "source": "VGM",
            "page": page,
            "size": [size],
            "type": type_value,
            "alignment": ["C", "E"],
            "ac": [14],
            "hp": {"average": 45, "formula": "6d8 + 18"},
            "speed": {"walk": 30},
            "str": 16,
            "dex": 14,
            "con": 16,
            "int": 10,
            "wis": 12,
            "cha": 10,
            "passive": 11,
            "languages": ["Common"],
            "cr": cr,
            "trait": [{"name": "Trait", "entries": [f"{name} has a focused test trait."]}],
            "action": [{"name": "Attack", "entries": [f"{name} makes a focused test attack."]}],
        }
        if group:
            payload["group"] = group
        return payload

    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Volo's Guide to Monsters",
                    "id": "VGM",
                    "source": "VGM",
                    "contents": [
                        {
                            "name": "Monster Lore",
                            "headers": [
                                "Beholders: Bad Dreams Come True",
                                "Giants: World Shakers",
                                "Gnolls: The Insatiable Hunger",
                                "Goblinoids: The Conquering Host",
                                "Hags: Dark Sisterhood",
                                "Kobolds: Little Dragons",
                                "Mind Flayers: Scourge of Worlds",
                                "Orcs: The Godsworn",
                                "Yuan-ti: Snake People",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 1},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-vgm.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Monster Lore",
                    "page": 5,
                    "entries": [
                        "This chapter expands several iconic monster families with source-backed lore and lair guidance.",
                        {
                            "type": "section",
                            "name": "Beholders: Bad Dreams Come True",
                            "page": 5,
                            "entries": [
                                "Beholders twist reality through paranoia and impossible dreams.",
                                {"type": "entries", "name": "Dreamspawn", "page": 6, "entries": ["New beholders emerge from warped dreams."]},
                                {
                                    "type": "entries",
                                    "name": "Roleplaying a Beholder",
                                    "page": 8,
                                    "entries": ["Beholder tables and quirks remain readable source context for encounter prep."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Battle Tactics",
                                    "page": 9,
                                    "entries": ["Beholders keep tactical guidance in book context instead of turning it into modeled combat behavior."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Variant Abilities",
                                    "page": 12,
                                    "entries": ["Variant eye effects stay readable on the wrapper page without becoming mechanically modeled options."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Giants: World Shakers",
                            "page": 18,
                            "entries": [
                                "Giants and their kin still feel the pull of the ordning.",
                                {"type": "entries", "name": "The Ordning", "page": 19, "entries": ["Every true giant measures itself against the ordning."]},
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Gnolls: The Insatiable Hunger",
                            "page": 33,
                            "entries": [
                                "Gnolls carry Yeenoghu's hunger into every raid.",
                                {"type": "entries", "name": "Demonic Hunger", "page": 34, "entries": ["Gnoll packs devour everything in their path."]},
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Goblinoids: The Conquering Host",
                            "page": 40,
                            "entries": [
                                "Goblinoids rally under Maglubiyet's endless call to conquest.",
                                {"type": "entries", "name": "The Host", "page": 41, "entries": ["Goblins, bugbears, and hobgoblins answer the same war god."]},
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Hags: Dark Sisterhood",
                            "page": 52,
                            "entries": [
                                "Hags bargain, corrupt, and gather in covens.",
                                {"type": "entries", "name": "Covens", "page": 53, "entries": ["A hag coven is more dangerous than any lone sister."]},
                                {
                                    "type": "entries",
                                    "name": "Roleplaying a Hag",
                                    "page": 54,
                                    "entries": ["Roleplaying cues stay visible here as source context for DM-facing prep."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Hag Lair Actions",
                                    "page": 59,
                                    "entries": [
                                        {
                                            "type": "entries",
                                            "name": "Lair Actions",
                                            "page": 59,
                                            "entries": ["Grandmother hags can shape their lairs with distinct effects."],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Regional Effects",
                                            "page": 60,
                                            "entries": ["A hag's warped territory remains readable as source context."],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Kobolds: Little Dragons",
                            "page": 63,
                            "entries": [
                                "Kobolds survive by traps, teamwork, and draconic devotion.",
                                {"type": "entries", "name": "Tribal Ingenuity", "page": 64, "entries": ["Kobolds turn scrap into vicious inventions."]},
                                {
                                    "type": "entries",
                                    "name": "Tactics",
                                    "page": 67,
                                    "entries": ["Kobold battlefield tricks stay readable as source context rather than modeled logic."],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Mind Flayers: Scourge of Worlds",
                            "page": 71,
                            "entries": [
                                "Mind flayers and their warped servants pursue impossible schemes below the world.",
                                {"type": "entries", "name": "Elder Brains", "page": 72, "entries": ["Every colony bends toward an elder brain's designs."]},
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Orcs: The Godsworn",
                            "page": 82,
                            "entries": [
                                "Orc war bands define themselves through divine struggle and violence.",
                                {"type": "entries", "name": "Gruumsh's Chosen", "page": 83, "entries": ["Gruumsh's servants hurl whole tribes into war."]},
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Yuan-ti: Snake People",
                            "page": 92,
                            "entries": [
                                "Yuan-ti societies prize transformation, hierarchy, and hidden rule.",
                                {"type": "entries", "name": "The Castes", "page": 93, "entries": ["Every yuan-ti city enforces a ruthless caste ladder."]},
                            ],
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/bestiary/bestiary-vgm.json",
        {
            "_meta": {"dependencies": {"monster": ["MM"]}, "internalCopies": ["monster"]},
            "monster": [
                monster("Death Kiss", page=124, monster_type="aberration", group=["Beholders"], size="L", cr="10"),
                monster("Gauth", page=125, monster_type="aberration", group=["Beholders"], cr="6"),
                monster("Gazer", page=126, monster_type="aberration", group=["Beholders"], size="T", cr="1/2"),
                monster("Cloud Giant Smiling One", page=146, monster_type="giant", tags=["cloud giant"], size="H", cr="11"),
                monster("Mouth of Grolantor", page=149, monster_type="giant", tags=["hill giant"], size="H", cr="6"),
                monster("Flind", page=153, monster_type="humanoid", tags=["gnoll"], cr="9"),
                monster("Gnoll Witherling", page=155, monster_type="undead", cr="1/4"),
                monster("Nilbog", page=159, monster_type="humanoid", tags=["goblinoid"], cr="1"),
                monster("Hobgoblin Devastator", page=161, monster_type="humanoid", tags=["goblinoid"], cr="4"),
                monster("Annis Hag", page=159, monster_type="fey", size="L", cr="6"),
                monster("Bheur Hag", page=160, monster_type="fey", size="L", cr="7"),
                monster("Kobold Dragonshield", page=165, monster_type="humanoid", tags=["kobold"], cr="1"),
                monster("Kobold Inventor", page=166, monster_type="humanoid", tags=["kobold"], cr="1/4"),
                monster("Alhoon", page=172, monster_type="undead", cr="10"),
                monster("Mindwitness", page=176, monster_type="aberration", size="L", cr="5"),
                monster("Ulitharid", page=175, monster_type="aberration", size="L", cr="9"),
                monster("Orc Hand of Yurtrus", page=184, monster_type="humanoid", tags=["orc"], cr="2"),
                monster("Tanarukk", page=186, monster_type="fiend", tags=["demon", "orc"], cr="5"),
                monster("Yuan-ti Anathema", page=202, monster_type="monstrosity", tags=["shapechanger", "yuan-ti"], size="H", cr="12"),
                monster("Yuan-ti Broodguard", page=203, monster_type="humanoid", tags=["yuan-ti"], cr="2"),
            ],
        },
    )
    return data_root


def build_xge_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Xanathar's Guide to Everything",
                    "id": "XGE",
                    "source": "XGE",
                    "contents": [
                        {
                            "name": "Dungeon Master's Tools",
                            "headers": [
                                "Simultaneous Effects",
                                "Falling",
                                "Sleep",
                                "Adamantine Weapons",
                                "Tying Knots",
                                "Tool Proficiencies",
                                "Spellcasting",
                                "Encounter Building",
                                "Random Encounters: A World of Possibilities",
                                "Traps Revisited",
                                "Downtime Revisited",
                                "Awarding Magic Items",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 2},
                        },
                        {
                            "name": "Shared Campaigns",
                            "headers": [
                                "Code of Conduct",
                                "Designing Adventures",
                                "Character Creation",
                                "Variant Rules",
                            ],
                            "ordinal": {"type": "appendix", "identifier": "A"},
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-xge.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Dungeon Master's Tools",
                    "page": 77,
                    "entries": [
                        {
                            "type": "entries",
                            "name": "Simultaneous Effects",
                            "page": 77,
                            "entries": [
                                "When multiple things happen at once, the person at the table or the creature in the game world who controls those things decides the order.",
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Falling",
                            "page": 77,
                            "entries": [
                                "The rule for falling assumes a creature immediately drops when it falls.",
                                {
                                    "type": "entries",
                                    "name": "Rate of Falling",
                                    "page": 77,
                                    "entries": ["A creature instantly descends up to 500 feet when it falls."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Flying Creatures and Falling",
                                    "page": 77,
                                    "entries": ["Flying creatures can stay aloft or plummet depending on why they fall."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Sleep",
                            "page": 77,
                            "entries": [
                                "Sleep and rest can be interrupted, deepened, or ignored only at a cost.",
                                {
                                    "type": "entries",
                                    "name": "Waking Someone",
                                    "page": 77,
                                    "entries": ["A sleeper can be awakened by noise, damage, or an ally's effort."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Sleeping in Armor",
                                    "page": 77,
                                    "entries": ["Armor makes rest harder and limits its benefits."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Going without a Long Rest",
                                    "page": 78,
                                    "entries": ["Skipping long rests invites exhaustion and mounting risk."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Adamantine Weapons",
                            "page": 78,
                            "entries": ["Adamantine weapons bite into objects and structures with unusual certainty."],
                        },
                        {
                            "type": "entries",
                            "name": "Tying Knots",
                            "page": 78,
                            "entries": ["Different knots ask for different ability checks, time, and conditions."],
                        },
                        {
                            "type": "entries",
                            "name": "Tool Proficiencies",
                            "page": 78,
                            "entries": [
                                "Tool proficiencies can deepen a character's identity without changing the app's current automation scope.",
                                {
                                    "type": "entries",
                                    "name": "Tools and Skills Together",
                                    "page": 78,
                                    "entries": ["Tools and skills can combine when both are relevant."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Tool Descriptions",
                                    "page": 78,
                                    "entries": ["Each tool description gives examples of useful checks and activities."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Spellcasting",
                            "page": 85,
                            "entries": [
                                "This section expands on core spellcasting without replacing the core rules.",
                                {
                                    "type": "entries",
                                    "name": "Perceiving a Caster at Work",
                                    "page": 85,
                                    "entries": ["Obvious components or visible magic can reveal that a spell is being cast."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Identifying a Spell",
                                    "page": 85,
                                    "entries": ["Observers can sometimes identify a spell as it is cast or after its effect appears."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Invalid Spell Targets",
                                    "page": 85,
                                    "entries": ["Spells can fail or misfire when their targets are invalid."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Areas of Effect on a Grid",
                                    "page": 86,
                                    "entries": ["A grid can help adjudicate cones, cubes, cylinders, lines, and spheres."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Encounter Building",
                            "page": 88,
                            "entries": [
                                "Encounter building weighs party size, monster count, and expected difficulty.",
                                {
                                    "type": "entries",
                                    "name": "Step 1: Assess the Characters",
                                    "page": 88,
                                    "entries": ["Review the party's level, resilience, and damage output before choosing foes."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Step 2: Choose Encounter Size",
                                    "page": 88,
                                    "entries": ["Decide whether the battle should feature one foe or multiple monsters."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Step 3: Determine Numbers and Challenge Ratings",
                                    "page": 88,
                                    "entries": [
                                        "Use the encounter math to match challenge ratings to the party and the number of monsters.",
                                        {
                                            "type": "entries",
                                            "name": "Weak Monsters and High-Level Characters",
                                            "page": 89,
                                            "entries": ["Very weak foes stop contributing once the party outlevels their impact."],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Step 4: Select Monsters",
                                    "page": 90,
                                    "entries": ["Choose monsters whose actions, durability, and mobility fit the encounter goals."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Step 5: Add Flavor",
                                    "page": 91,
                                    "entries": [
                                        "Encounter details become more memorable when the battlefield and monster behavior matter.",
                                        {
                                            "type": "entries",
                                            "name": "Monster Personality",
                                            "page": 91,
                                            "entries": ["A monster's temperament can change how it opens a fight or when it flees."],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Terrain and Traps",
                                            "page": 91,
                                            "entries": ["Battlefields gain texture when terrain or hazards influence every turn."],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Quick Matchups",
                                    "page": 91,
                                    "entries": ["Quick matchups offer a faster, rougher benchmark for encounter difficulty."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Random Encounters: A World of Possibilities",
                            "page": 92,
                            "entries": [
                                "Random encounters can do more than trigger a fight.",
                                {
                                    "type": "entries",
                                    "name": "Flight, or Fight, or..?",
                                    "page": 92,
                                    "entries": [
                                        "Some random encounters should invite caution, negotiation, or retreat instead of an immediate battle."
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Traps Revisited",
                            "page": 113,
                            "entries": [
                                "Traps range from quick hazards to elaborate multi-round challenges.",
                                {
                                    "type": "entries",
                                    "name": "Simple Traps",
                                    "page": 113,
                                    "entries": [
                                        "Simple traps trigger once and then become harmless or easy to bypass.",
                                        {
                                            "type": "entries",
                                            "name": "Elements of a Simple Trap",
                                            "page": 113,
                                            "entries": [
                                                "Simple traps define their level, trigger, effect, and countermeasures."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Running a Simple Trap",
                                            "page": 113,
                                            "entries": [
                                                "Running a simple trap starts with noticing passive perception and then adjudicating the trigger and effect."
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Example Simple Traps",
                                    "page": 114,
                                    "entries": [
                                        "Example simple traps offer ready-made hazards such as pits, nets, and poison needles."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Designing Simple Traps",
                                    "page": 115,
                                    "entries": [
                                        "Designing a simple trap starts with its purpose and expected lethality.",
                                        {
                                            "type": "entries",
                                            "name": "Purpose",
                                            "page": 115,
                                            "entries": [
                                                "A trap's purpose explains why it exists and what behavior it is meant to provoke."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Level and Lethality",
                                            "page": 116,
                                            "entries": [
                                                "Level and lethality set the saving throw DCs, attack bonuses, and damage expectations."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Triggers",
                                            "page": 116,
                                            "entries": [
                                                "Triggers define the event or intrusion that sets the trap off."
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Complex Traps",
                                    "page": 117,
                                    "entries": [
                                        "Complex traps unfold over multiple rounds and act on initiative.",
                                        {
                                            "type": "entries",
                                            "name": "Describing a Complex Trap",
                                            "page": 117,
                                            "entries": [
                                                "A complex trap description covers its dynamic battlefield behavior."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Running a Complex Trap",
                                            "page": 117,
                                            "entries": [
                                                "Running a complex trap means adjudicating initiative, ongoing elements, and player counterplay."
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Example Complex Traps",
                                    "page": 120,
                                    "entries": [
                                        "Example complex traps show how a room-sized hazard can evolve across rounds."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Designing Complex Traps",
                                    "page": 122,
                                    "entries": [
                                        "Complex trap design focuses on moving parts, pacing, and how characters can shut the hazard down.",
                                        {
                                            "type": "entries",
                                            "name": "Map",
                                            "page": 122,
                                            "entries": [
                                                "A trap map clarifies where hazards, cover, and escape routes live."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Active Elements",
                                            "page": 122,
                                            "entries": [
                                                "Active elements are the obvious, turn-by-turn threats the trap presents."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Initiative",
                                            "page": 123,
                                            "entries": [
                                                "Initiative determines when the trap acts in relation to the characters."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Defeating Complex Traps",
                                            "page": 123,
                                            "entries": [
                                                "Characters can defeat complex traps by disabling or surviving their moving parts."
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Downtime Revisited",
                            "page": 123,
                            "entries": [
                                "Downtime can span weeks or months and generate new problems as well as rewards.",
                                {
                                    "type": "entries",
                                    "name": "Rivals",
                                    "page": 123,
                                    "entries": ["Rivals turn downtime into a continuing source of tension."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Downtime Activities",
                                    "page": 125,
                                    "entries": ["Downtime activities spend time and treasure on focused goals."],
                                },
                                {
                                    "type": "entries",
                                    "name": "Example Downtime Activities",
                                    "page": 126,
                                    "entries": ["Example activities show how the downtime framework behaves in play."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Awarding Magic Items",
                            "page": 135,
                            "entries": ["Magic item awards can be paced by tone, treasure, and campaign expectations."],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Shared Campaigns",
                    "page": 171,
                    "entries": [
                        {
                            "type": "entries",
                            "name": "Code of Conduct",
                            "page": 171,
                            "entries": ["Shared campaigns ask everyone to follow the same conduct expectations."],
                        },
                        {
                            "type": "entries",
                            "name": "Designing Adventures",
                            "page": 172,
                            "entries": ["Shared-campaign adventures need tighter assumptions about pacing and rewards."],
                        },
                        {
                            "type": "entries",
                            "name": "Character Creation",
                            "page": 173,
                            "entries": ["Character creation in shared campaigns uses a narrower rules contract."],
                        },
                        {
                            "type": "entries",
                            "name": "Variant Rules",
                            "page": 173,
                            "entries": ["Shared campaigns keep a bounded rules list so different tables stay compatible."],
                        },
                    ],
                },
            ]
        },
    )
    return data_root


def build_xge_book_related_entities_data_root(root: Path) -> Path:
    data_root = build_xge_book_data_root(root)
    book_path = root / "data/book/book-xge.json"
    book_payload = json.loads(book_path.read_text(encoding="utf-8"))
    dungeon_masters_tools = book_payload["data"][0]["entries"]
    sleep_entry = next(entry for entry in dungeon_masters_tools if entry.get("name") == "Sleep")
    sleep_entry["entries"].append(
        {
            "type": "inlineBlock",
            "entries": [
                {
                    "type": "list",
                    "items": ["{@variantrule Waking Someone||Waking Someone}"],
                }
            ],
        }
    )
    spellcasting_entry = next(
        entry for entry in dungeon_masters_tools if entry.get("name") == "Spellcasting"
    )
    spellcasting_entry["entries"].append(
        {
            "type": "inlineBlock",
            "entries": [
                {
                    "type": "list",
                    "items": ["{@variantrule Identifying a Spell||Identifying a Spell}"],
                }
            ],
        }
    )
    write_json(book_path, book_payload)
    write_json(
        root / "data/variantrules.json",
        {
            "variantrule": [
                {
                    "name": "Waking Someone",
                    "source": "XGE",
                    "page": 77,
                    "ruleType": "O",
                    "entries": ["A sleeper can be awakened by noise, damage, or an ally's effort."],
                },
                {
                    "name": "Identifying a Spell",
                    "source": "XGE",
                    "page": 85,
                    "ruleType": "O",
                    "entries": ["Observers can sometimes identify a spell as it is cast or after its effects appear."],
                },
            ]
        },
    )
    return data_root


def build_egw_heroic_chronicle_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Explorer's Guide to Wildemount",
                    "id": "EGW",
                    "source": "EGW",
                    "contents": [
                        {
                            "name": "Character Options",
                            "headers": ["Heroic Chronicle"],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-egw.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Character Options",
                    "page": 184,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Subclasses",
                            "page": 186,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Heroic Chronicle",
                                    "page": 196,
                                    "entries": [
                                        (
                                            "The heroic chronicle system lets players and Dungeon Masters "
                                            "build a backstory rooted in Wildemount."
                                        ),
                                        {
                                            "type": "entries",
                                            "name": "Backstory",
                                            "page": 196,
                                            "entries": [
                                                (
                                                    "Instead of choosing a background in isolation, you can "
                                                    "roll or choose details that tie your character to the "
                                                    "setting's people and conflicts."
                                                ),
                                                {
                                                    "type": "entries",
                                                    "name": "Homeland",
                                                    "page": 197,
                                                    "entries": [
                                                        (
                                                            "Your homeland tells you where you were raised "
                                                            "and which cultures shaped your earliest years."
                                                        )
                                                    ],
                                                },
                                                {
                                                    "type": "entries",
                                                    "name": "Mysterious Secret",
                                                    "page": 200,
                                                    "entries": [
                                                        (
                                                            "Each mysterious secret offers a campaign hook "
                                                            "the Dungeon Master can reveal over time."
                                                        )
                                                    ],
                                                },
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Prophecy",
                                            "page": 201,
                                            "entries": [
                                                (
                                                    "A prophecy hints at a destiny waiting for your "
                                                    "adventuring career."
                                                ),
                                                {
                                                    "type": "entries",
                                                    "name": "Prophecy Rewards",
                                                    "page": 202,
                                                    "entries": [
                                                        (
                                                            "When your prophecy comes to pass, you gain a "
                                                            "supernatural charm or other reward."
                                                        )
                                                    ],
                                                },
                                            ],
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    return data_root


def build_egw_treasure_progression_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Explorer's Guide to Wildemount",
                    "id": "EGW",
                    "source": "EGW",
                    "contents": [
                        {
                            "name": "Wildemount Treasures",
                            "headers": ["Vestiges of Divergence", "Arms of the Betrayers"],
                            "ordinal": {"type": "chapter", "identifier": 6},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/book/book-egw.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Wildemount Treasures",
                    "page": 265,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Vestiges of Divergence",
                            "page": 270,
                            "entries": [
                                (
                                    "Vestiges of Divergence are legendary relics that evolve with a worthy "
                                    "bearer over the course of a campaign."
                                ),
                                {
                                    "type": "list",
                                    "items": [
                                        "{@item Danoth's Visor|EGW}",
                                        "{@item Wreath of the Prism|EGW}",
                                    ],
                                },
                                {
                                    "type": "inset",
                                    "name": "Advancement of a Vestige of Divergence",
                                    "page": 271,
                                    "entries": [
                                        (
                                            "Typically, the advancement of a Vestige of Divergence echoes "
                                            "its wielder's own journey of self-discovery."
                                        ),
                                        (
                                            "A Vestige of Divergence typically remains dormant until its "
                                            "wielder achieves 9th level."
                                        ),
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Arms of the Betrayers",
                            "page": 274,
                            "entries": [
                                (
                                    "The Arms of the Betrayers are sentient weapons forged from the souls "
                                    "of fiends by the Betrayer Gods."
                                ),
                                {
                                    "type": "entries",
                                    "name": "Betrayer Artifact Properties",
                                    "page": 274,
                                    "entries": [
                                        (
                                            "The Arms of the Betrayers advance in power in the same manner "
                                            "as the Vestiges of Divergence."
                                        ),
                                        (
                                            "When the item reaches its exalted state, it gains a major "
                                            "beneficial property."
                                        ),
                                    ],
                                },
                                {
                                    "type": "list",
                                    "items": [
                                        "{@item Grovelthrash|EGW}",
                                        "{@item The Bloody End|EGW}",
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/items.json",
        {
            "item": [
                {
                    "name": "Danoth's Visor (Dormant)",
                    "source": "EGW",
                    "page": 270,
                    "wondrous": True,
                    "rarity": "legendary",
                    "entries": [
                        "This jeweled visor lets its wearer read omens in reflected light.",
                    ],
                },
                {
                    "name": "Grovelthrash (Dormant)",
                    "source": "EGW",
                    "page": 275,
                    "type": "M",
                    "rarity": "artifact",
                    "entries": [
                        "This brutal warhammer exults in greed and cruelty.",
                    ],
                },
                {
                    "name": "Staff of Dunamancy",
                    "source": "EGW",
                    "page": 270,
                    "type": "ST",
                    "rarity": "very rare",
                    "entries": [
                        "This staff helps a spellcaster shape gravity and time magic.",
                    ],
                },
            ],
            "itemGroup": [],
        },
    )
    return data_root


def build_tce_book_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/books.json",
        {
            "book": [
                {
                    "name": "Tasha's Cauldron of Everything",
                    "id": "TCE",
                    "source": "TCE",
                    "contents": [
                        {
                            "name": "Using This Book",
                            "headers": [
                                "What You'll Find Within",
                                "It's All Optional",
                                "Ten Rules to Remember",
                            ],
                        },
                        {
                            "name": "Character Options",
                            "headers": [
                                "Customizing Your Origin",
                                "Changing a Skill",
                                "Changing Your Subclass",
                                *TCE_CLASS_WRAPPER_TEST_TITLES,
                            ],
                            "ordinal": {"type": "chapter", "identifier": 1},
                        },
                        {
                            "name": "Group Patrons",
                            "headers": [
                                "How Patrons Work",
                                "Example Patrons",
                                "Being Your Own Patron",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 2},
                        },
                        {
                            "name": "Magical Miscellany",
                            "headers": [
                                "Spells",
                                "Personalizing Spells",
                                "Magic Items",
                                "Magic Tattoos",
                                "Magic Item Descriptions",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 3},
                        },
                        {
                            "name": "Dungeon Master's Tools",
                            "headers": [
                                "Session Zero",
                                "Sidekicks",
                                "Parleying with Monsters",
                                "Environmental Hazards",
                                "Puzzles",
                            ],
                            "ordinal": {"type": "chapter", "identifier": 4},
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        root / "data/variantrules.json",
        {
            "variantrule": [
                {
                    "name": "Encumbrance",
                    "source": "PHB",
                    "page": 176,
                    "ruleType": "O",
                    "entries": [
                        "If you carry weight in excess of 5 times your Strength score, you are encumbered."
                    ],
                },
                {
                    "name": "Customizing Your Origin",
                    "source": "TCE",
                    "page": 7,
                    "ruleType": "O",
                    "entries": [
                        "With your DM's approval, you can customize the origin traits granted by your race."
                    ],
                },
            ]
        },
    )
    write_json(
        root / "data/optionalfeatures.json",
        {
            "optionalfeature": [
                {
                    "name": "Blind Fighting",
                    "source": "TCE",
                    "page": 42,
                    "featureType": ["FS:F", "FS:R"],
                    "entries": ["You have blindsight with a range of 10 feet while you are not blinded."],
                },
                {
                    "name": "Superior Technique",
                    "source": "TCE",
                    "page": 42,
                    "featureType": ["FS:F"],
                    "entries": ["You learn one maneuver of your choice and gain one superiority die."],
                },
                {
                    "name": "Druidic Warrior",
                    "source": "TCE",
                    "page": 57,
                    "featureType": ["FS:R"],
                    "entries": ["You learn two druid cantrips of your choice."],
                },
            ]
        },
    )
    write_json(
        root / "data/class/index.json",
        {
            "artificer": "class-artificer.json",
            "barbarian": "class-barbarian.json",
            "fighter": "class-fighter.json",
            "ranger": "class-ranger.json",
        },
    )
    write_json(
        root / "data/class/class-artificer.json",
        {
            "class": [
                {
                    "name": "Artificer",
                    "source": "TCE",
                    "page": 9,
                    "hd": {"number": 1, "faces": 8},
                    "proficiency": ["con", "int"],
                    "classFeatures": ["Infuse Item|Artificer|TCE|2"],
                }
            ],
            "classFeature": [
                {
                    "name": "Infuse Item",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "level": 2,
                    "page": 12,
                    "entries": ["You can infuse mundane items with magic."],
                }
            ],
            "subclass": [
                {
                    "name": "Alchemist",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "page": 14,
                    "subclassFeatures": ["Alchemist|Artificer|TCE|Alchemist|TCE|3"],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Alchemist",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "subclassShortName": "Alchemist",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 14,
                    "entries": ["You learn alchemical formulas and experimental mixtures."],
                }
            ],
        },
    )
    write_json(
        root / "data/class/class-barbarian.json",
        {
            "classFeature": [
                {
                    "name": "Primal Knowledge",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "level": 3,
                    "page": 24,
                    "entries": ["You gain proficiency in a skill from the barbarian class list."],
                },
                {
                    "name": "Instinctive Pounce",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "level": 7,
                    "page": 24,
                    "entries": ["Part of the movement granted by your rage can happen immediately."],
                },
            ],
            "subclass": [
                {
                    "name": "Path of the Beast",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "page": 24,
                    "subclassFeatures": ["Path of the Beast|Barbarian|PHB|Beast|TCE|3"],
                },
                {
                    "name": "Path of Wild Magic",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "page": 25,
                    "subclassFeatures": ["Path of Wild Magic|Barbarian|PHB|Wild Magic|TCE|3"],
                },
            ],
            "subclassFeature": [
                {
                    "name": "Path of the Beast",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "subclassShortName": "Beast",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 24,
                    "entries": ["Your rage channels bestial ferocity."],
                },
                {
                    "name": "Path of Wild Magic",
                    "source": "TCE",
                    "className": "Barbarian",
                    "classSource": "PHB",
                    "subclassShortName": "Wild Magic",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 25,
                    "entries": ["Your rage crackles with unstable magic."],
                },
            ],
        },
    )
    write_json(
        root / "data/class/class-fighter.json",
        {
            "classFeature": [
                {
                    "name": "Martial Versatility",
                    "source": "TCE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "level": 4,
                    "page": 42,
                    "entries": ["Whenever you reach a level that grants the Ability Score Increase feature, you can replace a fighting style option or a maneuver."],
                }
            ],
            "subclass": [
                {
                    "name": "Psi Warrior",
                    "source": "TCE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "page": 42,
                    "subclassFeatures": ["Psi Warrior|Fighter|PHB|Psi Warrior|TCE|3"],
                },
                {
                    "name": "Rune Knight",
                    "source": "TCE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "page": 45,
                    "subclassFeatures": ["Rune Knight|Fighter|PHB|Rune Knight|TCE|3"],
                },
            ],
            "subclassFeature": [
                {
                    "name": "Psi Warrior",
                    "source": "TCE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "subclassShortName": "Psi Warrior",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 42,
                    "entries": ["You awaken psionic power within yourself."],
                },
                {
                    "name": "Rune Knight",
                    "source": "TCE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "subclassShortName": "Rune Knight",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 45,
                    "entries": ["You use runes and giant magic to empower your combat style."],
                },
            ],
        },
    )
    write_json(
        root / "data/class/class-ranger.json",
        {
            "classFeature": [
                {
                    "name": "Deft Explorer",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "level": 1,
                    "page": 56,
                    "entries": ["You gain Canny, Roving, and Tireless as you level."],
                },
                {
                    "name": "Favored Foe",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "level": 1,
                    "page": 56,
                    "entries": ["You can mark a creature as your favored foe."],
                },
                {
                    "name": "Spellcasting Focus",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "level": 2,
                    "page": 57,
                    "entries": ["A druidic focus can serve as a spellcasting focus for your ranger spells."],
                },
            ],
            "subclass": [
                {
                    "name": "Fey Wanderer",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "page": 58,
                    "subclassFeatures": ["Fey Wanderer|Ranger|PHB|Fey Wanderer|TCE|3"],
                },
                {
                    "name": "Swarmkeeper",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "page": 60,
                    "subclassFeatures": ["Swarmkeeper|Ranger|PHB|Swarmkeeper|TCE|3"],
                },
            ],
            "subclassFeature": [
                {
                    "name": "Fey Wanderer",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "subclassShortName": "Fey Wanderer",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 58,
                    "entries": ["The Feywild marks your presence."],
                },
                {
                    "name": "Swarmkeeper",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "subclassShortName": "Swarmkeeper",
                    "subclassSource": "TCE",
                    "level": 3,
                    "page": 60,
                    "entries": ["A writhing swarm answers your call."],
                },
                {
                    "name": "Primal Companion",
                    "source": "TCE",
                    "className": "Ranger",
                    "classSource": "PHB",
                    "subclassShortName": "Beast Master",
                    "subclassSource": "PHB",
                    "level": 3,
                    "page": 61,
                    "entries": ["You magically summon a primal beast companion."],
                },
            ],
        },
    )
    write_json(
        root / "data/book/book-tce.json",
        {
            "data": [
                {
                    "type": "section",
                    "name": "Using This Book",
                    "page": 4,
                    "entries": [
                        {
                            "type": "entries",
                            "name": "What You'll Find Within",
                            "page": 4,
                            "entries": ["This book adds optional tools for players and DMs."],
                        },
                        {
                            "type": "entries",
                            "name": "It's All Optional",
                            "page": 4,
                            "entries": ["Each group decides which optional material belongs in the campaign."],
                        },
                        {
                            "type": "section",
                            "name": "Ten Rules to Remember",
                            "page": 4,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "1. The DM Adjudicates the Rules",
                                    "page": 4,
                                    "entries": ["The DM decides how the rules apply when play reaches an edge case."],
                                },
                                {
                                    "type": "entries",
                                    "name": "2. Exceptions Supersede General Rules",
                                    "page": 4,
                                    "entries": ["Specific features and spells override baseline procedures when they conflict."],
                                },
                                {
                                    "type": "entries",
                                    "name": "3. Advantage and Disadvantage",
                                    "page": 4,
                                    "entries": ["Multiple sources of advantage or disadvantage do not keep stacking."],
                                },
                                {
                                    "type": "entries",
                                    "name": "4. Reaction Timing",
                                    "page": 4,
                                    "entries": ["Reactions resolve after their triggers unless the rule says otherwise."],
                                },
                                {
                                    "type": "entries",
                                    "name": "5. Proficiency Bonus",
                                    "page": 5,
                                    "entries": ["You can apply your proficiency bonus only once to the same roll or DC."],
                                },
                                {
                                    "type": "entries",
                                    "name": "6. Bonus Action Spells",
                                    "page": 5,
                                    "entries": ["Casting a bonus action spell constrains what other spells you can cast that turn."],
                                },
                                {
                                    "type": "entries",
                                    "name": "7. Concentration",
                                    "page": 5,
                                    "entries": ["Only one concentration effect can be maintained at a time."],
                                },
                                {
                                    "type": "entries",
                                    "name": "8. Temporary Hit Points",
                                    "page": 5,
                                    "entries": ["Temporary hit points never stack; you keep the larger pool."],
                                },
                                {
                                    "type": "entries",
                                    "name": "9. Round Down",
                                    "page": 5,
                                    "entries": ["Fractional results round down unless a rule tells you to round another way."],
                                },
                                {
                                    "type": "entries",
                                    "name": "10. Have Fun",
                                    "page": 5,
                                    "entries": [
                                        "The table can adjust the procedure when it keeps the game moving and enjoyable.",
                                        {"type": "quote", "entries": ["The rules help, but the table comes first."]},
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Character Options",
                    "page": 7,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Customizing Your Origin",
                            "page": 7,
                            "entries": [
                                "See the {@variantrule Customizing Your Origin|TCE} entry."
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Changing a Skill",
                            "page": 8,
                            "entries": [
                                "Swap an underused skill proficiency for another one your class offered at 1st level."
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Changing Your Subclass",
                            "page": 8,
                            "entries": [
                                "With your DM's approval, you can replace your subclass when you gain a new subclass feature."
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Artificer",
                            "page": 9,
                            "entries": [
                                {
                                    "type": "section",
                                    "name": "Artificers in Many Worlds",
                                    "page": 9,
                                    "entries": [
                                        "{@class Artificer|TCE} is a full class in this source-backed slice.",
                                        "{@classFeature Infuse Item|Artificer|TCE|2|TCE} anchors the artificer's magical crafting.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Artificer Specialists",
                                    "page": 14,
                                    "entries": [
                                        "{@class Artificer|TCE|Alchemist|Alchemist|TCE} is one of the artificer specialists described here.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Barbarian",
                            "page": 24,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Optional Class Features",
                                    "page": 24,
                                    "entries": [
                                        "{@classFeature Primal Knowledge|Barbarian|PHB|3|TCE} broadens barbarian training.",
                                        "{@classFeature Instinctive Pounce|Barbarian|PHB|7|TCE} improves battlefield movement.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Primal Paths",
                                    "page": 24,
                                    "entries": [
                                        "{@class Barbarian|PHB|Path of the Beast|Beast|TCE} and {@class Barbarian|PHB|Path of Wild Magic|Wild Magic|TCE} are the new barbarian paths in this chapter.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Bard",
                            "page": 27,
                            "entries": ["Bard options in this chapter expand class features and colleges."],
                        },
                        {
                            "type": "section",
                            "name": "Cleric",
                            "page": 30,
                            "entries": ["Cleric options in this chapter expand divine domains and class features."],
                        },
                        {
                            "type": "section",
                            "name": "Druid",
                            "page": 35,
                            "entries": ["Druid options in this chapter expand circles and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Fighter",
                            "page": 41,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Optional Class Features",
                                    "page": 41,
                                    "entries": [
                                        "{@classFeature Martial Versatility|Fighter|PHB|4|TCE} lets fighters retrain part of their toolkit.",
                                        "{@optfeature Blind Fighting|TCE} and {@optfeature Superior Technique|TCE} join the fighter's fighting-style options.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Martial Archetypes",
                                    "page": 42,
                                    "entries": [
                                        "{@class Fighter|PHB|Psi Warrior|Psi Warrior|TCE} and {@class Fighter|PHB|Rune Knight|Rune Knight|TCE} are the new fighter archetypes in this chapter.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Battle Master Builds",
                                    "page": 46,
                                    "entries": [
                                        "Battle Master sample builds remain reference-only guidance for now.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Monk",
                            "page": 48,
                            "entries": ["Monk options in this chapter expand traditions and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Paladin",
                            "page": 52,
                            "entries": ["Paladin options in this chapter expand oaths and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Ranger",
                            "page": 56,
                            "entries": [
                                {
                                    "type": "entries",
                                    "name": "Optional Class Features",
                                    "page": 56,
                                    "entries": [
                                        "{@classFeature Deft Explorer|Ranger|PHB|1|TCE} and {@classFeature Favored Foe|Ranger|PHB|1|TCE} replace baseline ranger features.",
                                        "{@classFeature Spellcasting Focus|Ranger|PHB|2|TCE} and {@optfeature Druidic Warrior|TCE} reinforce the ranger's spell and fighting-style options.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Ranger Archetypes",
                                    "page": 58,
                                    "entries": [
                                        "{@class Ranger|PHB|Fey Wanderer|Fey Wanderer|TCE} and {@class Ranger|PHB|Swarmkeeper|Swarmkeeper|TCE} are the new ranger archetypes in this chapter.",
                                        "{@subclassFeature Primal Companion|Ranger|PHB|Beast Master|PHB|3|TCE} refreshes the Beast Master's companion rules.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Rogue",
                            "page": 62,
                            "entries": ["Rogue options in this chapter expand archetypes and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Sorcerer",
                            "page": 65,
                            "entries": ["Sorcerer options in this chapter expand origins and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Warlock",
                            "page": 70,
                            "entries": ["Warlock options in this chapter expand patrons and optional class features."],
                        },
                        {
                            "type": "section",
                            "name": "Wizard",
                            "page": 75,
                            "entries": ["Wizard options in this chapter expand traditions and optional class features."],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Group Patrons",
                    "page": 83,
                    "entries": [
                        "A group patron gives an adventuring party a shared purpose, a source of support, and a reliable way to frame the campaign's ongoing work.",
                        {
                            "type": "entries",
                            "name": "How Patrons Work",
                            "page": 83,
                            "entries": [
                                "Patrons offer the party concrete benefits, expected obligations, and a strong campaign premise that ties the group together.",
                                {
                                    "type": "entries",
                                    "name": "Group Assistance",
                                    "page": 83,
                                    "entries": [
                                        "A patron-backed party can coordinate more effectively when members support one another in the field.",
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Example Patrons",
                            "page": 84,
                            "entries": [
                                "Academic institutions, military commands, criminal syndicates, religious orders, and guilds can all serve as patrons.",
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Being Your Own Patron",
                            "page": 94,
                            "entries": [
                                "The party can also form its own organization and treat that collective identity as the campaign's patron.",
                            ],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Magical Miscellany",
                    "page": 105,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Spells",
                            "page": 105,
                            "entries": [
                                "This chapter opens with new spells before shifting into cosmetic spell themes and magic items.",
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Personalizing Spells",
                            "page": 116,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "What use is magic if you can't harness it to amuse your mom?",
                                    ],
                                },
                                "Spellcasters can customize the cosmetic effects of their magic without changing how a spell actually works.",
                                "Themes can reinforce the caster's training, beliefs, favored colors, or relationship to a season, culture, or supernatural force.",
                                {
                                    "type": "table",
                                    "caption": "Magic Themes",
                                    "colLabels": ["d4", "Theme"],
                                    "rows": [
                                        ["1", "Book pages, ink, and rustling library scents"],
                                        ["2", "Brine-scented sea creatures and drifting spray"],
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Magic Items",
                            "page": 118,
                            "entries": [
                                "After spell guidance, the chapter turns to new magic items and artifacts.",
                                {
                                    "type": "section",
                                    "name": "Magic Tattoos",
                                    "page": 118,
                                    "entries": [
                                        "Magic tattoos merge artistry and enchantment, binding wondrous power directly to a creature's body.",
                                        "A tattoo can look like a brand, scarification, a birthmark, patterns of scales, or another cosmetic alteration.",
                                        {
                                            "type": "table",
                                            "caption": "Magic Tattoo Coverage",
                                            "colLabels": ["Tattoo Rarity", "Area Covered"],
                                            "rows": [
                                                ["Common", "One hand or foot or a quarter of a limb"],
                                                ["Uncommon", "Half a limb or the scalp"],
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "section",
                                    "name": "Magic Item Descriptions",
                                    "page": 119,
                                    "entries": [
                                        "The chapter closes with item descriptions in alphabetical order.",
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Dungeon Master's Tools",
                    "page": 139,
                    "entries": [
                        {
                            "type": "section",
                            "name": "Session Zero",
                            "page": 139,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "Set expectations early so the campaign has room to breathe."
                                    ],
                                },
                                "A session zero gives the DM and players time to align on campaign expectations, tone, and house rules before play begins.",
                                {
                                    "type": "entries",
                                    "name": "Character and Party Creation",
                                    "page": 139,
                                    "entries": [
                                        "Build characters with the campaign's likely challenges in mind, and encourage the group to talk through how those characters fit together.",
                                        {
                                            "type": "entries",
                                            "name": "Party Formation",
                                            "page": 139,
                                            "entries": [
                                                "Use party-creation questions to decide why the adventurers stay together and what shared history already connects them.",
                                                {
                                                    "type": "table",
                                                    "caption": "Party Origin",
                                                    "colLabels": ["d6", "Origin Story"],
                                                    "rows": [
                                                        ["1", "The characters grew up in the same place."],
                                                        ["2", "The characters united against a shared foe."],
                                                    ],
                                                },
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Running a Game for One Player",
                                            "page": 140,
                                            "entries": [
                                                "A one-player campaign benefits from extra backstory work and a clear plan for whether a sidekick should round out the party.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Social Contract",
                                    "page": 140,
                                    "entries": [
                                        "Talk directly about the kind of game everyone wants so the table's expectations are explicit instead of assumed.",
                                        {
                                            "type": "entries",
                                            "name": "Hard and Soft Limits",
                                            "page": 141,
                                            "entries": [
                                                "Document the themes and behaviors the table wants to avoid or handle with extra care.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Game Customization",
                                    "page": 141,
                                    "entries": [
                                        "Ask players what kinds of challenges, tone, and advancement style they want the campaign to emphasize.",
                                        {
                                            "type": "entries",
                                            "name": "House Rules",
                                            "page": 141,
                                            "entries": [
                                                "Present house rules as experiments and revisit them if they stop making the game more fun.",
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Sidekicks",
                            "page": 142,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "A sidekick-in-training could learn a few tricks from this section."
                                    ],
                                },
                                "These rules let a low-CR ally join the party as a special NPC sidekick.",
                                {
                                    "type": "entries",
                                    "name": "Creating a Sidekick",
                                    "page": 142,
                                    "entries": [
                                        "Choose a creature with a modest challenge rating and a reason to adventure with the group."
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Gaining a Sidekick Class",
                                    "page": 143,
                                    "entries": [
                                        "Each sidekick follows one simple class: Expert, Spellcaster, or Warrior.",
                                        {
                                            "type": "entries",
                                            "name": "Starting Level",
                                            "page": 143,
                                            "entries": [
                                                "A sidekick usually begins close to the party's current level."
                                            ],
                                        },
                                        {
                                            "type": "entries",
                                            "name": "Leveling Up a Sidekick",
                                            "page": 143,
                                            "entries": [
                                                "When the group advances, the sidekick can gain levels as well."
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Parleying with Monsters",
                            "page": 148,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "A clever conversation can end an encounter before the first blade leaves its sheath."
                                    ],
                                },
                                "Not every monster encounter begins or ends with violence if the party can figure out what the creature wants.",
                                {
                                    "type": "entries",
                                    "name": "Monster Research",
                                    "page": 148,
                                    "entries": [
                                        "Characters can study a creature's nature before opening negotiations.",
                                        {
                                            "type": "table",
                                            "caption": "Monster Research",
                                            "colLabels": ["Type", "Suggested Skills"],
                                            "rows": [
                                                ["Aberration", "Arcana"],
                                                ["Beast", "Animal Handling, Nature, or Survival"],
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Monsters' Desires",
                                    "page": 148,
                                    "entries": [
                                        "Different creature types respond to different offerings.",
                                        {
                                            "type": "table",
                                            "caption": "Beasts",
                                            "colLabels": ["d4", "Desired Offering"],
                                            "rows": [
                                                ["1", "Fresh meat"],
                                                ["2", "A soothing melody"],
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Environmental Hazards",
                            "page": 150,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "The land itself can become the encounter when magic reshapes it."
                                    ],
                                },
                                "This section explores how to add fantastical challenges to any locale and ways to further bring an adventure's setting to life.",
                                {
                                    "type": "entries",
                                    "name": "Supernatural Regions",
                                    "page": 150,
                                    "entries": [
                                        "A supernatural region is warped by planar energy, lingering magic, or tragedy.",
                                        {
                                            "type": "entries",
                                            "name": "Blessed Radiance",
                                            "page": 150,
                                            "entries": [
                                                "Golden light bolsters allies and scorches fiends and undead.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Magical Phenomena",
                                    "page": 163,
                                    "entries": [
                                        "Localized magical events can make familiar terrain behave in uncanny ways.",
                                        {
                                            "type": "entries",
                                            "name": "Eldritch Storms",
                                            "page": 163,
                                            "entries": [
                                                "Arcane tempests lash the area with dangerous power.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Natural Hazards",
                                    "page": 169,
                                    "entries": [
                                        "The world still threatens travelers with mundane dangers alongside magical ones.",
                                        {
                                            "type": "entries",
                                            "name": "Spell Equivalents of Natural Hazards",
                                            "page": 170,
                                            "entries": [
                                                "Spells can approximate avalanches, sinkholes, and similar threats when you need a fast ruling.",
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "name": "Puzzles",
                            "page": 171,
                            "entries": [
                                {
                                    "type": "quote",
                                    "entries": [
                                        "Why create a solvable puzzle? Just pose an enigmatic question without an answer and watch your trespassers squirm!",
                                    ],
                                },
                                "Puzzles add collaborative problem solving to a campaign and can challenge characters without relying on combat statistics.",
                                {
                                    "type": "entries",
                                    "name": "Why Use Puzzles?",
                                    "page": 171,
                                    "entries": [
                                        "Puzzles invite teamwork, reward curiosity, and can make a location feel mysterious or magical.",
                                        {
                                            "type": "entries",
                                            "name": "Puzzle Elements",
                                            "page": 171,
                                            "entries": [
                                                "A good puzzle has a clear presentation, an understandable goal, and room for the group to experiment.",
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Creature Paintings",
                                    "page": 173,
                                    "entries": [
                                        "This sample puzzle asks the group to interpret murals of different creatures to unlock the next chamber.",
                                    ],
                                },
                                {
                                    "type": "entries",
                                    "name": "Reckless Steps",
                                    "page": 175,
                                    "entries": [
                                        "This sample puzzle tests whether the party can interpret a hazardous floor's hidden movement rules.",
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ]
        },
    )
    return data_root
