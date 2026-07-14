from __future__ import annotations

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_combat_service import CampaignCombatValidationError
from tests.helpers.api_test_helpers import (
    _configure_xianxia_campaign,
    api_headers,
    issue_api_token,
)


CREATE_PATH = "/api/v1/campaigns/linden-pass/combat/npc-combatants"


def _dm_token(app, users, *, label: str) -> str:
    return issue_api_token(app, users["dm"]["email"], label=label)


def _combat_state(app):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        tracker = service.get_tracker("linden-pass")
        combatants = service.list_combatants("linden-pass")
        return {
            "tracker": tracker,
            "combatants": combatants,
        }


def test_custom_npc_create_preserves_scope_login_and_manager_order(
    client,
    app,
    users,
    monkeypatch,
):
    missing = client.post(CREATE_PATH.replace("linden-pass", "missing-campaign"))
    assert missing.status_code == 404

    anonymous = client.post(CREATE_PATH)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    service = app.extensions["campaign_combat_service"]

    def eager_work(*_args, **_kwargs):
        raise AssertionError(
            "management denial must precede JSON, system, service, and payload work"
        )

    monkeypatch.setattr(service, "add_npc_combatant", eager_work)
    monkeypatch.setattr(service, "get_tracker", eager_work)
    _configure_xianxia_campaign(app)
    for user_key in ("owner", "party", "outsider"):
        token = issue_api_token(
            app,
            users[user_key]["email"],
            label=f"custom-npc-manager-order-{user_key}",
        )
        denied = client.post(
            CREATE_PATH,
            headers={**api_headers(token), "Content-Type": "application/json"},
            data="{",
        )
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"


