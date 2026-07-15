from __future__ import annotations

import ast
from dataclasses import replace
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.character_state_helpers import _write_campaign_config
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "api.character_create_context"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/create"


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    if "dependencies" in raw_view.__code__.co_freevars:
        index = raw_view.__code__.co_freevars.index("dependencies")
        dependencies = raw_view.__closure__[index].cell_contents
        monkeypatch.setattr(
            raw_view.__closure__[index],
            "cell_contents",
            replace(dependencies, **replacements),
        )
        return

    for name, value in replacements.items():
        index = raw_view.__code__.co_freevars.index(name)
        monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)


def _source_functions(name: str) -> list[tuple[str, ast.FunctionDef]]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("api.py", "character_create_context_api_routes.py"):
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


def _assert_json_error(response, status: int, code: str, message: str) -> None:
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


@pytest.mark.parametrize(
    ("actor", "expected_status", "expected_code"),
    (
        (None, 401, "auth_required"),
        ("owner", 403, "forbidden"),
        ("party", 403, "forbidden"),
        ("observer", 403, "forbidden"),
        ("outsider", 403, "forbidden"),
        ("dm", 200, None),
        ("admin", 200, None),
    ),
)
def test_create_context_actor_and_assignment_matrix(
    client,
    sign_in,
    users,
    actor,
    expected_status,
    expected_code,
):
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert response.content_type.startswith("application/json")
    if expected_code == "auth_required":
        assert response.get_json() == {
            "ok": False,
            "error": {
                "code": "auth_required",
                "message": "Authentication required.",
            },
        }
    elif expected_code == "forbidden":
        assert response.get_json() == {
            "ok": False,
            "error": {
                "code": "forbidden",
                "message": (
                    "You do not have permission to create characters in this campaign."
                ),
            },
        }
    else:
        assert response.get_json()["lane"] == "dnd5e"


@pytest.mark.parametrize("identity", ("browser", "bearer"))
def test_create_context_browser_and_bearer_identity_match(
    app,
    client,
    sign_in,
    users,
    identity,
):
    request_client = client
    headers = {}
    if identity == "browser":
        sign_in(users["dm"]["email"], users["dm"]["password"])
    else:
        request_client = app.test_client()
        token = issue_api_token(app, users["dm"]["email"], label="p38-create-context")
        headers = api_headers(token)

    response = request_client.get(ROUTE_PATH, headers=headers)

    assert response.status_code == 200
    assert response.get_json()["create"]["lane"] == "dnd5e"


