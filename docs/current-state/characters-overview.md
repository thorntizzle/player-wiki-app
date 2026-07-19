# Characters Overview

Last updated: 2026-07-19

## Owns

- Character storage, route lanes, permissions, and shared read/session/combat conventions.
- The split between stable file-backed definitions and mutable SQLite state.
- Cross-system behavior that applies to DND-5E, Xianxia, and future campaign systems.

## Current User-Facing Behavior

- Campaign character roster and detail pages are available through Flask `/campaigns/...` routes.
- Character roster, detail, native create/import lanes, DND-5E Advanced Editor, Progression Repair, Level Up, Retraining, Xianxia Cultivation, Portrait, Controls, and selected live-state edits are supported by Flask routes and shared JSON contracts.
- Character detail pages default to the normal read shell. Legacy `?mode=session` URLs remain compatibility aliases that render the normal Character page for the requested subpage.
- The character read header is stable above the subpage navigation. Its identity summary can display the portrait image/caption and character identity details, but HP, Temp HP, Hit Dice, System, and resource previews live on their owning sheet sections instead of the header summary.
- Character Controls includes a theme-aware destructive delete card that keeps the warning copy, slug-confirmation input, and destructive action readable across supported themes.
- Shared spell detail popups show resolved upcasting mechanics (`At Higher Levels`) when present and omit the field when no upcast payload is available.
- Character Notes uses the shared revision-checked note mutation for both saving and confirmed note deletion; editable users can clear their character note while read-only users cannot see the delete action.
- DND resource cards on the shared CharacterPane use the existing revision-checked resource mutation, retain autosubmit on blur, and expose a compact per-card `Save` action wherever the current-value field is editable.
- Inventory and Equipment item presentation on Character, Session Character, and Combat selected-PC surfaces uses compact up-to-three-column grids where space allows, stepping down to two columns on tablet/narrow layouts and one column on mobile while preserving item detail dialogs, quantity fields, equipment state toggles, and autosave behavior.
- DND rest confirmations expose final Current HP and current Hit Dice fields seeded from the modeled post-rest state. Applying the rest stores those final values through the same revision-checked rest mutation after automatic resource, spell-slot, and long-rest Hit Dice recovery is modeled.
- Native Flask create and level-up live previews preserve field focus and viewport position while async preview fragments refresh. Normal Character Systems item lookup keeps the current result list visible while a fresh search is in flight.
- `/session/character` remains the active-session sheet lane. The player-facing Session shell can lazy-load Session Character as a mounted pane; direct `/session/character` remains the full-page and no-JS fallback. The Session Character selector is a row under the Session shell tabs with `Open full character page`; it is outside the sheet card, and the embedded sheet omits the duplicate `Session Character` header.
- Combat and DM status selected-PC views reuse the shared character presentation and state-edit contracts where relevant.
- Combat mounts selected-PC play inside the unified Combat Character card. The card keeps the normal character header, HP/rest controls, movement/action-economy combat controls, combat-only Actions/Bonus Actions/Reactions/Attacks/Features sections, and the shared character section model in one flow.

## Current Data Contract

- Stable character definition data lives under `campaigns/<campaign-slug>/characters/<character-slug>/`.
- Character slugs are exact, cross-platform-safe directory names; Character reads, creation/import,
  and deletion reject path-like or escaping identities before state or filesystem effects.
- Imported and manually created characters use `definition.yaml`; imported characters also use `import.yaml`.
- `definition.yaml` carries a normalized top-level `system` discriminator.
- Mutable play state lives in SQLite. Mutable state must not be written back into `definition.yaml`.
- New-character publication is shared across browser native create, Xianxia
  manual import, first-time Markdown/PDF import, and first-time low-level
  content API create. These durable lanes are limited to absent/new targets;
  an all-absent raw character content PUT continues to use
  `content_api_create`. Existing-target Markdown/PDF CLI reimports use the
  coordinator's reimport update lane. A complete existing raw character
  content PUT uses the coordinator's separate `content_api_update` lane.
  Portrait mutation, character deletion, assignment, and other operator-facing
  character commands remain on their existing paths.
- For a new target, `CharacterPublicationCoordinator` commits revision-1
  SQLite state and an active recovery-journal row together before atomically
  publishing `definition.yaml` and then `import.yaml`. A `prepared`,
  `repository_pending`, or `conflict` operation hides the character and blocks
  update, delete, and automatic missing-state initialization until successful
  recovery or explicit repair deletes the journal. Forward recovery skips
  already-desired bytes, never overwrites third-party bytes, and retains
  conflicts for explicit repair.
