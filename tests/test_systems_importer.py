from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from player_wiki.systems_importer import Dnd5eSystemsImporter
from player_wiki.systems_models import SystemsEntryRecord


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_test_data_root(root: Path) -> Path:
    write_json(
        root / "data/actions.json",
        {
            "action": [
                {
                    "name": "Help",
                    "source": "PHB",
                    "page": 192,
                    "time": [{"number": 1, "unit": "action"}],
                    "entries": ["You can lend your aid to another creature in the completion of a task."]
                }
            ]
        },
    )
    write_json(
        root / "data/spells/spells-phb.json",
        {
            "spell": [
                {
                    "name": "Mage Hand",
                    "source": "PHB",
                    "page": 256,
                    "level": 0,
                    "school": "C",
                    "time": [{"number": 1, "unit": "action"}],
                    "range": {"type": "point", "distance": {"type": "feet", "amount": 30}},
                    "components": {"v": True, "s": True},
                    "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 1}}],
                    "entries": [
                        "A spectral, floating hand appears at a point you choose within range."
                    ],
                }
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
                        {"name": "Nimble Escape", "entries": ["The goblin can take the Disengage or Hide action as a bonus action."]}
                    ],
                    "action": [
                        {
                            "name": "Scimitar",
                            "entries": ["{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."]
                        }
                    ],
                    "hasToken": True,
                    "hasFluffImages": True,
                    "soundClip": {"type": "internal", "path": "monster/goblin.mp3"},
                    "altArt": [{"name": "Goblin Sketch", "source": "MM"}],
                }
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
                    "entries": ["A blinded creature can't see."]
                }
            ],
            "disease": [],
            "status": [
                {
                    "name": "Concentration",
                    "source": "PHB",
                    "page": 203,
                    "entries": ["You can concentrate on only one spell at a time."]
                }
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
                    "entries": ["Your Strength check covers difficult situations you encounter while climbing, jumping, or swimming."]
                }
            ]
        },
    )
    write_json(
        root / "data/senses.json",
        {
            "sense": [
                {
                    "name": "Darkvision",
                    "source": "PHB",
                    "page": 183,
                    "entries": ["A creature with darkvision can see in dim light within a specified radius as if it were bright light."]
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
                    "entries": ["If you carry weight in excess of 5 times your Strength score, you are encumbered."]
                }
            ]
        },
    )
    write_json(
        root / "data/feats.json",
        {
            "feat": [
                {
                    "name": "Alert",
                    "source": "PHB",
                    "page": 165,
                    "entries": ["Always on the lookout for danger, you gain the following benefits."]
                }
            ]
        },
    )
    write_json(
        root / "data/backgrounds.json",
        {
            "background": [
                {
                    "name": "Acolyte",
                    "source": "PHB",
                    "page": 127,
                    "skillProficiencies": [{"insight": True, "religion": True}],
                    "entries": ["You have spent your life in the service of a temple."]
                }
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
                    "entries": ["A versatile martial weapon."]
                }
            ],
            "itemGroup": [],
        },
    )
    write_json(
        root / "data/items-base.json",
        {
            "baseitem": [
                {
                    "name": "Chain Mail",
                    "source": "PHB",
                    "page": 145,
                    "type": "HA",
                    "armor": True,
                    "ac": 16,
                    "strength": "13",
                    "stealth": True,
                    "weight": 55,
                    "entries": ["Heavy armor made of interlocking metal rings."]
                },
                {
                    "name": "Light Crossbow",
                    "source": "PHB",
                    "page": 149,
                    "type": "R",
                    "weapon": True,
                    "weight": 5,
                    "entries": ["A martial ranged weapon with loading and two-handed properties."]
                },
                {
                    "name": "Crossbow Bolts (20)",
                    "source": "PHB",
                    "page": 150,
                    "type": "A",
                    "ammo": True,
                    "weight": 1.5,
                    "entries": ["A case of twenty crossbow bolts."]
                },
            ]
        },
    )
    write_json(
        root / "data/optionalfeatures.json",
        {
            "optionalfeature": [
                {
                    "name": "Archery",
                    "source": "PHB",
                    "page": 72,
                    "featureType": ["FS:F", "FS:R"],
                    "entries": ["You gain a +2 bonus to attack rolls you make with ranged weapons."]
                },
                {
                    "name": "Defense",
                    "source": "PHB",
                    "page": 72,
                    "featureType": ["FS:F", "FS:P", "FS:R"],
                    "entries": ["While you are wearing armor, you gain a +1 bonus to AC."]
                },
                {
                    "name": "Agonizing Blast",
                    "source": "PHB",
                    "page": 110,
                    "featureType": ["EI"],
                    "entries": ["When you cast {@spell eldritch blast}, add your Charisma modifier to the damage it deals on a hit."]
                }
            ]
        },
    )
    write_json(
        root / "data/races.json",
        {
            "race": [
                {
                    "name": "Dragonborn",
                    "source": "PHB",
                    "page": 32,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"str": 2, "cha": 1}],
                    "entries": [
                        {
                            "name": "Draconic Ancestry",
                            "type": "entries",
                            "entries": ["You have draconic ancestry."],
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
                    "name": "Elf",
                    "source": "PHB",
                    "page": 23,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"dex": 2}],
                    "entries": [
                        {
                            "name": "Darkvision",
                            "type": "entries",
                            "entries": ["Accustomed to twilit forests and the night sky, you have superior vision in dark and dim conditions."],
                        }
                    ],
                },
                {
                    "name": "Human",
                    "source": "PHB",
                    "page": 29,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "languageProficiencies": [{"common": True, "anyStandard": 1}],
                    "entries": [
                        {
                            "name": "Age",
                            "type": "entries",
                            "entries": ["Humans reach adulthood in their late teens and live less than a century."],
                        },
                        {
                            "name": "Size",
                            "type": "entries",
                            "entries": ["Humans vary widely in height and build, but your size is Medium."],
                        },
                    ],
                },
                {
                    "name": "Aasimar",
                    "source": "VGM",
                    "page": 104,
                    "size": ["M"],
                    "speed": {"walk": 30},
                    "ability": [{"cha": 2}],
                    "languageProficiencies": [{"common": True, "celestial": True}],
                    "entries": [
                        {
                            "name": "Celestial Resistance",
                            "type": "entries",
                            "entries": ["You have resistance to necrotic damage and radiant damage."],
                        }
                    ],
                },
            ],
            "subrace": [
                {
                    "name": "Hill",
                    "source": "PHB",
                    "raceName": "Dwarf",
                    "raceSource": "PHB",
                    "page": 20,
                    "ability": [{"wis": 1}],
                    "entries": [
                        {
                            "name": "Dwarven Toughness",
                            "type": "entries",
                            "entries": ["Your hit point maximum increases by 1, and it increases by 1 every time you gain a level."],
                        }
                    ],
                },
                {
                    "name": "Mountain",
                    "source": "PHB",
                    "raceName": "Dwarf",
                    "raceSource": "PHB",
                    "page": 20,
                    "ability": [{"str": 2}],
                    "entries": [
                        {
                            "name": "Dwarven Armor Training",
                            "type": "entries",
                            "entries": ["You have proficiency with light and medium armor."],
                        }
                    ],
                },
                {
                    "name": "Drow",
                    "source": "PHB",
                    "raceName": "Elf",
                    "raceSource": "PHB",
                    "page": 24,
                    "ability": [{"cha": 1}],
                    "entries": [
                        {
                            "name": "Superior Darkvision",
                            "type": "entries",
                            "entries": ["You can see in dim light within 120 feet of you as if it were bright light."],
                            "data": {"overwrite": "Darkvision"},
                        }
                    ],
                },
                {
                    "name": "High",
                    "source": "PHB",
                    "raceName": "Elf",
                    "raceSource": "PHB",
                    "page": 24,
                    "ability": [{"int": 1}],
                    "entries": [
                        {
                            "name": "Elf Weapon Training",
                            "type": "entries",
                            "entries": ["You have proficiency with the longsword, shortsword, shortbow, and longbow."],
                        }
                    ],
                },
                {
                    "name": "Variant",
                    "source": "PHB",
                    "raceName": "Human",
                    "raceSource": "PHB",
                    "page": 31,
                    "ability": [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"], "count": 2}}],
                    "feats": [{"any": 1}],
                    "skillProficiencies": [{"any": 1}],
                    "entries": [
                        {
                            "name": "Skills",
                            "type": "entries",
                            "entries": ["You gain proficiency in one skill of your choice."],
                        },
                        {
                            "name": "Feat",
                            "type": "entries",
                            "entries": ["You gain one feat of your choice."],
                        },
                    ],
                },
                {
                    "name": "Fallen",
                    "source": "VGM",
                    "raceName": "Aasimar",
                    "raceSource": "VGM",
                    "page": 105,
                    "ability": [{"str": 1}],
                    "entries": [
                        {
                            "name": "Necrotic Shroud",
                            "type": "entries",
                            "entries": ["Starting at 3rd level, you can use your action to unleash the divine energy within yourself."],
                        }
                    ],
                },
                {
                    "name": "Draconblood",
                    "source": "EGW",
                    "raceName": "Dragonborn",
                    "raceSource": "PHB",
                    "page": 168,
                    "ability": [{"int": 2, "cha": 1}],
                    "entries": [
                        {
                            "name": "Forceful Presence",
                            "type": "entries",
                            "entries": ["When you make a Charisma (Intimidation or Persuasion) check, you can do so with advantage."],
                        }
                    ],
                }
            ],
        },
    )
    write_json(root / "data/class/index.json", {"fighter": "class-fighter.json"})
    write_json(
        root / "data/class/class-fighter.json",
        {
            "class": [
                {
                    "name": "Fighter",
                    "source": "PHB",
                    "page": 70,
                    "hd": {"number": 1, "faces": 10},
                    "proficiency": ["str", "con"],
                    "startingProficiencies": {
                        "armor": ["light", "medium", "heavy", "shield"],
                        "weapons": ["simple", "martial"],
                        "skills": [{"choose": {"from": ["athletics", "history"], "count": 2}}],
                    },
                    "startingEquipment": {
                        "default": ["Chain mail", "A martial weapon and a shield"],
                        "goldAlternative": "{@dice 5d4 x 10}",
                    },
                    "multiclassing": {
                        "requirements": {"or": [{"str": 13, "dex": 13}]},
                        "proficienciesGained": {"armor": ["light", "medium", "shield"]},
                    },
                    "subclassTitle": "Martial Archetype",
                    "classFeatures": [
                        "Fighting Style|Fighter||1",
                        {"classFeature": "Martial Archetype|Fighter||3", "gainSubclassFeature": True},
                    ],
                    "optionalfeatureProgression": [
                        {"name": "Fighting Style", "featureType": ["FS:F"], "progression": {"1": 1}}
                    ],
                }
            ],
            "subclass": [
                {
                    "name": "Battle Master",
                    "source": "PHB",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "page": 73,
                    "subclassFeatures": ["Combat Superiority|Fighter||Battle Master||3"],
                }
            ],
            "classFeature": [
                {
                    "name": "Fighting Style",
                    "source": "PHB",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "level": 1,
                    "page": 72,
                    "entries": [
                        "You adopt a particular style of fighting as your specialty.",
                        {
                            "type": "options",
                            "count": 1,
                            "entries": [
                                {"type": "refOptionalfeature", "optionalfeature": "Archery"},
                                {"type": "refOptionalfeature", "optionalfeature": "Defense"},
                            ],
                        },
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Combat Superiority",
                    "source": "PHB",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "subclassShortName": "Battle Master",
                    "subclassSource": "PHB",
                    "level": 3,
                    "page": 73,
                    "entries": ["You learn maneuvers that are fueled by special dice called superiority dice."],
                }
            ],
        },
    )
    return root


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


def build_magicvariant_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/magicvariants.json",
        {
            "magicvariant": [
                {
                    "name": "+1 Armor",
                    "edition": "classic",
                    "type": "GV|DMG",
                    "requires": [{"armor": True}],
                    "inherits": {
                        "namePrefix": "+1 ",
                        "source": "DMG",
                        "page": 152,
                        "rarity": "rare",
                        "bonusAc": "+1",
                        "entries": ["You have a {=bonusAc} bonus to AC while wearing this armor."],
                    },
                }
            ]
        },
    )
    return data_root


