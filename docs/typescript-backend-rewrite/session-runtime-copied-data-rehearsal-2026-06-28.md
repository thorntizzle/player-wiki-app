# Session Runtime Copied-Data Rehearsal Transcript: 2026-06-28

Status: passed copied-fixture rollback rehearsal; staging snapshot still required

## Scope

- Write family: Session/runtime writes
- Rehearsal id: `ts-session-runtime-copied-data-20260628`
- Lane branch: `rewrite/ts-session-runtime-copied-data-rehearsal`
- TypeScript commit under rehearsal: `e552730`
- Flask authority: unchanged production authority; no Flask routes, Fly apps, live volumes, staging data, vault content, owner checkout, or tracked `campaigns/` data were mutated
- Source data: sanitized tracked `tests/fixtures/sample_campaigns` copied into `.task-temp/ts-session-runtime-copied-data-20260628/input/campaigns` plus a synthetic SQLite seed matching the current TypeScript API smoke schema
- Readiness transition tested: `fixture-write validated` -> `copied-data rollback ready`

## Safety Confirmation

- Repo root: current `campaign_player_wiki` Codex worktree
- Rehearsal root: `.task-temp/ts-session-runtime-copied-data-20260628`
- Copied SQLite: `.task-temp/ts-session-runtime-copied-data-20260628/input/player_wiki.sqlite3`
- Copied campaigns dir: `.task-temp/ts-session-runtime-copied-data-20260628/input/campaigns`
- Backup archive: `.task-temp/ts-session-runtime-copied-data-20260628/backup/session-runtime-pre-backup.zip`
- Restore target: `.task-temp/ts-session-runtime-copied-data-20260628/restore`
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: not available in this worktree
- Refused paths: no owner checkout, tracked `campaigns/<slug>/`, vault, Fly, staging, or production paths were used

Harness path guard:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-session-runtime-copied-data-20260628 `
  --db .\.task-temp\ts-session-runtime-copied-data-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-session-runtime-copied-data-20260628\input\campaigns `
  --backup-archive .\.task-temp\ts-session-runtime-copied-data-20260628\backup\session-runtime-pre-backup.zip
```

Result: passed; all resolved paths stayed under the rehearsal root.

## Baseline Evidence

Baseline harness snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-session-runtime-copied-data-20260628 `
  --label pre `
  --family session `
  --db .\.task-temp\ts-session-runtime-copied-data-20260628\backup\player_wiki.pre.sqlite3 `
  --campaigns-dir .\.task-temp\ts-session-runtime-copied-data-20260628\backup\campaigns-pre
```

Baseline SQLite counts:

| Table | Count |
| --- | ---: |
| `campaign_sessions` | 2 |
| `campaign_session_states` | 1 |
| `campaign_session_messages` | 4 |
| `campaign_session_articles` | 2 |
| `campaign_session_article_images` | 2 |

Baseline sampled API state:

- Admin Session read returned HTTP 200 with one active session, staged and revealed article management payloads, closed logs, and DM-only visibility.
- Player Session read returned HTTP 200 with server-filtered messages: global chat, revealed article entries, and no DM-only message.
- Player unchanged polling with matching `X-Live-Revision` and `X-Live-View-Token` returned HTTP 200 with `changed: false`.
- Closed log `2` and revealed article image `102` existed in the copied fixture seed.

Baseline evidence was saved under the ignored rehearsal root:

- `pre/manifest.json`
- `mutation/01-baseline-admin-session.json`
- `mutation/02-baseline-player-session.json`
- `mutation/04-player-unchanged-poll.json`

## Backup

Backup command:

```powershell
Compress-Archive -Path `
  .\.task-temp\ts-session-runtime-copied-data-20260628\backup\player_wiki.pre.sqlite3, `
  .\.task-temp\ts-session-runtime-copied-data-20260628\backup\campaigns-pre `
  -DestinationPath .\.task-temp\ts-session-runtime-copied-data-20260628\backup\session-runtime-pre-backup.zip
```

The backup captured the pre-mutation copied SQLite database and copied campaign content only. It did not archive owner-checkout, vault, Fly, staging, production, or tracked `campaigns/<slug>/` paths.

## Mutation

Runtime:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-session-runtime-copied-data-20260628/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-session-runtime-copied-data-20260628/input/campaigns"
node apps/api/dist/server.js
```

