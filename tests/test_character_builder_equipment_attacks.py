from __future__ import annotations

from tests.helpers.character_builder_fakes import *  # noqa: F401,F403

def test_level_one_builder_can_add_campaign_page_features_and_items():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True}],
        },
    )
    soldier = _systems_entry(
        "background",
        "phb-background-soldier",
        "Soldier",
        metadata={
            "skill_proficiencies": [{"athletics": True, "intimidation": True}],
        },
    )
    second_wind = _systems_entry(
        "classfeature",
        "phb-classfeature-second-wind",
        "Second Wind",
        metadata={"level": 1},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/arcane-overload",
            "Arcane Overload",
            section="Mechanics",
            subsection="Class Modifications",
            summary="A sample class modification for feature-card coverage.",
        ),
        _campaign_page_record(
            "items/stormglass-compass",
            "Stormglass Compass",
            section="Items",
            summary="A sample magic item whose title is used for search coverage.",
        ),
    ]

    form_values = {
        "name": "Campaign Hero",
        "character_slug": "campaign-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": soldier.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )

    assert _field_value_for_label(context, "campaign_feature_page_ref_1", "Arcane Overload")
    assert _field_value_for_label(context, "campaign_item_page_ref_1", "Stormglass Compass")

    form_values = {
        **form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(context, "campaign_feature_page_ref_1", "Arcane Overload"),
        "campaign_item_page_ref_1": _field_value_for_label(context, "campaign_item_page_ref_1", "Stormglass Compass"),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    arcane_overload = next(feature for feature in definition.features if feature["name"] == "Arcane Overload")
    stormglass_compass = next(item for item in definition.equipment_catalog if item["name"] == "Stormglass Compass")

    assert "Arcane Overload" in context["preview"]["features"]
    assert "Stormglass Compass" in context["preview"]["equipment"]
    assert arcane_overload["page_ref"] == "mechanics/arcane-overload"
    assert arcane_overload["category"] == "custom_feature"
    assert arcane_overload["description_markdown"] == "A sample class modification for feature-card coverage."
    assert stormglass_compass["page_ref"] == "items/stormglass-compass"
    assert stormglass_compass["notes"] == "A sample magic item whose title is used for search coverage."
def test_normalize_definition_to_native_model_merges_duplicate_attack_and_equipment_rows_ignoring_case():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "longsword-1",
            "name": "Longsword",
            "category": "Weapon",
            "attack_bonus": 5,
            "damage": "1d8+3 Slashing",
            "damage_type": "Slashing",
            "notes": "Versatile",
        },
        {
            "id": "longsword-2",
            "name": "Longsword",
            "category": "weapon",
            "attack_bonus": 5,
            "damage": "1d8+3 slashing",
            "damage_type": "slashing",
            "notes": "versatile",
        },
    ]
    definition.equipment_catalog = [
        {"id": "longsword-a", "name": "Longsword", "default_quantity": 1, "weight": "3 LB.", "notes": "Martial"},
        {"id": "longsword-b", "name": "Longsword", "default_quantity": 1, "weight": "3 lb.", "notes": "martial"},
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.attacks) == 1
    assert normalized.attacks[0]["name"] == "Longsword"
    assert len(normalized.equipment_catalog) == 1
    assert normalized.equipment_catalog[0]["default_quantity"] == 2
def test_normalize_definition_to_native_model_merges_linked_duplicate_attack_rows_when_names_differ():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "huron-blade-1",
            "name": "Huron Blade",
            "category": "Weapon",
            "attack_bonus": 5,
            "damage": "1d8+3 Slashing",
            "damage_type": "Slashing",
            "notes": "Versatile",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-longsword",
                "title": "Longsword",
                "source_id": "PHB",
            },
        },
        {
            "id": "longsword-2",
            "name": "Longsword",
            "category": "weapon",
            "attack_bonus": 5,
            "damage": "1d8+3 slashing",
            "damage_type": "slashing",
            "notes": "versatile",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-longsword",
                "title": "Longsword",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.attacks) == 1
    assert normalized.attacks[0]["name"] == "Huron Blade"
    assert normalized.attacks[0]["systems_ref"]["slug"] == "phb-item-longsword"
def test_normalize_definition_to_native_model_merges_linked_duplicate_attack_rows_with_same_mode_key():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "huron-blade-sharp-1",
            "name": "Huron Blade (sharpshooter)",
            "category": "weapon",
            "attack_bonus": 1,
            "damage": "1d8+13 slashing",
            "damage_type": "slashing",
            "notes": "Sharpshooter (-5 attack, +10 damage).",
            "mode_key": "feat:phb-feat-sharpshooter",
            "variant_label": "sharpshooter",
            "equipment_refs": ["huron-blade-1"],
        },
        {
            "id": "longsword-sharp-2",
            "name": "Longsword (sharpshooter)",
            "category": "weapon",
            "attack_bonus": 1,
            "damage": "1d8+13 slashing",
            "damage_type": "slashing",
            "notes": "Sharpshooter (-5 attack, +10 damage).",
            "equipment_refs": ["huron-blade-1"],
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.attacks) == 1
    assert normalized.attacks[0]["mode_key"] == "feat:phb-feat-sharpshooter"
    assert normalized.attacks[0]["variant_label"] == "sharpshooter"
    assert normalized.attacks[0]["equipment_refs"] == ["huron-blade-1"]
def test_normalize_definition_to_native_model_keeps_linked_attack_rows_separate_when_mode_keys_differ():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "longsword-sharp-1",
            "name": "Longsword (sharpshooter)",
            "category": "weapon",
            "attack_bonus": 1,
            "damage": "1d8+13 slashing",
            "damage_type": "slashing",
            "notes": "Sharpshooter (-5 attack, +10 damage).",
            "equipment_refs": ["longsword-1"],
        },
        {
            "id": "longsword-charger-2",
            "name": "Longsword (charger)",
            "category": "weapon",
            "attack_bonus": 1,
            "damage": "1d8+13 slashing",
            "damage_type": "slashing",
            "notes": "Charger (move 10 feet straight, +1d8 damage, once per turn).",
            "equipment_refs": ["longsword-1"],
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert len(normalized.attacks) == 2
    assert attacks_by_name["Longsword (sharpshooter)"]["mode_key"] == "feat:phb-feat-sharpshooter"
    assert attacks_by_name["Longsword (charger)"]["mode_key"] == "feat:xphb-feat-charger"
def test_normalize_definition_to_native_model_prefers_explicit_off_hand_weapon_mode_for_bonus_attack():
    definition = _minimal_character_definition("dual-wielder", "Dual Wielder")
    definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    definition.equipment_catalog = [
        {
            "id": "longsword-1",
            "name": "Longsword",
            "default_quantity": 1,
            "weight": "3 lb.",
            "is_equipped": True,
            "weapon_wield_mode": "main-hand",
        },
        {
            "id": "handaxe-2",
            "name": "Handaxe",
            "default_quantity": 1,
            "weight": "2 lb.",
            "is_equipped": True,
            "weapon_wield_mode": "off-hand",
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert "Handaxe (off-hand)" in attacks_by_name
    assert "Longsword (off-hand)" not in attacks_by_name
def test_normalize_definition_to_native_model_infers_legacy_attack_mode_metadata_from_suffix():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "crossbow-expert-1",
            "name": "Hand Crossbow (crossbow expert, sharpshooter)",
            "category": "ranged weapon",
            "attack_bonus": 1,
            "damage": "1d6+13 piercing",
            "damage_type": "piercing",
            "notes": (
                "Ammunition, range 30/120, Bonus action, Crossbow Expert bonus attack, "
                "Sharpshooter (-5 attack, +10 damage)."
            ),
            "equipment_refs": ["hand-crossbow-1"],
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.attacks[0]["mode_key"] == "feat:phb-feat-crossbow-expert:bonus|feat:phb-feat-sharpshooter"
    assert normalized.attacks[0]["variant_label"] == "crossbow expert, sharpshooter"
def test_normalize_definition_to_native_model_leaves_unrecognized_imported_attack_suffix_as_notes_only():
    definition = _minimal_imported_character_definition("mira-salt", "Mira Salt")
    definition.attacks = [
        {
            "id": "greatsword-slayer-1",
            "name": "Greatsword (slayer)",
            "category": "weapon",
            "attack_bonus": 6,
            "damage": "2d6+3 slashing",
            "damage_type": "slashing",
            "notes": "Bonus attack on crit or kill.",
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.attacks[0]["name"] == "Greatsword (slayer)"
    assert normalized.attacks[0]["notes"] == "Bonus attack on crit or kill."
    assert "mode_key" not in normalized.attacks[0]
    assert "variant_label" not in normalized.attacks[0]
def test_recalculate_definition_attacks_preserves_mode_identity_for_supported_variants():
    hand_crossbow = _systems_entry("item", "phb-item-hand-crossbow", "Hand Crossbow", metadata={"weight": 3})
    definition = _minimal_character_definition("bolt-dancer", "Bolt Dancer")
    definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    definition.equipment_catalog = [
        {
            "id": "hand-crossbow-1",
            "name": "Hand Crossbow",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": hand_crossbow.slug,
                "title": hand_crossbow.title,
                "source_id": "PHB",
            },
        }
    ]
    definition.features = [
        {
            "id": "sharpshooter-1",
            "name": "Sharpshooter",
            "category": "feat",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-sharpshooter",
                "title": "Sharpshooter",
                "source_id": "PHB",
            },
        },
        {
            "id": "crossbow-expert-1",
            "name": "Crossbow Expert",
            "category": "feat",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-crossbow-expert",
                "title": "Crossbow Expert",
                "source_id": "PHB",
            },
        },
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog={
            "by_title": {"hand crossbow": hand_crossbow},
            "by_slug": {hand_crossbow.slug: hand_crossbow},
        },
    )
    attacks_by_name = {attack["name"]: attack for attack in recalculated}

    assert attacks_by_name["Hand Crossbow (sharpshooter)"]["mode_key"] == "feat:phb-feat-sharpshooter"
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["mode_key"] == "feat:phb-feat-crossbow-expert:bonus"
    assert attacks_by_name["Hand Crossbow (crossbow expert, sharpshooter)"]["mode_key"] == (
        "feat:phb-feat-crossbow-expert:bonus|feat:phb-feat-sharpshooter"
    )
def test_recalculate_definition_attacks_adds_weapon_rows_when_import_only_has_unarmed_strike():
    dagger = _systems_entry("item", "phb-item-dagger", "Dagger", metadata={"weight": 1})
    shortbow = _systems_entry("item", "phb-item-shortbow", "Shortbow", metadata={"weight": 2})
    definition = _minimal_imported_character_definition("rasputin-like", "Rasputin Like")
    definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.attacks = [
        {
            "id": "unarmed-strike-1",
            "name": "Unarmed Strike",
            "category": "unarmed",
            "attack_bonus": 3,
            "damage": "1 Bludgeoning",
            "damage_type": "",
            "notes": "",
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "dagger-2",
            "name": "Dagger",
            "default_quantity": 2,
            "weight": "1 lb.",
            "notes": "",
            "is_equipped": False,
            "systems_ref": _systems_ref(dagger),
        },
        {
            "id": "shortbow-4",
            "name": "Shortbow",
            "default_quantity": 1,
            "weight": "2 lb.",
            "notes": "",
            "is_equipped": False,
            "systems_ref": _systems_ref(shortbow),
        },
        {
            "id": "plus-one-dagger-7",
            "name": "+1 Dagger",
            "default_quantity": 1,
            "weight": "1 lb.",
            "notes": "",
            "is_equipped": True,
            "weapon_wield_mode": "main-hand",
        },
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog=_build_item_catalog([dagger, shortbow]),
    )
    attacks_by_name = {attack["name"]: attack for attack in recalculated}

    assert {"Dagger", "Dagger (thrown)", "Shortbow", "+1 Dagger", "Unarmed Strike"}.issubset(attacks_by_name)
    assert attacks_by_name["Dagger"]["equipment_refs"] == ["dagger-2"]
    assert attacks_by_name["Dagger (thrown)"]["equipment_refs"] == ["dagger-2"]
    assert attacks_by_name["Shortbow"]["equipment_refs"] == ["shortbow-4"]
    assert attacks_by_name["+1 Dagger"]["attack_bonus"] == 6
    assert attacks_by_name["+1 Dagger"]["damage"] == "1d4+4 piercing"
    assert attacks_by_name["+1 Dagger"]["equipment_refs"] == ["plus-one-dagger-7"]
def test_recalculate_definition_attacks_keeps_unmatched_custom_attack_list_authoritative():
    dagger = _systems_entry("item", "phb-item-dagger", "Dagger", metadata={"weight": 1})
    definition = _minimal_imported_character_definition("moon-duelist", "Moon Duelist")
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.attacks = [
        {
            "id": "crescent-moon-strike-1",
            "name": "Crescent Moon Strike",
            "category": "special action",
            "attack_bonus": 7,
            "damage": "2d6 radiant",
            "damage_type": "radiant",
            "notes": "Campaign-specific weapon form.",
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "dagger-2",
            "name": "Dagger",
            "default_quantity": 1,
            "weight": "1 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": _systems_ref(dagger),
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog=_build_item_catalog([dagger]),
    )

    assert [attack["name"] for attack in recalculated] == ["Crescent Moon Strike"]
def test_recalculate_definition_attacks_preserves_structured_attack_mode_identity():
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4})
    definition = _minimal_character_definition("disciplined-guard", "Disciplined Guard")
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "quarterstaff-1",
            "name": "Quarterstaff",
            "default_quantity": 1,
            "weight": "4 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": quarterstaff.slug,
                "title": quarterstaff.title,
                "source_id": "PHB",
            },
        }
    ]
    definition.features = [
        {
            "id": "precision-drill-1",
            "name": "Precision Drill",
            "category": "custom_feature",
            "campaign_option": {
                "modeled_effects": [
                    "attack-mode:melee:precise strike:0:0:1d6",
                ]
            },
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog={
            "by_title": {"quarterstaff": quarterstaff},
            "by_slug": {quarterstaff.slug: quarterstaff},
        },
    )
    attacks_by_name = {attack["name"]: attack for attack in recalculated}

    assert attacks_by_name["Quarterstaff (precise strike)"]["mode_key"] == "effect:attack-mode:melee:precise-strike"
    assert attacks_by_name["Quarterstaff (precise strike)"]["variant_label"] == "precise strike"
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["mode_key"] == (
        "effect:attack-mode:melee:precise-strike|weapon:two-handed"
    )
def test_describe_equipment_state_support_uses_campaign_item_page_weapon_metadata_by_title():
    item_catalog = _attach_campaign_item_page_support(
        {"phb_weapon_profiles": {"Quarterstaff": {"title": "Quarterstaff", "type": "M", "weapon_category": "simple", "properties": ["V"], "damage": "1d6", "versatile_damage": "1d8", "damage_type": "B", "range": ""}}},
        [
            _campaign_page_record(
                "items/staff-of-the-crescent-moon",
                "Staff of the Crescent Moon",
                section="Items",
                body_markdown=(
                    "*Weapon (quarterstaff), rare (requires attunement by a sorcerer)*\n\n"
                    "Simple weapon, melee weapon\n\n"
                    "1d6 bludgeoning, versatile 1d8\n"
                ),
            )
        ],
    )

    support = describe_equipment_state_support(
        {
            "id": "staff-of-the-crescent-moon-1",
            "name": "Staff of the Crescent Moon",
            "default_quantity": 1,
            "weight": "4 lb.",
            "notes": "",
        },
        item_catalog=item_catalog,
    )

    assert support["supports_equipped_state"] is True
    assert support["supports_attunement"] is True
    assert support["requires_attunement"] is True
    assert support["is_weapon"] is True
    assert support["is_magic_item"] is True
def test_describe_equipment_state_support_recognizes_reordered_weapon_names():
    support = describe_equipment_state_support(
        {
            "id": "crossbow-light-1",
            "name": "Crossbow, Light",
            "default_quantity": 1,
            "weight": "5 lb.",
            "notes": "",
        },
        item_catalog={"phb_weapon_profiles": {"Light Crossbow": {"title": "Light Crossbow", "type": "R", "weapon_category": "simple", "properties": ["A", "LD", "2H"], "damage": "1d8", "versatile_damage": "", "damage_type": "P", "range": "80/320"}}},
    )

    assert support["supports_equipped_state"] is True
    assert support["is_weapon"] is True
def test_recalculate_definition_attacks_uses_campaign_item_page_weapon_bonus_metadata():
    definition = _minimal_character_definition("sun-bearer", "Sun Bearer")
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "censer-of-last-light-1",
            "name": "Censer of Last Light",
            "default_quantity": 1,
            "weight": "--",
            "notes": "",
            "is_equipped": True,
            "is_attuned": True,
        }
    ]

    item_catalog = _attach_campaign_item_page_support(
        {"phb_weapon_profiles": {"Mace": {"title": "Mace", "type": "M", "weapon_category": "simple", "properties": [], "damage": "1d6", "versatile_damage": "", "damage_type": "B", "range": ""}}},
        [
            _campaign_page_record(
                "items/censer-of-last-light",
                "Censer of Last Light",
                section="Items",
                body_markdown=(
                    "*Wondrous item (holy symbol), rare (requires attunement by a cleric of Bryneth)*\n\n"
                    "The censer can be wielded as a magic mace that grants a +1 bonus to attack and damage rolls made with it.\n"
                ),
            )
        ],
    )

    recalculated = _recalculate_definition_attacks(definition, item_catalog=item_catalog)

    assert len(recalculated) == 1
    attack = recalculated[0]
    assert attack["name"] == "Censer of Last Light"
    assert attack["category"] == "melee weapon"
    assert attack["attack_bonus"] == 6
    assert attack["damage"] == "1d6+4 bludgeoning"
    assert attack["damage_type"] == "bludgeoning"
    assert attack["page_ref"] == "items/censer-of-last-light"
    assert attack["equipment_refs"] == ["censer-of-last-light-1"]
