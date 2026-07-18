from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.auth_me_settings_update_api_routes as route_module
from player_wiki.auth_store import AuthStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "e498636d90ff7ef3b60f05fd882f6d39ca4d436e"
ROUTE_PATH = "/api/v1/me/settings"
ENDPOINT = "api.me_settings_update"
GET_ENDPOINT = "api.me_settings"
DEPENDENCY_ORDER = [
    "api_login_required",
    "get_current_user",
    "json_error",
    "load_json_object",
    "is_valid_theme_key",
    "is_valid_session_chat_order",
    "get_auth_store",
    "get_theme_preset",
    "normalize_session_chat_order",
    "serialize_user",
]
FORWARDED_DEPENDENCIES = {
    "get_current_user",
    "is_valid_theme_key",
    "is_valid_session_chat_order",
    "get_auth_store",
    "get_theme_preset",
    "normalize_session_chat_order",
}


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _dependencies_cell(app):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"]


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    cell = _dependencies_cell(app)
    monkeypatch.setattr(
        cell,
        "cell_contents",
        replace(cell.cell_contents, **replacements),
    )


class _DependencyQualifier(ast.NodeTransformer):
    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "dependencies"
        ):
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    node = _DependencyQualifier().visit(ast.fix_missing_locations(node))
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


class _PreferenceStore:
    def __init__(self, events: list[tuple]):
        self.events = events
        self.preferences = SimpleNamespace(
            theme_key="parchment",
            session_chat_order="newest_first",
            frontend_mode="flask",
        )

    def get_user_preferences(self, user_id):
        self.events.append(("get_preferences", user_id))
        return self.preferences

    def set_user_theme_key(self, user_id, value):
        self.events.append(("set_theme", user_id, value))
        self.preferences = SimpleNamespace(
            theme_key=value,
            session_chat_order=self.preferences.session_chat_order,
            frontend_mode="flask",
        )

    def set_user_session_chat_order(self, user_id, value):
        self.events.append(("set_chat", user_id, value))
        self.preferences = SimpleNamespace(
            theme_key=self.preferences.theme_key,
            session_chat_order=value,
            frontend_mode="flask",
        )


def _dependency_set(
    events: list[tuple],
    *,
    payload=None,
    user=object(),
    store=None,
):
    actual_user = (
        SimpleNamespace(id=7, email="reader@example.com", is_admin=False)
        if user.__class__ is object
        else user
    )
    actual_payload = (
        {"theme_key": " moonlit ", "session_chat_order": " oldest_first "}
        if payload is None
        else payload
    )
    actual_store = store or _PreferenceStore(events)

    def get_user():
        events.append(("get_user",))
        return actual_user

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    def load_payload():
        events.append(("load_json",))
        return actual_payload

    def valid_theme(value):
        events.append(("valid_theme", value))
        return True

    def valid_chat(value):
        events.append(("valid_chat", value))
        return True

    def get_store():
        events.append(("get_store",))
        return actual_store

    def get_preset(value):
        events.append(("get_preset", value))
        return SimpleNamespace(key="moonlit")

    def normalize_chat(value):
        events.append(("normalize_chat", value))
        return "oldest_first"

    def serialize_user(value):
        events.append(("serialize_user", value.id))
        return {"id": value.id}

    return {
        "get_current_user": get_user,
        "json_error": error,
        "load_json_object": load_payload,
        "is_valid_theme_key": valid_theme,
        "is_valid_session_chat_order": valid_chat,
        "get_auth_store": get_store,
        "get_theme_preset": get_preset,
        "normalize_session_chat_order": normalize_chat,
        "serialize_user": serialize_user,
    }


