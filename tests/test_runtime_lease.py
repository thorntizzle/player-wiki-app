from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from player_wiki import runtime_lease
from player_wiki.runtime_lease import (
    RuntimeRecoveryRequiredError,
    RuntimeStateBusyError,
    RuntimeStateLease,
    RuntimeStateLeaseError,
    acquire_exclusive_state_lease,
    acquire_runtime_state_lease,
    active_restore_journal_path,
    recovery_runtime_state_lease_context,
    runtime_state_lock_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROCESS_TIMEOUT_SECONDS = 15.0


def _hold_lease(
    database_path: str,
    mode: str,
    ready_path: str,
    release_path: str,
) -> None:
    from player_wiki.runtime_lease import (
        acquire_exclusive_state_lease,
        acquire_runtime_state_lease,
    )

    acquire = (
        acquire_runtime_state_lease
        if mode == "shared"
        else acquire_exclusive_state_lease
    )
    with acquire(Path(database_path)):
        Path(ready_path).write_text("ready", encoding="utf-8")
        while not Path(release_path).exists():
            time.sleep(0.01)


def _acquire_then_crash(database_path: str, ready_path: str) -> None:
    from player_wiki.runtime_lease import acquire_exclusive_state_lease

    lease = acquire_exclusive_state_lease(Path(database_path))
    Path(ready_path).write_text("ready", encoding="utf-8")
    assert lease.mode == "exclusive"
    os._exit(17)


def _wait_for_file(path: Path, process: multiprocessing.Process) -> None:
    deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
    while not path.exists():
        if not process.is_alive():
            raise AssertionError(
                f"lease helper exited before becoming ready: exitcode={process.exitcode}"
            )
        if time.monotonic() >= deadline:
            raise AssertionError("lease helper did not become ready")
        time.sleep(0.01)


def _start_holder(
    tmp_path: Path,
    database_path: Path,
    mode: str,
    name: str,
) -> tuple[multiprocessing.Process, Path, Path]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    ready = tmp_path / f"{name}.ready"
    release = tmp_path / f"{name}.release"
    process = context.Process(
        target=_hold_lease,
        args=(str(database_path), mode, str(ready), str(release)),
    )
    process.start()
    _wait_for_file(ready, process)
    return process, ready, release


def _stop_holder(process: multiprocessing.Process, release: Path) -> None:
    release.write_text("release", encoding="utf-8")
    process.join(_PROCESS_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(_PROCESS_TIMEOUT_SECONDS)
    assert process.exitcode == 0


def _entrypoint_environment(tmp_path: Path, database_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PLAYER_WIKI_DB_PATH": str(database_path),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(tmp_path / "campaigns"),
            "PLAYER_WIKI_ENV": "testing",
        }
    )
    return environment


def test_shared_processes_coexist_and_exclude_exclusive_process(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    first, _, first_release = _start_holder(
        tmp_path, database_path, "shared", "first-shared"
    )
    second, _, second_release = _start_holder(
        tmp_path, database_path, "shared", "second-shared"
    )
    try:
        with pytest.raises(RuntimeStateBusyError):
            acquire_exclusive_state_lease(database_path)
    finally:
        _stop_holder(second, second_release)
        _stop_holder(first, first_release)

    with acquire_exclusive_state_lease(database_path):
        pass


def test_exclusive_process_excludes_shared_and_exclusive_processes(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    process, _, release = _start_holder(
        tmp_path, database_path, "exclusive", "exclusive"
    )
    try:
        with pytest.raises(RuntimeStateBusyError):
            acquire_runtime_state_lease(database_path)
        with pytest.raises(RuntimeStateBusyError):
            acquire_exclusive_state_lease(database_path)
    finally:
        _stop_holder(process, release)


def test_process_crash_releases_the_exclusive_lease(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()
    ready = tmp_path / "crash.ready"
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_acquire_then_crash,
        args=(str(database_path), str(ready)),
    )
    process.start()
    process.join(_PROCESS_TIMEOUT_SECONDS)
    assert not process.is_alive()
    assert process.exitcode == 17
    assert ready.read_text(encoding="utf-8") == "ready"

    with acquire_exclusive_state_lease(database_path):
        pass


def test_lock_file_is_persistent_and_never_replaced(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()
    lock_path = runtime_state_lock_path(database_path)

    with acquire_runtime_state_lease(database_path) as first:
        assert first.lock_path == lock_path
        identity = lock_path.stat().st_dev, lock_path.stat().st_ino
        assert lock_path.read_bytes() == b""
        if os.name == "nt":
            with pytest.raises(PermissionError):
                lock_path.unlink()
            replacement = lock_path.with_suffix(".replacement")
            replacement.write_bytes(b"replacement")
            with pytest.raises(PermissionError):
                os.replace(replacement, lock_path)
            replacement.unlink()

    assert lock_path.exists()
    with acquire_exclusive_state_lease(database_path):
        assert (lock_path.stat().st_dev, lock_path.stat().st_ino) == identity
    assert lock_path.exists()
    assert lock_path.read_bytes() == b""


def test_recovery_context_reuses_only_a_valid_open_shared_lease_without_closing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()

    with acquire_runtime_state_lease(database_path) as retained_lease:
        def fail_nested_acquisition(*_args, **_kwargs):
            pytest.fail("valid retained lease acquired a nested runtime lease")

        monkeypatch.setattr(
            runtime_lease,
            "acquire_runtime_state_lease",
            fail_nested_acquisition,
        )
        with recovery_runtime_state_lease_context(
            database_path.parent / "." / database_path.name,
            retained_lease=retained_lease,
            timeout_seconds=30.0,
        ) as active_lease:
            assert active_lease is retained_lease
            assert retained_lease.is_open is True

        assert retained_lease.is_open is True


def test_runtime_acquisition_canonicalizes_database_identity_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()
    path_alias = database_path.parent / "nested" / ".." / database_path.name
    calls: list[Path] = []
    real_canonicalize = runtime_lease.canonical_database_path

    def tracked_canonicalize(path: Path) -> Path:
        calls.append(Path(path))
        return real_canonicalize(path)

    monkeypatch.setattr(
        runtime_lease,
        "canonical_database_path",
        tracked_canonicalize,
    )

    with acquire_runtime_state_lease(path_alias) as lease:
        assert lease.database_path == database_path.resolve()

    assert calls == [path_alias]


def test_recovery_context_canonicalizes_dot_alias_once_before_retained_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()
    path_alias = database_path.parent / "nested" / ".." / database_path.name

    with acquire_runtime_state_lease(database_path) as retained_lease:
        calls: list[Path] = []
        real_canonicalize = runtime_lease.canonical_database_path

        def tracked_canonicalize(path: Path) -> Path:
            calls.append(Path(path))
            return real_canonicalize(path)

        monkeypatch.setattr(
            runtime_lease,
            "canonical_database_path",
            tracked_canonicalize,
        )
        with recovery_runtime_state_lease_context(
            path_alias,
            retained_lease=retained_lease,
        ) as active_lease:
            assert active_lease is retained_lease

    assert calls == [path_alias]


@pytest.mark.parametrize(
    "case",
    (
        "absent",
        "non_lease",
        "closed",
        "exclusive",
        "wrong_database",
        "wrong_lock",
        "wrong_descriptor",
        "restore_journal",
    ),
)
def test_recovery_context_invalid_retained_lease_uses_existing_acquisition_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    database_path = tmp_path / "state" / "wiki.sqlite3"
    database_path.parent.mkdir()
    retained_lease: object | None = None
    close_retained = False
    close_unlocked_descriptor = False

    if case == "non_lease":
        retained_lease = object()
    elif case == "closed":
        retained_lease = acquire_runtime_state_lease(database_path)
        retained_lease.close()
    elif case == "exclusive":
        retained_lease = acquire_exclusive_state_lease(database_path)
        close_retained = True
    elif case == "wrong_database":
        (tmp_path / "other-state").mkdir()
        retained_lease = acquire_runtime_state_lease(
            tmp_path / "other-state" / "wiki.sqlite3"
        )
        close_retained = True
    elif case == "wrong_lock":
        retained_lease = acquire_runtime_state_lease(database_path)
        retained_lease._lock_path = runtime_state_lock_path(  # type: ignore[attr-defined]
            tmp_path / "other-state" / "wiki.sqlite3"
        )
        close_retained = True
    elif case == "wrong_descriptor":
        unrelated_lock_path = tmp_path / "unrelated.runtime.lock"
        unrelated_lock_path.write_bytes(b"")
        retained_lease = RuntimeStateLease(
            unrelated_lock_path.open("r+b", buffering=0),
            database_path=database_path.resolve(),
            lock_path=runtime_state_lock_path(database_path),
            mode="shared",
        )
        close_unlocked_descriptor = True
    elif case == "restore_journal":
        retained_lease = acquire_runtime_state_lease(database_path)
        active_restore_journal_path(database_path).write_text("{}", encoding="utf-8")
        close_retained = True

    acquired = object()
    calls: list[tuple[Path, float]] = []

    class _FallbackContext:
        def __enter__(self):
            return acquired

        def __exit__(self, *_exc_info):
            return None

    def capture_acquisition(path: Path, *, timeout_seconds: float = 0.0):
        calls.append((Path(path), timeout_seconds))
        return _FallbackContext()

    monkeypatch.setattr(runtime_lease, "acquire_runtime_state_lease", capture_acquisition)
    try:
        with recovery_runtime_state_lease_context(
            database_path,
            retained_lease=retained_lease,
            timeout_seconds=30.0,
        ) as active_lease:
            assert active_lease is acquired
    finally:
        if close_retained:
            retained_lease.close()  # type: ignore[union-attr]
        elif close_unlocked_descriptor:
            retained_lease._lock_file.close()  # type: ignore[union-attr]

    assert calls == [(database_path.resolve(), 30.0)]


def test_active_restore_journal_fails_runtime_closed_without_leaking_path(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "private-sentinel" / "wiki.sqlite3"
    journal_path = active_restore_journal_path(database_path)
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeRecoveryRequiredError) as failure:
        acquire_runtime_state_lease(database_path)
    assert "explicit recovery" in str(failure.value)
    assert "private-sentinel" not in str(failure.value)

    with acquire_exclusive_state_lease(database_path):
        pass


@pytest.mark.parametrize("module_name", ("wsgi", "run"))
def test_runtime_entrypoints_refuse_pending_restore_before_app_creation(
    tmp_path: Path,
    module_name: str,
) -> None:
    database_path = tmp_path / f"{module_name}.sqlite3"
    active_restore_journal_path(database_path).write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=PROJECT_ROOT,
        env=_entrypoint_environment(tmp_path, database_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "explicit recovery" in result.stderr
    assert not database_path.exists()


def test_manage_init_refuses_pending_restore_before_database_mutation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "manage.sqlite3"
    active_restore_journal_path(database_path).write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "manage.py"), "init-db"],
        cwd=PROJECT_ROOT,
        env=_entrypoint_environment(tmp_path, database_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "explicit recovery" in result.stderr
    assert not database_path.exists()
    assert not Path(f"{database_path}.migration.lock").exists()


def test_manage_init_is_blocked_by_exclusive_maintenance_before_mutation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "manage-blocked.sqlite3"
    with acquire_exclusive_state_lease(database_path):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "manage.py"), "init-db"],
            cwd=PROJECT_ROOT,
            env=_entrypoint_environment(tmp_path, database_path),
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0
    assert "incompatible process" in result.stderr
    assert not database_path.exists()
    assert not Path(f"{database_path}.migration.lock").exists()


def test_wsgi_retains_shared_lease_for_the_runtime_process(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime.sqlite3"
    ready = tmp_path / "wsgi.ready"
    release = tmp_path / "wsgi.release"
    script = (
        "import time\n"
        "from pathlib import Path\n"
        "from wsgi import app\n"
        f"Path({str(ready)!r}).write_text('ready', encoding='utf-8')\n"
        f"release = Path({str(release)!r})\n"
        "while not release.exists(): time.sleep(0.01)\n"
        "assert app.extensions['runtime_state_lease']\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=_entrypoint_environment(tmp_path, database_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
        while not ready.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    f"WSGI helper exited before becoming ready: {stdout}{stderr}"
                )
            if time.monotonic() >= deadline:
                raise AssertionError("WSGI helper did not become ready")
            time.sleep(0.01)
        with pytest.raises(RuntimeStateBusyError):
            acquire_exclusive_state_lease(database_path)
    finally:
        release.write_text("release", encoding="utf-8")
        stdout, stderr = process.communicate(timeout=_PROCESS_TIMEOUT_SECONDS)
    assert process.returncode == 0, stdout + stderr


def test_timeout_validation_is_fail_closed(tmp_path: Path) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    for invalid in (-0.1, True, float("inf"), float("nan"), "1"):
        with pytest.raises(ValueError, match="non-negative"):
            acquire_runtime_state_lease(  # type: ignore[arg-type]
                database_path,
                timeout_seconds=invalid,
            )
    assert not runtime_state_lock_path(database_path).exists()


def test_huge_timeout_fails_before_any_filesystem_mutation(tmp_path: Path) -> None:
    database_path = tmp_path / "must-not-exist" / "wiki.sqlite3"
    with pytest.raises(ValueError, match="finite non-negative"):
        acquire_runtime_state_lease(
            database_path,
            timeout_seconds=10**400,
        )
    assert not database_path.parent.exists()


def test_canonicalization_error_is_normalized_without_path_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "private-canonical-sentinel" / "wiki.sqlite3"

    def fail_canonicalization(_path: Path) -> Path:
        raise OSError("private-canonical-sentinel")

    monkeypatch.setattr(
        runtime_lease,
        "canonical_database_path",
        fail_canonicalization,
    )
    with pytest.raises(RuntimeStateLeaseError) as failure:
        acquire_runtime_state_lease(database_path)
    assert "identity" in str(failure.value)
    assert "private-canonical-sentinel" not in str(failure.value)
    assert not database_path.parent.exists()


def test_missing_database_parent_is_not_created_recursively(tmp_path: Path) -> None:
    database_path = tmp_path / "missing" / "nested" / "wiki.sqlite3"
    with pytest.raises(RuntimeStateLeaseError, match="identity"):
        acquire_runtime_state_lease(database_path)
    assert not database_path.parent.exists()


def test_final_symlink_or_reparse_lock_object_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    lock_path = runtime_state_lock_path(database_path)
    if os.name == "nt":
        target = tmp_path / "reparse-target"
        target.mkdir()
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(lock_path), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        target = tmp_path / "symlink-target"
        target.write_text("sentinel", encoding="utf-8")
        lock_path.symlink_to(target)

    with pytest.raises(RuntimeStateLeaseError, match="identity"):
        acquire_runtime_state_lease(database_path)
    if os.name == "nt":
        assert target.is_dir()
    else:
        assert target.read_text(encoding="utf-8") == "sentinel"


def test_nonregular_lock_object_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    lock_path = runtime_state_lock_path(database_path)
    lock_path.mkdir()
    with pytest.raises(RuntimeStateLeaseError, match="identity"):
        acquire_runtime_state_lease(database_path)

    if os.name != "nt":
        lock_path.rmdir()
        os.mkfifo(lock_path)
        with pytest.raises(RuntimeStateLeaseError, match="identity"):
            acquire_runtime_state_lease(database_path)


def test_multi_link_lock_object_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    lock_path = runtime_state_lock_path(database_path)
    alias_path = tmp_path / "lock-alias"
    lock_path.write_bytes(b"")
    os.link(lock_path, alias_path)

    with pytest.raises(RuntimeStateLeaseError, match="identity"):
        acquire_runtime_state_lease(database_path)
    assert lock_path.stat().st_nlink == 2
    assert alias_path.stat().st_ino == lock_path.stat().st_ino


def test_lock_hardlink_created_during_acquisition_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    lock_path = runtime_state_lock_path(database_path)
    alias_path = tmp_path / "racing-lock-alias"
    original_acquire = runtime_lease._try_acquire_file_lock

    def link_then_acquire(lock_file, *, mode):
        os.link(lock_path, alias_path)
        original_acquire(lock_file, mode=mode)

    monkeypatch.setattr(runtime_lease, "_try_acquire_file_lock", link_then_acquire)
    with pytest.raises(RuntimeStateLeaseError, match="changed during acquisition"):
        acquire_runtime_state_lease(database_path)
    assert alias_path.stat().st_ino == lock_path.stat().st_ino


def test_database_hardlink_created_during_acquisition_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    alias_path = tmp_path / "racing-database-alias.sqlite3"
    database_path.write_bytes(b"database fixture")
    original_acquire = runtime_lease._try_acquire_file_lock

    def link_then_acquire(lock_file, *, mode):
        os.link(database_path, alias_path)
        original_acquire(lock_file, mode=mode)

    monkeypatch.setattr(runtime_lease, "_try_acquire_file_lock", link_then_acquire)
    with pytest.raises(RuntimeStateLeaseError, match="changed during acquisition"):
        acquire_runtime_state_lease(database_path)
    assert alias_path.stat().st_ino == database_path.stat().st_ino


def test_database_unlink_recreate_identity_race_fails_and_releases_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    alias_path = tmp_path / "old-database-alias.sqlite3"
    database_path.write_bytes(b"old database identity")
    original_acquire = runtime_lease._try_acquire_file_lock

    def replace_identity_then_acquire(lock_file, *, mode):
        os.link(database_path, alias_path)
        database_path.unlink()
        database_path.write_bytes(b"new database identity")
        original_acquire(lock_file, mode=mode)

    monkeypatch.setattr(
        runtime_lease,
        "_try_acquire_file_lock",
        replace_identity_then_acquire,
    )
    with pytest.raises(RuntimeStateLeaseError, match="changed during acquisition"):
        acquire_runtime_state_lease(database_path)

    assert alias_path.read_bytes() == b"old database identity"
    assert database_path.read_bytes() == b"new database identity"
    monkeypatch.setattr(
        runtime_lease,
        "_try_acquire_file_lock",
        original_acquire,
    )
    with acquire_exclusive_state_lease(database_path):
        pass


def test_missing_database_that_appears_during_acquisition_fails_and_releases_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    original_acquire = runtime_lease._try_acquire_file_lock

    def create_database_then_acquire(lock_file, *, mode):
        database_path.write_bytes(b"appeared during acquisition")
        original_acquire(lock_file, mode=mode)

    monkeypatch.setattr(
        runtime_lease,
        "_try_acquire_file_lock",
        create_database_then_acquire,
    )
    with pytest.raises(RuntimeStateLeaseError, match="changed during acquisition"):
        acquire_runtime_state_lease(database_path)

    assert database_path.read_bytes() == b"appeared during acquisition"
    monkeypatch.setattr(
        runtime_lease,
        "_try_acquire_file_lock",
        original_acquire,
    )
    with acquire_exclusive_state_lease(database_path):
        pass


def test_existing_database_that_disappears_during_acquisition_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    database_path.write_bytes(b"present before acquisition")
    original_acquire = runtime_lease._try_acquire_file_lock

    def remove_database_then_acquire(lock_file, *, mode):
        database_path.unlink()
        original_acquire(lock_file, mode=mode)

    monkeypatch.setattr(
        runtime_lease,
        "_try_acquire_file_lock",
        remove_database_then_acquire,
    )
    with pytest.raises(RuntimeStateLeaseError, match="changed during acquisition"):
        acquire_runtime_state_lease(database_path)
    assert not database_path.exists()


def test_first_startup_may_create_missing_database_after_lease_acquisition(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    with acquire_runtime_state_lease(database_path):
        assert not database_path.exists()
        database_path.write_bytes(b"created by startup while protected")
    assert database_path.read_bytes() == b"created by startup while protected"


def test_database_hardlink_aliases_are_rejected_without_lock_creation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "wiki.sqlite3"
    alias_path = tmp_path / "wiki-alias.sqlite3"
    database_path.write_bytes(b"database fixture")
    os.link(database_path, alias_path)

    for candidate in (database_path, alias_path):
        with pytest.raises(RuntimeStateLeaseError, match="identity"):
            acquire_runtime_state_lease(candidate)
        assert not runtime_state_lock_path(candidate).exists()


def test_unexpected_acquisition_error_is_safe_and_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "private-acquire-sentinel" / "wiki.sqlite3"
    database_path.parent.mkdir()
    captured: dict[str, object] = {}
    original_open = runtime_lease._open_lock_file

    def capture_open(path: Path):
        opened = original_open(path)
        captured["opened"] = opened
        return opened

    def fail_acquisition(*_args, **_kwargs):
        raise OSError("private-acquire-sentinel")

    monkeypatch.setattr(runtime_lease, "_open_lock_file", capture_open)
    monkeypatch.setattr(runtime_lease, "_try_acquire_file_lock", fail_acquisition)

    with pytest.raises(RuntimeStateLeaseError) as failure:
        acquire_runtime_state_lease(database_path)
    assert "acquired safely" in str(failure.value)
    assert "private-acquire-sentinel" not in str(failure.value)
    opened = captured["opened"]
    assert opened.lock_file.closed  # type: ignore[attr-defined]
    lock_path = runtime_state_lock_path(database_path)
    lock_path.unlink()
