"""Durable Systems identity and real cache/transaction lifecycle contracts."""
from __future__ import annotations

import json
import multiprocessing
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from flask import Flask

from player_wiki.db import close_db, get_db, init_database
from player_wiki.migrations import (
    MIGRATIONS, CURRENT_SCHEMA_SQL, SCHEMA_V13_SQL, SYSTEMS_REVISION_TABLES, MigrationHooks,
    calculate_migration_checksum, run_migrations,
)
from player_wiki.systems_store import SystemsStore
from player_wiki.systems_service import SystemsService
from player_wiki.models import Campaign
from player_wiki.character_builder_catalogs import (
    _builder_static_revision_key, _class_progression_for_builder,
    _clear_builder_static_bundle_cache,
    _RevisionBoundCacheKey, _builder_static_cache_get,
)
from player_wiki.character_builder_static_bundle import _build_common_builder_static_bundle


LIBRARY = "REVISION-TEST"
CAMPAIGN = "revision-test"
ENTRY = "item|revision-test|stone"


@pytest.mark.parametrize("revision_available", [True, False], ids=["changed", "unavailable"])
def test_active_combat_preparation_observes_external_committed_systems_change(app, monkeypatch, revision_available):
    from tests.test_combat_catalog_preparation import _services, _item, CAMPAIGN as combat_campaign

    service, pages = _services(app)
    with app.test_request_context("/"):
        _item(service)
        with service.combat_detail_read(combat_campaign, pages) as prepared:
            initial_library = prepared.library()
            assert next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
            connection = get_db()
            changes = connection.total_changes
            initial_revision = service.get_durable_revision()
            with sqlite3.connect(app.config["DB_PATH"]) as writer:
                writer.execute("UPDATE systems_libraries SET title='Externally changed library' WHERE library_slug='DND-5E'")
                writer.execute("UPDATE campaign_enabled_sources SET is_enabled=0 WHERE campaign_slug=? AND source_id='PHB'", (combat_campaign,))
            assert connection.total_changes == changes
            assert service.get_durable_revision() != initial_revision
            if not revision_available:
                monkeypatch.setattr(service, "get_durable_revision", lambda: None)
            assert prepared.library().title == "Externally changed library"
            assert prepared.library() is not initial_library
            assert not next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
            with sqlite3.connect(app.config["DB_PATH"]) as writer:
                writer.execute("UPDATE campaign_enabled_sources SET is_enabled=1 WHERE campaign_slug=? AND source_id='PHB'", (combat_campaign,))
            assert next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
            if not revision_available:
                assert prepared.prepared_library is None
        assert service._combat_detail_preparation(combat_campaign) is None


@pytest.mark.parametrize("read_kind", ["library", "sources"])
@pytest.mark.parametrize("revision_available", [True, False], ids=["changed", "unavailable"])
def test_active_combat_preparation_does_not_publish_capture_across_external_commit(
    app, monkeypatch, read_kind, revision_available,
):
    from flask import g
    from tests.test_combat_catalog_preparation import _services, _item, CAMPAIGN as combat_campaign

    service, pages = _services(app)
    with app.test_request_context("/"):
        _item(service)
        initial_title = service.ensure_builtin_library_seeded("DND-5E").title
        # Complete the repository refresh before measuring reader-local writes
        # so the interleaving below isolates the other connection's commit.
        service.get_campaign_library_slug(combat_campaign)
        revision_reader = service.get_durable_revision
        before_revision = revision_reader()
        connection = get_db()
        changes = connection.total_changes
        method = "ensure_builtin_library_seeded" if read_kind == "library" else "_build_campaign_source_states"
        original = getattr(service, method)
        captures = []

        def commit_after_read(*args, **kwargs):
            value = original(*args, **kwargs)
            captures.append(value)
            if len(captures) == 1:
                # Deterministic interleaving: the real read has completed, but
                # its caller has not received the captured value yet.
                with sqlite3.connect(app.config["DB_PATH"]) as writer:
                    writer.execute("UPDATE systems_libraries SET title='Committed during capture' WHERE library_slug='DND-5E'")
                    writer.execute("UPDATE campaign_enabled_sources SET is_enabled=0 WHERE campaign_slug=? AND source_id='PHB'", (combat_campaign,))
                if not revision_available:
                    monkeypatch.setattr(service, "get_durable_revision", lambda: None)
            return value

        monkeypatch.setattr(service, method, commit_after_read)
        with service.combat_detail_read(combat_campaign, pages) as prepared:
            read = getattr(prepared, read_kind)
            first = read()
            assert len(captures) == 1  # No automatic retry of the in-flight read.
            assert connection.total_changes == changes
            assert revision_reader() != before_revision
            if read_kind == "library":
                assert first.title == initial_title
            else:
                assert next(row for row in first if row.source.source_id == "PHB").is_enabled
                cache = getattr(g, "_systems_service_request_cache", {})
                assert not any(key[-1] == ("campaign-source-states", combat_campaign) for key in cache)
            assert prepared.prepared_library is None
            if revision_available:
                assert prepared.generation[-1] == revision_reader()
            else:
                assert prepared.generation is None
            monkeypatch.setattr(service, "get_durable_revision", revision_reader)
            second = read()
            assert len(captures) == 2
            if read_kind == "library":
                assert second.title == "Committed during capture"
                assert prepared.prepared_library is second
                assert read() is second
            else:
                assert not next(row for row in second if row.source.source_id == "PHB").is_enabled
                assert prepared.prepared_library.title == "Committed during capture"
                assert read() == second
            assert len(captures) == 2  # Only the fresh value is reusable.


def test_active_combat_preparation_discards_uncommitted_values_after_rollback(app):
    from tests.test_combat_catalog_preparation import _services, _item, CAMPAIGN as combat_campaign

    service, pages = _services(app)
    with app.test_request_context("/"):
        _item(service)
        with service.combat_detail_read(combat_campaign, pages) as prepared:
            initial = prepared.library().title
            assert next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
            connection = get_db()
            connection.execute("UPDATE systems_libraries SET title='Uncommitted' WHERE library_slug='DND-5E'")
            connection.execute("UPDATE campaign_enabled_sources SET is_enabled=0 WHERE campaign_slug=? AND source_id='PHB'", (combat_campaign,))
            assert prepared.library().title == "Uncommitted"
            assert not next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
            changes = connection.total_changes
            connection.rollback()
            assert connection.total_changes == changes
            assert prepared.library().title == initial
            assert next(row for row in prepared.sources() if row.source.source_id == "PHB").is_enabled
ROWS = {
    "systems_libraries": dict(library_slug="trigger-test", title="Before", system_code="DND-5E", status="active", created_at="fixed", updated_at="fixed"),
    "systems_sources": dict(library_slug="trigger-test", source_id="TEST", title="Before", license_class="srd_cc", status="active", created_at="fixed", updated_at="fixed"),
    "systems_entries": dict(library_slug="trigger-test", source_id="TEST", entry_key="item|trigger", entry_type="item", slug="trigger", title="Before", created_at="fixed", updated_at="fixed"),
    "systems_entry_links": dict(library_slug="trigger-test", from_entry_key="item|trigger", to_entry_key="item|other", relation_type="before"),
    "campaign_system_policies": dict(campaign_slug="trigger-test", library_slug="trigger-test", status="active", created_at="fixed", updated_at="fixed"),
    "campaign_enabled_sources": dict(campaign_slug="trigger-test", library_slug="trigger-test", source_id="TEST", is_enabled=1, default_visibility="players", updated_at="fixed"),
    "campaign_entry_overrides": dict(campaign_slug="trigger-test", library_slug="trigger-test", entry_key="item|trigger", updated_at="fixed"),
}


class _Repository:
    def get(self):
        return self

    def get_campaign(self, slug):
        return Campaign(title="Revision test", slug=slug, summary="", system="DND-5E",
            current_session=1, source_wiki_root="", player_content_dir="", assets_dir="",
            systems_library_slug=LIBRARY)


