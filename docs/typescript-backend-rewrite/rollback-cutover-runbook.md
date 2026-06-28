# TypeScript Rollback And Cutover Evidence Runbook

Last updated: 2026-06-28

Status: no-live rollback and full cutover evidence scaffold

## Purpose

This runbook turns the TypeScript rewrite rollback requirement into a tracked
evidence path. It does not approve a PR, merge, deploy, Fly sync, live API
write, production volume access, or production cutover. Flask remains the
production authority.

Use this only with disposable copied data or a user-approved staging-equivalent
snapshot that has already been copied under `.task-temp/`. Do not point the
commands at live Fly volumes, production SQLite, production campaign content,
the owner checkout, or proprietary vault source.

## Evidence Command

The staging rehearsal harness now has a rollback and cutover evidence family:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py guide `
  --family rollback-cutover
```

Dry-run transcript scaffold:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-rollback-cutover-YYYYMMDD `
  --family rollback-cutover `
  --source-description "copied staging-equivalent snapshot under disposable rehearsal root" `
  --source-approval "operator-approved copied data only" `
  --dry-run
```

Create the scaffold only after the copied inputs are identified:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-rollback-cutover-YYYYMMDD `
  --family rollback-cutover `
  --source-description "<copied-data or staging-equivalent source summary>" `
  --source-approval "<operator approval record>"
```

Then guard the copied paths before any backup, smoke, restore, or rollback
command shape is exercised:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-rollback-cutover-YYYYMMDD `
  --db .\.task-temp\ts-rollback-cutover-YYYYMMDD\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-rollback-cutover-YYYYMMDD\input\campaigns `
  --backup-archive .\.task-temp\ts-rollback-cutover-YYYYMMDD\backup\pre-cutover-backup.zip
```

For Flask backup/restore wrapper rehearsals, set both Flask-side copied-data
environment variables before invoking `local.ps1`. `-DbPath` redirects the
SQLite database, while `PLAYER_WIKI_CAMPAIGNS_DIR` redirects copied campaign
content:

```powershell
$env:PLAYER_WIKI_DB_PATH = ".task-temp/ts-rollback-cutover-YYYYMMDD/input/player_wiki.sqlite3"
$env:PLAYER_WIKI_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-YYYYMMDD/input/campaigns"
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action backup `
  -DbPath .\.task-temp\ts-rollback-cutover-YYYYMMDD\input\player_wiki.sqlite3 `
  -BackupDir .\.task-temp\ts-rollback-cutover-YYYYMMDD\backup `
  -BackupLabel rollback-cutover-pre

$env:PLAYER_WIKI_DB_PATH = ".task-temp/ts-rollback-cutover-YYYYMMDD/restore/target/player_wiki.sqlite3"
$env:PLAYER_WIKI_CAMPAIGNS_DIR = ".task-temp/ts-rollback-cutover-YYYYMMDD/restore/target/campaigns"
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action restore `
  -DbPath .\.task-temp\ts-rollback-cutover-YYYYMMDD\restore\target\player_wiki.sqlite3 `
  -BackupArchive .\.task-temp\ts-rollback-cutover-YYYYMMDD\backup\<archive>.zip `
  -ForceRestore `
  -SkipPreRestoreBackup
```

## Required Transcript Fields

Record these before any cutover smoke:

- Last known-good Flask commit SHA, branch, and image tag/id if an image exists.
- TypeScript branch and commit SHA under rehearsal.
- Route snapshot/check status.
- Pre-cutover SQLite backup command, archive path, contents summary, and checksum.
- Pre-cutover campaign-content backup command, archive path, contents summary, and checksum.
- Runtime target summary using placeholders for private app identity and URLs.
- Confirmation that `.local` roadmap visibility was recorded.

Record these during the TypeScript smoke:

- Auth, Campaign Home, wiki, search, help, DM Content, Systems, Characters,
  Session, Combat, local build, `/healthz`, backup, restore, migration dry-run,
  and rollback smoke status.
- Every TypeScript write accepted during the smoke.
- Actor role, route/action, affected files/tables, request payload location, and
  response payload location for each accepted write.
- Data-delta decision for each write: `revert`, `preserve`, `merge manually`, or
  `block rollback`.

Record these during rollback:

- Runtime repoint/redeploy command shape back to the last known-good Flask commit
  or image, with private app identifiers left as placeholders.
- Restore command shape and backup archive inputs.
- Post-restore SQLite row counts, campaign-content hashes, and sampled API
  responses.
- Post-rollback Flask `/healthz` smoke.
- Representative player and DM smoke after Flask is restored.

## Decision Tree

Rollback can pass only when every TypeScript write accepted before rollback has
one recorded decision:

| Decision | Meaning | Required evidence |
| --- | --- | --- |
| `revert` | Restore returns the copied data to the pre-cutover baseline. | Matching post-restore manifests and sampled API responses. |
| `preserve` | The write is intentionally kept after returning to Flask. | Operator approval plus Flask compatibility smoke for the changed record or file. |
| `merge manually` | The write must be translated into the Flask-authority data shape. | Manual merge steps, owner, and verification result. |
| `block rollback` | The write cannot safely be resolved yet. | Transcript result is `blocked`; cutover rehearsal cannot pass. |

Any unresolved delta, failed restore, failed Flask health smoke, failed player/DM
smoke, missing last known-good Flask target, missing pre-cutover backup, or
live-path dependency keeps the result blocked.

## Readiness Label

The rollback and full cutover family starts from `staging snapshot ready` only
after all route-family staging snapshot gates have passed. A passing transcript
may move the rewrite to `cutover rehearsal passed` only when the full charter
workflow smoke, rollback command shape, data-delta decisions, restore evidence,
and Flask health smoke all pass against copied or user-approved
staging-equivalent data.

## Non-Goals

- No production deploy.
- No Fly sync.
- No live API writes.
- No production SQLite or campaign-content access.
- No tracked proprietary campaign data or private operational identifiers.
- No edits to ignored `.local/roadmaps` files.
