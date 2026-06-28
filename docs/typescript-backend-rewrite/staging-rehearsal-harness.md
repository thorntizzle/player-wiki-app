# TypeScript Backend Staging Rehearsal Harness

Last updated: 2026-06-28

Status: guarded script, runbook, and transcript template for copied-data and staging-snapshot rehearsals

## Purpose

This document defines a safe rehearsal harness for TypeScript write families before
any staging route enablement, production PR, merge, deploy, Fly sync, or cutover.
It captures the evidence path from backup to mutation to verification to restore
to equivalence without touching live data.

Flask remains the production authority. A rehearsal may use copied data or a
user-approved staging-equivalent snapshot only. It must never point TypeScript,
Flask, backup, restore, or verification commands at live Fly volumes, production
SQLite, production campaign content, or the owner checkout.

## Safety Rules

Allowed inputs:

- A disposable rehearsal root under `.task-temp/` or another explicitly disposable
  local scratch path.
- A copied SQLite database, never the original source database.
- A copied campaign content directory, never the original source content directory.
- Sanitized fixtures already tracked in the repo.
- A user-approved staging-equivalent snapshot that has first been copied into the
  disposable rehearsal root.

Forbidden inputs:

- Live Fly paths, mounted production volumes, or direct Fly SSH filesystem paths.
- The production SQLite file or production campaign content directory.
- The owner checkout as a mutation target.
- Any path under `campaigns/<campaign-slug>/` intended to be tracked by Git.
- Any raw proprietary vault material copied into tracked repo files.
- Any restore or mutation command whose target has not been confirmed as a
  disposable copy.

Before any command that mutates or restores data, record the resolved absolute
paths for `CPW_DB_PATH`, `CPW_CAMPAIGNS_DIR`, backup archive output, and restore
target. If any resolved path is outside the rehearsal root, stop.

## Worktree And Runtime Notes

- Run from the current `campaign_player_wiki` repo root, not from a broader tools
  workspace and not from the owner checkout.
- Prefer repo wrappers or documented runtime paths; do not assume global `python`,
  `node`, or `npm`.
- Use `.task-temp/<rehearsal-id>/` for copied data, logs, hashes, and transcripts.
- Do not create or edit `.local/roadmaps` as part of this harness. In Codex
  worktrees, `.local` may be absent because ignored local roadmap files are not
  copied automatically.
- Do not run broad app tests unless executable code changed. Rehearsal validation
  should be targeted to the write family under review.

## Executable Harness Helper

Use `scripts/staging_rehearsal_harness.py` to create the disposable folder
layout, write the initial transcript, validate copied-data paths, capture file
hashes plus selected SQLite row counts, print family-specific transcript guides,
and compare restored evidence.

The helper deliberately does not run TypeScript mutations, Flask mutations,
restore commands, Fly commands, deploys, or live syncs. It refuses evidence
paths that resolve outside the rehearsal root, and the rehearsal root must be
inside a `.task-temp` directory.

Supported write families:

- `content-character`
- `combat`
- `session`
- `systems`
- `dm-content`
- `publishing`
- `rollback-cutover`

Staging snapshot preflight checklist:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py staging-snapshot-preflight
```

The preflight output is a sanitized Markdown checklist for operator intake
before a user-approved staging-equivalent snapshot is copied under `.task-temp`.
It rechecks the tracked readiness docs, records the no-live boundary, lists
family gates and table families, and keeps every readiness label unchanged.
For a focused family preflight:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py staging-snapshot-preflight `
  --family combat
```

This checklist is not a rehearsal transcript and cannot mark any family
`staging snapshot ready`. A later approved run must still use `check-paths`,
capture baseline/mutation/restore evidence, compare equivalence, and commit only
the sanitized human transcript.

Dry-run scaffold:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-content-character-copy-YYYYMMDD `
  --family content-character `
  --dry-run
```

The dry-run output includes the transcript preview that would be written.

Every copied-data-ready route family has a family-specific guide for the next
operator-approved staging-equivalent snapshot run:

- `content-character`
- `combat`
- `session`
- `systems`
- `dm-content`
- `publishing`

To inspect only the family-specific checklist for a planned staging snapshot
rehearsal:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py guide `
  --family content-character
```

Each guide output is a scaffold, not approval. It lists route/action scope,
baseline evidence, copied-data backup evidence, mutation sequence, restore
equivalence requirements, and the honest label transition from
`copied-data rollback ready` to `staging snapshot ready`. A family can only
claim that transition after a user-approved staging-equivalent snapshot
transcript records approval, path-guard success, backup, mutation, restore, and
equivalence evidence.

For example, to inspect the Combat staging snapshot checklist:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py guide `
  --family combat
```

