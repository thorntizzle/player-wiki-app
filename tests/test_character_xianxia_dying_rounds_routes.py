from copy import deepcopy

import pytest

from tests.helpers.character_state_helpers import _write_character_definition
from tests.test_xianxia_derivation_presentation import _create_assigned_xianxia_session_character

BASE = "/campaigns/linden-pass/characters/dying-crane"
POST = BASE + "/xianxia-dying-rounds"


@pytest.fixture
def dying_character(app, client, sign_in, users, set_campaign_visibility, get_character):
    _create_assigned_xianxia_session_character(
        app, client, sign_in, users, set_campaign_visibility,
        character_slug="dying-crane", name="Dying Crane",
    )
    return lambda: get_character("dying-crane")


def _form(record, **overrides):
    return {"mode": "read", "action": "save", "expected_revision": str(record.state_record.revision),
            "dying_rounds_remaining": "4", **overrides}


@pytest.mark.parametrize("actor", ["dm", "admin", "owner"])
def test_editors_save_clear_reload_and_preserve_definition(app, client, sign_in, users, dying_character, actor):
    sign_in(users[actor]["email"], users[actor]["password"])
    definition = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass/characters/dying-crane/definition.yaml"
    before = definition.read_bytes()
    html = client.get(BASE + "?page=resources").get_data(as_text=True)
    assert "Not recorded" in html and 'name="dying_rounds_remaining"' in html
    for value in ("0", "6"):
        record = dying_character()
        state = deepcopy(record.state_record.state)
        response = client.post(POST, data=_form(record, dying_rounds_remaining=value))
        assert response.status_code == 302
        assert response.location.endswith("?page=resources#xianxia-dying-rounds")
        state["xianxia"]["dying_rounds_remaining"] = int(value)
        assert dying_character().state_record.state == state
        assert dying_character().state_record.updated_by_user_id == users[actor]["id"]
        assert f"{value} rounds remaining" in client.get(response.location).get_data(as_text=True)
        cleared = client.post(POST, data=_form(dying_character(), action="clear", dying_rounds_remaining="invalid"))
        assert cleared.status_code == 302
        assert dying_character().state_record.state["xianxia"]["dying_rounds_remaining"] is None
    assert definition.read_bytes() == before


@pytest.mark.parametrize("overrides", [
    {"dying_rounds_remaining": ""}, {"dying_rounds_remaining": "-1"}, {"dying_rounds_remaining": "7"},
    {"dying_rounds_remaining": "1.5"}, {"action": ""}, {"action": "roll"},
    {"expected_revision": ""}, {"expected_revision": "garbage"},
    {"mode": "session"}, {"mode": "combat"}, {"mode": ""}, {"return_view": "session-character"},
    {"combat_view": "player"},
])
def test_invalid_requests_are_visible_and_atomic(client, dying_character, overrides):
    before = dying_character().state_record
    response = client.post(POST, data=_form(dying_character(), **overrides), follow_redirects=True)
    assert response.status_code == 200
    assert 'data-feedback' in response.get_data(as_text=True)
    assert dying_character().state_record == before


@pytest.mark.parametrize("query", ["mode=session", "return_view=session-character", "combat_view=player", "mode=read&mode=session"])
def test_query_hints_cannot_enable_session_transport(client, dying_character, query):
    before = dying_character().state_record
    response = client.post(POST + "?" + query, data=_form(dying_character()))
    assert response.location.endswith("?page=resources#xianxia-dying-rounds")
    assert dying_character().state_record == before


def test_stale_save_and_clear_preserve_newer_hp(client, dying_character):
    record = dying_character()
    client.post(POST, data=_form(record))
    record = dying_character()
    client.post(BASE + "/session/vitals", data={"expected_revision": record.state_record.revision, "current_hp": 0, "mode": "read"})
    before = dying_character().state_record
    for action in ("save", "clear"):
        response = client.post(POST, data=_form(record, action=action), follow_redirects=True)
        assert "This sheet changed in another session" in response.get_data(as_text=True)
        assert dying_character().state_record == before
    assert before.state["vitals"]["current_hp"] == 0
    assert before.state["xianxia"]["dying_rounds_remaining"] == 4


