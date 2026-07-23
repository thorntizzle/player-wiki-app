from __future__ import annotations

from tests.helpers.systems_importer_test_helpers import *

def test_importer_preserves_additional_spell_metadata_on_class_entries(app, tmp_path):
    data_root = build_additional_spell_metadata_data_root(tmp_path / "dnd5e-source-additional-spells")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "subclass", "classfeature", "subclassfeature"])
        store = app.extensions["systems_store"]
        entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", limit=20)}

    assert entries["Cleric"].metadata["additional_spells"] == [{"prepared": {"1": ["ceremony"]}}]
    assert entries["Life Domain"].metadata["additional_spells"] == [
        {"prepared": {"1": ["bless", "cure wounds"], "3": ["lesser restoration", "spiritual weapon"]}}
    ]
    assert entries["Spellcasting"].metadata["additional_spells"] == [{"prepared": {"1": ["guidance"]}}]
    assert entries["Disciple of Life"].metadata["additional_spells"] == [{"prepared": {"1": ["bless"]}}]


def test_importer_preserves_native_class_progression_and_spell_class_lists(app, tmp_path):
    data_root = build_class_progression_metadata_data_root(tmp_path / "dnd5e-source-class-progression")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("TCE", entry_types=["class", "classfeature", "spell"])
        store = app.extensions["systems_store"]
        artificer = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="class", limit=10)
            if entry.title == "Artificer"
        )
        guidance = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="spell", limit=10)
            if entry.title == "Guidance"
        )

    assert artificer.metadata["spellcasting_ability"] == "int"
    assert artificer.metadata["caster_progression"] == "artificer"
    assert artificer.metadata["prepared_spells"] == "<$level$> / 2 + <$int_mod$>"
    assert artificer.metadata["cantrip_progression"] == [2, 2, 2]
    assert artificer.metadata["slot_progression"] == [
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 3}],
    ]
    assert guidance.metadata["class_lists"] == {"TCE": ["Artificer"]}


def test_importer_resolves_spell_class_lists_from_generated_lookup_keys_with_spaces(app, tmp_path):
    data_root = build_spell_class_lookup_data_root(tmp_path / "dnd5e-source-spell-class-lookup")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["spell"])
        store = app.extensions["systems_store"]
        mage_hand = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="spell", limit=10)
            if entry.title == "Mage Hand"
        )

    assert mage_hand.metadata["class_lists"] == {"PHB": ["Wizard"]}


def test_importer_includes_class_variant_source_classes(app, tmp_path):
    data_root = build_spell_class_variant_data_root(tmp_path / "dnd5e-source-spell-class-variant")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["spell"])
        store = app.extensions["systems_store"]
        absorb_elements = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="spell", limit=10)
            if entry.title == "Absorb Elements"
        )

    assert absorb_elements.metadata["class_lists"] == {
        "PHB": ["Druid", "Ranger", "Sorcerer", "Wizard"],
        "TCE": ["Artificer"],
    }


def test_importer_preserves_spell_ritual_metadata_for_native_builder(app, tmp_path):
    data_root = build_spell_metadata_data_root(tmp_path / "dnd5e-source-spell-metadata")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["spell"])
        store = app.extensions["systems_store"]
        detect_magic = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="spell", limit=10)
            if entry.title == "Detect Magic"
        )

    assert detect_magic.metadata["ritual"] is True


