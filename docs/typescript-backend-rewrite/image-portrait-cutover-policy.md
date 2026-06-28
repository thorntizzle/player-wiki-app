# TypeScript Image And Portrait Cutover Policy

Last updated: 2026-06-28

Status: operator decision brief; no cutover choice made

## Operating Boundary

Flask remains the production authority. This document does not approve a PR,
merge, deploy, live data write, Fly sync, production cutover, live image data
migration, or a production image-policy choice. It records the current
TypeScript behavior, the Flask/product contract it diverges from, the operator
options, and the exact decision still needed before image and portrait handling
can be called cutover-ready.

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
- `docs/typescript-backend-rewrite/image-portrait-compat-proof-2026-06-28.md`
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
  pre-existing WebP assets
- the legacy direct portrait URL
  `/campaigns/:campaignSlug/characters/:characterSlug/portrait` resolves the
  current profile asset reference with the character detail read gate and
  streams the stored bytes/media type for existing WebP references and
  extension-preserved PNG/JPG/GIF/WEBP uploads in sanitized fixture proof
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

Focused proof:

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
- Direct legacy portrait URL serving works for existing WebP profile references
  and extension-preserved PNG/JPG/GIF/WEBP uploads, uses character detail access
  checks, and returns TypeScript JSON error shapes for unauthenticated, missing,
  or cleared portrait cases.

Existing broader evidence remains in `apps/api/tests/smoke.mjs` and
`docs/typescript-backend-rewrite/read-only-compatibility-slice.md`, including
content asset list/detail/delete checks and prior portrait PNG preservation and
delete checks.

## Operator Decision Brief

This is an explicit user/orchestrator decision gate, not a worker-selected
cutover answer. Choose one policy before any TypeScript production cutover,
staging write enablement, or live image migration.

### Option A: Preserve Flask WebP Conversion Everywhere User-Facing

Decision: TypeScript keeps Flask's WebP-normalized contract for character
portrait uploads and browser/editor publication flows. PNG/JPG portrait uploads
become `characters/<characterSlug>/portrait.webp`; browser/editor page-image
publication keeps producing WebP quality 82 assets and page frontmatter by
default; GIF/WebP continue to pass through validation where the current Flask
contract allows that.

Consequences:

- Keeps current-state docs, character portrait behavior, publishing guidance,
  and page-image frontmatter conventions aligned with production Flask.
- Requires TypeScript image conversion support before portrait/editor cutover.
- Keeps low surprise for users who expect new PNG/JPG portrait and article-image
  uploads to become app-owned WebP copies.
- Adds runtime dependency and conversion failure modes that the current
  TypeScript slice intentionally avoided.

Remaining proof required:

- TypeScript conversion implementation and focused tests for PNG/JPG-to-WebP,
  GIF/WebP pass-through, media types, old-asset cleanup, stale revisions, absent
  portrait delete validation, existing WebP reads, and direct legacy portrait URL
  serving.
- Publication/editor tests proving page frontmatter points at WebP quality 82
  assets after PNG/JPG source uploads or session-article image promotion.
- Copied-data and staging-snapshot rehearsals for existing WebP assets, any
  legacy PNG/JPG portrait assets, page frontmatter, protected serving, and
  backup/restore equivalence.

Migration and rollback implications:

- Existing extension-preserved TypeScript fixture behavior cannot be promoted as
  production behavior without being replaced or migrated.
- Rollback to Flask is lowest-friction because Flask already understands the
  WebP-normalized product contract.
- Any data created by TypeScript before conversion lands would need an explicit
  cleanup/migration plan before or during rollback.

### Option B: Accept TypeScript Extension-Preserving Behavior

Decision: Treat the current TypeScript behavior as the new production contract
for selected portrait and content-asset routes. PNG/JPG/GIF/WEBP portrait uploads
and content asset writes preserve the uploaded bytes and extension; media type
comes from the stored extension; page/frontmatter callers are responsible for any
format normalization they require.

Consequences:

- Matches the currently proven TypeScript fixture behavior and avoids adding an
  image conversion dependency.
- Changes the current user-facing portrait and publication contract documented
  by current-state, character, publishing, and API docs.
- Creates mixed portrait/page-image formats by design instead of by migration
  residue.
- Requires explicit client/operator guidance so publication workflows know when
  to preconvert WebP assets.

Remaining proof required:

- User approval that this is an intentional product-contract change.
- Documentation updates across current-state, API, character, and publishing
  references so WebP conversion is no longer promised for the affected flows.
