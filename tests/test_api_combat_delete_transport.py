from __future__ import annotations

from types import SimpleNamespace

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_combat_service import CampaignCombatValidationError
from player_wiki.db import get_db
from tests.helpers.api_test_helpers import (
    _configure_xianxia_campaign,
    api_headers,
    issue_api_token,
)


DELETE_PATH = "/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}"


def _dm_token(app, users, *, label: str) -> str:
    return issue_api_token(app, users["dm"]["email"], label=label)


def _seed_probe(app, users, *, name: str, turn_value: int = 10):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=turn_value,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            source_kind="systems_monster",
            source_ref=f"delete-{name.lower().replace(' ', '-')}",
            resource_counter_seeds=[
                SimpleNamespace(
                    resource_key="delete-charge",
                    label="Delete Charge",
                    current_value=2,
                    max_value=3,
                    reset_label="Long rest",
                    source_label="Delete transport probe",
                )
            ],
            resource_note_seeds=[
                SimpleNamespace(
                    label="Delete Note",
                    note="Cascade with the combatant.",
                    source_label="Delete transport probe",
                )
            ],
            created_by_user_id=users["dm"]["id"],
        )
        condition = service.add_condition(
            "linden-pass",
            combatant.id,
            name="Grappled",
            duration_text="Until escaped",
            created_by_user_id=users["dm"]["id"],
        )
    return combatant, condition


def _state(app, combatant_ids: list[int]):
    placeholders = ", ".join("?" for _ in combatant_ids)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return {
            "tracker": service.get_tracker("linden-pass"),
            "combatants": service.list_combatants("linden-pass"),
            "dependents": {
                table: int(
                    get_db()
                    .execute(
                        f"SELECT COUNT(*) FROM {table} "
                        f"WHERE combatant_id IN ({placeholders})",
                        tuple(combatant_ids),
                    )
                    .fetchone()[0]
                )
                for table in (
                    "campaign_combat_conditions",
                    "campaign_combatant_resource_counters",
                    "campaign_combatant_resource_notes",
                )
            },
        }


