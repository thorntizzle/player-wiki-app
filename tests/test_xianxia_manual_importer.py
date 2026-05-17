from __future__ import annotations

from html import unescape

import yaml

from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID
from player_wiki.xianxia_character_importer import (
    XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
    XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE,
    build_xianxia_manual_import_character,
)


def _base_payload():
    return {
        "campaign_slug": "linden-pass",
        "name": "Tao Vale",
        "status": "active",
        "xianxia": {
            "realm": "Immortal",
            "honor": "Majestic",
            "reputation": "Unknown",
            "hp_max": 8,
            "stance_max": 6,
            "energies": {
                "jing": {"max": 2},
                "qi": {"max": 2},
                "shen": {"max": 2},
            },
        },
    }


def _write_campaign_config(app, mutator) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()


def _configure_xianxia_campaign(app) -> None:
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    _write_campaign_config(app, _mutate)


def _read_character_definition(app, character_slug: str) -> dict:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    return yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}


def _get_character_record(app, character_slug: str):
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        return record


def _manual_import_form_data() -> dict[str, str]:
    return {
        "name": "Imported Lotus",
        "character_slug": "imported-lotus",
        "realm": "Immortal",
        "honor": "Majestic",
        "reputation": "Saffron court witness",
        "attribute_str": "9",
        "attribute_dex": "8",
        "attribute_con": "7",
        "attribute_int": "6",
        "attribute_wis": "5",
        "attribute_cha": "4",
        "effort_basic": "3",
        "effort_weapon": "4",
        "effort_guns_explosive": "5",
        "effort_magic": "6",
        "effort_ultimate": "7",
        "hp_max": "19",
        "stance_max": "17",
        "manual_armor_bonus": "4",
        "insight_available": "12",
        "insight_spent": "8",
        "energy_jing_max": "5",
        "energy_qi_max": "6",
        "energy_shen_max": "7",
        "yin_max": "9",
        "yang_max": "10",
        "dao_max": "3",
        "coin": "12",
        "supply": "3",
        "spirit_stones": "2",
        "trained_skills_text": (
            "Tea Ceremony\n"
            "Qi Sense | Raised by a wandering hermit\n"
            "Sky Calling\n"
            "Blade Focus"
        ),
        "martial_art_1_slug": "heavenly-palm",
        "martial_art_1_rank": "Novice",
        "martial_art_1_teacher": "Elder Qing",
        "martial_art_1_breakthrough": "Cloud breakthrough",
        "martial_art_1_notes": "Linked branch",
        "martial_art_2_name": "Unlisted Fist",
        "martial_art_2_rank": "Apprentice",
        "martial_art_2_teacher": "Wandering monk",
        "martial_art_2_breakthrough": "Wind step",
        "martial_art_2_notes": "Manual record",
        "inventory_text": (
            "Spirit rice | 3 | consumable, treasure | Emergency cache\n"
            "Travel cloak | 1 | tool | Weathered"
        ),
        "additional_notes_markdown": "Imported from the table sheet.",
        "player_notes_markdown": "Keep an eye on the spirit rice.",
    }


def test_manual_importer_accepts_relaxed_high_values():
    payload = _base_payload()
    payload["xianxia"]["energies"] = {"jing": {"max": 4}, "qi": {"max": 5}, "shen": {"max": 6}}
    payload["xianxia"]["yin_yang"] = {"yin_max": 99, "yang_max": 120}
    payload["xianxia"]["dao_max"] = 3
    payload["xianxia"]["insight_available"] = 777
    payload["xianxia"]["insight_spent"] = 333
    payload["xianxia"]["attributes"] = {
        "str": 20,
        "dex": 18,
        "con": 22,
        "int": 19,
        "wis": 16,
        "cha": 15,
    }
    payload["xianxia"]["efforts"] = {
        "basic": 4,
        "weapon": 5,
        "guns_explosive": 3,
        "magic": 2,
        "ultimate": 4,
    }

    definition, import_metadata, initial_state = build_xianxia_manual_import_character(payload)

    assert definition.xianxia["energies"]["jing"]["max"] == 4
    assert definition.xianxia["yin_yang"]["yang_max"] == 120
    assert definition.xianxia["attributes"]["str"] == 20
    assert definition.xianxia["efforts"]["magic"] == 2
    assert definition.xianxia["insight"]["available"] == 777
    assert definition.source["source_path"] == XIANXIA_MANUAL_IMPORTER_SOURCE_PATH
    assert definition.source["source_type"] == XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE
    assert import_metadata.import_status == "clean"
    assert initial_state["xianxia"]["yin_yang"]["yang_current"] == 120
    assert initial_state["xianxia"]["currency"] == {
        "coin": 0,
        "supply": 0,
        "spirit_stones": 0,
    }


