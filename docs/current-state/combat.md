# Combat

Last updated: 2026-08-29

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
- DM-only canonical `/combat/dm` Status owns selected-combatant inspection and
  tactical editing. `/campaigns/<campaign_slug>/combat/status` retains endpoint
  ID `campaign_combat_status_view` as a temporary GET/HEAD `302` compatibility
  redirect to `/combat/dm`. Campaign DM/admin authorization is checked before
  parsing or looking up a requested target; a valid authorized `combatant` is
  preserved, and anonymous, outsider, assigned-player, and invalid-target
  denial outcomes remain unchanged. The redirect omits `view=status`.
  Generated canonical Status links use `/combat/dm`, while Controls links
  retain `view=controls`.
- The `/combat/status/live-state` endpoint retains endpoint ID
  `campaign_combat_status_live_state` and its existing methods, access policy,
  headers, payload, selected-detail token/skip behavior, fallback selection,
  fault behavior, and legacy `live_url`. Its canonical `page_url` and generated
  board links point to `/combat/dm` without `view=status`.
- The Status live-state poll is manager-only: campaign DM/admin authorization is checked before
  live metadata, player-character snapshot synchronization, payload rendering, or unchanged-response
  short-circuit evaluation.
- DM-only `DM page` / controls owns setup, seeding, and cleanup.
- `/combat/dm` defaults to the full-width `DM status` selected-combatant workspace, while `?view=controls` is a controls-only setup/seeding/cleanup view.
- `/combat/character` remains a separate compatibility family. An explicit
  `combatant` takes precedence over an authorized legacy `character=<slug>`;
  its existing access, empty-state, and invalid-target denial behavior remains
  unchanged for reassessment after the compatibility horizon.
- The selected-combatant snapshot card groups HP, movement, action economy, active conditions, and visible source-backed NPC resources. DM Status folds editable turn focus, NPC vitals, NPC action economy, source-backed NPC resource counters, conditions, and selected-combatant removal into that selected snapshot instead of rendering separate tactical cards; selected-PC HP and action-economy edits live in the unified Combat Character workspace.
- Integrated source slice `QOL-NPC-6B-C1` adds DM/admin-only forms to the
  canonical DM Status snapshot for selected source-backed NPC counters. Each row
  shows the resource label, current and maximum values, reset label, and source;
  the CSRF-protected form requires the current parent combatant revision and sets one
  counter to an absolute value. Recharge counters accept `0` or `1`, while
  daily and generic counters accept `0` through their source-backed maximum.
  The DM physically rolls recharge and records the result; Campaign Player Wiki
  has no roll mechanics and does not generate or retain a die result.
- The integrated 6B browser enhancement has no controls on player or `View As`
  surfaces. Native submission returns to the selected resource anchor. Enhanced
  submission preserves the selected NPC, focus, document viewport, carousel,
  and open-state context while replacing selected detail. If the response is
  missing or malformed, local focused guidance tells the DM to refresh Combat
  and inspect the counter before submitting again.
- The DM Status Conditions editor stays inside the selected-snapshot control card at desktop, tablet, and mobile widths. The `Add condition` disclosure stacks its fields inside the card, condition rows keep readable names/durations, and row actions such as `Remove` stay on one line.
- In DM Status and Encounter Controls, the shared encounter summary/status band owns Round, current turn, combatant count, and `Advance turn`; setup, cleanup, and DM tactical controls do not duplicate a separate tracker/status card.
- When DM Status focuses a player character, it mounts the same unified Combat Character workspace beneath the selected-combatant snapshot. DM/admin users still select characters through the status combatant focus/carousel instead of a separate player-style selector.
- Selected-PC combat workspaces expose combat-specific character sections from the presented character data, including Actions, Bonus Actions, Reactions, Attacks, and Features when present, followed by shared durable sheet sections and mutable-state edits.
- DM Status presents `Remove combatant` through a lower-risk shared confirmation: it names the selected participant and the encounter-owned conditions, resource counters, and resource notes that will be removed, while stating that linked character, statblock, Systems, and source records remain unchanged. The trigger plus final `Remove combatant` submit provide the confirmation; Cancel, Escape, and backdrop dismissal return focus to the trigger.
- Encounter Controls presents `Clear tracker` through a higher-risk shared confirmation. It states that every combatant and encounter-owned dependent row is removed, round resets to 1, current turn is cleared, and character sheets/source records remain unchanged. The final submit requires an explicit acknowledgement. Both workflows retain visible no-JavaScript scope/consequence details and real CSRF-protected POST forms.
- Selected-PC item and spell detail dialogs in player Combat,
  compatibility Combat Character, and canonical DM Status
  are bounded adopters of the accepted shared presentation lifecycle. The shared controller owns the generic
  trigger and native modal lifecycle: open, Close/Escape/backdrop dismissal, initial Close focus,
  and focus return only to a still-connected invoker.
