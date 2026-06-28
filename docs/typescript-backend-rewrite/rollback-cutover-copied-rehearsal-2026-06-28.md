# Rollback And Cutover Copied-Data Rehearsal - 2026-06-28

Status: passed for no-live copied-data rollback mechanics and representative
rollback/cutover smoke; no readiness label change

## Scope

- Rehearsal family: `rollback-cutover`.
- Lane branch: `rewrite/ts-rollback-cutover-copied-rehearsal`.
- Integration base after orchestrator update: `ac67e95e67a30ddbe8bea553e65f84345ef9ef34`
  (`origin/rewrite/ts-phase3-integration`, `Merge TypeScript DND Druid create parity`).
- Rehearsal id: `ts-rollback-cutover-copied-rehearsal-20260628`.
- Scratch evidence root: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/` (ignored).
- Tracked evidence target: this transcript only.

The run used tracked sanitized `tests/fixtures/sample_campaigns` copied under
the ignored rehearsal root plus a Flask-initialized synthetic SQLite database
seeded under the same root. It did not use Fly, staging, live SQLite, live
campaign content, a local campaign mirror, the owner checkout, vault content,
tracked `campaigns/` data, production URLs, or production secrets.

## Safety Confirmation

- Repo root: current Codex-managed `campaign_player_wiki` worktree.
- Owner checkout avoided: the owner checkout was not used as a mutation target.
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: absent in this worktree.
- `.local/roadmaps/ops-backlog.md`: absent in this worktree.
- Rehearsal root path guard: `scripts/staging_rehearsal_harness.py check-paths` passed.
- Copied SQLite: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/player_wiki.sqlite3`.
- Copied campaigns dir: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/campaigns`.
- Backup dir: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/backup/`.
- Restore target: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/restore/target/`.

## Commands

Baseline setup:

```powershell
git fetch origin
git switch -c rewrite/ts-rollback-cutover-copied-rehearsal origin/rewrite/ts-phase3-integration
git fetch origin
git rebase origin/rewrite/ts-phase3-integration
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py guide --family rollback-cutover
```

Disposable rehearsal driver:

```powershell
powershell -ExecutionPolicy Bypass -File .\.task-temp\run-rollback-cutover-rehearsal.ps1
```

The driver called the guarded harness:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-rollback-cutover-copied-rehearsal-20260628 `
  --family rollback-cutover `
  --source-description "tracked sanitized fixture campaigns copied under .task-temp plus Flask-initialized synthetic SQLite rows" `
  --source-approval "no-live copied-data rehearsal authorized by delegation; no staging/live source"

& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628 `
  --db .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\campaigns `
  --backup-archive .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\backup\pre-cutover-placeholder.zip

& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628 `
  --label pre `
  --family rollback-cutover `
  --db .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\campaigns

& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628 `
  --label post `
  --family rollback-cutover `
  --db .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\campaigns

& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628 `
  --label restore `
  --family rollback-cutover `
  --db .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\target\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\target\campaigns

& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\pre\manifest.json `
  --after .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\manifest.json
```

Flask schema/init and seed shape:

```powershell
$env:PLAYER_WIKI_DB_PATH = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/player_wiki.sqlite3"
$env:PLAYER_WIKI_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/campaigns"
$env:PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS = "999999"
& '<workspace>/.venv/Scripts/python.exe' .\manage.py init-db
& '<workspace>/.venv/Scripts/python.exe' .\.task-temp\rollback-cutover-seed.py `
  .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3
```

Backup shape:

```powershell
$env:PLAYER_WIKI_DB_PATH = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/player_wiki.sqlite3"
$env:PLAYER_WIKI_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/campaigns"
powershell -ExecutionPolicy Bypass -File .\local.ps1 `
  -Action backup `
  -DbPath .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3 `
  -BackupDir .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\backup `
  -BackupLabel rollback-cutover-pre
```

Restore shape:

