# Gen2 Migration Readiness

Gen2 is no longer the default browser frontend. Flask is the stable default again, while Flask still serves the Gen2 client at explicit `/app-next` URLs from the built `frontend/dist` bundle when `index.html` exists.

Hosting is controlled by the following environment/config options:

- `PLAYER_WIKI_ENABLE_APP_NEXT_PREVIEW` (default `true`; set `0`/`false` to disable explicit `/app-next` preview hosting)
- `PLAYER_WIKI_APP_NEXT_DIST_DIR` (default `<repo>/frontend/dist`)

Missing built assets and missing `index.html` still return 404. Explicit preview hosting does not make arbitrary missing files fall through to the SPA.

## Current Contract

- Account settings no longer expose a preferred-frontend selector.
- Root/single-campaign entry points and Flask campaign picker cards prefer Flask `/campaigns/<slug>` routes even when the Gen2 bundle is available.
- Stored legacy `frontend_mode = "flask"` preferences normalize to `gen2` when read.
- `GET /api/v1/me/settings` keeps the compatibility `preferences.frontend_mode` field, but it no longer advertises `frontend_mode_choices`.
- `PATCH /api/v1/me/settings` rejects `frontend_mode` writes with a validation error.
- Gen2 navigation keeps shell, campaign-picker, and published wiki links inside `/app-next`.
- Gen2 uses TanStack Router file-based route generation: `frontend/src/routes/**` owns thin route wrappers, `frontend/src/pages/**` owns page implementations, `frontend/src/routeTree.gen.ts` is committed generated output, and `frontend/src/main.tsx` bootstraps the generated route tree at the `/app-next` basepath.
- Direct Flask URLs such as `/campaigns/<slug>`, Flask picker links, and explicit `flask_*` API link fields are the stable browser paths.

## Historical State

The React/Vite source remains under `frontend/`. The Gen2 work has functional and visual-parity passes for the campaign picker, campaign home, published wiki browsing, Session, Characters, Combat, DM Content lanes, Systems browsing, Account settings, Campaign Help, Campaign Control, and Admin.

The JSON endpoints created for Gen2 remain in place where they are shared with current or future clients. Those endpoints support the explicit `/app-next` client, while Flask remains the stable browser surface for normal app entry.

## Latest Audit

On 2026-06-18, preview hosting was validated against a rebuilt Vite bundle after `tsc --noEmit` passed. The route smoke audit covered the campaign picker, campaign home, section, article, Session, Characters roster/detail, Systems, Combat, DM Content, Help, Control, Account, and Admin routes with no browser console errors, page errors, unexpected auth prompts, or API error notices. Desktop `1280x900` and mobile `390x800` layout checks on the main route set reported no horizontal overflow or wide elements.

The Gen2 browser acceptance suite was then refreshed and re-enabled. `tests/test_frontend_gen2_session_browser.py` has browser tests covering route loading, Session/Combat/DM Content/Systems/Character write flows, Account/Admin/Help/Control surfaces, route-mode preservation inside `/app-next`, desktop/mobile visual overflow checks, and visible Flask-fallback cleanup.

On 2026-06-24, the default promotion changed `/app-next` hosting to default-on, normalized the retired frontend preference to Gen2, and changed root/campaign-picker entry paths to prefer Gen2 while preserving Flask direct-route fallback.

Later on 2026-06-24, the Gen2 router was standardized around TanStack Router's file-based generator. The old manual route tree in `frontend/src/main.tsx` was replaced with the generated route tree, route wrappers moved to `frontend/src/routes/**`, and implementation-heavy route modules moved to `frontend/src/pages/**`. Verification for that pass included a Vite production build and the combined frontend/auth/API pytest suite.

On 2026-06-28, root and campaign-picker defaults were rolled back to Flask while preserving explicit `/app-next` hosting for direct Gen2 checks. The preferred-frontend account setting remains retired and legacy `frontend_mode` values still normalize to Gen2 for the compatibility API field.

## Resumption Checklist

Before future broad promotion or fallback-removal work:

- Re-validate explicit `/app-next` hosting behavior in `player_wiki/app.py`, including missing build and missing asset 404s.
- Run a manual acceptance pass on the real local campaign data.
- Revisit `frontend/README.md` and this document with the current route matrix.
- Run focused API tests plus the relevant browser acceptance tests before deploying route-surface changes on Fly.
