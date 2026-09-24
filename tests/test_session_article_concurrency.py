from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import sqlite3
from threading import Barrier

import pytest

from player_wiki.campaign_session_service import (
    CampaignSessionValidationError, SessionArticleEditConflictError, SessionArticleImageUpload,
)
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki import session_models
from player_wiki.session_models import session_article_base_token
from tests.helpers.api_test_helpers import api_headers, issue_api_token, embedded_png_payload


SLUG = "linden-pass"
URL = f"/api/v1/campaigns/{SLUG}/session/articles"


def loaded_token(service, article_id):
    return session_article_base_token(service.get_article(SLUG, article_id), service.get_article_image(SLUG, article_id))


@pytest.fixture
def article(app):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        record = service.create_article(SLUG, title="Original", body_markdown="Body.", image_upload=SessionArticleImageUpload("image.png", "image/png", b"original", "Alt", "Caption"))
        return record.id, loaded_token(service, record.id)


def test_digest_covers_exact_content_and_reuses_loaded_image(app, article):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        record = service.get_article(SLUG, article[0])
        image = service.get_article_image(SLUG, article[0])
        baseline = session_article_base_token(record, image)
        for field, value in {"campaign_slug": "other", "id": 999, "status": "revealed", "title": "other", "body_markdown": "other", "source_page_ref": "other"}.items():
            assert session_article_base_token(replace(record, **{field: value}), image) != baseline
        for field, value in {"filename": "other.png", "media_type": "image/jpeg", "alt_text": "other", "caption": "other", "data_blob": b"other"}.items():
            assert session_article_base_token(record, replace(image, **{field: value})) != baseline
        assert session_article_base_token(record) != baseline
        digest = image.content_digest
        assert image._digest_blob is image.data_blob
        assert image.content_digest is digest
        image.data_blob = b"changed in memory"
        assert image.content_digest != digest


@pytest.mark.parametrize("site", ["update_article", "upsert_article_image", "update_article_image_metadata", "bump_state_revision"])
def test_aggregate_rolls_back_every_precommit_write(app, article, monkeypatch, site):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        revision = service.get_live_revision(SLUG)
        original = getattr(service.store, site)
        def fail_after_write(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("precommit fault")
        monkeypatch.setattr(service.store, site, fail_after_write)
        options = {"image_metadata": ("new alt", "new caption")} if site == "update_article_image_metadata" else {"image_upload": SessionArticleImageUpload("new.png", "image/png", b"new")}
        with pytest.raises(RuntimeError, match="precommit fault"):
            service.update_article(SLUG, article[0], title="New title", body_markdown="New body", base_token=article[1], **options)
        assert loaded_token(service, article[0]) == article[1]
        assert service.get_live_revision(SLUG) == revision
        assert not get_db().in_transaction


def test_creation_commit_failure_leaves_no_partial_aggregate(app):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        articles = service.list_articles(SLUG)
        revision = service.get_live_revision(SLUG)
        get_db().execute("PRAGMA defer_foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            service.create_article(SLUG, title="Not committed", body_markdown="Body", created_by_user_id=999999,
                                   image_upload=SessionArticleImageUpload("new.png", "image/png", b"new"))
        assert service.list_articles(SLUG) == articles
        assert service.get_live_revision(SLUG) == revision
        assert not get_db().in_transaction


def test_normalized_noop_has_no_writes_and_one_changed_aggregate_revision(app, article):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        connection = get_db()
        before = connection.total_changes
        revision = service.get_live_revision(SLUG)
        service.update_article(SLUG, article[0], title=" Original ", body_markdown=" Body. ", base_token=article[1], image_metadata=(" Alt ", " Caption "))
        assert loaded_token(service, article[0]) == article[1]
        assert connection.total_changes == before
        reset_db_query_metrics()
        service.update_article(SLUG, article[0], title="Changed", base_token=article[1], image_upload=SessionArticleImageUpload("new.png", "image/png", b"new"))
        assert get_db_query_metrics()["commit_count"] == 1
        assert service.get_live_revision(SLUG) == revision + 1
        assert loaded_token(service, article[0]) != article[1]


@pytest.mark.parametrize("second_edit", ["text", "image", "metadata"])
def test_two_connections_cannot_overwrite_same_baseline(app, article, second_edit):
    barrier = Barrier(2)
    service = app.extensions["campaign_session_service"]
    def save(title):
        with app.app_context():
            barrier.wait(timeout=5)
            try:
                if title == "Second" and second_edit == "image":
                    service.attach_article_image(SLUG, article[0], filename="new.png", media_type="image/png", data_blob=b"new", base_token=article[1])
                elif title == "Second" and second_edit == "metadata":
                    service.update_article_image_metadata(SLUG, article[0], alt_text="New", base_token=article[1])
                else:
                    service.update_article(SLUG, article[0], title=title, base_token=article[1])
            except SessionArticleEditConflictError:
                return "conflict"
            return title
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, ["First", "Second"]))
    assert results.count("conflict") == 1
    with app.app_context():
        record = service.get_article(SLUG, article[0])
        assert record.title in results or (second_edit != "text" and record.title == "Original")
        assert loaded_token(service, article[0]) != article[1]


