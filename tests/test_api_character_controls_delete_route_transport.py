from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_repository import CharacterRepository
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/controls"
ENDPOINT = "api.character_controls_delete"


def test_delete_api_transport_has_exact_dependency_and_composition_shape() -> None:
    import player_wiki.character_controls_delete_api_routes as route_module

    assert [field.name for field in fields(route_module.CharacterControlsDeleteApiDependencies)] == [
        "api_login_required",
        "load_character_controls_target",
        "json_error",
        "load_json_object",
        "flask_campaign_href",
        "can_manage_campaign_content",
        "get_auth_store",
        "get_current_user",
        "delete_campaign_character_file",
    ]
    source = (PROJECT_ROOT / "player_wiki" / "character_controls_delete_api_routes.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_controls_delete"
    ]
    assert len(handlers) == 1
    assert handlers[0].decorator_list == []
    registrar = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_controls_delete_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1

    api_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_controls_delete"
        for node in ast.walk(api_tree)
    )

    dependency_calls = [
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterControlsDeleteApiDependencies"
    ]
    assert len(dependency_calls) == 1
    by_keyword = {keyword.arg: keyword.value for keyword in dependency_calls[0].keywords}
    assert list(by_keyword) == [
        "api_login_required",
        "load_character_controls_target",
        "json_error",
        "load_json_object",
        "flask_campaign_href",
        "can_manage_campaign_content",
        "get_auth_store",
        "get_current_user",
        "delete_campaign_character_file",
    ]
    assert all(
        isinstance(by_keyword[name], ast.Name)
        for name in (
            "api_login_required",
            "load_character_controls_target",
            "json_error",
            "load_json_object",
            "flask_campaign_href",
        )
    )
    assert all(
        isinstance(by_keyword[name], ast.Lambda)
        for name in (
            "can_manage_campaign_content",
            "get_auth_store",
            "get_current_user",
            "delete_campaign_character_file",
        )
    )


def _assert_json_error(response, status: int, code: str, message: str) -> None:
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "ok": False,
        "error": {"code": code, "message": message},
    }


def _raw_view(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _handler_module(app):
    raw_view = _raw_view(app)
    if raw_view.__module__ == "player_wiki.api":
        return api_module
    import player_wiki.character_controls_delete_api_routes as route_module

    return route_module


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _raw_view(app)
    if "dependencies" in raw_view.__code__.co_freevars:
        for name in (
            "can_manage_campaign_content",
            "get_auth_store",
            "get_current_user",
            "delete_campaign_character_file",
        ):
            if name in replacements:
                monkeypatch.setattr(api_module, name, replacements[name])
        index = raw_view.__code__.co_freevars.index("dependencies")
        dependencies = raw_view.__closure__[index].cell_contents
        monkeypatch.setattr(
            raw_view.__closure__[index],
            "cell_contents",
            replace(dependencies, **replacements),
        )
        return

    closure_names = {
        "api_login_required",
        "load_character_controls_target",
        "json_error",
        "load_json_object",
        "flask_campaign_href",
    }
    for name, value in replacements.items():
        if name in closure_names and name in raw_view.__code__.co_freevars:
            index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)
        else:
            monkeypatch.setattr(api_module, name, value)


