from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from player_wiki.dnd5e_rules_reference import DND5E_RULES_REFERENCE_VERSION, build_dnd5e_rules_reference_entries
from player_wiki.auth_store import AuthStore
from player_wiki.systems_importer import Dnd5eSystemsImporter
from tests.test_systems_importer import (
    build_dmg_book_data_root,
    build_egw_character_option_wrapper_data_root,
    build_egw_dunamis_book_data_root,
    build_mtf_book_data_root,
    build_mm_book_data_root,
    build_phb_book_data_root,
    build_test_data_root,
    build_vgm_book_data_root,
)


def build_source_form(app, campaign_slug: str = "linden-pass") -> dict[str, str]:
    with app.app_context():
        service = app.extensions["systems_service"]
        rows = service.list_campaign_source_states(campaign_slug)

    data: dict[str, str] = {}
    for row in rows:
        if row.is_enabled:
            data[f"source_{row.source.source_id}_enabled"] = "1"
        data[f"source_{row.source.source_id}_visibility"] = row.default_visibility
    return data


def build_repo_local_test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp-pytest-egw-data"
    root.mkdir(exist_ok=True)
    path = root / f"{name}-{uuid4().hex}"
    path.mkdir()
    return path


@pytest.fixture()
def tmp_path() -> Path:
    return build_repo_local_test_root("pytest")


def test_party_member_sees_systems_nav_and_player_visible_sources(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    systems = client.get("/campaigns/linden-pass/systems")

    assert campaign.status_code == 200
    campaign_body = campaign.get_data(as_text=True)
    assert 'href="/campaigns/linden-pass/systems"' in campaign_body

    assert systems.status_code == 200
    body = systems.get_data(as_text=True)
    assert "RULES" in body
    assert "Character Rules Reference" in body
    assert "PHB" in body
    assert "Player&#39;s Handbook (2014)" in body
    assert "Xanathar&#39;s Guide to Everything" in body
    assert "Wayfarer&#39;s Guide to Eberron" not in body
    assert "DMG" not in body
    assert "MM" not in body


def test_dm_can_open_systems_control_panel_and_visibility_panel_shows_systems_scope(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    visibility_panel = client.get("/campaigns/linden-pass/control-panel")
    systems_panel = client.get("/campaigns/linden-pass/systems/control-panel")

    assert visibility_panel.status_code == 200
    visibility_html = visibility_panel.get_data(as_text=True)
    assert "Systems" in visibility_html

    assert systems_panel.status_code == 200
    systems_html = systems_panel.get_data(as_text=True)
    assert "Systems Policy" in systems_html
    assert "Player&#39;s Handbook (2014)" in systems_html
    assert "Dungeon Master&#39;s Guide (2014)" in systems_html
    assert "Wayfarer&#39;s Guide to Eberron" not in systems_html
    assert "Proprietary-source acknowledgement" in systems_html
    assert 'class="checkbox-label"' in systems_html


def test_proprietary_source_cannot_be_made_public(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_PHB_visibility"] = "public"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "cannot be made public" in response.get_data(as_text=True)


def test_player_cannot_open_dm_only_source_but_dm_can(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert blocked.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    allowed = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert allowed.status_code == 200
    assert "Dungeon Master&#39;s Guide (2014)" in allowed.get_data(as_text=True)


def test_dm_can_update_source_visibility_and_audit_event_is_written(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_XGE_visibility"] = "dm"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Updated systems sources: XGE." in response.get_data(as_text=True)

    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_builtin_rules_source_is_seeded_and_browsable_without_import(client, sign_in, users, app):
    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "RULES")
        assert state is not None
        assert state.is_enabled is True
        entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "RULES",
            entry_type="rule",
            limit=None,
        )
        titles = {entry.title for entry in entries}
        assert "Ability Scores and Ability Modifiers" in titles
        assert "Spell Attacks and Save DCs" in titles
        attunement_entry = next(
            entry for entry in entries if entry.title == "Equipped Items, Inventory, and Attunement"
        )
        assert attunement_entry.metadata["content_origin"] == "managed_seed_file"
        assert attunement_entry.metadata["content_migration_stage"] == "seed_file_to_sqlite"
        assert attunement_entry.metadata["content_source_path"] == "player_wiki/data/dnd5e_rules_reference.json"
        assert attunement_entry.metadata["seed_version"] == DND5E_RULES_REFERENCE_VERSION
        assert attunement_entry.source_path.endswith(
            f"player_wiki/data/dnd5e_rules_reference.json#{DND5E_RULES_REFERENCE_VERSION}"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/RULES")
    category_response = client.get("/campaigns/linden-pass/systems/sources/RULES/types/rule")
    search_response = client.get("/campaigns/linden-pass/systems/search?q=attunement")
    detail_response = client.get(f"/campaigns/linden-pass/systems/entries/{attunement_entry.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Character Rules Reference" in source_body
    assert "Browse This Source" in source_body
    assert "Rules" in source_body
    assert "Searches only this source&#39;s rules entries using curated metadata" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Ability Scores and Ability Modifiers" in category_body
    assert "Armor Class" in category_body
    assert "Equipped Items, Inventory, and Attunement" in category_body

    assert search_response.status_code == 200
    search_body = search_response.get_data(as_text=True)
    assert "Equipped Items, Inventory, and Attunement" in search_body
    assert "RULES | Rules" in search_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "attunement is a separate state with a normal limit of 3 items" in detail_body
    assert "Inventory Versus Equipment" in detail_body


def test_related_rules_sidebar_respects_rules_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["item"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="RULES",
            is_enabled=True,
            default_visibility="dm",
        )
        longsword_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="item", limit=20)
            if entry.title == "Longsword"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")

    assert player_response.status_code == 200
    player_body = player_response.get_data(as_text=True)
    assert "Related Rules References" not in player_body
    assert "Attack Rolls and Attack Bonus" not in player_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Related Rules References" in dm_body
    assert "Attack Rolls and Attack Bonus" in dm_body


def test_phb_book_section_rule_links_respect_rules_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="RULES",
            is_enabled=True,
            default_visibility="dm",
        )
        using_ability_scores_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="book", limit=20)
            if entry.title == "Using Ability Scores"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores_entry.slug}")

    assert player_response.status_code == 200
    player_body = player_response.get_data(as_text=True)
    assert "Rules:" not in player_body
    assert "Passive Checks" in player_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Rules:" in dm_body
    assert '<a href="/campaigns/linden-pass/systems/entries/rules-rule-passive-checks">' in dm_body


def test_dmg_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

        store = app.extensions["systems_store"]
        multiverse_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="book", limit=20)
            if entry.title == "Creating a Multiverse"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")
    assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Creating a Multiverse" in dm_body
    assert "Chapter 2" in dm_body


