# Flask Rewrite Program Workflow

Last reviewed: 2026-07-18

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
- After a phase is independently accepted, integrated to `main`, pushed,
  deployed when authorized, and closed, retire its temporary slice and phase
  branches after proving that no unique or unreviewed work remains. The next
  phase starts from the resulting accepted `main`, not from the retired phase
  branch.

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
  made.

## Task-Local Browser Evidence

Browser attachment is task-local and must not be assumed to propagate from an
Orchestrator task to an independent Verifier subagent. For a required
real-browser gate, prefer giving the independent Verifier a browser attached to
its own task.

If task isolation prevents that and the fallback is explicitly authorized, the
parent Orchestrator may operate its task-local browser only under the canonical
Verifier's predefined script and assertions. The Orchestrator may perform only
bounded follow-up observations that the Verifier directs; it may not improvise,
edit the candidate, or decide acceptance. The canonical Verifier audits the
captured evidence and cleanup and alone issues the explicit `ACCEPT` or
`REJECT`.

Record this evidence as parent-Orchestrator-operated and Verifier-directed,
never as independently executed browser work. Do not replace an explicitly
required real-browser gate with a standalone browser, Flask test client, or
other test client unless separate authority permits the substitution.

## Validation Cadence

### 1. Targeted Slice Gates

- Every slice receives the smallest meaningful targeted validation for its
  changed contract, including policy, authorization, and security slices.
  Expand as applicable to affected-domain, route/API contract and manifest,
  deterministic generation, fault-injection, representative browser, static,
  link, and source-pointer checks.
- A pure behavior-parity transport slice additionally proves behavioral parity
  and Git commit/tree/blob/mode identity for the moved boundary. A passing broad
  suite does not replace missing focused parity assertions.
- Freeze each slice before independent verification. Record the exact commands
  and results, and return production or tested-boundary repairs to the writer
  for a new freeze and affected targeted reruns.

### 2. Promotion To A Domain-Integration Gate

- An individual verified slice does not require a complete regression suite
  merely because it changes policy, security, behavior, shared fixtures,
  composition, test infrastructure, or migrations.
- Shared fixtures, application composition, test infrastructure, and migrations
  expand targeted coverage immediately and promote the next assembled frozen
  domain candidate to an integration gate. Record that promotion in the
  handoff instead of silently deferring it.
- After the independently approved slices for a bounded domain are assembled,
  freeze the domain-integration candidate. One independent verifier runs one
  complete regression suite against that exact candidate before it advances.
  Use the repository wrapper without a PTY:

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\local.ps1 -Action test -PhysicalShortRoot
  ```

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

### 5. Harness And Windows Classification Rules

- Never run competing complete suites concurrently, and run decisive complete
  suites without a PTY. Complete-suite evidence must come from an uncontended
  validation lane. `local.ps1 -Action test` and
  `local.ps1 -Action check` hold the repository-wide complete-validation lock
  in the Git common directory; a physical short-root parent retains that lock
  while its guarded child process runs.
- For decisive Windows verification, use the maintained physical short-root
  controls when the normal worktree hits the known path-length harness limit:
  add `-PhysicalShortRoot` to `test-focused`, `test-restore`, `test-browser`,
  `test-serial`, `test`, or `check`. `-ShortRootBase` may select an absolute
  physical base; otherwise the wrapper uses `PLAYER_WIKI_SHORT_ROOT_BASE` or a
  drive-root default. Do not substitute a symlink or junction.
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

## Documentation Gate

- Update affected `docs/current-state/` documents and the local roadmap only
  after the behavior is verified on the integration branch.
- Give the resulting documentation diff to an independent verifier before
  integrating the tracked documentation slice.
- State explicitly whether a documented contract exists only on the
  integration branch or has also reached `main`, a remote, deployment, or live
  data. Evidence at one boundary does not imply the others.
- Keep future or unmerged behavior in the local roadmap. Do not describe it as
  shipped current state or check later-phase gates before their evidence exists.

## Integration And Rollback

Before integration, record the integration branch's pre-integration SHA. The
verified slice commit must not be rebased, amended, squashed, or otherwise
rewritten after verification. Fast-forward the exact verified descendant into
the clean integration branch by default so the pre-integration SHA and verified
commit form one clear rollback boundary. If a fast-forward is impossible, stop
and reclassify the integration: an authorized merge commit and any conflict
resolution create a new tree. Apply the runtime/test identity and candidate
promotion rules above before treating that tree as verified.

The integration agent reviews the final diff and evidence before merging. A
local slice-to-integration merge is permitted only after independent
verification. Pushing, opening a pull request, merging to `main`, deploying,
or performing a live-data operation remains an explicit user gate under
[Authority lanes](authority-lanes.md).
