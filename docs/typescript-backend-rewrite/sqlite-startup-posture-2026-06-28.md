# SQLite Startup Posture: 2026-06-28

Status: transitional TypeScript startup/schema posture implemented; full TypeScript migration command still pending

## Scope

- Lane branch: `rewrite/ts-ops-sqlite-startup-posture`
- Baseline: `origin/rewrite/ts-phase3-integration` at `0649d84`
- Data used: synthetic/disposable SQLite fixtures only
- No owner checkout, vault, Fly command, staging/live SQLite, production volume, tracked campaign content, or live API write was used.

## Decision

The TypeScript API now has an explicit transitional SQLite startup posture:

- Flask remains the production schema authority.
- `manage.py init-db` remains the initializer that creates or updates SQLite schema before TypeScript API startup.
- TypeScript startup does not run migrations yet. Instead, it fails fast if the configured SQLite database is missing the current Flask-initialized schema.
- The startup failure message points operators back to running Flask `manage.py init-db` against the same database before starting the TypeScript API.

This narrows the blocker from `sqlite-migration-dry-run-2026-06-28.md` without claiming a full TypeScript/Drizzle migration layer.

## Implementation

- `apps/api/src/sqlite.ts` now owns shared SQLite opening and startup preflight behavior.
- Runtime SQLite call sites in API modules outside the active Wizard character-authoring lane use `openSqliteDatabase(...)`.
- The helper applies intentional connection PRAGMAs:
  - `foreign_keys = ON`
  - `busy_timeout = 30000`
  - `journal_mode = WAL` for writable opens
  - `synchronous = NORMAL` for writable opens
- `apps/api/src/server.ts` runs `assertSqliteStartupSchema(config.dbPath)` before serving.
- The preflight checks the 34 current Flask SQLite tables, selected required columns, and current indexes.
- `local.ps1 -Action ts-api-check` now runs `npm --prefix apps/api run test:sqlite-startup-posture` after build and before route parity.

## Ownership Note

`apps/api/src/content/characterAuthoring.ts` still opens `better-sqlite3` directly because the Wizard create parity lane owns active edits there. Adopt the shared helper in that file after the Wizard lane lands.

## Remaining Blockers

- No tracked TypeScript/Drizzle migration command exists yet.
- No TypeScript startup hook runs additive migrations.
- Staging or production write readiness still requires a user-approved staging-equivalent migration rehearsal against realistic data.
- Failed or partial migration rollback remains a cutover rehearsal topic, not closed by this startup preflight.
