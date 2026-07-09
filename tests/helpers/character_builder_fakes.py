from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import player_wiki.app as app_module
import pytest
import yaml
from player_wiki.campaign_item_mechanics import (
    build_campaign_item_mechanics_metadata,
    campaign_item_special_effect_metadata,
)
from player_wiki.character_campaign_options import normalize_campaign_character_option
from player_wiki.character_campaign_progression import build_campaign_page_progression_entries
from player_wiki.character_builder import (
    ABILITY_LABELS,
    CHARACTER_BUILDER_VERSION,
    NATIVE_PROGRESSION_FEATURE_SOURCE_KIND,
    _attach_campaign_item_page_support,
    _automatic_prepared_spell_lookup_keys,
    _build_item_catalog,
    _build_spell_catalog,
    _clear_builder_static_bundle_cache,
    _list_campaign_enabled_entries,
    _prepared_spell_count_for_level,
    _recalculate_definition_attacks,
    _resolve_builder_choices,
    _stabilize_choice_section_values,
    apply_imported_progression_repairs,
    build_native_level_up_character_definition,
    build_native_level_up_context,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    describe_equipment_state_support,
    native_level_up_readiness,
    normalize_definition_to_native_model,
    supports_native_level_up,
)
from player_wiki.character_adjustments import apply_manual_stat_adjustments
from player_wiki.character_service import build_initial_state, merge_state_with_definition
from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata
from player_wiki.managed_resource_registry import MANAGED_RESOURCE_TRACKER_INVENTORY
from player_wiki.repository import slugify
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
@pytest.fixture(autouse=True)
def _clear_static_builder_cache_between_tests():
    _clear_builder_static_bundle_cache()
    yield
    _clear_builder_static_bundle_cache()
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
        static_revision_token: str = "v1",
    ):
        self.store = _FakeSystemsStore(entries_by_type)
        self._class_progression = list(class_progression)
        self._subclass_progression = list(subclass_progression or [])
        self.static_revision_token = static_revision_token
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
        self.class_progression_calls = 0
        self.subclass_progression_calls = 0

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

    def get_builder_static_revision(
        self,
        campaign_slug: str,
        *,
        entry_types: tuple[str, ...],
    ) -> tuple[object, ...]:
        return (
            "fake",
            campaign_slug,
            self.static_revision_token,
            tuple(sorted(str(entry_type or "").strip() for entry_type in entry_types)),
            tuple(sorted(self._enabled_source_ids)),
            tuple(sorted(self._disabled_entry_keys)),
        )

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
        self.class_progression_calls += 1
        return list(self._class_progression)

    def build_subclass_feature_progression_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord | None,
    ) -> list[dict]:
        del campaign_slug, entry
        self.subclass_progression_calls += 1
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
def _managed_resource_definition(
    *,
    slug: str,
    title: str,
    category: str,
    source_id: str,
    class_name: str = "Fighter",
    class_slug: str = "phb-class-fighter",
    class_source_id: str = "PHB",
    class_level: int = 1,
    ability_scores: dict[str, int] | None = None,
    page_ref: str | None = None,
) -> CharacterDefinition:
    definition = _minimal_character_definition(character_slug=slug.replace("-", "_"), name=title)
    definition.profile["class_level_text"] = f"{class_name} {class_level}"
    definition.profile["classes"] = [
        {
            "row_id": "class-row-1",
            "class_name": class_name,
            "subclass_name": "",
            "level": class_level,
            "systems_ref": {
                "entry_key": f"dnd-5e|class|{class_source_id.lower()}|{class_slug}",
                "entry_type": "class",
                "title": class_name,
                "slug": class_slug,
                "source_id": class_source_id,
            },
        }
    ]
    definition.profile["class_ref"] = dict(definition.profile["classes"][0]["systems_ref"])
    for ability_key, score in dict(ability_scores or {}).items():
        definition.stats["ability_scores"][ability_key] = {
            "score": int(score),
            "modifier": (int(score) - 10) // 2,
            "save_bonus": (int(score) - 10) // 2,
        }
    feature_payload = {
        "id": f"{slug}-feature",
        "name": title,
        "category": category,
        "source": source_id,
        "description_markdown": "",
        "activation_type": "passive",
        "class_row_id": "class-row-1",
        "systems_ref": {
            "entry_key": f"dnd-5e|feature|{source_id.lower()}|{slug}",
            "entry_type": "subclassfeature" if category == "subclass_feature" else "classfeature",
            "title": title,
            "slug": slug,
            "source_id": source_id,
        },
    }
    if page_ref:
        feature_payload["page_ref"] = page_ref
    definition.features = [feature_payload]
    return definition
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
                "live_preview_debounce_ms": 650,
            },
            "dex": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 650,
            },
            "con": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 650,
            },
            "int": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 650,
            },
            "wis": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 650,
            },
            "cha": {
                "live_preview_trigger": "input",
                "live_preview_regions": "preview-summary,preview-spells,preview-attacks",
                "live_preview_debounce_ms": 650,
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
                "live_preview_debounce_ms": 650,
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
def _structured_subclass_spellcasting_metadata(
    *,
    spell_list_class_name: str = "Wizard",
    caster_progression: str = "1/3",
) -> dict[str, object]:
    return {
        "class_name": "Fighter",
        "class_source": "PHB",
        "spellcasting_ability": "int",
        "spell_list_class_name": spell_list_class_name,
        "caster_progression": caster_progression,
        "cantrip_progression": [0, 0, 2, 2],
        "spells_known_progression": [0, 0, 3, 4],
        "slot_progression": [
            [],
            [],
            [{"level": 1, "max_slots": 2}],
            [{"level": 1, "max_slots": 3}],
        ],
    }
def _repair_form_values_for_spell_rows(
    repair_context: dict[str, Any],
    *,
    cantrip_names: set[str],
    noncantrip_mark: str,
) -> dict[str, str]:
    form_values = {
        key: str(value)
        for key, value in dict(repair_context.get("values") or {}).items()
    }
    for row in list(repair_context.get("spell_rows") or []):
        field_name = str(row.get("field_name") or "").strip()
        if not field_name:
            continue
        form_values[field_name] = "Cantrip" if str(row.get("name") or "").strip() in cantrip_names else noncantrip_mark
        class_row_field_name = str(row.get("class_row_field_name") or "").strip()
        if class_row_field_name and not str(form_values.get(class_row_field_name) or "").strip():
            options = list(row.get("class_row_options") or [])
            if options:
                form_values[class_row_field_name] = str(options[0].get("value") or "").strip()
    return form_values
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
def _build_ritual_caster_test_fixture() -> dict[str, object]:
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
    second_wind = _systems_entry("classfeature", "phb-classfeature-second-wind", "Second Wind", metadata={"level": 1})
    ability_score_improvement = _systems_entry(
        "classfeature",
        "phb-classfeature-ability-score-improvement",
        "Ability Score Improvement",
        metadata={"level": 4},
    )
    ritual_caster = _systems_entry("feat", "phb-feat-ritual-caster", "Ritual Caster", source_id="PHB")
    detect_magic = _systems_entry(
        "spell",
        "phb-spell-detect-magic",
        "Detect Magic",
        metadata={"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    find_familiar = _systems_entry(
        "spell",
        "phb-spell-find-familiar",
        "Find Familiar",
        metadata={"casting_time": [{"number": 1, "unit": "hour"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
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
    alarm = _systems_entry(
        "spell",
        "phb-spell-alarm",
        "Alarm",
        metadata={"casting_time": [{"number": 1, "unit": "minute"}], "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
    )
    systems_service = _FakeSystemsService(
        {
            "class": [fighter],
            "race": [variant_human, human],
            "background": [acolyte],
            "feat": [ritual_caster],
            "subclass": [],
            "item": [],
            "spell": [detect_magic, find_familiar, identify, magic_missile, alarm],
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
        "variant_human": variant_human,
        "human": human,
        "acolyte": acolyte,
        "ritual_caster": ritual_caster,
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
            body_markdown="The Wild Die is a d6 used by this subclass modification.",
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
def _innovators_bolt_body_markdown() -> str:
    return (
        "*Weapon (pistol), very rare (requires attunement by an artificer)*\n\n"
        "Martial weapon, ranged weapon\n\n"
        "1d10 piercing; ammunition (20/60), reload (1 bullet)\n\n"
        "You gain a +1 bonus to attack and damage rolls made with this magic weapon.\n\n"
        "When reloading this weapon, an artificer attuned to it can expend a spell slot to load an "
        "enchanted bullet from its current developed list. Additional bullets may be developed "
        "through research.\n\n"
        "Current known enchanted bullet options:\n\n"
        "| Bullet | Damage per spell level | Additional effect |\n"
        "| --- | --- | --- |\n"
        "| Incendiary | 1d6 fire | Creatures within 5 feet of the target must make a Dexterity save "
        "against the bearer's spell save DC or take the fire damage. |\n"
        "| Booming | 1d8 thunder | Constitution save against the bearer's spell save DC or be "
        "deafened for 1 minute and knocked prone. |\n"
        "| Smoke | 1d6 bludgeoning | Wisdom save against the bearer's spell save DC or be blinded "
        "for 1 minute. |\n"
    )
def _innovators_bolt_systems_entry(*, review_status: str = "approved") -> SystemsEntryRecord:
    return _systems_entry(
        "item",
        "custom-linden-pass-innovators-bolt",
        "Innovator's Bolt",
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title="Innovator's Bolt",
            body_markdown=_innovators_bolt_body_markdown(),
            source_page_ref="items/innovators-bolt",
            review_status=review_status,
        ),
    )
def _hourglass_pendant_systems_entry(*, review_status: str = "approved"):
    return _systems_entry(
        "item",
        "custom-linden-pass-hourglass-pendant",
        "Hourglass Pendant",
        source_id="CUSTOM-LINDEN-PASS",
        metadata=build_campaign_item_mechanics_metadata(
            title="Hourglass Pendant",
            body_markdown=(
                "*Wondrous item, very rare (requires attunement by a chronurgy wizard)*\n\n"
                "A timeworn focus for chronurgy magic."
            ),
            explicit_mechanics={
                "spell_support": [
                    {
                        "source": {
                            "id": "spell-source:item:hourglass-pendant",
                            "title": "Hourglass Pendant",
                            "kind": "item",
                            "ability_key": "int",
                        },
                        "grants": {
                            "_": [
                                {
                                    "spell": "Gift of Alacrity",
                                    "access_type": "free_cast",
                                    "access_uses": 1,
                                    "access_reset_on": "long_rest",
                                }
                            ]
                        },
                    }
                ],
                "resource_template_bonuses": [{"id": "chronal-shift", "bonus": 1}],
            },
            source_page_ref="items/hourglass-pendant",
            review_status=review_status,
        ),
    )

__all__ = [name for name in globals() if not name.startswith("__")]
