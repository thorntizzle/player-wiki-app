from __future__ import annotations

import pytest

import player_wiki.api as api_module
from player_wiki.campaign_session_store import CampaignSessionConflictError
from tests.helpers.api_test_helpers import (
    api_headers,
    embedded_png_payload,
    issue_api_token,
)


ARTICLES_URL = "/api/v1/campaigns/linden-pass/session/articles"
CLEAR_URL = f"{ARTICLES_URL}/revealed"


def _manager_headers(app, users) -> dict[str, str]:
    return api_headers(
        issue_api_token(
            app,
            users["dm"]["email"],
            label="session-lifecycle-transport",
        )
    )


def _create_article(client, headers, *, title: str = "Lifecycle", image: bool = False) -> int:
    payload = {
        "mode": "manual",
        "title": title,
        "body_markdown": f"{title} body.",
    }
    if image:
        payload["image"] = embedded_png_payload(
            filename=f"{title.lower().replace(' ', '-')}.png",
            alt_text=f"{title} alt",
            caption=f"{title} caption",
        )
    response = client.post(ARTICLES_URL, headers=headers, json=payload)
    assert response.status_code == 200
    return response.get_json()["article"]["id"]


def _start_session(client, headers) -> int:
    response = client.post(
        "/api/v1/campaigns/linden-pass/session/start",
        headers=headers,
    )
    assert response.status_code == 200
    return response.get_json()["session"]["id"]


def _reveal(client, headers, article_id: int):
    return client.post(f"{ARTICLES_URL}/{article_id}/reveal", headers=headers)


def _article(app, service, article_id: int):
    with app.app_context():
        return service.get_article("linden-pass", article_id)


def _image(app, service, article_id: int):
    with app.app_context():
        return service.get_article_image("linden-pass", article_id)


def _articles(app, service):
    with app.app_context():
        return service.list_articles("linden-pass")


def _messages(app, service, session_id: int):
    with app.app_context():
        return service.list_messages(session_id, can_manage_session=True)


def _revision(app, service) -> int:
    with app.app_context():
        return service.get_live_revision("linden-pass")


def _state(app, service):
    with app.app_context():
        return service.store.get_state("linden-pass")


def test_session_article_lifecycle_preserves_auth_missing_campaign_and_methods(
    client,
    app,
    users,
):
    manager_headers = _manager_headers(app, users)
    player_headers = api_headers(
        issue_api_token(
            app,
            users["party"]["email"],
            label="session-lifecycle-player",
        )
    )
    urls = (
        (f"{ARTICLES_URL}/1/reveal", "POST"),
        (f"{ARTICLES_URL}/1", "DELETE"),
        (CLEAR_URL, "DELETE"),
    )
    for url, method in urls:
        assert client.open(url, method=method).status_code == 401
        forbidden = client.open(url, method=method, headers=player_headers)
        assert forbidden.status_code == 403
        assert forbidden.get_json()["error"] == {
            "code": "forbidden",
            "message": "You do not have permission to manage this session.",
        }
        missing = client.open(
            url.replace("linden-pass", "missing-campaign"),
            method=method,
            headers=manager_headers,
        )
        assert missing.status_code == 404

        options = client.options(url)
        assert options.status_code == 200
        assert method in options.headers["Allow"]
        assert "HEAD" not in options.headers["Allow"]

    adapter = app.url_map.bind("localhost")
    shared_path = f"{ARTICLES_URL}/1"
    assert adapter.match(shared_path, method="PUT")[0] == "api.session_article_update"
    assert adapter.match(shared_path, method="DELETE")[0] == "api.session_article_delete"
    assert adapter.match(shared_path, method="OPTIONS")[0] == "api.session_article_update"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("post", f"{ARTICLES_URL}/1/reveal"),
        ("delete", f"{ARTICLES_URL}/1"),
        ("delete", CLEAR_URL),
    ],
)
def test_session_article_lifecycle_preserves_stable_api_413(client, app, method, url):
    app.config["MAX_CONTENT_LENGTH"] = 64
    response = getattr(client, method)(
        url,
        data=b"x" * 65,
        content_type="application/json",
    )
    assert response.status_code == 413
    assert response.get_json() == {
        "ok": False,
        "error": {
            "code": "request_too_large",
            "message": "The request is too large.",
        },
    }


