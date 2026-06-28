# SQLite Schema Command Proof: 2026-06-28

Status: tracked TypeScript read-only schema command implemented; additive migration hook still pending

## Scope

- Lane branch: `rewrite/ts-sqlite-migration-command-proof`
- Baseline: `origin/rewrite/ts-phase3-integration` at `1110f81079ea44804f419210766cd054ebf1c939`
- Data used: disposable SQLite databases created under test temp directories
- No owner checkout, vault, Fly command, staging/live SQLite, production volume, tracked campaign content, or live API write was used.

## Command

After building `apps/api`, the TypeScript schema proof command is:

```powershell
$env:CPW_DB_PATH = "<copied-or-disposable-sqlite-path>"
npm --prefix apps/api run sqlite:schema-check -- --json
```

Equivalent explicit path form:

```powershell
npm --prefix apps/api run sqlite:schema-check -- --db "<copied-or-disposable-sqlite-path>"
```

The command opens the database read-only, performs no migrations, and performs no schema writes. It exits nonzero when the database file is missing or when required tables, columns, indexes, or required connection PRAGMAs are missing.

## Implementation

- `apps/api/src/sqlite.ts` now exposes `inspectSqliteSchema(...)` on the same current-schema requirement list used by TypeScript startup preflight.
- `apps/api/src/sqliteSchemaCheck.ts` is a small CLI over that inspection helper.
- `apps/api/package.json` exposes:
  - `sqlite:schema-check`
  - `test:sqlite-schema-check`
- `local.ps1 -Action ts-api-check` now runs the focused schema-command test after the startup-posture test and before route parity. The wrapper passes its resolved Python path into npm as `CPW_PYTHON_PATH` so the proof test can run Flask `manage.py init-db` without relying on bare `python`.

Reported status includes:

- required and present counts for the 34-table current schema, required columns, and required indexes;
- missing schema items, if any;
- read-only connection PRAGMAs for `foreign_keys=ON` and `busy_timeout=30000`;
- observed database `journal_mode` and `synchronous`;
- the writable-open policy that TypeScript runtime opens apply separately (`journal_mode=WAL`, `synchronous=NORMAL`), with an explicit note that the schema command does not apply those writable PRAGMAs.

## Proof

Focused test:

```powershell
npm --prefix apps/api run test:sqlite-schema-check
```

The test creates a disposable Flask-initialized SQLite database by running `manage.py init-db` with `PLAYER_WIKI_DB_PATH`, `PLAYER_WIKI_CAMPAIGNS_DIR`, and `PLAYER_WIKI_TEMP_DIR` pointed at temp paths. It then runs the TypeScript schema command against that database through `CPW_DB_PATH` and verifies:

- JSON command exits `0`;
- `ok` is `true`;
- mode is `readonly`;
- required table count is `34`;
- no schema items are missing;
- connection `foreign_keys` is `1`;
- connection `busy_timeout_ms` is `30000`;
- writable-open PRAGMAs were not applied by the read-only command.

The same test also creates a deliberately partial SQLite database and verifies the command exits `1` while reporting missing items such as `column users.email` and `table campaign_page_sync_state`. A missing database path also exits `1` and reports `database file`.

Validation run in this lane:

```powershell
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check -NodeRoot "<bundled-node-runtime>\bin"
```

Result: passed. The wrapper completed `npm ci`, `scripts/route_snapshots.py --check`, TypeScript API typecheck, build, SQLite startup-posture test, SQLite schema-command test, and route parity. `npm ci` emitted the existing `prebuild-install` deprecation warning and exited successfully.

## Decision

This closes the narrow gap for a tracked TypeScript-side schema preflight command that can be rehearsed against copied or disposable SQLite databases without mutating them.

This does not close production or staging migration readiness. Flask `manage.py init-db` remains the production schema initializer, TypeScript startup still does not auto-run migrations, and no Drizzle or additive TypeScript migration hook was added in this slice.

Remaining gates:

- add real allowlisted TypeScript schema deltas or a Drizzle migration set beyond the ledger-only `sqlite:migrate-proof` command;
- rehearse that migration path against a user-approved staging-equivalent SQLite snapshot;
- cover failed or partial migration rollback;
- run post-migration TypeScript startup/read smoke against the rehearsed snapshot;
- preserve Flask rollback authority until a full cutover rehearsal and observation window are approved.
