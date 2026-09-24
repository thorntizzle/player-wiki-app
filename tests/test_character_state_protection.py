from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

import player_wiki.character_state_service as state_service_module
from player_wiki.character_service import build_initial_state
from player_wiki.character_store import CharacterStateConflictError, CharacterStateUnavailableError
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG
from tests.test_character_reconciliation import (
    _coordinator, _create_existing, _definition, _deletion_coordinator, _metadata,
    _paths, _publish_portrait, _update_payload,
)


def _separate_connection(app, action):
    def run():
        with app.app_context():
            return action()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run).result(timeout=10)


def _state_tuple(record):
    return (record.revision, record.state_json, record.updated_at, record.updated_by_user_id)


@pytest.mark.parametrize("operation_kind", ["markdown_import", "content_api_update", "character_update_apply", "interactive_update"])
@pytest.mark.parametrize("boundary", ["after_commit", "after_repository_pending"])
@pytest.mark.parametrize("state_changed", [False, True])
def test_loaded_save_refuses_publication_and_owner_completes_without_conflict(app, operation_kind, boundary, state_changed):
    with app.app_context():
        prior = _create_existing(app, "protected-save")
        store = app.extensions["character_state_store"]
        service = app.extensions["character_state_service"]
        definition, metadata, changed = _update_payload(prior)
        desired = changed if state_changed else deepcopy(prior.state_record.state)
        attempts = []

        def intercept(event, _operation_id):
            if event != boundary:
                return
            captured = _state_tuple(store.get_exact_state("linden-pass", "protected-save"))
            def save():
                with pytest.raises(CharacterStateConflictError):
                    service.update_player_notes(prior, expected_revision=prior.state_record.revision, notes_markdown="racing draft")
            _separate_connection(app, save)
            assert _state_tuple(store.get_exact_state("linden-pass", "protected-save")) == captured
            attempts.append(event)

        owner = _coordinator(app, intercept)
        audit = {}
        if operation_kind == "character_update_apply":
            owner.auth_store = app.extensions["auth_store"]
            audit = {"audit_event_type": "character_update_applied", "audit_actor_user_id": app.config["TEST_USERS"]["dm"]["id"], "audit_metadata": {"operation_count": 1}}
        result = owner.update(prior, definition, metadata, desired,
            expected_revision=prior.state_record.revision, operation_kind=operation_kind, **audit)
        assert attempts == [boundary]
        assert result.state_record.state["notes"] != {"player_notes_markdown": "racing draft"}
        assert app.extensions["character_repository"].get_character("linden-pass", "protected-save") is not None
        assert get_db().execute("SELECT COUNT(*) FROM character_reconciliation_operations").fetchone()[0] == 0


def test_state_save_wins_before_publication_and_stale_owner_does_not_prepare(app):
    with app.app_context():
        prior = _create_existing(app, "save-first")
        paths = _paths(app, "save-first")
        pair = tuple(path.read_bytes() for path in paths)
        _separate_connection(app, lambda: app.extensions["character_state_service"].update_player_notes(
            prior, expected_revision=prior.state_record.revision, notes_markdown="saved first"))
        definition, metadata, _ = _update_payload(prior)
        with pytest.raises(CharacterStateConflictError):
            _coordinator(app, None).update(prior, definition, metadata, prior.state_record.state,
                expected_revision=prior.state_record.revision, operation_kind="markdown_import")
        assert tuple(path.read_bytes() for path in paths) == pair
        assert get_db().execute("SELECT COUNT(*) FROM character_reconciliation_operations").fetchone()[0] == 0


