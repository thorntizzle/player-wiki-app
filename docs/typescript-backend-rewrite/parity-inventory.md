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
- `docs/typescript-backend-rewrite/charter.md`
- `frontend/src/api/client.ts`
- `frontend/src/components/SessionArticleDisplay.tsx`
- `player_wiki/api.py`
- `player_wiki/app.py`
- `manage.py`
- `ops.py`
- `local.ps1`
- `Dockerfile`
- `.dockerignore`
- `fly.toml`
- `deploy/fly-entrypoint.sh`
- `player_wiki/db.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/campaign_session_service.py`
- `player_wiki/campaign_session_store.py`
- `player_wiki/repository_store.py`
- `player_wiki/repository.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/character_repository.py`
- `player_wiki/system_policy.py`
- `player_wiki/auth.py`
- `player_wiki/campaign_visibility.py`
- `tests/test_api.py`

## Inventory hardening summary

Generated evidence from the current source shows:

- `player_wiki/api.py` declares 135 `/api/v1` routes: 46 `GET`, 39 `POST`, 21 `PATCH`, 11 `PUT`, and 18 `DELETE`.
- `player_wiki/app.py` declares 138 Flask browser/compatibility routes: 49 `GET`, 82 `POST`, and 7 `GET,POST` dual-method form routes.
- `player_wiki/db.py` currently creates 34 unique SQLite tables. The repeated `CREATE TABLE IF NOT EXISTS` blocks for `campaign_session_states`, `campaign_combatant_resource_counters`, and `campaign_combatant_resource_notes` are additive/migration guards, not separate domains.
- `frontend/src/api/client.ts` is the main Gen2 client. It calls `/api/v1` plus a small set of Flask browser JSON compatibility routes for global search and session wiki lookup.
- `frontend/src/components/SessionArticleDisplay.tsx` also builds the `/api/v1/campaigns/<slug>/session/articles/<id>/image` URL directly.
- No current evidence showed frontend calls to undocumented `/api/v1` endpoints outside `CampaignApiClient` and the session-article image helper. The intentionally compatibility-only non-API JSON routes are listed under Browser JSON compatibility endpoints used by Gen2.

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
  - `/characters/<character_slug>/advanced-editor`
  - `/characters/<character_slug>/retraining`
  - `/characters/<character_slug>/level-up`
  - `/characters/<character_slug>/progression-repair`
  - `/characters/<character_slug>/cultivation`
  - `/characters/<character_slug>`
  - `/characters/<character_slug>/controls/assignment*`
  - `/characters/<character_slug>/controls`
  - `/characters/<character_slug>/portrait`
  - `/characters/<character_slug>/rest-preview/<rest_type>`
  - `/characters/<character_slug>/sheet-edit`
  - `/characters/<character_slug>/session/vitals`
  - `/characters/<character_slug>/session/resources/<resource_id>`
  - `/characters/<character_slug>/session/spell-slots/<level>`
  - `/characters/<character_slug>/session/inventory/<item_id>`
  - `/characters/<character_slug>/session/equipment/<item_id>`
  - `/characters/<character_slug>/session/artificer-infusions`
  - `/characters/<character_slug>/session/feature-states/<feature_key>`
  - `/characters/<character_slug>/session/xianxia-active-state`
  - `/characters/<character_slug>/session/xianxia-dao-immolating-use-requests`
  - `/characters/<character_slug>/session/xianxia-dao-immolating-use-records`
  - `/characters/<character_slug>/session/xianxia-inventory*`
  - `/characters/<character_slug>/session/currency`
  - `/characters/<character_slug>/session/notes`
  - `/characters/<character_slug>/session/personal`
  - `/characters/<character_slug>/session/rest/<rest_type>`
- Cutover classification: **initial cutover**
- Evidence source:
  - `player_wiki/api.py:3297`, `3319`, `3691`, `3707`, `3971`, `3999`, `4241`, `4270`, `4679`, `4688`
  - `player_wiki/api.py:8650`, `8689`, `8696`, `8780`, `8802`, `8872`, `8918`, `8969`, `9011`, `9066`, `9119`, `9166`, `9382`, `9409`, `9436`, `9452`, `9469`, `9570`, `9585`, `9615`, `9649`, `9663`, `9678`, `9692`, `9707`, `9723`, `9741`, `9756`, `9782`, `9796`, `9812`
  - `docs/current-state/characters-overview.md`
  - `docs/current-state/characters-dnd5e.md`
  - `docs/current-state/characters-xianxia.md`
  - `player_wiki/system_policy.py`
  - `docs/api-v1.md` character section
  - `frontend/src/api/client.ts`
  - `tests/test_api.py`

