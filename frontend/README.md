# Gen2 Frontend

This React + TypeScript frontend is served alongside the existing Flask/Jinja UI under `/app-next/`.

It is a parity migration surface, not a full replacement yet. Route readiness and the current Flask-vs-Gen2 matrix live in:

- `docs/gen2-migration-readiness.md`

## Prerequisites

- Node.js 20+.
- Existing Flask app running from `campaign_player_wiki`.

## Install

```powershell
cd C:\Users\thorn\Documents\my_scripts\campaign_player_wiki\frontend
npm install
```

## Development

- Start Vite dev server:

```powershell
npm run dev
```

- In a second terminal, start the Flask app as usual (`python run.py`).
- Open `http://127.0.0.1:5173/app-next/` for hot-reload development, or `http://127.0.0.1:5000/app-next/` after building.
- The Vite dev server proxies `/api/*` requests to `http://127.0.0.1:5000`.

## Current Coverage

The current Gen2 build covers:

- campaign list, campaign home, published wiki sections, and published wiki pages
- Session player/character/DM panes
- Characters roster, character read/edit shell, native create/import lanes, Advanced Editor, DND-5E level-up, DND-5E retraining, Xianxia Cultivation, portrait controls, and Controls assignment/delete
- Combat player view, DM status, and DM controls
- DM Content statblocks, conditions, staged articles, Player Wiki, and Systems management lanes
- Systems browsing landing/search, source pages, source categories, and entry detail pages
- Account settings for theme and live-session chat-order preferences
- Campaign Help guidance, effective access, visibility notes, and Flask fallback links
- Campaign Control visibility editing for campaign and scope access floors

Flask remains the source of truth for workflows that are still Flask-first, including progression repair, Admin, shared/core Systems entry editing, and Systems imports.

## Build & Preview

```powershell
npm run typecheck
npm run build
```

The build outputs to `frontend/dist`.

The current Gen2 build is local-only: `frontend/dist` is intentionally ignored by Git and Docker context hygiene, and the Fly image does not yet run the frontend build stage. The Flask `/app-next/` route returns 404 until `frontend/dist` exists in the running app environment.

## Flask integration

- Flask serves the built Gen2 app at:
  - `GET /app-next/` -> `index.html`
  - `GET /app-next/<path>` -> static asset if present, otherwise SPA fallback to `index.html`.
- The build directory can be changed with `APP_NEXT_DIST_DIR` in Flask config.
- No legacy routes or templates are changed; this is intentionally side-by-side with the existing browser app.

## API Used By Gen2

The full API reference is maintained in `docs/api-v1.md`. The list below is a quick orientation for the original Session pilot path and should not be treated as exhaustive for the current Gen2 app.

- `GET /api/v1/app`
- `GET /api/v1/me`
- `GET /api/v1/me/settings`
- `PATCH /api/v1/me/settings`
- `GET /api/v1/campaigns`
- `GET /api/v1/campaigns/<campaign_slug>/control`
- `PATCH /api/v1/campaigns/<campaign_slug>/control/visibility`
- `GET /api/v1/campaigns/<campaign_slug>/help`
- `GET /api/v1/campaigns/<campaign_slug>/session`
- `POST /api/v1/campaigns/<campaign_slug>/session/start`
- `POST /api/v1/campaigns/<campaign_slug>/session/close`
- `POST /api/v1/campaigns/<campaign_slug>/session/messages`
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search?q=...`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles`
- `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/reveal`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed`
- `GET /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/image`
- `GET /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/search?q=...` (same-origin, browser route)
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/preview?page_ref=...` (same-origin, browser route)
- `GET /api/v1/campaigns/<campaign_slug>/characters`
- `GET /api/v1/campaigns/<campaign_slug>/characters/create`
- `POST /api/v1/campaigns/<campaign_slug>/characters/create`
- `GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `POST /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>`

The character create/import endpoints reuse the same backend DND-5E and Xianxia builders as Flask, including Xianxia manual import preview/confirm behavior. The Gen2 Advanced Editor route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/advanced-editor` to read and save the existing DND-5E native edit schema for proficiencies, reference text, campaign adjustments, recoverable penalties, custom features, and manual equipment. The Gen2 Level Up route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/level-up` to read and submit the existing DND-5E native one-level advancement context with stale revision checks and Flask repair fallbacks for repairable imports. The Gen2 Retraining route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/retraining` to read and save the existing bounded structured retraining context for persisted linked-feature choices while keeping repairable imports on the Flask progression-repair fallback. The Gen2 Cultivation route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/cultivation` to read the existing Xianxia advancement context and submit the same Insight, advancement-spend, Martial Art, Generic Technique, and Realm Ascension actions as Flask. Progression repair remains a Flask-backed authoring lane. The character detail response includes Gen2 presentation fields for DND-5E linked details: equipment rows, presented inventory items, and presented spellcasting spells carry source `href` values plus server-rendered `description_html` for the Session Character detail dialogs. The full Gen2 Character route can upload or remove the character portrait through the revision-checked portrait endpoints, and its Controls section now covers owner assignment/clear plus checked character deletion where permissions allow.

Authentication notes:

- Session polling and writes default to browser cookies using `same-origin` requests.
- Optional API token is supported in a local test field and sent as `Authorization: Bearer ...` when present.
- When an auth-gated call returns 401, the shell shows a clear recovery prompt to sign in and continue. Updating the API token field invalidates current queries so failed reads retry with the new token.
