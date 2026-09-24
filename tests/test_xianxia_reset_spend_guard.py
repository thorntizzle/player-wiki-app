from copy import deepcopy
import re

import pytest

from player_wiki.character_models import CharacterDefinition
from player_wiki.xianxia_advancement import (
    apply_xianxia_immortal_realm_rebuild_definition,
    apply_xianxia_divine_realm_rebuild_definition,
    confirm_xianxia_realm_ascension_definition,
    build_xianxia_realm_ascension_context,
    start_xianxia_realm_ascension_review_definition,
    reset_xianxia_realm_ascension_stats_definition,
    spend_xianxia_conditioning_definition,
    spend_xianxia_training_definition,
)
from tests.test_avatar_of_mourning import _definition


def realm_definition(realm):
    payload = _definition().to_dict()
    payload["system"] = "xianxia"
    payload["xianxia"] = {
        "realm": realm,
        "attributes": {"str": 10 if realm == "Mortal" else 15, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0},
        "efforts": {"basic": 0, "weapon": 0, "guns_explosive": 0, "magic": 0, "ultimate": 0},
        "insight": {"available": 100, "spent": 0},
        "durability": {"hp_max": 10, "stance_max": 10},
    }
    return CharacterDefinition.from_dict(payload)


def reviewed_definition(realm):
    return start_xianxia_realm_ascension_review_definition(
        realm_definition(realm), target_realm="Immortal" if realm == "Mortal" else "Divine", gm_review_note="Approved synthetic review"
    ).definition


def reset_definition(realm):
    return reset_xianxia_realm_ascension_stats_definition(
        reviewed_definition(realm), target_realm="Immortal" if realm == "Mortal" else "Divine"
    ).definition


@pytest.mark.parametrize("realm", ["Mortal", "Immortal"])
@pytest.mark.parametrize("kind", ["attribute", "effort"])
def test_reset_awaiting_rebuild_refuses_paid_stats_without_charging(realm, kind):
    definition = reset_definition(realm)
    original = deepcopy(definition.to_dict())
    with pytest.raises(ValueError, match="rebuild"):
        if kind == "attribute":
            spend_xianxia_training_definition(definition, training_target="attribute", attribute_key="str")
        else:
            spend_xianxia_conditioning_definition(definition, conditioning_target="effort", effort_key="basic")
    assert definition.to_dict() == original


def spend_stats(definition):
    trained = spend_xianxia_training_definition(definition, training_target="attribute", attribute_key="str").definition
    return spend_xianxia_conditioning_definition(trained, conditioning_target="effort", effort_key="basic").definition


def rebuild_scores(realm):
    return ({"str": 5, "dex": 5, "con": 5, "int": 0 if realm == "Mortal" else 5, "wis": 0 if realm == "Mortal" else 5, "cha": 0},
            {"basic": 0, "weapon": 0, "guns_explosive": 0, "magic": 0, "ultimate": 0})


@pytest.mark.parametrize("realm", ["Mortal", "Immortal"])
def test_real_lifecycle_only_blocks_between_reset_and_rebuild(realm):
    target = "Immortal" if realm == "Mortal" else "Divine"
    rebuild = apply_xianxia_immortal_realm_rebuild_definition if realm == "Mortal" else apply_xianxia_divine_realm_rebuild_definition
    for ready in (realm_definition(realm), reviewed_definition(realm)):
        assert not build_xianxia_realm_ascension_context(ready.xianxia)["reset_awaiting_rebuild"]
        assert spend_stats(ready).xianxia["insight"]["available"] < 100
    definition = reset_definition(realm)
    assert build_xianxia_realm_ascension_context(definition.xianxia)["reset_awaiting_rebuild"]
    with pytest.raises(ValueError, match="already been reset"):
        reset_xianxia_realm_ascension_stats_definition(definition, target_realm=target)
    definition = spend_xianxia_conditioning_definition(definition, conditioning_target="hp").definition
    definition = spend_xianxia_training_definition(definition, training_target="stance").definition
    durability = deepcopy(definition.xianxia["durability"])
    attributes, efforts = rebuild_scores(realm)
    rebuilt = rebuild(definition, target_realm=target, attribute_scores=attributes, effort_scores=efforts).definition
    for key in ("hp_max", "stance_max", "manual_armor_bonus"):
        assert rebuilt.xianxia["durability"][key] == durability[key]
    assert not build_xianxia_realm_ascension_context(rebuilt.xianxia)["reset_awaiting_rebuild"]
    assert spend_stats(rebuilt).xianxia["insight"]["available"] < rebuilt.xianxia["insight"]["available"]
    with pytest.raises(ValueError):
        rebuild(rebuilt, target_realm=target, attribute_scores=attributes, effort_scores=efforts)
    confirmed = confirm_xianxia_realm_ascension_definition(rebuilt, target_realm=target, gm_confirmation_note="Approved synthetic confirmation").definition
    assert spend_stats(confirmed).xianxia["insight"]["available"] < confirmed.xianxia["insight"]["available"]
    assert any(row.get("status") == "pending_rebuild" for row in confirmed.xianxia["advancement_history"])
    assert not build_xianxia_realm_ascension_context(confirmed.xianxia)["reset_awaiting_rebuild"]


