# Stack Spike: TypeScript Backend Runtime Choice

Date: 2026-06-25
Owner: campaign rewrite slice
Scope: scratch spike at `.task-temp/typescript-backend-framework-spike-20260625`
Status: complete evidence capture for framework runtime viability; migration layer still open

## Recommendation

For the TypeScript rewrite spike, Hono is the preferred initial stack because it gives a clear API boundary and the same checked request behaviors with lower runtime coupling to route surfaces. TanStack Start is viable and proved runnable for the same API requirements, but it should be chosen only if the team wants tighter full-stack route coupling.

For migration-layer follow-up and driver fit, see `sqlite-migration-spike.md`.

## Verified package/tooling assumptions

- `hono` and `@hono/node-server` were installed from npm in a scratch project.
- `@tanstack/react-start` was installed from npm in a separate scratch project.
- `better-sqlite3` was used for SQLite reads because the bundled Node runtime did not expose `node:sqlite`.
- `drizzle-orm` and `drizzle-kit` package versions were checked from npm to confirm availability for later migration work.

## Environment and package-manager bootstrap

The environment had no usable package manager in PATH, so a local runtime path was created:

1. Downloaded npm tooling into scratch: `.task-temp\typescript-backend-framework-spike-20260625\npm`
2. Downloaded Node 22.12.0 tarball into scratch: `.task-temp\typescript-backend-framework-spike-20260625\node-runtime\node-v22.12.0-win-x64`
3. Used the bundled npm CLI via `<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js`

Observed versions:
- Node: `v22.12.0`
- npm CLI: `10.9.0`

## Commands and outcomes

### Version and availability checks

```powershell
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view hono version
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view @tanstack/react-start version
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view better-sqlite3 version
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view drizzle-orm version
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js view drizzle-kit version
```

Observed: `4.12.27`, `1.168.26`, `12.11.1`, `0.45.2`, `0.31.10`.

### Hono spike (`.task-temp\typescript-backend-framework-spike-20260625\hono-spike`)

```powershell
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js install hono @hono/node-server
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js install better-sqlite3
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js install --save-dev @types/better-sqlite3
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run typecheck
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run build
```

Observed:
- `typecheck`: pass
- `build` (tsc): pass
- Local HTTP probe to Hono app: `SPIKE_OK`
- SQLite route behavior: returned fixture row via `better-sqlite3`.

### TanStack Start spike (`.task-temp\typescript-backend-framework-spike-20260625\tanstack-start-spike`)

```powershell
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run typecheck
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js install better-sqlite3
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js install --save-dev @types/better-sqlite3
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe <scratch>/node-runtime/node-v22.12.0-win-x64/node_modules/npm/bin/npm-cli.js run build
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe node_modules/vite/bin/vite.js dev --host 127.0.0.1 --port 4173
<scratch>/node-runtime/node-v22.12.0-win-x64/node.exe scripts/verify.mjs
```

Observed:
- `tsc --noEmit` pass after SQLite shim update
- `vite build`: pass
- Dev server started on `http://127.0.0.1:4173`
- Local HTTP probe: `SPIKE_OK`

## Spike checklist

| Checklist item | Result |
| --- | --- |
| Route handling | Hono: PASS, Start: PASS |
| API contract typing | PASS |
| Session cookie write/read | PASS |
| Protected asset serving + `image/webp` | PASS |
| Multipart/form-data upload parsing | PASS |
| SQLite read path | PASS (`better-sqlite3`; `node:sqlite` unavailable in this runtime) |
| Local Windows run + production-style build | PASS for both |
| Local package availability checks for `hono`, `@hono/node-server`, `@tanstack/react-start`, `drizzle-orm`, and `drizzle-kit` | PASS |
| Route-based health and API validation script | PASS (`SPIKE_OK`) |
| Fly deploy shape | not run (left for integration stack phase) |

## Remaining risk / open blocker

- `drizzle` migration command shape and `libsql` path were not executed in this spike; only package availability was confirmed.
- Drizzle migration and deployment posture are still required before final architecture lock.
