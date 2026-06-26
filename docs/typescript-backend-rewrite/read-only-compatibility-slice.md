# Read-Only Compatibility Slice Evidence

Last updated: 2026-06-26

This document records the first implemented TypeScript compatibility surface. It began as a read-only
fixture slice and now includes controlled SQLite write routes, validated only against a disposable
fixture database.

## Scope Completed

- Added a tracked TypeScript API app under `apps/api` using Hono.
- Added a tracked `better-sqlite3` runtime dependency for the first SQLite-backed read path.
- Implemented `GET /healthz`.
- Implemented `GET /api/v1/app` using fixture runtime metadata.
- Implemented `GET /api/v1/me` with Flask-compatible unauthenticated auth failure, synthetic fixture-role identity, membership, preference, and View As metadata, plus read-only SQLite API-token identity, active membership, normalized preference, and admin View As choice reads.
- Implemented `GET /api/v1/me/settings` with Flask-compatible unauthenticated auth failure, fixture-role user, preference, theme preset, and live-session chat-order metadata, plus read-only SQLite API-token user/preference reads.
- Implemented `PATCH /api/v1/me/settings` with Flask-compatible unauthenticated auth failure, bearer-token user preference writes, theme/chat-order validation, retired frontend-mode rejection, and refreshed preference payloads.
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
- Implemented Session state read endpoint with a no-header empty shell plus role-aware SQLite fixture or bearer-token reads for active session state, messages, and manager article/log arrays:
  - `GET /api/v1/campaigns/:campaignSlug/session`
- Implemented Session lifecycle write endpoints with bearer-token DM/admin access, SQLite session inserts/updates, and session revision bumps:
  - `POST /api/v1/campaigns/:campaignSlug/session/start`
  - `POST /api/v1/campaigns/:campaignSlug/session/close`
- Implemented Session message write endpoint with bearer-token campaign access, SQLite message inserts, and session revision bumps:
  - `POST /api/v1/campaigns/:campaignSlug/session/messages`
- Implemented Session article-store write endpoints with bearer-token DM/admin access, SQLite article/image/message mutations, and session revision bumps:
  - `POST /api/v1/campaigns/:campaignSlug/session/articles`
  - `PUT /api/v1/campaigns/:campaignSlug/session/articles/:articleId`
  - `POST /api/v1/campaigns/:campaignSlug/session/articles/:articleId/reveal`
  - `DELETE /api/v1/campaigns/:campaignSlug/session/articles/:articleId`
  - `DELETE /api/v1/campaigns/:campaignSlug/session/articles/revealed`
- Implemented Session manager article-source lookup endpoint with fixture or bearer-token manager access:
  - `GET /api/v1/campaigns/:campaignSlug/session/article-sources/search`
- Implemented SQLite-backed Session article image read endpoint with fixture or bearer-token visibility checks:
  - `GET /api/v1/campaigns/:campaignSlug/session/articles/:articleId/image`
- Implemented SQLite-backed Session log detail read endpoint with fixture or bearer-token manager access:
  - `GET /api/v1/campaigns/:campaignSlug/session/logs/:sessionId`
- Implemented SQLite-backed Session log delete endpoint with bearer-token DM/admin access:
  - `DELETE /api/v1/campaigns/:campaignSlug/session/logs/:sessionId`
- Added `apps/api/src/wiki/` as the read-only Markdown/frontmatter fixture reader and wiki payload serializer.
- Added Campaign Control read endpoint with fixture or bearer-token visibility-manager access:
  - `GET /api/v1/campaigns/:campaignSlug/control`
- Added Campaign Control visibility write endpoint with bearer-token visibility-manager access:
  - `PATCH /api/v1/campaigns/:campaignSlug/control/visibility`
- Added fixture-backed, content-management-gated content config endpoint:
  - `GET /api/v1/campaigns/:campaignSlug/content/config`
- Added fixture-backed content config write endpoint with bearer-token DM/admin access:
  - `PATCH /api/v1/campaigns/:campaignSlug/content/config`
