from __future__ import annotations

from html import unescape

import yaml

import pytest

from player_wiki.system_policy import XIANXIA_SYSTEM_CODE
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


def _read_character_definition(app, character_slug: str) -> dict:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    return yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}


def _valid_xianxia_create_data(name: str = "Lotus Wake") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": "",
        "attribute_str": "3",
        "attribute_dex": "1",
        "attribute_con": "1",
        "attribute_int": "1",
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


def test_xianxia_create_flow_accepts_valid_budgets_and_persists_inferred_gear(
    app, client, sign_in, users, get_character
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Budgeted Crane"),
            "manual_armor_bonus": "2",
            "generic_techniques": "Qi Blast",
            "starting_armor": "Silk lamellar",
            "starting_supplies": "Spirit rice",
            "starting_coin": "100 gp",
            "non_required_gear": "Travel lantern",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/budgeted-crane"
    )

    definition = _read_character_definition(app, "budgeted-crane")
    xianxia = definition["xianxia"]
    assert definition["system"] == XIANXIA_SYSTEM_CODE
    assert xianxia["attributes"] == {
        "str": 3,
        "dex": 1,
        "con": 1,
        "int": 1,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 3,
        "weapon": 1,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    assert xianxia["energies"] == {
        "jing": {"max": 1},
        "qi": {"max": 1},
        "shen": {"max": 1},
    }
    assert xianxia["durability"] == {
        "hp_max": 10,
        "stance_max": 10,
        "manual_armor_bonus": 2,
        "defense": 13,
    }
    assert [record["current_rank_key"] for record in xianxia["martial_arts"]] == [
        "initiate",
        "initiate",
        "initiate",
    ]
    assert xianxia["equipment"] == {
        "necessary_weapons": [{"name": "Jian", "reason": "Required by Taoist Blade"}],
        "necessary_tools": [
            {"name": "Fishing rod, spear, or net", "reason": "Required for Fishing"},
            {"name": "Calligraphy brush", "reason": "Required for Calligraphy"},
            {"name": "Tea set", "reason": "Required for Tea Ceremony"},
        ],
    }
    assert xianxia["generic_techniques"] == []
    assert definition["spellcasting"] == {}
    assert definition["attacks"] == []
    assert definition["features"] == []
    assert definition["equipment_catalog"] == []

    record = get_character("budgeted-crane")
    assert record is not None
    state = record.state_record.state
    assert state["spell_slots"] == []
    assert state["resources"] == []
    assert state["inventory"] == []
    assert state["currency"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []}
    assert state["xianxia"]["inventory"] == {"enabled": False, "quantities": []}


@pytest.mark.parametrize(
    ("name", "overrides", "expected_message"),
    [
        (
            "Attribute Underbudget",
            {"attribute_str": "2"},
            "Xianxia Attributes must spend exactly 6 creation points; submitted total is 5.",
        ),
        (
            "Attribute Overcap",
            {"attribute_str": "4", "attribute_dex": "0"},
            "Strength cannot exceed 3 at character creation.",
        ),
        (
            "Effort Overbudget",
            {"effort_ultimate": "1"},
            "Xianxia Efforts must spend exactly 5 creation points; submitted total is 6.",
        ),
        (
            "Effort Overcap",
            {"effort_basic": "4", "effort_weapon": "0"},
            "Basic cannot exceed 3 at character creation.",
        ),
        (
            "Energy Underbudget",
            {"energy_shen": "0"},
            "Xianxia Energies must spend exactly 3 creation points across Jing, Qi, and Shen; "
            "submitted total is 2.",
        ),
    ],
)
def test_xianxia_create_flow_rejects_invalid_creation_budgets(
    app, client, sign_in, users, name, overrides, expected_message
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    data = _valid_xianxia_create_data(name)
    data.update(overrides)

    response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert expected_message in unescape(response.get_data(as_text=True))


@pytest.mark.parametrize(
    ("name", "martial_art_fields", "expected_message"),
    [
        (
            "No Starting Arts",
            {
                "martial_art_1_slug": "",
                "martial_art_1_rank": "",
                "martial_art_2_slug": "",
                "martial_art_2_rank": "",
                "martial_art_3_slug": "",
                "martial_art_3_rank": "",
            },
            "Xianxia character creation requires a starting Martial Arts package: "
            "one Novice plus one Initiate, or three Initiates.",
        ),
        (
            "Two Initiates",
            {
                "martial_art_1_slug": "demons-fist",
                "martial_art_1_rank": "initiate",
                "martial_art_2_slug": "heavenly-palm",
                "martial_art_2_rank": "initiate",
                "martial_art_3_slug": "",
                "martial_art_3_rank": "",
            },
            "Starting Martial Arts must be one Novice plus one Initiate, or three Initiates.",
        ),
        (
            "Novice Plus Two Initiates",
            {
                "martial_art_1_slug": "demons-fist",
                "martial_art_1_rank": "novice",
                "martial_art_2_slug": "heavenly-palm",
                "martial_art_2_rank": "initiate",
                "martial_art_3_slug": "taoist-blade",
                "martial_art_3_rank": "initiate",
            },
            "Starting Martial Arts must be one Novice plus one Initiate, or three Initiates.",
        ),
        (
            "Duplicate Arts",
            {
                "martial_art_1_slug": "demons-fist",
                "martial_art_1_rank": "novice",
                "martial_art_2_slug": "demons-fist",
                "martial_art_2_rank": "initiate",
                "martial_art_3_slug": "",
                "martial_art_3_rank": "",
            },
            "Starting Martial Arts must be distinct; duplicates: Demon's Fist.",
        ),
        (
            "Unknown Art",
            {
                "martial_art_1_slug": "missing-art",
                "martial_art_1_rank": "novice",
                "martial_art_2_slug": "heavenly-palm",
                "martial_art_2_rank": "initiate",
                "martial_art_3_slug": "",
                "martial_art_3_rank": "",
            },
            "Unsupported starting Martial Art: missing-art.",
        ),
        (
            "Unavailable Novice",
            {
                "martial_art_1_slug": "rippling-melodies",
                "martial_art_1_rank": "novice",
                "martial_art_2_slug": "heavenly-palm",
                "martial_art_2_rank": "initiate",
                "martial_art_3_slug": "",
                "martial_art_3_rank": "",
            },
            "Rippling Melodies does not have Novice rank available in Systems metadata.",
        ),
    ],
)
def test_xianxia_create_flow_rejects_illegal_starting_martial_art_packages(
    app, client, sign_in, users, name, martial_art_fields, expected_message
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    data = _valid_xianxia_create_data(name)
    data.update(martial_art_fields)

    response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert expected_message in unescape(response.get_data(as_text=True))


def test_xianxia_create_flow_stays_isolated_from_dnd5e_builder_fields(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dnd_response = client.get("/campaigns/linden-pass/characters/new")
    assert dnd_response.status_code == 200
    dnd_html = dnd_response.get_data(as_text=True)
    assert "Native Level 1 Builder" in dnd_html
    assert "Create Echoes of the Alloy Coast Xianxia Character" not in dnd_html

    _configure_xianxia_campaign(app)

    xianxia_response = client.get("/campaigns/linden-pass/characters/new")
    assert xianxia_response.status_code == 200
    xianxia_html = xianxia_response.get_data(as_text=True)
    assert "Create Echoes of the Alloy Coast Xianxia Character" in xianxia_html
    assert "Native Level 1 Builder" not in xianxia_html
    assert "Spell Preview" not in xianxia_html
    assert 'name="class_slug"' not in xianxia_html
    assert 'name="species_slug"' not in xianxia_html
    assert 'name="background_slug"' not in xianxia_html

    submit_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Isolated Willow"),
            "class_slug": "phb-class-wizard",
            "species_slug": "phb-race-elf",
            "background_slug": "phb-background-acolyte",
            "spell_1": "phb-spell-magic-missile",
        },
        follow_redirects=False,
    )

    assert submit_response.status_code == 302
    definition = _read_character_definition(app, "isolated-willow")
    assert definition["system"] == XIANXIA_SYSTEM_CODE
    assert definition["profile"]["class_level_text"] == "Mortal Xianxia Character"
    assert definition["spellcasting"] == {}
    assert definition["proficiencies"] == {
        "armor": [],
        "weapons": [],
        "tools": [],
        "languages": [],
        "tool_expertise": [],
    }
    assert definition["attacks"] == []
    assert definition["features"] == []
    assert definition["equipment_catalog"] == []
