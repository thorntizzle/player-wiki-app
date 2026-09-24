"""Actual Chromium recovery form and publication, without source-only assertions."""
import pytest

from tests.test_character_read_shell_browser import character_read_shell_live_server, _sign_in_browser, _wait_for_app_loading_cover
from tests.test_character_ability_recovery_routes import legacy_character, SLUG, PAGE


@pytest.mark.parametrize('confirmed', ['0', '8'])
def test_legacy_recovery_form_requires_confirmation_and_persists_it(app, users, get_character, character_read_shell_live_server, confirmed):
    from playwright.sync_api import sync_playwright, expect

    legacy_character(app)
    before = get_character(SLUG)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            _sign_in_browser(page, character_read_shell_live_server, users['dm'])
            page.goto(character_read_shell_live_server + PAGE + '/edit')
            _wait_for_app_loading_cover(page)
            field = page.get_by_label('Strength before recoverable penalties', exact=True)
            expect(field).to_have_value('')
            assert page.locator('input[name^="recover_ability_"]').count() == 1
            page.get_by_role('button', name='Save character edits', exact=True).click()
            assert not field.evaluate('(node) => node.validity.valid')
            assert get_character(SLUG).state_record.revision == before.state_record.revision
            field.fill(confirmed)
            # Clearing the penalty and confirming its base is one intended save.
            page.locator('input[name="recoverable_penalty_amount_1"]').fill('')
            page.locator('input[name="recoverable_penalty_source_1"]').fill('')
            page.locator('select[name="recoverable_penalty_target_1"]').select_option('')
            page.get_by_role('button', name='Save character edits', exact=True).click()
            expect(page.locator('input[name="recover_ability_str"]')).to_have_count(0)
            record = get_character(SLUG)
            assert record.definition.stats['ability_scores']['str']['score'] == int(confirmed)
            assert record.definition.stats['ability_inputs']['scores']['str']['provenance'] == 'authorized_editor_confirmation'
            assert record.state_record.revision == before.state_record.revision + 1
            page.reload()
            expect(page.locator('input[name="recover_ability_str"]')).to_have_count(0)
        finally:
            browser.close()


def test_partial_recovery_server_error_retains_valid_input_and_other_drafts(app, users, get_character, character_read_shell_live_server):
    from playwright.sync_api import sync_playwright, expect
    from tests.helpers.character_state_helpers import _read_character_definition

    legacy_character(app, two_abilities=True)
    original = _read_character_definition(app, SLUG)
    revision = get_character(SLUG).state_record.revision
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            _sign_in_browser(page, character_read_shell_live_server, users['dm'])
            page.goto(character_read_shell_live_server + PAGE + '/edit')
            _wait_for_app_loading_cover(page)
            strength = page.locator('input[name="recover_ability_str"]')
            dexterity = page.locator('input[name="recover_ability_dex"]')
            strength.fill('8')
            dexterity.fill('-1')
            page.locator('textarea[name="additional_notes_markdown"]').fill('Keep this recovery draft')
            # Exercise server validation independently of native numeric validity.
            strength.evaluate('(node) => { node.form.noValidate = true; }')
            with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith(PAGE + '/edit')) as response:
                page.get_by_role('button', name='Save character edits', exact=True).click()
            assert response.value.status == 400
            expect(page.get_by_text('Enter a whole number of zero or more for Dexterity before recoverable penalties.', exact=False)).to_be_visible()
            expect(strength).to_have_value('8')
            expect(dexterity).to_have_value('-1')
            expect(page.locator('textarea[name="additional_notes_markdown"]')).to_have_value('Keep this recovery draft')
            assert _read_character_definition(app, SLUG) == original
            assert get_character(SLUG).state_record.revision == revision
            dexterity.fill('0')
            page.get_by_role('button', name='Save character edits', exact=True).click()
            expect(page.locator('input[name^="recover_ability_"]')).to_have_count(0)
            saved = get_character(SLUG)
            assert saved.state_record.revision == revision + 1
            assert saved.definition.stats['ability_inputs']['scores']['str']['score'] == 8
            assert saved.definition.stats['ability_inputs']['scores']['dex']['score'] == 0
            assert saved.definition.reference_notes['additional_notes_markdown'] == 'Keep this recovery draft'
        finally:
            browser.close()
