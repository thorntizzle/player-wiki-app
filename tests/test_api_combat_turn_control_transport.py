from __future__ import annotations

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatValidationError,
)
from tests.helpers.api_test_helpers import (
    _configure_xianxia_campaign,
    api_headers,
    issue_api_token,
)


BASE = "/api/v1/campaigns/linden-pass/combat"


def _token(app, users, key="dm", *, label="turn-control"):
    return issue_api_token(app, users[key]["email"], label=f"{label}-{key}")


def _seed(app, users, name, turn, *, priority=1):
    with app.app_context():
        return app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=turn,
            initiative_priority=priority,
            current_hp=10,
            max_hp=10,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )


def _state(app):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return service.get_tracker("linden-pass"), service.list_combatants("linden-pass")


def _requests(client, combatant_id=1):
    return (
        ("post", f"{BASE}/advance-turn"),
        ("post", f"{BASE}/clear"),
        ("post", f"{BASE}/combatants/{combatant_id}/set-current"),
        ("patch", f"{BASE}/combatants/{combatant_id}/turn"),
    )


def test_turn_control_preserves_scope_login_manager_and_no_eager_denial(client, app, users, monkeypatch):
    service = app.extensions["campaign_combat_service"]
    for method, path in _requests(client):
        assert getattr(client, method)(path.replace("linden-pass", "missing-campaign")).status_code == 404
        anonymous = getattr(client, method)(path)
        assert anonymous.status_code == 401
        assert anonymous.get_json()["error"]["code"] == "auth_required"

    def eager(*_args, **_kwargs):
        raise AssertionError("manager denial must precede user, JSON, system, service, and payload")

    monkeypatch.setattr(service, "advance_turn", eager)
    monkeypatch.setattr(service, "clear_tracker", eager)
    monkeypatch.setattr(service, "set_current_turn", eager)
    monkeypatch.setattr(service, "update_turn_value", eager)
    monkeypatch.setattr(service, "get_tracker", eager)
    _configure_xianxia_campaign(app)
    for user_key in ("owner", "party", "outsider"):
        headers = {**api_headers(_token(app, users, user_key, label="turn-denied")), "Content-Type": "application/json"}
        for method, path in _requests(client):
            denied = getattr(client, method)(path, headers=headers, data="{")
            assert denied.status_code == 403
            assert denied.get_json()["error"]["code"] == "forbidden"


def test_turn_control_preserves_handler_user_fallback(client, app, users, monkeypatch):
    with app.app_context():
        dm = app.extensions["auth_store"].get_user_by_id(users["dm"]["id"])
    for method, path in _requests(client):
        calls = iter((dm, None))
        monkeypatch.setattr(api_module, "get_current_user", lambda: next(calls))
        response = getattr(client, method)(path, headers=api_headers(_token(app, users, label=f"fallback-{method}")))
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "auth_required"


def test_turn_control_preserves_view_as_csrf_and_bearer_guards(client, app, users, sign_in):
    target = _seed(app, users, "Guard", 10)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    for method, path in _requests(client, target.id):
        response = getattr(client, method)(path, json={})
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "view_as_read_only"
    client.get("/auth/logout")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    assert client.post(f"{BASE}/advance-turn").get_json()["error"]["code"] == "csrf_failed"
    bearer = app.test_client().post(
        f"{BASE}/combatants/{target.id}/set-current",
        headers=api_headers(_token(app, users, label="bearer")),
    )
    assert bearer.status_code == 200


def test_turn_control_preserves_options_and_wrong_method_identity(client, app, users):
    target = _seed(app, users, "Methods", 10)
    for method, path in _requests(client, target.id):
        options = client.options(path)
        assert options.status_code == 200
        assert method.upper() in options.headers["Allow"]
        wrong = client.get(path, headers=api_headers(_token(app, users, label=f"wrong-{method}")))
        assert wrong.status_code == 405


def test_first_three_controls_ignore_all_request_bodies(client, app, users):
    target = _seed(app, users, "Ignored Body", 10)
    headers = {**api_headers(_token(app, users, label="ignored-body")), "Content-Type": "application/json"}
    for path in (
        f"{BASE}/combatants/{target.id}/set-current",
        f"{BASE}/advance-turn",
        f"{BASE}/clear",
    ):
        response = client.post(path, headers=headers, data="{")
        assert response.status_code == 200


