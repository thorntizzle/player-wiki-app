# Flask Browser App

Last updated: 2026-07-20

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
- Local Slice 5.4 adds one same-origin, content-versioned external presentation controller for generic dialog mechanics. It accepts either the document or an inserted element as its initialization scope, initializes each opted-in dialog once, requires a non-empty `aria-label` or valid `aria-labelledby`, uses native modal open/close behavior (including Escape and focus containment), closes from an opted-in Close control or backdrop, moves focus to an explicitly marked initial control, and returns focus only to a still-connected invoker. Repeated initialization, an already-open dialog, and a detached invoker remain safe; browsers without the native methods receive only a bounded `open`/`close` fallback.
- Global search is the first adopter from Slice 5.4. Its inline domain controller still owns browser search and preview fetches, cancellation/debounce, status/results/error rendering, preview insertion, and live and busy updates; the shared controller owns only the dialog lifecycle. Flask routes retain authorization and access filtering, while the server/template pipeline retains `safe_rich_html` preview sanitization and the real dedicated-page link. Query, viewport, theme, and loading behavior are preserved. The shared controller can initialize a later inserted element, but Slice 5.4 does not claim that global search itself is fragment-replaced. The native search form can submit without JavaScript, but there is no supported no-JavaScript search-results fallback and this slice does not invent one; existing real links and domain no-JavaScript fallbacks elsewhere remain unchanged.
- The external controller loads synchronously immediately before the existing nonce-bearing global-search adopter script. The CSP policy is unchanged: the checked template inventory contains 15 inline scripts in 14 templates, five external scripts, and no inline event handlers. Routes, API and access contracts, domain content, loading, theme, focus, draft, and viewport contracts are otherwise unchanged. Slice 5.4 did not migrate the then-existing Character, Combat, or Session dialog controllers; native `details` remains preferred when sufficient, and each later adopter requires a separate independently verified rollback unit. The accepted Slice 5.4 runtime/test state is exact local commit `160a0e2a26311601e4c179eb988d4d91d1d62e9c`, tree `e946e39fa2b52173f65f11b76ed18af1e85c0971`, on `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.5 adds one shared Jinja destructive-confirmation presentation primitive on top of that accepted external dialog lifecycle. The first bounded adopters are DM Combat's lower-risk `Remove combatant` action and higher-risk `Clear tracker` action. Both confirmations name the action and affected encounter scope, distinguish encounter-owned cleanup from unchanged character sheets and source records, and retain real CSRF-protected POST forms. Remove requires the trigger plus one final confirmation; Clear additionally requires an explicit acknowledgement before its final submit. Cancel, Escape, and backdrop dismissal return focus to the still-connected trigger.
- JavaScript-enabled Combat owns form submission, busy state, known server feedback, response rendering, and idempotent reinitialization after its authority or controls fragments are replaced; the shared presentation controller still owns only generic dialog mechanics. A non-2xx response, network failure, or malformed response exposes persistent local guidance that the result could not be confirmed and focuses it without claiming success, failure, rollback, or journal state. A controller-known success or failure retains the existing global transient feedback path. The no-JavaScript path exposes the same scope and consequence in native `details`, then submits the real POST form.
- Slice 5.5 changes no route, API, authorization, CSRF, service/store, persistence-order, loading, CSP, security, theme, focus/draft/viewport, or deletion-policy contract. Other destructive workflows are not adopters yet. Its independently accepted runtime/test state is exact local commit `7311ba8c5b0774cb8e536c4ca43c658bcb2aec7b`, tree `38eb0aa83c05dc3d0d65269d360e430186778674`, on local `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.6a makes normal DND-5E Character read-shell item, prepared-spell, and current-spell detail dialogs the next bounded adopter of the accepted shared presentation lifecycle. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Character retains sheet content and real links, page/mode query and History state, panel cache, draft and submitted values, focus and viewport restoration, access, and scoped initialization through its existing panel initializer after initial, cached, subpage, or mutation-response insertion. Dialogs have unique resolved heading labels, and the legacy Character data hooks remain for domain selectors and compatibility.
- If the shared controller or its `init` function is absent, Character leaves the trigger templates inert: no ancestor gate is created, no unavailable state is set, the native fallback remains visible, and the `spell-modal-js` enhancement class is not activated. When `init` is present, Character clones dialog triggers into hidden ancestor gates and makes them available only after scoped initialization enables every trigger. A present `init` that returns without enabling them or throws leaves the gates hidden, marks the scope unavailable, keeps the native fallback visible, and does not activate `spell-modal-js`; later Character initialization continues. With JavaScript disabled, spells retain native detail disclosures and items retain noscript detail content, real reference links, and direct subpage navigation.
- Slice 5.6a changes no shared controller, CSS, base-template or CSP ordering, route/API/method, authorization or View As, CSRF, presenter/service/store, storage, persistence or mutation, recovery, loading, theme, Session, Combat, or product-policy contract. Its independently accepted runtime/test state is exact local commit `67a57d48d5c9ec1fafaeb6a673da8d3804bb2f2e`, tree `a446f5f53263c7dd42faf6a8225131ac7db68daf`, on local `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live. Other Character, Combat, and Session dialog surfaces remain outside this adopter unit.
- Local Slice 5.6b makes DND-5E Session Character item and spell detail dialogs the next bounded adopter of the accepted shared presentation lifecycle. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Session retains content and real links, native fallbacks, its scoped workspace initializer after initial, lazy, or mutation-response fragment insertion, query and History state, draft, focus, viewport, mounted Session, and polling behavior. Every dialog keeps a unique resolved heading label.
- If the shared controller or its `init` function is absent, Session Character leaves trigger templates inert without creating gates or setting an unavailable state; native item and spell fallbacks stay visible, and `spell-modal-js` is not activated. When `init` is present, triggers remain in hidden gates until every trigger is enabled. A present `init` that no-ops or throws leaves the gates hidden, marks the Session Character scope unavailable, preserves the fallbacks, does not activate `spell-modal-js`, and does not prevent later Session sections or forms from initializing. Successful scoped initialization exposes the triggers atomically and remains idempotent.
- Slice 5.6b changes no shared controller, CSS, base template, spell partial, Session shell or live controller, CSP/static ordering, route/API/method, access, authorization or View As, CSRF, service/store, storage, persistence, mutation, polling, loading, theme, or Combat contract. Combat selected-PC dialogs remained outside that adopter unit and are adopted separately by Slice 5.6d below. Its independently accepted runtime/test state is exact local commit `db6d0d7aac1eb81bc053b8fe8873843c76a43111`, tree `f7f09ec0ce22799df21ec916bdc3954f9e7393c3`, on local `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.6c makes only Session's `Clear all` revealed-articles
  workflow the next bounded adopter of the accepted shared
  destructive-confirmation and dialog presentation. The higher-risk dialog
  names the action, current article count, and scope: all revealed session
  articles and related reveal chat and log entries are removed, while staged
  articles remain unchanged. The acknowledgement is client-side only; the
  real CSRF-protected POST form remains the native no-JavaScript fallback.
