# API v1

`Campaign Player Wiki` now exposes a JSON API under `/api/v1` for the app's mutable content and live campaign operations.

The API also now manages the live file-backed content stored on the campaign volume:

- campaign config updates in `campaigns/<campaign-slug>/campaign.yaml`
- published wiki pages under `campaigns/<campaign-slug>/content/`
- published asset files under `campaigns/<campaign-slug>/assets/`
- character definition/import files under `campaigns/<campaign-slug>/characters/`

## Auth

API access uses bearer tokens tied to existing app users. Tokens inherit the same admin flag, campaign memberships, ownership rules, and visibility checks as the browser UI.

Browser-session app admins can also use `View As`. `GET /api/v1/me` continues to report the real authenticated admin user and includes a `view_as` block with availability, active target, and selectable active users. While active, campaign-facing safe reads under `/api/v1/campaigns...` use the selected user's effective role, memberships, and visibility; campaign API writes are blocked with `403 view_as_read_only` until the admin exits `View As`.

Issue a token:

```powershell
python manage.py issue-api-token dm@example.com live-sync --expires-in-days 365
```

List a user's tokens:

```powershell
python manage.py list-api-tokens dm@example.com
```

Revoke a token:

```powershell
python manage.py revoke-api-token 1
```

Pass the token in the `Authorization` header:

```powershell
$headers = @{
  Authorization = "Bearer <token>"
}
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/me" -Headers $headers
```

## Core Endpoints

This list is checked against Flask's registered `/api/v1` URL map after
normalizing route converters. The generated route/access manifest in
`docs/contracts/route-api-role-visibility-manifest.json` records the owning
domain and access contract for each method/path pair.

- `GET /api/v1/app`
- `GET /api/v1/systems/import-runs`
- `GET /api/v1/systems/import-runs/<import_run_id>`
- `POST /api/v1/systems/imports/dnd5e`
- `GET /api/v1/me`
- `POST /api/v1/me/view-as`
- `DELETE /api/v1/me/view-as`
- `GET /api/v1/me/settings`
- `PATCH /api/v1/me/settings`
- `GET /api/v1/admin`
- `GET /api/v1/admin/users/<user_id>`
- `POST /api/v1/admin/users/invite`
- `POST /api/v1/admin/users/<user_id>/membership`
- `DELETE /api/v1/admin/users/<user_id>/membership`
- `POST /api/v1/admin/users/<user_id>/assignment`
- `DELETE /api/v1/admin/users/<user_id>/assignment`
- `POST /api/v1/admin/users/<user_id>/invite`
- `POST /api/v1/admin/users/<user_id>/password-reset`
- `POST /api/v1/admin/users/<user_id>/disable`
- `POST /api/v1/admin/users/<user_id>/enable`
- `DELETE /api/v1/admin/users/<user_id>`
- `GET /api/v1/campaigns`
- `GET /api/v1/campaigns/<campaign_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/control`
- `PATCH /api/v1/campaigns/<campaign_slug>/control/visibility`
- `GET /api/v1/campaigns/<campaign_slug>/help`
- `GET /api/v1/campaigns/<campaign_slug>/wiki`
- `GET /api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/wiki/pages/<page_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/content/config`
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config`
- `GET /api/v1/campaigns/<campaign_slug>/content/assets`
- `GET /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/assets/<asset_ref>`
- `GET /api/v1/campaigns/<campaign_slug>/content/pages`
- `GET /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>`
- `GET /api/v1/campaigns/<campaign_slug>/content/characters`
- `GET /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `DELETE /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/session`
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search`
- `POST /api/v1/campaigns/<campaign_slug>/session/start`
- `POST /api/v1/campaigns/<campaign_slug>/session/close`
- `POST /api/v1/campaigns/<campaign_slug>/session/messages`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles`
- `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `POST /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/reveal`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed`
- `GET /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/session/logs/<session_id>`
- `GET /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>/image`
- `GET /api/v1/campaigns/<campaign_slug>/dm-content`
- `GET /api/v1/campaigns/<campaign_slug>/dm-content/systems`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/statblocks`
- `PUT /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<statblock_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/dm-content/statblocks/<statblock_id>`
- `POST /api/v1/campaigns/<campaign_slug>/dm-content/conditions`
- `PUT /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<condition_definition_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/dm-content/conditions/<condition_definition_id>`
- `GET /api/v1/campaigns/<campaign_slug>/systems`
- `GET /api/v1/campaigns/<campaign_slug>/systems/search`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/sources`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>`
- `GET /api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>`
- `GET /api/v1/campaigns/<campaign_slug>/systems/entries/<entry_slug>`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<entry_key>`
- `POST /api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries`
- `PUT /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive`
- `POST /api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore`
- `GET /api/v1/campaigns/<campaign_slug>/combat`
- `GET /api/v1/campaigns/<campaign_slug>/combat/live-state`
- `GET /api/v1/campaigns/<campaign_slug>/combat/systems-monsters/search`
- `POST /api/v1/campaigns/<campaign_slug>/combat/player-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/npc-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/statblock-combatants`
- `POST /api/v1/campaigns/<campaign_slug>/combat/systems-monsters`
- `POST /api/v1/campaigns/<campaign_slug>/combat/advance-turn`
- `POST /api/v1/campaigns/<campaign_slug>/combat/clear`
- `POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/set-current`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/turn`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/resources`
- `PATCH /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/npc-resources`
- `POST /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>/conditions`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/conditions/<condition_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/combat/combatants/<combatant_id>`
- `GET /api/v1/campaigns/<campaign_slug>/characters`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>`
- `GET /api/v1/campaigns/<campaign_slug>/characters/create`
- `POST /api/v1/campaigns/<campaign_slug>/characters/create`
- `GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `POST /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls`
- `PUT /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait`
- `GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<level>`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/flexible-casting`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-infusions`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/item-actions/<action_id>/use`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/personal`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-requests`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-records`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>`
- `DELETE /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key>`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/currency`
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/notes`
- `POST /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>`

## Transport Ownership

The Flexible Casting POST accepts `expected_revision`, `direction` (`create` or
`convert`), `level`, and, for conversion, the explicit `slot_lane_id` source.
It uses the existing authenticated character mutation response/error envelope.
Current PHB2014 source and Sorcery Point ownership must qualify in activated
committed-source mode. Creation costs 2/3/5/6/7 points for levels 1–5; conversion
gains the selected slot's level without exceeding the point cap. The exchange is
atomic with its state action audit. Slot pools preserve source-specific capacity
and usage beneath aggregate `spellcasting.slot_totals`; `slot_pools` and
`flexible_casting` provide qualified source choices and action availability.
Temporary-slot spending through the existing spell-slot PATCH accepts positive
`delta_used`; an absolute `used` edit cannot restore granted slots. Long rest
expires their capacity. Ordinary class-slot usage contracts remain unchanged.

The final Phase 3B ownership inventory in this section is integrated on pushed `main` and deployed as Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. The documentation closeout that records this release is a later docs-only descendant and is not part of that deployed image. `player_wiki/session_api_routes.py` owns all 13 live-session JSON handlers and explicit registrations on the existing API Blueprint. Character API registrar modules own their extracted Character transports, Auth API registrar modules own the extracted `/me` transports, and `admin_api_routes.py` owns 12 Admin API rules on that same Blueprint. `player_wiki/api.py` retains the Blueprint, 35 direct route decorators, shared request/auth/error helpers, serializers, service composition, and registrar dependency wiring. Character `/session/character` and character-session endpoints remain Characters-owned. The low-level `/content/...` APIs remain Publishing-owned; neither family is counted among the 13 live-session API rules.

