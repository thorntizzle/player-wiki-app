from __future__ import annotations

import os
import re
import threading
from pathlib import Path
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


def _seed_management_shell_matrix(app, users) -> str:
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
        custom_entry = service.create_custom_campaign_entry(
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
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=custom_entry.entry_key,
            visibility_override=VISIBILITY_PLAYERS,
            is_enabled_override=False,
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
    return entry_key


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
        "#systems-custom-entries .meta",
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
    if source_lane.get_attribute("open") is None:
        source_summary.press("Enter")
    expect(source_lane).to_have_attribute("open", "")
    control_names = source_controls.evaluate_all(
        """elements => elements.map(element =>
            element.name || `${element.tagName.toLowerCase()}:${element.type || ""}`
        )"""
    )
    assert any(
        name.startswith("source_") and name.endswith("_enabled")
        for name in control_names
    )
    assert any(
        name.startswith("source_") and name.endswith("_visibility")
        for name in control_names
    )
    assert "acknowledge_proprietary" in control_names
    assert "button:submit" in control_names

    page.keyboard.press("Tab")
    expect(source_controls.first).to_be_focused()
    for _index in range(1, source_controls.count()):
        page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    expect(next_summary).to_be_focused()


def _assert_entry_override_control_order(page, expect) -> None:
    lane = page.locator("#systems-entry-overrides")
    summary = lane.locator(":scope > summary")
    entry_key = lane.locator('input[name="entry_key"]')
    visibility = lane.locator('select[name="visibility_override"]')
    enablement = lane.locator('select[name="is_enabled_override"]')
    save = lane.get_by_role("button", name="Save entry override")
    next_summary = page.locator("#systems-custom-entries > summary")

    summary.focus()
    expect(summary).to_be_focused()
    if lane.get_attribute("open") is None:
        summary.press("Enter")
    expect(lane).to_have_attribute("open", "")
    summary.press("Tab")
    expect(entry_key).to_be_focused()
    entry_key.press("Tab")
    expect(visibility).to_be_focused()
    visibility.press("Tab")
    expect(enablement).to_be_focused()
    enablement.press("Tab")
    expect(save).to_be_focused()
    save.press("Tab")
    expect(next_summary).to_be_focused()


def _assert_custom_entry_idle_fragment_target(page, expect, target_url: str) -> None:
    page.goto(target_url)
    page.wait_for_load_state("load")
    lane = page.locator("#systems-custom-entries")
    expect(lane).not_to_have_attribute("open", "")
    page.locator(
        'nav[aria-label="Systems management tasks"] '
        'a[href="#systems-custom-entries"]'
    ).click()
    assert page.evaluate("() => window.location.hash") == "#systems-custom-entries"
    expect(lane).not_to_have_attribute("open", "")
    summary = lane.locator(":scope > summary")
    box = summary.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] < page.viewport_size["height"]
    summary.focus()
    expect(summary).to_be_focused()
    summary.press("Enter")
    expect(lane).to_have_attribute("open", "")
    summary.press("Space")
    expect(lane).not_to_have_attribute("open", "")


def _assert_custom_entry_control_order(page, expect) -> None:
    lane = page.locator("#systems-custom-entries")
    summary = lane.locator(":scope > summary")
    title = lane.locator('input[name="custom_entry_title"]')
    slug = lane.locator('input[name="custom_entry_slug"]')
    entry_type = lane.locator('select[name="custom_entry_type"]')
    visibility = lane.locator('select[name="custom_entry_visibility"]')
    provenance = lane.locator('input[name="custom_entry_provenance"]')
    metadata = lane.locator('textarea[name="custom_entry_search_metadata"]')
    body = lane.locator('textarea[name="custom_entry_body_markdown"]')
    save = lane.get_by_role("button", name="Create custom entry")
    next_summary = page.locator("#systems-shared-imports > summary")

    summary.focus()
    expect(summary).to_be_focused()
    if lane.get_attribute("open") is None:
        summary.press("Enter")
    expect(lane).to_have_attribute("open", "")
    for control in (title, slug, entry_type, visibility, provenance, metadata, body, save):
        summary.press("Tab")
        expect(control).to_be_focused()
        summary = control
    save.press("Tab")
    expect(next_summary).to_be_focused()


