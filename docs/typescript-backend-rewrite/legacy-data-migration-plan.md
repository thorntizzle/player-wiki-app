# Legacy Data Migration Plan

Last updated: 2026-06-28

Status: planning contract; no live migration approved

## Purpose

V2 does not need to mimic Flask internals, but it must carry current app data
forward safely. This plan defines the non-destructive migration bridge from
Flask-era SQLite, YAML, Markdown, and asset storage into V2 structures.

The migration bridge is a first-class part of the rewrite. It is not a temporary
test helper and not a destructive schema migration.

## Migration Principles

- **Non-destructive:** legacy SQLite files, character folders, published content,
  and assets are read as source inputs, not rewritten in place.
- **Idempotent:** the same source snapshot can be imported repeatedly into an
  empty or reset V2 target with stable results.
- **Mapped:** every imported row/file/ref should have a manifest entry linking
  legacy identity to V2 identity.
- **Audited:** unsupported, ambiguous, or lossy transformations produce review
  records instead of silent best guesses.
- **Reversible:** rollback can return to the last known-good Flask app and the
  untouched legacy data snapshot.
- **Rehearsed:** fixture, copied-data, and staging-equivalent imports must pass
  before live cutover.

## Data Families

| Family | Legacy source | V2 migration concern | Minimum validation |
| --- | --- | --- | --- |
| Users and auth | SQLite users, sessions, settings, password/reset state, roles | Preserve account identity, disabled state, app admin rights, settings that still matter, and safe session/token policy. | User counts, admin membership, disabled users, login/auth smoke, settings migration report. |
| Campaign access | SQLite campaign memberships, assignments, visibility/control rows, config files | Preserve player/DM/admin visibility, assignments, view-as semantics, and campaign selection. | Role matrix, assigned character access, hidden/DM-only content checks. |
| Published content | Markdown/content folders, publication tables, page metadata, sections, backlinks, provenance | Map article ids/paths/sections/assets into V2 content model without losing published/unpublished/current-session state. | Page counts, section grouping, render smoke, backlink/provenance checks, search visibility checks. |
| Assets and portraits | Protected campaign assets, character portraits, session article images, frontmatter/image refs | Decide V2 asset policy, preserve refs, media types, alt/caption metadata, and access gates. | Asset manifest, byte/media checks, portrait resolution, article image render, missing/ref review report. |
| Characters | `definition.yaml`, `import.yaml`, character assets, SQLite `character_state`, assignments | Preserve stable definition facts, import provenance, mutable state, notes, resources, inventory, spell slots, equipment, progression history, and source refs. | Character manifest, DND/Xianxia read smoke, state revision import, source-ref validation, unsupported mechanic report. |
| Systems | SQLite Systems rows, source policy, shared library imports, overrides, custom entries, item mechanics | Normalize rules metadata for V2 while preserving visibility, source ownership, overrides, custom content, and import history. | Source policy matrix, entry counts by source/type, override checks, representative rules/item/monster lookups. |
| Session | SQLite session state, chat messages, staged/revealed articles, logs, images | Preserve live/closed session state worth carrying forward, audience filters, staged/revealed article refs, and logs. | Audience-filter smoke, staged/revealed counts, log samples, image refs, active/inactive state. |
| Combat | SQLite combat tracker, combatants, source refs, conditions, NPC resources, selected PC links | Preserve active encounter state when needed, durable source identity, conditions, resource counters, and selected-PC links. | Roster/order check, current turn, source-backed detail, conditions/resources, selected-PC widget smoke. |
| DM Content | SQLite statblocks, custom conditions, parser output, staged article links | Preserve DM-owned reusable content, source-backed combat seeding inputs, custom conditions, and staged article handoffs. | Statblock/condition counts, parser sample, combat seeding sample, staged article handoff checks. |
| Audit/history | Existing audit columns, native progression history, import history, actor columns | Preserve history useful for trust, rollback, and debugging without forcing V2 to keep every legacy event shape. | History presence report, actor mapping, dropped/condensed event review. |

## Migration Outputs

Each import run should produce:

- source snapshot metadata: source path, SQLite checksum, content tree checksum,
  import time, tool version, and operator;
- V2 target metadata: target path/database, schema version, import run id;
- mapping manifests for users, campaigns, characters, content pages, assets,
  Systems entries, Session records, Combat records, and DM Content records;
- validation report with errors, warnings, unsupported mechanics, missing refs,
  ambiguous refs, and manual-review items;
- summary counts by data family;
- replay command and cleanup/reset command for disposable targets.

## Phases

### Phase 1: Inventory

Define the exact legacy source inputs and the V2 target model for each data
family. Inventory should run without writing V2 data and should report counts,
refs, missing files, and unsupported cases.

### Phase 2: Disposable Import

Import sanitized fixtures and copied local snapshots into a disposable V2 target.
The import may create V2 schema/data from scratch, but it must not alter legacy
sources.

### Phase 3: Validation

Run family-specific validation against the V2 target:

- security/visibility checks;
- representative read workflows;
- source-ref and asset resolution;
- character read/widget smoke;
- Systems lookup/search;
- content render/search;
- Session/Combat/DM Content samples.

### Phase 4: Staging-Equivalent Rehearsal

Run the importer against an approved staging-equivalent snapshot. Record the
same manifests and validation reports, plus rollback/export instructions.

### Phase 5: Cutover Import

Only after explicit user approval, import the final production snapshot into the
V2 target and run the cutover workflow smoke. Keep the legacy snapshot intact
for rollback.

## Open Decisions

- Does V2 use a new SQLite schema, a different persistence layout, or a hybrid
  of SQLite plus file/document stores?
- Which Session, Combat, and audit/history records are worth carrying forward
  versus archived as legacy-only evidence?
- What is the final asset conversion policy for PNG/JPG/WebP/GIF portraits and
  article images?
- Should V2 keep legacy ids where possible, or always assign new ids with mapping
  manifests?
- How long should Flask compatibility routes remain available after V2 cutover?

## Stop Conditions

Stop before implementation or cutover if a proposed migration:

- rewrites legacy source files in place;
- cannot produce mapping manifests;
- silently drops unsupported mechanics;
- changes player/DM visibility semantics without an explicit decision;
- requires live SQLite, Fly volume, or production content access without user
  approval;
- cannot prove rollback to the untouched legacy snapshot.
