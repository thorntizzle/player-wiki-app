from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import Forbidden, NotFound

import pytest

import player_wiki.app as app_module
import player_wiki.character_xianxia_dao_use_request_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "xianxia/dao-immolating-use-requests"
)
ENDPOINT = "character_xianxia_dao_immolating_use_request"


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


def _fixtures(events: list[tuple]):
    definition = SimpleNamespace(system="XIANXIA", character_slug="arden-march")
    record = SimpleNamespace(
        definition=definition,
        import_metadata=SimpleNamespace(source="managed"),
    )
    updated_definition = SimpleNamespace(system="XIANXIA", character_slug="arden-march")
    managed_import = SimpleNamespace(source="managed-updated")

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    def is_xianxia(*args, **kwargs):
        events.append(("system", args, kwargs))
        return True

    def normalize(*args, **kwargs):
        events.append(("normalize", args, kwargs))
        return 7

    def request_use(*args, **kwargs):
        events.append(("request_use", args, kwargs))
        return SimpleNamespace(definition=updated_definition)

    def metadata(*args, **kwargs):
        events.append(("metadata", args, kwargs))
        return managed_import

    return {
        "run_character_definition_mutation": runner,
        "is_xianxia_system": is_xianxia,
        "normalize_dm_player_wiki_int": normalize,
        "request_xianxia_dao_immolating_use_definition": request_use,
        "build_managed_character_import_metadata": metadata,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "run_character_definition_mutation",
        "is_xianxia_system",
        "normalize_dm_player_wiki_int",
        "request_xianxia_dao_immolating_use_definition",
        "build_managed_character_import_metadata",
    ]
    assert [
        field.name
        for field in fields(
            route_module.CharacterXianxiaDaoUseRequestRouteDependencies
        )
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_dao_use_request_routes.py").read_text(
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
    action = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.FunctionDef) and node.name == "_action"
    )
    assert action.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
        for node in ast.walk(app_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_xianxia_dao_use_request_route"
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
    assert len(create_app.body) == 294
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 196
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 208
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_equipment_remove_route",
            "register_character_xianxia_dao_use_request_route",
            "register_character_xianxia_dao_use_record_route",
        }
    }
    assert (
        calls["register_character_equipment_remove_route"],
        calls["register_character_xianxia_dao_use_request_route"],
        calls["register_character_xianxia_dao_use_record_route"],
    ) == (276, 277, 278)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[277])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaDaoUseRequestRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert isinstance(by_name["run_character_definition_mutation"], ast.Name)
    assert all(isinstance(by_name[name], ast.Lambda) for name in expected_order[1:])


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_equipment_remove") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_xianxia_dao_immolating_use_record"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "xianxia/dao-immolating-use-requests"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_form_action_metadata_runner_order_and_contract(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    data = MultiDict(
        [
            ("dao_immolating_prepared_index", " 4 "),
            ("dao_immolating_prepared_index", "9"),
            ("dao_immolating_request_name", "First Name"),
            ("dao_immolating_request_name", "Second Name"),
            ("dao_immolating_request_notes", "First Notes"),
            ("dao_immolating_request_notes", "Second Notes"),
        ]
    )
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "system",
        "normalize",
        "request_use",
        "metadata",
        "action_result",
    ]
    runner = events[0]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "xianxia-dao-immolating-use-request"
    assert runner[2]["success_message"] == "Dao Immolating use request recorded."
    assert events[1][1] == ("XIANXIA",)
    assert events[2][1] == (" 4 ",)
    assert events[2][2] == {
        "field_label": "Prepared Dao Immolating Technique note"
    }
    request_use = events[3]
    assert request_use[1][0].character_slug == "arden-march"
    assert request_use[2] == {
        "request_name": "First Name",
        "notes": "First Notes",
        "prepared_record_index": 7,
    }
    metadata = events[4]
    assert metadata[1][0:2] == ("linden-pass", "arden-march")
    assert metadata[1][2].source == "managed"
    action_result = events[5][1][0]
    assert action_result[0].character_slug == "arden-march"
    assert action_result[1].source == "managed-updated"
    assert action_result[2] == {}


