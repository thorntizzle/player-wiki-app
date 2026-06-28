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


def _write_cutover_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_memberships (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE character_state (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_sessions (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_combat_trackers (id TEXT NOT NULL)")
        connection.execute("CREATE TABLE campaign_pages (id TEXT NOT NULL)")
        connection.execute("INSERT INTO users (id) VALUES ('operator')")
        connection.execute("INSERT INTO campaign_memberships (id) VALUES ('dm')")
        connection.execute("INSERT INTO character_state (id) VALUES ('arden')")
        connection.execute("INSERT INTO campaign_pages (id) VALUES ('home')")
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
    assert "Create a backup from the copied SQLite and copied campaigns directory only." in transcript
    assert "Restored linked character_state JSON and revision values must match baseline." in transcript
    assert "Label before: `copied-data rollback ready`" in transcript
    assert "Label after only if backup, mutation, restore, and equivalence all pass: `staging snapshot ready`" in transcript


def test_all_copied_data_families_have_staging_snapshot_guides():
    harness = _load_harness_module()

    for family in (
        "content-character",
        "combat",
        "session",
        "systems",
        "dm-content",
        "publishing",
    ):
        guide = harness.family_guide_markdown(family)

        assert "## Family-Specific Rehearsal Guide" in guide
        assert "### Backup Evidence Checklist" in guide
        assert "### Mutation Sequence" in guide
        assert "### Restore Equivalence Requirements" in guide
        assert "Label before: `copied-data rollback ready`" in guide
        assert "Label after only if backup, mutation, restore, and equivalence all pass: `staging snapshot ready`" in guide
        assert "staging-equivalent snapshot" in guide


def test_staging_snapshot_guides_use_current_api_contract_routes():
    harness = _load_harness_module()

    session_guide = harness.family_guide_markdown("session")
    assert "PUT /api/v1/campaigns/<slug>/session/articles/<articleId>" in session_guide
    assert "PATCH /api/v1/campaigns/<slug>/session/articles/<articleId>" not in session_guide

    systems_guide = harness.family_guide_markdown("systems")
    assert "PUT /api/v1/campaigns/<slug>/systems/sources" in systems_guide
    assert "PUT /api/v1/campaigns/<slug>/systems/overrides/<entryKey>" in systems_guide
    assert "PUT /api/v1/campaigns/<slug>/systems/custom-entries/<entrySlug>" in systems_guide
    assert "POST /api/v1/campaigns/<slug>/systems/item-mechanics/import" in systems_guide
    assert "/systems/source-policy" not in systems_guide
    assert "/systems/import-item-mechanics" not in systems_guide

    dm_content_guide = harness.family_guide_markdown("dm-content")
    assert "PUT /api/v1/campaigns/<slug>/dm-content/statblocks/<statblockId>" in dm_content_guide
    assert "PUT /api/v1/campaigns/<slug>/dm-content/conditions/<conditionDefinitionId>" in dm_content_guide
    assert "PATCH /api/v1/campaigns/<slug>/dm-content/statblocks/<statblockId>" not in dm_content_guide
    assert "/dm-content/conditions/<conditionId>" not in dm_content_guide

    publishing_guide = harness.family_guide_markdown("publishing")
    assert "PUT /api/v1/campaigns/<slug>/content/pages/<pageRef>" in publishing_guide
    assert "PUT /api/v1/campaigns/<slug>/content/assets/<assetRef>" in publishing_guide
    assert "POST /api/v1/campaigns/<slug>/content/pages" not in publishing_guide
    assert "POST /api/v1/campaigns/<slug>/content/assets" not in publishing_guide


def test_rollback_cutover_transcript_captures_runbook_evidence(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "rollback-cutover"

    result = harness.init_rehearsal(
        rehearsal_id="rollback-cutover",
        family="rollback-cutover",
        root=root,
        source_description="copied staging-equivalent snapshot",
        source_approval="test approval",
        dry_run=True,
    )

    transcript = result["transcript_preview"]
    assert "Write family: rollback-cutover" in transcript
    assert "Record the last known-good Flask commit SHA, image tag/id if available, branch, and build source." in transcript
    assert "Record pre-cutover SQLite backup command, archive path, contents summary, and checksum." in transcript
    assert "Record pre-cutover campaign-content backup command, archive path, contents summary, and checksum." in transcript
    assert "Classify each TypeScript data delta as revert, preserve, merge manually, or block rollback until operator decision." in transcript
    assert "Rollback command shape must name the Flask commit/image target and restore archive inputs, using placeholders for private app identity." in transcript
    assert "Post-rollback Flask health smoke must pass before the transcript can pass." in transcript
    assert "Label after only if backup, mutation, restore, and equivalence all pass: `cutover rehearsal passed`" in transcript
    assert "This rehearsal result is not production cutover approval" in transcript


def test_staging_snapshot_preflight_is_sanitized_and_non_approving():
    harness = _load_harness_module()

    markdown = harness.staging_snapshot_preflight_markdown()

    assert markdown.startswith("# Staging Snapshot Preflight Checklist")
    assert "`docs/typescript-backend-rewrite/cutover-readiness.md`" in markdown
    assert "`docs/typescript-backend-rewrite/staging-rehearsal-harness.md`" in markdown
    assert "No Fly command, deploy, live API write, live SQLite sync, or production volume access" in markdown
    assert "Result: blocked until an approved staging-snapshot rehearsal transcript passes." in markdown
    assert "Label after: unchanged by this preflight." in markdown
    assert "### content-character" in markdown
    assert "### rollback-cutover" in markdown
    assert "`character_state`" in markdown
    assert "<repo-root>/.task-temp/<staging-snapshot-id>/input/player_wiki.sqlite3" in markdown
    assert "C:" not in markdown


def test_staging_snapshot_preflight_can_focus_one_family():
    harness = _load_harness_module()

    markdown = harness.staging_snapshot_preflight_markdown(family="combat")

    assert "Scope: combat" in markdown
    assert "### combat" in markdown
    assert "`campaign_combat_trackers`" in markdown
    assert "### session" not in markdown
    assert "### rollback-cutover" not in markdown


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


def test_rollback_cutover_snapshot_captures_cross_domain_tables(tmp_path):
    harness = _load_harness_module()
    root = tmp_path / ".task-temp" / "rollback-cutover"
    campaigns_dir = root / "input" / "campaigns"
    db_path = root / "input" / "player_wiki.sqlite3"
    (campaigns_dir / "linden-pass" / "content").mkdir(parents=True)
    (campaigns_dir / "linden-pass" / "content" / "index.md").write_text(
        "# Cutover Smoke\n",
        encoding="utf-8",
    )
    _write_cutover_database(db_path)

    manifest = harness.capture_snapshot(
        root=root,
        label="pre",
        family="rollback-cutover",
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )["manifest"]

    assert manifest["sqlite"]["tables"]["users"] == 1
    assert manifest["sqlite"]["tables"]["campaign_memberships"] == 1
    assert manifest["sqlite"]["tables"]["character_state"] == 1
    assert manifest["sqlite"]["tables"]["campaign_pages"] == 1
    assert "campaign_combat_trackers" in manifest["sqlite"]["tables"]
    assert "campaign_session_messages" in manifest["sqlite"]["missing_tables"]
