from __future__ import annotations

import ast
import copy
from dataclasses import fields
from functools import wraps
from pathlib import Path
import subprocess
from types import SimpleNamespace

from flask import Blueprint, Flask, request
import pytest

import player_wiki.campaign_visibility_routes as route_module
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "ea47be0a16ee49a9970e3b156da01bb76fc80b3c"
SCOPES = ("campaign", "wiki", "systems", "session", "combat", "characters", "dm_content")
LABELS = {scope: scope.replace("_", " ").title() for scope in SCOPES}
BROWSER_ROUTES = (
    (
        "campaign_control_panel_view",
        "/campaigns/<campaign_slug>/control-panel",
        "GET",
        {"GET", "HEAD", "OPTIONS"},
    ),
    (
        "campaign_control_panel_update_visibility",
        "/campaigns/<campaign_slug>/control-panel/visibility",
        "POST",
        {"POST", "OPTIONS"},
    ),
)
API_ROUTES = (
    (
        "campaign_control",
        "/api/v1/campaigns/<campaign_slug>/control",
        "GET",
        {"GET", "HEAD", "OPTIONS"},
    ),
    (
        "campaign_control_update_visibility",
        "/api/v1/campaigns/<campaign_slug>/control/visibility",
        "PATCH",
        {"PATCH", "OPTIONS"},
    ),
)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


class _DependencyNormalizer(ast.NodeTransformer):
    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "dependencies":
            legacy_name = {
                "campaign_visibility_scopes": "CAMPAIGN_VISIBILITY_SCOPES",
                "campaign_visibility_scope_labels": "CAMPAIGN_VISIBILITY_SCOPE_LABELS",
                "visibility_private": "VISIBILITY_PRIVATE",
            }.get(node.attr, node.attr)
            return ast.copy_location(ast.Name(id=legacy_name, ctx=node.ctx), node)
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    normalized = copy.deepcopy(node)
    normalized.decorator_list = []
    normalized = _DependencyNormalizer().visit(normalized)
    ast.fix_missing_locations(normalized)
    return ast.dump(normalized, include_attributes=False)


def test_family_has_exact_canonical_owner_dependency_and_slot_boundaries() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "campaign_visibility_routes.py").read_text(
            encoding="utf-8"
        )
    )
    app_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "app.py").read_text(encoding="utf-8"))
    api_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8"))
    old_app_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/app.py"],
            text=True,
        )
    )
    old_api_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"],
            text=True,
        )
    )
    old_create_app = _function(old_app_tree, "create_app")
    old_register_api = _function(old_api_tree, "register_api")
    create_app = _function(app_tree, "create_app")
    register_api = _function(api_tree, "register_api")

    browser_names = [route[0] for route in BROWSER_ROUTES]
    api_names = [route[0] for route in API_ROUTES]
    assert [node.name for node in old_create_app.body[230:232]] == browser_names
    assert [node.name for node in old_register_api.body[171:173]] == api_names

    moved = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in browser_names + api_names
    }
    assert list(moved) == browser_names + api_names
    for original in old_create_app.body[230:232] + old_register_api.body[171:173]:
        assert _canonical_handler(moved[original.name]) == _canonical_handler(original)

    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in browser_names
        for node in ast.walk(app_tree)
    )
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in api_names
        for node in ast.walk(api_tree)
    )
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "build_campaign_visibility_control_context"
        for node in create_app.body
    )
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "serialize_campaign_control_visibility_row"
        for node in register_api.body
    )

    assert len(create_app.body) == 294
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 196
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 208
    assert isinstance(create_app.body[230], ast.Expr)
    assert create_app.body[230].value.func.id == "register_campaign_visibility_browser_routes"
    assert isinstance(create_app.body[231], ast.FunctionDef)
    assert create_app.body[231].name == "campaign_systems_control_panel_view"

    assert len(register_api.body) == 256
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 203
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 213
    assert isinstance(register_api.body[171], ast.Expr)
    assert register_api.body[171].value.func.id == "register_campaign_visibility_api_routes"
    assert isinstance(register_api.body[172], ast.FunctionDef)
    assert register_api.body[172].name == "campaign_help"

    expected_browser_dependencies = [
        field.name for field in fields(route_module.CampaignVisibilityBrowserDependencies)
    ]
    expected_api_dependencies = [
        field.name for field in fields(route_module.CampaignVisibilityApiDependencies)
    ]
    for statement, dependency_type, expected in (
        (create_app.body[230], "CampaignVisibilityBrowserDependencies", expected_browser_dependencies),
        (register_api.body[171], "CampaignVisibilityApiDependencies", expected_api_dependencies),
    ):
        dependency_call = next(
            node
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == dependency_type
        )
        assert [keyword.arg for keyword in dependency_call.keywords] == expected

    for old_index, before in enumerate(old_create_app.body):
        if 230 <= old_index <= 231:
            continue
        new_index = old_index if old_index < 230 else old_index - 1
        assert ast.dump(before, include_attributes=False) == ast.dump(
            create_app.body[new_index], include_attributes=False
        )
    for old_index, before in enumerate(old_register_api.body):
        if 171 <= old_index <= 172:
            continue
        new_index = old_index if old_index < 171 else old_index - 1
        assert ast.dump(before, include_attributes=False) == ast.dump(
            register_api.body[new_index], include_attributes=False
        )


