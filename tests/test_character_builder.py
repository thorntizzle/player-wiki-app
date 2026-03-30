from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import player_wiki.app as app_module
import yaml
from player_wiki.character_builder import (
    build_native_level_up_character_definition,
    build_native_level_up_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    supports_native_level_up,
)
from player_wiki.character_service import build_initial_state, merge_state_with_definition
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
        del campaign_slug, library_slug, limit
        return [
            entry
            for entry in self._entries_by_type.get(str(entry_type or ""), [])
            if str(entry.source_id or "").strip().upper() == str(source_id or "").strip().upper()
        ]


class _FakeSystemsService:
    def __init__(
        self,
        entries_by_type: dict[str, list[SystemsEntryRecord]],
        *,
        class_progression: list[dict],
        subclass_progression: list[dict] | None = None,
        enabled_source_ids: list[str] | None = None,
    ):
        self.store = _FakeSystemsStore(entries_by_type)
        self._class_progression = list(class_progression)
        self._subclass_progression = list(subclass_progression or [])
        self._enabled_source_ids = {
            str(source_id or "").strip().upper()
            for source_id in (
                enabled_source_ids
                if enabled_source_ids is not None
                else {
                    str(entry.source_id or "").strip().upper()
                    for entries in entries_by_type.values()
                    for entry in entries
                    if str(entry.source_id or "").strip()
                }
            )
            if str(source_id or "").strip()
        }

    def get_campaign_library(self, campaign_slug: str):
        del campaign_slug
        return SimpleNamespace(library_slug="DND-5E")

    def is_entry_enabled_for_campaign(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        del campaign_slug
        return str(entry.source_id or "").strip().upper() in self._enabled_source_ids

    def list_campaign_source_states(self, campaign_slug: str):
        del campaign_slug
        return [
            SimpleNamespace(
                source=SimpleNamespace(source_id=source_id, library_slug="DND-5E"),
                is_enabled=True,
            )
            for source_id in sorted(self._enabled_source_ids)
        ]

    def list_entries_for_campaign_source(
        self,
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        del query
        return self.store.list_entries_for_campaign_source(
            campaign_slug,
            "DND-5E",
            source_id,
            entry_type=entry_type,
            limit=limit,
        )

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
            "classes": [
                {
                    "class_name": "Fighter",
                    "subclass_name": "",
                    "level": 1,
                    "systems_ref": {
                        "entry_key": "dnd-5e|class|phb|fighter",
                        "entry_type": "class",
                        "title": "Fighter",
                        "slug": "phb-class-fighter",
                        "source_id": "PHB",
                    },
                }
            ],
            "class_ref": {
                "entry_key": "dnd-5e|class|phb|fighter",
                "entry_type": "class",
                "title": "Fighter",
                "slug": "phb-class-fighter",
                "source_id": "PHB",
            },
            "species": "Human",
            "species_ref": {
                "entry_key": "dnd-5e|race|phb|human",
                "entry_type": "race",
                "title": "Human",
                "slug": "phb-race-human",
                "source_id": "PHB",
            },
            "background": "Acolyte",
            "background_ref": {
                "entry_key": "dnd-5e|background|phb|acolyte",
                "entry_type": "background",
                "title": "Acolyte",
                "slug": "phb-background-acolyte",
                "source_id": "PHB",
            },
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
            "source_path": "builder://native-level-1",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Level 1 Builder",
            "imported_at": "2026-03-29T00:00:00Z",
            "parse_warnings": [],
        },
    )


def _minimal_import_metadata(character_slug: str = "new-hero") -> CharacterImportMetadata:
    return CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=character_slug,
        source_path="builder://native-level-1",
        imported_at_utc="2026-03-29T00:00:00Z",
        parser_version="2026-03-29.12",
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
        "class_options": [{"slug": "phb-class-fighter", "title": "Fighter", "source_id": "PHB", "label": "Fighter"}],
        "species_options": [{"slug": "phb-race-human", "title": "Human", "source_id": "PHB", "label": "Human"}],
        "background_options": [{"slug": "phb-background-acolyte", "title": "Acolyte", "source_id": "PHB", "label": "Acolyte"}],
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
            "Base classes currently follow the native PHB progression spine, but species, backgrounds, subclasses, feats, spells, and items can come from any enabled Systems source.",
            "Enter level-1 ability scores after any species bonuses. Native feat-driven ability increases are applied automatically.",
            "Native attack rows now cover basic PHB weapons, off-hand attacks, and key level-1 fighting-style adjustments, but a few advanced damage riders still need manual follow-up.",
            "Gold-alternative loadouts, some granted spell choices, spell-granting feats, and a few class-specific spell extras still need manual follow-up.",
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


