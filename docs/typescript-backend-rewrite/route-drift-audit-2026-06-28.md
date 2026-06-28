# TypeScript Route Drift Audit - 2026-06-28

Status: no-runtime route/API drift audit evidence

This pass advanced the `API route inventory stays in lockstep` and `Freeze and
dual-maintenance` readiness gates without editing runtime handlers, live data,
Fly configuration, SQLite files, campaign content, or character presenter files.

## Scope

- Branch: `rewrite/ts-route-drift-audit`
- Starting baseline: `774db30a59d4c21805f0bdd4e21c12d5dd1eb6bf`
  (`origin/rewrite/ts-phase3-integration` at lane start).
- Integrated baseline before final validation:
  `35ebf638ef9e7d9a6cbd9de96c32c3ed7844303b`.
- Local roadmaps: `.local/roadmaps/typescript-backend-rewrite-roadmap.md` and
  `.local/roadmaps/ops-backlog.md` were not present in this worktree.

## Commands Run

| Command | Result | Classification | Notes |
| --- | --- | --- | --- |
| `git fetch origin --prune` | Pass | Setup | Fetched origin before creating the lane branch. |
| `git switch -c rewrite/ts-route-drift-audit origin/rewrite/ts-phase3-integration` | Pass | Setup | Created the audit lane from integration head `774db30a59d4c21805f0bdd4e21c12d5dd1eb6bf`. |
| `git stash push --include-untracked`, `git fetch origin --prune`, `git merge --ff-only origin/rewrite/ts-phase3-integration`, `git stash pop` | Pass | Integration | Protected audit edits, fast-forwarded to integration head `35ebf638ef9e7d9a6cbd9de96c32c3ed7844303b`, and reapplied without conflicts. |
| `<shared-venv-python> .\scripts\route_snapshots.py --check` | Pass | Route snapshot | Tracked `route-snapshots.json` matched current Flask route declarations. |
| `npm --prefix apps/api run test:route-parity` | Fail | Tooling/environment | Bare `npm` was not on this PowerShell PATH. No route drift was reported. |
| `.\local.ps1 -Action ts-api-check -NodeRoot <bundled-node-root> -SkipTsApiInstall` | Fail | Tooling/environment | Bundled Node/npm resolved, but local TypeScript dependencies were missing, so `tsc` was unavailable. |
| `.\local.ps1 -Action ts-api-check -NodeRoot <bundled-node-root>` | Pass | Validation | Installed `apps/api` dependencies with `npm ci`, then passed snapshot check, typecheck, build, SQLite startup-posture, and route-parity. |
| `<bundled-npm.cmd> --prefix apps/api run test:route-parity` with bundled Node on PATH | Pass | Route parity | Direct route-parity validation after dependency install and seed alignment. |
| Static comparison of `route-snapshots.json`, `typescript-route-seed.json`, `apps/api/dist/routes.js`, and `docs/api-v1.md` | Pass after docs fix | Route/API drift audit | Found and fixed a seed-only browser JSON compatibility drift; no remaining snapshot, seed, manifest, dynamic missing-resource, or API docs route-list drift. |
| `git diff --check` | Pass | Hygiene | No whitespace errors in touched tracked files. |

## Route Counts

Source snapshots:

- `/api/v1` Flask snapshot: 135 declarations: 46 `GET`, 39 `POST`,
  21 `PATCH`, 11 `PUT`, and 18 `DELETE`.
- Expanded Flask browser/compatibility snapshot: 145 entries: 56 `GET` and
  89 `POST`.

TypeScript seed and manifest after this audit:

- `typescript-route-seed.json`: 148 total routes.
- Implemented seed entries: 143.
- Deferred scratch-proof entries: 5.
- `apps/api/src/routes.ts` implemented manifest: 143 routes.
- Manifest snapshot families: 135 `api_v1` routes and 8 Flask
  browser/compatibility routes.
- Manifest methods: 52 `GET`, 39 `POST`, 23 `PATCH`, 11 `PUT`, and
  18 `DELETE`.

## Drift Findings

The route snapshot was already current with Flask source declarations, and
`docs/api-v1.md` had no route-list drift after normalizing typed/path
placeholders and the documented `?q=...` query example.

The audit did find a seed-only drift: `apps/api/src/routes.ts` implemented four
browser JSON compatibility routes that were present in the Flask snapshot but
missing from `typescript-route-seed.json`:

- `GET /campaigns/<campaign_slug>/global-search`
- `GET /campaigns/<campaign_slug>/global-search/preview`
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/search`
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/preview`

This was docs/fixture drift, not runtime/API behavior drift. The fix in this
lane adds those four routes to the seed as `implemented_fixture_readonly`
`browser_json_compatibility` entries backed by the Flask snapshot.

Post-fix static comparison showed:

- No implemented seed entries missing from the TypeScript route manifest.
- No TypeScript route manifest entries missing from the implemented seed.
- No TypeScript route manifest entries missing from the current snapshot family.
- No dynamic TypeScript routes missing a `missingResource` check.
- No `docs/api-v1.md` route-list entries missing from the snapshot.
- No snapshot `/api/v1` route entries missing from `docs/api-v1.md`.

## Deferred Scratch Treatment

The five `deferred_scratch_proof` seed entries remain intentionally non-blocking
future candidates and were not promoted:

- `GET /api/v1/session/login`
- `POST /api/v1/session/login`
- `GET /api/v1/session/me`
- `POST /api/v1/upload`
- `GET /api/v1/notes/<id>`

They still have no current Flask parity snapshot or approved cutover contract.
They should stay outside initial cutover scope unless a later architecture
decision explicitly promotes session-cookie auth, a generic upload API, or a
generic note-resource API.

## Remaining Follow-Up Lanes

- Final freeze pass: rerun the same snapshot, route-parity, static seed/manifest,
  and API-doc comparison after each integration-branch advance and immediately
  before any user-approved PR, merge, deploy, or cutover rehearsal.
- Route-family semantic parity: continue family-owned golden Flask-vs-TypeScript
  tests for behavior that route inventory checks cannot prove, especially
  character presenter/detail, full DND create/edit/advancement, image/portrait
  policy, and write-family staging snapshot gates.
- Browser compatibility decision: keep the four browser JSON compatibility
  routes as non-/api/v1 Flask-backed cutover targets unless the frontend moves to
  approved `/api/v1` replacements first.

## Non-Goals Observed

No deploy, Fly command, live API write, SQLite sync, production data access,
vault copy, PR, merge, or runtime handler edit was performed.
