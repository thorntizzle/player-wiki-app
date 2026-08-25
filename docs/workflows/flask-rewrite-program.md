# Flask Rewrite Program Workflow

Last reviewed: 2026-07-28

Status: accepted Flask rewrite workflow authority

This document adds program-specific branch, review, evidence, and rollback
rules to the repository workflow. Use the universal role, authority, context,
and worktree rules in [AGENTS.md](../../AGENTS.md),
[Agent roles](agent-roles.md), [Authority lanes](authority-lanes.md), and
[Worktrees](worktrees.md) instead of restating them here.

## Branch And Worktree Contract

- Between phases, pushed and deployed `main` is the sole durable baseline. Do
  not retain a permanent cross-phase integration branch.
- After an explicit next-phase handoff, create one durable phase branch named
  `codex/flask-rewrite-phaseN` from the exact accepted `main` SHA. Record that
  base SHA and its worktree before opening slice writers.
- Name slice branches `codex/flask-rewrite-pNN-<bounded-slug>`.
- Base every slice on the then-current durable phase-branch SHA and record that
  SHA in the slice handoff.
- Give every slice an isolated worktree and one active writer.
- Never recreate or base new work on the retired `rewrite/typescript-backend`
  or `rewrite/ts-phase3-integration` histories.
- After a phase is independently accepted, delegate the authorized formal close
  to one Publisher subagent under `agent-roles.md`. After exact `main`
  integration, push, deployment when authorized, read-only live verification,
  and manifest-scoped cleanup, the next phase starts from the resulting
  accepted `main`, not from a retired phase branch.

An implementer leaves the bounded change for an independent verifier who did
not write it. Verification begins read-only. If repairs are needed, hand the
exact findings to the implementer or a narrowly scoped repair agent, then use
fresh independent verification before integration.

## Review Boundary

A reviewable slice is one behavioral contract, one ownership cluster, and one
rollback unit. Split work when parts have independent rollback paths or need
different evidence domains. There is no arbitrary line-count cap; review size
is determined by whether one reviewer can verify the declared contract and
revert it without removing unrelated behavior.

## Evidence Envelope

Every implementation-to-verification and verification-to-integration handoff
records:

- base and head SHAs;
- changed paths and diff statistics;
- preserved contracts and any intentionally changed contracts;
- exact focused validation commands and results;
- browser evidence when the behavior requires a real browser;
- qualifying frozen domain-integration complete-suite evidence when the handoff
  depends on that gate;
- residual risks and untested boundaries; and
- documentation accounting, including why no update was needed when none was
  made;
- the canonical validation environment manifest when the handoff uses a
  decisive suite: interpreter executable and exact version, development-lock
  SHA-256, locked dependency count, and dependency-consistency result;
- transition timestamps for writing, freeze, verification, integration, and
  closure, plus tool outages and user-attention gates that materially delayed
  the lane; and
- every retained disposable evidence root, its owner, reason, cleanup
  authority, and retention state.

Each material lifecycle transition also records the acting role and task or
context identity, a change kind (`candidate-delta`, `orchestrator-accounting`,
`verifier-result`, or `publisher-report`), the affected commit/tree when any,
and the authoritative evidence pointer. Lifecycle accounting never changes the
accepted candidate identity. An untagged change or a `candidate-delta` after
freeze is candidate drift: close the Publisher action and return the candidate
to identity reconciliation and qualification.

## Program Continuation And Gate States

The Phase Orchestrator owns continuous progress toward the whole phase. Ending
a worker, task turn, candidate, or gate never ends the program by itself.

- Harness/script/command errors, evidence-root mistakes, task/tool/capacity
  outages, environment mismatch, process or port contention, missing evidence,
  test failures, candidate rejection, verifier findings, and integration
  conflicts are `RECOVERING` or monitored `WAITING`.
- Preserve the original attempt and exact identity, keep only the affected gate
  closed, assign the smallest safe repair or recovery owner, and continue
  automatically through retry and fresh verification.
- Repeated routine failure changes the recovery method, diagnosis, ownership,
  or backoff. It does not create a terminal result or user-attention gate.
