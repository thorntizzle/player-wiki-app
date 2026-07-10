from __future__ import annotations

from tests.helpers.systems_importer_test_helpers import *

def test_scag_races_of_the_realms_wrappers_are_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_book_data_root(tmp_path / "dnd5e-source-scag-races-of-the-realms")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == [
        "Dwarves",
        "Elves",
        "Halflings",
        "Humans",
        "Dragonborn",
        "Gnomes",
        "Half-Elves",
        "Half-Orcs",
        "Tieflings",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dwarves_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")
    tieflings_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Tieflings'].slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Dwarves" in source_body
    assert "Tieflings" in source_body
    assert source_body.index("Dwarves") < source_body.index("Elves")
    assert source_body.index("Half-Elves") < source_body.index("Half-Orcs")
    assert source_body.index("Half-Orcs") < source_body.index("Tieflings")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Dwarves" in category_body
    assert "Tieflings" in category_body
    assert category_body.index("Dwarves") < category_body.index("Elves")
    assert category_body.index("Half-Elves") < category_body.index("Half-Orcs")
    assert category_body.index("Half-Orcs") < category_body.index("Tieflings")

    assert dwarves_response.status_code == 200
    dwarves_body = dwarves_response.get_data(as_text=True)
    assert "Chapter 3" in dwarves_body
    assert "Races of the Realms" in dwarves_body
    assert "Shield Dwarves" in dwarves_body
    assert "Gray Dwarves (Duergar)" in dwarves_body
    assert "Dwarven Deities" in dwarves_body
    assert 'href="#shield-dwarves"' in dwarves_body
    assert 'href="#gray-dwarves-duergar"' in dwarves_body
    assert 'id="dwarven-deities"' in dwarves_body

    assert tieflings_response.status_code == 200
    tieflings_body = tieflings_response.get_data(as_text=True)
    assert "Chapter 3" in tieflings_body
    assert "Races of the Realms" in tieflings_body
    assert "The Mark of Asmodeus" in tieflings_body
    assert "A Race without a Home" in tieflings_body
    assert "Tiefling Names" in tieflings_body
    assert "Aasimar" in tieflings_body
    assert 'href="#the-mark-of-asmodeus"' in tieflings_body
    assert 'href="#a-race-without-a-home"' in tieflings_body
    assert 'id="tiefling-names"' in tieflings_body
    assert 'id="aasimar"' in tieflings_body


def test_scag_races_of_the_realms_book_entries_follow_source_visibility(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_book_data_root(tmp_path / "dnd5e-source-scag-races-of-the-realms-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dwarves'].slug}")

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Dwarves" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Dwarves" in dm_body
    assert "Races of the Realms" in dm_body


def test_scag_classes_book_entries_follow_book_order_and_render_detail_pages(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_classes_book_data_root(tmp_path / "dnd5e-source-scag-classes")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == list(SCAG_CLASSES_TEST_HEADERS)

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    colleges_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Bardic Colleges'].slug}"
    )
    cantrips_response = client.get(
        "/campaigns/linden-pass/systems/entries/"
        f"{book_entries['Cantrips for Sorcerers, Warlocks, and Wizards'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    source_indexes = [source_body.index(title) for title in SCAG_CLASSES_TEST_HEADERS]
    assert source_indexes == sorted(source_indexes)

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    category_indexes = [category_body.index(title) for title in SCAG_CLASSES_TEST_HEADERS]
    assert category_indexes == sorted(category_indexes)

    assert colleges_response.status_code == 200
    colleges_body = colleges_response.get_data(as_text=True)
    assert "Chapter 4" in colleges_body
    assert "Classes" in colleges_body
    assert "College of Fochlucan" in colleges_body
    assert "College of New Olamn" in colleges_body
    assert "College of the Herald" in colleges_body
    assert 'href="#college-of-fochlucan"' in colleges_body
    assert 'href="#college-of-the-herald"' in colleges_body
    assert 'id="college-of-new-olamn"' in colleges_body

    assert cantrips_response.status_code == 200
    cantrips_body = cantrips_response.get_data(as_text=True)
    assert "Chapter 4" in cantrips_body
    assert "Classes" in cantrips_body
    assert "Booming Blade" in cantrips_body
    assert "Green-Flame Blade" in cantrips_body
    assert 'href="#booming-blade"' in cantrips_body
    assert 'id="green-flame-blade"' in cantrips_body


def test_scag_classes_book_entries_follow_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_scag_classes_book_data_root(tmp_path / "dnd5e-source-scag-classes-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=40)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Barbarians'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Barbarians'].slug}")

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Barbarians" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Barbarians" in dm_body
    assert "Classes" in dm_body


def test_scag_backgrounds_book_entry_is_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_scag_backgrounds_book_data_root(tmp_path / "dnd5e-source-scag-backgrounds-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == ["Backgrounds"]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    backgrounds_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Backgrounds" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 1 book chapters available to you in this source." in category_body
    assert "Backgrounds" in category_body

    assert backgrounds_response.status_code == 200
    backgrounds_body = backgrounds_response.get_data(as_text=True)
    assert "Chapter 5" in backgrounds_body
    assert "Backgrounds" in backgrounds_body
    assert "This chapter offers additional backgrounds for characters in a Forgotten Realms campaign" in backgrounds_body
    assert "City Watch" in backgrounds_body
    assert "Clan Crafter" in backgrounds_body
    assert "Urban Bounty Hunter" in backgrounds_body


def test_scag_backgrounds_book_entry_follows_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_scag_backgrounds_book_data_root(
        tmp_path / "dnd5e-source-scag-backgrounds-book-policy"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("SCAG", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/SCAG")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/SCAG/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}"
    )

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Backgrounds" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Backgrounds" in dm_body
    assert "City Watch" in dm_body


def test_scag_first_slice_excludes_setting_lore_chapters_from_book_imports(app, tmp_path):
    data_root = build_scag_first_slice_boundary_data_root(
        tmp_path / "dnd5e-source-scag-first-slice-boundary"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("SCAG", entry_types=["book"])
        store = app.extensions["systems_store"]
        book_entries = list(
            store.list_entries_for_source("DND-5E", "SCAG", entry_type="book", limit=20)
        )

    assert result.imported_count == 3
    assert result.imported_by_type == {"book": 3}
    book_titles = {entry.title for entry in book_entries}
    assert book_titles == {"Dwarves", "Barbarians", "Backgrounds"}
    assert "Welcome to the Realms" not in book_titles
    assert "The Sword Coast and the North" not in book_titles


def test_scag_entry_pages_surface_source_chapter_context_links(client, sign_in, users, app, tmp_path):
    data_root = build_scag_entry_source_context_data_root(
        tmp_path / "dnd5e-source-scag-entry-source-context"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "SCAG",
            entry_types=["book", "race", "subclass", "subclassfeature", "background", "item"],
        )

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="SCAG",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "SCAG",
                entry_type="book",
                limit=None,
            )
        }
        scag_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", limit=None)
            if entry.entry_type != "book"
        }

    sign_in(users["party"]["email"], users["party"]["password"])

    page_expectations = {
        "Ghostwise Halfling": ("Halflings",),
        "Path of the Battlerager": ("Primal Paths",),
        "Battlerager Armor": ("Primal Paths",),
        "Clan Crafter": ("Backgrounds",),
        "Spiked Armor": ("Primal Paths",),
        "Birdpipes": ("Musical Instruments",),
    }

    for title, book_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{scag_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Source Chapter Context" in body
        for book_title in book_titles:
            assert book_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{book_entries[book_title].slug}"'
                in body
            )


def test_phb_book_chapters_are_imported_and_browsable_in_book_order(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "PHB",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        book_entry_links = [f'/campaigns/linden-pass/systems/entries/{entry.slug}' for entry in book_entries]
        equipment = next(entry for entry in book_entries if entry.title == "Equipment")
        customization_options = next(entry for entry in book_entries if entry.title == "Customization Options")
        using_ability_scores = next(entry for entry in book_entries if entry.title == "Using Ability Scores")
        introduction = next(entry for entry in book_entries if entry.title == "Introduction")
        spellcasting = next(entry for entry in book_entries if entry.title == "Spellcasting")
        conditions = next(entry for entry in book_entries if entry.title == "Conditions")
        rules_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "RULES", entry_type="rule", limit=None)
        }
        passive_checks_rule = rules_entries["Passive Checks"]

    assert titles == [
        "Introduction",
        "Step-by-Step Characters",
        "Equipment",
        "Customization Options",
        "Using Ability Scores",
        "Adventuring",
        "Combat",
        "Spellcasting",
        "Conditions",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/book")
    equipment_response = client.get(f"/campaigns/linden-pass/systems/entries/{equipment.slug}")
    customization_response = client.get(f"/campaigns/linden-pass/systems/entries/{customization_options.slug}")
    detail_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores.slug}")
    intro_response = client.get(f"/campaigns/linden-pass/systems/entries/{introduction.slug}")
    spellcasting_response = client.get(f"/campaigns/linden-pass/systems/entries/{spellcasting.slug}")
    conditions_response = client.get(f"/campaigns/linden-pass/systems/entries/{conditions.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Introduction" in source_body
    assert "Equipment" in source_body
    assert "Customization Options" in source_body
    assert "Spellcasting" in source_body
    assert "Conditions" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 9 book chapters available to you in this source." in category_body
    for earlier, later in zip(book_entry_links, book_entry_links[1:]):
        assert category_body.index(earlier) < category_body.index(later)

    assert equipment_response.status_code == 200
    equipment_body = equipment_response.get_data(as_text=True)
    assert "Chapter 5" in equipment_body
    assert "Armor and Shields" in equipment_body
    assert "Weapons" in equipment_body
    assert 'href="#armor-and-shields"' in equipment_body
    assert 'id="armor-and-shields"' in equipment_body

    assert customization_response.status_code == 200
    customization_body = customization_response.get_data(as_text=True)
    assert "Chapter 6" in customization_body
    assert "Multiclassing" in customization_body
    assert "Feats" in customization_body
    assert 'href="#multiclassing"' in customization_body
    assert 'id="multiclassing"' in customization_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "Chapter 7" in detail_body
    assert "Chapter Navigation" in detail_body
    assert 'href="#advantage-and-disadvantage"' in detail_body
    assert 'href="#ability-checks--contests"' in detail_body
    assert 'id="advantage-and-disadvantage"' in detail_body
    assert 'id="ability-checks--contests"' in detail_body
    assert "Advantage and Disadvantage" in detail_body
    assert "Contests" in detail_body
    assert "Passive Checks" in detail_body
    assert "10 + all modifiers that normally apply to the check" in detail_body
    assert "Rules:" in detail_body
    assert f'href="/campaigns/linden-pass/systems/entries/{passive_checks_rule.slug}"' in detail_body
    assert "book/PHB/ch7.webp" not in detail_body
    assert "p. 175" in detail_body

    assert intro_response.status_code == 200
    intro_body = intro_response.get_data(as_text=True)
    assert "How to Play" in intro_body
    assert "book/PHB/intro.webp" not in intro_body

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert 'href="#casting-a-spell--components"' in spellcasting_body
    assert 'href="#targets--areas-of-effect"' in spellcasting_body
    assert 'id="casting-a-spell--components"' in spellcasting_body
    assert 'id="targets--areas-of-effect"' in spellcasting_body

    assert conditions_response.status_code == 200
    conditions_body = conditions_response.get_data(as_text=True)
    assert "Appendix A" in conditions_body
    assert "Conditions alter a creature" in conditions_body
    assert "blinded" in conditions_body


def test_dmg_book_chapters_are_imported_for_dm_browse_in_book_order(
    client, sign_in, users, app, tmp_path
):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

        service = app.extensions["systems_service"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "DMG",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        book_entry_links = [f'/campaigns/linden-pass/systems/entries/{entry.slug}' for entry in book_entries]
        multiverse = next(entry for entry in book_entries if entry.title == "Creating a Multiverse")
        traps = next(entry for entry in book_entries if entry.title == "Traps")
        downtime_activities = next(entry for entry in book_entries if entry.title == "Downtime Activities")
        treasure = next(entry for entry in book_entries if entry.title == "Treasure")
        running_the_game = next(entry for entry in book_entries if entry.title == "Running the Game")

    assert titles == [
        "Creating a Multiverse",
        "Traps",
        "Downtime Activities",
        "Treasure",
        "Running the Game",
        "Dungeon Master's Workshop",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    multiverse_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse.slug}")
    traps_response = client.get(f"/campaigns/linden-pass/systems/entries/{traps.slug}")
    downtime_response = client.get(f"/campaigns/linden-pass/systems/entries/{downtime_activities.slug}")
    treasure_response = client.get(f"/campaigns/linden-pass/systems/entries/{treasure.slug}")
    running_the_game_response = client.get(f"/campaigns/linden-pass/systems/entries/{running_the_game.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Creating a Multiverse" in source_body
    assert "Traps" in source_body
    assert "Downtime Activities" in source_body
    assert "Treasure" in source_body
    assert "Running the Game" in source_body
    assert "Dungeon Master&#39;s Workshop" in source_body
    assert "Adventure Environments" in source_body
    assert "Between Adventures" in source_body
    assert "Searches only this source&#39;s book chapters using curated metadata" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 6 book chapters available to you in this source." in category_body
    for earlier, later in zip(book_entry_links, book_entry_links[1:]):
        assert category_body.index(earlier) < category_body.index(later)

    assert multiverse_response.status_code == 200
    multiverse_body = multiverse_response.get_data(as_text=True)
    assert "Chapter 2" in multiverse_body
    assert "The Planes" in multiverse_body
    assert "Planar Travel" in multiverse_body
    assert "Outer Planes" in multiverse_body
    assert "Optional Rules" in multiverse_body
    assert "Known Worlds of the Material Plane" in multiverse_body
    assert 'href="#the-planes"' in multiverse_body
    assert 'id="the-planes"' in multiverse_body
    assert 'href="#outer-planes--optional-rules"' in multiverse_body
    assert 'id="outer-planes--optional-rules"' in multiverse_body

    assert traps_response.status_code == 200
    traps_body = traps_response.get_data(as_text=True)
    assert "Chapter 5" in traps_body
    assert "Adventure Environments" in traps_body
    assert "Traps in Play" in traps_body
    assert "Triggering a Trap" in traps_body
    assert "Detecting and Disabling a Trap" in traps_body
    assert "Trap Effects" in traps_body
    assert "Complex Traps" in traps_body
    assert "Sample Traps" in traps_body
    assert "Wilderness Survival" not in traps_body
    assert 'href="#traps-in-play"' in traps_body
    assert 'id="traps-in-play"' in traps_body
    assert 'href="#traps-in-play--triggering-a-trap"' in traps_body
    assert 'id="traps-in-play--triggering-a-trap"' in traps_body

    assert downtime_response.status_code == 200
    downtime_body = downtime_response.get_data(as_text=True)
    assert "Chapter 6" in downtime_body
    assert "Between Adventures" in downtime_body
    assert "More Downtime Activities" in downtime_body
    assert "Creating Downtime Activities" in downtime_body
    assert "Recurring Expenses" not in downtime_body
    assert 'href="#more-downtime-activities"' in downtime_body
    assert 'id="more-downtime-activities"' in downtime_body

    assert treasure_response.status_code == 200
    treasure_body = treasure_response.get_data(as_text=True)
    assert "Chapter 7" in treasure_body
    assert "Magic Items" in treasure_body
    assert "Attunement" in treasure_body
    assert 'href="#magic-items"' in treasure_body
    assert 'id="magic-items"' in treasure_body

    assert running_the_game_response.status_code == 200
    running_the_game_body = running_the_game_response.get_data(as_text=True)
    assert "Chapter 8" in running_the_game_body
    assert "Chapter Navigation" in running_the_game_body
    assert 'href="#using-ability-scores"' in running_the_game_body
    assert 'id="using-ability-scores"' in running_the_game_body
    assert "Chases" in running_the_game_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_multiverse_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse.slug}")
    assert blocked_multiverse_response.status_code == 404


def test_mm_intro_book_sections_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["book"])

        service = app.extensions["systems_service"]
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "MM",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        statistics = next(entry for entry in book_entries if entry.title == "Statistics")
        legendary = next(entry for entry in book_entries if entry.title == "Legendary Creatures")
        shadow_dragon_template = next(entry for entry in book_entries if entry.title == "Shadow Dragon Template")
        half_dragon_template = next(entry for entry in book_entries if entry.title == "Half-Dragon Template")
        spore_servant_template = next(entry for entry in book_entries if entry.title == "Spore Servant Template")
        customizing_npcs = next(entry for entry in book_entries if entry.title == "Customizing NPCs")

    assert titles == [
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/MM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/MM/types/book")
    statistics_response = client.get(f"/campaigns/linden-pass/systems/entries/{statistics.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Statistics" in source_body
    assert "Legendary Creatures" in source_body
    assert "Shadow Dragon Template" in source_body
    assert "Half-Dragon Template" in source_body
    assert "Spore Servant Template" in source_body
    assert "Customizing NPCs" in source_body
    assert source_body.index("Statistics") < source_body.index("Legendary Creatures")
    assert source_body.index("Legendary Creatures") < source_body.index("Shadow Dragon Template")
    assert source_body.index("Shadow Dragon Template") < source_body.index("Half-Dragon Template")
    assert source_body.index("Half-Dragon Template") < source_body.index("Spore Servant Template")
    assert source_body.index("Spore Servant Template") < source_body.index("Customizing NPCs")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Statistics" in category_body
    assert "Legendary Creatures" in category_body
    assert "Shadow Dragon Template" in category_body
    assert "Half-Dragon Template" in category_body
    assert "Spore Servant Template" in category_body
    assert "Customizing NPCs" in category_body
    assert category_body.index("Statistics") < category_body.index("Legendary Creatures")
    assert category_body.index("Legendary Creatures") < category_body.index("Shadow Dragon Template")
    assert category_body.index("Shadow Dragon Template") < category_body.index("Half-Dragon Template")
    assert category_body.index("Half-Dragon Template") < category_body.index("Spore Servant Template")
    assert category_body.index("Spore Servant Template") < category_body.index("Customizing NPCs")

    assert statistics_response.status_code == 200
    statistics_body = statistics_response.get_data(as_text=True)
    assert "Introduction" in statistics_body
    assert "Chapter Navigation" in statistics_body
    assert "Size" in statistics_body
    assert "Type" in statistics_body
    assert "Tags" in statistics_body
    assert "Speed" in statistics_body
    assert "Burrow" in statistics_body
    assert "Senses" in statistics_body
    assert "Blindsight" in statistics_body
    assert "Challenge" in statistics_body
    assert "Experience Points" in statistics_body
    assert "Equipment" in statistics_body
    assert "Legendary Creatures" not in statistics_body
    assert "Size Categories" in statistics_body
    assert 'href="#type--tags"' in statistics_body
    assert 'id="type--tags"' in statistics_body
    assert 'href="#senses--blindsight"' in statistics_body
    assert 'id="senses--blindsight"' in statistics_body

    legendary_response = client.get(f"/campaigns/linden-pass/systems/entries/{legendary.slug}")
    assert legendary_response.status_code == 200
    legendary_body = legendary_response.get_data(as_text=True)
    assert "Introduction" in legendary_body
    assert "Chapter Navigation" in legendary_body
    assert "Legendary Actions" in legendary_body
    assert "A Legendary Creature&#39;s Lair" in legendary_body
    assert "Lair Actions" in legendary_body
    assert "Regional Effects" in legendary_body
    assert "Statistics" not in legendary_body
    assert 'href="#legendary-actions"' in legendary_body
    assert 'id="legendary-actions"' in legendary_body
    assert 'href="#a-legendary-creatures-lair--lair-actions"' in legendary_body
    assert 'id="a-legendary-creatures-lair--regional-effects"' in legendary_body

    shadow_response = client.get(f"/campaigns/linden-pass/systems/entries/{shadow_dragon_template.slug}")
    assert shadow_response.status_code == 200
    shadow_body = shadow_response.get_data(as_text=True)
    assert "Introduction" in shadow_body
    assert "Chapter Navigation" in shadow_body
    assert "Damage Resistances" in shadow_body
    assert "Skills" in shadow_body
    assert "Living Shadow" in shadow_body
    assert "Shadow Breath" in shadow_body
    assert "Legendary Actions" not in shadow_body
    assert 'href="#damage-resistances"' in shadow_body
    assert 'id="damage-resistances"' in shadow_body
    assert 'href="#living-shadow"' in shadow_body
    assert 'id="shadow-breath"' in shadow_body

    half_dragon_response = client.get(f"/campaigns/linden-pass/systems/entries/{half_dragon_template.slug}")
    assert half_dragon_response.status_code == 200
    half_dragon_body = half_dragon_response.get_data(as_text=True)
    assert "Introduction" in half_dragon_body
    assert "Chapter Navigation" in half_dragon_body
    assert "Challenge" in half_dragon_body
    assert "Senses" in half_dragon_body
    assert "blindsight" in half_dragon_body
    assert "darkvision" in half_dragon_body
    assert "Resistances" in half_dragon_body
    assert "Damage Resistance" in half_dragon_body
    assert "Languages" in half_dragon_body
    assert "Breath Weapon" in half_dragon_body
    assert "Optional Prerequisite" in half_dragon_body
    assert "Shadow Breath" not in half_dragon_body
    assert 'href="#challenge"' in half_dragon_body
    assert 'id="challenge"' in half_dragon_body
    assert 'href="#new-action-breath-weapon"' in half_dragon_body
    assert 'id="new-action-breath-weapon"' in half_dragon_body

    spore_servant_response = client.get(f"/campaigns/linden-pass/systems/entries/{spore_servant_template.slug}")
    assert spore_servant_response.status_code == 200
    spore_servant_body = spore_servant_response.get_data(as_text=True)
    assert "Introduction" in spore_servant_body
    assert "Chapter Navigation" in spore_servant_body
    assert "Retained Characteristics" in spore_servant_body
    assert "Lost Characteristics" in spore_servant_body
    assert "Type" in spore_servant_body
    assert "Speed" in spore_servant_body
    assert "Ability Scores" in spore_servant_body
    assert "Senses" in spore_servant_body
    assert "blindsight" in spore_servant_body
    assert "Condition Immunities" in spore_servant_body
    assert "Languages" in spore_servant_body
    assert "rapport spores" in spore_servant_body
    assert "Attacks" in spore_servant_body
    assert "Breath Weapon" not in spore_servant_body
    assert 'href="#retained-characteristics"' in spore_servant_body
    assert 'id="retained-characteristics"' in spore_servant_body
    assert 'href="#senses"' in spore_servant_body
    assert 'id="senses"' in spore_servant_body
    assert 'href="#condition-immunities"' in spore_servant_body
    assert 'id="attacks"' in spore_servant_body

    customizing_npcs_response = client.get(f"/campaigns/linden-pass/systems/entries/{customizing_npcs.slug}")
    assert customizing_npcs_response.status_code == 200
    customizing_npcs_body = customizing_npcs_response.get_data(as_text=True)
    assert "Appendix B" in customizing_npcs_body
    assert "From Appendix B: Nonplayer Characters" in customizing_npcs_body
    assert "Chapter Navigation" in customizing_npcs_body
    assert "Racial Traits" in customizing_npcs_body
    assert "Spell Swaps" in customizing_npcs_body
    assert "Armor and Weapon Swaps" in customizing_npcs_body
    assert "NPC Descriptions" not in customizing_npcs_body
    assert 'href="#racial-traits"' in customizing_npcs_body
    assert 'id="racial-traits"' in customizing_npcs_body
    assert 'href="#armor-and-weapon-swaps"' in customizing_npcs_body
    assert 'id="armor-and-weapon-swaps"' in customizing_npcs_body


def test_vgm_character_race_wrappers_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "VGM",
            entry_type="book",
            limit=None,
        )
        titles = [entry.title for entry in book_entries]
        aasimar = next(entry for entry in book_entries if entry.title == "Aasimar")
        monstrous = next(entry for entry in book_entries if entry.title == "Monstrous Adventurers")
        height_and_weight = next(entry for entry in book_entries if entry.title == "Height and Weight")

    assert titles == [
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    aasimar_response = client.get(f"/campaigns/linden-pass/systems/entries/{aasimar.slug}")
    monstrous_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous.slug}")
    height_response = client.get(f"/campaigns/linden-pass/systems/entries/{height_and_weight.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Aasimar" in source_body
    assert "Firbolg" in source_body
    assert "Monstrous Adventurers" in source_body
    assert "Height and Weight" in source_body
    assert source_body.index("Aasimar") < source_body.index("Firbolg")
    assert source_body.index("Triton") < source_body.index("Monstrous Adventurers")
    assert source_body.index("Monstrous Adventurers") < source_body.index("Height and Weight")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Aasimar" in category_body
    assert "Firbolg" in category_body
    assert "Monstrous Adventurers" in category_body
    assert "Height and Weight" in category_body
    assert category_body.index("Aasimar") < category_body.index("Firbolg")
    assert category_body.index("Triton") < category_body.index("Monstrous Adventurers")
    assert category_body.index("Monstrous Adventurers") < category_body.index("Height and Weight")

    assert aasimar_response.status_code == 200
    aasimar_body = aasimar_response.get_data(as_text=True)
    assert "Chapter 2" in aasimar_body
    assert "Character Races" in aasimar_body
    assert "Celestial Champions" in aasimar_body
    assert "Aasimar Guides" in aasimar_body
    assert "Protector" in aasimar_body
    assert "Scourge" in aasimar_body
    assert "Fallen" in aasimar_body
    assert 'href="#celestial-champions"' in aasimar_body
    assert 'id="celestial-champions"' in aasimar_body
    assert 'href="#protector"' in aasimar_body
    assert 'id="fallen"' in aasimar_body

    assert monstrous_response.status_code == 200
    monstrous_body = monstrous_response.get_data(as_text=True)
    assert "Chapter 2" in monstrous_body
    assert "Character Races" in monstrous_body
    assert "Why a Monstrous Character?" in monstrous_body
    assert "Rare or Mundane?" in monstrous_body
    assert "Outcast or Ambassador?" in monstrous_body
    assert "Friends or Enemies?" in monstrous_body
    assert 'href="#rare-or-mundane"' in monstrous_body
    assert 'id="friends-or-enemies"' in monstrous_body

    assert height_response.status_code == 200
    height_body = height_response.get_data(as_text=True)
    assert "Chapter 2" in height_body
    assert "Character Races" in height_body
    assert "Base Height" in height_body
    assert "Base Weight" in height_body
    assert "Bugbear" in height_body
    assert "Triton" in height_body
    assert "Yuan-ti Pureblood" in height_body
    assert 'href="#height-and-weight"' not in height_body


def test_vgm_monster_lore_wrappers_are_imported_for_dm_browse(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore-browse")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == [
        "Beholders: Bad Dreams Come True",
        "Giants: World Shakers",
        "Gnolls: The Insatiable Hunger",
        "Goblinoids: The Conquering Host",
        "Hags: Dark Sisterhood",
        "Kobolds: Little Dragons",
        "Mind Flayers: Scourge of Worlds",
        "Orcs: The Godsworn",
        "Yuan-ti: Snake People",
    ]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    beholders_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Beholders: Bad Dreams Come True'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f"{book_entries['Beholders: Bad Dreams Come True'].slug}\""
        in source_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f"{book_entries['Yuan-ti: Snake People'].slug}\""
        in source_body
    )
    assert source_body.index("Beholders: Bad Dreams Come True") < source_body.index("Giants: World Shakers")
    assert source_body.index("Kobolds: Little Dragons") < source_body.index("Mind Flayers: Scourge of Worlds")
    assert source_body.index("Orcs: The Godsworn") < source_body.index("Yuan-ti: Snake People")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Beholders: Bad Dreams Come True" in category_body
    assert "Mind Flayers: Scourge of Worlds" in category_body
    assert "Yuan-ti: Snake People" in category_body
    assert category_body.index("Beholders: Bad Dreams Come True") < category_body.index("Giants: World Shakers")
    assert category_body.index("Kobolds: Little Dragons") < category_body.index("Mind Flayers: Scourge of Worlds")
    assert category_body.index("Orcs: The Godsworn") < category_body.index("Yuan-ti: Snake People")

    assert beholders_response.status_code == 200
    beholders_body = beholders_response.get_data(as_text=True)
    assert "Chapter 1" in beholders_body
    assert "Monster Lore" in beholders_body
    assert "Chapter Navigation" in beholders_body
    assert "Roleplaying a Beholder" in beholders_body
    assert "Battle Tactics" in beholders_body
    assert "Variant Abilities" in beholders_body
    assert 'href="#roleplaying-a-beholder"' in beholders_body
    assert 'href="#battle-tactics"' in beholders_body
    assert 'id="variant-abilities"' in beholders_body


def test_vgm_monster_lore_wrappers_surface_related_monster_family_entries(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "monster"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }
        monster_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="monster", limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page_expectations = {
        "Beholders: Bad Dreams Come True": ("Death Kiss", "Gauth", "Gazer"),
        "Giants: World Shakers": ("Cloud Giant Smiling One", "Mouth of Grolantor"),
        "Gnolls: The Insatiable Hunger": ("Flind", "Gnoll Witherling"),
        "Goblinoids: The Conquering Host": ("Nilbog", "Hobgoblin Devastator"),
        "Hags: Dark Sisterhood": ("Annis Hag", "Bheur Hag"),
        "Kobolds: Little Dragons": ("Kobold Dragonshield", "Kobold Inventor"),
        "Mind Flayers: Scourge of Worlds": ("Alhoon", "Mindwitness", "Ulitharid"),
        "Orcs: The Godsworn": ("Orc Hand of Yurtrus", "Tanarukk"),
        "Yuan-ti: Snake People": ("Yuan-ti Anathema", "Yuan-ti Broodguard"),
    }

    for title, monster_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Related Monsters" in body
        for monster_title in monster_titles:
            assert monster_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{monster_entries[monster_title].slug}"'
                in body
            )


def test_vgm_monster_lore_wrappers_preserve_reference_only_source_context_sections(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_monster_lore_data_root(tmp_path / "dnd5e-source-vgm-monster-lore-source-context")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])

    beholder_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Beholders: Bad Dreams Come True'].slug}"
    )
    assert beholder_response.status_code == 200
    beholder_body = beholder_response.get_data(as_text=True)
    assert "Source Context" in beholder_body
    assert "roleplaying, lair, tactics, and variant-ability guidance" in beholder_body
    assert "The app does not currently model them automatically." in beholder_body
    assert 'href="#roleplaying-a-beholder"' in beholder_body
    assert 'href="#battle-tactics"' in beholder_body
    assert 'href="#variant-abilities"' in beholder_body
    assert 'id="roleplaying-a-beholder"' in beholder_body
    assert 'id="variant-abilities"' in beholder_body

    hag_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Hags: Dark Sisterhood'].slug}")
    assert hag_response.status_code == 200
    hag_body = hag_response.get_data(as_text=True)
    assert 'href="#hag-lair-actions"' in hag_body
    assert 'href="#hag-lair-actions--lair-actions"' in hag_body
    assert 'href="#hag-lair-actions--regional-effects"' in hag_body
    assert 'id="hag-lair-actions--regional-effects"' in hag_body

    kobold_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Kobolds: Little Dragons'].slug}"
    )
    assert kobold_response.status_code == 200
    kobold_body = kobold_response.get_data(as_text=True)
    assert 'href="#tactics"' in kobold_body
    assert 'id="tactics"' in kobold_body


