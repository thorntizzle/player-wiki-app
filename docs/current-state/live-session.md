# Live Session

Last updated: 2026-06-25

## Owns

- Player Session, DM Session, Session Character, staged/revealed articles, chat logs, session article images, polling, live rerender stability, and session-to-publishing handoffs.

## Current User-Facing Behavior

- Live Session is distinct from published `Sessions` recap pages.
- `/session`, `/session/character`, and `/session/dm` share one Session shell. Enhanced tab clicks switch panes through History API without full document navigation.
- Player Session owns live chat, message composition, visible revealed article chat entries, and player-facing active/inactive state. In Gen2, inactive sessions render a compact inactive-state card instead of the chat window and composer; chat appears only while a session is active.
- DM Session owns live lifecycle controls, staged articles, revealed articles, passive score cards, Session article store, and chat logs. In Gen2 these are split into mounted `dm_view` subviews: `DM Tools`, `Staged Articles`, `Revealed Articles`, `Stage Session Articles`, and `Chat Logs`. `DM Tools` contains passive scores, a future DM references card, and live-session controls.
- Session message specific-player labels use character-first display when possible: `Character Name (username)`. Players without assigned characters fall back to username, duplicate labels are disambiguated with the user id, and emails are not shown in the picker.
- Session Character can mount inside the player Session shell and also remains available as a full-page/no-JS fallback. In Gen2, the Session Character picker sits below the Session/Character/DM navigation and outside the character card, with `Open full character page` in the same row; the duplicate `Session Character` header is omitted inside the embedded sheet.
- DND-5E Session Character uses DND sheet sections and active-session controls for HP/temp HP/Hit Dice, resources, spell slots, equipment state, inventory quantities, currency, notes, and rests. Editable resource cards use the shared resource mutation and include a visible per-card `Save` action in addition to blur autosave. Rest confirmations can set final Current HP and current Hit Dice before applying the rest.
- Session Character Inventory and Equipment reuse the compact shared item-grid convention, using up to three columns where space allows and one-column mobile stacking without losing quantity, item-detail, or equipment-state controls.
- Xianxia Session Character mirrors Xianxia read-sheet subpages except `Controls`, which stays on the full Character page.

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
- Gen2 Player Session polling should preserve the viewport while a user is reading older chat messages.
- Gen2 DM Session subviews stay mounted while hidden so staged-article edit drafts, open details, focus, selected log state, and viewport anchors survive live polling, status refreshes, and pane switches.
- DM staged/revealed article details should preserve open state across live polling and async mutation rerenders.
- Revision values, view tokens, and state revisions are implementation details; do not render user-facing `Revision` or `Live revision` counters.

## Current Tests Or Verification

- Session changes usually need focused route tests, browser checks, or direct API checks around lifecycle, staged/revealed articles, image handling, chat/log behavior, Session Character, and rerender stability.
- The June 25, 2026 Gen2 browser pass covers inactive/active Session chat presentation, Session DM subviews, character picker placement, specific-player labels without email, player-chat viewport preservation during polling, and DM staged-editor state/focus/viewport preservation during polling.

## Known Limits

- No Session-specific anti-jumpiness items are currently open after the June 25, 2026 browser verification pass. Cross-surface refresh work should use the owning current-state doc and backlog.

## Related Backlog

- `.local/roadmaps/live-combat-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`
- `.local/roadmaps/publishing-backlog.md`

## Source Pointers

- `player_wiki/campaign_session_store.py`
- `player_wiki/campaign_session_service.py`
- `player_wiki/session_source_presenter.py`
- `player_wiki/templates/session.html`
- `player_wiki/templates/session_dm.html`
- `player_wiki/templates/_session_character_panel.html`
- `frontend/src/pages/SessionPage.tsx`
- `frontend/src/pages/SessionRoutes.tsx`
- `frontend/src/pages/SessionDmPane.tsx`
- `frontend/src/sessionDmMutations.ts`
- `tests/test_campaign_session_page.py`
