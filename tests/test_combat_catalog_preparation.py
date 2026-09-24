from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
import re
import sqlite3

import pytest

import player_wiki.db as db_module
from player_wiki.auth_store import AuthStore
from player_wiki.character_assets import build_character_item_catalog
from player_wiki.character_page_records import list_visible_character_page_records
from player_wiki.db import close_db, get_db
from player_wiki.dnd5e_rules_reference import (
    DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY as SENTINEL,
    DND5E_RULES_REFERENCE_SOURCE_ID as RULES,
    DND5E_RULES_REFERENCE_VERSION as VERSION,
    build_dnd5e_rules_reference_entries,
)
from player_wiki.systems_store import SystemsStore
from tests.test_combat_context_consolidation import (
    ASYNC, CAMPAIGN, FIRST, LIVE, SECOND, _change_captured_world,
    _poll_headers, _write_campaign_config, context_world,
)
from tests.test_character_reconciliation import _deletion_coordinator


def _services(app):
    return app.extensions["systems_service"], app.extensions["campaign_page_store"]


def _watch_sql(monkeypatch):
    statements = []
    original = db_module._InstrumentedConnection.execute

    def execute(connection, sql, parameters=()):
        if str(sql).lstrip().upper().startswith("SELECT"):
            statements.append((" ".join(sql.split()), tuple(parameters)))
        return original(connection, sql, parameters)

    monkeypatch.setattr(db_module._InstrumentedConnection, "execute", execute)
    return statements


def _seed_spy(service, monkeypatch):
    calls = []
    original = service.ensure_builtin_library_seeded

    def seed(slug):
        calls.append(slug)
        return original(slug)

    monkeypatch.setattr(service, "ensure_builtin_library_seeded", seed)
    return calls


def _page(pages, ref="items/prepared-item", *, body="Original body.", **metadata):
    return pages.upsert_page(CAMPAIGN, ref, metadata={
        "title": "Prepared Item", "section": "Items", "type": "item",
        "published": True, **metadata,
    }, body_markdown=body)


def _item(service):
    service.ensure_builtin_library_seeded("DND-5E")
    service.store.upsert_campaign_enabled_source(
        CAMPAIGN, library_slug="DND-5E", source_id="PHB", is_enabled=True,
        default_visibility="players",
    )
    return service.store.upsert_entry(
        "DND-5E", "PHB", entry_key="r10-prepared-item", entry_type="item",
        slug="r10-prepared-item", title="Prepared Blade", player_safe_default=True,
        body={"name": "Prepared Blade"}, rendered_html="<p>Prepared blade body.</p>",
    )


