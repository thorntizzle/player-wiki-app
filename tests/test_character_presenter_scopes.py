from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from player_wiki import character_mechanics_projection as mechanics_module
from player_wiki import character_presenter as presenter_module
from player_wiki import character_builder as builder_module
from player_wiki import character_builder_catalogs as catalogs_module
from player_wiki import character_builder_derivation as derivation_module
from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
from player_wiki.character_models import (
    CharacterDefinition,
    CharacterImportMetadata,
    CharacterRecord,
    CharacterStateRecord,
)
from player_wiki.character_presenter import (
    DND_COMMON_PRESENTATION_FIELDS,
    DND_SECTION_DEPENDENCY_MANIFEST,
    present_character_detail,
    present_dnd_character_section,
    present_dnd_character_section_counts,
)
from player_wiki.character_workspace_sections import (
    build_dnd_session_section_navigation,
    build_session_character_sections,
)
from player_wiki.character_page_records import list_visible_character_page_records
from player_wiki.models import Campaign
from tests.helpers.character_builder_fakes import (
    _campaign_page_record,
    _systems_entry,
    _systems_ref,
)
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG


FULL_PRESENTATION_KEYS = (
    "slug",
    "name",
    "state_revision",
    "current_hp",
    "max_hp",
    "temp_hp",
    "hit_dice",
    "player_notes_markdown",
    "player_notes_html",
    "physical_description_markdown",
    "physical_description_html",
    "personal_background_markdown",
    "personal_background_html",
    "class_level_text",
    "header_segments",
    "species",
    "background",
    "alignment",
    "identity_details",
    "overview_stats",
    "overview_stat_rows",
    "xianxia_defense",
    "xianxia_actions",
    "xianxia_effort_damage",
    "xianxia_check_formula",
    "xianxia_difficulty_states",
    "xianxia_honor_interactions",
    "xianxia_skill_use_guardrails",
    "xianxia_rule_text_references",
    "xianxia_active_state_reminders",
    "xianxia_stance_break",
    "xianxia_read",
    "attack_reminders",
    "defensive_rules",
    "item_use_actions",
    "projection_warnings",
    "arcane_armor_state",
    "divine_avatar_forms_state",
    "death_save_summary",
    "abilities",
    "skills",
    "proficiency_groups",
    "resources",
    "attacks",
    "hidden_attacks",
    "feature_groups",
    "spellcasting",
    "inventory",
    "currency",
    "currency_values",
    "other_currency",
    "reference_sections",
)

SPELLCASTING_SUMMARY_FIELDS = (
    "spellcasting_class",
    "spellcasting_ability",
    "spell_save_dc",
    "spell_attack_bonus",
    "slots",
    "slots_title",
    "slot_pools",
    "multiclass_summary",
    "is_multiclass",
)
SPELLCASTING_ROW_SUMMARY_FIELDS = (
    "class_row_id",
    "title",
    "spellcasting_ability",
    "spell_save_dc",
    "spell_attack_bonus",
    "row_kind",
    "spell_mode",
)


def _assert_scoped_projection_parity(
    scoped: dict[str, Any],
    full: dict[str, Any],
    dependency: Any,
) -> None:
    projection_fields = tuple(
        dict.fromkeys((*DND_COMMON_PRESENTATION_FIELDS, *dependency.output_fields))
    )
    exact_fields = tuple(
        field
        for field in projection_fields
        if not (dependency.spellcasting_summary_only and field == "spellcasting")
    )
    assert {field: scoped[field] for field in exact_fields} == {
        field: full[field] for field in exact_fields
    }
    if not dependency.spellcasting_summary_only:
        return
    assert {
        field: scoped["spellcasting"][field]
        for field in SPELLCASTING_SUMMARY_FIELDS
    } == {
        field: full["spellcasting"][field]
        for field in SPELLCASTING_SUMMARY_FIELDS
    }
    assert [
        {field: row[field] for field in SPELLCASTING_ROW_SUMMARY_FIELDS}
        for row in scoped["spellcasting"]["row_sections"]
    ] == [
        {field: row[field] for field in SPELLCASTING_ROW_SUMMARY_FIELDS}
        for row in full["spellcasting"]["row_sections"]
    ]


def _campaign(*, system: str = "DND-5E") -> Campaign:
    return Campaign(
        title="Presenter Contract",
        slug="presenter-contract",
        summary="",
        system=system,
        current_session=1,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
    )


def _record(
    *,
    system: str = "DND-5E",
    definition_overrides: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> CharacterRecord:
    payload: dict[str, Any] = {
        "campaign_slug": "presenter-contract",
        "character_slug": "contract-character",
        "name": "Contract Character",
        "status": "active",
        "system": system,
        "profile": {},
        "stats": {"max_hp": 10},
        "skills": [],
        "proficiencies": {},
        "attacks": [],
        "features": [],
        "spellcasting": {},
        "equipment_catalog": [],
        "reference_notes": {},
        "resource_templates": [],
        "source": {},
    }
    payload.update(definition_overrides or {})
    definition = CharacterDefinition.from_dict(payload)
    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            source_path="test://character-presenter-contract",
            imported_at_utc="2026-08-11T00:00:00Z",
            parser_version="test",
            import_status="ok",
            warnings=[],
        ),
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=7,
            state=state or {"vitals": {"current_hp": 6, "temp_hp": 0}},
            updated_at=datetime(2026, 8, 11),
            updated_by_user_id=None,
        ),
    )


def _dnd_record() -> CharacterRecord:
    return _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {
                        "row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 2,
                        "hit_die": "d6",
                    }
                ],
                "species": "Human",
                "background": "Sage",
                "alignment": "Neutral Good",
                "size": "Medium",
                "faith": "The Lantern",
                "guild": "Readers",
                "experience_model": "Milestone",
                "biography_markdown": "First biography.",
                "personality_markdown": "Careful and curious.",
            },
            "stats": {
                "max_hp": 18,
                "armor_class": 13,
                "initiative_bonus": 2,
                "speed": "30 ft.",
                "proficiency_bonus": 2,
                "passive_perception": 12,
                "passive_insight": 11,
                "passive_investigation": 15,
                "carrying_capacity": 120,
                "push_drag_lift": 240,
                "ability_scores": {
                    "str": {"score": 8, "modifier": -1, "save_bonus": -1},
                    "dex": {"score": 14, "modifier": 2, "save_bonus": 2},
                    "con": {"score": 12, "modifier": 1, "save_bonus": 1},
                    "int": {"score": 16, "modifier": 3, "save_bonus": 5},
                    "wis": {"score": 12, "modifier": 1, "save_bonus": 1},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "skills": [
                {"name": "Perception", "bonus": 2, "proficiency_level": "none"},
                {"name": "Arcana", "bonus": 5, "proficiency_level": "proficient"},
            ],
            "proficiencies": {
                "weapons": ["Daggers"],
                "tools": ["Calligrapher's supplies"],
                "languages": ["Common", "Draconic"],
            },
            "attacks": [
                {
                    "name": "Quarterstaff",
                    "attack_bonus": 1,
                    "damage": "1d6 - 1",
                    "damage_type": "bludgeoning",
                    "category": "melee",
                    "notes": "Versatile.",
                }
            ],
            "features": [
                {
                    "id": "feature-parent",
                    "name": "Arcane Recovery",
                    "category": "class_feature",
                    "activation_type": "action",
                    "description_markdown": "Recover a spell slot.",
                    "page_ref": "mechanics/arcane-recovery",
                },
                {
                    "id": "feature-child",
                    "name": "Recovery Detail",
                    "category": "class_feature",
                    "parent_feature_id": "feature-parent",
                    "description_markdown": "Once per day.",
                },
            ],
            "spellcasting": {
                "spellcasting_class": "Wizard",
                "spellcasting_ability": "INT",
                "spell_save_dc": 13,
                "spell_attack_bonus": 5,
                "class_rows": [
                    {
                        "class_row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 2,
                        "spellcasting_ability": "INT",
                        "spell_save_dc": 13,
                        "spell_attack_bonus": 5,
                        "spell_mode": "wizard",
                    }
                ],
                "slot_progression": [{"level": 1, "max_slots": 3}],
                "spells": [
                    {
                        "name": "Fire Bolt",
                        "class_row_id": "class-row-1",
                        "level": 0,
                        "mark": "Cantrip",
                        "casting_time": "1 action",
                        "range": "120 feet",
                        "page_ref": "mechanics/fire-bolt",
                    },
                    {
                        "name": "Shield",
                        "class_row_id": "class-row-1",
                        "level": 1,
                        "mark": "Prepared",
                        "casting_time": "1 reaction",
                        "range": "Self",
                        "page_ref": "mechanics/shield",
                    },
                ],
            },
            "equipment_catalog": [
                {
                    "id": "rope",
                    "name": "Silk Rope",
                    "page_ref": "items/silk-rope",
                    "campaign_item_mechanics_version": "1",
                    "campaign_item_mechanics_review_status": "approved",
                    "item_use_actions": [
                        {
                            "id": "rope-burst",
                            "kind": "spell_slot_item_attack",
                            "label": "Rope burst",
                            "slot_cost": {
                                "lane": "spellcasting",
                                "allowed_levels": [1],
                            },
                            "choices": [
                                {
                                    "id": "pull",
                                    "label": "Pull",
                                    "support_state": "modeled",
                                }
                            ],
                        }
                    ],
                },
                {"id": "ink", "name": "Ink"},
            ],
            "reference_notes": {
                "additional_notes_markdown": "Additional note.",
                "allies_and_organizations_markdown": "The Readers.",
                "custom_sections": [
                    {"title": "Research", "body_markdown": "Catalogued clues."},
                ],
            },
        },
        state={
            "vitals": {
                "current_hp": 11,
                "temp_hp": 2,
                "death_saves": {"successes": 1, "failures": 2},
            },
            "hit_dice": {"pools": [{"faces": 6, "current": 1, "max": 2}]},
            "notes": {
                "player_notes_markdown": "Player note.",
                "physical_description_markdown": "Silver spectacles.",
                "background_markdown": "Raised in an archive.",
            },
            "resources": [
                {
                    "id": "second",
                    "label": "Second Resource",
                    "current": 1,
                    "max": 2,
                    "display_order": 2,
                },
                {
                    "id": "first",
                    "label": "First Resource",
                    "current": 3,
                    "max": 3,
                    "display_order": 1,
                },
            ],
            "spell_slots": [{"level": 1, "used": 1}],
            "inventory": [
                {
                    "id": "rope",
                    "catalog_ref": "rope",
                    "name": "Silk Rope",
                    "quantity": 1,
                    "tags": ["adventuring gear"],
                },
                {
                    "id": "ink",
                    "catalog_ref": "ink",
                    "name": "Ink",
                    "quantity": 2,
                    "tags": ["tool"],
                },
            ],
            "currency": {"cp": 1, "sp": 2, "ep": 3, "gp": 4, "pp": 5, "other": ["1 favor"]},
        },
    )


def _xianxia_record() -> CharacterRecord:
    return _record(
        system="Xianxia",
        definition_overrides={
            "profile": {"class_level_text": "Mortal Cultivator", "species": "Human"},
            "xianxia": {
                "realm": "Mortal",
                "attributes": {"con": 3},
                "efforts": {"basic": 2},
                "energy": {"jing": {"max": 1}, "qi": {"max": 1}, "shen": {"max": 1}},
                "durability": {"hp_max": 10, "stance_max": 12},
                "trained_skills": ["Calligraphy", "Tea Ceremony", "Fishing"],
                "manual_armor_bonus": 2,
            },
        },
        state={
            "vitals": {"current_hp": 8, "temp_hp": 1},
            "notes": {"player_notes_markdown": "Cultivation note."},
            "xianxia": {
                "vitals": {"current_hp": 8, "temp_hp": 1, "current_stance": 9, "temp_stance": 0},
                "energies": {"jing": {"current": 1}, "qi": {"current": 1}, "shen": {"current": 1}},
                "yin_yang": {"yin": {"current": 1}, "yang": {"current": 1}},
                "dao": {"current": 2},
                "currency": {"coin": 4, "supply": 3, "spirit_stones": 2},
                "inventory": {"enabled": True, "quantities": []},
            },
        },
    )


