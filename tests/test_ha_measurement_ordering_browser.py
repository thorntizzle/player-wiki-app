"""Test-only control for a sequential steady Combat measurement.

The same file is supplied externally to baseline and candidate measurements.
It never changes the application sampler, fetch, renderer, metrics, or clock.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import threading

import pytest


POLL_CALLBACK_SOURCE = "() => {\n        pollTimerId = 0;\n        refreshLiveState();\n      }"
CONTROL_SCRIPT = r"""(() => {
  if (!location.pathname.endsWith('/combat')) return;
  const expectedCallback = __EXPECTED_CALLBACK__;
  const nativeSetTimeout = window.setTimeout.bind(window);
  const nativeClearTimeout = window.clearTimeout.bind(window);
  const timers = new Map();
  let sequence = 0;
  let controlled = true;
  let policy = null;
  let tools;
  let captured = 0;
  let fired = 0;
  let cancelledRestored = 0;
  let lastFiredAt = null;

  const fire = (entry) => {
    timers.delete(entry.id);
    fired += 1;
    lastFiredAt = performance.now();
    entry.callback(...entry.args);
  };
  window.setTimeout = (callback, delay, ...args) => {
    if (controlled && typeof callback === 'function'
        && callback.toString().replace(/\r\n/g, '\n') === expectedCallback) {
      const id = --sequence;
      timers.set(id, {id, callback, args, dueAt: performance.now() + Number(delay), nativeId: null});
      captured += 1;
      return id;
    }
    return nativeSetTimeout(callback, delay, ...args);
  };
  window.clearTimeout = (id) => {
    const entry = timers.get(id);
    if (!entry) return nativeClearTimeout(id);
    timers.delete(id);
    if (entry.nativeId !== null) {
      nativeClearTimeout(entry.nativeId);
      cancelledRestored += 1;
    }
  };
  Object.defineProperty(window, '__playerWikiLiveUiTools', {
    configurable: true,
    get: () => tools,
    set: (value) => {
      tools = value;
      const originalCreate = value.createAsyncPolicy;
      value.createAsyncPolicy = (...args) => {
        const actual = originalCreate(...args);
        if (args[0]?.matches('[data-combat-live-root]')) policy = actual;
        return actual;
      };
    },
  });
  const snapshot = () => ({
    controlled,
    policy: policy ? policy.snapshot() : null,
    pending: [...timers.values()].map(({id, dueAt, nativeId}) => ({id, dueAt, restored: nativeId !== null})),
    captured, fired, cancelledRestored, lastFiredAt,
  });
  const assertReady = () => {
    const state = snapshot();
    if (!controlled || !state.policy || state.policy.readInFlight
        || state.pending.length !== 1 || state.pending[0].restored) {
      throw new Error(`Controlled Combat sampling is not ready: ${JSON.stringify(state)}`);
    }
    return state;
  };
  window.__haMeasurementControl = {
    snapshot,
    assertReady,
    restore: () => {
      controlled = false;
      const restored = [];
      for (const entry of timers.values()) {
        if (entry.nativeId !== null) continue;
        const scheduledAt = performance.now();
        const remainingMs = Math.max(0, entry.dueAt - scheduledAt);
        entry.nativeId = nativeSetTimeout(() => fire(entry), remainingMs);
        restored.push({id: entry.id, dueAt: entry.dueAt, scheduledAt, remainingMs});
      }
      return restored;
    },
    runPendingPollForTest: () => {
      assertReady();
      fire(timers.values().next().value);
    },
  };
})();""".replace("__EXPECTED_CALLBACK__", json.dumps(POLL_CALLBACK_SOURCE))


def bind_combat_sampling_source(source_root: Path) -> dict[str, str]:
    path = source_root / "player_wiki/static/combat-live.js"
    data = path.read_bytes()
    assert data.decode("utf-8").replace("\r\n", "\n").count(POLL_CALLBACK_SOURCE) == 1
    return {
        "combat_live_sha256": hashlib.sha256(data).hexdigest(),
        "poll_callback_sha256": hashlib.sha256(POLL_CALLBACK_SOURCE.encode()).hexdigest(),
    }


def install_controlled_combat_sampling(context) -> None:
    context.add_init_script(CONTROL_SCRIPT)


def assert_controlled_combat_ready(page) -> None:
    page.evaluate("() => window.__haMeasurementControl.assertReady()")


@contextmanager
def controlled_combat_samples(page):
    """Drain the actual read policy outside samples; restore on every exit."""
    try:
        page.wait_for_function(
            "() => window.__haMeasurementControl?.snapshot().policy !== null "
            "&& window.__haMeasurementControl?.snapshot().policy?.readInFlight === false",
            timeout=5000,
        )
        assert_controlled_combat_ready(page)
        yield
    finally:
        if not page.is_closed():
            page.evaluate("() => window.__haMeasurementControl?.restore()")


@pytest.fixture
def ordering_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright browser unavailable: package missing")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {type(exc).__name__}")
        try:
            yield browser
        finally:
            browser.close()


def _durable(app):
    from player_wiki.db import get_db
    with app.app_context():
        db = get_db()
        source = db.execute(
            "SELECT revision, state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",
            ("linden-pass", "arden-march"),
        ).fetchone()
        pc = db.execute(
            "SELECT revision, current_hp FROM campaign_combatants WHERE campaign_slug=? AND character_slug=?",
            ("linden-pass", "arden-march"),
        ).fetchone()
        tracker = db.execute(
            "SELECT revision FROM campaign_combat_trackers WHERE campaign_slug=?", ("linden-pass",),
        ).fetchone()
        return source["revision"], json.loads(source["state_json"])["vitals"]["current_hp"], pc["revision"], pc["current_hp"], tracker["revision"]


def _set_hp(app, value):
    from tests.helpers.character_state_helpers import _write_character_state
    def update(state):
        state["vitals"]["current_hp"] = value
    _write_character_state(app, "arden-march", update)


@pytest.fixture
def ordering_world(app, users):
    from flask import request
    from player_wiki.auth_store import AuthStore
    from scripts.measure_character_read_performance import FourWorkerWSGIServer
    app.config["CSRF_ENABLED"] = False
    app.config["LIVE_DIAGNOSTICS"] = True
    entered, release = threading.Event(), threading.Event()
    control = {"hold": False, "requests": [], "responses": []}

    @app.before_request
    def hold_real_request():
        if request.path.endswith("/combat/live-state"):
            control["requests"].append(request.headers.get("X-Live-Revision"))
            if control["hold"]:
                control["hold"] = False
                entered.set()
                assert release.wait(timeout=5)

    @app.after_request
    def observe_real_response(response):
        if request.path.endswith("/combat/live-state"):
            payload = response.get_json()
            control["responses"].append((payload["changed"], payload["live_revision"]))
        return response

    client = app.test_client()
    assert client.post("/sign-in", data={"email": users["dm"]["email"], "password": users["dm"]["password"]}).status_code == 302
    assert client.post("/campaigns/linden-pass/combat/player-combatants", data={"character_slug": "arden-march", "turn_value": 18}).status_code == 302
    with app.app_context():
        for scope in ("characters", "combat"):
            AuthStore().upsert_campaign_visibility_setting("linden-pass", scope, visibility="players", updated_by_user_id=users["dm"]["id"])
        service = app.extensions["campaign_combat_service"]
        for index in range(6):
            service.add_npc_combatant("linden-pass", display_name=f"Paired NPC {index+1}", turn_value=12-index, current_hp=10, max_hp=10, movement_total=30, created_by_user_id=users["dm"]["id"])
    _set_hp(app, 15)
    with app.app_context():
        for _ in range(3):
            service.sync_player_character_snapshots("linden-pass")
    server = FourWorkerWSGIServer(app)
    server.start()
    try:
        yield app, users, server.base_url, control, entered, release
    finally:
        release.set()
        server.stop()


def _open_controlled_page(browser, world, viewport):
    _, users, base_url, _, _, _ = world
    bind_combat_sampling_source(Path(__file__).resolve().parents[1])
    context = browser.new_context(viewport=viewport)
    install_controlled_combat_sampling(context)
    context.add_init_script("""(() => {
      let online=true;
      window.addEventListener('offline',()=>{online=false;},{capture:true});
      window.addEventListener('online',()=>{online=true;},{capture:true});
      Object.defineProperty(Navigator.prototype,'onLine',{configurable:true,get:()=>online});
    })();""")
    page = context.new_page()
    page.goto(base_url + "/sign-in")
    page.locator("input[name=email]").fill(users["owner"]["email"])
    page.locator("input[name=password]").fill(users["owner"]["password"])
    page.locator("button[type=submit]").click()
    page.wait_for_load_state("domcontentloaded")
    response = page.goto(base_url + "/campaigns/linden-pass/combat", wait_until="domcontentloaded")
    assert response.status == 200
    page.locator("[data-combat-live-root]").first.wait_for(state="visible")
    page.wait_for_function("() => typeof window.__playerWikiLiveDiagnostics?.combat?.sample === 'function'")
    return context, page


def _sample(page):
    return page.evaluate("() => window.__playerWikiLiveDiagnostics.combat.sample({mode:'steady',forceApply:false})")


@pytest.mark.parametrize("viewport", ({"width":1280,"height":900}, {"width":390,"height":800}), ids=("desktop", "mobile"))
@pytest.mark.parametrize("ordering", ("A", "B", "C"))
def test_controlled_measurement_ordering_uses_real_source_and_read_policy(ordering_world, ordering_browser, viewport, ordering):
    app, _, _, control, entered, release = ordering_world
    context, page = _open_controlled_page(ordering_browser, ordering_world, viewport)
    try:
        with controlled_combat_samples(page):
            for _ in range(3):
                assert _sample(page) is not None
            before = _durable(app)
            first_request = len(control["requests"])
            if ordering == "C":
                control["hold"] = True
                page.evaluate("() => window.__haMeasurementControl.runPendingPollForTest()")
                assert entered.wait(timeout=5)
            _set_hp(app, 16)
            committed = _durable(app)
            assert committed[1] == 16 and committed[3] == 15
            if ordering == "B":
                page.evaluate("() => window.__haMeasurementControl.runPendingPollForTest()")
            if ordering == "C":
                assert _sample(page) is None
                assert len(control["requests"]) == first_request + 1
                release.set()
            page.wait_for_function("() => !window.__haMeasurementControl.snapshot().policy.readInFlight")
            metric = _sample(page)
            assert metric is not None and metric["changed"] is (ordering == "A")
            after = _durable(app)
            assert after[0] == committed[0]
            assert after[1] == after[3] == 16
            assert after[4] == before[4] + 1
            assert int(page.locator("[data-combat-live-root]").first.get_attribute("data-live-revision")) == after[4]
            observed = control["responses"][first_request:]
            assert observed == ([(True, after[4])] if ordering == "A" else [(True, after[4]), (False, after[4])])
        assert page.evaluate("() => window.__haMeasurementControl.snapshot().controlled") is False
    finally:
        release.set()
        context.close()


@pytest.mark.parametrize("viewport", ({"width":1280,"height":900}, {"width":390,"height":800}), ids=("desktop", "mobile"))
@pytest.mark.parametrize("cancel", (False, True), ids=("ordinary-resumes", "restored-cancellation"))
def test_restored_poll_keeps_original_due_time_and_native_cancellation(ordering_world, ordering_browser, viewport, cancel):
    app, _, _, control, _, _ = ordering_world
    context, page = _open_controlled_page(ordering_browser, ordering_world, viewport)
    try:
        with controlled_combat_samples(page):
            for _ in range(3):
                assert _sample(page) is not None
            _set_hp(app, 16)
            before = len(control["requests"])
            pending = page.evaluate("() => window.__haMeasurementControl.assertReady().pending[0]")
            restored = page.evaluate("""cancel => {
                const restored = window.__haMeasurementControl.restore();
                if (cancel) window.dispatchEvent(new Event('offline'));
                return restored;
            }""", cancel)
            assert len(restored) == 1 and restored[0]["dueAt"] == pending["dueAt"]
            assert restored[0]["remainingMs"] == max(0, restored[0]["dueAt"] - restored[0]["scheduledAt"])
            if cancel:
                state = page.evaluate("() => window.__haMeasurementControl.snapshot()")
                assert state["cancelledRestored"] == 1 and state["pending"] == []
                # Cross this specific real timer deadline, rather than use an arbitrary delay.
                page.wait_for_function("due => performance.now() > due", arg=pending["dueAt"] + 1, timeout=5000)
                assert page.evaluate("() => window.__haMeasurementControl.snapshot().fired") == 0
                assert len(control["requests"]) == before
                assert _durable(app)[3] == 15
            else:
                page.wait_for_function("() => window.__haMeasurementControl.snapshot().fired === 1", timeout=5000)
                page.wait_for_function("() => !window.__haMeasurementControl.snapshot().policy.readInFlight", timeout=5000)
                assert len(control["requests"]) == before + 1
                assert control["responses"][-1][0] is True
                assert _durable(app)[1] == _durable(app)[3] == 16
                assert page.evaluate("() => window.__haMeasurementControl.snapshot().lastFiredAt") >= pending["dueAt"] - 1
    finally:
        context.close()
