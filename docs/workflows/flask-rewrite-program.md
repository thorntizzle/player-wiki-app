# Flask Rewrite Program Workflow

Last reviewed: 2026-07-12

Status: accepted Flask rewrite workflow authority

This document adds program-specific branch, review, evidence, and rollback
rules to the repository workflow. Use the universal role, authority, context,
and worktree rules in [AGENTS.md](../../AGENTS.md),
[Agent roles](agent-roles.md), [Authority lanes](authority-lanes.md), and
[Worktrees](worktrees.md) instead of restating them here.

## Branch And Worktree Contract

- The permanent integration target is `codex/flask-rewrite-integration`.
- Name slice branches `codex/flask-rewrite-pNN-<bounded-slug>`.
- Base every slice on the then-current integration SHA and record that SHA in
  the slice handoff.
- Give every slice an isolated worktree and one active writer.
- Never base new work on the frozen `rewrite/typescript-backend` or
  `rewrite/ts-phase3-integration` references.

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
- complete-suite evidence at required final-candidate and milestone gates;
- residual risks and untested boundaries; and
- documentation accounting, including why no update was needed when none was
  made.

## Validation Cadence

### 1. Focused Development And Repair Gates

- During implementation, run the smallest focused tests for the changed
  contract. Expand to the focused domain, route/API contract, static, or
  representative browser gates that the slice actually exercises.
- Freeze the candidate before independent verification. If a repair changes
  production code or the tested behavior boundary, return it to the writer,
  refreeze it, and rerun the affected focused gates before final-candidate
  verification.
- Record exact commands and results. A passing broad suite does not replace a
  missing focused assertion for the contract being changed.

### 2. One Independent Complete Final-Candidate Gate

- Every behavioral slice receives one independent complete regression run
  against its final frozen candidate before the verifier returns `COMMIT`.
  The verifier must not rely on an earlier implementation snapshot or a run
  made before the last behavior-affecting repair.
- Record the candidate commit when one exists, plus a deterministic tracked-tree
  content hash for the frozen candidate and tested checkout, the complete
  command, pass count, skips, xfails, failures, and any environmental
  classification. The hashes must prove that the reported run exercised the
  candidate being approved.
- A repair that changes production code or the tested behavior boundary starts
  a new final-candidate gate. Rerun the affected focused checks and one complete
  regression suite on the refrozen candidate.

### 3. Hash-Identical Fast-Forward Integration

- The default local integration is a fast-forward of the independently
  approved commit into a clean durable phase target. Record the durable
  pre-integration SHA as the rollback point.
- Prove with tracked-tree content hashes that the verified source tree,
  committed slice tree, and durable post-integration tree are identical. When
  that proof holds, run focused post-integration smoke, contract/manifest or
  generator, and static checks; do not repeat the complete suite by default.
- Focused-only post-integration validation is evidence reuse, not a weaker
  candidate gate: the independent complete result remains attached to the
  identical tree that reached the durable target.

### 4. Mandatory Complete Post-Integration Reruns

Repeat the complete suite on the integrated tree when any of these conditions
applies:

- the committed or integrated tree differs from the independently tested
  candidate;
- integration required a merge commit, conflict resolution, or any manual
  content change;
- generated artifacts changed after the tested snapshot;
- shared fixtures, application composition, migrations, validation helpers, or
  test infrastructure changed;
- the candidate run left an unresolved environmental or harness ambiguity; or
- the slice is a logical domain milestone or phase close-out.

Do not waive the rerun because the differing content appears mechanical. A new
tree requires its own evidence unless exact hash identity is restored and
proved.

### 5. Low-Risk Metadata And Documentation Slices

- Policy-only, manifest-only, metadata-only, and documentation-only slices use
  exact diff review plus the focused contract, deterministic generation, link,
  source-pointer, and static checks that apply to their files.
- These non-behavioral slices do not require a complete regression suite unless
  evidence shows runtime risk, they alter executable test infrastructure, or
  one of the mandatory-rerun conditions applies.

### 6. Durable Milestone Gates

- Run one complete regression suite from a clean durable branch at each logical
  domain milestone and every phase boundary. Record the durable commit/tree
  hash, exact command, and full result accounting.
- Completion of the Phase 3 Systems transport cluster is a logical domain
  milestone and requires this durable-branch complete gate even when each
  individual slice already has independent final-candidate evidence.
- Milestone evidence is cumulative confirmation of the integrated domain or
  phase. It does not erase slice-specific focused or fault-injection evidence.

### 7. Harness And Windows Classification Rules

- Never run competing complete suites concurrently. Complete-suite evidence
  must come from an uncontended validation lane.
- For decisive Windows verification, use the maintained physical short-root
  controls when the normal worktree hits the known path-length harness limit.
  Do not substitute a symlink or junction when the control requires a physical
  short root.
- Prove and report that the short-root checkout is hash-identical to the frozen
  candidate before using its result. A rerun used to classify a harness failure
  must preserve that identity and report the original failure, the suspected
  environmental cause, the control used, and the rerun result.
- Do not silently normalize line endings, permissions, paths, fixtures,
  generated artifacts, or file contents while preparing a verification copy.
  Any such change breaks hash identity and makes the run evidence for a
  different tree.

## Milestone Documentation Gate

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
resolution create a new tree and require the mandatory complete post-integration
rerun above.

The integration agent reviews the final diff and evidence before merging. A
local slice-to-integration merge is permitted only after independent
verification. Pushing, opening a pull request, merging to `main`, deploying,
or performing a live-data operation remains an explicit user gate under
[Authority lanes](authority-lanes.md).
