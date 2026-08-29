from __future__ import annotations

import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY


PATH = "/campaigns/linden-pass/combat/combatants/{combatant_id}/npc-resources"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _seed_source_npc(app, users, *, name: str = "Resource Browser Probe", with_counters: bool = True):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return service.add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=14,
            current_hp=24,
            max_hp=24,
            movement_total=30,
            source_kind="systems_monster",
            source_ref=f"browser-{name.lower().replace(' ', '-')}",
            resource_counter_seeds=(
                [
                    SimpleNamespace(
                        resource_key="recharge-breath",
                        label="Recharge Breath",
                        current_value=1,
                        max_value=1,
                        reset_label="Recharge 5–6",
                        source_label="Browser probe",
                        reset_kind="recharge_d6",
                        recharge_threshold=5,
                    ),
                    SimpleNamespace(
                        resource_key="misty-step",
                        label="Misty Step",
                        current_value=2,
                        max_value=3,
                        reset_label="Daily",
                        source_label="Browser probe",
                        reset_kind="daily",
                    ),
                    SimpleNamespace(
                        resource_key="arcane-charge",
                        label="Arcane Charge",
                        current_value=2,
                        max_value=4,
                        reset_label="Manual",
                        source_label="Browser probe",
                        reset_kind="source",
                    ),
                ]
                if with_counters
                else []
            ),
            resource_note_seeds=[
                SimpleNamespace(
                    label="Unmodeled Burst",
                    note="Recharge timing stays a table ruling.",
                    source_label="Browser probe",
                )
            ],
            created_by_user_id=users["dm"]["id"],
        )


def _state(app, combatant_id: int):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        return {
            "tracker": service.get_tracker("linden-pass"),
            "combatant": service.get_combatant("linden-pass", combatant_id),
            "counters": {
                row.resource_key: row
                for row in service.store.list_resource_counters(
                    "linden-pass",
                    combatant_ids=[combatant_id],
                )
            },
        }


