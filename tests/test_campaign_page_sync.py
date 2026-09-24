from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from flask import Flask

from player_wiki import campaign_page_store as page_module
from player_wiki.campaign_page_store import CampaignPageStore
from player_wiki.db import close_db, get_db, init_database


CAMPAIGN = "sync-campaign"


@pytest.fixture
def sync_env(tmp_path, monkeypatch):
    """Real schema and SQLite row triggers, with no repository/request recovery."""
    app = Flask(__name__)
    app.config["DB_PATH"] = tmp_path / "sync.sqlite3"
    app.teardown_appcontext(close_db)
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(page_module, "utcnow", lambda: clock[0])
    with app.app_context():
        init_database()
        db = get_db()
        events = []
        # Python-side events survive rollback, unlike rows in an audit table.
        db.create_function("observe_sync_row", 4, lambda *event: events.append(event))
        for table in ("campaign_pages", "campaign_page_sync_state"):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                row = "OLD" if operation == "DELETE" else "NEW"
                page_ref = f"{row}.page_ref" if table == "campaign_pages" else "''"
                db.execute(
                    f"""CREATE TEMP TRIGGER observe_{table}_{operation}
                    AFTER {operation} ON {table}
                    BEGIN
                        SELECT observe_sync_row(
                            '{table}', '{operation}', {row}.campaign_slug, {page_ref}
                        );
                    END"""
                )
        db.commit()
        yield SimpleNamespace(
            store=CampaignPageStore(), db=db, content=tmp_path / "content",
            clock=clock, events=events,
        )


def _write(env, page_ref="notes/page", *, metadata=None, body="Original body"):
    path = env.content / f"{page_ref}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if metadata is None:
        metadata = {"title": "Original title", "section": "Notes", "published": True}
    path.write_text(
        "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + body + "\n",
        encoding="utf-8",
    )
    return path


def _sync(env):
    env.store.sync_campaign_pages(CAMPAIGN, env.content)


def _rows(env):
    return {
        (row["campaign_slug"], row["page_ref"]): dict(row)
        for row in env.db.execute("SELECT * FROM campaign_pages").fetchall()
    }


def _page_events(env):
    return [event[1:] for event in env.events if event[0] == "campaign_pages"]


def _bookkeeping_events(env):
    return [event[1:] for event in env.events if event[0] == "campaign_page_sync_state"]


def _next_sync(env):
    env.events.clear()
    env.clock[0] = datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("normalization", ["identical", "key-order", "crlf", "body-edges"])
def test_normalized_repeats_validate_without_page_row_writes(sync_env, monkeypatch, normalization):
    env = sync_env
    metadata = {"title": "A page", "aliases": ["First", "Second"], "custom": {"a": 1, "b": 2}}
    path = _write(env, metadata=metadata, body="Text [[notes/target|label]]")
    _sync(env)
    assert _page_events(env) == [("INSERT", CAMPAIGN, "notes/page")]
    before = _rows(env)
    if normalization == "key-order":
        _write(env, metadata=dict(reversed(list(metadata.items()))), body="Text [[notes/target|label]]")
    elif normalization == "crlf":
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    elif normalization == "body-edges":
        _write(env, metadata=metadata, body=" \n\tText [[notes/target|label]]\n \t")
    validated = []
    original_validate = env.store.validate_page_upsert

    def validate(*args, **kwargs):
        assert env.db.in_transaction
        validated.append(args[1])
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(env.store, "validate_page_upsert", validate)
    _next_sync(env)
    _sync(env)
    _sync(env)
    assert validated == ["notes/page", "notes/page"]
    assert _page_events(env) == []
    assert _rows(env) == before
    assert _bookkeeping_events(env) == [("UPDATE", CAMPAIGN, "")] * 2


