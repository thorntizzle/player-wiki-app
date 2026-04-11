from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import player_wiki.app as app_module
import pytest
import yaml
from player_wiki.character_campaign_progression import build_campaign_page_progression_entries
from player_wiki.character_builder import (
    CHARACTER_BUILDER_VERSION,
    _list_campaign_enabled_entries,
    _prepared_spell_count_for_level,
    _recalculate_definition_attacks,
    _resolve_builder_choices,
    apply_imported_progression_repairs,
    build_native_level_up_character_definition,
    build_native_level_up_context,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    native_level_up_readiness,
    normalize_definition_to_native_model,
    supports_native_level_up,
)
from player_wiki.character_adjustments import apply_manual_stat_adjustments
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


def _systems_ref(entry: SystemsEntryRecord) -> dict[str, str]:
    return {
        "entry_key": str(entry.entry_key or "").strip(),
        "entry_type": str(entry.entry_type or "").strip(),
        "title": str(entry.title or "").strip(),
        "slug": str(entry.slug or "").strip(),
        "source_id": str(entry.source_id or "").strip(),
    }


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
        disabled_entry_keys: list[str] | None = None,
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
        self._disabled_entry_keys = {
            str(entry_key or "").strip()
            for entry_key in list(disabled_entry_keys or [])
            if str(entry_key or "").strip()
        }
        self.list_enabled_entries_calls: list[tuple[str, str | None, str, int | None]] = []
        self.list_entries_for_campaign_source_calls = 0
        self.is_entry_enabled_calls = 0

    def get_campaign_library(self, campaign_slug: str):
        del campaign_slug
        return SimpleNamespace(library_slug="DND-5E")

    def is_entry_enabled_for_campaign(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        del campaign_slug
        self.is_entry_enabled_calls += 1
        return (
            str(entry.source_id or "").strip().upper() in self._enabled_source_ids
            and str(entry.entry_key or "").strip() not in self._disabled_entry_keys
        )

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
        self.list_entries_for_campaign_source_calls += 1
        return self.store.list_entries_for_campaign_source(
            campaign_slug,
            "DND-5E",
            source_id,
            entry_type=entry_type,
            limit=limit,
        )

    def list_enabled_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        normalized_query = query.strip().lower()
        self.list_enabled_entries_calls.append((campaign_slug, entry_type, normalized_query, limit))
        entries = [
            entry
            for entry in self.store._entries_by_type.get(str(entry_type or ""), [])
            if str(entry.source_id or "").strip().upper() in self._enabled_source_ids
            and str(entry.entry_key or "").strip() not in self._disabled_entry_keys
            and (
                not normalized_query
                or normalized_query in str(entry.title or "").lower()
                or normalized_query in str(entry.search_text or "").lower()
            )
        ]
        return list(entries if limit is None else entries[:limit])

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
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="clean",
        warnings=[],
    )


def _minimal_imported_character_definition(
    character_slug: str = "imported-hero",
    name: str = "Imported Hero",
    *,
    source_type: str = "markdown_character_sheet",
) -> CharacterDefinition:
    definition = _minimal_character_definition(character_slug, name)
    definition.source = {
        "source_path": f"imports://{character_slug}.md",
        "source_type": source_type,
        "imported_from": f"{name}.md",
        "imported_at": "2026-03-31T00:00:00Z",
        "parse_warnings": [],
    }
    definition.profile["classes"][0]["level"] = 3
    definition.profile["class_level_text"] = "Fighter 3"
    definition.profile["subclass_ref"] = {
        "entry_key": "dnd-5e|subclass|phb|champion",
        "entry_type": "subclass",
        "title": "Champion",
        "slug": "phb-subclass-champion",
        "source_id": "PHB",
    }
    definition.profile["classes"][0]["subclass_name"] = "Champion"
    definition.profile["classes"][0]["subclass_ref"] = dict(definition.profile["subclass_ref"])
    return definition


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
            "Base classes now come from the campaign's enabled Systems sources when their native progression metadata is available, while older PHB fallback data still covers previously imported local classes.",
            "Enter level-1 ability scores after any species bonuses. Native feat-driven ability increases are applied automatically.",
            "Native attack rows now cover basic PHB weapons, off-hand attacks, key level-1 fighting-style adjustments, and the current modeled feat attack variants, but a few advanced riders still need manual follow-up.",
            "Gold-alternative loadouts, campaign-driven spell access, and a few class-specific spell extras still need manual follow-up.",
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
            "resources": [],
            "equipment": [],
            "attacks": [],
            "starting_currency": "",
            "spells": [],
            "background": "Acolyte",
            "subclass": "",
        },
        "field_live_preview": {
            "name": {"live_preview_trigger": "blur", "live_preview_regions": "", "live_preview_debounce_ms": 0},
            "character_slug": {"live_preview_trigger": "blur", "live_preview_regions": "", "live_preview_debounce_ms": 0},
            "alignment": {"live_preview_trigger": "blur", "live_preview_regions": "", "live_preview_debounce_ms": 0},
            "experience_model": {"live_preview_trigger": "blur", "live_preview_regions": "", "live_preview_debounce_ms": 0},
            "class_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-equipment,preview-attacks",
                "live_preview_debounce_ms": 120,
            },
            "subclass_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 120,
            },
            "species_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 120,
            },
            "background_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "choice-sections,preview-summary,preview-spells,preview-equipment,preview-attacks",
                "live_preview_debounce_ms": 120,
            },
            "str": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
            "dex": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
            "con": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
            "int": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
            "wis": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
            "cha": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 350,
            },
        },
        "preview_region_ids": [
            "preview-summary",
            "preview-features",
            "preview-resources",
            "preview-spells",
            "preview-scope",
            "preview-equipment",
            "preview-attacks",
        ],
        "preview_regions_csv": "preview-summary,preview-features,preview-resources,preview-spells,preview-scope,preview-equipment,preview-attacks",
        "live_region_ids": [
            "choice-sections",
            "preview-summary",
            "preview-features",
            "preview-resources",
            "preview-spells",
            "preview-scope",
            "preview-equipment",
            "preview-attacks",
        ],
        "live_regions_csv": "choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-scope,preview-equipment,preview-attacks",
    }