def _post(client, combatant, *, resource_key: str, current_value, revision=None, async_request=False):
    data = {
        "combat_view": "dm",
        "view": "status",
        "resource_key": resource_key,
        "current_value": current_value,
    }
    if revision is not None:
        data["expected_combatant_revision"] = revision
    return client.post(
        PATH.format(combatant_id=combatant.id),
        data=data,
        headers=(
            {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
            if async_request
            else None
        ),
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    ("resource_key", "current_value"),
    (
        ("recharge-breath", 0),
        ("recharge-breath", 1),
        ("misty-step", 0),
        ("misty-step", 3),
        ("arcane-charge", 4),
    ),
)
def test_manager_browser_update_sets_one_absolute_counter_and_redirects_to_selected_anchor(
    app,
    client,
    sign_in,
    users,
    resource_key,
    current_value,
):
    target = _seed_source_npc(app, users)
    before = _state(app, target.id)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = _post(
        client,
        target,
        resource_key=resource_key,
        current_value=current_value,
        revision=target.revision,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == (
        f"/campaigns/linden-pass/combat/dm?combatant={target.id}"
        f"#combat-npc-resource-{target.id}-{resource_key}"
    )
    after = _state(app, target.id)
    assert after["counters"][resource_key].current_value == current_value
    for other_key in set(before["counters"]) - {resource_key}:
        assert after["counters"][other_key].current_value == before["counters"][other_key].current_value
    assert after["combatant"].revision == before["combatant"].revision + 1
    assert after["combatant"].updated_by_user_id == users["dm"]["id"]
    assert after["tracker"].revision == before["tracker"].revision + 1
    assert after["tracker"].updated_by_user_id == users["dm"]["id"]


@pytest.mark.parametrize(
    ("resource_key", "current_value", "message"),
    (
        ("recharge-breath", 2, "Recharge Breath cannot exceed 1."),
        ("misty-step", -1, "Enter a valid NPC resource current value."),
        ("misty-step", 4, "Misty Step cannot exceed 3."),
        ("missing", 0, "Choose a valid NPC resource counter."),
        ("", 0, "Choose a valid NPC resource counter."),
        ("arcane-charge", "", "Enter a valid NPC resource current value."),
    ),
)
def test_manager_browser_update_rejects_bounds_keys_and_missing_values_without_writes(
    app,
    client,
    sign_in,
    users,
    resource_key,
    current_value,
    message,
):
    target = _seed_source_npc(app, users)
    before = _state(app, target.id)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = _post(
        client,
        target,
        resource_key=resource_key,
        current_value=current_value,
        revision=target.revision,
        async_request=True,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert message in payload["flash_html"]
    assert _state(app, target.id) == before


def test_manager_browser_update_requires_current_revision_and_rejects_stale_without_writes(
    app,
    client,
    sign_in,
    users,
):
    target = _seed_source_npc(app, users)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    missing = _post(
        client,
        target,
        resource_key="misty-step",
        current_value=1,
        revision=None,
        async_request=True,
    )
    assert missing.status_code == 200
    assert missing.get_json()["ok"] is False
    assert "Enter a valid combatant revision." in missing.get_json()["flash_html"]

    accepted = _post(
        client,
        target,
        resource_key="arcane-charge",
        current_value=1,
        revision=target.revision,
    )
    assert accepted.status_code == 302
    before_stale = _state(app, target.id)

    stale = _post(
        client,
        target,
        resource_key="misty-step",
        current_value=1,
        revision=target.revision,
        async_request=True,
    )
    assert stale.status_code == 200
    assert stale.headers["X-Live-Mutation-Outcome"] == "combatant-revision-conflict"
    assert stale.get_json()["ok"] is False
    assert "This combatant changed in another combat view." in stale.get_json()["flash_html"]
    assert _state(app, target.id) == before_stale


def test_manager_browser_update_validates_target_kind_and_presence(
    app,
    client,
    sign_in,
    users,
):
    target = _seed_source_npc(app, users, with_counters=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    missing = client.post(
        PATH.format(combatant_id=999999),
        data={"expected_combatant_revision": 1, "resource_key": "missing", "current_value": 0},
    )
    assert missing.status_code == 404

    no_counters = _post(
        client,
        target,
        resource_key="missing",
        current_value=0,
        revision=target.revision,
        async_request=True,
    )
    assert no_counters.status_code == 200
    assert "This NPC has no supported source-backed resource counters." in no_counters.get_json()["flash_html"]

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 15},
    )
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = next(row for row in service.list_combatants("linden-pass") if row.character_slug == "arden-march")
    player_response = _post(
        client,
        player,
        resource_key="missing",
        current_value=0,
        revision=player.revision,
        async_request=True,
    )
    assert player_response.status_code == 200
    assert "Only NPC source resources can be edited here." in player_response.get_json()["flash_html"]


@pytest.mark.parametrize(("user_key", "expected_status"), (("dm", 302), ("admin", 302), ("owner", 403), ("party", 403), ("outsider", 404)))
def test_browser_update_actor_matrix(app, client, sign_in, users, user_key, expected_status):
    target = _seed_source_npc(app, users)
    before = _state(app, target.id)
    sign_in(users[user_key]["email"], users[user_key]["password"])

    response = _post(
        client,
        target,
        resource_key="misty-step",
        current_value=1,
        revision=target.revision,
    )

    assert response.status_code == expected_status
    after = _state(app, target.id)
    if expected_status == 302:
        assert after["counters"]["misty-step"].current_value == 1
    else:
        assert after == before


def test_browser_update_blocks_anonymous_view_as_and_csrf_before_mutation(app, client, sign_in, users):
    target = _seed_source_npc(app, users)
    path = PATH.format(combatant_id=target.id)
    before = _state(app, target.id)

    anonymous = client.post(
        path,
        data={"expected_combatant_revision": target.revision, "resource_key": "misty-step", "current_value": 1},
        follow_redirects=False,
    )
    assert anonymous.status_code == 302

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as = client.post(
        path,
        data={"expected_combatant_revision": target.revision, "resource_key": "misty-step", "current_value": 1},
    )
    assert view_as.status_code == 403
    assert _state(app, target.id) == before

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    app.config["CSRF_ENABLED"] = True
    html = client.get(f"/campaigns/linden-pass/combat/dm?combatant={target.id}").get_data(as_text=True)
    form = re.search(
        rf'<form\b[^>]*action="{re.escape(path)}"[^>]*>([\s\S]*?)</form>',
        html,
    )
    assert form is not None
    assert form.group(1).count('name="_csrf_token"') == 1
    csrf_denied = client.post(
        path,
        data={"expected_combatant_revision": target.revision, "resource_key": "misty-step", "current_value": 1},
    )
    assert csrf_denied.status_code == 400
    assert _state(app, target.id) == before


def test_dm_status_renders_compact_bounded_counter_forms_and_read_only_notes(
    app,
    client,
    sign_in,
    users,
):
    target = _seed_source_npc(app, users)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    html = client.get(f"/campaigns/linden-pass/combat/dm?combatant={target.id}").get_data(as_text=True)

    assert "Source resources" in html
    assert "Recharge Breath" in html
    assert "Reset: Recharge 5–6 · Source: Browser probe" in html
    assert "Misty Step" in html and "Reset: Daily · Source: Browser probe" in html
    assert "Arcane Charge" in html and "Reset: Manual · Source: Browser probe" in html
    assert html.count(f'action="{PATH.format(combatant_id=target.id)}"') == 3
    assert html.count('name="expected_combatant_revision"') >= 3
    assert html.count('name="current_value"') == 3
    assert html.count('data-combat-async') >= 3
    assert html.count('data-post-submit-focus-key=') >= 3
    assert 'id="combat-npc-resource-' in html
    assert 'name="resource_key" value="recharge-breath"' in html
    recharge_input = re.search(
        r'id="combat-npc-resource-[^"]+-recharge-breath-current"[\s\S]*?max="1"[\s\S]*?required',
        html,
    )
    assert recharge_input is not None
    assert "Unmodeled Burst" in html
    assert "Recharge timing stays a table ruling." in html
    assert "Unsupported source mechanics" in html
    assert "data-combat-mutation-recovery" in html
    assert "inspect this resource's current value before submitting again" in html


def test_player_and_view_as_surfaces_expose_no_npc_counter_control(app, client, sign_in, users):
    target = _seed_source_npc(app, users)
    path = PATH.format(combatant_id=target.id)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    player_html = client.get(f"/campaigns/linden-pass/combat?combatant={target.id}").get_data(as_text=True)
    assert path not in player_html
    assert "data-combat-mutation-recovery" not in player_html

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    denied = client.get(f"/campaigns/linden-pass/combat/dm?combatant={target.id}")
    assert denied.status_code == 403
    assert path not in denied.get_data(as_text=True)


def test_async_browser_update_returns_refreshed_selected_detail_and_stable_focus_contract(
    app,
    client,
    sign_in,
    users,
):
    target = _seed_source_npc(app, users)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = _post(
        client,
        target,
        resource_key="misty-step",
        current_value=1,
        revision=target.revision,
        async_request=True,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == target.id
    assert payload["anchor"] == f"combat-npc-resource-{target.id}-misty-step"
    assert payload["combatant_detail_state_token"]
    detail_html = payload["tracker_detail_html"]
    assert 'name="resource_key" value="misty-step"' in detail_html
    assert re.search(r'name="current_value"[\s\S]*?value="1"', detail_html)
    assert f'data-post-submit-focus-key="combat-npc-resource-{target.id}-misty-step-update"' in detail_html
    assert "NPC resource updated." in payload["flash_html"]


def test_npc_resource_async_static_contract_preserves_focus_viewport_and_uncertain_outcome_guidance():
    combat_script = (PROJECT_ROOT / "player_wiki/static/combat-live.js").read_text(encoding="utf-8")
    snapshot_template = (PROJECT_ROOT / "player_wiki/templates/_combat_status_snapshot.html").read_text(
        encoding="utf-8"
    )

    assert 'form.querySelector("[data-combat-mutation-recovery]")' in combat_script
    assert "const mutationRecoveryForForm = (form) =>" in combat_script
    assert "recovery.focus({ preventScroll: true });" in combat_script
    assert "uiStateTools.restoreViewportAnchor(liveRoot, viewportAnchor);" in combat_script
    assert "uiStateTools.restoreFocusKey(liveRoot, postSubmitFocusKey)" in combat_script
    assert "data-post-submit-focus-key" in snapshot_template
    assert "data-live-focus-key" in snapshot_template
    assert "Refresh Combat and inspect this resource's current value before submitting again." in snapshot_template
    assert "data-combat-inline-autosubmit" not in snapshot_template.split("combat-npc-resources", 1)[1].split(
        "combat-status-conditions", 1
    )[0]
    assert "Roll recharge" not in snapshot_template


def test_browser_npc_resource_controls_preserve_selected_focus_and_viewport_across_desktop_mobile_and_no_js(
    app,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
        from werkzeug.serving import make_server
    except Exception as exc:
        pytest.skip(f"NPC resource browser coverage unavailable: {exc}")

    target = _seed_source_npc(app, users)
    server = make_server("127.0.0.1", 0, app)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    page_path = f"/campaigns/linden-pass/combat/dm?combatant={target.id}"
    mutation_path = PATH.format(combatant_id=target.id)
    browser_errors: list[str] = []
    expected_mutation_abort = {"active": False}

    def capture_console_error(message, *, label: str):
        if message.type != "error":
            return
        if expected_mutation_abort["active"] and "ERR_FAILED" in message.text:
            return
        browser_errors.append(f"{label}: {message.text}")

    def sign_in_browser(page):
        page.goto(f"{base_url}/sign-in")
        page.locator("input[name='email']").fill(users["dm"]["email"])
        page.locator("input[name='password']").fill(users["dm"]["password"])
        page.locator("button[type='submit']").click()
        page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium unavailable: {exc}")

            try:
                for index, viewport in enumerate(
                    ({"width": 1280, "height": 900}, {"width": 390, "height": 800})
                ):
                    context = browser.new_context(viewport=viewport)
                    page = context.new_page()
                    label = f"{viewport['width']}x{viewport['height']}"
                    page.on("pageerror", lambda error, label=label: browser_errors.append(f"{label}: {error}"))
                    page.on(
                        "console",
                        lambda message, label=label: capture_console_error(message, label=label),
                    )
                    try:
                        sign_in_browser(page)
                        response = page.goto(f"{base_url}{page_path}", wait_until="load")
                        assert response is not None and response.status == 200
                        row = page.locator(f"#combat-npc-resource-{target.id}-misty-step")
                        expect(row).to_be_visible(timeout=5000)
                        expect(page.get_by_text("Unmodeled Burst", exact=True)).to_be_visible()
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                        row.evaluate("node => window.scrollTo(0, Math.max(0, node.offsetTop - 120))")
                        current_input = row.locator("input[name='current_value']")
                        update_button = row.get_by_role("button", name="Update")
                        next_value = str(index + 1)
                        current_input.fill(next_value)
                        update_button.scroll_into_view_if_needed()
                        before_scroll = page.evaluate("window.scrollY")
                        with page.expect_response(
                            lambda candidate: (
                                candidate.request.method == "POST"
                                and candidate.url.endswith(mutation_path)
                            ),
                            timeout=5000,
                        ) as mutation_response:
                            update_button.click()
                        assert mutation_response.value.status == 200
                        expect(current_input).to_have_value(next_value, timeout=5000)
                        expect(update_button).to_be_focused()
                        assert page.url == f"{base_url}{page_path}"
                        assert page.evaluate(
                            "document.querySelector('[data-combat-live-root]').dataset.selectedCombatantId"
                        ) == str(target.id)
                        assert abs(float(page.evaluate("window.scrollY")) - float(before_scroll)) <= 2
                        form_box = row.locator("form").bounding_box()
                        assert form_box is not None
                        assert form_box["x"] >= -1
                        assert form_box["x"] + form_box["width"] <= viewport["width"] + 1

                        if index == 0:
                            lost_response_status: list[int] = []

                            def commit_then_drop(route):
                                fetched = route.fetch()
                                lost_response_status.append(fetched.status)
                                route.abort("failed")

                            page.route(f"**{mutation_path}", commit_then_drop)
                            current_input.fill("2")
                            expected_mutation_abort["active"] = True
                            update_button.click()
                            recovery = row.locator("[data-combat-mutation-recovery]")
                            expect(recovery).to_be_visible(timeout=5000)
                            expect(recovery).to_be_focused()
                            expect(recovery).to_contain_text(
                                "Refresh Combat and inspect this resource's current value before submitting again."
                            )
                            expected_mutation_abort["active"] = False
                            assert lost_response_status == [200]
                            page.unroute(f"**{mutation_path}", commit_then_drop)
                            assert _state(app, target.id)["counters"]["misty-step"].current_value == 2
                    finally:
                        page.close()
                        context.close()

                no_js_context = browser.new_context(
                    viewport={"width": 390, "height": 800},
                    java_script_enabled=False,
                )
                no_js_page = no_js_context.new_page()
                try:
                    sign_in_browser(no_js_page)
                    response = no_js_page.goto(f"{base_url}{page_path}", wait_until="load")
                    assert response is not None and response.status == 200
                    row = no_js_page.locator(f"#combat-npc-resource-{target.id}-arcane-charge")
                    row.locator("input[name='current_value']").fill("1")
                    row.get_by_role("button", name="Update").click()
                    no_js_page.wait_for_load_state("load")
                    assert no_js_page.url == (
                        f"{base_url}{page_path}#combat-npc-resource-{target.id}-arcane-charge"
                    )
                    expect(
                        no_js_page.locator(
                            f"#combat-npc-resource-{target.id}-arcane-charge input[name='current_value']"
                        )
                    ).to_have_value("1")
                finally:
                    no_js_page.close()
                    no_js_context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert browser_errors == []