def test_combatant_delete_preserves_scope_then_login_and_manager_order(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Authorization Target")
    path = DELETE_PATH.format(combatant_id=target.id)

    missing = client.delete(path.replace("linden-pass", "missing-campaign"))
    assert missing.status_code == 404

    anonymous = client.delete(path)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    for user_key in ("owner", "party", "outsider"):
        token = issue_api_token(
            app,
            users[user_key]["email"],
            label=f"combatant-delete-{user_key}",
        )
        denied = client.delete(path, headers=api_headers(token))
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"

    _configure_xianxia_campaign(app)
    service = app.extensions["campaign_combat_service"]

    def eager_work(*_args, **_kwargs):
        raise AssertionError("management denial must precede system, service, and payload work")

    monkeypatch.setattr(service, "delete_combatant", eager_work)
    monkeypatch.setattr(service, "get_tracker", eager_work)
    token = issue_api_token(
        app,
        users["party"]["email"],
        label="combatant-delete-denial-order",
    )
    denied = client.delete(
        path,
        headers={**api_headers(token), "Content-Type": "application/json"},
        data="{",
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"


def test_combatant_delete_preserves_scope_guard_fault_propagation(
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
        client.delete(DELETE_PATH.format(combatant_id=1))


def test_combatant_delete_preserves_view_as_and_csrf_before_service(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Request Guard Target")
    path = DELETE_PATH.format(combatant_id=target.id)
    service = app.extensions["campaign_combat_service"]
    original_delete = service.delete_combatant

    def eager_delete(*_args, **_kwargs):
        raise AssertionError("request guard must precede combatant deletion")

    monkeypatch.setattr(service, "delete_combatant", eager_delete)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    view_as_denied = client.delete(path)
    assert view_as_denied.status_code == 403
    assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    csrf_denied = client.delete(path)
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    monkeypatch.setattr(service, "delete_combatant", original_delete)
    token = _dm_token(app, users, label="combatant-delete-csrf-bearer")
    bearer_allowed = app.test_client().delete(path, headers=api_headers(token))
    assert bearer_allowed.status_code == 200


def test_combatant_delete_preserves_supported_campaign_before_service(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Unsupported Target")
    _configure_xianxia_campaign(app)
    service = app.extensions["campaign_combat_service"]

    def eager_delete(*_args, **_kwargs):
        raise AssertionError("unsupported combat must not call delete")

    monkeypatch.setattr(service, "delete_combatant", eager_delete)
    token = _dm_token(app, users, label="combatant-delete-unsupported")
    response = client.delete(
        DELETE_PATH.format(combatant_id=target.id),
        headers=api_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "Combat tracker support for Xianxia is not available yet.",
    }


@pytest.mark.parametrize(
    ("content_type", "body"),
    (
        ("application/json", "{"),
        ("application/json", '["arbitrary", {"expected_revision": 999}]'),
    ),
)
def test_combatant_delete_ignores_request_body_and_user_actor(
    client,
    app,
    users,
    monkeypatch,
    content_type,
    body,
):
    target, _ = _seed_probe(app, users, name="Ignored Body Target")
    survivor, _ = _seed_probe(app, users, name="Ignored Body Survivor", turn_value=5)
    service = app.extensions["campaign_combat_service"]
    original_delete = service.delete_combatant
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(service, "delete_combatant", capture)
    token = _dm_token(app, users, label=f"combatant-delete-body-{len(body)}")
    response = client.delete(
        f"{DELETE_PATH.format(combatant_id=target.id)}?combatant={survivor.id}",
        headers=api_headers(token),
        content_type=content_type,
        data=body,
    )
    assert response.status_code == 200
    assert calls == [(('linden-pass', target.id), {})]


def test_combatant_delete_preserves_payload_fallback_cascade_and_transaction(
    client,
    app,
    users,
):
    target, _ = _seed_probe(app, users, name="Current Delete Target", turn_value=20)
    survivor, _ = _seed_probe(app, users, name="Surviving Target", turn_value=10)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        service.set_current_turn(
            "linden-pass",
            target.id,
            updated_by_user_id=users["dm"]["id"],
        )
    before = _state(app, [target.id, survivor.id])

    token = _dm_token(app, users, label="combatant-delete-success")
    response = client.delete(
        f"{DELETE_PATH.format(combatant_id=target.id)}?combatant={target.id}",
        headers=api_headers(token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["changed"] is True
    assert payload["selected_combatant_id"] == survivor.id
    assert payload["selected_combatant"]["name"] == "Surviving Target"
    assert payload["tracker"]["combatant_count"] == 1
    assert payload["live_revision"] == before["tracker"].revision + 1
    assert isinstance(payload["live_view_token"], str) and payload["live_view_token"]
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_dm_status_url"] == "/campaigns/linden-pass/combat/dm"

    after = _state(app, [target.id, survivor.id])
    assert [row.id for row in after["combatants"]] == [survivor.id]
    assert after["tracker"].current_combatant_id is None
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id is None
    assert before["dependents"] == {
        "campaign_combat_conditions": 2,
        "campaign_combatant_resource_counters": 2,
        "campaign_combatant_resource_notes": 2,
    }
    assert after["dependents"] == {
        "campaign_combat_conditions": 1,
        "campaign_combatant_resource_counters": 1,
        "campaign_combatant_resource_notes": 1,
    }


def test_combatant_delete_preserves_missing_target_validation_without_payload(
    client,
    app,
    users,
    monkeypatch,
):
    service = app.extensions["campaign_combat_service"]

    def payload_fault(*_args, **_kwargs):
        raise AssertionError("validation response must not build the combat payload")

    monkeypatch.setattr(service, "get_tracker", payload_fault)
    token = _dm_token(app, users, label="combatant-delete-missing")
    response = client.delete(
        DELETE_PATH.format(combatant_id=999999),
        headers=api_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That combatant could not be found.",
    }


def test_combatant_delete_validation_fault_skips_payload_build(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Validation Fault Target")
    service = app.extensions["campaign_combat_service"]

    def validation_fault(*_args, **_kwargs):
        raise CampaignCombatValidationError("characterized combatant validation fault")

    def payload_fault(*_args, **_kwargs):
        raise AssertionError("validation response must not build the combat payload")

    monkeypatch.setattr(service, "delete_combatant", validation_fault)
    monkeypatch.setattr(service, "get_tracker", payload_fault)
    token = _dm_token(app, users, label="combatant-delete-validation-fault")
    response = client.delete(
        DELETE_PATH.format(combatant_id=target.id),
        headers=api_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "characterized combatant validation fault",
    }


def test_combatant_delete_transaction_fault_rolls_back_everything(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Rollback Target")
    service = app.extensions["campaign_combat_service"]
    before = _state(app, [target.id])

    def transaction_fault(*_args, **_kwargs):
        raise RuntimeError("characterized tracker bump fault")

    monkeypatch.setattr(service.store, "bump_tracker_revision", transaction_fault)
    token = _dm_token(app, users, label="combatant-delete-rollback")
    with pytest.raises(RuntimeError, match="characterized tracker bump fault"):
        client.delete(
            DELETE_PATH.format(combatant_id=target.id),
            headers=api_headers(token),
        )
    after = _state(app, [target.id])
    assert after == before


def test_combatant_delete_unexpected_service_fault_propagates_without_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Service Fault Target")
    service = app.extensions["campaign_combat_service"]
    before = _state(app, [target.id])

    def service_fault(*_args, **_kwargs):
        raise RuntimeError("characterized combatant delete fault")

    monkeypatch.setattr(service, "delete_combatant", service_fault)
    token = _dm_token(app, users, label="combatant-delete-service-fault")
    with pytest.raises(RuntimeError, match="characterized combatant delete fault"):
        client.delete(
            DELETE_PATH.format(combatant_id=target.id),
            headers=api_headers(token),
        )
    assert _state(app, [target.id]) == before


def test_combatant_delete_payload_fault_propagates_after_committed_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    target, _ = _seed_probe(app, users, name="Payload Fault Target")
    service = app.extensions["campaign_combat_service"]
    before = _state(app, [target.id])
    original_get_tracker = service.get_tracker
    calls = 0

    def payload_fault(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("characterized post-commit payload fault")
        return original_get_tracker(*args, **kwargs)

    monkeypatch.setattr(service, "get_tracker", payload_fault)
    token = _dm_token(app, users, label="combatant-delete-payload-fault")
    with pytest.raises(RuntimeError, match="characterized post-commit payload fault"):
        client.delete(
            DELETE_PATH.format(combatant_id=target.id),
            headers=api_headers(token),
        )
    after = _state(app, [target.id])
    assert after["combatants"] == []
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id is None
    assert after["dependents"] == {
        "campaign_combat_conditions": 0,
        "campaign_combatant_resource_counters": 0,
        "campaign_combatant_resource_notes": 0,
    }