def _level_up_context_fixture() -> dict[str, object]:
    return {
        "values": {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-1",
            "new_class_slug": "",
            "new_subclass_slug": "",
            "hp_gain": "8",
        },
        "character_name": "Leveler",
        "current_level": 1,
        "next_level": 2,
        "campaign_slug": "linden-pass",
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
            "resources": [],
            "attacks": [],
            "spell_slots": [],
            "new_spells": [],
            "class_rows": ["Fighter 2"],
        },
        "selected_class_rows": [],
        "mode_options": [{"value": "advance_existing", "label": "Advance existing class"}],
        "can_add_class": False,
        "current_class_rows": ["Fighter 1"],
        "target_row_options": [{"value": "class-row-1", "label": "Fighter 1"}],
        "target_class_row_id": "class-row-1",
        "row_current_level": 1,
        "row_target_level": 2,
        "new_class_options": [],
        "new_subclass_options": [],
        "multiclass_requirement_text": "",
        "multiclass_requirements_met": True,
        "state_revision": 3,
        "field_live_preview": {
            "advancement_mode": {
                "live_preview_trigger": "change",
                "live_preview_regions": "advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
                "live_preview_debounce_ms": 100,
            },
            "new_class_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
                "live_preview_debounce_ms": 100,
            },
            "new_subclass_slug": {
                "live_preview_trigger": "change",
                "live_preview_regions": "choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
                "live_preview_debounce_ms": 100,
            },
            "target_class_row_id": {
                "live_preview_trigger": "change",
                "live_preview_regions": "advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-spell-slots",
                "live_preview_debounce_ms": 100,
            },
            "hp_gain": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary",
                "live_preview_debounce_ms": 350,
            },
        },
        "preview_region_ids": [
            "preview-summary",
            "preview-features",
            "preview-resources",
            "preview-spells",
            "preview-attacks",
            "preview-scope",
            "preview-spell-slots",
        ],
        "preview_regions_csv": "preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-scope,preview-spell-slots",
        "live_region_ids": [
            "advancement",
            "choice-sections",
            "preview-summary",
            "preview-features",
            "preview-resources",
            "preview-spells",
            "preview-attacks",
            "preview-scope",
            "preview-spell-slots",
        ],
        "live_regions_csv": "advancement,choice-sections,preview-summary,preview-features,preview-resources,preview-spells,preview-attacks,preview-scope,preview-spell-slots",
    }


def _find_builder_field(builder_context: dict[str, object], field_name: str) -> dict:
    for section in list(builder_context.get("choice_sections") or []):
        for field in list(section.get("fields") or []):
            if field.get("name") == field_name:
                return dict(field)
    raise AssertionError(f"builder field '{field_name}' was not found")


def _assert_live_preview_metadata(
    payload: dict[str, object],
    *,
    trigger: str,
    regions: str,
    debounce_ms: int,
) -> None:
    assert payload["live_preview_trigger"] == trigger
    assert payload["live_preview_regions"] == regions
    assert payload["live_preview_debounce_ms"] == debounce_ms


def _field_value_for_label(builder_context: dict[str, object], field_name: str, label_fragment: str) -> str:
    field = _find_builder_field(builder_context, field_name)
    for option in list(field.get("options") or []):
        if str(option.get("label") or "").strip().lower() == label_fragment.strip().lower():
            return str(option.get("value") or "")
    for option in list(field.get("options") or []):
        if label_fragment.lower() in str(option.get("label") or "").lower():
            return str(option.get("value") or "")
    raise AssertionError(f"builder field '{field_name}' did not contain option '{label_fragment}'")


def _option_value_for_label(options: list[dict[str, object]], label_fragment: str) -> str:
    for option in list(options or []):
        if str(option.get("label") or "").strip().lower() == label_fragment.strip().lower():
            return str(option.get("value") or option.get("slug") or "")
    for option in list(options or []):
        if label_fragment.lower() in str(option.get("label") or "").lower():
            return str(option.get("value") or option.get("slug") or "")
    raise AssertionError(f"top-level builder options did not contain '{label_fragment}'")


