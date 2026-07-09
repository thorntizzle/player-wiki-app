from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from player_wiki import character_mechanics_projection as projection_module
from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
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
from player_wiki.systems_models import SystemsEntryRecord
from tests.sample_data import approved_innovators_bolt_item_mechanics


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


def test_projection_reports_warning_when_read_time_normalization_falls_back(monkeypatch):
    raw_definition = _definition(stats={"max_hp": 10})

    def fake_normalize(definition, *, systems_service=None, campaign_page_records=None):
        raise projection_module.CharacterBuildError("projection failed")

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)

    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=raw_definition,
        state={"vitals": {"current_hp": 5, "temp_hp": 0}},
        systems_service=object(),
    )

    assert projected["definition"] is raw_definition
    assert projected["projection_warnings"] == [
        {
            "code": "read_time_projection_failed",
            "message": "projection failed",
        }
    ]


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


def test_projection_shapes_attack_reminders_and_defensive_rules():
    definition = _definition(
        stats={
            "max_hp": 10,
            "attack_reminder_state": {
                "rules": [
                    {
                        "title": "Piercing note",
                        "condition": "Once per turn.",
                        "attack_scope": {
                            "label": "Piercing weapon attacks",
                            "categories": ["ranged weapon"],
                            "damage_types": ["piercing"],
                        },
                        "effects": [
                            {
                                "kind": "reroll",
                                "label": "Piercer",
                                "summary": "Reroll one piercing damage die.",
                            }
                        ],
                    }
                ]
            },
            "defensive_state": {
                "rules": [
                    {
                        "title": "Sleep ward",
                        "active": True,
                        "condition": "While attuned.",
                        "effects": [
                            {
                                "kind": "immunity",
                                "label": "Sleep",
                                "summary": "You can't be magically put to sleep.",
                            }
                        ],
                    }
                ]
            },
        },
        equipment_catalog=[
            {"id": "bolt-1", "name": "Innovator's Bolt", "default_quantity": 1},
        ],
        attacks=[
            {
                "name": "Innovator's Bolt",
                "category": "ranged weapon",
                "damage_type": "piercing",
                "equipment_refs": ["bolt-1"],
            }
        ],
    )
    state = {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "inventory": [
            {
                "catalog_ref": "bolt-1",
                "name": "Innovator's Bolt",
                "quantity": 1,
                "is_equipped": True,
            }
        ],
    }

    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=state,
    )

    assert projected["attack_reminders"][0]["eligible_attacks"] == ["Innovator's Bolt"]
    assert projected["attack_reminders"][0]["status_label"] == "Linked attacks"
    assert projected["defensive_rules"][0]["title"] == "Sleep ward"
    assert projected["defensive_rules"][0]["status_label"] == "Active"


class _FakeItemSystemsService:
    def __init__(self, metadata: dict[str, Any]):
        self.entry = SystemsEntryRecord(
            id=1,
            library_slug="DND-5E",
            source_id="CUSTOM-LINDEN-PASS",
            entry_key="dnd-5e|custom|linden-pass|innovators-bolt",
            entry_type="item",
            title="Innovator's Bolt",
            slug="custom-linden-pass-innovators-bolt",
            source_page="",
            source_path="",
            search_text="innovator's bolt",
            player_safe_default=True,
            dm_heavy=False,
            metadata=metadata,
            body={},
            rendered_html="",
            created_at=datetime(2026, 7, 9),
            updated_at=datetime(2026, 7, 9),
        )

    def get_entry_for_campaign(self, campaign_slug, entry_key):
        return None

    def get_entry_by_slug_for_campaign(self, campaign_slug, slug):
        if slug == self.entry.slug:
            return self.entry
        return None

    def get_campaign_item_entry_by_page_ref(self, campaign_slug, page_ref):
        metadata = dict(self.entry.metadata or {})
        normalized_page_ref = str(page_ref or "").strip()
        if normalized_page_ref in {
            str(metadata.get("page_ref") or "").strip(),
            str(metadata.get("linked_published_page_ref") or "").strip(),
        }:
            return self.entry
        return None

    def list_enabled_entries_for_campaign(self, campaign_slug, *, entry_type=None, limit=None):
        if entry_type == "item":
            return [self.entry]
        return []


def _innovators_bolt_action_metadata(*, review_status: str = "approved") -> dict[str, Any]:
    return build_campaign_item_mechanics_metadata(
        title="Innovator's Bolt",
        body_markdown="*Weapon (pistol), very rare (requires attunement by an artificer)*",
        explicit_mechanics=approved_innovators_bolt_item_mechanics(),
        source_page_ref="items/innovators-bolt",
        review_status=review_status,
    )


