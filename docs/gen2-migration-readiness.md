# Gen2 Migration Readiness

Gen2 frontend development is currently suspended. Flask is the active browser UI, and the Flask app intentionally closes `/app-next` and `/app-next/...` routes with 404 responses even when a `frontend/dist` build exists.

## Current Contract

- Account settings no longer expose a preferred-frontend selector.
- Campaign picker cards always open Flask campaign routes.
- Stored legacy `frontend_mode = "gen2"` preferences normalize back to `flask` when read.
- `GET /api/v1/me/settings` keeps the compatibility `preferences.frontend_mode` field, but it no longer advertises `frontend_mode_choices`.
- `PATCH /api/v1/me/settings` rejects `frontend_mode` writes with a validation error.
- The Gen2 browser acceptance suite is skipped while the routes are closed.

## Historical State

The React/Vite source remains under `frontend/` for possible future resumption. Before suspension, the Gen2 work had functional and visual-parity passes for the campaign picker, campaign home, published wiki browsing, Session, Characters, Combat, DM Content lanes, Systems browsing, Account settings, Campaign Help, Campaign Control, and Admin.

The JSON endpoints created for Gen2 remain in place where they are shared with current or future clients. Those endpoints should not be treated as evidence that the `/app-next` browser frontend is active.

## Resumption Checklist

Before reopening Gen2 routes:

- Restore an explicit hosting decision for `/app-next` in `player_wiki/app.py`.
- Decide whether the account-level frontend preference should return or whether Gen2 should be opened by direct route only.
- Re-enable and refresh `tests/test_frontend_gen2_session_browser.py`.
- Revisit `frontend/README.md` and this document with the current route matrix.
- Run focused API tests plus the relevant browser acceptance tests before exposing routes locally or on Fly.