Across the whole application, the qualified manifest has 299 Flask rules and 308 method/path contracts: 171 browser, 136 API, and one framework-owned static entry. Domain rule/contract ownership is app shell 13/13, Auth 13/15, Admin 30/30, Publishing 20/20, DM Content 25/25, Systems 33/33, Live Session 32/32, Combat 46/46, Characters 86/93, and framework 1/1. Every rule and method/path contract has one owner; transport extraction does not change the documented payload, authorization, visibility, persistence, or error contracts.

## Session Polling

`GET /api/v1/campaigns/<campaign_slug>/session` now participates in session polling:

- Include `X-Live-Revision` and `X-Live-View-Token` request headers for each poll.
- The response always includes `session_revision` and `session_view_token`.
- If both headers match current server values, the endpoint returns:
  - `{"ok": true, "changed": false, "session_revision": <int>, "session_view_token": "<token>"}`.
- If either header differs, the endpoint returns the full `/session` payload with updated revision/token metadata.

## Browser Content Management Coverage

The browser `DM Content` hub now covers the main DM-managed content lanes while still reusing the same app services and JSON API where those are the right write contract:

- `GET /api/v1/campaigns/<campaign_slug>/dm-content` returns `subpage_counts` for the Flask DM Content subpage badges with stable keys `statblocks`, `conditions`, `player_wiki`, `staged_articles`, and `systems`. Management-only lanes return permission-safe counts for the current viewer; inaccessible management lanes report `0`.
- `DM Content -> Player Wiki` creates, edits, and unpublishes wiki pages through the forward-reconciliation coordinator, uploads new page images into unique immutable campaign asset refs under `wiki-managed/v1/`, can prefill a new page from a staged or revealed session article in the Flask editor, and only hard-deletes after usage checks pass. Checked-delete retains its existing authorization, CSRF, confirmation, refusal, redirect, and status behavior while successful deletion uses the private deletion journal and writes one browser audit. Flask browser uploads convert PNG/JPG page images and session-article image copies into WebP quality 82 app-owned assets for page frontmatter; direct Session one-shot conversion copies use the same managed namespace. JSON clients can use the generic content asset API for legacy/nonmanaged refs when they need direct upload control.
- `DM Content -> Systems` manages campaign source enablement and entry overrides through the same Systems policy service as `PUT /api/v1/campaigns/<campaign_slug>/systems/sources` and `PUT /api/v1/campaigns/<campaign_slug>/systems/overrides/<entry_key>`. The Systems management payload is available from `GET /api/v1/campaigns/<campaign_slug>/dm-content/systems`; it creates/updates/archives/restores custom campaign Systems entries through the `/systems/custom-entries` JSON endpoints, imports or refreshes campaign item mechanics through `/systems/item-mechanics/import`, reviews sanitized import-run history, and keeps admin-only DND-5E ZIP uploads permission-gated on the Flask import form.
- `DM Content -> Staged Articles` writes into the existing session article store for manual, upload, and wiki-backed prep articles. The JSON API can create, revise unrevealed staged article title/body/image metadata or replacement image, reveal, delete, and bulk-clear revealed session articles. Browser Player Wiki promotion/conversion still owns the richer publication safety review.
- `DM Content -> Statblocks` and `DM Content -> Conditions` have both browser and JSON API create/update/delete coverage through the `/dm-content/statblocks` and `/dm-content/conditions` endpoints.

Use the browser Player Wiki lane when you want the built-in removal guidance, archive/unpublish affordance, session-article promotion flow, and usage blockers for backlinks, character hooks or sheet references, and session provenance. The content page API includes the same removal-safety contract on page list/detail/upsert responses: `can_hard_delete`, `hard_delete_blockers`, `removal_status_label`, `removal_guidance`, and nested `removal_safety`. `DELETE /api/v1/campaigns/<campaign_slug>/content/pages/<page_ref>` blocks unsafe hard deletes with `409 hard_delete_blocked` unless the request explicitly provides `?force=true` or JSON body `{"force": true}`. A blocked response keeps the existing error envelope and nested `details.removal_safety`; malformed JSON returns `400 validation_error`, and a missing page returns 404. Success returns HTTP 200 with `{"ok": true, "deleted": {"page_ref": "<page_ref>", "relative_path": "<page_ref>.md"}}`, uses the private deletion journal, retains all campaign assets, and writes no browser audit. Prefer unpublish/archive through a metadata update unless a hard delete is intentionally forced after review. The reference-blocker graph is unchanged; forcing bypasses that review but does not add an image or Markdown cleanup policy.

## Request Notes

### Source-owned noncasting item use

`PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>`
accepts `{"operation":"item_attack_d20","expected_revision":123,"confirm_attack":true}`
for an exact currently qualified physical item with an approved `item_capabilities`
v3 attack-d20-substitution declaration. Use the actual current revision. These
are the only JSON fields; duplicate fields and client replacement values,
targets, attack totals/outcomes or spell-slot fields are rejected. HTML uses the
existing authenticated inventory POST with CSRF and `confirm_attack=yes`.

The source supplies replacement 10, cost one, equipped-only activation and its
fixed counter/recovery rule. The item must have unique quantity-one ownership,
current activation custody, and a known effective count of at least one with
maximum equal to the source maximum. Attunement is not required. Unknown,
exhausted, unequipped, ambiguous or incompatible ownership/counts refuse without
changing state. The existing permissions and conflict/error envelopes apply.

Success records the choice of 10 instead of the attack d20 and decrements only
that physical item's current uses. The state update and
`character_item_action_applied` audit commit atomically under the existing
source reservation/CAS. The ordinary response returns refreshed character and
inventory data; `presented_inventory[].item_noncasting_action` supplies the
current rule, replacement, cost, source/campaign recovery and availability reason.
This does not resolve an attack, hit, target, damage, save or check. Modifiers and
final outcomes remain table managed. A stale revision refuses and is not an
instruction to replay an uncertain use.

Manager admission of a real unrecorded counter and existing count observations
remain separate `item_uses` operations. Recovery uses the existing explicit rest
path; an `at_dawn` source retains that fact alongside its approved long-rest
mapping. Nothing initializes, refills or equips the item on read or use. Shared
Sheet/editable Session controls use this operation; current read-only
Session/Combat inventory surfaces remain read-only. Existing v1/v2 item spell
operations are unchanged.

### Source-owned item spell operations

The existing `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>` accepts the following additional DND-5E `operation` values when that exact physical item has a currently approved `item_capabilities` v2 declaration. All require the normal character edit permission and integer `expected_revision`; the existing browser inventory POST uses the same service with CSRF protection. These operations require activated source-owned state and do not infer capabilities from item names or prose.

| Operation | Fields and effect |
| --- | --- |
| `item_cast` | `mode_id`, plus `slot_lane_id` and `slot_level` for a paid mode. A source-declared reaction trigger requires boolean `confirm_trigger: true`. Spends the selected qualified slot or one known item use atomically; paid and free budgets stay separate. |
| `storage_initialize` | Manager-only boolean `confirm_observation: true` records an explicitly observed empty baseline when no ledger exists. It cannot clear or reset an existing ledger. |
| `storage_store` | `choice_id` from the current inventory projection, `slot_lane_id`, `slot_level`. Atomically spends a compatible qualified slot and adds the selected castable class spell with frozen original-caster values. |
| `storage_external` | Manager-only `confirm_observation: true`, exact `spell_entry_key`, `slot_level`, actual `caster`, `ability` (`str`, `dex`, `con`, `int`, `wis`, `cha`), integer `ability_modifier`, `save_dc`, `attack_bonus`. Records an actual externally funded casting; its costs must be recorded separately. Omitted original metrics are never filled from the wearer. |
| `storage_release` | `stored_id` selects one current authenticated stored entry. Requires the declared worn/attuned activation, removes that entry and spends no wearer slot. |

