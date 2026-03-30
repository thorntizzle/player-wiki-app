from __future__ import annotations


def test_native_character_edits_can_apply_and_remove_campaign_page_spell_grants(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    blessing_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "blessing-of-the-tide.md"
    )
    blessing_page_path.write_text(
        """---
title: Blessing of the Tide
section: Mechanics
subsection: Blessings
published: true
summary: A tide-bound boon for trusted wardens.
character_option:
  name: Blessing of the Tide
  description_markdown: Call on the tide to steady your footing.
  activation_type: bonus_action
  grants:
    languages:
      - Primordial
    spells:
      - spell: Light
        mark: Granted
      - spell: Detect Magic
        always_prepared: true
        ritual: true
---
Wardens call on the tide when the harbor turns dangerous.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|light",
                    "entry_type": "spell",
                    "slug": "phb-spell-light",
                    "title": "Light",
                    "source_page": "255",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "light",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "ritual": False},
                    "body": {},
                    "rendered_html": "<p>Light.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "ritual": True},
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/blessing-of-the-tide",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/blessing-of-the-tide"
    )
    assert custom_feature["name"] == "Blessing of the Tide"
    assert custom_feature["description_markdown"] == "Call on the tide to steady your footing."
    assert "Primordial" in record.definition.proficiencies["languages"]

    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Light"]["systems_ref"]["slug"] == "phb-spell-light"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["systems_ref"]["slug"] == "phb-spell-detect-magic"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert "Primordial" not in record.definition.proficiencies["languages"]
    assert all(
        feature.get("page_ref") != "mechanics/blessing-of-the-tide"
        for feature in record.definition.features
    )
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    assert "Light" not in spells_by_name
    assert "Detect Magic" not in spells_by_name


def test_owner_player_can_open_native_character_edit_page(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Edit Arden March" in html
    assert "Save character edits" in html
    assert "Languages" in html
    assert "Reference Text" in html
    assert "Campaign Adjustments" in html
    assert "Custom Features" in html
    assert "Uses / Max" in html
    assert "Manual Equipment" in html
    assert "Linked Page" in html
    assert "Stormglass Compass | Items" in html
    assert "Arcane Overload | Mechanics / Class Modifications" in html


def test_owner_player_can_save_native_character_edits_and_reconcile_inventory_state(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    first_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish\nThieves' Cant",
            "armor_proficiencies_text": "Light Armor\nMedium Armor",
            "weapon_proficiencies_text": "Simple Weapons\nMartial Weapons",
            "tool_proficiencies_text": "Navigator's Tools\nThieves' Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/arcane-overload",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "You can usually find a friendly runner near the north piers.",
            "manual_item_name_1": "",
            "manual_item_page_ref_1": "items/stormglass-compass",
            "manual_item_quantity_1": "1",
            "manual_item_weight_1": "light",
            "manual_item_notes_1": "Stamped with blue wax.",
        },
        follow_redirects=False,
    )

    assert first_response.status_code == 302
    assert first_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march/edit")

    record = get_character("arden-march")
    assert record is not None
    assert record.import_metadata.import_status == "managed"
    assert "Elvish" in record.definition.proficiencies["languages"]
    assert "Navigator's Tools" in record.definition.proficiencies["tools"]

    custom_feature = next(
        feature for feature in record.definition.features if feature.get("category") == "custom_feature"
    )
    assert custom_feature["name"] == "Arcane Overload"
    assert custom_feature["description_markdown"] == "You can usually find a friendly runner near the north piers."
    assert custom_feature["page_ref"] == "mechanics/arcane-overload"

    manual_item = next(
        item
        for item in record.definition.equipment_catalog
        if item.get("source_kind") == "manual_edit"
    )
    assert manual_item["name"] == "Stormglass Compass"
    assert manual_item["default_quantity"] == 1
    assert manual_item["notes"] == "Stamped with blue wax."
    assert manual_item["page_ref"] == "items/stormglass-compass"

    inventory_item = next(
        item for item in record.state_record.state["inventory"] if item.get("catalog_ref") == manual_item["id"]
    )
    assert inventory_item["name"] == "Stormglass Compass"
    assert inventory_item["quantity"] == 1
    assert inventory_item["notes"] == "Stamped with blue wax."

    second_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish\nThieves' Cant",
            "armor_proficiencies_text": "Light Armor\nMedium Armor",
            "weapon_proficiencies_text": "Simple Weapons\nMartial Weapons",
            "tool_proficiencies_text": "Navigator's Tools\nThieves' Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "Overloaded Arcana",
            "custom_feature_page_ref_1": "mechanics/arcane-overload",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "You can usually find a friendly runner near the north piers.",
            "manual_item_id_1": manual_item["id"],
            "manual_item_name_1": "Silver Compass",
            "manual_item_page_ref_1": "items/stormglass-compass",
            "manual_item_quantity_1": "2",
            "manual_item_weight_1": "1 lb.",
            "manual_item_notes_1": "Stamped with silver wax.",
        },
        follow_redirects=False,
    )

    assert second_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    inventory_item = next(
        item for item in record.state_record.state["inventory"] if item.get("catalog_ref") == manual_item["id"]
    )
    custom_feature = next(
        feature for feature in record.definition.features if feature.get("category") == "custom_feature"
    )
    manual_item = next(
        item
        for item in record.definition.equipment_catalog
        if item.get("source_kind") == "manual_edit"
    )
    assert custom_feature["name"] == "Overloaded Arcana"
    assert custom_feature["page_ref"] == "mechanics/arcane-overload"
    assert manual_item["name"] == "Silver Compass"
    assert manual_item["page_ref"] == "items/stormglass-compass"
    assert inventory_item["quantity"] == 2
    assert inventory_item["weight"] == "1 lb."
    assert inventory_item["notes"] == "Stamped with silver wax."

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/pages/mechanics/arcane-overload" in read_html

    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert equipment_response.status_code == 200
    equipment_html = equipment_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/pages/items/stormglass-compass" in equipment_html


def test_stale_revision_is_rejected_for_native_character_edits(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": stale_revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "manual_item_name_1": "Storm Token",
            "manual_item_quantity_1": "1",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": stale_revision,
            "languages_text": "Common\nDwarvish",
        },
        follow_redirects=True,
    )

    assert second.status_code == 409
    html = second.get_data(as_text=True)
    assert "This sheet changed in another session. Refresh the page and try again." in html

    record = get_character("arden-march")
    assert record is not None
    manual_items = [
        item for item in record.definition.equipment_catalog if item.get("source_kind") == "manual_edit"
    ]
    assert any(item["name"] == "Storm Token" for item in manual_items)
    assert "Dwarvish" not in record.definition.proficiencies["languages"]


def test_native_character_edits_can_manage_reference_text_and_feature_trackers(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    first_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "biography_markdown": "Raised on the storm coast.",
            "personality_markdown": "- Calm under pressure",
            "additional_notes_markdown": "Keeps a weather eye on the harbor.",
            "allies_and_organizations_markdown": "Harbor Wardens",
            "custom_feature_name_1": "Blessing of the Tide",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "Call on the tide to steady your footing.",
            "custom_feature_resource_max_1": "3",
            "custom_feature_resource_reset_on_1": "long_rest",
        },
        follow_redirects=False,
    )

    assert first_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert record.definition.profile["biography_markdown"] == "Raised on the storm coast."
    assert record.definition.profile["personality_markdown"] == "- Calm under pressure"
    assert record.definition.reference_notes["additional_notes_markdown"] == "Keeps a weather eye on the harbor."
    assert record.definition.reference_notes["allies_and_organizations_markdown"] == "Harbor Wardens"

    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("name") == "Blessing of the Tide"
    )
    tracker_ref = str(custom_feature.get("tracker_ref") or "")
    assert tracker_ref.startswith("manual-feature-tracker:")

    tracker_template = next(
        template for template in record.definition.resource_templates if template.get("id") == tracker_ref
    )
    assert tracker_template["label"] == "Blessing of the Tide"
    assert tracker_template["max"] == 3
    assert tracker_template["reset_on"] == "long_rest"

    resource_state = next(
        resource for resource in record.state_record.state["resources"] if resource.get("id") == tracker_ref
    )
    assert resource_state["label"] == "Blessing of the Tide"
    assert resource_state["current"] == 3
    assert resource_state["max"] == 3
    assert resource_state["reset_on"] == "long_rest"

    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?page=notes")
    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert "Raised on the storm coast." in notes_html
    assert "Harbor Wardens" in notes_html

    features_response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")
    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Blessing of the Tide: 3 / 3 (Long Rest)" in features_html

    second_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "biography_markdown": "Raised on the storm coast.",
            "personality_markdown": "- Calm under pressure",
            "additional_notes_markdown": "Keeps a weather eye on the harbor.",
            "allies_and_organizations_markdown": "Harbor Wardens",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "",
            "custom_feature_resource_max_1": "",
            "custom_feature_resource_reset_on_1": "manual",
        },
        follow_redirects=False,
    )

    assert second_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert all(
        feature.get("name") != "Blessing of the Tide"
        for feature in record.definition.features
    )
    assert all(template.get("id") != tracker_ref for template in record.definition.resource_templates)
    assert all(resource.get("id") != tracker_ref for resource in record.state_record.state["resources"])


def test_native_character_edits_can_apply_campaign_stat_adjustments(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    base_stats = dict(record.definition.stats or {})

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "stat_adjustment_max_hp": "4",
            "stat_adjustment_armor_class": "1",
            "stat_adjustment_initiative_bonus": "2",
            "stat_adjustment_speed": "10",
            "stat_adjustment_passive_perception": "3",
            "stat_adjustment_passive_insight": "-1",
            "stat_adjustment_passive_investigation": "2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    adjustments = record.definition.stats["manual_adjustments"]
    assert adjustments == {
        "max_hp": 4,
        "armor_class": 1,
        "initiative_bonus": 2,
        "speed": 10,
        "passive_perception": 3,
        "passive_insight": -1,
        "passive_investigation": 2,
    }
    assert record.definition.stats["max_hp"] == int(base_stats["max_hp"]) + 4
    assert record.definition.stats["armor_class"] == int(base_stats["armor_class"]) + 1
    assert record.definition.stats["initiative_bonus"] == int(base_stats["initiative_bonus"]) + 2
    assert record.definition.stats["speed"] == "40 ft."
    assert record.definition.stats["passive_perception"] == int(base_stats["passive_perception"]) + 3
    assert record.definition.stats["passive_insight"] == int(base_stats["passive_insight"]) - 1
    assert record.definition.stats["passive_investigation"] == int(base_stats["passive_investigation"]) + 2

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "40 ft." in read_html