def _make_app(path):
    app = Flask(__name__)
    app.config.update(DB_PATH=Path(path), TESTING=True)
    app.teardown_appcontext(close_db)
    return app


@pytest.fixture
def revision_app(tmp_path):
    app = _make_app(tmp_path / "revision.sqlite3")
    with app.app_context():
        init_database()
        store = SystemsStore()
        store.upsert_library(LIBRARY, title="Revision test", system_code="DND-5E")
        store.upsert_source(LIBRARY, "TEST", title="Test", license_class="srd_cc")
        store.upsert_campaign_policy(CAMPAIGN, library_slug=LIBRARY)
        store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id="TEST", is_enabled=True, default_visibility="players")
        store.upsert_entry(LIBRARY, "TEST", entry_key=ENTRY, entry_type="item", slug="stone", title="Before", metadata={"revision_payload": "before"})
    _clear_builder_static_bundle_cache()
    yield app
    _clear_builder_static_bundle_cache()


def _service():
    return SystemsService(SystemsStore(), _Repository()).character_read_view()


def _title(service):
    bundle = _build_common_builder_static_bundle(service, CAMPAIGN, campaign_page_records=[])
    return bundle["item_catalog"]["by_entry_key"][ENTRY].title


@pytest.mark.parametrize("table", SYSTEMS_REVISION_TABLES)
def test_each_relevant_table_insert_update_delete_changes_token_with_fixed_rows(revision_app, table):
    with revision_app.app_context():
        connection = get_db()
        store = SystemsStore()
        before = store.get_durable_revision()
        row = ROWS[table]
        fields = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        connection.execute(f"INSERT INTO {table} ({fields}) VALUES ({marks})", tuple(row.values()))
        inserted = store.get_durable_revision()
        column = next(iter(row))
        connection.execute(f"UPDATE {table} SET {column} = {column} WHERE {column} = ?", (row[column],))
        updated = store.get_durable_revision()
        connection.execute(f"DELETE FROM {table} WHERE {column} = ?", (row[column],))
        deleted = store.get_durable_revision()
        connection.commit()
        assert len({before, inserted, updated, deleted}) == 4
        assert all(re.fullmatch(r"[0-9a-f]{64}", token) for token in [before, inserted, updated, deleted])
        assert connection.execute(f"SELECT count(*) FROM {table} WHERE {column} = ?", (row[column],)).fetchone()[0] == 0


def test_token_reads_do_not_write_or_scan_entry_bodies(revision_app):
    with revision_app.app_context():
        connection = get_db()
        statements = []
        connection.set_trace_callback(statements.append)
        store = SystemsStore()
        before = connection.total_changes
        tokens = [store.get_durable_revision() for _ in range(5)]
        assert len(set(tokens)) == 1
        assert connection.total_changes == before
        assert len(statements) == 5
        assert all("SELECT token FROM systems_revision" in sql for sql in statements)


def test_uncommitted_rollback_and_failed_commit_revision_remain_transaction_bound(revision_app):
    with revision_app.app_context():
        connection = get_db()
        observer = sqlite3.connect(revision_app.config["DB_PATH"])
        token = lambda: observer.execute("SELECT token FROM systems_revision").fetchone()[0]
        before = token()
        connection.execute("UPDATE systems_entries SET title='Pending' WHERE entry_key=?", (ENTRY,))
        pending = SystemsStore().get_durable_revision()
        assert pending != before
        assert token() == before
        connection.rollback()
        assert SystemsStore().get_durable_revision() == before
        connection.execute("CREATE TABLE revision_parent(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE revision_child(parent_id REFERENCES revision_parent(id) DEFERRABLE INITIALLY DEFERRED)")
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                connection.execute("UPDATE systems_entries SET title='Failed' WHERE entry_key=?", (ENTRY,))
                connection.execute("INSERT INTO revision_child VALUES(999)")
        assert token() == before == SystemsStore().get_durable_revision()
        connection.execute("UPDATE systems_entries SET title='Committed' WHERE entry_key=?", (ENTRY,))
        connection.commit()
        assert token() not in {before, pending}
        assert observer.execute("SELECT title FROM systems_entries WHERE entry_key=?", (ENTRY,)).fetchone()[0] == "Committed"
        observer.close()


def test_same_request_and_new_request_static_cache_observe_same_timestamp_edits(revision_app):
    service = _service()
    with revision_app.test_request_context("/"):
        before_row = SystemsStore().get_entry(LIBRARY, ENTRY)
        assert _title(service) == "Before"
        connection = get_db()
        connection.execute("UPDATE systems_entries SET title='After', metadata_json=? WHERE entry_key=?", (json.dumps({"revision_payload": "after"}), ENTRY))
        connection.commit()
        assert _title(service) == "After"
        after_row = SystemsStore().get_entry(LIBRARY, ENTRY)
        assert before_row.id == after_row.id and before_row.updated_at == after_row.updated_at
    with revision_app.test_request_context("/"):
        assert _title(service) == "After"
        get_db().execute("UPDATE systems_entries SET title='Later' WHERE entry_key=?", (ENTRY,))
        get_db().commit()
        assert _title(service) == "Later"


def test_aborted_warm_cache_never_reuses_token_on_divergent_commit(revision_app):
    service = _service()
    with revision_app.test_request_context("/"):
        assert _title(service) == "Before"
        connection = get_db()
        before = SystemsStore().get_durable_revision()
        connection.execute("UPDATE systems_entries SET title='Aborted' WHERE entry_key=?", (ENTRY,))
        aborted = SystemsStore().get_durable_revision()
        assert _title(service) == "Aborted"
        connection.rollback()
        assert SystemsStore().get_durable_revision() == before
        assert _title(service) == "Before"
        connection.execute("UPDATE systems_entries SET title='Divergent' WHERE entry_key=?", (ENTRY,))
        connection.commit()
        assert SystemsStore().get_durable_revision() not in {before, aborted}
        assert _title(service) == "Divergent"


def test_v13_migration_initializes_real_triggers_and_rolls_back_late_fault(tmp_path):
    path = tmp_path / "v13.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    run_migrations(connection, database_path=path, schema_sql=SCHEMA_V13_SQL, registry=MIGRATIONS[:13])
    connection.execute("INSERT INTO systems_libraries VALUES('old','Old','DND-5E','active','fixed','fixed')")
    connection.commit()
    historical = [tuple(row) for row in connection.execute("SELECT version,name,checksum FROM schema_migrations ORDER BY version")]
    def fail_after_ledger(version, _name):
        if version == 14:
            raise RuntimeError("late migration fault")
    with pytest.raises(RuntimeError, match="late migration fault"):
        run_migrations(connection, database_path=path, schema_sql=CURRENT_SCHEMA_SQL, hooks=MigrationHooks(after_ledger_insert=fail_after_ledger))
    assert connection.execute("SELECT name FROM sqlite_master WHERE name='systems_revision'").fetchone() is None
    result = run_migrations(connection, database_path=path, schema_sql=CURRENT_SCHEMA_SQL)
    assert result.applied_versions == (14,)
    assert [tuple(row) for row in connection.execute("SELECT version,name,checksum FROM schema_migrations WHERE version<=13 ORDER BY version")] == historical
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = connection.execute("SELECT token FROM systems_revision").fetchone()[0]
    assert run_migrations(connection, database_path=path, schema_sql=CURRENT_SCHEMA_SQL).no_op
    assert connection.execute("SELECT token FROM systems_revision").fetchone()[0] == before
    connection.execute("UPDATE systems_libraries SET title='New' WHERE library_slug='old'")
    assert connection.execute("SELECT token FROM systems_revision").fetchone()[0] != before
    assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE '%_revision_%'").fetchone()[0] == 21
    connection.close()