def test_vgm_character_race_wrappers_surface_related_race_entries(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-character-race-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "race"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "VGM",
                entry_type="book",
                limit=None,
            )
        }
        race_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="race", limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page_expectations = {
        "Aasimar": ("Aasimar", "Protector Aasimar", "Scourge Aasimar", "Fallen Aasimar"),
        "Firbolg": ("Firbolg",),
        "Goliath": ("Goliath",),
        "Kenku": ("Kenku",),
        "Lizardfolk": ("Lizardfolk",),
        "Tabaxi": ("Tabaxi",),
        "Triton": ("Triton",),
        "Monstrous Adventurers": ("Bugbear", "Goblin", "Hobgoblin", "Kobold", "Orc", "Yuan-ti Pureblood"),
        "Height and Weight": ("Aasimar", "Firbolg", "Triton", "Bugbear", "Yuan-ti Pureblood"),
    }

    for title, race_titles in page_expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Related Races" in body
        for race_title in race_titles:
            assert race_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{race_entries[race_title].slug}"' in body
            )


def test_mm_book_pages_surface_related_monsters_and_monster_rules(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["action", "condition", "sense", "skill", "status"])
        importer.import_source("MM", entry_types=["book", "monster", "sense"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "MM",
                entry_type="book",
                limit=None,
            )
        }
        mm_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("monster", "sense")
            for entry in store.list_entries_for_source("DND-5E", "MM", entry_type=entry_type, limit=None)
        }
        phb_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "condition", "sense", "skill", "status")
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type=entry_type, limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    statistics_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Statistics'].slug}")
    legendary_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Legendary Creatures'].slug}"
    )
    shadow_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Shadow Dragon Template'].slug}"
    )
    half_dragon_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Half-Dragon Template'].slug}"
    )
    spore_servant_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spore Servant Template'].slug}"
    )

    assert statistics_response.status_code == 200
    statistics_body = statistics_response.get_data(as_text=True)
    assert "Monsters:" in statistics_body
    assert "Skills:" in statistics_body
    assert "Senses:" in statistics_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("monster", "Goblin")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("monster", "Guard")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Perception")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{mm_entries[("sense", "Tremorsense")].slug}"'
        in statistics_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Invisible")].slug}"'
        in statistics_body
    )


    assert legendary_response.status_code == 200
    legendary_body = legendary_response.get_data(as_text=True)
    assert "Conditions:" in legendary_body
    assert "Statuses:" in legendary_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Incapacitated")].slug}"'
        in legendary_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("status", "Surprised")].slug}"'
        in legendary_body
    )

    assert shadow_response.status_code == 200
    shadow_body = shadow_response.get_data(as_text=True)
    assert "Skills:" in shadow_body
    assert "Actions:" in shadow_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Stealth")].slug}"'
        in shadow_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Hide")].slug}"'
        in shadow_body
    )

    assert half_dragon_response.status_code == 200
    half_dragon_body = half_dragon_response.get_data(as_text=True)
    assert "Senses:" in half_dragon_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Blindsight")].slug}"'
        in half_dragon_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"'
        in half_dragon_body
    )

    assert spore_servant_response.status_code == 200
    spore_servant_body = spore_servant_response.get_data(as_text=True)
    assert "Senses:" in spore_servant_body
    assert "Conditions:" in spore_servant_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Blindsight")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Blinded")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Charmed")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Frightened")].slug}"'
        in spore_servant_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Paralyzed")].slug}"'
        in spore_servant_body
    )