def build_scag_background_data_root(root: Path) -> Path:
    write_json(
        root / "data/backgrounds.json",
        {
            "background": [
                {
                    "name": "Clan Crafter",
                    "source": "SCAG",
                    "page": 145,
                    "skillProficiencies": [{"history": True, "insight": True}],
                    "languageProficiencies": [{"dwarvish": True}, {"anyStandard": 1}],
                    "toolProficiencies": [{"anyArtisansTool": 1}],
                    "startingEquipment": [
                        {
                            "_": [
                                {"equipmentType": "toolArtisan"},
                                {"special": "maker's mark chisel"},
                                "traveler's clothes|phb",
                                {"item": "pouch|phb", "containsValue": 1500},
                            ]
                        }
                    ],
                    "entries": [
                        {
                            "name": "Feature: Respect of the Stout Folk",
                            "type": "entries",
                            "entries": [
                                "Dwarves offer you hospitality and assistance in their settlements."
                            ],
                            "data": {"isFeature": True},
                        }
                    ],
                }
            ]
        },
    )
    return root


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
                                        ["Aasimar", "4'8\"", "110 lb.", "+{@dice 2d10}", "× ({@dice 2d4}) lb."],
                                        ["{@race Firbolg|VGM}", "6'2\"", "175 lb.", "+{@dice 2d12}", "× ({@dice 2d6}) lb."],
                                        ["{@race Triton|VGM}", "4'6\"", "90 lb.", "+{@dice 2d10}", "× ({@dice 2d4}) lb."],
                                        ["{@race Bugbear|VGM}", "6'0\"", "200 lb.", "+{@dice 2d12}", "× ({@dice 2d6}) lb."],
                                        [
                                            "{@race Yuan-ti Pureblood|VGM}",
                                            "4'8\"",
                                            "110 lb.",
                                            "+{@dice 2d10}",
                                            "× ({@dice 2d4}) lb.",
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


def build_additional_spell_metadata_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"cleric": "class-cleric.json"})
    write_json(
        root / "data/class/class-cleric.json",
        {
            "class": [
                {
                    "name": "Cleric",
                    "source": "PHB",
                    "page": 56,
                    "hd": {"number": 1, "faces": 8},
                    "proficiency": ["wis", "cha"],
                    "subclassTitle": "Divine Domain",
                    "classFeatures": ["Spellcasting|Cleric||1"],
                    "additionalSpells": [
                        {
                            "prepared": {
                                "1": ["ceremony"],
                            }
                        }
                    ],
                }
            ],
            "subclass": [
                {
                    "name": "Life Domain",
                    "source": "PHB",
                    "className": "Cleric",
                    "classSource": "PHB",
                    "page": 60,
                    "subclassFeatures": ["Disciple of Life|Cleric||Life||1"],
                    "additionalSpells": [
                        {
                            "prepared": {
                                "1": ["bless", "cure wounds"],
                                "3": ["lesser restoration", "spiritual weapon"],
                            }
                        }
                    ],
                }
            ],
            "classFeature": [
                {
                    "name": "Spellcasting",
                    "source": "PHB",
                    "className": "Cleric",
                    "classSource": "PHB",
                    "level": 1,
                    "page": 58,
                    "entries": ["You can cast prepared cleric spells."],
                    "additionalSpells": [
                        {
                            "prepared": {
                                "1": ["guidance"],
                            }
                        }
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Disciple of Life",
                    "source": "PHB",
                    "className": "Cleric",
                    "classSource": "PHB",
                    "subclassShortName": "Life",
                    "subclassSource": "PHB",
                    "level": 1,
                    "page": 60,
                    "entries": ["Your healing spells are more effective."],
                    "additionalSpells": [
                        {
                            "prepared": {
                                "1": ["bless"],
                            }
                        }
                    ],
                }
            ],
        },
    )
    return root


def build_large_feat_data_root(root: Path, *, count: int) -> Path:
    write_json(
        root / "data/feats.json",
        {
            "feat": [
                {
                    "name": f"Feat {index:03d}",
                    "source": "PHB",
                    "page": index + 1,
                    "entries": [f"Feat {index:03d} benefit text."],
                }
                for index in range(count)
            ]
        },
    )
    return root


def build_feat_metadata_data_root(root: Path) -> Path:
    write_json(
        root / "data/feats.json",
        {
            "feat": [
                {
                    "name": "Resilient",
                    "source": "PHB",
                    "page": 168,
                    "ability": [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"], "amount": 1}}],
                    "savingThrowProficiencies": [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"]}}],
                    "entries": ["Choose one ability score. Increase it by 1 and gain saving throw proficiency with it."],
                },
                {
                    "name": "Skilled",
                    "source": "PHB",
                    "page": 170,
                    "skillToolLanguageProficiencies": [
                        {
                            "choose": [
                                {
                                    "from": ["anySkill", "anyTool"],
                                    "count": 3,
                                }
                            ]
                        }
                    ],
                    "entries": ["Gain three skill or tool proficiencies."],
                },
            ]
        },
    )
    return root


def build_xphb_variant_subclass_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"wizard": "class-wizard.json"})
    write_json(
        root / "data/class/class-wizard.json",
        {
            "subclass": [
                {
                    "name": "Chronurgy Magic",
                    "source": "EGW",
                    "className": "Wizard",
                    "classSource": "PHB",
                    "page": 184,
                    "subclassFeatures": ["Chronurgy Magic|Wizard||Chronurgy||2"],
                },
                {
                    "name": "Chronurgy Magic",
                    "source": "EGW",
                    "className": "Wizard",
                    "classSource": "XPHB",
                    "page": 184,
                    "subclassFeatures": ["Chronurgy Magic|Wizard|XPHB|Chronurgy||3"],
                },
            ],
            "subclassFeature": [
                {
                    "name": "Chronurgy Magic",
                    "source": "EGW",
                    "className": "Wizard",
                    "classSource": "PHB",
                    "subclassShortName": "Chronurgy",
                    "subclassSource": "EGW",
                    "level": 2,
                    "page": 184,
                    "entries": ["PHB subclass variant."],
                },
                {
                    "name": "Chronurgy Magic",
                    "source": "EGW",
                    "className": "Wizard",
                    "classSource": "XPHB",
                    "subclassShortName": "Chronurgy",
                    "subclassSource": "EGW",
                    "level": 3,
                    "page": 184,
                    "entries": ["XPHB subclass variant."],
                },
            ],
        },
    )
    return root


def build_efa_variant_subclass_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"artificer": "class-artificer.json"})
    write_json(
        root / "data/class/class-artificer.json",
        {
            "subclass": [
                {
                    "name": "Alchemist",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "page": 14,
                    "subclassFeatures": ["Alchemist|Artificer|TCE|Alchemist|TCE|3"],
                },
                {
                    "name": "Alchemist",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "EFA",
                },
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
                    "entries": ["TCE artificer subclass entry."],
                }
            ],
        },
    )
    return root


def build_class_optionalfeature_progression_data_root(root: Path) -> Path:
    write_json(
        root / "data/optionalfeatures.json",
        {
            "optionalfeature": [
                {
                    "name": "Agonizing Blast",
                    "source": "PHB",
                    "page": 110,
                    "featureType": ["EI"],
                    "entries": ["Add your Charisma modifier to the damage of {@spell eldritch blast} on a hit."],
                },
                {
                    "name": "Armor of Shadows",
                    "source": "PHB",
                    "page": 110,
                    "featureType": ["EI"],
                    "entries": ["You can cast {@spell mage armor} on yourself at will, without expending a spell slot or material components."],
                },
                {
                    "name": "Enhanced Arcane Focus",
                    "source": "TCE",
                    "page": 20,
                    "featureType": ["AI"],
                    "entries": ["This item grants a +1 bonus to spell attack rolls."],
                },
                {
                    "name": "Mind Sharpener",
                    "source": "TCE",
                    "page": 21,
                    "featureType": ["AI"],
                    "entries": ["The infused item can send a jolt to refocus the wearer's concentration."],
                },
            ]
        },
    )
    write_json(
        root / "data/class/index.json",
        {
            "warlock": "class-warlock.json",
            "artificer": "class-artificer.json",
        },
    )
    write_json(
        root / "data/class/class-warlock.json",
        {
            "class": [
                {
                    "name": "Warlock",
                    "source": "PHB",
                    "page": 105,
                    "hd": {"number": 1, "faces": 8},
                    "proficiency": ["wis", "cha"],
                    "classFeatures": [
                        "Eldritch Invocations|Warlock||2",
                    ],
                    "optionalfeatureProgression": [
                        {
                            "name": "Eldritch Invocations",
                            "featureType": ["EI"],
                            "progression": [0, 2, 2, 2, 3, 3],
                        }
                    ],
                }
            ],
            "classFeature": [
                {
                    "name": "Eldritch Invocations",
                    "source": "PHB",
                    "className": "Warlock",
                    "classSource": "PHB",
                    "level": 2,
                    "page": 110,
                    "entries": [
                        "You gain two eldritch invocations of your choice.",
                        "A list of the available options can be found on the {@filter Optional Features|optionalfeatures|Feature Type=EI} page.",
                    ],
                }
            ],
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
                    "classFeatures": [
                        "Infuse Item|Artificer|TCE|2",
                        "Infusions Known|Artificer|TCE|2",
                    ],
                    "optionalfeatureProgression": [
                        {
                            "name": "Infusions",
                            "featureType": ["AI"],
                            "progression": [0, 4, 4, 4, 4, 6],
                        }
                    ],
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
                    "entries": [
                        "You have learned to imbue mundane items with certain magical infusions.",
                    ],
                },
                {
                    "name": "Infusions Known",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "level": 2,
                    "page": 12,
                    "entries": [
                        "Choose artificer infusions from the Optional Features section.",
                    ],
                },
            ],
        },
    )
    return root


def build_class_progression_metadata_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"artificer": "class-artificer.json"})
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
                    "spellcastingAbility": "int",
                    "casterProgression": "artificer",
                    "preparedSpells": "<$level$> / 2 + <$int_mod$>",
                    "cantripProgression": [2, 2, 2],
                    "startingProficiencies": {
                        "armor": ["light", "medium", "shield"],
                        "weapons": ["simple"],
                        "tools": ["thieves' tools", "tinker's tools"],
                        "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "medicine"]}}],
                    },
                    "classTableGroups": [
                        {
                            "colLabels": [
                                "{@filter Infusions Known|optionalfeatures|feature type=ai|source=TCE}",
                                "Infused Items",
                                "{@filter Cantrips Known|spells|level=0|class=artificer}",
                            ],
                            "rows": [
                                [0, 0, 2],
                                [4, 2, 2],
                                [4, 2, 2],
                            ],
                        },
                        {
                            "title": "Spell Slots per Spell Level",
                            "colLabels": [
                                "{@filter 1st|spells|level=1|class=Artificer}",
                                "{@filter 2nd|spells|level=2|class=Artificer}",
                                "{@filter 3rd|spells|level=3|class=Artificer}",
                                "{@filter 4th|spells|level=4|class=Artificer}",
                                "{@filter 5th|spells|level=5|class=Artificer}",
                            ],
                            "rowsSpellProgression": [
                                [2, 0, 0, 0, 0],
                                [2, 0, 0, 0, 0],
                                [3, 0, 0, 0, 0],
                            ],
                        },
                    ],
                    "classFeatures": [
                        "Magical Tinkering|Artificer|TCE|1",
                        "Infuse Item|Artificer|TCE|2",
                    ],
                }
            ],
            "classFeature": [
                {
                    "name": "Magical Tinkering",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "level": 1,
                    "entries": ["You learn how to invest a spark of magic into mundane objects."],
                },
                {
                    "name": "Infuse Item",
                    "source": "TCE",
                    "className": "Artificer",
                    "classSource": "TCE",
                    "level": 2,
                    "entries": ["You can infuse mundane items with certain magical infusions."],
                },
            ],
        },
    )
    write_json(
        root / "data/spells/spells-tce.json",
        {
            "spell": [
                {
                    "name": "Guidance",
                    "source": "TCE",
                    "page": 1,
                    "level": 0,
                    "school": "D",
                    "time": [{"number": 1, "unit": "action"}],
                    "range": {"type": "touch"},
                    "components": {"v": True, "s": True},
                    "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 1}, "concentration": True}],
                    "entries": ["You touch one willing creature."],
                }
            ]
        },
    )
    write_json(
        root / "data/generated/gendata-spell-source-lookup.json",
        {
            "tce": {
                "guidance": {
                    "class": {
                        "TCE": {"Artificer": True},
                    }
                }
            }
        },
    )
    return root


def build_spell_metadata_data_root(root: Path) -> Path:
    write_json(
        root / "data/spells/spells-phb.json",
        {
            "spell": [
                {
                    "name": "Detect Magic",
                    "source": "PHB",
                    "page": 231,
                    "level": 1,
                    "school": "D",
                    "time": [{"number": 1, "unit": "action"}],
                    "range": {"type": "self"},
                    "components": {"v": True, "s": True},
                    "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 10}}],
                    "meta": {"ritual": True},
                    "entries": ["For the duration, you sense the presence of magic within 30 feet of you."],
                }
            ]
        },
    )
    return root


XGE_ATOMIC_WRAPPER_TEST_TITLES = (
    "Simultaneous Effects",
    "Falling",
    "Sleep",
    "Waking Someone",
    "Adamantine Weapons",
    "Tying Knots",
    "Identifying a Spell",
    "Variant Rules",
)


