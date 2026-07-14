from __future__ import annotations

import pytest

import player_wiki.app as app_module
from player_wiki.live_presenter import build_combat_live_view_token


CAMPAIGN_SLUG = "linden-pass"
CHARACTER_SLUG = "arden-march"
LIVE_STATE_PATH = f"/campaigns/{CAMPAIGN_SLUG}/combat/character/live-state"


def _async_headers() -> dict[str, str]:
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def _poll_headers(revision: int, view_token: str) -> dict[str, str]:
    return {
        **_async_headers(),
        "X-Live-Revision": str(revision),
        "X-Live-View-Token": view_token,
    }


def _assert_live_diagnostics_shape(response) -> None:
    assert response.headers["X-Live-Query-Count"]
    assert response.headers["X-Live-Query-Time-Ms"]
    assert response.headers["X-Live-Request-Time-Ms"]
    assert response.headers["X-Live-Snapshot-Sync"]
    assert "db;dur=" in response.headers["Server-Timing"]
    assert "total;dur=" in response.headers["Server-Timing"]


def _add_player_combatant(app, users):
    with app.app_context():
        return app.extensions["campaign_combat_service"].add_player_character(
            CAMPAIGN_SLUG,
            character_slug=CHARACTER_SLUG,
            turn_value=18,
            created_by_user_id=users["dm"]["id"],
        )


def _sign_in_as(sign_in, users, actor: str) -> None:
    response = sign_in(users[actor]["email"], users[actor]["password"])
    assert response.status_code == 302