def test_importer_preserves_structured_feat_metadata_for_native_builder(app, tmp_path):
    data_root = build_feat_metadata_data_root(tmp_path / "dnd5e-source-feat-metadata")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("PHB", entry_types=["feat"])

        assert result.imported_count == 2
        store = app.extensions["systems_store"]
        feat_entries = {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="feat", limit=10)}

    resilient = feat_entries["Resilient"]
    skilled = feat_entries["Skilled"]

    assert resilient.metadata["ability"] == [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"], "amount": 1}}]
    assert resilient.metadata["saving_throw_proficiencies"] == [{"choose": {"from": ["str", "dex", "con", "int", "wis", "cha"]}}]
    assert skilled.metadata["skill_tool_language_proficiencies"] == [
        {"choose": [{"from": ["anySkill", "anyTool"], "count": 3}]}
    ]


def test_importer_skips_xphb_subclass_variants(app, tmp_path):
    data_root = build_xphb_variant_subclass_data_root(tmp_path / "dnd5e-source-xphb-variants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("EGW", entry_types=["subclass", "subclassfeature"])
        subclasses = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "EGW",
            entry_type="subclass",
        )
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "EGW",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclass": 1, "subclassfeature": 1}
    assert [entry.slug for entry in subclasses] == ["egw-subclass-chronurgymagic-wizard-phb"]
    assert [entry.slug for entry in subclassfeatures] == [
        "egw-subclassfeature-chronurgymagic-wizard-phb-chronurgy-egw-2"
    ]


def test_importer_skips_efa_variant_subclass_aliases(app, tmp_path):
    data_root = build_efa_variant_subclass_data_root(tmp_path / "dnd5e-source-efa-variants")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("TCE", entry_types=["subclass", "subclassfeature"])
        subclasses = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclass",
        )
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclass": 1, "subclassfeature": 1}
    assert [entry.slug for entry in subclasses] == ["tce-subclass-alchemist-artificer-tce"]
    assert [entry.slug for entry in subclassfeatures] == [
        "tce-subclassfeature-alchemist-artificer-tce-alchemist-tce-3"
    ]


def test_class_pages_surface_optionalfeature_progression_options(app, client, sign_in, users, tmp_path):
    data_root = build_class_optionalfeature_progression_data_root(tmp_path / "dnd5e-source-class-optionalfeatures")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "optionalfeature"])
        importer.import_source("TCE", entry_types=["class", "classfeature", "optionalfeature"])

        store = app.extensions["systems_store"]
        warlock_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20)
            if entry.title == "Warlock"
        )
        artificer_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "TCE", entry_type="class", limit=20)
            if entry.title == "Artificer"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    warlock_response = client.get(f"/campaigns/linden-pass/systems/entries/{warlock_entry.slug}")
    artificer_response = client.get(f"/campaigns/linden-pass/systems/entries/{artificer_entry.slug}")

    assert warlock_response.status_code == 200
    warlock_body = warlock_response.get_data(as_text=True)
    assert "Eldritch Invocations" in warlock_body
    assert "Agonizing Blast" in warlock_body
    assert "Armor of Shadows" in warlock_body
    assert "Level 2: 2" in warlock_body
    assert "Level 5: 3" in warlock_body

    assert artificer_response.status_code == 200
    artificer_body = artificer_response.get_data(as_text=True)
    assert "Infusions Known" in artificer_body
    assert "Enhanced Arcane Focus" in artificer_body
    assert "Mind Sharpener" in artificer_body
    assert "Level 2: 4" in artificer_body
    assert "Level 6: 6" in artificer_body
    assert "Class Optional Features" not in artificer_body


def test_subclass_pages_and_subclassfeature_pages_surface_optionalfeature_cards(
    app, client, sign_in, users, tmp_path
):
    data_root = build_subclass_optionalfeature_progression_data_root(tmp_path / "dnd5e-source-subclass-optionalfeatures")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["subclass", "subclassfeature", "optionalfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclass", limit=20)
            if entry.title == "Arcane Archer"
        )
        subclassfeature_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclassfeature", limit=20)
            if entry.title == "Arcane Shot Options"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")
    subclassfeature_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclassfeature_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Subclass Features By Level" in subclass_body
    assert "Arcane Shot Options" in subclass_body
    assert "Banishing Arrow" in subclass_body
    assert "Bursting Arrow" in subclass_body
    assert "systems-inline-option-card" in subclass_body
    assert "Subclass Optional Features" not in subclass_body

    assert subclassfeature_response.status_code == 200
    subclassfeature_body = subclassfeature_response.get_data(as_text=True)
    assert "Banishing Arrow" in subclassfeature_body
    assert "Bursting Arrow" in subclassfeature_body
    assert "Choose 2 options" in subclassfeature_body
    assert "systems-inline-option-card" in subclassfeature_body
    assert "<strong>Subclass:</strong> <span>Arcane Archer</span>" in subclassfeature_body


def test_subclass_pages_match_subclassfeature_short_names_to_full_titles(
    app, client, sign_in, users, tmp_path
):
    data_root = build_subclass_short_name_matching_data_root(tmp_path / "dnd5e-source-subclass-short-name")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "College of Lore"
        )
        subclassfeature_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclassfeature", limit=20)
            if entry.title == "Bonus Proficiencies"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Subclass Features By Level" in subclass_body
    assert "Bonus Proficiencies" in subclass_body
    assert "You gain proficiency with three skills of your choice." in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{subclassfeature_entry.slug}"' in subclass_body