def build_xge_atomic_wrapper_book_data_root(root: Path) -> Path:
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
                            "entries": ["Encounter building weighs party size, monster count, and expected difficulty."],
                        },
                        {
                            "type": "entries",
                            "name": "Random Encounters: A World of Possibilities",
                            "page": 92,
                            "entries": ["Random encounters can do more than trigger a fight."],
                        },
                        {
                            "type": "entries",
                            "name": "Traps Revisited",
                            "page": 113,
                            "entries": ["Traps range from quick hazards to elaborate multi-round challenges."],
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


def build_subclass_optionalfeature_progression_data_root(root: Path) -> Path:
    write_json(
        root / "data/optionalfeatures.json",
        {
            "optionalfeature": [
                {
                    "name": "Banishing Arrow",
                    "source": "XGE",
                    "page": 29,
                    "featureType": ["AS"],
                    "entries": ["A creature hit by the arrow is briefly banished."],
                },
                {
                    "name": "Bursting Arrow",
                    "source": "XGE",
                    "page": 29,
                    "featureType": ["AS"],
                    "entries": ["The arrow detonates after your attack."],
                },
            ]
        },
    )
    write_json(root / "data/class/index.json", {"fighter": "class-fighter.json"})
    write_json(
        root / "data/class/class-fighter.json",
        {
            "subclass": [
                {
                    "name": "Arcane Archer",
                    "source": "XGE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "page": 28,
                    "subclassFeatures": ["Arcane Shot Options|Fighter||Arcane Archer|XGE|3"],
                    "optionalfeatureProgression": [
                        {
                            "name": "Arcane Shots",
                            "featureType": ["AS"],
                            "progression": {"3": 2},
                        }
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Arcane Shot Options",
                    "source": "XGE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "subclassShortName": "Arcane Archer",
                    "subclassSource": "XGE",
                    "level": 3,
                    "page": 28,
                    "entries": [
                        "You learn two Arcane Shot options of your choice.",
                        {
                            "type": "options",
                            "count": 2,
                            "entries": [
                                {"type": "refOptionalfeature", "optionalfeature": "Banishing Arrow"},
                                {"type": "refOptionalfeature", "optionalfeature": "Bursting Arrow"},
                            ],
                        },
                    ],
                }
            ],
        },
    )
    return root


def build_subclass_short_name_matching_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"bard": "class-bard.json"})
    write_json(
        root / "data/class/class-bard.json",
        {
            "subclass": [
                {
                    "name": "College of Lore",
                    "source": "PHB",
                    "className": "Bard",
                    "classSource": "PHB",
                    "page": 54,
                    "subclassFeatures": [
                        "College of Lore|Bard||Lore||3",
                        "Bonus Proficiencies|Bard||Lore||3",
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "College of Lore",
                    "source": "PHB",
                    "className": "Bard",
                    "classSource": "PHB",
                    "subclassShortName": "Lore",
                    "subclassSource": "PHB",
                    "level": 3,
                    "page": 54,
                    "entries": ["The College of Lore pursues beauty and truth."],
                },
                {
                    "name": "Bonus Proficiencies",
                    "source": "PHB",
                    "className": "Bard",
                    "classSource": "PHB",
                    "subclassShortName": "Lore",
                    "subclassSource": "PHB",
                    "level": 3,
                    "page": 54,
                    "entries": ["You gain proficiency with three skills of your choice."],
                },
            ],
        },
    )
    return root


def build_subclass_spellcasting_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"fighter": "class-fighter.json"})
    write_json(
        root / "data/class/class-fighter.json",
        {
            "subclass": [
                {
                    "name": "Spellblade",
                    "source": "XGE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "page": 101,
                    "spellcastingAbility": "int",
                    "casterProgression": "1/3",
                    "subclassTableGroups": [
                        {
                            "rowsSpellProgression": [
                                [],
                                [],
                                [2],
                                [3],
                            ]
                        }
                    ],
                    "cantripProgression": [0, 0, 2, 2],
                    "spellsKnownProgression": [0, 0, 3, 4],
                    "subclassFeatures": [
                        "Spellcasting|Fighter||Spellblade|XGE|3",
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Spellcasting",
                    "source": "XGE",
                    "className": "Fighter",
                    "classSource": "PHB",
                    "subclassShortName": "Spellblade",
                    "subclassSource": "XGE",
                    "level": 3,
                    "page": 101,
                    "entries": ["You study martial spellcraft."],
                }
            ],
        },
    )
    return root


def build_unsupported_cross_source_subclassfeature_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"cleric": "class-cleric.json"})
    write_json(
        root / "data/class/class-cleric.json",
        {
            "subclassFeature": [
                {
                    "name": "Blessed Strikes",
                    "source": "TCE",
                    "className": "Cleric",
                    "classSource": "PHB",
                    "subclassShortName": "Life",
                    "subclassSource": "PHB",
                    "level": 8,
                    "page": 31,
                    "entries": ["Supported subclass source."],
                },
                {
                    "name": "Blessed Strikes",
                    "source": "TCE",
                    "className": "Cleric",
                    "classSource": "PHB",
                    "subclassShortName": "Arcana",
                    "subclassSource": "EFA",
                    "level": 8,
                    "page": 31,
                    "entries": ["Unsupported subclass source."],
                },
            ],
        },
    )
    return root


def build_campaign_subclass_progression_data_root(root: Path) -> Path:
    write_json(root / "data/class/index.json", {"sorcerer": "class-sorcerer.json"})
    write_json(
        root / "data/class/class-sorcerer.json",
        {
            "class": [
                {
                    "name": "Sorcerer",
                    "source": "PHB",
                    "page": 99,
                    "hd": {"number": 1, "faces": 6},
                    "proficiency": ["con", "cha"],
                    "startingProficiencies": {
                        "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                        "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "insight", "persuasion"]}}],
                    },
                    "subclassTitle": "Sorcerous Origin",
                    "classFeatures": [
                        "Spellcasting|Sorcerer|PHB|1",
                    ],
                }
            ],
            "classFeature": [
                {
                    "name": "Spellcasting",
                    "source": "PHB",
                    "className": "Sorcerer",
                    "classSource": "PHB",
                    "level": 1,
                    "entries": ["You have learned to untangle and reshape the fabric of reality in harmony with your wishes and music."],
                }
            ],
            "subclass": [
                {
                    "name": "Wild Magic",
                    "shortName": "Wild Magic",
                    "source": "PHB",
                    "className": "Sorcerer",
                    "classSource": "PHB",
                    "page": 103,
                    "subclassFeatures": [
                        "Wild Magic Surge|Sorcerer||Wild Magic|PHB|1",
                    ],
                }
            ],
            "subclassFeature": [
                {
                    "name": "Wild Magic Surge",
                    "source": "PHB",
                    "className": "Sorcerer",
                    "classSource": "PHB",
                    "subclassShortName": "Wild Magic",
                    "subclassSource": "PHB",
                    "level": 1,
                    "page": 103,
                    "entries": ["Your spellcasting can unleash surges of untamed magic."],
                }
            ],
        },
    )
    return root


def test_embedded_feature_cards_strip_inline_import_tags(app):
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        now = datetime.now(timezone.utc)
        entry = SystemsEntryRecord(
            id=1,
            library_slug="DND-5E",
            source_id="TCE",
            entry_key="dnd-5e|optionalfeature|tce|superior-technique",
            entry_type="optionalfeature",
            slug="superior-technique",
            title="Superior Technique",
            source_page="42",
            source_path="data/optionalfeatures.json",
            search_text="",
            player_safe_default=True,
            dm_heavy=False,
            metadata={"feature_type": ["FS:F"]},
            body={
                "entries": [
                    "You learn one {@filter maneuver|optionalfeatures|feature type=MV:B} of your choice from among those available to the {@class fighter|phb|Battle Master|Battle Master|phb|2-0} archetype.",
                    "You gain one superiority die, which is a {@dice d6}.",
                    "At the start of each of your turns, you can deal {@damage 1d4} bludgeoning damage to one creature {@condition grappled} by you while carrying a {@item shield|phb}.",
                ]
            },
            rendered_html="",
            created_at=now,
            updated_at=now,
        )

        embedded_card = systems_service._build_embedded_feature_card(
            "linden-pass",
            entry,
            optionalfeature_lookup={},
        )

    body_html = embedded_card["body_html"]
    assert "{@" not in body_html
    assert "maneuver of your choice" in body_html
    assert "fighter archetype" in body_html
    assert "a d6" in body_html
    assert "1d4 bludgeoning damage" in body_html
    assert "grappled" in body_html
    assert "shield" in body_html


def test_importer_renders_ability_formula_nodes_readably(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        rendered_html = importer._render_content_block(
            [
                {"attributes": ["cha"], "name": "Spell", "type": "abilityDc"},
                {"attributes": ["cha"], "name": "Spell", "type": "abilityAttackMod"},
            ],
            heading_level=3,
        )

    assert "Spell save DC:" in rendered_html
    assert "8 + your proficiency bonus + your Charisma modifier" in rendered_html
    assert "Spell attack modifier:" in rendered_html
    assert "your proficiency bonus + your Charisma modifier" in rendered_html
    assert "Spell.</strong>" not in rendered_html


def test_embedded_feature_cards_render_ability_formula_nodes_readably(app):
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        now = datetime.now(timezone.utc)
        entry = SystemsEntryRecord(
            id=2,
            library_slug="DND-5E",
            source_id="PHB",
            entry_key="dnd-5e|classfeature|phb|pact-magic|warlock|phb|1",
            entry_type="classfeature",
            slug="pact-magic-warlock-phb-1",
            title="Pact Magic",
            source_page="107",
            source_path="data/class/class-warlock.json",
            search_text="",
            player_safe_default=True,
            dm_heavy=False,
            metadata={"class_name": "Warlock", "class_source": "PHB", "level": 1},
            body={
                "entries": [
                    {
                        "name": "Spellcasting Ability",
                        "type": "entries",
                        "entries": [
                            "Charisma is your spellcasting ability for your warlock spells.",
                            {"attributes": ["cha"], "name": "Spell", "type": "abilityDc"},
                            {"attributes": ["cha"], "name": "Spell", "type": "abilityAttackMod"},
                        ],
                    }
                ]
            },
            rendered_html="",
            created_at=now,
            updated_at=now,
        )

        embedded_card = systems_service._build_embedded_feature_card(
            "linden-pass",
            entry,
            optionalfeature_lookup={},
        )

    body_html = embedded_card["body_html"]
    assert "Spell save DC:" in body_html
    assert "8 + your proficiency bonus + your Charisma modifier" in body_html
    assert "Spell attack modifier:" in body_html
    assert "your proficiency bonus + your Charisma modifier" in body_html
    assert "Spell.</strong>" not in body_html


def test_importer_imports_mechanics_only_and_strips_media_fields(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        phb_result = importer.import_source("PHB")
        vgm_result = importer.import_source("VGM", entry_types=["race"])
        egw_result = importer.import_source("EGW", entry_types=["race"])
        mm_result = importer.import_source("MM")

        assert phb_result.imported_count == 29
        assert phb_result.imported_by_type == {
            "action": 1,
            "background": 1,
            "class": 1,
            "classfeature": 1,
            "condition": 1,
            "feat": 1,
            "item": 4,
            "optionalfeature": 3,
            "race": 9,
            "sense": 1,
            "skill": 1,
            "spell": 1,
            "status": 1,
            "subclass": 1,
            "subclassfeature": 1,
            "variantrule": 1,
        }
        assert vgm_result.imported_count == 2
        assert vgm_result.imported_by_type == {"race": 2}
        assert egw_result.imported_count == 1
        assert egw_result.imported_by_type == {"race": 1}
        assert mm_result.imported_count == 1
        assert mm_result.imported_by_type == {"monster": 1}

        store = app.extensions["systems_store"]
        phb_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", limit=100)}
        vgm_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "VGM", limit=20)}
        egw_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "EGW", limit=20)}
        mm_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "MM", limit=50)}

        spell = phb_entries["Mage Hand"]
        assert "Cantrip (Conjuration)" in spell.rendered_html
        assert "30 feet" in spell.rendered_html
        assert "Heavy armor made of interlocking metal rings." in phb_entries["Chain Mail"].rendered_html
        assert phb_entries["Chain Mail"].metadata["ac"] == 16
        assert phb_entries["Chain Mail"].metadata["type"] == "HA"
        assert phb_entries["Chain Mail"].metadata["strength"] == "13"
        assert phb_entries["Chain Mail"].metadata["stealth_disadvantage"] is True
        assert "martial ranged weapon" in phb_entries["Light Crossbow"].rendered_html
        assert "twenty crossbow bolts" in phb_entries["Crossbow Bolts (20)"].rendered_html
        fighter = phb_entries["Fighter"]
        assert "Summary" not in fighter.rendered_html
        assert "<strong>Hit Die:</strong> <span>1d10</span>" in fighter.rendered_html
        assert "light, medium, heavy, shield" in fighter.rendered_html
        assert "simple, martial" in fighter.rendered_html
        assert "<p>light</p>" not in fighter.rendered_html
        assert "1d10" in fighter.rendered_html
        assert "Class Features By Level" in fighter.rendered_html
        assert "Level 1" in fighter.rendered_html
        fighting_style = phb_entries["Fighting Style"]
        assert "Choose 1 option:" in fighting_style.rendered_html
        assert "Archery" in fighting_style.rendered_html
        hill_dwarf = phb_entries["Hill Dwarf"]
        assert "Base Race:</strong> <span>Dwarf</span>" in hill_dwarf.rendered_html
        assert "Subrace:</strong> <span>Hill</span>" in hill_dwarf.rendered_html
        assert "Dwarven Toughness" in hill_dwarf.rendered_html
        drow = phb_entries["Drow"]
        assert "Base Race:</strong> <span>Elf</span>" in drow.rendered_html
        assert "Subrace:</strong> <span>Drow</span>" in drow.rendered_html
        assert "Superior Darkvision" in drow.rendered_html
        assert "High Elf" in phb_entries
        variant_human = phb_entries["Variant Human"]
        assert "Base Race:</strong> <span>Human</span>" in variant_human.rendered_html
        assert "Subrace:</strong> <span>Variant</span>" in variant_human.rendered_html
        assert "Skills" in variant_human.rendered_html
        assert "Feat" in variant_human.rendered_html
        assert "one skill of your choice" in variant_human.rendered_html
        fallen_aasimar = vgm_entries["Fallen Aasimar"]
        assert "Base Race:</strong> <span>Aasimar</span>" in fallen_aasimar.rendered_html
        assert "Necrotic Shroud" in fallen_aasimar.rendered_html
        draconblood = egw_entries["Draconblood Dragonborn"]
        assert "Base Race:</strong> <span>Dragonborn</span>" in draconblood.rendered_html
        assert "Forceful Presence" in draconblood.rendered_html

        monster = mm_entries["Goblin"]
        raw_monster_text = json.dumps(monster.metadata, sort_keys=True) + json.dumps(monster.body, sort_keys=True)
        assert "hasToken" not in raw_monster_text
        assert "soundClip" not in raw_monster_text
        assert "altArt" not in raw_monster_text
        assert "Melee Weapon Attack:" in monster.rendered_html
        assert "+4" in monster.rendered_html