- The shared presentation controller owns generic dialog lifecycle and focus
  return. The Session controller owns async submission, busy state, existing
  known feedback, and scoped reinitialization after the revealed-articles root
  is replaced. A known `ok: false` payload keeps global feedback without
  unknown-result recovery. Non-2xx, network, or malformed responses expose and
  focus guidance that the result could not be confirmed and that Session must
  be refreshed before repeating, without claiming success, failure, rollback,
  or journal state.
- Slice 5.6c changes no shared primitive, route/API/method, manager access,
  authorization or View As, CSRF, service/store, storage, transaction,
  revision, persistence ordering, deletion policy, polling, open-details,
  focus, viewport, composer draft, query, loading, theme, or CSP/static-order
  contract. Other Session destructive workflows remain separate. Combat selected-PC dialogs
  remained outside that unit and are adopted separately by Slice 5.6d below. Its independently
  accepted runtime/test state is exact local commit
  `1079dce2a1c024802c328db9e4fa92336ca30cbc`, tree
  `4363e7152659abf96401e0df6f557dfba222d236`, on local
  `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.6d makes selected-PC item and spell detail dialogs in player Combat,
  compatibility Combat Character, canonical DM Status, and compatibility `/combat/status` the next
  bounded adopters of the accepted shared presentation lifecycle. The shared controller owns the
  generic trigger and native modal lifecycle: open, Close/Escape/backdrop dismissal, initial Close
  focus, and focus return only to a still-connected invoker. Dialog headings remain uniquely
  resolved.
- The Combat workspace initializer owns scoped fail-safe gating and shared-controller retry after
  the initial mount and through its existing `init` and `restore` seams, including canonical and
  compatibility DM selected-detail replacements. Missing, no-op, or throwing shared initialization
  leaves trigger templates inert or gates hidden, keeps native item and spell details visible, and
  does not activate `spell-modal-js`; a later successful initialization can recover the scope.
  Legacy Combat direct dialog listeners exclude the adopted scope. Session Character initialization
  and Character/Session controller ownership are unchanged.
- Slice 5.6d preserves real item links and does not invent a dedicated spell link. JavaScript-disabled
  item and spell disclosures remain available. It changes no query, hash, selected section, focus,
  draft, viewport, carousel, polling, loading, theme, access, form, CSRF, CSP, static-order, route,
  API, method, authorization, View As, presenter/service/store, storage, persistence, or mutation
  contract. Its independently accepted runtime/test state is exact local commit
  `c0a442a275b8d7513a82f53cef9a8161cb8f67d8`, tree
  `4fd26d9c16c37ae35284f47d4eacf74ce73288ee`, on local
  `codex/flask-rewrite-phase5` only; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.3a adds one shared feedback primitive with `data-feedback`, `data-feedback-placement` (`transient` or `persistent`), and `data-feedback-tone` (`success`, `info`, `warning`, or `error`). Tone owns announcement urgency independently of placement: success and info use polite atomic status semantics, while warning and error use assertive atomic alert semantics.
- Global Flask flashes use the shared primitive as transient, fixed, viewport-visible feedback. Their `data-flash-stack-root` remains after the header and before the named main landmark, is not itself a live region, and does not intercept pointer input. Existing Session, Combat, and Character replacement hooks keep replacing this root.
- Account live-session chat order is the single synchronous representative. Valid changes and unchanged values retain native post/redirect/get success behavior; an invalid submission retains its `400` response and renders one persistent form-local error with stable description and invalid-state association, then restores focus to the choice group after loading. Native submission remains functional without JavaScript. Routes, methods, authorization and View As behavior, CSRF, CSP, private no-store responses, loading, mutation/audit behavior, event order, and Session/Combat/Character replacement compatibility are unchanged.
- Slice 5.3a exposes no timeout, retry, reconciliation, or private-journal browser state. That outcome gate remains deferred to Phase 7. Its accepted runtime/test state is exact local commit `22b2385b92ca038225f383b09a88fe405770ac64` on `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Local Slice 5.3b makes the Session message composer the representative asynchronous adopter. A successful enhanced post keeps one global transient, polite success path, replaces and clears the composer, and restores usable textarea focus. A controller-exposed validation response with `ok: false` instead keeps one form-local persistent, assertive shared-feedback path, associates the form with a stable description, and marks only the form invalid; it does not infer field errors. The mounted composer retains its draft, focus, selection, and visual viewport anchor, including across a Session identity change, and the controller suppresses its final anchor scroll. Success and validation transitions do not populate both feedback roots.
- The existing Session `requestInFlight` state now exposes form `aria-busy` and disables submit controls without mounting the full-page or live loader. HTTP `503` and network-failure exits restore controls and retain the mounted form state without inventing retry or error copy. Native no-JavaScript POST remains the fallback. Routes, API payload schema, authorization and View As behavior, CSRF, CSP, private no-store responses, loading and polling ownership, mutation/audit behavior, and event order remain unchanged. No timeout, retry, reconciliation, or private-journal outcome is standardized; Phase 7 remains the outcome gate. The accepted runtime/test state is exact local commit `f1118200daa3a3b7a0620b17d53c9e2cf00524f1` on `codex/flask-rewrite-phase5`; it is not on `main`, pushed, deployed, or live.
- Each HTML response receives a fresh content-security-policy nonce for approved inline scripts and styles. Templates do not use inline event-handler attributes. Privacy and cache headers prevent storage of auth, token-bearing, account, and Admin HTML, while secure production responses add HSTS.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Route registration or access-contract changes must update the explicit policy map and regenerate the deterministic manifest; `python -B scripts/generate_route_manifest.py --check` and the `contract` pytest marker detect missing/stale endpoint policies, duplicate method/path registrations, API-reference drift, and generated-byte drift.
- Separate preview build, typecheck, and browser checks are no longer part of verification.
- Keep a direct assertion that representative `/app-next` routes return 404 so the removed preview surface does not drift back in accidentally.
- Local Phase 5 shared-primitive coverage lives in `tests/test_static_assets.py` for shell order, the skip target, focused-main behavior, selector ownership, and the representative desktop/mobile keyboard smoke; `tests/test_auth_and_wiki.py` covers the labeled, non-live Campaign Picker empty and global not-found error panels plus native recovery links. The independently accepted candidate passed its focused source/contract checks and browser matrix; the complete suite remains due at the assembled presentation-domain freeze.
- Local Slice 5.2 coverage in `tests/test_auth_and_wiki.py` checks role-filtered real-href navigation, order, and active-link semantics. `tests/test_static_assets.py` checks the exact `820px` CSS boundary and the `1280x900`, `390x800`, `821px`, and `820px` browser matrix, including first-viewport priorities, auth actions, themes, one-row search, empty-region height, horizontal overflow, skip/main focus, and the mobile search-dialog interaction. The independently accepted slice used focused and contract validation only; no complete suite was run, and full representative Phase 5/browser validation remains due at the assembled presentation-domain freeze.
- Local Slice 5.3a coverage in `tests/test_auth_and_wiki.py`, `tests/test_auth_account_session_chat_order_route_transport.py`, `tests/test_security_headers.py`, and `tests/test_static_assets.py` checks feedback semantics and root order, the Account valid/unchanged/invalid route contract, CSP and no-store preservation, live replacement compatibility, desktop and narrow-mobile placement and interaction, focus recovery, and native no-JavaScript submission. The independently accepted slice used focused and contract validation only; no complete suite was run. Feedback/CSP/test-infrastructure coverage and representative browser effects remain due at the assembled presentation-domain freeze.
- Local Slice 5.3b coverage in `tests/test_campaign_session_page.py` checks the Session composer structure, shared-feedback routing, and controller-exposed busy/invalid states. `tests/test_character_read_shell_browser.py` checks the accepted `1280x900` parchment and `390x800` moonlit success, validation, delayed-response, HTTP/network failure, and native no-JavaScript paths, including focus, draft, selection, viewport, loader, and single-feedback-root behavior. The independently accepted slice used focused and contract validation only; no complete suite was run. Full Phase 5 presentation-domain validation remains due at the assembled presentation-domain freeze.
- Local Slice 5.4 source coverage in `tests/test_static_assets.py` checks controller ownership, explicit labeling, scoped and idempotent initialization, native and fallback lifecycle, connected/detached invokers, the sole-adopter boundary, content-versioned asset delivery, preserved search-domain code, and script ordering. Its browser coverage exercises the Global Search adopter at `1280x900` parchment and `390x800` moonlit for keyboard opening, native modality, explicit initial focus, Close/Escape/backdrop dismissal, focus return, query/scroll retention, dedicated-page navigation, theme, loading, and overflow; a separate inserted-element scenario challenges repeat initialization and detached-invoker safety. `tests/test_security_headers.py` fixes the CSP inventory at 15 inline scripts across 14 templates and five external scripts with no event handlers. The independently accepted slice used focused source, contract, and browser validation only; no complete suite was run. Shared JavaScript, CSP, static-asset, and representative browser coverage remain due at the assembled presentation-domain freeze.
- Local Slice 5.5 coverage in `tests/test_campaign_combat_page.py`, `tests/test_combat_dm_controls_browser.py`, and `tests/test_static_assets.py` checks proportional scope and confirmation strength, real CSRF POST fallbacks, authorization boundaries, dependent-row cleanup, unchanged source records, round/current-turn reset, cancel/Escape/backdrop focus return, fragment reinitialization, known server feedback, ambiguous transport guidance, busy state, theme, loading exclusion, and JavaScript-disabled forms. Independent verification passed 55 focused source/API/security/route tests, eight committed browser tests, five adversarial browser tests, and the 138-test contract marker selection with no final failures or skips. No complete suite was run; promotion remains due at the assembled Phase 5 presentation-domain freeze.
- Local Slice 5.6a coverage in `tests/test_character_read_routes.py`, `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py` checks scoped and repeated initialization after Character panel insertion, explicit dialog labels, Close/Escape/backdrop focus return, read-shell query/History/cache behavior, draft and viewport preservation, loading exclusion, desktop parchment and mobile moonlit presentation, native no-JavaScript content and links, and hidden trigger gates under no-op or throwing shared initialization. Independent verification passed 156 focused source/route/access/security tests with two Windows symlink skips, nine browser tests, three adversarial controller challenges, and the 138-test contract selection with no final failures; focused durable integration smoke also passed five tests plus the 138-test contract selection. No complete suite was run, and promotion remains due at the assembled Phase 5 presentation-domain freeze.
- Local Slice 5.6b coverage in `tests/test_campaign_session_page.py`, `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py` checks Session Character dialog structure, initial/lazy/mutation insertion, unique labels, keyboard and focus behavior, query/History/draft/viewport and mounted-Session preservation, no-JavaScript fallbacks, fail-safe gates, idempotence, loading exclusion, and legacy Combat isolation. Independent verification passed 439 broad affected tests with one unrelated loading-cover timing failure that passed its isolated rerun, all 226 Session tests, five candidate browser/adversarial tests, three Session regressions, six legacy Combat tests, and the 138-test contract selection with 4,531 deselected. Exact-integration checks passed eight focused tests plus the same 138-test contract selection. No complete suite was run; promotion remains due at the assembled Phase 5 presentation-domain freeze.
- Local Slice 5.6c coverage in `tests/test_campaign_session_page.py`,
  `tests/test_character_read_shell_browser.py`, and
  `tests/test_static_assets.py` checks Session clear-revealed scope and
  confirmation strength, native CSRF submission, shared-dialog focus behavior,
  async replacement/reinitialization, busy and known/unknown result paths,
  preserved Session state, and shared/static/legacy-Combat controls.
  Independent verification passed all 226 Session owner tests, two committed
  browser tests, one corrected independent double-submit/detached-success
  challenge, ten shared/static/legacy-Combat controls, and the 138-test contract
  selection with 4,534 deselected. Exact-integration checks used the canonical
  Python 3.12.12 environment with all 29 locked dependencies and passed four
  focused tests plus the same 138-test contract selection. No complete suite
  was run; promotion remains due at the assembled Phase 5 presentation-domain
  freeze.
