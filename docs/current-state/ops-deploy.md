# Ops And Fly Deployment

Last updated: 2026-07-10

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Python 3.12.12 is the canonical development and production interpreter; `.python-version` records the exact patch baseline.
- `requirements.txt` owns direct app-runtime ranges, `requirements-prod.txt` adds the production WSGI server, and `requirements-dev.txt` includes the production set plus test/browser tooling.
- Reproducible environments install `requirements-prod.lock` or `requirements-dev.lock` with pip `--require-hashes`. The committed universal Python 3.12 locks pin runtime transitives and do not install Playwright browser binaries.
- Lock refreshes use uv 0.9.28 through `scripts/refresh_requirements_locks.ps1 -Write`; `-Check` resolves into ignored `.local/tmp/runtime-baseline/` storage and byte-compares without changing tracked locks.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, test, contract, check, runtime-check, backup, restore, prepare-fly-campaigns, sync-fly, and deploy-fly.
- `local.ps1 -Action contract` runs the deterministic route/API/access manifest checks plus representative read-only smoke coverage for authentication, role and visibility boundaries, campaign surfaces, character assignment, and legacy rich-text rendering.
- The contract action is a fast local tier with a 60-second ceiling and a preferred runtime under 30 seconds. It does not replace focused domain tests, mutation-path tests, real-browser checks when interaction behavior requires them, or the full regression suite.
- Disposable local runtime temp files belong under `.local/tmp/<action>/` or task-specific `.task-temp` folders outside durable app data.

## Current Fly Deployment Shape

- Fly is the canonical supported production target. The tracked standalone systemd/nginx files are secondary examples aligned to the same one-process, one-Gunicorn-worker SQLite rule.
- The committed `fly.toml` is sanitized. Its `iad` region and `player_wiki_data` volume are generic, non-secret sample defaults; real app identity remains private local ops configuration.
- The Dockerfile pins `python:3.12.12-slim-bookworm` to immutable OCI index digest `sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c` and installs only `requirements-prod.lock` with pip hash enforcement.
- The real container entrypoint runs `manage.py init-db`, then Gunicorn with one worker, four threads, and a 60-second timeout. Fly retains one always-on machine, one `/data` volume, and one SQLite writer.
- Fly mounts the production SQLite/content volume at `/data`; the app DB lives on that mounted volume.
- The health endpoint is `/healthz`.
- Real app identity comes from `PLAYER_WIKI_FLY_APP`, `local.ps1 -Action deploy-fly`, or an explicit Fly app argument.
- Fly deploys snapshot the current working tree. Deploy from a clean copy if live should match committed state exactly.
- `.local/`, SQLite files, and local content mirrors are intentionally excluded from images.
- The Docker image is Python-only; it no longer builds or copies a separate browser bundle.

## Data And Volume Boundaries

- On Fly, app code is baked into the image.
- SQLite and campaign content live on the mounted `/data` volume.
- Additive schema changes come online through startup `manage.py init-db` against the mounted DB.
- Systems imports, auth rows, memberships, session rows, combat state, and other SQLite-backed changes are not changed by a code deploy unless explicit DB sync is performed.
- Content API writes on Fly update the live volume immediately but do not update local mirrors unless synced down.

## Verification Contract

- After dependency changes, install the development lock into a clean Python 3.12 environment with pip `--require-hashes`, run `pip check`, import `wsgi:app`, confirm Gunicorn is importable, and run the lock script in `-Check` mode twice.
- Static runtime contract tests enforce the immutable base image, hashed production install, entrypoint and secondary-example worker topology, Fly sample defaults and health shape, and disposable validator safety.
- `local.ps1 -Action runtime-check` requires an available Docker engine. It builds the current repo with a unique local tag, runs the real entrypoint using a strong disposable secret, ephemeral localhost port, and disposable `/tmp` data paths, then checks `/healthz`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, production WSGI metadata, and one Gunicorn worker before cleaning the container and image.
- The validator never contacts Fly or mounts real app data. Its local Docker Desktop Linux/amd64 engine-backed build/run verifies the pinned image, real `manage.py init-db` entrypoint, `/healthz` HTTP 200 with `status: ok`, Python 3.12.12, Gunicorn 23.0.0, production WSGI/routes, `pip check`, and one Gunicorn master with one worker. The failure harness confirms that post-health metadata failures emit container logs and still clean up the disposable container and image. No Fly deployment or live health validation has been performed.
- Run `local.ps1 -Action contract` for a fast route, API, access-policy, and representative read-boundary check. Run the full suite at milestone gates.
- Current Phase 1 milestone evidence includes a fresh hash-locked Python 3.12.12 environment, 35 contract tests, 112 security tests, the engine-backed runtime check, and 1,424/1,424 full-suite tests passing with zero failures or skips. The suite reports one existing future Python 3.14 tar-extraction warning.
- Normal deploy verification checks Fly status plus the live `/healthz` URL.
- After browser route changes, verify representative Flask `/campaigns/...` URLs.
- After app-shell/static-serving changes, verify versioned CSS/JS cache headers where relevant.
- After campaign asset-serving changes, verify representative asset content type.

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
