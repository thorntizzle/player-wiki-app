from __future__ import annotations

from tests.helpers.character_builder_fakes import *  # noqa: F401,F403

def test_native_level_up_can_add_strict_martial_class_and_records_row_provenance():
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
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["dex", "int"],
            "multiclassing": {
                "requirements": {"dex": 13},
                "proficienciesGained": {
                    "armor": ["light"],
                    "tools": ["thieves' tools"],
                    "skills": [{"choose": {"count": 1, "from": ["stealth", "investigation"]}}],
                },
            },
        },
    )
    sneak_attack = _systems_entry("classfeature", "rogue-sneak-attack", "Sneak Attack")
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, rogue],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            fighter.slug: [],
            rogue.slug: [
                {"level": 1, "feature_rows": [_progression_row("Sneak Attack", entry=sneak_attack)]},
            ],
        },
    )
    definition = _minimal_character_definition("martial-multi", "Martial Multi")
    definition.stats["ability_scores"]["dex"] = {"score": 13, "modifier": 1, "save_bonus": 1}

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {
            "advancement_mode": "add_class",
            "new_class_slug": f"systems:{rogue.slug}",
            "multiclass_skill_1": "stealth",
            "hp_gain": "5",
        },
    )
    leveled_definition, _import_metadata, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        context,
        context["values"],
    )

    assert hp_delta == 5
    assert [row["row_id"] for row in leveled_definition.profile["classes"]] == ["class-row-1", "class-row-2"]
    assert leveled_definition.profile["class_level_text"] == "Fighter 1 / Rogue 1"
    assert leveled_definition.profile["classes"][1]["class_name"] == "Rogue"
    assert leveled_definition.profile["classes"][1]["level"] == 1
    assert "Light Armor" in leveled_definition.proficiencies["armor"]
    assert "Thieves' Tools" in leveled_definition.proficiencies["tools"]
    skills_by_name = {skill["name"]: skill for skill in leveled_definition.skills}
    assert skills_by_name["Stealth"]["proficiency_level"] == "proficient"
    assert any(feature.get("class_row_id") == "class-row-2" for feature in leveled_definition.features)
    latest_event = list((leveled_definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert latest_event["action"] == "add_class"
    assert latest_event["class_row_id"] == "class-row-2"
    assert latest_event["row_from_level"] == 0
    assert latest_event["row_to_level"] == 1
def test_native_level_up_blocks_add_class_when_multiclass_requirements_are_not_met():
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
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["dex", "int"],
            "multiclassing": {"requirements": {"dex": 13}},
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, rogue],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    _set_progressions(systems_service, class_by_slug={fighter.slug: [], rogue.slug: []})
    definition = _minimal_character_definition("blocked-multi", "Blocked Multi")

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {
            "advancement_mode": "add_class",
            "new_class_slug": f"systems:{rogue.slug}",
            "hp_gain": "5",
        },
    )

    with pytest.raises(Exception, match="requires Dexterity 13 before multiclassing"):
        build_native_level_up_character_definition(
            "linden-pass",
            definition,
            context,
            context["values"],
        )
def test_native_level_up_clears_stale_add_class_fields_after_switching_back_to_existing_row():
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
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["dex", "int"],
            "multiclassing": {
                "requirements": {"dex": 13},
                "proficienciesGained": {
                    "skills": [{"choose": {"count": 1, "from": ["stealth", "investigation"]}}],
                },
            },
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, rogue],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    _set_progressions(systems_service, class_by_slug={fighter.slug: [], rogue.slug: []})
    current_definition = _minimal_character_definition("mode-shift", "Mode Shift")
    current_definition.stats["ability_scores"]["dex"] = {"score": 13, "modifier": 1, "save_bonus": 1}

    add_class_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        {
            "advancement_mode": "add_class",
            "new_class_slug": f"systems:{rogue.slug}",
            "multiclass_skill_1": "stealth",
            "hp_gain": "5",
        },
    )
    shifted_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        {
            **add_class_context["values"],
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-1",
        },
    )

    assert "multiclass_skill_1" in _builder_field_names(add_class_context)
    assert "multiclass_skill_1" not in _builder_field_names(shifted_context)
    assert shifted_context["values"].get("new_class_slug", "") == ""
    assert shifted_context["values"].get("multiclass_skill_1", "") == ""
    assert shifted_context["values"].get("hp_gain", "") == "5"
    assert shifted_context["field_live_preview"]["advancement_mode"]["live_preview_regions"] == (
        "advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots"
    )
def test_native_level_up_advances_selected_multiclass_row_only():
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
    cunning_action = _systems_entry("classfeature", "rogue-cunning-action", "Cunning Action")
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, rogue],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            fighter.slug: [],
            rogue.slug: [
                {"level": 1, "feature_rows": []},
                {"level": 2, "feature_rows": [_progression_row("Cunning Action", entry=cunning_action)]},
            ],
        },
    )
    definition = _minimal_character_definition("fighter-rogue", "Fighter Rogue")
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], row_id="class-row-1", level=1),
        {
            "row_id": "class-row-2",
            "class_name": "Rogue",
            "subclass_name": "",
            "level": 1,
            "systems_ref": {
                "entry_key": rogue.entry_key,
                "entry_type": rogue.entry_type,
                "title": rogue.title,
                "slug": rogue.slug,
                "source_id": rogue.source_id,
            },
        },
    ]
    definition.profile["class_level_text"] = "Fighter 1 / Rogue 1"

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-2",
            "hp_gain": "4",
        },
    )
    leveled_definition, _import_metadata, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        context,
        context["values"],
    )

    assert hp_delta == 4
    assert [row["level"] for row in leveled_definition.profile["classes"]] == [1, 2]
    assert [row["row_id"] for row in leveled_definition.profile["classes"]] == ["class-row-1", "class-row-2"]
    assert any(feature["name"] == "Cunning Action" for feature in leveled_definition.features)
    latest_event = list((leveled_definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert latest_event["action"] == "advance_existing"
    assert latest_event["class_row_id"] == "class-row-2"
    assert latest_event["row_from_level"] == 1
    assert latest_event["row_to_level"] == 2
def test_native_level_up_keeps_multiclass_resource_scaling_bound_to_each_class_row():
    sorcerer = _systems_entry(
        "class",
        "phb-class-sorcerer",
        "Sorcerer",
        metadata={"hit_die": {"faces": 6}, "proficiency": ["con", "cha"]},
    )
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"]},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [sorcerer, rogue],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    _set_progressions(systems_service, class_by_slug={sorcerer.slug: [], rogue.slug: []})

    definition = _minimal_character_definition("spell-split", "Spell Split")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Sorcerer",
            "subclass_name": "",
            "level": 4,
            "systems_ref": _systems_ref(sorcerer),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Rogue",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(rogue),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(sorcerer)
    definition.profile["class_level_text"] = "Sorcerer 4 / Rogue 1"
    definition.stats["max_hp"] = 26
    definition.stats["ability_scores"]["cha"] = {"score": 16, "modifier": 3, "save_bonus": 6}
    definition.features = [
        {
            "id": "font-of-magic-1",
            "name": "Font of Magic",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": "sorcery-points",
            "class_row_id": "class-row-1",
            "systems_ref": {
                "entry_type": "classfeature",
                "slug": "phb-classfeature-font-of-magic",
                "title": "Font of Magic",
                "source_id": "PHB",
            },
        }
    ]
    definition.resource_templates = [
        {
            "id": "sorcery-points",
            "label": "Sorcery Points",
            "category": "class_feature",
            "initial_current": 4,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Sorcery Points",
            "display_order": 0,
        }
    ]

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-2",
            "hp_gain": "4",
        },
    )

    assert "Sorcery Points: 4 / 4 (Long Rest)" in context["preview"]["resources"]

    leveled_definition, _import_metadata, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        context,
        context["values"],
    )
    state = build_initial_state(definition)
    state["resources"] = [
        {
            "id": "sorcery-points",
            "label": "Sorcery Points",
            "category": "class_feature",
            "current": 2,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Sorcery Points",
            "display_order": 0,
        }
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert [row["level"] for row in leveled_definition.profile["classes"]] == [4, 2]
    assert resources_by_id["sorcery-points"]["max"] == 4
    assert merged_resources["sorcery-points"]["current"] == 2
    assert merged_resources["sorcery-points"]["max"] == 4
def test_imported_level_up_preserves_imported_source_and_records_native_progression():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[{"level": 2, "feature_rows": [{"label": "Action Surge"}]}],
    )
    definition = _minimal_imported_character_definition()
    definition.profile["class_level_text"] = "Fighter 1"
    definition.profile["classes"][0]["level"] = 1
    definition.profile["classes"][0]["subclass_name"] = ""
    definition.profile["classes"][0].pop("subclass_ref", None)
    definition.profile.pop("subclass_ref", None)
    import_metadata = CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=definition.character_slug,
        source_path="imports://imported-hero.md",
        imported_at_utc="2026-03-31T00:00:00Z",
        parser_version="fixture",
        import_status="clean",
        warnings=[],
    )

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {"hp_gain": "6"},
    )
    leveled_definition, leveled_import, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        level_up_context,
        {"hp_gain": "6"},
        current_import_metadata=import_metadata,
    )

    history = list((leveled_definition.source.get("native_progression") or {}).get("history") or [])

    assert hp_gain == 6
    assert leveled_definition.source["source_type"] == "markdown_character_sheet"
    assert leveled_definition.profile["class_level_text"] == "Fighter 2"
    assert leveled_import.source_path == "imports://imported-hero.md"
    assert history[-1]["kind"] == "level_up"
    assert history[-1]["from_level"] == 1
    assert history[-1]["to_level"] == 2
    assert history[-1]["hp_gain"] == 6
    assert leveled_definition.source["native_progression"]["hp_baseline"] == {"level": 1, "max_hp": 12}
def test_native_level_up_records_hp_gain_and_keeps_hp_baseline():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}},
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
        },
        class_progression=[{"level": 2, "feature_rows": []}],
    )
    definition = _minimal_character_definition()
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {"hp_gain": "6"},
    )

    leveled_definition, _leveled_import, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        level_up_context,
        {"hp_gain": "6"},
    )

    history = list((leveled_definition.source.get("native_progression") or {}).get("history") or [])

    assert hp_gain == 6
    assert leveled_definition.stats["max_hp"] == 18
    assert leveled_definition.source["native_progression"]["hp_baseline"] == {"level": 1, "max_hp": 12}
    assert history[-1]["kind"] == "level_up"
    assert history[-1]["from_level"] == 1
    assert history[-1]["to_level"] == 2
    assert history[-1]["hp_gain"] == 6
