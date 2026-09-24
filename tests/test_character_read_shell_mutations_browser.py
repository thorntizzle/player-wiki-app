"""Normal Character mutation behavior under delayed and uncertain acknowledgements."""
from __future__ import annotations

import base64
import re
from types import SimpleNamespace

import pytest

from tests.test_character_read_shell_browser import (
    character_read_shell_live_server,
    _sign_in_browser,
    _wait_for_app_loading_cover,
)


@pytest.fixture
def mutation_page(users, character_read_shell_live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        base_url = character_read_shell_live_server
        _sign_in_browser(page, base_url, users["dm"])
        url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
        page.goto(f"{url}?page=notes")
        _wait_for_app_loading_cover(page)
        try:
            yield SimpleNamespace(page=page, url=url)
        finally:
            page.close()
            browser.close()


def _install_transport(page, fault="hold", *, failed_reconciliation=False):
    page.evaluate(
        r"""({fault, failedReconciliation}) => {
          const original = window.fetch.bind(window);
          const state = { posts: [], gets: [], ready: false, released: false, inFlight: 0, maxInFlight: 0 };
          window.__mutationTest = state;
          const replacement = (response, text, status=response.status) => {
            const value = new Response(text, { status, headers: response.headers });
            return new Proxy(value, { get(target, key) {
              if (key === 'url') return response.url;
              if (key === 'redirected') return response.redirected;
              const item = Reflect.get(target, key, target);
              return typeof item === 'function' ? item.bind(target) : item;
            }});
          };
          window.fetch = async (url, options={}) => {
            if (String(options.method || 'GET').toUpperCase() !== 'POST') {
              state.gets.push(String(url));
              if (failedReconciliation && state.released) throw new TypeError('GET unavailable');
              return original(url, options);
            }
            state.inFlight += 1;
            state.maxInFlight = Math.max(state.maxInFlight, state.inFlight);
            const payload = Array.from(options.body.entries()).map(([key, value]) => [key,
              typeof value === 'string' ? value : { name: value.name, size: value.size }]);
            state.posts.push({ url: String(url), payload });
            const first = state.posts.length === 1;
            // Feedback faults do not perform a mutation. Other faults happen after
            // the real server has handled the POST and followed its redirected GET.
            const response = first && /^feedback-/.test(fault)
              ? await original(window.location.href)
              : await original(url, options);
            const text = await response.clone().text();
            const parsed = new DOMParser().parseFromString(text, 'text/html');
            state.posts.at(-1).responseRevision = parsed.querySelector("input[name='expected_revision']")?.value;
            if (first) {
              state.ready = true;
              await new Promise(resolve => { state.release = () => { state.released = true; resolve(); }; });
            }
            state.inFlight -= 1;
            if (!first || fault === 'hold') return response;
            if (fault === 'fetch') throw new TypeError('acknowledgement lost after commit');
            if (fault === 'body') return new Proxy(response, { get(target, key) {
              if (key === 'text') return async () => { throw new TypeError('body stream failed'); };
              const item = Reflect.get(target, key, target);
              return typeof item === 'function' ? item.bind(target) : item;
            }});
            if (fault === 'malformed') return replacement(response, '<h1>Proxy failure</h1>');
            if (fault === 'revision') {
              parsed.querySelectorAll("input[name='expected_revision']").forEach(node => node.remove());
              return replacement(response, parsed.documentElement.outerHTML);
            }
            if (fault === 'bad-revision' || fault === 'stale-revision') {
              parsed.querySelectorAll("input[name='expected_revision']").forEach(node => {
                node.value = fault === 'bad-revision' ? 'not-a-revision' : options.body.get('expected_revision');
              });
              return replacement(response, parsed.documentElement.outerHTML);
            }
            if (fault === 'identity') {
              parsed.querySelectorAll('[data-character-read-subpage-link]').forEach(node => {
                node.href = node.getAttribute('href').replace('arden-march', 'another-character');
              });
              parsed.querySelector('h1').textContent = 'Other private character';
              return replacement(response, parsed.documentElement.outerHTML);
            }
            if (fault === 'access' || fault === 'signed-out') return replacement(response, '<h1>Access denied</h1>', fault === 'signed-out' ? 401 : 403);
            if (fault === 'status') return replacement(response, text, 500);
            if (fault === 'parse') {
              const parse = DOMParser.prototype.parseFromString;
              DOMParser.prototype.parseFromString = function(...args) {
                DOMParser.prototype.parseFromString = parse;
                throw new Error('injected parse failure');
              };
            }
            if (fault === 'mount') {
              const replace = Element.prototype.replaceChildren;
              let fail = true;
              Element.prototype.replaceChildren = function(...children) {
                if (fail && this.matches('.character-header')) {
                  fail = false;
                  throw new Error('injected chrome mount failure');
                }
                return replace.apply(this, children);
              };
            }
            if (/^feedback-/.test(fault)) {
              parsed.querySelector('[data-flash-stack-root]').innerHTML = '<div class="flash-error">Review this field before saving.</div>';
              const input = parsed.querySelector("textarea[name='player_notes_markdown']");
              input.setAttribute('aria-invalid', 'true');
              input.insertAdjacentHTML('afterend', '<p data-test-field-feedback>Notes need review.</p>');
              return replacement(response, parsed.documentElement.outerHTML, Number(fault.split('-')[1]));
            }
            return response;
          };
        }""",
        {"fault": fault, "failedReconciliation": failed_reconciliation},
    )


def _submit_note(page, value="First committed note"):
    page.locator("textarea[name='player_notes_markdown']").fill(value)
    page.get_by_role("button", name="Save note", exact=True).click()
    page.wait_for_function("() => window.__mutationTest.ready")


def _release(page):
    page.evaluate("window.__mutationTest.release()")


def _switch(page, section):
    from playwright.sync_api import expect

    page.locator(f"[data-character-read-target-subpage='{section}']").click()
    expect(page.locator("[data-character-read-shell-root]")).to_have_attribute(
        "data-character-read-shell-page", section
    )


def _posts(page):
    return page.evaluate("window.__mutationTest.posts")


def _install_protected_transport(page, *, invalid="", navigation=False):
    page.evaluate(r"""({invalid, navigation}) => {
      const original = window.fetch.bind(window);
      const state = window.__protectedTest = { posts: 0, ready: false };
      window.fetch = async (url, options={}) => {
        const post = options.method === 'POST';
        if (!post && !navigation) return original(url, options);
        if (post) state.posts += 1;
        const originalResponse = await original(window.location.href);
        const doc = new DOMParser().parseFromString(await originalResponse.text(), 'text/html');
        const panel = doc.querySelector('[data-character-read-shell-panel]');
        panel.dataset.characterWriteConflict = invalid === 'marker' ? 'another-character' : 'arden-march';
        panel.querySelector('.character-header').innerHTML = '<h1>Update not saved</h1>';
        panel.querySelector('.character-subpage-nav').replaceChildren();
        panel.querySelector('[data-character-read-section-content]').innerHTML = '<p>Protected response draft</p><textarea name="player_notes_markdown" readonly></textarea>';
        panel.querySelector('textarea').value = post ? options.body.get('player_notes_markdown') : 'Navigation recovery';
        if (post) {
          state.ready = true;
          await new Promise(resolve => { state.release = resolve; });
        }
        const headers = { 'Content-Type':'text/html' };
        if (invalid !== 'header') headers['X-Live-Mutation-Outcome'] = 'character-revision-conflict';
        const response = new Response(doc.documentElement.outerHTML, {status: invalid === 'status' ? 200 : 409, headers});
        return new Proxy(response, { get(target, key) {
          if (key === 'url') return invalid === 'origin' ? 'https://other.invalid/character' : invalid === 'path'
            ? new URL('/campaigns/linden-pass/characters/other', location.origin).href : String(url);
          const value = Reflect.get(target, key, target);
          return typeof value === 'function' ? value.bind(target) : value;
        }});
      };
    }""", {"invalid": invalid, "navigation": navigation})


@pytest.mark.parametrize("newer_navigation", [False, True], ids=["current", "newer-navigation"])
def test_protected_read_mode_preserves_queued_and_mounted_drafts_without_replay(mutation_page, newer_navigation):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_protected_transport(page)
    field = page.locator("textarea[name='player_notes_markdown']")
    field.fill("Submitted protected draft")
    page.get_by_role("button", name="Save note", exact=True).click()
    page.wait_for_function("() => window.__protectedTest.ready")
    field.fill("Queued protected draft")
    page.get_by_role("button", name="Save note", exact=True).click()
    field.fill("Newer mounted draft")
    if newer_navigation:
        _switch(page, "personal")
    page.evaluate("window.__protectedTest.release()")
    recovery = page.locator('[data-character-read-recovery]')
    expect(recovery).to_contain_text("Queued changes are paused")
    values = page.locator('textarea').evaluate_all("fields => fields.map(field => field.value)")
    assert {"Submitted protected draft", "Queued protected draft", "Newer mounted draft"} <= set(values)
    assert page.evaluate("window.__protectedTest.posts") == 1
    assert page.locator("[data-character-read-shell-panel]").is_visible()
    assert recovery.get_by_role('button').count() == 0
    if newer_navigation:
        expect(page.locator('[data-character-read-shell-root]')).to_have_attribute('data-character-read-shell-page', 'personal')
        assert 'page=personal' in page.url
    else:
        expect(page.get_by_role('heading', name='Update not saved', exact=True)).to_be_visible()


@pytest.mark.parametrize("invalid", ["marker", "header", "status", "origin", "path"])
def test_protected_read_mode_rejects_inexact_recovery_identity(mutation_page, invalid):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_protected_transport(page, invalid=invalid)
    page.locator("textarea[name='player_notes_markdown']").fill("Private mounted draft")
    page.get_by_role('button', name='Save note', exact=True).click()
    page.wait_for_function("() => window.__protectedTest.ready")
    page.evaluate("window.__protectedTest.release()")
    expect(page.locator('[data-character-read-recovery]')).to_contain_text('Character access could not be confirmed')
    assert page.get_by_role('heading', name='Update not saved', exact=True).count() == 0
    assert page.evaluate("window.__protectedTest.posts") == 1


def test_protected_navigation_response_retains_current_draft_without_authority_revision(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    page.locator("textarea[name='player_notes_markdown']").fill("Draft before protected navigation")
    _install_protected_transport(page, navigation=True)
    page.locator('[data-character-read-target-subpage="personal"]').click()
    expect(page.get_by_role('heading', name='Update not saved', exact=True)).to_be_visible()
    values = page.locator('textarea').evaluate_all('fields => fields.map(field => field.value)')
    assert 'Draft before protected navigation' in values
    assert page.locator('[data-character-read-shell-panel]').is_visible()
    assert page.evaluate('window.__protectedTest.posts') == 0


def _hold_restoration_frames(page):
    page.evaluate("""() => {
      const original = window.requestAnimationFrame.bind(window);
      const state = window.__restorationFrames = { callbacks: [], completed: false };
      window.requestAnimationFrame = callback => {
        state.callbacks.push(callback);
        return state.callbacks.length;
      };
      state.release = () => {
        window.requestAnimationFrame = original;
        for (const callback of state.callbacks.splice(0)) callback(performance.now());
        state.completed = true;
      };
    }""")


def _wait_for_reconciliation_mount(page):
    page.wait_for_function("""() =>
      document.querySelector("input[name='portrait_caption']") !== window.__priorPortraitField
      && window.__restorationFrames.callbacks.length > 0
    """)


def test_normal_mutation_fifo_preserves_distinct_forms_submitters_and_later_edits(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    page.goto(f"{mutation_page.url}?page=quick")
    _wait_for_app_loading_cover(page)
    _install_transport(page)
    page.evaluate("""() => {
      const form = document.querySelector("form[data-character-sheet-edit-form='vitals']");
      form.querySelector("input[name='current_hp']").value = '12';
      form.requestSubmit();
      form.requestSubmit();
    }""")
    page.wait_for_function("() => window.__mutationTest.ready")
    page.evaluate("""() => {
      const resource = document.querySelector("form[data-character-sheet-edit-form='resource']");
      resource.querySelector("input[name='current']").value = '1';
      const button = document.createElement('button');
      button.type = 'submit'; button.name = 'test_submitter'; button.value = 'resource-save';
      resource.append(button);
      resource.requestSubmit(button);
      resource.requestSubmit(button);
      const hp = document.querySelector("form[data-character-sheet-edit-form='vitals'] input[name='current_hp']");
      hp.value = '14';
      hp.dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    assert len(_posts(page)) == 1
    _release(page)
    page.wait_for_function("() => window.__mutationTest.posts.length === 3 && window.__mutationTest.inFlight === 0")
    expect(page.locator("form[data-character-sheet-edit-form='vitals'] input[name='current_hp']")).to_have_value("14")
    expect(page.locator("form[data-character-sheet-edit-form='resource'] input[name='current']").first).to_have_value("1")
    records = _posts(page)
    payloads = [dict(record["payload"]) for record in records]
    assert [payloads[0]["current_hp"], payloads[1]["current"], payloads[2]["current_hp"]] == ["12", "1", "14"]
    assert payloads[1]["test_submitter"] == "resource-save"
    assert all(payload["_csrf_token"] for payload in payloads)
    assert payloads[1]["expected_revision"] == records[0]["responseRevision"]
    assert payloads[2]["expected_revision"] == records[1]["responseRevision"]
    assert page.evaluate("window.__mutationTest.maxInFlight") == 1
    assert page.locator("[data-character-read-recovery]").is_hidden()


@pytest.mark.parametrize("navigation", ["cached", "fresh", "history"])
def test_normal_held_acknowledgement_keeps_latest_navigation_and_chrome(mutation_page, navigation):
    from playwright.sync_api import expect

    page = mutation_page.page
    if navigation != "fresh":
        _switch(page, "portrait")
        _switch(page, "notes")
    _install_transport(page)
    _submit_note(page)
    if navigation == "history":
        page.go_back()
        expect(page).to_have_url(re.compile(r"page=portrait"))
        page.go_forward()
        expect(page).to_have_url(re.compile(r"page=notes"))
        page.go_back()
    else:
        _switch(page, "portrait")
    expect(page.locator("input[name='portrait_caption']")).to_be_visible()
    page.locator("input[name='portrait_caption']").fill("Later portrait draft")
    page.locator("input[name='portrait_caption']").focus()
    page.locator("input[name='portrait_caption']").evaluate("field => field.setSelectionRange(3, 9)")
    history_length = page.evaluate("window.history.length")
    page.evaluate("window.__priorPortraitField = document.querySelector(\"input[name='portrait_caption']\")")
    _hold_restoration_frames(page)
    _release(page)
    _wait_for_reconciliation_mount(page)
    page.evaluate("window.__restorationFrames.release()")
    expect(page.locator("input[name='portrait_caption']")).to_have_value("Later portrait draft")
    expect(page).to_have_url(re.compile(r"page=portrait"))
    expect(page.locator("[data-character-read-shell-root]")).to_have_attribute("data-character-read-shell-page", "portrait")
    expect(page.locator("input[name='portrait_caption']")).to_be_focused()
    assert page.locator("input[name='portrait_caption']").evaluate("field => [field.selectionStart, field.selectionEnd]") == [3, 9]
    assert page.evaluate("window.history.length") == history_length
    assert len(_posts(page)) == 1
    assert page.locator("[data-flash-stack-root]").inner_text().strip() != "Note saved."
    assert not page.locator("[data-character-read-shell-root]").get_attribute("aria-busy")


@pytest.mark.parametrize("navigation", ["cached", "fresh", "history"])
def test_reconciliation_restoration_preserves_newer_selection_before_its_frame(mutation_page, navigation):
    from playwright.sync_api import expect

    page = mutation_page.page
    if navigation != "fresh":
        _switch(page, "portrait")
        _switch(page, "notes")
    _install_transport(page)
    _submit_note(page)
    if navigation == "history":
        page.go_back()
        expect(page).to_have_url(re.compile(r"page=portrait"))
    else:
        _switch(page, "portrait")
    field = page.locator("input[name='portrait_caption']")
    field.fill("Later portrait draft")
    field.evaluate("field => { field.focus(); field.setSelectionRange(3, 9); }")
    page.evaluate("window.__priorPortraitField = document.querySelector(\"input[name='portrait_caption']\")")
    _hold_restoration_frames(page)
    history_length = page.evaluate("history.length")
    _release(page)
    _wait_for_reconciliation_mount(page)
    field.evaluate("field => { field.focus(); field.setSelectionRange(4, 11); }")
    page.evaluate("window.__restorationFrames.release()")
    assert field.evaluate("field => [field.selectionStart, field.selectionEnd]") == [4, 11]
    expect(field).to_have_value("Later portrait draft")
    expect(field).to_be_focused()
    expect(page).to_have_url(re.compile(r"page=portrait"))
    assert page.evaluate("history.length") == history_length
    assert len(_posts(page)) == 1
    assert page.locator("[data-flash-stack-root]").inner_text().strip() != "Note saved."


@pytest.mark.parametrize("destination", ["retained", "detached", "reattached"])
def test_cached_restoration_frame_cannot_outlive_newer_selection_or_navigation(mutation_page, destination):
    from playwright.sync_api import expect

    page = mutation_page.page
    _switch(page, "portrait")
    field = page.locator("input[name='portrait_caption']")
    field.fill("Later portrait draft")
    field.evaluate("field => { field.focus(); field.setSelectionRange(3, 9); }")
    # Programmatic link activation keeps the authored field as the cached focus.
    page.locator("[data-character-read-target-subpage='notes']").evaluate("link => link.click()")
    expect(page.locator("textarea[name='player_notes_markdown']")).to_be_visible()
    _hold_restoration_frames(page)
    page.locator("[data-character-read-target-subpage='portrait']").evaluate("link => link.click()")
    expect(field).to_be_visible()
    page.wait_for_function("window.__restorationFrames.callbacks.length > 0")
    field.evaluate("field => { field.focus(); field.setSelectionRange(4, 11); }")
    if destination != "retained":
        page.locator("[data-character-read-target-subpage='notes']").evaluate("link => link.click()")
        notes = page.locator("textarea[name='player_notes_markdown']")
        notes.fill("New destination draft")
        notes.focus()
    if destination == "reattached":
        page.locator("[data-character-read-target-subpage='portrait']").evaluate("link => link.click()")
        field.evaluate("field => { field.focus(); field.setSelectionRange(5, 12); }")
    page.evaluate("window.__restorationFrames.release()")
    if destination == "detached":
        expect(notes).to_be_focused()
        expect(notes).to_have_value("New destination draft")
        expect(page).to_have_url(re.compile(r"page=notes"))
    else:
        expect(field).to_be_focused()
        expect(field).to_have_value("Later portrait draft")
        assert field.evaluate("field => [field.selectionStart, field.selectionEnd]") == ([5, 12] if destination == "reattached" else [4, 11])
        expect(page).to_have_url(re.compile(r"page=portrait"))


@pytest.mark.parametrize("fault", ["fetch", "body", "malformed", "revision", "bad-revision", "stale-revision", "parse", "mount", "status"])
def test_normal_unknown_outcome_reconciles_once_retains_drafts_and_never_replays(mutation_page, fault):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, fault)
    _submit_note(page)
    page.locator("textarea[name='player_notes_markdown']").fill("Later queued note")
    page.get_by_role("button", name="Save note", exact=True).click()
    page.locator("textarea[name='player_notes_markdown']").fill("Still newer unsent note")
    _release(page)
    recovery = page.locator("[data-character-read-recovery]")
    expect(recovery).to_contain_text("Inspect the current sheet")
    expect(recovery.get_by_role("button", name="Continue queued changes")).to_be_visible()
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Still newer unsent note")
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 1
    server_html = page.request.get(f"{mutation_page.url}?page=notes").text()
    assert "First committed note" in server_html
    assert "Still newer unsent note" not in server_html
    # A fresh GET does not drain the queue; this explicit continuation does.
    recovery.get_by_role("button", name="Continue queued changes").click()
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Still newer unsent note")
    assert dict(_posts(page)[1]["payload"])["player_notes_markdown"] == "Later queued note"


@pytest.mark.parametrize("status", [400, 409, 422])
def test_normal_validation_feedback_pauses_queue_and_preserves_field_feedback(mutation_page, status):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, f"feedback-{status}")
    _submit_note(page, "Rejected draft")
    page.locator("textarea[name='player_notes_markdown']").fill("Queued correction")
    page.get_by_role("button", name="Save note", exact=True).click()
    _release(page)
    expect(page.locator("[data-test-field-feedback]")).to_have_text("Notes need review.")
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Queued correction")
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("Queued changes are paused")
    assert len(_posts(page)) == 1
    assert page.evaluate("window.__mutationTest.gets") == []


@pytest.mark.parametrize("fault", ["access", "signed-out", "identity"])
def test_normal_access_identity_change_stops_queue_without_exposing_response(mutation_page, fault):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, fault)
    _submit_note(page)
    page.locator("textarea[name='player_notes_markdown']").fill("Private queued draft")
    page.get_by_role("button", name="Save note", exact=True).click()
    _release(page)
    expect(page.locator("[data-character-read-shell-panel]")).to_be_hidden()
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("access")
    assert "Other private character" not in page.locator("body").inner_text()
    assert "Private queued draft" not in page.locator("body").inner_text()
    assert len(_posts(page)) == 1
    assert page.locator("[data-character-read-recovery] button").count() == 0


def test_normal_failed_reconciliation_retains_live_file_and_never_repeats_post(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, "fetch", failed_reconciliation=True)
    _submit_note(page)
    _switch(page, "portrait")
    file = page.locator("input[name='portrait_file']")
    file.set_input_files({"name": "retained.png", "mimeType": "image/png", "buffer": b"actual retained file bytes"})
    page.locator("input[name='portrait_caption']").fill("Unsent file caption")
    page.evaluate("window.__retainedFile = document.querySelector(\"input[name='portrait_file']\")")
    _release(page)
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("could not be confirmed")
    page.wait_for_function("() => window.__mutationTest.gets.length === 2")
    assert file.evaluate("field => field === window.__retainedFile")
    assert file.evaluate("field => field.files[0].name") == "retained.png"
    expect(page.locator("input[name='portrait_caption']")).to_have_value("Unsent file caption")
    assert len(_posts(page)) == 1
    assert page.locator("[data-character-read-recovery] button").count() == 0


def test_normal_queued_file_survives_removed_form_and_keeps_payload(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page)
    _submit_note(page)
    _switch(page, "portrait")
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=")
    page.locator("input[name='portrait_file']").set_input_files({"name": "queued.png", "mimeType": "image/png", "buffer": png})
    page.locator("input[name='portrait_caption']").fill("Queued portrait caption")
    page.get_by_role("button", name="Save portrait", exact=True).click()
    _switch(page, "notes")
    page.locator("textarea[name='player_notes_markdown']").fill("Unsent note after upload queued")
    _release(page)
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    expect(page).to_have_url(re.compile(r"page=notes"))
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Unsent note after upload queued")
    payload = dict(_posts(page)[1]["payload"])
    assert payload["portrait_file"] == {"name": "queued.png", "size": len(png)}
    assert payload["portrait_caption"] == "Queued portrait caption"
    assert payload["expected_revision"] == _posts(page)[0]["responseRevision"]
    assert "Queued portrait caption" in page.request.get(f"{mutation_page.url}?page=portrait").text()


def test_normal_character_no_javascript_post_keeps_native_form_contract(users, character_read_shell_live_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(java_script_enabled=False)
        try:
            base = character_read_shell_live_server
            _sign_in_browser(page, base, users["dm"])
            page.goto(f"{base}/campaigns/linden-pass/characters/arden-march?page=notes")
            page.locator("textarea[name='player_notes_markdown']").fill("Native submitted note")
            page.get_by_role("button", name="Save note", exact=True).click()
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Native submitted note")
        finally:
            browser.close()


def test_normal_confirmed_revision_survives_read_only_destination_with_queued_save(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page)
    _submit_note(page)
    page.locator("textarea[name='player_notes_markdown']").fill("Queued after first")
    page.get_by_role("button", name="Save note", exact=True).click()
    _switch(page, "personal")
    assert page.locator("[data-character-read-section-content] input[name='expected_revision']").count() == 0
    _release(page)
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    expect(page).to_have_url(re.compile(r"page=personal"))
    records = _posts(page)
    assert dict(records[1]["payload"])["expected_revision"] == records[0]["responseRevision"]
    assert "Queued after first" in page.request.get(f"{mutation_page.url}?page=notes").text()


def test_normal_successful_reconciliation_retains_actual_file_selection(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page)
    _submit_note(page)
    _switch(page, "portrait")
    file = page.locator("input[name='portrait_file']")
    file.set_input_files({"name": "unsent.png", "mimeType": "image/png", "buffer": b"live selected bytes"})
    page.locator("input[name='portrait_caption']").fill("Latest unsent caption")
    page.evaluate("window.__retainedFile = document.querySelector(\"input[name='portrait_file']\"); window.__oldSection = document.querySelector('[data-character-read-section-content]')")
    _release(page)
    page.wait_for_function("() => document.querySelector('[data-character-read-section-content]') !== window.__oldSection")
    assert file.evaluate("field => field === window.__retainedFile")
    assert file.evaluate("field => field.files[0].name") == "unsent.png"
    assert file.evaluate("field => field.files[0].text()") == "live selected bytes"
    expect(page.locator("input[name='portrait_caption']")).to_have_value("Latest unsent caption")
    assert len(_posts(page)) == 1


def test_normal_late_fresh_navigation_read_reconciles_after_confirmed_post(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page)
    _submit_note(page)
    page.evaluate("""() => {
      const original = window.fetch.bind(window);
      let held = false;
      window.fetch = async (url, options={}) => {
        const response = await original(url, options);
        if (!held && String(url).includes('page=portrait') && !options.method) {
          held = true;
          const text = await response.text();
          const doc = new DOMParser().parseFromString(text, 'text/html');
          doc.querySelector('.character-header h1').textContent = 'Stale navigation header';
          doc.querySelectorAll("input[name='expected_revision']").forEach(node => { node.value = '0'; });
          window.__navigationReadReady = true;
          await new Promise(resolve => { window.__releaseNavigationRead = resolve; });
          const replacement = new Response(doc.documentElement.outerHTML, {status:200});
          return new Proxy(replacement, { get(target, key) {
            if (key === 'url') return response.url;
            const value = Reflect.get(target,key,target);
            return typeof value === 'function' ? value.bind(target) : value;
          }});
        }
        return response;
      };
    }""")
    page.locator("[data-character-read-target-subpage='portrait']").click()
    page.wait_for_function("() => window.__navigationReadReady")
    _release(page)
    page.wait_for_function("() => !document.querySelector('form[data-character-read-submitting]')")
    page.evaluate("window.__releaseNavigationRead()")
    expect(page).to_have_url(re.compile(r"page=portrait"))
    expect(page.locator(".character-header h1")).to_have_text("Arden March")
    assert len(page.evaluate("window.__mutationTest.gets")) == 2
    assert len(_posts(page)) == 1


def test_normal_unknown_reconciliation_does_not_replace_a_newer_navigation(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, "fetch")
    _submit_note(page)
    page.evaluate("""() => {
      const original = window.fetch.bind(window);
      let held = false;
      window.fetch = async (url, options={}) => {
        const response = await original(url, options);
        if (!held && !options.method && String(url).includes('page=notes')) {
          held = true;
          window.__reconcileReadReady = true;
          await new Promise(resolve => { window.__releaseReconcileRead = resolve; });
        }
        return response;
      };
    }""")
    _release(page)
    page.wait_for_function("() => window.__reconcileReadReady")
    _switch(page, "portrait")
    page.locator("input[name='portrait_caption']").fill("Navigation during reconciliation")
    page.evaluate("window.__releaseReconcileRead()")
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("could not be confirmed")
    expect(page).to_have_url(re.compile(r"page=portrait"))
    expect(page.locator("input[name='portrait_caption']")).to_have_value("Navigation during reconciliation")
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 2


def test_normal_uncertain_post_requires_explicit_repeat_even_after_reconciliation(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, "fetch")
    _submit_note(page, "Explicit repeat only")
    _release(page)
    repeat = page.get_by_role("button", name="Repeat submitted change", exact=True)
    expect(repeat).to_be_visible()
    assert len(_posts(page)) == 1
    repeat.click()
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    expect(page.locator("[data-character-read-recovery]")).to_be_hidden()
    assert dict(_posts(page)[1]["payload"])["player_notes_markdown"] == "Explicit repeat only"


@pytest.mark.parametrize("redirected", [False, True])
def test_normal_busy_unknown_outcome_never_retries_post_and_bounds_gets(mutation_page, redirected):
    from playwright.sync_api import expect

    page = mutation_page.page
    page.evaluate("""(redirected) => {
      const original = window.fetch.bind(window);
      const state = {posts:0, gets:0};
      window.__busyMutation = state;
      window.fetch = async (url, options={}) => {
        const post = options.method === 'POST';
        if (post) {
          state.posts += 1;
          await original(url, options);
        } else {
          state.gets += 1;
          if (!redirected) return original(url, options);
        }
        const response = new Response('<h1>Busy</h1>', {status:503, headers:{'Retry-After':'0'}});
        return new Proxy(response, {get(target,key) {
          if(key === 'url') return post && !redirected ? String(url) : window.location.href;
          if(key === 'redirected') return post && redirected;
          const value = Reflect.get(target,key,target);
          return typeof value === 'function' ? value.bind(target) : value;
        }});
      };
    }""", redirected)
    page.locator("textarea[name='player_notes_markdown']").fill("Busy committed note")
    page.get_by_role("button", name="Save note", exact=True).click()
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("could not be confirmed", timeout=10000)
    expected_gets = 4 if redirected else 1
    page.wait_for_function("count => window.__busyMutation.gets === count", arg=expected_gets)
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value("Busy committed note")
    assert page.evaluate("window.__busyMutation.posts") == 1
    assert page.evaluate("window.__busyMutation.gets") == expected_gets


def test_normal_edit_back_to_original_is_not_overwritten_by_held_acknowledgement(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    notes = page.locator("textarea[name='player_notes_markdown']")
    original = notes.input_value()
    _install_transport(page)
    _submit_note(page, "New server note")
    notes.fill(original)
    _release(page)
    expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")
    expect(notes).to_have_value(original)
    assert "New server note" in page.request.get(f"{mutation_page.url}?page=notes").text()
    assert len(_posts(page)) == 1


def test_normal_vitals_forms_with_shared_action_keep_distinct_autosubmit_drafts(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    page.goto(f"{mutation_page.url}?page=quick")
    _wait_for_app_loading_cover(page)
    _install_transport(page)
    page.evaluate("""() => {
      const hp = document.querySelector("input[name='current_hp']");
      hp.value = '11'; hp.form.requestSubmit();
    }""")
    page.wait_for_function("() => window.__mutationTest.ready")
    page.evaluate("""() => {
      const temp = document.querySelector("input[name='temp_hp']");
      temp.value = '3'; temp.dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    _release(page)
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    expect(page.locator("input[name='current_hp']")).to_have_value("11")
    expect(page.locator("input[name='temp_hp']")).to_have_value("3")
    records = _posts(page)
    assert "current_hp" in dict(records[0]["payload"])
    assert "temp_hp" in dict(records[1]["payload"])
    assert dict(records[1]["payload"])["expected_revision"] == records[0]["responseRevision"]
    assert page.evaluate("window.__mutationTest.maxInFlight") == 1


def test_normal_correction_after_feedback_can_continue_without_repeating_rejected_payload(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, "feedback-422")
    _submit_note(page, "Rejected original")
    _release(page)
    expect(page.locator("[data-test-field-feedback]")).to_be_visible()
    page.locator("textarea[name='player_notes_markdown']").fill("Corrected after feedback")
    page.get_by_role("button", name="Save note", exact=True).click()
    continuation = page.get_by_role("button", name="Continue queued changes", exact=True)
    expect(continuation).to_be_visible()
    assert len(_posts(page)) == 1
    continuation.click()
    page.wait_for_function("() => window.__mutationTest.posts.length === 2 && window.__mutationTest.inFlight === 0")
    assert dict(_posts(page)[1]["payload"])["player_notes_markdown"] == "Corrected after feedback"
    expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")


def test_normal_unknown_outcome_during_staged_navigation_has_one_mount_owner(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    _install_transport(page, "fetch")
    _submit_note(page)
    page.evaluate("""() => {
      const original = window.requestAnimationFrame.bind(window);
      window.__heldFrames = [];
      window.requestAnimationFrame = callback => {
        if (document.querySelector("[data-character-read-section-content] input[name='portrait_caption']")) {
          window.__heldFrames.push(callback);
          return window.__heldFrames.length;
        }
        return original(callback);
      };
      window.__releaseFrames = () => {
        window.requestAnimationFrame = original;
        for (const callback of window.__heldFrames.splice(0)) original(callback);
      };
    }""")
    page.locator("[data-character-read-target-subpage='portrait']").click()
    page.wait_for_function("() => window.__heldFrames.length > 0", polling=50)
    _release(page)
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("could not be confirmed")
    page.evaluate("window.__releaseFrames()")
    expect(page).to_have_url(re.compile(r"page=portrait"))
    expect(page.locator("[data-character-read-shell-root]")).to_have_attribute("data-character-read-shell-page", "portrait")
    expect(page.locator("input[name='portrait_caption']")).to_be_visible()
    expect(page.locator("textarea[name='player_notes_markdown']")).to_have_count(0)
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 2


def test_normal_post_submit_focus_key_restores_stable_navigation_target(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    features = page.locator("[data-live-focus-key='divine-avatar-forms-features-nav']")
    expect(features).to_be_visible()
    page.locator("form[data-character-sheet-edit-form='notes']").evaluate(
        "form => { form.dataset.postSubmitFocusKey = 'divine-avatar-forms-features-nav'; }"
    )
    _install_transport(page)
    _submit_note(page, "Restore explicit focus after save")
    _release(page)
    expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")
    expect(features).to_be_focused()
    assert len(_posts(page)) == 1


def test_post_submit_focus_target_cannot_replace_a_newer_user_selection(mutation_page):
    from playwright.sync_api import expect

    page = mutation_page.page
    page.locator("form[data-character-sheet-edit-form='notes']").evaluate(
        "form => { form.dataset.postSubmitFocusKey = 'divine-avatar-forms-features-nav'; }"
    )
    _install_transport(page)
    _submit_note(page, "Explicit target then newer selection")
    page.evaluate("window.__priorNotesField = document.querySelector(\"textarea[name='player_notes_markdown']\")")
    _hold_restoration_frames(page)
    _release(page)
    page.wait_for_function("""() =>
      document.querySelector("textarea[name='player_notes_markdown']") !== window.__priorNotesField
      && window.__restorationFrames.callbacks.length > 0
    """)
    notes = page.locator("textarea[name='player_notes_markdown']")
    notes.evaluate("field => { field.focus(); field.setSelectionRange(3, 9); }")
    page.evaluate("window.__restorationFrames.release()")
    expect(notes).to_be_focused()
    assert notes.evaluate("field => [field.selectionStart, field.selectionEnd]") == [3, 9]
    expect(notes).to_have_value("Explicit target then newer selection")
    expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")
    assert len(_posts(page)) == 1


# R1 promotes the frozen verifier's two regressions and exercises the shared
# field/default and reversible-mount branches without an external test import.
@pytest.mark.parametrize(
    ("initial", "newer_unsent"),
    [("", None), ("Original nonempty note", None), ("", "Newer unsent edit after queuing")],
)
def test_queued_return_to_original_remains_visible_after_both_confirmed_saves(
    mutation_page, initial, newer_unsent
):
    import html
    from playwright.sync_api import expect

    page = mutation_page.page
    notes = page.locator("textarea[name='player_notes_markdown']")
    if initial:
        notes.fill(initial)
        page.get_by_role("button", name="Save note", exact=True).click()
        expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text("Note saved.")
        page.reload()
        _wait_for_app_loading_cover(page)
    original = notes.input_value()
    assert original == initial
    _install_transport(page)
    _submit_note(page, "Intermediate committed note")
    notes.fill(original)
    page.get_by_role("button", name="Save note", exact=True).click()
    if newer_unsent is not None:
        notes.fill(newer_unsent)
    _release(page)
    page.wait_for_function("""() => window.__mutationTest.posts.length === 2
      && !!window.__mutationTest.posts[1].responseRevision
      && document.querySelector("input[name='expected_revision']").value
        === window.__mutationTest.posts[1].responseRevision""")
    server_html = page.request.get(f"{mutation_page.url}?page=notes").text()
    server_value = html.unescape(re.search(
        r'<textarea name="player_notes_markdown">(.*?)</textarea>', server_html, re.S
    ).group(1))
    records = _posts(page)
    assert server_value == original
    assert len(records) == 2
    assert [dict(record["payload"])["player_notes_markdown"] for record in records] == [
        "Intermediate committed note", original
    ]
    assert dict(records[1]["payload"])["expected_revision"] == records[0]["responseRevision"]
    assert page.evaluate("window.__mutationTest.maxInFlight") == 1
    expect(notes).to_have_value(original if newer_unsent is None else newer_unsent)
    expect(page.locator("[data-character-read-recovery]")).to_be_hidden()


@pytest.mark.parametrize("kind", ["checkbox", "radio", "select", "multiple"])
def test_queued_default_field_branches_retain_payload_and_final_selection(mutation_page, kind):
    from playwright.sync_api import expect

    page = mutation_page.page
    # The real notes POST/revision/redirect remains authoritative. An additional
    # controlled response field supplies the other editable field branches.
    page.evaluate("""kind => {
      const state = { kind, serverValues: kind === 'checkbox' ? [] : kind === 'multiple' ? ['a','c'] : ['a'] };
      window.__defaultBranch = state;
      const add = (root, values) => {
        const form = root.querySelector("form[data-character-sheet-edit-form='notes']");
        if (!form) return;
        const wrap = document.createElement('fieldset');
        wrap.dataset.defaultBranch = '';
        if (kind === 'checkbox') {
          wrap.innerHTML = '<label>Choice<input name="contract_value" type="checkbox" value="yes"></label>';
          wrap.querySelector('input').defaultChecked = values.includes('yes');
        } else if (kind === 'radio') {
          wrap.innerHTML = '<label>A<input name="contract_value" type="radio" value="a"></label><label>B<input name="contract_value" type="radio" value="b"></label>';
          wrap.querySelectorAll('input').forEach(field => { field.defaultChecked = values.includes(field.value); });
        } else {
          wrap.innerHTML = '<label>Choices<select name="contract_value"><option value="a">A</option><option value="b">B</option><option value="c">C</option></select></label>';
          const select = wrap.querySelector('select');
          select.multiple = kind === 'multiple';
          Array.from(select.options).forEach(option => { option.defaultSelected = values.includes(option.value); });
        }
        form.append(wrap);
      };
      add(document, state.serverValues);
      state.set = values => {
        const root = document.querySelector('[data-default-branch]');
        root.querySelectorAll('input').forEach(field => { field.checked = values.includes(field.value); });
        root.querySelectorAll('option').forEach(option => { option.selected = values.includes(option.value); });
      };
      const original = window.fetch.bind(window);
      window.fetch = async (url, options={}) => {
        const response = await original(url, options);
        if (options.method !== 'POST') return response;
        state.serverValues = options.body.getAll('contract_value');
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        add(doc, state.serverValues);
        const replacement = new Response(doc.documentElement.outerHTML, {status:response.status,headers:response.headers});
        return new Proxy(replacement, {get(target,key) {
          if (key === 'url') return response.url;
          if (key === 'redirected') return response.redirected;
          const value=Reflect.get(target,key,target);
          return typeof value === 'function' ? value.bind(target) : value;
        }});
      };
    }""", kind)
    original = [] if kind == "checkbox" else ["a", "c"] if kind == "multiple" else ["a"]
    intermediate = ["yes"] if kind == "checkbox" else ["b"]
    _install_transport(page)
    page.evaluate("values => window.__defaultBranch.set(values)", intermediate)
    _submit_note(page, "First synthetic branch save")
    page.evaluate("values => window.__defaultBranch.set(values)", original)
    page.locator("textarea[name='player_notes_markdown']").fill("Final synthetic branch save")
    page.get_by_role("button", name="Save note", exact=True).click()
    _release(page)
    page.wait_for_function("""() => window.__mutationTest.posts.length === 2
      && !!window.__mutationTest.posts[1].responseRevision
      && document.querySelector("input[name='expected_revision']").value === window.__mutationTest.posts[1].responseRevision""")
    assert page.evaluate("new FormData(document.querySelector(\"form[data-character-sheet-edit-form='notes']\")).getAll('contract_value')") == original
    assert page.evaluate("window.__defaultBranch.serverValues") == original
    records = _posts(page)
    assert [[value for key, value in record["payload"] if key == "contract_value"] for record in records] == [intermediate, original]
    assert dict(records[1]["payload"])["expected_revision"] == records[0]["responseRevision"]
    assert page.evaluate("window.__mutationTest.maxInFlight") == 1
    expect(page.locator("[data-character-read-recovery]")).to_be_hidden()


def _hold_portrait_then_select_newer_file(page, *, failed_reconciliation=False):
    _install_transport(page, failed_reconciliation=failed_reconciliation)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=")
    file_input = page.locator("input[name='portrait_file']")
    file_input.set_input_files({"name": "submitted.png", "mimeType": "image/png", "buffer": png})
    page.locator("input[name='portrait_caption']").fill("Submitted portrait caption")
    page.get_by_role("button", name="Save portrait", exact=True).click()
    page.wait_for_function("() => window.__mutationTest.ready")
    file_input.set_input_files({"name": "newer-unsent.png", "mimeType": "image/png", "buffer": b"newer unsent actual file bytes"})
    caption = page.locator("input[name='portrait_caption']")
    caption.fill("Newer unsent caption")
    caption.focus()
    caption.evaluate("field => field.setSelectionRange(2, 8)")
    return file_input


@pytest.mark.parametrize(
    ("history_fault", "failed_reconciliation"),
    [("before", False), ("after", False), ("after", True)],
)
def test_post_mount_failure_after_file_transfer_preserves_newer_live_selection(
    mutation_page, history_fault, failed_reconciliation
):
    from playwright.sync_api import expect

    page = mutation_page.page
    _switch(page, "portrait")
    file_input = _hold_portrait_then_select_newer_file(page, failed_reconciliation=failed_reconciliation)
    page.evaluate("""fault => {
      const state = {
        input: document.querySelector("input[name='portrait_file']"),
        section: document.querySelector('[data-character-read-section-content]'),
        faults: 0, rollback: null,
      };
      state.file = state.input.files[0];
      state.form = state.input.form;
      state.fields = Array.from(state.form.elements);
      window.__repairMount = state;
      const originalReplace = window.history.replaceState.bind(window.history);
      originalReplace({...window.history.state, repairHistoryMarker:'prior'}, '', window.location.href);
      state.href = window.location.href;
      window.history.replaceState = (...args) => {
        if (!state.faults && document.querySelector('[data-character-read-section-content]') !== state.section) {
          state.faults += 1;
          state.rejected = document.querySelector('[data-character-read-section-content]');
          if (fault === 'after') originalReplace(...args);
          throw new Error('one-shot History failure after File transfer');
        }
        return originalReplace(...args);
      };
      const originalFetch = window.fetch.bind(window);
      window.fetch = (url, options={}) => {
        if (!options.method && !state.rollback) {
          const shell = document.querySelector('[data-character-read-shell-root]');
          state.rollback = {
            priorSection: document.querySelector('[data-character-read-section-content]') === state.section,
            inputConnected: state.input.isConnected, sameOwner: state.input.form === state.form,
            fieldsIntact: Array.from(state.form.elements).every((field,index) => field === state.fields[index]),
            historyMarker: window.history.state.repairHistoryMarker,
            historyPage: window.history.state.characterReadSubpage, href: window.location.href,
            shellPage: shell.dataset.characterReadShellPage,
            rejectedCached: Array.from(window.__playerWikiCharacterReadShell.cache.values()).some(entry => entry.section === state.rejected),
            caption: document.querySelector("input[name='portrait_caption']").value,
          };
        }
        return originalFetch(url, options);
      };
    }""", history_fault)
    _release(page)
    recovery = page.locator("[data-character-read-recovery]")
    expect(recovery).to_contain_text("could not be confirmed")
    if not failed_reconciliation:
        expect(page.get_by_role("button", name="Repeat submitted change", exact=True)).to_be_visible()
    else:
        page.wait_for_function("() => window.__repairMount.rollback !== null && window.__mutationTest.gets.length === 1")
        expect(recovery.locator("button")).to_have_count(0)
    observed = page.evaluate("""() => {
      const state=window.__repairMount, field=document.querySelector("input[name='portrait_file']");
      return {faults:state.faults, rollback:state.rollback, sameInput:field===state.input,
        sameFile:field.files[0]===state.file, connected:field.isConnected,
        selectedNames:Array.from(field.files).map(file=>file.name),
        caption:document.querySelector("input[name='portrait_caption']").value};
    }""")
    assert observed["faults"] == 1
    assert observed["sameInput"] and observed["sameFile"] and observed["connected"]
    assert observed["selectedNames"] == ["newer-unsent.png"]
    assert file_input.evaluate("field => field.files[0].text()") == "newer unsent actual file bytes"
    assert observed["caption"] == "Newer unsent caption"
    assert observed["rollback"] == {
        "priorSection": True, "inputConnected": True, "sameOwner": True, "fieldsIntact": True,
        "historyMarker": "prior", "historyPage": "portrait", "href": f"{mutation_page.url}?page=portrait",
        "shellPage": "portrait", "rejectedCached": False, "caption": "Newer unsent caption",
    }
    expect(page.locator("input[name='portrait_caption']")).to_be_focused()
    assert page.locator("input[name='portrait_caption']").evaluate("field => [field.selectionStart, field.selectionEnd]") == [2, 8]
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 1
    expect(page).to_have_url(re.compile(r"page=portrait"))
    server_html = page.request.get(f"{mutation_page.url}?page=portrait").text()
    assert "Submitted portrait caption" in server_html
    assert "Newer unsent caption" not in server_html


@pytest.mark.parametrize("failure_side", ["before", "after"])
def test_partial_live_file_transfers_roll_back_all_owners_and_positions(mutation_page, failure_side):
    from playwright.sync_api import expect

    page = mutation_page.page
    _switch(page, "portrait")
    # Add one ignored upload field to the real form and its real server response,
    # allowing two consecutive retained File moves without a production fixture.
    page.evaluate("""() => {
      const add = root => {
        const form=root.querySelector("input[name='portrait_file']")?.form;
        if (form && !form.querySelector("input[name='supporting_file']")) {
          const label=document.createElement('label'); label.textContent='Supporting file';
          const field=document.createElement('input');field.type='file';field.name='supporting_file';
          label.append(field);form.append(label);
        }
      };
      add(document);
      const original=window.fetch.bind(window);
      window.fetch=async (url, options={}) => {
        const response=await original(url,options);
        const doc=new DOMParser().parseFromString(await response.text(),'text/html');
        add(doc);
        const replacement=new Response(doc.documentElement.outerHTML,{status:response.status,headers:response.headers});
        return new Proxy(replacement,{get(target,key){
          if(key==='url')return response.url;if(key==='redirected')return response.redirected;
          const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
        }});
      };
    }""")
    _hold_portrait_then_select_newer_file(page, failed_reconciliation=True)
    page.locator("input[name='supporting_file']").set_input_files({
        "name": "supporting.bin", "mimeType": "application/octet-stream", "buffer": b"second live selection"
    })
    page.evaluate("""side => {
      const inputs=Array.from(document.querySelectorAll("input[type='file']"));
      const state={inputs, files:inputs.map(field=>field.files[0]),
        parents:inputs.map(field=>field.parentNode), next:inputs.map(field=>field.nextSibling),
        form:inputs[0].form, fields:Array.from(inputs[0].form.elements), moves:0, faults:0};
      window.__repairTransfers=state;
      const original=Element.prototype.replaceWith;
      Element.prototype.replaceWith=function(...nodes){
        if(this instanceof HTMLInputElement && this.type==='file' && inputs.includes(nodes[0]) && this!==nodes[0]){
          state.moves += 1;
          if(state.moves===2 && !state.faults){
            state.faults += 1;
            if(side==='after')original.apply(this,nodes);
            throw new Error('one-shot partial File transfer failure');
          }
        }
        return original.apply(this,nodes);
      };
    }""", failure_side)
    _release(page)
    expect(page.locator("[data-character-read-recovery]")).to_contain_text("could not be confirmed")
    page.wait_for_function("() => window.__mutationTest.gets.length === 1")
    state = page.evaluate("""() => {
      const state=window.__repairTransfers;
      return {faults:state.faults, moves:state.moves,
        allIntact:state.inputs.every((field,index)=>field.isConnected && field.form===state.form
          && field.parentNode===state.parents[index] && field.nextSibling===state.next[index]
          && field.files[0]===state.files[index]),
        fieldsIntact:Array.from(state.form.elements).length===state.fields.length
          && Array.from(state.form.elements).every((field,index)=>field===state.fields[index]),
        names:state.inputs.map(field=>field.files[0]?.name),
        caption:document.querySelector("input[name='portrait_caption']").value};
    }""")
    assert state == {"faults":1,"moves":2,"allIntact":True,"fieldsIntact":True,
        "names":["newer-unsent.png","supporting.bin"],"caption":"Newer unsent caption"}
    assert page.locator("input[name='supporting_file']").evaluate("field => field.files[0].text()") == "second live selection"
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 1
    expect(page.locator("[data-character-read-recovery] button")).to_have_count(0)


@pytest.mark.parametrize("history_fault", ["before", "after"])
def test_fresh_navigation_history_failure_retains_live_file_until_explicit_retry(mutation_page, history_fault):
    from playwright.sync_api import expect

    page = mutation_page.page
    _switch(page, "portrait")
    page.locator("input[name='portrait_file']").set_input_files({
        "name": "retained-navigation.png", "mimeType": "image/png", "buffer": b"retained navigation file bytes"
    })
    page.locator("input[name='portrait_caption']").fill("Retained navigation caption")
    page.evaluate("""() => {
      const input=document.querySelector("input[name='portrait_file']");
      window.__navigationRepair={input, file:input.files[0], parent:input.parentNode,
        next:input.nextSibling, form:input.form, fields:Array.from(input.form.elements), faults:0};
    }""")
    _switch(page, "notes")
    _install_transport(page)
    _submit_note(page, "Committed note invalidates cached portrait")
    _release(page)
    expect(page.locator("[data-flash-stack-root]")).to_contain_text("Note saved.")
    # The real save clears the visited-page cache while retaining the detached
    # portrait's actual File input. The next portrait visit must use a fresh GET.
    assert page.evaluate("Array.from(window.__playerWikiCharacterReadShell.cache.keys()).every(key => !key.includes('page=portrait'))")
    page.evaluate("""fault => {
      const state=window.__navigationRepair;
      state.section=document.querySelector('[data-character-read-section-content]');
      state.header=document.querySelector('.character-header');
      state.headerHtml=state.header.innerHTML;
      state.nav=document.querySelector('.character-subpage-nav');
      state.navLinks=Array.from(state.nav.querySelectorAll('a'));
      state.href=window.location.href;
      window.history.replaceState({...window.history.state, navigationRepairMarker:'prior'}, '', state.href);
      const original=window.history.pushState.bind(window.history);
      window.history.pushState=(...args) => {
        if(!state.faults && String(args[2]).includes('page=portrait')){
          state.faults += 1;
          state.rejected=document.querySelector('[data-character-read-section-content]');
          state.transferExercised=state.input.isConnected && state.input.form!==state.form;
          if(fault==='after')original(...args);
          throw new Error('one-shot late navigation History failure');
        }
        return original(...args);
      };
    }""", history_fault)
    page.locator("[data-character-read-target-subpage='portrait']").click()
    expect(page.locator("[data-character-read-shell-root]")).not_to_have_attribute("aria-busy", "true")
    page.wait_for_function("() => window.__navigationRepair?.faults === 1")
    expect(page.get_by_text("Character pages are busy. Wait a moment, then choose the section again.", exact=True)).to_be_visible()
    snapshot = page.evaluate("""() => {
      const state=window.__navigationRepair;
      return {faults:state.faults, transferExercised:state.transferExercised,
        priorSection:document.querySelector('[data-character-read-section-content]')===state.section,
        priorHeader:document.querySelector('.character-header')===state.header && state.header.innerHTML===state.headerHtml,
        priorNav:document.querySelector('.character-subpage-nav')===state.nav
          && Array.from(state.nav.querySelectorAll('a')).every((link,index)=>link===state.navLinks[index]),
        retainedOwner:!state.input.isConnected && state.input.parentNode===state.parent
          && state.input.nextSibling===state.next && state.input.form===state.form && state.input.files[0]===state.file,
        fieldsIntact:Array.from(state.form.elements).length===state.fields.length
          && Array.from(state.form.elements).every((field,index)=>field===state.fields[index]),
        caption:state.form.querySelector("input[name='portrait_caption']").value,
        historyMarker:window.history.state.navigationRepairMarker,
        historyPage:window.history.state.characterReadSubpage, href:window.location.href,
        shellPage:document.querySelector('[data-character-read-shell-root]').dataset.characterReadShellPage,
        rejectedCached:Array.from(window.__playerWikiCharacterReadShell.cache.values()).some(entry=>entry.section===state.rejected)};
    }""")
    assert snapshot == {
        "faults":1, "transferExercised":True, "priorSection":True, "priorHeader":True, "priorNav":True,
        "retainedOwner":True, "fieldsIntact":True, "caption":"Retained navigation caption",
        "historyMarker":"prior", "historyPage":"notes", "href":f"{mutation_page.url}?page=notes",
        "shellPage":"notes", "rejectedCached":False,
    }
    assert page.evaluate("window.__navigationRepair.input.files[0].text()") == "retained navigation file bytes"
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 1
    _switch(page, "portrait")
    expect(page.locator("input[name='portrait_caption']")).to_have_value("Retained navigation caption")
    assert page.evaluate("""() => {
      const state=window.__navigationRepair, input=document.querySelector("input[name='portrait_file']");
      return input===state.input && input.isConnected && input.files[0]===state.file;
    }""")
    assert page.locator("input[name='portrait_file']").evaluate("field=>field.files[0].text()") == "retained navigation file bytes"
    assert len(_posts(page)) == 1
    assert len(page.evaluate("window.__mutationTest.gets")) == 2
    expect(page).to_have_url(re.compile(r"page=portrait"))
