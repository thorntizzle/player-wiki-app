# Ops And Fly Deployment

Last updated: 2026-07-20

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Python 3.12.12 is the canonical development and production interpreter; `.python-version` records the exact patch baseline.
- `requirements.txt` owns direct app-runtime ranges, `requirements-prod.txt` adds the production WSGI server, and `requirements-dev.txt` includes the production set plus test/browser tooling.
- Reproducible environments install `requirements-prod.lock` or `requirements-dev.lock` with pip `--require-hashes`. The committed universal Python 3.12 locks pin runtime transitives and do not install Playwright browser binaries.
- Lock refreshes use uv 0.9.28 through `scripts/refresh_requirements_locks.ps1 -Write`; `-Check` resolves into ignored `.local/tmp/runtime-baseline/` storage and byte-compares without changing tracked locks.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`. The wrapper accepts an explicit `-PythonPath`, then `PLAYER_WIKI_PYTHON_PATH`, and can resolve the shared workspace virtualenv from an arbitrary Git worktree.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, `environment-check`, `publisher-manifest`, test, test-focused, test-restore, test-browser, test-serial, `composition-contract`, `test-path-boundary`, contract, check, runtime-check, backup, restore, restore-status, restore-resume, restore-rollback, restore-rehearsal, `player-wiki-reconciliation-dry-run`, `player-wiki-reconciliation-apply`, prepare-fly-campaigns, sync-fly, and deploy-fly.
- `local.ps1 -Action environment-check` emits the resolved interpreter, exact `.python-version`, development-lock SHA-256, checked pinned dependency count, and dependency-consistency result. It uses `pip check` when pip exists and an equivalent installed-metadata check for intentionally pipless validation venvs. Complete `test` and `check` actions run that gate automatically and fail closed on interpreter or installed-lock drift.
- `local.ps1 -Action publisher-manifest` requires a full accepted commit SHA, a retained pytest node-id cache, one or more tracked test selectors, and an ignored `.local` output path. It expands parameterized node IDs, binds the cache and accepted commit/tree, and optionally derives read-only `endpoint:GET` assertions from that commit's route/access manifest. It rejects stale selectors, mutating live routes, abbreviated candidate identity, and output outside `.local`; it creates no wrapper temp/cache roots of its own.
- `local.ps1 -Action contract` runs the deterministic route/API/access manifest checks plus representative read-only smoke coverage for authentication, role and visibility boundaries, campaign surfaces, character assignment, and legacy rich-text rendering.
- The contract action is a fast local tier with a 60-second ceiling and a preferred runtime under 30 seconds. It does not replace focused domain tests, mutation-path tests, real-browser checks when interaction behavior requires them, or the full regression suite.
- `local.ps1 -Action test-focused -TestPath <file-or-node-selector>[,<selector>...]` runs only an explicit focused selection; it never infers a domain from changed files.
- `local.ps1 -Action test-restore` runs the maintained backup/archive, operations, restore-transaction, runtime-lease, and SQLite-safety files. `local.ps1 -Action test-browser` runs the maintained Character read-shell browser, Combat DM-controls browser, and static-asset files.
- `local.ps1 -Action test-serial` runs the maintained migration, SQLite safety, runtime lease/baseline/security, app metadata, backup/restore/operations, login-throttle, and real-browser/live-server files serially. Parallel pytest execution is not installed, enabled, or the default.
- `local.ps1 -Action composition-contract` runs every maintained route-transport file plus app-metadata, contract-smoke, and route-manifest controls. Run it after `create_app`, `register_api`, dependency, recovery-hook, registrar, or route-composition changes. `local.ps1 -Action test-path-boundary` runs generated filesystem path-budget contracts.
- Stateful and test wrapper invocations use a short unique ignored `.local` run name under `.local/tmp/`, `.local/pt/`, and `.local/pc/` for process temp, pytest basetemp, and pytest cache respectively. Read-only inventory actions and `publisher-manifest` do not create these wrapper roots. These paths bound the per-run suffix and prevent workers or consecutive runs from sharing scratch, but they cannot shorten an already long checkout prefix.
- Those `.local` paths are temp roots inside the current checkout; they are not a physical short-root checkout. For decisive Windows validation, add `-PhysicalShortRoot` to `test-focused`, `test-restore`, `test-browser`, `test-serial`, `composition-contract`, `test-path-boundary`, `test`, or `check`. The wrapper refuses dirty source, freezes the exact commit/tree/index, creates a unique detached physical worktree under an absolute `-ShortRootBase`, `PLAYER_WIKI_SHORT_ROOT_BASE`, or the generic drive-root `cpwv` directory, verifies Git/blob/mode identity, then runs the selected action there. Short-root success classifies harness risk but does not replace an explicit supported-length `path_boundary` regression for generated runtime names.
- Normalized text identity is established by the Git commit, tree, index, blobs, and tracked modes; only files marked `text: unset` receive an additional raw-byte comparison. The helper prints its commit/tree/path/exit evidence and retains failures. Successful roots remain by default; `-RemoveShortRootOnSuccess` removes only the current invocation's generated detached clean worktree after identity and path verification. It does not prune or clean historical worktrees.
- Complete `test` and `check` actions are serialized by a lock in the repository's Git common directory. A physical short-root parent holds the lock for its child through a validated recursion guard, so two complete suites cannot claim the same repository at once.
- Production startup fails fast without a strong application secret. Request envelopes, individual uploads, and Systems ZIP extraction are bounded before expensive processing or durable publication.
- Disposable local runtime temp files belong under unique short `.local/tmp/<scope-prefix>-<run-id>/` paths or task-specific folders outside durable app data.

## Backup, Migration, And Recovery Contract

- SQLite schema changes use ordered numbered migrations with recorded migration state. `manage.py init-db` applies pending migrations before the production server starts.
- Migration `0002_player_wiki_reconciliation_operations` adds the private
  publication recovery journal. Migration
  `0003_player_wiki_deletion_reconciliation_operations` adds its distinct
  private deletion journal. Migration
  `0004_character_reconciliation_operations` adds the private new-character
  publication journal. Migration `0005_character_reconciliation_updates`
  extends that journal with interactive-update revision evidence and
  constraints; `0006_character_reimport_reconciliation` adds existing-target
  Markdown/PDF reimport kinds; `0007_character_content_api_update_reconciliation`
  adds complete existing-target raw content API updates; accepted migration
  `0008_character_portrait_reconciliation` owns historical schema version 8
  and adds bounded portrait asset evidence; and accepted migration
  `0009_character_deletion_reconciliation` owns current schema version 9 and
  adds the separate private character deletion journal. The version-1 through
  version-8 migration payloads and checksums remain immutable. This is the
  accepted executable contract, not evidence that a live database has applied
  it.
- Backup archives use the verified v2 format and SQLite-aware online snapshots so committed WAL state is included. Restore validates archive metadata, hashes, database integrity, foreign keys, and migration state before publication.
- Active Player Wiki publication/deletion rows and active character
  publication/update/reimport/content-API/portrait/deletion rows survive backup
  and restore. The archive format remains verified v2 while the current schema
  registry is version 9. Supported self-consistent older producer ledgers are
  validated and restored with current-app migration evidence and
  `migration_required=True`; later `manage.py init-db` advances them to version
  9 before server startup. Current-version active portrait rows retain their
  private desired image bytes in SQLite and through verified-v2 backup/restore,
  then resume forward recovery. Verified archives containing an active portrait
  journal are therefore private recovery material.
  Current-version active deletion rows retain exact metadata-only recovery
  evidence and resume forward recovery; any captured file bytes remain only in
  private same-parent tombstones and are included with the campaign files.
  Tampered, future, and internally inconsistent producer migration evidence is
  rejected.
- Every restore requires explicit destructive-action confirmation. Restoring over an existing, nonempty target creates a mandatory transaction-correlated prebackup; an empty target intentionally creates none. Restore does not expose a skip-prebackup option or a caller-selected prebackup label.
- Restore publication is journaled and atomic. The runtime lease prevents concurrent state-changing operations, and startup refuses to proceed while an interrupted restore journal requires recovery.
- `restore-status` reports a path-redacted recovery summary and fails closed for invalid or tampered journal state. `restore-resume` and `restore-rollback` require explicit confirmation and provide idempotent recovery for supported interrupted phases.
- `restore-rehearsal` accepts legacy-v1 or verified-v2 source archives and reports their evidence level. It uses a disposable, nonempty synthetic target that forces a mandatory verified-v2 prebackup, then verifies integrity and foreign keys, migration application/current state, hashes and counts, committed/clean journal state, and cleanup. It never publishes into active application data, and active-data sentinels must remain unchanged.

## Player Wiki Reconciliation Inspection And Apply

- Operators can run `python ops.py player-wiki-reconciliation-dry-run` or
  `local.ps1 -Action player-wiki-reconciliation-dry-run` to inspect active
  Player Wiki reconciliation journals without creating the Flask app or
  initializing storage. The Python command accepts `--kind` with `all`,
  `publication`, or `deletion`; `--campaign-slug`; `--page-ref`; `--state`
  with `prepared`, `repository_pending`, or `conflict`; and a 32-hex
  `--operation-id`;
  `--page-ref` requires `--campaign-slug`. The PowerShell wrapper exposes the
  same filters through `-ReconciliationKind`,
  `-ReconciliationCampaignSlug`, `-ReconciliationPageRef`,
  `-ReconciliationState`, and `-ReconciliationOperationId`.
- Inspection is deliberately narrower than a repository audit. It covers the
  active publication journal under a verified applied version-2 ledger and
  both the publication and deletion journals under verified applied version-3,
  version-4, version-5, version-6, version-7, version-8, or version-9 ledgers in
  the current version-9 registry. It remains a Player Wiki inspection:
  Character publication and deletion rows, their private YAML, portrait, or
  tombstone recovery evidence, character slugs, and operation identities are
  omitted. It validates the
  complete ledger-owned table and
  active-index inventory before applying filters; it does not report
  unjournaled Markdown or asset drift.
- The command is pre-application and fully zero-write: it acquires no runtime
  lease and creates no lock, temp root, backup, schema, database parent,
  recovery state, repository refresh, filesystem publication, audit event, or
  other application state. It rejects active restore recovery before database
  inspection, opens SQLite with `mode=ro`, `query_only=ON`, and zero busy
  timeout, and observes committed WAL state. Two matching scans plus unchanged
  database, WAL, shared-memory, lock, restore-journal, configuration, and
  relevant-file evidence are required; busy or changing evidence is reported
  as indeterminate rather than repaired.
- Output is deterministic JSON schema version 1. Scope reports only filter
  presence and the selected kind. Operation entries expose the operation ID,
  journal kind/state, operation kind, classification, reason code, recommended
  action, and `backup_required`; they do not expose campaign/page/path/digest,
  recovery payload, audit metadata, timestamps, configuration, or exception
  text. Exit `0` means a stable current-schema inspection with no active rows;
  `1` means stable active rows or supported version-2 migration evidence; `2`
  means invalid, unsupported, or untrusted evidence; and `3` means busy,
  concurrent, or otherwise indeterminate evidence.
- Classifications distinguish precommit-abortable, forward-recoverable,
  Markdown-publication-required, refresh/cleanup-retryable, conflict, and
  manual-attention states. Their exact values are `precommit_abortable`,
  `forward_recoverable`, `forward_recoverable_requires_markdown_publish`,
  `refresh_cleanup_retryable`, `manual_conflict`, `manual_attention`, and
  `manual_repair_or_abandon`. Recommended actions are the advisory values
  `abandon_precommit_after_backup`, `resume_forward_after_backup`,
  `resume_forward_publish_markdown_after_backup`,
  `retry_refresh_cleanup_after_backup`, `repair_or_abandon_after_backup`, and
  `inspect_and_repair_after_backup`; every operation has
  `backup_required: true`. The dry run remains zero-write and has no apply,
  repair, abandon, cleanup, or deletion authority.
- Unsupported migration versions, future or tampered ledgers, missing or
  inconsistent journal tables/indexes, malformed recovery payloads or digests,
  unsafe references, symlinks/reparse points or special files, and missing or
  malformed campaign configuration or roots all fail closed without exposing
  the rejected evidence. A version-2 database is reported as
  `legacy_supported` with `migration_required: true`; a deletion-only request
  at version 2 is unsupported because that ledger does not own the deletion
  journal.
- Operators can apply one supported deterministic recommendation with
  `python ops.py player-wiki-reconciliation-apply`, required
  `--kind <publication|deletion>`, `--operation-id <32-hex>`, and
  `--action <abandon-precommit|resume-forward|retry-refresh-cleanup>` arguments,
  and explicit `--yes`; `--output-dir` is optional. The wrapper exposes the same
  boundary through
  `local.ps1 -Action player-wiki-reconciliation-apply`,
  `-ReconciliationKind`, `-ReconciliationOperationId`,
  `-ReconciliationApplyAction`, `-ConfirmReconciliationApply`, and optional
  `-BackupDir`.
- Apply refuses active restore recovery, acquires the exclusive runtime lease,
  requires a stable current-version-9 inspection whose exact operation and
  recommendation match the request, creates a verified-v2 safety backup, and
  revalidates that exact evidence after backup. It then invokes the existing
  publication or deletion coordinator and proves the selected journal row is
  gone while other rows are unchanged. Manual-conflict and manual-attention
  classifications are refused. Repeating an already completed exact request
  returns the redacted `no_active_operation` failure instead of repeating the
  mutation.
- Apply failures emit bounded redacted JSON without private campaign, page,
  path, payload, digest, audit, configuration, or exception evidence. Success
  may report the retained verified backup path and bounded backup evidence.
  This is a local CLI-only exact-operation boundary: it adds no UI or API
  repair surface, live or bulk operation, product-policy or schema change, or
  character-journal authority.

## Current Fly Deployment Shape

- Fly is the canonical supported production target. The tracked standalone systemd/nginx files are secondary examples aligned to the same one-process, one-Gunicorn-worker SQLite rule.
- Fly release `222` is the historical Phase 3A artifact at exact commit `a5e337bc39fd5a9ca07ca8e2adde3093f988556e`. Fly release `223` is the deployed Phase 3B artifact built from exact pushed-`main` commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`, image `registry.fly.io/linden-pass-player-wiki:deployment-01KXTW2HJ2E9M6S8MG7GAMYS55`, and build id `20260718-110347`. Machine `185516dc4576e8` is healthy 1/1. The later documentation closeout is not part of that deployed image.
- The committed `fly.toml` is sanitized. Its `iad` region and `player_wiki_data` volume are generic, non-secret sample defaults; real app identity remains private local ops configuration.
- The Dockerfile pins `python:3.12.12-slim-bookworm` to immutable OCI index digest `sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c` and installs only `requirements-prod.lock` with pip hash enforcement.
- The real container entrypoint runs `manage.py init-db`, then Gunicorn with one worker, four threads, and a 60-second timeout. Fly retains one always-on machine, one `/data` volume, and one SQLite writer.
- Fly mounts the production SQLite/content volume at `/data`; the app DB lives on that mounted volume.
- `/livez` is the minimal dependency-free liveness endpoint. `/readyz` checks
  database access, schema/migration state, required storage, and campaign
  storage without self-healing, mutating dependencies, or initializing
  storage. The legacy `/healthz` endpoint remains available and returns
  application metadata. All three paths bypass automatic Player Wiki,
  character publication, and character deletion recovery before any recovery
  database or repository access; ordinary application requests retain all
  three internal recovery triggers.