def test_mtf_blood_war_cult_and_ancestry_pages_are_imported_for_dm_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mtf_book_data_root(tmp_path / "dnd5e-source-mtf-blood-war-wrappers")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("MTF", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="MTF",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "MTF",
                entry_type="book",
                limit=None,
            )
        }

    assert result.imported_count == 8
    assert result.imported_by_type == {"book": 8}
    assert list(book_entries) == [
        "Diabolical Cults",
        "Tiefling Subraces",
        "Demonic Boons",
        "Fiendish Cults",
        "Elf Subraces",
        "Duergar Characters",
        "Gith Characters",
        "Deep Gnome Characters",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Diabolical Cults'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    diabolical_cults_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Diabolical Cults'].slug}"
    )
    tiefling_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Tiefling Subraces'].slug}"
    )
    demonic_boons_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Demonic Boons'].slug}"
    )
    fiendish_cults_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Fiendish Cults'].slug}"
    )
    elf_entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Elf Subraces'].slug}")
    duergar_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Duergar Characters'].slug}"
    )
    gith_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Gith Characters'].slug}"
    )
    deep_gnome_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Deep Gnome Characters'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Diabolical Cults" in source_body
    assert "Tiefling Subraces" in source_body
    assert "Demonic Boons" in source_body
    assert "Fiendish Cults" in source_body
    assert "Elf Subraces" in source_body
    assert "Duergar Characters" in source_body
    assert "Gith Characters" in source_body
    assert "Deep Gnome Characters" in source_body
    assert source_body.index("Diabolical Cults") < source_body.index("Tiefling Subraces")
    assert source_body.index("Tiefling Subraces") < source_body.index("Demonic Boons")
    assert source_body.index("Demonic Boons") < source_body.index("Fiendish Cults")
    assert source_body.index("Fiendish Cults") < source_body.index("Elf Subraces")
    assert source_body.index("Elf Subraces") < source_body.index("Duergar Characters")
    assert source_body.index("Duergar Characters") < source_body.index("Gith Characters")
    assert source_body.index("Gith Characters") < source_body.index("Deep Gnome Characters")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 8 book chapters available to you in this source." in category_body
    assert "Diabolical Cults" in category_body
    assert "Tiefling Subraces" in category_body
    assert "Demonic Boons" in category_body
    assert "Fiendish Cults" in category_body
    assert "Elf Subraces" in category_body
    assert "Duergar Characters" in category_body
    assert "Gith Characters" in category_body
    assert "Deep Gnome Characters" in category_body
    assert category_body.index("Diabolical Cults") < category_body.index("Tiefling Subraces")
    assert category_body.index("Tiefling Subraces") < category_body.index("Demonic Boons")
    assert category_body.index("Demonic Boons") < category_body.index("Fiendish Cults")
    assert category_body.index("Fiendish Cults") < category_body.index("Elf Subraces")
    assert category_body.index("Elf Subraces") < category_body.index("Duergar Characters")
    assert category_body.index("Duergar Characters") < category_body.index("Gith Characters")
    assert category_body.index("Gith Characters") < category_body.index("Deep Gnome Characters")

    assert diabolical_cults_response.status_code == 200
    diabolical_cults_body = diabolical_cults_response.get_data(as_text=True)
    assert "Chapter 1" in diabolical_cults_body
    assert "The Blood War" in diabolical_cults_body
    assert "Cults dedicated to infernal beings are the foes of adventurers throughout the D&amp;D multiverse." in diabolical_cults_body
    assert "Cult of Glasya" in diabolical_cults_body
    assert "Typical Cultist: Spy" in diabolical_cults_body

    assert tiefling_entry_response.status_code == 200
    tiefling_entry_body = tiefling_entry_response.get_data(as_text=True)
    assert "Chapter 1" in tiefling_entry_body
    assert "The Blood War" in tiefling_entry_body
    assert "At the DM&#x27;s option" in tiefling_entry_body
    assert "Tiefling (Asmodeus)" in tiefling_entry_body
    assert "Tiefling (Mephistopheles)" in tiefling_entry_body
    assert "Tiefling (Zariel)" in tiefling_entry_body

    assert demonic_boons_entry_response.status_code == 200
    demonic_boons_entry_body = demonic_boons_entry_response.get_data(as_text=True)
    assert "Chapter 1" in demonic_boons_entry_body
    assert "The Blood War" in demonic_boons_entry_body
    assert "Wicked folk who seek power from demons are scattered across the multiverse." in demonic_boons_entry_body
    assert "Demonic Boon of Baphomet" in demonic_boons_entry_body
    assert "Demonic Boon of Orcus" in demonic_boons_entry_body
    assert "Demonic Boon of Zuggtmoy" in demonic_boons_entry_body

    assert fiendish_cults_response.status_code == 200
    fiendish_cults_body = fiendish_cults_response.get_data(as_text=True)
    assert "Chapter 1" in fiendish_cults_body
    assert "The Blood War" in fiendish_cults_body
    assert "The following tables can be used to generate random cults dedicated to fiends." in fiendish_cults_body
    assert "Cult Goals" in fiendish_cults_body
    assert "Open a gate to the Abyss or the Nine Hells." in fiendish_cults_body

    assert elf_entry_response.status_code == 200
    elf_entry_body = elf_entry_response.get_data(as_text=True)
    assert "Chapter 2" in elf_entry_body
    assert "Elves" in elf_entry_body
    assert "At the DM&#x27;s discretion" in elf_entry_body
    assert "Elf (Eladrin)" in elf_entry_body
    assert "Elf (Sea)" in elf_entry_body
    assert "Elf (Shadar-kai)" in elf_entry_body

    assert duergar_entry_response.status_code == 200
    duergar_entry_body = duergar_entry_response.get_data(as_text=True)
    assert "Chapter 3" in duergar_entry_body
    assert "Dwarves and Duergar" in duergar_entry_body
    assert "At the DM&#x27;s discretion" in duergar_entry_body
    assert "Dwarf (Duergar)" in duergar_entry_body

    assert gith_entry_response.status_code == 200
    gith_entry_body = gith_entry_response.get_data(as_text=True)
    assert "Chapter 4" in gith_entry_body
    assert "Gith and Their Endless War" in gith_entry_body
    assert "At the DM&#x27;s option" in gith_entry_body
    assert "Gith (Githyanki)" in gith_entry_body
    assert "Gith (Githzerai)" in gith_entry_body
    assert "Gith Random Height and Weight" in gith_entry_body

    assert deep_gnome_entry_response.status_code == 200
    deep_gnome_entry_body = deep_gnome_entry_response.get_data(as_text=True)
    assert "Chapter 5" in deep_gnome_entry_body
    assert "Halflings and Gnomes" in deep_gnome_entry_body
    assert "At the DM&#x27;s discretion" in deep_gnome_entry_body
    assert "Gnome (Deep)" in deep_gnome_entry_body


