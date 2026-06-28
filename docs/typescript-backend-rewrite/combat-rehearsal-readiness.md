# Combat Rehearsal Readiness Scaffold

Last updated: 2026-06-28

## Decision

The TypeScript Combat write family has a concrete copied-data rehearsal scaffold,
but it is not yet copied-data rollback ready.

The scaffold adds a Combat-specific transcript guide to
`scripts/staging_rehearsal_harness.py`. It names the Combat routes/actions,
baseline evidence, mutation sequence, restore equivalence requirements, and the
honest label transition. It does not run TypeScript mutations, backup commands,
restore commands, Fly commands, deploys, live syncs, or staging writes.

## Current Label

Current status for this route family: `fixture-write validated; copied-data
rehearsal scaffold ready`.

Formal readiness label after a passing copied-data transcript:
`copied-data rollback ready`.

## Evidence Added

- `scripts/staging_rehearsal_harness.py guide --family combat` prints the
  Combat-specific transcript guide.
- `scripts/staging_rehearsal_harness.py init --family combat --dry-run` includes
  the same guide in the transcript preview.
- `tests/test_staging_rehearsal_harness.py` verifies the Combat transcript guide
  includes concrete write routes, restore equivalence requirements, and the
  guarded label transition.
- The same test module verifies Combat snapshots capture tracker, combatant,
  condition, resource, note, and linked `character_state` tables and detect
  SQLite drift without file drift.

## Dry-Run Command

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init `
  --rehearsal-id ts-combat-copy-YYYYMMDD `
  --family combat `
  --source-description "copied combat snapshot under disposable rehearsal root" `
  --source-approval "operator-approved copied data only" `
  --dry-run
```

## Remaining Gate

Before Combat can claim `copied-data rollback ready`, run the scaffold against a
disposable copied data root and record a completed transcript that proves:

- copied path guard passes for SQLite, campaign content, and backup archive;
- pre-mutation evidence captures player Combat, Combat live-state, DM Status,
  and DM Controls samples;
- approved Combat mutations cover player-character mirrors, manual NPC writes,
  source-backed combatant resources, conditions, turn flow, deletes, and clear;
- restore returns tracker, combatant, condition, resource, note, and linked
  character-state evidence to baseline or lists exact accepted differences;
- no live Fly volume, production SQLite, production campaign content, owner
  checkout, vault source, or tracked `campaigns/<campaign-slug>/` content is
  used.
