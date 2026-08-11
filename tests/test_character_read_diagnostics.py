from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

import pytest
from flask import Flask, Response

import player_wiki.app as app_module
from player_wiki.character_read_admission import CharacterReadAdmission
from player_wiki.character_read_diagnostics import (
    CHARACTER_READ_COMPONENTS,
    attach_character_read_diagnostics,
    classify_character_read_route,
    initialize_character_read_diagnostics,
    mark_character_read_access_complete,
    measure_character_read_component,
    set_character_read_outcome,
)


CHARACTER_ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march"
SESSION_CHARACTER_ROUTE_PATH = "/campaigns/linden-pass/session/character"


def _diagnostic_app(*, enabled: bool) -> Flask:
    app = Flask(__name__)
    app.config["LIVE_DIAGNOSTICS"] = enabled

    @app.get("/characters/<character_slug>", endpoint="character_read_view")
    def character_read_view(character_slug: str):
        mark_character_read_access_complete()
        with measure_character_read_component("page-records"):
            assert character_slug
        if character_slug == "busy":
            set_character_read_outcome("admission-503")
            return Response("busy", status=503)
        return Response("ok")

    @app.get(
        "/session/character",
        endpoint="campaign_session_character_view",
    )
    def session_character_view():
        mark_character_read_access_complete()
        return Response("ok")

    @app.before_request
    def start_character_read_diagnostics():
        initialize_character_read_diagnostics()

    @app.after_request
    def add_character_read_diagnostics(response):
        return attach_character_read_diagnostics(
            response,
            query_count=3,
            db_time_ms=1.25,
        )

    return app


def _assert_character_diagnostics(
    response,
    *,
    route_class: str,
    outcome: str = "ok",
) -> None:
    assert response.headers["X-Character-Read-Route"] == route_class
    assert response.headers["X-Character-Read-Outcome"] == outcome
    for component in (*CHARACTER_READ_COMPONENTS, "db", "total"):
        value = response.headers[f"X-Character-Read-{component.title()}-Ms"]
        assert float(value) >= 0
        assert f"character-{component};dur=" in response.headers["Server-Timing"]

    query_count = response.headers["X-Character-Read-Query-Count"]
    query_time_ms = response.headers["X-Character-Read-Query-Time-Ms"]
    response_bytes = response.headers["X-Character-Read-Response-Bytes"]
    assert int(query_count) >= 0
    assert float(query_time_ms) >= 0
    assert query_time_ms == response.headers["X-Character-Read-Db-Ms"]
    assert int(response_bytes) >= 0

    diagnostic_headers = "\n".join(
        f"{name}: {value}"
        for name, value in response.headers
        if name.startswith("X-Character-Read-") or name == "Server-Timing"
    )
    for private_value in (
        "linden-pass",
        "arden-march",
        "dm@example.com",
        "localhost",
        "127.0.0.1",
    ):
        assert private_value not in diagnostic_headers


def _install_character_render_measurement_spy(app, monkeypatch):
    original_measure = app_module.measure_character_read_component
    component_calls = []
    active_components = []

    @contextmanager
    def measure(component):
        component_calls.append(component)
        with original_measure(component):
            active_components.append(component)
            try:
                yield
            finally:
                active_components.pop()

    monkeypatch.setattr(app_module, "measure_character_read_component", measure)
    return component_calls, active_components


def _install_measured_character_manager_spy(
    app,
    monkeypatch,
    builder_name,
    active_components,
):
    render_character_page = app.extensions[
        "character_read_route_dependencies"
    ].render_character_page
    closure_index = render_character_page.__code__.co_freevars.index(builder_name)
    closure_cell = render_character_page.__closure__[closure_index]
    original_builder = closure_cell.cell_contents
    builder_calls = []

    def builder(*args, **kwargs):
        assert active_components and active_components[-1] == "managers"
        builder_calls.append(builder_name)
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(closure_cell, "cell_contents", builder)
    return builder_calls


def test_route_classification_is_a_fixed_sanitized_enum() -> None:
    assert classify_character_read_route("character_read_view") == "character-document"
    assert (
        classify_character_read_route(
            "character_read_view",
            requested_with="XMLHttpRequest",
        )
        == "character-fetch"
    )
    assert (
        classify_character_read_route(
            "character_read_view",
            requested_with="xmlhttprequest",
        )
        == "character-fetch"
    )
    assert (
        classify_character_read_route(
            "character_read_view",
            requested_with="not-the-contract",
        )
        == "character-document"
    )
    assert (
        classify_character_read_route("campaign_session_character_view", fragment="0")
        == "session-character-document"
    )
    assert (
        classify_character_read_route("campaign_session_character_view", fragment="1")
        == "session-character-fragment"
    )
    assert classify_character_read_route("static", fragment="1") is None


def test_enabled_diagnostics_emit_only_numeric_components_and_sanitized_enums() -> None:
    response = _diagnostic_app(enabled=True).test_client().get("/characters/example")

    _assert_character_diagnostics(response, route_class="character-document")
    assert response.headers["X-Character-Read-Admission-Ms"] == "0.00"
    assert response.headers["X-Character-Read-Query-Count"] == "3"
    assert response.headers["X-Character-Read-Query-Time-Ms"] == "1.25"
    assert response.headers["X-Character-Read-Response-Bytes"] == "2"
    assert "example" not in str(response.headers)


def test_disabled_diagnostics_add_no_character_headers() -> None:
    response = _diagnostic_app(enabled=False).test_client().get("/characters/example")

    assert not any(
        name.startswith("X-Character-Read-") for name, _value in response.headers
    )
    assert "Server-Timing" not in response.headers