@pytest.mark.parametrize("competitor", ["reveal", "delete", "image", "metadata"])
def test_stale_baseline_rejected_after_competing_mutation(app, article, competitor):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        if competitor == "reveal":
            service.begin_session(SLUG)
            service.reveal_article(SLUG, article[0], author_display_name="DM")
        elif competitor == "delete":
            service.delete_article(SLUG, article[0])
        elif competitor == "image":
            service.attach_article_image(SLUG, article[0], filename="new.png", media_type="image/png", data_blob=b"new", base_token=article[1])
        else:
            service.update_article_image_metadata(SLUG, article[0], alt_text="new", base_token=article[1])
        revision = service.get_live_revision(SLUG)
        with pytest.raises(SessionArticleEditConflictError):
            service.update_article(SLUG, article[0], title="Stale overwrite", base_token=article[1])
        assert service.get_live_revision(SLUG) == revision
        record = service.get_article(SLUG, article[0])
        assert record is None or record.title == "Original"


@pytest.mark.parametrize("token", [None, "", "v1:" + "A" * 64, "v1:" + "0" * 63, "v2:" + "0" * 64, 123])
def test_api_requires_valid_baseline(client, app, users, article, token):
    headers = api_headers(issue_api_token(app, users["dm"]["email"], label="baseline-test"))
    response = client.put(f"{URL}/{article[0]}", headers=headers, json={"base_token": token, "title": "Overwrite", "body_markdown": "Body"})
    assert response.status_code == 400
    assert "Refresh" in response.get_json()["error"]["message"]
    with app.app_context():
        assert loaded_token(app.extensions["campaign_session_service"], article[0]) == article[1]


def test_api_returns_uniform_token_and_conflict(client, app, users, article):
    headers = api_headers(issue_api_token(app, users["dm"]["email"], label="baseline-test"))
    payload = {"base_token": article[1], "title": "Winner", "body_markdown": "Body", "image": embedded_png_payload()}
    winner = client.put(f"{URL}/{article[0]}", headers=headers, json=payload)
    assert winner.status_code == 200
    assert winner.get_json()["article"]["base_token"] != article[1]
    assert client.put(f"{URL}/{article[0]}", headers=headers, json=payload).status_code == 409


@pytest.mark.parametrize("surface", ["session/articles", "dm-content/staged-articles"])
@pytest.mark.parametrize("deleted", [False, True])
def test_native_rejection_retains_draft_and_original_token(client, app, sign_in, users, article, surface, deleted):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        if deleted:
            service.delete_article(SLUG, article[0])
        else:
            service.update_article(SLUG, article[0], title="Peer winner", base_token=article[1])
    response = client.post(f"/campaigns/{SLUG}/{surface}/{article[0]}", data={"base_token": article[1], "title": '<script>draft</script>', "body_markdown": "Retained body", "image_alt": "Retained alt", "image_caption": "Retained caption", "image_file": (BytesIO(b"rejected bytes"), "draft.png")})
    assert response.status_code == 409
    html = response.get_data(as_text=True)
    assert article[1] in html
    assert "Retained body" in html and "Retained alt" in html and "Retained caption" in html
    assert "&lt;script&gt;draft&lt;/script&gt;" in html and "<script>draft</script>" not in html
    assert "Reselect your image file" in html


@pytest.mark.parametrize("method", ["attach_article_image", "update_article_image_metadata"])
def test_internal_image_edits_have_no_unconditional_bypass(app, article, method):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        arguments = {"filename": "new.png", "media_type": "image/png", "data_blob": b"new"} if method == "attach_article_image" else {"alt_text": "new"}
        with pytest.raises(CampaignSessionValidationError, match="out of date"):
            getattr(service, method)(SLUG, article[0], **arguments)
        assert loaded_token(service, article[0]) == article[1]