def _assert_custom_entry_lifecycle(
    page,
    expect,
    *,
    target_url: str,
    host_path: str,
    label: str,
    java_script_enabled: bool,
) -> None:
    slug_leaf = f"browser-custom-{uuid4().hex[:8]}"
    entry_slug = f"custom-linden-pass-{slug_leaf}"
    entry_anchor = f"#systems-custom-entry-{entry_slug}"
    expected_target = f"{target_url}{entry_anchor}"
    lane = page.locator("#systems-custom-entries")

    expect(lane).to_have_attribute("open", "")
    title = lane.locator('input[name="custom_entry_title"]')
    slug = lane.locator('input[name="custom_entry_slug"]')
    body = lane.locator('textarea[name="custom_entry_body_markdown"]')
    title.fill("   ")
    body.fill("Browser-retained invalid custom body.")
    with page.expect_navigation() as validation_navigation:
        lane.get_by_role("button", name="Create custom entry").click()
    validation_response = validation_navigation.value
    assert validation_response is not None
    assert validation_response.status == 400
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    lane = page.locator("#systems-custom-entries")
    expect(lane).to_have_attribute("open", "")
    expect(page.locator(".flash-error")).to_contain_text(
        "Choose a URL slug or title before saving a custom Systems entry."
    )
    expect(lane.locator('input[name="custom_entry_title"]')).to_have_value("   ")
    expect(
        lane.locator('textarea[name="custom_entry_body_markdown"]')
    ).to_have_value("Browser-retained invalid custom body.")
    _assert_containment(page, f"{label} custom validation 400")

    title = lane.locator('input[name="custom_entry_title"]')
    slug = lane.locator('input[name="custom_entry_slug"]')
    body = lane.locator('textarea[name="custom_entry_body_markdown"]')
    title.fill("Browser Custom Entry")
    slug.fill(slug_leaf)
    body.fill("Browser custom entry body.")
    with page.expect_navigation() as create_navigation:
        lane.get_by_role("button", name="Create custom entry").click()
    create_response = create_navigation.value
    assert create_response is not None
    assert create_response.status == 200
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    assert page.url == expected_target
    lane = page.locator("#systems-custom-entries")
    expect(lane).to_have_attribute("open", "")
    entry = page.locator(f"#systems-custom-entry-{entry_slug}")
    expect(entry).to_contain_text("Browser Custom Entry")
    _assert_containment(page, f"{label} custom create PRG")

    with page.expect_navigation() as archive_navigation:
        entry.get_by_role("button", name="Archive").click()
    archive_response = archive_navigation.value
    assert archive_response is not None
    assert archive_response.status == 200
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    assert page.url == expected_target
    entry = page.locator(f"#systems-custom-entry-{entry_slug}")
    expect(entry).to_contain_text("Archived")
    expect(entry.get_by_role("button", name="Restore")).to_have_count(1)
    expect(page.locator("#systems-custom-entries")).to_have_attribute("open", "")

    with page.expect_navigation() as restore_navigation:
        entry.get_by_role("button", name="Restore").click()
    restore_response = restore_navigation.value
    assert restore_response is not None
    assert restore_response.status == 200
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    assert page.url == expected_target
    entry = page.locator(f"#systems-custom-entry-{entry_slug}")
    expect(entry).to_contain_text("Active")
    expect(entry.get_by_role("button", name="Archive")).to_have_count(1)

    with page.expect_navigation() as edit_navigation:
        entry.get_by_role("link", name="Edit").click()
    edit_response = edit_navigation.value
    assert edit_response is not None
    assert edit_response.status == 200
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    lane = page.locator("#systems-custom-entries")
    expect(lane).to_have_attribute("open", "")
    expect(lane.locator('input[name="custom_entry_title"]')).to_have_value(
        "Browser Custom Entry"
    )
    expect(lane.locator('input[name="custom_entry_slug"]')).to_have_count(0)
    assert page.url.endswith("#systems-custom-entry-editor")

    title = lane.locator('input[name="custom_entry_title"]')
    body = lane.locator('textarea[name="custom_entry_body_markdown"]')
    title.fill("Browser Custom Entry Revised")
    body.fill("Browser custom entry revised body.")
    with page.expect_navigation() as update_navigation:
        lane.get_by_role("button", name="Update custom entry").click()
    update_response = update_navigation.value
    assert update_response is not None
    assert update_response.status == 200
    _wait_for_page(page, java_script_enabled=java_script_enabled)
    assert page.url == expected_target
    entry = page.locator(f"#systems-custom-entry-{entry_slug}")
    expect(entry).to_contain_text("Browser Custom Entry Revised")
    expect(page.locator("#systems-custom-entries")).to_have_attribute("open", "")
    _assert_containment(page, f"{label} custom lifecycle")

    return_fields = page.locator(
        '#systems-custom-entries input[name="return_to"]'
    )
    if host_path.endswith("/dm-content/systems"):
        assert return_fields.count() >= 2
        assert return_fields.evaluate_all(
            "elements => elements.every(element => element.value === 'dm-content-systems')"
        )
    else:
        expect(return_fields).to_have_count(0)


