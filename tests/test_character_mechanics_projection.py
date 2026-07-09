from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from player_wiki import character_mechanics_projection as projection_module
from player_wiki.character_mechanics_projection import (
    build_character_mechanics_projection,
    project_spell_action_state,
)
from player_wiki.character_models import (
    CharacterDefinition,
    CharacterImportMetadata,
    CharacterRecord,
    CharacterStateRecord,
)
from player_wiki.character_presenter import present_character_detail
from player_wiki.models import Campaign


def _campaign(*, system: str = "DND-5E") -> Campaign:
    return Campaign(
        title="Linden Pass",
        slug="linden-pass",
        summary="",
        system=system,
        current_session=1,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
    )


def _definition(**overrides: Any) -> CharacterDefinition:
    payload = {
        "campaign_slug": "linden-pass",
        "character_slug": "projection-test",
        "name": "Projection Test",
        "status": "active",
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
    payload.update(overrides)
    return CharacterDefinition.from_dict(payload)


def _record(definition: CharacterDefinition, *, state: dict[str, Any] | None = None) -> CharacterRecord:
    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            source_path="test://projection",
            imported_at_utc="2026-07-09T00:00:00Z",
            parser_version="test",
            import_status="ok",
            warnings=[],
        ),
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=1,
            state=state or {"vitals": {"current_hp": 3, "temp_hp": 0}},
            updated_at=datetime(2026, 7, 9),
            updated_by_user_id=None,
        ),
    )


def test_present_character_detail_uses_projection_normalization_when_systems_service_is_present(monkeypatch):
    raw_definition = _definition(stats={"max_hp": 10})
    normalized_definition = _definition(stats={"max_hp": 17})
    systems_service = object()
    calls: dict[str, Any] = {}

    def fake_normalize(definition, *, systems_service=None, campaign_page_records=None):
        calls["definition"] = definition
        calls["systems_service"] = systems_service
        calls["campaign_page_records"] = campaign_page_records
        return normalized_definition

    def fake_merge(definition, state):
        calls["merged_definition"] = definition
        return {"vitals": {"current_hp": 7, "temp_hp": 0}, "resources": [], "inventory": []}

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)
    monkeypatch.setattr(projection_module, "merge_state_with_definition", fake_merge)

    character = present_character_detail(
        _campaign(),
        _record(raw_definition),
        systems_service=systems_service,
        campaign_page_records=["page-record"],
    )

    assert calls["definition"] is raw_definition
    assert calls["systems_service"] is systems_service
    assert calls["campaign_page_records"] == ["page-record"]
    assert calls["merged_definition"] is normalized_definition
    assert character["max_hp"] == 17
    assert character["current_hp"] == 7