def test_recalculate_definition_attacks_uses_approved_campaign_systems_item_mechanics():
    definition = _minimal_character_definition("huran-bearer", "Huran Bearer")
    definition.proficiencies["weapons"] = ["Martial Weapons"]
    item_entry = _systems_entry(
        "item",
        "custom-linden-pass-consecrated-huran-blade",
        "Consecrated Huran Blade",
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title="Consecrated Huran Blade",
            body_markdown=(
                "*Weapon (longsword), uncommon (requires attunement)*\n\n"
                "You gain a +1 bonus to attack and damage rolls made with this magic weapon.\n"
            ),
            source_page_ref="items/consecrated-huran-blade",
            review_status="approved",
        ),
    )
    definition.equipment_catalog = [
        {
            "id": "consecrated-huran-blade-1",
            "name": "Consecrated Huran Blade",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "systems_ref": _systems_ref(item_entry),
            "is_equipped": True,
            "is_attuned": True,
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog=_build_item_catalog([item_entry]),
    )

    assert len(recalculated) == 2
    attack = next(item for item in recalculated if item["damage"] == "1d8+4 slashing")
    assert attack["name"] == "Consecrated Huran Blade"
    assert attack["category"] == "melee weapon"
    assert attack["attack_bonus"] == 6
    assert attack["damage"] == "1d8+4 slashing"
    assert attack["systems_ref"]["slug"] == item_entry.slug
    assert attack["equipment_refs"] == ["consecrated-huran-blade-1"]
def test_recalculate_definition_attacks_uses_approved_innovators_bolt_base_weapon_mechanics():
    item_entry = _innovators_bolt_systems_entry()
    definition = _minimal_character_definition("flair-sparkmantle", "Flair Sparkmantle")
    definition.profile["class_level_text"] = "Artificer 6"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Artificer",
            "subclass_name": "Armorer",
            "level": 6,
        }
    ]
    definition.stats["proficiency_bonus"] = 3
    definition.stats["ability_scores"]["dex"] = {
        "score": 17,
        "modifier": 3,
        "save_bonus": 3,
    }
    definition.proficiencies["weapons"] = ["Firearms"]
    definition.equipment_catalog = [
        {
            "id": "manual-item-innovators-bolt",
            "name": "Innovator's Bolt",
            "default_quantity": 1,
            "weight": "",
            "notes": "",
            "systems_ref": _systems_ref(item_entry),
            "page_ref": {
                "slug": "items/innovators-bolt",
                "title": "Innovator's Bolt",
            },
            "is_equipped": True,
            "is_attuned": True,
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog=_build_item_catalog([item_entry]),
    )
    review_payload = dict(item_entry.metadata.get("campaign_item_mechanics") or {})
    flag_codes = {
        str(flag.get("code") or "").strip()
        for flag in list(review_payload.get("flags") or [])
    }

    assert len(recalculated) == 1
    attack = recalculated[0]
    assert campaign_item_special_effect_metadata("Innovator's Bolt") == {}
    assert review_payload["review_status"] == "approved"
    assert review_payload["support_state"] == "needs_implementation"
    assert {"area_effect", "condition_effect", "spell_slot_expenditure"}.issubset(flag_codes)
    assert attack["name"] == "Innovator's Bolt"
    assert attack["category"] == "ranged weapon"
    assert attack["attack_bonus"] == 7
    assert attack["damage"] == "1d10+4 piercing"
    assert attack["damage_type"] == "piercing"
    assert attack["notes"] == "Ammunition, loading, range 30/90."
    assert attack["systems_ref"]["slug"] == item_entry.slug
    assert attack["page_ref"]["slug"] == "items/innovators-bolt"
    assert attack["equipment_refs"] == ["manual-item-innovators-bolt"]
def test_recalculate_definition_attacks_ignores_unapproved_campaign_systems_item_mechanics():
    definition = _minimal_character_definition("draft-bearer", "Draft Bearer")
    definition.proficiencies["weapons"] = ["Martial Weapons"]
    item_entry = _systems_entry(
        "item",
        "custom-linden-pass-consecrated-huran-blade",
        "Consecrated Huran Blade",
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title="Consecrated Huran Blade",
            body_markdown=(
                "*Weapon (longsword), uncommon (requires attunement)*\n\n"
                "You gain a +1 bonus to attack and damage rolls made with this magic weapon.\n"
            ),
            source_page_ref="items/consecrated-huran-blade",
            review_status="draft",
        ),
    )
    definition.equipment_catalog = [
        {
            "id": "consecrated-huran-blade-1",
            "name": "Consecrated Huran Blade",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "systems_ref": _systems_ref(item_entry),
            "is_equipped": True,
            "is_attuned": True,
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog=_build_item_catalog([item_entry]),
    )

    assert recalculated == []
def test_recalculate_definition_attacks_preserves_existing_systems_link_for_matching_weapon_row():
    definition = _minimal_character_definition("arden-march", "Arden March")
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "light-crossbow-1",
            "name": "Light Crossbow",
            "default_quantity": 1,
            "weight": "5 lb.",
            "notes": "",
            "is_equipped": True,
        }
    ]
    definition.attacks = [
        {
            "id": "legacy-crossbow-attack",
            "name": "Crossbow, Light",
            "category": "ranged weapon",
            "attack_bonus": 5,
            "damage": "1d8+2 piercing",
            "damage_type": "piercing",
            "notes": "Ammunition, loading, range 80/320.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-crossbow-light",
                "title": "Crossbow, Light",
                "source_id": "PHB",
            },
        }
    ]

    recalculated = _recalculate_definition_attacks(
        definition,
        item_catalog={
            "phb_weapon_profiles": {
                "Light Crossbow": {
                    "title": "Light Crossbow",
                    "type": "R",
                    "weapon_category": "simple",
                    "properties": ["A", "LD", "2H"],
                    "damage": "1d8",
                    "versatile_damage": "",
                    "damage_type": "P",
                    "range": "80/320",
                }
            }
        },
    )

    attack = next(attack for attack in recalculated if attack["name"] == "Light Crossbow")

    assert attack["systems_ref"]["slug"] == "phb-item-crossbow-light"
    assert attack["equipment_refs"] == ["light-crossbow-1"]
def test_recalculate_definition_attacks_preserves_matching_campaign_page_attack_when_weapon_profile_is_unavailable():
    definition = _minimal_character_definition("zigzag-blackscar", "Zigzag Blackscar")
    definition.equipment_catalog = [
        {
            "id": "consecrated-huran-blade-1",
            "name": "Consecrated Huran Blade",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "page_ref": {
                "slug": "items/consecrated-huran-blade",
                "title": "Consecrated Huran Blade",
            },
            "is_equipped": True,
        }
    ]
    definition.attacks = [
        {
            "id": "consecrated-huran-blade-attack",
            "name": "Consecrated Huran Blade",
            "category": "melee weapon",
            "attack_bonus": 5,
            "damage": "1d8+2 slashing",
            "damage_type": "slashing",
            "notes": "Consecrated steel that burns the unclean.",
            "page_ref": {
                "slug": "items/consecrated-huran-blade",
                "title": "Consecrated Huran Blade",
            },
        }
    ]

    recalculated = _recalculate_definition_attacks(definition, item_catalog={})

    assert len(recalculated) == 1
    assert recalculated[0]["name"] == "Consecrated Huran Blade"
    assert recalculated[0]["page_ref"]["slug"] == "items/consecrated-huran-blade"
@pytest.mark.parametrize(
    ("is_equipped", "is_attuned"),
    [
        (False, True),
        (True, False),
    ],
)
def test_normalize_definition_to_native_model_requires_hourglass_pendant_worn_and_attuned(
    is_equipped: bool,
    is_attuned: bool,
):
    gift_of_alacrity = _systems_entry(
        "spell",
        "egw-spell-gift-of-alacrity",
        "Gift of Alacrity",
        metadata={"level": 1},
    )
    hourglass_pendant = _hourglass_pendant_systems_entry()
    definition = _minimal_character_definition("olin-itador", "Olin Itador")
    definition.profile["class_level_text"] = "Wizard 2"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "Chronurgy Magic",
            "level": 2,
        }
    ]
    definition.features = [
        {
            "id": "chronal-shift-1",
            "name": "Chronal Shift",
            "category": "subclass_feature",
            "source": "EGW",
            "description_markdown": "",
            "class_row_id": "class-row-1",
        }
    ]
    definition.spellcasting["spells"] = [
        {
            "name": "Gift of Alacrity",
            "mark": "Item",
            "spell_source_row_id": "spell-source:item:hourglass-pendant",
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "hourglass-pendant-1",
            "name": "Hourglass Pendant",
            "default_quantity": 1,
            "weight": "--",
            "notes": "",
            "is_equipped": is_equipped,
            "is_attuned": is_attuned,
            "systems_ref": _systems_ref(hourglass_pendant),
        }
    ]

    item_catalog = _build_item_catalog([hourglass_pendant])

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=_build_spell_catalog([gift_of_alacrity]),
    )
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}
    source_row_ids = {
        row["source_row_id"]
        for row in list(normalized.spellcasting.get("source_rows") or [])
    }
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert "Gift of Alacrity" not in spells_by_name
    assert "spell-source:item:hourglass-pendant" not in source_row_ids
    assert resources_by_id["chronal-shift"]["max"] == 2
def test_normalize_definition_to_native_model_ignores_unapproved_campaign_item_special_metadata():
    gift_of_alacrity = _systems_entry(
        "spell",
        "egw-spell-gift-of-alacrity",
        "Gift of Alacrity",
        metadata={"level": 1},
    )
    hourglass_pendant = _hourglass_pendant_systems_entry(review_status="draft")
    definition = _minimal_character_definition("olin-itador", "Olin Itador")
    definition.profile["class_level_text"] = "Wizard 2"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "Chronurgy Magic",
            "level": 2,
        }
    ]
    definition.features = [
        {
            "id": "chronal-shift-1",
            "name": "Chronal Shift",
            "category": "subclass_feature",
            "source": "EGW",
            "description_markdown": "",
            "class_row_id": "class-row-1",
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "hourglass-pendant-1",
            "name": "Hourglass Pendant",
            "default_quantity": 1,
            "weight": "--",
            "notes": "",
            "is_equipped": True,
            "is_attuned": True,
            "systems_ref": _systems_ref(hourglass_pendant),
        }
    ]

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=_build_item_catalog([hourglass_pendant]),
        spell_catalog=_build_spell_catalog([gift_of_alacrity]),
    )
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}

    assert "Gift of Alacrity" not in spells_by_name
    assert resources_by_id["chronal-shift"]["max"] == 2