def test_custom_npc_create_preserves_handler_user_fallback(
    client,
    app,
    users,
    monkeypatch,
):
    dm = None
    with app.app_context():
        dm = app.extensions["auth_store"].get_user_by_id(users["dm"]["id"])
    calls = iter((dm, None))
    monkeypatch.setattr(api_module, "get_current_user", lambda: next(calls))

    response = client.post(
        CREATE_PATH,
        headers=api_headers(_dm_token(app, users, label="custom-npc-user-fallback")),
        json={"display_name": "Never Created"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == {
        "code": "auth_required",
        "message": "Authentication required.",
    }


def test_custom_npc_create_preserves_scope_guard_fault_propagation(
    client,
    app,
    monkeypatch,
):
    with app.app_context():
        repository = app.extensions["repository_store"].get()

    def guard_fault(*_args, **_kwargs):
        raise RuntimeError("characterized combat scope guard fault")

    monkeypatch.setattr(type(repository), "get_campaign", guard_fault)
    with pytest.raises(RuntimeError, match="characterized combat scope guard fault"):
        client.post(CREATE_PATH)


def test_custom_npc_create_preserves_view_as_and_csrf_before_service(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    service = app.extensions["campaign_combat_service"]
    original_add = service.add_npc_combatant

    def eager_add(*_args, **_kwargs):
        raise AssertionError("request guard must precede NPC creation")

    monkeypatch.setattr(service, "add_npc_combatant", eager_add)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    view_as_denied = client.post(CREATE_PATH, json={"display_name": "Blocked"})
    assert view_as_denied.status_code == 403
    assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    csrf_denied = client.post(CREATE_PATH, json={"display_name": "Blocked"})
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    monkeypatch.setattr(service, "add_npc_combatant", original_add)
    bearer_allowed = app.test_client().post(
        CREATE_PATH,
        headers=api_headers(_dm_token(app, users, label="custom-npc-csrf-bearer")),
        json={
            "display_name": "Bearer Allowed",
            "current_hp": 5,
            "max_hp": 5,
        },
    )
    assert bearer_allowed.status_code == 200


@pytest.mark.parametrize(
    ("body", "expected_message"),
    (
        ("{", "Request body must be a JSON object."),
        ('["not", "an", "object"]', "Request body must be a JSON object."),
        ("", "NPC name is required."),
    ),
)
def test_custom_npc_create_preserves_json_and_empty_body_validation(
    client,
    app,
    users,
    body,
    expected_message,
):
    response = client.post(
        CREATE_PATH,
        headers={
            **api_headers(_dm_token(app, users, label=f"custom-npc-json-{len(body)}")),
            "Content-Type": "application/json",
        },
        data=body,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": expected_message,
    }


def test_custom_npc_create_preserves_json_before_supported_system_order(
    client,
    app,
    users,
    monkeypatch,
):
    _configure_xianxia_campaign(app)
    service = app.extensions["campaign_combat_service"]

    def eager_add(*_args, **_kwargs):
        raise AssertionError("unsupported combat must not create an NPC")

    monkeypatch.setattr(service, "add_npc_combatant", eager_add)
    token = _dm_token(app, users, label="custom-npc-unsupported")

    malformed = client.post(
        CREATE_PATH,
        headers={**api_headers(token), "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["message"] == (
        "Request body must be a JSON object."
    )

    unsupported = client.post(
        CREATE_PATH,
        headers=api_headers(token),
        json={"display_name": "Never Created"},
    )
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"] == {
        "code": "validation_error",
        "message": "Combat tracker support for Xianxia is not available yet.",
    }


@pytest.mark.parametrize(
    ("request_payload", "expected_kwargs"),
    (
        (
            {
                "display_name": "  Clockwork Guard  ",
                "turn_value": "17",
                "dexterity_modifier": " +3 ",
                "initiative_priority": "",
                "current_hp": "7",
                "max_hp": 9,
                "temp_hp": None,
                "movement_total": False,
            },
            {
                "display_name": "Clockwork Guard",
                "turn_value": "17",
                "initiative_bonus": None,
                "dexterity_modifier": " +3 ",
                "initiative_priority": "",
                "current_hp": "7",
                "max_hp": 9,
                "temp_hp": None,
                "movement_total": False,
            },
        ),
        (
            {"display_name": "  Defaults  "},
            {
                "display_name": "Defaults",
                "turn_value": None,
                "initiative_bonus": None,
                "dexterity_modifier": None,
                "initiative_priority": None,
                "current_hp": None,
                "max_hp": None,
                "temp_hp": None,
                "movement_total": None,
            },
        ),
    ),
)
def test_custom_npc_create_preserves_exact_raw_and_default_forwarding(
    client,
    app,
    users,
    monkeypatch,
    request_payload,
    expected_kwargs,
):
    service = app.extensions["campaign_combat_service"]
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs.copy()))

    monkeypatch.setattr(service, "add_npc_combatant", capture)
    response = client.post(
        CREATE_PATH,
        headers=api_headers(_dm_token(app, users, label="custom-npc-forwarding")),
        json=request_payload,
    )
    assert response.status_code == 200
    assert calls == [
        (
            ("linden-pass",),
            {**expected_kwargs, "created_by_user_id": users["dm"]["id"]},
        )
    ]


def test_custom_npc_create_preserves_success_payload_actor_revision_and_defaults(
    client,
    app,
    users,
):
    before = _combat_state(app)
    response = client.post(
        f"{CREATE_PATH}?combatant=999999",
        headers=api_headers(_dm_token(app, users, label="custom-npc-success")),
        json={
            "display_name": "  Manual Scout  ",
            "turn_value": "12",
            "dexterity_modifier": "2",
            "initiative_priority": "2",
            "current_hp": "11",
            "max_hp": "14",
            "temp_hp": "3",
            "movement_total": "35",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["changed"] is True
    assert payload["live_revision"] == before["tracker"].revision + 1
    assert isinstance(payload["live_view_token"], str) and payload["live_view_token"]
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_dm_status_url"] == (
        "/campaigns/linden-pass/combat/dm"
    )

    created = next(
        combatant
        for combatant in payload["tracker"]["combatants"]
        if combatant["name"] == "Manual Scout"
    )
    assert created["type_label"] == "NPC"
    assert created["source_kind"] == "manual_npc"
    assert created["source_ref"] == ""
    assert created["turn_value"] == 12
    assert created["initiative_bonus_label"] == "0"
    assert created["dexterity_modifier"] == 2
    assert created["initiative_priority"] == 2
    assert created["current_hp"] == 11
    assert created["max_hp"] == 14
    assert created["temp_hp"] == 3
    assert created["movement_total"] == 35
    assert created["movement_remaining"] == 35
    assert created["npc_resource_counters"] == []
    assert created["npc_resource_notes"] == []

    after = _combat_state(app)
    stored = next(row for row in after["combatants"] if row.display_name == "Manual Scout")
    assert stored.created_by_user_id == users["dm"]["id"]
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id == users["dm"]["id"]


@pytest.mark.parametrize(
    ("fault", "message"),
    (
        (CampaignCombatValidationError("characterized NPC validation fault"), "characterized NPC validation fault"),
        (ValueError("characterized NPC value fault"), "characterized NPC value fault"),
    ),
)
def test_custom_npc_create_maps_expected_faults_without_payload(
    client,
    app,
    users,
    monkeypatch,
    fault,
    message,
):
    service = app.extensions["campaign_combat_service"]

    def expected_fault(*_args, **_kwargs):
        raise fault

    def payload_fault(*_args, **_kwargs):
        raise AssertionError("validation response must not build the combat payload")

    monkeypatch.setattr(service, "add_npc_combatant", expected_fault)
    monkeypatch.setattr(service, "get_tracker", payload_fault)
    response = client.post(
        CREATE_PATH,
        headers=api_headers(_dm_token(app, users, label=f"custom-npc-{type(fault).__name__}")),
        json={"display_name": "Fault"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": message,
    }


def test_custom_npc_create_transaction_fault_rolls_back_everything(
    client,
    app,
    users,
    monkeypatch,
):
    service = app.extensions["campaign_combat_service"]
    before = _combat_state(app)

    def transaction_fault(*_args, **_kwargs):
        raise RuntimeError("characterized tracker bump fault")

    monkeypatch.setattr(service.store, "bump_tracker_revision", transaction_fault)
    with pytest.raises(RuntimeError, match="characterized tracker bump fault"):
        client.post(
            CREATE_PATH,
            headers=api_headers(_dm_token(app, users, label="custom-npc-rollback")),
            json={
                "display_name": "Rolled Back",
                "current_hp": 4,
                "max_hp": 4,
            },
        )
    assert _combat_state(app) == before


def test_custom_npc_create_unexpected_service_fault_propagates_without_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    service = app.extensions["campaign_combat_service"]
    before = _combat_state(app)

    def service_fault(*_args, **_kwargs):
        raise RuntimeError("characterized custom NPC service fault")

    monkeypatch.setattr(service, "add_npc_combatant", service_fault)
    with pytest.raises(RuntimeError, match="characterized custom NPC service fault"):
        client.post(
            CREATE_PATH,
            headers=api_headers(_dm_token(app, users, label="custom-npc-service-fault")),
            json={"display_name": "Never Created"},
        )
    assert _combat_state(app) == before


def test_custom_npc_create_payload_fault_propagates_after_committed_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    service = app.extensions["campaign_combat_service"]
    before = _combat_state(app)
    original_get_tracker = service.get_tracker
    calls = 0

    def payload_fault(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("characterized post-commit payload fault")
        return original_get_tracker(*args, **kwargs)

    monkeypatch.setattr(service, "get_tracker", payload_fault)
    with pytest.raises(RuntimeError, match="characterized post-commit payload fault"):
        client.post(
            CREATE_PATH,
            headers=api_headers(_dm_token(app, users, label="custom-npc-payload-fault")),
            json={
                "display_name": "Committed Before Payload",
                "current_hp": 6,
                "max_hp": 6,
            },
        )
    after = _combat_state(app)
    assert len(after["combatants"]) == len(before["combatants"]) + 1
    assert any(
        row.display_name == "Committed Before Payload" for row in after["combatants"]
    )
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id == users["dm"]["id"]