def test_full_dnd_presenter_contract_freezes_outer_shape_nested_values_and_ordering():
    presented = present_character_detail(_campaign(), _dnd_record())

    assert len(presented) == 52
    assert tuple(presented) == FULL_PRESENTATION_KEYS
    assert presented["state_revision"] == 7
    assert presented["hit_dice"] == {
        "pools": [
            {
                "faces": 6,
                "label": "d6",
                "current": 1,
                "max": 2,
                "input_name": "hit_dice_d6",
            }
        ],
        "value": "d6 1/2",
        "full_value": "2d6",
        "regain_on_long_rest": 1,
    }
    assert [[stat["label"] for stat in row] for row in presented["overview_stat_rows"]] == [
        ["Current HP", "Temp HP", "Hit Dice"],
        ["Armor Class", "Initiative", "Speed"],
        ["Proficiency", "Passive Perception", "Passive Insight", "Passive Investigation"],
        ["Carrying Capacity", "Push / Drag / Lift"],
    ]
    assert [ability["name"] for ability in presented["abilities"]] == [
        "Strength",
        "Dexterity",
        "Constitution",
        "Intelligence",
        "Wisdom",
        "Charisma",
    ]
    assert [skill["name"] for skill in presented["skills"]] == ["Arcana", "Perception"]
    assert [resource["id"] for resource in presented["resources"]] == ["first", "second"]
    assert presented["attacks"][0]["name"] == "Quarterstaff"
    assert presented["feature_groups"][0]["title"] == "Class Features"
    assert [entry["name"] for entry in presented["feature_groups"][0]["entries"]] == [
        "Arcane Recovery"
    ]
    assert [child["name"] for child in presented["feature_groups"][0]["entries"][0]["children"]] == [
        "Recovery Detail"
    ]
    assert presented["spellcasting"]["slots"] == [
        {
            "level": 1,
            "label": "1st level",
            "available": 2,
            "used": 1,
            "max": 3,
            "slot_lane_id": "",
        }
    ]
    assert [
        spell["name"]
        for spell in presented["spellcasting"]["row_sections"][0]["spells"]
    ] == ["Fire Bolt", "Shield"]
    assert [item["name"] for item in presented["inventory"]] == ["Silk Rope", "Ink"]
    assert [row["key"] for row in presented["currency"]] == ["cp", "sp", "ep", "gp", "pp"]
    assert presented["currency_values"] == {"cp": 1, "sp": 2, "ep": 3, "gp": 4, "pp": 5}
    assert [section["title"] for section in presented["reference_sections"]] == [
        "Biography",
        "Personality",
        "Additional Notes",
        "Allies and Organizations",
        "Research",
    ]


def test_full_xianxia_presenter_contract_keeps_full_only_shape_and_ordering():
    presented = present_character_detail(_campaign(system="Xianxia"), _xianxia_record())

    assert len(presented) == 52
    assert tuple(presented) == FULL_PRESENTATION_KEYS
    assert presented["hit_dice"] == {
        "pools": [],
        "value": "--",
        "full_value": "--",
        "regain_on_long_rest": 0,
    }
    assert presented["spellcasting"] is None
    assert [subpage["label"] for subpage in presented["xianxia_read"]["subpages"]] == [
        "Quick Reference",
        "Martial Arts",
        "Techniques",
        "Resources",
        "Skills",
        "Equipment",
        "Inventory",
        "Portrait",
        "Personal",
        "Notes",
        "Controls",
    ]
    assert presented["xianxia_read"]["identity"] == {
        "realm": "Mortal",
        "actions_per_turn": 2,
        "honor": "Honorable",
        "reputation": "Unknown",
    }
    assert presented["xianxia_read"]["resources"]["durability"] == [
        {"key": "hp", "label": "HP", "current": 8, "max": 10, "temp": 1},
        {"key": "stance", "label": "Stance", "current": 9, "max": 12, "temp": 0},
    ]


def test_full_presenter_freezes_notes_flag_and_none_versus_empty_page_records(monkeypatch):
    record = _dnd_record()
    seen_page_records: list[list[Any] | None] = []
    original_projection = presenter_module.build_character_mechanics_projection

    def capture_projection(**kwargs):
        seen_page_records.append(kwargs["campaign_page_records"])
        return original_projection(**kwargs)

    monkeypatch.setattr(
        presenter_module,
        "build_character_mechanics_projection",
        capture_projection,
    )
    explicit_empty: list[Any] = []
    with_notes = present_character_detail(
        _campaign(),
        record,
        campaign_page_records=None,
        include_player_notes_section=True,
    )
    without_notes = present_character_detail(
        _campaign(),
        record,
        campaign_page_records=explicit_empty,
        include_player_notes_section=False,
    )

    assert seen_page_records[0] is None
    assert seen_page_records[1] is explicit_empty
    assert with_notes["player_notes_markdown"] == without_notes["player_notes_markdown"] == "Player note."
    assert with_notes["player_notes_html"] == without_notes["player_notes_html"]
    assert with_notes["reference_sections"] == without_notes["reference_sections"]


def test_full_presenter_returns_detached_nested_containers():
    record = _dnd_record()
    definition_before = deepcopy(record.definition.to_dict())
    state_before = deepcopy(record.state_record.state)
    baseline = present_character_detail(_campaign(), record)
    mutated = present_character_detail(_campaign(), record)

    mutated["overview_stat_rows"][0][0]["value"] = "mutated"
    mutated["abilities"][0]["skills"].append({"name": "Injected"})
    mutated["feature_groups"][0]["entries"][0]["children"][0]["name"] = "mutated"
    mutated["spellcasting"]["row_sections"][0]["spells"][0]["badges"].append("mutated")
    mutated["inventory"][0]["tags"].append("mutated")
    mutated["currency_values"]["gp"] = 999
    mutated["reference_sections"][0]["title"] = "mutated"

    assert present_character_detail(_campaign(), record) == baseline
    assert record.definition.to_dict() == definition_before
    assert record.state_record.state == state_before


def test_full_presenter_freezes_stateful_mechanics_warnings_and_sanitized_html(monkeypatch):
    record = _dnd_record()
    record.state_record.state["notes"]["player_notes_markdown"] = (
        "<script>alert('private')</script>**Safe note.**"
    )
    record.definition.features[0]["description_markdown"] = (
        "<script>alert('feature')</script>**Safe feature.**"
    )
    original_projection = presenter_module.build_character_mechanics_projection

    def stateful_projection(**kwargs):
        projection = original_projection(**kwargs)
        projection["arcane_armor_state"] = {
            "available": True,
            "enabled": True,
            "feature_key": "arcane_armor",
        }
        projection["divine_avatar_forms_state"] = {
            "available": True,
            "active_form_key": "mourning",
            "forms": [{"key": "mourning", "label": "Avatar of Mourning"}],
        }
        projection["item_use_actions"] = [
            {
                "action_key": "hourglass-shift",
                "item_name": "Hourglass Pendant",
                "available": True,
            }
        ]
        projection["defensive_rules"] = [
            {"label": "Warded", "summary": "Armor Class +1 while equipped."}
        ]
        projection["projection_warnings"] = [
            {"code": "read_time_projection_failed", "message": "sanitized fixture warning"}
        ]
        return projection

    monkeypatch.setattr(
        presenter_module,
        "build_character_mechanics_projection",
        stateful_projection,
    )

    presented = present_character_detail(_campaign(), record)

    assert presented["arcane_armor_state"] == {
        "available": True,
        "enabled": True,
        "feature_key": "arcane_armor",
    }
    assert presented["divine_avatar_forms_state"] == {
        "available": True,
        "active_form_key": "mourning",
        "forms": [{"key": "mourning", "label": "Avatar of Mourning"}],
    }
    assert presented["item_use_actions"] == [
        {
            "action_key": "hourglass-shift",
            "item_name": "Hourglass Pendant",
            "available": True,
        }
    ]
    assert presented["defensive_rules"] == [
        {"label": "Warded", "summary": "Armor Class +1 while equipped."}
    ]
    assert presented["projection_warnings"] == [
        {"code": "read_time_projection_failed", "message": "sanitized fixture warning"}
    ]
    assert "<script" not in presented["player_notes_html"]
    assert "Safe note." in presented["player_notes_html"]
    assert "<script" not in presented["feature_groups"][0]["entries"][0]["description_html"]
    assert "Safe feature." in presented["feature_groups"][0]["entries"][0]["description_html"]


@pytest.mark.parametrize("section", tuple(DND_SECTION_DEPENDENCY_MANIFEST))
def test_every_scoped_dnd_section_matches_only_its_frozen_full_fields(section):
    record = _dnd_record()
    full = present_character_detail(_campaign(), record)

    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section=section,
    )
    dependency = DND_SECTION_DEPENDENCY_MANIFEST[section]
    projection_fields = tuple(
        dict.fromkeys((*DND_COMMON_PRESENTATION_FIELDS, *dependency.output_fields))
    )

    assert tuple(scoped) == (
        "presentation_scope",
        "projection_fields",
        *projection_fields,
    )
    assert scoped["presentation_scope"] == section
    assert scoped["projection_fields"] == projection_fields
    _assert_scoped_projection_parity(scoped, full, dependency)


def test_scoped_quick_preserves_ability_and_spellcasting_summary_without_linked_bodies(
    monkeypatch,
):
    record = _dnd_record()
    full = present_character_detail(_campaign(), record)

    def fail_linked_body(*_args, **_kwargs):
        pytest.fail("Quick presentation resolved an unrelated feature or spell body")

    monkeypatch.setattr(
        presenter_module,
        "resolve_feature_description_html",
        fail_linked_body,
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_spell_description_html",
        fail_linked_body,
    )

    quick = present_dnd_character_section(_campaign(), record, section="quick")

    assert quick["abilities"] == full["abilities"]
    assert quick["skills"] == full["skills"]
    assert quick["proficiency_groups"] == full["proficiency_groups"]

    assert {
        field: quick["spellcasting"][field]
        for field in SPELLCASTING_SUMMARY_FIELDS
    } == {
        field: full["spellcasting"][field]
        for field in SPELLCASTING_SUMMARY_FIELDS
    }
    assert [
        {field: row[field] for field in SPELLCASTING_ROW_SUMMARY_FIELDS}
        for row in quick["spellcasting"]["row_sections"]
    ] == [
        {field: row[field] for field in SPELLCASTING_ROW_SUMMARY_FIELDS}
        for row in full["spellcasting"]["row_sections"]
    ]
    assert all(
        "spells" not in row and "spell_level_sections" not in row
        for row in quick["spellcasting"]["row_sections"]
    )
    assert quick["spellcasting"]["current_row_sections"] == []
    assert quick["spellcasting"]["preparation_row_sections"] == []