@pytest.mark.parametrize("mode", ("cold", "stale-detail", "document"))
def test_prepared_combat_read_reuses_systems_and_raw_pages(
    app, client, monkeypatch, context_world, record_property, mode,
):
    service, pages = _services(app)
    path = f"/campaigns/{CAMPAIGN}/combat" if mode == "document" else LIVE
    headers = {**ASYNC, **({"X-Live-Detail-State-Token": "stale"} if mode == "stale-detail" else {})}
    if mode == "document":
        # Live setup leaves its login flash for the first document. Consume only
        # that asserted fixture message before comparing two equivalent reads.
        with client.session_transaction() as session:
            assert session.get("_flashes") == [("success", "Signed in as Owner Player.")]
            session.pop("_flashes")
    statements = _watch_sql(monkeypatch)
    rollbacks = []
    original_rollback = db_module._InstrumentedConnection.rollback
    def rollback(connection):
        rollbacks.append(True)
        return original_rollback(connection)
    monkeypatch.setattr(db_module._InstrumentedConnection, "rollback", rollback)

    # Reconstitute the original two independent page reads and public Systems
    # consumers without altering either production implementation.
    @contextmanager
    def original_read(_campaign, _pages):
        yield type("OriginalRead", (), {"systems_service": service, "list_page_records": staticmethod(pages.list_page_records)})()

    with monkeypatch.context() as legacy:
        legacy.setattr(service, "combat_detail_read", original_read)
        legacy.setattr(service, "list_page_records", pages.list_page_records, raising=False)
        reference = client.get(path, headers=headers)
    original_sql = list(statements)
    statements.clear()
    response = client.get(path, headers=headers)
    assert reference.status_code == response.status_code == 200
    if mode == "document":
        bodies = []
        for label, result in (("original", reference), ("prepared", response)):
            nonce = re.search(rb'nonce="([^"]+)"', result.data).group(1)
            assert ("'nonce-" + nonce.decode("ascii") + "'") in result.headers["Content-Security-Policy"]
            record_property(label + "_document", result.get_data(as_text=True))
            record_property(label + "_csp", result.headers["Content-Security-Policy"])
            bodies.append(result.data.replace(nonce, b"CONTROLLED-CSP-NONCE"))
        assert bodies[0] == bodies[1]
    else:
        assert response.data == reference.data
    assert b"data-combat-section-panel" in response.data
    record_property("original_sql_with_arguments", json.dumps(original_sql))
    record_property("prepared_sql_with_arguments", json.dumps(statements))
    record_property("response_parity", json.dumps({"bytes": len(response.data), "sha256": sha256(response.data).hexdigest()}))
    def table_reads(rows, table):
        return [(sql, p) for sql, p in rows if re.search(rf"\b(?:FROM|JOIN)\s+{table}\b", sql, re.I)]

    original_library = [p for sql, p in table_reads(original_sql, "systems_libraries")]
    prepared_library = [p for sql, p in table_reads(statements, "systems_libraries")]
    # The accepted target already reuses warmed catalog values in both paths.
    assert original_library == [("DND-5E",)]
    assert prepared_library == [("DND-5E",)]
    page_lists = lambda rows: [(sql, p) for sql, p in rows if "FROM campaign_pages" in sql and "ORDER BY" in sql]
    assert len(page_lists(original_sql)) == 2
    assert len(page_lists(statements)) == 1
    assert page_lists(original_sql)[0] == page_lists(original_sql)[1] == page_lists(statements)[0]
    for table, count in (("systems_sources", 1), ("systems_entries", 2),
                         ("campaign_entry_overrides", 0), ("campaign_enabled_sources", 0)):
        assert table_reads(original_sql, table) == table_reads(statements, table)
        assert len(table_reads(statements, table)) == count
    # Seven additional durable checks preserve external-commit/rollback safety;
    # removing one page list yields six net reads with identical response bytes.
    assert len(table_reads(original_sql, "systems_revision")) == 3
    assert len(table_reads(statements, "systems_revision")) == 10
    assert len(original_sql) == (30 if mode == "document" else 31)
    assert len(statements) == (36 if mode == "document" else 37)
    assert rollbacks == []
    if mode != "document":
        assert response.headers["X-Live-Write-Count"] == "0"
        assert response.headers["X-Live-Commit-Count"] == "0"
        assert int(response.headers["X-Live-Query-Count"]) == len(statements)


