from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path

import pytest

import player_wiki.app as app_module
import player_wiki.character_controls_routes as controls_routes
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.character_repository import CharacterRepository
from tests.helpers.api_test_helpers import api_headers, issue_api_token


ASSIGN_PATH = "/campaigns/linden-pass/characters/arden-march/controls/assignment"
REMOVE_PATH = f"{ASSIGN_PATH}/remove"


def _flash(client) -> tuple[str, str]:
    with client.session_transaction() as browser_session:
        return browser_session["_flashes"][-1]


def _handler_module(app, endpoint: str):
    handler = inspect.unwrap(app.view_functions[endpoint])
    return importlib.import_module(handler.__module__)


def test_assignment_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(controls_routes.CharacterControlsAssignmentRouteDependencies)
    ] == [
        "load_character_context",
        "campaign_supports_character_controls_routes",
        "get_current_user",
        "get_auth_store",
        "redirect_to_character_controls",
    ]

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_controls_routes.py").read_text(encoding="utf-8")
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    route_handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {"character_controls_assignment", "character_controls_assignment_remove"}
    }
    assert set(route_handlers) == {
        "character_controls_assignment",
        "character_controls_assignment_remove",
    }
    assert all(handler.decorator_list == [] for handler in route_handlers.values())

    registrations = [
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {
            "register_character_read_route",
            "register_character_controls_assignment_routes",
        }
    ]
    by_name = {node.func.id: node for node in registrations}
    delete_handler = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_controls_delete"
    )
    assert (
        by_name["register_character_read_route"].lineno
        < by_name["register_character_controls_assignment_routes"].lineno
        < delete_handler.lineno
    )

    registration = by_name["register_character_controls_assignment_routes"]
    keyword_values = {keyword.arg: keyword.value for keyword in registration.keywords}
    assert isinstance(keyword_values["get_current_user"], ast.Lambda)
    assert isinstance(keyword_values["get_auth_store"], ast.Lambda)
    for name in (
        "load_character_context",
        "campaign_supports_character_controls_routes",
        "redirect_to_character_controls",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name


def test_assignment_transport_keeps_post_registration_auth_store_forwarding(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    original_get_store = app_module.get_auth_store
    calls: list[str] = []

    def get_store():
        calls.append("store")
        return original_get_store()

    monkeypatch.setattr(app_module, "get_auth_store", get_store)
    response = client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]})
    assert response.status_code == 302
    assert calls == ["store"]


def test_assignment_routes_preserve_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    expected = {
        "character_controls_assignment": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment",
            ASSIGN_PATH,
        ),
        "character_controls_assignment_remove": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment/remove",
            REMOVE_PATH,
        ),
    }

    for endpoint, (rule_path, request_path) in expected.items():
        rule = next(rule for rule in rules if rule.endpoint == endpoint)
        assert rule.rule == rule_path
        assert rule.methods == {"POST", "OPTIONS"}
        assert client.options(request_path).status_code == 200
        assert client.get(request_path).status_code == 405
        assert client.put(request_path).status_code == 405

    assert endpoints.index("character_read_view") < endpoints.index(
        "character_controls_assignment"
    )
    assert endpoints.index("character_controls_assignment") < endpoints.index(
        "character_controls_assignment_remove"
    )
    assert endpoints.index("character_controls_assignment_remove") < endpoints.index(
        "character_controls_delete"
    )


@pytest.mark.parametrize("user_key", ("owner", "party", "dm", "observer"))
@pytest.mark.parametrize("path", (ASSIGN_PATH, REMOVE_PATH))
def test_assignment_routes_keep_admin_only_body_after_scope_admission(
    client, sign_in, users, set_campaign_visibility, user_key, path
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users[user_key]["email"], users[user_key]["password"])

    assert client.post(path, data={"user_id": users["party"]["id"]}).status_code == 403


