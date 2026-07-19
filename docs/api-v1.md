# API v1

`Campaign Player Wiki` now exposes a JSON API under `/api/v1` for the app's mutable content and live campaign operations.

The API also now manages the live file-backed content stored on the campaign volume:

- campaign config updates in `campaigns/<campaign-slug>/campaign.yaml`
- published wiki pages under `campaigns/<campaign-slug>/content/`
- published asset files under `campaigns/<campaign-slug>/assets/`
- character definition/import files under `campaigns/<campaign-slug>/characters/`

## Auth

API access uses bearer tokens tied to existing app users. Tokens inherit the same admin flag, campaign memberships, ownership rules, and visibility checks as the browser UI.

Browser-session app admins can also use `View As`. `GET /api/v1/me` continues to report the real authenticated admin user and includes a `view_as` block with availability, active target, and selectable active users. While active, campaign-facing safe reads under `/api/v1/campaigns...` use the selected user's effective role, memberships, and visibility; campaign API writes are blocked with `403 view_as_read_only` until the admin exits `View As`.

Issue a token:

```powershell
python manage.py issue-api-token dm@example.com live-sync --expires-in-days 365
```

List a user's tokens:

```powershell
python manage.py list-api-tokens dm@example.com
```

Revoke a token:

```powershell
python manage.py revoke-api-token 1
```

Pass the token in the `Authorization` header:

```powershell
$headers = @{
  Authorization = "Bearer <token>"
}
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/me" -Headers $headers
```

## Core Endpoints

This list is checked against Flask's registered `/api/v1` URL map after
normalizing route converters. The generated route/access manifest in
`docs/contracts/route-api-role-visibility-manifest.json` records the owning
domain and access contract for each method/path pair.

