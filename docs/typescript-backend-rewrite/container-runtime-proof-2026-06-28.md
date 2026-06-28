# TypeScript API Container Runtime Proof - 2026-06-28

Status: passed for no-deploy compiled runtime and static packaging checks;
Docker image build/run skipped because Docker is unavailable in this worktree
environment

## Scope

- Branch: `rewrite/ts-container-runtime-proof`
- Base commit: `70dafde98f2a531a1d8282999147d23c5a14653e`
- Production authority: Flask remains production authority.
- Data boundary: tracked sanitized fixture campaigns plus a disposable SQLite DB
  initialized by Flask `manage.py init-db`.
- No-deploy confirmation: no Fly commands, no live URLs, no production app
  name, no live SQLite, no volume sync, no PR, no merge, and no deploy.
- Ownership: ops packaging/runtime evidence only. No character, Session,
  Combat, Publishing, Systems, or staging rehearsal runtime files were edited.

## Context Inspected

- `AGENTS.md`
- `docs/current-state/INDEX.md`
- `docs/current-state/workspace-boundaries.md`
- `docs/current-state/ops-deploy.md`
- `docs/typescript-backend-rewrite/README.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- Ops skill references for local runtime, local validation, Git close-out, and
  Fly/Docker config semantics.
- Runtime/package files: `apps/api/package.json`, `apps/api/package-lock.json`,
  `apps/api/tsconfig.json`, `frontend/package.json`,
  `frontend/package-lock.json`, `local.ps1`, `Dockerfile`, `.dockerignore`,
  `fly.toml`, `deploy/fly-entrypoint.sh`,
  `deploy/ts-api-proof-entrypoint.sh`,
  `apps/api/tests/container-runtime-proof.mjs`, and
  `apps/api/tests/packaging-proof.mjs`.

There is no repo-root `package.json`; the relevant TypeScript API package is
under `apps/api`.

## Proof Answer

Yes, the TypeScript API can currently build and start from the packaged,
container-like local runtime path using sanitized/local data only.
The repeatable proof command builds `apps/api`, initializes a disposable
Flask-schema SQLite DB, copies sanitized fixture campaigns, starts
`apps/api/dist/server.js` with production-shaped TypeScript environment
variables, and checks:

- `GET /healthz`
- `GET /api/v1/app`
- representative protected PNG asset serving from copied fixture content

The same wrapper attempts the non-default `ts-api-runtime-proof` Docker
build/run when Docker is available. In this worktree, Docker is absent, so the
image/container phase is a tooling/environment skip rather than a touched-code
regression.

## Commands And Results

| Command | Result | Classification |
| --- | --- | --- |
| `git status --short --branch` | Clean before proof; branch was `rewrite/ts-container-runtime-proof`. | Baseline check |
| `Get-Command docker -ErrorAction SilentlyContinue` | No Docker executable returned. | Tooling/environment |
| `powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check` | Passed: npm install, Flask route snapshot, TypeScript typecheck, build, SQLite startup-posture test, SQLite schema-command test, SQLite migration-proof test, and route parity. | Validation pass |
| `powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-container-proof` | Passed compiled runtime proof; Docker phase skipped with `spawnSync docker ENOENT`. | Validation pass with environment skip |
| `npm --prefix apps/api run test:packaging-proof` with only `npm.cmd` exposed | Failed because the package script invoked bare `node` and `node` was not on this shell PATH. | Tooling/environment |
| `npm --prefix apps/api run test:packaging-proof` with the resolved Node directory on `PATH` | Passed static Docker/Fly-shape checks. | Validation pass |

Both wrapper commands emitted an npm warning that `prebuild-install@7.1.3` is
deprecated. That warning did not fail install, build, or tests.

## Runtime Evidence

Sanitized highlights from the ignored proof summary:

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

Static packaging proof also confirmed:

- `Dockerfile` keeps the Flask/Python stage as the default final image.
- `Dockerfile` exposes a non-default `ts-api-runtime-proof` target.
- The proof target builds `apps/api` inside Docker and starts
  `deploy/ts-api-proof-entrypoint.sh`.
- `.dockerignore` excludes host-built API output, `node_modules`, and local
  proof scratch.
- `fly.toml` keeps the tracked placeholder app and Fly-shaped `/data` paths.
- The TypeScript proof entrypoint maps Fly-shaped env vars to `PORT`,
  `CPW_DB_PATH`, and `CPW_CAMPAIGNS_DIR` without running Flask schema init.

## What Remains Unproven

- Local Docker image build for `ts-api-runtime-proof`.
- Local Docker container boot and smoke against copied fixture data.
- Fly deploy/start behavior for TypeScript; no Fly commands were run.
- Whether a final cutover package is TypeScript-only, Flask plus TypeScript, a
  sidecar, or local-only Hono until cutover.
- Successful `/app-next/` serving if the TypeScript runtime becomes responsible
  for the frontend bundle; the current TypeScript proof target is API-only.
- Staging/live SQLite and campaign content behavior.
- Final migration/startup boundary beyond Flask `manage.py init-db` plus
  TypeScript startup preflight.
- Image-level rollback evidence from a TypeScript runtime back to Flask.

## App-Next Packaging Boundary Addendum

The `rewrite/ts-ops-app-next-packaging-proof` lane keeps Flask as the only
runtime with a proven frontend bundle path. Static packaging proof now verifies:

- the default Flask image builds `frontend/` inside Docker and copies
  Docker-built `frontend/dist` into the final Python image;
- host-built `frontend/dist` remains excluded from the Docker context;
- Fly config does not select the non-default `ts-api-runtime-proof` target;
- the TypeScript proof target and proof entrypoint are API-only and do not copy
  or serve `frontend/dist`;
- the TypeScript route manifest does not claim `/app-next` routes.

The compiled/runtime proof now also requests `GET /app-next/` and expects the
current `404` response. That is deliberate evidence of the open cutover gate,
not frontend-readiness evidence. If a future TypeScript package owns the
frontend bundle, that response check must change alongside a runtime
implementation, Docker copy/build assertions, and updated cutover docs.

## Orchestrator Rerun

Rerun this exact no-deploy proof from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-container-proof
```

Keep `powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check`
as the broader TypeScript API gate before integration.

When Docker is available, the same `ts-api-container-proof` wrapper should
collect the local image build and container boot transcript. If a direct Docker
command is needed for diagnosis, use the non-default proof target only:

```powershell
docker build --pull=false --target ts-api-runtime-proof -t campaign-player-wiki-ts-proof:local .
```

Do not run Fly commands, use live data, or treat this proof as deploy/cutover
approval without the remaining gates above.
