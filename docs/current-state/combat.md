# Combat

Last updated: 2026-06-25

## Owns

- Combat tracker setup, player combat, compatibility Combat Character, DM Status, DM encounter controls, combatant source identity, turn order, tactical edits, combat conditions, and selected-PC sheet reuse.

## Current User-Facing Behavior

- Combat tracker is currently implemented for DND-5E campaigns.
- Player-facing `Combat` defaults to the viewer's tracked player character when one exists, keeping turn order in the sidebar and a sectioned character workspace in the main panel.
- Compatibility `Combat Character` remains available for tracked PCs.
- DM-only `Status` owns selected-combatant inspection and tactical editing.
- DM-only `DM page` / controls owns setup, seeding, and cleanup.
- `/combat/dm` defaults to the full-width `DM status` selected-combatant workspace, while `?view=controls` is a controls-only setup/seeding/cleanup view.
- Selected-PC combat workspaces reuse shared character presentation for supported sheet sections and mutable-state edits.

## Combat State Contract

- Combatants persist source identity through `source_kind` and `source_ref` so DM detail can load linked characters, DM Content statblocks, Systems monsters, or manual/missing-source fallbacks without title matching.
- Shared turn order sorts by turn value descending, Dexterity modifier descending, DM priority ascending, then display name/id fallback.
- DM or owner-player users can edit HP/temp HP where permitted.
- Player resource/spell-slot edits and owner/DM selected-PC equipment-state edits use shared durable character-state paths and can bump combat tracker revision for live refresh.
- Combat row-owned tactical writes use combatant-row revision where relevant.

## Seeding And Source Detail

- DM controls can add combatants from player characters, Systems monsters, DM Content statblocks, or custom combatants.
- Creation-time priority is available for player, Systems, DM Content, and custom combatants.
- DM Content statblocks copy currently parsed HP, speed, initiative bonus, DEX tie-breaker modifier, and source identity into new combatants.
- Combat can inspect source-backed PC, DM Content statblock, Systems monster, or manual/missing-source detail.

## Current Tests Or Verification

- Combat changes usually need route/API tests, browser checks, and focused source-detail or mutation checks around turn flow, selected combatant, conditions, seeding, and selected-PC sheet behavior.

## Known Limits

- Source-backed NPC resources and richer NPC spell/resource edit controls remain deferred.
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
