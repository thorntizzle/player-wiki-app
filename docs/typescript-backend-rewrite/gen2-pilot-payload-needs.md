# Gen2 Pilot Payload Needs

Last updated: 2026-06-28

Status: planning sketch for the first frontend modernization pilot

## Purpose

The holistic rewrite plan names Combat, Session, and Character as likely
frontend modernization pilots. This document sketches the backend payload
contracts those pilots need so backend architecture work does not accidentally
preserve Flask page shapes that Gen2 then has to work around.

## Recommendation

Use **Combat** as the first frontend workspace pilot after TypeScript API
stabilization.

Reasoning:

- Combat has the strongest live-play value and the clearest need for an adaptive
  workspace.
- Current Gen2 Combat already has a useful shape: encounter summary, local
  player inspection, DM `status` and `controls` views, selected-PC sections, and
  source-backed NPC resources.
- Combat can advance on live-state service contracts without waiting for the
  DND progression kernel to finish.
- Character authoring modernization should wait for the DND progression kernel,
  because create/level-up/retraining UI would otherwise anchor to temporary
  class-by-class backend behavior.

Character remains the likely second pilot if the DND kernel lands first or if
the team chooses to modernize read-only sheet widgets without touching authoring.
Session is a good later pilot once Combat proves live polling and pane
preservation patterns.

## Shared Payload Principles

All pilots need:

- stable ids for selected entities, sections, rows, and controls;
- explicit permission flags and disabled reasons near each mutation;
- revision or view-token fields for the backend to enforce stale-write behavior,
  but not user-facing revision display;
- local pending/error targets for the exact widget being changed;
- direct fallback hrefs where current Gen2 route behavior preserves no-JS or
  Flask compatibility;
- server-owned derived values, with the frontend avoiding duplicate rules math;
- invalidation hints or updated fragments precise enough to avoid full-page
  refetches for small widget mutations.

## Combat Pilot Payload Needs

### Read Payloads

Combat workspace read payloads should expose:

- campaign and viewer capability summary;
- encounter summary: round, current turn, combatant count, active/inactive state,
  and `Advance turn` permission;
- combatant roster with stable combatant ids, source kind/ref, display name,
  initiative/turn value, priority, current-turn state, visibility, and compact
  vitals;
- player local-inspection state separate from DM canonical `combatant=<id>`
  focus;
- selected combatant snapshot with HP/temp HP, movement, speed, action economy,
  conditions, supported source-backed resources, and unsupported source notes;
- DM status metadata for turn focus, selected-combatant authority, row revision,
  and combatant removal;
- controls payload for player, Systems monster, DM Content statblock, and custom
  combatant seeding options;
- selected PC payload with combat-only sections plus the shared CharacterPane
  sections already consumed by Character and Session Character.

### Mutation Payloads

Combat widget mutations should return enough data to update locally:

- `advanceTurn`: new encounter summary, focused combatant decision, and updated
  roster order;
- combatant vitals/movement/action-economy/priority: updated selected snapshot,
  combatant row revision, and roster summary row;
- source-backed NPC resource edit: updated resource row plus selected snapshot;
- condition add/remove/update: updated condition list plus selected snapshot;
- selected-PC character-state edits: refreshed character widget section and
  combat tracker revision bump;
- add combatant: new combatant id, roster row, selected snapshot if focused, and
  setup-form recovery data on validation failure;
- clear/delete: updated empty/inactive workspace state plus recovery message.

### Frontend Pilot Acceptance

Combat pilot acceptance should verify:

- player inspection does not rewrite `combatant=` or reset scroll;
- DM status focus keeps canonical `combatant=` and preserves selected focus after
  mutations;
- encounter summary stays visible and does not duplicate status widgets;
- selected-PC sections update without leaving Combat;
- unsupported NPC source mechanics stay visible as read-only notes;
- keyboard focus and reduced-motion behavior survive carousel, selected snapshot,
  and condition/resource edits;
- mobile layout keeps turn order, selected snapshot, and primary actions usable
  without horizontal scrolling.

## Character Pilot Payload Needs

Character read/workspace payloads should expose:

- identity/vitals header, ownership/control status, portrait summary, and
  system-specific route capabilities;
- subpage list with stable keys and fallback hrefs;
- DND read widgets: overview, resources, spell slots, current spell cards,
  equipment state, inventory rows, abilities/skills, notes, and rest preview;
- Xianxia read widgets: Quick Reference, Martial Arts, Techniques, Resources,
  Skills, Equipment, Inventory, Personal, and Notes;
- mutation targets with state revisions and disabled reasons;
- resolved linked Systems or campaign-page detail HTML for items/spells where
  current contracts support it;
- authoring readiness and repair state that come from the DND progression kernel
  instead of frontend-side inference.

Character authoring pilot work should wait for:

- DND progression-kernel plan payloads;
- character persistence module boundary;
- stable required-choice section shape;
- create/level-up/retraining preview and save plans sharing the same data path.

## Session Pilot Payload Needs

Session workspace payloads should expose:

- active/inactive session state and player-safe chat visibility;
- DM `dm_view` subview state with mounted preservation expectations;
- staged, revealed, lookup, and log summaries with focused mutation targets;
- Session Character payloads that reuse Character read widgets;
- polling view tokens and unchanged-response behavior that preserve local draft,
  focus, open details, and scroll state;
- explicit private-audience labels that never expose email addresses.

Session is a strong follow-up pilot, but it should reuse live-state and widget
patterns proven in Combat first.

## First Backend Contract Slice For The Pilot

Before frontend implementation begins, add a TypeScript service-contract pass
for Combat:

1. Name the canonical Combat read model separate from `/api/v1` response shape.
2. Identify which fields are product contract versus compatibility shape.
3. Define focused mutation return fragments for selected snapshot, roster row,
   encounter summary, and selected-PC widget updates.
4. Confirm current Gen2 `CombatPage.tsx` can consume the compatibility adapter
   while the backend internals move toward the canonical model.
5. Add tests that assert the canonical model and current route payload stay in
   sync for representative player, DM status, and DM controls states.

## Decision

Do not wait for the DND progression kernel to start the first frontend
modernization pilot. Do wait for API stabilization and a Combat service-contract
pass.

Do wait for the DND progression kernel before modernizing character authoring
flows such as create, level-up, progression repair, or retraining.
