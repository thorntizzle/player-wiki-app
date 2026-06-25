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
- Browser shared-source imports are app-admin-only shared-library maintenance with import-run review.
- Campaign DMs manage shared-library behavior through source policy and entry overrides.
- App admins can edit shared/core entries through the separate shared/core editor, with mechanics-impact acknowledgement for rows that participate in modeled behavior.
- Shared/core saves write durable provenance into `systems_shared_entry_edit_events` and auth audit events.

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
- If local Systems DB changes matter on Fly, a code deploy is not enough; sync the volume-backed SQLite data separately.

## Known Limits

- Custom campaign items are not yet a unified structured Systems item lane.
- Some item/equipment mechanics remain character-side or manual until the structured item backlog ships.

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