def test_mtf_wrapper_pages_preserve_detail_navigation_and_inline_race_links(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mtf_book_data_root(tmp_path / "dnd5e-source-mtf-wrapper-navigation")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MTF", entry_types=["book", "race"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="MTF",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "MTF",
                entry_type="book",
                limit=None,
            )
        }
        race_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])

    diabolical_cults_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Diabolical Cults'].slug}"
    )
    fiendish_cults_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Fiendish Cults'].slug}"
    )
    tiefling_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Tiefling Subraces'].slug}")
    elf_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Elf Subraces'].slug}")
    duergar_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Duergar Characters'].slug}"
    )
    gith_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Gith Characters'].slug}")
    deep_gnome_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Deep Gnome Characters'].slug}"
    )

    assert diabolical_cults_response.status_code == 200
    diabolical_cults_body = diabolical_cults_response.get_data(as_text=True)
    assert "Chapter Navigation" in diabolical_cults_body
    assert 'href="#cult-of-glasya"' in diabolical_cults_body
    assert 'id="cult-of-glasya"' in diabolical_cults_body

    assert fiendish_cults_response.status_code == 200
    fiendish_cults_body = fiendish_cults_response.get_data(as_text=True)
    assert "Chapter Navigation" in fiendish_cults_body
    assert 'href="#cult-goals"' in fiendish_cults_body
    assert 'id="cult-goals"' in fiendish_cults_body

    assert tiefling_response.status_code == 200
    tiefling_body = tiefling_response.get_data(as_text=True)
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{race_entries["Asmodeus Tiefling"].slug}"' in tiefling_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{race_entries["Mephistopheles Tiefling"].slug}"'
        in tiefling_body
    )
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Zariel Tiefling"].slug}"' in tiefling_body

    assert elf_response.status_code == 200
    elf_body = elf_response.get_data(as_text=True)
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Eladrin"].slug}"' in elf_body
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Sea Elf"].slug}"' in elf_body
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Shadar-kai"].slug}"' in elf_body

    assert duergar_response.status_code == 200
    duergar_body = duergar_response.get_data(as_text=True)
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Duergar"].slug}"' in duergar_body

    assert gith_response.status_code == 200
    gith_body = gith_response.get_data(as_text=True)
    assert "Chapter Navigation" in gith_body
    assert 'href="#gith-random-height-and-weight"' in gith_body
    assert 'id="gith-random-height-and-weight"' in gith_body
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Githyanki"].slug}"' in gith_body
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Githzerai"].slug}"' in gith_body

    assert deep_gnome_response.status_code == 200
    deep_gnome_body = deep_gnome_response.get_data(as_text=True)
    assert f'href="/campaigns/linden-pass/systems/entries/{race_entries["Deep Gnome"].slug}"' in deep_gnome_body


