from __future__ import annotations

import re
import threading
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from player_wiki.campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
)


@pytest.fixture
def systems_source_category_live_server(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _browser_entry(
    source_id: str,
    entry_type: str,
    slug: str,
    title: str,
    *,
    metadata: dict[str, object] | None = None,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "entry_key": f"dnd-5e|{entry_type}|{source_id.lower()}|{slug}",
        "entry_type": entry_type,
        "slug": slug,
        "title": title,
        "source_path": rf"C:\private\imports\{source_id.lower()}-browser.json",
        "search_text": f"{title} browser-private-search-marker",
        "player_safe_default": True,
        "metadata": {
            "support_state": "browser-private-support",
            "import_run_id": "browser-private-import",
            "storage_state": "browser-private-storage",
            "provenance": "browser-private-provenance",
            **dict(metadata or {}),
        },
        "body": dict(body or {}),
        "rendered_html": f"<p>{title} reference text.</p>",
    }


def _seed_systems_source_category_browser_matrix(app) -> None:
    player_source = "P74B-BROWSER-PLAYER"
    empty_source = "P74B-BROWSER-EMPTY"
    private_source = "P74B-BROWSER-PRIVATE"
    disabled_source = "P74B-BROWSER-DISABLED"
    source_rows = (
        (player_source, "Player Navigator", True, VISIBILITY_PLAYERS),
        (empty_source, "Quiet Navigator", True, VISIBILITY_PLAYERS),
        (private_source, "Curator Navigator", True, VISIBILITY_PRIVATE),
        (disabled_source, "Dormant Navigator", False, VISIBILITY_PLAYERS),
    )
    entries: dict[str, list[dict[str, object]]] = {
        player_source: [
            _browser_entry(
                player_source,
                "book",
                "browser-opening-chapter",
                "Opening Chapter",
                metadata={
                    "headers": ["First Bearings"],
                    "section_label": "Chapter 1",
                    "target_order": 1,
                },
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-amber-compass",
                "Amber Compass",
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-long-compass",
                "A Very Long Yet Friendly Compass Reference Link That Must Wrap Within Every Card",
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-body-whisper",
                "Quiet Compass",
                body={"summary": "browser-body-only-needle"},
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-dm-compass",
                "DM Compass",
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-private-compass",
                "Private Compass",
            ),
            _browser_entry(
                player_source,
                "spell",
                "browser-disabled-compass",
                "Disabled Compass",
            ),
            _browser_entry(
                player_source,
                "rule",
                "browser-measured-course",
                "Measured Course",
                metadata={
                    "aliases": ["Careful Bearing"],
                    "formula": "12 focus",
                    "rule_facets": ["navigation"],
                },
            ),
        ],
        empty_source: [],
        private_source: [
            _browser_entry(
                private_source,
                "spell",
                "browser-private-source-compass",
                "Private Source Compass",
            )
        ],
        disabled_source: [
            _browser_entry(
                disabled_source,
                "spell",
                "browser-disabled-source-compass",
                "Disabled Source Compass",
            )
        ],
    }

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        for source_id, title, enabled, visibility in source_rows:
            store.upsert_source(
                library_slug,
                source_id,
                title=title,
                license_class="open_license",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=source_id,
                is_enabled=enabled,
                default_visibility=visibility,
            )
            store.replace_entries_for_source(
                library_slug,
                source_id,
                entries=entries[source_id],
            )
        player_entries = {entry["slug"]: entry for entry in entries[player_source]}
        for slug, visibility, enabled in (
            ("browser-dm-compass", VISIBILITY_DM, None),
            ("browser-private-compass", VISIBILITY_PRIVATE, None),
            ("browser-disabled-compass", None, False),
        ):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug=library_slug,
                entry_key=player_entries[slug]["entry_key"],
                visibility_override=visibility,
                is_enabled_override=enabled,
            )
        store.upsert_entry(
            library_slug,
            "DMG",
            entry_key="dnd-5e|book|dmg|p74b-browser-source-only",
            entry_type="book",
            slug="p74b-browser-source-only",
            title="Planar Bearings",
            search_text="planar bearings",
            player_safe_default=False,
            dm_heavy=True,
            metadata={
                "headers": ["Source Only Browser Heading"],
                "section_label": "Chapter 1",
                "target_order": 1,
            },
            body={},
            rendered_html="<p>Planar bearings reference.</p>",
        )