```powershell
$env:PLAYER_WIKI_DB_PATH = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/restore/target/player_wiki.sqlite3"
$env:PLAYER_WIKI_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/restore/target/campaigns"
powershell -ExecutionPolicy Bypass -File .\local.ps1 `
  -Action restore `
  -DbPath .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\target\player_wiki.sqlite3 `
  -BackupArchive .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\backup\player-wiki-backup-20260628T034751Z-rollback-cutover-pre.zip `
  -ForceRestore `
  -SkipPreRestoreBackup
```

TypeScript smoke shape:

```powershell
& '<node-runtime>/node.exe' .\.task-temp\rollback-cutover-ts-smoke.mjs `
  --root .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628 `
  --db .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\player_wiki.sqlite3 `
  --campaigns .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\input\campaigns `
  --port 39941
```

The smoke started `apps/api/dist/server.js` with:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-copied-rehearsal-20260628/input/campaigns"
$env:PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS = "999999"
$env:PORT = "39941"
```

Flask fallback smoke shape after restore:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\.task-temp\rollback-cutover-flask-smoke.py `
  .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\target\player_wiki.sqlite3 `
  .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\target\campaigns `
  .\.task-temp\ts-rollback-cutover-copied-rehearsal-20260628\restore\flask-smoke.json
```

## Baseline Evidence

- Last known-good Flask target: commit `ac67e95e67a30ddbe8bea553e65f84345ef9ef34` from the integration branch. No Flask image tag/id was available or used.
- TypeScript target: same branch and commit, built locally by `local.ps1 -Action ts-api-check`.
- Route snapshot status: `scripts/route_snapshots.py --check` passed.
- Flask schema initializer: `manage.py init-db` ran against the copied SQLite path before seeding.
- Pre-mutation harness snapshot captured 38 copied campaign files and all 31 rollback-cutover family tables with no missing tables.
- Selected baseline SQL sample:
  - `users`: 3
  - `api_tokens`: 3
  - `campaign_memberships`: 2
  - `character_state`: 3
  - `campaign_sessions`: 1
  - `campaign_session_messages`: 1
  - `campaign_dm_statblocks`: 1
  - `campaign_combat_trackers`: 1
  - `systems_entries`: 1
  - `campaign_pages`: 1
  - `user_preferences` for user `77`: `theme_key=parchment`, `session_chat_order=newest_first`

## Backup

