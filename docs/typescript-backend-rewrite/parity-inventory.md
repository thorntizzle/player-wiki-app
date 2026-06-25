# TypeScript Backend Rewrite - Phase 1 Parity Inventory

Last updated: 2026-06-25

This is a compatibility inventory only. It records what is currently observable in the
Flask implementation and should be preserved by the TypeScript backend during phased
migration. It is not a claim that parity is complete.

## Source evidence used

- `docs/current-state/INDEX.md`
- `docs/current-state/admin-auth.md`
- `docs/current-state/characters-overview.md`
- `docs/current-state/published-wiki.md`
- `docs/current-state/live-session.md`
- `docs/current-state/combat.md`
- `docs/current-state/systems.md`
- `docs/current-state/ops-deploy.md`
- `docs/current-state/frontend-gen2.md`
- `docs/api-v1.md`
- `player_wiki/api.py`
- `player_wiki/app.py`
- `manage.py`
- `ops.py`
- `local.ps1`
- `player_wiki/db.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/repository_store.py`
- `player_wiki/repository.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/character_repository.py`
- `player_wiki/system_policy.py`
- `player_wiki/auth.py`
- `player_wiki/campaign_visibility.py`

## 1) API endpoint families

Family names are grouped by behavior and route prefix. Evidence is from route decorators in
`player_wiki/api.py`, endpoint inventory in `docs/api-v1.md`, and shared behavior notes in
`player_wiki/app.py` + `docs` current-state files.

### 1.1 Authentication and account core
- Routes:
  - `/api/v1/me`
  - `/api/v1/me/view-as`
  - `/api/v1/me/settings`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:5230` (`/me` routes)
  - `docs/api-v1.md` account section
  - `player_wiki/auth.py` permissions/context helpers (`get_current_user`, `get_view_as_user`, `can_access_*`)
  - `docs/current-state/admin-auth.md`

### 1.2 App and import-run metadata
- Routes:
  - `/api/v1/app`
  - `/api/v1/systems/import-runs`
  - `/api/v1/systems/import-runs/<import_run_id>`
  - `/api/v1/systems/imports/dnd5e`
- Cutover classification: **before production**
- Evidence source:
  - `player_wiki/api.py:5829`, `5833`, `5857`, `5866`
  - `docs/api-v1.md` system import section
  - `player_wiki/systems_importer.py` and `systems_service` call sites via API handlers

### 1.3 Admin management
- Routes:
  - `/api/v1/admin`
  - `/api/v1/admin/users/<user_id>`
  - `/api/v1/admin/users/invite`
  - membership and assignment routes under `/api/v1/admin/users/...`
  - `/api/v1/admin/users/<user_id>/disable`, `/enable`, `/password-reset`, `/invite`, `/assignment`, `/membership`, `/remove` etc.
- Cutover classification: **before production**
- Evidence source:
  - `player_wiki/api.py:5384` onward
  - `docs/api-v1.md` admin section
  - `player_wiki/auth.py` and `player_wiki/admin_context.py` for permission scoping

### 1.4 Campaign shell and visibility control
- Routes:
  - `/api/v1/campaigns`
  - `/api/v1/campaigns/<campaign_slug>`
  - `/api/v1/campaigns/<campaign_slug>/control`
  - `/api/v1/campaigns/<campaign_slug>/control/visibility`
  - `/api/v1/campaigns/<campaign_slug>/help`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:5935`, `5945`, `5970`, `6009`, `6092`
  - `player_wiki/campaign_visibility.py`
  - `docs/current-state/admin-auth.md`
  - `docs/api-v1.md` control/help entries

