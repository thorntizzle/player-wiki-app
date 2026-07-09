from __future__ import annotations

from tests.helpers.character_builder_fakes import *  # noqa: F401,F403

def test_imported_character_readiness_is_ready_when_required_links_are_present():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
    )
    definition = _minimal_imported_character_definition()

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_class"].slug == fighter.slug
    assert readiness["selected_subclass"].slug == champion.slug
def test_imported_character_with_missing_progression_links_is_ready_when_titles_match_uniquely():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
    )
    definition = _minimal_imported_character_definition()
    definition.profile.pop("class_ref", None)
    definition.profile["classes"][0].pop("systems_ref", None)
    definition.profile.pop("species_ref", None)
    definition.profile.pop("background_ref", None)
    definition.profile.pop("subclass_ref", None)
    definition.profile["classes"][0].pop("subclass_ref", None)

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_class"].slug == fighter.slug
    assert readiness["selected_subclass"].slug == champion.slug
    assert readiness["selected_species"].slug == human.slug
    assert readiness["selected_background"].slug == acolyte.slug
    assert readiness["reasons"] == []
def test_imported_character_with_missing_progression_links_stays_repairable_when_titles_are_ambiguous():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    phb_human = _systems_entry("race", "phb-race-human", "Human", source_id="PHB")
    tce_human = _systems_entry("race", "tce-race-human", "Human", source_id="TCE")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion],
            "race": [phb_human, tce_human],
            "background": [acolyte],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
        enabled_source_ids=["PHB", "TCE"],
    )
    definition = _minimal_imported_character_definition()
    definition.profile.pop("species_ref", None)

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "repairable"
    assert readiness["selected_species"] is None
    assert any("species link" in reason for reason in readiness["reasons"])
def test_normalize_definition_persists_recovered_imported_progression_links():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
    )
    definition = _minimal_imported_character_definition()
    definition.profile.pop("class_ref", None)
    definition.profile["classes"][0].pop("systems_ref", None)
    definition.profile.pop("subclass_ref", None)
    definition.profile["classes"][0].pop("subclass_ref", None)
    definition.profile.pop("species_ref", None)
    definition.profile.pop("background_ref", None)

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.profile["class_ref"]["slug"] == fighter.slug
    assert normalized.profile["classes"][0]["systems_ref"]["slug"] == fighter.slug
    assert normalized.profile["subclass_ref"]["slug"] == champion.slug
    assert normalized.profile["classes"][0]["subclass_ref"]["slug"] == champion.slug
    assert normalized.profile["species_ref"]["slug"] == human.slug
    assert normalized.profile["background_ref"]["slug"] == acolyte.slug
def test_multiclass_readiness_uses_class_rows_for_total_level_even_when_legacy_summary_is_stale():
    systems_service = _FakeSystemsService({}, class_progression=[])
    definition = _minimal_character_definition("multiclass-hero", "Multiclass Hero")
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], level=3),
        {
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 2,
            "systems_ref": {
                "entry_key": "dnd-5e|class|phb|wizard",
                "entry_type": "class",
                "title": "Wizard",
                "slug": "phb-class-wizard",
                "source_id": "PHB",
            },
        },
    ]

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "unsupported"
    assert readiness["current_level"] == 5
    assert "missing enabled links" in readiness["message"].lower()
def test_multiclass_readiness_allows_shared_slot_spellcasting_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={"hit_die": {"faces": 6}, "proficiency": ["int", "wis"]},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, wizard],
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
            wizard.slug: [
                {"level": 1, "feature_rows": [_progression_row("Spellcasting")]},
            ],
        },
    )
    definition = _minimal_character_definition("fighter-wizard", "Fighter Wizard")
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], level=1),
        {
            "row_id": "class-row-2",
            "class_name": "Wizard",
            "subclass_name": "",
            "level": 1,
            "systems_ref": {
                "entry_key": wizard.entry_key,
                "entry_type": wizard.entry_type,
                "title": wizard.title,
                "slug": wizard.slug,
                "source_id": wizard.source_id,
            },
        },
    ]
    definition.profile["class_level_text"] = "Fighter 1 / Wizard 1"

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["shared_slot_multiclass_ready"] is True
    wizard_row = next(row for row in readiness["selected_class_rows"] if row["row_id"] == "class-row-2")
    assert wizard_row["shared_slot_multiclass_supported"] is True
    assert wizard_row["spellcasting_row"] is True
def test_multiclass_readiness_allows_pact_magic_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
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
            "class": [fighter, warlock],
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
            warlock.slug: [
                {"level": 1, "feature_rows": [_progression_row("Pact Magic")]},
            ],
        },
    )
    definition = _minimal_character_definition("fighter-warlock", "Fighter Warlock")
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], level=1),
        {
            "row_id": "class-row-2",
            "class_name": "Warlock",
            "subclass_name": "",
            "level": 1,
            "systems_ref": _systems_ref(warlock),
        },
    ]
    definition.profile["class_level_text"] = "Fighter 1 / Warlock 1"

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["shared_slot_multiclass_ready"] is True
    warlock_row = next(row for row in readiness["selected_class_rows"] if row["row_id"] == "class-row-2")
    assert warlock_row["shared_slot_multiclass_supported"] is True
    assert warlock_row["spellcasting_row"] is True
def test_multiclass_readiness_allows_supported_subclass_only_spellcasting_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
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
            "subclass": [champion, eldritch_knight],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}]},
        subclass_by_slug={
            eldritch_knight.slug: [
                {"level": 3, "feature_rows": [_progression_row("Spellcasting")]},
            ],
            champion.slug: [],
        },
    )
    definition = _minimal_character_definition("double-fighter", "Double Fighter")
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], level=3, subclass_name="Champion", subclass_ref=_systems_ref(champion)),
        {
            "row_id": "class-row-2",
            "class_name": "Fighter",
            "subclass_name": "Eldritch Knight",
            "level": 3,
            "systems_ref": _systems_ref(fighter),
            "subclass_ref": _systems_ref(eldritch_knight),
        },
    ]
    definition.profile["subclass_ref"] = _systems_ref(champion)
    definition.profile["class_level_text"] = "Fighter 3 / Fighter 3"

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["shared_slot_multiclass_ready"] is True
    eldritch_knight_row = next(row for row in readiness["selected_class_rows"] if row["row_id"] == "class-row-2")
    assert eldritch_knight_row["shared_slot_multiclass_supported"] is True
    assert eldritch_knight_row["spellcasting_row"] is True
def test_multiclass_readiness_blocks_unsupported_subclass_only_spellcasting_rows():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    spellblade = _systems_entry(
        "subclass",
        "phb-subclass-spellblade",
        "Spellblade",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion, spellblade],
            "race": [human],
            "background": [acolyte],
        },
        class_progression=[],
    )
    _set_progressions(
        systems_service,
        class_by_slug={fighter.slug: [{"level": 3, "feature_rows": [_progression_row("Martial Archetype")]}]},
        subclass_by_slug={
            spellblade.slug: [
                {"level": 3, "feature_rows": [_progression_row("Spellcasting")]},
            ],
            champion.slug: [],
        },
    )
    definition = _minimal_character_definition("fighter-spellblade", "Fighter Spellblade")
    definition.profile["classes"] = [
        dict(definition.profile["classes"][0], level=3, subclass_name="Champion", subclass_ref=_systems_ref(champion)),
        {
            "row_id": "class-row-2",
            "class_name": "Fighter",
            "subclass_name": "Spellblade",
            "level": 3,
            "systems_ref": _systems_ref(fighter),
            "subclass_ref": _systems_ref(spellblade),
        },
    ]
    definition.profile["subclass_ref"] = _systems_ref(champion)
    definition.profile["class_level_text"] = "Fighter 3 / Fighter 3"

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "unsupported"
    assert "multiclass spellcasting progression lane" in readiness["message"].lower()
    assert any("subclass-only spellcasting" in reason.lower() for reason in readiness["reasons"])
