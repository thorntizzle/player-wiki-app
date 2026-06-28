# DM Content Copied-Data Rehearsal Transcript: 2026-06-28

Status: passed copied-fixture rollback rehearsal; staging snapshot still required

## Scope

- Write family: DM Content statblocks and custom condition definitions
- Rehearsal id: `ts-dm-content-copy-20260628`
- Lane branch: `rewrite/ts-dm-content-copied-data-rehearsal`
- TypeScript commit under rehearsal: `fa48322`
- Flask authority: unchanged production authority; no Flask routes, Fly apps, live volumes, staging data, vault content, owner checkout, or tracked `campaigns/` data were mutated
- Source data: sanitized tracked `tests/fixtures/sample_campaigns` copied into `.task-temp/ts-dm-content-copy-20260628/input/campaigns` plus a synthetic SQLite seed matching the current TypeScript API smoke schema
- Readiness transition tested: `fixture-write validated` -> `copied-data rollback ready`

## Safety Confirmation

- Repo root: current `campaign_player_wiki` Codex worktree
- Rehearsal root: `.task-temp/ts-dm-content-copy-20260628`
- Copied SQLite: `.task-temp/ts-dm-content-copy-20260628/input/player_wiki.sqlite3`
- Copied campaigns dir: `.task-temp/ts-dm-content-copy-20260628/input/campaigns`
- Backup archive: `.task-temp/ts-dm-content-copy-20260628/backup/player-wiki-backup.zip`
- Restore target: `.task-temp/ts-dm-content-copy-20260628/restore`
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: not available in this worktree
- Refused paths: no owner checkout, tracked `campaigns/<slug>/`, vault, Fly, staging, or production paths were used

Harness path guard:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-dm-content-copy-20260628 `
  --db .\.task-temp\ts-dm-content-copy-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-dm-content-copy-20260628\input\campaigns `
  --backup-archive .\.task-temp\ts-dm-content-copy-20260628\backup\player-wiki-backup.zip
```

Result: passed; all resolved paths stayed under the rehearsal root.

## Baseline Evidence

Baseline harness snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-dm-content-copy-20260628 `
  --label pre `
  --family dm-content `
  --db .\.task-temp\ts-dm-content-copy-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-dm-content-copy-20260628\input\campaigns
```

Baseline SQLite counts:

| Table | Count |
| --- | ---: |
| `campaign_dm_statblocks` | 1 |
| `campaign_dm_condition_definitions` | 1 |

Baseline sampled API state:

- DM Content listed one `Dock Tough` statblock with parser summary `AC 12, HP 16, Speed 30 ft. (30 ft. movement), Init +2`.
- DM Content listed one custom condition, `Salt-Burned`.
- Combat DM setup exposed `Dock Tough` in `available_statblock_choices`.
- Combat condition options included `Salt-Burned` alongside built-in DND-5E conditions.

Baseline evidence was saved under the ignored rehearsal root:

- `pre/manifest.json`
- `pre/seed-rows.json`
- `pre/api-samples.json`

## Backup

Backup command shape:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-dm-content-copy-20260628/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-dm-content-copy-20260628/input/campaigns"
node .\.task-temp\dm-content-rehearsal-driver.mjs mutate-restore
```

The ignored driver created the backup archive before mutation and refused paths outside the `.task-temp` rehearsal root.

Backup summary:

| Field | Value |
| --- | --- |
| Archive | `.task-temp/ts-dm-content-copy-20260628/backup/player-wiki-backup.zip` |
| SHA-256 | `11a373400bee2ea52d213abb0fada4670821f7509e015f31bfbefb2da375ebae` |
| Size | 21263 bytes |
| Entries | 39 |

## Mutation

