from __future__ import annotations


def test_owner_player_can_update_mutable_state(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/vitals",
        data={"expected_revision": record.state_record.revision, "current_hp": 35, "temp_hp": 4},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    assert record.state_record.state["vitals"]["current_hp"] == 35
    assert record.state_record.state["vitals"]["temp_hp"] == 4

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 3},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    assert resources["sorcery-points"]["current"] == 3

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 2

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/inventory/crossbow-bolts-4",
        data={"expected_revision": record.state_record.revision, "quantity": 18},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    inventory = {item["id"]: item for item in record.state_record.state["inventory"]}
    assert inventory["crossbow-bolts-4"]["quantity"] == 18

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/currency",
        data={
            "expected_revision": record.state_record.revision,
            "cp": 0,
            "sp": 7,
            "ep": 0,
            "gp": 125,
            "pp": 0,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    assert record.state_record.state["currency"]["gp"] == 125
    assert record.state_record.state["currency"]["sp"] == 7

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/notes",
        data={
            "expected_revision": record.state_record.revision,
            "player_notes_markdown": "Session note test",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    assert record.state_record.state["notes"]["player_notes_markdown"] == "Session note test"


def test_long_rest_preview_and_apply_reset_modeled_state(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    client.post(
        "/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 2},
        follow_redirects=False,
    )
    record = get_character("arden-march")
    client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )

    preview = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&confirm_rest=long")
    assert preview.status_code == 200
    preview_html = preview.get_data(as_text=True)
    assert "Long Rest confirmation" in preview_html
    assert "Sorcery Points" in preview_html
    assert "2nd level spell slots" in preview_html

    record = get_character("arden-march")
    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/rest/long",
        data={"expected_revision": record.state_record.revision, "confirm_rest": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert resources["sorcery-points"]["current"] == 5
    assert spell_slots[2]["used"] == 0


def test_stale_revision_is_rejected(client, sign_in, users, get_character, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/resources/wild-die",
        data={"expected_revision": stale_revision, "current": 1},
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/resources/tides-of-chaos",
        data={"expected_revision": stale_revision, "current": 0},
        follow_redirects=True,
    )
    assert second.status_code == 200
    html = second.get_data(as_text=True)
    assert "This sheet changed in another session. Refresh the page and try again." in html

    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    assert resources["wild-die"]["current"] == 1
    assert resources["tides-of-chaos"]["current"] == 1


def test_observer_cannot_mutate_character_state(client, sign_in, users, get_character):
    sign_in(users["observer"]["email"], users["observer"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/vitals",
        data={"expected_revision": record.state_record.revision, "current_hp": 30, "temp_hp": 0},
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_dm_can_edit_any_character(client, sign_in, users, get_character):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    record = get_character("selene-brook")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/selene-brook/session/vitals",
        data={"expected_revision": record.state_record.revision, "current_hp": 40, "temp_hp": 0},
        follow_redirects=False,
    )
    assert response.status_code == 302

    record = get_character("selene-brook")
    assert record.state_record.state["vitals"]["current_hp"] == 40


def test_unassigned_player_cannot_mutate_other_character(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    record = get_character("selene-brook")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/selene-brook/session/vitals",
        data={"expected_revision": record.state_record.revision, "current_hp": 30, "temp_hp": 0},
        follow_redirects=False,
    )

    assert response.status_code == 403

