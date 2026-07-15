from __future__ import annotations

import ast
from dataclasses import fields
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
import player_wiki.character_controls_delete_routes as delete_routes
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_repository import CharacterRepository
from tests.helpers.api_test_helpers import api_headers, issue_api_token


ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/controls/delete"
ENDPOINT = "character_controls_delete"


def test_delete_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(delete_routes.CharacterControlsDeleteRouteDependencies)
    ] == [
        "load_character_context",
        "campaign_supports_character_controls_routes",
        "can_manage_campaign_content",
        "get_auth_store",
        "get_current_user",
        "delete_campaign_character_file",
        "redirect_to_character_controls",
    ]

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_controls_delete_routes.py").read_text(encoding="utf-8")
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
        for node in ast.walk(app_tree)
    )

    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1

    app_registrations = {
        node.func.id: node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {
            "register_character_controls_assignment_routes",
            "register_character_controls_delete_route",
        }
    }
    assert (
        app_registrations["register_character_controls_assignment_routes"].lineno
        < app_registrations["register_character_controls_delete_route"].lineno
    )
    registration = app_registrations["register_character_controls_delete_route"]
    keyword_values = {keyword.arg: keyword.value for keyword in registration.keywords}
    for name in (
        "can_manage_campaign_content",
        "get_auth_store",
        "get_current_user",
        "delete_campaign_character_file",
    ):
        assert isinstance(keyword_values[name], ast.Lambda)
    for name in (
        "load_character_context",
        "campaign_supports_character_controls_routes",
        "redirect_to_character_controls",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name


def _flash(client) -> tuple[str, str]:
    with client.session_transaction() as browser_session:
        return browser_session["_flashes"][-1]


def _handler_module(app):
    handler = inspect.unwrap(app.view_functions[ENDPOINT])
    return importlib.import_module(handler.__module__)


def test_delete_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)

    assert rule.rule == "/campaigns/<campaign_slug>/characters/<character_slug>/controls/delete"
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert endpoints.index("character_controls_assignment_remove") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_equipment_systems_item_search"
    )


