from __future__ import annotations

from tests.helpers.systems_importer_test_helpers import *

def test_embedded_feature_cards_strip_inline_import_tags(app):
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        now = datetime.now(timezone.utc)
        entry = SystemsEntryRecord(
            id=1,
            library_slug="DND-5E",
            source_id="TCE",
            entry_key="dnd-5e|optionalfeature|tce|superior-technique",
            entry_type="optionalfeature",
            slug="superior-technique",
            title="Superior Technique",
            source_page="42",
            source_path="data/optionalfeatures.json",
            search_text="",
            player_safe_default=True,
            dm_heavy=False,
            metadata={"feature_type": ["FS:F"]},
            body={
                "entries": [
                    "You learn one {@filter maneuver|optionalfeatures|feature type=MV:B} of your choice from among those available to the {@class fighter|phb|Battle Master|Battle Master|phb|2-0} archetype.",
                    "You gain one superiority die, which is a {@dice d6}.",
                    "At the start of each of your turns, you can deal {@damage 1d4} bludgeoning damage to one creature {@condition grappled} by you while carrying a {@item shield|phb}.",
                ]
            },
            rendered_html="",
            created_at=now,
            updated_at=now,
        )

        embedded_card = systems_service._build_embedded_feature_card(
            "linden-pass",
            entry,
            optionalfeature_lookup={},
        )

    body_html = embedded_card["body_html"]
    assert "{@" not in body_html
    assert "maneuver of your choice" in body_html
    assert "fighter archetype" in body_html
    assert "a d6" in body_html
    assert "1d4 bludgeoning damage" in body_html
    assert "grappled" in body_html
    assert "shield" in body_html


