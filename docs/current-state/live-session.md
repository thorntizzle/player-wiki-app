# Live Session

Last updated: 2026-07-19

## Owns

- Player Session, DM Session, Session Character, staged/revealed articles, chat logs, session article images, polling, live rerender stability, and session-to-publishing handoffs.

## Current User-Facing Behavior

- Live Session is distinct from published `Sessions` recap pages.
- `/session`, `/session/character`, and `/session/dm` share one Session shell. Enhanced tab clicks switch panes through History API without full document navigation.
- Player Session owns live chat, message composition, visible revealed article chat entries, and player-facing active/inactive state. Inactive sessions render a compact inactive-state card instead of the chat window and composer; chat appears only while a session is active.
- On the local `codex/flask-rewrite-phase5` branch only, the Session message composer is the representative asynchronous adopter of the shared feedback primitive. Successful enhanced posts use one global transient, polite success path, replace and clear the composer, and restore usable textarea focus. A controller-exposed validation response with `ok: false` instead uses one form-local persistent, assertive path with stable form description and form-level invalid state; it does not infer field errors. The mounted composer preserves draft, focus, selection, and visual viewport anchor, including across a Session identity change, and suppresses the final anchor scroll. Success and validation transitions do not leave both feedback roots populated.
- DM Session owns live lifecycle controls, staged articles, revealed articles,
  passive score cards, Session article store, and chat logs. The current Flask
  `/session/dm` pane renders those sections together; it does not yet parse a
  Session `dm_view` query or provide task-specific DM subviews.
- On the local `codex/flask-rewrite-phase5` branch only, Session's `Clear all`
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
  destructive workflows and Combat selected-PC dialogs remain separate and
  deferred.
- Session message specific-player labels use character-first display when possible: `Character Name (username)`. Players without assigned characters fall back to username, duplicate labels are disambiguated with the user id, and emails are not shown in the picker.
- Session Character can mount inside the player Session shell and also remains available as a full-page/no-JS fallback. The Session Character picker sits below the Session/Character/DM navigation and outside the character card, with `Open full character page` in the same row; the duplicate `Session Character` header is omitted inside the embedded sheet.
- DND-5E Session Character uses DND sheet sections and active-session controls for HP/temp HP/Hit Dice, resources, spell slots, equipment state, inventory quantities, currency, notes, and rests. Editable resource cards use the shared resource mutation and include a visible per-card `Save` action in addition to blur autosave. Rest confirmations can set final Current HP and current Hit Dice before applying the rest.
- Session Character Inventory and Equipment reuse the compact shared item-grid convention, using up to three columns where space allows and one-column mobile stacking without losing quantity, item-detail, or equipment-state controls.
- On the local `codex/flask-rewrite-phase5` branch only, DND-5E Session Character item and spell detail dialogs are the Slice 5.6b adopter of the accepted shared presentation controller. The shared controller owns generic trigger, open, Close/Escape/backdrop dismissal, initial Close focus, and return to a still-connected invoker. Session retains dialog content and real links, native fallbacks, scoped initialization after initial, lazy, or mutation-response fragment insertion, query and History state, draft, focus, viewport, mounted Session, and polling behavior. Dialogs retain unique resolved heading labels.
- If the shared controller or its `init` function is absent, Session Character leaves trigger templates inert without creating gates or setting an unavailable state; native item and spell fallbacks remain visible, and `spell-modal-js` stays inactive. A present `init` that no-ops or throws leaves hidden trigger gates in place, marks the Session Character scope unavailable, preserves the fallbacks, keeps `spell-modal-js` inactive, and allows later Session sections and forms to initialize. Success exposes every trigger atomically and idempotently.
- This adopter changes no shared controller, CSS, base template, spell partial, Session shell or live controller, CSP/static order, route/API/method, access, authorization or View As, CSRF, service/store, storage, persistence, mutation, polling, loading, or theme contract. Combat selected-PC dialogs remain unchanged and deferred.
- Xianxia Session Character mirrors Xianxia read-sheet subpages except `Controls`, which stays on the full Character page.

## Technical Ownership

- This ownership inventory is integrated on pushed `main`. The
  Session-to-wiki one-shot durability contract was independently verified in
  Phase 4 and is deployed in Fly release `224` from exact clean runtime commit
  `b80af7c7b441bb2fcecc763bf6ea4a73f9d85365`. The deployment performed no
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
- Live roots are paused while hidden where applicable.
- During enhanced composer submission, the existing request-in-flight state sets form `aria-busy` and disables submit controls without mounting the full-page or live loader. Validation preserves the mounted composer. HTTP `503` and network failures restore controls and retain its state without inventing retry or error copy; native no-JavaScript POST remains available. This changes no Session route, API response schema, authorization or View As rule, CSRF/CSP/no-store behavior, polling ownership, mutation/audit behavior, or event ordering. It standardizes no timeout, retry, private reconciliation, or journal outcome; Phase 7 remains the outcome gate.
- Player Session polling should preserve the viewport while a user is reading older chat messages.
- The combined DM Session pane preserves staged-article edit drafts, open
  details, focus, selected log state, and viewport anchors across live polling,
  status refreshes, and Session-shell pane switches.
