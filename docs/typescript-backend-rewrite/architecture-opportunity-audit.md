# TypeScript Rewrite Architecture Opportunity Audit

Last updated: 2026-06-28

Status: active audit and architecture decision input

## Purpose

The TypeScript rewrite needs enough behavioral parity to replace Flask safely,
but parity should not mean copying every Flask implementation shape into the new
backend. This audit separates product contracts that must be preserved from
temporary compatibility shims, migration bridges, and places where the rewrite
should deliberately build a better foundation.

The immediate trigger for this audit is the DND-5E level-up lane. The current
branch is adding bounded class-by-class parity slices to close observable
Flask gaps. That is useful as characterization evidence, but it should not
become the permanent architecture for advancement.

## Audit Rubric

Use these labels when reviewing existing or new TypeScript rewrite work:

| Label | Meaning | Rewrite posture |
| --- | --- | --- |
| Product contract | User-visible behavior, safety, authorization, rollback, or data boundary that must survive cutover. | Preserve directly and test heavily. |
| Compatibility shim | Legacy route, response shape, or browser contract needed so Gen2/current clients survive cutover. | Preserve at the edge; keep canonical internals cleaner. |
| Migration bridge | Transitional behavior needed while Flask, existing SQLite rows, YAML files, mirrors, or copied-data rehearsals remain authoritative. | Encapsulate and give it an exit condition. |
| Architecture debt | TypeScript is reproducing Flask's incidental implementation style instead of modeling the domain. | Stop widening where possible; design a reusable foundation. |
| Open decision | Multiple viable product or ops policies exist and a worker should not choose silently. | Record an ADR or operator decision before implementation broadens. |

## Current Snapshot

The integration branch is far enough along that architectural drift now matters.
`typescript-route-seed.json` currently records 148 route-seed entries:

| Status | Count |
| --- | ---: |
| `implemented_fixture_readonly` | 19 |
| `implemented_fixture_sqlite_readonly` | 32 |
| `implemented_fixture_sqlite_write` | 84 |
| `implemented_fixture_write` | 7 |
| `implemented_hono` | 1 |
| `deferred_scratch_proof` | 5 |

That breadth is good for cutover confidence, but it also means repeated
implementation patterns can harden quickly if the rewrite does not name which
parts are intentional contracts and which parts are temporary scaffolding.

## Guardrails

- Behavioral parity tests should characterize the Flask/product contract, not
  require TypeScript to keep Flask's internal structure.
- Route handlers should be compatibility adapters over service/domain modules,
  not the permanent home for domain behavior.
- Safety-critical behavior remains strict parity: auth, membership, view-as,
  visibility, revision checks, backup, restore, rollback, and no-live-data
  boundaries should not be loosened for architectural neatness.
- Migration bridges should have named exit criteria. If an exit is unknown,
  mark it as an open decision instead of letting it become permanent by default.
- New implementation lanes should state whether they are adding product
  contract, compatibility shim, migration bridge, or architecture foundation.

## Audit Matrix

