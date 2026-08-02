from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from player_wiki.character_models import CharacterDefinition, CharacterRecord, CharacterStateRecord
from player_wiki.character_service import validate_state
from player_wiki.character_state_service import CharacterStateService
from player_wiki.character_store import CharacterStateStore
from player_wiki.divine_avatar_forms import (
    AVATAR_OF_MOURNING_FORM_KEY,
    active_divine_avatar_transient_effects,
    character_has_divine_avatar_forms,
    divine_avatar_action_success_message,
    divine_avatar_form_state_from,
    divine_avatar_forms_state_from,
    end_divine_avatar_form_automatically,
    normalize_divine_avatar_forms_state,
    present_divine_avatar_forms_state,
    transition_divine_avatar_form,
)


def _definition(*, features=None, wisdom=16, system="DND-5E") -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": "tod",
            "name": "Tod",
            "status": "active",
            "system": system,
            "profile": {},
            "stats": {
                "max_hp": 50,
                "armor_class": 16,
                "proficiency_bonus": 3,
                "ability_scores": {"wis": {"score": wisdom, "modifier": (wisdom - 10) // 2}},
            },
            "skills": [],
            "proficiencies": {},
            "attacks": [],
            "features": features
            if features is not None
            else [
                {
                    "name": "Divine Avatar Forms",
                    "page_ref": "mechanics/divine-avatar-forms",
                }
            ],
            "spellcasting": {},
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {},
        }
    )


def _state(*, current_hp=20, rounds=0, exhaustion=0, combat_revision=None):
    avatar = {
        "schema_version": 1,
        "form_version": 1,
        "rounds_elapsed": rounds,
    }
    if combat_revision is not None:
        avatar["last_combat_revision"] = combat_revision
    return {
        "vitals": {"current_hp": current_hp, "temp_hp": 0},
        "spell_slots": [{"level": 1, "max": 4, "used": 2}],
        "resources": [],
        "inventory": [],
        "currency": {},
        "notes": {},
        "exhaustion_level": exhaustion,
        "feature_states": {
            "divine_avatar_forms": {
                "schema_version": 1,
                "active_form": AVATAR_OF_MOURNING_FORM_KEY,
                "forms": {AVATAR_OF_MOURNING_FORM_KEY: avatar},
            }
        },
    }


def test_grants_require_structured_effect_or_exact_legacy_page_ref():
    title_only = _definition(features=[{"name": "Divine Avatar Forms"}])
    assert character_has_divine_avatar_forms(title_only) is False

    exact_page = _definition()
    assert character_has_divine_avatar_forms(exact_page) is True

    structured = _definition(
        features=[
            {
                "name": "Something Else",
                "campaign_option": {
                    "mechanic_effects": [
                        {
                            "kind": "divine_avatar_form_grant",
                            "mechanic_key": "divine_avatar_forms",
                            "mechanic_version": 1,
                            "form_key": "avatar_of_mourning",
                            "form_version": 1,
                        }
                    ]
                },
            }
        ]
    )
    assert character_has_divine_avatar_forms(structured) is True
    assert character_has_divine_avatar_forms(_definition(system="Xianxia")) is False


def test_action_success_messages_share_transition_action_normalization():
    assert (
        divine_avatar_action_success_message("correct_end_cost")
        == "Avatar of Mourning's end cost corrected."
    )
    assert (
        divine_avatar_action_success_message("strength-of-remembrance")
        == "Strength of Remembrance marked used."
    )