_SINGLE_TRACKER_FEAT_CASES = [
    pytest.param(
        "Dragon Fear",
        "xge-feat-dragon-fear",
        "dragon-fear",
        "Dragon Fear: 1 / 1 (Short Rest)",
        "special",
        id="dragon-fear",
    ),
    pytest.param(
        "Orcish Fury",
        "xge-feat-orcish-fury",
        "orcish-fury",
        "Orcish Fury: 1 / 1 (Short Rest)",
        "special",
        id="orcish-fury",
    ),
    pytest.param(
        "Second Chance",
        "xge-feat-second-chance",
        "second-chance",
        "Second Chance: 1 / 1 (Short Rest)",
        "reaction",
        id="second-chance",
    ),
]


def _build_single_tracker_feat_level_one_fixture(
    feat_name: str,
    feat_slug: str,
) -> tuple[_FakeSystemsService, dict[str, str]]:
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
    feat_entry = _systems_entry("feat", feat_slug, feat_name, source_id="XGE")
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human],
            "background": [acolyte],
            "feat": [feat_entry],
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
        "name": f"{feat_name} Hero",
        "character_slug": feat_slug.replace("-", "_"),
        "alignment": "Neutral",
        "experience_model": "Milestone",
        "class_slug": fighter.slug,
        "species_slug": variant_human.slug,
        "background_slug": acolyte.slug,
        "class_skill_1": "athletics",
        "class_skill_2": "history",
        "species_feat_1": feat_entry.slug,
        "str": "16",
        "dex": "12",
        "con": "14",
        "int": "10",
        "wis": "13",
        "cha": "8",
    }
    return systems_service, form_values


def _build_single_tracker_feat_level_up_fixture(
    feat_name: str,
    feat_slug: str,
) -> tuple[_FakeSystemsService, CharacterDefinition, dict[str, str]]:
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
    feat_entry = _systems_entry("feat", feat_slug, feat_name, source_id="XGE")

    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [human],
            "background": [acolyte],
            "feat": [feat_entry],
            "subclass": [],
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

    current_definition = _minimal_character_definition(
        feat_slug.replace("-", "_"),
        f"{feat_name} Veteran",
    )
    current_definition.profile["class_level_text"] = "Fighter 7"
    current_definition.profile["classes"][0]["level"] = 7
    current_definition.stats["max_hp"] = 60
    current_definition.proficiencies["weapons"] = ["Simple Weapons", "Martial Weapons"]

    form_values = {
        "hp_gain": "8",
        "levelup_asi_mode_1": "feat",
        "levelup_feat_1": feat_entry.slug,
    }
    return systems_service, current_definition, form_values


def _progression_row(
    label: str,
    *,
    entry: SystemsEntryRecord | None = None,
    option_groups: list[dict] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"label": label}
    if entry is not None:
        payload["entry"] = entry
    if option_groups:
        payload["embedded_card"] = {"option_groups": list(option_groups)}
    return payload


def _set_progressions(
    systems_service: _FakeSystemsService,
    *,
    class_by_slug: dict[str, list[dict]] | None = None,
    subclass_by_slug: dict[str, list[dict]] | None = None,
) -> None:
    class_progressions = dict(class_by_slug or {})
    subclass_progressions = dict(subclass_by_slug or {})

    def _build_class_feature_progression_for_class_entry(campaign_slug: str, entry: SystemsEntryRecord | None) -> list[dict]:
        del campaign_slug
        if entry is None:
            return []
        return list(class_progressions.get(str(entry.slug or ""), []))

    def _build_subclass_feature_progression_for_subclass_entry(
        campaign_slug: str,
        entry: SystemsEntryRecord | None,
    ) -> list[dict]:
        del campaign_slug
        if entry is None:
            return []
        return list(subclass_progressions.get(str(entry.slug or ""), []))

    systems_service.build_class_feature_progression_for_class_entry = _build_class_feature_progression_for_class_entry
    systems_service.build_subclass_feature_progression_for_subclass_entry = _build_subclass_feature_progression_for_subclass_entry


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


def test_imported_character_with_missing_progression_links_is_repairable_even_when_titles_match():
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

    assert readiness["status"] == "repairable"
    assert any("base class link" in reason for reason in readiness["reasons"])
    assert any("species link" in reason for reason in readiness["reasons"])
    assert any("background link" in reason for reason in readiness["reasons"])
    assert any("before leveling up" in reason.lower() and "link" in reason.lower() for reason in readiness["reasons"])


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
        "phb-subclass-eldritch-knight",
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


def test_normalize_definition_to_native_model_supports_single_class_eldritch_knight_spellcasting():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritch-knight",
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
        "phb-subclass-eldritch-knight",
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


