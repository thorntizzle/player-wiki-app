from __future__ import annotations

from flask import Flask

import player_wiki.character_divine_avatar_routes as route_module


class _RecordingStateService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def update_divine_avatar_form(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "updated"


def _registered_app(monkeypatch, *, validator_builder=None):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    service = _RecordingStateService()
    mutation_calls = []

    monkeypatch.setattr(
        route_module,
        "campaign_scope_access_required",
        lambda _scope: lambda view: view,
    )

    def run_character_state_mutation(campaign_slug, character_slug, **kwargs):
        mutation_calls.append((campaign_slug, character_slug, kwargs))
        return kwargs["action"]("record", 14, 27)

    route_module.register_character_divine_avatar_route(
        app,
        dependencies=route_module.CharacterDivineAvatarRouteDependencies(
            run_character_state_mutation=run_character_state_mutation,
            get_character_state_service=lambda: service,
            build_proposed_state_validator=validator_builder,
        ),
    )
    return app, service, mutation_calls


def test_character_avatar_route_forwards_structured_end_cost_correction(monkeypatch):
    app, service, mutation_calls = _registered_app(monkeypatch)

    response = app.test_client().post(
        "/campaigns/linden-pass/characters/tod/divine-avatar-forms/"
        "avatar_of_mourning/correct-end-cost",
        data={
            "confirmed": "1",
            "destructive_acknowledgement": "1",
            "resolution_id": "avatar_of_mourning:2:1",
            "correction_rounds": "3",
            "correction_exhaustion_gained": "2",
            "correction_radiant_damage_dice": "15d12",
            "correction_radiant_damage_applied": "27",
            "correction_reason": "table correction",
        },
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "updated"
    assert len(mutation_calls) == 1
    campaign_slug, character_slug, mutation = mutation_calls[0]
    assert (campaign_slug, character_slug) == ("linden-pass", "tod")
    assert mutation["anchor"] == "character-divine-avatar-forms"
    assert mutation["invalidate_live_views"] is True
    assert mutation["success_message"] == "Avatar of Mourning's end cost corrected."

    args, kwargs = service.calls[0]
    assert args == ("record", "avatar_of_mourning", "correct_end_cost")
    assert kwargs == {
        "expected_revision": 14,
        "confirmed": True,
        "resolution_id": "avatar_of_mourning:2:1",
        "radiant_damage_applied": None,
        "correction": {
            "rounds": "3",
            "exhaustion_gained": "2",
            "radiant_damage_dice": "15d12",
            "radiant_damage_applied": "27",
            "reason": "table correction",
        },
        "updated_by_user_id": 27,
    }


def test_character_avatar_route_requires_server_acknowledgement_for_resolve(monkeypatch):
    app, service, _mutation_calls = _registered_app(monkeypatch)
    client = app.test_client()

    response = client.post(
        "/campaigns/linden-pass/characters/tod/divine-avatar-forms/"
        "avatar_of_mourning/resolve_end_cost",
        data={
            "confirmed": "1",
            "resolution_id": "avatar_of_mourning:2:1",
            "radiant_damage_applied": "41",
        },
    )

    assert response.status_code == 200
    _args, kwargs = service.calls[0]
    assert kwargs["confirmed"] is False
    assert kwargs["resolution_id"] == "avatar_of_mourning:2:1"
    assert kwargs["radiant_damage_applied"] == "41"


def test_character_avatar_route_wires_projection_validator_before_persistence(monkeypatch):
    proposed_states = []

    def validate(proposed_state):
        proposed_states.append(proposed_state)

    builder_calls = []

    def build_validator(campaign_slug, record, action):
        builder_calls.append((campaign_slug, record, action))
        return validate

    app, service, _mutation_calls = _registered_app(
        monkeypatch,
        validator_builder=build_validator,
    )

    response = app.test_client().post(
        "/campaigns/linden-pass/characters/tod/divine-avatar-forms/"
        "avatar_of_mourning/activate",
        data={"confirmed": "1"},
    )

    assert response.status_code == 200
    assert builder_calls == [("linden-pass", "record", "activate")]
    _args, kwargs = service.calls[0]
    assert kwargs["proposed_state_validator"] is validate
