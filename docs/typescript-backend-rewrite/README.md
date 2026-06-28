# TypeScript Backend Rewrite

Last updated: 2026-06-27

Status: active rewrite planning and implementation track

This folder tracks the deliberate TypeScript backend rewrite path for Campaign Player Wiki. It is separate from incremental Flask refactor work. The goal is a production-capable TypeScript backend that preserves the current product contract, data safety boundaries, local/Fly operations, and rollback path before replacing Flask.

## Source Of Truth

- `charter.md`: scope, freeze rules, cutover gates, rollback requirement, and branch/spec ownership.
- `parity-inventory.md`: current route, API, data, command, and policy inventory that TypeScript must preserve.
- `route-snapshots.md`: executable route snapshot artifact companion review notes.
- `route-snapshots.json`: tracked executable snapshot from
  `scripts/route_snapshots.py` used by parity checks.
- `typescript-route-seed.json`: provisional route seed for initial TypeScript handlers.
- `handoff-2026-06-26.md`: current pause/resume note for the Hono rewrite branch.
- `content-character-staging-readiness.md`: content-character write/delete rollback evidence and staging-readiness decision.
- `staging-rehearsal-harness.md` and `scripts/staging_rehearsal_harness.py`: guarded copied-data/staging-snapshot transcript scaffold, path checks, evidence manifests, family-specific transcript guides, and restore-equivalence comparison helper for TypeScript write-family readiness.
- `combat-rehearsal-readiness.md`: Combat copied-data rehearsal status, commands, evidence checklist, and remaining staging snapshot gate.
- `combat-copied-data-rehearsal-2026-06-28.md`: completed no-live copied-fixture Combat backup/mutate/restore transcript.
- `systems-copied-data-rehearsal-2026-06-28.md`: completed no-live copied-fixture Systems and shared-source backup/mutate/restore transcript.
- `dm-content-copied-data-rehearsal-2026-06-28.md`: completed no-live copied-fixture DM Content backup/mutate/restore transcript.
- `rollback-cutover-runbook.md`: no-live rollback and full cutover evidence runbook, including the `rollback-cutover` harness guide for last known-good Flask target, pre-cutover backups, TypeScript data-delta decisions, restore command shape, and Flask health smoke.
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: local active task queue for the rewrite track.
- `docs/current-state/INDEX.md`: current product contract index. Use it to confirm present behavior before porting any workflow.
- `docs/api-v1.md`: current JSON API contract.

Route parity check command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

### Deferred Scratch Candidates

Option 1 on 2026-06-27 keeps the rewrite contract-only for cutover parity. The remaining `deferred_scratch_proof` route-seed entries are scratch/probe candidates, not current Flask parity targets and not initial-cutover blockers:

- `GET /api/v1/session/login`
- `POST /api/v1/session/login`
- `GET /api/v1/session/me`
- `POST /api/v1/upload`
- `GET /api/v1/notes/<id>`

Do not implement these routes as part of the parity program unless a later architecture/scope decision explicitly approves session-cookie auth, a generic upload API, or a generic note-resource API. Current Flask parity remains anchored to `route-snapshots.json`, `docs/api-v1.md`, current-state docs, and route-specific upload/note workflows.

### Stack Evidence

- `stack-spike.md`: architecture decision record for the TypeScript backend stack evaluation and proof checklist.
- `sqlite-migration-spike.md`: migration-layer proof for Drizzle `generate`/`migrate`, runtime probes, and driver comparison.
- `read-only-compatibility-slice.md`: evidence for the fixture-backed compatibility API slice, including the first controlled SQLite write route validated against a disposable fixture database.
- `ops-image-runtime-proof.md`: no-deploy TypeScript API image-target proof notes, including the current Docker tooling blocker.

## Working Rules

- Python/Flask remains the production authority until TypeScript passes parity gates and a cutover rehearsal.
- TypeScript work starts read-only and fixture-backed before any production write path is added.
- Controlled write routes on this branch are not production-write readiness by themselves; production use still requires backup, dry-run, copied-data rehearsal, and rollback evidence for the affected data.
- Domain, service, persistence, content, auth, Systems, character, session, and combat logic must not live in React route components.
- Experimental spikes stay in `.task-temp` or an isolated approved workspace until a workspace layout decision is recorded.
- Any Python behavior that ships during the rewrite must either be added to the parity inventory or recorded as an explicit deferred exception.

## Initial Phase Order

1. Rewrite charter and tracked spec home.
2. Product contract and parity inventory.
3. Stack and workspace spike with a written decision record.
4. Framework-free domain and policy packages.
5. Compatibility persistence and migration reads.
6. Auth, API contracts, read-only Gen2 slices, then controlled write paths.

## Slice Progress