def test_session_article_lifecycle_ignores_malformed_request_bodies(
    client,
    app,
    users,
):
    headers = _manager_headers(app, users)
    first_id = _create_article(client, headers, title="Reveal malformed")
    second_id = _create_article(client, headers, title="Delete malformed")
    _start_session(client, headers)

    reveal = client.post(
        f"{ARTICLES_URL}/{first_id}/reveal",
        headers={**headers, "Content-Type": "application/json"},
        data="{",
    )
    assert reveal.status_code == 200
    delete = client.delete(
        f"{ARTICLES_URL}/{second_id}",
        headers={**headers, "Content-Type": "application/json"},
        data="{",
    )
    assert delete.status_code == 200
    clear = client.delete(
        CLEAR_URL,
        headers={**headers, "Content-Type": "application/json"},
        data="{",
    )
    assert clear.status_code == 200
    assert clear.get_json()["deleted_article_ids"] == [first_id]


def test_session_article_lifecycle_preserves_exact_service_arguments_and_payloads(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers, title="Exact args")
    _start_session(client, headers)
    calls: list[tuple[str, tuple, dict]] = []

    original_reveal = service.reveal_article
    original_delete = service.delete_article
    original_clear = service.delete_revealed_articles

    def record_reveal(*args, **kwargs):
        calls.append(("reveal", args, kwargs))
        return original_reveal(*args, **kwargs)

    def record_delete(*args, **kwargs):
        calls.append(("delete", args, kwargs))
        return original_delete(*args, **kwargs)

    def record_clear(*args, **kwargs):
        calls.append(("clear", args, kwargs))
        return original_clear(*args, **kwargs)

    monkeypatch.setattr(service, "reveal_article", record_reveal)
    reveal = _reveal(client, headers, article_id)
    assert reveal.status_code == 200
    reveal_payload = reveal.get_json()
    assert reveal_payload["article"]["is_revealed"] is True
    assert set(reveal_payload["message"]) == {
        "id",
        "session_id",
        "campaign_slug",
        "message_type",
        "body_text",
        "author_user_id",
        "author_display_name",
        "article_id",
        "created_at",
    }
    assert reveal_payload["message"]["message_type"] == "article_reveal"
    assert reveal_payload["message"]["body_text"] == ""
    assert reveal_payload["message"]["article_id"] == article_id
    assert calls[0][1] == ("linden-pass", article_id)
    assert calls[0][2] == {
        "revealed_by_user_id": users["dm"]["id"],
        "author_display_name": "Dungeon Master",
    }

    monkeypatch.setattr(service, "delete_article", record_delete)
    deleted = client.delete(f"{ARTICLES_URL}/{article_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.get_json()["article"]["id"] == article_id
    assert deleted.get_json()["article"]["image"] is None
    assert calls[1] == ("delete", ("linden-pass", article_id), {})

    empty_revision = _revision(app, service)
    monkeypatch.setattr(service, "delete_revealed_articles", record_clear)
    cleared = client.delete(CLEAR_URL, headers=headers)
    assert cleared.status_code == 200
    assert cleared.get_json() == {
        "ok": True,
        "deleted_articles": [],
        "deleted_article_ids": [],
    }
    assert calls[2][1] == ("linden-pass",)
    assert calls[2][2] == {"updated_by_user_id": users["dm"]["id"]}
    assert _revision(app, service) == empty_revision


def test_session_article_delete_intentionally_skips_redundant_user_lookup(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    article_id = _create_article(client, headers, title="No lookup")

    original_lookup = api_module.get_current_user
    calls = 0

    def count_lookup():
        nonlocal calls
        calls += 1
        return original_lookup()

    monkeypatch.setattr(api_module, "get_current_user", count_lookup)
    response = client.delete(f"{ARTICLES_URL}/{article_id}", headers=headers)
    assert response.status_code == 200
    assert calls == 1


@pytest.mark.parametrize(
    ("setup", "expected_message"),
    [
        ("no_active", "Begin a session before revealing articles in the chat."),
        ("missing", "That session article could not be found."),
        ("duplicate", "That session article has already been revealed."),
    ],
)
def test_session_article_reveal_preserves_validation_failures(
    client,
    app,
    users,
    setup,
    expected_message,
):
    headers = _manager_headers(app, users)
    article_id = _create_article(client, headers)
    if setup != "no_active":
        _start_session(client, headers)
    if setup == "missing":
        article_id = 999999
    elif setup == "duplicate":
        assert _reveal(client, headers, article_id).status_code == 200

    response = _reveal(client, headers, article_id)
    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": {"code": "validation_error", "message": expected_message},
    }


def test_session_article_reveal_conflict_rolls_back_with_exact_message(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers)
    session_id = _start_session(client, headers)
    baseline = _revision(app, service)

    def conflict(*args, **kwargs):
        raise CampaignSessionConflictError("forced reveal conflict")

    monkeypatch.setattr(service.store, "reveal_article_in_session", conflict)
    response = _reveal(client, headers, article_id)
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That session article could not be revealed. Refresh the page and try again.",
    }
    assert _article(app, service, article_id).status == "staged"
    assert _messages(app, service, session_id) == []
    assert _revision(app, service) == baseline