def test_v13_payload_checksum_remains_frozen():
    assert MIGRATIONS[12].checksum == "5b22a2400de5360db911e6de51e5bbb7ceed70db7e27b6f035b5b7b2a774bfc1"
    assert calculate_migration_checksum(MIGRATIONS[12].payload) == MIGRATIONS[12].checksum
    assert MIGRATIONS[12].payload.schema_sql == SCHEMA_V13_SQL
    assert MIGRATIONS[13].version == 14


def _ability_minimum_metadata(minimum):
    from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
    return build_campaign_item_mechanics_metadata(title="Before", body_markdown="Wondrous item",
        review_status="approved", explicit_mechanics={"ability_score_minimums":{"str":minimum}})


def _known_ability_stats():
    keys = ("str", "dex", "con", "int", "wis", "cha")
    return {
        "ability_scores": {key:{"score":10} for key in keys},
        "ability_inputs": {"version":1, "scores":{
            key:{"stage":"base", "score":10, "fixed_bonus":0, "provenance":"synthetic-known-input"}
            for key in keys
        }},
    }


def _worker_mechanics_score(service):
    from player_wiki.character_models import CharacterDefinition
    from player_wiki.character_mechanics_projection import build_character_mechanics_projection
    definition = CharacterDefinition.from_dict({
        "campaign_slug":CAMPAIGN, "character_slug":"worker", "name":"Worker", "status":"active",
        "stats":_known_ability_stats(),
        "equipment_catalog":[{"id":"stone", "name":"Before", "is_equipped":True, "is_attuned":True,
            "systems_ref":{"entry_key":ENTRY,"entry_type":"item","source_id":"TEST"}}],
    })
    result = build_character_mechanics_projection(campaign=_Repository().get_campaign(CAMPAIGN),
        definition=definition, state={}, systems_service=service, campaign_page_records=[])
    return result["definition"].stats["ability_scores"]["str"]["score"]


def _revision_worker(database_path, channel, writer):
    app = _make_app(database_path)
    service = _service()
    try:
        with app.app_context():
            while True:
                command = channel.recv()
                if command == "stop":
                    break
                if writer:
                    if command == "pending":
                        get_db().execute("UPDATE systems_entries SET title='Pending',metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(20)), ENTRY))
                    elif command == "rollback":
                        get_db().rollback()
                    elif command == "commit":
                        get_db().execute("UPDATE systems_entries SET title='Committed',metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(18)), ENTRY))
                        get_db().commit()
                    elif command == "failed-commit":
                        connection = get_db()
                        connection.execute("CREATE TABLE revision_parent(id INTEGER PRIMARY KEY)")
                        connection.execute("CREATE TABLE revision_child(parent_id REFERENCES revision_parent(id) DEFERRABLE INITIALLY DEFERRED)")
                        connection.commit()
                        try:
                            with connection:
                                connection.execute("UPDATE systems_entries SET title='Failed commit' WHERE entry_key=?", (ENTRY,))
                                connection.execute("INSERT INTO revision_child VALUES(999)")
                        except sqlite3.IntegrityError:
                            channel.send((SystemsStore().get_durable_revision(), "failed-commit-rolled-back"))
                            continue
                        raise AssertionError("deferred foreign-key commit must fail")
                    channel.send((SystemsStore().get_durable_revision(), None))
                else:
                    with app.test_request_context("/"):
                        channel.send((SystemsStore().get_durable_revision(), (_title(service), _worker_mechanics_score(service))))
    except BaseException as error:
        channel.send(("worker-error", repr(error)))
        raise
    finally:
        channel.close()


def test_two_long_lived_processes_observe_commits_without_restart_or_cache_clear(revision_app):
    with revision_app.app_context():
        get_db().execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(14)), ENTRY))
        get_db().commit()
    context = multiprocessing.get_context("spawn")
    reader, reader_child = context.Pipe()
    writer, writer_child = context.Pipe()
    processes = [
        context.Process(target=_revision_worker, args=(str(revision_app.config["DB_PATH"]), reader_child, False)),
        context.Process(target=_revision_worker, args=(str(revision_app.config["DB_PATH"]), writer_child, True)),
    ]
    for process in processes:
        process.start()
    def exchange(channel, command):
        channel.send(command)
        assert channel.poll(15), "worker did not respond"
        result = channel.recv()
        assert result[0] != "worker-error", result
        return result
    try:
        original, title = exchange(reader, "read")
        assert title == ("Before", 14)
        pending, _ = exchange(writer, "pending")
        assert pending != original
        assert exchange(reader, "read") == (original, ("Before", 14))
        assert exchange(writer, "rollback")[0] == original
        assert exchange(reader, "read") == (original, ("Before", 14))
        assert exchange(writer, "failed-commit") == (original, "failed-commit-rolled-back")
        assert exchange(reader, "read") == (original, ("Before", 14))
        committed, _ = exchange(writer, "commit")
        assert committed not in {original, pending}
        assert exchange(reader, "read") == (committed, ("Committed", 18))
    finally:
        reader.send("stop")
        writer.send("stop")
        for process in processes:
            process.join(15)
            assert not process.is_alive()
            assert process.exitcode == 0
        reader.close()
        writer.close()


def test_restored_snapshot_and_divergent_edit_keep_cached_database_states_distinct(revision_app, tmp_path):
    service = _service()
    database = revision_app.config["DB_PATH"]
    snapshot = tmp_path / "snapshot.sqlite3"
    with revision_app.test_request_context("/"):
        original = SystemsStore().get_durable_revision()
        assert _title(service) == "Before"
    with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as target:
        source.backup(target)
    with revision_app.test_request_context("/"):
        get_db().execute("UPDATE systems_entries SET title='Abandoned history' WHERE entry_key=?", (ENTRY,))
        get_db().commit()
        abandoned = SystemsStore().get_durable_revision()
        assert _title(service) == "Abandoned history"
    # Every application connection is closed before restoring synthetic data.
    with sqlite3.connect(snapshot) as source, sqlite3.connect(database) as target:
        source.backup(target)
    with revision_app.test_request_context("/"):
        assert SystemsStore().get_durable_revision() == original
        assert _title(service) == "Before"
        get_db().execute("UPDATE systems_entries SET title='Divergent history' WHERE entry_key=?", (ENTRY,))
        get_db().commit()
        assert SystemsStore().get_durable_revision() not in {original, abandoned}
        assert _title(service) == "Divergent history"
    other = _make_app(tmp_path / "other.sqlite3")
    with other.app_context():
        init_database()
        assert SystemsStore().get_durable_revision() != original
        store = SystemsStore()
        store.upsert_library(LIBRARY, title="Other database", system_code="DND-5E")
        store.upsert_source(LIBRARY, "TEST", title="Test", license_class="srd_cc")
        store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id="TEST", is_enabled=True, default_visibility="players")
        store.upsert_entry(LIBRARY, "TEST", entry_key=ENTRY, entry_type="item", slug="stone", title="Other database")
    with other.test_request_context("/"):
        assert _title(service) == "Other database"
    with revision_app.test_request_context("/"):
        assert _title(service) == "Divergent history"