def test_mixed_sync_changes_only_exact_rows_and_preserves_other_campaign(sync_env):
    env = sync_env
    for ref in ("a-stable", "b-change", "c-derived", "d-delete"):
        _write(env, ref)
    _sync(env)
    env.store.upsert_page("other-campaign", "a-stable", metadata={"title": "Other"}, body_markdown="Other")
    env.db.execute(
        "UPDATE campaign_pages SET searchable_text = 'stale derived text' WHERE campaign_slug = ? AND page_ref = ?",
        (CAMPAIGN, "c-derived"),
    )
    env.db.commit()
    before = _rows(env)
    _write(env, "b-change", metadata={"title": "New title", "aliases": ["Changed"]}, body="New [[link]]")
    _write(env, "e-insert")
    (env.content / "d-delete.md").unlink()
    _next_sync(env)
    _sync(env)
    after = _rows(env)
    assert _page_events(env) == [
        ("UPDATE", CAMPAIGN, "b-change"), ("UPDATE", CAMPAIGN, "c-derived"),
        ("INSERT", CAMPAIGN, "e-insert"), ("DELETE", CAMPAIGN, "d-delete"),
    ]
    for key in ((CAMPAIGN, "a-stable"), ("other-campaign", "a-stable")):
        assert after[key] == before[key]
    for ref in ("b-change", "c-derived"):
        assert after[CAMPAIGN, ref]["created_at"] == before[CAMPAIGN, ref]["created_at"]
        assert after[CAMPAIGN, ref]["updated_at"] != before[CAMPAIGN, ref]["updated_at"]
    assert after[CAMPAIGN, "b-change"]["body_markdown"] == "New [[link]]"
    assert after[CAMPAIGN, "c-derived"]["searchable_text"] == "original title original body"
    assert after[CAMPAIGN, "e-insert"]["created_at"] == after[CAMPAIGN, "e-insert"]["updated_at"]
    assert (CAMPAIGN, "d-delete") not in after
    _next_sync(env)
    _sync(env)
    assert _page_events(env) == []


@pytest.mark.parametrize(("field", "drift"), [
    ("route_slug", "wrong-route"), ("title", "Wrong title"), ("section", "Wrong"),
    ("subsection", "Wrong"), ("page_type", "wrong"), ("display_order", 42),
    ("published", 0), ("aliases_json", '["wrong"]'), ("summary", "Wrong"),
    ("image_path", "wrong.png"), ("image_alt", "Wrong"), ("image_caption", "Wrong"),
    ("reveal_after_session", 42), ("source_ref", "wrong/source"),
    ("metadata_json", '{"wrong": true}'), ("raw_link_targets_json", '["wrong"]'),
    ("searchable_text", "wrong"), ("body_markdown", "Wrong"),
])
def test_each_persisted_field_drift_requires_a_real_update(sync_env, field, drift):
    env = sync_env
    _write(env)
    _sync(env)
    original = _rows(env)[CAMPAIGN, "notes/page"]
    env.db.execute(
        f"UPDATE campaign_pages SET {field} = ? WHERE campaign_slug = ? AND page_ref = ?",
        (drift, CAMPAIGN, "notes/page"),
    )
    env.db.commit()
    _next_sync(env)
    _sync(env)
    restored = _rows(env)[CAMPAIGN, "notes/page"]
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "notes/page")]
    assert restored["updated_at"] != original["updated_at"]
    assert {k: v for k, v in restored.items() if k != "updated_at"} == {
        k: v for k, v in original.items() if k != "updated_at"
    }


@pytest.mark.parametrize(("field", "value"), [
    ("slug", "changed-route"), ("title", "Changed"), ("section", "Changed"),
    ("subsection", "Changed"), ("type", "changed"), ("display_order", 7),
    ("published", False), ("aliases", ["Second", "First"]), ("summary", "Changed"),
    ("image", "changed.png"), ("image_alt", "Changed"), ("image_caption", "Changed"),
    ("reveal_after_session", 7), ("source_ref", "changed/source"),
    ("custom", {"value": 7}), ("redirect_from", ["previous-route"]),
])
def test_source_metadata_changes_are_not_normalized_away(sync_env, field, value):
    env = sync_env
    metadata = {"title": "Original title", "aliases": ["First", "Second"]}
    _write(env, metadata=metadata)
    _sync(env)
    metadata[field] = value
    _write(env, metadata=metadata)
    _next_sync(env)
    _sync(env)
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "notes/page")]
    record = env.store.get_page_record(CAMPAIGN, "notes/page", include_body=True)
    assert record.metadata == metadata
    _next_sync(env)
    _sync(env)
    assert _page_events(env) == []