@pytest.mark.parametrize("case", (
    "same-detail", "unchanged", "unowned", "unsupported", "npc", "protected", "pending-deletion",
))
def test_no_preparation_for_omitted_or_denied_detail(
    app, client, users, monkeypatch, context_world, case,
):
    combat, first, second, npc, baseline = context_world
    service, _pages = _services(app)
    headers = dict(ASYNC)
    if case in {"same-detail", "unchanged"}:
        headers = _poll_headers(baseline, detail_only=case == "same-detail")
    else:
        with app.app_context():
            combat.delete_combatant(CAMPAIGN, second.id)
            if case == "unowned":
                AuthStore().upsert_character_assignment(users["party"]["id"], CAMPAIGN, FIRST)
            elif case == "unsupported":
                _write_campaign_config(app, lambda config: config.update(system="xianxia", systems_library="xianxia"))
            elif case == "npc":
                combat.delete_combatant(CAMPAIGN, first.id)
                combat.set_current_turn(CAMPAIGN, npc.id)
            elif case == "protected":
                _change_captured_world(app, combat, first, second, "protected")
            elif case == "pending-deletion":
                def hold(event, _operation_id):
                    if event == "after_commit":
                        raise RuntimeError("retained deletion boundary")
                with pytest.raises(RuntimeError, match="retained deletion boundary"):
                    _deletion_coordinator(app, hold).delete(CAMPAIGN, FIRST, operation_kind="content_api")
                get_db().execute("UPDATE character_deletion_operations SET state = 'conflict' WHERE character_slug = ?", (FIRST,))
                get_db().commit()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Omitted or denied detail must not start preparation")

    monkeypatch.setattr(service, "combat_detail_read", forbidden)
    response = client.get(LIVE, headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    if case == "unchanged":
        assert payload == {"changed": False, "live_revision": baseline["live_revision"], "live_view_token": baseline["live_view_token"]}
    else:
        assert payload["changed"] is True
        assert "data-combat-section-panel" not in payload.get("context_html", "")


@pytest.mark.parametrize("case", ("public-after-prepared", "prepared-after-public", "next-request", "exception-exit"))
def test_public_and_character_defaults_keep_revalidation(app, monkeypatch, case):
    service, pages = _services(app)
    with app.app_context():
        service.ensure_builtin_library_seeded("DND-5E")
    calls = _seed_spy(service, monkeypatch)
    with app.test_request_context("/"):
        get_db()
        if case == "prepared-after-public":
            service.get_campaign_library(CAMPAIGN)
            assert calls == ["DND-5E"]
        try:
            with service.combat_detail_read(CAMPAIGN, pages) as prepared:
                assert prepared.systems_service is service
                prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
                prepared.get_builder_static_revision(CAMPAIGN, entry_types=("item",))
                assert len(calls) == (2 if case == "prepared-after-public" else 1)
                if case == "public-after-prepared":
                    service.get_campaign_library(CAMPAIGN)
                    assert calls == ["DND-5E", "DND-5E"]
                if case == "exception-exit":
                    raise ValueError("operation stopped")
        except ValueError as exc:
            assert case == "exception-exit" and str(exc) == "operation stopped"
        assert service._combat_detail_preparation(CAMPAIGN) is None
        assert prepared.raw_pages is None and prepared.prepared_library is None
        with pytest.raises(RuntimeError, match="preparation has ended"):
            prepared.list_page_records(CAMPAIGN, include_body=True)
        previous = len(calls)
        service.character_read_view().get_campaign_library(CAMPAIGN)
        assert len(calls) == previous
        service.get_campaign_library(CAMPAIGN)
        assert len(calls) == previous + 1
    if case == "next-request":
        from flask import g

        previous = len(calls)
        with app.test_request_context("/"):
            assert getattr(g, "db_connection", None) is None
            with service.combat_detail_read(CAMPAIGN, pages) as prepared:
                prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
        # The first load opens this request's connection from an unknown initial
        # generation and cannot be cached. A subsequent read captures a known
        # generation; established-connection scopes above still seed only once.
        assert len(calls) == previous + 2


@pytest.mark.parametrize("damage", ("missing-library", "missing-source", "missing-sentinel", "wrong-version", "same-count-stale-seed"))
def test_first_use_and_rule_repair_preserve_work(app, damage):
    service, pages = _services(app)
    expected = build_dnd5e_rules_reference_entries()
    with app.test_request_context("/"):
        service.ensure_builtin_library_seeded("DND-5E")
        connection = get_db()
        if damage == "missing-library":
            connection.execute("DELETE FROM systems_libraries WHERE library_slug = ?", ("DND-5E",))
        elif damage == "missing-source":
            connection.execute("DELETE FROM systems_sources WHERE library_slug = ? AND source_id = ?", ("DND-5E", RULES))
        elif damage == "missing-sentinel":
            connection.execute("DELETE FROM systems_entries WHERE library_slug = ? AND entry_key = ?", ("DND-5E", SENTINEL))
        elif damage == "wrong-version":
            connection.execute("UPDATE systems_entries SET metadata_json = '{}' WHERE library_slug = ? AND entry_key = ?", ("DND-5E", SENTINEL))
        else:
            stale = deepcopy(expected)
            for entry in stale:
                entry["metadata"]["seed_version"] = "old-r10-fixture"
                entry["rendered_html"] = "<p>Stale seed body.</p>"
            service.store.replace_entries_for_source("DND-5E", RULES, entries=stale)
            assert service.store.count_entries_for_source("DND-5E", RULES) == len(expected)
        connection.commit()
        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="rule")
            prepared.get_builder_static_revision(CAMPAIGN, entry_types=("rule",))
        actual = service.store.list_entries_for_source("DND-5E", RULES, limit=None)
        assert {row.entry_key: row.rendered_html for row in actual} == {row["entry_key"]: row["rendered_html"] for row in expected}
        assert service.store.get_entry("DND-5E", SENTINEL).metadata["seed_version"] == VERSION
        assert service.store.get_source("DND-5E", RULES) is not None


