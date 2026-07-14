from __future__ import annotations

import base64

import pytest

from player_wiki.campaign_session_store import CampaignSessionConflictError
from tests.helpers.api_test_helpers import *
from tests.helpers.api_test_helpers import (
    _advanced_editor_values,
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
    _configure_xianxia_campaign,
    _find_tracker_combatant,
    _import_systems_goblin,
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
    _write_json,
)

def test_api_session_endpoints_follow_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-api")

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))

    assert start_response.status_code == 200
    assert start_response.get_json()["session"]["is_active"] is True

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Sealed Orders",
            "body_markdown": "Deliver the crate to the eastern gate before moonrise.",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Sealed Orders"
    assert article_payload["links"] == {
        "source_url": "",
        "published_page_url": "",
        "player_wiki_editor_url": "/campaigns/linden-pass/dm-content/player-wiki/session-articles/1/new",
        "convert_url": "/campaigns/linden-pass/session/articles/1/convert",
    }
    assert article_payload["source"] == {
        "title": "",
        "label": "",
        "action_label": "",
        "missing_message": "",
    }
    assert article_payload["converted_page"] is None

    dm_session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert dm_session_response.status_code == 200
    dm_session_payload = dm_session_response.get_json()
    assert dm_session_payload["show_session_dm_passive_scores"] is True
    assert isinstance(dm_session_payload["session_dm_passive_scores"], list)
    assert len(dm_session_payload["staged_articles"]) == 1
    assert dm_session_payload["staged_articles"][0]["title"] == "Sealed Orders"

    post_message_response = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(player_token),
        json={"body": "We should check the contract before we sign anything."},
    )

    assert post_message_response.status_code == 200
    assert post_message_response.get_json()["message"]["author_display_name"] == "Party Player"

    player_before_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_before_reveal.status_code == 200
    player_before_payload = player_before_reveal.get_json()
    assert player_before_payload["show_session_dm_passive_scores"] is False
    assert "session_dm_passive_scores" not in player_before_payload
    assert "staged_articles" not in player_before_payload
    assert all(message["article"] is None for message in player_before_payload["messages"])

    reveal_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles/1/reveal",
        headers=api_headers(dm_token),
    )

    assert reveal_response.status_code == 200
    assert reveal_response.get_json()["article"]["is_revealed"] is True

    player_after_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_after_reveal.status_code == 200
    player_after_payload = player_after_reveal.get_json()
    reveal_messages = [message for message in player_after_payload["messages"] if message["article"] is not None]
    assert len(reveal_messages) == 1
    assert reveal_messages[0]["article"]["title"] == "Sealed Orders"


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("POST", "/api/v1/campaigns/linden-pass/session/start"),
        ("POST", "/api/v1/campaigns/linden-pass/session/close"),
        ("DELETE", "/api/v1/campaigns/linden-pass/session/logs/77"),
    ),
)
def test_api_session_lifecycle_mutations_preserve_access_matrix(
    client,
    app,
    users,
    method,
    path,
):
    outsider_token = issue_api_token(
        app,
        users["outsider"]["email"],
        label=f"outsider-session-lifecycle-{method.lower()}",
    )
    player_token = issue_api_token(
        app,
        users["party"]["email"],
        label=f"player-session-lifecycle-{method.lower()}",
    )
    dm_token = issue_api_token(
        app,
        users["dm"]["email"],
        label=f"dm-session-lifecycle-{method.lower()}",
    )

    anonymous = client.open(path, method=method)
    assert anonymous.status_code == 401
    assert anonymous.get_json() == {
        "ok": False,
        "error": {"code": "auth_required", "message": "Authentication required."},
    }

    scope_denied = client.open(path, method=method, headers=api_headers(outsider_token))
    assert scope_denied.status_code == 403
    assert scope_denied.get_json() == {
        "ok": False,
        "error": {
            "code": "forbidden",
            "message": "You do not have access to this campaign scope.",
        },
    }

    manager_denied = client.open(path, method=method, headers=api_headers(player_token))
    assert manager_denied.status_code == 403
    assert manager_denied.get_json() == {
        "ok": False,
        "error": {
            "code": "forbidden",
            "message": "You do not have permission to manage this session.",
        },
    }

    missing_campaign = client.open(
        path.replace("/linden-pass/", "/missing/"),
        method=method,
        headers=api_headers(dm_token),
    )
    assert missing_campaign.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("POST", "/api/v1/campaigns/linden-pass/session/start"),
        ("POST", "/api/v1/campaigns/linden-pass/session/close"),
    ),
)
def test_api_session_start_and_close_keep_redundant_current_user_guard(
    client,
    app,
    users,
    monkeypatch,
    method,
    path,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label=f"dm-redundant-{path.rsplit('/', 1)[-1]}")
    with app.app_context():
        dm_user = app.extensions["auth_store"].get_user_by_email(users["dm"]["email"])
    assert dm_user is not None
    responses = iter((dm_user, None))
    monkeypatch.setattr(api_module, "get_current_user", lambda: next(responses))

    response = client.open(path, method=method, headers=api_headers(dm_token))

    assert response.status_code == 401
    assert response.get_json() == {
        "ok": False,
        "error": {"code": "auth_required", "message": "Authentication required."},
    }
    with app.app_context():
        assert app.extensions["campaign_session_service"].get_live_revision("linden-pass") == 0