def test_egw_heroic_chronicle_page_is_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_egw_heroic_chronicle_book_data_root(
        tmp_path / "dnd5e-source-egw-heroic-chronicle"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("EGW", entry_types=["book"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "EGW",
                entry_type="book",
                limit=None,
            )
        }

    assert result.imported_count == 1
    assert result.imported_by_type == {"book": 1}
    assert list(book_entries) == ["Heroic Chronicle"]

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    detail_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Heroic Chronicle'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Heroic Chronicle" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 1 book chapters available to you in this source." in category_body
    assert "Heroic Chronicle" in category_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "Chapter 4" in detail_body
    assert "Character Options" in detail_body
    assert "Heroic Chronicle" in detail_body
    assert (
        "The heroic chronicle system lets players and Dungeon Masters build a backstory rooted in Wildemount."
        in detail_body
    )
    assert "Backstory" in detail_body
    assert "Homeland" in detail_body
    assert "Mysterious Secret" in detail_body
    assert "Prophecy" in detail_body
    assert "Prophecy Rewards" in detail_body
    assert "Chapter Navigation" in detail_body
    assert 'href="#backstory"' in detail_body
    assert 'id="backstory"' in detail_body
    assert 'href="#prophecy"' in detail_body
    assert 'id="prophecy"' in detail_body


def test_egw_dunamis_page_is_imported_for_player_browse_and_keeps_book_order(
    client, sign_in, users, app, tmp_path
):
    data_root = build_egw_dunamis_book_data_root(tmp_path / "dnd5e-source-egw-dunamis")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("EGW", entry_types=["book"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "EGW",
                entry_type="book",
                limit=None,
            )
        }

    assert result.imported_count == 3
    assert result.imported_by_type == {"book": 3}
    assert list(book_entries) == ["Hollow One", "Dunamis and Dunamancy", "Heroic Chronicle"]

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    hollow_one_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Hollow One'].slug}"
    )
    detail_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamis and Dunamancy'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert source_body.index("Hollow One") < source_body.index("Dunamis and Dunamancy")
    assert source_body.index("Dunamis and Dunamancy") < source_body.index("Heroic Chronicle")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 3 book chapters available to you in this source." in category_body
    assert category_body.index("Hollow One") < category_body.index("Dunamis and Dunamancy")
    assert category_body.index("Dunamis and Dunamancy") < category_body.index("Heroic Chronicle")

    assert hollow_one_response.status_code == 200
    hollow_one_body = hollow_one_response.get_data(as_text=True)
    assert "Chapter 4" in hollow_one_body
    assert "Character Options" in hollow_one_body
    assert "Hollow One" in hollow_one_body
    assert (
        "The eastern coast of Xhorhas, known to the Kryn as Blightshore, is a land scarred by evil magic."
        in hollow_one_body
    )
    assert "Supernatural Gift: Hollow One" in hollow_one_body
    assert "Chapter Navigation" in hollow_one_body
    assert 'href="#supernatural-gift-hollow-one"' in hollow_one_body
    assert 'id="supernatural-gift-hollow-one"' in hollow_one_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "Chapter 4" in detail_body
    assert "Character Options" in detail_body
    assert "Dunamis and Dunamancy" in detail_body
    assert (
        "Dunamis studies possibility, probability, and the unseen force that can bend time and gravity."
        in detail_body
    )
    assert "Beyond the Kryn Dynasty" in detail_body
    assert "Dunamis as a Martial Focus" in detail_body
    assert "Chapter Navigation" in detail_body
    assert 'href="#beyond-the-kryn-dynasty"' in detail_body
    assert 'id="beyond-the-kryn-dynasty"' in detail_body
    assert 'href="#dunamis-as-a-martial-focus"' in detail_body
    assert 'id="dunamis-as-a-martial-focus"' in detail_body


def test_egw_character_option_wrapper_pages_surface_related_imported_entities(
    client, sign_in, users, app, tmp_path
):
    data_root = build_egw_character_option_wrapper_data_root(
        tmp_path / "dnd5e-source-egw-character-option-wrappers"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source(
            "EGW",
            entry_types=["background", "book", "race", "spell", "subclass", "subclassfeature"],
        )

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "EGW",
                entry_type="book",
                limit=None,
            )
        }
        egw_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("background", "race", "spell", "subclass")
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type=entry_type, limit=None)
        }

    assert result.imported_by_type == {
        "background": 3,
        "book": 12,
        "race": 5,
        "spell": 3,
        "subclass": 3,
        "subclassfeature": 6,
    }
    assert list(book_entries) == [
        "Elves",
        "Halflings",
        "Dragonborn",
        "Orcs and Half-Orcs",
        "Hollow One",
        "Dunamis and Dunamancy",
        "Fighter",
        "Wizard",
        "Dunamancy Spells",
        "Spell Descriptions",
        "Heroic Chronicle",
        "Backgrounds",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])
    category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    elves_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Elves'].slug}")
    fighter_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Fighter'].slug}")
    spells_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamancy Spells'].slug}")
    spell_descriptions_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spell Descriptions'].slug}"
    )
    backgrounds_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Backgrounds'].slug}")

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 12 book chapters available to you in this source." in category_body
    assert category_body.index("Elves") < category_body.index("Halflings")
    assert category_body.index("Halflings") < category_body.index("Dragonborn")
    assert category_body.index("Dragonborn") < category_body.index("Orcs and Half-Orcs")
    assert category_body.index("Orcs and Half-Orcs") < category_body.index("Hollow One")
    assert category_body.index("Hollow One") < category_body.index("Dunamancy Spells")
    assert category_body.index("Dunamancy Spells") < category_body.index("Backgrounds")

    assert elves_response.status_code == 200
    elves_body = elves_response.get_data(as_text=True)
    assert "Related Races" in elves_body
    assert f'href="/campaigns/linden-pass/systems/entries/{egw_entries[("race", "Pallid Elf")].slug}"' in elves_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert "Subclasses:" in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{egw_entries[("subclass", "Echo Knight")].slug}"' in fighter_body

    assert spells_response.status_code == 200
    spells_body = spells_response.get_data(as_text=True)
    assert "Spells:" in spells_body
    assert f'href="/campaigns/linden-pass/systems/entries/{egw_entries[("spell", "Dark Star")].slug}"' in spells_body

    assert spell_descriptions_response.status_code == 200
    spell_descriptions_body = spell_descriptions_response.get_data(as_text=True)
    assert "Spells:" in spell_descriptions_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{egw_entries[("spell", "Temporal Shunt")].slug}"'
        in spell_descriptions_body
    )

    assert backgrounds_response.status_code == 200
    backgrounds_body = backgrounds_response.get_data(as_text=True)
    assert "Backgrounds:" in backgrounds_body
    assert f'href="/campaigns/linden-pass/systems/entries/{egw_entries[("background", "Grinner")].slug}"' in backgrounds_body


