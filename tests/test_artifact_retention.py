from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from player_wiki import artifact_retention
from player_wiki.artifact_retention import ArtifactRoot, build_artifact_report


AS_OF = 2_000_000_000.0
DAY = 24 * 60 * 60


class _StatOverride:
    def __init__(self, base, **overrides):
        self._base = base
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._base, name)


def _write_aged(path: Path, *, age_days: float, payload: bytes = b"sample") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    modified = AS_OF - age_days * DAY
    os.utime(path, (modified, modified))


def _fingerprint(root: Path) -> tuple[tuple[object, ...], ...]:
    rows = []
    for path in sorted((root, *root.rglob("*")), key=lambda value: str(value)):
        value = path.lstat()
        rows.append(
            (
                str(path.relative_to(root)) if path != root else ".",
                value.st_mode,
                value.st_size,
                value.st_mtime_ns,
                path.read_bytes() if path.is_file() and not path.is_symlink() else None,
            )
        )
    return tuple(rows)


def _alert(report: dict[str, object], class_id: str) -> dict[str, object]:
    return next(
        row for row in report["advisory_alerts"] if row["class_id"] == class_id
    )


def test_inventory_classifies_aggregate_counts_and_approved_age_buckets(tmp_path):
    data = tmp_path / "opaque-data-root"
    archives = tmp_path / "opaque-archive-root"
    scratch = tmp_path / "opaque-scratch-root"
    for root in (data, archives, scratch):
        root.mkdir()

    _write_aged(data / ".state.snapshot.tmp-one", age_days=1)
    _write_aged(data / "pre-migration-v0001-to-v0002.sqlite3", age_days=180)
    _write_aged(data / "state-presync.sqlite3", age_days=90)
    _write_aged(archives / "player-wiki-backup-one.zip", age_days=30)
    _write_aged(archives / "pre-restore-one.zip", age_days=90)
    _write_aged(scratch / "arbitrary.bin", age_days=7)
    _write_aged(scratch / "future.bin", age_days=-1)
    _write_aged(data / "unclassified.bin", age_days=0.5)

    report = build_artifact_report(
        (
            ArtifactRoot("data", data),
            ArtifactRoot("archive", archives),
            ArtifactRoot("scratch", scratch),
        ),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["age_buckets"] == ["<24h", "1-7d", "8-30d", "31-90d", ">90d"]
    assert report["totals"]["count"] == 8
    assert report["classes"]["incomplete_stages"]["count"] == 1
    assert report["classes"]["local_scratch"]["count"] == 2
    assert report["classes"]["ordinary_verified_archives"]["count"] == 0
    assert report["classes"]["unverified_archive_candidates"]["count"] == 2
    assert report["classes"]["pre_restore_pre_sync_evidence"]["count"] == 0
    assert report["classes"]["migration_snapshots"]["count"] == 1
    assert report["classes"]["live_preimport_presync_copies"]["count"] == 1
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["classes"]["local_scratch"]["age_buckets"]["1-7d"]["count"] == 1
    assert report["classes"]["local_scratch"]["future_timestamp_count"] == 1
    assert "future_timestamp" in report["blocker_flags"]
    assert report["complete"] is False


def test_retention_thresholds_are_exact_advisory_and_never_actionable(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    _write_aged(root / "old.bin", age_days=7)

    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    expected = {
        "incomplete_stages": (DAY, 0, None),
        "local_scratch": (7 * DAY, 10, 2 * 1024**3),
        "ordinary_verified_archives": (30 * DAY, 14, 32 * 1024**3),
        "pre_restore_pre_sync_evidence": (90 * DAY, 10, 32 * 1024**3),
        "migration_snapshots": (180 * DAY, 5, 12 * 1024**3),
        "live_preimport_presync_copies": (90 * DAY, 3, 12 * 1024**3),
    }
    for class_id, values in expected.items():
        row = _alert(report, class_id)
        assert row["advisory"] is True
        assert row["actionable"] is False
        assert row["threshold"]["minimum_age_seconds"] == values[0]
        assert row["threshold"]["retain_newest_count"] == values[1]
        assert row["threshold"]["apparent_bytes"] == values[2]
    assert _alert(report, "local_scratch")["triggered_by"] == ["age"]


def test_report_is_deterministic_path_redacted_and_zero_write(tmp_path):
    secret_root = tmp_path / "private-campaign-root"
    secret_name = "secret-slug-deadbeef.sqlite3"
    _write_aged(secret_root / secret_name, age_days=8, payload=b"private-content")
    before = _fingerprint(secret_root)

    first = build_artifact_report(
        (ArtifactRoot("scratch", secret_root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )
    second = build_artifact_report(
        (ArtifactRoot("scratch", secret_root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert first == second
    assert _fingerprint(secret_root) == before
    rendered = json.dumps(first, sort_keys=True)
    for private_value in (
        str(secret_root),
        secret_root.name,
        secret_name,
        "secret-slug",
        "deadbeef",
        "private-content",
    ):
        assert private_value not in rendered


def test_restore_journal_and_orphan_bundle_block_without_content_reads(
    tmp_path, monkeypatch
):
    root = tmp_path / "data"
    journal = root / "state.restore-journal.json"
    bundle = root / ".state.restore-token.old"
    nested = bundle / "must-not-be-scanned.txt"
    _write_aged(journal, age_days=2, payload=b"private-journal")
    _write_aged(nested, age_days=2, payload=b"private-bundle")

    def fail_read(*args, **kwargs):
        raise AssertionError("inventory must not read artifact content")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    monkeypatch.setattr(Path, "read_text", fail_read)
    report = build_artifact_report(
        (ArtifactRoot("data", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert set(report["blocker_flags"]) == {
        "protected_or_ambiguous_present",
        "restore_bundle_present",
        "restore_recovery_pending",
    }
    assert report["complete"] is False
    assert report["classes"]["incomplete_stages"]["count"] == 1
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])


def test_symlink_is_protected_and_target_is_not_followed(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    _write_aged(outside / "target.bin", age_days=4, payload=b"outside")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {exc.__class__.__name__}")

    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["totals"]["count"] == 1
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["classes"]["protected_unknown"]["protected_count"] == 1
    assert report["blocker_flags"] == [
        "protected_or_ambiguous_present",
        "special_or_ambiguous_entry",
    ]


def test_reparse_like_directory_is_protected_and_not_descended(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "junction-like"
    _write_aged(nested / "must-not-be-counted.bin", age_days=4)
    nested_inode = nested.lstat().st_ino
    original = artifact_retention._is_reparse

    monkeypatch.setattr(
        artifact_retention,
        "_is_reparse",
        lambda value: value.st_ino == nested_inode or original(value),
    )
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["totals"]["count"] == 1
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["blocker_flags"] == [
        "protected_or_ambiguous_present",
        "special_or_ambiguous_entry",
    ]


def test_explicit_root_rejects_symlinked_ancestor(tmp_path):
    real = tmp_path / "real"
    root = real / "root"
    root.mkdir(parents=True)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {exc.__class__.__name__}")

    report = build_artifact_report(
        (ArtifactRoot("scratch", alias / "root"),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["blocker_flags"] == ["unsafe_root_alias"]
    assert report["totals"]["count"] == 0
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])


def test_explicit_root_rejects_reparse_like_ancestor(tmp_path, monkeypatch):
    ancestor = tmp_path / "ancestor"
    root = ancestor / "root"
    root.mkdir(parents=True)
    ancestor_inode = ancestor.lstat().st_ino
    original = artifact_retention._is_reparse
    monkeypatch.setattr(
        artifact_retention,
        "_is_reparse",
        lambda value: value.st_ino == ancestor_inode or original(value),
    )

    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["blocker_flags"] == ["unsafe_root_alias"]
    assert report["totals"]["count"] == 0


def test_cross_device_directory_is_protected_and_not_descended(tmp_path, monkeypatch):
    root = tmp_path / "root"
    mounted = root / "mounted"
    _write_aged(mounted / "must-not-be-counted.bin", age_days=4)
    original = Path.lstat

    def cross_device_lstat(path):
        value = original(path)
        if Path(path) == mounted:
            return _StatOverride(value, st_dev=value.st_dev + 1)
        return value

    monkeypatch.setattr(Path, "lstat", cross_device_lstat)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["classes"]["local_scratch"]["count"] == 0
    assert report["blocker_flags"] == [
        "cross_device_entry",
        "protected_or_ambiguous_present",
    ]
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])


@pytest.mark.parametrize("replacement_mode", [stat.S_IFLNK | 0o777, stat.S_IFREG | 0o600])
def test_entry_type_replacement_before_recursion_is_never_followed(
    tmp_path, monkeypatch, replacement_mode
):
    root = tmp_path / "root"
    nested = root / "nested"
    _write_aged(nested / "must-not-be-counted.bin", age_days=4)
    original = Path.lstat
    calls = 0

    def replaced_lstat(path):
        nonlocal calls
        value = original(path)
        if Path(path) == nested:
            calls += 1
            if calls == 2:
                return _StatOverride(value, st_mode=replacement_mode)
        return value

    monkeypatch.setattr(Path, "lstat", replaced_lstat)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["classes"]["local_scratch"]["count"] == 0
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["blocker_flags"] == [
        "entry_changed_during_scan",
        "protected_or_ambiguous_present",
    ]


def test_directory_is_revalidated_after_scan(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "nested"
    _write_aged(nested / "observed-before-change.bin", age_days=4)
    original = Path.lstat
    calls = 0

    def changed_after_scan(path):
        nonlocal calls
        value = original(path)
        if Path(path) == nested:
            calls += 1
            if calls == 5:
                return _StatOverride(value, st_mode=stat.S_IFREG | 0o600)
        return value

    monkeypatch.setattr(Path, "lstat", changed_after_scan)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["classes"]["local_scratch"]["count"] == 1
    assert report["classes"]["protected_unknown"]["count"] == 1
    assert report["blocker_flags"] == [
        "entry_changed_during_scan",
        "protected_or_ambiguous_present",
    ]
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])


def test_hardlinks_are_deduplicated_by_device_and_inode(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    root.mkdir()
    first = root / "first.bin"
    second = root / "second.bin"
    _write_aged(first, age_days=2)
    try:
        os.link(first, second)
    except OSError as exc:
        pytest.skip(f"hardlink capability unavailable: {exc.__class__.__name__}")

    monkeypatch.setattr(artifact_retention, "_allocated_bytes", lambda value: 4096)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["totals"]["count"] == 2
    assert report["totals"]["apparent_bytes"] == 12
    assert report["totals"]["allocated_bytes"] == 4096
    assert report["totals"]["protected_count"] == 2
    assert report["deduplicated_hardlink_count"] == 1
    assert report["blocker_flags"] == ["protected_or_ambiguous_present"]


def test_unreadable_or_racing_scan_is_sanitized_and_incomplete(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    root.mkdir()

    def deny_scan(path):
        raise PermissionError("private-path-must-not-escape")

    monkeypatch.setattr(artifact_retention.os, "scandir", deny_scan)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["blocker_flags"] == ["scan_incomplete"]
    assert report["complete"] is False
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])
    assert "private-path-must-not-escape" not in json.dumps(report)


def test_entry_disappearing_after_enumeration_blocks_assessment(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    artifact = root / "racing.bin"
    _write_aged(artifact, age_days=2)
    original = Path.lstat

    def racing_lstat(path):
        if Path(path) == artifact:
            raise FileNotFoundError("private-racing-path")
        return original(path)

    monkeypatch.setattr(Path, "lstat", racing_lstat)
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["blocker_flags"] == ["scan_race_or_unreadable"]
    assert report["totals"]["count"] == 0
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])
    assert "private-racing-path" not in json.dumps(report)


def test_allocated_bytes_and_capacity_unavailable_are_explicit(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    _write_aged(root / "one.bin", age_days=2)

    monkeypatch.setattr(artifact_retention, "_allocated_bytes", lambda value: None)
    monkeypatch.setattr(
        artifact_retention.shutil,
        "disk_usage",
        lambda path: (_ for _ in ()).throw(OSError("private capacity detail")),
    )
    report = build_artifact_report(
        (ArtifactRoot("scratch", root),),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["classes"]["local_scratch"]["allocated_bytes"] is None
    assert report["classes"]["local_scratch"]["allocated_bytes_status"] == "unavailable"
    assert report["filesystems"] == [
        {
            "capacity_bytes": None,
            "free_bytes": None,
            "status": "unavailable",
            "used_bytes": None,
        }
    ]
    assert report["blocker_flags"] == ["filesystem_capacity_unavailable"]
    assert "private capacity detail" not in json.dumps(report)


def test_root_must_be_real_directory_and_invalid_kind_is_safely_blocked(tmp_path):
    file_root = tmp_path / "not-a-directory"
    file_root.write_bytes(b"sample")

    report = build_artifact_report(
        (
            ArtifactRoot("scratch", file_root),
            ArtifactRoot("invalid", tmp_path),
        ),
        as_of_seconds=AS_OF,
        include_assessment=False,
    )

    assert report["blocker_flags"] == ["invalid_root_kind", "unsafe_root_alias"]
    assert report["totals"]["count"] == 0


def test_evidence_floor_blocks_archive_and_migration_advice_without_global_error(
    tmp_path,
):
    archives = tmp_path / "archives"
    data = tmp_path / "data"
    _write_aged(archives / "player-wiki-backup-old.zip", age_days=31)
    _write_aged(data / "pre-migration-v0001-to-v0002.sqlite3", age_days=181)

    report = build_artifact_report(
        (ArtifactRoot("archive", archives), ArtifactRoot("data", data)),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["complete"] is False
    assert report["blocker_flags"] == ["protected_or_ambiguous_present"]
    assert report["classes"]["ordinary_verified_archives"]["count"] == 0
    assert report["classes"]["unverified_archive_candidates"]["count"] == 1
    assert _alert(report, "ordinary_verified_archives")["triggered"] is False
    for class_id in ("ordinary_verified_archives", "migration_snapshots"):
        row = _alert(report, class_id)
        assert row["assessment_blocked"] is True
        assert row["actionable"] is False
    assert _alert(report, "migration_snapshots")["triggered"] is True


def test_filename_only_archive_is_never_reported_as_verified(tmp_path):
    archives = tmp_path / "archives"
    _write_aged(archives / "player-wiki-backup-plausible.zip", age_days=31)

    report = build_artifact_report(
        (ArtifactRoot("archive", archives),),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert report["classes"]["ordinary_verified_archives"]["count"] == 0
    assert report["classes"]["unverified_archive_candidates"]["count"] == 1
    verified_alert = _alert(report, "ordinary_verified_archives")
    assert verified_alert["triggered"] is False
    assert verified_alert["assessment_blocked"] is True


def test_unknown_in_one_class_globally_blocks_pressure_advice_for_other_classes(
    tmp_path,
):
    data = tmp_path / "data"
    scratch = tmp_path / "scratch"
    _write_aged(data / "unknown-format.bin", age_days=2)
    _write_aged(scratch / "old-scratch.bin", age_days=8)

    report = build_artifact_report(
        (ArtifactRoot("data", data), ArtifactRoot("scratch", scratch)),
        as_of_seconds=AS_OF,
        include_assessment=True,
    )

    assert _alert(report, "local_scratch")["triggered"] is True
    assert all(row["assessment_blocked"] for row in report["advisory_alerts"])
    assert not any(row["actionable"] for row in report["advisory_alerts"])


def test_empty_roots_and_nonfinite_assessment_time_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        build_artifact_report((), as_of_seconds=AS_OF, include_assessment=False)
    with pytest.raises(ValueError, match="finite"):
        build_artifact_report(
            (ArtifactRoot("scratch", tmp_path),),
            as_of_seconds=float("nan"),
            include_assessment=False,
        )