- Never record these conditions as terminal `HOLD`, `REJECT/HOLD`, or
  `blocked`. A rejected candidate returns to repair; it does not reject the
  phase objective.
- Use `READY_FOR_AUTHORIZATION` only when every possible local gate is complete
  and the next action is a separately authorized main integration, push,
  deployment, live/data operation, destructive cleanup, rollback, or formal
  close.
- Only an unresolved product decision, including an architecture,
  compatibility, or security-policy choice, or a genuine safety issue may stop
  the program.

## Publisher Test And Live Manifest

Before external release actions, generate one deterministic machine-readable
manifest from the retained node-id cache produced for the exact accepted
candidate:

```powershell
powershell -ExecutionPolicy Bypass -File .\local.ps1 `
  -Action publisher-manifest `
  -PublisherAcceptedCommit <accepted-sha> `
  -PublisherNodeidsCache <retained-nodeids-path> `
  -PublisherNodeidsExport <canonical-ignored-evidence-path> `
  -PublisherTestSelector <selector-or-selector-array> `
  -PublisherLiveRoute <endpoint:GET-or-array> `
  -PublisherManifestOutput <ignored-evidence-path>
```

The generator expands parameterized tests from the cache, rejects stale or
non-test selectors, binds commit/tree and cache hash, and reads route/access
assertions from the accepted commit's deterministic route contract. Publisher
focused validation uses the expanded node IDs exactly. Read-only live checks
use the derived GET route, authentication/access policy, actor matrix, and
denial mode plus explicit runtime bindings for converters. Challenge stale
operations prose or a hand-written selector instead of weakening the accepted
source/test contract.

The retained node-ID cache and generated Publisher manifest must be exported to
their canonical ignored lifecycle/evidence paths before the decisive physical
root becomes cleanup-eligible. Generate the manifest before disposing that
root; a cache or manifest available only inside a removed validation root is not
formal-close evidence.

## Publisher Release-Readiness Preflight

Before a Publisher performs its first external action, complete and retain a
candidate-bound, local-only readiness preflight. This is a release gate, not an
authority grant: source publication, target integration, deployment, live
checks, and credential handling still require their separately named operator
gates. A user may authorize the sealed automated disposal policy once as part
of the formal close; it becomes executable only after every named release gate
is green.

The preflight must establish all of the following for the exact accepted
commit/tree:

- Name the canonical Python executable explicitly; record its exact version,
  development-lock SHA-256, locked dependency count, and dependency-consistency
  result. Do not rely on a Python selected from `PATH`.
- When the Publisher host uses Windows PowerShell 5.1, prove the actual
  local-only invocation and capture path before release work: argument passing,
  child exit-state capture, text decoding/encoding, and retained result output
  must work with that host. A process-scoped execution-policy bypass may be
  used only when separately permitted by the existing local workflow.
- Prove candidate-bound node-ID determinism across fresh collections before
  granting cache or manifest credit. Compare two fresh collections using the
  repository's declared canonical ordering and record their identity; a stale,
  time-dependent, or host-order-dependent collection closes the release gate
  and returns to deterministic collection repair.
- Confirm a required real-browser capability is attached to the Publisher, or
  record the explicitly authorized parent-operated fallback script and the
  role that will audit its captured results. Task-local browser attachment must
  never be inferred, and HTTP-only checks are not a silent substitute for a
  required browser gate. Freeze the required evidence mode (`browser`,
  `GET_ONLY`, or `split`) and complete non-overlapping assertion partition
  independently in the formal candidate config and sealed plan. Retain a
  strict browser-capability receipt bound to the Publisher task and exact
  candidate; it names the selected mode and available capabilities and must
  satisfy the separate frozen requirements without rewriting or shrinking
  them. A parent-operated fallback additionally binds a contained ignored
  script and an independent auditor.
- Produce the exact sealed cleanup census and disposition for every
  program-owned worktree, branch, evidence root, runner/cache/temp root, and
  deploy-generated path before release begins. The plan binds accepted
  commit/tree, expected target state, canonical lifecycle/anchor controls,
  cache/manifest/config hashes, phase ownership, and an immutable per-item
  proof. An eligible historical residual may declare exact link-only fixture
  leaves and the narrow Windows attribute normalization as part of that proof.
  It can execute only after the formal-close receipt records green Git,
  deployment, and live gates; a failed proof is a refusal, never an expanded
  cleanup request.

The Python-owned `scripts/publisher_closeout.py` is the canonical executor.
`preflight` receives an explicit interpreter, candidate JSON, and ignored
output directory; it owns JSON, Python ordering, child capture, Git census, the
manifest call, browser-capability binding, and plan sealing. The focused gate
then uses three distinct actions:

1. `publisher-focused-proof` rehashes the sealed preflight, disposal plan,
   manifest, independently frozen browser requirements, browser-capability
   receipt, and frozen validation identity. The selected capabilities must
   satisfy the separate formal requirements. The proof freezes the exact
   ordered expanded node-ID array and interpreter/dependency identity without
   starting pytest.
2. `publisher-focused-run` is the only action run under the exported complete
   validation lock. Python owns the direct argv array, exclusive invocation
   sentinel, raw stdout/stderr files, opt-in pytest observer, invocation count,
   and clean postflight. It starts at most one non-PTY pytest child and never
   retries.
3. `publisher-focused-finalize` only rehashes and classifies the retained proof,
   child result, raw streams, observer counts/ledgers, and postflight. It may
   recover from a finalizer-only fault without running pytest again and emits
   `FOCUSED_GATE_PASS` only for the exact single green execution.

`dispose` accepts only the sealed plan and a matching green formal-close
receipt, then writes a per-item dry-run or apply receipt for eligible **local**
worktrees, local phase refs, and managed ignored artifact roots. It deliberately
does not push or delete remote refs. Remote publication and any separately
authorized remote-ref policy remain Publisher transport steps outside this
helper and must not be inferred from a green local disposal receipt. `local.ps1`
exposes thin `publisher-preflight`, `publisher-focused-proof`,
`publisher-focused-run`, `publisher-focused-finalize`, and
`publisher-dispose` actions. The wrapper validates scalar paths, delegates JSON
and node-ID handling to Python, and returns the child exit code. It must never
parse plan JSON, choose Python from `PATH`, reconstruct or sort node IDs, decode
captured streams, or suppress a child failure.

Keep external action closed on any missing, mismatched, or ambiguous preflight
result. Preserve and classify the attempt, repair the launcher or environment,
and repeat the preflight automatically against the same accepted identity. A
tracked candidate change returns the phase to its normal qualification gates.

## Source-Derived Text Fingerprints

When a source-derived textual fingerprint or version is intended to be
Git-text-equivalent, its contract must name the canonical bytes and line-ending
rule before the value is relied upon. The implementation must normalize only
the declared fingerprint input and must add focused controls proving equivalent
LF, CRLF, and CR physical text yields the same canonical value. The contract
must also state the encoding and the expected canonical result.

Raw-byte identity is the alternative contract: it deliberately preserves
physical bytes and must not claim Git-text equivalence. This fingerprint rule
does not alter verification-copy identity requirements. Commit, tree, index,
tracked blob, and tracked-mode proof remain authoritative, and no line-ending
or content normalization is permitted while preparing a verification copy.

## Task-Local Browser Evidence

Follow **Real-Browser Verification Across Task Isolation** in
`agent-roles.md`. This program adds no alternate browser-attachment or
acceptance procedure.

## Validation Cadence

### 1. Targeted Slice Gates

- Every slice receives the smallest meaningful targeted validation for its
  changed contract, including policy, authorization, and security slices.
  Expand as applicable to affected-domain, route/API contract and manifest,
  deterministic generation, fault-injection, representative browser, static,
  link, and source-pointer checks.
- Before candidate freeze, maintain a requirement-to-executed-assertion matrix
  for every accepted behavior requirement in the slice. Each requirement names
  the exact executed assertion and result, or an explicit justified deferral
  with owner and authority. Where relevant, the matrix covers event ownership
  and topology, native-interaction ordering, mobile containment, lazy
  activation, selected-section and actor edge cases, and harness time or shim
  behavior. A test name, visual observation, or broad-suite pass without the
  asserted behavior and execution result is not a completed matrix entry.
- A pure behavior-parity transport slice additionally proves behavioral parity
  and Git commit/tree/blob/mode identity for the moved boundary. A passing broad
  suite does not replace missing focused parity assertions.
- Freeze each slice before independent verification. Record the exact commands
  and results, and return production or tested-boundary repairs to the writer
  for a new freeze and affected targeted reruns.
- A change to `create_app`, `register_api`, dependency wiring, recovery hooks,
  registrars, or route composition must run the maintained
  `composition-contract` lane before freeze. New or modified static contracts
  locate named registrars or handlers and assert route-local adjacency,
  dependency order, wrapper counts, and manifests. Do not use whole-function
  body lengths, unrelated-statement parity, or absolute statement indexes as
  current-composition contracts.

### 2. Promotion To A Domain-Integration Gate

- An individual verified slice does not require a complete regression suite
  merely because it changes policy, security, behavior, shared fixtures,
  composition, test infrastructure, or migrations.
- Shared fixtures, application composition, test infrastructure, and migrations
  expand targeted coverage immediately and promote the next assembled frozen
  domain candidate to an integration gate. Record that promotion in the
  handoff instead of silently deferring it.
- Keep promotion closed while any known candidate-relevant tracked test is
  failing, stale, or unreconciled. Classify parent-baseline and harness
  evidence, then repair or rewrite the test, or explicitly exclude it with the
  required authority and recorded rationale, before complete-suite promotion.
  A failure on the parent candidate is evidence for classification, not
  permission to advance the child candidate.
- After the independently approved slices for a bounded domain are assembled,
  freeze the domain-integration candidate. One independent verifier runs one
  complete regression suite against that exact candidate before it advances.
  Use the repository wrapper without a PTY:

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action candidate-gate
  ```

