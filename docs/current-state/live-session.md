# Live Session

Last updated: 2026-07-22

## Owns

- Player Session, DM Session, Session Character, staged/revealed articles, chat logs, session article images, polling, live rerender stability, and session-to-publishing handoffs.

## Current User-Facing Behavior

- Live Session is distinct from published `Sessions` recap pages.
- `/session`, `/session/character`, and `/session/dm` share one Session shell. Enhanced tab clicks switch panes through History API without full document navigation.
- Player Session owns live chat, message composition, visible revealed article chat entries, and player-facing active/inactive state. Inactive sessions render a compact inactive-state card instead of the chat window and composer; chat appears only while a session is active.
- The Session message composer is the representative asynchronous adopter of the shared feedback primitive. Successful enhanced posts use one global transient, polite success path, replace and clear the composer, and restore usable textarea focus. A controller-exposed validation response with `ok: false` instead uses one form-local persistent, assertive path with stable form description and form-level invalid state; it does not infer field errors. The mounted composer preserves draft, focus, selection, and visual viewport anchor, including across a Session identity change, and suppresses the final anchor scroll. Success and validation transitions do not leave both feedback roots populated.
- DM Session owns five task views under `/session/dm`: `tools`, `staged`,
  `revealed`, `article-store`, and `logs`. Manager access is checked before a
  bare or unknown `dm_view` receives a temporary `302` normalization to
  `dm_view=tools`; generated links use only those five keys. Tools owns live
  lifecycle controls and DND-5E passive-score cards, using a lightweight
  mechanics projection rather than a complete Character presentation. Each
  other view owns its named workflow.
- One nested DM shell navigation controller owns switching among those five
  views inside exactly one enclosing `data-session-live-root`; a separate
  single Session DM polling controller owns live updates for that root.
  The requested view is server-rendered; an authorized first switch to another
  view performs one lazy fragment GET, then retains that pane mounted. A hidden
  pane affected by live state is marked stale and receives one refresh when it
  is next activated. History navigation uses canonical view URLs, while real
  links and full GETs remain the no-JavaScript fallback.
- Retained DM workflows preserve their relevant local state across switches and
  refreshes: staged edits and selected files, revealed open details and dialog
  focus, Article store mode/search/upload/manual drafts, Logs selection, focus,
  and viewport anchors. The first viewport prioritizes the active workflow and
  current live state before secondary reference or administration material.
- Session's `Clear all`
  revealed-articles action is the Slice 5.6c adopter of the accepted shared
  destructive-confirmation and dialog presentation. This higher-risk
  confirmation names the action, current article count, and scope: it removes
  all revealed session articles and their related reveal chat and log entries,
  while staged articles remain unchanged. Its acknowledgement is a
  client-side confirmation-strength control, not a new route-side policy.
- The shared presentation controller owns generic dialog lifecycle and focus
  return. The Session controller owns async submission, busy state, existing
  known feedback, and scoped reinitialization after the revealed-articles root
  is replaced. A known `ok: false` payload keeps the existing global feedback
  path and does not show unknown-result recovery. A non-2xx response, network
  failure, or malformed response instead focuses persistent local guidance
  that the result could not be confirmed and directs the manager to refresh
  Session before repeating; it does not infer success, failure, rollback, or
  journal state.
- The real CSRF-protected POST form remains the native no-JavaScript fallback,
  and manager access is unchanged. Slice 5.6c changes no route, API, method,
  authorization or View As, CSRF, service/store, storage, transaction,
  revision, persistence ordering, or deletion-policy contract. Polling,
  open-details, focus, viewport, composer draft, query, loading, and theme
  behavior remain owned by their existing Session paths. Other Session
  destructive workflows remain separate. Combat selected-PC dialogs were
  adopted independently in the later Phase 5 Combat slice.