For a slot selection, clients may instead send the existing `slot_selection` string `<pool-id>|<level>`; sending it together with separate slot fields refuses ambiguity. HTML confirmations use `yes`; JSON confirmations require boolean `true`. Source, custody, capacity, qualified slot availability and state revision are rechecked under the existing source-write transaction. Unsupported or unrecorded availability is not initialized by a cast or a read. Recording a cast spends its modeled cost; targeting, components, checks and effects remain table managed.

`presented_inventory` exposes `item_casting_modes` with explicit availability/reasons and current slot options, and `spell_storage` with known/unrecorded status, level capacity/occupancy, authenticated stored entries and available choices. Unknown storage is not an empty list of castable spells. Stored values retain their original source/caster snapshot; later wearer bonuses do not update them. The optional state `item_spell_storage` is preserved by other write families and authenticated by the latest actor-bound item audit checkpoint. Ordinary Character and legacy editable Session controls use this shared model; existing read-only Session/Combat inventory surfaces show the same facts without adding write controls. Source support alone does not admit an item declaration, establish a character baseline or prove an exercised operation.

- `GET /api/v1/app` exposes the current app version, build id, runtime, and active DB/campaign paths.
- The shared systems ingest endpoints are app-admin only. Campaign DMs can manage campaign systems policy, but only app admins can import new shared library source data.
- `POST /api/v1/systems/imports/dnd5e` accepts `source_ids`, optional `entry_types`, and an embedded `archive` object with `filename` and `data_base64`. The archive must be a `.zip` containing a compatible DND 5E source `data/` directory.
- `POST /api/v1/systems/imports/dnd5e` also accepts optional `import_version` and `source_path_label` overrides if you want import-run history to show a custom source label instead of the uploaded archive name. Its supported bare endpoint remains `api.systems_import_dnd5e`, with one POST rule, implicit `OPTIONS`, and no `HEAD`. `systems_api_routes.py` owns the controller and explicit registration; `api.py` retains the Blueprint, shared request/error helpers and serializers, and importer/store/service composition supplied to that transport.
- After the complete DND-5E API import succeeds, the controller synchronously writes one app-global `systems_dnd5e_source_imported` auth event before import-run refetch or response serialization. The event uses the real app-admin actor with `campaign_slug` unset and records canonical `library_slug: "DND-5E"`, result-derived ordered `source_ids` and `import_run_ids` (including truthful repeats), effective first-seen `entry_types` or `["all"]`, the trimmed `archive_filename`, and `source: "api"`. Validation, archive/import, or later-source failure writes no success event. Audit failure propagates after completed import runs and shared-entry replacements are already durable; later refetch or serialization failure occurs after the audit is durable. The browser import contract is unchanged.
- `GET /api/v1/systems/import-runs` and `GET /api/v1/systems/import-runs/<import_run_id>` are app-admin-only, read-only transports for recorded shared-library ingest history. They retain the supported bare `api.systems_import_run_list` and `api.systems_import_run_detail` endpoint identifiers, with one GET rule apiece and implicit `HEAD` and `OPTIONS`. Their existing serializer exposes the stored raw `source_path`, full import summary, timestamps, and `started_by_user_id`.
- Custom campaign Systems entry create/update/archive/restore is exposed through DM/admin JSON endpoints under `/api/v1/campaigns/<campaign_slug>/systems/custom-entries`. Successful mutations return HTTP 200 without redirecting and include `ok`, the serialized `entry`, and a refreshed `systems` management payload. Create and update require a JSON object and retain `400 invalid_json` for malformed, non-object, Markdown-limit, or service-validation failures; archive and restore ignore request-body content and retain `400 validation_error` for an invalid entry. Update keeps the existing slug and entry key. Each service mutation commits before its auth audit, and the audit runs before entry serialization and refreshed-payload construction, so a later audit, serializer, or payload failure can follow durable SQLite changes; archive and restore retain their refetch-or-original response fallback. Imported shared-library Systems entries remain read-only at the content level; use campaign source policy or entry overrides for campaign-specific changes unless a shared-library edit model is deliberately added later.
- Campaign item mechanics import is exposed through `POST /api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import`. The supported bare endpoint remains `api.systems_item_mechanics_import`, with one POST rule, implicit `OPTIONS`, and no `HEAD`. The payload requires `page_ref` and accepts optional `visibility`, `item_mechanics_review_status` (or the existing `mechanics_review_status` alias), and object-valued manual `item_mechanics` overrides. It remains DM/admin-only through the existing Systems-management boundary: non-admin managers require effective Systems-scope access, while direct app admins retain their established bypass. The route keeps the existing View As, session-CSRF, bearer-token, and JSON error boundaries and accepts only published item pages through `SystemsService`. The service/store path creates or refreshes a campaign-owned custom Systems `item` entry linked to that page, stores interpreter review output and unsupported flags, and returns both the saved `entry` and a refreshed `systems` management payload. The durable service write still precedes the auth audit, entry serialization, and full-payload build, so later failures retain the existing partial-durability behavior.
- `GET /api/v1/me` now includes the same app metadata block alongside the authenticated user payload, memberships, user preferences such as `theme_key`, `session_chat_order`, and the compatibility `frontend_mode` field, plus the admin-only `view_as` state. Flask is the only browser frontend; `frontend_mode` reads normalize to `flask`.
- `POST /api/v1/me/view-as` and `DELETE /api/v1/me/view-as` are browser-session admin-only endpoints for setting or clearing the active `View As` target. Non-admin users receive `403`; blank or self targets clear the mode; inactive or missing users are rejected. The active target affects only campaign-facing safe reads, while `/api/v1/me` and account/admin routes keep the real authenticated admin identity.
- `GET /api/v1/me/settings` returns the authenticated user's account-settings payload, including theme presets with preview colors, live-session chat-order choices, and current preferences. `PATCH /api/v1/me/settings` accepts `theme_key` and/or `session_chat_order`, validates them with the same account helpers as Flask, persists the preferences, and returns the refreshed preference values used by `/api/v1/me` theme hydration. `frontend_mode` writes are rejected because the preferred-frontend account setting is retired.
- `GET /api/v1/admin` and `GET /api/v1/admin/users/<user_id>` are app-admin-only Admin reads. They expose dashboard and user-detail context, user cards, campaign and character choices, audit filter choices, paginated audit rows, and Flask CSV export URLs.
- Admin mutations under `/api/v1/admin/users...` reuse the same auth-store operations and audit events as Flask for invites, membership save/remove, character assignment/clear, invite links, password reset links, disable/enable, and checked user deletion. Browser account deletion shows the target display name, email, and account ID and requires the unprefilled, case-sensitive text `DELETE USER <decimal account ID>`; missing or wrong text returns the same detail with an error before deletion or audit. `DELETE /api/v1/admin/users/<user_id>` accepts a string `confirm_account` with that exact phrase. For API compatibility, `confirm_email` or `confirm_user_email` also confirms when its trimmed, case-insensitive value matches the current stored email and both values are nonblank. Either valid form confirms; missing or wrong confirmation returns `400 validation_error` before deletion or audit. The API atomically rechecks the current account ID and email after acquiring the deletion write lock; an email change invalidates email-based confirmation with `409 account_conflict` and no deletion or audit. Confirmation prevents accidental deletion and does not replace app-admin authorization. Browser self-deletion denial, CSRF protection, missing-target `404`, successful audit, and redirects remain in place. Anonymous API users receive `401`, non-admin users receive `403`, and one-shot invite/reset URLs are returned only in mutation responses rather than audit rows.
- `GET /api/v1/campaigns/<campaign_slug>` includes visibility-aware campaign permissions such as `can_manage_visibility`.
- `GET /api/v1/campaigns/<campaign_slug>/control` and `PATCH /api/v1/campaigns/<campaign_slug>/control/visibility` expose the Campaign Control visibility editor. They require campaign visibility management permission, return the same selected/configured/default/effective visibility rows as the Flask Control panel, reject invalid visibility values, reserve `private` for app admins, clear visibility caches after writes, and write `campaign_visibility_updated` audit events for changed scopes.
- `GET /api/v1/campaigns/<campaign_slug>/help` returns the campaign-scoped Help context used by API clients, including visible help surfaces, viewer-role summary, effective visibility rows, cross-cutting limits, and Flask link fields. It follows campaign-scope access and reuses the same Help context builder as the Flask Help page.
- The `/wiki` endpoints are player-facing published-wiki reads for API clients. `GET .../wiki` follows campaign-scope access and returns a restricted-wiki message when the campaign is visible but the wiki scope is not; section and page detail reads require wiki-scope access. These endpoints return only visible published pages, rendered body HTML through the same repository renderer as Flask, Flask hrefs by default, and page image URLs only when the referenced protected campaign asset exists. Stale `/app-next` links in rendered wiki body HTML are rewritten to `/campaigns/...`. A page request using a legacy slug declared in visible page frontmatter `redirect_from` receives a permanent `308` redirect to the canonical page-detail API URL; a currently visible page at the legacy slug takes precedence during staged migrations.
- `PATCH /api/v1/campaigns/<campaign_slug>/content/config` supports the editable campaign fields `title`, `summary`, `system`, `current_session`, `source_wiki_root`, `systems_library`, and boolean `allow_artificer_infusion_deactivation`. The last field enables a campaign ruling and defaults to disabled when absent. Supported `system` and `systems_library` aliases are canonicalized through the app system-policy layer, including `DND-5E` and `Xianxia`.
- Asset detail reads return `data_base64`, and asset writes use an embedded `asset_file` object with `filename` and `data_base64`. `PUT .../content/assets/<asset_ref>` accepts at most 8 MiB of valid PNG, JPEG, GIF, or WebP bytes matching the asset reference suffix (case-insensitively; `.jpg` and `.jpeg` both mean JPEG). Validation also limits each frame to 16 million pixels, cumulative decoded pixels to 64 million, and frame count to 256. GIF files may contain at most 65,536 encoded extension bytes total, counting each extension introducer, label, sub-block length, payload, and zero terminator; header, palette, image descriptor, LZW image data, and trailer bytes do not count. The embedded filename and optional media type do not determine the accepted format. The generic API preserves accepted bytes and animations without conversion; unsupported, malformed, mismatched, or over-budget input returns the existing HTTP 400 `validation_error` envelope before a file is written. Successful writes keep the HTTP 200 asset response. Protected browser asset GET/HEAD reads display only valid matching raster files within those limits inline; unsupported, unknown, invalid, or over-budget legacy files remain available as `application/octet-stream` attachments with `nosniff` and a restrictive document CSP. The character portrait asset route applies the same serving rule under Characters-scope access.
- Generic content asset API PUT and DELETE reject the reserved `wiki-managed/` namespace and aliases resolving into it with the existing `400 validation_error` envelope; authorized content managers retain asset list/detail reads. New browser Wiki images and direct Session one-shot copies use unique immutable managed refs under `wiki-managed/v1/`. A content manager can GET/HEAD a canonical managed ref for draft preview even without Wiki-scope access. Other viewers need Wiki-scope access and an exact currently visible page referencing the ref with no active reconciliation journal owning it; denied reads return 404. Authorized and denied managed responses, including Range and conditional responses, use `private, no-store`. Existing legacy asset refs keep their prior access behavior.
- The `/content/...` management endpoints are DM/admin only. They expose unpublished pages and raw character file content, so they intentionally do not follow normal player-facing visibility rules.
- Page management endpoints read and write raw frontmatter plus `body_markdown`. Page upsert and hard delete use their durable reconciliation journals, finalize the SQLite read model, and refresh the running repository from that database state so the current app process sees the change immediately. A `PUT /content/pages/<page_ref>` that creates a page without `metadata.published` writes explicit `published: false`; an update that omits it preserves the existing page's publication state. If that page changes between the omitted-field read and the guarded write, the API returns `409 page_conflict` and asks the client to reload. Explicit `published: true` or `false` remains supported. Set `published: false` for an API-driven archive/unpublish workflow instead of hard-deleting a referenced page.
- Campaign config writes also refresh the running repository so title, summary, current session, and systems-library changes take effect immediately.
- Character management endpoints read and write `definition.yaml` and `import.yaml`. For `PUT /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`, an all-absent target retains the existing `content_api_create` behavior; a complete existing target uses durable `content_api_update` reconciliation. Partial targets and targets that remain active or conflicted after recovery fail closed. Unchanged DND or Xianxia mutable state is not rewritten; changed Xianxia state reconciliation advances its revision by exactly one.
- The raw character content PUT remains DM/admin-only, continues to accept the existing `definition` and optional `import_metadata` payload fields, returns validation failures through the existing HTTP 400 `validation_error` envelope, and returns HTTP 200 with the existing `{"ok": true, "character_file": ...}` shape on success. Restart and verified-backup recovery complete eligible `prepared` or `repository_pending` work forward. The journal does not make SQLite and filesystem publication one atomic transaction. See [Characters Overview](current-state/characters-overview.md) for the storage and recovery boundaries.
- `DELETE /api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>`
  remains DM/admin-only, ignores its request body, writes no browser audit, and
  preserves its existing 404, HTTP 400 `validation_error`, and HTTP 200
  response contracts. The successful `deleted` object retains
  `character_slug`, `deleted_files`, `deleted_state`, `deleted_assignment`, and
  `deleted_assets`; the booleans reflect the exact resources captured at the
  durable deletion commit point.