def test_admission_busy_and_fragment_routes_remain_classifiable() -> None:
    app = _diagnostic_app(enabled=True)
    busy = app.test_client().get("/characters/busy")
    fragment = app.test_client().get("/session/character?fragment=1")

    assert busy.status_code == 503
    assert busy.headers["X-Character-Read-Outcome"] == "admission-503"
    assert fragment.headers["X-Character-Read-Route"] == "session-character-fragment"


@pytest.mark.parametrize(
    ("request_headers", "route_class"),
    (
        ({}, "character-document"),
        ({"X-Requested-With": "XMLHttpRequest"}, "character-fetch"),
    ),
)
def test_real_app_character_document_diagnostics_cover_direct_and_fetch_reads(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    request_headers,
    route_class,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = True
    component_calls, _active_components = _install_character_render_measurement_spy(
        app,
        monkeypatch,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"{CHARACTER_ROUTE_PATH}?page=quick",
        headers=request_headers,
    )

    assert response.status_code == 200
    _assert_character_diagnostics(response, route_class=route_class)
    assert int(response.headers["X-Character-Read-Query-Count"]) > 0
    assert int(response.headers["X-Character-Read-Response-Bytes"]) == len(response.data)
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "managers" not in component_calls
    assert response.headers["X-Character-Read-Managers-Ms"] == "0.00"


@pytest.mark.parametrize(
    ("page", "builder_name"),
    (
        ("controls", "build_character_controls_context"),
        ("inventory", "build_character_inventory_manager_context"),
        ("equipment", "build_character_equipment_state_context"),
    ),
)
def test_real_app_selected_character_manager_sections_measure_their_constructor(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
    builder_name,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = True
    component_calls, active_components = _install_character_render_measurement_spy(
        app,
        monkeypatch,
    )
    builder_calls = _install_measured_character_manager_spy(
        app,
        monkeypatch,
        builder_name,
        active_components,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(f"{CHARACTER_ROUTE_PATH}?page={page}")

    assert response.status_code == 200
    _assert_character_diagnostics(response, route_class="character-document")
    assert component_calls.count("managers") == 1
    assert builder_calls == [builder_name]
    manager_ms = response.headers["X-Character-Read-Managers-Ms"]
    assert float(manager_ms) >= 0
    assert f"character-managers;dur={manager_ms}" in response.headers["Server-Timing"]


@pytest.mark.parametrize(
    ("query", "request_headers", "route_class"),
    (
        (
            "?character=arden-march&page=overview",
            {},
            "session-character-document",
        ),
        (
            "?character=arden-march&page=overview&fragment=1",
            {"X-Requested-With": "XMLHttpRequest"},
            "session-character-fragment",
        ),
    ),
)
def test_real_app_session_character_document_and_fragment_diagnostics(
    app,
    client,
    sign_in,
    users,
    query,
    request_headers,
    route_class,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = True
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"{SESSION_CHARACTER_ROUTE_PATH}{query}",
        headers=request_headers,
    )

    assert response.status_code == 200
    _assert_character_diagnostics(response, route_class=route_class)
    assert response.headers["X-Character-Read-Admission-Ms"] == "0.00"
    assert int(response.headers["X-Character-Read-Query-Count"]) > 0
    assert int(response.headers["X-Character-Read-Response-Bytes"]) == len(response.data)
    assert response.headers["Cache-Control"] == "private, no-store"


def test_real_app_disabled_boundary_emits_no_character_diagnostics(
    app,
    client,
    sign_in,
    users,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"{CHARACTER_ROUTE_PATH}?page=quick",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert not any(
        name.startswith("X-Character-Read-") for name, _value in response.headers
    )
    assert "character-" not in response.headers.get("Server-Timing", "")


def test_real_app_busy_response_is_generic_private_and_classifiable(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = True
    admission = CharacterReadAdmission(1)
    dependencies = app.extensions["character_read_route_dependencies"]
    monkeypatch.setitem(
        app.extensions,
        "character_read_route_dependencies",
        replace(dependencies, admission=admission),
    )
    assert admission.try_acquire()
    try:
        sign_in(users["dm"]["email"], users["dm"]["password"])
        response = client.get(CHARACTER_ROUTE_PATH)
    finally:
        admission.release()

    assert response.status_code == 503
    _assert_character_diagnostics(
        response,
        route_class="character-document",
        outcome="admission-503",
    )
    assert response.headers["Retry-After"] == "2"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert int(response.headers["X-Character-Read-Response-Bytes"]) == len(response.data)
    body = response.get_data(as_text=True)
    assert "Character pages are busy" in body
    assert "linden-pass" not in body
    assert "arden-march" not in body


def test_real_app_head_and_options_preserve_transport_and_diagnostics_headers(
    app,
    client,
    sign_in,
    users,
) -> None:
    app.config["LIVE_DIAGNOSTICS"] = True
    sign_in(users["dm"]["email"], users["dm"]["password"])

    head = client.head(CHARACTER_ROUTE_PATH)
    options = client.options(CHARACTER_ROUTE_PATH)

    assert head.status_code == 200
    assert head.data == b""
    _assert_character_diagnostics(head, route_class="character-document")
    assert int(head.headers["X-Character-Read-Response-Bytes"]) == int(
        head.headers["Content-Length"]
    )

    assert options.status_code == 200
    _assert_character_diagnostics(options, route_class="character-document")
    assert set(options.headers["Allow"].replace(" ", "").split(",")) == {
        "GET",
        "HEAD",
        "OPTIONS",
    }
