from __future__ import annotations

from types import SimpleNamespace

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


PATH = "/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/npc-resources"


def _dm_token(app, users, *, label: str) -> str:
    return issue_api_token(app, users["dm"]["email"], label=label)


def _seed_npc(app, users, *, name: str = "Resource Probe", with_counters: bool = True):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return service.add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=10,
            current_hp=12,
            max_hp=12,
            source_kind="systems_monster",
            source_ref=f"npc-resources-{name.lower().replace(' ', '-')}",
            resource_counter_seeds=(
                [
                    SimpleNamespace(
                        resource_key="arcane-charge",
                        label="Arcane Charge",
                        current_value=3,
                        max_value=3,
                        reset_label="Long rest",
                        source_label="Transport probe",
                    ),
                    SimpleNamespace(
                        resource_key="recharge-breath",
                        label="Recharge Breath",
                        current_value=1,
                        max_value=1,
                        reset_label="Recharge 5-6",
                        source_label="Transport probe",
                    ),
                ]
                if with_counters
                else []
            ),
            created_by_user_id=users["dm"]["id"],
        )


def _state(app, combatant_id: int):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return {
            "tracker": service.get_tracker("linden-pass"),
            "combatant": service.get_combatant("linden-pass", combatant_id),
            "counters": service.store.list_resource_counters(
                "linden-pass", combatant_ids=[combatant_id]
            ),
        }


def test_npc_resources_preserves_scope_login_manager_and_no_eager_work(client, app, users, monkeypatch):
    target = _seed_npc(app, users)
    path = PATH.format(combatant_id=target.id)
    assert client.patch(path.replace("linden-pass", "missing-campaign")).status_code == 404
    anonymous = client.patch(path)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    service = app.extensions["campaign_combat_service"]
    def eager(*_args, **_kwargs):
        raise AssertionError("manager denial must precede user, lookup, JSON, system, and payload work")
    monkeypatch.setattr(service, "get_combatant", eager)
    monkeypatch.setattr(service, "get_tracker", eager)
    _configure_xianxia_campaign(app)
    for user_key in ("owner", "party", "outsider"):
        token = issue_api_token(app, users[user_key]["email"], label=f"npc-resources-denied-{user_key}")
        denied = client.patch(
            path,
            headers={**api_headers(token), "Content-Type": "application/json"},
            data="{",
        )
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"


def test_npc_resources_preserves_handler_user_fallback(client, app, users, monkeypatch):
    target = _seed_npc(app, users)
    with app.app_context():
        dm = app.extensions["auth_store"].get_user_by_id(users["dm"]["id"])
    calls = iter((dm, None))
    monkeypatch.setattr(api_module, "get_current_user", lambda: next(calls))
    response = client.patch(
        PATH.format(combatant_id=target.id),
        headers=api_headers(_dm_token(app, users, label="npc-resources-user-fallback")),
        json={"counters": []},
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == {"code": "auth_required", "message": "Authentication required."}


def test_npc_resources_preserves_view_as_csrf_and_bearer_behavior(client, app, users, sign_in, monkeypatch):
    target = _seed_npc(app, users)
    path = PATH.format(combatant_id=target.id)
    service = app.extensions["campaign_combat_service"]
    original = service.update_npc_resource_counters
    monkeypatch.setattr(service, "update_npc_resource_counters", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("guard first")))
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    assert client.patch(path, json={"counters": []}).get_json()["error"]["code"] == "view_as_read_only"
    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    assert client.patch(path, json={"counters": []}).get_json()["error"]["code"] == "csrf_failed"
    monkeypatch.setattr(service, "update_npc_resource_counters", original)
    bearer = app.test_client().patch(
        path,
        headers=api_headers(_dm_token(app, users, label="npc-resources-bearer")),
        json={"counters": [{"resource_key": "arcane-charge", "current_value": 2}]},
    )
    assert bearer.status_code == 200