def test_normalize_definition_to_native_model_consumes_structured_mechanic_effects_without_legacy_keys():
    dagger = _systems_entry("item", "phb-item-dagger", "Dagger", metadata={"weight": 1})
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"level": 1})
    definition = _minimal_character_definition("structured-initiate", "Structured Initiate")
    mechanic_effects = [
        {
            "kind": "resource_template",
            "resource": {
                "label": "Arcane Charge",
                "max": 2,
                "reset_on": "long_rest",
            },
        },
        {
            "kind": "ability_minimum",
            "ability": "int",
            "minimum": 14,
        },
        {
            "kind": "spell_grant",
            "spell": "Shield",
            "mark": "Known",
            "always_prepared": True,
        },
        {
            "kind": "attack_bonus",
            "bonus": 1,
            "target": "weapon_attacks",
        },
        {
            "kind": "damage_bonus",
            "bonus": 2,
            "target": "weapon_attacks",
        },
        {
            "kind": "ac_bonus",
            "bonus": 1,
        },
        {
            "kind": "attack_reminder",
            "id": "feature:arcane-ricochet",
            "title": "Arcane Ricochet",
            "condition": "After a weapon hit.",
            "attack_scope": {"categories": ["melee weapon"]},
            "effects": [
                {
                    "kind": "forced_movement",
                    "label": "Ricochet",
                    "summary": "Push the target 5 feet.",
                }
            ],
        },
        {
            "kind": "defensive_rule",
            "id": "feature:arcane-guard",
            "title": "Arcane Guard",
            "condition": "While conscious.",
            "effects": [
                {
                    "kind": "armor_class",
                    "label": "Guard",
                    "summary": "You gain a flickering ward.",
                }
            ],
        },
    ]
    definition.features = [
        {
            "id": "structured-arcana-1",
            "name": "Structured Arcana",
            "category": "class_feature",
            "source": "CUSTOM",
            "description_markdown": "",
            "activation_type": "passive",
            "campaign_option": {
                "kind": "feature",
                "name": "Structured Arcana",
                "mechanic_effects": mechanic_effects,
            },
        }
    ]
    definition.proficiencies["weapons"] = ["Simple Weapons"]
    definition.equipment_catalog = [
        {
            "id": "dagger-1",
            "name": "Dagger",
            "default_quantity": 1,
            "weight": "1 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": _systems_ref(dagger),
        }
    ]

    assert all("legacy_key" not in row for row in mechanic_effects)

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=_build_item_catalog([dagger]),
        spell_catalog=_build_spell_catalog([shield]),
    )
    attacks_by_name = {attack["name"]: attack for attack in normalized.attacks}
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}
    resources_by_label = {resource["label"]: resource for resource in normalized.resource_templates}
    reminder_rules = {
        rule["title"]: rule
        for rule in list(dict(normalized.stats.get("attack_reminder_state") or {}).get("rules") or [])
    }
    defensive_rules = {
        rule["title"]: rule
        for rule in list(dict(normalized.stats.get("defensive_state") or {}).get("rules") or [])
    }

    assert resources_by_label["Arcane Charge"]["max"] == 2
    assert resources_by_label["Arcane Charge"]["reset_on"] == "long_rest"
    assert normalized.stats["ability_scores"]["int"]["score"] == 14
    assert spells_by_name["Shield"]["is_always_prepared"] is True
    assert attacks_by_name["Dagger"]["attack_bonus"] == 6
    assert attacks_by_name["Dagger"]["damage"] == "1d4+5 piercing"
    assert normalized.stats["armor_class"] == 12
    assert reminder_rules["Arcane Ricochet"]["effects"][0]["summary"] == "Push the target 5 feet."
    assert defensive_rules["Arcane Guard"]["active"] is True
    assert defensive_rules["Arcane Guard"]["effects"][0]["summary"] == "You gain a flickering ward."
def test_normalize_definition_to_native_model_updates_bardic_inspiration_to_short_rest_at_level_five():
    definition = _minimal_character_definition("bard-hero", "Bard Hero")
    definition.profile["class_level_text"] = "Bard 5"
    definition.profile["classes"] = [{"class_name": "Bard", "subclass_name": "", "level": 5}]
    definition.profile["class_ref"] = None
    definition.features = [
        {
            "id": "bardic-inspiration",
            "name": "Bardic Inspiration",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "bonus_action",
        }
    ]
    definition.resource_templates = []
    definition.stats["ability_scores"]["cha"] = {"score": 16, "modifier": 3, "save_bonus": 3}

    normalized = normalize_definition_to_native_model(definition)
    tracker = next(resource for resource in normalized.resource_templates if resource["id"] == "bardic-inspiration")

    assert tracker["max"] == 3
    assert tracker["reset_on"] == "short_rest"
def test_normalize_definition_to_native_model_scales_multiclass_trackers_by_owning_class_row():
    bard = _systems_entry(
        "class",
        "phb-class-bard",
        "Bard",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "cha"]},
    )
    sorcerer = _systems_entry(
        "class",
        "phb-class-sorcerer",
        "Sorcerer",
        metadata={"hit_die": {"faces": 6}, "proficiency": ["con", "cha"]},
    )
    definition = _minimal_character_definition("lyra-split", "Lyra Split")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Bard",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(bard),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Sorcerer",
            "subclass_name": "",
            "level": 4,
            "systems_ref": _systems_ref(sorcerer),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(bard)
    definition.profile["class_level_text"] = "Bard 1 / Sorcerer 4"
    definition.stats["ability_scores"]["cha"] = {"score": 16, "modifier": 3, "save_bonus": 6}
    definition.features = [
        {
            "id": "bardic-inspiration-1",
            "name": "Bardic Inspiration",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "class_row_id": "class-row-1",
        },
        {
            "id": "font-of-magic-1",
            "name": "Font of Magic",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "class_row_id": "class-row-2",
        },
    ]
    definition.resource_templates = []

    normalized = normalize_definition_to_native_model(definition)
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert resources_by_id["bardic-inspiration"]["max"] == 3
    assert resources_by_id["bardic-inspiration"]["reset_on"] == "long_rest"
    assert resources_by_id["sorcery-points"]["max"] == 4
def test_normalize_definition_to_native_model_preserves_imported_expertise_and_updates_passives():
    definition = _minimal_imported_character_definition("selka-voss", "Selka Voss")
    definition.profile["class_level_text"] = "Rogue 5"
    definition.profile["classes"][0]["class_name"] = "Rogue"
    definition.profile["classes"][0]["level"] = 5
    definition.stats["proficiency_bonus"] = 2
    definition.stats["ability_scores"]["dex"] = {"score": 18, "modifier": 4, "save_bonus": 7}
    definition.stats["ability_scores"]["wis"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.skills = [
        {"name": "Perception", "bonus": 9, "proficiency_level": "expertise"},
        {"name": "Insight", "bonus": 6, "proficiency_level": "proficient"},
        {"name": "Animal Handling", "bonus": 6, "proficiency_level": "proficient"},
        {"name": "Sleight of Hand", "bonus": 10, "proficiency_level": "expertise"},
        {"name": "Investigation", "bonus": 0, "proficiency_level": "none"},
    ]

    normalized = normalize_definition_to_native_model(definition)
    skills_by_name = {skill["name"]: skill for skill in normalized.skills}

    assert normalized.stats["proficiency_bonus"] == 3
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Perception"]["bonus"] == 9
    assert skills_by_name["Insight"]["proficiency_level"] == "proficient"
    assert skills_by_name["Insight"]["bonus"] == 6
    assert skills_by_name["Animal Handling"]["proficiency_level"] == "proficient"
    assert skills_by_name["Animal Handling"]["bonus"] == 6
    assert skills_by_name["Sleight of Hand"]["proficiency_level"] == "expertise"
    assert skills_by_name["Sleight of Hand"]["bonus"] == 10
    assert normalized.stats["passive_perception"] == 19
    assert normalized.stats["passive_insight"] == 16
def test_normalize_definition_to_native_model_seeds_hp_baseline_and_preserves_imported_max_hp():
    definition = _minimal_imported_character_definition("brann-vale", "Brann Vale")
    definition.stats["max_hp"] = 27

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.stats["max_hp"] == 27
    assert normalized.source["native_progression"]["hp_baseline"] == {"level": 3, "max_hp": 27}
def test_normalize_definition_to_native_model_applies_structured_effect_keys_to_skills_passives_and_stats():
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    definition = _minimal_character_definition("keen-step", "Keen Step")
    definition.skills = [
        {"name": "Perception", "bonus": 1, "proficiency_level": "none"},
        {"name": "Insight", "bonus": 1, "proficiency_level": "none"},
        {"name": "Investigation", "bonus": 0, "proficiency_level": "none"},
    ]
    definition.features = [
        {
            "id": "battle-instinct-1",
            "name": "Battle Instinct",
            "category": "class_feature",
            "campaign_option": {
                "modeled_effects": [
                    "half-proficiency:skills:Investigation",
                    "skill-bonus:Perception:2",
                    "passive-bonus:Insight:3",
                    "initiative-bonus:2",
                    "speed-bonus:5",
                ]
            },
        }
    ]

    normalized = normalize_definition_to_native_model(
        definition,
        resolved_species=human,
    )
    skills_by_name = {skill["name"]: skill for skill in normalized.skills}

    assert skills_by_name["Perception"]["bonus"] == 3
    assert skills_by_name["Perception"]["proficiency_level"] == "none"
    assert skills_by_name["Insight"]["bonus"] == 1
    assert skills_by_name["Investigation"]["bonus"] == 1
    assert skills_by_name["Investigation"]["proficiency_level"] == "half_proficient"
    assert normalized.stats["passive_perception"] == 13
    assert normalized.stats["passive_insight"] == 14
    assert normalized.stats["passive_investigation"] == 11
    assert normalized.stats["initiative_bonus"] == 3
    assert normalized.stats["speed"] == "35 ft."
def test_normalize_definition_to_native_model_uses_source_locked_tce_species_resolution():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["con", "int"]},
        source_id="TCE",
    )
    phb_human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        source_id="PHB",
    )
    tce_human = _systems_entry(
        "race",
        "tce-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 35, "languages": [{"common": True}]},
        source_id="TCE",
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        source_id="PHB",
    )
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "race": [phb_human, tce_human],
            "background": [acolyte],
            "subclass": [],
            "spell": [],
        },
        class_progression=[],
        enabled_source_ids=["PHB", "TCE"],
    )
    definition = _minimal_imported_character_definition("source-locked", "Source Locked")
    definition.profile["class_level_text"] = "Artificer 1"
    definition.profile["classes"][0] = {
        "class_name": "Artificer",
        "subclass_name": "",
        "level": 1,
        "systems_ref": {
            "entry_key": "dnd-5e|class|tce|artificer",
            "entry_type": "class",
            "title": "Artificer",
            "slug": "stale-tce-class-artificer",
            "source_id": "TCE",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile.pop("subclass_ref", None)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|tce|human",
        "entry_type": "race",
        "title": "Human",
        "slug": "stale-tce-race-human",
        "source_id": "TCE",
    }
    definition.profile["background"] = "Acolyte"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|acolyte",
        "entry_type": "background",
        "title": "Acolyte",
        "slug": "phb-background-acolyte",
        "source_id": "PHB",
    }

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.stats["speed"] == "35 ft."
    assert normalized.spellcasting["spellcasting_class"] == "Artificer"