def test_projection_exposes_approved_spell_slot_item_actions_with_slot_state():
    definition = _definition(
        spellcasting={
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "spell_save_dc": 15,
                }
            ],
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Artificer spell slots",
                    "slot_progression": [
                        {"level": 1, "max_slots": 4},
                        {"level": 2, "max_slots": 2},
                    ],
                }
            ],
        },
        equipment_catalog=[
            {
                "id": "innovators-bolt-1",
                "name": "Innovator's Bolt",
                "default_quantity": 1,
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "custom-linden-pass-innovators-bolt",
                    "title": "Innovator's Bolt",
                    "source_id": "CUSTOM-LINDEN-PASS",
                },
            }
        ],
    )
    state = {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "inventory": [
            {
                "catalog_ref": "innovators-bolt-1",
                "name": "Innovator's Bolt",
                "quantity": 1,
                "is_equipped": True,
                "is_attuned": True,
            }
        ],
        "spell_slots": [
            {"slot_lane_id": "class-row-1-slots", "level": 1, "used": 1},
            {"slot_lane_id": "class-row-1-slots", "level": 2, "used": 2},
        ],
    }

    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=state,
        systems_service=_FakeItemSystemsService(_innovators_bolt_action_metadata()),
    )

    action = projected["item_use_actions"][0]
    choices_by_id = {choice["id"]: choice for choice in action["choices"]}

    assert action["id"] == "innovators-bolt-enchanted-bullet"
    assert action["enabled"] is True
    assert action["slot_options"] == [
        {
            "level": 1,
            "level_label": "1st level",
            "slot_lane_id": "class-row-1-slots",
            "lane_title": "Artificer spell slots",
            "label": "1st level",
            "used": 1,
            "max": 4,
            "available": 3,
            "selection": "class-row-1-slots|1",
        },
        {
            "level": 2,
            "level_label": "2nd level",
            "slot_lane_id": "class-row-1-slots",
            "lane_title": "Artificer spell slots",
            "label": "2nd level",
            "used": 2,
            "max": 2,
            "available": 0,
            "selection": "class-row-1-slots|2",
        },
    ]
    assert list(choices_by_id) == ["incendiary", "booming", "smoke"]
    assert choices_by_id["incendiary"]["damage_scaling"] == {"per_slot_level": "1d6 fire"}
    assert choices_by_id["incendiary"]["save"]["label"] == "DEX save DC 15"
    assert choices_by_id["booming"]["damage_scaling"] == {"per_slot_level": "1d8 thunder"}
    assert choices_by_id["booming"]["save"]["label"] == "CON save DC 15"
    assert choices_by_id["booming"]["condition"] == {}
    assert choices_by_id["smoke"]["damage_scaling"] == {"per_slot_level": "1d6 bludgeoning"}
    assert choices_by_id["smoke"]["save"]["label"] == "WIS save DC 15"
    assert all(choice["is_supported"] is True for choice in choices_by_id.values())
    assert all("table-managed" in choice["summary"] for choice in choices_by_id.values())


def _page_linked_innovators_bolt_definition() -> CharacterDefinition:
    return _definition(
        spellcasting={
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "spell_save_dc": 15,
                }
            ],
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Artificer spell slots",
                    "slot_progression": [{"level": 1, "max_slots": 2}],
                }
            ],
        },
        equipment_catalog=[
            {
                "id": "manual-item-innovators-bolt",
                "name": "Innovator's Bolt",
                "default_quantity": 1,
                "page_ref": "items/innovators-bolt",
            }
        ],
    )


def _page_linked_innovators_bolt_state(
    *,
    is_equipped: bool = True,
    is_attuned: bool = True,
) -> dict[str, Any]:
    return {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "inventory": [
            {
                "catalog_ref": "manual-item-innovators-bolt",
                "name": "Innovator's Bolt",
                "quantity": 1,
                "is_equipped": is_equipped,
                "is_attuned": is_attuned,
            }
        ],
        "spell_slots": [{"slot_lane_id": "class-row-1-slots", "level": 1, "used": 0}],
    }


def test_projection_resolves_page_linked_approved_item_actions():
    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_page_linked_innovators_bolt_definition(),
        state=_page_linked_innovators_bolt_state(),
        systems_service=_FakeItemSystemsService(_innovators_bolt_action_metadata()),
    )

    action = projected["item_use_actions"][0]

    assert action["id"] == "innovators-bolt-enchanted-bullet"
    assert action["item_ref"] == "manual-item-innovators-bolt"
    assert action["enabled"] is True
    assert action["disabled_reason"] == ""


def test_projection_hides_unapproved_page_linked_item_actions():
    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_page_linked_innovators_bolt_definition(),
        state=_page_linked_innovators_bolt_state(),
        systems_service=_FakeItemSystemsService(
            _innovators_bolt_action_metadata(review_status="manual_review")
        ),
    )

    assert projected["item_use_actions"] == []