@pytest.mark.parametrize("consumer", ["builder", "normalized", "prepared"])
def test_post_build_revision_read_failure_releases_single_flight_waiter(monkeypatch, consumer):
    import player_wiki.character_builder_catalogs as catalogs
    import player_wiki.character_mechanics_projection as mechanics
    import player_wiki.character_read_projection as read
    from player_wiki.character_models import CharacterDefinition
    entered, waiting, release = Event(), Event(), Event()
    class ObservedEvent:
        def __init__(self):
            self.event = Event()
        def wait(self):
            waiting.set()
            return self.event.wait(5)
        def set(self):
            self.event.set()
    module = {"builder": catalogs, "normalized": mechanics, "prepared": read}[consumer]
    monkeypatch.setattr(module, "Event", ObservedEvent)
    fail = False
    def check():
        if fail:
            raise sqlite3.OperationalError("revision read failed after build")
        return True
    key = _RevisionBoundCacheKey(("revision-read-failure", consumer), check)
    def build():
        nonlocal fail
        entered.set()
        assert release.wait(5)
        fail = True
        if consumer == "normalized":
            return CharacterDefinition.from_dict({"campaign_slug":CAMPAIGN,"character_slug":"test","name":"Test","status":"active"})
        return {"value":"built"}
    if consumer == "builder":
        load = lambda: _builder_static_cache_get(key, build)
    elif consumer == "normalized":
        load = lambda: mechanics._normalized_definition_from_cache(cache_key=key, build_definition=build, full_normalization_recipe=True)
    else:
        load = lambda: read.load_cached_character_read_projection(key, build)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(load)
        assert entered.wait(5)
        second = executor.submit(load)
        assert waiting.wait(5)
        release.set()
        for future in (first, second):
            with pytest.raises(sqlite3.OperationalError, match="revision read failed after build"):
                future.result(timeout=5)


@pytest.mark.parametrize("recipe", ["full", "scoped", "prepared"])
def test_real_normalized_and_prepared_mechanics_follow_same_timestamp_metadata(revision_app, recipe):
    from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
    from player_wiki.character_mechanics_projection import build_character_mechanics_projection
    from player_wiki.character_models import CharacterDefinition
    from player_wiki.character_read_projection import build_character_read_projection_cache_key, load_cached_character_read_projection
    definition = CharacterDefinition.from_dict({
        "campaign_slug":CAMPAIGN, "character_slug":"mechanics", "name":"Mechanics", "status":"active",
        "stats":{"max_hp":20, **_known_ability_stats()},
        "equipment_catalog":[{"id":"stone", "name":"Before", "default_quantity":1, "is_equipped":True,"is_attuned":True,
            "systems_ref":{"entry_key":ENTRY,"entry_type":"item","slug":"stone","title":"Before","source_id":"TEST"}}],
    })
    service = _service()
    campaign = _Repository().get_campaign(CAMPAIGN)
    record = SimpleNamespace(definition=definition, state_record=SimpleNamespace(revision=1,state={"vitals":{"current_hp":7}}))
    def metadata(minimum):
        return build_campaign_item_mechanics_metadata(title="Before", body_markdown="Wondrous item", review_status="approved", explicit_mechanics={"ability_score_minimums":{"str":minimum}})
    def derive():
        kwargs = {} if recipe == "full" else dict(components=frozenset(),catalog_components=frozenset(),derivation_components=frozenset({"item_ability_minimums"}))
        result = build_character_mechanics_projection(campaign=campaign, definition=definition, state=record.state_record.state,
            systems_service=service,campaign_page_records=[], **kwargs)
        return {"score":result["definition"].stats["ability_scores"]["str"]["score"], "current_hp":result["state"]["vitals"]["current_hp"]}
    def read():
        if recipe != "prepared":
            return derive()
        key = build_character_read_projection_cache_key("revision-test",campaign_slug=CAMPAIGN,record=record,systems_service=service,
            campaign_page_records=[],campaign_current_session=1,effective_visibility="players")
        return load_cached_character_read_projection(key, derive)
    with revision_app.test_request_context("/"):
        connection = get_db()
        connection.execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?",(json.dumps(metadata(14)),ENTRY))
        connection.commit()
        before = SystemsStore().get_entry(LIBRARY,ENTRY)
        assert read() == {"score":14,"current_hp":7}
        assert read() == {"score":14,"current_hp":7}
        connection.execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?",(json.dumps(metadata(18)),ENTRY))
        connection.commit()
        after = SystemsStore().get_entry(LIBRARY,ENTRY)
        assert (before.id,before.updated_at)==(after.id,after.updated_at)
        assert read() == {"score":18,"current_hp":7}
    with revision_app.test_request_context("/"):
        assert read() == {"score":18,"current_hp":7}


def test_static_build_token_drift_is_uncached_and_next_read_builds_current_content(revision_app, monkeypatch):
    service = _service()
    original = service.list_enabled_entries_for_campaign
    item_reads = 0
    def drifting(*args, **kwargs):
        nonlocal item_reads
        entries = original(*args, **kwargs)
        if kwargs.get("entry_type") == "item":
            item_reads += 1
            if item_reads == 1:
                with sqlite3.connect(revision_app.config["DB_PATH"]) as writer:
                    writer.execute("UPDATE systems_entries SET title='After drift' WHERE entry_key=?",(ENTRY,))
        return entries
    monkeypatch.setattr(service,"list_enabled_entries_for_campaign",drifting)
    with revision_app.test_request_context("/"):
        assert _title(service) == "Before"
        assert _title(service) == "After drift"
        assert _title(service) == "After drift"
        assert item_reads == 2


def test_progression_cache_observes_same_timestamp_feature_content(revision_app):
    service = _service()
    with revision_app.test_request_context("/"):
        store = SystemsStore()
        selected = store.upsert_entry(LIBRARY,"TEST",entry_key="class|test",entry_type="class",slug="test-class",title="Test Class",
            body={"feature_progression":[{"name":"Level 1","entries":["Original feature"]}]})
        store.upsert_entry(LIBRARY,"TEST",entry_key="classfeature|test",entry_type="classfeature",slug="test-feature",title="Original feature",
            metadata={"class_name":"Test Class","class_source":"TEST","level":1},body={"entries":["Original feature content"]})
        first = _class_progression_for_builder(service,CAMPAIGN,selected,campaign_page_records=[])
        assert "Original feature" in repr(first)
        get_db().execute("UPDATE systems_entries SET title='Changed feature', body_json=? WHERE entry_key='classfeature|test'",(json.dumps({"entries":["Changed feature content"]}),))
        get_db().commit()
        second = _class_progression_for_builder(service,CAMPAIGN,selected,campaign_page_records=[])
        assert "Changed feature" in repr(second)
        assert first != second
        get_db().execute("UPDATE systems_entries SET body_json=? WHERE entry_key='class|test'",
            (json.dumps({"feature_progression":[{"name":"Level 1","entries":["Changed parent label"]}]}),))
        get_db().commit()
        third = _class_progression_for_builder(service,CAMPAIGN,selected,campaign_page_records=[])
        assert "Changed parent label" in repr(third)
        assert "Changed parent label" not in repr(selected.body)


def test_same_timestamp_mechanics_impact_cursor_and_selection_are_stale(revision_app):
    from player_wiki.mechanics_impact import (MechanicsImpactAccessContext, MechanicsImpactCursorCodec,
        MechanicsImpactIdentity, MechanicsImpactKernel, MechanicsImpactStale)
    service = _service()
    context = MechanicsImpactAccessContext(campaign_slug=CAMPAIGN,system_code="DND-5E",library_slug=LIBRARY,can_manage_systems=True)
    store = SystemsStore()
    kernel = MechanicsImpactKernel(store=store,systems_service=service,authorize=lambda _:context,
        inventory_adapters={},cursor_codec=MechanicsImpactCursorCodec(b"revision-test-signing-key-is-long"))
    metadata = {"campaign_item_mechanics_review_status":"draft","campaign_item_mechanics_support_state":"needs_implementation"}
    with revision_app.test_request_context("/"):
        for index in range(51):
            store.upsert_entry(LIBRARY,"TEST",entry_key=f"item|impact|{index:02}",entry_type="item",slug=f"impact-{index}",title=f"Impact {index}",metadata=metadata)
        page = kernel.list_queue_for_context(context)
        assert page.continuation and len(page.rows) == 50
        selected = store.get_entry(LIBRARY,"item|impact|00")
        get_db().execute("UPDATE systems_entries SET body_json=? WHERE entry_key=?",(json.dumps({"changed":"same timestamp"}),selected.entry_key))
        get_db().commit()
        assert store.get_entry(LIBRARY,selected.entry_key).updated_at == selected.updated_at
        with pytest.raises(MechanicsImpactStale,match="cursor"):
            kernel.list_queue_for_context(context,continuation=page.continuation)
        with pytest.raises(MechanicsImpactStale,match="selection snapshot"):
            kernel.review(context,MechanicsImpactIdentity(LIBRARY,"TEST",selected.entry_key),
                expected_updated_at=selected.updated_at.isoformat(),expected_input_digest="",expected_snapshot=page.snapshot)


