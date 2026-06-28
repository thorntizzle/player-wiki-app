# SQLite Migration Dry-Run Evidence: 2026-06-28

Status: copied synthetic current-style schema dry-run completed; TypeScript startup migration still blocked

## Scope

- Lane branch: `rewrite/ts-sqlite-migration-dry-run`
- Integration baseline before commit: `b96c159` (`Document published content copied-data readiness`)
- Evidence collection started on `e36faf1` and the lane was rebased to `b96c159`
  before staging or committing this tracked transcript.
- Rehearsal id: `ts-sqlite-migration-dry-run-20260628`
- Rehearsal root: `.task-temp/ts-sqlite-migration-dry-run-20260628`
- Source data: synthetic current-style legacy SQLite copy plus one placeholder campaign file under `.task-temp`
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: not available in this worktree

No owner checkout, vault, Fly, staging, live SQLite, production volume, tracked
`campaigns/<slug>/`, or proprietary campaign content was used.

## Safety Confirmation

Before backup, migration, restore, or TypeScript startup proof, the staging
rehearsal harness path guard resolved all evidence paths inside the disposable
rehearsal root:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-sqlite-migration-dry-run-20260628 `
  --db .\.task-temp\ts-sqlite-migration-dry-run-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-sqlite-migration-dry-run-20260628\input\campaigns `
  --backup-archive .\.task-temp\ts-sqlite-migration-dry-run-20260628\backup\pre-migration.zip
```

Result: passed. The resolved database, campaign directory, and backup archive
paths were all under `.task-temp/ts-sqlite-migration-dry-run-20260628`.

## Baseline Input

The synthetic SQLite input intentionally started below the current schema so the
existing migration guards had work to do. It included representative legacy rows
for:

- `users`
- `user_preferences`
- `campaign_visibility_settings`
- `campaign_sessions`
- `campaign_session_messages`
- `campaign_session_articles`
- `campaign_combat_trackers`
- `campaign_combatants`
- `campaign_dm_statblocks`
- `campaign_system_policies`

The pre-migration harness snapshot recorded those 10 populated tables and the
expected missing current tables under:

- `.task-temp/ts-sqlite-migration-dry-run-20260628/pre/manifest.json`
- `.task-temp/ts-sqlite-migration-dry-run-20260628/pre/schema-detail.json`

## Backup

Backup command, with both database and campaign paths pointed at the disposable
copy:

```powershell
$env:PLAYER_WIKI_CAMPAIGNS_DIR = '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\input\campaigns'
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action backup `
  -DbPath '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\input\player_wiki.sqlite3' `
  -BackupDir '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\backup' `
  -BackupLabel 'pre-migration'
```

Result:

- Archive: `.task-temp/ts-sqlite-migration-dry-run-20260628/backup/player-wiki-backup-20260628T020353Z-pre-migration.zip`
- Campaign files included: 1 synthetic placeholder
- Database snapshot: `player_wiki.sqlite3`

## Migration Dry Run

The only production-shaped schema command currently wired in this repo is the
Flask authority path:

```powershell
$env:PLAYER_WIKI_DB_PATH = '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\input\player_wiki.sqlite3'
$env:PLAYER_WIKI_CAMPAIGNS_DIR = '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\input\campaigns'
& '<workspace>/.venv/Scripts/python.exe' .\manage.py init-db
```

Result: passed against the copied database only.

Post-migration evidence:

- Harness snapshot: `.task-temp/ts-sqlite-migration-dry-run-20260628/post/manifest.json`
- Schema detail: `.task-temp/ts-sqlite-migration-dry-run-20260628/post/schema-detail.json`
- Schema delta: `.task-temp/ts-sqlite-migration-dry-run-20260628/post/schema-delta.json`

The migrated copy contained all 34 non-internal current SQLite tables.

## Additive Schema Deltas

The current `init-db` path preserved seeded rows and added the expected schema
surface.

Tables created from the legacy-shaped input:

- `campaign_session_states`
- `campaign_combatant_resource_counters`
- `campaign_combatant_resource_notes`

Representative columns added:

- `user_preferences`: `session_chat_order`, `frontend_mode`
- `campaign_session_messages`: `recipient_scope`, `recipient_user_id`
- `campaign_session_articles`: `source_page_ref`
- `campaign_combat_trackers`: `revision`
- `campaign_combatants`: `revision`, `source_kind`, `source_ref`, `player_detail_visible`, `dexterity_modifier`, `initiative_priority`
- `campaign_dm_statblocks`: `subsection`
- `campaign_system_policies`: `allow_dm_shared_core_entry_edits`

Representative indexes added:

- `idx_campaign_sessions_active`
- `idx_campaign_session_messages_session`
- `idx_campaign_session_messages_session_recipient`
- `idx_campaign_session_articles_campaign_status`
- `idx_campaign_combatants_campaign_order`
- `idx_campaign_combatants_campaign_order_v2`
- `idx_campaign_combatant_resource_counters_combatant`
- `idx_campaign_combatant_resource_notes_combatant`
- `idx_campaign_dm_statblocks_campaign`

