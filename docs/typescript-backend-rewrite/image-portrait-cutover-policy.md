# TypeScript Image And Portrait Cutover Policy

Last updated: 2026-06-28

Status: decision gate open; focused TypeScript behavior proof added

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
- `docs/typescript-backend-rewrite/README.md`
- `docs/typescript-backend-rewrite/cutover-readiness.md`
- `$campaign-player-wiki-characters` references:
  `character-reference-map.md`, `character-workflow-read-session.md`,
  `character-workflow-state-editing.md`, and
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

- PNG portrait upload stores `portrait.png`, reports `image/png`, writes exact
  PNG bytes, and serves the protected asset with exact bytes.
- JPG replacement stores `portrait.jpg`, reports `image/jpeg`, writes exact JPG
  bytes, serves the protected asset with exact bytes, and removes the old PNG
  portrait asset.
- Portrait delete removes the current JPG asset and profile portrait metadata.
- Content asset API upload of a PNG preserves the `.png` ref, `image/png` media
  type, exact bytes, and protected serving behavior, then deletes the copied
  asset.

Existing broader evidence remains in `apps/api/tests/smoke.mjs` and
`docs/typescript-backend-rewrite/read-only-compatibility-slice.md`, including
content asset list/detail/delete checks and prior portrait PNG preservation and
delete checks.

## Cutover Decision

Decision required before cutover: TypeScript image handling must either match the
current Flask WebP conversion contract, or the product contract must explicitly
accept extension-preserving TypeScript behavior for selected routes.

Recommended option: keep the production contract as WebP-normalized for PNG/JPG
portrait and published article images, then add an explicit TypeScript conversion
implementation and migration proof before cutover.

Why: current current-state docs, publishing guidance, and Flask production
behavior all teach users that PNG/JPG portrait and article image publication
produce app-owned WebP copies. Silently accepting TypeScript extension
preservation would make cutover change storage names, media types, and migration
expectations for existing PNG/WebP portrait/page-image assets.

Acceptable alternative: explicitly approve extension-preserving TypeScript
behavior for JSON/API writes, then update current-state docs, publication
guidance, frontend assumptions, and cutover migration instructions to make the
new behavior intentional. This alternative still needs migration evidence for
existing WebP portraits/page images and mixed-extension assets.

## Remaining Gate

This gate is not cutover-ready.

Required proof before readiness:

- User decision choosing WebP-normalized parity or extension-preserving
  TypeScript behavior.
- If WebP-normalized parity is chosen: TypeScript conversion implementation,
  tests proving PNG/JPG become WebP quality 82 for portraits and published page
  images, GIF/WebP pass-through tests, and no accidental conversion of unrelated
  generic assets.
- If extension-preserving behavior is chosen: explicit docs/current-state and
  publishing-reference updates plus tests covering PNG, JPG/JPEG, GIF, and WEBP
  media types for the accepted route families.
- Migration rehearsal for existing character portrait assets, including
  pre-cutover WebP assets, legacy PNG/JPG assets if present, profile references,
  protected serving, and old asset cleanup.
- Published page image rehearsal for page frontmatter, asset copies, protected
  serving, and local/live mirror sync behavior on copied or staging data.
- Backup/restore transcript on copied realistic data, then a user-approved
  staging-volume snapshot before any staging/live write enablement.

Until that proof exists, label this area `fixture behavior proven; image cutover
decision open`.