def test_egw_entry_pages_surface_source_chapter_context_links(client, sign_in, users, app, tmp_path):
    data_root = build_egw_character_option_wrapper_data_root(
        tmp_path / "dnd5e-source-egw-entry-source-context"
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

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "EGW",
                entry_type="book",
                limit=None,
            )
        }
        egw_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("background", "race", "spell", "subclass", "subclassfeature")
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type=entry_type, limit=None)
        }

    sign_in(users["party"]["email"], users["party"]["password"])

    expectations = {
        ("race", "Pallid Elf"): ("Elves",),
        ("race", "Lotusden Halfling"): ("Halflings",),
        ("race", "Draconblood Dragonborn"): ("Dragonborn",),
        ("race", "Orc"): ("Orcs and Half-Orcs",),
        ("subclass", "Echo Knight"): ("Fighter",),
        ("subclassfeature", "Chronal Shift"): ("Wizard",),
        ("spell", "Dark Star"): ("Dunamancy Spells", "Spell Descriptions"),
        ("background", "Grinner"): ("Backgrounds",),
    }

    for entry_key, wrapper_titles in expectations.items():
        response = client.get(f"/campaigns/linden-pass/systems/entries/{egw_entries[entry_key].slug}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Source Chapter Context" in body
        for wrapper_title in wrapper_titles:
            assert wrapper_title in body
            assert (
                f'href="/campaigns/linden-pass/systems/entries/{book_entries[wrapper_title].slug}"'
                in body
            )


def test_egw_treasure_progression_pages_are_imported_and_item_pages_link_back(
    client, sign_in, users, app, tmp_path
):
    data_root = build_egw_treasure_progression_data_root(
        tmp_path / "dnd5e-source-egw-treasure-progression"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("EGW", entry_types=["book", "item"])

        service = app.extensions["systems_service"]
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
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "EGW",
                entry_type="book",
                limit=None,
            )
        }
        item_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="item", limit=None)
        }

    assert result.imported_by_type == {"book": 2, "item": 3}
    assert list(book_entries) == [
        "Advancement of a Vestige of Divergence",
        "Betrayer Artifact Properties",
    ]

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    vestige_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Advancement of a Vestige of Divergence'].slug}"
    )
    betrayer_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Betrayer Artifact Properties'].slug}"
    )
    visor_response = client.get(
        f'/campaigns/linden-pass/systems/entries/{item_entries["Danoth\'s Visor (Dormant)"].slug}'
    )
    grovelthrash_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{item_entries['Grovelthrash (Dormant)'].slug}"
    )
    staff_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{item_entries['Staff of Dunamancy'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert (
        source_body.index("Advancement of a Vestige of Divergence")
        < source_body.index("Betrayer Artifact Properties")
    )

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 2 book chapters available to you in this source." in category_body
    assert (
        category_body.index("Advancement of a Vestige of Divergence")
        < category_body.index("Betrayer Artifact Properties")
    )

    assert vestige_response.status_code == 200
    vestige_body = vestige_response.get_data(as_text=True)
    assert "Chapter 6" in vestige_body
    assert "Wildemount Treasures" in vestige_body
    assert "Advancement of a Vestige of Divergence" in vestige_body
    assert (
        "Typically, the advancement of a Vestige of Divergence echoes its wielder&#x27;s own journey of self-discovery."
        in vestige_body
    )

    assert betrayer_response.status_code == 200
    betrayer_body = betrayer_response.get_data(as_text=True)
    assert "Chapter 6" in betrayer_body
    assert "Wildemount Treasures" in betrayer_body
    assert "Betrayer Artifact Properties" in betrayer_body
    assert (
        "The Arms of the Betrayers advance in power in the same manner as the Vestiges of Divergence."
        in betrayer_body
    )

    assert visor_response.status_code == 200
    visor_body = visor_response.get_data(as_text=True)
    assert "Source Chapter Context" in visor_body
    assert "Advancement of a Vestige of Divergence" in visor_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{book_entries["Advancement of a Vestige of Divergence"].slug}"'
        in visor_body
    )

    assert grovelthrash_response.status_code == 200
    grovelthrash_body = grovelthrash_response.get_data(as_text=True)
    assert "Source Chapter Context" in grovelthrash_body
    assert "Betrayer Artifact Properties" in grovelthrash_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{book_entries["Betrayer Artifact Properties"].slug}"'
        in grovelthrash_body
    )

    assert staff_response.status_code == 200
    staff_body = staff_response.get_data(as_text=True)
    assert "Source Chapter Context" not in staff_body


def test_dmg_book_chapters_surface_related_imported_entities(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["action", "book", "disease", "item", "variantrule"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "DMG",
                entry_type="book",
                limit=None,
            )
        }
        dmg_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "disease", "item", "variantrule")
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type=entry_type, limit=None)
        }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    treasure_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Treasure'].slug}")
    downtime_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Downtime Activities'].slug}")
    running_the_game_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Running the Game'].slug}")

    assert treasure_response.status_code == 200
    treasure_body = treasure_response.get_data(as_text=True)
    assert "Equipment:" in treasure_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("item", "Potion of Healing")].slug}"' in treasure_body

    assert downtime_response.status_code == 200
    downtime_body = downtime_response.get_data(as_text=True)
    assert "Variant Rules:" in downtime_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{dmg_entries[("variantrule", "Downtime Activity: Building a Stronghold")].slug}"'
        in downtime_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/'
        f'{dmg_entries[("variantrule", "Downtime Activity: Carousing")].slug}"'
        in downtime_body
    )

    assert running_the_game_response.status_code == 200
    running_the_game_body = running_the_game_response.get_data(as_text=True)
    assert "Diseases:" in running_the_game_body
    assert "Actions:" in running_the_game_body
    assert "Variant Rules:" in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("disease", "Cackle Fever")].slug}"' in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("action", "Overrun")].slug}"' in running_the_game_body
    assert f'href="/campaigns/linden-pass/systems/entries/{dmg_entries[("variantrule", "Chases")].slug}"' in running_the_game_body


def test_phb_book_chapters_surface_related_imported_entities(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-entity-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "PHB",
            entry_types=["action", "book", "condition", "feat", "item", "sense", "skill", "spell", "variantrule"],
        )

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "PHB",
                entry_type="book",
                limit=None,
            )
        }
        phb_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("action", "condition", "feat", "item", "sense", "skill", "spell", "variantrule")
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type=entry_type, limit=None)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    step_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Step-by-Step Characters'].slug}")
    equipment_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Equipment'].slug}")
    customization_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Customization Options'].slug}"
    )
    ability_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Using Ability Scores'].slug}")
    adventuring_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Adventuring'].slug}")
    combat_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Combat'].slug}")
    spellcasting_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Spellcasting'].slug}")

    assert step_response.status_code == 200
    step_body = step_response.get_data(as_text=True)
    assert "Equipment:" in step_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Chain Mail")].slug}"' in step_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Longsword")].slug}"' in step_body

    assert equipment_response.status_code == 200
    equipment_body = equipment_response.get_data(as_text=True)
    assert "Equipment:" in equipment_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Chain Mail")].slug}"' in equipment_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("item", "Longsword")].slug}"' in equipment_body

    assert customization_response.status_code == 200
    customization_body = customization_response.get_data(as_text=True)
    assert "Variant Rules:" in customization_body
    assert "Feats:" in customization_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("variantrule", "Multiclassing")].slug}"'
        in customization_body
    )
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("feat", "Alert")].slug}"' in customization_body

    assert ability_response.status_code == 200
    ability_body = ability_response.get_data(as_text=True)
    assert "Skills:" in ability_body
    assert "Actions:" in ability_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("skill", "Athletics")].slug}"' in ability_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Help")].slug}"' in ability_body

    assert adventuring_response.status_code == 200
    adventuring_body = adventuring_response.get_data(as_text=True)
    assert "Conditions:" in adventuring_body
    assert "Senses:" in adventuring_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("condition", "Blinded")].slug}"' in adventuring_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("sense", "Darkvision")].slug}"' in adventuring_body

    assert combat_response.status_code == 200
    combat_body = combat_response.get_data(as_text=True)
    assert "Actions:" in combat_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("action", "Help")].slug}"' in combat_body

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert "Spells:" in spellcasting_body
    assert f'href="/campaigns/linden-pass/systems/entries/{phb_entries[("spell", "Mage Hand")].slug}"' in spellcasting_body


def test_xge_book_entries_are_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_xge_book_data_root(tmp_path / "dnd5e-source-xge-book-entries")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["book"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="XGE",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "XGE",
                entry_type="book",
                limit=None,
            )
        }

    assert list(book_entries) == list(XGE_RULES_REFERENCE_TEST_TITLES)

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    falling_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Falling'].slug}")
    tool_proficiencies_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Tool Proficiencies'].slug}"
    )
    spellcasting_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spellcasting'].slug}"
    )
    encounter_building_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Encounter Building'].slug}"
    )
    random_encounters_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Random Encounters: A World of Possibilities'].slug}"
    )
    traps_revisited_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Traps Revisited'].slug}"
    )
    downtime_revisited_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Downtime Revisited'].slug}"
    )
    awarding_magic_items_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Awarding Magic Items'].slug}"
    )
    shared_campaigns_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Shared Campaigns'].slug}"
    )
    variant_rules_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Variant Rules'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    source_indexes = [source_body.index(title) for title in XGE_RULES_REFERENCE_TEST_TITLES]
    assert source_indexes == sorted(source_indexes)

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    category_indexes = [category_body.index(title) for title in XGE_RULES_REFERENCE_TEST_TITLES]
    assert category_indexes == sorted(category_indexes)

    assert falling_response.status_code == 200
    falling_body = falling_response.get_data(as_text=True)
    assert "Chapter 2" in falling_body
    assert "Dungeon Master&#39;s Tools" in falling_body
    assert "Rate of Falling" in falling_body
    assert "Flying Creatures and Falling" in falling_body
    assert 'href="#rate-of-falling"' in falling_body
    assert 'id="flying-creatures-and-falling"' in falling_body

    assert tool_proficiencies_response.status_code == 200
    tool_proficiencies_body = tool_proficiencies_response.get_data(as_text=True)
    assert "Chapter 2" in tool_proficiencies_body
    assert "Dungeon Master&#39;s Tools" in tool_proficiencies_body
    assert "Tools and Skills Together" in tool_proficiencies_body
    assert "Tool Descriptions" in tool_proficiencies_body
    assert 'href="#tools-and-skills-together"' in tool_proficiencies_body
    assert 'id="tool-descriptions"' in tool_proficiencies_body

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert "Chapter 2" in spellcasting_body
    assert "Dungeon Master&#39;s Tools" in spellcasting_body
    assert "Perceiving a Caster at Work" in spellcasting_body
    assert "Invalid Spell Targets" in spellcasting_body
    assert "Areas of Effect on a Grid" in spellcasting_body
    assert 'href="#perceiving-a-caster-at-work"' in spellcasting_body
    assert 'href="#areas-of-effect-on-a-grid"' in spellcasting_body
    assert 'id="invalid-spell-targets"' in spellcasting_body

    assert encounter_building_response.status_code == 200
    encounter_building_body = encounter_building_response.get_data(as_text=True)
    assert "Chapter 2" in encounter_building_body
    assert "Dungeon Master&#39;s Tools" in encounter_building_body
    assert "Step 1: Assess the Characters" in encounter_building_body
    assert "Step 5: Add Flavor" in encounter_building_body
    assert "Quick Matchups" in encounter_building_body
    assert 'href="#step-1-assess-the-characters"' in encounter_building_body
    assert (
        'href="#step-5-add-flavor--terrain-and-traps"' in encounter_building_body
    )
    assert (
        'id="step-3-determine-numbers-and-challenge-ratings--weak-monsters-and-high-level-characters"'
        in encounter_building_body
    )

    assert random_encounters_response.status_code == 200
    random_encounters_body = random_encounters_response.get_data(as_text=True)
    assert "Chapter 2" in random_encounters_body
    assert "Dungeon Master&#39;s Tools" in random_encounters_body
    assert "Flight, or Fight, or..?" in random_encounters_body
    assert 'href="#flight-or-fight-or"' in random_encounters_body
    assert 'id="flight-or-fight-or"' in random_encounters_body

    assert traps_revisited_response.status_code == 200
    traps_revisited_body = traps_revisited_response.get_data(as_text=True)
    assert "Chapter 2" in traps_revisited_body
    assert "Dungeon Master&#39;s Tools" in traps_revisited_body
    assert "Simple Traps" in traps_revisited_body
    assert "Complex Traps" in traps_revisited_body
    assert "Designing Complex Traps" in traps_revisited_body
    assert 'href="#simple-traps"' in traps_revisited_body
    assert 'href="#simple-traps--elements-of-a-simple-trap"' in traps_revisited_body
    assert 'id="complex-traps--running-a-complex-trap"' in traps_revisited_body

    assert downtime_revisited_response.status_code == 200
    downtime_revisited_body = downtime_revisited_response.get_data(as_text=True)
    assert "Chapter 2" in downtime_revisited_body
    assert "Dungeon Master&#39;s Tools" in downtime_revisited_body
    assert "Rivals" in downtime_revisited_body
    assert "Downtime Activities" in downtime_revisited_body
    assert "Example Downtime Activities" in downtime_revisited_body
    assert 'href="#rivals"' in downtime_revisited_body
    assert 'href="#downtime-activities"' in downtime_revisited_body
    assert 'id="example-downtime-activities"' in downtime_revisited_body

    assert awarding_magic_items_response.status_code == 200
    awarding_magic_items_body = awarding_magic_items_response.get_data(as_text=True)
    assert "Chapter 2" in awarding_magic_items_body
    assert "Dungeon Master&#39;s Tools" in awarding_magic_items_body
    assert "Magic item awards can be paced by tone, treasure, and campaign expectations." in awarding_magic_items_body

    assert shared_campaigns_response.status_code == 200
    shared_campaigns_body = shared_campaigns_response.get_data(as_text=True)
    assert "Appendix A" in shared_campaigns_body
    assert "Code of Conduct" in shared_campaigns_body
    assert "Designing Adventures" in shared_campaigns_body
    assert "Character Creation" in shared_campaigns_body
    assert "Variant Rules" in shared_campaigns_body
    assert 'href="#code-of-conduct"' in shared_campaigns_body
    assert 'href="#character-creation"' in shared_campaigns_body
    assert 'id="variant-rules"' in shared_campaigns_body

    assert variant_rules_response.status_code == 200
    variant_rules_body = variant_rules_response.get_data(as_text=True)
    assert "Appendix A" in variant_rules_body
    assert "Shared Campaigns" in variant_rules_body
    assert "bounded rules list" in variant_rules_body


