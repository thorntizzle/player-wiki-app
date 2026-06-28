# TypeScript Cutover Freeze And Drift Audit

Last updated: 2026-06-28

Status: no-runtime final pre-rehearsal checklist and evidence contract

## Boundary

This checklist does not approve a PR, merge, deploy, Fly action, live SQLite
sync, live API write, or production cutover. Flask remains the production
authority until a user-approved cutover window passes all route, data, ops, and
rollback gates.

Use this checklist immediately before any cutover rehearsal and again after
every integration-branch advance during the freeze window. It is intentionally
source-only unless a command explicitly says it uses local sanitized fixtures or
copied/staging-approved data.

## Owners

| Role | Owns | Required sign-off |
| --- | --- | --- |
| Rewrite cutover coordinator | Declares the freeze window, records the baseline commit, collects the transcript, and makes the go/no-go recommendation. | Confirms no unapproved Flask feature work entered during freeze. |
| Route/API parity owner | Reviews `docs/api-v1.md`, route snapshots, route seed, TypeScript route manifest, and `parity-inventory.md` for drift. | Confirms route inventory, documented API contract, and TypeScript seed/manifest agree or lists approved exceptions. |
| Current-state doc owner | Checks `docs/current-state/INDEX.md` plus touched current-state docs for behavior added since the last audit. | Confirms current product contract is reflected in rewrite parity evidence. |
| Data/rollback owner | Checks copied-data or staging snapshot transcripts, rollback runbook, and data-delta decisions. | Confirms write-family labels are not overstated and rollback evidence is current. |
| Ops owner | Checks local wrapper, build, health, packaging, backup, restore, and environment notes. | Confirms all evidence is no-live unless the user explicitly approved staging/live action. |

If one person fills multiple roles, the transcript must still record each role
decision separately.

## Evidence Inputs

The final audit must identify the exact branch and commit for each input:

- `docs/current-state/INDEX.md` and the current-state docs named by any touched
  route family.
- `docs/api-v1.md`.
- `docs/typescript-backend-rewrite/parity-inventory.md`.
- `docs/typescript-backend-rewrite/route-snapshots.json`.
- `docs/typescript-backend-rewrite/route-snapshots.md`.
- `docs/typescript-backend-rewrite/typescript-route-seed.json`.
- `docs/typescript-backend-rewrite/route-drift-audit-2026-06-28.md` or a newer
  final drift transcript.
- `apps/api/src/routes.ts` after TypeScript build output is regenerated.
- `apps/api/tests/route-parity.mjs`.
- `docs/typescript-backend-rewrite/cutover-readiness.md`.
- `docs/typescript-backend-rewrite/rollback-cutover-runbook.md`.
- The latest copied-data or staging transcript for every write family promoted
  above `fixture-write validated`.
- The local roadmap `.local/roadmaps/typescript-backend-rewrite-roadmap.md`
  when present in the operator worktree. If absent, record that absence; do not
  create or edit ignored roadmap files just to satisfy this audit.

## Freeze Entry Checklist

1. Fetch and record the integration baseline.

   ```powershell
   git fetch origin --prune
   git status --short --branch
   git rev-parse HEAD
   git rev-parse origin/rewrite/ts-phase3-integration
   ```

2. Declare the freeze scope in the transcript: branch, commit, expected rehearsal
   window, owners, and route/write families in scope.
3. Stop non-critical Flask feature work for in-scope families. Documentation
   fixes, tests, and TypeScript parity fixes may continue only when they are
   owned and recorded.
4. Confirm every Flask change since the previous drift audit has one of these
   outcomes:
   - current-state docs updated plus parity inventory updated;
   - route snapshot/API docs updated and route parity evidence rerun;
   - approved rewrite exception with owner, reason, and follow-up date;
   - critical Flask-only fix with a matching TypeScript follow-up blocking
     cutover until resolved.

## No-Runtime Input Audit