- The Combat workspace initializer owns scoped fail-safe gating and shared-controller retry on the
  initial mount plus its existing `init` and `restore` seams, including canonical DM Status
  selected-detail replacements. The `/combat/status` page redirect constructs no presentation.
  Missing, no-op, or throwing shared
  initialization keeps native item and spell details visible without exposing an inert trigger;
  a later successful initialization can recover the same scope. Legacy Combat direct dialog
  listeners explicitly exclude this adopted scope, while Session Character initialization and
  Character/Session ownership remain unchanged.
- Item detail adoption preserves each real dedicated-page `href`; it does not invent a dedicated
  spell link. JavaScript-disabled clients retain native item and spell disclosures, and existing
  form and navigation fallbacks remain available.

## Live Update And Conflict Contract

- Slice 6.5 adopts the shared root-scoped async-read policy from
  `player_wiki/templates/_live_ui_helper.html` across player Combat, Combat
  Character, DM Status, and Encounter Controls. `combat-live.js` owns the
  surface poll, selected-target/navigation reads, async mutation state, and
  safe-read pause/resume; the shared policy owns one in-flight read, the
  30-second timeout, exponential safe-read backoff capped at 30 seconds,
  visible retry guidance, and unchanged-versus-updated settling.
- Combat polling uses active/idle `500/3000 ms` for player Combat, Combat
  Character, and Controls, and `1500/4000 ms` for DM Status, with a `30000 ms`
  idle threshold. Hidden roots, hidden documents, and offline windows abort or
  pause safe reads; returning visible/online resumes with an immediate read.
  An unchanged response is `changed: false` and does not replace the mounted
  workspace; a changed response applies the appropriate partials and restores
  the active state.
- A stale combatant or character mutation is an explicit conflict: the server
  returns `X-Live-Mutation-Outcome` (`combatant-revision-conflict` or
  `character-revision-conflict`), and a `409` `state_conflict` payload is also
  recognized. Combat marks the form `revision-conflict`, tells the user that
  the view changed elsewhere and must be refreshed/reviewed, exposes safe
  refresh guidance, and never repeats the mutation automatically. The route
  tests also prove the stored combat row/state remains unchanged after a stale
  write.
- `app.py` attaches local live diagnostics (`X-Live-State-Changed`, live
  revision, payload/query timings, and `Server-Timing`).
  `scripts/measure_live_latency.py` records cold/steady/forced-apply samples,
  uses unchanged steady samples for live pressure projections, and evaluates
  payload, steady-render, and active/idle pressure reductions; its local
  contract is covered by `tests/test_measure_live_latency.py`.

## Combat State Contract

- The Phase 6 Combat compatibility and shared async-read contracts are
  independently accepted, integrated on pushed `main`, and deployed in current
  Fly release `v229` from exact clean commit
  `2c6774b269995320c149dd81e59d842304e740a8`, tree
  `c297efdfaa67e6aa98bef3d52194100fc47948f0`, with runtime subtree
  `8df5d77456ec84877fcb43caf0b26761630bceb1` and test subtree
  `0ea591db4faf8ee86d582958e6506da1c1760ef9`. Its CPython 3.12.12
  canonical suite passed 4,789 tests, skipped 25, and failed 0. Later pushed-main
  workflow, test, and documentation commits were not redeployed; the app runtime
  subtree remains exact. No live content/database write or incident causality is
  claimed.

