# SQLite Migration Hook Proof: 2026-06-28

Status: tracked TypeScript explicit migration-hook proof implemented; production migration authority unchanged

## Scope

- Lane branch: `rewrite/ts-sqlite-migration-hook-proof`
- Baseline: `origin/rewrite/ts-phase3-integration` at `7d005ff`
- Data used: disposable SQLite databases created under test temp directories
- No owner checkout, vault, Fly command, staging/live SQLite, production volume, tracked campaign content, or live API write was used.

## Command

Dry run:

```powershell
npm --prefix apps/api run sqlite:migrate-proof -- --db "<disposable-or-copied-sqlite-path>"
```

Explicit ledger apply:

```powershell
npm --prefix apps/api run sqlite:migrate-proof -- --db "<disposable-or-copied-sqlite-path>" --apply
```

The command intentionally ignores `CPW_DB_PATH`; operators must pass an explicit
`--db` path. It is not called by `apps/api/src/server.ts` or any API startup path.

## Safety Boundary

The command refuses:

- missing database paths;
- obvious live-ish `/data/player_wiki.sqlite3` targets;
- paths outside disposable temp roots, repo `.task-temp`, or repo `.local/tmp`
  unless `--allow-copied-db` is explicitly provided for an operator-approved
  copied database;
- databases that do not already satisfy the current Flask-initialized schema
  preflight.

When `--apply` is provided against a safe current-schema database, the command
creates only `__cpw_typescript_migration_ledger`. There are no allowlisted
TypeScript schema deltas in this slice, so successful reports show:

```json
{
  "migrations": {
    "allowlisted": [],
    "applied": [],
    "skipped": []
  }
}
```

## Implementation

- `apps/api/src/sqliteMigrationProof.ts` owns the explicit CLI and ledger proof.
- `apps/api/package.json` exposes:
  - `sqlite:migrate-proof`
  - `test:sqlite-migrate-proof`
- `apps/api/tests/sqlite-migrate-proof.mjs` creates disposable SQLite files,
  builds a synthetic current schema from `CURRENT_SQLITE_SCHEMA_REQUIREMENTS`,
  proves dry-run non-mutation, proves ledger creation, proves idempotent re-run,
  and proves refusal for partial-schema, missing, and live-ish targets.
- `local.ps1 -Action ts-api-check` now runs the migration proof test after the
  read-only schema command test and before route parity.

## Decision

This closes the narrow blocker for a tracked TypeScript-side additive migration
command shape or equivalent hook proof. It does not close staging or production
migration readiness:

- Flask `manage.py init-db` remains the production schema initializer.
- TypeScript API startup still does not run migrations.
- No real TypeScript schema delta is claimed in this slice.
- Staging-equivalent migration rehearsal, failed/partial migration rollback,
  and post-migration TypeScript startup/read smoke remain required before any
  production cutover decision.
