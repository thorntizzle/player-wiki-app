# Agent Workflow Index

Status: accepted workflow reference

Open only the narrowest document needed:

- [Agent roles](agent-roles.md): roles, locks, handoffs, and verification ownership.
- [Agent operating model](agent-operating-model.md): lifecycle, context, freezes, and cumulative controls.
- [Repo guardrails](repo-guardrails.md): scope, data safety, toolchain, validation, side effects, and Git.
- [Worker delegation](worker-delegation.md): waves, lanes, assignment contracts, and repair handoffs.
- [Worktrees](worktrees.md): concurrent ownership, candidate identity, integration, retention, and cleanup.

Universal rules live in repo-root `AGENTS.md`; shipped behavior belongs in
`docs/current-state/`. Persistent Overseer/heartbeat and one-off rewrite-program
workflows are not part of the active model.
