# Flask Browser App

Last updated: 2026-07-10

## Owns

- Browser route ownership, Flask template shell behavior, loading cover behavior, browser/API link contracts, and the retired preview-route boundary.

## Current Contract

- Flask is the only committed browser frontend. Normal entry points, campaign navigation, account/admin pages, wiki pages, Session, Combat, DM Content, Systems, and Characters all use `/campaigns/...`, `/account`, and `/admin` Flask routes.
- `/app-next` routes are not registered. Requests to `/app-next`, `/app-next/`, assets under `/app-next`, or old campaign preview paths return 404.
- The retired preview source tree and build output are removed from the app repo. The Docker image is Python-only and does not build or copy a separate browser bundle.
- Account settings no longer expose a preferred-frontend selector. The compatibility `frontend_mode` preference field remains in SQLite/API payloads, normalizes to `flask`, and rejects writes.
- JSON endpoints remain available for Flask browser flows and future clients. Link fields now point to Flask routes; stale `/app-next` links in rendered wiki body HTML are rewritten back to `/campaigns/...`.
- `docs/contracts/route-access-policies.json` is the explicit endpoint-policy source for the Flask rewrite, and `scripts/generate_route_manifest.py` combines it with `create_app().url_map` using tracked sample campaigns. The committed generated manifest records browser/API/framework ownership, method, actor matrix, campaign scope, visibility and object relationships, system gates, View As behavior, and denial mode without inspecting private campaign data.
- The checked inventory has 296 explicit route registrations (137 in `app.py`, 136 in `api.py`, 14 in `admin.py`, and 9 in `auth.py`) plus Flask's framework-owned static rule. Those registrations produce 305 explicit method/path pairs plus the static pair; nine registrations intentionally accept more than one explicit method. The API is the only Blueprint and no route is registered through `add_url_rule`.
- The shared loading cover remains in the Flask base template and may rotate visible campaign image assets when the viewer can access the wiki.
- Shared CSS and large page scripts are served from `player_wiki/static/` with content-hashed `?v=` URLs; templates should keep only small per-page data/configuration inline.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Route registration or access-contract changes must update the explicit policy map and regenerate the deterministic manifest; `python -B scripts/generate_route_manifest.py --check` and the `contract` pytest marker detect missing/stale endpoint policies, duplicate method/path registrations, API-reference drift, and generated-byte drift.
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
- `tests/test_api*.py`