def test_api_session_lifecycle_success_preserves_actor_arguments_and_exact_payloads(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-lifecycle-success")
    session_service = app.extensions["campaign_session_service"]
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    original_begin = session_service.begin_session
    original_close = session_service.close_session
    original_delete = session_service.delete_session_log

    def record_begin(*args, **kwargs):
        calls.append(("begin", args, kwargs))
        return original_begin(*args, **kwargs)

    def record_close(*args, **kwargs):
        calls.append(("close", args, kwargs))
        return original_close(*args, **kwargs)

    def record_delete(*args, **kwargs):
        calls.append(("delete", args, kwargs))
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(session_service, "begin_session", record_begin)
    monkeypatch.setattr(session_service, "close_session", record_close)
    monkeypatch.setattr(session_service, "delete_session_log", record_delete)

    start = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    )
    assert start.status_code == 200
    start_payload = start.get_json()
    assert set(start_payload) == {"ok", "session"}
    assert start_payload["ok"] is True
    assert start_payload["session"] == {
        "id": 1,
        "campaign_slug": "linden-pass",
        "status": "active",
        "started_at": start_payload["session"]["started_at"],
        "started_by_user_id": users["dm"]["id"],
        "ended_at": None,
        "ended_by_user_id": None,
        "is_active": True,
    }

    close = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert close.status_code == 200
    close_payload = close.get_json()
    assert set(close_payload) == {"ok", "session"}
    assert close_payload["ok"] is True
    assert close_payload["session"] == {
        **start_payload["session"],
        "status": "closed",
        "ended_at": close_payload["session"]["ended_at"],
        "ended_by_user_id": users["dm"]["id"],
        "is_active": False,
    }

    delete = client.delete(
        "/api/v1/campaigns/linden-pass/session/logs/1",
        headers=api_headers(dm_token),
    )
    assert delete.status_code == 200
    assert delete.get_json() == {"ok": True, "deleted_session_id": 1}
    assert calls == [
        ("begin", ("linden-pass",), {"started_by_user_id": users["dm"]["id"]}),
        ("close", ("linden-pass",), {"ended_by_user_id": users["dm"]["id"]}),
        ("delete", ("linden-pass", 1), {}),
    ]


def test_api_session_lifecycle_validation_preserves_state_and_exact_errors(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-lifecycle-validation")
    service = app.extensions["campaign_session_service"]

    def live_revision():
        with app.app_context():
            return service.get_live_revision("linden-pass")

    close_missing = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert close_missing.status_code == 400
    assert close_missing.get_json() == {
        "ok": False,
        "error": {"code": "validation_error", "message": "There is no active session to close."},
    }
    assert live_revision() == 0

    delete_missing = client.delete(
        "/api/v1/campaigns/linden-pass/session/logs/77",
        headers=api_headers(dm_token),
    )
    assert delete_missing.status_code == 400
    assert delete_missing.get_json() == {
        "ok": False,
        "error": {"code": "validation_error", "message": "That chat log could not be found."},
    }
    assert live_revision() == 0

    started = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    )
    assert started.status_code == 200
    active_id = started.get_json()["session"]["id"]
    active_revision = live_revision()

    duplicate_start = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    )
    assert duplicate_start.status_code == 400
    assert duplicate_start.get_json() == {
        "ok": False,
        "error": {
            "code": "validation_error",
            "message": "A live session is already running for this campaign.",
        },
    }
    assert live_revision() == active_revision
    with app.app_context():
        assert service.get_active_session("linden-pass").id == active_id

    delete_active = client.delete(
        f"/api/v1/campaigns/linden-pass/session/logs/{active_id}",
        headers=api_headers(dm_token),
    )
    assert delete_active.status_code == 400
    assert delete_active.get_json() == {
        "ok": False,
        "error": {
            "code": "validation_error",
            "message": "Close the live session before deleting its chat log.",
        },
    }
    assert live_revision() == active_revision

    closed = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert closed.status_code == 200
    closed_revision = live_revision()

    def conflict(*args, **kwargs):
        raise CampaignSessionConflictError("characterized conflict")

    monkeypatch.setattr(service.store, "delete_session", conflict)
    delete_conflict = client.delete(
        f"/api/v1/campaigns/linden-pass/session/logs/{active_id}",
        headers=api_headers(dm_token),
    )
    assert delete_conflict.status_code == 400
    assert delete_conflict.get_json() == {
        "ok": False,
        "error": {
            "code": "validation_error",
            "message": "That chat log could not be deleted. Refresh the page and try again.",
        },
    }
    assert live_revision() == closed_revision
    with app.app_context():
        assert service.get_session_log("linden-pass", active_id) is not None