def _protect(env, table, state, page_ref):
    original = b"Original retained authority"
    digest = hashlib.sha256(original).hexdigest()
    common = {
        "operation_id": "a" * 32, "campaign_slug": CAMPAIGN, "page_ref": page_ref,
        "state": state, "created_at": "original", "updated_at": "original",
    }
    if table == "player_wiki_reconciliation_operations":
        common.update(
            operation_kind="api_upsert", primary_authority="markdown",
            desired_primary_ref=f"{page_ref}.md", previous_primary_digest=digest,
            desired_primary_digest=digest, previous_markdown_digest=digest,
            desired_markdown_digest=digest,
            desired_markdown=original if state != "repository_pending" else None,
        )
    else:
        common.update(
            operation_kind="api_delete", source_ref=f"{page_ref}.md",
            tombstone_ref="retained.tombstone", source_sha256=digest, source_size=len(original),
        )
    env.db.execute(
        f"INSERT INTO {table} ({', '.join(common)}) VALUES ({', '.join('?' for _ in common)})",
        tuple(common.values()),
    )
    env.db.commit()
    tombstone = env.content / "retained.tombstone"
    tombstone.write_bytes(original)
    return dict(env.db.execute(f"SELECT * FROM {table}").fetchone()), tombstone


@pytest.mark.parametrize("table", ["player_wiki_reconciliation_operations", "player_wiki_deletion_operations"])
@pytest.mark.parametrize("state", ["prepared", "repository_pending", "conflict"])
@pytest.mark.parametrize("source_present", [True, False])
@pytest.mark.parametrize("row_present", [True, False])
def test_protection_preserves_row_or_absence_and_custody_then_resumes(
    sync_env, table, state, source_present, row_present,
):
    env = sync_env
    path = _write(env)
    _write(env, "notes/unrelated")
    _sync(env)
    if not row_present:
        env.store.delete_page(CAMPAIGN, "notes/page")
    journal, tombstone = _protect(env, table, state, "notes/page")
    if source_present:
        # Protected sources remain exempt from parsing, even when malformed.
        path.write_text("---\ntitle: [\n---\n", encoding="utf-8")
    else:
        path.unlink()
    source_bytes = path.read_bytes() if source_present else None
    before = _rows(env)
    _write(env, "notes/unrelated", body="Unrelated changed")
    _next_sync(env)
    _sync(env)
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "notes/unrelated")]
    assert _rows(env).get((CAMPAIGN, "notes/page")) == before.get((CAMPAIGN, "notes/page"))
    assert dict(env.db.execute(f"SELECT * FROM {table}").fetchone()) == journal
    assert tombstone.read_bytes() == b"Original retained authority"
    assert (path.read_bytes() if path.exists() else None) == source_bytes
    env.db.execute(f"DELETE FROM {table}")
    env.db.commit()
    if source_present:
        _write(env, body="Resumed filesystem authority")
    _next_sync(env)
    _sync(env)
    operation = "UPDATE" if row_present else "INSERT"
    expected = [(operation, CAMPAIGN, "notes/page")] if source_present else (
        [("DELETE", CAMPAIGN, "notes/page")] if row_present else []
    )
    assert _page_events(env) == expected
    if source_present:
        assert _rows(env)[CAMPAIGN, "notes/page"]["body_markdown"] == "Resumed filesystem authority"
    else:
        assert (CAMPAIGN, "notes/page") not in _rows(env)
    assert tombstone.read_bytes() == b"Original retained authority"