@pytest.mark.parametrize("realm", ["Mortal", "Immortal"])
@pytest.mark.parametrize("history_case", ["reset_only", "wrong_target", "reset_before_review", "completed_same_realm", "new_review_after_old_reset", "malformed"])
def test_stale_or_unmatched_history_does_not_invent_reset_gap(realm, history_case):
    definition = reset_definition(realm)
    payload = definition.to_dict()
    review, reset = deepcopy(payload["xianxia"]["advancement_history"])
    if history_case == "reset_only":
        history = [reset]
    elif history_case == "wrong_target":
        reset["target_realm"] = "Divine" if realm == "Mortal" else "Immortal"
        history = [review, reset]
    elif history_case == "reset_before_review":
        history = [reset, review]
    elif history_case == "completed_same_realm":
        history = [review, reset, {"action": "realm_ascension_immortal_rebuild_applied" if realm == "Mortal" else "realm_ascension_divine_rebuild_applied"}]
    elif history_case == "new_review_after_old_reset":
        history = [review, reset, review]
    else:
        history = [None, {}, "pending_rebuild", {"action": "unknown"}]
    payload["xianxia"]["advancement_history"] = history
    definition = CharacterDefinition.from_dict(payload)
    assert not build_xianxia_realm_ascension_context(definition.xianxia)["reset_awaiting_rebuild"]
    spend_stats(definition)


@pytest.mark.parametrize("realm", ["Mortal", "Immortal"])
@pytest.mark.parametrize("transport", ["native", "api"])
def test_persisted_cultivation_lifecycle_guards_only_reset_gap(
    app, client, sign_in, users, realm, transport
):
    from tests.helpers.api_test_helpers import issue_api_token, api_headers
    from tests.helpers.character_state_helpers import _write_character_definition, _read_character_definition, _character_state_revision
    from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign, _valid_xianxia_create_data

    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/characters/new", data=_valid_xianxia_create_data("Guard Crane")).status_code == 302
    def prepare(payload):
        payload["xianxia"].update(realm=realm, insight={"available": 100, "spent": 0})
        payload["xianxia"]["attributes"]["str"] = 10 if realm == "Mortal" else 15
    _write_character_definition(app, "guard-crane", prepare)
    path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass/characters/guard-crane/definition.yaml"
    headers = api_headers(issue_api_token(app, users["dm"]["email"], label="reset-gap"))
    native_url = "/campaigns/linden-pass/characters/guard-crane/cultivation"
    target = "Immortal" if realm == "Mortal" else "Divine"
    def snapshot():
        with app.app_context():
            state = app.extensions["character_state_store"].get_exact_state("linden-pass", "guard-crane")
        return path.read_bytes(), state
    def post(action, *, success=True, revision=None, **values):
        before = snapshot()
        submitted = {"cultivation_action": action, "expected_revision": _character_state_revision(app, "guard-crane") if revision is None else revision, **values}
        if transport == "api":
            response = client.post("/api/v1" + native_url, headers=headers, json=submitted)
            assert response.status_code == (200 if success else 409 if revision is not None else 400), response.get_data(as_text=True)
        else:
            response = client.post(native_url, data=submitted, follow_redirects=True)
            assert response.status_code == 200
        after = snapshot()
        if success:
            assert after[0] != before[0]
            assert after[1].revision == before[1].revision + 1
            assert CharacterDefinition.from_dict(_read_character_definition(app, "guard-crane")).xianxia
        else:
            assert after == before
        return response
    stat_actions = [
        ("spend_training", {"training_target": "attribute", "attribute_key": "str"}),
        ("spend_conditioning", {"conditioning_target": "effort", "effort_key": "basic"}),
    ]
    for action, values in stat_actions:
        post(action, **values)
    post("start_realm_ascension_review", target_realm=target, realm_ascension_gm_review_note="Approved synthetic review")
    for action, values in stat_actions:
        post(action, **values)
    stale_revision = _character_state_revision(app, "guard-crane")
    post("reset_realm_ascension_stats", target_realm=target)
    post("reset_realm_ascension_stats", target_realm=target, success=False)
    html = client.get(native_url).get_data(as_text=True)
    assert "Complete the pending Realm rebuild before spending Insight on Attributes or Efforts." in html
    stat_forms = [form for form in re.findall(r"<form\b.*?</form>", html, re.S) if 'name="conditioning_target" value="effort"' in form or 'name="training_target" value="attribute"' in form]
    assert len(stat_forms) == 11
    for form in stat_forms:
        assert re.search(r'<button\b[^>]*\bdisabled\b', form)
    for action, values in stat_actions:
        refusal = post(action, **values, success=False)
        assert "Complete the pending Realm rebuild" in refusal.get_data(as_text=True)
    post("spend_conditioning", conditioning_target="hp", success=False, revision=stale_revision)
    post("spend_conditioning", conditioning_target="hp")
    post("spend_training", training_target="stance")
    durability = _read_character_definition(app, "guard-crane")["xianxia"]["durability"]
    attributes, efforts = rebuild_scores(realm)
    rebuild_values = {**{f"realm_rebuild_attribute_{key}": value for key, value in attributes.items()}, **{f"realm_rebuild_effort_{key}": value for key, value in efforts.items()}}
    rebuild_action = "apply_immortal_realm_rebuild" if realm == "Mortal" else "apply_divine_realm_rebuild"
    post(rebuild_action, target_realm=target, **rebuild_values)
    post(rebuild_action, target_realm=target, **rebuild_values, success=False)
    for key in ("hp_max", "stance_max"):
        assert _read_character_definition(app, "guard-crane")["xianxia"]["durability"][key] == durability[key]
    for action, values in stat_actions:
        post(action, **values)
        post(action, **values, revision=stale_revision, success=False)
    post("confirm_realm_ascension", target_realm=target, realm_ascension_gm_confirmation_note="Approved synthetic confirmation")
    post("confirm_realm_ascension", target_realm=target, realm_ascension_gm_confirmation_note="Repeated confirmation", success=False)
    for action, values in stat_actions:
        post(action, **values)
    assert "Complete the pending Realm rebuild before spending Insight" not in client.get(native_url).get_data(as_text=True)