def test_normalize_definition_to_native_model_applies_psionic_circlet_item_effects():
    psionic_circlet = _systems_entry(
        "item",
        "custom-linden-pass-psionic-circlet",
        "Psionic Circlet",
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title="Psionic Circlet",
            body_markdown=(
                "*Wondrous item, rare (requires attunement)*\n\n"
                "The circlet stabilizes psionic talent."
            ),
            explicit_mechanics={
                "ability_score_minimums": {"int": 14},
                "resource_template_bonuses": [
                    {
                        "id": "psionic-power-psionic-energy",
                        "bonus": 1,
                    }
                ],
                "attack_reminder_rules": [
                    {
                        "id": "item:psionic-circlet:psionic-options",
                        "title": "Psionic Circlet",
                        "save_dc_ability_key": "int",
                        "condition": (
                            "Once on each of your turns, after you hit a target within 30 feet with a weapon "
                            "attack and deal damage to it, you can expend one Psionic Energy die to use one "
                            "of these options."
                        ),
                        "attack_scope": {
                            "label": "Weapon attacks",
                            "categories": ["melee weapon", "ranged weapon"],
                        },
                        "effects": [
                            {
                                "kind": "saving_throw",
                                "label": "Wisdom save DC",
                                "summary": "Psychic Hindrance and Psychic Anchor use Wisdom save DC {save_dc}.",
                            },
                            {
                                "kind": "disadvantage",
                                "label": "Psychic Hindrance",
                                "summary": (
                                    "On a failed Wisdom save, the target's next attack roll before the end of "
                                    "its next turn is made with disadvantage."
                                ),
                            },
                            {
                                "kind": "advantage",
                                "label": "Psychic Opening",
                                "summary": (
                                    "The next attack roll made against the target before the start of your next "
                                    "turn has advantage."
                                ),
                            },
                            {
                                "kind": "speed_control",
                                "label": "Psychic Anchor",
                                "summary": (
                                    "On a failed Wisdom save, the target's speed becomes 0 until the end of "
                                    "its next turn."
                                ),
                            },
                        ],
                    }
                ],
            },
            source_page_ref="items/psionic-circlet",
            review_status="approved",
        ),
    )
    definition = _minimal_character_definition("zigzag-blackscar", "Zigzag Blackscar")
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Fighter",
            "subclass_name": "Psi Warrior",
            "level": 3,
        }
    ]
    definition.stats["ability_scores"]["int"] = {
        "score": 10,
        "modifier": 0,
        "save_bonus": 0,
    }
    definition.features = [
        {
            "id": "psionic-power-1",
            "name": "Psionic Power",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "class_row_id": "class-row-1",
            "systems_ref": {
                "entry_type": "subclassfeature",
                "slug": "tce-subclassfeature-psionic-power",
                "title": "Psionic Power",
                "source_id": "TCE",
            },
            "page_ref": "mechanics/psi-warrior/psionic-power",
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "psionic-circlet-1",
            "name": "Psionic Circlet",
            "default_quantity": 1,
            "weight": "--",
            "notes": "",
            "is_equipped": True,
            "is_attuned": True,
            "systems_ref": _systems_ref(psionic_circlet),
        }
    ]

    item_catalog = _build_item_catalog([psionic_circlet])

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
    )
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}
    reminder_state = dict(normalized.stats.get("attack_reminder_state") or {})
    circlet_rule = next(rule for rule in list(reminder_state.get("rules") or []) if rule["title"] == "Psionic Circlet")
    reminder_effects = {effect["label"]: effect["summary"] for effect in list(circlet_rule.get("effects") or [])}

    assert campaign_item_special_effect_metadata("Psionic Circlet") == {}
    assert normalized.stats["ability_scores"]["int"]["score"] == 14
    assert normalized.stats["ability_scores"]["int"]["modifier"] == 2
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 5
    assert resources_by_id["psionic-power-psionic-energy"]["initial_current"] == 5
    assert dict(circlet_rule["attack_scope"]) == {
        "label": "Weapon attacks",
        "categories": ["melee weapon", "ranged weapon"],
    }
    assert "Once on each of your turns" in circlet_rule["condition"]
    assert reminder_effects["Wisdom save DC"] == "Psychic Hindrance and Psychic Anchor use Wisdom save DC 12."
    assert reminder_effects["Psychic Hindrance"] == (
        "On a failed Wisdom save, the target's next attack roll before the end of its next turn is made "
        "with disadvantage."
    )
    assert reminder_effects["Psychic Opening"] == (
        "The next attack roll made against the target before the start of your next turn has advantage."
    )
    assert reminder_effects["Psychic Anchor"] == (
        "On a failed Wisdom save, the target's speed becomes 0 until the end of its next turn."
    )
def test_normalize_definition_to_native_model_merges_linked_duplicate_equipment_rows_when_names_differ():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.equipment_catalog = [
        {
            "id": "huron-blade-1",
            "name": "Huron Blade",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-longsword",
                "title": "Longsword",
                "source_id": "PHB",
            },
        },
        {
            "id": "longsword-2",
            "name": "Longsword",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-longsword",
                "title": "Longsword",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.equipment_catalog) == 1
    assert normalized.equipment_catalog[0]["name"] == "Huron Blade"
    assert normalized.equipment_catalog[0]["default_quantity"] == 2
    assert normalized.equipment_catalog[0]["systems_ref"]["slug"] == "phb-item-longsword"
def test_normalize_definition_to_native_model_recovers_missing_systems_item_links_for_equipment():
    definition = _minimal_imported_character_definition("mira-salt", "Mira Salt")
    definition.stats["armor_class"] = 9
    definition.equipment_catalog = [
        {
            "id": "chain-mail-1",
            "name": "Chain Mail",
            "default_quantity": 1,
            "weight": "55 lb.",
            "notes": "",
            "is_equipped": True,
        }
    ]
    item_catalog = _build_item_catalog(
        [
            _systems_entry(
                "item",
                "phb-item-chain-mail",
                "Chain Mail",
                metadata={"type": "HA", "ac": 16},
            )
        ]
    )

    normalized = normalize_definition_to_native_model(definition, item_catalog=item_catalog)

    assert normalized.stats["armor_class"] == 16
    assert normalized.equipment_catalog[0]["systems_ref"]["slug"] == "phb-item-chain-mail"
def test_normalize_definition_to_native_model_recovers_missing_campaign_item_page_links_for_equipment():
    definition = _minimal_imported_character_definition("mira-salt", "Mira Salt")
    definition.equipment_catalog = [
        {
            "id": "stormglass-compass-1",
            "name": "Stormglass Compass",
            "default_quantity": 1,
            "weight": "1 lb.",
            "notes": "",
        }
    ]
    item_catalog = _attach_campaign_item_page_support(
        _build_item_catalog([]),
        [
            SimpleNamespace(
                page_ref="items/stormglass-compass",
                page=SimpleNamespace(title="Stormglass Compass", section="Items"),
                body_markdown="*Wondrous item, rare*",
            )
        ],
    )

    normalized = normalize_definition_to_native_model(definition, item_catalog=item_catalog)

    page_ref = normalized.equipment_catalog[0]["page_ref"]
    assert page_ref["slug"] == "items/stormglass-compass"
    assert page_ref["title"] == "Stormglass Compass"
    assert normalized.equipment_catalog[0].get("systems_ref") in (None, {})
