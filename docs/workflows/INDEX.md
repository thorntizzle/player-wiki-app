# Agent Workflow Index

Last reviewed: 2026-07-19

Status: accepted workflow reference

Open only the document needed for the current task:

- [Agent roles](agent-roles.md): responsibility, role collapse, Publisher
  closeout, handoffs, and role-lock fields.
- [Authority lanes](authority-lanes.md): allowed side effects and operator
  gates.
- [Context loading](context-loading.md): reference precedence and selective
  reading.
- [Worktrees](worktrees.md): concurrent lane ownership, integration, and
  cleanup.
- [Flask rewrite program](flask-rewrite-program.md): program branch names,
  review boundaries, evidence, verification, integration, and rollback.

Universal rules live in the repo-root `AGENTS.md`. Shipped behavior belongs in
`docs/current-state/`; these workflow documents must not duplicate it.
