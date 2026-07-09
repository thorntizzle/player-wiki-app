from __future__ import annotations

from tests.helpers.character_builder_fakes import *  # noqa: F401,F403

def test_normalize_definition_to_native_model_derives_shared_slots_for_full_and_half_casters():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "wis",
            "caster_progression": "full",
            "prepared_spells": "level + wis",
        },
    )
    paladin = _systems_entry(
        "class",
        "phb-class-paladin",
        "Paladin",
        metadata={
            "hit_die": {"faces": 10},
            "spellcasting_ability": "cha",
            "caster_progression": "1/2",
            "prepared_spells": "level + cha",
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [cleric, paladin],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("cleric-paladin", "Cleric Paladin")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Cleric",
            "subclass_name": "",
            "level": 2,
            "systems_ref": _systems_ref(cleric),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Paladin",
            "subclass_name": "",
            "level": 2,
            "systems_ref": _systems_ref(paladin),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(cleric)
    definition.profile["class_level_text"] = "Cleric 2 / Paladin 2"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert normalized.spellcasting["spellcasting_class"] == ""
    assert normalized.spellcasting["spellcasting_ability"] == ""
    assert normalized.spellcasting["slot_progression"] == [
        {"level": 1, "max_slots": 4},
        {"level": 2, "max_slots": 2},
    ]
    assert [row["class_name"] for row in normalized.spellcasting["class_rows"]] == ["Cleric", "Paladin"]
def test_normalize_definition_to_native_model_derives_shared_slots_for_full_and_artificer_rows():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "int",
            "caster_progression": "artificer",
            "prepared_spells": "level + int",
        },
        source_id="TCE",
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [wizard, artificer],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("wizard-artificer", "Wizard Artificer")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(wizard),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Artificer",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(artificer),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.profile["class_level_text"] = "Wizard 1 / Artificer 1"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert normalized.spellcasting["slot_progression"] == [
        {"level": 1, "max_slots": 3},
    ]
    assert [row["caster_progression"] for row in normalized.spellcasting["class_rows"]] == ["full", "artificer"]
def test_normalize_definition_to_native_model_derives_separate_slot_lanes_for_wizard_and_warlock():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "cha",
            "caster_progression": "pact",
            "spells_known_progression": [2, 3, 4],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [wizard, warlock],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("wizard-warlock", "Wizard Warlock")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 3,
            "systems_ref": _systems_ref(wizard),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Warlock",
            "subclass_name": "",
            "level": 2,
            "systems_ref": _systems_ref(warlock),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.profile["class_level_text"] = "Wizard 3 / Warlock 2"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert normalized.spellcasting["slot_progression"] == []
    assert normalized.spellcasting["class_rows"][0]["slot_lane_id"] == "class-row-1-slots"
    assert normalized.spellcasting["class_rows"][1]["slot_lane_id"] == "class-row-2-slots"
    assert normalized.spellcasting["slot_lanes"] == [
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
    ]
def test_normalize_definition_to_native_model_preserves_saved_multiclass_slot_lanes_when_resolution_is_incomplete():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [],
            "background": [],
            "subclass": [],
        },
        class_progression=[],
        enabled_source_ids=["PHB"],
    )
    definition = _minimal_character_definition("wizard-warlock-fallback", "Wizard Warlock Fallback")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 3,
            "systems_ref": _systems_ref(wizard),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Warlock",
            "subclass_name": "",
            "level": 2,
            "systems_ref": {
                "entry_key": "dnd-5e|class|phb|phb-class-warlock",
                "entry_type": "class",
                "title": "Warlock",
                "slug": "phb-class-warlock",
                "source_id": "PHB",
            },
        },
    ]
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.profile["class_level_text"] = "Wizard 3 / Warlock 2"
    definition.spellcasting = {
        "spellcasting_class": "",
        "spellcasting_ability": "",
        "spell_save_dc": None,
        "spell_attack_bonus": None,
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
        "class_rows": [
            {
                "class_row_id": "class-row-1",
                "class_name": "Wizard",
                "level": 3,
                "caster_progression": "full",
                "spell_mode": "wizard",
                "spellcasting_ability": "Intelligence",
                "spell_save_dc": 14,
                "spell_attack_bonus": 6,
                "slot_lane_id": "class-row-1-slots",
            },
            {
                "class_row_id": "class-row-2",
                "class_name": "Warlock",
                "level": 2,
                "caster_progression": "pact",
                "spell_mode": "known",
                "spellcasting_ability": "Charisma",
                "spell_save_dc": 13,
                "spell_attack_bonus": 5,
                "slot_lane_id": "class-row-2-slots",
            },
        ],
        "spells": [],
    }

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert [row["class_name"] for row in normalized.spellcasting["class_rows"]] == ["Wizard", "Warlock"]
    assert [row["slot_lane_id"] for row in normalized.spellcasting["class_rows"]] == [
        "class-row-1-slots",
        "class-row-2-slots",
    ]
    assert [row["spell_save_dc"] for row in normalized.spellcasting["class_rows"]] == [14, 13]
    assert normalized.spellcasting["slot_lanes"] == [
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
    ]
def test_normalize_definition_to_native_model_supports_single_class_eldritch_knight_spellcasting():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritchknight-fighter-phb",
        "Eldritch Knight",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [eldritch_knight],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}]},
        subclass_by_slug={eldritch_knight.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}]},
    )
    definition = _minimal_character_definition("eldritch-knight", "Eldritch Knight")
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["class_ref"] = _systems_ref(fighter)
    definition.profile["subclass_ref"] = _systems_ref(eldritch_knight)
    definition.profile["classes"][0]["level"] = 3
    definition.profile["classes"][0]["systems_ref"] = _systems_ref(fighter)
    definition.profile["classes"][0]["subclass_name"] = "Eldritch Knight"
    definition.profile["classes"][0]["subclass_ref"] = _systems_ref(eldritch_knight)
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    row = dict(normalized.spellcasting["class_rows"][0])
    assert normalized.spellcasting["spellcasting_class"] == "Fighter"
    assert normalized.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 2}]
    assert row["class_name"] == "Fighter"
    assert row["spell_list_class_name"] == "Wizard"
    assert row["caster_progression"] == "1/3"
    assert row["spell_mode"] == "known"
def test_normalize_definition_to_native_model_shares_slots_for_eldritch_knight_and_wizard():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritchknight-fighter-phb",
        "Eldritch Knight",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, wizard],
            "subclass": [eldritch_knight],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}],
            wizard.slug: [{"level": 1, "feature_rows": [_progression_row("Spellcasting")]}],
        },
        subclass_by_slug={eldritch_knight.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}]},
    )
    definition = _minimal_character_definition("ek-wizard", "EK Wizard")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Fighter",
            "subclass_name": "Eldritch Knight",
            "level": 3,
            "systems_ref": _systems_ref(fighter),
            "subclass_ref": _systems_ref(eldritch_knight),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(wizard),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(fighter)
    definition.profile["subclass_ref"] = _systems_ref(eldritch_knight)
    definition.profile["class_level_text"] = "Fighter 3 / Wizard 1"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert normalized.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 3}]
    assert [row["caster_progression"] for row in normalized.spellcasting["class_rows"]] == ["1/3", "full"]
    assert all(row["slot_lane_id"] == "shared-multiclass-slots" for row in normalized.spellcasting["class_rows"])
def test_normalize_definition_to_native_model_supports_structured_subclass_only_spellcasting_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    spellblade = _systems_entry(
        "subclass",
        "xge-subclass-spellblade",
        "Spellblade",
        metadata=_structured_subclass_spellcasting_metadata(),
        source_id="XGE",
    )
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, wizard],
            "subclass": [spellblade],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}],
            wizard.slug: [{"level": 1, "feature_rows": [_progression_row("Spellcasting")]}],
        },
        subclass_by_slug={spellblade.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}]},
    )
    definition = _minimal_character_definition("spellblade-wizard", "Spellblade Wizard")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Fighter",
            "subclass_name": "Spellblade",
            "level": 3,
            "systems_ref": _systems_ref(fighter),
            "subclass_ref": _systems_ref(spellblade),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(wizard),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(fighter)
    definition.profile["subclass_ref"] = _systems_ref(spellblade)
    definition.profile["class_level_text"] = "Fighter 3 / Wizard 1"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    first_row = dict(normalized.spellcasting["class_rows"][0])
    assert normalized.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 3}]
    assert first_row["class_name"] == "Fighter"
    assert first_row["spell_list_class_name"] == "Wizard"
    assert first_row["caster_progression"] == "1/3"
    assert [row["caster_progression"] for row in normalized.spellcasting["class_rows"]] == ["1/3", "full"]
    assert all(row["slot_lane_id"] == "shared-multiclass-slots" for row in normalized.spellcasting["class_rows"])
def test_normalize_definition_to_native_model_keeps_pact_lane_separate_for_arcane_trickster_and_warlock():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"], "subclass_title": "Roguish Archetype"},
    )
    arcane_trickster = _systems_entry(
        "subclass",
        "phb-subclass-arcanetrickster-rogue-phb",
        "Arcane Trickster",
        metadata={"class_name": "Rogue", "class_source": "PHB"},
    )
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "cha",
            "caster_progression": "pact",
            "spells_known_progression": [2, 3, 4],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [rogue, warlock],
            "subclass": [arcane_trickster],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            rogue.slug: [{"level": 3, "feature_rows": [_progression_row("Roguish Archetype")]}],
            warlock.slug: [{"level": 1, "feature_rows": [_progression_row("Pact Magic")]}],
        },
        subclass_by_slug={arcane_trickster.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}]},
    )
    definition = _minimal_character_definition("at-warlock", "AT Warlock")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Rogue",
            "subclass_name": "Arcane Trickster",
            "level": 3,
            "systems_ref": _systems_ref(rogue),
            "subclass_ref": _systems_ref(arcane_trickster),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Warlock",
            "subclass_name": "",
            "level": 2,
            "systems_ref": _systems_ref(warlock),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(rogue)
    definition.profile["subclass_ref"] = _systems_ref(arcane_trickster)
    definition.profile["class_level_text"] = "Rogue 3 / Warlock 2"
    definition.spellcasting = {"slot_progression": [], "spells": []}

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert normalized.spellcasting["slot_progression"] == []
    assert [row["caster_progression"] for row in normalized.spellcasting["class_rows"]] == ["1/3", "pact"]
    assert normalized.spellcasting["class_rows"][0]["spell_list_class_name"] == "Wizard"
    assert normalized.spellcasting["slot_lanes"] == [
        {
            "id": "class-row-1-slots",
            "title": "Rogue spell slots",
            "shared": False,
            "row_ids": ["class-row-1"],
            "slot_progression": [
                {"level": 1, "max_slots": 2},
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
    ]
def test_merge_state_with_definition_drops_legacy_spell_slot_duplicates_for_tracked_levels():
    definition = _minimal_character_definition("wizard-slot-merge", "Wizard Slot Merge")
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
                    {"level": 2, "max_slots": 3},
                    {"level": 3, "max_slots": 2},
                ],
            }
        ],
        "spells": [],
    }
    state = build_initial_state(definition)
    state["spell_slots"][0]["used"] = 1
    state["spell_slots"][1]["used"] = 0
    state["spell_slots"][2]["used"] = 1
    state["spell_slots"].extend(
        [
            {"level": 1, "max": 4, "used": 3},
            {"level": 2, "max": 3, "used": 2},
            {"level": 3, "max": 2, "used": 0},
        ]
    )

    merged_state = merge_state_with_definition(definition, state)

    assert merged_state["spell_slots"] == [
        {"level": 1, "max": 4, "used": 1, "slot_lane_id": "class-row-1-slots"},
        {"level": 2, "max": 3, "used": 0, "slot_lane_id": "class-row-1-slots"},
        {"level": 3, "max": 2, "used": 1, "slot_lane_id": "class-row-1-slots"},
    ]
def test_prepared_spell_formula_supports_simple_level_plus_ability_tokens():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "wis",
            "caster_progression": "full",
            "prepared_spells": "level + wis",
        },
    )

    assert (
        _prepared_spell_count_for_level(
            "Cleric",
            {"wis": 12},
            3,
            selected_class=cleric,
        )
        == 4
    )
def test_normalize_definition_to_native_model_keeps_same_spell_on_distinct_class_rows():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "spells_known_progression_fixed": [6],
        },
    )
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "spellcasting_ability": "wis",
            "caster_progression": "full",
            "prepared_spells": "level + wis",
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    spell_ref = {
        "entry_key": "dnd-5e|spell|phb|detect-magic",
        "entry_type": "spell",
        "title": "Detect Magic",
        "slug": "phb-spell-detect-magic",
        "source_id": "PHB",
    }
    systems_service = _FakeSystemsService(
        {
            "class": [wizard, cleric],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("double-detect-magic", "Double Detect Magic")
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 3,
            "systems_ref": _systems_ref(wizard),
        },
        {
            "row_id": "class-row-2",
            "class_name": "Cleric",
            "subclass_name": "",
            "level": 3,
            "systems_ref": _systems_ref(cleric),
        },
    ]
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.profile["class_level_text"] = "Wizard 3 / Cleric 3"
    definition.spellcasting = {
        "slot_progression": [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 3}, {"level": 3, "max_slots": 3}],
        "spells": [
            {
                "name": "Detect Magic",
                "mark": "Spellbook",
                "systems_ref": dict(spell_ref),
                "class_row_id": "class-row-1",
            },
            {
                "name": "Detect Magic",
                "mark": "Prepared",
                "systems_ref": dict(spell_ref),
                "class_row_id": "class-row-2",
            },
        ],
    }

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)

    assert len(normalized.spellcasting["spells"]) == 2
    assert {
        str(spell.get("class_row_id") or "").strip()
        for spell in normalized.spellcasting["spells"]
    } == {"class-row-1", "class-row-2"}
def test_native_level_up_surfaces_and_applies_eldritch_knight_spell_choices():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritchknight-fighter-phb",
        "Eldritch Knight",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    fire_bolt = _systems_entry(
        "spell",
        "phb-spell-fire-bolt",
        "Fire Bolt",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    ray_of_frost = _systems_entry(
        "spell",
        "phb-spell-ray-of-frost",
        "Ray of Frost",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    magic_missile = _systems_entry(
        "spell",
        "phb-spell-magic-missile",
        "Magic Missile",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    shield = _systems_entry(
        "spell",
        "phb-spell-shield",
        "Shield",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [eldritch_knight],
            "race": [human],
            "background": [acolyte],
            "spell": [fire_bolt, mage_hand, ray_of_frost, detect_magic, magic_missile, shield],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={
            fighter.slug: [
                {"level": 3, "feature_rows": [_progression_row("Martial Archetype")]},
            ],
        },
        subclass_by_slug={
            eldritch_knight.slug: [
                {"level": 3, "feature_rows": [_progression_row("Spellcasting")]},
            ],
        },
    )
    current_definition = _minimal_character_definition("eldritch-level-up", "Eldritch Level Up")
    current_definition.profile["class_level_text"] = "Fighter 2"
    current_definition.profile["class_ref"] = _systems_ref(fighter)
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(fighter)
    current_definition.stats["max_hp"] = 20

    form_values = {
        "advancement_mode": "advance_existing",
        "target_class_row_id": "class-row-1",
        "subclass_slug": eldritch_knight.slug,
        "hp_gain": "6",
    }
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
    )

    assert _find_builder_field(context, "levelup_spell_cantrip_1")["label"] == "New Cantrip 1"
    assert _find_builder_field(context, "levelup_spell_known_1")["label"] == "New Spell 1"

    form_values.update(
        {
            "levelup_spell_cantrip_1": _field_value_for_label(context, "levelup_spell_cantrip_1", "Fire Bolt"),
            "levelup_spell_cantrip_2": _field_value_for_label(context, "levelup_spell_cantrip_2", "Mage Hand"),
            "levelup_spell_known_1": _field_value_for_label(context, "levelup_spell_known_1", "Detect Magic"),
            "levelup_spell_known_2": _field_value_for_label(context, "levelup_spell_known_2", "Magic Missile"),
            "levelup_spell_known_3": _field_value_for_label(context, "levelup_spell_known_3", "Shield"),
        }
    )
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    spell_row = dict(leveled_definition.spellcasting["class_rows"][0])
    spells_by_name = {spell["name"]: dict(spell) for spell in leveled_definition.spellcasting["spells"]}

    assert leveled_definition.profile["classes"][0]["subclass_name"] == "Eldritch Knight"
    assert spell_row["class_name"] == "Fighter"
    assert spell_row["spell_list_class_name"] == "Wizard"
    assert spell_row["caster_progression"] == "1/3"
    assert leveled_definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 2}]
    assert spells_by_name["Fire Bolt"]["mark"] == "Cantrip"
    assert spells_by_name["Mage Hand"]["mark"] == "Cantrip"
    assert spells_by_name["Detect Magic"]["mark"] == "Known"
    assert spells_by_name["Magic Missile"]["class_row_id"] == "class-row-1"
    assert spells_by_name["Shield"]["class_row_id"] == "class-row-1"
def test_native_level_up_surfaces_and_applies_structured_subclass_spell_choices():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    spellblade = _systems_entry(
        "subclass",
        "xge-subclass-spellblade",
        "Spellblade",
        metadata=_structured_subclass_spellcasting_metadata(),
        source_id="XGE",
    )
    fire_bolt = _systems_entry(
        "spell",
        "phb-spell-fire-bolt",
        "Fire Bolt",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    ray_of_frost = _systems_entry(
        "spell",
        "phb-spell-ray-of-frost",
        "Ray of Frost",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    magic_missile = _systems_entry(
        "spell",
        "phb-spell-magic-missile",
        "Magic Missile",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    shield = _systems_entry(
        "spell",
        "phb-spell-shield",
        "Shield",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [spellblade],
            "race": [human],
            "background": [acolyte],
            "spell": [fire_bolt, mage_hand, ray_of_frost, detect_magic, magic_missile, shield],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}]},
        subclass_by_slug={spellblade.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}]},
    )
    current_definition = _minimal_character_definition("spellblade-level-up", "Spellblade Level Up")
    current_definition.profile["class_level_text"] = "Fighter 2"
    current_definition.profile["class_ref"] = _systems_ref(fighter)
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = _systems_ref(fighter)
    current_definition.stats["max_hp"] = 20

    form_values = {
        "advancement_mode": "advance_existing",
        "target_class_row_id": "class-row-1",
        "subclass_slug": spellblade.slug,
        "hp_gain": "6",
    }
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
    )

    assert _find_builder_field(context, "levelup_spell_cantrip_1")["label"] == "New Cantrip 1"
    assert _find_builder_field(context, "levelup_spell_known_1")["label"] == "New Spell 1"

    form_values.update(
        {
            "levelup_spell_cantrip_1": _field_value_for_label(context, "levelup_spell_cantrip_1", "Fire Bolt"),
            "levelup_spell_cantrip_2": _field_value_for_label(context, "levelup_spell_cantrip_2", "Mage Hand"),
            "levelup_spell_known_1": _field_value_for_label(context, "levelup_spell_known_1", "Detect Magic"),
            "levelup_spell_known_2": _field_value_for_label(context, "levelup_spell_known_2", "Magic Missile"),
            "levelup_spell_known_3": _field_value_for_label(context, "levelup_spell_known_3", "Shield"),
        }
    )
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    spell_row = dict(leveled_definition.spellcasting["class_rows"][0])
    spells_by_name = {spell["name"]: dict(spell) for spell in leveled_definition.spellcasting["spells"]}

    assert leveled_definition.profile["classes"][0]["subclass_name"] == "Spellblade"
    assert spell_row["class_name"] == "Fighter"
    assert spell_row["spell_list_class_name"] == "Wizard"
    assert spell_row["caster_progression"] == "1/3"
    assert leveled_definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 2}]
    assert spells_by_name["Fire Bolt"]["mark"] == "Cantrip"
    assert spells_by_name["Mage Hand"]["mark"] == "Cantrip"
    assert spells_by_name["Detect Magic"]["mark"] == "Known"
    assert spells_by_name["Magic Missile"]["class_row_id"] == "class-row-1"
    assert spells_by_name["Shield"]["class_row_id"] == "class-row-1"