def test_source_service_failure_rolls_back_batch_and_preserves_warm_cache(revision_app, monkeypatch):
    store = SystemsStore()
    service = SystemsService(store, _Repository())
    read_service = service.character_read_view()
    with revision_app.test_request_context("/"):
        store.upsert_source(LIBRARY, "SECOND", title="Second", license_class="srd_cc")
        store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id="SECOND", is_enabled=True, default_visibility="players")
        assert _title(read_service) == "Before"
        before = store.get_durable_revision()
        write = store.upsert_campaign_enabled_source
        def fail_second(campaign_slug, **kwargs):
            if kwargs["source_id"] == "SECOND":
                raise RuntimeError("second source unavailable")
            return write(campaign_slug, **kwargs)
        monkeypatch.setattr(store, "upsert_campaign_enabled_source", fail_second)
        with pytest.raises(RuntimeError, match="second source unavailable"):
            service.update_campaign_sources(CAMPAIGN, updates=[
                {"source_id":"TEST", "is_enabled":False, "default_visibility":"players"},
                {"source_id":"SECOND", "is_enabled":False, "default_visibility":"players"},
            ], actor_user_id=None, acknowledge_proprietary=False, can_set_private=False)
        after = store.get_durable_revision()
        assert after == before
        with sqlite3.connect(revision_app.config["DB_PATH"]) as observer:
            assert observer.execute("SELECT token FROM systems_revision").fetchone()[0] == after
            assert dict(observer.execute("SELECT source_id,is_enabled FROM campaign_enabled_sources")) == {"TEST":1, "SECOND":1}
        bundle = _build_common_builder_static_bundle(read_service, CAMPAIGN, campaign_page_records=[])
        assert ENTRY in bundle["item_catalog"]["by_entry_key"]
        assert service.get_campaign_source_state(CAMPAIGN, "TEST").is_enabled is True
        assert service.get_campaign_source_state(CAMPAIGN, "SECOND").is_enabled is True


def test_services_without_durable_identity_do_not_reuse_request_values(revision_app):
    from player_wiki.character_builder_catalogs import _builder_cache_get
    from player_wiki.systems_service import _systems_service_cache_get
    service = SystemsService(object(), object())
    calls = []
    def build():
        calls.append(len(calls))
        return len(calls)
    with revision_app.test_request_context("/"):
        assert _builder_cache_get(("fake",), build, systems_service=service) == 1
        assert _builder_cache_get(("fake",), build, systems_service=service) == 2
        assert _systems_service_cache_get(("fake",), build, systems_service=service) == 3
        assert _systems_service_cache_get(("fake",), build, systems_service=service) == 4


def test_empty_impact_queue_has_snapshot_and_mid_read_drift_fails_closed(revision_app, monkeypatch):
    from player_wiki.mechanics_impact import (MechanicsImpactAccessContext, MechanicsImpactCursorCodec,
        MechanicsImpactKernel, MechanicsImpactStale)
    service = _service()
    context = MechanicsImpactAccessContext(campaign_slug=CAMPAIGN, system_code="DND-5E", library_slug=LIBRARY, can_manage_systems=True)
    store = SystemsStore()
    kernel = MechanicsImpactKernel(store=store, systems_service=service, authorize=lambda _:context,
        inventory_adapters={}, cursor_codec=MechanicsImpactCursorCodec(b"revision-test-signing-key-is-long"))
    with revision_app.test_request_context("/"):
        empty = kernel.list_queue_for_context(context)
        assert empty.rows == () and empty.snapshot == store.mechanics_impact_metadata_snapshot(LIBRARY)
        store.upsert_entry(LIBRARY, "TEST", entry_key=ENTRY, entry_type="item", slug="stone", title="Draft",
            metadata={"review_status":"draft"})
        authorize = service.filter_mechanics_impact_authorized_identities
        def mutate_after_scan(*args):
            result = authorize(*args)
            get_db().execute("UPDATE systems_entries SET title='New draft' WHERE entry_key=?", (ENTRY,))
            get_db().commit()
            return result
        monkeypatch.setattr(service, "filter_mechanics_impact_authorized_identities", mutate_after_scan)
        with pytest.raises(MechanicsImpactStale, match="while reading"):
            kernel.list_queue_for_context(context)


@pytest.mark.parametrize("lookup", ["enabled", "targeted"])
def test_process_entry_lookups_are_detached_and_follow_content_source_and_override_changes(revision_app, lookup, monkeypatch):
    from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries, _build_targeted_item_support_catalog
    service = _service()
    source_records = []
    loader_name = ("list_enabled_entries_for_campaign" if lookup == "enabled"
        else "list_enabled_entries_by_identity_for_campaign")
    original_loader = getattr(service, loader_name)
    def retain_source_records(*args, **kwargs):
        rows = original_loader(*args, **kwargs)
        source_records.extend(rows)
        return rows
    monkeypatch.setattr(service, loader_name, retain_source_records)
    def entries():
        if lookup == "enabled":
            return _list_campaign_enabled_entries(service, CAMPAIGN, "item")
        catalog = _build_targeted_item_support_catalog([
            {"id":"stone", "name":"Before", "is_equipped":True, "systems_ref":{"entry_key":ENTRY}},
        ], campaign_slug=CAMPAIGN, systems_service=service, campaign_page_records=[])
        return catalog["entries"]
    with revision_app.test_request_context("/"):
        connection = get_db()
        connection.execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps({"nested":{"values":[1]}}), ENTRY))
        connection.commit()
        original = SystemsStore().get_entry(LIBRARY, ENTRY)
        cold = entries()
        cold[0].title = "Detached caller"
        cold[0].metadata["nested"]["values"].append(99)
        # A loader/request-cache owner may retain its own record references.
        source_records[0].metadata["nested"]["values"].append(77)
        warm = entries()
        assert warm[0].title == "Before" and warm[0].metadata["nested"]["values"] == [1]
        warm[0].metadata["nested"]["values"].append(88)
        assert entries()[0].metadata["nested"]["values"] == [1]
        connection.execute("UPDATE systems_entries SET title='After',metadata_json=? WHERE entry_key=?", (json.dumps({"nested":{"values":[2]}}), ENTRY))
        connection.commit()
        changed = entries()[0]
        assert changed.title == "After" and changed.metadata["nested"]["values"] == [2]
        assert (changed.id, changed.updated_at) == (original.id, original.updated_at)
        connection.execute("UPDATE campaign_enabled_sources SET is_enabled=0 WHERE source_id='TEST'")
        connection.commit()
        assert entries() == []
        SystemsStore().upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id="TEST", is_enabled=True, default_visibility="players")
        assert entries()[0].title == "After"
        SystemsStore().upsert_campaign_entry_override(CAMPAIGN, library_slug=LIBRARY, entry_key=ENTRY, is_enabled_override=False, visibility_override=None)
        assert entries() == []
    with revision_app.test_request_context("/"):
        assert entries() == []


def test_library_revision_read_is_one_coherent_read_and_missing_library_stays_absent(revision_app):
    with revision_app.test_request_context("/"):
        store = SystemsStore()
        statements = []
        connection = get_db()
        before = connection.total_changes
        connection.set_trace_callback(statements.append)
        library, token = store.get_library_with_revision(LIBRARY)
        connection.set_trace_callback(None)
        assert library.library_slug == LIBRARY and re.fullmatch(r"[0-9a-f]{64}", token)
        assert len(statements) == 1 and "systems_entries" not in statements[0]
        missing, missing_token = store.get_library_with_revision("missing")
        assert missing is None and missing_token == token
        assert connection.total_changes == before