def test_normalize_definition_to_native_model_keeps_pact_lane_separate_for_arcane_trickster_and_warlock():
    rogue = _systems_entry(
        "class",
        "phb-class-rogue",
        "Rogue",
        metadata={"hit_die": {"faces": 8}, "proficiency": ["dex", "int"], "subclass_title": "Roguish Archetype"},
    )
    arcane_trickster = _systems_entry(
        "subclass",
        "phb-subclass-arcane-trickster",
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


def test_native_level_up_surfaces_and_applies_eldritch_knight_spell_choices():
    fighter = _systems_entry(
        "class",
        "phb-class-fighter",
        "Fighter",
        metadata={"hit_die": {"faces": 10}, "proficiency": ["str", "con"], "subclass_title": "Martial Archetype"},
    )
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritch-knight",
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


def test_imported_multiclass_repair_is_row_aware_and_unlocks_native_advancement():
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
    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert readiness["status"] == "repairable"
    assert len(repair_context["class_rows"]) == 2
    repaired_definition, repaired_import = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        _minimal_import_metadata(definition.character_slug),
        repair_context,
        {
            **repair_context["values"],
            "repair_class_slug_class-row-1": f"systems:{fighter.slug}",
            "repair_class_slug_class-row-2": f"systems:{rogue.slug}",
        },
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)
    context = build_native_level_up_context(
        systems_service,
        "linden-pass",
        repaired_definition,
        {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-2",
            "hp_gain": "4",
        },
    )
    leveled_definition, _managed_import, _hp_delta = build_native_level_up_character_definition(
        "linden-pass",
        repaired_definition,
        context,
        context["values"],
        current_import_metadata=repaired_import,
    )

    assert repaired_readiness["status"] == "ready"
    assert [row["row_id"] for row in repaired_definition.profile["classes"]] == ["class-row-1", "class-row-2"]
    assert [row["level"] for row in leveled_definition.profile["classes"]] == [1, 2]
    assert any(feature["name"] == "Cunning Action" for feature in leveled_definition.features)


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


def test_imported_tce_artificer_with_stale_source_locked_refs_repairs_to_tce_entries():
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
    import_metadata = CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=definition.character_slug,
        source_path="imports://artificer-repair.md",
        imported_at_utc="2026-04-08T00:00:00Z",
        parser_version="fixture",
        import_status="clean",
        warnings=[],
    )

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "repairable"
    assert readiness["selected_class"].slug == artificer.slug
    assert readiness["selected_class"].source_id == "TCE"
    assert readiness["selected_species"].slug == tce_human.slug
    assert readiness["selected_species"].source_id == "TCE"
    assert readiness["selected_background"].slug == tce_sage.slug
    assert readiness["selected_background"].source_id == "TCE"
    assert readiness["selected_subclass"].slug == tce_armorer.slug
    assert readiness["selected_subclass"].source_id == "TCE"
    assert any("base class link" in reason for reason in readiness["reasons"])
    assert any("class row link" in reason for reason in readiness["reasons"])
    assert any("species link" in reason for reason in readiness["reasons"])
    assert any("background link" in reason for reason in readiness["reasons"])

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert repair_context["values"]["repair_class_slug"] == f"systems:{artificer.slug}"
    assert repair_context["values"]["repair_species_slug"] == f"systems:{tce_human.slug}"
    assert repair_context["values"]["repair_background_slug"] == f"systems:{tce_sage.slug}"
    assert repair_context["values"]["repair_subclass_slug"] == f"systems:{tce_armorer.slug}"

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        repair_context["values"],
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)

    assert repaired_definition.profile["class_ref"]["slug"] == artificer.slug
    assert repaired_definition.profile["class_ref"]["source_id"] == "TCE"
    assert repaired_definition.profile["classes"][0]["systems_ref"]["slug"] == artificer.slug
    assert repaired_definition.profile["species_ref"]["slug"] == tce_human.slug
    assert repaired_definition.profile["species_ref"]["source_id"] == "TCE"
    assert repaired_definition.profile["background_ref"]["slug"] == tce_sage.slug
    assert repaired_definition.profile["background_ref"]["source_id"] == "TCE"
    assert repaired_definition.profile["subclass_ref"]["slug"] == tce_armorer.slug
    assert repaired_definition.profile["subclass_ref"]["source_id"] == "TCE"
    assert repaired_readiness["status"] == "ready"


def test_imported_xge_subclass_with_stale_source_locked_ref_repairs_to_xge_entry():
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
    import_metadata = CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=definition.character_slug,
        source_path="imports://xge-archer.md",
        imported_at_utc="2026-04-08T00:00:00Z",
        parser_version="fixture",
        import_status="clean",
        warnings=[],
    )

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "repairable"
    assert readiness["selected_subclass"].slug == xge_arcane_archer.slug
    assert readiness["selected_subclass"].source_id == "XGE"
    assert any("XGE Martial Archetype link" in reason for reason in readiness["reasons"])

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert repair_context["values"]["repair_subclass_slug"] == f"systems:{xge_arcane_archer.slug}"

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        repair_context["values"],
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)

    assert repaired_definition.profile["subclass_ref"]["slug"] == xge_arcane_archer.slug
    assert repaired_definition.profile["subclass_ref"]["source_id"] == "XGE"
    assert repaired_readiness["status"] == "ready"


