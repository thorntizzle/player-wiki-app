# ADR: DND Progression Kernel

Date: 2026-06-28

Status: proposed architecture direction; implementation not started

## Context

The TypeScript rewrite currently closes character parity through bounded class
slices. That has been useful for proving Flask-vs-TypeScript behavior, but it is
not the right long-term architecture for DND-5E create, level-up, repair, or
retraining.

Current product contracts already point toward a shared model:

- save-time derivation is the authority for computed DND-5E sheet math;
- native level-up is one level at a time through level 20;
- level-up can advance an existing class row or add a new class row when the
  support matrix allows it;
- class rows, spellcasting rows, resources, equipment, attacks, and progression
  history need durable row identities;
- Systems metadata and structured campaign-page mechanics should drive choices
  where possible;
- unsupported base classes, spellcasting profiles, and respec/rebuild flows
  should remain blocked with clear reasons until they are modeled end to end.

The rewrite should therefore stop treating "next class, next level" as the main
implementation pattern. Existing class-specific slices should become golden
tests for a reusable progression kernel.

## Decision

Adopt a data-driven DND progression kernel as the target architecture for
TypeScript character authoring.

The kernel should generate explicit progression plans for supported operations:

- native level-one create;
- native level-up;
- imported progression repair;
- structured retraining;
- later native edit recalculation where it shares the same derivation path.

The kernel should not write files, mutate SQLite, or shape HTTP responses
directly. It should take normalized character, campaign, Systems, and request
input and return a typed plan that describes:

- current readiness and blocking reasons;
- required user choices;
- sanitized selected choices;
- feature, spell, resource, HP, Hit Dice, equipment, attack, and history deltas;
- durable refs and row ids to preserve;
- validation errors and stale-choice recovery guidance;
- persistence deltas that a separate character persistence module can commit.

## Canonical Data Source

The preferred source order is:

1. durable character refs already stored on the sheet;
2. enabled Systems metadata for class, subclass, species, background, feat,
   spell, item, and progression rows;
3. supported campaign-page `character_option`, `character_progression`,
   `spell_support`, `additionalSpells`, and structured item metadata;
4. curated fallback tables for bounded gaps, with explicit source ids,
   supported identity keys, and retirement notes.

Fallback tables are allowed when they capture a known shipped contract, such as
bounded PHB or TCE behavior that current Systems imports do not yet express.
They should not become title-only branching scattered through route handlers.

## Kernel Shape

Target module responsibilities:

| Module | Responsibility |
| --- | --- |
| `dndRulesCatalog` | Resolve enabled Systems rows, supported source matrix, class/subclass progression, spell lists, feat/item mechanics, and curated fallback tables. |
| `dndProgressionKernel` | Build create, level-up, repair, and retraining plans from normalized inputs. |
| `dndChoiceEngine` | Hydrate option sets, sanitize stale submitted values, detect missing choices, and produce stable required-choice payloads. |
| `dndDerivation` | Recalculate ability-derived stats, proficiency, saves, skills, passives, speed, HP, spellcasting, resources, Armor Class, attacks, and reminder state. |
| `dndProgressionHistory` | Build `source.native_progression` events, HP baselines, repair records, and provenance fields. |
| `characterPersistence` | Commit definition/import YAML, SQLite mutable state, revision bumps, and rollback-friendly history. |

Routes and Hono handlers should stay outside this kernel. Their job is auth,
compatibility shape, request parsing, and response mapping.

## Progression Plan Contract

A progression plan should contain at least:

- `status`: `ready`, `needs_choices`, `blocked`, or `validation_error`;
- `operation`: `create`, `level_up`, `repair`, `retrain`, or `recalculate`;
- `readiness_reasons`: user-safe explanations for unsupported or blocked cases;
- `choice_sections`: stable sections with field ids, labels, selected values,
  options, and dependencies;
- `preview`: derived summary for the UI, including features, resources,
  spellcasting, attacks, HP, and history impact;
- `persistence_plan`: definition/state/history deltas for the commit layer;
- `invalidated_fields`: submitted fields dropped because dependencies changed;
- `test_trace`: stable debug metadata for golden fixture assertions, not
  user-facing UI.

## Initial Implementation Scope

The first implementation slice should not attempt all DND advancement.
Start with a narrow but representative kernel path:

1. Extract current Fighter, Barbarian, Rogue, Ranger, Monk, and Paladin
   level-one-to-two TypeScript slices into golden expectations.
2. Implement the kernel for those same cases through shared class-level,
   HP/Hit Dice, feature, resource, and spell-slot plan logic.
3. Keep route payloads and fixture behavior compatible while replacing
   class-specific save branches under the route.
4. Add one nontrivial choice case, such as Fighting Style, as a generic
   required-choice section rather than a class-local one-off.
5. Only then widen to additional classes, levels, multiclass add-class, ASI/feat,
   subclass gates, and prepared-spell workflows.

## Non-Goals

- Full generic respec, arbitrary history rewrite, or open-ended rebuild flows.
- Xianxia progression. Xianxia remains a separate system-specific lane.
- Combat automation or target/effect adjudication.
- Source-policy expansion for unsupported base classes before their full
  create/edit/repair/import/level-up behavior is modeled.
- Frontend workspace redesign. The kernel should provide stable payloads that
  a later Gen2 pilot can consume.

## Consequences

Positive:

- Current class slices become evidence instead of permanent architecture.
- Level-up, repair, retraining, and later native edit can share derivation.
- Gen2 can consume stable choice and preview payloads without re-deriving DND
  rules in React.
- Future source expansion has one policy/catalog path instead of scattered
  guardrails.

Costs:

- Requires a module split before broad parity appears to move faster again.
- Needs fixture migration from route-shaped assertions toward plan and
  persistence assertions.
- Requires Systems metadata gaps to be named instead of patched silently.

## Validation

Each kernel slice should prove:

- existing Flask-vs-TypeScript golden behavior still passes through the route;
- the same plan can drive preview and save;
- YAML definition, import metadata, SQLite state, revision bumps, and
  `native_progression` history are asserted;
- unsupported and stale-choice cases return friendly blocking reasons;
- no GET/read path writes durable data.

## Open Questions

- Which curated fallback tables are acceptable for first implementation, and
  which Systems metadata gaps should block instead?
- Should the kernel expose a canonical API payload before `/api/v1` permanence
  is decided, or only feed compatibility adapters for now?
- How much of the current Python builder contract should be mirrored in tests
  before TypeScript becomes the new source of truth?
