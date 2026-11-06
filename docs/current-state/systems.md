# Systems Wiki

Last updated: 2026-11-03

## Owns

- Shared Systems libraries, source policy, imports, source/category/entry browsing, RULES/book slices, campaign overrides, custom entries, and Systems-linked mechanics used by characters and combat.

## Current User-Facing Behavior

- PHB import normalizes version-1 `feature_values` contracts for the exact
  Destroy Undead milestones and Sneak Attack publication. These explicitly bind
  family, facet, evolution, owning class, attainment level and source-body digest;
  display names do not establish family membership. The Rogue import also keeps
  the genuine twenty-row typed dice cells in `body.feature_value_source_tables`
  and their validated normalized values/provenance in `metadata.feature_value_tables`.
  Original source entries remain separate. Character reads require current
  contracts and qualification; they do not recover missing tables or formulas
  from prose. Existing records are not backfilled automatically. Updating them
  requires separate source-data authority and qualification of affected readers.
  This initial contract does not extend custom-feature authoring, other classes,
  resource state, source policy or gameplay automation; no SQL migration is used.

- Deterministic attained-feature qualification shares the class/subclass progression selector with Systems display, including exact spine, same-source unconditional references, visibility and ambiguity/bounds checks, while omitting embedded-card HTML and option decoration. Display callers retain their normal cards. Qualification does not gain catalogue siblings or elective options, and this separation alone establishes no runtime latency claim.

- Systems Wiki uses shared system libraries plus per-campaign source policy instead of duplicating imports per campaign.
- DND-5E source data is imported once into the shared app library and filtered per campaign by source policy.
- DND-5E item import and item-metadata repair share a bounded source-clause extractor for paired spell attack/save-DC bonuses. It requires an explicit literal bonus, canonical class scope, and wearing/holding activation; native bonus fields must agree when present. The complete source must fit the finite supported flat form: one bonus paragraph, optionally preceded within that paragraph by the complete supported blood-attunement procedure, and optionally one whole separate Hit Dice recovery/dawn reference paragraph for the same object. Recovery remains reference-only. Every other sentence, paragraph, nested block, expression, or structure withholds extraction, irrespective of its words. Item names, rarity, and attunement eligibility do not establish spell values or scope. Existing stored typed metadata, including explicit empty or conflicting values, is preserved rather than replaced or appended. Raw source `spellcasting_modifiers` extensions are retained only as inert `native_spellcasting_modifiers` evidence and prevent automatic inference; they do not become active engine metadata.
- Native item attunement text is preserved and can supply an explicit `requires_attunement` flag. Attunement-prefixed bonus extraction additionally requires a supported native true boolean or non-false attunement string; absent, false, or unreadable native attunement metadata withholds extraction rather than inventing a requirement from prose. Extracted modifiers use the existing class selector and effective-item pipeline; class ambiguity and source/owner policy still withhold automation, and manual spell totals retain their final-value contract. Importing code does not refresh existing SQLite item rows or adopt a character's formula provenance; those remain separate authorized operations. Armor and weapon metadata repair retains its existing behavior alongside this additive item metadata.
- Systems landing and source pages expose a metadata-focused Rules Reference Search for `book` and `rule` entries.
- Source pages are lightweight category indexes; source category pages load one entry type at a time.
- Entry detail pages can surface related rules references and campaign overlays.
- Class, subclass, and optional-feature browsing folds features into parent pages while keeping standalone feature entries searchable/direct-linkable. Campaign Systems search filters effective source and entry eligibility before applying its result cap and hydration, including manager and View As policy, while retaining the established result order.

## Registered Source Replacement Contract

- The existing authenticated registered-feature writer supports the exact
  `wild_magic_modification@1/wild_die@1` selection alongside the Avatar grant.
  It authors a typed replacement of PHB Wild Magic Surge for an exact attained
  Sorcerer/Wild owner, with explicit Tides/Bend Luck carry-forward and the finite
  Wild Die capacity/reset recipe. It adds no endpoint, arbitrary metadata editor,
  source enablement or visibility expansion.
- Ordinary feature body edits retain server-owned registration metadata. The
  legacy normalizer and descriptive base-rule links do not issue authority.
  Actual character composition requires current eligible publication facts,
  selected owner and a retained source-selection claim. Source Repair remains
  the existing reviewed relink path; it does not publish a private wiki page.
- Existing Wild Die narrative remains the rule reference for optional spending,
  roll bands, downward halves and additive natural 1/20 consequences. This
  source contract does not invent roll triggers, extra costs, reset timing or a
  natural-20/Tides interaction. Stored totals are never operative formula inputs.
  Implementation/source review does not claim source creation, character adoption
  or genuine application qualification.

## Management Contract

