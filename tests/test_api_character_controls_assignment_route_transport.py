from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.character_repository import CharacterRepository
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment"
UPDATE_ENDPOINT = "api.character_controls_assignment_update"
DELETE_ENDPOINT = "api.character_controls_assignment_delete"


def _install_dependencies(app, monkeypatch, endpoint: str, **replacements) -> None:
    raw_view = inspect.unwrap(app.view_functions[endpoint])
    if "dependencies" in raw_view.__code__.co_freevars:
        for name in ("get_current_user", "get_auth_store"):
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
        "load_character_controls_target",
        "json_error",
        "load_json_object",
        "serialize_character_controls_response",
    }
    for name, value in replacements.items():
        if name in closure_names:
            if name in raw_view.__code__.co_freevars:
                index = raw_view.__code__.co_freevars.index(name)
                monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)
        else:
            monkeypatch.setattr(api_module, name, value)


def _source_functions(name: str) -> list[tuple[str, ast.FunctionDef]]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("api.py", "character_controls_assignment_api_routes.py"):
        path = PROJECT_ROOT / "player_wiki" / filename
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        matches.extend(
            (filename, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    return matches


def _response_helper(app, endpoint: str):
    raw_view = inspect.unwrap(app.view_functions[endpoint])
    response_name = "serialize_character_controls_response"
    if response_name in raw_view.__code__.co_freevars:
        index = raw_view.__code__.co_freevars.index(response_name)
        return raw_view.__closure__[index].cell_contents
    index = raw_view.__code__.co_freevars.index("dependencies")
    return raw_view.__closure__[index].cell_contents.serialize_character_controls_response


def _assert_json_error(response, status: int, code: str, message: str) -> None:
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "ok": False,
        "error": {"code": code, "message": message},
    }


def test_assignment_api_routes_preserve_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    expected = {
        UPDATE_ENDPOINT: {"POST", "OPTIONS"},
        DELETE_ENDPOINT: {"DELETE", "OPTIONS"},
    }
    for endpoint, methods in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/api/v1/campaigns/<campaign_slug>/characters/"
            "<character_slug>/controls/assignment"
        )
        assert matches[0].methods == methods
        assert app.view_functions[endpoint].__name__ == endpoint.rsplit(".", 1)[1]

    options = client.options(ROUTE_PATH)
    assert options.status_code == 200
    assert set(options.headers["Allow"].replace(" ", "").split(",")) == {
        "POST",
        "DELETE",
        "OPTIONS",
    }
    for method in ("get", "put", "patch"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405

    assert endpoints.index("api.character_detail") < endpoints.index(UPDATE_ENDPOINT)
    assert endpoints.index(UPDATE_ENDPOINT) < endpoints.index(DELETE_ENDPOINT)
    assert endpoints.index(DELETE_ENDPOINT) < endpoints.index("api.character_controls_delete")


def test_assignment_api_anonymous_denial_precedes_target_load(app, client, monkeypatch):
    calls: list[str] = []

    def eager(*args, **kwargs):
        calls.append("target")
        raise AssertionError("anonymous denial loaded a character target")

    monkeypatch.setattr(CharacterRepository, "get_visible_character", eager)
    for method in (client.post, client.delete):
        response = method(ROUTE_PATH, json={"user_id": 1})
        _assert_json_error(response, 401, "auth_required", "Authentication required.")
    assert calls == []


@pytest.mark.parametrize("user_key", ("owner", "party", "dm", "observer"))
@pytest.mark.parametrize("method", ("post", "delete"))
def test_assignment_api_keeps_app_admin_only_after_eager_target_load(
    client, sign_in, users, monkeypatch, user_key, method
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    calls: list[str] = []
    original = CharacterRepository.get_visible_character

    def load(repository, *args):
        calls.append("target")
        return original(repository, *args)

    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    response = getattr(client, method)(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    _assert_json_error(
        response,
        403,
        "forbidden",
        "You do not have permission to assign character owners.",
    )
    assert calls == ["target"]


def test_assignment_api_preserves_view_as_csrf_and_bearer_behavior(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert view_as.status_code == 403
    assert view_as.get_json()["error"]["code"] == "view_as_read_only"

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert csrf.status_code == 400
    assert csrf.get_json() == {
        "ok": False,
        "error": {
            "code": "csrf_failed",
            "message": "The request could not be verified.",
            "details": {},
        },
    }

    token = issue_api_token(app, users["admin"]["email"], label="p32-api-assignment")
    bearer = app.test_client().post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"user_id": users["party"]["id"]},
    )
    assert bearer.status_code == 200


def test_assignment_api_missing_system_and_character_order(
    app, client, sign_in, users, monkeypatch
):
    token = issue_api_token(app, users["admin"]["email"], label="p32-order")
    headers = api_headers(token)
    assert client.post(
        "/api/v1/campaigns/missing/characters/arden-march/controls/assignment",
        headers=headers,
        json={"user_id": users["party"]["id"]},
    ).status_code == 404

    calls: list[str] = []
    original_supports = api_module.supports_character_controls_routes
    original_load = CharacterRepository.get_visible_character

    def supports(system):
        calls.append("system")
        return original_supports(system)

    def load(repository, *args):
        calls.append("character")
        return original_load(repository, *args)

    monkeypatch.setattr(api_module, "supports_character_controls_routes", supports)
    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    assert client.post(
        "/api/v1/campaigns/linden-pass/characters/missing/controls/assignment",
        headers=headers,
        json={"user_id": users["party"]["id"]},
    ).status_code == 404
    assert calls == ["system", "character"]

    calls.clear()
    monkeypatch.setattr(api_module, "supports_character_controls_routes", lambda system: False)
    assert client.post(
        ROUTE_PATH, headers=headers, json={"user_id": users["party"]["id"]}
    ).status_code == 404
    assert calls == []


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (None, "Choose a valid player to assign."),
        ([], "Choose a valid player to assign."),
        ({}, "Choose a valid player to assign."),
        ({"user_id": "not-an-id"}, "Choose a valid player to assign."),
        ({"user_id": 999999}, "Choose an active player account to assign."),
    ),
)
def test_assignment_api_update_preserves_payload_errors(
    app, client, users, payload, message
):
    token = issue_api_token(app, users["admin"]["email"], label=f"p32-payload-{payload!r}")
    response = client.post(ROUTE_PATH, headers=api_headers(token), json=payload)
    _assert_json_error(response, 400, "validation_error", message)