def test_normalize_definition_to_native_model_uses_source_locked_scag_species_resolution():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"]},
        source_id="PHB",
    )
    phb_human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        source_id="PHB",
    )
    scag_human = _systems_entry(
        "race",
        "scag-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 40, "languages": [{"common": True}]},
        source_id="SCAG",
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
        source_id="PHB",
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [phb_human, scag_human],
            "background": [acolyte],
            "subclass": [],
            "spell": [],
        },
        class_progression=[],
        enabled_source_ids=["PHB", "SCAG"],
    )
    definition = _minimal_imported_character_definition("scag-source-locked", "SCAG Source Locked")
    definition.profile["class_level_text"] = "Fighter 1"
    definition.profile["classes"][0] = {
        "class_name": "Fighter",
        "subclass_name": "",
        "level": 1,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|fighter",
            "entry_type": "class",
            "title": "Fighter",
            "slug": fighter.slug,
            "source_id": "PHB",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile.pop("subclass_ref", None)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|scag|human",
        "entry_type": "race",
        "title": "Human",
        "slug": "stale-scag-race-human",
        "source_id": "SCAG",
    }
    definition.profile["background"] = "Acolyte"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|acolyte",
        "entry_type": "background",
        "title": "Acolyte",
        "slug": acolyte.slug,
        "source_id": "PHB",
    }

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.stats["speed"] == "40 ft."
def test_normalize_definition_to_native_model_applies_structured_save_bonus_effect_keys_without_false_proficiency():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"proficiency": ["str", "con"]},
    )
    definition = _minimal_imported_character_definition("steadfast-hero", "Steadfast Hero")
    definition.features = [
        {
            "id": "steadfast-aura-1",
            "name": "Steadfast Aura",
            "category": "custom_feature",
            "campaign_option": {
                "modeled_effects": [
                    "save-bonus:all:2",
                    "save-bonus:abilities:wis,cha:1",
                    "save-bonus:abilities:foo:4",
                    "save-bonus:abilities:wis:not-a-number",
                    "save-bonus:other:3",
                ]
            },
        }
    ]

    normalized = normalize_definition_to_native_model(definition, resolved_class=fighter)
    renormalized = normalize_definition_to_native_model(normalized, resolved_class=fighter)

    assert normalized.stats["ability_scores"]["str"]["save_bonus"] == 7
    assert normalized.stats["ability_scores"]["dex"]["save_bonus"] == 3
    assert normalized.stats["ability_scores"]["con"]["save_bonus"] == 6
    assert normalized.stats["ability_scores"]["int"]["save_bonus"] == 2
    assert normalized.stats["ability_scores"]["wis"]["save_bonus"] == 4
    assert normalized.stats["ability_scores"]["cha"]["save_bonus"] == 2
    assert renormalized.stats["ability_scores"]["dex"]["save_bonus"] == 3
    assert renormalized.stats["ability_scores"]["wis"]["save_bonus"] == 4
def test_normalize_definition_to_native_model_maps_title_effects_through_shared_effect_keys():
    definition = _minimal_character_definition("selise-wynn", "Selise Wynn")
    definition.skills = [
        {"name": "Perception", "bonus": 1, "proficiency_level": "none"},
        {"name": "Insight", "bonus": 1, "proficiency_level": "none"},
        {"name": "Investigation", "bonus": 0, "proficiency_level": "none"},
    ]
    definition.features = [
        {"id": "joat-1", "name": "Jack of All Trades", "category": "class_feature"},
        {"id": "observant-1", "name": "Observant", "category": "feat"},
    ]

    normalized = normalize_definition_to_native_model(definition)
    skills_by_name = {skill["name"]: skill for skill in normalized.skills}

    assert skills_by_name["Perception"]["proficiency_level"] == "half_proficient"
    assert skills_by_name["Perception"]["bonus"] == 2
    assert skills_by_name["Insight"]["proficiency_level"] == "half_proficient"
    assert skills_by_name["Investigation"]["proficiency_level"] == "half_proficient"
    assert normalized.stats["initiative_bonus"] == 2
    assert normalized.stats["passive_perception"] == 17
    assert normalized.stats["passive_investigation"] == 16
def test_normalize_definition_to_native_model_adds_proficiency_bonus_feat_trackers():
    definition = _minimal_character_definition("mira-salt", "Mira Salt")
    definition.profile["class_level_text"] = "Fighter 5"
    definition.profile["classes"] = [{"class_name": "Fighter", "subclass_name": "", "level": 5}]
    definition.features = [
        {"id": "chef-1", "name": "Chef", "category": "feat", "source": "TCE", "description_markdown": ""},
        {"id": "poisoner-1", "name": "Poisoner", "category": "feat", "source": "TCE", "description_markdown": ""},
        {
            "id": "gift-metallic-dragon-1",
            "name": "Gift of the Metallic Dragon",
            "category": "feat",
            "source": "FTD",
            "description_markdown": "",
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Chef"]["tracker_ref"] == "chef-treats"
    assert features_by_name["Poisoner"]["tracker_ref"] == "poisoner-doses"
    assert features_by_name["Gift of the Metallic Dragon"]["tracker_ref"] == "protective-wings"
    assert resources_by_id["chef-treats"]["max"] == 3
    assert resources_by_id["chef-treats"]["reset_on"] == "long_rest"
    assert resources_by_id["poisoner-doses"]["max"] == 3
    assert resources_by_id["poisoner-doses"]["reset_on"] == "long_rest"
    assert resources_by_id["protective-wings"]["max"] == 3
    assert resources_by_id["protective-wings"]["reset_on"] == "long_rest"
def test_normalize_definition_to_native_model_adds_additional_modeled_feat_trackers():
    definition = _minimal_character_definition("arlen-voss", "Arlen Voss")
    definition.profile["class_level_text"] = "Wizard 5"
    definition.profile["classes"] = [{"class_name": "Wizard", "subclass_name": "", "level": 5}]
    definition.features = [
        {
            "id": "adept-red-robes-1",
            "name": "Adept of the Red Robes",
            "category": "feat",
            "source": "DSotDQ",
            "description_markdown": "",
        },
        {
            "id": "knight-crown-1",
            "name": "Knight of the Crown",
            "category": "feat",
            "source": "DSotDQ",
            "description_markdown": "",
        },
        {
            "id": "squire-solamnia-1",
            "name": "Squire of Solamnia",
            "category": "feat",
            "source": "DSotDQ",
            "description_markdown": "",
        },
        {
            "id": "boon-recovery-1",
            "name": "Boon of Recovery",
            "category": "feat",
            "source": "XPHB",
            "description_markdown": "",
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Adept of the Red Robes"]["tracker_ref"] == "magical-balance"
    assert features_by_name["Knight of the Crown"]["tracker_ref"] == "commanding-rally"
    assert features_by_name["Squire of Solamnia"]["tracker_ref"] == "precise-strike"
    assert features_by_name["Boon of Recovery"]["tracker_ref"] == "recover-vitality-dice"
    assert resources_by_id["magical-balance"]["max"] == 3
    assert resources_by_id["commanding-rally"]["max"] == 3
    assert resources_by_id["precise-strike"]["max"] == 3
    assert resources_by_id["recover-vitality-dice"]["max"] == 10
    assert resources_by_id["recover-vitality-dice"]["reset_on"] == "long_rest"
def test_normalize_definition_to_native_model_adds_single_use_short_rest_feat_trackers():
    definition = _minimal_character_definition("kora-flint", "Kora Flint")
    definition.profile["class_level_text"] = "Fighter 5"
    definition.profile["classes"] = [{"class_name": "Fighter", "subclass_name": "", "level": 5}]
    definition.features = [
        {"id": "dragon-fear-1", "name": "Dragon Fear", "category": "feat", "source": "XGE", "description_markdown": ""},
        {"id": "orcish-fury-1", "name": "Orcish Fury", "category": "feat", "source": "XGE", "description_markdown": ""},
        {
            "id": "second-chance-1",
            "name": "Second Chance",
            "category": "feat",
            "source": "XGE",
            "description_markdown": "",
        },
    ]

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Dragon Fear"]["tracker_ref"] == "dragon-fear"
    assert features_by_name["Dragon Fear"]["activation_type"] == "special"
    assert features_by_name["Orcish Fury"]["tracker_ref"] == "orcish-fury"
    assert features_by_name["Orcish Fury"]["activation_type"] == "special"
    assert features_by_name["Second Chance"]["tracker_ref"] == "second-chance"
    assert features_by_name["Second Chance"]["activation_type"] == "reaction"
    assert resources_by_id["dragon-fear"]["max"] == 1
    assert resources_by_id["dragon-fear"]["reset_on"] == "short_rest"
    assert resources_by_id["orcish-fury"]["max"] == 1
    assert resources_by_id["orcish-fury"]["reset_on"] == "short_rest"
    assert resources_by_id["second-chance"]["max"] == 1
    assert resources_by_id["second-chance"]["reset_on"] == "short_rest"
def test_normalize_definition_to_native_model_adds_gift_of_the_chromatic_dragon_trackers():
    definition = _minimal_character_definition("vesper-drake", "Vesper Drake")
    definition.profile["class_level_text"] = "Fighter 5"
    definition.profile["classes"] = [{"class_name": "Fighter", "subclass_name": "", "level": 5}]
    definition.features = [
        {
            "id": "gift-chromatic-dragon-1",
            "name": "Gift of the Chromatic Dragon",
            "category": "feat",
            "source": "FTD",
            "description_markdown": "",
        }
    ]

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert not features_by_name["Gift of the Chromatic Dragon"].get("tracker_ref")
    assert (
        features_by_name["Gift of the Chromatic Dragon: Chromatic Infusion"]["tracker_ref"]
        == "chromatic-infusion"
    )
    assert (
        features_by_name["Gift of the Chromatic Dragon: Reactive Resistance"]["tracker_ref"]
        == "reactive-resistance"
    )
    assert features_by_name["Gift of the Chromatic Dragon: Chromatic Infusion"]["activation_type"] == "bonus_action"
    assert features_by_name["Gift of the Chromatic Dragon: Reactive Resistance"]["activation_type"] == "reaction"
    assert resources_by_id["chromatic-infusion"]["max"] == 1
    assert resources_by_id["chromatic-infusion"]["reset_on"] == "long_rest"
    assert resources_by_id["reactive-resistance"]["max"] == 3
    assert resources_by_id["reactive-resistance"]["reset_on"] == "long_rest"
def test_normalize_definition_to_native_model_adds_chronal_shift_tracker():
    definition = _minimal_character_definition("nadi-tempo", "Nadi Tempo")
    definition.profile["class_level_text"] = "Wizard 2"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "Chronurgy Magic",
            "level": 2,
        }
    ]
    definition.profile["class_ref"] = None
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

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Chronal Shift"]["tracker_ref"] == "chronal-shift"
    assert features_by_name["Chronal Shift"]["activation_type"] == "reaction"
    assert resources_by_id["chronal-shift"]["class_row_id"] == "class-row-1"
    assert resources_by_id["chronal-shift"]["max"] == 2
    assert resources_by_id["chronal-shift"]["reset_on"] == "long_rest"
def test_native_level_up_advances_fighter_to_level_two_and_merges_state():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "subclass_title": "Martial Archetype",
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
    action_surge = _systems_entry("classfeature", "phb-classfeature-action-surge", "Action Surge", metadata={"level": 2})
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
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Action Surge", "entry": action_surge, "embedded_card": {"option_groups": []}},
                ],
            },
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

    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, form_values)
    assert supports_native_level_up(level_one_definition) is True

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        {"hp_gain": "8"},
    )
    leveled_definition, _, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_up_context,
        {"hp_gain": "8"},
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(level_one_definition),
        hp_delta=hp_gain,
    )

    feature_names = {feature["name"] for feature in leveled_definition.features}
    attacks_by_name = {attack["name"]: attack for attack in leveled_definition.attacks}
    resource_ids = {template["id"] for template in leveled_definition.resource_templates}

    assert leveled_definition.profile["class_level_text"] == "Fighter 2"
    assert leveled_definition.profile["classes"][0]["level"] == 2
    assert leveled_definition.stats["max_hp"] == level_one_definition.stats["max_hp"] + 8
    assert "Action Surge" in feature_names
    assert "action-surge" in resource_ids
    assert attacks_by_name["Longsword"]["damage"] == "1d8+5 slashing"
    assert merged_state["vitals"]["current_hp"] == leveled_definition.stats["max_hp"]
    assert {slot["level"]: slot["max"] for slot in merged_state["spell_slots"]} == {}