- DM Content -> `Systems` is the current browser management lane.
- `player_wiki/systems_routes.py` owns browser transport for the five Systems index/search/source/category/entry reads; the private mechanics-impact queue and selected-detail reads; the source-policy and entry-override mutations; the five custom-entry create, edit, update, archive, and restore controllers; the app-admin shared/core permission mutation; the shared-entry edit GET and update POST; and the browser DND-5E import POST. Eighteen explicit app-level registrations preserve their bare Flask endpoint identifiers and one-rule-per-method/path compatibility. The intended four-GET subset is the custom-entry edit GET, shared-entry edit GET, mechanics-impact queue GET, and mechanics-impact selected-detail GET. Both mechanics-impact registrations are explicit GET-only registrations with Flask-supplied `HEAD` and `OPTIONS`; the two editor GETs retain the same supplied methods. The extracted POST registrations retain implicit `OPTIONS` without `HEAD`.
- The shared Systems management panel begins with a six-anchor navigator for Source Enablement, Entry Overrides, Custom Entries, Shared/Core Editing, Shared Source Imports, and Import-Run History. One separate static, count-free Mechanics Review card links to the review queue without loading it; both DM Content -> Systems and the Systems control panel reuse that presentation.
- `player_wiki/systems_api_routes.py` owns JSON transport for 15 Systems handlers through 16 explicit registrations on the existing API Blueprint: seven read handlers across eight GET rules plus the eight source-policy, entry-override, custom-entry create/update/archive/restore, campaign item-mechanics import, and app-admin DND-5E ingest mutation handlers. Landing and search share `api.systems_index`; all other handlers retain their existing bare `api.*` identifiers, including `api.systems_import_run_list`, `api.systems_import_run_detail`, `api.systems_item_mechanics_import`, and `api.systems_import_dnd5e`. The import-run list and detail transports remain app-admin-only, read-only GETs with implicit `HEAD` and `OPTIONS`; they expose stored import history through the existing serializer, including raw `source_path` and full summaries. The DND-5E ingest transport remains one app-admin-only POST rule with implicit `OPTIONS` and no `HEAD`. In deployed Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`, `api.py` retains the Blueprint, 35 direct route decorators, shared decorators, request and error helpers, serializers, full DM Content Systems-payload builder, repository/service and importer/store composition, dependency wiring, and all other nonmoved Systems API routes; the final count includes later Session, Character, Auth, and Admin extraction rather than a change to the 33-rule/33-contract Systems boundary. The later documentation closeout is not part of that deployed image. The source-list GET and source-policy PUT remain one rule per method on the same path, whose OPTIONS response advertises GET, HEAD, OPTIONS, and PUT; each custom-entry, item-mechanics, and DND-5E ingest POST mutation remains one rule with implicit `OPTIONS` and no `HEAD`.
- The API source-list read returns every configured source state to a Systems manager. A non-manager receives only enabled source states that the effective actor can access; the top-level and per-source permission fields describe that projection.
- Entry-detail admin behavior intentionally differs between browser and API transport. The browser requires an enabled source even for a direct app admin, then lets that admin inspect a disabled or archived entry within the enabled source. The API lets a direct app admin inspect a stored entry even through a disabled source. `View As` replaces the effective actor on both safe-read surfaces, so the real admin does not retain either entry-level bypass while viewing as another user.
- Transport ownership does not change Systems product, authorization, policy, audit, persistence, context, or presentation ownership. Except for the finite registered-feature authoring branch below, the seven campaign API mutations in `systems_api_routes.py` retain their payloads, authorization, audit ordering, and durability behavior: `auth.py` owns Systems access helpers and shared-editor authority, `SystemsService` owns policy/source/entry/override, custom-entry, and campaign item-mechanics orchestration, `SystemsStore` owns their SQLite persistence and shared-edit/import-run records, and `AuthStore` owns auth audit persistence. The app-admin DND-5E API ingest transport writes one app-global `systems_dnd5e_source_imported` event after the full import succeeds and before import-run refetch or response serialization. `api.py` still supplies the shared JSON loader/error envelope, serializers, full DM Content Systems-payload builder, and importer/store/service composition as explicit transport dependencies. DM Content and the Systems control panel remain the two presentation surfaces; `app.py` retains the four read-context builders, both surface context builders, `build_systems_import_form()`, the custom-entry DOM-ID helper injected into the browser transport module, and the remaining control-panel view; existing templates remain the HTML owners. `Dnd5eSystemsImporter` and the archive-ingest helpers retain DND-5E import and archive-safety ownership. Shared-entry form/JSON, resolver, and editor-rendering helpers remain with the extracted controllers in `systems_routes.py`; `systems_mutations.py` owns original-source identity, changed-field calculation, and the joined shared-entry provenance/auth-audit writes.
- Custom campaign Systems entries are campaign-owned DM authoring rows stored only through the Systems SQLite service/store path. Create assigns the custom-source-prefixed slug; update keeps the existing slug and entry key rather than accepting a replacement slug. Create and update validation rerender the originating control-panel or DM Content surface with status 400, and successful lifecycle submissions redirect to that surface with the custom-entry anchor. Archive and restore validation redirect to the originating surface's custom-entry section.
- Archive preserves the custom entry and its visibility override while setting its enablement override to disabled. Restore preserves the entry and visibility override while clearing the enablement override back to inheritance.
- Ordinary custom-entry creation and non-feature lifecycle persistence retain independent custom-source, campaign-policy, enabled-source, entry and override commits; the controller writes its auth audit after service return. Invalid ordinary create input can therefore leave supporting policy rows, and later write or audit failures can leave earlier commits durable. Feature-to-feature body edits now own their entry and override together while their outer audit remains separate. The selected registered-feature create described below additionally owns its required audit and performs no supporting-source preparation. Existing body fields retain last-writer-wins behavior while server metadata is read under the feature write owner.
- Ordinary custom-entry JSON mutations preserve that lifecycle without redirects; the selected registered-feature create has the bounded response described below. Ordinary success returns HTTP 200 with `ok`, the serialized `entry`, and the refreshed DM Content `systems` management payload. Create and update parse a JSON object and retain the established `invalid_json` 400 envelope for malformed, non-object, Markdown-limit, and service-validation failures; archive and restore do not consume a request body and retain the `validation_error` 400 envelope for an invalid entry. The controller writes its auth audit after the durable service mutation and before entry serialization and full-payload construction, so audit, serializer, or payload failures can occur after earlier SQLite commits; archive/restore also preserve their refetch-or-original response fallback.
- Campaign Item Mechanics import/refresh is currently available through the
  JSON API and operator CLI. The Flask DM Content -> `Systems` management panel
  does not render a Campaign Item Mechanics browser lane.
- Browser shared-source imports are app-admin-only shared-library maintenance with import-run review. `campaign_systems_control_panel_import_dnd5e` first requires an existing campaign and applies the existing Systems-management check, then requires app-admin authority and a DND-5E Systems library; missing campaigns remain 404, anonymous requests redirect to sign-in, authenticated non-admins remain 403, and unsupported campaign systems rerender the originating surface with status 400. CSRF and View As mutation protections remain in the shared browser boundary.
- The browser import accepts either the Systems control panel or DM Content -> `Systems` as its presentation/return surface. Validation rerenders that surface with status 400 while retaining source, entry-family, import-version, and return-target fields but never the uploaded file; success redirects to the same surface at `#systems-import-history`. The supported bare POST endpoint keeps implicit `OPTIONS` and no `HEAD`.
- Browser source IDs are normalized and deduplicated in first-submitted order, then imported sequentially into the shared library. Each source creates an import run, replaces that source's selected entry families, and marks its run complete through separate commits; a later-source failure can leave earlier source imports and runs durable, and a completion failure can occur after replacement is durable. The controller writes one auth audit only after all sources return, so an audit failure can leave all source replacements and completed runs durable. This path does not change campaign source policy or entry overrides, refresh the campaign repository, or bump Combat revisions.
- Direct and batch importer entry refuses an active caller transaction or savepoint before library seeding or run creation, outside failure bookkeeping. Standalone run creation, completion, and failure recording also require clean transaction entry. Their own precommit write failures roll back before any subsequent bookkeeping can commit; a cleanup failure closes only the admitted connection. Refusal itself never commits, rolls back, closes, or records over caller-owned work. Separate per-source commits and postcommit readback/audit failures retain their existing durability boundaries.
- DND source replacement also protects curated `native_spell_grants` feature metadata. Within the owned `BEGIN IMMEDIATE` replacement transaction, selected existing rows are inspected before deletion; any present container, including unknown or malformed values, refuses replacement pending explicit source reconciliation. Fresh import prose does not rebase or overwrite an authenticated grant basis. Concurrent curation cannot slip between an unlocked check and replacement. Refusal rolls back only the replacement's own transaction before import-failure bookkeeping. Unselected source families remain untouched; built-in RULES and Xianxia seeding retain their existing replacement behavior. This contract adds no automatic source-data adoption or character migration.
- The browser DND-5E import handler retains login, campaign-404, Systems-management-403, and admin checks in that order. Existing repository refresh admission preserves caller transactions; its exact legacy ownership refusal receives a constant plain-text 400 response. After those checks, clean Store ownership is required before library/source validation or any Systems error renderer. A later specific import-ownership refusal also bypasses generic validation rendering. Both return `Cache-Control: private, no-store` without templates, contexts, flash, audit, redirect, refetch, or source-derived details; global security headers remain unchanged. The ownership boundary starts at handler/importer entry, after existing request authentication/bootstrap, rather than changing the shared request lifecycle.
- DND-5E imports selecting items opt into stored spellcasting-choice preservation at the Store replacement boundary. One owned `BEGIN IMMEDIATE` transaction reads existing items, merges choices, and replaces the selected source families. Existing active modifier keys survive by presence, including null, empty, malformed, or conflicting values; inferred modifiers never overwrite or append to them. Existing inert native extensions survive even when fresh source data omits that key: omission cannot clear pending evidence. Inert evidence without an existing active choice suppresses new inference. Newly introducing an inert key on a protected row, or changing its present value, requires reconciliation; fresh unprotected rows may receive inert evidence. Raw active/inert extension forms remain inert; contradictory forms refuse import rather than choosing one. Comparisons retain JSON type distinctions, including boolean versus integer. Matching requires exact library/source/key/type and consistent final slug, title, page, and archive-relative source-path identity; title matching never transfers a choice. Changed page or dataset location on a protected row intentionally requires reconciliation. Ambiguous normalized item identities, unreadable metadata, changed inert evidence, and disappearing protected items refuse before deletion. Precommit replacement failures roll back before separately committing import-failure bookkeeping. An unexpected preexisting transaction is refused without failure-bookkeeping writes that could commit unowned data; the already-started run remains for explicit resolution. Other Store replacement callers, including RULES and Xianxia seeding, retain their default behavior.
- The app-admin JSON ingest uses the same archive and importer boundaries and returns serialized import results plus refetched import runs. After all requested sources succeed, it synchronously writes one `systems_dnd5e_source_imported` event for the real actor with no campaign attribution. Metadata records canonical DND-5E library identity, result-derived ordered source and import-run IDs, effective first-seen entry types or `["all"]`, the trimmed archive filename, and API source identity. Validation, archive/import, or later-source failure writes no success event. Audit failure can occur after completed runs and replacements are durable; run-refetch or response-serialization failure can occur after the audit is durable.
- Browser uploads share the bounded request and safe-ZIP ingestion contracts: a 96 MiB request envelope, 1 MiB per text field, 200 multipart parts, and a 64 MiB raw archive limit, followed by member-count, per-member, total-expanded-size, compression-ratio, path-length, duplicate/conflict, encryption, compression, and cross-platform path-safety checks. The importer remains mechanics-only and stores shared-library rows and import-run history in SQLite; it does not retain the uploaded archive or sync imported rows to Fly.
- Campaign DMs manage shared-library behavior through source policy and entry overrides.
- Source-policy validation failures rerender the current control-panel or DM Content context with status 400 rather than retaining submitted invalid field state. Successful no-change submissions redirect without source-update audit events. Selected browser and API source-policy saves commit the policy, changed-source batch, and required per-source auth audit events in one transaction; absent saved-source readback or audit failure rolls back that business operation.
- Entry-override validation failures likewise rerender current context with status 400 and do not retain invalid submitted fields. Selected browser and API override saves remain last-writer-wins, but commit the policy, override, and required auth audit together. Repeated saves remain accepted and audited; audit failure rolls back the selected operation.
- The shared/core permission POST is app-admin-only and deliberately independent of effective Systems-scope admission. It can be submitted from DM Content -> Systems or the Systems control panel and returns to the originating surface at `#systems-shared-core-permission`. A validation error rerenders that surface with status 400 from persisted context rather than retaining the submitted checkbox state.
- App admins bypass Systems scope and the campaign opt-in when opening or saving the separate shared/core editor. A campaign DM needs effective Systems-scope access plus the app-admin-managed `allow_dm_shared_core_entry_edits` opt-in. Shared editor validation keeps submitted fields on its status-400 form, successful updates redirect to the entry detail management anchor, and shared-library/source/key/type/slug identity remains fixed.
- Shared-entry saves preserve the mechanics-impact acknowledgement requirement, JSON-object validation, rich-HTML sanitization, and existing field limits. The selected shared-entry business write, `systems_shared_entry_edit_events` provenance write, and required auth audit commit together; failed readback, history, or audit rolls back the operation. A successful no-change submission still writes an edit event and auth audit with an empty changed-field list.
- Administrative atomic shared-entry batches use `systems_mutations.save_shared_core_entries` and the same audited single-entry primitive. The batch requires committed campaign settings, an active app admin/library, an expected opaque Systems revision and complete raw stored preimages for 1–100 distinct existing entries. Under one `BEGIN IMMEDIATE`, it rechecks admin/configuration/revision, all preimages and effective source/entry enablement before writing any entry. All entries and both audit streams commit together. Existing browser saves retain their authorization and single-entry behavior. Catalog preparation still precedes business ownership. The returned receipt records known commit and the transaction's final revision; cache-clear errors are reported separately, and callers qualify current values after saving rather than including qualification assertions in the transaction.
- `python -m player_wiki.systems_batch --request <json> --outcome <new-json> --database <existing-db> --campaigns <existing-root>` exposes that operation to an authorized local operator using the configured environment. Both explicit data paths must match configuration before construction and the actual app afterward. A bounded 4 MiB request contains exactly `campaign_slug`, `actor_user_id`, `expected_revision`, `updates` and `mechanics_impact_acknowledged: true`; each update contains `expected` (the complete stored row) and `values` (all nine normal editor fields). The command reserves a new outcome file outside the data roots before its single invocation and never retries. Known commit is printed and atomically recorded before separate qualification; reporting/cleanup failures preserve known commit when available, while an exception without a receipt is explicitly indeterminate until readback. A zero exit alone does not replace durable outcome and preservation checks. This adds no HTTP endpoint, session, Character migration or deployment.
- `player_wiki/systems_mutations.py` owns these selected saves plus the browser shared/core permission save. Permission policy and required auth audit also commit together. Catalog/seed preparation completes before business ownership starts; it is not included in the selected business transaction. The owner starts `BEGIN IMMEDIATE` on the shared connection and joins service/store and audit writes with `commit=False`; join mode requires the matching prepared context and active caller transaction, and never commits or rolls back caller work. Request caches clear after successful owned commit. Redirects, serialization, and response-payload construction follow commit and can still fail after durability. This shared/core contract does not generalize to other custom-entry paths, shared-source imports or campaign item-mechanics imports. Their partial outcomes above remain supported; the finite registered-feature writer has its own explicit contract below.
- Shared/core mechanics-impact warnings recognize structured `mechanic_effects` metadata alongside legacy `modeled_effects`, spell support, spell managers, resource hooks, and derived-stat hooks.