- `candidate-gate` fails before acquiring the complete-validation lock unless
  the resolved interpreter exactly matches `.python-version`, every applicable
  installed development dependency matches `requirements-dev.lock`, and
  dependency consistency succeeds. Use `pip check` when pip is installed and
  the equivalent installed-metadata check for intentionally pipless validation
  environments. Do not substitute a newer shared virtual environment.
- The decisive candidate gate is the union of a Linux/amd64 Docker lane and an
  exact `windows_host` pytest lane. The digest-pinned cached Linux image includes
  a staged snapshot of Git's cached-plus-nonignored-untracked current worktree
  bytes and installs `requirements-dev.lock` with hashes, Git, Playwright
  Chromium, and its Linux dependencies. The stable staged context excludes
  ignored material before Docker receives it; a deterministic path/state/mode/
  size/SHA-256 manifest is mounted read-only and must exactly match `/workspace`
  before any other Linux validation. The lock-hash tag is only a cache key; the
  gate validates and prints the exact built image ID, OS, and architecture as
  candidate evidence before running the environment check, dependency
  consistency, version-reporting Chromium launch smoke, and pytest with browser
  capability skips made fatal. Linux pytest basetemp and cache stay under the
  `/workspace/.local` tmpfs; process temp variables resolve to the separately
  writable `/tmp` tmpfs. The gate also emits a stable image-receipt SHA over
  candidate inputs, pinned base/platform, ordered root-filesystem layer diff
  IDs, and normalized execution configuration while recording volatile image
  identity, creation time, and provenance only as diagnostics.
  The host lane uses canonical Windows Python and an explicit marked file list,
  without strict browser mode or any Playwright probe, avoiding repository-wide
  browser collection under SAC. Both lanes run after ordinary failures and
  their exit statuses aggregate.