def test_normalize_definition_to_native_model_derives_imported_armor_class_from_equipped_armor_and_shield():
    definition = _minimal_imported_character_definition("mira-salt", "Mira Salt")
    definition.stats["armor_class"] = 12
    definition.equipment_catalog = [
        {
            "id": "chain-mail-1",
            "name": "Chain Mail",
            "default_quantity": 1,
            "weight": "55 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-chain-mail",
                "title": "Chain Mail",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
        {
            "id": "plate-1",
            "name": "Plate Armor",
            "default_quantity": 1,
            "weight": "65 lb.",
            "notes": "",
            "is_equipped": False,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-plate",
                "title": "Plate Armor",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    equipment_by_name = {item["name"]: item for item in normalized.equipment_catalog}

    assert normalized.stats["armor_class"] == 18
    assert equipment_by_name["Chain Mail"]["is_equipped"] is True
    assert equipment_by_name["Shield"]["is_equipped"] is True
def test_normalize_definition_to_native_model_applies_medium_armor_master_title_fallback_to_medium_armor_dex_cap():
    definition = _minimal_imported_character_definition("selene-march", "Selene March")
    definition.stats["armor_class"] = 99
    definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.equipment_catalog = [
        {
            "id": "scale-mail-1",
            "name": "Scale Mail",
            "default_quantity": 1,
            "weight": "45 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-scale-mail",
                "title": "Scale Mail",
                "source_id": "PHB",
            },
        }
    ]
    definition.features = [
        {
            "id": "medium-armor-master-1",
            "name": "Medium Armor Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.stats["armor_class"] == 17
    defensive_state = dict(normalized.stats.get("defensive_state") or {})
    assert dict(defensive_state.get("armor_state") or {}).get("stealth_disadvantage") is False
    assert dict(defensive_state.get("armor_state") or {}).get("stealth_disadvantage_suppressed") is True
    medium_armor_master_rule = next(rule for rule in list(defensive_state.get("rules") or []) if rule["title"] == "Medium Armor Master")
    assert medium_armor_master_rule["active"] is True
    assert medium_armor_master_rule["effects"][0]["kind"] == "armor_state"
def test_normalize_definition_to_native_model_derives_heavy_armor_master_and_shield_master_defensive_rules():
    definition = _minimal_character_definition("shield-wall", "Shield Wall")
    definition.features = [
        {
            "id": "heavy-armor-master-1",
            "name": "Heavy Armor Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-heavy-armor-master",
                "title": "Heavy Armor Master",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-master-1",
            "name": "Shield Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-shield-master",
                "title": "Shield Master",
                "source_id": "PHB",
            },
        },
    ]
    definition.equipment_catalog = [
        {
            "id": "chain-mail-1",
            "name": "Chain Mail",
            "default_quantity": 1,
            "weight": "55 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-chain-mail",
                "title": "Chain Mail",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    defensive_state = dict(normalized.stats.get("defensive_state") or {})
    armor_state = dict(defensive_state.get("armor_state") or {})
    rules_by_title = {rule["title"]: rule for rule in list(defensive_state.get("rules") or [])}

    assert armor_state["wearing_shield"] is True
    assert armor_state["shield_bonus"] == 2
    assert "heavy" in armor_state["equipped_armor_categories"]
    assert rules_by_title["Heavy Armor Master"]["active"] is True
    assert rules_by_title["Heavy Armor Master"]["effects"][0]["kind"] == "damage_mitigation"
    assert rules_by_title["Shield Master"]["active"] is True
    assert rules_by_title["Shield Master"]["effects"][0]["summary"].startswith(
        "Add +2 to Dexterity saves"
    )
    assert rules_by_title["Shield Master"]["effects"][1]["kind"] == "reaction"
def test_normalize_definition_to_native_model_preserves_imported_armor_class_when_only_shield_is_known():
    definition = _minimal_imported_character_definition("tobin-slate", "Tobin Slate")
    definition.stats["armor_class"] = 17
    definition.equipment_catalog = [
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.stats["armor_class"] == 17
def test_normalize_definition_to_native_model_derives_imported_plain_unarmored_armor_class_when_explicit_armor_state_proves_no_armor():
    definition = _minimal_imported_character_definition("lena-frost", "Lena Frost")
    definition.stats["armor_class"] = 17
    definition.stats["ability_scores"]["dex"] = {"score": 14, "modifier": 2, "save_bonus": 2}
    definition.equipment_catalog = [
        {
            "id": "chain-mail-1",
            "name": "Chain Mail",
            "default_quantity": 1,
            "weight": "55 lb.",
            "notes": "",
            "is_equipped": False,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-chain-mail",
                "title": "Chain Mail",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.stats["armor_class"] == 14
def test_normalize_definition_to_native_model_preserves_imported_armor_class_when_armor_presence_is_still_unproven():
    definition = _minimal_imported_character_definition("orsa-wick", "Orsa Wick")
    definition.stats["armor_class"] = 17
    definition.stats["ability_scores"]["dex"] = {"score": 14, "modifier": 2, "save_bonus": 2}
    definition.equipment_catalog = [
        {
            "id": "chain-mail-1",
            "name": "Chain Mail",
            "default_quantity": 1,
            "weight": "55 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-chain-mail",
                "title": "Chain Mail",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.stats["armor_class"] == 17
def test_normalize_definition_to_native_model_adds_single_shield_master_helper_row_for_multiple_shields():
    definition = _minimal_character_definition("shield-marshal", "Shield Marshal")
    definition.features = [
        {
            "id": "shield-master-1",
            "name": "Shield Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-shield-master",
                "title": "Shield Master",
                "source_id": "PHB",
            },
        }
    ]
    definition.equipment_catalog = [
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
        {
            "id": "shield-2",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "Spare shield",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.attacks) == 1
    shield_shove = normalized.attacks[0]
    assert shield_shove["name"] == "Shield Shove"
    assert shield_shove["category"] == "special action"
    assert shield_shove["attack_bonus"] is None
    assert shield_shove["damage"] == ""
    assert shield_shove["notes"] == "Bonus action after taking the Attack action; Shield Master shove within 5 feet."
    assert shield_shove["mode_key"] == "feat:phb-feat-shield-master:shove"
    assert shield_shove["equipment_refs"] == ["shield-1", "shield-2"]
def test_normalize_definition_to_native_model_adds_phb_grappler_helper_row():
    definition = _minimal_character_definition("lockdown-marshal", "Lockdown Marshal")
    definition.features = [
        {
            "id": "grappler-1",
            "name": "Grappler",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-grappler",
                "title": "Grappler",
                "source_id": "PHB",
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert len(normalized.attacks) == 1
    grapple_helper = normalized.attacks[0]
    assert grapple_helper["name"] == "Pin Grappled Creature"
    assert grapple_helper["category"] == "special action"
    assert grapple_helper["attack_bonus"] is None
    assert grapple_helper["damage"] == ""
    assert (
        grapple_helper["notes"]
        == "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends."
    )
    assert grapple_helper["mode_key"] == "feat:phb-feat-grappler:pin"
    assert "equipment_refs" not in grapple_helper
def test_normalize_definition_to_native_model_keeps_xphb_grappler_out_of_phb_helper_slice():
    definition = _minimal_character_definition("xphb-grappler", "XPHB Grappler")
    definition.features = [
        {
            "id": "grappler-1",
            "name": "Grappler",
            "category": "feat",
            "source": "XPHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "xphb-feat-grappler",
                "title": "Grappler",
                "source_id": "XPHB",
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.attacks == []
def test_normalize_definition_to_native_model_adds_phb_mounted_combatant_note_only_to_melee_rows():
    definition = _minimal_character_definition("mounted-marshal", "Mounted Marshal")
    definition.features = [
        {
            "id": "mounted-combatant-1",
            "name": "Mounted Combatant",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-mounted-combatant",
                "title": "Mounted Combatant",
                "source_id": "PHB",
            },
        }
    ]
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "handaxe-1",
            "name": "Handaxe",
            "default_quantity": 1,
            "weight": "2 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-handaxe",
                "title": "Handaxe",
                "source_id": "PHB",
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition)
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert (
        attacks_by_name["Handaxe"]["notes"]
        == "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)."
    )
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
def test_normalize_definition_to_native_model_keeps_xphb_mounted_combatant_out_of_phb_note_slice():
    definition = _minimal_character_definition("xphb-mounted-combatant", "XPHB Mounted Combatant")
    definition.features = [
        {
            "id": "mounted-combatant-1",
            "name": "Mounted Combatant",
            "category": "feat",
            "source": "XPHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "xphb-feat-mounted-combatant",
                "title": "Mounted Combatant",
                "source_id": "XPHB",
            },
        }
    ]
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "handaxe-1",
            "name": "Handaxe",
            "default_quantity": 1,
            "weight": "2 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-handaxe",
                "title": "Handaxe",
                "source_id": "PHB",
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition)
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert attacks_by_name["Handaxe"]["notes"] == ""
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
def test_normalize_definition_to_native_model_derives_stateful_attack_reminder_contract():
    definition = _minimal_character_definition("reactive-marshal", "Reactive Marshal")
    definition.features = [
        {
            "id": "sentinel-1",
            "name": "Sentinel",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-sentinel",
                "title": "Sentinel",
                "source_id": "PHB",
            },
        },
        {
            "id": "mage-slayer-1",
            "name": "Mage Slayer",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-mage-slayer",
                "title": "Mage Slayer",
                "source_id": "PHB",
            },
        },
        {
            "id": "crusher-1",
            "name": "Crusher",
            "category": "feat",
            "source": "TCE",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "tce-feat-crusher",
                "title": "Crusher",
                "source_id": "TCE",
            },
        },
        {
            "id": "piercer-1",
            "name": "Piercer",
            "category": "feat",
            "source": "TCE",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "tce-feat-piercer",
                "title": "Piercer",
                "source_id": "TCE",
            },
        },
        {
            "id": "slasher-1",
            "name": "Slasher",
            "category": "feat",
            "source": "TCE",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "tce-feat-slasher",
                "title": "Slasher",
                "source_id": "TCE",
            },
        },
    ]

    normalized = normalize_definition_to_native_model(definition)

    reminder_state = dict(normalized.stats.get("attack_reminder_state") or {})
    rules_by_title = {
        str(rule.get("title") or ""): dict(rule)
        for rule in list(reminder_state.get("rules") or [])
    }
    defensive_state = dict(normalized.stats.get("defensive_state") or {})
    defensive_rules_by_title = {
        str(rule.get("title") or ""): dict(rule)
        for rule in list(defensive_state.get("rules") or [])
    }

    assert dict(rules_by_title["Sentinel"]["attack_scope"]) == {
        "label": "Melee weapon attacks",
        "categories": ["melee weapon"],
    }
    assert [effect["kind"] for effect in list(rules_by_title["Sentinel"]["effects"] or [])] == [
        "opportunity_attack",
        "speed_control",
        "reaction",
    ]
    assert dict(rules_by_title["Mage Slayer"]["attack_scope"]) == {
        "label": "Melee weapon attacks",
        "categories": ["melee weapon"],
    }
    assert [effect["kind"] for effect in list(rules_by_title["Mage Slayer"]["effects"] or [])] == [
        "reaction",
        "concentration",
    ]
    assert dict(rules_by_title["Crusher"]["attack_scope"]) == {
        "label": "Bludgeoning attacks",
        "damage_types": ["Bludgeoning"],
    }
    assert dict(rules_by_title["Piercer"]["attack_scope"]) == {
        "label": "Piercing attacks",
        "damage_types": ["Piercing"],
    }
    assert dict(rules_by_title["Slasher"]["attack_scope"]) == {
        "label": "Slashing attacks",
        "damage_types": ["Slashing"],
    }
    assert defensive_rules_by_title["Mage Slayer"]["active"] is True
    assert defensive_rules_by_title["Mage Slayer"]["effects"] == [
        {
            "kind": "saving_throw",
            "label": "Spell saves",
            "summary": "You have advantage on saving throws against spells cast by creatures within 5 feet of you.",
        }
    ]
def test_normalize_definition_to_native_model_derives_carrying_capacity_from_size_and_title_effects():
    definition = _minimal_character_definition("river-stone", "River Stone")
    definition.profile["size"] = "Large"
    definition.features = [
        {
            "id": "powerful-build-1",
            "name": "Powerful Build",
            "category": "species_trait",
            "activation_type": "passive",
        }
    ]

    normalized = normalize_definition_to_native_model(definition)
    renormalized = normalize_definition_to_native_model(normalized)

    assert normalized.stats["carrying_capacity"] == 960
    assert normalized.stats["push_drag_lift"] == 1920
    assert renormalized.stats["carrying_capacity"] == 960
def test_normalize_definition_to_native_model_applies_structured_weapon_effect_bonuses():
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    definition = _minimal_character_definition("arden-kest", "Arden Kest")
    definition.proficiencies["weapons"] = ["Longswords"]
    definition.equipment_catalog = [
        {
            "id": "longsword-1",
            "name": "Longsword",
            "default_quantity": 1,
            "weight": "3 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_key": longsword.entry_key,
                "entry_type": longsword.entry_type,
                "title": longsword.title,
                "slug": longsword.slug,
                "source_id": longsword.source_id,
            },
        }
    ]
    definition.features = [
        {
            "id": "weapon-mastery-1",
            "name": "Weapon Mastery",
            "category": "feat",
            "campaign_option": {
                "modeled_effects": [
                    "weapon-attack-bonus:1",
                    "weapon-damage-bonus:2",
                ]
            },
        }
    ]

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog={
            "by_title": {"longsword": longsword},
            "by_slug": {longsword.slug: longsword},
        },
    )
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert attacks_by_name["Longsword"]["attack_bonus"] == 6
    assert attacks_by_name["Longsword"]["damage"] == "1d8+5 slashing"
def test_normalize_definition_to_native_model_applies_structured_attack_modes_to_melee_and_two_handed_rows():
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4})
    definition = _minimal_imported_character_definition("precise-guard", "Precise Guard")
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "quarterstaff-1",
            "name": "Quarterstaff",
            "default_quantity": 1,
            "weight": "4 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_key": quarterstaff.entry_key,
                "entry_type": quarterstaff.entry_type,
                "title": quarterstaff.title,
                "slug": quarterstaff.slug,
                "source_id": quarterstaff.source_id,
            },
        }
    ]
    definition.features = [
        {
            "id": "precision-drill-1",
            "name": "Precision Drill",
            "category": "custom_feature",
            "campaign_option": {
                "modeled_effects": [
                    "attack-mode:melee:precise strike:0:0:1d6",
                ]
            },
        }
    ]

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog={
            "by_title": {"quarterstaff": quarterstaff},
            "by_slug": {quarterstaff.slug: quarterstaff},
        },
    )
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}

    assert attacks_by_name["Quarterstaff (precise strike)"]["damage"] == "1d6+1d6+3 bludgeoning"
    assert attacks_by_name["Quarterstaff (precise strike)"]["notes"] == "Precise Strike (+1d6 damage)."
    assert attacks_by_name["Quarterstaff (precise strike)"]["mode_key"] == "effect:attack-mode:melee:precise-strike"
    assert attacks_by_name["Quarterstaff (precise strike)"]["variant_label"] == "precise strike"
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["damage"] == "1d8+1d6+3 bludgeoning"
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["mode_key"] == (
        "effect:attack-mode:melee:precise-strike|weapon:two-handed"
    )
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["variant_label"] == (
        "precise strike, two-handed"
    )
def test_normalize_definition_to_native_model_adds_psionic_power_helper_rows_and_trackers():
    definition = _minimal_character_definition("cerin-psi", "Cerin Psi")
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Fighter",
            "subclass_name": "Psi Warrior",
            "level": 3,
        }
    ]
    definition.features = [
        {
            "id": "psionic-power-1",
            "name": "Psionic Power",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "class_row_id": "class-row-1",
            "systems_ref": {
                "entry_type": "subclassfeature",
                "slug": "tce-subclassfeature-psionic-power",
                "title": "Psionic Power",
                "source_id": "TCE",
            },
            "page_ref": "mechanics/psi-warrior/psionic-power",
        }
    ]

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Psionic Power"]["tracker_ref"] == "psionic-power-psionic-energy"
    assert features_by_name["Psionic Power"]["class_row_id"] == "class-row-1"
    assert features_by_name["Psionic Power: Protective Field"]["activation_type"] == "reaction"
    assert features_by_name["Psionic Power: Psionic Strike"]["activation_type"] == "special"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["activation_type"] == "action"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["tracker_ref"] == "psionic-power-telekinetic-movement"
    assert features_by_name["Psionic Power: Recovery"]["activation_type"] == "bonus_action"
    assert features_by_name["Psionic Power: Recovery"]["tracker_ref"] == "psionic-power-recovery"
    assert features_by_name["Psionic Power: Protective Field"]["class_row_id"] == "class-row-1"
    assert features_by_name["Psionic Power: Recovery"]["systems_ref"]["slug"] == "tce-subclassfeature-psionic-power"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["page_ref"] == "mechanics/psi-warrior/psionic-power"
    assert resources_by_id["psionic-power-psionic-energy"]["class_row_id"] == "class-row-1"
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 4
    assert resources_by_id["psionic-power-psionic-energy"]["reset_on"] == "long_rest"
    assert resources_by_id["psionic-power-telekinetic-movement"]["class_row_id"] == "class-row-1"
    assert resources_by_id["psionic-power-telekinetic-movement"]["max"] == 1
    assert resources_by_id["psionic-power-telekinetic-movement"]["reset_on"] == "short_rest"
    assert resources_by_id["psionic-power-recovery"]["class_row_id"] == "class-row-1"
    assert resources_by_id["psionic-power-recovery"]["max"] == 1
    assert resources_by_id["psionic-power-recovery"]["reset_on"] == "short_rest"