def _assert_native_toggle_and_nested_independence(
    page,
    expect,
    *,
    nested_history_expected: bool,
) -> None:
    source_lane = page.locator("#systems-source-enablement")
    source_summary = source_lane.locator(":scope > summary")
    source_summary.focus()
    source_summary.press("Enter")
    expect(source_lane).not_to_have_attribute("open", "")
    source_summary.press("Space")
    expect(source_lane).to_have_attribute("open", "")
    source_summary.press("Enter")
    expect(source_lane).not_to_have_attribute("open", "")

    history_lane = page.locator("#systems-import-history")
    nested = history_lane.locator("details.feature-detail")
    if not nested_history_expected:
        expect(nested).to_have_count(0)
        return
    expect(nested).to_have_count(1)
    nested_summary = nested.locator(":scope > summary")
    nested_summary.focus()
    nested_summary.press("Enter")
    expect(nested).to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")
    nested_summary.press("Space")
    expect(nested).not_to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")


def _capture_browser_evidence(page, *, label: str, state: str) -> None:
    evidence_root = os.environ.get("SYSTEMS_MANAGEMENT_BROWSER_EVIDENCE_DIR")
    if not evidence_root:
        return
    path = Path(evidence_root)
    path.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^a-z0-9]+", "-", f"{label}-{state}".casefold()).strip("-")
    page.screenshot(path=str(path / f"{filename}.png"), full_page=True)


def _assert_shared_import_details_validation(
    page,
    expect,
    *,
    host_path: str,
    label: str,
    java_script_enabled: bool,
) -> None:
    imports_lane = page.locator("#systems-shared-imports")
    imports_summary = imports_lane.locator(":scope > summary")
    history_lane = page.locator("#systems-import-history")
    history_summary = history_lane.locator(":scope > summary")

    expect(imports_lane).not_to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")
    assert PRIVATE_SOURCE_PATH not in page.content()
    _capture_browser_evidence(page, label=label, state="normal-get")

    imports_summary.focus()
    expect(imports_summary).to_be_focused()
    assert (
        imports_summary.evaluate(
            "element => parseFloat(getComputedStyle(element).outlineWidth)"
        )
        > 0
    )
    imports_summary.press("Enter")
    expect(imports_lane).to_have_attribute("open", "")
    controls = imports_lane.locator(
        "input:not([type='hidden']):not([disabled]), "
        "select:not([disabled]), textarea:not([disabled]), button:not([disabled])"
    )
    assert controls.count() > 0
    imports_summary.press("Tab")
    expect(controls.first).to_be_focused()
    for index in range(1, controls.count()):
        controls.nth(index - 1).press("Tab")
        expect(controls.nth(index)).to_be_focused()
    controls.last.press("Tab")
    expect(history_summary).to_be_focused()

    imports_lane.locator('input[name="import_version"]').fill(
        " retained-browser-label "
    )
    imports_lane.locator('input[name="source_ids"][value="MM"]').check()
    imports_lane.locator('input[name="entry_types"][value="monster"]').check()
    archive = imports_lane.locator('input[name="systems_import_archive"]')
    archive.set_input_files(
        {
            "name": "shared-import-validation-must-not-be-retained.zip",
            "mimeType": "application/zip",
            "buffer": b"not-a-zip",
        }
    )
    expect(archive).to_have_value(
        re.compile(r"shared-import-validation-must-not-be-retained\.zip$")
    )
    with page.expect_navigation() as validation_navigation:
        imports_lane.get_by_role("button", name="Import selected sources").click()
    validation_response = validation_navigation.value
    assert validation_response is not None
    assert validation_response.status == 400
    _wait_for_page(page, java_script_enabled=java_script_enabled)

    imports_lane = page.locator("#systems-shared-imports")
    history_lane = page.locator("#systems-import-history")
    expect(imports_lane).to_have_attribute("open", "")
    expect(history_lane).to_have_attribute("open", "")
    expect(page.locator(".flash-error")).to_contain_text(
        "Import archive must be a valid supported ZIP file."
    )
    expect(imports_lane.locator('input[name="import_version"]')).to_have_value(
        "retained-browser-label"
    )
    expect(
        imports_lane.locator('input[name="source_ids"][value="MM"]')
    ).to_be_checked()
    expect(
        imports_lane.locator('input[name="entry_types"][value="monster"]')
    ).to_be_checked()
    expect(
        imports_lane.locator('input[name="systems_import_archive"]')
    ).to_have_value("")
    validation_markup = page.content()
    assert "shared-import-validation-must-not-be-retained.zip" not in validation_markup
    assert PRIVATE_SOURCE_PATH not in validation_markup
    _assert_containment(page, f"{label} import validation 400")
    _capture_browser_evidence(page, label=label, state="validation-post")

    if host_path.endswith("/dm-content/systems"):
        expect(page.locator("main h1")).to_have_text("DM Content")
    else:
        expect(page.locator("main h1")).to_have_text("Systems Settings")


