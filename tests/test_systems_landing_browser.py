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
def systems_landing_live_server(app):
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


def _seed_systems_landing_browser_matrix(app) -> None:
    source_rows = (
        ("BROWSE-PLAYER", "Player Almanac", True, VISIBILITY_PLAYERS),
        ("BROWSE-DM", "Game Master Almanac", True, VISIBILITY_DM),
        ("BROWSE-PRIVATE", "Curator Almanac", True, VISIBILITY_PRIVATE),
        ("BROWSE-DISABLED", "Dormant Almanac", False, VISIBILITY_PLAYERS),
    )
    entries: dict[str, list[dict[str, object]]] = {source_id: [] for source_id, *_ in source_rows}

    def add(
        source_id: str,
        slug: str,
        title: str,
        *,
        entry_type: str = "spell",
        metadata: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
    ) -> str:
        key = f"dnd-5e|{entry_type}|{source_id.lower()}|{slug}"
        entries[source_id].append(
            {
                "entry_key": key,
                "entry_type": entry_type,
                "slug": slug,
                "title": title,
                "source_path": f"C:\\private\\imports\\{source_id.lower()}-browser.json",
                "search_text": f"{title} hidden-search-index-marker",
                "player_safe_default": True,
                "metadata": {
                    "support_state": "browser-support-internal",
                    "review_status": "browser-review-internal",
                    "import_run_id": "browser-import-run-internal",
                    "archive_filename": "browser-archive-internal.zip",
                    "sqlite_storage_state": "browser-storage-internal",
                    "provenance_actor": "browser-provenance-internal",
                    **dict(metadata or {}),
                },
                "body": dict(body or {}),
                "rendered_html": f"<p>{title} reader text.</p>",
            }
        )
        return key

    add("BROWSE-PLAYER", "amber-atlas", "Amber Atlas")
    add(
        "BROWSE-PLAYER",
        "careful-measure",
        "Careful Measure",
        entry_type="rule",
        metadata={
            "aliases": ["Measured Guard"],
            "formula": "12 focus",
            "rule_facets": ["careful_reference"],
        },
        body={"summary": "rules-body-only-browser"},
    )
    add(
        "BROWSE-PLAYER",
        "first-steps",
        "First Steps",
        entry_type="book",
        metadata={
            "headers": ["Opening Move"],
            "section_label": "Chapter 1",
            "target_order": 1,
        },
    )
    add(
        "BROWSE-PLAYER",
        "body-whisper",
        "Body Whisper",
        body={"summary": "ordinary-body-only-browser"},
    )
    dm_entry_key = add("BROWSE-PLAYER", "dm-brief", "DM Brief")
    private_entry_key = add("BROWSE-PLAYER", "private-brief", "Private Brief")
    disabled_entry_key = add("BROWSE-PLAYER", "disabled-brief", "Disabled Brief")
    add("BROWSE-DM", "dm-source-brief", "DM Source Brief")
    add("BROWSE-PRIVATE", "private-source-brief", "Private Source Brief")
    add("BROWSE-DISABLED", "disabled-source-brief", "Disabled Source Brief")

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
        for entry_key, visibility, enabled in (
            (dm_entry_key, VISIBILITY_DM, None),
            (private_entry_key, VISIBILITY_PRIVATE, None),
            (disabled_entry_key, None, False),
        ):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug=library_slug,
                entry_key=entry_key,
                visibility_override=visibility,
                is_enabled_override=enabled,
            )
        store.upsert_entry(
            library_slug,
            "DMG",
            entry_key="dnd-5e|book|dmg|browser-source-only-reference",
            entry_type="book",
            slug="browser-source-only-reference",
            title="Source Page Reference",
            search_text="source page reference",
            player_safe_default=False,
            dm_heavy=True,
            metadata={
                "headers": ["Planar Browser Reference"],
                "section_label": "Chapter 1",
                "target_order": 1,
            },
            body={},
            rendered_html="<p>Source page reference.</p>",
        )


def _sign_in(page, base_url: str, user: dict[str, object]) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(str(user["email"]))
    page.locator("input[name='password']").fill(str(user["password"]))
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _wait_for_loading_cover(page) -> None:
    expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0, timeout=5000)


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