def _initial_live_payload(client, *, selector: str = "") -> dict[str, object]:
    response = client.get(f"{LIVE_STATE_PATH}{selector}", headers=_async_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is True
    return payload


def _headers_for_mode(
    initial_payload: dict[str, object],
    mode: str,
    *,
    live_view_token: str | None = None,
) -> dict[str, str]:
    expected_view_token = live_view_token or str(initial_payload["live_view_token"])
    if mode == "matching":
        return _poll_headers(
            int(initial_payload["live_revision"]),
            expected_view_token,
        )
    if mode == "stale":
        return _poll_headers(
            int(initial_payload["live_revision"]) - 1,
            expected_view_token,
        )
    if mode == "malformed":
        return {
            **_async_headers(),
            "X-Live-Revision": "not-a-revision",
            "X-Live-View-Token": "not-a-view-token",
        }
    assert mode == "absent"
    return _async_headers()


@pytest.mark.parametrize("selector_kind", ["combatant", "character"])
@pytest.mark.parametrize("header_mode", ["matching", "stale", "malformed", "absent"])
def test_explicit_unowned_player_target_is_forbidden_before_polling_short_circuit(
    app,
    client,
    sign_in,
    users,
    selector_kind,
    header_mode,
):
    combatant = _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "party")
    initial_payload = _initial_live_payload(client)
    selector = (
        f"?combatant={combatant.id}"
        if selector_kind == "combatant"
        else f"?character={CHARACTER_SLUG}"
    )
    selected_combatant_id = combatant.id if selector_kind == "combatant" else None
    selected_view_token = build_combat_live_view_token(
        CAMPAIGN_SLUG,
        "character",
        selected_combatant_id=selected_combatant_id,
        can_manage_combat=False,
        owned_character_slugs=(),
    )

    response = client.get(
        f"{LIVE_STATE_PATH}{selector}",
        headers=_headers_for_mode(
            initial_payload,
            header_mode,
            live_view_token=selected_view_token,
        ),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("selector_kind", ["combatant", "character"])
@pytest.mark.parametrize("header_mode", ["matching", "stale", "malformed", "absent"])
def test_assigned_player_explicit_target_preserves_live_polling_contract(
    app,
    client,
    sign_in,
    users,
    selector_kind,
    header_mode,
):
    combatant = _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "owner")
    selector = (
        f"?combatant={combatant.id}"
        if selector_kind == "combatant"
        else f"?character={CHARACTER_SLUG}"
    )
    initial_payload = _initial_live_payload(client, selector=selector)

    response = client.get(
        f"{LIVE_STATE_PATH}{selector}",
        headers=_headers_for_mode(initial_payload, header_mode),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is (header_mode != "matching")
    assert payload["live_revision"] == initial_payload["live_revision"]
    assert payload["live_view_token"] == initial_payload["live_view_token"]
    _assert_live_diagnostics_shape(response)
    if header_mode == "matching":
        assert payload == {
            "changed": False,
            "live_revision": initial_payload["live_revision"],
            "live_view_token": initial_payload["live_view_token"],
        }
        assert response.headers["X-Live-State-Changed"] == "false"
    else:
        assert payload["snapshot_html"] == initial_payload["snapshot_html"]
        assert response.headers["X-Live-State-Changed"] == "true"


@pytest.mark.parametrize("actor", ["dm", "admin"])
@pytest.mark.parametrize("selector_kind", ["combatant", "character"])
@pytest.mark.parametrize("header_mode", ["matching", "stale", "malformed", "absent"])
def test_manager_explicit_target_preserves_existing_compatibility_live_behavior(
    app,
    client,
    sign_in,
    users,
    actor,
    selector_kind,
    header_mode,
):
    combatant = _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, actor)
    initial_payload = _initial_live_payload(client)
    selector = (
        f"?combatant={combatant.id}"
        if selector_kind == "combatant"
        else f"?character={CHARACTER_SLUG}"
    )
    selected_combatant_id = combatant.id if selector_kind == "combatant" else None
    selected_view_token = build_combat_live_view_token(
        CAMPAIGN_SLUG,
        "character",
        selected_combatant_id=selected_combatant_id,
        can_manage_combat=True,
        owned_character_slugs=(),
    )

    response = client.get(
        f"{LIVE_STATE_PATH}{selector}",
        headers=_headers_for_mode(
            initial_payload,
            header_mode,
            live_view_token=selected_view_token,
        ),
    )

    if header_mode == "matching":
        assert response.status_code == 200
        assert response.get_json() == {
            "changed": False,
            "live_revision": initial_payload["live_revision"],
            "live_view_token": selected_view_token,
        }
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("selector_kind", ["combatant", "character"])
def test_explicit_unowned_player_target_denial_precedes_all_eager_live_work(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    selector_kind,
):
    combatant = _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "party")
    service = app.extensions["campaign_combat_service"]
    eager_calls: list[str] = []

    def fail_if_called(label):
        def _fail(*args, **kwargs):
            eager_calls.append(label)
            raise AssertionError(f"denied live request performed eager work: {label}")

        return _fail

    monkeypatch.setattr(
        service,
        "sync_player_character_snapshots",
        fail_if_called("snapshot-sync"),
    )
    monkeypatch.setattr(service, "get_live_revision", fail_if_called("live-revision"))
    monkeypatch.setattr(service, "get_tracker", fail_if_called("tracker-payload"))
    monkeypatch.setattr(
        app_module,
        "build_shared_combat_live_view_token",
        fail_if_called("live-view-token"),
    )
    monkeypatch.setattr(
        app_module,
        "should_short_circuit_shared_live_response",
        fail_if_called("short-circuit"),
    )
    monkeypatch.setattr(app_module, "render_template", fail_if_called("render"))
    selector = (
        f"?combatant={combatant.id}"
        if selector_kind == "combatant"
        else f"?character={CHARACTER_SLUG}"
    )

    response = client.get(
        f"{LIVE_STATE_PATH}{selector}",
        headers={
            **_async_headers(),
            "X-Live-Revision": "0",
            "X-Live-View-Token": "attacker-supplied-token",
        },
    )

    assert response.status_code == 403
    assert eager_calls == []


def test_bare_unassigned_player_compatibility_live_state_remains_available(
    app,
    client,
    sign_in,
    users,
):
    _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "party")

    response = client.get(LIVE_STATE_PATH, headers=_async_headers())

    assert response.status_code == 200
    assert response.get_json()["changed"] is True


def test_explicit_combatant_selector_keeps_precedence_over_character_selector(
    app,
    client,
    sign_in,
    users,
):
    combatant = _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "owner")

    response = client.get(
        f"{LIVE_STATE_PATH}?combatant={combatant.id}&character=selene-brook",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is True
    assert "<h2>Arden March</h2>" in payload["snapshot_html"]
    assert "<h2>Selene Brook</h2>" not in payload["snapshot_html"]


def test_malformed_explicit_combatant_keeps_precedence_over_owned_character(
    app,
    client,
    sign_in,
    users,
):
    _add_player_combatant(app, users)
    _sign_in_as(sign_in, users, "owner")

    response = client.get(
        f"{LIVE_STATE_PATH}?combatant=not-an-id&character={CHARACTER_SLUG}",
        headers=_async_headers(),
    )

    assert response.status_code == 403