def test_delete_api_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    matches = [rule for rule in rules if rule.endpoint == ENDPOINT]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls"
    )
    assert matches[0].methods == {"DELETE", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == "character_controls_delete"

    options = client.options(ROUTE_PATH)
    assert options.status_code == 200
    assert set(options.headers["Allow"].replace(" ", "").split(",")) == {
        "DELETE",
        "OPTIONS",
    }
    for method in ("get", "head", "post", "put", "patch"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405

    assert endpoints.index("api.character_controls_assignment_delete") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_portrait_upsert")


def test_delete_api_anonymous_denial_precedes_target_load(app, client, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("anonymous denial loaded a Character target")

    monkeypatch.setattr(CharacterRepository, "get_visible_character", unexpected)
    response = client.delete(
        ROUTE_PATH,
        json={"confirm_character_slug": "arden-march"},
    )
    _assert_json_error(response, 401, "auth_required", "Authentication required.")


def test_delete_api_preserves_view_as_csrf_and_bearer_behavior(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as = client.delete(
        ROUTE_PATH,
        json={"confirm_character_slug": "arden-march"},
    )
    assert view_as.status_code == 403
    assert view_as.get_json() == {
        "ok": False,
        "error": {
            "code": "view_as_read_only",
            "message": (
                "View As mode is read-only for campaign API writes. "
                "Exit View As before making changes."
            ),
            "details": {},
        },
    }

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.delete(
        ROUTE_PATH,
        json={"confirm_character_slug": "arden-march"},
    )
    assert csrf.status_code == 400
    assert csrf.get_json()["error"]["code"] == "csrf_failed"

    token = issue_api_token(app, users["dm"]["email"], label="p35-bearer")
    bearer = app.test_client().delete(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"confirm_character_slug": "wrong"},
    )
    _assert_json_error(
        bearer,
        400,
        "validation_error",
        "Type arden-march to confirm deletion.",
    )


def test_delete_api_preserves_campaign_system_character_order(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["admin"]["email"], label="p35-order")
    headers = api_headers(token)
    assert client.delete(
        "/api/v1/campaigns/missing/characters/arden-march/controls",
        headers=headers,
        json={"confirm_character_slug": "arden-march"},
    ).status_code == 404

    events: list[str] = []
    original_supports = api_module.supports_character_controls_routes
    original_load = CharacterRepository.get_visible_character

    def supports(system):
        events.append("system")
        return original_supports(system)

    def load(repository, *args):
        events.append("character")
        return original_load(repository, *args)

    monkeypatch.setattr(api_module, "supports_character_controls_routes", supports)
    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    assert client.delete(
        "/api/v1/campaigns/linden-pass/characters/missing/controls",
        headers=headers,
        json={"confirm_character_slug": "missing"},
    ).status_code == 404
    assert events == ["system", "character"]

    events.clear()
    monkeypatch.setattr(
        api_module, "supports_character_controls_routes", lambda system: False
    )
    assert client.delete(
        ROUTE_PATH,
        headers=headers,
        json={"confirm_character_slug": "arden-march"},
    ).status_code == 404
    assert events == []


@pytest.mark.parametrize("user_key", ("owner", "party", "observer"))
def test_delete_api_valid_nonmanager_loads_target_before_forbidden(
    client, sign_in, users, monkeypatch, user_key
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    events: list[str] = []
    original = CharacterRepository.get_visible_character

    def load(repository, *args):
        events.append("target")
        return original(repository, *args)

    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    response = client.delete(
        ROUTE_PATH,
        json={"confirm_character_slug": "arden-march"},
    )
    _assert_json_error(
        response,
        403,
        "forbidden",
        "You do not have permission to delete this character.",
    )
    assert events == ["target"]


@pytest.mark.parametrize(
    ("json_body", "raw_body", "content_type", "message"),
    (
        (None, "{", "application/json", "Request body must be a JSON object."),
        ([], None, None, "Request body must be a JSON object."),
        ({}, None, None, "Type arden-march to confirm deletion."),
        (
            {"confirm_character_slug": " Arden-March "},
            None,
            None,
            "Type arden-march to confirm deletion.",
        ),
    ),
)
def test_delete_api_preserves_json_and_confirmation_errors(
    app, client, users, json_body, raw_body, content_type, message
):
    token = issue_api_token(app, users["dm"]["email"], label=f"p35-json-{message}")
    kwargs = {"headers": api_headers(token)}
    if raw_body is not None:
        kwargs.update(data=raw_body, content_type=content_type)
    else:
        kwargs["json"] = json_body
    response = client.delete(ROUTE_PATH, **kwargs)
    _assert_json_error(response, 400, "validation_error", message)


def test_delete_api_preserves_exact_dependency_order(app, client, monkeypatch):
    events: list[str] = []
    actor = SimpleNamespace(id=11, is_admin=True)
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(name="Arden March"))
    assignment = SimpleNamespace(user_id=22)
    deleted = SimpleNamespace(
        deleted_files=True,
        deleted_state=True,
        deleted_assignment=True,
        deleted_assets=True,
    )

    class Store:
        def get_character_assignment(self, *args):
            events.append("assignment")
            return assignment

        def write_audit_event(self, **kwargs):
            events.append("audit")

    _install_dependencies(
        app,
        monkeypatch,
        load_character_controls_target=lambda *args: events.append("target")
        or (campaign, record),
        can_manage_campaign_content=lambda *args: events.append("manager") or True,
        load_json_object=lambda: events.append("json")
        or {"confirm_character_slug": "arden-march"},
        get_auth_store=lambda: events.append("store") or Store(),
        get_current_user=lambda: events.append("actor") or actor,
        delete_campaign_character_file=lambda *args, **kwargs: events.append("delete")
        or deleted,
        flask_campaign_href=lambda *args: events.append("href") or "/roster",
    )
    route_module = _handler_module(app)
    original_url_for = route_module.url_for
    original_jsonify = route_module.jsonify
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda *args, **kwargs: events.append("url")
        or original_url_for(*args, **kwargs),
    )
    monkeypatch.setattr(
        route_module,
        "jsonify",
        lambda *args, **kwargs: events.append("response")
        or original_jsonify(*args, **kwargs),
    )

    response = client.delete(ROUTE_PATH)
    assert response.status_code == 200
    assert events == [
        "actor",
        "target",
        "manager",
        "json",
        "store",
        "actor",
        "assignment",
        "delete",
        "audit",
        "href",
        "url",
        "response",
    ]


def test_delete_api_helper_none_is_404_without_audit(app, client, monkeypatch):
    actor = SimpleNamespace(id=11, is_admin=True)
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(name="Arden March"))
    events: list[str] = []

    class Store:
        def get_character_assignment(self, *args):
            return None

        def write_audit_event(self, **kwargs):
            events.append("audit")

    _install_dependencies(
        app,
        monkeypatch,
        load_character_controls_target=lambda *args: (campaign, record),
        can_manage_campaign_content=lambda *args: True,
        load_json_object=lambda: {"confirm_character_slug": "arden-march"},
        get_auth_store=lambda: Store(),
        get_current_user=lambda: actor,
        delete_campaign_character_file=lambda *args, **kwargs: None,
    )
    response = client.delete(ROUTE_PATH)
    _assert_json_error(
        response, 404, "not_found", "That character no longer exists."
    )
    assert events == []


def test_delete_api_success_preserves_audit_response_and_forwarding(
    app, client, monkeypatch
):
    actor = SimpleNamespace(id=11, is_admin=True)
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(name="Arden March"))
    assignment = SimpleNamespace(user_id=22)
    deleted = SimpleNamespace(
        deleted_files=True,
        deleted_state=False,
        deleted_assignment=True,
        deleted_assets=False,
    )
    audit: dict[str, object] = {}

    class Store:
        def get_character_assignment(self, *args):
            return assignment

        def write_audit_event(self, **kwargs):
            audit.update(kwargs)

    _install_dependencies(
        app,
        monkeypatch,
        load_character_controls_target=lambda *args: (campaign, record),
        can_manage_campaign_content=lambda *args: True,
        load_json_object=lambda: {"confirm_character_slug": " arden-march "},
        get_auth_store=lambda: Store(),
        get_current_user=lambda: actor,
        delete_campaign_character_file=lambda *args, **kwargs: deleted,
        flask_campaign_href=lambda *args: "/campaigns/linden-pass/characters",
    )
    response = client.delete(ROUTE_PATH)
    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "ok": True,
        "message": "Deleted character Arden March.",
        "deleted_character_slug": "arden-march",
        "deleted_character_name": "Arden March",
        "links": {
            "roster_url": "/campaigns/linden-pass/characters",
            "flask_roster_url": "/campaigns/linden-pass/characters",
        },
    }
    assert audit == {
        "event_type": "character_deleted",
        "actor_user_id": 11,
        "target_user_id": 22,
        "campaign_slug": "linden-pass",
        "character_slug": "arden-march",
        "metadata": {
            "deleted_files": True,
            "deleted_state": False,
            "deleted_assignment": True,
            "deleted_assets": False,
            "source": "character_controls_api",
        },
    }


