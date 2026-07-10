# Agent Roles

Last reviewed: 2026-07-10

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

- Scout to Implementer: evidence, requirements, owned files, hazards,
  non-goals, acceptance checks, and operator gates.
- Implementer to Verifier: changed files, behavior, validation run, risks, and
  documentation obligations.
- Verifier to Scribe: verified behavior and required workflow/current-state
  updates.
- Any role to Orchestrator: blockers, scope expansion, missing evidence,
  conflicting authority, or an operator gate.

## Stop Rules

Stop and report when work requires an ungranted authority lane, overlaps an
active writer, expands beyond owned files, lacks required evidence, introduces
a product or architecture choice, touches secrets or protected data, or hits a
validation failure unrelated to the assigned slice.
