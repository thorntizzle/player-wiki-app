# Image And Portrait Compatibility Proof - 2026-06-28

Status: fixture proof for direct legacy character portrait serving; no live data, no deploy.

## Scope

- Base branch: `rewrite/ts-image-portrait-compat-proof`
- Integration base: `ac67e95e67a30ddbe8bea553e65f84345ef9ef34`
- Production authority remains Flask.
- This pass did not add `sharp`, image conversion, live data migration, Fly commands, route seed edits, or PR/merge work.

## Behavior Proven

- TypeScript now serves `GET /campaigns/:campaignSlug/characters/:characterSlug/portrait`.
- The route resolves the same `definition.profile.portrait_asset_ref` advertised by TypeScript character roster/detail payloads.
- The route uses the existing character detail read gate, including Characters-scope access and assigned-character Session/Combat fallback access.
- The route streams the underlying protected campaign asset with the stored bytes, `Content-Type`, inline disposition, and length.
- Missing characters return the existing TypeScript `content_character_not_found` JSON shape.
- Missing or cleared portrait assets return `campaign_asset_not_found`.

## Fixture Evidence

`apps/api/tests/image-portrait-policy.mjs` now verifies the advertised legacy portrait URL for:

- existing WebP profile references
- uploaded PNG bytes served as `image/png`
- uploaded JPG bytes served as `image/jpeg`
- uploaded GIF bytes served as `image/gif`
- uploaded WEBP bytes served as `image/webp`
- unauthenticated legacy portrait reads returning `auth_required`
- cleared portrait metadata returning `campaign_asset_not_found`

The same test still verifies generic protected campaign asset serving and extension-preserving content asset writes.

## Validation

- `powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action ts-api-check -NodeRoot <bundled-node-root>` passed.
- `<bundled-node-root>\node.exe .\apps\api\tests\image-portrait-policy.mjs` passed.

## Remaining Gate

The direct URL compatibility gap is closed for sanitized fixture profiles. The remaining image/data-policy gate is the broader cutover decision: preserve Flask's PNG/JPG-to-WebP conversion, migrate existing data/clients, or explicitly accept extension-preserving behavior for selected TypeScript API routes.