def _assert_management_shell(
    page,
    expect,
    *,
    host_path: str,
    label: str,
    source_open: bool,
    entry_override_open: bool,
    custom_entries_open: bool,
    shared_imports_open: bool = False,
    seeded: bool = True,
) -> None:
    nav = page.locator('nav[aria-label="Systems management tasks"]')
    expect(nav).to_have_count(1)
    expect(nav.locator("a")).to_have_count(6)
    lanes = page.locator("details.systems-management-lane")
    expect(lanes).to_have_count(6)
    for lane_id, heading in LANE_HEADINGS.items():
        lane = page.locator(f"#{lane_id}")
        expect(lane).to_have_count(1)
        if lane_id == "systems-source-enablement" and not source_open:
            expect(lane).not_to_have_attribute("open", "")
        elif lane_id == "systems-entry-overrides" and not entry_override_open:
            expect(lane).not_to_have_attribute("open", "")
        elif lane_id == "systems-custom-entries" and not custom_entries_open:
            expect(lane).not_to_have_attribute("open", "")
        elif lane_id == "systems-shared-imports" and not shared_imports_open:
            expect(lane).not_to_have_attribute("open", "")
        else:
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
    if seeded:
        assert RELATIVE_SOURCE_FILE in markup
    else:
        assert RELATIVE_SOURCE_FILE not in markup
    assert INTERNAL_PLAYER_READ_MARKER not in markup
    assert "Proprietary-source acknowledgement:" in markup
    assert "Proprietary - private campaign use" in markup
    assert "restricted from public visibility by policy" in markup
    assert (
        "I understand proprietary systems sources are for private campaign use "
        "only and must not be made public or redistributed."
    ) in " ".join(markup.split())
    assert "source_path" not in markup
    assert "audit_state" not in markup
    assert "storage_state" not in markup
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
    _assert_entry_override_control_order(page, expect)
    if not custom_entries_open:
        _assert_custom_entry_control_order(page, expect)
    _assert_containment(page, label)
    _assert_native_toggle_and_nested_independence(
        page,
        expect,
        nested_history_expected=seeded,
    )


