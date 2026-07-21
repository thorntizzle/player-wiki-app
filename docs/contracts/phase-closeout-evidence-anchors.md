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
| Flask rewrite Phase 6 (70a externally disposed; 7099 + six HOLD) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 382755 | `CE655F40E1B996F18C00BD0763810330C34FFAE5B69A761EBB8673A11C7D9CCD` | `2026-07-21T23:34:35.5307376Z` |

The Phase 6 row anchors the same Publisher's read-only reconciliation after the
user reported completing the previously approved exact `70a` recursive force
removal outside the command-policy-restricted lane. Exact `70a` is absent, with
no same-name alternate; the current 86-directory/0-file shallow `C:\cpwv` set
is exactly the prior 87-entry set minus only that name. Its ordinal-sorted,
LF-joined UTF-8 no-trailing-LF name hash is
`6FD127BB9B39F1B2A767E7C907D0B43ABAC855E50FC16595493016A55E880022`.
The raw root is irrecoverably removed externally after its material evidence
was anchored. Exact empty unregistered `7099` remains on Win32-32 `HOLD`; the
other six populated roots remain present on their serial item-specific safety
gates. The exact ignored residual manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 14,603
bytes, SHA-256
`BE7F72D395D8CDB76B2709FBBC91F17ECAB436E2EB8F388BD1BBC42DBDFB302B`.
The latest pushed documentation/evidence identity before this refresh is
`b1644730a623ee9b5cb63be020fdd6b75c9b5b77`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only,
records no Publisher mutation during reconciliation, and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
