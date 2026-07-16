from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.character_session_personal_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/session/personal"
ENDPOINT = "character_session_personal"
DEPENDENCY_ORDER = [
    "load_character_context",
    "campaign_supports_character_session_routes",
    "has_session_mode_access",
    "get_current_user",
    "is_session_character_return_requested",
    "campaign_supports_native_character_tools",
    "session_character_advanced_personal_edit_block_message",
    "session_character_personal_edit_block_message",
    "redirect_to_campaign_session_character",
    "ensure_active_session_for_session_character_mutation",
    "parse_expected_revision",
    "get_character_state_service",
    "render_session_character_page",
    "render_character_page",
    "redirect_to_character_mode",
]
STRING_FIELDS = {
    "session_character_advanced_personal_edit_block_message": (
        "SESSION_CHARACTER_ADVANCED_PERSONAL_EDIT_BLOCK_MESSAGE"
    ),
    "session_character_personal_edit_block_message": (
        "SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE"
    ),
}


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
            return ast.copy_location(
                ast.Name(id=STRING_FIELDS.get(node.attr, node.attr), ctx=node.ctx),
                node,
            )
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    node = _DependencyQualifier().visit(ast.fix_missing_locations(node))
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


def _dependencies(
    events: list[tuple],
    *,
    update_error=None,
    session_return=False,
    native_tools=True,
):
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(slug="arden-march")
    user = SimpleNamespace(id=42)

    def load(*args):
        events.append(("load", args))
        return campaign, record

    def support(*args):
        events.append(("support", args))
        return True

    def access(*args):
        events.append(("access", args))
        return True

    def current_user(*args):
        events.append(("user", args))
        return user

    def return_requested(*args):
        events.append(("return_requested", args))
        return session_return

    def native(*args):
        events.append(("native", args))
        return native_tools

    def session_redirect(*args, **kwargs):
        events.append(("session_redirect", args, kwargs))
        return "session-redirect"

    def active(*args, **kwargs):
        events.append(("active", args, kwargs))
        return None

    def revision(*args):
        events.append(("revision", args))
        return 17

    def update(*args, **kwargs):
        events.append(("update", args, kwargs))
        if update_error is not None:
            raise update_error
        return "updated"

    service = SimpleNamespace(update_personal_details=update)

    def get_service(*args):
        events.append(("service", args))
        return service

    def session_page(*args, **kwargs):
        events.append(("session_page", args, kwargs))
        return "session-page"

    def character_page(*args, **kwargs):
        events.append(("character_page", args, kwargs))
        return "character-page"

    def redirect(*args, **kwargs):
        events.append(("redirect", args, kwargs))
        return "redirected"

    return {
        "load_character_context": load,
        "campaign_supports_character_session_routes": support,
        "has_session_mode_access": access,
        "get_current_user": current_user,
        "is_session_character_return_requested": return_requested,
        "campaign_supports_native_character_tools": native,
        "session_character_advanced_personal_edit_block_message": "advanced guidance",
        "session_character_personal_edit_block_message": "read guidance",
        "redirect_to_campaign_session_character": session_redirect,
        "ensure_active_session_for_session_character_mutation": active,
        "parse_expected_revision": revision,
        "get_character_state_service": get_service,
        "render_session_character_page": session_page,
        "render_character_page": character_page,
        "redirect_to_character_mode": redirect,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterSessionPersonalRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_personal_routes.py").read_text(
            encoding="utf-8"
        )
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
        and node.name == "register_character_session_personal_route"
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
        (291, "register_character_session_notes_route"),
        (292, "register_character_session_personal_route"),
    ):
        assert isinstance(create_app.body[index], ast.Expr)
        assert isinstance(create_app.body[index].value, ast.Call)
        assert isinstance(create_app.body[index].value.func, ast.Name)
        assert create_app.body[index].value.func.id == registrar_name
    assert isinstance(create_app.body[293], ast.Expr)
    assert isinstance(create_app.body[293].value, ast.Call)
    assert isinstance(create_app.body[293].value.func, ast.Name)
    assert create_app.body[293].value.func.id == "register_character_session_rest_route"

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[292])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionPersonalRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert isinstance(by_name["has_session_mode_access"], ast.Lambda)
    assert isinstance(by_name["get_current_user"], ast.Lambda)
    for field_name, constant_name in STRING_FIELDS.items():
        assert isinstance(by_name[field_name], ast.Name)
        assert by_name[field_name].id == constant_name
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in DEPENDENCY_ORDER
        if name not in {
            "has_session_mode_access",
            "get_current_user",
            *STRING_FIELDS,
        }
    )


