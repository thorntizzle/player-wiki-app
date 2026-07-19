# Flask Browser App

Last updated: 2026-07-19

## Owns

- Browser route ownership, Flask template shell behavior, loading cover behavior, browser/API link contracts, and the retired preview-route boundary.

## Current Contract

- Flask is the only committed browser frontend. Normal entry points, campaign navigation, account/admin pages, wiki pages, Session, Combat, DM Content, Systems, and Characters all use `/campaigns/...`, `/account`, and `/admin` Flask routes.
- `/app-next` routes are not registered. Requests to `/app-next`, `/app-next/`, assets under `/app-next`, or old campaign preview paths return 404.
- The retired preview source tree and build output are removed from the app repo. The Docker image is Python-only and does not build or copy a separate browser bundle.
- Account settings no longer expose a preferred-frontend selector. The compatibility `frontend_mode` preference field remains in SQLite/API payloads, normalizes to `flask`, and rejects writes.
- JSON endpoints remain available for Flask browser flows and future clients. Link fields now point to Flask routes; stale `/app-next` links in rendered wiki body HTML are rewritten back to `/campaigns/...`.
- `docs/contracts/route-access-policies.json` is the explicit endpoint-policy source for the Flask rewrite, and `scripts/generate_route_manifest.py` combines it with `create_app().url_map` using tracked sample campaigns. The committed generated manifest records browser/API/framework ownership, method, actor matrix, campaign scope, visibility and object relationships, system gates, View As behavior, and denial mode without inspecting private campaign data.
- The final Phase 3B ownership inventory is integrated on pushed `main` and deployed as Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. Release health endpoints and representative read-only browser/API smoke are green. No explicit database/content sync or private-data write accompanied the deploy, and the later documentation closeout is not part of the deployed image.
- The checked inventory has 299 Flask rules and 308 method/path contracts: 171 browser, 136 API, and 1 framework-owned static entry. Domain ownership is app shell 13 rules/13 contracts, Auth 13/15, Admin 30/30, Publishing 20/20, DM Content 25/25, Systems 33/33, Live Session 32/32, Combat 46/46, Characters 86/93, and framework 1/1. Each rule and method/path contract has one owner. Direct route decorators now number 26 in `app.py`, 35 in `api.py`, 1 in `auth.py`, and 14 in `admin.py`; extracted registrars own the remainder without changing supported endpoint identifiers, methods, order, or implicit method behavior.
- The app registers the `/api/v1` API Blueprint plus publishing, DM Content, Systems, and Session browser Blueprints and the extracted Character, Auth, Admin API, and campaign-visibility registrar families. Compatibility registration preserves supported bare Flask endpoint identifiers with exactly one registered rule per method/path. The Session layer owns 19 live-session browser handlers/rules, split into nine GET and ten POST rules. The Systems layer owns five read registrations, the source-policy and entry-override POST registrations, five custom-entry lifecycle registrations, the shared/core permission POST, the shared-entry edit GET and update POST, and the browser DND-5E import POST. Both Systems edit GETs keep implicit `HEAD` and `OPTIONS`; all extracted Systems POST registrations, including `campaign_systems_control_panel_import_dnd5e`, keep implicit `OPTIONS` without `HEAD`.
- `session_api_routes.py` adds 13 live-session rules and handlers to the existing API Blueprint rather than creating another Blueprint. They preserve their supported `api.*` endpoint identifiers, methods, implicit `HEAD`/`OPTIONS` behavior, authorization wrappers, payloads, and registration order where PUT and DELETE share the article path. `api.py` retains the Blueprint, shared request/auth/error helpers, Session serializers and composition, and registrar dependency wiring.
- `systems_api_routes.py` adds 16 rules for 15 Systems handlers to the existing API Blueprint rather than creating another Blueprint: eight GET rules for seven read handlers plus eight mutation handlers for source policy, entry overrides, custom-entry create/update/archive/restore, campaign item-mechanics import, and app-admin DND-5E ingest. The landing and search paths keep the shared `api.systems_index` identifier; every other handler keeps its existing bare `api.*` identifier, including `api.systems_import_run_list`, `api.systems_import_run_detail`, `api.systems_item_mechanics_import`, `api.systems_import_dnd5e`, and the four `api.systems_custom_entry_*` identifiers. The two app-admin-only import-run reads remain read-only GET rules with implicit `HEAD` and `OPTIONS`. Each method/path remains registered exactly once. The shared `/systems/sources` path continues to advertise GET, HEAD, OPTIONS, and PUT through automatic OPTIONS handling; the custom-entry, item-mechanics, and DND-5E ingest POST mutations retain implicit `OPTIONS` without `HEAD`.
- The shared loading cover remains in the Flask base template and may rotate visible campaign image assets when the viewer can access the wiki.
- Shared CSS and large page scripts are served from `player_wiki/static/` with content-digest `?v=` URLs. In production, immutable caching is granted only when that digest matches the served content; absent, stale, or bogus versions do not receive immutable caching.
- On the local `codex/flask-rewrite-phase5` branch only, the shared shell puts a `.skip-link` first in focus order and targets the named, programmatically focusable `#main-content` landmark. Shared presentation CSS supplies low-specificity native `:focus-visible`, the single `.visually-hidden` helper definition, `.state-panel` with `--empty` and `--error` modifiers, and `.action-group`.
- That local Phase 5 candidate adopts the state panel on two representative surfaces only: the Campaign Picker empty state and the global not-found recovery error. Both panels are statically labeled by headings and are not live regions; the not-found action group retains real links and navigation semantics.
- The local campaign shell remains one adaptive, role-aware shell. Its compact desktop secondary row places authorized campaign navigation beside global search; at `max-width: 820px` the row stacks and the navigation changes to an auto-fit grid (`821px` remains above the boundary and `820px` is at it). The mobile search form remains one row, and empty search status and results regions consume no initial height.
- The campaign navigation has a programmatic label and exactly one active real-href link carries both `.is-active` and `aria-current="page"`. Existing server-owned role filtering remains authoritative, and the shell does not expose View As controls. At the accepted `1280x900` and `390x800` matrix, campaign identity, authorized route navigation, global search, auth actions, the route `h1`, and the applicable primary action remain in the first viewport without horizontal overflow under the exercised signed-out, player, DM, and app-admin states across parchment and moonlit themes.
- The existing global-search controller and endpoint URLs are unchanged. Its labeled native dialog, live and busy feedback, dedicated-page link, Escape dismissal and result-focus return continue to work, and in-page search preview does not reveal the global loading cover. The accepted runtime/test state is exact local commit `92382045b4542ed18a3bb8728e01130271c4ae32` on `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.3a adds one shared feedback primitive with `data-feedback`, `data-feedback-placement` (`transient` or `persistent`), and `data-feedback-tone` (`success`, `info`, `warning`, or `error`). Tone owns announcement urgency independently of placement: success and info use polite atomic status semantics, while warning and error use assertive atomic alert semantics.
- Global Flask flashes use the shared primitive as transient, fixed, viewport-visible feedback. Their `data-flash-stack-root` remains after the header and before the named main landmark, is not itself a live region, and does not intercept pointer input. Existing Session, Combat, and Character replacement hooks keep replacing this root, but Slice 5.3a does not standardize Session live success/error, draft, focus, or viewport behavior; that adoption remains in Slice 5.3b.
- Account live-session chat order is the single synchronous representative. Valid changes and unchanged values retain native post/redirect/get success behavior; an invalid submission retains its `400` response and renders one persistent form-local error with stable description and invalid-state association, then restores focus to the choice group after loading. Native submission remains functional without JavaScript. Routes, methods, authorization and View As behavior, CSRF, CSP, private no-store responses, loading, mutation/audit behavior, event order, and Session/Combat/Character replacement compatibility are unchanged.
- Slice 5.3a exposes no timeout, retry, reconciliation, or private-journal browser state. That outcome gate remains deferred to Phase 7. Its accepted runtime/test state is exact local commit `22b2385b92ca038225f383b09a88fe405770ac64` on `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Each HTML response receives a fresh content-security-policy nonce for approved inline scripts and styles. Templates do not use inline event-handler attributes. Privacy and cache headers prevent storage of auth, token-bearing, account, and Admin HTML, while secure production responses add HSTS.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Route registration or access-contract changes must update the explicit policy map and regenerate the deterministic manifest; `python -B scripts/generate_route_manifest.py --check` and the `contract` pytest marker detect missing/stale endpoint policies, duplicate method/path registrations, API-reference drift, and generated-byte drift.
- Separate preview build, typecheck, and browser checks are no longer part of verification.
- Keep a direct assertion that representative `/app-next` routes return 404 so the removed preview surface does not drift back in accidentally.
- Local Phase 5 shared-primitive coverage lives in `tests/test_static_assets.py` for shell order, the skip target, focused-main behavior, selector ownership, and the representative desktop/mobile keyboard smoke; `tests/test_auth_and_wiki.py` covers the labeled, non-live Campaign Picker empty and global not-found error panels plus native recovery links. The independently accepted candidate passed its focused source/contract checks and browser matrix; the complete suite remains due at the assembled presentation-domain freeze.
- Local Slice 5.2 coverage in `tests/test_auth_and_wiki.py` checks role-filtered real-href navigation, order, and active-link semantics. `tests/test_static_assets.py` checks the exact `820px` CSS boundary and the `1280x900`, `390x800`, `821px`, and `820px` browser matrix, including first-viewport priorities, auth actions, themes, one-row search, empty-region height, horizontal overflow, skip/main focus, and the mobile search-dialog interaction. The independently accepted slice used focused and contract validation only; no complete suite was run, and full representative Phase 5/browser validation remains due at the assembled presentation-domain freeze.
- Local Slice 5.3a coverage in `tests/test_auth_and_wiki.py`, `tests/test_auth_account_session_chat_order_route_transport.py`, `tests/test_security_headers.py`, and `tests/test_static_assets.py` checks feedback semantics and root order, the Account valid/unchanged/invalid route contract, CSP and no-store preservation, live replacement compatibility, desktop and narrow-mobile placement and interaction, focus recovery, and native no-JavaScript submission. The independently accepted slice used focused and contract validation only; no complete suite was run. Feedback/CSP/test-infrastructure coverage and representative browser effects remain due at the assembled presentation-domain freeze.

