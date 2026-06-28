# Ops And Fly Deployment

Last updated: 2026-06-28

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`.
- Prefer existing `frontend/node_modules` tools or bundled Node; do not assume global `npm` is on `PATH`.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, test, check, TypeScript API validation, TypeScript API container/runtime proof, backup, restore, prepare-fly-campaigns, sync-fly, and deploy-fly.
- `local.ps1 -Action ts-api-check` is the local TypeScript API validation gate. It resolves Node/npm from explicit parameters, `CPW_NODE_*` environment variables, repo-local ignored runtimes, `$HOME`-relative Codex or pinned Node runtime locations, and then `PATH`; it does not require global `npm` to be on `PATH`.
- The TypeScript API gate runs `npm ci`, `scripts/route_snapshots.py --check`, `npm --prefix apps/api run typecheck`, `npm --prefix apps/api run build`, `npm --prefix apps/api run test:sqlite-startup-posture`, `npm --prefix apps/api run test:sqlite-schema-check`, `npm --prefix apps/api run test:sqlite-migrate-proof`, and `npm --prefix apps/api run test:route-parity`. Use `-SkipTsApiInstall` only when `apps/api/node_modules` is already current, and `-SkipRouteSnapshotCheck` only for diagnostics that do not need the Flask route snapshot.
- `local.ps1 -Action ts-api-container-proof` is the no-deploy TypeScript API runtime packaging proof. It resolves the same Node/npm and Python toolchains, runs `npm --prefix apps/api run test:container-runtime-proof`, creates disposable copied fixture data under `.task-temp/ts-ops-container-runtime-proof/`, initializes that scratch DB with Flask `manage.py init-db`, starts the compiled TypeScript API in production-shaped env, checks local `/healthz`, `/api/v1/app`, and representative protected PNG asset serving, and runs the non-default Docker proof image only when local Docker is available.
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
- During the TypeScript rewrite transition, Flask `manage.py init-db` remains the SQLite schema initializer. The TypeScript API startup preflights the configured DB for the current Flask-initialized schema before serving, `npm --prefix apps/api run sqlite:schema-check -- --db <copy>` provides a read-only TypeScript-side schema proof command for copied or disposable databases, and `npm --prefix apps/api run sqlite:migrate-proof -- --db <copy> --apply` provides an explicit no-startup additive migration-hook proof that only creates a TypeScript migration ledger after the Flask-current schema is already present. TypeScript SQLite opens apply explicit PRAGMAs for foreign keys, WAL/normal synchronous on writable opens, and a 30000 ms busy timeout.
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
