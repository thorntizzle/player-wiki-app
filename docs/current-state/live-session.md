# Live Session

Last updated: 2026-07-14

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

- This ownership inventory is verified on `codex/flask-rewrite-phase3b` at `44a95ba3b3f6143857c857835a9724a7b7cca16a` only. It does not yet describe `main`, the deployed app, or live production state.
- `player_wiki/session_routes.py` owns the Session Blueprint and all 19 live-session browser handlers/rules: nine GET and ten POST rules. `player_wiki/session_api_routes.py` owns all 13 live-session JSON handlers/rules through explicit registrations on the existing API Blueprint. Public Flask and `api.*` endpoint identifiers, methods, wrapper order, payloads, and implicit `HEAD`/`OPTIONS` behavior remain unchanged.
- `player_wiki/app.py` and `player_wiki/api.py` retain shared Session context builders, renderers, serializers, request/auth/error helpers, service composition, and registrar dependency wiring. The qualified inventory leaves 89 decorator registrations in `app.py` and 107 in `api.py`.
- `/session/character` and the character-session route family remain Characters-owned even when surfaced inside the Session shell. Low-level content APIs remain Publishing-owned. Neither family is part of the 19 browser plus 13 API live-session transport inventory.

## Session Article Contract

- Session article store creation modes are Manual, Upload, and Lookup.
- Upload mode accepts UTF-8 `.md` or `.markdown` files and can attach separately uploaded referenced images from frontmatter, Markdown images, or Obsidian embeds.
- Lookup mode lazily searches visible published wiki pages plus accessible Systems entries and stages a revealable snapshot.
- Staged articles are hidden from wiki/search until converted or saved through the Player Wiki editor.
- DMs/admins can update unrevealed staged article title, body, image alt/caption, or replacement image from Session DM or DM Content -> `Staged Articles`.
- Revealed session articles render into the session chat feed and remain visible in stored DM chat logs.

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

## Known Limits

- No Session-specific anti-jumpiness items are currently open after the June 25, 2026 browser verification pass. Cross-surface refresh work should use the owning current-state doc and backlog.

## Related Backlog

- `.local/roadmaps/session-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`
- `.local/roadmaps/publishing-backlog.md`

## Source Pointers

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
