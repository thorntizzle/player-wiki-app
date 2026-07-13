# Ops And Fly Deployment

Last updated: 2026-07-12

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Python 3.12.12 is the canonical development and production interpreter; `.python-version` records the exact patch baseline.
- `requirements.txt` owns direct app-runtime ranges, `requirements-prod.txt` adds the production WSGI server, and `requirements-dev.txt` includes the production set plus test/browser tooling.
- Reproducible environments install `requirements-prod.lock` or `requirements-dev.lock` with pip `--require-hashes`. The committed universal Python 3.12 locks pin runtime transitives and do not install Playwright browser binaries.
- Lock refreshes use uv 0.9.28 through `scripts/refresh_requirements_locks.ps1 -Write`; `-Check` resolves into ignored `.local/tmp/runtime-baseline/` storage and byte-compares without changing tracked locks.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`. The wrapper accepts an explicit `-PythonPath`, then `PLAYER_WIKI_PYTHON_PATH`, and can resolve the shared workspace virtualenv from an arbitrary Git worktree.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, test, test-focused, test-restore, test-browser, test-serial, contract, check, runtime-check, backup, restore, restore-status, restore-resume, restore-rollback, restore-rehearsal, prepare-fly-campaigns, sync-fly, and deploy-fly.
- `local.ps1 -Action contract` runs the deterministic route/API/access manifest checks plus representative read-only smoke coverage for authentication, role and visibility boundaries, campaign surfaces, character assignment, and legacy rich-text rendering.
- The contract action is a fast local tier with a 60-second ceiling and a preferred runtime under 30 seconds. It does not replace focused domain tests, mutation-path tests, real-browser checks when interaction behavior requires them, or the full regression suite.
- `local.ps1 -Action test-focused -TestPath <file-or-node-selector>[,<selector>...]` runs only an explicit focused selection; it never infers a domain from changed files.
- `local.ps1 -Action test-restore` runs the maintained backup/archive, operations, restore-transaction, runtime-lease, and SQLite-safety files. `local.ps1 -Action test-browser` runs the maintained Character read-shell browser, Combat DM-controls browser, and static-asset files.
- `local.ps1 -Action test-serial` runs the maintained migration, SQLite safety, runtime lease/baseline/security, app metadata, backup/restore/operations, login-throttle, and real-browser/live-server files serially. Parallel pytest execution is not installed, enabled, or the default.
- Every wrapper invocation uses a short unique ignored `.local` run name under `.local/tmp/`, `.local/pt/`, and `.local/pc/` for process temp, pytest basetemp, and pytest cache respectively. These paths bound the per-run suffix and prevent workers or consecutive runs from sharing scratch, but they cannot shorten an already long checkout prefix.
- Those `.local` paths are temp roots inside the current checkout; they are not a physical short-root checkout. For decisive Windows path-length controls, add `-PhysicalShortRoot` to `test-focused`, `test-restore`, `test-browser`, `test-serial`, `test`, or `check`. The wrapper refuses dirty source, freezes the exact commit/tree/index, creates a unique detached physical worktree under an absolute `-ShortRootBase`, `PLAYER_WIKI_SHORT_ROOT_BASE`, or the generic drive-root `cpwv` directory, verifies Git/blob/mode identity, then runs the selected action there.
- Normalized text identity is established by the Git commit, tree, index, blobs, and tracked modes; only files marked `text: unset` receive an additional raw-byte comparison. The helper prints its commit/tree/path/exit evidence and retains failures. Successful roots remain by default; `-RemoveShortRootOnSuccess` removes only the current invocation's generated detached clean worktree after identity and path verification. It does not prune or clean historical worktrees.
- Complete `test` and `check` actions are serialized by a lock in the repository's Git common directory. A physical short-root parent holds the lock for its child through a validated recursion guard, so two complete suites cannot claim the same repository at once.
- Production startup fails fast without a strong application secret. Request envelopes, individual uploads, and Systems ZIP extraction are bounded before expensive processing or durable publication.
- Disposable local runtime temp files belong under unique short `.local/tmp/<scope-prefix>-<run-id>/` paths or task-specific folders outside durable app data.

## Backup, Migration, And Recovery Contract

- SQLite schema changes use ordered numbered migrations with recorded migration state. `manage.py init-db` applies pending migrations before the production server starts.
- Backup archives use the verified v2 format and SQLite-aware online snapshots so committed WAL state is included. Restore validates archive metadata, hashes, database integrity, foreign keys, and migration state before publication.
- Every restore requires explicit destructive-action confirmation. Restoring over an existing, nonempty target creates a mandatory transaction-correlated prebackup; an empty target intentionally creates none. Restore does not expose a skip-prebackup option or a caller-selected prebackup label.
- Restore publication is journaled and atomic. The runtime lease prevents concurrent state-changing operations, and startup refuses to proceed while an interrupted restore journal requires recovery.
- `restore-status` reports a path-redacted recovery summary and fails closed for invalid or tampered journal state. `restore-resume` and `restore-rollback` require explicit confirmation and provide idempotent recovery for supported interrupted phases.
- `restore-rehearsal` accepts legacy-v1 or verified-v2 source archives and reports their evidence level. It uses a disposable, nonempty synthetic target that forces a mandatory verified-v2 prebackup, then verifies integrity and foreign keys, migration application/current state, hashes and counts, committed/clean journal state, and cleanup. It never publishes into active application data, and active-data sentinels must remain unchanged.

## Current Fly Deployment Shape

- Fly is the canonical supported production target. The tracked standalone systemd/nginx files are secondary examples aligned to the same one-process, one-Gunicorn-worker SQLite rule.
- The committed `fly.toml` is sanitized. Its `iad` region and `player_wiki_data` volume are generic, non-secret sample defaults; real app identity remains private local ops configuration.
- The Dockerfile pins `python:3.12.12-slim-bookworm` to immutable OCI index digest `sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c` and installs only `requirements-prod.lock` with pip hash enforcement.
- The real container entrypoint runs `manage.py init-db`, then Gunicorn with one worker, four threads, and a 60-second timeout. Fly retains one always-on machine, one `/data` volume, and one SQLite writer.
- Fly mounts the production SQLite/content volume at `/data`; the app DB lives on that mounted volume.
- `/livez` is the minimal liveness endpoint. `/readyz` checks database access, schema/migration state, required storage, and campaign storage without self-healing or mutating dependencies. The legacy `/healthz` endpoint remains available and returns application metadata.
- Real app identity comes from `PLAYER_WIKI_FLY_APP`, `local.ps1 -Action deploy-fly`, or an explicit Fly app argument.
- Fly deploys snapshot the current working tree. Deploy from a clean copy if live should match committed state exactly.
- `.local/`, SQLite files, and local content mirrors are intentionally excluded from images.
- The Docker image is Python-only; it no longer builds or copies a separate browser bundle.

## Data And Volume Boundaries

- On Fly, app code is baked into the image.
- SQLite and campaign content live on the mounted `/data` volume.
- Numbered schema migrations come online through startup `manage.py init-db` against the mounted DB before Gunicorn starts.
- Systems imports, auth rows, memberships, session rows, combat state, and other SQLite-backed changes are not changed by a code deploy unless explicit DB sync is performed.
- Content API writes on Fly update the live volume immediately but do not update local mirrors unless synced down.

## Verification Contract

- After dependency changes, install the development lock into a clean Python 3.12 environment with pip `--require-hashes`, run `pip check`, import `wsgi:app`, confirm Gunicorn is importable, and run the lock script in `-Check` mode twice.
- Static runtime contract tests enforce the immutable base image, hashed production install, migration-before-server entrypoint, one-process/one-worker topology, Fly sample defaults and health shape, strong production-secret requirement, bounded request envelopes, and disposable validator safety.
- `local.ps1 -Action runtime-check` requires an available Docker engine. It builds the current repo with a unique local tag, runs the real entrypoint using a strong disposable secret, ephemeral localhost port, and disposable `/tmp` data paths, then checks `/livez`, legacy `/healthz`, `/readyz`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, production WSGI metadata, and one Gunicorn worker before cleaning the container and image.
- The validator never contacts Fly or mounts real app data. Its local Docker Desktop Linux/amd64 engine-backed build/run verifies the pinned image, real migration from schema 0 to 1 before server start, `/livez` and legacy `/healthz` HTTP 200, missing-campaign `/readyz` HTTP 503 with `self_heal: false`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, and one Gunicorn master with one worker. Disposable containers and images are cleaned up. No Fly deployment or live health validation has been performed.
- Run `local.ps1 -Action contract` for a fast route, API, access-policy, and representative read-boundary check. Use `local.ps1 -Action test-focused -TestPath ...` for an explicit domain selection, `local.ps1 -Action test-restore` for the maintained recovery lane, `local.ps1 -Action test-browser` for the maintained browser/static lane, and `local.ps1 -Action test-serial` for shared-resource-sensitive coverage. The tracked [Flask Rewrite Program Workflow](../workflows/flask-rewrite-program.md) owns the complete-suite cadence, exact command, physical short-root controls, evidence reuse, and failure classification; this current-state document adds no per-slice or milestone complete-suite requirement.
- Current Phase 2 integration-branch milestone evidence is 38 contract-marker tests, 20 explicit manifest/smoke tests, 527 focused security/operations/contract tests plus one capability-classified skip, and 1,909 full-suite tests passing with one capability-classified skip and zero failures, errors, xfails, or warnings. The skip is the expected Windows symlink-privilege limitation (`WinError 1314`). Docker runtime and direct disposable restore-rehearsal gates also passed.
- Normal deploy verification checks Fly status plus live `/livez` and `/readyz`; legacy `/healthz` remains an application-metadata compatibility check.
- After browser route changes, verify representative Flask `/campaigns/...` URLs.
- After app-shell/static-serving changes, verify versioned CSS/JS cache headers where relevant.
- After campaign asset-serving changes, verify representative asset content type.

This contract is verified on `codex/flask-rewrite-integration`. Phase 2 has not been pushed, merged to `main`, deployed, exercised against Fly, or applied to live data.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `local.ps1`
- `ops.py`
- `Dockerfile`
- `fly.toml`
- `.dockerignore`
- `deploy/fly-entrypoint.sh`
- `$campaign-player-wiki-ops-deploy` private skill references for machine-local app identity and Fly commands.
