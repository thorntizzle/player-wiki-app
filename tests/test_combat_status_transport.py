from __future__ import annotations

from dataclasses import replace

import pytest

from player_wiki import combat_routes


STATUS_PAGE = "/campaigns/linden-pass/combat/status"
STATUS_LIVE = f"{STATUS_PAGE}/live-state"
CANONICAL_STATUS_PAGE = "/campaigns/linden-pass/combat/dm"


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
        page = client.get(STATUS_PAGE, follow_redirects=False)
        assert page.status_code == 302
        assert page.headers["Location"] == CANONICAL_STATUS_PAGE
        assert client.get(STATUS_LIVE, headers=_async_headers()).status_code == 200


@pytest.mark.parametrize(
    ("suffix", "expected_location"),
    (
        ("", CANONICAL_STATUS_PAGE),
        ("?view=status", CANONICAL_STATUS_PAGE),
        ("?view=controls", CANONICAL_STATUS_PAGE),
        ("?ignored=value", CANONICAL_STATUS_PAGE),
    ),
)
def test_status_page_redirects_bare_and_ignored_query_variants(
    client, sign_in, users, suffix, expected_location
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(f"{STATUS_PAGE}{suffix}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == expected_location


def test_status_page_preserves_only_a_valid_scoped_combatant(app, client, sign_in, users):
    first = _seed_npc(app, users, "First Bookmark", 20)
    _seed_npc(app, users, "Second Bookmark", 10)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"{STATUS_PAGE}?combatant={first.id}&view=controls&ignored=value",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == f"{CANONICAL_STATUS_PAGE}?combatant={first.id}"
    assert client.get(f"{STATUS_PAGE}?combatant=not-an-integer").status_code == 404
    assert client.get(f"{STATUS_PAGE}?combatant=999999").status_code == 404


def test_status_page_head_options_post_and_xhr_contract(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    head = client.head(STATUS_PAGE, follow_redirects=False)
    assert head.status_code == 302
    assert head.headers["Location"] == CANONICAL_STATUS_PAGE
    assert head.get_data() == b""
    assert client.open(STATUS_PAGE, method="OPTIONS").status_code == 200
    assert client.post(STATUS_PAGE).status_code == 405

    xhr = client.get(STATUS_PAGE, headers=_async_headers(), follow_redirects=False)
    assert xhr.status_code == 302
    assert xhr.headers["Location"] == CANONICAL_STATUS_PAGE


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    ((None, 302), ("outsider", 404), ("owner", 403), ("party", 403)),
)
@pytest.mark.parametrize("target", ("", "?combatant=not-an-integer", "?combatant=999999"))
def test_status_page_denies_unauthorized_actors_before_dependency_or_target_disclosure(
    client, sign_in, users, monkeypatch, user_key, expected_status, target
):
    if user_key is not None:
        sign_in(users[user_key]["email"], users[user_key]["password"])
    monkeypatch.setattr(
        combat_routes,
        "_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("dependencies were obtained before denial")),
    )

    assert client.get(f"{STATUS_PAGE}{target}").status_code == expected_status


@pytest.mark.parametrize("user_key", ("dm", "admin"))
def test_status_page_bare_redirect_builds_no_service_or_presentation(
    app, client, sign_in, users, monkeypatch, user_key
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    original = app.extensions["combat_route_dependencies"]

    def fail(label):
        return lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError(label))

    app.extensions["combat_route_dependencies"] = replace(
        original,
        get_campaign_combat_service=fail("combat service constructed for bare redirect"),
        build_campaign_combat_status_context=fail("status presentation constructed"),
        build_campaign_combat_status_live_state=fail("status live presentation constructed"),
        build_campaign_combat_dm_status_context=fail("DM presentation constructed"),
    )

    response = client.get(STATUS_PAGE, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == CANONICAL_STATUS_PAGE


def test_status_page_valid_target_performs_one_scoped_lookup_without_presentation(
    app, client, sign_in, users, monkeypatch
):
    target = _seed_npc(app, users, "Scoped Target", 20)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    original = app.extensions["combat_route_dependencies"]
    service = original.get_campaign_combat_service()
    calls: list[tuple[str, int]] = []
    original_get_combatant = service.get_combatant

    def get_combatant(campaign_slug, combatant_id):
        calls.append((campaign_slug, combatant_id))
        return original_get_combatant(campaign_slug, combatant_id)

    def fail(label):
        return lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError(label))

    monkeypatch.setattr(service, "get_combatant", get_combatant)
    app.extensions["combat_route_dependencies"] = replace(
        original,
        build_campaign_combat_status_context=fail("status presentation constructed"),
        build_campaign_combat_status_live_state=fail("status live presentation constructed"),
        build_campaign_combat_dm_status_context=fail("DM presentation constructed"),
    )

    response = client.get(f"{STATUS_PAGE}?combatant={target.id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{CANONICAL_STATUS_PAGE}?combatant={target.id}"
    assert calls == [("linden-pass", target.id)]


def test_status_page_rejects_a_stale_scoped_target(app, client, sign_in, users):
    target = _seed_npc(app, users, "Stale Target", 20)
    with app.app_context():
        app.extensions["campaign_combat_service"].delete_combatant(
            "linden-pass",
            target.id,
        )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    assert client.get(f"{STATUS_PAGE}?combatant={target.id}").status_code == 404


@pytest.mark.parametrize(
    ("requested", "expected_calls"),
    (("not-an-integer", []), ("999999", ["service", ("get", "linden-pass", 999999)])),
)
def test_status_page_invalid_target_builds_no_presentation(
    app, client, sign_in, users, requested, expected_calls
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    original = app.extensions["combat_route_dependencies"]
    calls: list[object] = []

    class MissingService:
        def get_combatant(self, campaign_slug, combatant_id):
            calls.append(("get", campaign_slug, combatant_id))
            return None

    def get_service():
        calls.append("service")
        return MissingService()

    def fail(label):
        return lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError(label))

    app.extensions["combat_route_dependencies"] = replace(
        original,
        get_campaign_combat_service=get_service,
        build_campaign_combat_status_context=fail("status presentation constructed"),
        build_campaign_combat_status_live_state=fail("status live presentation constructed"),
        build_campaign_combat_dm_status_context=fail("DM presentation constructed"),
    )

    assert client.get(f"{STATUS_PAGE}?combatant={requested}").status_code == 404
    assert calls == expected_calls


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
    assert payload["page_url"] == f"{CANONICAL_STATUS_PAGE}?combatant={first.id}"
    assert payload["live_url"] == f"{STATUS_LIVE}?combatant={first.id}"
    assert "Live Fallback" in payload["detail_html"]
    assert "board_html" in payload
    assert f'href="{CANONICAL_STATUS_PAGE}?combatant={first.id}"' in payload["board_html"]
    assert f'href="{STATUS_PAGE}?combatant={first.id}"' not in payload["board_html"]
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