@pytest.mark.parametrize(
    ("method", "path", "service_method", "fault_message"),
    (
        ("POST", "/api/v1/campaigns/linden-pass/session/start", "begin_session", "start fault"),
        ("POST", "/api/v1/campaigns/linden-pass/session/close", "close_session", "close fault"),
        (
            "DELETE",
            "/api/v1/campaigns/linden-pass/session/logs/1",
            "delete_session_log",
            "delete fault",
        ),
    ),
)
def test_api_session_lifecycle_unexpected_faults_propagate_without_mutation(
    client,
    app,
    users,
    monkeypatch,
    method,
    path,
    service_method,
    fault_message,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label=f"dm-session-{service_method}-fault")
    service = app.extensions["campaign_session_service"]

    def fail(*args, **kwargs):
        raise RuntimeError(fault_message)

    monkeypatch.setattr(service, service_method, fail)
    with pytest.raises(RuntimeError, match=fault_message):
        client.open(path, method=method, headers=api_headers(dm_token))
    with app.app_context():
        assert service.get_live_revision("linden-pass") == 0


def test_api_session_start_serializer_fault_follows_durable_actor_and_revision(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-start-serializer-fault")
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        revision_before = service.get_live_revision("linden-pass")

    def fail_isoformat(_value):
        raise RuntimeError("start serializer fault")

    with monkeypatch.context() as patch:
        patch.setattr(api_module, "isoformat", fail_isoformat)
        with pytest.raises(RuntimeError, match="start serializer fault"):
            client.post(
                "/api/v1/campaigns/linden-pass/session/start",
                headers=api_headers(dm_token),
            )

    with app.app_context():
        active = service.get_active_session("linden-pass")
        assert active is not None
        assert active.started_by_user_id == users["dm"]["id"]
        assert service.get_live_revision("linden-pass") == revision_before + 1


def test_api_session_close_serializer_fault_follows_durable_actor_and_revision(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-close-serializer-fault")
    service = app.extensions["campaign_session_service"]
    started = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    )
    assert started.status_code == 200
    session_id = started.get_json()["session"]["id"]
    with app.app_context():
        revision_before = service.get_live_revision("linden-pass")

    def fail_isoformat(_value):
        raise RuntimeError("close serializer fault")

    with monkeypatch.context() as patch:
        patch.setattr(api_module, "isoformat", fail_isoformat)
        with pytest.raises(RuntimeError, match="close serializer fault"):
            client.post(
                "/api/v1/campaigns/linden-pass/session/close",
                headers=api_headers(dm_token),
            )

    with app.app_context():
        assert service.get_active_session("linden-pass") is None
        closed = service.get_session_log("linden-pass", session_id)
        assert closed is not None
        assert closed.is_active is False
        assert closed.ended_by_user_id == users["dm"]["id"]
        assert service.get_live_revision("linden-pass") == revision_before + 1


def test_api_session_articles_allow_image_only_manual_staging(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-only-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Signal Sketch",
            "body_markdown": "",
            "image": embedded_png_payload(
                "signal-sketch.png",
                alt_text="A sketched signal flag.",
                caption="Shown as the only article content.",
            ),
        },
    )

    assert create_response.status_code == 200
    article_payload = create_response.get_json()["article"]
    assert article_payload["title"] == "Signal Sketch"
    assert article_payload["body_markdown"] == ""
    assert article_payload["image"]["filename"] == "signal-sketch.png"
    assert article_payload["image"]["alt_text"] == "A sketched signal flag."
    assert article_payload["image"]["caption"] == "Shown as the only article content."

    session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert session_response.status_code == 200
    staged_payload = session_response.get_json()["staged_articles"]
    assert any(article["title"] == "Signal Sketch" and article["body_markdown"] == "" for article in staged_payload)


