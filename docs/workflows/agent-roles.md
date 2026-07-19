# Agent Roles

Last reviewed: 2026-07-19

Status: accepted workflow reference

## Roles

- **Orchestrator** owns classification, context routing, lane ownership,
  operator gates, integration, validation coordination, Git close-out, and
  final reporting.
- **Scout** owns read-only discovery, evidence, hazards, target files,
  constraints, validation suggestions, and a bounded implementation brief.
- **Implementer** owns changes in assigned files or modules and bounded
  validation. It does not expand requirements or side-effect authority.
- **Verifier** owns review, tests, failure classification, regression findings,
  and a commit/no-commit recommendation. It does not silently fix unrelated
  failures.
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

## Role Lock

Before tracked edits or an external write, state:

- current role or collapsed roles;
- branch and worktree path;
- authority lane from `authority-lanes.md`;
- owned files or module cluster;
- expected validation;
- operator gates;
- stop conditions.

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
- Any role to Orchestrator: blockers, scope expansion, missing evidence,
  conflicting authority, or an operator gate.

The receiving role verifies Git/worktree identity and authority before
mutation, then loads only the cited source needed for the unresolved boundary.

## Real-Browser Verification Across Task Isolation

Browser attachment is task-local. An Orchestrator must not assume that a
browser attached to its task is available to a Verifier subagent. When a gate
explicitly requires a real browser, prefer attaching one to the independent
Verifier's own task so that the Verifier can execute and adjudicate the gate.

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