def test_manual_importer_defaults_blank_currency_to_zero():
    payload = {
        **_base_payload(),
        "coin": "",
        "supply": "",
        "spirit_stones": "",
    }

    _, _, initial_state = build_xianxia_manual_import_character(payload)

    assert initial_state["xianxia"]["currency"] == {
        "coin": 0,
        "supply": 0,
        "spirit_stones": 0,
    }


def test_manual_importer_preserves_current_values_when_current_exceeds_maxima():
    payload = _base_payload()
    payload["state"] = {
        "vitals": {"current_hp": 25, "current_stance": 19},
        "energies_current": {
            "jing": 9,
            "qi": 8,
            "shen": 7,
        },
        "yin_yang": {"yin_current": 11, "yang_current": 13},
        "dao": {"current": 3},
    }
    payload["xianxia"]["hp_max"] = 10
    payload["xianxia"]["stance_max"] = 12
    payload["xianxia"]["energies"] = {"jing": {"max": 1}, "qi": {"max": 1}, "shen": {"max": 1}}
    payload["xianxia"]["yin_yang"] = {"yin_max": 1, "yang_max": 2}

    definition, _, initial_state = build_xianxia_manual_import_character(payload)

    assert definition.xianxia["durability"]["hp_max"] == 25
    assert definition.xianxia["durability"]["stance_max"] == 19
    assert definition.xianxia["energies"]["jing"]["max"] == 9
    assert definition.xianxia["energies"]["qi"]["max"] == 8
    assert definition.xianxia["energies"]["shen"]["max"] == 7
    assert definition.xianxia["yin_yang"]["yin_max"] == 11
    assert definition.xianxia["yin_yang"]["yang_max"] == 13

    assert initial_state["xianxia"]["vitals"]["current_hp"] == 25
    assert initial_state["xianxia"]["vitals"]["current_stance"] == 19
    assert initial_state["xianxia"]["energies"]["jing"]["current"] == 9
    assert initial_state["xianxia"]["yin_yang"]["yin_current"] == 11
    assert initial_state["xianxia"]["dao"]["current"] == 3


def test_manual_importer_supports_unlimited_skills_and_stores_notes_as_reference():
    payload = _base_payload()
    payload["trained_skills"] = [
        "Tea Ceremony",
        {"name": "Qi Sense", "notes": "Raised from a wandering hermit"},
        {"name": "Breathwork", "notes": "Found in mountain scroll"},
        {"name": "Blade Focus", "notes": "Nightblade techniques"},
        {"name": "Runic Sighting", "notes": "Cloud-path omen"},
        {"name": "Sky Calling"},
    ]

    definition, import_metadata, initial_state = build_xianxia_manual_import_character(payload)

    assert definition.xianxia["skills"]["trained"] == [
        "Tea Ceremony",
        "Qi Sense",
        "Breathwork",
        "Blade Focus",
        "Runic Sighting",
        "Sky Calling",
    ]
    assert import_metadata.warnings == []
    reference_notes = definition.reference_notes["additional_notes_markdown"]
    assert "Imported skill notes" in reference_notes