def test_mm_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["book"])

        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "MM", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    for title in (
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ):
        player_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    for title in (
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ):
        dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert dm_response.status_code == 200
        dm_body = dm_response.get_data(as_text=True)
        assert title in dm_body
        if title == "Customizing NPCs":
            assert "Appendix B" in dm_body
            assert "Appendix B: Nonplayer Characters" in dm_body
        else:
            assert "Introduction" in dm_body


def test_vgm_character_race_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    for title in (
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ):
        player_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    for title in (
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ):
        dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert dm_response.status_code == 200
        dm_body = dm_response.get_data(as_text=True)
        assert title in dm_body
        assert "Character Races" in dm_body


def test_vgm_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_vgm_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book-policy-lowered")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "race"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="players",
        )
        monstrous_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="book", limit=20)
            if entry.title == "Monstrous Adventurers"
        )
        bugbear_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="race", limit=20)
            if entry.title == "Bugbear"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    player_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous_entry.slug}")
    player_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{bugbear_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=monstrous")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Monstrous Adventurers" not in source_body
    assert "Races" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_book_response.status_code == 404

    assert player_race_response.status_code == 200
    assert "Bugbear" in player_race_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "Monstrous Adventurers" not in search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    dm_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous_entry.slug}")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Monstrous Adventurers" in dm_source_body
    assert "default to DM visibility" in dm_source_body

    assert dm_book_category_response.status_code == 200
    assert "Monstrous Adventurers" in dm_book_category_response.get_data(as_text=True)

    assert dm_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_book_response.get_data(as_text=True)


def test_dmg_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_dmg_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book", "item"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="DMG",
            is_enabled=True,
            default_visibility="players",
        )
        multiverse_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="book", limit=20)
            if entry.title == "Creating a Multiverse"
        )
        potion_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=20)
            if entry.title == "Potion of Healing"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    player_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")
    player_item_response = client.get(f"/campaigns/linden-pass/systems/entries/{potion_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=multiverse")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Creating a Multiverse" not in source_body
    assert "Items" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_book_response.status_code == 404

    assert player_item_response.status_code == 200
    assert "Potion of Healing" in player_item_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "Creating a Multiverse" not in search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    dm_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Creating a Multiverse" in dm_source_body

    assert dm_book_category_response.status_code == 200
    assert "Creating a Multiverse" in dm_book_category_response.get_data(as_text=True)

    assert dm_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_book_response.get_data(as_text=True)


