from __future__ import annotations

from tests.helpers.character_builder_fakes import *  # noqa: F401,F403

def test_build_initial_state_tracks_slot_usage_by_lane_for_non_shared_multiclass():
    definition = _minimal_character_definition("wizard-warlock-state", "Wizard Warlock State")
    definition.spellcasting = {
        "slot_progression": [],
        "slot_lanes": [
            {
                "id": "class-row-1-slots",
                "title": "Wizard spell slots",
                "shared": False,
                "row_ids": ["class-row-1"],
                "slot_progression": [
                    {"level": 1, "max_slots": 4},
                    {"level": 2, "max_slots": 2},
                ],
            },
            {
                "id": "class-row-2-slots",
                "title": "Warlock Pact Magic slots",
                "shared": False,
                "row_ids": ["class-row-2"],
                "slot_progression": [
                    {"level": 1, "max_slots": 2},
                ],
            },
        ],
        "spells": [],
    }

    initial_state = build_initial_state(definition)

    assert initial_state["spell_slots"] == [
        {"level": 1, "max": 4, "used": 0, "slot_lane_id": "class-row-1-slots"},
        {"level": 2, "max": 2, "used": 0, "slot_lane_id": "class-row-1-slots"},
        {"level": 1, "max": 2, "used": 0, "slot_lane_id": "class-row-2-slots"},
    ]
def test_builder_requires_complete_structured_replacement_pairs():
    with pytest.raises(ValueError, match="must both be chosen together"):
        _resolve_builder_choices(
            [
                {
                    "title": "Spell Choices",
                    "fields": [
                        {
                            "name": "spell_support_replace_known_1_from_1",
                            "label": "Replace Spell 1",
                            "options": [{"label": "Message", "value": "phb-spell-message"}],
                            "selected": "",
                            "group_key": "spell_support_replace_known_1_from",
                            "kind": "spell_support_replace_from",
                            "required": False,
                            "paired_field_name": "spell_support_replace_known_1_to_1",
                            "paired_field_label": "Replacement Spell 1",
                        },
                        {
                            "name": "spell_support_replace_known_1_to_1",
                            "label": "Replacement Spell 1",
                            "options": [{"label": "Ray of Frost", "value": "phb-spell-ray-of-frost"}],
                            "selected": "",
                            "group_key": "spell_support_replace_known_1_to",
                            "kind": "spell_support_replace_to",
                            "required": False,
                            "paired_field_name": "spell_support_replace_known_1_from_1",
                            "paired_field_label": "Replace Spell 1",
                        },
                    ],
                }
            ],
            {"spell_support_replace_known_1_from_1": "phb-spell-message"},
        )
