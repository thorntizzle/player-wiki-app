# API v1

`Campaign Player Wiki` now exposes a JSON API under `/api/v1` for the app's mutable content and live campaign operations.

The API also now manages the live file-backed content stored on the campaign volume:

- campaign config updates in `campaigns/<campaign-slug>/campaign.yaml`
- published wiki pages under `campaigns/<campaign-slug>/content/`
- published asset files under `campaigns/<campaign-slug>/assets/`
- character definition/import files under `campaigns/<campaign-slug>/characters/`

## Auth

API access uses bearer tokens tied to existing app users. Tokens inherit the same admin flag, campaign memberships, ownership rules, and visibility checks as the browser UI.

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

- `GET /api/v1/app`
- `GET /api/v1/systems/import-runs`
- `GET /api/v1/systems/import-runs/<import_run_id>`
- `POST /api/v1/systems/imports/dnd5e`
- `GET /api/v1/me`
- `GET /api/v1/campaigns`
- `GET /api/v1/campaigns/<campaign_slug>`
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
- `POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/conditions`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/conditions/<condition_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>`
- `GET /api/v1/campaigns/<campaign_slug>/characters`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
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

## Session Polling

`GET /api/v1/campaigns/<campaign_slug>/session` now participates in session polling:

- Include `X-Live-Revision` and `X-Live-View-Token` request headers for each poll.
- The response always includes `session_revision` and `session_view_token`.
- If both headers match current server values, the endpoint returns:
  - `{"ok": true, "changed": false, "session_revision": <int>, "session_view_token": "<token>"}`.
- If either header differs, the endpoint returns the full `/session` payload with updated revision/token metadata.

## Browser Content Management Coverage

The browser `DM Content` hub now covers the main DM-managed content lanes while still reusing the same app services and JSON API where those are the right write contract:

- `DM Content -> Player Wiki` creates and edits published wiki pages through the content service, uploads page images into campaign assets under `wiki-pages/`, converts PNG/JPG browser uploads and session-article image copies into WebP quality 82 app-owned assets for published page frontmatter, can prefill a new page from a staged or revealed session article, can unpublish/archive pages by updating page metadata, and only hard-deletes through the browser after usage checks pass.
- `DM Content -> Systems` manages campaign source enablement and entry overrides through the same Systems policy service as `PUT /api/v1/campaigns/<campaign_slug>/systems/sources` and `PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<entry_key>`. It also owns the browser surface for custom campaign Systems entries, shared-source import review, and admin-only DND-5E ZIP uploads.
- `DM Content -> Staged Articles` writes into the existing session article store for manual, upload, and wiki-backed prep articles. The JSON API can create, revise unrevealed staged article title/body/image metadata or replacement image, reveal, delete, and bulk-clear revealed session articles. Browser Player Wiki promotion/conversion still owns the richer publication safety review.
- `DM Content -> Statblocks` and `DM Content -> Conditions` have both browser and JSON API create/update/delete coverage through the `/dm-content/statblocks` and `/dm-content/conditions` endpoints.

Use the browser Player Wiki lane when you want the built-in removal guidance, archive/unpublish affordance, session-article promotion flow, and usage blockers for backlinks, character hooks or sheet references, and session provenance. The low-level content API remains automation-oriented: `DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>` deletes the page file after DM/admin authorization and does not display the browser safety review, so API clients should either unpublish through a metadata update or reproduce the relevant dependency checks before hard deletion.

## Request Notes

- `GET /api/v1/app` exposes the current app version, build id, runtime, and active DB/campaign paths.
- The shared systems ingest endpoints are app-admin only. Campaign DMs can manage campaign systems policy, but only app admins can import new shared library source data.
- `POST /api/v1/systems/imports/dnd5e` accepts `source_ids`, optional `entry_types`, and an embedded `archive` object with `filename` and `data_base64`. The archive must be a `.zip` containing a compatible DND 5E source `data/` directory.
- `POST /api/v1/systems/imports/dnd5e` also accepts optional `import_version` and `source_path_label` overrides if you want import-run history to show a custom source label instead of the uploaded archive name.
- `GET /api/v1/systems/import-runs` and `GET /api/v1/systems/import-runs/<import_run_id>` expose the recorded shared-library ingest history, including import summaries and source file lists.
- Browser custom campaign Systems entry create/edit/archive/restore is currently service-backed rather than exposed as a JSON API endpoint. Imported shared-library Systems entries remain read-only at the content level; use campaign source policy or entry overrides for campaign-specific changes unless a shared-library edit model is deliberately added later.
- `GET /api/v1/me` now includes the same app metadata block alongside the authenticated user payload, memberships, and user preferences such as `theme_key` and `session_chat_order`.
- `GET /api/v1/campaigns/<campaign_slug>` includes visibility-aware campaign permissions such as `can_manage_visibility`, which the Gen2 shell uses to decide whether to show the Control link.
- The `/wiki` endpoints are player-facing published-wiki reads for Gen2 and other clients. `GET .../wiki` follows campaign-scope access and returns a restricted-wiki message when the campaign is visible but the wiki scope is not; section and page detail reads require wiki-scope access. These endpoints return only visible published pages, rendered body HTML through the same repository renderer as Flask, Gen2 hrefs for wiki links, and page image URLs only when the referenced protected campaign asset exists.
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config` currently supports the live editable campaign fields `title`, `summary`, `system`, `current_session`, `source_wiki_root`, and `systems_library`. Supported `system` and `systems_library` aliases are canonicalized through the app system-policy layer, including `DND-5E` and `Xianxia`.
- Asset detail reads return `data_base64`, and asset writes use an embedded `asset_file` object with `filename` and `data_base64`.
- The `/content/...` management endpoints are DM/admin only. They expose unpublished pages and raw character file content, so they intentionally do not follow normal player-facing visibility rules.
- Page management endpoints read and write raw frontmatter plus `body_markdown`, then refresh the running repository so the current app process sees the changes immediately. Set page metadata such as `published: false` for an API-driven archive/unpublish workflow instead of hard-deleting a referenced page.
- Campaign config writes also refresh the running repository so title, summary, current session, and systems-library changes take effect immediately.
- Character management endpoints read and write `definition.yaml` and `import.yaml`. They initialize live character state if it does not already exist, but they do not overwrite existing mutable session state.
- Character content management endpoints accept both DND-5E and Xianxia file-backed definitions. For Xianxia, submit `system: "Xianxia"` with a top-level stable `xianxia` definition block; the content service normalizes supported aliases into the canonical Realm, action-count, Honor, Attribute, Effort, Energy, Yin/Yang, durability, Martial Art, Generic Technique, approval, and advancement-history fields.
- Xianxia mutable play state remains SQLite-backed. Current HP/Stance, Energy, Yin/Yang, Dao, active Stance/Aura, inventory quantities, and notes should not be written into `definition.yaml`; when the character content API updates an existing Xianxia definition, it reconciles the existing mutable state against the new definition maxima instead of replacing live session values.
- Xianxia native creation and Cultivation/advancement remain browser workflows in v1. Session-state JSON coverage now includes active Stance/Aura, modeled inventory add/edit/remove/equip, and Dao Immolating use request/record actions because Gen2 Session Character consumes those same durable write paths.
- Character content management endpoints are low-level file operations. Native in-browser character create, edit, level-up, progression repair, portrait, assignment, and deletion workflows continue to use the character-specific routes and support matrix rather than the raw content API.
- Deleting a managed character removes the file-backed definition/import metadata, the live `character_state` row, and any character assignment for that slug.
- Session article creation accepts JSON `mode: "manual"`, `mode: "upload"`, or `mode: "wiki"`.
- Upload mode accepts `filename`, `markdown_text`, and optional `referenced_image`.
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search?q=...` lazily searches visible published wiki pages plus accessible Systems entries for DM/admin session management.
- Wiki mode accepts `source_ref`. For published wiki pages, `source_ref` is the page ref such as `npcs/captain-lyra-vale`. For Systems entries, use `systems:<entry-slug>`. Legacy `page_ref` still works for published wiki pages.
- Pulling a published wiki page creates a staged markdown snapshot from the current visible page. If that page has a published frontmatter image, the API copies it into the session article image store so reveal behavior matches a native staged article.
- Pulling a Systems entry creates a staged HTML snapshot from the current rendered Systems article. Session article payloads now include `source_page_ref`, `source_kind`, `source_ref`, and `body_format` so API clients can tell whether the staged body is markdown or rendered HTML.
- Session article payloads also include `source`, `converted_page`, and `links` metadata for Gen2/other clients. `links.source_url` points back to the pulled wiki page or Systems entry when it is still accessible; session-only manual/upload articles expose `links.player_wiki_editor_url` and `links.convert_url` for the established browser publication workflows; already converted articles expose `links.published_page_url` when the published page is currently visible.
- Staged session articles can be revised with `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>` using `title`, `body_markdown`, optional replacement `image`, or optional existing-image `image_alt_text` / `image_caption`. Revealed articles remain immutable in the prep queue.
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed` removes all currently revealed session articles for DM/admin cleanup and returns the deleted article IDs.
- Embedded image payloads use JSON objects with `filename`, optional `media_type`, and `data_base64`.
- Systems read endpoints follow the same source-level and entry-level visibility rules as the browser UI. Systems source updates and entry-override writes are DM/admin only.
- Combat reads return a structured tracker payload. Combat mutations are DM/admin only except for player-character vitals, which can also be updated by the assigned owner player when they provide the current sheet revision.
- Combatant-row combat writes can also send `expected_combatant_revision`; when that row changed first, the API returns `409 state_conflict` instead of last-writing stale movement, action-economy, NPC vitals, or turn-value payloads.
- Character session mutations require `expected_revision` and return `409 state_conflict` when the sheet changed first. For Xianxia characters, `PATCH .../session/vitals` also accepts `current_stance`, `temp_stance`, `current_jing`, `current_qi`, `current_shen`, `current_yin`, `current_yang`, and `current_dao` alongside shared HP/temp HP. `PATCH .../session/inventory/<item_id>` routes to the Xianxia inventory quantity write path when the character system is Xianxia. `POST .../session/xianxia-dao-immolating-use-requests` accepts `request_name`, optional `notes`, and optional `prepared_record_index`; it appends a pending ad hoc or prepared-note-backed definition-level use request. `POST .../session/xianxia-dao-immolating-use-records` is DM/session-manager only and accepts `use_record_index` plus optional `notes`; it records one approved unused Dao Immolating use, spends the fixed 10 Insight cost, marks that use history record used, and returns the refreshed character payload.
- Character detail reads return the raw file-backed definition/state plus Gen2 presentation helpers. DND-5E `equipment_state.rows` and `presented_inventory` include linked item `href` and server-rendered `description_html` when the item resolves to an accessible Systems entry or campaign page. `presented_spellcasting` mirrors the browser spell presentation with spell facts, badges, source links, and server-rendered `description_html` for linked spells. Xianxia reads expose `presented_xianxia`, which mirrors the existing `xianxia_read` presenter context for Gen2 Session Character sections, including Quick Reference derivations, Resources, active state, Martial Arts, Techniques, Skills, Equipment, modeled Inventory, Xianxia currency, approval/reference records, and notes-adjacent state.
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit` is the legacy compatibility contract for out-of-session Character-page batching. It accepts one `expected_revision` plus absolute-value section payloads for the state-backed Character-page fields (`vitals`, `resources`, `spell_slots`, `inventory`, `currency`, `notes`, and `personal`).
- The `sheet-edit` batch route is intentionally absolute-value only. Delta actions such as `hp_delta`, resource `delta`, spell-slot `delta_used`, currency `delta`, and rest actions stay on the immediate live-edit routes instead of mixing relative and batched writes.
- `sheet-edit` batches use one shared revision check for the whole request. If any other actor changed the character first, the entire batch is rejected with `409 state_conflict` rather than partially applying the payload.
- If a `409` is returned, clients should refresh and retry from a fresh draft because the route does not merge partial drafts.
- The browser normal Character workflow now favors inline per-form state edits; DND-5E sheets expose HP, resources, spell slots, inventory quantities, currency, and notes, while Xianxia sheets expose Resources, Techniques request/record actions, Inventory/currency, and Notes state lanes. Batch behavior is still available for compatibility and is not the recommended browser workflow.
- Browser lane boundaries are now: the normal Character page inline state slice for quick DND HP/resource/slot/inventory/currency/notes and Xianxia resource/technique/inventory/currency/notes updates, `Session Character` for active-session edits, and `Combat`/`Encounter status` for encounter-context edits tied to `combatant=<id>`.
- API reads and writes use the same visibility and role checks as the app. A DM token can do DM work; a player token only sees or edits what that player could in the site.