- Added fixture-backed, content-management-gated content page management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/pages`
  - `GET /api/v1/campaigns/:campaignSlug/content/pages/*`
- Added fixture-backed content page write/delete endpoints with bearer-token DM/admin access:
  - `PUT /api/v1/campaigns/:campaignSlug/content/pages/*`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/pages/*`
- Added fixture-backed, content-management-gated content asset management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/assets`
  - `GET /api/v1/campaigns/:campaignSlug/content/assets/*`
- Added fixture-backed content asset write/delete endpoints with bearer-token DM/admin access:
  - `PUT /api/v1/campaigns/:campaignSlug/content/assets/*`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/assets/*`
- Added fixture-backed, content-management-gated content character management read endpoints:
  - `GET /api/v1/campaigns/:campaignSlug/content/characters`
  - `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
- Added fixture-backed content character write/delete endpoints with bearer-token DM/admin access:
  - `PUT /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
  - `DELETE /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug`
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
- Identity bootstrap response preserves the `/api/v1/me` shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture `player`, `dm`, and `admin` roles return synthetic active users with Flask-compatible user fields
  - fixture memberships cover available fixture campaigns, with `player` or `dm` campaign roles
  - preferences include `theme_key: parchment`, `session_chat_order: newest_first`, and `frontend_mode: gen2`
  - fixture admin reads expose View As availability and selectable player/DM fixture users, with no active target
  - bearer API tokens read active users, active memberships, normalized preferences, and admin View As choices from `CPW_DB_PATH`
  - the TypeScript read-only slice validates token hash/revocation/expiration but does not update API token `last_used_at`
- Account settings response preserves the `/api/v1/me/settings` read shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture role reads return the same user and preference fields as the identity shell
  - bearer API tokens read the same user and normalized preference fields from `CPW_DB_PATH`
  - `theme_presets` and `session_chat_order_choices` match Flask's static account-settings choices
  - retired `frontend_mode_choices` remains omitted
- Account settings writes preserve the `/api/v1/me/settings` mutation shell against the disposable SQLite fixture database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer API tokens update `user_preferences` rows for `theme_key` and/or `session_chat_order`
  - invalid themes, invalid chat order values, empty payloads, and retired `frontend_mode` writes return Flask-compatible `validation_error` messages
  - responses return `ok`, serialized `user`, and refreshed normalized `preferences`
  - subsequent `/api/v1/me` reads reflect the updated preference values
- Systems import-run list/detail responses add the first tracked SQLite read:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-admin requests read `systems_import_runs` from `CPW_DB_PATH`
  - bearer API tokens read import-run history when the token user is an app admin and return `forbidden` for non-admin token users
  - `library_slug`, `source_id`, and `limit` filters preserve Flask's list-route behavior
  - missing detail rows return `systems_import_run_not_found` JSON
- Campaign Systems source-list response extends the same SQLite read foundation:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture `player` role sees enabled player-visible sources only
  - fixture `dm` and `admin` roles see/manage the full source list
  - bearer API tokens derive player/DM/admin access from the active user and active campaign memberships before applying the same source filters
  - `campaign.yaml` `systems_sources` seeds default enablement/visibility when no SQLite campaign source row exists
- Campaign Systems landing/search response preserves the browsing API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source cards include only enabled, accessible sources
  - bearer API tokens use the same membership-derived visibility lane as the source-list route
  - `q` returns accessible entry summaries capped after access filtering
  - `reference_q` searches only global rules-reference entries and keeps source-scoped rules-reference sources separate
  - missing campaign landing/search requests return `campaign_not_found` JSON
- Campaign Systems source-detail response preserves the source page API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture `player` role can load player-visible enabled sources and receives `forbidden` for inaccessible sources
  - fixture `dm` and `admin` roles can load manager-visible enabled sources
  - bearer API tokens use the same membership-derived visibility lane as fixture roles
  - response fields include `source`, `entry_groups`, `book_entries`, entry counts, hidden entry type metadata, rules-reference search metadata, reference query/results, book visibility note, and manage permissions
  - missing source detail rows return `systems_source_not_found` JSON
- Campaign Systems source-category response preserves the category API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source access checks match the source-detail route
  - bearer API tokens use the same membership-derived visibility lane as fixture roles
  - response fields include `source`, `entry_groups`, `entry_type`, `entry_type_label`, `query`, entry counts, filtered entry summaries, and manage permissions
  - category `q` filtering matches Flask's title/type term search for this fixture slice
  - missing or empty categories return `systems_source_category_not_found` JSON
- Campaign Systems entry-detail response preserves the entry page API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture source and entry visibility checks block inaccessible entries with `forbidden`
  - bearer API tokens use the same membership-derived visibility lane as fixture roles
  - response fields include the full entry summary fields plus `metadata`, `body`, `rendered_html`, `source_state`, `override`, manage permissions, and Flask compatibility links
  - missing entries return `systems_entry_not_found` JSON
- Combat Systems monster search response preserves the manager search API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture player role receives `forbidden`
  - fixture DM/admin roles can search enabled campaign Systems monster rows
  - bearer API tokens use the same membership-derived manager lane as fixture roles
  - short queries return the Flask guidance message and empty results
  - result rows include `entry_key`, `title`, `source_id`, HP/speed subtitle, and signed initiative bonus
- Combat state/live-state responses preserve the read API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture or bearer-token player roles receive a read-only empty tracker with manager-only links omitted
  - fixture or bearer-token DM/admin roles receive manager permission flags, DM fallback links, condition options, and empty setup choices
  - invalid bearer requests return `auth_required`, and bearer users without active campaign access return `forbidden`
  - `live_revision`, 12-character `live_view_token`, and `poll_settings` fields are present
  - matching `X-Live-Revision` and `X-Live-View-Token` headers return an unchanged response without the tracker payload
  - missing campaign combat reads return `campaign_not_found` JSON
- Campaign Help response preserves the stable public Flask fixture fields for:
  - public viewer role and account note
  - available surface labels, cross-cutting limits, visibility rows, and surface guidance
  - Flask and Gen2 help/account/sign-in links
- Campaign Control response preserves the visibility-management API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture or bearer-token player roles receive `forbidden`
  - fixture or bearer-token DM/admin roles receive campaign metadata, visibility rows, rules, notes, and control links
  - fixture or bearer-token admin reads include the Private visibility choice while DM reads omit it
  - rows include selected, configured, default, effective, label, choice, and campaign-floor override fields
  - missing campaign control reads return `campaign_not_found` JSON
- Campaign Control visibility writes preserve the API mutation shell for a disposable fixture SQLite database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor for update and audit rows
  - bearer-token players receive `forbidden`
  - bearer-token DMs can update non-Private visibility choices when they can manage campaign visibility
  - `private` choices are rejected for non-admins with the Flask-compatible validation message
  - invalid `visibility` payloads return Flask-compatible `validation_error`
  - unchanged defaults/current values are skipped and return the no-change success message
  - changed scopes upsert `campaign_visibility_settings` rows with the actor user id
  - changed scopes write `auth_audit_log` rows with `campaign_visibility_updated` and `campaign_control_api` metadata
  - responses return a refreshed Campaign Control payload plus `changed_scopes` and `message`
  - missing campaign control writes return `campaign_not_found` JSON
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
- Session role-aware SQLite reads cover:
  - fixture or bearer-token DM/admin roles reading `campaign_session_states.revision`, active session, global/DM-only messages, staged/revealed articles, article image metadata, and closed-session log summaries.
  - bearer-token player role reading active session, global messages, messages targeted to that player, and messages authored by that player while filtering unrelated DM-only/player-private messages and omitting manager arrays.
  - fixture player role still using the synthetic fixture shell and reading global messages only because fixture headers do not identify a durable user id.
  - active player recipient choices for message targeting, using active campaign player memberships without exposing email addresses.
  - no-role requests keeping the inactive empty shell and unchanged short-circuit.
  - invalid bearer requests returning `auth_required`, and bearer users without active campaign access returning `forbidden`.
  - matching live headers short-circuiting role-aware responses too.
- Session message writes preserve the `/api/v1/campaigns/:campaignSlug/session/messages` mutation shell for a disposable fixture SQLite database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token users without active campaign access receive `forbidden`
  - malformed JSON returns Flask-compatible `invalid_json`
  - blank bodies, overlong bodies, invalid audience scopes, missing targeted players, and inactive/non-player targets return Flask-compatible `validation_error` messages
  - bearer-token campaign members can write `global`, `dm_only`, or targeted `player` chat messages while an active session exists
  - writes insert `campaign_session_messages`, bump `campaign_session_states.revision`, and set `updated_by_user_id` to the message actor
  - response messages include author metadata, recipient scope/user/label metadata, trimmed body text, and no article payload for normal chat messages
  - subsequent Session reads reflect Flask-compatible private-message visibility for the posting player, targeted player, and DM/admin readers
  - missing campaign message writes return `campaign_not_found` JSON
- Session lifecycle writes preserve the `/api/v1/campaigns/:campaignSlug/session/start` and
  `/api/v1/campaigns/:campaignSlug/session/close` mutation shells for a disposable fixture SQLite database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - duplicate start requests return Flask-compatible `A live session is already running for this campaign.`
  - close requests without an active session return Flask-compatible `There is no active session to close.`
  - start inserts an active `campaign_sessions` row with `started_by_user_id`
  - close updates the active `campaign_sessions` row to `closed` with `ended_at` and `ended_by_user_id`
  - both lifecycle writes bump `campaign_session_states.revision` and set `updated_by_user_id` to the actor
  - response sessions preserve Flask-compatible serialized session fields and subsequent Session reads expose the new active session or closed-session log summary
  - missing campaign lifecycle writes return `campaign_not_found` JSON
- Session article-store writes preserve the `/api/v1/campaigns/:campaignSlug/session/articles...`
  mutation shells for a disposable fixture SQLite database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - manual creates require a title plus body text or an embedded image
  - upload creates parse UTF-8 Markdown title/frontmatter/body and require a supplied `referenced_image` when the Markdown references one
  - wiki creates pull visible published wiki pages as Markdown snapshots and accessible Systems entries as rendered HTML snapshots
  - published wiki page pulls copy valid page image assets into the session article image store
  - staged updates can revise title/body and existing or replacement image metadata, while revealed articles are blocked from prep-queue edits
  - reveal requires an active session, marks the article revealed, creates a global `article_reveal` chat message, and returns both serialized records
  - delete removes the article and related article chat messages
  - clear-revealed removes all revealed articles and related article chat messages, bumping the revision only when rows are removed
  - article mutations bump `campaign_session_states.revision` and set `updated_by_user_id` to the actor when data changes
  - missing campaign article writes return `campaign_not_found`; missing article update/reveal/delete returns `validation_error`
- Session article image reads stream the stored SQLite `data_blob` with the stored `media_type`; fixture or bearer-token DM/admin roles can read staged or revealed images, while fixture or bearer-token players receive only currently revealed active-session images and get a missing-image response for staged or inaccessible images.
- Session log detail reads cover closed-session records and all related messages for fixture or bearer-token DM/admin roles, including DM-only recipient metadata, while unauthenticated requests keep Flask-compatible `auth_required` and fixture or bearer-token player requests receive `forbidden`.
- Session log deletes preserve the `/api/v1/campaigns/:campaignSlug/session/logs/:sessionId` mutation shell for a disposable fixture SQLite database:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - missing logs return Flask-compatible `That chat log could not be found.`
  - active sessions return Flask-compatible `Close the live session before deleting its chat log.`
  - closed-log deletion unlinks article `revealed_in_session_id` provenance for that session, deletes related chat messages, deletes the closed session row, and bumps `campaign_session_states.revision`
- Session article-source search preserves the manager lookup API shell:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture or bearer-token player roles receive `forbidden`
  - short queries return the Flask guidance message and empty results
  - fixture or bearer-token DM/admin roles receive visible published wiki page results and accessible Systems entry results
  - result rows include `source_ref`, `source_kind`, `title`, `subtitle`, `kind_label`, and `select_label`
  - missing campaign lookup requests return `campaign_not_found` JSON
- Content-management read routes preserve Flask's manager gate before returning fixture-backed payloads:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture or bearer-token player/outsider identities receive `forbidden` with the content-management message
  - fixture or bearer-token DM/admin identities can read content config, page, asset, and character management payloads
  - missing campaigns still return `campaign_not_found` before the auth gate
- Content/config payload compatibility checks cover:
  - `config_file.campaign_slug`
  - stable `config_file.config` fields, including `title`, `current_session`, and `source_wiki_root`
  - `config_file.editable_fields` list
  - parseable `config_file.updated_at` string
- Content/config writes preserve the `/api/v1/campaigns/:campaignSlug/content/config` mutation shell for a copied fixture campaign tree:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - request bodies may be empty, top-level update objects, or `{ "config": { ... } }`
  - unsupported fields, invalid `current_session`, and blank titles return Flask-compatible `validation_error` messages
  - `system` and `systems_library` aliases normalize to canonical known codes such as `DND-5E` and `Xianxia`
  - writes update `campaign.yaml`, and subsequent Hono campaign/config reads reflect the changed fixture file
- Content/page-management payload checks cover:
  - list endpoint `pages` shape with `29` fixture records, omitted `body_markdown`, and stable page/order sorting.
  - detail endpoint `page_file` shape with `body_markdown` included.
  - removal safety defaults (`can_hard_delete`, `hard_delete_blockers`, `removal_status_label`, `removal_guidance`, and nested `removal_safety` fields).
- Content/page writes preserve the `/api/v1/campaigns/:campaignSlug/content/pages/*` mutation shell for copied fixture campaign trees:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - `metadata` must be an object and `body_markdown` must be a string
  - writes render Markdown frontmatter, create parent directories safely, and return a detail payload with `body_markdown`
  - subsequent list/detail reads reflect the written page file
  - backlink removal-safety is recomputed for list/detail/upsert responses
  - deletes return the deleted page reference, remove the copied fixture file, and prune empty parent directories
  - backlink-blocked hard deletes return `409 hard_delete_blocked` unless forced with `force=true`
  - missing campaigns and missing pages return explicit JSON errors
- Content/asset-management payload checks cover:
  - list endpoint `assets` shape with `2` fixture records and omitted `data_base64`.
  - detail endpoint `asset_file` shape with exact Flask-compatible `data_base64`.
  - stable asset fields (`asset_ref`, `relative_path`, `size_bytes`, `media_type`, and protected asset `url`).
- Content/asset writes preserve the `/api/v1/campaigns/:campaignSlug/content/assets/*` mutation shell for copied fixture campaign trees:
  - unauthenticated requests return Flask-compatible `auth_required`
  - fixture-role write attempts are rejected because the mutation needs a durable bearer-token actor
  - bearer-token players and users without active manager access receive `forbidden`
  - `asset_file` must be an object with `filename` and valid `data_base64`
  - writes use the URL asset path, safely create parent directories, and return an asset summary without `data_base64`
  - subsequent list/detail reads reflect the written file bytes
  - deletes return the deleted asset reference, remove the copied fixture file, and prune empty parent directories
  - missing campaigns and missing assets return explicit JSON errors
- Content/character-management payload checks cover:
  - list endpoint `characters` shape with `3` fixture records and stable slug ordering.
  - summary fields (`character_slug`, `name`, `status`, and `import_status`).
  - detail endpoint `character_file` shape with Flask-compatible definition/import metadata normalization and `state_created: false`.
  - bearer-token write/delete auth, fixture-role write denial, player-forbidden behavior, validation errors, copied-fixture `definition.yaml`/`import.yaml` writes, reflected list/detail reads, deleted-character payload flags, file removal, and missing-character delete responses.
  - DND-5E content-character creation initializes a real SQLite `character_state` row with HP, resources, spell slots, Hit Dice, inventory, and notes from the copied fixture definition; raw delete removes the state row plus a seeded assignment row and reports `deleted_state` / `deleted_assignment` from row counts.
  - Xianxia content-character creation initializes SQLite mutable state, and Xianxia definition update reconciles existing current HP/temp HP, Stance/temp Stance, Jing, Yin/Yang, Dao, active Stance, and notes against lowered definition maxima without writing mutable state back into `definition.yaml`.
  - Flask-vs-TypeScript golden contract tests now compare DND-5E initialized state JSON and delete cleanup directly, and compare Xianxia mutable-state clamping/preservation plus definition-file separation directly.

## Added Tests and Checks

- `tests/test_typescript_readonly_slice_contract.py`:
  - runs a focused Flask-vs-TypeScript contract check for stable `campaign` fields for `linden-pass` using sanitized fixture data.
  - compares Flask-vs-TypeScript app-state metadata fields under explicit test runtime overrides.
  - compares Flask-vs-TypeScript unauthenticated `/api/v1/me` auth envelopes and asserts the fixture admin identity shell.
  - compares Flask-vs-TypeScript unauthenticated `/api/v1/me/settings` auth envelopes and static account-settings choices.
  - compares Flask-vs-TypeScript unauthenticated systems import-run list/detail and campaign Systems source-list auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems landing/search auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems source-detail auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems source-category auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated campaign Systems entry-detail auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated Combat Systems monster search auth envelopes.
  - compares Flask-vs-TypeScript unauthenticated Combat state auth envelopes and asserts the fixture combat shell/unchanged-response shape.
  - compares Flask-vs-TypeScript campaign-list payload campaign fields while asserting explicit fixture read-only roles.
  - compares Flask-vs-TypeScript public Campaign Help payload fields under sanitized fixture data.
  - compares Flask-vs-TypeScript Campaign Control auth envelopes and DM payload parity.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/config`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/pages` and one `.../content/pages/locations/port-meridian` detail endpoint, including removal fields and omission/inclusion of `body_markdown`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/assets` and one `.../content/assets/npcs/captain-lyra-vale.png` detail endpoint, including detail-only `data_base64`.
  - compares Flask-vs-TypeScript payload parity for `GET /api/v1/campaigns/linden-pass/content/characters` and one `.../content/characters/arden-march` detail endpoint, including Flask-style definition/import metadata normalization.
  - compares stable Flask-vs-TypeScript wiki home, section, and page payload fields.
  - checks JSON missing-resource shapes for TypeScript wiki dynamic routes.
  - adds fixture session parity checks (active session state, messages, passive score flag, revision/token shape, short-circuit response, missing session campaign 404).
  - compares Flask-vs-TypeScript unauthenticated Session article-source search, Session article image, Session log detail, and Session log delete auth envelopes, and asserts the fixture lookup shell for short, wiki-result, player-forbidden, and missing-campaign cases.
  - compares Flask-vs-TypeScript content-management unauthenticated and player-forbidden auth envelopes, plus the unauthenticated content/config, content page, and content asset mutation envelopes.
  - compares Flask-vs-TypeScript unauthenticated content character mutation envelopes for `PUT` and `DELETE .../content/characters/:characterSlug`.
  - compares Flask-vs-TypeScript DND-5E content-character create/delete golden behavior against copied campaign files and temp SQLite, including exact initialized state JSON, assignment cleanup, and delete flags.
  - compares Flask-vs-TypeScript Xianxia content-character create/update/delete golden behavior against copied campaign files and temp SQLite, including clamped current pools, preserved active Stance/notes/Dao, no mutable fields in `definition.yaml`, and delete flags.
- `apps/api/tests/smoke.mjs`:
  - starts compiled API on a local port and verifies `/healthz`, app state, fixture `/api/v1/me` identity reads, fixture `/api/v1/me/settings` account-settings reads, SQLite bearer-token `/api/v1/me` and `/api/v1/me/settings` reads/writes, SQLite-backed systems import-run list/detail reads with bearer admin/non-admin gates, campaign Systems landing/search/source list/detail/category/entry reads with fixture and bearer-token role gates, Combat state/live-state shell reads with fixture and bearer-token role gates, Combat Systems monster search reads with fixture and bearer-token role gates, Session state/article-source/image/log reads with fixture and bearer-token role gates, campaign list/detail, public Campaign Help, Campaign Control auth/payload reads and visibility writes, wiki home, wiki section, wiki page, image metadata, and 404 behavior.
  - validates content-management auth gates for anonymous, fixture player, bearer player, bearer outsider, and bearer app-admin content config reads.
  - validates fixture-backed content config endpoint payload for `linden-pass` (`campaign_slug`, `current_session`, `title`, `systems_sources`, `editable_fields`, `updated_at`), content/config PATCH auth and validation behavior, `campaign.yaml` writes against a copied fixture tree, reflected campaign-detail reads, empty-body no-op behavior, canonical system/library normalization, and missing-campaign 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/pages` list sorting/count/body omission and sampled `Port Meridian` metadata/removal fields, plus `GET /api/v1/campaigns/:campaignSlug/content/pages/*` detail payload body inclusion and missing-content-page 404.
  - validates `PUT` and `DELETE /api/v1/campaigns/:campaignSlug/content/pages/*` auth, fixture-write denial, player-forbidden behavior, metadata validation, missing-campaign behavior, copied-fixture Markdown writes, list/detail refresh, backlink hard-delete blockers, forced delete, deleted-reference payloads, file removal, and cleanup before later wiki count assertions.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/assets` list sorting/count/data omission and sampled PNG metadata, plus `GET /api/v1/campaigns/:campaignSlug/content/assets/*` detail payload byte data and missing-content-asset 404.
  - validates `PUT` and `DELETE /api/v1/campaigns/:campaignSlug/content/assets/*` auth, fixture-write denial, player-forbidden behavior, base64 validation, missing-campaign behavior, copied-fixture file writes, list/detail refresh, deleted-reference payloads, file removal, and missing-asset delete 404.
  - validates `GET /api/v1/campaigns/:campaignSlug/content/characters` list sorting/count and sampled character summary metadata, plus `GET /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug` detail payload definition/import metadata and missing-content-character 404.
  - validates content-character SQLite persistence for DND-5E create/delete and Xianxia create/update/delete, including actual `state_created`, `deleted_state`, and `deleted_assignment` response flags and Xianxia mutable-state clamping/preservation.
  - validates `PUT` and `DELETE /api/v1/campaigns/:campaignSlug/content/characters/:characterSlug` auth, fixture-write denial, player-forbidden behavior, definition validation, missing-campaign behavior, copied-fixture definition/import YAML writes, list/detail refresh, deleted-character payload flags, file removal, and missing-character delete 404.
  - verifies `GET /api/v1/campaigns/:campaignSlug/session` no-header read-only payload shape, role-aware fixture and bearer-token SQLite Session state reads, auth/forbidden bearer envelopes, token/revision headers behavior, unchanged-response short-circuit, and session missing-campaign 404.
  - verifies `POST /api/v1/campaigns/:campaignSlug/session/messages` auth, fixture-write denial, malformed JSON handling, validation messages, SQLite persistence, private-message visibility, recipient labels, revision bumps, and missing-campaign 404 against the disposable smoke-test database.
  - verifies `POST /api/v1/campaigns/:campaignSlug/session/start` and `.../session/close` auth, fixture-write denial, player-forbidden behavior, duplicate-start/empty-close validation, SQLite session persistence, revision bumps, refreshed Session reads/log summaries, and missing-campaign 404 against the disposable smoke-test database.
  - verifies Session article create/update/reveal/delete/clear auth, fixture-write denial, player-forbidden behavior, malformed JSON handling, validation messages, manual image-only staging, upload-mode referenced image handling, wiki-page image copying, Systems HTML snapshot staging, reveal chat-message creation, SQLite persistence, revision bumps, missing-article validation, and missing-campaign 404 against the disposable smoke-test database.
  - verifies Session log delete auth, fixture-write denial, player-forbidden behavior, active-log and missing-log validation, SQLite closed-session/message deletion, revealed-article provenance unlinking, revision bumps, and missing-campaign 404 against the disposable smoke-test database.
  - verifies `PATCH /api/v1/me/settings` auth, fixture-write denial, validation messages, retired frontend-mode rejection, SQLite persistence, and `/me` preference hydration after writes.
  - verifies `PATCH /api/v1/campaigns/:campaignSlug/control/visibility` auth, validation, Private restrictions, changed-scope response shape, SQLite persistence, audit rows, idempotent no-change response, and missing-campaign 404 against the disposable smoke-test database.
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

- Production auth, live SQLite cutover, production write readiness, backup/restore rehearsal, and deployment cutover are intentionally outside this fixture-only slice.

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