def test_imported_egw_subclass_with_stale_source_locked_ref_repairs_to_egw_entry():
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
    import_metadata = CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug=definition.character_slug,
        source_path="imports://egw-chronurgist.md",
        imported_at_utc="2026-04-08T00:00:00Z",
        parser_version="fixture",
        import_status="clean",
        warnings=[],
    )

    readiness = native_level_up_readiness(systems_service, "linden-pass", definition)

    assert readiness["status"] == "repairable"
    assert readiness["selected_subclass"].slug == egw_chronurgy.slug
    assert readiness["selected_subclass"].source_id == "EGW"
    assert any("EGW Arcane Tradition link" in reason for reason in readiness["reasons"])

    repair_context = build_imported_progression_repair_context(
        systems_service,
        "linden-pass",
        definition,
    )

    assert repair_context["values"]["repair_subclass_slug"] == f"systems:{egw_chronurgy.slug}"

    repaired_definition, _ = apply_imported_progression_repairs(
        "linden-pass",
        definition,
        import_metadata,
        repair_context,
        repair_context["values"],
    )
    repaired_readiness = native_level_up_readiness(systems_service, "linden-pass", repaired_definition)

    assert repaired_definition.profile["subclass_ref"]["slug"] == egw_chronurgy.slug
    assert repaired_definition.profile["subclass_ref"]["source_id"] == "EGW"
    assert repaired_readiness["status"] == "ready"


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
    assert repair_context["readiness"]["status"] == "repairable"
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

    repaired_feature_names = {feature["name"] for feature in repaired_definition.features}

    assert repaired_definition.source["source_type"] == "markdown_character_sheet"
    assert repaired_definition.profile["class_ref"]["slug"] == fighter.slug
    assert repaired_definition.profile["subclass_ref"]["slug"] == champion.slug
    assert repaired_definition.profile["species_ref"]["slug"] == human.slug
    assert repaired_definition.profile["background_ref"]["slug"] == acolyte.slug
    assert "Lucky" in repaired_feature_names
    assert "Archery" in repaired_feature_names
    assert repaired_definition.source["native_progression"]["baseline_repaired_at"]
    assert repaired_import.source_path == "imports://imported-hero.md"


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


def _builder_field_names(builder_context: dict[str, object]) -> set[str]:
    return {
        str(field.get("name") or "")
        for section in list(builder_context.get("choice_sections") or [])
        for field in list(section.get("fields") or [])
        if str(field.get("name") or "").strip()
    }


def _field_name_for_label(builder_context: dict[str, object], label_fragment: str) -> str:
    for section in list(builder_context.get("choice_sections") or []):
        for field in list(section.get("fields") or []):
            if label_fragment.lower() in str(field.get("label") or "").lower():
                return str(field.get("name") or "")
    raise AssertionError(f"builder field label containing '{label_fragment}' was not found")


_FREE_CAST_FEAT_CASES = [
    pytest.param(
        {
            "title": "Artificer Initiate",
            "slug": "tce-feat-artificer-initiate",
            "source_id": "TCE",
            "field_labels": {
                "spell_known_1_1": "Artificer Initiate Granted Cantrip 1",
                "spell_known_2_1": "Artificer Initiate Granted Spell 1",
            },
            "field_choices": {
                "spell_known_1_1": "Mage Hand",
                "spell_known_2_1": "Cure Wounds",
            },
            "expected_spells": [
                {"name": "Mage Hand", "mark": "Cantrip"},
                {
                    "name": "Cure Wounds",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "long_rest",
                },
            ],
            "expected_preview": [
                "Mage Hand (Granted, Cantrip)",
                "Cure Wounds (Granted, 1 / Long Rest)",
            ],
            "expected_ability": "Intelligence",
            "expected_save_dc": 12,
            "expected_attack_bonus": 4,
        },
        id="artificer-initiate",
    ),
    pytest.param(
        {
            "title": "Drow High Magic",
            "slug": "xge-feat-drow-high-magic",
            "source_id": "XGE",
            "field_labels": {},
            "field_choices": {},
            "expected_spells": [
                {
                    "name": "Detect Magic",
                    "mark": "",
                    "spell_access_type": "at_will",
                },
                {
                    "name": "Levitate",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "long_rest",
                },
                {
                    "name": "Dispel Magic",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "long_rest",
                },
            ],
            "expected_preview": [
                "Detect Magic (Granted, At will)",
                "Levitate (Granted, 1 / Long Rest)",
                "Dispel Magic (Granted, 1 / Long Rest)",
            ],
            "expected_ability": "Charisma",
            "expected_save_dc": 12,
            "expected_attack_bonus": 4,
        },
        id="drow-high-magic",
    ),
    pytest.param(
        {
            "title": "Fey Teleportation",
            "slug": "xge-feat-fey-teleportation",
            "source_id": "XGE",
            "field_labels": {},
            "field_choices": {},
            "expected_spells": [
                {
                    "name": "Misty Step",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "short_or_long_rest",
                },
            ],
            "expected_preview": [
                "Misty Step (Granted, 1 / Short or Long Rest)",
            ],
            "expected_ability": "Intelligence",
            "expected_save_dc": 12,
            "expected_attack_bonus": 4,
        },
        id="fey-teleportation",
    ),
    pytest.param(
        {
            "title": "Wood Elf Magic",
            "slug": "xge-feat-wood-elf-magic",
            "source_id": "XGE",
            "field_labels": {
                "spell_known_1_1": "Wood Elf Magic Granted Cantrip 1",
            },
            "field_choices": {
                "spell_known_1_1": "Produce Flame",
            },
            "expected_spells": [
                {"name": "Produce Flame", "mark": "Cantrip"},
                {
                    "name": "Longstrider",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "long_rest",
                },
                {
                    "name": "Pass without Trace",
                    "mark": "",
                    "spell_access_type": "free_cast",
                    "spell_access_uses": 1,
                    "spell_access_reset_on": "long_rest",
                },
            ],
            "expected_preview": [
                "Produce Flame (Granted, Cantrip)",
                "Longstrider (Granted, 1 / Long Rest)",
                "Pass without Trace (Granted, 1 / Long Rest)",
            ],
            "expected_ability": "Wisdom",
            "expected_save_dc": 11,
            "expected_attack_bonus": 3,
        },
        id="wood-elf-magic",
    ),
]


