from __future__ import annotations

import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from player_wiki.campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
)


SOURCE_ID = "P74C-PRESENTATION"
SOURCE_TITLE = "Adventurer's Field Manual"
PRIMARY_SLUG = "guiding-spark"
PRIMARY_TITLE = "Guiding Spark"
EMPTY_SLUG = "quiet-reference"
WIDENED_SOURCE_ID = "P74C-RESTRICTED-SOURCE"
WIDENED_SOURCE_TITLE = "Keeper's Restricted Notes"
WIDENED_SLUG = "widened-lantern"
DISABLED_SOURCE_ID = "P74C-DISABLED-SINGLETON"
DISABLED_SOURCE_TITLE = "Dormant Field Manual"
DISABLED_SLUG = "disabled-admin-reference"
INTERNAL_MARKERS = (
    r"C:\private\imports\p74c-entry-presentation.json",
    "p74c-support-state-internal",
    "p74c-import-run-internal",
    "p74c-policy-state-internal",
    "p74c-storage-state-internal",
    "p74c-provenance-internal",
    "p74c-audit-internal",
    "p74c-persistence-internal",
)


@pytest.fixture
def systems_entry_presentation_live_server(app):
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


def _primary_body() -> dict[str, object]:
    long_cell = "LocalTableScrollToken" * 20
    paragraphs = [
        (
            f"Reader field note {index}: this reference remains in natural document "
            "flow while preserving a calm player-facing presentation."
        )
        for index in range(1, 19)
    ]
    return {
        "entries": [
            *paragraphs[:4],
            {
                "type": "table",
                "caption": "Guiding Spark outcomes",
                "colLabels": [f"Outcome {index}" for index in range(1, 9)],
                "rows": [[f"{index}: {long_cell}" for index in range(1, 9)]],
            },
            {
                "type": "options",
                "count": 1,
                "entries": [
                    "Open the lantern path",
                    "Follow the starlight path",
                ],
            },
            *paragraphs[4:],
            "<script>window.p74cUnsafe = true</script>",
        ]
    }