def test_manual_importer_preserves_linked_and_unlinked_martial_arts():
    payload = _base_payload()
    payload["martial_arts"] = [
        {
            "systems_ref": {"entry_type": "martial_art", "slug": "heavenly-palm"},
            "name": "Heavenly Palm",
            "current_rank": "Initiate",
            "learned_rank_refs": ["xianxia:heavenly-palm:initiate", "xianxia:heavenly-palm:novice"],
            "teacher": "Elder Qing",
            "breakthrough": "Cloud Palm",
            "notes": "Linked training branch",
        },
        {
            "name": "Unlisted Fist",
            "rank": "Novice",
            "teacher": "Wandering monk",
            "breakthrough": "Wind Step",
            "notes": "Manual import",
            "source_notes": "House record",
        },
    ]

    definition, _, _ = build_xianxia_manual_import_character(payload)

    martial_arts = definition.xianxia["martial_arts"]
    assert len(martial_arts) == 2
    linked = martial_arts[0]
    assert linked["systems_ref"]["slug"] == "heavenly-palm"
    assert linked["current_rank_key"] == "initiate"
    assert linked["learned_rank_refs"] == [
        "xianxia:heavenly-palm:initiate",
        "xianxia:heavenly-palm:novice",
    ]
    assert linked["teacher"] == "Elder Qing"

    unlinked = martial_arts[1]
    assert unlinked["name"] == "Unlisted Fist"
    assert "systems_ref" not in unlinked
    assert unlinked["current_rank_key"] == "novice"
    assert unlinked["notes"] == "Manual import"
    assert unlinked["teacher"] == "Wandering monk"
    assert unlinked["breakthrough"] == "Wind Step"


def test_manual_importer_links_selected_stored_martial_art_without_manual_name():
    payload = _base_payload()
    payload.update(
        {
            "martial_art_1_slug": "heavenly-palm",
            "martial_art_1_rank": "Master",
            "martial_art_1_teacher": "Elder Qing",
            "martial_art_1_breakthrough": "Storm crown",
        }
    )
    martial_art_options = [
        {
            "slug": "heavenly-palm",
            "title": "Heavenly Palm",
            "entry_key": "xianxia-homebrew:martial-art:heavenly-palm",
            "entry_type": "martial_art",
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "library_slug": "xianxia",
            "rank_refs": {
                "initiate": "xianxia:heavenly-palm:initiate",
                "novice": "xianxia:heavenly-palm:novice",
                "apprentice": "xianxia:heavenly-palm:apprentice",
                "master": "xianxia:heavenly-palm:master",
            },
        }
    ]

    definition, _, _ = build_xianxia_manual_import_character(
        payload,
        martial_art_options=martial_art_options,
    )

    linked_art = definition.xianxia["martial_arts"][0]
    assert linked_art["name"] == "Heavenly Palm"
    assert linked_art["systems_ref"]["slug"] == "heavenly-palm"
    assert linked_art["current_rank_key"] == "master"
    assert linked_art["current_rank"] == "Master"
    assert linked_art["learned_rank_refs"] == [
        "xianxia:heavenly-palm:initiate",
        "xianxia:heavenly-palm:novice",
        "xianxia:heavenly-palm:apprentice",
        "xianxia:heavenly-palm:master",
    ]
    assert linked_art["teacher"] == "Elder Qing"
    assert linked_art["breakthrough"] == "Storm crown"


def test_manual_importer_preserves_inventory_rows_with_notes_and_tags():
    payload = _base_payload()
    payload["state"] = {
        "xianxia": {
            "inventory": {
                "quantities": [
                    {
                        "name": "Spirit Rice",
                        "quantity": 3,
                        "notes": "Emergency cache",
                        "tags": ["ritual", "fragile"],
                    },
                    {
                        "name": "Field Rations",
                        "quantity": "2",
                    },
                ]
            }
        }
    }

    _, _, initial_state = build_xianxia_manual_import_character(payload)

    inventory = initial_state["xianxia"]["inventory"]["quantities"]
    assert initial_state["xianxia"]["inventory"]["enabled"] is True
    assert inventory[0]["name"] == "Spirit Rice"
    assert inventory[0]["quantity"] == 3
    assert inventory[0]["notes"] == "Emergency cache"
    assert inventory[0]["tags"] == ["ritual", "fragile"]
    assert inventory[0]["item_type"] == "Miscellaneous"
    assert inventory[0]["item_nature"] == "Mundane"
    assert inventory[0]["legacy_tags"] == ["ritual", "fragile"]
    assert inventory[1]["name"] == "Field Rations"
    assert inventory[1]["quantity"] == 2
    assert inventory[1]["item_type"] == "Miscellaneous"
    assert inventory[1]["item_nature"] == "Mundane"


