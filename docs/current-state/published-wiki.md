# Published Wiki And Publishing

Last updated: 2026-07-19

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

- The Session-to-wiki one-shot durability statements below were independently
  verified in Phase 4 and are included in pushed `main` and deployed Fly
  release `224` from exact clean runtime commit
  `b80af7c7b441bb2fcecc763bf6ea4a73f9d85365`. The deployment performed no
  explicit database/content sync or private-data write.
- Browser Player Wiki management can create, edit, search, attach inline page images, promote staged/session articles, unpublish/archive, and hard-delete published pages. Publishing transport owns the six edit, session-article prefill, create, update, unpublish/archive, and checked-delete handlers shown inside the DM Content product surface.
- Those handlers retain the supported bare Flask endpoint identifiers `campaign_dm_content_edit_player_wiki_page`, `campaign_dm_content_new_player_wiki_page_from_session_article`, `campaign_dm_content_create_player_wiki_page`, `campaign_dm_content_update_player_wiki_page`, `campaign_dm_content_unpublish_player_wiki_page`, and `campaign_dm_content_delete_player_wiki_page`. Their route-policy and manifest ownership remains `dm-content`; product-surface ownership is distinct from publishing transport/module ownership.
- Creating a page with a nonblank `source_session_article_id` also requires Session-manager authority. That check occurs before source-article lookup or mutation side effects, so unauthorized callers receive the same 403 for valid and nonexistent source IDs. Blank or absent source IDs retain ordinary content-manager page creation behavior.
- Browser page create, update, and unpublish plus API page upsert use the
  `player_wiki_reconciliation` coordinator to publish authoritative mirrored
  Markdown before completing the SQLite read model. Browser authorization,
  CSRF, response behavior, and audit behavior remain unchanged; the API path
  retains its existing authorization and response boundary and does not add a
  browser audit.
- The coordinator keeps the exact sanitized rendered Markdown in a private,
  transient recovery BLOB while an operation is prepared. The payload must be
  nonempty and no larger than 96 MiB; it is not a read authority and is never
  returned through the API, logs, or audit metadata. Image bytes are not stored
  in the journal.
- A changed image is published as the primary file; an identical image or an
  operation without an image is Markdown-primary. After an image commit, the
  coordinator verifies or atomically publishes the desired Markdown before it
  updates SQLite. Page-row and browser-audit writes plus the transition to
  `repository_pending` share one SQLite transaction. Repository refresh is
  derived from that finalized database state, final file authority is checked
  again, and successful cleanup deletes the journal row rather than retaining
  completed operations.
- Recovery classifies each prepared file as previous, desired, or a third
  conflicting state. Conflicts retain the private Markdown payload and block
  new operations for that page until explicit repair or abandonment.
  `repository_pending` operations have already cleared that payload and retry
  refresh and cleanup. While a prepared, repository-pending, or conflicted
  operation exists, filesystem reload skips upsert and deletion for that page
  across restarts while continuing to synchronize unrelated pages; normal
  reload resumes after journal deletion.
- Successful hard delete uses a distinct deletion journal. After journaling, it
  atomically moves the bounded regular Markdown file without replacement to a
  short, private, same-directory operation tombstone whose name does not end in
  `.md`; that move is the deletion commit. Symlink and Windows reparse sources,
  out-of-bound paths, existing tombstone destinations, empty files, and files
  larger than 96 MiB are rejected. Page-row deletion, the single browser audit
  when applicable, and `repository_pending` share one SQLite transaction;
  refresh reads finalized SQLite, then durable tombstone cleanup and journal
  deletion complete forward. API deletion writes no browser audit. Referenced
  and unreferenced campaign assets are always retained.
- Deletion recovery recognizes the precommit, committed, completed, and
  conflicting file arrangements without repeating the page delete or browser
  audit. Prepared, repository-pending, and conflict deletion rows protect that
  page from filesystem reload upsert/deletion across restart while unrelated
  pages continue to synchronize. A conflict retains the journal and any private
  tombstone evidence; successful retry removes the tombstone and journal so
  normal sync resumes.
- The operator reconciliation dry run reports only active journal-owned
  publication and deletion work; it is not a generic Markdown, image, or
  repository-drift audit. Its redacted classifications distinguish abortable,
  forward-recoverable, refresh/cleanup-retryable, conflicting, and
  manual-attention states without publishing, deleting, refreshing, recovering,
  or otherwise repairing content. Every recommended mutation is advisory and
  marked as requiring a backup.
- A separate local CLI-only apply command can execute one exact active
  publication or deletion operation by 32-hex operation ID. It supports only
  `abandon-precommit`, `resume-forward`, and `retry-refresh-cleanup`, requires
  explicit `--yes`, and can accept an optional backup directory. It refuses
  manual-conflict and manual-attention cases rather than inferring a repair.