def _sign_in(page, base_url: str, user: dict[str, object]) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(str(user["email"]))
    page.locator("input[name='password']").fill(str(user["password"]))
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _wait_for_loading_cover(page) -> None:
    expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(
        0,
        timeout=5000,
    )
    expect(page.locator("body > .app-loading-cover")).to_have_count(1)
    expect(page.locator("main .app-loading-cover")).to_have_count(0)


def _assert_within_viewport(page, selector: str, label: str, *, required: bool = True) -> None:
    rows = page.locator(selector)
    if not rows.count():
        assert not required, f"{label}: missing {selector}"
        return
    for index in range(rows.count()):
        measurements = rows.nth(index).evaluate(
            """element => {
                const rect = element.getBoundingClientRect();
                return {
                    left: rect.left,
                    right: rect.right,
                    clientWidth: element.clientWidth,
                    scrollWidth: element.scrollWidth,
                    overflowX: getComputedStyle(element).overflowX,
                };
            }"""
        )
        assert measurements["left"] >= -2, f"{label}: {selector}[{index}] starts left of viewport"
        assert measurements["right"] <= page.viewport_size["width"] + 2, (
            f"{label}: {selector}[{index}] extends right of viewport"
        )
        if measurements["overflowX"] not in {"hidden", "clip"}:
            assert measurements["scrollWidth"] <= measurements["clientWidth"] + 2, (
                f"{label}: {selector}[{index}] has horizontal overflow"
            )


def _assert_containment(page, label: str) -> None:
    document_width = page.evaluate(
        "() => (document.scrollingElement || document.documentElement).scrollWidth"
    )
    assert document_width <= page.viewport_size["width"] + 2, f"{label}: document overflow"
    for selector in (
        ".page-shell",
        "main.main-content",
        ".page-layout",
        ".article.page-stack",
        ".card",
        "form",
        "input[type='search']",
        "button",
        ".plain-list",
        ".plain-list li",
        ".plain-list a",
    ):
        _assert_within_viewport(page, selector, label, required=False)


def _assert_resolved_labels(page) -> None:
    unresolved = page.evaluate(
        """() => [...document.querySelectorAll("[aria-labelledby]")].flatMap((element) => {
            const ids = (element.getAttribute("aria-labelledby") || "").trim().split(/\\s+/).filter(Boolean);
            return ids.filter((id) => !document.getElementById(id)).map((id) => ({
                tag: element.tagName,
                id,
            }));
        })"""
    )
    assert unresolved == []


def _assert_static_semantics(page) -> None:
    expect(page.locator("main h1")).to_have_count(1)
    expect(page.locator(".card .card")).to_have_count(0)
    expect(page.locator(".state-panel[role='status'], .state-panel[role='alert']")).to_have_count(0)
    expect(page.locator(".state-panel[aria-live]")).to_have_count(0)
    expect(page.locator("main [aria-busy='true']")).to_have_count(0)
    _assert_resolved_labels(page)


def _assert_friendly_privacy(page) -> None:
    text = page.locator("main").inner_text()
    for marker in (
        "P74B-BROWSER-PLAYER",
        "P74B-BROWSER-EMPTY",
        "P74B-BROWSER-PRIVATE",
        "P74B-BROWSER-DISABLED",
        "dnd-5e|",
        r"C:\private\imports",
        "browser-private-support",
        "browser-private-import",
        "browser-private-storage",
        "browser-private-provenance",
        "open_license",
        "Open License",
        "Source ID",
        "Default visibility",
        "source path",
        "import run",
        "storage state",
        "management inventory",
        "SQLite",
    ):
        assert marker.casefold() not in text.casefold(), f"visible internal marker: {marker}"