def test_importer_renders_ability_formula_nodes_readably(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        rendered_html = importer._render_content_block(
            [
                {"attributes": ["cha"], "name": "Spell", "type": "abilityDc"},
                {"attributes": ["cha"], "name": "Spell", "type": "abilityAttackMod"},
            ],
            heading_level=3,
        )

    assert "Spell save DC:" in rendered_html
    assert "8 + your proficiency bonus + your Charisma modifier" in rendered_html
    assert "Spell attack modifier:" in rendered_html
    assert "your proficiency bonus + your Charisma modifier" in rendered_html
    assert "Spell.</strong>" not in rendered_html


def test_embedded_feature_cards_render_ability_formula_nodes_readably(app):
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        now = datetime.now(timezone.utc)
        entry = SystemsEntryRecord(
            id=2,
            library_slug="DND-5E",
            source_id="PHB",
            entry_key="dnd-5e|classfeature|phb|pact-magic|warlock|phb|1",
            entry_type="classfeature",
            slug="pact-magic-warlock-phb-1",
            title="Pact Magic",
            source_page="107",
            source_path="data/class/class-warlock.json",
            search_text="",
            player_safe_default=True,
            dm_heavy=False,
            metadata={"class_name": "Warlock", "class_source": "PHB", "level": 1},
            body={
                "entries": [
                    {
                        "name": "Spellcasting Ability",
                        "type": "entries",
                        "entries": [
                            "Charisma is your spellcasting ability for your warlock spells.",
                            {"attributes": ["cha"], "name": "Spell", "type": "abilityDc"},
                            {"attributes": ["cha"], "name": "Spell", "type": "abilityAttackMod"},
                        ],
                    }
                ]
            },
            rendered_html="",
            created_at=now,
            updated_at=now,
        )

        embedded_card = systems_service._build_embedded_feature_card(
            "linden-pass",
            entry,
            optionalfeature_lookup={},
        )

    body_html = embedded_card["body_html"]
    assert "Spell save DC:" in body_html
    assert "8 + your proficiency bonus + your Charisma modifier" in body_html
    assert "Spell attack modifier:" in body_html
    assert "your proficiency bonus + your Charisma modifier" in body_html
    assert "Spell.</strong>" not in body_html


def test_importer_imports_mechanics_only_and_strips_media_fields(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        phb_result = importer.import_source("PHB")
        vgm_result = importer.import_source("VGM", entry_types=["race"])
        egw_result = importer.import_source("EGW", entry_types=["race"])
        mm_result = importer.import_source("MM")

        assert phb_result.imported_count == 29
        assert phb_result.imported_by_type == {
            "action": 1,
            "background": 1,
            "class": 1,
            "classfeature": 1,
            "condition": 1,
            "feat": 1,
            "item": 4,
            "optionalfeature": 3,
            "race": 9,
            "sense": 1,
            "skill": 1,
            "spell": 1,
            "status": 1,
            "subclass": 1,
            "subclassfeature": 1,
            "variantrule": 1,
        }
        assert vgm_result.imported_count == 2
        assert vgm_result.imported_by_type == {"race": 2}
        assert egw_result.imported_count == 1
        assert egw_result.imported_by_type == {"race": 1}
        assert mm_result.imported_count == 1
        assert mm_result.imported_by_type == {"monster": 1}

        store = app.extensions["systems_store"]
        phb_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", limit=100)}
        vgm_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "VGM", limit=20)}
        egw_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "EGW", limit=20)}
        mm_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "MM", limit=50)}

        spell = phb_entries["Mage Hand"]
        assert "Cantrip (Conjuration)" in spell.rendered_html
        assert "30 feet" in spell.rendered_html
        assert "Heavy armor made of interlocking metal rings." in phb_entries["Chain Mail"].rendered_html
        assert phb_entries["Chain Mail"].metadata["ac"] == 16
        assert phb_entries["Chain Mail"].metadata["type"] == "HA"
        assert phb_entries["Chain Mail"].metadata["strength"] == "13"
        assert phb_entries["Chain Mail"].metadata["stealth_disadvantage"] is True
        assert phb_entries["Longsword"].metadata["damage"] == "1d8 slashing"
        assert phb_entries["Longsword"].metadata["weapon_category"] == "martial"
        assert phb_entries["Longsword"].metadata["properties"] == ["V"]
        assert "<strong>Weapon Properties:</strong> <span>Versatile</span>" in phb_entries["Longsword"].rendered_html
        assert "martial ranged weapon" in phb_entries["Light Crossbow"].rendered_html
        assert "twenty crossbow bolts" in phb_entries["Crossbow Bolts (20)"].rendered_html
        fighter = phb_entries["Fighter"]
        assert "Summary" not in fighter.rendered_html
        assert "<strong>Hit Die:</strong> <span>1d10</span>" in fighter.rendered_html
        assert "light, medium, heavy, shield" in fighter.rendered_html
        assert "simple, martial" in fighter.rendered_html
        assert "<p>light</p>" not in fighter.rendered_html
        assert "1d10" in fighter.rendered_html
        assert "Class Features By Level" in fighter.rendered_html
        assert "Level 1" in fighter.rendered_html
        fighting_style = phb_entries["Fighting Style"]
        assert "Choose 1 option:" in fighting_style.rendered_html
        assert "Archery" in fighting_style.rendered_html
        hill_dwarf = phb_entries["Hill Dwarf"]
        assert "Base Race:</strong> <span>Dwarf</span>" in hill_dwarf.rendered_html
        assert "Subrace:</strong> <span>Hill</span>" in hill_dwarf.rendered_html
        assert "Dwarven Toughness" in hill_dwarf.rendered_html
        drow = phb_entries["Drow"]
        assert "Base Race:</strong> <span>Elf</span>" in drow.rendered_html
        assert "Subrace:</strong> <span>Drow</span>" in drow.rendered_html
        assert "Superior Darkvision" in drow.rendered_html
        assert "High Elf" in phb_entries
        variant_human = phb_entries["Variant Human"]
        assert "Base Race:</strong> <span>Human</span>" in variant_human.rendered_html
        assert "Subrace:</strong> <span>Variant</span>" in variant_human.rendered_html
        assert "Skills" in variant_human.rendered_html
        assert "Feat" in variant_human.rendered_html
        assert "one skill of your choice" in variant_human.rendered_html
        fallen_aasimar = vgm_entries["Fallen Aasimar"]
        assert "Base Race:</strong> <span>Aasimar</span>" in fallen_aasimar.rendered_html
        assert "Necrotic Shroud" in fallen_aasimar.rendered_html
        draconblood = egw_entries["Draconblood Dragonborn"]
        assert "Base Race:</strong> <span>Dragonborn</span>" in draconblood.rendered_html
        assert "Forceful Presence" in draconblood.rendered_html

        monster = mm_entries["Goblin"]
        raw_monster_text = json.dumps(monster.metadata, sort_keys=True) + json.dumps(monster.body, sort_keys=True)
        assert "hasToken" not in raw_monster_text
        assert "soundClip" not in raw_monster_text
        assert "altArt" not in raw_monster_text
        assert "Melee Weapon Attack:" in monster.rendered_html
        assert "+4" in monster.rendered_html


