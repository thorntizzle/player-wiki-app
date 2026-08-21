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

The main checkout is the integration lane by default. A lone writer may use it
only after confirming exclusive ownership; concurrent writers require distinct
worktrees.

## Context And Routing Safeguards

- Use the narrowest CPW specialist skill first.
- Route first, search second, and read the smallest authoritative source.
- Open `docs/current-state/INDEX.md` only when shipped behavior matters, then
  open the owning domain file. Open the skill repo map only for routing,
  storage-boundary, or shared-architecture uncertainty. Open `.local/roadmaps/`
  only for unresolved or explicitly named future work.
- Delegate worker-shaped tasks with `fork_turns="none"` and one current
  replace-only 300-500 word capsule by default. An explicitly approved
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
     -> Exhaustive Independent Verification Sweep
     -> acceptance or Frozen Failure Inventory
  -> Repair Cycle 1 follows the same edges
  -> Repair Cycle 2 follows the same edges; failure requires operator review
```

Each candidate-producing cycle has exactly one Scout pass, one approved
Requirements Freeze, one wave, one assembled candidate, and one exhaustive
sweep. Implementers own L1 and affected L2 checks; an independent Verifier owns
candidate-level L3 and applicable hosted/live L4 checks. A failed sweep closes
the cycle with a Frozen Failure Inventory. Repair starts only after the next
cycle's Scout brief and approved Repair Requirements Freeze.

Default cumulative limit: one initial candidate plus two repair candidates.
Renaming tasks, chats, branches, lanes, batches, waves, or cycles never resets
it. Any candidate byte change after candidate freeze or sweep start creates a
repair candidate. An unchanged-candidate environment rerun is separately
bounded, requires a changed diagnosis, and preserves every relevant test,
fixture, configuration, lock, toolchain, and target input.

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
- Prefer targeted Flask/Python tests. Use a real browser only when behavior
  requires it.

## Operator Gates

Explicit matching authority is required for commit/push, protected-target
integration, PR, merge, deploy, live content/data/credential writes,
destructive operations, unusual branch/remote changes, and unresolved product,
architecture, compatibility, privacy, or security-policy decisions. A code
request does not imply deployment; a content task does not imply publication.

## Close-Out

Report role/authority; stable IDs when applicable; branch/worktree and exact
candidate; changed files; validation/evidence and failure classification;
current-state/skill obligations; cumulative controls; commit/push/integration
state; external/live-data impact; operator gates; and retained lanes.