def test_create_context_view_as_uses_effective_actor(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["dm"]["id"]
    assert client.get(ROUTE_PATH).status_code == 200

    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    denied = client.get(ROUTE_PATH)
    _assert_json_error(
        denied,
        403,
        "forbidden",
        "You do not have permission to create characters in this campaign.",
    )


@pytest.mark.parametrize("identity", ("anonymous", "bearer"))
def test_create_context_missing_campaign_precedes_actor_inspection(
    app,
    client,
    users,
    identity,
):
    headers = {}
    if identity == "bearer":
        token = issue_api_token(app, users["dm"]["email"], label="p38-missing-campaign")
        headers = api_headers(token)

    response = client.get(
        "/api/v1/campaigns/missing-campaign/characters/create",
        headers=headers,
    )

    assert response.status_code == 404


def test_create_context_dnd_xianxia_and_unsupported_system_lanes(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dnd = client.get(ROUTE_PATH)
    assert dnd.status_code == 200
    assert dnd.get_json()["lane"] == "dnd5e"
    assert dnd.get_json()["create"]["lane"] == "dnd5e"

    _configure_xianxia_campaign(app)
    xianxia = client.get(ROUTE_PATH)
    assert xianxia.status_code == 200
    assert xianxia.get_json()["lane"] == "xianxia"
    assert xianxia.get_json()["create"]["lane"] == "xianxia"

    def _unsupported(payload: dict) -> None:
        payload["system"] = "unsupported-test-system"
        payload["systems_library"] = "unsupported-test-system"

    _write_campaign_config(app, _unsupported)
    unsupported = client.get(ROUTE_PATH)
    _assert_json_error(
        unsupported,
        400,
        "unsupported_campaign_system",
        (
            "This campaign can still use the character roster, read-mode sheets, "
            "session-mode sheets, and Controls. Native DND-5E builder, edit, "
            "level-up, repair, retraining, PDF-import, and spellcasting tools "
            "are not implemented for this campaign system."
        ),
    )


def test_create_context_preserves_access_query_builder_jsonify_order(
    app,
    client,
    monkeypatch,
):
    events: list[object] = []
    campaign = SimpleNamespace(slug="linden-pass", system="DND-5E")

    def access(slug):
        events.append(("access", slug))
        return campaign, None

    def build(slug, current_campaign, values):
        events.append(("build", slug, current_campaign, values))
        return {"ok": True, "values": values}

    _install_dependencies(
        app,
        monkeypatch,
        ensure_character_authoring_access=access,
        build_character_create_payload=build,
    )
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    view_module = importlib.import_module(raw_view.__module__)
    original_jsonify = view_module.jsonify

    def recording_jsonify(payload):
        events.append(("jsonify", payload))
        return original_jsonify(payload)

    monkeypatch.setattr(view_module, "jsonify", recording_jsonify)
    response = client.get(
        f"{ROUTE_PATH}?blank=&repeat=first&repeat=second&spaces=+value+&alias=Quick+Reference"
    )

    expected_values = {
        "blank": "",
        "repeat": "first",
        "spaces": " value ",
        "alias": "Quick Reference",
    }
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "values": expected_values}
    assert events == [
        ("access", "linden-pass"),
        ("build", "linden-pass", campaign, expected_values),
        ("jsonify", {"ok": True, "values": expected_values}),
    ]


def test_create_context_denial_returns_immediately_without_query_or_builder_work(
    app,
    client,
    monkeypatch,
):
    campaign = SimpleNamespace(slug="linden-pass")
    denied_response = ({"denied": True}, 403)
    calls: list[str] = []

    def access(slug):
        calls.append("access")
        return campaign, denied_response

    def forbidden_builder(*args):
        pytest.fail("denied create context must not build a payload")

    _install_dependencies(
        app,
        monkeypatch,
        ensure_character_authoring_access=access,
        build_character_create_payload=forbidden_builder,
    )

    response = client.get(f"{ROUTE_PATH}?repeat=first&repeat=second")

    assert response.status_code == 403
    assert response.get_json() == {"denied": True}
    assert calls == ["access"]


@pytest.mark.parametrize("fault_name", ("access", "builder", "jsonify"))
def test_create_context_faults_propagate_once(
    app,
    client,
    monkeypatch,
    fault_name,
):
    campaign = SimpleNamespace(slug="linden-pass")
    calls: list[str] = []

    def access(slug):
        calls.append("access")
        if fault_name == "access":
            raise RuntimeError("access fault")
        return campaign, None

    def build(*args):
        calls.append("builder")
        if fault_name == "builder":
            raise RuntimeError("builder fault")
        return {"ok": True}

    _install_dependencies(
        app,
        monkeypatch,
        ensure_character_authoring_access=access,
        build_character_create_payload=build,
    )
    if fault_name == "jsonify":
        raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
        view_module = importlib.import_module(raw_view.__module__)

        def fault(*args):
            calls.append("jsonify")
            raise RuntimeError("jsonify fault")

        monkeypatch.setattr(view_module, "jsonify", fault)

    with pytest.raises(RuntimeError, match=f"{fault_name} fault"):
        client.get(ROUTE_PATH)

    expected = {
        "access": ["access"],
        "builder": ["access", "builder"],
        "jsonify": ["access", "builder", "jsonify"],
    }
    assert calls == expected[fault_name]


def test_create_context_endpoint_methods_order_manifest_and_policy(app):
    rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule == "/api/v1/campaigns/<campaign_slug>/characters/create"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == "character_create_context"

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("api.character_list") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_create_submit")

    assert app.test_client().options(ROUTE_PATH).status_code == 200
    assert app.test_client().put(ROUTE_PATH).status_code == 405

    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "GET"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["owning_domain"] == "characters"
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["access_policy"] == "character_manager_api"
    assert entry["system_restriction"] == "campaign_character_authoring_capability"

    policies = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-access-policies.json").read_text(
            encoding="utf-8"
        )
    )
    assert policies["endpoints"][ENDPOINT] == {
        "profile": "character_manager_api",
        "owning_domain": "characters",
        "system_restriction": "campaign_character_authoring_capability",
    }


def test_create_context_head_invokes_handler_and_options_does_not(
    app,
    client,
    monkeypatch,
):
    campaign = SimpleNamespace(slug="linden-pass")
    calls: list[str] = []

    def access(slug):
        calls.append("access")
        return campaign, None

    def build(*args):
        calls.append("builder")
        return {"ok": True}

    _install_dependencies(
        app,
        monkeypatch,
        ensure_character_authoring_access=access,
        build_character_create_payload=build,
    )

    head = client.head(ROUTE_PATH)
    assert head.status_code == 200
    assert head.get_data() == b""
    assert calls == ["access", "builder"]

    calls.clear()
    options = client.options(ROUTE_PATH)
    assert options.status_code == 200
    assert calls == []


def test_create_context_has_one_source_handler_and_transport_shape():
    matches = _source_functions("character_create_context")
    assert len(matches) == 1
    filename, handler = matches[0]
    module_path = PROJECT_ROOT / "player_wiki" / "character_create_context_api_routes.py"
    if not module_path.exists():
        assert filename == "api.py"
        assert len(handler.decorator_list) == 1
        return

    assert filename == "character_create_context_api_routes.py"
    assert handler.decorator_list == []
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_create_submit_transport_immediately_follows_context_registration():
    api_path = PROJECT_ROOT / "player_wiki" / "api.py"
    tree = ast.parse(api_path.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_create_submit"
        for node in ast.walk(tree)
    )
    register_api = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )

    def statement_name(statement):
        if isinstance(statement, ast.FunctionDef):
            return statement.name
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
        ):
            return statement.value.func.id
        return None

    statement_names = [statement_name(statement) for statement in register_api.body]
    context_index = statement_names.index("register_character_create_context_api_route")
    assert statement_names[context_index : context_index + 3] == [
        "register_character_create_context_api_route",
        "register_character_create_submit_api_route",
        "register_character_xianxia_manual_import_api_routes",
    ]

    route_path = PROJECT_ROOT / "player_wiki" / "character_create_submit_api_routes.py"
    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    submit = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_create_submit"
    ]
    assert len(submit) == 1
    assert submit[0].decorator_list == []
