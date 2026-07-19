# Live Session

Last updated: 2026-07-18

## Owns

- Player Session, DM Session, Session Character, staged/revealed articles, chat logs, session article images, polling, live rerender stability, and session-to-publishing handoffs.

## Current User-Facing Behavior

- Live Session is distinct from published `Sessions` recap pages.
- `/session`, `/session/character`, and `/session/dm` share one Session shell. Enhanced tab clicks switch panes through History API without full document navigation.
- Player Session owns live chat, message composition, visible revealed article chat entries, and player-facing active/inactive state. Inactive sessions render a compact inactive-state card instead of the chat window and composer; chat appears only while a session is active.
- DM Session owns live lifecycle controls, staged articles, revealed articles, passive score cards, Session article store, and chat logs. These are split into `dm_view` subviews: `DM Tools`, `Staged Articles`, `Revealed Articles`, `Stage Session Articles`, and `Chat Logs`. `DM Tools` contains passive scores and live-session controls.
- Session message specific-player labels use character-first display when possible: `Character Name (username)`. Players without assigned characters fall back to username, duplicate labels are disambiguated with the user id, and emails are not shown in the picker.
- Session Character can mount inside the player Session shell and also remains available as a full-page/no-JS fallback. The Session Character picker sits below the Session/Character/DM navigation and outside the character card, with `Open full character page` in the same row; the duplicate `Session Character` header is omitted inside the embedded sheet.
- DND-5E Session Character uses DND sheet sections and active-session controls for HP/temp HP/Hit Dice, resources, spell slots, equipment state, inventory quantities, currency, notes, and rests. Editable resource cards use the shared resource mutation and include a visible per-card `Save` action in addition to blur autosave. Rest confirmations can set final Current HP and current Hit Dice before applying the rest.
- Session Character Inventory and Equipment reuse the compact shared item-grid convention, using up to three columns where space allows and one-column mobile stacking without losing quantity, item-detail, or equipment-state controls.
- Xianxia Session Character mirrors Xianxia read-sheet subpages except `Controls`, which stays on the full Character page.

## Technical Ownership

- This ownership inventory is integrated on pushed `main` and deployed as Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. The later documentation closeout is not part of the deployed image.
- The Session-to-wiki one-shot durability contract is verified and locally
  integrated only on `codex/flask-rewrite-phase4`. Runtime commit
  `a6ea9da737f1a12739085cb6bb71763671d6c9e4`, a separate rollback unit from
  durable pre-slice commit `223ab5898c476e16b166c82279b93b18d29b4f2c`, is
  included in pre-documentation durable head
  `34b4731ace8e0ffb402d8cf320718fde4cdd0967`. It has not been pushed, merged
  to `main`, deployed, or applied through a live content or database write.
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
- Player Session polling should preserve the viewport while a user is reading older chat messages.
- DM Session subviews should preserve staged-article edit drafts, open details, focus, selected log state, and viewport anchors across live polling, status refreshes, and pane switches.
- DM staged/revealed article details should preserve open state across live polling and async mutation rerenders.
- Revision values, view tokens, and state revisions are implementation details; do not render user-facing `Revision` or `Live revision` counters.

## Current Tests Or Verification

- Session changes usually need focused route tests, browser checks, or direct API checks around lifecycle, staged/revealed articles, image handling, chat/log behavior, Session Character, and rerender stability.
- The June 25, 2026 browser pass covers inactive/active Session chat presentation, Session DM subviews, character picker placement, specific-player labels without email, player-chat viewport preservation during polling, and DM staged-editor state/focus/viewport preservation during polling.
- Slice 4.3 verification covers immediate and future real-browser conversion,
  source/destination races, restart-visible provenance, malformed-payload
  refusal, optional-image cleanup and retention, reconciliation refresh faults,
  revision/response faults, audit separation, and preserved route/form/security
  contracts.

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
- `player_wiki/templates/_session_character_panel.html`
- `tests/test_campaign_session_page.py`
- `tests/test_api_session.py`
- `tests/test_route_contract_manifest.py`
