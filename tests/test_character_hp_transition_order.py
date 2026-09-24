from copy import deepcopy

import pytest

from player_wiki.character_state_service import CharacterStateService
from player_wiki.divine_avatar_forms import AVATAR_OF_MOURNING_FORM_KEY
from tests.test_avatar_of_mourning import _MemoryStateStore, _next_record, _record


class CountingStore(_MemoryStateStore):
    def __init__(self):
        self.calls = 0

    def replace_state(self, *args, **kwargs):
        self.calls += 1
        return super().replace_state(*args, **kwargs)


def active_record():
    service = CharacterStateService(_MemoryStateStore())
    active = service.update_divine_avatar_form(
        _record(), AVATAR_OF_MOURNING_FORM_KEY, "activate", expected_revision=1, confirmed=True
    )
    active.state["feature_states"]["divine_avatar_forms"]["forms"][AVATAR_OF_MOURNING_FORM_KEY]["rounds_elapsed"] = 3
    return _next_record(active)


@pytest.mark.parametrize("entrypoint", ["absolute", "delta", "batch", "short", "long"])
def test_final_zero_hp_ends_avatar_once_and_preserves_explicit_values(entrypoint):
    record = active_record()
    original_definition = deepcopy(record.definition.to_dict())
    store = CountingStore()
    service = CharacterStateService(store)
    kwargs = {"expected_revision": record.state_record.revision}
    if entrypoint == "batch":
        result = service.save_character_sheet_edit(
            record, **kwargs, vitals={"current_hp": 0, "temp_hp": 17},
            spell_slots=[{"level": 1, "used": 2}], notes={"player_notes_markdown": "Final draft"},
        )
        assert result.state["vitals"]["temp_hp"] == 17
        assert result.state["spell_slots"][0]["used"] == 2
        assert result.state["notes"]["player_notes_markdown"] == "Final draft"
    elif entrypoint in {"short", "long"}:
        result = service.apply_rest(record, entrypoint, **kwargs, current_hp=0)
    else:
        result = service.update_vitals(record, **kwargs, **({"current_hp": 0} if entrypoint == "absolute" else {"hp_delta": -20}))
    assert store.calls == 1
    assert result.revision == record.state_record.revision + 1
    forms = result.state["feature_states"]["divine_avatar_forms"]
    assert forms["active_form"] == ""
    avatar = forms["forms"][AVATAR_OF_MOURNING_FORM_KEY]
    assert avatar["cooldown_active"] is True
    assert avatar["end_sequence"] == 1
    assert forms["pending_resolution"]["status"] == "pending"
    assert result.state["exhaustion_level"] == 3
    assert forms["pending_resolution"]["radiant_damage_dice"] == "15d12"
    ended = deepcopy(result.state["feature_states"])
    for hp in (0, 0, 20):
        result = service.save_character_sheet_edit(_next_record(result), expected_revision=result.revision, vitals={"current_hp": hp})
        assert result.state["feature_states"] == ended
    assert record.definition.to_dict() == original_definition


def test_invalid_late_batch_edit_does_not_transition_or_persist(monkeypatch):
    record = active_record()
    original = deepcopy(record.state_record.state)
    store = CountingStore()
    service = CharacterStateService(store)
    def unexpected_transition(*args, **kwargs):
        pytest.fail("Transition must run only after every explicit field is valid")
    monkeypatch.setattr("player_wiki.character_state_service.end_divine_avatar_form_automatically", unexpected_transition)
    with pytest.raises(TypeError, match="personal"):
        service.save_character_sheet_edit(record, expected_revision=2, vitals={"current_hp": 0}, personal=[])
    assert store.calls == 0
    assert record.state_record.state == original


def test_unchanged_conscious_hp_does_not_end_form():
    record = active_record()
    result = CharacterStateService(CountingStore()).save_character_sheet_edit(
        record, expected_revision=2, vitals={"current_hp": 20}
    )
    assert result.state["feature_states"] == record.state_record.state["feature_states"]


def test_invalid_explicit_slot_bounds_are_validated_before_end_cost(monkeypatch):
    record = active_record()
    original = deepcopy(record.state_record.state)
    store = CountingStore()
    def unexpected_transition(*args, **kwargs):
        pytest.fail("Validate the complete explicit state before applying the end cost")
    monkeypatch.setattr("player_wiki.character_state_service.end_divine_avatar_form_automatically", unexpected_transition)
    with pytest.raises(ValueError, match="spell slot usage"):
        CharacterStateService(store).save_character_sheet_edit(
            record, expected_revision=2, vitals={"current_hp": 0}, spell_slots=[{"level": 1, "used": 99}]
        )
    assert store.calls == 0
    assert record.state_record.state == original