def test_multiclass_readiness_supports_structured_subclass_only_spellcasting_rows():
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
        subclass_by_slug={
            spellblade.slug: [{"level": 3, "feature_rows": [_progression_row("Spellcasting")]}],
        },
    )
    definition = _minimal_character_definition("fighter-spellblade-wizard", "Fighter Spellblade Wizard")
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

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_class_rows"][0]["selected_subclass"].slug == spellblade.slug
def test_imported_multiclass_rows_with_recoverable_links_unlock_native_advancement_without_repair():
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
    definition = _minimal_imported_character_definition("imported-ftr-rogue", "Imported Fighter Rogue")
    definition.profile["classes"] = [
        {"row_id": "class-row-1", "class_name": "Fighter", "subclass_name": "", "level": 1},
        {"row_id": "class-row-2", "class_name": "Rogue", "subclass_name": "", "level": 1},
    ]
    definition.profile["class_level_text"] = "Fighter 1 / Rogue 1"
    definition.profile.pop("class_ref", None)
    definition.profile.pop("subclass_ref", None)

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)
    assert readiness["status"] == "ready"
    assert [row["selected_class"].slug for row in readiness["selected_class_rows"]] == [fighter.slug, rogue.slug]
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
    leveled_definition, _managed_import, _hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        definition,
        context,
        context["values"],
        current_import_metadata=_minimal_import_metadata(definition.character_slug),
    )

    assert [row["row_id"] for row in leveled_definition.profile["classes"]] == ["class-row-1", "class-row-2"]
    assert [row["level"] for row in leveled_definition.profile["classes"]] == [1, 2]
    assert leveled_definition.profile["classes"][0]["systems_ref"]["slug"] == fighter.slug
    assert leveled_definition.profile["classes"][1]["systems_ref"]["slug"] == rogue.slug
    assert any(feature["name"] == "Cunning Action" for feature in leveled_definition.features)
def test_imported_multiclass_repair_supports_structured_subclass_only_spellcasting_rows():
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
    definition = _minimal_imported_character_definition("imported-spellblade-wizard", "Imported Spellblade Wizard")
    definition.profile["classes"] = [
        {"row_id": "class-row-1", "class_name": "Fighter", "subclass_name": "Spellblade", "level": 3},
        {"row_id": "class-row-2", "class_name": "Wizard", "subclass_name": "", "level": 1},
    ]
    definition.profile["class_level_text"] = "Fighter 3 / Wizard 1"
    definition.profile.pop("class_ref", None)
    definition.profile.pop("subclass_ref", None)

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    first_row_subclass_labels = [option["label"] for option in repair_context["class_rows"][0]["subclass_options"]]
    assert any("Spellblade" in label for label in first_row_subclass_labels)

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        _minimal_import_metadata(definition.character_slug),
        repair_context,
        {
            **repair_context["values"],
            "repair_class_slug_class-row-1": f"systems:{fighter.slug}",
            "repair_subclass_slug_class-row-1": f"systems:{spellblade.slug}",
            "repair_class_slug_class-row-2": f"systems:{wizard.slug}",
        },
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)

    assert repaired_readiness["status"] == "ready"
    assert repaired_definition.profile["classes"][0]["subclass_ref"]["slug"] == spellblade.slug
def test_imported_multiclass_repair_blocks_duplicate_row_repairs():
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
    definition = _minimal_imported_character_definition("duplicate-repair", "Duplicate Repair")
    definition.profile["classes"] = [
        {"row_id": "class-row-1", "class_name": "Fighter", "subclass_name": "", "level": 1},
        {"row_id": "class-row-2", "class_name": "Rogue", "subclass_name": "", "level": 1},
    ]
    definition.profile.pop("class_ref", None)
    definition.profile.pop("subclass_ref", None)

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    with pytest.raises(Exception, match="distinct class/subclass repairs"):
        apply_imported_progression_repairs(
            "linden-pass",
            definition,
            _minimal_import_metadata(definition.character_slug),
            repair_context,
            {
                **repair_context["values"],
                "repair_class_slug_class-row-1": f"systems:{fighter.slug}",
                "repair_class_slug_class-row-2": f"systems:{fighter.slug}",
            },
        )
def test_imported_character_with_unsupported_enabled_class_is_blocked():
    mystic = _systems_entry(
        "class",
        "ua-class-mystic",
        "Mystic",
        metadata={"hit_die": {"faces": 8}},
        source_id="UA",
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    systems_service = _FakeSystemsService(
        {
            "class": [mystic],
            "race": [human],
            "background": [acolyte],
            "subclass": [],
        },
        class_progression=[],
    )
    definition = _minimal_imported_character_definition()
    definition.profile["class_level_text"] = "Mystic 3"
    definition.profile["classes"][0]["class_name"] = "Mystic"
    definition.profile["classes"][0]["systems_ref"] = {
        "entry_key": "dnd-5e|class|ua|mystic",
        "entry_type": "class",
        "title": "Mystic",
        "slug": "ua-class-mystic",
        "source_id": "UA",
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["classes"][0]["subclass_name"] = ""
    definition.profile["classes"][0].pop("subclass_ref", None)
    definition.profile.pop("subclass_ref", None)

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "unsupported"
    assert "native support lane" in readiness["message"].lower()
def test_imported_artificer_with_stale_enabled_class_metadata_uses_reference_progression():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "tools": ["thieves' tools", "tinker's tools"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "medicine"]}}],
            },
        },
    )
    armorer = _systems_entry(
        "subclass",
        "tce-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="TCE",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    faerie_fire = _systems_entry(
        "spell",
        "phb-spell-faerie-fire",
        "Faerie Fire",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
    )
    web = _systems_entry(
        "spell",
        "phb-spell-web",
        "Web",
        metadata={"level": 2, "class_lists": {"TCE": ["Artificer"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [armorer],
            "race": [human],
            "background": [sage],
            "spell": [cure_wounds, faerie_fire, web],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Artificer Specialist"}]}],
        enabled_source_ids=["PHB", "TCE"],
    )
    definition = _minimal_imported_character_definition("artificer-import", "Artificer Import")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "class_name": "Artificer",
        "subclass_name": "Armorer",
        "level": 5,
        "systems_ref": {
            "entry_key": "dnd-5e|class|tce|artificer",
            "entry_type": "class",
            "title": "Artificer",
            "slug": artificer.slug,
            "source_id": "TCE",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|tce|armorer-artificer-tce",
            "entry_type": "subclass",
            "title": "Armorer",
            "slug": armorer.slug,
            "source_id": "TCE",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|phb|human",
        "entry_type": "race",
        "title": "Human",
        "slug": human.slug,
        "source_id": "PHB",
    }
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|sage",
        "entry_type": "background",
        "title": "Sage",
        "slug": sage.slug,
        "source_id": "PHB",
    }
    definition.stats["ability_scores"]["int"] = {"score": 16, "modifier": 3, "save_bonus": 3}

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        definition,
        {"hp_gain": "5"},
    )

    assert readiness["status"] == "ready"
    assert readiness["selected_class"].slug == artificer.slug
    assert readiness["selected_subclass"].slug == armorer.slug
    assert any(
        field["name"] == "levelup_prepared_spell_1"
        for section in level_up_context["choice_sections"]
        for field in section["fields"]
    )
def test_imported_tce_artificer_with_stale_source_locked_refs_auto_recover_to_tce_entries():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "tools": ["thieves' tools", "tinker's tools"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "medicine"]}}],
            },
        },
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
    phb_sage = _systems_entry("background", "phb-background-sage", "Sage", source_id="PHB")
    tce_sage = _systems_entry("background", "tce-background-sage", "Sage", source_id="TCE")
    phb_armorer = _systems_entry(
        "subclass",
        "phb-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="PHB",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
    )
    tce_armorer = _systems_entry(
        "subclass",
        "tce-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="TCE",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
    )
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
        source_id="PHB",
    )
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [phb_armorer, tce_armorer],
            "race": [phb_human, tce_human],
            "background": [phb_sage, tce_sage],
            "spell": [cure_wounds],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Artificer Specialist"}]}],
        enabled_source_ids=["PHB", "TCE"],
    )
    definition = _minimal_imported_character_definition("artificer-repair", "Artificer Repair")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "class_name": "Artificer",
        "subclass_name": "Armorer",
        "level": 5,
        "systems_ref": {
            "entry_key": "dnd-5e|class|tce|artificer",
            "entry_type": "class",
            "title": "Artificer",
            "slug": "stale-tce-class-artificer",
            "source_id": "TCE",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|tce|armorer-artificer-tce",
            "entry_type": "subclass",
            "title": "Armorer",
            "slug": "stale-tce-subclass-armorer",
            "source_id": "TCE",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|tce|human",
        "entry_type": "race",
        "title": "Human",
        "slug": "stale-tce-race-human",
        "source_id": "TCE",
    }
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|tce|sage",
        "entry_type": "background",
        "title": "Sage",
        "slug": "stale-tce-background-sage",
        "source_id": "TCE",
    }
    definition.stats["ability_scores"]["int"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_class"].slug == artificer.slug
    assert readiness["selected_class"].source_id == "TCE"
    assert readiness["selected_species"].slug == tce_human.slug
    assert readiness["selected_species"].source_id == "TCE"
    assert readiness["selected_background"].slug == tce_sage.slug
    assert readiness["selected_background"].source_id == "TCE"
    assert readiness["selected_subclass"].slug == tce_armorer.slug
    assert readiness["selected_subclass"].source_id == "TCE"
    assert readiness["reasons"] == []

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.profile["class_ref"]["slug"] == artificer.slug
    assert normalized.profile["class_ref"]["source_id"] == "TCE"
    assert normalized.profile["classes"][0]["systems_ref"]["slug"] == artificer.slug
    assert normalized.profile["species_ref"]["slug"] == tce_human.slug
    assert normalized.profile["species_ref"]["source_id"] == "TCE"
    assert normalized.profile["background_ref"]["slug"] == tce_sage.slug
    assert normalized.profile["background_ref"]["source_id"] == "TCE"
    assert normalized.profile["subclass_ref"]["slug"] == tce_armorer.slug
    assert normalized.profile["subclass_ref"]["source_id"] == "TCE"
def test_imported_xge_subclass_with_stale_source_locked_ref_auto_recovers_to_xge_entry():
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
        source_id="PHB",
    )
    phb_arcane_archer = _systems_entry(
        "subclass",
        "phb-subclass-fighter-arcane-archer",
        "Arcane Archer",
        source_id="PHB",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    xge_arcane_archer = _systems_entry(
        "subclass",
        "xge-subclass-fighter-arcane-archer",
        "Arcane Archer",
        source_id="XGE",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human", source_id="PHB")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte", source_id="PHB")
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [phb_arcane_archer, xge_arcane_archer],
            "race": [human],
            "background": [acolyte],
            "spell": [],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
        enabled_source_ids=["PHB", "XGE"],
    )
    definition = _minimal_imported_character_definition("xge-archer", "XGE Archer")
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["classes"][0] = {
        "class_name": "Fighter",
        "subclass_name": "Arcane Archer",
        "level": 3,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|fighter",
            "entry_type": "class",
            "title": "Fighter",
            "slug": fighter.slug,
            "source_id": "PHB",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|xge|arcane-archer",
            "entry_type": "subclass",
            "title": "Arcane Archer",
            "slug": "stale-xge-subclass-arcane-archer",
            "source_id": "XGE",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|phb|human",
        "entry_type": "race",
        "title": "Human",
        "slug": human.slug,
        "source_id": "PHB",
    }
    definition.profile["background"] = "Acolyte"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|acolyte",
        "entry_type": "background",
        "title": "Acolyte",
        "slug": acolyte.slug,
        "source_id": "PHB",
    }
    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_subclass"].slug == xge_arcane_archer.slug
    assert readiness["selected_subclass"].source_id == "XGE"
    assert readiness["reasons"] == []

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.profile["subclass_ref"]["slug"] == xge_arcane_archer.slug
    assert normalized.profile["subclass_ref"]["source_id"] == "XGE"