def _build_free_cast_feat_test_fixture() -> dict[str, object]:
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
    wizard = _systems_entry(
        "class",
        "phb-class-wizard",
        "Wizard",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["int", "wis"],
            "starting_proficiencies": {
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "history", "insight"]}}],
            },
            "spellcasting_ability": "int",
            "caster_progression": "full",
            "prepared_spells": "level + int",
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
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    artificer_initiate = _systems_entry("feat", "tce-feat-artificer-initiate", "Artificer Initiate", source_id="TCE")
    drow_high_magic = _systems_entry("feat", "xge-feat-drow-high-magic", "Drow High Magic", source_id="XGE")
    fey_teleportation = _systems_entry(
        "feat",
        "xge-feat-fey-teleportation",
        "Fey Teleportation",
        source_id="XGE",
    )
    wood_elf_magic = _systems_entry("feat", "xge-feat-wood-elf-magic", "Wood Elf Magic", source_id="XGE")
    mage_hand = _systems_entry(
        "spell",
        "phb-spell-mage-hand",
        "Mage Hand",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"TCE": ["Artificer"], "PHB": ["Wizard"]}},
    )
    cure_wounds = _systems_entry(
        "spell",
        "phb-spell-cure-wounds",
        "Cure Wounds",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"TCE": ["Artificer"], "PHB": ["Cleric", "Druid"]}},
    )
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={
            "casting_time": [{"number": 1, "unit": "action"}],
            "level": 1,
            "class_lists": {"PHB": ["Artificer", "Cleric", "Wizard"]},
            "ritual": True,
        },
    )
    levitate = _systems_entry(
        "spell",
        "phb-spell-levitate",
        "Levitate",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 2, "class_lists": {"PHB": ["Artificer", "Sorcerer", "Wizard"]}},
    )
    dispel_magic = _systems_entry(
        "spell",
        "phb-spell-dispel-magic",
        "Dispel Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 3, "class_lists": {"PHB": ["Artificer", "Cleric", "Wizard"]}},
    )
    misty_step = _systems_entry(
        "spell",
        "phb-spell-misty-step",
        "Misty Step",
        metadata={"casting_time": [{"number": 1, "unit": "bonus"}], "level": 2, "class_lists": {"PHB": ["Sorcerer", "Warlock", "Wizard"]}},
    )
    produce_flame = _systems_entry(
        "spell",
        "phb-spell-produce-flame",
        "Produce Flame",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 0, "class_lists": {"PHB": ["Druid"]}},
    )
    longstrider = _systems_entry(
        "spell",
        "phb-spell-longstrider",
        "Longstrider",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Artificer", "Druid", "Ranger"]}},
    )
    pass_without_trace = _systems_entry(
        "spell",
        "phb-spell-pass-without-trace",
        "Pass without Trace",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 2, "class_lists": {"PHB": ["Druid", "Ranger"]}},
    )

    feats = [artificer_initiate, drow_high_magic, fey_teleportation, wood_elf_magic]
    spells = [
        mage_hand,
        cure_wounds,
        detect_magic,
        levitate,
        dispel_magic,
        misty_step,
        produce_flame,
        longstrider,
        pass_without_trace,
    ]
    systems_service = _FakeSystemsService(
        {
            "class": [fighter, wizard],
            "race": [variant_human, human],
            "background": [acolyte],
            "feat": feats,
            "subclass": [],
            "item": [],
            "spell": spells,
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
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": ability_score_improvement,
                        "embedded_card": {"option_groups": []},
                    },
                ],
            },
        ],
    )
    return {
        "systems_service": systems_service,
        "fighter": fighter,
        "wizard": wizard,
        "variant_human": variant_human,
        "acolyte": acolyte,
        "feats": {entry.title: entry for entry in feats},
    }


def _apply_free_cast_test_ability_scores(definition: CharacterDefinition) -> None:
    definition.stats["ability_scores"]["int"].update({"score": 14, "modifier": 2, "save_bonus": 2})
    definition.stats["ability_scores"]["wis"].update({"score": 13, "modifier": 1, "save_bonus": 1})
    definition.stats["ability_scores"]["cha"].update({"score": 14, "modifier": 2, "save_bonus": 2})


