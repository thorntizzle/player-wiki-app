from __future__ import annotations

from pathlib import Path
import logging
from io import BytesIO

import pytest
from flask import g, request, url_for

from player_wiki.auth import VIEW_AS_SESSION_KEY
from PIL import Image


RECOVERY_EXTENSIONS = (
    "player_wiki_reconciler",
    "character_publication_coordinator",
    "character_deletion_coordinator",
)


def _observe_recovery(app, monkeypatch):
    calls = []
    for name in RECOVERY_EXTENSIONS:
        def recover(*, limit, _name=name, **kwargs):
            calls.append((_name, limit, kwargs))
            return {"recovered": 0, "conflict": 0, "pending": 0}

        monkeypatch.setattr(app.extensions[name], "recover_pending", recover)
    return calls


def _static_asset(app):
    path = next(path for path in Path(app.static_folder).rglob("*.css") if path.is_file())
    return "/static/" + path.relative_to(app.static_folder).as_posix(), path.read_bytes()


def test_static_file_preserves_delivery_without_any_recovery(app, client, monkeypatch):
    calls = _observe_recovery(app, monkeypatch)
    url, contents = _static_asset(app)
    matched = app.url_map.bind("localhost").match(url)
    assert matched[0] == "static"

    response = client.get(url)
    assert response.status_code == 200
    assert response.data == contents
    assert response.mimetype == "text/css"
    assert response.headers["ETag"]
    assert response.headers["Last-Modified"]
    assert client.head(url).data == b""
    assert client.get(url, headers={"If-None-Match": response.headers["ETag"]}).status_code == 304
    partial = client.get(url, headers={"Range": "bytes=2-5"})
    assert partial.status_code == 206
    assert partial.data == contents[2:6]
    assert client.get("/static/recovery-admission-missing.css").status_code == 404
    assert calls == []


def test_static_looking_dynamic_endpoint_still_recovers(app, client, monkeypatch):
    app.add_url_rule("/static/recovery-dynamic.css", endpoint="recovery_dynamic", view_func=lambda: request.endpoint)
    calls = _observe_recovery(app, monkeypatch)
    response = client.get("/static/recovery-dynamic.css")
    assert response.status_code == 200
    assert response.data == b"recovery_dynamic"
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)


def test_restricted_campaign_asset_denial_still_recovers(app, client, monkeypatch, set_campaign_visibility):
    set_campaign_visibility("linden-pass", wiki="players")
    calls = _observe_recovery(app, monkeypatch)
    response = client.get("/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")
    assert response.status_code == 302
    assert "/sign-in?next=" in response.headers["Location"]
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)


@pytest.mark.parametrize("variant", (
    "get", "head", "options", "query", "etag-hit", "etag-miss",
    "modified-hit", "modified-miss", "range", "range-unsatisfiable",
    "missing", "missing-head", "unsafe",
))
def test_matched_static_variants_skip_each_recovery_and_lease(
    app, client, monkeypatch, variant,
):
    calls = _observe_recovery(app, monkeypatch)
    acquisitions = []
    monkeypatch.setattr(
        "player_wiki.app.acquire_runtime_state_lease",
        lambda path: acquisitions.append(path) or pytest.fail("static recovery lease"),
    )
    url, contents = _static_asset(app)
    initial = client.get(url)
    etag = initial.headers["ETag"]
    modified = initial.headers["Last-Modified"]
    method, headers, status = "GET", {}, 200
    if variant == "head":
        method = "HEAD"
    elif variant == "options":
        method = "OPTIONS"
    elif variant == "query":
        url += "?v=123&endpoint=dynamic"
    elif variant.startswith("etag"):
        headers = {"If-None-Match": etag if variant == "etag-hit" else '"unmatched"'}
        status = 304 if variant == "etag-hit" else 200
    elif variant.startswith("modified"):
        headers = {"If-Modified-Since": modified if variant == "modified-hit" else "Thu, 01 Jan 1970 00:00:00 GMT"}
        status = 304 if variant == "modified-hit" else 200
    elif variant == "range":
        headers, status = {"Range": "bytes=2-5"}, 206
    elif variant == "range-unsatisfiable":
        headers, status = {"Range": f"bytes={len(contents)+1}-"}, 416
    elif variant in {"missing", "missing-head"}:
        url, status = "/static/recovery-admission-missing.css", 404
        method = "HEAD" if variant == "missing-head" else "GET"
    elif variant == "unsafe":
        url, status = "/static/..%2Fapp.py", 404
    response = client.open(url, method=method, headers=headers)
    assert response.status_code == status
    if method == "HEAD" or status == 304:
        assert response.data == b""
    elif status == 200 and method == "GET":
        assert response.data == contents
    if method == "OPTIONS":
        assert {"GET", "HEAD", "OPTIONS"} <= set(response.headers["Allow"].split(", "))
    if variant == "head":
        assert response.content_length == len(contents)
    if status in {200, 206, 304} and method != "OPTIONS":
        assert response.headers["ETag"] == etag
        assert response.headers["Cache-Control"] == initial.headers["Cache-Control"]
    if status == 206:
        assert response.data == contents[2:6]
        assert response.headers["Content-Range"] == f"bytes 2-5/{len(contents)}"
    if status == 416:
        assert response.headers["Content-Range"] == f"bytes */{len(contents)}"
    assert calls == []
    assert acquisitions == []