- DM staged/revealed article details should preserve open state across live polling and async mutation rerenders.
- Revision values, view tokens, and state revisions are implementation details; do not render user-facing `Revision` or `Live revision` counters.

## Current Tests Or Verification

- Session changes usually need focused route tests, browser checks, or direct API checks around lifecycle, staged/revealed articles, image handling, chat/log behavior, Session Character, and rerender stability.
- The June 25, 2026 browser pass covers inactive/active Session chat
  presentation, the combined Session DM pane, character picker placement,
  specific-player labels without email, player-chat viewport preservation
  during polling, and DM staged-editor state/focus/viewport preservation during
  polling.
- Slice 4.3 verification covers immediate and future real-browser conversion,
  source/destination races, restart-visible provenance, malformed-payload
  refusal, optional-image cleanup and retention, reconciliation refresh faults,
  revision/response faults, audit separation, and preserved route/form/security
  contracts.
- Local Slice 5.3b focused coverage uses `tests/test_campaign_session_page.py` for composer markup, shared-feedback routing, and controller state, and `tests/test_character_read_shell_browser.py` for the `1280x900` parchment and `390x800` moonlit success, validation, delayed-response, transport-failure, and native no-JavaScript matrix. The accepted runtime/test state is exact local commit `f1118200daa3a3b7a0620b17d53c9e2cf00524f1`; it is not on `main`, pushed, deployed, or live. No complete suite was run, and full presentation-domain validation remains due at the assembled Phase 5 freeze.
- Local Slice 5.6b coverage uses `tests/test_campaign_session_page.py`, `tests/test_character_read_shell_browser.py`, and `tests/test_static_assets.py` for dialog structure, initial/lazy/mutation insertion, labels, keyboard and focus behavior, Session state preservation, native fallbacks, fail-safe gates, idempotence, loading exclusion, and legacy Combat isolation. Independent verification passed 439 broad affected tests with one unrelated loading-cover timing failure that passed isolated rerun, all 226 Session tests, five candidate browser/adversarial tests, three Session regressions, six legacy Combat tests, and 138 contract tests with 4,531 deselected. Exact-integration checks passed eight focused tests and the same 138 contract tests. The accepted runtime/test state is exact local commit `db6d0d7aac1eb81bc053b8fe8873843c76a43111`, tree `f7f09ec0ce22799df21ec916bdc3954f9e7393c3`; it exists only on local `codex/flask-rewrite-phase5`, not on `main`, pushed, deployed, or live. No complete suite was run, and the assembled Phase 5 presentation-domain freeze remains the promotion gate.
- Local Slice 5.6c coverage uses `tests/test_campaign_session_page.py`,
  `tests/test_character_read_shell_browser.py`, and
  `tests/test_static_assets.py` for confirmation scope and strength, native
  CSRF fallback, shared-dialog focus behavior, async replacement and
  reinitialization, busy/known/unknown result paths, preserved Session state,
  and shared/static/legacy-Combat isolation. Independent verification passed
  all 226 Session owner tests, two committed browser tests, one corrected
  independent double-submit/detached-success challenge, ten
  shared/static/legacy-Combat controls, and 138 contract tests with 4,534
  deselected. Exact-integration checks used the canonical Python 3.12.12
  environment with all 29 locked dependencies and passed four focused tests
  plus the same 138 contract tests. The accepted runtime/test state is exact
  local commit `1079dce2a1c024802c328db9e4fa92336ca30cbc`, tree
  `4363e7152659abf96401e0df6f557dfba222d236`; it exists only on local
  `codex/flask-rewrite-phase5`, not on `main`, pushed, deployed, or live. No
  complete suite was run, and the assembled Phase 5 presentation-domain freeze
  remains the promotion gate.

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
- `player_wiki/app.py`
- `player_wiki/api.py`
- `player_wiki/session_source_presenter.py`
- `player_wiki/templates/session.html`
- `player_wiki/templates/session_dm.html`
- `player_wiki/templates/_session_composer_card.html`
- `player_wiki/templates/_session_revealed_articles_card.html`
- `player_wiki/templates/_destructive_confirmation.html`
- `player_wiki/static/session-live.js`
- `player_wiki/static/presentation-controller.js`
- `player_wiki/templates/_session_character_panel.html`
- `player_wiki/templates/_session_character_dnd_workspace.html`
- `player_wiki/templates/_combat_workspace_scripts.html`
- `tests/test_campaign_session_page.py`
- `tests/test_character_read_shell_browser.py`
- `tests/test_static_assets.py`
- `tests/test_api_session.py`
- `tests/test_route_contract_manifest.py`
