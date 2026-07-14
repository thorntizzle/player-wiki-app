from __future__ import annotations

import pytest

from player_wiki.live_presenter import build_combat_live_view_token


STATUS_LIVE_PATH = "/campaigns/linden-pass/combat/status/live-state"


def _async_headers() -> dict[str, str]:
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def _poll_headers(
    app,
    *,
    owned_character_slugs: set[str],
    mode: str,
) -> dict[str, str]:
    headers = _async_headers()
    if mode == "absent":
        return headers

    with app.app_context():
        revision = app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
    view_token = build_combat_live_view_token(
        "linden-pass",
        "status",
        can_manage_combat=False,
        owned_character_slugs=owned_character_slugs,
    )
    if mode == "matching":
        headers["X-Live-Revision"] = str(revision)
        headers["X-Live-View-Token"] = view_token
    elif mode == "stale":
        headers["X-Live-Revision"] = str(revision - 1)
        headers["X-Live-View-Token"] = view_token
    elif mode == "malformed":
        headers["X-Live-Revision"] = "not-a-revision"
        headers["X-Live-View-Token"] = "not-a-view-token"
    else:
        raise AssertionError(f"Unknown polling header mode: {mode}")
    return headers


@pytest.mark.parametrize(
    ("user_key", "owned_character_slugs"),
    (("owner", {"arden-march"}), ("party", set())),
    ids=("assigned-player", "unassigned-player"),
)
@pytest.mark.parametrize("header_mode", ("matching", "stale", "malformed", "absent"))
def test_status_live_state_denies_nonmanagers_for_every_poll_header_state(
    app,
    client,
    sign_in,
    users,
    user_key,
    owned_character_slugs,
    header_mode,
):
    sign_in(users[user_key]["email"], users[user_key]["password"])

    response = client.get(
        STATUS_LIVE_PATH,
        headers=_poll_headers(
            app,
            owned_character_slugs=owned_character_slugs,
            mode=header_mode,
        ),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("user_key", ("owner", "party"), ids=("assigned-player", "unassigned-player"))
def test_status_live_state_denial_precedes_metadata_snapshot_and_payload_work(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    user_key,
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    combat_service = app.extensions["campaign_combat_service"]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("denied status polling must not perform combat live-state work")

    monkeypatch.setattr(combat_service, "sync_player_character_snapshots", fail_if_called)
    monkeypatch.setattr(combat_service, "get_live_revision", fail_if_called)

    response = client.get(
        f"{STATUS_LIVE_PATH}?combatant=not-an-integer",
        headers={
            **_async_headers(),
            "X-Live-Revision": "0",
            "X-Live-View-Token": "matching-or-stale-is-irrelevant-before-authorization",
            "X-Live-Detail-State-Token": "untrusted-detail-token",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize("user_key", ("dm", "admin"), ids=("campaign-dm", "app-admin"))
@pytest.mark.parametrize(
    ("header_mode", "expected_changed"),
    (("matching", False), ("stale", True), ("malformed", True), ("absent", True)),
)
def test_status_live_state_preserves_authorized_polling_semantics(
    app,
    client,
    sign_in,
    users,
    user_key,
    header_mode,
    expected_changed,
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    initial_response = client.get(STATUS_LIVE_PATH, headers=_async_headers())
    assert initial_response.status_code == 200
    initial_payload = initial_response.get_json()
    assert initial_payload["changed"] is True

    headers = _async_headers()
    if header_mode == "matching":
        headers["X-Live-Revision"] = str(initial_payload["live_revision"])
        headers["X-Live-View-Token"] = initial_payload["live_view_token"]
    elif header_mode == "stale":
        headers["X-Live-Revision"] = str(initial_payload["live_revision"] - 1)
        headers["X-Live-View-Token"] = initial_payload["live_view_token"]
    elif header_mode == "malformed":
        headers["X-Live-Revision"] = "not-a-revision"
        headers["X-Live-View-Token"] = "not-a-view-token"
    elif header_mode != "absent":
        raise AssertionError(f"Unknown polling header mode: {header_mode}")

    response = client.get(STATUS_LIVE_PATH, headers=headers)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["changed"] is expected_changed
    assert payload["live_revision"] == initial_payload["live_revision"]
    assert payload["live_view_token"] == initial_payload["live_view_token"]
    if expected_changed:
        assert "detail_html" in payload
        assert "board_html" in payload
    else:
        assert payload == {
            "changed": False,
            "live_revision": initial_payload["live_revision"],
            "live_view_token": initial_payload["live_view_token"],
        }


@pytest.mark.parametrize("user_key", ("dm", "admin"), ids=("campaign-dm", "app-admin"))
def test_status_live_state_preserves_authorized_metadata_fault_propagation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    user_key,
):
    sign_in(users[user_key]["email"], users[user_key]["password"])
    combat_service = app.extensions["campaign_combat_service"]

    def fail_snapshot_sync(*args, **kwargs):
        raise RuntimeError("authorized snapshot sync failed")

    monkeypatch.setattr(combat_service, "sync_player_character_snapshots", fail_snapshot_sync)

    with pytest.raises(RuntimeError, match="authorized snapshot sync failed"):
        client.get(STATUS_LIVE_PATH, headers=_async_headers())


def test_status_live_state_preserves_get_head_options_method_identity(app, client, sign_in, users):
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == "campaign_combat_status_live_state")
    assert rule.rule == STATUS_LIVE_PATH.replace("linden-pass", "<campaign_slug>")
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}

    sign_in(users["dm"]["email"], users["dm"]["password"])
    head_response = client.head(STATUS_LIVE_PATH, headers=_async_headers())
    options_response = client.options(STATUS_LIVE_PATH)
    post_response = client.post(STATUS_LIVE_PATH)

    assert head_response.status_code == 200
    assert head_response.get_data() == b""
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {"GET", "HEAD", "OPTIONS"}
    assert post_response.status_code == 405