- `apps/api` exists and now serves:
  - `GET /healthz`
  - `GET /api/v1/app`
  - `GET /api/v1/me`
  - `POST /api/v1/me/view-as`
  - `DELETE /api/v1/me/view-as`
  - `GET /api/v1/me/settings`
  - `PATCH /api/v1/me/settings`
  - `GET /api/v1/systems/import-runs`
  - `GET /api/v1/systems/import-runs/:importRunId`
  - `POST /api/v1/systems/imports/dnd5e`
  - `GET /api/v1/admin`
  - `POST /api/v1/admin/users/invite`
  - `GET /api/v1/admin/users/:userId`
  - `POST /api/v1/admin/users/:userId/membership`
  - `DELETE /api/v1/admin/users/:userId/membership`
  - `POST /api/v1/admin/users/:userId/password-reset`
  - `POST /api/v1/admin/users/:userId/disable`
  - `POST /api/v1/admin/users/:userId/enable`
  - `POST /api/v1/admin/users/:userId/invite`
  - `DELETE /api/v1/admin/users/:userId`
  - `GET /api/v1/campaigns/:campaignSlug/systems`
  - `GET /api/v1/campaigns/:campaignSlug/systems/search`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources`
  - `PUT /api/v1/campaigns/:campaignSlug/systems/sources`
  - `PUT /api/v1/campaigns/:campaignSlug/systems/overrides/*`
  - `POST /api/v1/campaigns/:campaignSlug/systems/custom-entries`
  - `POST /api/v1/campaigns/:campaignSlug/systems/item-mechanics/import`
  - `PUT /api/v1/campaigns/:campaignSlug/systems/custom-entries/:entrySlug`
  - `POST /api/v1/campaigns/:campaignSlug/systems/custom-entries/:entrySlug/archive`
  - `POST /api/v1/campaigns/:campaignSlug/systems/custom-entries/:entrySlug/restore`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId/types/:entryType`
  - `GET /api/v1/campaigns/:campaignSlug/systems/entries/:entrySlug`
  - `GET /api/v1/campaigns/:campaignSlug/combat`
  - `GET /api/v1/campaigns/:campaignSlug/combat/live-state`
  - `GET /api/v1/campaigns/:campaignSlug/combat/systems-monsters/search`
  - `POST /api/v1/campaigns/:campaignSlug/combat/advance-turn`
  - `POST /api/v1/campaigns/:campaignSlug/combat/clear`
  - `POST /api/v1/campaigns/:campaignSlug/combat/player-combatants`
  - `POST /api/v1/campaigns/:campaignSlug/combat/npc-combatants`
  - `POST /api/v1/campaigns/:campaignSlug/combat/statblock-combatants`
  - `POST /api/v1/campaigns/:campaignSlug/combat/systems-monsters`
  - `PATCH /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId/turn`
  - `PATCH /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId/vitals`
  - `PATCH /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId/resources`
  - `PATCH /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId/npc-resources`
  - `POST /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId/conditions`
  - `PATCH /api/v1/campaigns/:campaignSlug/combat/conditions/:conditionId`
  - `DELETE /api/v1/campaigns/:campaignSlug/combat/conditions/:conditionId`
  - `DELETE /api/v1/campaigns/:campaignSlug/combat/combatants/:combatantId`
  - `GET /api/v1/campaigns`
  - `GET /api/v1/campaigns/:campaignSlug`
  - `GET /api/v1/campaigns/:campaignSlug/control`
  - `PATCH /api/v1/campaigns/:campaignSlug/control/visibility`
  - `GET /api/v1/campaigns/:campaignSlug/dm-content`
  - `GET /api/v1/campaigns/:campaignSlug/dm-content/systems`
  - `POST /api/v1/campaigns/:campaignSlug/dm-content/statblocks`
  - `PUT /api/v1/campaigns/:campaignSlug/dm-content/statblocks/:statblockId`
  - `DELETE /api/v1/campaigns/:campaignSlug/dm-content/statblocks/:statblockId`
  - `POST /api/v1/campaigns/:campaignSlug/dm-content/conditions`
  - `PUT /api/v1/campaigns/:campaignSlug/dm-content/conditions/:conditionDefinitionId`
  - `DELETE /api/v1/campaigns/:campaignSlug/dm-content/conditions/:conditionDefinitionId`
  - `GET /api/v1/campaigns/:campaignSlug/help`
  - `GET /api/v1/campaigns/:campaignSlug/wiki`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/sections/:sectionSlug`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/pages/*`
  - `GET /api/v1/campaigns/:campaignSlug/session`
  - `POST /api/v1/campaigns/:campaignSlug/session/start`
  - `POST /api/v1/campaigns/:campaignSlug/session/close`
  - `POST /api/v1/campaigns/:campaignSlug/session/messages`
  - `POST /api/v1/campaigns/:campaignSlug/session/articles`
  - `PUT /api/v1/campaigns/:campaignSlug/session/articles/:articleId`
  - `POST /api/v1/campaigns/:campaignSlug/session/articles/:articleId/reveal`
  - `DELETE /api/v1/campaigns/:campaignSlug/session/articles/:articleId`
  - `DELETE /api/v1/campaigns/:campaignSlug/session/articles/revealed`
  - `GET /api/v1/campaigns/:campaignSlug/session/article-sources/search`
  - `GET /api/v1/campaigns/:campaignSlug/session/articles/:articleId/image`
  - `GET /api/v1/campaigns/:campaignSlug/session/logs/:sessionId`
  - `DELETE /api/v1/campaigns/:campaignSlug/session/logs/:sessionId`
  - `GET /api/v1/me`
  - `GET /api/v1/me/settings`
  - `PATCH /api/v1/me/settings`
  - `GET /api/v1/campaigns/:campaignSlug/content/config`
  - `PATCH /api/v1/campaigns/:campaignSlug/content/config`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages/*`
  - `PUT /api/v1/campaigns/:campaignSlug/content/pages/*`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/pages/*`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets/*`
  - `PUT /api/v1/campaigns/:campaignSlug/content/assets/*`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/assets/*`
  - `GET /campaigns/:campaignSlug/assets/*`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `PUT /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `GET /api/v1/campaigns/:campaignSlug/characters`
  - `GET /api/v1/campaigns/:campaignSlug/characters/create`
  - `POST /api/v1/campaigns/:campaignSlug/characters/create` (Xianxia native create; bounded DND-5E PHB Fighter/Barbarian level-one slice plus PHB Cleric/Life Domain spellcasting create slice; full DND builder parity pending)
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug`
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug/advanced-editor`
  - `PUT /api/v1/campaigns/:campaignSlug/characters/:characterSlug/advanced-editor` (reference, proficiency, stat-adjustment, recoverable-penalty, custom-feature, and manual-equipment fields with linked-page selector hydration plus `page_ref` validation/round-trip; linked custom-feature defaults, campaign-feat Optional Feature choices, and linked additional-spell choices supported; spell support/manager replacement derivation and full native derivation parity pending)
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug/retraining` (empty-readiness shell plus ready-state linked custom-feature retraining context)
  - `POST /api/v1/campaigns/:campaignSlug/characters/:characterSlug/retraining` (bounded linked custom-feature structured-choice save parity through the Advanced Editor derivation path)
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug/level-up` (unsupported shells plus bounded ready context for TypeScript-created DND-5E Fighter/Barbarian level-one sheets)
  - `POST /api/v1/campaigns/:campaignSlug/characters/:characterSlug/level-up` (bounded TypeScript-created DND-5E Fighter/Barbarian level-one to level-two fixture save; broader save parity pending)
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug/progression-repair` (unsupported/current shells plus bounded imported DND-5E class/subclass/species/background ref repair context)
  - `POST /api/v1/campaigns/:campaignSlug/characters/:characterSlug/progression-repair` (bounded imported DND-5E class/subclass/species/background ref fixture save; broader repair parity pending)
  - `GET /api/v1/campaigns/:campaignSlug/characters/:characterSlug/cultivation` (supported Xianxia read context)
  - `POST /api/v1/campaigns/:campaignSlug/characters/:characterSlug/cultivation` (`save_insight`, `record_gathering_insight`, `spend_cultivation_energy`, `spend_meditation_yin_yang`, `spend_conditioning`, `spend_training`, `advance_martial_art_rank`, `learn_generic_technique`, `start_realm_ascension_review`, `reset_realm_ascension_stats`, `apply_immortal_realm_rebuild`, `apply_divine_realm_rebuild`, and `confirm_realm_ascension`)
  - `PATCH /api/v1/campaigns/:campaignSlug/characters/:characterSlug/sheet-edit`
  - `GET /api/v1/campaigns/:campaignSlug/characters/import/xianxia-manual`
  - `POST /api/v1/campaigns/:campaignSlug/characters/import/xianxia-manual` (preview and confirmed local fixture/SQLite create)
- Implemented Character Controls JSON mutation endpoints:
  - `POST /api/v1/campaigns/:campaignSlug/characters/:characterSlug/controls/assignment`
  - `DELETE /api/v1/campaigns/:campaignSlug/characters/:characterSlug/controls/assignment`
  - `DELETE /api/v1/campaigns/:campaignSlug/characters/:characterSlug/controls`
- Campaign detail uses fixture-backed reads from `tests/fixtures/sample_campaigns` by default and supports
  `CPW_CAMPAIGNS_DIR` override.
- The first tracked SQLite read path uses `better-sqlite3` against `CPW_DB_PATH` for
  the Systems import-run list/detail routes and the campaign Systems landing/search/source
  list/detail/category/entry-detail routes, while unauthenticated requests still preserve Flask's
  `auth_required` envelope, bearer API tokens now drive app-admin import-run access and campaign
  role visibility from active memberships, fixture roles remain available for parity tests, landing
  search responses include source cards, entry search results, and rules-reference metadata search
  fields, entry detail responses include parsed metadata/body JSON, source state, override payloads,
  and Flask compatibility links, and missing detail rows return explicit JSON 404s.
- The first combat-adjacent read path reuses the Systems SQLite fixture layer for Combat Systems monster
  search, preserving Flask-compatible unauthenticated `auth_required`, bearer-token or fixture-role
  manager-only access, short-query guidance, and monster HP/speed/initiative result formatting.
- The Combat state shell now serves read-only tracker payloads for `GET .../combat` and
  `GET .../combat/live-state`, preserving Flask-compatible unauthenticated `auth_required`, fixture
  or bearer-token membership-derived player/DM permission splits, live polling metadata,
  invalid/no-membership bearer auth envelopes, unchanged-response short-circuit behavior, DM/admin
  player-character setup choices from fixture character definitions, DM Content statblock setup
  choices, custom condition names merged into combat condition options, and SQLite tracker/combatant
  reads with current-turn labels, ordered combatants, visible conditions, and NPC resource summaries
  when the fixture database carries Combat rows.
- The first Combat write route now serves `POST .../combat/combatants/:combatantId/set-current`
  for bearer-token DM/admin users against fixture SQLite, denying fixture-role writes, validating
  supported Combat campaigns and combatant existence, resetting the selected combatant's movement
  and action economy, bumping tracker/combatant revisions, and returning the refreshed Combat payload.
- The Combat advance-turn route now serves `POST .../combat/advance-turn` for bearer-token DM/admin
  users against fixture SQLite, denying fixture-role writes, validating non-empty DND-5E Combat
  encounters, cycling through the ordered combatant list, incrementing the round when wrapping,
  resetting the new current combatant's movement and action economy, bumping tracker/combatant
  revisions, and returning the refreshed Combat payload.
- The Combat clear route now serves `POST .../combat/clear` for bearer-token DM/admin users against
  fixture SQLite, denying fixture-role writes, removing campaign combatants plus condition/resource
  rows, resetting the tracker to round 1 with no current combatant, bumping the tracker revision,
  and returning the refreshed empty Combat payload.
- The Combat player-combatant add route now serves `POST .../combat/player-combatants` for
  bearer-token DM/admin users against fixture SQLite, denying fixture-role writes, validating visible
  active characters, initializing missing character state through the existing content-state helper,
  defaulting turn value from initiative, validating priority/duplicates, bumping tracker revision
  without changing the current turn, and returning the refreshed Combat payload.
- The Combat manual NPC add route now serves `POST .../combat/npc-combatants` for bearer-token
  DM/admin users against fixture SQLite, denying fixture-role writes, validating manual NPC name,
  initiative, HP, temp HP, movement, and priority fields, defaulting dexterity modifier from
  initiative bonus when blank, storing manual source identity without resource seeds, bumping tracker
  revision without changing the current turn, and returning the refreshed Combat payload.
- The Combat DM Content statblock add route now serves `POST .../combat/statblock-combatants`
  for bearer-token DM/admin users against fixture SQLite, denying fixture-role writes, validating
  selected statblocks, defaulting name/initiative/HP/movement from DM Content rows, extracting the
  DEX tie-breaker from statblock Markdown, seeding supported source-backed resource counters and
  read-only mechanic notes, bumping tracker revision without changing the current turn, and returning
  the refreshed Combat payload.
- The Combat Systems monster add route now serves `POST .../combat/systems-monsters` for
  bearer-token DM/admin users against fixture SQLite, denying fixture-role writes, validating enabled
  Systems monster entries, deriving initiative/DEX/HP/movement from Systems metadata, seeding
  supported source-backed resource counters and read-only mechanic notes from structured Systems body
  JSON, storing Systems source identity, bumping tracker revision without changing the current turn,
  and returning the refreshed Combat payload.
- The Combat turn-value route now serves `PATCH .../combat/combatants/:combatantId/turn` for
  bearer-token DM/admin users against fixture SQLite, denying fixture-role writes, validating
  supported Combat campaigns and combatant existence, defaulting omitted turn/priority fields from
  the existing combatant row, enforcing the combatant row revision guard when supplied, bumping both
  combatant and tracker revisions, and returning the refreshed Combat payload.
- The Combat vitals route now serves `PATCH .../combat/combatants/:combatantId/vitals` against
  fixture SQLite, denying fixture-role writes, allowing bearer-token DM/admin users to update NPC or
  player-character vitals, allowing assigned bearer-token players to update their own player-character
  HP/temp HP through `character_state`, enforcing state/combatant revision guards, mirroring
  player-character sheet vitals back to the combatant row, bumping combatant/tracker revisions, and
  returning refreshed Combat payloads with player-character `state_revision` values.
- The Combat resources route now serves `PATCH .../combat/combatants/:combatantId/resources`
  against fixture SQLite, denying fixture-role writes, allowing bearer-token DM/admin users to update
  movement/action economy on any combatant, allowing assigned bearer-token players to update their own
  player-character combatant row, strictly validating action booleans and remaining movement, enforcing
  the combatant revision guard when supplied, bumping combatant/tracker revisions, and returning the
  refreshed Combat payload.
- The Combat NPC source-resource route now serves
  `PATCH .../combat/combatants/:combatantId/npc-resources` against fixture SQLite, denying fixture-role
  writes and player bearer writes, validating source-backed NPC counter payloads, enforcing the
  combatant revision guard when supplied, persisting existing counter current values only, bumping
  combatant/tracker revisions, and returning the refreshed Combat payload.
- The Combat condition add/delete routes now serve
  `POST .../combat/combatants/:combatantId/conditions` and
  `DELETE .../combat/conditions/:conditionId` against fixture SQLite, denying fixture-role writes and
  player bearer writes, validating condition name/duration constraints and condition existence,
  bumping the tracker revision, and returning refreshed Combat payloads.
- The Combat condition update route now serves API-only
  `PATCH .../combat/conditions/:conditionId` as the JSON replacement for Flask's form
  `POST /campaigns/<slug>/combat/conditions/<id>`, denying fixture-role writes and player bearer
  writes, validating condition name/duration constraints and condition existence, bumping the tracker
  revision with the acting user, and returning refreshed Combat payloads.
- The Combat combatant delete route now serves `DELETE .../combat/combatants/:combatantId` against
  fixture SQLite, denying fixture-role writes and player bearer writes, validating combatant
  existence, removing the combatant plus dependent condition/resource rows, clearing current-turn
  focus when needed, bumping the tracker revision, and returning the refreshed Combat payload.
- The first Session manager lookup slice now serves `GET .../session/article-sources/search`, preserving
  Flask-compatible unauthenticated `auth_required`, fixture or bearer-token membership-derived
  manager-only access, short-query guidance, visible wiki page results, accessible Systems entry
  results, and explicit missing-campaign JSON.
- The Session state route now has a role-aware SQLite read path for fixture roles or bearer API tokens,
  reading active sessions, messages, staged/revealed article rows, article image metadata,
  closed-session log summaries, session recipient player choices, and session revisions from
  `CPW_DB_PATH`, while no-header requests keep the empty read-only fixture shell and
  invalid/no-membership bearer requests use the standard auth/forbidden JSON envelopes. Bearer-token
  player reads now preserve Flask's private-message visibility rule for global messages, messages
  targeted to that player, and messages authored by that player.
- The first Session write route now serves `POST .../session/messages` for bearer API-token campaign
  members against `CPW_DB_PATH`, preserving Flask-compatible JSON parsing, active-session checks,
  message length/body validation, `global`/`dm_only`/targeted `player` recipient validation, SQLite
  `campaign_session_messages` inserts, session revision bumps, recipient labels, refreshed read
  visibility, and missing-campaign JSON. Current validation covers a disposable fixture database only;
  production/staging write readiness remains gated by migration, backup, and rollback rehearsal.
- The Session lifecycle write routes now serve `POST .../session/start` and `POST .../session/close`
  for bearer API-token DM/admin users against `CPW_DB_PATH`, preserving Flask-compatible manager
  permission checks, duplicate-start and empty-close validation messages, SQLite
  `campaign_sessions` inserts/updates, session revision bumps, serialized session responses, refreshed
  closed-log summaries, and missing-campaign JSON. Current validation covers a disposable fixture
  database only; production/staging write readiness remains gated by migration, backup, and rollback
  rehearsal.
- The Session article-store write routes now serve create/update/reveal/delete/clear-revealed
  mutations for bearer API-token DM/admin users against `CPW_DB_PATH`, preserving Flask-compatible
  manager permission checks, manual/upload/wiki staging modes, embedded image validation, wiki page
  and Systems source pulls, unrevealed staged-article update rules, reveal chat-message creation,
  article-message cleanup on deletion, session revision bumps, serialized article/message responses,
  and missing-campaign or missing-article JSON. Current validation covers a disposable fixture
  database only; production/staging write readiness remains gated by migration, backup, and rollback
  rehearsal.
- The Session article image route now streams SQLite-backed fixture image bytes with stored media
  types, preserving fixture or bearer-token manager access to staged/revealed images and player
  access only to images on articles revealed in the active session.
- The Session log detail route now reads closed session records and all closed-session messages
  from SQLite for fixture or bearer-token DM/admin roles, preserving manager-only access and message
  recipient metadata for historical chat logs.
- The Session log delete route now removes closed chat logs for bearer-token DM/admin users against
  `CPW_DB_PATH`, preserving Flask-compatible missing/active-log validation, closed-log message
  cleanup, revealed-article session provenance unlinking, and session revision bumps. Current
  validation covers a disposable fixture database only; production/staging write readiness remains
  gated by migration, backup, and rollback rehearsal.
- The first identity bootstrap slice now serves `GET /api/v1/me`, preserving
  Flask-compatible unauthenticated `auth_required` behavior, returning synthetic role-header
  user, membership, preference, and View As metadata for player, DM, and admin fixture reads,
  and reading live-style API-token identity, active memberships, normalized preferences, and
  admin View As choices from `CPW_DB_PATH` when a bearer token is supplied. The View As mutation
  pair now serves `POST /api/v1/me/view-as` and `DELETE /api/v1/me/view-as` for bearer-token
  app admins, storing the requested active user in a same-origin cookie, preserving the real admin
  identity on `/me` while reporting `auth_source: "view_as"`, switching campaign safe reads to the viewed user's effective role, and
  blocking campaign API writes with `view_as_read_only` while preview mode is active.
- The account settings slice now serves `GET /api/v1/me/settings` and
  `PATCH /api/v1/me/settings`, preserving Flask-compatible unauthenticated `auth_required`
  behavior, the current theme preset and live-session chat-order choice metadata, fixture-role
  reads, bearer-token user/preference reads, bearer-token `user_preferences` writes, validation
  for theme/chat-order choices, retired `frontend_mode` rejection, and refreshed preference payloads.
  Bearer API-token identity reads now update `api_tokens.last_used_at` when the stored timestamp is
  older than the configured session-touch interval.
- The Admin shell now serves `GET /api/v1/admin`, `POST /api/v1/admin/users/invite`,
  `GET /api/v1/admin/users/:userId`, `POST /api/v1/admin/users/:userId/membership`, and
  `DELETE /api/v1/admin/users/:userId/membership`,
  `POST /api/v1/admin/users/:userId/assignment`, and
  `DELETE /api/v1/admin/users/:userId/assignment`,
  preserving app-admin-only fixture or bearer-token access, campaign and character choices, user
  cards, membership and assignment summaries, audit filters, paginated audit rows, Flask CSV export
  links, Gen2/Flask Admin URLs, and explicit JSON missing-user handling. Membership mutations are
  bearer API-token app-admin writes against disposable fixture SQLite only, with fixture-role write
  denial, Flask-compatible validation/success messages, explicit select-then-insert/update
  membership persistence, refreshed detail payloads, and `auth_audit_log` membership events.
  Assignment mutations are also bearer API-token app-admin writes against disposable fixture SQLite
  only, validating visible active characters plus active player memberships, refreshing Admin user
  detail payloads, and writing `character_assignment_*` audit events with `admin_screen` metadata.
  Password-reset issuance is bearer API-token app-admin only, validates active target users,
  consumes prior unused reset tokens, persists SHA-256-hashed reset tokens with the configured
  reset TTL, refreshes detail payloads, and writes `password_reset_issued` audit events. Account
  disable/enable mutations are bearer API-token app-admin only, protect the acting admin account,
  refresh detail payloads, increment `auth_version`, update account status, write `user_disabled`
  and `user_enabled` audit events, revoke all target sessions and API tokens on disable, and restore
  disabled accounts to `active` or `invited` based on password presence.
  Invite creation and resend-invite mutations are bearer API-token app-admin only, validate invite
  type/campaign/user identity rules, persist invited accounts and optional active campaign
  memberships, consume prior unused invite tokens, persist SHA-256-hashed invite tokens with the
  configured invite TTL, refresh detail payloads, and write `user_created`, `user_invited`, and
  optional `membership_created` audit events without raw token metadata.
  User deletion is bearer API-token app-admin only, protects the acting admin account, requires
  case-insensitive email confirmation, removes target memberships, assignments, invite/reset
  tokens, sessions, and API tokens, nulls retained user references, refreshes dashboard payloads,
  and writes `user_deleted` audit events with deleted-user metadata.
- The Campaign Control read route now serves `GET .../control`, preserving Flask-compatible
  visibility-management auth for fixture or bearer-token DM/admin identities, default campaign
  visibility rows, optional SQLite visibility overrides, admin-only Private choices, rules, notes,
  and Flask/Gen2 control links.
- The Campaign Control visibility write route now serves `PATCH .../control/visibility` for bearer
  API-token managers against `CPW_DB_PATH`, preserving Flask-compatible visibility object validation,
  admin-only Private restrictions, changed-scope labels, no-change messaging, SQLite
  `campaign_visibility_settings` upserts, `auth_audit_log` events with `campaign_control_api`
  metadata, refreshed control payloads, and missing-campaign JSON. Current validation covers a
  disposable fixture database only; production/staging write readiness remains gated by migration,
  backup, and rollback rehearsal.
- The first DM Content read route now serves `GET .../dm-content`, preserving Flask-compatible
  unauthenticated `auth_required`, DM/admin-only access for fixture roles and bearer API tokens,
  SQLite statblock and custom condition serialization, statblock parser feedback summaries, lane
  counts for Player Wiki pages, staged Session articles, and Systems sources, and missing-campaign
  JSON.
- The DM Content Systems management read route now serves `GET .../dm-content/systems`, preserving
  Flask-compatible unauthenticated `auth_required`, DM/admin-only access for fixture roles and bearer
  API tokens, source policy rows, shared-core permission state, entry overrides, custom campaign
  entries, campaign item mechanics rows, sanitized import-run history without raw source paths, and
  missing-campaign JSON. This route is read-only and fixture/SQLite-backed; Systems source policy
  entry overrides, custom-entry writes, and item-mechanics import are implemented as separate mutation
  slices.
- The first Systems source-policy write route now serves `PUT .../systems/sources` for bearer-token
  DM/admin actors against `CPW_DB_PATH`, preserving fixture-role write denial, player/outsider
  forbiddance, update-row shape validation, boolean enablement validation, source-id validation,
  private/admin and public-allowed visibility gates, proprietary source acknowledgement,
  `campaign_system_policies` and `campaign_enabled_sources` upserts, `auth_audit_log`
  source-update events, refreshed source rows, and missing-campaign JSON. Fixture route validation
  exists; `systems-copied-data-rehearsal-2026-06-28.md` records the copied-data rollback pass for the
  combined Systems write family. Production or staging write readiness remains gated by migration,
  staging snapshot rehearsal, and rollback approval.
- The bounded Systems entry override write route now serves `PUT .../systems/overrides/*` for
  bearer-token DM/admin actors against `CPW_DB_PATH`, preserving slashy entry keys, fixture-role
  write denial, player/outsider forbiddance, Flask-compatible boolean coercion, private/admin and
  public-allowed visibility gates, `campaign_system_policies` and `campaign_entry_overrides`
  upserts, `auth_audit_log` entry-override events, serialized override/entry responses, and
  missing-campaign JSON. Fixture route validation exists; `systems-copied-data-rehearsal-2026-06-28.md`
  records the copied-data rollback pass for the combined Systems write family. Production or staging
  write readiness remains gated by migration, staging snapshot rehearsal, and rollback approval.
- The custom campaign Systems entry write family now serves `POST .../systems/custom-entries`,
  `PUT .../systems/custom-entries/:entrySlug`, and the archive/restore POST routes for bearer-token
  DM/admin actors against `CPW_DB_PATH`, preserving custom source bootstrap, slug/key preservation,
  title/type/visibility/body validation, item-only linked page validation, SQLite `systems_entries`
  and `campaign_entry_overrides` writes, override-based archive/restore, `auth_audit_log` custom
  entry events, serialized entry responses, refreshed DM Content Systems payloads, and
  missing-campaign JSON. Fixture route validation exists; `systems-copied-data-rehearsal-2026-06-28.md`
  records the copied-data rollback pass for the combined Systems write family. Production or staging
  write readiness remains gated by migration, staging snapshot rehearsal, and rollback approval.
- The campaign item mechanics import route now serves `POST .../systems/item-mechanics/import` for
  bearer-token DM/admin actors against `CPW_DB_PATH`, preserving published item-page validation,
  custom source bootstrap, imported item slug/key reuse, linked page metadata, approved modeled
  review payloads, override preservation on refresh, `campaign_systems_item_mechanics_imported`
  audit rows, serialized entry responses, refreshed DM Content Systems payloads, and
  missing-campaign JSON. Fixture route validation exists; `systems-copied-data-rehearsal-2026-06-28.md`
  records the copied-data rollback pass for the combined Systems write family. Production or staging
  write readiness remains gated by migration, staging snapshot rehearsal, and rollback approval.
- The shared DND-5E Systems import route now serves `POST /api/v1/systems/imports/dnd5e` for bearer
  API-token app-admin actors against `CPW_DB_PATH`, preserving fixture-role write denial, source and
  entry-type validation, `.zip` archive validation through a small pure-JS dependency, unsafe archive
  path rejection, mechanics-only media stripping, `systems_import_runs` persistence, and source-row
  replacement for the requested source/type slice. Fixture route validation exists;
  `systems-copied-data-rehearsal-2026-06-28.md` records the copied-data rollback pass for the combined
  Systems write family. Production or staging import readiness remains gated by migration, staging
  snapshot rehearsal, and rollback approval.
- The DM Content statblock and custom condition API mutations now serve bearer-token DM/admin
  create/update/delete routes against `CPW_DB_PATH`, preserving Flask-compatible durable-actor
  requirements, markdown statblock upload validation and parser field extraction, condition
  name/description/duplicate validation, deleted-record response payloads, and missing-resource
  `validation_error` JSON. Fixture route validation exists; `dm-content-copied-data-rehearsal-2026-06-28.md`
  records the copied-data rollback pass for statblock and custom condition writes plus Combat
  source-backed statblock/condition smoke after restore. Production or staging write readiness remains
  gated by migration, staging snapshot rehearsal, and rollback approval.
- The content/config, content page, content asset, and content character management read routes now
  preserve Flask-compatible content-management auth: no identity returns `auth_required`, fixture or
  bearer-token player/outsider identities return `forbidden`, and fixture or bearer-token DM/admin
  identities can read the fixture-backed payloads.
- The content/config write route now serves `PATCH .../content/config` for bearer API-token DM/admin
  users against the fixture campaign tree, preserving Flask-compatible editable-field validation,
  `current_session` coercion, `system` and `systems_library` alias normalization, `campaign.yaml`
  writes, refreshed campaign-detail reads, empty-body no-op behavior, and missing-campaign JSON.
  Current validation covers a disposable copied fixture campaign only; production/staging write
  readiness remains gated by migration, backup, and rollback rehearsal.
- The content page write/delete routes now serve `PUT` and `DELETE .../content/pages/*` for bearer
  API-token DM/admin users against copied fixture campaign trees, preserving metadata/body validation,
  Markdown frontmatter writes, page list/detail refresh, backlink-based removal-safety payloads,
  `hard_delete_blocked` responses, force-delete override support, deleted-reference payloads, and
  missing-campaign/page JSON. Current validation covers disposable copied fixtures and backlink
  blockers; broader character/session provenance blockers remain tied to later TypeScript content
  parity work.
- The content asset write/delete routes now serve `PUT` and `DELETE .../content/assets/*` for bearer
  API-token DM/admin users against copied fixture campaign trees, preserving Flask-compatible
  embedded `asset_file` validation, base64 decoding, safe asset path writes, list/detail refresh,
  summary and deleted-reference payloads, missing-campaign JSON, missing-asset JSON, and empty parent
  directory pruning on delete. Current validation covers disposable copied fixtures only; production
  or live publication still requires the normal backup, sync, and rollback gates.
- The content character write/delete routes now serve `PUT` and `DELETE .../content/characters/:characterSlug`
  for bearer API-token DM/admin users against copied fixture campaign trees, preserving
  definition/import YAML validation, route-slug normalization, Flask-style default API import
  metadata, list/detail refresh, missing-campaign JSON, and missing-character JSON. The route now
  initializes missing SQLite `character_state` rows for DND-5E and Xianxia definitions, reports
  `state_created` from real row insertion, reconciles existing Xianxia mutable state against updated
  definition maxima without writing live state into `definition.yaml`, and deletes SQLite
  character-state plus assignment rows while reporting `deleted_state` / `deleted_assignment` from
  real deletes. Current validation covers disposable copied fixture files, fixture SQLite, and
  Flask-vs-TypeScript golden parity for DND-5E state initialization/deletion plus Xianxia mutable
  state preservation/clamping. It also includes a copied-data backup/restore rehearsal that proves
  a content-character write/delete can be rolled back across definition/import YAML, portrait assets,
  SQLite state rows, and assignment rows. The staging-readiness decision labels this route family
  `copied-data rollback ready; staging snapshot required`, so staging or production write enablement
  still requires an approved staging-volume snapshot rehearsal.
- The first character session-state write routes now serve
  `PATCH .../characters/:characterSlug/session/vitals` and
  `PATCH .../characters/:characterSlug/session/resources/:resourceId` plus
  `PATCH .../characters/:characterSlug/session/spell-slots/:level` and
  `PATCH .../characters/:characterSlug/session/inventory/:itemId` and
  `PATCH .../characters/:characterSlug/session/xianxia-active-state` and
  `PATCH .../characters/:characterSlug/session/currency` and
  `PATCH .../characters/:characterSlug/session/notes` plus
  `PATCH .../characters/:characterSlug/session/personal` and the legacy Character-page
  `PATCH .../characters/:characterSlug/sheet-edit` batch route for bearer API-token app admins,
  campaign DMs, and assigned players where the route's Flask-compatible scope gates allow it. They write only the shared SQLite `character_state`
  row, enforce the shared state revision, support DND HP/temp HP/Hit Dice, resource current/delta
  updates, spell-slot used/delta-used updates with optional slot-lane migration, DND inventory
  quantity/delta updates, and Xianxia HP/temp HP plus Stance/Energy/Yin-Yang/Dao fields, nested
  inventory quantity updates with top-level mirror sync, active Stance/Aura manual state edits, and
  absolute currency denomination updates for DND `state.currency` plus Xianxia
  `state.xianxia.currency` with non-negative Xianxia clamping, plus player note text updates that
  preserve the rest of the notes object, and personal physical/background note updates that preserve
  other note fields while clearing null/omitted values to empty strings. The legacy sheet-edit batch
  route accepts absolute-value Character-page sections only, rejects delta/rest-style actions, uses
  one batch-wide revision check and conflict message, denies fixture-role writes, and returns refreshed
  `character.state_record` payloads. Current
  validation covers disposable copied fixture files and fixture SQLite only; further character
  session-state route families remain sliced separately.
- Character rest preview/apply parity now serves
  `GET .../characters/:characterSlug/rest-preview/:restType` and
  `POST .../characters/:characterSlug/session/rest/:restType`. Preview is a read-only SQLite
  derivation behind the session-mode character access gate; apply is bearer-token authenticated,
  shared-revision checked, and returns the refreshed `character.state_record` payload. The slice
  normalizes `short`/`long`, rejects unsupported rest types with Flask-compatible
  `validation_error`, resets modeled DND resources, clears long-rest spell-slot usage, recovers
  long-rest Hit Dice before applying submitted final HP/Hit Dice values, restores Xianxia
  HP/Stance/Jing/Qi/Shen/Yin/Yang while preserving Dao, and keeps missing-character responses on
  the TypeScript `content_character_not_found` JSON convention.
- The first feature-state session write now serves
  `PATCH .../characters/:characterSlug/session/feature-states/:featureKey` for Arcane Armor
  enablement on sheets that actually carry an `Arcane Armor` feature. It preserves the bearer-only
  session-state write gate, shared revision conflicts, unsupported-key validation, non-Armorer
  validation, SQLite-only `state.feature_states.arcane_armor.enabled` writes, and refreshed
  `character.state_record` payloads.
- The Xianxia Dao Immolating definition-backed session pair now serves
  `POST .../characters/:characterSlug/session/xianxia-dao-immolating-use-requests` and
  `POST .../characters/:characterSlug/session/xianxia-dao-immolating-use-records`. The request
  route preserves bearer-only character-session writes for app admins, campaign DMs, and assigned
  players, shared revision conflicts, Xianxia-only validation, current and legacy JSON keys,
  prepared-record defaulting/copying, pending `use_history` definition persistence, YAML
  definition/import writes, and refreshed `character.state_record` payloads. The record route is
  DM/admin-only, requires an approved unused use-history record, spends the fixed 10 Insight,
  marks the one-use fields, appends an advancement-history event, writes definition/import YAML,
  and returns the refreshed character payload.
- The DND equipment-state write now serves
  `PATCH .../characters/:characterSlug/session/equipment/:itemId`. It preserves the bearer-only
  session-state write gate, shared revision conflicts, valid definition-backed inventory row
  validation, inventory-only row rejection, weapon wield-mode normalization and allowed-mode
  validation, attunement support/limit validation, synchronized definition `equipment_catalog` and
  SQLite `state.inventory` persistence, and refreshed `character.state_record` payloads.
- The DND Artificer infusion state write now serves
  `PATCH .../characters/:characterSlug/session/artificer-infusions`. It preserves the bearer-only
  session-state write gate, shared revision conflicts, DND Artificer/Infuse Item eligibility,
  known-infusion validation, active-capacity validation, duplicate active infusion and target
  validation, nonmagical target validation, Enhanced Defense armor/shield validation, synchronized
  definition `equipment_catalog` and SQLite `state.inventory.active_infusions` persistence,
  Enhanced Defense Armor Class/defensive-rule automation across infusion and equipment writes,
  and refreshed `character.state_record` payloads.
- The Character Portrait JSON mutation pair now serves
  `PUT .../characters/:characterSlug/portrait` and
  `DELETE .../characters/:characterSlug/portrait`. It preserves bearer-only session-mode edit
  access for app admins, campaign DMs, and assigned players, shared `character_state`
  revision conflicts, copied-fixture definition/import YAML writes, old-asset cleanup, profile
  field removal, absent-portrait validation, and refreshed `character.state_record` plus compact
  `portrait` payloads. Deliberate TypeScript divergence while Flask remains production authority:
  TS does not add `sharp` or convert portrait uploads; it preserves validated PNG/JPG/GIF/WEBP
  bytes and writes `characters/<characterSlug>/portrait.<ext>`. Existing production Flask/WebP
  behavior and broader vault PNG data migration remain outside this slice and require the normal
  cutover decision path.
- The Character Controls JSON route slice now serves
  `POST .../characters/:characterSlug/controls/assignment`,
  `DELETE .../characters/:characterSlug/controls/assignment`, and
  `DELETE .../characters/:characterSlug/controls`. Assignment and clear are bearer API-token
  app-admin-only, validate active player accounts and active campaign player memberships, write
  `character_assignments`, and record `character_assignment_created` /
  `character_assignment_removed` audit events with `gen2_character_controls` metadata. Checked
  delete is bearer API-token campaign DM/admin-only, reuses content-character deletion for files,
  `character_state`, portrait assets, and assignment cleanup, records `character_deleted` audit
  events, and returns the Flask-compatible delete success message and roster links.
- The Character roster read route now serves `GET .../characters`, preserving Flask-compatible
  campaign existence checks, Characters-scope visibility, assigned-player fallback visibility,
  `q` filtering against roster `search_text`, roster card fields consumed by Gen2, existing
  portrait asset references without image conversion, and create/import link/tool flags.
- The Browser JSON compatibility route slice now serves the four legacy Gen2 browser endpoints
  outside `/api/v1`: `/campaigns/:campaignSlug/global-search`,
  `/campaigns/:campaignSlug/global-search/preview`,
  `/campaigns/:campaignSlug/session/wiki-lookup/search`, and
  `/campaigns/:campaignSlug/session/wiki-lookup/preview`. These Hono handlers preserve the
  Gen2-consumed `results`/`message` and `preview_html` contracts, short-query and empty-preview
  behavior, JSON missing-campaign envelopes, unavailable preview `404` responses, and
  Session-scope/player-visible wiki gating. `browser-json-compatibility-decision.md` records the
  route-level cutover decision and focused fixture proof.
- The Character create route pair now serves `GET .../characters/create` plus Xianxia-lane
  `POST .../characters/create`, preserving
  Flask-compatible campaign existence checks, authoring auth/permission failures, unsupported-system
  errors, route-lane links/tools, DND-5E Gen2 payload shape with builder-ready enabled Systems
  class/species/background/subclass options, sanitized selected values, ability-score fields, preview
  basics, and explicit support-limit notes, and Xianxia create fields/defaults plus enabled
  martial-art and Generic Technique options. The POST lane writes native Xianxia records through the copied fixture
  content-character persistence path with `builder://xianxia-create` import metadata, and now also
  writes a bounded DND-5E PHB Fighter, PHB Barbarian, or PHB Cleric / Human / Soldier level-one slice through the same persistence path with
  `builder://dnd5e-create-level-one` metadata, initialized SQLite mutable state, duplicate-slug
  `character_exists` handling, and validation errors for out-of-slice DND selections. The Cleric slice requires the PHB Life Domain,
  writes prepared cantrip/spell selections plus Life Domain always-prepared spells, and seeds first-level spell slots in SQLite.
  Full DND level-one builder write parity, broader species/background choices, broader spellcasting classes, and broader level-one subclass choices remain pending.
- The Character detail read route now serves `GET .../characters/:characterSlug`, preserving
  Flask-compatible campaign/missing-character envelopes, Characters-scope or assigned-owner
  Session-scope access, SQLite `state_record` reads, CharacterPane-safe optional presentation
  shells, permissions, controls metadata, protected portrait URLs from existing asset references,
  and Flask/Gen2 detail links. Full Flask presenter derivation remains outside this detail-read
  slice.
- The Character Advanced Editor context route now serves `GET .../characters/:characterSlug/advanced-editor`,
  preserving Flask-compatible campaign/missing-character envelopes, auth and assigned-owner access
  checks, DND-5E support detection, unsupported non-DND payloads, edit-page links, state revision,
  reference fields, proficiency fields, stat-adjustment fields, recoverable-penalty rows, feature/equipment row shells,
  and hydrated linked campaign-page selector options for custom features and manual equipment.
  The `PUT .../advanced-editor` reference/proficiency/stat-adjustment/recoverable-penalty/custom-feature/manual-equipment-field slice now serves
  bearer-token writes for the existing reference, proficiency, stat-adjustment, recoverable-penalty, custom-feature, and manual-equipment fields with `page_ref` validation and round-trip,
  preserving fixture-role write denial, unsupported non-DND validation, stale revision conflicts, copied-fixture
  `definition.yaml` and managed `import.yaml` writes for profile/reference notes/proficiencies/stat adjustments/recoverable penalties/custom features/manual equipment,
  SQLite notes persistence for state-backed reference fields, current-HP clamping for lowered max HP, SQLite inventory
  reconciliation for manual equipment rows, SQLite resource reconciliation for custom-feature trackers,
  and refreshed Advanced Editor payloads. Linked custom-feature page defaults, fresh `campaign_option`
  storage, campaign feat `optionalfeature_progression` choice fields, and linked additional-spell choice fields
  now cover the Harbor Drill-style linked feature slices, including generated child feature rows with native
  edit parent/position metadata. Manual item option derivation from linked manual pages is implemented. Spell
  support/manager replacement derivation, full native edit derivation, and complete Advanced Editor parity remain pending.
- The Character retraining route now serves the first DND-5E advancement save-parity slice. `GET .../characters/:characterSlug/retraining`
  preserves Flask-compatible campaign/missing-character envelopes, auth and route-specific access failures,
  current fixture empty-readiness shells, Advanced Editor/detail links, and ready-state linked custom-feature
  contexts for persisted structured choices such as Optional Feature swaps. `POST .../retraining` preserves
  unsupported empty-shell responses, validates ready-state retraining choices, reuses the Advanced Editor
  derivation and state-reconciliation path, writes copied-fixture `definition.yaml` / managed `import.yaml`,
  bumps SQLite state revisions, records `source.native_progression.history` retrain events when the definition
  changes, and returns refreshed retraining payloads. The Character Level Up route now has the first bounded
  DND-5E level-up save-parity slice for sheets created by the TypeScript DND level-one builder: `GET .../level-up`
  hydrates a ready level-1 to level-2 context for the supported Fighter/Barbarian slice, while
  `POST .../level-up` validates HP Gain, writes copied-fixture `definition.yaml` / managed `import.yaml`,
  bumps SQLite state revisions, reconciles HP, Hit Dice, and derived resources, records
  `source.native_progression.hp_baseline` plus `level_up` history, and returns refreshed level-up payloads.
  Multiclassing, subclass choices, ASI/feat choices, spell growth, imported-sheet repair, and broader native
  level-up parity remain pending. The Character Progression Repair route now has the first bounded imported-sheet
  fixture save slice: `GET .../progression-repair` hydrates a repairable context for imported DND-5E sheets that
  are missing durable class/subclass/species/background refs, and `POST .../progression-repair` validates those
  selections, writes copied-fixture `definition.yaml` / managed `import.yaml`, bumps the SQLite state revision,
  records `source.native_progression.baseline_repaired_at` plus `repair` history, and returns either a refreshed
  repair payload or a Level Up handoff when the sheet becomes ready. Legacy spell-mark repair, feat/optional-feature
  repair backfills, and broader imported progression repair parity remain pending.
- The first Character Cultivation write slices now serve
  `POST .../characters/:characterSlug/cultivation` for the `save_insight`, `record_gathering_insight`,
  `spend_cultivation_energy`, `spend_meditation_yin_yang`, `spend_conditioning`,
  `spend_training`, `advance_martial_art_rank`, `learn_generic_technique`,
  `start_realm_ascension_review`, `reset_realm_ascension_stats`,
  `apply_immortal_realm_rebuild`, `apply_divine_realm_rebuild`, and
  `confirm_realm_ascension` actions. They preserve
  bearer-token DM/admin management access, Xianxia-only validation, shared revision conflicts,
  flat or nested JSON value parsing, non-negative whole-number Insight available/spent validation,
  positive whole-number Gathering Insight validation, Cultivation Energy key and available-Insight
  validation, Meditation Yin/Yang key and available-Insight validation,
  Conditioning HP/Effort target validation, Training Stance/Attribute target validation,
  Martial Art selection/rank/structured metadata/Insight validation,
  Generic Technique selection/catalog/direct-spend/duplicate/Insight validation,
  Realm Ascension target/prerequisite/review-note/reset/rebuild/final-confirmation sequencing validation,
  available-Insight validation, HP and Stance maximum cap validation,
  copied-fixture `definition.yaml` writes, SQLite state revision bumps and Xianxia state
  reconciliation without refilling current HP/Stance/Energy/Yin-Yang pools, `insight_counter_adjustment`,
  `gathering_insight`, `cultivation_energy_increase`, `meditation_yin_yang_increase`,
  `conditioning_hp_increase`, `conditioning_effort_increase`, `training_stance_increase`,
  `training_attribute_increase`, `martial_art_rank_advance`, `generic_technique_learned`,
  `realm_ascension_review_started`, `realm_ascension_attributes_efforts_reset`,
  `realm_ascension_immortal_rebuild_applied`, `realm_ascension_divine_rebuild_applied`,
  and `realm_ascension_gm_confirmation_recorded` history rows, and refreshed Cultivation payloads.
- The first Xianxia inventory equipment write now serves
  `PATCH .../characters/:characterSlug/session/xianxia-inventory/:itemId/equipped`. It preserves the
  bearer-only session-state write gate, shared revision conflicts, Xianxia-only validation, unknown
  and non-equippable item validation, SQLite `state.xianxia.inventory.quantities` equipped-state
  writes, synchronized top-level `state.inventory` mirrors, and refreshed `character.state_record`
  payloads.
- The Xianxia inventory add write now serves
  `POST .../characters/:characterSlug/session/xianxia-inventory`. It preserves the bearer-only
  session-state write gate, shared revision conflicts, Xianxia-only validation, Flask-style wrapped
  or flat item payload extraction, missing-name/catalog and duplicate-id validation, generated item
  IDs, non-equippable equipped-item validation, SQLite `state.xianxia.inventory.quantities`
  insertion, synchronized top-level `state.inventory` mirrors, and refreshed
  `character.state_record` payloads.
- The Xianxia inventory remove write now serves
  `DELETE .../characters/:characterSlug/session/xianxia-inventory/:itemId`. It preserves the
  bearer-only session-state write gate, shared revision conflicts, Xianxia-only validation,
  unknown-item validation, SQLite `state.xianxia.inventory.quantities` removal, synchronized
  top-level `state.inventory` mirrors, and refreshed `character.state_record` payloads.
- The Xianxia inventory item update write now serves
  `PATCH .../characters/:characterSlug/session/xianxia-inventory/:itemId`. It preserves the
  bearer-only session-state write gate, shared revision conflicts, Xianxia-only validation,
  Flask-style wrapped or flat item payload extraction, unknown-item validation, merged item field
  updates with canonical type/nature/equippable normalization, SQLite
  `state.xianxia.inventory.quantities` persistence, synchronized top-level `state.inventory`
  mirrors, and refreshed `character.state_record` payloads.
- Read-only auth/permission metadata for the fixture mode is explicit in the response.
- `apps/api/src/routes.ts` is the implemented-route manifest for the tracked slice.
- `apps/api/tests/route-parity.mjs` checks implemented TypeScript routes against the Python route snapshot and active route seed.

Production cutover is not part of the early phases. It requires backup, migration dry-run, browser rehearsal, production smoke checks, and an approved rollback window.