def test_imported_egw_subclass_with_stale_source_locked_ref_auto_recovers_to_egw_entry():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "subclass_title": "Arcane Tradition",
            "starting_proficiencies": {
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "insight", "investigation"]}}],
            },
        },
        source_id="PHB",
    )
    phb_chronurgy = _systems_entry(
        "subclass",
        "phb-subclass-wizard-chronurgy-magic",
        "Chronurgy Magic",
        source_id="PHB",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    egw_chronurgy = _systems_entry(
        "subclass",
        "egw-subclass-wizard-chronurgy-magic",
        "Chronurgy Magic",
        source_id="EGW",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human", source_id="PHB")
    sage = _systems_entry("background", "phb-background-sage", "Sage", source_id="PHB")
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "subclass": [phb_chronurgy, egw_chronurgy],
            "race": [human],
            "background": [sage],
            "spell": [],
        },
        class_progression=[{"level": 2, "feature_rows": [{"label": "Arcane Tradition"}]}],
        enabled_source_ids=["PHB", "EGW"],
    )
    definition = _minimal_imported_character_definition("egw-chronurgist", "EGW Chronurgist")
    definition.profile["class_level_text"] = "Wizard 2"
    definition.profile["classes"][0] = {
        "class_name": "Wizard",
        "subclass_name": "Chronurgy Magic",
        "level": 2,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|wizard",
            "entry_type": "class",
            "title": "Wizard",
            "slug": wizard.slug,
            "source_id": "PHB",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|egw|chronurgy-magic",
            "entry_type": "subclass",
            "title": "Chronurgy Magic",
            "slug": "stale-egw-subclass-chronurgy-magic",
            "source_id": "EGW",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|phb|human",
        "entry_type": "race",
        "title": "Human",
        "slug": human.slug,
        "source_id": "PHB",
    }
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|sage",
        "entry_type": "background",
        "title": "Sage",
        "slug": sage.slug,
        "source_id": "PHB",
    }
    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_subclass"].slug == egw_chronurgy.slug
    assert readiness["selected_subclass"].source_id == "EGW"
    assert readiness["reasons"] == []

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.profile["subclass_ref"]["slug"] == egw_chronurgy.slug
    assert normalized.profile["subclass_ref"]["source_id"] == "EGW"
def test_imported_dmg_subclass_with_stale_source_locked_ref_auto_recovers_to_dmg_entry():
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
    phb_death_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-death-domain",
        "Death Domain",
        source_id="PHB",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
    )
    dmg_death_domain = _systems_entry(
        "subclass",
        "dmg-subclass-cleric-death-domain",
        "Death Domain",
        source_id="DMG",
        metadata={"class_name": "Cleric", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human", source_id="PHB")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte", source_id="PHB")
    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "subclass": [phb_death_domain, dmg_death_domain],
            "race": [human],
            "background": [acolyte],
            "spell": [],
        },
        class_progression=[{"level": 1, "feature_rows": [{"label": "Divine Domain"}]}],
        enabled_source_ids=["PHB", "DMG"],
    )
    definition = _minimal_imported_character_definition("dmg-cleric", "DMG Cleric")
    definition.profile["class_level_text"] = "Cleric 1"
    definition.profile["classes"][0] = {
        "class_name": "Cleric",
        "subclass_name": "Death Domain",
        "level": 1,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|cleric",
            "entry_type": "class",
            "title": "Cleric",
            "slug": cleric.slug,
            "source_id": "PHB",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|dmg|death-domain",
            "entry_type": "subclass",
            "title": "Death Domain",
            "slug": "stale-dmg-subclass-death-domain",
            "source_id": "DMG",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = {
        "entry_key": "dnd-5e|race|phb|human",
        "entry_type": "race",
        "title": "Human",
        "slug": human.slug,
        "source_id": "PHB",
    }
    definition.profile["background"] = "Acolyte"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|acolyte",
        "entry_type": "background",
        "title": "Acolyte",
        "slug": acolyte.slug,
        "source_id": "PHB",
    }
    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "ready"
    assert readiness["selected_subclass"].slug == dmg_death_domain.slug
    assert readiness["selected_subclass"].source_id == "DMG"
    assert readiness["reasons"] == []

    normalized = normalize_definition_to_native_model(
        definition,
        systems_service=systems_service,
    )

    assert normalized.profile["subclass_ref"]["slug"] == dmg_death_domain.slug
    assert normalized.profile["subclass_ref"]["source_id"] == "DMG"
