from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
import os

import pytest

import player_wiki.app as app_module
import player_wiki.db as db_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db
from tests.helpers.character_state_helpers import (
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.test_character_reconciliation import _coordinator, _update_payload


CAMPAIGN = "linden-pass"
FIRST = "arden-march"
SECOND = "selene-brook"
LIVE = f"/campaigns/{CAMPAIGN}/combat/live-state"
ASYNC = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


def _poll_headers(payload, *, detail_only=False):
    headers = {**ASYNC, "X-Live-Detail-State-Token": payload["combatant_detail_state_token"]}
    if not detail_only:
        headers.update({
            "X-Live-Revision": str(payload["live_revision"]),
            "X-Live-View-Token": payload["live_view_token"],
        })
    return headers


@pytest.fixture
def context_world(app, client, sign_in, users):
    service = app.extensions["campaign_combat_service"]
    with app.app_context():
        AuthStore().upsert_character_assignment(users["owner"]["id"], CAMPAIGN, SECOND)
        first = service.add_player_character(CAMPAIGN, character_slug=FIRST, turn_value=18)
        second = service.add_player_character(CAMPAIGN, character_slug=SECOND, turn_value=16)
        npc = service.add_npc_combatant(
            CAMPAIGN, display_name="Context Sentinel", turn_value=12,
            current_hp=10, max_hp=10, movement_total=30,
        )
        service.set_current_turn(CAMPAIGN, first.id)
        service.sync_player_character_snapshots(CAMPAIGN)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    baseline = client.get(LIVE, headers=ASYNC)
    assert baseline.status_code == 200
    return service, first, second, npc, baseline.get_json()


def _observe_context_work(app, monkeypatch):
    service = app.extensions["campaign_combat_service"]
    repository = app.extensions["character_repository"]
    calls = Counter()
    records = {}
    details = []
    statements = []

    for name in (
        "list_combatants", "get_tracker", "list_conditions_by_combatant",
        "list_resource_counters_by_combatant", "list_resource_notes_by_combatant",
    ):
        original = getattr(service, name)

        def call(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(service, name, call)

    original_read = repository.get_visible_character

    def read(campaign, slug):
        calls[f"character:{slug}"] += 1
        record = original_read(campaign, slug)
        records[slug] = record
        return record

    original_present = app_module.present_character_detail

    def present(campaign, record, **kwargs):
        assert record is records[record.definition.character_slug]
        details.append((record.definition.character_slug, record.state_record.revision))
        return original_present(campaign, record, **kwargs)

    original_execute = db_module._InstrumentedConnection.execute

    def execute(connection, sql, parameters=()):
        if str(sql).lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(str(sql).split()))
        return original_execute(connection, sql, parameters)

    monkeypatch.setattr(repository, "get_visible_character", read)
    monkeypatch.setattr(app_module, "present_character_detail", present)
    monkeypatch.setattr(db_module._InstrumentedConnection, "execute", execute)
    return calls, records, details, statements


@pytest.mark.parametrize("mode", ("cold", "stale-detail", "same-detail", "unchanged", "document"))
def test_common_reads_and_authorized_detail_are_not_repeated(
    app, client, monkeypatch, context_world, record_property, mode,
):
    _service, first, _second, _npc, baseline = context_world
    calls, records, details, statements = _observe_context_work(app, monkeypatch)
    headers = dict(ASYNC)
    path = LIVE
    if mode == "stale-detail":
        headers["X-Live-Detail-State-Token"] = "stale"
    elif mode == "same-detail":
        headers = _poll_headers(baseline, detail_only=True)
    elif mode == "unchanged":
        headers = _poll_headers(baseline)
    elif mode == "document":
        path = f"/campaigns/{CAMPAIGN}/combat"
        # A live-detail header does not make an ordinary full page omit detail.
        headers = _poll_headers(baseline, detail_only=True)
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    record_property("select_statements", json.dumps(statements))
    record_property("common_reads", json.dumps(dict(calls), sort_keys=True))
    if mode == "unchanged":
        assert calls == {}
        assert details == []
        assert response.get_json() == {
            "changed": False,
            "live_revision": baseline["live_revision"],
            "live_view_token": baseline["live_view_token"],
        }
        return
    assert calls == {
        "list_combatants": 1, "get_tracker": 1,
        "list_conditions_by_combatant": 1,
        "list_resource_counters_by_combatant": 1,
        "list_resource_notes_by_combatant": 1,
        f"character:{FIRST}": 1, f"character:{SECOND}": 1,
    }
    expected_details = [] if mode == "same-detail" else [(FIRST, records[FIRST].state_record.revision)]
    assert details == expected_details
    if mode == "document":
        assert 'data-combat-section-panel=' in response.get_data(as_text=True)
        return
    payload = response.get_json()
    assert payload["selected_combatant_id"] == first.id
    assert payload["combatant_detail_state_token"] == baseline["combatant_detail_state_token"]
    assert ("tracker_html" in payload) is (mode != "same-detail")
    assert ("context_html" in payload) is (mode != "same-detail")
    assert response.headers["X-Live-Write-Count"] == "0"
    assert response.headers["X-Live-Commit-Count"] == "0"
    if mode != "same-detail":
        assert payload == baseline
        assert int(response.headers["X-Live-Query-Count"]) == len(statements)


@pytest.mark.parametrize("selector", ("first", "second", "npc", "missing", "malformed", "character-only"))
def test_consolidated_context_preserves_player_selector_fallback(
    app, client, monkeypatch, context_world, selector,
):
    _service, first, second, npc, _baseline = context_world
    query = {
        "first": f"?combatant={first.id}",
        "second": f"?combatant={second.id}",
        "npc": f"?combatant={npc.id}",
        "missing": "?combatant=999999",
        "malformed": "?combatant=not-a-number",
        "character-only": f"?character={SECOND}",
    }[selector]
    expected = second if selector == "second" else first
    calls, records, details, _statements = _observe_context_work(app, monkeypatch)
    response = client.get(LIVE + query, headers=ASYNC)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == expected.id
    assert f"combatant={expected.id}" in payload["page_url"]
    assert f"combatant={expected.id}" in payload["live_url"]
    assert details == [(expected.character_slug, records[expected.character_slug].state_record.revision)]
    assert calls["list_combatants"] == 1
    assert records[expected.character_slug].definition.name in payload["summary_html"]


@pytest.mark.parametrize("case", ("foreign", "unowned", "query-wins", "unsupported"))
def test_main_live_selector_boundaries_keep_authorized_capture(
    app, client, users, monkeypatch, context_world, case,
):
    service, first, second, _npc, _baseline = context_world
    requested_id = second.id
    expected = first
    with app.app_context():
        if case == "foreign":
            foreign = service.add_npc_combatant(
                "foreign-campaign", display_name="Foreign Sentinel", turn_value=30,
                current_hp=10, max_hp=10, movement_total=30,
            )
            requested_id = foreign.id
        elif case == "unowned":
            AuthStore().upsert_character_assignment(users["party"]["id"], CAMPAIGN, SECOND)
            service.set_current_turn(CAMPAIGN, second.id)
        elif case == "unsupported":
            _write_campaign_config(
                app, lambda config: config.update(system="xianxia", systems_library="xianxia"),
            )
    if case == "query-wins":
        dependencies = app.extensions["combat_route_dependencies"]

        def build_with_conflicting_argument(campaign_slug, **kwargs):
            kwargs["selected_combatant_id"] = first.id
            return dependencies.build_campaign_combat_live_state(campaign_slug, **kwargs)

        monkeypatch.setitem(
            app.extensions, "combat_route_dependencies",
            replace(dependencies, build_campaign_combat_live_state=build_with_conflicting_argument),
        )
        expected = second
    reference = (
        client.get(f"{LIVE}?combatant={expected.id}", headers=ASYNC).get_json()
        if case != "unsupported" else None
    )
    calls, records, details, _statements = _observe_context_work(app, monkeypatch)
    response = client.get(f"{LIVE}?combatant={requested_id}", headers=ASYNC)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is True
    assert all(isinstance(payload[key], str) for key in ("summary_html", "tracker_html", "context_html"))
    if case == "unsupported":
        assert payload["selected_combatant_id"] is None
        assert payload["combatant_detail_state_token"] == ""
        assert calls["list_combatants"] == 0 and details == []
        assert "data-combat-section-panel=" not in payload["tracker_html"]
        return
    assert payload["selected_combatant_id"] == expected.id
    assert f"combatant={expected.id}" in payload["page_url"]
    assert f"combatant={expected.id}" in payload["live_url"]
    assert details == [(expected.character_slug, records[expected.character_slug].state_record.revision)]
    assert calls["list_combatants"] == 1
    assert payload["combatant_detail_state_token"] == reference["combatant_detail_state_token"]
    for key in ("summary_html", "tracker_html", "context_html"):
        assert payload[key] == reference[key]
    assert f'name="expected_revision" value="{records[expected.character_slug].state_record.revision}"' in payload["tracker_html"]
    assert "Foreign Sentinel" not in json.dumps(payload)


@pytest.mark.parametrize("actor", ("party", "dm", "admin", "view-as-owner"))
def test_consolidated_context_keeps_effective_authority_and_fallback_fragments(
    app, client, sign_in, users, monkeypatch, context_world, actor,
):
    _service, first, _second, _npc, _baseline = context_world
    login = "admin" if actor == "view-as-owner" else actor
    sign_in(users[login]["email"], users[login]["password"])
    if actor == "view-as-owner":
        with client.session_transaction() as session:
            session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    calls, _records, details, _statements = _observe_context_work(app, monkeypatch)
    response = client.get(LIVE, headers=ASYNC)
    assert response.status_code == 200
    payload = response.get_json()
    assert all(isinstance(payload[key], str) for key in ("summary_html", "tracker_html", "context_html"))
    assert calls["list_combatants"] == 1
    if actor == "view-as-owner":
        assert payload["selected_combatant_id"] == first.id
        assert len(details) == 1
        assert 'data-combat-section-panel=' in payload["tracker_html"]
    else:
        assert details == []
        assert 'data-combat-section-panel=' not in payload["tracker_html"]


@pytest.mark.parametrize("has_npc", (False, True))
def test_empty_and_npc_only_contexts_keep_fallback_response(
    app, client, sign_in, users, monkeypatch, has_npc,
):
    with app.app_context():
        if has_npc:
            app.extensions["campaign_combat_service"].add_npc_combatant(
                CAMPAIGN, display_name="Context Sentinel", turn_value=12,
                current_hp=10, max_hp=10, movement_total=30,
            )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    calls, _records, details, _statements = _observe_context_work(app, monkeypatch)
    response = client.get(LIVE, headers={**ASYNC, "X-Live-Detail-State-Token": "arbitrary"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["combatant_detail_state_token"] == ""
    assert all(isinstance(payload[key], str) for key in ("summary_html", "tracker_html", "context_html"))
    assert details == []
    assert calls["list_combatants"] == 1


def test_detail_skip_does_not_suppress_required_loader_failures(
    app, client, monkeypatch, context_world,
):
    _service, _first, _second, _npc, baseline = context_world

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("synthetic detail unavailable")

    monkeypatch.setattr(app_module, "present_character_detail", unavailable)
    response = client.get(LIVE, headers=_poll_headers(baseline, detail_only=True))
    assert response.status_code == 200
    assert "tracker_html" not in response.get_json()
    for path in (LIVE, f"/campaigns/{CAMPAIGN}/combat"):
        with pytest.raises(RuntimeError, match="synthetic detail unavailable"):
            client.get(path, headers=ASYNC)

    def common_unavailable(*_args, **_kwargs):
        raise RuntimeError("synthetic common unavailable")

    monkeypatch.setattr(app.extensions["character_repository"], "get_visible_character", common_unavailable)
    with pytest.raises(RuntimeError, match="synthetic common unavailable"):
        client.get(LIVE, headers=_poll_headers(baseline, detail_only=True))


def _change_captured_world(app, service, first, second, kind):
    with app.app_context():
        if kind == "state":
            _write_character_state(app, FIRST, lambda state: state["vitals"].update(current_hp=9))
        elif kind == "resources":
            current = service.get_combatant(CAMPAIGN, first.id)
            service.update_resources(
                CAMPAIGN, first.id, expected_revision=current.revision,
                movement_remaining=0, has_action=False, has_bonus_action=False, has_reaction=False,
            )
        elif kind == "deleted":
            service.delete_combatant(CAMPAIGN, first.id)
        elif kind == "relinked":
            connection = get_db()
            connection.execute(
                "UPDATE campaign_combatants SET character_slug = ?, source_ref = ?, revision = revision + 1 WHERE id = ?",
                (SECOND, SECOND, first.id),
            )
            service.store.bump_tracker_revision(CAMPAIGN)
        elif kind == "current-turn":
            service.set_current_turn(CAMPAIGN, second.id)
        elif kind == "same-stat-definition":
            path = app.config["TEST_CAMPAIGNS_DIR"] / CAMPAIGN / "characters" / FIRST / "definition.yaml"
            original_stat = path.stat()
            original_bytes = path.read_bytes()
            changed = original_bytes.replace(b"Arden March", b"Arden Marsh", 1)
            assert changed != original_bytes and len(changed) == len(original_bytes)
            path.write_bytes(changed)
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        elif kind == "inactive":
            _write_character_definition(app, FIRST, lambda definition: definition.update(status="inactive"))
        elif kind == "missing":
            path = app.config["TEST_CAMPAIGNS_DIR"] / CAMPAIGN / "characters" / FIRST / "definition.yaml"
            path.rename(path.with_suffix(".absent"))
        elif kind == "protected":
            prior = service.character_repository.get_combat_seed_character(CAMPAIGN, FIRST)
            definition, metadata, _ = _update_payload(prior)

            def hold(event, _operation_id):
                if event == "after_commit":
                    raise RuntimeError("hold synthetic journal")

            with pytest.raises(RuntimeError, match="hold synthetic journal"):
                _coordinator(app, hold).update(
                    prior, definition, metadata, deepcopy(prior.state_record.state),
                    expected_revision=prior.state_record.revision, operation_kind="markdown_import",
                )
            get_db().execute(
                "UPDATE character_reconciliation_operations SET state = 'conflict' WHERE character_slug = ?",
                (FIRST,),
            )
            get_db().commit()
        else:
            raise AssertionError(kind)


@pytest.mark.parametrize("kind", (
    "state", "resources", "deleted", "relinked", "current-turn",
    "same-stat-definition", "inactive", "missing", "protected",
))
@pytest.mark.parametrize("boundary", ("before-capture", "after-capture"))
def test_capture_boundary_keeps_detail_token_and_record_together_then_converges(
    app, client, monkeypatch, context_world, kind, boundary,
):
    service, first, second, _npc, baseline = context_world
    if kind == "relinked":
        # A character can be linked only once; free the destination before
        # this scenario's capture so the boundary mutation is the relink alone.
        with app.app_context():
            service.delete_combatant(CAMPAIGN, second.id)
        baseline = client.get(LIVE, headers=ASYNC).get_json()
    captured_contexts = []
    original_render = app_module.render_template

    def render(template_name, **context):
        if template_name == "_combat_summary_card.html":
            captured_contexts.append(context)
        return original_render(template_name, **context)

    monkeypatch.setattr(app_module, "render_template", render)
    if boundary == "before-capture":
        _change_captured_world(app, service, first, second, kind)
    else:
        original_skip = app_module.should_skip_selected_combatant_detail_render
        changed = False

        def skip(**kwargs):
            nonlocal changed
            result = original_skip(**kwargs)
            if not changed:
                changed = True
                _change_captured_world(app, service, first, second, kind)
            return result

        monkeypatch.setattr(app_module, "should_skip_selected_combatant_detail_render", skip)

    response = client.get(LIVE, headers=ASYNC)
    assert response.status_code == 200
    payload = response.get_json()
    if boundary == "after-capture":
        assert payload["selected_combatant_id"] == first.id
        assert payload["combatant_detail_state_token"] == baseline["combatant_detail_state_token"]
        selected = captured_contexts[-1]["selected_combatant"]
        detail = captured_contexts[-1]["selected_combat_character"]
        assert detail["state_revision"] == selected["state_revision"]
        assert f'name="expected_revision" value="{detail["state_revision"]}"' in payload["tracker_html"]
        # Force a context read: unavailable snapshots intentionally need not bump
        # the tracker revision merely to advertise source protection/removal.
        response = client.get(LIVE, headers=_poll_headers(payload, detail_only=True))
        assert response.status_code == 200
        payload = response.get_json()
    expected = second if kind in {"deleted", "current-turn", "inactive", "missing", "protected"} else first
    assert payload["changed"] is True
    assert payload["selected_combatant_id"] == expected.id
    assert payload["combatant_detail_state_token"] != baseline["combatant_detail_state_token"]
    assert "tracker_html" in payload and "context_html" in payload
    selected = captured_contexts[-1]["selected_combatant"]
    detail = captured_contexts[-1]["selected_combat_character"]
    assert detail["state_revision"] == selected["state_revision"]
    if kind == "same-stat-definition":
        assert detail["name"] == "Arden Marsh"
    if kind == "relinked":
        assert detail["slug"] == SECOND
    if kind == "deleted":
        with app.app_context():
            assert service.get_combatant(CAMPAIGN, first.id) is None


def test_async_resource_response_consolidates_context_without_changing_mutation(
    app, client, monkeypatch, context_world,
):
    service, first, _second, _npc, _baseline = context_world
    with app.app_context():
        current = service.get_combatant(CAMPAIGN, first.id)
    calls, _records, details, _statements = _observe_context_work(app, monkeypatch)
    response = client.post(
        f"/campaigns/{CAMPAIGN}/combat/combatants/{first.id}/resources",
        data={
            "expected_combatant_revision": current.revision,
            "movement_remaining": 8, "has_action": "1",
            "has_bonus_action": "1", "has_reaction": "1", "combatant": first.id,
        },
        headers=ASYNC,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == first.id
    assert all(key in payload for key in ("summary_html", "tracker_html", "context_html", "flash_html"))
    assert calls["list_combatants"] == 1 and len(details) == 1
    with app.app_context():
        updated = service.get_combatant(CAMPAIGN, first.id)
    assert updated.revision == current.revision + 1
    assert updated.movement_remaining == 8
