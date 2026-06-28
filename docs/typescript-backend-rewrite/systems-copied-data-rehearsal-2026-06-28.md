# Systems Copied-Data Rehearsal Transcript: 2026-06-28

Status: passed copied-fixture rollback rehearsal; staging snapshot still required

## Scope

- Write family: Systems and shared-source writes
- Rehearsal id: `ts-systems-copy-20260628-caef`
- Lane branch: `rewrite/ts-systems-copied-data-rehearsal`
- TypeScript commit under rehearsal: `994aa62`
- Flask authority: unchanged production authority; no Flask routes, Fly apps, live volumes, or staging data were mutated
- Source data: sanitized `sample_campaigns` fixture plus synthetic SQLite seeded from the TypeScript Systems smoke fixture under `.task-temp/ts-systems-copy-20260628-caef/input`
- Readiness transition tested: `fixture-write validated` -> `copied-data rollback ready`

## Safety Confirmation

- Repo root: current `campaign_player_wiki` Codex worktree
- Rehearsal root: `.task-temp/ts-systems-copy-20260628-caef`
- Copied SQLite: `.task-temp/ts-systems-copy-20260628-caef/input/player_wiki.sqlite3`
- Copied campaigns dir: `.task-temp/ts-systems-copy-20260628-caef/input/campaigns`
- Backup archive: `.task-temp/ts-systems-copy-20260628-caef/backup/pre-mutation-copy.zip`
- Restore target: `.task-temp/ts-systems-copy-20260628-caef/restore/input`
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: not available in this worktree after integration through `994aa62`
- Refused paths: no owner checkout, tracked `campaigns/<slug>/`, vault, Fly, staging, or production paths were used

Harness path guard:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-systems-copy-20260628-caef `
  --db .\.task-temp\ts-systems-copy-20260628-caef\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-systems-copy-20260628-caef\input\campaigns `
  --backup-archive .\.task-temp\ts-systems-copy-20260628-caef\backup\pre-mutation-copy.zip
```

Result: passed; all resolved paths stayed under the rehearsal root.

## Baseline Evidence

Baseline harness snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-systems-copy-20260628-caef `
  --label pre `
  --family systems `
  --db .\.task-temp\ts-systems-copy-20260628-caef\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-systems-copy-20260628-caef\input\campaigns
```

Baseline SQLite counts:

| Table | Count |
| --- | ---: |
| `systems_libraries` | 1 |
| `systems_sources` | 3 |
| `systems_entries` | 4 |
| `systems_import_runs` | 1 |
| `systems_shared_entry_edit_events` | 0 |
| `systems_entry_links` | 0 |
| `campaign_system_policies` | 0 |
| `campaign_enabled_sources` | 1 |
| `campaign_entry_overrides` | 1 |

Baseline sampled rows were saved under the ignored rehearsal root:

- `pre/manifest.json`
- `pre/sql-summary.json`
- `pre/seed-summary.json`

## Backup

Backup command:

```powershell
Compress-Archive -LiteralPath `
  .\.task-temp\ts-systems-copy-20260628-caef\input\player_wiki.sqlite3, `
  .\.task-temp\ts-systems-copy-20260628-caef\input\campaigns `
  -DestinationPath .\.task-temp\ts-systems-copy-20260628-caef\backup\pre-mutation-copy.zip `
  -Force
```

Backup SHA-256:

```text
CCC4EB005A78B3DCEC96ED3D41FEEB43FFE682EBBD78EE74B77A3789CBFAA845
```

## Mutation

Runtime:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-systems-copy-20260628-caef/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-systems-copy-20260628-caef/input/campaigns"
node apps/api/dist/server.js
```

The rehearsal drove the built Hono app in-process with those copied-data environment variables and saved redacted request/response payloads under `.task-temp/ts-systems-copy-20260628-caef/mutation`.

Representative request sequence, all against copied data:

| Step | Result |
| --- | --- |
| Baseline Systems source list | HTTP 200 |
| DM enables `XGE` with proprietary acknowledgement | HTTP 200 |
| App admin changes `XGE` visibility to `private` | HTTP 200 |
| Update slashy-key entry override | HTTP 200 |
| Create custom campaign Systems entry | HTTP 200 |
| Update custom campaign Systems entry | HTTP 200 |
| Archive custom campaign Systems entry | HTTP 200 |
| Restore custom campaign Systems entry | HTTP 200 |
| Import campaign item mechanics from a sanitized published item page | HTTP 200 |
| Refresh campaign item mechanics import | HTTP 200 |
| Import a tiny sanitized DND-5E `MM` monster ZIP | HTTP 200 |
| Read sanitized `MM` import history | HTTP 200 |
| Read post-import `MM` monster category | HTTP 200 |

Coverage gained:

- source policy writes across proprietary acknowledgement and admin-private visibility;
- slash-containing entry-key override persistence;
- custom source bootstrap, custom entry create/update/archive/restore, and audit rows;
- campaign item mechanics import and refresh from a copied, sanitized published `Items` page;
- shared DND-5E import using a tiny synthetic ZIP with no art, token, sound, or vault content;
- sanitized import-run history and post-import Systems source/category reads.

Post-mutation SQLite counts:

| Table | Count |
| --- | ---: |
| `systems_libraries` | 1 |
| `systems_sources` | 4 |
| `systems_entries` | 6 |
| `systems_import_runs` | 2 |
| `systems_shared_entry_edit_events` | 0 |
| `systems_entry_links` | 0 |
| `campaign_system_policies` | 1 |
| `campaign_enabled_sources` | 2 |
| `campaign_entry_overrides` | 4 |

This post state proves the mutation sequence exercised shared-source import history, custom source/entry writes, campaign policy rows, enabled-source rows, and entry overrides while leaving copied campaign files unchanged.

## Restore

Restore command:

```powershell
Expand-Archive -LiteralPath .\.task-temp\ts-systems-copy-20260628-caef\backup\pre-mutation-copy.zip `
  -DestinationPath .\.task-temp\ts-systems-copy-20260628-caef\restore\input `
  -Force
```

Restore path guard:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-systems-copy-20260628-caef `
  --db .\.task-temp\ts-systems-copy-20260628-caef\restore\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-systems-copy-20260628-caef\restore\input\campaigns `
  --backup-archive .\.task-temp\ts-systems-copy-20260628-caef\backup\pre-mutation-copy.zip
```

Restore snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-systems-copy-20260628-caef `
  --label restore `
  --family systems `
  --db .\.task-temp\ts-systems-copy-20260628-caef\restore\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-systems-copy-20260628-caef\restore\input\campaigns
```

## Equivalence

Harness compare:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-systems-copy-20260628-caef\pre\manifest.json `
  --after .\.task-temp\ts-systems-copy-20260628-caef\restore\manifest.json
```

Result:

```json
{"equal":true,"changed_files":[],"sqlite_equal":true}
```

Additional sampled SQL comparison:

```json
{"equal":true}
```

Known acceptable differences: none.

Unexpected differences: none.

## Decision

- Result: pass
- Label before: `fixture-write validated`
- Label after: `copied-data rollback ready; staging snapshot required`
- Production/staging implication: no staging write, production write, Fly sync, deploy, PR, merge, or cutover is approved by this transcript.
- Follow-up required: user-approved staging-equivalent snapshot rehearsal before Systems and shared-source writes can claim `staging snapshot ready`.