def _apply_primary_class(definition: CharacterDefinition, class_entry: SystemsEntryRecord, *, level: int) -> None:
    class_ref = _systems_ref(class_entry)
    definition.profile["class_level_text"] = f"{class_entry.title} {level}"
    definition.profile["class_ref"] = class_ref
    definition.profile["classes"][0] = {
        "class_name": class_entry.title,
        "subclass_name": "",
        "level": level,
        "systems_ref": class_ref,
    }


def _apply_free_cast_feat_field_choices(
    *,
    form_values: dict[str, str],
    context: dict[str, object],
    prefix: str,
    case: dict[str, object],
) -> None:
    for suffix, expected_label in dict(case.get("field_labels") or {}).items():
        field_name = f"{prefix}{suffix}"
        assert _find_builder_field(context, field_name)["label"] == expected_label
    for suffix, choice_label in dict(case.get("field_choices") or {}).items():
        field_name = f"{prefix}{suffix}"
        form_values[field_name] = _field_value_for_label(context, field_name, str(choice_label))


def _assert_free_cast_feat_spellcasting(spellcasting: dict[str, object], case: dict[str, object]) -> None:
    source_rows = [dict(row or {}) for row in list(spellcasting.get("source_rows") or []) if isinstance(row, dict)]
    assert len(source_rows) == 1
    source_row = source_rows[0]
    assert source_row["title"] == case["title"]
    assert source_row["spellcasting_ability"] == case["expected_ability"]
    assert source_row["spell_save_dc"] == case["expected_save_dc"]
    assert source_row["spell_attack_bonus"] == case["expected_attack_bonus"]

    spells_by_name = {
        str(spell.get("name") or "").strip(): dict(spell or {})
        for spell in list(spellcasting.get("spells") or [])
    }
    assert set(spells_by_name) == {str(spec["name"]) for spec in list(case.get("expected_spells") or [])}
    for spec in list(case.get("expected_spells") or []):
        spell = spells_by_name[str(spec["name"])]
        assert spell["is_bonus_known"] is True
        assert str(spell.get("class_row_id") or "").strip() == ""
        assert str(spell.get("spell_source_row_id") or "").strip() == str(source_row.get("source_row_id") or "")
        assert str(spell.get("grant_source_label") or "").strip() == case["title"]
        assert str(spell.get("mark") or "").strip() == str(spec.get("mark") or "")
        assert str(spell.get("spell_access_type") or "").strip() == str(spec.get("spell_access_type") or "")
        expected_uses = spec.get("spell_access_uses")
        if expected_uses is None:
            assert spell.get("spell_access_uses") in {"", None}
        else:
            assert spell.get("spell_access_uses") == expected_uses
        assert str(spell.get("spell_access_reset_on") or "").strip() == str(spec.get("spell_access_reset_on") or "")


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


def _campaign_page_record(
    page_ref: str,
    title: str,
    *,
    section: str,
    subsection: str = "",
    summary: str = "",
    metadata: dict | None = None,
    body_markdown: str = "",
):
    return SimpleNamespace(
        page_ref=page_ref,
        metadata=dict(metadata or {}),
        body_markdown=body_markdown,
        page=SimpleNamespace(
            title=title,
            section=section,
            subsection=subsection,
            summary=summary,
        ),
    )


def _sorcerer_spell_entry(slug: str, title: str, *, level: int) -> SystemsEntryRecord:
    return _systems_entry(
        "spell",
        slug,
        title,
        metadata={
            "level": level,
            "class_lists": {"PHB": ["Sorcerer"]},
        },
    )