def test_mtf_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_mtf_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mtf_book_data_root(tmp_path / "dnd5e-source-mtf-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MTF", entry_types=["book", "race"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="MTF",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="book", limit=20)
        }
        tiefling_wrapper_entry = book_entries["Tiefling Subraces"]
        demonic_boons_entry = book_entries["Demonic Boons"]
        elf_wrapper_entry = book_entries["Elf Subraces"]
        duergar_wrapper_entry = book_entries["Duergar Characters"]
        gith_wrapper_entry = book_entries["Gith Characters"]
        deep_gnome_wrapper_entry = book_entries["Deep Gnome Characters"]
        asmodeus_tiefling_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Asmodeus Tiefling"
        )
        sea_elf_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Sea Elf"
        )
        duergar_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Duergar"
        )
        githyanki_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Githyanki"
        )
        deep_gnome_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Deep Gnome"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    player_tiefling_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{tiefling_wrapper_entry.slug}"
    )
    player_demonic_boons_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{demonic_boons_entry.slug}"
    )
    player_elf_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{elf_wrapper_entry.slug}")
    player_duergar_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{duergar_wrapper_entry.slug}"
    )
    player_gith_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{gith_wrapper_entry.slug}")
    player_deep_gnome_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{deep_gnome_wrapper_entry.slug}"
    )
    player_tiefling_race_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{asmodeus_tiefling_entry.slug}"
    )
    player_elf_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{sea_elf_entry.slug}")
    player_duergar_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{duergar_entry.slug}")
    player_githyanki_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{githyanki_entry.slug}")
    player_deep_gnome_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{deep_gnome_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=subraces")
    demonic_boons_search_response = client.get("/campaigns/linden-pass/systems?q=demonic+boons")
    duergar_search_response = client.get("/campaigns/linden-pass/systems?q=duergar+characters")
    gith_search_response = client.get("/campaigns/linden-pass/systems?q=gith+characters")
    deep_gnome_search_response = client.get("/campaigns/linden-pass/systems?q=deep+gnome+characters")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Tiefling Subraces" not in source_body
    assert "Demonic Boons" not in source_body
    assert "Elf Subraces" not in source_body
    assert "Duergar Characters" not in source_body
    assert "Gith Characters" not in source_body
    assert "Deep Gnome Characters" not in source_body
    assert "Races" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_tiefling_book_response.status_code == 404
    assert player_demonic_boons_response.status_code == 404
    assert player_elf_book_response.status_code == 404
    assert player_duergar_book_response.status_code == 404
    assert player_gith_book_response.status_code == 404
    assert player_deep_gnome_book_response.status_code == 404

    assert player_tiefling_race_response.status_code == 200
    assert "Asmodeus Tiefling" in player_tiefling_race_response.get_data(as_text=True)
    assert player_elf_race_response.status_code == 200
    assert "Sea Elf" in player_elf_race_response.get_data(as_text=True)
    assert player_duergar_race_response.status_code == 200
    assert "Duergar" in player_duergar_race_response.get_data(as_text=True)
    assert player_githyanki_race_response.status_code == 200
    assert "Githyanki" in player_githyanki_race_response.get_data(as_text=True)
    assert player_deep_gnome_race_response.status_code == 200
    assert "Deep Gnome" in player_deep_gnome_race_response.get_data(as_text=True)

    assert search_response.status_code == 200
    search_body = search_response.get_data(as_text=True)
    assert "Tiefling Subraces" not in search_body
    assert "Elf Subraces" not in search_body
    assert demonic_boons_search_response.status_code == 200
    assert "Demonic Boons" not in demonic_boons_search_response.get_data(as_text=True)
    assert duergar_search_response.status_code == 200
    assert "Duergar Characters" not in duergar_search_response.get_data(as_text=True)
    assert gith_search_response.status_code == 200
    assert "Gith Characters" not in gith_search_response.get_data(as_text=True)
    assert deep_gnome_search_response.status_code == 200
    assert "Deep Gnome Characters" not in deep_gnome_search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    dm_tiefling_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{tiefling_wrapper_entry.slug}")
    dm_demonic_boons_response = client.get(f"/campaigns/linden-pass/systems/entries/{demonic_boons_entry.slug}")
    dm_elf_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{elf_wrapper_entry.slug}")
    dm_duergar_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{duergar_wrapper_entry.slug}")
    dm_gith_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{gith_wrapper_entry.slug}")
    dm_deep_gnome_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{deep_gnome_wrapper_entry.slug}"
    )
    dm_demonic_boons_search_response = client.get("/campaigns/linden-pass/systems?q=demonic+boons")
    dm_duergar_search_response = client.get("/campaigns/linden-pass/systems?q=duergar+characters")
    dm_gith_search_response = client.get("/campaigns/linden-pass/systems?q=gith+characters")
    dm_deep_gnome_search_response = client.get("/campaigns/linden-pass/systems?q=deep+gnome+characters")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Tiefling Subraces" in dm_source_body
    assert "Demonic Boons" in dm_source_body
    assert "Elf Subraces" in dm_source_body
    assert "Duergar Characters" in dm_source_body
    assert "Gith Characters" in dm_source_body
    assert "Deep Gnome Characters" in dm_source_body
    assert dm_source_body.index("Tiefling Subraces") < dm_source_body.index("Demonic Boons")
    assert dm_source_body.index("Demonic Boons") < dm_source_body.index("Elf Subraces")
    assert dm_source_body.index("Elf Subraces") < dm_source_body.index("Duergar Characters")
    assert dm_source_body.index("Duergar Characters") < dm_source_body.index("Gith Characters")
    assert dm_source_body.index("Gith Characters") < dm_source_body.index("Deep Gnome Characters")
    assert "default to DM visibility" in dm_source_body

    assert dm_book_category_response.status_code == 200
    dm_book_category_body = dm_book_category_response.get_data(as_text=True)
    assert "Tiefling Subraces" in dm_book_category_body
    assert "Demonic Boons" in dm_book_category_body
    assert "Elf Subraces" in dm_book_category_body
    assert "Duergar Characters" in dm_book_category_body
    assert "Gith Characters" in dm_book_category_body
    assert "Deep Gnome Characters" in dm_book_category_body
    assert dm_book_category_body.index("Tiefling Subraces") < dm_book_category_body.index("Demonic Boons")
    assert dm_book_category_body.index("Demonic Boons") < dm_book_category_body.index("Elf Subraces")
    assert dm_book_category_body.index("Elf Subraces") < dm_book_category_body.index("Duergar Characters")
    assert dm_book_category_body.index("Duergar Characters") < dm_book_category_body.index("Gith Characters")
    assert dm_book_category_body.index("Gith Characters") < dm_book_category_body.index("Deep Gnome Characters")

    assert dm_tiefling_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_tiefling_book_response.get_data(as_text=True)
    assert dm_demonic_boons_response.status_code == 200
    assert "Policy default visibility: DM" in dm_demonic_boons_response.get_data(as_text=True)
    assert dm_elf_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_elf_book_response.get_data(as_text=True)
    assert dm_duergar_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_duergar_book_response.get_data(as_text=True)
    assert dm_gith_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_gith_book_response.get_data(as_text=True)
    assert dm_deep_gnome_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_deep_gnome_book_response.get_data(as_text=True)
    assert dm_demonic_boons_search_response.status_code == 200
    assert "Demonic Boons" in dm_demonic_boons_search_response.get_data(as_text=True)
    assert dm_duergar_search_response.status_code == 200
    assert "Duergar Characters" in dm_duergar_search_response.get_data(as_text=True)
    assert dm_gith_search_response.status_code == 200
    assert "Gith Characters" in dm_gith_search_response.get_data(as_text=True)
    assert dm_deep_gnome_search_response.status_code == 200
    assert "Deep Gnome Characters" in dm_deep_gnome_search_response.get_data(as_text=True)