def test_importer_supports_scag_backgrounds(app, tmp_path):
    data_root = build_scag_background_data_root(tmp_path / "dnd5e-source-scag-backgrounds")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("SCAG", entry_types=["background"])
        store = app.extensions["systems_store"]
        clan_crafter = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="background", limit=10)
            if entry.title == "Clan Crafter"
        )

    assert result.imported_count == 1
    assert result.imported_by_type == {"background": 1}
    assert clan_crafter.metadata["skill_proficiencies"] == [{"history": True, "insight": True}]
    assert clan_crafter.metadata["language_proficiencies"] == [{"dwarvish": True}, {"anyStandard": 1}]
    assert clan_crafter.metadata["tool_proficiencies"] == [{"anyArtisansTool": 1}]
    assert "Respect of the Stout Folk" in clan_crafter.rendered_html


def test_scag_races_of_the_realms_wrappers_are_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_book_data_root(tmp_path / "dnd5e-source-scag-races-of-the-realms")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == [
        "Dwarves",
        "Elves",
        "Halflings",
        "Humans",
        "Dragonborn",
        "Gnomes",
        "Half-Elves",
        "Half-Orcs",
        "Tieflings",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dwarves_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")
    tieflings_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Tieflings'].slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Dwarves" in source_body
    assert "Tieflings" in source_body
    assert source_body.index("Dwarves") < source_body.index("Elves")
    assert source_body.index("Half-Elves") < source_body.index("Half-Orcs")
    assert source_body.index("Half-Orcs") < source_body.index("Tieflings")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Dwarves" in category_body
    assert "Tieflings" in category_body
    assert category_body.index("Dwarves") < category_body.index("Elves")
    assert category_body.index("Half-Elves") < category_body.index("Half-Orcs")
    assert category_body.index("Half-Orcs") < category_body.index("Tieflings")

    assert dwarves_response.status_code == 200
    dwarves_body = dwarves_response.get_data(as_text=True)
    assert "Chapter 3" in dwarves_body
    assert "Races of the Realms" in dwarves_body
    assert "Shield Dwarves" in dwarves_body
    assert "Gray Dwarves (Duergar)" in dwarves_body
    assert "Dwarven Deities" in dwarves_body
    assert 'href="#shield-dwarves"' in dwarves_body
    assert 'href="#gray-dwarves-duergar"' in dwarves_body
    assert 'id="dwarven-deities"' in dwarves_body

    assert tieflings_response.status_code == 200
    tieflings_body = tieflings_response.get_data(as_text=True)
    assert "Chapter 3" in tieflings_body
    assert "Races of the Realms" in tieflings_body
    assert "The Mark of Asmodeus" in tieflings_body
    assert "A Race without a Home" in tieflings_body
    assert "Tiefling Names" in tieflings_body
    assert "Aasimar" in tieflings_body
    assert 'href="#the-mark-of-asmodeus"' in tieflings_body
    assert 'href="#a-race-without-a-home"' in tieflings_body
    assert 'id="tiefling-names"' in tieflings_body
    assert 'id="aasimar"' in tieflings_body


def test_scag_races_of_the_realms_book_entries_follow_source_visibility(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_book_data_root(tmp_path / "dnd5e-source-scag-races-of-the-realms-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Dwarves" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Dwarves" in dm_body
    assert "Races of the Realms" in dm_body


def test_scag_classes_book_entries_follow_book_order_and_render_detail_pages(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_classes_book_data_root(tmp_path / "dnd5e-source-scag-classes")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == list(SCAG_CLASSES_TEST_HEADERS)

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    colleges_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Bardic Colleges'].slug}"
    )
    cantrips_response = client.get(
        "/campaigns/linden-pass/systems/entries/"
        f"{book_entries['Cantrips for Sorcerers, Warlocks, and Wizards'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    source_indexes = [source_body.index(title) for title in SCAG_CLASSES_TEST_HEADERS]
    assert source_indexes == sorted(source_indexes)

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    category_indexes = [category_body.index(title) for title in SCAG_CLASSES_TEST_HEADERS]
    assert category_indexes == sorted(category_indexes)

    assert colleges_response.status_code == 200
    colleges_body = colleges_response.get_data(as_text=True)
    assert "Chapter 4" in colleges_body
    assert "Classes" in colleges_body
    assert "College of Fochlucan" in colleges_body
    assert "College of New Olamn" in colleges_body
    assert "College of the Herald" in colleges_body
    assert 'href="#college-of-fochlucan"' in colleges_body
    assert 'href="#college-of-the-herald"' in colleges_body
    assert 'id="college-of-new-olamn"' in colleges_body

    assert cantrips_response.status_code == 200
    cantrips_body = cantrips_response.get_data(as_text=True)
    assert "Chapter 4" in cantrips_body
    assert "Classes" in cantrips_body
    assert "Booming Blade" in cantrips_body
    assert "Green-Flame Blade" in cantrips_body
    assert 'href="#booming-blade"' in cantrips_body
    assert 'id="green-flame-blade"' in cantrips_body


def test_scag_classes_book_entries_follow_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_scag_classes_book_data_root(tmp_path / "dnd5e-source-scag-classes-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=40)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Barbarians'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Barbarians'].slug}")

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Barbarians" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Barbarians" in dm_body
    assert "Classes" in dm_body


def test_scag_backgrounds_book_entry_is_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_backgrounds_book_data_root(tmp_path / "dnd5e-source-scag-backgrounds-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == ["Backgrounds"]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    backgrounds_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Backgrounds" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 1 book chapters available to you in this source." in category_body
    assert "Backgrounds" in category_body

    assert backgrounds_response.status_code == 200
    backgrounds_body = backgrounds_response.get_data(as_text=True)
    assert "Chapter 5" in backgrounds_body
    assert "Backgrounds" in backgrounds_body
    assert "This chapter offers additional backgrounds for characters in a Forgotten Realms campaign" in backgrounds_body
    assert "City Watch" in backgrounds_body
    assert "Clan Crafter" in backgrounds_body
    assert "Urban Bounty Hunter" in backgrounds_body


def test_scag_backgrounds_book_entry_follows_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_scag_backgrounds_book_data_root(
        tmp_path / "dnd5e-source-scag-backgrounds-book-policy"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Backgrounds" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Backgrounds" in dm_body
    assert "City Watch" in dm_body


def test_scag_first_slice_excludes_setting_lore_chapters_from_book_imports(app, tmp_path):
    data_root = build_scag_first_slice_boundary_data_root(
        tmp_path / "dnd5e-source-scag-first-slice-boundary"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("SCAG", entry_types=["book"])
        store = app.extensions["systems_store"]
        book_entries = list(
            store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        )

    assert result.imported_count == 3
    assert result.imported_by_type == {"book": 3}
    book_titles = {entry.title for entry in book_entries}
    assert book_titles == {"Dwarves", "Barbarians", "Backgrounds"}
    assert "Welcome to the Realms" not in book_titles
    assert "The Sword Coast and the North" not in book_titles


def test_scag_entry_pages_surface_source_chapter_context_links(client, sign_in, users, app, tmp_path):
    data_root = build_scag_entry_source_context_data_root(
        tmp_path / "dnd5e-source-scag-entry-source-context"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "SCAG",
            entry_types=["book", "race", "subclass", "subclassfeature", "background", "item"],
        )

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }
        scag_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", limit=None)
            if entry.entry_type != "book"
        }

    sign_in(users["party"]["email"], users["party"]["password"])

    page_expectations = {
        "Ghostwise Halfling": ("Halflings",),
        "Path of the Battlerager": ("Primal Paths",),
        "Battlerager Armor": ("Primal Paths",),
        "Clan Crafter": ("Backgrounds",),
        "Spiked Armor": ("Primal Paths",),
        "Birdpipes": ("Musical Instruments",),
    }

    for title, book_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{scag_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Source Chapter Context" in body
        for book_title in book_titles:
            assert book_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{book_entries[book_title].slug}"'
                in body
            )


def test_importer_expands_safe_classic_magic_armor_variants(app, tmp_path):
    data_root = build_magicvariant_data_root(tmp_path / "dnd5e-source-magicvariants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["item"])
        result = importer.import_source("DMG", entry_types=["item"])
        store = app.extensions["systems_store"]
        dmg_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=20)
        }

    assert result.imported_count == 1
    assert result.imported_by_type == {"item": 1}
    assert "+1 Chain Mail" in dmg_entries
    assert "You have a +1 bonus to AC while wearing this armor." in dmg_entries["+1 Chain Mail"].rendered_html
    assert "Heavy armor made of interlocking metal rings." in dmg_entries["+1 Chain Mail"].rendered_html
    assert dmg_entries["+1 Chain Mail"].metadata["ac"] == 16
    assert dmg_entries["+1 Chain Mail"].metadata["bonus_ac"] == "+1"
    assert dmg_entries["+1 Chain Mail"].metadata["base_item"] == "Chain Mail|PHB"


def test_importer_preserves_additional_spell_metadata_on_class_entries(app, tmp_path):
    data_root = build_additional_spell_metadata_data_root(tmp_path / "dnd5e-source-additional-spells")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "subclass", "classfeature", "subclassfeature"])
        store = app.extensions["systems_store"]
        entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", limit=20)}

    assert entries["Cleric"].metadata["additional_spells"] == [{"prepared": {"1": ["ceremony"]}}]
    assert entries["Life Domain"].metadata["additional_spells"] == [
        {"prepared": {"1": ["bless", "cure wounds"], "3": ["lesser restoration", "spiritual weapon"]}}
    ]
    assert entries["Spellcasting"].metadata["additional_spells"] == [{"prepared": {"1": ["guidance"]}}]
    assert entries["Disciple of Life"].metadata["additional_spells"] == [{"prepared": {"1": ["bless"]}}]


def test_importer_preserves_native_class_progression_and_spell_class_lists(app, tmp_path):
    data_root = build_class_progression_metadata_data_root(tmp_path / "dnd5e-source-class-progression")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("TCE", entry_types=["class", "classfeature", "spell"])
        store = app.extensions["systems_store"]
        artificer = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="class", limit=10)
            if entry.title == "Artificer"
        )
        guidance = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="spell", limit=10)
            if entry.title == "Guidance"
        )

    assert artificer.metadata["spellcasting_ability"] == "int"
    assert artificer.metadata["caster_progression"] == "artificer"
    assert artificer.metadata["prepared_spells"] == "<$level$> / 2 + <$int_mod$>"
    assert artificer.metadata["cantrip_progression"] == [2, 2, 2]
    assert artificer.metadata["slot_progression"] == [
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 3}],
    ]
    assert guidance.metadata["class_lists"] == {"TCE": ["Artificer"]}