Run the lightweight source-input audit first. It checks that the required
evidence files exist, the tracked JSON route fixtures parse, and the key
markdown sections used by the checklist are present.

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\cutover_freeze_drift_audit.py
```

A pass here is not route parity. It only proves the final audit has the expected
local inputs before heavier checks run.

## Drift Command Checklist

Run these on the frozen integration commit and record the exact command, result,
and failure classification.

| Command | Required result before rehearsal | Notes |
| --- | --- | --- |
| `python .\scripts\cutover_freeze_drift_audit.py` | Pass | Source-input scaffold only. |
| `python .\scripts\route_snapshots.py --check` | Pass | Flask authority declarations match `route-snapshots.json`. |
| `.\local.ps1 -Action ts-api-check` | Pass | Preferred wrapper because it resolves local Node/npm and runs route snapshot, typecheck, build, schema checks, migration proof, and route parity. |
| `npm --prefix apps/api run test:route-parity` after build | Pass | Direct manifest/seed/snapshot lockstep proof when dependencies are available. |
| Focused family tests named by changed evidence | Pass or explicitly deferred with owner | Required for any family whose parity label or route behavior changed. |
| `git diff --check` | Pass | Whitespace hygiene for the evidence commit. |

Tooling or environment failures may be classified as such, but they do not make
the gate green. They require either a rerun in a working environment or an
explicit no-go/defer decision.

## Go/No-Go Gates

The cutover rehearsal is a no-go when any of these are true:

- `route_snapshots.py --check` fails.
- TypeScript route parity fails, or build output is stale, missing, or generated
  from a different commit.
- `docs/api-v1.md`, current-state docs, route snapshots, route seed, and
  `parity-inventory.md` disagree without an approved exception.
- A Flask behavior change during freeze lacks both current-state documentation
  and TypeScript parity follow-up.
- A write family is labeled above its evidence level.
- Rollback evidence does not name the last known-good Flask target, backups,
  restore path, and TypeScript data-delta decision.
- Any transcript or tracked file includes secrets, personal vault paths, real Fly
  identifiers, live database paths, local campaign mirrors, or proprietary vault
  content.
- A required owner sign-off is missing.

The rehearsal may proceed only when every no-go item is resolved and the
transcript explicitly states that no PR, merge, deploy, Fly command, live API
write, live SQLite sync, or production cutover was performed unless separately
approved by the user.

## Late Flask Fixes

Critical Flask fixes are allowed during hard freeze only for data safety,
security, access control, severe production breakage, or rollback integrity.
Each fix must add a freeze exception entry with:

- Flask commit and files changed.
- User-visible behavior or data-safety impact.
- Current-state/API docs updated or reason no docs changed.
- Route snapshot or parity inventory impact.
- Matching TypeScript owner and target commit.
- Rerun commands and results.
- Decision: resolved before rehearsal, approved defer, or no-go.

Cutover remains blocked until the TypeScript follow-up lands or an explicit
approved exception states why Flask and TypeScript may differ during rehearsal.

## Required Transcript

Store the final audit transcript under `docs/typescript-backend-rewrite/` with a
date in the filename. It must include:

- Branch, commit SHA, upstream, and fetch time.
- Owners and sign-offs.
- Evidence input versions and optional roadmap presence/absence.
- Route counts from snapshot, seed, and TypeScript manifest.
- All commands run, results, and failure classifications.
- Freeze exceptions and their resolution status.
- Go/no-go decision with remaining blockers.
- Sanitization statement confirming no secrets, personal vault paths, real Fly
  identifiers, live DB paths, local campaign mirrors, or proprietary vault
  content.
- Explicit statement that no PR, merge, deploy, Fly command, live API write,
  live SQLite sync, or production cutover occurred unless separately approved.

This checklist closes the process/scaffolding gap only. The freeze gate is not
complete until the transcript is executed on the final integration commit.