def test_subclass_import_preserves_structured_spellcasting_metadata(app, tmp_path):
    data_root = build_subclass_spellcasting_data_root(tmp_path / "dnd5e-source-subclass-spellcasting")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("XGE", entry_types=["subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "XGE", entry_type="subclass", limit=20)
            if entry.title == "Spellblade"
        )

    assert subclass_entry.metadata["spellcasting_ability"] == "int"
    assert subclass_entry.metadata["caster_progression"] == "1/3"
    assert subclass_entry.metadata["cantrip_progression"] == [0, 0, 2, 2]
    assert subclass_entry.metadata["spells_known_progression"] == [0, 0, 3, 4]
    assert subclass_entry.metadata["slot_progression"] == [
        [],
        [],
        [{"level": 1, "max_slots": 2}],
        [{"level": 1, "max_slots": 3}],
    ]


def test_subclass_pages_surface_campaign_mechanics_progression_overlays(
    app, client, sign_in, users, tmp_path
):
    data_root = build_campaign_subclass_progression_data_root(tmp_path / "dnd5e-source-campaign-subclass-progression")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "Wild Magic"
        )
        wild_magic_rule_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "RULES", entry_type="rule", limit=50)
            if entry.title == "Hit Points and Hit Dice"
        )

        campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
        page_path = campaigns_dir / "linden-pass" / "content" / "mechanics" / "wild-magic-modification.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "---\n"
            "title: Wild Magic Modification\n"
            "section: Mechanics\n"
            "type: mechanic\n"
            "subsection: Class Modifications\n"
            "character_progression:\n"
            "  kind: subclass\n"
            "  class_name: Sorcerer\n"
            "  subclass_name: Wild Magic\n"
            "  level: 1\n"
            "  character_option:\n"
            "    name: Wild Magic Modification\n"
            "    activation_type: special\n"
            "    base_rule_refs:\n"
            "      - rule_key: hit-points-and-hit-dice\n"
            "    grants:\n"
            "      resource:\n"
            "        label: Wild Die\n"
            "        reset_on: long_rest\n"
            "        scaling:\n"
            "          mode: half_level\n"
            "          minimum: 1\n"
            "          round: down\n"
            "---\n\n"
            "You gain a number of Wild Die equal to half your level. A Wild Die is a d6.\n",
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Wild Magic Surge" in subclass_body
    assert "Wild Magic Modification" in subclass_body
    assert "Wild Die" in subclass_body
    assert "You gain a number of Wild Die equal to half your level." in subclass_body
    assert '/campaigns/linden-pass/pages/mechanics/wild-magic-modification' in subclass_body
    assert "Overlay Support:" in subclass_body
    assert "Mechanically Modeled Overlay." in subclass_body
    assert (
        "This overlay uses existing structured campaign metadata that the app can already project on supported "
        "character and build surfaces." in subclass_body
    )
    assert "Existing Structured Hooks:" not in subclass_body
    assert "Character Option." not in subclass_body
    assert "Character Progression." not in subclass_body
    assert "Missing Metadata For True Base-Rule Modifiers:" not in subclass_body
    assert "Change Operation." not in subclass_body
    assert "Affected Rule Facet." not in subclass_body
    assert "Baseline Carry-Forward." not in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{wild_magic_rule_entry.slug}"' in subclass_body