def test_blank_prepared_reference_skips_normalization_but_reads_name_and_notes(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    class RecordingForm:
        values = {
            "dao_immolating_prepared_index": "   ",
            "dao_immolating_request_name": "Ad Hoc Name",
            "dao_immolating_request_notes": "Ad Hoc Notes",
        }

        def get(self, name, default=""):
            events.append(("form", (name, default), {}))
            return self.values.get(name, default)

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    _install_dependencies(app, monkeypatch, **dependencies)
    assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    assert "normalize" not in [event[0] for event in events]
    assert [event[1][0] for event in events if event[0] == "form"] == [
        "dao_immolating_prepared_index",
        "dao_immolating_request_name",
        "dao_immolating_request_notes",
    ]
    request_use = next(event for event in events if event[0] == "request_use")
    assert request_use[2] == {
        "request_name": "Ad Hoc Name",
        "notes": "Ad Hoc Notes",
        "prepared_record_index": None,
    }


def test_unsupported_system_stops_before_form_request_or_metadata(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["is_xianxia_system"] = (
        lambda *args, **kwargs: events.append(("system", args, kwargs)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(
            ValueError,
            match="only available for Xianxia character sheets",
        ):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["runner", "system"]


def test_request_failure_stops_before_managed_import_metadata(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        events.append(("request_use", args, kwargs))
        raise ValueError("request validation fault")

    dependencies["request_xianxia_dao_immolating_use_definition"] = fault
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"dao_immolating_request_name": "Fault"},
    ):
        with pytest.raises(ValueError, match="request validation fault"):
            _handler(app)("linden-pass", "arden-march")
    assert "metadata" not in [event[0] for event in events]


def test_scope_denial_performs_no_runner_or_action_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached Dao use request handler")

    _install_dependencies(
        app,
        monkeypatch,
        run_character_definition_mutation=unexpected,
        is_xianxia_system=unexpected,
    )
    assert client.post(ROUTE_PATH).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_definition_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p60-dao-request")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_p34_failure_occurs_in_runner_before_system_or_form_work(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    dependencies["run_character_definition_mutation"] = invalid_runner
    _install_dependencies(app, monkeypatch, **dependencies)
    malicious_path = ROUTE_PATH.replace("arden-march", "..\\victim")
    with app.test_request_context(malicious_path, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim")
    assert [event[0] for event in events] == ["runner"]


@pytest.mark.parametrize(
    ("fault_stage", "form_data"),
    (
        ("runner", {}),
        ("system", {}),
        ("normalize", {"dao_immolating_prepared_index": "1"}),
        ("request_use", {}),
        ("metadata", {}),
    ),
)
def test_faults_propagate_at_every_transport_stage(
    app, monkeypatch, fault_stage, form_data
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    key = {
        "runner": "run_character_definition_mutation",
        "system": "is_xianxia_system",
        "normalize": "normalize_dm_player_wiki_int",
        "request_use": "request_xianxia_dao_immolating_use_definition",
        "metadata": "build_managed_character_import_metadata",
    }[fault_stage]
    dependencies[key] = fault
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST", data=form_data):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")


def test_forwarded_helpers_remain_late_monkeypatchable(app, monkeypatch):
    events: list[tuple] = []
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    original = freevars["dependencies"].cell_contents
    _install_dependencies(
        app,
        monkeypatch,
        run_character_definition_mutation=_fixtures(events)[
            "run_character_definition_mutation"
        ],
        is_xianxia_system=original.is_xianxia_system,
        normalize_dm_player_wiki_int=original.normalize_dm_player_wiki_int,
        request_xianxia_dao_immolating_use_definition=(
            original.request_xianxia_dao_immolating_use_definition
        ),
        build_managed_character_import_metadata=(
            original.build_managed_character_import_metadata
        ),
    )
    monkeypatch.setattr(
        app_module,
        "is_xianxia_system",
        lambda *args, **kwargs: events.append(("forwarded_system", args, kwargs))
        or True,
    )
    monkeypatch.setattr(
        app_module,
        "normalize_dm_player_wiki_int",
        lambda *args, **kwargs: events.append(("forwarded_normalize", args, kwargs))
        or 3,
    )
    monkeypatch.setattr(
        app_module,
        "request_xianxia_dao_immolating_use_definition",
        lambda *args, **kwargs: events.append(("forwarded_request", args, kwargs))
        or SimpleNamespace(definition=args[0]),
    )
    monkeypatch.setattr(
        app_module,
        "build_managed_character_import_metadata",
        lambda *args, **kwargs: events.append(("forwarded_metadata", args, kwargs))
        or args[2],
    )
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"dao_immolating_prepared_index": "3"},
    ):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_system",
        "forwarded_normalize",
        "forwarded_request",
        "forwarded_metadata",
    ]


def test_manager_use_record_route_preserves_module_ownership_and_manager_before_runner(
    app, monkeypatch
) -> None:
    app_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "app.py").read_text(encoding="utf-8")
    )
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_xianxia_dao_use_record_routes.py"
        ).read_text(encoding="utf-8")
    )
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_record"
        for node in ast.walk(app_tree)
    )
    manager = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_record"
    )
    assert manager.decorator_list == []
    manager_calls = [
        node.func.attr
        if isinstance(node.func, ast.Attribute)
        else node.func.id
        for node in ast.walk(manager)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute)
            or isinstance(node.func, ast.Name)
        )
    ]
    assert "can_manage_campaign_session" in manager_calls
    assert "run_character_definition_mutation" in manager_calls

    endpoint = "character_xianxia_dao_immolating_use_record"
    raw_view = inspect.unwrap(app.view_functions[endpoint])
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    events: list[str] = []

    def deny_manager(*args, **kwargs):
        events.append("manager")
        return False

    def unexpected(*args, **kwargs):
        events.append("downstream")
        raise AssertionError(
            "manager denial reached runner, load/access/P34/state/form/helper, or persistence work"
        )

    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(
            current,
            can_manage_campaign_session=deny_manager,
            run_character_definition_mutation=unexpected,
            is_xianxia_system=unexpected,
            normalize_dm_player_wiki_int=unexpected,
            record_xianxia_dao_immolating_use_definition=unexpected,
            build_managed_character_import_metadata=unexpected,
        ),
    )
    path = (
        "/campaigns/linden-pass/characters/..%5Cvictim/"
        "xianxia/dao-immolating-use-records"
    )
    with app.test_request_context(path, method="POST"):
        with pytest.raises(Forbidden):
            raw_view("linden-pass", "..\\victim")
    assert events == ["manager"]
