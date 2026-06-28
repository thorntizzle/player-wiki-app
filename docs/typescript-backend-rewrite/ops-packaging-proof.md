# TypeScript Backend Ops Packaging Proof

Last updated: 2026-06-28

Status: no-deploy packaging readiness artifact for future TypeScript backend cutover

## Purpose

This document defines the no-deploy packaging proof required before the
TypeScript backend can be considered ready for user-approved staging, deploy, or
cutover steps. It is a readiness artifact only. It does not approve a PR, merge,
Fly deploy, production smoke, live SQLite sync, or live data mutation.

Flask remains the production authority until TypeScript passes route parity,
copied-data or staging-snapshot rehearsal, packaging proof, rollback proof, and a
full cutover rehearsal.

## Current Production Packaging Authority

The tracked production packaging is currently Flask/Python:

- `Dockerfile` builds `frontend/` in a Node build stage, then creates a
  `python:3.12-slim` runtime image.
- The final image installs `requirements-prod.txt`, copies the repo snapshot,
  copies only Docker-built `frontend/dist`, normalizes
  `deploy/fly-entrypoint.sh`, and starts that shell entrypoint.
- `deploy/fly-entrypoint.sh` initializes the SQLite schema with
  `python manage.py init-db`, then executes Gunicorn against `wsgi:app`.
- `fly.toml` points Fly traffic at internal port `8080`, mounts `/data`, and
  checks `/healthz`.
- `local.ps1 -Action deploy-fly` is the current deploy wrapper and refuses the
  sample Fly app unless a real app is supplied locally.

The TypeScript API is not production-packaged by the default image:

- The default final image is Python-based and does not retain the Node
  build-stage runtime.
- `apps/api/package.json` defines `build`, `typecheck`, `start`, `smoke`,
  packaging-proof, and route-parity scripts, but the default Flask image does
  not run `npm ci`, `npm run build`, or `npm run start` in `apps/api`.
- `.dockerignore` excludes `apps/**/dist` and `apps/**/node_modules`, so a
  host-built TypeScript API bundle and dependencies are not sent in the Docker
  context.
- `deploy/fly-entrypoint.sh` starts only Gunicorn. It has no TypeScript API
  process, sidecar, proxy, or cutover start path.
- The Dockerfile now has a non-default `ts-api-runtime-proof` target that builds
  `apps/api` inside Docker and starts `deploy/ts-api-proof-entrypoint.sh`.
  This target is for local no-deploy proof work only; it is not selected by the
  sanitized Fly config or the default Docker build.

Current production packaging therefore proves the Flask production image and
Gen2 frontend bundle path only. The TypeScript proof target statically proves a
build/start path exists, but because Docker is unavailable in this worktree
environment it does not yet prove a locally built image, a combined
Flask-plus-TypeScript image, a TypeScript sidecar, or a TypeScript-only cutover
image.

Follow-up local runtime evidence is recorded in
`docs/typescript-backend-rewrite/ops-local-runtime-evidence.md`. That proof shows
the integrated TypeScript API can install, build, start from `apps/api/dist`, and
answer `/healthz` plus `/api/v1/app` against copied fixture/local paths on
Windows with the pinned Node/npm runtime. It still does not prove Docker/Fly
packaging or authorize deploy.

## Inspected Files

- `Dockerfile`
- `.dockerignore`
- `fly.toml`
- `deploy/fly-entrypoint.sh`
- `deploy/ts-api-proof-entrypoint.sh`
- `local.ps1`
- `ops.py`
- `apps/api/package.json`
- `apps/api/tests/packaging-proof.mjs`
- `docs/current-state/ops-deploy.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- `docs/typescript-backend-rewrite/staging-rehearsal-harness.md`
- `docs/typescript-backend-rewrite/ops-image-runtime-proof.md`

Ignored `.local` roadmap files are absent in this worktree, so this proof is
based on tracked packaging files and tracked rewrite docs only.

## Allowed Local Evidence

Allowed before explicit deployment approval:

- Read packaging files and inspect Git metadata.
- Run `git ls-files --eol Dockerfile .dockerignore fly.toml
  deploy/fly-entrypoint.sh local.ps1 ops.py apps/api/package.json`.
- Run TypeScript API local build/typecheck/test commands when the local Node
  dependency state supports them:
  - `npm --prefix apps/api run typecheck`
  - `npm --prefix apps/api run build`
  - `npm --prefix apps/api test`
- Run the repo wrapper gate when validating the local TypeScript API route
  parity path on Windows without relying on global npm:
  - `powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check`
- Run static Docker context hygiene checks that do not contact Fly.
- Run `npm --prefix apps/api run test:packaging-proof` to verify the
  non-default TypeScript image target and proof entrypoint wiring.
- Run a local Docker image build only when Docker is available and the target is
  explicitly local, for example `docker build --pull=false -t
  campaign-player-wiki-ts-proof:local --target ts-api-runtime-proof .`.
- Run a local container only against disposable copied data under `.task-temp/`.
- Probe only local URLs such as `http://127.0.0.1:<port>/healthz`.

