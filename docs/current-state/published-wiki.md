# Published Wiki And Publishing

Last updated: 2026-07-12

## Owns

- Player-facing wiki pages, Campaign Home, section/category navigation, page publication, page images, content API writes, session-article promotion, and local/live content conventions.

## Current User-Facing Behavior

- Published wiki pages are read-only for players and manageable by DMs/admins through DM Content -> `Player Wiki` or the content API.
- Campaign Home is the player-facing landing view for a campaign. It shows the latest visible published session summary as a news-style card above the section list, while section and article pages use section navigation and backlinks.
- Campaign Home section cards, wiki section navigation, page cards, backlinks, and rendered internal article-body links use ordinary Flask `href` values.
- The shared global search row is the ordinary ad hoc lookup path for visible wiki pages and accessible Systems entries. Flask Campaign Home no longer owns a visible page-local search form, though old `?q=` URLs remain compatible.
- Page detail views lead with article title and optional summary. They can render an optional image between summary and body.
- Article images are campaign-owned protected assets, not public static files. PNG/JPG image uploads are converted to WebP by the shared image-publishing helper, while GIF/WebP uploads pass through validation; character portrait uploads reuse that same conversion rule.
- Protected campaign assets follow Wiki-scope access. Existing contained assets remain readable within that scope even when no visible published page links to them; path traversal outside the campaign asset root remains denied.
- The publishing transport owns the protected asset, section, and page reads. Their bare Flask endpoint identifiers (`campaign_asset`, `section_view`, and `page_view`) are supported compatibility surfaces, with exactly one registered rule per path.
- `Overview` pages and `type: overview` pages are legacy artifacts and are not visible through public wiki discovery, section navigation, search, section routes, or direct page routes.

## Current Content Conventions

- Current sections include `Sessions`, `Notes`, `Locations`, `NPCs`, `Races`, `Factions`, `Gods`, `Discoveries`, `Bestiary`, `Items`, `Spells`, `Mechanics`, and `Lore`.
- `Bestiary` is the dedicated player-facing section for enemy or monster articles the party has encountered; do not place those articles in `Discoveries`.
- The Campaign Home latest-session card is selected from visible published pages where `section: Sessions` and `type: session`, ordered by highest `reveal_after_session` with stable title/slug tie-breaks.
- Grouped section pages can use subsections and top-level featured pages.
- Pages with `display_order < 10000` render as pinned featured cards at the top of their section or subsection.
- Gods use subsection-aware display labels in cards and search results.
- Item, spell, and mechanic detail pages suppress the summary lede even when summaries appear in cards/search.
- Published item pages are player-facing prose and can be linked as provenance for campaign-owned Systems `item` mechanics records. The Systems item record, not the article body alone, is the mechanics intake/source of truth for character-facing behavior.
- Current publication conventions for guilds, gods, civic NPCs, NPC buckets, notes, session handouts, Bestiary articles, and images are documented in the app repo map until fully atomized here.

## Management And Safety Contract

- Browser Player Wiki management can create, edit, search, attach inline page images, promote staged/session articles, unpublish/archive, and hard-delete published pages. Publishing transport owns the six edit, session-article prefill, create, update, unpublish/archive, and checked-delete handlers shown inside the DM Content product surface.
- Those handlers retain the supported bare Flask endpoint identifiers `campaign_dm_content_edit_player_wiki_page`, `campaign_dm_content_new_player_wiki_page_from_session_article`, `campaign_dm_content_create_player_wiki_page`, `campaign_dm_content_update_player_wiki_page`, `campaign_dm_content_unpublish_player_wiki_page`, and `campaign_dm_content_delete_player_wiki_page`. Their route-policy and manifest ownership remains `dm-content`; product-surface ownership is distinct from publishing transport/module ownership.
- Creating a page with a nonblank `source_session_article_id` also requires Session-manager authority. That check occurs before source-article lookup or mutation side effects, so unauthorized callers receive the same 403 for valid and nonexistent source IDs. Blank or absent source IDs retain ordinary content-manager page creation behavior.
- Published page writes keep the SQLite read model plus mirrored Markdown in sync through `campaign_content_service`.
- DM Content -> `Systems` can import/refresh a structured campaign item record from an existing published item page. DM Content -> `Player Wiki` remains the place to edit the public item article.
- Hard delete is blocked when backlinks, character hooks or sheet references, session article source refs, or session-article conversion provenance make removal risky unless an explicit force path is used where supported.
- Session-only articles stay out of wiki/search until converted or saved through the Player Wiki editor promotion path.

## Current Tests Or Verification

- Publishing/wiki changes usually need focused route/API tests around section grouping, visibility, content API writes, image serving, removal safety, and Flask page rendering.
- Live content writes through the API do not update local content mirrors automatically; sync down from Fly when local state must match live.

## Known Limits

- Some advanced publishing workflows are still browser-first, especially session-article prefill/promotion and automatic WebP conversion.

## Related Backlog

- `.local/roadmaps/publishing-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`

## Source Pointers

- `player_wiki/repository.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/campaign_wiki_safety.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/publishing_mutations.py`
- `player_wiki/publisher.py`
- `player_wiki/session_article_publisher.py`
- `docs/api-v1.md`
