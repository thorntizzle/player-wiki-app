# Browser JSON Compatibility Decision Gate

Last updated: 2026-06-27

Status: implemented compatibility route evidence for `rewrite/ts-browser-json-compatibility`.

This pass inspected the legacy browser JSON routes that Gen2 still calls outside
`/api/v1`. It implements focused TypeScript compatibility handlers for the four
legacy browser JSON routes so Gen2 does not need to migrate to explicit
`/api/v1` replacements before the TypeScript cutover. Flask remains the
production authority until the broader rewrite cutover is approved.

## Routes In Scope

- `GET /campaigns/<campaign_slug>/global-search`
- `GET /campaigns/<campaign_slug>/global-search/preview`
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/search`
- `GET /campaigns/<campaign_slug>/session/wiki-lookup/preview`

## Evidence

Tracked parity inventory classifies these as initial-cutover blockers unless
equivalent `/api/v1` replacements are built and the frontend client is moved
first:

- `docs/typescript-backend-rewrite/parity-inventory.md`
- `docs/typescript-backend-rewrite/route-snapshots.md`
- `docs/typescript-backend-rewrite/route-snapshots.json`

Flask authority handlers:

- `player_wiki/app.py` around `campaign_global_search`
- `player_wiki/app.py` around `campaign_global_search_preview`
- `player_wiki/app.py` around `campaign_session_wiki_lookup_search`
- `player_wiki/app.py` around `campaign_session_wiki_lookup_preview`

Current Gen2 frontend calls:

- `frontend/src/api/client.ts` `searchCampaignReferences`
- `frontend/src/api/client.ts` `previewCampaignReference`
- `frontend/src/api/client.ts` `searchPlayerSessionWiki`
- `frontend/src/api/client.ts` `previewPlayerSessionWiki`

Pre-implementation TypeScript API search:

- `apps/api/src/routes.ts` has no `global-search` or `wiki-lookup` route entries.
- `apps/api/src/server.ts` has no `global-search` or `wiki-lookup` handlers.
- `docs/typescript-backend-rewrite/typescript-route-seed.json` has no seeded
  compatibility entries for these browser paths.

Implementation evidence:

- `apps/api/src/routes.ts` now declares the four routes as Flask snapshot-family
  browser JSON compatibility entries.
- `apps/api/src/server.ts` now serves focused Hono handlers for global search,
  global search preview, Session wiki lookup search, and Session wiki lookup
  preview.
- `apps/api/tests/browser-json-compatibility.mjs` proves the fixture contract for
  JSON content type, response keys, short queries, successful wiki search,
  empty preview, missing campaign, missing/inaccessible preview resources, and
  Session-scope auth behavior.
- `apps/api/package.json` exposes the focused proof as
  `test:browser-json-compatibility`.

## Current Flask Contract

`GET /campaigns/<campaign_slug>/global-search`:

- Requires campaign-scope access.
- Returns `results` and `message`.
- Queries shorter than 2 characters return an empty result list plus
  `Type at least 2 letters to search wiki pages and Systems entries.`
- Full search returns up to 30 visible wiki page and Systems references.

`GET /campaigns/<campaign_slug>/global-search/preview`:

- Requires campaign-scope access.
- Accepts `result_id`.
- Empty `result_id` returns `{ "preview_html": "" }`.
- Missing or no-longer-visible results return `404` with rendered unavailable
  preview HTML.
- Visible results return rendered `_campaign_global_search_preview.html`.

`GET /campaigns/<campaign_slug>/session/wiki-lookup/search`:

- Requires session-scope access.
- If player-visible wiki is unavailable, returns an empty result list plus
  `No player-visible wiki articles are available right now.`
- Queries shorter than 2 characters return an empty result list plus
  `Type at least 2 letters to search player-visible wiki articles.`
- Full search returns up to 30 player-visible wiki/System article results.

`GET /campaigns/<campaign_slug>/session/wiki-lookup/preview`:

- Requires session-scope access.
- Accepts `page_ref`.
- Empty `page_ref` returns rendered empty `_session_wiki_lookup_preview.html`.
- Missing or inaccessible pages return `404` with rendered unavailable preview
  HTML.
- Visible pages return rendered `_session_wiki_lookup_preview.html`.

## Decision

Option 1 was selected and implemented for this slice: preserve the legacy
browser JSON routes in TypeScript.

The TypeScript handlers keep the Gen2-facing browser JSON shape:

- Search routes return `results` and `message`.
- Preview routes return `preview_html`.
- Empty preview identifiers return `{ "preview_html": "" }`.
- Missing campaigns return JSON `campaign_not_found`.
- Missing or inaccessible previews return `404` with unavailable preview HTML.
- Session wiki lookup remains Session-scope gated and uses player-visible wiki
  access for lookup results.

No frontend migration to `/api/v1` replacements is required for these four
cutover-blocking Gen2 calls.

## Validation

- `node apps/api/node_modules/typescript/lib/tsc.js -p apps/api/tsconfig.json`
  using the bundled Node runtime: passed.
- `node apps/api/tests/browser-json-compatibility.mjs` using the bundled Node
  runtime: passed.
- `node apps/api/tests/route-parity.mjs` using the bundled Node runtime: passed.

## Remaining Gate

The Browser JSON compatibility gate is closed for the four routes listed above.
This does not approve production TypeScript cutover by itself; the broader
cutover matrix still owns unrelated parity, data migration, rehearsal, and
rollback gates.
