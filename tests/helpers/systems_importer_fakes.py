from __future__ import annotations

import json
from pathlib import Path


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
                    "weaponCategory": "martial",
                    "dmg1": "1d8",
                    "dmg2": "1d10",
                    "dmgType": "S",
                    "property": ["V"],
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
