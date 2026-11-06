"""Operator entry point for the app-owned atomic shared/core save.

Run with the configured environment and explicit matching data paths. This
command performs one save invocation, never retries, and does no qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def _write(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _publish(path, value):
    # A reporting failure must not truncate the last known durable outcome.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", suffix=".pending", delete=False) as stream:
        _write(stream, value)
        pending = stream.name
    os.replace(pending, path)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Nonfinite JSON value.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--campaigns", required=True, type=Path)
    args = parser.parse_args(argv)
    from .config import Config

    # Refuse a mismatched configured target before runtime construction/migrations.
    database, campaigns = args.database.resolve(strict=True), args.campaigns.resolve(strict=True)
    if database != Config.DB_PATH.resolve(strict=True) or campaigns != Config.CAMPAIGNS_DIR.resolve(strict=True):
        parser.error("Explicit data paths must match the configured environment.")
    with args.request.open("rb") as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        parser.error("Batch request exceeds 4 MiB.")
    request = json.loads(raw, object_pairs_hook=_object, parse_constant=_nonfinite)
    request_digest = hashlib.sha256(raw).hexdigest()
    if (type(request) is not dict or set(request) != {
            "campaign_slug", "actor_user_id", "expected_revision", "updates", "mechanics_impact_acknowledged"}
            or type(request["campaign_slug"]) is not str or not request["campaign_slug"]
            or request["mechanics_impact_acknowledged"] is not True):
        parser.error("Supply the exact batch fields and acknowledge mechanics impact.")

    # A preexisting outcome refuses replay. Output belongs outside the data roots.
    output = args.outcome.resolve()
    if (output.is_relative_to(database.parent) or output == args.request.resolve()
            or output.is_relative_to(campaigns) or output.is_symlink()):
        parser.error("Outcome must be a new file outside the data target and request.")
    with output.open("x", encoding="utf-8") as stream:
        _write(stream, {"state": "started", "committed": None})
    app = None
    receipt = None
    failure = None
    cleanup_error = None
    try:
        from .runtime_app import create_runtime_app
        from .db import get_db
        from .systems_mutations import save_shared_core_entries

        app = create_runtime_app()
        with app.app_context():
            actual = Path(get_db().execute("PRAGMA database_list").fetchone()[2]).resolve(strict=True)
            actual_campaigns = app.extensions["repository_store"].campaigns_dir.resolve(strict=True)
            if actual != database or actual_campaigns != campaigns:
                raise RuntimeError("Constructed app data target differs from the explicit paths.")
            receipt = save_shared_core_entries(
                app.extensions["systems_service"], app.extensions["auth_store"],
                request["campaign_slug"], actor_user_id=request["actor_user_id"],
                expected_revision=request["expected_revision"], updates=request["updates"],
            )
            receipt["request_sha256"] = request_digest
            # Emit known durability before any filesystem reporting or cleanup.
            print(json.dumps(receipt, sort_keys=True), flush=True)
            _publish(output, {"state": "committed", **receipt})
    except BaseException as error:
        failure = type(error).__name__
        print(json.dumps({"error_type": failure, "committed": True if receipt else None,
                          "receipt": receipt, "action": "read back; never automatically retry"}),
              file=sys.stderr, flush=True)
    finally:
        if app is not None:
            try:
                app.extensions["runtime_state_lease"].close()
            except BaseException as error:
                cleanup_error = type(error).__name__
        try:
            _publish(output, {"state": "finished", "committed": True if receipt else None,
                              "receipt": receipt, "error_type": failure,
                              "cleanup_error": cleanup_error})
        except BaseException as error:
            failure = failure or type(error).__name__
            print("Outcome write failed; retained stdout may prove commit. Read back; do not retry.",
                  file=sys.stderr, flush=True)
    return 1 if failure or cleanup_error or (receipt and receipt["postcommit_cache_error"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