def test_imported_progression_repair_can_restore_refs_and_add_prior_feature_links():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "subclass_title": "Martial Archetype"},
    )
    champion = _systems_entry(
        "subclass",
        "phb-subclass-champion",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    lucky = _systems_entry("feat", "phb-feat-lucky", "Lucky")
    archery = _systems_entry(
        "optionalfeature",
        "phb-optionalfeature-archery",
        "Archery",
        metadata={"feature_type": ["Fighting Style"]},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "subclass": [champion],
            "race": [human],
            "background": [acolyte],
            "feat": [lucky],
            "optionalfeature": [archery],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Martial Archetype"}]}],
    )
    definition = _minimal_imported_character_definition()
    definition.profile.pop("class_ref", None)
    definition.profile.pop("subclass_ref", None)
    definition.profile["classes"][0].pop("systems_ref", None)
    definition.profile["classes"][0].pop("subclass_ref", None)
    definition.profile.pop("species_ref", None)
    definition.profile.pop("background_ref", None)
    definition.profile["class_level_text"] = "Fighter 4"
    definition.profile["classes"][0]["level"] = 4
    import_metadata = CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=definition.character_slug,
        source_path="imports://imported-hero.md",
        imported_at_utc="2026-03-31T00:00:00Z",
        parser_version="fixture",
        import_status="clean",
        warnings=[],
    )

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )
    assert repair_context["readiness"]["status"] == "ready"
    repaired_definition, repaired_import = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        {
            "repair_class_slug": f"systems:{fighter.slug}",
            "repair_subclass_slug": f"systems:{champion.slug}",
            "repair_species_slug": f"systems:{human.slug}",
            "repair_background_slug": f"systems:{acolyte.slug}",
            "repair_feat_1": f"systems:{lucky.slug}",
            "repair_optionalfeature_1": archery.slug,
        },
    )
    native_equivalent = _minimal_character_definition("native-fighter-hero", "Native Fighter Hero")
    native_equivalent.profile["class_level_text"] = "Fighter 4"
    native_equivalent.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Fighter",
        "subclass_name": "Champion",
        "level": 4,
        "systems_ref": _systems_ref(fighter),
        "subclass_ref": _systems_ref(champion),
    }
    native_equivalent.profile["class_ref"] = _systems_ref(fighter)
    native_equivalent.profile["subclass_ref"] = _systems_ref(champion)
    native_equivalent.profile["species"] = "Human"
    native_equivalent.profile["species_ref"] = _systems_ref(human)
    native_equivalent.profile["background"] = "Acolyte"
    native_equivalent.profile["background_ref"] = _systems_ref(acolyte)
    native_equivalent.features = [
        {
            "id": "native-lucky",
            "name": "Lucky",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "systems_ref": _systems_ref(lucky),
        },
        {
            "id": "native-archery",
            "name": "Archery",
            "category": "optional_feature",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "systems_ref": _systems_ref(archery),
        },
    ]

    repaired_feature_names = {feature["name"] for feature in repaired_definition.features}
    repaired_features_by_name = {feature["name"]: feature for feature in repaired_definition.features}
    repaired_normalized = normalize_definition_to_native_model(
        repaired_definition,
        systems_service=systems_service,
    )
    native_normalized = normalize_definition_to_native_model(
        native_equivalent,
        systems_service=systems_service,
    )

    def comparable_progression_slice(definition: CharacterDefinition) -> dict[str, object]:
        class_row = dict((definition.profile.get("classes") or [])[0])
        return {
            "class_level_text": definition.profile["class_level_text"],
            "class_slug": str(dict(definition.profile.get("class_ref") or {}).get("slug") or "").strip(),
            "subclass_slug": str(dict(definition.profile.get("subclass_ref") or {}).get("slug") or "").strip(),
            "species_slug": str(dict(definition.profile.get("species_ref") or {}).get("slug") or "").strip(),
            "background_slug": str(dict(definition.profile.get("background_ref") or {}).get("slug") or "").strip(),
            "class_row": {
                "class_slug": str(dict(class_row.get("systems_ref") or {}).get("slug") or "").strip(),
                "subclass_slug": str(dict(class_row.get("subclass_ref") or {}).get("slug") or "").strip(),
                "level": class_row.get("level"),
            },
            "feature_slugs": sorted(
                str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
                for feature in list(definition.features or [])
                if str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
            ),
        }

    assert repaired_definition.source["source_type"] == "markdown_character_sheet"
    assert repaired_definition.profile["class_ref"]["slug"] == fighter.slug
    assert repaired_definition.profile["subclass_ref"]["slug"] == champion.slug
    assert repaired_definition.profile["species_ref"]["slug"] == human.slug
    assert repaired_definition.profile["background_ref"]["slug"] == acolyte.slug
    assert "Lucky" in repaired_feature_names
    assert "Archery" in repaired_feature_names
    assert repaired_features_by_name["Lucky"]["source_kind"] == NATIVE_PROGRESSION_FEATURE_SOURCE_KIND
    assert repaired_features_by_name["Archery"]["source_kind"] == NATIVE_PROGRESSION_FEATURE_SOURCE_KIND
    assert repaired_definition.source["native_progression"]["baseline_repaired_at"]
    assert repaired_import.source_path == "imports://imported-hero.md"
    assert comparable_progression_slice(repaired_normalized) == comparable_progression_slice(native_normalized)
def test_imported_spell_baseline_with_blank_marks_is_repairable():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "subclass_title": "Arcane Tradition",
            "spellcasting_ability": "int",
            "spells_known_progression_fixed": [6],
            "cantrip_progression": [3],
            "slot_progression": [[{"level": 1, "max_slots": 2}]],
        },
    )
    evocation = _systems_entry(
        "subclass",
        "phb-subclass-evocation",
        "School of Evocation",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "subclass": [evocation],
            "race": [human],
            "background": [sage],
        },
        class_progression=[{"level": 2, "feature_rows": [{"label": "Arcane Tradition"}]}],
    )
    definition = _minimal_imported_character_definition("wizard-import", "Wizard Import")
    definition.profile["class_level_text"] = "Wizard 3"
    definition.profile["classes"][0] = {
        "class_name": "Wizard",
        "subclass_name": "School of Evocation",
        "level": 3,
        "systems_ref": {
            "entry_key": "dnd-5e|class|phb|wizard",
            "entry_type": "class",
            "title": "Wizard",
            "slug": "phb-class-wizard",
            "source_id": "PHB",
        },
        "subclass_ref": {
            "entry_key": "dnd-5e|subclass|phb|school-of-evocation",
            "entry_type": "subclass",
            "title": "School of Evocation",
            "slug": "phb-subclass-evocation",
            "source_id": "PHB",
        },
    }
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    definition.profile["subclass_ref"] = dict(definition.profile["classes"][0]["subclass_ref"])
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = {
        "entry_key": "dnd-5e|background|phb|sage",
        "entry_type": "background",
        "title": "Sage",
        "slug": "phb-background-sage",
        "source_id": "PHB",
    }
    definition.spellcasting["spells"] = [{"name": "Magic Missile", "mark": ""}]

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert readiness["status"] == "repairable"
    assert repair_context["spell_rows"]
def test_imported_progression_repair_ignores_item_granted_source_row_spells():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "subclass_title": "Arcane Tradition",
            "spellcasting_ability": "int",
            "spells_known_progression_fixed": [6],
            "cantrip_progression": [3],
            "slot_progression": [[{"level": 1, "max_slots": 2}]],
        },
    )
    evocation = _systems_entry(
        "subclass",
        "phb-subclass-evocation",
        "School of Evocation",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    gift_of_alacrity = _systems_entry(
        "spell",
        "egw-spell-gift-of-alacrity",
        "Gift of Alacrity",
        source_id="EGW",
        metadata={"level": 1},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "subclass": [evocation],
            "race": [human],
            "background": [sage],
            "spell": [gift_of_alacrity],
        },
        class_progression=[{"level": 2, "feature_rows": [{"label": "Arcane Tradition"}]}],
        enabled_source_ids=["PHB", "EGW"],
    )
    definition = _minimal_imported_character_definition("olin-itador", "Olin Itador")
    definition.profile["class_level_text"] = "Wizard 3"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Wizard",
        "subclass_name": "School of Evocation",
        "level": 3,
        "systems_ref": _systems_ref(wizard),
        "subclass_ref": _systems_ref(evocation),
    }
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.profile["subclass_ref"] = _systems_ref(evocation)
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = _systems_ref(sage)
    definition.spellcasting["spells"] = [
        {
            "id": "gift-of-alacrity-hourglass",
            "name": "Gift of Alacrity",
            "mark": "",
            "systems_ref": _systems_ref(gift_of_alacrity),
            "spell_source_row_id": "spell-source:item:hourglass-pendant",
            "spell_source_row_kind": "item",
            "spell_source_row_title": "Hourglass Pendant",
            "spell_source_ability_key": "int",
            "grant_source_label": "Hourglass Pendant",
            "spell_access_type": "free_cast",
            "spell_access_uses": 1,
            "spell_access_reset_on": "long_rest",
        }
    ]

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert readiness["status"] == "ready"
    assert repair_context["spell_rows"] == []
