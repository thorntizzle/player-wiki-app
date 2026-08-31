from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_combat_preset_service import (
    CampaignCombatPresetAuthorizationError,
)
from player_wiki.campaign_combat_preset_store import CampaignCombatPresetStore
from player_wiki.db import (
    get_db_query_metrics,
    reset_db_query_metrics,
)
from player_wiki.manager_tools_routes import MANAGER_TOOLS_HTML_MAX_BYTES


MANAGER_TOOLS_URL = "/campaigns/linden-pass/manager-tools"


def _sign_in(sign_in, users, actor: str) -> None:
    response = sign_in(users[actor]["email"], users[actor]["password"])
    assert response.status_code == 302


def _card_titles(body: str) -> list[str]:
    return [
        title
        for title in (
            "Character Updates",
            "Session Readiness",
            "Session Closeouts",
            "Encounter Presets",
            "Source Health",
        )
        if title in body
    ]


@pytest.fixture
def manager_tools_live_server(app):
    from werkzeug.serving import make_server

    app.config["APP_ENV"] = "production"
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _browser_session_state(browser, base_url: str, theme: str):
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{base_url}/sign-in", wait_until="load")
    page.get_by_label("Email").fill("dm@example.com")
    page.get_by_label("Password").fill("dm-pass")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_load_state("load")
    page.goto(f"{base_url}/account", wait_until="load")
    status = page.evaluate(
        """async (themeKey) => {
          const body = new URLSearchParams();
          body.set("theme_key", themeKey);
          const response = await fetch("/account/theme", {
            method: "POST",
            body,
            credentials: "same-origin",
          });
          return response.status;
        }""",
        theme,
    )
    assert status == 200
    state = context.storage_state()
    context.close()
    return state


