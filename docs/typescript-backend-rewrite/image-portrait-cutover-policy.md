# TypeScript Image And Portrait Cutover Policy

Last updated: 2026-06-28

Status: decision recommendation recorded; implementation gates open

## Operating Boundary

Flask remains the production authority. This document does not approve a PR,
merge, deploy, live data write, Fly sync, production cutover, or live image data
migration. It records the current TypeScript behavior, the Flask/product
contract it diverges from, and the exact evidence still needed before image and
portrait handling can be called cutover-ready.

This lane intentionally avoids live campaign volumes and vault content. Evidence
must use sanitized fixtures, copied fixture trees, or a user-approved
staging-volume snapshot.

## Sources Reviewed

- `AGENTS.md`
- `docs/current-state/INDEX.md`
- `docs/current-state/workspace-boundaries.md`
- `docs/current-state/characters-overview.md`
- `docs/current-state/characters-dnd5e.md`
- `docs/current-state/published-wiki.md`
- `docs/api-v1.md` portrait, content asset, wiki image, and session image
  sections
- `docs/typescript-backend-rewrite/README.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- `$campaign-player-wiki-characters` references:
  `character-reference-map.md`, `character-workflow-read-session.md`,
  `character-workflow-state-editing.md`,
  `character-workflow-core-storage.md`, and
  `character-system-reimport-ux.md`
- `$campaign-player-wiki-publishing` references:
  `publishing-reference-map.md`, `publishing-page-frontmatter.md`,
  `publishing-live-content-api.md`, and `publishing-page-structure.md`

The ignored local roadmap
`.local/roadmaps/typescript-backend-rewrite-roadmap.md` was absent in this
worktree, likely because no `.worktreeinclude` copied it into this lane.

## Current Product Contract

Character portrait uploads are one portrait slot per character, editable by app
admins, campaign DMs, and assigned players through the portrait/session-state
permission boundary. The current Flask and current-state contract stores PNG/JPG
portrait uploads as WebP via the shared image-publishing helper, while GIF/WebP
uploads pass through validation. Portrait assets are campaign-owned protected
assets and are rendered from character profile metadata.

Published wiki article images are campaign-owned protected assets. Publishing
guidance treats local PNG/JPG files as source inputs and stores the app-owned
published copy as WebP quality 82 unless preserving the original format is
explicitly required. Page frontmatter should point at that app-owned asset copy.
The Flask Player Wiki editor performs automatic PNG/JPG-to-WebP conversion for
page images; the Gen2 content asset API currently preserves the uploaded file
extension and bytes, so a publication pass that requires WebP must preconvert the
asset or use the Flask editor.

## Current TypeScript Behavior

TypeScript deliberately does not add `sharp` or perform image conversion in the
current slice.

Character portrait uploads:

- validate only PNG, JPG/JPEG, GIF, and WEBP extensions
- store the uploaded bytes unchanged
- write `characters/<characterSlug>/portrait.<ext>` based on the uploaded
  filename extension
- write `profile.portrait_asset_ref`, `portrait_alt`, and `portrait_caption`
  into `definition.yaml`
- preserve/import metadata through `import.yaml`
- bump the shared `character_state` revision
- remove the prior portrait asset when a replacement uses a different extension
- remove profile portrait fields and the current asset on delete
- expose the resulting media type from the stored asset extension
- existing profile references resolve through the character detail payload when
  the referenced asset is present in the copied fixture asset tree, including
  pre-existing WebP assets; that payload still advertises the legacy
  `/campaigns/:campaignSlug/characters/:characterSlug/portrait` URL, while the
  focused protected-serving proof uses `/campaigns/:campaignSlug/assets/:assetRef`
  and does not by itself settle the direct legacy portrait URL cutover behavior
- the portrait write/delete response helper returns protected asset URLs of the
  form `/campaigns/:campaignSlug/assets/:assetRef`, so the rewrite currently has
  two portrait URL shapes in play: legacy character portrait URLs on detail/read
  payloads and protected asset URLs on write-result payloads

Published content asset writes:

- accept embedded `asset_file` payloads through
  `PUT /api/v1/campaigns/:campaignSlug/content/assets/*`
- decode and write bytes unchanged at the URL asset ref
- infer media type from the written asset path extension
- serve protected campaign assets at `/campaigns/:campaignSlug/assets/*` with
  the inferred content type and exact stored bytes
- do not rewrite page frontmatter or convert PNG/JPG to WebP by themselves

## Focused Evidence

Added focused proof:

```powershell
cd apps/api
npm run build
node ./tests/image-portrait-policy.mjs
```

The test uses only copied sanitized fixtures and a disposable SQLite database. It
proves:

- An existing copied-fixture WebP portrait profile reference resolves in the
  character detail payload as `image/webp`, and the protected asset route serves
  the exact stored WebP bytes.
- PNG portrait upload stores `portrait.png`, reports `image/png`, writes exact
  PNG bytes, serves the protected asset with exact bytes, and removes the prior
  WebP portrait asset.
- JPG replacement stores `portrait.jpg`, reports `image/jpeg`, writes exact JPG
  bytes, serves the protected asset with exact bytes, and removes the old PNG
  portrait asset.
- GIF replacement stores `portrait.gif`, reports `image/gif`, writes exact GIF
  bytes, serves the protected asset with exact bytes, and removes the old JPG
  portrait asset.
- WEBP replacement stores `portrait.webp`, reports `image/webp`, writes exact
  WEBP bytes, serves the protected asset with exact bytes, and removes the old
  GIF portrait asset.
- Each portrait upload preserves copied-fixture `import.yaml` metadata, writes
  profile portrait fields in `definition.yaml`, bumps the shared
  `character_state` revision, and records the acting user id.
- Portrait delete removes the current WEBP asset, removes profile portrait
  metadata, preserves copied-fixture `import.yaml` metadata, and bumps the
  shared `character_state` revision.
- Content asset API upload of a PNG preserves the `.png` ref, `image/png` media
  type, exact bytes, and protected serving behavior, then deletes the copied
  asset.

Existing broader evidence remains in `apps/api/tests/smoke.mjs` and
`docs/typescript-backend-rewrite/read-only-compatibility-slice.md`, including
content asset list/detail/delete checks and prior portrait PNG preservation and
delete checks.

## Cutover Decision

Decision recommendation for orchestration: choose a split cutover path.

1. Preserve Flask's WebP-normalized contract for user-facing portrait uploads
   and browser/editor publication flows. Before TypeScript replaces Flask for
   `PUT /api/v1/campaigns/:campaignSlug/characters/:characterSlug/portrait`,
   PNG/JPG portrait uploads should be converted to app-owned
   `characters/<characterSlug>/portrait.webp` assets, GIF/WebP should pass
   through validation, profile metadata should point at the final stored asset,
   and old portrait assets should still be cleaned up. Browser/editor
   publication paths that create or promote published page images should keep
   producing WebP quality 82 page assets and frontmatter by default.
2. Explicitly allow extension-preserving behavior for the low-level content
   asset API and protected asset serving. `PUT
   /api/v1/campaigns/:campaignSlug/content/assets/*` should remain a raw
   asset-file write unless a later API-version decision says otherwise; callers
   that need a published WebP image should preconvert the file or use the Flask
   Player Wiki editor until a TypeScript publication/editor flow owns that
   conversion step.
3. Keep the direct legacy character portrait URL as a read-compatibility
   requirement through cutover. `/campaigns/:campaignSlug/characters/:characterSlug/portrait`
   should resolve the current `profile.portrait_asset_ref` with the same
   character-scope authorization and media type behavior as Flask. The protected
   `/campaigns/:campaignSlug/assets/:assetRef` URL can remain available, but
   payloads should not switch URL shape silently without a client/versioning
   decision.

Why: current current-state docs, character references, publishing guidance, API
docs, and Flask tests all teach users that portrait/page-image publication
normalizes PNG/JPG sources into app-owned WebP copies. At the same time, the
Gen2 content asset API is already documented and implemented as an
extension-preserving low-level asset writer. The split path preserves the
user-facing product contract while avoiding unnecessary conversion behavior in
generic asset storage.

## Remaining Gate

This gate is not cutover-ready.

Required proof before readiness:

- User or orchestrator acceptance of the split path above, or a replacement
  decision that intentionally changes the current product contract.
- TypeScript portrait conversion implementation for the character portrait API:
  PNG/JPG become WebP quality 82, GIF/WebP pass through validation, old mixed
  extension assets are cleaned up, `definition.yaml` / `import.yaml` /
  `character_state` revision behavior remains unchanged, and the implementation
  does not touch unrelated character authoring lanes.
- Focused TypeScript portrait tests covering PNG/JPG-to-WebP conversion,
  GIF/WebP pass-through, media types, exact old-asset cleanup, stale revision
  behavior, absent portrait delete validation, existing WebP profile reads, and
  direct `/campaigns/:campaignSlug/characters/:characterSlug/portrait`
  resolution.
- Focused TypeScript content asset tests preserving the low-level raw-asset
  contract for `PUT /content/assets/*`, including PNG/JPG/GIF/WEBP media types
  and proof that this route does not perform portrait/page publication
  conversion by accident.
- Publication/editor implementation decision: either keep automatic WebP
  conversion in Flask-only browser/editor flows until cutover, or add a
  TypeScript publication/editor conversion slice with tests proving page
  frontmatter points at WebP quality 82 assets for PNG/JPG sources while the raw
  content asset API remains extension-preserving.
- Migration rehearsal for existing character portrait assets, including
  pre-cutover WebP assets, legacy PNG/JPG assets if present, profile references,
  protected serving, and old asset cleanup.
- Published page image rehearsal for page frontmatter, asset copies, protected
  serving, and local/live mirror sync behavior on copied or staging data.
- Backup/restore transcript on copied realistic data, then a user-approved
  staging-volume snapshot before any staging/live write enablement.

Until that proof exists, label this area `fixture behavior proven; split image
cutover path recommended, implementation gates open`.
