from __future__ import annotations

from datetime import datetime, timezone

import pytest

from player_wiki.divine_avatar_forms import (
    AVATAR_OF_MOURNING_FORM_KEY,
    present_divine_avatar_forms_state,
)
from player_wiki.character_mechanics_projection import build_character_mechanics_projection
from player_wiki.character_models import (
    CharacterDefinition,
    CharacterImportMetadata,
    CharacterRecord,
    CharacterStateRecord,
)
from player_wiki.character_service import validate_state
from player_wiki.character_state_service import CharacterStateService
from player_wiki.models import Campaign


def _definition() -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": "tod",
            "name": "Tod",
            "status": "active",
            "profile": {},
            "stats": {
                "max_hp": 50,
                "armor_class": 16,
                "proficiency_bonus": 3,
                "passive_perception": 16,
                "passive_insight": 16,
                "passive_investigation": 10,
                "ability_scores": {
                    "wis": {"score": 16, "modifier": 3, "save_bonus": 6},
                },
            },
            "skills": [
                {"name": "Insight", "bonus": 6, "proficiency_level": "proficient"},
                {"name": "Perception", "bonus": 6, "proficiency_level": "proficient"},
                {"name": "Investigation", "bonus": 0, "proficiency_level": "none"},
            ],
            "proficiencies": {},
            "attacks": [],
            "features": [
                {
                    "name": "Divine Avatar Forms",
                    "category": "custom_feature",
                    "page_ref": "mechanics/divine-avatar-forms",
                }
            ],
            "spellcasting": {
                "spellcasting_class": "Cleric",
                "spellcasting_ability": "Wisdom",
                "spell_save_dc": 14,
                "spell_attack_bonus": 6,
                "slot_progression": [
                    {"level": 1, "max_slots": 4},
                    {"level": 2, "max_slots": 3},
                ],
                "class_rows": [
                    {
                        "class_row_id": "cleric",
                        "class_name": "Cleric",
                        "spellcasting_ability": "Wisdom",
                        "spell_save_dc": 14,
                        "spell_attack_bonus": 6,
                    }
                ],
                "spells": [],
            },
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {},
        }
    )


def _state(**overrides):
    payload = {
        "vitals": {"current_hp": 20, "temp_hp": 4},
        "spell_slots": [
            {"level": 1, "max": 4, "used": 3},
            {"level": 2, "max": 3, "used": 2},
        ],
        "resources": [],
        "inventory": [],
        "currency": {},
        "notes": {},
    }
    payload.update(overrides)
    return payload


def _record(state=None, *, revision=1) -> CharacterRecord:
    definition = _definition()
    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata(
            campaign_slug="linden-pass",
            character_slug="tod",
            source_path="test://avatar",
            imported_at_utc="2026-08-01T00:00:00Z",
            parser_version="test",
            import_status="complete",
            warnings=[],
        ),
        state_record=CharacterStateRecord(
            campaign_slug="linden-pass",
            character_slug="tod",
            revision=revision,
            state=state or _state(),
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=None,
        ),
    )


class _MemoryStateStore:
    def replace_state(
        self,
        definition,
        state,
        *,
        expected_revision,
        updated_by_user_id=None,
        commit=True,
    ):
        return CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=expected_revision + 1,
            state=validate_state(definition, state),
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=updated_by_user_id,
        )


def _next_record(result: CharacterStateRecord) -> CharacterRecord:
    record = _record(result.state, revision=result.revision)
    return record


def test_activation_restores_slots_and_grants_nonstacking_temporary_hit_points():
    result = CharacterStateService(_MemoryStateStore()).update_divine_avatar_form(
        _record(),
        AVATAR_OF_MOURNING_FORM_KEY,
        "activate",
        expected_revision=1,
        confirmed=True,
    )

    forms_state = result.state["feature_states"]["divine_avatar_forms"]
    avatar = forms_state["forms"]["avatar_of_mourning"]
    assert forms_state["active_form"] == AVATAR_OF_MOURNING_FORM_KEY
    assert avatar["rounds_elapsed"] == 0
    assert result.state["vitals"]["temp_hp"] == 90
    assert [slot["used"] for slot in result.state["spell_slots"]] == [0, 0]


def test_activation_requires_less_than_half_hp_and_completed_cooldown():
    service = CharacterStateService(_MemoryStateStore())
    with pytest.raises(ValueError, match="less than half"):
        service.update_divine_avatar_form(
            _record(_state(vitals={"current_hp": 25, "temp_hp": 0})),
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            expected_revision=1,
            confirmed=True,
        )
    with pytest.raises(ValueError, match="40-day cooldown"):
        service.update_divine_avatar_form(
            _record(
                _state(
                    feature_states={
                        "divine_avatar_forms": {
                            "forms": {
                                "avatar_of_mourning": {"cooldown_active": True}
                            }
                        }
                    }
                )
            ),
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            expected_revision=1,
            confirmed=True,
        )


def test_divine_avatar_forms_is_the_feature_gate_and_mourning_is_a_form():
    singular_definition_payload = _definition().to_dict()
    singular_definition_payload["features"] = [
        {"name": "Avatar of Mourning", "category": "custom_feature"}
    ]
    singular_record = _record()
    singular_record.definition = CharacterDefinition.from_dict(singular_definition_payload)

    with pytest.raises(ValueError, match="Divine Avatar Forms are not recorded"):
        CharacterStateService(_MemoryStateStore()).update_divine_avatar_form(
            singular_record,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            expected_revision=1,
        )

    presented = present_divine_avatar_forms_state(_definition(), _state())
    assert presented["label"] == "Divine Avatar Forms"
    assert [form["label"] for form in presented["forms"]] == ["Avatar of Mourning"]


