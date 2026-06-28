# TypeScript Local Runtime Evidence

Last updated: 2026-06-27

Status: no-live local runtime proof for `rewrite/ts-ops-local-packaging-proof`.

This transcript proves the integrated TypeScript API can install dependencies,
build, start locally from compiled output, and answer `/healthz` against
fixture/local paths. It does not approve PR, merge, deploy, Fly sync, production
SQLite sync, live URL checks, or cutover. Flask remains the production authority.

## Worktree And Branch

- Worktree: `C:\Users\thorn\.codex\worktrees\ebe8\campaign_player_wiki`
- Branch: `rewrite/ts-ops-local-packaging-proof`
- Baseline: `origin/rewrite/ts-phase1-integration` at `ccd2d34`

## Runtime

- Node: `C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64\node.exe`
- npm: `C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64\npm.cmd`
- Campaign fixtures: `tests\fixtures\sample_campaigns`
- SQLite path: `.local\tmp\ts-ops-local-packaging-proof\player_wiki.sqlite3`

## Commands

```powershell
$nodeDir = 'C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64'
$env:PATH = "$nodeDir;$env:PATH"
& "$nodeDir\npm.cmd" --prefix apps/api ci
& "$nodeDir\npm.cmd" --prefix apps/api run build

$env:NODE_ENV = 'test'
$env:PORT = '<free localhost port>'
$env:CPW_CAMPAIGNS_DIR = '<repo>\tests\fixtures\sample_campaigns'
$env:CPW_DB_PATH = '<repo>\.local\tmp\ts-ops-local-packaging-proof\player_wiki.sqlite3'
$env:PLAYER_WIKI_VERSION = 'ops-packaging-proof'
$env:PLAYER_WIKI_BUILD_ID = 'local-proof'
$env:PLAYER_WIKI_GIT_SHA = 'ccd2d34'
$env:PLAYER_WIKI_GIT_DIRTY = '0'
$env:PLAYER_WIKI_RUNTIME = 'typescript-local-proof'
$env:PLAYER_WIKI_INSTANCE_NAME = 'local-proof'
$env:PLAYER_WIKI_BASE_URL = 'http://127.0.0.1:<free localhost port>'
$env:PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS = '300'

& "$nodeDir\node.exe" apps/api/dist/server.js
Invoke-RestMethod -Uri 'http://127.0.0.1:<free localhost port>/healthz'
```

The proof run used local port `58953`, then stopped the Node process.

## Results

| Check | Result |
| --- | --- |
| `npm --prefix apps/api ci` | Passed; 46 packages installed into ignored `apps/api/node_modules`. |
| `npm --prefix apps/api run typecheck` | Passed. |
| `npm --prefix apps/api run build` | Passed; compiled output written under ignored `apps/api/dist`. |
| `node apps/api/dist/server.js` | Started successfully from compiled output. |
| `GET /healthz` | Passed with `status: ok`, `runtime_mode: fixture`, `campaign_count: 1`, and fixture `campaigns_dir`. |
| Server stderr | Empty. |
| Server stdout | Reported the local listening port. |

Observed `/healthz` payload:

```json
{
  "status": "ok",
  "environment": "development",
  "runtime_mode": "fixture",
  "campaign_count": 1,
  "data": {
    "campaigns_dir": "C:\\Users\\thorn\\.codex\\worktrees\\ebe8\\campaign_player_wiki\\tests\\fixtures\\sample_campaigns"
  }
}
```

## Packaging Refresh

A follow-up packaging proof run used copied fixture data and a disposable local
SQLite path under ignored `.task-temp` scratch space, then checked both the
operational health endpoint and one simple `/api/v1` route.

