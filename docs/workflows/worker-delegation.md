# Worker Delegation

Status: accepted workflow reference

## Unit And Capacity

Delegate only concrete bounded work that advances the current freeze. One
candidate-producing cycle has one Scout pass, one approved freeze, one
immutable wave, one assembled candidate, and one independent sweep. Capacity
batches inherit the same IDs and controls.

Use at most two concurrent writer lanes by default and one writer per
file/module cluster. Read-only roles may run beside writers only without
ownership or independence conflicts.

## Assignment Contract

Default to `fork_turns="none"` and the current replace-only capsule. Name stable
IDs, role, authority, exact owned files/modules, freeze excerpts/headings,
repo/worktree/base/target, dependencies, relevant inputs, protected-data and
non-goal boundaries, L1/L2 checks, evidence form, handoff fields, and stop
conditions. Workers do not commit, push, integrate, publish, deploy, or write
live data unless explicitly assigned matching authority.

## Assembly And Repair

The Orchestrator integrates only L1/L2-qualified lane results, then freezes one
exact candidate. Candidate-level L3/L4 begins only after assembly. The
independent Verifier returns acceptance or one complete Frozen Failure Inventory
with root-cause clusters and dependency-skips.
It continues unaffected checks after ordinary failures and stops early only for
safety or an invalid candidate/environment that makes dependent results
meaningless.

No repair occurs inside a rejected cycle. When budget permits, the next Repair
Cycle's Scout receives the exact inventory and returns a Repair Requirements
Brief; the Orchestrator approves the new freeze before any repair writer starts.

## Reclaiming A Lane

A timeout is unknown state, not failure. Request stop/report, wait when
practical, inspect status/diff and ownership, preserve useful partial work, and
reclaim only after confirming the writer is inactive and no unreviewed unique
work, protected data, or conflicting side effect remains.