def test_importer_preserves_spell_ritual_metadata_for_native_builder(app, tmp_path):
    data_root = build_spell_metadata_data_root(tmp_path / "dnd5e-source-spell-metadata")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["spell"])
        store = app.extensions["systems_store"]
        detect_magic = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="spell", limit=10)
            if entry.title == "Detect Magic"
        )

    assert detect_magic.metadata["ritual"] is True


def test_importer_preserves_structured_feat_metadata_for_native_builder(app, tmp_path):
    data_root = build_feat_metadata_data_root(tmp_path / "dnd5e-source-feat-metadata")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("PHB", entry_types=["feat"])

        assert result.imported_count == 2
        store = app.extensions["systems_store"]
        feat_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="feat", limit=10)}

    resilient = feat_entries["Resilient"]
    skilled = feat_entries["Skilled"]

    assert resilient.metadata["ability"] == [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"], "amount": 1}}]
    assert resilient.metadata["saving_throw_proficiencies"] == [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"]}}]
    assert skilled.metadata["skill_tool_language_proficiencies"] == [
        {"choose": [{"from": ["anySkill", "anyTool"], "count": 3}]}
    ]


def test_importer_replaces_existing_entries_for_a_source(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

        updated_spell_file = data_root / "data/spells/spells-phb.json"
        write_json(
            updated_spell_file,
            {
                "spell": [
                    {
                        "name": "Shield",
                        "source": "PHB",
                        "page": 275,
                        "level": 1,
                        "school": "A",
                        "time": [{"number": 1, "unit": "reaction"}],
                        "range": {"type": "self"},
                        "components": {"v": True, "s": True},
                        "duration": [{"type": "timed", "duration": {"type": "round", "amount": 1}}],
                        "entries": ["An invisible barrier of magical force appears and protects you."]
                    }
                ]
            },
        )

        result = importer.import_source("PHB", entry_types=["spell"])
        entries = app.extensions["systems_store"].list_entries_for_source("DND-5E", "PHB", limit=100)

        assert result.imported_count == 1
        titles = [entry.title for entry in entries]
        assert "Shield" in titles
        assert "Mage Hand" not in titles
        assert "Alert" in titles
        assert "Fighter" in titles
        assert len(entries) == 29


def test_systems_search_uses_imported_entries(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["spell"])

    sign_in(users["party"]["email"], users["party"]["password"])
    response = client.get("/campaigns/linden-pass/systems/search?q=mage")

    assert response.status_code == 200
    assert "Mage Hand" in response.get_data(as_text=True)


def test_systems_search_ignores_body_text_false_positives(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

    sign_in(users["party"]["email"], users["party"]["password"])

    global_search = client.get("/campaigns/linden-pass/systems/search?q=spectral")
    source_search = client.get("/campaigns/linden-pass/systems/sources/PHB/types/spell?q=spectral")

    assert global_search.status_code == 200
    global_html = global_search.get_data(as_text=True)
    assert "Mage Hand" not in global_html
    assert "No imported systems entries matched that search yet." in global_html

    assert source_search.status_code == 200
    source_html = source_search.get_data(as_text=True)
    assert "Mage Hand" not in source_html
    assert "No imported spells matched that title/type search." in source_html


def test_source_detail_is_a_category_index_and_category_page_is_not_capped_at_one_hundred(
    client, sign_in, users, app, tmp_path
):
    data_root = build_large_feat_data_root(tmp_path / "dnd5e-source-large", count=105)

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["feat"])

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/feat")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "105 browsable entries across 1" in source_body
    assert "category." in source_body
    assert "Feats" in source_body
    assert "Feat 000" not in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 105 feats in this source." in category_body
    assert "Feat 000" in category_body
    assert "Feat 104" in category_body


def test_phb_book_chapters_are_imported_and_browsable_in_book_order(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "PHB",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        book_entry_links = [f'/campaigns/linden-pass/systems/entries/{entry.slug}' for entry in book_entries]
        equipment = next(entry for entry in book_entries if entry.title == "Equipment")
        customization_options = next(entry for entry in book_entries if entry.title == "Customization Options")
        using_ability_scores = next(entry for entry in book_entries if entry.title == "Using Ability Scores")
        introduction = next(entry for entry in book_entries if entry.title == "Introduction")
        spellcasting = next(entry for entry in book_entries if entry.title == "Spellcasting")
        conditions = next(entry for entry in book_entries if entry.title == "Conditions")
        rules_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "RULES", entry_type="rule", limit=None)
        }
        passive_checks_rule = rules_entries["Passive Checks"]

    assert titles == [
        "Introduction",
        "Step-by-Step Characters",
        "Equipment",
        "Customization Options",
        "Using Ability Scores",
        "Adventuring",
        "Combat",
        "Spellcasting",
        "Conditions",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/book")
    equipment_response = client.get(f"/campaigns/linden-pass/systems/entries/{equipment.slug}")
    customization_response = client.get(f"/campaigns/linden-pass/systems/entries/{customization_options.slug}")
    detail_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores.slug}")
    intro_response = client.get(f"/campaigns/linden-pass/systems/entries/{introduction.slug}")
    spellcasting_response = client.get(f"/campaigns/linden-pass/systems/entries/{spellcasting.slug}")
    conditions_response = client.get(f"/campaigns/linden-pass/systems/entries/{conditions.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Introduction" in source_body
    assert "Equipment" in source_body
    assert "Customization Options" in source_body
    assert "Spellcasting" in source_body
    assert "Conditions" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 9 book chapters available to you in this source." in category_body
    for earlier, later in zip(book_entry_links, book_entry_links[1:]):
        assert category_body.index(earlier) < category_body.index(later)

    assert equipment_response.status_code == 200
    equipment_body = equipment_response.get_data(as_text=True)
    assert "Chapter 5" in equipment_body
    assert "Armor and Shields" in equipment_body
    assert "Weapons" in equipment_body
    assert 'href="#armor-and-shields"' in equipment_body
    assert 'id="armor-and-shields"' in equipment_body

    assert customization_response.status_code == 200
    customization_body = customization_response.get_data(as_text=True)
    assert "Chapter 6" in customization_body
    assert "Multiclassing" in customization_body
    assert "Feats" in customization_body
    assert 'href="#multiclassing"' in customization_body
    assert 'id="multiclassing"' in customization_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "Chapter 7" in detail_body
    assert "Chapter Navigation" in detail_body
    assert 'href="#advantage-and-disadvantage"' in detail_body
    assert 'href="#ability-checks--contests"' in detail_body
    assert 'id="advantage-and-disadvantage"' in detail_body
    assert 'id="ability-checks--contests"' in detail_body
    assert "Advantage and Disadvantage" in detail_body
    assert "Contests" in detail_body
    assert "Passive Checks" in detail_body
    assert "10 + all modifiers that normally apply to the check" in detail_body
    assert "Rules:" in detail_body
    assert f'href="/campaigns/linden-pass/systems/entries/{passive_checks_rule.slug}"' in detail_body
    assert "book/PHB/ch7.webp" not in detail_body
    assert "p. 175" in detail_body

    assert intro_response.status_code == 200
    intro_body = intro_response.get_data(as_text=True)
    assert "How to Play" in intro_body
    assert "book/PHB/intro.webp" not in intro_body

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert 'href="#casting-a-spell--components"' in spellcasting_body
    assert 'href="#targets--areas-of-effect"' in spellcasting_body
    assert 'id="casting-a-spell--components"' in spellcasting_body
    assert 'id="targets--areas-of-effect"' in spellcasting_body

    assert conditions_response.status_code == 200
    conditions_body = conditions_response.get_data(as_text=True)
    assert "Appendix A" in conditions_body
    assert "Conditions alter a creature" in conditions_body
    assert "blinded" in conditions_body


def test_dmg_book_chapters_are_imported_for_dm_browse_in_book_order(
    client, sign_in, users, app, tmp_path
):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

        service = app.extensions["systems_service"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "DMG",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        book_entry_links = [f'/campaigns/linden-pass/systems/entries/{entry.slug}' for entry in book_entries]
        multiverse = next(entry for entry in book_entries if entry.title == "Creating a Multiverse")
        traps = next(entry for entry in book_entries if entry.title == "Traps")
        downtime_activities = next(entry for entry in book_entries if entry.title == "Downtime Activities")
        treasure = next(entry for entry in book_entries if entry.title == "Treasure")
        running_the_game = next(entry for entry in book_entries if entry.title == "Running the Game")

    assert titles == [
        "Creating a Multiverse",
        "Traps",
        "Downtime Activities",
        "Treasure",
        "Running the Game",
        "Dungeon Master's Workshop",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    multiverse_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse.slug}")
    traps_response = client.get(f"/campaigns/linden-pass/systems/entries/{traps.slug}")
    downtime_response = client.get(f"/campaigns/linden-pass/systems/entries/{downtime_activities.slug}")
    treasure_response = client.get(f"/campaigns/linden-pass/systems/entries/{treasure.slug}")
    running_the_game_response = client.get(f"/campaigns/linden-pass/systems/entries/{running_the_game.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Creating a Multiverse" in source_body
    assert "Traps" in source_body
    assert "Downtime Activities" in source_body
    assert "Treasure" in source_body
    assert "Running the Game" in source_body
    assert "Dungeon Master&#39;s Workshop" in source_body
    assert "Adventure Environments" in source_body
    assert "Between Adventures" in source_body
    assert "Searches only this source&#39;s book chapters using curated metadata" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 6 book chapters available to you in this source." in category_body
    for earlier, later in zip(book_entry_links, book_entry_links[1:]):
        assert category_body.index(earlier) < category_body.index(later)

    assert multiverse_response.status_code == 200
    multiverse_body = multiverse_response.get_data(as_text=True)
    assert "Chapter 2" in multiverse_body
    assert "The Planes" in multiverse_body
    assert "Planar Travel" in multiverse_body
    assert "Outer Planes" in multiverse_body
    assert "Optional Rules" in multiverse_body
    assert "Known Worlds of the Material Plane" in multiverse_body
    assert 'href="#the-planes"' in multiverse_body
    assert 'id="the-planes"' in multiverse_body
    assert 'href="#outer-planes--optional-rules"' in multiverse_body
    assert 'id="outer-planes--optional-rules"' in multiverse_body

    assert traps_response.status_code == 200
    traps_body = traps_response.get_data(as_text=True)
    assert "Chapter 5" in traps_body
    assert "Adventure Environments" in traps_body
    assert "Traps in Play" in traps_body
    assert "Triggering a Trap" in traps_body
    assert "Detecting and Disabling a Trap" in traps_body
    assert "Trap Effects" in traps_body
    assert "Complex Traps" in traps_body
    assert "Sample Traps" in traps_body
    assert "Wilderness Survival" not in traps_body
    assert 'href="#traps-in-play"' in traps_body
    assert 'id="traps-in-play"' in traps_body
    assert 'href="#traps-in-play--triggering-a-trap"' in traps_body
    assert 'id="traps-in-play--triggering-a-trap"' in traps_body

    assert downtime_response.status_code == 200
    downtime_body = downtime_response.get_data(as_text=True)
    assert "Chapter 6" in downtime_body
    assert "Between Adventures" in downtime_body
    assert "More Downtime Activities" in downtime_body
    assert "Creating Downtime Activities" in downtime_body
    assert "Recurring Expenses" not in downtime_body
    assert 'href="#more-downtime-activities"' in downtime_body
    assert 'id="more-downtime-activities"' in downtime_body

    assert treasure_response.status_code == 200
    treasure_body = treasure_response.get_data(as_text=True)
    assert "Chapter 7" in treasure_body
    assert "Magic Items" in treasure_body
    assert "Attunement" in treasure_body
    assert 'href="#magic-items"' in treasure_body
    assert 'id="magic-items"' in treasure_body

    assert running_the_game_response.status_code == 200
    running_the_game_body = running_the_game_response.get_data(as_text=True)
    assert "Chapter 8" in running_the_game_body
    assert "Chapter Navigation" in running_the_game_body
    assert 'href="#using-ability-scores"' in running_the_game_body
    assert 'id="using-ability-scores"' in running_the_game_body
    assert "Chases" in running_the_game_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_multiverse_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse.slug}")
    assert blocked_multiverse_response.status_code == 404


def test_mm_intro_book_sections_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["book"])

        service = app.extensions["systems_service"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "MM",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        statistics = next(entry for entry in book_entries if entry.title == "Statistics")
        legendary = next(entry for entry in book_entries if entry.title == "Legendary Creatures")
        shadow_dragon_template = next(entry for entry in book_entries if entry.title == "Shadow Dragon Template")
        half_dragon_template = next(entry for entry in book_entries if entry.title == "Half-Dragon Template")
        spore_servant_template = next(entry for entry in book_entries if entry.title == "Spore Servant Template")
        customizing_npcs = next(entry for entry in book_entries if entry.title == "Customizing NPCs")

    assert titles == [
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/MM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/MM/types/book")
    statistics_response = client.get(f"/campaigns/linden-pass/systems/entries/{statistics.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Statistics" in source_body
    assert "Legendary Creatures" in source_body
    assert "Shadow Dragon Template" in source_body
    assert "Half-Dragon Template" in source_body
    assert "Spore Servant Template" in source_body
    assert "Customizing NPCs" in source_body
    assert source_body.index("Statistics") < source_body.index("Legendary Creatures")
    assert source_body.index("Legendary Creatures") < source_body.index("Shadow Dragon Template")
    assert source_body.index("Shadow Dragon Template") < source_body.index("Half-Dragon Template")
    assert source_body.index("Half-Dragon Template") < source_body.index("Spore Servant Template")
    assert source_body.index("Spore Servant Template") < source_body.index("Customizing NPCs")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Statistics" in category_body
    assert "Legendary Creatures" in category_body
    assert "Shadow Dragon Template" in category_body
    assert "Half-Dragon Template" in category_body
    assert "Spore Servant Template" in category_body
    assert "Customizing NPCs" in category_body
    assert category_body.index("Statistics") < category_body.index("Legendary Creatures")
    assert category_body.index("Legendary Creatures") < category_body.index("Shadow Dragon Template")
    assert category_body.index("Shadow Dragon Template") < category_body.index("Half-Dragon Template")
    assert category_body.index("Half-Dragon Template") < category_body.index("Spore Servant Template")
    assert category_body.index("Spore Servant Template") < category_body.index("Customizing NPCs")

    assert statistics_response.status_code == 200
    statistics_body = statistics_response.get_data(as_text=True)
    assert "Introduction" in statistics_body
    assert "Chapter Navigation" in statistics_body
    assert "Size" in statistics_body
    assert "Type" in statistics_body
    assert "Tags" in statistics_body
    assert "Speed" in statistics_body
    assert "Burrow" in statistics_body
    assert "Senses" in statistics_body
    assert "Blindsight" in statistics_body
    assert "Challenge" in statistics_body
    assert "Experience Points" in statistics_body
    assert "Equipment" in statistics_body
    assert "Legendary Creatures" not in statistics_body
    assert "Size Categories" in statistics_body
    assert 'href="#type--tags"' in statistics_body
    assert 'id="type--tags"' in statistics_body
    assert 'href="#senses--blindsight"' in statistics_body
    assert 'id="senses--blindsight"' in statistics_body

    legendary_response = client.get(f"/campaigns/linden-pass/systems/entries/{legendary.slug}")
    assert legendary_response.status_code == 200
    legendary_body = legendary_response.get_data(as_text=True)
    assert "Introduction" in legendary_body
    assert "Chapter Navigation" in legendary_body
    assert "Legendary Actions" in legendary_body
    assert "A Legendary Creature&#39;s Lair" in legendary_body
    assert "Lair Actions" in legendary_body
    assert "Regional Effects" in legendary_body
    assert "Statistics" not in legendary_body
    assert 'href="#legendary-actions"' in legendary_body
    assert 'id="legendary-actions"' in legendary_body
    assert 'href="#a-legendary-creatures-lair--lair-actions"' in legendary_body
    assert 'id="a-legendary-creatures-lair--regional-effects"' in legendary_body

    shadow_response = client.get(f"/campaigns/linden-pass/systems/entries/{shadow_dragon_template.slug}")
    assert shadow_response.status_code == 200
    shadow_body = shadow_response.get_data(as_text=True)
    assert "Introduction" in shadow_body
    assert "Chapter Navigation" in shadow_body
    assert "Damage Resistances" in shadow_body
    assert "Skills" in shadow_body
    assert "Living Shadow" in shadow_body
    assert "Shadow Breath" in shadow_body
    assert "Legendary Actions" not in shadow_body
    assert 'href="#damage-resistances"' in shadow_body
    assert 'id="damage-resistances"' in shadow_body
    assert 'href="#living-shadow"' in shadow_body
    assert 'id="shadow-breath"' in shadow_body

    half_dragon_response = client.get(f"/campaigns/linden-pass/systems/entries/{half_dragon_template.slug}")
    assert half_dragon_response.status_code == 200
    half_dragon_body = half_dragon_response.get_data(as_text=True)
    assert "Introduction" in half_dragon_body
    assert "Chapter Navigation" in half_dragon_body
    assert "Challenge" in half_dragon_body
    assert "Senses" in half_dragon_body
    assert "blindsight" in half_dragon_body
    assert "darkvision" in half_dragon_body
    assert "Resistances" in half_dragon_body
    assert "Damage Resistance" in half_dragon_body
    assert "Languages" in half_dragon_body
    assert "Breath Weapon" in half_dragon_body
    assert "Optional Prerequisite" in half_dragon_body
    assert "Shadow Breath" not in half_dragon_body
    assert 'href="#challenge"' in half_dragon_body
    assert 'id="challenge"' in half_dragon_body
    assert 'href="#new-action-breath-weapon"' in half_dragon_body
    assert 'id="new-action-breath-weapon"' in half_dragon_body

    spore_servant_response = client.get(f"/campaigns/linden-pass/systems/entries/{spore_servant_template.slug}")
    assert spore_servant_response.status_code == 200
    spore_servant_body = spore_servant_response.get_data(as_text=True)
    assert "Introduction" in spore_servant_body
    assert "Chapter Navigation" in spore_servant_body
    assert "Retained Characteristics" in spore_servant_body
    assert "Lost Characteristics" in spore_servant_body
    assert "Type" in spore_servant_body
    assert "Speed" in spore_servant_body
    assert "Ability Scores" in spore_servant_body
    assert "Senses" in spore_servant_body
    assert "blindsight" in spore_servant_body
    assert "Condition Immunities" in spore_servant_body
    assert "Languages" in spore_servant_body
    assert "rapport spores" in spore_servant_body
    assert "Attacks" in spore_servant_body
    assert "Breath Weapon" not in spore_servant_body
    assert 'href="#retained-characteristics"' in spore_servant_body
    assert 'id="retained-characteristics"' in spore_servant_body
    assert 'href="#senses"' in spore_servant_body
    assert 'id="senses"' in spore_servant_body
    assert 'href="#condition-immunities"' in spore_servant_body
    assert 'id="attacks"' in spore_servant_body

    customizing_npcs_response = client.get(f"/campaigns/linden-pass/systems/entries/{customizing_npcs.slug}")
    assert customizing_npcs_response.status_code == 200
    customizing_npcs_body = customizing_npcs_response.get_data(as_text=True)
    assert "Appendix B" in customizing_npcs_body
    assert "From Appendix B: Nonplayer Characters" in customizing_npcs_body
    assert "Chapter Navigation" in customizing_npcs_body
    assert "Racial Traits" in customizing_npcs_body
    assert "Spell Swaps" in customizing_npcs_body
    assert "Armor and Weapon Swaps" in customizing_npcs_body
    assert "NPC Descriptions" not in customizing_npcs_body
    assert 'href="#racial-traits"' in customizing_npcs_body
    assert 'id="racial-traits"' in customizing_npcs_body
    assert 'href="#armor-and-weapon-swaps"' in customizing_npcs_body
    assert 'id="armor-and-weapon-swaps"' in customizing_npcs_body


def test_vgm_character_race_wrappers_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "VGM",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        aasimar = next(entry for entry in book_entries if entry.title == "Aasimar")
        monstrous = next(entry for entry in book_entries if entry.title == "Monstrous Adventurers")
        height_and_weight = next(entry for entry in book_entries if entry.title == "Height and Weight")

    assert titles == [
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    aasimar_response = client.get(f"/campaigns/linden-pass/systems/entries/{aasimar.slug}")
    monstrous_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous.slug}")
    height_response = client.get(f"/campaigns/linden-pass/systems/entries/{height_and_weight.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Aasimar" in source_body
    assert "Firbolg" in source_body
    assert "Monstrous Adventurers" in source_body
    assert "Height and Weight" in source_body
    assert source_body.index("Aasimar") < source_body.index("Firbolg")
    assert source_body.index("Triton") < source_body.index("Monstrous Adventurers")
    assert source_body.index("Monstrous Adventurers") < source_body.index("Height and Weight")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Aasimar" in category_body
    assert "Firbolg" in category_body
    assert "Monstrous Adventurers" in category_body
    assert "Height and Weight" in category_body
    assert category_body.index("Aasimar") < category_body.index("Firbolg")
    assert category_body.index("Triton") < category_body.index("Monstrous Adventurers")
    assert category_body.index("Monstrous Adventurers") < category_body.index("Height and Weight")

    assert aasimar_response.status_code == 200
    aasimar_body = aasimar_response.get_data(as_text=True)
    assert "Chapter 2" in aasimar_body
    assert "Character Races" in aasimar_body
    assert "Celestial Champions" in aasimar_body
    assert "Aasimar Guides" in aasimar_body
    assert "Protector" in aasimar_body
    assert "Scourge" in aasimar_body
    assert "Fallen" in aasimar_body
    assert 'href="#celestial-champions"' in aasimar_body
    assert 'id="celestial-champions"' in aasimar_body
    assert 'href="#protector"' in aasimar_body
    assert 'id="fallen"' in aasimar_body

    assert monstrous_response.status_code == 200
    monstrous_body = monstrous_response.get_data(as_text=True)
    assert "Chapter 2" in monstrous_body
    assert "Character Races" in monstrous_body
    assert "Why a Monstrous Character?" in monstrous_body
    assert "Rare or Mundane?" in monstrous_body
    assert "Outcast or Ambassador?" in monstrous_body
    assert "Friends or Enemies?" in monstrous_body
    assert 'href="#rare-or-mundane"' in monstrous_body
    assert 'id="friends-or-enemies"' in monstrous_body

    assert height_response.status_code == 200
    height_body = height_response.get_data(as_text=True)
    assert "Chapter 2" in height_body
    assert "Character Races" in height_body
    assert "Base Height" in height_body
    assert "Base Weight" in height_body
    assert "Bugbear" in height_body
    assert "Triton" in height_body
    assert "Yuan-ti Pureblood" in height_body
    assert 'href="#height-and-weight"' not in height_body


def test_vgm_monster_lore_wrappers_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore-browse")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == [
        "Beholders: Bad Dreams Come True",
        "Giants: World Shakers",
        "Gnolls: The Insatiable Hunger",
        "Goblinoids: The Conquering Host",
        "Hags: Dark Sisterhood",
        "Kobolds: Little Dragons",
        "Mind Flayers: Scourge of Worlds",
        "Orcs: The Godsworn",
        "Yuan-ti: Snake People",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    beholders_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Beholders: Bad Dreams Come True'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f"{book_entries['Beholders: Bad Dreams Come True'].slug}\""
        in source_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f"{book_entries['Yuan-ti: Snake People'].slug}\""
        in source_body
    )
    assert source_body.index("Beholders: Bad Dreams Come True") < source_body.index("Giants: World Shakers")
    assert source_body.index("Kobolds: Little Dragons") < source_body.index("Mind Flayers: Scourge of Worlds")
    assert source_body.index("Orcs: The Godsworn") < source_body.index("Yuan-ti: Snake People")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Beholders: Bad Dreams Come True" in category_body
    assert "Mind Flayers: Scourge of Worlds" in category_body
    assert "Yuan-ti: Snake People" in category_body
    assert category_body.index("Beholders: Bad Dreams Come True") < category_body.index("Giants: World Shakers")
    assert category_body.index("Kobolds: Little Dragons") < category_body.index("Mind Flayers: Scourge of Worlds")
    assert category_body.index("Orcs: The Godsworn") < category_body.index("Yuan-ti: Snake People")

    assert beholders_response.status_code == 200
    beholders_body = beholders_response.get_data(as_text=True)
    assert "Chapter 1" in beholders_body
    assert "Monster Lore" in beholders_body
    assert "Chapter Navigation" in beholders_body
    assert "Roleplaying a Beholder" in beholders_body
    assert "Battle Tactics" in beholders_body
    assert "Variant Abilities" in beholders_body
    assert 'href="#roleplaying-a-beholder"' in beholders_body
    assert 'href="#battle-tactics"' in beholders_body
    assert 'id="variant-abilities"' in beholders_body


def test_vgm_monster_lore_wrappers_surface_related_monster_family_entries(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "monster"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }
        monster_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="monster", limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page_expectations = {
        "Beholders: Bad Dreams Come True": ("Death Kiss", "Gauth", "Gazer"),
        "Giants: World Shakers": ("Cloud Giant Smiling One", "Mouth of Grolantor"),
        "Gnolls: The Insatiable Hunger": ("Flind", "Gnoll Witherling"),
        "Goblinoids: The Conquering Host": ("Nilbog", "Hobgoblin Devastator"),
        "Hags: Dark Sisterhood": ("Annis Hag", "Bheur Hag"),
        "Kobolds: Little Dragons": ("Kobold Dragonshield", "Kobold Inventor"),
        "Mind Flayers: Scourge of Worlds": ("Alhoon", "Mindwitness", "Ulitharid"),
        "Orcs: The Godsworn": ("Orc Hand of Yurtrus", "Tanarukk"),
        "Yuan-ti: Snake People": ("Yuan-ti Anathema", "Yuan-ti Broodguard"),
    }

    for title, monster_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Related Monsters" in body
        for monster_title in monster_titles:
            assert monster_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{monster_entries[monster_title].slug}"'
                in body
            )


def test_vgm_monster_lore_wrappers_preserve_reference_only_source_context_sections(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore-source-context")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])

    beholder_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Beholders: Bad Dreams Come True'].slug}"
    )
    assert beholder_response.status_code == 200
    beholder_body = beholder_response.get_data(as_text=True)
    assert "Source Context" in beholder_body
    assert "roleplaying, lair, tactics, and variant-ability guidance" in beholder_body
    assert "The app does not currently model them automatically." in beholder_body
    assert 'href="#roleplaying-a-beholder"' in beholder_body
    assert 'href="#battle-tactics"' in beholder_body
    assert 'href="#variant-abilities"' in beholder_body
    assert 'id="roleplaying-a-beholder"' in beholder_body
    assert 'id="variant-abilities"' in beholder_body

    hag_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Hags: Dark Sisterhood'].slug}")
    assert hag_response.status_code == 200
    hag_body = hag_response.get_data(as_text=True)
    assert 'href="#hag-lair-actions"' in hag_body
    assert 'href="#hag-lair-actions--lair-actions"' in hag_body
    assert 'href="#hag-lair-actions--regional-effects"' in hag_body
    assert 'id="hag-lair-actions--regional-effects"' in hag_body

    kobold_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Kobolds: Little Dragons'].slug}"
    )
    assert kobold_response.status_code == 200
    kobold_body = kobold_response.get_data(as_text=True)
    assert 'href="#tactics"' in kobold_body
    assert 'id="tactics"' in kobold_body


def test_vgm_character_race_wrappers_surface_related_race_entries(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-character-race-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "race"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }
        race_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="race", limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page_expectations = {
        "Aasimar": ("Aasimar", "Protector Aasimar", "Scourge Aasimar", "Fallen Aasimar"),
        "Firbolg": ("Firbolg",),
        "Goliath": ("Goliath",),
        "Kenku": ("Kenku",),
        "Lizardfolk": ("Lizardfolk",),
        "Tabaxi": ("Tabaxi",),
        "Triton": ("Triton",),
        "Monstrous Adventurers": ("Bugbear", "Goblin", "Hobgoblin", "Kobold", "Orc", "Yuan-ti Pureblood"),
        "Height and Weight": ("Aasimar", "Firbolg", "Triton", "Bugbear", "Yuan-ti Pureblood"),
    }

    for title, race_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Related Races" in body
        for race_title in race_titles:
            assert race_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{race_entries[race_title].slug}"' in body
            )


def test_mm_book_pages_surface_related_monsters_and_monster_rules(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["action", "condition", "sense", "skill", "status"])
        importer.import_source("MM", entry_types=["book", "monster", "sense"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "MM",
                entry_type="book",
                limit=None,
            )
        }
        mm_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("monster", "sense")
            for entry in store.list_entries_for_source("DND-5E", "MM", entry_type=entry_type, limit=None)
        }
        phb_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "condition", "sense", "skill", "status")
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type=entry_type, limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    statistics_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Statistics'].slug}")
    legendary_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Legendary Creatures'].slug}"
    )
    shadow_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Shadow Dragon Template'].slug}"
    )
    half_dragon_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Half-Dragon Template'].slug}"
    )
    spore_servant_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spore Servant Template'].slug}"
    )

    assert statistics_response.status_code == 200
    statistics_body = statistics_response.get_data(as_text=True)
    assert "Monsters:" in statistics_body
    assert "Skills:" in statistics_body
    assert "Senses:" in statistics_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("monster", "Goblin")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("monster", "Guard")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Perception")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("sense", "Tremorsense")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Invisible")].slug}"'
        in statistics_body
    )

    assert legendary_response.status_code == 200
    legendary_body = legendary_response.get_data(as_text=True)
    assert "Conditions:" in legendary_body
    assert "Statuses:" in legendary_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Incapacitated")].slug}"'
        in legendary_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("status", "Surprised")].slug}"'
        in legendary_body
    )

    assert shadow_response.status_code == 200
    shadow_body = shadow_response.get_data(as_text=True)
    assert "Skills:" in shadow_body
    assert "Actions:" in shadow_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Stealth")].slug}"'
        in shadow_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Hide")].slug}"'
        in shadow_body
    )

    assert half_dragon_response.status_code == 200
    half_dragon_body = half_dragon_response.get_data(as_text=True)
    assert "Senses:" in half_dragon_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Blindsight")].slug}"'
        in half_dragon_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"'
        in half_dragon_body
    )

    assert spore_servant_response.status_code == 200
    spore_servant_body = spore_servant_response.get_data(as_text=True)
    assert "Senses:" in spore_servant_body
    assert "Conditions:" in spore_servant_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Blindsight")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Blinded")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Charmed")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Frightened")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Paralyzed")].slug}"'
        in spore_servant_body
    )