def test_native_level_up_preserves_manual_campaign_stat_adjustments():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "subclass_title": "Martial Archetype",
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
    action_surge = _systems_entry("classfeature", "phb-classfeature-action-surge", "Action Surge", metadata={"level": 2})
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
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Action Surge", "entry": action_surge, "embedded_card": {"option_groups": []}},
                ],
            },
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

    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, form_values)
    level_one_definition.stats = apply_manual_stat_adjustments(
        dict(level_one_definition.stats or {}),
        {
            "max_hp": 4,
            "armor_class": 1,
            "initiative_bonus": 2,
            "speed": 10,
            "passive_perception": 3,
            "passive_insight": -1,
            "passive_investigation": 2,
        },
    )

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        {"hp_gain": "8"},
    )
    leveled_definition, _, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_up_context,
        {"hp_gain": "8"},
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(level_one_definition),
        hp_delta=hp_gain,
    )

    assert leveled_definition.stats["manual_adjustments"] == {
        "max_hp": 4,
        "armor_class": 1,
        "initiative_bonus": 2,
        "speed": 10,
        "passive_perception": 3,
        "passive_insight": -1,
        "passive_investigation": 2,
    }
    assert leveled_definition.stats["max_hp"] == level_one_definition.stats["max_hp"] + 8
    assert leveled_definition.stats["armor_class"] == level_one_definition.stats["armor_class"]
    assert leveled_definition.stats["initiative_bonus"] == level_one_definition.stats["initiative_bonus"]
    assert leveled_definition.stats["speed"] == level_one_definition.stats["speed"]
    assert leveled_definition.stats["passive_perception"] == level_one_definition.stats["passive_perception"]
    assert leveled_definition.stats["passive_insight"] == level_one_definition.stats["passive_insight"]
    assert leveled_definition.stats["passive_investigation"] == level_one_definition.stats["passive_investigation"]
    assert merged_state["vitals"]["current_hp"] == leveled_definition.stats["max_hp"]
def test_native_level_up_preserves_structured_campaign_page_option_effects():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "subclass_title": "Martial Archetype",
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
    soldier = _systems_entry(
        "background",
        "phb-background-soldier",
        "Soldier",
        metadata={"skill_proficiencies": [{"athletics": True, "intimidation": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    action_surge = _systems_entry("classfeature", "phb-classfeature-action-surge", "Action Surge", metadata={"level": 2})
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"level": 0},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"level": 1, "ritual": True},
        source_page="231",
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [light, detect_magic],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Action Surge", "entry": action_surge, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/blessing-of-the-tide",
            "Blessing of the Tide",
            section="Mechanics",
            subsection="Blessings",
            summary="A tide-bound boon for trusted wardens.",
            metadata={
                "character_option": {
                    "name": "Blessing of the Tide",
                    "description_markdown": "Call on the tide to steady your footing.",
                    "activation_type": "bonus_action",
                    "resource": {"max": 3, "reset_on": "long_rest"},
                    "grants": {
                        "languages": ["Primordial"],
                        "tools": ["Navigator's Tools"],
                        "stat_adjustments": {
                            "initiative_bonus": 2,
                            "speed": 10,
                            "passive_perception": 3,
                        },
                        "spells": [
                            {"spell": "Light", "mark": "Granted"},
                            {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                        ],
                    },
                }
            },
        ),
        _campaign_page_record(
            "items/harbor-badge",
            "Harbor Badge",
            section="Items",
            summary="An issued badge for sworn harbor wardens.",
            metadata={
                "character_option": {
                    "quantity": 2,
                    "weight": "light",
                    "notes": "Issued by the Harbor Wardens.",
                    "grants": {
                        "armor": ["Light Armor"],
                        "stat_adjustments": {
                            "armor_class": 1,
                        },
                    },
                }
            },
        ),
    ]
    form_values = {
        "name": "Harbor Warden",
        "character_slug": "harbor-warden",
        "alignment": "Neutral Good",
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
        "wis": "12",
        "cha": "8",
    }

    level_one_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    level_one_form = {
        **form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(level_one_context, "campaign_feature_page_ref_1", "Blessing of the Tide"),
        "campaign_item_page_ref_1": _field_value_for_label(level_one_context, "campaign_item_page_ref_1", "Harbor Badge"),
    }
    level_one_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        level_one_form,
        campaign_page_records=campaign_page_records,
    )
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, level_one_form)

    blessing = next(feature for feature in level_one_definition.features if feature["name"] == "Blessing of the Tide")
    tracker_ref = str(blessing.get("tracker_ref") or "")

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        {"hp_gain": "8"},
    )
    leveled_definition, _, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_up_context,
        {"hp_gain": "8"},
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(level_one_definition),
        hp_delta=hp_gain,
    )

    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert leveled_definition.stats["max_hp"] == level_one_definition.stats["max_hp"] + 8
    assert leveled_definition.stats["initiative_bonus"] == level_one_definition.stats["initiative_bonus"]
    assert leveled_definition.stats["speed"] == level_one_definition.stats["speed"]
    assert leveled_definition.stats["armor_class"] == level_one_definition.stats["armor_class"]
    assert leveled_definition.stats["passive_perception"] == level_one_definition.stats["passive_perception"]
    assert "Primordial" in leveled_definition.proficiencies["languages"]
    assert "Navigator's Tools" in leveled_definition.proficiencies["tools"]
    assert "Light Armor" in leveled_definition.proficiencies["armor"]
    assert "Blessing of the Tide" in {feature["name"] for feature in leveled_definition.features}
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert tracker_ref in resources_by_id
    assert resources_by_id[tracker_ref]["max"] == 3
    assert merged_resources[tracker_ref]["current"] == 3
    assert merged_state["vitals"]["current_hp"] == leveled_definition.stats["max_hp"]
def test_native_level_up_advances_fighter_to_level_four_with_ability_score_improvement():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "subclass_title": "Martial Archetype",
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
    champion = _systems_entry(
        "subclass",
        "phb-subclass-fighter-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
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
    action_surge = _systems_entry("classfeature", "phb-classfeature-action-surge", "Action Surge", metadata={"level": 2})
    martial_archetype = _systems_entry("classfeature", "phb-classfeature-martial-archetype", "Martial Archetype", metadata={"level": 3})
    improved_critical = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-improved-critical",
        "Improved Critical",
        metadata={"level": 3, "class_name": "Fighter", "class_source": "PHB", "subclass_name": "Champion"},
    )
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword", metadata={"weight": 3})
    shield = _systems_entry("item", "phb-item-shield", "Shield", metadata={"weight": 6, "type": "S"})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [champion],
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
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Action Surge", "entry": action_surge, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Martial Archetype", "entry": martial_archetype, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Improved Critical", "entry": improved_critical, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
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

    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, base_form_values)

    level_two_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        {"hp_gain": "8"},
    )
    level_two_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_two_context,
        {"hp_gain": "8"},
    )

    level_three_form = {"hp_gain": "7", "subclass_slug": champion.slug}
    level_three_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_two_definition,
        level_three_form,
    )
    level_three_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        level_two_definition,
        level_three_context,
        level_three_form,
    )

    level_four_form = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "ability_scores",
        "levelup_asi_ability_1_1": "str",
        "levelup_asi_ability_1_2": "str",
    }
    level_four_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_three_definition,
        level_four_form,
    )
    level_four_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        level_three_definition,
        level_four_context,
        level_four_form,
    )

    attacks_by_name = {attack["name"]: attack for attack in level_four_definition.attacks}
    feature_names = {feature["name"] for feature in level_four_definition.features}

    assert level_four_context["preview"]["gained_features"] == ["Strength +2"]
    assert level_four_definition.profile["class_level_text"] == "Fighter 4"
    assert level_four_definition.profile["subclass_ref"]["slug"] == champion.slug
    assert level_four_definition.stats["ability_scores"]["str"]["score"] == 18
    assert level_four_definition.stats["ability_scores"]["str"]["modifier"] == 4
    assert attacks_by_name["Longsword"]["attack_bonus"] == 6
    assert attacks_by_name["Longsword"]["damage"] == "1d8+6 slashing"
    assert "Improved Critical" in feature_names
    assert "Ability Score Improvement" not in feature_names
