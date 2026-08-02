from __future__ import annotations

from types import SimpleNamespace

import pytest

from player_wiki.campaign_combat_store import CampaignCombatConflictError
from player_wiki.campaign_combat_service import CampaignCombatValidationError
from player_wiki.character_store import CharacterStateConflictError


CAMPAIGN_SLUG = "linden-pass"
CHARACTER_SLUG = "arden-march"


def _active_avatar_record(*, revision: int = 41):
    return SimpleNamespace(
        state_record=SimpleNamespace(
            revision=revision,
            state={
                "feature_states": {
                    "divine_avatar_forms": {
                        "active_form": "avatar_of_mourning",
                        "forms": {"avatar_of_mourning": {}},
                    }
                }
            },
        )
    )


def _seed_player(service, users, *, turn_value: int = 20):
    return service.add_player_character(
        CAMPAIGN_SLUG,
        character_slug=CHARACTER_SLUG,
        turn_value=turn_value,
        created_by_user_id=users["dm"]["id"],
    )


def test_advance_turn_dispatches_avatar_with_updated_tracker_revision_and_session_bump(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        record = _active_avatar_record()
        avatar_calls = []
        session_calls = []

        monkeypatch.setattr(
            service.character_repository,
            "get_visible_character",
            lambda campaign_slug, character_slug: record,
        )

        def update_avatar(current_record, form_key, action, **kwargs):
            avatar_calls.append((current_record, form_key, action, kwargs))
            return SimpleNamespace(revision=current_record.state_record.revision + 1)

        monkeypatch.setattr(
            service.character_state_service,
            "update_divine_avatar_form",
            update_avatar,
        )
        service.session_revision_callback = lambda *args, **kwargs: session_calls.append(
            (args, kwargs)
        )

        tracker = service.advance_turn(
            CAMPAIGN_SLUG,
            updated_by_user_id=users["dm"]["id"],
        )

    assert tracker.current_combatant_id == player.id
    assert avatar_calls == [
        (
            record,
            "avatar_of_mourning",
            "advance_turn",
            {
                "expected_revision": record.state_record.revision,
                "combat_revision": tracker.revision,
                "updated_by_user_id": users["dm"]["id"],
                "commit": False,
            },
        )
    ]
    assert session_calls == [
        (
            (CAMPAIGN_SLUG,),
            {
                "updated_by_user_id": users["dm"]["id"],
                "commit": False,
            },
        )
    ]


def test_set_current_dispatches_only_when_target_changes(app, users, monkeypatch):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        record = _active_avatar_record()
        avatar_revisions = []
        session_calls = []

        monkeypatch.setattr(
            service.character_repository,
            "get_visible_character",
            lambda campaign_slug, character_slug: record,
        )

        def update_avatar(current_record, form_key, action, **kwargs):
            avatar_revisions.append(kwargs["combat_revision"])
            return SimpleNamespace(revision=current_record.state_record.revision + 1)

        monkeypatch.setattr(
            service.character_state_service,
            "update_divine_avatar_form",
            update_avatar,
        )
        service.session_revision_callback = lambda *args, **kwargs: session_calls.append(
            (args, kwargs)
        )

        first = service.set_current_turn(
            CAMPAIGN_SLUG,
            player.id,
            updated_by_user_id=users["dm"]["id"],
        )
        service.update_resources(
            CAMPAIGN_SLUG,
            player.id,
            has_action=False,
            has_bonus_action=False,
            has_reaction=False,
            movement_remaining=0,
            updated_by_user_id=users["dm"]["id"],
        )
        tracker_before_repeat = service.get_tracker(CAMPAIGN_SLUG)
        second = service.set_current_turn(
            CAMPAIGN_SLUG,
            player.id,
            updated_by_user_id=users["dm"]["id"],
        )
        player_after_repeat = service.get_combatant(CAMPAIGN_SLUG, player.id)

    assert avatar_revisions == [first.revision]
    assert second == tracker_before_repeat
    assert player_after_repeat is not None
    assert player_after_repeat.has_action is False
    assert player_after_repeat.has_bonus_action is False
    assert player_after_repeat.has_reaction is False
    assert player_after_repeat.movement_remaining == 0
    assert len(session_calls) == 1


def test_advance_turn_reenters_same_solo_combatant_on_each_tracker_revision(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        record = _active_avatar_record()
        avatar_revisions = []

        monkeypatch.setattr(
            service.character_repository,
            "get_visible_character",
            lambda campaign_slug, character_slug: record,
        )

        def update_avatar(current_record, form_key, action, **kwargs):
            avatar_revisions.append(kwargs["combat_revision"])
            return SimpleNamespace(revision=current_record.state_record.revision + 1)

        monkeypatch.setattr(
            service.character_state_service,
            "update_divine_avatar_form",
            update_avatar,
        )
        service.session_revision_callback = lambda *args, **kwargs: None

        first = service.advance_turn(
            CAMPAIGN_SLUG,
            updated_by_user_id=users["dm"]["id"],
        )
        second = service.advance_turn(
            CAMPAIGN_SLUG,
            updated_by_user_id=users["dm"]["id"],
        )

    assert first.current_combatant_id == second.current_combatant_id == player.id
    assert second.round_number == first.round_number + 1
    assert avatar_revisions == [first.revision, second.revision]


def test_player_vitals_update_bumps_session_revision_after_character_state_change(
    app,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        record = service.character_repository.get_visible_character(
            CAMPAIGN_SLUG,
            CHARACTER_SLUG,
        )
        assert record is not None
        session_calls = []
        service.session_revision_callback = lambda *args, **kwargs: session_calls.append(
            (args, kwargs)
        )

        service.update_player_character_vitals(
            CAMPAIGN_SLUG,
            player.id,
            expected_revision=record.state_record.revision,
            current_hp=int(
                (record.state_record.state.get("vitals") or {}).get("current_hp") or 0
            ),
            temp_hp=int(
                (record.state_record.state.get("vitals") or {}).get("temp_hp") or 0
            ),
            updated_by_user_id=users["dm"]["id"],
        )

    assert session_calls == [
        (
            (CAMPAIGN_SLUG,),
            {
                "updated_by_user_id": users["dm"]["id"],
                "commit": False,
            },
        )
    ]


def test_player_vitals_combat_failure_rolls_back_character_state_and_session_bump(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        record_before = service.character_repository.get_visible_character(
            CAMPAIGN_SLUG,
            CHARACTER_SLUG,
        )
        assert record_before is not None
        combatant_before = service.get_combatant(CAMPAIGN_SLUG, player.id)
        tracker_before = service.get_tracker(CAMPAIGN_SLUG)
        session_calls = []
        service.session_revision_callback = lambda *args, **kwargs: session_calls.append(
            (args, kwargs)
        )
        monkeypatch.setattr(
            service.store,
            "update_combatant",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                CampaignCombatConflictError("snapshot write failed")
            ),
        )

        with pytest.raises(CampaignCombatValidationError, match="tracker row"):
            service.update_player_character_vitals(
                CAMPAIGN_SLUG,
                player.id,
                expected_revision=record_before.state_record.revision,
                current_hp=int(
                    (record_before.state_record.state.get("vitals") or {}).get("current_hp")
                    or 0
                ),
                temp_hp=(
                    int(
                        (record_before.state_record.state.get("vitals") or {}).get("temp_hp")
                        or 0
                    )
                    + 1
                ),
                updated_by_user_id=users["dm"]["id"],
            )

        record_after = service.character_repository.get_visible_character(
            CAMPAIGN_SLUG,
            CHARACTER_SLUG,
        )
        combatant_after = service.get_combatant(CAMPAIGN_SLUG, player.id)
        tracker_after = service.get_tracker(CAMPAIGN_SLUG)

    assert record_after is not None
    assert record_after.state_record == record_before.state_record
    assert combatant_after == combatant_before
    assert tracker_after == tracker_before
    assert session_calls == []


def test_avatar_failure_rolls_back_set_current_tracker_and_resource_refresh(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = _seed_player(service, users)
        npc = service.add_npc_combatant(
            CAMPAIGN_SLUG,
            display_name="Rollback Sentinel",
            turn_value=10,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        service.set_current_turn(
            CAMPAIGN_SLUG,
            npc.id,
            updated_by_user_id=users["dm"]["id"],
        )
        tracker_before = service.get_tracker(CAMPAIGN_SLUG)
        player_before = service.get_combatant(CAMPAIGN_SLUG, player.id)
        session_calls = []

        monkeypatch.setattr(
            service.character_repository,
            "get_visible_character",
            lambda campaign_slug, character_slug: _active_avatar_record(),
        )
        monkeypatch.setattr(
            service.character_state_service,
            "update_divine_avatar_form",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                CharacterStateConflictError("stale avatar state")
            ),
        )
        service.session_revision_callback = lambda *args, **kwargs: session_calls.append(
            (args, kwargs)
        )

        with pytest.raises(CampaignCombatValidationError, match="turn was not updated"):
            service.set_current_turn(
                CAMPAIGN_SLUG,
                player.id,
                updated_by_user_id=users["dm"]["id"],
            )

        tracker_after = service.get_tracker(CAMPAIGN_SLUG)
        player_after = service.get_combatant(CAMPAIGN_SLUG, player.id)

    assert tracker_after.current_combatant_id == tracker_before.current_combatant_id == npc.id
    assert tracker_after.round_number == tracker_before.round_number
    assert tracker_after.revision == tracker_before.revision
    assert player_before is not None and player_after is not None
    assert player_after.revision == player_before.revision
    assert player_after.movement_remaining == player_before.movement_remaining
    assert player_after.has_action == player_before.has_action
    assert player_after.has_bonus_action == player_before.has_bonus_action
    assert player_after.has_reaction == player_before.has_reaction
    assert session_calls == []
