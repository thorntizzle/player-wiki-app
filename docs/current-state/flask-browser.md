# Flask Browser App

Last updated: 2026-09-01

## Owns

- Browser route ownership, Flask template shell behavior, loading cover behavior, browser/API link contracts, and the retired preview-route boundary.

## Current Contract

- Flask is the only committed browser frontend. Normal entry points, campaign navigation, account/admin pages, wiki pages, Session, Combat, DM Content, Systems, and Characters all use `/campaigns/...`, `/account`, and `/admin` Flask routes.
- `/app-next` routes are not registered. Requests to `/app-next`, `/app-next/`, assets under `/app-next`, or old campaign preview paths return 404.
- The retired preview source tree and build output are removed from the app repo. The Docker image is Python-only and does not build or copy a separate browser bundle.
- Account settings no longer expose a preferred-frontend selector. The compatibility `frontend_mode` preference field remains in SQLite/API payloads, normalizes to `flask`, and rejects writes.
- JSON endpoints remain available for Flask browser flows and future clients. Link fields now point to Flask routes; stale `/app-next` links in rendered wiki body HTML are rewritten back to `/campaigns/...`.
- `docs/contracts/route-access-policies.json` is the explicit endpoint-policy source for the Flask rewrite, and `scripts/generate_route_manifest.py` combines it with `create_app().url_map` using tracked sample campaigns. The committed generated manifest records browser/API/framework ownership, method, actor matrix, campaign scope, visibility and object relationships, system gates, View As behavior, and denial mode without inspecting private campaign data.
- The final Phase 3B ownership inventory remains part of the shipped boundary. Phase 5 presentation behavior is integrated on pushed `main` and was deployed as historical Fly release `225` from exact clean commit `8766292816f2f91f10085f09f2e372651545eced`, tree `292d130a3e76b5208061dd7f58b477305461530b`. That deploy performed no explicit database/content sync or private-data write.
- Phase 6 live-workspace, shared async-read, and character-load behavior is
  independently accepted, integrated on pushed `main`, and deployed in
  historical program release `v229` from exact clean commit
  `2c6774b269995320c149dd81e59d842304e740a8`, tree
  `c297efdfaa67e6aa98bef3d52194100fc47948f0`, with runtime subtree
  `8df5d77456ec84877fcb43caf0b26761630bceb1` and test subtree
  `0ea591db4faf8ee86d582958e6506da1c1760ef9`. Its CPython 3.12.12
  canonical suite passed 4,789 tests, skipped 25, and failed 0. Later pushed-main
  workflow, test, and documentation commits were not part of that release; the
  `v229` artifact's runtime subtree remains exact. The release implies no live
  content/database write or incident causality. Separately, historical
  user-supplied production provenance on 2026-07-28 reported hotfix commit
  `24f65346` as the deployed state at that time; later formal releases `233`
  and `v235` supersede it as the current deployment record.