@pytest.mark.parametrize(("path", "method", "status"), (
    ("/ordinary-dynamic.css", "GET", 200),
    ("/static", "GET", 404),
    ("/no-such-route.css", "GET", 404),
    ("/static/no-such-file.css", "POST", 405),
))
def test_nonstatic_routing_and_errors_remain_eligible(app, client, monkeypatch, path, method, status):
    app.add_url_rule("/ordinary-dynamic.css", endpoint="ordinary_dynamic", view_func=lambda: "dynamic")
    calls = _observe_recovery(app, monkeypatch)
    response = client.open(path, method=method)
    assert response.status_code == status
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)
    assert all(limit == 8 for _, limit, _ in calls)
    assert calls[0][2] == {}
    assert callable(calls[1][2]["runtime_state_lease_provider"])
    assert calls[1][2] == calls[2][2]


@pytest.mark.parametrize("endpoint", (
    "campaign_asset", "campaign_session_article_image", "character_portrait_asset",
))
@pytest.mark.parametrize("scenario", ("public-missing", "anonymous-denied", "member-denied", "view-as-denied"))
def test_stateful_asset_requests_remain_eligible_after_identity(
    app, client, monkeypatch, set_campaign_visibility, users, sign_in, endpoint, scenario,
):
    scope = {"campaign_asset": "wiki", "campaign_session_article_image": "session", "character_portrait_asset": "characters"}[endpoint]
    visibility = "public" if scenario == "public-missing" else "dm"
    set_campaign_visibility("linden-pass", **{scope: visibility})
    if scenario == "member-denied":
        sign_in(users["party"]["email"], users["party"]["password"])
    elif scenario == "view-as-denied":
        sign_in(users["admin"]["email"], users["admin"]["password"])
        with client.session_transaction() as session:
            session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    with app.test_request_context():
        arguments = {
            "campaign_asset": {"asset_path": "missing.png"},
            "campaign_session_article_image": {"article_id": 99999},
            "character_portrait_asset": {"character_slug": "missing-character"},
        }[endpoint]
        url = url_for(endpoint, campaign_slug="linden-pass", **arguments)
    calls = _observe_recovery(app, monkeypatch)
    response = client.get(url)
    assert response.status_code == (302 if scenario == "anonymous-denied" else 404)
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)


