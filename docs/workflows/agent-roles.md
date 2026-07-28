# Agent Roles

Last reviewed: 2026-07-28

Status: accepted workflow reference

## Roles

- **Orchestrator** owns classification, context routing, lane ownership,
  operator gates, durable slice integration, validation coordination,
  Publisher handoff, and final reporting.
- **Scout** owns read-only discovery, evidence, hazards, target files,
  constraints, validation suggestions, and a bounded implementation brief.
- **Implementer** owns changes in assigned files or modules and bounded
  validation. It does not expand requirements or side-effect authority.
- **Verifier** owns review, tests, failure classification, regression findings,
  and a commit/no-commit recommendation. It does not silently fix unrelated
  failures.
- **Publisher** is a bounded subagent that owns formal release transport after
  exact candidate acceptance: publish the accepted source branch, integrate and
  push the named target branch, deploy the exact clean pushed target, perform
  authorized read-only live verification, and execute only the eligible items
  in the accepted candidate's sealed automated disposal plan. It does not
  implement or repair product behavior,
  accept its own candidate, infer rollback authority, or start the next phase.
- **Scribe** owns verified workflow or current-state documentation and small
  handoff notes. It must not describe unverified behavior as shipped.
- **Auditor** owns read-only repo, app, security, workflow, documentation, or
  context-health findings. Editing requires a separately scoped hardening lane.

## Role-Lite Default

The full role sequence is optional. A small, isolated, low-risk change may
collapse Orchestrator, Implementer, and Verifier when ownership and acceptance
checks are clear, the checkout is safe, and no operator gate exists.

Split roles for concurrent work, architecture or security changes, live/data
operations, broad product changes, uncertain requirements, or worktree lanes.
Use a Scout before implementation when evidence, ownership, or acceptance
criteria are unclear.

Publisher never collapses into Implementer, Verifier, or Orchestrator. Spawn
exactly one Publisher subagent for an authorized formal close, after final
acceptance. The parent Orchestrator remains responsible for user decisions,
program completion, and any later retrospective.

## Role Lock

Before tracked edits or an external write, state:

- current role or collapsed roles;
- branch and worktree path;
- authority lane from `authority-lanes.md`;
- owned files or module cluster;
- expected validation;
- operator gates;
- stop conditions.

A Publisher lock additionally names the accepted commit/tree, source and target
refs, expected remote target SHA, deployment app/environment, read-only live
test plan, exact cleanup manifest, rollback boundary, and explicitly forbidden
actions.

After close-out, compaction, or scope expansion, return to Orchestrator and
classify the next slice again.

## Handoffs

- Use the replace-only capsule structure in `context-loading.md`. Handoffs are
  delta-first: exact identity, changed state, material evidence, remaining gate,
  and next owner/action. Reference stable workflow and product authority by
  path and heading instead of copying it.
- Do not carry raw logs, full roadmaps, repeated instruction kernels, transient
  commentary, or completed-step narration into the next role. Preserve detailed
  evidence in its owning task or file and pass only the pointer, hash, concise
  result, and unresolved implication.
- Scout to Implementer: evidence, requirements, owned files, hazards,
  non-goals, acceptance checks, and operator gates.
- Implementer to Verifier: changed files, behavior, validation run, risks, and
  documentation obligations.
- Verifier to Scribe: verified behavior and required workflow/current-state
  updates.
- Orchestrator to Publisher: exact accepted identity and evidence pointer,
  expected source/target/remote state, authorized publish/deploy/live-test
  actions, exact cleanup manifest, rollback boundary, and stop conditions.
- Publisher to Orchestrator: actual pushed refs, target integration identity,
  deploy artifact/release identity, live verification results, per-path cleanup
  disposition, retained lanes, and any stopped gate.
- Any role to Orchestrator: blockers, scope expansion, missing evidence,
  conflicting authority, or an operator gate.

The receiving role verifies Git/worktree identity and authority before
mutation, then loads only the cited source needed for the unresolved boundary.

## Program Continuation And Result Semantics

A role context, worker, task turn, candidate, or gate can end without ending the
program. The owning Orchestrator keeps the full objective active and routes the
next safe action.

- `RECOVERING`: an in-scope repair, retry, backoff, fresh role context, or
  revalidation can make progress. Preserve the failed attempt, classify it,
  name the next owner/action, and continue automatically.
- `WAITING`: required external capacity or state is temporarily unavailable.
  Keep monitoring and resume automatically. This is nonterminal.
- `REJECTED`: the exact candidate failed its acceptance contract. Return it to
  the smallest repair lane and require fresh independent verification; the
  program objective continues.
