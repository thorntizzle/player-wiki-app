# DM Content

Last updated: 2026-07-12

## Owns

- DM-facing Statblocks, Player Wiki management, Systems management lane, Staged Articles, Conditions, and their handoffs into combat, publishing, and live Session workflows.

## Current User-Facing Behavior

- DM Content is a campaign page with default `dm` visibility.
- Current lanes are `Statblocks`, `Player Wiki`, `Systems`, `Staged Articles`, and `Conditions`.
- The compatibility `/dm-content` entry still defaults to the statblock lane.
- Flask covers ordinary statblock/condition management, staged-article prep, Player Wiki create/search/load/edit/archive/checked-delete, image asset upload, and Systems management lane behavior. DM Content remains the product surface and route-policy/manifest domain for Player Wiki management, while the publishing transport owns its six edit, session-article prefill, create, update, unpublish/archive, and checked-delete handlers.

## Lane Contracts

- Statblocks accepts UTF-8 `.md` or `.markdown` uploads and can edit stored source Markdown body/subsection labels. The parser uses frontmatter `title`/`name`, then first non-generic heading, then `Name:`, then filename.
- Player Wiki manages published Markdown pages through `campaign_content_service`, preserves unknown frontmatter, syncs the SQLite read model plus mirrored Markdown, and blocks unsafe hard delete through the shared removal-safety rules. The six publishing-owned management handlers retain their supported bare Flask endpoint identifiers rather than Blueprint-namespaced identifiers. The page editor section choices include `Bestiary` for encountered-enemy or monster articles.
- Player Wiki creation with a nonblank `source_session_article_id` requires Session-manager authority before the source is looked up or any mutation-side-effect code runs. Unauthorized valid and nonexistent source IDs both return the same 403; blank or absent source IDs do not add the Session-manager requirement.
- Systems separates Source Enablement, Entry Overrides, Custom Entries, Shared Source Imports, and Import-Run History.
- Staged Articles writes directly into the Session DM staged article queue. Reveal timing and revealed-article management remain on Session DM.
- Conditions creates, edits, and deletes custom combat condition definitions, which augment the built-in DND-5E condition list.

## Cross-Surface Handoffs

- Statblocks populate the DM-side combat NPC picker and copy parsed combat seed fields into new combatants.
- Staged articles can be edited before reveal or conversion and can open in the Player Wiki editor before publication.
- Player Wiki image uploads and promoted session-article images are copied into campaign assets under `wiki-pages/`.
- Systems source policy and custom entries affect Systems browsing and downstream character/combat links.

## Current Tests Or Verification

- DM Content changes usually need focused route/API tests around the touched lane, plus combat/publishing/session checks when a handoff changes.

## Known Limits

- Some advanced session-article prefill/promotion and automatic WebP conversion behavior remains browser-first rather than raw API-first.

## Related Backlog

- `.local/roadmaps/dm-content-backlog.md`
- `.local/roadmaps/publishing-backlog.md`
- `.local/roadmaps/systems-backlog.md`
- `.local/roadmaps/session-backlog.md`
- `.local/roadmaps/combat-backlog.md`

## Source Pointers

- `player_wiki/campaign_dm_content_store.py`
- `player_wiki/campaign_dm_content_service.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/publishing_mutations.py`
- `player_wiki/templates/dm_content.html`
