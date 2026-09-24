from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.test_character_read_shell_browser import (
    character_read_shell_live_server,
    _sign_in_browser,
    _wait_for_app_loading_cover,
)

FORM = "form[action$='/session/spell-slots/2']"
SESSION_UNCONFIRMED = 'The save result could not be confirmed. Refresh Session and inspect the current sheet before repeating the action.'


@pytest.mark.parametrize('surface', ['read', 'session'])
def test_slot_autosave_preserves_surface_and_updates_revision_once(app, client, sign_in, users, set_campaign_visibility, get_character, character_read_shell_live_server, surface):
    set_campaign_visibility('linden-pass', characters='players')
    if surface == 'session':
        sign_in(users['dm']['email'], users['dm']['password'])
        assert client.post('/campaigns/linden-pass/session/start').status_code == 302
    base = character_read_shell_live_server
    path = ('/campaigns/linden-pass/session/character?character=arden-march&page=spells'
            if surface == 'session' else '/campaigns/linden-pass/characters/arden-march?page=spellcasting')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            _sign_in_browser(page, base, users['owner'])
            page.goto(base + path)
            _wait_for_app_loading_cover(page)
            form = page.locator(FORM).first
            expect(form).to_be_visible()
            revision = form.locator("input[name='expected_revision']").input_value()
            page.evaluate('window.__slotAdmissionMarker = 7')
            posts = []
            page.on('request', lambda req: posts.append(req) if req.method == 'POST' and '/session/spell-slots/' in req.url else None)
            form.locator("input[name='used']").fill('1')
            form.locator("input[name='used']").dispatch_event('change')
            expect(page.locator(FORM).first.locator("input[name='expected_revision']")).not_to_have_value(revision)
            expect(page.locator(FORM).first.locator("input[name='used']")).to_have_value('1')
            expect(page.locator('.flash-success').filter(has_text='Spell slot usage updated.')).to_be_visible()
            assert len(posts) == 1
            assert page.evaluate('window.__slotAdmissionMarker') == 7
            assert urlsplit(page.url).path == urlsplit(base + path).path
            record = get_character('arden-march')
            assert record.state_record.revision == int(revision) + 1
            slot = next(row for row in record.state_record.state['spell_slots'] if row['level'] == 2)
            assert slot['used'] == 1
        finally:
            browser.close()


@pytest.fixture
def slot_failure_page(app, client, sign_in, users, set_campaign_visibility, character_read_shell_live_server, surface):
    set_campaign_visibility('linden-pass', characters='players')
    if surface == 'session':
        sign_in(users['dm']['email'], users['dm']['password'])
        assert client.post('/campaigns/linden-pass/session/start').status_code == 302
    base = character_read_shell_live_server
    path = ('/campaigns/linden-pass/session/character?character=arden-march&page=spells'
            if surface == 'session' else '/campaigns/linden-pass/characters/arden-march?page=spellcasting')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            _sign_in_browser(page, base, users['owner'])
            page.goto(base + path)
            _wait_for_app_loading_cover(page)
            expect(page.locator(FORM).first).to_be_visible()
            page.evaluate('window.__slotFailureMarker = 9')
            yield page
        finally:
            browser.close()