@pytest.mark.parametrize(("raw", "error"), [
    ("---\ntitle: [\n---\n", yaml.YAMLError),
    ("---\n- nonempty-list\n---\nBody", ValueError),
    ("---\nnonempty-scalar\n---\nBody", ValueError),
    ("---\ndisplay_order: invalid\n---\nBody", ValueError),
    ("---\nreveal_after_session: invalid\n---\nBody", ValueError),
])
def test_malformed_input_rolls_back_earlier_changed_and_unchanged_pages(sync_env, raw, error):
    env = sync_env
    for ref in ("a-stable", "b-change", "z-invalid"):
        _write(env, ref)
    _sync(env)
    before = _rows(env)
    state_before = tuple(env.db.execute("SELECT * FROM campaign_page_sync_state").fetchone())
    _write(env, "b-change", body="Must roll back")
    (env.content / "z-invalid.md").write_text(raw, encoding="utf-8")
    _next_sync(env)
    with pytest.raises(error):
        _sync(env)
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "b-change")]
    assert _rows(env) == before
    assert tuple(env.db.execute("SELECT * FROM campaign_page_sync_state").fetchone()) == state_before
    assert not env.db.in_transaction


@pytest.mark.parametrize("destination", ["existing", "protected", "new"])
def test_duplicate_route_validation_rolls_back_batch(sync_env, destination):
    env = sync_env
    _write(env, "a-stable")
    _write(env, "b-change")
    if destination != "new":
        _write(env, "c-owner", metadata={"title": "Owner", "slug": "shared"})
    _sync(env)
    if destination == "protected":
        _protect(env, "player_wiki_reconciliation_operations", "prepared", "c-owner")
    before = _rows(env)
    _write(env, "b-change", body="Must roll back")
    if destination == "new":
        _write(env, "c-owner", metadata={"title": "Owner", "slug": "shared"})
    _write(env, "z-duplicate", metadata={"title": "Duplicate", "slug": "shared"})
    _next_sync(env)
    with pytest.raises(ValueError, match="slug is already in use"):
        _sync(env)
    assert _rows(env) == before
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "b-change")] + (
        [("INSERT", CAMPAIGN, "c-owner")] if destination == "new" else []
    )
    assert not env.db.in_transaction


@pytest.mark.parametrize("fault", ["read", "parse", "write", "delete", "pre-commit"])
def test_faults_roll_back_mixed_batch_and_successful_retry_skips_stable_row(sync_env, monkeypatch, fault):
    env = sync_env
    for ref in ("a-stable", "b-change", "c-fault", "d-delete"):
        _write(env, ref)
    _sync(env)
    before = _rows(env)
    sync_before = tuple(env.db.execute("SELECT * FROM campaign_page_sync_state").fetchone())
    fingerprint_before = dict(env.store._content_fingerprints)
    _write(env, "b-change", body="Changed")
    _write(env, "c-fault", body="Fault target")
    _write(env, "e-insert")
    (env.content / "d-delete.md").unlink()
    _next_sync(env)

    def fail():
        raise RuntimeError(f"injected {fault}")

    with monkeypatch.context() as patch:
        if fault == "read":
            original_read = Path.read_text

            def read(path, *args, **kwargs):
                if path.name == "c-fault.md":
                    fail()
                return original_read(path, *args, **kwargs)

            patch.setattr(Path, "read_text", read)
        elif fault == "parse":
            original_parse = page_module.parse_frontmatter

            def parse(raw):
                if "Fault target" in raw:
                    fail()
                return original_parse(raw)

            patch.setattr(page_module, "parse_frontmatter", parse)
        else:
            class FaultConnection:
                def __getattr__(self, name):
                    return getattr(env.db, name)

                def execute(self, sql, parameters=()):
                    normalized = " ".join(sql.split()).upper()
                    if fault == "write" and normalized.startswith("INSERT INTO CAMPAIGN_PAGES") and parameters[1] == "c-fault":
                        fail()
                    if fault == "delete" and normalized.startswith("DELETE FROM CAMPAIGN_PAGES"):
                        fail()
                    return env.db.execute(sql, parameters)

                def commit(self):
                    if fault == "pre-commit":
                        fail()
                    return env.db.commit()

            patch.setattr(page_module, "get_db", lambda: FaultConnection())
        with pytest.raises(RuntimeError, match=f"injected {fault}"):
            _sync(env)
    assert _rows(env) == before
    assert tuple(env.db.execute("SELECT * FROM campaign_page_sync_state").fetchone()) == sync_before
    assert env.store._content_fingerprints == fingerprint_before
    assert not env.db.in_transaction
    attempted = [("UPDATE", CAMPAIGN, "b-change")]
    if fault in ("delete", "pre-commit"):
        attempted += [("UPDATE", CAMPAIGN, "c-fault"), ("INSERT", CAMPAIGN, "e-insert")]
    if fault == "pre-commit":
        attempted += [("DELETE", CAMPAIGN, "d-delete")]
    assert _page_events(env) == attempted
    env.events.clear()
    _sync(env)
    assert _page_events(env) == [
        ("UPDATE", CAMPAIGN, "b-change"), ("UPDATE", CAMPAIGN, "c-fault"),
        ("INSERT", CAMPAIGN, "e-insert"), ("DELETE", CAMPAIGN, "d-delete"),
    ]
    assert _rows(env)[CAMPAIGN, "a-stable"] == before[CAMPAIGN, "a-stable"]