def test_invalid_pending_resolution_does_not_get_overwritten():
    record = active_record()
    record.state_record.state["feature_states"]["divine_avatar_forms"]["pending_resolution"] = {
        "form_key": AVATAR_OF_MOURNING_FORM_KEY, "status": "pending", "resolution_id": "earlier"
    }
    original = deepcopy(record.state_record.state)
    store = CountingStore()
    with pytest.raises(ValueError):
        CharacterStateService(store).save_character_sheet_edit(record, expected_revision=2, vitals={"current_hp": 0})
    assert store.calls == 0
    assert record.state_record.state == original


def test_sheet_edit_api_ends_avatar_and_rejects_stale_and_invalid_batches(
    app, client, users, set_campaign_visibility, monkeypatch
):
    from tests.helpers.api_test_helpers import issue_api_token, api_headers
    from tests.helpers.character_state_helpers import _write_character_definition, _write_character_state

    set_campaign_visibility("linden-pass", characters="players")
    def grant(payload):
        payload["features"].append({"name": "Divine Avatar Forms", "category": "custom_feature", "page_ref": "mechanics/divine-avatar-forms"})
    _write_character_definition(app, "arden-march", grant)
    _write_character_state(app, "arden-march", lambda state: state["vitals"].update(current_hp=10))
    with app.app_context():
        repo = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        record = repo.get_character("linden-pass", "arden-march")
        CharacterStateService(store).update_divine_avatar_form(record, AVATAR_OF_MOURNING_FORM_KEY, "activate", expected_revision=record.state_record.revision, confirmed=True)
    _write_character_state(app, "arden-march", lambda state: state["feature_states"]["divine_avatar_forms"]["forms"][AVATAR_OF_MOURNING_FORM_KEY].update(rounds_elapsed=3))
    path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass/characters/arden-march/definition.yaml"
    definition_bytes = path.read_bytes()
    token = issue_api_token(app, users["owner"]["email"], label="avatar-hp-test")
    headers = api_headers(token)
    url = "/api/v1/campaigns/linden-pass/characters/arden-march"
    def read():
        response = client.get(url, headers=headers)
        assert response.status_code == 200
        return response.get_json()["character"]["state_record"]
    before = read()
    original_revision = before["revision"]
    def patch(**values):
        return client.patch(url + "/sheet-edit", headers=headers, json={"expected_revision": original_revision, **values})
    invalid = patch(vitals={"current_hp": 0}, inventory=[{"id": "unknown", "quantity": 1}])
    assert invalid.status_code == 400
    assert read() == before
    with monkeypatch.context() as fault:
        def fail_replace(*args, **kwargs):
            raise ValueError("Synthetic pre-persist fault")
        fault.setattr(store, "replace_state", fail_replace)
        failed = patch(vitals={"current_hp": 0})
        assert failed.status_code == 400
    assert read() == before
    slot = before["state"]["spell_slots"][0]
    response = patch(vitals={"current_hp": 0, "temp_hp": 13}, spell_slots=[{"level": slot["level"], "slot_lane_id": slot.get("slot_lane_id", ""), "used": 1}])
    assert response.status_code == 200
    after = read()
    assert after["revision"] == original_revision + 1
    assert after["state"]["vitals"] == {**before["state"]["vitals"], "current_hp": 0, "temp_hp": 13}
    assert after["state"]["spell_slots"][0]["used"] == 1
    forms = after["state"]["feature_states"]["divine_avatar_forms"]
    assert forms["active_form"] == ""
    assert forms["pending_resolution"]["status"] == "pending"
    assert after["state"]["exhaustion_level"] == 3
    stale = patch(vitals={"current_hp": 10})
    assert stale.status_code == 409
    assert read() == after
    healed = client.patch(url + "/sheet-edit", headers=headers, json={"expected_revision": after["revision"], "vitals": {"current_hp": 10}})
    assert healed.status_code == 200
    assert read()["state"]["feature_states"]["divine_avatar_forms"] == forms
    assert path.read_bytes() == definition_bytes