- Archive path: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/backup/player-wiki-backup-20260628T034751Z-rollback-cutover-pre.zip`.
- Archive contents: `manifest.json`, `database/player_wiki.sqlite3`, and `campaigns/**`.
- Campaign files included: 38.
- Database snapshot: `player_wiki.sqlite3`.
- Size: 28,486 bytes.
- SHA-256: `35424bd0c954b3e52d3eaca8c3e6416b29ef80351ef9468669a9eff432f9ceab`.

The archive was created from disposable copied data only.

## TypeScript Smoke And Write Delta

All TypeScript smoke requests returned HTTP 200 against the copied-data server:

| Surface | Route | Status |
| --- | --- | ---: |
| Health | `GET /healthz` | 200 |
| App metadata | `GET /api/v1/app` | 200 |
| Auth | `GET /api/v1/me` | 200 |
| Campaign Home | `GET /api/v1/campaigns/linden-pass` | 200 |
| Wiki | `GET /api/v1/campaigns/linden-pass/wiki` | 200 |
| Wiki page | `GET /api/v1/campaigns/linden-pass/wiki/pages/locations/port-meridian` | 200 |
| Search | `GET /campaigns/linden-pass/global-search?q=port` | 200 |
| Help | `GET /api/v1/campaigns/linden-pass/help` | 200 |
| DM Content | `GET /api/v1/campaigns/linden-pass/dm-content` | 200 |
| DM Content Systems | `GET /api/v1/campaigns/linden-pass/dm-content/systems` | 200 |
| Systems | `GET /api/v1/campaigns/linden-pass/systems` | 200 |
| Characters | `GET /api/v1/campaigns/linden-pass/characters` | 200 |
| Character detail | `GET /api/v1/campaigns/linden-pass/characters/arden-march` | 200 |
| Session | `GET /api/v1/campaigns/linden-pass/session` | 200 |
| Session wiki lookup | `GET /campaigns/linden-pass/session/wiki-lookup/search?q=port` | 200 |
| Combat | `GET /api/v1/campaigns/linden-pass/combat` | 200 |
| Account settings write | `PATCH /api/v1/me/settings` | 200 |
| Account settings readback | `GET /api/v1/me/settings` | 200 |

Accepted TypeScript write:

| Route/action | Actor | Affected data | Decision | Evidence |
| --- | --- | --- | --- | --- |
| `PATCH /api/v1/me/settings` with `theme_key=verdant`, `session_chat_order=oldest_first` | app-admin bearer API token | `user_preferences` row for user `77` | `revert` | `post/sql-samples.json` changed user `77` from `parchment/newest_first` to `verdant/oldest_first`; `restore/sql-samples.json` returned user `77` to `parchment/newest_first`. |

No other TypeScript write was accepted. `api_tokens.last_used_at` was held stable
with `PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS=999999` and future fixture
timestamps, so the account-settings row was the only deliberate data delta.

## Restore And Equivalence

The pre-cutover backup archive was restored into a separate disposable target:

- Restore SQLite: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/restore/target/player_wiki.sqlite3`.
- Restore campaigns dir: `.task-temp/ts-rollback-cutover-copied-rehearsal-20260628/restore/target/campaigns`.
- Campaign files restored: 38.

Harness compare of pre vs restore:

```json
{
  "changed_files": [],
  "equal": true,
  "sqlite_equal": true
}
```

Focused SQL samples also matched the intended rollback decision: user `77`
returned to `theme_key=parchment` and `session_chat_order=newest_first`, while
the sampled auth, session, combat, systems, and publishing rows matched the
baseline values.

## Flask Fallback Smoke

After restore, the Flask fallback smoke used the restored copied paths with
Flask's test client:

| Smoke | Route | Status |
| --- | --- | ---: |
| Health | `GET /healthz` | 200 |
| App metadata | `GET /api/v1/app` | 200 |

`/healthz` reported `status=ok`, `campaign_count=1`, the restored copied
SQLite path, and the restored copied campaigns dir.

The fallback metadata reported `git_dirty=true` because the evidence docs were
uncommitted during validation after the Druid rebase; no runtime implementation
file was modified by this lane.

Rollback command shape for a real cutover window remains placeholder-only:

```powershell
# Placeholder shape only; not run in this no-live rehearsal.
git checkout <last-known-good-flask-commit>
fly deploy --app <private-fly-app> --image-label <last-known-good-flask-image>
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action restore `
  -BackupArchive <pre-cutover-backup.zip> `
  -ForceRestore
```

## Decision

- Result: pass for no-live copied-data rollback mechanics and representative rollback/cutover smoke.
- Label before: no label movement; the full family requires `staging snapshot ready` before it can move to `cutover rehearsal passed`.
- Label after: unchanged.
- Not claimed: `staging snapshot ready`, `cutover rehearsal passed`, PR approval, merge approval, deploy approval, Fly sync approval, live cutover approval, or production write approval.

## Limitations And Remaining Gates

- The SQLite seed was synthetic and sanitized, not a user-approved staging-equivalent snapshot.
- The smoke was API/server-level, not a browser rehearsal.
- Only one TypeScript write was accepted and reverted; route-family staging snapshot gates still need realistic data coverage before cutover discussion.
- No Fly command, deploy, live API write, live SQLite sync, production volume access, or production URL was used.
- No TypeScript container/Fly runtime proof was added by this lane.
- Full cutover still needs all route-family staging snapshot gates, a realistic staging-equivalent or approved copied-data workflow smoke, final drift audit, operator-approved rollback window, and explicit user approval before PR/merge/deploy/cutover.