Allowed evidence must use local, disposable, or fixture data. It must not depend
on the real Fly app, live `/healthz`, or production volumes.

## Forbidden Until Explicit Approval

Do not run these in this proof lane:

- `fly deploy`
- `fly status`
- `fly machine list`
- `fly machine status`
- `fly logs`
- live `/healthz` or public production smoke checks
- `local.ps1 -Action deploy-fly`
- `local.ps1 -Action sync-fly`
- `ops.py pull-fly-db`
- `ops.py sync-from-fly`
- destructive restore commands
- any command that uses the real Fly app name, a live Fly machine id, or a live
  production URL

## No-Deploy Evidence Checklist

### Local TypeScript API Build

Collect:

- `apps/api/package.json` script list.
- `npm --prefix apps/api run typecheck` result.
- `npm --prefix apps/api run build` result.
- `npm --prefix apps/api test` or narrower route/smoke result.
- Whether `apps/api/dist/server.js` is produced locally.

Current gap:

- The app has local TypeScript API scripts, a durable `local.ps1 -Action
  ts-api-check` validation wrapper, and a non-default Docker proof target, but
  those scripts are not wired into the production Flask image, Fly process, or
  `local.ps1` deploy path.

Current local evidence:

- Pinned Node `v22.12.0` and npm `10.9.0` can run `npm --prefix apps/api ci`,
  `npm --prefix apps/api run typecheck`, and `npm --prefix apps/api run build`.
- `local.ps1 -Action ts-api-check` resolves Node/npm from explicit parameters,
  `CPW_NODE_*` environment variables, repo-local ignored runtimes,
  `$HOME`-relative Codex/pinned runtime locations, or `PATH`; the wrapper runs
  `npm ci`, route snapshot validation, API typecheck, API build, and
  `test:route-parity` without requiring global npm.
- `apps/api/dist/server.js` starts locally with copied fixture campaigns under
  `.task-temp` and a disposable SQLite path.
- Local `GET /healthz` returns `status: ok`, `runtime_mode: fixture`, and
  `campaign_count: 1`.
- Local `GET /api/v1/app` returns `ok: true` and reflects the disposable
  `CPW_DB_PATH`, `CPW_CAMPAIGNS_DIR`, and health metadata overrides.
- `npm --prefix apps/api run test:packaging-proof` statically verifies that the
  Dockerfile keeps Flask as the default final image, exposes a non-default
  `ts-api-runtime-proof` target, builds `apps/api` inside Docker, ignores
  host-built API output/dependencies from the Docker context, and maps Fly-style
  `PLAYER_WIKI_*` env vars to the TypeScript API's `CPW_*` runtime env vars.

### Docker Context Hygiene

Collect:

- `.dockerignore` review confirming exclusion of `.local`, SQLite files,
  campaign mirrors, `campaigns`, local frontend output, `apps/**/node_modules`,
  `apps/**/dist`, tests, docs, and scratch paths.
- Confirmation that a future TypeScript build plan does not rely on ignored
  host-built `apps/api/dist` or `apps/api/node_modules`.
- A local-only Docker build transcript when available.

Current gap:

- `.dockerignore` correctly blocks host-built API output and dependencies.
- The `ts-api-runtime-proof` target now builds `apps/api` inside Docker and
  copies only the pruned production dependency tree plus compiled `dist`, but
  Docker is unavailable in this worktree environment so the image build itself
  has not run.