def test_assignment_api_update_preserves_account_membership_audit_and_response(
    app, client, users
):
    token = issue_api_token(app, users["admin"]["email"], label="p32-success")
    headers = api_headers(token)

    observer = client.post(
        ROUTE_PATH, headers=headers, json={"user_id": users["observer"]["id"]}
    )
    _assert_json_error(
        observer,
        400,
        "validation_error",
        "Character owners must have an active player membership in that campaign.",
    )

    assigned = client.post(
        ROUTE_PATH, headers=headers, json={"user_id": users["party"]["id"]}
    )
    assert assigned.status_code == 200
    assert assigned.content_type.startswith("application/json")
    assert assigned.get_json()["message"] == "Assigned arden-march to party@example.com."
    assert assigned.get_json()["character"]["controls"]["assignment"]["user_id"] == users["party"]["id"]

    with app.app_context():
        store = AuthStore()
        assignment = store.get_character_assignment("linden-pass", "arden-march")
        events = store.list_audit_events_for_user(users["party"]["id"], limit=20)
        event = next(event for event in events if event.event_type == "character_assignment_created")
        assert assignment is not None and assignment.user_id == users["party"]["id"]
        assert event.actor_user_id == users["admin"]["id"]
        assert event.target_user_id == users["party"]["id"]
        assert event.metadata == {
            "previous_user_id": users["owner"]["id"],
            "assignment_type": "owner",
            "source": "character_controls_api",
        }

    removed = client.delete(ROUTE_PATH, headers=headers)
    assert removed.status_code == 200
    assert removed.get_json()["message"] == "Cleared assignment for arden-march."
    assert removed.get_json()["character"]["controls"]["assignment"] is None

    with app.app_context():
        store = AuthStore()
        assert store.get_character_assignment("linden-pass", "arden-march") is None
        events = store.list_audit_events_for_user(users["party"]["id"], limit=20)
        event = next(event for event in events if event.event_type == "character_assignment_removed")
        assert event.actor_user_id == users["admin"]["id"]
        assert event.target_user_id == users["party"]["id"]
        assert event.metadata == {
            "assignment_type": "owner",
            "source": "character_controls_api",
        }


def test_assignment_api_delete_preserves_missing_and_race_branches(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["admin"]["email"], label="p32-delete-branches")
    headers = api_headers(token)
    with app.app_context():
        AuthStore().delete_character_assignment("linden-pass", "arden-march")
    missing = client.delete(ROUTE_PATH, headers=headers)
    _assert_json_error(
        missing,
        400,
        "validation_error",
        "That character does not currently have an assigned player.",
    )

    with app.app_context():
        AuthStore().upsert_character_assignment(
            users["owner"]["id"], "linden-pass", "arden-march"
        )
    monkeypatch.setattr(AuthStore, "delete_character_assignment", lambda self, *args: None)
    raced = client.delete(ROUTE_PATH, headers=headers)
    _assert_json_error(
        raced,
        400,
        "validation_error",
        "That character assignment no longer exists.",
    )