def test_dmg_book_chapters_surface_related_imported_entities(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["action", "book", "disease", "item", "variantrule"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "DMG",
                entry_type="book",
                limit=None,
            )
        }
        dmg_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "disease", "item", "variantrule")
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type=entry_type, limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    treasure_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Treasure'].slug}")
    downtime_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Downtime Activities'].slug}")
    running_the_game_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Running the Game'].slug}")

    assert treasure_response.status_code == 200
    treasure_body = treasure_response.get_data(as_text=True)
    assert "Equipment:" in treasure_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("item", "Potion of Healing")].slug}"' in treasure_body

    assert downtime_response.status_code == 200
    downtime_body = downtime_response.get_data(as_text=True)
    assert "Variant Rules:" in downtime_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{dmg_entries[("variantrule", "Downtime Activity: Building a Stronghold")].slug}"'
        in downtime_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{dmg_entries[("variantrule", "Downtime Activity: Carousing")].slug}"'
        in downtime_body
    )

    assert running_the_game_response.status_code == 200
    running_the_game_body = running_the_game_response.get_data(as_text=True)
    assert "Diseases:" in running_the_game_body
    assert "Actions:" in running_the_game_body
    assert "Variant Rules:" in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("disease", "Cackle Fever")].slug}"' in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("action", "Overrun")].slug}"' in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("variantrule", "Chases")].slug}"' in running_the_game_body