def test_level_one_builder_creates_native_character_definition_from_phb_choices():
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
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True, "anyStandard": 1}],
            "skill_proficiencies": [{"any": 1}],
            "feats": [{"any": 1}],
        },
        body={
            "entries": [
                {"name": "Feature: Human Versatility", "entries": ["You are broadly capable and adaptable."]},
                {"name": "Languages", "entries": ["You can speak Common and one extra language."]},
            ]
        },
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={
            "skill_proficiencies": [{"insight": True, "religion": True}],
            "language_proficiencies": [{"anyStandard": 2}],
        },
        body={
            "entries": [
                {
                    "name": "Feature: Shelter of the Faithful",
                    "entries": ["You can find shelter and support from others of your faith."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    alert = _systems_entry("feat", "phb-feat-alert", "Alert")
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    fighting_style = _systems_entry(
        "classfeature",
        "phb-classfeature-fighting-style",
        "Fighting Style",
        metadata={"level": 1},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [alert],
            "subclass": [],
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
                                        {"label": "Defense", "slug": "phb-optionalfeature-defense"},
                                        {"label": "Dueling", "slug": "phb-optionalfeature-dueling"},
                                    ]
                                }
                            ]
                        },
                    },
                    {
                        "label": "Second Wind",
                        "entry": second_wind,
                        "embedded_card": {"option_groups": []},
                    },
                ],
            }
        ],
    )
    form_values = {
        "name": "Test Hero",
        "character_slug": "test-hero",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Dwarvish",
        "background_language_1": "Elvish",
        "background_language_2": "Gnomish",
        "species_feat_1": alert.slug,
        "class_option_1": "phb-optionalfeature-defense",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, import_metadata = build_level_one_character_definition("linden-pass", context, form_values)

    feature_names = {feature["name"] for feature in definition.features}
    proficient_skill_names = {
        skill["name"] for skill in definition.skills if skill.get("proficiency_level") == "proficient"
    }

    assert context["preview"]["max_hp"] == 12
    assert "Alert" in context["preview"]["features"]
    assert definition.character_slug == "test-hero"
    assert definition.profile["class_level_text"] == "Fighter 1"
    assert definition.profile["species"] == "Variant Human"
    assert definition.stats["max_hp"] == 12
    assert "Common" in definition.proficiencies["languages"]
    assert "Dwarvish" in definition.proficiencies["languages"]
    assert "Elvish" in definition.proficiencies["languages"]
    assert "Gnomish" in definition.proficiencies["languages"]
    assert "Athletics" in proficient_skill_names
    assert "History" in proficient_skill_names
    assert "Perception" in proficient_skill_names
    assert "Insight" in proficient_skill_names
    assert "Religion" in proficient_skill_names
    assert "Second Wind" in feature_names
    assert "Defense" in feature_names
    assert "Human Versatility" in feature_names
    assert "Shelter of the Faithful" in feature_names
    assert "Alert" in feature_names
    assert any(feature["tracker_ref"] == "second-wind" for feature in definition.features if feature["name"] == "Second Wind")
    assert any(template["id"] == "second-wind" and template["max"] == 1 for template in definition.resource_templates)
    assert import_metadata.source_path == "builder://native-level-1"
def test_level_one_builder_applies_structured_campaign_page_option_grants():
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
    soldier = _systems_entry(
        "background",
        "phb-background-soldier",
        "Soldier",
        metadata={"skill_proficiencies": [{"athletics": True, "intimidation": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={
            "level": 0,
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "touch"},
            "components": {"v": True, "m": "a firefly or phosphorescent moss"},
            "duration": [{"type": "timed", "duration": {"type": "hour", "amount": 1}}],
        },
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={
            "level": 1,
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "self"},
            "components": {"v": True, "s": True},
            "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 10}, "concentration": True}],
            "ritual": True,
        },
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
            }
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
                        "skills": ["Perception"],
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

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values = {
        **form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(context, "campaign_feature_page_ref_1", "Blessing of the Tide"),
        "campaign_item_page_ref_1": _field_value_for_label(context, "campaign_item_page_ref_1", "Harbor Badge"),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    blessing = next(feature for feature in definition.features if feature["name"] == "Blessing of the Tide")
    harbor_badge = next(item for item in definition.equipment_catalog if item["name"] == "Harbor Badge")
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    skills_by_name = {skill["name"]: skill for skill in definition.skills}
    tracker_ref = str(blessing.get("tracker_ref") or "")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert blessing["page_ref"] == "mechanics/blessing-of-the-tide"
    assert blessing["activation_type"] == "bonus_action"
    assert blessing["description_markdown"] == "Call on the tide to steady your footing."
    assert tracker_ref.startswith("campaign-option-tracker:blessing-of-the-tide-")
    assert harbor_badge["page_ref"] == "items/harbor-badge"
    assert harbor_badge["default_quantity"] == 2
    assert harbor_badge["weight"] == "light"
    assert harbor_badge["notes"] == "Issued by the Harbor Wardens."
    assert "Primordial" in definition.proficiencies["languages"]
    assert "Navigator's Tools" in definition.proficiencies["tools"]
    assert "Light Armor" in definition.proficiencies["armor"]
    assert skills_by_name["Perception"]["proficiency_level"] == "proficient"
    assert definition.stats["initiative_bonus"] == 3
    assert definition.stats["speed"] == "40 ft."
    assert definition.stats["armor_class"] == 12
    assert definition.stats["passive_perception"] == 16
    assert definition.spellcasting["spellcasting_class"] == ""
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert resources_by_id[tracker_ref]["max"] == 3
    assert resources_by_id[tracker_ref]["reset_on"] == "long_rest"
    assert "Blessing of the Tide: 3 / 3 (Long Rest)" in context["preview"]["resources"]
    assert any("Detect Magic" in spell_line for spell_line in context["preview"]["spells"])
def test_campaign_progression_entries_preserve_base_rule_refs():
    progression_entry = build_campaign_page_progression_entries(
        _campaign_page_record(
            "mechanics/warding-principles",
            "Warding Principles",
            section="Mechanics",
            subsection="Class Modifications",
            metadata={
                "character_progression": {
                    "kind": "class",
                    "class_name": "Wizard",
                    "level": 2,
                    "character_option": {
                        "name": "Warding Principles",
                        "base_rule_refs": [
                            {"rule_key": "Armor Class"},
                            {
                                "systems_ref": {
                                    "slug": "phb-variantrule-encumbrance",
                                    "entry_type": "variantrule",
                                    "source_id": "PHB",
                                }
                            },
                        ],
                    },
                }
            },
        )
    )[0]

    assert progression_entry.metadata["campaign_option"]["base_rule_refs"] == [
        {"rule_key": "armor-class"},
        {
            "slug": "phb-variantrule-encumbrance",
            "source_id": "PHB",
            "entry_type": "variantrule",
        },
    ]
    assert progression_entry.metadata["campaign_option"]["overlay_support"] == "reference_only"
    summary = progression_entry.metadata["campaign_option"]["base_rule_modification_summary"]
    assert [hook["key"] for hook in summary["reused_hooks"]] == [
        "character_option",
        "character_progression",
    ]
    assert [item["key"] for item in summary["missing_metadata"]] == [
        "change_operation",
        "affected_rule_facet",
        "baseline_carry_forward",
    ]
def test_campaign_character_option_base_rule_modification_summary_reuses_existing_hooks():
    campaign_option = normalize_campaign_character_option(
        {
            "kind": "feature",
            "name": "Arcane Thesis",
            "base_rule_refs": [{"rule_key": "Spell Attacks and Save DCs"}],
            "spell_support": [{"granted": [{"value": "Shield"}]}],
            "spell_manager": {"mode": "ritual_book", "title": "Arcane Thesis"},
            "modeled_effects": ["save-bonus:all:1"],
        },
        page_ref="mechanics/arcane-thesis",
        title="Arcane Thesis",
        summary="",
        default_kind="feature",
    )

    assert campaign_option is not None
    assert campaign_option["overlay_support"] == "modeled"
    summary = campaign_option["base_rule_modification_summary"]
    assert [hook["key"] for hook in summary["reused_hooks"]] == [
        "character_option",
        "spell_support",
        "spell_manager",
        "modeled_effects",
    ]
    assert [item["key"] for item in summary["missing_metadata"]] == [
        "change_operation",
        "affected_rule_facet",
        "baseline_carry_forward",
    ]
def test_campaign_character_option_normalizes_mechanic_effects_with_legacy_keys():
    campaign_option = normalize_campaign_character_option(
        {
            "kind": "feature",
            "name": "Arcane Thesis",
            "modeled_effects": ["save-bonus:all:1"],
            "mechanic_effects": [
                {
                    "kind": "stat-adjustment",
                    "key": "carrying-capacity-multiplier:2",
                    "label": "Dockside load training",
                },
                {
                    "kind": "ability_minimum",
                    "ability": "int",
                    "minimum": 14,
                },
            ],
        },
        page_ref="mechanics/arcane-thesis",
        title="Arcane Thesis",
        summary="",
        default_kind="feature",
    )

    assert campaign_option is not None
    assert campaign_option["modeled_effects"] == [
        "save-bonus:all:1",
        "carrying-capacity-multiplier:2",
    ]
    assert campaign_option["mechanic_effects"] == [
        {
            "kind": "stat_adjustment",
            "key": "save-bonus:all:1",
            "legacy_key": "save-bonus:all:1",
            "source": "modeled_effects",
        },
        {
            "kind": "stat_adjustment",
            "key": "carrying-capacity-multiplier:2",
            "legacy_key": "carrying-capacity-multiplier:2",
            "label": "Dockside load training",
            "source": "mechanic_effects",
        },
        {
            "kind": "ability_minimum",
            "ability": "int",
            "minimum": 14,
            "source": "mechanic_effects",
        },
    ]
def test_campaign_character_option_projects_resource_grant_as_mechanic_effect():
    campaign_option = normalize_campaign_character_option(
        {
            "kind": "feature",
            "name": "Wild Magic Modification",
            "activation_type": "special",
            "grants": {
                "resource": {
                    "label": "Wild Die",
                    "reset_on": "long_rest",
                    "scaling": {
                        "mode": "half_level",
                        "minimum": 1,
                        "round": "down",
                    },
                }
            },
        },
        page_ref="mechanics/wild-magic-modification",
        title="Wild Magic Modification",
        summary="The Wild Die is a d6 used by this subclass modification.",
        default_kind="feature",
    )

    assert campaign_option is not None
    assert campaign_option["resource"] == {
        "label": "Wild Die",
        "reset_on": "long_rest",
        "scaling": {
            "mode": "half_level",
            "minimum": 1,
            "round": "down",
        },
    }
    assert campaign_option["mechanic_effects"] == [
        {
            "kind": "resource_template",
            "resource": {
                "label": "Wild Die",
                "reset_on": "long_rest",
                "scaling": {
                    "mode": "half_level",
                    "minimum": 1,
                    "round": "down",
                },
            },
            "source": "character_option.resource",
        }
    ]
    assert "modeled_effects" not in campaign_option
def test_level_one_builder_applies_page_backed_campaign_progression_overlay_base_rule_effects():
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
    soldier = _systems_entry(
        "background",
        "phb-background-soldier",
        "Soldier",
        metadata={"skill_proficiencies": [{"athletics": True, "intimidation": True}]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    overlay_record = _campaign_page_record(
        "mechanics/dockside-load-training",
        "Dockside Load Training",
        section="Mechanics",
        subsection="Class Modifications",
        metadata={
            "character_progression": {
                "kind": "class",
                "class_name": "Fighter",
                "level": 1,
                "character_option": {
                    "name": "Dockside Load Training",
                    "description_markdown": "Dock crews in this campaign double the normal carrying baseline.",
                    "activation_type": "passive",
                    "base_rule_refs": [
                        {"rule_key": "Carrying Capacity and Encumbrance"},
                        {
                            "systems_ref": {
                                "slug": "phb-variantrule-encumbrance",
                                "entry_type": "variantrule",
                                "source_id": "PHB",
                            }
                        },
                    ],
                    "modeled_effects": ["carrying-capacity-multiplier:2"],
                },
            }
        },
    )
    dockside_load_training = build_campaign_page_progression_entries(overlay_record)[0]
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
                    {"label": "Dockside Load Training", "entry": dockside_load_training, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Dockhand",
        "character_slug": "dockhand",
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
        campaign_page_records=[overlay_record],
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    overlay_feature = next(feature for feature in definition.features if feature["name"] == "Dockside Load Training")

    assert "Dockside Load Training" in context["preview"]["features"]
    assert overlay_feature["page_ref"] == "mechanics/dockside-load-training"
    assert overlay_feature["campaign_option"]["overlay_support"] == "modeled"
    assert overlay_feature["campaign_option"]["base_rule_refs"] == [
        {"rule_key": "carrying-capacity-and-encumbrance"},
        {
            "slug": "phb-variantrule-encumbrance",
            "source_id": "PHB",
            "entry_type": "variantrule",
        },
    ]
    assert definition.stats["carrying_capacity"] == 480
    assert definition.stats["push_drag_lift"] == 960
def test_level_one_builder_supports_page_backed_species_background_and_feat_choices():
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
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"level": 0, "casting_time": [{"number": 1, "unit": "action"}]},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"level": 1, "casting_time": [{"number": 1, "unit": "action"}], "ritual": True},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [],
            "background": [],
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
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "species/sea-blessed",
            "Sea-Blessed",
            section="Mechanics",
            subsection="Species",
            summary="A people shaped by tide and storm.",
            metadata={
                "character_option": {
                    "kind": "species",
                    "name": "Sea-Blessed",
                    "description_markdown": "Children of the surf carry a little of the sea wherever they go.",
                    "size": ["M"],
                    "speed": 35,
                    "languages": [{"common": True, "anyStandard": 1}],
                    "skill_proficiencies": [{"any": 1}],
                    "feats": [{"any": 1}],
                }
            },
        ),
        _campaign_page_record(
            "backgrounds/harbor-initiate",
            "Harbor Initiate",
            section="Mechanics",
            subsection="Backgrounds",
            summary="Raised amid watchfires and harbor bells.",
            metadata={
                "character_option": {
                    "kind": "background",
                    "name": "Harbor Initiate",
                    "description_markdown": "You learned to read the tides and the people who work them.",
                    "skill_proficiencies": [{"insight": True}],
                    "language_proficiencies": [{"anyStandard": 1}],
                }
            },
        ),
        _campaign_page_record(
            "mechanics/tidecaller-gift",
            "Tidecaller Gift",
            section="Mechanics",
            subsection="Feats",
            summary="A blessing that turns the voice of the sea toward you.",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Tidecaller Gift",
                    "description_markdown": "You can briefly call the tide to answer your need.",
                    "ability": [{"wis": 1}],
                    "grants": {
                        "tools": ["Navigator's Tools"],
                        "stat_adjustments": {"initiative_bonus": 2},
                        "resource": {"label": "Tidecaller Gift", "max": 1, "reset_on": "long_rest"},
                        "spells": [
                            {"spell": "Light", "mark": "Granted"},
                            {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                        ],
                    },
                }
            },
        ),
    ]

    initial_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "name": "Maris Vane",
            "character_slug": "maris-vane",
            "alignment": "Neutral Good",
            "experience_model": "Milestone",
            "class_slug": fighter.slug,
            "str": "16",
            "dex": "12",
            "con": "14",
            "int": "10",
            "wis": "12",
            "cha": "8",
        },
        campaign_page_records=campaign_page_records,
    )

    species_value = _option_value_for_label(initial_context["species_options"], "Sea-Blessed")
    background_value = _option_value_for_label(initial_context["background_options"], "Harbor Initiate")

    assert species_value.startswith("page:")
    assert background_value.startswith("page:")

    form_values = {
        "name": "Maris Vane",
        "character_slug": "maris-vane",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": species_value,
        "background_slug": background_value,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_skill_1": "perception",
        "species_language_1": "Elvish",
        "background_language_1": "Dwarvish",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "12",
        "cha": "8",
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    feat_value = _field_value_for_label(context, "species_feat_1", "Tidecaller Gift")
    assert feat_value.startswith("page:")
    form_values["species_feat_1"] = feat_value

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    feature_names = {feature["name"] for feature in definition.features}
    tidecaller = next(feature for feature in definition.features if feature["name"] == "Tidecaller Gift")
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert definition.profile["species"] == "Sea-Blessed"
    assert definition.profile["species_ref"] is None
    assert definition.profile["species_page_ref"] == "species/sea-blessed"
    assert definition.profile["background"] == "Harbor Initiate"
    assert definition.profile["background_ref"] is None
    assert definition.profile["background_page_ref"] == "backgrounds/harbor-initiate"
    assert definition.stats["speed"] == "35 ft."
    assert definition.stats["initiative_bonus"] == 3
    assert definition.stats["ability_scores"]["wis"]["score"] == 13
    assert "Sea-Blessed" in feature_names
    assert "Harbor Initiate" in feature_names
    assert tidecaller["page_ref"] == "mechanics/tidecaller-gift"
    assert "Navigator's Tools" in definition.proficiencies["tools"]
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert resources_by_id[str(tidecaller.get("tracker_ref") or "")]["max"] == 1
def test_level_one_builder_supports_campaign_feat_optionalfeature_progression_and_modeled_effects():
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
    defense = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-defense",
        "Defense",
        metadata={"feature_type": ["FS:F"]},
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
            "race": [variant_human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [],
            "optionalfeature": [defense, dueling],
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
            "mechanics/harbor-drill",
            "Harbor Drill",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Harbor Drill",
                    "description_markdown": "A campaign feat that teaches a drilled fighting style.",
                    "modeled_effects": ["Squire of Solamnia"],
                    "optionalfeature_progression": [
                        {
                            "name": "Fighting Style",
                            "featureType": ["FS:F"],
                            "progression": {"1": 1},
                        }
                    ],
                }
            },
        )
    ]

    form_values = {
        "name": "Harbor Guard",
        "character_slug": "harbor-guard",
        "alignment": "Lawful Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
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

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values["species_feat_1"] = _field_value_for_label(context, "species_feat_1", "Harbor Drill")

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    assert _find_builder_field(context, "feat_species_feat_1_optionalfeature_1_1")["label"] == "Harbor Drill Fighting Style"

    form_values["feat_species_feat_1_optionalfeature_1_1"] = "phb-optionalfeature-defense"
    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    feature_names = {feature["name"] for feature in definition.features}
    harbor_drill = next(feature for feature in definition.features if feature["name"] == "Harbor Drill")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "Defense" in feature_names
    assert harbor_drill["page_ref"] == "mechanics/harbor-drill"
    assert harbor_drill["tracker_ref"] == "precise-strike"
    assert resources_by_id["precise-strike"]["max"] == 2
def test_level_one_builder_applies_campaign_feat_expertise_metadata():
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

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
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
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/harbor-savant",
            "Harbor Savant",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Harbor Savant",
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
                }
            },
        )
    ]

    form_values = {
        "name": "Harbor Savant Hero",
        "character_slug": "harbor-savant-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
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

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values["species_feat_1"] = _field_value_for_label(context, "species_feat_1", "Harbor Savant")

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    assert _find_builder_field(context, "feat_species_feat_1_expertise_1")["label"] == "Harbor Savant Expertise"

    form_values.update(
        {
            "feat_species_feat_1_ability_1": _field_value_for_label(
                context,
                "feat_species_feat_1_ability_1",
                "Wisdom",
            ),
            "feat_species_feat_1_skills_1": _field_value_for_label(
                context,
                "feat_species_feat_1_skills_1",
                "Perception",
            ),
            "feat_species_feat_1_expertise_1": _field_value_for_label(
                context,
                "feat_species_feat_1_expertise_1",
                "Perception",
            ),
        }
    )

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(
            systems_service,
            "linden-pass",
            form_values,
            campaign_page_records=campaign_page_records,
        ),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in definition.skills}
    harbor_savant = next(feature for feature in definition.features if feature["name"] == "Harbor Savant")

    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Perception"]["bonus"] == 6
    assert definition.stats["ability_scores"]["wis"]["score"] == 14
    assert definition.stats["passive_perception"] == 16
    assert harbor_savant["page_ref"] == "mechanics/harbor-savant"
