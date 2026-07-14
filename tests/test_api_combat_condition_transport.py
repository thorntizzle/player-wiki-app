from __future__ import annotations

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_combat_service import CampaignCombatValidationError
from tests.helpers.api_test_helpers import (
    _configure_xianxia_campaign,
    api_headers,
    issue_api_token,
)


CREATE_PATH = "/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/conditions"
DELETE_PATH = "/api/v1/campaigns/linden-pass/combat/conditions/{condition_id}"


def _seed_npc(app, *, name: str = "Condition Target"):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return service.add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=10,
            current_hp=12,
            max_hp=12,
            movement_total=30,
        )


def _condition_state(app, *, combatant_id: int):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return (
            service.get_tracker("linden-pass"),
            service.get_combatant("linden-pass", combatant_id),
            service.store.list_conditions(
                "linden-pass",
                combatant_ids=[combatant_id],
            ),
        )


def _dm_token(app, users, *, label: str):
    return issue_api_token(app, users["dm"]["email"], label=label)


@pytest.mark.parametrize("method", ("post", "delete"))
def test_combat_condition_mutations_preserve_scope_login_and_manager_order(
    client,
    app,
    users,
    monkeypatch,
    method,
):
    combatant = _seed_npc(app)
    if method == "delete":
        with app.app_context():
            condition = app.extensions["campaign_combat_service"].add_condition(
                "linden-pass",
                combatant.id,
                name="Marked",
            )
        path = DELETE_PATH.format(condition_id=condition.id)
    else:
        path = CREATE_PATH.format(combatant_id=combatant.id)

    missing = getattr(client, method)(path.replace("linden-pass", "missing-campaign"))
    assert missing.status_code == 404

    anonymous = getattr(client, method)(path)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    party_token = issue_api_token(
        app,
        users["party"]["email"],
        label=f"condition-{method}-party",
    )
    service = app.extensions["campaign_combat_service"]
    controller_name = "add_condition" if method == "post" else "delete_condition"

    def fail_controller(*_args, **_kwargs):
        raise AssertionError("management denial must precede the controller")

    monkeypatch.setattr(service, controller_name, fail_controller)
    denied_kwargs = {
        "headers": api_headers(party_token),
        "content_type": "application/json",
        "data": "{",
    }
    denied = getattr(client, method)(path, **denied_kwargs)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method", ("post", "delete"))
def test_combat_condition_mutations_preserve_view_as_and_csrf_before_controller(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
    method,
):
    combatant = _seed_npc(app)
    if method == "delete":
        with app.app_context():
            condition = app.extensions["campaign_combat_service"].add_condition(
                "linden-pass",
                combatant.id,
                name="Marked",
            )
        path = DELETE_PATH.format(condition_id=condition.id)
    else:
        path = CREATE_PATH.format(combatant_id=combatant.id)

    service = app.extensions["campaign_combat_service"]
    controller_name = "add_condition" if method == "post" else "delete_condition"
    original_controller = getattr(service, controller_name)

    def fail_controller(*_args, **_kwargs):
        raise AssertionError("request guard must precede the controller")

    monkeypatch.setattr(service, controller_name, fail_controller)

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    view_as_denied = getattr(client, method)(path, json={})
    assert view_as_denied.status_code == 403
    assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    csrf_denied = getattr(client, method)(path, json={})
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    monkeypatch.setattr(service, controller_name, original_controller)
    token = _dm_token(app, users, label=f"condition-{method}-csrf-bearer")
    bearer_kwargs = {"json": {"name": "Marked"}} if method == "post" else {}
    bearer_allowed = getattr(app.test_client(), method)(
        path,
        headers=api_headers(token),
        **bearer_kwargs,
    )
    assert bearer_allowed.status_code == 200


