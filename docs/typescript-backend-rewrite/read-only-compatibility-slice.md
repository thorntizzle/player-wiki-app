# Read-Only Compatibility Slice Evidence

Last updated: 2026-06-26

This document records the first implemented TypeScript read-only compatibility surface.

## Scope Completed

- Added a tracked TypeScript API app under `apps/api` using Hono.
- Added a tracked `better-sqlite3` runtime dependency for the first SQLite-backed read path.
- Implemented `GET /healthz`.
- Implemented `GET /api/v1/app` using fixture runtime metadata.
- Implemented `GET /api/v1/systems/import-runs` with Flask-compatible unauthenticated auth failure and fixture-admin SQLite reads.
- Implemented `GET /api/v1/systems/import-runs/:importRunId` with the same auth gate, fixture-admin SQLite detail reads, and explicit missing-resource JSON.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems` with Flask-compatible unauthenticated auth failure, fixture-role source cards, entry search, and rules-reference metadata search fields.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems/search` as the Flask-compatible search alias sharing the Systems landing payload contract.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems/sources` with Flask-compatible unauthenticated auth failure, fixture-role source filtering, campaign YAML source defaults, and SQLite library/source reads.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId` with Flask-compatible unauthenticated auth failure, fixture-role source access checks, entry grouping, book-entry summaries, rules-reference metadata fields, and explicit missing-source JSON.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems/sources/:sourceId/types/:entryType` with Flask-compatible unauthenticated auth failure, fixture-role source access checks, category entry grouping, title/type query filtering, entry summaries, and explicit missing-category JSON.
- Implemented `GET /api/v1/campaigns/:campaignSlug/systems/entries/:entrySlug` with Flask-compatible unauthenticated auth failure, fixture-role entry access checks, parsed entry metadata/body JSON, source state, campaign entry override serialization, Flask compatibility links, and explicit missing-entry JSON.
- Implemented `GET /api/v1/campaigns/:campaignSlug/combat` and `GET /api/v1/campaigns/:campaignSlug/combat/live-state` with Flask-compatible unauthenticated auth failure, fixture player/DM permission splits, empty read-only tracker state, live polling metadata, and unchanged-response short-circuit behavior.
- Implemented `GET /api/v1/campaigns/:campaignSlug/combat/systems-monsters/search` with Flask-compatible unauthenticated auth failure, fixture manager-only access, short-query guidance, and Systems monster metadata result formatting.
- Implemented `GET /api/v1/campaigns` using fixture-backed repository reads.
- Implemented `GET /api/v1/campaigns/:campaignSlug` using fixture-backed repository reads.
- Implemented `GET /api/v1/campaigns/:campaignSlug/help` using public fixture-read-only Campaign Help assumptions.
- Implemented fixture-backed wiki read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/wiki`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/sections/:sectionSlug`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/pages/*`
- Implemented fixture-backed session read endpoint with a no-header empty shell plus role-aware SQLite fixture reads for active session state, messages, and manager article/log arrays:
  - `GET /api/v1/campaigns/:campaignSlug/session`
