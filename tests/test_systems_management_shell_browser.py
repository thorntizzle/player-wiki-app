from __future__ import annotations

import re
import threading
from uuid import uuid4

import pytest

from player_wiki.campaign_visibility import VISIBILITY_DM, VISIBILITY_PLAYERS


HOST_PATHS = (
    "/campaigns/linden-pass/systems/control-panel",
    "/campaigns/linden-pass/dm-content/systems",
)

LANE_HEADINGS = {
    "systems-source-enablement": "Source Enablement",
    "systems-shared-core-permission": "Shared/Core Editing",
    "systems-entry-overrides": "Entry Overrides",
    "systems-custom-entries": "Custom Entries",
    "systems-shared-imports": "Shared Source Imports",
    "systems-import-history": "Import-Run History",
}

PRIVATE_SOURCE_PATH = r"C:\private\management-shell\source-archive.zip"
RELATIVE_SOURCE_FILE = (
    "data/bestiary/"
    "management-shell-authorized-relative-file-"
    + ("very-long-segment-" * 12)
    + ".json"
)
INTERNAL_PLAYER_READ_MARKER = "PLAYER-READ-INVENTORY-MUST-STAY-ABSENT"


@pytest.fixture
def systems_management_shell_live_server(app):
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


def _sign_in(page, base_url: str, user: dict[str, object]) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(str(user["email"]))
    page.locator("input[name='password']").fill(str(user["password"]))
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _wait_for_page(page, *, java_script_enabled: bool) -> None:
    page.wait_for_load_state("load")
    if java_script_enabled:
        page.locator("html.app-loading, html.app-loading-closing").wait_for(
            state="detached",
            timeout=5000,
        )


def _seed_management_shell_matrix(app, users) -> None:
    source_id = f"SHELL-{uuid4().hex[:8].upper()}"
    entry_slug = "management-shell-long-entry"
    entry_key = (
        f"dnd-5e|rule|{source_id.casefold()}|{entry_slug}-"
        + ("long-key-segment-" * 12)
    )
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Management Shell Source " + ("Long Title " * 18),
            license_class="open_license",
            public_visibility_allowed=True,
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
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "rule",
                    "slug": entry_slug,
                    "title": "Management Shell Long Entry",
                    "search_text": "management shell long entry",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                }
            ],
            entry_types=["rule"],
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=entry_key,
            visibility_override=VISIBILITY_DM,
            is_enabled_override=False,
        )
        service.create_custom_campaign_entry(
            "linden-pass",
            title="Management Shell Custom Entry " + ("Long Form Value " * 8),
            entry_type="rule",
            slug_leaf="management-shell-custom-entry",
            visibility=VISIBILITY_PLAYERS,
            provenance="Authorized relative provenance " + ("long-field-value-" * 12),
            search_metadata="management shell browser containment",
            body_markdown="## Management shell\n\nBrowser containment record.",
            actor_user_id=users["dm"]["id"],
            can_set_private=False,
        )
        import_run = store.create_import_run(
            library_slug=library_slug,
            source_id=source_id,
            import_version="management-shell-browser-" + ("long-version-" * 10),
            source_path=PRIVATE_SOURCE_PATH,
            summary={},
        )
        store.complete_import_run(
            import_run.id,
            summary={
                "imported_count": 123,
                "imported_by_type": {"rule": 123},
                "source_files": [RELATIVE_SOURCE_FILE],
            },
        )


def _assert_no_management_inventory(page) -> None:
    markup = page.content()
    for marker in (
        'aria-label="Systems management tasks"',
        "Show or hide Source Enablement",
        'name="source_',
        " imported entries",
        "custom campaign entries",
        "recent shared-library run",
        "systems_import_archive",
        "shared-core-permission",
        'option value="private"',
        RELATIVE_SOURCE_FILE,
        PRIVATE_SOURCE_PATH,
    ):
        assert marker not in markup


def _assert_containment(page, label: str) -> None:
    viewport_width = page.viewport_size["width"]
    document_width = page.evaluate(
        "() => (document.scrollingElement || document.documentElement).scrollWidth"
    )
    assert document_width <= viewport_width, f"{label}: document overflow"
    for selector in (
        ".page-shell",
        "main.main-content",
        ".page-layout",
        ".section-list",
        ".systems-management-task-nav",
        "details.systems-management-lane",
        "details.systems-management-lane > summary",
        "details.systems-management-lane form",
        "details.systems-management-lane input",
        "details.systems-management-lane select",
        "details.systems-management-lane textarea",
        "details.systems-management-lane button",
        "#systems-entry-overrides .meta",
        "#systems-import-history .meta",
    ):
        locator = page.locator(selector)
        for index in range(locator.count()):
            node = locator.nth(index)
            if not node.is_visible():
                continue
            box = node.bounding_box()
            assert box is not None
            assert box["x"] >= -1, f"{label}: {selector}[{index}] starts outside"
            assert box["x"] + box["width"] <= viewport_width + 1, (
                f"{label}: {selector}[{index}] extends outside"
            )


