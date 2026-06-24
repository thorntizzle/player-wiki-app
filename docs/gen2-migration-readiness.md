# Gen2 Migration Readiness

Gen2 is now the default browser frontend. Flask serves `/app-next` from the built `frontend/dist` bundle by default when `index.html` exists, and direct Flask campaign routes remain available as compatibility URLs.

Hosting is controlled by the following environment/config options:

- `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW` (default `true`; set `0`/`false` as a temporary kill switch)
- `PLAYER_WIKI_APP_NEXT_DIST_DIR` (default `<repo>/frontend/dist`)

Missing built assets and missing `index.html` still return 404. The default promotion does not make arbitrary missing files fall through to the SPA.

## Current Contract

- Account settings no longer expose a preferred-frontend selector.
- Root/single-campaign entry points and Flask campaign picker cards prefer `/app-next/campaigns/<slug>` when the Gen2 bundle is available.
- Stored legacy `frontend_mode = "flask"` preferences normalize to `gen2` when read.
- `GET /api/v1/me/settings` keeps the compatibility `preferences.frontend_mode` field, but it no longer advertises `frontend_mode_choices`.
- `PATCH /api/v1/me/settings` rejects `frontend_mode` writes with a validation error.
- Gen2 navigation keeps shell, campaign-picker, and published wiki links inside `/app-next`.
- Direct Flask URLs such as `/campaigns/<slug>`, Flask picker links when Gen2 hosting is disabled, and explicit `flask_*` API link fields remain compatibility paths.

## Historical State

The React/Vite source remains under `frontend/`. The Gen2 work has functional and visual-parity passes for the campaign picker, campaign home, published wiki browsing, Session, Characters, Combat, DM Content lanes, Systems browsing, Account settings, Campaign Help, Campaign Control, and Admin.

The JSON endpoints created for Gen2 remain in place where they are shared with current or future clients. Those endpoints are now part of the default `/app-next` browser surface, while Flask remains the fallback for direct compatibility routes and still-owned admin/import lanes.

## Latest Audit

On 2026-06-18, preview hosting was validated against a rebuilt Vite bundle after `tsc --noEmit` passed. The route smoke audit covered the campaign picker, campaign home, section, article, Session, Characters roster/detail, Systems, Combat, DM Content, Help, Control, Account, and Admin routes with no browser console errors, page errors, unexpected auth prompts, or API error notices. Desktop `1280x900` and mobile `390x800` layout checks on the main route set reported no horizontal overflow or wide elements.

The Gen2 browser acceptance suite was then refreshed and re-enabled. `tests/test_frontend_gen2_session_browser.py` has browser tests covering route loading, Session/Combat/DM Content/Systems/Character write flows, Account/Admin/Help/Control surfaces, route-mode preservation inside `/app-next`, desktop/mobile visual overflow checks, and visible Flask-fallback cleanup.

On 2026-06-24, the default promotion changed `/app-next` hosting to default-on, normalized the retired frontend preference to Gen2, and changed root/campaign-picker entry paths to prefer Gen2 while preserving Flask direct-route fallback.

## Resumption Checklist

Before future broad promotion or fallback-removal work:

- Re-validate default `/app-next` hosting behavior in `player_wiki/app.py`, including missing build and missing asset 404s.
- Run a manual acceptance pass on the real local campaign data.
- Revisit `frontend/README.md` and this document with the current route matrix.
- Run focused API tests plus the relevant browser acceptance tests before deploying route-surface changes on Fly.