- Frozen Phase 8 release base
  `0f144e51a6a00dd74b005cbf7a19af5acd720be9`, tree and index
  `f989201a91e46bd0c75ed829b5957d5fd88d4294`, has exact runtime subtree
  `aec65a79385049ebf7f201fb2461ca20e6b1361f` and test subtree
  `c2d983699b6e62d48ab8373e61c03d03921600a2`. Its independent
  exact-candidate suite collected 5,039 tests, passed 5,007, skipped 32, and
  had zero failures or errors in one invocation. The final comparison gate is
  `WAIVED_BY_OPERATOR_RUNNER_FAILURE`, with program credit `NONE` and accepted
  residual unmeasured-regression risk; its zero-sample runner failures imply no
  product or performance result. The accepted Phase 4 versus `af3f122e`
  comparison is historical support only. See
  [Ops And Fly Deployment](ops-deploy.md#phase-8-local-candidate-and-release-boundary).
  The candidate contains pushed `main`'s legacy Player Wiki URL delta but is
  itself local only, not `main`, pushed, deployed, or observed live.
- The integrated route manifest at
  `a6286f3885c478f825bb7130b109e73ab4fa9546` contains 319 Flask rules, 318
  non-static rules, and 329 method/path contracts: 192 browser, 136 API, and
  one framework-owned static entry. Domain rule/contract ownership is app shell
  16/16, Auth 13/15, Admin 30/30, Publishing 20/20, DM Content 25/25, Systems
  35/35, Live Session 39/39, Combat 52/52, Characters 88/96, and framework 1/1.
  QOL Mechanics Browser 10B is exactly two additive Systems browser GET
  rules/contracts over its parent: totals move from 317/327 to 319/329, browser
  contracts from 190 to 192, and Systems from 33/33 to 35/35; API accounting is
  unchanged.
- The app registers the `/api/v1` API Blueprint plus publishing, DM Content, Systems, and Session browser Blueprints and the extracted Character, Auth, Admin API, and campaign-visibility registrar families. Compatibility registration preserves supported bare Flask endpoint identifiers with exactly one registered rule per method/path. The Session layer owns 19 live-session browser handlers/rules, split into nine GET and ten POST rules. The Systems transport owns seven read registrations, including the private mechanics-impact queue and selected-detail GETs; the source-policy and entry-override POST registrations; five custom-entry lifecycle registrations; the shared/core permission POST; the shared-entry edit GET and update POST; and the browser DND-5E import POST. Its 18 explicit registrations preserve bare endpoint identifiers. The intended four-GET subset is the custom-entry edit GET, shared-entry edit GET, mechanics-impact queue GET, and mechanics-impact selected-detail GET. Each mechanics-impact registration is explicitly GET-only with Flask-supplied `HEAD` and `OPTIONS`; the two editor GETs retain the same supplied methods. All extracted Systems POST registrations, including `campaign_systems_control_panel_import_dnd5e`, keep implicit `OPTIONS` without `HEAD`.
- `session_api_routes.py` adds 13 live-session rules and handlers to the existing API Blueprint rather than creating another Blueprint. They preserve their supported `api.*` endpoint identifiers, methods, implicit `HEAD`/`OPTIONS` behavior, authorization wrappers, payloads, and registration order where PUT and DELETE share the article path. `api.py` retains the Blueprint, shared request/auth/error helpers, Session serializers and composition, and registrar dependency wiring.
- `systems_api_routes.py` adds 16 rules for 15 Systems handlers to the existing API Blueprint rather than creating another Blueprint: eight GET rules for seven read handlers plus eight mutation handlers for source policy, entry overrides, custom-entry create/update/archive/restore, campaign item-mechanics import, and app-admin DND-5E ingest. The landing and search paths keep the shared `api.systems_index` identifier; every other handler keeps its existing bare `api.*` identifier, including `api.systems_import_run_list`, `api.systems_import_run_detail`, `api.systems_item_mechanics_import`, `api.systems_import_dnd5e`, and the four `api.systems_custom_entry_*` identifiers. The two app-admin-only import-run reads remain read-only GET rules with implicit `HEAD` and `OPTIONS`. Each method/path remains registered exactly once. The shared `/systems/sources` path continues to advertise GET, HEAD, OPTIONS, and PUT through automatic OPTIONS handling; the custom-entry, item-mechanics, and DND-5E ingest POST mutations retain implicit `OPTIONS` without `HEAD`.
- The shared loading cover remains in the Flask base template and may rotate visible campaign image assets when the viewer can access the wiki.
- Shared CSS and large page scripts are served from `player_wiki/static/` with content-digest `?v=` URLs. In production, immutable caching is granted only when that digest matches the served content; absent, stale, or bogus versions do not receive immutable caching.
- The shared shell puts a `.skip-link` first in focus order and targets the named, programmatically focusable `#main-content` landmark. Shared presentation CSS supplies low-specificity native `:focus-visible`, the single `.visually-hidden` helper definition, `.state-panel` with `--empty` and `--error` modifiers, and `.action-group`.
- The state panel is adopted on two representative surfaces: the Campaign Picker empty state and the global not-found recovery error. Both panels are statically labeled by headings and are not live regions; the not-found action group retains real links and navigation semantics.
- The campaign shell remains one adaptive, role-aware shell. Its compact desktop secondary row places authorized campaign navigation beside global search; at `max-width: 820px` the row stacks and the navigation changes to an auto-fit grid (`821px` remains above the boundary and `820px` is at it). The mobile search form remains one row, and empty search status and results regions consume no initial height.
- The campaign navigation has a programmatic label and exactly one active real-href link carries both `.is-active` and `aria-current="page"`. Existing server-owned role filtering remains authoritative, and the shell does not expose View As controls. At the accepted `1280x900` and `390x800` matrix, campaign identity, authorized route navigation, global search, auth actions, the route `h1`, and the applicable primary action remain in the first viewport without horizontal overflow under the exercised signed-out, player, DM, and app-admin states across parchment and moonlit themes.
- Campaign DMs and effective app admins have a `Manager Tools` navigation link
  after `DM Content` and before `Control`, replacing the former top-level
  `Source Health` slot. Its private, server-rendered GET at
  `/campaigns/<campaign-slug>/manager-tools` authorizes the effective actor
  before evaluating four independently owner-gated capabilities: Character
  Updates, Session Readiness, Encounter Presets, and Source Health. Character
  Updates, Session Readiness, and Source Health report availability without
  scanning Characters, aggregating readiness, or building a Source Health
  report. Encounter Presets performs at most one
  authorization-first bounded count and presents `0`, `1`, `2` through `25`,
  or `25+` saved encounters without loading preset records into the page.
  View As player or observer exposes neither the hub nor its cards; an eligible
  effective DM can receive the hub while each owning destination retains its
  own authorization and mutation boundary. The hub adds no mutation, API,
  schema, migration, JavaScript, polling, background work, or cache.
- Systems managers now have two private server-rendered mechanics-review GETs:
  the bounded queue at
  `/campaigns/<campaign_slug>/systems/mechanics-impact` and selected detail at
  `/campaigns/<campaign_slug>/systems/mechanics-impact/review`. Effective-actor
  Systems admission precedes query parsing or inspection, so View As retains no
  real-admin bypass; Characters/equipment, published Mechanics, Combat, and
  preset consumers remain independently owner-gated. The queue/detail templates
  have no page JavaScript or forms and carry `private, no-store` plus
  `no-referrer` headers.
- Queue continuation, selection, queue return, owner continuation, and
  selected-Character preview use signed, purpose-bound, 900-second state tied
  to the campaign/library and relevant snapshot, row, timestamp, and digest.
  Malformed or tampered query state, stale state, unavailable selection, and
  internal errors use bounded generic 400, 409, 404, and 500 recovery behavior
  respectively; no raw metadata, JSON/HTML, private identifiers, internal
  paths, digests, or test canaries render. Invalid effective metadata on a valid
  selected row instead returns bounded detail with status 200, fixes both
  displayed status values to `Invalid Metadata`, exposes only allowlisted row
  identity/presentation fields, and suppresses raw, humanized, fallback, or
  dormant status echoes, owner/interpreter calls, and all editor actions.
  Preview constructs an
  approve-only in-memory proposal and reuses the existing item/Character and
  monster/NPC-resource interpreters; it performs no approval or other write and
  does not retroactively change Characters, presets, or combatants.
- The Systems management panel now begins with exactly six in-page management
  anchors: Source Enablement, Entry Overrides, Custom Entries, Shared/Core
  Editing, Shared Source Imports, and Import-Run History. A seventh, separate
  static Mechanics Review card links to the queue without loading counts or
  inspection data. The same panel appears in DM Content -> Systems and the
  Systems control panel.
- Browser bounds are a 4,096-byte request target, 3,840-byte signed browser
  tokens, 50-row queue/owner pages, 131,072-byte successful HTML, and
  65,536-byte error HTML. Warmed queue, owner-detail, and selected-Character
  preview ceilings are 8, 12, and 24 database queries with zero writes,
  commits, or rollbacks; their frozen checked p95 ceilings are 100 ms, 150 ms,
  and 500 ms respectively.
- `Session Readiness` opens the private native-link document at
  `/campaigns/<campaign-slug>/manager-tools/session-readiness`. It presents no
  overall pass/fail result; exactly five independent cards appear in this
  order: Active Session, Session Characters, Session content, Source Health,
  and Encounter Presets. Each uses only `ready`, `needs review`,
  `not configured`, `unavailable`, or `not applicable`, plus a real link back
  to its owning workflow. The server-rendered page has no forms, mutation,
  page-specific JavaScript, polling, persistence, or no-JavaScript fork.
- Readiness reads remain bounded and advisory. Session supplies one body/blob-
  free aggregate with staged/revealed counts capped at `25+`; Character
  summarizes at most 50 definitions without initializing missing state and
  intersects assignments against those available definitions; Source Health
  computes only its existing bounded first page and treats partial, stale, or
  finding-bearing reports as review rather than healthy; Encounter Presets
  counts at most 26 and reports unsupported Combat as `not applicable`.
  Owner failures remain confined to their owning row or rows and expose
  sanitized guidance; one Session aggregate supplies both Active Session and
  Session content, so its failure marks those two rows `unavailable` together.
- The Source Health URL remains
  `/campaigns/<campaign-slug>/source-health`. Its private read-only page now
  marks `Manager Tools` as the single active campaign-navigation link while
  retaining its native Retry, Campaign Home, action, and one-token Next-page
  links and requiring no page-specific JavaScript. Partial results explicitly
  make no campaign-wide healthy or empty claim; error and stale reports
  suppress unsafe actions. The inventory roster remains `characters`,
  `mechanics`, `combat`, then `presets`; the roster is bound into the bounded
  campaign-specific `sh2` continuation, so older three-owner browser
  continuations fail closed before service inventory while a fresh GET
  succeeds. The accepted service `sh1` profile remains unchanged.
- The preset owner inventories one bounded page of durable source-backed entry rows and projects only an opaque affected-consumer identity and the `Encounter preset` surface. It exposes no preset/source title, raw row ID, or fingerprint and continues to provide no Source Health destination; the later manager-only preset browser does not change Source Health action projection. Current Character, DM Content, and Systems seed fingerprints are resolved in bounded read-only batches after ordinary eligibility/access resolution. The composed request remains capped at 50 findings, 4,096 unique target references, 18 database queries, a 3,840-byte browser cursor, and the established success/error response ceilings. A target-reference overflow fails before resolution; malformed durable or current fingerprints produce the existing sanitized all-or-nothing error.
- Encounter Controls now hosts a manager-only `Saved encounters` browser on the existing private GET document. Stable query links select list pages, new drafts, saved detail, and edit mode while preserving a valid selected combatant. Three CSRF-protected POST patterns own draft/review/create, draft/review/update, and revision-guarded delete. Review and save re-derive bounded source-backed rows and compare a canonical digest; draft operations do not persist, successful mutations use `303` redirects, and malformed/foreign selectors fail only after campaign and manager authorization.
- The preset section stays outside `[data-combat-live-root]`, so ordinary changed Combat polls do not replace its mounted node or draft. The accepted desktop/mobile browser matrix preserves typed values, source selection, disclosure/dialog state, focus, combatant URL, viewport, theme, and tracker/source state. JavaScript-disabled clients retain native CRUD, row ordering, edit/review Name autofocus, and deletion. In edit/review mode, JavaScript-enabled validation responses use one error-only CSP-nonced loading-aware script to focus the marked Name control; delete conflicts instead retain server guidance without that script. Preset deletion retains the shared accessible confirmation content but deliberately uses native document POST rather than Combat's JSON mutation transport.
- In the accepted QOL Preset 3B candidate, saved-encounter detail adds an
  explicit additive-apply review link and one manager-only CSRF-protected POST.
  The server-rendered review separates proposed from existing combatants and
  warns on a nonempty tracker. The POST reauthorizes and rematerializes sources,
  binds preset, tracker, source, Character-state, authorization, and digest
  state, and either commits the complete expanded roster with source-derived
  counters/notes, one tracker revision bump, and one sanitized audit or writes
  none of them. Existing combatant rows and their dependents, round/current
  state, the selected combatant URL, presets, and source records are preserved.
  The tracker record receives exactly one metadata transition for its revision,
  updater, and timestamp on success.
- The successful apply path performs authoritative readback before a bounded
  post/redirect/get receipt. An uncertain outcome offers only refresh, tracker
  inspection, and fresh-review guidance, with no repeat control. The native
  server-rendered flow remains functional without JavaScript; there is no apply
  API, asynchronous apply enhancement, or durable browser outcome ledger. The
  preset browser remains outside the live replacement root, so changed polls
  preserve its mounted review state, focus, viewport, and selected URL while
  the single tracker revision transition exposes the completed roster
  atomically on subsequent live reads. This is an accepted local candidate
  boundary, not a deployment or live-verification claim.
- Phase 5 added one same-origin, content-versioned external presentation controller for generic dialog mechanics. It accepts either the document or an inserted element as its initialization scope, initializes each opted-in dialog once, requires a non-empty `aria-label` or valid `aria-labelledby`, uses native modal open/close behavior (including Escape and focus containment), closes from an opted-in Close control or backdrop, moves focus to an explicitly marked initial control, and returns focus only to a still-connected invoker. Repeated initialization, an already-open dialog, and a detached invoker remain safe; browsers without the native methods receive only a bounded `open`/`close` fallback.
- Global search is the first adopter from Slice 5.4. Its inline domain controller still owns browser search and preview fetches, cancellation/debounce, status/results/error rendering, preview insertion, and live and busy updates; the shared controller owns only the dialog lifecycle. Flask routes retain authorization and access filtering, while the server/template pipeline retains `safe_rich_html` preview sanitization and the real dedicated-page link. Query, viewport, theme, and loading behavior are preserved. The shared controller can initialize a later inserted element, but Slice 5.4 does not claim that global search itself is fragment-replaced. The native search form can submit without JavaScript, but there is no supported no-JavaScript search-results fallback and this slice does not invent one; existing real links and domain no-JavaScript fallbacks elsewhere remain unchanged.
- The external controller loads synchronously immediately before the existing nonce-bearing global-search adopter script. The checked template inventory now contains 13 inline scripts across 12 templates, seven external scripts, one inline style, and no inline event handlers; every inline element carries the required nonce. Native `details` remains preferred when sufficient, and each additional adopter requires a separate independently verified rollback unit.
- Phase 5 added one shared Jinja destructive-confirmation presentation primitive on top of that accepted external dialog lifecycle. The first bounded adopters are DM Combat's lower-risk `Remove combatant` action and higher-risk `Clear tracker` action. Both confirmations name the action and affected encounter scope, distinguish encounter-owned cleanup from unchanged character sheets and source records, and retain real CSRF-protected POST forms. Remove requires the trigger plus one final confirmation; Clear additionally requires an explicit acknowledgement before its final submit. Cancel, Escape, and backdrop dismissal return focus to the still-connected trigger.
- JavaScript-enabled Combat owns form submission, busy state, known server feedback, response rendering, and idempotent reinitialization after its authority or controls fragments are replaced; the shared presentation controller still owns only generic dialog mechanics. A non-2xx response, network failure, or malformed response exposes persistent local guidance that the result could not be confirmed and focuses it without claiming success, failure, rollback, or journal state. A controller-known success or failure retains the existing global transient feedback path. The no-JavaScript path exposes the same scope and consequence in native `details`, then submits the real POST form.
- The Combat destructive-confirmation adoption changes no route, API, authorization, CSRF, service/store, persistence-order, loading, CSP, security, theme, focus/draft/viewport, or deletion-policy contract. Session clear-revealed is adopted separately below; other destructive workflows remain outside these bounded adopters.
- Normal DND-5E Character read-shell item, prepared-spell, and current-spell detail dialogs are bounded adopters of the shared presentation lifecycle. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Character retains sheet content and real links, page/mode query and History state, panel cache, draft and submitted values, focus and viewport restoration, access, and scoped initialization through its existing panel initializer after initial, cached, subpage, or mutation-response insertion. Dialogs have unique resolved heading labels, and the legacy Character data hooks remain for domain selectors and compatibility.
- If the shared controller or its `init` function is absent, Character leaves the trigger templates inert: no ancestor gate is created, no unavailable state is set, the native fallback remains visible, and the `spell-modal-js` enhancement class is not activated. When `init` is present, Character clones dialog triggers into hidden ancestor gates and makes them available only after scoped initialization enables every trigger. A present `init` that returns without enabling them or throws leaves the gates hidden, marks the scope unavailable, keeps the native fallback visible, and does not activate `spell-modal-js`; later Character initialization continues. With JavaScript disabled, spells retain native detail disclosures and items retain noscript detail content, real reference links, and direct subpage navigation.
- Character dialog adoption changes no shared controller, CSS, base-template or CSP ordering, route/API/method, authorization or View As, CSRF, presenter/service/store, storage, persistence or mutation, recovery, loading, theme, Session, Combat, or product-policy contract.
- DND-5E Session Character item and spell detail dialogs are bounded adopters of the shared presentation lifecycle. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Session retains content and real links, native fallbacks, its scoped workspace initializer after initial, lazy, or mutation-response fragment insertion, query and History state, draft, focus, viewport, mounted Session, and polling behavior. Every dialog keeps a unique resolved heading label.
- If the shared controller or its `init` function is absent, Session Character leaves trigger templates inert without creating gates or setting an unavailable state; native item and spell fallbacks stay visible, and `spell-modal-js` is not activated. When `init` is present, triggers remain in hidden gates until every trigger is enabled. A present `init` that no-ops or throws leaves the gates hidden, marks the Session Character scope unavailable, preserves the fallbacks, does not activate `spell-modal-js`, and does not prevent later Session sections or forms from initializing. Successful scoped initialization exposes the triggers atomically and remains idempotent.
- Session Character adoption changes no shared controller, CSS, base template, spell partial, Session shell or live controller, CSP/static ordering, route/API/method, access, authorization or View As, CSRF, service/store, storage, persistence, mutation, polling, loading, theme, or Combat contract. Combat selected-PC dialogs are adopted separately below.
- Session's `Clear all` revealed-articles
  workflow is a bounded adopter of the accepted shared
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
  accepted runtime/test milestone is exact commit
  `1079dce2a1c024802c328db9e4fa92336ca30cbc`, tree
  `4363e7152659abf96401e0df6f557dfba222d236`.
- Selected-PC item and spell detail dialogs in player Combat,
  compatibility Combat Character, and canonical DM Status are
  bounded adopters of the accepted shared presentation lifecycle. The shared controller owns the
  generic trigger and native modal lifecycle: open, Close/Escape/backdrop dismissal, initial Close
  focus, and focus return only to a still-connected invoker. Dialog headings remain uniquely
  resolved.
- The Combat workspace initializer owns scoped fail-safe gating and shared-controller retry after
  the initial mount and through its existing `init` and `restore` seams, including canonical DM
  selected-detail replacements. The current `/combat/status` compatibility page returns an
  access-first temporary redirect and constructs no dialog presentation. Missing, no-op, or
  throwing shared initialization
  leaves trigger templates inert or gates hidden, keeps native item and spell details visible, and
  does not activate `spell-modal-js`; a later successful initialization can recover the scope.
  Legacy Combat direct dialog listeners exclude the adopted scope. Session Character initialization
  and Character/Session controller ownership are unchanged.
- Slice 5.6d preserves real item links and does not invent a dedicated spell link. JavaScript-disabled
  item and spell disclosures remain available. It changes no query, hash, selected section, focus,
  draft, viewport, carousel, polling, loading, theme, access, form, CSRF, CSP, static-order, route,
  API, method, authorization, View As, presenter/service/store, storage, persistence, or mutation
  contract. Its independently accepted runtime/test milestone is exact commit
  `c0a442a275b8d7513a82f53cef9a8161cb8f67d8`, tree
  `4fd26d9c16c37ae35284f47d4eacf74ce73288ee`.
- Phase 5 added one shared feedback primitive with `data-feedback`, `data-feedback-placement` (`transient` or `persistent`), and `data-feedback-tone` (`success`, `info`, `warning`, or `error`). Tone owns announcement urgency independently of placement: success and info use polite atomic status semantics, while warning and error use assertive atomic alert semantics.
- Global Flask flashes use the shared primitive as transient, fixed, viewport-visible feedback. Their `data-flash-stack-root` remains after the header and before the named main landmark, is not itself a live region, and does not intercept pointer input. Existing Session, Combat, and Character replacement hooks keep replacing this root.
- Account live-session chat order is the single synchronous representative. Valid changes and unchanged values retain native post/redirect/get success behavior; an invalid submission retains its `400` response and renders one persistent form-local error with stable description and invalid-state association, then restores focus to the choice group after loading. Native submission remains functional without JavaScript. Routes, methods, authorization and View As behavior, CSRF, CSP, private no-store responses, loading, mutation/audit behavior, event order, and Session/Combat/Character replacement compatibility are unchanged.
- The shared feedback primitive exposes no durable-outcome or private-journal
  browser state. Phase 6 permits safe fragment GET fallback to the canonical
  full GET and backoff/retry for safe live reads. Ambiguous mutations instead
  present refresh-and-search-before-repeat guidance and are never blindly
  retried; explicit revision conflicts remain on their owning workflow.
  Durable write-outcome and private-journal presentation remain deferred
  without a phase assignment. Accepted local Phase 8 behavior does not expand
  beyond that conservative unknown-outcome guidance unless separately approved
  product and authority do so.
- Browser safe-live-read behavior remains root-scoped through
  `player_wiki/templates/_live_ui_helper.html`: one read is in flight per root,
  reads time out at 30 seconds, safe-read errors back off exponentially to a
  30-second cap, and hidden/offline roots pause and abort their read.
  Visible/online resume schedules an immediate refresh, and unchanged responses
  leave the mounted DOM alone. `session-live.js` and `combat-live.js` own their
  respective polling and mutation transports; `session-shell.js` owns Session
  History/lazy-pane navigation and retained stale-pane activation.
- In local-only Phase 8, changed Session and Combat reads synchronously settle
  status once and return a deferred replacement result containing only roots
  that were actually written. Session records them in semantic order: status,
  chat, composer, controls, staged, revealed, then logs. Its staged helper
  counts the staged root only when the helper result has `.applied === true`;
  the direct fallback counts the root immediately after its write. Combat
  records summary, the applicable tracker root, tracker detail, DM authority,
  context, then controls immediately after each actual write; same-token and
  stale responses report no replacement.
- Exact visibility is evaluated only inside the existing update-announcement
  `requestAnimationFrame`. A replacement region must be an `HTMLElement`, not
  have `hidden`, have no `[hidden]` ancestor, and have at least one client rect.
  The live root must also pass `!document.hidden`, `!root.hidden`, no `[hidden]`
  ancestor, and at least one client rect. The frame first rejects a superseded
  announcement sequence, then applies those predicates, then writes the update
  message.
- `Session updated.` or `Combat updated.` is therefore not announced for an
  unchanged response, a changed response with no actual write, a hidden or
  detached root, no visible replacement root, a superseded response or
  announcement, a poll error, or offline state. Existing poll-error/offline
  status announcements and the established revision-conflict message and retry
  behavior remain unchanged; they are not visible-update announcements. Phase
  8 changes no route/API/method or payload schema, access, authorization, View
  As, CSRF, storage, polling cadence/retry/timeout, request token/header, or
  no-JavaScript contract.
- The Session message composer is the representative asynchronous adopter. A successful enhanced post keeps one global transient, polite success path, replaces and clears the composer, and restores usable textarea focus. A controller-exposed validation response with `ok: false` instead keeps one form-local persistent, assertive shared-feedback path, associates the form with a stable description, and marks only the form invalid; it does not infer field errors. The mounted composer retains its draft, focus, selection, and visual viewport anchor, including across a Session identity change, and the controller suppresses its final anchor scroll. Success and validation transitions do not populate both feedback roots.
- The existing Session `requestInFlight` state exposes form `aria-busy` and disables submit controls without mounting the full-page or live loader. HTTP `503` and network-failure exits restore controls and retain the mounted form state without inventing retry or error copy. Native no-JavaScript POST remains the fallback. Routes, API payload schema, authorization and View As behavior, CSRF, CSP, private no-store responses, loading and polling ownership, mutation/audit behavior, and event order remain unchanged.
- Session DM now has one nested shell navigation controller for `tools`,
  `staged`, `revealed`, `article-store`, and `logs` inside exactly one enclosing
  `data-session-live-root`; a separate single Session DM polling controller
  owns live updates for that root. Authorized panes lazy-load once,
  remain mounted, are marked stale while hidden when affected, and refresh once
  on activation while retaining workflow-specific drafts, files, details,
  focus, selection, and viewport state. Real links, History navigation,
  canonical full GETs, and no-JavaScript fallbacks remain available.
- Combat Status canonicalizes to `/combat/dm`: the
  `campaign_combat_status_view` GET/HEAD compatibility endpoint performs an
  authorization-first temporary `302`, preserves a valid `combatant`, and
  omits `view=status`; Controls retains `view=controls`.
  `/combat/status/live-state` remains response-compatible, including its legacy
  `live_url`, while generated Status page and board URLs are canonical.
- Integrated source slice `QOL-NPC-6B-C1`, product commit
  `3d374f9209e73f0fac93efc6913a6cedaf68bc7b` and documentation integration
  commit `025c433949a79c61c5fd4433cee5000817752f7e`, adds compact DM/admin-only
  `Update` forms to the selected source-backed NPC
  counter rows on canonical DM Status. The forms are CSRF protected, submit one
  absolute current value with the parent combatant revision, and remain explicit
  buttons rather than autosubmit controls. A recharge row accepts only `0` or
  `1`; daily and generic rows accept `0..max`. The DM rolls recharge physically
  and records the outcome; the browser performs no roll and displays no die
  result. Player and `View As` surfaces expose no such controls.
- Native 6B submission preserves the selected combatant query and returns to
  the stable resource-row fragment. The enhanced path keeps the selected NPC,
  focused control, document viewport, carousel position, and open state across
  selected-detail replacement. An unknown response focuses persistent local
  guidance to refresh and inspect the resource before another submission. The
  source slice adds no RNG, reset/restore action, audit, schema, or migration and
  does not change the existing API PATCH/public payload/query contract. No
  deployment or live use is claimed.
- Character section navigation handles the bounded-read saturation response by
  retaining the mounted section and History state, showing a local busy message,
  and making no automatic retry. The server admits no more than two expensive
  Character renders and returns a generic no-store `503` with `Retry-After: 2`
  when saturated so navigation and health requests retain worker access.
- The accepted Character Read Performance code point anchored in
  [Characters Overview](characters-overview.md#current-tests-or-verification)
  is on pushed `main` and is the runtime-bearing parent of current Fly release
  `v235`. Xianxia Session Character document and fragment reads skip DND
  item-catalog and equipment-manager construction, while DND-5E retains its
  selected-section scoped managers. The subsequent no-code fairness gate
  retained the normal two-render Character guard, opened no shared Session
  Character admission lane, and changed no worker or machine configuration.
- All Phase 5 presentation slices above are assembled in independently accepted final candidate `8766292816f2f91f10085f09f2e372651545eced`, pushed on `main`, and deployed as historical Fly release `225`, superseded by Phase 6 release `v229`.
- Each HTML response receives a fresh content-security-policy nonce for approved inline scripts and styles. Templates do not use inline event-handler attributes. Privacy and cache headers prevent storage of auth, token-bearing, account, and Admin HTML, while secure production responses add HSTS.

## Current Tests Or Verification

- Flask route changes usually need focused route/API tests and, when browser behavior changes, a local browser smoke check against `/campaigns/...`.
- Route registration or access-contract changes must update the explicit policy map and regenerate the deterministic manifest; `python -B scripts/generate_route_manifest.py --check` and the `contract` pytest marker detect missing/stale endpoint policies, duplicate method/path registrations, API-reference drift, and generated-byte drift.
- QOL Mechanics Browser 10B was independently accepted at implementation
  commit `46b30ec6abfa08706764387e787f19bcae6e31b9`, tree
  `a002fd0ac82387fe2a4a75b52ac2487453b6c671`, then integrated on `main` and
  `origin/main` at `a6286f3885c478f825bb7130b109e73ab4fa9546`.
  Evidence passed 848 focused tests with one expected skip, Chromium 23/23,
  Linux 6,668 passed, and Windows 55 passed. No deployment, live verification,
  private-data access, or database/content sync is claimed.
- QOL Manager Tools 8A C2 passed its independent immutable-candidate sweep with
  6,538 Linux tests passing, three intentional skips, 54 deselections, and 54
  decisive Windows tests passing with 416 deselections. The sweep covered the
  exact route inventory, effective-actor/View As containment, card order and
  links, bounded preset summaries, zero writes, private no-store outcomes,
  real Chromium behavior, and the absence of API/schema/JavaScript/polling/
  cache expansion.
- QOL Session Readiness 8B C0 passed one independent immutable-candidate sweep
  with 6,573 Linux tests passing, three intentional skips, 54 deselections,
  and all 54 Windows-owned tests passing with 416 deselections. Chromium
  `149.0.7827.55` and Playwright `1.61.0` exercised desktop, mobile, `821px`/
  `820px`, parchment/moonlit themes, keyboard skip navigation,
  JavaScript-disabled rendering, native links, overflow containment, and
  document navigation. Independent warmed measurement over 240 samples passed
  at `99.583 ms` readiness p95, 15 queries, 46,082 response bytes, zero writes/
  commits/rollbacks, and a `-2.26%` Manager Tools p95 comparison.
- Separate preview build, typecheck, and browser checks are no longer part of verification.
- Keep a direct assertion that representative `/app-next` routes return 404 so the removed preview surface does not drift back in accidentally.
- Phase 5 shared-primitive coverage lives in `tests/test_static_assets.py` for shell order, the skip target, focused-main behavior, selector ownership, and the representative desktop/mobile keyboard smoke; `tests/test_auth_and_wiki.py` covers the labeled, non-live Campaign Picker empty and global not-found error panels plus native recovery links. This focused evidence contributed to the independently accepted assembled Phase 5 candidate.
- Slice 5.2 coverage in `tests/test_auth_and_wiki.py` checks role-filtered real-href navigation, order, and active-link semantics. `tests/test_static_assets.py` checks the exact `820px` CSS boundary and the `1280x900`, `390x800`, `821px`, and `820px` browser matrix, including first-viewport priorities, auth actions, themes, one-row search, empty-region height, horizontal overflow, skip/main focus, and the mobile search-dialog interaction.
- Slice 5.3a coverage in `tests/test_auth_and_wiki.py`, `tests/test_auth_account_session_chat_order_route_transport.py`, `tests/test_security_headers.py`, and `tests/test_static_assets.py` checks feedback semantics and root order, the Account valid/unchanged/invalid route contract, CSP and no-store preservation, live replacement compatibility, desktop and narrow-mobile placement and interaction, focus recovery, and native no-JavaScript submission.
- Slice 5.3b coverage in `tests/test_campaign_session_page.py` checks the Session composer structure, shared-feedback routing, and controller-exposed busy/invalid states. `tests/test_character_read_shell_browser.py` checks the accepted `1280x900` parchment and `390x800` moonlit success, validation, delayed-response, HTTP/network failure, and native no-JavaScript paths, including focus, draft, selection, viewport, loader, and single-feedback-root behavior.
- Slice 5.4 source coverage in `tests/test_static_assets.py` checks controller ownership, explicit labeling, scoped and idempotent initialization, native and fallback lifecycle, connected/detached invokers, the sole-adopter boundary, content-versioned asset delivery, preserved search-domain code, and script ordering. Its browser coverage exercises the Global Search adopter at `1280x900` parchment and `390x800` moonlit for keyboard opening, native modality, explicit initial focus, Close/Escape/backdrop dismissal, focus return, query/scroll retention, dedicated-page navigation, theme, loading, and overflow; a separate inserted-element scenario challenges repeat initialization and detached-invoker safety. `tests/test_security_headers.py` fixes the current CSP inventory at 13 inline scripts across 12 templates, seven external scripts, one inline style, and no event handlers.
- Slice 5.5 coverage in `tests/test_campaign_combat_page.py`, `tests/test_combat_dm_controls_browser.py`, and `tests/test_static_assets.py` checks proportional scope and confirmation strength, real CSRF POST fallbacks, authorization boundaries, dependent-row cleanup, unchanged source records, round/current-turn reset, cancel/Escape/backdrop focus return, fragment reinitialization, known server feedback, ambiguous transport guidance, busy state, theme, loading exclusion, and JavaScript-disabled forms. Independent verification passed 55 focused source/API/security/route tests, eight committed browser tests, five adversarial browser tests, and the 138-test contract marker selection with no final failures or skips.
- Slice 5.6a coverage in `tests/test_character_read_routes.py`, `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py` checks scoped and repeated initialization after Character panel insertion, explicit dialog labels, Close/Escape/backdrop focus return, read-shell query/History/cache behavior, draft and viewport preservation, loading exclusion, desktop parchment and mobile moonlit presentation, native no-JavaScript content and links, and hidden trigger gates under no-op or throwing shared initialization. Independent verification passed 156 focused source/route/access/security tests with two Windows symlink skips, nine browser tests, three adversarial controller challenges, and the 138-test contract selection with no final failures; focused durable integration smoke also passed five tests plus the 138-test contract selection.
- Slice 5.6b coverage in `tests/test_campaign_session_page.py`, `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py` checks Session Character dialog structure, initial/lazy/mutation insertion, unique labels, keyboard and focus behavior, query/History/draft/viewport and mounted-Session preservation, no-JavaScript fallbacks, fail-safe gates, idempotence, loading exclusion, and legacy Combat isolation. Independent verification passed 439 broad affected tests with one unrelated loading-cover timing failure that passed its isolated rerun, all 226 Session tests, five candidate browser/adversarial tests, three Session regressions, six legacy Combat tests, and the 138-test contract selection with 4,531 deselected. Exact-integration checks passed eight focused tests plus the same 138-test contract selection.
- Slice 5.6c coverage in `tests/test_campaign_session_page.py`,
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
  focused tests plus the same 138-test contract selection.
- Slice 5.6d coverage in `tests/test_campaign_combat_page.py`,
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
  same 138 contract tests.
- Phase 6 browser evidence in `tests/test_static_assets.py`,
  `tests/test_campaign_session_page.py`,
  `tests/test_character_read_shell_browser.py`, and
  `tests/test_combat_dm_controls_browser.py` exercises the five retained
  Session DM workflows, stale activation, shared safe-read fault/backoff/
  pause/resume/retry behavior, unchanged responses, ambiguous mutation
  guidance, Character saturation with no retry, and canonical Combat Status
  navigation at accepted `1280x900` and `390x800` viewports. Focused
  route/access/security tests accompany that local browser evidence. The exact
  deployed Phase 6 runtime/test identities above passed one uncontended CPython
  3.12.12 canonical suite with 4,789 passed, 25 skipped, and 0 failed.
- Phase 8 source and browser coverage in `tests/test_static_assets.py`,
  `tests/test_campaign_session_page.py`, and
  `tests/test_campaign_combat_page.py` checks one synchronous successful-read
  status settlement, announcement-frame visibility evaluation, exact
  actual-write root ordering, Session staged-helper `.applied` refusal, Combat
  same-token and stale no-write paths, visible and hidden/detached outcomes,
  unchanged and superseded reads, and preserved
  error/offline/revision-conflict behavior. The frozen exact local candidate
  suite collected 5,039 tests, passed 5,007, skipped 32, and had zero failures
  or errors. Its final exact-candidate comparison was operator-waived after
  runner failures with zero samples and no product/performance inference. The
  earlier Phase 4 versus `af3f122e` result at `1.1444007858546168` remains
  historical support only.
- The Character Read Performance package summarized in
  [Characters Overview](characters-overview.md#current-tests-or-verification)
  is independently accepted sanitized local-host evidence. Verifier replay
  measured ordinary Session fragment, unchanged Session polling, and unchanged
  Combat polling server-p95 improvements of `21.095%`, `15.174%`, and
  `34.129%`; under overload, Session fragment, readiness, liveness, and
  campaign access all succeeded. No deployment or live-capacity conclusion
  follows from that package itself. The later exact clean documentation/build
  descendant recorded under
  [Ops And Fly Deployment](ops-deploy.md#current-fly-deployment-shape) was
  deployed as Fly release `v235`. Read-only release verification checked
  liveness, readiness, legacy health, anonymous public routing, and one
  existing authenticated GET-only direct Session then Session Character
  browser navigation. The Session Character sheet rendered without a visible
  error at a coarse `~352 ms`; it was Xianxia-or-non-DND, and the selected
  section was not recorded. This single interaction is not production-wide,
  natural group-load, causal, or capacity proof.
- Final Phase 5 candidate
  `8766292816f2f91f10085f09f2e372651545eced`, tree
  `292d130a3e76b5208061dd7f58b477305461530b`, was independently accepted. Its
  canonical Python 3.12.12 complete suite collected 4,674 tests: 4,649 passed,
  25 expected skips, and none failed, errored, or xfailed. Corrected Publisher
  integration checks passed 9/9, and the candidate was deployed as historical
  Fly release `225`, superseded by Phase 6 release `v229`.
- Phase 6 production verification was HTTP-only by explicit operator acceptance
  because the Publisher task had no browser backend or authenticated-session
  fixture. Accepted local candidate browser evidence remains the interaction
  proof; authenticated production browser interaction was not run. No further
  deploy occurred within the Phase 6 closeout after release `v229`; the later
  user-supplied hotfix provenance is a separate observed-live boundary.

## Source Pointers

- `player_wiki/app.py`
- `player_wiki/auth.py`
- `player_wiki/api.py`
- `player_wiki/systems_api_routes.py`
- `player_wiki/session_routes.py`
- `player_wiki/session_api_routes.py`
- `player_wiki/combat_routes.py`
- `player_wiki/character_read_admission.py`
- `player_wiki/character_routes.py`
- `player_wiki/character_*_routes.py`
- `player_wiki/auth_*_routes.py`
- `player_wiki/admin_api_routes.py`
- `player_wiki/campaign_visibility_routes.py`
- `player_wiki/manager_tools_routes.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/dm_content_routes.py`
- `player_wiki/systems_routes.py`
- `player_wiki/mechanics_impact.py`
- `player_wiki/mechanics_impact_presenter.py`
- `player_wiki/templates/systems_mechanics_impact_queue.html`
- `player_wiki/templates/systems_mechanics_impact_detail.html`
- `player_wiki/security_headers.py`
- `player_wiki/templates/base.html`
- `player_wiki/templates/manager_tools.html`
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
- `player_wiki/templates/_combat_preset_browser.html`
- `player_wiki/templates/campaign_picker.html`
- `player_wiki/templates/not_found.html`
- `player_wiki/auth_account_session_chat_order_routes.py`
- `player_wiki/static/styles.css`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/templates/_live_ui_helper.html`
- `player_wiki/static/session-live.js`
- `player_wiki/static/session-shell.js`
- `player_wiki/static/combat-live.js`
- `player_wiki/static/character-read-shell.js`
- `player_wiki/static/`
- `Dockerfile`
- `tests/test_auth_and_wiki.py`
- `tests/test_auth_account_session_chat_order_route_transport.py`
- `tests/test_manager_tools_browser.py`
- `tests/test_manager_tools_route_transport.py`
- `tests/test_security_headers.py`
- `tests/test_static_assets.py`
- `tests/test_campaign_session_page.py`
- `tests/test_character_read_shell_browser.py`
- `tests/test_campaign_combat_page.py`
- `tests/test_combat_dm_controls_browser.py`
- `scripts/measure_live_latency.py`
- `tests/test_measure_live_latency.py`
- `tests/test_character_read_routes.py`
- `tests/test_character_read_common_costs.py`
- `tests/test_character_read_route_transport.py`
- `tests/test_character_performance_caches.py`
- `scripts/measure_character_read_performance.py`
- `tests/test_campaign_combat_preset_browser.py`
- `tests/test_measure_character_read_performance.py`
- `tests/test_session_passive_score_containment.py`
- `tests/test_api*.py`
