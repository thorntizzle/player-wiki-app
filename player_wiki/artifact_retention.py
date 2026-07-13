from __future__ import annotations

import math
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


GIB = 1024 * 1024 * 1024
DAY_SECONDS = 24 * 60 * 60
AGE_BUCKETS = ("<24h", "1-7d", "8-30d", "31-90d", ">90d")
CLASS_IDS = (
    "incomplete_stages",
    "local_scratch",
    "ordinary_verified_archives",
    "unverified_archive_candidates",
    "pre_restore_pre_sync_evidence",
    "migration_snapshots",
    "live_preimport_presync_copies",
    "protected_unknown",
)
ROOT_KINDS = ("data", "archive", "scratch")

_MIGRATION_RE = re.compile(
    r"^pre-migration-v(?P<from>\d{4})-to-v(?P<to>\d{4})(?:\.\d+)?\.sqlite3$",
    re.IGNORECASE,
)
_RESTORE_BUNDLE_RE = re.compile(r"^\..+\.restore-[^.]+\.(?:old|new)$", re.IGNORECASE)
_INCOMPLETE_PATTERNS = (
    re.compile(r"^\..+\.snapshot\.tmp.*$", re.IGNORECASE),
    re.compile(r"^\.player-wiki-backup-.*\.(?:sqlite3|zip)$", re.IGNORECASE),
    re.compile(r"^\..+\.restore-journal\.json\..+\.tmp$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class ArtifactRoot:
    kind: str
    path: Path


@dataclass(slots=True)
class _Artifact:
    class_id: str
    apparent_bytes: int
    allocated_bytes: int | None
    modified_seconds: float
    protected: bool
    group: str = ""


@dataclass(slots=True)
class _ScanState:
    artifacts: list[_Artifact]
    blockers: set[str]
    seen_files: dict[tuple[int, int], int]
    deduplicated_count: int = 0


def build_artifact_report(
    roots: Iterable[ArtifactRoot],
    *,
    as_of_seconds: float,
    include_assessment: bool,
) -> dict[str, object]:
    """Return a path-redacted, zero-write aggregate artifact report."""

    root_values = tuple(roots)
    if not root_values:
        raise ValueError("At least one artifact root is required.")
    if not math.isfinite(as_of_seconds):
        raise ValueError("The assessment time must be finite.")

    state = _ScanState([], set(), {})
    filesystems: dict[int, tuple[int, int, int] | None] = {}
    for root in sorted(root_values, key=lambda item: (item.kind, str(item.path))):
        if root.kind not in ROOT_KINDS:
            state.blockers.add("invalid_root_kind")
            continue
        _scan_root(root, state, filesystems)

    if any(item.modified_seconds > as_of_seconds for item in state.artifacts):
        state.blockers.add("future_timestamp")
    if any(item.protected for item in state.artifacts):
        state.blockers.add("protected_or_ambiguous_present")

    recovery_blocked = bool(
        {"restore_recovery_pending", "restore_bundle_present"} & state.blockers
    )
    classes = {
        class_id: _summarize_class(
            class_id,
            state.artifacts,
            as_of_seconds=as_of_seconds,
            recovery_blocked=recovery_blocked,
        )
        for class_id in CLASS_IDS
    }
    totals = _summarize_totals(classes)
    filesystem_rows = [
        {
            "capacity_bytes": values[0] if values is not None else None,
            "free_bytes": values[2] if values is not None else None,
            "used_bytes": values[1] if values is not None else None,
            "status": "available" if values is not None else "unavailable",
        }
        for _, values in sorted(
            filesystems.items(),
            key=lambda item: item[1] if item[1] is not None else (math.inf,) * 3,
        )
    ]
    report: dict[str, object] = {
        "age_buckets": list(AGE_BUCKETS),
        "blocker_flags": sorted(state.blockers),
        "classes": classes,
        "complete": not state.blockers,
        "deduplicated_hardlink_count": state.deduplicated_count,
        "filesystems": filesystem_rows,
        "mode": "retention_assessment" if include_assessment else "inventory",
        "schema_version": 1,
        "totals": totals,
    }
    if include_assessment:
        report["advisory_alerts"] = _build_alerts(
            state.artifacts,
            classes,
            as_of_seconds=as_of_seconds,
            blocked=bool(state.blockers),
        )
    return report


def _scan_root(
    root: ArtifactRoot,
    state: _ScanState,
    filesystems: dict[int, tuple[int, int, int] | None],
) -> None:
    path = Path(os.path.abspath(root.path))
    try:
        root_stat = _validate_root_components(path)
        if root_stat is None:
            state.blockers.add("unsafe_root_alias")
            return
        root_device = int(root_stat.st_dev)
        try:
            usage = shutil.disk_usage(path)
            capacity_stat = path.lstat()
            if not _same_identity_and_type(root_stat, capacity_stat) or (
                _is_alias_or_special(capacity_stat)
                or int(capacity_stat.st_dev) != root_device
            ):
                _append_changed(root_stat, state)
                return
            filesystems[root_device] = (usage.total, usage.used, usage.free)
        except OSError:
            filesystems[root_device] = None
            state.blockers.add("filesystem_capacity_unavailable")
        _scan_directory(
            path,
            path,
            root.kind,
            root_device,
            root_stat,
            state,
        )
    except (OSError, RuntimeError, ValueError):
        state.blockers.add("root_unavailable")


def _validate_root_components(path: Path) -> os.stat_result | None:
    if not path.is_absolute() or not path.anchor:
        return None
    current = Path(path.anchor)
    components = path.parts[1:]
    if not components:
        components = ()
    last_stat = current.lstat()
    if _is_alias_or_special(last_stat) or not stat.S_ISDIR(last_stat.st_mode):
        return None
    for component in components:
        current = current / component
        last_stat = current.lstat()
        if _is_alias_or_special(last_stat) or not stat.S_ISDIR(last_stat.st_mode):
            return None
    return last_stat


def _scan_directory(
    root: Path,
    directory: Path,
    root_kind: str,
    root_device: int,
    expected_stat: os.stat_result,
    state: _ScanState,
) -> None:
    if not _revalidate_directory(directory, expected_stat, root_device, state):
        return
    try:
        entries = os.scandir(directory)
    except OSError:
        state.blockers.add("scan_incomplete")
        return
    with entries:
        if not _revalidate_directory(directory, expected_stat, root_device, state):
            return
        try:
            ordered = sorted(entries, key=lambda entry: entry.name)
        except OSError:
            state.blockers.add("scan_incomplete")
            return

    for entry in ordered:
        entry_path = Path(entry.path)
        try:
            entry_stat = entry_path.lstat()
        except OSError:
            state.blockers.add("scan_race_or_unreadable")
            continue
        if _is_alias_or_special(entry_stat):
            _append_special(entry_stat, state, blocker="special_or_ambiguous_entry")
            continue
        if int(entry_stat.st_dev) != root_device:
            _append_special(entry_stat, state, blocker="cross_device_entry")
            continue
        if not _lexically_contained(root, entry_path):
            _append_special(entry_stat, state, blocker="containment_ambiguous")
            continue
        try:
            confirmed_stat = entry_path.lstat()
        except OSError:
            _append_changed(entry_stat, state)
            continue
        if (
            not _same_identity_and_type(entry_stat, confirmed_stat)
            or _is_alias_or_special(confirmed_stat)
            or int(confirmed_stat.st_dev) != root_device
        ):
            _append_changed(entry_stat, state)
            continue
        if stat.S_ISDIR(confirmed_stat.st_mode):
            if _RESTORE_BUNDLE_RE.fullmatch(entry.name):
                state.blockers.add("restore_bundle_present")
                state.artifacts.append(
                    _Artifact(
                        "incomplete_stages",
                        max(0, int(confirmed_stat.st_size)),
                        None,
                        float(confirmed_stat.st_mtime),
                        True,
                    )
                )
                continue
            _scan_directory(
                root,
                entry_path,
                root_kind,
                root_device,
                confirmed_stat,
                state,
            )
        elif stat.S_ISREG(confirmed_stat.st_mode):
            class_id, protected, group = _classify(entry.name, root_kind)
            if entry.name.lower().endswith(".restore-journal.json"):
                state.blockers.add("restore_recovery_pending")
            if _RESTORE_BUNDLE_RE.fullmatch(entry.name):
                state.blockers.add("restore_bundle_present")
            identity = (int(confirmed_stat.st_dev), int(confirmed_stat.st_ino))
            hardlinked = int(getattr(confirmed_stat, "st_nlink", 1)) > 1
            allocated_bytes = _allocated_bytes(confirmed_stat)
            if identity in state.seen_files:
                state.deduplicated_count += 1
                allocated_bytes = 0
                state.artifacts[state.seen_files[identity]].protected = True
                hardlinked = True
            else:
                state.seen_files[identity] = len(state.artifacts)
            state.artifacts.append(
                _Artifact(
                    class_id,
                    max(0, int(confirmed_stat.st_size)),
                    allocated_bytes,
                    float(confirmed_stat.st_mtime),
                    protected or hardlinked,
                    group,
                )
            )
        else:
            _append_special(confirmed_stat, state, blocker="special_or_ambiguous_entry")

    _revalidate_directory(directory, expected_stat, root_device, state)


def _revalidate_directory(
    directory: Path,
    expected_stat: os.stat_result,
    root_device: int,
    state: _ScanState,
) -> bool:
    try:
        current_stat = directory.lstat()
    except OSError:
        _append_changed(expected_stat, state)
        return False
    if (
        not _same_identity_and_type(expected_stat, current_stat)
        or _is_alias_or_special(current_stat)
        or not stat.S_ISDIR(current_stat.st_mode)
        or int(current_stat.st_dev) != root_device
    ):
        _append_changed(expected_stat, state)
        return False
    return True


def _same_identity_and_type(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        int(first.st_dev),
        int(first.st_ino),
        stat.S_IFMT(first.st_mode),
    ) == (
        int(second.st_dev),
        int(second.st_ino),
        stat.S_IFMT(second.st_mode),
    )


def _lexically_contained(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


def _is_alias_or_special(value: os.stat_result) -> bool:
    return _is_reparse(value) or stat.S_ISLNK(value.st_mode)


def _append_changed(entry_stat: os.stat_result, state: _ScanState) -> None:
    _append_special(entry_stat, state, blocker="entry_changed_during_scan")


def _append_special(
    entry_stat: os.stat_result,
    state: _ScanState,
    *,
    blocker: str,
) -> None:
    state.blockers.add(blocker)
    state.artifacts.append(
        _Artifact(
            "protected_unknown",
            max(0, int(entry_stat.st_size)),
            None,
            float(entry_stat.st_mtime),
            True,
        )
    )


def _classify(name: str, root_kind: str) -> tuple[str, bool, str]:
    lowered = name.lower()
    migration = _MIGRATION_RE.fullmatch(name)
    if migration:
        return (
            "migration_snapshots",
            True,
            f"{migration.group('from')}:{migration.group('to')}",
        )
    if _RESTORE_BUNDLE_RE.fullmatch(name) or any(
        pattern.fullmatch(name) for pattern in _INCOMPLETE_PATTERNS
    ):
        return "incomplete_stages", bool(_RESTORE_BUNDLE_RE.fullmatch(name)), ""
    if (
        "preimport" in lowered
        or "pre-import" in lowered
        or "presync" in lowered
        or "pre-sync" in lowered
    ) and lowered.endswith((".sqlite3", ".db")):
        return "live_preimport_presync_copies", True, ""
    if root_kind == "archive" and lowered.endswith(".zip"):
        return "unverified_archive_candidates", True, ""
    if root_kind == "scratch":
        return "local_scratch", False, ""
    return "protected_unknown", True, ""


def _allocated_bytes(value: os.stat_result) -> int | None:
    blocks = getattr(value, "st_blocks", None)
    if blocks is None:
        return None
    return max(0, int(blocks) * 512)


def _is_reparse(value: os.stat_result) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0)) & 0x400)