def test_api_session_articles_still_reject_title_only_manual_staging(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-empty-article-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Empty Draft",
            "body_markdown": "",
        },
    )

    assert create_response.status_code == 400
    payload = create_response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Session articles need body text or an image before they can be saved."


def test_api_session_article_blank_update_requires_existing_or_valid_image(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-update-api")

    text_create = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Text Draft",
            "body_markdown": "This text should survive a failed image replacement.",
        },
    )
    assert text_create.status_code == 200
    text_article_id = text_create.get_json()["article"]["id"]

    failed_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{text_article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Text Draft",
            "body_markdown": "",
            "image": {
                "filename": "not-an-image.txt",
                "media_type": "text/plain",
                "data_base64": TINY_PNG_BASE64,
            },
        },
    )
    assert failed_update.status_code == 400

    session_after_failure = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    text_article = next(
        article
        for article in session_after_failure.get_json()["staged_articles"]
        if article["id"] == text_article_id
    )
    assert text_article["body_markdown"] == "This text should survive a failed image replacement."
    assert text_article["image"] is None

    image_create = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Image Draft",
            "body_markdown": "This body can be cleared because the article has an image.",
            "image": embedded_png_payload("image-draft.png"),
        },
    )
    assert image_create.status_code == 200
    image_article_id = image_create.get_json()["article"]["id"]

    blank_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{image_article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Image Draft",
            "body_markdown": "",
            "image_alt_text": "Updated image-only draft.",
            "image_caption": "Body intentionally blank.",
        },
    )
    assert blank_update.status_code == 200
    updated_article = blank_update.get_json()["article"]
    assert updated_article["body_markdown"] == ""
    assert updated_article["image"]["alt_text"] == "Updated image-only draft."
    assert updated_article["image"]["caption"] == "Body intentionally blank."


def test_api_session_messages_support_private_audience_scope(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-audience-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-audience-api")
    party_token = issue_api_token(app, users["party"]["email"], label="party-session-audience-api")

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))
    assert start_response.status_code == 200
    assert start_response.get_json()["session"]["id"] == 1

    global_body = "Council update for everyone."
    dm_only_body = "DM-only response notes."
    owner_only_body = "Owner should get this note."
    party_private_body = "Party-to-DM check-in."

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(dm_token),
            json={
                "body": global_body,
            },
        ).status_code
        == 200
    )

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(dm_token),
            json={
                "body": dm_only_body,
                "recipient_scope": "dm_only",
            },
        ).status_code
        == 200
    )

    owner_create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(dm_token),
        json={
            "body": owner_only_body,
            "recipient_scope": "player",
            "recipient_user_id": users["owner"]["id"],
        },
    )
    assert owner_create_response.status_code == 200
    assert owner_create_response.get_json()["message"]["recipient_label"] == "Owner Player"

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(party_token),
            json={
                "body": party_private_body,
                "recipient_scope": "dm_only",
            },
        ).status_code
        == 200
    )

    party_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(party_token),
    ).get_json()
    party_messages = [entry["body_text"] for entry in party_payload["messages"]]
    assert global_body in party_messages
    assert dm_only_body not in party_messages
    assert owner_only_body not in party_messages
    assert party_private_body in party_messages

    owner_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(owner_token),
    ).get_json()
    recipient_choices = owner_payload.get("session_message_recipient_player_choices")
    assert isinstance(recipient_choices, list)
    recipient_ids = {int(choice["user_id"]) for choice in recipient_choices}
    assert users["owner"]["id"] in recipient_ids
    assert users["party"]["id"] in recipient_ids
    assert all("label" in choice for choice in recipient_choices)
    recipient_labels = {int(choice["user_id"]): choice["label"] for choice in recipient_choices}
    assert recipient_labels[users["owner"]["id"]] == "Arden March (Owner Player)"
    assert recipient_labels[users["party"]["id"]] == "Party Player"
    assert all("@" not in choice["label"] for choice in recipient_choices)

    owner_messages = {entry["body_text"]: entry for entry in owner_payload["messages"]}
    assert owner_messages[global_body]["recipient_scope"] == "global"
    assert owner_messages[owner_only_body]["recipient_scope"] == "player"
    assert owner_messages[owner_only_body]["recipient_label"] == "Owner Player"
    assert party_private_body not in owner_messages

    dm_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(dm_token),
    ).get_json()
    dm_messages = {entry["body_text"]: entry for entry in dm_payload["messages"]}
    assert dm_messages[global_body]["recipient_scope"] == "global"
    assert dm_messages[dm_only_body]["recipient_scope"] == "dm_only"
    assert dm_messages[dm_only_body]["recipient_label"] == "DM"
    assert dm_messages[owner_only_body]["recipient_label"] == "Owner Player"

    close_response = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert close_response.status_code == 200

    log_id = int(close_response.get_json()["session"]["id"])
    log_payload = client.get(
        f"/api/v1/campaigns/linden-pass/session/logs/{log_id}",
        headers=api_headers(dm_token),
    ).get_json()
    assert log_payload["ok"] is True
    log_messages = {entry["body_text"]: entry for entry in log_payload["messages"]}
    assert set(log_messages.keys()) >= {
        global_body,
        dm_only_body,
        owner_only_body,
        party_private_body,
    }
    assert log_messages[dm_only_body]["recipient_scope"] == "dm_only"
    assert log_messages[owner_only_body]["recipient_scope"] == "player"
    assert log_messages[owner_only_body]["recipient_label"] == "Owner Player"