- Combatants persist source identity through `source_kind` and `source_ref` so DM detail can load linked characters, DM Content statblocks, Systems monsters, or manual/missing-source fallbacks without title matching.
- Shared turn order sorts by turn value descending, Dexterity modifier descending, DM priority ascending, then display name/id fallback.
- DM or owner-player users can edit HP/temp HP where permitted.
- Player resource/spell-slot edits and owner/DM selected-PC equipment-state edits use shared durable character-state paths and can bump combat tracker revision for live refresh.
- Combat turn entry is transport-neutral: browser Advance, API Advance, browser/API Set Current, and compatibility views all use the same service transition. A real entry dispatches the updated tracker revision as a durable monotonic mechanic event; re-selecting the already-current combatant is a no-op. The tracker/resource update, active Divine Avatar Form event, Character state write, and Session invalidation share one SQLite transaction, so a mechanic conflict rolls the turn back instead of reporting partial success. Avatar of Mourning counts each accepted entry once, ends on its tenth counted turn, and exposes its pending table resolution before live selected-character projections refresh.
- Combat row-owned tactical writes use combatant-row revision where relevant.
- Source-backed NPC resource counters are combatant-owned durable rows. DM Content statblocks and Systems monsters can seed supported limited-use counters at combatant creation, and current values persist on the combatant without mutating the underlying source entry. Common daily counters retain their existing behavior. A strict terminal `Recharge 6` or `Recharge 2–6` through `Recharge 5–6` suffix in a Markdown ATX ability heading, or the equivalent terminal literal/tag form in a typed Systems ability-name position, seeds a full one-use counter (`current_value = max_value = 1`) with internal `reset_kind = recharge_d6` and a `recharge_threshold` from 2 through 6.
- Ambiguous, body-only, nonterminal, out-of-range, qualified, conflicting, or otherwise unsupported recharge prose remains a read-only source note, as do at-will and other unmodeled mechanics. A daily/recharge key collision keeps the existing daily counter and the recharge note.
- Recharge parsing runs while source-backed combatant or preset seeds are materialized, not on live reads. Source identity, preset source-version drift fingerprints, preset apply materialization, and cutover/package export preserve the structured metadata. Public combat counter objects retain their existing keys and display `reset_label`; they do not expose `reset_kind` or `recharge_threshold`, and the accepted live query counts are unchanged.
- The integrated 6A parser/model slice itself added no browser mutation.
  Integrated source slice `QOL-NPC-6B-C1`, product commit
  `3d374f9209e73f0fac93efc6913a6cedaf68bc7b` and documentation integration
  commit `025c433949a79c61c5fd4433cee5000817752f7e`, adds only the bounded DM
  Status absolute-value forms described above. It
  reuses the existing combatant resource service/store update and adds no RNG,
  roll receipt or persistence, schema or migration, audit, group reset,
  restore/reset action, automatic event, or source inference. The existing API
  `PATCH .../npc-resources` request and response behavior, public counter keys,
  and accepted live query behavior are unchanged. No deployment or live use is
  claimed.
- Combat payloads include `selected_player_combat_sections` for the selected tracked PC so API/browser clients can render combat-only Actions/Reactions/Attacks/Features inside the unified Combat Character workspace without leaving the combat route.
- Player-facing combat selection keeps meaningful focus in `combatant=` query state where relevant.
- Combat remains the owner of destructive form fetches, busy state, known global transient success/failure feedback, payload rendering, and shared-dialog reinitialization after authority or controls fragment replacement. For a non-2xx, network, or malformed response, it shows and focuses only persistent local guidance that the result could not be confirmed and that Combat should be refreshed before repeating; it does not infer mutation, rollback, or journal state.
- Phase 5's confirmation adoption changes no Combat route, API, manager authorization, CSRF, service/store, persistence ordering, deletion policy, or source-record behavior.
- Slice 5.6d changes no query, hash, selected section, focus, draft, viewport, carousel, polling,
  loading, theme, access, form, CSRF, CSP, static-order, route, API, method, authorization, View As,
  presenter/service/store, storage, persistence, or mutation contract. Its independently accepted
  runtime/test milestone was exact commit `c0a442a275b8d7513a82f53cef9a8161cb8f67d8`, tree
  `4fd26d9c16c37ae35284f47d4eacf74ce73288ee`, and is included in final Phase 5
  candidate `8766292816f2f91f10085f09f2e372651545eced`, which was pushed and
  deployed as historical Fly release `225`, superseded by Phase 6 release
  `v229`.

## Seeding And Source Detail