def test_imported_progression_repair_restores_armorer_always_prepared_spells():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
        },
    )
    armorer = _systems_entry(
        "subclass",
        "tce-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="TCE",
        metadata={
            "class_name": "Artificer",
            "class_source": "TCE",
        },
    )
    armorer_spells = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-armorer-spells",
        "Armorer Spells",
        source_id="TCE",
        metadata={
            "level": 3,
            "class_name": "Artificer",
            "class_source": "TCE",
            "subclass_name": "Armorer",
        },
        body={
            "entries": [
                "You always have certain spells prepared after you reach particular levels in this class, as shown in the Armorer Spells table.",
                "These spells count as artificer spells for you, but they don't count against the number of artificer spells you prepare.",
                {
                    "type": "table",
                    "caption": "Armorer Spells",
                    "colLabels": ["Artificer Level", "Spells"],
                    "rows": [
                        ["3rd", "{@spell magic missile}, {@spell thunderwave}"],
                        ["5th", "{@spell mirror image}, {@spell shatter}"],
                    ],
                },
            ]
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    fire_bolt = _systems_entry("spell", "phb-spell-fire-bolt", "Fire Bolt", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    magic_missile = _systems_entry("spell", "phb-spell-magic-missile", "Magic Missile", metadata={"level": 1})
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"level": 1})
    mirror_image = _systems_entry("spell", "phb-spell-mirror-image", "Mirror Image", metadata={"level": 2})
    shatter = _systems_entry("spell", "phb-spell-shatter", "Shatter", metadata={"level": 2})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [armorer],
            "race": [human],
            "background": [sage],
            "spell": [message, fire_bolt, magic_missile, thunderwave, mirror_image, shatter, cure_wounds],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Artificer Specialist"}]}],
        subclass_progression=[{"level": 3, "feature_rows": [{"label": "Armorer Spells", "entry": armorer_spells}]}],
    )
    definition = _minimal_imported_character_definition("armorer-import", "Armorer Import")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Artificer",
        "subclass_name": "Armorer",
        "level": 5,
        "systems_ref": _systems_ref(artificer),
        "subclass_ref": _systems_ref(armorer),
    }
    definition.profile["class_ref"] = _systems_ref(artificer)
    definition.profile["subclass_ref"] = _systems_ref(armorer)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = _systems_ref(human)
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = _systems_ref(sage)
    definition.stats["ability_scores"]["int"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.spellcasting = {
        "spellcasting_class": "Artificer",
        "spellcasting_ability": "Intelligence",
        "spells": [
            {"name": "Message", "mark": "", "systems_ref": _systems_ref(message)},
            {"name": "Fire Bolt", "mark": "", "systems_ref": _systems_ref(fire_bolt)},
            {"name": "Magic Missile", "mark": "", "systems_ref": _systems_ref(magic_missile)},
            {"name": "Thunderwave", "mark": "", "systems_ref": _systems_ref(thunderwave)},
            {"name": "Mirror Image", "mark": "", "systems_ref": _systems_ref(mirror_image)},
            {"name": "Shatter", "mark": "", "systems_ref": _systems_ref(shatter)},
            {"name": "Cure Wounds", "mark": "", "systems_ref": _systems_ref(cure_wounds)},
        ],
    }
    import_metadata = _minimal_import_metadata(definition.character_slug)
    import_metadata.source_path = "imports://armorer-import.md"
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )
    repair_spell_names = {str(row.get("name") or "").strip() for row in repair_context["spell_rows"]}

    assert repair_context["readiness"]["status"] == "repairable"
    assert repair_spell_names == {"Message", "Fire Bolt", "Cure Wounds"}

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        _repair_form_values_for_spell_rows(
            repair_context,
            cantrip_names={"Message", "Fire Bolt"},
            noncantrip_mark="Known",
        ),
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)
    spells_by_name = {spell["name"]: spell for spell in repaired_definition.spellcasting["spells"]}

    assert repaired_readiness["status"] == "ready"
    for spell_name in ("Magic Missile", "Thunderwave", "Mirror Image", "Shatter"):
        assert spells_by_name[spell_name]["is_always_prepared"] is True
        assert spells_by_name[spell_name]["mark"] == ""
    assert spells_by_name["Cure Wounds"].get("is_always_prepared") is not True
    assert spells_by_name["Cure Wounds"]["mark"] == "Known"
def test_imported_progression_repair_prepared_artificer_with_resolved_class_rows_is_ready():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
        },
    )
    armorer = _systems_entry(
        "subclass",
        "tce-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="TCE",
        metadata={
            "class_name": "Artificer",
            "class_source": "TCE",
        },
    )
    armorer_spells = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-armorer-spells",
        "Armorer Spells",
        source_id="TCE",
        metadata={
            "level": 3,
            "class_name": "Artificer",
            "class_source": "TCE",
            "subclass_name": "Armorer",
        },
        body={
            "entries": [
                "You always have certain spells prepared after you reach particular levels in this class, as shown in the Armorer Spells table.",
                "These spells count as artificer spells for you, but they don't count against the number of artificer spells you prepare.",
                {
                    "type": "table",
                    "caption": "Armorer Spells",
                    "colLabels": ["Artificer Level", "Spells"],
                    "rows": [["5th", "{@spell mirror image}"]],
                },
            ]
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    fire_bolt = _systems_entry("spell", "phb-spell-fire-bolt", "Fire Bolt", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    disguise_self = _systems_entry("spell", "phb-spell-disguise-self", "Disguise Self", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    magic_missile = _systems_entry("spell", "phb-spell-magic-missile", "Magic Missile", metadata={"level": 1})
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [armorer],
            "race": [human],
            "background": [sage],
            "spell": [message, fire_bolt, disguise_self, cure_wounds, magic_missile],
        },
        class_progression=[{"level": 5, "feature_rows": [{"label": "Artificer Specialist"}]}],
        subclass_progression=[
            {"level": 3, "feature_rows": [{"label": "Armorer Spells", "entry": armorer_spells}]},
            {"level": 5, "feature_rows": [{"label": "Armorer Spells", "entry": armorer_spells}]},
        ],
    )
    definition = _minimal_imported_character_definition("artificer-import", "Armorer Import")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Artificer",
        "subclass_name": "Armorer",
        "level": 5,
        "systems_ref": _systems_ref(artificer),
        "subclass_ref": _systems_ref(armorer),
    }
    definition.profile["class_ref"] = _systems_ref(artificer)
    definition.profile["subclass_ref"] = _systems_ref(armorer)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = _systems_ref(human)
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = _systems_ref(sage)
    definition.stats["ability_scores"]["int"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.spellcasting = {
        "spellcasting_class": "Artificer",
        "spellcasting_ability": "Intelligence",
        "spells": [
            {"name": "Message", "mark": "Cantrip", "class_row_id": "class-row-1", "systems_ref": _systems_ref(message)},
            {"name": "Fire Bolt", "mark": "Cantrip", "class_row_id": "class-row-1", "systems_ref": _systems_ref(fire_bolt)},
            {"name": "Disguise Self", "mark": "Prepared", "class_row_id": "class-row-1", "systems_ref": _systems_ref(disguise_self)},
            {"name": "Cure Wounds", "mark": "", "class_row_id": "class-row-1", "systems_ref": _systems_ref(cure_wounds)},
            {"name": "Magic Missile", "mark": "", "class_row_id": "class-row-1", "is_always_prepared": True, "systems_ref": _systems_ref(magic_missile)},
        ],
    }

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert readiness["status"] == "ready"
    assert repair_context["spell_rows"] == []
def test_imported_progression_repair_still_flags_blank_cantrips_on_prepared_casters():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
        },
    )
    armorer = _systems_entry(
        "subclass",
        "tce-subclass-armorer-artificer-tce",
        "Armorer",
        source_id="TCE",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    fire_bolt = _systems_entry(
        "spell",
        "phb-spell-fire-bolt",
        "Fire Bolt",
        metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [armorer],
            "race": [human],
            "background": [sage],
            "spell": [fire_bolt],
        },
        class_progression=[],
    )
    definition = _minimal_imported_character_definition("artificer-import", "Armorer Import")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Artificer",
        "subclass_name": "Armorer",
        "level": 5,
        "systems_ref": _systems_ref(artificer),
        "subclass_ref": _systems_ref(armorer),
    }
    definition.profile["class_ref"] = _systems_ref(artificer)
    definition.profile["subclass_ref"] = _systems_ref(armorer)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = _systems_ref(human)
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = _systems_ref(sage)
    definition.spellcasting = {
        "spellcasting_class": "Artificer",
        "spellcasting_ability": "Intelligence",
        "spells": [
            {"name": "Fire Bolt", "mark": "", "class_row_id": "class-row-1", "systems_ref": _systems_ref(fire_bolt)},
        ],
    }

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "repairable"
    assert [row["name"] for row in readiness["spell_repair_rows"]] == ["Fire Bolt"]
