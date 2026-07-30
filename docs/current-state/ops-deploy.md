# Ops And Fly Deployment

Last updated: 2026-07-30

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

- Work from the `campaign_player_wiki` app repo root for app repo operations.
- Python 3.12.12 is the canonical development and production interpreter; `.python-version` records the exact patch baseline.
- `requirements.txt` owns direct app-runtime ranges, `requirements-prod.txt` adds the production WSGI server, and `requirements-dev.txt` includes the production set plus test/browser tooling.
- Reproducible environments install `requirements-prod.lock` or `requirements-dev.lock` with pip `--require-hashes`. The committed universal Python 3.12 locks pin runtime transitives and do not install Playwright browser binaries.
- Lock refreshes use uv 0.9.28 through `scripts/refresh_requirements_locks.ps1 -Write`; `-Check` resolves into ignored `.local/tmp/runtime-baseline/` storage and byte-compares without changing tracked locks.
- Prefer the workspace virtualenv Python or `local.ps1` instead of bare `python`. The wrapper accepts an explicit `-PythonPath`, then `PLAYER_WIKI_PYTHON_PATH`, and can resolve the shared workspace virtualenv from an arbitrary Git worktree.
- `local.ps1` is the Windows-first wrapper for bootstrap, run, `environment-check`, the three `validation-evidence-*` identity/decision/compact-failure actions, `phase-closeout-anchor-render`, `phase-closeout-anchor-write`, `phase-closeout-anchor-verify`, `publisher-manifest`, `publisher-preflight`, `publisher-focused-proof`, `publisher-focused-run`, `publisher-focused-finalize`, `publisher-dispose`, test, test-focused, test-restore, test-browser, test-serial, `composition-contract`, `test-path-boundary`, contract, check, runtime-check, backup, restore, restore-status, restore-resume, restore-rollback, restore-rehearsal, `player-wiki-reconciliation-dry-run`, `player-wiki-reconciliation-apply`, prepare-fly-campaigns, sync-fly, and deploy-fly.
- `local.ps1 -Action environment-check` emits the resolved interpreter, exact `.python-version`, development-lock SHA-256, checked pinned dependency count, and dependency-consistency result. It uses `pip check` when pip exists and an equivalent installed-metadata check for intentionally pipless validation venvs. Complete `test` and `check` actions run that gate automatically and fail closed on interpreter or installed-lock drift.
- `local.ps1 -Action validation-evidence-freeze` records a clean full commit/tree plus runtime, tests, workflow, Fly-blob, interpreter, dependency, runner, envelope, and accepted-suite identities in deterministic canonical JSON. `validation-evidence-assess-reuse` emits an explicit `REUSE`, `INVALIDATE`, or `RECLASSIFY` decision; `validation-evidence-failure` writes one compact pre-invocation failure receipt without manufacturing a full evidence seal. The wrapper selects the configured interpreter and passes only scalar input/output paths; Python owns parsing, hashing, comparison, and atomic publication.
- The three `phase-closeout-anchor-*` actions finalize one explicitly named sanitized lifecycle record without discovering or interpreting lifecycle Markdown. `render` is read-only and binds three registered same-repository worktrees, explicit refs, the frozen accepted identity, an independently accepted sanitization receipt, exact source bytes, destination/ledger prestates, and one prospective ledger row in a self-sealed plan. `write` alone holds the common validation lock, revalidates that plan, writes and verifies the ignored canonical copy first, then updates exactly one tracked ledger row. A ledger-only failure retains the verified copy and emits `RECOVERING`. `verify` rehashes the copy and row without changing either target. The tool never stages, commits, switches, fetches, pushes, deploys, deletes evidence, or grants cleanup authority.
- `local.ps1 -Action publisher-manifest` requires a full accepted commit SHA, a retained pytest node-id cache, a distinct canonical ignored `.local` node-ID export path, one or more tracked test selectors, and a distinct ignored `.local` manifest output path. It atomically copies and verifies the exact cache bytes into the canonical export, expands parameterized node IDs, binds the accepted commit/tree plus the exported cache's repository-relative path, SHA-256, and count, and optionally derives read-only `endpoint:GET` assertions from that commit's route/access manifest. The manifest does not retain the source cache's absolute path. The action rejects stale selectors, mutating live routes, abbreviated candidate identity, paths outside `.local`, and aliased export/manifest paths; it removes any stale manifest before export and creates no wrapper temp/cache roots of its own.
- The Publisher focused gate is a sealed three-action lifecycle. `publisher-focused-proof` validates the candidate-bound preflight, plan, manifest, frozen validation identity, independently frozen browser requirements, and strict task/candidate-bound browser-capability receipt without starting tests. The receipt reports selected capabilities and must satisfy the separate formal requirement and assertion partition; it does not define or weaken them. `publisher-focused-run` alone inherits the common validation lock and gives the ordered node-ID array directly to one non-PTY pytest child; Python owns the exclusive sentinel, exact argv, byte-preserving streams, observer ledgers, and invocation count. `publisher-focused-finalize` performs no process launch and may reclassify retained evidence after a finalizer-only failure. Missing or drifted inputs fail before the sentinel; a consumed invocation is never retried.
- `local.ps1 -Action contract` runs the deterministic route/API/access manifest checks plus representative read-only smoke coverage for authentication, role and visibility boundaries, campaign surfaces, character assignment, and legacy rich-text rendering.
- The contract action is a fast local tier with a 60-second ceiling and a preferred runtime under 30 seconds. It does not replace focused domain tests, mutation-path tests, real-browser checks when interaction behavior requires them, or the full regression suite.
- `local.ps1 -Action test-focused -TestPath <file-or-node-selector>[,<selector>...]` runs only an explicit focused selection; it never infers a domain from changed files.
- `local.ps1 -Action test-restore` runs the maintained backup/archive, operations, restore-transaction, runtime-lease, and SQLite-safety files. `local.ps1 -Action test-browser` runs the maintained Character read-shell browser, Combat DM-controls browser, and static-asset files.
- `local.ps1 -Action test-serial` runs the maintained migration, SQLite safety, runtime lease/baseline/security, app metadata, backup/restore/operations, login-throttle, and real-browser/live-server files serially. Parallel pytest execution is not installed, enabled, or the default.
- `local.ps1 -Action composition-contract` runs every maintained route-transport file plus app-metadata, contract-smoke, and route-manifest controls. Run it after `create_app`, `register_api`, dependency, recovery-hook, registrar, or route-composition changes. `local.ps1 -Action test-path-boundary` runs generated filesystem path-budget contracts.
- Stateful and test wrapper invocations use a short unique ignored `.local` run name under `.local/tmp/`, `.local/pt/`, and `.local/pc/` for process temp, pytest basetemp, and pytest cache respectively. Read-only inventory actions and `publisher-manifest` do not create these wrapper roots. These paths bound the per-run suffix and prevent workers or consecutive runs from sharing scratch, but they cannot shorten an already long checkout prefix.
- `deploy-fly` records its exact three run roots and removes only those roots after success, a nonzero Fly exit, or a terminating PowerShell error. Cleanup validates absolute containment and rejects reparse-point anchors or descendants. An unsafe or incomplete cleanup fails the action closed and reports the deploy and cleanup outcomes separately.
- Those `.local` paths are temp roots inside the current checkout; they are not a physical short-root checkout. For decisive Windows validation, add `-PhysicalShortRoot` to `test-focused`, `test-restore`, `test-browser`, `test-serial`, `composition-contract`, `test-path-boundary`, `test`, or `check`. The wrapper refuses dirty source, freezes the exact commit/tree/index, creates a unique detached physical worktree under an absolute `-ShortRootBase`, `PLAYER_WIKI_SHORT_ROOT_BASE`, or the generic drive-root `cpwv` directory, verifies Git/blob/mode identity, then runs the selected action there. Short-root success classifies harness risk but does not replace an explicit supported-length `path_boundary` regression for generated runtime names.
- Normalized text identity is established by the Git commit, tree, index, blobs, and tracked modes; only files marked `text: unset` receive an additional raw-byte comparison. The helper prints its commit/tree/path/exit evidence and retains failures. Successful roots remain by default; `-RemoveShortRootOnSuccess` first uses ordinary `git worktree remove <exact-path>` without force for only the current invocation's generated detached clean worktree after identity and path verification. If Git deregisters that worktree but leaves a residual, the helper may remove only the exact generated leaf with bottom-up, no-follow filesystem operations after repeating containment and non-reparse checks. It retains the root on Git refusal, continued registration, reparse points, identity or containment ambiguity, or cleanup refusal; it never performs automatic force deletion, pruning, or historical worktree cleanup.
- Complete `test` and `check` actions are serialized by a lock in the repository's Git common directory. A physical short-root parent holds the lock for its child through a validated recursion guard, so two complete suites cannot claim the same repository at once.
- The shared short-root and complete-validation-lock implementation lives in `scripts/short_root_validation.psm1`, which exports only `Invoke-PhysicalShortRootValidation` and `Invoke-WithCompleteValidationLock`. Both `local.ps1` and the executable `scripts/invoke_short_root_validation.ps1` import that module; neither dot-sources a parameterized helper into caller scope.
- Production startup fails fast without a strong application secret. Request envelopes, individual uploads, and Systems ZIP extraction are bounded before expensive processing or durable publication.
- Disposable local runtime temp files belong under unique short `.local/tmp/<scope-prefix>-<run-id>/` paths or task-specific folders outside durable app data.

