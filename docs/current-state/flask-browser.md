# Flask Browser App

Last updated: 2026-07-12

## Owns

- Browser route ownership, Flask template shell behavior, loading cover behavior, browser/API link contracts, and the retired preview-route boundary.

## Current Contract

- Flask is the only committed browser frontend. Normal entry points, campaign navigation, account/admin pages, wiki pages, Session, Combat, DM Content, Systems, and Characters all use `/campaigns/...`, `/account`, and `/admin` Flask routes.
- `/app-next` routes are not registered. Requests to `/app-next`, `/app-next/`, assets under `/app-next`, or old campaign preview paths return 404.
- The retired preview source tree and build output are removed from the app repo. The Docker image is Python-only and does not build or copy a separate browser bundle.
- Account settings no longer expose a preferred-frontend selector. The compatibility `frontend_mode` preference field remains in SQLite/API payloads, normalizes to `flask`, and rejects writes.
- JSON endpoints remain available for Flask browser flows and future clients. Link fields now point to Flask routes; stale `/app-next` links in rendered wiki body HTML are rewritten back to `/campaigns/...`.
- `docs/contracts/route-access-policies.json` is the explicit endpoint-policy source for the Flask rewrite, and `scripts/generate_route_manifest.py` combines it with `create_app().url_map` using tracked sample campaigns. The committed generated manifest records browser/API/framework ownership, method, actor matrix, campaign scope, visibility and object relationships, system gates, View As behavior, and denial mode without inspecting private campaign data.
- The checked inventory has 298 explicit URL rules (108 decorator registrations in `app.py`, 136 in `api.py`, 14 in `admin.py`, 9 in `auth.py`, 9 publishing registrations, 6 DM Content registrations, and 16 Systems registrations) plus Flask's framework-owned static rule, for 299 total rules. Those registrations produce 307 explicit method/path entries plus the static entry, for 308 total: 171 browser, 136 API, and 1 framework entry.
- The app registers the `/api/v1` API Blueprint plus publishing, DM Content, and Systems browser Blueprints. The three browser Blueprints use explicit `add_url_rule` compatibility layers for their extracted routes so supported bare Flask endpoint identifiers remain unchanged, with exactly one registered rule per method/path. The Systems layer owns five read registrations, the source-policy and entry-override POST registrations, five custom-entry lifecycle registrations, the shared/core permission POST, the shared-entry edit GET and update POST, and the browser DND-5E import POST. Both edit GETs keep implicit `HEAD` and `OPTIONS`; all extracted Systems POST registrations, including `campaign_systems_control_panel_import_dnd5e`, keep implicit `OPTIONS` without `HEAD`.
- The shared loading cover remains in the Flask base template and may rotate visible campaign image assets when the viewer can access the wiki.
- Shared CSS and large page scripts are served from `player_wiki/static/` with content-digest `?v=` URLs. In production, immutable caching is granted only when that digest matches the served content; absent, stale, or bogus versions do not receive immutable caching.
- Each HTML response receives a fresh content-security-policy nonce for approved inline scripts and styles. Templates do not use inline event-handler attributes. Privacy and cache headers prevent storage of auth, token-bearing, account, and Admin HTML, while secure production responses add HSTS.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Route registration or access-contract changes must update the explicit policy map and regenerate the deterministic manifest; `python -B scripts/generate_route_manifest.py --check` and the `contract` pytest marker detect missing/stale endpoint policies, duplicate method/path registrations, API-reference drift, and generated-byte drift.
- Separate preview build, typecheck, and browser checks are no longer part of verification.
- Keep a direct assertion that representative `/app-next` routes return 404 so the removed preview surface does not drift back in accidentally.

## Source Pointers

- `player_wiki/app.py`
- `player_wiki/auth.py`
- `player_wiki/api.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/dm_content_routes.py`
- `player_wiki/systems_routes.py`
- `player_wiki/security_headers.py`
- `player_wiki/templates/base.html`
- `player_wiki/static/`
- `Dockerfile`
- `tests/test_auth_and_wiki.py`
- `tests/test_api*.py`