### 1.5 Published wiki read APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/wiki`
  - `/api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug>`
  - `/api/v1/campaigns/<campaign_slug>/wiki/pages/<path:page_slug>`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:6092`, `6152`, `6245`, `6296`
  - `docs/current-state/published-wiki.md`
  - `docs/api-v1.md` wiki read coverage

### 1.6 Campaign file-backed content management
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/content/config`
  - `/api/v1/campaigns/<campaign_slug>/content/assets*`
  - `/api/v1/campaigns/<campaign_slug>/content/pages*`
  - `/api/v1/campaigns/<campaign_slug>/content/characters*`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:6353`, `6363`, `6381`, `6414`, `6458`, `6488`
  - `player_wiki/campaign_content_service.py`
  - `player_wiki/db.py` includes `campaign_sessions`, `campaign_pages`, `campaign_system_*` tables used by content services
  - `docs/current-state/published-wiki.md`

### 1.7 Session runtime APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/session`
  - `/api/v1/campaigns/<campaign_slug>/session/logs`
  - `/api/v1/campaigns/<campaign_slug>/session/start`, `/close`, `/messages`
  - `/api/v1/campaigns/<campaign_slug>/session/articles` create/update/reveal/delete
  - `/api/v1/campaigns/<campaign_slug>/session/articles/revealed`
  - `/api/v1/campaigns/<campaign_slug>/session/article-sources/search`
  - `/api/v1/campaigns/<campaign_slug>/session/articles/<id>/image`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:7110`, `7134`, `7163`, `7187`, `7208`, `7229`, `7259`, `7273`, `7308`, `7491`, `7560`, `7600`, `7614`, `7641`
  - `docs/current-state/live-session.md`
  - `docs/api-v1.md` session section including revision headers

### 1.8 DM Content APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/dm-content`
  - `/api/v1/campaigns/<campaign_slug>/dm-content/systems`
  - `/api/v1/campaigns/<campaign_slug>/dm-content/statblocks`
  - `/api/v1/campaigns/<campaign_slug>/dm-content/conditions`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:7641`, `7646`, `7658`, `7687`, `7734`, `7751`, `7779`
  - `docs/current-state/dm-content.md`
  - `player_wiki/campaign_dm_content_service.py`

### 1.9 Systems APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/systems`
  - `/systems/search`
  - `/systems/sources`, `/systems/sources/<source_id>`, `/systems/sources/<source_id>/types/<entry_type>`
  - `/systems/entries/<entry_slug>`
  - `/systems/overrides/<entry_key>`
  - `/systems/custom-entries*`
  - `/systems/item-mechanics/import`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:6719`, `6720`, `6736`, `6760`, `6809`, `6931`, `7010`, `7057`, `7836`, `7890`, `7939`, `7993`, `8032`
  - `docs/current-state/systems.md`
  - `docs/api-v1.md` systems section
  - `player_wiki/systems_service.py`, `player_wiki/systems_store.py`

### 1.10 Combat APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/combat`
  - `/combat/live-state`
  - `/combat/systems-monsters/search`
  - `/combat/player-combatants`, `/combat/npc-combatants`, `/combat/statblock-combatants`
  - `/combat/advance-turn`, `/combat/clear`
  - combatant mutation routes for turn/vitals/resources/conditions/delete and player detail endpoints
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:8071`, `8089`, `8107`, `8171`, `8197`, `8229`, `8281`, `8333`, `8355`, `8377`, `8400`, `8438`, `8500`, `8549`, `8594`, `8620`, `8635`, `8650`
  - `docs/current-state/combat.md`
  - `docs/api-v1.md` combat section

### 1.11 Character APIs
- Routes:
  - `/api/v1/campaigns/<campaign_slug>/characters`
  - `/characters/create`
  - `/characters/import/xianxia-manual`
  - `/characters/<character_slug>`
  - `/characters/<character_slug>/controls/assignment*`
  - `/characters/<character_slug>/portrait`
  - `/characters/<character_slug>/rest-preview/<rest_type>`
  - `/characters/<character_slug>/sheet-edit`
  - `/characters/<character_slug>/session/*` and session resource/equipment/dao-immolating/inventory routes
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:8650`, `8696`, `8780`, `8802`, `8872`, `8918`, `8969`, `9011`, `9066`, `9119`, `9166`, `9382`, `9409`, `9436`, `9469`, `9570`, `9615`, `9649`, `9663`, `9678`, `9707`, `9723`, `9741`, `9756`, `9782`, `9796`
  - `docs/current-state/characters-overview.md`
  - `docs/current-state/characters-dnd5e.md`
  - `docs/current-state/characters-xianxia.md`
  - `player_wiki/system_policy.py`
  - `docs/api-v1.md` character section

## 2) Flask/browser compatibility route families

These are Flask-side routes still required for existing links, direct browser navigation, or migration fallback.

- `/app-next` and app asset fallback
  - `/app-next`, `/app-next/`, `/app-next/<path:asset_path>`
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:1432`, `player_wiki/app.py` app host helpers, `docs/current-state/frontend-gen2.md`, `docs/api-v1.md`

- Campaign home and picker fallback
  - `/`, `/campaigns/<campaign_slug>`
  - `/campaigns/<campaign_slug>/global-search`
  - `/campaigns/<campaign_slug>/global-search/preview`
  - `/campaigns/<campaign_slug>/help`
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:9209`, `9289`, `9313`, `9343`

- Asset and player wiki compatibility pages
  - `/campaigns/<campaign_slug>/assets/<path:asset_path>`
  - `/campaigns/<campaign_slug>/sections/<section_slug>`
  - `/campaigns/<campaign_slug>/pages/<path:page_slug>`
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:9349`, `9367`, `9405`

- Campaign control and systems legacy forms
  - `/campaigns/<campaign_slug>/control-panel`
  - `/campaigns/<campaign_slug>/systems` and related post endpoints under `/systems/control-panel*`
  - `/campaigns/<campaign_slug>/systems/sources/*`, `/systems/entries/*`
  - `/campaigns/<campaign_slug>/systems/control-panel/custom-entries*`, `/shared-entries*`, `/imports/dnd5e`
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:9442` through `10183`
  - Notes: These are currently browser form routes feeding the same service layer as API writes.

- Campaign DM Content legacy forms
  - `/campaigns/<campaign_slug>/dm-content` and subroutes for player-wiki, staged-articles, statblocks, conditions
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:10312` through `10980`

- Legacy combat and session routes
  - `/campaigns/<campaign_slug>/combat`, `/combat/dm`, `/combat/status`, `/combat/character` and all `POST` forms on those pages
  - `/campaigns/<campaign_slug>/session`, `/session/dm`, `/session/character`, `/session/live-state`, plus form endpoints for start/close/messages/articles
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:11002` through `12630`

- Legacy character forms and mutation routes
  - `/campaigns/<campaign_slug>/characters`, `/characters/new`, `/characters/import/xianxia-manual`, `/characters/<slug>/level-up`, `/cultivation`, `/progression-repair`, `/edit`, `/retraining`
  - Assignment, spellcasting, equipment, portrait, session action routes
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:12691` through `15049`

- Operational browser routes
  - `/healthz`
  - Cutover classification: **before production**
  - Source: `player_wiki/app.py:9209`
  - Notes: keep available as a first-stage operational probe independent of API migration.

- Can-retire marker from current evidence:
  - No route family is marked `can retire` yet in this phase because Gen2/route replacement boundaries are still active.

## 3) CLI, admin, and ops commands

- Auth/bootstrap and membership management (`manage.py`)
  - Commands: `init-db`, `create-admin`, `ensure-admin`, `invite-user`, `set-membership`, `assign-character`,
    `disable-user`, `issue-password-reset`, `issue-api-token`, `list-api-tokens`, `revoke-api-token`
  - Cutover classification: **before production**
  - Source:
    - `manage.py` command registration and dispatch (`build_parser`, `if args.command ==` blocks)
    - `player_wiki/auth.py` and `player_wiki/auth_store.py`
  - Notes: Required to bootstrap local parity test environments and validate account-level policy.

- Shared library and campaign-item maintenance (`manage.py`)
  - Commands: `import-dnd5e-source`, `repair-dnd5e-item-metadata`, `import-campaign-item-mechanics`
  - Cutover classification: **before production**
  - Source: `manage.py` command definitions and `player_wiki/systems_importer.py`

- Backup lifecycle and Fly sync/restore tooling (`ops.py`)
  - Commands: `backup`, `restore`, `pull-fly-db`, `prepare-fly-campaigns`, `sync-from-fly`
  - Cutover classification: **migration-only**
  - Source: `ops.py` parser + command handlers
  - Notes: Evidence confirms overwrite-guard flags (`--yes`, `--skip-*`) and backup-before-write behavior.

- Scripted local ops wrapper (`local.ps1`)
  - Actions: `install`, `bootstrap`, `run`, `test`, `check`, `backup`, `restore`, `prepare-fly-campaigns`,
    `sync-fly`, `deploy-fly`
  - Cutover classification:
    - `run`, `test`, `check`, `install` => **legacy compatibility**
    - `bootstrap`/`deploy-fly` and destructive actions => **before production / migration-only**
  - Source: `local.ps1` action switch and wrappers
  - Notes: Evidence includes safety switches `-ForceRestore`, `-ForceSyncFromFly`, `-SkipPreRestoreBackup`, `-SkipPreSyncBackup`.

## 4) SQLite-backed stores and file-backed domains

### 4.1 SQLite-backed domains from schema

- Auth and account: `users`, `user_preferences`, `campaign_memberships`, `campaign_visibility_settings`,
  `character_assignments`, `invite_tokens`, `password_reset_tokens`, `sessions`, `api_tokens`,
  `auth_audit_log`
- Character mutable state: `character_state`
- Session runtime and history: `campaign_sessions`, `campaign_session_states`,
  `campaign_session_articles`, `campaign_session_article_images`, `campaign_session_messages`
- DM Content: `campaign_dm_statblocks`, `campaign_dm_condition_definitions`
- Combat: `campaign_combatants`, `campaign_combat_trackers`, `campaign_combat_conditions`,
  `campaign_combatant_resource_counters`, `campaign_combatant_resource_notes`
- Systems/shared library and policy: `systems_libraries`, `systems_sources`, `systems_import_runs`,
  `systems_entries`, `systems_shared_entry_edit_events`, `systems_entry_links`,
  `campaign_system_policies`, `campaign_enabled_sources`, `campaign_entry_overrides`
- Wiki cache/search-read mirror: `campaign_pages`, `campaign_page_sync_state`
- Cutover classification: all **initial cutover** for TypeScript replacement persistence layer parity
- Source: `player_wiki/db.py` schema declarations and migration guards

### 4.2 File-backed domains

- Campaign config file:
  - `campaigns/<campaign_slug>/campaign.yaml`
- Wiki content files:
  - `campaigns/<campaign_slug>/content/**/*.md` (published and unpublished pages)
- Campaign media:
  - `campaigns/<campaign_slug>/assets/**/*`
  - evidence of specific subpaths through asset write/read functions and session/publishing flows
- Character file bundle:
  - `campaigns/<campaign_slug>/characters/<character_slug>/definition.yaml`
  - `campaigns/<campaign_slug>/characters/<character_slug>/import.yaml`
- Session article artifacts:
  - session article images written into campaign assets during API/browser publish flows
- Character images:
  - character portrait files under campaign character directories and campaign asset area
- Cutover classification: **initial cutover** for read/write parity; path/layout cleanup remains open.
- Source:
  - `player_wiki/campaign_content_service.py`
  - `player_wiki/character_repository.py`
  - `player_wiki/repository.py`
  - `player_wiki/campaign_page_store.py`
  - `docs/api-v1.md`

## 5) Permission and visibility policy families requiring parity tests

- Identity and session:
  - Flask session identity (`get_current_user`) and API token/authorization checks in auth middleware
  - `view_as` state behavior: read-only write guard (`view_as_read_only`)
- Campaign membership + scope access:
  - `can_access_campaign_scope`, `can_access_campaign`, `get_current_memberships`, role mapping from campaign memberships
- Campaign visibility:
  - `CAMPAIGN_VISIBILITY_SCOPES` and per-scope effective visibility merge logic
  - default/public/player/DM/private inheritance across `campaign`, `wiki`, `systems`, `session`, `combat`, `characters`, `dm_content`
- Management scopes:
  - `can_manage_campaign_session`, `can_manage_campaign_combat`, `can_manage_campaign_content`,
    `can_manage_campaign_systems`, `can_manage_campaign_dm_content`, `can_manage_campaign_visibility`
- Character system policy lanes:
  - `supports_character_read_routes`, `supports_character_controls_routes`,
    `supports_combat_tracker`, `supports_native_character_create`, `character_read_lane`,
    and `CHARACTER_ROUTE_LANE_*` plus advancement lane values
- Cutover classification: **initial cutover** for route-level parity and **before production** for
  edge-case restrictions (admin-only imports, destructive writes, visibility-private operations)
- Evidence source: `player_wiki/auth.py`, `player_wiki/campaign_visibility.py`,
  `player_wiki/system_policy.py`, `docs/current-state/admin-auth.md`, `docs/api-v1.md`

## 6) Unknowns / follow-ups for stronger later evidence

These items need explicit follow-up passes before the next migration milestone:

- Confirm whether any browser JS client routes call non-documented endpoints not listed in `docs/api-v1.md`.
- Validate parity for error payload shapes and HTTP status details on conflict cases (`409`, `403`, `401`, `422`) for every major write family.
- Capture a complete list of `local.ps1` and deployment-side dependency behavior (`flyctl` and build metadata flags)
  that must remain stable during TypeScript cutover.
- Confirm whether any remaining `app.py` POST form routes are no longer needed once the
  Gen2 routes are moved off Flask-rendered templates.
- Confirm whether `/campaigns/<slug>/assets/*` and session-article image writes require byte-level equivalence
  (mimetype, conversion behavior, and naming strategy) in the TS replacement.