def test_transport_has_exact_dependencies_wrapper_registration_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthMeSettingsUpdateApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_me_settings_update_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_settings_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "me_settings_update"
        for node in ast.walk(api_tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id
        in {
            "api_campaign_scope_access_required",
            "api_admin_required",
            "current_app",
            "session",
            "request",
        }
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_me_settings_update_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    assert next(
        keyword.value.value
        for keyword in registration.keywords
        if keyword.arg == "endpoint"
    ) == "me_settings_update"
    methods = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "methods"
    )
    assert [item.value for item in methods.elts] == ["PATCH"]
    view_func = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "view_func"
    )
    assert isinstance(view_func, ast.Call)
    assert ast.unparse(view_func.func) == "dependencies.api_login_required"

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 217
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 227
    api_route_decorators = [
        decorator
        for node in ast.walk(register_api)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "api"
    ]
    assert len(api_route_decorators) == 49
    assert register_api.body[165].value.func.id == (
        "register_auth_me_settings_view_api_route"
    )
    assert register_api.body[166].value.func.id == (
        "register_auth_me_settings_update_api_route"
    )
    assert isinstance(register_api.body[167], ast.FunctionDef)
    assert register_api.body[167].name == "admin_dashboard_api"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[166])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthMeSettingsUpdateApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        if name in FORWARDED_DEPENDENCIES:
            assert isinstance(by_name[name], ast.Lambda)
        else:
            assert isinstance(by_name[name], ast.Name)

    assert {"load_json_object", "serialize_user"} <= {
        node.name
        for node in register_api.body
        if isinstance(node, ast.FunctionDef)
    }


def test_moved_handler_and_all_unrelated_register_api_statements_keep_canonical_ast() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_me_settings_update_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_settings_update"
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"], text=True
        )
    )
    new_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8")
    )
    old_register = next(
        node
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    new_register = next(
        node
        for node in new_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    original = old_register.body[166]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "me_settings_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index == 166:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_methods_login_headers_cache_and_get_admin_neighbors(
    app, client, users
):
    token = issue_api_token(app, users["party"]["email"], label="p105-party")
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index(GET_ENDPOINT) < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.admin_dashboard_api")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.head(ROUTE_PATH).status_code == 401

    anonymous = client.patch(ROUTE_PATH, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"theme_key": "moonlit"},
    )
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.headers.get("Cache-Control") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.get_json()["preferences"]["theme_key"] == "moonlit"


def test_handler_preserves_exact_payload_validation_commit_and_serialization_order(
    app, monkeypatch
):
    events: list[tuple] = []
    store = _PreferenceStore(events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(events, store=store),
    )
    original_jsonify = route_module.jsonify

    def record_jsonify(*args, **kwargs):
        events.append(("jsonify",))
        return original_jsonify(*args, **kwargs)

    monkeypatch.setattr(route_module, "jsonify", record_jsonify)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        response = _handler(app)()

    assert events == [
        ("get_user",),
        ("load_json",),
        ("valid_theme", " moonlit "),
        ("valid_chat", " oldest_first "),
        ("get_store",),
        ("get_preferences", 7),
        ("get_preset", " moonlit "),
        ("set_theme", 7, "moonlit"),
        ("normalize_chat", " oldest_first "),
        ("set_chat", 7, "oldest_first"),
        ("get_preferences", 7),
        ("serialize_user", 7),
        ("jsonify",),
    ]
    assert response.get_json() == {
        "ok": True,
        "preferences": {
            "frontend_mode": "flask",
            "session_chat_order": "oldest_first",
            "theme_key": "moonlit",
        },
        "user": {"id": 7},
    }


