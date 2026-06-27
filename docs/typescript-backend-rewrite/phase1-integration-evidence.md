# TypeScript Phase 1 Integration Evidence

Last updated: 2026-06-27

Status: no-live integration evidence for `rewrite/ts-phase1-integration`.

This transcript records the first combined validation pass after integrating the
completed Character, Combat, and readiness/doc lanes. It does not approve PR,
merge, deploy, Fly sync, production SQLite sync, or cutover. Flask remains the
production authority.

## Integrated Branches

- `origin/rewrite/ts-character-advanced-editor-spell-derivation`
- `origin/rewrite/ts-combat-advance-turn-focus-parity`
- `origin/rewrite/ts-route-parity-evidence`

Integration merge commit validated:

- `d30ae302c2a139414333d115f4357fcf8006dbf5`

Worktree:

- `C:\Users\thorn\.codex\worktrees\9490\campaign_player_wiki`

## Runtime

- Python: `C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe`
- Node: `C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64\node.exe`
- npm: `C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64\npm.cmd`

## Commands

```powershell
git switch -c rewrite/ts-phase1-integration
git fetch origin
git merge --no-ff origin/rewrite/ts-character-advanced-editor-spell-derivation -m "Merge character advanced editor TypeScript slices"
git merge --no-ff origin/rewrite/ts-combat-advance-turn-focus-parity -m "Merge combat TypeScript parity slices"
git merge --no-ff origin/rewrite/ts-route-parity-evidence -m "Merge TypeScript rewrite readiness docs"

$nodeDir = 'C:\Users\thorn\Documents\my_scripts\.task-temp\typescript-backend-sqlite-migration-spike-20260625\node-v22.12.0-win-x64'
$env:PATH = "$nodeDir;$env:PATH"
& "$nodeDir\npm.cmd" --prefix apps/api ci
& "$nodeDir\npm.cmd" --prefix apps/api run build
& 'C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe' .\scripts\route_snapshots.py --check
$env:CPW_NODE_BIN = "$nodeDir\node.exe"
$env:CPW_NPM_BIN = "$nodeDir\npm.cmd"
& 'C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe' -m pytest tests\test_typescript_readonly_slice_contract.py -k advanced_editor
& "$nodeDir\npm.cmd" --prefix apps/api run test:route-parity
& "$nodeDir\node.exe" .\tests\combat-selected-pc-sections.mjs
& "$nodeDir\node.exe" .\tests\combat-focus-query.mjs
git diff --check
git diff --cached --check
git status --short --branch
```

## Results

| Check | Result |
| --- | --- |
| `npm --prefix apps/api ci` | Passed; 46 packages installed into ignored `apps/api/node_modules`. |
| `npm --prefix apps/api run build` | Passed. |
| `python scripts/route_snapshots.py --check` | Passed. |
| `pytest tests/test_typescript_readonly_slice_contract.py -k advanced_editor` | Passed: 2 passed, 58 deselected. |
| `npm --prefix apps/api run test:route-parity` | Passed. |
| `node apps/api/tests/combat-selected-pc-sections.mjs` | Passed. |
| `node apps/api/tests/combat-focus-query.mjs` | Passed. |
| `git diff --check` | Passed. |
| `git diff --cached --check` | Passed. |
| `git status --short --branch` | Clean tracked state on `rewrite/ts-phase1-integration`; ignored validation artifacts were `apps/api/dist/` and `apps/api/node_modules/`. |

## Gate Outcome

- `manifest known`: passed for this integrated commit.
- `route parity checked`: passed for route snapshot lockstep plus TypeScript route manifest parity.
- `fixture smoke green`: partially passed for the promoted Advanced Editor and Combat focused fixtures listed above.
- `integrated branch parity green`: not complete for the whole rewrite; remaining route families still need their own focused fixture/golden evidence.
- `staging/copy-data parity ready`: not complete; no copied-data or staging-volume rehearsal was run.

## Remaining Before Cutover Approval

- Full DND create, native Advanced Editor derivation, retraining, level-up, and progression-repair save parity.
- Browser JSON compatibility route decision and tests for global search and session wiki lookup.
- Family-specific evidence transcripts for Systems/shared source, DM Content, publishing/assets, admin/auth/visibility, and error shapes.
- Copied-data backup, mutation, restore, and equivalence rehearsals for promoted write families.
- TypeScript local production packaging/container proof and rollback runbook.