def test_dnd_scope_manifest_is_immutable_and_keeps_overview_quick_and_spell_aliases_explicit():
    assert DND_SECTION_DEPENDENCY_MANIFEST["overview"] is not DND_SECTION_DEPENDENCY_MANIFEST["quick"]
    assert DND_SECTION_DEPENDENCY_MANIFEST["overview"].output_fields != (
        DND_SECTION_DEPENDENCY_MANIFEST["quick"].output_fields
    )
    assert DND_SECTION_DEPENDENCY_MANIFEST["spells"] is DND_SECTION_DEPENDENCY_MANIFEST["spellcasting"]
    assert DND_SECTION_DEPENDENCY_MANIFEST["spells"].catalog_components == frozenset({"spells"})
    assert DND_SECTION_DEPENDENCY_MANIFEST["spells"].mechanics_components.isdisjoint(
        {"equipment", "inventory", "item_actions"}
    )
    assert DND_SECTION_DEPENDENCY_MANIFEST["overview"].mechanics_components == frozenset(
        {"defensive_rules", "divine_avatar"}
    )
    assert DND_SECTION_DEPENDENCY_MANIFEST["equipment"].catalog_components == frozenset({"items"})
    assert "divine_avatar" in DND_SECTION_DEPENDENCY_MANIFEST["equipment"].mechanics_components
    assert "item_actions" in DND_SECTION_DEPENDENCY_MANIFEST["equipment"].mechanics_components
    assert "item_actions" not in DND_SECTION_DEPENDENCY_MANIFEST["inventory"].mechanics_components

    with pytest.raises(TypeError):
        DND_SECTION_DEPENDENCY_MANIFEST["new"] = DND_SECTION_DEPENDENCY_MANIFEST["notes"]
    with pytest.raises(FrozenInstanceError):
        DND_SECTION_DEPENDENCY_MANIFEST["notes"].output_fields = ()


def test_equipment_scope_reprojects_avatar_dependent_item_action_save_dc_without_spell_work(
    monkeypatch,
):
    record = _record(
        definition_overrides={
            "stats": {
                "max_hp": 50,
                "armor_class": 16,
                "proficiency_bonus": 3,
                "passive_perception": 16,
                "passive_insight": 16,
                "passive_investigation": 10,
                "ability_scores": {
                    "str": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "wis": {"score": 16, "modifier": 3, "save_bonus": 6},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "skills": [
                {
                    "name": "Insight",
                    "bonus": 6,
                    "proficiency_level": "proficient",
                },
                {
                    "name": "Perception",
                    "bonus": 6,
                    "proficiency_level": "proficient",
                },
            ],
            "features": [
                {
                    "name": "Divine Avatar Forms",
                    "category": "custom_feature",
                    "campaign_option": {
                        "kind": "feature",
                        "page_ref": "mechanics/divine-avatar-forms",
                        "mechanic_effects": [
                            {
                                "kind": "divine_avatar_form_grant",
                                "mechanic_key": "divine_avatar_forms",
                                "mechanic_version": 1,
                                "form_key": "avatar_of_mourning",
                                "form_version": 1,
                            }
                        ],
                    },
                }
            ],
            "spellcasting": {
                "spellcasting_class": "Cleric",
                "spellcasting_ability": "Wisdom",
                "spell_save_dc": 14,
                "spell_attack_bonus": 6,
                "slot_progression": [{"level": 1, "max_slots": 4}],
                "class_rows": [],
                "spells": [],
            },
            "equipment_catalog": [
                {
                    "id": "avatar-bolt",
                    "name": "Avatar Bolt",
                    "campaign_item_mechanics_version": "1",
                    "campaign_item_mechanics_review_status": "approved",
                    "item_use_actions": [
                        {
                            "id": "avatar-bolt-shot",
                            "kind": "spell_slot_item_attack",
                            "label": "Avatar Bolt Shot",
                            "requires_equipped": True,
                            "requires_attunement": True,
                            "slot_cost": {
                                "lane": "spellcasting",
                                "allowed_levels": [1],
                            },
                            "choices": [
                                {
                                    "id": "mourning",
                                    "label": "Mourning",
                                    "support_state": "modeled",
                                    "save": {
                                        "ability": "wis",
                                        "dc_source": "character_spell_save_dc",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        state={
            "vitals": {"current_hp": 20, "temp_hp": 0},
            "spell_slots": [{"level": 1, "used": 0}],
            "resources": [],
            "inventory": [
                {
                    "id": "avatar-bolt",
                    "catalog_ref": "avatar-bolt",
                    "name": "Avatar Bolt",
                    "quantity": 1,
                    "is_equipped": True,
                    "is_attuned": True,
                }
            ],
            "currency": {},
            "notes": {},
            "feature_states": {
                "divine_avatar_forms": {
                    "schema_version": 1,
                    "active_form": "avatar_of_mourning",
                    "forms": {
                        "avatar_of_mourning": {
                            "schema_version": 1,
                            "form_version": 1,
                            "rounds_elapsed": 1,
                            "cooldown_active": False,
                        }
                    },
                }
            },
        },
    )
    full = present_character_detail(_campaign(), record)
    assert full["item_use_actions"][0]["choices"][0]["save"]["dc"] == 22

    transient_calls: list[dict[str, Any]] = []
    original_transient_projection = mechanics_module.project_definition_with_transient_effects

    def transient_projection_spy(*args, **kwargs):
        transient_calls.append(dict(kwargs))
        return original_transient_projection(*args, **kwargs)

    def fail_hidden_spell_or_body_work(*_args, **_kwargs):
        pytest.fail("equipment scope performed spell presentation or linked-body work")

    monkeypatch.setattr(
        mechanics_module,
        "project_definition_with_transient_effects",
        transient_projection_spy,
    )
    monkeypatch.setattr(
        derivation_module,
        "_derive_definition_spellcasting",
        fail_hidden_spell_or_body_work,
    )
    monkeypatch.setattr(
        presenter_module,
        "spell_slot_lanes_from_spellcasting",
        fail_hidden_spell_or_body_work,
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_spell_description_html",
        fail_hidden_spell_or_body_work,
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_feature_description_html",
        fail_hidden_spell_or_body_work,
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_item_description_html",
        fail_hidden_spell_or_body_work,
    )
    scoped = present_dnd_character_section(_campaign(), record, section="equipment")

    assert scoped["item_use_actions"] == full["item_use_actions"]
    assert scoped["item_use_actions"][0]["choices"][0]["save"] == {
        "ability": "wis",
        "dc_source": "character_spell_save_dc",
        "dc": 22,
        "label": "WIS save DC 22",
    }
    assert len(transient_calls) == 1
    assert transient_calls[0]["item_catalog"]["entries"] == []
    assert transient_calls[0]["spell_catalog"]["entries"] == []
    assert transient_calls[0]["derivation_components"] == frozenset(
        {"item_ability_minimums", "sheet_entries", "spellcasting_math"}
    )


def test_equipment_scope_derives_missing_spell_action_math_without_spell_state_or_catalog_work(
    monkeypatch,
):
    wizard = _systems_entry(
        "class",
        "wizard-phb",
        "Wizard",
        metadata={
            "hit_die": "d6",
            "spellcasting_ability": "int",
            "caster_progression": "full",
        },
    )

    class MathSystemsService:
        def __init__(self):
            self.catalog_calls: list[str] = []

        def list_enabled_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            entry_type=None,
            query="",
            limit=None,
        ):
            del query, limit
            self.catalog_calls.append(str(entry_type or ""))
            return [wizard] if entry_type == "class" else []

        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return wizard if entry_key == wizard.entry_key else None

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            return wizard if entry_slug == wizard.slug else None

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry.entry_key == wizard.entry_key

        def search_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            query,
            entry_type=None,
            limit=100,
            **_kwargs,
        ):
            del limit
            return [
                entry
                for entry in (wizard,)
                if entry.entry_type == entry_type
                and entry.title.casefold() == str(query).casefold()
            ]

        def build_class_feature_progression_for_class_entry(self, *_args, **_kwargs):
            return []

        def build_subclass_feature_progression_for_subclass_entry(self, *_args, **_kwargs):
            return []

    service = MathSystemsService()
    record = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {
                        "row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 5,
                    }
                ],
                "class_level_text": "Wizard 5",
            },
            "stats": {
                "max_hp": 25,
                "armor_class": 12,
                "proficiency_bonus": 3,
                "ability_scores": {
                    "str": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 20, "modifier": 5, "save_bonus": 8},
                    "wis": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "spellcasting": {
                "spellcasting_class": "Wizard",
                "spellcasting_ability": "Intelligence",
                "spell_save_dc": None,
                "spell_attack_bonus": None,
                "class_rows": [
                    {
                        "class_row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 5,
                        "spellcasting_ability": "Intelligence",
                        "spell_save_dc": None,
                        "spell_attack_bonus": None,
                        "spell_mode": "wizard",
                    }
                ],
                "slot_progression": [{"level": 1, "max_slots": 4}],
                "spells": [],
            },
            "equipment_catalog": [
                {
                    "id": "math-focus",
                    "name": "Math Focus",
                    "is_equipped": True,
                    "campaign_item_mechanics_version": "1",
                    "campaign_item_mechanics_review_status": "approved",
                    "item_use_actions": [
                        {
                            "id": "math-focus-burst",
                            "kind": "spell_slot_item_attack",
                            "label": "Math Focus Burst",
                            "requires_equipped": True,
                            "slot_cost": {
                                "lane": "spellcasting",
                                "allowed_levels": [1],
                            },
                            "choices": [
                                {
                                    "id": "burst",
                                    "label": "Burst",
                                    "support_state": "modeled",
                                    "save": {
                                        "ability": "int",
                                        "dc_source": "character_spell_save_dc",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        state={
            "vitals": {"current_hp": 25, "temp_hp": 0},
            "spell_slots": [{"level": 1, "used": 0}],
            "resources": [],
            "inventory": [
                {
                    "id": "math-focus",
                    "catalog_ref": "math-focus",
                    "name": "Math Focus",
                    "quantity": 1,
                    "is_equipped": True,
                }
            ],
            "currency": {},
            "notes": {},
        },
    )
    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[],
    )
    assert full["item_use_actions"][0]["choices"][0]["save"]["dc"] == 16

    def fail_full_spell_work(*_args, **_kwargs):
        pytest.fail("equipment math-only projection rebuilt spell state or a spell catalog")

    monkeypatch.setattr(
        derivation_module,
        "_derive_definition_spellcasting",
        fail_full_spell_work,
    )
    monkeypatch.setattr(
        mechanics_module,
        "_build_scoped_spell_catalog",
        fail_full_spell_work,
    )
    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section="equipment",
        systems_service=service,
        campaign_page_records=[],
    )

    assert scoped["item_use_actions"][0]["choices"][0]["save"] == {
        "ability": "int",
        "dc_source": "character_spell_save_dc",
        "dc": 16,
        "label": "INT save DC 16",
    }


def test_spellcasting_math_only_fills_single_and_multiclass_rows_and_preserves_deltas_and_transients():
    single_definition = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {"row_id": "class-row-1", "class_name": "Wizard", "level": 5}
                ]
            },
            "stats": {
                "proficiency_bonus": 3,
                "ability_scores": {
                    "int": {"score": 20, "modifier": 5, "save_bonus": 8}
                },
            },
            "spellcasting": {
                "spellcasting_ability": "Intelligence",
                "spell_save_dc": None,
                "spell_attack_bonus": None,
                "class_rows": [
                    {
                        "class_row_id": "class-row-1",
                        "spellcasting_ability": "",
                        "spell_save_dc": None,
                        "spell_attack_bonus": None,
                    }
                ],
            },
        }
    ).definition
    single = derivation_module._derive_definition_spellcasting_math(
        single_definition,
        ability_scores={"int": 20},
        proficiency_bonus=3,
        transient_spellcasting_adjustments={
            "save_dc": 3,
            "attack_bonus": 2,
        },
    )
    assert (single["spell_save_dc"], single["spell_attack_bonus"]) == (19, 10)
    assert (
        single["class_rows"][0]["spell_save_dc"],
        single["class_rows"][0]["spell_attack_bonus"],
    ) == (19, 10)

    multiclass_definition = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {"row_id": "wizard-row", "class_name": "Wizard", "level": 3},
                    {"row_id": "cleric-row", "class_name": "Cleric", "level": 2},
                ]
            },
            "stats": {
                "proficiency_bonus": 2,
                "ability_scores": {
                    "int": {"score": 14, "modifier": 2, "save_bonus": 4},
                    "wis": {"score": 16, "modifier": 3, "save_bonus": 5},
                },
            },
            "spellcasting": {
                "spellcasting_ability": "",
                "spell_save_dc": None,
                "spell_attack_bonus": None,
                "class_rows": [
                    {
                        "class_row_id": "wizard-row",
                        "spellcasting_ability": "Intelligence",
                        "spell_save_dc": None,
                        "spell_attack_bonus": None,
                    },
                    {
                        "class_row_id": "cleric-row",
                        "spellcasting_ability": "Wisdom",
                        "spell_save_dc": 13,
                        "spell_attack_bonus": 5,
                    },
                ],
            },
        }
    ).definition
    multiclass = derivation_module._derive_definition_spellcasting_math(
        multiclass_definition,
        ability_scores={"int": 20, "wis": 18},
        proficiency_bonus=3,
        transient_spellcasting_adjustments={
            "save_dc": 3,
            "attack_bonus": 2,
        },
    )
    assert multiclass["spell_save_dc"] is None
    assert multiclass["spell_attack_bonus"] is None
    assert [
        (row["spell_save_dc"], row["spell_attack_bonus"])
        for row in multiclass["class_rows"]
    ] == [(19, 10), (18, 9)]


def test_scoped_common_headers_resolve_only_targeted_legacy_profile_entries(
    monkeypatch,
):
    wizard = _systems_entry(
        "class",
        "wizard-phb",
        "Wizard",
        metadata={"hit_die": "d6"},
    )
    fighter = _systems_entry(
        "class",
        "fighter-phb",
        "Fighter",
        metadata={"hit_die": "d10"},
    )
    evocation = _systems_entry(
        "subclass",
        "school-of-evocation-phb",
        "School of Evocation",
        metadata={"class_name": "Wizard", "class_source": "PHB"},
    )
    champion = _systems_entry(
        "subclass",
        "champion-phb",
        "Champion",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    human = _systems_entry("race", "human-phb", "Human")
    sage = _systems_entry("background", "sage-phb", "Sage")
    entries = (wizard, fighter, evocation, champion, human, sage)

    class ProfileSystemsService:
        def __init__(self):
            self.catalog_calls: list[str] = []
            self.search_calls: list[tuple[str, str, int]] = []
            self.direct_calls: list[tuple[str, str]] = []

        def list_enabled_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            entry_type=None,
            query="",
            limit=None,
        ):
            del query, limit
            self.catalog_calls.append(str(entry_type or ""))
            return [entry for entry in entries if entry.entry_type == entry_type]

        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            self.direct_calls.append(("entry_key", str(entry_key)))
            return next((entry for entry in entries if entry.entry_key == entry_key), None)

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            self.direct_calls.append(("slug", str(entry_slug)))
            return next((entry for entry in entries if entry.slug == entry_slug), None)

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry in entries

        def search_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            query,
            entry_type=None,
            limit=100,
            **_kwargs,
        ):
            self.search_calls.append((str(entry_type or ""), str(query), int(limit)))
            return [
                entry
                for entry in entries
                if entry.entry_type == entry_type
                and entry.title.casefold() == str(query).casefold()
            ][:limit]

        def build_character_sheet_entry_body_html(self, *_args, **_kwargs):
            pytest.fail("common profile-link resolution read a Systems body")

        def build_class_feature_progression_for_class_entry(self, *_args, **_kwargs):
            return []

        def build_subclass_feature_progression_for_subclass_entry(self, *_args, **_kwargs):
            return []

    service = ProfileSystemsService()
    record = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {
                        "row_id": "class-row-1",
                        "class_name": "Wizard",
                        "subclass_name": "School of Evocation",
                        "level": 5,
                    },
                    {
                        "row_id": "class-row-2",
                        "class_name": "Fighter",
                        "subclass_name": "Champion",
                        "level": 2,
                    },
                ],
                "class_level_text": "Wizard 5 / Fighter 2",
                "species": "Human",
                "background": "Sage",
            }
        }
    )
    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[],
    )
    assert [segment["text"] for segment in full["header_segments"]] == [
        "Wizard 5 / Fighter 2",
        "School of Evocation",
        "Human",
        "Sage",
    ]
    assert all(segment["href"] for segment in full["header_segments"])

    def fail_common_static_bundle(*_args, **_kwargs):
        pytest.fail("scoped profile-link resolution rebuilt the campaign-wide static bundle")

    monkeypatch.setattr(
        builder_module,
        "_build_common_builder_static_bundle",
        fail_common_static_bundle,
    )
    for section, dependency in DND_SECTION_DEPENDENCY_MANIFEST.items():
        prior_catalog_calls = len(service.catalog_calls)
        scoped = present_dnd_character_section(
            _campaign(),
            record,
            section=section,
            systems_service=service,
            campaign_page_records=[],
        )
        assert scoped["header_segments"] == full["header_segments"], section
        new_catalog_calls = service.catalog_calls[prior_catalog_calls:]
        assert set(new_catalog_calls).issubset(
            {
                {"items": "item", "spells": "spell"}[catalog]
                for catalog in dependency.catalog_components
            }
        ), section

    normalized = builder_module.normalize_definition_to_native_model(
        record.definition,
        derivation_components=frozenset({"sheet_entries"}),
        item_catalog=builder_module._build_item_catalog([]),
        spell_catalog=builder_module._build_spell_catalog([]),
        systems_service=service,
        campaign_page_records=[],
    )
    normalized_rows = normalized.profile["classes"]
    assert [row["systems_ref"]["slug"] for row in normalized_rows] == [
        wizard.slug,
        fighter.slug,
    ]
    assert [row["subclass_ref"]["slug"] for row in normalized_rows] == [
        evocation.slug,
        champion.slug,
    ]
    assert normalized.profile["species_ref"]["slug"] == human.slug
    assert normalized.profile["background_ref"]["slug"] == sage.slug
    assert service.search_calls
    assert all(limit <= 8 for _, _, limit in service.search_calls)