### Entry Point And Line Endings

Collect:

- `git ls-files --eol deploy/fly-entrypoint.sh Dockerfile .dockerignore`.
- Confirmation that `.gitattributes` keeps `*.sh text eol=lf`.
- Confirmation that the Dockerfile still strips CRLF from
  `/app/deploy/fly-entrypoint.sh` before `chmod +x`.

Current evidence:

- `deploy/fly-entrypoint.sh` is tracked with `i/lf w/lf attr/text eol=lf`.
- `.gitattributes` contains `*.sh text eol=lf`.
- Dockerfile includes `sed -i 's/\r$//' /app/deploy/fly-entrypoint.sh`.
- `deploy/ts-api-proof-entrypoint.sh` is also covered by `*.sh text eol=lf`,
  and the `ts-api-runtime-proof` target strips CRLF before `chmod +x`.

### Fly Config Sanitization

Collect:

- `fly.toml` app name.
- Volume mount path.
- Internal port and health check path.
- Environment variables.
- Confirmation that no real Fly app identity is committed.

Current evidence:

- `fly.toml` uses placeholder app `campaign-player-wiki-example`.
- `/data` is the mounted volume.
- `PLAYER_WIKI_DB_PATH` is `/data/player_wiki.sqlite3`.
- `PLAYER_WIKI_CAMPAIGNS_DIR` is `/data/campaigns`.
- Health check path is `/healthz`.

Current gap:

- No TypeScript-specific runtime variables, process names, or health checks are
  defined in Fly config. The TypeScript proof target relies on Docker
  `--target ts-api-runtime-proof` and is intentionally not selected by
  `fly.toml`.

### Startup And Schema Behavior

Collect:

- Startup command used by the image.
- Schema/migration command and target DB path.
- Whether the startup command handles copied-data/staging data without mutating
  live paths.
- Whether TypeScript migrations are dry-run capable before startup.

Current evidence:

- Flask startup runs `python manage.py init-db` against the active
  `PLAYER_WIKI_DB_PATH`, then starts Gunicorn.

Current gap:

- There is no TypeScript startup migration command, Drizzle migration command,
  or TypeScript schema dry-run wired into the production image.
- There is no decision yet on whether TypeScript uses the existing Flask
  `manage.py init-db`, a Drizzle migration path, or a transitional dual check.
- `deploy/ts-api-proof-entrypoint.sh` deliberately creates only the parent
  directories for copied local paths, then starts Node. It does not claim schema
  initialization or migration readiness.

### Runtime Environment

Collect:

- Required Flask env vars.
- Required TypeScript env vars.
- Port ownership and routing plan.
- Process model: TypeScript-only, Flask-plus-TypeScript, sidecar, or reverse
  proxy.

Current evidence:

- Flask owns `PLAYER_WIKI_*` runtime env vars and port `8080`.
- The TypeScript API local slice reads `CPW_DB_PATH` and `CPW_CAMPAIGNS_DIR` in
  local rehearsal docs.
- The proof-only entrypoint maps `PLAYER_WIKI_PORT` to `PORT`,
  `PLAYER_WIKI_DB_PATH` to `CPW_DB_PATH`, and `PLAYER_WIKI_CAMPAIGNS_DIR` to
  `CPW_CAMPAIGNS_DIR` when the TypeScript-specific env vars are not supplied.

Current gaps:

- Port ownership between Gunicorn and Hono is undecided.
- No process supervisor or proxy plan exists for running both Flask and
  TypeScript in one image.

### Health And Smoke Expectations

Collect locally before deploy approval:

- TypeScript `/healthz` response from a local process.
- Flask `/healthz` response from the current local production-style image if
  Flask remains in the image.
- Representative local `/app-next/` response when frontend bundle is included.
- Representative protected asset content type from copied data.

Current gap:

- Existing Fly health checks target Flask `/healthz`; no staged TypeScript image
  health transcript exists.

### Rollback Image And Data Boundaries

Collect:

- Last known-good Flask commit or image id.
- Pre-cutover SQLite backup path.
- Pre-cutover campaign content backup path.
- Procedure for returning the runtime to Flask.
- Data-delta decision for any writes accepted by TypeScript before rollback.

