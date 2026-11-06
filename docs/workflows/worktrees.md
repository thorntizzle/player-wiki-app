# Worktrees

Status: accepted workflow reference

## Preflight And Lane Model

Run `git status --short --branch` and `git worktree list --porcelain` from the
confirmed root. Parse the full inventory but report a bounded projection:
current checkout, integration lane, active conflicts, aggregate retained count,
and only retained entries relevant to ownership or cleanup.

The main checkout is the sole active worktree by default. Confirm exclusive
ownership, preserve existing dirty work and make the current task's delta
separable. If unrelated edits prevent safe work, resolve ownership or request
explicit authority for a named additional lane; do not create one by default.
Read-only independent reviewers can use the same checkout without writing it.

Never place live SQLite files, campaign/vault content, backups, secrets,
credentials, private identifiers, or protected evidence in a worktree or repo-
local scratch. Use an operator-provided external data root or approved runtime
volume.

## Lane Assignment

Every lane records stable IDs; role; authority; branch/worktree/base/target;
owned files/modules; freeze; relevant inputs; L1 inspection and optional L2
uncertainty; stop conditions; and disposition. Another worktree is not itself a
blocker; overlapping ownership or ambiguous identity is.

## Instruction Delivery And Reuse

Workflow edits in one checkout do not update other worktrees; uncommitted edits
are also absent from a new checkout of HEAD. Before assigning or resuming work,
identify the approved current governance location and the affected document
identities in the existing assignment/current record. Read those instructions
and compare them with the lane's local copies. A matching source HEAD alone is
not proof of matching governance.

For a mutable lane, deliver the reviewed files before its next assignment, or
explicitly assign an approved shared governance reference and confirm it was
read. Keep instruction delivery within existing scope and ownership. Do not
require a commit, merge, new service or receipt protocol merely to deliver
reviewed documentation. A worktree with missing or ambiguous current governance
is not ready for new work until that narrow gap is resolved.

For a frozen candidate, preserve its local instructions and bound authority.
Separately identify the current governance for a future assignment; adopting it
never rebinds the historical candidate. Any successor still needs its applicable
scope, allowance and review. Mark stopped lanes deferred until that assignment
actually reads the selected governance; a prepared pointer is not confirmation.

Close workflow changes with a short consumer disposition in the existing record:
delivered to active mutable lanes, or deferred for frozen/inactive lanes until
reuse. Do not synchronize every dormant historical checkout by default.

## Candidate Identity And Integration

Assemble qualified lane results within the owned candidate lane, then freeze
one candidate. Protected Git integration remains separately authorized after
the required complete release review. A committed candidate records exact
commit/tree and relevant config/toolchain/inputs. An uncommitted candidate
records its base commit and exact intended artifact, including untracked
source, path/mode changes, renames and explicit deletions. Commit authority
is not needed to establish verifiable identity.

For newly frozen candidates, distinguish material identity from Git custody.
Declare which bytes form the artifact: the assembled worktree by default,
or explicitly selected index bytes. Fingerprint those selected bytes, paths,
modes and base, plus declared semantic inputs. Record complete porcelain and
any differing index/worktree observations separately as custody evidence.
Unselected index bytes are not silently substituted for reviewed worktree bytes.

Keep the canonical UTF-8 LF JSONL representation, sorted ordinally by normalized
repo-relative path and state, with fixed key order
`path,state,oldPath,mode,byteLength,sha256` and `null` for inapplicable values.
For the selected artifact use `state` of `worktree`, `index`, or `deleted`;
record rename origin in `oldPath` and the old-path deletion/final layout.
Index/worktree custody observations can use separate entries/manifests; they
are not part of the selected product digest unless declared semantic inputs.
Record the manifest SHA-256, artifact selection and input identities once.

Verify a frozen manifest against its declared artifact, not a freshly inferred
Git staging classification. Staging already-reviewed worktree bytes without
changing the selected artifact does not consume a source candidate. A changed
selected index, product byte, path, mode, base or semantic input does. A commit
can be mapped to the same reviewed tree only when exact selected paths, modes,
bytes, deletions and relevant semantics are proved equal; staging unrelated
files or changing artifact selection is not equivalent. Record the new Git
identity prospectively, without overwriting the reviewed one.

This prospective format/selection rule does not migrate or reinterpret legacy
frozen manifests. Before using any existing assembler/helper, inspect its
actual selected-byte, status and envelope contract as part of ordinary
preflight. If it cannot verify the declared representation, use a compatible
admitted representation or scope its adaptation separately; never bypass its
checks. Preserve bound old revisions and formats as evidence.

The independent Verifier recomputes and matches selected material identity
before and after review. The
[operating model](agent-operating-model.md#independent-review-and-reuse) owns
review coverage/reuse and complete release review; the
[guardrails](repo-guardrails.md#identity-and-evidence-changes) own evidence
corrections and relevant drift. Never implement during independent review.

## Retention And Cleanup

Retain useful lanes through verification and possible repair, but require the
current cycle's new freeze and Role Lock before another edit. Rejected cycles
and completed gates grant no cleanup authority. Before removal, recheck exact
paths, registration, ownership, integration/disposition, ignored outputs,
protected data, and unique work. Never use force or broad recursive deletion
for a worktree.

An explicitly authorized maintenance cleanup may archive dormant lanes without
waiting for an unrelated release or deployment. Retain only explicitly needed
active lanes; exact frozen candidates can remain in verified inactive archives.
Before retiring a dirty lane, preserve and
verify its complete tracked/untracked/ignored files, index state and commit/ref
identity outside source worktrees; retain referenced evidence and recovery
instructions. Prefer moving the complete directory intact to an external inert
archive, verifying its identities, then normally deregistering its absent
original path. Do not repair/re-register the archive as an active checkout.
This preserves dirty and frozen bytes without clearing local changes. Check
ownership/process use and
source/archive identity again before removal. Keep branches unless their
deletion is separately authorized. Record the archive location once; future
reuse must restore deliberately and load current governance before new work.
