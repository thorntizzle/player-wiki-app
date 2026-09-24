from pathlib import Path
import re
import time

import pytest

from tests.test_static_assets import static_asset_live_server, _configure_loopback_online, _sign_in_in_browser
from tests.helpers.session_article_helpers import article_base_token
from player_wiki.auth_store import AuthStore


@pytest.fixture
def live_browser_page(static_asset_live_server):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _configure_loopback_online(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        browser.close()
        assert errors == []


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}], ids=["desktop", "mobile"])
@pytest.mark.parametrize("scrolled", [False, True], ids=["top", "scrolled"])
def test_session_post_send_focus_receives_peer_message_reveal_and_close(client, sign_in, users, static_asset_live_server, live_browser_page, viewport, scrolled):
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start")
    client.post("/campaigns/linden-pass/session/articles", data={"title": "Peer reveal", "body_markdown": "Article body"})
    page = live_browser_page
    page.set_viewport_size(viewport)
    _sign_in_in_browser(page, static_asset_live_server, users["party"]["email"], users["party"]["password"])
    page.goto(static_asset_live_server + "/campaigns/linden-pass/session")
    form = page.locator("form[data-session-composer-form]")
    field = form.locator("textarea[name=body]")
    field.fill("Own message")
    form.locator('button[type="submit"]').click()
    expect(field).to_have_value("")
    expect(field).to_be_focused()
    page.evaluate("scrolled => window.scrollTo(0, scrolled ? 120 : 0)", scrolled)
    assert (page.evaluate("window.scrollY") > 0) is scrolled
    root = page.locator('[data-session-live-view=session]')
    assert [root.get_attribute(name) for name in ('data-live-active-interval-ms', 'data-live-idle-interval-ms', 'data-live-idle-threshold-ms')] == ['3000', '6000', '30000']

    def capture():
        return field.evaluate("field => {window.retainedComposer = field; return {value:field.value,start:field.selectionStart,end:field.selectionEnd,direction:field.selectionDirection,top:field.getBoundingClientRect().top};}")

    def preserved(before):
        after = page.evaluate("() => {const field = window.retainedComposer; return {same:field===document.querySelector('[data-session-composer-root] textarea[name=body]'),connected:field.isConnected,focus:document.activeElement===field,value:field.value,start:field.selectionStart,end:field.selectionEnd,direction:field.selectionDirection,top:field.getBoundingClientRect().top};}")
        assert all(after[key] for key in ('same', 'connected', 'focus')), after
        assert {key: after[key] for key in ('value','start','end','direction')} == {key: before[key] for key in ('value','start','end','direction')}
        assert abs(after['top'] - before['top']) <= 2, (before, after)

    def peer(path, data, predicate):
        before = capture()
        started = time.perf_counter()
        assert client.post(path, data=data).status_code == 302
        page.wait_for_function(predicate, timeout=max(1, 3500 - (time.perf_counter()-started)*1000))
        assert (time.perf_counter()-started)*1000 <= 3500
        preserved(before)

    peer('/campaigns/linden-pass/session/messages', {'body':'Peer message while focused'}, "() => document.querySelector('[data-session-chat-card]').textContent.includes('Peer message while focused')")
    field.fill("HB retained typing draft")
    field.evaluate('field => {field.setSelectionRange(3, 12, "forward"); field.dispatchEvent(new CompositionEvent("compositionstart", {bubbles:true}));}')
    peer('/campaigns/linden-pass/session/articles/1/reveal', {}, "() => document.querySelector('[data-session-chat-card]').textContent.includes('Peer reveal')")
    field.dispatch_event('compositionend')
    peer('/campaigns/linden-pass/session/close', {}, "() => document.querySelector('[data-session-live-view=session]').dataset.activeSessionId === ''")
    expect(form.locator("button[type=submit]")).to_be_disabled()
    # An ordinary unchanged poll cannot accumulate compensating layout space.
    before = capture()
    padding = form.evaluate('form => form.style.paddingTop')
    sequence = page.evaluate("window.__playerWikiLiveMetrics?.latest?.session?.sequence || 0")
    page.wait_for_function("sequence => (window.__playerWikiLiveMetrics?.latest?.session?.sequence || 0) > sequence", arg=sequence, timeout=3500)
    preserved(before)
    assert form.evaluate('form => form.style.paddingTop') == padding
    field.evaluate('field => field.blur()')
    page.wait_for_function("() => window.retainedComposer.form.style.paddingTop === ''", timeout=1000)


