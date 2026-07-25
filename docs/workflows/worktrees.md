# Worktrees And Concurrent Lanes

Last reviewed: 2026-07-25

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

## Formal-Close Cleanup

The applicable program workflow owns candidate-specific cleanup census,
sealed-plan proof, evidence disposal, and branch or ref cleanup. Do not perform
Publisher cleanup from this generic workflow.

Outside that program, remove only an exact, authorized worktree with
`git worktree remove <exact-path>` and without force. Stop on ownership,
registration, path, or unique-work uncertainty; never substitute broad
filesystem removal for Git's worktree operation.