@pytest.mark.parametrize(
    ("payload", "invalid_dependency", "expected_message", "expected_events"),
    (
        (
            {"frontend_mode": "gen2", "theme_key": "moonlit"},
            None,
            "Preferred frontend selection is no longer available.",
            ["get_user", "load_json", "json_error"],
        ),
        (
            {},
            None,
            "No account settings were provided.",
            ["get_user", "load_json", "json_error"],
        ),
        (
            {"theme_key": "bad", "session_chat_order": "oldest_first"},
            "is_valid_theme_key",
            "Choose a valid theme preset.",
            ["get_user", "load_json", "valid_theme", "json_error"],
        ),
        (
            {"theme_key": "moonlit", "session_chat_order": "bad"},
            "is_valid_session_chat_order",
            "Choose a valid live session chat order.",
            ["get_user", "load_json", "valid_theme", "valid_chat", "json_error"],
        ),
    ),
)
def test_validation_stops_before_store_and_any_commit(
    app,
    monkeypatch,
    payload,
    invalid_dependency,
    expected_message,
    expected_events,
):
    events: list[tuple] = []
    replacements = _dependency_set(events, payload=payload)
    if invalid_dependency is not None:
        original = replacements[invalid_dependency]

        def reject(value):
            original(value)
            return False

        replacements[invalid_dependency] = reject
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == expected_events
    assert events[-1][1] == (expected_message, 400)
    assert events[-1][2] == {"code": "validation_error"}