def _assert_skip_and_focus(page) -> None:
    page.locator("body").press("Home")
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main-content")).to_be_focused()
    assert page.locator("#main-content").evaluate(
        "element => parseFloat(getComputedStyle(element).outlineWidth)"
    ) > 0

    search_input = page.locator("main input[type='search']")
    if search_input.count():
        search_input.first.focus()
        page.keyboard.press("Tab")
        expect(page.locator("main button[type='submit']").first).to_be_focused()
        assert page.locator("main button[type='submit']").first.evaluate(
            "element => parseFloat(getComputedStyle(element).outlineWidth)"
        ) > 0
        focus_indexes = page.evaluate(
            """() => {
                const focusable = [...document.querySelectorAll("a[href], button, input:not([type='hidden']), select, textarea, summary")];
                const input = document.querySelector("main input[type='search']");
                const button = document.querySelector("main button[type='submit']");
                return [focusable.indexOf(input), focusable.indexOf(button)];
            }"""
        )
        assert focus_indexes[0] >= 0
        assert focus_indexes == sorted(focus_indexes)


def _assert_source_semantics(page, source_title: str) -> None:
    expect(page.get_by_role("heading", name=source_title, exact=True)).to_have_count(1)
    expect(page.get_by_role("navigation", name="Systems breadcrumb")).to_have_count(1)
    expect(page.get_by_role("link", name="Back to Systems", exact=True)).to_have_count(1)
    _assert_static_semantics(page)
    _assert_friendly_privacy(page)


def _assert_category_semantics(page, source_title: str) -> None:
    expect(
        page.get_by_role("heading", name=f"{source_title}: Spells", exact=True)
    ).to_have_count(1)
    expect(page.get_by_role("navigation", name="Systems breadcrumb")).to_have_count(1)
    expect(page.get_by_role("searchbox", name="Search Spells", exact=True)).to_have_count(1)
    expect(page.get_by_role("button", name="Search Spells", exact=True)).to_have_count(1)
    form = page.locator("main form")
    assert form.get_attribute("method").casefold() == "get"
    assert form.get_attribute("action").endswith(
        "/campaigns/linden-pass/systems/sources/P74B-BROWSER-PLAYER/types/spell"
    )
    _assert_static_semantics(page)
    _assert_friendly_privacy(page)


