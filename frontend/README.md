# Gen2 Frontend

This React + TypeScript frontend is currently suspended. The source remains in place for possible future resumption, but Flask does not serve it: `/app-next` and `/app-next/...` intentionally return 404.

The suspension status and resumption checklist live in:

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
- Open `http://127.0.0.1:5173/app-next/` only for isolated Vite development. Flask-hosted `http://127.0.0.1:5000/app-next/` is closed while Gen2 is suspended.
- The Vite dev server proxies `/api/*` requests to `http://127.0.0.1:5000`.

## Historical Coverage

The suspended Gen2 build covered:

- campaign list, campaign home, published wiki sections, and published wiki pages
- Session player/character/DM panes
- Characters roster, character read/edit shell, native create/import lanes, Advanced Editor, DND-5E progression repair, DND-5E level-up, DND-5E retraining, Xianxia Cultivation, portrait controls, and Controls assignment/delete
- Combat player view, DM status, and DM controls
- DM Content statblocks, conditions, staged articles, Player Wiki, and Systems management lanes
- Systems browsing landing/search, source pages, source categories, and entry detail pages
- Account settings for theme and live-session chat-order preferences
- Admin dashboard and user-management operations
- Campaign Help guidance, effective access, visibility notes, and Flask fallback links
- Campaign Control visibility editing for campaign and scope access floors

Flask remains the source of truth for workflows that are still Flask-first or intentionally fallback-only, including shared/core Systems entry editing, Systems imports, and CLI/bootstrap recovery operations.

## Build & Preview

```powershell
npm run typecheck
npm run build
```

The build outputs to `frontend/dist`.

For local development, run `npm run build` after installing dependencies if you need to inspect the bundle directly. The Flask app currently ignores this build output for `/app-next` hosting.
`frontend/dist` is still ignored for local Git hygiene and is still excluded from the Docker build context by `.dockerignore` on source builds.

## Flask integration

- Flask returns 404 for `GET /app-next`, `GET /app-next/`, and `GET /app-next/<path>`.
- Account settings no longer include a preferred-frontend selector.
- Campaign picker cards always open Flask routes.

## Historical API Used By Gen2

The full API reference is maintained in `docs/api-v1.md`. The list below is historical orientation for the suspended Gen2 app and should not be treated as evidence that `/app-next` is currently hosted.

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

The character create/import endpoints reuse the same backend DND-5E and Xianxia builders as Flask, including Xianxia manual import preview/confirm behavior. The Gen2 Advanced Editor route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/advanced-editor` to read and save the existing DND-5E native edit schema for proficiencies, reference text, campaign adjustments, recoverable penalties, custom features, and manual equipment. The Gen2 Progression Repair route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/progression-repair` to read and save the existing imported-character repair context for baseline class/subclass/species/background links, prior feat/optional-feature backfills, and spell-row classification. The Gen2 Level Up route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/level-up` to read and submit the existing DND-5E native one-level advancement context with stale revision checks and Gen2 repair handoffs for repairable imports. The Gen2 Retraining route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/retraining` to read and save the existing bounded structured retraining context for persisted linked-feature choices while keeping repairable imports pointed at Gen2 progression repair. The Gen2 Cultivation route uses `/api/v1/campaigns/<slug>/characters/<characterSlug>/cultivation` to read the existing Xianxia advancement context and submit the same Insight, advancement-spend, Martial Art, Generic Technique, and Realm Ascension actions as Flask. The character detail response includes Gen2 presentation fields for DND-5E linked details: equipment rows, presented inventory items, and presented spellcasting spells carry source `href` values plus server-rendered `description_html` for the Session Character detail dialogs. The full Gen2 Character route can upload or remove the character portrait through the revision-checked portrait endpoints, and its Controls section now covers owner assignment/clear plus checked character deletion where permissions allow.

The Gen2 Admin route uses `/api/v1/admin` and `/api/v1/admin/users/<user_id>` to read the same dashboard, user-detail, membership, assignment, and audit contexts as the Flask Admin screen. Its mutations reuse the same auth-store operations and audit event metadata for invites, password resets, membership updates/removal, character assignment/clear, disable/enable, and checked user deletion while keeping the Flask Admin route available as a fallback.

Authentication notes:

- Session polling and writes default to browser cookies using `same-origin` requests.
- Optional API token is supported in a local test field and sent as `Authorization: Bearer ...` when present.
- When an auth-gated call returns 401, the shell shows a clear recovery prompt to sign in and continue. Updating the API token field invalidates current queries so failed reads retry with the new token.
