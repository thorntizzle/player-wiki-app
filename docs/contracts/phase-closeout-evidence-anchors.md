# Phase Closeout Evidence Anchors

Last reviewed: 2026-07-22

Status: accepted sanitized evidence ledger

This tracked ledger anchors final ignored lifecycle/postmortem records without
tracking private or machine-local evidence. A row proves only the named file's
bytes and accepted Git identity; deployment and live status require their own
evidence.

| Phase | Accepted commit | Accepted tree | Relative lifecycle record | Bytes | SHA-256 | Finalized UTC |
| --- | --- | --- | --- | ---: | --- | --- |
| Flask rewrite Phase 5 | `8766292816f2f91f10085f09f2e372651545eced` | `292d130a3e76b5208061dd7f58b477305461530b` | `.local/roadmaps/flask-rewrite-phase5-lifecycle-evidence.md` | 141787 | `60BAD34535C3309BB0D4E582F397AB96375F1DAC0CAE7C68F2DFCA9079927E0E` | `2026-07-20T14:27:37.3353132Z` |
| Flask rewrite Phase 6 (70a + empty 7099 disposed; 8160 + acd9 + be46 + ca2 junctions unlinked; be46 root gate ready; ca2 + e476 + 35e5 HOLD) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 401233 | `9403C1ACAEF7DE9DED3F23A7F48420378A9DA68D89755E6F55A576779C73FAB2` | `2026-07-22T04:36:18.1060095Z` |

The Phase 6 row anchors the same Publisher's exact non-recursive, non-force
unlink of only the approved `be46` and `ca2` junctions after separate fresh no-
follow gates. Both roots remain ordinary, unregistered, reparse-free, and
payload-unchanged. `be46` has complete green post-unlink handle and root-
`DELETE` proof; its exact-root Force gate remains separately unauthorized.
`ca2` remains on `HOLD` because the final handle/root-`DELETE` helper did not
complete, so final proof is unavailable. Read-only audits retained `e476` and
`35e5` junction-bearing on `HOLD` because authoritative exact-path reference
enumeration was unavailable; neither junction was unlinked. Parked `8160` and
`acd9` remain reparse-free and intact. Exact `70a` and empty `7099` remain
absent. The exact `C:\cpwv` boundary was unchanged at 86 directories and zero
files with SHA-256
`6FD127BB9B39F1B2A767E7C907D0B43ABAC855E50FC16595493016A55E880022`.
Local and remote `main` were unchanged, clean, and equal at
`6b37850c4f754962f4f8e2ff973a17e96f2015ff`, tree
`f3829a71494983da10947b514040aeb897d512e9`. No exact-root Force, push, deploy,
process termination, or other cleanup occurred. The exact ignored residual
manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 29,311
bytes, SHA-256
`AB96DA9708782AEB74E339F4C0E5ACA6D76AF136B439B4F91737C9FB18AA27AB`.
The latest pushed documentation/evidence identity before this refresh is
`6b37850c4f754962f4f8e2ff973a17e96f2015ff`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only
and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