def test_native_level_up_applies_resilient_feat_side_effects():
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
    resilient = _systems_entry(
        "feat",
        "phb-feat-resilient",
        "Resilient",
        metadata={
            "ability": [
                {
                    "choose": {
                        "from": ["str", "dex", "con", "int", "wis", "cha"],
                        "amount": 1,
                    }
                }
            ],
            "saving_throw_proficiencies": [
                {
                    "choose": {
                        "from": ["str", "dex", "con", "int", "wis", "cha"],
                    }
                }
            ],
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [resilient],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("resilient-hero", "Resilient Hero")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": resilient.slug,
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    assert _find_builder_field(context, "feat_levelup_feat_1_ability_1")["label"] == "Resilient Ability"
    form_values["feat_levelup_feat_1_ability_1"] = _field_value_for_label(
        context,
        "feat_levelup_feat_1_ability_1",
        "Dexterity",
    )

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    dexterity = leveled_definition.stats["ability_scores"]["dex"]
    feature_names = {feature["name"] for feature in leveled_definition.features}

    assert dexterity["score"] == 13
    assert dexterity["save_bonus"] == 3
    assert "Resilient" in feature_names
def test_native_level_up_applies_skill_expert_feat_expertise():
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
    skill_expert = _systems_entry(
        "feat",
        "tce-feat-skill-expert",
        "Skill Expert",
        source_id="TCE",
        metadata={
            "ability": [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"], "amount": 1}}],
            "skill_proficiencies": [
                {
                    "choose": {
                        "from": [
                            "athletics",
                            "acrobatics",
                            "sleight of hand",
                            "stealth",
                            "arcana",
                            "history",
                            "investigation",
                            "nature",
                            "religion",
                            "animal handling",
                            "insight",
                            "medicine",
                            "perception",
                            "survival",
                            "deception",
                            "intimidation",
                            "performance",
                            "persuasion",
                        ]
                    }
                }
            ],
            "expertise": [{"anyProficientSkill": 1}],
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [skill_expert],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("skill-expert-veteran", "Skill Expert Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.skills = [
        {"name": "Athletics", "bonus": 5, "proficiency_level": "proficient"},
        {"name": "History", "bonus": 2, "proficiency_level": "proficient"},
        {"name": "Insight", "bonus": 3, "proficiency_level": "proficient"},
        {"name": "Religion", "bonus": 2, "proficiency_level": "proficient"},
        {"name": "Perception", "bonus": 1, "proficiency_level": "none"},
    ]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": skill_expert.slug,
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    assert _find_builder_field(context, "feat_levelup_feat_1_expertise_1")["label"] == "Skill Expert Expertise"
    form_values.update(
        {
            "feat_levelup_feat_1_ability_1": _field_value_for_label(
                context,
                "feat_levelup_feat_1_ability_1",
                "Wisdom",
            ),
            "feat_levelup_feat_1_skills_1": _field_value_for_label(
                context,
                "feat_levelup_feat_1_skills_1",
                "Perception",
            ),
            "feat_levelup_feat_1_expertise_1": _field_value_for_label(
                context,
                "feat_levelup_feat_1_expertise_1",
                "Athletics",
            ),
        }
    )

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in leveled_definition.skills}
    feature_names = {feature["name"] for feature in leveled_definition.features}

    assert skills_by_name["Athletics"]["proficiency_level"] == "expertise"
    assert skills_by_name["Athletics"]["bonus"] == 7
    assert skills_by_name["Perception"]["proficiency_level"] == "proficient"
    assert leveled_definition.stats["ability_scores"]["wis"]["score"] == 14
    assert "Skill Expert" in feature_names
def test_native_level_up_surfaces_and_applies_rogue_expertise_class_feature():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"]},
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    expertise = _systems_entry(
        "classfeature",
        "phb-classfeature-expertise-rogue-phb-6",
        "Expertise",
        metadata={"class_name": "Rogue", "class_source": "PHB", "level": 6},
        body={
            "entries": [
                "At 6th level, you can choose two more of your proficiencies (in skills or with thieves' tools) to gain this benefit.",
            ]
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [rogue],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            rogue.slug: [
                {
                    "level": 6,
                    "level_label": "Level 6",
                    "feature_rows": [_progression_row("Expertise", entry=expertise)],
                }
            ]
        },
    )

    current_definition = _minimal_character_definition("rogue-veteran", "Rogue Veteran")
    current_definition.profile["class_level_text"] = "Rogue 5"
    current_definition.profile["classes"][0]["class_name"] = "Rogue"
    current_definition.profile["classes"][0]["level"] = 5
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(rogue)
    current_definition.profile["class_ref"] = _systems_ref(rogue)
    current_definition.profile["species_ref"] = _systems_ref(human)
    current_definition.profile["background_ref"] = _systems_ref(acolyte)
    current_definition.stats["proficiency_bonus"] = 3
    current_definition.skills = [
        {"name": "Acrobatics", "bonus": 4, "proficiency_level": "proficient"},
        {"name": "Investigation", "bonus": 3, "proficiency_level": "proficient"},
        {"name": "Perception", "bonus": 4, "proficiency_level": "proficient"},
        {"name": "Stealth", "bonus": 4, "proficiency_level": "proficient"},
    ]

    form_values = {"hp_gain": "5"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    first_expertise_field = _field_name_for_label(context, "Rogue Expertise 1")
    second_expertise_field = _field_name_for_label(context, "Rogue Expertise 2")
    form_values[first_expertise_field] = _field_value_for_label(context, first_expertise_field, "Perception")
    form_values[second_expertise_field] = _field_value_for_label(context, second_expertise_field, "Stealth")

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in leveled_definition.skills}
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Stealth"]["proficiency_level"] == "expertise"
    assert skills_by_name["Investigation"]["proficiency_level"] == "proficient"
def test_native_level_up_applies_rogue_expertise_to_thieves_tools():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"]},
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    expertise = _systems_entry(
        "classfeature",
        "phb-classfeature-expertise-rogue-phb-6",
        "Expertise",
        metadata={"class_name": "Rogue", "class_source": "PHB", "level": 6},
        body={
            "entries": [
                "At 6th level, you can choose two more of your proficiencies (in skills or with thieves' tools) to gain this benefit.",
            ]
        },
    )

    systems_service = _FakeSystemsService(
        {
            "class": [rogue],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            rogue.slug: [
                {
                    "level": 6,
                    "level_label": "Level 6",
                    "feature_rows": [_progression_row("Expertise", entry=expertise)],
                }
            ]
        },
    )

    current_definition = _minimal_character_definition("rogue-veteran", "Rogue Veteran")
    current_definition.profile["class_level_text"] = "Rogue 5"
    current_definition.profile["classes"][0]["class_name"] = "Rogue"
    current_definition.profile["classes"][0]["level"] = 5
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(rogue)
    current_definition.profile["class_ref"] = _systems_ref(rogue)
    current_definition.profile["species_ref"] = _systems_ref(human)
    current_definition.profile["background_ref"] = _systems_ref(acolyte)
    current_definition.stats["proficiency_bonus"] = 3
    current_definition.skills = [
        {"name": "Acrobatics", "bonus": 4, "proficiency_level": "proficient"},
        {"name": "Investigation", "bonus": 3, "proficiency_level": "proficient"},
        {"name": "Perception", "bonus": 4, "proficiency_level": "proficient"},
        {"name": "Stealth", "bonus": 4, "proficiency_level": "proficient"},
    ]
    current_definition.proficiencies["tools"] = ["Thieves' Tools"]

    form_values = {"hp_gain": "5"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    first_expertise_field = _field_name_for_label(context, "Rogue Expertise 1")
    second_expertise_field = _field_name_for_label(context, "Rogue Expertise 2")
    form_values[first_expertise_field] = _field_value_for_label(context, first_expertise_field, "Stealth")
    form_values[second_expertise_field] = _field_value_for_label(context, second_expertise_field, "Thieves' Tools")

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in leveled_definition.skills}
    assert skills_by_name["Stealth"]["proficiency_level"] == "expertise"
    assert any(tool.casefold() == "thieves' tools" for tool in leveled_definition.proficiencies["tools"])
    assert any(
        tool.casefold() == "thieves' tools"
        for tool in leveled_definition.proficiencies.get("tool_expertise") or []
    )
def test_native_level_up_applies_structured_save_bonus_effect_keys():
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
    battle_resilience = _systems_entry(
        "classfeature",
        "phb-classfeature-battle-resilience",
        "Battle Resilience",
        metadata={
            "level": 4,
            "campaign_option": {
                "modeled_effects": [
                    "save-bonus:all:2",
                    "save-bonus:abilities:wis,cha:1",
                ]
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
                    {"label": "Battle Resilience", "entry": battle_resilience, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("resolute-veteran", "Resolute Veteran")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    form_values = {"hp_gain": "8"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
        current_import_metadata=_minimal_import_metadata("resolute-veteran"),
    )

    assert leveled_definition.stats["ability_scores"]["str"]["save_bonus"] == 7
    assert leveled_definition.stats["ability_scores"]["dex"]["save_bonus"] == 3
    assert leveled_definition.stats["ability_scores"]["wis"]["save_bonus"] == 4
    assert leveled_definition.stats["ability_scores"]["cha"]["save_bonus"] == 2
def test_native_level_up_applies_page_backed_feat_grants():
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
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"level": 0})
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"level": 1, "ritual": True},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [light, detect_magic],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/tidecaller-gift",
            "Tidecaller Gift",
            section="Mechanics",
            subsection="Feats",
            summary="A storm-marked blessing drawn from harbor rites.",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Tidecaller Gift",
                    "description_markdown": "You can call a little of the tide to your side.",
                    "grants": {
                        "resource": {"label": "Tidecaller Gift", "max": 2, "reset_on": "long_rest"},
                        "stat_adjustments": {"max_hp": 4, "initiative_bonus": 1},
                        "tools": ["Navigator's Tools"],
                        "spells": [
                            {"spell": "Light", "mark": "Granted"},
                            {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                        ],
                    },
                }
            },
        )
    ]

    current_definition = _minimal_character_definition("tidecaller", "Tidecaller")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    initial_form = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
    }
    initial_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        initial_form,
        campaign_page_records=campaign_page_records,
    )
    feat_value = _field_value_for_label(initial_context, "levelup_feat_1", "Tidecaller Gift")
    assert feat_value.startswith("page:")

    form_values = {
        **initial_form,
        "levelup_feat_1": feat_value,
    }
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
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

    tidecaller = next(feature for feature in leveled_definition.features if feature["name"] == "Tidecaller Gift")
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Tidecaller Gift" in level_up_context["preview"]["gained_features"]
    assert any("Detect Magic" in spell_name for spell_name in level_up_context["preview"]["new_spells"])
    assert "Tidecaller Gift: 2 / 2 (Long Rest)" in level_up_context["preview"]["resources"]
    assert leveled_definition.stats["max_hp"] == current_definition.stats["max_hp"] + 8 + 4
    assert leveled_definition.stats["initiative_bonus"] == current_definition.stats["initiative_bonus"] + 1
    assert "Navigator's Tools" in leveled_definition.proficiencies["tools"]
    assert tidecaller["page_ref"] == "mechanics/tidecaller-gift"
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert resources_by_id[str(tidecaller.get("tracker_ref") or "")]["max"] == 2
    assert merged_resources[str(tidecaller.get("tracker_ref") or "")]["current"] == 2