To inspect only the rollback and full cutover checklist:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py guide `
  --family rollback-cutover
```

The rollback/cutover guide is a scaffold, not approval. It may only be used
after the route-family staging snapshot gates are ready, and it must record a
last known-good Flask target, pre-cutover SQLite and campaign-content backups,
TypeScript data-delta decisions, restore command shape, post-rollback Flask
health smoke, and representative player/DM smoke.

Create a rehearsal scaffold:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-content-character-copy-YYYYMMDD `
  --family content-character `
  --source-description "copied staging-equivalent snapshot, already copied into .task-temp" `
  --source-approval "approved by operator before local copy"
```

Validate copied-data paths before any external backup, mutation, or restore
command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-content-character-copy-YYYYMMDD `
  --db .\.task-temp\ts-content-character-copy-YYYYMMDD\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-content-character-copy-YYYYMMDD\input\campaigns `
  --backup-archive .\.task-temp\ts-content-character-copy-YYYYMMDD\backup\player-wiki-backup.zip
```

Capture baseline, post-mutation, and post-restore manifests:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-content-character-copy-YYYYMMDD `
  --label pre `
  --family content-character `
  --db .\.task-temp\ts-content-character-copy-YYYYMMDD\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-content-character-copy-YYYYMMDD\input\campaigns
```

Compare restored evidence to the baseline:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-content-character-copy-YYYYMMDD\pre\manifest.json `
  --after .\.task-temp\ts-content-character-copy-YYYYMMDD\restore\manifest.json
```

The comparison must pass, and the human transcript must classify any accepted
differences, before a family can claim `copied-data rollback ready` or
`staging snapshot ready`.

## Rehearsal Inputs

Record these fields before starting:

```text
Rehearsal id:
Date:
Operator/thread:
Source snapshot description:
Source snapshot approval:
Rehearsal root:
Copied SQLite path:
Copied campaigns dir:
TypeScript branch/commit:
Flask authority branch/commit:
Write family:
Routes/actions under rehearsal:
Expected readiness transition:
```

Required files under the rehearsal root:

- `input/`: copied SQLite and copied campaign content.
- `backup/`: backup archives created before mutation.
- `pre/`: pre-mutation hashes, selected SQL exports, selected API responses.
- `mutation/`: commands, request payloads, response payloads, and server logs.
- `post/`: post-mutation hashes, SQL exports, API responses, and file listings.
- `restore/`: restore command transcript and post-restore evidence.
- `transcript.md`: the final human-readable transcript.

## Generic Flow

1. Create a fresh rehearsal root.
2. Copy the approved source SQLite and campaign content into `input/`.
3. Resolve and record all paths.
4. Refuse the run if any mutation target is outside the rehearsal root.
5. Run `scripts/staging_rehearsal_harness.py check-paths` for the copied SQLite,
   copied campaign content directory, and intended backup archive path.
6. Point Flask backup tooling and TypeScript runtime variables at the copied data.
7. Capture pre-mutation evidence with the helper:
   - selected file hashes;
   - selected directory listings;
   - selected table row counts and sampled rows;
   - baseline API responses from the Flask authority when practical;
   - baseline TypeScript read responses for the same entities.
8. Create a backup archive from the copied data.
9. Run only the approved write-family mutation commands.
10. Capture mutation responses and immediate post-mutation evidence.
11. Restore from the backup archive into the same disposable copy or a new
    disposable restore target.
12. Capture post-restore evidence.
13. Compare pre and post-restore hashes, SQL exports, row counts, selected rows,
    and sampled API responses.
14. Classify the result and record the readiness decision.

## Command Template

The exact commands are lane-specific and should be filled in by the operator.
Keep placeholders until the paths are known.

```powershell
$env:CPW_DB_PATH = "<rehearsal-root>/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = "<rehearsal-root>/input/campaigns"

# Start TypeScript API against copied data only.
npm --prefix apps/api run build
npm --prefix apps/api run start

# In a separate shell, create a backup of copied data only.
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action backup

# Send approved mutation requests to the copied-data TypeScript API.
# Save request and response bodies under <rehearsal-root>/mutation/.

# Restore only the copied-data backup into a disposable target.
powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action restore `
  -BackupArchive "<rehearsal-root>/backup/<archive>.zip" `
  -ForceRestore
```

If `local.ps1` cannot target the copied rehearsal paths without affecting normal
local app data, do not run it. Use a narrower rehearsal helper in a later ops
lane or record the blocker.

## Transcript Template

```markdown
# Rehearsal Transcript: <id>

## Scope
- Write family:
- Routes/actions:
- Readiness target:

## Safety Confirmation
- Rehearsal root:
- Copied SQLite:
- Copied campaigns dir:
- Refused live paths:
- `.local` visibility:

