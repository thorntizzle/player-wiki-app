# Holistic TypeScript Rewrite And Frontend Modernization Plan

Last updated: 2026-06-28

Status: planning reference; not cutover approval

## Purpose

The backend rewrite and frontend modernization are the same product move from
two angles. The backend needs to stop preserving Flask implementation shapes
when a better domain foundation is available. The frontend needs stable,
typed, responsive app contracts so Gen2 can become a richer tabletop workspace
instead of a page-for-page compatibility shell.

This plan combines:

- `docs/typescript-backend-rewrite/architecture-opportunity-audit.md`
- `docs/frontend-modernization-vision.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- `docs/current-state/frontend-gen2.md`
- `docs/frontend-ux-style-guide.md`
- `docs/gen2-migration-readiness.md`

Current-state docs remain the shipped product contract. This plan describes the
path from parity work to a cleaner TypeScript backend and a calmer, denser,
more capable Gen2 workspace.

## Operating Boundary

- Flask remains production authority until the TypeScript cutover gates pass.
- This plan does not approve a PR, merge, deploy, live data write, Fly sync, or
  production cutover.
- Gen2 is already the default browser frontend; frontend modernization should
  not destabilize the current `/app-next` contract during backend cutover.
- Direct Flask routes and legacy browser JSON routes remain compatibility paths
  until a later plan explicitly retires them.
- Future work belongs in narrow `.local/roadmaps/*` backlog items before
  implementation branches are opened.

## North Star

Campaign Player Wiki should become a stable TypeScript-backed tabletop
operations workspace:

- Backend services model campaign access, content publication, character
  authoring, DND progression, Systems rules, Session runtime, Combat state, and
  migration/ops explicitly.
- API routes preserve current client contracts at the edge while TypeScript
  internals use canonical service functions, typed payloads, and explicit error
  semantics.
- Gen2 keeps campaign identity, account/view-as state, global search, and
  navigation stable while Session, Combat, Character, DM Content, Systems, and
  Wiki surfaces become adaptive workspaces.
- Gameplay values and actions are compact, keyboard reachable, resilient during
  polling, and honest about server truth.
- Migration, rollback, schema, asset, and fallback decisions stay visible until
  they are intentionally closed.

## Planning Principles

| Principle | Backend meaning | Frontend meaning |
| --- | --- | --- |
| Preserve product contracts, not incidental Flask structure. | Auth, visibility, revisions, rollback, and current API semantics stay strict; route handlers become adapters over services. | Existing Gen2 routes and fallback links stay stable while internal data hooks and workspace layouts improve. |
| Build reusable domain foundations before widening parity treadmills. | DND create/level-up moves toward a progression kernel, not class-by-class hard coding. | Character, Session, and Combat widgets consume stable domain payloads instead of re-deriving scattered backend details. |
| Treat compatibility as an edge concern. | Browser JSON and Flask-shaped `/api/v1` routes are shims where needed. | Gen2 can keep old endpoints for cutover, then migrate to typed query/mutation hooks after the backend contract settles. |
| Keep live-play state honest. | Mutations preserve revision checks, permission checks, and rollback-friendly writes. | Pending, optimistic, invalidated, and failed states stay local to the affected widget or workflow. |
| Let pilots prove abstractions. | Service/module boundaries should be designed around real workflow needs. | New layout primitives, motion, or dependencies need a pilot and validation before broad adoption. |

## Architecture Workstreams

| Workstream | Goal | Depends on | Output |
| --- | --- | --- | --- |
| API and service boundary | Keep `/api/v1` and compatibility routes thin while centralizing domain behavior. | Route parity inventory, current-state docs, error-shape decision. | Route adapters, service modules, typed DTOs, explicit compatibility exceptions. |
| Character and DND progression | Replace class-by-class create/level-up slices with reusable DND progression rules. | Systems metadata normalization, character persistence boundary, DND progression ADR. | `dndProgression`, `characterPersistence`, and `characterChoices` modules with golden tests from current slices. |
| Systems rules foundation | Make Systems metadata reliable enough to drive DND options, source policy, rules references, and widgets. | Existing Systems import/source-policy contract. | Normalized metadata helpers and validation for class, subclass, spell, feat, item, and rule rows. |
| Live state services | Give Session and Combat durable service boundaries for revisions, polling, source counters, and state writes. | Current Session/Combat parity and copied-data rehearsal evidence. | Session and Combat service modules with UI-oriented payloads and mutation contracts. |
| Content and asset policy | Encapsulate published pages, Markdown mirrors, protected assets, portraits, and image conversion policy. | Image/portrait cutover decision and publishing current-state contract. | Content repository APIs and a chosen asset conversion/storage policy. |
| Frontend workspace shell | Keep `/app-next` stable while introducing persistent campaign context and adaptive workspaces. | Stable API contracts and current Gen2 shell behavior. | Shared shell conventions, route data loading rules, panel layout primitives, and local pending/error patterns. |
| Ops, schema, and cutover | Keep migration, packaging, rollback, and staging evidence honest. | SQLite ownership decision, container/frontend hosting decision, staging rehearsals. | Cutover-ready evidence labels, TypeScript schema posture, packaging proof, rollback transcript. |

## Phase Plan

### Phase 0: Integration Discipline

Goal: prevent current parity work from becoming accidental architecture.

- Keep `rewrite/ts-phase3-integration` as the authoritative integration branch.
- Classify new rewrite work as product contract, compatibility shim, migration
  bridge, architecture debt, or open decision.
- Stop treating "implemented route" as "architecturally final."
- Keep Gen2 behavior stable; do not start broad frontend redesign while backend
  contracts are moving.

Exit criteria:

- New cutover-readiness updates include architecture classification.
- New branch handoffs identify whether they improved foundation or only
  preserved compatibility.

### Phase 1: Contract Decisions

Goal: close decisions that would otherwise leak into every implementation lane.

Decide:

- Is `/api/v1` permanent TypeScript API or cutover compatibility surface?
- What is the canonical DND progression data source: Systems metadata, curated
  TypeScript tables, imported content, or hybrid?
- Does TypeScript own SQLite migrations before cutover, or only schema
  preflight until Flask authority ends?
- Does TypeScript preserve Flask WebP conversion, preserve extensions, or split
  image behavior by workflow?
- Does TypeScript serve `/app-next`, delegate frontend static hosting, or keep a
  Flask-shaped deployment through cutover?
- Which frontend pilot comes first after API stabilization: Combat, Session, or
  Character?

Exit criteria:

- Decision docs or ADRs exist for DND progression, schema ownership,
  image/portrait policy, API compatibility, and frontend hosting.
- First frontend pilot is chosen only after the API surface it needs is stable
  enough to avoid churn.

### Phase 2: Domain Foundation

Goal: build the reusable backend surface that Gen2 workspaces can trust.

- Split character authoring into persistence, DND progression, choices, campaign
  options, and route adapters.
- Build a data-driven DND progression kernel and reframe current class-specific
  slices as golden tests.
- Normalize Systems metadata enough to drive DND class/subclass/spell/feat/item
  choices.
- Create service boundaries for Session, Combat, content publication, and
  protected assets where route handlers are still carrying domain behavior.
- Define canonical JSON error envelopes and compatibility exceptions.

Exit criteria:

- At least one existing parity treadmill is replaced by a reusable domain
  module.
- Current golden tests still pass through the compatibility routes.
- Gen2-facing payloads for the chosen pilot are stable and documented.

### Phase 3: Cutover Parity And Rehearsal

Goal: make TypeScript safe enough to replace Flask without coupling cutover to a
large frontend redesign.

- Preserve required `/api/v1` and browser JSON compatibility routes.
- Keep frontend changes limited to compatibility fixes and API hook alignment.
- Finish copied-data and staging-equivalent rehearsals for write families.
- Close or explicitly defer SQLite migration, image/portrait, container, and
  `/app-next` hosting gates.
- Run route snapshot, route parity, TypeScript checks, focused API tests, and
  browser smoke for existing Gen2 surfaces.

Exit criteria:

- Cutover-readiness labels honestly distinguish fixture, copied-data, staging,
  and cutover evidence.
- Existing Gen2 workflows pass with TypeScript backend behavior.
- Rollback and Flask fallback remain rehearsed.

### Phase 4: First Frontend Workspace Pilot

Goal: prove the modern workspace pattern on one high-value surface.

Default pilot candidates:

- Combat if the goal is maximum live-play value and dense dynamic layout.
- Session if the goal is live article/chat/character workflow cohesion.
- Character if the DND progression kernel lands first and the goal is reusable
  gameplay widgets.

Pilot rules:

- Use existing theme tokens and shared components first.
- Add dependencies such as Motion only after explicit approval.
- Prefer container-aware layout and local pending/error states over new global
  chrome.
- Keep route hrefs and fallback behavior intact.
- Verify desktop, tablet, and mobile layouts, keyboard focus, reduced motion,
  polling stability, and mutation recovery.

Exit criteria:

- One pilot ships as current behavior and updates `docs/current-state/`.
- Reusable patterns are promoted only when at least two surfaces need them or
  when the pattern carries accessibility behavior.

### Phase 5: Post-Cutover Modernization

Goal: retire compatibility pressure and spread proven workspace patterns.

- Move Gen2 clients from compatibility shims to typed canonical hooks where
  useful.
- Retire Flask fallbacks only through explicit user-approved milestones.
- Expand adaptive workspaces to the next surface based on pilot findings.
- Reduce duplicated route-specific payload shaping in favor of service/domain
  contracts.
- Keep API and frontend docs aligned as behavior changes.

Exit criteria:

- Compatibility shims have owners, retirement conditions, or accepted permanent
  status.
- Frontend modernization backlog is organized by surfaces, not generic polish.

## First Combined Backlog Slice

The next high-leverage slice should be architecture planning, not another broad
implementation push:

1. Draft a DND progression-kernel ADR.
2. Define target module boundaries for character authoring.
3. Add architecture classification to cutover-readiness updates.
4. Sketch the Gen2 payload needs for the first likely pilot, with Combat and
   Character as the leading candidates.
5. Choose whether the first frontend pilot should wait for DND progression or
   start from live Combat/Session state services.

This avoids the trap of finishing backend parity in a shape the frontend then
has to work around.

Slice artifacts:

- `dnd-progression-kernel-adr.md`: adopts a data-driven DND progression kernel
  as the target architecture and reframes current class-specific slices as
  golden tests.
- `character-authoring-module-boundaries.md`: defines the target TypeScript
  module boundaries for character routes, persistence, DND progression, choices,
  options, derivation, presenter adapters, and Xianxia authoring.
- `gen2-pilot-payload-needs.md`: chooses Combat as the first likely frontend
  workspace pilot after Character read/widget dependencies and API stabilization
  are satisfied, and records the payload needs for Combat, Character, and
  Session.
- `cutover-readiness.md`: now carries an architecture classification overlay
  so future branches can distinguish product contract, compatibility shim,
  migration bridge, architecture debt, and open decision work.

Combined recommendation:

- Do the DND progression-kernel and character boundary work before widening
  level-up class-by-class.
- Stabilize Character read/widget payloads before the full Combat workspace
  pilot, because Combat embeds Character sections and mutations heavily.
- Do not wait for the DND authoring kernel to plan Combat service contracts;
  do wait for Character read/widget and Combat service-contract passes before
  frontend implementation.
- Do wait for the DND kernel before redesigning character authoring surfaces
  such as create, level-up, progression repair, or retraining.

## Validation Matrix

| Change type | Minimum validation |
| --- | --- |
| Backend domain/service split | Existing route parity tests plus focused golden tests for the moved behavior. |
| DND progression kernel | Current class-slice golden tests, new data-driven fixture cases, YAML/SQLite revision assertions. |
| Compatibility route | Route snapshot/seed update, API response check, and Gen2 client smoke if consumed by frontend. |
| Frontend workspace pilot | TypeScript/Vite check, targeted API tests, browser/screenshot review at desktop/tablet/mobile widths, keyboard/focus pass, reduced-motion pass. |
| Migration/schema/asset policy | Disposable proof, copied-data rehearsal, staging-equivalent transcript before production authority. |
| Cutover rehearsal | Full workflow smoke across auth, Campaign Home/wiki/search/help, DM Content, Systems, Characters, Session, Combat, backup, restore, rollback, and Flask fallback. |

## Stop Conditions

Pause and get an explicit decision if a lane needs to:

- choose a new canonical API surface;
- broaden class-by-class DND progression instead of building the kernel;
- add a frontend runtime dependency;
- remove Flask fallback behavior;
- change image conversion/storage semantics;
- make TypeScript responsible for SQLite schema deltas;
- change live Combat or Session table behavior;
- touch live data, Fly volumes, deployment, or production cutover.