def test_importer_supports_scag_backgrounds(app, tmp_path):
    data_root = build_scag_background_data_root(tmp_path / "dnd5e-source-scag-backgrounds")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("SCAG", entry_types=["background"])
        store = app.extensions["systems_store"]
        clan_crafter = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "SCAG", entry_type="background", limit=10)
            if entry.title == "Clan Crafter"
        )

    assert result.imported_count == 1
    assert result.imported_by_type == {"background": 1}
    assert clan_crafter.metadata["skill_proficiencies"] == [{"history": True, "insight": True}]
    assert clan_crafter.metadata["language_proficiencies"] == [{"dwarvish": True}, {"anyStandard": 1}]
    assert clan_crafter.metadata["tool_proficiencies"] == [{"anyArtisansTool": 1}]
    assert "Respect of the Stout Folk" in clan_crafter.rendered_html


def test_importer_expands_safe_classic_magic_armor_variants(app, tmp_path):
    data_root = build_magicvariant_data_root(tmp_path / "dnd5e-source-magicvariants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["item"])
        result = importer.import_source("DMG", entry_types=["item"])
        store = app.extensions["systems_store"]
        dmg_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=20)
        }

    assert result.imported_count == 1
    assert result.imported_by_type == {"item": 1}
    assert "+1 Chain Mail" in dmg_entries
    assert "You have a +1 bonus to AC while wearing this armor." in dmg_entries["+1 Chain Mail"].rendered_html
    assert "Heavy armor made of interlocking metal rings." in dmg_entries["+1 Chain Mail"].rendered_html
    assert dmg_entries["+1 Chain Mail"].metadata["ac"] == 16
    assert dmg_entries["+1 Chain Mail"].metadata["bonus_ac"] == "+1"
    assert dmg_entries["+1 Chain Mail"].metadata["base_item"] == "Chain Mail|PHB"