def test_native_level_up_applies_tough_feat_hit_points_to_definition_and_state():
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
    tough = _systems_entry("feat", "phb-feat-tough", "Tough")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [tough],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("tough-hero", "Tough Hero")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 28

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": tough.slug,
    }

    leveled_definition, _, hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values),
        form_values,
    )
    merged_state = merge_state_with_definition(
        leveled_definition,
        build_initial_state(current_definition),
        hp_delta=hp_delta,
    )

    assert leveled_definition.stats["max_hp"] == 44
    assert hp_delta == 16
    assert merged_state["vitals"]["current_hp"] == 44
def test_native_level_up_refreshes_scaling_fighter_resource_templates():
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

    current_definition = _minimal_character_definition("fighter-ace", "Fighter Ace")
    current_definition.profile["class_level_text"] = "Fighter 16"
    current_definition.profile["classes"][0]["level"] = 16
    current_definition.stats["max_hp"] = 132
    current_definition.features = [
        {
            "id": "action-surge-1",
            "name": "Action Surge",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "special",
            "tracker_ref": "action-surge",
            "systems_ref": {"entry_type": "classfeature", "slug": "phb-classfeature-action-surge", "title": "Action Surge", "source_id": "PHB"},
        },
        {
            "id": "indomitable-1",
            "name": "Indomitable",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "special",
            "tracker_ref": "indomitable",
            "systems_ref": {"entry_type": "classfeature", "slug": "phb-classfeature-indomitable", "title": "Indomitable", "source_id": "PHB"},
        },
    ]
    current_definition.resource_templates = [
        {
            "id": "action-surge",
            "label": "Action Surge",
            "category": "class_feature",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Action Surge",
            "display_order": 0,
        },
        {
            "id": "indomitable",
            "label": "Indomitable",
            "category": "class_feature",
            "initial_current": 2,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Indomitable",
            "display_order": 1,
        },
    ]

    form_values = {"hp_gain": "9"}
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
            "id": "action-surge",
            "label": "Action Surge",
            "category": "class_feature",
            "current": 0,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Action Surge",
            "display_order": 0,
        },
        {
            "id": "indomitable",
            "label": "Indomitable",
            "category": "class_feature",
            "current": 1,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Indomitable",
            "display_order": 1,
        },
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert resources_by_id["action-surge"]["max"] == 2
    assert resources_by_id["indomitable"]["max"] == 3
    assert merged_resources["action-surge"]["current"] == 0
    assert merged_resources["action-surge"]["max"] == 2
    assert merged_resources["indomitable"]["current"] == 1
    assert merged_resources["indomitable"]["max"] == 3
def test_native_level_up_refreshes_gift_of_the_chromatic_dragon_reactive_resistance():
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

    current_definition = _minimal_character_definition("chromatic-veteran", "Chromatic Veteran")
    current_definition.profile["class_level_text"] = "Fighter 4"
    current_definition.profile["classes"][0]["level"] = 4
    current_definition.stats["max_hp"] = 36
    current_definition.features = [
        {
            "id": "gift-chromatic-dragon-1",
            "name": "Gift of the Chromatic Dragon",
            "category": "feat",
            "source": "FTD",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": {
                "entry_type": "feat",
                "slug": "ftd-feat-gift-of-the-chromatic-dragon",
                "title": "Gift of the Chromatic Dragon",
                "source_id": "FTD",
            },
        },
        {
            "id": "gift-chromatic-dragon-1-chromatic-infusion",
            "name": "Gift of the Chromatic Dragon: Chromatic Infusion",
            "category": "feat",
            "source": "FTD",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "tracker_ref": "chromatic-infusion",
        },
        {
            "id": "gift-chromatic-dragon-1-reactive-resistance",
            "name": "Gift of the Chromatic Dragon: Reactive Resistance",
            "category": "feat",
            "source": "FTD",
            "description_markdown": "",
            "activation_type": "reaction",
            "tracker_ref": "reactive-resistance",
        },
    ]
    current_definition.resource_templates = [
        {
            "id": "chromatic-infusion",
            "label": "Chromatic Infusion",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Chromatic Infusion",
            "display_order": 0,
        },
        {
            "id": "reactive-resistance",
            "label": "Reactive Resistance",
            "category": "feat",
            "initial_current": 2,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Reactive Resistance",
            "display_order": 1,
        },
    ]

    form_values = {"hp_gain": "9"}
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
            "id": "chromatic-infusion",
            "label": "Chromatic Infusion",
            "category": "feat",
            "current": 0,
            "max": 1,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Chromatic Infusion",
            "display_order": 0,
        },
        {
            "id": "reactive-resistance",
            "label": "Reactive Resistance",
            "category": "feat",
            "current": 1,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Reactive Resistance",
            "display_order": 1,
        },
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Chromatic Infusion: 1 / 1 (Long Rest)" in level_up_context["preview"]["resources"]
    assert "Reactive Resistance: 3 / 3 (Long Rest)" in level_up_context["preview"]["resources"]
    assert resources_by_id["chromatic-infusion"]["max"] == 1
    assert resources_by_id["reactive-resistance"]["max"] == 3
    assert merged_resources["chromatic-infusion"]["current"] == 0
    assert merged_resources["chromatic-infusion"]["max"] == 1
    assert merged_resources["reactive-resistance"]["current"] == 1
    assert merged_resources["reactive-resistance"]["max"] == 3
