# Published Content Copied-Data Rehearsal - 2026-06-28

Status: passed for no-live copied fixture rollback evidence

## Scope

- Write family: Published content config/pages/assets.
- Lane branch: `rewrite/ts-published-content-copied-data-rehearsal`.
- Integration base after orchestrator update: `e55273026c41e3a7a8e163d1e441d1e0b65c242c` (`origin/rewrite/ts-phase3-integration`).
- Rehearsal id: `ts-published-content-copied-data-rehearsal-20260628`.
- Tracked evidence target: this transcript only.
- Scratch evidence root: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/` (ignored).

The run used tracked sanitized `tests/fixtures/sample_campaigns` copied under the
ignored rehearsal root plus a disposable SQLite database created under the same
root. It did not use Fly, live SQLite, a local campaign mirror, vault content,
tracked `campaigns/` data, or production-like secrets.

## Safety Confirmation

- Repo root: `<app-worktree>/campaign_player_wiki`.
- Owner checkout avoided: `<owner-checkout>/campaign_player_wiki` was not used as a mutation target.
- `.local/roadmaps/typescript-backend-rewrite-roadmap.md`: absent in this worktree.
- Rehearsal root path guard: `scripts/staging_rehearsal_harness.py check-paths` passed for copied SQLite, copied campaigns dir, and backup archive path.
- Copied SQLite: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/input/player_wiki.sqlite3`.
- Copied campaigns dir: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/input/campaigns`.
- Backup archive: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/backup/published-content-pre-mutation.zip`.
- Restore target: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/restore/target`.

## Commands

```powershell
git fetch origin rewrite/ts-phase3-integration
git rebase origin/rewrite/ts-phase3-integration

$nodeRoot = '<bundled-node-runtime>\bin'
$env:PATH = "$nodeRoot;$env:PATH"
& "$nodeRoot\npm.cmd" ci
& "$nodeRoot\npm.cmd" --prefix apps/api run build
& "$nodeRoot\node.exe" .\.task-temp\run-published-content-rehearsal.mjs
```

The scratch driver called the guarded harness:

```powershell
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py init --family publishing ...
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py check-paths ...
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot --label pre ...
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot --label post ...
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py snapshot --label restore ...
& '<workspace>/.venv/Scripts/python.exe' .\scripts\staging_rehearsal_harness.py compare --before ...\pre\manifest.json --after ...\restore\manifest.json
```

## Baseline Evidence

- TypeScript API built from `e55273026c41e3a7a8e163d1e441d1e0b65c242c`.
- Baseline content config read succeeded for `linden-pass`.
- Baseline content page list returned 29 pages.
- Baseline page detail sample: `locations/port-meridian`, title `Port Meridian`.
- Baseline content asset list returned 2 assets.
- Baseline asset detail sample: `npcs/captain-lyra-vale.png`, media type `image/png`.
- Baseline protected asset smoke: `GET /campaigns/linden-pass/assets/npcs/captain-lyra-vale.png` returned 200, `image/png`, 69 bytes, SHA-256 `cfff279f33f8b787c61cc5b4b0f69c66528c89cb4a8247399024cfb5f5224719`.
- Baseline SQLite publishing tables:
  - `campaign_pages`: 1
  - `campaign_page_sync_state`: 1

## Backup

- Archive path: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/backup/published-content-pre-mutation.zip`.
- Contents: `player_wiki.sqlite3` and `campaigns/**`.
- Size: 20669 bytes.
- SHA-256: `5f4423a08c60971a023e24918cd7f0853c317324ec47e9e76ad86bf189dad0ee`.

The archive was created from the disposable copied data only.

## Mutation Evidence

The TypeScript API ran three local copied-data server instances against disposable paths only.
All mutation responses were saved under the ignored rehearsal root.

Covered sequence:

- `PATCH /api/v1/campaigns/linden-pass/content/config`
  - Updated `current_session` from 2 to 4.
  - Updated `summary` to a copied-data rehearsal value.
