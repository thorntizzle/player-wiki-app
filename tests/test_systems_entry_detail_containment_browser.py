from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from player_wiki.campaign_visibility import VISIBILITY_PLAYERS
from player_wiki.rich_text import sanitize_rich_html
from player_wiki.systems_importer import Dnd5eSystemsImporter


SCOPED_ENTRY_SELECTOR = (
    "main.main-content:has(> .page-layout > .article.card .table-scroll)"
)
LONG_UNBROKEN = "UnbrokenContainmentToken" * 18
LONG_SPACED = (
    "A deliberately long but naturally spaced Systems entry label that must remain "
    "inside its owning card at desktop and mobile widths"
)


@pytest.fixture
def systems_entry_containment_live_server(app):
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


def _table_html() -> str:
    headers = "".join(f"<th>Wide column {index}</th>" for index in range(1, 9))
    cells = "".join(
        f"<td>Cell {index} {LONG_UNBROKEN}</td>" for index in range(1, 9)
    )
    return (
        '<div class="table-scroll"><table>'
        f"<caption>{LONG_SPACED}</caption>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody><tr>{cells}</tr></tbody>"
        "</table></div>"
    )


def _seed_entry_containment_matrix(app) -> str:
    source_id = "P74C-CONTAINMENT"
    entry_slug = "p74c-table-containment"
    rendered_html = "".join(
        (
            f'<h2 id="long-spaced-article">{LONG_SPACED}.</h2>',
            f'<h3 id="long-unbroken-article">{LONG_UNBROKEN}</h3>',
            _table_html(),
            (
                '<p><a class="long-article-link" href="#containment-target-card">'
                f"{LONG_UNBROKEN}</a></p>"
            ),
            (
                '<article class="card systems-inline-feature-card" '
                'id="containment-target-card">'
                f"<h2>{LONG_UNBROKEN}</h2>"
                f'<p><a class="long-target-link" href="#long-spaced-article">'
                f"{LONG_SPACED}</a></p>"
                "</article>"
            ),
            "".join(
                f"<p>Natural document flow paragraph {index}: {LONG_SPACED}.</p>"
                for index in range(1, 19)
            ),
        )
    )
    entry = {
        "entry_key": f"dnd-5e|book|{source_id.lower()}|{entry_slug}",
        "entry_type": "book",
        "slug": entry_slug,
        "title": f"{LONG_SPACED} {LONG_UNBROKEN}",
        "source_path": r"C:\sanitized\p74c-containment.json",
        "search_text": "p74c table containment",
        "player_safe_default": True,
        "metadata": {
            "headers": [LONG_SPACED, LONG_UNBROKEN],
            "section_label": "Containment chapter",
            "target_order": 1,
            "section_outline": [
                {
                    "title": LONG_SPACED,
                    "anchor": "long-spaced-article",
                    "depth": 1,
                },
                {
                    "title": LONG_UNBROKEN,
                    "anchor": "long-unbroken-article",
                    "depth": 1,
                },
            ],
        },
        "body": {},
        "rendered_html": rendered_html,
    }

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Containment Reference",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility=VISIBILITY_PLAYERS,
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[entry],
        )
    return entry_slug


def _sign_in(page, base_url: str, user: dict[str, object]) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(str(user["email"]))
    page.locator("input[name='password']").fill(str(user["password"]))
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _wait_for_loading_cover(page, *, java_script_enabled: bool) -> None:
    if java_script_enabled:
        expect(
            page.locator("html.app-loading, html.app-loading-closing")
        ).to_have_count(0, timeout=5000)
    expect(page.locator("body > .app-loading-cover")).to_have_count(1)
    expect(page.locator("main .app-loading-cover")).to_have_count(0)