def test_level_one_builder_limits_mixed_source_page_options_to_structured_mechanics_pages():
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
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [],
            "background": [],
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
            "species/sea-blessed",
            "Sea-Blessed",
            section="Mechanics",
            subsection="Species",
            metadata={
                "character_option": {
                    "kind": "species",
                    "name": "Sea-Blessed",
                    "size": ["M"],
                    "speed": 35,
                    "feats": [{"any": 1}],
                }
            },
        ),
        _campaign_page_record(
            "backgrounds/harbor-initiate",
            "Harbor Initiate",
            section="Mechanics",
            subsection="Backgrounds",
            metadata={"character_option": {"kind": "background", "name": "Harbor Initiate"}},
        ),
        _campaign_page_record(
            "mechanics/tidecaller-gift",
            "Tidecaller Gift",
            section="Mechanics",
            subsection="Feats",
            metadata={"character_option": {"kind": "feat", "name": "Tidecaller Gift"}},
        ),
        _campaign_page_record(
            "mechanics/blessing-of-the-tide",
            "Blessing of the Tide",
            section="Mechanics",
            subsection="Blessings",
            metadata={"character_option": {"kind": "feat", "name": "Blessing of the Tide"}},
        ),
        _campaign_page_record(
            "items/field-training",
            "Field Training",
            section="Items",
            metadata={"character_option": {"kind": "background", "name": "Field Training"}},
        ),
        _campaign_page_record(
            "species/reefborn",
            "Reefborn",
            section="Lore",
            subsection="Species",
            metadata={"character_option": {"kind": "species", "name": "Reefborn", "size": ["M"], "speed": 30}},
        ),
    ]

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "name": "Maris Vane",
            "character_slug": "maris-vane",
            "alignment": "Neutral Good",
            "experience_model": "Milestone",
            "class_slug": fighter.slug,
            "str": "16",
            "dex": "12",
            "con": "14",
            "int": "10",
            "wis": "12",
            "cha": "8",
        },
        campaign_page_records=campaign_page_records,
    )

    species_labels = {option["label"] for option in context["species_options"]}
    background_labels = {option["label"] for option in context["background_options"]}

    assert any("Sea-Blessed" in label for label in species_labels)
    assert any("Harbor Initiate" in label for label in background_labels)
    assert not any("Reefborn" in label for label in species_labels)
    assert not any("Field Training" in label for label in background_labels)

    form_values = {
        "name": "Maris Vane",
        "character_slug": "maris-vane",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": _option_value_for_label(context["species_options"], "Sea-Blessed"),
        "background_slug": _option_value_for_label(context["background_options"], "Harbor Initiate"),
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "12",
        "cha": "8",
    }
    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    feat_field = _find_builder_field(context, "species_feat_1")
    feat_labels = {option["label"] for option in list(feat_field.get("options") or [])}

    assert any("Tidecaller Gift" in label for label in feat_labels)
    assert not any("Blessing of the Tide" in label for label in feat_labels)
def test_level_one_builder_keeps_non_artificer_tce_classes_outside_tce_first_support_lane():
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
        source_id="PHB",
    )
    swordmage = _systems_entry(
        "class",
        "tce-class-swordmage",
        "Swordmage",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "spellcasting_ability": "int",
            "cantrip_progression": [2, 2],
            "slot_progression": [[{"level": 1, "max_slots": 2}], [{"level": 1, "max_slots": 2}]],
        },
        source_id="TCE",
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        source_id="PHB",
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
            "class": [fighter, swordmage],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
            "feat": [],
            "optionalfeature": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
        enabled_source_ids=["PHB", "TCE"],
    )

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "name": "Lane Guard",
            "character_slug": "lane-guard",
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
            "wis": "11",
            "cha": "8",
        },
    )

    assert any(option["slug"] == fighter.slug for option in context["class_options"])
    assert all(option["slug"] != swordmage.slug for option in context["class_options"])
