from __future__ import annotations

from html import unescape

import yaml

from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID


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


def _valid_xianxia_create_data(name: str = "Armored Crane") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": "",
        "attribute_str": "3",
        "attribute_dex": "0",
        "attribute_con": "3",
        "attribute_int": "0",
        "attribute_wis": "0",
        "attribute_cha": "0",
        "effort_basic": "3",
        "effort_weapon": "1",
        "effort_guns_explosive": "0",
        "effort_magic": "1",
        "effort_ultimate": "0",
        "energy_jing": "1",
        "energy_qi": "1",
        "energy_shen": "1",
        "trained_skill_1": "Fishing",
        "trained_skill_2": "Calligraphy",
        "trained_skill_3": "Tea Ceremony",
        "martial_art_1_slug": "demons-fist",
        "martial_art_1_rank": "initiate",
        "martial_art_2_slug": "heavenly-palm",
        "martial_art_2_rank": "initiate",
        "martial_art_3_slug": "taoist-blade",
        "martial_art_3_rank": "initiate",
    }


def _write_raw_xianxia_character_definition(app, character_slug: str, definition_payload: dict) -> None:
    character_dir = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
    )
    character_dir.mkdir(parents=True, exist_ok=True)
    (character_dir / "definition.yaml").write_text(
        yaml.safe_dump(definition_payload, sort_keys=False),
        encoding="utf-8",
    )
    (character_dir / "import.yaml").write_text(
        yaml.safe_dump(
            {
                "campaign_slug": "linden-pass",
                "character_slug": character_slug,
                "source_path": "test://xianxia-realm-actions",
                "imported_at_utc": "2026-04-26T00:00:00Z",
                "parser_version": "test",
                "import_status": "ok",
                "warnings": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_xianxia_quick_reference_presents_derived_defense(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data(), "manual_armor_bonus": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/armored-crane"
    )

    sheet_response = client.get("/campaigns/linden-pass/characters/armored-crane?page=quick")

    assert sheet_response.status_code == 200
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Action count" in html
    assert "Actions per turn" in html
    assert "Actions per turn = Mortal -> 2 actions per turn" in html
    assert "Defense calculation" in html
    assert "Manual armor bonus" in html
    assert "Constitution" in html
    assert "Defense = 10 + 2 + 3" in html
    assert "<strong>15</strong>" in html
    assert "Effort damage" in html
    assert "1d4 + Basic" in html
    assert "1d6 + Weapon" in html
    assert "1d8 + Guns/Explosive" in html
    assert "1d10 + Magic" in html
    assert "1d12 + Ultimate" in html
    assert "Score 3" in html
    assert "Armor Class" not in html


def test_xianxia_quick_reference_derives_actions_from_realm_not_stored_value(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    _write_raw_xianxia_character_definition(
        app,
        "divine-stale-actions",
        {
            "campaign_slug": "linden-pass",
            "character_slug": "divine-stale-actions",
            "name": "Divine Stale Actions",
            "status": "active",
            "system": "Xianxia",
            "xianxia": {
                "realm": "Divine",
                "actions_per_turn": 2,
                "attributes": {
                    "str": 0,
                    "dex": 0,
                    "con": 2,
                    "int": 0,
                    "wis": 0,
                    "cha": 0,
                },
                "durability": {"manual_armor_bonus": 1},
            },
        },
    )

    sheet_response = client.get("/campaigns/linden-pass/characters/divine-stale-actions?page=quick")

    assert sheet_response.status_code == 200
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Action count" in html
    assert "Actions per turn = Divine -> 4 actions per turn" in html
    assert "<strong>Divine</strong>" in html
    assert "<strong>4</strong>" in html