- Implemented fixture-backed Session manager article-source lookup endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/session/article-sources/search`
- Implemented SQLite-backed Session article image read endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/session/articles/:articleId/image`
- Implemented SQLite-backed Session log detail read endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/session/logs/:sessionId`
- Added `apps/api/src/wiki/` as the read-only Markdown/frontmatter fixture reader and wiki payload serializer.
- Added fixture-backed content config endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/content/config`
- Added fixture-backed content page management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/pages`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages/*`
- Added fixture-backed content asset management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/assets`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets/*`
- Added fixture-backed content character management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/characters`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
- Default campaign fixture directory is `tests/fixtures/sample_campaigns`.
- `CPW_CAMPAIGNS_DIR` overrides the fixture directory.
- Implemented endpoints return JSON-only payloads for the read-only slice, with explicit fixture-mode auth/permissions metadata on campaign detail.
- Missing campaigns, wiki sections, and wiki pages return JSON `404` responses.
- Added `apps/api/src/routes.ts` as the implemented-route manifest for the tracked TypeScript slice.
- Added a route-parity smoke check that verifies implemented TypeScript routes stay present in both the Python route snapshot and the active TypeScript route seed.

## Compatibility Contract Verified

- Campaign response includes:
  - `ok`
  - `campaign` with `slug`, `title`, `summary`, `system`, `current_session`, and `systems_library_slug`
  - `auth_source` and explicit read-only auth block
  - read-only `permissions` block
- Campaign list response includes:
  - `ok`
  - `campaigns` entries sorted by campaign title with Flask-compatible campaign payload fields
  - explicit fixture read-only role/auth metadata
- App-state response includes Flask-compatible metadata fields:
  - `version`, `build_id`, `git_sha`, `git_dirty`, `runtime`, `instance_name`, `environment`, and `base_url`
  - fixture `db_path` and `campaigns_dir`
- Systems import-run list/detail responses add the first tracked SQLite read:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-admin requests read `systems_import_runs` from `CPW_DB_PATH`
  - `library_slug`, `source_id`, and `limit` filters preserve Flask's list-route behavior
  - missing detail rows return `systems_import_run_not_found` JSON
- Campaign Systems source-list response extends the same SQLite read foundation:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture `player` role sees enabled player-visible sources only
  - fixture `dm` and `admin` roles see/manage the full source list
  - `campaign.yaml` `systems_sources` seeds default enablement/visibility when no SQLite campaign source row exists
- Campaign Systems landing/search response preserves the browsing API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source cards include only enabled, accessible sources
  - `q` returns accessible entry summaries capped after access filtering
  - `reference_q` searches only global rules-reference entries and keeps source-scoped rules-reference sources separate
  - missing campaign landing/search requests return `campaign_not_found` JSON
- Campaign Systems source-detail response preserves the source page API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture `player` role can load player-visible enabled sources and receives `forbidden` for inaccessible sources
  - fixture `dm` and `admin` roles can load manager-visible enabled sources
  - response fields include `source`, `entry_groups`, `book_entries`, entry counts, hidden entry type metadata, rules-reference search metadata, reference query/results, book visibility note, and manage permissions
  - missing source detail rows return `systems_source_not_found` JSON
- Campaign Systems source-category response preserves the category API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source access checks match the source-detail route
  - response fields include `source`, `entry_groups`, `entry_type`, `entry_type_label`, `query`, entry counts, filtered entry summaries, and manage permissions
  - category `q` filtering matches Flask's title/type term search for this fixture slice
  - missing or empty categories return `systems_source_category_not_found` JSON
- Campaign Systems entry-detail response preserves the entry page API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source and entry visibility checks block inaccessible entries with `forbidden`
  - response fields include the full entry summary fields plus `metadata`, `body`, `rendered_html`, `source_state`, `override`, manage permissions, and Flask compatibility links
  - missing entries return `systems_entry_not_found` JSON
- Combat Systems monster search response preserves the manager search API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture player role receives `forbidden`
  - fixture DM/admin roles can search enabled campaign Systems monster rows
  - short queries return the Flask guidance message and empty results
  - result rows include `entry_key`, `title`, `source_id`, HP/speed subtitle, and signed initiative bonus
- Combat state/live-state responses preserve the read API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture player role receives a read-only empty tracker with manager-only links omitted
  - fixture DM/admin roles receive manager permission flags, DM fallback links, condition options, and empty setup choices
  - `live_revision`, 12-character `live_view_token`, and `poll_settings` fields are present
  - matching `X-Live-Revision` and `X-Live-View-Token` headers return an unchanged response without the tracker payload
  - missing campaign combat reads return `campaign_not_found` JSON
- Campaign Help response preserves the stable public Flask fixture fields for:
  - public viewer role and account note
  - available surface labels, cross-cutting limits, visibility rows, and surface guidance
  - Flask and Gen2 help/account/sign-in links
- Wiki home response preserves the stable Flask fixture fields for:
  - `frontend_mode`
  - `can_view_wiki`
  - `wiki_visibility_label`
  - `query`
  - `result_count`
  - `grouped_sections`
  - `section_navigation`
  - `latest_session_summary`
  - hidden deprecated `Overview` page behavior
- Wiki section response preserves stable Flask fixture section grouping fields, including top-level pages, subsection groups, and section navigation.
- Wiki page response preserves stable Flask fixture page fields, image metadata, `body_html`, backlinks, and section navigation.
- Session endpoint preserves fixture read-only inactive session fields:
  - `campaign` and read-only `permissions` (`can_manage_session: false`, `can_post_messages: false`)
  - `active_session: null`
  - `messages: []`
  - `session_message_recipient_player_choices: []`
  - `show_session_dm_passive_scores: false`
  - `session_revision` and deterministic 12-character `session_view_token`
  - unchanged-response short-circuit response using matching `X-Live-Revision` + `X-Live-View-Token` headers
- Session response omits DM-only arrays (`staged_articles`, `revealed_articles`, `session_logs`, `session_dm_passive_scores`) in read-only fixture mode.
- Session role-aware SQLite fixture reads cover:
  - fixture DM/admin roles reading `campaign_session_states.revision`, active session, global/DM-only messages, staged/revealed articles, article image metadata, and closed-session log summaries.
  - fixture player role reading active session and global messages while filtering DM-only messages and omitting manager arrays.
  - no-role requests keeping the inactive empty shell and unchanged short-circuit.
  - matching live headers short-circuiting role-aware responses too.
- Session article image reads stream the stored SQLite `data_blob` with the stored `media_type`; fixture DM/admin roles can read staged or revealed images, while fixture players receive only currently revealed active-session images and get a missing-image response for staged or inaccessible images.
- Session log detail reads cover closed-session records and all related messages for fixture DM/admin roles, including DM-only recipient metadata, while unauthenticated requests keep Flask-compatible `auth_required` and fixture player requests receive `forbidden`.
- Session article-source search preserves the manager lookup API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture player role receives `forbidden`
  - short queries return the Flask guidance message and empty results
  - fixture DM/admin roles receive visible published wiki page results and accessible Systems entry results
  - result rows include `source_ref`, `source_kind`, `title`, `subtitle`, `kind_label`, and `select_label`
  - missing campaign lookup requests return `campaign_not_found` JSON
- Content/config payload compatibility checks cover:
  - `config_file.campaign_slug`
  - stable `config_file.config` fields, including `title`, `current_session`, and `source_wiki_root`
  - `config_file.editable_fields` list
  - parseable `config_file.updated_at` string
- Content/page-management payload checks cover:
  - list endpoint `pages` shape with `29` fixture records, omitted `body_markdown`, and stable page/order sorting.
  - detail endpoint `page_file` shape with `body_markdown` included.
  - removal safety defaults (`can_hard_delete`, `hard_delete_blockers`, `removal_status_label`, `removal_guidance`, and nested `removal_safety` fields).
- Content/asset-management payload checks cover:
  - list endpoint `assets` shape with `2` fixture records and omitted `data_base64`.
  - detail endpoint `asset_file` shape with exact Flask-compatible `data_base64`.
  - stable asset fields (`asset_ref`, `relative_path`, `size_bytes`, `media_type`, and protected asset `url`).
- Content/character-management payload checks cover:
  - list endpoint `characters` shape with `3` fixture records and stable slug ordering.
  - summary fields (`character_slug`, `name`, `status`, and `import_status`).
  - detail endpoint `character_file` shape with Flask-compatible definition/import metadata normalization and `state_created: false`.

## Added Tests and Checks

- `tests/test_typescript_readonly_slice_contract.py`:
  - runs a focused Flask-vs-TypeScript contract check for stable `campaign` fields for `linden-pass` using sanitized fixture data.
  - compares Flask-vs-TypeScript app-state metadata fields under explicit test runtime overrides.
  - compares Flask-vs-TypeScript unauthenticated systems import-run list/detail and campaign Systems source-list auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems landing/search auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems source-detail auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems source-category auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems entry-detail auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated Combat Systems monster search auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated Combat state auth envelopes and asserts the fixture combat shell/unchanged-response shape.
  - compares Flask-vs-TypeScript campaign-list payload campaign fields while asserting explicit fixture read-only roles.
  - compares Flask-vs-TypeScript public Campaign Help payload fields under sanitized fixture data.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/config`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/pages` and one `.../content/pages/locations/port-meridian` detail endpoint, including removal fields and omission/inclusion of `body_markdown`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/assets` and one `.../content/assets/npcs/captain-lyra-vale.png` detail endpoint, including detail-only `data_base64`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/characters` and one `.../content/characters/arden-march` detail endpoint, including Flask-style definition/import metadata normalization.
  - compares stable Flask-vs-TypeScript wiki home, section, and page payload fields.
  - checks JSON missing-resource shapes for TypeScript wiki dynamic routes.
  - adds fixture session parity checks (active session state, messages, passive score flag, revision/token shape, short-circuit response, missing session campaign 404).
  - compares Flask-vs-TypeScript unauthenticated Session article-source search, Session article image, and Session log detail auth envelopes, and asserts the fixture lookup shell for short, wiki-result, player-forbidden, and missing-campaign cases.
- `apps/api/tests/smoke.mjs`:
  - starts compiled API on a local port and verifies `/healthz`, app state, SQLite-backed systems import-run list/detail reads, campaign Systems landing/search/source list/detail/category/entry reads, Combat state/live-state shell reads, Combat Systems monster search reads, Session article-source search reads, Session article image byte reads, Session log detail reads, campaign list/detail, public Campaign Help, wiki home, wiki section, wiki page, image metadata, and 404 behavior.
  - validates fixture-backed content config endpoint payload for `linden-pass` (`campaign_slug`, `current_session`, `title`, `systems_sources`, `editable_fields`, `updated_at`) and missing-campaign 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/pages` list sorting/count/body omission and sampled `Port Meridian` metadata/removal fields, plus `GET /api/v1/campaigns/:campaignSlug/content/pages/*` detail payload body inclusion and missing-content-page 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/assets` list sorting/count/data omission and sampled PNG metadata, plus `GET /api/v1/campaigns/:campaignSlug/content/assets/*` detail payload byte data and missing-content-asset 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/characters` list sorting/count and sampled character summary metadata, plus `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug` detail payload definition/import metadata and missing-content-character 404.
  - verifies `GET /api/v1/campaigns/:campaignSlug/session` no-header read-only payload shape, role-aware SQLite Session state reads, token/revision headers behavior, unchanged-response short-circuit, and session missing-campaign 404.
- `apps/api/tests/route-parity.mjs`:
  - checks implemented route coverage against `route-snapshots.json` and `typescript-route-seed.json`.

## Build/Test Commands

From repo root:

```powershell
npm --prefix apps/api install
npm --prefix apps/api run typecheck
npm --prefix apps/api test
& '<workspace>/.venv/Scripts/python.exe' -m pytest .\tests\test_typescript_readonly_slice_contract.py
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

## Outside This Slice

- Production auth, live SQLite, write paths, and deployment cutover are intentionally outside this fixture-only slice.

## Frontend Dev-Mode Pointer

To load campaign detail from the TypeScript API while keeping other surfaces on Flask:

1. Start the fixture API slice on `127.0.0.1:3000`:

```powershell
npm --prefix apps/api run build
npm --prefix apps/api run start
```

2. In a separate terminal for Vite, set `VITE_CPW_TYPESCRIPT_CAMPAIGN_API_BASE_URL` to the Vite-only proxy path and start the dev server:

```powershell
$env:VITE_CPW_TYPESCRIPT_CAMPAIGN_API_BASE_URL="/typescript-api"
npm --prefix frontend run dev
```

3. Leave the variable unset for normal Flask behavior (including production). The Vite proxy forwards `/typescript-api/*` to `http://127.0.0.1:3000/*`, so browser dev-mode reads stay same-origin with Vite while only campaign detail uses the TypeScript API.