- The existing manager JSON custom-entry create endpoint accepts the finite
  create-only `registered_feature_grant` value
  `divine_avatar_forms@1/avatar_of_mourning@1` for a feature. Its request must
  supply only the supported text/identity fields; it has no general metadata
  editor or Character adoption effect. This selected path requires a genuine
  authenticated, non-View-As manager request and rechecks account/auth version,
  role, campaign/Systems visibility and admitted configuration under its owned
  write snapshot. The exact configured active library, matching campaign policy
  and existing active/enabled owned custom source must already exist. It does
  not seed, enable, publish or repair them. The entry key and slug must both be
  absent or identify the exact approved record; conflicts refuse. One transaction
  owns the feature entry, explicit DM override, bounded required audit and
  readbacks. The selected response contains only the saved entry identity and
  create/reuse result; it skips the ordinary management payload and outer audit,
  which can otherwise seed or commit separately. A response/cache failure after
  commit can still follow durability and is not permission to retry.
- Ordinary custom-feature body edits retain the same locked entry's server
  metadata and non-editor body fields without normalizing or upgrading mechanic
  aliases, invalid/future versions or unknown fields. A structured feature cannot
  be moved to another type by a prose edit. Entry and override updates share an
  owned transaction; omitted visibility preserves existing flags and override
  presence/value, and entry enablement is retained. Ordinary custom-edit auth
  audits and response construction remain outside that transaction, so their
  existing partial-outcome contract is unchanged. Item/non-feature saves retain
  their established behavior. A raw client metadata map cannot replace feature
  mechanics, and the registered grant is not mutable through the body-edit API.
  Unstructured feature conversions to another entry type retain their existing
  preparation path outside the feature write owner, including legacy item-page
  refresh; the refresh transaction guard is not relaxed.

