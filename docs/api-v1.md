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
- `POST /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/reveal`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `GET /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `GET /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/image`
- `GET /api/v1/campaigns/<campaign_slug>/dm-content`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/statblocks`
- `DELETE /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<statblock_id>`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/conditions`
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
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>`

## Request Notes

- `GET /api/v1/app` exposes the current app version, build id, runtime, and active DB/campaign paths.
- The shared systems ingest endpoints are app-admin only. Campaign DMs can manage campaign systems policy, but only app admins can import new shared library source data.
- `POST /api/v1/systems/imports/dnd5e` accepts `source_ids`, optional `entry_types`, and an embedded `archive` object with `filename` and `data_base64`. The archive must be a `.zip` containing a compatible DND 5E source `data/` directory.
- `POST /api/v1/systems/imports/dnd5e` also accepts optional `import_version` and `source_path_label` overrides if you want import-run history to show a custom source label instead of the uploaded archive name.
- `GET /api/v1/systems/import-runs` and `GET /api/v1/systems/import-runs/<import_run_id>` expose the recorded shared-library ingest history, including import summaries and source file lists.
- `GET /api/v1/me` now includes the same app metadata block alongside the authenticated user payload.
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config` currently supports the live editable campaign fields `title`, `summary`, `system`, `current_session`, `source_wiki_root`, and `systems_library`.
- Asset detail reads return `data_base64`, and asset writes use an embedded `asset_file` object with `filename` and `data_base64`.
- The `/content/...` management endpoints are DM/admin only. They expose unpublished pages and raw character file content, so they intentionally do not follow normal player-facing visibility rules.
- Page management endpoints read and write raw frontmatter plus `body_markdown`, then refresh the running repository so the current app process sees the changes immediately.
- Campaign config writes also refresh the running repository so title, summary, current session, and systems-library changes take effect immediately.
- Character management endpoints read and write `definition.yaml` and `import.yaml`. They initialize live character state if it does not already exist, but they do not overwrite existing mutable session state.
- Deleting a managed character removes the file-backed definition/import metadata, the live `character_state` row, and any character assignment for that slug.
- Session article creation accepts JSON `mode: "manual"`, `mode: "upload"`, or `mode: "wiki"`.
- Upload mode accepts `filename`, `markdown_text`, and optional `referenced_image`.
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search?q=...` lazily searches visible published wiki pages plus accessible Systems entries for DM/admin session management.
- Wiki mode accepts `source_ref`. For published wiki pages, `source_ref` is the page ref such as `npcs/captain-lyra-vale`. For Systems entries, use `systems:<entry-slug>`. Legacy `page_ref` still works for published wiki pages.
- Pulling a published wiki page creates a staged markdown snapshot from the current visible page. If that page has a published frontmatter image, the API copies it into the session article image store so reveal behavior matches a native staged article.
- Pulling a Systems entry creates a staged HTML snapshot from the current rendered Systems article. Session article payloads now include `source_page_ref`, `source_kind`, `source_ref`, and `body_format` so API clients can tell whether the staged body is markdown or rendered HTML.
- Embedded image payloads use JSON objects with `filename`, optional `media_type`, and `data_base64`.
- Systems read endpoints follow the same source-level and entry-level visibility rules as the browser UI. Systems source updates and entry-override writes are DM/admin only.
- Combat reads return a structured tracker payload. Combat mutations are DM/admin only except for player-character vitals, which can also be updated by the assigned owner player when they provide the current sheet revision.
- Character session mutations require `expected_revision` and return `409 state_conflict` when the sheet changed first.
- API reads and writes use the same visibility and role checks as the app. A DM token can do DM work; a player token only sees or edits what that player could in the site.
