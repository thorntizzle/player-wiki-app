# TypeScript Route Parity Evidence

Last updated: 2026-06-27

Status: readiness artifact only. This branch does not certify TypeScript cutover because it is not an integration branch containing the active character, combat, session, systems, DM Content, publishing, and ops implementation lanes.

## Purpose

This document defines the no-live evidence required before the TypeScript backend can be considered route-parity ready for user-approved PR, merge, staging, deploy, or cutover steps. Flask remains the production authority until those later approvals happen.

The route-parity proof must answer four questions:

- Are the Flask authority routes and TypeScript route manifest in lockstep?
- Do TypeScript handlers return Flask-compatible JSON, status codes, auth behavior, and error shapes for each route family?
- Do fixture and copied-data checks prove the same behavior without touching live data?
- Are all skipped, deferred, or implementation-branch-dependent checks recorded with enough detail for the orchestrator to rerun them on an integration branch?

## Current Branch Facts

These facts were observed from this docs-only branch and should be refreshed on the integration branch that combines active implementation lanes.

- `scripts/route_snapshots.py --check` passes against the tracked route snapshot.
- `docs/typescript-backend-rewrite/route-snapshots.json` currently contains 135 `/api/v1` route declarations and 145 expanded Flask route entries.
- `docs/typescript-backend-rewrite/typescript-route-seed.json` currently contains 144 seeded TypeScript route entries.
- Seed status counts are: `implemented_fixture_sqlite_write` 81, `implemented_fixture_sqlite_readonly` 35, `implemented_fixture_readonly` 15, `implemented_fixture_write` 7, `deferred_scratch_proof` 5, and `implemented_hono` 1.
- `apps/api/node_modules` and `apps/api/dist/routes.js` are absent in this worktree, so `apps/api/tests/route-parity.mjs` is deferred until local TypeScript dependencies are installed and the API package is built.
- `.local` is absent in this worktree, so ignored roadmap files are not visible here. Do not edit ignored `.local/roadmaps` from this lane.

## Authority Surfaces

Flask authority surfaces:

- `player_wiki/api.py` and `player_wiki/app.py`, as inventoried by `scripts/route_snapshots.py`.
- `docs/typescript-backend-rewrite/route-snapshots.json`, the tracked executable route snapshot.
- `docs/typescript-backend-rewrite/route-snapshots.md`, the human route snapshot companion.
- `docs/typescript-backend-rewrite/parity-inventory.md`, especially route-family status, browser JSON compatibility notes, and error-shape follow-ups.
- `docs/api-v1.md` and current-state docs for documented public contracts.

TypeScript candidate surfaces:

- `apps/api/src/routes.ts` and its exported route manifest after active implementation lanes are integrated.
- `apps/api/tests/route-parity.mjs`, which compares the built TypeScript manifest with the Flask snapshot and seeded route map.
- `docs/typescript-backend-rewrite/typescript-route-seed.json`, which records intended TypeScript route coverage and status.
- `apps/api/tests/smoke.mjs` and focused contract tests once dependencies and build output exist locally.

Do not treat route parity as certified from this branch alone. The active implementation branches must be merged or rebased into an integration branch before broad route parity can be claimed.

## Allowed Local Commands

Use these commands only against the local worktree, sanitized fixtures, or explicitly copied staging data. They do not deploy and they do not contact Fly or live URLs.

```powershell
# Confirm Flask route snapshot lockstep.
& 'C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe' .\scripts\route_snapshots.py --check

# Regenerate the snapshot only after intentional Flask authority route changes.
& 'C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe' .\scripts\route_snapshots.py --write

# Prepare TypeScript checks on an integration branch.
npm --prefix apps/api ci
npm --prefix apps/api run build
npm --prefix apps/api run test:route-parity
npm --prefix apps/api run smoke
npm --prefix apps/api test

# Run focused Flask/TypeScript contract fixtures when present.
& 'C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe' -m pytest .\tests\test_typescript_readonly_slice_contract.py
```

If the repository-local virtualenv differs from the command above, record the exact Python path used in the transcript. Do not substitute production paths or live database paths.

## Forbidden Until Explicit User Approval

