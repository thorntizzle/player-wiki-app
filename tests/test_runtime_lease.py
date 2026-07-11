from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from player_wiki.runtime_lease import (
    RuntimeRecoveryRequiredError,
    RuntimeStateBusyError,
    acquire_exclusive_state_lease,
    acquire_runtime_state_lease,
    active_restore_journal_path,
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
    lock_path = runtime_state_lock_path(database_path)

    with acquire_runtime_state_lease(database_path) as first:
        assert first.lock_path == lock_path
        identity = lock_path.stat().st_dev, lock_path.stat().st_ino
        assert lock_path.read_bytes() == b""

    assert lock_path.exists()
    with acquire_exclusive_state_lease(database_path):
        assert (lock_path.stat().st_dev, lock_path.stat().st_ino) == identity
    assert lock_path.exists()
    assert lock_path.read_bytes() == b""


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
