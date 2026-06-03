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
- `POST /api/v1/campaigns/<campaign_slug>/session/messages`