def test_subclass_pages_surface_campaign_overlay_base_rule_refs(
    app, client, sign_in, users, tmp_path
):
    data_root = build_campaign_subclass_progression_data_root(
        tmp_path / "dnd5e-source-campaign-overlay-base-rules"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "Wild Magic"
        )
        spellcasting_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="classfeature", limit=20)
            if entry.title == "Spellcasting"
        )
        spell_math_rule_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "RULES", entry_type="rule", limit=50)
            if entry.title == "Spell Attacks and Save DCs"
        )

        campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
        page_path = campaigns_dir / "linden-pass" / "content" / "mechanics" / "wild-magic-modification.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            (
                "---\n"
                "title: Wild Magic Modification\n"
                "section: Mechanics\n"
                "type: mechanic\n"
                "subsection: Class Modifications\n"
                "character_progression:\n"
                "  kind: subclass\n"
                "  class_name: Sorcerer\n"
                "  subclass_name: Wild Magic\n"
                "  level: 1\n"
                "  character_option:\n"
                "    name: Wild Magic Modification\n"
                "    activation_type: special\n"
                "    base_rule_refs:\n"
                "      - rule_key: spell-attacks-and-save-dcs\n"
                f"      - slug: {spellcasting_entry.slug}\n"
                "        entry_type: classfeature\n"
                "        source_id: PHB\n"
                "---\n\n"
                "Your wild magic now keys off the campaign spellcasting baseline.\n"
            ),
            encoding="utf-8",
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Overlay Support:" in subclass_body
    assert "Reference-Only Overlay." in subclass_body
    assert "This house rule stays visible beside the baseline links, but the app does not currently automate the change." in subclass_body
    assert "Modifies Base Rules:" in subclass_body
    assert "Precedence in this campaign: the published campaign overlay applies first." in subclass_body
    assert "Linked Character Rules Reference entries are the normalized app-owned rules layer beneath that overlay" in subclass_body
    assert "linked supported-source entries remain the baseline source context beneath both." in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{spell_math_rule_entry.slug}"' in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{spellcasting_entry.slug}"' in subclass_body
    assert "Spell Attacks and Save DCs" in subclass_body
    assert "Spellcasting" in subclass_body
    assert "Normalized RULES Reference" in subclass_body
    assert "Supported Source Baseline" in subclass_body


def test_subclass_pages_only_surface_visible_campaign_overlay_links_and_support_levels(
    app, client, sign_in, users, tmp_path
):
    data_root = build_campaign_subclass_progression_data_root(
        tmp_path / "dnd5e-source-campaign-overlay-visibility"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["class", "classfeature", "subclass", "subclassfeature"])

        store = app.extensions["systems_store"]
        subclass_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="subclass", limit=20)
            if entry.title == "Wild Magic"
        )
        spellcasting_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="classfeature", limit=20)
            if entry.title == "Spellcasting"
        )
        spell_math_rule_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "RULES", entry_type="rule", limit=50)
            if entry.title == "Spell Attacks and Save DCs"
        )

        mechanics_dir = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "mechanics"
        mechanics_dir.mkdir(parents=True, exist_ok=True)

        def write_overlay_page(
            filename: str,
            title: str,
            body: str,
            *,
            modeled_effects: list[str] | None = None,
            reveal_after_session: int | None = None,
        ) -> None:
            lines = [
                "---",
                f"title: {title}",
                "section: Mechanics",
                "type: mechanic",
                "subsection: Class Modifications",
            ]
            if reveal_after_session is not None:
                lines.append(f"reveal_after_session: {reveal_after_session}")
            lines.extend(
                [
                    "character_progression:",
                    "  kind: subclass",
                    "  class_name: Sorcerer",
                    "  subclass_name: Wild Magic",
                    "  level: 1",
                    "  character_option:",
                    f"    name: {title}",
                    "    activation_type: special",
                    "    base_rule_refs:",
                    "      - rule_key: spell-attacks-and-save-dcs",
                    f"      - slug: {spellcasting_entry.slug}",
                    "        entry_type: classfeature",
                    "        source_id: PHB",
                ]
            )
            if modeled_effects:
                lines.append("    modeled_effects:")
                lines.extend(f"      - {effect}" for effect in modeled_effects)
            lines.extend(["---", "", body, ""])
            (mechanics_dir / filename).write_text("\n".join(lines), encoding="utf-8")

        write_overlay_page(
            "wild-magic-tide-harnessing.md",
            "Wild Magic Tide Harnessing",
            "This campaign models a tide die on top of the usual spellcasting baseline.",
            modeled_effects=["save-bonus:all:1"],
        )
        write_overlay_page(
            "wild-magic-table-reference.md",
            "Wild Magic Table Reference",
            "This house rule changes the visible spellcasting baseline without automated math.",
        )
        write_overlay_page(
            "hidden-wild-magic-forecast.md",
            "Hidden Wild Magic Forecast",
            "This future overlay should stay hidden until a later session.",
            reveal_after_session=3,
        )
        app.extensions["repository_store"].refresh()

    sign_in(users["party"]["email"], users["party"]["password"])

    subclass_response = client.get(f"/campaigns/linden-pass/systems/entries/{subclass_entry.slug}")

    assert subclass_response.status_code == 200
    subclass_body = subclass_response.get_data(as_text=True)
    assert "Wild Magic Tide Harnessing" in subclass_body
    assert "Wild Magic Table Reference" in subclass_body
    assert "Hidden Wild Magic Forecast" not in subclass_body
    assert "Mechanically Modeled Overlay." in subclass_body
    assert "Reference-Only Overlay." in subclass_body
    assert (
        "This overlay uses existing structured campaign metadata that the app can already project on supported "
        "character and build surfaces." in subclass_body
    )
    assert (
        "This house rule stays visible beside the baseline links, but the app does not currently automate the "
        "change." in subclass_body
    )
    assert "Precedence in this campaign: the published campaign overlay applies first." in subclass_body
    assert (
        "Linked Character Rules Reference entries are the normalized app-owned rules layer beneath that overlay"
        in subclass_body
    )
    assert "linked supported-source entries remain the baseline source context beneath both." in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{spell_math_rule_entry.slug}"' in subclass_body
    assert f'href="/campaigns/linden-pass/systems/entries/{spellcasting_entry.slug}"' in subclass_body
    assert "Spell Attacks and Save DCs" in subclass_body
    assert "Spellcasting" in subclass_body
    assert "Normalized RULES Reference" in subclass_body
    assert "Supported Source Baseline" in subclass_body