def test_combat_focused_controls_read_and_latest_fragment_catches_up_after_blur(client, sign_in, users, static_asset_live_server, live_browser_page):
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    page = live_browser_page
    _sign_in_in_browser(page, static_asset_live_server, users["dm"]["email"], users["dm"]["password"])
    page.goto(static_asset_live_server + "/campaigns/linden-pass/combat/dm?view=controls")
    page.get_by_text("Add custom combatant", exact=True).click()
    field = page.locator('form[action$="/combat/npc-combatants"] input[name="display_name"]')
    field.focus()
    field.evaluate("field => window.retainedControl = field")
    root = page.locator("[data-combat-live-root]")
    before = root.get_attribute("data-live-revision")
    response = client.post("/campaigns/linden-pass/combat/npc-combatants", data={"display_name": "Peer Guard", "turn_value": "11", "initiative_priority": "1", "dexterity_modifier": "2", "current_hp": "14", "max_hp": "16", "temp_hp": "0", "movement_total": "30"})
    assert response.status_code == 302
    expect(root).not_to_have_attribute("data-live-revision", before, timeout=1000)
    assert field.evaluate("field => field === window.retainedControl && document.activeElement === field")
    # No new server change: pending controls must apply despite unchanged revision short-circuiting.
    field.evaluate("field => field.blur()")
    page.wait_for_function("() => !window.retainedControl.isConnected", timeout=1000)
    expect(page.locator('form[action$="/combat/npc-combatants"] input[name="display_name"]')).to_have_value("")


def test_fragment_guard_preserves_dirty_ime_files_and_flushes_latest_without_reads(live_browser_page):
    page = live_browser_page
    page.set_content('<main id="root"><section id="region"><details open><summary>Draft</summary><form action="/save"><textarea name="body"></textarea><input name="file" type="file"><button>Save</button></form></details></section><button id="outside">Outside</button></main>')
    page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / "player_wiki/static/live-ui-helper.js"))
    page.evaluate("""() => {
      window.region = document.querySelector('#region');
      window.guard = window.__playerWikiLiveUiTools.createFragmentGuard(document.querySelector('#root'));
      window.field = region.querySelector('textarea');
      window.applied = [];
      field.focus(); field.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
      guard.replace(region, '<p>First</p>', () => { applied.push('first'); region.innerHTML = '<p>First</p>'; });
      guard.replace(region, '<p>Latest</p>', () => { applied.push('latest'); region.innerHTML = '<p>Latest</p>'; });
      field.blur();
    }""")
    assert page.evaluate("window.applied") == []
    page.evaluate("field.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true}))")
    page.wait_for_function("() => window.applied.length === 1")
    assert page.evaluate("window.applied") == ["latest"]
    page.evaluate("""() => {
      region.innerHTML = '<form action="/save"><input type="file" name="file"><textarea name="body"></textarea></form>';
      window.file = region.querySelector('input');
      const transfer = new DataTransfer(); transfer.items.add(new File(['bytes'], 'draft.png', {type:'image/png'}));
      file.files = transfer.files;
      window.selected = file.files[0];
      guard.replace(region, '<p>After file release</p>');
      guard.flush();
    }""")
    assert page.evaluate("file.isConnected && file.files[0] === selected")
    page.evaluate("file.value = ''; file.dispatchEvent(new Event('change', {bubbles:true}))")
    page.wait_for_function("() => region.textContent === 'After file release'")


