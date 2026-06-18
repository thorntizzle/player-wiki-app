# Gen2 Migration Readiness

Gen2 frontend development is currently suspended. Flask is the active browser UI, and the Flask app now hosts `/app-next` only in preview mode.

Preview mode is controlled by the following environment/config options:

- `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW` (default `false`)
- `PLAYER_WIKI_APP_NEXT_DIST_DIR` (default `<repo>/frontend/dist`)

With preview disabled (the default, and the production posture), `GET /app-next`, `GET /app-next/`, and `GET /app-next/<path>` return 404.

## Current Contract

- Account settings no longer expose a preferred-frontend selector.
- Campaign picker cards always open Flask campaign routes.
- Stored legacy `frontend_mode = "gen2"` preferences normalize back to `flask` when read.
- `GET /api/v1/me/settings` keeps the compatibility `preferences.frontend_mode` field, but it no longer advertises `frontend_mode_choices`.
- `PATCH /api/v1/me/settings` rejects `frontend_mode` writes with a validation error.
- Flask-hosted Gen2 browser routes stay closed by default; only preview users running with `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW=1` get route fallback behavior for built frontend assets.

## Historical State

The React/Vite source remains under `frontend/` for possible future resumption. Before suspension, the Gen2 work had functional and visual-parity passes for the campaign picker, campaign home, published wiki browsing, Session, Characters, Combat, DM Content lanes, Systems browsing, Account settings, Campaign Help, Campaign Control, and Admin.

The JSON endpoints created for Gen2 remain in place where they are shared with current or future clients. Those endpoints should not be treated as evidence that the `/app-next` browser frontend is active.

## Latest Preview Audit

On 2026-06-18, preview hosting was validated against a rebuilt Vite bundle after `tsc --noEmit` passed. The smoke audit covered the campaign picker, campaign home, section, article, Session, Characters roster/detail, Systems, Combat, DM Content, Help, Control, Account, and Admin routes with no browser console errors, page errors, unexpected auth prompts, or API error notices. Desktop `1280x900` and mobile `390x800` layout checks on the main route set reported no horizontal overflow or wide elements.

This is a preview-only audit. The skipped Gen2 browser acceptance suite still needs to be refreshed before treating Gen2 as route-promotion ready.

## Resumption Checklist

Before reopening Gen2 routes:

- Re-validate preview hosting behavior for `/app-next` in `player_wiki/app.py` (gated by `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW`).
- Decide whether the account-level frontend preference should return or whether Gen2 should be opened by direct route only.
- Re-enable and refresh `tests/test_frontend_gen2_session_browser.py`.
- Revisit `frontend/README.md` and this document with the current route matrix.
- Run focused API tests plus the relevant browser acceptance tests before exposing routes locally or on Fly.