- Interactive mutations that rebuild the stable definition/import pair together
  with SQLite state use `CharacterPublicationCoordinator.update`. This covers
  browser and API native edit, Level Up, Progression Repair, Retraining,
  definition-changing spell/equipment/infusion paths, Xianxia Cultivation and
  Dao-definition changes, and shared Session/Combat equipment-definition
  mutations. SQLite-only state edits retain their existing state-service path.
- An interactive update records the previous and desired YAML/state digests and
  advances the expected state revision by one. The desired SQLite state and
  `prepared` journal row commit together before atomic definition-then-import
  publication. Recovery accepts already-desired bytes, advances only exact
  prior bytes, and retains missing or third-party bytes as a conflict without
  reconstruction or overwrite.
- Existing-target Markdown/PDF CLI reimports enter
  `CharacterPublicationCoordinator.update` as `markdown_import` or
  `pdf_import`. The reconciled SQLite state and `prepared` journal row commit
  together before ordered atomic publication of `definition.yaml` and then
  `import.yaml`. When reconciliation leaves mutable state unchanged, its exact
  revision, serialized state, update timestamp, and updating actor are
  preserved; when state changes, its revision advances exactly once.
- Reimport recovery accepts already-desired bytes and advances only exact prior
  bytes. Missing or third-party file bytes remain retained conflicts and are
  neither reconstructed nor overwritten. Partial definition/import/state
  targets, and targets that remain active or conflicted after recovery, fail
  closed for explicit repair without further mutation. Active reimports remain
  hidden and support forward recovery after restart or verified backup restore.
