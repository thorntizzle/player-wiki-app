from __future__ import annotations

import pytest


STATUS_PAGE = "/campaigns/linden-pass/combat/status"
STATUS_LIVE = f"{STATUS_PAGE}/live-state"


def _async_headers() -> dict[str, str]:
    return {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


def _seed_npc(app, users, name: str, turn: int):
    with app.app_context():
        return app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name=name,
            turn_value=turn,
            initiative_priority=1,
            current_hp=10,
            max_hp=10,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )


def test_status_pair_preserves_endpoints_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    expected = (
        ("campaign_combat_view", "/campaigns/<campaign_slug>/combat"),
        ("campaign_combat_live_state", "/campaigns/<campaign_slug>/combat/live-state"),
        ("campaign_combat_dm_view", "/campaigns/<campaign_slug>/combat/dm"),
        ("campaign_combat_dm_live_state", "/campaigns/<campaign_slug>/combat/dm/live-state"),
        ("campaign_combat_status_view", "/campaigns/<campaign_slug>/combat/status"),
        (
            "campaign_combat_status_live_state",
            "/campaigns/<campaign_slug>/combat/status/live-state",
        ),
    )
    positions = []
    for endpoint, path in expected:
        matches = [(index, rule) for index, rule in enumerate(rules) if rule.endpoint == endpoint]
        assert len(matches) == 1
        index, rule = matches[0]
        positions.append(index)
        assert rule.rule == path
        assert rule.methods == {"GET", "HEAD", "OPTIONS"}
        assert client.post(path.replace("<campaign_slug>", "linden-pass")).status_code == 405
    assert positions == sorted(positions)


def test_status_pair_preserves_auth_membership_and_manager_access(client, sign_in, users):
    anonymous_page = client.get(STATUS_PAGE, follow_redirects=False)
    anonymous_live = client.get(STATUS_LIVE, headers=_async_headers(), follow_redirects=False)
    assert anonymous_page.status_code == 302
    assert anonymous_live.status_code == 302
    assert "/sign-in" in anonymous_page.headers["Location"]
    assert "/sign-in" in anonymous_live.headers["Location"]

    sign_in(users["outsider"]["email"], users["outsider"]["password"])
    assert client.get(STATUS_PAGE).status_code == 404
    assert client.get(STATUS_LIVE, headers=_async_headers()).status_code == 404

    for user_key in ("owner", "party"):
        sign_in(users[user_key]["email"], users[user_key]["password"])
        assert client.get(STATUS_PAGE).status_code == 403
        assert client.get(STATUS_LIVE, headers=_async_headers()).status_code == 403

    for user_key in ("dm", "admin"):
        sign_in(users[user_key]["email"], users[user_key]["password"])
        assert client.get(STATUS_PAGE).status_code == 200
        assert client.get(STATUS_LIVE, headers=_async_headers()).status_code == 200


def test_status_page_preserves_strict_bookmark_selection_and_template(app, client, sign_in, users):
    first = _seed_npc(app, users, "First Bookmark", 20)
    _seed_npc(app, users, "Second Bookmark", 10)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(f"{STATUS_PAGE}?combatant={first.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-combat-status-live-root' in body
    assert f'data-combat-live-url="{STATUS_LIVE}?combatant={first.id}"' in body
    assert "First Bookmark" in body
    assert client.get(f"{STATUS_PAGE}?combatant=not-an-integer").status_code == 404
    assert client.get(f"{STATUS_PAGE}?combatant=999999").status_code == 404


@pytest.mark.parametrize("requested", ("not-an-integer", "999999"))
def test_status_live_preserves_nonstrict_fallback_and_canonical_focus(
    app, client, sign_in, users, requested
):
    first = _seed_npc(app, users, "Live Fallback", 20)
    _seed_npc(app, users, "Other Target", 10)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(f"{STATUS_LIVE}?combatant={requested}", headers=_async_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is True
    assert payload["selected_combatant_id"] == first.id
    assert payload["page_url"] == f"{STATUS_PAGE}?combatant={first.id}"
    assert payload["live_url"] == f"{STATUS_LIVE}?combatant={first.id}"
    assert "Live Fallback" in payload["detail_html"]
    assert "board_html" in payload
    assert response.headers["X-Live-State-Changed"] == "true"
    assert response.headers["X-Live-View"] == "combat-status"


def test_status_live_preserves_metadata_then_short_circuit_and_diagnostics(
    app, client, sign_in, users, monkeypatch
):
    _seed_npc(app, users, "Polling Target", 20)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_combat_service"]
    calls: list[str] = []
    original_sync = service.sync_player_character_snapshots
    original_revision = service.get_live_revision

    def sync(*args, **kwargs):
        calls.append("metadata:sync")
        return original_sync(*args, **kwargs)

    def revision(*args, **kwargs):
        calls.append("metadata:revision")
        return original_revision(*args, **kwargs)

    monkeypatch.setattr(service, "sync_player_character_snapshots", sync)
    monkeypatch.setattr(service, "get_live_revision", revision)
    initial = client.get(STATUS_LIVE, headers=_async_headers())
    assert initial.status_code == 200
    payload = initial.get_json()
    assert calls[:2] == ["metadata:sync", "metadata:revision"]

    calls.clear()
    unchanged = client.get(
        STATUS_LIVE,
        headers={
            **_async_headers(),
            "X-Live-Revision": str(payload["live_revision"]),
            "X-Live-View-Token": payload["live_view_token"],
        },
    )
    assert calls[:2] == ["metadata:sync", "metadata:revision"]
    assert unchanged.get_json() == {
        "changed": False,
        "live_revision": payload["live_revision"],
        "live_view_token": payload["live_view_token"],
    }
    assert unchanged.headers["X-Live-State-Changed"] == "false"
    assert "render;dur=0.00" in unchanged.headers["Server-Timing"]


def test_status_live_preserves_detail_token_reuse(app, client, sign_in, users):
    target = _seed_npc(app, users, "Detail Reuse", 20)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    initial = client.get(f"{STATUS_LIVE}?combatant={target.id}", headers=_async_headers()).get_json()

    with app.app_context():
        app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Revision Only",
            turn_value=10,
            initiative_priority=1,
            current_hp=10,
            max_hp=10,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    response = client.get(
        f"{STATUS_LIVE}?combatant={target.id}",
        headers={
            **_async_headers(),
            "X-Live-Revision": str(initial["live_revision"]),
            "X-Live-View-Token": initial["live_view_token"],
            "X-Live-Detail-State-Token": initial["combatant_detail_state_token"],
        },
    )
    payload = response.get_json()
    assert payload["changed"] is True
    assert payload["selected_combatant_id"] == target.id
    assert payload["combatant_detail_state_token"] == initial["combatant_detail_state_token"]
    assert "detail_html" not in payload
    assert "board_html" in payload


def test_status_live_preserves_authorized_fault_propagation(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_combat_service"]

    monkeypatch.setattr(
        service,
        "get_live_revision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("metadata fault")),
    )
    with pytest.raises(RuntimeError, match="metadata fault"):
        client.get(STATUS_LIVE, headers=_async_headers())