| Area | Current parity pressure | Classification | Architectural opportunity | Recommended next move |
| --- | --- | --- | --- | --- |
| Auth, membership, view-as, visibility | Flask gates are the product safety contract. | Product contract | Keep one central authorization policy layer that routes and services share. | Preserve strictly; add parity/golden coverage where gaps appear. |
| YAML definitions plus SQLite mutable state | Existing characters and campaign data span files and database rows. | Product contract plus migration bridge | Hide storage mechanics behind repositories so future storage changes do not leak into route logic. | Preserve through cutover, but keep all direct file/SQLite coordination inside persistence modules. |
| DND-5E character create and level-up | Bounded class-by-class slices are closing visible Flask parity gaps. | Architecture debt with useful parity evidence | Build a data-driven progression kernel from class/subclass/species/background metadata, generic level rules, choices, resources, spells, HP, hit dice, ASI/feat gates, and history writes. | Open a DND progression-kernel ADR and use current slices as golden tests; avoid broadening one class and one level at a time as the default plan. |
| `apps/api/src/content/characterAuthoring.ts` growth | Create, edit, repair, retraining, level-up, campaign options, validation, persistence, and YAML/state reconciliation live together. | Architecture debt | Split into `dndProgression`, `characterPersistence`, `characterChoices`, `campaignOptions`, and thin route adapters. | Make the split a prerequisite for broad advancement work, even if some helpers move incrementally. |
| Flask `/api/v1` route parity and route seed | Route inventory is the main cutover checklist. | Compatibility shim | Keep Flask route shapes at the HTTP edge while canonical TypeScript services expose cleaner contracts. | Add classification notes to future route-seed/readiness updates so "implemented" does not imply "architecturally final." |
| Missing-resource and error response shapes | Flask sometimes returns HTML 404s where TypeScript naturally returns JSON. | Compatibility shim plus open decision | Define a canonical JSON error envelope for new TypeScript clients while documenting v1 exceptions. | Record which v1 differences are deliberate compatibility breaks and which are temporary parity gaps. |
| Browser JSON compatibility routes | Gen2 still calls legacy non-`/api/v1` search and preview endpoints. | Compatibility shim | Treat the four implemented compatibility routes as edge adapters, not the next API pattern. | Keep the closed compatibility decision for cutover, but plan typed Gen2 client migration after cutover pressure drops. |
| SQLite schema and migration ownership | TypeScript can preflight Flask-current schema and run a guarded ledger-only proof, but Flask still initializes production schema. | Migration bridge plus open decision | Either give TypeScript a real migration package with allowlisted deltas or explicitly keep Flask schema ownership until cutover. | Create a schema-ownership decision before the first real TypeScript schema delta. |
| Published content and Markdown mirror behavior | Current product uses app-owned published content, protected assets, page metadata, and mirrored Markdown conventions. | Product contract plus migration bridge | Expose content through repository/service APIs so mirror and source-file mechanics are not coupled to routes. | Preserve behavior and rollback semantics, but do not spread mirror-path logic beyond content persistence. |
| Image and portrait handling | Flask converts some PNG/JPG publication flows to WebP; TypeScript currently preserves uploaded bytes/extensions. | Open decision plus migration bridge | Choose an explicit asset policy: preserve Flask WebP normalization, accept extension-preserving APIs, or split by workflow. | Use `image-portrait-cutover-policy.md` as the decision gate before widening image writes or claiming readiness. |
| Copied-data write proof | Many write families have strong disposable or copied-fixture evidence. | Migration bridge | Keep evidence labels honest so fixture success does not masquerade as staging or production readiness. | Continue using `fixture-write validated`, `copied-data rollback ready`, and `staging snapshot ready` labels exactly. |
| Ops wrapper growth | `local.ps1` now carries TypeScript check/proof orchestration for Windows-local workflows. | Compatibility/local shim | Put portable checks in package scripts or small cross-platform scripts; keep PowerShell as the local convenience wrapper. | Avoid adding business logic to `local.ps1`; make it call named scripts with clear evidence output. |
| `/app-next` and frontend serving | Flask production owns current app shell serving; TypeScript runtime proof is API-only. | Compatibility shim plus open decision | Decide whether TypeScript ultimately owns frontend static serving, delegates it, or keeps Flask-shaped deployment until cutover. | Keep API-only proof labels explicit until a frontend hosting decision and runtime proof exist. |
| Systems metadata as rules source | Current DND rows already carry class, spell, source, and policy metadata used by the builder. | Product contract and architecture foundation | Lean into structured Systems metadata for rules and choices instead of hard-coded title/class exceptions. | Treat Systems metadata normalization as a prerequisite for the generic DND progression kernel. |

## Priority Findings

### 1. DND progression should become a kernel, not a class treadmill

The current level-up slices are valuable because they turn uncertain Flask
behavior into concrete fixtures and tests. They are not a good final shape.
Advancement should be driven by durable class/subclass/species/background refs
and progression metadata, with generic logic for:

- level targets and multiclass rows;
- hit dice, average/manual HP gain, max HP, and level history;
- proficiency bonus and derived stats;
- class and subclass features by level;
- resources and scaling resources;
- spell slot tables, pact slots, known/prepared spell choices, and automatic
  spells;