def test_staged_atomic_move_fallback_retains_focused_ime_file_then_catches_up(client, sign_in, users, static_asset_live_server, live_browser_page):
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/articles", data={"title": "Fallback draft", "body_markdown": "Original"})
    page = live_browser_page
    page.add_init_script("Element.prototype.moveBefore = undefined")
    _sign_in_in_browser(page, static_asset_live_server, users["dm"]["email"], users["dm"]["password"])
    page.goto(static_asset_live_server + "/campaigns/linden-pass/session/dm?dm_view=staged")
    article = page.locator('details[data-session-article-id="1"]')
    article.locator("summary").first.click()
    article.locator(".session-article-edit-detail > summary").click()
    field = article.locator("textarea")
    file = article.locator('input[type=file]')
    file.set_input_files({"name": "retained.png", "mimeType": "image/png", "buffer": b"local"})
    field.focus()
    field.dispatch_event("compositionstart")
    field.evaluate("field => {window.fallbackField = field; window.fallbackFile = field.form.querySelector('input[type=file]').files[0]; field.setSelectionRange(1, 3);}")
    root = page.locator('[data-session-live-view=dm]')
    before = root.get_attribute('data-live-revision')
    page.wait_for_function("root => !window.__playerWikiSessionLive.snapshot(root).readInFlight", arg=root.element_handle())
    announcement = root.locator('[data-live-read-announcement]')
    announcement.evaluate("node => node.textContent = 'unchanged announcement sentinel'")
    response = client.post("/campaigns/linden-pass/session/articles/1", data={"base_token": article_base_token(client), "title": "Peer replacement", "body_markdown": "Latest body"})
    assert response.status_code == 302
    expect(root).not_to_have_attribute('data-live-revision', before, timeout=3500)
    assert field.evaluate("field => field === fallbackField && document.activeElement === field && field.selectionStart === 1 && field.selectionEnd === 3")
    assert file.evaluate("file => file.files[0] === fallbackFile")
    expect(field).to_have_value("Original")
    page.wait_for_function("root => !window.__playerWikiSessionLive.snapshot(root).readInFlight", arg=root.element_handle())
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(announcement).to_have_text("unchanged announcement sentinel")
    field.dispatch_event("compositionend")
    field.evaluate("field => field.blur()")
    file.set_input_files([])
    expect(article.locator("textarea")).to_have_value("Latest body", timeout=1000)
    assert page.evaluate("() => !window.fallbackField.isConnected")
    file.set_input_files({"name": "deleted-draft.png", "mimeType": "image/png", "buffer": b"local"})
    field.focus()
    before = root.get_attribute('data-live-revision')
    assert client.post("/campaigns/linden-pass/session/articles/1/delete").status_code == 302
    expect(root).not_to_have_attribute('data-live-revision', before, timeout=3500)
    expect(article.locator('.session-article-edit-form')).to_have_attribute('data-live-authority-unavailable', '1')
    expect(article.get_by_role("button", name="Update prep draft")).to_be_disabled()
    expect(field).to_have_value("Latest body")
    assert file.evaluate("field => field.files[0].name") == "deleted-draft.png"


def test_native_rejected_session_draft_survives_unfocused_poll(client, sign_in, users, static_asset_live_server, live_browser_page):
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/articles", data={"title": "Native draft", "body_markdown": "Original"})
    page = live_browser_page
    _sign_in_in_browser(page, static_asset_live_server, users["dm"]["email"], users["dm"]["password"])
    page.goto(static_asset_live_server + "/campaigns/linden-pass/session/dm?dm_view=staged")
    article = page.locator('details[data-session-article-id="1"]')
    article.locator("summary").first.click()
    article.locator(".session-article-edit-detail > summary").click()
    form = article.locator(".session-article-edit-form")
    baseline = form.locator('[name=base_token]').input_value()
    form.locator("textarea").fill("Native retained text")
    assert client.post("/campaigns/linden-pass/session/articles/1", data={"base_token": baseline, "title": "Peer winner", "body_markdown": "Peer text"}).status_code == 302
    with page.expect_navigation() as navigation:
        form.evaluate("form => {form.removeAttribute('data-session-async'); form.requestSubmit();}")
    assert navigation.value.status == 409
    form = page.locator('details[data-session-article-id="1"] .session-article-edit-form')
    expect(form).to_have_attribute('data-session-article-validation-retained', '1')
    expect(form.locator("textarea")).to_have_value("Native retained text")
    assert form.locator('[name=base_token]').input_value() == baseline
    form.locator("textarea").evaluate("field => field.blur()")
    before = page.locator('[data-session-live-view=dm]').get_attribute('data-live-revision')
    client.post("/campaigns/linden-pass/session/articles", data={"title": "After native refusal", "body_markdown": "Fresh peer card"})
    expect(page.locator('[data-session-live-view=dm]')).not_to_have_attribute('data-live-revision', before, timeout=3500)
    expect(form.locator("textarea")).to_have_value("Native retained text")
    assert form.locator('[name=base_token]').input_value() == baseline
    expect(form.get_by_role("link", name="Refresh and compare")).to_have_attribute('href', '/campaigns/linden-pass/session/dm?dm_view=staged')


