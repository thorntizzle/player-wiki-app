# TypeScript Ops Container Runtime Proof - 2026-06-28

Status: passed for no-live compiled runtime proof; Docker image build skipped
because Docker is unavailable in this worktree environment

## Scope

- Branch: `rewrite/ts-ops-container-runtime-proof`
- Integration base: `origin/rewrite/ts-phase3-integration` at
  `d9c1cf8eb544059b36116158de5ff95dd4eb485a`
- Proof command: `local.ps1 -Action ts-api-container-proof`
- Scratch root: `.task-temp/ts-ops-container-runtime-proof/`
- Copied campaigns source: tracked sanitized `tests/fixtures/sample_campaigns/`
- SQLite source: disposable scratch DB initialized by Flask `manage.py init-db`
- No-deploy confirmation: no Fly commands, no live URLs, no production app name,
  no live SQLite, no volume sync, no PR, no merge, and no deploy

This proof advances the Docker/Fly packaging gate by making the
production-shaped compiled TypeScript runtime smoke repeatable from the app
wrapper and by keeping the optional local Docker image smoke in the same command
when Docker is available. It does not move the gate to `local image builds`
because Docker was not available on `PATH` during this run.

## Implementation

- Added `apps/api/tests/container-runtime-proof.mjs`.
- Added `npm --prefix apps/api run test:container-runtime-proof`.
- Added `local.ps1 -Action ts-api-container-proof`, reusing the wrapper's
  Node/npm and Python resolution so the proof can run without global `node`,
  `npm`, or `python` assumptions.
- Broadened `.dockerignore` to exclude nested `.task-temp*` scratch folders.
- Extended `apps/api/tests/packaging-proof.mjs` to assert nested task scratch
  stays out of the Docker context.

The proof script:

1. Recreates `.task-temp/ts-ops-container-runtime-proof/`.
2. Copies sanitized fixture campaigns into that ignored scratch root.
3. Initializes a disposable SQLite DB at
   `.task-temp/ts-ops-container-runtime-proof/player_wiki.sqlite3` with Flask
   `manage.py init-db`.
4. Starts `apps/api/dist/server.js` with production-shaped TypeScript env:
   `NODE_ENV=production`, `PLAYER_WIKI_ENV=production`,
   `PLAYER_WIKI_RUNTIME=typescript-container-proof`, `CPW_DB_PATH`, and
   `CPW_CAMPAIGNS_DIR`.
5. Probes local-only `127.0.0.1` endpoints:
   - `GET /healthz`
   - `GET /api/v1/app`
   - `GET /campaigns/linden-pass/assets/lore/trade-coast-map.png`
6. If the Docker CLI and daemon are available, builds the non-default
   `ts-api-runtime-proof` target with `--pull=false`, runs it with the same
   copied scratch data mounted at `/proof-data`, and repeats the same probes.
7. If Docker is missing or the daemon is unavailable, records an environment
   skip and exits successfully after the compiled runtime proof.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File .\local.ps1 `
  -Action ts-api-container-proof `
  -NodeRoot "<codex-node-runtime>/bin"
```

## Result

The command passed.

Observed proof output, sanitized:

```text
TypeScript API container runtime proof passed.
Scratch root: <repo>\.task-temp\ts-ops-container-runtime-proof
Compiled runtime: /healthz ok, /api/v1/app ok, /campaigns/linden-pass/assets/lore/trade-coast-map.png image/png
Docker runtime: skipped (spawnSync docker ENOENT)
Summary: <repo>\.task-temp\ts-ops-container-runtime-proof\summary.json
```

Ignored summary highlights:

```json
{
  "proof": "ts-ops-container-runtime-proof",
  "no_deploy": true,
  "compiled_runtime": {
    "health_status": "ok",
    "health_environment": "production",
    "health_campaign_count": 1,
    "app_ok": true,
    "app_runtime": "typescript-container-proof",
    "asset_status": 200,
    "asset_content_type": "image/png",
    "asset_bytes": 69
  },
  "docker": {
    "status": "skipped",
    "reason": "spawnSync docker ENOENT"
  }
}
```

## Decision

- Previous packaging label: `static image path scaffolded`
- New packaging label: unchanged
- Strengthened evidence: repeatable wrapper-backed compiled runtime proof from a
  Flask-initialized scratch DB, copied sanitized campaigns, production-shaped
  TypeScript env, `/healthz`, `/api/v1/app`, and representative protected asset
  content type.
- Docker classification: tooling/environment skip because Docker was not
  available on `PATH`.
- Not claimed: local image build, local container boot, Fly deploy readiness,
  staging snapshot readiness, cutover rehearsal passed, PR approval, merge
  approval, deploy approval, live sync approval, or production write approval.

## Remaining Packaging Gates

- Run the same proof command in an environment with Docker available and collect
  the local `ts-api-runtime-proof` image build plus container boot transcript.
- Decide the final packaging shape: TypeScript-only replacement,
  Flask-plus-TypeScript transition image, sidecar, or local-only Hono proof until
  cutover.
- Prove frontend bundle behavior if the TypeScript runtime becomes responsible
  for `/app-next/`.
- Finalize the startup/migration boundary between Flask `manage.py init-db` and
  TypeScript/Drizzle migration commands.
- Complete image-level rollback evidence before any user-approved deploy or
  cutover step.