def test_imported_progression_repair_restores_grave_domain_always_prepared_spells():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Divine Domain",
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
    grave_domain_spells = _systems_entry(
        "subclassfeature",
        "xge-subclassfeature-grave-domain-spells",
        "Grave Domain Spells",
        source_id="XGE",
        metadata={
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
    human = _systems_entry("race", "phb-race-human", "Human")
    acolyte = _systems_entry("background", "phb-background-acolyte", "Acolyte")
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"level": 0, "class_lists": {"PHB": ["Cleric"]}})
    guidance = _systems_entry("spell", "phb-spell-guidance", "Guidance", metadata={"level": 0, "class_lists": {"PHB": ["Cleric"]}})
    bane = _systems_entry("spell", "phb-spell-bane", "Bane", metadata={"level": 1, "class_lists": {"PHB": ["Cleric"]}})
    false_life = _systems_entry("spell", "phb-spell-false-life", "False Life", metadata={"level": 1})
    gentle_repose = _systems_entry("spell", "phb-spell-gentle-repose", "Gentle Repose", metadata={"level": 2, "class_lists": {"PHB": ["Cleric"]}})
    ray_of_enfeeblement = _systems_entry("spell", "phb-spell-ray-of-enfeeblement", "Ray of Enfeeblement", metadata={"level": 2})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"PHB": ["Cleric"]}})
    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "subclass": [grave_domain],
            "race": [human],
            "background": [acolyte],
            "spell": [sacred_flame, guidance, bane, false_life, gentle_repose, ray_of_enfeeblement, cure_wounds],
        },
        class_progression=[{"level": 1, "feature_rows": [{"label": "Divine Domain", "entry": divine_domain}]}],
        subclass_progression=[{"level": 1, "feature_rows": [{"label": "Grave Domain Spells", "entry": grave_domain_spells}]}],
    )
    definition = _minimal_imported_character_definition("grave-import", "Grave Import")
    definition.profile["class_level_text"] = "Cleric 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Cleric",
        "subclass_name": "Grave Domain",
        "level": 5,
        "systems_ref": _systems_ref(cleric),
        "subclass_ref": _systems_ref(grave_domain),
    }
    definition.profile["class_ref"] = _systems_ref(cleric)
    definition.profile["subclass_ref"] = _systems_ref(grave_domain)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = _systems_ref(human)
    definition.profile["background"] = "Acolyte"
    definition.profile["background_ref"] = _systems_ref(acolyte)
    definition.stats["ability_scores"]["wis"] = {"score": 16, "modifier": 3, "save_bonus": 5}
    definition.spellcasting = {
        "spellcasting_class": "Cleric",
        "spellcasting_ability": "Wisdom",
        "spells": [
            {"name": "Sacred Flame", "mark": "", "systems_ref": _systems_ref(sacred_flame)},
            {"name": "Guidance", "mark": "", "systems_ref": _systems_ref(guidance)},
            {"name": "Bane", "mark": "", "systems_ref": _systems_ref(bane)},
            {"name": "False Life", "mark": "", "systems_ref": _systems_ref(false_life)},
            {"name": "Gentle Repose", "mark": "", "systems_ref": _systems_ref(gentle_repose)},
            {"name": "Ray of Enfeeblement", "mark": "", "systems_ref": _systems_ref(ray_of_enfeeblement)},
            {"name": "Cure Wounds", "mark": "", "systems_ref": _systems_ref(cure_wounds)},
        ],
    }
    import_metadata = _minimal_import_metadata(definition.character_slug)
    import_metadata.source_path = "imports://grave-import.md"
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )
    repair_spell_names = {str(row.get("name") or "").strip() for row in repair_context["spell_rows"]}

    assert repair_context["readiness"]["status"] == "repairable"
    assert repair_spell_names == {"Sacred Flame", "Guidance", "Cure Wounds"}

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        _repair_form_values_for_spell_rows(
            repair_context,
            cantrip_names={"Sacred Flame", "Guidance"},
            noncantrip_mark="Known",
        ),
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)
    spells_by_name = {spell["name"]: spell for spell in repaired_definition.spellcasting["spells"]}

    assert repaired_readiness["status"] == "ready"
    for spell_name in ("Bane", "False Life", "Gentle Repose", "Ray of Enfeeblement"):
        assert spells_by_name[spell_name]["is_always_prepared"] is True
        assert spells_by_name[spell_name]["mark"] == ""
    assert spells_by_name["Cure Wounds"].get("is_always_prepared") is not True
    assert spells_by_name["Cure Wounds"]["mark"] == "Known"
def test_imported_progression_repair_restores_spell_support_always_prepared_grants():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
            "subclass_title": "Divine Domain",
        },
    )
    knowledge_domain = _systems_entry(
        "subclass",
        "phb-subclass-cleric-knowledge-domain",
        "Knowledge Domain",
        metadata={
            "class_name": "Cleric",
            "class_source": "PHB",
        },
    )
    knowledge_domain_spells = _systems_entry(
        "subclassfeature",
        "phb-subclassfeature-knowledge-domain-spells",
        "Knowledge Domain Spells",
        metadata={
            "class_name": "Cleric",
            "class_source": "PHB",
            "subclass_name": "Knowledge Domain",
            "spell_support": [
                {
                    "grants": {
                        "1": [
                            {"spell": "Command", "always_prepared": True},
                            {"spell": "Identify", "always_prepared": True},
                        ],
                        "3": [
                            {"spell": "Augury", "always_prepared": True},
                            {"spell": "Suggestion", "always_prepared": True},
                        ],
                    }
                }
            ],
        },
    )
    human = _systems_entry("race", "phb-race-human", "Human")
    sage = _systems_entry("background", "phb-background-sage", "Sage")
    sacred_flame = _systems_entry("spell", "phb-spell-sacred-flame", "Sacred Flame", metadata={"level": 0, "class_lists": {"PHB": ["Cleric"]}})
    guidance = _systems_entry("spell", "phb-spell-guidance", "Guidance", metadata={"level": 0, "class_lists": {"PHB": ["Cleric"]}})
    command = _systems_entry("spell", "phb-spell-command", "Command", metadata={"level": 1, "class_lists": {"PHB": ["Cleric"]}})
    identify = _systems_entry("spell", "phb-spell-identify", "Identify", metadata={"level": 1})
    augury = _systems_entry("spell", "phb-spell-augury", "Augury", metadata={"level": 2, "class_lists": {"PHB": ["Cleric"]}})
    suggestion = _systems_entry("spell", "phb-spell-suggestion", "Suggestion", metadata={"level": 2})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"PHB": ["Cleric"]}})
    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "subclass": [knowledge_domain],
            "race": [human],
            "background": [sage],
            "spell": [sacred_flame, guidance, command, identify, augury, suggestion, cure_wounds],
        },
        class_progression=[{"level": 1, "feature_rows": [{"label": "Divine Domain"}]}],
        subclass_progression=[{"level": 1, "feature_rows": [{"label": "Knowledge Domain Spells", "entry": knowledge_domain_spells}]}],
    )
    definition = _minimal_imported_character_definition("knowledge-import", "Knowledge Import")
    definition.profile["class_level_text"] = "Cleric 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Cleric",
        "subclass_name": "Knowledge Domain",
        "level": 5,
        "systems_ref": _systems_ref(cleric),
        "subclass_ref": _systems_ref(knowledge_domain),
    }
    definition.profile["class_ref"] = _systems_ref(cleric)
    definition.profile["subclass_ref"] = _systems_ref(knowledge_domain)
    definition.profile["species"] = "Human"
    definition.profile["species_ref"] = _systems_ref(human)
    definition.profile["background"] = "Sage"
    definition.profile["background_ref"] = _systems_ref(sage)
    definition.stats["ability_scores"]["wis"] = {"score": 16, "modifier": 3, "save_bonus": 5}
    definition.spellcasting = {
        "spellcasting_class": "Cleric",
        "spellcasting_ability": "Wisdom",
        "spells": [
            {"name": "Sacred Flame", "mark": "", "systems_ref": _systems_ref(sacred_flame)},
            {"name": "Guidance", "mark": "", "systems_ref": _systems_ref(guidance)},
            {"name": "Command", "mark": "", "systems_ref": _systems_ref(command)},
            {"name": "Identify", "mark": "", "systems_ref": _systems_ref(identify)},
            {"name": "Augury", "mark": "", "systems_ref": _systems_ref(augury)},
            {"name": "Suggestion", "mark": "", "systems_ref": _systems_ref(suggestion)},
            {"name": "Cure Wounds", "mark": "", "systems_ref": _systems_ref(cure_wounds)},
        ],
    }
    import_metadata = _minimal_import_metadata(definition.character_slug)
    import_metadata.source_path = "imports://knowledge-import.md"
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert repair_context["readiness"]["status"] == "repairable"

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        _repair_form_values_for_spell_rows(
            repair_context,
            cantrip_names={"Sacred Flame", "Guidance"},
            noncantrip_mark="Known",
        ),
    )
    spells_by_name = {spell["name"]: spell for spell in repaired_definition.spellcasting["spells"]}

    for spell_name in ("Command", "Identify", "Augury", "Suggestion"):
        assert spells_by_name[spell_name]["is_always_prepared"] is True
        assert spells_by_name[spell_name]["mark"] == ""
    assert spells_by_name["Cure Wounds"].get("is_always_prepared") is not True
    assert spells_by_name["Cure Wounds"]["mark"] == "Known"