def test_level_one_builder_supports_enabled_non_phb_species_background_feat_and_subclass_options():
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
        source_id="PHB",
    )
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation"]}}],
            },
        },
        source_id="TCE",
    )
    custom_lineage = _systems_entry(
        "race",
        "tce-race-custom-lineage",
        "Custom Lineage",
        metadata={
            "size": ["M"],
            "speed": 30,
            "languages": [{"common": True}],
            "feats": [{"any": 1}],
        },
        source_id="TCE",
    )
    urban_bounty_hunter = _systems_entry(
        "background",
        "xge-background-urban-bounty-hunter",
        "Urban Bounty Hunter",
        metadata={"skill_proficiencies": [{"insight": True, "persuasion": True}]},
        source_id="XGE",
    )
    telekinetic = _systems_entry("feat", "tce-feat-telekinetic", "Telekinetic", source_id="TCE")
    psi_warrior = _systems_entry(
        "subclass",
        "tce-subclass-psi-warrior",
        "Psi Warrior",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
        source_id="TCE",
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, artificer],
            "race": [custom_lineage],
            "background": [urban_bounty_hunter],
            "feat": [telekinetic],
            "subclass": [psi_warrior],
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
        enabled_source_ids=["PHB", "TCE", "XGE"],
    )
    form_values = {
        "name": "Mixed Source Hero",
        "character_slug": "mixed-source-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": custom_lineage.slug,
        "background_slug": urban_bounty_hunter.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": telekinetic.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, import_metadata = build_level_one_character_definition("linden-pass", context, form_values)

    species_feat_field = _find_builder_field(context, "species_feat_1")

    assert [option["slug"] for option in context["class_options"]] == [artificer.slug, fighter.slug]
    assert context["selected_class"].slug == fighter.slug
    assert any(
        option["slug"] == custom_lineage.slug and option["label"] == "Custom Lineage (TCE)"
        for option in context["species_options"]
    )
    assert any(
        option["slug"] == urban_bounty_hunter.slug and option["label"] == "Urban Bounty Hunter (XGE)"
        for option in context["background_options"]
    )
    assert any(
        option["slug"] == psi_warrior.slug and option["label"] == "Psi Warrior (TCE)"
        for option in context["subclass_options"]
    )
    assert any(
        option["value"] == f"systems:{telekinetic.slug}" and option["label"] == "Telekinetic (TCE)"
        for option in species_feat_field["options"]
    )
    assert definition.profile["species_ref"]["source_id"] == "TCE"
    assert definition.profile["background_ref"]["source_id"] == "XGE"
    assert any(feature["name"] == "Telekinetic" for feature in definition.features)
    assert import_metadata.source_path == "builder://native-level-1"
def test_level_one_builder_supports_enabled_dmg_subclass_options_while_sidekick_classes_stay_blocked():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Divine Domain",
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["history", "insight", "medicine", "religion"]}}],
            },
        },
        source_id="PHB",
    )
    expert_sidekick = _systems_entry(
        "class",
        "tce-class-expert-sidekick",
        "Expert Sidekick",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "cha"]},
        source_id="TCE",
    )
    death_domain = _systems_entry(
        "subclass",
        "dmg-subclass-cleric-death-domain",
        "Death Domain",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
        source_id="DMG",
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    divine_domain = _systems_entry("classfeature", "phb-classfeature-divine-domain", "Divine Domain", metadata={"level": 1})
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry(
        "spell",
        "phb-spell-sacred-flame",
        "Sacred Flame",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    thaumaturgy = _systems_entry(
        "spell",
        "phb-spell-thaumaturgy",
        "Thaumaturgy",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    healing_word = _systems_entry(
        "spell",
        "phb-spell-healing-word",
        "Healing Word",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1},
    )
    shield_of_faith = _systems_entry(
        "spell",
        "phb-spell-shield-of-faith",
        "Shield of Faith",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [cleric, expert_sidekick],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [death_domain],
            "item": [],
            "spell": [light, sacred_flame, thaumaturgy, bless, cure_wounds, healing_word, shield_of_faith],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Divine Domain", "entry": divine_domain, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        enabled_source_ids=["PHB", "DMG", "TCE"],
    )
    form_values = {
        "name": "Mournwell",
        "character_slug": "mournwell",
        "alignment": "Neutral Evil",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": death_domain.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "history",
        "class_skill_2": "medicine",
        "str": "10",
        "dex": "12",
        "con": "14",
        "int": "11",
        "wis": "16",
        "cha": "13",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)

    assert any(
        option["slug"] == death_domain.slug and option["label"] == "Death Domain (DMG)"
        for option in context["subclass_options"]
    )
    assert context["selected_subclass"].slug == death_domain.slug
    assert all(option["slug"] != expert_sidekick.slug for option in context["class_options"])
def test_level_one_builder_surfaces_and_applies_skilled_feat_choices():
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
    skilled = _systems_entry(
        "feat",
        "phb-feat-skilled",
        "Skilled",
        metadata={
            "skill_tool_language_proficiencies": [
                {
                    "choose": [
                        {
                            "from": ["anySkill", "anyTool"],
                            "count": 3,
                        }
                    ]
                }
            ]
        },
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [skilled],
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
        "name": "Skill Hero",
        "character_slug": "skill-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": skilled.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_skill_tool_language_1")["label"] == "Skilled Choice 1"

    form_values.update(
        {
            "feat_species_feat_1_skill_tool_language_1": _field_value_for_label(
                context,
                "feat_species_feat_1_skill_tool_language_1",
                "Skill: Acrobatics",
            ),
            "feat_species_feat_1_skill_tool_language_2": _field_value_for_label(
                context,
                "feat_species_feat_1_skill_tool_language_2",
                "Skill: Perception",
            ),
            "feat_species_feat_1_skill_tool_language_3": _field_value_for_label(
                context,
                "feat_species_feat_1_skill_tool_language_3",
                "Tool: Thieves' Tools",
            ),
        }
    )

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(systems_service, "linden-pass", form_values),
        form_values,
    )

    proficient_skill_names = {
        skill["name"] for skill in definition.skills if skill.get("proficiency_level") == "proficient"
    }
    feature_names = {feature["name"] for feature in definition.features}

    assert {"Acrobatics", "Perception"} <= proficient_skill_names
    assert "Thieves' Tools" in definition.proficiencies["tools"]
    assert "Skilled" in feature_names
def test_level_one_builder_surfaces_and_applies_skill_expert_feat_expertise():
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
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [skill_expert],
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
        "name": "Expert Hero",
        "character_slug": "expert-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": skill_expert.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_expertise_1")["label"] == "Skill Expert Expertise"

    form_values.update(
        {
            "feat_species_feat_1_ability_1": _field_value_for_label(
                context,
                "feat_species_feat_1_ability_1",
                "Wisdom",
            ),
            "feat_species_feat_1_skills_1": _field_value_for_label(
                context,
                "feat_species_feat_1_skills_1",
                "Perception",
            ),
            "feat_species_feat_1_expertise_1": _field_value_for_label(
                context,
                "feat_species_feat_1_expertise_1",
                "Perception",
            ),
        }
    )

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(systems_service, "linden-pass", form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in definition.skills}
    feature_names = {feature["name"] for feature in definition.features}

    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Perception"]["bonus"] == 6
    assert definition.stats["ability_scores"]["wis"]["score"] == 14
    assert definition.stats["passive_perception"] == 16
    assert "Skill Expert" in feature_names
def test_level_one_builder_surfaces_and_applies_rogue_expertise_class_feature():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["dex", "int"],
            "starting_proficiencies": {
                "tools": ["Thieves' Tools"],
                "skills": [
                    {
                        "choose": {
                            "count": 4,
                            "from": [
                                "acrobatics",
                                "athletics",
                                "deception",
                                "insight",
                                "intimidation",
                                "investigation",
                                "perception",
                                "performance",
                                "persuasion",
                                "sleight of hand",
                                "stealth",
                            ],
                        }
                    }
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
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    expertise = _systems_entry(
        "classfeature",
        "phb-classfeature-expertise-rogue-phb-1",
        "Expertise",
        metadata={"class_name": "Rogue", "class_source": "PHB", "level": 1},
        body={
            "entries": [
                "At 1st level, choose two of your skill proficiencies, or one of your skill proficiencies and your proficiency with thieves' tools.",
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
                    "level": 1,
                    "level_label": "Level 1",
                    "feature_rows": [_progression_row("Expertise", entry=expertise)],
                }
            ]
        },
    )

    form_values = {
        "name": "Rook Vale",
        "character_slug": "rook-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": rogue.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "acrobatics",
        "class_skill_2": "investigation",
        "class_skill_3": "perception",
        "class_skill_4": "stealth",
        "str": "10",
        "dex": "16",
        "con": "12",
        "int": "14",
        "wis": "12",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    first_expertise_field = _field_name_for_label(context, "Rogue Expertise 1")
    second_expertise_field = _field_name_for_label(context, "Rogue Expertise 2")
    form_values[first_expertise_field] = _field_value_for_label(context, first_expertise_field, "Perception")
    form_values[second_expertise_field] = _field_value_for_label(context, second_expertise_field, "Stealth")

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(systems_service, "linden-pass", form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in definition.skills}
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Stealth"]["proficiency_level"] == "expertise"
    assert skills_by_name["Investigation"]["proficiency_level"] == "proficient"
def test_level_one_builder_applies_rogue_expertise_to_thieves_tools():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["dex", "int"],
            "starting_proficiencies": {
                "tools": ["Thieves' Tools"],
                "skills": [
                    {
                        "choose": {
                            "count": 4,
                            "from": [
                                "acrobatics",
                                "athletics",
                                "deception",
                                "insight",
                                "intimidation",
                                "investigation",
                                "perception",
                                "performance",
                                "persuasion",
                                "sleight of hand",
                                "stealth",
                            ],
                        }
                    }
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
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    expertise = _systems_entry(
        "classfeature",
        "phb-classfeature-expertise-rogue-phb-1",
        "Expertise",
        metadata={"class_name": "Rogue", "class_source": "PHB", "level": 1},
        body={
            "entries": [
                "At 1st level, choose two of your skill proficiencies, or one of your skill proficiencies and your proficiency with thieves' tools.",
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
                    "level": 1,
                    "level_label": "Level 1",
                    "feature_rows": [_progression_row("Expertise", entry=expertise)],
                }
            ]
        },
    )

    form_values = {
        "name": "Rook Vale",
        "character_slug": "rook-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": rogue.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "acrobatics",
        "class_skill_2": "investigation",
        "class_skill_3": "perception",
        "class_skill_4": "stealth",
        "str": "10",
        "dex": "16",
        "con": "12",
        "int": "14",
        "wis": "12",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    first_expertise_field = _field_name_for_label(context, "Rogue Expertise 1")
    second_expertise_field = _field_name_for_label(context, "Rogue Expertise 2")
    form_values[first_expertise_field] = _field_value_for_label(context, first_expertise_field, "Perception")
    form_values[second_expertise_field] = _field_value_for_label(context, second_expertise_field, "Thieves' Tools")

    definition, _ = build_level_one_character_definition(
        "linden-pass",
        build_level_one_builder_context(systems_service, "linden-pass", form_values),
        form_values,
    )

    skills_by_name = {skill["name"]: skill for skill in definition.skills}
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert any(tool.casefold() == "thieves' tools" for tool in definition.proficiencies["tools"])
    assert any(tool.casefold() == "thieves' tools" for tool in definition.proficiencies.get("tool_expertise") or [])
def test_level_one_builder_updates_background_preview_and_preserves_valid_class_choices_after_background_change():
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
                "skills": [{"choose": {"count": 1, "from": ["athletics", "history"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"a": ["longsword|phb"], "b": ["handaxe|phb"]},
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
        metadata={
            "skill_proficiencies": [{"insight": True, "religion": True}],
            "language_proficiencies": [{"anyStandard": 1}],
            "starting_equipment": [{"_": ["holy symbol|phb"]}],
        },
    )
    hermit = _systems_entry(
        "background",
        "phb-background-hermit",
        "Hermit",
        metadata={
            "skill_proficiencies": [{"medicine": True, "religion": True}],
            "tool_proficiencies": ["Herbalism Kit"],
            "starting_equipment": [{"_": ["herbalism kit|phb"]}],
        },
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword")
    handaxe = _systems_entry("item", "phb-item-handaxe", "Handaxe")
    holy_symbol = _systems_entry("item", "phb-item-holy-symbol", "Holy Symbol")
    herbalism_kit = _systems_entry("item", "phb-item-herbalism-kit", "Herbalism Kit")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte, hermit],
            "feat": [],
            "subclass": [],
            "item": [longsword, handaxe, holy_symbol, herbalism_kit],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form = {
        "name": "Shifted Pilgrim",
        "character_slug": "shifted-pilgrim",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "background_language_1": "Elvish",
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    base_context = build_level_one_builder_context(systems_service, "linden-pass", base_form)
    base_form["class_equipment_1"] = _field_value_for_label(base_context, "class_equipment_1", "Longsword")
    switched_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            **base_form,
            "background_slug": hermit.slug,
        },
    )

    assert "background_language_1" not in _builder_field_names(switched_context)
    assert switched_context["values"].get("background_language_1", "") == ""
    assert switched_context["values"].get("class_equipment_1", "") == base_form["class_equipment_1"]
    assert switched_context["preview"]["background"] == "Hermit"
    assert "Longsword" in switched_context["preview"]["equipment"]
    assert "Herbalism Kit" in switched_context["preview"]["equipment"]
    assert "Holy Symbol" not in switched_context["preview"]["equipment"]
def test_level_one_builder_applies_gift_of_the_gem_dragon_tracker():
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
    gift_of_the_gem_dragon = _systems_entry(
        "feat",
        "ftd-feat-gift-of-the-gem-dragon",
        "Gift of the Gem Dragon",
        source_id="FTD",
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [gift_of_the_gem_dragon],
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
        "name": "Gem Hero",
        "character_slug": "gem-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": gift_of_the_gem_dragon.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    gem_feature = next(feature for feature in definition.features if feature["name"] == "Gift of the Gem Dragon")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "Telekinetic Reprisal: 2 / 2 (Long Rest)" in context["preview"]["resources"]
    assert gem_feature["tracker_ref"] == "telekinetic-reprisal"
    assert resources_by_id["telekinetic-reprisal"]["max"] == 2
    assert resources_by_id["telekinetic-reprisal"]["reset_on"] == "long_rest"
def test_level_one_builder_applies_gift_of_the_chromatic_dragon_trackers():
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
    gift_of_the_chromatic_dragon = _systems_entry(
        "feat",
        "ftd-feat-gift-of-the-chromatic-dragon",
        "Gift of the Chromatic Dragon",
        source_id="FTD",
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [gift_of_the_chromatic_dragon],
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
        "name": "Iris Scale",
        "character_slug": "iris-scale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": gift_of_the_chromatic_dragon.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    feature_names = {feature["name"] for feature in definition.features}
    features_by_name = {feature["name"]: feature for feature in definition.features}
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "Gift of the Chromatic Dragon" in context["preview"]["features"]
    assert "Gift of the Chromatic Dragon: Chromatic Infusion" in context["preview"]["features"]
    assert "Gift of the Chromatic Dragon: Reactive Resistance" in context["preview"]["features"]
    assert "Chromatic Infusion: 1 / 1 (Long Rest)" in context["preview"]["resources"]
    assert "Reactive Resistance: 2 / 2 (Long Rest)" in context["preview"]["resources"]
    assert {
        "Gift of the Chromatic Dragon",
        "Gift of the Chromatic Dragon: Chromatic Infusion",
        "Gift of the Chromatic Dragon: Reactive Resistance",
    } <= feature_names
    assert not features_by_name["Gift of the Chromatic Dragon"].get("tracker_ref")
    assert features_by_name["Gift of the Chromatic Dragon: Chromatic Infusion"]["tracker_ref"] == "chromatic-infusion"
    assert features_by_name["Gift of the Chromatic Dragon: Reactive Resistance"]["tracker_ref"] == "reactive-resistance"
    assert resources_by_id["chromatic-infusion"]["max"] == 1
    assert resources_by_id["reactive-resistance"]["max"] == 2
@pytest.mark.parametrize(
    ("feat_name", "feat_slug", "tracker_id", "preview_label", "activation_type"),
    _SINGLE_TRACKER_FEAT_CASES,
)
def test_level_one_builder_applies_single_use_short_rest_feat_trackers(
    feat_name: str,
    feat_slug: str,
    tracker_id: str,
    preview_label: str,
    activation_type: str,
):
    systems_service, form_values = _build_single_tracker_feat_level_one_fixture(feat_name, feat_slug)

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    feat_feature = next(feature for feature in definition.features if feature["name"] == feat_name)
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert preview_label in context["preview"]["resources"]
    assert feat_feature["tracker_ref"] == tracker_id
    assert feat_feature["activation_type"] == activation_type
    assert resources_by_id[tracker_id]["max"] == 1
    assert resources_by_id[tracker_id]["reset_on"] == "short_rest"
def test_level_one_builder_applies_alert_feat_to_initiative():
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
    alert = _systems_entry("feat", "phb-feat-alert", "Alert")
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [alert],
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
        "name": "Alert Hero",
        "character_slug": "alert-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": alert.slug,
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

    assert definition.stats["initiative_bonus"] == 6
def test_level_one_builder_applies_structured_save_bonus_effect_keys():
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
    battle_resilience = _systems_entry(
        "classfeature",
        "phb-classfeature-battle-resilience",
        "Battle Resilience",
        metadata={
            "level": 1,
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
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Second Wind", "entry": second_wind, "embedded_card": {"option_groups": []}},
                    {"label": "Battle Resilience", "entry": battle_resilience, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Resilient Recruit",
        "character_slug": "resilient-recruit",
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

    assert definition.stats["ability_scores"]["str"]["save_bonus"] == 7
    assert definition.stats["ability_scores"]["dex"]["save_bonus"] == 3
    assert definition.stats["ability_scores"]["wis"]["save_bonus"] == 4
    assert definition.stats["ability_scores"]["cha"]["save_bonus"] == 2
def test_native_builder_and_level_up_support_non_phb_artificer_progression():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "tools": ["thieves' tools", "tinker's tools"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "medicine"]}}],
            },
            "spellcasting_ability": "int",
            "caster_progression": "artificer",
            "prepared_spells": "<$level$> / 2 + <$int_mod$>",
            "cantrip_progression": [2, 2, 2, 2],
            "slot_progression": [
                [{"level": 1, "max_slots": 2}],
                [{"level": 1, "max_slots": 2}],
                [{"level": 1, "max_slots": 3}],
                [{"level": 1, "max_slots": 3}],
            ],
        },
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
    )
    sage = _systems_entry(
        "background",
        "phb-background-sage",
        "Sage",
        metadata={"skill_proficiencies": [{"arcana": True, "history": True}]},
    )
    magical_tinkering = _systems_entry(
        "classfeature",
        "tce-classfeature-magical-tinkering",
        "Magical Tinkering",
        source_id="TCE",
        metadata={"level": 1},
    )
    spellcasting = _systems_entry(
        "classfeature",
        "tce-classfeature-spellcasting",
        "Spellcasting",
        source_id="TCE",
        metadata={"level": 1},
    )
    infuse_item = _systems_entry(
        "classfeature",
        "tce-classfeature-infuse-item",
        "Infuse Item",
        source_id="TCE",
        metadata={"level": 2},
    )
    guidance = _systems_entry(
        "spell",
        "tce-spell-guidance",
        "Guidance",
        source_id="TCE",
        metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}},
    )
    mending = _systems_entry(
        "spell",
        "phb-spell-mending",
        "Mending",
        source_id="PHB",
        metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}},
    )
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        source_id="PHB",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        source_id="PHB",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    faerie_fire = _systems_entry(
        "spell",
        "phb-spell-faerie-fire",
        "Faerie Fire",
        source_id="PHB",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    grease = _systems_entry(
        "spell",
        "phb-spell-grease",
        "Grease",
        source_id="PHB",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "race": [human],
            "background": [sage],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [guidance, mending, cure_wounds, detect_magic, faerie_fire, grease],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Magical Tinkering", "entry": magical_tinkering, "embedded_card": {"option_groups": []}},
                    {"label": "Spellcasting", "entry": spellcasting, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Infuse Item", "entry": infuse_item, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
        enabled_source_ids=["PHB", "TCE"],
    )

    form_values = {
        "name": "Copper Finch",
        "character_slug": "copper-finch",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": artificer.slug,
        "species_slug": human.slug,
        "background_slug": sage.slug,
        "class_skill_1": "investigation",
        "class_skill_2": "medicine",
        "str": "8",
        "dex": "14",
        "con": "13",
        "int": "16",
        "wis": "12",
        "cha": "10",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)

    assert any(option["slug"] == artificer.slug for option in context["class_options"])
    assert _field_value_for_label(context, "spell_cantrip_1", "Guidance")
    assert _field_value_for_label(context, "spell_level_one_1", "Cure Wounds")

    form_values = {
        **form_values,
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Guidance"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Mending"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Cure Wounds"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Detect Magic"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Faerie Fire"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    assert definition.profile["class_level_text"] == "Artificer 1"
    assert definition.spellcasting["spellcasting_class"] == "Artificer"
    assert definition.spellcasting["spellcasting_ability"] == "Intelligence"
    assert definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 2}]
    assert supports_native_level_up(definition) is True

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {"hp_gain": "5"},
    )

    assert level_up_context["next_level"] == 2
    assert any(
        field["name"] == "levelup_prepared_spell_1"
        for section in level_up_context["choice_sections"]
        for field in section["fields"]
    )

    level_up_values = {
        "hp_gain": "5",
        "levelup_prepared_spell_1": _field_value_for_label(level_up_context, "levelup_prepared_spell_1", "Grease"),
    }
    leveled_definition, _, hp_gain = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        level_up_context,
        level_up_values,
    )

    feature_names = {feature["name"] for feature in leveled_definition.features}
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert hp_gain == 5
    assert leveled_definition.profile["class_level_text"] == "Artificer 2"
    assert "Infuse Item" in feature_names
    assert leveled_definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 2}]
    assert spells_by_name["Grease"]["mark"] == "Prepared"