- Record the candidate commit and tree, runtime/test subtree identities, exact
  command, pass count, skips, xfails, failures, and environmental
  classifications. A runtime or test change after the freeze invalidates that
  complete-suite evidence and creates a new domain-integration candidate.

### 3. Phase And Release Evidence Reuse

- A phase or release boundary reuses the latest qualifying independent
  domain-integration complete-suite evidence when the boundary has the same
  runtime and test trees and no unresolved application-relevant ambiguity.
- Repeat the complete suite at a phase or release boundary only when its
  runtime or test tree differs from that qualifying candidate, or when an
  unresolved runner, environment, integration, or product ambiguity could
  conceal an application failure.
- Documentation, policy metadata, generated contract metadata, or Git history
  differences alone do not force another complete run when targeted checks
  pass and runtime/test identity and application behavior remain unambiguous.

### 4. Exact Integration And Targeted Repair

- The default local integration is a fast-forward of the independently
  approved commit into a clean durable phase target. Record the durable
  pre-integration SHA as the rollback point.
- Prove that the integrated runtime/test trees and relevant generated artifacts
  are identical to the verified candidate. For an exact integration, run
  focused cross-domain smoke, contract/manifest or generator, and static checks;
  do not repeat the complete suite.
- Repair targeted failures and rerun the failing and affected matrices. Defer
  broad regression to the next domain-integration gate unless a repair changes
  an already-frozen domain-integration candidate; that change requires a new
  freeze and independent complete-suite result.