Runtime:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-dm-content-copy-20260628/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-dm-content-copy-20260628/input/campaigns"
node apps/api/dist/server.js
```

The rehearsal started the built TypeScript API against copied data only. Redacted request/response payloads were saved under `.task-temp/ts-dm-content-copy-20260628/mutation/request-response-log.json`.

Representative request sequence, all against copied data:

| Step | Result |
| --- | --- |
| Create `Harbor Lookout` statblock | HTTP 200 |
| Update same statblock to `Harbor Lookout Captain` | HTTP 200 |
| Delete updated statblock | HTTP 200 |
| Attempt duplicate custom condition `Salt Burned` | HTTP 400 validation error |
| Create `Off Balance` custom condition | HTTP 200 |
| Update same condition to `Off Balance Revised` | HTTP 200 |
| Delete updated condition | HTTP 200 |
| Add Combat NPC from baseline DM Content statblock `Dock Tough` | HTTP 200 |
| Add `Salt-Burned` condition to the source-backed combatant | HTTP 200 |

Coverage gained:

- statblock create/update/delete against copied SQLite;
- parser output changes for AC, HP, speed/movement, and initiative from statblock Markdown;
- durable actor columns in mutation responses (`created_by_user_id` / `updated_by_user_id`);
- condition duplicate validation, create/update/delete, and deleted-record response payloads;
- Combat setup still consumed restored DM Content statblock choices and custom condition options;
- Combat source-backed seeding from DM Content copied HP, movement, initiative, Dexterity tie-breaker, source identity, supported daily counter `Arcane Jolt`, and read-only unsupported notes for at-will spellcasting and recharge text.

Post-mutation sampled SQL state:

| Evidence | Result |
| --- | --- |
| `campaign_dm_statblocks` | Returned to the single baseline row after create/update/delete |
| `campaign_dm_condition_definitions` | Returned to the single baseline row after create/update/delete |
| `campaign_combatants` | One `dm_statblock` combatant seeded from `source_ref = 301` |
| `campaign_combatant_resource_counters` | One `Arcane Jolt` counter, `2/2`, reset label `Per day`, source label `DM Content` |
| `campaign_combatant_resource_notes` | Two notes: at-will spellcasting and `Rust Breath` recharge |
| `campaign_combat_conditions` | One `Salt-Burned` condition on the seeded combatant |
| `campaign_combat_trackers` | Revision advanced to `2` |

Audit rows: no DM Content-specific audit event table path is present for these TypeScript routes in the copied fixture seed. Actor evidence is covered by statblock and condition `created_by_user_id` / `updated_by_user_id` columns in responses and SQL samples.

## Restore

Restore target:

```text
.task-temp/ts-dm-content-copy-20260628/restore
```

The backup archive was restored into that separate disposable target, not over the mutated input copy.

Restore snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-dm-content-copy-20260628 `
  --label restore `
  --family dm-content `
  --db .\.task-temp\ts-dm-content-copy-20260628\restore\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-dm-content-copy-20260628\restore\campaigns
```

Focused Combat smoke after restore:

- The clean restored target was copied to `.task-temp/ts-dm-content-copy-20260628/restore-combat-smoke`.
- `POST /api/v1/campaigns/linden-pass/combat/statblock-combatants` with `statblock_id = 301` returned HTTP 200.
- The seeded combatant preserved `source_kind = dm_statblock`, `source_ref = 301`, HP 16, movement 30, initiative +2, Dexterity tie-breaker +2, `Arcane Jolt` `2/2` with reset label `Per day`, and read-only notes for at-will spellcasting plus `Rust Breath` recharge.
- `POST /api/v1/campaigns/linden-pass/combat/combatants/1/conditions` with `Salt-Burned` returned HTTP 200, and the restored Combat payload still included `Salt-Burned` in `combat_condition_options`.
- Evidence file: `.task-temp/ts-dm-content-copy-20260628/restore/combat-smoke-after-restore.json`.

## Equivalence

Harness compare:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-dm-content-copy-20260628\pre\manifest.json `
  --after .\.task-temp\ts-dm-content-copy-20260628\restore\manifest.json
```

Result:

```json
{"equal":true,"changed_files":[],"sqlite_equal":true}
```

Additional sampled API comparison:

```json
{"api_samples_match_baseline":true}
```

Known acceptable differences: none.

Unexpected differences: none.

## Decision

- Result: pass
- Label before: `fixture-write validated`
- Label after: `copied-data rollback ready; staging snapshot required`
- Production/staging implication: no staging write, production write, Fly sync, deploy, PR, merge, or cutover is approved by this transcript.
- Follow-up required: user-approved staging-equivalent snapshot rehearsal before DM Content writes can claim `staging snapshot ready`.
