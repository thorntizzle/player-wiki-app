# Stack Spike: TypeScript Backend Runtime Choice

Date: 2026-06-25
Owner: campaign rewrite slice
Scope: Bounded evidence spike in `.task-temp/typescript-backend-stack-spike-20260625`
Status: partial stack evidence; final framework choice deferred until package tooling is available

## Recommendation

Do not lock the final TypeScript backend framework from this pass alone. This spike proved
that the local Node runtime can support the app's backend constraints in principle, but it did
not execute TanStack Start or Hono because neither package is installed and no package manager
is available in PATH.

For the next concrete spike, evaluate a dedicated Hono API first and TanStack Start second
against the same runnable fixture checklist. Hono maps more directly to the backend replacement
goal and the Web-standard request/response proof built here. TanStack Start remains a serious
candidate for a same-origin full-stack app, but it needs stricter package-boundary guardrails
before it can be selected for backend ownership.

The immediate blocker is local toolchain access, not framework capability:
- no package manager (`npm`/`corepack`) is available in PATH,
- repository root has no package manifest,
- only `frontend/package.json` exists and it currently carries a Vite/TanStack Router pilot shape.

When package install tooling is restored, proceed with a second spike branch that wires the
same fixture checklist into a minimal Hono API app and a real TanStack Start app scaffold.

## Snapshot of checked options

The following options were evaluated against the same checklist. Only static proof could be
run for the frameworks themselves because neither framework is installed in the existing
workspace tree. The runnable scratch proof uses plain Node APIs to prove local constraints
that either framework must satisfy.

- Option A: TanStack Start
  - Pros: tight route + server-function ergonomics for the existing TanStack frontend ecosystem, first-party conventions for same-origin web APIs, cookies, and typed route contracts.
  - Cons: adds a full-stack coupling risk if service boundaries are not guarded, requires package-manager setup and a separate install of Start tooling.
- Option B: Hono API + React/TanStack Router frontend
  - Pros: explicit HTTP API boundary, small web-standard server model, adapter-first deployment options, and clear service package seam.
  - Cons: additional integration work for SSR/client consistency and route-surface parity once the app moves toward same-origin rendering patterns.

## Spike proof checklist

| Checklist item | Spike evidence | Result |
| --- | --- | --- |
| Route handling | `createTypedRouteTable` with typed handler signatures in spike router table | PASS |
| API contract typing | typed request/response interfaces and JSON writer in spike server | PASS |
| Session cookie write/read | `/api/session/login` sets cookie; `/api/session/me` reads cookie | PASS |
| Protected asset response + media type | `/assets/protected/*` checks cookie and returns `content-type` | PASS |
| Multipart/form-data upload parse | `/api/upload` parses via `Request.formData()` | PASS |
| SQLite read | `node:sqlite` and scratch route data return fixture rows | PASS |
| Local Windows dev command | TypeScript compile and runner execute with bundled Node runtime | PASS for no-install scratch; BLOCKED for real framework scaffold |
| Production-style build/typecheck | TypeScript compile to `dist` using bundled `tsc` | PASS |
| Fly deploy shape | not executed in this spike | BLOCKED |
| Test runner setup | not executed in this spike | BLOCKED |

## Commands run and observed status

### Runtime/tooling checks

- `<node-runtime>\node.exe -v`
  => Node available (`v24.14.0`).
- `Get-Command npm,corepack` in repo root
  => no npm/corepack on PATH.

### Package baseline checks

- `Get-Content frontend/package.json`
  => only Vite, React Query, TanStack Router in dependencies.
- `rg -n "hono|@hono|@tanstack/start" frontend/package.json frontend/package-lock.json`
  => no matches.
- `node -e "require.resolve('hono')"`
  => `Cannot find module 'hono'`.
- `node -e "require.resolve('@tanstack/start')"`
  => `Cannot find module '@tanstack/start'`.

### Scratch spike build/run checks

- From `.task-temp/typescript-backend-stack-spike-20260625`: `<node-runtime>\node.exe ..\..\frontend\node_modules\typescript\bin\tsc -p tsconfig.json`
  => pass.
- From `.task-temp/typescript-backend-stack-spike-20260625`: `<node-runtime>\node.exe dist\spike-runner.js`
  => pass; logs `STACK_SPIKE_OK` after route, cookie, protected asset, upload, and SQLite checks.
- `<node-runtime>\node.exe -e "const {DatabaseSync}=require('node:sqlite'); ..."`
  => SQLite read path executed and rows returned from fixture DB.

## Tooling gaps and blockers

- There is no package manager available in PATH in this environment.
- No root package manifest means no backend package shape exists yet.
- The repository currently contains only Vite + TanStack Router frontend dependencies.
- `node:sqlite` works in the bundled Node runtime, but it is still an experimental Node API; production persistence should be decided again once Drizzle and SQLite driver packages can be installed and compared.
- Real TanStack Start and Hono execution remains unproven until package installation is available.

## Next steps

1. Install tooling (`npm` or equivalent) into the workspace and add the first concrete `@tanstack/start` and `hono` scratch projects under dedicated temporary folders.
2. Implement the same `/healthz`, cookie, protected asset, upload, and SQLite routes in both scratch projects and include:
   - build + typecheck,
   - one local request test suite,
   - one deployment-shape smoke command.
3. Re-open this ADR once both are executed and gate the rewrite stack choice on the same evidence set.