@pytest.mark.parametrize("change", ("source-policy", "entry-override", "shared-entry", "page-row", "repository-refresh"))
def test_same_request_mutation_invalidates_preparation(app, monkeypatch, change):
    service, pages = _services(app)
    with app.test_request_context("/"):
        item = _item(service)
        _page(pages)
        calls = _seed_spy(service, monkeypatch)
        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            initial = prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
            assert item.entry_key in {row.entry_key for row in initial}
            old_revision = prepared.get_builder_static_revision(CAMPAIGN, entry_types=("item",))
            old_pages = prepared.list_page_records(CAMPAIGN, include_body=True)
            assert len(calls) == 1
            if change == "source-policy":
                service.store.upsert_campaign_enabled_source(CAMPAIGN, library_slug="DND-5E", source_id="PHB", is_enabled=False, default_visibility="players")
            elif change == "entry-override":
                service.store.upsert_campaign_entry_override(CAMPAIGN, library_slug="DND-5E", entry_key=item.entry_key, visibility_override=None, is_enabled_override=False)
            elif change == "shared-entry":
                get_db().execute("UPDATE systems_entries SET title = ?, updated_at = ? WHERE entry_key = ?", ("Changed Blade", "2099-01-01T00:00:00+00:00", item.entry_key))
                get_db().commit()
            elif change == "page-row":
                _page(pages, body="Changed body.")
            else:
                service.repository_store.refresh_from_database()
            current = prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
            revision = prepared.get_builder_static_revision(CAMPAIGN, entry_types=("item",))
            current_pages = prepared.list_page_records(CAMPAIGN, include_body=True)
            assert len(calls) == 2
            if change in {"source-policy", "entry-override"}:
                assert item.entry_key not in {row.entry_key for row in current}
                assert revision != old_revision
            elif change == "shared-entry":
                assert next(row.title for row in current if row.entry_key == item.entry_key) == "Changed Blade"
                assert revision != old_revision
            elif change == "page-row":
                assert current_pages != old_pages
                assert any(row.page.body_markdown == "Changed body." for row in current_pages)
            else:
                assert current == initial and revision == old_revision


@pytest.mark.parametrize("case", ("empty", "hidden-item", "unpublished-item", "visible-custom-item", "duplicate-title", "nonitems-and-sessions", "body-and-order"))
def test_raw_page_projections_preserve_content(app, case):
    service, pages = _services(app)
    with app.test_request_context("/"):
        service.ensure_builtin_library_seeded("DND-5E")
        get_db().execute("DELETE FROM campaign_pages WHERE campaign_slug = ?", (CAMPAIGN,))
        get_db().commit()
        if case != "empty":
            _page(pages, published=case != "unpublished-item", reveal_after_session=999 if case == "hidden-item" else 0, body="**Exact body**\n\n[Reference](../items/other)")
        if case == "duplicate-title":
            _page(pages, "items/other", body="Distinct duplicate body.")
        if case == "nonitems-and-sessions":
            _page(pages, "mechanics/prepared", section="Mechanics", type="mechanic")
            _page(pages, "sessions/prepared", section="Sessions", type="session")
        if case == "body-and-order":
            _page(pages, "items/earlier", title="A Blade", order=-2, body="Earlier body.")
        campaign = service.repository_store.refresh_from_database().get_campaign(CAMPAIGN)
        expected_visible = list_visible_character_page_records(pages, CAMPAIGN, campaign, excluded_sections={"Sessions"})
        expected_catalog = build_character_item_catalog(service, pages, CAMPAIGN)
        raw = pages.list_page_records(CAMPAIGN, include_body=True)
        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            visible = list_visible_character_page_records(prepared, CAMPAIGN, campaign, excluded_sections={"Sessions"})
            catalog = build_character_item_catalog(prepared, prepared, CAMPAIGN)
            assert visible == expected_visible
            assert catalog == expected_catalog
            assert prepared.list_page_records(CAMPAIGN, include_body=True) == raw
            assert all(row.page.section != "Sessions" for row in visible)
            if case in {"hidden-item", "unpublished-item"}:
                assert len(raw) == 1 and visible == []
            if case == "empty":
                assert raw == visible == []
            if case == "duplicate-title":
                assert len({row.page_ref for row in raw}) == 2