def test_normalize_definition_restores_legacy_always_prepared_flags_from_source_labels():
    cleric = _systems_entry(
        "class",
        "phb-class-cleric",
        "Cleric",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["wis", "cha"],
        },
    )
    bless = _systems_entry("spell", "phb-spell-bless", "Bless", metadata={"level": 1})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1})
    sacred_flame = _systems_entry(
        "spell",
        "phb-spell-sacred-flame",
        "Sacred Flame",
        metadata={"level": 0, "class_lists": {"PHB": ["Cleric"]}},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [cleric],
            "spell": [bless, cure_wounds, sacred_flame],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("arden-march", "Arden March")
    definition.profile["class_level_text"] = "Cleric 5"
    definition.profile["classes"][0]["class_name"] = "Cleric"
    definition.profile["classes"][0]["level"] = 5
    definition.profile["classes"][0]["systems_ref"] = _systems_ref(cleric)
    definition.profile["class_ref"] = _systems_ref(cleric)
    definition.spellcasting = {
        "spellcasting_class": "Cleric",
        "spellcasting_ability": "Wisdom",
        "spells": [
            {
                "name": "Bless",
                "mark": "P",
                "source": "Cleric (Always Prepared)",
                "systems_ref": _systems_ref(bless),
            },
            {
                "name": "Cure Wounds",
                "mark": "Prepared",
                "source": "Cleric",
                "systems_ref": _systems_ref(cure_wounds),
            },
            {
                "name": "Sacred Flame",
                "mark": "O",
                "source": "Cleric",
                "systems_ref": _systems_ref(sacred_flame),
            },
        ],
    }

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}

    assert spells_by_name["Bless"]["is_always_prepared"] is True
    assert spells_by_name["Bless"]["source"] == "Cleric (Always Prepared)"
    assert spells_by_name["Bless"]["mark"] == "Prepared"
    assert spells_by_name["Cure Wounds"].get("is_always_prepared") is not True
    assert spells_by_name["Sacred Flame"]["mark"] == "Cantrip"
def test_normalize_definition_canonicalizes_legacy_wizard_spellbook_marks():
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
        },
    )
    fire_bolt = _systems_entry(
        "spell",
        "phb-spell-fire-bolt",
        "Fire Bolt",
        metadata={"level": 0, "class_lists": {"PHB": ["Wizard"]}},
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
    systems_service = _FakeSystemsService(
        {
            "class": [wizard],
            "spell": [fire_bolt, magic_missile, shield],
        },
        class_progression=[],
    )
    definition = _minimal_character_definition("ember-volt", "Ember Volt")
    definition.profile["class_level_text"] = "Wizard 5"
    definition.profile["classes"][0]["class_name"] = "Wizard"
    definition.profile["classes"][0]["level"] = 5
    definition.profile["classes"][0]["systems_ref"] = _systems_ref(wizard)
    definition.profile["class_ref"] = _systems_ref(wizard)
    definition.spellcasting = {
        "spellcasting_class": "Wizard",
        "spellcasting_ability": "Intelligence",
        "spells": [
            {"name": "Fire Bolt", "mark": "O", "systems_ref": _systems_ref(fire_bolt)},
            {"name": "Magic Missile", "mark": "P + O", "systems_ref": _systems_ref(magic_missile)},
            {"name": "Shield", "mark": "P", "systems_ref": _systems_ref(shield)},
        ],
    }

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}

    assert spells_by_name["Fire Bolt"]["mark"] == "Cantrip"
    assert spells_by_name["Magic Missile"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Shield"]["mark"] == "Prepared + Spellbook"
def test_normalize_definition_restores_body_only_artillerist_always_prepared_spells():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
        },
    )
    artillerist = _systems_entry(
        "subclass",
        "tce-subclass-artillerist-artificer",
        "Artillerist",
        source_id="TCE",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
    )
    artillerist_spells = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-artillerist-spells",
        "Artillerist Spells",
        source_id="TCE",
        metadata={
            "level": 3,
            "class_name": "Artificer",
            "class_source": "TCE",
            "subclass_name": "Artillerist",
        },
        body={
            "entries": [
                "You always have certain spells prepared after you reach particular levels in this class, as shown in the Artillerist Spells table.",
                "These spells count as artificer spells for you, but they don't count against the number of artificer spells you prepare.",
                {
                    "type": "table",
                    "caption": "Artillerist Spells",
                    "colLabels": ["Artificer Level", "Spells"],
                    "rows": [
                        ["3rd", "{@spell shield}, {@spell thunderwave}"],
                        ["5th", "{@spell scorching ray}, {@spell shatter}"],
                    ],
                },
            ]
        },
    )
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"level": 1})
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"level": 1})
    scorching_ray = _systems_entry("spell", "phb-spell-scorching-ray", "Scorching Ray", metadata={"level": 2})
    shatter = _systems_entry("spell", "phb-spell-shatter", "Shatter", metadata={"level": 2})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})

    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "subclass": [artillerist],
            "spell": [shield, thunderwave, scorching_ray, shatter, cure_wounds],
        },
        class_progression=[{"level": 3, "feature_rows": [{"label": "Artificer Specialist"}]}],
        subclass_progression=[{"level": 3, "feature_rows": [{"label": "Artillerist Spells", "entry": artillerist_spells}]}],
    )
    definition = _minimal_character_definition("ember-volt", "Ember Volt")
    definition.profile["class_level_text"] = "Artificer 5"
    definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Artificer",
        "subclass_name": "Artillerist",
        "level": 5,
        "systems_ref": _systems_ref(artificer),
        "subclass_ref": _systems_ref(artillerist),
    }
    definition.profile["class_ref"] = _systems_ref(artificer)
    definition.profile["subclass_ref"] = _systems_ref(artillerist)
    definition.spellcasting = {
        "spellcasting_class": "Artificer",
        "spellcasting_ability": "Intelligence",
        "spells": [
            {"name": "Shield", "mark": "", "systems_ref": _systems_ref(shield)},
            {"name": "Thunderwave", "mark": "", "systems_ref": _systems_ref(thunderwave)},
            {"name": "Scorching Ray", "mark": "", "systems_ref": _systems_ref(scorching_ray)},
            {"name": "Shatter", "mark": "", "systems_ref": _systems_ref(shatter)},
            {"name": "Cure Wounds", "mark": "Prepared", "systems_ref": _systems_ref(cure_wounds)},
        ],
    }

    normalized = normalize_definition_to_native_model(definition, systems_service=systems_service)
    spells_by_name = {spell["name"]: spell for spell in normalized.spellcasting["spells"]}

    for spell_name in ("Shield", "Thunderwave", "Scorching Ray", "Shatter"):
        assert spells_by_name[spell_name]["is_always_prepared"] is True
    assert spells_by_name["Cure Wounds"].get("is_always_prepared") is not True
def test_normalize_definition_to_native_model_derives_barbarian_unarmored_defense_for_imported_character():
    definition = _minimal_imported_character_definition("bryn-coal", "Bryn Coal")
    definition.profile["class_level_text"] = "Barbarian 3"
    definition.profile["classes"] = [
        {
            "class_name": "Barbarian",
            "subclass_name": "",
            "level": 3,
        }
    ]
    definition.profile["class_ref"] = {
        "entry_key": "dnd-5e|class|phb|barbarian",
        "entry_type": "class",
        "title": "Barbarian",
        "slug": "phb-class-barbarian",
        "source_id": "PHB",
    }
    definition.stats["armor_class"] = 10
    definition.stats["ability_scores"]["dex"]["score"] = 14
    definition.stats["ability_scores"]["con"]["score"] = 14
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

    assert normalized.stats["armor_class"] == 16
