# Worktrees And Concurrent Lanes

Last reviewed: 2026-07-19

Status: accepted workflow reference

## Preflight

Before tracked edits, run from the confirmed repo root:

```shell
git status --short --branch
git worktree list --porcelain
```

Keep one active writer per file or module cluster. Another registered worktree
is not itself a blocker; overlapping ownership or an ambiguous active lane is.

## Lane Selection

The main checkout is the integration lane by default. A small isolated slice may
use it only when it is clean, no other task writes the same branch/files, and
the change can close out without staging unrelated work.

Use a dedicated `codex/` branch and worktree when:

- another task is implementing concurrently;
- the main checkout contains unrelated changes;
- the slice is parallel, broad, security-sensitive, or architecture-affecting;
- file/module ownership cannot otherwise remain exclusive.

Every dedicated lane needs a branch, worktree path, role, authority, owned
files/modules, deliverable, validation, stop conditions, and integration target.

Do not edit another task's checkout or rely on two tasks coordinating through
the same dirty working tree. Read-only Scouts or Verifiers may inspect shared
source when they do not mutate it.

## Integration And Cleanup

Before integration, review the lane diff and validation. Stage only the intended
slice. Do not merge, push, remove worktrees, or delete branches unless the
request and role lock authorize those actions.

Close out with the branch/worktree, changed files, validation, integration and
push state, and any lanes intentionally left open. Never delete a worktree or
branch with unreviewed or unique changes.

When a Publisher owns formal-close cleanup, its handoff must enumerate every
candidate worktree and branch. For each worktree, before removal:

1. resolve and record the exact absolute path and registered branch/HEAD;
2. confirm the path is the exact manifest entry and not a workspace root,
   parent directory, glob, symlink, junction, or unresolved variable;
3. require clean tracked and untracked status; if contents remain, retain the
   worktree or clean those exact contents only under separate authority, then
   recheck from Git;
4. prove the branch/HEAD has no unique commits or unreviewed evidence relative
   to the exact accepted target; and
5. use `git worktree remove <exact-path>` without force. Stop if Git refuses.

Branch deletion is a separate manifest item and uses safe deletion only after
the remote/local target is verified. Do not run broad recursive filesystem
deletion, infer cleanup from branch containment, or prune unrelated worktree
metadata. Non-worktree evidence roots require their own exact path, ownership,
retention decision, and destructive-cleanup authority; otherwise retain them.
