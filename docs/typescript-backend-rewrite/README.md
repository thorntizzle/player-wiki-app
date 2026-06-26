# TypeScript Backend Rewrite

Last updated: 2026-06-26

Status: active rewrite planning and implementation track

This folder tracks the deliberate TypeScript backend rewrite path for Campaign Player Wiki. It is separate from incremental Flask refactor work. The goal is a production-capable TypeScript backend that preserves the current product contract, data safety boundaries, local/Fly operations, and rollback path before replacing Flask.

## Source Of Truth

- `charter.md`: scope, freeze rules, cutover gates, rollback requirement, and branch/spec ownership.
- `parity-inventory.md`: current route, API, data, command, and policy inventory that TypeScript must preserve.
- `route-snapshots.md`: executable route snapshot artifact companion review notes.
- `route-snapshots.json`: tracked executable snapshot from
  `scripts/route_snapshots.py` used by parity checks.
- `typescript-route-seed.json`: provisional route seed for initial TypeScript handlers.
- `content-character-staging-readiness.md`: content-character write/delete rollback evidence and staging-readiness decision.
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: local active task queue for the rewrite track.
- `docs/current-state/INDEX.md`: current product contract index. Use it to confirm present behavior before porting any workflow.
- `docs/api-v1.md`: current JSON API contract.

Route parity check command:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

### Stack Evidence

- `stack-spike.md`: architecture decision record for the TypeScript backend stack evaluation and proof checklist.
- `sqlite-migration-spike.md`: migration-layer proof for Drizzle `generate`/`migrate`, runtime probes, and driver comparison.
- `read-only-compatibility-slice.md`: evidence for the fixture-backed compatibility API slice, including the first controlled SQLite write route validated against a disposable fixture database.

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
  - `GET /api/v1/systems/import-runs`
  - `GET /api/v1/systems/import-runs/:importRunId`
  - `GET /api/v1/campaigns/:campaignSlug/systems`
  - `GET /api/v1/campaigns/:campaignSlug/systems/search`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId`
  - `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId/types/:entryType`
  - `GET /api/v1/campaigns/:campaignSlug/systems/entries/:entrySlug`
  - `GET /api/v1/campaigns/:campaignSlug/combat`
  - `GET /api/v1/campaigns/:campaignSlug/combat/live-state`
  - `GET /api/v1/campaigns/:campaignSlug/combat/systems-monsters/search`
  - `GET /api/v1/campaigns`
  - `GET /api/v1/campaigns/:campaignSlug`
  - `GET /api/v1/campaigns/:campaignSlug/control`
  - `PATCH /api/v1/campaigns/:campaignSlug/control/visibility`
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
  - `GET /api/v1/campaigns/:campaignSlug/content/characters`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `PUT /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
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
- The first Combat state shell now serves read-only empty tracker payloads for `GET .../combat` and
  `GET .../combat/live-state`, preserving Flask-compatible unauthenticated `auth_required`, fixture
  or bearer-token membership-derived player/DM permission splits, live polling metadata,
  invalid/no-membership bearer auth envelopes, and unchanged-response short-circuit behavior.
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
  admin View As choices from `CPW_DB_PATH` when a bearer token is supplied.
- The account settings slice now serves `GET /api/v1/me/settings` and
  `PATCH /api/v1/me/settings`, preserving Flask-compatible unauthenticated `auth_required`
  behavior, the current theme preset and live-session chat-order choice metadata, fixture-role
  reads, bearer-token user/preference reads, bearer-token `user_preferences` writes, validation
  for theme/chat-order choices, retired `frontend_mode` rejection, and refreshed preference payloads.
  Bearer API-token identity reads now update `api_tokens.last_used_at` when the stored timestamp is
  older than the configured session-touch interval.
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
- Read-only auth/permission metadata for the fixture mode is explicit in the response.
- `apps/api/src/routes.ts` is the implemented-route manifest for the tracked slice.
- `apps/api/tests/route-parity.mjs` checks implemented TypeScript routes against the Python route snapshot and active route seed.

Production cutover is not part of the early phases. It requires backup, migration dry-run, browser rehearsal, production smoke checks, and an approved rollback window.