def _assert_box_within(page, selector: str, label: str) -> None:
    elements = page.locator(selector)
    assert elements.count(), f"{label}: missing {selector}"
    for index in range(elements.count()):
        metrics = elements.nth(index).evaluate(
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
        assert metrics["left"] >= -2, f"{label}: {selector}[{index}] starts outside"
        assert metrics["right"] <= page.viewport_size["width"] + 2, (
            f"{label}: {selector}[{index}] ends outside"
        )
        if (
            selector != ".table-scroll"
            and metrics["overflowX"] not in {"hidden", "clip"}
        ):
            assert metrics["scrollWidth"] <= metrics["clientWidth"] + 2, (
                f"{label}: {selector}[{index}] leaks horizontal content"
            )


def _assert_visible_focus(locator, label: str) -> None:
    expect(locator).to_be_focused()
    focus = locator.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                outlineStyle: style.outlineStyle,
                outlineWidth: parseFloat(style.outlineWidth),
            };
        }"""
    )
    assert focus["outlineStyle"] != "none", f"{label}: focus outline missing"
    assert focus["outlineWidth"] > 0, f"{label}: focus outline has no width"


def _assert_containment_and_natural_scroll(page, label: str) -> None:
    document_metrics = page.evaluate(
        """() => {
            const root = document.scrollingElement || document.documentElement;
            return {
                clientWidth: root.clientWidth,
                scrollWidth: root.scrollWidth,
                clientHeight: root.clientHeight,
                scrollHeight: root.scrollHeight,
            };
        }"""
    )
    assert document_metrics["scrollWidth"] <= document_metrics["clientWidth"] + 2, (
        f"{label}: document has horizontal overflow"
    )
    assert document_metrics["scrollHeight"] > document_metrics["clientHeight"] + 100, (
        f"{label}: fixture did not preserve natural document vertical scrolling"
    )

    for selector in (
        ".page-shell",
        "main.main-content",
        ".hero",
        ".hero h1",
        ".page-layout",
        ".article.card",
        ".sidebar",
        ".sidebar-card",
        "#containment-target-card",
        "#long-spaced-article",
        "#long-unbroken-article",
        ".long-article-link",
        ".long-target-link",
        ".sidebar-card a",
        ".table-scroll",
    ):
        _assert_box_within(page, selector, label)

    table_metrics = page.locator(".table-scroll").evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
                scrollHeight: element.scrollHeight,
                clientHeight: element.clientHeight,
                overflowX: style.overflowX,
                maxHeight: style.maxHeight,
                position: style.position,
                overscrollInline: style.overscrollBehaviorInline,
            };
        }"""
    )
    assert table_metrics["overflowX"] == "auto"
    assert table_metrics["overscrollInline"] == "contain"
    assert table_metrics["scrollWidth"] > table_metrics["clientWidth"] + 100
    assert table_metrics["scrollHeight"] <= table_metrics["clientHeight"] + 2
    assert table_metrics["maxHeight"] == "none"
    assert table_metrics["position"] != "fixed"

    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert page.evaluate("window.scrollY") > 0, f"{label}: document did not scroll vertically"
    page.evaluate("window.scrollTo(0, 0)")