@pytest.mark.parametrize('surface', ['read', 'session'])
@pytest.mark.parametrize('failure', ['stale', 'validation'])
def test_slot_refusal_keeps_surface_feedback_and_durable_state(app, get_character, users, slot_failure_page, surface, failure):
    from copy import deepcopy
    from tests.test_character_session_admission import _snapshot
    page = slot_failure_page
    record = get_character('arden-march')
    if failure == 'stale':
        state = deepcopy(record.state_record.state)
        state['notes']['player_notes_markdown'] = 'Changed on another surface'
        with app.app_context():
            app.extensions['character_state_store'].replace_state(record.definition, state, expected_revision=record.state_record.revision, updated_by_user_id=users['dm']['id'])
    before = _snapshot(app)
    form = page.locator(FORM).first
    field = form.locator("input[name='used']")
    value = '2' if failure == 'stale' else '999'
    if failure == 'validation':
        # Admit the intentionally invalid form in the browser; server bounds
        # remain authoritative. This does not change application UI behavior.
        field.evaluate("node => node.max = '999'")
    posts = []
    page.on('request', lambda req: posts.append(req) if req.method == 'POST' and '/session/spell-slots/' in req.url else None)
    fragments = []
    page.on('response', lambda response: fragments.append(response) if '/session/character?' in response.url and 'fragment=1' in response.url else None)
    field.fill(value)
    field.dispatch_event('change')
    message = ('This sheet changed in another session.' if failure == 'stale' else 'must be between')
    if surface == 'session':
        # The server's existing 302 -> 200 error fragment is not a confirmed
        # success or an explicit 400/409/422 feedback response to Session shell.
        # Keep its guidance and held draft, while checking the raw server flash.
        expect(page.get_by_text(SESSION_UNCONFIRMED, exact=True)).to_be_visible()
        assert fragments and fragments[-1].status == 200
        assert message in fragments[-1].text()
    else:
        expect(page.locator('.flash-error').filter(has_text=message)).to_be_visible()
    assert page.evaluate('window.__slotFailureMarker') == 9
    assert _snapshot(app) == before
    assert len(posts) == 1
    expect(page.locator(FORM).first.locator("input[name='used']")).to_have_value(value)
    assert ('/session/character' in page.url) == (surface == 'session')


@pytest.mark.parametrize('surface', ['session'])
def test_ended_session_refuses_actual_slot_autosave(app, client, get_character, slot_failure_page, surface):
    from tests.test_character_session_admission import _snapshot
    page = slot_failure_page
    before = _snapshot(app)
    assert client.post('/campaigns/linden-pass/session/close').status_code == 302
    fragments = []
    page.on('response', lambda response: fragments.append(response) if '/session/character?' in response.url and 'fragment=1' in response.url else None)
    field = page.locator(FORM).first.locator("input[name='used']")
    field.fill('1')
    field.dispatch_event('change')
    expect(page.get_by_text(SESSION_UNCONFIRMED, exact=True)).to_be_visible()
    assert fragments and fragments[-1].status == 200
    assert 'The live session has ended.' in fragments[-1].text()
    expect(page.locator(FORM).first.locator("input[name='used']")).to_have_value('1')
    assert _snapshot(app) == before
    assert page.evaluate('window.__slotFailureMarker') == 9
    assert '/session/character' in page.url


@pytest.mark.parametrize('surface', ['read', 'session'])
def test_slot_form_no_javascript_follows_canonical_return(app, client, sign_in, users, set_campaign_visibility, get_character, character_read_shell_live_server, surface):
    set_campaign_visibility('linden-pass', characters='players')
    if surface == 'session':
        sign_in(users['dm']['email'], users['dm']['password'])
        assert client.post('/campaigns/linden-pass/session/start').status_code == 302
    base = character_read_shell_live_server
    path = ('/campaigns/linden-pass/session/character?character=arden-march&page=spells'
            if surface == 'session' else '/campaigns/linden-pass/characters/arden-march?page=spellcasting')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(java_script_enabled=False)
            page = context.new_page()
            _sign_in_browser(page, base, users['owner'])
            page.goto(base + path)
            form = page.locator(FORM).first
            field = form.locator("input[name='used']")
            field.fill('1')
            revision = int(form.locator("input[name='expected_revision']").input_value())
            with page.expect_navigation():
                field.press('Enter')
            expect(page.locator('.flash-success').filter(has_text='Spell slot usage updated.')).to_be_visible()
            assert page.url.endswith('#session-spell-slots')
            assert ('/session/character' in page.url) == (surface == 'session')
            assert get_character('arden-march').state_record.revision == revision + 1
        finally:
            browser.close()