def test_xge_book_chapters_surface_related_variant_rules_and_respect_entry_visibility(
    client, sign_in, users, app, tmp_path
):
    data_root = build_xge_book_related_entities_data_root(
        tmp_path / "dnd5e-source-xge-book-entity-links"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["book", "variantrule"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="XGE",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="book", limit=20)
        }
        xge_rules = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="variantrule", limit=20)
        }
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug="DND-5E",
            entry_key=xge_rules["Identifying a Spell"].entry_key,
            visibility_override="dm",
            is_enabled_override=None,
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    sleep_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries['Sleep'].slug}")
    spellcasting_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spellcasting'].slug}"
    )

    assert sleep_response.status_code == 200
    sleep_body = sleep_response.get_data(as_text=True)
    assert "Variant Rules:" in sleep_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{xge_rules["Waking Someone"].slug}"'
        in sleep_body
    )

    assert spellcasting_response.status_code == 200
    spellcasting_body = spellcasting_response.get_data(as_text=True)
    assert "Identifying a Spell" in spellcasting_body
    assert "Variant Rules:" not in spellcasting_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{xge_rules["Identifying a Spell"].slug}"'
        not in spellcasting_body
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_spellcasting_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Spellcasting'].slug}"
    )

    assert dm_spellcasting_response.status_code == 200
    dm_spellcasting_body = dm_spellcasting_response.get_data(as_text=True)
    assert "Variant Rules:" in dm_spellcasting_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{xge_rules["Identifying a Spell"].slug}"'
        in dm_spellcasting_body
    )


def test_xge_book_entries_follow_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_xge_book_data_root(
        tmp_path / "dnd5e-source-xge-book-entries-policy"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="XGE",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Shared Campaigns'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/XGE")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/XGE/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Shared Campaigns'].slug}"
    )

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    assert "Shared Campaigns" in dm_category_response.get_data(as_text=True)
    assert dm_entry_response.status_code == 200
    dm_body = dm_entry_response.get_data(as_text=True)
    assert "Appendix A" in dm_body
    assert "Code of Conduct" in dm_body
    assert "Character Creation" in dm_body


def test_xge_book_slice_includes_shared_campaigns_wrapper_and_excludes_remaining_pending_section_pages(
    app, tmp_path
):
    data_root = build_xge_book_data_root(
        tmp_path / "dnd5e-source-xge-book-boundary"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("XGE", entry_types=["book"])
        store = app.extensions["systems_store"]
        book_entries = list(
            store.list_entries_for_source("DND-5E", "XGE", entry_type="book", limit=20)
        )

    assert result.imported_count == len(XGE_RULES_REFERENCE_TEST_TITLES)
    assert result.imported_by_type == {"book": len(XGE_RULES_REFERENCE_TEST_TITLES)}
    book_titles = {entry.title for entry in book_entries}
    assert book_titles == set(XGE_RULES_REFERENCE_TEST_TITLES)
    assert "Shared Campaigns" in book_titles


def test_tce_book_entries_are_imported_for_player_browse(
    client, sign_in, users, app, tmp_path
):
    data_root = build_tce_book_data_root(tmp_path / "dnd5e-source-tce-book-entries")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("TCE", entry_types=["book", "variantrule"])

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="TCE",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "TCE",
                entry_type="book",
                limit=None,
            )
        }
        tce_rules = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "TCE",
                entry_type="variantrule",
                limit=None,
            )
        }

    assert list(book_entries) == list(TCE_RULES_REFERENCE_TEST_TITLES)
    assert "Customizing Your Origin" in tce_rules

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/TCE")
    category_response = client.get("/campaigns/linden-pass/systems/sources/TCE/types/book")
    ten_rules_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Ten Rules to Remember'].slug}"
    )
    customizing_origin_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Customizing Your Origin'].slug}"
    )
    changing_skill_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Changing a Skill'].slug}"
    )
    changing_subclass_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Changing Your Subclass'].slug}"
    )
    group_patrons_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Group Patrons'].slug}"
    )
    personalizing_spells_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Personalizing Spells'].slug}"
    )
    magic_tattoos_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Magic Tattoos'].slug}"
    )
    sidekicks_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Sidekicks'].slug}"
    )
    parleying_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Parleying with Monsters'].slug}"
    )
    environmental_hazards_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Environmental Hazards'].slug}"
    )
    puzzles_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Puzzles'].slug}"
    )
    session_zero_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Session Zero'].slug}"
    )
    artificer_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Artificer'].slug}"
    )
    fighter_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Fighter'].slug}"
    )

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" in source_body
    assert "Ten Rules to Remember" in source_body
    assert "Customizing Your Origin" in source_body
    assert "Changing a Skill" in source_body
    assert "Changing Your Subclass" in source_body
    assert "Group Patrons" in source_body
    assert "Personalizing Spells" in source_body
    assert "Magic Tattoos" in source_body
    assert "Session Zero" in source_body
    assert "Sidekicks" in source_body
    assert "Parleying with Monsters" in source_body
    assert "Environmental Hazards" in source_body
    assert "Puzzles" in source_body
    assert "Artificer" in source_body
    assert "Fighter" in source_body
    assert "Wizard" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert (
        f"Showing all {len(TCE_RULES_REFERENCE_TEST_TITLES)} book chapters available to you in this source."
        in category_body
    )
    assert "Ten Rules to Remember" in category_body
    assert "Customizing Your Origin" in category_body
    assert "Changing a Skill" in category_body
    assert "Changing Your Subclass" in category_body
    assert "Group Patrons" in category_body
    assert "Personalizing Spells" in category_body
    assert "Magic Tattoos" in category_body
    assert "Session Zero" in category_body
    assert "Sidekicks" in category_body
    assert "Parleying with Monsters" in category_body
    assert "Environmental Hazards" in category_body
    assert "Puzzles" in category_body
    assert "Artificer" in category_body
    assert "Fighter" in category_body
    assert "Wizard" in category_body

    assert ten_rules_response.status_code == 200
    ten_rules_body = ten_rules_response.get_data(as_text=True)
    assert "Using This Book" in ten_rules_body
    assert "Ten Rules to Remember" in ten_rules_body
    assert "1. The DM Adjudicates the Rules" in ten_rules_body
    assert "10. Have Fun" in ten_rules_body
    assert 'href="#1-the-dm-adjudicates-the-rules"' in ten_rules_body
    assert 'href="#10-have-fun"' in ten_rules_body
    assert 'id="3-advantage-and-disadvantage"' in ten_rules_body
    assert "The rules help, but the table comes first." in ten_rules_body

    assert customizing_origin_response.status_code == 200
    customizing_origin_body = customizing_origin_response.get_data(as_text=True)
    assert "Character Options" in customizing_origin_body
    assert "Customizing Your Origin" in customizing_origin_body
    assert "See the Customizing Your Origin entry." in customizing_origin_body

    assert changing_skill_response.status_code == 200
    changing_skill_body = changing_skill_response.get_data(as_text=True)
    assert "Character Options" in changing_skill_body
    assert "Changing a Skill" in changing_skill_body
    assert (
        "Swap an underused skill proficiency for another one your class offered at 1st level."
        in changing_skill_body
    )

    assert changing_subclass_response.status_code == 200
    changing_subclass_body = changing_subclass_response.get_data(as_text=True)
    assert "Character Options" in changing_subclass_body
    assert "Changing Your Subclass" in changing_subclass_body
    assert "replace your subclass when you gain a new subclass feature." in changing_subclass_body

    assert group_patrons_response.status_code == 200
    group_patrons_body = group_patrons_response.get_data(as_text=True)
    assert "Chapter 2" in group_patrons_body
    assert "Group Patrons" in group_patrons_body
    assert "How Patrons Work" in group_patrons_body
    assert "Example Patrons" in group_patrons_body
    assert "Being Your Own Patron" in group_patrons_body
    assert 'href="#how-patrons-work"' in group_patrons_body
    assert 'id="being-your-own-patron"' in group_patrons_body

    assert personalizing_spells_response.status_code == 200
    personalizing_spells_body = personalizing_spells_response.get_data(as_text=True)
    assert "Chapter 3" in personalizing_spells_body
    assert "Magical Miscellany" in personalizing_spells_body
    assert "Personalizing Spells" in personalizing_spells_body
    assert "cosmetic effects of their magic" in personalizing_spells_body
    assert "Magic Themes" in personalizing_spells_body
    assert "Book pages, ink, and rustling library scents" in personalizing_spells_body

    assert magic_tattoos_response.status_code == 200
    magic_tattoos_body = magic_tattoos_response.get_data(as_text=True)
    assert "Chapter 3" in magic_tattoos_body
    assert "Magical Miscellany" in magic_tattoos_body
    assert "Magic Tattoos" in magic_tattoos_body
    assert "brand, scarification, a birthmark" in magic_tattoos_body
    assert "Magic Tattoo Coverage" in magic_tattoos_body
    assert "One hand or foot or a quarter of a limb" in magic_tattoos_body

    assert session_zero_response.status_code == 200
    session_zero_body = session_zero_response.get_data(as_text=True)
    assert "Chapter 4" in session_zero_body
    assert "Dungeon Master&#x27;s Tools" in session_zero_body
    assert "Session Zero" in session_zero_body
    assert "Character and Party Creation" in session_zero_body
    assert "Party Formation" in session_zero_body
    assert "Social Contract" in session_zero_body
    assert "Hard and Soft Limits" in session_zero_body
    assert "Game Customization" in session_zero_body
    assert "House Rules" in session_zero_body
    assert "Party Origin" in session_zero_body
    assert 'href="#character-and-party-creation"' in session_zero_body
    assert 'href="#social-contract--hard-and-soft-limits"' in session_zero_body
    assert 'id="game-customization--house-rules"' in session_zero_body

    assert sidekicks_response.status_code == 200
    sidekicks_body = sidekicks_response.get_data(as_text=True)
    assert "Chapter 4" in sidekicks_body
    assert "Dungeon Master&#x27;s Tools" in sidekicks_body
    assert "Sidekicks" in sidekicks_body
    assert "Creating a Sidekick" in sidekicks_body
    assert "Gaining a Sidekick Class" in sidekicks_body
    assert "Expert, Spellcaster, or Warrior" in sidekicks_body
    assert 'href="#creating-a-sidekick"' in sidekicks_body
    assert 'id="gaining-a-sidekick-class"' in sidekicks_body

    assert parleying_response.status_code == 200
    parleying_body = parleying_response.get_data(as_text=True)
    assert "Chapter 4" in parleying_body
    assert "Dungeon Master&#x27;s Tools" in parleying_body
    assert "Parleying with Monsters" in parleying_body
    assert "Monster Research" in parleying_body
    assert "Monsters&#x27; Desires" in parleying_body
    assert "Fresh meat" in parleying_body
    assert 'href="#monster-research"' in parleying_body
    assert 'id="monsters-desires"' in parleying_body

    assert environmental_hazards_response.status_code == 200
    environmental_hazards_body = environmental_hazards_response.get_data(as_text=True)
    assert "Chapter 4" in environmental_hazards_body
    assert "Dungeon Master&#x27;s Tools" in environmental_hazards_body
    assert "Environmental Hazards" in environmental_hazards_body
    assert "Supernatural Regions" in environmental_hazards_body
    assert "Magical Phenomena" in environmental_hazards_body
    assert "Natural Hazards" in environmental_hazards_body
    assert "Blessed Radiance" in environmental_hazards_body
    assert "Eldritch Storms" in environmental_hazards_body
    assert "Spell Equivalents of Natural Hazards" in environmental_hazards_body
    assert 'href="#supernatural-regions"' in environmental_hazards_body
    assert 'href="#magical-phenomena"' in environmental_hazards_body
    assert 'id="natural-hazards"' in environmental_hazards_body

    assert puzzles_response.status_code == 200
    puzzles_body = puzzles_response.get_data(as_text=True)
    assert "Chapter 4" in puzzles_body
    assert "Dungeon Master&#x27;s Tools" in puzzles_body
    assert "Puzzles" in puzzles_body
    assert "Why Use Puzzles?" in puzzles_body
    assert "Puzzle Elements" in puzzles_body
    assert "Creature Paintings" in puzzles_body
    assert "Reckless Steps" in puzzles_body
    assert 'href="#why-use-puzzles"' in puzzles_body
    assert 'id="creature-paintings"' in puzzles_body

    assert artificer_response.status_code == 200
    artificer_body = artificer_response.get_data(as_text=True)
    assert "Chapter 1" in artificer_body
    assert "Character Options" in artificer_body
    assert "Artificers in Many Worlds" in artificer_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert "Chapter 1" in fighter_body
    assert "Character Options" in fighter_body
    assert "Battle Master Builds" in fighter_body