## Phase 8 Local Candidate And Release Boundary

- **Frozen local release base:** Phase 8 candidate
  `0f144e51a6a00dd74b005cbf7a19af5acd720be9`, tree and index
  `f989201a91e46bd0c75ed829b5957d5fd88d4294`, has runtime subtree
  `aec65a79385049ebf7f201fb2461ca20e6b1361f`, test subtree
  `c2d983699b6e62d48ab8373e61c03d03921600a2`, and workflow subtree
  `3569ceda3e1ab22ed6bd9932aa2cd6d1ac018cda`. Its tracked `fly.toml` blob is
  `ea61988ae4118dfa7c180fa6075f80f3d110807d`. P8.1 composite parity is closed.
- **Exact-candidate suite:** the independent suite was accepted with 5,039
  collected, 5,007 passed, 32 skipped, and zero failures or errors in exactly
  one invocation. It remains reusable while the runtime and test identities
  above remain exact and no unresolved application ambiguity appears. Its
  retained terminal verdict, evidence index, and seal are under
  `.local/phase8-p84b-measurement-support/complete-suite/p84bcs-20260730T005135Z-393f3dbc1742/`
  with SHA-256
  `99BFBEE73C2700BCECC3118BDFF18F082709E4DC38BC80F334444E51F265C6C2`,
  `F190F598C62BA2E3B6E4E57E1C71A8AE2022F312CB177DCFA2B9B2F82666A98F`,
  and `65A194340E4F2ECA0F4BB9AAEA4246712BB14FB36B682572C509D4DBB7B4F05E`.