- Raw character deletion supports a partial managed target when at least one
  definition, import, state, assignment, or exact managed portrait resource is
  present, including portrait-only targets. Multiple exact managed portrait
  candidates, a definition/discovery mismatch, or unsafe or ambiguous file
  authority returns the established validation failure with no commit. After
  commit, restart and verified-backup recovery complete the exact captured
  resources forward; unrelated files and Combat snapshot or string references
  are preserved.
- Character content management endpoints accept both DND-5E and Xianxia file-backed definitions. For Xianxia, submit `system: "Xianxia"` with a top-level stable `xianxia` definition block; the content service normalizes supported aliases into the canonical Realm, action-count, Honor, Attribute, Effort, Energy, Yin/Yang, durability, Martial Art, Generic Technique, approval, and advancement-history fields.
- Xianxia mutable play state remains SQLite-backed. Current HP/Stance, Energy, Yin/Yang, Dao, active Stance/Aura, inventory quantities, and notes should not be written into `definition.yaml`; when the character content API updates an existing Xianxia definition, it reconciles the existing mutable state against the new definition maxima instead of replacing live session values.
- Xianxia native creation, Xianxia manual import, Xianxia Cultivation, DND-5E native creation, DND-5E Advanced Editor, and DND-5E level-up have JSON contracts used by Flask browser flows and API clients. Session-state JSON coverage also includes active Stance/Aura, modeled inventory add/edit/remove/equip, and Dao Immolating use request/record actions because browser session surfaces consume those same durable write paths.
- Character content management endpoints are low-level file operations. Native in-browser character create/import, edit, level-up, progression repair, assignment, and deletion workflows continue to use the character-specific routes and support matrix rather than the raw content API.
- Deleting a managed character removes the exact captured file-backed
  definition/import metadata and one exact managed portrait when present, the
  live `character_state` row, and any character assignment for that slug. It
  does not recursively clean other assets or introduce archive, reassignment,
  cascade, reference-refusal, force, or CLI-delete behavior.
