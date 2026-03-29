from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import player_wiki.app as app_module
from player_wiki.character_builder import (
    build_level_one_builder_context,
    build_level_one_character_definition,
)
from player_wiki.character_service import build_initial_state
from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata
from player_wiki.systems_models import SystemsEntryRecord


def _systems_entry(
    entry_type: str,
    slug: str,
    title: str,
    *,
    metadata: dict | None = None,
    body: dict | None = None,
    source_id: str = "PHB",
    source_page: str = "",
) -> SystemsEntryRecord:
    now = datetime.now(timezone.utc)
    return SystemsEntryRecord(
        id=1,
        library_slug="DND-5E",
        source_id=source_id,
        entry_key=f"dnd-5e|{entry_type}|{source_id.lower()}|{slug}",
        entry_type=entry_type,
        slug=slug,
        title=title,
        source_page=source_page,
        source_path="",
        search_text=title.lower(),
        player_safe_default=True,
        dm_heavy=False,
        metadata=dict(metadata or {}),
        body=dict(body or {}),
        rendered_html="",
        created_at=now,
        updated_at=now,
    )


class _FakeSystemsStore:
    def __init__(self, entries_by_type: dict[str, list[SystemsEntryRecord]]):
        self._entries_by_type = entries_by_type

    def list_entries_for_campaign_source(
        self,
        campaign_slug: str,
        library_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        limit=None,
    ) -> list[SystemsEntryRecord]:
        del campaign_slug, library_slug, source_id, limit
        return list(self._entries_by_type.get(str(entry_type or ""), []))


class _FakeSystemsService:
    def __init__(
        self,
        entries_by_type: dict[str, list[SystemsEntryRecord]],
        *,
        class_progression: list[dict],
        subclass_progression: list[dict] | None = None,
    ):
        self.store = _FakeSystemsStore(entries_by_type)
        self._class_progression = list(class_progression)
        self._subclass_progression = list(subclass_progression or [])

    def get_campaign_library(self, campaign_slug: str):
        del campaign_slug
        return SimpleNamespace(library_slug="DND-5E")

    def is_entry_enabled_for_campaign(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        del campaign_slug, entry
        return True

    def build_class_feature_progression_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord | None,
    ) -> list[dict]:
        del campaign_slug, entry
        return list(self._class_progression)

    def build_subclass_feature_progression_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord | None,
    ) -> list[dict]:
        del campaign_slug, entry
        return list(self._subclass_progression)


def _minimal_character_definition(character_slug: str = "new-hero", name: str = "New Hero") -> CharacterDefinition:
    return CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug=character_slug,
        name=name,
        status="active",
        profile={
            "sheet_name": name,
            "display_name": name,
            "class_level_text": "Fighter 1",
            "classes": [],
            "species": "Human",
            "background": "Acolyte",
            "alignment": "Neutral",
            "experience_model": "Milestone",
            "size": "Medium",
            "biography_markdown": "",
            "personality_markdown": "",
        },
        stats={
            "max_hp": 12,
            "armor_class": 10,
            "initiative_bonus": 1,
            "speed": "30 ft.",
            "proficiency_bonus": 2,
            "passive_perception": 12,
            "passive_insight": 11,
            "passive_investigation": 10,
            "ability_scores": {
                "str": {"score": 16, "modifier": 3, "save_bonus": 5},
                "dex": {"score": 12, "modifier": 1, "save_bonus": 1},
                "con": {"score": 14, "modifier": 2, "save_bonus": 4},
                "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                "wis": {"score": 13, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 8, "modifier": -1, "save_bonus": -1},
            },
        },
        skills=[],
        proficiencies={"armor": [], "weapons": [], "tools": [], "languages": ["Common"]},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "spells": [],
        },
        equipment_catalog=[],
        reference_notes={
            "additional_notes_markdown": "",
            "allies_and_organizations_markdown": "",
            "custom_sections": [],
        },
        resource_templates=[],
        source={
            "source_path": "builder://phb-level-1",
            "source_type": "native_character_builder",
            "imported_from": "In-app PHB Level 1 Builder",
            "imported_at": "2026-03-29T00:00:00Z",
            "parse_warnings": [],
        },
    )


def _minimal_import_metadata(character_slug: str = "new-hero") -> CharacterImportMetadata:
    return CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=character_slug,
        source_path="builder://phb-level-1",
        imported_at_utc="2026-03-29T00:00:00Z",
        parser_version="2026-03-29.3",
        import_status="clean",
        warnings=[],
    )