def test_runtime_preserves_exact_rules_methods_endpoints_and_family_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    for endpoint, path, _method, methods in BROWSER_ROUTES + API_ROUTES:
        full_endpoint = f"api.{endpoint}" if path.startswith("/api/v1/") else endpoint
        matches = [rule for rule in rules if rule.endpoint == full_endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert matches[0].methods == methods
        assert app.view_functions[full_endpoint].__name__ == endpoint

    assert endpoints.index("campaign_control_panel_view") < endpoints.index(
        "campaign_control_panel_update_visibility"
    )
    assert endpoints.index("api.campaign_control") < endpoints.index(
        "api.campaign_control_update_visibility"
    )
    assert len(rules) == 299
    assert sum(rule.endpoint != "static" for rule in rules) == 298
    assert sum(endpoint.startswith("api.") for endpoint in endpoints) == 136

    assert client.options("/campaigns/linden-pass/control-panel").status_code == 200
    assert client.options("/campaigns/linden-pass/control-panel/visibility").status_code == 200
    assert client.options("/api/v1/campaigns/linden-pass/control").status_code == 200
    assert client.options("/api/v1/campaigns/linden-pass/control/visibility").status_code == 200
    assert client.post("/campaigns/linden-pass/control-panel").status_code == 405
    assert client.get("/campaigns/linden-pass/control-panel/visibility").status_code == 405
    assert client.patch("/api/v1/campaigns/linden-pass/control").status_code == 405
    assert client.post("/api/v1/campaigns/linden-pass/control/visibility").status_code == 405


class _VisibilityStore:
    def __init__(self, events: list[tuple], *, fail_audit_scope: str | None = None):
        self.events = events
        self.values: dict[str, str] = {}
        self.fail_audit_scope = fail_audit_scope

    def get_campaign_visibility_setting(self, _campaign_slug: str, scope: str):
        value = self.values.get(scope)
        return None if value is None else SimpleNamespace(visibility=value)

    def upsert_campaign_visibility_setting(
        self,
        campaign_slug: str,
        scope: str,
        *,
        visibility: str,
        updated_by_user_id: int,
    ) -> None:
        self.values[scope] = visibility
        self.events.append(("write", campaign_slug, scope, visibility, updated_by_user_id))

    def write_audit_event(self, **kwargs) -> None:
        scope = kwargs["metadata"]["scope"]
        self.events.append(("audit", scope, kwargs["metadata"]["source"]))
        if scope == self.fail_audit_scope:
            raise RuntimeError(f"audit failed for {scope}")


def _browser_test_app(monkeypatch, store: _VisibilityStore, events: list[tuple]) -> Flask:
    app = Flask(__name__)
    app.secret_key = "transport-test"
    app.testing = True
    monkeypatch.setattr(route_module, "render_template", lambda template, **_context: template)

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            events.append(("login",))
            return view(*args, **kwargs)

        return wrapped

    dependencies = route_module.CampaignVisibilityBrowserDependencies(
        login_required=login_required,
        load_campaign_context=lambda slug: events.append(("load", slug)),
        can_manage_campaign_visibility=lambda slug: events.append(("authorize", slug)) or True,
        build_campaign_visibility_control_context=lambda slug: events.append(("context", slug)) or {},
        get_current_user=lambda: SimpleNamespace(id=7, is_admin=True),
        get_auth_store=lambda: store,
        get_campaign_default_scope_visibility=lambda _slug, _scope: "public",
        normalize_visibility_choice=lambda value: str(value).strip().lower(),
        is_valid_visibility=lambda value: value in {"public", "players", "dm", "private"},
        clear_campaign_visibility_cache=lambda slug: events.append(("clear", slug)),
        campaign_visibility_scopes=SCOPES,
        campaign_visibility_scope_labels=LABELS,
        visibility_private="private",
    )
    route_module.register_campaign_visibility_browser_routes(app, dependencies=dependencies)
    return app


def _api_test_app(store: _VisibilityStore, events: list[tuple]) -> Flask:
    app = Flask(__name__)
    app.testing = True
    api = Blueprint("api", __name__, url_prefix="/api/v1")

    def management_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            events.append(("authorize", kwargs["campaign_slug"]))
            return view(*args, **kwargs)

        return wrapped

    repository = SimpleNamespace(
        get_campaign=lambda slug: SimpleNamespace(slug=slug) if slug == "linden-pass" else None
    )
    dependencies = route_module.CampaignVisibilityApiDependencies(
        api_campaign_visibility_management_required=management_required,
        get_repository=lambda: repository,
        get_current_user=lambda: SimpleNamespace(id=11, is_admin=True),
        serialize_campaign=lambda campaign: {"slug": campaign.slug},
        serialize_campaign_control_visibility_row=lambda slug, scope: {
            "campaign_slug": slug,
            "scope": scope,
        },
        flask_campaign_href=lambda slug, page: f"/campaigns/{slug}/{page}",
        load_json_object=lambda: request.get_json(),
        json_error=lambda message, status, code: ({"ok": False, "error": {"message": message, "code": code}}, status),
        get_auth_store=lambda: store,
        get_campaign_default_scope_visibility=lambda _slug, _scope: "public",
        normalize_visibility_choice=lambda value: str(value).strip().lower(),
        is_valid_visibility=lambda value: value in {"public", "players", "dm", "private"},
        clear_campaign_visibility_cache=lambda slug: events.append(("clear", slug)),
        campaign_visibility_scopes=SCOPES,
        campaign_visibility_scope_labels=LABELS,
        visibility_private="private",
    )
    route_module.register_campaign_visibility_api_routes(api, dependencies=dependencies)
    app.register_blueprint(api)
    return app


@pytest.mark.parametrize("surface", ["browser", "api"])
def test_mutations_preserve_seven_scope_write_audit_order_and_cache_timing(
    monkeypatch,
    surface: str,
) -> None:
    events: list[tuple] = []
    store = _VisibilityStore(events)
    if surface == "browser":
        app = _browser_test_app(monkeypatch, store, events)
        response = app.test_client().post(
            "/campaigns/linden-pass/control-panel/visibility",
            data={f"{scope}_visibility": "dm" for scope in SCOPES},
        )
    else:
        app = _api_test_app(store, events)
        response = app.test_client().patch(
            "/api/v1/campaigns/linden-pass/control/visibility",
            json={"visibility": {scope: "dm" for scope in SCOPES}},
        )
    assert response.status_code in {200, 302}

    persistence = [event for event in events if event[0] in {"write", "audit", "clear"}]
    expected: list[tuple] = []
    source = "campaign_control_panel" if surface == "browser" else "campaign_control_api"
    user_id = 7 if surface == "browser" else 11
    for scope in SCOPES:
        expected.extend(
            [
                ("write", "linden-pass", scope, "dm", user_id),
                ("audit", scope, source),
            ]
        )
    expected.append(("clear", "linden-pass"))
    assert persistence == expected


@pytest.mark.parametrize("surface", ["browser", "api"])
def test_later_audit_failure_preserves_earlier_partial_commits_and_skips_cache(
    monkeypatch,
    surface: str,
) -> None:
    events: list[tuple] = []
    store = _VisibilityStore(events, fail_audit_scope="wiki")
    if surface == "browser":
        app = _browser_test_app(monkeypatch, store, events)
        request_call = lambda: app.test_client().post(
            "/campaigns/linden-pass/control-panel/visibility",
            data={f"{scope}_visibility": "dm" for scope in SCOPES},
        )
    else:
        app = _api_test_app(store, events)
        request_call = lambda: app.test_client().patch(
            "/api/v1/campaigns/linden-pass/control/visibility",
            json={"visibility": {scope: "dm" for scope in SCOPES}},
        )

    with pytest.raises(RuntimeError, match="audit failed for wiki"):
        request_call()
    assert store.values == {"campaign": "dm", "wiki": "dm"}
    persistence = [event for event in events if event[0] in {"write", "audit", "clear"}]
    assert persistence[-4:] == [
        ("write", "linden-pass", "campaign", "dm", 7 if surface == "browser" else 11),
        ("audit", "campaign", "campaign_control_panel" if surface == "browser" else "campaign_control_api"),
        ("write", "linden-pass", "wiki", "dm", 7 if surface == "browser" else 11),
        ("audit", "wiki", "campaign_control_panel" if surface == "browser" else "campaign_control_api"),
    ]
    assert not any(event[0] == "clear" for event in events)


def test_api_security_order_view_as_csrf_bearer_and_missing_campaign(
    app,
    client,
    sign_in,
    users,
) -> None:
    assert client.get("/api/v1/campaigns/missing/control").status_code == 404
    anonymous = client.get("/api/v1/campaigns/linden-pass/control")
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    player_token = issue_api_token(app, users["party"]["email"], label="visibility-player")
    forbidden = client.get(
        "/api/v1/campaigns/linden-pass/control",
        headers=api_headers(player_token),
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "forbidden"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session["view_as_user_id"] = users["party"]["id"]
    effective_actor = client.get("/api/v1/campaigns/linden-pass/control")
    assert effective_actor.status_code == 403

    view_as_write = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        json={"visibility": {"campaign": "players"}},
    )
    assert view_as_write.status_code == 403
    assert view_as_write.get_json()["error"]["code"] == "view_as_read_only"

    with client.session_transaction() as browser_session:
        browser_session.pop("view_as_user_id", None)
    csrf = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        json={"visibility": {"campaign": "players"}},
    )
    assert csrf.status_code == 400
    assert csrf.get_json()["error"]["code"] == "csrf_failed"

    admin_token = issue_api_token(app, users["admin"]["email"], label="visibility-admin-bearer")
    bearer = app.test_client().patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        headers=api_headers(admin_token),
        json={"visibility": {"campaign": "private"}},
    )
    assert bearer.status_code == 200
    assert "Campaign" in bearer.get_json()["changed_scopes"]


def test_browser_view_as_and_csrf_stop_before_visibility_mutation(
    app,
    client,
    sign_in,
    users,
) -> None:
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session["view_as_user_id"] = users["party"]["id"]

    effective_actor = client.get("/campaigns/linden-pass/control-panel")
    assert effective_actor.status_code == 403
    view_as_write = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={"campaign_visibility": "private"},
    )
    assert view_as_write.status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop("view_as_user_id", None)
    csrf = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={"campaign_visibility": "private"},
    )
    assert csrf.status_code == 400
    assert "That request could not be completed." in csrf.get_data(as_text=True)