def test_spell_action_projection_preserves_preparation_flags_and_current_view_filtering():
    prepared_row = {"row_kind": "class", "spell_mode": "prepared"}
    wizard_row = {"row_kind": "class", "spell_mode": "wizard"}
    ritual_book_row = {"row_kind": "source", "spell_mode": "ritual_book"}

    cantrip = project_spell_action_state(
        spell={"name": "Mage Hand"},
        row_payload=prepared_row,
        spell_level=0,
        mark="Cantrip",
    )
    prepared_spell = project_spell_action_state(
        spell={"name": "Bless"},
        row_payload=prepared_row,
        spell_level=1,
        mark="Prepared",
    )
    unprepared_spell = project_spell_action_state(
        spell={"name": "Cure Wounds"},
        row_payload=prepared_row,
        spell_level=1,
        mark="",
    )
    always_prepared_spell = project_spell_action_state(
        spell={"name": "Shield", "is_bonus_known": True},
        row_payload=prepared_row,
        spell_level=1,
        mark="",
        always_prepared=True,
    )
    wizard_spellbook_spell = project_spell_action_state(
        spell={"name": "Magic Missile"},
        row_payload=wizard_row,
        spell_level=1,
        mark="Spellbook",
    )
    ritual_book_spell = project_spell_action_state(
        spell={"name": "Detect Magic"},
        row_payload=ritual_book_row,
        spell_level=1,
        mark="Ritual book",
    )

    assert cantrip["can_show_in_current_view"] is True
    assert cantrip["can_toggle_prepared"] is False
    assert cantrip["can_remove"] is False

    assert prepared_spell["is_prepared"] is True
    assert prepared_spell["can_toggle_prepared"] is True
    assert prepared_spell["can_show_in_current_view"] is True
    assert prepared_spell["can_remove"] is False

    assert unprepared_spell["is_prepared"] is False
    assert unprepared_spell["can_toggle_prepared"] is True
    assert unprepared_spell["can_show_in_current_view"] is False
    assert unprepared_spell["can_remove"] is False

    assert always_prepared_spell["is_fixed"] is True
    assert always_prepared_spell["can_toggle_prepared"] is False
    assert always_prepared_spell["can_show_in_current_view"] is True

    assert wizard_spellbook_spell["can_toggle_prepared"] is True
    assert wizard_spellbook_spell["can_show_in_current_view"] is False
    assert ritual_book_spell["can_remove"] is True
    assert ritual_book_spell["can_show_in_current_view"] is True


def test_attack_projection_respects_item_links_equipped_state_quantity_and_wield_mode():
    definition = _definition(
        features=[{"name": "Arcane Armor", "category": "class_feature"}],
        equipment_catalog=[
            {"id": "quarterstaff-1", "name": "Quarterstaff", "default_quantity": 1},
            {"id": "light-crossbow-1", "name": "Light Crossbow", "default_quantity": 1},
            {"id": "dagger-1", "name": "Dagger"},
        ],
        attacks=[
            {"name": "Quarterstaff", "equipment_refs": ["quarterstaff-1"]},
            {
                "name": "Quarterstaff (two-handed)",
                "equipment_refs": ["quarterstaff-1"],
                "mode_key": "weapon:two-handed",
            },
            {"name": "Light Crossbow", "equipment_refs": ["light-crossbow-1"]},
            {"name": "Dagger", "equipment_refs": ["dagger-1"]},
            {"name": "Guardian Armor: Thunder Gauntlets"},
        ],
    )
    state = {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "inventory": [
            {
                "catalog_ref": "quarterstaff-1",
                "name": "Quarterstaff",
                "quantity": 1,
                "is_equipped": True,
                "weapon_wield_mode": "main-hand",
            },
            {
                "catalog_ref": "light-crossbow-1",
                "name": "Light Crossbow",
                "quantity": 1,
                "is_equipped": False,
            },
            {
                "catalog_ref": "dagger-1",
                "name": "Dagger",
                "quantity": 0,
                "is_equipped": True,
            },
        ],
    }

    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=state,
    )
    attacks_by_name = {
        attack["name"]: attack for attack in projected["attack_visibility"]
    }

    assert attacks_by_name["Quarterstaff"]["hidden"] is False
    assert attacks_by_name["Quarterstaff"]["linked_item_refs"] == ["quarterstaff-1"]
    assert attacks_by_name["Quarterstaff (two-handed)"]["hidden"] is True
    assert attacks_by_name["Quarterstaff (two-handed)"]["hidden_reason"] == "linked_item_not_equipped"
    assert attacks_by_name["Light Crossbow"]["hidden"] is True
    assert attacks_by_name["Light Crossbow"]["hidden_reason"] == "linked_item_not_equipped"
    assert attacks_by_name["Dagger"]["hidden"] is False
    assert attacks_by_name["Dagger"]["is_equipped"] is None
    assert attacks_by_name["Guardian Armor: Thunder Gauntlets"]["hidden"] is True
    assert attacks_by_name["Guardian Armor: Thunder Gauntlets"]["hidden_reason"] == "arcane_armor_unavailable"

    enabled_state = {
        **state,
        "feature_states": {"arcane_armor": {"enabled": True}},
        "inventory": [
            {key: value for key, value in {**item, "is_equipped": False}.items() if key != "weapon_wield_mode"}
            for item in state["inventory"]
        ],
    }
    enabled_projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=enabled_state,
    )
    enabled_attacks = {
        attack["name"]: attack for attack in enabled_projected["attack_visibility"]
    }

    assert enabled_projected["arcane_armor_state"]["thunder_gauntlets_available"] is True
    assert enabled_attacks["Guardian Armor: Thunder Gauntlets"]["hidden"] is False