def test_permission_loss_revokes_controls_and_discards_pending_authority(app, client, sign_in, users, static_asset_live_server, live_browser_page):
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/articles", data={"title": "Permission draft", "body_markdown": "Original"})
    page = live_browser_page
    _sign_in_in_browser(page, static_asset_live_server, users["dm"]["email"], users["dm"]["password"])
    page.goto(static_asset_live_server + "/campaigns/linden-pass/session/dm?dm_view=staged")
    article = page.locator('details[data-session-article-id="1"]')
    article.locator("summary").first.click()
    article.locator(".session-article-edit-detail > summary").click()
    form = article.locator(".session-article-edit-form")
    form.locator("textarea").fill("Draft before access loss")
    with app.app_context():
        AuthStore().upsert_membership(users["dm"]["id"], "linden-pass", role="player")
    expect(form).to_have_attribute('data-live-authority-unavailable', '1', timeout=3500)
    expect(form.get_by_role("button", name="Update prep draft")).to_be_disabled()
    expect(page.locator('[data-session-live-view=dm] [data-live-read-status-message]')).to_contain_text("no longer available")
    form.locator("textarea").evaluate("field => {field.value = field.defaultValue; field.blur(); field.dispatchEvent(new Event('input', {bubbles:true}));}")
    expect(form.get_by_role("button", name="Update prep draft")).to_be_disabled()


@pytest.mark.parametrize("surface", ["session", "combat"])
def test_live_announcements_attribute_only_actual_regions_at_announcement_frame(client, sign_in, users, static_asset_live_server, live_browser_page, surface):
    """Controlled payload/RAF fixture; production polling cadence remains unchanged."""
    from playwright.sync_api import expect
    sign_in(users["dm"]["email"], users["dm"]["password"])
    page = live_browser_page
    _sign_in_in_browser(page, static_asset_live_server, users["dm"]["email"], users["dm"]["password"])
    if surface == "session":
        path, live_path = "/session", "/session/live-state"
        root_selector, target_selector = '[data-session-live-view=session]', '[data-session-chat-card]'
        payload_key, token_key, updated = "chat_html", "manager_state_token", "Session updated."
        visible_selector = '[data-session-status-card]'
        timeout = 3500
    else:
        path, live_path = "/combat/dm?view=controls", "/combat/dm/live-state?view=controls"
        root_selector, target_selector = '[data-combat-live-root]', '[data-combat-controls-root]'
        payload_key, token_key, updated = "controls_html", "combat_state_token", "Combat updated."
        visible_selector = '[data-combat-clear-confirmation-root]'
        timeout = 1000
    page.goto(static_asset_live_server + "/campaigns/linden-pass" + path)
    root, target = page.locator(root_selector), page.locator(target_selector)
    expect(target).to_be_visible()
    payload = client.get("/campaigns/linden-pass" + live_path).get_json()
    assert isinstance(payload, dict) and payload["changed"]
    payload = {key: value for key, value in payload.items() if not key.endswith("_html")}
    pending = []
    def respond(route):
        if pending:
            route.fulfill(status=200, json=pending.pop(0))
        else:
            route.fulfill(status=200, json=dict(payload, changed=False))
    page.route(re.compile(r".*/(?:session|combat/dm)/live-state(?:\?.*)?$"), respond)
    page.wait_for_function("root => root.dataset.liveAsyncState !== 'checking'", arg=root.element_handle())
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    announcement = root.locator('[data-live-read-announcement]')
    target.evaluate("node => {window.announcementTarget = node; const form = document.createElement('form'); form.innerHTML = '<textarea name=protected></textarea>'; node.append(form); form.querySelector('textarea').focus();}")
    expect(root.locator(visible_selector)).to_be_visible()
    announcement.evaluate("node => node.textContent = 'sentinel'")
    def enqueue(sequence):
        pending.append(dict(payload, changed=True, live_revision=int(payload.get("live_revision") or 0) + sequence,
                            **{token_key: f"announcement-{sequence}", payload_key: f'<p data-announcement-content="{sequence}">Changed region {sequence}</p>'}))
    enqueue(1)
    page.wait_for_function("() => document.querySelector('[name=protected]').form.dataset.liveAuthorityUnavailable === '1'", timeout=timeout)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(announcement).to_have_text("sentinel")
    # Pending target applies after release, without borrowing unrelated visible content.
    page.locator('[name=protected]').evaluate("node => node.blur()")
    expect(target.locator('[data-announcement-content="1"]')).to_have_count(1)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(announcement).to_have_text("sentinel")
    target.evaluate("node => node.hidden = true")
    enqueue(2)
    expect(target.locator('[data-announcement-content="2"]')).to_have_count(1, timeout=timeout)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(announcement).to_have_text("sentinel")
    # Hold the actual announcement frame, then hide its applied target before it runs.
    target.evaluate("node => node.hidden = false")
    page.evaluate("() => {window.originalAnimationFrame = window.requestAnimationFrame; window.heldAnnouncementFrames = []; window.requestAnimationFrame = callback => {heldAnnouncementFrames.push(callback); return 0;};}")
    enqueue(3)
    expect(target.locator('[data-announcement-content="3"]')).to_have_count(1, timeout=timeout)
    page.wait_for_function("() => heldAnnouncementFrames.length > 0", polling=20)
    target.evaluate("node => node.hidden = true")
    page.evaluate("() => {window.requestAnimationFrame = originalAnimationFrame; for (const callback of heldAnnouncementFrames.splice(0)) originalAnimationFrame(callback);}")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(announcement).to_have_text("sentinel")
    # Positive control: the same applied region, visible at settlement, announces once.
    target.evaluate("node => node.hidden = false")
    enqueue(4)
    expect(announcement).to_have_text(updated, timeout=timeout)

