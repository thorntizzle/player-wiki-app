# Systems Wiki

Last updated: 2026-06-25

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
- Custom campaign Systems entries are campaign-owned DM authoring rows.
- DM Content -> `Systems` now includes a `Campaign Item Mechanics` lane that lists published campaign `Items` pages and can import/refresh each one into a campaign-owned Systems `item` row.
- Browser shared-source imports are app-admin-only shared-library maintenance with import-run review.
- Campaign DMs manage shared-library behavior through source policy and entry overrides.
- App admins can edit shared/core entries through the separate shared/core editor, with mechanics-impact acknowledgement for rows that participate in modeled behavior.
- Shared/core saves write durable provenance into `systems_shared_entry_edit_events` and auth audit events.

## Campaign Item Mechanics Contract

- Campaign-owned Systems `item` entries are the mechanics source of truth for homebrew items. Published `Items` pages remain player-facing prose and provenance; article creation alone does not enable mechanics.
- Item records can be imported/refreshed from a published item page with `manage.py import-campaign-item-mechanics <campaign_slug> [page_refs...]` or the JSON API `POST /api/v1/campaigns/{campaign_slug}/systems/item-mechanics/import`.
- Custom item entries store `campaign_item_mechanics` review payloads plus top-level character-facing item metadata such as `base_item`, weapon damage/range/properties, armor/shield AC fields, `bonus_weapon`, `bonus_ac`, `attunement`, `rarity`, `spell_support`, resource modifiers, defensive rules, and attack reminder rules.
- Review statuses are `draft`, `approved`, `reference_only`, and `manual_review`. Support states are `modeled`, `reference_only`, `unsupported`, `needs_implementation`, and `manual_review`.
- The interpreter handles the first safe DND-style slice: item classification, rarity, attunement, PHB weapon/armor profile mapping, `+X` weapon/armor bonuses, simple spell grants, known curated Linden Pass item effects, field provenance, and unsupported-mechanic flags.
- Approved campaign item mechanics can feed character-facing automation through the same metadata paths as shared DND item rows. `draft`, `manual_review`, and `reference_only` campaign item rows remain visible/reviewable but do not silently drive character automation.
- The first local Linden Pass migration pass created/refreshed structured records for Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Innovator's Bolt is held at `manual_review`; the other five are `approved` but carry `needs_implementation` flags where bespoke effects exceed the modeled slice.

## DND-5E Import Contract

- The importer strips images, tokens, sound clips, and other media-oriented fields.
- Current importer coverage includes actions, backgrounds, classes, class features, conditions, diseases, feats, items, monsters, optional features, races, senses, skills, spells, statuses, subclasses, subclass features, variant rules, and shipped `book` slices for supported sources.
- Unsupported alias-style class/subclass variants such as `XPHB` and `EFA` are filtered during import.
- Race imports synthesize supported subraces into first-class Systems race entries.
- Built-in `RULES` content ships from managed seed data with stable rule keys/facets/provenance and reseeds stale rows when payload versions change.

## Xianxia Systems Contract

- Xianxia uses a built-in shared Systems library identity and `XIANXIA-HOMEBREW` source.
- Curated managed seed data in `player_wiki/data/xianxia_systems_seed.json` owns the first Xianxia source rows for core rules, Martial Arts, Generic Techniques, and Basic Actions.
- Xianxia seeded entries are currently reference-heavy; Basic Action/status automation and combat automation remain deferred.

## Current Tests Or Verification

- Systems changes usually need focused source policy tests, importer tests, route/API tests, or seed validation depending on the touched lane.
- Campaign item mechanics coverage includes API import/review serialization, approved-vs-draft character automation gating, existing published-item fallback behavior, Gen2 Systems lane source checks, and TypeScript typecheck.
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
- `player_wiki/systems_importer.py`
- `player_wiki/systems_ingest.py`
- `player_wiki/systems_labels.py`
- `player_wiki/xianxia_systems_seed.py`
- `frontend/src/pages/SystemsRoutes.tsx`
- `frontend/src/pages/DmContentSystemsLane.tsx`
- `tests/test_systems_importer.py`
- `tests/test_campaign_systems_policy.py`
