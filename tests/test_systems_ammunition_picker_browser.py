import pytest

from tests.test_character_read_shell_browser import character_read_shell_live_server, _sign_in_browser
from tests.test_systems_ammunition_equipment import ammunition_record, seed_ammunition
from tests.test_systems_ammunition_importer import AMMUNITION_BASES


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}], ids=["desktop", "mobile"])
def test_real_ammunition_picker_firearm_units_save_and_reload(app, users, tmp_path, set_campaign_visibility, character_read_shell_live_server, viewport):
    from playwright.sync_api import expect, sync_playwright

    entries = seed_ammunition(app, tmp_path)
    set_campaign_visibility("linden-pass", characters="players", systems="private")
    prefix = character_read_shell_live_server + "/campaigns/linden-pass/characters/arden-march"
    selected = (
        ("+1 Modern Bullet", 3), ("+2 Modern Bullets (10)", 2),
        ("+2 Renaissance Bullet", 4), ("+3 Renaissance Bullets (10)", 3),
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=viewport)
        try:
            page = context.new_page()
            _sign_in_browser(page, character_read_shell_live_server, users["owner"])
            page.goto(prefix + "?page=inventory")
            form = page.locator("[data-character-systems-item-search-form]")
            expect(form).to_be_visible()
            for tier in (1, 2, 3):
                form.locator("[data-character-systems-item-query]").fill(f"ammunition +{tier}")
                options = form.locator("[data-character-systems-item-results] option")
                expected_slugs = sorted(entries[f"+{tier} {base[0]}"].slug for base in AMMUNITION_BASES)
                expect(form.locator("[data-character-systems-item-status]")).to_have_text("Found 12 matching Systems items.")
                expect(options).to_have_count(12)
                expect(options.first).to_contain_text(f"+{tier}")
                assert sorted(options.evaluate_all("nodes => nodes.map(node => node.value)")) == expected_slugs
            for title, quantity in selected:
                form.locator("[data-character-systems-item-query]").fill(title)
                picker = form.locator("[data-character-systems-item-results]")
                expect(picker.locator(f'option[value="{entries[title].slug}"]')).to_have_count(1)
                picker.select_option(entries[title].slug)
                form.locator('input[name="quantity"]').fill(str(quantity))
                form.get_by_role("button", name="Add Systems item", exact=True).click()
                expect(page.get_by_text("Systems item added to supplemental equipment.", exact=True)).to_be_visible()
                page.goto(prefix + "?page=inventory")
                row = page.locator("article.inventory-row").filter(has=page.get_by_role("heading", name=title, exact=True))
                expect(row).to_be_visible()
                expect(row.locator('input[name="quantity"]')).to_have_value(str(quantity))
            page.goto(prefix + "/edit")
            page.get_by_role("button", name="Save character edits", exact=True).click()
            page.goto(prefix + "?page=inventory")
            title, quantity = selected[1]
            row = page.locator("article.inventory-row").filter(has=page.get_by_role("heading", name=title, exact=True))
            with page.expect_response(lambda response: "/session/inventory/" in response.url and response.request.method == "POST"):
                row.locator('input[name="quantity"]').fill("5")
                row.locator('input[name="quantity"]').press("Tab")
            page.reload()
            expect(row.locator('input[name="quantity"]')).to_have_value("5")
            current = ammunition_record(app)
            for selected_title, initial_quantity in selected:
                entry = entries[selected_title]
                item = next(item for item in current.definition.equipment_catalog if (item.get("systems_ref") or {}).get("entry_key") == entry.entry_key)
                stored_quantity = next(value["quantity"] for value in current.state_record.state["inventory"] if value["catalog_ref"] == item["id"])
                assert stored_quantity == (5 if selected_title == title else initial_quantity)
                assert float(item["weight"].split()[0]) == entry.metadata["weight"]
                assert item["systems_ref"]["slug"] == entry.slug
                assert item["systems_ref"]["source_id"] == "DMG"
        finally:
            context.close()
            browser.close()
