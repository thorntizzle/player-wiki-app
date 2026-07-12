# Current State Index

Last updated: 2026-07-10

This directory is the fast reference layer for the current Campaign Player Wiki app contract. It is meant for implementation, audits, and roadmap close-out. Prefer these atomized docs over old roadmap completion notes when deciding what the app does now.

## How To Use

- Start here when a task asks how a surface currently works.
- Open only the docs that match the surface being changed or audited.
- Treat `.local/roadmaps/*.md` as active backlog, not as source of current behavior.
- Current-state docs own the present app contract only. They may describe current boundaries in present-tense terms, but future implementation goals, unresolved follow-up, and desired behavior belong in the active backlog files.
- When a backlog item ships, update the matching current-state doc before closing or archiving that item.
- Keep historical roadmap files as audit trails. Do not rely on completed historical checklist prose as current truth unless the current-state doc points back to it.

## Current-State Docs

- [Flask Architecture And Ownership](flask-architecture.md): application entrypoints and composition, domain/persistence/presentation ownership, storage boundaries, preserved contracts, and transitional architecture limits.
- [Admin, Auth, And Visibility](admin-auth.md): sign-in, account settings, roles, membership, assignment, audit, and campaign visibility behavior.
- [Combat](combat.md): player combat, DM status, encounter controls, combatant source identity, live updates, and current automation boundaries.
- [DM Content](dm-content.md): Statblocks, Player Wiki management, Systems management lane, Staged Articles, Conditions, and cross-surface handoffs.
- [Flask Browser App](flask-browser.md): browser route ownership, Flask template shell behavior, loading cover behavior, browser/API links, and the retired preview-route boundary.
- [Live Session](live-session.md): player Session, DM Session, Session Character, staged/revealed articles, logs, and polling behavior.
- [Ops And Fly Deployment](ops-deploy.md): local wrapper usage, Fly deployment shape, SQLite volume boundaries, and verification expectations.
- [Published Wiki And Publishing](published-wiki.md): player-facing wiki pages, section/grouping conventions, images, Campaign Home, and publication/removal guardrails.
- [Rich-Text Security](rich-text-security.md): central rich-text sanitization, write and legacy-render boundaries, template sink policy, preserved contracts, and verification evidence.
- [Systems Wiki](systems.md): source policy, shared libraries, imports, RULES/book slices, custom entries, overrides, and search behavior.
- [Characters Overview](characters-overview.md): shared character storage, route lanes, permissions, mutable state, save/revision rules, and cross-system conventions.
- [Characters: DND-5E](characters-dnd5e.md): DND-5E native/imported support matrix, authoring lanes, read/session/combat behavior, spellcasting, equipment, and known limits.
- [Characters: Xianxia](characters-xianxia.md): Xianxia definition/state model, create/import, read/session pages, Cultivation, Realm Ascension, approval records, and deferred automation.

## Existing Contract Docs

- [API v1](../api-v1.md): JSON API and browser/API contract reference.
- [Frontend UX Style Guide](../frontend-ux-style-guide.md): app-wide UX, action, form, density, accessibility, and feedback conventions.
- [Frontend UX Audit Checklist](../frontend-ux-audit-checklist.md): page-by-page UX audit checklist.

## Local Backlog Entry Points

Local roadmaps are intentionally not tracked:

- `.local/roadmaps/INDEX.md`
- `.local/roadmaps/feedback-inbox.md`
- `.local/roadmaps/flask-only-tanstack-removal-plan.md`
- `.local/roadmaps/ux-backlog.md`
- `.local/roadmaps/publishing-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`
- `.local/roadmaps/systems-backlog.md`
- `.local/roadmaps/session-backlog.md`
- `.local/roadmaps/combat-backlog.md`
- `.local/roadmaps/character-backlog.md`
- `.local/roadmaps/xianxia-backlog.md`
- `.local/roadmaps/ops-backlog.md`

## Migration Notes

The older `.local/*roadmap.md` files are historical until each domain is migrated. During migration, copy only active unchecked work into the new `.local/roadmaps/*-backlog.md` files and summarize shipped behavior in this `docs/current-state/` directory.