## Durable Systems Revision And Custody

- The integrated registry/init target is schema 14, `0014_systems_revision`.
  `systems_revision` holds one opaque 64-character token, not a timestamp,
  row count, aggregate maximum, or ordered counter. Twenty-one trusted
  INSERT/UPDATE/DELETE triggers cover seven tables: `systems_libraries`,
  `systems_sources`, `systems_entries`, `systems_entry_links`,
  `campaign_system_policies`, `campaign_enabled_sources`, and
  `campaign_entry_overrides`. Covered writes, including raw/store writes,
  replace the token inside their transaction. Rollback restores the prior
  identity; another process sees committed identity through SQLite.
- `SystemsStore` reads the token uncached; character-read library eligibility
  and revision are captured in one SQLite snapshot. Request and process caches
  bind durable identity and campaign policy context, recheck across reuse/build
  publication, and decline reuse when identity is unavailable. Character
  foundations also bind service identity and campaign-page evidence. Prepared
  Combat detail values additionally bind active request lifetime, connection
  identity/changes, Repository and page-store identity, and cache generation;
  refresh or identity drift invalidates the captured values rather than
  relabelling them with a new revision. These are identity contracts, not
  constant-work or latency guarantees.
- On an installation with committed source authority, the Systems policy-only
  readers for cache context, campaign library and configured source defaults
  read validated committed campaign settings directly. Policy values and the
  config revision/hash come from the same settings receipt; these lookups do
  not hydrate the page repository. Missing or invalid committed config yields
  the existing absent-policy result, while activation failures still propagate.
  Durable Systems revision barriers, source/access rules and CharacterRead
  subset invalidation remain in force. Actual page/body and mirror reads keep
  their separate repository validation; a policy read does not validate pages.