- Session message creation accepts optional `recipient_scope` values of `global`, `dm_only`, or `player`; `player` messages also require `recipient_user_id` for an active campaign player. Session reads server-filter messages for ordinary players, while DM/admin reads and closed session-log reads include all messages with `recipient_scope`, `recipient_user_id`, and `recipient_label` metadata. Revealed session articles remain global-only.
- DM/admin Session reads include `show_session_dm_passive_scores`; for DND-5E campaigns they also include `session_dm_passive_scores` rows with character name, Passive Perception, Passive Insight, and Passive Investigation values for the DM Session workspace.
- Session article creation accepts JSON `mode: "manual"`, `mode: "upload"`, or `mode: "wiki"`.
- Manual session article creation requires a title plus either `body_markdown` or an embedded `image`; image-only staged articles are valid when the image payload passes normal session-article image validation.
- Upload mode accepts `filename`, `markdown_text`, and optional `referenced_image`. Markdown uploads whose body is only a referenced image are valid when `referenced_image` is supplied.
- `GET /api/v1/campaigns/<campaign_slug>/session/article-sources/search?q=...` lazily searches visible published wiki pages plus accessible Systems entries for DM/admin session management.
- Wiki mode accepts `source_ref`. For published wiki pages, `source_ref` is the page ref such as `npcs/captain-lyra-vale`. For Systems entries, use `systems:<entry-slug>`. Legacy `page_ref` still works for published wiki pages.
- Pulling a published wiki page creates a staged markdown snapshot from the selected visible page. In activated committed-source mode, only an exact selected-revision managed image BLOB is copied. A nonmanaged legacy page image is omitted without reading its file; if committed body and summary are both empty, the pull returns `400 validation_error` before a Session write, with conversion or separate manual-upload guidance. When text is staged without that legacy image, the success response includes `image_omitted: true` and a payload-free `notice`; other success responses retain their existing shape. Closed never-activated mode retains file-backed image copying, and managed image proof failures refuse the pull.
- Pulling a Systems entry creates a staged HTML snapshot from the current rendered Systems article. Session article payloads now include `source_page_ref`, `source_kind`, `source_ref`, and `body_format` so API clients can tell whether the staged body is markdown or rendered HTML.
- Session article payloads also include `source`, `converted_page`, and `links` metadata for API clients. `links.source_url` points back to the pulled wiki page or Systems entry when it is still accessible; session-only manual/upload articles expose `links.player_wiki_editor_url` and `links.convert_url` for the established browser publication workflows; already converted articles expose `links.published_page_url` when the published page is currently visible.
- Staged session articles can be revised with `PUT /api/v1/campaigns/<campaign_slug>/session/articles/<article_id>` using `title`, `body_markdown`, optional replacement `image`, or optional existing-image `image_alt_text` / `image_caption`. Authorized edit projections expose a `base_token` in `v1:` plus 64 lowercase hexadecimal characters; staged edits require the original token. Missing or malformed tokens return 400; stale, revealed, or deleted articles return 409. A successful edit atomically updates text, image, and metadata, while an unchanged save does not create a new version. There is no baseline upgrade, automatic retry, or creation-token requirement. Omitted metadata and upload limits retain their existing behavior. The revised article must retain either body text or an existing or replacement image. Revealed articles remain immutable in the prep queue.
- `DELETE /api/v1/campaigns/<campaign_slug>/session/articles/revealed` removes all currently revealed session articles for DM/admin cleanup and returns the deleted article IDs.
- Embedded image payloads use JSON objects with `filename`, optional `media_type`, and `data_base64`.
- Systems browsing reads are available at `GET /api/v1/campaigns/<campaign_slug>/systems`, its `/systems/search` alias, `/systems/sources`, `/systems/sources/<source_id>`, `/systems/sources/<source_id>/types/<entry_type>`, and `/systems/entries/<entry_slug>`. Together with the two app-admin import-run reads, `systems_api_routes.py` owns seven read handlers across eight GET rules plus eight mutation handlers for source policy, entry overrides, custom-entry create/update/archive/restore, campaign item-mechanics import, and app-admin DND-5E ingest, for 15 handlers and 16 explicit registrations on the existing API Blueprint. Landing and search share `api.systems_index`; all other registrations retain their bare `api.*` endpoint identifiers, including `api.systems_import_run_list`, `api.systems_import_run_detail`, `api.systems_item_mechanics_import`, `api.systems_import_dnd5e`, and the four `api.systems_custom_entry_*` identifiers. The custom-entry, item-mechanics, and DND-5E ingest POST mutation rules retain implicit `OPTIONS` without `HEAD`. On the final qualified Phase 3B branch, `api.py` retains the Blueprint, 35 direct route decorators, shared decorators, request/error helpers, serializers, import-run and importer/store/service composition, the full DM Content Systems-payload builder, dependency wiring, and the other nonmoved Systems JSON routes; extracted Session, Character, Auth, Admin, and Systems registrars own the remainder.
- These reads preserve source-level and entry-level visibility, support `q` on landing/category searches, support `reference_q` for landing and source-scoped rules-reference metadata searches, and return server-rendered safe Systems entry HTML for detail pages. The source-list GET returns all configured states to a Systems manager and only enabled, accessible states to a non-manager, with matching permission fields. Because GET and PUT share `/systems/sources`, its OPTIONS response advertises GET, HEAD, OPTIONS, and PUT.
- For direct-admin entry inspection, the browser and API intentionally differ at the source boundary: a direct app admin can use the API to inspect a stored entry through a disabled source, while the browser still requires the source to be enabled before rendering entry detail. An admin using `View As` is evaluated as the effective target actor and retains no admin bypass. Systems source updates, entry-override writes, custom campaign entry mutations, and campaign item mechanics import remain DM/admin only. The eight Systems mutation transports in `systems_api_routes.py` retain their payloads, authorization, persistence, and durability behavior: selected source-policy/source batches and entry-override saves join business writes and required auth audits in one transaction owned by `systems_mutations.py`, after catalog/seed preparation. Missing required saved-source readback or audit failure rolls back that selected operation. No-change source submissions write no source-update audits; repeated overrides remain audited. Serialization and refreshed management-payload construction follow commit and can fail after durability. Custom-entry and campaign item-mechanics writes retain independent service commits before their controller audits, and app-admin DND-5E ingest writes its one app-global success audit after the full import and before response preparation; these excluded paths retain partial durable outcomes. The DM Content Systems management payload is also DM/admin only and intentionally omits raw import `source_path` values.
- Combat reads return a structured tracker payload plus live-play metadata: `live_revision`, `live_view_token`, `selected_combatant`, `selected_player_character`, `player_character_targets`, manager-only `available_character_choices`, `available_statblock_choices`, `combat_condition_options`, `poll_settings`, and Flask links for Combat, DM Status, and DM Controls where authorized. Clients can echo `X-Live-Revision` and `X-Live-View-Token` on `GET .../combat` or `GET .../combat/live-state`; matching values return only `changed: false`, `live_revision`, and `live_view_token` so clients can preserve the already-mounted player or DM combat workspace. Unsupported campaign systems return `combat_system_supported: false` with an empty tracker and fallback link instead of starting live polling.
- Combat mutations are DM/admin only except for player-character vitals, which can also be updated by the assigned owner player when they provide the current sheet revision. Browser Combat consumes the read payload, combat mutation endpoints, Systems monster search, and shared Character detail/session-state contracts for player Combat, manager DM Status, and manager DM Controls. DM Status uses `combatant=<id>` as canonical selected focus for turn, vitals, action economy, source-backed NPC resources, condition add/remove, selected-PC detail, and selected-combatant cleanup. DM Controls uses the same JSON endpoints for player-character seeding, manual NPC seeding, DM Content statblock seeding, Systems monster search/seeding, turn advance, and clear-tracker cleanup.
- Source-backed NPC resources appear on visible combatant summaries as `npc_resource_counters` and `npc_resource_notes`. Supported counters are combatant-owned current/max rows seeded from DM Content statblocks or Systems monsters. Strict terminal recharge syntax in typed Markdown ATX ability headings or Systems ability-name positions seeds a full one-use counter with canonical `reset_label`; ambiguous, body-only, nonterminal, out-of-range, qualified, conflicting, and otherwise unsupported recharge prose remains a note. The persisted `reset_kind = recharge_d6` and `recharge_threshold` fields are internal provenance/model metadata and are not added to the public counter object, whose keys and accepted query counts remain unchanged. `PATCH .../npc-resources` is DM/admin only and accepts `expected_combatant_revision` plus `counters: [{resource_key, current_value}]`. Integrated browser slice `QOL-NPC-6B-C1`, shipped in source on protected `main` by product commit `3d374f9209e73f0fac93efc6913a6cedaf68bc7b` and documentation integration commit `025c433949a79c61c5fd4433cee5000817752f7e`, reuses that absolute-update service/store behavior through a separate CSRF-protected Flask POST form for one selected counter; it does not change this PATCH contract, its public payload, query behavior, or authorization. The API still has no roll, die-result, restore/reset, group-reset, or automatic-reset endpoint. This source integration is not a deployment or live-use claim.
- Combatant-row combat writes can also send `expected_combatant_revision`; when that row changed first, the API returns `409 state_conflict` instead of last-writing stale movement, action-economy, source-backed NPC resource, NPC vitals, or turn-value payloads.
- Character session mutations require `expected_revision` and return `409 state_conflict` when the sheet changed first. These live/session JSON lanes are available to DMs/admins and to a player assigned to that character, even when the full Characters surface remains DM-only; unassigned players still receive `403 forbidden`. For Xianxia characters, `PATCH .../session/vitals` also accepts `current_stance`, `temp_stance`, `current_jing`, `current_qi`, `current_shen`, `current_yin`, `current_yang`, and `current_dao` alongside shared HP/temp HP. `PATCH .../session/inventory/<item_id>` routes to the Xianxia inventory quantity write path when the character system is Xianxia. `POST .../session/xianxia-dao-immolating-use-requests` accepts `request_name`, optional `notes`, and optional `prepared_record_index`; it appends a pending ad hoc or prepared-note-backed definition-level use request. `POST .../session/xianxia-dao-immolating-use-records` is DM/session-manager only and accepts `use_record_index` plus optional `notes`; it records one approved unused Dao Immolating use, spends the fixed 10 Insight cost, marks that use history record used, and returns the refreshed character payload.
- Character roster reads accept optional `q` search and return Flask-aligned roster cards, including derived class text, HP/temp HP, Hit Dice summary, up to three resource previews, sheet links, roster tool flags, and protected portrait metadata when the character profile points at an existing campaign asset. If the viewer cannot access the broader Characters scope but is assigned to one or more characters, the roster read returns only those assigned character cards for live/session surfaces such as Combat.
- `GET /api/v1/campaigns/<campaign_slug>/characters/create` returns the system-lane create context. DND-5E campaigns receive the level-1 builder core options, dynamic choice sections, preview, readiness flag, and Flask links. Xianxia campaigns receive canonical Attribute/Effort/Energy/Skill fields, Martial Art/rank choices, GM grant fields, starting defaults, and import links. `POST .../characters/create` accepts `values`, rebuilds the authoritative backend context, validates through the DND-5E or Xianxia builder, writes `definition.yaml` and `import.yaml`, initializes SQLite mutable state, and returns the refreshed character plus Flask links. The endpoint requires the same character-management access as Flask create.
- `GET /api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual` returns the manual Xianxia import context. `POST .../characters/import/xianxia-manual` accepts `values`; without `confirm_import` it returns a review preview and writes nothing, and with `confirm_import: true` it writes the normal Xianxia definition/import files plus initial SQLite state. The route is Xianxia-only and uses the same enabled Martial Art Systems choices as the Flask manual importer.
- Character detail reads return the raw file-backed definition/state plus presentation helpers and detail links. DND-5E `equipment_state.rows` and `presented_inventory` include linked item `href` and server-rendered `description_html` when the item resolves to an accessible Systems entry or campaign page. `presented_spellcasting` mirrors the browser spell presentation with spell facts, badges, source links, and server-rendered `description_html` for linked spells. Xianxia reads expose `presented_xianxia`, which mirrors the existing `xianxia_read` presenter context for Character and Session Character sections, including Quick Reference derivations, Resources, active state, Martial Arts, Techniques, Skills, Equipment, modeled Inventory, Xianxia currency, approval/reference records, and notes-adjacent state. Detail payloads also include protected portrait metadata when available.
- DND character detail retains `definition` as `historical_raw` and adds `update_safe_definition` with legacy equipment activation keys stripped, `effective_equipment_activation`, and `projection_warnings`. Manager raw content GET keeps its historical `definition` and adds `definition_label`, `update_safe_definition`, `state_revision`, `effective_equipment_activation`, `activation_warnings`, and `source_warnings`. Existing DND raw content PUT rejects equipment activation keys on an existing character with `400 validation_error` directing the caller to the revisioned equipment action; new-character creation may seed YAML. An existing raw DND update can append only proven new equipment inventory rows and the activation marker beyond the same state-validation behavior its prior raw path already performed; it refuses any additional change to old inventory, HP, resources, spell state, notes, or other SQLite fields. A DND source-only pair with no SQLite state refuses raw PUT and ordinary reads pending separate operator reconciliation. `PATCH .../session/equipment/<item_id>` still accepts the same URL and fields and returns the existing refreshed character shape after one state-only revision. Stale state/definition or protected publication conflicts return recoverable conflict responses.
- Character Controls and portrait endpoints remain on the character-detail contract. The `controls` payload is included when the campaign supports character controls and the viewer has session-mode character access; it reports owner assignment, owner identity, admin assignment choices, delete permission, and Flask links. `POST .../controls/assignment` assigns an active campaign player as owner and is app-admin only. `DELETE .../controls/assignment` clears the current owner assignment and is app-admin only. `DELETE .../controls` deletes the character after case-sensitive `confirm_character_slug` matches the route slug, removes the exact captured managed files, mutable state, and assignment records, writes one Controls audit, and requires DM/admin content-management permission. Its existing success message, deleted-character fields, roster links, and error statuses are unchanged. `PUT .../portrait` writes the campaign-owned portrait asset from an embedded file payload, and `DELETE .../portrait` clears the portrait metadata and asset. Controls and portrait writes return `409 state_conflict` on stale sheet revisions.
- `GET .../advanced-editor` returns the DND-5E native edit field context, option lists, current state revision, links, and unsupported fallback metadata for non-DND lanes. `PUT .../advanced-editor` accepts `expected_revision` plus a flat `values` object matching the returned field names, reuses the existing native edit apply/derivation path for proficiencies, reference text, stat adjustments, recoverable penalties, custom features, and manual equipment, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Advanced Editor writes are available to DMs/admins and assigned players with session-mode character access, return `409 state_conflict` on stale sheet revisions, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../progression-repair` returns the DND-5E imported-character repair context, current sheet revision, readiness reasons, class/subclass repair rows, species/background options, prior feat or optional-feature backfill rows, spell-row classification fields, Flask links, and unsupported fallback metadata for non-repairable lanes. `POST .../progression-repair` accepts `expected_revision` plus a flat `values` object matching the returned repair field names, reuses the existing imported progression-repair apply path, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Progression repair writes are manager-only, return `409 state_conflict` on stale sheet revisions, return a Level Up handoff when the sheet becomes ready, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../retraining` returns the DND-5E native structured retraining context, current sheet revision, supported linked-feature choice rows, Flask links, and unsupported or repairable fallback metadata for non-ready lanes. `POST .../retraining` accepts `expected_revision` plus a flat `values` object matching the returned retraining field names, reuses the existing native edit/retraining derivation path for persisted linked-feature choices, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Retraining writes use the same session-mode character access as Flask retraining, return `409 state_conflict` on stale sheet revisions, point repairable imported sheets at progression repair, and return `unsupported_campaign_system` for unsupported lanes.
- `GET .../level-up` returns the DND-5E native level-up context, current sheet revision, readiness metadata, dynamic choice sections, preview payload, Flask links, and unsupported or repairable fallback metadata for non-ready lanes. `POST .../level-up` accepts `expected_revision` plus a flat `values` object matching the returned level-up field names, reuses the existing native level-up builder/apply path for one-level advancement and HP gain, then writes `definition.yaml`, `import.yaml`, and reconciled SQLite state. Level-up writes are manager-only, return `409 state_conflict` on stale sheet revisions, point repairable imported sheets at progression repair, and return `unsupported_campaign_system` for non-DND lanes.
- `GET .../cultivation` returns the Xianxia Cultivation context, current sheet revision, Flask links, and unsupported fallback metadata for non-Xianxia sheets. `POST .../cultivation` accepts `expected_revision`, an action name, and a flat `values` object matching the Flask Cultivation form names; supported actions include Insight save, Gathering Insight, Cultivation Energy, Meditation, Conditioning, Training, Martial Art rank advancement, Generic Technique learning, Realm review start, Realm stat reset, Immortal/Divine rebuild, and final Realm confirmation. Cultivation writes are manager-only, return `409 state_conflict` on stale sheet revisions, preserve mutable state through definition reconciliation, and return `unsupported_campaign_system` for non-Xianxia lanes.
- `PATCH /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit` is the legacy compatibility contract for out-of-session Character-page batching. It accepts one `expected_revision` plus absolute-value section payloads for the state-backed Character-page fields (`vitals`, `resources`, `spell_slots`, `inventory`, `currency`, `notes`, and `personal`).
- The `sheet-edit` batch route is intentionally absolute-value only. Delta actions such as `hp_delta`, resource `delta`, spell-slot `delta_used`, currency `delta`, and rest actions stay on the immediate live-edit routes instead of mixing relative and batched writes.
- `sheet-edit` batches use one shared revision check for the whole request. If any other actor changed the character first, the entire batch is rejected with `409 state_conflict` rather than partially applying the payload.
- If a `409` is returned, clients should refresh and retry from a fresh draft because the route does not merge partial drafts.
- The browser normal Character workflow now favors inline per-form state edits; DND-5E sheets expose HP, resources, spell slots, inventory quantities, currency, and notes, while Xianxia sheets expose Resources, Techniques request/record actions, Inventory/currency, and Notes state lanes. Batch behavior is still available for compatibility and is not the recommended browser workflow.
- Browser lane boundaries are now: the normal Character page inline state slice for quick DND HP/resource/slot/inventory/currency/notes and Xianxia resource/technique/inventory/currency/notes updates, `Session Character` for active-session edits, and `Combat`/`Encounter status` for encounter-context edits tied to `combatant=<id>`.
- API reads and writes use the same visibility and role checks as the app. A DM token can do DM work; a player token only sees or edits what that player could in the site.