def test_phb_book_chapters_surface_related_imported_entities(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "PHB",
            entry_types=["action", "book", "condition", "feat", "item", "sense", "skill", "spell", "variantrule"],
        )

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "PHB",
                entry_type="book",
                limit=None,
            )
        }
        phb_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "condition", "feat", "item", "sense", "skill", "spell", "variantrule")
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type=entry_type, limit=None)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    step_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Step-by-Step Characters'].slug}")
    equipment_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Equipment'].slug}")
    customization_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Customization Options'].slug}"
    )
    ability_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Using Ability Scores'].slug}")
    adventuring_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Adventuring'].slug}")
    combat_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Combat'].slug}")
    spellcasting_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Spellcasting'].slug}")

    assert step_response.status_code == 200
    step_body = step_response.get_data(as_text=True)
    assert "Equipment:" in step_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Chain Mail")].slug}"' in step_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Longsword")].slug}"' in step_body

    assert equipment_response.status_code == 200
    equipment_body = equipment_response.get_data(as_text=True)
    assert "Equipment:" in equipment_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Chain Mail")].slug}"' in equipment_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Longsword")].slug}"' in equipment_body

    assert customization_response.status_code == 200
    customization_body = customization_response.get_data(as_text=True)
    assert "Variant Rules:" in customization_body
    assert "Feats:" in customization_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("variantrule", "Multiclassing")].slug}"'
        in customization_body
    )
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("feat", "Alert")].slug}"' in customization_body

    assert ability_response.status_code == 200
    ability_body = ability_response.get_data(as_text=True)
    assert "Skills:" in ability_body
    assert "Actions:" in ability_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Athletics")].slug}"' in ability_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Help")].slug}"' in ability_body

    assert adventuring_response.status_code == 200
    adventuring_body = adventuring_response.get_data(as_text=True)
    assert "Conditions:" in adventuring_body
    assert "Senses:" in adventuring_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Blinded")].slug}"' in adventuring_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"' in adventuring_body

    assert combat_response.status_code == 200
    combat_body = combat_response.get_data(as_text=True)
    assert "Actions:" in combat_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Help")].slug}"' in combat_body

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert "Spells:" in spellcasting_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("spell", "Mage Hand")].slug}"' in spellcasting_body


def test_xge_atomic_rule_wrappers_are_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_xge_atomic_wrapper_book_data_root(tmp_path / "dnd5e-source-xge-atomic-wrappers")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="XGE",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "XGE",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == list(XGE_ATOMIC_WRAPPER_TEST_TITLES)

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    falling_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Falling'].slug}")
    variant_rules_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Variant Rules'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    source_indexes = [source_body.index(title) for title in XGE_ATOMIC_WRAPPER_TEST_TITLES]
    assert source_indexes == sorted(source_indexes)

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    category_indexes = [category_body.index(title) for title in XGE_ATOMIC_WRAPPER_TEST_TITLES]
    assert category_indexes == sorted(category_indexes)

    assert falling_response.status_code == 200
    falling_body = falling_response.get_data(as_text=True)
    assert "Chapter 2" in falling_body
    assert "Dungeon Master&#39;s Tools" in falling_body
    assert "Rate of Falling" in falling_body
    assert "Flying Creatures and Falling" in falling_body
    assert 'href="#rate-of-falling"' in falling_body
    assert 'id="flying-creatures-and-falling"' in falling_body

    assert variant_rules_response.status_code == 200
    variant_rules_body = variant_rules_response.get_data(as_text=True)
    assert "Appendix A" in variant_rules_body
    assert "Shared Campaigns" in variant_rules_body
    assert "bounded rules list" in variant_rules_body


def test_xge_atomic_rule_wrappers_follow_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_xge_atomic_wrapper_book_data_root(
        tmp_path / "dnd5e-source-xge-atomic-wrappers-policy"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="XGE",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Simultaneous Effects'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Simultaneous Effects'].slug}"
    )

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Simultaneous Effects" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Chapter 2" in dm_body
    assert "Dungeon Master&#39;s Tools" in dm_body