- A raw `PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
  first recovers the character key. A partial definition/import/state target,
  or a target that remains active or conflicted after recovery, fails closed
  without further mutation. DND state, and logically unchanged Xianxia state,
  preserves the exact state row, including serialized state, revision, update
  timestamp, and updating actor; changed Xianxia reconciliation advances the
  revision exactly once.
- For `content_api_update`, the desired state and `prepared` journal row commit
  before ordered atomic publication of `definition.yaml` and then `import.yaml`.
  Recovery accepts already-desired bytes, advances only exact prior bytes, and
  retains missing or third-party bytes as a conflict without overwrite.
  `prepared` and `repository_pending` work can complete forward after restart
  or verified backup restore. This is durable forward reconciliation, not one
  atomic transaction across SQLite and the filesystem.
- Portrait set, replacement, and removal use the same coordinator as one
  revision-checked operation spanning the portrait asset, `definition.yaml`,
  `import.yaml`, and SQLite state. Each completed non-no-op mutation advances
  the shared character-state revision exactly once. The durability work does
  not change the existing browser or [API v1](../api-v1.md) URLs,
  authorization, validation, redirects and flash behavior, payloads, or status
  behavior. See [Flask Architecture](flask-architecture.md) for publication
  ordering and [Ops And Fly Deployment](ops-deploy.md) for migration and
  backup behavior.
- Character hard delete retains the existing browser Controls POST, Controls
  API DELETE, and raw content API DELETE contracts. Its sole behavioral commit
  point atomically records a private `prepared` deletion operation, deletes any
  matching SQLite character state and assignment, and writes the one Controls
  audit when applicable before any filesystem mutation. Raw content deletion
  ignores the request body and writes no browser audit.
- Deletion recovery is forward-only. It moves only the exact captured
  `definition.yaml`, `import.yaml`, and one exact managed portrait, when each is
  present, to private tombstones; hides and protects the active character key;
  proves the repository absent; removes the tombstones; and then deletes the
  journal row. Unsafe, symlink, special, missing, changed, third-state, or
  otherwise unexpected authority for an exact owned resource becomes a
  retained conflict instead of being overwritten. Unrelated unmanaged files
  and siblings are ignored and preserved; there is no recursive cleanup.
  Recovery is retry-safe after a process restart or verified backup restore.
- The raw content DELETE continues to support partial managed targets when at
  least one definition, import, state, assignment, or exact managed portrait
  resource exists. Portrait-only deletion is supported. Multiple exact managed
  portrait candidates, or a definition/discovery mismatch, refuse without
  effects. Deletion preserves unrelated files and Combat snapshot or string
  references; it adds no recursive asset cleanup, reassignment, archive,
  cascade, reference-refusal, force, or CLI-delete policy.
- Reimports may refresh stable sheet structure, but must preserve live mutable state and safe native-managed overlays.
- Combat JSON reads expose `selected_player_combat_sections` for the selected tracked PC. Those sections are read-only projections of presented character data; durable combat edits still use the normal combat or character-state mutation lanes.

## Route And Component Ownership

- System capability and route-lane dispatch belongs in `player_wiki/system_policy.py`.
- DND-5E native create/edit/level-up/repair/retraining behavior belongs in the DND character helpers and shared derivation path.
- Xianxia create/import/model/cultivation behavior belongs in the Xianxia-specific helpers.
- `player_wiki/character_reconciliation.py` owns durable absent-target,
  interactive existing-character, existing-target Markdown/PDF reimport, and
  existing-target raw content API PUT and portrait definition/import/state
  publication through `CharacterPublicationCoordinator`, plus character hard
  deletion and forward recovery through `CharacterDeletionCoordinator`;
  `CharacterRepository` and `CharacterStateStore` enforce the active-operation
  read and state boundaries.
- `player_wiki/campaign_content_service.py` owns raw character content
  validation and selection of the absent-create or complete-existing update
  lane.
- Flask route handlers and templates own browser presentation; shared JSON helpers own API/client contracts.
- Portrait upload/remove uses the existing portrait mutation contract and is mounted on the dedicated `Portrait` subpage. PNG/JPG portrait uploads are converted to WebP with the same image-publishing helper used by article images, while GIF/WebP uploads pass through validation. The dedicated Portrait subpage renders the current portrait as a large unframed image rather than a thumbnail card, and upload/remove redirects return to `page=portrait`.

## Permissions

- Editable character-session state users: app admin, campaign DM, assigned player.
- Read-only users: campaign observer and unassigned player.
- Assigned players can list/read their assigned character through live/session/combat JSON lanes even when full Characters navigation is DM-only.
- Assigned DND-5E owners can use ready one-level Level Up for their own sheet; progression repair remains manager-only.
- Controls owner assignment/clear is app-admin-only. Character deletion is DM/admin-only.

## Save And Revision Rules

- Writes are server-validated and revision-checked.
- Character-page, Session Character, and other sheet-state writes use the shared character-state revision.
- Combat row-owned tactical writes use combatant-row revision where relevant.
- Read-mode forms posted with `mode=read` should return to read mode.
- Stale Character-page conflicts stay on the same shell surface and preserve submitted values only for validation or conflict feedback.
- Session Character and combat conflict recovery should stay on their respective surfaces.

## Current Tests Or Verification

- Character behavior is covered across focused route tests, shell/browser checks, API tests, and native/import/repair/level-up suites depending on the touched lane. The June 25, 2026 character stability pass specifically verified native create/level-up live-preview focus and viewport preservation, Systems item lookup result visibility during pending searches, and portrait upload/remove return to the dedicated Portrait subpage.
- Choose the smallest realistic character flow for validation: import, repair, native create, native edit, native level-up, spellcasting, inventory, controls, reimport, read/session sheet, or combat selected-PC behavior.

## Known Limits

- Admin remains a broader app surface.
- PDF import and some spellcasting-management authoring remain narrower than the primary Flask character lanes.
- Current-state docs are now the source of current behavior. Older completed roadmap notes may be stale.

## Related Backlog

- `.local/roadmaps/character-backlog.md`
- Historical source: `.local/character-system-roadmap.md`

## Source Pointers

- `player_wiki/system_policy.py`
- `player_wiki/api.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/character_reconciliation.py`
- `player_wiki/character_repository.py`
- `player_wiki/character_store.py`
- `player_wiki/migrations.py`
- `player_wiki/character_state_service.py`
- `player_wiki/character_assets.py`
- `player_wiki/character_portrait_mutation_routes.py`
- `player_wiki/character_portrait_mutation_api_routes.py`
- `player_wiki/character_controls_delete_routes.py`
- `player_wiki/character_controls_delete_api_routes.py`
- `player_wiki/player_wiki_reconciliation_inspection.py`
- `player_wiki/templates/character_read.html`
- `player_wiki/templates/_character_session_panels.html`
- `tests/test_character_portrait_mutation_route_transport.py`
- `tests/test_api_character_portrait_mutation_route_transport.py`
- `tests/test_character_controls_delete_route_transport.py`
- `tests/test_api_character_controls_delete_route_transport.py`
- `tests/test_character_reconciliation.py`
- `docs/api-v1.md`