def test_transient_effect_bundle_is_absolute_and_does_not_store_true_wisdom():
    definition = _definition(wisdom=18)
    effects = active_divine_avatar_transient_effects(definition, _state())
    assert effects == {
        "effect_id": "divine_avatar_form:avatar_of_mourning@1",
        "ability_score_overrides": {"wis": 26},
        "stat_adjustments": {"armor_class": 4},
        "spellcasting_adjustments": {"save_dc": 3, "attack_bonus": 3},
    }
    assert definition.stats["ability_scores"]["wis"]["score"] == 18
    inactive = _state()
    inactive["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    assert active_divine_avatar_transient_effects(definition, inactive) == {}


def test_future_form_versions_and_active_pending_state_fail_closed():
    future = _state()
    future["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    future["feature_states"]["divine_avatar_forms"]["forms"][AVATAR_OF_MOURNING_FORM_KEY][
        "schema_version"
    ] = 2
    with pytest.raises(ValueError, match="newer unsupported"):
        transition_divine_avatar_form(
            _definition(),
            future,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )
    presented = present_divine_avatar_forms_state(_definition(), future)
    assert presented["forms"][0]["activation_available"] is False
    assert presented["state_errors"]

    contradictory = _state()
    contradictory["feature_states"]["divine_avatar_forms"]["pending_resolution"] = {
        "kind": "avatar_form_end_cost",
        "form_key": AVATAR_OF_MOURNING_FORM_KEY,
        "status": "pending",
        "resolution_id": "old",
    }
    assert active_divine_avatar_transient_effects(_definition(), contradictory) == {}


@pytest.mark.parametrize(
    ("state_change", "message"),
    [
        (lambda state: state["vitals"].update(current_hp=0), "unconscious"),
        (lambda state: state.update(exhaustion_level=6), "fatal exhaustion"),
    ],
)
def test_active_form_requires_a_conscious_nonfatally_exhausted_character(
    state_change, message
):
    state = _state()
    state_change(state)
    assert active_divine_avatar_transient_effects(_definition(), state) == {}
    presented = present_divine_avatar_forms_state(_definition(), state)
    assert message in presented["state_errors"][0]
    assert presented["forms"][0]["mourning_wave_available"] is False


def test_automatic_unconscious_end_rejects_orphan_and_future_active_state():
    orphan_definition = _definition(features=[{"name": "Divine Avatar Forms"}])
    with pytest.raises(ValueError, match="not recorded"):
        end_divine_avatar_form_automatically(
            orphan_definition,
            _state(current_hp=0),
            AVATAR_OF_MOURNING_FORM_KEY,
            reason="unconscious",
        )
    future = _state(current_hp=0)
    future["feature_states"]["divine_avatar_forms"]["forms"][
        AVATAR_OF_MOURNING_FORM_KEY
    ]["schema_version"] = 2
    with pytest.raises(ValueError, match="newer unsupported"):
        end_divine_avatar_form_automatically(
            _definition(),
            future,
            AVATAR_OF_MOURNING_FORM_KEY,
            reason="unconscious",
        )


def test_activation_is_blocked_before_mutation_at_fatal_exhaustion():
    state = _state(exhaustion=6)
    state["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    presented = present_divine_avatar_forms_state(_definition(), state)
    assert presented["forms"][0]["activation_available"] is False
    assert presented["forms"][0]["exhaustion_gate_met"] is False
    assert "fatal exhaustion" in presented["forms"][0]["activation_blocked_reason"]
    with pytest.raises(ValueError, match="fatal exhaustion"):
        transition_divine_avatar_form(
            _definition(),
            state,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )

def test_unknown_form_payload_survives_normalization():
    unknown = {"schema_version": 9, "opaque": {"keep": True}}
    normalized = normalize_divine_avatar_forms_state(
        {"forms": {"future_avatar": unknown}, "active_form": ""}
    )
    assert normalized["forms"]["future_avatar"] == unknown
    with_history = normalize_divine_avatar_forms_state(
        {
            "forms": {},
            "action_history": [
                {"sequence": 1, "action": "future_action", "opaque": {"keep": True}}
            ],
        }
    )
    assert with_history["action_history"][0]["opaque"] == {"keep": True}


def test_malformed_schema_one_containers_are_preserved_and_fail_closed():
    malformed = _state()
    malformed_forms_state = malformed["feature_states"]["divine_avatar_forms"]
    malformed_forms_state["active_form"] = ""
    malformed_forms_state["forms"] = "opaque-forms"
    malformed_forms_state["action_history"] = {"opaque": True}
    presented = present_divine_avatar_forms_state(_definition(), malformed)
    assert presented["state_errors"]
    assert presented["forms"][0]["activation_available"] is False
    normalized = divine_avatar_forms_state_from(malformed)
    assert normalized["invalid_containers"]["forms"] == "opaque-forms"
    assert normalized["invalid_containers"]["action_history"] == {"opaque": True}
    with pytest.raises(ValueError, match="Malformed Divine Avatar Forms state"):
        transition_divine_avatar_form(
            _definition(),
            malformed,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )

    malformed_turn_ids = _state()
    malformed_turn_ids["feature_states"]["divine_avatar_forms"]["forms"][
        AVATAR_OF_MOURNING_FORM_KEY
    ]["processed_turn_ids"] = 42
    presented_turn_ids = present_divine_avatar_forms_state(
        _definition(), malformed_turn_ids
    )
    assert "processed_turn_ids" in presented_turn_ids["state_errors"][0]
    normalized_avatar = divine_avatar_form_state_from(
        malformed_turn_ids, AVATAR_OF_MOURNING_FORM_KEY
    )
    assert normalized_avatar["invalid_containers"]["processed_turn_ids"] == 42


def test_nonobject_avatar_root_survives_validation_and_json_persistence_fail_closed():
    definition = _definition()
    state = _state()
    opaque_root = ["pending", {"opaque": True}]
    state["feature_states"]["divine_avatar_forms"] = opaque_root

    presented = present_divine_avatar_forms_state(definition, state)
    assert presented["state_errors"]
    assert presented["forms"][0]["activation_available"] is False
    normalized = divine_avatar_forms_state_from(state)
    assert normalized["invalid_containers"]["state"] == opaque_root
    with pytest.raises(ValueError, match="Divine Avatar Forms state must be an object"):
        transition_divine_avatar_form(
            definition,
            state,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )

    validated = validate_state(definition, state)
    validated_avatar = validated["feature_states"]["divine_avatar_forms"]
    assert validated_avatar["invalid_containers"]["state"] == opaque_root
    prepared = CharacterStateStore.prepare_initial_state(definition, state)
    persisted = json.loads(prepared.state_json)
    assert persisted["feature_states"]["divine_avatar_forms"]["invalid_containers"][
        "state"
    ] == opaque_root


@pytest.mark.parametrize(
    ("container_key", "opaque_value"),
    [
        ("pending_resolution", ["unresolved"]),
        ("last_resolution", "opaque-resolution"),
        ("last_transition", 17),
        ("undo_snapshot", ["opaque-undo"]),
    ],
)
def test_nonobject_lifecycle_containers_are_preserved_and_block_actions(
    container_key, opaque_value
):
    definition = _definition()
    state = _state()
    state["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    state["feature_states"]["divine_avatar_forms"][container_key] = opaque_value

    presented = present_divine_avatar_forms_state(definition, state)
    assert presented["state_errors"]
    assert presented["forms"][0]["activation_available"] is False
    normalized = divine_avatar_forms_state_from(state)
    assert normalized["invalid_containers"][container_key] == opaque_value
    with pytest.raises(ValueError, match=f"{container_key} must be an object"):
        transition_divine_avatar_form(
            definition,
            state,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )
    persisted = CharacterStateStore.prepare_initial_state(definition, state)
    persisted_avatar = json.loads(persisted.state_json)["feature_states"][
        "divine_avatar_forms"
    ]
    assert persisted_avatar["invalid_containers"][container_key] == opaque_value


@pytest.mark.parametrize(
    ("version_path", "invalid_value"),
    [
        (("schema_version",), "future"),
        (("forms", AVATAR_OF_MOURNING_FORM_KEY, "schema_version"), "future"),
        (("forms", AVATAR_OF_MOURNING_FORM_KEY, "form_version"), "future"),
    ],
)
def test_present_invalid_version_tokens_are_preserved_and_fail_closed(
    version_path, invalid_value
):
    definition = _definition()
    state = _state()
    state["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    target = state["feature_states"]["divine_avatar_forms"]
    for path_part in version_path[:-1]:
        target = target[path_part]
    target[version_path[-1]] = invalid_value

    presented = present_divine_avatar_forms_state(definition, state)
    assert presented["state_errors"]
    assert presented["forms"][0]["activation_available"] is False
    normalized = divine_avatar_forms_state_from(state)
    normalized_target = normalized
    for path_part in version_path[:-1]:
        normalized_target = normalized_target[path_part]
    assert normalized_target[version_path[-1]] == invalid_value
    with pytest.raises(ValueError, match="must be a nonnegative integer"):
        transition_divine_avatar_form(
            definition,
            state,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            confirmed=True,
        )


def test_external_projection_errors_fail_close_actions_but_keep_safe_end():
    presented = present_divine_avatar_forms_state(
        _definition(),
        _state(),
        external_errors=["Avatar projection failed."],
    )
    form = presented["forms"][0]
    assert presented["state_errors"] == ["Avatar projection failed."]
    assert form["mourning_wave_available"] is False
    assert form["strength_of_remembrance_available"] is False
    assert form["end_available"] is True


def test_combat_revision_remains_monotonic_across_end_undo_and_reend():
    definition = _definition()
    state = _state(rounds=1, combat_revision=40)
    ended = transition_divine_avatar_form(
        definition,
        state,
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        confirmed=True,
    ).state
    first_resolution_id = divine_avatar_forms_state_from(ended)["pending_resolution"][
        "resolution_id"
    ]
    restored = transition_divine_avatar_form(
        definition,
        ended,
        AVATAR_OF_MOURNING_FORM_KEY,
        "undo_last_action",
        confirmed=True,
    ).state
    restored_avatar = divine_avatar_form_state_from(restored, AVATAR_OF_MOURNING_FORM_KEY)
    assert restored_avatar["active"] is True
    assert restored_avatar["last_combat_revision"] == 40

    replay = transition_divine_avatar_form(
        definition,
        restored,
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        combat_revision=40,
        combat_turn_token="combat:a",
    )
    assert replay.changed is False
    advanced = transition_divine_avatar_form(
        definition,
        restored,
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        combat_revision=41,
        combat_turn_token="combat:a",
    ).state
    reended = transition_divine_avatar_form(
        definition,
        advanced,
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        confirmed=True,
    ).state
    second_resolution_id = divine_avatar_forms_state_from(reended)["pending_resolution"][
        "resolution_id"
    ]
    assert second_resolution_id != first_resolution_id


def test_replayed_token_still_checkpoints_a_newer_combat_revision():
    definition = _definition()
    state = _state(rounds=1, combat_revision=40)
    state["feature_states"]["divine_avatar_forms"]["forms"][
        AVATAR_OF_MOURNING_FORM_KEY
    ]["processed_turn_ids"] = ["combat:a"]
    checkpointed = transition_divine_avatar_form(
        definition,
        state,
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        combat_revision=50,
        combat_turn_token="combat:a",
    )
    assert checkpointed.changed is True
    avatar = divine_avatar_form_state_from(
        checkpointed.state, AVATAR_OF_MOURNING_FORM_KEY
    )
    assert avatar["rounds_elapsed"] == 1
    assert avatar["last_combat_revision"] == 50
    stale = transition_divine_avatar_form(
        definition,
        checkpointed.state,
        AVATAR_OF_MOURNING_FORM_KEY,
        "advance_turn",
        combat_revision=45,
        combat_turn_token="combat:b",
    )
    assert stale.changed is False


def test_end_cost_tracks_actual_capped_exhaustion_and_corrects_to_baseline():
    definition = _definition()
    ended = transition_divine_avatar_form(
        definition,
        _state(rounds=2, exhaustion=5),
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        confirmed=True,
    ).state
    forms_state = divine_avatar_forms_state_from(ended)
    pending = forms_state["pending_resolution"]
    assert ended["exhaustion_level"] == 6
    assert pending["exhaustion_gained"] == 2
    assert pending["exhaustion_applied"] == 1

    corrected = transition_divine_avatar_form(
        definition,
        ended,
        AVATAR_OF_MOURNING_FORM_KEY,
        "correct_end_cost",
        confirmed=True,
        resolution_id=pending["resolution_id"],
        correction={"rounds": 0, "exhaustion_gained": 0, "radiant_damage_dice": "0d12"},
    ).state
    assert corrected["exhaustion_level"] == 5
    corrected_cost = divine_avatar_form_state_from(
        corrected, AVATAR_OF_MOURNING_FORM_KEY
    )["last_end_cost"]
    assert corrected_cost["exhaustion_applied"] == 0
    correction_audit = divine_avatar_forms_state_from(corrected)["action_history"][-1]
    assert correction_audit["action"] == "correct_end_cost"
    assert correction_audit["before"]["exhaustion_gained"] == 2
    assert correction_audit["after"]["exhaustion_gained"] == 0


def test_end_undo_refuses_after_resolution_or_unrelated_exhaustion_change():
    definition = _definition()
    ended = transition_divine_avatar_form(
        definition,
        _state(rounds=1),
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        confirmed=True,
    ).state
    pending = divine_avatar_forms_state_from(ended)["pending_resolution"]
    changed_exhaustion = dict(ended)
    changed_exhaustion["exhaustion_level"] = 2
    with pytest.raises(ValueError, match="Exhaustion changed"):
        transition_divine_avatar_form(
            definition,
            changed_exhaustion,
            AVATAR_OF_MOURNING_FORM_KEY,
            "undo_last_action",
            confirmed=True,
        )

    resolved = transition_divine_avatar_form(
        definition,
        ended,
        AVATAR_OF_MOURNING_FORM_KEY,
        "resolve_end_cost",
        confirmed=True,
        resolution_id=pending["resolution_id"],
        radiant_damage_applied=12,
    ).state
    resolved_presenter = present_divine_avatar_forms_state(definition, resolved)
    assert resolved_presenter["last_resolution"]["rounds"] == 1
    assert resolved_presenter["last_resolution"]["radiant_damage_applied"] == 12
    assert resolved_presenter["can_correct_last_resolution"] is True
    corrected_resolution = transition_divine_avatar_form(
        definition,
        resolved,
        AVATAR_OF_MOURNING_FORM_KEY,
        "correct_end_cost",
        confirmed=True,
        resolution_id=pending["resolution_id"],
        correction={"radiant_damage_applied": 13},
    ).state
    assert (
        present_divine_avatar_forms_state(definition, corrected_resolution)[
            "last_resolution"
        ]["radiant_damage_applied"]
        == 13
    )
    with pytest.raises(ValueError, match="no Divine Avatar Form action"):
        transition_divine_avatar_form(
            definition,
            corrected_resolution,
            AVATAR_OF_MOURNING_FORM_KEY,
            "undo_last_action",
            confirmed=True,
        )


def test_end_undo_cannot_reactivate_form_after_hit_points_fall_to_zero():
    definition = _definition()
    ended = transition_divine_avatar_form(
        definition,
        _state(rounds=1),
        AVATAR_OF_MOURNING_FORM_KEY,
        "end",
        confirmed=True,
    ).state
    ended["vitals"]["current_hp"] = 0
    with pytest.raises(ValueError, match="unconscious"):
        transition_divine_avatar_form(
            definition,
            ended,
            AVATAR_OF_MOURNING_FORM_KEY,
            "undo_last_action",
            confirmed=True,
        )


def test_service_threads_commit_false_to_state_store_for_vitals_and_avatar():
    class Store:
        commits: list[bool] = []

        def replace_state(self, definition, state, *, expected_revision, updated_by_user_id=None, commit=True):
            self.commits.append(commit)
            return CharacterStateRecord(
                campaign_slug=definition.campaign_slug,
                character_slug=definition.character_slug,
                revision=expected_revision + 1,
                state=state,
                updated_at=datetime.now(timezone.utc),
                updated_by_user_id=updated_by_user_id,
            )

    definition = _definition()
    state = _state()
    record = CharacterRecord(
        definition=definition,
        import_metadata=None,
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=1,
            state=state,
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=None,
        ),
    )
    store = Store()
    service = CharacterStateService(store)
    service.update_divine_avatar_form(
        record,
        AVATAR_OF_MOURNING_FORM_KEY,
        "mourning_wave",
        expected_revision=1,
        confirmed=True,
        commit=False,
    )
    service.update_vitals(record, expected_revision=1, current_hp=19, commit=False)
    assert store.commits == [False, False]


def test_service_validates_proposed_avatar_state_before_persistence():
    class Store:
        def replace_state(self, *args, **kwargs):
            raise AssertionError("Rejected proposed state must not be persisted.")

    definition = _definition()
    state = _state()
    state["feature_states"]["divine_avatar_forms"]["active_form"] = ""
    record = CharacterRecord(
        definition=definition,
        import_metadata=None,
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=1,
            state=state,
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=None,
        ),
    )
    seen_states = []

    def reject_projection(proposed_state):
        seen_states.append(proposed_state)
        assert (
            proposed_state["feature_states"]["divine_avatar_forms"]["active_form"]
            == AVATAR_OF_MOURNING_FORM_KEY
        )
        proposed_state["vitals"]["temp_hp"] = -999
        raise ValueError("Projected Avatar state is invalid.")

    with pytest.raises(ValueError, match="Projected Avatar state is invalid"):
        CharacterStateService(Store()).update_divine_avatar_form(
            record,
            AVATAR_OF_MOURNING_FORM_KEY,
            "activate",
            expected_revision=1,
            confirmed=True,
            proposed_state_validator=reject_projection,
        )
    assert len(seen_states) == 1
    assert record.state_record.state["vitals"]["temp_hp"] == 0