def test_importer_skips_subclassfeatures_for_unsupported_subclass_sources(app, tmp_path):
    data_root = build_unsupported_cross_source_subclassfeature_data_root(
        tmp_path / "dnd5e-source-unsupported-subclassfeature-sources"
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        result = importer.import_source("TCE", entry_types=["subclassfeature"])
        subclassfeatures = app.extensions["systems_store"].list_entries_for_source(
            "DND-5E",
            "TCE",
            entry_type="subclassfeature",
        )

    assert result.imported_by_type == {"subclassfeature": 1}
    assert [entry.slug for entry in subclassfeatures] == [
        "tce-subclassfeature-blessedstrikes-cleric-phb-life-phb-8"
    ]


def test_class_features_are_hidden_from_source_index_and_embedded_on_class_pages(
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
        fighter_entry = next(
            (entry for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="class", limit=20) if entry.title == "Fighter"),
            None,
        )
        feature_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="classfeature", limit=20)
                if entry.title == "Fighting Style"
            ),
            None,
        )
        skill_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="skill", limit=20)
                if entry.title == "Athletics"
            ),
            None,
        )
        archery_entry = next(
            (
                entry
                for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="optionalfeature", limit=20)
                if entry.title == "Archery"
            ),
            None,
        )

    assert fighter_entry is not None
    assert feature_entry is not None
    assert skill_entry is not None
    assert archery_entry is not None

    sign_in(users["party"]["email"], users["party"]["password"])
    source_response = client.get("/campaigns/linden-pass/systems/sources/PHB")
    fighter_response = client.get(f"/campaigns/linden-pass/systems/entries/{fighter_entry.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/systems/sources/PHB/types/classfeature" not in source_body
    assert "/campaigns/linden-pass/systems/sources/PHB/types/subclassfeature" not in source_body
    assert "/campaigns/linden-pass/systems/sources/PHB/types/optionalfeature" not in source_body
    assert "Class Features are folded into their Class pages" in source_body
    assert "Subclass Features are folded into their Subclass pages" in source_body
    assert "Optional Features are surfaced under their related Class and Subclass pages" in source_body

    assert fighter_response.status_code == 200
    fighter_body = fighter_response.get_data(as_text=True)
    assert '<h2>Class Features By Level</h2>' in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{feature_entry.slug}"' in fighter_body
    assert "Choose 2 from:" in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{skill_entry.slug}"' in fighter_body
    assert "Athletics" in fighter_body
    assert "History" in fighter_body
    assert "Fighting Style" in fighter_body
    assert "Martial Archetype (choose subclass feature)" in fighter_body
    assert "Class Feature" in fighter_body
    assert 'class="systems-inline-card__header"' in fighter_body
    assert "Level 1" in fighter_body
    assert "<p>Fighting Style</p>" not in fighter_body
    assert "Optional Feature Progression" not in fighter_body
    assert 'class="systems-inline-option-card"' in fighter_body
    assert f'href="/campaigns/linden-pass/systems/entries/{archery_entry.slug}"' in fighter_body
    assert "Choose 1 option:" in fighter_body
    assert "You gain a +2 bonus to attack rolls you make with ranged weapons." in fighter_body