def test_public_campaign_asset_success_still_recovers(app, client, monkeypatch):
    calls = _observe_recovery(app, monkeypatch)
    response = client.get("/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)


@pytest.mark.parametrize("asset", ("session", "portrait"))
def test_manager_image_success_still_recovers(app, client, monkeypatch, sign_in, users, asset):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    image.seek(0)
    if asset == "session":
        response = client.post(
            "/campaigns/linden-pass/session/articles",
            data={"title": "Recovery asset", "body_markdown": "Image fixture", "image_file": (image, "recovery.png")},
            content_type="multipart/form-data",
        )
        url = "/campaigns/linden-pass/session-article-images/1"
    else:
        # The legacy app fixture sets DB_PATH after app construction. Bind the
        # mutation coordinator to that same synthetic database before upload.
        app.extensions["character_publication_coordinator"].database_path = Path(app.config["DB_PATH"])
        with app.app_context():
            record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
            assert record is not None
            revision = record.state_record.revision
        response = client.post(
            "/campaigns/linden-pass/characters/arden-march/personal/portrait",
            data={"expected_revision": revision, "portrait_file": (image, "recovery.png"), "portrait_alt": "Fixture", "mode": "read", "page": "portrait"},
            content_type="multipart/form-data",
        )
        url = "/campaigns/linden-pass/characters/arden-march/portrait"
    assert response.status_code == 302
    calls = _observe_recovery(app, monkeypatch)
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype.startswith("image/")
    assert response.data
    assert [name for name, _, _ in calls] == list(RECOVERY_EXTENSIONS)


@pytest.mark.parametrize("path", ("/favicon.ico", "/healthz", "/livez", "/readyz"))
def test_existing_exact_probe_exclusions(app, client, monkeypatch, path):
    calls = _observe_recovery(app, monkeypatch)
    client.get(path)
    assert calls == []


@pytest.mark.parametrize("endpoint", (
    "campaign_systems_mechanics_impact_queue", "campaign_systems_mechanics_impact_detail",
))
def test_existing_impact_endpoint_exclusions(app, client, monkeypatch, endpoint):
    with app.test_request_context():
        url = url_for(endpoint, campaign_slug="linden-pass")
    calls = _observe_recovery(app, monkeypatch)
    client.get(url)
    assert calls == []


@pytest.mark.parametrize("path", ("/", "/static/missing.css"))
def test_content_envelope_precedes_recovery_including_static(app, client, monkeypatch, path):
    app.config["MAX_CONTENT_LENGTH"] = 8
    calls = _observe_recovery(app, monkeypatch)
    response = client.get(path, data=b"123456789")
    assert response.status_code == 413
    assert calls == []
    names = [hook.__name__ for hook in app.before_request_funcs[None]]
    assert names[:2] == ["initialize_request_diagnostics", "enforce_request_content_envelope"]


@pytest.mark.parametrize("guard", ("csrf", "view-as"))
def test_identity_refusals_precede_recovery(app, client, monkeypatch, users, sign_in, guard):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    if guard == "csrf":
        app.config["CSRF_ENABLED"] = True
    else:
        with client.session_transaction() as session:
            session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    calls = _observe_recovery(app, monkeypatch)
    response = client.post("/campaigns/linden-pass/session/articles", data={"title": "Refused"})
    assert response.status_code == (400 if guard == "csrf" else 403)
    assert calls == []


@pytest.mark.parametrize("failing_hook", RECOVERY_EXTENSIONS)
@pytest.mark.parametrize("outcome", ("exception", "attention"))
def test_recovery_failures_keep_order_diagnostics_response_and_lease_custody(
    app, client, monkeypatch, caplog, failing_hook, outcome,
):
    events = []

    class Lease:
        def close(self):
            events.append("close")

    lease = Lease()
    monkeypatch.setattr("player_wiki.app.acquire_runtime_state_lease", lambda path: events.append("acquire") or lease)
    for name in RECOVERY_EXTENSIONS:
        def recover(*, limit, _name=name, **kwargs):
            assert g.request_started_at
            assert limit == 8
            events.append(_name)
            if _name != RECOVERY_EXTENSIONS[0]:
                assert kwargs["runtime_state_lease_provider"]() is lease
            if _name == failing_hook:
                if outcome == "exception":
                    raise RuntimeError("private-recovery-error-detail")
                return {"recovered": 0, "conflict": 1, "pending": 2}
            return {"recovered": 0, "conflict": 0, "pending": 0}
        monkeypatch.setattr(app.extensions[name], "recover_pending", recover)
    app.add_url_rule("/recovery-dispatch", endpoint="recovery_dispatch", view_func=lambda: events.append("view") or "ok")
    caplog.set_level(logging.WARNING)
    response = client.get("/recovery-dispatch")
    assert response.status_code == 200 and response.data == b"ok"
    assert [event for event in events if event in RECOVERY_EXTENSIONS] == list(RECOVERY_EXTENSIONS)
    assert events.count("acquire") == events.count("close") == 1
    assert events[-2:] == ["close", "view"]
    messages = [record.message for record in caplog.records]
    assert any("exception_type=RuntimeError" in message if outcome == "exception" else "conflict=1 pending=2" in message for message in messages)
    assert all("private-recovery-error-detail" not in message for message in messages)
