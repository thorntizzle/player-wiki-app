# Combat

Last updated: 2026-06-25

## Owns

- Combat tracker setup, player combat, compatibility Combat Character, DM Status, DM encounter controls, combatant source identity, turn order, tactical edits, combat conditions, and selected-PC sheet reuse.

## Current User-Facing Behavior

- Combat tracker is currently implemented for DND-5E campaigns.
- Player-facing Gen2 `Combat` defaults to the viewer's tracked player character when one exists, keeps turn order and the jump selector above the workspace, and treats combatant inspection as local page state rather than rewriting `combatant=` for ordinary player clicks.
- Compatibility `Combat Character` remains available for tracked PCs.
- DM-only `Status` owns selected-combatant inspection and tactical editing.
- DM-only `DM page` / controls owns setup, seeding, and cleanup.
- `/combat/dm` defaults to the full-width `DM status` selected-combatant workspace, while `?view=controls` is a controls-only setup/seeding/cleanup view.
- The Gen2 selected-combatant snapshot card groups HP, movement, action economy, and active conditions. DM Status folds editable turn focus, vitals, action economy, conditions, and selected-combatant removal into that selected snapshot instead of rendering separate tactical cards.
- The DM Status Conditions editor stays inside the selected-snapshot control card at desktop, tablet, and mobile widths. The `Add condition` disclosure stacks its fields inside the card, condition rows keep readable names/durations, and row actions such as `Remove` stay on one line.
- In Gen2 Encounter Controls, the encounter summary/status band owns Round, current turn, combatant count, and `Advance turn`; setup and cleanup controls do not duplicate a separate tracker/status card.
- Selected-PC combat workspaces expose combat-specific character sections from the presented character data, including Actions, Bonus Actions, Reactions, Attacks, and Features when present, followed by the shared CharacterPane for durable sheet sections and mutable-state edits.

## Combat State Contract

- Combatants persist source identity through `source_kind` and `source_ref` so DM detail can load linked characters, DM Content statblocks, Systems monsters, or manual/missing-source fallbacks without title matching.
- Shared turn order sorts by turn value descending, Dexterity modifier descending, DM priority ascending, then display name/id fallback.
- DM or owner-player users can edit HP/temp HP where permitted.
- Player resource/spell-slot edits and owner/DM selected-PC equipment-state edits use shared durable character-state paths and can bump combat tracker revision for live refresh.
- Combat row-owned tactical writes use combatant-row revision where relevant.
- Gen2 combat payloads include `selected_player_combat_sections` for the selected tracked PC so the frontend can render combat-only Actions/Reactions/Attacks/Features without leaving the combat route.
- Player-facing Gen2 combat selection preserves the mounted payload and viewport by keeping player inspection local; DM focus and view changes keep `combatant=` but request TanStack navigation without scroll reset.

## Seeding And Source Detail

- DM controls can add combatants from player characters, Systems monsters, DM Content statblocks, or custom combatants.
- Creation-time priority is available for player, Systems, DM Content, and custom combatants.
- DM Content statblocks copy currently parsed HP, speed, initiative bonus, DEX tie-breaker modifier, and source identity into new combatants.
- Combat can inspect source-backed PC, DM Content statblock, Systems monster, or manual/missing-source detail.

## Current Tests Or Verification

- Combat changes usually need route/API tests, browser checks, and focused source-detail or mutation checks around turn flow, selected combatant, conditions, seeding, and selected-PC sheet behavior.
- Current Gen2 combat verification includes source-contract tests for local/no-scroll selection and folded snapshot controls, API coverage for selected-PC combat sections, frontend typecheck/build, and a Gen2 browser smoke for Encounter Controls status placement.

## Known Limits

- Source-backed NPC resources and richer NPC spell/resource edit controls remain deferred. The current durable combatant model persists source identity, HP, movement/action economy, conditions, and revisions, but it does not yet persist arbitrary per-combatant counters derived from Systems monsters or DM Content statblocks without mutating those source rows.
- Xianxia combat automation is not implemented.
- Encounter presets or saved rosters are future backlog work.

## Related Backlog

- `.local/roadmaps/live-combat-backlog.md`
- `.local/roadmaps/xianxia-backlog.md`

## Source Pointers

- `player_wiki/campaign_combat_store.py`
- `player_wiki/campaign_combat_service.py`
- `player_wiki/combat_models.py`
- `player_wiki/combat_presenter.py`
- `player_wiki/templates/combat.html`
- `player_wiki/templates/combat_status.html`
- `player_wiki/templates/combat_dm.html`
- `frontend/src/pages/CombatPage.tsx`
- `frontend/src/combatMutations.ts`
- `frontend/src/components/CombatDmStatusPanel.tsx`
- `frontend/src/components/CombatDmControlsPanel.tsx`