@pytest.mark.parametrize("system", ["DND-5E", "Xianxia"])
@pytest.mark.parametrize("boundary", ["after_commit", "after_repository_pending"])
def test_portrait_owner_protects_loaded_system_state_mutation(app, system, boundary):
    with app.app_context():
        definition = _definition("portrait-state-race", system=system)
        _coordinator(app, None).create(definition, _metadata(definition.character_slug),
            build_initial_state(definition), operation_kind="native_create")
        prior = app.extensions["character_repository"].get_character("linden-pass", definition.character_slug)
        store = app.extensions["character_state_store"]
        calls = []
        def intercept(event, _operation_id):
            if event != boundary:
                return
            exact = _state_tuple(store.get_exact_state("linden-pass", definition.character_slug))
            def save():
                service = app.extensions["character_state_service"]
                with pytest.raises(CharacterStateConflictError):
                    if system == "Xianxia":
                        service.update_xianxia_active_state(prior,
                            expected_revision=prior.state_record.revision, active_stance_name="Racing stance")
                    else:
                        service.update_player_notes(prior,
                            expected_revision=prior.state_record.revision, notes_markdown="Racing notes")
            _separate_connection(app, save)
            assert _state_tuple(store.get_exact_state("linden-pass", definition.character_slug)) == exact
            calls.append(event)
        result = _publish_portrait(app, prior,
            asset_ref=f"characters/{definition.character_slug}/portrait.webp",
            asset_bytes=b"synthetic-portrait", on_event=intercept)
        assert calls == [boundary]
        assert result.state_record.revision == prior.state_record.revision + 1
        assert get_db().execute("SELECT COUNT(*) FROM character_reconciliation_operations").fetchone()[0] == 0


@pytest.mark.parametrize("table", ["character_reconciliation_operations", "character_deletion_operations"])
@pytest.mark.parametrize("operation", ["write", "noop", "initialize"])
def test_current_schema_missing_protection_table_fails_closed(app, table, operation):
    with app.app_context():
        prior = _create_existing(app, "missing-protection-table")
        store = app.extensions["character_state_store"]
        connection = get_db()
        if operation == "initialize":
            connection.execute("DELETE FROM character_state WHERE character_slug = ?", (prior.definition.character_slug,))
        connection.execute(f"DROP TABLE {table}")
        connection.commit()
        before = store.get_exact_state("linden-pass", prior.definition.character_slug)
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            if operation == "noop":
                store.require_writable_state(prior.definition, expected_revision=prior.state_record.revision)
            elif operation == "initialize":
                store.initialize_state_if_missing(prior.definition, prior.state_record.state)
            else:
                store.replace_state(prior.definition, prior.state_record.state,
                    expected_revision=prior.state_record.revision)
        after = store.get_exact_state("linden-pass", prior.definition.character_slug)
        assert (None if after is None else _state_tuple(after)) == (None if before is None else _state_tuple(before))


@pytest.mark.parametrize("boundary", ["after_commit", "after_repository_pending"])
def test_deletion_cannot_be_undone_by_loaded_save_or_missing_state_initialization(app, boundary):
    with app.app_context():
        prior = _create_existing(app, "delete-race")
        store = app.extensions["character_state_store"]
        attempts = []
        def intercept(event, _operation_id):
            if event != boundary:
                return
            def save():
                with pytest.raises(CharacterStateConflictError):
                    store.replace_state(prior.definition, prior.state_record.state, expected_revision=prior.state_record.revision)
                with pytest.raises(CharacterStateConflictError):
                    store.initialize_state_if_missing(prior.definition, build_initial_state(prior.definition))
            _separate_connection(app, save)
            assert store.get_state("linden-pass", "delete-race") is None
            attempts.append(event)
        _deletion_coordinator(app, intercept).delete("linden-pass", "delete-race", operation_kind="content_api")
        assert attempts == [boundary]
        assert store.get_state("linden-pass", "delete-race") is None
        assert get_db().execute("SELECT COUNT(*) FROM character_deletion_operations").fetchone()[0] == 0


@pytest.mark.parametrize("journal_state", ["prepared", "repository_pending", "conflict"])
@pytest.mark.parametrize("same_state", [False, True])
def test_interrupted_owner_blocks_state_writes_without_altering_journal(app, journal_state, same_state):
    with app.app_context():
        prior = _create_existing(app, "interrupted")
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("synthetic interruption")
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            _coordinator(app, stop).update(prior, prior.definition, prior.import_metadata, prior.state_record.state,
                expected_revision=prior.state_record.revision, operation_kind="markdown_import")
        get_db().execute("UPDATE character_reconciliation_operations SET state = ?", (journal_state,))
        get_db().commit()
        before = tuple(get_db().execute("SELECT * FROM character_reconciliation_operations").fetchone())
        state = deepcopy(prior.state_record.state)
        if not same_state:
            state["notes"] = {"player_notes_markdown": "unsaved"}
        with pytest.raises(CharacterStateConflictError):
            app.extensions["character_state_store"].replace_state(prior.definition, state, expected_revision=prior.state_record.revision)
        assert tuple(get_db().execute("SELECT * FROM character_reconciliation_operations").fetchone()) == before