```powershell
$nodeDir = 'C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64'
$env:PATH = "$nodeDir;$env:PATH"
& "$nodeDir\node.exe" --version
& "$nodeDir\npm.cmd" --version
& "$nodeDir\npm.cmd" --prefix apps/api ci
& "$nodeDir\npm.cmd" --prefix apps/api run typecheck
& "$nodeDir\npm.cmd" --prefix apps/api run build

$proofRoot = '<repo>\.task-temp\ts-ops-local-packaging-proof'
$env:PORT = '<free localhost port>'
$env:NODE_ENV = 'test'
$env:PLAYER_WIKI_ENV = 'development'
$env:PLAYER_WIKI_RUNTIME = 'fixture'
$env:PLAYER_WIKI_BUILD_ID = 'ts-ops-local-packaging-proof'
$env:PLAYER_WIKI_GIT_SHA = 'local-proof'
$env:PLAYER_WIKI_GIT_DIRTY = 'false'
$env:CPW_CAMPAIGNS_DIR = "$proofRoot\campaigns"
$env:CPW_DB_PATH = "$proofRoot\player_wiki.sqlite3"
& "$nodeDir\node.exe" apps/api/dist/server.js
Invoke-RestMethod -Uri 'http://127.0.0.1:<free localhost port>/healthz'
Invoke-RestMethod -Uri 'http://127.0.0.1:<free localhost port>/api/v1/app'
```

The proof run copied `tests\fixtures\sample_campaigns` to
`.task-temp\ts-ops-local-packaging-proof\campaigns`, created an empty
`.task-temp\ts-ops-local-packaging-proof\player_wiki.sqlite3`, started the
compiled API on local port `50177`, and then stopped the Node process.

Observed result:

```json
{
  "port": 50177,
  "health_status": "ok",
  "health_environment": "development",
  "health_runtime_mode": "fixture",
  "health_campaign_count": 1,
  "health_campaigns_dir": "C:\\Users\\thorn\\.codex\\worktrees\\ebe8\\campaign_player_wiki\\.task-temp\\ts-ops-local-packaging-proof\\campaigns",
  "app_ok": true,
  "app_runtime": "fixture",
  "app_build_id": "ts-ops-local-packaging-proof",
  "app_git_sha": "local-proof",
  "app_git_dirty": false,
  "app_db_path": "C:\\Users\\thorn\\.codex\\worktrees\\ebe8\\campaign_player_wiki\\.task-temp\\ts-ops-local-packaging-proof\\player_wiki.sqlite3",
  "app_campaigns_dir": "C:\\Users\\thorn\\.codex\\worktrees\\ebe8\\campaign_player_wiki\\.task-temp\\ts-ops-local-packaging-proof\\campaigns"
}
```

An earlier harness attempt failed before server startup because the local
PowerShell/.NET runtime exposed a null `ProcessStartInfo.ArgumentList`; rerunning
the same proof with `ProcessStartInfo.Arguments` passed. That failure is
classified as a local harness issue, not a TypeScript API regression.

## Decision

- The TypeScript API has a working local install, build, compiled start, and
  fixture health-check path on Windows when the pinned Node/npm runtime is used.
- The copied-fixture refresh also proves `/api/v1/app` reflects the disposable
  DB path, copied campaigns path, and health metadata overrides.
- The proof depends on ignored local artifacts: `apps/api/node_modules`,
  `apps/api/dist`, and task-scoped local scratch space.
- This does not prove Docker/Fly packaging because the current tracked
  production image remains Flask/Gunicorn-only and excludes host-built
  `apps/api/dist` and `apps/api/node_modules` from the Docker context.

## Remaining Ops Gates

- Add a stable repo-local wrapper or documented command path so operators do
  not need to rediscover the pinned Node/npm runtime manually.
- Decide whether TypeScript cutover uses a TypeScript-only image, a sidecar, or
  a combined Flask-plus-TypeScript transition image.
- Prove Docker image build/start locally with mounted fixture paths and
  `/healthz`.
- Prove mounted `/data` paths, SQLite schema initialization or migration order,
  and rollback behavior against copied data before any user-approved deploy.