def test_assignment_scope_admission_keeps_anonymous_missing_and_assignment_non_bypass(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.post(f"{ASSIGN_PATH}?mode=session", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/controls/assignment?mode%3Dsession"
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]}).status_code == 404

    sign_in(users["admin"]["email"], users["admin"]["password"])
    assert client.post(
        "/campaigns/missing/characters/arden-march/controls/assignment",
        data={"user_id": users["party"]["id"]},
    ).status_code == 404
    assert client.post(
        "/campaigns/linden-pass/characters/missing/controls/assignment",
        data={"user_id": users["party"]["id"]},
    ).status_code == 404


def test_assignment_validation_preserves_exact_errors_and_redirect_mode(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    cases = (
        ("", "Choose a valid player to assign."),
        ("not-an-id", "Choose a valid player to assign."),
        ("999999", "Choose an active player account to assign."),
        (
            str(users["observer"]["id"]),
            "Character owners must have an active player membership in that campaign.",
        ),
    )
    for user_id, message in cases:
        response = client.post(
            f"{ASSIGN_PATH}?mode=session",
            data={"user_id": user_id, "mode": "session"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith(
            "/campaigns/linden-pass/characters/arden-march?page=controls&mode=session"
        )
        assert _flash(client) == ("error", message)

    with app.app_context():
        AuthStore().disable_user(users["party"]["id"])
    response = client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]})
    assert response.status_code == 302
    assert _flash(client) == ("error", "Choose an active player account to assign.")


def test_assignment_and_remove_preserve_audit_payloads_and_success_redirects(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    assigned = client.post(
        ASSIGN_PATH,
        data={"user_id": users["party"]["id"]},
        follow_redirects=False,
    )
    assert assigned.status_code == 302
    assert assigned.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=controls"
    )
    assert _flash(client) == (
        "success",
        "Assigned arden-march to party@example.com.",
    )

    with app.app_context():
        store = AuthStore()
        assignment = store.get_character_assignment("linden-pass", "arden-march")
        events = store.list_audit_events_for_user(users["party"]["id"], limit=20)
        event = next(event for event in events if event.event_type == "character_assignment_created")
        assert assignment is not None
        assert assignment.user_id == users["party"]["id"]
        assert event.actor_user_id == users["admin"]["id"]
        assert event.target_user_id == users["party"]["id"]
        assert event.metadata == {
            "previous_user_id": users["owner"]["id"],
            "assignment_type": "owner",
            "source": "character_controls",
        }

    removed = client.post(REMOVE_PATH, follow_redirects=False)
    assert removed.status_code == 302
    assert _flash(client) == ("success", "Cleared assignment for arden-march.")
    with app.app_context():
        store = AuthStore()
        assert store.get_character_assignment("linden-pass", "arden-march") is None
        events = store.list_audit_events_for_user(users["party"]["id"], limit=20)
        event = next(event for event in events if event.event_type == "character_assignment_removed")
        assert event.actor_user_id == users["admin"]["id"]
        assert event.target_user_id == users["party"]["id"]
        assert event.metadata == {
            "assignment_type": "owner",
            "source": "character_controls",
        }


def test_assignment_remove_preserves_missing_and_raced_removal_branches(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with app.app_context():
        AuthStore().delete_character_assignment("linden-pass", "arden-march")

    missing = client.post(REMOVE_PATH)
    assert missing.status_code == 302
    assert _flash(client) == (
        "error",
        "That character does not currently have an assigned player.",
    )

    with app.app_context():
        AuthStore().upsert_character_assignment(
            users["owner"]["id"], "linden-pass", "arden-march"
        )
    monkeypatch.setattr(AuthStore, "delete_character_assignment", lambda self, *args: None)
    raced = client.post(REMOVE_PATH)
    assert raced.status_code == 302
    assert _flash(client) == ("error", "That character assignment no longer exists.")


def test_assignment_preserves_view_as_csrf_and_bearer_behavior(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as = client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]})
    assert view_as.status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]})
    assert csrf.status_code == 400
    assert "Refresh the page and try again." in csrf.get_data(as_text=True)

    token = issue_api_token(app, users["admin"]["email"], label="p31-browser-bearer")
    bearer = app.test_client().post(
        ASSIGN_PATH,
        data={"user_id": users["party"]["id"]},
        headers=api_headers(token),
    )
    assert bearer.status_code == 302