@pytest.mark.parametrize("scroll_y", [0, 120], ids=["top", "scrolled"])
def test_fragment_interaction_reconciliation_leaves_stationary_viewport_untouched(live_browser_page, scroll_y):
    page = live_browser_page
    page.set_content('<main id="root"><section id="region"><p>Before</p><form action="/save"><textarea name="body"></textarea><button>Save</button></form></section>' + '<p>Surrounding document context.</p>' * 40 + '</main>')
    page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / "player_wiki/static/live-ui-helper.js"))
    state = page.evaluate("""scrollY => {
      const root = document.querySelector('#root');
      const region = root.querySelector('#region');
      const field = region.querySelector('textarea');
      field.value = 'Local draft'; field.focus({preventScroll:true}); field.setSelectionRange(1, 5, 'backward');
      window.scrollTo(0, scrollY);
      const before = field.getBoundingClientRect().top;
      const scroll = window.scrollY;
      const originalScrollTo = window.scrollTo;
      let scrollCalls = 0;
      window.scrollTo = (...args) => {scrollCalls++; originalScrollTo.apply(window, args);};
      const guard = window.__playerWikiLiveUiTools.createFragmentGuard(root, {interactionViewport:true});
      const updated = guard.replace(region, '<p>After!</p><form action="/save"><textarea name="body"></textarea><button>Save</button></form>', undefined, {retainInteractions:true});
      return {updated, same:field === region.querySelector('textarea'), focused:document.activeElement === field,
        direction:field.selectionDirection, value:field.value, start:field.selectionStart, end:field.selectionEnd, topDelta:field.getBoundingClientRect().top-before,
        scrollDelta:window.scrollY-scroll, scrollCalls, padding:field.form.style.paddingTop};
    }""", scroll_y)
    assert state == dict(updated=True, same=True, focused=True, direction='backward', value='Local draft', start=1, end=5, topDelta=0, scrollDelta=0, scrollCalls=0, padding='')


