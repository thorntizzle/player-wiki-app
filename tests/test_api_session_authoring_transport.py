from __future__ import annotations

import pytest

import player_wiki.api as api_module
from player_wiki.campaign_session_service import CampaignSessionValidationError
from tests.helpers.api_test_helpers import (
    api_headers,
    embedded_png_payload,
    issue_api_token,
)


CREATE_URL = "/api/v1/campaigns/linden-pass/session/articles"


def _manager_headers(app, users) -> dict[str, str]:
    token = issue_api_token(
        app,
        users["dm"]["email"],
        label="session-authoring-transport",
    )
    return api_headers(token)


def _create_text_article(client, headers, *, title: str = "Original") -> int:
    response = client.post(
        CREATE_URL,
        headers=headers,
        json={
            "mode": "manual",
            "title": title,
            "body_markdown": "Original body.",
        },
    )
    assert response.status_code == 200
    return response.get_json()["article"]["id"]


def _list_articles(app, service):
    with app.app_context():
        return service.list_articles("linden-pass")


def _get_article(app, service, article_id: int):
    with app.app_context():
        return service.get_article("linden-pass", article_id)


def test_session_article_authoring_preserves_auth_json_and_method_contract(
    client,
    app,
    users,
):
    manager_headers = _manager_headers(app, users)
    player_headers = api_headers(
        issue_api_token(
            app,
            users["party"]["email"],
            label="session-authoring-player",
        )
    )

    assert client.post(CREATE_URL, json={}).status_code == 401
    forbidden = client.post(CREATE_URL, headers=player_headers, json={})
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == {
        "code": "forbidden",
        "message": "You do not have permission to manage this session.",
    }

    invalid_json = client.post(
        CREATE_URL,
        headers={**manager_headers, "Content-Type": "application/json"},
        data="{",
    )
    assert invalid_json.status_code == 400
    assert invalid_json.get_json()["error"]["code"] == "invalid_json"

    multipart = client.post(
        CREATE_URL,
        headers=manager_headers,
        data={"title": "Not JSON"},
    )
    assert multipart.status_code == 400
    assert multipart.get_json()["error"]["code"] == "validation_error"

    article_id = _create_text_article(client, manager_headers)
    update_url = f"{CREATE_URL}/{article_id}"
    assert client.put(update_url, json={}).status_code == 401
    assert client.put(update_url, headers=player_headers, json={}).status_code == 403
    invalid_update = client.put(
        update_url,
        headers={**manager_headers, "Content-Type": "application/json"},
        data="{",
    )
    assert invalid_update.status_code == 400
    assert invalid_update.get_json()["error"]["code"] == "invalid_json"

    for url, method in ((CREATE_URL, "POST"), (update_url, "PUT")):
        options = client.options(url)
        assert options.status_code == 200
        assert method in options.headers["Allow"]
        assert "HEAD" not in options.headers["Allow"]


def test_session_article_upload_preserves_frontmatter_image_derivation(
    client,
    app,
    users,
):
    headers = _manager_headers(app, users)
    response = client.post(
        CREATE_URL,
        headers=headers,
        json={
            "mode": "upload",
            "filename": "sealed-orders.md",
            "markdown_text": (
                "---\n"
                "title: Sealed Orders\n"
                "image: seal.png\n"
                "image_alt: Wax seal\n"
                "image_caption: Broken at midnight\n"
                "---\n\n"
                "# Sealed Orders\n\nRead this in private.\n"
            ),
            "referenced_image": embedded_png_payload("seal.png"),
        },
    )

    assert response.status_code == 200
    article = response.get_json()["article"]
    assert article["title"] == "Sealed Orders"
    assert article["body_markdown"] == "Read this in private."
    assert article["image"]["alt_text"] == "Wax seal"
    assert article["image"]["caption"] == "Broken at midnight"


@pytest.mark.parametrize("fault_site", ["prepare_article_image_upload", "create_article"])
def test_session_article_create_preserves_precommit_fault_boundary(
    client,
    app,
    users,
    monkeypatch,
    fault_site,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]

    def fail(*args, **kwargs):
        raise RuntimeError(f"{fault_site} fault")

    monkeypatch.setattr(service, fault_site, fail)
    payload = {
        "mode": "manual",
        "title": "Never durable",
        "body_markdown": "Must not persist.",
    }
    if fault_site == "prepare_article_image_upload":
        payload["image"] = embedded_png_payload()
    with pytest.raises(RuntimeError, match=f"{fault_site} fault"):
        client.post(CREATE_URL, headers=headers, json=payload)
    assert _list_articles(app, service) == []


@pytest.mark.parametrize("method", ["post", "put"])
def test_session_article_authoring_preserves_stable_api_413(
    client,
    app,
    method,
):
    app.config["MAX_CONTENT_LENGTH"] = 64
    url = CREATE_URL if method == "post" else f"{CREATE_URL}/1"
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


@pytest.mark.parametrize(
    ("attach_error", "expected_status", "article_survives"),
    [
        (CampaignSessionValidationError("rejected attachment"), 400, False),
        (RuntimeError("attachment fault"), None, True),
    ],
)
def test_session_article_create_preserves_attach_fault_durability(
    client,
    app,
    users,
    monkeypatch,
    attach_error,
    expected_status,
    article_survives,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]

    def fail_attach(*args, **kwargs):
        raise attach_error

    monkeypatch.setattr(service, "attach_article_image", fail_attach)
    request = lambda: client.post(
        CREATE_URL,
        headers=headers,
        json={
            "mode": "manual",
            "title": "Fault boundary",
            "body_markdown": "Created before attachment.",
            "image": embedded_png_payload(),
        },
    )

    if expected_status is None:
        with pytest.raises(RuntimeError, match="attachment fault"):
            request()
    else:
        response = request()
        assert response.status_code == expected_status
        assert response.get_json()["error"] == {
            "code": "validation_error",
            "message": "rejected attachment",
        }

    articles = _list_articles(app, service)
    assert bool(articles) is article_survives
    if articles:
        assert articles[0].title == "Fault boundary"


