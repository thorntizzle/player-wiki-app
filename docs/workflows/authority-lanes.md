# Authority Lanes

Last reviewed: 2026-07-28

Status: accepted workflow reference

Roles describe responsibility. Authority lanes describe permitted side
effects. Use the least-powerful lane that can complete the request.

## Lane Registry

1. `read-only`: inspect files, Git state, logs, tests, or local/live health
   without changing repo, content, or runtime state.
2. `repo-write`: edit tracked app code, tests, sanitized fixtures, or docs in an
   owned checkout. It does not permit external writes.
3. `local-content-write`: update ignored/local campaign mirrors, local drafts,
   or local roadmap files named by the request. It does not permit live writes.
4. `live-content-api-write`: write player-facing content through an approved
   live API. It does not permit deploys or direct database mutation.
5. `deploy`: deploy the current app artifact to the named environment. It does
   not permit database replacement or unrelated content mutation.
6. `live-database-write`: merge, migrate, restore, or directly mutate live
   SQLite/database state. This is the highest-risk lane.

Multiple lanes may be granted explicitly. Permission for a higher-numbered lane
does not imply unrelated lower-numbered actions.

## Operator Gates

The current user request must explicitly authorize lanes 4 through 6. It must
also authorize destructive local writes, secret changes, integration into
`main` or another protected target, and PRs. Confirm the exact app/environment
and intended data scope before a live write.

A tracked program workflow or the current request may authorize bounded local
slice-to-durable integration after independent acceptance. That repo-write
authority does not imply integration into a protected target, a remote write,
or any external side effect.

Destructive cleanup is normally item-specific. A formal-close exception may
authorize only the accepted candidate's sealed disposal plan, as defined by the
applicable program workflow. It becomes executable only after every named gate
is green and never extends to an unlisted, ambiguous, or drifted target.

Live database work requires a backup or recovery plan, a narrow table/data
scope, protection for newer remote auth/membership/session/combat state, and
post-write verification.

## Publisher Authority

Publisher is a role, not an authority lane. Its handoff must individually name
the source or target ref, deployment environment, read-only live-check scope,
and any approved cleanup plan. An omitted capability is not authorized.

Main or other protected-target integration, deploy, destructive cleanup,
branch deletion, PR creation, rollback, secret changes, live content writes,
and live database or volume writes remain separate operator gates. Successful
deployment does not imply cleanup. The applicable program workflow owns the
exact sealed-plan proof and executor rules.

## Escalation

When a task reaches a stronger authority lane than its role lock permits, keep
that side effect closed, complete every other permitted step, and report
`READY_FOR_AUTHORIZATION`:

- requested action and target;
- why it is needed;
- evidence gathered;
- risk and rollback path;
- the exact authority being requested.

Do not substitute deployment for a content API write, database replacement for
a table-scoped merge, or a live write for local verification.

An authority gate is not a terminal program result. The owning Orchestrator
continues all in-scope work and resumes the gated action only after the user
authorizes its exact target and scope.