def test_creation_validates_upload_before_any_write(app):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        before = get_db().total_changes
        with pytest.raises(CampaignSessionValidationError):
            service.create_article(SLUG, title="Invalid", body_markdown="Body", image_upload=SessionArticleImageUpload("bad.exe", "image/png", b"bad"))
        assert get_db().total_changes == before


def test_commit_constraint_failure_rolls_back_text_image_and_revision(app, article):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        revision = service.get_live_revision(SLUG)
        get_db().execute("PRAGMA defer_foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            service.update_article(SLUG, article[0], title="Not committed", base_token=article[1], updated_by_user_id=999999,
                                   image_upload=SessionArticleImageUpload("new.png", "image/png", b"new"))
        assert loaded_token(service, article[0]) == article[1]
        assert service.get_live_revision(SLUG) == revision


@pytest.mark.parametrize("competitor", ["reveal", "delete"])
def test_committed_edit_precedes_competing_reveal_or_delete(app, article, competitor):
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        service.update_article(SLUG, article[0], title="Latest stored title", base_token=article[1],
                               image_upload=SessionArticleImageUpload("new.png", "image/png", b"new"))
    # A separate connection must see the complete committed aggregate.
    with app.app_context():
        if competitor == "reveal":
            service.begin_session(SLUG)
            record, _ = service.reveal_article(SLUG, article[0], author_display_name="DM")
            assert record.title == "Latest stored title"
            assert service.get_article_image(SLUG, article[0]).data_blob == b"new"
        else:
            service.delete_article(SLUG, article[0])
            assert service.get_article(SLUG, article[0]) is None
            assert service.store.get_article_image(article[0]) is None


@pytest.mark.parametrize("surface", ["session/articles", "dm-content/staged-articles", "api"])
def test_view_as_cannot_submit_article_edits(client, app, sign_in, users, article, surface):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["dm"]["id"]
    submitted = {"base_token": article[1], "title": "Forbidden", "body_markdown": "Forbidden"}
    if surface == "api":
        response = client.put(f"{URL}/{article[0]}", json=submitted)
        assert response.get_json()["error"]["code"] == "view_as_read_only"
    else:
        response = client.post(f"/campaigns/{SLUG}/{surface}/{article[0]}", data=submitted)
    assert response.status_code == 403
    with app.app_context():
        assert loaded_token(app.extensions["campaign_session_service"], article[0]) == article[1]


@pytest.mark.parametrize("surface", ["session/articles", "dm-content/staged-articles"])
def test_native_missing_baseline_retains_draft_with_refresh_guidance(client, sign_in, users, article, surface):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(f"/campaigns/{SLUG}/{surface}/{article[0]}", data={"title": "Old form", "body_markdown": "Keep this text"})
    assert response.status_code == 400
    assert b"Keep this text" in response.data
    assert b"Refresh and compare" in response.data
    assert b'data-session-article-validation-retained="1"' in response.data
    assert article[1].encode() not in response.data


def test_manager_projection_batches_queries_and_hashes_loaded_image_once(client, app, sign_in, users, monkeypatch):
    service = app.extensions["campaign_session_service"]
    blobs = [b"projection image one", b"projection image two", b"projection image three"]
    def create(index):
        with app.app_context():
            service.create_article(SLUG, title=f"Projection {index}", body_markdown="Body",
                                   image_upload=SessionArticleImageUpload("image.png", "image/png", blobs[index]))
    create(0)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    # Initialize fixture-backed campaign/system presentation before measuring steady projection.
    assert client.get(f"/campaigns/{SLUG}/session/live-state?view=dm&dm_view=staged").status_code == 200
    real_sha256 = session_models.hashlib.sha256
    hashed_images = []
    def count_image_hash(data=b"", *args, **kwargs):
        if data in blobs:
            hashed_images.append(data)
        return real_sha256(data, *args, **kwargs)
    monkeypatch.setattr(session_models.hashlib, "sha256", count_image_hash)
    with client:
        response = client.get(f"/campaigns/{SLUG}/session/live-state?view=dm&dm_view=staged")
        assert response.status_code == 200
        one_queries = get_db_query_metrics()["query_count"]
    assert hashed_images == blobs[:1]
    create(1)
    create(2)
    hashed_images.clear()
    with client:
        response = client.get(f"/campaigns/{SLUG}/session/live-state?view=dm&dm_view=staged")
        assert response.status_code == 200
        assert get_db_query_metrics()["query_count"] == one_queries
    assert sorted(hashed_images) == sorted(blobs)
    html = response.get_json()["staged_articles_html"]
    assert html.count('name="base_token"') == 3
    assert html.count("session-article-images/") == 3