@pytest.mark.parametrize(
    ("endpoint", "method", "expected"),
    (
        (
            UPDATE_ENDPOINT,
            "post",
            ["actor", "target", "actor", "json", "store", "user", "membership", "previous", "upsert", "audit", "response"],
        ),
        (
            DELETE_ENDPOINT,
            "delete",
            ["actor", "target", "actor", "store", "previous", "delete", "audit", "response"],
        ),
    ),
)
def test_assignment_api_preserves_exact_dependency_order(
    app, client, monkeypatch, endpoint, method, expected
):
    events: list[str] = []
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="arden-march"))
    actor = SimpleNamespace(id=1, is_admin=True)
    target = SimpleNamespace(id=2, is_active=True, email="party@example.com")
    assignment = SimpleNamespace(user_id=2, assignment_type="owner")

    class Store:
        def get_user_by_id(self, user_id):
            events.append("user")
            return target

        def get_membership(self, *args, **kwargs):
            events.append("membership")
            return SimpleNamespace(role="player")

        def get_character_assignment(self, *args):
            events.append("previous")
            return assignment

        def upsert_character_assignment(self, *args):
            events.append("upsert")
            return assignment

        def delete_character_assignment(self, *args):
            events.append("delete")
            return assignment

        def write_audit_event(self, **kwargs):
            events.append("audit")

    _install_dependencies(
        app,
        monkeypatch,
        endpoint,
        load_character_controls_target=lambda *args: events.append("target") or (campaign, record),
        get_current_user=lambda: events.append("actor") or actor,
        load_json_object=lambda: events.append("json") or {"user_id": 2},
        get_auth_store=lambda: events.append("store") or Store(),
        serialize_character_controls_response=lambda *args, **kwargs: events.append("response") or ({"ok": True}, 200),
    )
    response = getattr(client, method)(ROUTE_PATH, json={"user_id": 2})
    assert response.status_code == 200
    assert events == expected


@pytest.mark.parametrize("endpoint,method", ((UPDATE_ENDPOINT, "post"), (DELETE_ENDPOINT, "delete")))
@pytest.mark.parametrize("fault_stage", ("audit", "response"))
def test_assignment_api_persistence_survives_post_commit_faults(
    app, client, users, monkeypatch, endpoint, method, fault_stage
):
    token = issue_api_token(app, users["admin"]["email"], label=f"p32-{method}-{fault_stage}")
    headers = api_headers(token)
    if method == "delete":
        with app.app_context():
            AuthStore().upsert_character_assignment(
                users["party"]["id"], "linden-pass", "arden-march"
            )

    if fault_stage == "audit":
        monkeypatch.setattr(
            AuthStore,
            "write_audit_event",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit fault")),
        )
    else:
        _install_dependencies(
            app,
            monkeypatch,
            endpoint,
            serialize_character_controls_response=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("response fault")),
        )

    kwargs = {"json": {"user_id": users["party"]["id"]}} if method == "post" else {}
    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        getattr(client, method)(ROUTE_PATH, headers=headers, **kwargs)

    with app.app_context():
        assignment = AuthStore().get_character_assignment("linden-pass", "arden-march")
        if method == "post":
            assert assignment is not None and assignment.user_id == users["party"]["id"]
        else:
            assert assignment is None


def test_assignment_api_response_serializes_record_before_links(app, client, monkeypatch):
    helper = _response_helper(app, UPDATE_ENDPOINT)
    names = list(helper.__code__.co_freevars)
    events: list[str] = []
    for name, value in {
        "serialize_character_record": lambda *args: events.append("record") or {},
        "serialize_character_links": lambda *args: events.append("links") or {},
    }.items():
        cell = helper.__closure__[names.index(name)]
        monkeypatch.setattr(cell, "cell_contents", value)
    campaign = SimpleNamespace()
    record = SimpleNamespace()
    with app.test_request_context("/"):
        response = helper("linden-pass", campaign, record, message="ok")
    assert response.get_json() == {
        "ok": True,
        "message": "ok",
        "character": {},
        "links": {},
    }
    assert events == ["record", "links"]