@pytest.mark.parametrize("fault_stage", ("audit", "href", "url_for", "jsonify"))
def test_delete_api_post_delete_faults_propagate_after_helper(
    app, client, monkeypatch, fault_stage
):
    events: list[str] = []
    actor = SimpleNamespace(id=11, is_admin=True)
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(name="Arden March"))
    deleted = SimpleNamespace(
        deleted_files=True,
        deleted_state=True,
        deleted_assignment=True,
        deleted_assets=True,
    )

    def stage(name, result=None):
        events.append(name)
        if name == fault_stage:
            raise RuntimeError(f"{name} fault")
        return result

    class Store:
        def get_character_assignment(self, *args):
            return None

        def write_audit_event(self, **kwargs):
            stage("audit")

    _install_dependencies(
        app,
        monkeypatch,
        load_character_controls_target=lambda *args: (campaign, record),
        can_manage_campaign_content=lambda *args: True,
        load_json_object=lambda: {"confirm_character_slug": "arden-march"},
        get_auth_store=lambda: Store(),
        get_current_user=lambda: actor,
        delete_campaign_character_file=lambda *args, **kwargs: stage("delete", deleted),
        flask_campaign_href=lambda *args: stage("href", "/roster"),
    )
    route_module = _handler_module(app)
    original_url_for = route_module.url_for
    original_jsonify = route_module.jsonify
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda *args, **kwargs: stage(
            "url_for", original_url_for(*args, **kwargs)
        ),
    )
    monkeypatch.setattr(
        route_module,
        "jsonify",
        lambda *args, **kwargs: stage("jsonify", original_jsonify(*args, **kwargs)),
    )

    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        client.delete(ROUTE_PATH)
    assert events[0] == "delete"


def test_delete_api_p34_malicious_slug_has_no_eager_or_effect_work(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["admin"]["email"], label="p35-malicious")
    requested_slug = "..\\outside-character"
    encoded_slug = quote(requested_slug, safe="")
    events: list[str] = []

    def unexpected(stage):
        def fail(*args, **kwargs):
            events.append(stage)
            raise AssertionError(f"malicious slug reached {stage}")

        return fail

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected("state"))
    _install_dependencies(
        app,
        monkeypatch,
        can_manage_campaign_content=unexpected("manager"),
        load_json_object=unexpected("json"),
        get_auth_store=unexpected("store"),
        delete_campaign_character_file=unexpected("delete"),
        flask_campaign_href=unexpected("href"),
    )
    route_module = _handler_module(app)
    monkeypatch.setattr(route_module, "url_for", unexpected("url_for"))
    monkeypatch.setattr(route_module, "jsonify", unexpected("jsonify"))
    response = client.delete(
        f"/api/v1/campaigns/linden-pass/characters/{encoded_slug}/controls",
        headers=api_headers(token),
        json={"confirm_character_slug": requested_slug},
    )
    assert response.status_code == 404
    assert events == []