def test_targeted_profile_resolution_fails_closed_for_ambiguous_disabled_and_wrong_type_candidates():
    human_phb = _systems_entry("race", "human-phb", "Human")
    human_xge = _systems_entry(
        "race",
        "human-xge",
        "Human",
        source_id="XGE",
    )
    disabled_sage = _systems_entry("background", "sage-phb", "Sage")
    wrong_type = _systems_entry("race", "wizard-race", "Wizard")
    entries = (human_phb, human_xge, disabled_sage, wrong_type)

    class EdgeSystemsService:
        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return next((entry for entry in entries if entry.entry_key == entry_key), None)

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            return next((entry for entry in entries if entry.slug == entry_slug), None)

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry.entry_key != disabled_sage.entry_key

        def search_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            query,
            entry_type=None,
            limit=100,
            **_kwargs,
        ):
            return [
                entry
                for entry in entries
                if entry.entry_type == entry_type
                and entry.title.casefold() == str(query).casefold()
            ][:limit]

    definition = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {
                        "row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 3,
                        "systems_ref": {
                            "entry_key": wrong_type.entry_key,
                            "title": "Wizard",
                        },
                    }
                ],
                "species": "Human",
                "background": "Sage",
            }
        }
    ).definition
    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        definition,
        systems_service=EdgeSystemsService(),
        campaign_page_records=[],
    )

    assert resolved["selected_class"] is None
    assert resolved["selected_class_rows"][0]["selected_class"] is None
    assert resolved["selected_species"] is None
    assert resolved["selected_background"] is None


def test_targeted_profile_resolution_fails_closed_when_exact_title_search_saturates():
    exact_human = _systems_entry("race", "human-phb", "Human")
    saturated_results = [
        exact_human,
        *[
            _systems_entry(
                "race",
                f"human-variant-{index}",
                f"Human Variant {index}",
            )
            for index in range(1, 8)
        ],
    ]

    class SaturatedSystemsService:
        def search_entries_for_campaign(self, *_args, limit=100, **_kwargs):
            return saturated_results[:limit]

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return True

    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        _record(definition_overrides={"profile": {"species": "Human"}}).definition,
        systems_service=SaturatedSystemsService(),
        campaign_page_records=[],
    )

    assert resolved["selected_species"] is None


def test_targeted_profile_resolution_uses_source_filter_before_bounded_title_decision():
    human_phb = _systems_entry("race", "human-phb", "Human")
    human_rows = [
        human_phb,
        *[
            _systems_entry(
                "race",
                f"human-source-{index}",
                "Human",
                source_id=f"SRC{index}",
            )
            for index in range(1, 8)
        ],
    ]

    class SaturatedSystemsService:
        def __init__(self, entries):
            self.entries = list(entries)
            self.search_calls: list[tuple[str, ...]] = []

        def search_entries_for_campaign(
            self,
            *_args,
            include_source_ids=None,
            limit=100,
            **_kwargs,
        ):
            source_ids = tuple(include_source_ids or ())
            self.search_calls.append(source_ids)
            entries = self.entries
            if include_source_ids is not None:
                allowed = {
                    str(source_id or "").strip().upper()
                    for source_id in include_source_ids
                }
                entries = [
                    entry
                    for entry in entries
                    if str(entry.source_id or "").strip().upper() in allowed
                ]
            return entries[:limit]

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return True

    definition = _record(
        definition_overrides={
            "profile": {
                "species": "Human",
                "species_ref": {
                    "source_id": "PHB",
                    "title": "Human",
                },
            }
        }
    ).definition
    service = SaturatedSystemsService(human_rows)
    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        definition,
        systems_service=service,
        campaign_page_records=[],
    )

    assert resolved["selected_species"] == human_phb
    assert service.search_calls == [("PHB",)]


def test_targeted_profile_resolution_fails_closed_when_source_filtered_search_saturates():
    human_phb = _systems_entry("race", "human-phb", "Human")
    hidden_duplicate = _systems_entry(
        "race",
        "human-phb-hidden-duplicate",
        "Human",
    )
    source_rows = [
        human_phb,
        *[
            _systems_entry(
                "race",
                f"human-phb-variant-{index}",
                f"Human Variant {index}",
            )
            for index in range(1, 8)
        ],
        hidden_duplicate,
    ]

    class SourceSaturatedSystemsService:
        def search_entries_for_campaign(
            self,
            *_args,
            include_source_ids=None,
            limit=100,
            **_kwargs,
        ):
            assert include_source_ids == ["PHB"]
            return source_rows[:limit]

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return True

    definition = _record(
        definition_overrides={
            "profile": {
                "species": "Human",
                "species_ref": {
                    "source_id": "PHB",
                    "title": "Human",
                },
            }
        }
    ).definition
    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        definition,
        systems_service=SourceSaturatedSystemsService(),
        campaign_page_records=[],
    )

    assert resolved["selected_species"] is None


def test_targeted_profile_resolution_falls_back_without_source_filter_and_keeps_saturation_closed():
    human_phb = _systems_entry("race", "human-phb", "Human")
    cross_source_rows = [
        human_phb,
        *[
            _systems_entry(
                "race",
                f"human-source-{index}",
                "Human",
                source_id=f"SRC{index}",
            )
            for index in range(1, 8)
        ],
    ]

    class LegacySearchSystemsService:
        def __init__(self):
            self.search_calls = 0

        def search_entries_for_campaign(
            self,
            *_args,
            query,
            entry_type=None,
            limit=100,
        ):
            del query, entry_type
            self.search_calls += 1
            return cross_source_rows[:limit]

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return True

    definition = _record(
        definition_overrides={
            "profile": {
                "species": "Human",
                "species_ref": {
                    "source_id": "PHB",
                    "title": "Human",
                },
            }
        }
    ).definition
    service = LegacySearchSystemsService()
    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        definition,
        systems_service=service,
        campaign_page_records=[],
    )

    assert resolved["selected_species"] is None
    assert service.search_calls == 1