def test_turn_patch_preserves_json_before_system_and_revision_conversion(client, app, users):
    target = _seed(app, users, "JSON Order", 10)
    path = f"{BASE}/combatants/{target.id}/turn"
    token = _token(app, users, label="json-order")
    _configure_xianxia_campaign(app)
    malformed = client.patch(path, headers={**api_headers(token), "Content-Type": "application/json"}, data="{")
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["message"] == "Request body must be a JSON object."
    unsupported = client.patch(path, headers=api_headers(token), json={"expected_combatant_revision": "bad"})
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"]["message"] == "Combat tracker support for Xianxia is not available yet."


@pytest.mark.parametrize("body", ["[]", '"value"'])
def test_turn_patch_rejects_nonobject_json(client, app, users, body):
    target = _seed(app, users, "JSON Shape", 10)
    response = client.patch(
        f"{BASE}/combatants/{target.id}/turn",
        headers={**api_headers(_token(app, users, label="json-shape")), "Content-Type": "application/json"},
        data=body,
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_turn_patch_preserves_empty_body_as_empty_object_and_field_defaults(client, app, users):
    target = _seed(app, users, "JSON Empty", 10, priority=3)
    response = client.patch(
        f"{BASE}/combatants/{target.id}/turn?combatant={target.id}",
        headers={**api_headers(_token(app, users, label="json-empty")), "Content-Type": "application/json"},
        data="",
    )
    assert response.status_code == 200
    selected = response.get_json()["selected_combatant"]
    assert selected["turn_value"] == 10
    assert selected["initiative_priority"] == 3


@pytest.mark.parametrize(("revision", "expected"), [(None, None), ("", None), ("  ", None), ("7", 7)])
def test_turn_patch_preserves_exact_service_arguments_and_focus(client, app, users, monkeypatch, revision, expected):
    target = _seed(app, users, "Forward", 10)
    service = app.extensions["campaign_combat_service"]
    calls = []
    monkeypatch.setattr(service, "update_turn_value", lambda *args, **kwargs: calls.append((args, kwargs)))
    payload = {"turn_value": " 14 ", "initiative_priority": "0", "extra": "raw"}
    if revision is not None:
        payload["expected_combatant_revision"] = revision
    response = client.patch(
        f"{BASE}/combatants/{target.id}/turn?combatant={target.id}",
        headers=api_headers(_token(app, users, label="forward")),
        json=payload,
    )
    assert response.status_code == 200
    assert calls == [(("linden-pass", target.id), {"expected_revision": expected, "turn_value": " 14 ", "initiative_priority": "0", "updated_by_user_id": users["dm"]["id"]})]
    assert response.get_json()["selected_combatant"]["id"] == target.id


def test_turn_controls_preserve_success_round_focus_resources_actor_and_revisions(client, app, users):
    first = _seed(app, users, "First", 20)
    second = _seed(app, users, "Second", 10)
    token = _token(app, users, label="success")
    initial_tracker, initial_rows = _state(app)
    patch = client.patch(
        f"{BASE}/combatants/{second.id}/turn?combatant={second.id}",
        headers=api_headers(token),
        json={"expected_combatant_revision": second.revision, "turn_value": 15, "initiative_priority": 2},
    )
    assert patch.status_code == 200
    changed = patch.get_json()["selected_combatant"]
    assert changed["turn_value"] == 15 and changed["initiative_priority"] == 2
    assert changed["combatant_revision"] == second.revision + 1

    current = client.post(f"{BASE}/combatants/{second.id}/set-current?combatant={second.id}", headers=api_headers(token))
    assert current.status_code == 200
    assert current.get_json()["selected_combatant"]["is_current_turn"] is True
    assert current.get_json()["tracker"]["round_number"] == 1
    assert current.get_json()["selected_combatant"]["movement_remaining"] == 30

    next_turn = client.post(f"{BASE}/advance-turn", headers=api_headers(token))
    assert next(row for row in next_turn.get_json()["tracker"]["combatants"] if row["id"] == first.id)["is_current_turn"] is True
    assert next_turn.get_json()["tracker"]["round_number"] == 2
    after_tracker, after_rows = _state(app)
    assert after_tracker.updated_by_user_id == users["dm"]["id"]
    assert after_tracker.revision > initial_tracker.revision
    assert all(row.updated_by_user_id == users["dm"]["id"] for row in after_rows)

    cleared = client.post(f"{BASE}/clear", headers=api_headers(token))
    assert cleared.status_code == 200
    assert cleared.get_json()["tracker"]["combatant_count"] == 0
    tracker, rows = _state(app)
    assert rows == [] and tracker.current_combatant_id is None and tracker.round_number == 1


def test_turn_controls_preserve_empty_and_missing_target_validation(client, app, users):
    token = _token(app, users, label="missing")
    empty = client.post(f"{BASE}/advance-turn", headers=api_headers(token))
    assert empty.status_code == 400
    assert empty.get_json()["error"]["message"] == "Add combatants before advancing turn order."
    for method, path in (("post", f"{BASE}/combatants/99999/set-current"), ("patch", f"{BASE}/combatants/99999/turn")):
        response = getattr(client, method)(path, headers=api_headers(token), json={})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("service_name", "method", "path", "fault", "status", "code"),
    [
        ("advance_turn", "post", f"{BASE}/advance-turn", CampaignCombatValidationError("advance"), 400, "validation_error"),
        ("clear_tracker", "post", f"{BASE}/clear", CampaignCombatValidationError("clear"), 400, "validation_error"),
        ("set_current_turn", "post", f"{BASE}/combatants/1/set-current", CampaignCombatValidationError("current"), 400, "validation_error"),
        ("update_turn_value", "patch", f"{BASE}/combatants/1/turn", CampaignCombatRevisionConflictError("stale"), 409, "state_conflict"),
        ("update_turn_value", "patch", f"{BASE}/combatants/1/turn", ValueError("bad"), 400, "validation_error"),
    ],
)
def test_turn_controls_preserve_mapped_faults_and_skip_payload(client, app, users, monkeypatch, service_name, method, path, fault, status, code):
    service = app.extensions["campaign_combat_service"]
    monkeypatch.setattr(service, service_name, lambda *_a, **_k: (_ for _ in ()).throw(fault))
    monkeypatch.setattr(service, "get_tracker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("mapped fault must skip payload")))
    response = getattr(client, method)(path, headers=api_headers(_token(app, users, label=f"mapped-{service_name}")), json={})
    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code


def test_turn_controls_preserve_unexpected_and_postcommit_payload_faults(client, app, users, monkeypatch):
    target = _seed(app, users, "Fault", 10)
    service = app.extensions["campaign_combat_service"]
    before = _state(app)
    original = service.update_turn_value
    monkeypatch.setattr(service, "update_turn_value", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("service fault")))
    with pytest.raises(RuntimeError, match="service fault"):
        client.patch(f"{BASE}/combatants/{target.id}/turn", headers=api_headers(_token(app, users, label="unexpected")), json={"turn_value": 11})
    assert _state(app) == before

    monkeypatch.setattr(service, "update_turn_value", original)
    original_get = service.get_tracker
    calls = 0
    def payload_fault(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("postcommit payload fault")
        return original_get(*args, **kwargs)
    monkeypatch.setattr(service, "get_tracker", payload_fault)
    with pytest.raises(RuntimeError, match="postcommit payload fault"):
        client.patch(f"{BASE}/combatants/{target.id}/turn", headers=api_headers(_token(app, users, label="postcommit")), json={"turn_value": 12})
    with app.app_context():
        assert service.get_combatant("linden-pass", target.id).turn_value == 12


def test_turn_update_transaction_fault_rolls_back_combatant_and_tracker(client, app, users, monkeypatch):
    target = _seed(app, users, "Rollback", 10)
    service = app.extensions["campaign_combat_service"]
    before = _state(app)
    monkeypatch.setattr(service.store, "bump_tracker_revision", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("tracker bump fault")))
    with pytest.raises(RuntimeError, match="tracker bump fault"):
        client.patch(
            f"{BASE}/combatants/{target.id}/turn",
            headers=api_headers(_token(app, users, label="rollback")),
            json={"expected_combatant_revision": target.revision, "turn_value": 99},
        )
    assert _state(app) == before