def _assert_skip_link_and_visible_focus(page, expect) -> None:
    page.locator("body").press("Home")
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main-content")).to_be_focused()
    assert (
        page.locator("#main-content").evaluate(
            "element => parseFloat(getComputedStyle(element).outlineWidth)"
        )
        > 0
    )

    summary = page.locator("#systems-source-enablement > summary")
    summary.focus()
    expect(summary).to_be_focused()
    assert (
        summary.evaluate(
            "element => parseFloat(getComputedStyle(element).outlineWidth)"
        )
        > 0
    )


def _assert_summary_control_order(page, expect) -> None:
    source_lane = page.locator("#systems-source-enablement")
    source_summary = source_lane.locator(":scope > summary")
    source_controls = source_lane.locator(
        "input:not([type='hidden']):not([disabled]), "
        "select:not([disabled]), textarea:not([disabled]), button:not([disabled])"
    )
    next_summary = page.locator("#systems-shared-core-permission > summary")
    assert source_controls.count() > 0

    source_summary.focus()
    page.keyboard.press("Tab")
    expect(source_controls.first).to_be_focused()
    for _index in range(1, source_controls.count()):
        page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    expect(next_summary).to_be_focused()


def _assert_native_toggle_and_nested_independence(page, expect) -> None:
    source_lane = page.locator("#systems-source-enablement")
    source_summary = source_lane.locator(":scope > summary")
    source_summary.focus()
    source_summary.press("Enter")
    expect(source_lane).not_to_have_attribute("open", "")
    source_summary.press("Space")
    expect(source_lane).to_have_attribute("open", "")

    history_lane = page.locator("#systems-import-history")
    nested = history_lane.locator("details.feature-detail")
    expect(nested).to_have_count(1)
    nested_summary = nested.locator(":scope > summary")
    nested_summary.focus()
    nested_summary.press("Enter")
    expect(nested).to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")
    nested_summary.press("Space")
    expect(nested).not_to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")


def _assert_management_shell(
    page,
    expect,
    *,
    host_path: str,
    label: str,
) -> None:
    nav = page.locator('nav[aria-label="Systems management tasks"]')
    expect(nav).to_have_count(1)
    expect(nav.locator("a")).to_have_count(6)
    lanes = page.locator("details.systems-management-lane")
    expect(lanes).to_have_count(6)
    for lane_id, heading in LANE_HEADINGS.items():
        lane = page.locator(f"#{lane_id}")
        expect(lane).to_have_count(1)
        expect(lane).to_have_attribute("open", "")
        expect(lane.locator(":scope > summary")).to_have_text(
            f"Show or hide {heading}"
        )
        expect(lane.locator(":scope h2", has_text=heading)).to_have_count(1)

    native_aria = page.locator("details[aria-expanded], details[aria-controls], "
                               "summary[aria-expanded], summary[aria-controls]")
    expect(native_aria).to_have_count(0)
    duplicate_ids = page.evaluate(
        """() => {
            const ids = [...document.querySelectorAll("[id]")].map(node => node.id);
            return ids.filter((id, index) => ids.indexOf(id) !== index);
        }"""
    )
    assert duplicate_ids == []

    visible_unlabelled_fields = page.locator(
        "details.systems-management-lane input:not([type='hidden']), "
        "details.systems-management-lane select, "
        "details.systems-management-lane textarea"
    ).evaluate_all(
        """elements => elements
            .filter(element => element.getClientRects().length)
            .filter(element => !element.labels?.length)
            .filter(element => !element.getAttribute("aria-label"))
            .map(element => `${element.tagName}:${element.name}`)"""
    )
    assert visible_unlabelled_fields == []

    markup = page.content()
    assert PRIVATE_SOURCE_PATH not in markup
    assert RELATIVE_SOURCE_FILE in markup
    assert INTERNAL_PLAYER_READ_MARKER not in markup
    assert "Campaign Item Mechanics" not in markup
    assert "/systems/item-mechanics/import" not in markup
    assert 'name="systems_import_archive"' not in markup
    assert (
        'action="/campaigns/linden-pass/systems/control-panel/'
        'shared-core-permission"'
    ) not in markup
    assert '<option value="private">' not in markup

    if host_path.endswith("/dm-content/systems"):
        expect(page.locator('nav[aria-label="DM Content subpages"]')).to_have_count(1)
        expect(page.locator("main h1")).to_have_text("DM Content")
    else:
        expect(page.get_by_role("heading", name="Authoring Model", exact=True)).to_be_visible()
        expect(page.locator("main h1")).to_have_text("Systems Settings")
    expect(page.locator(".page-layout > aside.sidebar")).to_have_count(1)

    _assert_skip_link_and_visible_focus(page, expect)
    _assert_summary_control_order(page, expect)
    _assert_native_toggle_and_nested_independence(page, expect)
    _assert_containment(page, label)