def test_targeted_profile_resolution_skips_title_search_when_explicit_slug_resolves():
    human_phb = _systems_entry("race", "human-phb", "Human")

    class DirectSlugSystemsService:
        def get_entry_for_campaign(self, *_args, **_kwargs):
            return None

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            return human_phb if entry_slug == human_phb.slug else None

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry == human_phb

        def search_entries_for_campaign(self, *_args, **_kwargs):
            pytest.fail("a compatible explicit slug triggered a redundant title search")

    definition = _record(
        definition_overrides={
            "profile": {
                "species": "Human",
                "species_ref": _systems_ref(human_phb),
            }
        }
    ).definition
    resolved = builder_module._resolve_definition_targeted_sheet_entries(
        definition,
        systems_service=DirectSlugSystemsService(),
        campaign_page_records=[],
    )

    assert resolved["selected_species"] == human_phb


@pytest.mark.parametrize("lookup_kind", ("entry_key", "slug", "search"))
def test_targeted_item_entry_rejects_disabled_candidates_from_every_lookup_path(
    lookup_kind,
):
    disabled_item = _systems_entry(
        "item",
        "disabled-focus",
        "Disabled Focus",
        source_id="CUSTOM-PRESENTER",
    )

    class DisabledItemSystemsService:
        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            if lookup_kind == "entry_key" and entry_key == disabled_item.entry_key:
                return disabled_item
            return None

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            if lookup_kind == "slug" and entry_slug == disabled_item.slug:
                return disabled_item
            return None

        def search_entries_for_campaign(self, *_args, **_kwargs):
            return [disabled_item] if lookup_kind == "search" else []

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            assert entry == disabled_item
            return False

    systems_ref = {
        "entry_key": disabled_item.entry_key if lookup_kind == "entry_key" else "",
        "slug": disabled_item.slug if lookup_kind == "slug" else "",
        "title": disabled_item.title,
    }
    resolved = catalogs_module._targeted_item_entry(
        DisabledItemSystemsService(),
        "presenter-contract",
        {"name": disabled_item.title, "systems_ref": systems_ref},
    )

    assert resolved is None


def test_targeted_item_entry_keeps_campaign_scoped_get_contract_without_optional_enabled_hook():
    enabled_item = _systems_entry(
        "item",
        "enabled-focus",
        "Enabled Focus",
        source_id="CUSTOM-PRESENTER",
    )

    class CampaignScopedGetSystemsService:
        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return enabled_item if entry_key == enabled_item.entry_key else None

        def get_entry_by_slug_for_campaign(self, *_args, **_kwargs):
            pytest.fail("a valid entry-key lookup triggered a redundant slug lookup")

        def search_entries_for_campaign(self, *_args, **_kwargs):
            pytest.fail("a valid entry-key lookup triggered a redundant title search")

    resolved = catalogs_module._targeted_item_entry(
        CampaignScopedGetSystemsService(),
        "presenter-contract",
        {
            "name": enabled_item.title,
            "systems_ref": {
                "entry_key": enabled_item.entry_key,
                "title": enabled_item.title,
            },
        },
    )

    assert resolved == enabled_item


def test_targeted_item_entry_fails_closed_when_exact_title_search_saturates():
    exact_item = _systems_entry(
        "item",
        "bounded-focus",
        "Bounded Focus",
        source_id="CUSTOM-PRESENTER",
    )
    hidden_duplicate = _systems_entry(
        "item",
        "bounded-focus-hidden-duplicate",
        "Bounded Focus",
        source_id="CUSTOM-PRESENTER",
    )
    search_rows = [
        exact_item,
        *[
            _systems_entry(
                "item",
                f"bounded-focus-variant-{index}",
                f"Bounded Focus Variant {index}",
                source_id="CUSTOM-PRESENTER",
            )
            for index in range(1, 8)
        ],
        hidden_duplicate,
    ]

    class SaturatedItemSystemsService:
        def search_entries_for_campaign(self, *_args, limit=100, **_kwargs):
            return search_rows[:limit]

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return True

    resolved = catalogs_module._targeted_item_entry(
        SaturatedItemSystemsService(),
        "presenter-contract",
        {"name": exact_item.title},
    )

    assert resolved is None


def test_scoped_quick_ignores_disabled_direct_item_and_matches_full_without_catalog_work():
    disabled_item = _systems_entry(
        "item",
        "disabled-ward",
        "Disabled Ward",
        source_id="CUSTOM-PRESENTER",
        metadata=build_campaign_item_mechanics_metadata(
            title="Disabled Ward",
            body_markdown="*Wondrous item, rare*",
            explicit_mechanics={
                "defensive_rules": [
                    {
                        "id": "item:disabled-ward",
                        "title": "Disabled Ward",
                        "condition": "While equipped.",
                        "effects": [
                            {
                                "kind": "resistance",
                                "label": "Disabled ward",
                                "summary": "This disabled entry must not apply.",
                            }
                        ],
                    }
                ]
            },
            source_page_ref="items/disabled-ward",
            review_status="approved",
        ),
    )

    class DisabledCatalogSystemsService:
        def __init__(self):
            self.catalog_calls: list[str] = []

        def list_enabled_entries_for_campaign(
            self,
            *_args,
            entry_type=None,
            **_kwargs,
        ):
            self.catalog_calls.append(str(entry_type or ""))
            return []

        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return disabled_item if entry_key == disabled_item.entry_key else None

        def search_entries_for_campaign(
            self,
            *_args,
            query,
            entry_type=None,
            **_kwargs,
        ):
            return (
                [disabled_item]
                if entry_type == "item" and query == disabled_item.title
                else []
            )

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry.entry_key != disabled_item.entry_key

        def build_character_sheet_entry_body_html(self, *_args, **_kwargs):
            pytest.fail("disabled item support read a Systems body")

    service = DisabledCatalogSystemsService()
    record = _record(
        definition_overrides={
            "equipment_catalog": [
                {
                    "id": "disabled-ward",
                    "name": "Disabled Ward",
                    "is_equipped": True,
                    "systems_ref": {
                        "entry_key": disabled_item.entry_key,
                        "title": disabled_item.title,
                    },
                }
            ]
        },
        state={
            "vitals": {"current_hp": 6, "temp_hp": 0},
            "inventory": [
                {
                    "id": "disabled-ward",
                    "catalog_ref": "disabled-ward",
                    "name": "Disabled Ward",
                    "quantity": 1,
                    "is_equipped": True,
                }
            ],
            "resources": [],
            "spell_slots": [],
            "currency": {},
            "notes": {},
        },
    )
    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[],
    )
    assert full["defensive_rules"] == []
    service.catalog_calls.clear()

    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section="quick",
        systems_service=service,
        campaign_page_records=[],
    )

    assert {
        field: scoped[field]
        for field in scoped["projection_fields"]
    } == {
        field: full[field]
        for field in scoped["projection_fields"]
    }
    assert scoped["defensive_rules"] == []
    assert service.catalog_calls == []


def test_targeted_profile_resolution_preserves_explicit_campaign_page_priority(
    monkeypatch,
):
    preferred_species = _campaign_page_record(
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
            }
        },
    )
    duplicate_title_species = _campaign_page_record(
        "species/sea-blessed-legacy",
        "Sea-Blessed",
        section="Mechanics",
        subsection="Species",
        metadata={
            "character_option": {
                "kind": "species",
                "name": "Sea-Blessed",
                "size": ["M"],
                "speed": 30,
            }
        },
    )
    background = _campaign_page_record(
        "backgrounds/harbor-initiate",
        "Harbor Initiate",
        section="Mechanics",
        subsection="Backgrounds",
        metadata={
            "character_option": {
                "kind": "background",
                "name": "Harbor Initiate",
            }
        },
    )
    page_records = [preferred_species, duplicate_title_species, background]

    class PageOnlySystemsService:
        def get_entry_for_campaign(self, *_args, **_kwargs):
            return None

        def get_entry_by_slug_for_campaign(self, *_args, **_kwargs):
            return None

        def search_entries_for_campaign(self, *_args, **_kwargs):
            return []

        def is_entry_enabled_for_campaign(self, *_args, **_kwargs):
            return False

        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            pytest.fail("scoped campaign profile links enumerated a Systems catalog")

    service = PageOnlySystemsService()
    record = _record(
        definition_overrides={
            "profile": {
                "species": "Sea-Blessed",
                "species_page_ref": preferred_species.page_ref,
                "background": "Harbor Initiate",
                "background_page_ref": background.page_ref,
            }
        }
    )

    def fail_common_static_bundle(*_args, **_kwargs):
        pytest.fail("scoped campaign profile links rebuilt the common static bundle")

    monkeypatch.setattr(
        builder_module,
        "_build_common_builder_static_bundle",
        fail_common_static_bundle,
    )
    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section="controls",
        systems_service=service,
        campaign_page_records=page_records,
    )
    headers = {segment["text"]: segment["href"] for segment in scoped["header_segments"]}
    assert headers["Sea-Blessed"].endswith("/pages/species/sea-blessed")
    assert headers["Harbor Initiate"].endswith(
        "/pages/backgrounds/harbor-initiate"
    )

    normalized = builder_module.normalize_definition_to_native_model(
        record.definition,
        derivation_components=frozenset({"sheet_entries"}),
        item_catalog=builder_module._build_item_catalog([]),
        spell_catalog=builder_module._build_spell_catalog([]),
        systems_service=service,
        campaign_page_records=page_records,
    )
    assert normalized.profile["species_page_ref"] == preferred_species.page_ref
    assert not normalized.profile.get("species_ref")
    assert normalized.profile["background_page_ref"] == background.page_ref
    assert not normalized.profile.get("background_ref")


