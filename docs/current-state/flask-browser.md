# Flask Browser App

Last updated: 2026-07-09

## Owns

- Browser route ownership, Flask template shell behavior, loading cover behavior, browser/API link contracts, and the retired preview-route boundary.

## Current Contract

- Flask is the only committed browser frontend. Normal entry points, campaign navigation, account/admin pages, wiki pages, Session, Combat, DM Content, Systems, and Characters all use `/campaigns/...`, `/account`, and `/admin` Flask routes.
- `/app-next` routes are not registered. Requests to `/app-next`, `/app-next/`, assets under `/app-next`, or old campaign preview paths return 404.
- The retired preview source tree and build output are removed from the app repo. The Docker image is Python-only and does not build or copy a separate browser bundle.
- Account settings no longer expose a preferred-frontend selector. The compatibility `frontend_mode` preference field remains in SQLite/API payloads, normalizes to `flask`, and rejects writes.
- JSON endpoints remain available for Flask browser flows and future clients. Link fields now point to Flask routes; stale `/app-next` links in rendered wiki body HTML are rewritten back to `/campaigns/...`.
- The shared loading cover remains in the Flask base template and may rotate visible campaign image assets when the viewer can access the wiki.
- Shared CSS and large page scripts are served from `player_wiki/static/` with content-hashed `?v=` URLs; templates should keep only small per-page data/configuration inline.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Separate preview build, typecheck, and browser checks are no longer part of verification.
- Keep a direct assertion that representative `/app-next` routes return 404 so the removed preview surface does not drift back in accidentally.

## Source Pointers

- `player_wiki/app.py`
- `player_wiki/auth.py`
- `player_wiki/api.py`
- `player_wiki/templates/base.html`
- `player_wiki/static/`
- `Dockerfile`
- `tests/test_auth_and_wiki.py`
- `tests/test_api.py`