- Apply refuses active restore recovery, holds the exclusive runtime lease,
  requires stable current-version-9 exact inspection evidence, creates a
  verified-v2 safety backup, revalidates the same operation and recommendation,
  delegates mutation to the existing coordinator, and proves terminal journal
  deletion. Repeating a completed request reports `no_active_operation`.
  Failure output is redacted; success may retain and report the verified backup
  path and bounded evidence. This adds no browser or API repair path, live or
  bulk operation, policy or schema change, or character-journal authority.
- Each mirrored Markdown file and each uploaded or generated campaign asset is
  published through a flushed and fsynced temporary sibling in the destination
  directory followed by atomic replacement. Concurrent readers therefore see
  either the prior file or the complete replacement file, rather than a
  truncated or partially written file. File formats, final paths, sanitization,
  size/type validation, protected serving, and caller ordering remain unchanged.
  This per-file guarantee does not make a multi-file page/image operation, a
  SQLite write, an audit write, or repository refresh transactionally atomic;
  it also does not provide cross-file atomicity. The Player Wiki coordinator
  supplies durable forward recovery across those boundaries, not a claim of
  filesystem/database atomicity.
- Campaign Item Mechanics import/refresh is available only through the JSON API
  or operator CLI. DM Content -> `Systems` does not render a browser lane for
  that operation; DM Content -> `Player Wiki` remains the place to edit the
  public item article.
- Hard delete is blocked when backlinks, character hooks or sheet references, session article source refs, or session-article conversion provenance make removal risky unless an explicit force path is used where supported. Slice 4.2b changes durable deletion mechanics, not this blocker graph or the Markdown/image reference policy.
- Session-only articles stay out of wiki/search until converted or saved through the Player Wiki editor promotion path.
- Direct Session conversion and Player Wiki editor promotion share the stable
  sanitized provenance
  `source_ref: session-article:<campaign>:<article-id>`. A keyed source lock and
  persisted finalized or active prepared/conflict provenance guard the source
  across restart. Unrelated valid provenance remains allowed; malformed private
  reconciliation payload fails closed without exposing its content.
- One-shot conversion prepares the page and optional validated/converted image
  for the Player Wiki coordinator. Destination creation has one transactional
  winner across competing one-shot and editor paths; the loser neither
  overwrites the winner nor leaves an orphaned asset. A committed converted
  asset is protected campaign content and survives deletion of the source
  Session article. Cleanup is limited to losing or otherwise uncommitted image
  preparation.
- Forward reconciliation supplies retryable completion rather than a claim of
  cross-filesystem/database atomicity. A refresh failure leaves
  `repository_pending`; a later Session live-revision failure leaves the
  committed page/image readable; and a response fault after the revision bump
  does not repeat that bump. Normal one-shot success bumps the live revision
  once. Immediate content redirects to its readable wiki page, while a future
  reveal returns to the conversion form as `Already converted` and remains 404
  to players until its reveal threshold.
- The direct one-shot path deliberately omits the browser
  `campaign_wiki_page_created` audit; the Player Wiki editor promotion path
  retains it. Existing manager authorization, CSRF, validation, submitted-form
  preservation, route, flash, and redirect behavior remains unchanged.

## Current Tests Or Verification

- Publishing/wiki changes usually need focused route/API tests around section grouping, visibility, content API writes, image serving, removal safety, and Flask page rendering.
- Live content writes through the API do not update local content mirrors automatically; sync down from Fly when local state must match live.
- Slice 4.3 verification covers source and destination concurrency, persisted
  restart guards, fail-closed private provenance parsing, image lifecycle,
  reconciliation/revision/response faults, audit separation, and immediate and
  future real-browser publication behavior.

## Known Limits

- Some advanced publishing workflows are still browser-first, especially session-article prefill/promotion and automatic WebP conversion.

## Related Backlog

- `.local/roadmaps/publishing-backlog.md`
- `.local/roadmaps/dm-content-backlog.md`

## Source Pointers

- Primary Slice 4.3 sources and focused tests:
  `player_wiki/session_article_publisher.py`,
  `player_wiki/publishing_mutations.py`,
  `player_wiki/player_wiki_reconciliation.py`,
  `player_wiki/session_routes.py`,
  `tests/test_campaign_session_page.py`,
  `tests/test_dm_content_player_wiki.py`, and
  `tests/test_player_wiki_reconciliation.py`.
- `player_wiki/repository.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/file_publication.py`
- `player_wiki/player_wiki_reconciliation.py`
- `player_wiki/player_wiki_reconciliation_inspection.py`
- `player_wiki/player_wiki_reconciliation_operations.py`
- `ops.py`
- `local.ps1`
- `tests/test_player_wiki_reconciliation_operations.py`
- `player_wiki/campaign_wiki_safety.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/publishing_mutations.py`
- `player_wiki/publisher.py`
- `player_wiki/session_article_publisher.py`
- `docs/api-v1.md`