def test_level_one_builder_applies_structured_carrying_capacity_effect_keys():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    mighty_frame = _systems_entry(
        "classfeature",
        "phb-classfeature-mighty-frame",
        "Mighty Frame",
        metadata={
            "level": 1,
            "campaign_option": {
                "mechanic_effects": [
                    {
                        "kind": "stat_adjustment",
                        "key": "carrying-capacity-multiplier:2",
                    }
                ],
            },
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                    {"label": "Mighty Frame", "entry": mighty_frame, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Loadbearer",
        "character_slug": "loadbearer",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(systems_service, "linden-pass", form_values),
        form_values,
    )

    assert definition.stats["carrying_capacity"] == 480
    assert definition.stats["push_drag_lift"] == 960
def test_level_one_builder_generates_attack_rows_from_starting_weapons():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"a": ["longsword|phb", "shield|phb"], "b": ["battleaxe|phb", "shield|phb"]},
                    {"_": ["light crossbow|phb", "crossbow bolts (20)|phb"]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        body={"entries": [{"name": "Feature: Adaptable", "entries": ["You fit in almost anywhere."]}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        body={
            "entries": [
                {
                    "name": "Feature: Shelter of the Faithful",
                    "entries": ["You can find refuge among the faithful."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    fighting_style = _systems_entry("classfeature", "phb-classfeature-fighting-style", "Fighting Style", metadata={"level": 1})
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    battleaxe = _systems_entry("item", "phb-item-battleaxe", "Battleaxe", metadata={"weight": 4})
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})
    light_crossbow = _systems_entry("item", "phb-item-light-crossbow", "Light Crossbow", metadata={"weight": 5})
    crossbow_bolts = _systems_entry("item", "phb-item-crossbow-bolts-20", "Crossbow Bolts (20)", metadata={"weight": 1.5})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [longsword, battleaxe, shield, light_crossbow, crossbow_bolts],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "entry": fighting_style,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Archery", "slug": "phb-optionalfeature-archery"},
                                        {"label": "Defense", "slug": "phb-optionalfeature-defense"},
                                    ]
                                }
                            ]
                        },
                    },
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Hale Rowan",
        "character_slug": "hale-rowan",
        "alignment": "Lawful Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "class_option_1": "phb-optionalfeature-archery",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    form_values = {
        **base_form_values,
        "class_equipment_1": _field_value_for_label(context, "class_equipment_1", "Longsword"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    equipment_ids_by_name = {item["name"]: item["id"] for item in definition.equipment_catalog}

    assert "Longsword (+5, 1d8+3 slashing)" in context["preview"]["attacks"]
    assert "Light Crossbow (+5, 1d8+1 piercing)" in context["preview"]["attacks"]
    assert set(attacks_by_name) == {"Longsword", "Light Crossbow"}
    assert attacks_by_name["Longsword"]["category"] == "melee weapon"
    assert attacks_by_name["Longsword"]["damage"] == "1d8+3 slashing"
    assert attacks_by_name["Longsword"]["notes"] == "Versatile (1d10)."
    assert attacks_by_name["Longsword"]["systems_ref"]["slug"] == "phb-item-longsword"
    assert attacks_by_name["Longsword"]["equipment_refs"] == [equipment_ids_by_name["Longsword"]]
    assert attacks_by_name["Light Crossbow"]["category"] == "ranged weapon"
    assert attacks_by_name["Light Crossbow"]["attack_bonus"] == 5
    assert attacks_by_name["Light Crossbow"]["damage"] == "1d8+1 piercing"
    assert attacks_by_name["Light Crossbow"]["notes"] == "Ammunition, loading, range 80/320."
    assert attacks_by_name["Light Crossbow"]["systems_ref"]["slug"] == "phb-item-light-crossbow"
    assert attacks_by_name["Light Crossbow"]["equipment_refs"] == [equipment_ids_by_name["Light Crossbow"]]
def test_level_one_builder_applies_magic_weapon_variant_bonus_from_item_title():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["+1 light crossbow|dmg"]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    magic_crossbow = _systems_entry(
        "item",
        "dmg-item-plus-one-light-crossbow",
        "+1 Light Crossbow",
        source_id="DMG",
        metadata={"weight": 5, "base_item": "Light Crossbow|PHB"},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "optionalfeature": [],
            "item": [magic_crossbow],
            "spell": [],
        },
        class_progression=[],
    )
    form_values = {
        "name": "Hale Rowan",
        "character_slug": "hale-rowan",
        "alignment": "Lawful Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    equipment_by_name = {item["name"]: item for item in definition.equipment_catalog}

    assert context["preview"]["attacks"] == ["+1 Light Crossbow (+4, 1d8+2 piercing)"]
    assert attacks_by_name["+1 Light Crossbow"]["attack_bonus"] == 4
    assert attacks_by_name["+1 Light Crossbow"]["damage"] == "1d8+2 piercing"
    assert attacks_by_name["+1 Light Crossbow"]["systems_ref"]["slug"] == "dmg-item-plus-one-light-crossbow"
    assert equipment_by_name["+1 Light Crossbow"]["is_equipped"] is True
def test_level_one_builder_derives_armor_class_from_starting_armor_and_shield():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["chain mail|phb", "shield|phb"]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    chain_mail = _systems_entry(
        "item",
        "phb-item-chain-mail",
        "Chain Mail",
        metadata={"type": "HA", "ac": 16, "armor": True, "strength": "13", "stealth_disadvantage": True},
    )
    shield = _systems_entry(
        "item",
        "phb-item-shield",
        "Shield",
        metadata={"type": "S", "ac": 2},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "optionalfeature": [],
            "item": [chain_mail, shield],
            "spell": [],
        },
        class_progression=[],
    )
    form_values = {
        "name": "Ser Rowan",
        "character_slug": "ser-rowan",
        "alignment": "Lawful Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    assert definition.stats["armor_class"] == 18
def test_level_one_builder_applies_medium_armor_master_to_starting_medium_armor():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["scale mail|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    medium_armor_master = _systems_entry("feat", "phb-feat-medium-armor-master", "Medium Armor Master")
    scale_mail = _systems_entry(
        "item",
        "phb-item-scale-mail",
        "Scale Mail",
        metadata={"type": "MA", "ac": 14, "weight": 45, "armor": True, "stealth_disadvantage": True},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [medium_armor_master],
            "subclass": [],
            "item": [scale_mail],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Mara Vale",
        "character_slug": "mara-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": medium_armor_master.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "16",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    assert definition.stats["armor_class"] == 17
    defensive_state = dict(definition.stats.get("defensive_state") or {})
    assert dict(defensive_state.get("armor_state") or {}).get("stealth_disadvantage_suppressed") is True
def test_level_one_builder_applies_dueling_damage_bonus_to_one_handed_melee_weapon():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["longsword|phb", "shield|phb"]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        body={"entries": [{"name": "Feature: Adaptable", "entries": ["You fit in almost anywhere."]}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        body={
            "entries": [
                {
                    "name": "Feature: Shelter of the Faithful",
                    "entries": ["You can find refuge among the faithful."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    fighting_style = _systems_entry("classfeature", "phb-classfeature-fighting-style", "Fighting Style", metadata={"level": 1})
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [longsword, shield],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "entry": fighting_style,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Dueling", "slug": "phb-optionalfeature-dueling"},
                                        {"label": "Defense", "slug": "phb-optionalfeature-defense"},
                                    ]
                                }
                            ]
                        },
                    },
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Ser Rowan",
        "character_slug": "ser-rowan",
        "alignment": "Lawful Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "class_option_1": "phb-optionalfeature-dueling",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    assert context["preview"]["attacks"] == ["Longsword (+5, 1d8+5 slashing)"]
    assert definition.attacks[0]["name"] == "Longsword"
    assert definition.attacks[0]["damage"] == "1d8+5 slashing"
    assert definition.attacks[0]["notes"] == "Versatile (1d10)."
def test_level_one_builder_generates_off_hand_attack_and_two_weapon_fighting_damage():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": [{"item": "handaxe|phb", "quantity": 2}]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        body={"entries": [{"name": "Feature: Adaptable", "entries": ["You fit in almost anywhere."]}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        body={
            "entries": [
                {
                    "name": "Feature: Shelter of the Faithful",
                    "entries": ["You can find refuge among the faithful."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    fighting_style = _systems_entry("classfeature", "phb-classfeature-fighting-style", "Fighting Style", metadata={"level": 1})
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    handaxe = _systems_entry("item", "phb-item-handaxe", "Handaxe", metadata={"weight": 2})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [handaxe],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "entry": fighting_style,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {
                                            "label": "Two-Weapon Fighting",
                                            "slug": "phb-optionalfeature-two-weapon-fighting",
                                        },
                                        {"label": "Defense", "slug": "phb-optionalfeature-defense"},
                                    ]
                                }
                            ]
                        },
                    },
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Tamsin Vale",
        "character_slug": "tamsin-vale",
        "alignment": "Chaotic Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "acrobatics",
        "class_option_1": "phb-optionalfeature-two-weapon-fighting",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    handaxe_id = next(item["id"] for item in definition.equipment_catalog if item["name"] == "Handaxe")

    assert "Handaxe (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert "Handaxe (thrown) (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert "Handaxe (off-hand) (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert attacks_by_name["Handaxe"]["notes"] == ""
    assert attacks_by_name["Handaxe"]["equipment_refs"] == [handaxe_id]
    assert attacks_by_name["Handaxe (thrown)"]["category"] == "ranged weapon"
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
    assert attacks_by_name["Handaxe (thrown)"]["mode_key"] == "weapon:thrown"
    assert attacks_by_name["Handaxe (thrown)"]["variant_label"] == "thrown"
    assert attacks_by_name["Handaxe (thrown)"]["equipment_refs"] == [handaxe_id]
    assert attacks_by_name["Handaxe (off-hand)"]["damage"] == "1d6+3 slashing"
    assert attacks_by_name["Handaxe (off-hand)"]["notes"] == "range 20/60, Bonus action."
    assert attacks_by_name["Handaxe (off-hand)"]["mode_key"] == "weapon:off-hand"
    assert attacks_by_name["Handaxe (off-hand)"]["variant_label"] == "off-hand"
    assert attacks_by_name["Handaxe (off-hand)"]["equipment_refs"] == [handaxe_id]
def test_level_one_builder_generates_dual_wielder_off_hand_attack_for_non_light_weapons():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["longsword|phb", "longsword|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True}],
            "feats": [{"any": 1}],
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    dual_wielder = _systems_entry("feat", "phb-feat-dual-wielder", "Dual Wielder")
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [dual_wielder],
            "subclass": [],
            "item": [longsword],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Tamsin Vale",
        "character_slug": "tamsin-vale",
        "alignment": "Chaotic Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": dual_wielder.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "acrobatics",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Longsword (+5, 1d8+3 slashing)" in context["preview"]["attacks"]
    assert "Longsword (off-hand) (+5, 1d8 slashing)" in context["preview"]["attacks"]
    assert attacks_by_name["Longsword"]["notes"] == "Versatile (1d10)."
    assert attacks_by_name["Longsword (off-hand)"]["damage"] == "1d8 slashing"
    assert attacks_by_name["Longsword (off-hand)"]["notes"] == "Bonus action."
    assert attacks_by_name["Longsword (off-hand)"]["mode_key"] == "weapon:off-hand"
def test_level_one_builder_generates_phb_charger_bonus_attack_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["greatsword|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    charger = _systems_entry("feat", "phb-feat-charger", "Charger", source_id="PHB")
    greatsword = _systems_entry("item", "phb-item-greatsword", "Greatsword", metadata={"weight": 6})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [charger],
            "subclass": [],
            "item": [greatsword],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Brom Vale",
        "character_slug": "brom-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": charger.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Greatsword (charger) (+5, 2d6+8 slashing)" in context["preview"]["attacks"]
    assert attacks_by_name["Greatsword (charger)"]["notes"] == "Bonus action, Charger (after Dash, move 10 feet straight for +5 damage)."
    assert attacks_by_name["Greatsword (charger)"]["mode_key"] == "feat:phb-feat-charger"
    assert attacks_by_name["Greatsword (charger)"]["variant_label"] == "charger"
def test_level_one_builder_generates_xphb_charger_attack_profile():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["greatsword|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    charger = _systems_entry("feat", "xphb-feat-charger", "Charger", source_id="XPHB")
    greatsword = _systems_entry("item", "phb-item-greatsword", "Greatsword", metadata={"weight": 6})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [charger],
            "subclass": [],
            "item": [greatsword],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Nell Voss",
        "character_slug": "nell-voss",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": charger.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Greatsword (charger) (+5, 2d6+1d8+3 slashing)" in context["preview"]["attacks"]
    assert attacks_by_name["Greatsword (charger)"]["notes"] == "Charger (move 10 feet straight, +1d8 damage, once per turn)."
    assert attacks_by_name["Greatsword (charger)"]["mode_key"] == "feat:xphb-feat-charger"
    assert attacks_by_name["Greatsword (charger)"]["variant_label"] == "charger"
def test_level_one_builder_adds_phb_mounted_combatant_note_only_to_melee_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["handaxe|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    mounted_combatant = _systems_entry("feat", "phb-feat-mounted-combatant", "Mounted Combatant", source_id="PHB")
    handaxe = _systems_entry("item", "phb-item-handaxe", "Handaxe", metadata={"weight": 2})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [mounted_combatant],
            "subclass": [],
            "item": [handaxe],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Mira Vale",
        "character_slug": "mira-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": mounted_combatant.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Handaxe (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert "Handaxe (thrown) (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert (
        attacks_by_name["Handaxe"]["notes"]
        == "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)."
    )
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
def test_level_one_builder_surfaces_sentinel_attack_reminder_state():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["handaxe|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    sentinel = _systems_entry("feat", "phb-feat-sentinel", "Sentinel", source_id="PHB")
    handaxe = _systems_entry("item", "phb-item-handaxe", "Handaxe", metadata={"weight": 2})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [sentinel],
            "subclass": [],
            "item": [handaxe],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Holdfast Vale",
        "character_slug": "holdfast-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": sentinel.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    reminder_state = dict(definition.stats.get("attack_reminder_state") or {})
    sentinel_rule = next(rule for rule in list(reminder_state.get("rules") or []) if rule["title"] == "Sentinel")

    assert "Handaxe (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert dict(sentinel_rule["attack_scope"]) == {
        "label": "Melee weapon attacks",
        "categories": ["melee weapon"],
    }
def test_level_one_builder_applies_structured_attack_modes_to_firearm_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["pistol|dmg"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    deadeye_drill = _systems_entry(
        "classfeature",
        "phb-classfeature-deadeye-drill",
        "Deadeye Drill",
        metadata={
            "level": 1,
            "campaign_option": {
                "modeled_effects": [
                    "attack-mode:firearm:deadeye shot:-2:0:1d6",
                ]
            },
        },
    )
    gunner = _systems_entry(
        "feat",
        "tce-feat-gunner",
        "Gunner",
        source_id="TCE",
        metadata={"weapon_proficiencies": [{"firearms": True}], "ability": [{"dex": 1}]},
    )
    pistol = _systems_entry("item", "dmg-item-pistol", "Pistol", metadata={"weight": 3}, source_id="DMG")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [gunner],
            "subclass": [],
            "item": [pistol],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                    {"label": "Deadeye Drill", "entry": deadeye_drill, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Mira Flint",
        "character_slug": "mira-flint",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": gunner.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "14",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Pistol (+4, 1d10+2 piercing)" in context["preview"]["attacks"]
    assert "Pistol (deadeye shot) (+2, 1d10+1d6+2 piercing)" in context["preview"]["attacks"]
    assert attacks_by_name["Pistol (deadeye shot)"]["notes"] == (
        "Ammunition, range 30/90, Gunner (ignore loading, no adjacent disadvantage), "
        "Deadeye Shot (-2 attack, +1d6 damage)."
    )
    assert attacks_by_name["Pistol (deadeye shot)"]["mode_key"] == "effect:attack-mode:firearm:deadeye-shot"
    assert attacks_by_name["Pistol (deadeye shot)"]["variant_label"] == "deadeye shot"
def test_level_one_builder_applies_gunner_to_firearm_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["pistol|dmg"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    gunner = _systems_entry(
        "feat",
        "tce-feat-gunner",
        "Gunner",
        source_id="TCE",
        metadata={"weapon_proficiencies": [{"firearms": True}], "ability": [{"dex": 1}]},
    )
    pistol = _systems_entry("item", "dmg-item-pistol", "Pistol", metadata={"weight": 3}, source_id="DMG")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [gunner],
            "subclass": [],
            "item": [pistol],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Mira Flint",
        "character_slug": "mira-flint",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": gunner.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "14",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    pistol_attack = next(attack for attack in definition.attacks if attack["name"] == "Pistol")

    assert "Firearms" in definition.proficiencies["weapons"]
    assert "Pistol (+4, 1d10+2 piercing)" in context["preview"]["attacks"]
    assert pistol_attack["notes"] == "Ammunition, range 30/90, Gunner (ignore loading, no adjacent disadvantage)."
def test_level_one_builder_adds_tavern_brawler_unarmed_attack_and_improvised_proficiency():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    tavern_brawler = _systems_entry(
        "feat",
        "xphb-feat-tavern-brawler",
        "Tavern Brawler",
        source_id="XPHB",
        metadata={"weapon_proficiencies": [{"improvised": True}]},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [tavern_brawler],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Rook Dane",
        "character_slug": "rook-dane",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": tavern_brawler.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    unarmed_attack = next(attack for attack in definition.attacks if attack["name"] == "Unarmed Strike")

    assert "Improvised Weapons" in definition.proficiencies["weapons"]
    assert "Unarmed Strike (+5, 1d4+3 bludgeoning)" in context["preview"]["attacks"]
    assert unarmed_attack["notes"] == "Tavern Brawler enhanced unarmed strike."
def test_level_one_builder_adds_shield_master_helper_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["shield|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    shield_master = _systems_entry("feat", "phb-feat-shield-master", "Shield Master")
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [shield_master],
            "subclass": [],
            "item": [shield],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Shield Hero",
        "character_slug": "shield-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": shield_master.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    shield_id = next(item["id"] for item in definition.equipment_catalog if item["name"] == "Shield")
    shield_shove = next(attack for attack in definition.attacks if attack["name"] == "Shield Shove")
    defensive_state = dict(definition.stats.get("defensive_state") or {})
    shield_master_rule = next(rule for rule in list(defensive_state.get("rules") or []) if rule["title"] == "Shield Master")

    assert "Shield Shove (special action)" in context["preview"]["attacks"]
    assert shield_shove["attack_bonus"] is None
    assert shield_shove["damage"] == ""
    assert shield_shove["notes"] == "Bonus action after taking the Attack action; Shield Master shove within 5 feet."
    assert shield_shove["mode_key"] == "feat:phb-feat-shield-master:shove"
    assert shield_shove["equipment_refs"] == [shield_id]
    assert shield_master_rule["active"] is True
    assert shield_master_rule["effects"][0]["summary"].startswith("Add +2 to Dexterity saves")
def test_level_one_builder_adds_phb_grappler_helper_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}], "feats": [{"any": 1}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    grappler = _systems_entry("feat", "phb-feat-grappler", "Grappler")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [grappler],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    form_values = {
        "name": "Lockdown Hero",
        "character_slug": "lockdown-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "species_feat_1": grappler.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    grapple_helper = next(attack for attack in definition.attacks if attack["name"] == "Pin Grappled Creature")

    assert "Pin Grappled Creature (special action)" in context["preview"]["attacks"]
    assert grapple_helper["attack_bonus"] is None
    assert grapple_helper["damage"] == ""
    assert (
        grapple_helper["notes"]
        == "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends."
    )
    assert grapple_helper["mode_key"] == "feat:phb-feat-grappler:pin"
    assert "equipment_refs" not in grapple_helper
def test_level_one_builder_puts_great_weapon_fighting_note_on_versatile_two_handed_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["quarterstaff|phb"]},
                ]
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        body={"entries": [{"name": "Feature: Adaptable", "entries": ["You fit in almost anywhere."]}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        body={
            "entries": [
                {
                    "name": "Feature: Shelter of the Faithful",
                    "entries": ["You can find refuge among the faithful."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    fighting_style = _systems_entry("classfeature", "phb-classfeature-fighting-style", "Fighting Style", metadata={"level": 1})
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [quarterstaff],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "entry": fighting_style,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {
                                            "label": "Great Weapon Fighting",
                                            "slug": "phb-optionalfeature-great-weapon-fighting",
                                        },
                                        {"label": "Defense", "slug": "phb-optionalfeature-defense"},
                                    ]
                                }
                            ]
                        },
                    },
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Brom Hale",
        "character_slug": "brom-hale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "class_option_1": "phb-optionalfeature-great-weapon-fighting",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert context["preview"]["attacks"] == [
        "Quarterstaff (+5, 1d6+3 bludgeoning)",
        "Quarterstaff (two-handed) (+5, 1d8+3 bludgeoning)",
    ]
    assert attacks_by_name["Quarterstaff"]["notes"] == ""
    assert attacks_by_name["Quarterstaff (two-handed)"]["notes"] == "Great Weapon Fighting (reroll 1s and 2s)."
def test_native_level_up_applies_structured_carrying_capacity_effect_keys():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    mighty_frame = _systems_entry(
        "classfeature",
        "phb-classfeature-mighty-frame",
        "Mighty Frame",
        metadata={
            "level": 4,
            "campaign_option": {
                "mechanic_effects": [
                    {
                        "kind": "stat_adjustment",
                        "key": "carrying-capacity-multiplier:2",
                    }
                ],
            },
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Mighty Frame", "entry": mighty_frame, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("loadbearer-veteran", "Loadbearer Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    form_values = {"hp_gain": "8"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
        current_import_metadata=_minimal_import_metadata("loadbearer-veteran"),
    )

    assert leveled_definition.stats["carrying_capacity"] == 480
    assert leveled_definition.stats["push_drag_lift"] == 960
def test_native_level_up_adds_psionic_power_helper_rows_on_subclass_selection():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    psi_warrior = _systems_entry(
        "subclass",
        "tce-subclass-psi-warrior",
        "Psi Warrior",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
        source_id="TCE",
    )
    martial_archetype = _systems_entry(
        "classfeature",
        "phb-classfeature-martial-archetype",
        "Martial Archetype",
        metadata={"level": 3},
    )
    psionic_power = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-psionic-power",
        "Psionic Power",
        metadata={"level": 3, "class_name": "Fighter", "class_source": "PHB", "subclass_name": "Psi Warrior"},
        source_id="TCE",
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [psi_warrior],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    _progression_row("Martial Archetype", entry=martial_archetype, option_groups=[]),
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    _progression_row("Psionic Power", entry=psionic_power, option_groups=[]),
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("psi-vanguard", "Psi Vanguard")
    current_definition.profile["class_level_text"] = "Fighter 2"
    current_definition.profile["classes"][0]["row_id"] = "class-row-1"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(fighter)
    current_definition.profile["class_ref"] = _systems_ref(fighter)
    current_definition.stats["max_hp"] = 20

    form_values = {
        "hp_gain": "8",
        "subclass_slug": psi_warrior.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(current_definition),
        hp_delta=hp_delta,
    )

    features_by_name = {feature["name"]: feature for feature in leveled_definition.features}
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Psionic Power: Psionic Energy: 4 / 4 (Long Rest)" in level_up_context["preview"]["resources"]
    assert "Psionic Power: Telekinetic Movement: 1 / 1 (Short Rest)" in level_up_context["preview"]["resources"]
    assert "Psionic Power: Recovery: 1 / 1 (Short Rest)" in level_up_context["preview"]["resources"]
    assert leveled_definition.profile["subclass_ref"]["slug"] == psi_warrior.slug
    assert features_by_name["Psionic Power"]["tracker_ref"] == "psionic-power-psionic-energy"
    assert features_by_name["Psionic Power: Protective Field"]["activation_type"] == "reaction"
    assert features_by_name["Psionic Power: Psionic Strike"]["activation_type"] == "special"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["activation_type"] == "action"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["tracker_ref"] == "psionic-power-telekinetic-movement"
    assert features_by_name["Psionic Power: Recovery"]["activation_type"] == "bonus_action"
    assert features_by_name["Psionic Power: Recovery"]["tracker_ref"] == "psionic-power-recovery"
    assert features_by_name["Psionic Power"]["class_row_id"] == "class-row-1"
    assert features_by_name["Psionic Power: Recovery"]["class_row_id"] == "class-row-1"
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 4
    assert resources_by_id["psionic-power-psionic-energy"]["reset_on"] == "long_rest"
    assert resources_by_id["psionic-power-telekinetic-movement"]["max"] == 1
    assert resources_by_id["psionic-power-telekinetic-movement"]["reset_on"] == "short_rest"
    assert resources_by_id["psionic-power-recovery"]["max"] == 1
    assert resources_by_id["psionic-power-recovery"]["reset_on"] == "short_rest"
    assert merged_resources["psionic-power-psionic-energy"]["current"] == 4
    assert merged_resources["psionic-power-telekinetic-movement"]["current"] == 1
    assert merged_resources["psionic-power-recovery"]["current"] == 1
def test_native_level_up_refreshes_psionic_power_pool_and_preserves_spent_values():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    psi_warrior = _systems_entry(
        "subclass",
        "tce-subclass-psi-warrior",
        "Psi Warrior",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
        source_id="TCE",
    )
    psionic_power = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-psionic-power",
        "Psionic Power",
        metadata={"level": 3, "class_name": "Fighter", "class_source": "PHB", "subclass_name": "Psi Warrior"},
        source_id="TCE",
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [psi_warrior],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )

    current_definition = _minimal_character_definition("psi-veteran", "Psi Veteran")
    current_definition.profile["class_level_text"] = "Fighter 4"
    current_definition.profile["classes"][0]["row_id"] = "class-row-1"
    current_definition.profile["classes"][0]["level"] = 4
    current_definition.profile["classes"][0]["class_name"] = "Fighter"
    current_definition.profile["classes"][0]["subclass_name"] = "Psi Warrior"
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(fighter)
    current_definition.profile["classes"][0]["subclass_ref"] = _systems_ref(psi_warrior)
    current_definition.profile["class_ref"] = _systems_ref(fighter)
    current_definition.profile["subclass_ref"] = _systems_ref(psi_warrior)
    current_definition.stats["max_hp"] = 36
    current_definition.features = [
        {
            "id": "psionic-power-1",
            "name": "Psionic Power",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": "psionic-power-psionic-energy",
            "class_row_id": "class-row-1",
            "systems_ref": _systems_ref(psionic_power),
        },
        {
            "id": "psionic-power-1-protective-field",
            "name": "Psionic Power: Protective Field",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "reaction",
            "class_row_id": "class-row-1",
        },
        {
            "id": "psionic-power-1-psionic-strike",
            "name": "Psionic Power: Psionic Strike",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "special",
            "class_row_id": "class-row-1",
        },
        {
            "id": "psionic-power-1-telekinetic-movement",
            "name": "Psionic Power: Telekinetic Movement",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "action",
            "class_row_id": "class-row-1",
        },
        {
            "id": "psionic-power-1-recovery",
            "name": "Psionic Power: Recovery",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "class_row_id": "class-row-1",
        },
    ]
    current_definition.resource_templates = [
        {
            "id": "psionic-power-psionic-energy",
            "label": "Psionic Power: Psionic Energy",
            "category": "subclass_feature",
            "initial_current": 4,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Psionic Power",
            "display_order": 0,
            "class_row_id": "class-row-1",
        }
    ]

    form_values = {"hp_gain": "8"}
    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )

    state = build_initial_state(current_definition)
    state["resources"] = [
        {
            "id": "psionic-power-psionic-energy",
            "label": "Psionic Power: Psionic Energy",
            "category": "subclass_feature",
            "current": 1,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Psionic Power",
            "display_order": 0,
            "class_row_id": "class-row-1",
        }
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)

    features_by_name = {feature["name"]: feature for feature in leveled_definition.features}
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Psionic Power: Psionic Energy: 6 / 6 (Long Rest)" in level_up_context["preview"]["resources"]
    assert features_by_name["Psionic Power: Telekinetic Movement"]["tracker_ref"] == "psionic-power-telekinetic-movement"
    assert features_by_name["Psionic Power: Recovery"]["tracker_ref"] == "psionic-power-recovery"
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 6
    assert resources_by_id["psionic-power-telekinetic-movement"]["max"] == 1
    assert resources_by_id["psionic-power-recovery"]["max"] == 1
    assert merged_resources["psionic-power-psionic-energy"]["current"] == 1
    assert merged_resources["psionic-power-psionic-energy"]["max"] == 6
    assert merged_resources["psionic-power-telekinetic-movement"]["current"] == 1
    assert merged_resources["psionic-power-telekinetic-movement"]["max"] == 1
    assert merged_resources["psionic-power-recovery"]["current"] == 1
    assert merged_resources["psionic-power-recovery"]["max"] == 1
def test_native_level_up_keeps_psionic_power_scaling_bound_to_each_class_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"]},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    psi_warrior = _systems_entry(
        "subclass",
        "tce-subclass-psi-warrior",
        "Psi Warrior",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
        source_id="TCE",
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter, rogue],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [psi_warrior],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )
    _set_progressions(systems_service, class_by_slug={fighter.slug: [], rogue.slug: []})

    definition = _minimal_character_definition("psi-split", "Psi Split")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Fighter",
            "subclass_name": "Psi Warrior",
            "level": 4,
            "systems_ref": _systems_ref(fighter),
            "subclass_ref": _systems_ref(psi_warrior),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Rogue",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(rogue),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(fighter)
    definition.profile["subclass_ref"] = _systems_ref(psi_warrior)
    definition.profile["class_level_text"] = "Fighter 4 / Rogue 1"
    definition.stats["max_hp"] = 34
    definition.features = [
        {
            "id": "psionic-power-1",
            "name": "Psionic Power",
            "category": "subclass_feature",
            "source": "TCE",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": "psionic-power-psionic-energy",
            "class_row_id": "class-row-1",
        }
    ]
    definition.resource_templates = [
        {
            "id": "psionic-power-psionic-energy",
            "label": "Psionic Power: Psionic Energy",
            "category": "subclass_feature",
            "initial_current": 4,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Psionic Power",
            "display_order": 0,
            "class_row_id": "class-row-1",
        }
    ]

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-2",
            "hp_gain": "5",
        },
    )

    assert "Psionic Power: Psionic Energy: 4 / 4 (Long Rest)" in context["preview"]["resources"]

    leveled_definition, _, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        context,
        context["values"],
    )
    state = build_initial_state(definition)
    state["resources"] = [
        {
            "id": "psionic-power-psionic-energy",
            "label": "Psionic Power: Psionic Energy",
            "category": "subclass_feature",
            "current": 2,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Psionic Power",
            "display_order": 0,
            "class_row_id": "class-row-1",
        }
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert [row["level"] for row in leveled_definition.profile["classes"]] == [4, 2]
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 4
    assert merged_resources["psionic-power-psionic-energy"]["current"] == 2
    assert merged_resources["psionic-power-psionic-energy"]["max"] == 4
def test_managed_resource_registry_keeps_rogue_psionic_power_distinct_from_psi_warrior():
    definition = _managed_resource_definition(
        slug="tce-subclassfeature-psionicpower-rogue-phb-soulknife-tce-3",
        title="Psionic Power",
        category="subclass_feature",
        source_id="TCE",
        class_name="Rogue",
        class_slug="phb-class-rogue",
        class_level=5,
    )

    normalized = normalize_definition_to_native_model(definition)
    feature_names = {feature["name"] for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert "Psionic Power: Recovery" in feature_names
    assert "Psionic Power: Protective Field" not in feature_names
    assert "Psionic Power: Psionic Strike" not in feature_names
    assert "Psionic Power: Telekinetic Movement" not in feature_names
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 6
    assert resources_by_id["psionic-power-recovery"]["max"] == 1
def test_level_one_builder_applies_fighting_initiate_optionalfeature_choice_to_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["longsword|phb", "shield|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True, "anyStandard": 1}],
            "skill_proficiencies": [{"any": 1}],
            "feats": [{"any": 1}],
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    fighting_initiate = _systems_entry(
        "feat",
        "tce-feat-fighting-initiate",
        "Fighting Initiate",
        source_id="TCE",
        metadata={
            "optionalfeature_progression": [
                {"name": "Fighting Style", "featureType": ["FS:F"], "progression": {"*": 1}}
            ]
        },
    )
    dueling = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-dueling",
        "Dueling",
        metadata={"feature_type": ["FS:F"]},
    )
    defense = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-defense",
        "Defense",
        metadata={"feature_type": ["FS:F"]},
    )
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [fighting_initiate],
            "subclass": [],
            "optionalfeature": [dueling, defense],
            "item": [longsword, shield],
            "spell": [],
        },
        class_progression=[],
    )

    form_values = {
        "name": "Style Adept",
        "character_slug": "style-adept",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Elvish",
        "species_feat_1": fighting_initiate.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_optionalfeature_1_1")["label"] == "Fighting Initiate Fighting Style"
    form_values["feat_species_feat_1_optionalfeature_1_1"] = _field_value_for_label(
        context,
        "feat_species_feat_1_optionalfeature_1_1",
        "Dueling",
    )

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    feature_names = {feature["name"] for feature in definition.features}

    assert "Fighting Initiate" in context["preview"]["features"]
    assert "Dueling" in context["preview"]["features"]
    assert attacks_by_name["Longsword"]["damage"] == "1d8+5 slashing"
    assert {"Fighting Initiate", "Dueling"} <= feature_names
def test_level_one_builder_applies_martial_adept_tracker_and_attack_notes():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["longsword|phb", "shield|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True, "anyStandard": 1}],
            "skill_proficiencies": [{"any": 1}],
            "feats": [{"any": 1}],
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    martial_adept = _systems_entry(
        "feat",
        "phb-feat-martial-adept",
        "Martial Adept",
        metadata={
            "optionalfeature_progression": [
                {"name": "Maneuvers", "featureType": ["MV:B"], "progression": {"*": 2}}
            ]
        },
    )
    precision_attack = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-precision-attack",
        "Precision Attack",
        metadata={"feature_type": ["MV:B"]},
    )
    trip_attack = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-trip-attack",
        "Trip Attack",
        metadata={"feature_type": ["MV:B"]},
    )
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [martial_adept],
            "subclass": [],
            "optionalfeature": [precision_attack, trip_attack],
            "item": [longsword, shield],
            "spell": [],
        },
        class_progression=[],
    )

    form_values = {
        "name": "Maneuver Adept",
        "character_slug": "maneuver-adept",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Elvish",
        "species_feat_1": martial_adept.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_optionalfeature_1_1")["label"] == "Martial Adept Maneuvers 1"
    form_values.update(
        {
            "feat_species_feat_1_optionalfeature_1_1": _field_value_for_label(
                context,
                "feat_species_feat_1_optionalfeature_1_1",
                "Precision Attack",
            ),
            "feat_species_feat_1_optionalfeature_1_2": _field_value_for_label(
                context,
                "feat_species_feat_1_optionalfeature_1_2",
                "Trip Attack",
            ),
        }
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    feature_names = {feature["name"] for feature in definition.features}
    martial_adept_feature = next(feature for feature in definition.features if feature["name"] == "Martial Adept")
    martial_adept_resource = next(resource for resource in definition.resource_templates if resource["id"] == "martial-adept")

    assert "Martial Adept" in context["preview"]["features"]
    assert "Martial Adept: 1 / 1 (Short Rest)" in context["preview"]["resources"]
    assert {"Precision Attack", "Trip Attack"} <= feature_names
    assert attacks_by_name["Longsword"]["notes"] == "Versatile (1d10), Martial Adept maneuvers available."
    assert martial_adept_feature["tracker_ref"] == "martial-adept"
    assert martial_adept_resource["max"] == 1
    assert martial_adept_resource["reset_on"] == "short_rest"
def test_level_one_builder_adds_crossbow_expert_bonus_attack_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["hand crossbow|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True, "anyStandard": 1}],
            "skill_proficiencies": [{"any": 1}],
            "feats": [{"any": 1}],
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    crossbow_expert = _systems_entry("feat", "phb-feat-crossbow-expert", "Crossbow Expert")
    hand_crossbow = _systems_entry("item", "phb-item-hand-crossbow", "Hand Crossbow", metadata={"weight": 3})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [crossbow_expert],
            "subclass": [],
            "item": [hand_crossbow],
            "spell": [],
        },
        class_progression=[],
    )

    form_values = {
        "name": "Quickshot",
        "character_slug": "quickshot",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Elvish",
        "species_feat_1": crossbow_expert.slug,
        "str": "12",
        "dex": "16",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert attacks_by_name["Hand Crossbow"]["attack_bonus"] == 5
    assert attacks_by_name["Hand Crossbow"]["damage"] == "1d6+3 piercing"
    assert attacks_by_name["Hand Crossbow"]["notes"] == (
        "Ammunition, range 30/120, Crossbow Expert (ignore loading, no adjacent disadvantage)."
    )
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["attack_bonus"] == 5
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["damage"] == "1d6+3 piercing"
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["notes"] == (
        "Ammunition, range 30/120, Bonus action, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Crossbow Expert bonus attack."
    )
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["mode_key"] == "feat:phb-feat-crossbow-expert:bonus"
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["variant_label"] == "crossbow expert"
def test_level_one_builder_adds_polearm_master_attack_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"_": ["glaive|phb"]},
                ]
            },
        },
    )
    variant_human = _systems_entry(
        "race",
        "phb-race-variant-human",
        "Variant Human",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True, "anyStandard": 1}],
            "skill_proficiencies": [{"any": 1}],
            "feats": [{"any": 1}],
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    polearm_master = _systems_entry("feat", "phb-feat-polearm-master", "Polearm Master")
    glaive = _systems_entry("item", "phb-item-glaive", "Glaive", metadata={"weight": 6})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [polearm_master],
            "subclass": [],
            "item": [glaive],
            "spell": [],
        },
        class_progression=[],
    )

    form_values = {
        "name": "Polearm Hero",
        "character_slug": "polearm-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Elvish",
        "species_feat_1": polearm_master.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "11",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}

    assert "Polearm Master" in context["preview"]["features"]
    assert attacks_by_name["Glaive"]["attack_bonus"] == 5
    assert attacks_by_name["Glaive"]["damage"] == "1d10+3 slashing"
    assert attacks_by_name["Glaive"]["notes"] == (
        "Polearm Master (bonus attack, opportunity attack when creatures enter reach)."
    )
    assert attacks_by_name["Glaive (polearm master)"]["attack_bonus"] == 5
    assert attacks_by_name["Glaive (polearm master)"]["damage"] == "1d4+3 bludgeoning"
    assert attacks_by_name["Glaive (polearm master)"]["notes"] == "Bonus action, Polearm Master bonus attack."
    assert attacks_by_name["Glaive (polearm master)"]["mode_key"] == "feat:phb-feat-polearm-master:bonus"
    assert attacks_by_name["Glaive (polearm master)"]["variant_label"] == "polearm master"