def _assert_entry_override_default_prefill_fragment_and_validation(
    page,
    expect,
    *,
    target_url: str,
    host_path: str,
    label: str,
) -> None:
    page.goto(f"{target_url}?systems_entry_override_validation_active=1")
    page.wait_for_load_state("load")
    entry_lane = page.locator("#systems-entry-overrides")
    expect(entry_lane).not_to_have_attribute("open", "")

    prefill_key = 'spell::<browser-prefill>&"quoted"'
    encoded_prefill = "spell%3A%3A%3Cbrowser-prefill%3E%26%22quoted%22"
    page.goto(f"{target_url}?entry_key={encoded_prefill}")
    page.wait_for_load_state("load")
    entry_lane = page.locator("#systems-entry-overrides")
    expect(entry_lane).to_have_attribute("open", "")
    expect(entry_lane.locator('input[name="entry_key"]')).to_have_value(
        prefill_key
    )
    expect(
        entry_lane.locator('select[name="visibility_override"]')
    ).to_have_value("")
    expect(
        entry_lane.locator('select[name="is_enabled_override"]')
    ).to_have_value("")

    page.goto(target_url)
    page.wait_for_load_state("load")
    entry_lane = page.locator("#systems-entry-overrides")
    expect(entry_lane).not_to_have_attribute("open", "")
    page.locator(
        'nav[aria-label="Systems management tasks"] '
        'a[href="#systems-entry-overrides"]'
    ).click()
    assert page.evaluate("() => window.location.hash") == "#systems-entry-overrides"
    expect(entry_lane).not_to_have_attribute("open", "")
    summary = entry_lane.locator(":scope > summary")
    box = summary.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] < page.viewport_size["height"]
    expect(summary).to_be_visible()
    summary.focus()
    summary.press("Enter")
    expect(entry_lane).to_have_attribute("open", "")
    summary.press("Space")
    expect(entry_lane).not_to_have_attribute("open", "")

    summary.press("Enter")
    invalid_key = "missing-browser-entry-that-must-be-lost"
    entry_lane.locator('input[name="entry_key"]').fill(invalid_key)
    entry_lane.locator('select[name="visibility_override"]').select_option(
        VISIBILITY_DM
    )
    entry_lane.locator('select[name="is_enabled_override"]').select_option(
        "disabled"
    )
    with page.expect_navigation() as validation_navigation:
        entry_lane.get_by_role(
            "button",
            name="Save entry override",
        ).click()
    validation_response = validation_navigation.value
    assert validation_response is not None
    assert validation_response.status == 400
    entry_lane = page.locator("#systems-entry-overrides")
    expect(entry_lane).to_have_attribute("open", "")
    expect(page.locator(".flash-error")).to_contain_text(
        "Choose a valid systems entry"
    )
    expect(entry_lane.locator('input[name="entry_key"]')).to_have_value("")
    expect(
        entry_lane.locator('select[name="visibility_override"]')
    ).to_have_value("")
    expect(
        entry_lane.locator('select[name="is_enabled_override"]')
    ).to_have_value("")
    assert invalid_key not in page.content()
    return_fields = entry_lane.locator('input[name="return_to"]')
    if host_path.endswith("/dm-content/systems"):
        expect(return_fields).to_have_count(1)
        expect(return_fields).to_have_value("dm-content-systems")
        expect(page.locator("main h1")).to_have_text("DM Content")
    else:
        expect(return_fields).to_have_count(0)
        expect(page.locator("main h1")).to_have_text("Systems Settings")
    expect(page.locator("#systems-source-enablement")).not_to_have_attribute(
        "open",
        "",
    )
    _assert_containment(page, f"{label} entry validation 400")


def _assert_source_fragment_target(page, expect, target_url: str) -> None:
    page.goto(target_url)
    page.wait_for_load_state("load")
    source_lane = page.locator("#systems-source-enablement")
    expect(source_lane).not_to_have_attribute("open", "")
    page.locator(
        'nav[aria-label="Systems management tasks"] '
        'a[href="#systems-source-enablement"]'
    ).click()
    assert page.evaluate("() => window.location.hash") == "#systems-source-enablement"
    expect(source_lane).not_to_have_attribute("open", "")
    summary = source_lane.locator(":scope > summary")
    box = summary.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] < page.viewport_size["height"]
    expect(summary).to_be_visible()
    summary.focus()
    summary.press("Enter")
    expect(source_lane).to_have_attribute("open", "")
    summary.press("Space")
    expect(source_lane).not_to_have_attribute("open", "")


