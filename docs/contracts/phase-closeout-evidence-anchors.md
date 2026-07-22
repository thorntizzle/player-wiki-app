# Phase Closeout Evidence Anchors

Last reviewed: 2026-07-21

Status: accepted sanitized evidence ledger

This tracked ledger anchors final ignored lifecycle/postmortem records without
tracking private or machine-local evidence. A row proves only the named file's
bytes and accepted Git identity; deployment and live status require their own
evidence.

| Phase | Accepted commit | Accepted tree | Relative lifecycle record | Bytes | SHA-256 | Finalized UTC |
| --- | --- | --- | --- | ---: | --- | --- |
| Flask rewrite Phase 5 | `8766292816f2f91f10085f09f2e372651545eced` | `292d130a3e76b5208061dd7f58b477305461530b` | `.local/roadmaps/flask-rewrite-phase5-lifecycle-evidence.md` | 141787 | `60BAD34535C3309BB0D4E582F397AB96375F1DAC0CAE7C68F2DFCA9079927E0E` | `2026-07-20T14:27:37.3353132Z` |
| Flask rewrite Phase 6 (70a + empty 7099 disposed; six HOLD) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 385579 | `326E6338C4DFF3B019131721E7502930C0985135E32BD48F6F675B98B3756D6D` | `2026-07-22T00:02:00.5353518Z` |

The Phase 6 row anchors the same Publisher's exact non-recursive, non-force
removal of the empty unregistered `7099` child after the user-reported full
Codex restart released its prior handles. Fresh preflight found zero process
references and relevant handles with exclusive `DELETE` access green;
post-proof found only the exact empty child absent and its ordinary parent
empty. No content was removed. Local and remote `main` remained clean and
equal at `b958886186a90d6beaabdb6c5dbf67d478a3c10e`, tree
`0409ee6ea8af5de55141038e2f4838228aeb47eb`, with one worktree and only
local/remote `main`. Exact `70a` remains externally absent and evidence-safe;
the six populated roots remain present on their serial item-specific safety
gates. The exact ignored residual manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 15,954
bytes, SHA-256
`7A358E3A5E80FC753664E025CA7E795466F8966B4D4A9C7E82515D4BDA74C416`.
The latest pushed documentation/evidence identity before this refresh is
`b958886186a90d6beaabdb6c5dbf67d478a3c10e`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only
and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
