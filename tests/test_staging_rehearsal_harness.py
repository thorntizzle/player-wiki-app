from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


def _load_harness_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "staging_rehearsal_harness.py"
    spec = importlib.util.spec_from_file_location("staging_rehearsal_harness", module_path)
    assert spec and spec.loader is not None, f"Unable to load {module_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE character_state (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE character_assignments (id TEXT NOT NULL)")
        connection.execute("INSERT INTO character_state (id) VALUES ('arden')")
        connection.commit()


def _write_combat_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE campaign_combat_trackers (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_combatants (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_combat_conditions (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_combatant_resource_counters (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_combatant_resource_notes (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE character_state (id TEXT NOT NULL)")
        connection.execute("INSERT INTO campaign_combat_trackers (id) VALUES ('linden-pass')")
        connection.execute("INSERT INTO campaign_combatants (id) VALUES ('arden')")
        connection.execute("INSERT INTO character_state (id) VALUES ('arden')")
        connection.commit()


def test_init_rehearsal_creates_guarded_folder_and_transcript(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "content-character-rehearsal"

    result = harness.init_rehearsal(
        rehearsal_id="content-character-rehearsal",
        family="content-character",
        root=root,
        source_description="copied fixture snapshot",
        source_approval="test approval",
    )

    assert result["created"] is True
    for name in harness.REHEARSAL_DIRS:
        assert (root / name).is_dir()
    transcript = (root / "transcript.md").read_text(encoding="utf-8")
    assert "Write family: content-character" in transcript
    assert "`character_state`" in transcript


def test_combat_rehearsal_transcript_includes_concrete_write_family_plan(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "combat-rehearsal"

    result = harness.init_rehearsal(
        rehearsal_id="combat-rehearsal",
        family="combat",
        root=root,
        source_description="copied combat snapshot",
        source_approval="test approval",
    )

    assert result["created"] is True
    transcript = (root / "transcript.md").read_text(encoding="utf-8")
    assert "POST /api/v1/campaigns/<slug>/combat/player-combatants" in transcript
    assert "PATCH /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/vitals" in transcript
    assert "Restored linked character_state JSON and revision values must match baseline." in transcript
    assert "Label before: `fixture-write validated`" in transcript
    assert "Label after only if backup, mutation, restore, and equivalence all pass: `copied-data rollback ready`" in transcript


def test_path_guard_rejects_targets_outside_rehearsal_root(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "rehearsal"
    (root / "input" / "campaigns").mkdir(parents=True)

    with pytest.raises(ValueError, match="database path must resolve inside"):
        harness.validate_rehearsal_paths(
            root=root,
            db_path=tmp_path / "outside.sqlite3",
            campaigns_dir=root / "input" / "campaigns",
        )


def test_snapshot_compare_detects_restore_equivalence_and_drift(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "rehearsal"
    campaigns_dir = root / "input" / "campaigns"
    db_path = root / "input" / "player_wiki.sqlite3"
    (campaigns_dir / "linden-pass" / "content").mkdir(parents=True)
    (campaigns_dir / "linden-pass" / "content" / "index.md").write_text(
        "# Linden Pass\n",
        encoding="utf-8",
    )
    _write_database(db_path)

    pre = harness.capture_snapshot(
        root=root,
        label="pre",
        family="content-character",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]
    restore = harness.capture_snapshot(
        root=root,
        label="restore",
        family="content-character",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]

    assert harness.compare_manifests(pre, restore)["equal"] is True

    (campaigns_dir / "linden-pass" / "content" / "index.md").write_text(
        "# Changed\n",
        encoding="utf-8",
    )
    post = harness.capture_snapshot(
        root=root,
        label="post",
        family="content-character",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]

    comparison = harness.compare_manifests(pre, post)
    assert comparison["equal"] is False
    assert comparison["changed_files"] == ["linden-pass/content/index.md"]


def test_combat_snapshot_captures_family_tables_and_restore_drift(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "combat-rehearsal"
    campaigns_dir = root / "input" / "campaigns"
    db_path = root / "input" / "player_wiki.sqlite3"
    (campaigns_dir / "linden-pass" / "content").mkdir(parents=True)
    (campaigns_dir / "linden-pass" / "content" / "encounter.md").write_text(
        "# Encounter Notes\n",
        encoding="utf-8",
    )
    _write_combat_database(db_path)

    pre = harness.capture_snapshot(
        root=root,
        label="pre",
        family="combat",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]
    assert pre["sqlite"]["tables"]["campaign_combat_trackers"] == 1
    assert pre["sqlite"]["tables"]["campaign_combatants"] == 1
    assert pre["sqlite"]["tables"]["character_state"] == 1
    assert pre["sqlite"]["missing_tables"] == []

    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO campaign_combat_conditions (id) VALUES ('prone')")
        connection.commit()

    post = harness.capture_snapshot(
        root=root,
        label="post",
        family="combat",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]

    comparison = harness.compare_manifests(pre, post)
    assert comparison["equal"] is False
    assert comparison["changed_files"] == []
    assert comparison["sqlite_equal"] is False
    assert comparison["after_sqlite"]["tables"]["campaign_combat_conditions"] == 1