- Real app identity comes from `PLAYER_WIKI_FLY_APP`, `local.ps1 -Action deploy-fly`, or an explicit Fly app argument.
- Fly deploys snapshot the current working tree. Deploy from a clean copy if live should match committed state exactly.
- `.local/`, SQLite files, and local content mirrors are intentionally excluded from images.
- The Docker image is Python-only; it no longer builds or copies a separate browser bundle.

## Data And Volume Boundaries

- On Fly, app code is baked into the image.
- SQLite and campaign content live on the mounted `/data` volume.
- Numbered schema migrations come online through startup `manage.py init-db` against the mounted DB before Gunicorn starts.
- Systems imports, auth rows, memberships, session rows, combat state, and other SQLite-backed changes are not changed by a code deploy unless explicit DB sync is performed.
- Content API writes on Fly update the live volume immediately but do not update local mirrors unless synced down.

## Verification Contract

- After dependency changes, install the development lock into a clean Python 3.12 environment with pip `--require-hashes`, run `pip check`, import `wsgi:app`, confirm Gunicorn is importable, and run the lock script in `-Check` mode twice.
- Static runtime contract tests enforce the immutable base image, hashed production install, migration-before-server entrypoint, one-process/one-worker topology, Fly sample defaults and health shape, strong production-secret requirement, bounded request envelopes, and disposable validator safety.
- `local.ps1 -Action runtime-check` requires an available Docker engine. It builds the current repo with a unique local tag, runs the real entrypoint using a strong disposable secret, ephemeral localhost port, and disposable `/tmp` data paths, then checks `/livez`, legacy `/healthz`, `/readyz`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, production WSGI metadata, and one Gunicorn worker before cleaning the container and image.
- The validator never contacts Fly or mounts real app data. Its local Docker Desktop Linux/amd64 engine-backed build/run verifies the pinned image, real migration from schema 0 to 9 before server start, `/livez` and legacy `/healthz` HTTP 200, missing-campaign `/readyz` HTTP 503 with `self_heal: false`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, and one Gunicorn master with one worker. Disposable containers and images are cleaned up. The local validator itself performs no Fly deployment or live health validation.
- Run `local.ps1 -Action contract` for a fast route, API, access-policy, and representative read-boundary check. Use `local.ps1 -Action composition-contract` for application composition and route-transport changes, `local.ps1 -Action test-path-boundary` for generated path budgets, `local.ps1 -Action test-focused -TestPath ...` for an explicit domain selection, `local.ps1 -Action test-restore` for the maintained recovery lane, `local.ps1 -Action test-browser` for the maintained browser/static lane, and `local.ps1 -Action test-serial` for shared-resource-sensitive coverage. The tracked [Flask Rewrite Program Workflow](../workflows/flask-rewrite-program.md) owns the complete-suite cadence, exact command, canonical environment gate, physical short-root controls, evidence reuse, and failure classification; this current-state document adds no per-slice or milestone complete-suite requirement.
- The deployed Phase 3B runtime commit has runtime identity `973202997e403d2a8402280d427ee72e419a9fbc`, test identity `8d1f1c0e9e10f184c8c04c200e85284ecba6fed6`, and pre-release documentation identity `4ee14ebb29cb96d9db7330ce7382774a7dbad55a`. Its authoritative pushed-`main` complete suite collected 4,092 tests: 4,083 passed and nine were fully classified Windows symlink-capability skips, with zero failures, errors, or xfails and exit code 0 in 1,310.37 seconds. Under the [Flask Rewrite Program Workflow](../workflows/flask-rewrite-program.md), the later documentation-only closeout reuses that qualification when runtime and test identities remain exact and no application or runner ambiguity exists; it does not duplicate the complete suite.
- Normal deploy verification checks Fly status plus live `/livez` and `/readyz`; legacy `/healthz` remains an application-metadata compatibility check.
- After browser route changes, verify representative Flask `/campaigns/...` URLs.
- After app-shell/static-serving changes, verify versioned CSS/JS cache headers where relevant.
- After campaign asset-serving changes, verify representative asset content type.