Note: the `docs/api-v1.md` core endpoint list is missing a few character routes that are implemented and exercised by Gen2/tests, including `advanced-editor`, `retraining`, `level-up`, `progression-repair`, `cultivation`, `characters/create`, `characters/import/xianxia-manual`, `session/personal`, and `session/artificer-infusions`. The TypeScript rewrite should treat source route declarations plus `frontend/src/api/client.ts` and `tests/test_api.py` as stronger evidence until the API reference is refreshed.

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

- Browser JSON compatibility endpoints used by Gen2
  - `/campaigns/<campaign_slug>/global-search`
  - `/campaigns/<campaign_slug>/global-search/preview`
  - `/campaigns/<campaign_slug>/session/wiki-lookup/search`
  - `/campaigns/<campaign_slug>/session/wiki-lookup/preview`
  - Cutover classification: **initial cutover** unless equivalent `/api/v1` replacements are built and the frontend client is moved first
  - Source: `frontend/src/api/client.ts:438`, `446`, `1022`, `1028`; `player_wiki/app.py:9289`, `9313`, `12188`, `12220`
  - Notes: these are not under `/api/v1`, but the current Gen2 API client consumes them with `requestBrowserJson`. They must either remain supported as compatibility routes or be replaced by explicit API contract routes before Gen2 cutover.

