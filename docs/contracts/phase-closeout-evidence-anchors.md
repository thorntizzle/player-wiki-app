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
| Flask rewrite Phase 6 (70a + empty 7099 disposed; 8160 junction unlinked; five HOLD) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 389307 | `0EFB788C25F52BB6295658873B0C8BB449E941AE233A5722124EBA142AA7226A` | `2026-07-22T01:08:55.2537454Z` |

The Phase 6 row anchors the same Publisher's exact non-recursive, non-force
unlink of only the approved `8160` junction after fresh no-follow and handle/
access preflight. Post-proof found the exact junction and its absent internal
sibling target absent; the populated root remained ordinary, unregistered,
reparse-free, and payload-unchanged at 73,598 files, 42,763 ordinary
directories, and 2,104,118,012 bytes. The exact `C:\cpwv` boundary was unchanged
at 86 names with SHA-256
`6FD127BB9B39F1B2A767E7C907D0B43ABAC855E50FC16595493016A55E880022`.
Local and remote `main` were unchanged, clean, and equal at
`069e67a351e7f95b22b27b4c8fa52adc6ed3a214`, tree
`809d92b0e4377d0eec5af23b2e111c4e698b428a`. Exact `70a` and empty `7099`
remain absent; the other five populated roots remain present on their serial
item-specific junction-bearing `HOLD`s. No exact-root force authority was
granted or exercised. The exact ignored residual manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 19,344
bytes, SHA-256
`7BBE82A8AC7103A1A5A07AE9EBEA167B9E355EBCB8164E82FEBC258D3AF95716`.
The latest pushed documentation/evidence identity before this refresh is
`069e67a351e7f95b22b27b4c8fa52adc6ed3a214`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only
and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