def test_native_level_up_refreshes_scaling_rage_resource():
    barbarian = _systems_entry(
        "class",
        "phb-class-barbarian",
        "Barbarian",
        metadata={
            "hit_die": {"faces": 12},
            "proficiency": ["str", "con"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple", "martial"],
                "skills": [{"choose": {"count": 2, "from": ["athletics", "nature", "survival"]}}],
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
            "class": [barbarian],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )

    current_definition = _minimal_character_definition("rage-heart", "Rage Heart")
    current_definition.profile["class_level_text"] = "Barbarian 2"
    current_definition.profile["classes"][0]["class_name"] = "Barbarian"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": barbarian.entry_key,
        "entry_type": "class",
        "title": barbarian.title,
        "slug": barbarian.slug,
        "source_id": barbarian.source_id,
    }
    current_definition.profile["class_ref"] = {
        "entry_key": barbarian.entry_key,
        "entry_type": "class",
        "title": barbarian.title,
        "slug": barbarian.slug,
        "source_id": barbarian.source_id,
    }
    current_definition.stats["max_hp"] = 27
    current_definition.features = [
        {
            "id": "rage-1",
            "name": "Rage",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "tracker_ref": "rage",
            "systems_ref": {"entry_type": "classfeature", "slug": "phb-classfeature-rage", "title": "Rage", "source_id": "PHB"},
        }
    ]
    current_definition.resource_templates = [
        {
            "id": "rage",
            "label": "Rage",
            "category": "class_feature",
            "initial_current": 2,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Rage",
            "display_order": 0,
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
            "id": "rage",
            "label": "Rage",
            "category": "class_feature",
            "current": 1,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Rage",
            "display_order": 0,
        }
    ]
    merged_state = merge_state_with_definition(leveled_definition, state, hp_delta=hp_delta)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert resources_by_id["rage"]["max"] == 3
    assert merged_resources["rage"]["current"] == 1
    assert merged_resources["rage"]["max"] == 3
def test_native_level_up_adds_arcane_shot_tracker_on_subclass_selection():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["str", "con"],
            "subclass_title": "Martial Archetype",
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
    arcane_archer = _systems_entry(
        "subclass",
        "xge-subclass-fighter-arcane-archer",
        "Arcane Archer",
        source_id="XGE",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    martial_archetype = _systems_entry(
        "classfeature",
        "phb-classfeature-martial-archetype",
        "Martial Archetype",
        metadata={"level": 3},
    )
    arcane_shot = _systems_entry(
        "subclassfeature",
        "xge-subclassfeature-arcane-shot",
        "Arcane Shot",
        source_id="XGE",
        metadata={"level": 3, "class_name": "Fighter", "class_source": "PHB", "subclass_name": "Arcane Archer"},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [arcane_archer],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Martial Archetype", "entry": martial_archetype, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Arcane Shot", "entry": arcane_shot, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("arrow-ace", "Arrow Ace")
    current_definition.profile["class_level_text"] = "Fighter 2"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.stats["max_hp"] = 20

    form_values = {
        "hp_gain": "8",
        "subclass_slug": arcane_archer.slug,
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

    arcane_shot_feature = next(feature for feature in leveled_definition.features if feature["name"] == "Arcane Shot")
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Arcane Shot: 2 / 2 (Short Rest)" in level_up_context["preview"]["resources"]
    assert arcane_shot_feature["tracker_ref"] == "arcane-shot"
    assert resources_by_id["arcane-shot"]["max"] == 2
    assert resources_by_id["arcane-shot"]["reset_on"] == "short_rest"
    assert merged_resources["arcane-shot"]["current"] == 2
def test_native_level_up_adds_chronal_shift_tracker_on_subclass_selection():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "subclass_title": "Arcane Tradition",
        },
    )
    chronurgy = _systems_entry(
        "subclass",
        "egw-subclass-wizard-chronurgy-magic",
        "Chronurgy Magic",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
        source_id="EGW",
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
    spellcasting_feature = _systems_entry(
        "classfeature",
        "phb-classfeature-spellcasting",
        "Spellcasting",
        metadata={"level": 1},
    )
    arcane_recovery = _systems_entry(
        "classfeature",
        "phb-classfeature-arcane-recovery",
        "Arcane Recovery",
        metadata={"level": 1},
    )
    arcane_tradition = _systems_entry(
        "classfeature",
        "phb-classfeature-arcane-tradition",
        "Arcane Tradition",
        metadata={"level": 2},
    )
    chronal_shift = _systems_entry(
        "subclassfeature",
        "egw-subclassfeature-chronal-shift",
        "Chronal Shift",
        metadata={"level": 2, "class_name": "Wizard", "class_source": "PHB", "subclass_name": "Chronurgy Magic"},
        source_id="EGW",
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    mage_hand = _systems_entry("spell", "phb-spell-mage-hand", "Mage Hand", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    find_familiar = _systems_entry("spell", "phb-spell-find-familiar", "Find Familiar", metadata={"casting_time": [{"number": 1, "unit": "hour"}]})
    mage_armor = _systems_entry("spell", "phb-spell-mage-armor", "Mage Armor", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    magic_missile = _systems_entry("spell", "phb-spell-magic-missile", "Magic Missile", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"casting_time": [{"number": 1, "unit": "reaction"}]})
    sleep = _systems_entry("spell", "phb-spell-sleep", "Sleep", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    burning_hands = _systems_entry("spell", "phb-spell-burning-hands", "Burning Hands", metadata={"casting_time": [{"number": 1, "unit": "action"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [chronurgy],
            "item": [],
            "spell": [
                light,
                mage_hand,
                message,
                detect_magic,
                find_familiar,
                mage_armor,
                magic_missile,
                shield,
                sleep,
                thunderwave,
                burning_hands,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    _progression_row("Spellcasting", entry=spellcasting_feature, option_groups=[]),
                    _progression_row("Arcane Recovery", entry=arcane_recovery, option_groups=[]),
                ],
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    _progression_row("Arcane Tradition", entry=arcane_tradition, option_groups=[]),
                ],
            },
        ],
        subclass_progression=[
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    _progression_row("Chronal Shift", entry=chronal_shift, option_groups=[]),
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("nadi-tempo", "Nadi Tempo")
    current_definition.profile["class_level_text"] = "Wizard 1"
    current_definition.profile["classes"][0]["row_id"] = "class-row-1"
    current_definition.profile["classes"][0]["class_name"] = "Wizard"
    current_definition.profile["classes"][0]["level"] = 1
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(wizard)
    current_definition.profile["class_ref"] = _systems_ref(wizard)
    current_definition.stats["max_hp"] = 8
    current_definition.stats["ability_scores"]["int"] = {"score": 16, "modifier": 3, "save_bonus": 5}
    current_definition.stats["ability_scores"]["wis"] = {"score": 12, "modifier": 1, "save_bonus": 3}
    current_definition.features = [
        {
            "id": "spellcasting-1",
            "name": "Spellcasting",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": _systems_ref(spellcasting_feature),
            "class_row_id": "class-row-1",
        },
        {
            "id": "arcane-recovery-1",
            "name": "Arcane Recovery",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "systems_ref": _systems_ref(arcane_recovery),
            "class_row_id": "class-row-1",
        },
    ]
    current_definition.spellcasting = {
        "spellcasting_class": "Wizard",
        "spellcasting_ability": "Intelligence",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {"name": "Light", "mark": "Cantrip", "systems_ref": _systems_ref(light), "class_row_id": "class-row-1"},
            {"name": "Mage Hand", "mark": "Cantrip", "systems_ref": _systems_ref(mage_hand), "class_row_id": "class-row-1"},
            {"name": "Message", "mark": "Cantrip", "systems_ref": _systems_ref(message), "class_row_id": "class-row-1"},
            {
                "name": "Detect Magic",
                "mark": "Prepared + Spellbook",
                "systems_ref": _systems_ref(detect_magic),
                "class_row_id": "class-row-1",
            },
            {"name": "Find Familiar", "mark": "Spellbook", "systems_ref": _systems_ref(find_familiar), "class_row_id": "class-row-1"},
            {
                "name": "Mage Armor",
                "mark": "Prepared + Spellbook",
                "systems_ref": _systems_ref(mage_armor),
                "class_row_id": "class-row-1",
            },
            {
                "name": "Magic Missile",
                "mark": "Prepared + Spellbook",
                "systems_ref": _systems_ref(magic_missile),
                "class_row_id": "class-row-1",
            },
            {"name": "Shield", "mark": "Prepared + Spellbook", "systems_ref": _systems_ref(shield), "class_row_id": "class-row-1"},
            {"name": "Sleep", "mark": "Spellbook", "systems_ref": _systems_ref(sleep), "class_row_id": "class-row-1"},
        ],
    }

    form_values = {
        "hp_gain": "4",
        "subclass_slug": chronurgy.slug,
        "levelup_wizard_spellbook_1": thunderwave.slug,
        "levelup_wizard_spellbook_2": burning_hands.slug,
        "levelup_wizard_prepared_1": thunderwave.slug,
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

    chronal_shift_feature = next(feature for feature in leveled_definition.features if feature["name"] == "Chronal Shift")
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}
    merged_resources = {resource["id"]: resource for resource in merged_state["resources"]}

    assert "Chronal Shift: 2 / 2 (Long Rest)" in level_up_context["preview"]["resources"]
    assert leveled_definition.profile["subclass_ref"]["slug"] == chronurgy.slug
    assert chronal_shift_feature["class_row_id"] == "class-row-1"
    assert chronal_shift_feature["tracker_ref"] == "chronal-shift"
    assert chronal_shift_feature["activation_type"] == "reaction"
    assert resources_by_id["chronal-shift"]["class_row_id"] == "class-row-1"
    assert resources_by_id["chronal-shift"]["max"] == 2
    assert resources_by_id["chronal-shift"]["reset_on"] == "long_rest"
    assert merged_resources["chronal-shift"]["current"] == 2
@pytest.mark.parametrize(
    "slug,title,status",
    [
        pytest.param(slug, entry["title"], entry["status"], id=slug)
        for slug, entry in sorted(MANAGED_RESOURCE_TRACKER_INVENTORY.items())
    ],
)
def test_managed_resource_inventory_entries_attach_or_stay_excluded(slug: str, title: str, status: str):
    category = "subclass_feature" if "-subclassfeature-" in slug else "class_feature"
    source_id = slug.split("-", 1)[0].upper()
    definition = _managed_resource_definition(
        slug=slug,
        title=title,
        category=category,
        source_id=source_id,
        class_level=20,
    )
    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}

    if status == "supported":
        assert normalized.resource_templates, slug
        assert next(iter(features_by_name.values())).get("tracker_ref"), slug
        return

    assert normalized.resource_templates == []
    assert not next(iter(features_by_name.values())).get("tracker_ref")
def test_managed_resource_registry_supports_page_ref_identity_for_psi_warrior():
    definition = _managed_resource_definition(
        slug="campaign-psi-warrior",
        title="Psionic Power",
        category="subclass_feature",
        source_id="Campaign",
        class_level=7,
        page_ref="mechanics/psi-warrior/psionic-power",
    )
    definition.features[0].pop("systems_ref", None)

    normalized = normalize_definition_to_native_model(definition)
    features_by_name = {feature["name"]: feature for feature in normalized.features}
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}

    assert features_by_name["Psionic Power"]["tracker_ref"] == "psionic-power-psionic-energy"
    assert features_by_name["Psionic Power: Telekinetic Movement"]["tracker_ref"] == "psionic-power-telekinetic-movement"
    assert features_by_name["Psionic Power: Recovery"]["tracker_ref"] == "psionic-power-recovery"
    assert "Psionic Power: Protective Field" in features_by_name
    assert "Psionic Power: Psionic Strike" in features_by_name
    assert resources_by_id["psionic-power-psionic-energy"]["max"] == 6
@pytest.mark.parametrize(
    ("slug", "title", "class_level", "ability_scores", "expected"),
    [
        pytest.param(
            "tce-classfeature-flashofgenius-artificer-tce-7",
            "Flash of Genius",
            7,
            {"int": 18},
            {"id": "flash-of-genius", "max": 4, "reset_on": "long_rest", "activation_type": "reaction"},
            id="ability-mod",
        ),
        pytest.param(
            "tce-subclassfeature-experimentalelixir-artificer-tce-alchemist-tce-3",
            "Experimental Elixir",
            15,
            {},
            {"id": "experimental-elixir", "max": 3, "reset_on": "long_rest", "activation_type": "action"},
            id="threshold",
        ),
        pytest.param(
            "xge-subclassfeature-healinglight-warlock-phb-celestial-xge-1",
            "Healing Light",
            6,
            {},
            {"id": "healing-light", "max": 7, "reset_on": "long_rest", "activation_type": "bonus_action"},
            id="level-pool",
        ),
        pytest.param(
            "phb-subclassfeature-arcaneward-wizard-phb-abjuration-phb-2",
            "Arcane Ward",
            10,
            {"int": 16},
            {"id": "arcane-ward", "max": 23, "reset_on": "manual", "reset_to": "unchanged", "activation_type": "passive"},
            id="manual-pool",
        ),
        pytest.param(
            "xge-subclassfeature-powersurge-wizard-phb-war-xge-6",
            "Power Surge",
            10,
            {"int": 18},
            {"id": "power-surge", "max": 4, "reset_on": "long_rest", "reset_to": "1", "activation_type": "special"},
            id="fixed-reset-to",
        ),
    ],
)
def test_managed_resource_registry_representative_scaling_cases(
    slug: str,
    title: str,
    class_level: int,
    ability_scores: dict[str, int],
    expected: dict[str, object],
):
    category = "subclass_feature" if "-subclassfeature-" in slug else "class_feature"
    definition = _managed_resource_definition(
        slug=slug,
        title=title,
        category=category,
        source_id=slug.split("-", 1)[0].upper(),
        class_level=class_level,
        ability_scores=ability_scores,
    )

    normalized = normalize_definition_to_native_model(definition)
    feature = normalized.features[0]
    resource = normalized.resource_templates[0]

    assert feature["tracker_ref"] == expected["id"]
    assert feature["activation_type"] == expected["activation_type"]
    assert resource["id"] == expected["id"]
    assert resource["max"] == expected["max"]
    assert resource["reset_on"] == expected["reset_on"]
    if "reset_to" in expected:
        assert resource["reset_to"] == expected["reset_to"]
def test_managed_resource_registry_scales_from_class_row_level_on_multiclass_definition():
    definition = _managed_resource_definition(
        slug="xge-subclassfeature-healinglight-warlock-phb-celestial-xge-1",
        title="Healing Light",
        category="subclass_feature",
        source_id="XGE",
        class_name="Warlock",
        class_slug="phb-class-warlock",
        class_level=3,
    )
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Warlock",
            "subclass_name": "The Celestial",
            "level": 3,
            "systems_ref": _systems_ref(_systems_entry("class", "phb-class-warlock", "Warlock")),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Fighter",
            "subclass_name": "",
            "level": 7,
            "systems_ref": _systems_ref(_systems_entry("class", "phb-class-fighter", "Fighter")),
        },
    ]
    definition.profile["class_level_text"] = "Warlock 3 / Fighter 7"

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.resource_templates[0]["max"] == 4
def test_managed_resource_registry_preserves_spent_values_when_level_pool_max_grows():
    definition = _managed_resource_definition(
        slug="xge-subclassfeature-healinglight-warlock-phb-celestial-xge-1",
        title="Healing Light",
        category="subclass_feature",
        source_id="XGE",
        class_name="Warlock",
        class_slug="phb-class-warlock",
        class_level=3,
    )
    normalized = normalize_definition_to_native_model(definition)
    state = build_initial_state(normalized)
    state["resources"] = [
        {
            "id": "healing-light",
            "label": "Healing Light",
            "category": "subclass_feature",
            "current": 2,
            "max": 4,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Healing Light",
            "display_order": 0,
            "class_row_id": "class-row-1",
        }
    ]

    definition.profile["classes"][0]["level"] = 4
    definition.profile["class_level_text"] = "Warlock 4"
    leveled = normalize_definition_to_native_model(definition)
    merged_state = merge_state_with_definition(leveled, state)

    assert leveled.resource_templates[0]["max"] == 5
    assert merged_state["resources"][0]["current"] == 2
    assert merged_state["resources"][0]["max"] == 5
def test_build_native_level_up_context_assigns_targeted_live_preview_regions_for_controls_and_asi_fields():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    human = _systems_entry("race", "phb-race-human", "Human", metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]})
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    ability_score_improvement = _systems_entry("classfeature", "phb-classfeature-asi", "Ability Score Improvement", metadata={"level": 4})
    magic_initiate = _systems_entry(
        "feat",
        "phb-feat-magic-initiate",
        "Magic Initiate",
        metadata={
            "additional_spells": [
                {
                    "ability": "wis",
                    "known": {"_": [{"choose": "level=0|class=Cleric", "count": 1}]},
                    "innate": {"_": {"daily": {"1": [{"choose": "level=1|class=Cleric"}]}}},
                }
            ]
        },
    )
    guidance = _systems_entry(
        "spell",
        "phb-spell-guidance",
        "Guidance",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Cleric"]}},
    )
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Cleric"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [magic_initiate],
            "subclass": [],
            "item": [],
            "spell": [guidance, cure_wounds],
        },
        class_progression=[
            {
                "level": 4,
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )
    current_definition = _minimal_character_definition("asi-preview", "ASI Preview")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.stats["max_hp"] = 24

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        {"hp_gain": "8"},
    )

    _assert_live_preview_metadata(
        context["field_live_preview"]["advancement_mode"],
        trigger="change",
        regions="advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
        debounce_ms=100,
    )
    _assert_live_preview_metadata(
        context["field_live_preview"]["target_class_row_id"],
        trigger="change",
        regions="advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
        debounce_ms=100,
    )
    _assert_live_preview_metadata(
        context["field_live_preview"]["hp_gain"],
        trigger="input",
        regions="preview-summary",
        debounce_ms=650,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "levelup_asi_mode_1"),
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "levelup_asi_ability_1_1"),
        trigger="change",
        regions="preview-summary,preview-spells,preview-attacks",
        debounce_ms=120,
    )

    feat_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        {"hp_gain": "8", "levelup_asi_mode_1": "feat", "levelup_feat_1": magic_initiate.slug},
    )

    _assert_live_preview_metadata(
        _find_builder_field(feat_context, "levelup_feat_1"),
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(feat_context, "feat_levelup_feat_1_spell_known_1_1"),
        trigger="change",
        regions="preview-spells",
        debounce_ms=120,
    )
