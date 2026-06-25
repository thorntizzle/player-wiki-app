# Read-Only Compatibility Slice Evidence

Last updated: 2026-06-25

This document records the first implemented TypeScript read-only compatibility surface.

## Scope Completed

- Added a tracked TypeScript API app under `apps/api` using Hono.
- Implemented `GET /healthz`.
- Implemented `GET /api/v1/campaigns/:campaignSlug` using fixture-backed repository reads.
- Implemented fixture-backed wiki read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/wiki`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/sections/:sectionSlug`
  - `GET /api/v1/campaigns/:campaignSlug/wiki/pages/*`
- Implemented fixture-backed session read endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/session`
- Added `apps/api/src/wiki/` as the read-only Markdown/frontmatter fixture reader and wiki payload serializer.
- Added fixture-backed content config endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/content/config`
- Added fixture-backed content page management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/pages`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages/*`
- Added fixture-backed content asset management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/assets`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets/*`
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

## Added Tests and Checks

- `tests/test_typescript_readonly_slice_contract.py`:
  - runs a focused Flask-vs-TypeScript contract check for stable `campaign` fields for `linden-pass` using sanitized fixture data.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/config`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/pages` and one `.../content/pages/locations/port-meridian` detail endpoint, including removal fields and omission/inclusion of `body_markdown`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/assets` and one `.../content/assets/npcs/captain-lyra-vale.png` detail endpoint, including detail-only `data_base64`.
  - compares stable Flask-vs-TypeScript wiki home, section, and page payload fields.
  - checks JSON missing-resource shapes for TypeScript wiki dynamic routes.
  - adds fixture session parity checks (active session state, messages, passive score flag, revision/token shape, short-circuit response, missing session campaign 404).
- `apps/api/tests/smoke.mjs`:
  - starts compiled API on a local port and verifies `/healthz`, campaign detail, wiki home, wiki section, wiki page, image metadata, and 404 behavior.
  - validates fixture-backed content config endpoint payload for `linden-pass` (`campaign_slug`, `current_session`, `title`, `systems_sources`, `editable_fields`, `updated_at`) and missing-campaign 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/pages` list sorting/count/body omission and sampled `Port Meridian` metadata/removal fields, plus `GET /api/v1/campaigns/:campaignSlug/content/pages/*` detail payload body inclusion and missing-content-page 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/assets` list sorting/count/data omission and sampled PNG metadata, plus `GET /api/v1/campaigns/:campaignSlug/content/assets/*` detail payload byte data and missing-content-asset 404.
  - verifies `GET /api/v1/campaigns/:campaignSlug/session` read-only payload shape, token/revision headers behavior, unchanged-response short-circuit, and session missing-campaign 404.
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