def test_active_player_choices_use_campaign_membership_list(app, users, monkeypatch):
    from player_wiki.player_choices import build_active_player_choices

    with app.app_context():
        store = app.extensions["auth_store"]

        def fail_get_membership(*args, **kwargs):
            raise AssertionError("player choices should use the campaign membership list")

        monkeypatch.setattr(store, "get_membership", fail_get_membership)

        choices = build_active_player_choices(
            store,
            "linden-pass",
            current_user_id=users["owner"]["id"],
            include_current=True,
        )

    choices_by_id = {int(choice["user_id"]): choice for choice in choices}
    assert set(choices_by_id) == {users["owner"]["id"], users["party"]["id"]}
    assert choices_by_id[users["owner"]["id"]]["label"] == "Owner Player (owner@example.com)"
    assert choices_by_id[users["owner"]["id"]]["is_current"] is True
    assert choices_by_id[users["party"]["id"]]["is_current"] is False


def test_api_session_state_includes_revision_and_view_token(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-metadata-api")

    response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["ok"] is True
    assert isinstance(payload["session_revision"], int)
    assert payload["session_revision"] >= 0
    assert isinstance(payload["session_view_token"], str)
    assert len(payload["session_view_token"]) == 12


def test_api_session_state_short_circuits_with_matching_live_tokens(client, app, users, monkeypatch):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-unchanged-api")

    initial_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert initial_response.status_code == 200
    initial_payload = initial_response.get_json()
    assert initial_payload["ok"] is True

    def fail_if_full_payload_is_built(*args, **kwargs):
        raise AssertionError("matching live tokens must not build the full session payload")

    monkeypatch.setattr(
        app.extensions["campaign_session_service"],
        "get_active_session",
        fail_if_full_payload_is_built,
    )

    unchanged_response = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers={
            **api_headers(dm_token),
            "X-Live-Revision": str(initial_payload["session_revision"]),
            "X-Live-View-Token": initial_payload["session_view_token"],
        },
    )
    assert unchanged_response.status_code == 200
    unchanged_payload = unchanged_response.get_json()

    assert unchanged_payload["ok"] is True
    assert unchanged_payload["changed"] is False
    assert unchanged_payload["session_revision"] == initial_payload["session_revision"]
    assert unchanged_payload["session_view_token"] == initial_payload["session_view_token"]
    assert set(unchanged_payload.keys()) == {"ok", "changed", "session_revision", "session_view_token"}