def _assert_source_prg_and_validation(
    page,
    expect,
    *,
    target_url: str,
    host_path: str,
    label: str,
) -> None:
    page.goto(target_url)
    page.wait_for_load_state("load")
    source_lane = page.locator("#systems-source-enablement")
    source_summary = source_lane.locator(":scope > summary")
    expect(source_lane).not_to_have_attribute("open", "")
    source_summary.click()
    expect(source_lane).to_have_attribute("open", "")

    enabled_checkboxes = source_lane.locator(
        'input[name^="source_"][name$="_enabled"]'
    )
    assert enabled_checkboxes.count() > 0
    for index in range(enabled_checkboxes.count()):
        checkbox = enabled_checkboxes.nth(index)
        if checkbox.is_checked():
            checkbox.uncheck()

    expected_target = (
        f"{target_url}#systems-source-enablement"
        if host_path.endswith("/dm-content/systems")
        else target_url
    )
    with page.expect_navigation():
        source_lane.get_by_role("button", name="Save systems sources").click()
    assert page.url == expected_target
    expect(page.locator("#systems-source-enablement")).to_have_attribute("open", "")
    for lane_id in set(LANE_HEADINGS) - {"systems-source-enablement"}:
        lane = page.locator(f"#{lane_id}")
        if lane_id == "systems-shared-imports":
            expect(lane).not_to_have_attribute("open", "")
        else:
            expect(lane).to_have_attribute("open", "")

    with page.expect_navigation():
        page.locator("#systems-source-enablement").get_by_role(
            "button",
            name="Save systems sources",
        ).click()
    assert page.url == expected_target
    expect(page.locator("#systems-source-enablement")).to_have_attribute("open", "")

    first_enabled_checkbox = page.locator(
        '#systems-source-enablement input[name^="source_"][name$="_enabled"]'
    ).first
    first_enabled_checkbox.check()
    with page.expect_navigation():
        page.locator("#systems-source-enablement").get_by_role(
            "button",
            name="Save systems sources",
        ).click()
    assert page.url == expected_target
    expect(page.locator("#systems-source-enablement")).not_to_have_attribute("open", "")

    source_summary = page.locator("#systems-source-enablement > summary")
    source_summary.click()
    phb_checkbox = page.locator(
        '#systems-source-enablement input[name="source_PHB_enabled"]'
    )
    phb_visibility = page.locator(
        '#systems-source-enablement select[name="source_PHB_visibility"]'
    )
    phb_checkbox.check()
    phb_visibility.locator('option[value="public"]').evaluate(
        "option => { option.disabled = false; }"
    )
    phb_visibility.select_option("public")
    with page.expect_navigation() as validation_navigation:
        page.locator("#systems-source-enablement").get_by_role(
            "button",
            name="Save systems sources",
        ).click()
    validation_response = validation_navigation.value
    assert validation_response is not None
    assert validation_response.status == 400
    expect(page.locator(".flash-error")).to_contain_text("cannot be made public")
    expect(page.locator("#systems-source-enablement")).to_have_attribute("open", "")
    expect(
        page.locator(
            '#systems-source-enablement input[name="source_PHB_enabled"]'
        )
    ).not_to_be_checked()
    expect(
        page.locator(
            '#systems-source-enablement select[name="source_PHB_visibility"]'
        )
    ).to_have_value("players")
    return_fields = page.locator(
        '#systems-source-enablement input[name="return_to"]'
    )
    if host_path.endswith("/dm-content/systems"):
        expect(return_fields).to_have_count(1)
        expect(return_fields).to_have_value("dm-content-systems")
    else:
        expect(return_fields).to_have_count(0)
    for lane_id in set(LANE_HEADINGS) - {"systems-source-enablement"}:
        lane = page.locator(f"#{lane_id}")
        if lane_id == "systems-shared-imports":
            expect(lane).not_to_have_attribute("open", "")
        else:
            expect(lane).to_have_attribute("open", "")
    _assert_containment(page, f"{label} validation 400")


def _assert_entry_override_prg(
    page,
    expect,
    *,
    target_url: str,
    host_path: str,
    entry_key: str,
    label: str,
    java_script_enabled: bool,
) -> None:
    expected_target = (
        f"{target_url}#systems-entry-overrides"
        if host_path.endswith("/dm-content/systems")
        else target_url
    )
    page.goto(target_url)
    page.wait_for_load_state("load")
    lane = page.locator("#systems-entry-overrides")
    expect(lane).to_have_attribute("open", "")

    def submit(*, visibility: str, enablement: str) -> None:
        lane.locator('input[name="entry_key"]').fill(entry_key)
        lane.locator('select[name="visibility_override"]').select_option(
            visibility
        )
        lane.locator('select[name="is_enabled_override"]').select_option(
            enablement
        )
        with page.expect_navigation():
            lane.get_by_role("button", name="Save entry override").click()
        _wait_for_page(
            page,
            java_script_enabled=java_script_enabled,
        )

    submit(visibility=VISIBILITY_PLAYERS, enablement="enabled")
    assert page.url == expected_target
    lane = page.locator("#systems-entry-overrides")
    expect(lane).to_have_attribute("open", "")
    expect(lane).to_contain_text("Players")
    expect(lane).to_contain_text("Enabled")

    submit(visibility=VISIBILITY_PLAYERS, enablement="enabled")
    assert page.url == expected_target
    lane = page.locator("#systems-entry-overrides")
    expect(lane).to_have_attribute("open", "")

    submit(visibility="", enablement="")
    assert page.url == expected_target
    lane = page.locator("#systems-entry-overrides")
    expect(lane).to_have_attribute("open", "")
    expect(lane).to_contain_text("Inherit source default")
    expect(lane).to_contain_text("Inherit source enablement")
    expect(lane.get_by_text("No campaign-specific Systems entry overrides")).to_have_count(
        0
    )
    expect(lane.get_by_role("button", name=re.compile("delete|remove|reset", re.I))).to_have_count(
        0
    )
    return_fields = lane.locator('input[name="return_to"]')
    if host_path.endswith("/dm-content/systems"):
        expect(return_fields).to_have_count(1)
        expect(return_fields).to_have_value("dm-content-systems")
    else:
        expect(return_fields).to_have_count(0)
    _assert_entry_override_control_order(page, expect)
    _assert_containment(page, f"{label} entry override PRG")


