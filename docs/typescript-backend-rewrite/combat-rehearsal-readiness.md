# Combat Rehearsal Readiness

Last updated: 2026-06-28

## Decision

The TypeScript Combat write family has passed a no-live copied-fixture
backup/mutate/restore equivalence rehearsal. Combat can now claim
`copied-data rollback ready`; it is not `staging snapshot ready`.

The rehearsal used only sanitized fixture data copied into `.task-temp`, the
guarded staging rehearsal harness, and a local TypeScript API runtime pointed at
the copied SQLite/content paths. It did not run Fly commands, deploys, live
syncs, staging writes, production writes, vault reads, or owner-checkout
mutations.

## Current Label

Current status for this route family: `copied-data rollback ready; staging
snapshot required`.

Previous status: `fixture-write validated; copied-data rehearsal scaffold
ready`.

## Evidence Added

- `combat-copied-data-rehearsal-2026-06-28.md` records the completed local
  transcript. It proves copied path guard, pre snapshot, representative
  TypeScript Combat mutations, post snapshot, restore, file/table/row sample
  equivalence, and API payload equivalence.
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

## Staging Gate

Before Combat can claim `staging snapshot ready`, run the scaffold against a
user-approved staging-equivalent copied snapshot and record a completed
transcript that proves:

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

The 2026-06-28 transcript satisfies those checks for sanitized copied fixtures
only. It is sufficient for `copied-data rollback ready`, not staging or
production approval.