def test_api_session_state_preserves_live_token_inputs_and_faults(client, app, users, monkeypatch):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-live-inputs-api")
    captured: dict[str, object] = {}

    def build_token(campaign_slug: str, scope: str, **kwargs):
        captured.update(campaign_slug=campaign_slug, scope=scope, **kwargs)
        return "fixed-token"

    monkeypatch.setattr(api_module, "build_shared_session_live_view_token", build_token)
    response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert response.status_code == 200
    assert captured == {
        "campaign_slug": "linden-pass",
        "scope": "session",
        "session_chat_order": "newest_first",
        "can_manage_session": True,
        "can_post_session_messages": True,
        "normalize_hash_parts": True,
    }
    assert response.get_json()["session_view_token"] == "fixed-token"

    def fail_revision(_campaign_slug: str):
        raise RuntimeError("revision fault")

    monkeypatch.setattr(
        app.extensions["campaign_session_service"],
        "get_live_revision",
        fail_revision,
    )
    with pytest.raises(RuntimeError, match="revision fault"):
        client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))


def test_api_session_article_source_search_preserves_access_and_short_query_contract(
    client,
    app,
    users,
):
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-search-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-short-search-api")

    anonymous = client.get("/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt")
    assert anonymous.status_code == 401
    assert anonymous.get_json() == {
        "ok": False,
        "error": {"code": "auth_required", "message": "Authentication required."},
    }

    forbidden = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=api_headers(player_token),
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json() == {
        "ok": False,
        "error": {
            "code": "forbidden",
            "message": "You do not have permission to manage this session.",
        },
    }

    missing = client.get(
        "/api/v1/campaigns/missing/session/article-sources/search?q=capt",
        headers=api_headers(dm_token),
    )
    assert missing.status_code == 404

    original_page_store = app.extensions["campaign_page_store"]
    original_systems_service = app.extensions["systems_service"]
    app.extensions["campaign_page_store"] = object()
    app.extensions["systems_service"] = object()
    try:
        short = client.get(
            "/api/v1/campaigns/linden-pass/session/article-sources/search?q=%20a%20",
            headers=api_headers(dm_token),
        )
    finally:
        app.extensions["campaign_page_store"] = original_page_store
        app.extensions["systems_service"] = original_systems_service

    assert short.status_code == 200
    assert short.get_json() == {
        "ok": True,
        "results": [],
        "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
    }


def test_api_session_article_source_search_preserves_filters_messages_and_faults(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-search-boundary-api")
    calls: list[dict[str, object]] = []

    def build_results(**kwargs):
        calls.append(kwargs)
        if kwargs["query"] == "none":
            return []
        if kwargs["query"] == "single":
            return [{"title": "One"}]
        if kwargs["query"] == "thirty":
            return [{"title": f"Result {index}"} for index in range(30)]
        raise RuntimeError("search fault")

    monkeypatch.setattr(
        api_module,
        "build_shared_session_article_source_search_results",
        build_results,
    )
    expected_messages = {
        "none": "No published wiki or Systems articles matched that search.",
        "single": "Found 1 matching article.",
        "thirty": "Showing the first 30 matching articles.",
    }
    for query, expected_message in expected_messages.items():
        response = client.get(
            f"/api/v1/campaigns/linden-pass/session/article-sources/search?q=%20{query}%20",
            headers=api_headers(dm_token),
        )
        assert response.status_code == 200
        assert response.get_json()["message"] == expected_message

    assert [call["query"] for call in calls] == ["none", "single", "thirty"]
    assert all(call["campaign_slug"] == "linden-pass" for call in calls)
    assert all(call["limit"] == 30 for call in calls)
    assert all(call["can_access_systems"] is True for call in calls)
    assert all(callable(call["can_access_systems_entry"]) for call in calls)

    with pytest.raises(RuntimeError, match="search fault"):
        client.get(
            "/api/v1/campaigns/linden-pass/session/article-sources/search?q=fault",
            headers=api_headers(dm_token),
        )


def test_api_session_article_image_preserves_visibility_bytes_and_headers(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-read-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-image-read-api")
    create = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Signal Map",
            "body_markdown": "A map for the current scene.",
            "image": embedded_png_payload("signal-map.png"),
        },
    )
    article_id = create.get_json()["article"]["id"]
    image_url = f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/image"

    manager = client.get(image_url, headers=api_headers(dm_token))
    assert manager.status_code == 200
    assert manager.data == base64.b64decode(TINY_PNG_BASE64)
    assert manager.content_type == "image/png"
    assert manager.headers["Content-Disposition"] == "inline; filename=signal-map.png"

    assert client.get(image_url, headers=api_headers(player_token)).status_code == 404
    assert client.get(image_url).status_code == 401

    assert client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    ).status_code == 200
    assert client.post(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/reveal",
        headers=api_headers(dm_token),
    ).status_code == 200

    current_player = client.get(image_url, headers=api_headers(player_token))
    assert current_player.status_code == 200
    assert current_player.data == manager.data
    assert client.get(image_url).status_code == 401

    assert client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    ).status_code == 200
    assert client.get(image_url, headers=api_headers(player_token)).status_code == 404

    assert client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    ).status_code == 200
    assert client.get(image_url, headers=api_headers(player_token)).status_code == 404