@pytest.mark.parametrize(
    "endpoint,method", ((UPDATE_ENDPOINT, "post"), (DELETE_ENDPOINT, "delete"))
)
@pytest.mark.parametrize("fault_stage", ("record", "links", "jsonify"))
def test_assignment_api_persistence_survives_each_response_stage_fault(
    app, client, users, monkeypatch, endpoint, method, fault_stage
):
    token = issue_api_token(
        app, users["admin"]["email"], label=f"p32-{method}-{fault_stage}"
    )
    headers = api_headers(token)
    if method == "delete":
        with app.app_context():
            AuthStore().upsert_character_assignment(
                users["party"]["id"], "linden-pass", "arden-march"
            )

    helper = _response_helper(app, endpoint)
    freevars = list(helper.__code__.co_freevars)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "record":
        cell = helper.__closure__[freevars.index("serialize_character_record")]
        monkeypatch.setattr(cell, "cell_contents", fault)
    elif fault_stage == "links":
        cell = helper.__closure__[freevars.index("serialize_character_links")]
        monkeypatch.setattr(cell, "cell_contents", fault)
    else:
        monkeypatch.setattr(api_module, "jsonify", fault)

    kwargs = (
        {"json": {"user_id": users["party"]["id"]}} if method == "post" else {}
    )
    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        getattr(client, method)(ROUTE_PATH, headers=headers, **kwargs)

    with app.app_context():
        assignment = AuthStore().get_character_assignment(
            "linden-pass", "arden-march"
        )
        if method == "post":
            assert assignment is not None
            assert assignment.user_id == users["party"]["id"]
        else:
            assert assignment is None


def test_assignment_api_manifest_and_policy_contract():
    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {
        (entry["endpoint"], entry["method"]): entry
        for entry in manifest["entries"]
        if entry["endpoint"] in {UPDATE_ENDPOINT, DELETE_ENDPOINT}
    }
    assert set(entries) == {(UPDATE_ENDPOINT, "POST"), (DELETE_ENDPOINT, "DELETE")}
    for entry in entries.values():
        assert entry["owning_domain"] == "characters"
        assert entry["authentication_policy"] == "api_identity_required"
        assert entry["access_policy"] == "character_admin_api"
        assert entry["system_restriction"] == "none"
        assert entry["view_as_policy"] == "campaign_mutations_blocked"

    policies = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-access-policies.json").read_text(encoding="utf-8")
    )
    for endpoint in (UPDATE_ENDPOINT, DELETE_ENDPOINT):
        assert policies["endpoints"][endpoint] == {
            "profile": "character_admin_api",
            "owning_domain": "characters",
        }


def test_assignment_api_has_one_source_handler_each():
    assert len(_source_functions("character_controls_assignment_update")) == 1
    assert len(_source_functions("character_controls_assignment_delete")) == 1


def test_assignment_api_explicit_transport_shape_after_extraction():
    path = PROJECT_ROOT / "player_wiki" / "character_controls_assignment_api_routes.py"
    if not path.exists():
        pytest.skip("explicit registration applies after extraction")
    import player_wiki.character_controls_assignment_api_routes as routes

    assert [field.name for field in fields(routes.CharacterControlsAssignmentApiDependencies)] == [
        "api_login_required",
        "load_character_controls_target",
        "get_current_user",
        "json_error",
        "load_json_object",
        "get_auth_store",
        "serialize_character_controls_response",
    ]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"character_controls_assignment_update", "character_controls_assignment_delete"}
    }
    assert set(handlers) == {"character_controls_assignment_update", "character_controls_assignment_delete"}
    assert all(node.decorator_list == [] for node in handlers.values())
    registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2
    assert len(_source_functions("character_controls_assignment_update")) == 1
    assert len(_source_functions("character_controls_assignment_delete")) == 1


def test_assignment_api_module_globals_remain_post_registration_monkeypatchable(
    app, client, monkeypatch
):
    events: list[str] = []
    campaign = SimpleNamespace()
    record = SimpleNamespace()
    actor = SimpleNamespace(id=1, is_admin=False)
    monkeypatch.setattr(api_module, "get_current_user", lambda: events.append("actor") or actor)
    monkeypatch.setattr(
        api_module,
        "get_auth_store",
        lambda: (_ for _ in ()).throw(AssertionError("denied request reached store")),
    )
    _install_dependencies(
        app,
        monkeypatch,
        UPDATE_ENDPOINT,
        load_character_controls_target=lambda *args: events.append("target") or (campaign, record),
    )
    response = client.post(ROUTE_PATH, json={"user_id": 2})
    assert response.status_code == 403
    assert events == ["actor", "target", "actor"]