## Baseline Evidence
- Flask authority commit:
- TypeScript commit:
- Route snapshot/check status:
- Pre-mutation file hashes:
- Pre-mutation SQL row counts:
- Baseline API samples:

## Backup
- Command:
- Archive path:
- Archive contents summary:
- Result:

## Mutation
- TypeScript runtime command:
- Environment:
- Request payloads:
- Response payloads:
- Expected changed files/tables:
- Observed changed files/tables:

## Restore
- Command:
- Target:
- Result:

## Equivalence
- File hash comparison:
- SQL row comparison:
- API response comparison:
- Known acceptable differences:
- Unexpected differences:

## Decision
- Result: pass | fail | blocked
- Label before:
- Label after:
- Follow-up required:
```

## Family Templates

### Content Character

Scope:

- `PUT /api/v1/campaigns/<slug>/content/characters/<characterSlug>`
- `DELETE /api/v1/campaigns/<slug>/content/characters/<characterSlug>`
- Character Controls delete if it reuses content-character deletion.

Baseline evidence:

- `characters/<characterSlug>/definition.yaml`
- `characters/<characterSlug>/import.yaml`
- portrait asset files and metadata;
- `character_state` row JSON/revision;
- `character_assignments` rows;
- sampled character detail response.

Mutation checks:

- DND-5E create/delete state initialization and assignment cleanup.
- Xianxia update/delete mutable-state preservation and clamping.
- Response flags such as `state_created`, `deleted_state`, and
  `deleted_assignment` match actual data changes.

Decision gate:

- Move from `fixture-write validated` to `copied-data rollback ready` only when
  copied-data backup/restore equivalence passes.
- Move to `staging snapshot ready` only after a user-approved staging-equivalent
  snapshot rehearsal passes and the transcript is tracked.

### Combat

Scope:

- Combat tracker start-state reads and live-state polling.
- Add player, manual NPC, DM Content statblock, and Systems monster combatants.
- Advance turn, set current, edit turn, vitals, resources, NPC resources,
  conditions, delete combatant, and clear tracker.

Baseline evidence:

- `campaign_combat_trackers`;
- `campaign_combatants`;
- `campaign_combat_conditions`;
- `campaign_combatant_resource_counters`;
- `campaign_combatant_resource_notes`;
- linked `character_state` rows for selected player characters;
- sampled player Combat, DM Status, and DM Controls payloads.

Mutation checks:

- Revision guards reject stale writes.
- Player-character HP mirrors stay consistent between combatant and
  `character_state`.
- Source-backed NPC counters and notes persist on combatants without mutating
  source statblocks or Systems entries.
- Clear/delete removes dependent condition/resource rows.

Decision gate:

- Require restored tracker, combatants, conditions, counters, notes, and linked
  character state to match baseline or list exact acceptable differences.
- The harness-generated Combat transcript guide starts from
  `fixture-write validated` and may only move to `copied-data rollback ready`
  after the copied-data transcript proves backup, mutation, restore, and
  equivalence. It is not `staging snapshot ready` unless the source snapshot was
  explicitly approved as staging-equivalent and that approval is recorded.

### Session

Scope:

- Start/close session.
- Send global, DM-only, and player-targeted messages.
- Create/update/reveal/delete/clear staged articles.
- Session article image reads.
- Closed log reads and log delete.

Baseline evidence:

- `campaign_sessions`;
- `campaign_session_states`;
- `campaign_session_messages`;
- `campaign_session_articles`;
- `campaign_session_article_images`;
- selected live Session, DM Session, and closed-log API responses.

Mutation checks:

- Audience filtering preserves player/DM visibility.
- Revision and view-token behavior preserve unchanged-response semantics.
- Revealed article chat entries and provenance links are created and removed as
  expected.
- Restored closed logs and images match baseline bytes and metadata.

Decision gate:

- Require backup/restore equivalence across session tables and sampled live/log
  responses before any staging-write label.

### Systems And Shared Source

Scope:

- Source policy updates.
- Entry overrides.
- Custom campaign Systems entries create/update/archive/restore.
- Campaign item mechanics import.
- Shared DND-5E source import.

Baseline evidence:

- `systems_libraries`;
- `systems_sources`;
- `systems_entries`;
- `systems_import_runs`;
- `systems_shared_entry_edit_events`;
- `systems_entry_links`;
- `campaign_system_policies`;
- `campaign_enabled_sources`;
- `campaign_entry_overrides`;
- sampled Systems landing/source/entry/DM Content Systems payloads.

Mutation checks:

- Proprietary/public/private visibility gates are preserved.
- Custom entries keep slug/key identity and archive/restore through overrides.
- Item mechanics import links to the published item page and preserves review
  payload expectations.
- Shared imports strip media fields and record sanitized import history.

Decision gate:

- Require copied-data backup/restore equivalence plus a written decision before
  running any shared-source import against staging snapshots.

### DM Content

Scope:

- Statblock create/update/delete.
- Custom condition create/update/delete.

Baseline evidence:

- `campaign_dm_statblocks`;
- `campaign_dm_condition_definitions`;
- parser output summaries;
- sampled DM Content payload;
- sampled Combat setup choices that consume statblocks/conditions.

Mutation checks:

- Statblock parser fields are stable after upload/update.
- Condition duplicate and validation behavior matches Flask.
- Deleted-record payloads match actual row changes.
- Combat setup choices reflect changes after mutation and return after restore.

Decision gate:

- Require restored DM Content rows and Combat setup payloads to match baseline.

### Publishing And Content Assets

Scope:

- Content config update.
- Page create/update/delete.
- Asset upload/delete.
- Protected asset byte serving.

Baseline evidence:

- `campaign.yaml`;
- selected `content/**/*.md` files;
- selected `assets/**/*` files;
- `campaign_pages`;
- `campaign_page_sync_state`;
- sampled wiki list/detail, DM Content Player Wiki, and protected asset responses.

Mutation checks:

- Page frontmatter and Markdown body remain well-formed.
- SQLite read model and mirrored Markdown stay synchronized.
- Removal-safety blockers and forced-delete behavior are recorded.
- Asset media type, base64 payload, raw byte serving, and empty-directory pruning
  match expectations.

Decision gate:

- Require file hash, SQLite read-model, and sampled API response equivalence after
  restore. Image conversion differences need a separate cutover decision before
  staging-write approval.

### Rollback And Full Cutover

Scope:

- Flask authority health smoke before any TypeScript routing change.
- Full charter workflow smoke across auth, Campaign Home, wiki, search, help, DM
  Content, Systems, Characters, Session, Combat, local build, `/healthz`,
  backup, restore, migration dry-run, and rollback.
- Runtime repoint/redeploy command shape back to Flask using placeholders for
  private app identity.
- Post-rollback Flask health and representative player/DM smoke.

Baseline evidence:

- Last known-good Flask commit SHA, branch, and image tag/id if available.
- TypeScript branch/commit and route snapshot/check status.
- Pre-cutover SQLite backup command, archive path, contents summary, and checksum.
- Pre-cutover campaign-content backup command, archive path, contents summary,
  and checksum.
- Runtime target summary that omits real Fly app identifiers, tokens, secrets,
  and live URLs.

Mutation checks:

- Every TypeScript write accepted during the smoke records route/action, actor
  role, affected files/tables, request payload, and response payload.
- Every accepted write has a data-delta decision: `revert`, `preserve`,
  `merge manually`, or `block rollback`.
- Migration dry-run/startup schema evidence and additive schema deltas are
  recorded before rollback.

Decision gate:

- Require restored SQLite row counts, campaign-content hashes, sampled API
  responses, and post-rollback Flask `/healthz` to match baseline or list exact
  approved differences.
- Any unresolved TypeScript data delta, failed restore, failed Flask smoke,
  missing last known-good Flask target, missing backup, or live-path dependency
  keeps the transcript blocked.
- This family can move from `staging snapshot ready` to `cutover rehearsal
  passed` only after all charter workflows and rollback evidence pass against
  copied or user-approved staging-equivalent data.

## Readiness Transitions

| From | To | Required evidence |
| --- | --- | --- |
| `fixture-write validated` | `copied-data rollback ready` | Disposable copied-data rehearsal passes backup, mutation, restore, and equivalence checks for the write family. |
| `copied-data rollback ready` | `staging snapshot ready` | User-approved staging-equivalent snapshot rehearsal passes with transcript tracked under `docs/typescript-backend-rewrite/` or another approved evidence folder. |
| `staging snapshot ready` | `cutover rehearsal passed` | Full charter workflow smoke passes across auth, campaign home/wiki/search/help, DM Content, Systems, Characters, Session, Combat, local build, health, backup, restore, migration dry-run, and rollback. |

Any failure keeps the previous label. Any unexpected data delta must be classified
as route bug, migration bug, rehearsal harness bug, stale baseline, or approved
behavior difference before rerun.

## Close-Out Checklist

- Transcript written and reviewed.
- No live paths used.
- No production/Fly sync or deploy performed.
- No proprietary snapshot content committed.
- Backup archive stored outside tracked files.
- Readiness label decision recorded.
- Follow-up lanes queued for failures or blockers.
- Final `git status --short --branch` checked from the repo root.