def test_scoped_dnd_item_effect_families_match_full_without_unrelated_catalog_enumeration(
    monkeypatch,
):
    granted_spell = _systems_entry(
        "spell",
        "phb-spell-granted-spell",
        "Granted Spell",
        metadata={"level": 1},
    )
    supported_item = _systems_entry(
        "item",
        "custom-presenter-effect-focus",
        "Effect Focus",
        source_id="CUSTOM-PRESENTER",
        metadata=build_campaign_item_mechanics_metadata(
            title="Effect Focus",
            body_markdown="*Wondrous item, rare (requires attunement)*",
            explicit_mechanics={
                "ability_score_minimums": {"con": 16, "int": 20},
                "resource_template_bonuses": [{"id": "focus", "bonus": 2}],
                "spell_support": [
                    {
                        "source": {
                            "id": "spell-source:item:effect-focus",
                            "title": "Effect Focus",
                            "kind": "item",
                            "ability_key": "int",
                        },
                        "grants": {
                            "_": [
                                {
                                    "spell": "Granted Spell",
                                    "access_type": "at_will",
                                }
                            ]
                        },
                    }
                ],
                "defensive_rules": [
                    {
                        "id": "item:effect-focus:ward",
                        "title": "Effect Focus Ward",
                        "condition": "While equipped and attuned.",
                        "effects": [
                            {
                                "kind": "resistance",
                                "label": "Focus ward",
                                "summary": "You have resistance to test damage.",
                            }
                        ],
                    }
                ],
                "attack_reminder_rules": [
                    {
                        "id": "item:effect-focus:opening",
                        "title": "Effect Focus Opening",
                        "save_dc_ability_key": "int",
                        "condition": "After you hit with a weapon attack.",
                        "attack_scope": {
                            "label": "Weapon attacks",
                            "categories": ["melee weapon", "ranged weapon"],
                        },
                        "effects": [
                            {
                                "kind": "saving_throw",
                                "label": "Focus save",
                                "summary": "The target makes a save against DC {save_dc}.",
                            }
                        ],
                    }
                ],
                "item_use_actions": [
                    {
                        "id": "effect-focus-burst",
                        "kind": "spell_slot_item_attack",
                        "label": "Effect Focus Burst",
                        "requires_equipped": True,
                        "requires_attunement": True,
                        "slot_cost": {"lane": "spellcasting", "allowed_levels": [1]},
                        "choices": [
                            {
                                "id": "burst",
                                "label": "Burst",
                                "support_state": "modeled",
                                "save": {
                                    "ability": "int",
                                    "dc_source": "character_spell_save_dc",
                                },
                            }
                        ],
                    }
                ],
            },
            source_page_ref="items/effect-focus",
            review_status="approved",
        ),
    )

    class TargetedSystemsService:
        def __init__(self):
            self.full_catalog_calls: list[str] = []

        def list_enabled_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            entry_type=None,
            query="",
            limit=None,
        ):
            del query, limit
            self.full_catalog_calls.append(str(entry_type or ""))
            return {
                "item": [supported_item],
                "spell": [granted_spell],
            }.get(str(entry_type or ""), [])

        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return supported_item if entry_key == supported_item.entry_key else None

        def get_entry_by_slug_for_campaign(self, _campaign_slug, entry_slug):
            return supported_item if entry_slug == supported_item.slug else None

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry.entry_key in {supported_item.entry_key, granted_spell.entry_key}

        def build_character_sheet_entry_body_html(self, _campaign_slug, _entry):
            return ""

        def search_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            query,
            entry_type=None,
            limit=100,
            **_kwargs,
        ):
            del limit
            return [
                entry
                for entry in (supported_item, granted_spell)
                if entry.entry_type == entry_type and entry.title.casefold() == query.casefold()
            ]

    service = TargetedSystemsService()
    record = _record(
        definition_overrides={
            "profile": {
                "classes": [
                    {
                        "row_id": "class-row-1",
                        "class_name": "Wizard",
                        "level": 5,
                    }
                ],
                "class_level_text": "Wizard 5",
            },
            "stats": {
                "max_hp": 18,
                "armor_class": 12,
                "proficiency_bonus": 2,
                "ability_scores": {
                    "str": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 2},
                    "wis": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "skills": [
                {"name": "Arcana", "bonus": 2, "proficiency_level": "proficient"}
            ],
            "spellcasting": {
                "spellcasting_class": "Wizard",
                "spellcasting_ability": "Intelligence",
                "spell_save_dc": 10,
                "spell_attack_bonus": 2,
                "class_rows": [],
                "spells": [],
            },
            "features": [
                {
                    "id": "focus-feature",
                    "name": "Focus",
                    "category": "class_feature",
                    "tracker": {"id": "focus", "label": "Focus", "max": 1},
                }
            ],
            "resource_templates": [
                {"id": "focus", "label": "Focus", "max": 1, "initial_current": 1}
            ],
            "equipment_catalog": [
                {
                    "id": "effect-focus",
                    "name": "Effect Focus",
                    "page_ref": "items/effect-focus",
                    "is_equipped": True,
                    "is_attuned": True,
                    "systems_ref": _systems_ref(supported_item),
                }
            ],
        },
        state={
            "vitals": {"current_hp": 18, "temp_hp": 0},
            "resources": [{"id": "focus", "label": "Focus", "current": 1, "max": 1}],
            "spell_slots": [{"level": 1, "used": 0}],
            "inventory": [
                {
                    "id": "effect-focus",
                    "catalog_ref": "effect-focus",
                    "name": "Effect Focus",
                    "quantity": 1,
                    "is_equipped": True,
                    "is_attuned": True,
                }
            ],
            "currency": {},
            "notes": {},
        },
    )
    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[],
    )
    full_abilities = {row["key"]: row for row in full["abilities"]}
    assert full_abilities["con"]["score"] == 16
    assert full_abilities["int"]["score"] == 20
    assert next(row for row in full["resources"] if row["id"] == "focus")["max"] == 3
    assert [
        spell["name"]
        for row in full["spellcasting"]["row_sections"]
        for spell in row["spells"]
    ] == ["Granted Spell"]
    assert [rule["title"] for rule in full["defensive_rules"]] == [
        "Effect Focus Ward"
    ]
    assert [rule["title"] for rule in full["attack_reminders"]] == [
        "Effect Focus Opening"
    ]
    assert [action["label"] for action in full["item_use_actions"]] == [
        "Effect Focus Burst"
    ]
    assert full["item_use_actions"][0]["choices"][0]["save"]["dc"] == 16

    def fail_common_static_bundle(*_args, **_kwargs):
        pytest.fail("scoped presentation rebuilt the campaign-wide static bundle")

    monkeypatch.setattr(
        builder_module,
        "_build_common_builder_static_bundle",
        fail_common_static_bundle,
    )
    full_catalog_call_count = len(service.full_catalog_calls)

    for section in (
        "overview",
        "quick",
        "spells",
        "resources",
        "features",
        "equipment",
        "inventory",
        "abilities_skills",
        "personal",
        "portrait",
        "notes",
        "controls",
    ):
        scoped = present_dnd_character_section(
            _campaign(),
            record,
            section=section,
            systems_service=service,
            campaign_page_records=[],
        )
        dependency = DND_SECTION_DEPENDENCY_MANIFEST[section]
        projection_fields = tuple(
            dict.fromkeys((*DND_COMMON_PRESENTATION_FIELDS, *dependency.output_fields))
        )
        _assert_scoped_projection_parity(scoped, full, dependency)
        if section == "equipment":
            assert scoped["item_use_actions"][0]["choices"][0]["save"]["dc"] == 16
        new_catalog_calls = service.full_catalog_calls[full_catalog_call_count:]
        allowed_entry_types = {
            {"items": "item", "spells": "spell"}[catalog]
            for catalog in dependency.catalog_components
        }
        assert set(new_catalog_calls).issubset(allowed_entry_types), section
        full_catalog_call_count = len(service.full_catalog_calls)

    counts = present_dnd_character_section_counts(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[],
    )
    assert counts["spells"] == 1
    assert service.full_catalog_calls[full_catalog_call_count:] == []


def test_scoped_quick_uses_only_exact_carried_campaign_item_body_support():
    body_reads: list[str] = []

    class ItemPageRecord:
        def __init__(self, page_ref: str, title: str, body: str, *, forbid_body=False):
            self.page_ref = page_ref
            self.page = SimpleNamespace(section="Items", title=title)
            self.metadata = {}
            self._body = body
            self._forbid_body = forbid_body

        @property
        def body_markdown(self):
            if self._forbid_body:
                pytest.fail("scoped quick read an unrelated campaign item body")
            body_reads.append(self.page_ref)
            return self._body

    carried_page = ItemPageRecord(
        "items/body-blade",
        "Body Blade",
        (
            "*Weapon (longsword), rare (requires attunement)*\n\n"
            "You gain a +2 bonus to attack and damage rolls made with this weapon."
        ),
    )
    unrelated_page = ItemPageRecord(
        "items/unrelated",
        "Unrelated Item",
        "*Wondrous item, common*",
        forbid_body=True,
    )

    class EmptyCatalogService:
        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            return []

    service = EmptyCatalogService()
    record = _record(
        definition_overrides={
            "stats": {
                "max_hp": 12,
                "armor_class": 10,
                "proficiency_bonus": 2,
                "ability_scores": {
                    "str": {"score": 16, "modifier": 3, "save_bonus": 3},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "wis": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "proficiencies": {"weapons": ["Martial Weapons", "Longswords"]},
            "equipment_catalog": [
                {
                    "id": "body-blade",
                    "name": "Body Blade",
                    "page_ref": "items/body-blade",
                    "is_equipped": True,
                    "is_attuned": True,
                }
            ],
        },
        state={
            "vitals": {"current_hp": 12, "temp_hp": 0},
            "inventory": [
                {
                    "id": "body-blade",
                    "catalog_ref": "body-blade",
                    "name": "Body Blade",
                    "quantity": 1,
                    "is_equipped": True,
                    "is_attuned": True,
                }
            ],
            "resources": [],
            "spell_slots": [],
            "currency": {},
            "notes": {},
        },
    )
    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[carried_page],
    )
    body_reads.clear()

    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section="quick",
        systems_service=service,
        campaign_page_records=[carried_page, unrelated_page],
    )

    assert scoped["attacks"] == full["attacks"]
    assert scoped["attacks"]
    assert scoped["attacks"][0]["name"] == "Body Blade"
    assert body_reads == ["items/body-blade"]


