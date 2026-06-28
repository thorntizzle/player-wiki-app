# SQLite Migration Readiness Inventory: 2026-06-28

Status: inventory proof completed; no real TypeScript schema deltas exist yet

## Scope

- Lane branch: `rewrite/ts-sqlite-migration-readiness-inventory`
- Baseline: `origin/rewrite/ts-phase3-integration` at `016ed0421673a735676e0824bb66b0fffda401d0`
- Data used: disposable SQLite database initialized through Flask `manage.py init-db`
- No owner checkout, vault, Fly command, staging/live SQLite, production volume, tracked `campaigns/<slug>/` content, or live API write was used.

This inventory advances the migration posture gate by making the current schema
requirements and no-op TypeScript migration proof explicit. It does not claim
that TypeScript can own production schema changes, staging writes, or cutover.

## Sources Reviewed

- `docs/current-state/INDEX.md`
- `docs/current-state/workspace-boundaries.md`
- `docs/current-state/ops-deploy.md`
- `docs/typescript-backend-rewrite/README.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- `docs/typescript-backend-rewrite/sqlite-migration-spike.md`
- `docs/typescript-backend-rewrite/sqlite-migration-dry-run-2026-06-28.md`
- `docs/typescript-backend-rewrite/sqlite-startup-posture-2026-06-28.md`
- `docs/typescript-backend-rewrite/sqlite-schema-command-proof-2026-06-28.md`
- `docs/typescript-backend-rewrite/sqlite-migration-hook-proof-2026-06-28.md`
- `apps/api/src/sqlite.ts`
- `apps/api/src/sqliteSchemaCheck.ts`
- `apps/api/src/sqliteMigrationProof.ts`
- `apps/api/tests/sqlite-startup-posture.mjs`
- `apps/api/tests/sqlite-schema-check.mjs`
- `apps/api/tests/sqlite-migrate-proof.mjs`
- `local.ps1`
- `manage.py`
- `player_wiki/db.py`

## Current Inventory

The current TypeScript startup/schema requirement list lives in
`CURRENT_SQLITE_SCHEMA_REQUIREMENTS` in `apps/api/src/sqlite.ts`.

Required current-schema inventory:

| Required item family | Count |
| --- | ---: |
| Tables | 34 |
| Selected columns | 205 |
| Named indexes | 21 |

This is a TypeScript startup/readiness requirement inventory, not a claim that
TypeScript owns the full SQL definition. Flask `manage.py init-db` remains the
production schema authority and may define additional column details, checks,
foreign keys, defaults, and autoindexes beyond this TypeScript preflight list.

## Flask Scratch Comparison

Focused proof added in this lane:

```powershell
npm --prefix apps/api run test:sqlite-migration-readiness-inventory
```

The test creates a disposable temp root, runs Flask `manage.py init-db` with
`PLAYER_WIKI_DB_PATH`, `PLAYER_WIKI_CAMPAIGNS_DIR`, and `PLAYER_WIKI_TEMP_DIR`
pointed at that disposable root, and then inspects the resulting database with
the TypeScript schema helper.

Observed proof output:

```json
{
  "required": {
    "tables": 34,
    "columns": 205,
    "indexes": 21
  },
  "present": {
    "tables": 34,
    "columns": 205,
    "indexes": 21
  },
  "missing": [],
  "allowlistedTypeScriptDeltas": [],
  "appliedTypeScriptDeltas": []
}
```

Result: a Flask-initialized scratch database satisfies the complete current
TypeScript required schema inventory. No missing required tables, selected
columns, or named indexes were found.

The same proof verifies the read-only TypeScript connection requirements that
matter for the startup/schema check:

- `PRAGMA foreign_keys = 1`
- `PRAGMA busy_timeout = 30000`

Writable TypeScript opens still apply the transitional policy recorded in the
earlier startup-posture evidence: `journal_mode=WAL` and `synchronous=NORMAL`.

## TypeScript Delta Status

The migration proof command still has no real schema deltas:

```powershell
npm --prefix apps/api run sqlite:migrate-proof -- --db "<disposable-sqlite-path>"
```

Against the Flask-initialized scratch database, the dry run reported:

- `migrations.allowlisted`: `[]`
- `migrations.applied`: `[]`
- `migrations.skipped`: `[]`
- ledger created: `false`

So the honest current posture is:

- TypeScript can check that the Flask-current schema is present.
- TypeScript has a guarded explicit migration-hook proof shape.
- TypeScript does not yet have a Drizzle migration set or allowlisted additive schema deltas.
- TypeScript API startup still does not run migrations.
- Flask `manage.py init-db` remains production schema authority.

## Future Allowlisted Delta Contract

Before TypeScript can own even one schema change, a real allowlisted delta needs
to be recorded as an explicit contract, not inferred from runtime behavior. At
minimum it should include:

- a stable migration id, purpose, owner, and affected app feature;
- exact SQL or tracked Drizzle migration file content;
- preconditions, including a passing Flask-current schema preflight;
- explicit target safety rules matching or tightening the current proof command
  boundaries: `--db` required, live-ish paths refused, copied databases requiring
  operator approval;
- dry-run output that names allowlisted, skipped, and would-apply deltas;
- apply output that records exactly which deltas ran and which ledger row was
  written;
- idempotence proof on a copied or disposable database;
- failed or partial migration rollback evidence;
- post-migration TypeScript schema check plus startup/read smoke;
- updated rollback guidance while Flask remains the fallback runtime.

Until that exists, a successful `sqlite:migrate-proof --apply` means only that
the TypeScript ledger proof table can be created on a safe current-schema copy.
It does not mean a TypeScript schema migration has been rehearsed.

## Remaining Staging-Equivalent Gate

The staging/production migration gate remains blocked. The next meaningful
rehearsal still needs a user-approved staging-equivalent SQLite snapshot or
approved copy, not live production data. The rehearsal must record:

- source approval and path-safety proof for the copied database;
- pre-migration backup command, archive contents, and checksum;
- current TypeScript read-only schema report;
- real TypeScript allowlisted delta dry run and apply, if any deltas exist by then;
- WAL, busy-timeout, selected index, and required-schema observations;
- failed or partial migration rollback behavior;
- post-migration TypeScript startup/read smoke;
- restore into a separate target and equivalence comparison;
- exact accepted differences, or a blocked result if differences are unresolved.

No staging-ready or cutover-ready label should be applied while the allowlist is
empty and the only TypeScript migration apply behavior is the ledger proof.

## Decision

This lane improves the gate from "migration hook proof exists" to "current
schema inventory is counted and Flask-initialized scratch parity is proven."

It does not change the production authority decision. The current migration
posture remains:

- Flask `manage.py init-db`: production/staging schema initializer.
- TypeScript schema check: read-only compatibility and startup preflight.
- TypeScript migration proof: explicit, guarded, ledger-only command.
- Real TypeScript schema deltas: none today.
- Cutover readiness: still blocked on staging-equivalent migration rehearsal,
  rollback evidence for failed or partial migration, and full cutover workflow
  approval.