- Asset and player wiki compatibility pages
  - `/campaigns/<campaign_slug>/assets/<path:asset_path>`
  - `/campaigns/<campaign_slug>/session-article-images/<article_id>`
  - `/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
  - `/campaigns/<campaign_slug>/sections/<section_slug>`
  - `/campaigns/<campaign_slug>/pages/<path:page_slug>`
  - Cutover classification: **legacy compatibility**
  - Source: `player_wiki/app.py:9349`, `9367`, `9405`, `12258`, `14500`
  - Notes: protected binary routes need byte/media-type parity or explicit client migration.

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
  - No route family is marked `can retire` yet in this phase. Many Flask `POST` routes duplicate JSON API behavior, but they also preserve fallback forms, direct browser navigation, and rollback capacity while Flask remains the production authority.
  - Candidate retire groups after TypeScript replacement and Gen2 migration: Systems control-panel forms, DM Content browser mutation forms, Combat browser mutation forms, Session browser mutation forms, Character spellcasting/equipment/session mutation forms, and character create/edit/advancement form routes. Each candidate needs a route-level deprecation decision before removal.

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

### 3.1 Local and deployment behavior to preserve

- `local.ps1` must keep the action contract `install`, `bootstrap`, `run`, `test`, `check`, `backup`, `restore`, `prepare-fly-campaigns`, `sync-fly`, and `deploy-fly`.
- The wrapper must continue to route disposable temp files into `.local/tmp/<action>/` rather than repo-root scratch folders.
- `restore` remains destructive and guarded by `-ForceRestore`; `sync-fly` remains destructive and guarded by `-ForceSyncFromFly`.
- The Fly app name must stay local, supplied through `-FlyApp`, process/user `PLAYER_WIKI_FLY_APP`, or an explicit Fly command. The tracked `fly.toml` remains sanitized and is not the live app source of truth.
- The wrapper and `ops.py` currently fall back to the saved user-scoped Fly login by injecting `FLY_ACCESS_TOKEN` for child processes when the current shell lacks it.
- `deploy-fly` ships the current working-tree snapshot, so a clean-commit or temporary clean-export workflow is required whenever live deploys must match committed state exactly.
- The Fly image builds the Gen2 frontend in Docker and excludes local `.local/`, SQLite files, ignored `frontend/dist`, tests, and scratch folders through `.dockerignore`.
- `deploy/fly-entrypoint.sh` owns mounted-volume schema initialization through `manage.py init-db`; TypeScript deployment must preserve startup schema/migration behavior against `/data/player_wiki.sqlite3`.
- Current Fly production shape remains one app, one `/data` volume, SQLite at `/data/player_wiki.sqlite3`, campaign content at `/data/campaigns`, and `/healthz` as the operational probe.
- Evidence source: `local.ps1`, `ops.py`, `docs/current-state/ops-deploy.md`, `docs/roadmap-automation-reference.md`, `Dockerfile`, `.dockerignore`, `fly.toml`, `deploy/fly-entrypoint.sh`, and the ops-deploy skill references.

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
- Count: 34 unique current tables. Compatibility readers should model the unique table set and also preserve migration behavior for additive `ALTER TABLE`, WAL/busy-timeout pragmas, and index creation.

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

### 4.3 Asset and image parity notes

- Campaign asset API reads return `data_base64`; asset writes accept embedded `asset_file` with `filename` and `data_base64`.
- Campaign asset media-type resolution uses `mimetypes.guess_type` plus explicit extension fallbacks, including `.webp -> image/webp`; unknown extensions fall back to `application/octet-stream`.
- Protected campaign asset serving uses `send_from_directory(..., mimetype=guess_campaign_asset_media_type(...))`, so TypeScript must preserve WebP content type even when the host MIME table lacks it.
- Session article images are SQLite-backed rows in `campaign_session_article_images` with `filename`, `media_type`, `data`, `alt_text`, and `caption`; API and Flask routes stream the stored bytes using the stored `media_type`.
- Session article image uploads accept JSON/file payloads with filename/media type/data, normalize media type from allowed extensions, and keep alt/caption updates separate from image replacement.
- Browser Player Wiki publication converts PNG/JPG page images and session article image copies to WebP quality 82 through `player_wiki/image_publish.py`; GIF and WebP pass through. The Gen2 content asset API preserves the selected file extension.
- Character portrait writes store campaign-owned protected assets and delete replaced assets; portrait updates and removals are revision-guarded and must preserve stale-write `409 state_conflict` behavior.
- Cutover classification: **initial cutover** for byte/media-type reads and protected serving; **before production** for image conversion parity unless publication flows are deliberately moved to extension-preserving APIs first.
- Evidence source: `player_wiki/campaign_content_service.py`, `player_wiki/campaign_session_service.py`, `player_wiki/campaign_session_store.py`, `player_wiki/image_publish.py`, `player_wiki/app.py`, `player_wiki/api.py`, and `docs/api-v1.md`.

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

## 6) Error and response contract families

The rewrite should preserve the current API error envelope unless an explicit API version break is approved:

```json
{
  "ok": false,
  "error": {
    "code": "<machine_code>",
    "message": "<human_message>",
    "details": {}
  }
}
```

- `details` is optional and appears only when supplied by `json_error`.
- `401 auth_required`: unauthenticated API/browser-session requests and revoked/missing bearer-token reads.
- `403 forbidden`: insufficient admin, scope, campaign, DM Content, Systems, Session, Combat, or character permissions.
- `403 view_as_read_only`: admin View As mode blocks non-safe `/api/...` writes before route handlers run.
- `400 validation_error`: most invalid form/body/domain validation failures.
- `400 invalid_json`: selected JSON mutation endpoints where the request body is malformed or not an object.
- `409 state_conflict`: stale character sheet, combatant, portrait, resource, equipment, cultivation, and similar revision-guard failures.
- `409 hard_delete_blocked`: unsafe Player Wiki hard delete without force.
- `409 character_exists`: duplicate character create/import slug collisions.
- `404 not_found`: a few explicit JSON paths, such as already-deleted character controls. Many missing-resource API branches still call `abort(404)`, which currently routes through Flask's generic 404 handler and may not return JSON. Parity tests should capture whether each cutover-critical missing-resource response is JSON or generic 404 before changing wire behavior.
- `500 server_error`: currently used for Campaign Help context build failure.
- No current evidence shows deliberate `422` responses in the API contract; validation is currently `400`.
- Evidence source: `player_wiki/api.py:264`, `player_wiki/auth.py:118`, `tests/test_api.py`, and `frontend/src/api/client.ts`.

## 7) Remaining follow-ups for stronger later evidence

These items need explicit follow-up passes before the next migration milestone:

- Refresh `docs/api-v1.md` so its core endpoint list includes the implemented Gen2 character create/import/edit/advancement and session-state endpoints now documented by source/tests.
- Convert the route-family inventory into generated route snapshots for parity tests before adding TypeScript handlers.
- Capture route-by-route missing-resource 404 shapes for cutover-critical API paths, because source currently mixes JSON `not_found` with `abort(404)`.
- Decide whether Flask browser form routes remain long-term compatibility routes, temporary rollback-only routes, or can be retired after TypeScript/Gen2 cutover.
- Capture exact image conversion parity for Browser Player Wiki publication if TypeScript replaces that browser flow rather than routing all publication through the extension-preserving content asset API.
