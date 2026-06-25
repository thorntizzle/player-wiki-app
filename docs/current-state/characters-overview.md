# Characters Overview

Last updated: 2026-06-25

## Owns

- Character storage, route lanes, permissions, and shared read/session/combat conventions.
- The split between stable file-backed definitions and mutable SQLite state.
- Cross-system behavior that applies to DND-5E, Xianxia, and future campaign systems.

## Current User-Facing Behavior

- Campaign character roster and detail pages are available in Flask compatibility routes and Gen2 `/app-next` routes.
- Gen2 is the default frontend. Character roster, detail, native create/import lanes, DND-5E Advanced Editor, Progression Repair, Level Up, Retraining, Xianxia Cultivation, Portrait, Controls, and selected live-state edits have Gen2 parity.
- Character detail pages default to the normal read shell. Legacy `?mode=session` URLs remain compatibility aliases that render the normal Character page for the requested subpage.
- The Gen2 character read header is stable above the subpage navigation. Its identity summary can display the portrait image/caption and character identity details, but HP, Temp HP, Hit Dice, System, and resource previews live on their owning sheet sections instead of the header summary.
- Character Controls includes a theme-aware destructive delete card that keeps the warning copy, slug-confirmation input, and destructive action readable across supported themes.
- Gen2 shared spell detail popups show resolved upcasting mechanics (`At Higher Levels`) when present and omit the field when no upcast payload is available.
- Character Notes uses the shared revision-checked note mutation for both saving and confirmed note deletion; editable users can clear their character note while read-only users cannot see the delete action.
- DND resource cards on the shared CharacterPane use the existing revision-checked resource mutation, retain autosubmit on blur, and expose a compact per-card `Save` action wherever the current-value field is editable.
- Inventory and Equipment item presentation on Gen2 Character, Session Character, and Combat selected-PC surfaces uses compact up-to-three-column grids where space allows, stepping down to two columns on tablet/narrow layouts and one column on mobile while preserving item detail dialogs, quantity fields, equipment state toggles, and autosave behavior.
- Gen2 DND rest confirmations expose final Current HP and current Hit Dice fields seeded from the modeled post-rest state. Applying the rest stores those final values through the same revision-checked rest mutation after automatic resource, spell-slot, and long-rest Hit Dice recovery is modeled.
- Native Flask create and level-up live previews preserve field focus and viewport position while async preview fragments refresh. Normal Character Systems item lookup keeps the current result list visible while a fresh search is in flight.
- `/session/character` remains the active-session sheet lane. The player-facing Session shell can lazy-load Session Character as a mounted pane; direct `/session/character` remains the full-page and no-JS fallback. In Gen2, the Session Character selector is a row under the Session shell tabs with `Open full character page`; it is outside the sheet card, and the embedded sheet omits the duplicate `Session Character` header.
- Combat and DM status selected-PC views reuse the shared character presentation and state-edit contracts where relevant.
- Gen2 Combat mounts selected-PC play inside the unified Combat Character card. The card keeps the normal character header, HP/rest controls, movement/action-economy combat controls, combat-only Actions/Bonus Actions/Reactions/Attacks/Features sections, and the shared CharacterPane section model in one flow.

## Current Data Contract

- Stable character definition data lives under `campaigns/<campaign-slug>/characters/<character-slug>/`.
- Imported and manually created characters use `definition.yaml`; imported characters also use `import.yaml`.
- `definition.yaml` carries a normalized top-level `system` discriminator.
- Mutable play state lives in SQLite. Mutable state must not be written back into `definition.yaml`.
- Reimports may refresh stable sheet structure, but must preserve live mutable state and safe native-managed overlays.
- Combat JSON reads expose `selected_player_combat_sections` for the selected tracked PC. Those sections are read-only projections of presented character data; durable combat edits still use the normal combat or character-state mutation lanes.

## Route And Component Ownership

- System capability and route-lane dispatch belongs in `player_wiki/system_policy.py`.
- DND-5E native create/edit/level-up/repair/retraining behavior belongs in the DND character helpers and shared derivation path.
- Xianxia create/import/model/cultivation behavior belongs in the Xianxia-specific helpers.
- Gen2 file routes should stay thin under `frontend/src/routes/**`; page implementations live under `frontend/src/pages/**`.
- CharacterPane shared presentation, mutation, model, draft, and submit-handler modules own reusable Gen2 detail behavior.
- Portrait upload/remove uses the existing portrait mutation contract and is mounted on the dedicated `Portrait` subpage in Gen2 and Flask fallback reads. PNG/JPG portrait uploads are converted to WebP with the same image-publishing helper used by article images, while GIF/WebP uploads pass through validation. The dedicated Portrait subpage renders the current portrait as a large unframed image rather than a thumbnail card, and fallback upload/remove redirects return to `page=portrait`.

## Permissions

- Editable character-session state users: app admin, campaign DM, assigned player.
- Read-only users: campaign observer and unassigned player.
- Assigned players can list/read their assigned character through live/session/combat JSON lanes even when full Characters navigation is DM-only.
- Assigned DND-5E owners can use ready one-level Gen2 Level Up for their own sheet; progression repair remains manager-only.
- Controls owner assignment/clear is app-admin-only. Character deletion is DM/admin-only.

## Save And Revision Rules

- Writes are server-validated and revision-checked.
- Character-page, Session Character, and other sheet-state writes use the shared character-state revision.
- Combat row-owned tactical writes use combatant-row revision where relevant.
- Read-mode forms posted with `mode=read` should return to read mode.
- Stale Character-page conflicts stay on the same shell surface and preserve submitted values only for validation or conflict feedback.
- Session Character and combat conflict recovery should stay on their respective surfaces.

## Current Tests Or Verification

- Character behavior is covered across focused route tests, shell/browser checks, Gen2 session/browser tests, and native/import/repair/level-up suites depending on the touched lane. The June 25, 2026 character stability pass specifically verified native create/level-up live-preview focus and viewport preservation, Systems item lookup result visibility during pending searches, and portrait upload/remove return to the dedicated Portrait subpage.
- Choose the smallest realistic character flow for validation: import, repair, native create, native edit, native level-up, spellcasting, inventory, controls, reimport, read/session sheet, or combat selected-PC behavior.

## Known Limits

- Admin remains a broader app surface, though character-maintenance authoring has Gen2 parity.
- PDF import and some spellcasting-management authoring remain Flask-backed until explicit Gen2 parity slices are opened.
- Current-state docs are now the source of current behavior. Older completed roadmap notes may be stale.

## Related Backlog

- `.local/roadmaps/character-backlog.md`
- Historical source: `.local/character-system-roadmap.md`

## Source Pointers

- `player_wiki/system_policy.py`
- `player_wiki/character_repository.py`
- `player_wiki/character_state_service.py`
- `frontend/src/pages/CharacterPane.tsx`
- `frontend/src/components/CharacterDndSections.tsx`
- `frontend/src/components/CharacterXianxiaSections.tsx`
- `frontend/src/components/CharacterPortraitSection.tsx`
- `docs/api-v1.md`
