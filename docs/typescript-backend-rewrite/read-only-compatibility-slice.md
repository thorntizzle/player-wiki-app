# Read-Only Compatibility Slice Evidence

Last updated: 2026-06-25

This document records the first implemented TypeScript read-only compatibility surface.

## Scope Completed

- Added a tracked TypeScript API app under `apps/api` using Hono.
- Implemented `GET /healthz`.
- Implemented `GET /api/v1/campaigns/:campaignSlug` using fixture-backed repository reads.
- Default campaign fixture directory is `tests/fixtures/sample_campaigns`.
- `CPW_CAMPAIGNS_DIR` overrides the fixture directory.
- Both endpoints return JSON-only payloads for the read-only slice and include explicit fixture-mode auth/permissions metadata.
- Missing campaigns return a JSON `404` response.
- Added `apps/api/src/routes.ts` as the implemented-route manifest for the tracked TypeScript slice.
- Added a route-parity smoke check that verifies implemented TypeScript routes stay present in both the Python route snapshot and the active TypeScript route seed.

## Compatibility Contract Verified

- Campaign response includes:
  - `ok`
  - `campaign` with `slug`, `title`, `summary`, `system`, `current_session`, and `systems_library_slug`
  - `auth_source` and explicit read-only auth block
  - read-only `permissions` block

## Added Tests and Checks

- `tests/test_typescript_readonly_slice_contract.py`:
  - runs a focused Flask-vs-TypeScript contract check for stable `campaign` fields for `linden-pass` using sanitized fixture data.
- `apps/api/tests/smoke.mjs`:
  - starts compiled API on a local port and verifies `/healthz`, campaign detail, and 404 behavior.
- `apps/api/tests/route-parity.mjs`:
  - checks implemented route coverage against `route-snapshots.json` and `typescript-route-seed.json`.

## Build/Test Commands

From repo root:

```powershell
npm --prefix apps/api install
npm --prefix apps/api run typecheck
npm --prefix apps/api test
& '<workspace>/.venv/Scripts/python.exe' -m pytest .\tests\test_typescript_readonly_slice_contract.py
& '<workspace>/.venv/Scripts/python.exe' .\scripts\route_snapshots.py --check
```

## Open Items

- Frontend dev-mode pointer to TypeScript API remains open and is tracked separately.
- Remaining read-only surfaces beyond campaign detail remain open.
