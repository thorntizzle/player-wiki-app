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
| Flask rewrite Phase 6 (70a + empty 7099 disposed; 8160 + acd9 junctions unlinked; four junction-bearing HOLD) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 393341 | `9BBD8928C8E48A2FF8159282A1F3FA601E1DB60A98BBA618A4B326B34F28AA6F` | `2026-07-22T02:09:28.5397883Z` |

The Phase 6 row anchors the same Publisher's exact non-recursive, non-force
unlink of only the approved `acd9` junction after fresh no-follow and handle/
access preflight. Post-proof found the exact junction and its absent internal
sibling target absent; the populated root remained ordinary, unregistered,
reparse-free, and payload-unchanged at 73,517 files, 42,717 ordinary
directories, and 2,102,823,184 bytes. The exact `C:\cpwv` boundary was unchanged
at 86 names with SHA-256
`6FD127BB9B39F1B2A767E7C907D0B43ABAC855E50FC16595493016A55E880022`.
Local and remote `main` were unchanged, clean, and equal at
`690a53d70ca9ba0987184fb20a457c9af6e5944e`, tree
`9cc96531e4dc2b1ce008b310f84d7710960d614a`. Exact `70a` and empty `7099`
remain absent. Parked `8160` remains present, reparse-free, and payload-
unchanged on its deferred exact-root disposal `HOLD`; the other four populated
roots remain present on their serial item-specific junction-bearing `HOLD`s.
No exact-root Force was exercised. `acd9` root deletion/Force remain
unauthorized. The exact ignored residual manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 22,775
bytes, SHA-256
`5DB67FE25529EC667F9C5CCC085C36AAB64EF92D32712DCF721AAB1FE04D9953`.
The latest pushed documentation/evidence identity before this refresh is
`690a53d70ca9ba0987184fb20a457c9af6e5944e`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only
and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
