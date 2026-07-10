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
