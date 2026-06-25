# TypeScript Backend Rewrite Charter

Last updated: 2026-06-25

Status: adopted for the `rewrite/typescript-backend` branch

## Decision

Campaign Player Wiki will explore and implement a staged TypeScript backend replacement on the `rewrite/typescript-backend` branch. The rewrite is a replacement track, not an incremental Flask cleanup. Flask remains the production backend until TypeScript proves parity, migration safety, operational readiness, and rollback safety.

## Scope

The rewrite must preserve the current app contract documented in `docs/current-state/INDEX.md` and `docs/api-v1.md`. Required parity includes:

- authenticated account, admin, membership, assignment, and view-as behavior;
- player-safe vs DM-only campaign visibility;
- published wiki browsing, publishing, assets, current-session gates, and Markdown mirrors;
- DND-5E and Xianxia character definition/state separation and supported workflows;
- Systems source policy, shared library, custom entries, overrides, managed seed behavior, and imports;
- live Session chat, staged/revealed articles, logs, image handling, and revision polling;
- Combat tracker, player/DM surfaces, source-backed combatants, conditions, revisions, and character-state writes;
- DM Content statblocks, custom conditions, Player Wiki management, Systems lane, and staged articles;
- local Windows development, SQLite-backed private deployment, Fly deployment, backup, restore, and rollback workflows.

## Replacement Strategy

The approved strategy is staged backend replacement.

1. Build TypeScript packages and services beside the existing app, not inside React page code.
2. Start with read-only compatibility readers against current fixtures, SQLite shape, and file-backed campaign content.
3. Add golden parity tests comparing selected Python and TypeScript outputs before wiring Gen2 to TypeScript endpoints.
4. Add controlled TypeScript write paths only after backup, dry-run, and rollback checks exist for the affected data.
5. Cut production over only after a copied-data rehearsal and player/DM workflow smoke pass.

Full production replacement is the destination, but not the first integration mode.

## Freeze And Dual-Maintenance Rules

- There is no immediate global feature freeze while Flask remains production.
- New Flask behavior may continue only when it updates the relevant current-state docs and is added to the TypeScript parity inventory or marked as an approved rewrite exception.
- Once TypeScript read/write parity reaches cutover rehearsal, Flask feature work should enter a hard freeze except for critical fixes and data-safety repairs.
- Any critical Flask fix during the hard freeze must receive a matching TypeScript follow-up before cutover can proceed.

## Cutover Workflows

The rewrite is not eligible for production cutover until these workflows pass against copied or staging data:

- sign in, sign out, account settings, admin user management, campaign picker, and view-as;
- Campaign Home, wiki section, wiki page detail, global search, protected assets, and Campaign Help;
- DM Content Player Wiki, statblocks, conditions, Systems management, and staged articles;
- Systems browse, source pages, entry detail, custom entries, source policy, and import review paths;
- Character roster, DND-5E detail/edit/session flows, Xianxia detail/import/cultivation flows, and portrait handling;
- player Session, DM Session, chat audience filters, staged/revealed articles, logs, and live polling;
- player Combat, DM Status, DM Controls, source-backed combatants, selected-PC state writes, and live polling;
- local production build, `/healthz`, backup, restore, migration dry-run, staging deploy, and rollback smoke.

## Rollback Requirement

Rollback to the Flask app is required until at least one full rehearsal passes and a post-cutover observation window is approved. The rollback plan must preserve:

- the last known-good Flask commit or image;
- a pre-cutover SQLite and campaign-content backup;
- instructions for repointing Fly or the local runner to Flask;
- a data-delta decision for any writes accepted by TypeScript before rollback.

## Branch And Spec Ownership

- Active implementation branch: `rewrite/typescript-backend`.
- Tracked rewrite artifacts live under `docs/typescript-backend-rewrite/`.
- The local active task queue remains `.local/roadmaps/typescript-backend-rewrite-roadmap.md` until a broader project-management location is chosen.
- Experimental stack spikes must stay in `.task-temp` or an explicitly approved isolated workspace until the stack decision record approves a tracked workspace layout.

## Exit Criteria For This Charter

This charter satisfies Phase 0 when the tracked spec home exists, the branch strategy is explicit, staged replacement is chosen, dual-maintenance rules are written, cutover workflows are named, and rollback is mandatory.
