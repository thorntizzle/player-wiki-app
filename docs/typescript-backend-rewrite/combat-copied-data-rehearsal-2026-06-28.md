# Combat Copied-Data Rehearsal Transcript: 2026-06-28

Status: passed copied-fixture rollback rehearsal; staging snapshot still required

## Scope

- Write family: Combat
- Rehearsal id: `ts-combat-copy-20260628`
- Lane branch: `rewrite/ts-combat-copied-data-rehearsal`
- TypeScript commit under rehearsal: `39c15d8`
- Flask authority: unchanged production authority; no Flask routes, Fly apps, live volumes, or staging data were mutated
- Source data: sanitized smoke-fixture SQLite/content copied into `.task-temp/ts-combat-copy-20260628/input`
- Readiness transition tested: `fixture-write validated; copied-data rehearsal scaffold ready` -> `copied-data rollback ready`

## Safety Confirmation

- Repo root: current `campaign_player_wiki` Codex worktree
- Rehearsal root: `.task-temp/ts-combat-copy-20260628`
- Copied SQLite: `.task-temp/ts-combat-copy-20260628/input/player_wiki.sqlite3`
- Copied campaigns dir: `.task-temp/ts-combat-copy-20260628/input/campaigns`
- Backup archive: `.task-temp/ts-combat-copy-20260628/backup/player-wiki-backup.zip`
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: not available in this worktree after integration merges through `39c15d8`
- Refused paths: no owner checkout, tracked `campaigns/<slug>/`, vault, Fly, staging, or production paths were used

Harness path guard:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths `
  --root .\.task-temp\ts-combat-copy-20260628 `
  --db .\.task-temp\ts-combat-copy-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-combat-copy-20260628\input\campaigns `
  --backup-archive .\.task-temp\ts-combat-copy-20260628\backup\player-wiki-backup.zip
```

Result: passed; all resolved paths stayed under the rehearsal root.

## Baseline Evidence

Baseline harness snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-combat-copy-20260628 `
  --label pre `
  --family combat `
  --db .\.task-temp\ts-combat-copy-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-combat-copy-20260628\input\campaigns
```

Baseline SQLite counts:

| Table | Count |
| --- | ---: |
| `campaign_combat_trackers` | 1 |
| `campaign_combatants` | 2 |
| `campaign_combat_conditions` | 1 |
| `campaign_combatant_resource_counters` | 1 |
| `campaign_combatant_resource_notes` | 1 |
| `character_state` | 1 |

Baseline sampled tracker row:

```json
{"campaign_slug":"linden-pass","round_number":3,"current_combatant_id":501,"revision":12,"updated_by_user_id":77}
```

Baseline API samples saved under the ignored rehearsal root:

- `pre/player-combat-sample.json`
- `pre/dm-status-controls-sample.json`
- `pre/live-state-sample.json`
- `pre/live-state-unchanged-sample.json`
- `pre/sql-samples.json`

## Backup

Backup command:

```powershell
Compress-Archive -LiteralPath `
  .\.task-temp\ts-combat-copy-20260628\input\player_wiki.sqlite3, `
  .\.task-temp\ts-combat-copy-20260628\input\campaigns `
  -DestinationPath .\.task-temp\ts-combat-copy-20260628\backup\player-wiki-backup.zip `
  -Force
```

Backup SHA-256:

```text
174DFCFC77C9DB2119E664BDCC58C3C94F813195061A341BAACF0324DB65599C
```

## Mutation

Runtime:

```powershell
$env:CPW_DB_PATH = ".task-temp/ts-combat-copy-20260628/input/player_wiki.sqlite3"
$env:CPW_CAMPAIGNS_DIR = ".task-temp/ts-combat-copy-20260628/input/campaigns"
node apps/api/dist/server.js
```

Representative request sequence, all against copied data:

| Step | Result |
| --- | --- |
| Set current to existing player combatant | HTTP 200 |
| Advance turn | HTTP 200 |
| Clear tracker before representative add sequence | HTTP 200 |
| Add player combatant | HTTP 200 |
| Add manual NPC combatant | HTTP 200 |
| Add DM Content statblock combatant | HTTP 200 |
| Add Systems monster combatant | HTTP 200 |
| Stale turn revision guard | HTTP 409 `state_conflict` |
| Update Systems monster turn | HTTP 200 |
| Update Systems monster vitals | HTTP 200 |
| Update player HP mirror | HTTP 200 |
| Update Systems monster action resources | HTTP 200 |
| Update Systems monster source-backed resource counter | HTTP 200 |
| Create condition | HTTP 200 |
| Update condition | HTTP 200 |
| Delete condition | HTTP 200 |
| Delete Systems monster combatant | HTTP 200 |
| Clear tracker after post-mutation sample | HTTP 200 |

Coverage gained:

- player-character add and selected-PC `character_state` mirror through HP/temp HP update;
- manual NPC add;
- source-backed DM Content and Systems combatant adds with resource counters and mechanic notes;
- row-level stale revision conflict;
- turn, vitals, movement/action economy, NPC resource counter, condition create/update/delete, combatant delete, and clear paths;
- sampled player Combat, DM status/controls, live-state, and unchanged live-state payloads.

Post-mutation SQLite counts after final clear:

| Table | Count |
| --- | ---: |
| `campaign_combat_trackers` | 1 |
| `campaign_combatants` | 0 |
| `campaign_combat_conditions` | 0 |
| `campaign_combatant_resource_counters` | 0 |
| `campaign_combatant_resource_notes` | 0 |
| `character_state` | 1 |

This post state proves clear/delete removed combatant-dependent condition, counter, and note rows while retaining the linked character state row for rollback comparison.

## Restore

Restore command:

```powershell
Remove-Item -LiteralPath .\.task-temp\ts-combat-copy-20260628\input\player_wiki.sqlite3 -Force
Remove-Item -LiteralPath .\.task-temp\ts-combat-copy-20260628\input\campaigns -Recurse -Force
Expand-Archive -LiteralPath .\.task-temp\ts-combat-copy-20260628\backup\player-wiki-backup.zip `
  -DestinationPath .\.task-temp\ts-combat-copy-20260628\input `
  -Force
```

Restore snapshot command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot `
  --root .\.task-temp\ts-combat-copy-20260628 `
  --label restore `
  --family combat `
  --db .\.task-temp\ts-combat-copy-20260628\input\player_wiki.sqlite3 `
  --campaigns-dir .\.task-temp\ts-combat-copy-20260628\input\campaigns
```

## Equivalence

Harness compare:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare `
  --before .\.task-temp\ts-combat-copy-20260628\pre\manifest.json `
  --after .\.task-temp\ts-combat-copy-20260628\restore\manifest.json
```

Result:

```json
{"equal":true,"changed_files":[],"sqlite_equal":true}
```

Additional equality checks:

| Evidence | Pre hash | Restore hash |
| --- | --- | --- |
| SQL samples | `DE36530192FDE9A05C607E0A9CBE40A28C33FE27FE8581B7FA59609BC566B587` | `DE36530192FDE9A05C607E0A9CBE40A28C33FE27FE8581B7FA59609BC566B587` |
| Player Combat payload | `E2B804EA5AD9E170E04628E69F9453EA9938891F1744B53700B4DBD37FB50ED9` | `E2B804EA5AD9E170E04628E69F9453EA9938891F1744B53700B4DBD37FB50ED9` |
| DM status/controls payload | `A10407F03CD7CE4FF9ABEC9AE777A7561ED11E597592FD7CC85AA365A05CE70B` | `A10407F03CD7CE4FF9ABEC9AE777A7561ED11E597592FD7CC85AA365A05CE70B` |
| Combat live-state payload | `A10407F03CD7CE4FF9ABEC9AE777A7561ED11E597592FD7CC85AA365A05CE70B` | `A10407F03CD7CE4FF9ABEC9AE777A7561ED11E597592FD7CC85AA365A05CE70B` |

Known acceptable differences: none.

Unexpected differences: none.

## Decision

- Result: pass
- Label before: `fixture-write validated; copied-data rehearsal scaffold ready`
- Label after: `copied-data rollback ready; staging snapshot required`
- Production/staging implication: no staging write, production write, Fly sync, deploy, PR, merge, or cutover is approved by this transcript.
- Follow-up required: user-approved staging-equivalent snapshot rehearsal before Combat can claim `staging snapshot ready`.