def test_importer_replaces_existing_entries_for_a_source(app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

        updated_spell_file = data_root / "data/spells/spells-phb.json"
        write_json(
            updated_spell_file,
            {
                "spell": [
                    {
                        "name": "Shield",
                        "source": "PHB",
                        "page": 275,
                        "level": 1,
                        "school": "A",
                        "time": [{"number": 1, "unit": "reaction"}],
                        "range": {"type": "self"},
                        "components": {"v": True, "s": True},
                        "duration": [{"type": "timed", "duration": {"type": "round", "amount": 1}}],
                        "entries": ["An invisible barrier of magical force appears and protects you."]
                    }
                ]
            },
        )

        result = importer.import_source("PHB", entry_types=["spell"])
        entries = app.extensions["systems_store"].list_entries_for_source("DND-5E", "PHB", limit=100)

        assert result.imported_count == 1
        titles = [entry.title for entry in entries]
        assert "Shield" in titles
        assert "Mage Hand" not in titles
        assert "Alert" in titles
        assert "Fighter" in titles
        assert len(entries) == 29


def test_systems_search_uses_imported_entries(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["spell"])

    sign_in(users["party"]["email"], users["party"]["password"])
    response = client.get("/campaigns/linden-pass/systems/search?q=mage")

    assert response.status_code == 200
    assert "Mage Hand" in response.get_data(as_text=True)


def test_systems_search_ignores_body_text_false_positives(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

    sign_in(users["party"]["email"], users["party"]["password"])

    global_search = client.get("/campaigns/linden-pass/systems/search?q=spectral")
    source_search = client.get("/campaigns/linden-pass/systems/sources/PHB/types/spell?q=spectral")

    assert global_search.status_code == 200
    global_html = global_search.get_data(as_text=True)
    assert "Mage Hand" not in global_html
    assert "No imported systems entries matched that search yet." in global_html

    assert source_search.status_code == 200
    source_html = source_search.get_data(as_text=True)
    assert "Mage Hand" not in source_html
    assert "matched that title/type search." in source_html


def test_source_detail_is_a_category_index_and_category_page_is_not_capped_at_one_hundred(
    client, sign_in, users, app, tmp_path
):
    data_root = build_large_feat_data_root(tmp_path / "dnd5e-source-large", count=105)

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["feat"])

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/feat")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "105 browsable entries across 1" in source_body
    assert "category." in source_body
    assert "Feats" in source_body
    assert "Feat 000" not in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 105 feats in this source." in category_body
    assert "Feat 000" in category_body
    assert "Feat 104" in category_body


def test_rules_reference_search_uses_curated_metadata_without_full_body_search(
    client, sign_in, users, app, tmp_path
):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-reference-search")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

    sign_in(users["party"]["email"], users["party"]["password"])

    heading_response = client.get("/campaigns/linden-pass/systems/search?reference_q=passive+checks")
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB?reference_q=surprise")
    rule_response = client.get("/campaigns/linden-pass/systems/search?reference_q=15+strength")
    negative_response = client.get("/campaigns/linden-pass/systems/search?reference_q=training+talent")

    assert heading_response.status_code == 200
    heading_body = heading_response.get_data(as_text=True)
    assert "Rules Reference Search" in heading_body
    assert "Using Ability Scores" in heading_body
    assert "PHB | Book Chapters | Chapter 7" in heading_body

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Rules Reference Search" in source_body
    assert "Combat" in source_body
    assert "PHB | Book Chapters | Chapter 9" in source_body
    assert "Searches only this source&#39;s book chapters using curated metadata" in source_body
    assert "`RULES` entries" not in source_body

    assert rule_response.status_code == 200
    rule_body = rule_response.get_data(as_text=True)
    assert "Carrying Capacity and Encumbrance" in rule_body
    assert "RULES | Rules" in rule_body

    assert negative_response.status_code == 200
    negative_body = negative_response.get_data(as_text=True)
    assert "No rules references matched that metadata search yet." in negative_body
    assert "Using Ability Scores" not in negative_body


def test_rule_pages_surface_active_campaign_overlays_from_mechanics_pages(
    app, client, sign_in, users
):
    with app.app_context():
        service = app.extensions["systems_service"]
        spell_math_rule_entry = next(
            entry
            for entry in service.list_entries_for_campaign_source(
                "linden-pass",
                "RULES",
                entry_type="rule",
                limit=None,
            )
            if entry.title == "Spell Attacks and Save DCs"
        )

        campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
        page_path = campaigns_dir / "linden-pass" / "content" / "mechanics" / "spellcasting-baseline-update.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            (
                "---\n"
                "title: Spellcasting Baseline Update\n"
                "section: Mechanics\n"
                "type: mechanic\n"
                "subsection: Variant and House Rules\n"
                "character_option:\n"
                "  kind: feature\n"
                "  name: Spellcasting Baseline Update\n"
                "  activation_type: special\n"
                "  base_rule_refs:\n"
                "    - rule_key: spell-attacks-and-save-dcs\n"
                "---\n\n"
                "Spell attacks in this campaign use the published party-wide baseline for spell save math.\n"
            ),
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    rule_response = client.get(f"/campaigns/linden-pass/systems/entries/{spell_math_rule_entry.slug}")

    assert rule_response.status_code == 200
    rule_body = rule_response.get_data(as_text=True)
    assert "Active Campaign Overlays" in rule_body
    assert "Spellcasting Baseline Update" in rule_body
    assert "Applies To:</strong> This entry." in rule_body
    assert "This house rule stays visible beside the baseline links, but the app does not currently automate the change." in rule_body
    assert "Spell attacks in this campaign use the published party-wide baseline for spell save math." in rule_body
    assert '/campaigns/linden-pass/pages/mechanics/spellcasting-baseline-update' in rule_body


