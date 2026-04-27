from __future__ import annotations

from html import unescape

import yaml

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


def _valid_xianxia_create_data(name: str, *, slug: str = "") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": slug,
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


def _character_state_revision(app, character_slug: str) -> int:
    return int(_get_character_record(app, character_slug).state_record.revision)


def _post_cultivation(client, app, character_slug: str, data: dict[str, str]):
    response = client.post(
        f"/campaigns/linden-pass/characters/{character_slug}/cultivation",
        data={
            "expected_revision": str(_character_state_revision(app, character_slug)),
            **data,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response


def test_xianxia_milestone1_character_create_and_read_routes_cover_system_lane(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_page = client.get("/campaigns/linden-pass/characters/new")
    assert create_page.status_code == 200
    create_html = create_page.get_data(as_text=True)
    assert "Xianxia Character" in create_html
    assert "Native Level 1 Builder" not in create_html
    assert "Spell Preview" not in create_html

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Milestone Crane"),
            "manual_armor_bonus": "1",
            "dao_current": "1",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/milestone-crane"
    )

    definition = _read_character_definition(app, "milestone-crane")
    xianxia = definition["xianxia"]
    assert definition["system"] == XIANXIA_SYSTEM_CODE
    assert xianxia["realm"] == "Mortal"
    assert xianxia["actions_per_turn"] == 2
    assert xianxia["durability"] == {
        "hp_max": 10,
        "stance_max": 10,
        "manual_armor_bonus": 1,
        "defense": 14,
    }
    assert [art["current_rank_key"] for art in xianxia["martial_arts"]] == [
        "initiate",
        "initiate",
        "initiate",
    ]
    assert xianxia["generic_techniques"] == []

    record = _get_character_record(app, "milestone-crane")
    state = record.state_record.state
    assert state["spell_slots"] == []
    assert state["resources"] == []
    assert state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 10,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert state["xianxia"]["dao"] == {"current": 1}

    quick_html = unescape(
        client.get("/campaigns/linden-pass/characters/milestone-crane?page=quick").get_data(
            as_text=True
        )
    )
    assert "Actions per turn" in quick_html
    assert "Defense calculation" in quick_html
    assert "Spellcasting" not in quick_html

    martial_html = unescape(
        client.get(
            "/campaigns/linden-pass/characters/milestone-crane?page=martial_arts"
        ).get_data(as_text=True)
    )
    assert "Demon's Fist" in martial_html
    assert "Heavenly Palm" in martial_html
    assert "Taoist Blade" in martial_html
    assert "/campaigns/linden-pass/systems/entries/demons-fist" in martial_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/milestone-crane?page=resources"
    ).get_data(as_text=True)
    assert "<h3>HP</h3>" in resources_html
    assert "Current 10 / Max 10" in resources_html
    assert "Current 1 / Max 3" in resources_html


def test_xianxia_milestone1_session_state_writes_and_one_day_rest_recovery(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data("Session Rest Crane"), "dao_current": "2"},
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    session_page = client.get(
        "/campaigns/linden-pass/session/character?character=session-rest-crane&page=resources"
    )
    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'id="session-vitals"' in session_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in session_html

    record = _get_character_record(app, "session-rest-crane")
    vitals_response = client.post(
        "/campaigns/linden-pass/characters/session-rest-crane/session/vitals",
        data={
            "expected_revision": str(record.state_record.revision),
            "current_hp": "4",
            "temp_hp": "1",
            "current_stance": "3",
            "temp_stance": "2",
            "current_jing": "0",
            "current_qi": "0",
            "current_shen": "0",
            "current_yin": "0",
            "current_yang": "0",
            "current_dao": "2",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    assert vitals_response.status_code == 302

    updated = _get_character_record(app, "session-rest-crane")
    assert updated.state_record.state["vitals"] == {"current_hp": 4, "temp_hp": 1}
    assert updated.state_record.state["xianxia"]["vitals"] == {
        "current_hp": 4,
        "temp_hp": 1,
        "current_stance": 3,
        "temp_stance": 2,
    }
    assert updated.state_record.state["xianxia"]["energies"] == {
        "jing": {"current": 0},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    assert updated.state_record.state["xianxia"]["yin_yang"] == {
        "yin_current": 0,
        "yang_current": 0,
    }
    assert updated.state_record.state["xianxia"]["dao"] == {"current": 2}

    notes_response = client.post(
        "/campaigns/linden-pass/characters/session-rest-crane/session/notes",
        data={
            "expected_revision": str(updated.state_record.revision),
            "player_notes_markdown": "Watch for recovery blockers.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    assert notes_response.status_code == 302

    noted = _get_character_record(app, "session-rest-crane")
    assert noted.state_record.state["notes"]["player_notes_markdown"] == (
        "Watch for recovery blockers."
    )
    assert noted.state_record.state["xianxia"]["notes"] == {
        "player_notes_markdown": "Watch for recovery blockers."
    }

    rest_response = client.post(
        "/campaigns/linden-pass/characters/session-rest-crane/session/rest/long",
        data={
            "expected_revision": str(noted.state_record.revision),
            "confirm_rest": "1",
        },
        follow_redirects=False,
    )
    assert rest_response.status_code == 302

    rested = _get_character_record(app, "session-rest-crane")
    rested_state = rested.state_record.state
    assert rested_state["vitals"] == {"current_hp": 10, "temp_hp": 1}
    assert rested_state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 1,
        "current_stance": 10,
        "temp_stance": 2,
    }
    assert rested_state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert rested_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert rested_state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_milestone1_advancement_records_core_insight_spends(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        systems_service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        qi_blast = systems_service.get_entry_by_slug_for_campaign("linden-pass", "qi-blast")
        assert qi_blast is not None

    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Advancement Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "save_insight",
            "insight_available": "6",
            "insight_spent": "0",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "qi",
            "cultivation_energy_notes": "Opened the inner breath gate.",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yin",
            "meditation_notes": "Balanced the moon aspect.",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "hp",
            "conditioning_notes": "Stone-body conditioning.",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "spend_training",
            "training_target": "stance",
            "training_notes": "Waterfall stance drills.",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": qi_blast.entry_key,
            "generic_technique_notes": "Learned through focused breath.",
        },
    )
    _post_cultivation(
        client,
        app,
        "advancement-crane",
        {
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "novice",
        },
    )

    definition = _read_character_definition(app, "advancement-crane")
    xianxia = definition["xianxia"]
    assert xianxia["insight"] == {"available": 0, "spent": 6}
    assert xianxia["energies"] == {
        "jing": {"max": 2},
        "qi": {"max": 3},
        "shen": {"max": 1},
    }
    assert xianxia["yin_yang"] == {"yin_max": 2, "yang_max": 1}
    assert xianxia["durability"]["hp_max"] == 20
    assert xianxia["durability"]["stance_max"] == 20
    assert xianxia["martial_arts"][0]["current_rank_key"] == "novice"
    assert xianxia["generic_techniques"][0]["generic_technique_key"] == "qi_blast"

    assert [event["action"] for event in xianxia["advancement_history"]] == [
        "insight_counter_adjustment",
        "cultivation_energy_increase",
        "meditation_yin_yang_increase",
        "conditioning_hp_increase",
        "training_stance_increase",
        "generic_technique_learned",
        "martial_art_rank_advance",
    ]

    record = _get_character_record(app, "advancement-crane")
    state = record.state_record.state["xianxia"]
    assert record.state_record.state["vitals"]["current_hp"] == 10
    assert state["vitals"]["current_stance"] == 10
    assert state["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert state["yin_yang"] == {"yin_current": 1, "yang_current": 1}

    techniques_html = client.get(
        "/campaigns/linden-pass/characters/advancement-crane?page=techniques"
    ).get_data(as_text=True)
    assert "Qi Blast" in techniques_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in techniques_html