- DM controls can add combatants from player characters, Systems monsters, DM Content statblocks, or custom combatants.
- Creation-time priority is available for player, Systems, DM Content, and custom combatants.
- DM Content statblocks copy currently parsed HP, speed, initiative bonus, DEX tie-breaker modifier, source identity, supported daily/explicit counters, strictly typed terminal recharge counters, and read-only unsupported mechanic notes into new combatants.
- Systems monster combatants copy parsed HP, speed, initiative/DEX tie-breakers, source identity, supported daily/explicit counters, strictly typed terminal recharge counters from ability-name positions, and read-only unsupported mechanic notes into new combatants.
- Combat can inspect source-backed PC, DM Content statblock, Systems monster, or manual/missing-source detail.

## Encounter Preset Persistence Boundary

- Schema version 10 adds campaign-owned encounter preset aggregates and ordered
  entry rows for character, manual NPC, DM Content statblock, and Systems
  monster source kinds. Presets retain typed source pointers, optional paired
  source-version tokens, quantities, turn values, initiative priorities, and
  custom-NPC setup defaults; they do not copy source titles or bodies.
- The bounded persistence store provides campaign-filtered list/detail,
  transactional aggregate creation, revision-guarded metadata/entry/reorder
  updates that preserve retained entry IDs, and revision-guarded hard deletion
  with entry cascade. Preset revision is the sole aggregate concurrency token.
- The composed preset service provides manager-only campaign-confined list,
  detail, create, update, and delete operations with a 50-entry and 50-expanded-
  combatant ceiling. Reads use the effective identity; View As and other read-
  only contexts cannot mutate. Each successful mutation resolves all sources
  before its existing preset-plus-audit transaction, then the aggregate and
  sanitized audit commit together or roll back together.
- Character, DM Content statblock, and enabled Systems monster rows accept only
  exact campaign-scoped identities. Save/update derive a deterministic
  `combat-seed-v1-sha256` version from the current normalized seeding facts and
  resource seeds; manual NPC rows retain setup fields and no version. Character
  resolution reads one exact active, complete character with existing state and
  never initializes missing SQLite state. Current and temporary HP flow into
  apply materialization but remain excluded from the Character source-version
  projection. DM Content uses one bounded ID query, and Systems uses only an
  existing library plus exact entry identities and current source/entry
  enablement; missing library rows are not seeded by preset reads.
- Explicit inspection reports only sanitized current, changed, disabled, or
  missing/inaccessible states. Explicit apply materialization re-resolves each
  unique source, derives current setup and pristine resource values, honors an
  explicit saved turn value, and rejects drift or unavailable sources without
  adopting a new version.
- Each durable source-backed preset entry now participates as one opaque
  affected consumer in the manager-only Source Health report. Manual NPC rows
  are excluded; quantity does not multiply consumers; repeated source rows stay
  distinct affected consumers while exact source resolution is request-locally
  deduplicated. Source Health compares the saved and current
  `combat-seed-v1-sha256` fingerprints by exact equality after ordinary source
  eligibility and access checks, classifying eligible mismatch with the
  existing `stale-version` result without exposing preset names, raw row IDs,
  source titles, or fingerprint values.
- Encounter Controls now includes a compact manager-only `Saved encounters`
  browser on the existing `/combat/dm?view=controls` GET surface. It provides
  bounded pagination, compose, semantic review, create, stable detail links,
  edit/reorder/update, and revision-guarded delete. Draft row operations and
  review render the complete Controls document without persistence; successful
  create/update/delete use post/redirect/get. Ordinary parsed create/update
  validation errors retain the bounded draft, associate error guidance, and
  mark/focus the Name control. Structural envelope failures rebuild only a
  bounded minimal draft, and an oversized body fails with `413`; stale or
  conflicting writes return review/refresh guidance without retrying.
- Review resolves current accessible Character, DM Content, and Systems sources,
  normalizes the bounded rows, and issues a canonical digest. Save re-parses and
  re-prepares the draft and accepts only the matching digest; source drift,
  disabled/missing/inaccessible sources, aggregate conflicts, and cross-campaign
  selectors fail without partial persistence. Source disclosure is limited to
  safe labels, stable campaign references, source kind, and sanitized status.
- The preset browser is outside the live-replaced Combat controls root. Changed
  polls preserve its exact mounted node, draft values, source selection, open
  confirmation, focus, combatant URL, viewport, and theme. JavaScript-disabled
  clients retain native row actions, review/save/apply navigation, and
  destructive confirmation/delete. Preset create/edit/delete never mutates the
  tracker or any source. Presets still store no current HP loss, conditions,
  spent resources, action economy, movement remaining, turn state, tracker
  revision, or current turn.
