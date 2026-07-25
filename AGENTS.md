# Campaign Player Wiki Agent Router

Last reviewed: 2026-07-25

Status: accepted workflow authority

Start here for work in this repository. These instructions own agent routing,
repo and data boundaries, and durable guardrails. Product behavior belongs in
`docs/current-state/`, unresolved work in `.local/roadmaps/`, and implementation
details in current source and tests.

## Required Preflight

Before tracked edits or any external write:

1. Follow the **Preflight** heading in `docs/workflows/worktrees.md`.
2. Classify the execution role with the relevant heading in
   `docs/workflows/agent-roles.md`.
3. Classify the permitted side effects with the relevant heading in
   `docs/workflows/authority-lanes.md`.
4. State a role lock: role, branch/worktree, authority, owned files or module
   cluster, expected validation, operator gates, and stop conditions.

Reclassify after implementation close-out, context compaction, or a follow-up
that expands scope. Authority does not carry into a new slice by inertia.

If another task owns the checkout, branch, file, or module cluster, do not add
edits there. Use `docs/workflows/worktrees.md` to select an isolated lane.

## Context Loading

Follow `docs/workflows/context-loading.md`: route, search, read the smallest
relevant section, and open a full large reference only when necessary.

- Keep a bounded working set: current objective, role and authority, exact
  checkout identity, owned boundary, active gate, and next action. Reference
  stable rules by file and heading instead of copying them into prompts or
  handoffs.
- For work that spans tasks, agents, or context compaction, maintain one
  replace-only context capsule using the structure in `context-loading.md`.
  Replace it on material state changes; do not append commentary, raw logs, or
  completed-history narration.
- Use the selected CPW specialist skill and follow its map-loading rules.
- Open `docs/current-state/INDEX.md` only when the task needs the shipped product
  contract, then open the narrow domain document.
- Use the app-wide repo map only for routing uncertainty, cross-domain
  ownership, storage boundaries, or shared shell architecture.
- Use `.local/roadmaps/` only for unresolved or explicitly requested future
  work and explicitly named local lifecycle/evidence packages. Neither is
  authority for shipped behavior.
- Inspect targeted source and tests when implementation details matter.
- After compaction or handoff, verify the recorded Git/worktree identity and
  reload only the capsule's unresolved sources. Do not replay completed work or
  reopen every previously consulted reference.

## Domain Routes

- Characters: `$campaign-player-wiki-characters`.
- Combat, Session, DM Content, polling, and rerender stability:
  `$campaign-player-wiki-live`.
- Systems sources, imports, rules, and rendering:
  `$campaign-player-wiki-systems`.
- Player-safe wiki and session publication:
  `$campaign-player-wiki-publishing`.
- Local runtime, validation, Git, Fly, backup, auth, and SQLite operations:
  `$campaign-player-wiki-ops-deploy`.
- Formal accepted-release closeout: route through
  `$campaign-player-wiki-ops-deploy`, `docs/workflows/agent-roles.md`, and the
  active program workflow. Activate a Publisher only after independent
  acceptance and explicit authorization.
- Feedback capture without implementation:
  `$campaign-player-wiki-feedback-logger`.
- Broad or mixed app work: `$campaign-player-wiki-app`.
- GM/canon vault source work: `$campaign-wiki-vault`.

## Repo And Data Boundaries

- The current Git root is the app root; do not assume a worktree is nested under
  a particular parent directory.
- Track app code, workflow docs, and sanitized fixtures. Do not track live
  SQLite files, campaign content, vault content, secrets, personal paths,
  private identifiers, or proprietary source data.
- Keep `campaigns/{campaign-slug}/`, live data, and private campaign evidence
  out of tracked history.
- Use the repo-root `./local.ps1` or the configured shared virtual environment;
  do not rely on bare `python` from `PATH`.
- Prefer targeted Flask/Python tests. Use browser automation only for behavior
  that requires a real browser.

## Operator Gates

Explicit user approval is required for live content API writes, deploys, live
SQLite/database writes or sync, destructive data operations, secrets, merging,
opening a PR, or changing product/architecture policy not already decided by
tracked authority or the current request.

Role titles do not grant external capabilities. Authorization must name the
action, target, and scope; formal close follows `authority-lanes.md` and the
applicable program workflow.

Do not broaden a repo-write request into a live operation. A content task does
not imply live publication, and a code task does not imply deployment.

## Workflow References

- Workflow index: `docs/workflows/INDEX.md`.
- Roles, verification, handoffs, and formal closeout:
  `docs/workflows/agent-roles.md`.
- Side-effect authority: `docs/workflows/authority-lanes.md`.
- Context discipline: `docs/workflows/context-loading.md`.
- Concurrent work and worktrees: `docs/workflows/worktrees.md`.