def _builder_context_fixture() -> dict[str, object]:
    return {
        "values": {
            "name": "New Hero",
            "character_slug": "new-hero",
            "alignment": "Neutral",
            "experience_model": "Milestone",
            "str": "16",
            "dex": "12",
            "con": "14",
            "int": "10",
            "wis": "13",
            "cha": "8",
        },
        "class_options": [{"slug": "phb-class-fighter", "title": "Fighter", "source_id": "PHB"}],
        "species_options": [{"slug": "phb-race-human", "title": "Human", "source_id": "PHB"}],
        "background_options": [{"slug": "phb-background-acolyte", "title": "Acolyte", "source_id": "PHB"}],
        "subclass_options": [],
        "selected_class": None,
        "selected_species": None,
        "selected_background": None,
        "selected_subclass": None,
        "requires_subclass": False,
        "choice_sections": [],
        "class_progression": [],
        "subclass_progression": [],
        "limitations": [
            "Enter final level-1 ability scores after any species bonuses.",
            "Basic weapon attack rows are now generated from chosen starting gear, but off-hand attacks and a few feature-based damage adjustments still need manual follow-up.",
            "Gold-alternative loadouts and a few class-specific spell extras still need manual follow-up.",
        ],
        "preview": {
            "class_level_text": "Fighter 1",
            "max_hp": 12,
            "speed": "30 ft.",
            "size": "Medium",
            "proficiency_bonus": 2,
            "saving_throws": ["Strength Save", "Constitution Save"],
            "languages": ["Common"],
            "features": ["Second Wind"],
            "equipment": [],
            "attacks": [],
            "starting_currency": "",
            "spells": [],
            "background": "Acolyte",
            "subclass": "",
        },
    }


def _find_builder_field(builder_context: dict[str, object], field_name: str) -> dict:
    for section in list(builder_context.get("choice_sections") or []):
        for field in list(section.get("fields") or []):
            if field.get("name") == field_name:
                return dict(field)
    raise AssertionError(f"builder field '{field_name}' was not found")


def _field_value_for_label(builder_context: dict[str, object], field_name: str, label_fragment: str) -> str:
    field = _find_builder_field(builder_context, field_name)
    for option in list(field.get("options") or []):
        if str(option.get("label") or "").strip().lower() == label_fragment.strip().lower():
            return str(option.get("value") or "")
    for option in list(field.get("options") or []):
        if label_fragment.lower() in str(option.get("label") or "").lower():
            return str(option.get("value") or "")
    raise AssertionError(f"builder field '{field_name}' did not contain option '{label_fragment}'")


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
    assert import_metadata.source_path == "builder://phb-level-1"


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

    assert "Longsword (+5, 1d8+3 slashing)" in context["preview"]["attacks"]
    assert "Light Crossbow (+5, 1d8+1 piercing)" in context["preview"]["attacks"]
    assert set(attacks_by_name) == {"Longsword", "Light Crossbow"}
    assert attacks_by_name["Longsword"]["category"] == "melee weapon"
    assert attacks_by_name["Longsword"]["damage"] == "1d8+3 slashing"
    assert attacks_by_name["Longsword"]["notes"] == "Versatile (1d10)."
    assert attacks_by_name["Longsword"]["systems_ref"]["slug"] == "phb-item-longsword"
    assert attacks_by_name["Light Crossbow"]["category"] == "ranged weapon"
    assert attacks_by_name["Light Crossbow"]["attack_bonus"] == 5
    assert attacks_by_name["Light Crossbow"]["damage"] == "1d8+1 piercing"
    assert attacks_by_name["Light Crossbow"]["notes"] == "Ammunition, loading, range 80/320."
    assert attacks_by_name["Light Crossbow"]["systems_ref"]["slug"] == "phb-item-light-crossbow"


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

    assert context["preview"]["starting_currency"] == "5 gp"
    assert "Quarterstaff" in context["preview"]["equipment"]
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
    assert spells_by_name["Light"]["mark"] == "Cantrip"
    assert spells_by_name["Magic Missile"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Find Familiar"]["mark"] == "Spellbook"
    assert spells_by_name["Detect Magic"]["reference"] == "p. 231"
    assert spells_by_name["Message"]["components"] == "V, S, M (a short piece of copper wire)"
    assert import_metadata.parser_version == "2026-03-29.3"


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
    assert "PHB Level 1 Builder" in html
    assert "The builder needs PHB Systems entries for classes, species, and backgrounds" in html


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