def test_session_article_create_preserves_cleanup_fault_precedence(
    client,
    app,
    users,
    monkeypatch,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]

    def reject_attach(*args, **kwargs):
        raise CampaignSessionValidationError("rejected attachment")

    def fail_cleanup(*args, **kwargs):
        raise RuntimeError("cleanup fault")

    monkeypatch.setattr(service, "attach_article_image", reject_attach)
    monkeypatch.setattr(service, "delete_article", fail_cleanup)

    with pytest.raises(RuntimeError, match="cleanup fault"):
        client.post(
            CREATE_URL,
            headers=headers,
            json={
                "mode": "manual",
                "title": "Cleanup boundary",
                "body_markdown": "Durable after cleanup failure.",
                "image": embedded_png_payload(),
            },
        )
    assert _list_articles(app, service)[0].title == "Cleanup boundary"


@pytest.mark.parametrize("fault_site", ["get_article_image", "serialize"])
def test_session_article_create_preserves_response_fault_durability(
    client,
    app,
    users,
    monkeypatch,
    fault_site,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]

    if fault_site == "get_article_image":
        def fail_response(*args, **kwargs):
            raise RuntimeError("response fault")

        monkeypatch.setattr(service, "get_article_image", fail_response)
    else:
        def fail_url(*args, **kwargs):
            raise RuntimeError("response fault")

        monkeypatch.setattr(api_module, "url_for", fail_url)

    with pytest.raises(RuntimeError, match="response fault"):
        client.post(
            CREATE_URL,
            headers=headers,
            json={
                "mode": "manual",
                "title": "Response boundary",
                "body_markdown": "Already durable.",
            },
        )
    assert _list_articles(app, service)[0].title == "Response boundary"


@pytest.mark.parametrize(
    ("fault_site", "error_type", "expected_status"),
    [
        ("prepare_article_image_upload", RuntimeError, None),
        ("attach_article_image", CampaignSessionValidationError, 400),
        ("attach_article_image", RuntimeError, None),
        ("update_article_image_metadata", CampaignSessionValidationError, 400),
        ("update_article_image_metadata", RuntimeError, None),
    ],
)
def test_session_article_update_preserves_fault_order_and_partial_durability(
    client,
    app,
    users,
    monkeypatch,
    fault_site,
    error_type,
    expected_status,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_text_article(client, headers)
    message = f"{fault_site} fault"

    def fail(*args, **kwargs):
        raise error_type(message)

    monkeypatch.setattr(service, fault_site, fail)
    payload = {
        "title": "Updated before later fault",
        "body_markdown": "Updated body.",
    }
    if fault_site in {"prepare_article_image_upload", "attach_article_image"}:
        payload["image"] = embedded_png_payload()
    else:
        payload["image_alt_text"] = "Updated alt"

    request = lambda: client.put(
        f"{CREATE_URL}/{article_id}",
        headers=headers,
        json=payload,
    )
    if expected_status is None:
        with pytest.raises(RuntimeError, match=message):
            request()
    else:
        response = request()
        assert response.status_code == expected_status
        assert response.get_json()["error"] == {
            "code": "validation_error",
            "message": message,
        }

    article = _get_article(app, service, article_id)
    if fault_site == "prepare_article_image_upload":
        assert article.title == "Original"
        assert article.body_markdown == "Original body."
    else:
        assert article.title == "Updated before later fault"
        assert article.body_markdown == "Updated body."


@pytest.mark.parametrize("fault_site", ["get_article_image", "serialize"])
def test_session_article_update_preserves_response_fault_durability(
    client,
    app,
    users,
    monkeypatch,
    fault_site,
):
    headers = _manager_headers(app, users)
    service = app.extensions["campaign_session_service"]
    article_id = _create_text_article(client, headers)

    if fault_site == "get_article_image":
        original = service.get_article_image
        calls = 0

        def fail_second_image_read(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("response fault")
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "get_article_image", fail_second_image_read)
    else:
        def fail_url(*args, **kwargs):
            raise RuntimeError("response fault")

        monkeypatch.setattr(api_module, "url_for", fail_url)

    with pytest.raises(RuntimeError, match="response fault"):
        client.put(
            f"{CREATE_URL}/{article_id}",
            headers=headers,
            json={
                "title": "Durable update",
                "body_markdown": "Committed before response rendering.",
            },
        )
    article = _get_article(app, service, article_id)
    assert article.title == "Durable update"
    assert article.body_markdown == "Committed before response rendering."


def test_session_article_update_metadata_omission_clears_other_field(
    client,
    app,
    users,
):
    headers = _manager_headers(app, users)
    create = client.post(
        CREATE_URL,
        headers=headers,
        json={
            "mode": "manual",
            "title": "Image metadata",
            "body_markdown": "Body.",
            "image": embedded_png_payload(
                alt_text="Original alt",
                caption="Original caption",
            ),
        },
    )
    article_id = create.get_json()["article"]["id"]

    update = client.put(
        f"{CREATE_URL}/{article_id}",
        headers=headers,
        json={
            "title": "Image metadata",
            "body_markdown": "Body.",
            "image_alt_text": "Replacement alt",
        },
    )
    assert update.status_code == 200
    assert update.get_json()["article"]["image"]["alt_text"] == "Replacement alt"
    assert update.get_json()["article"]["image"]["caption"] == ""
