from __future__ import annotations

from copy import deepcopy
from html import unescape

import yaml

from player_wiki.xianxia_character_model import derive_xianxia_difficulty_state_adjustments
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


def _replace_character_state(app, record, state: dict) -> None:
    with app.app_context():
        app.extensions["character_state_store"].replace_state(
            record.definition,
            state,
            expected_revision=record.state_record.revision,
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
    assert "Check formula" in html
    assert "1d20 + Attribute + Realm modifier + situational modifiers" in html
    assert "+1d6" in html
    assert "per spent Energy/Yin/Yang point" in html
    assert (
        "Check formula = 1d20 + Attribute + Realm modifier + situational modifiers, "
        "plus +1d6 per spent Energy/Yin/Yang point."
    ) in html
    assert "Difficulty states" in html
    assert "Difficulty states = EASY -3, Normal 0, HARD +3." in html
    assert "Final DC adjustment" in html
    assert "<strong>-3</strong>" in html
    assert "<strong>0</strong>" in html
    assert "<strong>+3</strong>" in html
    assert "Resolve EASY/HARD influences to one final DC state" in html
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


def test_xianxia_difficulty_state_helper_presents_capped_final_dc_states():
    presentation = derive_xianxia_difficulty_state_adjustments()

    assert presentation["summary"] == "EASY -3, Normal 0, HARD +3"
    assert presentation["states"] == [
        {"key": "easy", "label": "EASY", "adjustment": -3, "adjustment_label": "-3"},
        {"key": "normal", "label": "Normal", "adjustment": 0, "adjustment_label": "0"},
        {"key": "hard", "label": "HARD", "adjustment": 3, "adjustment_label": "+3"},
    ]


def test_xianxia_dao_persists_across_session_surface_saves_and_rests(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data("Dao Keeper"), "dao_current": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    record = get_character("dao-keeper")
    assert record is not None
    assert record.state_record.state["xianxia"]["dao"] == {"current": 2}

    session_response = client.get(
        "/campaigns/linden-pass/session/character?character=dao-keeper&page=quick"
    )

    assert session_response.status_code == 200
    record_after_session_read = get_character("dao-keeper")
    assert record_after_session_read.state_record.revision == record.state_record.revision
    assert record_after_session_read.state_record.state["xianxia"]["dao"] == {"current": 2}

    vitals_response = client.post(
        "/campaigns/linden-pass/characters/dao-keeper/session/vitals",
        data={
            "expected_revision": record_after_session_read.state_record.revision,
            "current_hp": "7",
            "temp_hp": "1",
        },
        follow_redirects=False,
    )

    assert vitals_response.status_code == 302
    record_after_vitals = get_character("dao-keeper")
    assert record_after_vitals.state_record.state["vitals"] == {"current_hp": 7, "temp_hp": 1}
    assert record_after_vitals.state_record.state["xianxia"]["vitals"]["current_hp"] == 7
    assert record_after_vitals.state_record.state["xianxia"]["dao"] == {"current": 2}

    for rest_type in ("short", "long"):
        rest_response = client.post(
            f"/campaigns/linden-pass/characters/dao-keeper/session/rest/{rest_type}",
            data={
                "expected_revision": record_after_vitals.state_record.revision,
                "confirm_rest": "1",
            },
            follow_redirects=False,
        )

        assert rest_response.status_code == 302
        record_after_vitals = get_character("dao-keeper")
        assert record_after_vitals.state_record.state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_one_day_rest_recovers_mutable_pools_and_preserves_dao(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data("Resting Crane"), "dao_current": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    record = get_character("resting-crane")
    assert record is not None

    depleted_state = deepcopy(record.state_record.state)
    depleted_state["vitals"] = {"current_hp": 4, "temp_hp": 2}
    depleted_state["xianxia"]["vitals"] = {
        "current_hp": 4,
        "temp_hp": 2,
        "current_stance": 3,
        "temp_stance": 5,
    }
    depleted_state["xianxia"]["energies"] = {
        "jing": {"current": 0},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    depleted_state["xianxia"]["yin_yang"] = {"yin_current": 0, "yang_current": 0}
    depleted_state["xianxia"]["dao"] = {"current": 2}
    _replace_character_state(app, record, depleted_state)

    depleted_record = get_character("resting-crane")
    assert depleted_record is not None

    with app.app_context():
        preview = app.extensions["character_state_service"].preview_rest(depleted_record, "long")
    preview_changes = {
        change.label: (change.from_value, change.to_value)
        for change in preview.changes
    }

    assert preview_changes == {
        "HP": ("4 / 10", "10 / 10"),
        "Stance": ("3 / 10", "10 / 10"),
        "Jing Energy": ("0 / 1", "1 / 1"),
        "Qi Energy": ("0 / 1", "1 / 1"),
        "Shen Energy": ("0 / 1", "1 / 1"),
        "Yin": ("0 / 1", "1 / 1"),
        "Yang": ("0 / 1", "1 / 1"),
    }

    rest_response = client.post(
        "/campaigns/linden-pass/characters/resting-crane/session/rest/long",
        data={
            "expected_revision": depleted_record.state_record.revision,
            "confirm_rest": "1",
        },
        follow_redirects=False,
    )

    assert rest_response.status_code == 302
    rested_record = get_character("resting-crane")
    rested_state = rested_record.state_record.state
    assert rested_state["vitals"] == {"current_hp": 10, "temp_hp": 2}
    assert rested_state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 2,
        "current_stance": 10,
        "temp_stance": 5,
    }
    assert rested_state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert rested_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert rested_state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_quick_reference_displays_stance_break_only_at_zero_stance(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Broken Stance"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    normal_response = client.get("/campaigns/linden-pass/characters/broken-stance?page=quick")

    assert normal_response.status_code == 200
    normal_html = unescape(normal_response.get_data(as_text=True))
    assert "Stance Break" not in normal_html

    record = get_character("broken-stance")
    assert record is not None
    broken_state = deepcopy(record.state_record.state)
    broken_state["xianxia"]["vitals"]["current_stance"] = 0
    _replace_character_state(app, record, broken_state)

    broken_response = client.get("/campaigns/linden-pass/characters/broken-stance?page=quick")

    assert broken_response.status_code == 200
    broken_html = unescape(broken_response.get_data(as_text=True))
    assert "Stance Break" in broken_html
    assert "Current Stance 0" in broken_html
    assert "/campaigns/linden-pass/systems/entries/stance" in broken_html
    assert "When current Stance reaches 0, the character's Stance breaks." in broken_html
    assert "Stance recovers with one day of rest unless another effect prevents recovery." in broken_html