def test_native_level_up_preserves_ranged_feat_attack_variants():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )

    current_definition = _minimal_character_definition("marksman", "Marksman")
    current_definition.profile["class_level_text"] = "Fighter 5"
    current_definition.profile["classes"][0]["level"] = 5
    current_definition.stats["max_hp"] = 44
    current_definition.stats["ability_scores"]["str"] = {"score": 12, "modifier": 1, "save_bonus": 4}
    current_definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Light Crossbow",
            "default_quantity": 1,
            "weight": "5 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-light-crossbow",
                "title": "Light Crossbow",
                "source_id": "PHB",
            },
        }
    ]
    current_definition.features = [
        {
            "id": "sharpshooter-1",
            "name": "Sharpshooter",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {"entry_type": "feat", "slug": "phb-feat-sharpshooter", "title": "Sharpshooter", "source_id": "PHB"},
        },
        {
            "id": "crossbow-expert-1",
            "name": "Crossbow Expert",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {"entry_type": "feat", "slug": "phb-feat-crossbow-expert", "title": "Crossbow Expert", "source_id": "PHB"},
        },
    ]

    form_values = {"hp_gain": "8"}
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}

    assert attacks_by_name["Light Crossbow"]["attack_bonus"] == 6
    assert attacks_by_name["Light Crossbow"]["damage"] == "1d8+3 piercing"
    assert attacks_by_name["Light Crossbow"]["notes"] == (
        "Ammunition, range 80/320, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage)."
    )
    assert "Ammunition, loading" not in attacks_by_name["Light Crossbow"]["notes"]
    assert attacks_by_name["Light Crossbow (sharpshooter)"]["attack_bonus"] == 1
    assert attacks_by_name["Light Crossbow (sharpshooter)"]["damage"] == "1d8+13 piercing"
    assert attacks_by_name["Light Crossbow (sharpshooter)"]["notes"] == (
        "Ammunition, range 80/320, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage), Sharpshooter (-5 attack, +10 damage)."
    )
    assert attacks_by_name["Light Crossbow (sharpshooter)"]["mode_key"] == "feat:phb-feat-sharpshooter"