def test_level_one_builder_campaign_page_slots_follow_allowed_content_policy():
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
            subsection="Boons",
            metadata={"character_option": {"kind": "feature", "name": "Arcane Overload"}},
        ),
        _campaign_page_record(
            "mechanics/bulwark-discipline",
            "Bulwark Discipline",
            section="Mechanics",
            subsection="Feats",
            metadata={"character_option": {"kind": "feat", "name": "Bulwark Discipline"}},
        ),
        _campaign_page_record(
            "species/sea-blessed",
            "Sea-Blessed",
            section="Mechanics",
            subsection="Species",
            metadata={"character_option": {"kind": "species", "name": "Sea-Blessed", "size": ["M"], "speed": 35}},
        ),
        _campaign_page_record(
            "backgrounds/harbor-initiate",
            "Harbor Initiate",
            section="Mechanics",
            subsection="Backgrounds",
            metadata={"character_option": {"kind": "background", "name": "Harbor Initiate"}},
        ),
        _campaign_page_record(
            "items/stormglass-compass",
            "Stormglass Compass",
            section="Items",
            subsection="Wondrous Items",
            metadata={"character_option": {"kind": "item", "name": "Stormglass Compass"}},
        ),
    ]

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        {
            "name": "Ward",
            "character_slug": "ward",
            "alignment": "Lawful Good",
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

    feature_labels = [str(option.get("label") or "") for option in _find_builder_field(context, "campaign_feature_page_ref_1")["options"]]
    item_labels = [str(option.get("label") or "") for option in _find_builder_field(context, "campaign_item_page_ref_1")["options"]]

    assert _option_value_for_label(context["species_options"], "Sea-Blessed")
    assert _option_value_for_label(context["background_options"], "Harbor Initiate")
    assert any("Arcane Overload" in label for label in feature_labels)
    assert any("Bulwark Discipline" in label for label in feature_labels)
    assert all("Sea-Blessed" not in label for label in feature_labels)
    assert all("Harbor Initiate" not in label for label in feature_labels)
    assert all("Stormglass Compass" not in label for label in feature_labels)
    assert any("Stormglass Compass" in label for label in item_labels)
    assert all("Arcane Overload" not in label for label in item_labels)
    assert all("Bulwark Discipline" not in label for label in item_labels)
def test_level_one_builder_campaign_feat_pages_can_be_added_through_campaign_feature_slots():
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
            "mechanics/bulwark-discipline",
            "Bulwark Discipline",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Bulwark Discipline",
                    "description_markdown": "A disciplined bulwark technique.",
                    "grants": {
                        "languages": ["Primordial"],
                        "skills": ["Perception"],
                    },
                }
            },
        )
    ]
    form_values = {
        "name": "Bulwark Recruit",
        "character_slug": "bulwark-recruit",
        "alignment": "Lawful Neutral",
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
        "campaign_feature_page_ref_1": _field_value_for_label(context, "campaign_feature_page_ref_1", "Bulwark Discipline"),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    bulwark_discipline = next(feature for feature in definition.features if feature["name"] == "Bulwark Discipline")
    skills_by_name = {skill["name"]: skill for skill in definition.skills}

    assert bulwark_discipline["category"] == "feat"
    assert bulwark_discipline["page_ref"] == "mechanics/bulwark-discipline"
    assert dict(bulwark_discipline.get("campaign_option") or {}).get("kind") == "feat"
    assert "Primordial" in definition.proficiencies["languages"]
    assert skills_by_name["Perception"]["proficiency_level"] == "proficient"
def test_level_one_builder_applies_campaign_feature_spell_support_and_create_replacement():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
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
    eldritch_blast = _systems_entry(
        "spell",
        "phb-spell-eldritch-blast",
        "Eldritch Blast",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    chill_touch = _systems_entry(
        "spell",
        "phb-spell-chill-touch",
        "Chill Touch",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    charm_person = _systems_entry(
        "spell",
        "phb-spell-charm-person",
        "Charm Person",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hex_spell = _systems_entry(
        "spell",
        "phb-spell-hex",
        "Hex",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
    )
    silent_image = _systems_entry(
        "spell",
        "phb-spell-silent-image",
        "Silent Image",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    cause_fear = _systems_entry(
        "spell",
        "phb-spell-cause-fear",
        "Cause Fear",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    disguise_self = _systems_entry(
        "spell",
        "phb-spell-disguise-self",
        "Disguise Self",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [
                eldritch_blast,
                chill_touch,
                charm_person,
                hex_spell,
                detect_magic,
                silent_image,
                cause_fear,
                disguise_self,
            ],
        },
        class_progression=[],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/harbor-whispers",
            "Harbor Whispers",
            section="Mechanics",
            subsection="Blessings",
            summary="A harbor rite that teaches tide-borne secrets.",
            metadata={
                "character_option": {
                    "name": "Harbor Whispers",
                    "description_markdown": "The tide shares a few whispered spells with you.",
                    "activation_type": "special",
                    "spell_support": [
                        {
                            "grants": {
                                "_": [
                                    {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                                ]
                            },
                            "choices": {
                                "_": [
                                    {
                                        "category": "granted",
                                        "options": ["Silent Image", "Disguise Self"],
                                        "count": 1,
                                        "label_prefix": "Harbor Spell",
                                        "mark": "Granted",
                                    }
                                ]
                            },
                            "replacement": {
                                "_": [
                                    {
                                        "kind": "known",
                                        "from": {"mark": "Known", "level": 1},
                                        "to": {"options": ["Cause Fear", "Disguise Self"]},
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
    ]
    base_form_values = {
        "name": "Selka Norn",
        "character_slug": "selka-norn",
        "alignment": "Chaotic Good",
        "experience_model": "Milestone",
        "class_slug": warlock.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "arcana",
        "class_skill_2": "deception",
        "str": "8",
        "dex": "14",
        "con": "13",
        "int": "12",
        "wis": "10",
        "cha": "16",
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        base_form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values = {
        **base_form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(
            context,
            "campaign_feature_page_ref_1",
            "Harbor Whispers",
        ),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Eldritch Blast"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Chill Touch"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Charm Person"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Hex"),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    harbor_spell_field = _field_name_for_label(context, "Harbor Spell 1")
    replace_from_field = _field_name_for_label(context, "Replace Spell 1")
    replace_to_field = _field_name_for_label(context, "Replacement Spell 1")
    form_values.update(
        {
            harbor_spell_field: _field_value_for_label(context, harbor_spell_field, "Silent Image"),
            replace_from_field: _field_value_for_label(context, replace_from_field, "Charm Person"),
            replace_to_field: _field_value_for_label(context, replace_to_field, "Cause Fear"),
        }
    )

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Harbor Whispers" in {feature["name"] for feature in definition.features}
    assert "Detect Magic (Always prepared)" in context["preview"]["spells"]
    assert any("Silent Image" in spell_line for spell_line in context["preview"]["spells"])
    assert any("Cause Fear" in spell_line for spell_line in context["preview"]["spells"])
    assert "Charm Person" not in spells_by_name
    assert spells_by_name["Cause Fear"]["mark"] == "Known"
    assert spells_by_name["Silent Image"]["mark"] == "Granted"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["systems_ref"]["slug"] == detect_magic.slug
def test_level_one_builder_applies_campaign_feature_spell_support_source_rows_for_free_cast_spells():
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
    misty_step = _systems_entry(
        "spell",
        "phb-spell-misty-step",
        "Misty Step",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 2},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [misty_step],
        },
        class_progression=[],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/moonlit-step",
            "Moonlit Step",
            section="Mechanics",
            subsection="Blessings",
            summary="A moon-marked step that slips between moments.",
            metadata={
                "character_option": {
                    "name": "Moonlit Step",
                    "description_markdown": "You can slip through a moonlit seam in the air.",
                    "activation_type": "special",
                    "spell_support": [
                        {
                            "source": {
                                "title": "Moonlit Step",
                                "kind": "feature",
                                "ability_key": "wis",
                            },
                            "grants": {
                                "_": [
                                    {
                                        "spell": "Misty Step",
                                        "mark": "Granted",
                                        "access_type": "free_cast",
                                        "access_uses": 1,
                                        "access_reset_on": "short_or_long_rest",
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
    ]
    base_form_values = {
        "name": "Maeve Dain",
        "character_slug": "maeve-dain",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": soldier.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "15",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "14",
        "cha": "8",
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        base_form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values = {
        **base_form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(
            context,
            "campaign_feature_page_ref_1",
            "Moonlit Step",
        ),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    moonlit_step = next(feature for feature in definition.features if feature["name"] == "Moonlit Step")
    source_rows = [dict(row or {}) for row in list(definition.spellcasting.get("source_rows") or [])]
    assert len(source_rows) == 1
    source_row = source_rows[0]
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert moonlit_step["page_ref"] == "mechanics/moonlit-step"
    assert source_row["source_row_id"] == "spell-source:moonlit-step"
    assert source_row["source_row_kind"] == "feature"
    assert source_row["title"] == "Moonlit Step"
    assert source_row["spellcasting_ability"] == "Wisdom"
    assert source_row["spell_save_dc"] == 12
    assert source_row["spell_attack_bonus"] == 4
    assert spells_by_name["Misty Step"]["spell_source_row_id"] == "spell-source:moonlit-step"
    assert spells_by_name["Misty Step"]["spell_source_row_kind"] == "feature"
    assert spells_by_name["Misty Step"]["spell_source_row_title"] == "Moonlit Step"
    assert spells_by_name["Misty Step"]["spell_access_type"] == "free_cast"
    assert spells_by_name["Misty Step"]["spell_access_uses"] == 1
    assert spells_by_name["Misty Step"]["spell_access_reset_on"] == "short_or_long_rest"
    assert spells_by_name["Misty Step"]["grant_source_label"] == "Moonlit Step"
    assert any("Misty Step" in spell_line for spell_line in context["preview"]["spells"])
def test_level_one_builder_applies_campaign_feature_ritual_book_spell_manager():
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
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    identify = _systems_entry(
        "spell",
        "phb-spell-identify",
        "Identify",
        metadata={"casting_time": [{"number": 1, "unit": "minute"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    magic_missile = _systems_entry(
        "spell",
        "phb-spell-magic-missile",
        "Magic Missile",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [detect_magic, identify, magic_missile],
        },
        class_progression=[],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/harbor-ritual-book",
            "Harbor Ritual Book",
            section="Mechanics",
            subsection="Blessings",
            summary="A warded ritual book kept in the harbor shrine.",
            metadata={
                "character_option": {
                    "name": "Harbor Ritual Book",
                    "description_markdown": "You keep a slim ritual book of harbor wards.",
                    "activation_type": "special",
                    "spell_manager": {
                        "mode": "ritual_book",
                        "source_row_kind": "feature",
                        "source_title": "Harbor Ritual Book",
                        "spell_list_class_name": "Wizard",
                        "ability_key": "int",
                        "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                        "choice_fields": [
                            {
                                "category": "spell_managed",
                                "filter": "level=1|class=Wizard|miscellaneous=ritual",
                                "count": 2,
                                "label_prefix": "Ritual Spell",
                                "help_text": "Choose a wizard ritual for the harbor ritual book.",
                                "spell_mark": "Ritual Book",
                                "spell_is_ritual": True,
                            }
                        ],
                    },
                }
            },
        )
    ]
    base_form_values = {
        "name": "Corin Vale",
        "character_slug": "corin-vale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": soldier.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "15",
        "dex": "12",
        "con": "14",
        "int": "14",
        "wis": "10",
        "cha": "8",
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        base_form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values = {
        **base_form_values,
        "campaign_feature_page_ref_1": _field_value_for_label(
            context,
            "campaign_feature_page_ref_1",
            "Harbor Ritual Book",
        ),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    first_ritual_field = _field_name_for_label(context, "Harbor Ritual Book Ritual Spell 1")
    second_ritual_field = _field_name_for_label(context, "Harbor Ritual Book Ritual Spell 2")
    form_values[first_ritual_field] = _field_value_for_label(context, first_ritual_field, "Detect Magic")
    form_values[second_ritual_field] = _field_value_for_label(context, second_ritual_field, "Identify")

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    harbor_ritual_book = next(feature for feature in definition.features if feature["name"] == "Harbor Ritual Book")
    spell_manager = dict(harbor_ritual_book.get("spell_manager") or {})
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    source_rows = [dict(row or {}) for row in list(definition.spellcasting.get("source_rows") or []) if isinstance(row, dict)]

    assert definition.spellcasting["spellcasting_class"] == ""
    assert spell_manager["mode"] == "ritual_book"
    assert spell_manager["title"] == "Harbor Ritual Book"
    assert spell_manager["spell_list_class_name"] == "Wizard"
    assert spell_manager["spellcasting_ability"] == "Intelligence"
    assert spell_manager["max_spell_level_formula"] == "ritual_caster_half_level_rounded_up"
    assert {spell["name"] for spell in definition.spellcasting["spells"]} == {"Detect Magic", "Identify"}
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert spells_by_name["Identify"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert len(source_rows) == 1
    assert source_rows[0]["source_row_id"] == spell_manager["source_row_id"]
    assert source_rows[0]["spell_mode"] == "ritual_book"
    assert source_rows[0]["title"] == "Harbor Ritual Book"
    assert source_rows[0]["spell_list_class_name"] == "Wizard"
    assert "Detect Magic (Ritual Book)" in list(context["preview"]["spells"] or [])
    assert "Identify (Ritual Book)" in list(context["preview"]["spells"] or [])
def test_native_level_up_applies_campaign_progression_ritual_book_spell_manager():
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
    action_surge = _systems_entry("classfeature", "phb-classfeature-action-surge", "Action Surge", metadata={"level": 2})
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    alarm = _systems_entry(
        "spell",
        "phb-spell-alarm",
        "Alarm",
        metadata={"casting_time": [{"number": 1, "unit": "minute"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    campaign_progression_entry = build_campaign_page_progression_entries(
        _campaign_page_record(
            "mechanics/harbor-ritual-book",
            "Harbor Ritual Book",
            section="Mechanics",
            subsection="Class Modifications",
            metadata={
                "character_progression": {
                    "kind": "class",
                    "class_name": "Fighter",
                    "level": 2,
                    "character_option": {
                        "name": "Harbor Ritual Book",
                        "description_markdown": "You inherit a warded ritual book from the harbor shrine.",
                        "activation_type": "special",
                        "spell_manager": {
                            "mode": "ritual_book",
                            "source_row_kind": "feature",
                            "source_title": "Harbor Ritual Book",
                            "spell_list_class_name": "Wizard",
                            "ability_key": "int",
                            "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                            "choice_fields": [
                                {
                                    "category": "spell_managed",
                                    "filter": "level=1|class=Wizard|miscellaneous=ritual",
                                    "count": 1,
                                    "label_prefix": "Ritual Spell",
                                    "help_text": "Choose a ritual for the harbor ritual book.",
                                    "spell_mark": "Ritual Book",
                                    "spell_is_ritual": True,
                                }
                            ],
                        },
                    },
                }
            },
        )
    )[0]
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [detect_magic, alarm],
        },
        class_progression=[
            {"level": 1, "feature_rows": [{"label": "Second Wind", "entry": second_wind}]},
            {
                "level": 2,
                "feature_rows": [
                    {"label": "Action Surge", "entry": action_surge},
                    {"label": "Harbor Ritual Book", "entry": campaign_progression_entry},
                ],
            },
        ],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/harbor-ritual-book",
            "Harbor Ritual Book",
            section="Mechanics",
            subsection="Class Modifications",
            metadata={
                "character_progression": {
                    "kind": "class",
                    "class_name": "Fighter",
                    "level": 2,
                    "character_option": {
                        "name": "Harbor Ritual Book",
                        "description_markdown": "You inherit a warded ritual book from the harbor shrine.",
                        "activation_type": "special",
                        "spell_manager": {
                            "mode": "ritual_book",
                            "source_row_kind": "feature",
                            "source_title": "Harbor Ritual Book",
                            "spell_list_class_name": "Wizard",
                            "ability_key": "int",
                            "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                            "choice_fields": [
                                {
                                    "category": "spell_managed",
                                    "filter": "level=1|class=Wizard|miscellaneous=ritual",
                                    "count": 1,
                                    "label_prefix": "Ritual Spell",
                                    "help_text": "Choose a ritual for the harbor ritual book.",
                                    "spell_mark": "Ritual Book",
                                    "spell_is_ritual": True,
                                }
                            ],
                        },
                    },
                }
            },
        )
    ]

    level_one_form = {
        "name": "Jory Flint",
        "character_slug": "jory-flint",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": human.slug,
        "background_slug": soldier.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "str": "15",
        "dex": "12",
        "con": "14",
        "int": "14",
        "wis": "10",
        "cha": "8",
    }
    level_one_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        level_one_form,
        campaign_page_records=campaign_page_records,
    )
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, level_one_form)

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        {"hp_gain": "8"},
        campaign_page_records=campaign_page_records,
    )
    ritual_field = _field_name_for_label(level_up_context, "Harbor Ritual Book Ritual Spell 1")
    level_up_form = {
        "hp_gain": "8",
        ritual_field: _field_value_for_label(level_up_context, ritual_field, "Detect Magic"),
    }
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        level_up_form,
        campaign_page_records=campaign_page_records,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_up_context,
        level_up_form,
    )

    harbor_ritual_book = next(feature for feature in leveled_definition.features if feature["name"] == "Harbor Ritual Book")
    spell_manager = dict(harbor_ritual_book.get("spell_manager") or {})
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert spell_manager["mode"] == "ritual_book"
    assert spell_manager["title"] == "Harbor Ritual Book"
    assert spell_manager["spell_list_class_name"] == "Wizard"
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert any("Detect Magic" in spell_name for spell_name in list(level_up_context["preview"]["new_spells"] or []))
def test_level_one_builder_applies_campaign_feat_spell_support_for_noncasters():
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
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={
            "skill_proficiencies": [{"insight": True, "religion": True}],
            "language_proficiencies": [{"anyStandard": 2}],
        },
    )
    alert = _systems_entry("feat", "phb-feat-alert", "Alert")
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    message = _systems_entry(
        "spell",
        "phb-spell-message",
        "Message",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [alert],
            "subclass": [],
            "item": [],
            "spell": [light, message, detect_magic],
        },
        class_progression=[],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/embersworn-initiate",
            "Embersworn Initiate",
            section="Mechanics",
            subsection="Feats",
            summary="A fire-marked rite that teaches a few practical tricks.",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Embersworn Initiate",
                    "description_markdown": "You learn a few ember-bound tricks.",
                    "activation_type": "special",
                    "spell_support": [
                        {
                            "grants": {
                                "_": [
                                    {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                                ]
                            },
                            "choices": {
                                "_": [
                                    {
                                        "category": "granted",
                                        "options": ["Light", "Message"],
                                        "count": 1,
                                        "label_prefix": "Feat Spell",
                                        "mark": "Granted",
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
    ]
    base_form_values = {
        "name": "Bran Holt",
        "character_slug": "bran-holt",
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
        base_form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values = {
        **base_form_values,
        "species_feat_1": _field_value_for_label(context, "species_feat_1", "Embersworn Initiate"),
    }

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    feat_spell_field = _field_name_for_label(context, "Feat Spell 1")
    form_values[feat_spell_field] = _field_value_for_label(context, feat_spell_field, "Light")

    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        form_values,
        campaign_page_records=campaign_page_records,
    )
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert feat_spell_field in _builder_field_names(context)
    assert definition.spellcasting["spellcasting_class"] == ""
    assert "Detect Magic (Always prepared)" in context["preview"]["spells"]
    assert any("Light" in spell_line for spell_line in context["preview"]["spells"])
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["systems_ref"]["slug"] == detect_magic.slug
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Light"]["systems_ref"]["slug"] == light.slug
def test_level_one_builder_clears_stale_campaign_feat_spell_support_fields_after_feat_change():
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
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={
            "skill_proficiencies": [{"insight": True, "religion": True}],
            "language_proficiencies": [{"anyStandard": 2}],
        },
    )
    alert = _systems_entry("feat", "phb-feat-alert", "Alert")
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    message = _systems_entry(
        "spell",
        "phb-spell-message",
        "Message",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [alert],
            "subclass": [],
            "item": [],
            "spell": [light, message, detect_magic],
        },
        class_progression=[],
    )
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/embersworn-initiate",
            "Embersworn Initiate",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Embersworn Initiate",
                    "description_markdown": "You learn a few ember-bound tricks.",
                    "activation_type": "special",
                    "spell_support": [
                        {
                            "grants": {"_": [{"spell": "Detect Magic", "always_prepared": True, "ritual": True}]},
                            "choices": {
                                "_": [
                                    {
                                        "category": "granted",
                                        "options": ["Light", "Message"],
                                        "count": 1,
                                        "label_prefix": "Feat Spell",
                                        "mark": "Granted",
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
    ]
    base_form_values = {
        "name": "Bran Holt",
        "character_slug": "bran-holt",
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
        base_form_values,
        campaign_page_records=campaign_page_records,
    )
    selected_values = {
        **base_form_values,
        "species_feat_1": _field_value_for_label(context, "species_feat_1", "Embersworn Initiate"),
    }
    context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        selected_values,
        campaign_page_records=campaign_page_records,
    )
    feat_spell_field = _field_name_for_label(context, "Feat Spell 1")
    selected_values[feat_spell_field] = _field_value_for_label(context, feat_spell_field, "Light")

    stale_values = {
        **selected_values,
        "species_feat_1": _field_value_for_label(context, "species_feat_1", "Alert"),
    }
    stale_context = build_level_one_builder_context(
        systems_service,
        "linden-pass",
        stale_values,
        campaign_page_records=campaign_page_records,
    )

    assert feat_spell_field not in _builder_field_names(stale_context)
    assert stale_context["values"].get(feat_spell_field, "") == ""
def test_normalize_definition_to_native_model_applies_hourglass_pendant_spell_and_resource_bonus():
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

    item_catalog = _build_item_catalog([hourglass_pendant])

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=_build_spell_catalog([gift_of_alacrity]),
    )
    resources_by_id = {resource["id"]: resource for resource in normalized.resource_templates}
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}
    source_rows = {
        row["source_row_id"]: row
        for row in list(normalized.spellcasting.get("source_rows") or [])
    }

    assert resources_by_id["chronal-shift"]["max"] == 3
    assert resources_by_id["chronal-shift"]["initial_current"] == 3
    assert campaign_item_special_effect_metadata("Hourglass Pendant") == {}
    assert spells_by_name["Gift of Alacrity"]["spell_source_row_id"] == "spell-source:item:hourglass-pendant"
    assert spells_by_name["Gift of Alacrity"]["spell_access_type"] == "free_cast"
    assert spells_by_name["Gift of Alacrity"]["spell_access_uses"] == 1
    assert spells_by_name["Gift of Alacrity"]["spell_access_reset_on"] == "long_rest"
    assert source_rows["spell-source:item:hourglass-pendant"]["title"] == "Hourglass Pendant"
    assert source_rows["spell-source:item:hourglass-pendant"]["spellcasting_ability"] == "Intelligence"
@pytest.mark.parametrize(
    ("item_name", "page_ref", "spell_entry", "ability_key", "expected_spell_name", "explicit_mechanics", "expected_rule_title"),
    [
        (
            "Censer of Last Light",
            "items/censer-of-last-light",
            _systems_entry("spell", "phb-spell-spare-the-dying", "Spare the Dying", metadata={"level": 0}),
            "wis",
            "Spare the Dying",
            {
                "spell_support": [
                    {
                        "source": {
                            "id": "spell-source:item:censer-of-last-light",
                            "title": "Censer of Last Light",
                            "kind": "item",
                            "ability_key": "wis",
                        },
                        "grants": {
                            "_": [
                                {
                                    "spell": "Spare the Dying",
                                    "mark": "Cantrip",
                                    "access_type": "at_will",
                                }
                            ]
                        },
                    }
                ],
            },
            "",
        ),
        (
            "Staff of the Crescent Moon",
            "items/staff-of-the-crescent-moon",
            _systems_entry("spell", "phb-spell-sleep", "Sleep", metadata={"level": 1}),
            "cha",
            "Sleep",
            {
                "spell_support": [
                    {
                        "source": {
                            "id": "spell-source:item:staff-of-the-crescent-moon",
                            "title": "Staff of the Crescent Moon",
                            "kind": "item",
                            "ability_key": "cha",
                        },
                        "grants": {
                            "_": [
                                {
                                    "spell": "Sleep",
                                    "access_type": "free_cast",
                                    "access_uses": 1,
                                    "access_reset_on": "long_rest",
                                }
                            ]
                        },
                    }
                ],
                "defensive_rules": [
                    {
                        "id": "item:staff-of-the-crescent-moon:sleep-ward",
                        "title": "Staff of the Crescent Moon",
                        "condition": "Applies only while the staff is equipped and attuned.",
                        "effects": [
                            {
                                "kind": "immunity",
                                "label": "Sleep ward",
                                "summary": "You can't be magically put to sleep.",
                            }
                        ],
                    }
                ],
            },
            "Staff of the Crescent Moon",
        ),
    ],
)
def test_normalize_definition_to_native_model_applies_campaign_item_spell_support(
    item_name,
    page_ref,
    spell_entry,
    ability_key,
    expected_spell_name,
    explicit_mechanics,
    expected_rule_title,
):
    item_entry = _systems_entry(
        "item",
        f"custom-linden-pass-{slugify(item_name)}",
        item_name,
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title=item_name,
            body_markdown="*Wondrous item, rare (requires attunement)*",
            explicit_mechanics=explicit_mechanics,
            source_page_ref=page_ref,
            review_status="approved",
        ),
    )
    definition = _minimal_character_definition("glenn-hakewood", "Glenn Hakewood")
    definition.equipment_catalog = [
        {
            "id": f"{slugify(item_name)}-1",
            "name": item_name,
            "default_quantity": 1,
            "weight": "--",
            "notes": "",
            "is_equipped": True,
            "is_attuned": True,
            "systems_ref": _systems_ref(item_entry),
        }
    ]
    item_catalog = _build_item_catalog([item_entry])

    normalized = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=_build_spell_catalog([spell_entry]),
    )
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}
    source_rows = {
        row["source_row_id"]: row
        for row in list(normalized.spellcasting.get("source_rows") or [])
    }
    source_row_id = f"spell-source:item:{slugify(item_name)}"

    assert campaign_item_special_effect_metadata(item_name) == {}
    assert spells_by_name[expected_spell_name]["spell_source_row_id"] == source_row_id
    assert source_rows[source_row_id]["title"] == item_name
    assert source_rows[source_row_id]["spellcasting_ability"] == ABILITY_LABELS[ability_key]
    if expected_spell_name == "Spare the Dying":
        assert spells_by_name[expected_spell_name]["spell_access_type"] == "at_will"
    else:
        assert spells_by_name[expected_spell_name]["spell_access_type"] == "free_cast"
        assert spells_by_name[expected_spell_name]["spell_access_uses"] == 1
        assert spells_by_name[expected_spell_name]["spell_access_reset_on"] == "long_rest"
    defensive_rule_titles = [
        rule["title"]
        for rule in list((normalized.stats.get("defensive_state") or {}).get("rules") or [])
    ]
    assert (expected_rule_title in defensive_rule_titles) is bool(expected_rule_title)
def test_normalize_definition_to_native_model_derives_supported_imported_spell_math_from_resolved_class():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "spellcasting_ability": "int",
            "slot_progression": [
                [{"level": 1, "max_slots": 2}],
                [{"level": 1, "max_slots": 3}],
                [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 2}],
                [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 3}],
                [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 3}, {"level": 3, "max_slots": 2}],
            ],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [human],
            "background": [sage],
        },
        class_progression=[],
    )
    definition = _minimal_imported_character_definition("olin-itador", "Olin Itador")
    definition.profile["class_level_text"] = "Wizard 5"
    definition.profile["classes"] = [
        {
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 5,
            "systems_ref": {
                "entry_key": wizard.entry_key,
                "entry_type": wizard.entry_type,
                "title": wizard.title,
                "slug": wizard.slug,
                "source_id": wizard.source_id,
            },
        }
    ]
    definition.profile["class_ref"] = {
        "entry_key": wizard.entry_key,
        "entry_type": wizard.entry_type,
        "title": wizard.title,
        "slug": wizard.slug,
        "source_id": wizard.source_id,
    }
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": human.entry_key,
        "entry_type": human.entry_type,
        "title": human.title,
        "slug": human.slug,
        "source_id": human.source_id,
    }
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = {
        "entry_key": sage.entry_key,
        "entry_type": sage.entry_type,
        "title": sage.title,
        "slug": sage.slug,
        "source_id": sage.source_id,
    }
    definition.stats["proficiency_bonus"] = 2
    definition.stats["ability_scores"]["int"] = {"score": 18, "modifier": 4, "save_bonus": 4}
    definition.spellcasting = {
        "spellcasting_class": "Wizard",
        "spellcasting_ability": "Intelligence",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 4}],
        "spells": [],
    }

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.stats["proficiency_bonus"] == 3
    assert normalized.stats["ability_scores"]["int"]["save_bonus"] == 7
    assert normalized.spellcasting["spell_save_dc"] == 15
    assert normalized.spellcasting["spell_attack_bonus"] == 7
    assert normalized.spellcasting["slot_progression"] == [
        {"level": 1, "max_slots": 4},
        {"level": 2, "max_slots": 3},
        {"level": 3, "max_slots": 2},
    ]
def test_level_one_builder_surfaces_and_applies_magic_initiate_feat_spells():
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
    magic_initiate = _systems_entry(
        "feat",
        "phb-feat-magic-initiate",
        "Magic Initiate",
        metadata={
            "additional_spells": [
                {
                    "name": "Cleric Spells",
                    "ability": "wis",
                    "known": {"_": [{"choose": "level=0|class=Cleric", "count": 2}]},
                    "innate": {"_": {"daily": {"1": [{"choose": "level=1|class=Cleric"}]}}},
                },
                {
                    "name": "Wizard Spells",
                    "ability": "int",
                    "known": {"_": [{"choose": "level=0|class=Wizard", "count": 2}]},
                    "innate": {"_": {"daily": {"1": [{"choose": "level=1|class=Wizard"}]}}},
                },
            ]
        },
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    guidance = _systems_entry(
        "spell",
        "phb-spell-guidance",
        "Guidance",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Cleric"]}},
    )
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Cleric", "Wizard"]}},
    )
    thaumaturgy = _systems_entry(
        "spell",
        "phb-spell-thaumaturgy",
        "Thaumaturgy",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Cleric"]}},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Wizard"]}},
    )
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Cleric"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "level": 1,
            "class_lists": {"PHB": ["Cleric", "Wizard"]},
            "ritual": True,
        },
    )
    magic_missile = _systems_entry(
        "spell",
        "phb-spell-magic-missile",
        "Magic Missile",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [magic_initiate],
            "subclass": [],
            "item": [],
            "spell": [guidance, light, thaumaturgy, mage_hand, cure_wounds, detect_magic, magic_missile],
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
        "name": "Spell Dabbler",
        "character_slug": "spell-dabbler",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": magic_initiate.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_spell_source_1")["label"] == "Magic Initiate Spell List"

    form_values["feat_species_feat_1_spell_source_1"] = _field_value_for_label(
        context,
        "feat_species_feat_1_spell_source_1",
        "Cleric Spells",
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)

    assert _field_value_for_label(context, "feat_species_feat_1_spell_known_1_1", "Guidance")
    assert _field_value_for_label(context, "feat_species_feat_1_spell_granted_1_1", "Cure Wounds")

    form_values.update(
        {
            "feat_species_feat_1_spell_known_1_1": _field_value_for_label(
                context,
                "feat_species_feat_1_spell_known_1_1",
                "Guidance",
            ),
            "feat_species_feat_1_spell_known_1_2": _field_value_for_label(
                context,
                "feat_species_feat_1_spell_known_1_2",
                "Light",
            ),
            "feat_species_feat_1_spell_granted_1_1": _field_value_for_label(
                context,
                "feat_species_feat_1_spell_granted_1_1",
                "Cure Wounds",
            ),
        }
    )

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert definition.spellcasting["spellcasting_class"] == ""
    assert spells_by_name["Guidance"]["mark"] == "Cantrip"
    assert spells_by_name["Guidance"]["is_bonus_known"] is True
    assert spells_by_name["Cure Wounds"]["mark"] == "1 / Long Rest"
    assert "Cure Wounds (1 / Long Rest)" in context["preview"]["spells"]
@pytest.mark.parametrize("case", _FREE_CAST_FEAT_CASES)
def test_level_one_builder_applies_supported_free_cast_feat_spells(case: dict[str, object]):
    fixture = _build_free_cast_feat_test_fixture()
    systems_service = fixture["systems_service"]
    fighter = fixture["fighter"]
    variant_human = fixture["variant_human"]
    acolyte = fixture["acolyte"]

    form_values = {
        "name": f"{case['title']} Hero",
        "character_slug": f"{str(case['title']).lower().replace(' ', '-')}-hero",
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
        "int": "14",
        "wis": "13",
        "cha": "14",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    form_values["species_feat_1"] = _field_value_for_label(context, "species_feat_1", str(case["title"]))
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    _apply_free_cast_feat_field_choices(
        form_values=form_values,
        context=context,
        prefix="feat_species_feat_1_",
        case=case,
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    if not dict(case.get("field_choices") or {}):
        assert not any(
            name.startswith("feat_species_feat_1_spell_")
            for name in _builder_field_names(context)
        )

    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    assert definition.spellcasting["spellcasting_class"] == ""
    _assert_free_cast_feat_spellcasting(definition.spellcasting, case)
    for preview_entry in list(case.get("expected_preview") or []):
        assert preview_entry in list(context["preview"]["spells"] or [])
def test_level_one_builder_applies_ritual_caster_with_ritual_book_manager():
    fixture = _build_ritual_caster_test_fixture()
    systems_service = fixture["systems_service"]
    fighter = fixture["fighter"]
    variant_human = fixture["variant_human"]
    acolyte = fixture["acolyte"]

    form_values = {
        "name": "Ritual Keeper",
        "character_slug": "ritual-keeper",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": fixture["ritual_caster"].slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "14",
        "wis": "12",
        "cha": "10",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_spell_source_1")["label"] == "Ritual Caster Spell List"

    form_values["feat_species_feat_1_spell_source_1"] = _field_value_for_label(
        context,
        "feat_species_feat_1_spell_source_1",
        "Wizard Spells",
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)

    first_ritual_field = _find_builder_field(context, "feat_species_feat_1_spell_managed_1_1")
    ritual_options = {option["label"] for option in list(first_ritual_field.get("options") or [])}
    assert {"Alarm", "Detect Magic", "Find Familiar", "Identify"} <= ritual_options
    assert "Magic Missile" not in ritual_options

    form_values["feat_species_feat_1_spell_managed_1_1"] = _field_value_for_label(
        context,
        "feat_species_feat_1_spell_managed_1_1",
        "Detect Magic",
    )
    form_values["feat_species_feat_1_spell_managed_1_2"] = _field_value_for_label(
        context,
        "feat_species_feat_1_spell_managed_1_2",
        "Identify",
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    ritual_caster_feature = next(feature for feature in definition.features if feature["name"] == "Ritual Caster")
    spell_manager = dict(ritual_caster_feature.get("spell_manager") or {})
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    source_rows = [dict(row or {}) for row in list(definition.spellcasting.get("source_rows") or []) if isinstance(row, dict)]

    assert spell_manager["mode"] == "ritual_book"
    assert spell_manager["spell_list_class_name"] == "Wizard"
    assert spell_manager["title"] == "Ritual Caster (Wizard)"
    assert spell_manager["spellcasting_ability"] == "Intelligence"
    assert spell_manager["max_spell_level_formula"] == "ritual_caster_half_level_rounded_up"
    assert {spell["name"] for spell in definition.spellcasting["spells"]} == {"Detect Magic", "Identify"}
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"].get("is_bonus_known") in {False, None}
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert spells_by_name["Identify"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert len(source_rows) == 1
    assert source_rows[0]["spell_mode"] == "ritual_book"
    assert source_rows[0]["spell_list_class_name"] == "Wizard"
    assert source_rows[0]["spell_save_dc"] == 12
    assert source_rows[0]["spell_attack_bonus"] == 4
    assert "Detect Magic (Ritual Book)" in list(context["preview"]["spells"] or [])
    assert "Identify (Ritual Book)" in list(context["preview"]["spells"] or [])
def test_level_one_builder_clears_stale_species_feat_and_spell_fields_after_species_change():
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
    elf = _systems_entry(
        "race",
        "phb-race-elf",
        "Elf",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True, "elvish": True}]},
    )
    acolyte = _systems_entry(
        "background",
        "phb-background-acolyte",
        "Acolyte",
        metadata={"skill_proficiencies": [{"insight": True, "religion": True}]},
    )
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
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
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
            "race": [variant_human, elf],
            "background": [acolyte],
            "feat": [magic_initiate],
            "subclass": [],
            "item": [],
            "spell": [guidance, cure_wounds],
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

    base_form = {
        "name": "Shifted Hero",
        "character_slug": "shifted-hero",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": magic_initiate.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    base_context = build_level_one_builder_context(systems_service, "linden-pass", base_form)
    stale_form = {
        **base_form,
        "species_slug": elf.slug,
        "feat_species_feat_1_spell_known_1_1": _field_value_for_label(
            base_context,
            "feat_species_feat_1_spell_known_1_1",
            "Guidance",
        ),
        "feat_species_feat_1_spell_granted_1_1": _field_value_for_label(
            base_context,
            "feat_species_feat_1_spell_granted_1_1",
            "Cure Wounds",
        ),
    }

    stale_context = build_level_one_builder_context(systems_service, "linden-pass", stale_form)
    field_names = _builder_field_names(stale_context)
    definition, _ = build_level_one_character_definition("linden-pass", stale_context, stale_form)

    assert "species_feat_1" not in field_names
    assert not any(name.startswith("feat_species_feat_1_") for name in field_names)
    assert stale_context["values"].get("species_feat_1", "") == ""
    assert stale_context["values"].get("feat_species_feat_1_spell_known_1_1", "") == ""
    assert stale_context["values"].get("class_skill_1", "") == "athletics"
    assert stale_context["values"].get("class_skill_2", "") == "history"
    assert stale_context["preview"]["spells"] == []
    assert definition.spellcasting["spells"] == []
    assert all(feature["name"] != "Magic Initiate" for feature in definition.features)
def test_level_one_builder_applies_metamagic_adept_tracker():
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
    metamagic_adept = _systems_entry(
        "feat",
        "tce-feat-metamagic-adept",
        "Metamagic Adept",
        source_id="TCE",
        metadata={
            "optionalfeature_progression": [
                {"name": "Metamagic", "featureType": ["MM"], "progression": {"*": 2}}
            ]
        },
    )
    quickened_spell = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-quickened-spell",
        "Quickened Spell",
        metadata={"feature_type": ["MM"]},
    )
    subtle_spell = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-subtle-spell",
        "Subtle Spell",
        metadata={"feature_type": ["MM"]},
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [metamagic_adept],
            "subclass": [],
            "optionalfeature": [quickened_spell, subtle_spell],
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
        "name": "Ari Vale",
        "character_slug": "ari-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": metamagic_adept.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    assert _find_builder_field(context, "feat_species_feat_1_optionalfeature_1_1")["label"] == "Metamagic Adept Metamagic 1"
    form_values.update(
        {
            "feat_species_feat_1_optionalfeature_1_1": _field_value_for_label(
                context,
                "feat_species_feat_1_optionalfeature_1_1",
                "Quickened Spell",
            ),
            "feat_species_feat_1_optionalfeature_1_2": _field_value_for_label(
                context,
                "feat_species_feat_1_optionalfeature_1_2",
                "Subtle Spell",
            ),
        }
    )
    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    feature_names = {feature["name"] for feature in definition.features}
    metamagic_feature = next(feature for feature in definition.features if feature["name"] == "Metamagic Adept")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "Metamagic Adept Sorcery Points: 2 / 2 (Long Rest)" in context["preview"]["resources"]
    assert {"Quickened Spell", "Subtle Spell"} <= feature_names
    assert metamagic_feature["tracker_ref"] == "metamagic-adept"
    assert resources_by_id["metamagic-adept"]["max"] == 2
    assert resources_by_id["metamagic-adept"]["reset_on"] == "long_rest"
def test_level_one_builder_applies_gift_of_the_metallic_dragon_spell_and_tracker():
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
    gift_of_the_metallic_dragon = _systems_entry(
        "feat",
        "ftd-feat-gift-of-the-metallic-dragon",
        "Gift of the Metallic Dragon",
        source_id="FTD",
        metadata={
            "additional_spells": [
                {
                    "ability": {"choose": ["int", "wis", "cha"]},
                    "innate": {"_": {"daily": {"1": ["Cure Wounds"]}}},
                }
            ]
        },
    )
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [gift_of_the_metallic_dragon],
            "subclass": [],
            "item": [],
            "spell": [cure_wounds],
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
        "name": "Ari Vale",
        "character_slug": "ari-vale",
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": gift_of_the_metallic_dragon.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)

    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    gift_feature = next(feature for feature in definition.features if feature["name"] == "Gift of the Metallic Dragon")
    resources_by_id = {resource["id"]: resource for resource in definition.resource_templates}

    assert "Cure Wounds (1 / Long Rest)" in context["preview"]["spells"]
    assert "Protective Wings: 2 / 2 (Long Rest)" in context["preview"]["resources"]
    assert spells_by_name["Cure Wounds"]["mark"] == "1 / Long Rest"
    assert gift_feature["tracker_ref"] == "protective-wings"
    assert resources_by_id["protective-wings"]["max"] == 2
    assert resources_by_id["protective-wings"]["reset_on"] == "long_rest"
def test_level_one_builder_populates_starting_equipment_spells_and_currency():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "starting_proficiencies": {
                "armor": [],
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "insight"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"a": ["quarterstaff|phb"], "b": ["dagger|phb"]},
                    {"a": ["component pouch|phb"], "b": [{"equipmentType": "focusSpellcastingArcane"}]},
                    {"a": ["scholar's pack|phb"], "b": ["explorer's pack|phb"]},
                    {"_": ["spellbook|phb"]},
                ]
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
        body={"entries": [{"name": "Feature: Resourceful", "entries": ["You adapt quickly to new situations."]}]},
    )
    hermit = _systems_entry(
        "background",
        "phb-background-hermit",
        "Hermit",
        metadata={
            "skill_proficiencies": [{"medicine": True, "religion": True}],
            "tool_proficiencies": ["Herbalism Kit"],
            "starting_equipment": [
                {
                    "_": [
                        {
                            "item": "map or scroll case|phb",
                            "displayName": "scroll case stuffed full of notes from your studies or prayers",
                        },
                        {"item": "blanket|phb", "displayName": "winter blanket"},
                        "common clothes|phb",
                        "herbalism kit|phb",
                        {"value": 500},
                    ]
                }
            ],
        },
        body={
            "entries": [
                {
                    "name": "Feature: Discovery",
                    "entries": ["Your quiet seclusion has yielded a singular insight."],
                    "data": {"isFeature": True},
                }
            ]
        },
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
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4, "type": "M"})
    component_pouch = _systems_entry("item", "phb-item-component-pouch", "Component Pouch", metadata={"weight": 2})
    crystal = _systems_entry("item", "phb-item-crystal", "Crystal", metadata={"weight": 1, "type": "SCF"})
    wand = _systems_entry("item", "phb-item-wand", "Wand", metadata={"weight": 1, "type": "SCF"})
    scholars_pack = _systems_entry("item", "phb-item-scholars-pack", "Scholar's Pack", metadata={"weight": 10})
    explorers_pack = _systems_entry("item", "phb-item-explorers-pack", "Explorer's Pack", metadata={"weight": 12})
    spellbook = _systems_entry("item", "phb-item-spellbook", "Spellbook", metadata={"weight": 3})
    scroll_case = _systems_entry("item", "phb-item-map-or-scroll-case", "Map or Scroll Case", metadata={"weight": 1})
    blanket = _systems_entry("item", "phb-item-blanket", "Blanket", metadata={"weight": 3})
    common_clothes = _systems_entry("item", "phb-item-common-clothes", "Common Clothes", metadata={"weight": 3})
    herbalism_kit = _systems_entry("item", "phb-item-herbalism-kit", "Herbalism Kit", metadata={"weight": 3, "type": "AT"})

    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "touch"},
            "components": {"v": True, "m": "a firefly or phosphorescent moss"},
            "duration": [{"type": "timed", "duration": {"type": "hour", "amount": 1}}],
        },
        source_page="255",
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "point", "distance": {"type": "feet", "amount": 30}},
            "components": {"v": True, "s": True},
            "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 1}}],
        },
        source_page="256",
    )
    message = _systems_entry(
        "spell",
        "phb-spell-message",
        "Message",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "point", "distance": {"type": "feet", "amount": 120}},
            "components": {"v": True, "s": True, "m": "a short piece of copper wire"},
            "duration": [{"type": "timed", "duration": {"type": "round", "amount": 1}}],
        },
        source_page="259",
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "self"},
            "components": {"v": True, "s": True},
            "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 10}, "concentration": True}],
        },
        source_page="231",
    )
    find_familiar = _systems_entry(
        "spell",
        "phb-spell-find-familiar",
        "Find Familiar",
        metadata={
            "casting_time": [{"number": 1, "unit": "hour"}],
            "range": {"type": "point", "distance": {"type": "feet", "amount": 10}},
            "components": {"v": True, "s": True, "m": "10 gp worth of charcoal, incense, and herbs"},
            "duration": [{"type": "instant"}],
        },
        source_page="240",
    )
    mage_armor = _systems_entry(
        "spell",
        "phb-spell-mage-armor",
        "Mage Armor",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "touch"},
            "components": {"v": True, "s": True, "m": "a piece of cured leather"},
            "duration": [{"type": "timed", "duration": {"type": "hour", "amount": 8}}],
        },
        source_page="256",
    )
    magic_missile = _systems_entry(
        "spell",
        "phb-spell-magic-missile",
        "Magic Missile",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "point", "distance": {"type": "feet", "amount": 120}},
            "components": {"v": True, "s": True},
            "duration": [{"type": "instant"}],
        },
        source_page="257",
    )
    shield = _systems_entry(
        "spell",
        "phb-spell-shield",
        "Shield",
        metadata={
            "casting_time": [{"number": 1, "unit": "reaction"}],
            "range": {"type": "self"},
            "components": {"v": True, "s": True},
            "duration": [{"type": "timed", "duration": {"type": "round", "amount": 1}}],
        },
        source_page="275",
    )
    sleep = _systems_entry(
        "spell",
        "phb-spell-sleep",
        "Sleep",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "point", "distance": {"type": "feet", "amount": 90}},
            "components": {"v": True, "s": True, "m": "a pinch of fine sand, rose petals, or a cricket"},
            "duration": [{"type": "timed", "duration": {"type": "minute", "amount": 1}}],
        },
        source_page="276",
    )
    thunderwave = _systems_entry(
        "spell",
        "phb-spell-thunderwave",
        "Thunderwave",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "range": {"type": "self"},
            "components": {"v": True, "s": True},
            "duration": [{"type": "instant"}],
        },
        source_page="282",
    )

    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [human],
            "background": [hermit],
            "feat": [],
            "subclass": [],
            "item": [
                quarterstaff,
                component_pouch,
                crystal,
                wand,
                scholars_pack,
                explorers_pack,
                spellbook,
                scroll_case,
                blanket,
                common_clothes,
                herbalism_kit,
            ],
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
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Arcane Recovery", "entry": arcane_recovery, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Mira Vale",
        "character_slug": "mira-vale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": wizard.slug,
        "species_slug": human.slug,
        "background_slug": hermit.slug,
        "class_skill_1": "arcana",
        "class_skill_2": "history",
        "str": "8",
        "dex": "14",
        "con": "13",
        "int": "16",
        "wis": "12",
        "cha": "10",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    form_values = {
        **base_form_values,
        "class_equipment_1": _field_value_for_label(context, "class_equipment_1", "Quarterstaff"),
        "class_equipment_2": _field_value_for_label(context, "class_equipment_2", "Crystal"),
        "class_equipment_3": _field_value_for_label(context, "class_equipment_3", "Scholar's Pack"),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Mage Hand"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Message"),
        "wizard_spellbook_1": _field_value_for_label(context, "wizard_spellbook_1", "Detect Magic"),
        "wizard_spellbook_2": _field_value_for_label(context, "wizard_spellbook_2", "Find Familiar"),
        "wizard_spellbook_3": _field_value_for_label(context, "wizard_spellbook_3", "Mage Armor"),
        "wizard_spellbook_4": _field_value_for_label(context, "wizard_spellbook_4", "Magic Missile"),
        "wizard_spellbook_5": _field_value_for_label(context, "wizard_spellbook_5", "Shield"),
        "wizard_spellbook_6": _field_value_for_label(context, "wizard_spellbook_6", "Sleep"),
        "wizard_prepared_1": _field_value_for_label(context, "wizard_prepared_1", "Detect Magic"),
        "wizard_prepared_2": _field_value_for_label(context, "wizard_prepared_2", "Mage Armor"),
        "wizard_prepared_3": _field_value_for_label(context, "wizard_prepared_3", "Magic Missile"),
        "wizard_prepared_4": _field_value_for_label(context, "wizard_prepared_4", "Shield"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, import_metadata = build_level_one_character_definition("linden-pass", context, form_values)
    initial_state = build_initial_state(definition)

    equipment_names = {item["name"] for item in definition.equipment_catalog}
    inventory_names = {item["name"] for item in initial_state["inventory"]}
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}
    attacks_by_name = {attack["name"]: attack for attack in definition.attacks}
    resource_templates_by_id = {resource["id"]: resource for resource in definition.resource_templates}
    state_resources_by_id = {resource["id"]: resource for resource in initial_state["resources"]}

    assert context["preview"]["starting_currency"] == "5 gp"
    assert "Quarterstaff" in context["preview"]["equipment"]
    assert "Quarterstaff (+1, 1d6-1 bludgeoning)" in context["preview"]["attacks"]
    assert "Quarterstaff (two-handed) (+1, 1d8-1 bludgeoning)" in context["preview"]["attacks"]
    assert "Arcane Recovery: 1 / 1 (Long Rest)" in context["preview"]["resources"]
    assert any("Magic Missile" in spell_name for spell_name in context["preview"]["spells"])
    assert definition.profile["class_level_text"] == "Wizard 1"
    assert definition.spellcasting["spellcasting_class"] == "Wizard"
    assert definition.spellcasting["spellcasting_ability"] == "Intelligence"
    assert definition.spellcasting["spell_save_dc"] == 13
    assert definition.spellcasting["spell_attack_bonus"] == 5
    assert equipment_names >= {
        "Quarterstaff",
        "Crystal",
        "Scholar's Pack",
        "Spellbook",
        "scroll case stuffed full of notes from your studies or prayers",
        "winter blanket",
        "Common Clothes",
        "Herbalism Kit",
        "5 gp",
    }
    assert "5 gp" not in inventory_names
    assert initial_state["currency"]["gp"] == 5
    assert attacks_by_name["Quarterstaff"]["notes"] == ""
    assert attacks_by_name["Quarterstaff (two-handed)"]["damage"] == "1d8-1 bludgeoning"
    assert attacks_by_name["Quarterstaff (two-handed)"]["mode_key"] == "weapon:two-handed"
    assert attacks_by_name["Quarterstaff (two-handed)"]["variant_label"] == "two-handed"
    assert spells_by_name["Light"]["mark"] == "Cantrip"
    assert spells_by_name["Magic Missile"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Find Familiar"]["mark"] == "Spellbook"
    assert spells_by_name["Detect Magic"]["reference"] == "p. 231"
    assert spells_by_name["Message"]["components"] == "V, S, M (a short piece of copper wire)"
    assert resource_templates_by_id["arcane-recovery"]["max"] == 1
    assert state_resources_by_id["arcane-recovery"]["current"] == 1
    assert import_metadata.parser_version == CHARACTER_BUILDER_VERSION
def test_level_one_builder_adds_structured_subclass_prepared_spells():
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
    life_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-life-domain",
        "Life Domain",
        metadata={
            "class_name": "Cleric",
            "class_source": "PHB",
            "additional_spells": [
                {
                    "prepared": {
                        "1": ["Bless", "Cure Wounds"],
                        "3": ["Lesser Restoration", "Spiritual Weapon"],
                    }
                }
            ],
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
    spellcasting_feature = _systems_entry(
        "classfeature",
        "phb-classfeature-spellcasting",
        "Spellcasting",
        metadata={"level": 1},
    )
    divine_domain = _systems_entry(
        "classfeature",
        "phb-classfeature-divine-domain",
        "Divine Domain",
        metadata={"level": 1},
    )
    disciple_of_life = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-disciple-of-life",
        "Disciple of Life",
        metadata={"level": 1, "class_name": "Cleric", "class_source": "PHB", "subclass_name": "Life Domain"},
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [life_domain],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                bless,
                cure_wounds,
                detect_magic,
                guiding_bolt,
                healing_word,
                shield_of_faith,
            ],
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
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Disciple of Life", "entry": disciple_of_life, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Aster Vale",
        "character_slug": "aster-vale",
        "alignment": "Lawful Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": life_domain.slug,
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

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    prepared_spell_field = next(
        field
        for section in context["choice_sections"]
        if section["title"] == "Spell Choices"
        for field in section["fields"]
        if field["name"] == "spell_level_one_1"
    )
    option_labels = {option["label"] for option in prepared_spell_field["options"]}

    assert "Bless" not in option_labels
    assert "Cure Wounds" not in option_labels

    form_values = {
        **base_form_values,
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Shield of Faith"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Bless (Always prepared)" in context["preview"]["spells"]
    assert "Cure Wounds (Always prepared)" in context["preview"]["spells"]
    assert spells_by_name["Detect Magic"]["mark"] == "Prepared"
    assert spells_by_name["Bless"]["is_always_prepared"] is True
    assert spells_by_name["Cure Wounds"]["is_always_prepared"] is True
def test_automatic_prepared_spells_do_not_fall_back_to_subclass_title_only():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={"subclass_title": "Divine Domain"},
    )
    life_domain_without_spell_metadata = _systems_entry(
        "subclass",
        "phb-subclass-cleric-life-domain",
        "Life Domain",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"level": 1})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1})

    automatic_keys = _automatic_prepared_spell_lookup_keys(
        selected_class=cleric,
        selected_subclass=life_domain_without_spell_metadata,
        spell_catalog=_build_spell_catalog([bless, cure_wounds]),
        target_level=1,
        feature_entries=[],
    )

    assert automatic_keys == set()