- `PUT /api/v1/campaigns/linden-pass/content/pages/notes/rehearsal-field-report`
  - Created a published Notes page.
  - Updated metadata/body, including `source_ref`, `display_order`, and temporary `image`.
  - Unpublished via `published: false`.
  - Republished via `published: true`.
- `PUT /api/v1/campaigns/linden-pass/content/assets/notes/rehearsal-sigil.txt`
  - Uploaded a text asset through `asset_file.data_base64`.
  - Protected asset smoke returned 200, `text/plain`, 50 bytes, SHA-256 `f37f404bf08febaf449b33781ba95a122034ab1e20064538f484dbb4664fe9a7`.
- Backlink removal-safety check:
  - Created `notes/rehearsal-delete-target`.
  - Created `notes/rehearsal-delete-referrer` linking to `[[Rehearsal Delete Target]]`.
  - Plain delete of the target returned `409 hard_delete_blocked`.
  - Blocker details included `Backlinked from Rehearsal Delete Referrer.`
  - Forced delete with `?force=true` returned 200.
- Cleanup mutations:
  - Deleted referrer page.
  - Deleted field report page.
  - Deleted uploaded asset.

Post-mutation snapshot showed expected copied-file changes during the run and stable SQLite publishing table counts:

- `campaign_pages`: 1
- `campaign_page_sync_state`: 1

This confirms the copied-data mutation set did not leave extra SQLite publishing rows in the rehearsal database. It does not prove a staging/live read-model refresh path; it proves rollback equivalence for the current TypeScript copied-fixture behavior.

## Restore And Equivalence

The backup archive was restored into a separate disposable target:

- Restore SQLite: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/restore/target/player_wiki.sqlite3`.
- Restore campaigns dir: `.task-temp/ts-published-content-copied-data-rehearsal-20260628/restore/target/campaigns`.

Harness comparison of pre vs restore:

```json
{
  "changed_files": [],
  "equal": true,
  "sqlite_equal": true
}
```

Restored API samples also matched the baseline after timestamp normalization:

- content config payload matched baseline;
- page count returned to 29;
- `locations/port-meridian` title remained `Port Meridian`;
- asset count returned to 2;
- protected asset sample returned the same media type, length, and SHA-256.

## Blocker Observations

- Backlink blockers were exposed and verified with a `409 hard_delete_blocked` response.
- Character hook blockers were not represented by this copied fixture sequence.
- Session provenance blockers were not represented by this copied fixture sequence.
- Live publication backup/sync/rollback remains untested by design.
- No image conversion decision was tested here. The asset API preserved uploaded bytes and served them through the protected asset route.
- SQLite publishing read-model tables were present and restored equivalently, but this run did not prove a staging/live `campaign_pages` refresh after page writes.

## Decision

- Result: pass.
- Label before: `fixture-write validated`.
- Label after: `copied-data rollback ready` for the published content config/pages/assets copied-fixture write family.
- Not claimed: `staging snapshot ready`, production write approval, Fly deployment approval, live sync approval, or cutover approval.

Remaining evidence needed before a stronger label:

- user-approved staging-equivalent snapshot rehearsal;
- realistic character hook and session provenance blocker coverage if staging data exposes those links;
- explicit staging/live read-model refresh evidence for `campaign_pages` and `campaign_page_sync_state`;
- rollback/sync evidence for live publication flows.

## Proposed Shared-Doc Wording

If the orchestrator chooses to update shared docs later, suggested cutover-readiness wording:

> Published content config/pages/assets now has a no-live copied-fixture backup/mutate/restore transcript covering content config PATCH, page create/update/unpublish/republish/delete, asset upload/read/delete, protected asset serving, backlink hard-delete blocking, forced delete, and restore equivalence. The family is `copied-data rollback ready; staging snapshot required`. Remaining evidence: staging-equivalent snapshot rehearsal, realistic character/session provenance blockers where present, live publication backup/sync/rollback, and explicit staging read-model refresh proof for `campaign_pages` / `campaign_page_sync_state`.