def test_egw_book_entries_follow_source_visibility(client, sign_in, users, app):
    data_root = build_egw_dunamis_book_data_root(
        build_repo_local_test_root("dnd5e-source-egw-book-entries-policy")
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("EGW", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="EGW",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamis and Dunamancy'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamis and Dunamancy'].slug}"
    )

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Dunamis and Dunamancy" in dm_source_body

    assert dm_category_response.status_code == 200
    dm_category_body = dm_category_response.get_data(as_text=True)
    assert "Dunamis and Dunamancy" in dm_category_body
    assert "Heroic Chronicle" in dm_category_body

    assert dm_entry_response.status_code == 200
    dm_entry_body = dm_entry_response.get_data(as_text=True)
    assert "Chapter 4" in dm_entry_body
    assert "Character Options" in dm_entry_body
    assert "Beyond the Kryn Dynasty" in dm_entry_body


def test_egw_source_chapter_context_respects_wrapper_entry_visibility(
    client, sign_in, users, app
):
    data_root = build_egw_character_option_wrapper_data_root(
        build_repo_local_test_root("dnd5e-source-egw-wrapper-visibility")
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "EGW",
            entry_types=["background", "book", "race", "spell", "subclass", "subclassfeature"],
        )

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="EGW",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="book", limit=None)
        }
        spell_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="spell", limit=None)
        }
        for wrapper_title in ("Dunamancy Spells", "Spell Descriptions"):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug="DND-5E",
                entry_key=book_entries[wrapper_title].entry_key,
                visibility_override="dm",
                is_enabled_override=None,
            )

    sign_in(users["party"]["email"], users["party"]["password"])

    player_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    player_hidden_wrapper_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamancy Spells'].slug}"
    )
    player_spell_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{spell_entries['Dark Star'].slug}"
    )

    assert player_source_response.status_code == 200
    player_source_body = player_source_response.get_data(as_text=True)
    assert "Book Chapters" in player_source_body
    assert "Heroic Chronicle" in player_source_body
    assert "Dunamancy Spells" not in player_source_body
    assert "Spell Descriptions" not in player_source_body

    assert player_category_response.status_code == 200
    player_category_body = player_category_response.get_data(as_text=True)
    assert "Heroic Chronicle" in player_category_body
    assert "Dunamancy Spells" not in player_category_body
    assert "Spell Descriptions" not in player_category_body

    assert player_hidden_wrapper_response.status_code == 404

    assert player_spell_response.status_code == 200
    player_spell_body = player_spell_response.get_data(as_text=True)
    assert "Dark Star" in player_spell_body
    assert "Source Chapter Context" not in player_spell_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Dunamancy Spells"].slug}"'
        not in player_spell_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Spell Descriptions"].slug}"'
        not in player_spell_body
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    dm_hidden_wrapper_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamancy Spells'].slug}"
    )
    dm_spell_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{spell_entries['Dark Star'].slug}"
    )

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Dunamancy Spells" in dm_source_body
    assert "Spell Descriptions" in dm_source_body

    assert dm_category_response.status_code == 200
    dm_category_body = dm_category_response.get_data(as_text=True)
    assert "Dunamancy Spells" in dm_category_body
    assert "Spell Descriptions" in dm_category_body

    assert dm_hidden_wrapper_response.status_code == 200
    assert "Dunamancy Spells" in dm_hidden_wrapper_response.get_data(as_text=True)

    assert dm_spell_response.status_code == 200
    dm_spell_body = dm_spell_response.get_data(as_text=True)
    assert "Source Chapter Context" in dm_spell_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Dunamancy Spells"].slug}"'
        in dm_spell_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Spell Descriptions"].slug}"'
        in dm_spell_body
    )


