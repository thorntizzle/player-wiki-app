# Combat

Last updated: 2026-07-20

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
- DM Status presents `Remove combatant` through a lower-risk shared confirmation: it names the selected participant and the encounter-owned conditions, resource counters, and resource notes that will be removed, while stating that linked character, statblock, Systems, and source records remain unchanged. The trigger plus final `Remove combatant` submit provide the confirmation; Cancel, Escape, and backdrop dismissal return focus to the trigger.
- Encounter Controls presents `Clear tracker` through a higher-risk shared confirmation. It states that every combatant and encounter-owned dependent row is removed, round resets to 1, current turn is cleared, and character sheets/source records remain unchanged. The final submit requires an explicit acknowledgement. Both workflows retain visible no-JavaScript scope/consequence details and real CSRF-protected POST forms.
- Selected-PC item and spell detail dialogs in player Combat,
  compatibility Combat Character, canonical DM Status, and compatibility `/combat/status`
  are bounded adopters of the accepted shared presentation lifecycle. The shared controller owns the generic
  trigger and native modal lifecycle: open, Close/Escape/backdrop dismissal, initial Close focus,
  and focus return only to a still-connected invoker.
- The Combat workspace initializer owns scoped fail-safe gating and shared-controller retry on the
  initial mount plus its existing `init` and `restore` seams. That includes canonical DM Status and
  compatibility `/combat/status` selected-detail replacements. Missing, no-op, or throwing shared
  initialization keeps native item and spell details visible without exposing an inert trigger;
  a later successful initialization can recover the same scope. Legacy Combat direct dialog
  listeners explicitly exclude this adopted scope, while Session Character initialization and
  Character/Session ownership remain unchanged.
- Item detail adoption preserves each real dedicated-page `href`; it does not invent a dedicated
  spell link. JavaScript-disabled clients retain native item and spell disclosures, and existing
  form and navigation fallbacks remain available.

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
- Combat remains the owner of destructive form fetches, busy state, known global transient success/failure feedback, payload rendering, and shared-dialog reinitialization after authority or controls fragment replacement. For a non-2xx, network, or malformed response, it shows and focuses only persistent local guidance that the result could not be confirmed and that Combat should be refreshed before repeating; it does not infer mutation, rollback, or journal state.
- Phase 5's confirmation adoption changes no Combat route, API, manager authorization, CSRF, service/store, persistence ordering, deletion policy, or source-record behavior.
- Slice 5.6d changes no query, hash, selected section, focus, draft, viewport, carousel, polling,
  loading, theme, access, form, CSRF, CSP, static-order, route, API, method, authorization, View As,
  presenter/service/store, storage, persistence, or mutation contract. Its independently accepted
  runtime/test milestone was exact commit `c0a442a275b8d7513a82f53cef9a8161cb8f67d8`, tree
  `4fd26d9c16c37ae35284f47d4eacf74ce73288ee`, and is included in final Phase 5
  candidate `8766292816f2f91f10085f09f2e372651545eced`, now pushed and deployed
  as Fly release `225`.

## Seeding And Source Detail

- DM controls can add combatants from player characters, Systems monsters, DM Content statblocks, or custom combatants.
- Creation-time priority is available for player, Systems, DM Content, and custom combatants.
- DM Content statblocks copy currently parsed HP, speed, initiative bonus, DEX tie-breaker modifier, source identity, supported daily/explicit NPC resource counters, and read-only unsupported mechanic notes into new combatants.
- Systems monster combatants copy parsed HP, speed, initiative/DEX tie-breakers, source identity, supported daily/explicit NPC resource counters, and read-only unsupported mechanic notes into new combatants.
- Combat can inspect source-backed PC, DM Content statblock, Systems monster, or manual/missing-source detail.

## Current Tests Or Verification

- Combat changes usually need route/API tests, browser checks, and focused source-detail or mutation checks around turn flow, selected combatant, conditions, seeding, and selected-PC sheet behavior.
- Current combat verification includes route/API coverage for unified Combat Character workspace structure, summary-band Advance Turn placement, folded snapshot controls, selected-PC combat sections, source-backed NPC resource seeding/edit/conflict/permission behavior, and browser smoke checks for player Combat, DM Status, and Encounter Controls placement.
- Phase 5 coverage in `tests/test_campaign_combat_page.py`, `tests/test_combat_dm_controls_browser.py`, and `tests/test_static_assets.py` verifies the two confirmation scopes, proportional acknowledgement, manager-only access, CSRF, real no-JavaScript POSTs, dependent-row cleanup and unchanged source records, round/current-turn reset, cancellation and focus return, fragment replacement, known versus ambiguous outcomes, loading exclusion, and both themes.
- Selected-PC dialog coverage in `tests/test_campaign_combat_page.py`,
  `tests/test_combat_dm_controls_browser.py`, `tests/test_static_assets.py`, and
  `tests/test_security_headers.py` checks all four Combat surfaces, scoped initial and replacement
  initialization, native dialog lifecycle and focus, connected-invoker return, fail-safe recovery,
  no-JavaScript detail content, the real item link, legacy-listener isolation, Session regressions,
  access/security/route preservation, and static adopter ownership. Independent verification first
  rejected exact parent `b858b27a6172a40267bb23e6a9b20e1df0dbadb0` only because its maintained
  production-adopter allowlist omitted the new Combat template. Exact repair
  `c0a442a275b8d7513a82f53cef9a8161cb8f67d8` added that allowlist entry and received `ACCEPT`.
  Fresh repaired checks passed the one former failure, four lifecycle static checks, three
  security/route checks, one Combat browser check, four Session browser checks, and all 138 contract
  tests. The rejected parent's broader 148-test Combat run and one adversarial browser check are
  supporting evidence only. Exact integration passed nine canonical focused/browser checks plus the
  same 138 contract tests. The repaired slice was assembled into final Phase 5
  candidate `8766292816f2f91f10085f09f2e372651545eced`; its independent complete
  suite passed 4,649 tests with 25 expected skips and no failures, errors, or
  xfails. The candidate is pushed on `main` and deployed as Fly release `225`.

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
- `player_wiki/templates/_combat_player_workspace_sections.html`
- `player_wiki/templates/_combat_workspace_scripts.html`
- `player_wiki/templates/_destructive_confirmation.html`
- `player_wiki/templates/_combat_dm_controls.html`
- `player_wiki/templates/_combat_dm_selected_authority.html`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/static/combat-live.js`
- `tests/test_campaign_combat_page.py`
- `tests/test_combat_dm_controls_browser.py`
- `tests/test_security_headers.py`
- `tests/test_static_assets.py`