def test_scoped_quick_preserves_body_derived_hidden_attacks_for_stowed_item():
    stowed_page = SimpleNamespace(
        page_ref="items/stowed-blade",
        page=SimpleNamespace(section="Items", title="Stowed Blade"),
        metadata={
            "ability_score_minimums": {"int": 20},
            "resource_template_bonuses": [{"id": "focus", "bonus": 2}],
            "defensive_rules": [
                {
                    "id": "stowed-blade-ward",
                    "title": "Stowed Blade Ward",
                    "effects": [
                        {
                            "kind": "resistance",
                            "label": "Stowed ward",
                            "summary": "This inactive effect must not apply.",
                        }
                    ],
                }
            ],
        },
        body_markdown=(
            "*Weapon (longsword), rare*\n\n"
            "You gain a +2 bonus to attack and damage rolls made with this weapon."
        ),
    )

    class EmptyCatalogService:
        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            return []

    service = EmptyCatalogService()
    record = _record(
        definition_overrides={
            "stats": {
                "max_hp": 12,
                "armor_class": 10,
                "proficiency_bonus": 2,
                "ability_scores": {
                    "str": {"score": 16, "modifier": 3, "save_bonus": 3},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "wis": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "proficiencies": {"weapons": ["Martial Weapons", "Longswords"]},
            "resource_templates": [
                {"id": "focus", "label": "Focus", "max": 1, "initial_current": 1}
            ],
            "equipment_catalog": [
                {
                    "id": "stowed-blade",
                    "name": "Stowed Blade",
                    "page_ref": "items/stowed-blade",
                    "is_equipped": False,
                    "is_attuned": False,
                }
            ],
        },
        state={
            "vitals": {"current_hp": 12, "temp_hp": 0},
            "inventory": [
                {
                    "id": "stowed-blade",
                    "catalog_ref": "stowed-blade",
                    "name": "Stowed Blade",
                    "quantity": 1,
                    "is_equipped": False,
                    "is_attuned": False,
                }
            ],
            "resources": [{"id": "focus", "label": "Focus", "current": 1, "max": 1}],
            "spell_slots": [],
            "currency": {},
            "notes": {},
        },
    )

    full = present_character_detail(
        _campaign(),
        record,
        systems_service=service,
        campaign_page_records=[stowed_page],
    )
    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section="quick",
        systems_service=service,
        campaign_page_records=[stowed_page],
    )

    assert full["attacks"] == []
    assert [row["name"] for row in full["hidden_attacks"]] == [
        "Stowed Blade",
        "Stowed Blade (two-handed)",
    ]
    assert scoped["hidden_attacks"] == full["hidden_attacks"]
    assert next(row for row in full["abilities"] if row["key"] == "int")["score"] == 10
    assert next(
        row["value"]
        for group in scoped["overview_stat_rows"]
        for row in group
        if row["label"] == "Passive Investigation"
    ) == next(
        row["value"]
        for group in full["overview_stat_rows"]
        for row in group
        if row["label"] == "Passive Investigation"
    )
    assert next(row for row in scoped["resources"] if row["id"] == "focus")["max"] == 1
    assert scoped["defensive_rules"] == []


@pytest.mark.parametrize(
    "section",
    ("overview", "resources", "spells", "features", "abilities_skills"),
)
def test_non_attack_scopes_do_not_resolve_stowed_item_support(section):
    class StowedPage:
        page_ref = "items/stowed-blade"
        page = SimpleNamespace(section="Items", title="Stowed Blade")
        metadata = {}

        @property
        def body_markdown(self):
            pytest.fail(f"{section} resolved inactive carried item support")

    class EmptyCatalogService:
        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            return []

    record = _record(
        definition_overrides={
            "equipment_catalog": [
                {
                    "id": "stowed-blade",
                    "name": "Stowed Blade",
                    "page_ref": "items/stowed-blade",
                    "is_equipped": False,
                    "is_attuned": False,
                }
            ],
        },
        state={
            "vitals": {"current_hp": 6, "temp_hp": 0},
            "inventory": [
                {
                    "id": "stowed-blade",
                    "catalog_ref": "stowed-blade",
                    "name": "Stowed Blade",
                    "quantity": 1,
                    "is_equipped": False,
                    "is_attuned": False,
                }
            ],
            "resources": [],
            "spell_slots": [],
            "currency": {},
            "notes": {},
        },
    )

    scoped = present_dnd_character_section(
        _campaign(),
        record,
        section=section,
        systems_service=EmptyCatalogService(),
        campaign_page_records=[StowedPage()],
    )

    assert scoped["presentation_scope"] == section


def test_scoped_common_fields_exclude_projection_warnings_and_non_avatar_scope_skips_transient_failure(
    monkeypatch,
):
    record = _dnd_record()
    record.state_record.state["divine_avatar"] = {"active_form_key": "mourning"}
    transient_calls: list[str] = []

    def active_transient_effects(*_args, **_kwargs):
        transient_calls.append("active")
        return [{"type": "ability_score", "ability": "wisdom", "value": 2}]

    def fail_transient_projection(*_args, **_kwargs):
        transient_calls.append("project")
        raise ValueError("failure-injected avatar projection")

    monkeypatch.setattr(
        mechanics_module,
        "active_divine_avatar_transient_effects",
        active_transient_effects,
    )
    monkeypatch.setattr(
        mechanics_module,
        "project_definition_with_transient_effects",
        fail_transient_projection,
    )

    full = present_character_detail(_campaign(), record)
    assert transient_calls == ["active", "project"]
    assert full["projection_warnings"] == [
        {
            "code": "transient_mechanics_projection_failed",
            "message": "failure-injected avatar projection",
        }
    ]

    transient_calls.clear()
    scoped = present_dnd_character_section(_campaign(), record, section="notes")

    assert transient_calls == []
    assert "projection_warnings" not in DND_COMMON_PRESENTATION_FIELDS
    assert "projection_warnings" not in scoped
    assert "projection_warnings" not in scoped["projection_fields"]
    assert {field: scoped[field] for field in scoped["projection_fields"]} == {
        field: full[field] for field in scoped["projection_fields"]
    }


@pytest.mark.parametrize("section", ("personal", "portrait", "notes", "controls"))
def test_text_only_scopes_skip_targeted_item_resolution(section, monkeypatch):
    def fail_targeted_support(*_args, **_kwargs):
        pytest.fail(f"{section} resolved unrelated item support")

    class NoItemLookupService:
        def get_entry_for_campaign(self, *_args, **_kwargs):
            return None

        def get_entry_by_slug_for_campaign(self, *_args, **_kwargs):
            return None

        def search_entries_for_campaign(self, *_args, entry_type=None, **_kwargs):
            if entry_type == "item":
                pytest.fail(f"{section} performed an item title search")
            return []

        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            pytest.fail(f"{section} enumerated a campaign catalog")

    monkeypatch.setattr(
        mechanics_module,
        "_build_targeted_item_support_catalog",
        fail_targeted_support,
    )

    scoped = present_dnd_character_section(
        _campaign(),
        _dnd_record(),
        section=section,
        systems_service=NoItemLookupService(),
        campaign_page_records=[],
    )

    assert scoped["projection_fields"] == tuple(
        dict.fromkeys(
            (
                *DND_COMMON_PRESENTATION_FIELDS,
                *DND_SECTION_DEPENDENCY_MANIFEST[section].output_fields,
            )
        )
    )


def test_scoped_targeted_item_lookup_failure_uses_read_time_projection_fallback(
    monkeypatch,
):
    def fail_targeted_support(*_args, **_kwargs):
        raise ValueError("failure-injected targeted item lookup")

    monkeypatch.setattr(
        mechanics_module,
        "_build_targeted_item_support_catalog",
        fail_targeted_support,
    )

    projection = mechanics_module.build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_dnd_record().definition,
        state={"vitals": {"current_hp": 6, "temp_hp": 0}},
        systems_service=object(),
        components=frozenset(),
        catalog_components=frozenset(),
        derivation_components=frozenset({"item_ability_minimums"}),
    )

    assert projection["definition"].character_slug == "contract-character"
    assert projection["projection_warnings"] == [
        {
            "code": "read_time_projection_failed",
            "message": "failure-injected targeted item lookup",
        }
    ]


def test_scoped_dnd_presenter_refuses_unknown_scopes_and_xianxia():
    with pytest.raises(ValueError, match="Unknown DND character presentation section"):
        present_dnd_character_section(_campaign(), _dnd_record(), section="unknown")
    with pytest.raises(ValueError, match="only for DND-5E"):
        present_dnd_character_section(
            _campaign(system="Xianxia"),
            _xianxia_record(),
            section="quick",
        )
    with pytest.raises(ValueError, match="only for DND-5E"):
        present_dnd_character_section_counts(
            _campaign(system="Xianxia"),
            _xianxia_record(),
        )


def test_scoped_dnd_results_are_detached_from_later_scoped_and_full_results():
    record = _dnd_record()
    baseline = present_dnd_character_section(_campaign(), record, section="features")
    mutated = present_dnd_character_section(_campaign(), record, section="features")

    mutated["feature_groups"][0]["entries"][0]["name"] = "mutated"
    mutated["feature_groups"][0]["entries"][0]["children"][0]["name"] = "mutated child"

    assert present_dnd_character_section(_campaign(), record, section="features") == baseline
    assert present_character_detail(_campaign(), record)["feature_groups"] == baseline["feature_groups"]


def test_scoped_dependency_matrix_skips_unselected_catalogs_state_and_linked_bodies(monkeypatch):
    record = _dnd_record()
    page_records: list[Any] = []
    normalization_calls: list[dict[str, Any]] = []
    body_calls: list[tuple[str, object]] = []
    state_calls: list[str] = []
    catalog_calls: list[str] = []

    class CatalogService:
        def list_enabled_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            entry_type=None,
            **_kwargs,
        ):
            catalog_calls.append(str(entry_type or ""))
            return []

    catalog_service = CatalogService()

    original_build_inventory_lookup = mechanics_module.build_inventory_lookup
    original_build_equipment_catalog_lookup = mechanics_module.build_equipment_catalog_lookup
    original_project_spell_slot_options = mechanics_module.project_spell_slot_options
    original_present_spell_slot_lanes = presenter_module.spell_slot_lanes_from_spellcasting

    def fake_normalize(definition, **kwargs):
        normalization_calls.append(dict(kwargs))
        return definition

    def linked_entry(*_args, **_kwargs):
        body_calls.append(("spell_entry", None))
        return SimpleNamespace(metadata={})

    def body_spy(kind):
        def capture(*_args, **kwargs):
            body_calls.append((kind, kwargs.get("campaign_page_records")))
            return f"<p>{kind}</p>"

        return capture

    def state_spy(kind, target):
        def capture(*args, **kwargs):
            state_calls.append(kind)
            return target(*args, **kwargs)

        return capture

    monkeypatch.setattr(mechanics_module, "normalize_definition_to_native_model", fake_normalize)
    monkeypatch.setattr(
        mechanics_module,
        "build_inventory_lookup",
        state_spy("item_inventory_state", original_build_inventory_lookup),
    )
    monkeypatch.setattr(
        mechanics_module,
        "build_equipment_catalog_lookup",
        state_spy("item_equipment_state", original_build_equipment_catalog_lookup),
    )
    monkeypatch.setattr(
        mechanics_module,
        "project_spell_slot_options",
        state_spy("item_action_slot_state", original_project_spell_slot_options),
    )
    monkeypatch.setattr(
        presenter_module,
        "spell_slot_lanes_from_spellcasting",
        state_spy("spell_presentation_state", original_present_spell_slot_lanes),
    )
    monkeypatch.setattr(presenter_module, "resolve_linked_systems_entry", linked_entry)
    monkeypatch.setattr(
        presenter_module,
        "resolve_spell_description_html",
        body_spy("spell_body"),
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_feature_description_html",
        body_spy("feature_body"),
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_item_description_html",
        body_spy("item_body"),
    )

    expected_bodies = {
        "overview": [],
        "quick": [],
        "spells": ["spell_entry", "spell_body", "spell_entry", "spell_body"],
        "spellcasting": ["spell_entry", "spell_body", "spell_entry", "spell_body"],
        "resources": [],
        "features": ["feature_body", "feature_body"],
        "equipment": [],
        "inventory": ["item_body"],
        "abilities_skills": [],
        "personal": [],
        "portrait": [],
        "notes": [],
        "controls": [],
    }
    expected_catalog_entry_types = {
        "overview": [],
        "quick": [],
        "spells": ["spell"],
        "spellcasting": ["spell"],
        "resources": [],
        "features": [],
        "equipment": ["item"],
        "inventory": ["item"],
        "abilities_skills": [],
        "personal": [],
        "portrait": [],
        "notes": [],
        "controls": [],
    }
    expected_state = {
        "overview": [],
        "quick": [
            "item_inventory_state",
            "item_equipment_state",
            "spell_presentation_state",
        ],
        "spells": ["spell_presentation_state"],
        "spellcasting": ["spell_presentation_state"],
        "resources": [],
        "features": ["item_inventory_state", "item_equipment_state"],
        "equipment": [
            "item_inventory_state",
            "item_equipment_state",
            "item_action_slot_state",
        ],
        "inventory": ["item_inventory_state", "item_equipment_state"],
        "abilities_skills": [],
        "personal": [],
        "portrait": [],
        "notes": [],
        "controls": [],
    }
    for section in expected_bodies:
        normalization_calls.clear()
        body_calls.clear()
        state_calls.clear()
        catalog_calls.clear()
        present_dnd_character_section(
            _campaign(),
            record,
            section=section,
            systems_service=catalog_service,
            campaign_page_records=page_records,
        )
        assert [kind for kind, _records in body_calls] == expected_bodies[section]
        assert len(normalization_calls) == 1
        assert normalization_calls[0]["item_catalog"]["entries"] == []
        assert normalization_calls[0]["spell_catalog"]["entries"] == []
        assert normalization_calls[0]["derivation_components"] == (
            DND_SECTION_DEPENDENCY_MANIFEST[section].derivation_components
        )
        assert catalog_calls == expected_catalog_entry_types[section]
        assert state_calls == expected_state[section]
        for kind, forwarded_records in body_calls:
            if kind.endswith("_body"):
                assert forwarded_records is page_records

    normalization_calls.clear()
    body_calls.clear()
    state_calls.clear()
    present_character_detail(
        _campaign(),
        record,
        systems_service=catalog_service,
        campaign_page_records=page_records,
    )
    assert "item_catalog" not in normalization_calls[0]
    assert "spell_catalog" not in normalization_calls[0]
    assert "derivation_components" not in normalization_calls[0]
    assert [kind for kind, _records in body_calls] == [
        "spell_entry",
        "spell_body",
        "spell_entry",
        "spell_body",
        "feature_body",
        "feature_body",
        "item_body",
    ]
    assert state_calls == [
        "item_inventory_state",
        "item_equipment_state",
        "item_action_slot_state",
        "spell_presentation_state",
    ]


