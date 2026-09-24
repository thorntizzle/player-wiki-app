"""Business saves preserve their complete row group, including failed commits."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from player_wiki.auth_store import AuthStore
from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries
from player_wiki.db import close_db, get_db, get_db_query_metrics, init_database, reset_db_query_metrics
from player_wiki.models import Campaign
from player_wiki.systems_mutations import (
    prepare_systems_mutation, save_campaign_override, save_campaign_sources,
    save_shared_core_entry, save_shared_core_permission,
)
from player_wiki.systems_service import SystemsService
from player_wiki.systems_store import SystemsStore


CAMPAIGN = "transaction-test"
LIBRARY = "TRANSACTION-TEST"
ENTRY = "item|transaction-test|stone"
TABLES = (
    "campaign_system_policies", "campaign_enabled_sources", "campaign_entry_overrides",
    "systems_entries", "systems_shared_entry_edit_events", "auth_audit_log", "systems_revision",
)
OPERATIONS = ("sources", "override", "permission", "entry")


class Repository:
    def __init__(self, library=LIBRARY):
        self.library = library

    def get(self):
        return self

    def get_campaign(self, slug):
        return Campaign(title="Transaction test", slug=slug, summary="", system="DND-5E",
                        current_session=1, source_wiki_root="", player_content_dir="", assets_dir="",
                        systems_library_slug=self.library)


@pytest.fixture
def transaction_app(tmp_path):
    app = Flask(__name__)
    app.config.update(DB_PATH=Path(tmp_path / "transactions.sqlite3"), TESTING=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_database()
        store = SystemsStore()
        store.upsert_library(LIBRARY, title="Transaction test", system_code="DND-5E")
        for source in ("A", "B"):
            store.upsert_source(LIBRARY, source, title=source, license_class="srd_cc")
            store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id=source,
                                                is_enabled=True, default_visibility="players")
        store.upsert_campaign_policy(CAMPAIGN, library_slug=LIBRARY)
        store.upsert_entry(LIBRARY, "A", entry_key=ENTRY, entry_type="item", slug="stone", title="Before")
    return app


def snapshot(connection):
    return {table: sorted(tuple(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall())
            for table in TABLES}


def source_values():
    return dict(updates=[dict(source_id=source, is_enabled=False, default_visibility="dm")
                         for source in ("A", "B")], actor_user_id=None,
                acknowledge_proprietary=False, can_set_private=False)


def operation_values(operation):
    return {
        "sources": source_values(),
        "override": dict(entry_key=ENTRY, visibility_override="dm", is_enabled_override=False,
                         actor_user_id=None, can_set_private=False),
        "permission": dict(allow_dm_shared_core_entry_edits=True, actor_user_id=None),
        "entry": dict(title="After"),
    }[operation]


def save(operation, service, auth):
    values = operation_values(operation)
    if operation == "sources":
        return save_campaign_sources(service, auth, CAMPAIGN, audit_source="api", **values)
    if operation == "override":
        return save_campaign_override(service, auth, CAMPAIGN, audit_source="api", **values)
    if operation == "permission":
        return save_shared_core_permission(service, auth, CAMPAIGN, **values)
    return save_shared_core_entry(service, auth, CAMPAIGN, "stone", actor_user_id=None, **values)


def direct_save(operation, service, **ownership):
    method = getattr(service, {
        "sources": "update_campaign_sources", "override": "update_campaign_entry_override",
        "permission": "update_campaign_shared_core_entry_edit_permission", "entry": "update_shared_core_entry",
    }[operation])
    args = (CAMPAIGN, "stone") if operation == "entry" else (CAMPAIGN,)
    return method(*args, **operation_values(operation), **ownership)


def assert_metrics(*, commits, rollbacks):
    metrics = get_db_query_metrics()
    assert metrics["commit_count"] == commits
    assert metrics["rollback_count"] == rollbacks
    assert metrics["commit_time_ms"] >= 0 and metrics["rollback_time_ms"] >= 0


@pytest.mark.parametrize("operation", OPERATIONS)
def test_success_is_one_observable_commit_with_required_audits(transaction_app, monkeypatch, operation):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)
            original = auth.insert_audit_event
            pending_tokens = []

            def observe_pending(**values):
                original(**values)
                assert snapshot(observer) == before
                pending_tokens.append(service.get_durable_revision())

            monkeypatch.setattr(auth, "insert_audit_event", observe_pending)
            reset_db_query_metrics()
            save(operation, service, auth)
            assert_metrics(commits=1, rollbacks=0)
            assert not connection.in_transaction
            after = snapshot(observer)
            assert after == snapshot(connection) and after != before
            assert len(after["auth_audit_log"]) == (2 if operation == "sources" else 1)
            assert len(after["systems_shared_entry_edit_events"]) == (1 if operation == "entry" else 0)
            assert pending_tokens and pending_tokens[-1] == service.get_durable_revision()
            assert after["systems_revision"] != before["systems_revision"]


FAULTS = [
    ("sources", "upsert_campaign_policy", 1),
    ("sources", "upsert_campaign_enabled_source", 1),
    ("sources", "upsert_campaign_enabled_source", 2),
    ("sources", "insert_audit_event", 1), ("sources", "insert_audit_event", 2),
    ("override", "upsert_campaign_policy", 1), ("override", "upsert_campaign_entry_override", 1),
    ("override", "insert_audit_event", 1), ("permission", "upsert_campaign_policy", 1),
    ("permission", "insert_audit_event", 1), ("entry", "upsert_entry", 1),
    ("entry", "record_shared_entry_edit_event", 1), ("entry", "insert_audit_event", 1),
]


@pytest.mark.parametrize("operation,boundary,ordinal", FAULTS)
def test_required_row_failure_rolls_back_all_rows_and_revision(transaction_app, monkeypatch, operation, boundary, ordinal):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        owner = auth if boundary == "insert_audit_event" else service.store
        original = getattr(owner, boundary)
        count = 0
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)

            def fail_after_write(*args, **kwargs):
                nonlocal count
                result = original(*args, **kwargs)
                count += 1
                assert snapshot(observer) == before
                if count == ordinal:
                    raise RuntimeError("required row failure")
                return result

            monkeypatch.setattr(owner, boundary, fail_after_write)
            reset_db_query_metrics()
            with pytest.raises(RuntimeError, match="required row failure"):
                save(operation, service, auth)
            assert_metrics(commits=0, rollbacks=1)
            assert count == ordinal and not connection.in_transaction
            assert snapshot(observer) == snapshot(connection) == before
            connection.execute("CREATE TABLE subsequent_unrelated(value)")
            connection.execute("INSERT INTO subsequent_unrelated VALUES (1)")
            connection.commit()
            assert snapshot(observer) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_real_commit_failure_preserves_observer_and_chained_recovery(transaction_app, monkeypatch, operation, rollback_fails):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        connection.executescript("CREATE TABLE tx_parent(id PRIMARY KEY); CREATE TABLE tx_child(id REFERENCES tx_parent(id) DEFERRABLE INITIALLY DEFERRED);")
        original = auth.insert_audit_event

        def violate_deferred_constraint(**values):
            original(**values)
            connection.execute("INSERT INTO tx_child VALUES (999)")

        monkeypatch.setattr(auth, "insert_audit_event", violate_deferred_constraint)
        if rollback_fails:
            connection.set_authorizer(lambda action, arg, *_: sqlite3.SQLITE_DENY
                                      if action == sqlite3.SQLITE_TRANSACTION and arg == "ROLLBACK"
                                      else sqlite3.SQLITE_OK)
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)
            reset_db_query_metrics()
            expected = sqlite3.DatabaseError if rollback_fails else sqlite3.IntegrityError
            with pytest.raises(expected) as caught:
                save(operation, service, auth)
            assert_metrics(commits=1, rollbacks=1)
            assert snapshot(observer) == before
            assert connection.in_transaction is rollback_fails
            if rollback_fails:
                assert isinstance(caught.value.__context__, sqlite3.IntegrityError)
                connection.set_authorizer(None)
                connection.rollback()
            assert snapshot(connection) == before
            assert connection.execute("SELECT * FROM tx_child").fetchall() == []
            connection.execute("INSERT INTO tx_parent VALUES (1)")
            connection.commit()
            assert snapshot(observer) == before


@pytest.mark.parametrize("operation", OPERATIONS)
def test_body_and_rollback_failure_retains_original_error(transaction_app, monkeypatch, operation):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        original = auth.insert_audit_event
        body_error = RuntimeError("audit body failure")

        def fail_audit(**values):
            original(**values)
            raise body_error

        monkeypatch.setattr(auth, "insert_audit_event", fail_audit)
        connection.set_authorizer(lambda action, arg, *_: sqlite3.SQLITE_DENY
                                  if action == sqlite3.SQLITE_TRANSACTION and arg == "ROLLBACK"
                                  else sqlite3.SQLITE_OK)
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)
            reset_db_query_metrics()
            with pytest.raises(sqlite3.DatabaseError) as caught:
                save(operation, service, auth)
            assert caught.value.__context__ is body_error
            assert_metrics(commits=0, rollbacks=1)
            assert connection.in_transaction and snapshot(observer) == before
            connection.set_authorizer(None)
            connection.rollback()
            assert snapshot(connection) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("audited", [False, True])
def test_self_owner_rejects_active_transaction_before_initialization(transaction_app, monkeypatch, operation, audited):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        connection.execute("CREATE TABLE caller_work(value)")
        connection.execute("INSERT INTO caller_work VALUES (1)")
        monkeypatch.setattr(service, "get_campaign_library", lambda *_: pytest.fail("initialization entered"))
        reset_db_query_metrics()
        with pytest.raises(RuntimeError, match="explicit joining"):
            save(operation, service, auth) if audited else direct_save(operation, service)
        assert_metrics(commits=0, rollbacks=0)
        assert connection.in_transaction
        assert connection.execute("SELECT value FROM caller_work").fetchone()[0] == 1
        connection.rollback()


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("complete", ["commit", "rollback", "error"])
def test_explicit_join_preserves_caller_ownership(transaction_app, monkeypatch, operation, complete):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        prepared = prepare_systems_mutation(service, CAMPAIGN)
        connection.execute("CREATE TABLE caller_work(value)")
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO caller_work VALUES (1)")
            monkeypatch.setattr(service, "get_campaign_library", lambda *_: pytest.fail("joined seed"))
            if complete == "error":
                method = "upsert_entry" if operation == "entry" else "upsert_campaign_policy"
                original = getattr(service.store, method)

                def failed_write(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError("joined write failure")

                monkeypatch.setattr(service.store, method, failed_write)
            reset_db_query_metrics()
            if complete == "error":
                with pytest.raises(RuntimeError, match="joined write failure"):
                    direct_save(operation, service, commit=False, prepared=prepared)
            else:
                direct_save(operation, service, commit=False, prepared=prepared)
            assert_metrics(commits=0, rollbacks=0)
            assert connection.in_transaction and snapshot(observer) == before
            assert connection.execute("SELECT value FROM caller_work").fetchone()[0] == 1
            if complete == "commit":
                connection.commit()
                assert snapshot(observer) != before
                assert observer.execute("SELECT value FROM caller_work").fetchone()[0] == 1
            else:
                connection.rollback()
                assert snapshot(observer) == before
                assert observer.execute("SELECT value FROM caller_work").fetchall() == []


@pytest.mark.parametrize("operation", OPERATIONS)
def test_audit_fault_evicts_aborted_warm_character_values(transaction_app, monkeypatch, operation):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        read_service = service.character_read_view()
        entries = lambda: [(row.entry_key, row.title) for row in _list_campaign_enabled_entries(read_service, CAMPAIGN, "item")]
        before_entries = entries()
        before_token = service.get_durable_revision()
        pending = []
        original = auth.insert_audit_event

        def warm_then_fail(**values):
            original(**values)
            pending.append(service.get_durable_revision())
            entries()
            raise RuntimeError("audit failure after warming")

        monkeypatch.setattr(auth, "insert_audit_event", warm_then_fail)
        with pytest.raises(RuntimeError, match="audit failure after warming"):
            save(operation, service, auth)
        assert pending[0] != before_token == service.get_durable_revision()
        assert entries() == before_entries
        monkeypatch.setattr(auth, "insert_audit_event", original)
        save(operation, service, auth)
        assert service.get_durable_revision() not in {before_token, *pending}
        expected = [] if operation in {"sources", "override"} else [(ENTRY, "After" if operation == "entry" else "Before")]
        assert entries() == expected


@pytest.mark.parametrize("operation", OPERATIONS)
def test_postcommit_cache_failure_keeps_complete_save(transaction_app, monkeypatch, operation):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()

        def fail_presentation():
            raise RuntimeError("postcommit cache failure")

        monkeypatch.setattr("player_wiki.systems_mutations._finish_mutation", fail_presentation)
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            before = snapshot(observer)
            reset_db_query_metrics()
            with pytest.raises(RuntimeError, match="postcommit cache failure"):
                save(operation, service, auth)
            assert_metrics(commits=1, rollbacks=0)
            after = snapshot(observer)
            assert after != before and not get_db().in_transaction
            assert len(after["auth_audit_log"]) == (2 if operation == "sources" else 1)
            assert len(after["systems_shared_entry_edit_events"]) == (1 if operation == "entry" else 0)


@pytest.mark.parametrize("stale", [False, True])
def test_catalog_initialization_finishes_before_business_writes(transaction_app, stale):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository("DND-5E")), AuthStore()
        if stale:
            service.ensure_builtin_library_seeded("DND-5E")
            get_db().execute("UPDATE systems_entries SET metadata_json='{}' WHERE library_slug='DND-5E' AND source_id='RULES'")
            get_db().commit()
        statements = []
        get_db().set_trace_callback(statements.append)
        save_shared_core_permission(service, auth, CAMPAIGN,
                                    allow_dm_shared_core_entry_edits=True, actor_user_id=None)
        get_db().set_trace_callback(None)
        first_business = next(index for index, sql in enumerate(statements)
                              if "INSERT INTO campaign_system_policies" in sql)
        assert any(sql == "COMMIT" for sql in statements[:first_business])
        assert [sql for sql in statements[first_business:] if sql == "COMMIT"] == ["COMMIT"]
        assert not any("INSERT INTO systems_entries" in sql or "INSERT INTO systems_sources" in sql
                       for sql in statements[first_business:])
        assert service.get_campaign_policy(CAMPAIGN).allow_dm_shared_core_entry_edits


@pytest.mark.parametrize("operation,readback", [
    ("sources", "get_campaign_enabled_source"), ("override", "get_campaign_entry_override"),
    ("permission", "get_campaign_policy"), ("entry", "get_shared_entry_edit_event"),
])
def test_required_readback_failure_rolls_back_saved_group(transaction_app, monkeypatch, operation, readback):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        connection = get_db()
        before = snapshot(connection)
        original = getattr(service.store, readback)

        def fail_saved_readback(*args, **kwargs):
            result = original(*args, **kwargs)
            if connection.in_transaction and service.get_durable_revision() != before["systems_revision"][0][1]:
                raise RuntimeError("required readback failed")
            return result

        monkeypatch.setattr(service.store, readback, fail_saved_readback)
        with pytest.raises(RuntimeError, match="required readback failed"):
            save(operation, service, auth)
        assert not connection.in_transaction
        assert snapshot(connection) == before
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            assert snapshot(observer) == before


def test_proprietary_acknowledgment_rolls_back_with_source_audit(transaction_app, monkeypatch):
    with transaction_app.test_request_context("/"):
        service, auth = SystemsService(SystemsStore(), Repository()), AuthStore()
        service.store.upsert_source(LIBRARY, "PROTECTED", title="Protected", license_class="proprietary_private")
        service.store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY,
                                                    source_id="PROTECTED", is_enabled=False, default_visibility="players")
        before = snapshot(get_db())
        original = auth.insert_audit_event

        def fail_ack_audit(**values):
            original(**values)
            assert service.store.get_campaign_policy(CAMPAIGN).proprietary_acknowledged_at is not None
            raise RuntimeError("ack audit unavailable")

        monkeypatch.setattr(auth, "insert_audit_event", fail_ack_audit)
        with pytest.raises(RuntimeError, match="ack audit unavailable"):
            save_campaign_sources(service, auth, CAMPAIGN, audit_source="api", actor_user_id=None,
                                  can_set_private=False, acknowledge_proprietary=True,
                                  updates=[dict(source_id="PROTECTED", is_enabled=True, default_visibility="players")])
        assert snapshot(get_db()) == before


@pytest.mark.parametrize("commit", [False, True])
def test_all_participating_stores_preserve_explicit_join_and_standalone_defaults(transaction_app, commit):
    with transaction_app.app_context():
        store, connection = SystemsStore(), get_db()
        before = snapshot(connection)
        ownership = {} if commit else {"commit": False}
        with sqlite3.connect(transaction_app.config["DB_PATH"]) as observer:
            reset_db_query_metrics()
            store.upsert_campaign_policy(CAMPAIGN, library_slug=LIBRARY,
                                         allow_dm_shared_core_entry_edits=True, **ownership)
            store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id="A",
                                                is_enabled=False, default_visibility="dm", **ownership)
            store.upsert_campaign_entry_override(CAMPAIGN, library_slug=LIBRARY, entry_key=ENTRY,
                                                visibility_override="dm", is_enabled_override=False, **ownership)
            store.upsert_entry(LIBRARY, "A", entry_key=ENTRY, entry_type="item", slug="stone", title="After", **ownership)
            store.record_shared_entry_edit_event(campaign_slug=CAMPAIGN, library_slug=LIBRARY, source_id="A",
                                                entry_key=ENTRY, entry_slug="stone", original_source_identity={},
                                                edited_fields=["title"], actor_user_id=None,
                                                audit_event_type="campaign_systems_shared_entry_updated", audit_metadata={}, **ownership)
            assert_metrics(commits=5 if commit else 0, rollbacks=0)
            assert connection.in_transaction is not commit
            if commit:
                assert snapshot(observer) == snapshot(connection) != before
            else:
                assert snapshot(observer) == before != snapshot(connection)
                connection.rollback()
                assert snapshot(connection) == before


def test_join_requires_matching_prepared_context_without_taking_caller_work(transaction_app):
    with transaction_app.app_context():
        service = SystemsService(SystemsStore(), Repository())
        other = SystemsService(service.store, Repository())
        prepared = prepare_systems_mutation(service, CAMPAIGN)
        before = snapshot(get_db())
        with pytest.raises(RuntimeError, match="prepared context"):
            direct_save("sources", service, commit=False, prepared=prepared)
        get_db().execute("BEGIN IMMEDIATE")
        for candidate_service, candidate_context in ((service, None), (other, prepared)):
            with pytest.raises(RuntimeError, match="prepared context"):
                direct_save("sources", candidate_service, commit=False, prepared=candidate_context)
            assert get_db().in_transaction
            assert snapshot(get_db()) == before
        get_db().rollback()