def _context_mechanics_read(service, recipe):
    from player_wiki.character_mechanics_projection import build_character_mechanics_projection
    from player_wiki.character_models import CharacterDefinition
    from player_wiki.character_read_projection import build_character_read_projection_cache_key, load_cached_character_read_projection
    definition = CharacterDefinition.from_dict({
        "campaign_slug": CAMPAIGN, "character_slug": "context", "name": "Context", "status": "active",
        "stats": _known_ability_stats(),
        "equipment_catalog": [{"id": "stone", "name": "Before", "is_equipped": True, "is_attuned": True,
            "systems_ref": {"entry_key": ENTRY, "entry_type": "item", "source_id": "TEST"}}],
    })
    def derive():
        kwargs = {} if recipe == "full" else dict(components=frozenset(), catalog_components=frozenset() if recipe == "targeted" else frozenset({"items"}),
            derivation_components=frozenset({"item_ability_minimums"}))
        result = build_character_mechanics_projection(campaign=service._get_campaign(CAMPAIGN),
            definition=definition, state={}, systems_service=service, campaign_page_records=[], **kwargs)
        return result["definition"].stats["ability_scores"]["str"]["score"]
    if recipe != "prepared":
        return derive()
    record = SimpleNamespace(definition=definition, state_record=SimpleNamespace(revision=1, state={}))
    key = build_character_read_projection_cache_key("context", campaign_slug=CAMPAIGN, record=record,
        systems_service=service, campaign_page_records=[], campaign_current_session=1, effective_visibility="players")
    return load_cached_character_read_projection(key, lambda: {"score": derive()})["score"]


@pytest.mark.parametrize("recipe", ["full", "scoped", "prepared"])
@pytest.mark.parametrize("order", [("other", "stone", "full", "empty"), ("full", "other", "stone", "empty")])
def test_request_subsets_isolate_entries_and_enclosing_mechanics_with_same_token(revision_app, recipe, order):
    from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries
    service = _service()
    with revision_app.app_context():
        store = SystemsStore()
        store.upsert_entry(LIBRARY, "TEST", entry_key=ENTRY, entry_type="item", slug="stone", title="Before",
            metadata=_ability_minimum_metadata(18))
        other = store.upsert_entry(LIBRARY, "TEST", entry_key="item|revision-test|other", entry_type="item",
            slug="other", title="Other", metadata=_ability_minimum_metadata(14))
        stone = store.get_entry(LIBRARY, ENTRY)
        token = store.get_durable_revision()
    selections = {"other": [other], "stone": [stone], "empty": []}
    expected = {"other": [other.entry_key], "stone": [ENTRY], "full": [other.entry_key, ENTRY], "empty": []}
    for selection in order:
        with revision_app.test_request_context("/"):
            if selection != "full":
                _install_current_subset(service, CAMPAIGN, entry_type="item", entries=selections[selection])
            # Exercise the enclosing value before its lower-level entry lookup.
            score = 18 if selection in {"stone", "full"} else 10
            assert _context_mechanics_read(service, recipe) == score
            assert sorted(row.entry_key for row in _list_campaign_enabled_entries(service, CAMPAIGN, "item")) == expected[selection]
            assert _context_mechanics_read(service, recipe) == score
            assert SystemsStore().get_durable_revision() == token


def _yaml_repository(tmp_path, *, enabled=True, visibility="players"):
    from player_wiki.repository_store import RepositoryStore
    config = tmp_path / "campaigns" / CAMPAIGN / "campaign.yaml"
    config.parent.mkdir(parents=True)
    # Empty synthetic content; refresh_from_database never seeds any page rows.
    pages = SimpleNamespace(ensure_campaign_seeded=lambda *args: None, list_pages=lambda *args: [])
    repository = RepositoryStore(config.parent.parent, page_store=pages, reload_enabled=False, scan_interval_seconds=0)
    def refresh(enabled, visibility):
        config.write_text(json.dumps({"title": "Revision test", "slug": CAMPAIGN, "system": "DND-5E",
            "systems_library": LIBRARY, "systems_sources": [{"source_id": "TEST", "enabled": enabled,
                "default_visibility": visibility}]}), encoding="utf-8")
        return repository.refresh_from_database().get_campaign(CAMPAIGN)
    refresh(enabled, visibility)
    return repository, refresh


@pytest.mark.parametrize("recipe", ["full", "scoped", "targeted", "prepared"])
def test_yaml_source_defaults_refresh_warmed_entries_mechanics_and_visibility_without_db_writes(revision_app, tmp_path, recipe):
    from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries
    repository, refresh = _yaml_repository(tmp_path)
    service = SystemsService(SystemsStore(), repository).character_read_view()
    with revision_app.app_context():
        get_db().execute("DELETE FROM campaign_enabled_sources WHERE campaign_slug=?", (CAMPAIGN,))
        get_db().execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(18)), ENTRY))
        get_db().commit()
        token = SystemsStore().get_durable_revision()
    for enabled, visibility in [(True, "players"), (False, "players"), (True, "dm"), (True, "players")]:
        refresh(enabled, visibility)
        with revision_app.test_request_context("/"):
            before = get_db().total_changes
            assert _context_mechanics_read(service, recipe) == (18 if enabled else 10)
            entries = _list_campaign_enabled_entries(service, CAMPAIGN, "item")
            assert [row.entry_key for row in entries] == ([ENTRY] if enabled else [])
            state = service.get_campaign_source_state(CAMPAIGN, "TEST")
            assert (state.is_enabled, state.default_visibility, state.is_configured) == (enabled, visibility, False)
            assert SystemsStore().get_durable_revision() == token
            assert get_db().total_changes == before


def test_subset_replacement_in_same_request_invalidates_retained_keys_and_detaches_records(revision_app):
    from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries, _build_scoped_spell_catalog
    service = _service()
    with revision_app.test_request_context("/"):
        stone = SystemsStore().get_entry(LIBRARY, ENTRY)
        stone.metadata.update(_ability_minimum_metadata(18))
        token = SystemsStore().get_durable_revision()
        _install_current_subset(service, CAMPAIGN, entry_type="item", entries=[stone])
        key = _builder_static_revision_key(service, CAMPAIGN)
        assert _builder_static_cache_get(key, lambda: {"score": _context_mechanics_read(service, "full")}) == {"score": 18}
        stone.metadata.clear()
        returned = service.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
        returned[0].metadata.clear()
        assert _context_mechanics_read(service, "full") == 18
        _install_current_subset(service, CAMPAIGN, entry_type="item", entries=[])
        # A retained old key must rebuild, never serve its earlier item mechanics.
        assert _builder_static_cache_get(key, lambda: {"score": _context_mechanics_read(service, "full")}) == {"score": 10}
        assert _list_campaign_enabled_entries(service, CAMPAIGN, "item") == []
        _install_current_subset(service, CAMPAIGN, entry_type="item", entries=[stone])
        assert _context_mechanics_read(service, "full") == 10
        # Another entry type also changes the enclosing request-cached catalog.
        spell = SystemsStore().upsert_entry(LIBRARY, "TEST", entry_key="spell|revision-test|spark", entry_type="spell", slug="spark", title="Spark")
        spell_token = SystemsStore().get_durable_revision()
        assert "spell|revision-test|spark" in _build_scoped_spell_catalog(service, CAMPAIGN)["by_entry_key"]
        _install_current_subset(service, CAMPAIGN, entry_type="spell", entries=[])
        assert _build_scoped_spell_catalog(service, CAMPAIGN)["by_entry_key"] == {}
        assert token != spell_token == SystemsStore().get_durable_revision()