- Staging/live asset audit for existing WebP, PNG, JPG, GIF, and frontmatter
  references, plus proof that all relevant clients render mixed formats.
- Rollback rehearsal proving Flask can tolerate mixed extension-preserved assets
  created during the TypeScript window, or a cleanup plan before Flask fallback.

Migration and rollback implications:

- Data migration may be lighter upfront because uploaded bytes stay as-is.
- Rollback is riskier: Flask publication/portrait paths may resume converting
  future PNG/JPG uploads while TypeScript-created assets remain mixed-format.
- Operators need a clear rule for whether existing WebP assets remain WebP and
  whether any legacy PNG/JPG assets should be left alone or normalized.

### Option C: Split Raw Asset Storage From User-Facing Publication

Decision: Keep low-level `PUT /api/v1/campaigns/:campaignSlug/content/assets/*`
as an extension-preserving raw asset writer, but require user-facing portrait and
published-image/editor flows to preserve Flask's WebP-normalized behavior unless
a workflow explicitly opts out. Direct legacy portrait URL compatibility remains
a read requirement.

Consequences:

- Preserves the user-facing product contract for portraits and article images
  while keeping generic asset storage simple and explicit.
- Requires clear API/client boundaries so raw asset writes are not mistaken for
  publication conversion.
- Leaves two valid image-write contracts in the system: raw asset storage and
  normalized publication/portrait flows.
- Most closely matches the current docs tension: the Gen2 content asset API is
  documented as extension-preserving, while portrait/page-image publication is
  documented as WebP-normalized.

Remaining proof required:

- User approval that the split is the intended cutover policy.
- TypeScript portrait/editor conversion implementation and tests for
  user-facing flows, plus raw-content-asset tests proving `/content/assets/*`
  remains extension-preserving.
- Client/payload review so read and write response URL shapes do not silently
  change without a versioning/client decision.
- Copied-data and staging-snapshot rehearsals for both policy lanes, including
  backup/restore equivalence.

Migration and rollback implications:

- Existing raw content assets can remain mixed-format, while published page
  images and portraits need policy-specific migration or verification.
- Rollback is manageable if normalized flows write Flask-compatible WebP assets
  and raw asset callers are documented as lower-level storage.
- Operators must rehearse both a normalized portrait/page-image restore and a
  raw asset restore so neither lane masks the other's failures.

## Decision Gate

Before this area can move past documentation evidence, a human decision must
answer:

1. Should production TypeScript preserve Flask WebP conversion for character
   portraits?
2. Should browser/editor publication of page images preserve Flask WebP quality
   82 behavior, accept extension-preserving uploads, or split by workflow?
3. Is the low-level content asset API allowed to remain extension-preserving
   after cutover?
4. What migration rule applies to existing WebP assets, any legacy PNG/JPG
   portrait assets, and published page frontmatter?
5. What rollback rule applies to mixed-format assets created during any
   TypeScript staging or production window?

## Remaining Gate

This gate is not cutover-ready.

Required proof before readiness:

- User or orchestrator selection of Option A, Option B, Option C, or a
  replacement policy with the same migration and rollback specificity.
- Implementation and test work that matches the chosen policy exactly. If the
  chosen policy preserves Flask conversion for any TypeScript route, tests must
  cover PNG/JPG-to-WebP conversion, GIF/WebP pass-through where applicable,
  media types, exact old-asset cleanup, stale revision behavior, absent portrait
  delete validation, existing WebP profile reads, and direct
  `/campaigns/:campaignSlug/characters/:characterSlug/portrait` resolution. If
  the chosen policy accepts extension preservation, tests must prove that
  behavior and docs must be updated to remove Flask-conversion promises for the
  affected flows.
- Focused TypeScript content asset tests for the chosen raw/converted boundary,
  including PNG/JPG/GIF/WEBP media types and proof that `/content/assets/*` does
  or does not perform conversion according to the chosen policy.
- Publication/editor implementation decision and proof: either keep automatic
  WebP conversion in Flask-only browser/editor flows until cutover, add a
  TypeScript publication/editor conversion slice, or deliberately document
  extension-preserving publication behavior.
- Migration rehearsal for existing character portrait assets, including
  pre-cutover WebP assets, legacy PNG/JPG assets if present, profile references,
  protected serving, and old asset cleanup.
- Published page image rehearsal for page frontmatter, asset copies, protected
  serving, and local/live mirror sync behavior on copied or staging data.
- Backup/restore transcript on copied realistic data, then a user-approved
  staging-volume snapshot before any staging/live write enablement.

Until that proof exists, label this area `fixture behavior proven; image policy
decision required`.