def test_fragment_interaction_reorder_defers_without_detaching_ime_file_or_tokens(live_browser_page):
    page = live_browser_page
    first = '<form action="/a"><input type="hidden" name="base_token" value="original"><textarea name="body"></textarea><input type="file" name="file"><button>Save</button></form>'
    second = '<form action="/b"><textarea name="other"></textarea><button>Save</button></form>'
    page.set_content('<main id="root"><section id="region">' + first + second + '</section></main>')
    page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / "player_wiki/static/live-ui-helper.js"))
    page.evaluate("""() => {
      Element.prototype.moveBefore = undefined;
      window.region = document.querySelector('#region');
      window.guard = window.__playerWikiLiveUiTools.createFragmentGuard(document.querySelector('#root'));
      window.first = region.querySelector('form[action="/a"]');
      window.second = region.querySelector('form[action="/b"]');
      window.field = first.querySelector('textarea'); window.file = first.querySelector('input[type=file]');
      field.value = 'IME draft'; field.focus(); field.setSelectionRange(1, 5, 'backward');
      field.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
      const transfer = new DataTransfer(); transfer.items.add(new File(['bytes'], 'draft.png', {type:'image/png'}));
      file.files = transfer.files; window.selectedFile = file.files[0];
      second.querySelector('textarea').value = 'Other draft';
    }""")
    html = '<p>Latest peer update</p>' + second + first.replace('original', 'new-token')
    assert page.evaluate('(html) => guard.replace(region, html, undefined, {retainInteractions:true})', html) is False
    assert page.evaluate("""() => first.isConnected && second.isConnected && field === first.querySelector('textarea')
      && document.activeElement === field && field.selectionStart === 1 && field.selectionEnd === 5
      && field.selectionDirection === 'backward' && file.files[0] === selectedFile
      && first.querySelector('[name=base_token]').value === 'original'
      && region.firstElementChild === first && region.lastElementChild === second""")
    page.evaluate("""() => {
      field.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true}));
      field.value = ''; field.blur(); second.querySelector('textarea').value = '';
      second.querySelector('textarea').dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    assert page.evaluate('first.isConnected && file.files[0] === selectedFile')
    page.evaluate("file.value = ''; file.dispatchEvent(new Event('change', {bubbles:true}))")
    page.wait_for_function("() => !first.isConnected && !second.isConnected && region.textContent.includes('Latest peer update')", timeout=1000)
    assert page.locator('[name=base_token]').input_value() == 'new-token'


@pytest.mark.parametrize("viewport", [{"width":1440,"height":1000}, {"width":390,"height":844}], ids=["desktop", "mobile"])
def test_uncertain_clear_retains_only_revoked_confirmation_when_peer_clears_articles(client, sign_in, users, static_asset_live_server, live_browser_page, viewport):
    from playwright.sync_api import expect
    sign_in(users['dm']['email'], users['dm']['password'])
    assert client.post('/campaigns/linden-pass/session/start').status_code == 302
    assert client.post('/campaigns/linden-pass/session/articles', data={'title':'Peer removed article', 'body_markdown':'Must disappear after clear'}).status_code == 302
    assert client.post('/campaigns/linden-pass/session/articles/1/reveal').status_code == 302
    page = live_browser_page
    page.set_viewport_size(viewport)
    _sign_in_in_browser(page, static_asset_live_server, users['dm']['email'], users['dm']['password'])
    page.goto(static_asset_live_server + '/campaigns/linden-pass/session/dm?dm_view=revealed')
    region = page.locator('[data-session-revealed-root]')
    expect(region.locator('[data-session-article-id]')).to_have_count(1)
    region.locator('[data-presentation-dialog-trigger]').click()
    dialog = region.locator('dialog')
    acknowledgement = dialog.locator('[name=destructive_acknowledgement]')
    acknowledgement.check()
    acknowledgement.evaluate('field => window.retainedAcknowledgement = field')
    page.route('**/session/articles/clear-revealed', lambda route: route.fulfill(status=503, body='Unknown result'))
    dialog.locator('button[type=submit]').click()
    expect(dialog.locator('[data-destructive-confirmation-recovery]')).to_be_focused()
    dialog.locator('[data-presentation-dialog-close]').first.click()
    page.unroute('**/session/articles/clear-revealed')
    assert client.post('/campaigns/linden-pass/session/articles/clear-revealed').status_code == 302
    expect(region).to_contain_text('No revealed articles yet.', timeout=3500)
    expect(region.locator('[data-session-article-id]')).to_have_count(0)
    assert acknowledgement.evaluate('field => field === window.retainedAcknowledgement && field.checked')
    expect(dialog.locator('button[type=submit]')).to_be_disabled()
    expect(dialog.locator('form')).to_have_attribute('data-live-authority-unavailable', '1')
    region.locator('[data-presentation-dialog-trigger]').click()
    acknowledgement.uncheck()
    dialog.locator('[data-presentation-dialog-close]').first.click()
    expect(region.locator('[data-destructive-confirmation]')).to_have_count(0, timeout=1000)