@pytest.mark.parametrize("pinned", [False, True])
def test_yaml_refresh_respects_pinned_campaign_and_revalidates_retained_keys(revision_app, tmp_path, pinned):
    repository, refresh = _yaml_repository(tmp_path)
    service = SystemsService(SystemsStore(), repository).character_read_view()
    with revision_app.test_request_context("/"):
        get_db().execute("DELETE FROM campaign_enabled_sources WHERE campaign_slug=?", (CAMPAIGN,))
        get_db().commit()
        token = SystemsStore().get_durable_revision()
        campaign = repository.get().get_campaign(CAMPAIGN)
        if pinned:
            service.bind_campaign_for_request(CAMPAIGN, campaign)
        def visible():
            state = service.get_campaign_source_state(CAMPAIGN, "TEST")
            return {"enabled": state.is_enabled, "visibility": state.default_visibility}
        key = _builder_static_revision_key(service, CAMPAIGN)
        assert _builder_static_cache_get(key, visible) == {"enabled": True, "visibility": "players"}
        refresh(False, "dm")
        expected = {"enabled": True, "visibility": "players"} if pinned else {"enabled": False, "visibility": "dm"}
        assert visible() == expected
        assert _builder_static_cache_get(key, visible) == expected
        assert SystemsStore().get_durable_revision() == token
    with revision_app.test_request_context("/"):
        assert _builder_static_cache_get(key, visible) == {"enabled": False, "visibility": "dm"}
        assert SystemsStore().get_durable_revision() == token


@pytest.mark.parametrize("recipe", ["full", "scoped", "prepared"])
def test_yaml_drift_during_build_does_not_publish_under_previous_context(revision_app, tmp_path, monkeypatch, recipe):
    repository, refresh = _yaml_repository(tmp_path)
    service = SystemsService(SystemsStore(), repository).character_read_view()
    with revision_app.test_request_context("/"):
        get_db().execute("DELETE FROM campaign_enabled_sources WHERE campaign_slug=?", (CAMPAIGN,))
        get_db().execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(18)), ENTRY))
        get_db().commit()
        token = SystemsStore().get_durable_revision()
        original = service.list_enabled_entries_for_campaign
        changed = False
        def drift(*args, **kwargs):
            nonlocal changed
            entries = original(*args, **kwargs)
            if kwargs.get("entry_type") == "item" and not changed:
                changed = True
                refresh(False, "players")
            return entries
        monkeypatch.setattr(service, "list_enabled_entries_for_campaign", drift)
        _context_mechanics_read(service, recipe)
        assert changed
        assert _context_mechanics_read(service, recipe) == 10
        assert _context_mechanics_read(service, recipe) == 10
        assert SystemsStore().get_durable_revision() == token


def _install_current_subset(service, *args, **kwargs):
    revision = service.get_durable_revision()
    generation = (revision, service.get_cache_context(CAMPAIGN, entry_types=()))
    service.set_enabled_entry_subset_for_request(*args, source_generation=generation, **kwargs)


_SERVICE_SUBSET_CONSUMERS = ("class", "subclass", "vgm_monster", "race", "mtf_monster", "feat", "item")


def _service_subset_reader(service, consumer):
    """Seed actual entry relationships consumed by the seven public branches."""
    store = service.store
    if consumer in {"class", "subclass"}:
        entry_type = consumer + "feature"
        parent = store.upsert_entry(LIBRARY, "TEST", entry_key=f"{consumer}|subset-parent", entry_type=consumer,
            slug="subset-parent", title="Subset Adept" if consumer == "class" else "Subset School",
            metadata={"class_name": "Subset Adept", "class_source": "TEST"},
            body={"feature_progression": []}, rendered_html="<p>Parent fallback</p>")
        entries = [store.upsert_entry(LIBRARY, "TEST", entry_key=f"{entry_type}|subset-{letter}", entry_type=entry_type,
            slug=f"subset-{letter}", title=f"Subset Feature {letter}",
            metadata={"class_name": "Subset Adept", "class_source": "TEST", "subclass_name": "Subset School",
                "subclass_source": "TEST", "level": 1}, body={"entries": [f"Synthetic feature {letter}"]})
            for letter in ("A", "B")]
        progression = (service.build_class_feature_progression_for_class_entry if consumer == "class"
            else service.build_subclass_feature_progression_for_subclass_entry)
        def read():
            # The outer HTML cache is reached before the inner progression cache.
            html = service.build_character_sheet_entry_body_html(CAMPAIGN, parent)
            groups = progression(CAMPAIGN, parent)
            keys = sorted(row["entry"].entry_key for group in groups for row in group["feature_rows"] if row["entry"] is not None)
            return keys, html
    else:
        source, entry_type, wrapper, titles, metadata = {
            "vgm_monster": ("VGM", "monster", "Beholders: Bad Dreams Come True", ("Gauth", "Gazer"), {}),
            "race": ("VGM", "race", "Aasimar", ("Synthetic Aasimar A", "Synthetic Aasimar B"), {"base_race_name": "Aasimar"}),
            "mtf_monster": ("MTF", "monster", "Diabolical Cults", ("Geryon", "Zariel"), {}),
            "feat": ("MTF", "feat", "Deep Gnome Characters", ("Svirfneblin Magic", "Svirfneblin Magic"), {}),
            "item": ("MTF", "item", "Gith Characters", ("Greater Silver Sword", "Silver Sword"), {}),
        }[consumer]
        store.upsert_source(LIBRARY, source, title="Synthetic relationship source", license_class="srd_cc")
        store.upsert_campaign_enabled_source(CAMPAIGN, library_slug=LIBRARY, source_id=source, is_enabled=True, default_visibility="players")
        parent = store.upsert_entry(LIBRARY, source, entry_key=f"book|{consumer}", entry_type="book", slug=consumer, title=wrapper)
        entries = [store.upsert_entry(LIBRARY, source, entry_key=f"{entry_type}|{consumer}-{letter}", entry_type=entry_type,
            slug=f"{consumer}-{letter}", title=title, metadata=metadata)
            for letter, title in zip(("A", "B"), titles)]
        method = getattr(service, "build_related_" + {"monster": "monsters", "race": "races", "feat": "feats", "item": "items"}[entry_type] + "_for_entry")
        def read():
            return sorted(row.entry_key for row in method(CAMPAIGN, parent)), None
    return entry_type, entries, read


def _assert_service_subset_result(result, selected, consumer):
    keys, html = result
    assert keys == sorted(row.entry_key for row in selected)
    if consumer in {"class", "subclass"}:
        assert ("Subset Feature A" in html) == any(row.title == "Subset Feature A" for row in selected)
        assert ("Subset Feature B" in html) == any(row.title == "Subset Feature B" for row in selected)
        assert ("Parent fallback" in html) == (not selected)


@pytest.mark.parametrize("consumer", _SERVICE_SUBSET_CONSUMERS)
@pytest.mark.parametrize("start_subset", [False, True], ids=["full-first", "subset-first"])
def test_service_request_loaders_follow_relevant_subset_replacement_and_reuse_irrelevant_context(revision_app, monkeypatch, consumer, start_subset):
    service = _service()
    with revision_app.test_request_context("/"):
        entry_type, entries, read = _service_subset_reader(service, consumer)
        token = SystemsStore().get_durable_revision()
        original = service.list_enabled_entries_for_campaign
        reads = []
        def counted(*args, **kwargs):
            if kwargs.get("entry_type") == entry_type:
                reads.append(1)
            return original(*args, **kwargs)
        monkeypatch.setattr(service, "list_enabled_entries_for_campaign", counted)
        initial = entries[:1] if start_subset else entries
        if start_subset:
            _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=initial)
        _assert_service_subset_result(read(), initial, consumer)
        assert len(reads) == 1
        # This unrelated list cannot invalidate a progression/related-row result.
        _install_current_subset(service, CAMPAIGN, entry_type="rule", entries=[])
        _assert_service_subset_result(read(), initial, consumer)
        assert len(reads) == 1
        for selected in (entries[:1], entries[1:], [], entries[:1]):
            _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=selected)
            _assert_service_subset_result(read(), selected, consumer)
            assert SystemsStore().get_durable_revision() == token