@pytest.mark.parametrize("actor", ["observer", "party", "outsider"])
def test_noneditors_cannot_write(client, sign_in, users, dying_character, actor):
    sign_in(users[actor]["email"], users[actor]["password"])
    before = dying_character().state_record
    response = client.post(POST, data=_form(dying_character()))
    assert response.status_code == 403
    html = client.get(BASE + "?page=resources").get_data(as_text=True)
    assert 'name="dying_rounds_remaining"' not in html
    assert dying_character().state_record == before


def test_view_as_and_csrf_middleware_guard(app, client, sign_in, users, dying_character):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as session:
        session["view_as_user_id"] = users["owner"]["id"]
    before = dying_character().state_record
    html = client.get(BASE + "?page=resources").get_data(as_text=True)
    assert 'id="xianxia-dying-rounds"' in html
    assert 'name="dying_rounds_remaining"' not in html
    assert client.post(POST, data=_form(dying_character())).status_code == 403
    assert dying_character().state_record == before
    with client.session_transaction() as session:
        session.pop("view_as_user_id")
    app.config["CSRF_ENABLED"] = True
    assert client.post(POST, data=_form(dying_character())).status_code == 400
    assert dying_character().state_record == before
    with client.session_transaction() as session:
        session["csrf_token"] = "x" * 43
    assert client.post(POST, data=_form(dying_character(), _csrf_token="x" * 43)).status_code == 302
    assert dying_character().state_record.state["xianxia"]["dying_rounds_remaining"] == 4


def test_hidden_character_and_inaccessible_campaign(app, client, sign_in, users, dying_character, set_campaign_visibility):
    before = dying_character().state_record
    sign_in(users["owner"]["email"], users["owner"]["password"])
    set_campaign_visibility("linden-pass", characters="dm")
    assert client.post(POST, data=_form(dying_character())).status_code == 404
    assert dying_character().state_record == before
    set_campaign_visibility("linden-pass", characters="public")
    _write_character_definition(app, "dying-crane", lambda payload: payload.update(status="hidden"))
    assert client.post(POST, data={"mode": "read", "action": "save", "expected_revision": before.revision,
                                  "dying_rounds_remaining": "1"}).status_code == 404
    with app.app_context():
        assert app.extensions["character_state_store"].get_state("linden-pass", "dying-crane") == before


def test_dnd_character_and_campaign_refused(client, sign_in, users, get_character):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    from tests.sample_data import ASSIGNED_CHARACTER_SLUG
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    response = client.post(f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/xianxia-dying-rounds", data=_form(record))
    assert response.status_code == 404
    assert get_character(ASSIGNED_CHARACTER_SLUG).state_record == record.state_record


def test_character_session_combat_and_existing_payload_boundaries(client, dying_character):
    for query in ("page=resources", "page=resources&mode=session"):
        assert 'id="xianxia-dying-rounds"' in client.get(BASE + "?" + query).get_data(as_text=True)
    for url in (
        "/campaigns/linden-pass/session/character?character=dying-crane&page=resources",
        "/campaigns/linden-pass/session/character?character=dying-crane&page=resources&fragment=1",
        "/campaigns/linden-pass/combat",
    ):
        response = client.get(url, follow_redirects=True)
        assert response.status_code == 200
        assert 'id="xianxia-dying-rounds"' not in response.get_data(as_text=True)
        assert 'name="dying_rounds_remaining"' not in response.get_data(as_text=True)
    client.post(POST, data=_form(dying_character()))
    client.post(BASE + "/session/vitals", data={**_form(dying_character()), "current_hp": 0, "dying_rounds_remaining": "1"})
    assert dying_character().state_record.state["xianxia"]["dying_rounds_remaining"] == 4
    response = client.post(BASE + "/session/xianxia-active-state", data={**_form(dying_character()),
                           "active_stance_name": "Still Lotus", "active_aura_name": "Mist", "dying_rounds_remaining": "1"})
    assert response.status_code == 302
    assert dying_character().state_record.state["xianxia"]["dying_rounds_remaining"] == 4
    response = client.patch("/api/v1" + BASE + "/sheet-edit", json={"expected_revision": dying_character().state_record.revision,
                "vitals": {"current_hp": 5, "dying_rounds_remaining": 1}, "xianxia": {"dying_rounds_remaining": 1}})
    assert response.status_code == 200
    assert dying_character().state_record.state["xianxia"]["dying_rounds_remaining"] == 4