def test_manager_tools_authorizes_before_cards_and_view_as_discloses_none(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    service = app.extensions["campaign_combat_preset_service"]
    calls: list[tuple[str, int]] = []

    def count_presets(campaign_slug: str, *, limit: int) -> int:
        calls.append((campaign_slug, limit))
        return 0

    monkeypatch.setattr(service, "count_presets_up_to", count_presets)

    signed_out = client.get(MANAGER_TOOLS_URL)
    assert signed_out.status_code == 302
    assert signed_out.headers["Cache-Control"] == "private, no-store"
    assert signed_out.headers["Referrer-Policy"] == "no-referrer"
    assert calls == []

    for actor in ("owner", "observer", "outsider"):
        _sign_in(sign_in, users, actor)
        denied = client.get(MANAGER_TOOLS_URL)
        assert denied.status_code == 403
        assert denied.headers["Cache-Control"] == "private, no-store"
        assert denied.headers["Referrer-Policy"] == "no-referrer"
        assert _card_titles(denied.get_data(as_text=True)) == []
        assert calls == []

    for effective_actor in ("owner", "observer"):
        _sign_in(sign_in, users, "admin")
        with client.session_transaction() as session:
            session[VIEW_AS_SESSION_KEY] = users[effective_actor]["id"]
        denied_view_as = client.get(MANAGER_TOOLS_URL)
        assert denied_view_as.status_code == 403
        assert denied_view_as.headers["Cache-Control"] == "private, no-store"
        assert denied_view_as.headers["Referrer-Policy"] == "no-referrer"
        assert _card_titles(denied_view_as.get_data(as_text=True)) == []
        assert calls == []

    _sign_in(sign_in, users, "admin")
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["dm"]["id"]
    allowed_view_as_dm = client.get(MANAGER_TOOLS_URL)
    assert allowed_view_as_dm.status_code == 200
    assert calls == [("linden-pass", 26)]

    _sign_in(sign_in, users, "dm")
    allowed = client.get(MANAGER_TOOLS_URL)
    assert allowed.status_code == 200
    assert calls == [("linden-pass", 26), ("linden-pass", 26)]


@pytest.mark.parametrize(
    ("blocked_scope", "hidden_card"),
    (
        ("characters", "character-updates"),
        ("session", "character-updates"),
        ("combat", "encounter-presets"),
    ),
)
def test_manager_tools_cards_enforce_each_owner_scope_gate(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    blocked_scope,
    hidden_card,
) -> None:
    set_campaign_visibility("linden-pass", **{blocked_scope: "private"})
    _sign_in(sign_in, users, "dm")

    response = client.get(MANAGER_TOOLS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'data-manager-tool-card="{hidden_card}"' not in body
    assert 'data-manager-tool-card="source-health"' in body


def test_manager_tools_hides_session_readiness_when_session_management_is_denied(
    client,
    sign_in,
    users,
    set_campaign_visibility,
) -> None:
    set_campaign_visibility("linden-pass", session="private")
    _sign_in(sign_in, users, "dm")

    response = client.get(MANAGER_TOOLS_URL)

    assert response.status_code == 200
    assert 'data-manager-tool-card="session-readiness"' not in response.get_data(
        as_text=True
    )


def test_manager_tools_renders_exact_five_cards_in_order_with_native_links(
    client,
    sign_in,
    users,
) -> None:
    _sign_in(sign_in, users, "dm")

    response = client.get(MANAGER_TOOLS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert len(response.data) <= MANAGER_TOOLS_HTML_MAX_BYTES
    assert body.count('data-manager-tool-card="') == 5
    positions = [body.index(title) for title in _card_titles(body)]
    assert positions == sorted(positions)
    assert "Available for D&amp;D 5E characters." in body
    assert "No saved encounters" in body
    assert ">Available</strong>" in body
    assert 'href="/campaigns/linden-pass/characters"' in body
    assert 'href="/campaigns/linden-pass/manager-tools/session-readiness"' in body
    assert 'href="/campaigns/linden-pass/manager-tools/session-closeouts"' in body
    assert 'href="/campaigns/linden-pass/combat/dm?view=controls#saved-encounters"' in body
    assert 'href="/campaigns/linden-pass/source-health"' in body
    assert all(
        label in body
        for label in (
            "Choose a Character",
            "Review Session Readiness",
            "Open Session Closeouts",
            "Open Encounter Presets",
            "Open Source Health",
        )
    )
    assert body.count('aria-current="page"') == 1
    assert 'href="/campaigns/linden-pass/manager-tools"' in body
    assert "Source Health" not in body.split(
        '<nav class="campaign-nav" aria-label="Campaign navigation">', 1
    )[1].split("</nav>", 1)[0]
    main = body.split("<main", 1)[1].split("</main>", 1)[0]
    assert "<script" not in main
    assert "Character scan" not in body
    assert "Source Health report" not in body


def test_manager_tools_empty_state_is_static_and_accessibly_labelled() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "player_wiki"
        / "templates"
        / "manager_tools.html"
    ).read_text(encoding="utf-8")

    assert 'state-panel state-panel--empty' in template
    assert 'aria-labelledby="manager-tools-empty-title"' in template
    assert 'id="manager-tools-empty-title"' in template
    assert "No manager tools are currently available for this campaign." in template
    assert "aria-live" not in template


@pytest.mark.parametrize(
    ("created_count", "expected"),
    (
        (0, "No saved encounters"),
        (1, "1 saved encounter"),
        (2, "2 saved encounters"),
        (25, "25 saved encounters"),
        (26, "25+ saved encounters"),
        (30, "25+ saved encounters"),
    ),
)
def test_manager_tools_preset_count_states_are_bounded(
    app,
    client,
    sign_in,
    users,
    created_count,
    expected,
) -> None:
    with app.app_context():
        store = CampaignCombatPresetStore()
        for index in range(created_count):
            store.create_preset(
                "linden-pass",
                name=f"Private preset {index:02d}",
                entries=(),
            )

    _sign_in(sign_in, users, "dm")
    response = client.get(MANAGER_TOOLS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert expected in body
    assert "Private preset" not in body


def test_manager_tools_preset_authorization_denial_hides_card_and_fault_is_sanitized(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    service = app.extensions["campaign_combat_preset_service"]
    _sign_in(sign_in, users, "dm")

    monkeypatch.setattr(
        service,
        "count_presets_up_to",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CampaignCombatPresetAuthorizationError("private authorization detail")
        ),
    )
    denied = client.get(MANAGER_TOOLS_URL)
    denied_body = denied.get_data(as_text=True)
    assert denied.status_code == 200
    assert 'data-manager-tool-card="encounter-presets"' not in denied_body
    assert "private authorization detail" not in denied_body

    monkeypatch.setattr(
        service,
        "count_presets_up_to",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("private sqlite detail")
        ),
    )
    fault = client.get(MANAGER_TOOLS_URL)
    fault_body = fault.get_data(as_text=True)
    assert fault.status_code == 200
    assert 'data-manager-tool-card="encounter-presets"' in fault_body
    assert "Count unavailable" in fault_body
    assert "private sqlite detail" not in fault_body


def test_manager_tools_capability_gates_do_not_scan_characters_or_build_source_health(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign(
            "linden-pass"
        )
    assert campaign is not None
    original_system = campaign.system
    source_health_service = app.extensions["source_health_service"]
    monkeypatch.setattr(
        source_health_service,
        "build_report",
        lambda *_args, **_kwargs: pytest.fail("manager landing built Source Health"),
    )
    character_repository = app.extensions["character_repository"]
    monkeypatch.setattr(
        character_repository,
        "list_characters",
        lambda *_args, **_kwargs: pytest.fail("manager landing scanned Characters"),
    )
    monkeypatch.setattr(
        character_repository,
        "summarize_session_readiness_characters",
        lambda *_args, **_kwargs: pytest.fail(
            "manager landing aggregated Session readiness Characters"
        ),
    )
    session_service = app.extensions["campaign_session_service"]
    monkeypatch.setattr(
        session_service,
        "get_readiness_summary",
        lambda *_args, **_kwargs: pytest.fail(
            "manager landing aggregated Session readiness"
        ),
    )
    campaign.system = "Xianxia"
    try:
        _sign_in(sign_in, users, "dm")
        response = client.get(MANAGER_TOOLS_URL)
        body = response.get_data(as_text=True)
    finally:
        campaign.system = original_system
    assert response.status_code == 200
    assert 'data-manager-tool-card="character-updates"' not in body
    assert 'data-manager-tool-card="encounter-presets"' not in body
    assert 'data-manager-tool-card="source-health"' in body


def test_manager_tools_uses_bounded_queries_and_zero_writes(
    client,
    sign_in,
    users,
) -> None:
    _sign_in(sign_in, users, "dm")
    reset_db_query_metrics()

    response = client.get(MANAGER_TOOLS_URL)
    metrics = get_db_query_metrics()

    assert response.status_code == 200
    assert int(metrics["query_count"]) <= 12
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0


def test_real_browser_manager_tools_responsive_theme_keyboard_links_and_no_js(
    manager_tools_live_server,
) -> None:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    scenarios = (
        ({"width": 1280, "height": 900}, True, "parchment"),
        ({"width": 390, "height": 800}, False, "moonlit"),
        ({"width": 821, "height": 900}, True, "moonlit"),
        ({"width": 820, "height": 900}, False, "parchment"),
    )
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            for viewport, java_script_enabled, theme in scenarios:
                state = _browser_session_state(
                    browser,
                    manager_tools_live_server,
                    theme,
                )
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                    storage_state=state,
                )
                page = context.new_page()
                try:
                    response = page.goto(
                        f"{manager_tools_live_server}{MANAGER_TOOLS_URL}",
                        wait_until="load",
                    )
                    assert response is not None and response.status == 200
                    expect(page.locator("html")).to_have_attribute(
                        "data-theme",
                        theme,
                    )
                    expect(page.get_by_role("heading", name="Manager Tools", exact=True)).to_be_visible()
                    cards = page.locator("[data-manager-tool-card]")
                    expect(cards).to_have_count(5)
                    assert cards.locator("h2").all_inner_texts() == [
                        "Character Updates",
                        "Session Readiness",
                        "Session Closeouts",
                        "Encounter Presets",
                        "Source Health",
                    ]
                    nav = page.get_by_role("navigation", name="Campaign navigation")
                    current = nav.locator('[aria-current="page"]')
                    expect(current).to_have_count(1)
                    expect(current).to_have_text("Manager Tools")
                    expect(current).to_have_class(re.compile(r"\bis-active\b"))
                    assert [
                        cards.get_by_role("link", name=label).get_attribute("href")
                        for label in (
                            "Choose a Character",
                            "Review Session Readiness",
                            "Open Session Closeouts",
                            "Open Encounter Presets",
                            "Open Source Health",
                        )
                    ] == [
                        "/campaigns/linden-pass/characters",
                        "/campaigns/linden-pass/manager-tools/session-readiness",
                        "/campaigns/linden-pass/manager-tools/session-closeouts",
                        "/campaigns/linden-pass/combat/dm?view=controls#saved-encounters",
                        "/campaigns/linden-pass/source-health",
                    ]
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    )
                    for card in cards.all():
                        box = card.bounding_box()
                        assert box is not None
                        assert box["x"] >= 0
                        assert box["x"] + box["width"] <= viewport["width"] + 1

                    page.keyboard.press("Tab")
                    skip_link = page.locator(".skip-link")
                    expect(skip_link).to_be_focused()
                    page.keyboard.press("Enter")
                    expect(page.locator("#main-content")).to_be_focused()
                    assert page.locator("main script").count() == 0
                finally:
                    context.close()
        finally:
            browser.close()