## Source Pointers

- `player_wiki/app.py`
- `player_wiki/auth.py`
- `player_wiki/api.py`
- `player_wiki/systems_api_routes.py`
- `player_wiki/session_routes.py`
- `player_wiki/session_api_routes.py`
- `player_wiki/character_routes.py`
- `player_wiki/character_*_routes.py`
- `player_wiki/auth_*_routes.py`
- `player_wiki/admin_api_routes.py`
- `player_wiki/campaign_visibility_routes.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/dm_content_routes.py`
- `player_wiki/systems_routes.py`
- `player_wiki/security_headers.py`
- `player_wiki/templates/base.html`
- `player_wiki/templates/_feedback.html`
- `player_wiki/templates/_flash_stack.html`
- `player_wiki/templates/_campaign_global_search.html`
- `player_wiki/templates/_campaign_global_search_scripts.html`
- `player_wiki/templates/account_settings.html`
- `player_wiki/templates/_combat_status_live_scripts.html`
- `player_wiki/templates/campaign_picker.html`
- `player_wiki/templates/not_found.html`
- `player_wiki/auth_account_session_chat_order_routes.py`
- `player_wiki/static/styles.css`
- `player_wiki/static/session-live.js`
- `player_wiki/static/combat-live.js`
- `player_wiki/static/character-read-shell.js`
- `player_wiki/static/`
- `Dockerfile`
- `tests/test_auth_and_wiki.py`
- `tests/test_auth_account_session_chat_order_route_transport.py`
- `tests/test_security_headers.py`
- `tests/test_static_assets.py`
- `tests/test_api*.py`