def test_empty_seeding_and_none_content_keep_existing_contract(sync_env):
    env = sync_env
    env.store.sync_campaign_pages(CAMPAIGN, None)
    assert env.events == []
    env.store.ensure_campaign_seeded(CAMPAIGN, env.content)
    assert _page_events(env) == []
    assert _bookkeeping_events(env) == [("INSERT", CAMPAIGN, "")]
    _next_sync(env)
    env.store.ensure_campaign_seeded(CAMPAIGN, env.content)
    assert _bookkeeping_events(env) == [("UPDATE", CAMPAIGN, "")]
    assert _page_events(env) == []


@pytest.mark.parametrize("reload_enabled", [True, False])
def test_read_refresh_initial_seed_and_explicit_sync_preserve_admission(sync_env, reload_enabled):
    env = sync_env
    env.store.reload_enabled = reload_enabled
    _write(env, "a-stable")
    _write(env, "b-change")
    env.store.list_pages(CAMPAIGN, content_dir=env.content)
    assert _page_events(env) == [("INSERT", CAMPAIGN, "a-stable"), ("INSERT", CAMPAIGN, "b-change")]
    stable = _rows(env)[CAMPAIGN, "a-stable"]
    _write(env, "b-change", body="Clearly different size forces fingerprint admission")
    _next_sync(env)
    env.store.list_page_records(CAMPAIGN, content_dir=env.content)
    assert _page_events(env) == ([("UPDATE", CAMPAIGN, "b-change")] if reload_enabled else [])
    env.events.clear()
    _sync(env)
    assert _page_events(env) == ([] if reload_enabled else [("UPDATE", CAMPAIGN, "b-change")])
    assert _rows(env)[CAMPAIGN, "a-stable"] == stable


def test_identical_direct_save_still_updates_timestamp_and_obeys_commit_flag(sync_env):
    env = sync_env
    metadata = {"title": "Original title", "section": "Notes", "published": True}
    _write(env, metadata=metadata)
    _sync(env)
    before = _rows(env)[CAMPAIGN, "notes/page"]
    _next_sync(env)
    env.store.upsert_page(CAMPAIGN, "notes/page.md", metadata=metadata, body_markdown="Original body", commit=False)
    assert env.db.in_transaction
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "notes/page")]
    assert _rows(env)[CAMPAIGN, "notes/page"]["updated_at"] != before["updated_at"]
    env.db.rollback()
    assert _rows(env)[CAMPAIGN, "notes/page"] == before
    env.events.clear()
    env.store.upsert_page(CAMPAIGN, "notes/page", metadata=metadata, body_markdown="Original body")
    assert not env.db.in_transaction
    assert _page_events(env) == [("UPDATE", CAMPAIGN, "notes/page")]
    assert _rows(env)[CAMPAIGN, "notes/page"]["created_at"] == before["created_at"]