- Local Slice 5.6d coverage in `tests/test_campaign_combat_page.py`,
  `tests/test_combat_dm_controls_browser.py`, `tests/test_static_assets.py`, and
  `tests/test_security_headers.py` checks the four Combat surfaces, scoped initial and replacement
  initialization, native lifecycle and focus, fail-safe recovery, no-JavaScript details and real item
  link, legacy listener isolation, Session regression boundaries, access/security/route preservation,
  and maintained static adopter ownership. Independent verification rejected exact parent
  `b858b27a6172a40267bb23e6a9b20e1df0dbadb0` only for the stale maintained adopter allowlist;
  repaired `c0a442a275b8d7513a82f53cef9a8161cb8f67d8` added only the missing allowlist entry and received
  `ACCEPT`. Fresh repaired checks passed the one former failure, four lifecycle static checks, three
  security/route checks, one Combat browser check, four Session browser checks, and all 138 contract
  tests. The rejected parent's broader 148-test Combat run and one adversarial browser check are
  supporting evidence only. Exact integration passed nine canonical focused/browser checks and the
  same 138 contract tests. No complete suite was run; promotion remains due at the assembled Phase 5
  presentation-domain freeze.

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
- `player_wiki/templates/_destructive_confirmation.html`
- `player_wiki/templates/_session_revealed_articles_card.html`
- `player_wiki/templates/character_read.html`
- `player_wiki/templates/_character_spellcasting_section.html`
- `player_wiki/templates/_session_character_dnd_workspace.html`
- `player_wiki/templates/_combat_player_workspace_sections.html`
- `player_wiki/templates/_combat_workspace_scripts.html`
- `player_wiki/templates/_combat_dm_controls.html`
- `player_wiki/templates/_combat_dm_selected_authority.html`
- `player_wiki/templates/account_settings.html`
- `player_wiki/templates/_session_composer_card.html`
- `player_wiki/templates/_combat_status_live_scripts.html`
- `player_wiki/templates/campaign_picker.html`
- `player_wiki/templates/not_found.html`
- `player_wiki/auth_account_session_chat_order_routes.py`
- `player_wiki/static/styles.css`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/static/session-live.js`
- `player_wiki/static/combat-live.js`
- `player_wiki/static/character-read-shell.js`
- `player_wiki/static/`
- `Dockerfile`
- `tests/test_auth_and_wiki.py`
- `tests/test_auth_account_session_chat_order_route_transport.py`
- `tests/test_security_headers.py`
- `tests/test_static_assets.py`
- `tests/test_campaign_session_page.py`
- `tests/test_character_read_shell_browser.py`
- `tests/test_campaign_combat_page.py`
- `tests/test_combat_dm_controls_browser.py`
- `tests/test_character_read_routes.py`
- `tests/test_api*.py`
