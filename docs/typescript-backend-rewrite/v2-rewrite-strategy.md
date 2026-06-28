# V2 Rewrite Strategy

Last updated: 2026-06-28

Status: adopted planning direction; implementation not started

## Decision

The TypeScript rewrite is a true V2 application rewrite, not a Flask parity
port. The rewrite branch does not affect the live app, so implementation should
optimize for the V2 foundation we want rather than reproducing every Flask-era
route, page shape, or implementation pattern.

Flask behavior remains useful as evidence about current data, permissions,
workflow intent, and migration risk. It is not the target architecture.

The hard compatibility requirement is non-destructive migration of current app
data into V2 structures, with enough validation and rollback evidence to trust a
future cutover.

## Non-Negotiables

V2 must preserve:

- account, role, membership, assignment, and view-as security semantics;
- player-safe versus DM-only visibility and publication boundaries;
- current campaign data without destructive conversion;
- durable character identity, ownership, definitions, imports, mutable state,
  portraits, notes, inventory, progression history, and source refs;
- published articles, sections, assets, images, page metadata, backlink/provenance
  relationships, and current-session gates;
- Systems sources, source policy, shared libraries, overrides, custom entries,
  imports, and rules metadata;
- Session, Combat, and DM Content state worth carrying forward;
- backup, restore, rollback, and operator observability.

V2 does not need to preserve:

- Flask route internals or handler structure;
- Flask page layout assumptions;
- HTML error shapes except where a compatibility edge explicitly requires them;
- class-by-class DND progression branches;
- route-by-route TypeScript implementation as the default measure of progress;
- legacy browser JSON routes beyond the cutover or migration window unless they
  are intentionally promoted.

## V2 Foundation Goals

The V2 foundation should provide:

- canonical domain models for Campaign, User, Membership, Content, Asset,
  Character, Systems Entry, Session, Combat, DM Content, and Audit/History;
- typed service contracts that routes and frontend workspaces consume;
- a data-driven DND progression kernel instead of class-by-class advancement;
- a shared Character read/widget model consumed by Character, Session Character,
  and Combat selected-PC views;
- live Session and Combat services with revision-aware mutation contracts;
- content and asset repositories that hide Markdown/file/mirror mechanics;
- Systems metadata normalization that can drive rules, character choices, and
  widgets;
- a frontend app shell and adaptive workspaces designed for live tabletop use;
- migration/import tools that can explain every transformed legacy record.

## Legacy Data Bridge

The migration bridge owns current data compatibility. It should be idempotent,
auditable, and non-destructive.

Legacy inputs include:

- Flask SQLite tables for users, sessions, memberships, settings, character
  state, Systems rows, Session, Combat, DM Content, publication state, and audit
  data;
- character `definition.yaml`, `import.yaml`, portraits, and character assets;
- published Markdown/content folders, page metadata, images, and protected
  assets;
- campaign configuration and visibility files;
- sanitized fixture data and copied-data rehearsal snapshots.

The V2 bridge should produce:

- V2 schema rows or documents without mutating the legacy source;
- mapping manifests from legacy ids/paths/refs to V2 ids/refs;
- validation reports for missing refs, unsupported mechanics, permission
  mismatches, and data that needs operator review;
- repeatable dry-run output;
- rollback/export instructions;
- fixture, copied-data, and staging-equivalent evidence before live cutover.

## Implementation Posture

Use parity selectively:

- **Use parity tests** for security, visibility, data migration integrity,
  rollback, and user-critical workflows.
- **Use golden examples** to protect existing character/content/session/combat
  behavior while replacing internals with V2 services.
- **Do not use parity** as permission to widen temporary route or class-specific
  architecture.

Prefer V2 work in this order:

1. Define the canonical domain/service contract.
2. Define the legacy import/migration adapter into that contract.
3. Prove imported legacy data can drive the V2 workflow.
4. Add compatibility adapters only when current Gen2, cutover, or rollback needs
   them.
5. Retire or quarantine compatibility once V2 owns the workflow.

## Architecture Implications

- `/api/v1` should be treated as a compatibility edge unless explicitly promoted
  as a permanent V2 API.
- Route seed progress is not the main progress metric. V2 domain coverage,
  migration coverage, and workflow coverage matter more.
- Character work should prioritize the V2 Character model, read/widget payloads,
  persistence boundary, and DND progression kernel.
- Combat modernization depends on stable Character read/widget payloads.
- Content work should decide the V2 content and asset model before widening
  Flask-shaped content writes.
- SQLite work should decide V2 schema ownership and import mechanics instead of
  only proving Flask-current schema preflight.

## V2 Readiness Metrics

Track progress by:

- V2 domain model coverage;
- legacy data import coverage;
- migration validation coverage;
- workflow coverage on imported data;
- security and visibility preservation;
- rollback/export readiness;
- frontend workspace readiness;
- compatibility shims remaining and their retirement decisions.

Route parity counts remain useful diagnostics, not the scoreboard.