def test_native_level_up_applies_structured_attack_modes_to_melee_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    precision_drill = _systems_entry(
        "classfeature",
        "phb-classfeature-precision-drill",
        "Precision Drill",
        metadata={
            "level": 4,
            "campaign_option": {
                "modeled_effects": [
                    "attack-mode:melee:precise strike:0:0:1d6",
                ]
            },
        },
    )
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4})
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [quarterstaff],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Precision Drill", "entry": precision_drill, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("precise-veteran", "Precise Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Quarterstaff",
            "default_quantity": 1,
            "weight": "4 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-quarterstaff",
                "title": "Quarterstaff",
                "source_id": "PHB",
            },
        }
    ]

    form_values = {"hp_gain": "8"}
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}

    assert attacks_by_name["Quarterstaff (precise strike)"]["damage"] == "1d6+1d6+3 bludgeoning"
    assert attacks_by_name["Quarterstaff (precise strike)"]["notes"] == "Precise Strike (+1d6 damage)."
    assert attacks_by_name["Quarterstaff (precise strike)"]["mode_key"] == "effect:attack-mode:melee:precise-strike"
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["damage"] == "1d8+1d6+3 bludgeoning"
    assert attacks_by_name["Quarterstaff (precise strike, two-handed)"]["mode_key"] == (
        "effect:attack-mode:melee:precise-strike|weapon:two-handed"
    )
def test_native_level_up_preserves_crossbow_expert_bonus_attack_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )

    current_definition = _minimal_character_definition("bolt-dancer", "Bolt Dancer")
    current_definition.profile["class_level_text"] = "Fighter 5"
    current_definition.profile["classes"][0]["level"] = 5
    current_definition.stats["max_hp"] = 44
    current_definition.stats["ability_scores"]["str"] = {"score": 12, "modifier": 1, "save_bonus": 4}
    current_definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Hand Crossbow",
            "default_quantity": 1,
            "weight": "3 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-hand-crossbow",
                "title": "Hand Crossbow",
                "source_id": "PHB",
            },
        }
    ]
    current_definition.features = [
        {
            "id": "sharpshooter-1",
            "name": "Sharpshooter",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {"entry_type": "feat", "slug": "phb-feat-sharpshooter", "title": "Sharpshooter", "source_id": "PHB"},
        },
        {
            "id": "crossbow-expert-1",
            "name": "Crossbow Expert",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {"entry_type": "feat", "slug": "phb-feat-crossbow-expert", "title": "Crossbow Expert", "source_id": "PHB"},
        },
    ]

    form_values = {"hp_gain": "8"}
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}

    assert attacks_by_name["Hand Crossbow"]["attack_bonus"] == 6
    assert attacks_by_name["Hand Crossbow"]["damage"] == "1d6+3 piercing"
    assert attacks_by_name["Hand Crossbow"]["notes"] == (
        "Ammunition, range 30/120, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage)."
    )
    assert attacks_by_name["Hand Crossbow (sharpshooter)"]["attack_bonus"] == 1
    assert attacks_by_name["Hand Crossbow (sharpshooter)"]["damage"] == "1d6+13 piercing"
    assert attacks_by_name["Hand Crossbow (sharpshooter)"]["notes"] == (
        "Ammunition, range 30/120, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage), Sharpshooter (-5 attack, +10 damage)."
    )
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["attack_bonus"] == 6
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["damage"] == "1d6+3 piercing"
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["notes"] == (
        "Ammunition, range 30/120, Bonus action, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage), Crossbow Expert bonus attack."
    )
    assert attacks_by_name["Hand Crossbow (crossbow expert, sharpshooter)"]["attack_bonus"] == 1
    assert attacks_by_name["Hand Crossbow (crossbow expert, sharpshooter)"]["damage"] == "1d6+13 piercing"
    assert attacks_by_name["Hand Crossbow (crossbow expert, sharpshooter)"]["notes"] == (
        "Ammunition, range 30/120, Bonus action, Crossbow Expert (ignore loading, no adjacent disadvantage), "
        "Sharpshooter (ignore cover, no long-range disadvantage), Crossbow Expert bonus attack, "
        "Sharpshooter (-5 attack, +10 damage)."
    )
    assert attacks_by_name["Hand Crossbow (crossbow expert)"]["mode_key"] == "feat:phb-feat-crossbow-expert:bonus"
    assert attacks_by_name["Hand Crossbow (crossbow expert, sharpshooter)"]["mode_key"] == (
        "feat:phb-feat-crossbow-expert:bonus|feat:phb-feat-sharpshooter"
    )