def test_systems_entry_pages_surface_related_rules_references(
    client, sign_in, users, app, tmp_path
):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB")

        store = app.extensions["systems_store"]
        longsword_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="item", limit=20)
            if entry.title == "Longsword"
        )
        athletics_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="skill", limit=20)
            if entry.title == "Athletics"
        )
        mage_hand_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="spell", limit=20)
            if entry.title == "Mage Hand"
        )
        fighter_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20)
            if entry.title == "Fighter"
        )
        encumbrance_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="variantrule", limit=20)
            if entry.title == "Encumbrance"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    longsword_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")
    athletics_response = client.get(f"/campaigns/linden-pass/systems/entries/{athletics_entry.slug}")
    mage_hand_response = client.get(f"/campaigns/linden-pass/systems/entries/{mage_hand_entry.slug}")
    fighter_response = client.get(f"/campaigns/linden-pass/systems/entries/{fighter_entry.slug}")
    encumbrance_response = client.get(f"/campaigns/linden-pass/systems/entries/{encumbrance_entry.slug}")

    assert longsword_response.status_code == 200
    longsword_body = longsword_response.get_data(as_text=True)
    assert "Related Rules References" in longsword_body
    assert "Attack Rolls and Attack Bonus" in longsword_body
    assert "Damage Rolls" in longsword_body
    assert "Equipped Items, Inventory, and Attunement" in longsword_body

    assert athletics_response.status_code == 200
    athletics_body = athletics_response.get_data(as_text=True)
    assert "Related Rules References" in athletics_body
    assert "Ability Scores and Ability Modifiers" in athletics_body
    assert "Proficiency Bonus" in athletics_body
    assert "Skill Bonuses and Proficiency" in athletics_body

    assert mage_hand_response.status_code == 200
    mage_hand_body = mage_hand_response.get_data(as_text=True)
    assert "Related Rules References" in mage_hand_body
    assert "Spell Attacks and Save DCs" in mage_hand_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert "Related Rules References" in fighter_body
    assert "Proficiency Bonus" in fighter_body
    assert "Hit Points and Hit Dice" in fighter_body

    assert encumbrance_response.status_code == 200
    encumbrance_body = encumbrance_response.get_data(as_text=True)
    assert "Related Rules References" in encumbrance_body
    assert "Carrying Capacity and Encumbrance" in encumbrance_body


def test_source_index_and_category_page_respect_disabled_entry_overrides(
    client, sign_in, users, app, tmp_path
):
    data_root = build_large_feat_data_root(tmp_path / "dnd5e-source-large", count=3)

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["feat"])

        store = app.extensions["systems_store"]
        disabled_entry = next(
            (entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="feat", limit=10) if entry.title == "Feat 001"),
            None,
        )
        assert disabled_entry is not None
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug="DND-5E",
            entry_key=disabled_entry.entry_key,
            visibility_override=None,
            is_enabled_override=False,
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    category_response = client.get("/campaigns/linden-pass/systems/sources/PHB/types/feat")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "2 entries" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Showing all 2 feats in this source." in category_body
    assert "Feat 000" in category_body
    assert "Feat 001" not in category_body
    assert "Feat 002" in category_body