def test_level_one_builder_applies_war_priest_tracker_from_level_one_subclass():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Divine Domain",
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["history", "insight", "medicine", "religion"]}}],
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
    war_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-war-domain",
        "War Domain",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
    )
    divine_domain = _systems_entry(
        "classfeature",
        "phb-classfeature-divine-domain",
        "Divine Domain",
        metadata={"level": 1},
    )
    war_priest = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-war-priest",
        "War Priest",
        metadata={"level": 1, "class_name": "Cleric", "class_source": "PHB", "subclass_name": "War Domain"},
    )
    guidance = _systems_entry("spell", "phb-spell-guidance", "Guidance", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    sacred_flame = _systems_entry(
        "spell",
        "phb-spell-sacred-flame",
        "Sacred Flame",
        metadata={"casting_time": [{"number": 1, "unit": "action"}]},
    )
    thaumaturgy = _systems_entry(
        "spell",
        "phb-spell-thaumaturgy",
        "Thaumaturgy",
        metadata={"casting_time": [{"number": 1, "unit": "action"}]},
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}]},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [war_domain],
            "item": [],
            "spell": [guidance, sacred_flame, thaumaturgy, bless, cure_wounds],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Divine Domain", "entry": divine_domain, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "War Priest", "entry": war_priest, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    form_values = {
        "name": "Sister Arden",
        "character_slug": "sister-arden",
        "alignment": "Lawful Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": war_domain.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "history",
        "class_skill_2": "medicine",
        "str": "12",
        "dex": "10",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "15",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    form_values = {
        **form_values,
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Guidance"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Bless"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Cure Wounds"),
    }
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    war_priest_feature = next(feature for feature in definition.features if feature["name"] == "War Priest")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "War Priest: 1 / 1 (Long Rest)" in context["preview"]["resources"]
    assert war_priest_feature["tracker_ref"] == "war-priest"
    assert resources_by_id["war-priest"]["max"] == 1
    assert resources_by_id["war-priest"]["reset_on"] == "long_rest"