def test_npc_resources_preserves_missing_combatant_before_json_and_system(client, app, users):
    _configure_xianxia_campaign(app)
    response = client.patch(
        PATH.format(combatant_id=999999),
        headers={**api_headers(_dm_token(app, users, label="npc-resources-missing")), "Content-Type": "application/json"},
        data="{",
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "message"),
    (("{", "Request body must be a JSON object."), ('["row"]', "Request body must be a JSON object."), ("", "NPC resource counters must be sent as a list.")),
)
def test_npc_resources_preserves_json_and_list_validation(client, app, users, body, message):
    target = _seed_npc(app, users)
    response = client.patch(
        PATH.format(combatant_id=target.id),
        headers={**api_headers(_dm_token(app, users, label=f"npc-resources-json-{len(body)}")), "Content-Type": "application/json"},
        data=body,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {"code": "validation_error", "message": message}


def test_npc_resources_preserves_json_before_supported_system(client, app, users):
    target = _seed_npc(app, users)
    _configure_xianxia_campaign(app)
    path = PATH.format(combatant_id=target.id)
    token = _dm_token(app, users, label="npc-resources-system-order")
    malformed = client.patch(path, headers={**api_headers(token), "Content-Type": "application/json"}, data="{")
    assert malformed.get_json()["error"]["message"] == "Request body must be a JSON object."
    unsupported = client.patch(path, headers=api_headers(token), json={"counters": []})
    assert unsupported.get_json()["error"]["message"] == "Combat tracker support for Xianxia is not available yet."


@pytest.mark.parametrize(
    ("counters", "message"),
    (
        ([], "Choose at least one NPC resource counter to update."),
        (["bad"], "NPC resource row 1 must be an object."),
        ([{}], "Choose a valid NPC resource counter."),
        ([{"resource_key": "missing"}], "Choose a valid NPC resource counter."),
        ([{"resource_key": "arcane-charge", "current_value": -1}], "Arcane Charge current value cannot be less than 0."),
        ([{"resource_key": "arcane-charge", "current_value": 4}], "Arcane Charge cannot exceed 3."),
    ),
)
def test_npc_resources_preserves_counter_row_validation(client, app, users, counters, message):
    target = _seed_npc(app, users)
    response = client.patch(
        PATH.format(combatant_id=target.id),
        headers=api_headers(_dm_token(app, users, label="npc-resources-row-validation")),
        json={"counters": counters},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {"code": "validation_error", "message": message}


def test_npc_resources_preserves_pc_and_no_counter_rejections(client, app, users):
    token = _dm_token(app, users, label="npc-resources-target-kinds")
    add_pc = client.post(
        "/api/v1/campaigns/linden-pass/combat/player-combatants",
        headers=api_headers(token),
        json={"character_slug": "arden-march"},
    )
    assert add_pc.status_code == 200
    pc_id = next(
        row["id"]
        for row in add_pc.get_json()["tracker"]["combatants"]
        if row.get("character_slug") == "arden-march"
    )
    no_counters = _seed_npc(app, users, name="No Counters", with_counters=False)
    pc_response = client.patch(PATH.format(combatant_id=pc_id), headers=api_headers(token), json={"counters": [{}]})
    assert pc_response.get_json()["error"]["message"] == "Only NPC source resources can be edited here."
    none_response = client.patch(PATH.format(combatant_id=no_counters.id), headers=api_headers(token), json={"counters": [{}]})
    assert none_response.get_json()["error"]["message"] == "This NPC has no supported source-backed resource counters."


@pytest.mark.parametrize(("revision", "expected"), ((None, None), ("", None), ("  ", None), ("7", 7)))
def test_npc_resources_preserves_exact_forwarding_actor_defaults_and_duplicates(client, app, users, monkeypatch, revision, expected):
    target = _seed_npc(app, users)
    service = app.extensions["campaign_combat_service"]
    calls = []
    monkeypatch.setattr(service, "update_npc_resource_counters", lambda *args, **kwargs: calls.append((args, kwargs.copy())))
    counters = [
        {"resource_key": " arcane-charge ", "current_value": "2", "extra": False},
        {"resource_key": "arcane-charge", "current_value": 1},
    ]
    payload = {"counters": counters}
    if revision is not None:
        payload["expected_combatant_revision"] = revision
    response = client.patch(
        f"{PATH.format(combatant_id=target.id)}?combatant={target.id}",
        headers=api_headers(_dm_token(app, users, label="npc-resources-forwarding")),
        json=payload,
    )
    assert response.status_code == 200
    assert calls == [(('linden-pass', target.id), {"expected_revision": expected, "counter_values": counters, "updated_by_user_id": users["dm"]["id"]})]
    assert response.get_json()["selected_combatant"]["id"] == target.id


def test_npc_resources_preserves_success_payload_focus_actor_and_revisions(client, app, users):
    target = _seed_npc(app, users)
    before = _state(app, target.id)
    response = client.patch(
        f"{PATH.format(combatant_id=target.id)}?combatant={target.id}",
        headers=api_headers(_dm_token(app, users, label="npc-resources-success")),
        json={"expected_combatant_revision": target.revision, "counters": [{"resource_key": "arcane-charge", "current_value": 1}]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True and payload["changed"] is True
    assert payload["selected_combatant"]["id"] == target.id
    assert next(row for row in payload["selected_combatant"]["npc_resource_counters"] if row["resource_key"] == "arcane-charge")["current_value"] == 1
    after = _state(app, target.id)
    assert after["combatant"].revision == before["combatant"].revision + 1
    assert after["combatant"].updated_by_user_id == users["dm"]["id"]
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id == users["dm"]["id"]


@pytest.mark.parametrize(
    ("fault", "status", "code"),
    ((CampaignCombatRevisionConflictError("stale"), 409, "state_conflict"), (CampaignCombatValidationError("mapped validation"), 400, "validation_error"), (ValueError("mapped value"), 400, "validation_error")),
)
def test_npc_resources_preserves_mapped_faults_without_payload(client, app, users, monkeypatch, fault, status, code):
    target = _seed_npc(app, users)
    service = app.extensions["campaign_combat_service"]
    monkeypatch.setattr(service, "update_npc_resource_counters", lambda *_a, **_k: (_ for _ in ()).throw(fault))
    monkeypatch.setattr(service, "get_tracker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("mapped fault must skip payload")))
    response = client.patch(PATH.format(combatant_id=target.id), headers=api_headers(_dm_token(app, users, label=f"npc-resources-{code}")), json={"counters": [{}]})
    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code


def test_npc_resources_preserves_malformed_revision_mapping(client, app, users):
    target = _seed_npc(app, users)
    response = client.patch(PATH.format(combatant_id=target.id), headers=api_headers(_dm_token(app, users, label="npc-resources-revision")), json={"expected_combatant_revision": "bad", "counters": []})
    assert response.status_code == 400
    assert response.get_json()["error"] == {"code": "validation_error", "message": "invalid literal for int() with base 10: 'bad'"}


def test_npc_resources_transaction_fault_rolls_back_counter_combatant_and_tracker(client, app, users, monkeypatch):
    target = _seed_npc(app, users)
    service = app.extensions["campaign_combat_service"]
    before = _state(app, target.id)
    monkeypatch.setattr(service.store, "bump_tracker_revision", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("tracker bump fault")))
    with pytest.raises(RuntimeError, match="tracker bump fault"):
        client.patch(PATH.format(combatant_id=target.id), headers=api_headers(_dm_token(app, users, label="npc-resources-rollback")), json={"counters": [{"resource_key": "arcane-charge", "current_value": 0}]})
    assert _state(app, target.id) == before


def test_npc_resources_unexpected_and_postcommit_payload_faults(client, app, users, monkeypatch):
    target = _seed_npc(app, users)
    service = app.extensions["campaign_combat_service"]
    before = _state(app, target.id)
    original_update = service.update_npc_resource_counters
    monkeypatch.setattr(service, "update_npc_resource_counters", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("service fault")))
    with pytest.raises(RuntimeError, match="service fault"):
        client.patch(PATH.format(combatant_id=target.id), headers=api_headers(_dm_token(app, users, label="npc-resources-service-fault")), json={"counters": [{}]})
    assert _state(app, target.id) == before

    monkeypatch.setattr(service, "update_npc_resource_counters", original_update)
    original_get_tracker = service.get_tracker
    calls = 0
    def payload_fault(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("postcommit payload fault")
        return original_get_tracker(*args, **kwargs)
    monkeypatch.setattr(service, "get_tracker", payload_fault)
    with pytest.raises(RuntimeError, match="postcommit payload fault"):
        client.patch(PATH.format(combatant_id=target.id), headers=api_headers(_dm_token(app, users, label="npc-resources-payload-fault")), json={"counters": [{"resource_key": "arcane-charge", "current_value": 0}]})
    after = _state(app, target.id)
    assert next(row for row in after["counters"] if row.resource_key == "arcane-charge").current_value == 0
    assert after["combatant"].revision == before["combatant"].revision + 1
    assert after["tracker"].revision == before["tracker"].revision + 1