- **Exact-candidate comparison disposition:** the final gate is
  `WAIVED_BY_OPERATOR_RUNNER_FAILURE`; program credit is `NONE`, and the
  operator explicitly accepts the residual unmeasured-regression risk. The
  immutable first and final zero-sample readiness receipts are
  `.local/phase8-p84b-measurement-support/runner-readiness/p84breadiness-20260730T025509Z-fb2e412b2a10/terminal-verdict.json`
  at SHA-256
  `939ABF0F17A781DFFEA3A1F31BD725F07F5C0513A2B3E7A3E5EA0ADB0C3DF32D`
  and
  `.local/phase8-p84b-measurement-support/runner-readiness-final/p84breadiness-final-20260730T032440Z-d96369714408/preflight-terminal.json`
  at SHA-256
  `3CDEAFD961F4147164620C6F35DADEC38450F0BC1E35A5F2F4B6B8062D8FAB83`.
  They support no product or performance inference and do not establish a
  measured exact-candidate result.
- **Historical comparison support:** the independently accepted comparison
  between Phase 4
  `b80af7c7b441bb2fcecc763bf6ea4a73f9d85365`, tree
  `30dc769f0f8d40b1f89307459cf2700541815c02`, and historical Phase 8
  candidate `af3f122edca1a9eb80645fc8f1ac3870371f3484`, tree
  `d1cf551bc840b12560ce4cc47920c6589a179cee`, retained 135 samples per
  candidate, observed zero unexpected errors, and recorded maximum ratio
  `1.1444007858546168` within the `1.15` ceiling. It is supporting history only,
  never exact-`0f144e51` credit.