def test_dm_roster_shows_create_character_link(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/new" in html
    assert "Create character" in html
def test_dm_can_open_character_builder_page_without_systems_data(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/new")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Native Level 1 Builder" in html
    assert "The builder needs a supported base class plus enabled Systems species and backgrounds" in html
def test_builder_enabled_entries_use_bulk_helper_and_request_cache(app):
    fighter = _systems_entry("feat", "fighting-initiate", "Fighting Initiate")
    disabled_feat = _systems_entry("feat", "shadow-touched", "Shadow Touched")
    systems_service = _FakeSystemsService(
        {"feat": [fighter, disabled_feat]},
        class_progression=[],
        disabled_entry_keys=[disabled_feat.entry_key],
    )

    with app.test_request_context("/campaigns/linden-pass/characters/new"):
        entries = _list_campaign_enabled_entries(systems_service, "linden-pass", "feat")
        repeated_entries = _list_campaign_enabled_entries(systems_service, "linden-pass", "feat")

    assert [entry.slug for entry in entries] == ["fighting-initiate"]
    assert [entry.slug for entry in repeated_entries] == ["fighting-initiate"]
    assert systems_service.list_enabled_entries_calls == [("linden-pass", "feat", "", None)]
    assert systems_service.list_entries_for_campaign_source_calls == 0
    assert systems_service.is_entry_enabled_calls == 0
def test_builder_static_bundle_cache_uses_source_and_page_revisions():
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
            "subclass": [],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "optionalfeature": [],
            "item": [],
            "spell": [],
        },
        class_progression=[],
    )
    page_record = _campaign_page_record(
        "mechanics/page-feat",
        "Page Feat",
        section="Mechanics",
        metadata={"character_option": {"kind": "feat", "name": "Page Feat"}},
    )
    page_record.updated_at = "2026-04-24T12:00:00+00:00"
    form_values = {
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
    }
    expected_static_entry_types = [
        "class",
        "subclass",
        "race",
        "background",
        "feat",
        "optionalfeature",
        "item",
        "spell",
    ]

    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert [call[1] for call in systems_service.list_enabled_entries_calls] == expected_static_entry_types

    page_record.updated_at = "2026-04-24T12:05:00+00:00"
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert [call[1] for call in systems_service.list_enabled_entries_calls] == expected_static_entry_types * 2

    systems_service.static_revision_token = "v2"
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert [call[1] for call in systems_service.list_enabled_entries_calls] == expected_static_entry_types * 3
def test_builder_progression_cache_uses_source_and_page_revisions():
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
            "subclass": [],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "optionalfeature": [],
            "item": [],
            "spell": [],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "1st Level",
                "feature_rows": [_progression_row("Second Wind")],
            }
        ],
    )
    page_record = _campaign_page_record("mechanics/fighter-training", "Fighter Training", section="Mechanics")
    page_record.updated_at = "2026-04-24T12:00:00+00:00"
    form_values = {
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
    }

    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert systems_service.class_progression_calls == 1

    page_record.updated_at = "2026-04-24T12:05:00+00:00"
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert systems_service.class_progression_calls == 2

    systems_service.static_revision_token = "v2"
    build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=[page_record],
    )

    assert systems_service.class_progression_calls == 3
