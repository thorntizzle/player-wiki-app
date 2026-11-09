"""One credential-free, fixed local readiness GET with complete preservation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys
import time

# -B alone still reads timestamp-valid caches. Select an unused prefix before
# importing any owned helper/application; -B ensures it stays unpopulated.
if not sys.dont_write_bytecode:
    raise RuntimeError("Use the configured interpreter with -B")
FRESH_BYTECODE_PREFIX = Path(__file__).resolve().parents[1] / ".local" / (
    "unused-qualification-bytecode-" + secrets.token_hex(24))
if FRESH_BYTECODE_PREFIX.exists():
    raise RuntimeError("Fresh bytecode prefix unexpectedly exists")
sys.pycache_prefix = str(FRESH_BYTECODE_PREFIX)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_qualification import (OwnedProcess, QualificationError, Timeline, capture_state, capture_file_tree,
    compare_states, file_identity, load_json, regular_path, utc_now, write_new_json)

ROOT = Path(__file__).resolve().parents[1]


def isolated(path: Path, *, directory: bool = False) -> Path:
    path = regular_path(path, directory=directory)
    local = regular_path(ROOT / ".local", directory=True)
    if path == local or not path.is_relative_to(local):
        raise QualificationError("Inputs must be existing explicit isolated .local paths")
    return path


def source_identity() -> dict:
    paths = [ROOT / ".python-version", ROOT / "requirements-prod.lock",
             ROOT / "requirements-dev.lock", Path(__file__),
             ROOT / "scripts/local_qualification.py"]
    result = {path.relative_to(ROOT).as_posix(): file_identity(path) for path in sorted(paths)}
    tree = capture_file_tree(ROOT / "player_wiki")
    result.update({"player_wiki/" + name: item for name, item in tree["files"].items()
                   if "__pycache__" not in Path(name).parts})
    if FRESH_BYTECODE_PREFIX.exists() or sys.pycache_prefix != str(FRESH_BYTECODE_PREFIX):
        raise QualificationError("Fresh bytecode admission drift")
    return result


def worker(run_dir: Path) -> int:
    run_dir = isolated(run_dir, directory=True)
    request = load_json(run_dir / "request.json")
    if set(request) != {"database", "campaigns", "nonce", "python_version", "root"}:
        raise QualificationError("Unexpected read request")
    database = isolated(Path(request["database"]))
    campaigns = isolated(Path(request["campaigns"]), directory=True)
    if request["root"] != str(ROOT) or request["python_version"] != ".".join(map(str, sys.version_info[:3])):
        raise QualificationError("Worker root/interpreter mismatch")
    if not isinstance(request["nonce"], str) or len(request["nonce"]) != 64:
        raise QualificationError("Invalid worker nonce")
    write_new_json(run_dir / "worker-ready.json", {
        "pid": os.getpid(), "parent_pid": os.getppid(), "nonce": request["nonce"],
        "python": file_identity(Path(sys.executable)), "at": utc_now()})
    deadline = time.monotonic() + 15
    while not (run_dir / "go.json").exists():
        if time.monotonic() > deadline:
            raise QualificationError("Native observer was not armed before deadline")
        time.sleep(0.02)
    if load_json(run_dir / "go.json") != {"nonce": request["nonce"]}:
        raise QualificationError("Native observer handshake mismatch")
    # Set before importing Config/app. No listener, credentials, sessions or bypasses.
    os.environ.update(PLAYER_WIKI_ENV="development", PLAYER_WIKI_DB_PATH=str(database),
        PLAYER_WIKI_CAMPAIGNS_DIR=str(campaigns), PLAYER_WIKI_RELOAD_CONTENT="false",
        PLAYER_WIKI_TRUST_PROXY="false", PLAYER_WIKI_SECRET_KEY=secrets.token_urlsafe(48),
        PLAYER_WIKI_REQUEST_TRAIL_ENABLED="false", PLAYER_WIKI_LIVE_DIAGNOSTICS="false",
        PLAYER_WIKI_INCIDENT_DIAGNOSTICS_ENABLED="false")
    sys.path.insert(0, str(ROOT))
    timeline = Timeline()
    with timeline.phase("app_construction"):
        from player_wiki.app import create_app
        app = create_app()
    with timeline.phase("GET_readyz"):
        with app.test_client() as client:
            response = client.get("/readyz", follow_redirects=False)
            body = response.get_json()
            if response.status_code != 200 or not isinstance(body, dict) or body.get("status") != "ready":
                raise QualificationError("Fixed readiness read did not pass")
            if body.get("checks") != {name: {"status": "ok"}
                                      for name in ("database", "migrations", "campaigns")}:
                raise QualificationError("Unexpected readiness checks")
            if response.headers.getlist("Set-Cookie"):
                raise QualificationError("Credential-free readiness unexpectedly set a cookie")
    if FRESH_BYTECODE_PREFIX.exists() or sys.pycache_prefix != str(FRESH_BYTECODE_PREFIX):
        raise QualificationError("Worker bytecode admission drift")
    write_new_json(run_dir / "read-result.json", {
        "path": "/readyz", "method": "GET", "status": response.status_code,
        "checks": body["checks"], "set_cookie_count": 0, "request_count": 1,
        "dispatch": "ordinary Flask WSGI test-client; no network or auth substitution",
        "owned_imports": "fresh nonexistent cache prefix with -B; prior caches untouched",
        "timing": timeline.summary(), "completed_utc": utc_now()})
    return 0


def qualify(database: Path, campaigns: Path, output: Path, *, confirmed: bool) -> dict:
    if not confirmed:
        raise QualificationError("Confirm exclusive stopped isolated inputs with --confirm-isolated")
    database, campaigns = isolated(database), isolated(campaigns, directory=True)
    expected_python = (ROOT / ".python-version").read_text().strip()
    if ".".join(map(str, sys.version_info[:3])) != expected_python or not sys.dont_write_bytecode:
        raise QualificationError("Use the exact configured interpreter with -B")
    output = Path(os.path.abspath(output))
    parent = isolated(output.parent, directory=True)
    if output.is_relative_to(campaigns) or output == database or output.exists():
        raise QualificationError("A new output directory outside captured inputs is required")
    output = parent / output.name
    output.mkdir()  # one exclusive evidence directory, never replacement/recursive cleanup
    timeline, process, closure, before = Timeline(), None, None, None
    failure = None
    result = {"status": "failed", "started_utc": timeline.started_utc,
              "scope": "one fixed credential-free GET /readyz on isolated stopped inputs"}
    try:
        with timeline.phase("source_and_input_admission"):
            sources = source_identity()
            write_new_json(output / "source.json", sources)
            python_identity = file_identity(Path(sys.executable))
        with timeline.phase("complete_PRE_capture"):
            before = capture_state(database, campaigns)
            write_new_json(output / "before.json", before)
        nonce = secrets.token_hex(32)
        write_new_json(output / "request.json", {"database": str(database),
            "campaigns": str(campaigns), "nonce": nonce, "python_version": expected_python,
            "root": str(ROOT)})
        with timeline.phase("child_start_and_native_admission"):
            env = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
            scratch = output / "scratch"
            scratch.mkdir()
            env.update(TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch))
            process = OwnedProcess([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                "--worker-run-dir", str(output)], cwd=ROOT, env=env, output_dir=output)
            deadline = time.monotonic() + 10
            while not (output / "worker-ready.json").exists():
                if process.child.poll() is not None:
                    raise QualificationError("Worker exited before readiness witness")
                if time.monotonic() >= deadline:
                    raise QualificationError("Worker readiness deadline exceeded")
                time.sleep(0.02)
            ready = load_json(output / "worker-ready.json")
            if ready["nonce"] != nonce or ready["python"] != python_identity:
                raise QualificationError("Worker nonce/interpreter mismatch")
            process.admit_native(ready["pid"], ready["parent_pid"])
            write_new_json(output / "go.json", {"nonce": nonce})
        with timeline.phase("worker_read_and_normal_closure"):
            closure = process.finish(60)
            write_new_json(output / "closure.json", closure)
            if not closure["normal_exit"]:
                raise QualificationError("Worker failed or closure remains unknown; no retry")
            read_result = load_json(output / "read-result.json")
            if read_result["status"] != 200 or read_result["request_count"] != 1:
                raise QualificationError("Read result is not the intended single request")
        with timeline.phase("complete_FINAL_capture_and_compare"):
            after = capture_state(database, campaigns)
            write_new_json(output / "after.json", after)
            comparison = compare_states(before, after)
            write_new_json(output / "comparison.json", comparison)
            if not comparison["unchanged"]:
                raise QualificationError("Captured data changed")
        with timeline.phase("source_closing_check"):
            if sources != source_identity() or python_identity != file_identity(Path(sys.executable)):
                raise QualificationError("Source/interpreter drift during qualification")
        result.update(status="observed_read_and_preservation_passed",
                      read=read_result, comparison=comparison, closure=closure)
    except Exception as error:
        failure = type(error).__name__  # private logs may contain app error details
        result.update(error_type=failure, closure=closure)
        if isinstance(error, QualificationError):
            result["reason"] = str(error)
    finally:
        if process is not None and closure is None:
            closure = process.finish(20)  # bounded wait; never kill an unknown child
            write_new_json(output / "closure.json", closure)
            result["closure"] = closure
        if before is not None and closure is not None and closure["state"] == "closed" and failure:
            try:
                with timeline.phase("closed_failure_preservation"):
                    after_failure = capture_state(database, campaigns)
                    write_new_json(output / "failure-after.json", after_failure)
                    result["failure_preservation"] = compare_states(before, after_failure)
            except Exception as error:
                result["failure_capture_error_type"] = type(error).__name__
        result.update(completed_utc=utc_now(), timing=timeline.summary(),
                      independent_acceptance="pending; observation is not reviewer acceptance")
        write_new_json(output / "outcome.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--campaigns", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-isolated", action="store_true")
    parser.add_argument("--worker-run-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_run_dir:
        if args.db or args.campaigns or args.output or args.confirm_isolated:
            parser.error("Worker arguments cannot mix with public arguments")
        return worker(args.worker_run_dir)
    if not all((args.db, args.campaigns, args.output)):
        parser.error("--db, --campaigns and --output are required")
    result = qualify(args.db, args.campaigns, args.output, confirmed=args.confirm_isolated)
    print(result["status"])
    return 0 if result["status"] == "observed_read_and_preservation_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