def _assert_sequential_keyboard_path(page, label: str) -> None:
    page.locator("body").press("Home")
    page.keyboard.press("Tab")
    _assert_visible_focus(page.locator(".skip-link"), f"{label} skip link")
    page.keyboard.press("Enter")
    _assert_visible_focus(page.locator("#main-content"), f"{label} main content")

    breadcrumb_links = page.locator('nav[aria-label="Systems breadcrumb"] a')
    assert breadcrumb_links.count(), f"{label}: Systems breadcrumb has no native links"
    for index in range(breadcrumb_links.count()):
        page.keyboard.press("Tab")
        _assert_visible_focus(
            breadcrumb_links.nth(index),
            f"{label} breadcrumb link {index + 1}",
        )

    page.keyboard.press("Tab")
    table_scroll = page.locator(".table-scroll")
    _assert_visible_focus(table_scroll, f"{label} table scroller")

    before = page.evaluate(
        """() => ({
            table: document.querySelector(".table-scroll").scrollLeft,
            document: (document.scrollingElement || document.documentElement).scrollLeft,
        })"""
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    after = page.evaluate(
        """() => ({
            table: document.querySelector(".table-scroll").scrollLeft,
            document: (document.scrollingElement || document.documentElement).scrollLeft,
        })"""
    )
    assert after["table"] > before["table"], f"{label}: ArrowRight did not scroll table"
    assert after["document"] == before["document"] == 0, (
        f"{label}: ArrowRight moved the document horizontally"
    )

    sidebar_link = page.locator(
        '.sidebar-card a[href="#long-spaced-article"]'
    )
    reached_sidebar = False
    for _ in range(20):
        page.keyboard.press("Tab")
        if sidebar_link.evaluate("element => element === document.activeElement"):
            reached_sidebar = True
            break
    assert reached_sidebar, f"{label}: sequential focus never reached the long sidebar link"
    _assert_visible_focus(sidebar_link, f"{label} sidebar link")


def test_systems_entry_table_containment_static_and_wrapper_contracts(
    app,
    tmp_path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "player_wiki/static/styles.css").read_text(
        encoding="utf-8"
    )

    assert SCOPED_ENTRY_SELECTOR in stylesheet
    assert f"{SCOPED_ENTRY_SELECTOR} .table-scroll {{" in stylesheet
    assert f"{SCOPED_ENTRY_SELECTOR} .table-scroll:focus-visible {{" in stylesheet
    assert f"{SCOPED_ENTRY_SELECTOR} .table-scroll > table {{" in stylesheet
    for contract in (
        "overflow-x: auto;",
        "overscroll-behavior-inline: contain;",
        "width: max-content;",
        "min-width: 100%;",
        "max-width: none;",
        "overflow-wrap: anywhere;",
    ):
        assert contract in stylesheet

    scoped_css = stylesheet[
        stylesheet.index(SCOPED_ENTRY_SELECTOR) : stylesheet.index(
            ".plain-list {",
            stylesheet.index(SCOPED_ENTRY_SELECTOR),
        )
    ]
    for forbidden in (
        "height:",
        "max-height:",
        "position: fixed",
        "overflow-y:",
    ):
        assert forbidden not in scoped_css
    assert not re.search(r"(?m)^\.table-scroll(?:\s|:|>)", stylesheet)
    assert ".article-body table {" in stylesheet

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=tmp_path,
        )
        importer_table = importer._render_table(
            {
                "caption": "Generated table",
                "colLabels": ["First", "Second"],
                "rows": [["A", "B"]],
            }
        )
        service_table = app.extensions["systems_service"]._render_embedded_table(
            {
                "caption": "Embedded table",
                "colLabels": ["First", "Second"],
                "rows": [["A", "B"]],
            }
        )

    for rendered in (importer_table, service_table):
        assert rendered.startswith('<div class="table-scroll"><table>')
        assert rendered.endswith("</tbody></table></div>")
        assert rendered.count('<div class="table-scroll">') == 1
        assert sanitize_rich_html(rendered) == rendered


def test_systems_entry_table_containment_real_chromium_matrix(
    app,
    users,
    systems_entry_containment_live_server,
) -> None:
    entry_slug = _seed_entry_containment_matrix(app)
    base_url = systems_entry_containment_live_server
    entry_url = f"{base_url}/campaigns/linden-pass/systems/entries/{entry_slug}"
    scenarios = (
        ("desktop js", {"width": 1280, "height": 900}, True),
        ("desktop no-js", {"width": 1280, "height": 900}, False),
        ("mobile js", {"width": 390, "height": 800}, True),
        ("mobile no-js", {"width": 390, "height": 800}, False),
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for label, viewport, java_script_enabled in scenarios:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                )
                page = context.new_page()
                try:
                    _sign_in(page, base_url, users["party"])
                    page.goto(entry_url)
                    _wait_for_loading_cover(
                        page,
                        java_script_enabled=java_script_enabled,
                    )
                    expect(page.locator("main h1")).to_have_count(1)
                    expect(page.locator(".table-scroll")).to_have_count(1)
                    expect(page.locator("#containment-target-card")).to_have_count(1)
                    expect(
                        page.locator('.sidebar-card a[href="#long-spaced-article"]')
                    ).to_have_count(1)
                    assert page.evaluate(
                        f"CSS.supports('selector({SCOPED_ENTRY_SELECTOR})')"
                    )
                    assert page.locator("main.main-content").evaluate(
                        """(element, selector) => element.matches(selector)""",
                        SCOPED_ENTRY_SELECTOR,
                    )
                    _assert_containment_and_natural_scroll(page, label)
                    _assert_sequential_keyboard_path(page, label)
                finally:
                    page.close()
                    context.close()
        finally:
            browser.close()