def test_xianxia_manual_import_route_previews_then_creates_native_sheet(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    assert roster.status_code == 200
    assert "Import existing character" in roster.get_data(as_text=True)

    import_page = client.get("/campaigns/linden-pass/characters/import/xianxia-manual")
    assert import_page.status_code == 200
    import_page_html = import_page.get_data(as_text=True)
    assert "Import Existing Xianxia Character" in import_page_html
    assert "Stored Martial Art" in import_page_html
    assert "Heavenly Palm" in import_page_html
    assert "Add Martial Art" in import_page_html
    assert 'name="active_stance"' not in import_page_html
    assert 'name="active_aura"' not in import_page_html

    preview = client.post(
        "/campaigns/linden-pass/characters/import/xianxia-manual",
        data=_manual_import_form_data(),
    )
    assert preview.status_code == 200
    preview_html = preview.get_data(as_text=True)
    assert "Review Import" in preview_html
    assert "Imported Lotus" in preview_html
    assert "Confirm import" in preview_html
    assert 'name="current_hp"' not in preview_html
    assert 'name="temp_hp"' not in preview_html
    assert 'name="current_stance"' not in preview_html
    assert 'name="temp_stance"' not in preview_html
    assert 'name="current_yin"' not in preview_html
    assert 'name="current_yang"' not in preview_html
    assert 'name="current_dao"' not in preview_html
    assert 'name="active_stance"' not in preview_html
    assert 'name="active_aura"' not in preview_html
    for energy in ("jing", "qi", "shen"):
        assert f'name="current_{energy}"' not in preview_html

    create_response = client.post(
        "/campaigns/linden-pass/characters/import/xianxia-manual",
        data={**_manual_import_form_data(), "confirm_import": "1"},
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/imported-lotus"
    )

    definition = _read_character_definition(app, "imported-lotus")
    xianxia = definition["xianxia"]
    assert definition["source"]["source_path"] == XIANXIA_MANUAL_IMPORTER_SOURCE_PATH
    assert definition["source"]["source_type"] == XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["attributes"]["str"] == 9
    assert xianxia["efforts"]["ultimate"] == 7
    assert xianxia["durability"]["hp_max"] == 19
    assert xianxia["durability"]["stance_max"] == 17
    assert xianxia["energies"]["jing"]["max"] == 5
    assert xianxia["yin_yang"]["yang_max"] == 10
    assert xianxia["dao"]["max"] == 3
    assert xianxia["skills"]["trained"] == [
        "Tea Ceremony",
        "Qi Sense",
        "Sky Calling",
        "Blade Focus",
    ]

    linked_art = xianxia["martial_arts"][0]
    assert linked_art["name"] == "Heavenly Palm"
    assert linked_art["systems_ref"]["slug"] == "heavenly-palm"
    assert linked_art["current_rank_key"] == "novice"
    assert linked_art["learned_rank_refs"] == [
        "xianxia:heavenly-palm:initiate",
        "xianxia:heavenly-palm:novice",
    ]
    assert linked_art["teacher"] == "Elder Qing"

    manual_art = xianxia["martial_arts"][1]
    assert manual_art["name"] == "Unlisted Fist"
    assert "systems_ref" not in manual_art
    assert manual_art["current_rank_key"] == "apprentice"
    assert manual_art["breakthrough"] == "Wind step"

    record = _get_character_record(app, "imported-lotus")
    state = record.state_record.state
    assert state["vitals"] == {"current_hp": 19, "temp_hp": 0}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 19,
        "temp_hp": 0,
        "current_stance": 17,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"]["shen"] == {"current": 7}
    assert state["xianxia"]["yin_yang"] == {"yin_current": 9, "yang_current": 10}
    assert state["xianxia"]["dao"] == {"current": 0}
    assert state["xianxia"]["currency"] == {
        "coin": 12,
        "supply": 3,
        "spirit_stones": 2,
    }
    assert state["xianxia"]["notes"] == {
        "player_notes_markdown": "Keep an eye on the spirit rice."
    }
    assert state["xianxia"].get("active_stance") is None
    assert state["xianxia"].get("active_aura") is None
    state_inventory_row = state["xianxia"]["inventory"]["quantities"][0]
    assert state_inventory_row["name"] == "Spirit rice"
    assert state_inventory_row["quantity"] == 3
    assert state_inventory_row["notes"] == "Emergency cache"
    assert state_inventory_row["tags"] == ["consumable", "treasure"]
    assert state_inventory_row["item_type"] == "Consumable"
    assert state_inventory_row["item_nature"] == "Mundane"
    assert "legacy_tags" not in state_inventory_row
    assert state["inventory"][0]["tags"] == ["consumable", "treasure"]

    martial_html = unescape(
        client.get(
            "/campaigns/linden-pass/characters/imported-lotus?page=martial_arts"
        ).get_data(as_text=True)
    )
    assert "Heavenly Palm" in martial_html
    assert "Novice" in martial_html
    assert "Unlisted Fist" in martial_html

    inventory_html = unescape(
        client.get(
            "/campaigns/linden-pass/characters/imported-lotus?page=inventory"
        ).get_data(as_text=True)
    )
    assert "Spirit rice" in inventory_html
    assert "consumable, treasure" in inventory_html
    assert "Emergency cache" in inventory_html
    assert "Coin" in inventory_html
    assert "Supply" in inventory_html
    assert "Spirit Stones" in inventory_html
    assert "Out of battle: gain +1 Insight. In battle: restore ALL Energy." in inventory_html

    session_html = client.get(
        "/campaigns/linden-pass/characters/imported-lotus?mode=session&page=resources"
    ).get_data(as_text=True)
    assert "Current 19 / Max 19" in session_html


def test_xianxia_manual_import_route_ignores_stale_mutable_inputs(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    base_payload = _manual_import_form_data()
    stale_payload = {
        **base_payload,
        "character_slug": "imported-lotus-stale",
        "current_hp": "99",
        "temp_hp": "11",
        "current_stance": "88",
        "temp_stance": "9",
        "current_yin": "111",
        "current_yang": "111",
        "current_jing": "111",
        "current_qi": "111",
        "current_shen": "111",
        "current_dao": "111",
        "active_stance": "Stone Root",
        "active_aura": "Crane Halo",
        "energy_jing_max": "5",
        "energy_qi_max": "6",
        "energy_shen_max": "7",
    }
    response = client.post(
        "/campaigns/linden-pass/characters/import/xianxia-manual",
        data={**stale_payload, "confirm_import": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/imported-lotus-stale"
    )

    record = _get_character_record(app, "imported-lotus-stale")
    state = record.state_record.state
    definition = _read_character_definition(app, "imported-lotus-stale")

    assert definition["xianxia"]["durability"]["hp_max"] == 19
    assert definition["xianxia"]["durability"]["stance_max"] == 17
    assert definition["xianxia"]["energies"]["jing"]["max"] == 5
    assert definition["xianxia"]["energies"]["qi"]["max"] == 6
    assert definition["xianxia"]["energies"]["shen"]["max"] == 7
    assert definition["xianxia"]["yin_yang"]["yin_max"] == 9
    assert definition["xianxia"]["yin_yang"]["yang_max"] == 10

    assert state["vitals"] == {"current_hp": 19, "temp_hp": 0}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 19,
        "temp_hp": 0,
        "current_stance": 17,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 5},
        "qi": {"current": 6},
        "shen": {"current": 7},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 9, "yang_current": 10}
    assert state["xianxia"]["dao"] == {"current": 0}
    assert state["xianxia"]["currency"] == {
        "coin": 12,
        "supply": 3,
        "spirit_stones": 2,
    }
    assert state["xianxia"].get("active_stance") is None
    assert state["xianxia"].get("active_aura") is None


def test_xianxia_manual_import_route_requires_character_management_access(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/characters/import/xianxia-manual")

    assert response.status_code == 404


def test_xianxia_manual_import_route_is_hidden_for_dnd5e_campaigns(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    assert roster.status_code == 200
    assert "Import existing character" not in roster.get_data(as_text=True)

    response = client.get(
        "/campaigns/linden-pass/characters/import/xianxia-manual",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters")