def test_native_level_up_adds_body_only_artillerist_spells_from_prior_feature_table():
    artificer = _systems_entry(
        "class",
        "tce-class-artificer",
        "Artificer",
        source_id="TCE",
        metadata={
            "hit_die": {"faces": 8},
            "proficiency": ["con", "int"],
            "subclass_title": "Artificer Specialist",
            "starting_proficiencies": {
                "armor": ["light", "medium", "shield"],
                "weapons": ["simple"],
                "tools": ["thieves' tools", "tinker's tools"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "investigation", "medicine"]}}],
            },
        },
    )
    artillerist = _systems_entry(
        "subclass",
        "tce-subclass-artillerist-artificer",
        "Artillerist",
        source_id="TCE",
        metadata={"class_name": "Artificer", "class_source": "TCE"},
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
    artificer_specialist = _systems_entry(
        "classfeature",
        "tce-classfeature-artificer-specialist",
        "Artificer Specialist",
        source_id="TCE",
        metadata={"level": 3},
    )
    artillerist_spells = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-artillerist-spells",
        "Artillerist Spells",
        source_id="TCE",
        metadata={
            "level": 3,
            "class_name": "Artificer",
            "class_source": "TCE",
            "subclass_name": "Artillerist",
        },
        body={
            "entries": [
                "You always have certain spells prepared after you reach particular levels in this class, as shown in the Artillerist Spells table.",
                "These spells count as artificer spells for you, but they don't count against the number of artificer spells you prepare.",
                {
                    "type": "table",
                    "caption": "Artillerist Spells",
                    "colLabels": ["Artificer Level", "Spells"],
                    "rows": [
                        ["3rd", "{@spell shield}, {@spell thunderwave}"],
                        ["5th", "{@spell scorching ray}, {@spell shatter}"],
                    ],
                },
            ]
        },
    )
    arcane_firearm = _systems_entry(
        "subclassfeature",
        "tce-subclassfeature-arcane-firearm",
        "Arcane Firearm",
        source_id="TCE",
        metadata={
            "level": 5,
            "class_name": "Artificer",
            "class_source": "TCE",
            "subclass_name": "Artillerist",
        },
    )
    message = _systems_entry("spell", "phb-spell-message", "Message", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    fire_bolt = _systems_entry("spell", "phb-spell-fire-bolt", "Fire Bolt", metadata={"level": 0, "class_lists": {"TCE": ["Artificer"]}})
    absorb_elements = _systems_entry("spell", "xge-spell-absorb-elements", "Absorb Elements", source_id="XGE", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    aid = _systems_entry("spell", "phb-spell-aid", "Aid", metadata={"level": 2, "class_lists": {"TCE": ["Artificer"]}})
    cure_wounds = _systems_entry("spell", "phb-spell-cure-wounds", "Cure Wounds", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    faerie_fire = _systems_entry("spell", "phb-spell-faerie-fire", "Faerie Fire", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    feather_fall = _systems_entry("spell", "phb-spell-feather-fall", "Feather Fall", metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}})
    shield = _systems_entry("spell", "phb-spell-shield", "Shield", metadata={"level": 1})
    thunderwave = _systems_entry("spell", "phb-spell-thunderwave", "Thunderwave", metadata={"level": 1})
    scorching_ray = _systems_entry("spell", "phb-spell-scorching-ray", "Scorching Ray", metadata={"level": 2})
    shatter = _systems_entry("spell", "phb-spell-shatter", "Shatter", metadata={"level": 2, "class_lists": {"TCE": ["Artificer"]}})

    systems_service = _FakeSystemsService(
        {
            "class": [artificer],
            "race": [human],
            "background": [sage],
            "feat": [],
            "subclass": [artillerist],
            "item": [],
            "spell": [
                message,
                fire_bolt,
                absorb_elements,
                aid,
                cure_wounds,
                faerie_fire,
                feather_fall,
                shield,
                thunderwave,
                scorching_ray,
                shatter,
            ],
        },
        class_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Artificer Specialist", "entry": artificer_specialist, "embedded_card": {"option_groups": []}},
                ],
            }
        ],
        subclass_progression=[
            {
                "level": 3,
                "level_label": "Level 3",
                "feature_rows": [
                    {"label": "Artillerist Spells", "entry": artillerist_spells, "embedded_card": {"option_groups": []}},
                ],
            },
            {
                "level": 5,
                "level_label": "Level 5",
                "feature_rows": [
                    {"label": "Arcane Firearm", "entry": arcane_firearm, "embedded_card": {"option_groups": []}},
                ],
            },
        ],
    )

    current_definition = _minimal_character_definition("ember-volt", "Ember Volt")
    current_definition.profile["class_level_text"] = "Artificer 4"
    current_definition.profile["classes"][0] = {
        "row_id": "class-row-1",
        "class_name": "Artificer",
        "subclass_name": "Artillerist",
        "level": 4,
        "systems_ref": _systems_ref(artificer),
        "subclass_ref": _systems_ref(artillerist),
    }
    current_definition.profile["class_ref"] = _systems_ref(artificer)
    current_definition.profile["subclass_ref"] = _systems_ref(artillerist)
    current_definition.profile["species"] = "Human"
    current_definition.profile["species_ref"] = _systems_ref(human)
    current_definition.profile["background"] = "Sage"
    current_definition.profile["background_ref"] = _systems_ref(sage)
    current_definition.stats["max_hp"] = 31
    current_definition.stats["proficiency_bonus"] = 2
    current_definition.stats["ability_scores"] = {
        "str": {"score": 10, "modifier": 0, "save_bonus": 0},
        "dex": {"score": 12, "modifier": 1, "save_bonus": 1},
        "con": {"score": 14, "modifier": 2, "save_bonus": 4},
        "int": {"score": 16, "modifier": 3, "save_bonus": 5},
        "wis": {"score": 11, "modifier": 0, "save_bonus": 0},
        "cha": {"score": 8, "modifier": -1, "save_bonus": -1},
    }
    current_definition.spellcasting = {
        "spellcasting_class": "Artificer",
        "spellcasting_ability": "Intelligence",
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "slot_progression": [{"level": 1, "max_slots": 3}],
        "spells": [
            {"name": "Message", "mark": "Cantrip", "systems_ref": _systems_ref(message)},
            {"name": "Fire Bolt", "mark": "Cantrip", "systems_ref": _systems_ref(fire_bolt)},
            {"name": "Absorb Elements", "mark": "Prepared", "systems_ref": _systems_ref(absorb_elements)},
            {"name": "Aid", "mark": "Prepared", "systems_ref": _systems_ref(aid)},
            {"name": "Cure Wounds", "mark": "Prepared", "systems_ref": _systems_ref(cure_wounds)},
            {"name": "Faerie Fire", "mark": "Prepared", "systems_ref": _systems_ref(faerie_fire)},
            {"name": "Feather Fall", "mark": "Prepared", "systems_ref": _systems_ref(feather_fall)},
            {"name": "Shield", "mark": "", "is_always_prepared": True, "systems_ref": _systems_ref(shield)},
            {"name": "Thunderwave", "mark": "", "is_always_prepared": True, "systems_ref": _systems_ref(thunderwave)},
        ],
    }
    current_definition.source["source_path"] = "builder://native-level-4"

    form_values = {"hp_gain": "5"}
    level_up_context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        current_definition,
        form_values,
    )
    leveled_definition, _, _ = build_native_level_up_character_definition(
        "linden-pass",
        current_definition,
        level_up_context,
        form_values,
    )
    spells_by_name = {spell["name"]: spell for spell in leveled_definition.spellcasting["spells"]}

    assert level_up_context["preview"]["new_spells"] == ["Scorching Ray", "Shatter"]
    assert spells_by_name["Scorching Ray"]["is_always_prepared"] is True
    assert spells_by_name["Scorching Ray"]["mark"] == ""
    assert spells_by_name["Shatter"]["is_always_prepared"] is True
    assert spells_by_name["Shatter"]["mark"] == ""
def test_dm_can_see_progression_repair_entry_for_repairable_imported_character(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "repairer"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_imported_character_definition("repairer", "Repairer")
    import_metadata = _minimal_import_metadata("repairer")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {
            "status": "repairable",
            "message": "This imported character needs a quick progression repair before native level-up.",
            "reasons": ["Choose a supported base class link for this character."],
        },
    )

    response = client.get("/campaigns/linden-pass/characters/repairer")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/repairer/progression-repair" in html
    assert "Prepare for level-up" in html
def test_level_up_route_redirects_repairable_imported_character_to_progression_repair(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "repairer"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_imported_character_definition("repairer", "Repairer")
    import_metadata = _minimal_import_metadata("repairer")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {
            "status": "repairable",
            "message": "This imported character needs a quick progression repair before native level-up.",
            "reasons": ["Choose a supported base class link for this character."],
        },
    )

    response = client.get("/campaigns/linden-pass/characters/repairer/level-up", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/repairer/progression-repair")
def test_progression_repair_route_saves_partial_repairs_and_redirects_back_when_more_work_remains(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "repairer"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_imported_character_definition("repairer", "Repairer")
    import_metadata = _minimal_import_metadata("repairer")
    import_metadata.source_path = "imports://repairer.md"
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    readiness_states = iter(
        [
            {
                "status": "repairable",
                "message": "This imported character needs a quick progression repair before native level-up.",
                "reasons": ["Choose a supported base class link for this character."],
            },
            {
                "status": "repairable",
                "message": "This imported character needs a quick progression repair before native level-up.",
                "reasons": ["Confirm the subclass link before leveling up."],
            },
        ]
    )
    monkeypatch.setattr(app_module, "native_level_up_readiness", lambda *args, **kwargs: next(readiness_states))
    monkeypatch.setattr(
        app_module,
        "build_imported_progression_repair_context",
        lambda *args, **kwargs: {
            "values": {},
            "character_name": "Repairer",
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
    repaired_definition = _minimal_imported_character_definition("repairer", "Repairer")
    repaired_definition.source["native_progression"] = {
        "baseline_repaired_at": "2026-03-31T00:00:00Z",
        "history": [{"kind": "repair", "at": "2026-03-31T00:00:00Z", "target_level": 3}],
    }
    repaired_import = _minimal_import_metadata("repairer")
    repaired_import.source_path = "imports://repairer.md"
    repaired_import.import_status = "managed"
    monkeypatch.setattr(
        app_module,
        "apply_imported_progression_repairs",
        lambda *args, **kwargs: (repaired_definition, repaired_import),
    )

    response = client.post(
        "/campaigns/linden-pass/characters/repairer/progression-repair",
        data={"expected_revision": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/repairer/progression-repair")
    definition_payload = yaml.safe_load((character_dir / "definition.yaml").read_text(encoding="utf-8"))
    assert definition_payload["source"]["native_progression"]["history"][-1]["kind"] == "repair"
