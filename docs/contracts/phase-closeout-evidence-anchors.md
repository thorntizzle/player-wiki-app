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
| Flask rewrite Phase 6 (recovery audited; 7099 HOLD; 70a junction recovery-ready) | `2c6774b269995320c149dd81e59d842304e740a8` | `c297efdfaa67e6aa98bef3d52194100fc47948f0` | `.local/roadmaps/flask-rewrite-phase6-lifecycle-evidence.md` | 378615 | `AA8A07DCFD89E579173CE37E5016B7A4713D8439F94BAD05688C31503814F332` | `2026-07-21T22:27:55.5819208Z` |

The Phase 6 row anchors the recovery-audited canonical record. Git cleanup is
main-only. Exact empty unregistered `7099` remains on `HOLD` pending a user-
controlled Codex desktop exit/restart and fresh Publisher preflight. The exact
`70a` junction is recovery-ready under its existing literal-unlink approval;
its root-force gate remains withheld. The other six populated roots remain on
`HOLD`. The exact ignored residual manifest is
`.local/roadmaps/flask-rewrite-phase6-residual-safety-manifest.md`: 12,630
bytes, SHA-256
`594B11C4E0EC000EED2EB6C5DF1A755A8AA592B30BEF7EC0097861840F8DFCA1`.
The latest pushed documentation/evidence identity before this refresh is
`d2f8130b4e173156505b9ca4398de57a5b72d63b`. This anchor refresh is local-only
pending independent verification and push; it is documentation/evidence only
and was not redeployed.

For each future row, verify the record from the canonical main worktree after
final postmortem replacement. Record only the repository-relative path, exact
byte count, uppercase SHA-256, accepted commit/tree, and finalization time.
Never record secret contents, personal absolute paths, private campaign facts,
or hashes of secret-bearing material.
