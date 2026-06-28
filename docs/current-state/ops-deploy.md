# Ops And Fly Deployment

Last updated: 2026-06-25

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`.
- Prefer existing `frontend/node_modules` tools or bundled Node; do not assume global `npm` is on `PATH`.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, test, check, backup, restore, prepare-fly-campaigns, sync-fly, and deploy-fly.
- Disposable local runtime temp files belong under `.local/tmp/<action>/` or task-specific `.task-temp` folders outside durable app data.
- The default Docker/Fly image remains Flask/Gunicorn. `Dockerfile` also exposes a non-default `ts-api-runtime-proof` target for local-only TypeScript API packaging proof work; it is not the production deploy target.

## Current Fly Deployment Shape

- The committed `fly.toml` is sanitized. Real app identity, public URL, region, and volume names are supplied by private local ops configuration or skill references.
- Fly mounts the production SQLite/content volume at `/data`; the app DB lives on that mounted volume.
- The health endpoint is `/healthz`.
- Real app identity comes from `PLAYER_WIKI_FLY_APP`, `local.ps1 -Action deploy-fly`, or an explicit Fly app argument.
- Fly deploys snapshot the current working tree. Deploy from a clean copy if live should match committed state exactly.
- `.local/`, SQLite files, local content mirrors, and local frontend build output are intentionally excluded from images.

## Data And Volume Boundaries

- On Fly, app code is baked into the image.
- SQLite and campaign content live on the mounted `/data` volume.
- Additive schema changes come online through startup `manage.py init-db` against the mounted DB.
- Systems imports, auth rows, memberships, session rows, combat state, and other SQLite-backed changes are not changed by a code deploy unless explicit DB sync is performed.
- Content API writes on Fly update the live volume immediately but do not update local mirrors unless synced down.

## Verification Contract

- Normal deploy verification checks Fly status plus the live `/healthz` URL.
- After Gen2/frontend changes, verify an explicit `/app-next/` URL.
- After app-shell/static-serving changes, verify versioned CSS cache headers where relevant.
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
