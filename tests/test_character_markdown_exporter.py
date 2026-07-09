from __future__ import annotations

from copy import deepcopy

from player_wiki.character_markdown_exporter import render_dnd_character_markdown
from player_wiki.character_page_records import list_visible_character_page_records
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG


def _render_character_markdown(app, character_slug: str) -> str:
    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign(TEST_CAMPAIGN_SLUG)
        assert campaign is not None
        record = app.extensions["character_repository"].get_visible_character(
            TEST_CAMPAIGN_SLUG,
            character_slug,
        )
        assert record is not None
        campaign_page_records = list_visible_character_page_records(
            app.extensions["campaign_page_store"],
            TEST_CAMPAIGN_SLUG,
            campaign,
            include_body=True,
            excluded_sections={"Sessions"},
        )
        return render_dnd_character_markdown(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
            campaign_page_records=campaign_page_records,
        )


def test_dnd_character_markdown_export_includes_full_sheet_sections(app):
    markdown = _render_character_markdown(app, ASSIGNED_CHARACTER_SLUG)

    assert markdown.startswith("# Arden March\n")
    assert "## At a Glance" in markdown
    assert "| Armor Class | 14 |" in markdown
    assert "## Abilities and Skills" in markdown
    assert "| Charisma | 18 | +4 | +7 |" in markdown
    assert "Arcana +7 (Expertise)" in markdown
    assert "## Spellcasting" in markdown
    assert "| 1st level | 4 | 0 | 4 |" in markdown
    assert "| Message | Spell | 1 action | 120 feet | 1 round | V, S, M | -- |  |" in markdown
    assert "## Features" in markdown
    assert "Spend sorcery points to shape prepared magic on the fly." in markdown
    assert "## Equipment and Inventory" in markdown
    assert "| Crossbow Bolts | 20 | 1.5 lb. | no | no | ammunition |  |" in markdown
    assert "## Character Notes and Reference" in markdown
    assert "### Biography" in markdown
    assert "Arden serves as the crew's relay mage" in markdown
    assert "[Captain Lyra Vale](/campaigns/linden-pass/pages/npcs/captain-lyra-vale)" in markdown
    assert "## Source" in markdown


def test_dnd_character_markdown_export_uses_current_sqlite_state(app):
    with app.app_context():
        character_repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = character_repository.get_character(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)
        assert record is not None
        state = deepcopy(record.state_record.state)
        state["vitals"]["current_hp"] = 31
        for item in state["inventory"]:
            if item["id"] == "crossbow-bolts-4":
                item["quantity"] = 17
        state["currency"]["gp"] = 12
        state["notes"]["player_notes_markdown"] = "Fresh table note from the latest session."
        state_store.replace_state(
            record.definition,
            state,
            expected_revision=record.state_record.revision,
        )

    markdown = _render_character_markdown(app, ASSIGNED_CHARACTER_SLUG)

    assert "| Current HP | 31 / 38 |" in markdown
    assert "| Crossbow Bolts | 17 | 1.5 lb. | no | no | ammunition |  |" in markdown
    assert "| GP | 12 |" in markdown
    assert "### Player Notes" in markdown
    assert "Fresh table note from the latest session." in markdown
