# Campaign Player Wiki Agent Router

Status: accepted workflow authority

Start here, then load only the narrowest workflow or product reference needed.
These files govern agent behavior. Shipped facts belong in
`docs/current-state/`; source/tests own implementation behavior; unresolved
work belongs in `.local/roadmaps/` and never overrides shipped authority.

## Mandatory Repository Preflight

Before a tracked edit or implementation validation:

1. Run `git status --short --branch` and `git worktree list --porcelain` from
   the confirmed repository root.
2. Classify the change as documentation-only or candidate-producing.
3. Classify program, cycle, wave, role, lane, ownership, and authority with
   [Agent Roles](docs/workflows/agent-roles.md).
4. For candidate-producing work, prove the exact toolchain and relevant inputs
   under [Repo Guardrails](docs/workflows/repo-guardrails.md).
5. State a Role Lock at each program/cycle boundary, implementation-wave
   boundary, or ownership/authority change.

Use the [proportionate delivery route](docs/workflows/agent-operating-model.md#proportionate-delivery):
documentation, compact bounded local tooling, or the canonical product
lifecycle. Executable helpers are never documentation-only. Compact tooling
retains exact independent acceptance and all applicable cumulative controls.

The main checkout is the sole active worktree by default. Confirm exclusive
write ownership and keep task deltas separable. Additional active worktrees
require explicit operator authorization for a named need; use read-only review
without another checkout when possible. Do not leave completed lanes active.

Before assigning or resuming a lane, apply
[Instruction Delivery And Reuse](docs/workflows/worktrees.md#instruction-delivery-and-reuse):
confirm its current governance explicitly, separately from frozen authority.
Workflow closeout includes delivery to active consumers or a deferred-reuse note.

## Context And Routing Safeguards

- Use the narrowest CPW specialist skill first.
- Route first, search second, and read the smallest authoritative source.
- Open `docs/current-state/INDEX.md` only when shipped behavior matters, then
  open the owning domain file. Open the skill repo map only for routing,
  storage-boundary, or shared-architecture uncertainty. Open `.local/roadmaps/`
  only for unresolved or explicitly named future work.
- Delegate worker-shaped tasks with `fork_turns="none"` and one current
  replace-only capsule; 300-500 words is a target, not a fill quota.
  An explicitly approved
  full-history fork receives no capsule.
- Parse the full worktree inventory but report only the current checkout,
  integration lane, active conflicts, aggregate retained count, and retained
  entries relevant to ownership or cleanup.
- Keep raw logs and private/local evidence behind concise pointers.

## Documentation-Only Route

A change is documentation-only only when every tracked edit is human-readable
documentation and no executable/generated input, source, test, fixture,
schema, migration, dependency/lock, CI, deployment, or runtime configuration
changes.

- Ordinary documentation receives author checks: owned diff/status,
  `git diff --check`, links/anchors, formatting, and factual consistency.
- Canonical workflow, plan, policy, requirements, migration, or operator-
  runbook documentation also receives one focused independent semantic review.
- Documentation-only work does not manufacture implementation lifecycle IDs or
  run unrelated executable suites. A change touching protected/live data is
  never documentation-only; prove only documentation tools used by scoped checks.

## Canonical Implementation Lifecycle

```text
Stable Program ID and cumulative budgets
  -> Initial Cycle
     -> Scout pass -> Initial Requirements Brief
     -> Orchestrator-approved Initial Requirements Freeze
     -> Implementation Wave
     -> Assembled Candidate Freeze
     -> Independent Precommit Adversarial Review
     -> acceptance or Frozen Failure Inventory
  -> Repair Cycle 1 follows the same edges
  -> Repair Cycle 2 follows the same edges; failure requires operator review
```

The [Agent Operating Model](docs/workflows/agent-operating-model.md) owns the
lifecycle, discovery/change control, review coverage/reuse, and bounded
evidence rules. Each product candidate-producing cycle has one accountable Scout,
approved Requirements Freeze, mutable wave, assembled candidate, and
independent exact-candidate review. Discovery may iterate before approval;
ordinary technical feedback inside the freeze does not create another cycle.
The Verifier accounts for every changed path and affected entry-to-side-effect
path, using fresh inspection or explicitly valid prior coverage. Complete
release review is required before protected integration; an exact review may
satisfy both candidate and release coverage without a duplicate pass.
Acceptance requires no unresolved blocking finding. Failed candidates retain
their verdict and Frozen Failure Inventory; repairs follow the next approved
cycle. Compact local tooling uses the operating model's shorter route. Establish
critical execution capabilities and interface compatibility before assembling
an operational packet; use bounded permitted diagnostics when inspection is
insufficient. Other L2 checks are optional; L4 needs separate authority. Retired
automated suites and dedicated gate commands remain unavailable.

Default cumulative limit: one initial candidate plus two repair candidates.
Renaming tasks, chats, branches, lanes, batches, waves, or cycles never resets
it. A change to frozen product bytes or relevant semantic inputs after
assembled freeze creates a repair candidate. Source, diagnostic/evidence, and
operational identities are distinguished in
[Repo Guardrails](docs/workflows/repo-guardrails.md#identity-and-evidence-changes).
An administrative pointer correction is not permission to alter a frozen
artifact or cure failed evidence. Unchanged-candidate environment reruns remain
separately bounded and require a changed diagnosis and preserved relevant inputs.

Workflow amendments take effect prospectively after their authorized
documentation review. An already frozen candidate retains its exact bound
authority revision and historical verdicts. A proposed policy file is not
authority merely because it appears in a candidate. Direct matching owner
decisions retain their stated scope; no lower artifact or launcher expands it.

Simplification changes future work only. An existing stopped/frozen packet needs
an explicit forward disposition identifying replaced controls, retained outcome
guarantees, exact successor/review scope and unchanged consumption before it can
use a new route. Workflow approval alone grants no helper candidate, retry,
protected operation or tool-policy workaround for that packet.

There is no persistent Program Overseer or heartbeat layer. The current task's
Orchestrator owns the bounded program and delegates Scouts, Implementers, and
Verifiers directly under the canonical lifecycle.

## Domain Routes

- Characters: `$campaign-player-wiki-characters`
- Combat, Session, DM Content, polling, and rerender stability: `$campaign-player-wiki-live`
- Systems sources, imports, rules, and rendering: `$campaign-player-wiki-systems`
- Player-safe wiki and session publication: `$campaign-player-wiki-publishing`
- Runtime, validation, Git, Fly, backup, auth, and SQLite: `$campaign-player-wiki-ops-deploy`
- Feedback capture without implementation: `$campaign-player-wiki-feedback-logger`
- Broad or mixed app work: `$campaign-player-wiki-app`
- GM/canon vault source work: `$campaign-wiki-vault`

## Workflow Routes

- Roles, locks, handoffs, and verification ownership:
  [agent-roles.md](docs/workflows/agent-roles.md)
- Program state, context, freezes, budgets, and planning:
  [agent-operating-model.md](docs/workflows/agent-operating-model.md)
- Scope, data safety, toolchain, validation, side effects, and Git:
  [repo-guardrails.md](docs/workflows/repo-guardrails.md)
- Wave and lane assignments: [worker-delegation.md](docs/workflows/worker-delegation.md)
- Worktree lanes, candidate identity, integration, and cleanup:
  [worktrees.md](docs/workflows/worktrees.md)

## Repo And Data Boundaries

- The current Git root is the app root; never assume a worktree parent.
- Keep live SQLite files, campaign/vault content, secrets, personal paths,
  private identifiers, proprietary source data, backups, and protected evidence
  out of tracked history.
- Keep `campaigns/{campaign-slug}/` and live/private campaign evidence untracked.
- Use repo-root `./local.ps1` or the configured shared environment; do not rely
  on bare `python` from `PATH`.
- Use a focused disposable local drill or forensic command only to resolve a
  concrete uncertainty. Automated suites and a real browser are optional
  diagnostic tools, not routine candidate gates.

## Operator Gates

Explicit matching authority is required for commit/push, protected-target
integration, PR, merge, deploy, live content/data/credential writes,
destructive operations, unusual branch/remote changes, and unresolved product,
architecture, compatibility, privacy, or security-policy decisions. A code
request does not imply deployment; a content task does not imply publication.

## Close-Out

Maintain affected current-state and skill guidance as part of the change under
[Current-State And Skill Maintenance](docs/workflows/agent-operating-model.md#current-state-and-skill-maintenance).

Report role/authority; stable IDs when applicable; branch/worktree and exact
candidate; changed files; validation/evidence and failure classification;
current-state/skill obligations; cumulative controls; commit/push/integration
state; external/live-data impact; operator gates; and retained lanes.