- The accepted QOL Preset 3B candidate adds manager-only, explicitly requested
  additive apply review and a native CSRF-protected apply POST. Review
  first passes campaign, manager, and supported-system checks, then uses the
  mutation-capable service authorization before rematerializing current sources.
  It presents proposed and existing combatants in separate groups and warns when
  the tracker is not empty. Ordinary list/detail/live reads do not perform apply
  materialization.
- On POST, request identity loading and View As mutation denial precede CSRF;
  CSRF precedes campaign-object disclosure; campaign scope, manager, and
  supported-system checks precede service authorization and bounded payload
  parsing. The service reauthorizes before opening `BEGIN IMMEDIATE`. Inside that
  transaction it reloads the guarded preset/tracker baseline, rebuilds the
  materialized review, and compares the review digest before writing. It refuses
  an empty or zero-combatant result; missing, disabled, drifted, inaccessible, or
  cross-campaign sources; duplicate Characters within the proposal; a Character
  already on the tracker; stale preset, tracker, source, Character-state,
  authorization, or digest state; and campaign, manager, View As, authentication,
  or CSRF failures. These refusals do not partially write the candidate roster.
- A successful apply adds every expanded combatant plus its source-derived
  counters and notes in that single transaction, then bumps the tracker revision
  once and records one sanitized audit event. Existing combatants and dependent
  rows, round and current-turn state, the selected `combatant` URL, saved
  presets, and source records remain unchanged. The one revision transition
  exposes the completed additive roster to subsequent live reads as one tracker
  state change rather than an increment per inserted row.
- After commit, authoritative readback verifies the tracker revision and each
  created combatant, counter, and note before returning a bounded post/redirect/
  get receipt. If commit acknowledgment or readback is uncertain, the page says
  not to submit again, directs the manager to refresh and inspect the tracker
  before beginning a fresh review, and exposes no repeat apply control. The
  server-rendered workflow remains usable without JavaScript; this candidate
  adds no apply API, asynchronous apply enhancement, or durable outcome ledger.
  This is an accepted local candidate boundary, not a deployment or observed-live
  claim.

## Current Tests Or Verification

- Combat changes usually need route/API tests, browser checks, and focused source-detail or mutation checks around turn flow, selected combatant, conditions, seeding, and selected-PC sheet behavior.
- Current combat verification includes route/API coverage for unified Combat Character workspace structure, summary-band Advance Turn placement, folded snapshot controls, selected-PC combat sections, source-backed NPC resource seeding/edit/conflict/permission behavior, strict recharge positive/false-positive parsing, migration/backfill constraints, provenance/export preservation, unchanged public counter shape/query budgets, and browser smoke checks for player Combat, DM Status, and Encounter Controls placement.
- Accepted `QOL-NPC-6B-C1` evidence is bound to status SHA-256
  `b77249d28ea123a6d525d93abb844a5c41ccbf697a197cb99f062fa23ee93bd7`
  and manifest SHA-256
  `d0008d48e6d7d7fb7f2f723e4989f7aea841c0b226f50705320db1725654c495`.
  Focused route and browser coverage checks absolute recharge/daily/generic
  bounds, one-counter writes, revision conflicts, CSRF, DM/admin authorization,
  player and `View As` control absence, selected-resource no-JavaScript return,
  async selected-NPC/focus/viewport/open-state preservation, and uncertain-
  response guidance. Product commit
  `3d374f9209e73f0fac93efc6913a6cedaf68bc7b` and documentation integration
  commit `025c433949a79c61c5fd4433cee5000817752f7e` are on protected `main` and
  `origin/main`; no deployment or live use is claimed.