- Verified-v2 backup/restore preserves the database revision with its data;
  restored identity describes that restored snapshot, not continued counter
  ordering. Campaign cutover treats the revision table as sealed preservation
  for runtime custody only. Its schema inspector requires the complete exact
  21-trigger set derived from trusted application SQL and rejects missing,
  altered, or extra triggers; it does not admit arbitrary executable schema
  from an export source. Preserve revision-table/trigger custody when handling
  database exports or Systems sync. See [Ops](ops-deploy.md#backup-migration-and-recovery-contract).
- Schema 14 is integrated application behavior. It does not establish a
  deployment, hosted migration, live sync, or executed restore/export.

## Campaign Item Mechanics Contract

- Campaign-owned Systems `item` entries are the mechanics source of truth for homebrew items. Published `Items` pages remain player-facing prose and provenance; article creation alone does not enable mechanics.
- Item records can be imported/refreshed from a published item page with `manage.py import-campaign-item-mechanics <campaign_slug> [page_refs...]` or the JSON API `POST /api/v1/campaigns/{campaign_slug}/systems/item-mechanics/import`.
- `systems_api_routes.py` owns that JSON route's transport and preserves the supported bare `api.systems_item_mechanics_import` endpoint with one POST rule, implicit `OPTIONS`, and no `HEAD`. The route remains DM/admin-only through the existing Systems-management boundary: non-admin managers require effective Systems-scope access, while direct app admins retain their established bypass. View As and session-CSRF denial still happen before controller execution, bearer-token requests still bypass session CSRF, and the existing JSON error envelopes remain unchanged.
- The item-mechanics controller accepts a published item `page_ref`, optional visibility and review-status fields, and optional object-valued manual mechanics. `SystemsService` retains published-item validation and orchestration, `SystemsStore` retains the resulting campaign-owned SQLite rows, and `AuthStore` retains the post-write audit. Service writes remain durable before audit, entry serialization, and refreshed DM Content Systems-payload construction, so failures in those later steps can still follow a durable import; this transport move adds no compensation or atomicity behavior.
- Custom item entries store `campaign_item_mechanics` review payloads plus top-level character-facing item metadata such as `base_item`, weapon damage/range/properties, armor/shield AC fields, `bonus_weapon`, `bonus_ac`, `attunement`, `rarity`, `spell_support`, resource modifiers, defensive rules, attack reminder rules, and `item_use_actions`.
- Item refreshes with omitted or null mechanics retain prior explicitly curated fields and their review status while refreshing inferred body/page fields. An explicit object replaces the prior curated ledger; `{}` clears that ledger, while named empty fields also clear that field's current body/page contribution. Explicit replacements do not inherit approval unless requested. Approved `weapon_extra_damage` accepts a bounded list of unconditional dice/damage-type pairs; it does not resolve conditional riders or apply damage to targets.
- Campaign Mechanics pages can expose structured `character_option.mechanic_effects`; the app preserves those rows and projects legacy effect keys for current DND-5E builder compatibility.
- Campaign Mechanics pages can define scaled `character_option.resource` grants such as `scaling.mode: half_level`; normalization mirrors those grants into `resource_template` mechanic effects, and DND-5E builders derive trackers from that structured metadata rather than prose.
- Review statuses are `draft`, `approved`, `reference_only`, and `manual_review`. Support states are `modeled`, `reference_only`, `unsupported`, `needs_implementation`, and `manual_review`.
- The interpreter handles the first safe DND-style slice: item classification, rarity, attunement, PHB weapon/armor profile mapping, `+X` weapon/armor bonuses, simple spell grants, explicit structured item-use actions, field provenance, and unsupported-mechanic flags.
- Approved campaign item mechanics can feed character-facing automation through the same metadata paths as shared DND item rows. `draft`, `manual_review`, and `reference_only` campaign item rows remain visible/reviewable but do not silently drive character automation.
- The first local Linden Pass migration pass created/refreshed structured records for Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Supported Linden Pass item spell grants, defensive rules, Hourglass Pendant, Psionic Circlet, Innovator's Bolt base weapon mechanics, and Innovator's Bolt enchanted bullet slot expenditure are covered by approved structured metadata only. The approved Innovator's Bolt `innovators-bolt-enchanted-bullet` action uses the real published Incendiary, Booming, and Smoke bullet list, spends one lane spellcasting slot at levels 1-5, and displays damage/save/rider summaries as table-managed. Records can still carry `needs_implementation` or reference fields where bespoke effects exceed the modeled slice, including area damage application, condition riders, charges, healing auras, and live initiative rewrites.

The finite `item_capabilities` v1 metadata contract is retained and validated through ordinary item body edits and approved source assembly. It binds a physical-item Uses counter and one exact casting publication/source row to fixed source capacity/recovery; source-owned attuned ward and extra Hit Die recovery clauses are separate from generic equipped bonuses. Invalid or conflicting capability/spell declarations withhold the complete affected contract. Daily/dawn item recovery uses the established campaign long-rest convention; original source wording remains provenance and recharge amounts are not inferred from unrelated nearby paragraphs. Equivalent same-source/spell/level grants collapse; real conflicts still refuse. A source edit or source link never initializes remaining uses. Character current-state documentation owns admission, mutation and rest behavior. Target/roll/condition adjudication remains table managed; metadata retention alone is not proof of operational adoption.

## Mechanics-Impact Inspection And Browser

- Integrated 10A Candidate 0 added `player_wiki/mechanics_impact.py` as an
  extension-only, read-only inspection kernel, composed by `app.py` at
  `app.extensions["mechanics_impact_kernel"]`. Exact 10A commit
  `2ae1d0b4e6f866c727266cfe43b78c6f3cfedec1`, tree
  `d67e138f669dfc7d14215f39023ed85b5dab80f3`, remains in protected-main
  ancestry. It added no browser or API route, template, UI, schema, migration,
  cache, or generic rules interpreter.
- Integrated 10B adds private server-rendered GETs at
  `/campaigns/<campaign_slug>/systems/mechanics-impact` and
  `/campaigns/<campaign_slug>/systems/mechanics-impact/review` over that kernel.
  `systems_routes.py` owns transport, `mechanics_impact.py` owns bounded
  inspection and existing-interpreter orchestration, and
  `mechanics_impact_presenter.py` owns strict query parsing, signed browser
  state, allowlisted view models, destinations, and sanitized state/error copy.
  `systems_mechanics_impact_queue.html` and
  `systems_mechanics_impact_detail.html` own the two documents; shared
  `styles.css` owns their presentation. Accepted implementation commit
  `46b30ec6abfa08706764387e787f19bcae6e31b9`, verified tree
  `a002fd0ac82387fe2a4a75b52ac2487453b6c671`, is integrated on `main` and
  `origin/main` at `a6286f3885c478f825bb7130b109e73ab4fa9546`.
- Review status and support state remain separate canonical vocabularies.
  Review is exactly `draft`, `approved`, `reference_only`, or `manual_review`;
  support is exactly `modeled`, `reference_only`, `unsupported`,
  `needs_implementation`, or `manual_review`. Reads trim, lowercase, and replace
  hyphens with underscores only. Review precedence is
  `campaign_item_mechanics_review_status` then `review_status`; support
  precedence is `campaign_item_mechanics_support_state`, `support_state`, then
  `xianxia_support_state`. Unknown non-empty states fail closed with sanitized
  invalid-metadata behavior rather than creating a new state or inferring from
  prose, titles, or nested records.
- The queue includes only top-level Systems entries whose review is `draft`,
  `manual_review`, or `reference_only`, or whose support is `manual_review`,
  `reference_only`, `unsupported`, or `needs_implementation`. It orders
  `needs_implementation`, `unsupported`, `manual_review`, `draft`, then
  `reference_only`, followed by binary source ID and entry key order. Queue
  identity is the three-part `(library_slug, source_id, entry_key)` tuple;
  `library_slug:entry_key` remains the canonical comparison key, with
  `source_id` retained for exact disambiguation.
- Admission requires the effective actor's `can_manage_campaign_systems` result;
  View As does not retain a real-admin bypass. Queue visibility applies source
  policy, entry overrides, enabled state, campaign access, and wrong-system
  refusal in one cache-free batched exact-reference resolution. Loading the
  queue performs no owner inventory, Character-definition read, normalization,
  or derivation.
- Queue continuation is signed, limited to 4,096 bytes and 900 seconds, and
  bound to campaign, library, and a metadata snapshot. One page performs one
  snapshot query, one metadata-only seek query that fetches at most 51 rows for
  a 50-row result plus continuation sentinel, and one exact policy/override
  resolution for at most 50 targets. Queue and affected-consumer results each
  return at most 50 rows and reject a serialized payload above 65,536 bytes.
- Selected-row inspection resolves only the exact three-part identity and
  rechecks effective visibility before an owner adapter or interpreter runs.
  Each request invokes at most one bounded page from one separately authorized
  owner lane: Character/equipment, campaign Mechanics/DM Content, Combat, or
  presets. An unavailable owner returns no rows and leaks no hidden count.
  Returned consumer rows contain only owner ID, safe surface, stable consumer
  key, and a campaign-confined canonical destination; they omit bodies, state,
  names, raw metadata/JSON/HTML, internal paths, audits, private identifiers,
  and unfinished totals. Continuations are required before `complete` is true.
  Character inventory retains Source Health's ceiling of 50 definition files
  and 8,388,608 aggregate bytes. Queue, consumer, and preview serialization all
  declare a private, `no-store` payload policy.
- A selected detail performs one exact three-part row lookup and one cache-free
  policy/override resolution before the single bounded owner page. A consumer
  continuation is signed and bound to campaign, library, owner, canonical
  identity, source ID, row `updated_at`, and the current matched-page digest;
  drift or expiry fails closed as stale.
- Preview binds the exact row to expected `updated_at` and a digest of its
  current interpretation inputs; either drift returns `stale_review`. Current
  and proposed records are used only in memory, identity and entry type cannot
  change, and the proposal must already be a normalized `SystemsEntryRecord`
  from the canonical Systems editor boundary. Item preview reuses
  `campaign_item_character_metadata` for activation and reports modeled fields
  plus sanitized review flags. When explicitly asked for one separately
  authorized Character, it loads only that Character, requires the exact
  `(entry_key, source_id)` item reference, and runs the existing Character
  projection twice through a request-local overlay.
- Monster preview reuses `SystemsService.build_monster_combat_seed` and the
  existing NPC-resource seed interpreter. It is labeled as a future-seed
  projection: existing presets and active combatants remain unchanged. Every
  other entry type returns `preview_not_supported` with a reference-only,
  no-modeled-activation disclosure and its authorized Systems destination.
- The kernel cannot approve or mutate statuses, support, entries, source
  policy, overrides, Characters, combatants, presets, accepted Character-update
  plans, audits, journals, caches, or files. It performs no retroactive repair,
  publication, import, source activation, historical scan, title match, or
  live operation.
- Both browser reads admit the effective actor before parsing review state or
  reading inventory; View As retains no real-admin bypass. The four owner lanes
  (Characters/equipment, published Mechanics, Combat, and presets) are exposed
  only when their independent owner capability is authorized. A selected owner
  invokes at most one bounded page, and a selected Character preview separately
  reauthorizes that exact Character.
- Selected-detail editor handoffs follow one canonical matrix. A custom-source
  row links to the custom-entry editor with `return_to=dm-content-systems` and
  `#systems-custom-entry-editor`. A shared-source row links to the shared/core
  editor only when the effective actor has the separate shared-edit capability:
  either a direct app admin, or an effective campaign DM with Systems access and
  the app-admin-managed `allow_dm_shared_core_entry_edits` opt-in. Independently,
  a shared-source row links to the campaign override in DM Content -> Systems at
  `#systems-entry-overrides` when the effective actor can manage DM Content.
  Invalid effective metadata suppresses every editor action. The permission
  toggle itself remains app-admin-only.
- Queue continuation, selected-row identity, queue return, owner continuation,
  and Character preview are signed, purpose-bound, campaign/library-bound, and
  expire after 900 seconds. Selection and preview also bind the metadata
  snapshot, exact source/entry identity, `updated_at`, and interpretation digest
  where applicable. Strict query grammar caps the complete request target at
  4,096 bytes and each browser token at 3,840 bytes. Malformed or tampered query
  state renders the bounded generic 400 recovery document; stale or expired
  state renders the bounded generic 409 recovery document; unavailable selected
  rows remain hidden by 404; and internal failures render the bounded generic
  500 recovery document. None exposes raw metadata, JSON/HTML, private
  identifiers, internal paths, digests, or canary values.
- Invalid effective metadata on an otherwise valid selected row is distinct
  from those recovery documents: detail remains a bounded 200 response whose
  review and support values are both the fixed label `Invalid Metadata`. It
  renders only the allowlisted row identity/presentation fields, never raw,
  humanized, fallback, or dormant status values, and it performs no owner-page,
  approval-proposal, preview-interpreter, or editor-action work.
- Preview is deterministic and approve-only: it derives an in-memory proposal
  from the current normalized row and compares it through existing item,
  Character, monster-combat-seed, and NPC-resource interpreters. It never saves
  that proposal. Non-item/non-monster types remain explicitly unsupported and
  reference-only; monster output describes future seed behavior, not changes to
  existing presets or combatants.
- Browser queue/owner results remain capped at 50 rows; Character inventory
  retains the 50-definition/8,388,608-byte Source Health ceiling. Kernel payloads
  cap at 65,536 bytes, HTML success responses at 131,072 bytes, and HTML error
  responses at 65,536 bytes. Warmed ceilings are 8 database queries for queue,
  12 for owner detail, and 24 for selected-Character preview, with zero writes,
  commits, or rollbacks; frozen p95 ceilings are respectively 100 ms, 150 ms,
  and 500 ms over the checked local profile.
- The browser pages are private `Cache-Control: private, no-store` and
  `Referrer-Policy: no-referrer` documents. They add no page JavaScript, form,
  mutation, API, schema, migration, cache, background task, retroactive update,
  or startup-recovery work; ordinary Player Wiki and Character recovery hooks
  deliberately skip these requests.
- At integrated main, the generated manifest contains 319 Flask rules (318
  non-static) and 329 method/path contracts: 192 browser, 136 API, and one
  framework contract. Systems owns 35 rules/contracts. The exact 10B delta from
  its parent is two browser GET rules/contracts, taking the manifest from
  317/327 and Systems from 33/33 to 35/35; API accounting is unchanged.

## DND-5E Import Contract

- The importer strips images, tokens, sound clips, and other media-oriented fields.
- Current importer coverage includes actions, backgrounds, classes, class features, conditions, diseases, feats, items, monsters, optional features, races, senses, skills, spells, statuses, subclasses, subclass features, variant rules, and shipped `book` slices for supported sources.
- Background import resolves bounded exact-parent `_copy` inheritance with child overrides and supported array modifications. Missing parents, cycles and unsupported modifications fail explicitly. A changed child Equipment rules declaration without a structured child equipment override withholds contradictory inherited grants and displays a diagnostic; it does not invent an equipment package from prose.
- Unsupported alias-style class/subclass variants such as `XPHB` and `EFA` are filtered during import. The approved classic +1/+2/+3 ammunition catalogue has 36 choices across twelve single and bundle bases, including Modern and Renaissance firearm bullets. Exact catalog entries supply source, unit, base item, and numeric bonus metadata; catalog refresh into a target database is a separate operation.
- Race imports synthesize supported subraces into first-class Systems race entries.
- Built-in `RULES` content ships from managed seed data with stable rule keys/facets/provenance and reseeds stale rows when payload versions change.

## Xianxia Systems Contract

- Xianxia uses a built-in shared Systems library identity and `XIANXIA-HOMEBREW` source.
- Curated managed seed data in `player_wiki/data/xianxia_systems_seed.json` owns the first Xianxia source rows for core rules, Martial Arts, Generic Techniques, and Basic Actions.
- Seeded Xianxia rule rows can expose structured `xianxia_rule_facets` for character-facing reminders. Current facets include Skills `guardrails`, Stance `break_reference`, Stance/Aura `active_state_reminders`, and generic `quick_reference` lines for linked rule-text cards.
- Xianxia seeded entries are currently reference-heavy; Basic Action/status automation and combat automation remain deferred.

## Current Tests Or Verification

- Systems changes usually need focused source policy tests, importer tests, route/API tests, or seed validation depending on the touched lane.
- Campaign item mechanics coverage includes API import/review serialization, structured `item_use_actions` preservation, approved-vs-draft character automation gating, and Flask Systems lane source checks.
- Exact local Candidate 0 tree
  `84f709edbf9ac6d8c74ee5302c0a1f2b29cfd91c` was independently accepted with
  Mechanics Impact `17 passed`, affected Source Health `6 passed, 1 expected
  skip`, verifier stress `1 passed`, Linux `6,631 passed, 3 skipped, 55
  deselected`, and Windows-host `55 passed, 429 deselected`. The stress evidence
  confirmed one snapshot query, one 51-row seek, one 50-target policy/override
  resolution, zero database writes, and zero owner reads during queue load.
  Its commit and protected-main integration are complete.
- The accepted and integrated 10B browser candidate passed 848 focused tests
  with one expected skip, all 23 Chromium checks, 6,668 Linux tests, and all 55
  Windows-owned tests. The focused evidence covers effective-actor admission,
  independently gated owner lanes, signed stale-state handling, sanitization,
  deterministic preview, response/query/write bounds, native desktop/mobile
  behavior, and no-JavaScript rendering. No deployment, live verification,
  live/private-data access, database/content sync, or external side effect is
  claimed for either 10A or 10B.
- The 2026-06-25 local DND-5E duplicate audit is recorded in `.local/systems-duplicate-audit/summary.md`; it found no confirmed true importer or normalization duplicate requiring cleanup.
- If local Systems DB changes matter on Fly, a code deploy is not enough; sync the volume-backed SQLite data separately.

## Known Limits

- Bespoke item effects such as extra damage riders, area healing, save riders, action-economy timing, charges, and recharge counters are stored as review flags unless a narrow structured hook already exists.
- Fly needs both the code deploy and a volume-backed SQLite sync before live item searches or character sheets can see newly imported local campaign item records.

## Related Backlog

- `.local/roadmaps/systems-backlog.md`
- `.local/roadmaps/xianxia-backlog.md`

## Source Pointers

- `player_wiki/systems_store.py`
- `player_wiki/systems_service.py`
- `player_wiki/mechanics_impact.py`
- `player_wiki/mechanics_impact_presenter.py`
- `player_wiki/systems_routes.py`
- `player_wiki/systems_api_routes.py`
- `player_wiki/api.py`
- `player_wiki/systems_importer.py`
- `player_wiki/systems_ingest.py`
- `player_wiki/systems_labels.py`
- `player_wiki/xianxia_systems_seed.py`

## Structured campaign spell authoring

- DND-5E custom spell create/update accepts a closed `spell_profile` through the existing manager JSON routes and the Custom Entries form. Required fields are `level` (integer 0-9), `school` (A/C/D/E/V/I/N/T), typed `casting_time`, `range`, `components`, `duration`, and `classes.fromClassList` records with explicit names/sources. Optional `ritual`, `savingThrow`, and `spellAttack` must be explicit source declarations. The service derives `class_lists` from those class records. Profiles cannot supply arbitrary metadata, source identity, class grants or character state.
- The bounded authoring vocabulary supports action/bonus/reaction/round/minute/hour casting times, measured or named point/self/special ranges, verbal/somatic/material components, and instantaneous/timed/permanent/special durations. Other geometry stays in the source rules; this is not a general effect interpreter. Material cost uses copper pieces; consumption is optional and never inferred. Roll declarations are not roll automation and do not substitute a caster DC for an externally set check.
- Omitting the profile, submitting JSON null, or leaving the form profile blank preserves current structured mechanics. An explicitly empty or invalid profile is rejected. Ordinary DND-5E spell edits read current server metadata under the same entry/override transaction and retain unknown fields, immutable identity, omitted visibility and archive enablement. A structured spell cannot be converted to another type through prose editing. Ordinary create/source preparation and outer audit ordering retain the existing partial-commit contract; spell edit entry+override are owned together, while its route audit follows separately. Legacy unstructured type conversions prepare any linked item page before ownership and recheck the current spell structure under the write transaction.
- The main Markdown and separate optional At Higher Levels text are sanitized and projected at save time to `body.entries` and `body.entries_higher_level`; the editor copies live in metadata. The rendered body includes each section once, with a summary derived from the supported typed profile rather than a duplicate statblock in the rules text. Omitted higher-level input preserves its current authored value; an explicit empty value clears authored higher-level text. Legacy structured higher-level content without an editor copy requires explicit separation before editing. Unrelated body fields are preserved, and the generic spell-metric interpreter remains conservative when it cannot understand them. No name-based special spell behavior is introduced.
- Custom spell details describe a Systems source. Character acquisition, preparation, casting, resource spending, DM-selected checks and campaign item adoption retain their separate existing permissions and current-authority checks. Saving a spell does not modify a character.

### Structured class and subclass feature proficiencies

The class/subclass feature importer retains `skillProficiencies`, `toolProficiencies`, `armorProficiencies`, `weaponProficiencies`, `languageProficiencies` and `expertise` as their existing snake-case metadata counterparts (with `expertise` unchanged). Shared/core metadata editing validates the same closed contract before its existing transaction. No declaration is inferred from prose, and absent fields remain absent.

Supported grants include fixed names/true entries, bounded `choose.from` domains and supported ordinary skill/tool/language choice families. Artisan choices use the native artisan domain. A conditional tool block has the exact shape `{"ifAlreadyProficient": {"proficiency": "Smith's Tools", "replacement": {"anyArtisansTool": 1}}}`. It owns either the initial named proficiency or a different artisan replacement selected against prior proficiency evidence; it is not an unconditional extra choice. The automatic capability is `expertise: [{"allProficientTools": true}]`. Boolean counts, unknown conditional shapes and malformed present declarations are rejected. Existing named/selected expertise remains supported.

Import or shared/core admission only records a rule. Character creation, advancement and explicit reconstruction must separately prove current source access, attainment, owning class/member and decisions. Unsupported current source shapes withhold dependent Character authority. This support performs no catalog admission or Character migration by itself.

### Source-Owned Simultaneous Capacities

TCE import preserves the original Artificer Infused Items table separately in
`body.feature_capacity_source_tables`, with normalized twenty-level maxima and
provenance in `metadata.feature_capacity_tables`. Registered Magical Tinkering
and Infuse Item publications receive versioned `feature_capacity` declarations
bound to their exact rule bodies, owning class and attainment level. The former
uses qualified Intelligence modifier/minimum one; the latter selects the actual
Infused Items column, never the number of known recipes. Unrecognized or changed
registered source semantics require review rather than inferred conversion.
These declarations provide read-only maximum simultaneous-object values. They do
not register a spendable resource, establish current availability or assign an
infusion. Existing catalog rows need explicit import/admission; a source update
alone does not rewrite those rows or any character.


## Prepared Ammunition And Conditional Item Actions

`item_capabilities` v4 declares one prepared-ammunition load, exact required class
source key, load/discharge activation, one slot paid on reload, and distinct
source-owned developed options. Options contain typed per-slot damage, optional
bearer-save clauses with separate per-effect durations, conditional attack
advantage and current-bearer ability riders. It is not a spell grant or an
original-caster snapshot. Approved source assembly and equipment/authority
projection reject conflicting legacy `item_use_actions`, spell support, physical
use budgets or missing attunement. Existing v1/v2 and v3 attack-d20 contracts stay
separate. No source declaration supplies current state.

The closed v3 tagged action union additionally supports `prevent_forced_movement`
with equipped activation, reaction timing, one counter use, exact triggers,
self/willing-visible targets, source range and target-next-turn speed restriction.
Its optional `conditional_rules` describes natural-wetlands nonmagical movement
and Wisdom (Survival) navigation/getting-lost advantage; it is separate from the
v1 `passive` shape and from reaction availability. Source text and unrelated
metadata remain preserved; actual catalog adoption requires its normal save.
Character current-state documentation owns state custody and operation limits.
