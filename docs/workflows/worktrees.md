# Worktrees

Status: accepted workflow reference

## Preflight And Lane Model

Run `git status --short --branch` and `git worktree list --porcelain` from the
confirmed root. Parse the full inventory but report a bounded projection:
current checkout, integration lane, active conflicts, aggregate retained count,
and only retained entries relevant to ownership or cleanup.

The main checkout is the integration lane by default. A lone writer may use it
only when status is clean or every existing dirty path is owned by the same
lane, ownership is exclusive, and close-out is separable. Unrelated existing
work requires a distinct worktree. Keep at most two writer lanes active by
default.

Never place live SQLite files, campaign/vault content, backups, secrets,
credentials, private identifiers, or protected evidence in a worktree or repo-
local scratch. Use an operator-provided external data root or approved runtime
volume.

## Lane Assignment

Every lane records stable IDs; role; authority; branch/worktree/base/target;
owned files/modules; freeze; relevant inputs; L1/L2 checks; stop conditions;
and disposition. Another worktree is not itself a blocker; overlapping
ownership or ambiguous identity is.

## Candidate Identity And Integration

Integrate only qualified lane results, then freeze one candidate. A committed
candidate records exact commit/tree plus relevant config/tests/fixtures,
toolchain, and environment. An uncommitted candidate records its base commit
and a canonical SHA-256 fingerprint over intended tracked and untracked paths,
modes, and bytes, plus frozen status and relevant inputs. Commit authority is
not required to create a verifiable identity. Build the fingerprint from UTF-8
LF JSONL entries sorted ordinally by normalized repo-relative path and state.
Each entry uses the fixed key order `path,state,oldPath,mode,byteLength,sha256`
with `null` for inapplicable values. Represent index and worktree bytes
separately when they differ; include Git
mode, byte SHA-256, untracked paths, renames with old/new paths, and explicit
deletion markers. Record the base commit, complete porcelain status, manifest
SHA-256, and relevant-input identities. The Verifier recomputes and matches the
manifest before and after the sweep. Any post-freeze byte, path/mode, status, or
relevant-input change invalidates candidate evidence and creates a repair
candidate. Never implement during the independent sweep.

## Retention And Cleanup

Retain useful lanes through verification and possible repair, but require the
current cycle's new freeze and Role Lock before another edit. Rejected cycles
and completed gates grant no cleanup authority. Before removal, recheck exact
paths, registration, ownership, integration/disposition, ignored outputs,
protected data, and unique work. Never use force or broad recursive deletion
for a worktree.
