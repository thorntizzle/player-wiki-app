from __future__ import annotations


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
    assert "Custom Features" in html
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
