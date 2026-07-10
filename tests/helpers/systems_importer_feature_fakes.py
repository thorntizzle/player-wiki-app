from __future__ import annotations

from pathlib import Path

from tests.helpers.systems_importer_fakes import build_test_data_root, write_json

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


def build_spell_class_lookup_data_root(root: Path) -> Path:
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
                    "entries": ["A spectral, floating hand appears at a point you choose within range."],
                }
            ]
        },
    )
    write_json(
        root / "data/generated/gendata-spell-source-lookup.json",
        {
            "phb": {
                "mage hand": {
                    "class": {
                        "PHB": {"Wizard": True},
                        "EFA": {"Artificer": True},
                    }
                }
            }
        },
    )
    return root


def build_spell_class_variant_data_root(root: Path) -> Path:
    write_json(
        root / "data/spells/spells-xge.json",
        {
            "spell": [
                {
                    "name": "Absorb Elements",
                    "source": "XGE",
                    "page": 152,
                    "level": 1,
                    "school": "A",
                    "time": [{"number": 1, "unit": "reaction"}],
                    "range": {"type": "self"},
                    "components": {"s": True},
                    "duration": [{"type": "instant"}],
                    "entries": ["The spell captures some of the incoming energy."],
                }
            ]
        },
    )
    write_json(
        root / "data/generated/gendata-spell-source-lookup.json",
        {
            "xge": {
                "absorb elements": {
                    "classVariant": {
                        "PHB": {
                            "Druid": {"definedInSources": ["XGE"]},
                            "Ranger": {"definedInSources": ["XGE"]},
                            "Sorcerer": {"definedInSources": ["XGE"]},
                            "Wizard": {"definedInSources": ["XGE"]},
                        },
                        "TCE": {
                            "Artificer": {"definedInSources": ["XGE"]},
                        },
                        "XPHB": {
                            "Fighter": {"definedInSources": ["XGE"]},
                        },
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
