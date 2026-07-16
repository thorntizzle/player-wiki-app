from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.character_session_notes_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/session/notes"
ENDPOINT = "character_session_notes"
DEPENDENCY_ORDER = [
    "load_character_context",
    "campaign_supports_character_session_routes",
    "has_session_mode_access",
    "get_current_user",
    "ensure_active_session_for_session_character_mutation",
    "parse_expected_revision",
    "get_character_state_service",
    "is_session_character_return_requested",
    "render_session_character_page",
    "render_character_page",
    "redirect_to_character_mode",
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


def _dependencies(events: list[tuple], *, update_error=None, session_return=False):
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

    service = SimpleNamespace(update_player_notes=update)

    def get_service(*args):
        events.append(("service", args))
        return service

    def return_requested(*args):
        events.append(("return_requested", args))
        return session_return

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
        "ensure_active_session_for_session_character_mutation": active,
        "parse_expected_revision": revision,
        "get_character_state_service": get_service,
        "is_session_character_return_requested": return_requested,
        "render_session_character_page": session_page,
        "render_character_page": character_page,
        "redirect_to_character_mode": redirect,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterSessionNotesRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_notes_routes.py").read_text(encoding="utf-8")
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
        and node.name == "register_character_session_notes_route"
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
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 200
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 212
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
    assert len(route_decorators) == 30

    for index, registrar_name in (
        (290, "register_character_session_currency_route"),
        (291, "register_character_session_notes_route"),
    ):
        assert isinstance(create_app.body[index], ast.Expr)
        assert isinstance(create_app.body[index].value, ast.Call)
        assert isinstance(create_app.body[index].value.func, ast.Name)
        assert create_app.body[index].value.func.id == registrar_name
    assert isinstance(create_app.body[292], ast.FunctionDef)
    assert create_app.body[292].name == "character_session_personal"

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[291])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionNotesRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert isinstance(by_name["has_session_mode_access"], ast.Lambda)
    assert isinstance(by_name["get_current_user"], ast.Lambda)
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in DEPENDENCY_ORDER
        if name not in {"has_session_mode_access", "get_current_user"}
    )


def test_moved_handler_keeps_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_notes_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    original_app = ast.parse(
        inspect.cleandoc(
            '''
            def character_session_notes(campaign_slug: str, character_slug: str):
                campaign, record = load_character_context(campaign_slug, character_slug)
                if not campaign_supports_character_session_routes(campaign):
                    abort(404)
                if not has_session_mode_access(campaign_slug, character_slug):
                    abort(403)

                user = get_current_user()
                if user is None:
                    abort(403)

                notes_markdown = request.form.get("player_notes_markdown", "")
                return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
                inactive_session_redirect = ensure_active_session_for_session_character_mutation(
                    campaign_slug,
                    character_slug,
                    anchor="session-notes",
                )
                if inactive_session_redirect is not None:
                    return inactive_session_redirect
                try:
                    expected_revision = parse_expected_revision()
                    get_character_state_service().update_player_notes(
                        record,
                        expected_revision=expected_revision,
                        notes_markdown=notes_markdown,
                        updated_by_user_id=user.id,
                    )
                except CharacterStateConflictError:
                    flash("This sheet changed in another session. Refresh the page and try again.", "error")
                    if is_session_character_return_requested(campaign_slug, character_slug):
                        return render_session_character_page(
                            campaign_slug,
                            character_slug,
                            notes_draft=notes_markdown,
                            status_code=409,
                        )
                    return render_character_page(
                        campaign_slug,
                        character_slug,
                        notes_draft=notes_markdown,
                        force_session_mode=return_to_session_mode,
                        status_code=409,
                    )
                except (CharacterStateValidationError, ValueError) as exc:
                    flash(str(exc), "error")
                    if is_session_character_return_requested(campaign_slug, character_slug):
                        return render_session_character_page(
                            campaign_slug,
                            character_slug,
                            notes_draft=notes_markdown,
                            status_code=400,
                        )
                    return render_character_page(
                        campaign_slug,
                        character_slug,
                        notes_draft=notes_markdown,
                        force_session_mode=return_to_session_mode,
                        status_code=400,
                    )

                flash("Note saved.", "success")
                return redirect_to_character_mode(campaign_slug, character_slug, anchor="session-notes")
            '''
        )
    ).body[0]
    assert _canonical_handler(moved) == _canonical_handler(original_app)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_session_currency") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_session_personal")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == ROUTE_PATH.replace("linden-pass", "<campaign_slug>").replace(
        "arden-march", "<character_slug>"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_success_order_raw_form_values_and_redirect(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))

    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"player_notes_markdown": "  raw note  ", "mode": " SeSsIoN "},
    ):
        assert _handler(app)("linden-pass", "arden-march") == "redirected"

    assert [event[0] for event in events] == [
        "load",
        "support",
        "access",
        "user",
        "active",
        "revision",
        "service",
        "update",
        "redirect",
    ]
    update = next(event for event in events if event[0] == "update")
    assert update[2] == {
        "expected_revision": 17,
        "notes_markdown": "  raw note  ",
        "updated_by_user_id": 42,
    }
    assert events[-1][2] == {"anchor": "session-notes"}


def test_inactive_session_guard_runs_after_form_reads_and_before_revision(app, monkeypatch):
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
        data={"player_notes_markdown": "draft", "mode": "session"},
    ):
        assert _handler(app)("linden-pass", "arden-march") == "inactive"
    assert [event[0] for event in events] == ["load", "support", "access", "user", "active"]


@pytest.mark.parametrize(
    ("error", "session_return", "expected", "status"),
    [
        (route_module.CharacterStateConflictError(), True, "session-page", 409),
        (route_module.CharacterStateConflictError(), False, "character-page", 409),
        (ValueError("bad notes"), True, "session-page", 400),
        (ValueError("bad notes"), False, "character-page", 400),
    ],
)
def test_conflict_and_validation_preserve_exact_draft_rerender(
    app, monkeypatch, error, session_return, expected, status
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, update_error=error, session_return=session_return),
    )
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"player_notes_markdown": "draft", "mode": "session"},
    ):
        assert _handler(app)("linden-pass", "arden-march") == expected
    render = next(event for event in events if event[0] in {"session_page", "character_page"})
    assert render[2]["notes_draft"] == "draft"
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
            event[0] in {"user", "active", "revision", "service", "update"}
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