def test_systems_management_shell_real_chromium_matrix(
    app,
    systems_management_shell_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

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
                            label=f"{host_path} {mode_label} default",
                            source_open=False,
                            entry_override_open=False,
                            custom_entries_open=False,
                            seeded=False,
                        )
                        _assert_custom_entry_idle_fragment_target(
                            page,
                            expect,
                            target_url,
                        )
                        _assert_entry_override_default_prefill_fragment_and_validation(
                            page,
                            expect,
                            target_url=target_url,
                            host_path=host_path,
                            label=f"{host_path} {mode_label}",
                        )
                finally:
                    page.close()
                    context.close()

            entry_key = _seed_management_shell_matrix(app, users)
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
                            source_open=False,
                            entry_override_open=True,
                            custom_entries_open=True,
                        )
                        _assert_source_fragment_target(page, expect, target_url)
                        _assert_source_prg_and_validation(
                            page,
                            expect,
                            target_url=target_url,
                            host_path=host_path,
                            label=f"{host_path} {mode_label}",
                        )
                        _assert_entry_override_prg(
                            page,
                            expect,
                            target_url=target_url,
                            host_path=host_path,
                            entry_key=entry_key,
                            label=f"{host_path} {mode_label}",
                            java_script_enabled=java_script_enabled,
                        )
                        _assert_custom_entry_lifecycle(
                            page,
                            expect,
                            target_url=target_url,
                            host_path=host_path,
                            label=f"{host_path} {mode_label}",
                            java_script_enabled=java_script_enabled,
                        )
                finally:
                    page.close()
                    context.close()

            for mode_label, viewport, java_script_enabled in modes:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                )
                page = context.new_page()
                try:
                    _sign_in(page, base_url, users["admin"])
                    for host_path in HOST_PATHS:
                        target_url = f"{base_url}{host_path}"
                        page.goto(target_url)
                        _wait_for_page(
                            page,
                            java_script_enabled=java_script_enabled,
                        )
                        _assert_shared_import_details_validation(
                            page,
                            expect,
                            host_path=host_path,
                            label=f"{host_path} {mode_label}",
                            java_script_enabled=java_script_enabled,
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
                expect(
                    projected_page.locator("#systems-source-enablement")
                ).not_to_have_attribute("open", "")
                expect(
                    projected_page.locator("#systems-entry-overrides")
                ).to_have_attribute("open", "")
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
                expect(
                    admin_page.locator("#systems-source-enablement")
                ).not_to_have_attribute("open", "")
                expect(
                    admin_page.locator("#systems-entry-overrides")
                ).to_have_attribute("open", "")
                markup = admin_page.content()
                assert 'name="systems_import_archive"' in markup
                assert (
                    'action="/campaigns/linden-pass/systems/control-panel/'
                    'shared-core-permission"'
                ) in markup
                assert '<option value="private">' in markup
                assert PRIVATE_SOURCE_PATH not in markup
                assert "source_path" not in markup
                assert "audit_state" not in markup
                assert "storage_state" not in markup
                assert INTERNAL_PLAYER_READ_MARKER not in markup
                assert "Campaign Item Mechanics" not in markup
                assert "/systems/item-mechanics/import" not in markup
        finally:
            for context in reversed(contexts):
                context.close()
            browser.close()
