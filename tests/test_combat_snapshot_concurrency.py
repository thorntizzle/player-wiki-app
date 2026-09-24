from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import pytest
import yaml

from player_wiki.character_models import CharacterDefinition
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from tests.helpers.character_state_helpers import (
    _write_character_definition,
    _write_character_state,
)
from tests.test_character_reconciliation import _coordinator, _deletion_coordinator, _update_payload

CAMPAIGN = "linden-pass"
PC = "arden-march"


def _seed(app, *slugs):
    service = app.extensions["campaign_combat_service"]
    with app.app_context():
        rows = [
            service.add_player_character(CAMPAIGN, character_slug=slug, turn_value=18 - index)
            for index, slug in enumerate(slugs or (PC,))
        ]
    return service, rows


def _change_hp(app, slug=PC, value=17):
    _write_character_state(
        app, slug, lambda state: state["vitals"].update(current_hp=value, temp_hp=6)
    )


def _parallel(app, action):
    caller_connection = get_db()

    def execute():
        with app.app_context():
            assert get_db() is not caller_connection
            return action()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(execute).result(timeout=10)


def _after_source_read(monkeypatch, service, app, action, *, slug=PC, times=1):
    calls = []

    # The behavior is independent of the loader choice; H3 uses the exact,
    # non-initializing loader while the red characterization uses the old one.
    for method_name in ("get_visible_character", "get_combat_seed_character"):
        original = getattr(service.character_repository, method_name)

        def load(campaign, character, _original=original):
            record = _original(campaign, character)
            if character == slug and len(calls) < times:
                calls.append(character)
                _parallel(app, action)
            return record

        monkeypatch.setattr(service.character_repository, method_name, load)
    return calls


def _resources(service, row_id, *, movement=None, action=False, reaction=False):
    current = service.get_combatant(CAMPAIGN, row_id)
    return service.update_resources(
        CAMPAIGN,
        row_id,
        expected_revision=current.revision,
        has_action=action,
        has_bonus_action=False,
        has_reaction=reaction,
        movement_remaining=current.movement_remaining if movement is None else movement,
    )


def test_snapshot_recomputes_after_concurrent_movement_spend(app, monkeypatch):
    service, (row,) = _seed(app)
    assert row.movement_remaining == 30
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch, service, app, lambda: _resources(service, row.id, movement=0)
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        current = service.get_combatant(CAMPAIGN, row.id)
        assert calls == [PC]
        assert result.sync_changed is True
        assert current.movement_remaining == 0
        assert current.current_hp == 17
        assert current.temp_hp == 6
        assert not current.has_action and not current.has_bonus_action and not current.has_reaction
        assert current.revision == row.revision + 2
        assert service.get_tracker(CAMPAIGN).revision == before + 2


def test_snapshot_recomputes_from_newer_character_state(app, monkeypatch):
    service, (row,) = _seed(app)
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch, service, app, lambda: _change_hp(app, value=9)
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert calls == [PC]
        assert result.sync_changed
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == 9
        assert service.get_tracker(CAMPAIGN).revision == before + 1


def test_snapshot_recomputes_from_newer_definition(app, monkeypatch):
    service, (row,) = _seed(app)
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch,
        service,
        app,
        lambda: _write_character_definition(
            app, PC, lambda definition: definition.update(name="Current source name")
        ),
    )
    with app.app_context():
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert calls == [PC]
        assert result.sync_changed
        assert service.get_combatant(CAMPAIGN, row.id).display_name == "Current source name"


def test_deleted_combatant_is_not_resurrected_or_reported_as_sync_error(app, monkeypatch):
    service, (row,) = _seed(app)
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch, service, app, lambda: service.delete_combatant(CAMPAIGN, row.id)
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert calls == [PC]
        assert result.sync_changed is False
        assert service.get_combatant(CAMPAIGN, row.id) is None
        assert service.get_tracker(CAMPAIGN).revision == before + 1


def test_two_collisions_defer_without_cache_poisoning_then_next_call_converges(app, monkeypatch):
    service, (row,) = _seed(app)
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch,
        service,
        app,
        lambda: _resources(service, row.id),
        times=2,
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        current = service.get_combatant(CAMPAIGN, row.id)
        assert len(calls) == 2
        assert result.status == "deferred_conflict"
        assert result.sync_changed is False
        assert current.current_hp == row.current_hp
        assert current.revision == row.revision + 2
        assert service.get_tracker(CAMPAIGN).revision == before + 2
        assert CAMPAIGN not in service._player_snapshot_sync_source_tokens
        resumed = service.sync_player_character_snapshots(CAMPAIGN)
        assert resumed.sync_changed
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == 17
        assert service.get_tracker(CAMPAIGN).revision == before + 3