class _FakeXianxiaSystemsService:
    def __init__(self):
        self.entries_by_slug = {
            "skills": _entry(
                "Skills",
                "skills",
                paragraphs=[
                    "Trained skills never add active battle Attack or Damage bonuses.",
                    "Pre-battle preparation and surroundings can still matter.",
                ],
            ),
            "stance": _entry(
                "Stance",
                "stance",
                bullets=[
                    "When current Stance reaches 0, Stance Breaks.",
                    "Stance recovers after a short rest.",
                ],
            ),
            "stance-activation-rules": _entry(
                "Stance Activation Rules",
                "stance-activation-rules",
                summary="Only one Stance can be active at a time.",
            ),
            "aura-activation-rules": _entry(
                "Aura Activation Rules",
                "aura-activation-rules",
                summary="Only one Aura can be active at a time.",
            ),
            "critical-hits": _entry(
                "Critical Hits",
                "critical-hits",
                summary="Critical Hits are reference-only in this slice.",
            ),
        }

    def get_entry_for_campaign(self, campaign_slug, entry_key):
        return None

    def get_entry_by_slug_for_campaign(self, campaign_slug, slug):
        return self.entries_by_slug.get(slug)


def _entry(title: str, slug: str, *, summary: str = "", paragraphs=None, bullets=None):
    return SimpleNamespace(
        title=title,
        slug=slug,
        metadata={"support_state": "reference_only"},
        body={
            "summary": summary,
            "sections": [
                {
                    "paragraphs": list(paragraphs or []),
                    "bullets": list(bullets or []),
                }
            ],
        },
    )


def test_xianxia_rule_reminders_are_projected_from_systems_entries():
    definition = _definition(
        system="Xianxia",
        xianxia={
            "realm": "Mortal",
            "honor": "Honorable",
            "attributes": {"con": 2},
            "efforts": {},
            "durability": {"hp_max": 10, "stance_max": 10, "manual_armor_bonus": 1},
        },
    )
    state = {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "xianxia": {
            "vitals": {"current_stance": 0, "temp_stance": 0},
            "active_stance": {"name": "Falling Leaf"},
            "active_aura": {},
        },
    }

    projected = build_character_mechanics_projection(
        campaign=_campaign(system="Xianxia"),
        definition=definition,
        state=state,
        systems_service=_FakeXianxiaSystemsService(),
    )
    xianxia_projection = projected["xianxia"]

    assert xianxia_projection["defense"]["value"] == 13
    assert xianxia_projection["skill_use_guardrails"]["reference_lines"] == [
        "Trained skills never add active battle Attack or Damage bonuses.",
        "Pre-battle preparation and surroundings can still matter.",
    ]
    assert xianxia_projection["stance_break"]["reference_lines"] == [
        "When current Stance reaches 0, Stance Breaks."
    ]
    assert xianxia_projection["stance_break"]["recovery_lines"] == [
        "Stance recovers after a short rest."
    ]
    assert [
        reminder["status_label"]
        for reminder in xianxia_projection["active_state_reminders"]
    ] == ["Active Stance: Falling Leaf", "No active Aura recorded"]
    assert [entry["title"] for entry in xianxia_projection["rule_text_references"]] == [
        "Critical Hits"
    ]
