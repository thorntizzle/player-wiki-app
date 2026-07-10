# Context Loading

Last reviewed: 2026-07-10

Status: accepted workflow reference

## Loading Order

Use this sequence:

1. **Route** with `AGENTS.md` and the narrow specialist skill.
2. **Search** with `rg`, file lists, indexes, and heading scans.
3. **Read a section** or small target file.
4. **Open the full reference** only when the task requires its complete
   contract.

If a large full-file read is necessary, note why at close-out.

## Source Ownership

- `AGENTS.md` and `docs/workflows/`: agent behavior, lanes, gates, and context
  discipline.
- `docs/current-state/`: current shipped product contract and known boundaries.
- Specialist skill references: procedural guidance and domain routing.
- `.local/roadmaps/`: unresolved future work only.
- Current source and tests: implementation behavior and verification evidence.
- Live checks: environment state only when the request needs current production
  evidence and the authority lane allows the check.

When sources disagree, prefer the latest explicit user instruction for the
current slice, then repo-local workflow authority, current source/tests, and the
narrow current-state document. Report a material conflict instead of silently
choosing stale roadmap or skill prose.

## Conditional References

- Open the app-wide repo map only for cross-domain ownership, storage splits,
  shared shell architecture, or routing uncertainty.
- Open `docs/api-v1.md` only for the endpoint family or authentication contract
  involved; search headings or route terms first.
- Open frontend UX guidance only when changing or auditing user-facing layout,
  controls, feedback, loading, accessibility, or interaction patterns.
- Open local roadmaps only when planning, logging feedback, or updating an
  unresolved item.
- Do not load legacy checklists, historical milestones, generated artifacts,
  or private campaign evidence by default.

## Reference Hygiene

Keep routing maps small. Break large facts into titled sections with one subject
per paragraph or bullet so targeted reads remain possible. Put changing product
facts in `docs/current-state/`, not in personal skill adapters.