- Session message specific-player labels use character-first display when possible: `Character Name (username)`. Players without assigned characters fall back to username, duplicate labels are disambiguated with the user id, and emails are not shown in the picker.
- Session Character can mount inside the player Session shell and also remains available as a full-page/no-JS fallback. The Session Character picker sits below the Session/Character/DM navigation and outside the character card, with `Open full character page` in the same row; the duplicate `Session Character` header is omitted inside the embedded sheet.
- DND-5E Session Character uses DND sheet sections and active-session controls for HP/temp HP/Hit Dice, resources, spell slots, equipment state, inventory quantities, currency, notes, and rests. Editable resource cards use the shared resource mutation and include a visible per-card `Save` action in addition to blur autosave. Rest confirmations can set final Current HP and current Hit Dice before applying the rest.
- Session Character Inventory and Equipment reuse the compact shared item-grid convention, using up to three columns where space allows and one-column mobile stacking without losing quantity, item-detail, or equipment-state controls.
- DND-5E Session Character item and spell detail dialogs are adopters of the shared presentation controller. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Session retains dialog content and real links, native fallbacks, scoped initialization after initial, lazy, or mutation-response fragment insertion, query and History state, draft, focus, viewport, mounted Session, and polling behavior. Dialogs retain unique resolved heading labels.
- If the shared controller or its `init` function is absent, Session Character leaves trigger templates inert without creating gates or setting an unavailable state; native item and spell fallbacks remain visible, and `spell-modal-js` stays inactive. A present `init` that no-ops or throws leaves hidden trigger gates in place, marks the Session Character scope unavailable, preserves the fallbacks, keeps `spell-modal-js` inactive, and allows later Session sections and forms to initialize. Success exposes every trigger atomically and idempotently.
- This adopter changed no shared controller, CSS, base template, spell partial, Session shell or live controller, CSP/static order, route/API/method, access, authorization or View As, CSRF, service/store, storage, persistence, mutation, polling, loading, or theme contract. Combat selected-PC dialogs were adopted in the later Phase 5 Combat slice and retain Combat-owned initialization and replacement behavior.
- Xianxia Session Character mirrors Xianxia read-sheet subpages except `Controls`, which stays on the full Character page.

## Technical Ownership

- The Phase 6 Session workspace and shared async-read contract are independently
  accepted, integrated on pushed `main`, and deployed in current Fly release
  `v229` from exact clean commit
  `2c6774b269995320c149dd81e59d842304e740a8`, tree
  `c297efdfaa67e6aa98bef3d52194100fc47948f0`, with runtime subtree
  `8df5d77456ec84877fcb43caf0b26761630bceb1` and test subtree
  `0ea591db4faf8ee86d582958e6506da1c1760ef9`. Its CPython 3.12.12
  canonical suite passed 4,789 tests, skipped 25, and failed 0. Later pushed-main
  workflow, test, and documentation commits were not redeployed; the app runtime
  subtree remains exact. No live content/database write or incident causality is
  implied. The Session-to-wiki one-shot durability contract first
  shipped in Phase 4; Phase 5 Session presentation was deployed in historical
  Fly release `225` from exact clean commit
  `8766292816f2f91f10085f09f2e372651545eced`. The deployment performed no
  explicit database/content sync or private-data write.
- `player_wiki/session_routes.py` owns the Session Blueprint and all 19 live-session browser handlers/rules: nine GET and ten POST rules. `player_wiki/session_api_routes.py` owns all 13 live-session JSON handlers/rules through explicit registrations on the existing API Blueprint. Public Flask and `api.*` endpoint identifiers, methods, wrapper order, payloads, and implicit `HEAD`/`OPTIONS` behavior remain unchanged.
- `player_wiki/app.py` and `player_wiki/api.py` retain shared Session context builders, renderers, serializers, request/auth/error helpers, service composition, and registrar dependency wiring. The final qualified Phase 3B inventory leaves 26 direct route decorators in `app.py` and 35 in `api.py`; the change from the earlier Session checkpoint also reflects the later Character, Auth, and Admin extractions, not a Session contract change.
- `/session/character` and the character-session route family remain Characters-owned even when surfaced inside the Session shell. Low-level content APIs remain Publishing-owned. Neither family is part of the 19 browser plus 13 API live-session transport inventory.

## Session Article Contract

- Session article store creation modes are Manual, Upload, and Lookup.
- Upload mode accepts UTF-8 `.md` or `.markdown` files and can attach separately uploaded referenced images from frontmatter, Markdown images, or Obsidian embeds.
- Lookup mode lazily searches visible published wiki pages plus accessible Systems entries and stages a revealable snapshot.
- Staged articles are hidden from wiki/search until converted or saved through the Player Wiki editor.
- DMs/admins can update unrevealed staged article title, body, image alt/caption, or replacement image from Session DM or DM Content -> `Staged Articles`.
- Revealed session articles render into the session chat feed and remain visible in stored DM chat logs.
- One-shot conversion prepares sanitized mirrored Markdown with stable provenance
  `source_ref: session-article:<campaign>:<article-id>`. A keyed in-process
  source lock plus finalized page provenance and active prepared-or-conflict
  journal provenance prevents converting the same source twice, including
  after process restart. Valid unrelated provenance does not block conversion;
  malformed or untrusted private recovery payload fails closed with a repair
  error and is not disclosed.