The operational contract through Phase 3A remains historical release `222` at `a5e337bc39fd5a9ca07ca8e2adde3093f988556e`, followed by Phase 3B release `223`. Phase 4 is on pushed `main` and deployed as Fly release `224` from exact clean commit `b80af7c7b441bb2fcecc763bf6ea4a73f9d85365`, build `20260719-113554`, image digest `sha256:6dd9653c3c31be32b841109ed7f741616f195020e88f934eb4099d9f37a335bd`. Its canonical Python 3.12.12 assembled suite collected 4,633 tests: 4,608 passed, 25 skipped, and none failed or xfailed. `/livez`, `/readyz`, `/healthz`, anonymous campaign discovery, representative campaign HTML, `/api/v1/campaigns`, immutable CSS, and a representative campaign asset were read-only green. The deploy performed no explicit database/content sync or private-data write.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `local.ps1`
- `scripts/generate_publisher_manifest.py`
- `ops.py`
- `player_wiki/migrations.py`
- `player_wiki/backup_archive.py`
- `player_wiki/character_reconciliation.py`
- `player_wiki/player_wiki_reconciliation.py`
- `player_wiki/player_wiki_reconciliation_inspection.py`
- `player_wiki/player_wiki_reconciliation_operations.py`
- `tests/test_player_wiki_reconciliation_inspection.py`
- `tests/test_player_wiki_reconciliation_operations.py`
- `tests/test_migrations.py`
- `tests/test_backup_archive.py`
- `tests/test_character_reconciliation.py`
- `tests/test_operations.py`
- `tests/test_generate_publisher_manifest.py`
- `Dockerfile`
- `fly.toml`
- `.dockerignore`
- `deploy/fly-entrypoint.sh`
- `$campaign-player-wiki-ops-deploy` private skill references for machine-local app identity and Fly commands.
