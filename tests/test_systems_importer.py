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
                    "weight": 55,
                    "entries": ["Heavy armor made of interlocking metal rings."]
                },
                {
                    "name": "Light Crossbow",
                    "source": "PHB",
                    "page": 149,
                    "type": "R",
                    "weight": 5,
                    "entries": ["A martial ranged weapon with loading and two-handed properties."]
                },
                {
                    "name": "Crossbow Bolts (20)",
                    "source": "PHB",
                    "page": 150,
                    "type": "A",
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
                    "subclassSource": "SCAG",
                    "level": 8,
                    "page": 31,
                    "entries": ["Unsupported subclass source."],
                },
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
