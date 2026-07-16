from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import NotFound

import player_wiki.character_session_rest_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/session/rest/long"
ENDPOINT = "character_session_rest"
DEPENDENCY_ORDER = [
    "load_character_context",
    "campaign_supports_character_session_routes",
    "redirect_to_character_mode",
    "ensure_active_session_for_session_character_mutation",
    "run_session_mutation",
    "get_character_state_service",
]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(current, **replacements),
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


def _dependencies(events: list[tuple]):
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(slug="arden-march")

    def load(*args):
        events.append(("load", args))
        return campaign, record

    def support(*args):
        events.append(("support", args))
        return True

    def redirect(*args, **kwargs):
        events.append(("redirect", args, kwargs))
        return "redirected"

    def active(*args, **kwargs):
        events.append(("active", args, kwargs))
        return None

    def apply_rest(*args, **kwargs):
        events.append(("apply_rest", args, kwargs))
        return "rest-state"

    service = SimpleNamespace(apply_rest=apply_rest)

    def get_service(*args):
        events.append(("service", args))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record, 17, 42)
        events.append(("action_result", (result,)))
        return "mutation-result"

    return {
        "load_character_context": load,
        "campaign_supports_character_session_routes": support,
        "redirect_to_character_mode": redirect,
        "ensure_active_session_for_session_character_mutation": active,
        "run_session_mutation": runner,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterSessionRestRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_rest_routes.py").read_text(encoding="utf-8")
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

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_session_rest_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "campaign_scope_access_required"
        for node in ast.walk(registrar)
    ) == 1

    create_app = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    assert len(create_app.body) == 295
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 198
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 210
    route_decorators = [
        decorator
        for node in ast.walk(create_app)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "app"
        and decorator.func.attr in {"get", "post"}
    ]
    assert len(route_decorators) == 28

    for index, registrar_name in (
        (292, "register_character_session_personal_route"),
        (293, "register_character_session_rest_route"),
    ):
        assert isinstance(create_app.body[index], ast.Expr)
        assert isinstance(create_app.body[index].value, ast.Call)
        assert isinstance(create_app.body[index].value.func, ast.Name)
        assert create_app.body[index].value.func.id == registrar_name
    assert isinstance(create_app.body[294], ast.Return)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[293])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionRestRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER)


def test_moved_handler_and_lambda_keep_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_rest_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    app_at_base = ast.parse(
        __import__("subprocess").check_output(
            [
                "git",
                "show",
                "8ff56f4d2c87289f89126fe9a4116579d25b03b2:player_wiki/app.py",
            ],
            text=True,
        )
    )
    create_app = next(
        node
        for node in app_at_base.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    original = next(
        node
        for node in create_app.body
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    assert _canonical_handler(moved) == _canonical_handler(original)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_session_personal") < endpoints.index(ENDPOINT)
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("confirm_rest", [None, "", "0", "yes", " 1 "])
def test_unconfirmed_redirects_after_support_with_zero_guard_runner_or_service(
    app, monkeypatch, confirm_rest
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    data = {} if confirm_rest is None else {"confirm_rest": confirm_rest}
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        assert _handler(app)("linden-pass", "arden-march", "long") == "redirected"
    assert [event[0] for event in events] == ["load", "support", "redirect"]
    assert events[-1][2] == {"anchor": "session-rest"}


def test_confirmed_preserves_outer_guard_runner_action_and_raw_rest_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"confirm_rest": "1"},
    ):
        assert _handler(app)("linden-pass", "arden-march", " long ") == "mutation-result"
    assert [event[0] for event in events] == [
        "load",
        "support",
        "active",
        "runner",
        "service",
        "apply_rest",
        "action_result",
    ]
    runner = next(event for event in events if event[0] == "runner")
    assert runner[2]["anchor"] == "session-rest"
    assert runner[2]["success_message"] == "Long rest applied."
    apply_rest = next(event for event in events if event[0] == "apply_rest")
    assert apply_rest[1][1] == " long "
    assert apply_rest[2] == {"expected_revision": 17, "updated_by_user_id": 42}


def test_inactive_session_guard_precedes_runner_and_service(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def inactive(*args, **kwargs):
        events.append(("active", args, kwargs))
        return "inactive"

    replacements["ensure_active_session_for_session_character_mutation"] = inactive
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"confirm_rest": "1"},
    ):
        assert _handler(app)("linden-pass", "arden-march", "long") == "inactive"
    assert [event[0] for event in events] == ["load", "support", "active"]


def test_unsupported_campaign_stops_before_confirmation_and_downstream_work(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def unsupported(campaign):
        events.append(("support", (campaign,)))
        return False

    replacements["campaign_supports_character_session_routes"] = unsupported
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST", data={"confirm_rest": "1"}):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "arden-march", "long")
    assert [event[0] for event in events] == ["load", "support"]


def test_service_and_runner_faults_remain_uncaught(app, monkeypatch):
    for dependency_name in ("get_character_state_service", "run_session_mutation"):
        events: list[tuple] = []
        replacements = _dependencies(events)

        def fail(*args, **kwargs):
            raise RuntimeError(f"{dependency_name} fault")

        replacements[dependency_name] = fail
        _install_dependencies(app, monkeypatch, **replacements)
        with app.test_request_context(
            ROUTE_PATH,
            method="POST",
            data={"confirm_rest": "1"},
        ):
            with pytest.raises(RuntimeError, match=f"{dependency_name} fault"):
                _handler(app)("linden-pass", "arden-march", "long")
