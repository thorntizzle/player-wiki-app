# Worktrees And Concurrent Lanes

Last reviewed: 2026-07-20

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

When a Publisher owns formal-close cleanup, begin with a comprehensive live
census rather than a hand-selected removal list. Reconcile every program-owned
entry from `git worktree list --porcelain`, local and live-remote ref listings,
the lifecycle retained-root inventory, validation roots, and deploy-generated
temporary paths. Classify each entry as removable, retained for a named active
owner, retained for irreducible unique work or unresolved evidence, protected,
unrelated, or lacking cleanup authority. An omitted owned entry is a stopped
gate, not an implicit retention decision.

For each worktree, before removal:

1. resolve and record the exact absolute path and registered branch/HEAD;
2. confirm the path is the exact manifest entry and not a workspace root,
   parent directory, glob, symlink, junction, or unresolved variable;
3. prove its Git common directory is the expected repository and that the path
   is a normal directory, not a reparse point;
4. require clean tracked and untracked status; if contents remain, retain the
   worktree or clean those exact contents only under separate authority, then
   recheck from Git;
5. prove the branch/HEAD has no unique commits or unreviewed evidence relative
   to the exact accepted target; and
6. use `git worktree remove <exact-path>` without force. Stop if Git refuses.

Branch deletion follows worktree cleanup and is a separate manifest item. For
each exact local ref, prove no worktree is attached, reread its tip, ancestry,
unique-commit count, owner, and protection state, then use safe non-force
deletion. For each explicitly authorized remote ref, first reread the live
remote ref and accepted target, prove the same ancestry and uniqueness, and
delete only the fully enumerated ref without force. Protect `main`, tags,
unmerged, ambiguous, active, unrelated, and changed refs by default.

If ordinary Git removal deregisters a Windows worktree but leaves a residual
directory, stop. A later exact filesystem removal requires separate destructive
authority plus fresh proof that the literal path is the approved child of the
expected parent, absent from the worktree registry, normal/non-reparse, has no
active owner or process, and contains no unique or unreviewed evidence. Use
`Remove-Item -LiteralPath <exact-path> -Recurse` without `-Force` first. `-Force`
is allowed only when separately approved for that same audited residual. Never
use a glob, unresolved variable, parent-recursive deletion, prune, or filesystem
force against a registered worktree.

Runner roots, coverage/cache roots, temporary outputs, screenshots, and similar
raw validation artifacts are disposable after the lifecycle ledger records the
exact candidate identity, command/result, failure classification, and every
unresolved implication. Failed or ambiguous raw evidence stays inert until its
material implication is accepted or explicitly retained. Non-worktree roots
still require exact path, owner, containment/non-reparse checks, retention
decision, and destructive authority.

Formal close ends with only the accepted target worktree and protected durable
refs unless a concrete active-owner or irreducible unique-work exception is
named. For the Flask rewrite, this means a clean main-only local/remote state;
the completed phase worktree and merged phase/slice refs are not durable
evidence.