def test_dmg_rules_reference_search_stays_source_scoped(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-search-scope")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

    sign_in(users["dm"]["email"], users["dm"]["password"])

    landing_response = client.get("/campaigns/linden-pass/systems?reference_q=planar+travel")
    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG?reference_q=planar+travel")

    assert landing_response.status_code == 200
    landing_body = landing_response.get_data(as_text=True)
    assert "No rules references matched that metadata search yet." in landing_body
    assert "Creating a Multiverse" not in landing_body
    assert "DM-heavy source-backed references stay on their own source pages" in landing_body
    assert 'href="/campaigns/linden-pass/systems/sources/DMG"' in landing_body

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Creating a Multiverse" in source_body
    assert "DM-heavy source keeps chapter browse and rules-reference metadata search on this source page" in source_body


def test_builtin_rules_source_reseeds_stale_rows_from_managed_payload(app):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded("DND-5E")

        stale_entries = build_dnd5e_rules_reference_entries()
        for entry in stale_entries:
            entry["source_path"] = "builtin:dnd5e-rules:legacy"
            entry["metadata"] = {
                **entry["metadata"],
                "seed_version": "2026-04-01.0",
                "content_origin": "code_seed",
                "content_source_path": "player_wiki/dnd5e_rules_reference.py",
                "content_migration_stage": "python_literal_seed",
            }

        store.replace_entries_for_source("DND-5E", "RULES", entries=stale_entries)

        refreshed_state = service.get_campaign_source_state("linden-pass", "RULES")
        assert refreshed_state is not None

        refreshed_entry = store.get_entry(
            "DND-5E",
            "rules-rule-character-math-overview",
        )
        assert refreshed_entry is not None
        assert refreshed_entry.metadata["seed_version"] == DND5E_RULES_REFERENCE_VERSION
        assert refreshed_entry.metadata["content_origin"] == "managed_seed_file"
        assert refreshed_entry.metadata["content_migration_stage"] == "seed_file_to_sqlite"
        assert refreshed_entry.metadata["content_source_path"] == "player_wiki/data/dnd5e_rules_reference.json"
        assert refreshed_entry.source_path.endswith(
            f"player_wiki/data/dnd5e_rules_reference.json#{DND5E_RULES_REFERENCE_VERSION}"
        )
