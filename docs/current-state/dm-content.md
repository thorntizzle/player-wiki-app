# DM Content

Last updated: 2026-07-22

## Owns

- DM-facing Statblocks, Player Wiki management, Systems management lane, Staged Articles, Conditions, and their handoffs into combat, publishing, and live Session workflows.

## Current User-Facing Behavior

- DM Content is a campaign page with default `dm` visibility.
- Current lanes are `Statblocks`, `Player Wiki`, `Systems`, `Staged Articles`, and `Conditions`.
- The compatibility `/dm-content` entry still defaults to the statblock lane.
- Flask covers ordinary statblock/condition management, staged-article prep, Player Wiki create/search/load/edit/archive/checked-delete, image asset upload, and Systems management lane behavior. DM Content remains the product surface and route-policy/manifest domain for Player Wiki management, while the publishing transport owns its six edit, session-article prefill, create, update, unpublish/archive, and checked-delete handlers. DM Content likewise remains the product and policy domain for statblocks and custom conditions, while `player_wiki/dm_content_routes.py` owns their six upload/create, update, and delete mutation controllers.

## Lane Contracts

- Statblocks accepts UTF-8 `.md` or `.markdown` uploads and can edit stored source Markdown body/subsection labels. The parser uses frontmatter `title`/`name`, then first non-generic heading, then `Name:`, then filename. The DM Content service and store persist statblock bodies and parsed fields in SQLite only; these routes do not retain the upload or create mirrored Markdown.
- Player Wiki preserves unknown frontmatter and blocks unsafe hard delete
  through the shared removal-safety rules. Browser create, update, and
  unpublish route sanitized mirrored-Markdown, optional changed-image, SQLite
  read-model, browser-audit, and repository-refresh work through the durable
  `player_wiki_reconciliation` coordinator. Its private recovery journal is
  not exposed in DM Content, APIs, logs, audits, or ordinary page reads. The six
  publishing-owned management handlers retain their supported bare Flask
  endpoint identifiers rather than Blueprint-namespaced identifiers. The page
  editor section choices include `Bestiary` for encountered-enemy or monster
  articles.
- The Player Wiki lane now leads with search and recently updated pages before
  its result list. Unfiltered pages use descending `updated_at` ordering with
  stable title and page-reference ties; matching searches retain the query and
  use a `Search results` state, while no-match searches use an explicit empty
  state. The native details-based editor follows search and conservative
  outcome guidance, precedes results, and is closed by default. It opens for
  edit, Session prefill, retained submitted validation/error state, and
  advanced-field state when required. Primary authoring fields stay visible;
  advanced publishing, provenance, and image fields remain nested. Direct
  GETs, editor anchors, native no-JavaScript forms, and the staged Session
  handoff remain intact.
- Static Player Wiki guidance says to refresh or search the current page list
  before repeating an action whose result could not be confirmed. It coexists
  with known validation feedback, makes no success, failure, rollback, repair,
  or safe-retry claim, and exposes no private journal, blind retry, repair
  surface, or unpublished-draft surface.
- Browser checked-delete retains its existing content-manager authorization,
  CSRF, explicit confirmation, reference-blocker refusal, flash/redirect, and
  status behavior. A successful delete now completes through the private
  deletion journal and records exactly one
  `campaign_wiki_page_deleted` browser audit; page assets are retained.
- Archive/unpublish is the lane's normal visible removal action and hides a
  page without deleting its Markdown. Blocked pages show exact blockers and
  archive guidance without any hard-delete disclosure, form, acknowledgement,
  button, or disabled substitute. Only a currently unreferenced safe page shows
  a closed native hard-delete exception disclosure naming the exact title and
  `.md` page reference, permanent removal of the file and Player Wiki entry,
  browser irreversibility, and retained unchanged campaign assets. The existing
  CSRF POST requires `confirm_delete=1`; browser presentation and submission do
  not expose `force`. Removal policy, blocker graph, transport, persistence,
  authorization, status, audit, and asset-retention behavior are unchanged.
- These Player Wiki presentation statements for Phase 7 Slices 7.1 through 7.3
  were independently accepted on the local integrated Phase 7 branch at
  `a704e5f9090e60fc16ae47f7843e7392ee177e6c`. They are not pushed, merged to
  `main`, deployed, or live, and the slices performed no content or database
  writes.
- Player Wiki creation with a nonblank `source_session_article_id` requires Session-manager authority before the source is looked up or any mutation-side-effect code runs. Unauthorized valid and nonexistent source IDs both return the same 403; blank or absent source IDs do not add the Session-manager requirement.
- Systems separates Source Enablement, Entry Overrides, Custom Entries, Shared Source Imports, and Import-Run History.
- Staged Articles writes directly into the Session DM staged article queue. Reveal timing and revealed-article management remain on Session DM.
- Conditions creates, edits, and deletes SQLite-backed custom combat condition definitions, which augment the built-in DND-5E condition list by name. The six statblock/condition mutation routes retain their supported bare Flask endpoint identifiers through an explicit compatibility registration layer, with exactly one registered rule per method/path.

## Cross-Surface Handoffs

- Statblocks populate the DM-side combat NPC picker. Seeding copies the creation-time combat values, resource counters, and statblock source identity into the new combatant; later source edits do not rewrite that snapshot or bump the Combat revision. DM Combat detail reads the current source record dynamically, and a deleted source leaves the copied combatant state intact with the existing unavailable-source fallback.
- Custom conditions are name-only suggestions in the Combat picker. Active Combat conditions do not retain a definition identity, so renaming or deleting a definition changes future picker options without rewriting existing active-condition rows or bumping the Combat revision.
- Staged articles can be edited before reveal or conversion and can open in the Player Wiki editor before publication.
- Player Wiki image uploads and promoted session-article images are copied into campaign assets under `wiki-pages/`.
- Systems source policy and custom entries affect Systems browsing and downstream character/combat links.

## Current Tests Or Verification

- DM Content changes usually need focused route/API tests around the touched lane, plus combat/publishing/session checks when a handoff changes.
- Phase 7 Slices 7.1 through 7.3 have focused Flask assertions for Player Wiki
  ordering/search, editor state and native form/deep-link behavior, static
  outcome guidance, nested fields, absence of draft-preview/force controls, and
  safe-removal presentation, plus Chromium matrices for the native workflow and
  safe removal. The accepted evidence did not include a complete test suite.

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
- `player_wiki/dm_content_routes.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/publishing_mutations.py`
- `player_wiki/player_wiki_reconciliation.py`
- `player_wiki/app.py`
- `player_wiki/templates/dm_content.html`
- `tests/test_dm_content_player_wiki.py`
- `tests/test_dm_content_player_wiki_browser.py`
