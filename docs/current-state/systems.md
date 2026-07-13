# Systems Wiki

Last updated: 2026-07-13

## Owns

- Shared Systems libraries, source policy, imports, source/category/entry browsing, RULES/book slices, campaign overrides, custom entries, and Systems-linked mechanics used by characters and combat.

## Current User-Facing Behavior

- Systems Wiki uses shared system libraries plus per-campaign source policy instead of duplicating imports per campaign.
- DND-5E source data is imported once into the shared app library and filtered per campaign by source policy.
- Systems landing and source pages expose a metadata-focused Rules Reference Search for `book` and `rule` entries.
- Source pages are lightweight category indexes; source category pages load one entry type at a time.
- Entry detail pages can surface related rules references and campaign overlays.
- Class, subclass, and optional-feature browsing folds features into parent pages while keeping standalone feature entries searchable/direct-linkable.

## Management Contract

- DM Content -> `Systems` is the current browser management lane.
- `player_wiki/systems_routes.py` owns browser transport for the five Systems index/search/source/category/entry reads, the source-policy and entry-override mutations, the five custom-entry create, edit, update, archive, and restore controllers, the app-admin shared/core permission mutation, the shared-entry edit GET and update POST, and the browser DND-5E import POST. Sixteen explicit app-level registrations preserve their bare Flask endpoint identifiers and one-rule-per-method/path compatibility. The custom-entry and shared-entry edit GETs retain implicit `HEAD` and `OPTIONS`, while the extracted POST registrations retain implicit `OPTIONS` without `HEAD`.
- `player_wiki/systems_api_routes.py` owns JSON transport for five Systems read handlers through six explicit registrations on the existing API Blueprint: landing and search share `api.systems_index`, followed by source list, source detail, source category detail, and entry detail under their existing `api.*` identifiers. `api.py` retains the Blueprint, shared serializers, authorization and error boundaries, repository/service composition, the source-policy PUT and all other Systems API mutations/imports. The source-list GET and source-policy PUT remain one rule per method on the same path, whose OPTIONS response advertises GET, HEAD, OPTIONS, and PUT.
- The API source-list read returns every configured source state to a Systems manager. A non-manager receives only enabled source states that the effective actor can access; the top-level and per-source permission fields describe that projection.
- Entry-detail admin behavior intentionally differs between browser and API transport. The browser requires an enabled source even for a direct app admin, then lets that admin inspect a disabled or archived entry within the enabled source. The API lets a direct app admin inspect a stored entry even through a disabled source. `View As` replaces the effective actor on both safe-read surfaces, so the real admin does not retain either entry-level bypass while viewing as another user.
- Transport ownership does not move Systems product, authorization, persistence, context, or presentation ownership: `auth.py` still owns Systems access helpers and shared-editor authority, `SystemsService` still owns policy/source/entry/override orchestration, `SystemsStore` still owns their SQLite persistence and shared-edit/import-run records, and `AuthStore` still owns auth audit persistence. DM Content and the Systems control panel remain the two presentation surfaces; `app.py` retains the four read-context builders, both surface context builders, `build_systems_import_form()`, the custom-entry DOM-ID helper injected into the browser transport module, and the remaining control-panel view; existing templates remain the HTML owners. `Dnd5eSystemsImporter` and the archive-ingest helpers retain import and archive-safety ownership. Controller-local shared-entry form/JSON, provenance, changed-field, resolver, and editor-rendering helpers remain with the three extracted controllers in `systems_routes.py`.
- Custom campaign Systems entries are campaign-owned DM authoring rows stored only through the Systems SQLite service/store path. Create assigns the custom-source-prefixed slug; update keeps the existing slug and entry key rather than accepting a replacement slug. Create and update validation rerender the originating control-panel or DM Content surface with status 400, and successful lifecycle submissions redirect to that surface with the custom-entry anchor. Archive and restore validation redirect to the originating surface's custom-entry section.
- Archive preserves the custom entry and its visibility override while setting its enablement override to disabled. Restore preserves the entry and visibility override while clearing the enablement override back to inheritance.
- Custom-entry persistence is not an atomic unit: custom-source, campaign-policy, enabled-source, entry, and override writes commit independently, and the controller writes the auth audit event only after the service writes return. Invalid create input can therefore leave supporting custom-source policy rows, and later write or audit failures can leave earlier commits durable. These writes retain the existing last-writer-wins behavior.
- DM Content -> `Systems` now includes a `Campaign Item Mechanics` lane that lists published campaign `Items` pages and can import/refresh each one into a campaign-owned Systems `item` row.
- Browser shared-source imports are app-admin-only shared-library maintenance with import-run review. `campaign_systems_control_panel_import_dnd5e` first requires an existing campaign and applies the existing Systems-management check, then requires app-admin authority and a DND-5E Systems library; missing campaigns remain 404, anonymous requests redirect to sign-in, authenticated non-admins remain 403, and unsupported campaign systems rerender the originating surface with status 400. CSRF and View As mutation protections remain in the shared browser boundary.
- The browser import accepts either the Systems control panel or DM Content -> `Systems` as its presentation/return surface. Validation rerenders that surface with status 400 while retaining source, entry-family, import-version, and return-target fields but never the uploaded file; success redirects to the same surface at `#systems-import-history`. The supported bare POST endpoint keeps implicit `OPTIONS` and no `HEAD`.
- Browser source IDs are normalized and deduplicated in first-submitted order, then imported sequentially into the shared library. Each source creates an import run, replaces that source's selected entry families, and marks its run complete through separate commits; a later-source failure can leave earlier source imports and runs durable, and a completion failure can occur after replacement is durable. The controller writes one auth audit only after all sources return, so an audit failure can leave all source replacements and completed runs durable. This path does not change campaign source policy or entry overrides, refresh the campaign repository, or bump Combat revisions.
- Browser uploads share the bounded request and safe-ZIP ingestion contracts: a 96 MiB request envelope, 1 MiB per text field, 200 multipart parts, and a 64 MiB raw archive limit, followed by member-count, per-member, total-expanded-size, compression-ratio, path-length, duplicate/conflict, encryption, compression, and cross-platform path-safety checks. The importer remains mechanics-only and stores shared-library rows and import-run history in SQLite; it does not retain the uploaded archive or sync imported rows to Fly.
- Campaign DMs manage shared-library behavior through source policy and entry overrides.
- Source-policy validation failures rerender the current control-panel or DM Content context with status 400 rather than retaining submitted invalid field state. Successful no-change submissions redirect without source-update audit events. A changed submission commits the policy and each changed source independently before the controller writes per-source auth audit events; a later source or audit failure can therefore leave earlier writes durable.
- Entry-override validation failures likewise rerender current context with status 400 and do not retain invalid submitted fields. Override saves remain last-writer-wins: the policy write and override write commit before the controller writes the auth audit event, repeated saves remain accepted and audited, and an audit failure can occur after the override is durable.
- The shared/core permission POST is app-admin-only and deliberately independent of effective Systems-scope admission. It can be submitted from DM Content -> Systems or the Systems control panel and returns to the originating surface at `#systems-shared-core-permission`. A validation error rerenders that surface with status 400 from persisted context rather than retaining the submitted checkbox state.
- App admins bypass Systems scope and the campaign opt-in when opening or saving the separate shared/core editor. A campaign DM needs effective Systems-scope access plus the app-admin-managed `allow_dm_shared_core_entry_edits` opt-in. Shared editor validation keeps submitted fields on its status-400 form, successful updates redirect to the entry detail management anchor, and shared-library/source/key/type/slug identity remains fixed.
- Shared-entry saves preserve the mechanics-impact acknowledgement requirement, JSON-object validation, rich-HTML sanitization, and existing field limits. The entry write, `systems_shared_entry_edit_events` provenance write, and auth audit write remain three independent commits in that order; a later failure can leave earlier commits durable. A successful no-change submission still writes an edit event and auth audit with an empty changed-field list.
- Shared/core mechanics-impact warnings recognize structured `mechanic_effects` metadata alongside legacy `modeled_effects`, spell support, spell managers, resource hooks, and derived-stat hooks.