def test_api_session_article_image_hides_missing_objects_and_propagates_faults(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-errors-api")
    without_image = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={"mode": "manual", "title": "Text Only", "body_markdown": "No image."},
    )
    article_id = without_image.get_json()["article"]["id"]
    assert client.get(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/image",
        headers=api_headers(dm_token),
    ).status_code == 404
    assert client.get(
        "/api/v1/campaigns/linden-pass/session/articles/999999/image",
        headers=api_headers(dm_token),
    ).status_code == 404

    def fail_article(*args, **kwargs):
        raise RuntimeError("article image fault")

    monkeypatch.setattr(app.extensions["campaign_session_service"], "get_article", fail_article)
    with pytest.raises(RuntimeError, match="article image fault"):
        client.get(
            f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/image",
            headers=api_headers(dm_token),
        )


def test_api_session_log_detail_preserves_access_payload_and_faults(client, app, users, monkeypatch):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-log-read-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-log-read-api")
    log_url = "/api/v1/campaigns/linden-pass/session/logs/1"

    anonymous = client.get(log_url)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"] == {
        "code": "auth_required",
        "message": "Authentication required.",
    }
    forbidden = client.get(log_url, headers=api_headers(player_token))
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == {
        "code": "forbidden",
        "message": "You do not have permission to manage this session.",
    }
    assert client.get(log_url, headers=api_headers(dm_token)).status_code == 404

    start = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=api_headers(dm_token),
    )
    assert start.status_code == 200
    session_id = start.get_json()["session"]["id"]
    log_url = f"/api/v1/campaigns/linden-pass/session/logs/{session_id}"
    assert client.get(log_url, headers=api_headers(dm_token)).status_code == 404

    message = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(dm_token),
        json={"body": "Exact log payload marker."},
    )
    assert message.status_code == 200
    close = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert close.status_code == 200

    detail = client.get(log_url, headers=api_headers(dm_token))
    assert detail.status_code == 200
    detail_payload = detail.get_json()
    assert set(detail_payload) == {"ok", "session", "messages"}
    assert detail_payload["ok"] is True
    assert detail_payload["session"] == close.get_json()["session"]
    assert message.get_json()["message"] in detail_payload["messages"]
    assert all(
        set(entry)
        == {
            "id",
            "session_id",
            "campaign_slug",
            "message_type",
            "body_text",
            "author_user_id",
            "author_display_name",
            "article_id",
            "created_at",
            "recipient_scope",
            "recipient_user_id",
            "recipient_label",
            "article",
        }
        for entry in detail_payload["messages"]
    )

    def fail_log(*args, **kwargs):
        raise RuntimeError("session log fault")

    monkeypatch.setattr(app.extensions["campaign_session_service"], "get_session_log", fail_log)
    with pytest.raises(RuntimeError, match="session log fault"):
        client.get(log_url, headers=api_headers(dm_token))


def test_api_can_pull_visible_wiki_page_into_session_store(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-wiki-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": "npcs/captain-lyra-vale",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Captain Lyra Vale"
    assert article_payload["body_format"] == "markdown"
    assert article_payload["source_kind"] == "page"
    assert article_payload["source_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["source_page_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["links"]["source_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert article_payload["links"]["player_wiki_editor_url"] == ""
    assert article_payload["links"]["convert_url"] == ""
    assert article_payload["source"] == {
        "title": "Captain Lyra Vale",
        "label": "published wiki page",
        "action_label": "View published page",
        "missing_message": "The original published wiki page is not currently visible in the player wiki.",
    }
    assert article_payload["image"] is not None
    assert article_payload["image"]["filename"] == "captain-lyra-vale.png"
    assert article_payload["image"]["alt_text"] == "Portrait of Captain Lyra Vale."
    assert article_payload["image"]["caption"] == "Harbor watch captain and trusted ally of the crew."


def test_api_session_article_payload_reports_converted_page_links(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-converted-links-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Courier Seal",
            "body_markdown": "A seal shown during the session.",
        },
    )

    assert create_response.status_code == 200
    article_id = create_response.get_json()["article"]["id"]

    create_page_response = client.put(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-courier-seal",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Courier Seal",
                "section": "Notes",
                "type": "note",
                "summary": "A session article converted into a durable player wiki page.",
                "published": True,
                "reveal_after_session": 0,
                "source_ref": f"session-article:linden-pass:{article_id}",
            },
            "body_markdown": "The courier seal is now a published reference.",
        },
    )

    assert create_page_response.status_code == 200

    session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert session_response.status_code == 200
    staged_articles = session_response.get_json()["staged_articles"]
    article_payload = next(article for article in staged_articles if article["id"] == article_id)
    assert article_payload["converted_page"] == {
        "title": "API Courier Seal",
        "is_visible": True,
        "reveal_after_session": 0,
    }
    assert article_payload["links"]["published_page_url"] == "/campaigns/linden-pass/pages/notes/api-courier-seal"
    assert article_payload["links"]["player_wiki_editor_url"] == ""
    assert article_payload["links"]["convert_url"] == ""