def test_combat_condition_create_preserves_json_and_supported_system_order(
    client,
    app,
    users,
):
    combatant = _seed_npc(app)
    path = CREATE_PATH.format(combatant_id=combatant.id)
    token = _dm_token(app, users, label="condition-create-order")
    headers = api_headers(token)

    for response in (
        client.post(path, headers=headers, json=[]),
        client.post(
            path,
            headers={**headers, "Content-Type": "application/json"},
            data="{",
        ),
    ):
        assert response.status_code == 400
        assert response.get_json()["error"] == {
            "code": "validation_error",
            "message": "Request body must be a JSON object.",
        }

    _configure_xianxia_campaign(app)
    malformed = client.post(
        path,
        headers={**headers, "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["message"] == "Request body must be a JSON object."

    unsupported = client.post(path, headers=headers, json={"name": "Marked"})
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"]["message"] == (
        "Combat tracker support for Xianxia is not available yet."
    )


def test_combat_condition_create_preserves_trim_actor_transaction_and_payload_focus(
    client,
    app,
    users,
    monkeypatch,
):
    target = _seed_npc(app, name="Target")
    focused = _seed_npc(app, name="Focused")
    service = app.extensions["campaign_combat_service"]
    original = service.add_condition
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "add_condition", capture)
    tracker_before, combatant_before, _ = _condition_state(
        app,
        combatant_id=target.id,
    )
    token = _dm_token(app, users, label="condition-create-success")
    response = client.post(
        f"{CREATE_PATH.format(combatant_id=target.id)}?combatant={focused.id}",
        headers=api_headers(token),
        json={"name": "  Restrained  ", "duration_text": "  Two rounds  "},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == focused.id
    assert payload["selected_combatant"]["name"] == "Focused"
    assert "tracker" in payload and "live_revision" in payload
    assert calls == [
        (
            ("linden-pass", target.id),
            {
                "name": "Restrained",
                "duration_text": "Two rounds",
                "created_by_user_id": users["dm"]["id"],
            },
        )
    ]

    tracker_after, combatant_after, conditions = _condition_state(
        app,
        combatant_id=target.id,
    )
    assert tracker_after.revision == tracker_before.revision + 1
    assert tracker_after.updated_by_user_id == users["dm"]["id"]
    assert combatant_after.revision == combatant_before.revision
    assert [(row.name, row.duration_text, row.created_by_user_id) for row in conditions] == [
        ("Restrained", "Two rounds", users["dm"]["id"]),
    ]


@pytest.mark.parametrize(
    ("combatant_id", "payload", "message"),
    (
        (999999, {"name": "Marked"}, "That combatant could not be found."),
        (None, {}, "Condition name is required."),
        (None, {"name": "x" * 81}, "Condition names must stay under 80 characters."),
        (
            None,
            {"name": "Marked", "duration_text": "x" * 121},
            "Condition duration text must stay under 120 characters.",
        ),
    ),
)
def test_combat_condition_create_preserves_validation_errors(
    client,
    app,
    users,
    combatant_id,
    payload,
    message,
):
    combatant = _seed_npc(app)
    token = _dm_token(app, users, label="condition-create-validation")
    response = client.post(
        CREATE_PATH.format(combatant_id=combatant_id or combatant.id),
        headers=api_headers(token),
        json=payload,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": message,
    }


def test_combat_condition_delete_ignores_body_and_preserves_null_actor_transaction(
    client,
    app,
    users,
):
    target = _seed_npc(app, name="Delete Target")
    focused = _seed_npc(app, name="Delete Focus")
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        condition = service.add_condition(
            "linden-pass",
            target.id,
            name="Marked",
            created_by_user_id=users["dm"]["id"],
        )
    tracker_before, combatant_before, _ = _condition_state(
        app,
        combatant_id=target.id,
    )
    token = _dm_token(app, users, label="condition-delete-success")
    response = client.delete(
        f"{DELETE_PATH.format(condition_id=condition.id)}?combatant={focused.id}",
        headers={**api_headers(token), "Content-Type": "application/json"},
        data="{",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == focused.id
    assert payload["selected_combatant"]["name"] == "Delete Focus"
    assert "tracker" in payload and "live_revision" in payload

    tracker_after, combatant_after, conditions = _condition_state(
        app,
        combatant_id=target.id,
    )
    assert conditions == []
    assert tracker_after.revision == tracker_before.revision + 1
    assert tracker_after.updated_by_user_id is None
    assert combatant_after.revision == combatant_before.revision


def test_combat_condition_delete_preserves_missing_condition_validation(
    client,
    app,
    users,
):
    token = _dm_token(app, users, label="condition-delete-missing")
    response = client.delete(
        DELETE_PATH.format(condition_id=999999),
        headers=api_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That condition could not be found.",
    }


@pytest.mark.parametrize("operation", ("create", "delete"))
def test_combat_condition_validation_fault_skips_payload_build(
    client,
    app,
    users,
    monkeypatch,
    operation,
):
    target = _seed_npc(app)
    service = app.extensions["campaign_combat_service"]
    if operation == "delete":
        with app.app_context():
            condition = service.add_condition("linden-pass", target.id, name="Marked")
        method = client.delete
        path = DELETE_PATH.format(condition_id=condition.id)
        controller = "delete_condition"
        request_kwargs = {}
    else:
        method = client.post
        path = CREATE_PATH.format(combatant_id=target.id)
        controller = "add_condition"
        request_kwargs = {"json": {"name": "Marked"}}

    def validation_fault(*_args, **_kwargs):
        raise CampaignCombatValidationError("characterized condition validation fault")

    def payload_fault(*_args, **_kwargs):
        raise AssertionError("validation response must not build the combat payload")

    monkeypatch.setattr(service, controller, validation_fault)
    monkeypatch.setattr(service, "get_tracker", payload_fault)
    token = _dm_token(app, users, label=f"condition-{operation}-validation-fault")
    response = method(path, headers=api_headers(token), **request_kwargs)
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "characterized condition validation fault",
    }


@pytest.mark.parametrize("operation", ("create", "delete"))
def test_combat_condition_unexpected_service_fault_propagates_without_mutation(
    client,
    app,
    users,
    monkeypatch,
    operation,
):
    target = _seed_npc(app)
    service = app.extensions["campaign_combat_service"]
    if operation == "delete":
        with app.app_context():
            condition = service.add_condition("linden-pass", target.id, name="Marked")
        method = client.delete
        path = DELETE_PATH.format(condition_id=condition.id)
        controller = "delete_condition"
        request_kwargs = {}
    else:
        method = client.post
        path = CREATE_PATH.format(combatant_id=target.id)
        controller = "add_condition"
        request_kwargs = {"json": {"name": "Marked"}}
    tracker_before, _, conditions_before = _condition_state(app, combatant_id=target.id)

    def service_fault(*_args, **_kwargs):
        raise RuntimeError("characterized condition service fault")

    monkeypatch.setattr(service, controller, service_fault)
    token = _dm_token(app, users, label=f"condition-{operation}-service-fault")
    with pytest.raises(RuntimeError, match="characterized condition service fault"):
        method(path, headers=api_headers(token), **request_kwargs)

    tracker_after, _, conditions_after = _condition_state(app, combatant_id=target.id)
    assert tracker_after.revision == tracker_before.revision
    assert conditions_after == conditions_before


@pytest.mark.parametrize("operation", ("create", "delete"))
def test_combat_condition_payload_fault_propagates_after_committed_mutation(
    client,
    app,
    users,
    monkeypatch,
    operation,
):
    target = _seed_npc(app)
    service = app.extensions["campaign_combat_service"]
    if operation == "delete":
        with app.app_context():
            condition = service.add_condition("linden-pass", target.id, name="Marked")
        method = client.delete
        path = DELETE_PATH.format(condition_id=condition.id)
        request_kwargs = {}
    else:
        method = client.post
        path = CREATE_PATH.format(combatant_id=target.id)
        request_kwargs = {"json": {"name": "Marked"}}
    tracker_before, combatant_before, conditions_before = _condition_state(
        app,
        combatant_id=target.id,
    )

    def payload_fault(*_args, **_kwargs):
        raise RuntimeError("characterized condition payload fault")

    monkeypatch.setattr(service, "list_combatants", payload_fault)
    token = _dm_token(app, users, label=f"condition-{operation}-payload-fault")
    with pytest.raises(RuntimeError, match="characterized condition payload fault"):
        method(path, headers=api_headers(token), **request_kwargs)

    tracker_after, combatant_after, conditions_after = _condition_state(
        app,
        combatant_id=target.id,
    )
    assert tracker_after.revision == tracker_before.revision + 1
    assert combatant_after.revision == combatant_before.revision
    if operation == "create":
        assert len(conditions_after) == len(conditions_before) + 1
        assert conditions_after[-1].created_by_user_id == users["dm"]["id"]
        assert tracker_after.updated_by_user_id == users["dm"]["id"]
    else:
        assert conditions_after == []
        assert tracker_after.updated_by_user_id is None
