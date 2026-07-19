# Agent Roles

Last reviewed: 2026-07-19

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
  authorized read-only live verification, and remove only explicitly approved
  non-unique worktrees. It does not implement or repair product behavior,
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

## Publisher Formal Close Step

The Publisher is a delegated subagent, not a persistent program Orchestrator.
It begins only after an independent Verifier has accepted the exact candidate
and the user has explicitly authorized every requested external or destructive
action. The Publisher is the sole Git integrator and deployer for the close.

Execute formal close serially:

1. Verify the accepted commit/tree, clean source, evidence pointer, expected
   remote source/target refs, exclusive integration checkout, and rollback SHA.
2. Confirm every real tracked closeout delta was reviewed, committed, and
   included in the accepted source before Publisher activation. If no delta
   exists, do not manufacture an empty or metadata-only closure commit.
3. Push the exact accepted source ref. Re-read the remote refs before target
   integration.
4. Integrate into the named clean target with fast-forward-only semantics by
   default, run the prescribed focused post-integration checks, push the exact
   target, and verify both local and remote identity. Stop on non-fast-forward,
   conflict, target drift, or any tree change.
5. Verify the deploy source is the exact clean pushed target, deploy only to the
   named app/environment, and bind release/image/runtime metadata back to the
   Git identity.
6. Run only the authorized read-only live plan: health/readiness, representative
   HTML/API/access/static/asset checks, and real-browser behavior when required
   and available in the Publisher task. Live content or database writes,
   account creation, secrets, rollback, and volume changes need separate
   authority.
7. After Git, deploy, and live gates are green, process the approved cleanup
   manifest one exact path at a time under `worktrees.md`. Retain every path
   with unique work, ambiguous ownership, failed evidence, or missing cleanup
   authority.
8. Return one delta-first formal-close handoff to the parent Orchestrator and
   end. Do not run the retrospective or begin another phase.

The Publisher relies on the independent candidate acceptance already supplied
in its handoff. Its release checks are operational evidence, not a replacement
for candidate verification, and it does not spawn further agents by default.
It never converts a Verifier rejection, deployment failure, live failure, or
cleanup ambiguity into an implementation repair or an inferred rollback.

## Real-Browser Verification Across Task Isolation

Browser attachment is task-local. An Orchestrator must not assume that a
browser attached to its task is available to a Verifier subagent. When a gate
explicitly requires a real browser, prefer attaching one to the independent
Verifier's own task so that the Verifier can execute and adjudicate the gate.

Publisher live-browser checks are likewise task-local. Attach the required
browser to the Publisher subagent; if it is unavailable, stop or report the
explicitly allowed HTTP-only limitation rather than silently weakening the
formal-close plan.

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

## Stop Rules

Stop and report when work requires an ungranted authority lane, overlaps an
active writer, expands beyond owned files, lacks required evidence, introduces
a product or architecture choice, touches secrets or protected data, or hits a
validation failure unrelated to the assigned slice.