def test_projection_keeps_page_linked_unequipped_item_action_disabled():
    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_page_linked_innovators_bolt_definition(),
        state=_page_linked_innovators_bolt_state(is_equipped=False, is_attuned=True),
        systems_service=_FakeItemSystemsService(_innovators_bolt_action_metadata()),
    )

    action = projected["item_use_actions"][0]

    assert action["id"] == "innovators-bolt-enchanted-bullet"
    assert action["enabled"] is False
    assert action["disabled_reason"] == "Equip this item before using this action."


def test_projection_keeps_page_linked_unattuned_item_action_disabled():
    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_page_linked_innovators_bolt_definition(),
        state=_page_linked_innovators_bolt_state(is_equipped=True, is_attuned=False),
        systems_service=_FakeItemSystemsService(_innovators_bolt_action_metadata()),
    )

    action = projected["item_use_actions"][0]

    assert action["id"] == "innovators-bolt-enchanted-bullet"
    assert action["enabled"] is False
    assert action["disabled_reason"] == "Attune this item before using this action."


def test_projection_hides_unapproved_spell_slot_item_actions():
    definition = _definition(
        spellcasting={
            "slot_lanes": [
                {"id": "class-row-1-slots", "slot_progression": [{"level": 1, "max_slots": 2}]}
            ]
        },
        equipment_catalog=[
            {
                "id": "innovators-bolt-1",
                "name": "Innovator's Bolt",
                "default_quantity": 1,
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "custom-linden-pass-innovators-bolt",
                    "title": "Innovator's Bolt",
                    "source_id": "CUSTOM-LINDEN-PASS",
                },
            }
        ],
    )
    state = {
        "vitals": {"current_hp": 10, "temp_hp": 0},
        "inventory": [
            {
                "catalog_ref": "innovators-bolt-1",
                "name": "Innovator's Bolt",
                "quantity": 1,
                "is_equipped": True,
                "is_attuned": True,
            }
        ],
        "spell_slots": [{"slot_lane_id": "class-row-1-slots", "level": 1, "used": 0}],
    }

    projected = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=state,
        systems_service=_FakeItemSystemsService(
            _innovators_bolt_action_metadata(review_status="manual_review")
        ),
    )

    assert projected["item_use_actions"] == []


class _FakeXianxiaSystemsService:
    def __init__(self):
        self.entries_by_slug = {
            "skills": _entry(
                "Skills",
                "skills",
                paragraphs=["General skill prose that should not drive Quick Reference guardrails."],
                rule_facets={
                    "guardrails": {
                        "reference_lines": [
                            "Trained skills never add active battle Attack or Damage bonuses.",
                            "Pre-battle preparation and surroundings can still matter.",
                        ]
                    }
                },
            ),
            "stance": _entry(
                "Stance",
                "stance",
                bullets=["General Stance prose that should not drive Stance Break."],
                rule_facets={
                    "break_reference": {
                        "status_label": "Current Stance 0",
                        "reference_lines": ["When current Stance reaches 0, Stance Breaks."],
                        "recovery_lines": ["Stance recovers after a short rest."],
                    }
                },
            ),
            "stance-activation-rules": _entry(
                "Stance Activation Rules",
                "stance-activation-rules",
                summary="General Stance activation prose.",
                rule_facets={
                    "active_state_reminders": {
                        "state_key": "active_stance",
                        "label": "Stance",
                        "reference_lines": ["Only one Stance can be active at a time."],
                    }
                },
            ),
            "aura-activation-rules": _entry(
                "Aura Activation Rules",
                "aura-activation-rules",
                summary="General Aura activation prose.",
                rule_facets={
                    "active_state_reminders": {
                        "state_key": "active_aura",
                        "label": "Aura",
                        "reference_lines": ["Only one Aura can be active at a time."],
                    }
                },
            ),
            "critical-hits": _entry(
                "Critical Hits",
                "critical-hits",
                summary="General critical hit prose.",
                rule_facets={
                    "quick_reference": {
                        "reference_lines": ["Critical Hits are reference-only in this slice."],
                    }
                },
            ),
        }

    def get_entry_for_campaign(self, campaign_slug, entry_key):
        return None

    def get_entry_by_slug_for_campaign(self, campaign_slug, slug):
        return self.entries_by_slug.get(slug)


def _entry(
    title: str,
    slug: str,
    *,
    summary: str = "",
    paragraphs=None,
    bullets=None,
    rule_facets=None,
):
    return SimpleNamespace(
        title=title,
        slug=slug,
        metadata={
            "support_state": "reference_only",
            "xianxia_rule_facets": dict(rule_facets or {}),
        },
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
    assert [
        reminder["reference_lines"]
        for reminder in xianxia_projection["active_state_reminders"]
    ] == [
        ["Only one Stance can be active at a time."],
        ["Only one Aura can be active at a time."],
    ]
    assert [entry["title"] for entry in xianxia_projection["rule_text_references"]] == [
        "Critical Hits"
    ]
    assert xianxia_projection["rule_text_references"][0]["reference_lines"] == [
        "Critical Hits are reference-only in this slice."
    ]
