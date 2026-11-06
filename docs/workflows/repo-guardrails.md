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

### Preparation And Attempt Accounting

Within authorized local preparation, ordinary helper edits and bounded
nonprivate compatibility checks may proceed under the operating model's
[proportionate route](agent-operating-model.md#proportionate-delivery). No new
human approval is needed merely for an internal draft, a changed technical
diagnosis, or a preparation failure proved to have no protected effect.

Record every actual attempt and any conservative reservation honestly. A
no-effect preparation failure does not by default consume a protected-operation
allowance; the actual grant determines its charging boundary. Existing explicit
invocation, reservation, retry, effort and candidate limits remain binding even
when no effect occurred. Never refund, reset or reinterpret historical charges.
Unknown or partial effects stop dependent actions and require readback within
existing authority before any retry decision. No automatic retry of Save/Apply,
migration, activation, restore or another protected operation follows here.

For future grants, separate bounded preparation effort from consequential
operation attempts and state the charging boundary once. A new wrapper does not
need a separate grant when the existing one covers its exact effects. Changing
an approved preservation/security guarantee still requires matching authority.

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
- **L2:** a focused disposable drill or forensic command for a concrete
  uncertainty. Select it when inspection cannot settle a critical execution
  assumption under the operating model's feasibility rule; otherwise it is
  optional. Record its scope and limits. Retired suites remain unavailable.
- **L3:** independent precommit adversarial review of the exact frozen
  candidate. Account for every changed path and affected entry-to-side-effect
  path using the [operating model's coverage and reuse rules](agent-operating-model.md#independent-review-and-reuse).
  Freshly inspect changed material and invalidated coverage through
  authorization, validation, side effects, outcome, and failure or retry.
  Challenge auth, visibility, CSRF/session, input bounds, privacy and
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

Freeze the assembled candidate before L3 and do not edit it during review.
Bind L4 to exact source and scoped operational inputs before observation.
Use the identity/change rules below; preserve failed or ambiguous evidence
outside tracked history.

## Identity And Evidence Changes

Distinguish three classes in the freeze; reference immutable artifacts rather
than recursively copying their contents:

- **Product and semantic inputs:** selected source/docs/schema/configuration
  bytes, base/tree, toolchain/locks and any requirement, source-policy or fixture
  input that can change the reviewed behavior. Changing these after assembled
  freeze creates a repair candidate and invalidates dependent evidence. Code-
  accompanying contract docs are product inputs, not administrative notes.
- **Diagnostic inputs and evidence:** the scoped dataset, invocation, environment,
  observations and review receipts. A change invalidates dependent claims;
  it does not itself establish a source fix. An unchanged-source environment
  rerun requires its existing bounded allowance and a changed diagnosis.
  Changed semantic fixture/configuration inputs follow the product rule.
- **Operational targets and results:** actor/permission, logical target
  generation/state, relevant source/policy versions, allowed operation and
  resulting revisions. An approved revision advance is an outcome, not a new
  source candidate. Relevant external drift still rejects stale operations;
  an archive hash proves custody, not current apply authority. Unrelated
  sign-in or database activity is not automatically relevant character drift.

A forward administrative correction may fix a current pointer, transcription
or status observation outside the frozen product/input manifest when exact
source, semantic inputs, authority, requirements and historical verdicts remain
unchanged. Preserve the original and name the correction. It cannot provide
missing review coverage, repair a malformed frozen envelope, or reinterpret
readiness/acceptance without independent appraisal of affected evidence.
A failed frozen envelope remains failed; any independently appraised successor
evidence record preserves that original verdict rather than rewriting it.
Record evidence failures against their actual class and existing effort/rerun
limits; do not label them source defects or create unlimited free retries.
If relevant source/input equivalence cannot be proved, invalidate the affected
claim rather than calling the correction cosmetic.

[Worktrees](worktrees.md#candidate-identity-and-integration) owns fingerprint
and staging mechanics. A new workflow revision never silently changes an old
frozen manifest's format or its bound verification rules.

The default-on `incident_event_v1` stream and its operator procedure are
described in [Incident Diagnostics](../incident-diagnostics.md). Live activation
or changes to deployment configuration and monitors still require separate
authority; a local candidate does not deploy them.

## Git Sequencing

Inspect status/diff before and after changes. Stage only intended files. Do not
commit or push without explicit user authority. Never integrate a rejected
candidate or remove a lane without exact cleanup authority and unique-work checks.