def test_overview_scope_skips_attack_arcane_armor_and_equipment_projection(monkeypatch):
    record = _dnd_record()
    full = present_character_detail(_campaign(), record)

    def fail_unselected_work(*_args, **_kwargs):
        pytest.fail("overview executed unselected attack or equipment mechanics")

    monkeypatch.setattr(mechanics_module, "build_inventory_lookup", fail_unselected_work)
    monkeypatch.setattr(mechanics_module, "build_equipment_catalog_lookup", fail_unselected_work)
    monkeypatch.setattr(mechanics_module, "present_arcane_armor_state", fail_unselected_work)
    monkeypatch.setattr(mechanics_module, "project_attack_visibility", fail_unselected_work)
    monkeypatch.setattr(mechanics_module, "project_attack_reminders", fail_unselected_work)

    scoped = present_dnd_character_section(_campaign(), record, section="overview")

    assert {field: scoped[field] for field in scoped["projection_fields"]} == {
        field: full[field] for field in scoped["projection_fields"]
    }


def test_exact_dnd_count_projection_matches_existing_session_navigation_without_hidden_bodies(monkeypatch):
    record = _dnd_record()
    full = present_character_detail(_campaign(), record)
    full["portrait"] = {"url": "/portrait.webp"}
    equipment_state_manager = {
        "rows": [{"id": "rope"}, {"id": "ink"}],
    }
    labels = {
        "overview": "At a Glance",
        "spells": "Magic",
        "resources": "Trackers",
    }
    expected = build_session_character_sections(
        full,
        equipment_state_manager=equipment_state_manager,
        include_spellcasting=True,
        session_character_subpage_labels=labels,
    )

    monkeypatch.setattr(
        presenter_module,
        "resolve_spell_description_html",
        lambda *_args, **_kwargs: pytest.fail("count projection resolved a spell body"),
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_feature_description_html",
        lambda *_args, **_kwargs: pytest.fail("count projection resolved a feature body"),
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_item_description_html",
        lambda *_args, **_kwargs: pytest.fail("count projection resolved an item body"),
    )
    monkeypatch.setattr(
        mechanics_module,
        "project_item_use_actions",
        lambda *_args, **_kwargs: pytest.fail(
            "count projection built full item-action state"
        ),
    )
    monkeypatch.setattr(
        mechanics_module,
        "project_spell_slot_options",
        lambda *_args, **_kwargs: pytest.fail(
            "count projection built item-action spell-slot state"
        ),
    )
    counts = present_dnd_character_section_counts(_campaign(), record)
    actual = build_dnd_session_section_navigation(
        counts,
        equipment_state_manager=equipment_state_manager,
        include_spellcasting=True,
        session_character_subpage_labels=labels,
        portrait=full["portrait"],
    )

    assert actual == expected
    with pytest.raises(ValueError, match="requires exact counts"):
        build_dnd_session_section_navigation(
            {key: value for key, value in counts.items() if key != "spells"},
            equipment_state_manager=equipment_state_manager,
            include_spellcasting=True,
        )


def test_exact_note_and_personal_counts_use_bounded_presence_without_building_hidden_sections(
    monkeypatch,
):
    record = _record(
        definition_overrides={
            "profile": {
                "biography_markdown": "<!-- comment only -->",
                "personality_markdown": "[profile-only]: https://example.com/profile",
            },
            "reference_notes": {
                "additional_notes_markdown": "Suppressed base additional notes.",
                "allies_and_organizations_markdown": "A visible ally.",
                "custom_sections": [
                    {
                        "title": " Additional Notes ",
                        "body_markdown": "<script>alert('kept as text')</script>",
                    },
                    {"title": "Research", "body_markdown": "Visible research."},
                    {"title": " research ", "body_markdown": "Visible research."},
                    {"title": "Comment", "body_markdown": "<!-- hidden -->"},
                    {
                        "title": "Reference",
                        "body_markdown": "[only]: https://example.com/reference",
                    },
                    {"title": "Actions: Imported", "body_markdown": "Excluded action."},
                    {"title": "", "body_markdown": "Missing title."},
                    {"title": "Missing body", "body_markdown": "   "},
                ],
            },
        },
        state={
            "vitals": {"current_hp": 6, "temp_hp": 0},
            "notes": {
                "player_notes_markdown": "[player-only]: https://example.com/player",
                "physical_description_markdown": "<!-- no visible description -->",
                "background_markdown": "Visible personal background.",
            },
        },
    )
    full = present_character_detail(_campaign(), record)
    expected_notes = int(bool(full["player_notes_html"])) + len(
        full["reference_sections"]
    )
    expected_personal = int(bool(full["physical_description_html"])) + int(
        bool(full["personal_background_html"])
    )

    assert [section["title"] for section in full["reference_sections"]] == [
        "Allies and Organizations",
        "Additional Notes",
        "Research",
    ]

    monkeypatch.setattr(
        presenter_module,
        "render_campaign_markdown",
        lambda *_args, **_kwargs: pytest.fail(
            "count projection called the public Markdown renderer"
        ),
    )
    monkeypatch.setattr(
        presenter_module,
        "build_reference_sections",
        lambda *_args, **_kwargs: pytest.fail(
            "count projection built hidden reference sections"
        ),
    )

    counts = present_dnd_character_section_counts(_campaign(), record)

    assert counts["notes"] == expected_notes
    assert counts["personal"] == expected_personal


def test_exact_feature_count_uses_structural_nesting_without_descriptions_or_replicate_item_lookup(
    monkeypatch,
):
    record = _record(
        definition_overrides={
            "stats": {"max_hp": 10},
            "features": [
                {
                    "id": "explicit-parent",
                    "name": "Explicit Parent",
                    "category": "class_feature",
                },
                {
                    "id": "explicit-child",
                    "name": "Explicit Child",
                    "category": "class_feature",
                    "parent_feature_id": "explicit-parent",
                },
                {"id": "arcane", "name": "Arcane Armor", "category": "class_feature"},
                {"id": "model", "name": "Armor Model", "category": "class_feature"},
                {"id": "guardian", "name": "Guardian", "category": "class_feature"},
                {
                    "id": "gauntlets",
                    "name": "Guardian Armor: Thunder Gauntlets",
                    "category": "class_feature",
                },
                {
                    "id": "infusions",
                    "name": "Artificer Infusions",
                    "category": "class_feature",
                },
                {
                    "id": "enhanced-defense",
                    "name": "Enhanced Defense",
                    "category": "class_feature",
                },
                {
                    "id": "replicate",
                    "name": "Replicate Magic Item (Goggles of Night)",
                    "category": "class_feature",
                },
                {
                    "id": "custom-base",
                    "name": "Guardian Armor: Lightning Launcher",
                    "category": "custom_feature",
                },
                {
                    "id": "custom-empty",
                    "name": "Guardian Armor: Lightning Launcher (DEX)",
                    "category": "custom_feature",
                },
                {
                    "id": "custom-comment",
                    "name": "Guardian Armor: Lightning Launcher (INT)",
                    "category": "custom_feature",
                    "description_markdown": "<!-- comment only -->",
                },
                {
                    "id": "custom-reference",
                    "name": "Guardian Armor: Lightning Launcher (WIS)",
                    "category": "custom_feature",
                    "description_markdown": "[only]: https://example.com/only",
                },
                {
                    "id": "custom-script",
                    "name": "Guardian Armor: Lightning Launcher (CHA)",
                    "category": "custom_feature",
                    "description_markdown": "<script>alert('safe text')</script>",
                },
                {
                    "id": "custom-visible",
                    "name": "Guardian Armor: Lightning Launcher (CON)",
                    "category": "custom_feature",
                    "description_markdown": "Visible duplicate detail.",
                },
            ],
        },
    )
    searches: list[tuple[str, str]] = []

    class MetadataOnlySystemsService:
        def search_entries_for_campaign(
            self,
            _campaign_slug,
            *,
            query,
            entry_type,
            limit,
        ):
            searches.append((query, entry_type))
            pytest.fail("feature count performed an irrelevant exact-title lookup")

        def get_entry_by_slug_for_campaign(self, *_args, **_kwargs):
            pytest.fail("feature count resolved a linked Systems body entry")

        def build_character_sheet_entry_body_html(self, *_args, **_kwargs):
            pytest.fail("feature count built a linked Systems body")

    service = MetadataOnlySystemsService()
    monkeypatch.setattr(
        mechanics_module,
        "normalize_definition_to_native_model",
        lambda definition, **_kwargs: definition,
    )

    full = present_character_detail(_campaign(), record)
    expected_feature_count = sum(
        len(group["entries"]) for group in full["feature_groups"]
    )

    monkeypatch.setattr(
        presenter_module,
        "render_campaign_markdown",
        lambda *_args, **_kwargs: pytest.fail(
            "feature count called the public Markdown renderer"
        ),
    )
    monkeypatch.setattr(
        presenter_module,
        "resolve_feature_description_html",
        lambda *_args, **_kwargs: pytest.fail("feature count resolved a feature body"),
    )
    monkeypatch.setattr(
        presenter_module,
        "nest_feature_components",
        lambda *_args, **_kwargs: pytest.fail(
            "feature count invoked live feature nesting"
        ),
    )
    searches.clear()

    counts = present_dnd_character_section_counts(
        _campaign(),
        record,
        systems_service=service,
    )

    assert counts["features"] == expected_feature_count
    assert searches == []


def test_exact_feature_count_uses_cleaned_tool_expertise_and_language_predicates():
    record = _record(
        definition_overrides={
            "proficiencies": {
                "tools": ["   "],
                "tool_expertise": ["Thieves' Tools"],
                "languages": ["   "],
            },
            "features": [
                {
                    "id": "proficiencies",
                    "name": "Proficiencies",
                    "category": "class_feature",
                },
                {
                    "id": "languages",
                    "name": "Languages",
                    "category": "class_feature",
                },
            ],
        },
    )
    full = present_character_detail(_campaign(), record)
    full_feature_count = sum(
        len(group["entries"]) for group in full["feature_groups"]
    )

    assert full["proficiency_groups"] == [
        {"title": "Tools", "values_list": ["Thieves' Tools (Expertise)"]}
    ]
    assert [
        entry["name"]
        for group in full["feature_groups"]
        for entry in group["entries"]
    ] == ["Languages"]
    assert present_dnd_character_section_counts(_campaign(), record)[
        "features"
    ] == full_feature_count


def test_every_scoped_dnd_section_matches_full_with_real_systems_and_campaign_links(app):
    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign(TEST_CAMPAIGN_SLUG)
        record = app.extensions["character_repository"].get_visible_character(
            TEST_CAMPAIGN_SLUG,
            ASSIGNED_CHARACTER_SLUG,
        )
        page_records = list_visible_character_page_records(
            app.extensions["campaign_page_store"],
            TEST_CAMPAIGN_SLUG,
            campaign,
            include_body=True,
            excluded_sections={"Sessions"},
        )
        full = present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
            campaign_page_records=page_records,
        )
        for section, dependency in DND_SECTION_DEPENDENCY_MANIFEST.items():
            scoped = present_dnd_character_section(
                campaign,
                record,
                section=section,
                systems_service=app.extensions["systems_service"],
                campaign_page_records=page_records,
            )
            projection_fields = tuple(
                dict.fromkeys((*DND_COMMON_PRESENTATION_FIELDS, *dependency.output_fields))
            )
            _assert_scoped_projection_parity(scoped, full, dependency)
        counts = present_dnd_character_section_counts(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
            campaign_page_records=page_records,
        )
        assert build_dnd_session_section_navigation(
            counts,
            equipment_state_manager={"rows": []},
            include_spellcasting=True,
        ) == build_session_character_sections(
            full,
            equipment_state_manager={"rows": []},
            include_spellcasting=True,
        )