def _seed_systems_entry_presentation_matrix(app, users) -> dict[str, str]:
    primary_key = f"dnd-5e|subclassfeature|{SOURCE_ID.lower()}|{PRIMARY_SLUG}"
    empty_key = f"dnd-5e|condition|{SOURCE_ID.lower()}|{EMPTY_SLUG}"
    dm_key = f"dnd-5e|spell|{SOURCE_ID.lower()}|dm-only-entry"
    private_key = f"dnd-5e|spell|{SOURCE_ID.lower()}|private-entry"
    rich_key = f"dnd-5e|rule|{SOURCE_ID.lower()}|safe-rich-entry"
    book_key = f"dnd-5e|book|{SOURCE_ID.lower()}|reader-chapter"
    widened_key = (
        f"dnd-5e|spell|{WIDENED_SOURCE_ID.lower()}|{WIDENED_SLUG}"
    )
    disabled_key = (
        f"dnd-5e|rule|{DISABLED_SOURCE_ID.lower()}|{DISABLED_SLUG}"
    )

    primary_entry = {
        "entry_key": primary_key,
        "entry_type": "subclassfeature",
        "slug": PRIMARY_SLUG,
        "title": PRIMARY_TITLE,
        "source_path": INTERNAL_MARKERS[0],
        "search_text": "guiding spark presentation",
        "player_safe_default": True,
        "metadata": {
            "class_name": "Mage",
            "subclass_name": "Lantern Keeper",
            "level": 3,
            "additional_spells": ["guiding bolt"],
            "support_state": INTERNAL_MARKERS[1],
            "import_run_id": INTERNAL_MARKERS[2],
            "campaign_policy_state": INTERNAL_MARKERS[3],
            "sqlite_storage_state": INTERNAL_MARKERS[4],
            "provenance_state": INTERNAL_MARKERS[5],
            "audit_state": INTERNAL_MARKERS[6],
            "persistence_state": INTERNAL_MARKERS[7],
        },
        "body": _primary_body(),
        "rendered_html": "<p>Fallback content must not replace the structured presentation.</p>",
    }
    source_entries = [
        primary_entry,
        {
            "entry_key": empty_key,
            "entry_type": "condition",
            "slug": EMPTY_SLUG,
            "title": "Quiet Reference",
            "source_page": "44",
            "source_path": r"C:\private\imports\quiet-reference.json",
            "search_text": "quiet reference",
            "player_safe_default": True,
            "metadata": {"internal_identifier": "quiet-internal-identifier"},
            "body": {},
            "rendered_html": "",
        },
        {
            "entry_key": dm_key,
            "entry_type": "spell",
            "slug": "dm-only-entry",
            "title": "DM Lantern",
            "search_text": "dm lantern",
            "player_safe_default": True,
            "metadata": {},
            "body": {},
            "rendered_html": "<p>DM-facing lantern guidance.</p>",
        },
        {
            "entry_key": private_key,
            "entry_type": "spell",
            "slug": "private-entry",
            "title": "Curator Lantern",
            "search_text": "curator lantern",
            "player_safe_default": True,
            "metadata": {},
            "body": {},
            "rendered_html": "<p>Curator-facing lantern guidance.</p>",
        },
        {
            "entry_key": rich_key,
            "entry_type": "rule",
            "slug": "safe-rich-entry",
            "title": "Safe Rich Reference",
            "search_text": "safe rich reference",
            "player_safe_default": True,
            "metadata": {},
            "body": {},
            "rendered_html": (
                '<section id="safe-rich-reader"><h2>Safe rich content</h2>'
                '<p onclick="window.p74cUnsafe=true"><strong>Reader-safe emphasis.</strong></p>'
                "<script>window.p74cUnsafe = true</script></section>"
            ),
        },
        {
            "entry_key": book_key,
            "entry_type": "book",
            "slug": "reader-chapter",
            "title": "Reader Chapter",
            "source_page": "73",
            "search_text": "reader chapter",
            "player_safe_default": True,
            "metadata": {
                "section_label": "Chapter 4",
                "chapter_title": "Adventurer Guidance",
                "headers": ["At the Lantern Gate"],
                "section_outline": [
                    {
                        "title": "At the Lantern Gate",
                        "anchor": "at-the-lantern-gate",
                        "depth": 1,
                        "page": "73",
                    }
                ],
            },
            "body": {},
            "rendered_html": (
                '<section id="at-the-lantern-gate"><h2>At the Lantern Gate</h2>'
                "<p>Reader-facing chapter guidance.</p></section>"
            ),
        },
    ]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        for source_id, title, visibility, entries in (
            (SOURCE_ID, SOURCE_TITLE, VISIBILITY_PLAYERS, source_entries),
            (
                WIDENED_SOURCE_ID,
                WIDENED_SOURCE_TITLE,
                VISIBILITY_DM,
                [
                    {
                        "entry_key": widened_key,
                        "entry_type": "spell",
                        "slug": WIDENED_SLUG,
                        "title": "Widened Lantern",
                        "search_text": "widened lantern",
                        "player_safe_default": True,
                        "metadata": {},
                        "body": {},
                        "rendered_html": "<p>Player-widened entry guidance.</p>",
                    }
                ],
            ),
            (
                DISABLED_SOURCE_ID,
                DISABLED_SOURCE_TITLE,
                VISIBILITY_PLAYERS,
                [
                    {
                        "entry_key": disabled_key,
                        "entry_type": "rule",
                        "slug": DISABLED_SLUG,
                        "title": "Disabled Admin Reference",
                        "search_text": "disabled admin reference",
                        "player_safe_default": True,
                        "metadata": {},
                        "body": {},
                        "rendered_html": "<p>Authorized admin reference.</p>",
                    }
                ],
            ),
        ):
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
                is_enabled=True,
                default_visibility=visibility,
            )
            store.replace_entries_for_source(
                library_slug,
                source_id,
                entries=entries,
            )

        for entry_key, visibility, enabled in (
            (dm_key, VISIBILITY_DM, None),
            (private_key, VISIBILITY_PRIVATE, None),
            (widened_key, VISIBILITY_PLAYERS, None),
            (disabled_key, None, False),
        ):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug=library_slug,
                entry_key=entry_key,
                visibility_override=visibility,
                is_enabled_override=enabled,
            )

        mechanics_dir = (
            Path(app.config["TEST_CAMPAIGNS_DIR"])
            / "linden-pass"
            / "content"
            / "mechanics"
        )
        mechanics_dir.mkdir(parents=True, exist_ok=True)
        (mechanics_dir / "alpha-reader-detail.md").write_text(
            (
                "---\n"
                "title: Alpha Reader Detail\n"
                "section: Mechanics\n"
                "type: mechanic\n"
                "character_option:\n"
                "  name: Alpha Reader Detail\n"
                "  activation_type: special\n"
                "  base_rule_refs:\n"
                f"    - slug: {PRIMARY_SLUG}\n"
                "      entry_type: subclassfeature\n"
                f"      source_id: {SOURCE_ID}\n"
                "      anchor: reader-options\n"
                "      section_title: Reader options\n"
                "---\n\n"
                "This published Mechanics page applies to the reader options section.\n"
            ),
            encoding="utf-8",
        )
        (mechanics_dir / "zeta-general-spark.md").write_text(
            (
                "---\n"
                "title: Zeta General Spark\n"
                "section: Mechanics\n"
                "type: mechanic\n"
                "character_option:\n"
                "  name: Zeta General Spark\n"
                "  activation_type: special\n"
                "  base_rule_refs:\n"
                f"    - slug: {PRIMARY_SLUG}\n"
                "      entry_type: subclassfeature\n"
                f"      source_id: {SOURCE_ID}\n"
                "---\n\n"
                "This published Mechanics page applies across the entry.\n"
            ),
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    return {
        "primary_key": primary_key,
        "primary_slug": PRIMARY_SLUG,
        "empty_slug": EMPTY_SLUG,
        "dm_slug": "dm-only-entry",
        "private_slug": "private-entry",
        "rich_slug": "safe-rich-entry",
        "book_slug": "reader-chapter",
        "widened_slug": WIDENED_SLUG,
        "disabled_slug": DISABLED_SLUG,
    }


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


def _assert_accessibility_integrity(page, label: str) -> None:
    expect(page.locator("h1")).to_have_count(1)
    expect(page.locator('nav[aria-label="Systems breadcrumb"]')).to_have_count(1)
    expect(
        page.locator('nav[aria-label="Systems breadcrumb"] [aria-current="page"]')
    ).to_have_count(1)
    failures = page.evaluate(
        """() => {
            const ids = [...document.querySelectorAll("[id]")].map(node => node.id);
            const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
            const brokenRefs = [];
            for (const node of document.querySelectorAll("[aria-labelledby], [aria-describedby]")) {
                for (const attr of ["aria-labelledby", "aria-describedby"]) {
                    const value = node.getAttribute(attr);
                    if (!value) continue;
                    for (const id of value.trim().split(/\\s+/)) {
                        if (!document.getElementById(id)) brokenRefs.push(`${attr}:${id}`);
                    }
                }
            }
            const brokenLabels = [...document.querySelectorAll("label[for]")]
                .map(label => label.getAttribute("for"))
                .filter(id => id && !document.getElementById(id));
            return {duplicateIds, brokenRefs, brokenLabels};
        }"""
    )
    assert failures == {
        "duplicateIds": [],
        "brokenRefs": [],
        "brokenLabels": [],
    }, f"{label}: invalid ID/label/ARIA references"


def _assert_containment(page, label: str, *, expect_table: bool) -> None:
    metrics = page.evaluate(
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
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 2, (
        f"{label}: document has horizontal overflow"
    )
    if expect_table:
        assert metrics["scrollHeight"] > metrics["clientHeight"] + 100, (
            f"{label}: fixture does not exercise natural vertical scrolling"
        )

    for selector in (
        ".page-shell",
        "main.main-content",
        ".hero",
        ".hero h1",
        ".page-layout",
        ".page-layout > .article.card",
        ".sidebar",
    ):
        rows = page.locator(selector)
        assert rows.count(), f"{label}: missing {selector}"
        for index in range(rows.count()):
            box = rows.nth(index).bounding_box()
            assert box is not None
            assert box["x"] >= -2, f"{label}: {selector}[{index}] begins outside viewport"
            assert box["x"] + box["width"] <= page.viewport_size["width"] + 2, (
                f"{label}: {selector}[{index}] is clipped"
            )
    for index in range(page.locator(".sidebar-card").count()):
        box = page.locator(".sidebar-card").nth(index).bounding_box()
        assert box is not None
        assert box["x"] >= -2
        assert box["x"] + box["width"] <= page.viewport_size["width"] + 2

    if not expect_table:
        return
    table = page.locator(".table-scroll")
    expect(table).to_have_count(1)
    table_metrics = table.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
                clientHeight: element.clientHeight,
                scrollHeight: element.scrollHeight,
                overflowX: style.overflowX,
                overflowY: style.overflowY,
                maxHeight: style.maxHeight,
                position: style.position,
            };
        }"""
    )
    assert table_metrics["overflowX"] == "auto"
    assert table_metrics["scrollWidth"] > table_metrics["clientWidth"] + 100
    assert table_metrics["scrollHeight"] <= table_metrics["clientHeight"] + 2
    assert table_metrics["maxHeight"] == "none"
    assert table_metrics["position"] != "fixed"

    table.focus()
    _assert_visible_focus(table, f"{label} table scroller")
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
    assert after["table"] > before["table"], f"{label}: table did not scroll locally"
    assert after["document"] == before["document"] == 0

    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert page.evaluate("window.scrollY") > 0, f"{label}: document did not scroll vertically"
    page.evaluate("window.scrollTo(0, 0)")


def _assert_no_internal_inventory(page) -> None:
    visible = page.locator("main").inner_text().casefold()
    html = page.locator("main").inner_html()
    for marker in INTERNAL_MARKERS:
        assert marker not in html
    for marker in (
        "Entry Metadata",
        "Entry key:",
        "Class Source:",
        "Policy default visibility:",
        "Existing Structured Hooks:",
        "Missing Metadata For True Base-Rule Modifiers:",
        "Open License",
        "source policy",
        "import run",
        "storage state",
        "provenance",
        "audit",
        "persistence",
        "Campaign Item Mechanics",
    ):
        assert marker.casefold() not in visible
    expect(page.locator("main script")).to_have_count(0)
    expect(page.locator("main [onclick], main [onerror], main [onload]")).to_have_count(0)


def _assert_primary_semantics(
    page,
    *,
    expect_management: bool,
    primary_key: str,
) -> None:
    breadcrumb = page.locator('nav[aria-label="Systems breadcrumb"]')
    expect(breadcrumb.get_by_role("link", name="Systems", exact=True)).to_have_count(1)
    source_link = breadcrumb.get_by_role("link", name=SOURCE_TITLE, exact=True)
    category_link = breadcrumb.get_by_role(
        "link", name="Subclass Features", exact=True
    )
    expect(source_link).to_have_count(1)
    expect(category_link).to_have_count(1)
    assert source_link.get_attribute("href") == (
        f"/campaigns/linden-pass/systems/sources/{SOURCE_ID}"
    )
    assert category_link.get_attribute("href") == (
        f"/campaigns/linden-pass/systems/sources/{SOURCE_ID}"
        "/types/subclassfeature"
    )
    current = breadcrumb.locator('[aria-current="page"]')
    expect(current).to_have_text(PRIMARY_TITLE)
    expect(current.locator("a")).to_have_count(0)
    expect(page.get_by_role("heading", name=PRIMARY_TITLE, exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            f"A reference from {SOURCE_TITLE}, filed under Subclass Features.",
            exact=True,
        )
    ).to_be_visible()
    expect(page.locator(".page-layout > .article.card")).to_have_count(1)
    expect(page.get_by_role("heading", name="Related Rules References")).to_be_visible()
    expect(
        page.get_by_role("link", name="Spell Attacks and Save DCs", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("heading", name="Active Campaign Overlays")).to_be_visible()
    expect(
        page.get_by_role("link", name="Alpha Reader Detail", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_role("link", name="Zeta General Spark", exact=True)
    ).to_be_visible()
    article_text = page.locator(".article.card").inner_text()
    assert article_text.index("Alpha Reader Detail") < article_text.index(
        "Zeta General Spark"
    )
    assert "Campaign Overlay" in article_text
    assert "Reference-Only Overlay" in article_text
    assert (
        "This house rule stays visible beside the baseline links, but the app "
        "does not currently automate the change."
    ) in article_text
    assert "Applies To: Reader options" in article_text
    assert "Applies To: This entry." in article_text
    assert (
        "The Systems/RULES content above is the shared baseline for this campaign."
        in article_text
    )
    expect(page.locator(".page-layout form, .page-layout button")).to_have_count(0)
    if expect_management:
        expect(page.get_by_role("heading", name="Entry Management")).to_be_visible()
        override_link = page.get_by_role(
            "link", name="Manage campaign override", exact=True
        )
        expect(override_link).to_be_visible()
        override_query = parse_qs(urlsplit(override_link.get_attribute("href")).query)
        assert override_query["entry_key"] == [primary_key]
        assert primary_key not in page.locator("main").inner_text()
    else:
        expect(page.get_by_role("heading", name="Entry Management")).to_have_count(0)
        expect(
            page.get_by_role("link", name="Manage campaign override", exact=True)
        ).to_have_count(0)


def _assert_keyboard_path(page, label: str, *, expect_management: bool) -> None:
    page.locator("body").press("Home")
    page.keyboard.press("Tab")
    _assert_visible_focus(page.locator(".skip-link"), f"{label} skip link")
    page.keyboard.press("Enter")
    _assert_visible_focus(page.locator("#main-content"), f"{label} main content")

    targets = {
        "source": f"/campaigns/linden-pass/systems/sources/{SOURCE_ID}",
        "category": (
            f"/campaigns/linden-pass/systems/sources/{SOURCE_ID}"
            "/types/subclassfeature"
        ),
        "overlay": "/campaigns/linden-pass/pages/mechanics/alpha-reader-detail",
        "manager": "entry_key=",
    }
    seen: set[str] = set()
    disclosure_toggled = False
    for _ in range(120):
        page.keyboard.press("Tab")
        active = page.evaluate(
            """() => {
                const node = document.activeElement;
                return {
                    tag: node ? node.tagName.toLowerCase() : "",
                    href: node && node.getAttribute ? (node.getAttribute("href") || "") : "",
                    text: node ? node.textContent.trim() : "",
                };
            }"""
        )
        matched = None
        if active["href"] == targets["source"]:
            matched = "source"
        elif active["href"] == targets["category"]:
            matched = "category"
        elif (
            active["tag"] == "a"
            and active["text"] == "Spell Attacks and Save DCs"
        ):
            matched = "rules"
        elif active["href"] == targets["overlay"]:
            matched = "overlay"
        elif targets["manager"] in active["href"]:
            matched = "manager"
        elif active["tag"] == "summary" and "Open the lantern path" in active["text"]:
            matched = "disclosure"
            if not disclosure_toggled:
                page.keyboard.press("Enter")
                expect(page.locator(".systems-inline-option-card").first).to_have_attribute(
                    "open", ""
                )
                disclosure_toggled = True
        if matched:
            _assert_visible_focus(
                page.locator(":focus"), f"{label} {matched} keyboard target"
            )
            seen.add(matched)
        required = {"source", "category", "rules", "overlay", "disclosure"}
        if expect_management:
            required.add("manager")
        if required <= seen:
            break
    required = {"source", "category", "rules", "overlay", "disclosure"}
    if expect_management:
        required.add("manager")
    assert required <= seen, f"{label}: keyboard path missed {sorted(required - seen)}"


def test_systems_entry_detail_player_first_source_contract(
    app,
    client,
    sign_in,
    users,
) -> None:
    records = _seed_systems_entry_presentation_matrix(app, users)
    sign_in(users["party"]["email"], users["party"]["password"])

    primary = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['primary_slug']}?q=ignored"
    )
    empty = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['empty_slug']}"
    )
    rich = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['rich_slug']}"
    )
    book = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['book_slug']}"
    )
    widened = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['widened_slug']}"
    )

    assert all(
        response.status_code == 200
        for response in (primary, empty, rich, book, widened)
    )
    primary_html = primary.get_data(as_text=True)
    assert '<nav aria-label="Systems breadcrumb">' in primary_html
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{SOURCE_ID}"'
        ">Adventurer&#39;s Field Manual</a>"
    ) in primary_html
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{SOURCE_ID}/types/subclassfeature"'
        ">Subclass Features</a>"
    ) in primary_html
    assert '<span aria-current="page">Guiding Spark</span>' in primary_html
    assert "?q=" not in primary_html[
        primary_html.index('<nav aria-label="Systems breadcrumb">') :
        primary_html.index("</nav>", primary_html.index('<nav aria-label="Systems breadcrumb">'))
    ]
    assert '<div class="page-layout">\n    <section class="article card">' in primary_html
    assert primary_html.count("<h1>") == 1
    assert "Related Rules References" in primary_html
    assert "Active Campaign Overlays" in primary_html
    assert primary_html.index("Alpha Reader Detail") < primary_html.index(
        "Zeta General Spark"
    )
    assert "Applies To:</strong> Reader options" in primary_html
    assert "Applies To:</strong> This entry." in primary_html
    for marker in INTERNAL_MARKERS:
        assert marker not in primary_html
    for technical_inventory in (
        "Entry Metadata",
        "Entry key:",
        "Class Source:",
        "Policy default visibility:",
        "Existing Structured Hooks:",
        "Missing Metadata For True Base-Rule Modifiers:",
        "Open License",
        "Campaign Item Mechanics",
    ):
        assert technical_inventory not in primary_html

    empty_html = empty.get_data(as_text=True)
    assert '<section class="state-panel state-panel--empty"' in empty_html
    assert 'aria-labelledby="entry-empty-heading"' in empty_html
    assert '<h2 id="entry-empty-heading">No reference content available</h2>' in empty_html
    empty_fragment = empty_html[
        empty_html.index('<section class="state-panel state-panel--empty"') :
        empty_html.index("</section>", empty_html.index('<section class="state-panel state-panel--empty"'))
    ]
    assert 'role="status"' not in empty_fragment
    assert 'role="alert"' not in empty_fragment
    assert "aria-live=" not in empty_fragment
    assert records["primary_key"] not in empty_fragment
    assert "quiet-internal-identifier" not in empty_fragment
    assert "imported into" not in empty_fragment

    rich_html = rich.get_data(as_text=True)
    assert '<section id="safe-rich-reader">' in rich_html
    assert "<strong>Reader-safe emphasis.</strong>" in rich_html
    assert "<script>" not in rich_html
    assert "onclick=" not in rich_html

    book_html = book.get_data(as_text=True)
    assert "Chapter 4" in book_html
    assert "From Adventurer Guidance" in book_html
    assert "Starts on page 73" in book_html
    assert "At the Lantern Gate" in book_html
    assert "Policy default visibility:" not in book_html
    assert "Entry Metadata" not in book_html

    widened_html = widened.get_data(as_text=True)
    widened_breadcrumb = widened_html[
        widened_html.index('<nav aria-label="Systems breadcrumb">') :
        widened_html.index("</nav>", widened_html.index('<nav aria-label="Systems breadcrumb">'))
    ]
    assert "Keeper&#39;s Restricted Notes" in widened_breadcrumb
    assert ">Spells</span>" in widened_breadcrumb
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{WIDENED_SOURCE_ID}"'
        not in widened_breadcrumb
    )
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{WIDENED_SOURCE_ID}/types/spell"'
        not in widened_breadcrumb
    )

    with app.app_context():
        app.extensions["systems_store"].upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="RULES",
            is_enabled=True,
            default_visibility=VISIBILITY_DM,
        )
    hidden_rules = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['primary_slug']}"
    )
    assert hidden_rules.status_code == 200
    assert "Related Rules References" not in hidden_rules.get_data(as_text=True)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_rules = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['primary_slug']}"
    )
    assert dm_rules.status_code == 200
    assert "Related Rules References" in dm_rules.get_data(as_text=True)

    sign_in(users["admin"]["email"], users["admin"]["password"])
    disabled = client.get(
        f"/campaigns/linden-pass/systems/entries/{records['disabled_slug']}"
    )
    assert disabled.status_code == 200
    disabled_html = disabled.get_data(as_text=True)
    disabled_breadcrumb = disabled_html[
        disabled_html.index('<nav aria-label="Systems breadcrumb">') :
        disabled_html.index("</nav>", disabled_html.index('<nav aria-label="Systems breadcrumb">'))
    ]
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{DISABLED_SOURCE_ID}"'
        in disabled_breadcrumb
    )
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{DISABLED_SOURCE_ID}/types/rule"'
        not in disabled_breadcrumb
    )
    assert ">Rules</span>" in disabled_breadcrumb


def test_systems_entry_detail_real_chromium_matrix(
    app,
    users,
    systems_entry_presentation_live_server,
) -> None:
    records = _seed_systems_entry_presentation_matrix(app, users)
    base_url = systems_entry_presentation_live_server
    primary_url = (
        f"{base_url}/campaigns/linden-pass/systems/entries/"
        f"{records['primary_slug']}?q=ignored"
    )
    scenarios = (
        ("desktop js", {"width": 1280, "height": 900}, True),
        ("desktop no-js", {"width": 1280, "height": 900}, False),
        ("mobile js", {"width": 390, "height": 800}, True),
        ("mobile no-js", {"width": 390, "height": 800}, False),
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        contexts = []
        try:
            for label, viewport, java_script_enabled in scenarios:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                )
                contexts.append(context)
                page = context.new_page()
                _sign_in(page, base_url, users["party"])
                page.goto(primary_url)
                _wait_for_loading_cover(
                    page,
                    java_script_enabled=java_script_enabled,
                )
                _assert_primary_semantics(
                    page,
                    expect_management=False,
                    primary_key=records["primary_key"],
                )
                _assert_accessibility_integrity(page, label)
                _assert_no_internal_inventory(page)
                _assert_keyboard_path(page, label, expect_management=False)
                _assert_containment(page, label, expect_table=True)

                page.goto(
                    f"{base_url}/campaigns/linden-pass/systems/entries/"
                    f"{records['empty_slug']}"
                )
                _wait_for_loading_cover(
                    page,
                    java_script_enabled=java_script_enabled,
                )
                expect(
                    page.get_by_role("heading", name="No reference content available")
                ).to_be_visible()
                empty_panel = page.locator(".state-panel.state-panel--empty")
                expect(empty_panel).to_have_attribute(
                    "aria-labelledby", "entry-empty-heading"
                )
                expect(
                    empty_panel.locator("[role='status'], [role='alert'], [aria-live]")
                ).to_have_count(0)
                _assert_accessibility_integrity(page, f"{label} empty")
                _assert_containment(page, f"{label} empty", expect_table=False)

            dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
            contexts.append(dm_context)
            dm_page = dm_context.new_page()
            _sign_in(dm_page, base_url, users["dm"])
            dm_page.goto(
                f"{base_url}/campaigns/linden-pass/systems/entries/"
                f"{records['dm_slug']}"
            )
            _wait_for_loading_cover(dm_page, java_script_enabled=True)
            expect(dm_page.get_by_role("heading", name="DM Lantern")).to_be_visible()
            expect(
                dm_page.get_by_role("link", name="Manage campaign override", exact=True)
            ).to_be_visible()
            expect(
                dm_page.locator(".page-layout form, .page-layout button")
            ).to_have_count(0)
            _assert_accessibility_integrity(dm_page, "dm")
            _assert_containment(dm_page, "dm", expect_table=False)

            admin_context = browser.new_context(
                viewport={"width": 390, "height": 800},
                java_script_enabled=False,
            )
            contexts.append(admin_context)
            admin_page = admin_context.new_page()
            _sign_in(admin_page, base_url, users["admin"])
            admin_page.goto(
                f"{base_url}/campaigns/linden-pass/systems/entries/"
                f"{records['private_slug']}"
            )
            expect(
                admin_page.get_by_role("heading", name="Curator Lantern")
            ).to_be_visible()
            expect(
                admin_page.get_by_role("link", name="Manage campaign override", exact=True)
            ).to_be_visible()
            _assert_accessibility_integrity(admin_page, "direct admin")
            _assert_containment(admin_page, "direct admin", expect_table=False)

            admin_page.goto(
                f"{base_url}/campaigns/linden-pass/systems/entries/"
                f"{records['disabled_slug']}"
            )
            disabled_breadcrumb = admin_page.locator(
                'nav[aria-label="Systems breadcrumb"]'
            )
            expect(
                disabled_breadcrumb.get_by_role(
                    "link", name=DISABLED_SOURCE_TITLE, exact=True
                )
            ).to_have_count(1)
            expect(
                disabled_breadcrumb.get_by_role("link", name="Rules", exact=True)
            ).to_have_count(0)
            expect(disabled_breadcrumb.get_by_text("Rules", exact=True)).to_have_count(1)

            projected_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            contexts.append(projected_context)
            projected_page = projected_context.new_page()
            _sign_in(projected_page, base_url, users["admin"])
            view_as_party = projected_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["party"]["id"]},
            )
            assert view_as_party.ok
            projected_page.goto(primary_url)
            _wait_for_loading_cover(projected_page, java_script_enabled=True)
            _assert_primary_semantics(
                projected_page,
                expect_management=False,
                primary_key=records["primary_key"],
            )
            expect(
                projected_page.get_by_role(
                    "link", name="Manage campaign override", exact=True
                )
            ).to_have_count(0)

            view_as_dm = projected_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["dm"]["id"]},
            )
            assert view_as_dm.ok
            projected_page.set_viewport_size({"width": 390, "height": 800})
            projected_page.goto(
                f"{base_url}/campaigns/linden-pass/systems/entries/"
                f"{records['dm_slug']}"
            )
            _wait_for_loading_cover(projected_page, java_script_enabled=True)
            expect(
                projected_page.get_by_role("heading", name="DM Lantern")
            ).to_be_visible()
            expect(
                projected_page.get_by_role(
                    "link", name="Manage campaign override", exact=True
                )
            ).to_be_visible()
            expect(
                projected_page.locator(".page-layout form, .page-layout button")
            ).to_have_count(0)
            _assert_containment(
                projected_page,
                "admin view as dm mobile",
                expect_table=False,
            )

            anonymous_context = browser.new_context(
                viewport={"width": 390, "height": 800},
                java_script_enabled=False,
            )
            contexts.append(anonymous_context)
            anonymous_page = anonymous_context.new_page()
            response = anonymous_page.goto(primary_url)
            assert response is not None
            assert response.status == 200
            assert "/sign-in?next=" in anonymous_page.url
            expect(
                anonymous_page.get_by_role("heading", name="Sign in")
            ).to_be_visible()
            expect(
                anonymous_page.get_by_role("heading", name=PRIMARY_TITLE, exact=True)
            ).to_have_count(0)
            assert PRIMARY_TITLE not in anonymous_page.locator("main").inner_text()
        finally:
            for context in contexts:
                context.close()
            browser.close()