@pytest.mark.parametrize("consumer", _SERVICE_SUBSET_CONSUMERS)
def test_service_request_loader_subset_drift_rejects_publication_including_enclosing_html(revision_app, monkeypatch, consumer):
    service = _service()
    with revision_app.test_request_context("/"):
        entry_type, entries, read = _service_subset_reader(service, consumer)
        token = SystemsStore().get_durable_revision()
        _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=entries[:1])
        original = service.list_enabled_entries_for_campaign
        reads = []
        def drift(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get("entry_type") == entry_type:
                reads.append(1)
                if len(reads) == 1:
                    _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=entries[1:])
            return result
        monkeypatch.setattr(service, "list_enabled_entries_for_campaign", drift)
        renders = []
        original_render = service._render_character_sheet_progression_groups
        def render(groups):
            renders.append(1)
            return original_render(groups)
        monkeypatch.setattr(service, "_render_character_sheet_progression_groups", render)
        read()
        # Return to A: neither a changed-context inner result nor the enclosing
        # HTML may have been published under A during the first build.
        _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=entries[:1])
        before = len(reads)
        _assert_service_subset_result(read(), entries[:1], consumer)
        assert len(reads) > before
        if consumer in {"class", "subclass"}:
            assert len(renders) == 2
        _install_current_subset(service, CAMPAIGN, entry_type=entry_type, entries=entries[1:])
        _assert_service_subset_result(read(), entries[1:], consumer)
        assert SystemsStore().get_durable_revision() == token


def _prefetch_item_catalog(service):
    from player_wiki.character_builder_catalogs import _build_targeted_item_support_catalog
    return _build_targeted_item_support_catalog([
        {"id": "stone", "name": "Before", "is_equipped": True,
            "systems_ref": {"entry_key": ENTRY, "entry_type": "item", "source_id": "TEST"}},
    ], campaign_slug=CAMPAIGN, systems_service=service, campaign_page_records=[])


def _install_prefetch(service, catalog):
    service.set_enabled_entry_subset_for_request(CAMPAIGN, entry_type="item",
        entries=catalog["entries"], source_generation=catalog["systems_source_generation"])


@pytest.mark.parametrize("recipe", ["full", "scoped", "prepared"])
@pytest.mark.parametrize("phase", ["installed", "load-to-install", "during-load"])
def test_prefetch_generation_drift_refreshes_mechanics_and_caches_full_fallback_once(revision_app, monkeypatch, recipe, phase):
    from player_wiki.character_builder_catalogs import _list_campaign_enabled_entries
    service = _service()
    with revision_app.test_request_context("/"):
        store = service.store
        get_db().execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(14)), ENTRY))
        get_db().commit()
        other = store.upsert_entry(LIBRARY, "TEST", entry_key="item|prefetch-other", entry_type="item", slug="prefetch-other", title="Other")
        before_token = service.get_durable_revision()
        before_row = store.get_entry(LIBRARY, ENTRY)
        full_reads = []
        original_list = store.list_entries_for_campaign
        def counted(*args, **kwargs):
            if kwargs.get("entry_type") == "item":
                full_reads.append(1)
            return original_list(*args, **kwargs)
        monkeypatch.setattr(store, "list_entries_for_campaign", counted)
        def commit():
            get_db().execute("UPDATE systems_entries SET metadata_json=? WHERE entry_key=?", (json.dumps(_ability_minimum_metadata(18)), ENTRY))
            get_db().commit()
        if phase == "during-load":
            original_identity = service.list_enabled_entries_by_identity_for_campaign
            def drift(*args, **kwargs):
                rows = original_identity(*args, **kwargs)
                commit()
                return rows
            monkeypatch.setattr(service, "list_enabled_entries_by_identity_for_campaign", drift)
        catalog = _prefetch_item_catalog(service)
        assert catalog["systems_source_generation"][0] == before_token
        if phase == "during-load":
            monkeypatch.setattr(service, "list_enabled_entries_by_identity_for_campaign", original_identity)
        elif phase == "load-to-install":
            commit()
        _install_prefetch(service, catalog)
        if phase == "installed":
            assert _context_mechanics_read(service, recipe) == 14
            assert full_reads == []
            commit()
        assert _context_mechanics_read(service, recipe) == 18
        assert sorted(row.entry_key for row in _list_campaign_enabled_entries(service, CAMPAIGN, "item")) == sorted([ENTRY, other.entry_key])
        assert _context_mechanics_read(service, recipe) == 18
        assert len(full_reads) == 1
        assert service.get_durable_revision() != before_token
        after_row = store.get_entry(LIBRARY, ENTRY)
        assert (before_row.id, before_row.updated_at) == (after_row.id, after_row.updated_at)
    with revision_app.test_request_context("/"):
        # The expired subset cannot label the full fallback for another request.
        fresh_catalog = _prefetch_item_catalog(service)
        _install_prefetch(service, fresh_catalog)
        assert [row.entry_key for row in _list_campaign_enabled_entries(service, CAMPAIGN, "item")] == [ENTRY]
        assert _context_mechanics_read(service, recipe) == 18
        assert len(full_reads) == 1
    with revision_app.test_request_context("/"):
        assert sorted(row.entry_key for row in _list_campaign_enabled_entries(service, CAMPAIGN, "item")) == sorted([ENTRY, other.entry_key])
        assert len(full_reads) == 1


@pytest.mark.parametrize("mutation", ["unrelated-entry", "disabled-source", "disabled-entry", "unknown-generation"])
def test_prefetch_expiration_preserves_current_membership_policy_and_direct_service_reads(revision_app, mutation):
    service = _service()
    with revision_app.test_request_context("/"):
        other = service.store.upsert_entry(LIBRARY, "TEST", entry_key="item|prefetch-other", entry_type="item", slug="prefetch-other", title="Other")
        catalog = _prefetch_item_catalog(service)
        before = service.get_durable_revision()
        if mutation == "unknown-generation":
            service.set_enabled_entry_subset_for_request(CAMPAIGN, entry_type="item", entries=catalog["entries"])
        else:
            _install_prefetch(service, catalog)
            if mutation == "disabled-source":
                get_db().execute("UPDATE campaign_enabled_sources SET is_enabled=0 WHERE source_id='TEST'")
            elif mutation == "disabled-entry":
                service.store.upsert_campaign_entry_override(CAMPAIGN, library_slug=LIBRARY, entry_key=ENTRY,
                    is_enabled_override=False, visibility_override=None)
            else:
                get_db().execute("UPDATE systems_entries SET title='Changed other' WHERE entry_key=?", (other.entry_key,))
            get_db().commit()
        expected = [] if mutation == "disabled-source" else [other.entry_key] if mutation == "disabled-entry" else [ENTRY, other.entry_key]
        assert sorted(row.entry_key for row in service.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")) == sorted(expected)
        assert (service.get_durable_revision() == before) == (mutation == "unknown-generation")
        # With unchanged selected-record bytes, a fresh receipt must still select
        # only the exact prefetch membership, never an earlier full fallback.
        fresh = _prefetch_item_catalog(service)
        _install_prefetch(service, fresh)
        assert [row.entry_key for row in service.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")] == ([] if mutation in {"disabled-source", "disabled-entry"} else [ENTRY])


def test_prefetch_generation_expires_on_yaml_policy_drift_without_token_change(revision_app, tmp_path):
    repository, refresh = _yaml_repository(tmp_path)
    service = SystemsService(SystemsStore(), repository).character_read_view()
    with revision_app.test_request_context("/"):
        get_db().execute("DELETE FROM campaign_enabled_sources WHERE campaign_slug=?", (CAMPAIGN,))
        get_db().commit()
        catalog = _prefetch_item_catalog(service)
        before = service.get_durable_revision()
        refresh(False, "players")
        _install_prefetch(service, catalog)
        assert service.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item") == []
        assert service.get_durable_revision() == before