def _assert_landing_containment(page, label: str) -> None:
    document_width = page.evaluate(
        "() => (document.scrollingElement || document.documentElement).scrollWidth"
    )
    assert document_width <= page.viewport_size["width"] + 2, f"{label}: document overflow"
    for selector in (
        ".page-shell",
        "main.main-content",
        ".page-layout",
        ".article.page-stack",
        ".card.search-card",
        ".card.search-card form",
        ".card.search-card input[type='search']",
        ".card.search-card button",
    ):
        _assert_within_viewport(page, selector, label)
    _assert_within_viewport(
        page,
        ".card.search-card .plain-list li",
        label,
        required=False,
    )


def _assert_negative_visible_inventory(page) -> None:
    text = page.locator("main").inner_text()
    for marker in (
        "BROWSE-PLAYER",
        "BROWSE-DM",
        "BROWSE-PRIVATE",
        "BROWSE-DISABLED",
        "dnd-5e|",
        "C:\\private\\imports",
        "browser-support-internal",
        "browser-review-internal",
        "browser-import-run-internal",
        "browser-archive-internal.zip",
        "browser-storage-internal",
        "browser-provenance-internal",
        "open_license",
        "Open License",
        "default visibility",
        "source policy",
        "source IDs",
        "landing-page",
        "DM-heavy source-backed",
        "SQLite",
        "management inventory",
    ):
        assert marker.casefold() not in text.casefold(), f"visible internal marker: {marker}"


def _assert_task_semantics(page) -> None:
    task_cards = page.locator(".article.page-stack > section.card.search-card")
    expect(task_cards).to_have_count(2)
    assert task_cards.nth(0).get_attribute("aria-labelledby") == "systems-search-heading"
    assert task_cards.nth(1).get_attribute("aria-labelledby") == "rules-reference-search-heading"
    expect(task_cards.locator(".card")).to_have_count(0)
    ordinary_input = page.locator("input[type='search'][name='q']")
    rules_input = page.locator("input[type='search'][name='reference_q']")
    expect(ordinary_input).to_have_count(1)
    expect(ordinary_input).to_have_accessible_name("Search Systems entries")
    expect(page.get_by_role("button", name="Search Systems", exact=True)).to_have_count(1)
    expect(rules_input).to_have_count(1)
    expect(rules_input).to_have_accessible_name("Search rules references")
    expect(page.get_by_role("button", name="Search rules", exact=True)).to_have_count(1)
    assert ordinary_input.get_attribute("aria-describedby") == "systems-search-help"
    assert rules_input.get_attribute("aria-describedby") == "rules-reference-search-help"
    expect(page.locator("main h1")).to_have_count(1)
    expect(page.locator(".card.search-card [role='status'], .card.search-card [role='alert']")).to_have_count(0)
    expect(page.locator(".card.search-card [aria-live]")).to_have_count(0)
    for form in page.locator(".card.search-card form").all():
        assert form.get_attribute("method").casefold() == "get"
        assert form.get_attribute("action").endswith("/campaigns/linden-pass/systems/search")


def _assert_first_viewport_and_focus(page) -> None:
    viewport_height = page.viewport_size["height"]
    for selector in (
        ".site-header__campaign-title",
        ".site-header__actions",
        ".campaign-nav",
        "main h1",
        "input[type='search'][name='q']",
    ):
        box = page.locator(selector).bounding_box()
        assert box is not None and box["y"] < viewport_height, f"first viewport missing {selector}"

    page.locator("body").press("Home")
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main-content")).to_be_focused()
    main_outline = page.locator("#main-content").evaluate(
        "element => parseFloat(getComputedStyle(element).outlineWidth)"
    )
    assert main_outline > 0

    ordinary_input = page.locator("input[type='search'][name='q']")
    ordinary_input.focus()
    page.keyboard.press("Tab")
    ordinary_button = page.get_by_role("button", name="Search Systems", exact=True)
    expect(ordinary_button).to_be_focused()
    assert ordinary_button.evaluate(
        "element => parseFloat(getComputedStyle(element).outlineWidth)"
    ) > 0
    focus_order = page.evaluate(
        """() => [
            document.querySelector("input[type='search'][name='q']"),
            [...document.querySelectorAll("button")].find((element) => element.textContent.trim() === "Search Systems"),
            document.querySelector("input[type='search'][name='reference_q']"),
            [...document.querySelectorAll("button")].find((element) => element.textContent.trim() === "Search rules"),
        ].map((element) => [...document.querySelectorAll("a[href], button, input:not([type='hidden']), select, textarea, summary")].indexOf(element))"""
    )
    assert focus_order == sorted(focus_order)
    rules_input = page.locator("input[type='search'][name='reference_q']")
    rules_input.focus()
    page.keyboard.press("Tab")
    rules_button = page.get_by_role("button", name="Search rules", exact=True)
    expect(rules_button).to_be_focused()
    assert rules_button.evaluate(
        "element => parseFloat(getComputedStyle(element).outlineWidth)"
    ) > 0


