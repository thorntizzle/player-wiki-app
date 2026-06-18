# Gen2 Migration Readiness

Gen2 frontend development is open for gated preview again. Flask remains the active default and production browser UI, while the Flask app hosts `/app-next` only in preview mode.

Preview mode is controlled by the following environment/config options:

- `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW` (default `false`)
- `PLAYER_WIKI_APP_NEXT_DIST_DIR` (default `<repo>/frontend/dist`)

With preview disabled (the default, and the production posture), `GET /app-next`, `GET /app-next/`, and `GET /app-next/<path>` return 404.

## Current Contract

- Account settings no longer expose a preferred-frontend selector.
- Flask campaign picker cards continue to open Flask campaign routes; the Gen2 preview campaign picker opens `/app-next/campaigns/<slug>` direct preview routes.
- Stored legacy `frontend_mode = "gen2"` preferences normalize back to `flask` when read.
- `GET /api/v1/me/settings` keeps the compatibility `preferences.frontend_mode` field, but it no longer advertises `frontend_mode_choices`.
- `PATCH /api/v1/me/settings` rejects `frontend_mode` writes with a validation error.
- Flask-hosted Gen2 browser routes stay closed by default; only preview users running with `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW=1` get route fallback behavior for built frontend assets.
- Direct `/app-next` preview navigation forces Gen2 route mode for the shell, campaign picker, and published wiki links so preview sessions do not fall back to Flask merely because stored frontend preferences normalize to Flask.

## Historical State

The React/Vite source remains under `frontend/` and is active for gated preview. The Gen2 work has functional and visual-parity passes for the campaign picker, campaign home, published wiki browsing, Session, Characters, Combat, DM Content lanes, Systems browsing, Account settings, Campaign Help, Campaign Control, and Admin.

The JSON endpoints created for Gen2 remain in place where they are shared with current or future clients. Those endpoints should not be treated as evidence that the `/app-next` browser frontend is production-default; preview hosting is still gated by `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW`.

## Latest Preview Audit

On 2026-06-18, preview hosting was validated against a rebuilt Vite bundle after `tsc --noEmit` passed. The route smoke audit covered the campaign picker, campaign home, section, article, Session, Characters roster/detail, Systems, Combat, DM Content, Help, Control, Account, and Admin routes with no browser console errors, page errors, unexpected auth prompts, or API error notices. Desktop `1280x900` and mobile `390x800` layout checks on the main route set reported no horizontal overflow or wide elements.

The Gen2 browser acceptance suite was then refreshed and re-enabled. `tests/test_frontend_gen2_session_browser.py` now has 28 passing browser tests covering preview route loading, Session/Combat/DM Content/Systems/Character write flows, Account/Admin/Help/Control surfaces, route-mode preservation inside `/app-next`, desktop/mobile visual overflow checks, and visible Flask-fallback cleanup.

This is still a preview-only audit. Treat route promotion beyond gated preview as a separate decision that needs manual acceptance and deployment planning.

## Resumption Checklist

Before promoting Gen2 routes beyond gated preview:

- Re-validate preview hosting behavior for `/app-next` in `player_wiki/app.py` (gated by `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW`).
- Decide whether Gen2 should remain direct-route-only or whether an account-level/default route selector should return.
- Run a manual preview acceptance pass on the real local campaign data.
- Revisit `frontend/README.md` and this document with the current route matrix.
- Run focused API tests plus the relevant browser acceptance tests before exposing routes locally or on Fly.
