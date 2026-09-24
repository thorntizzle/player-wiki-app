from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
import json

from flask import abort, g, session
import pytest

import player_wiki.app as app_module
from tests.test_combat_context_consolidation import (
    ASYNC, CAMPAIGN, FIRST, LIVE, _poll_headers, _write_campaign_config,
    context_world,
)


def _loading_spy(app, monkeypatch):
    inject = next(fn for fn in app.template_context_processors[None]
                  if fn.__name__ == "inject_helpers")
    cell = dict(zip(inject.__code__.co_freevars, inject.__closure__))[
        "_build_campaign_loading_media_urls"
    ]
    original = cell.cell_contents
    calls = []

    def select(slug):
        result = original(slug)
        calls.append((slug, result))
        return result

    monkeypatch.setattr(cell, "cell_contents", select)
    return inject, calls


@pytest.mark.parametrize("mode,original_calls", (
    ("changed", 5), ("same-detail", 3), ("unchanged", 0), ("fallback", 3),
))
def test_live_bytes_and_loading_selection_calls(
    app, client, monkeypatch, context_world, record_property, mode, original_calls,
):
    baseline = context_world[-1]
    if mode == "fallback":
        _write_campaign_config(
            app, lambda config: config.update(system="xianxia", systems_library="xianxia"),
        )
    headers = (_poll_headers(baseline, detail_only=mode == "same-detail")
               if mode in {"same-detail", "unchanged"} else ASYNC)
    _inject, calls = _loading_spy(app, monkeypatch)
    with monkeypatch.context() as legacy:
        legacy.setattr(app_module, "_combat_live_fragment_scope", nullcontext)
        reference = client.get(LIVE, headers=headers)
    assert len(calls) == original_calls
    calls.clear()
    response = client.get(LIVE, headers=headers)
    assert response.status_code == reference.status_code == 200
    assert response.data == reference.data
    assert calls == []
    payload = response.get_json()
    assert payload["changed"] is (mode != "unchanged")
    if mode == "same-detail":
        assert "tracker_html" not in payload and "context_html" not in payload
    elif mode == "fallback":
        assert "data-combat-section-panel=" not in payload["tracker_html"]
    record_property("response_parity", json.dumps({
        "bytes": len(response.data), "sha256": sha256(response.data).hexdigest(),
        "original_selector_calls": original_calls, "scoped_selector_calls": 0,
    }))


@pytest.mark.parametrize("route", (
    f"/campaigns/{CAMPAIGN}/combat",
    f"/campaigns/{CAMPAIGN}/characters/{FIRST}?page=quick",
))
def test_full_documents_keep_loading_media(
    app, client, monkeypatch, context_world, set_campaign_visibility, route,
):
    set_campaign_visibility(CAMPAIGN, characters="players")
    _inject, calls = _loading_spy(app, monkeypatch)
    response = client.get(route)
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == CAMPAIGN and calls[0][1]
    assert b"data-app-loading-media-urls=" in response.data
    assert calls[0][1][0].encode() in response.data


@pytest.mark.parametrize("prior", (None, False, True))
def test_nested_and_exception_scope_restore_all_context_helpers(app, monkeypatch, prior):
    inject, calls = _loading_spy(app, monkeypatch)
    with app.test_request_context(f"/campaigns/{CAMPAIGN}/combat"):
        if prior is not None:
            g._combat_live_fragment_rendering = prior
        initial = dict(g.__dict__)
        # Compare every other helper, including metadata and asset builders.
        normal = inject()
        calls.clear()
        with app_module._combat_live_fragment_scope():
            with pytest.raises(RuntimeError, match="nested fragment"):
                with app_module._combat_live_fragment_scope():
                    scoped = inject()
                    assert scoped["app_loading_media_urls"] == []
                    assert scoped["app_loading_image_url"] is None
                    assert {k: v for k, v in scoped.items() if not k.startswith("app_loading_")} == {
                        k: v for k, v in normal.items() if not k.startswith("app_loading_")
                    }
                    raise RuntimeError("nested fragment")
            assert g._combat_live_fragment_rendering is True
            assert calls == []
        assert ("_combat_live_fragment_rendering" in g) is (prior is not None)
        if prior is not None:
            assert g._combat_live_fragment_rendering is prior
        # The scope itself must not leave any other request-local state.
        assert {k: v for k, v in g.__dict__.items() if k == "_combat_live_fragment_rendering"} == {
            k: v for k, v in initial.items() if k == "_combat_live_fragment_rendering"
        }


def test_fragment_exception_restores_loading_for_same_endpoint_error_document(
    app, client, monkeypatch, context_world,
):
    _inject, calls = _loading_spy(app, monkeypatch)
    original = app_module.render_template

    def render(template, **context):
        if template == "_combat_summary_card.html":
            assert g._combat_live_fragment_rendering is True
            abort(404)
        assert template == "not_found.html"
        assert "_combat_live_fragment_rendering" not in g
        return original(template, **context)

    monkeypatch.setattr(app_module, "render_template", render)
    response = client.get(LIVE, headers=ASYNC)
    assert response.status_code == 404
    assert len(calls) == 1 and calls[0][0] == CAMPAIGN and calls[0][1]
    assert b"data-app-loading-media-urls=" in response.data


@pytest.mark.parametrize("actor,view", (("owner", "combat"), ("dm", "combat"), ("dm", "dm")))
def test_mutation_fragments_match_unsuppressed_render_and_persist_once(
    app, client, sign_in, users, monkeypatch, context_world, get_character, actor, view,
):
    sign_in(users[actor]["email"], users[actor]["password"])
    first = context_world[1]
    original = app_module.render_template
    checked = []

    def render(template, **context):
        flashes = session.get("_flashes")
        result = original(template, **context)
        if getattr(g, "_combat_live_fragment_rendering", False):
            g._combat_live_fragment_rendering = False
            if flashes is not None:
                session["_flashes"] = flashes
            try:
                assert result == original(template, **context)
            finally:
                g._combat_live_fragment_rendering = True
            checked.append(template)
        else:
            assert view == "dm"
            checked.append(template)
        return result

    monkeypatch.setattr(app_module, "render_template", render)
    before = get_character(FIRST)
    response = client.post(
        f"/campaigns/{CAMPAIGN}/combat/character/combatants/{first.id}/resources/sorcery-points",
        data={"expected_revision": before.state_record.revision, "current": 3,
              "combat_view": view, "view": "status", "combatant": first.id},
        headers=ASYNC,
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert "_flash_stack.html" in checked
    after = get_character(FIRST)
    assert after.state_record.revision == before.state_record.revision + 1
    assert next(row for row in after.state_record.state["resources"]
                if row["id"] == "sorcery-points")["current"] == 3
