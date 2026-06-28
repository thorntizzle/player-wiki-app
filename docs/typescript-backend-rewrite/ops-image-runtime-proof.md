# TypeScript API Image Runtime Proof

Last updated: 2026-06-28

Status: static no-deploy image path scaffold for `rewrite/ts-ops-packaging-runtime-proof`.

This proof does not approve deploy, PR, merge, production smoke, Fly sync, live
SQLite access, or cutover. Flask remains the production authority.

## Scope

- Branch: `rewrite/ts-ops-packaging-runtime-proof`
- Baseline: `rewrite/ts-phase2-integration` at `ffc21be`
- Packaging mode under proof: non-default local Docker target
  `ts-api-runtime-proof`
- No-deploy confirmation: no Fly commands, no live URLs, no live data, no
  production SQLite sync

## Implementation

- `Dockerfile` keeps the Python Flask/Gunicorn stage as the default final image.
- `Dockerfile` adds `ts-api-build`, which runs `npm ci`, compiles `apps/api`,
  and prunes dev dependencies inside Docker instead of relying on ignored
  host-built `apps/api/dist` or `apps/api/node_modules`.
- `Dockerfile` adds `ts-api-runtime-proof`, which copies the compiled API,
  pruned Node dependencies, `VERSION`, and the proof entrypoint into a Node
  runtime image.
- `deploy/ts-api-proof-entrypoint.sh` maps Fly-shaped env vars to the current
  TypeScript runtime names:
  - `PLAYER_WIKI_PORT` -> `PORT`
  - `PLAYER_WIKI_DB_PATH` -> `CPW_DB_PATH`
  - `PLAYER_WIKI_CAMPAIGNS_DIR` -> `CPW_CAMPAIGNS_DIR`
- `apps/api/tests/packaging-proof.mjs` statically verifies the Docker target,
  default Flask final stage, dockerignore hygiene, sanitized Fly placeholder,
  and proof entrypoint env mapping.

## Current Validation

- `npm --prefix apps/api run test:packaging-proof`: static target/env proof.
- Docker execution: not run. `docker` is not available on `PATH` in this
  worktree environment, so local image build/container smoke remains a
  tooling/environment blocker rather than a touched-code regression.

Follow-up validation on 2026-06-28 from `rewrite/ts-ops-packaging-proof` at
`5d886814593536dc08d17a2aa1236de668159597` confirmed the static proof still
passes after the phase 3 integration baseline. The same pass also proved the
compiled TypeScript API can start locally from `apps/api/dist/server.js` with
copied fixture campaigns and a disposable SQLite path under `.task-temp`,
answering `/healthz` and `/api/v1/app` with the expected local path metadata.
Docker remained unavailable on `PATH`, so this still is not an image-build
transcript.

Follow-up validation on 2026-06-28 from
`rewrite/ts-ops-packaging-runtime-proof-next` after resetting to integration
commit `61191fe17651309dfdad9f9c42c26cd6cc4c5be0` confirmed:

- `local.ps1 -Action ts-api-check -NodeRoot <pinned Codex Node bin>` passes,
  including npm install, route snapshot check, TypeScript typecheck/build,
  SQLite startup-posture test, and route-parity test.
- `apps/api` packaging static proof passes when the same pinned Node bin is on
  `PATH`.
- Docker is still unavailable on `PATH`, so no local image build or container
  boot transcript could be collected.
- A compiled-start proof against copied fixture campaigns and a scratch
  SQLite DB initialized with Flask `manage.py init-db` is blocked on this
  baseline: TypeScript startup preflight expects `sessions.session_token_hash`,
  while Flask initializes the table with `sessions.token_hash`. This is a
  fresh integration baseline blocker, not a touched-code regression from this
  docs-only ops packaging lane.

## Startup And Migration Boundary

The proof entrypoint creates only the parent directories for the configured
SQLite path and campaigns directory before starting Node. It deliberately does
not run Flask `manage.py init-db`, Drizzle migrations, or any schema dry-run.
TypeScript startup migration behavior remains a separate cutover gate.

## Decision

- Previous packaging label: `not packaged`
- New packaging label: `static image path scaffolded`
- Not reached: `local image builds`
- Blocker: Docker unavailable for local build/run proof in this worktree
- Additional blocker: latest integration compiled-start proof from a
  Flask-initialized scratch DB is blocked by the `sessions.token_hash` versus
  `sessions.session_token_hash` startup-preflight mismatch
- Remaining gates: local Docker build, local container boot with copied data,
  migration dry-run decision, rollback transcript, staging snapshot rehearsal,
  and full cutover smoke
