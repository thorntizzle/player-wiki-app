# Ops And Fly Deployment

Last updated: 2026-09-24

## Owns

- Local Windows wrapper usage, Python/runtime conventions, backups/restores, Fly deploys, SQLite volume boundaries, deployment verification, and operational safety rules.

## Current Local Contract

Candidate acceptance requires independent adversarial review of every changed
path and affected entry-to-side-effect path on the exact frozen candidate.
Focused diagnostics are optional when they resolve a concrete uncertainty;
the retired automated suite and candidate gate are not available. Historical
acceptance statements below describe completed releases, not current commands.

- Work from the confirmed app repository root. Use Python 3.12.12 from
  `.python-version`; do not rely on bare `python` from `PATH`.
- `requirements.txt` owns direct runtime ranges, `requirements-prod.txt`
  adds Gunicorn, and `requirements-dev.txt` adds Playwright for optional live
  latency diagnosis. Their hashed locks support reproducible installs.
- Refresh locks with pinned uv 0.9.28 through
  `scripts/refresh_requirements_locks.ps1`. The production lock is unchanged
  by the suite retirement.
- `local.ps1` supports install, bootstrap, run, environment-check,
  phase-closeout-anchor render/write/verify, runtime-check, backup, restore
  and restore transaction actions, artifact
  inventory/retention assessment, Player Wiki reconciliation inspection/apply,
  prepare-fly-campaigns, sync-fly, and deploy-fly.
- `phase-closeout-anchor-*` preserves the protected evidence ledger workflow.
  Its write action uses the shared Git-common-directory lock in
  `scripts/evidence_lock.psm1`; it does not invoke the retired suite.
- `environment-check` reports the selected interpreter, exact Python version,
  development-lock SHA-256, installed pinned dependencies, and dependency
  consistency. It does not invoke pytest.
- The wrapper resolves Python from `-PythonPath`, then
  `PLAYER_WIKI_PYTHON_PATH`, then the shared or repo-local environment. It
  uses unique ignored `.local/tmp/` roots for stateful actions.
- `deploy-fly` cleans only its own validated temporary root and reports
  deployment and cleanup failures separately. It does not expand cleanup to
  historical or unrelated worktrees.
- The explicit route/access policy and route/API/role/visibility manifest in
  `docs/contracts/` remain static security and compatibility references.
  Runtime authorization is enforced in application code.

## Diagnostics And Live Health

- The default-on, separately disableable `PLAYER_WIKI_INCIDENT_DIAGNOSTICS_ENABLED` stream emits privacy-bounded `incident_event_v1` records for access decisions, non-read requests, and named publication/apply outcomes. [Incident Diagnostics](../incident-diagnostics.md) owns its schema and runbook. It writes through the existing app logger; no new durable store or retention guarantee is added.
- The older request trail and live timing stream remain off by default behind `PLAYER_WIKI_REQUEST_TRAIL_ENABLED` and `PLAYER_WIKI_LIVE_DIAGNOSTICS`. The request-trail payload no longer includes a path or remote address. It omits health/static requests.
- `player_wiki/character_read_diagnostics.py` remains in the runtime and attaches request-scoped Character read timing and outcome headers only when `PLAYER_WIKI_LIVE_DIAGNOSTICS` is enabled. The dedicated Character read measurement harness was retired; the retained `scripts/measure_live_latency.py` measures Session and Combat surfaces. Production activation and monitoring require a separately authorized deployment/configuration decision.
- `/livez` reports process liveness and `/readyz` reports service readiness; normal authorized deploy verification reads both. Activating or changing live diagnostics, monitors, deployment configuration, or live data is a separate operator gate, not an effect of local candidate review.

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
  `0009_character_deletion_reconciliation` owns historical schema version 9 and
  adds the separate private character deletion journal. Forward-only migration
  `0010_campaign_encounter_presets` owns historical schema version 10 and adds the
  campaign-owned preset aggregate, ordered entries, actor metadata, cascade,
  source lookup index, and store-facing constraints without altering tracker
  tables. Forward-only migration `0011_character_update_apply` owns historical
  schema version 11. It rebuilds the character publication journal losslessly,
  admits `character_update_apply`, enforces exact state or one reviewed state
  reconciliation, and adds apply-only audit event/metadata with nullable
  actor/target foreign keys. Forward-only migration
  `0012_npc_recharge_metadata` owns historical schema version 12. It rebuilds
  `campaign_combatant_resource_counters` with `reset_kind` constrained to
  `source`, `daily`, or `recharge_d6` and a `recharge_threshold` that is
  required from 2 through 6 only for `recharge_d6`. It preserves existing
  counter rows and the combatant lookup index, and backfills case-insensitive exact `Per day`
  labels as `daily` with all other existing rows as `source`; both backfills
  retain a null threshold. Forward-only migration
  `0013_campaign_session_closeouts` owns current schema version 13. It adds the
  campaign-confined closed-Session closeout aggregate and six-item checklist,
  explicit revision and actor evidence, restrictive Session ownership,
  cascading item ownership, and nullable actor foreign keys without creating
  or backfilling lifecycle rows. The version-1 through version-12 migration
  payloads and checksums remain immutable. This is the
  accepted executable contract, not evidence that a live database has applied
  it.
