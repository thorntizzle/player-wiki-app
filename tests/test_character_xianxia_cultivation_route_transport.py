from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.app as app_module
import player_wiki.character_xianxia_cultivation_routes as route_module
from player_wiki.character_store import CharacterStateConflictError


ENDPOINT = "character_xianxia_cultivation_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/cultivation-crane/cultivation"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _event_names(events):
    return [event[0] for event in events]


def _fixtures(tmp_path: Path, events: list[object]):
    definition = SimpleNamespace(
        name="Cultivation Crane",
        system="Xianxia",
        character_slug="cultivation-crane",
        xianxia={"realm": "Mortal"},
        to_dict=lambda: {"character_slug": "cultivation-crane"},
    )
    updated_definition = SimpleNamespace(
        name="Cultivation Crane",
        system="Xianxia",
        character_slug="cultivation-crane",
        xianxia={"realm": "Mortal", "updated": True},
        to_dict=lambda: {"character_slug": "cultivation-crane", "updated": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "managed"})
    state_record = SimpleNamespace(revision=7, state={"hp": {"current": 18}})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=state_record,
    )
    campaign = SimpleNamespace(system="Xianxia")
    user = SimpleNamespace(id=41)
    systems_service = object()
    character_dir = tmp_path / "characters" / "cultivation-crane"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    result = SimpleNamespace(
        definition=updated_definition,
        insight_cost=3,
        energy_name="Qi",
        yin_yang_name="Yin",
        target_name="Strength",
        martial_art_name="Heavenly Palm",
        rank_name="Initiate",
        technique_name="Cloud Step",
        current_realm="Mortal",
        target_realm="Immortal",
        total_rebuild_points=15,
        actions_per_turn=3,
    )

    class Coordinator:
        def __init__(self):
            self.expected_args = (
                record,
                updated_definition,
                import_metadata,
                {"hp": {"current": 18}},
            )

        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))

    def config(campaigns_dir, campaign_slug):
        events.append(("config", campaigns_dir, campaign_slug))
        return SimpleNamespace(characters_dir=character_dir.parent)

    def write(path, payload):
        events.append(("write", path.name, payload))

    return {
        "load_character_context": event("load", (campaign, record)),
        "get_systems_service": event("systems", systems_service),
        "list_visible_character_page_records": event("pages", ["page"]),
        "parse_expected_revision": event("revision", 7),
        "finalize_character_definition_for_write": event(
            "finalize", updated_definition
        ),
        "can_manage_campaign_session": event("manager", True),
        "character_advancement_lane": event("lane", "xianxia-cultivation"),
        "is_xianxia_system": event("xianxia", True),
        "get_current_user": event("user", user),
        "normalize_dm_player_wiki_int": event("integer", 2),
        "update_xianxia_insight_definition": event(
            "save_insight", updated_definition
        ),
        "update_xianxia_gathering_insight_definition": event(
            "record_gathering_insight", updated_definition
        ),
        "spend_xianxia_cultivation_energy_definition": event(
            "spend_cultivation_energy", result
        ),
        "spend_xianxia_meditation_definition": event(
            "spend_meditation_yin_yang", result
        ),
        "spend_xianxia_conditioning_definition": event(
            "spend_conditioning", result
        ),
        "spend_xianxia_training_definition": event("spend_training", result),
        "advance_xianxia_martial_art_rank_definition": event(
            "advance_martial_art_rank", result
        ),
        "learn_xianxia_generic_technique_definition": event(
            "learn_generic_technique", result
        ),
        "start_xianxia_realm_ascension_review_definition": event(
            "start_realm_ascension_review", result
        ),
        "reset_xianxia_realm_ascension_stats_definition": event(
            "reset_realm_ascension_stats", result
        ),
        "apply_xianxia_immortal_realm_rebuild_definition": event(
            "apply_immortal_realm_rebuild", result
        ),
        "apply_xianxia_divine_realm_rebuild_definition": event(
            "apply_divine_realm_rebuild", result
        ),
        "confirm_xianxia_realm_ascension_definition": event(
            "confirm_realm_ascension", result
        ),
        "build_managed_character_import_metadata": event(
            "metadata", import_metadata
        ),
        "merge_state_with_definition": event("merge", {"hp": {"current": 18}}),
        "present_character_detail": event(
            "present", {"xianxia_read": {"realm": "Mortal"}}
        ),
        "list_xianxia_generic_technique_learning_options": event(
            "options", [{"systems_ref": {"entry_key": "cloud-step"}}]
        ),
        "build_character_entry_href": event("href", "/systems/cloud-step"),
        "present_xianxia_cultivation_context": event(
            "cultivation", {"insight": {"available": 0}}
        ),
        "character_publication_coordinator": Coordinator(),
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    direct = [
        "load_character_context",
        "get_systems_service",
        "list_visible_character_page_records",
        "parse_expected_revision",
        "finalize_character_definition_for_write",
    ]
    forwarded = [
        "can_manage_campaign_session",
        "character_advancement_lane",
        "is_xianxia_system",
        "get_current_user",
        "normalize_dm_player_wiki_int",
        "update_xianxia_insight_definition",
        "update_xianxia_gathering_insight_definition",
        "spend_xianxia_cultivation_energy_definition",
        "spend_xianxia_meditation_definition",
        "spend_xianxia_conditioning_definition",
        "spend_xianxia_training_definition",
        "advance_xianxia_martial_art_rank_definition",
        "learn_xianxia_generic_technique_definition",
        "start_xianxia_realm_ascension_review_definition",
        "reset_xianxia_realm_ascension_stats_definition",
        "apply_xianxia_immortal_realm_rebuild_definition",
        "apply_xianxia_divine_realm_rebuild_definition",
        "confirm_xianxia_realm_ascension_definition",
        "build_managed_character_import_metadata",
        "merge_state_with_definition",
        "present_character_detail",
        "list_xianxia_generic_technique_learning_options",
        "build_character_entry_href",
        "present_xianxia_cultivation_context",
    ]
    expected_order = direct + forwarded + ["character_publication_coordinator"]
    assert [
        field.name
        for field in fields(
            route_module.CharacterXianxiaCultivationRouteDependencies
        )
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_cultivation_routes.py").read_text(
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
    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1

    registrar_call = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_character_xianxia_cultivation_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaCultivationRouteDependencies"
    )
    values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert set(values) == set(expected_order)
    for name in direct:
        assert isinstance(values[name], ast.Name)
        assert values[name].id == name
    assert all(isinstance(values[name], ast.Lambda) for name in forwarded)
    assert isinstance(values["character_publication_coordinator"], ast.Name)
    assert values["character_publication_coordinator"].id == (
        "character_publication_coordinator"
    )


def test_forwarded_dependencies_and_captured_store_keep_composition_identity(
    app, monkeypatch
):
    dependencies = dict(
        zip(_handler(app).__code__.co_freevars, _handler(app).__closure__ or ())
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(
        app_module, "can_manage_campaign_session", lambda *args: marker
    )
    monkeypatch.setattr(
        app_module.xianxia_cultivation,
        "update_xianxia_insight_definition",
        lambda *args, **kwargs: marker,
    )
    monkeypatch.setattr(
        app_module.xianxia_cultivation,
        "update_xianxia_gathering_insight_definition",
        lambda *args, **kwargs: marker,
    )
    monkeypatch.setattr(
        app_module.xianxia_cultivation,
        "present_xianxia_cultivation_context",
        lambda *args, **kwargs: marker,
    )
    assert dependencies.can_manage_campaign_session("campaign") is marker
    assert dependencies.update_xianxia_insight_definition(object()) is marker
    assert (
        dependencies.update_xianxia_gathering_insight_definition(object())
        is marker
    )
    assert dependencies.present_xianxia_cultivation_context(object()) is marker
    assert dependencies.character_publication_coordinator is app.extensions[
        "character_publication_coordinator"
    ]


def test_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/cultivation"
    )
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_import_xianxia_manual_view") < endpoints.index(
        "character_level_up_view"
    )
    assert endpoints.index("character_level_up_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_progression_repair_view"
    )
    assert endpoints.index("character_progression_repair_view") < endpoints.index(
        "character_edit_view"
    )
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_manager_denial_precedes_character_load(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["can_manage_campaign_session"] = (
        lambda campaign_slug: events.append(("manager", campaign_slug)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(Forbidden):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="../escape"
            )
    assert _event_names(events) == ["manager"]


def test_invalid_character_load_stops_before_state_or_cultivation_work(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def missing(*args, **kwargs):
        events.append(("load", args, kwargs))
        raise NotFound()

    dependencies["load_character_context"] = missing
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="../escape"
            )
    assert _event_names(events) == ["manager", "load"]


def test_unsupported_system_loads_then_redirects_without_user_or_presentation(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["character_advancement_lane"] = (
        lambda system: events.append(("lane", system)) or "unsupported"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="cultivation-crane"
        )
    assert response.status_code == 302
    assert response.location.endswith(
        "/campaigns/linden-pass/characters/cultivation-crane"
    )
    assert _event_names(events) == ["manager", "load", "lane"]


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_builds_full_presentation_and_ignores_query_values(
    app, monkeypatch, tmp_path, method
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    def render(template, **context):
        events.append(("render", template, context))
        return "rendered"

    monkeypatch.setattr(route_module, "render_template", render)
    with app.test_request_context(
        f"{ROUTE_PATH}?cultivation_action=unsupported&energy_key=Qi",
        method=method,
    ):
        assert _handler(app)(
            campaign_slug="linden-pass", character_slug="cultivation-crane"
        ) == "rendered"
    assert _event_names(events) == [
        "manager",
        "load",
        "lane",
        "xianxia",
        "systems",
        "pages",
        "present",
        "systems",
        "options",
        "href",
        "cultivation",
        "render",
    ]
    render_event = events[-1]
    assert render_event[1] == "character_cultivation_xianxia.html"
    assert render_event[2]["active_nav"] == "characters"


@pytest.mark.parametrize(
    "action",
    (
        "save_insight",
        "record_gathering_insight",
        "spend_cultivation_energy",
        "spend_meditation_yin_yang",
        "spend_conditioning",
        "spend_training",
        "advance_martial_art_rank",
        "learn_generic_technique",
        "start_realm_ascension_review",
        "reset_realm_ascension_stats",
        "apply_immortal_realm_rebuild",
        "apply_divine_realm_rebuild",
        "confirm_realm_ascension",
    ),
)
def test_all_actions_keep_mutation_and_persistence_order(
    app, monkeypatch, tmp_path, action
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)
    data = {
        "cultivation_action": action,
        "martial_art_index": "0",
        "expected_revision": "7",
    }
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="cultivation-crane"
        )
    assert response.status_code == 302
    assert action in _event_names(events)
    names = _event_names(events)
    action_index = names.index(action)
    assert names[action_index + 1 :] == [
        "finalize",
        "metadata",
        "merge",
        "publish",
    ]
    publish_event = next(event for event in events if event[0] == "publish")
    assert publish_event[1] == dependencies[
        "character_publication_coordinator"
    ].expected_args
    assert publish_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}


def test_missing_actor_stops_before_revision_and_mutation(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["get_current_user"] = lambda: events.append(("user",)) or None
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(Forbidden):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="cultivation-crane"
            )
    assert _event_names(events) == [
        "manager",
        "load",
        "lane",
        "xianxia",
        "user",
    ]


@pytest.mark.parametrize(
    ("error", "caught"),
    (
        (ValueError("invalid cultivation"), True),
        (TypeError("bug"), False),
    ),
)
def test_value_error_redirects_but_type_error_propagates(
    app, monkeypatch, tmp_path, error, caught
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        raise error

    dependencies["update_xianxia_insight_definition"] = fail
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        if caught:
            response = _handler(app)(
                campaign_slug="linden-pass", character_slug="cultivation-crane"
            )
            assert response.status_code == 302
        else:
            with pytest.raises(TypeError, match="bug"):
                _handler(app)(
                    campaign_slug="linden-pass", character_slug="cultivation-crane"
                )
    assert "publish" not in _event_names(events)


def test_conflict_after_merge_redirects_without_success(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    class ConflictCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise CharacterStateConflictError()

    dependencies["character_publication_coordinator"] = ConflictCoordinator()
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="cultivation-crane"
        )
    assert response.status_code == 302
    assert "publish" in _event_names(events)


def test_publication_fault_surfaces_after_merge(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    class FaultCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise RuntimeError("publication fault")

    dependencies["character_publication_coordinator"] = FaultCoordinator()
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match="publication fault"):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="cultivation-crane"
            )
    names = _event_names(events)
    assert names.index("merge") < names.index("publish")


def test_second_publication_fault_does_not_invoke_legacy_file_dependencies(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    class FaultCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise RuntimeError("publication fault")

    dependencies["character_publication_coordinator"] = FaultCoordinator()
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match="publication fault"):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="cultivation-crane"
            )
    names = _event_names(events)
    assert names.count("publish") == 1
    assert "config" not in names
    assert "write" not in names