def _assert_fragment_target(page, expect, target_url: str) -> None:
    page.goto(f"{target_url}#systems-custom-entries")
    page.wait_for_load_state("load")
    assert page.evaluate("() => window.location.hash") == "#systems-custom-entries"
    target = page.locator("#systems-custom-entries")
    expect(target).to_have_attribute("open", "")
    box = target.bounding_box()
    assert box is not None
    assert box["y"] < page.viewport_size["height"]
    expect(target.get_by_role("heading", name="Custom Entries", exact=True)).to_be_visible()


def _assert_representative_prg_target(page, expect, target_url: str) -> None:
    page.goto(target_url)
    page.wait_for_load_state("load")
    custom_lane = page.locator("#systems-custom-entries")
    action = custom_lane.get_by_role(
        "button",
        name=re.compile(r"^(Archive|Restore)$"),
    ).first
    with page.expect_navigation():
        action.click()
    fragment = page.url.rsplit("#", 1)[-1]
    assert fragment.startswith("systems-custom-entry-")
    expect(custom_lane).to_have_attribute("open", "")
    expect(page.locator(f"#{fragment}")).to_be_visible()


def test_systems_management_shell_real_chromium_matrix(
    app,
    systems_management_shell_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

    _seed_management_shell_matrix(app, users)
    base_url = systems_management_shell_live_server
    modes = (
        ("desktop JS", {"width": 1280, "height": 900}, True),
        ("mobile JS", {"width": 390, "height": 800}, True),
        ("desktop no-JS", {"width": 1280, "height": 900}, False),
        ("mobile no-JS", {"width": 390, "height": 800}, False),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.fail(f"Playwright browser unavailable: {exc}")
        try:
            for mode_label, viewport, java_script_enabled in modes:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                )
                page = context.new_page()
                try:
                    _sign_in(page, base_url, users["dm"])
                    for host_path in HOST_PATHS:
                        target_url = f"{base_url}{host_path}"
                        page.goto(target_url)
                        _wait_for_page(
                            page,
                            java_script_enabled=java_script_enabled,
                        )
                        _assert_management_shell(
                            page,
                            expect,
                            host_path=host_path,
                            label=f"{host_path} {mode_label}",
                        )
                        _assert_fragment_target(page, expect, target_url)
                        if (
                            mode_label in {"desktop JS", "mobile no-JS"}
                        ):
                            _assert_representative_prg_target(
                                page,
                                expect,
                                target_url,
                            )
                finally:
                    page.close()
                    context.close()
        finally:
            browser.close()


def test_systems_management_shell_effective_actor_privacy_real_chromium(
    app,
    systems_management_shell_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

    _seed_management_shell_matrix(app, users)
    base_url = systems_management_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.fail(f"Playwright browser unavailable: {exc}")
        contexts = []
        try:
            anonymous_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            contexts.append(anonymous_context)
            anonymous_page = anonymous_context.new_page()
            for host_path in HOST_PATHS:
                anonymous_page.goto(f"{base_url}{host_path}")
                _assert_no_management_inventory(anonymous_page)

            player_context = browser.new_context(
                viewport={"width": 390, "height": 800}
            )
            contexts.append(player_context)
            player_page = player_context.new_page()
            _sign_in(player_page, base_url, users["party"])
            for host_path in HOST_PATHS:
                response = player_page.goto(f"{base_url}{host_path}")
                assert response is not None and response.status in {403, 404}
                _assert_no_management_inventory(player_page)

            projected_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            contexts.append(projected_context)
            projected_page = projected_context.new_page()
            _sign_in(projected_page, base_url, users["admin"])
            view_as_player = projected_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["party"]["id"]},
            )
            assert view_as_player.ok
            for host_path in HOST_PATHS:
                response = projected_page.goto(f"{base_url}{host_path}")
                assert response is not None and response.status in {403, 404}
                _assert_no_management_inventory(projected_page)

            view_as_dm = projected_context.request.post(
                f"{base_url}/api/v1/me/view-as",
                data={"user_id": users["dm"]["id"]},
            )
            assert view_as_dm.ok
            for host_path in HOST_PATHS:
                projected_page.goto(f"{base_url}{host_path}")
                expect(
                    projected_page.locator(
                        'nav[aria-label="Systems management tasks"]'
                    )
                ).to_have_count(1)
                markup = projected_page.content()
                assert 'name="systems_import_archive"' not in markup
                assert (
                    'action="/campaigns/linden-pass/systems/control-panel/'
                    'shared-core-permission"'
                ) not in markup
                assert '<option value="private">' not in markup

            admin_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            contexts.append(admin_context)
            admin_page = admin_context.new_page()
            _sign_in(admin_page, base_url, users["admin"])
            for host_path in HOST_PATHS:
                admin_page.goto(f"{base_url}{host_path}")
                markup = admin_page.content()
                assert 'name="systems_import_archive"' in markup
                assert (
                    'action="/campaigns/linden-pass/systems/control-panel/'
                    'shared-core-permission"'
                ) in markup
                assert '<option value="private">' in markup
                assert PRIVATE_SOURCE_PATH not in markup
                assert "/systems/item-mechanics/import" not in markup
        finally:
            for context in reversed(contexts):
                context.close()
            browser.close()
