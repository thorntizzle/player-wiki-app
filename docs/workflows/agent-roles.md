# Agent Roles

Status: accepted workflow reference

## Role Registry

- **Planner** proposes goals, program shape, evidence, lane structure, and gates.
- **Orchestrator** owns stable identities, freeze approval, lane assignment,
  integration, candidate freeze, verification coordination, cumulative
  controls, operator gates, and close-out. It resolves or escalates Scout
  choices; it does not invent substitute requirements.
- **Scout** performs one comprehensive targeted read-only pass per cycle and
  returns an Initial or Repair Requirements Brief.
- **Implementer** owns one non-overlapping lane, ordinary technical decisions
  inside the freeze and L1 code/diff inspection. L2 focused drills are optional
  for a concrete uncertainty.
- **Verifier** is independent from implementation and owns the exact-candidate
  precommit L3 adversarial code review, applicable authorized L4 checks,
  evidence audit, and acceptance or Frozen Failure Inventory. It reads every
  changed path, traces affected entry-to-side-effect paths, challenges
  applicable security, privacy, custody, compatibility, concurrency, and
  failure assumptions, and records residual uncertainty. It does not repair
  the candidate or run a routine drill gate.
- **Scribe** records assigned verified post-review notes.
- **Auditor** owns read-only app, workflow, security, documentation, or
  context-health findings. Editing requires reclassification.

There is no persistent Program Overseer or Publisher role. External
publication/deployment is an authority gate owned by the current Orchestrator,
not a role capability. Existing `publisher-*`, `publisher-attached`, and
Publisher schema identifiers are legacy tool/protocol labels only; they grant
no role, independence, publication, deployment, rollback, or cleanup authority.

Ordinary documentation-only work may collapse roles except where a focused
independent semantic review is required. Candidate-producing work follows the
canonical lifecycle regardless of size; a tiny change may use an inline freeze
after its cycle's one Scout brief.

## Role Lock

Record stable program/cycle/wave IDs; role; repository, branch, worktree, base,
integration target, and candidate; authority and exact side-effect target;
owned files/modules; Requirements Freeze; risk tier; exact toolchain,
configuration, environment, fixture, and relevant-input identity; L1 and
optional L2, L3/L4 review scope including browser ownership when relevant;
checkpoint and intended/achieved gate delta;
cumulative controls; operator gates; stop conditions; and next owner/action.
Restate only when one of those boundaries changes.

## Handoffs

- Scout to Orchestrator: complete brief, decisions/deferrals, ownership, identity, validation, and non-goals.
- Orchestrator to Implementer: approved freeze excerpts/headings, lane ownership, authority, dependencies, L1 checks, and optional L2 uncertainty.
- Implementer to Orchestrator: exact diff/commit identity, decisions, checks, risks, and integration readiness.
- Orchestrator to Verifier: immutable precommit candidate, every changed path, affected entry-to-side-effect paths, applicable L3/L4 review scope, environment, and expected evidence.
- Verifier to Orchestrator: acceptance with residual uncertainty and no unresolved blocker, or complete Frozen Failure Inventory. Each actionable finding gives location, trigger, expected/actual behavior, impact/severity, evidence, root cause, and scope.

## Continuation And Stops

Routine tool, test, environment, worker, integration, or evidence failures are
classified and returned to the Orchestrator. Stop the affected action for a
genuine product/policy decision, safety issue, invalid authority, overlapping
writer, protected-data risk, or separately gated side effect. Failure of the
second repair candidate requires operator review. Role titles never grant Git,
deploy, live-data, credential, publication, or destructive authority.

During a Verifier review, continue every unaffected path after an ordinary
finding. Stop early only for safety or an invalid candidate/environment that
makes dependent analysis meaningless. Classify unreviewed paths as blocked,
invalid, or dependency-skipped in the Frozen Failure Inventory. Use a focused
drill or forensic command only to resolve a concrete uncertainty.