def test_choice_section_stabilizer_rebuilds_after_stale_values_drop():
    build_calls = 0

    def build_sections(values: dict[str, str]) -> list[dict[str, object]]:
        nonlocal build_calls
        build_calls += 1
        return [
            {
                "title": "Choices",
                "fields": [
                    {
                        "name": "known_choice",
                        "label": "Known Choice",
                        "options": [{"value": "alpha", "label": "Alpha"}],
                        "selected": str(values.get("known_choice") or "").strip(),
                    }
                ],
            }
        ]

    values, sections = _stabilize_choice_section_values(
        {
            "name": "Preview Hero",
            "known_choice": "alpha",
            "stale_choice": "removed",
        },
        static_keys=frozenset({"name"}),
        build_sections=build_sections,
    )

    assert values == {"name": "Preview Hero", "known_choice": "alpha"}
    assert sections[0]["fields"][0]["selected"] == "alpha"
    assert build_calls == 2
def test_build_level_one_builder_context_marks_choice_fields_with_live_preview_regions():
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
        metadata={"feats": [{"any": 1}]},
    )
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    archery = _systems_entry("feat", "phb-feat-archery", "Archery")
    defense = _systems_entry("feat", "phb-feat-defense", "Defense")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [archery, defense],
        },
        class_progression=[
            {
                "level": 1,
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Archery", "slug": archery.slug},
                                        {"label": "Defense", "slug": defense.slug},
                                    ]
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    )

    builder_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "class_slug": fighter.slug,
            "species_slug": human.slug,
            "background_slug": acolyte.slug,
        },
    )

    class_option_field = _find_builder_field(builder_context, "class_option_1")
    species_feat_field = _find_builder_field(builder_context, "species_feat_1")

    _assert_live_preview_metadata(
        builder_context["field_live_preview"]["class_slug"],
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-equipment,preview-attacks",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        builder_context["field_live_preview"]["str"],
        trigger="input",
        regions="preview-summary,preview-spells,preview-attacks",
        debounce_ms=650,
    )
    _assert_live_preview_metadata(
        class_option_field,
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-equipment,preview-attacks",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        species_feat_field,
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-equipment,preview-attacks",
        debounce_ms=120,
    )
def test_build_level_one_builder_context_assigns_targeted_live_preview_regions_for_representative_field_families():
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
                "skills": [{"choose": {"count": 1, "from": ["athletics", "history"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"a": ["longsword|phb"], "b": ["handaxe|phb"]},
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
        metadata={
            "skill_proficiencies": [{"insight": True, "religion": True}],
            "language_proficiencies": [{"anyStandard": 1}],
        },
    )
    archery = _systems_entry("feat", "phb-feat-archery", "Archery")
    defense = _systems_entry("feat", "phb-feat-defense", "Defense")
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
    longsword = _systems_entry("item", "phb-item-longsword", "Longsword")
    handaxe = _systems_entry("item", "phb-item-handaxe", "Handaxe")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [archery, defense, magic_initiate],
            "subclass": [],
            "item": [longsword, handaxe],
            "spell": [guidance, cure_wounds],
        },
        class_progression=[
            {
                "level": 1,
                "feature_rows": [
                    {
                        "label": "Fighting Style",
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Archery", "slug": archery.slug},
                                        {"label": "Defense", "slug": defense.slug},
                                    ]
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/arcane-overload",
            "Arcane Overload",
            section="Mechanics",
            subsection="Boons",
            metadata={
                "character_option": {
                    "kind": "feature",
                    "name": "Arcane Overload",
                    "proficiencies": {"weapons": ["martial"]},
                    "resource": {"label": "Arcane Overload", "max": 1, "reset_on": "long_rest"},
                    "spell_support": [
                        {"choices": {"1": [{"category": "known", "filter": "level=0|class=Cleric", "count": 1}]}}
                    ],
                    "modeled_effects": ["effect:attack-mode:melee:arcane-overload"],
                }
            },
        ),
        _campaign_page_record(
            "items/stormglass-compass",
            "Stormglass Compass",
            section="Items",
            subsection="Wondrous Items",
            metadata={
                "character_option": {
                    "kind": "item",
                    "name": "Stormglass Compass",
                    "spells": [{"value": guidance.slug, "mark": "Granted"}],
                }
            },
        ),
    ]

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "class_slug": fighter.slug,
            "species_slug": variant_human.slug,
            "background_slug": acolyte.slug,
            "species_feat_1": magic_initiate.slug,
        },
        campaign_page_records=campaign_page_records,
    )

    _assert_live_preview_metadata(
        context["field_live_preview"]["background_slug"],
        trigger="change",
        regions="choice-sections,preview-summary,preview-spells,preview-equipment,preview-attacks",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "species_language_1"),
        trigger="change",
        regions="preview-summary",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "class_equipment_1"),
        trigger="change",
        regions="preview-summary,preview-equipment,preview-attacks",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "feat_species_feat_1_spell_known_1_1"),
        trigger="change",
        regions="preview-spells",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "campaign_feature_page_ref_1"),
        trigger="change",
        regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks",
        debounce_ms=120,
    )
    _assert_live_preview_metadata(
        _find_builder_field(context, "campaign_item_page_ref_1"),
        trigger="change",
        regions="preview-summary,preview-equipment,preview-attacks,preview-spells",
        debounce_ms=120,
    )
