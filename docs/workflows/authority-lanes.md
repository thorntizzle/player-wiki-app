# Authority Lanes

Last reviewed: 2026-07-22

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
also authorize destructive local writes, secret changes, merges, and PRs.
Confirm the exact app/environment and intended data scope before a live write.

Destructive cleanup authority is item-specific. Worktree removal, local branch
deletion, remote branch deletion, raw-evidence deletion, and removal of a
deploy-generated credential directory are separate capabilities. Authority for
one item never extends to a parent, glob, sibling, later residual, or another
item class. Secret cleanup permits absence checks but never permits secret
contents to be read, hashed, logged, or retained as evidence.

One operator approval may enumerate a homogeneous set of exact items in one
manifest. That is still item-specific authority: resolve, preflight, execute,
stop, and record disposition separately for every item. A manifest never grants
parent-directory, glob, prefix, class-wide, sibling, or newly discovered-item
authority, and drift in one item does not relax the checks for another.

Live database work requires a backup or recovery plan, a narrow table/data
scope, protection for newer remote auth/membership/session/combat state, and
post-write verification.

## Publisher Authority Bundle

Publisher is a role, not an authority lane. Its formal-close handoff grants
only the individually named capabilities:

- push the exact accepted source ref;
- integrate and push the named target ref from the recorded rollback SHA;
- deploy the exact clean pushed target to the named app/environment;
- perform the named read-only live checks; and
- remove the exact worktrees or branches in an approved cleanup manifest.

An omitted capability is not authorized. Main or other protected-target
integration, deploy, destructive cleanup, branch deletion, PR creation,
rollback, secret changes, live content writes, and live database/volume writes
remain separate operator gates. Successful deployment does not imply cleanup,
and cleanup authority for one exact path does not extend to a parent directory,
glob, other worktree, or residual evidence root.

## Escalation

When a task reaches a stronger authority lane than its role lock permits, stop
before the side effect and report:

- requested action and target;
- why it is needed;
- evidence gathered;
- risk and rollback path;
- the exact authority being requested.

Do not substitute deployment for a content API write, database replacement for
a table-scoped merge, or a live write for local verification.