@pytest.mark.parametrize("case", ("other-campaign", "other-store", "source-loader-error", "page-loader-error", "consumer-mutation"))
def test_prepared_scope_isolation_and_failure(app, monkeypatch, case):
    service, pages = _services(app)
    with app.test_request_context("/"):
        service.ensure_builtin_library_seeded("DND-5E")
        _page(pages)
        calls = _seed_spy(service, monkeypatch)
        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            if case == "source-loader-error":
                original = service._build_campaign_source_states
                with monkeypatch.context() as failure:
                    failure.setattr(service, "_build_campaign_source_states", lambda *_: (_ for _ in ()).throw(ValueError("source failure")))
                    with pytest.raises(ValueError, match="source failure"):
                        prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
                assert service._build_campaign_source_states == original
                assert prepared.list_campaign_source_states(CAMPAIGN)
            elif case == "page-loader-error":
                with monkeypatch.context() as failure:
                    failure.setattr(pages, "list_page_records", lambda *_, **__: (_ for _ in ()).throw(ValueError("page failure")))
                    with pytest.raises(ValueError, match="page failure"):
                        prepared.list_page_records(CAMPAIGN, include_body=True)
                assert prepared.list_page_records(CAMPAIGN, include_body=True)
            else:
                prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
                captured = prepared.list_page_records(CAMPAIGN, include_body=True)
                if case == "other-campaign":
                    assert prepared.list_page_records("other-campaign", include_body=True) == []
                    assert prepared.list_enabled_entries_for_campaign("other-campaign", entry_type="item") == []
                    assert prepared.list_page_records(CAMPAIGN, include_body=True) == captured
                elif case == "other-store":
                    monkeypatch.setattr(service, "store", SystemsStore())
                    prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
                    assert len(calls) == 2
                    close_db()
                    get_db()
                    prepared.list_enabled_entries_for_campaign(CAMPAIGN, entry_type="item")
                    assert len(calls) == 3
                else:
                    expected = list(captured)
                    captured.clear()
                    assert prepared.list_page_records(CAMPAIGN, include_body=True) == expected
                    sources = prepared.list_campaign_source_states(CAMPAIGN)
                    sources.clear()
                    assert prepared.list_campaign_source_states(CAMPAIGN)
        assert service._combat_detail_preparation(CAMPAIGN) is None


@pytest.mark.parametrize("timing", ("before-capture", "after-capture"))
def test_prepared_capture_interleaving(app, timing):
    service, pages = _services(app)
    with app.test_request_context("/"):
        service.ensure_builtin_library_seeded("DND-5E")
        _page(pages)
        service.repository_store.refresh_from_database()

        def external_write():
            with sqlite3.connect(app.config["DB_PATH"]) as connection:
                connection.execute("UPDATE campaign_pages SET body_markdown = ? WHERE campaign_slug = ? AND page_ref = ?", ("External body.", CAMPAIGN, "items/prepared-item"))

        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            if timing == "before-capture":
                external_write()
            first = prepared.list_page_records(CAMPAIGN, include_body=True)
            if timing == "after-capture":
                external_write()
            second = prepared.list_page_records(CAMPAIGN, include_body=True)
            assert first == second
            expected = "External body." if timing == "before-capture" else "Original body."
            assert next(row.page.body_markdown for row in second if row.page_ref == "items/prepared-item") == expected
    with app.test_request_context("/"):
        with service.combat_detail_read(CAMPAIGN, pages) as prepared:
            current = prepared.list_page_records(CAMPAIGN, include_body=True)
            assert next(row.page.body_markdown for row in current if row.page_ref == "items/prepared-item") == "External body."