def test_active_projection_changes_only_transient_avatar_statistics():
    definition = _definition()
    projected = build_character_mechanics_projection(
        campaign=Campaign(
            title="Linden Pass",
            slug="linden-pass",
            summary="",
            system="DND-5E",
            current_session=34,
            source_wiki_root="",
            player_content_dir="",
            assets_dir="",
        ),
        definition=definition,
        state=_state(
            feature_states={
                "divine_avatar_forms": {
                    "active_form": "avatar_of_mourning",
                    "forms": {"avatar_of_mourning": {}},
                }
            }
        ),
    )
    projected_definition = projected["definition"]

    assert projected_definition.stats["ability_scores"]["wis"] == {
        "score": 26,
        "modifier": 8,
        "save_bonus": 11,
    }
    assert projected_definition.stats["armor_class"] == 20
    assert projected_definition.stats["passive_perception"] == 21
    assert projected_definition.stats["passive_insight"] == 21
    assert projected_definition.stats["passive_investigation"] == 10
    projected_skill_bonuses = {
        skill["name"]: skill["bonus"] for skill in projected_definition.skills
    }
    assert projected_skill_bonuses["Insight"] == 11
    assert projected_skill_bonuses["Perception"] == 11
    assert projected_skill_bonuses["Investigation"] == 0
    assert projected_definition.spellcasting["spell_save_dc"] == 22
    assert projected_definition.spellcasting["spell_attack_bonus"] == 14
    assert definition.stats["ability_scores"]["wis"]["score"] == 16
    assert definition.stats["armor_class"] == 16


def test_combat_turns_count_once_and_end_at_ten_rounds_with_one_cost_record():
    service = CharacterStateService(_MemoryStateStore())
    result = service.update_divine_avatar_form(
        _record(),
        AVATAR_OF_MOURNING_FORM_KEY,
        "activate",
        expected_revision=1,
        confirmed=True,
    )
    record = _next_record(result)

    result = service.update_divine_avatar_form(
        record,
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        expected_revision=record.state_record.revision,
        combat_turn_token="combat:2:tod",
    )
    assert result.state["feature_states"]["divine_avatar_forms"]["forms"]["avatar_of_mourning"]["rounds_elapsed"] == 1

    duplicate = service.update_divine_avatar_form(
        _next_record(result),
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        expected_revision=result.revision,
        combat_turn_token="combat:2:tod",
    )
    assert duplicate.revision == result.revision

    current = result
    for round_number in range(3, 12):
        record = _next_record(current)
        current = service.update_divine_avatar_form(
            record,
            AVATAR_OF_MOURNING_FORM_KEY,
            "advance_turn",
            expected_revision=record.state_record.revision,
            combat_turn_token=f"combat:{round_number}:tod",
        )

    forms_state = current.state["feature_states"]["divine_avatar_forms"]
    avatar = forms_state["forms"]["avatar_of_mourning"]
    assert forms_state["active_form"] == ""
    assert avatar["cooldown_active"] is True
    assert avatar["last_end_cost"]["rounds"] == 10
    assert avatar["last_end_cost"]["exhaustion_gained"] == 10
    assert avatar["last_end_cost"]["exhaustion_applied"] == 6
    assert avatar["last_end_cost"]["radiant_damage_dice"] == "50d12"
    assert avatar["last_end_cost"]["reason"] == "duration"
    assert current.state["exhaustion_level"] == 6


def test_dismissal_tracks_current_cost_and_cooldown_without_removing_temp_hp():
    service = CharacterStateService(_MemoryStateStore())
    activated = service.update_divine_avatar_form(
        _record(),
        AVATAR_OF_MOURNING_FORM_KEY,
        "activate",
        expected_revision=1,
        confirmed=True,
    )
    active_state = activated.state
    active_state["feature_states"]["divine_avatar_forms"]["forms"]["avatar_of_mourning"]["rounds_elapsed"] = 2
    result = service.update_divine_avatar_form(
        _record(active_state, revision=activated.revision),
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        expected_revision=activated.revision,
        confirmed=True,
    )

    avatar = result.state["feature_states"]["divine_avatar_forms"]["forms"]["avatar_of_mourning"]
    assert avatar["last_end_cost"]["radiant_damage_dice"] == "10d12"
    assert result.state["exhaustion_level"] == 2
    assert result.state["vitals"]["temp_hp"] == 90
    presented_form = present_divine_avatar_forms_state(_definition(), result.state)["forms"][0]
    assert presented_form["status_label"] == "Recharging"


def test_zero_hp_ends_an_active_avatar_as_unconscious():
    service = CharacterStateService(_MemoryStateStore())
    activated = service.update_divine_avatar_form(
        _record(),
        AVATAR_OF_MOURNING_FORM_KEY,
        "activate",
        expected_revision=1,
        confirmed=True,
    )
    state = activated.state
    state["feature_states"]["divine_avatar_forms"]["forms"]["avatar_of_mourning"]["rounds_elapsed"] = 1
    result = service.update_vitals(
        _record(state, revision=activated.revision),
        expected_revision=activated.revision,
        current_hp=0,
    )

    forms_state = result.state["feature_states"]["divine_avatar_forms"]
    avatar = forms_state["forms"]["avatar_of_mourning"]
    assert forms_state["active_form"] == ""
    assert avatar["last_end_cost"]["reason"] == "unconscious"
    assert result.state["exhaustion_level"] == 1