def test_character_builder_live_preview_route_returns_fragment(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())

    response = client.get("/campaigns/linden-pass/characters/new?_live_preview=1&class_slug=phb-class-fighter")

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
def test_character_builder_live_preview_route_returns_requested_regions_only(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())

    response = client.get(
        "/campaigns/linden-pass/characters/new?_live_preview=1&regions=choice-sections,preview-summary&class_slug=phb-class-fighter"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data-live-builder-root" not in html
    assert 'data-live-builder-region="choice-sections"' in html
    assert 'data-live-builder-region="preview-summary"' in html
    assert 'data-live-builder-region="preview-features"' not in html
def test_character_builder_page_renders_top_level_live_preview_metadata(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())

    response = client.get("/campaigns/linden-pass/characters/new")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-live-builder-root' in html
    assert 'data-loading="0"' in html
    assert "window.__playerWikiLiveUiTools" in html
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in html
    assert 'name="name"' in html
    assert 'data-live-preview-trigger="blur"' in html
    assert 'data-live-preview-regions=""' in html
    assert 'data-live-preview-debounce-ms="0"' in html
    assert 'name="class_slug"' in html
    assert 'data-live-preview-regions="choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-equipment,preview-attacks"' in html
    assert 'name="str"' in html
    assert 'data-live-preview-trigger="input"' in html
    assert 'data-live-preview-regions="preview-summary,preview-spells,preview-attacks"' in html
    assert 'data-live-preview-debounce-ms="650"' in html
    assert "function cancelActivePreview()" in html
    assert "cancelActivePreview();" in html
    assert "if (requestId === activeRequestId)" in html
def test_character_builder_loading_styles_do_not_dim_live_builder_surfaces():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert "live-builder-root][data-loading" not in css
def test_character_builder_route_passes_only_builder_relevant_campaign_pages_into_builder(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    captured_page_refs: list[str] = []

    def _fake_builder_context(_systems_service, _campaign_slug, form_values=None, *, campaign_page_records=None):
        del form_values
        captured_page_refs.extend(
            str(getattr(record, "page_ref", "") or "").strip()
            for record in list(campaign_page_records or [])
        )
        return _builder_context_fixture()

    monkeypatch.setattr(app_module, "build_level_one_builder_context", _fake_builder_context)

    response = client.get("/campaigns/linden-pass/characters/new")

    assert response.status_code == 200
    assert "items/stormglass-compass" in captured_page_refs
    assert "mechanics/arcane-overload" in captured_page_refs
    assert all(
        page_ref.startswith("mechanics/") or page_ref.startswith("items/")
        for page_ref in captured_page_refs
        if page_ref
    )
def test_level_up_route_passes_only_builder_relevant_campaign_pages_into_builder(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    captured_page_refs: list[str] = []

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    def _capture_page_refs(_systems_service, _campaign_slug, _definition, *, campaign_page_records=None, **_kwargs):
        captured_page_refs.extend(
            str(getattr(record, "page_ref", "") or "").strip()
            for record in list(campaign_page_records or [])
        )
        return {"status": "ready", "message": "", "reasons": []}

    monkeypatch.setattr(app_module, "native_level_up_readiness", _capture_page_refs)
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )

    response = client.get("/campaigns/linden-pass/characters/leveler/level-up")

    assert response.status_code == 200
    assert "items/stormglass-compass" in captured_page_refs
    assert "mechanics/arcane-overload" in captured_page_refs
    assert all(
        page_ref.startswith("mechanics/") or page_ref.startswith("items/")
        for page_ref in captured_page_refs
        if page_ref
    )
def test_non_manager_cannot_open_character_builder_page(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/new")

    assert response.status_code == 403
def test_dm_can_create_character_from_builder_route(app, client, sign_in, users, get_character, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())
    monkeypatch.setattr(
        app_module,
        "build_level_one_character_definition",
        lambda *args, **kwargs: (_minimal_character_definition(), _minimal_import_metadata()),
    )

    response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "New Hero", "character_slug": "new-hero"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/new-hero")

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "new-hero" / "definition.yaml"
    )
    import_path = (
        app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "new-hero" / "import.yaml"
    )
    assert definition_path.exists()
    assert import_path.exists()

    record = get_character("new-hero")
    assert record is not None
    assert record.definition.name == "New Hero"
    assert record.state_record.state["vitals"]["current_hp"] == 12
def test_xianxia_milestone1_dnd5e_native_create_level_up_and_repair_routes_remain_dnd5e(
    app, client, sign_in, users, get_character, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    route_calls = {"create": 0, "level_up": 0, "repair": 0}

    monkeypatch.setattr(
        app_module,
        "build_level_one_builder_context",
        lambda *args, **kwargs: _builder_context_fixture(),
    )

    def _build_dnd_character(*args, **kwargs):
        route_calls["create"] += 1
        return _minimal_character_definition("milestone-dnd-hero", "Milestone DND Hero"), _minimal_import_metadata(
            "milestone-dnd-hero"
        )

    monkeypatch.setattr(app_module, "build_level_one_character_definition", _build_dnd_character)

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Milestone DND Hero", "character_slug": "milestone-dnd-hero"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/milestone-dnd-hero"
    )
    assert route_calls["create"] == 1
    created_payload = yaml.safe_load(
        (
            app.config["TEST_CAMPAIGNS_DIR"]
            / "linden-pass"
            / "characters"
            / "milestone-dnd-hero"
            / "definition.yaml"
        ).read_text(encoding="utf-8")
    )
    assert created_payload["system"] == "DND-5E"
    assert "xianxia" not in created_payload
    assert created_payload["source"]["source_type"] == "native_character_builder"
    assert get_character("milestone-dnd-hero").state_record.state["vitals"]["current_hp"] == 12

    leveler_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "milestone-leveler"
    leveler_dir.mkdir(parents=True, exist_ok=True)
    leveler_definition = _minimal_character_definition("milestone-leveler", "Milestone Leveler")
    (leveler_dir / "definition.yaml").write_text(
        yaml.safe_dump(leveler_definition.to_dict(), sort_keys=False),
        encoding="utf-8",
    )
    (leveler_dir / "import.yaml").write_text(
        yaml.safe_dump(_minimal_import_metadata("milestone-leveler").to_dict(), sort_keys=False),
        encoding="utf-8",
    )
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
    leveled_definition = _minimal_character_definition("milestone-leveler", "Milestone Leveler")
    leveled_definition.profile["class_level_text"] = "Fighter 2"
    leveled_definition.profile["classes"][0]["level"] = 2
    leveled_definition.stats["max_hp"] = 20
    leveled_import = _minimal_import_metadata("milestone-leveler")
    leveled_import.source_path = "builder://native-level-2"

    def _build_dnd_level_up(*args, **kwargs):
        route_calls["level_up"] += 1
        return leveled_definition, leveled_import, 8

    monkeypatch.setattr(app_module, "build_native_level_up_character_definition", _build_dnd_level_up)

    level_up_response = client.post(
        "/campaigns/linden-pass/characters/milestone-leveler/level-up",
        data={"expected_revision": "1", "hp_gain": "8"},
        follow_redirects=False,
    )

    assert level_up_response.status_code == 302
    assert level_up_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/milestone-leveler"
    )
    assert route_calls["level_up"] == 1
    level_up_payload = yaml.safe_load((leveler_dir / "definition.yaml").read_text(encoding="utf-8"))
    assert level_up_payload["system"] == "DND-5E"
    assert "xianxia" not in level_up_payload
    assert level_up_payload["profile"]["class_level_text"] == "Fighter 2"
    assert yaml.safe_load((leveler_dir / "import.yaml").read_text(encoding="utf-8"))[
        "source_path"
    ] == "builder://native-level-2"
    assert get_character("milestone-leveler").state_record.state["vitals"]["current_hp"] == 20

    repairer_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "milestone-repairer"
    repairer_dir.mkdir(parents=True, exist_ok=True)
    repairer_definition = _minimal_imported_character_definition("milestone-repairer", "Milestone Repairer")
    (repairer_dir / "definition.yaml").write_text(
        yaml.safe_dump(repairer_definition.to_dict(), sort_keys=False),
        encoding="utf-8",
    )
    (repairer_dir / "import.yaml").write_text(
        yaml.safe_dump(_minimal_import_metadata("milestone-repairer").to_dict(), sort_keys=False),
        encoding="utf-8",
    )
    readiness_states = iter(
        [
            {
                "status": "repairable",
                "message": "This imported character needs a quick progression repair before native level-up.",
                "reasons": ["Choose a supported base class link for this character."],
            },
            {"status": "ready", "message": "", "reasons": []},
        ]
    )
    monkeypatch.setattr(app_module, "native_level_up_readiness", lambda *args, **kwargs: next(readiness_states))
    monkeypatch.setattr(
        app_module,
        "build_imported_progression_repair_context",
        lambda *args, **kwargs: {
            "values": {},
            "character_name": "Milestone Repairer",
            "current_level": 3,
            "readiness": {"message": "repair"},
            "class_options": [],
            "species_options": [],
            "background_options": [],
            "subclass_options": [],
            "feat_rows": [],
            "optionalfeature_rows": [],
            "spell_rows": [],
            "class_entries": [],
            "species_entries": [],
            "background_entries": [],
            "subclass_entries": [],
            "feat_entries": [],
            "optionalfeature_entries": [],
        },
    )
    repaired_definition = _minimal_imported_character_definition("milestone-repairer", "Milestone Repairer")
    repaired_definition.source["native_progression"] = {
        "baseline_repaired_at": "2026-04-27T00:00:00Z",
        "history": [{"kind": "repair", "at": "2026-04-27T00:00:00Z", "target_level": 3}],
    }
    repaired_import = _minimal_import_metadata("milestone-repairer")
    repaired_import.source_path = "imports://milestone-repairer.md"
    repaired_import.import_status = "managed"

    def _repair_dnd_imported_progression(*args, **kwargs):
        route_calls["repair"] += 1
        return repaired_definition, repaired_import

    monkeypatch.setattr(app_module, "apply_imported_progression_repairs", _repair_dnd_imported_progression)

    repair_response = client.post(
        "/campaigns/linden-pass/characters/milestone-repairer/progression-repair",
        data={"expected_revision": "1"},
        follow_redirects=False,
    )

    assert repair_response.status_code == 302
    assert repair_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/milestone-repairer/level-up"
    )
    assert route_calls["repair"] == 1
    repair_payload = yaml.safe_load((repairer_dir / "definition.yaml").read_text(encoding="utf-8"))
    assert repair_payload["system"] == "DND-5E"
    assert "xianxia" not in repair_payload
    assert repair_payload["source"]["native_progression"]["history"][-1]["kind"] == "repair"
    assert yaml.safe_load((repairer_dir / "import.yaml").read_text(encoding="utf-8"))[
        "import_status"
    ] == "managed"
def test_level_one_builder_applies_campaign_subclass_progression_feature_and_tracker():
    fixture = _build_sorcerer_wild_magic_fixture()
    systems_service = fixture["systems_service"]
    level_one_values = dict(fixture["level_one_values"])

    builder_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        level_one_values,
    )

    assert "Wild Magic Modification" in builder_context["preview"]["features"]
    assert "Wild Die: 1 / 1 (Long Rest)" in builder_context["preview"]["resources"]

    definition, _import_metadata = build_level_one_character_definition(
        "linden-pass",
        builder_context,
        level_one_values,
    )

    wild_magic_feature = next(
        feature for feature in definition.features if feature.get("name") == "Wild Magic Modification"
    )
    wild_die_resource = next(
        template for template in definition.resource_templates if template.get("label") == "Wild Die"
    )

    assert wild_magic_feature["page_ref"] == "mechanics/wild-magic-modification"
    assert wild_magic_feature["activation_type"] == "special"
    assert wild_magic_feature["tracker_ref"] == wild_die_resource["id"]
    assert wild_magic_feature["campaign_option"]["resource"]["scaling"]["mode"] == "half_level"
    assert "half your level" not in wild_magic_feature["description_markdown"].casefold()
    assert wild_magic_feature["campaign_option"]["mechanic_effects"] == [
        {
            "kind": "resource_template",
            "resource": {
                "label": "Wild Die",
                "reset_on": "long_rest",
                "scaling": {
                    "mode": "half_level",
                    "minimum": 1,
                    "round": "down",
                },
            },
            "source": "character_option.resource",
        }
    ]
    assert wild_die_resource["max"] == 1
    assert wild_die_resource["reset_on"] == "long_rest"
    assert wild_die_resource["scaling"] == {
        "mode": "half_level",
        "minimum": 1,
        "round": "down",
    }
