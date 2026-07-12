# Flask Rewrite Program Workflow

Last reviewed: 2026-07-11

Status: accepted Flask rewrite workflow authority

This document adds program-specific branch, review, evidence, and rollback
rules to the repository workflow. Use the universal role, authority, context,
and worktree rules in [AGENTS.md](../../AGENTS.md),
[Agent roles](agent-roles.md), [Authority lanes](authority-lanes.md), and
[Worktrees](worktrees.md) instead of restating them here.

## Branch And Worktree Contract

- The permanent integration target is `codex/flask-rewrite-integration`.
- Name slice branches `codex/flask-rewrite-pNN-<bounded-slug>`.
- Base every slice on the then-current integration SHA and record that SHA in
  the slice handoff.
- Give every slice an isolated worktree and one active writer.
- Never base new work on the frozen `rewrite/typescript-backend` or
  `rewrite/ts-phase3-integration` references.

An implementer leaves the bounded change for an independent verifier who did
not write it. Verification begins read-only. If repairs are needed, hand the
exact findings to the implementer or a narrowly scoped repair agent, then use
fresh independent verification before integration.

## Review Boundary

A reviewable slice is one behavioral contract, one ownership cluster, and one
rollback unit. Split work when parts have independent rollback paths or need
different evidence domains. There is no arbitrary line-count cap; review size
is determined by whether one reviewer can verify the declared contract and
revert it without removing unrelated behavior.

## Evidence Envelope

Every implementation-to-verification and verification-to-integration handoff
records:

- base and head SHAs;
- changed paths and diff statistics;
- preserved contracts and any intentionally changed contracts;
- exact focused validation commands and results;
- browser evidence when the behavior requires a real browser;
- full-suite evidence at milestone gates;
- residual risks and untested boundaries; and
- documentation accounting, including why no update was needed when none was
  made.

## Milestone Documentation Gate

- Update affected `docs/current-state/` documents and the local roadmap only
  after the behavior is verified on the integration branch.
- Give the resulting documentation diff to an independent verifier before
  integrating the tracked documentation slice.
- State explicitly whether a documented contract exists only on the
  integration branch or has also reached `main`, a remote, deployment, or live
  data. Evidence at one boundary does not imply the others.
- Keep future or unmerged behavior in the local roadmap. Do not describe it as
  shipped current state or check later-phase gates before their evidence exists.

## Integration And Rollback

Before integration, record the integration branch's pre-integration SHA. The
verified slice commit must not be rebased, amended, squashed, or otherwise
rewritten after verification. Integrate it locally with an explicit merge
commit so the pre-integration SHA and merge commit form one clear rollback
target.

The integration agent reviews the final diff and evidence before merging. A
local slice-to-integration merge is permitted only after independent
verification. Pushing, opening a pull request, merging to `main`, deploying,
or performing a live-data operation remains an explicit user gate under
[Authority lanes](authority-lanes.md).