def test_moved_handler_keeps_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_personal_routes.py")
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
                "5eb526f60f117626fffbc8290937b49bfd8e90d6:player_wiki/app.py",
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
    assert endpoints.index("character_session_notes") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_session_rest")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/personal"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_success_order_raw_forms_and_redirect(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={
            "physical_description_markdown": "  raw physical  ",
            "background_markdown": "  raw background  ",
            "mode": " SeSsIoN ",
        },
    ):
        assert _handler(app)("linden-pass", "arden-march") == "redirected"

    assert [event[0] for event in events] == [
        "load",
        "support",
        "access",
        "user",
        "return_requested",
        "active",
        "revision",
        "service",
        "update",
        "redirect",
    ]
    update = next(event for event in events if event[0] == "update")
    assert update[2] == {
        "expected_revision": 17,
        "physical_description_markdown": "  raw physical  ",
        "background_markdown": "  raw background  ",
        "updated_by_user_id": 42,
    }
    assert events[-1][2] == {"anchor": "session-personal"}


@pytest.mark.parametrize(
    ("native_tools", "expected_message"),
    [(True, "advanced guidance"), (False, "read guidance")],
)
def test_session_character_return_blocks_write_with_exact_system_message(
    app, monkeypatch, native_tools, expected_message
):
    events: list[tuple] = []
    replacements = _dependencies(
        events,
        session_return=True,
        native_tools=native_tools,
    )
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda *args: events.append(("flash", args)),
    )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={
            "physical_description_markdown": "draft physical",
            "background_markdown": "draft background",
            "mode": "session",
        },
    ):
        assert _handler(app)("linden-pass", "arden-march") == "session-redirect"
    assert [event[0] for event in events] == [
        "load",
        "support",
        "access",
        "user",
        "return_requested",
        "native",
        "flash",
        "session_redirect",
    ]
    assert events[-2][1] == (expected_message, "error")
    assert events[-1][2] == {"anchor": "session-personal-guidance"}


def test_inactive_session_guard_precedes_revision_and_service(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def inactive(*args, **kwargs):
        events.append(("active", args, kwargs))
        return "inactive"

    replacements["ensure_active_session_for_session_character_mutation"] = inactive
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "inactive"
    assert [event[0] for event in events] == [
        "load",
        "support",
        "access",
        "user",
        "return_requested",
        "active",
    ]


@pytest.mark.parametrize(
    ("error", "session_return", "expected", "status"),
    [
        (route_module.CharacterStateConflictError(), True, "session-page", 409),
        (route_module.CharacterStateConflictError(), False, "character-page", 409),
        (ValueError("bad personal"), True, "session-page", 400),
        (ValueError("bad personal"), False, "character-page", 400),
    ],
)
def test_conflict_and_validation_preserve_exact_draft_rerender(
    app, monkeypatch, error, session_return, expected, status
):
    events: list[tuple] = []
    replacements = _dependencies(events, update_error=error)
    return_calls = iter((False, session_return))

    def return_requested(*args):
        events.append(("return_requested", args))
        return next(return_calls)

    replacements["is_session_character_return_requested"] = return_requested
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={
            "physical_description_markdown": "draft physical",
            "background_markdown": "draft background",
            "mode": "session",
        },
    ):
        assert _handler(app)("linden-pass", "arden-march") == expected
    render = next(event for event in events if event[0] in {"session_page", "character_page"})
    assert render[2]["physical_description_draft"] == "draft physical"
    assert render[2]["background_draft"] == "draft background"
    assert render[2]["status_code"] == status
    if not session_return:
        assert render[2]["force_session_mode"] is True


def test_denied_support_and_access_preserve_no_eager_downstream_work(app, monkeypatch):
    for denied_name, exception_type in (("support", NotFound), ("access", Forbidden)):
        events: list[tuple] = []
        replacements = _dependencies(events)
        if denied_name == "support":
            replacements["campaign_supports_character_session_routes"] = lambda campaign: False
        else:
            replacements["has_session_mode_access"] = lambda *args: False
        _install_dependencies(app, monkeypatch, **replacements)
        with app.test_request_context(ROUTE_PATH, method="POST"):
            with pytest.raises(exception_type):
                _handler(app)("linden-pass", "arden-march")
        assert not any(
            event[0]
            in {
                "user",
                "return_requested",
                "active",
                "revision",
                "service",
                "update",
            }
            for event in events
        )


def test_type_error_and_unrelated_faults_remain_uncaught(app, monkeypatch):
    for error in (TypeError("type fault"), RuntimeError("unexpected")):
        events: list[tuple] = []
        _install_dependencies(
            app,
            monkeypatch,
            **_dependencies(events, update_error=error),
        )
        with app.test_request_context(ROUTE_PATH, method="POST"):
            with pytest.raises(type(error), match=str(error)):
                _handler(app)("linden-pass", "arden-march")