- If integration or conflict resolution changes runtime or tests, stop treating
  it as identity-preserving integration and promote the resulting assembled
  tree to a new domain-integration candidate. If only non-executable content
  changes, prove runtime/test identity and run the applicable focused checks.

### 5. Harness, Environment, And Windows Classification Rules

- A command-syntax mistake, launcher failure, evidence-root error,
  runner-presentation issue, task/tool outage, capacity pressure, process/port
  contention, path problem, or other pre-candidate harness failure is
  nonterminal. Preserve its command and result, correct the smallest harness
  boundary, and rerun the same exact candidate automatically. Keep one active
  attempt at a time and resolve ambiguous task/process state before retrying.
  Do not request user approval or issue terminal `HOLD` for routine recovery.
- An environment mismatch keeps the affected validation gate closed while the
  Orchestrator uses an already authorized matching environment, routes an
  in-scope repair, or monitors `WAITING`. If changing the environment itself is
  separately gated, complete other work and report `READY_FOR_AUTHORIZATION`;
  do not terminate the phase.
- Never run competing complete suites concurrently, and run decisive complete
  suites without a PTY. Complete-suite evidence must come from an uncontended
  validation lane. `local.ps1 -Action candidate-gate`, `local.ps1 -Action test`,
  and `local.ps1 -Action check` hold the repository-wide complete-validation
  lock in the Git common directory; a physical short-root parent retains that
  lock while its guarded child process runs.
- For decisive domain, phase, and release verification, use the maintained
  composite `candidate-gate` by default. Physical short-root controls remain
  available for focused Windows diagnosis: add `-PhysicalShortRoot` to
  `test-focused`, `test-restore`, `test-browser`, `test-serial`,
  `composition-contract`, `test-path-boundary`, `test`, or `check`.
  `-ShortRootBase` may select an absolute physical base; otherwise the wrapper
  uses `PLAYER_WIKI_SHORT_ROOT_BASE` or a drive-root default. Do not substitute
  a symlink or junction, and do not represent a Windows-only complete run as
  the composite candidate result.