- `GET /api/v1/app`
- `GET /api/v1/systems/import-runs`
- `GET /api/v1/systems/import-runs/<import_run_id>`
- `POST /api/v1/systems/imports/dnd5e`
- `GET /api/v1/me`
- `POST /api/v1/me/view-as`
- `DELETE /api/v1/me/view-as`
- `GET /api/v1/me/settings`
- `PATCH /api/v1/me/settings`
- `GET /api/v1/admin`
- `GET /api/v1/admin/users/<user_id>`
- `POST /api/v1/admin/users/invite`
- `POST /api/v1/admin/users/<user_id>/membership`
- `DELETE /api/v1/admin/users/<user_id>/membership`
- `POST /api/v1/admin/users/<user_id>/assignment`
- `DELETE /api/v1/admin/users/<user_id>/assignment`
- `POST /api/v1/admin/users/<user_id>/invite`
- `POST /api/v1/admin/users/<user_id>/password-reset`
- `POST /api/v1/admin/users/<user_id>/disable`
- `POST /api/v1/admin/users/<user_id>/enable`
- `DELETE /api/v1/admin/users/<user_id>`
- `GET /api/v1/campaigns`
- `GET /api/v1/campaigns/<campaign_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/control`
- `PATCH /api/v1/campaigns/<campaign_slug>/control/visibility`
- `GET /api/v1/campaigns/<campaign_slug>/help`
- `GET /api/v1/campaigns/<campaign_slug>/wiki`
- `GET /api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/wiki/pages/<page_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/content/config`
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config`
- `GET /api/v1/campaigns/<campaign_slug>/content/assets`
- `GET /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `GET /api/v1/campaigns/<campaign_slug>/content/pages`
- `GET /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `GET /api/v1/campaigns/<campaign_slug>/content/characters`
- `GET /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/session`
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search`
- `POST /api/v1/campaigns/<campaign_slug>/session/start`
- `POST /api/v1/campaigns/<campaign_slug>/session/close`
- `POST /api/v1/campaigns/<campaign_slug>/session/messages`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles`
- `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/reveal`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed`
- `GET /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `GET /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/image`
- `GET /api/v1/campaigns/<campaign_slug>/dm-content`
- `GET /api/v1/campaigns/<campaign_slug>/dm-content/systems`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/statblocks`
- `PUT /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<statblock_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<statblock_id>`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/conditions`
- `PUT /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<condition_definition_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<condition_definition_id>`
- `GET /api/v1/campaigns/<campaign_slug>/systems`
- `GET /api/v1/campaigns/<campaign_slug>/systems/search`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/sources`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>`
- `GET /api/v1/campaigns/<campaign_slug>/systems/entries/<entry_slug>`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<entry_key>`
- `POST /api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore`
- `GET /api/v1/campaigns/<campaign_slug>/combat`
- `GET /api/v1/campaigns/<campaign_slug>/combat/live-state`
- `GET /api/v1/campaigns/<campaign_slug>/combat/systems-monsters/search`
- `POST /api/v1/campaigns/<campaign_slug>/combat/player-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/npc-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/statblock-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/systems-monsters`
- `POST /api/v1/campaigns/<campaign_slug>/combat/advance-turn`
- `POST /api/v1/campaigns/<campaign_slug>/combat/clear`
- `POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/set-current`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/turn`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/resources`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/npc-resources`
- `POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/conditions`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/conditions/<condition_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>`
- `GET /api/v1/campaigns/<campaign_slug>/characters`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/characters/create`
- `POST /api/v1/campaigns/<campaign_slug>/characters/create`
- `GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `POST /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-infusions`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/item-actions/<action_id>/use`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/personal`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-requests`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-records`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>`

## Transport Ownership

The final Phase 3B ownership inventory in this section is integrated on pushed `main` and deployed as Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. The documentation closeout that records this release is a later docs-only descendant and is not part of that deployed image. `player_wiki/session_api_routes.py` owns all 13 live-session JSON handlers and explicit registrations on the existing API Blueprint. Character API registrar modules own their extracted Character transports, Auth API registrar modules own the extracted `/me` transports, and `admin_api_routes.py` owns 12 Admin API rules on that same Blueprint. `player_wiki/api.py` retains the Blueprint, 35 direct route decorators, shared request/auth/error helpers, serializers, service composition, and registrar dependency wiring. Character `/session/character` and character-session endpoints remain Characters-owned. The low-level `/content/...` APIs remain Publishing-owned; neither family is counted among the 13 live-session API rules.

Across the whole application, the qualified manifest has 299 Flask rules and 308 method/path contracts: 171 browser, 136 API, and one framework-owned static entry. Domain rule/contract ownership is app shell 13/13, Auth 13/15, Admin 30/30, Publishing 20/20, DM Content 25/25, Systems 33/33, Live Session 32/32, Combat 46/46, Characters 86/93, and framework 1/1. Every rule and method/path contract has one owner; transport extraction does not change the documented payload, authorization, visibility, persistence, or error contracts.

## Session Polling

`GET /api/v1/campaigns/<campaign_slug>/session` now participates in session polling:

- Include `X-Live-Revision` and `X-Live-View-Token` request headers for each poll.
- The response always includes `session_revision` and `session_view_token`.
- If both headers match current server values, the endpoint returns:
  - `{"ok": true, "changed": false, "session_revision": <int>, "session_view_token": "<token>"}`.
- If either header differs, the endpoint returns the full `/session` payload with updated revision/token metadata.

## Browser Content Management Coverage

The browser `DM Content` hub now covers the main DM-managed content lanes while still reusing the same app services and JSON API where those are the right write contract:

- `GET /api/v1/campaigns/<campaign_slug>/dm-content` returns `subpage_counts` for the Flask DM Content subpage badges with stable keys `statblocks`, `conditions`, `player_wiki`, `staged_articles`, and `systems`. Management-only lanes return permission-safe counts for the current viewer; inaccessible management lanes report `0`.
- `DM Content -> Player Wiki` creates, edits, and unpublishes published wiki pages through the forward-reconciliation coordinator, uploads page images into campaign assets under `wiki-pages/`, can prefill a new page from a staged or revealed session article in the Flask editor, and only hard-deletes after usage checks pass. Checked-delete retains its existing authorization, CSRF, confirmation, refusal, redirect, and status behavior while successful deletion uses the private deletion journal and writes one browser audit. Flask browser uploads convert PNG/JPG page images and session-article image copies into WebP quality 82 app-owned assets for published page frontmatter; JSON clients can use the same content asset API when they need direct upload control.
- `DM Content -> Systems` manages campaign source enablement and entry overrides through the same Systems policy service as `PUT /api/v1/campaigns/<campaign_slug>/systems/sources` and `PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<entry_key>`. The Systems management payload is available from `GET /api/v1/campaigns/<campaign_slug>/dm-content/systems`; it creates/updates/archives/restores custom campaign Systems entries through the `/systems/custom-entries` JSON endpoints, imports or refreshes campaign item mechanics through `/systems/item-mechanics/import`, reviews sanitized import-run history, and keeps admin-only DND-5E ZIP uploads permission-gated on the Flask import form.
- `DM Content -> Staged Articles` writes into the existing session article store for manual, upload, and wiki-backed prep articles. The JSON API can create, revise unrevealed staged article title/body/image metadata or replacement image, reveal, delete, and bulk-clear revealed session articles. Browser Player Wiki promotion/conversion still owns the richer publication safety review.
- `DM Content -> Statblocks` and `DM Content -> Conditions` have both browser and JSON API create/update/delete coverage through the `/dm-content/statblocks` and `/dm-content/conditions` endpoints.

Use the browser Player Wiki lane when you want the built-in removal guidance, archive/unpublish affordance, session-article promotion flow, and usage blockers for backlinks, character hooks or sheet references, and session provenance. The content page API includes the same removal-safety contract on page list/detail/upsert responses: `can_hard_delete`, `hard_delete_blockers`, `removal_status_label`, `removal_guidance`, and nested `removal_safety`. `DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>` blocks unsafe hard deletes with `409 hard_delete_blocked` unless the request explicitly provides `?force=true` or JSON body `{"force": true}`. A blocked response keeps the existing error envelope and nested `details.removal_safety`; malformed JSON returns `400 validation_error`, and a missing page returns 404. Success returns HTTP 200 with `{"ok": true, "deleted": {"page_ref": "<page_ref>", "relative_path": "<page_ref>.md"}}`, uses the private deletion journal, retains all campaign assets, and writes no browser audit. Prefer unpublish/archive through a metadata update unless a hard delete is intentionally forced after review. The reference-blocker graph is unchanged; forcing bypasses that review but does not add an image or Markdown cleanup policy.

## Request Notes

- `GET /api/v1/app` exposes the current app version, build id, runtime, and active DB/campaign paths.
- The shared systems ingest endpoints are app-admin only. Campaign DMs can manage campaign systems policy, but only app admins can import new shared library source data.
- `POST /api/v1/systems/imports/dnd5e` accepts `source_ids`, optional `entry_types`, and an embedded `archive` object with `filename` and `data_base64`. The archive must be a `.zip` containing a compatible DND 5E source `data/` directory.
- `POST /api/v1/systems/imports/dnd5e` also accepts optional `import_version` and `source_path_label` overrides if you want import-run history to show a custom source label instead of the uploaded archive name. Its supported bare endpoint remains `api.systems_import_dnd5e`, with one POST rule, implicit `OPTIONS`, and no `HEAD`. `systems_api_routes.py` owns the controller and explicit registration; `api.py` retains the Blueprint, shared request/error helpers and serializers, and importer/store/service composition supplied to that transport.
- After the complete DND-5E API import succeeds, the controller synchronously writes one app-global `systems_dnd5e_source_imported` auth event before import-run refetch or response serialization. The event uses the real app-admin actor with `campaign_slug` unset and records canonical `library_slug: "DND-5E"`, result-derived ordered `source_ids` and `import_run_ids` (including truthful repeats), effective first-seen `entry_types` or `["all"]`, the trimmed `archive_filename`, and `source: "api"`. Validation, archive/import, or later-source failure writes no success event. Audit failure propagates after completed import runs and shared-entry replacements are already durable; later refetch or serialization failure occurs after the audit is durable. The browser import contract is unchanged.
- `GET /api/v1/systems/import-runs` and `GET /api/v1/systems/import-runs/<import_run_id>` are app-admin-only, read-only transports for recorded shared-library ingest history. They retain the supported bare `api.systems_import_run_list` and `api.systems_import_run_detail` endpoint identifiers, with one GET rule apiece and implicit `HEAD` and `OPTIONS`. Their existing serializer exposes the stored raw `source_path`, full import summary, timestamps, and `started_by_user_id`.
- Custom campaign Systems entry create/update/archive/restore is exposed through DM/admin JSON endpoints under `/api/v1/campaigns/<campaign_slug>/systems/custom-entries`. Successful mutations return HTTP 200 without redirecting and include `ok`, the serialized `entry`, and a refreshed `systems` management payload. Create and update require a JSON object and retain `400 invalid_json` for malformed, non-object, Markdown-limit, or service-validation failures; archive and restore ignore request-body content and retain `400 validation_error` for an invalid entry. Update keeps the existing slug and entry key. Each service mutation commits before its auth audit, and the audit runs before entry serialization and refreshed-payload construction, so a later audit, serializer, or payload failure can follow durable SQLite changes; archive and restore retain their refetch-or-original response fallback. Imported shared-library Systems entries remain read-only at the content level; use campaign source policy or entry overrides for campaign-specific changes unless a shared-library edit model is deliberately added later.
- Campaign item mechanics import is exposed through `POST /api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import`. The supported bare endpoint remains `api.systems_item_mechanics_import`, with one POST rule, implicit `OPTIONS`, and no `HEAD`. The payload requires `page_ref` and accepts optional `visibility`, `item_mechanics_review_status` (or the existing `mechanics_review_status` alias), and object-valued manual `item_mechanics` overrides. It remains DM/admin-only through the existing Systems-management boundary: non-admin managers require effective Systems-scope access, while direct app admins retain their established bypass. The route keeps the existing View As, session-CSRF, bearer-token, and JSON error boundaries and accepts only published item pages through `SystemsService`. The service/store path creates or refreshes a campaign-owned custom Systems `item` entry linked to that page, stores interpreter review output and unsupported flags, and returns both the saved `entry` and a refreshed `systems` management payload. The durable service write still precedes the auth audit, entry serialization, and full-payload build, so later failures retain the existing partial-durability behavior.
- `GET /api/v1/me` now includes the same app metadata block alongside the authenticated user payload, memberships, user preferences such as `theme_key`, `session_chat_order`, and the compatibility `frontend_mode` field, plus the admin-only `view_as` state. Flask is the only browser frontend; `frontend_mode` reads normalize to `flask`.
- `POST /api/v1/me/view-as` and `DELETE /api/v1/me/view-as` are browser-session admin-only endpoints for setting or clearing the active `View As` target. Non-admin users receive `403`; blank or self targets clear the mode; inactive or missing users are rejected. The active target affects only campaign-facing safe reads, while `/api/v1/me` and account/admin routes keep the real authenticated admin identity.
- `GET /api/v1/me/settings` returns the authenticated user's account-settings payload, including theme presets with preview colors, live-session chat-order choices, and current preferences. `PATCH /api/v1/me/settings` accepts `theme_key` and/or `session_chat_order`, validates them with the same account helpers as Flask, persists the preferences, and returns the refreshed preference values used by `/api/v1/me` theme hydration. `frontend_mode` writes are rejected because the preferred-frontend account setting is retired.
- `GET /api/v1/admin` and `GET /api/v1/admin/users/<user_id>` are app-admin-only Admin reads. They expose dashboard and user-detail context, user cards, campaign and character choices, audit filter choices, paginated audit rows, and Flask CSV export URLs.
- Admin mutations under `/api/v1/admin/users...` reuse the same auth-store operations and audit events as Flask for invites, membership save/remove, character assignment/clear, invite links, password reset links, disable/enable, and checked user deletion. Deletion requires a matching `confirm_email`; anonymous users receive `401`, non-admin users receive `403`, and one-shot invite/reset URLs are returned only in mutation responses rather than audit rows.
- `GET /api/v1/campaigns/<campaign_slug>` includes visibility-aware campaign permissions such as `can_manage_visibility`.
- `GET /api/v1/campaigns/<campaign_slug>/control` and `PATCH /api/v1/campaigns/<campaign_slug>/control/visibility` expose the Campaign Control visibility editor. They require campaign visibility management permission, return the same selected/configured/default/effective visibility rows as the Flask Control panel, reject invalid visibility values, reserve `private` for app admins, clear visibility caches after writes, and write `campaign_visibility_updated` audit events for changed scopes.
- `GET /api/v1/campaigns/<campaign_slug>/help` returns the campaign-scoped Help context used by API clients, including visible help surfaces, viewer-role summary, effective visibility rows, cross-cutting limits, and Flask link fields. It follows campaign-scope access and reuses the same Help context builder as the Flask Help page.
- The `/wiki` endpoints are player-facing published-wiki reads for API clients. `GET .../wiki` follows campaign-scope access and returns a restricted-wiki message when the campaign is visible but the wiki scope is not; section and page detail reads require wiki-scope access. These endpoints return only visible published pages, rendered body HTML through the same repository renderer as Flask, Flask hrefs by default, and page image URLs only when the referenced protected campaign asset exists. Stale `/app-next` links in rendered wiki body HTML are rewritten to `/campaigns/...`.
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config` currently supports the live editable campaign fields `title`, `summary`, `system`, `current_session`, `source_wiki_root`, and `systems_library`. Supported `system` and `systems_library` aliases are canonicalized through the app system-policy layer, including `DND-5E` and `Xianxia`.
- Asset detail reads return `data_base64`, and asset writes use an embedded `asset_file` object with `filename` and `data_base64`.
- The `/content/...` management endpoints are DM/admin only. They expose unpublished pages and raw character file content, so they intentionally do not follow normal player-facing visibility rules.
- Page management endpoints read and write raw frontmatter plus `body_markdown`. Page upsert and hard delete use their durable reconciliation journals, finalize the SQLite read model, and refresh the running repository from that database state so the current app process sees the change immediately. Set page metadata such as `published: false` for an API-driven archive/unpublish workflow instead of hard-deleting a referenced page.
- Campaign config writes also refresh the running repository so title, summary, current session, and systems-library changes take effect immediately.
- Character management endpoints read and write `definition.yaml` and `import.yaml`. For `PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`, an all-absent target retains the existing `content_api_create` behavior; a complete existing target uses durable `content_api_update` reconciliation. Partial targets and targets that remain active or conflicted after recovery fail closed. Unchanged DND or Xianxia mutable state is not rewritten; changed Xianxia state reconciliation advances its revision by exactly one.
- The raw character content PUT remains DM/admin-only, continues to accept the existing `definition` and optional `import_metadata` payload fields, returns validation failures through the existing HTTP 400 `validation_error` envelope, and returns HTTP 200 with the existing `{"ok": true, "character_file": ...}` shape on success. Restart and verified-backup recovery complete eligible `prepared` or `repository_pending` work forward. The journal does not make SQLite and filesystem publication one atomic transaction. See [Characters Overview](current-state/characters-overview.md) for the storage and recovery boundaries.
- Character content management endpoints accept both DND-5E and Xianxia file-backed definitions. For Xianxia, submit `system: "Xianxia"` with a top-level stable `xianxia` definition block; the content service normalizes supported aliases into the canonical Realm, action-count, Honor, Attribute, Effort, Energy, Yin/Yang, durability, Martial Art, Generic Technique, approval, and advancement-history fields.
- Xianxia mutable play state remains SQLite-backed. Current HP/Stance, Energy, Yin/Yang, Dao, active Stance/Aura, inventory quantities, and notes should not be written into `definition.yaml`; when the character content API updates an existing Xianxia definition, it reconciles the existing mutable state against the new definition maxima instead of replacing live session values.
- Xianxia native creation, Xianxia manual import, Xianxia Cultivation, DND-5E native creation, DND-5E Advanced Editor, and DND-5E level-up have JSON contracts used by Flask browser flows and API clients. Session-state JSON coverage also includes active Stance/Aura, modeled inventory add/edit/remove/equip, and Dao Immolating use request/record actions because browser session surfaces consume those same durable write paths.
- Character content management endpoints are low-level file operations. Native in-browser character create/import, edit, level-up, progression repair, assignment, and deletion workflows continue to use the character-specific routes and support matrix rather than the raw content API.
- Deleting a managed character removes the file-backed definition/import metadata, the live `character_state` row, and any character assignment for that slug.
- Session message creation accepts optional `recipient_scope` values of `global`, `dm_only`, or `player`; `player` messages also require `recipient_user_id` for an active campaign player. Session reads server-filter messages for ordinary players, while DM/admin reads and closed session-log reads include all messages with `recipient_scope`, `recipient_user_id`, and `recipient_label` metadata. Revealed session articles remain global-only.
- DM/admin Session reads include `show_session_dm_passive_scores`; for DND-5E campaigns they also include `session_dm_passive_scores` rows with character name, Passive Perception, Passive Insight, and Passive Investigation values for the DM Session workspace.
- Session article creation accepts JSON `mode: "manual"`, `mode: "upload"`, or `mode: "wiki"`.
- Manual session article creation requires a title plus either `body_markdown` or an embedded `image`; image-only staged articles are valid when the image payload passes normal session-article image validation.
- Upload mode accepts `filename`, `markdown_text`, and optional `referenced_image`. Markdown uploads whose body is only a referenced image are valid when `referenced_image` is supplied.
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search?q=...` lazily searches visible published wiki pages plus accessible Systems entries for DM/admin session management.
- Wiki mode accepts `source_ref`. For published wiki pages, `source_ref` is the page ref such as `npcs/captain-lyra-vale`. For Systems entries, use `systems:<entry-slug>`. Legacy `page_ref` still works for published wiki pages.
- Pulling a published wiki page creates a staged markdown snapshot from the current visible page. If that page has a published frontmatter image, the API copies it into the session article image store so reveal behavior matches a native staged article.
- Pulling a Systems entry creates a staged HTML snapshot from the current rendered Systems article. Session article payloads now include `source_page_ref`, `source_kind`, `source_ref`, and `body_format` so API clients can tell whether the staged body is markdown or rendered HTML.
- Session article payloads also include `source`, `converted_page`, and `links` metadata for API clients. `links.source_url` points back to the pulled wiki page or Systems entry when it is still accessible; session-only manual/upload articles expose `links.player_wiki_editor_url` and `links.convert_url` for the established browser publication workflows; already converted articles expose `links.published_page_url` when the published page is currently visible.
- Staged session articles can be revised with `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>` using `title`, `body_markdown`, optional replacement `image`, or optional existing-image `image_alt_text` / `image_caption`. The revised article must retain either body text or an existing or replacement image. Revealed articles remain immutable in the prep queue.
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed` removes all currently revealed session articles for DM/admin cleanup and returns the deleted article IDs.
- Embedded image payloads use JSON objects with `filename`, optional `media_type`, and `data_base64`.
- Systems browsing reads are available at `GET /api/v1/campaigns/<campaign_slug>/systems`, its `/systems/search` alias, `/systems/sources`, `/systems/sources/<source_id>`, `/systems/sources/<source_id>/types/<entry_type>`, and `/systems/entries/<entry_slug>`. Together with the two app-admin import-run reads, `systems_api_routes.py` owns seven read handlers across eight GET rules plus eight mutation handlers for source policy, entry overrides, custom-entry create/update/archive/restore, campaign item-mechanics import, and app-admin DND-5E ingest, for 15 handlers and 16 explicit registrations on the existing API Blueprint. Landing and search share `api.systems_index`; all other registrations retain their bare `api.*` endpoint identifiers, including `api.systems_import_run_list`, `api.systems_import_run_detail`, `api.systems_item_mechanics_import`, `api.systems_import_dnd5e`, and the four `api.systems_custom_entry_*` identifiers. The custom-entry, item-mechanics, and DND-5E ingest POST mutation rules retain implicit `OPTIONS` without `HEAD`. On the final qualified Phase 3B branch, `api.py` retains the Blueprint, 35 direct route decorators, shared decorators, request/error helpers, serializers, import-run and importer/store/service composition, the full DM Content Systems-payload builder, dependency wiring, and the other nonmoved Systems JSON routes; extracted Session, Character, Auth, Admin, and Systems registrars own the remainder.
- These reads preserve source-level and entry-level visibility, support `q` on landing/category searches, support `reference_q` for landing and source-scoped rules-reference metadata searches, and return server-rendered safe Systems entry HTML for detail pages. The source-list GET returns all configured states to a Systems manager and only enabled, accessible states to a non-manager, with matching permission fields. Because GET and PUT share `/systems/sources`, its OPTIONS response advertises GET, HEAD, OPTIONS, and PUT.
- For direct-admin entry inspection, the browser and API intentionally differ at the source boundary: a direct app admin can use the API to inspect a stored entry through a disabled source, while the browser still requires the source to be enabled before rendering entry detail. An admin using `View As` is evaluated as the effective target actor and retains no admin bypass. Systems source updates, entry-override writes, custom campaign entry mutations, and campaign item mechanics import remain DM/admin only. The eight Systems mutation transports in `systems_api_routes.py` retain their payloads, authorization, persistence, and durability behavior: the seven campaign mutations keep their established auth-audit ordering, while app-admin DND-5E ingest writes its one app-global success audit after the full import and before response preparation. The DM Content Systems management payload is also DM/admin only and intentionally omits raw import `source_path` values.
- Combat reads return a structured tracker payload plus live-play metadata: `live_revision`, `live_view_token`, `selected_combatant`, `selected_player_character`, `player_character_targets`, manager-only `available_character_choices`, `available_statblock_choices`, `combat_condition_options`, `poll_settings`, and Flask links for Combat, DM Status, and DM Controls where authorized. Clients can echo `X-Live-Revision` and `X-Live-View-Token` on `GET .../combat` or `GET .../combat/live-state`; matching values return only `changed: false`, `live_revision`, and `live_view_token` so clients can preserve the already-mounted player or DM combat workspace. Unsupported campaign systems return `combat_system_supported: false` with an empty tracker and fallback link instead of starting live polling.
- Combat mutations are DM/admin only except for player-character vitals, which can also be updated by the assigned owner player when they provide the current sheet revision. Browser Combat consumes the read payload, combat mutation endpoints, Systems monster search, and shared Character detail/session-state contracts for player Combat, manager DM Status, and manager DM Controls. DM Status uses `combatant=<id>` as canonical selected focus for turn, vitals, action economy, source-backed NPC resources, condition add/remove, selected-PC detail, and selected-combatant cleanup. DM Controls uses the same JSON endpoints for player-character seeding, manual NPC seeding, DM Content statblock seeding, Systems monster search/seeding, turn advance, and clear-tracker cleanup.
- Source-backed NPC resources appear on visible combatant summaries as `npc_resource_counters` and `npc_resource_notes`. Supported counters are combatant-owned current/max rows seeded from DM Content statblocks or Systems monsters; notes preserve unsupported mechanics such as at-will or recharge references. `PATCH .../npc-resources` is DM/admin only and accepts `expected_combatant_revision` plus `counters: [{resource_key, current_value}]`.
- Combatant-row combat writes can also send `expected_combatant_revision`; when that row changed first, the API returns `409 state_conflict` instead of last-writing stale movement, action-economy, source-backed NPC resource, NPC vitals, or turn-value payloads.
- Character session mutations require `expected_revision` and return `409 state_conflict` when the sheet changed first. These live/session JSON lanes are available to DMs/admins and to a player assigned to that character, even when the full Characters surface remains DM-only; unassigned players still receive `403 forbidden`. For Xianxia characters, `PATCH .../session/vitals` also accepts `current_stance`, `temp_stance`, `current_jing`, `current_qi`, `current_shen`, `current_yin`, `current_yang`, and `current_dao` alongside shared HP/temp HP. `PATCH .../session/inventory/<item_id>` routes to the Xianxia inventory quantity write path when the character system is Xianxia. `POST .../session/xianxia-dao-immolating-use-requests` accepts `request_name`, optional `notes`, and optional `prepared_record_index`; it appends a pending ad hoc or prepared-note-backed definition-level use request. `POST .../session/xianxia-dao-immolating-use-records` is DM/session-manager only and accepts `use_record_index` plus optional `notes`; it records one approved unused Dao Immolating use, spends the fixed 10 Insight cost, marks that use history record used, and returns the refreshed character payload.
- Character roster reads accept optional `q` search and return Flask-aligned roster cards, including derived class text, HP/temp HP, Hit Dice summary, up to three resource previews, sheet links, roster tool flags, and protected portrait metadata when the character profile points at an existing campaign asset. If the viewer cannot access the broader Characters scope but is assigned to one or more characters, the roster read returns only those assigned character cards for live/session surfaces such as Combat.
- `GET /api/v1/campaigns/<campaign_slug>/characters/create` returns the system-lane create context. DND-5E campaigns receive the level-1 builder core options, dynamic choice sections, preview, readiness flag, and Flask links. Xianxia campaigns receive canonical Attribute/Effort/Energy/Skill fields, Martial Art/rank choices, GM grant fields, starting defaults, and import links. `POST .../characters/create` accepts `values`, rebuilds the authoritative backend context, validates through the DND-5E or Xianxia builder, writes `definition.yaml` and `import.yaml`, initializes SQLite mutable state, and returns the refreshed character plus Flask links. The endpoint requires the same character-management access as Flask create.
- `GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual` returns the manual Xianxia import context. `POST .../characters/import/xianxia-manual` accepts `values`; without `confirm_import` it returns a review preview and writes nothing, and with `confirm_import: true` it writes the normal Xianxia definition/import files plus initial SQLite state. The route is Xianxia-only and uses the same enabled Martial Art Systems choices as the Flask manual importer.
- Character detail reads return the raw file-backed definition/state plus presentation helpers and detail links. DND-5E `equipment_state.rows` and `presented_inventory` include linked item `href` and server-rendered `description_html` when the item resolves to an accessible Systems entry or campaign page. `presented_spellcasting` mirrors the browser spell presentation with spell facts, badges, source links, and server-rendered `description_html` for linked spells. Xianxia reads expose `presented_xianxia`, which mirrors the existing `xianxia_read` presenter context for Character and Session Character sections, including Quick Reference derivations, Resources, active state, Martial Arts, Techniques, Skills, Equipment, modeled Inventory, Xianxia currency, approval/reference records, and notes-adjacent state. Detail payloads also include protected portrait metadata when available.
- Character Controls and portrait endpoints remain on the character-detail contract. The `controls` payload is included when the campaign supports character controls and the viewer has session-mode character access; it reports owner assignment, owner identity, admin assignment choices, delete permission, and Flask links. `POST .../controls/assignment` assigns an active campaign player as owner and is app-admin only. `DELETE .../controls/assignment` clears the current owner assignment and is app-admin only. `DELETE .../controls` deletes the character after `confirm_character_slug` matches the route slug, removes file-backed metadata, mutable state, and assignment records, and requires DM/admin content-management permission. `PUT .../portrait` writes the campaign-owned portrait asset from an embedded file payload, and `DELETE .../portrait` clears the portrait metadata and asset. Controls and portrait writes return `409 state_conflict` on stale sheet revisions.
- `GET .../advanced-editor` returns the DND-5E native edit field context, option lists, current state revision, links, and unsupported fallback metadata for non-DND lanes. `PUT .../advanced-editor` accepts `expected_revision` plus a flat `values` object matching the returned field names, reuses the existing native edit apply/derivation path for proficiencies, reference text, stat adjustments, recoverable penalties, custom features, and manual equipment, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Advanced Editor writes are available to DMs/admins and assigned players with session-mode character access, return `409 state_conflict` on stale sheet revisions, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../progression-repair` returns the DND-5E imported-character repair context, current sheet revision, readiness reasons, class/subclass repair rows, species/background options, prior feat or optional-feature backfill rows, spell-row classification fields, Flask links, and unsupported fallback metadata for non-repairable lanes. `POST .../progression-repair` accepts `expected_revision` plus a flat `values` object matching the returned repair field names, reuses the existing imported progression-repair apply path, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Progression repair writes are manager-only, return `409 state_conflict` on stale sheet revisions, return a Level Up handoff when the sheet becomes ready, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../retraining` returns the DND-5E native structured retraining context, current sheet revision, supported linked-feature choice rows, Flask links, and unsupported or repairable fallback metadata for non-ready lanes. `POST .../retraining` accepts `expected_revision` plus a flat `values` object matching the returned retraining field names, reuses the existing native edit/retraining derivation path for persisted linked-feature choices, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Retraining writes use the same session-mode character access as Flask retraining, return `409 state_conflict` on stale sheet revisions, point repairable imported sheets at progression repair, and return `unsupported_campaign_system` for unsupported lanes.
- `GET .../level-up` returns the DND-5E native level-up context, current sheet revision, readiness metadata, dynamic choice sections, preview payload, Flask links, and unsupported or repairable fallback metadata for non-ready lanes. `POST .../level-up` accepts `expected_revision` plus a flat `values` object matching the returned level-up field names, reuses the existing native level-up builder/apply path for one-level advancement and HP gain, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Level-up writes are manager-only, return `409 state_conflict` on stale sheet revisions, point repairable imported sheets at progression repair, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../cultivation` returns the Xianxia Cultivation context, current sheet revision, Flask links, and unsupported fallback metadata for non-Xianxia sheets. `POST .../cultivation` accepts `expected_revision`, an action name, and a flat `values` object matching the Flask Cultivation form names; supported actions include Insight save, Gathering Insight, Cultivation Energy, Meditation, Conditioning, Training, Martial Art rank advancement, Generic Technique learning, Realm review start, Realm stat reset, Immortal/Divine rebuild, and final Realm confirmation. Cultivation writes are manager-only, return `409 state_conflict` on stale sheet revisions, preserve mutable state through definition reconciliation, and return `unsupported_campaign_system` for non-Xianxia lanes.
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit` is the legacy compatibility contract for out-of-session Character-page batching. It accepts one `expected_revision` plus absolute-value section payloads for the state-backed Character-page fields (`vitals`, `resources`, `spell_slots`, `inventory`, `currency`, `notes`, and `personal`).
- The `sheet-edit` batch route is intentionally absolute-value only. Delta actions such as `hp_delta`, resource `delta`, spell-slot `delta_used`, currency `delta`, and rest actions stay on the immediate live-edit routes instead of mixing relative and batched writes.
- `sheet-edit` batches use one shared revision check for the whole request. If any other actor changed the character first, the entire batch is rejected with `409 state_conflict` rather than partially applying the payload.
- If a `409` is returned, clients should refresh and retry from a fresh draft because the route does not merge partial drafts.
- The browser normal Character workflow now favors inline per-form state edits; DND-5E sheets expose HP, resources, spell slots, inventory quantities, currency, and notes, while Xianxia sheets expose Resources, Techniques request/record actions, Inventory/currency, and Notes state lanes. Batch behavior is still available for compatibility and is not the recommended browser workflow.
- Browser lane boundaries are now: the normal Character page inline state slice for quick DND HP/resource/slot/inventory/currency/notes and Xianxia resource/technique/inventory/currency/notes updates, `Session Character` for active-session edits, and `Combat`/`Encounter status` for encounter-context edits tied to `combatant=<id>`.
- API reads and writes use the same visibility and role checks as the app. A DM token can do DM work; a player token only sees or edits what that player could in the site.