- Destination creation is decided transactionally with the Player Wiki journal.
  A concurrent one-shot or editor promotion has one winner; the loser does not
  overwrite the page or leave an orphaned image. The optional Session article
  image is validated, converted to a protected campaign asset, and remains
  readable after the source article is deleted. Only a losing or otherwise
  uncommitted prepared image is cleaned up.
- Conversion uses Player Wiki forward reconciliation across Markdown, the
  optional image, SQLite, and repository refresh; it does not claim
  cross-filesystem/database atomicity. A refresh failure remains retryable as
  `repository_pending`. If the later live-revision bump fails, the committed
  page and image remain readable; if response generation fails after the bump,
  the revision has advanced exactly once. Normal success also advances the live
  revision exactly once.
- Immediately visible conversions redirect to the player-readable wiki page.
  Future-reveal conversions return to the same form with the exact success
  message and `Already converted` state; players receive 404 until the campaign
  reaches the threshold. The one-shot path emits no browser
  `campaign_wiki_page_created` audit, while promotion through the Player Wiki
  editor retains that audit. Existing manager authorization, CSRF, validation,
  submitted-form preservation, route, flash, and redirect behavior is
  unchanged.

## Live Update Contract

- Session pages use lightweight polling and server-rendered or JSON-backed partial refreshes rather than websockets.
- The shared root-scoped async-read policy in
  `player_wiki/templates/_live_ui_helper.html` owns one in-flight safe read per
  live root, a 30-second read timeout, hidden/offline/pane-hidden cancellation,
  and the visible/online resume path. Safe-read errors back off from the
  surface idle interval with exponential delay capped at 30 seconds; the
  visible `Retry live update` control performs one explicit safe refresh.
  `changed: false` responses clear the error state without replacing DOM or
  announcing an update; changed responses settle the read and announce only
  after a visible replacement.
- Session timings are active/idle `3000/6000 ms` for Player Session and
  Session Character, and `2000/5000 ms` for Session DM, with a `30000 ms`
  idle threshold and read timeout. `session-live.js` owns polling, response
  application, retry/status state, and pause/resume; `session-shell.js` owns
  History API pane navigation, lazy fragment loading, retained/stale pane
  activation, and canonical full-GET fallback. Shell navigation does not own
  polling, and polling does not replace the shell's real-link/no-JavaScript
  fallback.
- Live roots are paused while hidden where applicable.
- During enhanced composer submission, the existing request-in-flight state sets form `aria-busy` and disables submit controls without mounting the full-page or live loader. Validation preserves the mounted composer. HTTP `503` and network failures restore controls and retain its state without claiming success, failure, rollback, or a safe mutation retry; native no-JavaScript POST remains available. This changes no Session route, API response schema, authorization or View As rule, CSRF/CSP/no-store behavior, polling ownership, mutation/audit behavior, or event ordering.
- Safe Session fragment GET failures can fall back to the canonical full GET,
  and safe live reads may back off and retry. A response that leaves a mutation
  outcome ambiguous instead directs the user to refresh and search current
  state before repeating the action and is never blindly retried. Phase 6
  exposes explicit revision conflicts on their owning workflow. Private-journal
  and durable write-outcome presentation remain deferred without a phase
  assignment; the Phase 7 planning baseline is limited to this conservative
  unknown-outcome guidance unless separately approved product and authority
  expand it.
- Player Session polling should preserve the viewport while a user is reading older chat messages.
- The retained DM workflow panes preserve staged-article edit drafts and files,
  open details, Article store mode/search/upload/manual drafts, focus, selected
  log state, and viewport anchors across live polling, stale-on-activation
  refreshes, and Session-shell pane switches.
- DM staged/revealed article details should preserve open state across live polling and async mutation rerenders.
- Revision values, view tokens, and state revisions are implementation details; do not render user-facing `Revision` or `Live revision` counters.

## Current Tests Or Verification