### Custom spell profiles

The ordinary custom-entry create/update endpoints additionally accept `spell_profile` for DND-5E entries of type `spell`, plus optional string `spell_higher_level_markdown`. The serializer returns both fields for editing. Existing authentication, manager authorization, CSRF, immutable update identity, error envelopes and partial-outcome ordering apply.

`spell_profile` is a closed object with required `level`, `school`, `casting_time`, `range`, `components`, `duration`, and `classes`; optional `ritual`, `savingThrow`, and `spellAttack`. These use the imported spell metadata shapes. `classes` accepts `fromClassList: [{"name": "Wizard", "source": "PHB"}]`; derived `class_lists` is server-owned. The service validates nested keys, types and bounds (profile at most 16,000 characters). Components may include material text or `{text, cost?, consume?}`; cost is copper pieces and consume is an explicit boolean. Unsupported fields or type conversions return the existing validation envelope rather than silently dropping mechanics.

Omitted/null `spell_profile` preserves existing mechanics; `{}` is invalid. Existing profile fields omitted from an otherwise complete replacement are retained unless explicitly updated (for example ritual false or an empty savingThrow list). The main `body_markdown` remains required. Higher-level text has a 30,000-character limit; omission preserves the existing authored value, while an explicit empty string clears it. The form and API store current sanitized narrative projections alongside the retained profile. Legacy higher-level structures without editor text require an explicit source-backed separation. Source declarations neither authorize a spell cast nor establish caster metrics for a DM-selected ability check.