def test_xge_first_wrapper_slice_excludes_broader_section_pages(app, tmp_path):
    data_root = build_xge_atomic_wrapper_book_data_root(
        tmp_path / "dnd5e-source-xge-atomic-wrapper-boundary"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("XGE", entry_types=["book"])
        store = app.extensions["systems_store"]
        book_entries = list(
            store.list_entries_for_source("DND-5E", "XGE", entry_type="book", limit=20)
        )

    assert result.imported_count == len(XGE_ATOMIC_WRAPPER_TEST_TITLES)
    assert result.imported_by_type == {"book": len(XGE_ATOMIC_WRAPPER_TEST_TITLES)}
    book_titles = {entry.title for entry in book_entries}
    assert book_titles == set(XGE_ATOMIC_WRAPPER_TEST_TITLES)
    assert "Tool Proficiencies" not in book_titles
    assert "Spellcasting" not in book_titles
    assert "Downtime Revisited" not in book_titles
    assert "Encounter Building" not in book_titles
    assert "Random Encounters: A World of Possibilities" not in book_titles
    assert "Traps Revisited" not in book_titles
    assert "Awarding Magic Items" not in book_titles
    assert "Shared Campaigns" not in book_titles


def test_rules_reference_search_uses_curated_metadata_without_full_body_search(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-reference-search")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

    sign_in(users["party"]["email"], users["party"]["password"])

    heading_response = client.get("/campaigns/linden-pass/systems/search?reference_q=passive+checks")
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB?reference_q=surprise")
    rule_response = client.get("/campaigns/linden-pass/systems/search?reference_q=15+strength")
    negative_response = client.get("/campaigns/linden-pass/systems/search?reference_q=training+talent")

    assert heading_response.status_code == 200
    heading_body = heading_response.get_data(as_text=True)
    assert "Rules Reference Search" in heading_body
    assert "Using Ability Scores" in heading_body
    assert "PHB | Book Chapters | Chapter 7" in heading_body

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Rules Reference Search" in source_body
    assert "Combat" in source_body
    assert "PHB | Book Chapters | Chapter 9" in source_body
    assert "Searches only this source&#39;s book chapters using curated metadata" in source_body
    assert "`RULES` entries" not in source_body

    assert rule_response.status_code == 200
    rule_body = rule_response.get_data(as_text=True)
    assert "Carrying Capacity and Encumbrance" in rule_body
    assert "RULES | Rules" in rule_body

    assert negative_response.status_code == 200
    negative_body = negative_response.get_data(as_text=True)
    assert "No rules references matched that metadata search yet." in negative_body
    assert "Using Ability Scores" not in negative_body


def test_importer_skips_xphb_subclass_variants(app, tmp_path):
    data_root = build_xphb_variant_subclass_data_root(tmp_path / "dnd5e-source-xphb-variants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("EGW", entry_types=["subclass", "subclassfeature"])
        subclasses = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "EGW",
            entry_type="subclass",
        )
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "EGW",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclass": 1, "subclassfeature": 1}
    assert [entry.slug for entry in subclasses] == ["egw-subclass-chronurgymagic-wizard-phb"]
    assert [entry.slug for entry in subclassfeatures] == [
        "egw-subclassfeature-chronurgymagic-wizard-phb-chronurgy-egw-2"
    ]


def test_importer_skips_efa_variant_subclass_aliases(app, tmp_path):
    data_root = build_efa_variant_subclass_data_root(tmp_path / "dnd5e-source-efa-variants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("TCE", entry_types=["subclass", "subclassfeature"])
        subclasses = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclass",
        )
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclass": 1, "subclassfeature": 1}
    assert [entry.slug for entry in subclasses] == ["tce-subclass-alchemist-artificer-tce"]
    assert [entry.slug for entry in subclassfeatures] == [
        "tce-subclassfeature-alchemist-artificer-tce-alchemist-tce-3"
    ]


def test_class_pages_surface_optionalfeature_progression_options(app, client, sign_in, users, tmp_path):
    data_root = build_class_optionalfeature_progression_data_root(tmp_path / "dnd5e-source-class-optionalfeatures")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "optionalfeature"])
        importer.import_source("TCE", entry_types=["class", "classfeature", "optionalfeature"])

        store = app.extensions["systems_store"]
        warlock_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20)
            if entry.title == "Warlock"
        )
        artificer_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="class", limit=20)
            if entry.title == "Artificer"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    warlock_response = client.get(f"/campaigns/linden-pass/systems/entries/{warlock_entry.slug}")
    artificer_response = client.get(f"/campaigns/linden-pass/systems/entries/{artificer_entry.slug}")

    assert warlock_response.status_code == 200
    warlock_body = warlock_response.get_data(as_text=True)
    assert "Eldritch Invocations" in warlock_body
    assert "Agonizing Blast" in warlock_body
    assert "Armor of Shadows" in warlock_body
    assert "Level 2: 2" in warlock_body
    assert "Level 5: 3" in warlock_body

    assert artificer_response.status_code == 200
    artificer_body = artificer_response.get_data(as_text=True)
    assert "Infusions Known" in artificer_body
    assert "Enhanced Arcane Focus" in artificer_body
    assert "Mind Sharpener" in artificer_body
    assert "Level 2: 4" in artificer_body
    assert "Level 6: 6" in artificer_body
    assert "Class Optional Features" not in artificer_body


def test_subclass_pages_and_subclassfeature_pages_surface_optionalfeature_cards(
    app, client, sign_in, users, tmp_path
):
    data_root = build_subclass_optionalfeature_progression_data_root(tmp_path / "dnd5e-source-subclass-optionalfeatures")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["subclass", "subclassfeature", "optionalfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclass", limit=20)
            if entry.title == "Arcane Archer"
        )
        subclassfeature_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclassfeature", limit=20)
            if entry.title == "Arcane Shot Options"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")
    subclassfeature_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclassfeature_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Subclass Features By Level" in subclass_body
    assert "Arcane Shot Options" in subclass_body
    assert "Banishing Arrow" in subclass_body
    assert "Bursting Arrow" in subclass_body
    assert "systems-inline-option-card" in subclass_body
    assert "Subclass Optional Features" not in subclass_body

    assert subclassfeature_response.status_code == 200
    subclassfeature_body = subclassfeature_response.get_data(as_text=True)
    assert "Banishing Arrow" in subclassfeature_body
    assert "Bursting Arrow" in subclassfeature_body
    assert "Choose 2 options" in subclassfeature_body
    assert "systems-inline-option-card" in subclassfeature_body
    assert "<strong>Subclass:</strong> <span>Arcane Archer</span>" in subclassfeature_body


def test_subclass_pages_match_subclassfeature_short_names_to_full_titles(
    app, client, sign_in, users, tmp_path
):
    data_root = build_subclass_short_name_matching_data_root(tmp_path / "dnd5e-source-subclass-short-name")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "College of Lore"
        )
        subclassfeature_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclassfeature", limit=20)
            if entry.title == "Bonus Proficiencies"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Subclass Features By Level" in subclass_body
    assert "Bonus Proficiencies" in subclass_body
    assert "You gain proficiency with three skills of your choice." in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{subclassfeature_entry.slug}"' in subclass_body


def test_subclass_import_preserves_structured_spellcasting_metadata(app, tmp_path):
    data_root = build_subclass_spellcasting_data_root(tmp_path / "dnd5e-source-subclass-spellcasting")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclass", limit=20)
            if entry.title == "Spellblade"
        )

    assert subclass_entry.metadata["spellcasting_ability"] == "int"
    assert subclass_entry.metadata["caster_progression"] == "1/3"
    assert subclass_entry.metadata["cantrip_progression"] == [0, 0, 2, 2]
    assert subclass_entry.metadata["spells_known_progression"] == [0, 0, 3, 4]
    assert subclass_entry.metadata["slot_progression"] == [
        [],
        [],
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 3}],
    ]


def test_subclass_pages_surface_campaign_mechanics_progression_overlays(
    app, client, sign_in, users, tmp_path
):
    data_root = build_campaign_subclass_progression_data_root(tmp_path / "dnd5e-source-campaign-subclass-progression")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "Wild Magic"
        )

        campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
        page_path = campaigns_dir / "linden-pass" / "content" / "mechanics" / "wild-magic-modification.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "---\n"
            "title: Wild Magic Modification\n"
            "section: Mechanics\n"
            "type: mechanic\n"
            "subsection: Class Modifications\n"
            "character_progression:\n"
            "  kind: subclass\n"
            "  class_name: Sorcerer\n"
            "  subclass_name: Wild Magic\n"
            "  level: 1\n"
            "  character_option:\n"
            "    name: Wild Magic Modification\n"
            "    activation_type: special\n"
            "    grants:\n"
            "      resource:\n"
            "        label: Wild Die\n"
            "        reset_on: long_rest\n"
            "        scaling:\n"
            "          mode: half_level\n"
            "          minimum: 1\n"
            "          round: down\n"
            "---\n\n"
            "You gain a number of Wild Die equal to half your level. A Wild Die is a d6.\n",
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Wild Magic Surge" in subclass_body
    assert "Wild Magic Modification" in subclass_body
    assert "Wild Die" in subclass_body
    assert "You gain a number of Wild Die equal to half your level." in subclass_body
    assert '/campaigns/linden-pass/pages/mechanics/wild-magic-modification' in subclass_body


def test_importer_skips_subclassfeatures_for_unsupported_subclass_sources(app, tmp_path):
    data_root = build_unsupported_cross_source_subclassfeature_data_root(
        tmp_path / "dnd5e-source-unsupported-subclassfeature-sources"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("TCE", entry_types=["subclassfeature"])
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclassfeature": 1}
    assert [entry.slug for entry in subclassfeatures] == [
        "tce-subclassfeature-blessedstrikes-cleric-phb-life-phb-8"
    ]


def test_class_features_are_hidden_from_source_index_and_embedded_on_class_pages(
    client, sign_in, users, app, tmp_path
):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

        store = app.extensions["systems_store"]
        fighter_entry = next(
            (entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20) if entry.title == "Fighter"),
            None,
        )
        feature_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="classfeature", limit=20)
                if entry.title == "Fighting Style"
            ),
            None,
        )
        skill_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="skill", limit=20)
                if entry.title == "Athletics"
            ),
            None,
        )
        archery_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="optionalfeature", limit=20)
                if entry.title == "Archery"
            ),
            None,
        )

    assert fighter_entry is not None
    assert feature_entry is not None
    assert skill_entry is not None
    assert archery_entry is not None

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    fighter_response = client.get(f"/campaigns/linden-pass/systems/entries/{fighter_entry.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/systems/sources/PHB/types/classfeature" not in source_body
    assert "/campaigns/linden-pass/systems/sources/PHB/types/subclassfeature" not in source_body
    assert "/campaigns/linden-pass/systems/sources/PHB/types/optionalfeature" not in source_body
    assert "Class Features are folded into their Class pages" in source_body
    assert "Subclass Features are folded into their Subclass pages" in source_body
    assert "Optional Features are surfaced under their related Class and Subclass pages" in source_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert '<h2>Class Features By Level</h2>' in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{feature_entry.slug}"' in fighter_body
    assert "Choose 2 from:" in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{skill_entry.slug}"' in fighter_body
    assert "Athletics" in fighter_body
    assert "History" in fighter_body
    assert "Fighting Style" in fighter_body
    assert "Martial Archetype (choose subclass feature)" in fighter_body
    assert "Class Feature" in fighter_body
    assert 'class="systems-inline-card__header"' in fighter_body
    assert "Level 1" in fighter_body
    assert "<p>Fighting Style</p>" not in fighter_body
    assert "Optional Feature Progression" not in fighter_body
    assert 'class="systems-inline-option-card"' in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{archery_entry.slug}"' in fighter_body
    assert "Choose 1 option:" in fighter_body
    assert "You gain a +2 bonus to attack rolls you make with ranged weapons." in fighter_body


def test_systems_entry_pages_surface_related_rules_references(
    client, sign_in, users, app, tmp_path
):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

        store = app.extensions["systems_store"]
        longsword_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="item", limit=20)
            if entry.title == "Longsword"
        )
        athletics_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="skill", limit=20)
            if entry.title == "Athletics"
        )
        mage_hand_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="spell", limit=20)
            if entry.title == "Mage Hand"
        )
        fighter_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20)
            if entry.title == "Fighter"
        )
        encumbrance_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="variantrule", limit=20)
            if entry.title == "Encumbrance"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    longsword_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")
    athletics_response = client.get(f"/campaigns/linden-pass/systems/entries/{athletics_entry.slug}")
    mage_hand_response = client.get(f"/campaigns/linden-pass/systems/entries/{mage_hand_entry.slug}")
    fighter_response = client.get(f"/campaigns/linden-pass/systems/entries/{fighter_entry.slug}")
    encumbrance_response = client.get(f"/campaigns/linden-pass/systems/entries/{encumbrance_entry.slug}")

    assert longsword_response.status_code == 200
    longsword_body = longsword_response.get_data(as_text=True)
    assert "Related Rules References" in longsword_body
    assert "Attack Rolls and Attack Bonus" in longsword_body
    assert "Damage Rolls" in longsword_body
    assert "Equipped Items, Inventory, and Attunement" in longsword_body

    assert athletics_response.status_code == 200
    athletics_body = athletics_response.get_data(as_text=True)
    assert "Related Rules References" in athletics_body
    assert "Ability Scores and Ability Modifiers" in athletics_body
    assert "Proficiency Bonus" in athletics_body
    assert "Skill Bonuses and Proficiency" in athletics_body

    assert mage_hand_response.status_code == 200
    mage_hand_body = mage_hand_response.get_data(as_text=True)
    assert "Related Rules References" in mage_hand_body
    assert "Spell Attacks and Save DCs" in mage_hand_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert "Related Rules References" in fighter_body
    assert "Proficiency Bonus" in fighter_body
    assert "Hit Points and Hit Dice" in fighter_body

    assert encumbrance_response.status_code == 200
    encumbrance_body = encumbrance_response.get_data(as_text=True)
    assert "Related Rules References" in encumbrance_body
    assert "Carrying Capacity and Encumbrance" in encumbrance_body


def test_source_index_and_category_page_respect_disabled_entry_overrides(
    client, sign_in, users, app, tmp_path
):
    data_root = build_large_feat_data_root(tmp_path / "dnd5e-source-large", count=3)

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["feat"])

        store = app.extensions["systems_store"]
        disabled_entry = next(
            (entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="feat", limit=10) if entry.title == "Feat 001"),
            None,
        )
        assert disabled_entry is not None
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug="DND-5E",
            entry_key=disabled_entry.entry_key,
            visibility_override=None,
            is_enabled_override=False,
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/feat")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "2 entries" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 2 feats in this source." in category_body
    assert "Feat 000" in category_body
    assert "Feat 001" not in category_body
    assert "Feat 002" in category_body