def _campaign_page_record(
    page_ref: str,
    title: str,
    *,
    section: str,
    subsection: str = "",
    summary: str = "",
):
    return SimpleNamespace(
        page_ref=page_ref,
        page=SimpleNamespace(
            title=title,
            section=section,
            subsection=subsection,
            summary=summary,
        ),
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

    assert [option["slug"] for option in context["class_options"]] == [fighter.slug]
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
        option["value"] == telekinetic.slug and option["label"] == "Telekinetic (TCE)"
        for option in species_feat_field["options"]
    )
    assert definition.profile["species_ref"]["source_id"] == "TCE"
    assert definition.profile["background_ref"]["source_id"] == "XGE"
    assert any(feature["name"] == "Telekinetic" for feature in definition.features)
    assert import_metadata.source_path == "builder://native-level-1"


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

    assert "Handaxe (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert "Handaxe (thrown) (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert "Handaxe (off-hand) (+5, 1d6+3 slashing)" in context["preview"]["attacks"]
    assert attacks_by_name["Handaxe"]["notes"] == ""
    assert attacks_by_name["Handaxe (thrown)"]["category"] == "ranged weapon"
    assert attacks_by_name["Handaxe (thrown)"]["notes"] == "range 20/60."
    assert attacks_by_name["Handaxe (off-hand)"]["damage"] == "1d6+3 slashing"
    assert attacks_by_name["Handaxe (off-hand)"]["notes"] == "range 20/60, Bonus action."


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
    assert spells_by_name["Light"]["mark"] == "Cantrip"
    assert spells_by_name["Magic Missile"]["mark"] == "Prepared + Spellbook"
    assert spells_by_name["Find Familiar"]["mark"] == "Spellbook"
    assert spells_by_name["Detect Magic"]["reference"] == "p. 231"
    assert spells_by_name["Message"]["components"] == "V, S, M (a short piece of copper wire)"
    assert resource_templates_by_id["arcane-recovery"]["max"] == 1
    assert state_resources_by_id["arcane-recovery"]["current"] == 1
    assert import_metadata.parser_version == "2026-03-29.12"


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
    assert spells_by_name["Burning Hands"]["mark"] == "Spellbook + Prepared"


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


def test_character_builder_route_passes_visible_campaign_pages_into_builder(app, client, sign_in, users, monkeypatch):
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
    assert all(not page_ref.startswith("sessions/") for page_ref in captured_page_refs if page_ref)


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


def test_dm_can_see_level_up_entry_for_supported_native_character(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(app_module, "supports_native_level_up", lambda definition: True)

    response = client.get("/campaigns/linden-pass/characters/leveler")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/leveler/level-up" in html
    assert "Level up" in html


def test_dm_can_apply_native_level_up_route(app, client, sign_in, users, get_character, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(app_module, "supports_native_level_up", lambda definition: True)
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: {
            "values": {"hp_gain": "8"},
            "character_name": "Leveler",
            "current_level": 1,
            "next_level": 2,
            "selected_class": SimpleNamespace(title="Fighter"),
            "selected_species": SimpleNamespace(title="Human"),
            "selected_background": SimpleNamespace(title="Acolyte"),
            "selected_subclass": None,
            "subclass_options": [],
            "requires_subclass": False,
            "choice_sections": [],
            "class_progression": [],
            "subclass_progression": [],
            "spell_catalog": {},
            "limitations": [],
            "preview": {
                "class_level_text": "Fighter 2",
                "max_hp": 20,
                "gained_features": ["Action Surge"],
                "spell_slots": [],
                "new_spells": [],
            },
        },
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

    monkeypatch.setattr(app_module, "supports_native_level_up", lambda definition: True)
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: {
            "values": {"hp_gain": "8"},
            "character_name": "Leveler",
            "current_level": 1,
            "next_level": 2,
            "selected_class": SimpleNamespace(title="Fighter"),
            "selected_species": SimpleNamespace(title="Human"),
            "selected_background": SimpleNamespace(title="Acolyte"),
            "selected_subclass": None,
            "subclass_options": [],
            "requires_subclass": False,
            "choice_sections": [],
            "class_progression": [],
            "subclass_progression": [],
            "spell_catalog": {},
            "limitations": [],
            "preview": {
                "class_level_text": "Fighter 2",
                "max_hp": 20,
                "gained_features": ["Action Surge"],
                "spell_slots": [],
                "new_spells": [],
            },
            "state_revision": 1,
        },
    )

    response = client.get("/campaigns/linden-pass/characters/leveler/level-up?_live_preview=1&hp_gain=8")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<!doctype html>" not in html.lower()
    assert "data-live-builder-root" in html
    assert "data-live-builder-form" in html
    assert "data-live-refresh-fallback" in html
