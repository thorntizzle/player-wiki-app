# Combat

Last updated: 2026-07-14

## Owns

- Combat tracker setup, player combat, compatibility Combat Character, DM Status, DM encounter controls, combatant source identity, turn order, tactical edits, combat conditions, and selected-PC sheet reuse.

## Current User-Facing Behavior

- Combat tracker is currently implemented for DND-5E campaigns.
- Player-facing `Combat` defaults to the viewer's tracked player character when one exists and keeps turn order and the jump selector above the workspace.
- The player-facing Combat Character workspace is a single character card: the normal Combat Character header, HP/rest controls, combat movement/action-economy controls, combat-only action/feature sections, and the shared character sections live in one card flow. Players do not get a separate selected-PC selector in that card.
- Compatibility `Combat Character` remains available for tracked PCs.
- The compatibility Combat Character live-state poll validates an explicit `combatant=` or
  `character=` selected-PC relationship before player-character snapshot synchronization, live
  metadata, payload rendering, or unchanged-response short-circuit evaluation. Unassigned explicit
  targets receive `403` for matching, stale, malformed, and absent polling headers; authorized
  polling and the no-selector compatibility empty state retain their existing behavior.
- DM-only `Status` owns selected-combatant inspection and tactical editing.
- The `Status` live-state poll is manager-only: campaign DM/admin authorization is checked before
  live metadata, player-character snapshot synchronization, payload rendering, or unchanged-response
  short-circuit evaluation.
- DM-only `DM page` / controls owns setup, seeding, and cleanup.
- `/combat/dm` defaults to the full-width `DM status` selected-combatant workspace, while `?view=controls` is a controls-only setup/seeding/cleanup view.
- The selected-combatant snapshot card groups HP, movement, action economy, active conditions, and visible source-backed NPC resources. DM Status folds editable turn focus, NPC vitals, NPC action economy, source-backed NPC resource counters, conditions, and selected-combatant removal into that selected snapshot instead of rendering separate tactical cards; selected-PC HP and action-economy edits live in the unified Combat Character workspace.
- The DM Status Conditions editor stays inside the selected-snapshot control card at desktop, tablet, and mobile widths. The `Add condition` disclosure stacks its fields inside the card, condition rows keep readable names/durations, and row actions such as `Remove` stay on one line.
- In DM Status and Encounter Controls, the shared encounter summary/status band owns Round, current turn, combatant count, and `Advance turn`; setup, cleanup, and DM tactical controls do not duplicate a separate tracker/status card.
- When DM Status focuses a player character, it mounts the same unified Combat Character workspace beneath the selected-combatant snapshot. DM/admin users still select characters through the status combatant focus/carousel instead of a separate player-style selector.
- Selected-PC combat workspaces expose combat-specific character sections from the presented character data, including Actions, Bonus Actions, Reactions, Attacks, and Features when present, followed by shared durable sheet sections and mutable-state edits.

## Combat State Contract

- Combatants persist source identity through `source_kind` and `source_ref` so DM detail can load linked characters, DM Content statblocks, Systems monsters, or manual/missing-source fallbacks without title matching.
- Shared turn order sorts by turn value descending, Dexterity modifier descending, DM priority ascending, then display name/id fallback.
- DM or owner-player users can edit HP/temp HP where permitted.
- Player resource/spell-slot edits and owner/DM selected-PC equipment-state edits use shared durable character-state paths and can bump combat tracker revision for live refresh.
- Combat row-owned tactical writes use combatant-row revision where relevant.
- Source-backed NPC resource counters are combatant-owned durable rows. DM Content statblocks and Systems monsters can seed supported limited-use counters at combatant creation, and current values persist on the combatant without mutating the underlying source entry.
- Unsupported source mechanics that are not editable counters, such as recharge and at-will lines, are stored as read-only source notes on the combatant so visible mechanics are not silently hidden.
- Combat payloads include `selected_player_combat_sections` for the selected tracked PC so API/browser clients can render combat-only Actions/Reactions/Attacks/Features inside the unified Combat Character workspace without leaving the combat route.
- Player-facing combat selection keeps meaningful focus in `combatant=` query state where relevant.

## Seeding And Source Detail

- DM controls can add combatants from player characters, Systems monsters, DM Content statblocks, or custom combatants.
- Creation-time priority is available for player, Systems, DM Content, and custom combatants.
- DM Content statblocks copy currently parsed HP, speed, initiative bonus, DEX tie-breaker modifier, source identity, supported daily/explicit NPC resource counters, and read-only unsupported mechanic notes into new combatants.
- Systems monster combatants copy parsed HP, speed, initiative/DEX tie-breakers, source identity, supported daily/explicit NPC resource counters, and read-only unsupported mechanic notes into new combatants.
- Combat can inspect source-backed PC, DM Content statblock, Systems monster, or manual/missing-source detail.

## Current Tests Or Verification

- Combat changes usually need route/API tests, browser checks, and focused source-detail or mutation checks around turn flow, selected combatant, conditions, seeding, and selected-PC sheet behavior.
- Current combat verification includes route/API coverage for unified Combat Character workspace structure, summary-band Advance Turn placement, folded snapshot controls, selected-PC combat sections, source-backed NPC resource seeding/edit/conflict/permission behavior, and browser smoke checks for player Combat, DM Status, and Encounter Controls placement.

## Current Boundaries

- Source-backed NPC resource support currently models explicit current/max counters and common daily limited-use patterns. Other source mechanics, including recharge lines, at-will lines, spell-specific casting rules, shared pools, and reset behavior, stay visible as read-only source notes unless they are modeled as supported counters.
- Combat automation is currently DND-5E-only. Xianxia campaigns keep their character/session surfaces without combat automation.
- Encounter setup currently seeds individual player, Systems, DM Content, or custom combatants. Saved encounter presets and reusable rosters are not modeled.

## Related Backlog

- `.local/roadmaps/combat-backlog.md`
- `.local/roadmaps/xianxia-backlog.md`

## Source Pointers

- `player_wiki/campaign_combat_store.py`
- `player_wiki/campaign_combat_service.py`
- `player_wiki/combat_models.py`
- `player_wiki/combat_presenter.py`
- `player_wiki/templates/combat.html`
- `player_wiki/templates/combat_status.html`
- `player_wiki/templates/combat_dm.html`