Do not run these as part of route-parity evidence collection:

- `fly deploy`, `fly status`, `fly ssh`, `fly proxy`, or any other command that depends on the real Fly app.
- Live `/healthz`, production smoke tests, or any command against live URLs.
- Production SQLite sync, restore, or mutation commands.
- Broad write tests against real local campaign data.
- PR creation, merge, or cutover commands.

## Evidence By Route Family

### Browser JSON Compatibility

Routes: browser compatibility endpoints such as global search, global search preview, session wiki lookup search, and session wiki lookup preview.

Evidence required:

- Flask snapshot lists the compatibility routes and TypeScript either implements compatible JSON routes or the frontend has been intentionally moved to `/api/v1`.
- Local fixture requests compare status codes, content type, response keys, pagination or preview fields, and empty-result behavior.
- Missing-resource and validation responses are compared with the documented matrix in `route-snapshots.md` and `parity-inventory.md`.
- Any intentional compatibility break is documented as a user-approved frontend/API contract change, not hidden inside cutover.

### Characters

Routes: character roster, detail, create/import, advanced editor, advancement, cultivation, controls, portraits, and session-state surfaces.

Evidence required:

- Fixture writes prove create, update, validation failure, hard-delete block, and rollback behavior without real campaign data.
- Copied-data rehearsal proves backup, mutate, verify, restore, and equivalence transcripts for each promoted write family.
- Auth, visibility, `view_as_read_only`, missing campaign, missing character, and unsupported ruleset paths match Flask-compatible JSON envelopes.
- Generated or derived sheet fields are compared with Flask golden responses where derivation parity is in scope.
- Known implementation gaps such as full DND builder saves, advanced-editor derivation, and real advancement saves remain explicitly gated until implemented on the integration branch.

### Combat, Session, And Live

Routes: combat tracker reads and mutations, session polling, session pages/articles, reveal state, diagnostics, and live-view resources.

Evidence required:

- Fixture smoke proves read-only and write route behavior for both DM and player roles.
- Mutation checks include stale revision or conflict handling, invalid payloads, missing resources, and unauthorized role attempts.
- Session/live polling responses preserve shape, cache behavior, and no-content or empty-state behavior expected by the frontend.
- Copied-data rehearsal confirms that combat/session writes can be restored to pre-rehearsal equivalence.

### Systems And Shared Source

Routes: systems wiki reads, source and entry reads, custom entries, imports, item mechanics, visibility, and shared source-backed resources.

Evidence required:

- Source policy is enforced locally: public, private, proprietary, custom, and hidden sources remain separated.
- TypeScript responses preserve Flask keys for list, detail, search, and import-history surfaces.
- Missing source, missing entry, forbidden source, and invalid source-slug responses match the documented error matrix.
- No tracked fixture or transcript includes proprietary vault content or machine-local vault paths.

### DM Content

Routes: DM Content parser, statblocks, conditions, setup handoff, and validation surfaces.

Evidence required:

- Fixture inputs cover valid parse, invalid parse, unknown entity, validation error, and permission failure.
- Response envelopes preserve Flask-compatible structured errors, warnings, normalized entities, and handoff metadata.
- Any parser behavior intentionally changed by TypeScript is recorded as a contract change requiring user approval.

### Publishing And Content Assets

Routes: content config, wiki pages, page sections, assets, protected asset bytes, character content, image conversion, and removal-safety checks.

Evidence required:

- Fixture and copied-data checks prove create/update/delete safeguards without deleting real content.
- Asset routes preserve content type, cache expectations, protected visibility, missing asset behavior, and byte-equivalence expectations where applicable.
- Image conversion or optimization differences are documented with before/after fixture artifacts before staging readiness is claimed.
- Publishing routes do not copy vault-only canon or local campaign mirrors into tracked app fixtures.

### Admin, Auth, And Visibility

Routes: `/me`, view-as, settings, campaign membership, admin user mutation, campaign visibility, audit-like rows, and auth-dependent API gates.

Evidence required:

- Local fixture accounts cover admin, DM, player, read-only view-as, unauthenticated, and unauthorized roles.
- Responses preserve Flask-compatible role fields, campaign lists, visibility flags, and user-facing error shapes.
- Admin mutations are fixture-only and prove validation, duplicate, permission, and audit expectations.
- No real local user database or production auth state is used for parity evidence.