def test_api_session_article_source_search_returns_wiki_pages_and_systems_entries(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-source-search-api")

    wiki_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=api_headers(dm_token),
    )
    assert wiki_search.status_code == 200
    wiki_payload = wiki_search.get_json()
    assert wiki_payload["results"]
    captain_result = next(
        result for result in wiki_payload["results"] if result["source_ref"] == "npcs/captain-lyra-vale"
    )
    assert captain_result["source_kind"] == "page"
    assert captain_result["kind_label"] == "Wiki"
    assert captain_result["select_label"] == "Captain Lyra Vale - Wiki - NPCs"

    systems_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=gob",
        headers=api_headers(dm_token),
    )
    assert systems_search.status_code == 200
    systems_payload = systems_search.get_json()
    assert systems_payload["results"]
    assert systems_payload["results"][0]["source_kind"] == "systems"
    assert systems_payload["results"][0]["source_ref"] == f"systems:{goblin_slug}"
    assert systems_payload["results"][0]["title"] == "Goblin"
    assert systems_payload["results"][0]["subtitle"] == "Monsters - MM"
    assert systems_payload["results"][0]["kind_label"] == "Systems"
    assert systems_payload["results"][0]["select_label"] == "Goblin - Systems - Monsters - MM"


def test_api_can_pull_visible_systems_entry_into_session_store(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-systems-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": f"systems:{goblin_slug}",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Goblin"
    assert article_payload["body_format"] == "html"
    assert article_payload["source_kind"] == "systems"
    assert article_payload["source_ref"] == goblin_slug
    assert article_payload["source_page_ref"] == f"systems:{goblin_slug}"
    assert "Scimitar" in article_payload["body_markdown"]
    assert article_payload["image"] is None


def test_api_can_update_and_clear_session_articles(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-article-update-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-article-update-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Initial Orders",
            "body_markdown": "Meet at the north gate.",
        },
    )

    assert create_response.status_code == 200
    article_id = create_response.get_json()["article"]["id"]

    forbidden_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(player_token),
        json={
            "title": "Player Rewrite",
            "body_markdown": "This should not save.",
        },
    )

    assert forbidden_update.status_code == 403

    update_response = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Updated Orders",
            "body_markdown": "Meet at the south gate.",
        },
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()["article"]
    assert updated_payload["title"] == "Updated Orders"
    assert updated_payload["body_markdown"] == "Meet at the south gate."

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))

    assert start_response.status_code == 200

    reveal_response = client.post(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/reveal",
        headers=api_headers(dm_token),
    )

    assert reveal_response.status_code == 200
    assert reveal_response.get_json()["article"]["is_revealed"] is True

    revealed_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Late Rewrite",
            "body_markdown": "This should not save either.",
        },
    )

    assert revealed_update.status_code == 400
    assert revealed_update.get_json()["error"]["code"] == "validation_error"

    forbidden_clear = client.delete(
        "/api/v1/campaigns/linden-pass/session/articles/revealed",
        headers=api_headers(player_token),
    )

    assert forbidden_clear.status_code == 403

    clear_response = client.delete(
        "/api/v1/campaigns/linden-pass/session/articles/revealed",
        headers=api_headers(dm_token),
    )

    assert clear_response.status_code == 200
    clear_payload = clear_response.get_json()
    assert clear_payload["deleted_article_ids"] == [article_id]
    assert clear_payload["deleted_articles"][0]["title"] == "Updated Orders"

    dm_session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert dm_session_response.status_code == 200
    assert dm_session_response.get_json()["revealed_articles"] == []
