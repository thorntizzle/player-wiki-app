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
  inside the freeze, and L1 plus affected L2 checks.
- **Verifier** is independent from implementation and owns candidate-level L3
  and applicable L4 checks, evidence audit, and acceptance or Frozen Failure
  Inventory. It does not repair the candidate.
- **Scribe** records assigned verified post-sweep notes.
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
configuration, environment, fixture, and relevant-input identity; L1/L2 and
L3/L4 including browser ownership; checkpoint and intended/achieved gate delta;
cumulative controls; operator gates; stop conditions; and next owner/action.
Restate only when one of those boundaries changes.

## Handoffs

- Scout to Orchestrator: complete brief, decisions/deferrals, ownership, identity, validation, and non-goals.
- Orchestrator to Implementer: approved freeze excerpts/headings, lane ownership, authority, dependencies, and L1/L2 checks.
- Implementer to Orchestrator: exact diff/commit identity, decisions, checks, risks, and integration readiness.
- Orchestrator to Verifier: immutable candidate, full L3/L4 matrix, environment, and expected evidence.
- Verifier to Orchestrator: acceptance or complete Frozen Failure Inventory with root causes and dependency-skips.

## Continuation And Stops

Routine tool, test, environment, worker, integration, or evidence failures are
classified and returned to the Orchestrator. Stop the affected action for a
genuine product/policy decision, safety issue, invalid authority, overlapping
writer, protected-data risk, or separately gated side effect. Failure of the
second repair candidate requires operator review. Role titles never grant Git,
deploy, live-data, credential, publication, or destructive authority.

During a Verifier sweep, continue every unaffected check after an ordinary
failure. Stop early only for safety or an invalid candidate/environment that
makes dependent results meaningless. Classify every not-run check as blocked,
invalid, or dependency-skipped in the Frozen Failure Inventory.