def test_missing_user_and_json_value_error_keep_exact_taxonomy_and_zero_store_work(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(events, user=None),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == ["get_user", "json_error"]
    assert events[-1][1] == ("Authentication required.", 401)

    events.clear()
    replacements = _dependency_set(events)

    def invalid_json():
        events.append(("load_json",))
        raise ValueError("JSON object required.")

    replacements["load_json_object"] = invalid_json
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == ["get_user", "load_json", "json_error"]
    assert events[-1][1] == ("JSON object required.", 400)
    assert events[-1][2] == {"code": "validation_error"}


def test_unchanged_values_skip_both_setters_but_keep_normalization_and_final_read(
    app, monkeypatch
):
    events: list[tuple] = []
    store = _PreferenceStore(events)
    replacements = _dependency_set(
        events,
        payload={"theme_key": "parchment", "session_chat_order": "newest_first"},
        store=store,
    )
    replacements["get_theme_preset"] = (
        lambda value: events.append(("get_preset", value))
        or SimpleNamespace(key="parchment")
    )
    replacements["normalize_session_chat_order"] = (
        lambda value: events.append(("normalize_chat", value)) or "newest_first"
    )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        response = _handler(app)()
    assert response.status_code == 200
    assert not any(event[0].startswith("set_") for event in events)
    assert [event[0] for event in events].count("get_preferences") == 2
    assert ("get_preset", "parchment") in events
    assert ("normalize_chat", "newest_first") in events


def test_forwarded_globals_remain_post_registration_substitutable(app, monkeypatch):
    events: list[tuple] = []
    store = _PreferenceStore(events)
    replacements = _dependency_set(events, store=store)
    for name in FORWARDED_DEPENDENCIES:
        replacements.pop(name)
    _install_dependencies(app, monkeypatch, **replacements)

    monkeypatch.setattr(
        api_module,
        "get_current_user",
        lambda: events.append(("forwarded_user",)) or SimpleNamespace(id=19),
    )
    monkeypatch.setattr(
        api_module,
        "is_valid_theme_key",
        lambda value: events.append(("forwarded_theme_validator", value)) or True,
    )
    monkeypatch.setattr(
        api_module,
        "is_valid_session_chat_order",
        lambda value: events.append(("forwarded_chat_validator", value)) or True,
    )
    monkeypatch.setattr(
        api_module,
        "get_auth_store",
        lambda: events.append(("forwarded_store",)) or store,
    )
    monkeypatch.setattr(
        api_module,
        "get_theme_preset",
        lambda value: events.append(("forwarded_preset", value))
        or SimpleNamespace(key="moonlit"),
    )
    monkeypatch.setattr(
        api_module,
        "normalize_session_chat_order",
        lambda value: events.append(("forwarded_normalize", value))
        or "oldest_first",
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        _handler(app)()
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_user",
        "forwarded_theme_validator",
        "forwarded_chat_validator",
        "forwarded_store",
        "forwarded_preset",
        "forwarded_normalize",
    ]


@pytest.mark.parametrize(
    ("stage", "expected_theme", "expected_chat"),
    (
        ("theme_setter_post_commit", "moonlit", "newest_first"),
        ("normalize_after_theme", "moonlit", "newest_first"),
        ("chat_setter_post_commit", "moonlit", "oldest_first"),
        ("final_read", "moonlit", "oldest_first"),
        ("serialize_user", "moonlit", "oldest_first"),
        ("jsonify", "moonlit", "oldest_first"),
    ),
)
def test_two_independent_sqlite_commits_and_later_faults_never_roll_back(
    app,
    users,
    monkeypatch,
    stage,
    expected_theme,
    expected_chat,
):
    user_id = users["party"]["id"]
    original_set_theme = AuthStore.set_user_theme_key
    original_set_chat = AuthStore.set_user_session_chat_order
    original_get = AuthStore.get_user_preferences

    if stage == "theme_setter_post_commit":
        def set_theme_then_fault(self, target_user_id, value):
            original_set_theme(self, target_user_id, value)
            raise RuntimeError("theme post-commit fault")

        monkeypatch.setattr(AuthStore, "set_user_theme_key", set_theme_then_fault)
    elif stage == "chat_setter_post_commit":
        def set_chat_then_fault(self, target_user_id, value):
            original_set_chat(self, target_user_id, value)
            raise RuntimeError("chat post-commit fault")

        monkeypatch.setattr(
            AuthStore, "set_user_session_chat_order", set_chat_then_fault
        )

    events: list[tuple] = []
    replacements = _dependency_set(
        events,
        payload={"theme_key": "moonlit", "session_chat_order": "oldest_first"},
        user=SimpleNamespace(id=user_id),
    )
    replacements["get_auth_store"] = AuthStore
    replacements["get_theme_preset"] = lambda value: SimpleNamespace(key="moonlit")
    replacements["normalize_session_chat_order"] = lambda value: "oldest_first"

    if stage == "normalize_after_theme":
        replacements["normalize_session_chat_order"] = lambda value: (_ for _ in ()).throw(
            RuntimeError("normalize fault")
        )
    elif stage == "final_read":
        reads = 0

        def final_read_fault(self, target_user_id):
            nonlocal reads
            reads += 1
            if reads == 4:
                raise RuntimeError("final read fault")
            return original_get(self, target_user_id)

        monkeypatch.setattr(AuthStore, "get_user_preferences", final_read_fault)
    elif stage == "serialize_user":
        replacements["serialize_user"] = lambda user: (_ for _ in ()).throw(
            RuntimeError("serialize fault")
        )
    elif stage == "jsonify":
        monkeypatch.setattr(
            route_module,
            "jsonify",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("jsonify fault")),
        )

    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError):
            _handler(app)()

    monkeypatch.setattr(AuthStore, "get_user_preferences", original_get)
    with app.app_context():
        persisted = AuthStore().get_user_preferences(user_id)
    assert persisted.theme_key == expected_theme
    assert persisted.session_chat_order == expected_chat


def test_browser_session_requires_csrf_while_bearer_bypasses_it_and_view_as_keeps_real_actor(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session["view_as_user_id"] = users["party"]["id"]
    denied = client.patch(ROUTE_PATH, json={"theme_key": "verdant"})
    assert denied.status_code == 400
    assert denied.get_json()["error"]["code"] == "csrf_failed"

    csrf_token = "x" * 43
    with client.session_transaction() as browser_session:
        browser_session["csrf_token"] = csrf_token
    browser = client.patch(
        ROUTE_PATH,
        headers={"X-CSRF-Token": csrf_token},
        json={"theme_key": "verdant"},
    )
    assert browser.status_code == 200

    token = issue_api_token(app, users["party"]["email"], label="p105-csrf")
    bearer = app.test_client().patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"theme_key": "ember"},
    )
    assert bearer.status_code == 200
    with app.app_context():
        store = AuthStore()
        assert store.get_user_preferences(users["party"]["id"]).theme_key == "ember"
        assert store.get_user_preferences(users["admin"]["id"]).theme_key == "verdant"