def _build_sorcerer_wild_magic_fixture() -> dict[str, object]:
    sorcerer = _systems_entry(
        "class",
        "phb-class-sorcerer",
        "Sorcerer",
        metadata={
            "hit_die": {"faces": 6},
            "proficiency": ["con", "cha"],
            "subclass_title": "Sorcerous Origin",
            "starting_proficiencies": {
                "weapons": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
                "skills": [{"choose": {"count": 2, "from": ["arcana", "deception", "insight", "persuasion"]}}],
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
            "languages": ["Common"],
        },
    )
    soldier = _systems_entry(
        "background",
        "phb-background-soldier",
        "Soldier",
        metadata={
            "skill_proficiencies": [{"athletics": True, "intimidation": True}],
        },
        body={
            "entries": [
                {
                    "name": "Feature: Military Rank",
                    "entries": ["You have a military rank from your career as a soldier."],
                    "data": {"isFeature": True},
                }
            ]
        },
    )
    wild_magic = _systems_entry(
        "subclass",
        "phb-subclass-wild-magic",
        "Wild Magic",
        metadata={
            "class_name": "Sorcerer",
            "class_source": "PHB",
        },
    )
    spellcasting = _systems_entry(
        "classfeature",
        "phb-classfeature-spellcasting",
        "Spellcasting",
        metadata={"level": 1},
    )
    wild_magic_progression_entry = build_campaign_page_progression_entries(
        _campaign_page_record(
            "mechanics/wild-magic-modification",
            "Wild Magic Modification",
            section="Mechanics",
            subsection="Class Modifications",
            metadata={
                "character_progression": {
                    "kind": "subclass",
                    "class_name": "Sorcerer",
                    "subclass_name": "Wild Magic",
                    "level": 1,
                    "character_option": {
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
                }
            },
            body_markdown=(
                "You gain a number of Wild Die equal to half your level. "
                "A Wild Die is a d6."
            ),
        )
    )[0]
    spells = [
        _sorcerer_spell_entry("phb-spell-mage-hand", "Mage Hand", level=0),
        _sorcerer_spell_entry("phb-spell-fire-bolt", "Fire Bolt", level=0),
        _sorcerer_spell_entry("phb-spell-prestidigitation", "Prestidigitation", level=0),
        _sorcerer_spell_entry("phb-spell-ray-of-frost", "Ray of Frost", level=0),
        _sorcerer_spell_entry("phb-spell-magic-missile", "Magic Missile", level=1),
        _sorcerer_spell_entry("phb-spell-shield", "Shield", level=1),
        _sorcerer_spell_entry("phb-spell-chromatic-orb", "Chromatic Orb", level=1),
        _sorcerer_spell_entry("phb-spell-sleep", "Sleep", level=1),
        _sorcerer_spell_entry("phb-spell-mage-armor", "Mage Armor", level=1),
    ]
    systems_service = _FakeSystemsService(
        {
            "class": [sorcerer],
            "race": [human],
            "background": [soldier],
            "feat": [],
            "subclass": [wild_magic],
            "spell": spells,
        },
        class_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Spellcasting",
                        "entry": spellcasting,
                        "embedded_card": {"option_groups": []},
                    },
                    {
                        "label": "Sorcerous Origin (choose subclass feature)",
                        "entry": None,
                        "embedded_card": None,
                    },
                ],
            },
            {
                "level": 4,
                "level_label": "Level 4",
                "feature_rows": [
                    {
                        "label": "Ability Score Improvement",
                        "entry": None,
                        "embedded_card": None,
                    }
                ],
            },
        ],
        subclass_progression=[
            {
                "level": 1,
                "level_label": "Level 1",
                "feature_rows": [
                    {
                        "label": "Wild Magic Modification",
                        "entry": wild_magic_progression_entry,
                        "embedded_card": None,
                    }
                ],
            }
        ],
    )
    level_one_values = {
        "name": "Aeris Vale",
        "character_slug": "aeris-vale",
        "class_slug": sorcerer.slug,
        "subclass_slug": wild_magic.slug,
        "species_slug": human.slug,
        "background_slug": soldier.slug,
        "str": "8",
        "dex": "14",
        "con": "14",
        "int": "10",
        "wis": "12",
        "cha": "16",
        "class_skill_1": "arcana",
        "class_skill_2": "deception",
        "spell_cantrip_1": "phb-spell-mage-hand",
        "spell_cantrip_2": "phb-spell-fire-bolt",
        "spell_cantrip_3": "phb-spell-prestidigitation",
        "spell_cantrip_4": "phb-spell-ray-of-frost",
        "spell_level_one_1": "phb-spell-magic-missile",
        "spell_level_one_2": "phb-spell-shield",
    }
    return {
        "systems_service": systems_service,
        "sorcerer": sorcerer,
        "human": human,
        "soldier": soldier,
        "wild_magic": wild_magic,
        "level_one_values": level_one_values,
    }


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


def test_normalize_definition_to_native_model_preserves_imported_expertise_and_updates_passives():
    definition = _minimal_imported_character_definition("selka-voss", "Selka Voss")
    definition.profile["class_level_text"] = "Rogue 5"
    definition.profile["classes"][0]["class_name"] = "Rogue"
    definition.profile["classes"][0]["level"] = 5
    definition.stats["proficiency_bonus"] = 2
    definition.stats["ability_scores"]["wis"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    definition.skills = [
        {"name": "Perception", "bonus": 9, "proficiency_level": "expertise"},
        {"name": "Insight", "bonus": 6, "proficiency_level": "proficient"},
        {"name": "Investigation", "bonus": 0, "proficiency_level": "none"},
    ]

    normalized = normalize_definition_to_native_model(definition)
    skills_by_name = {skill["name"]: skill for skill in normalized.skills}

    assert normalized.stats["proficiency_bonus"] == 3
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Perception"]["bonus"] == 9
    assert skills_by_name["Insight"]["proficiency_level"] == "proficient"
    assert skills_by_name["Insight"]["bonus"] == 6
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

    assert "Shield Shove (special action)" in context["preview"]["attacks"]
    assert shield_shove["attack_bonus"] is None
    assert shield_shove["damage"] == ""
    assert shield_shove["notes"] == "Bonus action after taking the Attack action; Shield Master shove within 5 feet."
    assert shield_shove["mode_key"] == "feat:phb-feat-shield-master:shove"
    assert shield_shove["equipment_refs"] == [shield_id]


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
        debounce_ms=350,
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
        debounce_ms=350,
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
    assert 'data-live-preview-debounce-ms="350"' in html


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
    assert 'data-live-preview-debounce-ms="350"' in html


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
    assert wild_die_resource["max"] == 1
    assert wild_die_resource["reset_on"] == "long_rest"


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