@pytest.mark.parametrize("protected", [False, True])
def test_avatar_noop_checks_current_revision_and_protection_without_writes(app, monkeypatch, protected):
    with app.app_context():
        prior = _create_existing(app, "avatar-noop")
        store = app.extensions["character_state_store"]
        service = app.extensions["character_state_service"]
        monkeypatch.setattr(state_service_module, "transition_divine_avatar_form", lambda *a, **kw: SimpleNamespace(changed=False))
        if protected:
            def stop(event, _operation_id):
                if event == "after_commit":
                    raise RuntimeError("hold")
            with pytest.raises(RuntimeError, match="hold"):
                _coordinator(app, stop).update(prior, prior.definition, prior.import_metadata, prior.state_record.state,
                    expected_revision=prior.state_record.revision, operation_kind="markdown_import")
        exact_before = _state_tuple(store.get_exact_state("linden-pass", "avatar-noop"))
        reset_db_query_metrics()
        if protected:
            with pytest.raises(CharacterStateConflictError):
                service.update_divine_avatar_form(prior, "test", "test", expected_revision=prior.state_record.revision)
        else:
            result = service.update_divine_avatar_form(prior, "test", "test", expected_revision=prior.state_record.revision)
            assert result.revision == prior.state_record.revision
        metrics = get_db_query_metrics()
        assert metrics["query_count"] == 1
        assert metrics["write_count"] == metrics["commit_count"] == metrics["rollback_count"] == 0
        assert _state_tuple(store.get_exact_state("linden-pass", "avatar-noop")) == exact_before
        with pytest.raises(CharacterStateConflictError):
            service.update_divine_avatar_form(prior, "test", "test", expected_revision=prior.state_record.revision + 1)


def test_commit_false_protection_refusal_preserves_caller_transaction_ownership(app):
    with app.app_context():
        prior = _create_existing(app, "caller-owned")
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("hold")
        with pytest.raises(RuntimeError, match="hold"):
            _coordinator(app, stop).update(prior, prior.definition, prior.import_metadata, prior.state_record.state,
                expected_revision=prior.state_record.revision, operation_kind="markdown_import")
        connection = get_db()
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE synthetic_caller_work (value TEXT)")
        connection.execute("INSERT INTO synthetic_caller_work VALUES ('retained')")
        with pytest.raises(CharacterStateConflictError):
            app.extensions["character_state_store"].replace_state(prior.definition, prior.state_record.state,
                expected_revision=prior.state_record.revision, commit=False)
        assert connection.in_transaction
        assert connection.execute("SELECT value FROM synthetic_caller_work").fetchone()[0] == "retained"
        connection.rollback()