- A physical short-root pass classifies harness risk but does not prove the
  application's generated paths fit a supported production-length root. Every
  change to backup, restore, journal, tombstone, snapshot, or temporary
  publication names must add or update a `path_boundary` regression and run:

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action test-path-boundary -PhysicalShortRoot
  ```

  The regression records the supported boundary and proves both the generated
  name budget and the relevant recovery validation. A short-root result must
  not erase a failing boundary-length control.
- Prove and report that the short-root checkout is hash-identical to the frozen
  candidate before using its result. A rerun used to classify a harness failure
  must preserve that identity and report the original failure, the suspected
  environmental cause, the control used, and the rerun result.
- Classify runner or terminal-presentation failures separately from application
  failures. Preserve the command, exit state, and available raw output; if the
  presentation is incomplete or ambiguous, rerun the exact frozen candidate in
  the maintained non-PTY lane before accepting or rejecting the evidence. Do
  not convert a nonzero test result into a presentation issue, or a presentation
  issue into an application regression, without concrete evidence.
- Do not silently normalize line endings, permissions, paths, fixtures,
  generated artifacts, or file contents while preparing a verification copy.
  Commit, tree, index, tracked blob, and tracked-mode identity are authoritative
  for normalized text. Files marked `text: unset` also receive a raw-byte
  comparison. Any unexplained identity change makes the run evidence for a
  different tree.
- The helper refuses a dirty source, including nonignored untracked files, and
  retains every failed checkout for diagnosis. Successful checkouts are also
  retained unless the same invocation receives `-RemoveShortRootOnSuccess`;
  that switch removes only its generated detached, clean, commit-identical
  worktree after stringent path and common-directory verification. It never
  performs historical worktree cleanup.
- Use `-RemoveShortRootOnSuccess` by default for successful noncanonical runs.
  Retain a successful root only for a named unique evidence or cache reason and
  record its owner and disposal gate. Retain every failed or ambiguous root
  until its material implication is classified.

## Documentation Gate

- Update affected `docs/current-state/` documents and the local roadmap only
  after the behavior is verified on the integration branch.
- Give the resulting documentation diff to an independent verifier before
  integrating the tracked documentation slice.
- The lightweight review uses a structured claim inventory rather than prose
  sampling. Check the current schema version and owning migration, every
  registered recovery/startup/health-bypass hook, authoritative registry or
  container counts, owned-versus-unmanaged resource wording, source and test
  pointers, relative links, and whether each claim is local, pushed, deployed,
  or live. Prefer source-derived names and manifests over hand-maintained
  numeric counts.
- State explicitly whether a documented contract exists only on the
  integration branch or has also reached `main`, a remote, deployment, or live
  data. Evidence at one boundary does not imply the others.
- Keep future or unmerged behavior in the local roadmap. Do not describe it as
  shipped current state or check later-phase gates before their evidence exists.

## Phase Completion Discovery, Evidence, And Retention

Before freezing a phase-final assembled candidate, run one read-only remaining-
boundary sweep against the roadmap, current-state docs, supported CLI/API
commands, migration ledger, and explicitly deferred mutation or cleanup paths.
Classify every result as closed, intentionally deferred, separately authorized,
or a required bounded slice. Do not discover a required mutation lane only
after release-readiness begins.

Before phase-final qualification or documentation freeze, checkpoint the exact
target `main` state locally and at the named remote against the phase base and
candidate. Classify every new target delta and choose the early reconciliation
path before final evidence is frozen. This read-only drift checkpoint grants no
integration, merge, fetch-side mutation, push, or conflict-resolution authority;
any required mutation follows its existing gate and produces a newly qualified
identity when applicable.

Keep one replace-only lifecycle package with material transition timestamps,
accepted and rejected identities, validation commands/results, environment
manifests, user gates, tool outages, and retained-root inventory. Do not append
transient heartbeat commentary as lifecycle history.

Failed or diagnostically valuable roots remain inert until their material
implications are classified and durably summarized. The raw root is not itself
durable evidence and is default-disposable after the ledger captures exact
identity, command/result, classification, and every unresolved implication. At
phase close, produce a comprehensive ownership manifest for every program-owned
worktree, branch, runner/cache/temp/screenshot root, and deploy residual with
exact path or ref, purpose, owner, unique-work state, retention state, cleanup
authority, and disposition. Once a user authorizes formal close with the sealed
automated disposal policy, every item that still passes its independent proof
is disposed after successful release; no recursive, parent, glob, force, or
newly discovered cleanup is inferred.

Before deleting final raw evidence or a completed phase lane, use
`local.ps1 -Action phase-closeout-anchor-render` with explicit registered
source, canonical, and ledger worktrees, their configured refs, the frozen
accepted validation identity, and an independently accepted sanitized-
lifecycle classification bound to the exact source bytes. The tool does not
infer that Markdown is safe. The classification is a canonical self-sealed
`campaign-player-wiki.sanitized-lifecycle-classification` version 1 receipt of
kind `SANITIZED_LIFECYCLE_ACCEPTANCE`; it records `ACCEPT`,
`SANITIZED_LIFECYCLE`, the repo-relative source path/byte count/SHA-256, the
review UTC, and the independent reviewer identifier, with no raw contents or
private fields. Independently review the sealed plan, then use
`phase-closeout-anchor-write` under the common validation lock and
`phase-closeout-anchor-verify` read-only. The write copies the canonical
lifecycle/postmortem bytes first and proves byte identity before it writes or
replaces exactly one row in the tracked sanitized
[phase closeout evidence-anchor ledger](../contracts/phase-closeout-evidence-anchors.md).
If the ledger write fails, retain the correct canonical copy and route the
sealed `RECOVERING` receipt; do not roll it back or delete the source.

The anchor automation is a local evidence-finalization utility only. It never
discovers records, decides sanitization, stages, commits, switches refs,
fetches, pushes, deploys, deletes evidence, or grants cleanup authority. Its
receipts and ledger row contain only repository-relative paths and sanitized
identity metadata. After final postmortem changes, refresh the anchor in a
bounded docs-only slice; that commit is an evidence attestation, not a claim
that runtime was redeployed.

Tracked anchor rows and their explanatory ledger prose use timeless factual
wording. They must not describe their own current bytes as pending verification,
commit, or push; Git disposition for the anchor change belongs in the verified
handoff. Validate row structure and prospective-state wording without reading
the ignored lifecycle records.

Release packaging must exclude `.git`, ignored validation state, private
campaign content, databases, and evidence roots. Explicit build metadata binds
the deployed artifact to Git identity; repository metadata is not part of the
container build context.

## Integration And Rollback

Before integration, record the integration branch's pre-integration SHA. The
verified slice commit must not be rebased, amended, squashed, or otherwise
rewritten after verification. Fast-forward the exact verified descendant into
the clean integration branch by default so the pre-integration SHA and verified
commit form one clear rollback boundary. If a fast-forward is impossible, keep
the integration gate closed and reclassify it: a separately bounded local
assembly role may create a merge commit and resolve conflicts already decided
by tracked behavior authority. That creates a new tree, so continue through the
runtime/test identity and candidate-promotion rules above before treating it as
verified. Ask the user only when conflict resolution exposes a genuine product
decision; do not request new approval for routine local assembly already
authorized by this workflow.

The integration agent reviews the final diff and evidence before merging. A
local slice-to-integration merge is permitted only after independent
verification. Pushing, opening a pull request, merging to `main`, deploying,
or performing a live-data operation remains an explicit user gate under
[Authority lanes](authority-lanes.md).

## Formal Close Publication Gate

Slice-to-durable integration remains with the Phase Orchestrator. Once the
phase-final candidate and factual handoff are independently accepted, the
Orchestrator delegates exactly one bounded Publisher subagent; it does not
create another persistent Formal Close Orchestrator.

The Publisher receives the exact accepted commit/tree, qualifying suite and
focused evidence pointers, source and target refs, expected remote target SHA,
rollback point, named Fly app/environment, read-only live test plan, and sealed
cleanup plan. After the readiness preflight is green and the user has granted
the named capabilities, execute serially:

1. revalidate the accepted identity, evidence, remote refs, exclusive target,
   and all preflight artifacts;
2. push the exact accepted source and reread the remote refs;
3. fast-forward the named clean target, run the required focused
   post-integration checks, push it, and verify local and remote identity;
4. prove the deploy source is that exact clean pushed target, then deploy only
   to the named environment and bind its release identity to Git;
5. run only the authorized read-only live plan, including a required browser
   gate when available under `agent-roles.md`; and
6. after every named Git, deploy, and live gate is green, invoke only the
   sealed-plan disposer for eligible local items. Remote-ref actions remain
   separately authorized Publisher transport actions.

Any drift, conflict, unexplained check failure, deployment or live failure,
unavailable required browser, or cleanup ambiguity closes the affected
Publisher action and returns control to the Orchestrator as `RECOVERING`,
monitored `WAITING`, or `SAFETY_STOP` as applicable. The Publisher does not
improvise repair, rollback, broader cleanup, retrospective, or next-phase work.
Only an unresolved product decision or a genuine safety issue stops the
program; routine operational failures are classified and routed through a new
bounded recovery gate.