def test_systems_source_category_browser_matrix(
    app,
    users,
    systems_source_category_live_server,
):
    _seed_systems_source_category_browser_matrix(app)
    base_url = systems_source_category_live_server
    landing_url = f"{base_url}/campaigns/linden-pass/systems"
    player_source_url = f"{landing_url}/sources/P74B-BROWSER-PLAYER"
    player_category_url = f"{player_source_url}/types/spell"
    empty_source_url = f"{landing_url}/sources/P74B-BROWSER-EMPTY"
    private_source_url = f"{landing_url}/sources/P74B-BROWSER-PRIVATE"
    dmg_source_url = f"{landing_url}/sources/DMG"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        player_desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        player_mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
        admin_context = browser.new_context(viewport={"width": 1280, "height": 900})
        no_js_context = browser.new_context(
            viewport={"width": 390, "height": 800},
            java_script_enabled=False,
        )
        player_desktop = player_desktop_context.new_page()
        player_mobile = player_mobile_context.new_page()
        dm_page = dm_context.new_page()
        admin_page = admin_context.new_page()
        no_js_page = no_js_context.new_page()
        try:
            _sign_in(player_desktop, base_url, users["party"])
            player_desktop.goto(player_source_url)
            _wait_for_loading_cover(player_desktop)
            _assert_source_semantics(player_desktop, "Player Navigator")
            expect(player_desktop.get_by_role("heading", name="Browse This Source")).to_be_visible()
            expect(player_desktop.get_by_role("link", name="Spells", exact=True)).to_be_visible()
            expect(player_desktop.get_by_role("link", name="Opening Chapter", exact=True)).to_be_visible()
            expect(
                player_desktop.get_by_role(
                    "searchbox",
                    name="Search this source's rules references",
                    exact=True,
                )
            ).to_be_visible()
            expect(player_desktop.get_by_role("button", name="Search rules", exact=True)).to_be_visible()
            source_text = player_desktop.locator("main").inner_text()
            assert "5 entries are available to you." in source_text
            assert "DM Compass" not in source_text
            assert "Private Compass" not in source_text
            assert "Disabled Compass" not in source_text
            _assert_skip_and_focus(player_desktop)
            _assert_containment(player_desktop, "player desktop source")

            player_desktop.goto(player_category_url)
            _wait_for_loading_cover(player_desktop)
            _assert_category_semantics(player_desktop, "Player Navigator")
            expect(player_desktop.get_by_role("heading", name="Available Spells")).to_be_visible()
            expect(player_desktop.get_by_role("link", name="Amber Compass", exact=True)).to_be_visible()
            assert "Showing all 3 spells in this source." in player_desktop.locator("main").inner_text()
            _assert_skip_and_focus(player_desktop)
            _assert_containment(player_desktop, "player desktop category")

            player_desktop.goto(f"{player_category_url}?q=missing")
            _wait_for_loading_cover(player_desktop)
            _assert_category_semantics(player_desktop, "Player Navigator")
            expect(player_desktop.get_by_role("heading", name="No matching Spells")).to_be_visible()
            expect(player_desktop.get_by_role("link", name="Clear this search", exact=True)).to_be_visible()
            expect(player_desktop.get_by_role("searchbox", name="Search Spells")).to_have_value("missing")
            _assert_containment(player_desktop, "player desktop filtered empty")

            player_desktop.goto(empty_source_url)
            _wait_for_loading_cover(player_desktop)
            _assert_source_semantics(player_desktop, "Quiet Navigator")
            expect(
                player_desktop.get_by_role(
                    "heading",
                    name="No entries available from this source",
                    exact=True,
                )
            ).to_be_visible()
            _assert_containment(player_desktop, "player desktop source empty")

            _sign_in(player_mobile, base_url, users["party"])
            player_mobile.goto(player_source_url)
            _wait_for_loading_cover(player_mobile)
            _assert_source_semantics(player_mobile, "Player Navigator")
            _assert_skip_and_focus(player_mobile)
            _assert_containment(player_mobile, "player mobile source")
            player_mobile.goto(player_category_url)
            _wait_for_loading_cover(player_mobile)
            _assert_category_semantics(player_mobile, "Player Navigator")
            _assert_skip_and_focus(player_mobile)
            _assert_containment(player_mobile, "player mobile category")

            _sign_in(dm_page, base_url, users["dm"])
            dm_page.goto(f"{dmg_source_url}?reference_q=Source+Only+Browser+Heading")
            _wait_for_loading_cover(dm_page)
            _assert_static_semantics(dm_page)
            expect(
                dm_page.get_by_role(
                    "heading",
                    name="Dungeon Master's Guide (2014)",
                    exact=True,
                )
            ).to_be_visible()
            expect(dm_page.get_by_role("heading", name="Rules reference results")).to_be_visible()
            expect(
                dm_page.locator(
                    '[aria-labelledby="source-rules-results-heading"]'
                ).get_by_role("link", name="Planar Bearings", exact=True)
            ).to_be_visible()
            expect(
                dm_page.get_by_role(
                    "searchbox",
                    name="Search this source's rules references",
                    exact=True,
                )
            ).to_have_value("Source Only Browser Heading")
            assert (
                "DM-heavy source keeps chapter browse and rules-reference metadata search on this source page"
                in dm_page.locator("main").inner_text()
            )
            assert (
                "DMG chapter-backed rules pages default to DM visibility even if a campaign lowers "
                "the broader DMG source to surface specific player-facing DMG rows. Use entry "
                "overrides only when a chapter page should be intentionally exposed more broadly."
                in dm_page.locator("main").inner_text()
            )
            _assert_friendly_privacy(dm_page)
            _assert_containment(dm_page, "dm source-only search")

            _sign_in(admin_page, base_url, users["admin"])
            admin_page.goto(private_source_url)
            _wait_for_loading_cover(admin_page)
            _assert_source_semantics(admin_page, "Curator Navigator")
            expect(admin_page.get_by_role("link", name="Systems settings", exact=True)).to_be_visible()
            assert "Private Source Compass" not in admin_page.locator("main").inner_text()
            expect(admin_page.get_by_role("link", name="Spells", exact=True)).to_be_visible()
            _assert_containment(admin_page, "direct admin private source")

            view_as_response = admin_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["party"]["id"]},
            )
            assert view_as_response.ok
            admin_page.set_viewport_size({"width": 390, "height": 800})
            admin_page.goto(player_source_url)
            _wait_for_loading_cover(admin_page)
            _assert_source_semantics(admin_page, "Player Navigator")
            expect(admin_page.get_by_role("link", name="Systems settings", exact=True)).to_have_count(0)
            projected_text = admin_page.locator("main").inner_text()
            assert "5 entries are available to you." in projected_text
            assert "DM Compass" not in projected_text
            assert "Private Compass" not in projected_text
            _assert_containment(admin_page, "admin view as player mobile")

            _sign_in(no_js_page, base_url, users["party"])
            no_js_page.goto(landing_url)
            no_js_page.get_by_role("link", name="Player Navigator", exact=True).click()
            expect(no_js_page).to_have_url(re.compile(r"/systems/sources/P74B-BROWSER-PLAYER$"))
            expect(no_js_page.get_by_role("heading", name="Player Navigator", exact=True)).to_be_visible()
            no_js_page.get_by_role("link", name="Spells", exact=True).click()
            expect(no_js_page).to_have_url(re.compile(r"/types/spell$"))
            expect(no_js_page.get_by_role("heading", name="Player Navigator: Spells", exact=True)).to_be_visible()
            no_js_page.get_by_role("link", name="Amber Compass", exact=True).click()
            expect(no_js_page).to_have_url(re.compile(r"/systems/entries/browser-amber-compass$"))
            expect(no_js_page.get_by_role("heading", name="Amber Compass", exact=True)).to_be_visible()

            no_js_page.goto(player_category_url)
            no_js_page.get_by_role("searchbox", name="Search Spells", exact=True).fill("Amber")
            no_js_page.get_by_role("searchbox", name="Search Spells", exact=True).press("Enter")
            no_js_page.wait_for_url(re.compile(r"/types/spell\?q=Amber$"), timeout=5000)
            assert parse_qs(urlsplit(no_js_page.url).query) == {"q": ["Amber"]}
            expect(no_js_page.get_by_role("link", name="Amber Compass", exact=True)).to_be_visible()
            expect(no_js_page.get_by_role("link", name="Quiet Compass", exact=True)).to_have_count(0)

            no_js_page.goto(player_source_url)
            no_js_page.get_by_role(
                "searchbox",
                name="Search this source's rules references",
                exact=True,
            ).fill("Careful Bearing")
            no_js_page.get_by_role(
                "searchbox",
                name="Search this source's rules references",
                exact=True,
            ).press("Enter")
            no_js_page.wait_for_url(
                re.compile(r"/sources/P74B-BROWSER-PLAYER\?reference_q=Careful\+Bearing$"),
                timeout=5000,
            )
            assert parse_qs(urlsplit(no_js_page.url).query) == {
                "reference_q": ["Careful Bearing"]
            }
            expect(
                no_js_page.get_by_role("link", name="Measured Course", exact=True)
            ).to_be_visible()
            _assert_static_semantics(no_js_page)
            _assert_friendly_privacy(no_js_page)
            _assert_containment(no_js_page, "native no-js source search")
        finally:
            player_desktop.close()
            player_mobile.close()
            dm_page.close()
            admin_page.close()
            no_js_page.close()
            player_desktop_context.close()
            player_mobile_context.close()
            dm_context.close()
            admin_context.close()
            no_js_context.close()
            browser.close()
