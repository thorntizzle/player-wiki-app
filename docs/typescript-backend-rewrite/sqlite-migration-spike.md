# SQLite Migration Spike

Date: 2026-06-25
Owner: TypeScript backend rewrite evidence capture
Scratch root: `<workspace>/.task-temp/typescript-backend-sqlite-migration-spike-20260625`

## Objective

Prove a minimal, practical Drizzle SQLite migration path for the rewrite with one run of:

- schema declaration
- migration generation
- migration application
- runtime insert/select through Drizzle
- driver comparison for `better-sqlite3` and `libsql`

## Scratch project layout

- `<workspace>/.task-temp/typescript-backend-sqlite-migration-spike-20260625/node-v22.12.0-win-x64`
  Local Node/npm runtime used for all commands.
- `<workspace>/.task-temp/typescript-backend-sqlite-migration-spike-20260625/drizzle-migration-spike`
- `<workspace>/.task-temp/typescript-backend-sqlite-migration-spike-20260625/drizzle-migration-spike/src/schema.ts`
- `<workspace>/.task-temp/typescript-backend-sqlite-migration-spike-20260625/drizzle-migration-spike/fixture.sqlite`

## Commands and outcomes

Run from `...drizzle-migration-spike` unless noted.

```powershell
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js --version
<scratch>/node-v22.12.0-win-x64/node.exe --version
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view drizzle-orm version
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view drizzle-kit version
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view better-sqlite3 version
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view @libsql/client version
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run db:generate
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run db:migrate
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run verify:better-sqlite3
<scratch>/node-v22.12.0-win-x64/node.exe <scratch>/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run probe:libsql -- fixture.sqlite
```

Observed outcomes:

- Node runtime and local npm available from scratch path (`node v22.12.0`, `npm 10.9.0`).
- Drizzle package metadata checks resolved to:
  - `drizzle-orm 0.45.2`
  - `drizzle-kit 0.31.10`
  - `better-sqlite3 12.11.1`
  - `@libsql/client 0.17.4`
- `db:generate` generated the migration set for the fixture schema; reruns report no schema changes once the migration exists.
- `db:migrate` applied the migration set to `fixture.sqlite`.
- `verify:better-sqlite3` executed clean insert/select:
  - 1 row in `campaigns`
  - 2 rows in `route_fixtures`
  - rows were read back through Drizzle with joined and filtered queries.
- `probe:libsql` succeeded against the same file-backed database and returned 2 `campaigns` rows after inserting a second campaign through the libSQL driver.

## Representative schema used

- `campaigns` table: id/slug/name/description/is_active/current_session_slug
- `route_fixtures` table: campaign_id FK + route_method/route_path/fixture_payload/response_status

This is minimal but route-shaped, matching rewrite-readiness needs for fixture-backed API route parity tests.

## Driver comparison

### better-sqlite3

Result: PASS for proof-of-concept migration + query runtime.

- Pros:
  - sync API with predictable behavior in local scripts
  - direct Drizzle integration in this spike via `drizzle-orm/better-sqlite3`
- Cons:
  - native module install requires a local Node runtime on `PATH` during install fallback steps on this machine.

### libsql

Result: PASS for file-backed probe using `drizzle-orm/libsql` + `@libsql/client`.

- Pros:
  - async interface available and works with file URL path in probe.
- Cons:
  - adds a second client dependency and setup profile.

## Recommendation

For this slice, `better-sqlite3` is the recommended default driver for local migration scripting and runtime verification because it is minimal and straightforward for file-based fixture DB workflows.

`libsql` is viable and not blocked, but adds operational surface area for local installs and is not yet needed for initial rewrite migration spike.

## Blockers and follow-up

- No remaining blockers for this spike.
- Initial install attempt used `@libsql/client@0.16.0`, which did not exist in this environment; corrected to `^0.17.4`.
- During native module install, `node` had to be available on `PATH`; this was handled by invoking npm with local Node first in `PATH`.

## References

- Drizzle `generate`: https://orm.drizzle.team/docs/drizzle-kit-generate
- Drizzle `migrate`: https://orm.drizzle.team/docs/drizzle-kit-migrate
- Drizzle kit overview: https://orm.drizzle.team/docs/kit-overview
- Drizzle SQLite docs: https://orm.drizzle.team/docs/get-started/sqlite
