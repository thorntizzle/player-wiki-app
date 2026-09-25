# Repo Guardrails

Status: accepted workflow reference

## Scope, Data, And Side Effects

- User-authorized tracked changes grant only the least-powerful local repo-write scope needed.
- Commit, push, protected-target integration, PR, merge, deploy, live content,
  database, credential, destructive, and unusual branch/remote operations
  require explicit matching authority.
- Keep live SQLite, campaign/vault content, secrets, credentials, backups,
  proprietary sources, personal paths, private identifiers, and protected
  evidence out of Git.
- Preserve authorization, visibility, CSRF, session, data-custody, bounded-input,
  migration, and player-safe publication boundaries.

## Exact Toolchain Preflight

Before implementation validation, prove repository/branch/worktree/base/head
identity; `.python-version`; the configured shared environment or `local.ps1`;
exact requirements lock(s); relevant configuration, migrations, source-data
classification, and environment class. Fail fast on mismatch and
repeat after relevant drift. Do not install or upgrade dependencies outside the
authorized scope. Do not rely on bare `python` from `PATH`.

## Documentation-Only Validation

Ordinary docs: owned diff/status, `git diff --check`, formatting, links/anchors,
and factual consistency. Canonical workflow/plan/policy/requirements/migration/
runbook docs add one focused independent semantic review. Protected/live data
changes are never documentation-only. Do not run unrelated executable gates.

## Diagnostic Review Ladder

- **L1:** author code/diff and document-consistency inspection of the owned
  change, including privacy and behavior preservation.
- **L2:** an optional focused disposable drill or forensic command only when a
  concrete uncertainty needs resolution. Record its scope and limits.
- **L3:** independent precommit adversarial review of the exact frozen
  candidate. Read every changed path and trace each affected path from entry
  through authorization, validation, side effects, outcome, and failure or
  retry. Challenge auth, visibility, CSRF/session, input bounds, privacy and
  secrets, protected-data custody, compatibility, concurrency/idempotency,
  and partial-commit semantics as applicable. Source, docs, and dormant tests
  are read-only evidence; canonical policy docs receive a focused independent
  semantic review. Acceptance requires no unresolved blocking finding
  and an explicit account of residual uncertainty; otherwise return a Frozen
  Failure Inventory.
- **L4:** hosted/live observation only with explicit matching authority. Local
  drills cannot substitute for live evidence.

The automated test suite and its dedicated `local.ps1` actions are retired.
No automated test, browser suite, hosted CI, complete suite, or routine manual
drill is a standing acceptance gate. A freeze may name a focused diagnostic command,
but doing so does not restore a general gate. Current
diagnostic-first policy supersedes older domain/current-state test guidance as
mandatory workflow. Candidate freeze, exact fingerprint, independent review,
bounded repairs, toolchain/input identity, and operator gates remain required.

Every actionable L3 finding records its location, triggering path, expected
and actual behavior, impact/severity, evidence, root cause, and affected scope.
The Verifier does not edit the candidate. Resolve blockers through the next
approved repair cycle; do not accept by leaving them as residual uncertainty.

Freeze the candidate before L3/L4 and do not edit it during review. Any
candidate byte or relevant-input change after freeze creates a repair
candidate. An unchanged-candidate environment rerun is separately bounded and
requires a changed diagnosis. Preserve failed or ambiguous evidence outside
tracked history.

The default-on `incident_event_v1` stream and its operator procedure are
described in [Incident Diagnostics](../incident-diagnostics.md). Live activation
or changes to deployment configuration and monitors still require separate
authority; a local candidate does not deploy them.

## Git Sequencing

Inspect status/diff before and after changes. Stage only intended files. Do not
commit or push without explicit user authority. Never integrate a rejected
candidate or remove a lane without exact cleanup authority and unique-work checks.