Current gap:

- Rollback is required by the charter. `rollback-cutover-runbook.md` and the
  staging harness `rollback-cutover` guide now define the no-live transcript
  fields, but an image-level TypeScript rollback transcript has not been
  completed.

## Packaging Proof Transcript Template

```markdown
# Packaging Proof Transcript: <id>

## Scope
- Branch/commit:
- Packaging mode under proof:
- No-deploy confirmation:

## Static File Evidence
- Dockerfile summary:
- `.dockerignore` summary:
- `fly.toml` sanitization:
- entrypoint EOL:
- local wrapper/deploy path:

## TypeScript API Local Build
- install command:
- typecheck command/result:
- build command/result:
- test/smoke command/result:
- produced artifacts:

## Local Image Build
- command:
- image tag/id:
- context exclusions observed:
- result:

## Local Boot With Copied Data
- copied DB:
- copied campaigns dir:
- environment:
- command:
- health response:
- app-next response:
- representative asset response:

## Startup/Migration
- schema command:
- migration dry-run:
- target DB:
- result:

## Rollback
- Flask commit/image:
- backup archive:
- restore rehearsal reference:
- data-delta decision:

## Decision
- Previous label:
- New label:
- blockers:
- follow-up lanes:
```

## Decision Gates

| Label | Meaning | Required evidence |
| --- | --- | --- |
| `not packaged` | TypeScript API can run locally but is not part of a production-like image. | Current state. Local `apps/api` scripts may pass, but Docker/Fly startup does not include TypeScript. |
| `static image path scaffolded` | A non-default image target and proof entrypoint exist, and static checks verify the build/start/env-mapping shape without running Docker. | `npm --prefix apps/api run test:packaging-proof`, Docker context hygiene review, and explicit documentation that default Flask packaging remains unchanged. |
| `local image builds` | A local-only image includes the intended TypeScript runtime and builds without live dependencies. | Local Docker build transcript, Docker context hygiene, TypeScript build inside image or copied deliberate artifact, no private/live identifiers. |
| `staging image boots with copied data` | The image boots locally or in a non-live staging target against copied data and passes local health/smoke checks. | Copied SQLite/content paths, schema/migration proof, `/healthz`, `/app-next/` if applicable, protected asset check, no live paths. |
| `user-approved deploy ready` | The image and rollback plan are ready for an explicitly approved deploy step. | Staging snapshot rehearsal, rollback transcript, final route/data parity gates, clean committed state, explicit user approval. |

Any failed build, live-path dependency, missing rollback path, or unproven data
mutation keeps the label at the previous stage.

## Current Concrete Gaps

- The default production image is Flask/Gunicorn only.
- The default final Docker stage does not include Node, API dependencies, or
  `apps/api/dist`.
- The Dockerfile builds and starts `apps/api` only in the non-default
  `ts-api-runtime-proof` target.
- The entrypoint has no TypeScript process, process supervisor, proxy, or
  TypeScript-only cutover command.
- Fly config has no TypeScript-specific process, port, or health check.
- TypeScript env names are mapped only in the proof entrypoint, not in the
  default Flask entrypoint or Fly process model.
- Startup schema behavior is still Flask `manage.py init-db`; TypeScript
  migration dry-run/startup behavior is unproven.
- No local Docker build transcript exists for a TypeScript API runtime because
  Docker was unavailable in the current worktree environment.
- A no-live rollback/cutover transcript scaffold exists, but no image-level
  rollback transcript has been completed for returning from TypeScript to the
  last known-good Flask image.

## Next Packaging Work

1. Decide the packaging shape: TypeScript-only replacement, temporary
   Flask-plus-TypeScript image, separate sidecar, or local-only Hono proof until
   cutover.
2. Run the non-live Docker proof lane with
   `docker build --pull=false --target ts-api-runtime-proof -t
   campaign-player-wiki-ts-proof:local .` when Docker is available, then boot
   it only against copied data.
3. Define the migration/startup boundary between Flask `manage.py init-db` and
   the TypeScript/Drizzle path.
4. Complete the rollback/cutover transcript with image and data boundaries
   before any deploy request.