- **Accepted distribution boundary:** the docs-only accepted descendant
  `53fc8b5059d01464f70e99a54142cb03780cd17d`, tree
  `4f413a6470e4ed96e9bdebd6b8ebac486cb2192c`, is the exact clean local and
  remote `main` and the exact clean local and remote Phase 8 source branch.
  Its executable parent remains `0f144e51` with the runtime, tests, accepted
  suite, and comparison disposition recorded above. The single authorized
  deploy produced Fly release `233`, image
  `sha256:9e7728168dfdcbc315a80054df61e20809d28fe0f570c530529ebb3d2633ddd9`,
  and started machine `185516dc4576e8` in `iad` at `performance/2` and
  4096 MB. Read-only source-derived live correctness passed 10/10 checks.
  The bounded public-only observation completed 30 serial requests with five
  warmups and 25 retained samples, zero errors or identity mismatches, and
  endpoint p95 values from 67.386 ms through 106.4 ms. That observation did
  not include authenticated database, render, or apply-path performance and
  does not replace the explicit `WAIVED_BY_OPERATOR_RUNNER_FAILURE`, credit
  `NONE`, exact-candidate comparison disposition.

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
- Fly release `224` is the historical Phase 4 artifact from exact clean commit
  `b80af7c7b441bb2fcecc763bf6ea4a73f9d85365`. Fly release `225` is the
  historical Phase 5 artifact from exact clean commit
  `8766292816f2f91f10085f09f2e372651545eced`, tree
  `292d130a3e76b5208061dd7f58b477305461530b`. Phase 6 release `v229` was the
  most recent formally recorded program deployment, from exact clean commit
  `2c6774b269995320c149dd81e59d842304e740a8`, tree
  `c297efdfaa67e6aa98bef3d52194100fc47948f0`, image
  `deployment-01KY2WVT1XF8BTXBNQ6Q63G1AH`, digest
  `sha256:de8157f9799099094a1a411e3c6c825dd3276bb795f3801b492c2c8802794869`,
  machine `185516dc4576e8`, and build `20260721-135131`. Health and readiness
  checks were green. The accepted release candidate's test subtree is
  `0ea591db4faf8ee86d582958e6506da1c1760ef9`. Later pushed-main workflow, test,
  and documentation commits were not part of that deployment; release `v229`
  had exact runtime subtree
  `8df5d77456ec84877fcb43caf0b26761630bceb1`.
- User-supplied production provenance on 2026-07-28 reports that hotfix commit
  `24f65346` is currently deployed, `/readyz` is healthy, and the machine is
  `performance-2x`, equivalent to two performance CPUs and 4096 MB of memory.
  This configuration-and-documentation slice did not query Fly, resize a
  machine, deploy, or perform new live validation.
- The committed `fly.toml` is sanitized. Its `iad` region and `player_wiki_data`
  volume are generic, non-secret sample defaults; real app identity remains
  private local ops configuration. Its exact `[[vm]]` requirements are
  `memory = '4096mb'`, `cpu_kind = 'performance'`, and `cpus = 2`; it does not
  use the lower-precedence `size` preset. Before a future deploy, the Publisher
  must bind the accepted clean pushed target's `fly.toml` to that exact block;
  local-candidate acceptance or retained production provenance is not a
  substitute for the pushed-target check.
- Fly enforces a tracked `[[vm]]` section on later deploys. A manual `fly scale vm` or `fly scale memory` change is reset to the committed `[[vm]]` requirements by the next deploy unless `fly.toml` is updated.
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

The formally recorded operational history includes releases `222`, `223`,
`224`, `225`, and Phase 6 release `v229` from exact clean commit
`2c6774b269995320c149dd81e59d842304e740a8`, tree
`c297efdfaa67e6aa98bef3d52194100fc47948f0`. Its canonical Python 3.12.12 suite
passed 4,789 tests, skipped 25, and failed 0. The deterministic Publisher
manifest bound 25 expanded node IDs and eight read-only GET routes; its focused
run passed 25/25. Health/readiness, representative public and access-denial
routes, and static assets were read-only green. The Publisher task had no
browser backend or authenticated-session fixture; the operator explicitly
accepted HTTP-only live closeout. Accepted local real-browser evidence remains
the interaction proof, and authenticated production browser interaction was
not run. The `v229` deploy performed no explicit database/content sync or
private-data write. The later hotfix production state and capacity are recorded
above only from user-supplied provenance.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `local.ps1`
- `scripts/validation_evidence.py`
- `scripts/generate_publisher_manifest.py`
- `scripts/publisher_closeout.py`
- `scripts/short_root_validation.psm1`
- `scripts/invoke_short_root_validation.ps1`
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
- `tests/test_publisher_closeout.py`
- `tests/test_publisher_focused_validation.py`
- `tests/test_validation_evidence.py`
- `tests/test_short_root_validation.py`
- `tests/test_runtime_baseline.py`
- `Dockerfile`
- `fly.toml`
- `.dockerignore`
- `deploy/fly-entrypoint.sh`
- [Fly `[[vm]]` configuration and deploy-reset precedence](https://fly.io/docs/reference/configuration/#the-vm-section)
- [Fly `performance-2x` CPU and memory equivalence](https://fly.io/docs/launch/scale-machine/#scale-by-process-group)
- `$campaign-player-wiki-ops-deploy` private skill references for machine-local app identity and Fly commands.
