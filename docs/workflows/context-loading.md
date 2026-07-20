# Context Loading

Last reviewed: 2026-07-20

Status: accepted workflow reference

## Loading Order

Use this sequence:

1. **Route** with `AGENTS.md` and the narrow specialist skill.
2. **Search** with `rg`, file lists, indexes, and heading scans.
3. **Read a section** or small target file.
4. **Open the full reference** only when the task requires its complete
   contract.

If a large full-file read is necessary, note why at close-out.

Stop loading when the current objective, authority, ownership, acceptance
checks, and next safe action are supported. Do not preload adjacent domains or
future phases merely because they may become relevant later.

## Bounded Working Set

Keep stable and changing context separate:

- Stable rules stay in `AGENTS.md`, workflow documents, specialist skills, and
  current-state documents. Carry paths and relevant headings, not copied prose.
- Changing state contains only the current objective, exact checkout identity,
  role and authority, owned boundary, active gate, material evidence, blockers,
  and next action.
- Detailed lifecycle history, test logs, rejected-candidate evidence, and
  residual-root inventories stay in their authoritative files or owning task.
  Carry a path, hash, command/result summary, or task cursor when needed.
- Tool output is evidence, not permanent prompt context. Extract the decisive
  lines or summary and discard routine successful output from the working set.
- Context disposition and capacity gates are owned by
  `agent-roles.md` under **Disposable Context Lifecycle**. Saved changing state
  carries only the role/context identity, final disposition, durable evidence
  pointer, and unresolved implication; it does not restate that procedure.

Use searches, headings, line-targeted reads, and narrow source/test files before
opening a large document. A required skill instruction may still require its
complete `SKILL.md`; that requirement does not authorize loading every linked
reference.

## Replace-Only Context Capsule

Use one context capsule for work that spans multiple turns, tasks, agents, or a
context compaction. Keep it concise enough to scan once and structure it as:

1. objective and current role/authority lane;
2. repository, branch/worktree, exact HEAD or candidate identity, and owned
   files or module boundary;
3. authoritative source paths/headings actually relied on;
4. current state or gate and the latest material validation/evidence;
5. unresolved blocker, operator decision, or stop condition; and
6. one next safe action.

Replace the capsule whenever identity, ownership, authority, gate, or next
action materially changes. Do not append chronological commentary, duplicate
stable instructions, raw command output, speculative future work, or a ledger
of already completed steps. Heartbeat capsules follow any smaller explicit
limit in the selected specialist skill.

## Compaction, Resume, And Handoff

After compaction or task resume:

1. treat the latest capsule as an index, not proof;
2. verify the exact Git/worktree identity and ownership before mutation;
3. reread only the cited section needed for the unresolved gate;
4. preserve completed results unless identity or evidence changed; and
5. replace the capsule before continuing if the recorded state is stale.

Handoffs are delta-first. State what changed, exact identity, result, remaining
risk or gate, authoritative evidence pointer, and next owner/action. Do not copy
the whole roadmap, workflow, transcript, test log, or prior handoff. The
receiving role expands context only when a cited gate or ambiguity requires it.

## Source Ownership

- `AGENTS.md` and `docs/workflows/`: agent behavior, lanes, gates, and context
  discipline.
- `docs/current-state/`: current shipped product contract and known boundaries.
- `docs/contracts/`: sanitized generated or curated contracts and immutable
  evidence-anchor ledgers. Load an artifact only when an active gate cites it.
- Specialist skill references: procedural guidance and domain routing.
- `.local/roadmaps/`: unresolved future work and explicitly named local
  lifecycle/evidence packages. Neither is workflow or shipped-product
  authority.
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
- Open local roadmaps only when planning, logging feedback, updating an
  unresolved item, or following an exact lifecycle/evidence pointer required
  by the active gate.
- Do not load legacy checklists, historical milestones, generated artifacts,
  or private campaign evidence by default.

## Reference Hygiene

Keep routing maps small. Break large facts into titled sections with one subject
per paragraph or bullet so targeted reads remain possible. Put changing product
facts in `docs/current-state/`, not in personal skill adapters.

Keep one owner for each fact. Update the authoritative source and point other
instructions to it instead of duplicating changing counts, identities, or
procedures across routers, skills, roadmaps, and handoffs.
