# Current State Index

Last updated: 2026-06-25

This directory is the fast reference layer for the current Campaign Player Wiki app contract. It is meant for implementation, audits, and roadmap close-out. Prefer these atomized docs over old roadmap completion notes when deciding what the app does now.

## How To Use

- Start here when a task asks how a surface currently works.
- Open only the docs that match the surface being changed or audited.
- Treat `.local/roadmaps/*.md` as active backlog, not as source of current behavior.
- When a backlog item ships, update the matching current-state doc before closing or archiving that item.
- Keep historical roadmap files as audit trails. Do not rely on completed historical checklist prose as current truth unless the current-state doc points back to it.

## Current-State Docs

- [Characters Overview](characters-overview.md): shared character storage, route lanes, permissions, mutable state, save/revision rules, and cross-system conventions.
- [Characters: DND-5E](characters-dnd5e.md): DND-5E native/imported support matrix, authoring lanes, read/session/combat behavior, spellcasting, equipment, and known limits.
- [Characters: Xianxia](characters-xianxia.md): Xianxia definition/state model, create/import, read/session pages, Cultivation, Realm Ascension, approval records, and deferred automation.

## Existing Contract Docs

- [API v1](../api-v1.md): JSON API and browser/API contract reference.
- [Gen2 Migration Readiness](../gen2-migration-readiness.md): current `/app-next` hosting, route ownership, and migration readiness notes.
- [Frontend UX Style Guide](../frontend-ux-style-guide.md): app-wide UX, action, form, density, accessibility, and feedback conventions.
- [Frontend UX Audit Checklist](../frontend-ux-audit-checklist.md): page-by-page UX audit checklist.

## Local Backlog Entry Points

Local roadmaps are intentionally not tracked:

- `.local/roadmaps/INDEX.md`
- `.local/roadmaps/feedback-inbox.md`
- `.local/roadmaps/character-backlog.md`

## Migration Notes

The older `.local/*roadmap.md` files are historical until each domain is migrated. During migration, copy only active unchecked work into the new `.local/roadmaps/*-backlog.md` files and summarize shipped behavior in this `docs/current-state/` directory.