def test_session_article_reveal_runtime_fault_rolls_back_article_message_and_revision(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers)
    session_id = _start_session(client, headers)
    baseline = _revision(app, service)

    def fail_revision(*args, **kwargs):
        raise RuntimeError("reveal precommit fault")

    monkeypatch.setattr(service.store, "bump_state_revision", fail_revision)
    with pytest.raises(RuntimeError, match="reveal precommit fault"):
        _reveal(client, headers, article_id)
    assert _article(app, service, article_id).status == "staged"
    assert _messages(app, service, session_id) == []
    assert _revision(app, service) == baseline


@pytest.mark.parametrize("fault_site", ["image", "article", "datetime"])
def test_session_article_reveal_response_fault_keeps_committed_state(
    client,
    app,
    users,
    monkeypatch,
    fault_site,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers, image=True)
    session_id = _start_session(client, headers)
    baseline = _revision(app, service)

    if fault_site == "image":
        def fail_image(*args, **kwargs):
            raise RuntimeError("reveal response fault")

        monkeypatch.setattr(service, "get_article_image", fail_image)
    elif fault_site == "article":
        def fail_url(*args, **kwargs):
            raise RuntimeError("reveal response fault")

        monkeypatch.setattr(api_module, "url_for", fail_url)
    else:
        original_isoformat = api_module.isoformat
        calls = 0

        def fail_message_datetime(value):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("reveal response fault")
            return original_isoformat(value)

        monkeypatch.setattr(api_module, "isoformat", fail_message_datetime)

    with pytest.raises(RuntimeError, match="reveal response fault"):
        _reveal(client, headers, article_id)
    assert _article(app, service, article_id).status == "revealed"
    messages = _messages(app, service, session_id)
    assert len(messages) == 1
    assert messages[0].article_id == article_id
    assert _revision(app, service) == baseline + 1