- ASI/feat, fighting style, expertise, invocation, metamagic, and other choice
  gates;
- required-choice payloads when automation cannot safely continue;
- YAML definition, SQLite state, revision, and `native_progression` history
  writes through one persistence path.

The present class-specific slices should become acceptance tests for that
kernel. They should not set the pattern for every class, every level, and every
subclass.

### 2. Character authoring needs module boundaries before it gets much wider

`characterAuthoring.ts` is carrying too many responsibilities. That was
reasonable while the branch was proving parity quickly, but the file now mixes
HTTP-facing context shape, DND rule interpretation, editor validation, persistence
coordination, repair, retraining, level-up, and Xianxia/native paths.

Recommended target boundaries:

- `characterPersistence`: definition/import YAML, SQLite character state,
  revisions, history, and rollback-friendly writes.
- `dndProgression`: DND level/create/retrain/repair rules driven by Systems
  metadata and curated fallback tables.
- `characterChoices`: field normalization, option hydration, required-choice
  payloads, and reusable validation helpers.
- `campaignOptions`: enabled source/class/species/background/feat/spell options.
- route adapters: Hono request/response compatibility, auth context, and API v1
  shape mapping.

### 3. Route parity is a checklist, not the domain model

The route seed and parity inventory are essential for cutover. The risk is that
the TypeScript rewrite starts designing around Flask route families instead of
domain workflows. The permanent architecture should name services around
campaign access, content publication, character authoring, session runtime,
combat state, Systems library, and ops/migration behavior. API v1 routes can
then stay as thin compatibility boundaries.

### 4. Error and browser compatibility need expiry pressure

Some compatibility shims are already intentional and well documented, such as
the four browser JSON search/preview routes. Others are still in the gray zone,
especially missing-resource response shapes where Flask returns HTML and
TypeScript returns JSON. Those differences should be explicit API decisions, not
incidental results of whichever handler landed first.

### 5. Migration bridges should not become production architecture by inertia

Copied-data rehearsals, fixture-backed writes, SQLite preflights, and the
ledger-only migration proof are useful bridge work. They are not the same as
TypeScript owning real production writes or schema changes. The rewrite should
keep those labels visible and require explicit promotion to staging snapshot,
cutover rehearsal, and production authority.

## Do Not Redesign Lightly

The following areas should remain conservative unless a later product decision
changes them:

- authorization, campaign membership, role checks, and view-as behavior;
- campaign visibility and player-safe publication rules;
- stale revision and write-conflict semantics;
- backup, restore, rollback, and no-live-data guardrails;
- separation between app-owned repo code and campaign/vault source material;
- current player-facing URL/API contracts needed for cutover.

These are not places to trade parity for elegance.

## Immediate Actions

1. Create a DND progression-kernel ADR before opening more broad class-by-class
   level-up lanes.
2. Mark current Fighter/Barbarian/Rogue/Ranger/Monk/Paladin level-one-to-two
   work as golden evidence for the future kernel, not as the implementation
   template for all classes.
3. Add a module-boundary target for character authoring before broadening
   advancement, Advanced Editor derivation, or retraining.
4. Add an architecture classification note to future cutover-readiness updates:
   product contract, compatibility shim, migration bridge, architecture debt, or
   open decision.
5. Keep image/portrait and SQLite schema ownership as explicit decision gates,
   not implicit worker choices.
6. When integrating new rewrite branches, ask whether the branch improved the
   TypeScript foundation or only preserved Flask shape. If it only preserved
   Flask shape, document whether that was intentional.

## Open Decisions

- Is `/api/v1` the permanent TypeScript API surface, or the cutover compatibility
  surface for current clients?
- What is the canonical source for DND progression data: Systems metadata,
  curated TypeScript tables, imported source content, or a hybrid?
- When do Markdown/YAML mirrors stop being implementation primitives and become
  repository-backed persistence details?
- Should TypeScript own SQLite schema migration before cutover, or only after
  Flask production authority ends?
- Which Flask error shapes are true API compatibility requirements, and which
  can be replaced by canonical TypeScript JSON envelopes?
- Does TypeScript eventually own `/app-next` static serving, or does deployment
  split frontend hosting from the API?