def _bucket_for(modified_seconds: float, as_of_seconds: float) -> tuple[str, bool]:
    age = as_of_seconds - modified_seconds
    if age < 0:
        return "<24h", True
    days = age / DAY_SECONDS
    if days < 1:
        return "<24h", False
    if days < 8:
        return "1-7d", False
    if days < 31:
        return "8-30d", False
    if days <= 90:
        return "31-90d", False
    return ">90d", False


def _summarize_class(
    class_id: str,
    artifacts: list[_Artifact],
    *,
    as_of_seconds: float,
    recovery_blocked: bool,
) -> dict[str, object]:
    selected = [item for item in artifacts if item.class_id == class_id]
    buckets = {
        bucket: {"apparent_bytes": 0, "count": 0}
        for bucket in AGE_BUCKETS
    }
    future_count = 0
    for item in selected:
        bucket, future = _bucket_for(item.modified_seconds, as_of_seconds)
        buckets[bucket]["count"] += 1
        buckets[bucket]["apparent_bytes"] += item.apparent_bytes
        future_count += int(future)
    allocated_available = all(item.allocated_bytes is not None for item in selected)
    protected_count = sum(
        1
        for item in selected
        if item.protected
        or (recovery_blocked and class_id == "incomplete_stages")
        or (
            class_id == "incomplete_stages"
            and as_of_seconds - item.modified_seconds < DAY_SECONDS
        )
    )
    return {
        "age_buckets": buckets,
        "allocated_bytes": (
            sum(int(item.allocated_bytes or 0) for item in selected)
            if allocated_available
            else None
        ),
        "allocated_bytes_status": "available" if allocated_available else "unavailable",
        "apparent_bytes": sum(item.apparent_bytes for item in selected),
        "count": len(selected),
        "future_timestamp_count": future_count,
        "protected_count": protected_count,
    }


