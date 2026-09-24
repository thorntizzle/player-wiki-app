"""Test-only presentation-date input and post-interval Character body custody.

The performance driver imports only ``fixed_loading_selection_date`` and its
constant. Application defaults, clocks, response work and polling are unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from functools import wraps
import importlib
import hashlib
import re
import time
from types import SimpleNamespace

import pytest

LOADING_SELECTION_DATE = date(2026, 9, 6)


@contextmanager
def fixed_loading_selection_date(selection_date: date = LOADING_SELECTION_DATE):
    """Supply only a default presentation date, restoring the imported reference."""
    if type(selection_date) is not date:
        raise TypeError("A date is required for the synthetic loading selection.")
    app_module = importlib.import_module("player_wiki.app")
    original = app_module.select_campaign_loading_image_urls

    @wraps(original)
    def select_with_date(*args, **kwargs):
        if kwargs.get("selection_date") is None and not kwargs.get("selection_seed"):
            kwargs = {**kwargs, "selection_date": selection_date}
        return original(*args, **kwargs)

    app_module.select_campaign_loading_image_urls = select_with_date
    try:
        yield
    finally:
        app_module.select_campaign_loading_image_urls = original


def _selector_campaign():
    return SimpleNamespace(
        slug="linden-pass",
        visible_pages=lambda: [
            SimpleNamespace(source_path="lore/trade-coast-map.md", image_path="lore/trade-coast-map.png", route_slug="trade-coast-map"),
            SimpleNamespace(source_path="npcs/captain-lyra-vale.md", image_path="npcs/captain-lyra-vale.png", route_slug="captain-lyra-vale"),
        ],
    )


@pytest.mark.parametrize("explicit", [{}, {"selection_date": date(2026, 9, 7)}, {"selection_seed": "caller-owned-seed"}, {"selection_date": date(2026, 9, 7), "selection_seed": "caller-owned-seed"}])
def test_adapter_forwards_real_selector_work_and_preserves_explicit_inputs(monkeypatch, explicit):
    app_module = importlib.import_module("player_wiki.app")
    original = app_module.select_campaign_loading_image_urls
    calls, assets, urls = [], [], []
    def observe(*args, **kwargs):
        calls.append(dict(kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(app_module, "select_campaign_loading_image_urls", observe)
    campaign = _selector_campaign()
    common = {"can_access_wiki": True,
              "image_exists": lambda campaign, path: assets.append(path) is None,
              "build_image_url": lambda campaign, path: urls.append(path) or "/assets/" + path}
    with fixed_loading_selection_date():
        result = app_module.select_campaign_loading_image_urls(campaign, **common, **explicit)
    assert app_module.select_campaign_loading_image_urls is observe
    assert len(assets) == len(urls) == len(result) == 2
    expected_date = explicit.get("selection_date") if explicit else LOADING_SELECTION_DATE
    if "selection_seed" in explicit and "selection_date" not in explicit:
        assert "selection_date" not in calls[0]
    else:
        assert calls[0]["selection_date"] == expected_date
    assert calls[0].get("selection_seed") == explicit.get("selection_seed")
    expected_keywords = {**common, **explicit}
    if not explicit:
        expected_keywords["selection_date"] = LOADING_SELECTION_DATE
    assert result == original(campaign, **expected_keywords)


def test_adapter_retains_access_refusal_and_real_clocks(monkeypatch):
    app_module = importlib.import_module("player_wiki.app")
    loading = importlib.import_module("player_wiki.loading_presenter")
    auth = importlib.import_module("player_wiki.auth_store")
    original = app_module.select_campaign_loading_image_urls
    clocks = (loading.datetime, loading._selection_day, auth.utcnow, time.perf_counter, time.monotonic, time.time)
    before = datetime.now(timezone.utc)
    def prohibited(*args):
        raise AssertionError("Denied content must not enumerate images or URLs")
    with fixed_loading_selection_date():
        assert app_module.select_campaign_loading_image_urls(_selector_campaign(), can_access_wiki=False, image_exists=prohibited, build_image_url=prohibited) == []
        assert (loading.datetime, loading._selection_day, auth.utcnow, time.perf_counter, time.monotonic, time.time) == clocks
    assert app_module.select_campaign_loading_image_urls is original
    assert datetime.now(timezone.utc) >= before


def test_adapter_restores_exact_reference_after_selector_and_context_errors():
    app_module = importlib.import_module("player_wiki.app")
    original = app_module.select_campaign_loading_image_urls
    sentinel = RuntimeError("real campaign enumeration failed")
    def fail():
        raise sentinel
    campaign = _selector_campaign()
    campaign.visible_pages = fail
    with pytest.raises(RuntimeError) as observed:
        with fixed_loading_selection_date():
            app_module.select_campaign_loading_image_urls(campaign, can_access_wiki=True, image_exists=lambda *args: True, build_image_url=lambda *args: "ignored")
    assert observed.value is sentinel
    assert app_module.select_campaign_loading_image_urls is original
    with pytest.raises(ValueError, match="context failed"):
        with fixed_loading_selection_date():
            raise ValueError("context failed")
    assert app_module.select_campaign_loading_image_urls is original
    with pytest.raises(TypeError):
        with fixed_loading_selection_date("2026-09-06"):
            pass
    assert app_module.select_campaign_loading_image_urls is original


@pytest.fixture
def loading_world(app, users):
    from player_wiki.auth_store import AuthStore
    from tests.helpers.character_state_helpers import _write_character_state
    app.config["CSRF_ENABLED"] = False
    app.config["LIVE_DIAGNOSTICS"] = True
    client = app.test_client()
    assert client.post("/sign-in", data={"email": users["dm"]["email"], "password": users["dm"]["password"]}).status_code == 302
    assert client.post("/campaigns/linden-pass/combat/player-combatants", data={"character_slug": "arden-march", "turn_value": 18}).status_code == 302
    def set_hp(value):
        def update(state):
            vitals = dict(state.get("vitals") or {})
            vitals["current_hp"] = value
            state["vitals"] = vitals
        _write_character_state(app, "arden-march", update)
    with app.app_context():
        for scope in ("characters", "combat"):
            AuthStore().upsert_campaign_visibility_setting("linden-pass", scope, visibility="players", updated_by_user_id=users["dm"]["id"])
        service = app.extensions["campaign_combat_service"]
        for index in range(6):
            service.add_npc_combatant("linden-pass", display_name=f"Paired NPC {index+1}", turn_value=12-index, current_hp=10, max_hp=10, movement_total=30, created_by_user_id=users["dm"]["id"])
        for _ in range(3):
            service.sync_player_character_snapshots("linden-pass")
        for scenario in ("unchanged", "changed"):
            for index in range(28):
                if scenario == "changed":
                    set_hp(15 + index % 2)
                sync = service.sync_player_character_snapshots("linden-pass")
                assert sync.sync_changed is (scenario == "changed")
    return app, users, set_hp


def _nonce_explanation(body):
    nonce = re.search(rb'nonce="([^"]+)"', body).group(1)
    return body.replace(nonce, b"<per-response-nonce>")


def test_actual_document_date_and_default_control_preserve_exact_work(loading_world):
    app, users, _ = loading_world
    client = app.test_client()
    assert client.post("/sign-in", data={"email": users["owner"]["email"], "password": users["owner"]["password"]}).status_code == 302
    route = "/campaigns/linden-pass/characters/arden-march?page=quick"
    with fixed_loading_selection_date():
        for _ in range(4):
            assert client.get(route).status_code == 200
        historical = client.get(route)
    with fixed_loading_selection_date(date(2026, 9, 7)):
        next_day = client.get(route)
    today = datetime.now(timezone.utc).date()
    current_default = client.get(route)
    with fixed_loading_selection_date(today):
        current_explicit = client.get(route)
    assert datetime.now(timezone.utc).date() == today, "UTC rollover invalidates same-day comparison"
    assert len(historical.data) == int(historical.headers["X-Character-Read-Response-Bytes"]) == 70359
    assert len(next_day.data) == int(next_day.headers["X-Character-Read-Response-Bytes"]) == 70363
    for response in (historical, next_day, current_default, current_explicit):
        assert response.status_code == 200
        assert int(response.headers["X-Character-Read-Query-Count"]) == 24
    assert _nonce_explanation(current_default.data) == _nonce_explanation(current_explicit.data)
    def without_loading_line(body):
        return re.sub(rb'^.*<div class="app-loading-cover[^\n]*\n', b'<loading-cover-line>\n', _nonce_explanation(body), flags=re.M)
    assert without_loading_line(historical.data) == without_loading_line(next_day.data)


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}])
def test_post_interval_first_capture_keeps_original_work_and_combat_lifecycle(loading_world, viewport, monkeypatch):
    from playwright.sync_api import Response, sync_playwright
    from scripts.measure_character_read_performance import FourWorkerWSGIServer, extract_character_diagnostics
    from tests.test_ha_measurement_ordering_browser import install_controlled_combat_sampling, controlled_combat_samples, assert_controlled_combat_ready
    app, users, set_hp = loading_world
    original_wsgi = app.wsgi_app
    character_requests = []
    def count_wsgi(environ, start_response):
        if environ.get("PATH_INFO") == "/campaigns/linden-pass/characters/arden-march":
            character_requests.append(environ.get("QUERY_STRING"))
        return original_wsgi(environ, start_response)
    app.wsgi_app = count_wsgi
    server = FourWorkerWSGIServer(app)
    server.start()
    captured, body_calls = [], []
    stage = {"value": "outside-capture", "elapsed": None, "diagnostics": None}
    real_body = Response.body
    def guarded_body(response):
        assert stage["value"] == "elapsed-and-headers-complete"
        assert isinstance(stage["elapsed"], float) and stage["elapsed"] >= 0
        assert stage["diagnostics"]["route_class"] == "character-document"
        assert response not in body_calls, "Capture never retries or reads a response twice"
        body_calls.append(response)
        return real_body(response)
    monkeypatch.setattr(Response, "body", guarded_body)
    try:
        with fixed_loading_selection_date(), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport=viewport)
            install_controlled_combat_sampling(context)
            context.add_init_script("""(() => { let online=true;
              window.addEventListener('offline',()=>{online=false;},{capture:true});
              window.addEventListener('online',()=>{online=true;},{capture:true});
              Object.defineProperty(Navigator.prototype,'onLine',{configurable:true,get:()=>online});
            })();""")
            page = context.new_page()
            page.goto(server.base_url + "/sign-in")
            page.locator("input[name=email]").fill(users["owner"]["email"])
            page.locator("input[name=password]").fill(users["owner"]["password"])
            page.locator("button[type=submit]").click()
            page.wait_for_load_state("domcontentloaded")
            for index in range(6):
                stage["value"] = "navigation"
                tick = time.perf_counter()
                response = page.goto(server.base_url + "/campaigns/linden-pass/characters/arden-march?page=quick", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("[data-character-read-shell-root]").first.wait_for(state="visible")
                elapsed = (time.perf_counter() - tick) * 1000
                diagnostics = extract_character_diagnostics(response.all_headers())
                stage.update(value="elapsed-and-headers-complete", elapsed=elapsed, diagnostics=diagnostics)
                capture_started = time.perf_counter()
                body = response.body()
                capture_ms = (time.perf_counter() - capture_started) * 1000
                assert elapsed == stage["elapsed"]
                assert len(character_requests) == index + 1
                assert len(body_calls) == index + 1
                assert type(body) is bytes and len(body) == diagnostics["response_bytes"]
                if index >= 4:
                    assert len(body) == 70359 and diagnostics["query_count"] == 24
                captured.append((body, diagnostics, capture_ms))
                stage["value"] = "outside-capture"
            assert len(captured) == len(body_calls) == len(character_requests) == 6
            page.goto(server.base_url + "/campaigns/linden-pass/combat", wait_until="domcontentloaded")
            page.locator("[data-combat-live-root]").first.wait_for(state="visible")
            with controlled_combat_samples(page):
                for _ in range(3):
                    assert page.evaluate("() => window.__playerWikiLiveDiagnostics.combat.sample({mode:'steady',forceApply:false})") is not None
                for scenario in ("unchanged", "changed"):
                    for index in range(28):
                        if scenario == "changed":
                            set_hp(15 + index % 2)
                        metrics = page.evaluate("() => window.__playerWikiLiveDiagnostics.combat.sample({mode:'steady',forceApply:false})")
                        assert metrics is not None and metrics["changed"] is (scenario == "changed")
                assert_controlled_combat_ready(page)
                assert_controlled_combat_ready(page)
            assert page.evaluate("() => window.__haMeasurementControl.snapshot().controlled") is False
            context.close()
            browser.close()
    finally:
        server.stop()
        app.wsgi_app = original_wsgi
    assert len(character_requests) == len(body_calls) == 6
    for body, diagnostics, capture_ms in captured:
        assert len(body) == diagnostics["response_bytes"]
        assert len(hashlib.sha256(body).hexdigest()) == 64
        assert b'data-character-read-shell-root' in body
        assert b'data-app-loading-media-url="/campaigns/linden-pass/assets/lore/trade-coast-map.png"' in body
        assert capture_ms >= 0