### Armor Model Read Projection

DND Equipment payloads expose `arcane_armor_state.hands`, keyed by `main-hand` and `off-hand`, with `status` (`clear`, `occupied`, or `unknown`) and `reason`. `enabled` is a strict retained boolean or null when unknown. `thunder_gauntlets_available` requires a qualified selected Guardian, current wearing and at least one proved clear hand; `defensive_field_available` requires the selected feature and current wearing independently of hands. An unproved model/source/activation cannot become availability through a name or copied value.

The shared read frame may include per-hand STR/INT attack formula alternatives and availability reasons, plus the current class-level Defensive Field amount. They are observational projections and do not enter `update_safe_definition`, raw exports or save provenance. Existing equipment and feature-state writes retain their separate contracts; no model switch, hand-assignment, attack, resource use or doffing effect endpoint is added. An item's generic wondrous classification does not prove worn versus held placement, so unsupported placement remains unknown.

Full Character serialization reuses its already computed armor frame for that record. An independent equipment read explicitly scopes components, catalogs and derivation to equipment, current ability layers and transient numeric dependencies, using targeted active-item support. It does not request full sheet-entry or spell normalization solely to produce the armor frame. This is a dependency contract, not a measured latency guarantee.

Native reconstruction Review can show explicit exact-source `armor_model_choices` with the selected class/branch and unchanged historical summary. Independent reconstruction custody and current source checks are required on subsequent reads. Typed artisan-tool choices remain separate class/background proficiency selections; a chosen tool must already be retained, and this support does not grant a physical item or change current play state.

### Explicit Reconstruction Skill Adoption

The existing browser reconstruction form accepts a separate scalar `skill_adoption_<canonical skill key>` choice: `keep` or the current server-generated contract digest for an eligible existing `none` skill and exact ordinary source slot. The corresponding `feature_proficiency_<index>` selection must independently choose that same skill. Unsupported, duplicate, stale or unused confirmations refuse. There is no arbitrary skill-row/bonus input or new API endpoint.