def test_level_one_builder_adds_body_only_grave_domain_prepared_spells():
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
    grave_domain = _systems_entry(
        "subclass",
        "xge-subclass-cleric-grave-domain",
        "Grave Domain",
        source_id="XGE",
        metadata={
            "class_name": "Cleric",
            "class_source": "PHB",
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
    spellcasting_feature = _systems_entry(
        "classfeature",
        "phb-classfeature-spellcasting",
        "Spellcasting",
        metadata={"level": 1},
    )
    divine_domain = _systems_entry(
        "classfeature",
        "phb-classfeature-divine-domain",
        "Divine Domain",
        metadata={"level": 1},
        body={
            "entries": [
                {
                    "name": "Domain Spells",
                    "entries": [
                        "Each domain has a list of spells. Once you gain a domain spell, you always have it prepared, and it doesn't count against the number of spells you can prepare each day.",
                    ],
                }
            ]
        },
    )
    grave_domain_spells = _systems_entry(
        "subclassfeature",
        "xge-subclassfeature-grave-domain-spells",
        "Grave Domain Spells",
        source_id="XGE",
        metadata={
            "level": 1,
            "class_name": "Cleric",
            "class_source": "PHB",
            "subclass_name": "Grave Domain",
        },
        body={
            "entries": [
                "You gain domain spells at the cleric levels listed in the Grave Domain Spells table. See the Divine Domain class feature for how domain spells work.",
                {
                    "type": "table",
                    "caption": "Grave Domain Spells",
                    "colLabels": ["Cleric Level", "Spells"],
                    "rows": [
                        ["1st", "{@spell bane}, {@spell false life}"],
                        ["3rd", "{@spell gentle repose}, {@spell ray of enfeeblement}"],
                    ],
                },
            ]
        },
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    bane = _systems_entry("spell", "phb-spell-bane", "Bane", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    false_life = _systems_entry("spell", "phb-spell-false-life", "False Life", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [grave_domain],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                bane,
                false_life,
                detect_magic,
                guiding_bolt,
                healing_word,
                cure_wounds,
            ],
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
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Grave Domain Spells", "entry": grave_domain_spells, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Mira Voss",
        "character_slug": "mira-voss",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": grave_domain.slug,
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

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    prepared_spell_field = next(
        field
        for section in context["choice_sections"]
        if section["title"] == "Spell Choices"
        for field in section["fields"]
        if field["name"] == "spell_level_one_1"
    )
    option_labels = {option["label"] for option in prepared_spell_field["options"]}

    assert "Bane" not in option_labels
    assert "False Life" not in option_labels

    form_values = {
        **base_form_values,
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Cure Wounds"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Bane (Always prepared)" in context["preview"]["spells"]
    assert "False Life (Always prepared)" in context["preview"]["spells"]
    assert spells_by_name["Detect Magic"]["mark"] == "Prepared"
    assert spells_by_name["Bane"]["is_always_prepared"] is True
    assert spells_by_name["False Life"]["is_always_prepared"] is True
def test_level_one_builder_adds_known_spell_choice_fields_from_additional_spells():
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
    nature_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-nature-domain",
        "Nature Domain",
        metadata={
            "class_name": "Cleric",
            "class_source": "PHB",
            "additional_spells": [
                {
                    "known": {
                        "1": {
                            "_": [
                                {"choose": "level=0|class=Druid"},
                            ]
                        }
                    },
                    "prepared": {
                        "1": ["Animal Friendship", "Speak with Animals"],
                    },
                }
            ],
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    nature_domain_feature = _systems_entry("classfeature", "phb-classfeature-divine-domain", "Divine Domain", metadata={"level": 1})
    nature_acolyte = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-nature-acolyte",
        "Nature Acolyte",
        metadata={"level": 1, "class_name": "Cleric", "class_source": "PHB", "subclass_name": "Nature Domain"},
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0})
    animal_friendship = _systems_entry("spell", "phb-spell-animal-friendship", "Animal Friendship", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    speak_with_animals = _systems_entry("spell", "phb-spell-speak-with-animals", "Speak with Animals", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [nature_domain],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                druidcraft,
                shillelagh,
                animal_friendship,
                speak_with_animals,
                detect_magic,
                guiding_bolt,
                healing_word,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Divine Domain", "entry": nature_domain_feature, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Nature Acolyte", "entry": nature_acolyte, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Rowan Vale",
        "character_slug": "rowan-vale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": nature_domain.slug,
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

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    granted_field = _find_builder_field(context, "bonus_spell_known_1_1")
    option_labels = {option["label"] for option in granted_field["options"]}

    assert option_labels >= {"Druidcraft", "Shillelagh"}

    form_values = {
        **base_form_values,
        "bonus_spell_known_1_1": _field_value_for_label(context, "bonus_spell_known_1_1", "Shillelagh"),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Shield of Faith"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    cantrip_labels = {option["label"] for option in _find_builder_field(context, "spell_cantrip_1")["options"]}
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Shillelagh" not in cantrip_labels
    assert "Shillelagh (Granted, Cantrip)" in context["preview"]["spells"]
    assert spells_by_name["Shillelagh"]["mark"] == "Cantrip"
    assert spells_by_name["Shillelagh"]["is_bonus_known"] is True
def test_level_one_builder_applies_feature_level_additional_spells():
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
    nature_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-nature-domain",
        "Nature Domain",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
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
    nature_domain_feature = _systems_entry("classfeature", "phb-classfeature-divine-domain", "Divine Domain", metadata={"level": 1})
    nature_acolyte = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-nature-acolyte",
        "Nature Acolyte",
        metadata={
            "level": 1,
            "class_name": "Cleric",
            "class_source": "PHB",
            "subclass_name": "Nature Domain",
            "additional_spells": [
                {
                    "known": {
                        "1": {
                            "_": [
                                {"choose": "level=0|class=Druid"},
                            ]
                        }
                    },
                    "prepared": {
                        "1": ["Animal Friendship", "Speak with Animals"],
                    },
                }
            ],
        },
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0})
    animal_friendship = _systems_entry("spell", "phb-spell-animal-friendship", "Animal Friendship", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    speak_with_animals = _systems_entry("spell", "phb-spell-speak-with-animals", "Speak with Animals", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [nature_domain],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                druidcraft,
                shillelagh,
                animal_friendship,
                speak_with_animals,
                detect_magic,
                guiding_bolt,
                healing_word,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Divine Domain", "entry": nature_domain_feature, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Nature Acolyte", "entry": nature_acolyte, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Rowan Vale",
        "character_slug": "rowan-vale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "subclass_slug": nature_domain.slug,
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

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    granted_field = _find_builder_field(context, "bonus_spell_known_1_1")
    granted_option_labels = {option["label"] for option in granted_field["options"]}
    prepared_option_labels = {option["label"] for option in _find_builder_field(context, "spell_level_one_1")["options"]}

    assert granted_option_labels >= {"Druidcraft", "Shillelagh"}
    assert "Animal Friendship" not in prepared_option_labels
    assert "Speak with Animals" not in prepared_option_labels

    form_values = {
        **base_form_values,
        "bonus_spell_known_1_1": _field_value_for_label(context, "bonus_spell_known_1_1", "Shillelagh"),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Shield of Faith"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Animal Friendship (Always prepared)" in context["preview"]["spells"]
    assert "Speak with Animals (Always prepared)" in context["preview"]["spells"]
    assert "Shillelagh (Granted, Cantrip)" in context["preview"]["spells"]
    assert spells_by_name["Animal Friendship"]["is_always_prepared"] is True
    assert spells_by_name["Speak with Animals"]["is_always_prepared"] is True
    assert spells_by_name["Shillelagh"]["is_bonus_known"] is True
def test_level_one_builder_applies_optionalfeature_additional_spells():
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    mystic_training = _systems_entry(
        "classfeature",
        "phb-classfeature-mystic-training",
        "Mystic Training",
        metadata={"level": 1},
    )
    druidic_initiate = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-druidic-initiate",
        "Druidic Initiate",
        metadata={
            "additional_spells": [
                {
                    "known": {"1": {"_": [{"choose": "level=0|class=Druid"}]}},
                    "prepared": {"1": ["Animal Friendship"]},
                }
            ]
        },
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0})
    animal_friendship = _systems_entry("spell", "phb-spell-animal-friendship", "Animal Friendship", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "optionalfeature": [druidic_initiate],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                druidcraft,
                shillelagh,
                animal_friendship,
                bless,
                detect_magic,
                guiding_bolt,
                healing_word,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {
                        "label": "Mystic Training",
                        "entry": mystic_training,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Druidic Initiate", "slug": druidic_initiate.slug},
                                    ]
                                }
                            ]
                        },
                    },
                ],
            }
        ],
    )
    base_form_values = {
        "name": "Sister Elm",
        "character_slug": "sister-elm",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "history",
        "class_skill_2": "medicine",
        "class_option_1": druidic_initiate.slug,
        "str": "10",
        "dex": "12",
        "con": "14",
        "int": "11",
        "wis": "16",
        "cha": "13",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    granted_field = _find_builder_field(context, "bonus_spell_known_1_1")
    granted_labels = {option["label"] for option in granted_field["options"]}
    form_values = {
        **base_form_values,
        "bonus_spell_known_1_1": _field_value_for_label(context, "bonus_spell_known_1_1", "Shillelagh"),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Bless"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert {"Druidcraft", "Shillelagh"} <= granted_labels
    assert "Shillelagh (Granted, Cantrip)" in context["preview"]["spells"]
    assert spells_by_name["Shillelagh"]["is_bonus_known"] is True
    assert spells_by_name["Animal Friendship"]["is_always_prepared"] is True
def test_level_one_builder_applies_structured_spell_support_feature_metadata():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    tide_blessing = _systems_entry(
        "classfeature",
        "phb-classfeature-tide-blessing",
        "Tide Blessing",
        metadata={
            "level": 1,
            "spell_support": [
                {
                    "grants": {
                        "1": [
                            {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                        ]
                    },
                    "choices": {
                        "1": [
                            {"category": "known", "filter": "level=0|class=Druid", "count": 1},
                            {
                                "category": "granted",
                                "options": ["Animal Friendship", "Speak with Animals"],
                                "count": 1,
                                "mark": "Granted",
                            },
                        ]
                    },
                }
            ],
        },
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Druid"]}})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0, "class_lists": {"PHB": ["Druid"]}})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True})
    animal_friendship = _systems_entry("spell", "phb-spell-animal-friendship", "Animal Friendship", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    speak_with_animals = _systems_entry("spell", "phb-spell-speak-with-animals", "Speak with Animals", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                druidcraft,
                shillelagh,
                detect_magic,
                animal_friendship,
                speak_with_animals,
                bless,
                guiding_bolt,
                healing_word,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Tide Blessing", "entry": tide_blessing, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Tessa Wavebound",
        "character_slug": "tessa-wavebound",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
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

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    field_names = _builder_field_names(context)
    prepared_option_labels = {option["label"] for option in _find_builder_field(context, "spell_level_one_1")["options"]}

    assert {"spell_support_known_1_1", "spell_support_granted_2_1"} <= field_names
    assert "Detect Magic" not in prepared_option_labels

    form_values = {
        **base_form_values,
        "spell_support_known_1_1": _field_value_for_label(context, "spell_support_known_1_1", "Shillelagh"),
        "spell_support_granted_2_1": _field_value_for_label(context, "spell_support_granted_2_1", "Speak with Animals"),
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Bless"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(context, "spell_level_one_4", "Shield of Faith"),
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", form_values)
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert "Detect Magic (Always prepared)" in context["preview"]["spells"]
    assert "Shillelagh (Granted, Cantrip)" in context["preview"]["spells"]
    assert "Speak with Animals (Granted)" in context["preview"]["spells"]
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Shillelagh"]["is_bonus_known"] is True
    assert spells_by_name["Shillelagh"]["mark"] == "Cantrip"
    assert spells_by_name["Speak with Animals"]["mark"] == "Granted"
def test_level_one_builder_clears_stale_spell_support_fields_after_class_option_change():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    mystic_training = _systems_entry("classfeature", "phb-classfeature-mystic-training", "Mystic Training", metadata={"level": 1})
    tide_initiate = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-tide-initiate",
        "Tide Initiate",
        metadata={
            "spell_support": [
                {
                    "choices": {
                        "1": [
                            {"category": "known", "filter": "level=0|class=Druid", "count": 1},
                        ]
                    }
                }
            ]
        },
    )
    martial_discipline = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-martial-discipline",
        "Martial Discipline",
        metadata={},
    )
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Druid"]}})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0, "class_lists": {"PHB": ["Druid"]}})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "optionalfeature": [tide_initiate, martial_discipline],
            "item": [],
            "spell": [druidcraft, shillelagh],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {
                        "label": "Mystic Training",
                        "entry": mystic_training,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Tide Initiate", "slug": tide_initiate.slug},
                                        {"label": "Martial Discipline", "slug": martial_discipline.slug},
                                    ]
                                }
                            ]
                        },
                    },
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Mira Stonewake",
        "character_slug": "mira-stonewake",
        "alignment": "Lawful Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "history",
        "class_skill_2": "medicine",
        "class_option_1": tide_initiate.slug,
        "str": "10",
        "dex": "12",
        "con": "14",
        "int": "11",
        "wis": "16",
        "cha": "13",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    stale_form = {
        **base_form_values,
        "class_option_1": martial_discipline.slug,
        "spell_support_known_1_1": _field_value_for_label(context, "spell_support_known_1_1", "Shillelagh"),
    }

    stale_context = build_level_one_builder_context(systems_service, "linden-pass", stale_form)
    field_names = _builder_field_names(stale_context)

    assert "spell_support_known_1_1" not in field_names
    assert stale_context["values"].get("spell_support_known_1_1", "") == ""
    assert stale_context["values"]["class_option_1"] == martial_discipline.slug
    assert stale_context["preview"]["spells"] == []
def test_level_one_builder_surfaces_expanded_subclass_spells_in_known_options():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Otherworldly Patron",
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
            },
        },
    )
    archfey = _systems_entry(
        "subclass",
        "phb-subclass-warlock-archfey",
        "The Archfey",
        metadata={
            "class_name": "Warlock",
            "class_source": "PHB",
            "additional_spells": [
                {
                    "expanded": {
                        "s1": ["Faerie Fire", "Sleep"],
                        "s2": ["Calm Emotions", "Phantasmal Force"],
                    }
                }
            ],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human", metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]})
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte", metadata={"skill_proficiencies": [{"insight": True, "religion": True}]})
    otherworldly_patron = _systems_entry("classfeature", "phb-classfeature-otherworldly-patron", "Otherworldly Patron", metadata={"level": 1})
    fey_presence = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-fey-presence",
        "Fey Presence",
        metadata={"level": 1, "class_name": "Warlock", "class_source": "PHB", "subclass_name": "The Archfey"},
    )
    eldritch_blast = _systems_entry("spell", "phb-spell-eldritch-blast", "Eldritch Blast", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    mage_hand = _systems_entry("spell", "phb-spell-mage-hand", "Mage Hand", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    armor_of_agathys = _systems_entry("spell", "phb-spell-armor-of-agathys", "Armor of Agathys", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    hex = _systems_entry("spell", "phb-spell-hex", "Hex", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})
    faerie_fire = _systems_entry("spell", "phb-spell-faerie-fire", "Faerie Fire", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    sleep = _systems_entry("spell", "phb-spell-sleep", "Sleep", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [archfey],
            "item": [],
            "spell": [eldritch_blast, mage_hand, armor_of_agathys, hex, faerie_fire, sleep],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Otherworldly Patron", "entry": otherworldly_patron, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Fey Presence", "entry": fey_presence, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    values = {
        "name": "Nyx Vale",
        "character_slug": "nyx-vale",
        "alignment": "Chaotic Good",
        "experience_model": "Milestone",
        "class_slug": warlock.slug,
        "subclass_slug": archfey.slug,
        "species_slug": human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "arcana",
        "class_skill_2": "deception",
        "str": "8",
        "dex": "14",
        "con": "13",
        "int": "12",
        "wis": "10",
        "cha": "16",
    }

    context = build_level_one_builder_context(systems_service, "linden-pass", values)
    known_spell_labels = {option["label"] for option in _find_builder_field(context, "spell_level_one_1")["options"]}

    assert known_spell_labels >= {"Faerie Fire", "Sleep"}

    form_values = {
        **values,
        "spell_cantrip_1": _field_value_for_label(context, "spell_cantrip_1", "Eldritch Blast"),
        "spell_cantrip_2": _field_value_for_label(context, "spell_cantrip_2", "Mage Hand"),
        "spell_level_one_1": _field_value_for_label(context, "spell_level_one_1", "Faerie Fire"),
        "spell_level_one_2": _field_value_for_label(context, "spell_level_one_2", "Hex"),
    }
    definition, _ = build_level_one_character_definition("linden-pass", context, form_values)
    spells_by_name = {spell["name"]: spell for spell in definition.spellcasting["spells"]}

    assert spells_by_name["Faerie Fire"]["mark"] == "Known"
def test_native_level_up_surfaces_expanded_subclass_spells_in_known_options():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Otherworldly Patron",
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
            },
        },
    )
    archfey = _systems_entry(
        "subclass",
        "phb-subclass-warlock-archfey",
        "The Archfey",
        metadata={
            "class_name": "Warlock",
            "class_source": "PHB",
            "additional_spells": [
                {
                    "expanded": {
                        "s1": ["Faerie Fire", "Sleep"],
                        "s2": ["Calm Emotions", "Phantasmal Force"],
                    }
                }
            ],
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
    pact_boon = _systems_entry("classfeature", "phb-classfeature-pact-boon", "Pact Boon", metadata={"level": 3})
    eldritch_blast = _systems_entry(
        "spell",
        "phb-spell-eldritch-blast",
        "Eldritch Blast",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    armor_of_agathys = _systems_entry(
        "spell",
        "phb-spell-armor-of-agathys",
        "Armor of Agathys",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    hex = _systems_entry(
        "spell",
        "phb-spell-hex",
        "Hex",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1},
    )
    sleep = _systems_entry(
        "spell",
        "phb-spell-sleep",
        "Sleep",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    calm_emotions = _systems_entry(
        "spell",
        "phb-spell-calm-emotions",
        "Calm Emotions",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 2},
    )
    phantasmal_force = _systems_entry(
        "spell",
        "phb-spell-phantasmal-force",
        "Phantasmal Force",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 2},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [archfey],
            "item": [],
            "spell": [
                eldritch_blast,
                mage_hand,
                armor_of_agathys,
                hex,
                sleep,
                calm_emotions,
                phantasmal_force,
            ],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Pact Boon", "entry": pact_boon, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[],
    )

    current_definition = _minimal_character_definition("nyx-vale", "Nyx Vale")
    current_definition.profile["class_level_text"] = "Warlock 2"
    current_definition.profile["classes"][0]["class_name"] = "Warlock"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|phb|warlock",
        "entry_type": "class",
        "title": "Warlock",
        "slug": warlock.slug,
        "source_id": "PHB",
    }
    current_definition.profile["class_ref"] = dict(current_definition.profile["classes"][0]["systems_ref"])
    current_definition.profile["subclass_ref"] = {
        "entry_key": "dnd-5e|subclass|phb|the-archfey",
        "entry_type": "subclass",
        "title": "The Archfey",
        "slug": archfey.slug,
        "source_id": "PHB",
    }
    current_definition.profile["classes"][0]["subclass_name"] = "The Archfey"
    current_definition.profile["classes"][0]["subclass_ref"] = dict(current_definition.profile["subclass_ref"])
    current_definition.stats["max_hp"] = 17
    current_definition.stats["ability_scores"] = {
        "str": {"score": 8, "modifier": -1, "save_bonus": -1},
        "dex": {"score": 14, "modifier": 2, "save_bonus": 2},
        "con": {"score": 13, "modifier": 1, "save_bonus": 1},
        "int": {"score": 12, "modifier": 1, "save_bonus": 1},
        "wis": {"score": 10, "modifier": 0, "save_bonus": 2},
        "cha": {"score": 16, "modifier": 3, "save_bonus": 5},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Warlock",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {"name": "Eldritch Blast", "mark": "Cantrip", "systems_ref": {"slug": eldritch_blast.slug, "title": eldritch_blast.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Mage Hand", "mark": "Cantrip", "systems_ref": {"slug": mage_hand.slug, "title": mage_hand.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Armor of Agathys", "mark": "Known", "systems_ref": {"slug": armor_of_agathys.slug, "title": armor_of_agathys.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Hex", "mark": "Known", "systems_ref": {"slug": hex.slug, "title": hex.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Sleep", "mark": "Known", "systems_ref": {"slug": sleep.slug, "title": sleep.title, "entry_type": "spell", "source_id": "PHB"}},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-2"

    form_values = {"hp_gain": "5"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    known_spell_labels = {option["label"] for option in _find_builder_field(context, "levelup_spell_known_1")["options"]}

    assert known_spell_labels >= {"Calm Emotions", "Phantasmal Force"}

    form_values["levelup_spell_known_1"] = _field_value_for_label(context, "levelup_spell_known_1", "Phantasmal Force")
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert spells_by_name["Phantasmal Force"]["mark"] == "Known"
def test_native_level_up_surfaces_and_applies_magic_initiate_feat_spells():
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
    magic_initiate = _systems_entry(
        "feat",
        "phb-feat-magic-initiate",
        "Magic Initiate",
        metadata={
            "additional_spells": [
                {
                    "name": "Cleric Spells",
                    "ability": "wis",
                    "known": {"_": [{"choose": "level=0|class=Cleric", "count": 2}]},
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
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
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
            "spell": [guidance, light, cure_wounds],
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

    current_definition = _minimal_character_definition("spell-feat-hero", "Spell Feat Hero")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": magic_initiate.slug,
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    assert _find_builder_field(context, "feat_levelup_feat_1_spell_known_1_1")["label"] == "Magic Initiate Granted Cantrip 1"

    form_values.update(
        {
            "feat_levelup_feat_1_spell_known_1_1": _field_value_for_label(
                context,
                "feat_levelup_feat_1_spell_known_1_1",
                "Guidance",
            ),
            "feat_levelup_feat_1_spell_known_1_2": _field_value_for_label(
                context,
                "feat_levelup_feat_1_spell_known_1_2",
                "Light",
            ),
            "feat_levelup_feat_1_spell_granted_1_1": _field_value_for_label(
                context,
                "feat_levelup_feat_1_spell_granted_1_1",
                "Cure Wounds",
            ),
        }
    )
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert {"Guidance", "Light", "Cure Wounds"} <= set(context["preview"]["new_spells"])
    assert spells_by_name["Guidance"]["mark"] == "Cantrip"
    assert spells_by_name["Guidance"]["is_bonus_known"] is True
    assert spells_by_name["Cure Wounds"]["mark"] == "1 / Long Rest"
@pytest.mark.parametrize("case", _FREE_CAST_FEAT_CASES)
def test_native_level_up_applies_supported_free_cast_feat_spells_without_merging_into_class_rows(
    case: dict[str, object],
):
    fixture = _build_free_cast_feat_test_fixture()
    systems_service = fixture["systems_service"]
    fighter = fixture["fighter"]

    current_definition = _minimal_character_definition(
        f"{str(case['title']).lower().replace(' ', '-')}-caster",
        f"{case['title']} Caster",
    )
    _apply_primary_class(current_definition, fighter, level=3)
    _apply_free_cast_test_ability_scores(current_definition)

    form_values = {
        "hp_gain": "6",
        "levelup_asi_mode_1": "feat",
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", str(case["title"]))
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    _apply_free_cast_feat_field_choices(
        form_values=form_values,
        context=context,
        prefix="feat_levelup_feat_1_",
        case=case,
    )
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)

    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    assert set(context["preview"]["new_spells"]) == {
        str(spec["name"])
        for spec in list(case.get("expected_spells") or [])
    }
    assert list(leveled_definition.spellcasting.get("class_rows") or []) == []
    _assert_free_cast_feat_spellcasting(leveled_definition.spellcasting, case)
def test_native_level_up_clears_stale_feat_and_spell_fields_after_switching_back_to_ability_scores():
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
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("asi-shift", "ASI Shift")
    current_definition.profile["class_level_text"] = "Fighter 3"
    current_definition.profile["classes"][0]["level"] = 3

    feat_form = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": magic_initiate.slug,
    }
    feat_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, feat_form)
    stale_form = {
        **feat_form,
        "levelup_asi_mode_1": "ability_scores",
        "levelup_asi_ability_1_1": "str",
        "levelup_asi_ability_1_2": "str",
        "feat_levelup_feat_1_spell_known_1_1": _field_value_for_label(
            feat_context,
            "feat_levelup_feat_1_spell_known_1_1",
            "Guidance",
        ),
        "feat_levelup_feat_1_spell_granted_1_1": _field_value_for_label(
            feat_context,
            "feat_levelup_feat_1_spell_granted_1_1",
            "Cure Wounds",
        ),
    }

    stale_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, stale_form)
    field_names = _builder_field_names(stale_context)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        stale_context,
        stale_form,
    )

    assert "levelup_feat_1" not in field_names
    assert not any(name.startswith("feat_levelup_feat_1_") for name in field_names)
    assert {"levelup_asi_ability_1_1", "levelup_asi_ability_1_2"} <= field_names
    assert stale_context["values"].get("levelup_feat_1", "") == ""
    assert stale_context["values"].get("feat_levelup_feat_1_spell_known_1_1", "") == ""
    assert stale_context["preview"]["new_spells"] == []
    assert leveled_definition.stats["ability_scores"]["str"]["score"] == 18
    assert leveled_definition.spellcasting["spells"] == []
    assert all(feature["name"] != "Magic Initiate" for feature in leveled_definition.features)
def test_native_level_up_clears_stale_supported_feat_spell_fields_after_switching_back_to_ability_scores():
    fixture = _build_free_cast_feat_test_fixture()
    systems_service = fixture["systems_service"]
    fighter = fixture["fighter"]

    current_definition = _minimal_character_definition("asi-free-cast-shift", "ASI Free Cast Shift")
    _apply_primary_class(current_definition, fighter, level=3)
    _apply_free_cast_test_ability_scores(current_definition)

    feat_form = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
    }
    feat_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, feat_form)
    feat_form["levelup_feat_1"] = _field_value_for_label(feat_context, "levelup_feat_1", "Artificer Initiate")
    feat_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, feat_form)
    stale_form = {
        **feat_form,
        "levelup_asi_mode_1": "ability_scores",
        "levelup_asi_ability_1_1": "str",
        "levelup_asi_ability_1_2": "str",
        "feat_levelup_feat_1_spell_known_1_1": _field_value_for_label(
            feat_context,
            "feat_levelup_feat_1_spell_known_1_1",
            "Mage Hand",
        ),
        "feat_levelup_feat_1_spell_known_2_1": _field_value_for_label(
            feat_context,
            "feat_levelup_feat_1_spell_known_2_1",
            "Cure Wounds",
        ),
    }

    stale_context = build_native_level_up_context(systems_service, "linden-pass", current_definition, stale_form)
    field_names = _builder_field_names(stale_context)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        stale_context,
        stale_form,
    )

    assert "levelup_feat_1" not in field_names
    assert not any(name.startswith("feat_levelup_feat_1_") for name in field_names)
    assert {"levelup_asi_ability_1_1", "levelup_asi_ability_1_2"} <= field_names
    assert stale_context["values"].get("levelup_feat_1", "") == ""
    assert stale_context["values"].get("feat_levelup_feat_1_spell_known_1_1", "") == ""
    assert stale_context["values"].get("feat_levelup_feat_1_spell_known_2_1", "") == ""
    assert stale_context["preview"]["new_spells"] == []
    assert leveled_definition.stats["ability_scores"]["str"]["score"] == 18
    assert leveled_definition.spellcasting["spells"] == []
    assert list(leveled_definition.spellcasting.get("source_rows") or []) == []
    assert all(feature["name"] != "Artificer Initiate" for feature in leveled_definition.features)
def test_native_level_up_can_add_ritual_caster_with_ritual_book_manager():
    fixture = _build_ritual_caster_test_fixture()
    systems_service = fixture["systems_service"]
    fighter = fixture["fighter"]

    current_definition = _minimal_character_definition("ritual-leveler", "Ritual Leveler")
    _apply_primary_class(current_definition, fighter, level=3)
    _apply_free_cast_test_ability_scores(current_definition)

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", "Ritual Caster")
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    form_values["feat_levelup_feat_1_spell_source_1"] = _field_value_for_label(
        context,
        "feat_levelup_feat_1_spell_source_1",
        "Wizard Spells",
    )
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    form_values["feat_levelup_feat_1_spell_managed_1_1"] = _field_value_for_label(
        context,
        "feat_levelup_feat_1_spell_managed_1_1",
        "Detect Magic",
    )
    form_values["feat_levelup_feat_1_spell_managed_1_2"] = _field_value_for_label(
        context,
        "feat_levelup_feat_1_spell_managed_1_2",
        "Find Familiar",
    )
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    ritual_caster_feature = next(feature for feature in leveled_definition.features if feature["name"] == "Ritual Caster")
    spell_manager = dict(ritual_caster_feature.get("spell_manager") or {})
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}
    source_rows = [dict(row or {}) for row in list(leveled_definition.spellcasting.get("source_rows") or []) if isinstance(row, dict)]

    assert spell_manager["mode"] == "ritual_book"
    assert spell_manager["spell_list_class_name"] == "Wizard"
    assert {spell["name"] for spell in leveled_definition.spellcasting["spells"]} == {"Detect Magic", "Find Familiar"}
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Find Familiar"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert len(source_rows) == 1
    assert source_rows[0]["spell_mode"] == "ritual_book"
    assert source_rows[0]["spell_save_dc"] == 12
    assert source_rows[0]["spell_attack_bonus"] == 4
def test_native_level_up_can_replace_known_spell():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
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
    charm_person = _systems_entry(
        "spell",
        "phb-spell-charm-person",
        "Charm Person",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hex_spell = _systems_entry(
        "spell",
        "phb-spell-hex",
        "Hex",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    armor_of_agathys = _systems_entry(
        "spell",
        "phb-spell-armor-of-agathys",
        "Armor of Agathys",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hellish_rebuke = _systems_entry(
        "spell",
        "phb-spell-hellish-rebuke",
        "Hellish Rebuke",
        metadata={"casting_time": [{"number": 1, "unit": "reaction"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    eldritch_blast = _systems_entry(
        "spell",
        "phb-spell-eldritch-blast",
        "Eldritch Blast",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    chill_touch = _systems_entry(
        "spell",
        "phb-spell-chill-touch",
        "Chill Touch",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    disguise_self = _systems_entry(
        "spell",
        "phb-spell-disguise-self",
        "Disguise Self",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
                "background": [acolyte],
                "feat": [],
                "subclass": [],
                "item": [],
                "spell": [charm_person, hex_spell, armor_of_agathys, eldritch_blast, chill_touch, disguise_self],
            },
            class_progression=[
                {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [],
            }
        ],
    )

    current_definition = _minimal_character_definition("warlock-hero", "Warlock Hero")
    current_definition.profile["class_level_text"] = "Warlock 1"
    current_definition.profile["classes"][0] = {
        "class_name": "Warlock",
        "subclass_name": "",
        "level": 1,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|warlock",
            "entry_type": "class",
            "title": "Warlock",
            "slug": warlock.slug,
            "source_id": "PHB",
        },
    }
    current_definition.profile["class_ref"] = {
        "entry_key": "dnd-5e|class|phb|warlock",
        "entry_type": "class",
        "title": "Warlock",
        "slug": warlock.slug,
        "source_id": "PHB",
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Warlock",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 10,
        "spell_attack_bonus": 2,
        "slot_progression": [{"level": 1, "max_slots": 1}],
            "spells": [
                {
                    "name": "Eldritch Blast",
                    "mark": "Cantrip",
                    "systems_ref": {
                        "entry_key": eldritch_blast.entry_key,
                        "entry_type": eldritch_blast.entry_type,
                        "title": eldritch_blast.title,
                        "slug": eldritch_blast.slug,
                        "source_id": eldritch_blast.source_id,
                    },
                },
                {
                    "name": "Chill Touch",
                    "mark": "Cantrip",
                    "systems_ref": {
                        "entry_key": chill_touch.entry_key,
                        "entry_type": chill_touch.entry_type,
                        "title": chill_touch.title,
                        "slug": chill_touch.slug,
                        "source_id": chill_touch.source_id,
                    },
                },
                {
                    "name": "Charm Person",
                    "mark": "Known",
                "systems_ref": {
                    "entry_key": charm_person.entry_key,
                    "entry_type": charm_person.entry_type,
                    "title": charm_person.title,
                    "slug": charm_person.slug,
                    "source_id": charm_person.source_id,
                },
            },
            {
                "name": "Hex",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": hex_spell.entry_key,
                    "entry_type": hex_spell.entry_type,
                    "title": hex_spell.title,
                    "slug": hex_spell.slug,
                    "source_id": hex_spell.source_id,
                },
            },
        ],
    }

    form_values = {
        "hp_gain": "5",
    }
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)

    assert _find_builder_field(context, "levelup_spell_replace_from_1")["label"] == "Replace Known Spell"
    assert _field_value_for_label(context, "levelup_spell_replace_from_1", "Charm Person")
    assert _field_value_for_label(context, "levelup_spell_replace_to_1", "Disguise Self")

    form_values.update(
        {
            "levelup_spell_known_1": _field_value_for_label(context, "levelup_spell_known_1", "Armor of Agathys"),
            "levelup_spell_replace_from_1": _field_value_for_label(
                context,
                "levelup_spell_replace_from_1",
                "Charm Person",
            ),
            "levelup_spell_replace_to_1": _field_value_for_label(
                context,
                "levelup_spell_replace_to_1",
                "Disguise Self",
            ),
        }
    )
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert {"Armor of Agathys", "Disguise Self"} <= set(context["preview"]["new_spells"])
    assert "Charm Person" not in spells_by_name
    assert spells_by_name["Hex"]["mark"] == "Known"
    assert spells_by_name["Armor of Agathys"]["mark"] == "Known"
    assert spells_by_name["Disguise Self"]["mark"] == "Known"
def test_native_level_up_applies_structured_spell_support_and_replacement_rules():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
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
    eldritch_tuning = _systems_entry(
        "classfeature",
        "phb-classfeature-eldritch-tuning",
        "Eldritch Tuning",
        metadata={
            "level": 2,
            "spell_support": [
                {
                    "grants": {
                        "2": [
                            {"spell": "Mage Hand", "bonus_known": True},
                        ]
                    },
                    "choices": {
                        "2": [
                            {
                                "category": "granted",
                                "options": ["Disguise Self", "Silent Image"],
                                "count": 1,
                                "mark": "Granted",
                            }
                        ]
                    },
                    "replacement": {
                        "2": [
                            {
                                "kind": "known",
                                "from": {"mark": "Known", "level": 1},
                                "to": {"options": ["Cause Fear", "Disguise Self"]},
                            }
                        ]
                    },
                }
            ],
        },
    )
    charm_person = _systems_entry(
        "spell",
        "phb-spell-charm-person",
        "Charm Person",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hex_spell = _systems_entry(
        "spell",
        "phb-spell-hex",
        "Hex",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    armor_of_agathys = _systems_entry(
        "spell",
        "phb-spell-armor-of-agathys",
        "Armor of Agathys",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    eldritch_blast = _systems_entry(
        "spell",
        "phb-spell-eldritch-blast",
        "Eldritch Blast",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    chill_touch = _systems_entry(
        "spell",
        "phb-spell-chill-touch",
        "Chill Touch",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    disguise_self = _systems_entry(
        "spell",
        "phb-spell-disguise-self",
        "Disguise Self",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    silent_image = _systems_entry(
        "spell",
        "phb-spell-silent-image",
        "Silent Image",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    cause_fear = _systems_entry(
        "spell",
        "phb-spell-cause-fear",
        "Cause Fear",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )

    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [
                charm_person,
                hex_spell,
                armor_of_agathys,
                eldritch_blast,
                chill_touch,
                mage_hand,
                disguise_self,
                silent_image,
                cause_fear,
            ],
        },
        class_progression=[
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Eldritch Tuning", "entry": eldritch_tuning, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("warlock-hero", "Warlock Hero")
    current_definition.profile["class_level_text"] = "Warlock 1"
    current_definition.profile["classes"][0] = {
        "class_name": "Warlock",
        "subclass_name": "",
        "level": 1,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|warlock",
            "entry_type": "class",
            "title": "Warlock",
            "slug": warlock.slug,
            "source_id": "PHB",
        },
    }
    current_definition.profile["class_ref"] = {
        "entry_key": "dnd-5e|class|phb|warlock",
        "entry_type": "class",
        "title": "Warlock",
        "slug": warlock.slug,
        "source_id": "PHB",
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Warlock",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 10,
        "spell_attack_bonus": 2,
        "slot_progression": [{"level": 1, "max_slots": 1}],
        "spells": [
            {
                "name": "Eldritch Blast",
                "mark": "Cantrip",
                "systems_ref": {
                    "entry_key": eldritch_blast.entry_key,
                    "entry_type": eldritch_blast.entry_type,
                    "title": eldritch_blast.title,
                    "slug": eldritch_blast.slug,
                    "source_id": eldritch_blast.source_id,
                },
            },
            {
                "name": "Chill Touch",
                "mark": "Cantrip",
                "systems_ref": {
                    "entry_key": chill_touch.entry_key,
                    "entry_type": chill_touch.entry_type,
                    "title": chill_touch.title,
                    "slug": chill_touch.slug,
                    "source_id": chill_touch.source_id,
                },
            },
            {
                "name": "Charm Person",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": charm_person.entry_key,
                    "entry_type": charm_person.entry_type,
                    "title": charm_person.title,
                    "slug": charm_person.slug,
                    "source_id": charm_person.source_id,
                },
            },
            {
                "name": "Hex",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": hex_spell.entry_key,
                    "entry_type": hex_spell.entry_type,
                    "title": hex_spell.title,
                    "slug": hex_spell.slug,
                    "source_id": hex_spell.source_id,
                },
            },
        ],
    }

    form_values = {"hp_gain": "5"}
    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    field_names = _builder_field_names(context)

    assert "levelup_spell_support_granted_1_1" in field_names
    assert "levelup_spell_support_replace_known_1_from_1" in field_names
    assert "levelup_spell_support_replace_known_1_to_1" in field_names
    assert "levelup_spell_replace_from_1" not in field_names

    form_values.update(
        {
            "levelup_spell_known_1": _field_value_for_label(context, "levelup_spell_known_1", "Armor of Agathys"),
            "levelup_spell_support_granted_1_1": _field_value_for_label(
                context,
                "levelup_spell_support_granted_1_1",
                "Disguise Self",
            ),
            "levelup_spell_support_replace_known_1_from_1": _field_value_for_label(
                context,
                "levelup_spell_support_replace_known_1_from_1",
                "Charm Person",
            ),
            "levelup_spell_support_replace_known_1_to_1": _field_value_for_label(
                context,
                "levelup_spell_support_replace_known_1_to_1",
                "Cause Fear",
            ),
        }
    )

    context = build_native_level_up_context(systems_service, "linden-pass", current_definition, form_values)
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )

    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert {"Armor of Agathys", "Cause Fear", "Disguise Self", "Mage Hand"} <= set(context["preview"]["new_spells"])
    assert "Charm Person" not in spells_by_name
    assert spells_by_name["Armor of Agathys"]["mark"] == "Known"
    assert spells_by_name["Cause Fear"]["mark"] == "Known"
    assert spells_by_name["Disguise Self"]["mark"] == "Granted"
    assert spells_by_name["Mage Hand"]["mark"] == "Cantrip"
    assert spells_by_name["Mage Hand"]["is_bonus_known"] is True
def test_native_level_up_applies_campaign_progression_and_feat_spell_support():
    warlock = _systems_entry(
        "class",
        "phb-class-warlock",
        "Warlock",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "starting_proficiencies": {
                "armor": ["light"],
                "weapons": ["simple"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "history", "intimidation"]}}],
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
    charm_person = _systems_entry(
        "spell",
        "phb-spell-charm-person",
        "Charm Person",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hex_spell = _systems_entry(
        "spell",
        "phb-spell-hex",
        "Hex",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    armor_of_agathys = _systems_entry(
        "spell",
        "phb-spell-armor-of-agathys",
        "Armor of Agathys",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    hellish_rebuke = _systems_entry(
        "spell",
        "phb-spell-hellish-rebuke",
        "Hellish Rebuke",
        metadata={"casting_time": [{"number": 1, "unit": "reaction"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    expeditious_retreat = _systems_entry(
        "spell",
        "phb-spell-expeditious-retreat",
        "Expeditious Retreat",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1, "class_lists": {"PHB": ["Warlock"]}},
    )
    eldritch_blast = _systems_entry(
        "spell",
        "phb-spell-eldritch-blast",
        "Eldritch Blast",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    chill_touch = _systems_entry(
        "spell",
        "phb-spell-chill-touch",
        "Chill Touch",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Warlock"]}},
    )
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    disguise_self = _systems_entry(
        "spell",
        "phb-spell-disguise-self",
        "Disguise Self",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    silent_image = _systems_entry(
        "spell",
        "phb-spell-silent-image",
        "Silent Image",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    cause_fear = _systems_entry(
        "spell",
        "phb-spell-cause-fear",
        "Cause Fear",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
    )
    light = _systems_entry(
        "spell",
        "phb-spell-light",
        "Light",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )
    message = _systems_entry(
        "spell",
        "phb-spell-message",
        "Message",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
    )

    campaign_progression_entry = build_campaign_page_progression_entries(
        _campaign_page_record(
            "mechanics/covenant-secrets",
            "Covenant Secrets",
            section="Mechanics",
            subsection="Class Modifications",
            metadata={
                "character_progression": {
                    "kind": "class",
                    "class_name": "Warlock",
                    "level": 4,
                    "character_option": {
                        "name": "Covenant Secrets",
                        "description_markdown": "You trade one spell for a covenant-taught secret.",
                        "activation_type": "special",
                        "spell_support": [
                            {
                                "grants": {
                                    "4": [
                                        {"spell": "Mage Hand", "bonus_known": True},
                                    ]
                                },
                                "choices": {
                                    "4": [
                                        {
                                            "category": "granted",
                                            "options": ["Disguise Self", "Silent Image"],
                                            "count": 1,
                                            "label_prefix": "Covenant Spell",
                                            "mark": "Granted",
                                        }
                                    ]
                                },
                                "replacement": {
                                    "4": [
                                        {
                                            "kind": "known",
                                            "from": {"mark": "Known", "level": 1},
                                            "to": {"options": ["Cause Fear", "Disguise Self"]},
                                        }
                                    ]
                                },
                            }
                        ],
                    },
                }
            },
        )
    )[0]
    campaign_page_records = [
        _campaign_page_record(
            "mechanics/tidebound-initiate",
            "Tidebound Initiate",
            section="Mechanics",
            subsection="Feats",
            metadata={
                "character_option": {
                    "kind": "feat",
                    "name": "Tidebound Initiate",
                    "description_markdown": "The tide teaches you a cantrip and a warding rite.",
                    "activation_type": "special",
                    "spell_support": [
                        {
                            "grants": {
                                "_": [
                                    {"spell": "Detect Magic", "always_prepared": True, "ritual": True},
                                ]
                            },
                            "choices": {
                                "_": [
                                    {
                                        "category": "granted",
                                        "options": ["Light", "Message"],
                                        "count": 1,
                                        "label_prefix": "Tidebound Cantrip",
                                        "mark": "Granted",
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
    ]
    systems_service = _FakeSystemsService(
        {
            "class": [warlock],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "item": [],
            "spell": [
                charm_person,
                hex_spell,
                armor_of_agathys,
                hellish_rebuke,
                expeditious_retreat,
                eldritch_blast,
                chill_touch,
                mage_hand,
                disguise_self,
                silent_image,
                cause_fear,
                detect_magic,
                light,
                message,
            ],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": None, "embedded_card": None},
                    {"label": "Covenant Secrets", "entry": campaign_progression_entry, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("warlock-hero", "Warlock Hero")
    current_definition.profile["class_level_text"] = "Warlock 3"
    current_definition.profile["classes"][0] = {
        "class_name": "Warlock",
        "subclass_name": "",
        "level": 3,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|warlock",
            "entry_type": "class",
            "title": "Warlock",
            "slug": warlock.slug,
            "source_id": "PHB",
        },
    }
    current_definition.profile["class_ref"] = {
        "entry_key": "dnd-5e|class|phb|warlock",
        "entry_type": "class",
        "title": "Warlock",
        "slug": warlock.slug,
        "source_id": "PHB",
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Warlock",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 12,
        "spell_attack_bonus": 4,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {
                "name": "Eldritch Blast",
                "mark": "Cantrip",
                "systems_ref": {
                    "entry_key": eldritch_blast.entry_key,
                    "entry_type": eldritch_blast.entry_type,
                    "title": eldritch_blast.title,
                    "slug": eldritch_blast.slug,
                    "source_id": eldritch_blast.source_id,
                },
            },
            {
                "name": "Chill Touch",
                "mark": "Cantrip",
                "systems_ref": {
                    "entry_key": chill_touch.entry_key,
                    "entry_type": chill_touch.entry_type,
                    "title": chill_touch.title,
                    "slug": chill_touch.slug,
                    "source_id": chill_touch.source_id,
                },
            },
            {
                "name": "Charm Person",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": charm_person.entry_key,
                    "entry_type": charm_person.entry_type,
                    "title": charm_person.title,
                    "slug": charm_person.slug,
                    "source_id": charm_person.source_id,
                },
            },
            {
                "name": "Hex",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": hex_spell.entry_key,
                    "entry_type": hex_spell.entry_type,
                    "title": hex_spell.title,
                    "slug": hex_spell.slug,
                    "source_id": hex_spell.source_id,
                },
            },
        ],
    }

    form_values = {"hp_gain": "5", "levelup_asi_mode_1": "feat"}
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    form_values["levelup_feat_1"] = _field_value_for_label(context, "levelup_feat_1", "Tidebound Initiate")

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    field_names = _builder_field_names(context)
    covenant_field = _field_name_for_label(context, "Covenant Spell 1")
    tidebound_field = _field_name_for_label(context, "Tidebound Cantrip 1")
    replace_from_field = _field_name_for_label(context, "Replace Spell 1")
    replace_to_field = _field_name_for_label(context, "Replacement Spell 1")

    assert covenant_field in field_names
    assert tidebound_field in field_names
    assert replace_from_field in field_names
    assert replace_to_field in field_names
    assert "levelup_spell_replace_from_1" not in field_names

    form_values.update(
        {
            "levelup_spell_known_1": _field_value_for_label(context, "levelup_spell_known_1", "Armor of Agathys"),
            "levelup_spell_known_2": _field_value_for_label(context, "levelup_spell_known_2", "Hellish Rebuke"),
            "levelup_spell_known_3": _field_value_for_label(
                context,
                "levelup_spell_known_3",
                "Expeditious Retreat",
            ),
            covenant_field: _field_value_for_label(context, covenant_field, "Disguise Self"),
            tidebound_field: _field_value_for_label(context, tidebound_field, "Light"),
            replace_from_field: _field_value_for_label(context, replace_from_field, "Charm Person"),
            replace_to_field: _field_value_for_label(context, replace_to_field, "Cause Fear"),
        }
    )

    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
        campaign_page_records=campaign_page_records,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        context,
        form_values,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert {"Armor of Agathys", "Cause Fear", "Detect Magic", "Disguise Self", "Light", "Mage Hand"} <= set(
        context["preview"]["new_spells"]
    )
    assert "Charm Person" not in spells_by_name
    assert spells_by_name["Armor of Agathys"]["mark"] == "Known"
    assert spells_by_name["Cause Fear"]["mark"] == "Known"
    assert spells_by_name["Disguise Self"]["mark"] == "Granted"
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Mage Hand"]["mark"] == "Cantrip"
    assert spells_by_name["Mage Hand"]["is_bonus_known"] is True
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["systems_ref"]["slug"] == detect_magic.slug
def test_native_level_up_advances_wizard_to_level_two_with_subclass_and_spellbook_growth():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "subclass_title": "Arcane Tradition",
            "starting_proficiencies": {
                "armor": [],
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "insight"]}}],
            },
            "starting_equipment": {
                "defaultData": [
                    {"a": ["quarterstaff|phb"], "b": ["dagger|phb"]},
                    {"a": ["component pouch|phb"], "b": [{"equipmentType": "focusSpellcastingArcane"}]},
                    {"a": ["scholar's pack|phb"], "b": ["explorer's pack|phb"]},
                    {"_": ["spellbook|phb"]},
                ]
            },
        },
    )
    evocation = _systems_entry(
        "subclass",
        "phb-subclass-wizard-school-of-evocation",
        "School of Evocation",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    human = _systems_entry(
        "race",
        "phb-race-human",
        "Human",
        metadata={"size": ["M"], "speed": 30, "languages": [{"common": True}]},
        body={"entries": [{"name": "Feature: Resourceful", "entries": ["You adapt quickly to new situations."]}]},
    )
    hermit = _systems_entry(
        "background",
        "phb-background-hermit",
        "Hermit",
        metadata={
            "skill_proficiencies": [{"medicine": True, "religion": True}],
            "tool_proficiencies": ["Herbalism Kit"],
            "starting_equipment": [
                {
                    "_": [
                        {
                            "item": "map or scroll case|phb",
                            "displayName": "scroll case stuffed full of notes from your studies or prayers",
                        },
                        {"item": "blanket|phb", "displayName": "winter blanket"},
                        "common clothes|phb",
                        "herbalism kit|phb",
                        {"value": 500},
                    ]
                }
            ],
        },
        body={
            "entries": [
                {
                    "name": "Feature: Discovery",
                    "entries": ["Your quiet seclusion has yielded a singular insight."],
                    "data": {"isFeature": True},
                }
            ]
        },
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
    evocation_savant = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-evocation-savant",
        "Evocation Savant",
        metadata={"level": 2, "class_name": "Wizard", "class_source": "PHB", "subclass_name": "School of Evocation"},
    )
    sculpt_spells = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-sculpt-spells",
        "Sculpt Spells",
        metadata={"level": 2, "class_name": "Wizard", "class_source": "PHB", "subclass_name": "School of Evocation"},
    )
    quarterstaff = _systems_entry("item", "phb-item-quarterstaff", "Quarterstaff", metadata={"weight": 4, "type": "M"})
    component_pouch = _systems_entry("item", "phb-item-component-pouch", "Component Pouch", metadata={"weight": 2})
    crystal = _systems_entry("item", "phb-item-crystal", "Crystal", metadata={"weight": 1, "type": "SCF"})
    scholars_pack = _systems_entry("item", "phb-item-scholars-pack", "Scholar's Pack", metadata={"weight": 10})
    spellbook = _systems_entry("item", "phb-item-spellbook", "Spellbook", metadata={"weight": 3})
    scroll_case = _systems_entry("item", "phb-item-map-or-scroll-case", "Map or Scroll Case", metadata={"weight": 1})
    blanket = _systems_entry("item", "phb-item-blanket", "Blanket", metadata={"weight": 3})
    common_clothes = _systems_entry("item", "phb-item-common-clothes", "Common Clothes", metadata={"weight": 3})
    herbalism_kit = _systems_entry("item", "phb-item-herbalism-kit", "Herbalism Kit", metadata={"weight": 3, "type": "AT"})

    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    mage_hand = _systems_entry("spell", "phb-spell-mage-hand", "Mage Hand", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="231")
    find_familiar = _systems_entry("spell", "phb-spell-find-familiar", "Find Familiar", metadata={"casting_time": [{"number": 1, "unit": "hour"}]}, source_page="240")
    mage_armor = _systems_entry("spell", "phb-spell-mage-armor", "Mage Armor", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="256")
    magic_missile = _systems_entry("spell", "phb-spell-magic-missile", "Magic Missile", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="257")
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"casting_time": [{"number": 1, "unit": "reaction"}]}, source_page="275")
    sleep = _systems_entry("spell", "phb-spell-sleep", "Sleep", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="276")
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="282")
    burning_hands = _systems_entry("spell", "phb-spell-burning-hands", "Burning Hands", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="220")

    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [human],
            "background": [hermit],
            "feat": [],
            "subclass": [evocation],
            "item": [
                quarterstaff,
                component_pouch,
                crystal,
                scholars_pack,
                spellbook,
                scroll_case,
                blanket,
                common_clothes,
                herbalism_kit,
            ],
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
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                    {"label": "Arcane Recovery", "entry": arcane_recovery, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Arcane Tradition", "entry": arcane_tradition, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
        subclass_progression=[
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {"label": "Evocation Savant", "entry": evocation_savant, "embedded_card": {"option_groups": []}},
                    {"label": "Sculpt Spells", "entry": sculpt_spells, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    base_form_values = {
        "name": "Mira Vale",
        "character_slug": "mira-vale",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": wizard.slug,
        "species_slug": human.slug,
        "background_slug": hermit.slug,
        "class_skill_1": "arcana",
        "class_skill_2": "history",
        "str": "8",
        "dex": "14",
        "con": "13",
        "int": "16",
        "wis": "12",
        "cha": "10",
    }

    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", base_form_values)
    level_one_form = {
        **base_form_values,
        "class_equipment_1": _field_value_for_label(level_one_context, "class_equipment_1", "Quarterstaff"),
        "class_equipment_2": _field_value_for_label(level_one_context, "class_equipment_2", "Crystal"),
        "class_equipment_3": _field_value_for_label(level_one_context, "class_equipment_3", "Scholar's Pack"),
        "spell_cantrip_1": _field_value_for_label(level_one_context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(level_one_context, "spell_cantrip_2", "Mage Hand"),
        "spell_cantrip_3": _field_value_for_label(level_one_context, "spell_cantrip_3", "Message"),
        "wizard_spellbook_1": _field_value_for_label(level_one_context, "wizard_spellbook_1", "Detect Magic"),
        "wizard_spellbook_2": _field_value_for_label(level_one_context, "wizard_spellbook_2", "Find Familiar"),
        "wizard_spellbook_3": _field_value_for_label(level_one_context, "wizard_spellbook_3", "Mage Armor"),
        "wizard_spellbook_4": _field_value_for_label(level_one_context, "wizard_spellbook_4", "Magic Missile"),
        "wizard_spellbook_5": _field_value_for_label(level_one_context, "wizard_spellbook_5", "Shield"),
        "wizard_spellbook_6": _field_value_for_label(level_one_context, "wizard_spellbook_6", "Sleep"),
        "wizard_prepared_1": _field_value_for_label(level_one_context, "wizard_prepared_1", "Detect Magic"),
        "wizard_prepared_2": _field_value_for_label(level_one_context, "wizard_prepared_2", "Mage Armor"),
        "wizard_prepared_3": _field_value_for_label(level_one_context, "wizard_prepared_3", "Magic Missile"),
        "wizard_prepared_4": _field_value_for_label(level_one_context, "wizard_prepared_4", "Shield"),
    }
    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", level_one_form)
    level_one_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, level_one_form)

    level_up_form = {
        "hp_gain": "4",
        "subclass_slug": evocation.slug,
        "levelup_wizard_spellbook_1": thunderwave.slug,
        "levelup_wizard_spellbook_2": burning_hands.slug,
        "levelup_wizard_prepared_1": thunderwave.slug,
    }
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        level_one_definition,
        level_up_form,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        level_one_definition,
        level_up_context,
        level_up_form,
    )

    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}
    feature_names = {feature["name"] for feature in leveled_definition.features}

    assert leveled_definition.profile["class_level_text"] == "Wizard 2"
    assert leveled_definition.profile["subclass_ref"]["slug"] == evocation.slug
    assert leveled_definition.stats["max_hp"] == level_one_definition.stats["max_hp"] + 4
    assert leveled_definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 3}]
    assert spells_by_name["Thunderwave"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Burning Hands"]["mark"] == "Spellbook"
    assert feature_names >= {"Evocation Savant", "Sculpt Spells"}
def test_native_level_up_adds_structured_subclass_prepared_spells():
    paladin = _systems_entry(
        "class",
        "phb-class-paladin",
        "Paladin",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Sacred Oath",
        },
    )
    devotion = _systems_entry(
        "subclass",
        "phb-subclass-paladin-oath-of-devotion",
        "Oath of Devotion",
        metadata={
            "class_name": "Paladin",
            "class_source": "PHB",
            "additional_spells": [
                {
                    "prepared": {
                        "3": ["Protection from Evil and Good", "Sanctuary"],
                        "5": ["Lesser Restoration", "Zone of Truth"],
                    }
                }
            ],
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
    sacred_oath = _systems_entry(
        "classfeature",
        "phb-classfeature-sacred-oath",
        "Sacred Oath",
        metadata={"level": 3},
    )
    oath_of_devotion = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-oath-of-devotion",
        "Oath of Devotion",
        metadata={"level": 3, "class_name": "Paladin", "class_source": "PHB", "subclass_name": "Oath of Devotion"},
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    command = _systems_entry("spell", "phb-spell-command", "Command", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    protection_from_evil = _systems_entry(
        "spell",
        "phb-spell-protection-from-evil-and-good",
        "Protection from Evil and Good",
        metadata={"casting_time": [{"number": 1, "unit": "action"}]},
    )
    sanctuary = _systems_entry("spell", "phb-spell-sanctuary", "Sanctuary", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [paladin],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [devotion],
            "item": [],
            "spell": [
                bless,
                command,
                cure_wounds,
                protection_from_evil,
                sanctuary,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Sacred Oath", "entry": sacred_oath, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Oath of Devotion", "entry": oath_of_devotion, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("ser-galen", "Ser Galen")
    current_definition.profile["class_level_text"] = "Paladin 2"
    current_definition.profile["classes"][0]["class_name"] = "Paladin"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|phb|paladin",
        "entry_type": "class",
        "title": "Paladin",
        "slug": paladin.slug,
        "source_id": "PHB",
    }
    current_definition.profile["class_ref"] = dict(current_definition.profile["classes"][0]["systems_ref"])
    current_definition.stats["max_hp"] = 22
    current_definition.stats["proficiency_bonus"] = 2
    current_definition.stats["ability_scores"] = {
        "str": {"score": 16, "modifier": 3, "save_bonus": 3},
        "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
        "con": {"score": 14, "modifier": 2, "save_bonus": 2},
        "int": {"score": 8, "modifier": -1, "save_bonus": -1},
        "wis": {"score": 12, "modifier": 1, "save_bonus": 3},
        "cha": {"score": 16, "modifier": 3, "save_bonus": 5},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Paladin",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {"name": "Bless", "mark": "Prepared", "systems_ref": {"slug": bless.slug, "title": bless.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Shield of Faith", "mark": "Prepared", "systems_ref": {"slug": shield_of_faith.slug, "title": shield_of_faith.title, "entry_type": "spell", "source_id": "PHB"}},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-2"

    base_form = {"hp_gain": "6", "subclass_slug": devotion.slug}
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        base_form,
    )
    prepared_spell_field = next(
        field
        for section in level_up_context["choice_sections"]
        if section["title"] == "Spell Choices"
        for field in section["fields"]
        if field["name"] == "levelup_prepared_spell_1"
    )
    option_labels = {option["label"] for option in prepared_spell_field["options"]}

    assert "Protection from Evil and Good" not in option_labels
    assert "Sanctuary" not in option_labels
    assert level_up_context["preview"]["new_spells"] == ["Protection from Evil and Good", "Sanctuary"]

    level_up_form = {
        **base_form,
        "levelup_prepared_spell_1": _field_value_for_label(level_up_context, "levelup_prepared_spell_1", "Command"),
        "levelup_prepared_spell_2": _field_value_for_label(level_up_context, "levelup_prepared_spell_2", "Cure Wounds"),
    }
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_form,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert leveled_definition.profile["subclass_ref"]["slug"] == devotion.slug
    assert spells_by_name["Command"]["mark"] == "Prepared"
    assert spells_by_name["Protection from Evil and Good"]["is_always_prepared"] is True
    assert spells_by_name["Sanctuary"]["is_always_prepared"] is True
def test_native_level_up_adds_feature_level_additional_spells():
    paladin = _systems_entry(
        "class",
        "phb-class-paladin",
        "Paladin",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Sacred Oath",
        },
    )
    devotion = _systems_entry(
        "subclass",
        "phb-subclass-paladin-oath-of-devotion",
        "Oath of Devotion",
        metadata={"class_name": "Paladin", "class_source": "PHB"},
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
    sacred_oath = _systems_entry(
        "classfeature",
        "phb-classfeature-sacred-oath",
        "Sacred Oath",
        metadata={"level": 3},
    )
    oath_of_devotion = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-oath-of-devotion",
        "Oath of Devotion",
        metadata={
            "level": 3,
            "class_name": "Paladin",
            "class_source": "PHB",
            "subclass_name": "Oath of Devotion",
            "additional_spells": [
                {
                    "prepared": {
                        "3": ["Protection from Evil and Good", "Sanctuary"],
                        "5": ["Lesser Restoration", "Zone of Truth"],
                    }
                }
            ],
        },
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    command = _systems_entry("spell", "phb-spell-command", "Command", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    protection_from_evil = _systems_entry(
        "spell",
        "phb-spell-protection-from-evil-and-good",
        "Protection from Evil and Good",
        metadata={"casting_time": [{"number": 1, "unit": "action"}]},
    )
    sanctuary = _systems_entry("spell", "phb-spell-sanctuary", "Sanctuary", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [paladin],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [devotion],
            "item": [],
            "spell": [
                bless,
                command,
                cure_wounds,
                protection_from_evil,
                sanctuary,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Sacred Oath", "entry": sacred_oath, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Oath of Devotion", "entry": oath_of_devotion, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("ser-galen", "Ser Galen")
    current_definition.profile["class_level_text"] = "Paladin 2"
    current_definition.profile["classes"][0]["class_name"] = "Paladin"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|phb|paladin",
        "entry_type": "class",
        "title": "Paladin",
        "slug": paladin.slug,
        "source_id": "PHB",
    }
    current_definition.profile["class_ref"] = dict(current_definition.profile["classes"][0]["systems_ref"])
    current_definition.stats["max_hp"] = 22
    current_definition.stats["proficiency_bonus"] = 2
    current_definition.stats["ability_scores"] = {
        "str": {"score": 16, "modifier": 3, "save_bonus": 3},
        "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
        "con": {"score": 14, "modifier": 2, "save_bonus": 2},
        "int": {"score": 8, "modifier": -1, "save_bonus": -1},
        "wis": {"score": 12, "modifier": 1, "save_bonus": 3},
        "cha": {"score": 16, "modifier": 3, "save_bonus": 5},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Paladin",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {"name": "Bless", "mark": "Prepared", "systems_ref": {"slug": bless.slug, "title": bless.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Shield of Faith", "mark": "Prepared", "systems_ref": {"slug": shield_of_faith.slug, "title": shield_of_faith.title, "entry_type": "spell", "source_id": "PHB"}},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-2"

    base_form = {"hp_gain": "6", "subclass_slug": devotion.slug}
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        base_form,
    )
    prepared_spell_field = next(
        field
        for section in level_up_context["choice_sections"]
        if section["title"] == "Spell Choices"
        for field in section["fields"]
        if field["name"] == "levelup_prepared_spell_1"
    )
    option_labels = {option["label"] for option in prepared_spell_field["options"]}

    assert "Protection from Evil and Good" not in option_labels
    assert "Sanctuary" not in option_labels
    assert level_up_context["preview"]["new_spells"] == ["Protection from Evil and Good", "Sanctuary"]

    level_up_form = {
        **base_form,
        "levelup_prepared_spell_1": _field_value_for_label(level_up_context, "levelup_prepared_spell_1", "Command"),
        "levelup_prepared_spell_2": _field_value_for_label(level_up_context, "levelup_prepared_spell_2", "Cure Wounds"),
    }
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_form,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert leveled_definition.profile["subclass_ref"]["slug"] == devotion.slug
    assert spells_by_name["Command"]["mark"] == "Prepared"
    assert spells_by_name["Protection from Evil and Good"]["is_always_prepared"] is True
    assert spells_by_name["Sanctuary"]["is_always_prepared"] is True
def test_native_level_up_adds_feature_level_innate_spells():
    paladin = _systems_entry(
        "class",
        "phb-class-paladin",
        "Paladin",
        metadata={
            "hit_die": {"faces": 10},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Sacred Oath",
        },
    )
    devotion = _systems_entry(
        "subclass",
        "phb-subclass-paladin-oath-of-devotion",
        "Oath of Devotion",
        metadata={"class_name": "Paladin", "class_source": "PHB"},
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
    sacred_oath = _systems_entry(
        "classfeature",
        "phb-classfeature-sacred-oath",
        "Sacred Oath",
        metadata={"level": 3},
    )
    oath_of_devotion = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-oath-of-devotion",
        "Oath of Devotion",
        metadata={
            "level": 3,
            "class_name": "Paladin",
            "class_source": "PHB",
            "subclass_name": "Oath of Devotion",
            "additional_spells": [
                {
                    "innate": {
                        "3": {
                            "daily": {
                                "1": ["Sanctuary"],
                            }
                        }
                    }
                }
            ],
        },
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    command = _systems_entry("spell", "phb-spell-command", "Command", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    sanctuary = _systems_entry("spell", "phb-spell-sanctuary", "Sanctuary", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})
    shield_of_faith = _systems_entry("spell", "phb-spell-shield-of-faith", "Shield of Faith", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]})

    systems_service = _FakeSystemsService(
        {
            "class": [paladin],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [devotion],
            "item": [],
            "spell": [
                bless,
                command,
                cure_wounds,
                sanctuary,
                shield_of_faith,
            ],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Sacred Oath", "entry": sacred_oath, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Oath of Devotion", "entry": oath_of_devotion, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
    )

    current_definition = _minimal_character_definition("ser-galen", "Ser Galen")
    current_definition.profile["class_level_text"] = "Paladin 2"
    current_definition.profile["classes"][0]["class_name"] = "Paladin"
    current_definition.profile["classes"][0]["level"] = 2
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|phb|paladin",
        "entry_type": "class",
        "title": "Paladin",
        "slug": paladin.slug,
        "source_id": "PHB",
    }
    current_definition.profile["class_ref"] = dict(current_definition.profile["classes"][0]["systems_ref"])
    current_definition.stats["max_hp"] = 22
    current_definition.stats["proficiency_bonus"] = 2
    current_definition.stats["ability_scores"] = {
        "str": {"score": 16, "modifier": 3, "save_bonus": 3},
        "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
        "con": {"score": 14, "modifier": 2, "save_bonus": 2},
        "int": {"score": 8, "modifier": -1, "save_bonus": -1},
        "wis": {"score": 12, "modifier": 1, "save_bonus": 3},
        "cha": {"score": 16, "modifier": 3, "save_bonus": 5},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Paladin",
        "spellcasting_ability": "Charisma",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 2}],
        "spells": [
            {"name": "Bless", "mark": "Prepared", "systems_ref": {"slug": bless.slug, "title": bless.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Shield of Faith", "mark": "Prepared", "systems_ref": {"slug": shield_of_faith.slug, "title": shield_of_faith.title, "entry_type": "spell", "source_id": "PHB"}},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-2"

    base_form = {"hp_gain": "6", "subclass_slug": devotion.slug}
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        base_form,
    )

    assert "Sanctuary" in level_up_context["preview"]["new_spells"]

    level_up_form = {
        **base_form,
        "levelup_prepared_spell_1": _field_value_for_label(level_up_context, "levelup_prepared_spell_1", "Command"),
        "levelup_prepared_spell_2": _field_value_for_label(level_up_context, "levelup_prepared_spell_2", "Cure Wounds"),
    }
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_form,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert spells_by_name["Sanctuary"]["mark"] == "1 / Long Rest"
    assert spells_by_name["Command"]["mark"] == "Prepared"
def test_native_level_up_applies_optionalfeature_additional_spells():
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
    spellcasting_feature = _systems_entry("classfeature", "phb-classfeature-spellcasting", "Spellcasting", metadata={"level": 1})
    mystic_training = _systems_entry(
        "classfeature",
        "phb-classfeature-mystic-training",
        "Mystic Training",
        metadata={"level": 2},
    )
    druidic_initiate = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-druidic-initiate",
        "Druidic Initiate",
        metadata={
            "additional_spells": [
                {
                    "known": {"2": {"_": [{"choose": "level=0|class=Druid"}]}},
                    "prepared": {"2": ["Animal Friendship"]},
                }
            ]
        },
    )
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    thaumaturgy = _systems_entry("spell", "phb-spell-thaumaturgy", "Thaumaturgy", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    druidcraft = _systems_entry("spell", "phb-spell-druidcraft", "Druidcraft", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0})
    shillelagh = _systems_entry("spell", "phb-spell-shillelagh", "Shillelagh", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 0})
    animal_friendship = _systems_entry("spell", "phb-spell-animal-friendship", "Animal Friendship", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    guiding_bolt = _systems_entry("spell", "phb-spell-guiding-bolt", "Guiding Bolt", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    healing_word = _systems_entry("spell", "phb-spell-healing-word", "Healing Word", metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 1})
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [],
            "optionalfeature": [druidic_initiate],
            "item": [],
            "spell": [
                light,
                sacred_flame,
                thaumaturgy,
                druidcraft,
                shillelagh,
                animal_friendship,
                detect_magic,
                guiding_bolt,
                healing_word,
                bless,
                cure_wounds,
            ],
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {"label": "Spellcasting", "entry": spellcasting_feature, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 2,
                "level_label": "Level 2",
                "feature_rows": [
                    {
                        "label": "Mystic Training",
                        "entry": mystic_training,
                        "embedded_card": {
                            "option_groups": [
                                {
                                    "options": [
                                        {"label": "Druidic Initiate", "slug": druidic_initiate.slug},
                                    ]
                                }
                            ]
                        },
                    },
                ],
            },
        ],
    )
    level_one_form = {
        "name": "Sister Elm",
        "character_slug": "sister-elm",
        "alignment": "Neutral Good",
        "experience_model": "Milestone",
        "class_slug": cleric.slug,
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

    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", level_one_form)
    level_one_form = {
        **level_one_form,
        "spell_cantrip_1": _field_value_for_label(level_one_context, "spell_cantrip_1", "Light"),
        "spell_cantrip_2": _field_value_for_label(level_one_context, "spell_cantrip_2", "Sacred Flame"),
        "spell_cantrip_3": _field_value_for_label(level_one_context, "spell_cantrip_3", "Thaumaturgy"),
        "spell_level_one_1": _field_value_for_label(level_one_context, "spell_level_one_1", "Detect Magic"),
        "spell_level_one_2": _field_value_for_label(level_one_context, "spell_level_one_2", "Guiding Bolt"),
        "spell_level_one_3": _field_value_for_label(level_one_context, "spell_level_one_3", "Healing Word"),
        "spell_level_one_4": _field_value_for_label(level_one_context, "spell_level_one_4", "Bless"),
    }
    level_one_context = build_level_one_builder_context(systems_service, "linden-pass", level_one_form)
    current_definition, _ = build_level_one_character_definition("linden-pass", level_one_context, level_one_form)

    level_up_form = {
        "hp_gain": "5",
        "levelup_class_option_1": druidic_initiate.slug,
    }
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        level_up_form,
    )
    granted_field = _find_builder_field(level_up_context, "levelup_bonus_spell_known_1_1")
    granted_labels = {option["label"] for option in granted_field["options"]}
    level_up_form = {
        **level_up_form,
        "levelup_bonus_spell_known_1_1": _field_value_for_label(
            level_up_context,
            "levelup_bonus_spell_known_1_1",
            "Shillelagh",
        ),
        "levelup_prepared_spell_1": _field_value_for_label(level_up_context, "levelup_prepared_spell_1", "Cure Wounds"),
    }

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        level_up_form,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_form,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert {"Druidcraft", "Shillelagh"} <= granted_labels
    assert "Shillelagh" in level_up_context["preview"]["new_spells"]
    assert spells_by_name["Shillelagh"]["is_bonus_known"] is True
    assert spells_by_name["Animal Friendship"]["is_always_prepared"] is True
def test_native_level_up_advances_wizard_to_level_four_with_cantrip_and_asi_growth():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "subclass_title": "Arcane Tradition",
            "starting_proficiencies": {
                "armor": [],
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "insight"]}}],
            },
        },
    )
    evocation = _systems_entry(
        "subclass",
        "phb-subclass-wizard-school-of-evocation",
        "School of Evocation",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
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
    light = _systems_entry("spell", "phb-spell-light", "Light", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    mage_hand = _systems_entry("spell", "phb-spell-mage-hand", "Mage Hand", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    prestidigitation = _systems_entry("spell", "phb-spell-prestidigitation", "Prestidigitation", metadata={"casting_time": [{"number": 1, "unit": "action"}]})
    detect_magic = _systems_entry("spell", "phb-spell-detect-magic", "Detect Magic", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="231")
    mage_armor = _systems_entry("spell", "phb-spell-mage-armor", "Mage Armor", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="256")
    magic_missile = _systems_entry("spell", "phb-spell-magic-missile", "Magic Missile", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="257")
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"casting_time": [{"number": 1, "unit": "reaction"}]}, source_page="275")
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="282")
    burning_hands = _systems_entry("spell", "phb-spell-burning-hands", "Burning Hands", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="220")
    misty_step = _systems_entry("spell", "phb-spell-misty-step", "Misty Step", metadata={"casting_time": [{"number": 1, "unit": "bonus"}]}, source_page="260")
    scorching_ray = _systems_entry("spell", "phb-spell-scorching-ray", "Scorching Ray", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="273")
    mirror_image = _systems_entry("spell", "phb-spell-mirror-image", "Mirror Image", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="260")
    web = _systems_entry("spell", "phb-spell-web", "Web", metadata={"casting_time": [{"number": 1, "unit": "action"}]}, source_page="287")

    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "race": [human],
            "background": [acolyte],
            "feat": [],
            "subclass": [evocation],
            "item": [],
            "spell": [
                light,
                mage_hand,
                message,
                prestidigitation,
                detect_magic,
                mage_armor,
                magic_missile,
                shield,
                thunderwave,
                burning_hands,
                misty_step,
                scorching_ray,
                mirror_image,
                web,
            ],
        },
        class_progression=[
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {"label": "Ability Score Improvement", "entry": ability_score_improvement, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
        subclass_progression=[],
    )

    current_definition = _minimal_character_definition("mira-vale", "Mira Vale")
    current_definition.profile["class_level_text"] = "Wizard 3"
    current_definition.profile["classes"][0]["class_name"] = "Wizard"
    current_definition.profile["classes"][0]["level"] = 3
    current_definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|phb|wizard",
        "entry_type": "class",
        "title": "Wizard",
        "slug": "phb-class-wizard",
        "source_id": "PHB",
    }
    current_definition.profile["class_ref"] = dict(current_definition.profile["classes"][0]["systems_ref"])
    current_definition.profile["subclass_ref"] = {
        "entry_key": "dnd-5e|subclass|phb|school-of-evocation",
        "entry_type": "subclass",
        "title": "School of Evocation",
        "slug": evocation.slug,
        "source_id": "PHB",
    }
    current_definition.profile["classes"][0]["subclass_name"] = "School of Evocation"
    current_definition.profile["classes"][0]["subclass_ref"] = dict(current_definition.profile["subclass_ref"])
    current_definition.stats["max_hp"] = 18
    current_definition.stats["proficiency_bonus"] = 2
    current_definition.stats["ability_scores"] = {
        "str": {"score": 8, "modifier": -1, "save_bonus": -1},
        "dex": {"score": 14, "modifier": 2, "save_bonus": 2},
        "con": {"score": 13, "modifier": 1, "save_bonus": 1},
        "int": {"score": 16, "modifier": 3, "save_bonus": 5},
        "wis": {"score": 12, "modifier": 1, "save_bonus": 3},
        "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Wizard",
        "spellcasting_ability": "Intelligence",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 2}],
        "spells": [
            {"name": "Light", "mark": "Cantrip", "systems_ref": {"slug": light.slug, "title": light.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Mage Hand", "mark": "Cantrip", "systems_ref": {"slug": mage_hand.slug, "title": mage_hand.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Message", "mark": "Cantrip", "systems_ref": {"slug": message.slug, "title": message.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Detect Magic", "mark": "Prepared + Spellbook", "systems_ref": {"slug": detect_magic.slug, "title": detect_magic.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Mage Armor", "mark": "Prepared + Spellbook", "systems_ref": {"slug": mage_armor.slug, "title": mage_armor.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Magic Missile", "mark": "Prepared + Spellbook", "systems_ref": {"slug": magic_missile.slug, "title": magic_missile.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Shield", "mark": "Prepared + Spellbook", "systems_ref": {"slug": shield.slug, "title": shield.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Thunderwave", "mark": "Prepared + Spellbook", "systems_ref": {"slug": thunderwave.slug, "title": thunderwave.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Burning Hands", "mark": "Spellbook", "systems_ref": {"slug": burning_hands.slug, "title": burning_hands.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Misty Step", "mark": "Prepared + Spellbook", "systems_ref": {"slug": misty_step.slug, "title": misty_step.title, "entry_type": "spell", "source_id": "PHB"}},
            {"name": "Scorching Ray", "mark": "Spellbook", "systems_ref": {"slug": scorching_ray.slug, "title": scorching_ray.title, "entry_type": "spell", "source_id": "PHB"}},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-3"

    level_up_form = {
        "hp_gain": "4",
        "levelup_asi_mode_1": "ability_scores",
        "levelup_asi_ability_1_1": "int",
        "levelup_asi_ability_1_2": "int",
        "levelup_spell_cantrip_1": prestidigitation.slug,
        "levelup_wizard_spellbook_1": mirror_image.slug,
        "levelup_wizard_spellbook_2": web.slug,
        "levelup_wizard_prepared_1": burning_hands.slug,
        "levelup_wizard_prepared_2": web.slug,
    }

    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        level_up_form,
    )
    field_names = {
        field["name"]
        for section in level_up_context["choice_sections"]
        for field in section["fields"]
    }
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        level_up_form,
    )

    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert level_up_context["preview"]["gained_features"] == ["Intelligence +2"]
    assert {"levelup_spell_cantrip_1", "levelup_wizard_spellbook_1", "levelup_wizard_spellbook_2"} <= field_names
    assert {"levelup_wizard_prepared_1", "levelup_wizard_prepared_2"} <= field_names
    assert leveled_definition.profile["class_level_text"] == "Wizard 4"
    assert leveled_definition.stats["ability_scores"]["int"]["score"] == 18
    assert leveled_definition.spellcasting["spell_save_dc"] == 14
    assert leveled_definition.spellcasting["spell_attack_bonus"] == 6
    assert leveled_definition.spellcasting["slot_progression"] == [{"level": 1, "max_slots": 4}, {"level": 2, "max_slots": 3}]
    assert spells_by_name["Prestidigitation"]["mark"] == "Cantrip"
    assert spells_by_name["Mirror Image"]["mark"] == "Spellbook"
    assert spells_by_name["Web"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Burning Hands"]["mark"] == "Prepared + Spellbook"
