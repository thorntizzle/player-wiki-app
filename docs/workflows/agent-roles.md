# Agent Roles

Status: accepted workflow reference

## Role Registry

- **Planner** proposes goals, program shape, evidence, lane structure, and gates.
- **Orchestrator** owns stable identities, freeze approval, lane assignment,
  integration, candidate freeze, verification coordination, cumulative
  controls, operator gates, and close-out. It resolves or escalates Scout
  choices; it does not invent substitute requirements.
- **Scout** owns the cycle's comprehensive targeted read-only discovery and
  Initial or Repair Requirements Brief. Bounded discovery can iterate before
  approval; use the operating model's distinction between technical learning
  and a genuine requirements change.
- **Implementer** owns one non-overlapping lane, ordinary technical decisions
  inside the freeze and L1 code/diff inspection. It resolves critical execution
  assumptions under the operating model; other focused L2 drills are optional.
- **Verifier** is independent from implementation and owns the exact-candidate
  precommit L3 adversarial code review, applicable authorized L4 checks,
  evidence audit, and acceptance or Frozen Failure Inventory. It owns coverage
  of every changed path and affected entry-to-side-effect path under the
  operating model's review/reuse rules, challenges applicable security,
  privacy, custody, compatibility, concurrency and failure assumptions, and
  records residual uncertainty. It does not repair the candidate, inherit an
  author's self-approval, or run a routine drill gate.
- **Scribe** records assigned verified post-review notes.
- **Auditor** owns read-only app, workflow, security, documentation, or
  context-health findings. Editing requires reclassification.

There is no persistent Program Overseer or Publisher role. External
publication/deployment is an authority gate owned by the current Orchestrator,
not a role capability. Existing `publisher-*`, `publisher-attached`, and
Publisher schema identifiers are legacy tool/protocol labels only; they grant
no role, independence, publication, deployment, rollback, or cleanup authority.

Ordinary documentation-only work may collapse roles except where a focused
independent semantic review is required. Product changes follow the canonical
lifecycle; bounded local tooling may use the operating model's compact route.
The Orchestrator may also perform discovery and implementation when ownership
permits. Product/helper candidate acceptance and required documentary semantic
review remain independent of authorship; ordinary documentation retains author
checks. A separate agent, handoff or document for every other role is not
required. The
[operating model](agent-operating-model.md) owns lifecycle and review rules;
this file owns role capabilities and independence.

## Role Lock

Record stable program/cycle/wave IDs; role; repository, branch, worktree, base,
integration target, and candidate; authority and exact side-effect target;
owned files/modules; Requirements Freeze; risk tier; exact toolchain,
configuration, environment, fixture, and relevant-input identity; L1 and
optional L2, L3/L4 review scope including browser ownership when relevant;
checkpoint and intended/achieved gate delta;
cumulative controls; operator gates; stop conditions; and next owner/action.
Restate only when one of those boundaries changes.
Reuse exact references for unchanged fields rather than copying the full
freeze or historical handoffs into each assignment. The Role Lock is not
restated at every tool call or ordinary technical clarification.

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
