# Session Companion Pilot

This is a small React + TypeScript pilot surface served alongside the existing Flask/Jinja UI.

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

## Build & preview

```powershell
npm run typecheck
npm run build
```

The build outputs to `frontend/dist`.

The current pilot build is local-only: `frontend/dist` is intentionally ignored by Git and Docker context hygiene, and the Fly image does not yet run the frontend build stage. The Flask `/app-next/` route returns 404 until `frontend/dist` exists in the running app environment.

## Flask integration

- Flask serves the built pilot at:
  - `GET /app-next/` -> `index.html`
  - `GET /app-next/<path>` -> static asset if present, otherwise SPA fallback to `index.html`.
- The build directory can be changed with `APP_NEXT_DIST_DIR` in Flask config.
- No legacy routes or templates are changed; this is intentionally side-by-side with the existing browser app.

## API used by the pilot

- `GET /api/v1/app`
- `GET /api/v1/campaigns`
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
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>`

Authentication notes:

- Session polling and writes default to browser cookies using `same-origin` requests.
- Optional API token is supported in a local test field and sent as `Authorization: Bearer ...` when present.
- When an auth-gated call returns 401, the shell shows a clear recovery prompt to sign in and continue.