def test_late_row_conflict_rolls_back_entire_snapshot_batch(app, monkeypatch):
    service, rows = _seed(app, PC, "selene-brook")
    for row in rows:
        _change_hp(app, row.character_slug)
    calls = _after_source_read(
        monkeypatch,
        service,
        app,
        lambda: _resources(service, rows[1].id),
        slug="selene-brook",
        times=2,
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert len(calls) == 2
        assert result.status == "deferred_conflict"
        first = service.get_combatant(CAMPAIGN, rows[0].id)
        second = service.get_combatant(CAMPAIGN, rows[1].id)
        assert first.revision == rows[0].revision
        assert first.current_hp == rows[0].current_hp
        assert second.revision == rows[1].revision + 2
        assert second.current_hp == rows[1].current_hp
        assert service.get_tracker(CAMPAIGN).revision == before + 2


def test_missing_state_defers_without_initialization_or_tracker_write(app, monkeypatch):
    service, (row,) = _seed(app)
    with app.app_context():
        app.extensions["character_state_store"].delete_state(CAMPAIGN, PC)
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert result.status == "deferred_conflict"
        assert result.sync_changed is False
        assert metrics["write_count"] == metrics["commit_count"] == 0
        assert app.extensions["character_state_store"].get_state(CAMPAIGN, PC) is None
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == row.current_hp
        assert service.get_tracker(CAMPAIGN).revision == before


def test_unprovable_source_defers_and_keeps_snapshot_and_cache_truth(app, monkeypatch):
    service, (row,) = _seed(app)
    with app.app_context():
        service.sync_player_character_snapshots(CAMPAIGN)
        assert CAMPAIGN in service._player_snapshot_sync_source_tokens
    _change_hp(app)
    monkeypatch.setattr(service.character_repository, "get_snapshot_source_file_token", lambda *a, **k: None)
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert result.status == "deferred_conflict"
        assert result.sync_changed is False
        assert metrics["write_count"] == metrics["commit_count"] == 0
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == row.current_hp
        assert service.get_tracker(CAMPAIGN).revision == before
        assert CAMPAIGN not in service._player_snapshot_sync_source_tokens


def test_changed_and_unchanged_snapshot_work_stays_bounded(app):
    service, (row,) = _seed(app)
    _change_hp(app)
    with app.app_context():
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        changed = get_db_query_metrics()
        assert result.sync_changed
        assert changed["query_count"] <= 13
        assert changed["write_count"] == 2
        assert changed["commit_count"] == 1
        assert changed["rollback_count"] == 0
        service.sync_player_character_snapshots(CAMPAIGN)
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        unchanged = get_db_query_metrics()
        assert result.status == "skipped_unchanged_source_token"
        assert unchanged["query_count"] == 1
        assert unchanged["write_count"] == unchanged["commit_count"] == unchanged["rollback_count"] == 0


def test_snapshot_preserves_a_concurrent_turn_resource_reset(app, monkeypatch):
    service, (row,) = _seed(app)
    with app.app_context():
        _resources(service, row.id, movement=0)
    _change_hp(app)
    calls = _after_source_read(
        monkeypatch, service, app, lambda: service.advance_turn(CAMPAIGN)
    )
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        current = service.get_combatant(CAMPAIGN, row.id)
        assert calls == [PC]
        assert result.sync_changed
        assert current.current_hp == 17
        assert current.movement_remaining == 30
        assert current.has_action and current.has_bonus_action and current.has_reaction
        tracker = service.get_tracker(CAMPAIGN)
        assert tracker.current_combatant_id == row.id
        assert tracker.revision == before + 2


@pytest.mark.parametrize("kind", ("publication", "deletion"))
@pytest.mark.parametrize("status", ("prepared", "repository_pending", "conflict"))
def test_new_source_protection_defers_without_changing_journal_or_snapshot(
    app, monkeypatch, kind, status
):
    service, (row,) = _seed(app)
    _change_hp(app)

    def protect():
        def hold(event, operation_id):
            if event == "after_commit":
                raise RuntimeError("hold synthetic journal")

        with pytest.raises(RuntimeError, match="hold synthetic journal"):
            if kind == "publication":
                prior = service.character_repository.get_combat_seed_character(CAMPAIGN, PC)
                definition, metadata, _ = _update_payload(prior)
                _coordinator(app, hold).update(
                    prior, definition, metadata, deepcopy(prior.state_record.state),
                    expected_revision=prior.state_record.revision,
                    operation_kind="markdown_import",
                )
            else:
                _deletion_coordinator(app, hold).delete(CAMPAIGN, PC, operation_kind="content_api")
        table = "character_reconciliation_operations" if kind == "publication" else "character_deletion_operations"
        get_db().execute(f"UPDATE {table} SET state = ? WHERE character_slug = ?", (status, PC))
        get_db().commit()

    calls = _after_source_read(monkeypatch, service, app, protect)
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert calls == [PC]
        assert result.status == "deferred_conflict"
        assert not result.sync_changed
        current = service.get_combatant(CAMPAIGN, row.id)
        assert current.current_hp == row.current_hp
        assert current.revision == row.revision
        assert service.get_tracker(CAMPAIGN).revision == before
        table = "character_reconciliation_operations" if kind == "publication" else "character_deletion_operations"
        assert get_db().execute(f"SELECT state FROM {table} WHERE character_slug = ?", (PC,)).fetchone()[0] == status
        if kind == "deletion":
            assert app.extensions["character_state_store"].get_state(CAMPAIGN, PC) is None


@pytest.mark.parametrize("source", ("import", "config"))
def test_source_metadata_drift_gets_one_current_recompute(app, monkeypatch, source):
    service, (row,) = _seed(app)
    _change_hp(app)
    reads = []
    original = service._build_player_character_snapshot

    def build(record):
        reads.append(record.definition.character_slug)
        return original(record)

    monkeypatch.setattr(service, "_build_player_character_snapshot", build)

    def change_source():
        path = app.config["TEST_CAMPAIGNS_DIR"] / CAMPAIGN
        path = path / "campaign.yaml" if source == "config" else path / "characters" / PC / "import.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload["synthetic_h3_drift"] = "changed"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    _after_source_read(monkeypatch, service, app, change_source)
    with app.app_context():
        result = service.sync_player_character_snapshots(CAMPAIGN)
        assert result.sync_changed
        assert reads == [PC, PC]
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == 17


@pytest.mark.parametrize("stage", ("first_row", "last_row", "tracker", "commit"))
def test_snapshot_precommit_fault_rolls_back_every_row(app, monkeypatch, stage):
    service, rows = _seed(app, PC, "selene-brook")
    for row in rows:
        _change_hp(app, row.character_slug)
    with app.app_context():
        connection = get_db()
        before_rows = [tuple(row) for row in connection.execute("SELECT * FROM campaign_combatants ORDER BY id").fetchall()]
        before_tracker = tuple(connection.execute("SELECT * FROM campaign_combat_trackers").fetchone())
        original_update = service.store.update_combatant
        original_bump = service.store.bump_tracker_revision

        def update(*args, **kwargs):
            result = original_update(*args, **kwargs)
            if stage == "first_row" or (stage == "last_row" and args[1] == rows[-1].id):
                raise RuntimeError("snapshot fault")
            return result

        def bump(*args, **kwargs):
            result = original_bump(*args, **kwargs)
            if stage == "tracker":
                raise RuntimeError("snapshot fault")
            return result

        monkeypatch.setattr(service.store, "update_combatant", update)
        monkeypatch.setattr(service.store, "bump_tracker_revision", bump)
        if stage == "commit":
            monkeypatch.setattr(connection, "commit", lambda: (_ for _ in ()).throw(RuntimeError("snapshot fault")))
        with pytest.raises(RuntimeError, match="snapshot fault"):
            service.sync_player_character_snapshots(CAMPAIGN)
        assert not connection.in_transaction
        assert [tuple(row) for row in connection.execute("SELECT * FROM campaign_combatants ORDER BY id").fetchall()] == before_rows
        assert tuple(connection.execute("SELECT * FROM campaign_combat_trackers").fetchone()) == before_tracker


def test_sync_does_not_commit_or_rollback_a_callers_transaction(app):
    service, (row,) = _seed(app)
    _change_hp(app)
    with app.app_context():
        connection = get_db()
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE campaign_combatants SET has_action = 0 WHERE id = ?", (row.id,))
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert result.status == "deferred_conflict"
        assert connection.in_transaction
        assert metrics["write_count"] == metrics["commit_count"] == metrics["rollback_count"] == 0
        connection.rollback()
        assert service.get_combatant(CAMPAIGN, row.id).has_action


@pytest.mark.parametrize("count", (1, 6, 50))
def test_snapshot_batch_cost_scales_without_extra_per_row_rechecks(app, monkeypatch, record_property, count):
    source_dir = app.config["TEST_CAMPAIGNS_DIR"] / CAMPAIGN / "characters" / PC
    definition_payload = yaml.safe_load((source_dir / "definition.yaml").read_text(encoding="utf-8"))
    metadata = yaml.safe_load((source_dir / "import.yaml").read_text(encoding="utf-8"))
    slugs = []
    for index in range(count):
        slug = f"h3-cost-{index:02d}"
        directory = source_dir.parent / slug
        directory.mkdir()
        definition = deepcopy(definition_payload)
        definition.update(character_slug=slug, name=f"H3 Cost {index}")
        imported = dict(metadata, character_slug=slug)
        (directory / "definition.yaml").write_text(yaml.safe_dump(definition), encoding="utf-8")
        (directory / "import.yaml").write_text(yaml.safe_dump(imported), encoding="utf-8")
        with app.app_context():
            original = app.extensions["character_repository"].get_character(CAMPAIGN, PC)
            app.extensions["character_state_store"].initialize_state_if_missing(
                CharacterDefinition.from_dict(definition), deepcopy(original.state_record.state)
            )
        slugs.append(slug)
    service, rows = _seed(app, *slugs)
    for slug in slugs:
        _change_hp(app, slug)
    builds = []
    original_build = service._build_player_character_snapshot

    def build(record):
        builds.append(record.definition.character_slug)
        return original_build(record)

    monkeypatch.setattr(service, "_build_player_character_snapshot", build)
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        record_property("pc_count", count)
        for name in ("query_count", "write_count", "commit_count", "rollback_count"):
            record_property(name, metrics[name])
        assert result.sync_changed
        assert len(builds) == count
        assert metrics["query_count"] <= 4 * count + 9
        assert metrics["write_count"] == count + 1
        assert metrics["commit_count"] == 1
        assert metrics["rollback_count"] == 0
        assert service.get_tracker(CAMPAIGN).revision == before + 1
        assert all(service.get_combatant(CAMPAIGN, row.id).current_hp == 17 for row in rows)


@pytest.mark.parametrize("kind", ("publication", "deletion"))
def test_retained_unavailable_snapshot_does_not_block_healthy_peer(app, kind):
    service, (retained, healthy) = _seed(app, PC, "selene-brook")

    def protect():
        def hold(event, operation_id):
            if event == "after_commit":
                raise RuntimeError("hold retained source")

        with pytest.raises(RuntimeError, match="hold retained source"):
            if kind == "publication":
                prior = service.character_repository.get_combat_seed_character(CAMPAIGN, PC)
                definition, metadata, _ = _update_payload(prior)
                _coordinator(app, hold).update(
                    prior, definition, metadata, deepcopy(prior.state_record.state),
                    expected_revision=prior.state_record.revision,
                    operation_kind="markdown_import",
                )
            else:
                _deletion_coordinator(app, hold).delete(CAMPAIGN, PC, operation_kind="content_api")

    with app.app_context():
        _parallel(app, protect)
    _change_hp(app, "selene-brook")
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert result.sync_changed
        assert metrics["query_count"] <= 13
        assert metrics["write_count"] == 2
        assert metrics["commit_count"] == 1
        assert service.get_combatant(CAMPAIGN, retained.id).revision == retained.revision
        assert service.get_combatant(CAMPAIGN, retained.id).current_hp == retained.current_hp
        assert service.get_combatant(CAMPAIGN, healthy.id).current_hp == 17
        assert service.get_tracker(CAMPAIGN).revision == before + 1
        assert CAMPAIGN not in service._player_snapshot_sync_source_tokens
        if kind == "deletion":
            assert app.extensions["character_state_store"].get_state(CAMPAIGN, PC) is None


@pytest.mark.parametrize("filename", ("definition.yaml", "import.yaml"))
def test_malformed_source_defers_without_snapshot_or_state_writes(app, filename):
    service, (row,) = _seed(app)
    _change_hp(app)
    source = app.config["TEST_CAMPAIGNS_DIR"] / CAMPAIGN / "characters" / PC / filename
    source.write_text("invalid: [unterminated", encoding="utf-8")
    with app.app_context():
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert result.status == "deferred_conflict"
        assert metrics["write_count"] == metrics["commit_count"] == 0
        assert service.get_combatant(CAMPAIGN, row.id).current_hp == row.current_hp
        assert service.get_tracker(CAMPAIGN).revision == before


def test_unchanged_snapshot_after_tactical_write_does_not_add_revision(app):
    service, (row,) = _seed(app)
    with app.app_context():
        service.sync_player_character_snapshots(CAMPAIGN)
        current = _resources(service, row.id, movement=0)
        before = service.get_tracker(CAMPAIGN).revision
        reset_db_query_metrics()
        result = service.sync_player_character_snapshots(CAMPAIGN)
        metrics = get_db_query_metrics()
        assert not result.sync_changed
        assert metrics["write_count"] == metrics["commit_count"] == 0
        saved = service.get_combatant(CAMPAIGN, row.id)
        assert saved.movement_remaining == 0
        assert not saved.has_action and not saved.has_bonus_action and not saved.has_reaction
        assert saved.revision == current.revision
        assert service.get_tracker(CAMPAIGN).revision == before