- Session changes usually need focused route tests, browser checks, or direct API checks around lifecycle, staged/revealed articles, image handling, chat/log behavior, Session Character, and rerender stability.
- The June 25, 2026 browser pass covers inactive/active Session chat
  presentation, the Session DM presentation then in place, character picker placement,
  specific-player labels without email, player-chat viewport preservation
  during polling, and DM staged-editor state/focus/viewport preservation during
  polling.
- Slice 4.3 verification covers immediate and future real-browser conversion,
  source/destination races, restart-visible provenance, malformed-payload
  refusal, optional-image cleanup and retention, reconciliation refresh faults,
  revision/response faults, audit separation, and preserved route/form/security
  contracts.
- Phase 5 focused coverage in `tests/test_campaign_session_page.py`,
  `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py`
  covers composer feedback, Session Character dialog initialization and
  fallbacks, clear-revealed confirmation, async replacement, focus/draft/
  viewport preservation, native CSRF/no-JavaScript behavior, and Session/
  Combat ownership boundaries. Those slices were independently accepted and
  assembled into final Phase 5 candidate `8766292816f2f91f10085f09f2e372651545eced`.
- Slice 6.4 coverage in `tests/test_campaign_session_page.py` and
  `tests/test_static_assets.py` checks the five-key route and access matrix,
  normalization redirects, lazy retained panes, stale-on-activation refresh,
  History and no-JavaScript fallbacks, retained workflow state, shared
  root-scoped safe-read timeout/backoff/pause/resume/retry behavior, unchanged
  short-circuit responses, and ambiguous-mutation guidance. The exact deployed
  Phase 6 runtime/test trees above passed the CPython 3.12.12 canonical suite
  with 4,789 passed, 25 skipped, and 0 failed. The Tools-only lightweight
  passive-score projection remains covered by
  `tests/test_session_passive_score_containment.py`. Named local anchors
  include `test_shared_live_async_policy_and_session_adoption_are_root_scoped`,
  `test_browser_shared_live_async_policy_backoff_conflict_and_mutation_state`,
  `test_browser_session_safe_read_policy_recovers_pauses_and_retains_mounted_state`,
  and the Session unchanged-response checks in
  `tests/test_campaign_session_page.py`.
- The independently verified Phase 5 complete suite collected 4,674 tests:
  4,649 passed, 25 expected skips, and none failed, errored, or xfailed. The
  accepted candidate was pushed on `main` and deployed as historical Fly
  release `225`, superseded by Phase 6 release `v229`.

## Known Limits

- No Session-specific anti-jumpiness items are currently open after the June 25, 2026 browser verification pass. Cross-surface refresh work should use the owning current-state doc and backlog.

## Related Backlog

- `.local/roadmaps/session-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`
- `.local/roadmaps/publishing-backlog.md`

## Source Pointers

- Primary Slice 4.3 sources and focused tests:
  `player_wiki/session_article_publisher.py`,
  `player_wiki/publishing_mutations.py`,
  `player_wiki/player_wiki_reconciliation.py`,
  `player_wiki/session_routes.py`,
  `tests/test_campaign_session_page.py`,
  `tests/test_dm_content_player_wiki.py`, and
  `tests/test_player_wiki_reconciliation.py`.
- `player_wiki/campaign_session_store.py`
- `player_wiki/campaign_session_service.py`
- `player_wiki/session_routes.py`
- `player_wiki/session_api_routes.py`
- `player_wiki/live_presenter.py`
- `player_wiki/app.py`
- `player_wiki/api.py`
- `player_wiki/session_source_presenter.py`
- `player_wiki/templates/session.html`
- `player_wiki/templates/session_dm.html`
- `player_wiki/templates/_session_composer_card.html`
- `player_wiki/templates/_session_revealed_articles_card.html`
- `player_wiki/templates/_destructive_confirmation.html`
- `player_wiki/static/session-live.js`
- `player_wiki/static/session-shell.js`
- `player_wiki/templates/_live_ui_helper.html`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/templates/_session_character_panel.html`
- `player_wiki/templates/_session_character_dnd_workspace.html`
- `player_wiki/templates/_combat_workspace_scripts.html`
- `tests/test_campaign_session_page.py`
- `tests/test_character_read_shell_browser.py`
- `tests/test_static_assets.py`
- `tests/test_api_session.py`
- `tests/test_session_passive_score_containment.py`
- `tests/test_route_contract_manifest.py`