def test_systems_landing_player_first_browser_matrix(
    app,
    users,
    systems_landing_live_server,
):
    _seed_systems_landing_browser_matrix(app)
    base_url = systems_landing_live_server
    landing_url = f"{base_url}/campaigns/linden-pass/systems"

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
            player_desktop.goto(landing_url)
            _wait_for_loading_cover(player_desktop)
            _assert_task_semantics(player_desktop)
            _assert_first_viewport_and_focus(player_desktop)
            _assert_negative_visible_inventory(player_desktop)
            _assert_landing_containment(player_desktop, "player desktop initial")
            player_text = player_desktop.locator("main").inner_text()
            assert "Player Almanac" in player_text
            assert "Amber Atlas" not in player_text
            assert "Game Master Almanac" not in player_text
            assert "Curator Almanac" not in player_text
            assert "Dormant Almanac" not in player_text
            assert "Systems settings" not in player_text
            assert player_desktop.locator(
                'a[href="/campaigns/linden-pass/systems/sources/BROWSE-PLAYER"]'
            ).count() == 1

            player_desktop.goto(f"{landing_url}/search?q=&reference_q=")
            _wait_for_loading_cover(player_desktop)
            expect(player_desktop.locator("input[type='search'][name='q']")).to_have_value("")
            expect(player_desktop.locator("input[type='search'][name='reference_q']")).to_have_value("")
            player_desktop.locator("input[type='search'][name='q']").fill("Amber Atlas")
            player_desktop.locator("input[type='search'][name='q']").press("Enter")
            player_desktop.wait_for_url(re.compile(r"/systems/search\?.*q=Amber\+Atlas"), timeout=5000)
            _wait_for_loading_cover(player_desktop)
            expect(player_desktop.get_by_role("heading", name="Systems search results")).to_be_visible()
            expect(player_desktop.get_by_role("link", name="Amber Atlas", exact=True)).to_be_visible()
            assert "Player Almanac | Spells" in player_desktop.locator("main").inner_text()
            assert player_desktop.get_by_role("link", name="Amber Atlas", exact=True).get_attribute("href").endswith(
                "/campaigns/linden-pass/systems/entries/amber-atlas"
            )

            player_desktop.locator("input[type='search'][name='reference_q']").fill("Measured Guard")
            player_desktop.locator("input[type='search'][name='reference_q']").press("Enter")
            player_desktop.wait_for_url(re.compile(r"/systems/search\?.*reference_q=Measured\+Guard"), timeout=5000)
            _wait_for_loading_cover(player_desktop)
            query = parse_qs(urlsplit(player_desktop.url).query)
            assert query == {"q": ["Amber Atlas"], "reference_q": ["Measured Guard"]}
            expect(player_desktop.locator("input[type='search'][name='q']")).to_have_value("Amber Atlas")
            expect(player_desktop.locator("input[type='search'][name='reference_q']")).to_have_value("Measured Guard")
            expect(player_desktop.get_by_role("link", name="Careful Measure", exact=True)).to_be_visible()
            assert "Player Almanac | Rules" in player_desktop.locator("main").inner_text()
            _assert_negative_visible_inventory(player_desktop)
            _assert_landing_containment(player_desktop, "player desktop populated")

            player_desktop.goto(
                f"{landing_url}/search?q=ordinary-body-only-browser&reference_q=rules-body-only-browser"
            )
            _wait_for_loading_cover(player_desktop)
            expect(player_desktop.get_by_role("heading", name="No Systems entries found")).to_be_visible()
            expect(player_desktop.get_by_role("heading", name="No rules references found")).to_be_visible()
            assert "Body Whisper" not in player_desktop.locator("main").inner_text()
            assert "Careful Measure" not in player_desktop.locator("main").inner_text()

            _sign_in(player_mobile, base_url, users["party"])
            player_mobile.goto(f"{landing_url}/search?q=Amber+Atlas&reference_q=Opening+Move")
            _wait_for_loading_cover(player_mobile)
            _assert_task_semantics(player_mobile)
            _assert_first_viewport_and_focus(player_mobile)
            _assert_negative_visible_inventory(player_mobile)
            _assert_landing_containment(player_mobile, "player mobile populated")

            _sign_in(dm_page, base_url, users["dm"])
            dm_page.goto(f"{landing_url}/search?q=Brief")
            _wait_for_loading_cover(dm_page)
            dm_text = dm_page.locator("main").inner_text()
            assert "Player Almanac" in dm_text
            assert "Game Master Almanac" in dm_text
            assert "DM Brief" in dm_text
            assert "DM Source Brief" in dm_text
            assert "Curator Almanac" not in dm_text
            assert "Private Brief" not in dm_text
            assert "Dormant Almanac" not in dm_text
            assert "Disabled Brief" not in dm_text
            assert "Systems settings" in dm_text
            assert dm_page.locator('a[href="/campaigns/linden-pass/systems/sources/DMG"]').count() >= 2
            _assert_negative_visible_inventory(dm_page)
            _assert_landing_containment(dm_page, "dm desktop")

            _sign_in(admin_page, base_url, users["admin"])
            admin_page.goto(f"{landing_url}/search?q=Brief")
            _wait_for_loading_cover(admin_page)
            admin_text = admin_page.locator("main").inner_text()
            assert "Game Master Almanac" in admin_text
            assert "Curator Almanac" in admin_text
            assert "DM Brief" in admin_text
            assert "Private Brief" in admin_text
            assert "Private Source Brief" in admin_text
            assert "Dormant Almanac" not in admin_text
            assert "Disabled Brief" not in admin_text
            assert "Disabled Source Brief" not in admin_text
            assert "Systems settings" in admin_text
            _assert_negative_visible_inventory(admin_page)
            _assert_landing_containment(admin_page, "direct admin desktop")

            view_as_response = admin_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["party"]["id"]},
            )
            assert view_as_response.ok
            admin_page.set_viewport_size({"width": 390, "height": 800})
            admin_page.goto(f"{landing_url}/search?q=Brief")
            _wait_for_loading_cover(admin_page)
            projected_text = admin_page.locator("main").inner_text()
            assert "Player Almanac" in projected_text
            assert "Game Master Almanac" not in projected_text
            assert "Curator Almanac" not in projected_text
            assert "DM Brief" not in projected_text
            assert "Private Brief" not in projected_text
            assert "Systems settings" not in projected_text
            _assert_negative_visible_inventory(admin_page)
            _assert_landing_containment(admin_page, "admin view as player mobile")

            _sign_in(no_js_page, base_url, users["party"])
            no_js_page.goto(landing_url)
            _assert_task_semantics(no_js_page)
            no_js_page.locator("input[type='search'][name='reference_q']").fill("Measured Guard")
            no_js_page.locator("input[type='search'][name='reference_q']").press("Enter")
            no_js_page.wait_for_url(re.compile(r"/systems/search\?.*reference_q=Measured\+Guard"), timeout=5000)
            expect(no_js_page.get_by_role("link", name="Careful Measure", exact=True)).to_be_visible()
            no_js_page.locator("input[type='search'][name='q']").fill("ordinary-body-only-browser")
            no_js_page.locator("input[type='search'][name='q']").press("Enter")
            no_js_page.wait_for_url(re.compile(r"/systems/search\?.*q=ordinary-body-only-browser"), timeout=5000)
            no_js_query = parse_qs(urlsplit(no_js_page.url).query)
            assert no_js_query == {
                "q": ["ordinary-body-only-browser"],
                "reference_q": ["Measured Guard"],
            }
            expect(no_js_page.get_by_role("heading", name="No Systems entries found")).to_be_visible()
            expect(no_js_page.get_by_role("link", name="Careful Measure", exact=True)).to_be_visible()
            no_js_page.goto(landing_url)
            no_js_page.locator(
                'a[href="/campaigns/linden-pass/systems/sources/BROWSE-PLAYER"]'
            ).click()
            expect(no_js_page).to_have_url(re.compile(r"/systems/sources/BROWSE-PLAYER$"))
            expect(no_js_page.get_by_role("heading", name="Player Almanac", exact=True)).to_be_visible()
            no_js_page.goto(f"{landing_url}/search?q=Amber+Atlas")
            no_js_page.get_by_role("link", name="Amber Atlas", exact=True).click()
            expect(no_js_page).to_have_url(re.compile(r"/systems/entries/amber-atlas$"))
            expect(no_js_page.get_by_role("heading", name="Amber Atlas", exact=True)).to_be_visible()
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