- Preset schema/store, guided Character apply, NPC recharge metadata, and the
  post-Session closeout kernel are application
  capabilities only. Their accepted candidates or commits do not establish that a deployment,
  hosted migration, live Character apply, or other live database/content write
  occurred. Migrations 11 through 13 change no backup archive format.
  Campaign cutover projects selected preset rows in the existing
  `session_history` family; out-of-scope rows remain sealed preservation and
  selected actor references participate in the existing account closure.
- Backup archives use the verified v2 format and SQLite-aware online snapshots so committed WAL state is included. Restore validates archive metadata, hashes, database integrity, foreign keys, and migration state before publication.
- Active Player Wiki publication/deletion rows and active character
  publication/update/reimport/content-API/portrait/deletion rows survive backup
  and restore. The archive format remains verified v2 while the current schema
  registry is version 13. Supported self-consistent older producer ledgers are
  validated and restored with current-app migration evidence and
  `migration_required=True`; later `manage.py init-db` advances them to version
  13 before server startup. A verified version-12 archive restores under the
  version-13 app with `migration_required=True`; a version-13 archive is not a
  downgrade artifact for version-12 code. Populated closeout aggregates and
  item notes remain private Session-history data and survive verified-v2
  backup/restore. Current-version active portrait rows retain their
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
  version-4, version-5, version-6, version-7, version-8, version-9, version-10,
  version-11, version-12, or version-13 ledgers in the current version-13
  registry. It remains a Player Wiki inspection:
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
  requires a stable current-version-13 inspection whose exact operation and
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
  `292d130a3e76b5208061dd7f58b477305461530b`. Phase 6 release `v229` was a
  later formally recorded program deployment, from exact clean commit
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
- Phase 8 release `233` is the later accepted distribution boundary recorded
  under the
  [Phase 8 release boundary](#phase-8-local-candidate-and-release-boundary).
- Fly release `v235` is the current formally recorded deployment. It was built
  from exact clean pushed documentation/build commit
  `0a68c134af3a81ac4dc59f50a388bc95d275fe06`, tree
  `556af9d69aaee506a59d4c84c3a062bc1b4b5a8d`; its runtime-bearing accepted code
  parent is `7151116a0b6074808e2326e0280591aa02019210`, tree
  `b9bf347ddc238862aa038606b208c917d1dd9fc6`. The release completed with image
  `deployment-01M00HDP6XCXJ66JZC9TFGW7A3`, manifest
  `sha256:155d648673491dd0ccfc8d6960a162b08a791de4423293bb64e5cb1eab031d77`, and
  build `20260814-122427`; health metadata reported the exact Git commit with
  `dirty=false`.
- Machine `185516dc4576e8` remained started in `iad` with `1/1` health checks
  passing, retained two performance CPUs and 4096 MB, and kept the existing
  volume attached. The release performed no resize, configuration change,
  content/database sync, private-data write, cleanup, or rollback.
- Post-deploy `/livez`, `/readyz`, and legacy `/healthz` returned HTTP `200`.
  Anonymous `/` returned the contract-valid `302` to `/campaigns` for the
  current multi-public-entry state; the public picker and a representative
  direct public campaign route returned HTTP `200`.
- One existing authenticated task-local browser session performed GET-only
  direct Session then Session Character navigation. Session Character rendered
  without a visible error at a coarse `~352 ms` for a Xianxia-or-non-DND sheet;
  the selected section was not recorded. No forms or mutations were used, and
  no credentials or browser storage were inspected.
- The sanitized UTC observation window
  `2026-08-14T16:24:26.783Z`-`2026-08-14T16:31:50Z` included one Session
  Character document request. Starting process RSS/high-water memory was about
  `76.7/79.3 MiB`, with zero `5xx`, busy `503`, request exception, SQLite
  busy/locked, OOM/crash, or unexpected-restart signal. The request completed
  below the `750 ms` slow-log threshold, so query count and response bytes were
  unavailable. Compared cautiously with the incident baseline of `8-31 s`,
  `281-735` queries, `88-443 KB`, `430-451 MiB` RSS, and multiple busy `503`s,
  the single read is materially favorable but is not causal proof, a
  production-wide result, or a natural group-load window. Current evidence
  does not justify a resize; preserve the current shape and observe a future
  natural group-use window before any capacity decision.
- Historical user-supplied provenance on 2026-07-28 reported hotfix commit
  `24f65346`, healthy readiness, and the same two-performance-CPU/4096 MB shape.
  Later formal releases `233` and `v235` supersede that as the current
  deployment record.
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
  database or repository access. The exact Flask `static` endpoint also skips
  all three recovery operations, including conditional, range and missing-file
  responses. Existing favicon and mechanics-impact exclusions remain in place.
  Campaign assets, Session article images and Character portraits remain
  eligible, as do static-looking dynamic routes and unmatched routes when
  earlier request guards allow them. Eligible application requests retain all
  three internal recovery triggers; the wiki trigger handles both publication
  and deletion journals. App construction does not drain these journals.
  Static-only traffic leaves pending work unchanged until an eligible request
  attempts the existing bounded recovery; no idle completion is promised.
- Guided Character apply interruptions use the existing character-publication
  trigger on eligible requests. Exact prior or already-desired evidence resumes
  forward; conflicting evidence remains protected and requires manual repair.
  The Player Wiki dry-run/apply commands do not inspect or operate on Character
  journals, and this slice adds no live or bulk recovery command.
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

The operational diagnostics below remain available for concrete uncertainties.
Historical acceptance evidence remains below. Current candidate acceptance requires independent precommit
adversarial review of every changed path and affected call path, with no
unresolved blocking finding. A focused local drill is optional for a concrete
uncertainty. Older domain-document test guidance is superseded as a mandatory
gate.

- For dependency incidents, the development-lock, pip, WSGI import, Gunicorn, and lock-script checks are available as focused diagnostics.
- `local.ps1 -Action runtime-check` requires an available Docker engine. It builds the current repo with a unique local tag, runs the real entrypoint using a strong disposable secret, ephemeral localhost port, and disposable `/tmp` data paths, then checks `/livez`, legacy `/healthz`, `/readyz`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, production WSGI metadata, and one Gunicorn worker before cleaning the container and image.
- The validator never contacts Fly or mounts real app data. Its local Docker Desktop Linux/amd64 engine-backed build/run verifies the pinned image, real migration from schema 0 to 13 before server start, `/livez` and legacy `/healthz` HTTP 200, missing-campaign `/readyz` HTTP 503 with `self_heal: false`, Python 3.12.12, Gunicorn 23.0.0, `pip check`, and one Gunicorn master with one worker. Disposable containers and images are cleaned up. The local validator itself performs no Fly deployment or live health validation.
- Historical acceptance: the deployed Phase 3B runtime commit has runtime identity `973202997e403d2a8402280d427ee72e419a9fbc`, test identity `8d1f1c0e9e10f184c8c04c200e85284ecba6fed6`, and pre-release documentation identity `4ee14ebb29cb96d9db7330ce7382774a7dbad55a`. Its authoritative pushed-`main` complete suite collected 4,092 tests: 4,083 passed and nine were fully classified Windows symlink-capability skips, with zero failures, errors, or xfails and exit code 0 in 1,310.37 seconds. That qualification was reusable under the former exact-identity rule; it does not establish current candidate credit.
- Normal deploy verification checks Fly status plus live `/livez` and `/readyz`; legacy `/healthz` remains an application-metadata compatibility check.
- For a concrete browser-route uncertainty, representative Flask `/campaigns/...` URLs are available as a focused diagnostic.
- For a concrete app-shell/static-serving uncertainty, inspect versioned CSS/JS cache headers where relevant.
- For a concrete campaign-asset-serving uncertainty, inspect representative asset content type.

The formally recorded operational history includes releases `222`, `223`,
`224`, `225`, Phase 6 release `v229` from exact clean commit
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
private-data write. Later Phase 8 release `233` and current Character Read
Performance release `v235`, including the bounded read-only live verification
and its limitations, are recorded above.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `local.ps1`
- `scripts/phase_closeout_anchor.py`
- `scripts/validation_evidence.py`
- `scripts/evidence_lock.psm1`
- `ops.py`
- `player_wiki/migrations.py`
- `player_wiki/campaign_combat_preset_store.py`
- `player_wiki/combat_preset_models.py`
- `player_wiki/campaign_cutover_exporter.py`
- `player_wiki/backup_archive.py`
- `player_wiki/character_reconciliation.py`
- `player_wiki/character_update_apply.py`
- `player_wiki/player_wiki_reconciliation.py`
- `player_wiki/player_wiki_reconciliation_inspection.py`
- `player_wiki/player_wiki_reconciliation_operations.py`
- `Dockerfile`
- `fly.toml`
- `.dockerignore`
- `deploy/fly-entrypoint.sh`
- [Fly `[[vm]]` configuration and deploy-reset precedence](https://fly.io/docs/reference/configuration/#the-vm-section)
- [Fly `performance-2x` CPU and memory equivalence](https://fly.io/docs/launch/scale-machine/#scale-by-process-group)
- `$campaign-player-wiki-ops-deploy` private skill references for machine-local app identity and Fly commands.