def _summarize_totals(classes: dict[str, dict[str, object]]) -> dict[str, object]:
    allocated_available = all(
        value["allocated_bytes_status"] == "available" for value in classes.values()
    )
    return {
        "allocated_bytes": (
            sum(int(value["allocated_bytes"]) for value in classes.values())
            if allocated_available
            else None
        ),
        "allocated_bytes_status": "available" if allocated_available else "unavailable",
        "apparent_bytes": sum(int(value["apparent_bytes"]) for value in classes.values()),
        "count": sum(int(value["count"]) for value in classes.values()),
        "protected_count": sum(int(value["protected_count"]) for value in classes.values()),
        "unknown_count": int(classes["protected_unknown"]["count"]),
    }


def _build_alerts(
    artifacts: list[_Artifact],
    classes: dict[str, dict[str, object]],
    *,
    as_of_seconds: float,
    blocked: bool,
) -> list[dict[str, object]]:
    definitions = (
        ("incomplete_stages", "incomplete_stages_24h_zero", 1, 0, None),
        ("local_scratch", "local_scratch_7d_newest10_2gib", 7, 10, 2 * GIB),
        (
            "ordinary_verified_archives",
            "ordinary_verified_archives_30d_newest14_32gib",
            30,
            14,
            32 * GIB,
        ),
        (
            "pre_restore_pre_sync_evidence",
            "pre_restore_pre_sync_evidence_90d_newest10_32gib_combined",
            90,
            10,
            32 * GIB,
        ),
        (
            "migration_snapshots",
            "migration_snapshots_180d_newest2_per_transition_newest5_global_12gib",
            180,
            5,
            12 * GIB,
        ),
        (
            "live_preimport_presync_copies",
            "live_preimport_presync_copies_90d_newest2_to3_12gib",
            90,
            3,
            12 * GIB,
        ),
    )
    rows = []
    for class_id, threshold_id, age_days, newest, byte_limit in definitions:
        selected = [item for item in artifacts if item.class_id == class_id]
        old_count = sum(
            1
            for item in selected
            if as_of_seconds - item.modified_seconds >= age_days * DAY_SECONDS
        )
        per_group_excess = False
        if class_id == "migration_snapshots":
            groups: dict[str, int] = {}
            for item in selected:
                groups[item.group] = groups.get(item.group, 0) + 1
            per_group_excess = any(value > 2 for value in groups.values())
        byte_excess = byte_limit is not None and (
            int(classes[class_id]["apparent_bytes"]) > byte_limit
        )
        count_excess = len(selected) > newest
        rows.append(
            {
                "actionable": False,
                "advisory": True,
                "assessment_blocked": blocked
                or int(classes[class_id]["protected_count"]) > 0,
                "class_id": class_id,
                "threshold": {
                    "apparent_bytes": byte_limit,
                    "minimum_age_seconds": age_days * DAY_SECONDS,
                    "retain_newest_count": newest,
                    "retain_per_transition_count": (
                        2 if class_id == "migration_snapshots" else None
                    ),
                },
                "threshold_id": threshold_id,
                "triggered": bool(
                    old_count or byte_excess or count_excess or per_group_excess
                ),
                "triggered_by": sorted(
                    key
                    for key, value in {
                        "age": old_count > 0,
                        "apparent_bytes": byte_excess,
                        "global_count": count_excess,
                        "per_transition_count": per_group_excess,
                    }.items()
                    if value
                ),
            }
        )
    return rows