def test_session_article_delete_removes_staged_or_revealed_with_linked_data(
    client,
    app,
    users,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    staged_id = _create_article(client, headers, title="Staged delete", image=True)
    revealed_id = _create_article(client, headers, title="Revealed delete", image=True)
    session_id = _start_session(client, headers)
    assert _reveal(client, headers, revealed_id).status_code == 200

    assert client.delete(f"{ARTICLES_URL}/{staged_id}", headers=headers).status_code == 200
    assert client.delete(f"{ARTICLES_URL}/{revealed_id}", headers=headers).status_code == 200
    assert _article(app, service, staged_id) is None
    assert _article(app, service, revealed_id) is None
    assert _image(app, service, staged_id) is None
    assert _image(app, service, revealed_id) is None
    assert _messages(app, service, session_id) == []


def test_session_article_delete_missing_and_conflict_preserve_state(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    missing = client.delete(f"{ARTICLES_URL}/999999", headers=headers)
    assert missing.status_code == 400
    assert missing.get_json()["error"]["message"] == "That session article could not be found."

    article_id = _create_article(client, headers)
    baseline = _revision(app, service)

    def conflict(*args, **kwargs):
        raise CampaignSessionConflictError("forced delete conflict")

    monkeypatch.setattr(service.store, "delete_article", conflict)
    response = client.delete(f"{ARTICLES_URL}/{article_id}", headers=headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That session article could not be deleted. Refresh the page and try again.",
    }
    assert _article(app, service, article_id) is not None
    assert _revision(app, service) == baseline


def test_session_article_delete_runtime_fault_rolls_back_linked_data_and_revision(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers, image=True)
    session_id = _start_session(client, headers)
    assert _reveal(client, headers, article_id).status_code == 200
    baseline = _revision(app, service)

    def fail_revision(*args, **kwargs):
        raise RuntimeError("delete precommit fault")

    monkeypatch.setattr(service.store, "bump_state_revision", fail_revision)
    with pytest.raises(RuntimeError, match="delete precommit fault"):
        client.delete(f"{ARTICLES_URL}/{article_id}", headers=headers)
    assert _article(app, service, article_id) is not None
    assert _image(app, service, article_id) is not None
    assert len(_messages(app, service, session_id)) == 1
    assert _revision(app, service) == baseline


def test_session_article_delete_response_fault_keeps_deletion_and_null_actor(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_article(client, headers)
    baseline = _revision(app, service)

    def fail_url(*args, **kwargs):
        raise RuntimeError("delete response fault")

    monkeypatch.setattr(api_module, "url_for", fail_url)
    with pytest.raises(RuntimeError, match="delete response fault"):
        client.delete(f"{ARTICLES_URL}/{article_id}", headers=headers)
    assert _article(app, service, article_id) is None
    assert _revision(app, service) == baseline + 1
    assert _state(app, service).updated_by_user_id is None


def test_session_revealed_articles_clear_preserves_order_staged_and_single_revision(
    client,
    app,
    users,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    staged_id = _create_article(client, headers, title="Keep staged")
    first_id = _create_article(client, headers, title="First revealed")
    second_id = _create_article(client, headers, title="Second revealed")
    session_id = _start_session(client, headers)
    assert _reveal(client, headers, first_id).status_code == 200
    assert _reveal(client, headers, second_id).status_code == 200
    baseline = _revision(app, service)

    response = client.delete(CLEAR_URL, headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["deleted_article_ids"] == [second_id, first_id]
    assert [item["title"] for item in payload["deleted_articles"]] == [
        "Second revealed",
        "First revealed",
    ]
    assert [item.id for item in _articles(app, service)] == [staged_id]
    assert _messages(app, service, session_id) == []
    assert _revision(app, service) == baseline + 1
    assert _state(app, service).updated_by_user_id == users["dm"]["id"]


def test_session_revealed_articles_clear_conflict_rolls_back_full_batch(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    first_id = _create_article(client, headers, title="First")
    second_id = _create_article(client, headers, title="Second")
    session_id = _start_session(client, headers)
    assert _reveal(client, headers, first_id).status_code == 200
    assert _reveal(client, headers, second_id).status_code == 200
    baseline = _revision(app, service)
    original_delete = service.store.delete_article
    calls = 0

    def conflict_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CampaignSessionConflictError("forced clear conflict")
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(service.store, "delete_article", conflict_second)
    response = client.delete(CLEAR_URL, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That session article could not be deleted. Refresh the page and try again.",
    }
    assert {item.id for item in _articles(app, service)} == {first_id, second_id}
    assert len(_messages(app, service, session_id)) == 2
    assert _revision(app, service) == baseline


def test_session_revealed_articles_clear_mid_serialization_fault_keeps_full_batch(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    first_id = _create_article(client, headers, title="First")
    second_id = _create_article(client, headers, title="Second")
    session_id = _start_session(client, headers)
    assert _reveal(client, headers, first_id).status_code == 200
    assert _reveal(client, headers, second_id).status_code == 200
    baseline = _revision(app, service)
    original_url_for = api_module.url_for
    calls = 0

    def fail_second_article(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("clear response fault")
        return original_url_for(*args, **kwargs)

    monkeypatch.setattr(api_module, "url_for", fail_second_article)
    with pytest.raises(RuntimeError, match="clear response fault"):
        client.delete(CLEAR_URL, headers=headers)
    assert _articles(app, service) == []
    assert _messages(app, service, session_id) == []
    assert _revision(app, service) == baseline + 1