- Phase 6 acceptance in `tests/test_campaign_combat_page.py`,
  `tests/test_combat_dm_controls_browser.py`, `tests/test_static_assets.py`,
  `tests/test_route_contract_manifest.py`, and
  `tests/test_measure_live_latency.py` checks authorization-before-target
  disclosure, the GET/HEAD `302`, authorized target preservation, canonical
  Status and Controls URLs, unchanged `/combat/status/live-state` behavior,
  separate `/combat/character` compatibility, no presentation construction on
  redirect, shared-policy adoption, safe-read fault/pause/retry behavior,
  unchanged responses, explicit mutation conflicts, and local diagnostic/
  pressure-check contracts. Accepted desktop `1280x900` and mobile `390x800`
  local browser checks include all four live surfaces. The exact deployed
  Phase 6 identities above passed 4,789 tests, skipped 25, and failed 0 under
  CPython 3.12.12. Named local anchors include
  `test_combat_live_roots_adopt_shared_async_policy_without_global_loading_state`,
  `test_browser_shared_live_async_policy_backoff_conflict_and_mutation_state`,
  `test_flask_combat_safe_read_policy_fault_pause_retry_across_surfaces_and_viewports`,
  `test_flask_dm_status_explicit_revision_conflict_is_not_retried_browser`,
  the unchanged-response checks in `tests/test_campaign_combat_page.py`, and
  `test_build_pressure_projection_uses_unchanged_steady_samples_when_available`
  plus `test_build_checklist_evaluation_marks_pressure_reduction_passes` in
  `tests/test_measure_live_latency.py`.
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
  xfails. That candidate was pushed on `main` and deployed as historical Fly
  release `225`, superseded by Phase 6 release `v229`.

## Current Boundaries

- Source-backed NPC resource support models explicit current/max counters,
  common daily limited-use patterns, and the strict one-use recharge grammar
  described above. The integrated 6B source slice adds manual absolute-value
  recording only. Ambiguous or unsupported recharge prose, at-will lines,
  spell-specific casting rules, shared pools, RNG, roll receipts, group reset,
  automatic reset behavior, and inferred source semantics stay visible as
  read-only source notes or remain unmodeled.
- Combat automation is currently DND-5E-only. Xianxia campaigns keep their character/session surfaces without combat automation.
- Encounter setup currently seeds individual player, Systems, DM Content, or
  custom combatants. Saved preset persistence, manager-only service CRUD,
  source eligibility/versioning, sanitized inspection, and read-only apply
  materialization are modeled, and source-backed preset entries participate in
  manager Source Health. Manager-only preset route/browser presentation is
  available through Encounter Controls. The accepted QOL Preset 3B candidate
  adds explicit reviewed atomic additive application to the tracker through the
  native manager-only browser workflow; replacement apply, an apply API,
  asynchronous apply, and a durable outcome ledger remain outside this boundary.

## Related Backlog

- `.local/roadmaps/combat-backlog.md`
- `.local/roadmaps/xianxia-backlog.md`

## Source Pointers

- `player_wiki/campaign_combat_store.py`
- `player_wiki/campaign_combat_preset_store.py`
- `player_wiki/campaign_combat_preset_service.py`
- `player_wiki/campaign_combat_preset_sources.py`
- `player_wiki/combat_preset_models.py`
- `player_wiki/source_health.py`
- `player_wiki/campaign_combat_service.py`
- `player_wiki/templates/_combat_status_snapshot.html`
- `tests/test_campaign_combat_npc_resource_browser.py`
- `player_wiki/combat_models.py`
- `player_wiki/combat_presenter.py`
- `player_wiki/combat_routes.py`
- `player_wiki/app.py`
- `player_wiki/live_presenter.py`
- `player_wiki/templates/combat.html`
- `player_wiki/templates/combat_status.html`
- `player_wiki/templates/combat_dm.html`
- `player_wiki/templates/_combat_preset_browser.html`
- `player_wiki/templates/_combat_player_workspace_sections.html`
- `player_wiki/templates/_combat_workspace_scripts.html`
- `player_wiki/templates/_destructive_confirmation.html`
- `player_wiki/templates/_combat_dm_controls.html`
- `player_wiki/templates/_combat_dm_selected_authority.html`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/templates/_live_ui_helper.html`
- `player_wiki/static/combat-live.js`
- `scripts/measure_live_latency.py`
- `tests/test_campaign_combat_page.py`
- `tests/test_campaign_combat_preset_store.py`
- `tests/test_campaign_combat_preset_service.py`
- `tests/test_campaign_combat_preset_sources.py`
- `tests/test_campaign_combat_preset_browser.py`
- `tests/test_source_health.py`
- `tests/test_source_health_browser.py`
- `tests/test_combat_dm_controls_browser.py`
- `tests/test_security_headers.py`
- `tests/test_static_assets.py`
- `tests/test_measure_live_latency.py`