@pytest.mark.parametrize("transport,draft_kind", [
    ("browser", "notes"), ("session", "notes"), ("api", "notes"),
    ("browser", "personal"), ("api", "personal"),
])
def test_loaded_draft_transport_preserves_draft_and_refuses_protected_write(app, client, sign_in, users, monkeypatch, set_campaign_visibility, transport, draft_kind):
    set_campaign_visibility(TEST_CAMPAIGN_SLUG, characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    service = app.extensions["character_state_service"]
    method = "update_player_notes" if draft_kind == "notes" else "update_personal_details"
    original = getattr(service, method)
    def raced(record, **kwargs):
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("hold")
        with pytest.raises(RuntimeError, match="hold"):
            _coordinator(app, stop).update(record, record.definition, record.import_metadata, record.state_record.state,
                expected_revision=record.state_record.revision, operation_kind="markdown_import")
        return original(record, **kwargs)
    monkeypatch.setattr(service, method, raced)
    with app.app_context():
        record = app.extensions["character_repository"].get_character(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)
        revision = record.state_record.revision
        exact = _state_tuple(app.extensions["character_state_store"].get_exact_state(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG))
    draft = "My unsaved draft <script>unsafe()</script>"
    payload = {"expected_revision": revision, "mode": "session", "page": draft_kind}
    if draft_kind == "notes":
        payload["player_notes_markdown"] = draft
    else:
        payload.update(physical_description_markdown=draft, background_markdown="My unsaved background")
    path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}/session/{draft_kind}"
    if transport == "api":
        response = client.patch("/api/v1" + path, json=payload)
        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "state_conflict"
    else:
        if transport == "session":
            payload["return_view"] = "session-character"
            with app.app_context():
                app.extensions["campaign_session_service"].begin_session(TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"])
        response = client.post(path, data=payload)
        assert response.status_code == 409
        html = response.get_data(as_text=True)
        assert "My unsaved draft &lt;script&gt;unsafe()&lt;/script&gt;" in html
        assert "Update not saved" in html
        assert "<script>unsafe()" not in html
        assert "character_reconciliation_operations" not in html
        assert "repository_pending" not in html
        assert "no-store" in response.headers["Cache-Control"]
    with app.app_context():
        assert _state_tuple(app.extensions["character_state_store"].get_exact_state(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)) == exact
        assert get_db().execute("SELECT state FROM character_reconciliation_operations").fetchone()[0] == "prepared"


@pytest.mark.parametrize("transport,draft_kind", [("browser", "notes"), ("session", "notes"), ("browser", "personal")])
def test_deletion_finishing_after_refused_save_still_preserves_draft(
    app, client, sign_in, users, monkeypatch, set_campaign_visibility, transport, draft_kind,
):
    set_campaign_visibility(TEST_CAMPAIGN_SLUG, characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    service = app.extensions["character_state_service"]
    method = "update_player_notes" if draft_kind == "notes" else "update_personal_details"
    original = getattr(service, method)
    def delete_around_refusal(record, **kwargs):
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("paused deletion")
        with pytest.raises(RuntimeError, match="paused deletion"):
            _deletion_coordinator(app, stop).delete(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG,
                operation_kind="content_api")
        try:
            return original(record, **kwargs)
        except CharacterStateUnavailableError:
            assert _separate_connection(app, lambda: _deletion_coordinator(app).recover_key(
                TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG))
            assert get_db().execute("SELECT COUNT(*) FROM character_deletion_operations").fetchone()[0] == 0
            raise
    monkeypatch.setattr(service, method, delete_around_refusal)
    with app.app_context():
        record = app.extensions["character_repository"].get_character(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)
        revision = record.state_record.revision
        if transport == "session":
            app.extensions["campaign_session_service"].begin_session(TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"])
    payload = {"expected_revision": revision, "mode": "session", "page": draft_kind}
    if draft_kind == "notes":
        payload["player_notes_markdown"] = "Draft retained after deletion"
    else:
        payload.update(physical_description_markdown="Draft retained after deletion", background_markdown="Background draft")
    if transport == "session":
        payload["return_view"] = "session-character"
    response = client.post(f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}/session/{draft_kind}", data=payload)
    assert response.status_code == 409
    assert "Draft retained after deletion" in response.get_data(as_text=True)
    assert "Update not saved" in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions["character_state_store"].get_exact_state(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG) is None


@pytest.mark.parametrize("page,expected_page", [("features", "features"), ("resources", "resources"), ("martial_arts", "martial_arts"), ("//untrusted.example", "overview")])
def test_protected_scalar_conflict_keeps_validated_session_subpage(
    app, client, sign_in, users, monkeypatch, set_campaign_visibility, page, expected_page,
):
    set_campaign_visibility(TEST_CAMPAIGN_SLUG, characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    service = app.extensions["character_state_service"]
    original = service.update_vitals
    def collide(record, **kwargs):
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("hold")
        with pytest.raises(RuntimeError, match="hold"):
            _coordinator(app, stop).update(record, record.definition, record.import_metadata, record.state_record.state,
                expected_revision=record.state_record.revision, operation_kind="markdown_import")
        return original(record, **kwargs)
    monkeypatch.setattr(service, "update_vitals", collide)
    with app.app_context():
        record = app.extensions["character_repository"].get_character(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)
        revision = record.state_record.revision
        app.extensions["campaign_session_service"].begin_session(TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"])
    response = client.post(f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}/session/vitals", data={
        "expected_revision": revision, "current_hp": 10, "temp_hp": 0,
        "return_view": "session-character", "mode": "session", "page": page,
    })
    assert response.status_code == 409
    html = response.get_data(as_text=True)
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "a" and attributes.get("aria-current") == "page":
                self.href = attributes["href"]
    links = Links()
    links.feed(html)
    assert urlsplit(links.href).netloc == ""
    assert parse_qs(urlsplit(links.href).query)["page"] == [expected_page]
