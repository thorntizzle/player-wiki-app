# TypeScript Backend Rewrite

Last updated: 2026-06-25

Status: active rewrite planning and implementation track

This folder tracks the deliberate TypeScript backend rewrite path for Campaign Player Wiki. It is separate from incremental Flask refactor work. The goal is a production-capable TypeScript backend that preserves the current product contract, data safety boundaries, local/Fly operations, and rollback path before replacing Flask.

## Source Of Truth

- `charter.md`: scope, freeze rules, cutover gates, rollback requirement, and branch/spec ownership.
- `parity-inventory.md`: current route, API, data, command, and policy inventory that TypeScript must preserve.
- `route-snapshots.md`: executable route snapshot artifact companion review notes.
- `route-snapshots.json`: tracked executable snapshot from
  `scripts/route_snapshots.py` used by parity checks.
- `typescript-route-seed.json`: provisional route seed for initial TypeScript handlers.
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: local active task queue for the rewrite track.
- `docs/current-state/INDEX.md`: current product contract index. Use it to confirm present behavior before porting any workflow.
- `docs/api-v1.md`: current JSON API contract.

Route parity check command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

### Stack Evidence

- `stack-spike.md`: architecture decision record for the TypeScript backend stack evaluation and proof checklist.
- `sqlite-migration-spike.md`: migration-layer proof for Drizzle `generate`/`migrate`, runtime probes, and driver comparison.
- `read-only-compatibility-slice.md`: evidence for the fixture-backed read-only API compatibility slice.

## Working Rules

- Python/Flask remains the production authority until TypeScript passes parity gates and a cutover rehearsal.
- TypeScript work starts read-only and fixture-backed before any production write path is added.
- Domain, service, persistence, content, auth, Systems, character, session, and combat logic must not live in React route components.
- Experimental spikes stay in `.task-temp` or an isolated approved workspace until a workspace layout decision is recorded.
- Any Python behavior that ships during the rewrite must either be added to the parity inventory or recorded as an explicit deferred exception.

## Initial Phase Order

1. Rewrite charter and tracked spec home.
2. Product contract and parity inventory.
3. Stack and workspace spike with a written decision record.
4. Framework-free domain and policy packages.
5. Compatibility persistence and migration reads.
6. Auth, API contracts, read-only Gen2 slices, then controlled write paths.

## Slice Progress

- `apps/api` exists and now serves:
  - `GET /healthz`
  - `GET /api/v1/app`
  - `GET /api/v1/campaigns`
  - `GET /api/v1/campaigns/:campaignSlug`
  - `GET /api/v1/campaigns/:campaignSlug/wiki`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/sections/:sectionSlug`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/pages/*`
  - `GET /api/v1/campaigns/:campaignSlug/session`
  - `GET /api/v1/campaigns/:campaignSlug/content/config`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages/*`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets/*`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
- Campaign detail uses fixture-backed reads from `tests/fixtures/sample_campaigns` by default and supports
  `CPW_CAMPAIGNS_DIR` override.
- Read-only auth/permission metadata for the fixture mode is explicit in the response.
- `apps/api/src/routes.ts` is the implemented-route manifest for the tracked slice.
- `apps/api/tests/route-parity.mjs` checks implemented TypeScript routes against the Python route snapshot and active route seed.

Production cutover is not part of the early phases. It requires backup, migration dry-run, browser rehearsal, production smoke checks, and an approved rollback window.
