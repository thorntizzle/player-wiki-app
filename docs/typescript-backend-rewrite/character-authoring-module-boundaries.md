# Character Authoring Module Boundaries

Last updated: 2026-06-28

Status: target module plan for TypeScript rewrite refactors

## Purpose

The current TypeScript character authoring implementation has grown by parity
slices. That was useful for proving behavior, but the rewrite now needs stable
module boundaries before broad DND create, Advanced Editor, level-up, repair,
and retraining work continues.

This document defines the intended boundaries. It does not require an immediate
large refactor; it gives future branches a map for extracting behavior without
changing route contracts.

## Boundary Goals

- Keep Hono routes thin and compatibility-focused.
- Keep DND progression rules out of file/SQLite persistence code.
- Keep persistence commits centralized and rollback-friendly.
- Keep Systems metadata and campaign-page option hydration reusable across
  create, edit, level-up, repair, retraining, Session Character, and Combat
  selected-PC payloads.
- Keep Xianxia in its own system lane instead of teaching DND modules about
  Xianxia resource semantics.

## Target Modules

| Module | Owns | Must not own |
| --- | --- | --- |
| `characterAuthoringRoutes` | Hono route handlers, auth context, compatibility request/response shape, redirects/links, HTTP status mapping. | DND rules, YAML writes, SQLite write orchestration, Systems scans. |
| `characterAccess` | Campaign access, route-lane capability checks, authoring/session-edit permissions, view-as-aware actor context. | Progression rules or persistence deltas. |
| `characterPersistence` | Loading and saving definition/import YAML, SQLite character state, revisions, actor columns, history, reconciliation, and atomic commit helpers. | Class-specific DND progression logic or React payload layout. |
| `campaignCharacterOptions` | Enabled Systems source state, campaign-page mechanics, supported source matrix, option catalogs, cache keys, and option invalidation inputs. | Sheet mutation commits or route responses. |
| `characterChoices` | Field normalization, stale submitted value cleanup, required-choice sections, selected-value validation, and user-safe choice errors. | Derivation math or direct writes. |
| `dndProgression` | DND create, level-up, repair, retraining, HP/Hit Dice, class/subclass feature progression, spell growth, resources, and progression history planning. | HTTP response mapping or direct filesystem/database writes. |
| `dndDerivation` | Shared save-time recalculation for stats, spellcasting, equipment, Armor Class, attacks, resources, passives, and combat reminders. | Route auth, campaign option queries, or persistence transactions. |
| `characterPresenterAdapters` | Mapping canonical domain output into existing Gen2/Flask-compatible presenter payloads. | Rules decisions or state commits. |
| `xianxiaAuthoring` | Xianxia create, Cultivation, Realm Ascension, Xianxia-specific resources, Dao, Martial Arts, Techniques, and Xianxia state reconciliation. | DND spellcasting/class assumptions. |
| `characterAuthoringErrors` | Shared typed errors and compatibility conversion to current API envelopes. | Domain rules beyond error categories. |

Names can change during implementation, but those responsibilities should not
collapse back into one file.

## Current Extraction Pressure

The highest-pressure cluster is DND create and level-up:

- class configs, supported-class checks, features, resources, attacks, armor
  math, spells, and level-two feature/resource templates are sitting close to
  route context shape;
- progression repair, retraining, level-up, and create all need the same durable
  class/species/background/subclass refs and Systems option hydration;
- frontend Character, Session Character, and Combat selected-PC panes all need
  stable presented payloads derived from the same state rather than their own
  special-case interpretations.

## Recommended Extraction Order

1. **Pure helpers first.** Move DND class/source lookup, option identity,
   spell-list filtering, and source-matrix helpers without changing behavior.
2. **Persistence plan boundary.** Introduce a commit helper that accepts a
   persistence plan and performs definition/import YAML writes, SQLite state
   updates, revision bumps, and history append in one place.
3. **Choice sections.** Extract required-choice hydration and submitted-value
   sanitization so create, level-up, repair, and retraining can share it.
4. **DND progression kernel.** Replace the bounded class-specific level-up
   branches with progression plans for the same golden cases.
5. **Presenter adapters.** Keep current response shapes but map them from
   canonical progression/read models.
6. **Widen support.** Only after the kernel passes current golden cases, add
   broader levels, class rows, subclass gates, ASI/feat, spell growth, and
   prepared-spell choice UI.

## Route Adapter Contract

Route handlers should be able to follow this pattern:

1. Resolve actor, campaign, and route capability.
2. Load the character definition/state through `characterPersistence`.
3. Build campaign/System option context through `campaignCharacterOptions`.
4. Call the relevant domain service, such as `dndProgression.planLevelUp`.
5. If saving, pass the returned persistence plan to `characterPersistence`.
6. Map the resulting plan/commit result into the existing API v1 or browser
   compatibility payload.

If a route needs to inspect raw YAML, mutate SQLite directly, and decide DND
features in the same function, it is still too wide.

## Validation Per Extraction

Each extraction branch should run the smallest test set that proves behavior did
not move:

- route compatibility/golden tests for the touched character operation;
- YAML definition and import metadata assertions;
- SQLite `character_state` revision/state assertions;
- stale revision and permission assertions for write paths;
- route payload compatibility assertions for Gen2 consumers.

## Stop Conditions

Pause for an explicit architecture decision if an extraction would:

- make GET/read paths write durable character data;
- expand DND source support without end-to-end create/edit/repair/import/level-up
  proof;
- merge Xianxia and DND resource/spellcasting semantics;
- remove current API v1 or Flask fallback compatibility;
- require frontend redesign to preserve backend behavior.
