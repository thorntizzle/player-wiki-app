from __future__ import annotations

from copy import deepcopy

import pytest

import player_wiki.character_mechanics_projection as mechanics_projection
from player_wiki.character_mechanics_projection import (
    build_character_mechanics_projection,
    validate_divine_avatar_proposed_state_projection,
)
from player_wiki.character_models import CharacterDefinition
from player_wiki.models import Campaign


def _campaign() -> Campaign:
    return Campaign(
        title="Linden Pass",
        slug="linden-pass",
        summary="",
        system="DND-5E",
        current_session=34,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
    )


def _definition(*, wisdom: int = 16) -> CharacterDefinition:
    wisdom_modifier = (wisdom - 10) // 2
    proficiency_bonus = 3
    wisdom_save = wisdom_modifier + proficiency_bonus
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
                "proficiency_bonus": proficiency_bonus,
                "passive_perception": 10 + wisdom_save,
                "passive_insight": 10 + wisdom_save,
                "passive_investigation": 10,
                "ability_scores": {
                    "str": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "wis": {
                        "score": wisdom,
                        "modifier": wisdom_modifier,
                        "save_bonus": wisdom_save,
                    },
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "skills": [
                {
                    "name": "Insight",
                    "bonus": wisdom_save,
                    "proficiency_level": "proficient",
                },
                {
                    "name": "Perception",
                    "bonus": wisdom_save,
                    "proficiency_level": "proficient",
                },
                {
                    "name": "Investigation",
                    "bonus": 0,
                    "proficiency_level": "none",
                },
            ],
            "proficiencies": {},
            "attacks": [],
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
                "spell_save_dc": 8 + proficiency_bonus + wisdom_modifier,
                "spell_attack_bonus": proficiency_bonus + wisdom_modifier,
                "slot_progression": [],
                "class_rows": [],
                "spells": [],
            },
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {},
        }
    )


def _state(*, active: bool) -> dict:
    return {
        "vitals": {"current_hp": 20, "temp_hp": 0},
        "spell_slots": [],
        "resources": [],
        "inventory": [],
        "currency": {},
        "notes": {},
        "feature_states": {
            "divine_avatar_forms": {
                "schema_version": 1,
                "active_form": "avatar_of_mourning" if active else "",
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
    }


def _project(definition: CharacterDefinition, *, active: bool) -> CharacterDefinition:
    return build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state=_state(active=active),
    )["definition"]


def test_mourning_wisdom_override_is_transient_and_latest_true_score_returns() -> None:
    original = _definition(wisdom=16)
    active = _project(original, active=True)
    inactive = _project(original, active=False)

    assert active.stats["ability_scores"]["wis"] == {
        "score": 26,
        "modifier": 8,
        "save_bonus": 11,
    }
    assert inactive.stats["ability_scores"]["wis"]["score"] == 16
    assert original.stats["ability_scores"]["wis"]["score"] == 16

    revised_true_score = _definition(wisdom=18)
    revised_active = _project(revised_true_score, active=True)
    revised_inactive = _project(revised_true_score, active=False)

    assert revised_active.stats["ability_scores"]["wis"]["score"] == 26
    assert revised_inactive.stats["ability_scores"]["wis"]["score"] == 18
    assert revised_true_score.stats["ability_scores"]["wis"]["score"] == 18


def test_mourning_projection_rederives_dependents_without_losing_proficiencies() -> None:
    projected = _project(_definition(), active=True)
    skills = {row["name"]: row for row in projected.skills}

    assert projected.stats["armor_class"] == 20
    assert projected.stats["passive_perception"] == 21
    assert projected.stats["passive_insight"] == 21
    assert projected.stats["passive_investigation"] == 10
    assert skills["Insight"]["bonus"] == 11
    assert skills["Insight"]["proficiency_level"] == "proficient"
    assert skills["Perception"]["bonus"] == 11
    assert projected.spellcasting["spell_save_dc"] == 22
    assert projected.spellcasting["spell_attack_bonus"] == 14


def test_mourning_projection_is_repeatable_and_does_not_stack_or_mutate_base() -> None:
    definition = _definition()
    before = deepcopy(definition.to_dict())

    first = _project(definition, active=True)
    second = _project(definition, active=True)

    assert first.to_dict() == second.to_dict()
    assert first.stats["armor_class"] == 20
    assert first.spellcasting["spell_save_dc"] == 22
    assert definition.to_dict() == before


def test_base_projection_failure_blocks_activation(monkeypatch) -> None:
    def fail_projection(*args, **kwargs):
        raise ValueError("source normalization failed")

    monkeypatch.setattr(
        mechanics_projection,
        "normalize_definition_to_native_model",
        fail_projection,
    )

    result = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_definition(),
        state=_state(active=False),
        systems_service=object(),
    )
    avatar_state = result["divine_avatar_forms_state"]

    assert result["projection_warnings"] == [
        {
            "code": "read_time_projection_failed",
            "message": "source normalization failed",
        }
    ]
    assert avatar_state["state_errors"] == [
        "Divine Avatar mechanics could not be safely projected: source normalization failed"
    ]
    assert avatar_state["forms"][0]["activation_available"] is False


def test_transient_projection_failure_blocks_actions_but_preserves_safe_end(monkeypatch) -> None:
    def fail_projection(*args, **kwargs):
        raise ValueError("transient derivation failed")

    monkeypatch.setattr(
        mechanics_projection,
        "project_definition_with_transient_effects",
        fail_projection,
    )

    result = build_character_mechanics_projection(
        campaign=_campaign(),
        definition=_definition(),
        state=_state(active=True),
    )
    avatar_state = result["divine_avatar_forms_state"]
    form = avatar_state["forms"][0]

    assert result["definition"].stats["ability_scores"]["wis"]["score"] == 16
    assert result["projection_warnings"] == [
        {
            "code": "transient_mechanics_projection_failed",
            "message": "transient derivation failed",
        }
    ]
    assert avatar_state["state_errors"] == [
        "Divine Avatar mechanics could not be safely projected: transient derivation failed"
    ]
    assert form["mourning_wave_available"] is False
    assert form["strength_of_remembrance_available"] is False
    assert form["end_available"] is True

    with pytest.raises(ValueError, match="transient derivation failed"):
        validate_divine_avatar_proposed_state_projection(
            campaign=_campaign(),
            definition=_definition(),
            state=_state(active=True),
        )


def test_write_preflight_rejects_active_state_without_effective_wisdom_26(monkeypatch) -> None:
    monkeypatch.setattr(
        mechanics_projection,
        "project_definition_with_transient_effects",
        lambda definition, *_args, **_kwargs: definition,
    )

    with pytest.raises(ValueError, match="Wisdom 26 could not be safely projected"):
        validate_divine_avatar_proposed_state_projection(
            campaign=_campaign(),
            definition=_definition(),
            state=_state(active=True),
        )