def test_delete_scope_admission_preserves_anonymous_missing_and_assignment_non_bypass(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.post(f"{ROUTE_PATH}?mode=session", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/controls/delete?mode%3Dsession"
    )

    assert client.post(
        "/campaigns/missing/characters/arden-march/controls/delete",
        data={"confirm_character_slug": "arden-march"},
    ).status_code == 404

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.post(
        ROUTE_PATH, data={"confirm_character_slug": "arden-march"}
    ).status_code == 404

    set_campaign_visibility("linden-pass", characters="public")
    assert client.post(
        ROUTE_PATH, data={"confirm_character_slug": "arden-march"}
    ).status_code == 403


@pytest.mark.parametrize("user_key", ("party", "observer", "outsider"))
def test_delete_body_keeps_non_manager_denial_after_public_scope_admission(
    client, sign_in, users, set_campaign_visibility, user_key
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users[user_key]["email"], users[user_key]["password"])
    assert client.post(
        ROUTE_PATH, data={"confirm_character_slug": "arden-march"}
    ).status_code == 403


def test_delete_preserves_view_as_csrf_and_bearer_order(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as = client.post(ROUTE_PATH, data={"confirm_character_slug": "wrong"})
    assert view_as.status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.post(ROUTE_PATH, data={"confirm_character_slug": "wrong"})
    assert csrf.status_code == 400
    assert "Refresh the page and try again." in csrf.get_data(as_text=True)

    token = issue_api_token(app, users["admin"]["email"], label="p33-browser-bearer")
    bearer = app.test_client().post(
        ROUTE_PATH,
        data={"confirm_character_slug": "wrong"},
        headers=api_headers(token),
    )
    assert bearer.status_code == 302


def test_delete_preserves_load_system_manager_order_and_denied_no_eager_work(
    client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["party"]["email"], users["party"]["password"])
    calls: list[str] = []

    original_load = CharacterRepository.get_visible_character
    original_supports = app_module.supports_character_controls_routes

    def load(repository, *args):
        calls.append("load")
        return original_load(repository, *args)

    def supports(system):
        calls.append("supports")
        return original_supports(system)

    def manage(campaign_slug):
        calls.append("manage")
        return False

    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    monkeypatch.setattr(app_module, "supports_character_controls_routes", supports)
    monkeypatch.setattr(app_module, "can_manage_campaign_content", manage)
    monkeypatch.setattr(
        app_module,
        "get_auth_store",
        lambda: (_ for _ in ()).throw(AssertionError("denial reached store")),
    )
    monkeypatch.setattr(
        app_module,
        "delete_campaign_character_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("denial reached deletion")
        ),
    )

    response = client.post(ROUTE_PATH, data={"confirm_character_slug": "arden-march"})
    assert response.status_code == 403
    assert calls == ["load", "supports", "manage"]

    calls.clear()
    monkeypatch.setattr(app_module, "supports_character_controls_routes", lambda system: False)
    response = client.post(ROUTE_PATH, data={"confirm_character_slug": "arden-march"})
    assert response.status_code == 404
    assert calls == ["load"]


@pytest.mark.parametrize(
    ("data", "expected_message"),
    (
        ({}, "Type arden-march to confirm deletion."),
        ({"confirm_character_slug": "ARDEN-MARCH"}, "Type arden-march to confirm deletion."),
        ({"confirm_character_slug": "not-arden-march"}, "Type arden-march to confirm deletion."),
    ),
)
def test_delete_confirmation_uses_trimmed_form_only_and_exact_controls_redirect(
    client, sign_in, users, data, expected_message
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        f"{ROUTE_PATH}?mode=session",
        data={**data, "mode": "session"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=controls&mode=session"
    )
    assert _flash(client) == ("error", expected_message)

    json_only = client.post(
        ROUTE_PATH,
        json={"confirm_character_slug": "arden-march"},
        follow_redirects=False,
    )
    assert json_only.status_code == 302
    assert _flash(client) == ("error", "Type arden-march to confirm deletion.")


def test_delete_preserves_store_actor_assignment_delete_audit_and_response_order(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    audit_payload: dict[str, object] = {}
    assignment = SimpleNamespace(user_id=users["owner"]["id"])

    class Store:
        def get_character_assignment(self, campaign_slug, character_slug):
            events.append("assignment")
            return assignment

        def write_audit_event(self, **kwargs):
            events.append("audit")
            audit_payload.update(kwargs)

    actor = SimpleNamespace(id=users["admin"]["id"])
    deleted = SimpleNamespace(
        deleted_files=True,
        deleted_state=True,
        deleted_assignment=True,
        deleted_assets=True,
    )

    store = Store()
    monkeypatch.setattr(app_module, "get_auth_store", lambda: events.append("store") or store)
    monkeypatch.setattr(app_module, "get_current_user", lambda: events.append("actor") or actor)

    def delete(*args, **kwargs):
        events.append(("delete", args, kwargs))
        return deleted

    monkeypatch.setattr(app_module, "delete_campaign_character_file", delete)
    route_module = _handler_module(app)
    original_flash = route_module.flash
    original_redirect = route_module.redirect
    original_url_for = route_module.url_for
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category))
        or original_flash(message, category),
    )
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda *args, **kwargs: events.append(("url_for", args, kwargs))
        or original_url_for(*args, **kwargs),
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda location: events.append(("redirect", location)) or original_redirect(location),
    )

    response = client.post(
        ROUTE_PATH,
        data={"confirm_character_slug": "  arden-march  "},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters")
    assert [event if isinstance(event, str) else event[0] for event in events] == [
        "store",
        "actor",
        "assignment",
        "delete",
        "audit",
        "flash",
        "url_for",
        "redirect",
    ]
    delete_event = next(event for event in events if not isinstance(event, str) and event[0] == "delete")
    assert delete_event[1][:3] == (
        app.config["CAMPAIGNS_DIR"],
        "linden-pass",
        "arden-march",
    )
    assert delete_event[2] == {
        "state_store": app.extensions["character_state_store"],
        "auth_store": store,
    }
    assert audit_payload == {
        "event_type": "character_deleted",
        "actor_user_id": users["admin"]["id"],
        "target_user_id": users["owner"]["id"],
        "campaign_slug": "linden-pass",
        "character_slug": "arden-march",
        "metadata": {
            "deleted_files": True,
            "deleted_state": True,
            "deleted_assignment": True,
            "deleted_assets": True,
            "source": "character_controls",
        },
    }
    assert _flash(client) == ("success", "Deleted character Arden March.")


def test_delete_none_branch_preserves_error_without_audit(app, client, sign_in, users, monkeypatch):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    class Store:
        def get_character_assignment(self, *args):
            return SimpleNamespace(user_id=users["owner"]["id"])

        def write_audit_event(self, **kwargs):
            raise AssertionError("none branch audited")

    store = Store()
    monkeypatch.setattr(app_module, "get_auth_store", lambda: store)
    monkeypatch.setattr(app_module, "delete_campaign_character_file", lambda *args, **kwargs: None)

    response = client.post(
        ROUTE_PATH,
        data={"confirm_character_slug": "arden-march"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters")
    assert _flash(client) == ("error", "That character no longer exists.")


@pytest.mark.parametrize("fault_stage", ("delete", "audit", "flash", "url_for", "redirect"))
def test_delete_preserves_fault_order_and_post_delete_partial_commit_boundary(
    app, client, sign_in, users, monkeypatch, fault_stage
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[str] = []
    deleted = SimpleNamespace(
        deleted_files=True,
        deleted_state=True,
        deleted_assignment=True,
        deleted_assets=True,
    )

    class Store:
        def get_character_assignment(self, *args):
            events.append("assignment")
            return SimpleNamespace(user_id=users["owner"]["id"])

        def write_audit_event(self, **kwargs):
            events.append("audit")
            if fault_stage == "audit":
                raise RuntimeError("audit fault")

    monkeypatch.setattr(app_module, "get_auth_store", lambda: events.append("store") or Store())

    def delete(*args, **kwargs):
        events.append("delete")
        if fault_stage == "delete":
            raise RuntimeError("delete fault")
        return deleted

    monkeypatch.setattr(app_module, "delete_campaign_character_file", delete)
    route_module = _handler_module(app)
    for name in ("flash", "url_for", "redirect"):
        if name == fault_stage:
            monkeypatch.setattr(
                route_module,
                name,
                lambda *args, _name=name, **kwargs: (_ for _ in ()).throw(
                    RuntimeError(f"{_name} fault")
                ),
            )

    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        client.post(ROUTE_PATH, data={"confirm_character_slug": "arden-march"})

    assert events[:3] == ["store", "assignment", "delete"]
    if fault_stage == "delete":
        assert "audit" not in events
    else:
        assert "audit" in events