Review includes the original row, source owner/slot and actual qualified derived result. Successful publication would retain immutable `source.native_reconstruction_choices.skill_adoptions` history and its independently audited reconstruction custody. A signed nonpublishing Review is not a saved adoption. Current reads require the source slot and recovered witness; later valid advancement may change expertise or bonus while preserving the historical record. Existing exact play-state, import, original-content and publication checks remain unchanged.

### Optional Class Weapon Source Clauses

Reconstruction recognizes the strict structured optional Firearms clause without adding a proficiency, permission field or required selection. A retained unproved Firearms label remains in the raw definition, with the existing unresolved-weapons status in Review. Fixed current class grants remain independently eligible. Unsupported structured shapes refuse reconstruction; the shared native read extractor withholds its class grant result without turning the object into a label or propagating a shape error. No endpoint, marker, choice index, play-state or publication contract changes.

### Feature proficiency reconstruction and physical tracker associations

Existing native creation/advancement and reconstruction routes share the typed class/subclass feature proficiency parser. No new mutation endpoint is introduced. Native feature proficiency choices are retained under `source.native_feature_proficiency_choices`, bound to source/class/member, prior inputs and selected branch by the native publication proof. They cannot be edited through an ordinary Character update. Reconstruction uses its existing explicit proficiency inputs and unresolved values; missing fixed proficiency observations are not automatically upgraded.

Reconstruction may additionally accept `feature_auto_expertise_<owner-digest>` and `feature_tracker_association_<tracker-digest>` scalar fields. `keep` preserves the observation without adoption; other values must exactly match a currently offered contract digest. Automatic expertise preserves its original observation in `source.native_reconstruction_choices.automatic_tool_expertise`. Conditional retained acquisitions use `feature_proficiency_conditions`; physical associations use `tracker_associations`. These records are history, not independent authority. Their origin digests, complete prior observations and independently recovered generation-pair audit custody are required on replay. Signed Review, manager/CSRF checks, reserved recomputation, exact state, CAS and durable confirmation continue through the existing reconstruction path.

Automatic tool expertise projects from the current authenticated capability and qualified proficient tools, including tools acquired later. It does not invent tool selections or change raw export/update-safe observations during a read. Physical resource identifiers remain unchanged across source qualification, normalization and advancement. Initial association offers support one source-owned class and fixed/level/half-level/PB/threshold capacities and supported sums; ability-dependent offers are withheld until independently qualified inputs are available. Unknown counts do not become known. These contracts do not authorize source admission, Character Apply, spending or recovery operations.

Conditional reconstruction chronology is bounded to confirmed starting class/species/background grants or strictly earlier attained feature grants of the same class. Later or unordered current grants do not establish the prerequisite; unsupported chronology remains unresolved.

Initial physical association also withholds an offer when a current item source modifies that pool capacity. An existing association with an active item bonus still targeting the canonical pool has unproved current capacity; it cannot silently fall back to a smaller base maximum. The saved physical tracker, count and capacity observations remain intact. This support does not retarget item bonuses.


### Prepared ammunition and triggered item reactions

The existing inventory PATCH/HTML POST also accepts the following disjoint
operations, always with the exact current `expected_revision` and existing
character access/CSRF rules. JSON rejects duplicate or unknown fields, nested
values, client effect/metric data and conflicting slot selections. HTML uses
`yes` for the confirmations; JSON requires `true`.

- `item_triggered_reaction`: `confirm_reaction`, `trigger` (one of `pushed`,
  `pulled`, `knocked_prone`, `fall`) and `target_kind` (`self` or
  `willing_visible_creature`). Requires the exact current v3 source rule,
  equipped item and qualified remaining use. Spends one use; does not resolve
  target effects or maintain reaction economy. Attack confirmations are rejected.
- `prepared_observe`: manager-only `confirm_observation`, `load_kind` (`empty`,
  `mundane`, `enchanted`), optional `choice_id` and `slot_level`. The latter two
  must be empty/absent for nonenchanted loads; enchanted loads require both.
  Records a first actual current observation only, without spending a slot.
- `prepared_load`: `confirm_reload`, `choice_id`, and either `slot_selection`
  (`lane|level`) or `slot_lane_id` plus `slot_level` (1-9). Requires a known empty
  load and qualified class/attunement/available slot. Atomically spends one slot
  and records the load. It cannot replace an existing load.
- `prepared_discharge`: `confirm_discharge`. Requires a known actual load and
  qualified class/equipped/attuned ownership. Clears that load once; no slot cost
  and no inferred hit, damage result, target or condition application.

Prepared state is held in `item_prepared_ammunition`, keyed by unique physical
item ID. Latest actor-bound audit custody, current source basis, full-state
transition seals, source reservation and CAS guard its use. Unknown/stale facts
remain preserved and disabled. No operation silently refills, deletes history,
assigns an infusion or updates other characters. An unadopted source does not
make a current-load observation or item action available.


### Artificer assignment observations

`GET /api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-assignments`
returns `state_revision` and separate `assignments.infusions` / `.tinkering`
status, maximum, entries, eligible choices and manual-effect limits. It requires
session-edit permission and never initializes a ledger.

`POST` on the same endpoint uses normal character mutation admission and returns
the refreshed character. Supply integer `expected_revision`, `kind` (`infusions`
or `tinkering`), `operation`, and boolean `confirm: true`. Keys must be unique;
unknown fields, wrong types and nonfinite numbers are rejected.

- `confirm_empty`: no further fields; confirms a genuinely empty unknown member
  without erasing existing assignments or legacy observations.
- `assign`: exact returned `choice_id`, `object_mode` (`inventory`/`external`),
  `object_id`, `object_name`, `recipient`, eligible `object_kind`, `nonmagical: true`,
  `attunement` (`unknown`/`none`/`self`/`other`), `touch: true`, `replace_oldest`
  (empty below capacity; exact oldest assignment ID at capacity). Optional integer
  `value_gp` must meet the Homunculus target's100gp minimum. Infusions require
  `long_rest: true`. Tinkering requires `tools`, `action`, `tiny` all true,
  `property_text`, integer `message_seconds` (1-6 for message, zero otherwise).
  Only visual also requires `visual_type` (`text`/`picture`/`shapes`/`mixed`) and
  `visual_text`: at most25 actual words, nonempty for text/mixed and empty for
  picture/shapes. Property descriptions are separate from displayed text.
- `end`: `assignment_id`, `reason`. Tinkering uses `action_touch` plus `action`
  and `touch` true. Infusions may record `item_destroyed` or `death_duration`
  with integer `days_elapsed`. `knowledge_loss` cannot end a still-known recipe;
  stale knowledge requires reconciliation. `campaign_deactivation` records an
  actual deactivation only when the current admitted campaign configuration
  explicitly enables `allow_artificer_infusion_deactivation: true`. The action
  requires `policy_revision` and `policy_sha256` from the returned infusion
  `deactivation_policy`; stale policy is rejected. The action audit records the
  configuration generation and digest; it does not infer a
  rest, action, or touch cost.

The optional version1 `artificer_assignments` ledger and same-transaction
`character_artificer_assignment_applied` audit event preserve confirmed-empty
versus unknown. Recipes, historical counters, inventory, history and unrelated
play state remain unchanged. External observations do not write another character.
These controls record assignments and rules; effects, companions, charges and
recipient statistics remain table-managed. The legacy `artificer-infusions`
endpoint remains withheld for typed adopters.
