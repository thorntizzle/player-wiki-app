# TypeScript Backend Rewrite Charter

Last updated: 2026-06-28

Status: adopted for the TypeScript rewrite track; amended for V2-first strategy

## Decision

Campaign Player Wiki will implement a true V2 TypeScript app on the rewrite
track. The rewrite is a replacement track, not an incremental Flask cleanup and
not a route-by-route parity port. Flask remains the production backend until V2
proves legacy data migration safety, security/visibility preservation,
operational readiness, workflow coverage, and rollback safety.

## Scope

The rewrite must preserve current app data and safety contracts while allowing
V2 to improve architecture, API shape, frontend workflow design, and internal
domain models. Required preservation includes:

- authenticated account, admin, membership, assignment, and view-as behavior;
- player-safe vs DM-only campaign visibility;
- non-destructive migration of published wiki pages, sections, assets,
  current-session gates, provenance, and relevant Markdown/file metadata;
- non-destructive migration of DND-5E and Xianxia character definitions, import
  metadata, portraits, source refs, mutable state, and history;
- non-destructive migration of Systems source policy, shared library, custom
  entries, overrides, managed seed behavior, imports, and rules metadata;
- non-destructive migration of live Session chat, staged/revealed articles, logs,
  image refs, and revision/polling state worth carrying forward;
- non-destructive migration of Combat tracker state, source-backed combatants,
  conditions, revisions, and character-state links worth carrying forward;
- non-destructive migration of DM Content statblocks, custom conditions, Player
  Wiki management state, Systems lane state, and staged articles;
- local Windows development, SQLite-backed private deployment, Fly deployment, backup, restore, and rollback workflows.

Flask route shape, page structure, HTML error bodies, and one-off implementation
patterns are not preservation requirements unless a V2 compatibility decision
explicitly promotes them.

## Replacement Strategy

The approved strategy is V2-first replacement with a legacy data bridge.

1. Define canonical V2 domain models, services, and frontend workspace contracts.
2. Build import/migration adapters from current SQLite, YAML, Markdown, and asset
   storage into V2 structures without mutating the legacy source.
3. Use Flask parity and golden examples selectively to validate migrated data,
   security, visibility, and user-critical workflows.
4. Add compatibility adapters only where current Gen2, cutover, or rollback
   requires them.
5. Add V2 write paths only after backup, dry-run, migration validation, and
   rollback checks exist for the affected data.
6. Cut production over only after copied-data and staging-equivalent migration
   rehearsals plus player/DM workflow smoke pass.

Full production replacement is the destination, but not the first integration mode.

## Freeze And Dual-Maintenance Rules

- There is no immediate global feature freeze while Flask remains production.
- New Flask behavior may continue only when it updates the relevant current-state
  docs and is added to the V2 migration/workflow inventory or marked as an
  approved rewrite exception.
- Once V2 migration/workflow readiness reaches cutover rehearsal, Flask feature
  work should enter a hard freeze except for critical fixes and data-safety
  repairs.
- Any critical Flask fix during the hard freeze must receive a matching TypeScript follow-up before cutover can proceed.

## Cutover Workflows

The rewrite is not eligible for production cutover until these workflows pass
against migrated copied or staging data:

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

This charter satisfies Phase 0 when the tracked spec home exists, the branch strategy is explicit, V2-first replacement with a legacy data bridge is chosen, dual-maintenance rules are written, cutover workflows are named, and rollback is mandatory.