Seeded row counts remained stable for existing tables. Newly created tables had
zero rows, as expected.

## WAL And Busy Timeout Observations

The Flask app connection path in `player_wiki.db.get_db()` set these PRAGMAs
against the copied database:

```json
{
  "busy_timeout": 30000,
  "foreign_keys": 1,
  "journal_mode": "wal",
  "synchronous": 1
}
```

The TypeScript `better-sqlite3` probe opened the migrated copy successfully and
reported:

```json
{
  "busy_timeout": 5000,
  "foreign_keys": 1,
  "journal_mode": "wal",
  "synchronous": 1,
  "user_count": 1
}
```

Observation: WAL persisted on the copied DB after Flask initialization, but
busy timeout is connection-level. Current TypeScript SQLite callers instantiate
`better-sqlite3` directly and do not set the Flask-equivalent 30000 ms busy
timeout.

## Idempotence

A second `manage.py init-db` pass against the migrated copy completed
successfully.

Focused schema/index comparison after the first and second passes:

```json
{
  "schema_equal_after_second_init_db": true,
  "interesting_table_count": 13,
  "index_count": 45
}
```

This proves the current Flask schema guard path is additive and idempotent for
the synthetic current-style legacy shape used in this lane.

## TypeScript Startup Probe

The TypeScript validation gate was run during evidence collection and rerun
after the final rebase to `b96c159`:

```powershell
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check `
  -NodeRoot "C:\Users\thorn\AppData\Local\OpenAI\Codex\runtimes\cua_node\a89897d3d9baa117\bin"
```

Result: passed. The command ran `npm ci`, route snapshot check, TypeScript
typecheck, build, and route parity. `npm ci` emitted a `prebuild-install`
deprecation warning, but the command exited successfully.

Compiled TypeScript API smoke was then run in process against the migrated copy,
without leaving a server running:

- `GET /healthz`: HTTP 200
- `GET /api/v1/app`: HTTP 200, with copied DB and campaigns paths in the app payload
- `GET /api/v1/me` with an invalid bearer token: HTTP 401 expected auth envelope

Evidence file:

- `.task-temp/ts-sqlite-migration-dry-run-20260628/post/typescript-compiled-api-smoke.json`

## Restore

The pre-migration backup was restored into a separate disposable target, not
over the migrated input copy and not over local app state:

```powershell
$env:PLAYER_WIKI_CAMPAIGNS_DIR = '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\restore\campaigns'
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action restore `
  -DbPath '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\restore\player_wiki.sqlite3' `
  -BackupArchive '<repo>\.task-temp\ts-sqlite-migration-dry-run-20260628\backup\player-wiki-backup-20260628T020353Z-pre-migration.zip' `
  -ForceRestore `
  -SkipPreRestoreBackup
```

Result:

- Restored database: `.task-temp/ts-sqlite-migration-dry-run-20260628/restore/player_wiki.sqlite3`
- Restored campaign files: 1 synthetic placeholder

## Equivalence

Restore comparison command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-sqlite-migration-dry-run-20260628\pre\manifest.json `
  --after .\.task-temp\ts-sqlite-migration-dry-run-20260628\restore\manifest.json
```

Result:

```json
{
  "changed_files": [],
  "equal": true,
  "sqlite_equal": true
}
```

Known acceptable differences: none.

Unexpected differences: none.

## Blocker

This lane did not find a tracked TypeScript production migration command,
Drizzle schema package, Drizzle migration folder, or TypeScript startup migration
hook in `apps/api`. The current TypeScript server starts Hono directly from
`apps/api/src/server.ts`, reads `CPW_DB_PATH`, and uses `better-sqlite3`
call sites directly.

Therefore this evidence moves the SQLite gate beyond the previous standalone
Drizzle spike/static proof, but it does not close the production migration gate.
The remaining blocker is an explicit TypeScript startup/schema posture decision:

- continue to call Flask `manage.py init-db` before TypeScript startup during
  transition;
- add a tracked TypeScript/Drizzle migration command and dry-run path;
- or define another dual-check handoff that can be rehearsed against copied and
  staging-equivalent SQLite snapshots.

Until that decision is implemented and rehearsed, TypeScript production/staging
write readiness remains blocked on schema migration/startup integration.

## Decision

- Result: passed copied synthetic current-style dry run for current Flask
  additive schema initialization, TypeScript read/startup smoke, and restore
  equivalence.
- Label before: `Drizzle spike/static proof`
- Label after: `copied synthetic SQLite migration dry-run evidence; TypeScript startup migration blocked`
- Production/staging implication: no PR, merge, deploy, Fly sync, live API write,
  production SQLite access, or cutover approval is implied by this transcript.
- Follow-up required: implement or formally choose the TypeScript schema startup
  path, set TypeScript SQLite PRAGMAs intentionally if preserving Flask busy
  timeout behavior matters, and rerun on a user-approved staging-equivalent DB
  snapshot before claiming staging readiness.