## Campaign Item Mechanics Contract

- Campaign-owned Systems `item` entries are the mechanics source of truth for homebrew items. Published `Items` pages remain player-facing prose and provenance; article creation alone does not enable mechanics.
- Item records can be imported/refreshed from a published item page with `manage.py import-campaign-item-mechanics <campaign_slug> [page_refs...]` or the JSON API `POST /api/v1/campaigns/{campaign_slug}/systems/item-mechanics/import`.
- Custom item entries store `campaign_item_mechanics` review payloads plus top-level character-facing item metadata such as `base_item`, weapon damage/range/properties, armor/shield AC fields, `bonus_weapon`, `bonus_ac`, `attunement`, `rarity`, `spell_support`, resource modifiers, defensive rules, attack reminder rules, and `item_use_actions`.
- Campaign Mechanics pages can expose structured `character_option.mechanic_effects`; the app preserves those rows and projects legacy effect keys for current DND-5E builder compatibility.
- Campaign Mechanics pages can define scaled `character_option.resource` grants such as `scaling.mode: half_level`; normalization mirrors those grants into `resource_template` mechanic effects, and DND-5E builders derive trackers from that structured metadata rather than prose.
- Review statuses are `draft`, `approved`, `reference_only`, and `manual_review`. Support states are `modeled`, `reference_only`, `unsupported`, `needs_implementation`, and `manual_review`.
- The interpreter handles the first safe DND-style slice: item classification, rarity, attunement, PHB weapon/armor profile mapping, `+X` weapon/armor bonuses, simple spell grants, explicit structured item-use actions, field provenance, and unsupported-mechanic flags.
- Approved campaign item mechanics can feed character-facing automation through the same metadata paths as shared DND item rows. `draft`, `manual_review`, and `reference_only` campaign item rows remain visible/reviewable but do not silently drive character automation.
- The first local Linden Pass migration pass created/refreshed structured records for Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Supported Linden Pass item spell grants, defensive rules, Hourglass Pendant, Psionic Circlet, Innovator's Bolt base weapon mechanics, and Innovator's Bolt enchanted bullet slot expenditure are covered by approved structured metadata only. The approved Innovator's Bolt `innovators-bolt-enchanted-bullet` action uses the real published Incendiary, Booming, and Smoke bullet list, spends one lane spellcasting slot at levels 1-5, and displays damage/save/rider summaries as table-managed. Records can still carry `needs_implementation` or reference fields where bespoke effects exceed the modeled slice, including area damage application, condition riders, charges, healing auras, and live initiative rewrites.

## DND-5E Import Contract

- The importer strips images, tokens, sound clips, and other media-oriented fields.
- Current importer coverage includes actions, backgrounds, classes, class features, conditions, diseases, feats, items, monsters, optional features, races, senses, skills, spells, statuses, subclasses, subclass features, variant rules, and shipped `book` slices for supported sources.
- Unsupported alias-style class/subclass variants such as `XPHB` and `EFA` are filtered during import.
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
- `player_wiki/systems_routes.py`
- `player_wiki/systems_api_routes.py`
- `player_wiki/api.py`
- `player_wiki/systems_importer.py`
- `player_wiki/systems_ingest.py`
- `player_wiki/systems_labels.py`
- `player_wiki/xianxia_systems_seed.py`
- `tests/test_systems_importer*.py`
- `tests/test_campaign_systems_policy.py`
- `tests/test_api_systems.py`
