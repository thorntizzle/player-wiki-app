# Live Session

Last updated: 2026-06-25

## Owns

- Player Session, DM Session, Session Character, staged/revealed articles, chat logs, session article images, polling, live rerender stability, and session-to-publishing handoffs.

## Current User-Facing Behavior

- Live Session is distinct from published `Sessions` recap pages.
- `/session`, `/session/character`, and `/session/dm` share one Session shell. Enhanced tab clicks switch panes through History API without full document navigation.
- Player Session owns live chat, message composition, visible revealed article chat entries, and player-facing active/inactive state.
- DM Session owns live lifecycle controls, staged articles, revealed articles, passive score cards, Session article store, and chat logs.
- Session Character can mount inside the player Session shell and also remains available as a full-page/no-JS fallback.
- DND-5E Session Character uses DND sheet sections and active-session controls for HP/temp HP/Hit Dice, resources, spell slots, equipment state, inventory quantities, currency, notes, and rests.
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
- DM staged/revealed article details should preserve open state across live polling and async mutation rerenders.
- Revision values, view tokens, and state revisions are implementation details; do not render user-facing `Revision` or `Live revision` counters.

## Current Tests Or Verification

- Session changes usually need focused route tests, browser checks, or direct API checks around lifecycle, staged/revealed articles, image handling, chat/log behavior, Session Character, and rerender stability.

## Known Limits

- Anti-jumpiness coverage still has open follow-up items for some Session and cross-surface refresh paths.

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
