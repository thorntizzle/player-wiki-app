# Worker Delegation

Status: accepted workflow reference

## Unit And Capacity

Delegate only concrete bounded work that advances the current freeze. One
candidate-producing cycle has one Scout pass, one approved freeze, one
immutable wave, one assembled candidate, and one independent precommit
adversarial review. Capacity batches inherit the same IDs and controls.

Use at most two concurrent writer lanes by default and one writer per
file/module cluster. Read-only roles may run beside writers only without
ownership or independence conflicts.

## Assignment Contract

Default to `fork_turns="none"` and the current replace-only capsule. Name stable
IDs, role, authority, exact owned files/modules, freeze excerpts/headings,
repo/worktree/base/target, dependencies, relevant inputs, protected-data and
non-goal boundaries, L1 checks, optional L2 uncertainty, evidence form,
handoff fields, and stop conditions. Workers do not commit, push, integrate,
publish, deploy, or write live data unless explicitly assigned matching
authority.

## Assembly And Repair

The Orchestrator integrates L1-qualified lane results, then freezes one exact
candidate. Before commit, the independent Verifier reads every changed path,
traces affected entry-to-side-effect paths, and challenges applicable access,
privacy, custody, compatibility, concurrency, and failure assumptions. L2 and
Verifier drills are optional only for a concrete uncertainty; L4 requires
separate authority. The Verifier returns acceptance only with no unresolved
blocking finding and stated residual uncertainty, or one complete Frozen
Failure Inventory with root-cause clusters and dependency-skips. Each finding
identifies location, trigger, expected/actual behavior, impact/severity,
evidence, root cause, and affected scope. It continues unaffected paths after
ordinary findings and stops early only for safety or an invalid candidate or
environment that makes dependent analysis meaningless.

No repair occurs inside a rejected cycle. When budget permits, the next Repair
Cycle's Scout receives the exact inventory and returns a Repair Requirements
Brief; the Orchestrator approves the new freeze before any repair writer starts.

## Reclaiming A Lane

A timeout is unknown state, not failure. Request stop/report, wait when
practical, inspect status/diff and ownership, preserve useful partial work, and
reclaim only after confirming the writer is inactive and no unreviewed unique
work, protected data, or conflicting side effect remains.