Representative request sequence, all against copied data:

| Step | Result |
| --- | --- |
| Admin Session baseline read | HTTP 200 |
| Player Session baseline read | HTTP 200 |
| Player unchanged revision/view-token poll | HTTP 200, `changed: false` |
| Send global player chat message | HTTP 200 |
| Send player-targeted DM message to active player `79` | HTTP 200 |
| Send DM-only message | HTTP 200 |
| Create manual staged article with embedded PNG image | HTTP 200 |
| Read created article image before reveal | HTTP 200 |
| Update unrevealed staged article title/body/image metadata | HTTP 200 |
| Reveal staged article into active Session chat | HTTP 200 |
| Admin Session post-reveal read | HTTP 200 |
| Player Session post-reveal read | HTTP 200 |
| Delete all revealed articles and related chat entries | HTTP 200 |
| Close active session | HTTP 200 |
| Start new active session | HTTP 200 |
| Read closed log `2` | HTTP 200 |
| Delete closed log `2` | HTTP 200 |
| Admin Session final read | HTTP 200 |
| Player Session final read | HTTP 200 |

Coverage gained:

- live session lifecycle close/start on copied SQLite;
- global, DM-only, and player-targeted chat writes;
- player/DM audience filtering after scoped writes;
- unchanged-response polling semantics through revision/view-token headers;
- staged article create/update/reveal/delete behavior;
- embedded session-article image storage and serving;
- revealed article chat entry creation and cleanup;
- closed-log read/delete behavior;
- restore into a separate disposable target and post-restore API smoke.

Post-mutation SQLite counts:

| Table | Count |
| --- | ---: |
| `campaign_sessions` | 2 |
| `campaign_session_states` | 1 |
| `campaign_session_messages` | 5 |
| `campaign_session_articles` | 1 |
| `campaign_session_article_images` | 3 |

Post-mutation sampled SQL state:

| Evidence | Result |
| --- | --- |
| Session rows | Baseline active session `1` closed by user `81`; new active session `3` started by user `81` |
| Message scopes | `dm_only`: 2, `global`: 2, `player`: 1 |
| Article rows | Revealed articles were cleared; one unrevealed staged article remained |
| Image rows | Existing fixture images plus created copied-data article image were present before restore |

## Restore

Restore target:

```text
.task-temp/ts-session-runtime-copied-data-20260628/restore
```

The copied pre-mutation database and campaign content backup were restored into that separate disposable target, not over live data and not over tracked repository content.

Restore snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-session-runtime-copied-data-20260628 `
  --label restore `
  --family session `
  --db .\.task-temp\ts-session-runtime-copied-data-20260628\restore\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-session-runtime-copied-data-20260628\restore\campaigns
```

Focused Session smoke after restore:

- `GET /api/v1/campaigns/linden-pass/session` as admin returned HTTP 200.
- `GET /api/v1/campaigns/linden-pass/session` as player returned HTTP 200.
- `GET /api/v1/campaigns/linden-pass/session/logs/2` as admin returned HTTP 200.
- `GET /api/v1/campaigns/linden-pass/session/articles/102/image` as admin returned HTTP 200 and 13 bytes.
- Evidence file: `.task-temp/ts-session-runtime-copied-data-20260628/restore/restore-api-samples.json`.

## Equivalence

Harness compare:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-session-runtime-copied-data-20260628\pre\manifest.json `
  --after .\.task-temp\ts-session-runtime-copied-data-20260628\restore\manifest.json
```

Result:

```json
{"equal":true,"changed_files":[],"sqlite_equal":true}
```

Pre-restore and post-restore SQLite counts both matched:

| Table | Count |
| --- | ---: |
| `campaign_sessions` | 2 |
| `campaign_session_states` | 1 |
| `campaign_session_messages` | 4 |
| `campaign_session_articles` | 2 |
| `campaign_session_article_images` | 2 |

Known acceptable differences: none.

Unexpected differences: none.

## Decision

- Result: pass
- Label before: `fixture-write validated`
- Label after: `copied-data rollback ready; staging snapshot required`
- Production/staging implication: no staging write, production write, Fly sync, deploy, PR, merge, or cutover is approved by this transcript.
- Follow-up required: user-approved staging-equivalent snapshot rehearsal before Session/runtime writes can claim `staging snapshot ready`.