def test_dm_can_see_level_up_entry_for_supported_native_character(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )

    response = client.get("/campaigns/linden-pass/characters/leveler")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/leveler/level-up" in html
    assert "Level up" in html
def test_assigned_player_can_open_level_up_without_characters_scope(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="dm", session="players")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march/level-up")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Level Up Leveler" in html
    assert 'href="/campaigns/linden-pass/session/character?character=arden-march"' in html

    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_response = client.get("/campaigns/linden-pass/characters/arden-march/level-up")

    assert blocked_response.status_code == 403
def test_dm_can_apply_native_level_up_route(app, client, sign_in, users, get_character, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    leveled_definition = _minimal_character_definition("leveler", "Leveler")
    leveled_definition.profile["class_level_text"] = "Fighter 2"
    leveled_definition.profile["classes"][0]["level"] = 2
    leveled_definition.stats["max_hp"] = 20
    leveled_definition.features = [
        {
            "id": "action-surge-1",
            "name": "Action Surge",
            "category": "class_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "special",
            "tracker_ref": "action-surge",
            "systems_ref": {"entry_type": "classfeature", "slug": "phb-classfeature-action-surge", "title": "Action Surge", "source_id": "PHB"},
        }
    ]
    leveled_definition.resource_templates = [
        {
            "id": "action-surge",
            "label": "Action Surge",
            "category": "class_feature",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Action Surge",
            "display_order": 0,
        }
    ]
    leveled_import = _minimal_import_metadata("leveler")
    leveled_import.source_path = "builder://native-level-2"

    monkeypatch.setattr(
        app_module,
        "build_native_level_up_character_definition",
        lambda *args, **kwargs: (leveled_definition, leveled_import, 8),
    )

    response = client.post(
        "/campaigns/linden-pass/characters/leveler/level-up",
        data={"expected_revision": "1", "hp_gain": "8"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/leveler")

    definition_payload = yaml.safe_load((character_dir / "definition.yaml").read_text(encoding="utf-8"))
    import_payload = yaml.safe_load((character_dir / "import.yaml").read_text(encoding="utf-8"))
    assert definition_payload["profile"]["class_level_text"] == "Fighter 2"
    assert import_payload["source_path"] == "builder://native-level-2"

    record = get_character("leveler")
    assert record is not None
    assert record.definition.stats["max_hp"] == 20
    assert record.state_record.state["vitals"]["current_hp"] == 20
    assert any(resource["id"] == "action-surge" for resource in record.state_record.state["resources"])
def test_level_up_live_preview_route_returns_fragment(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    response = client.get("/campaigns/linden-pass/characters/leveler/level-up?_live_preview=1&hp_gain=8")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<!doctype html>" not in html.lower()
    assert "data-live-builder-root" in html
    assert "data-live-builder-form" in html
    assert "data-live-refresh-fallback" in html
    assert response.headers["X-Live-State-Changed"] == "true"
    assert response.headers["X-Live-Query-Count"]
    assert response.headers["X-Live-Query-Time-Ms"]
    assert response.headers["X-Live-Request-Time-Ms"]
    assert "db;dur=" in response.headers["Server-Timing"]
    assert "total;dur=" in response.headers["Server-Timing"]
def test_level_up_live_preview_route_returns_requested_regions_only(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    response = client.get(
        "/campaigns/linden-pass/characters/leveler/level-up?_live_preview=1&regions=preview-summary,preview-spell-slots&hp_gain=8"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data-live-builder-root" not in html
    assert 'data-live-builder-region="preview-summary"' in html
    assert 'data-live-builder-region="preview-spell-slots"' in html
    assert 'data-live-builder-region="preview-features"' not in html
def test_level_up_page_renders_hp_gain_as_summary_only_live_preview(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    response = client.get("/campaigns/linden-pass/characters/leveler/level-up")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-live-builder-root' in html
    assert 'data-loading="0"' in html
    assert "window.__playerWikiLiveUiTools" in html
    assert 'liveRoot.dataset.loading = "1";' in html
    assert 'name="hp_gain"' in html
    assert 'data-live-preview-trigger="input"' in html
    assert 'data-live-preview-regions="preview-summary"' in html
    assert 'data-live-preview-debounce-ms="650"' in html
def test_native_level_up_adds_campaign_feat_modeled_helper_row():
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
            "mechanics/bulwark-discipline",
            "Bulwark Discipline",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Bulwark Discipline",
                    "modeled_effects": ["Shield Master"],
                }
            },
        )
    ]

    current_definition = _minimal_character_definition("bulwark-veteran", "Bulwark Veteran")
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
                "entry_key": "phb|item|shield",
                "entry_type": "item",
                "title": "Shield",
                "slug": "phb-item-shield",
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
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", "Bulwark Discipline")

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
    bulwark_discipline = next(feature for feature in leveled_definition.features if feature["name"] == "Bulwark Discipline")
    shield_shove = next(attack for attack in leveled_definition.attacks if attack["name"] == "Shield Shove")

    assert "Bulwark Discipline" in level_up_context["preview"]["gained_features"]
    assert "Shield Shove (special action)" in level_up_context["preview"]["attacks"]
    assert bulwark_discipline["page_ref"] == "mechanics/bulwark-discipline"
    assert shield_shove["attack_bonus"] is None
    assert shield_shove["damage"] == ""
    assert shield_shove["notes"] == "Bonus action after taking the Attack action; Shield Master shove within 5 feet."
    assert shield_shove["mode_key"] == "feat:phb-feat-shield-master:shove"
    assert shield_shove["equipment_refs"] == ["shield-1"]
@pytest.mark.parametrize(
    ("feat_name", "feat_slug", "tracker_id", "preview_label", "activation_type"),
    _SINGLE_TRACKER_FEAT_CASES,
)
def test_native_level_up_applies_single_use_short_rest_feat_trackers(
    feat_name: str,
    feat_slug: str,
    tracker_id: str,
    preview_label: str,
    activation_type: str,
):
    systems_service, current_definition, form_values = _build_single_tracker_feat_level_up_fixture(feat_name, feat_slug)

    level_up_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )

    feat_feature = next(feature for feature in leveled_definition.features if feature["name"] == feat_name)
    resources_by_id = {resource["id"]: resource for resource in leveled_definition.resource_templates}

    assert feat_name in level_up_context["preview"]["gained_features"]
    assert preview_label in level_up_context["preview"]["resources"]
    assert feat_feature["tracker_ref"] == tracker_id
    assert feat_feature["activation_type"] == activation_type
    assert resources_by_id[tracker_id]["max"] == 1
    assert resources_by_id[tracker_id]["reset_on"] == "short_rest"
def test_native_level_up_recalculates_scaled_campaign_progression_trackers():
    fixture = _build_sorcerer_wild_magic_fixture()
    systems_service = fixture["systems_service"]
    level_one_values = dict(fixture["level_one_values"])

    builder_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        level_one_values,
    )
    current_definition, _import_metadata = build_level_one_character_definition(
        "linden-pass",
        builder_context,
        level_one_values,
    )

    current_definition.profile["class_level_text"] = "Sorcerer 3"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.spellcasting["spells"].extend(
        [
            {
                "name": "Chromatic Orb",
                "mark": "Known",
                "systems_ref": {
                    "entry_type": "spell",
                    "slug": "phb-spell-chromatic-orb",
                    "title": "Chromatic Orb",
                    "source_id": "PHB",
                },
            },
            {
                "name": "Sleep",
                "mark": "Known",
                "systems_ref": {
                    "entry_type": "spell",
                    "slug": "phb-spell-sleep",
                    "title": "Sleep",
                    "source_id": "PHB",
                },
            },
        ]
    )

    level_up_values = {
        "hp_gain": "4",
        "levelup_asi_mode_1": "ability_scores",
        "levelup_asi_ability_1_1": "cha",
        "levelup_asi_ability_1_2": "cha",
        "levelup_spell_known_1": "phb-spell-mage-armor",
    }
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        level_up_values,
    )

    assert "Wild Die: 2 / 2 (Long Rest)" in level_up_context["preview"]["resources"]

    leveled_definition, _leveled_import, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_values,
    )

    wild_die_resource = next(
        template for template in leveled_definition.resource_templates if template.get("label") == "Wild Die"
    )

    assert hp_gain == 4
    assert wild_die_resource["max"] == 2
    assert wild_die_resource["initial_current"] == 2
    assert wild_die_resource["scaling"]["mode"] == "half_level"