- `READY_FOR_AUTHORIZATION`: all possible in-scope work is complete and the
  next action is a separately gated side effect. This is not a failure.
- `DECISION_REQUIRED` and `SAFETY_STOP`: the only program-stopping states,
  reserved respectively for an unresolved product/architecture/compatibility/
  security-policy choice and a genuine safety issue.

Do not use terminal `HOLD`, `REJECT/HOLD`, or `blocked` for harness, command,
tool, task, capacity, evidence, environment, process/port, test, candidate,
verification, or integration failures.

Repeated routine failures require deeper diagnosis, a different bounded
recovery strategy, a fresh owner when independence requires it, or longer
backoff. Retry count alone never promotes them to `DECISION_REQUIRED`,
`SAFETY_STOP`, or a user-approval gate.

## Disposable Context Lifecycle

Role identity is immutable within a slice. A Scout cannot become that slice's
Implementer, and no writer can become its independent Verifier. Tool or worker
capacity pressure does not relax this rule.

At every Scout, Implementer, Verifier, and Scribe handoff:

1. confirm that the material result is durable in the accepted commit/tree,
   lifecycle record, retained evidence path, or explicit handoff;
2. record the context's final role and disposition;
3. release the completed context through the supported stop mechanism; and
4. audit available capacity before opening the next context.

Completed contexts are provenance, not evidence or reusable workers. If a fresh
required context cannot be created, keep the slice in monitored `WAITING`; do
not reuse an old role identity, collapse required independence, or start
mutation in a Scout context. The owning Orchestrator retries on a later wake
after any ambiguous creation result is resolved.

If the supported release primitive reports success but capacity remains
unavailable, record the tool or app outage, audit capacity once, and keep the
slice in monitored `WAITING`. Back off and retry on later wakes rather than
repeatedly dispatching, retrying release, or reusing a completed role.
Repository workflow can require and record context disposition, but it cannot
manufacture a context release that the supporting tool did not perform.
Capacity pressure is not a terminal result or a user-attention gate.

## Publisher Activation

The Publisher is a delegated subagent, not a persistent program Orchestrator.
It begins only after an independent Verifier has accepted the exact candidate
and the user has explicitly authorized the named external actions. The role
does not grant those capabilities.

The active program workflow owns the exact release sequence, validation plan,
and any sealed cleanup mechanics. The Publisher relies on the accepted handoff;
its operational checks do not replace candidate verification. It does not
implement repairs, infer rollback authority, begin the next phase, or spawn
further agents by default.

## Real-Browser Verification Across Task Isolation

Browser attachment is task-local. An Orchestrator must not assume that a
browser attached to its task is available to a Verifier subagent. When a gate
explicitly requires a real browser, prefer attaching one to the independent
Verifier's own task so that the Verifier can execute and adjudicate the gate.

Publisher live-browser checks are likewise task-local. Attach the required
browser to the Publisher subagent; if it is unavailable, keep that gate in
monitored `WAITING` or report the explicitly allowed HTTP-only limitation
rather than silently weakening the formal-close plan.

When task isolation prevents that arrangement, use a parent-operated fallback
only when the current authority explicitly allows it. The parent Orchestrator
may operate its attached browser strictly from the canonical Verifier's
predefined script and assertions, plus bounded follow-up observations directed
by that Verifier. The Orchestrator must not improvise the procedure, edit the
candidate, or adjudicate the result. The canonical Verifier audits the captured
evidence and cleanup and alone issues the explicit `ACCEPT` or `REJECT`.

The evidence envelope must identify the browser work as
parent-Orchestrator-operated and Verifier-directed; it must not call the
operation independently executed. For an explicitly required real-browser
gate, do not substitute a standalone browser, Flask test client, or another
test client unless separate authority permits that substitution.

## Decision, Safety, And Authority Gates

Stop the program only for an unresolved product decision (including an
architecture, compatibility, or security-policy choice), or for a genuine
safety issue involving secrets, protected data, destructive scope, or an
unsafe recovery or rollback boundary.

When an action needs an ungranted authority lane, keep that action closed,
complete every other permitted step, and report `READY_FOR_AUTHORIZATION` with
the exact target and scope. An active-writer overlap keeps the conflicting
mutation closed until ownership is reconciled. Neither state terminates the
program.

Identity ambiguity, missing evidence, scope-local validation failures,
unrelated failures, harness or command errors, environment mismatch, and tool
or capacity outages are `RECOVERING` or monitored `WAITING`. End the bounded
worker turn when needed, hand the evidence to the Orchestrator, and continue
through classification and the next safe action.
