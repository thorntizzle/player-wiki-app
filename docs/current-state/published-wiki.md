# Published Wiki And Publishing

Last updated: 2026-06-25

## Owns

- Player-facing wiki pages, Campaign Home, section/category navigation, page publication, page images, content API writes, session-article promotion, and local/live content conventions.

## Current User-Facing Behavior

- Published wiki pages are read-only for players and manageable by DMs/admins through DM Content -> `Player Wiki` or the content API.
- Campaign Home is the player-facing landing view for a campaign. Gen2 uses section-card browsing; section and article pages use section navigation and backlinks.
- The shared global search row is the ordinary ad hoc lookup path for visible wiki pages and accessible Systems entries. Flask Campaign Home no longer owns a visible page-local search form, though old `?q=` URLs remain compatible.
- Page detail views lead with article title and optional summary. They can render an optional image between summary and body.
- Article images are campaign-owned protected assets, not public static files.
- `Overview` pages and `type: overview` pages are legacy artifacts and are not visible through public wiki discovery, section navigation, search, section routes, or direct page routes.

## Current Content Conventions

- Current sections include `Sessions`, `Notes`, `Locations`, `NPCs`, `Races`, `Factions`, `Gods`, `Discoveries`, `Items`, `Spells`, `Mechanics`, and `Lore`.
- Grouped section pages can use subsections and top-level featured pages.
- Pages with `display_order < 10000` render as pinned featured cards at the top of their section or subsection.
- Gods use subsection-aware display labels in cards and search results.
- Item, spell, and mechanic detail pages suppress the summary lede even when summaries appear in cards/search.
- Current publication conventions for guilds, gods, civic NPCs, NPC buckets, notes, session handouts, and images are documented in the app repo map until fully atomized here.

## Management And Safety Contract

- Browser Player Wiki management can create, edit, search, attach inline page images, promote staged/session articles, unpublish/archive, and hard-delete published pages.
- Published page writes keep the SQLite read model plus mirrored Markdown in sync through `campaign_content_service`.
- Hard delete is blocked when backlinks, character hooks or sheet references, session article source refs, or session-article conversion provenance make removal risky unless an explicit force path is used where supported.
- Session-only articles stay out of wiki/search until converted or saved through the Player Wiki editor promotion path.

## Current Tests Or Verification

- Publishing/wiki changes usually need focused route/API tests around section grouping, visibility, content API writes, image serving, removal safety, and Gen2/Flask page rendering.
- Live content writes through the API do not update local content mirrors automatically; sync down from Fly when local state must match live.

## Known Limits

- The Bestiary split is not implemented. Enemy articles currently remain under existing published sections until the publishing backlog item ships.
- The latest-session-summary Campaign Home news card is not implemented.

## Related Backlog

- `.local/roadmaps/publishing-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`

## Source Pointers

- `player_wiki/repository.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/campaign_wiki_safety.py`
- `player_wiki/publisher.py`
- `player_wiki/session_article_publisher.py`
- `frontend/src/pages/WikiRoutes.tsx`
- `frontend/src/components/WikiChrome.tsx`
- `docs/api-v1.md`