def test_tce_book_entries_follow_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_tce_book_data_root(
        tmp_path / "dnd5e-source-tce-book-entries-policy"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("TCE", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="TCE",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="book", limit=None)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/TCE")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/TCE/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Magic Tattoos'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/TCE")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/TCE/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Puzzles'].slug}"
    )

    assert dm_source_response.status_code == 200
    assert "Book Chapters" in dm_source_response.get_data(as_text=True)
    assert dm_category_response.status_code == 200
    dm_category_body = dm_category_response.get_data(as_text=True)
    assert "Ten Rules to Remember" in dm_category_body
    assert "Customizing Your Origin" in dm_category_body
    assert "Changing a Skill" in dm_category_body
    assert "Changing Your Subclass" in dm_category_body
    assert "Group Patrons" in dm_category_body
    assert "Personalizing Spells" in dm_category_body
    assert "Magic Tattoos" in dm_category_body
    assert "Session Zero" in dm_category_body
    assert "Sidekicks" in dm_category_body
    assert "Parleying with Monsters" in dm_category_body
    assert "Environmental Hazards" in dm_category_body
    assert "Puzzles" in dm_category_body
    assert dm_entry_response.status_code == 200
    dm_entry_body = dm_entry_response.get_data(as_text=True)
    assert "Dungeon Master&#x27;s Tools" in dm_entry_body
    assert "Puzzles" in dm_entry_body


def test_tce_book_slice_includes_group_patrons_miscellany_and_dm_tool_wrappers_for_now(
    app, tmp_path
):
    data_root = build_tce_book_data_root(tmp_path / "dnd5e-source-tce-book-boundary")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("TCE", entry_types=["book"])
        store = app.extensions["systems_store"]
        book_entries = list(
            store.list_entries_for_source("DND-5E", "TCE", entry_type="book", limit=None)
        )

    assert result.imported_count == len(TCE_RULES_REFERENCE_TEST_TITLES)
    assert result.imported_by_type == {"book": len(TCE_RULES_REFERENCE_TEST_TITLES)}
    assert [entry.title for entry in book_entries] == list(TCE_RULES_REFERENCE_TEST_TITLES)


def test_tce_class_wrappers_surface_related_imported_entities(
    client, sign_in, users, app, tmp_path
):
    data_root = build_tce_book_data_root(tmp_path / "dnd5e-source-tce-class-wrapper-links")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "TCE",
            entry_types=["book", "class", "classfeature", "subclass", "subclassfeature", "optionalfeature"],
        )

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="TCE",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "TCE",
                entry_type="book",
                limit=None,
            )
        }
        tce_entries = {
            (entry.entry_type, entry.title): entry
            for entry_type in ("class", "classfeature", "subclass", "subclassfeature", "optionalfeature")
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type=entry_type, limit=None)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    artificer_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Artificer'].slug}"
    )
    fighter_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Fighter'].slug}"
    )
    ranger_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Ranger'].slug}"
    )

    assert artificer_response.status_code == 200
    artificer_body = artificer_response.get_data(as_text=True)
    assert "Classes:" in artificer_body
    assert "Class Features:" in artificer_body
    assert "Subclasses:" in artificer_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("class", "Artificer")].slug}"'
        in artificer_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("classfeature", "Infuse Item")].slug}"'
        in artificer_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("subclass", "Alchemist")].slug}"'
        in artificer_body
    )

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert "Class Features:" in fighter_body
    assert "Optional Features:" in fighter_body
    assert "Subclasses:" in fighter_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("classfeature", "Martial Versatility")].slug}"'
        in fighter_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("optionalfeature", "Blind Fighting")].slug}"'
        in fighter_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("optionalfeature", "Superior Technique")].slug}"'
        in fighter_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("subclass", "Psi Warrior")].slug}"'
        in fighter_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("subclass", "Rune Knight")].slug}"'
        in fighter_body
    )

    assert ranger_response.status_code == 200
    ranger_body = ranger_response.get_data(as_text=True)
    assert "Class Features:" in ranger_body
    assert "Optional Features:" in ranger_body
    assert "Subclasses:" in ranger_body
    assert "Subclass Features:" in ranger_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("classfeature", "Deft Explorer")].slug}"'
        in ranger_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("optionalfeature", "Druidic Warrior")].slug}"'
        in ranger_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("subclass", "Fey Wanderer")].slug}"'
        in ranger_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{tce_entries[("subclassfeature", "Primal Companion")].slug}"'
        in ranger_body
    )


def test_book_pages_surface_section_targeted_active_campaign_overlays(
    app, client, sign_in, users, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-campaign-overlays")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

        store = app.extensions["systems_store"]
        spellcasting_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="book", limit=20)
            if entry.title == "Spellcasting"
        )

        campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
        page_path = campaigns_dir / "linden-pass" / "content" / "mechanics" / "component-casting-adjustment.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            (
                "---\n"
                "title: Component Casting Adjustment\n"
                "section: Mechanics\n"
                "type: mechanic\n"
                "subsection: Class Modifications\n"
                "character_progression:\n"
                "  kind: class\n"
                "  class_name: Wizard\n"
                "  level: 1\n"
                "  character_option:\n"
                "    name: Component Casting Adjustment\n"
                "    activation_type: special\n"
                "    base_rule_refs:\n"
                f"      - slug: {spellcasting_entry.slug}\n"
                "        entry_type: book\n"
                "        source_id: PHB\n"
                "        anchor: casting-a-spell--components\n"
                "        section_title: Components\n"
                "---\n\n"
                "Wizards in this campaign can substitute a bonded focus for listed common components.\n"
            ),
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    book_response = client.get(f"/campaigns/linden-pass/systems/entries/{spellcasting_entry.slug}")

    assert book_response.status_code == 200
    book_body = book_response.get_data(as_text=True)
    assert "Active Campaign Overlays" in book_body
    assert "Component Casting Adjustment" in book_body
    assert "Applies To:</strong> Components" in book_body
    assert "Wizards in this campaign can substitute a bonded focus for listed common components." in book_body
    assert '/campaigns/linden-pass/pages/mechanics/component-casting-adjustment' in book_body
