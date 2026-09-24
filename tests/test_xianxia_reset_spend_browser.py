import pytest

from tests.helpers.character_state_helpers import _write_character_definition
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign, _valid_xianxia_create_data
from tests.test_character_read_shell_browser import character_read_shell_live_server, _sign_in_browser
from tests.test_xianxia_reset_spend_guard import reset_definition


@pytest.mark.parametrize("realm", ["Mortal", "Immortal"])
@pytest.mark.parametrize("javascript", [False, True])
def test_cultivation_reset_gap_keeps_durability_controls_available(
    app, client, sign_in, users, character_read_shell_live_server, realm, javascript
):
    from playwright.sync_api import sync_playwright, expect

    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/characters/new", data=_valid_xianxia_create_data("Browser Crane")).status_code == 302
    _write_character_definition(app, "browser-crane", lambda payload: payload.update(xianxia=reset_definition(realm).xianxia))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(java_script_enabled=javascript)
        try:
            page = context.new_page()
            _sign_in_browser(page, character_read_shell_live_server, users["dm"])
            page.goto(character_read_shell_live_server + "/campaigns/linden-pass/characters/browser-crane/cultivation")
            for target, value, expected in [("conditioning_target", "effort", 5), ("training_target", "attribute", 6)]:
                forms = page.locator("form").filter(has=page.locator(f'input[name="{target}"][value="{value}"]'))
                expect(forms).to_have_count(expected)
                for button in forms.locator('button[type="submit"]').all():
                    expect(button).to_be_disabled()
            expect(page.get_by_text("Complete the pending Realm rebuild before spending Insight on Attributes or Efforts. HP Conditioning and Stance Training remain available.", exact=True)).to_have_count(2)
            hp = page.locator("form").filter(has=page.locator('input[name="conditioning_target"][value="hp"]')).locator('button[type="submit"]')
            stance = page.locator("form").filter(has=page.locator('input[name="training_target"][value="stance"]')).locator('button[type="submit"]')
            expect(hp).to_be_enabled()
            expect(stance).to_be_enabled()
            hp.click()
            expect(page.get_by_text("Spent 1 Insight on Conditioning to increase HP.", exact=True)).to_be_visible()
        finally:
            context.close()
            browser.close()