def test_assignment_preserves_load_system_actor_order_and_faults(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["party"]["email"], users["party"]["password"])
    calls: list[str] = []

    original_load = CharacterRepository.get_visible_character
    original_supports = app_module.supports_character_controls_routes
    original_actor = app_module.get_current_user

    def load(repository, *args):
        calls.append("load")
        return original_load(repository, *args)

    def supports(system):
        calls.append("supports")
        return original_supports(system)

    def actor():
        calls.append("actor")
        return original_actor()

    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    monkeypatch.setattr(app_module, "supports_character_controls_routes", supports)
    monkeypatch.setattr(app_module, "get_current_user", actor)

    assert client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]}).status_code == 403
    assert calls == ["load", "supports", "actor"]

    monkeypatch.setattr(app_module, "supports_character_controls_routes", lambda system: False)
    calls.clear()
    assert client.post(ASSIGN_PATH, data={"user_id": users["party"]["id"]}).status_code == 404
    assert calls == ["load"]


@pytest.mark.parametrize("path", (ASSIGN_PATH, REMOVE_PATH))
def test_assignment_persistence_remains_committed_when_audit_fails(
    app, client, sign_in, users, monkeypatch, path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    if path == REMOVE_PATH:
        with app.app_context():
            AuthStore().upsert_character_assignment(
                users["party"]["id"], "linden-pass", "arden-march"
            )

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit fault")

    monkeypatch.setattr(AuthStore, "write_audit_event", fail_audit)
    data = {"user_id": users["party"]["id"]} if path == ASSIGN_PATH else {}
    with pytest.raises(RuntimeError, match="audit fault"):
        client.post(path, data=data)

    with app.app_context():
        assignment = AuthStore().get_character_assignment("linden-pass", "arden-march")
        if path == ASSIGN_PATH:
            assert assignment is not None
            assert assignment.user_id == users["party"]["id"]
        else:
            assert assignment is None


@pytest.mark.parametrize("path", (ASSIGN_PATH, REMOVE_PATH))
def test_assignment_persistence_remains_committed_when_success_flash_fails(
    app, client, sign_in, users, monkeypatch, path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    if path == REMOVE_PATH:
        with app.app_context():
            AuthStore().upsert_character_assignment(
                users["party"]["id"], "linden-pass", "arden-march"
            )

    route_module = _handler_module(app, path == ASSIGN_PATH and "character_controls_assignment" or "character_controls_assignment_remove")

    def fail_flash(message, category):
        if category == "success":
            raise RuntimeError("flash fault")

    monkeypatch.setattr(route_module, "flash", fail_flash)
    data = {"user_id": users["party"]["id"]} if path == ASSIGN_PATH else {}
    with pytest.raises(RuntimeError, match="flash fault"):
        client.post(path, data=data)

    with app.app_context():
        assignment = AuthStore().get_character_assignment("linden-pass", "arden-march")
        if path == ASSIGN_PATH:
            assert assignment is not None
            assert assignment.user_id == users["party"]["id"]
        else:
            assert assignment is None


@pytest.mark.parametrize("path", (ASSIGN_PATH, REMOVE_PATH))
def test_assignment_persistence_remains_committed_when_redirect_fails(
    app, client, sign_in, users, path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    if path == REMOVE_PATH:
        with app.app_context():
            AuthStore().upsert_character_assignment(
                users["party"]["id"], "linden-pass", "arden-march"
            )

    dependencies = app.extensions["character_controls_assignment_route_dependencies"]

    def fail_redirect(*args):
        raise RuntimeError("redirect fault")

    app.extensions["character_controls_assignment_route_dependencies"] = replace(
        dependencies,
        redirect_to_character_controls=fail_redirect,
    )
    data = {"user_id": users["party"]["id"]} if path == ASSIGN_PATH else {}
    with pytest.raises(RuntimeError, match="redirect fault"):
        client.post(path, data=data)

    with app.app_context():
        assignment = AuthStore().get_character_assignment("linden-pass", "arden-march")
        if path == ASSIGN_PATH:
            assert assignment is not None
            assert assignment.user_id == users["party"]["id"]
        else:
            assert assignment is None