def test_native_level_up_preserves_polearm_master_attack_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )

    current_definition = _minimal_character_definition("reach-warden", "Reach Warden")
    current_definition.profile["class_level_text"] = "Fighter 5"
    current_definition.profile["classes"][0]["level"] = 5
    current_definition.stats["max_hp"] = 44
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Glaive",
            "default_quantity": 1,
            "weight": "6 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-glaive",
                "title": "Glaive",
                "source_id": "PHB",
            },
        }
    ]
    current_definition.features = [
        {
            "id": "polearm-master-1",
            "name": "Polearm Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-polearm-master",
                "title": "Polearm Master",
                "source_id": "PHB",
            },
        },
    ]

    form_values = {"hp_gain": "8"}
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}

    assert attacks_by_name["Glaive"]["attack_bonus"] == 6
    assert attacks_by_name["Glaive"]["damage"] == "1d10+3 slashing"
    assert attacks_by_name["Glaive"]["notes"] == (
        "Polearm Master (bonus attack, opportunity attack when creatures enter reach)."
    )
    assert attacks_by_name["Glaive (polearm master)"]["attack_bonus"] == 6
    assert attacks_by_name["Glaive (polearm master)"]["damage"] == "1d4+3 bludgeoning"
    assert attacks_by_name["Glaive (polearm master)"]["notes"] == "Bonus action, Polearm Master bonus attack."
    assert attacks_by_name["Glaive (polearm master)"]["mode_key"] == "feat:phb-feat-polearm-master:bonus"
def test_native_level_up_adds_shield_master_helper_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    shield_master = _systems_entry("feat", "phb-feat-shield-master", "Shield Master")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [shield_master],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("shield-veteran", "Shield Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.equipment_catalog = [
        {
            "id": "shield-1",
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        }
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": shield_master.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    shield_shove = next(attack for attack in leveled_definition.attacks if attack["name"] == "Shield Shove")

    assert "Shield Master" in level_up_context["preview"]["gained_features"]
    assert "Shield Shove (special action)" in level_up_context["preview"]["attacks"]
    assert shield_shove["attack_bonus"] is None
    assert shield_shove["damage"] == ""
    assert shield_shove["notes"] == "Bonus action after taking the Attack action; Shield Master shove within 5 feet."
    assert shield_shove["mode_key"] == "feat:phb-feat-shield-master:shove"
    assert shield_shove["equipment_refs"] == ["shield-1"]
def test_native_level_up_adds_campaign_grappler_helper_row():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/lockdown-discipline",
            "Lockdown Discipline",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Lockdown Discipline",
                    "modeled_effects": ["grappler-phb"],
                }
            },
        )
    ]

    current_definition = _minimal_character_definition("lockdown-veteran", "Lockdown Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
    }

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", "Lockdown Discipline")

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    lockdown_discipline = next(feature for feature in leveled_definition.features if feature["name"] == "Lockdown Discipline")
    grapple_helper = next(attack for attack in leveled_definition.attacks if attack["name"] == "Pin Grappled Creature")

    assert "Lockdown Discipline" in level_up_context["preview"]["gained_features"]
    assert "Pin Grappled Creature (special action)" in level_up_context["preview"]["attacks"]
    assert lockdown_discipline["page_ref"] == "mechanics/lockdown-discipline"
    assert grapple_helper["attack_bonus"] is None
    assert grapple_helper["damage"] == ""
    assert (
        grapple_helper["notes"]
        == "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends."
    )
    assert grapple_helper["mode_key"] == "feat:phb-feat-grappler:pin"
    assert "equipment_refs" not in grapple_helper
def test_native_level_up_adds_campaign_mounted_combatant_note_only_to_melee_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/cavalier-drill",
            "Cavalier Drill",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Cavalier Drill",
                    "modeled_effects": ["mounted-combatant-phb"],
                }
            },
        )
    ]

    current_definition = _minimal_character_definition("cavalier-veteran", "Cavalier Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "id": "handaxe-1",
            "name": "Handaxe",
            "default_quantity": 1,
            "weight": "2 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-handaxe",
                "title": "Handaxe",
                "source_id": "PHB",
            },
        }
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
    }

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", "Cavalier Drill")

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    cavalier_drill = next(feature for feature in leveled_definition.features if feature["name"] == "Cavalier Drill")
    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}

    assert "Cavalier Drill" in level_up_context["preview"]["gained_features"]
    assert cavalier_drill["page_ref"] == "mechanics/cavalier-drill"
    assert (
        attacks_by_name["Handaxe"]["notes"]
        == "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)."
    )
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
def test_native_level_up_surfaces_crusher_attack_reminder_state():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    crusher = _systems_entry("feat", "tce-feat-crusher", "Crusher", source_id="TCE")
    mace = _systems_entry("item", "phb-item-mace", "Mace", metadata={"weight": 4})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [crusher],
            "subclass": [],
            "item": [mace],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("crusher-veteran", "Crusher Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.proficiencies["weapons"] = ["Simple Weapons"]
    current_definition.equipment_catalog = [
        {
            "id": "mace-1",
            "name": "Mace",
            "default_quantity": 1,
            "weight": "4 lb.",
            "notes": "",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-mace",
                "title": "Mace",
                "source_id": "PHB",
            },
        }
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": crusher.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    reminder_state = dict(leveled_definition.stats.get("attack_reminder_state") or {})
    crusher_rule = next(rule for rule in list(reminder_state.get("rules") or []) if rule["title"] == "Crusher")

    assert "Crusher" in level_up_context["preview"]["gained_features"]
    assert dict(crusher_rule["attack_scope"]) == {
        "label": "Bludgeoning attacks",
        "damage_types": ["Bludgeoning"],
    }
def test_native_level_up_applies_medium_armor_master_to_equipped_medium_armor():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    medium_armor_master = _systems_entry("feat", "phb-feat-medium-armor-master", "Medium Armor Master")
    scale_mail = _systems_entry(
        "item",
        "phb-item-scale-mail",
        "Scale Mail",
        metadata={"type": "MA", "ac": 14, "weight": 45, "armor": True, "stealth_disadvantage": True},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [medium_armor_master],
            "subclass": [],
            "item": [scale_mail],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("mara-veteran", "Mara Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.stats["armor_class"] = 16
    current_definition.stats["ability_scores"]["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    current_definition.equipment_catalog = [
        {
            "id": "scale-mail-1",
            "name": "Scale Mail",
            "default_quantity": 1,
            "weight": "45 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-scale-mail",
                "title": "Scale Mail",
                "source_id": "PHB",
            },
        }
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": medium_armor_master.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )

    assert "Medium Armor Master" in level_up_context["preview"]["gained_features"]
    assert leveled_definition.stats["armor_class"] == 17
    defensive_state = dict(leveled_definition.stats.get("defensive_state") or {})
    assert dict(defensive_state.get("armor_state") or {}).get("stealth_disadvantage_suppressed") is True
def test_native_level_up_applies_fighting_initiate_optionalfeature_choice_to_attacks():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    fighting_initiate = _systems_entry(
        "feat",
        "tce-feat-fighting-initiate",
        "Fighting Initiate",
        source_id="TCE",
        metadata={
            "optionalfeature_progression": [
                {"name": "Fighting Style", "featureType": ["FS:F"], "progression": {"*": 1}}
            ]
        },
    )
    dueling = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-dueling",
        "Dueling",
        metadata={"feature_type": ["FS:F"]},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [fighting_initiate],
            "subclass": [],
            "optionalfeature": [dueling],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("style-warden", "Style Warden")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Longsword",
            "default_quantity": 1,
            "weight": "3 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-longsword",
                "title": "Longsword",
                "source_id": "PHB",
            },
        },
        {
            "name": "Shield",
            "default_quantity": 1,
            "weight": "6 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-shield",
                "title": "Shield",
                "source_id": "PHB",
            },
        },
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": fighting_initiate.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    assert _find_builder_field(level_up_context, "feat_levelup_feat_1_optionalfeature_1_1")["label"] == "Fighting Initiate Fighting Style"
    form_values["feat_levelup_feat_1_optionalfeature_1_1"] = _field_value_for_label(
        level_up_context,
        "feat_levelup_feat_1_optionalfeature_1_1",
        "Dueling",
    )

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}
    feature_names = {feature["name"] for feature in leveled_definition.features}

    assert "Fighting Initiate" in level_up_context["preview"]["gained_features"]
    assert "Dueling" in level_up_context["preview"]["gained_features"]
    assert attacks_by_name["Longsword"]["damage"] == "1d8+5 slashing"
    assert {"Fighting Initiate", "Dueling"} <= feature_names
def test_native_level_up_adds_martial_adept_resource_and_preserves_melee_feat_variants():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "heavy", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "history", "acrobatics"]}}],
            },
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 8},
    )
    martial_adept = _systems_entry(
        "feat",
        "phb-feat-martial-adept",
        "Martial Adept",
        metadata={
            "optionalfeature_progression": [
                {"name": "Maneuvers", "featureType": ["MV:B"], "progression": {"*": 2}}
            ]
        },
    )
    precision_attack = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-precision-attack",
        "Precision Attack",
        metadata={"feature_type": ["MV:B"]},
    )
    trip_attack = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-trip-attack",
        "Trip Attack",
        metadata={"feature_type": ["MV:B"]},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [martial_adept],
            "subclass": [],
            "optionalfeature": [precision_attack, trip_attack],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 8,
                "level_label": "Level 8",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    }
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("steel-warden", "Steel Warden")
    current_definition.profile["class_level_text"] = "Fighter 7"
    current_definition.profile["classes"][0]["level"] = 7
    current_definition.stats["max_hp"] = 60
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]
    current_definition.equipment_catalog = [
        {
            "name": "Greatsword",
            "default_quantity": 1,
            "weight": "6 lb.",
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-greatsword",
                "title": "Greatsword",
                "source_id": "PHB",
            },
        }
    ]
    current_definition.features = [
        {
            "id": "great-weapon-master-1",
            "name": "Great Weapon Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-great-weapon-master",
                "title": "Great Weapon Master",
                "source_id": "PHB",
            },
        },
        {
            "id": "savage-attacker-1",
            "name": "Savage Attacker",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-savage-attacker",
                "title": "Savage Attacker",
                "source_id": "PHB",
            },
        },
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": martial_adept.slug,
    }

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    assert _find_builder_field(level_up_context, "feat_levelup_feat_1_optionalfeature_1_1")["label"] == "Martial Adept Maneuvers 1"
    form_values.update(
        {
            "feat_levelup_feat_1_optionalfeature_1_1": _field_value_for_label(
                level_up_context,
                "feat_levelup_feat_1_optionalfeature_1_1",
                "Precision Attack",
            ),
            "feat_levelup_feat_1_optionalfeature_1_2": _field_value_for_label(
                level_up_context,
                "feat_levelup_feat_1_optionalfeature_1_2",
                "Trip Attack",
            ),
        }
    )
    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(current_definition),
        hp_delta=hp_delta,
    )

    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}
    feature_names = {feature["name"] for feature in leveled_definition.features}
    martial_adept_feature = next(feature for feature in leveled_definition.features if feature["name"] == "Martial Adept")
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    state_resources_by_id = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Martial Adept" in level_up_context["preview"]["gained_features"]
    assert "Precision Attack" in level_up_context["preview"]["gained_features"]
    assert "Trip Attack" in level_up_context["preview"]["gained_features"]
    assert "Martial Adept: 1 / 1 (Short Rest)" in level_up_context["preview"]["resources"]
    assert {"Precision Attack", "Trip Attack"} <= feature_names
    assert attacks_by_name["Greatsword"]["attack_bonus"] == 6
    assert attacks_by_name["Greatsword"]["damage"] == "2d6+3 slashing"
    assert attacks_by_name["Greatsword"]["notes"] == (
        "Great Weapon Master (bonus attack on crit or kill), Martial Adept maneuvers available, "
        "Savage Attacker (reroll damage once per turn)."
    )
    assert attacks_by_name["Greatsword (great weapon master)"]["attack_bonus"] == 1
    assert attacks_by_name["Greatsword (great weapon master)"]["damage"] == "2d6+13 slashing"
    assert attacks_by_name["Greatsword (great weapon master)"]["notes"] == (
        "Great Weapon Master (bonus attack on crit or kill), Martial Adept maneuvers available, "
        "Savage Attacker (reroll damage once per turn), Great Weapon Master (-5 attack, +10 damage)."
    )
    assert attacks_by_name["Greatsword (great weapon master)"]["mode_key"] == "feat:phb-feat-great-weapon-master"
    assert attacks_by_name["Greatsword (great weapon master)"]["variant_label"] == "great weapon master"
    assert martial_adept_feature["tracker_ref"] == "martial-adept"
    assert resources_by_id["martial-adept"]["max"] == 1
    assert resources_by_id["martial-adept"]["reset_on"] == "short_rest"
    assert state_resources_by_id["martial-adept"]["current"] == 1
    assert state_resources_by_id["martial-adept"]["max"] == 1