### Error Shapes

Route parity is not green unless error behavior is documented and tested, not merely happy-path JSON.

Evidence required:

- `invalid_json`, `validation_error`, `state_conflict`, `hard_delete_blocked`, unauthorized, forbidden, missing campaign, missing resource, and generic HTML 404 compatibility are each assigned to a family-specific expectation.
- TypeScript does not introduce `422` or a different envelope for existing Flask `400` or `404` cases unless that contract change is approved.
- Browser compatibility routes retain their existing HTML-vs-JSON behavior until the frontend contract changes.

## Transcript Template

Capture one transcript per integration or staging evidence pass.

```text
Route parity evidence transcript
Date:
Operator:
Worktree:
Branch:
Commit:
Integrated branches:
Flask authority snapshot:
TypeScript manifest source:
Fixture data version:
Copied-data snapshot identifier, if used:
Python version and path:
Node version:
npm version:

Command: git status --short --branch
Result:

Command: python scripts/route_snapshots.py --check
Result:

Route snapshot counts:
- /api/v1 declarations:
- Flask expanded routes:
- TypeScript seed routes:
- TypeScript manifest routes:
- Seed status counts:

Command: npm --prefix apps/api ci
Result:

Command: npm --prefix apps/api run build
Result:

Command: npm --prefix apps/api run test:route-parity
Result:

Command: npm --prefix apps/api run smoke
Result:

Focused contract/golden commands:
Result:

Family results:
- Browser JSON compatibility:
- Characters:
- Combat/session/live:
- Systems/shared-source:
- DM Content:
- Publishing/content assets:
- Admin/auth/visibility:
- Error shapes:

Skipped checks and reason:

Decision:
```

When copied data is used, include only sanitized identifiers in the transcript. Record database and content-root paths as local copied-data paths, never production paths.

## Decision Gates

| Gate | Required evidence | Exit criteria |
| --- | --- | --- |
| `manifest known` | Flask route snapshot, TypeScript seed map, and TypeScript manifest source are all identified. | Route counts and seed statuses are recorded; deferred routes are intentionally labeled. |
| `route parity checked` | `route_snapshots.py --check`, TypeScript build, and `test:route-parity` pass on the same integration commit. | No missing Flask authority routes, no untracked implemented TypeScript routes, and no accidental promotion of deferred routes. |
| `fixture smoke green` | Local smoke and focused fixture contract tests pass. | Happy-path, auth, missing-resource, invalid payload, and error-envelope cases are green for each promoted route family. |
| `integrated branch parity green` | Active implementation branches are merged or rebased into one integration branch and revalidated. | Character, combat, session, systems, DM Content, publishing, auth, and error-shape evidence is complete or explicitly deferred with owner approval. |
| `staging/copy-data parity ready` | Copied-data rehearsal transcripts exist for promoted write families. | Backup, mutate, verify, restore, and equivalence checks are green without live data, Fly commands, or production paths. |

## Current Known Gaps

- This docs-only branch has not built the TypeScript API package; `apps/api/node_modules` and `apps/api/dist/routes.js` are absent.
- Broad route parity must wait for an integration branch containing the active implementation lanes.
- Character write parity still needs full fixture and copied-data proof for full DND create, advanced editor derivation, advancement persistence, cultivation, controls, portraits, and session-state surfaces.
- Browser JSON compatibility routes need an explicit retain-vs-migrate decision before cutover.
- Combat/session/live, systems/shared-source, DM Content, publishing/content assets, admin/auth/visibility, and error shapes need family-specific fixture transcripts once implementation branches land.
- Missing-resource behavior currently spans JSON and generic HTML 404 paths; route family expectations must be recorded before declaring parity green.
- Publishing asset and image conversion behavior needs byte/content-type evidence before staging readiness.

## Close-Out Rule

Do not use this artifact to justify deployment by itself. The next route-parity evidence pass must run on an integration branch with built TypeScript output, fixture data, and no-live transcripts attached for every route family promoted past `manifest known`.
