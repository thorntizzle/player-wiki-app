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
exact requirements lock(s); relevant pytest/configuration, migrations, fixtures,
source-data classification, and environment class. Fail fast on mismatch and
repeat after relevant drift. Do not install or upgrade dependencies outside the
authorized scope. Do not rely on bare `python` from `PATH`.

## Documentation-Only Validation

Ordinary docs: owned diff/status, `git diff --check`, formatting, links/anchors,
and factual consistency. Canonical workflow/plan/policy/requirements/migration/
runbook docs add one focused independent semantic review. Protected/live data
changes are never documentation-only. Do not run unrelated executable gates.

## Validation Ladder

- **L1:** smallest targeted pytest/static check for the owned change.
- **L2:** affected domain/integration, migration, security, reconciliation, or browser checks implicated by the lane.
- **L3:** independent exact-candidate sweep using the project-declared full local suite plus every meaningful affected browser/security/data-custody check.
- **L4:** hosted CI, Fly, production browser/health, deploy, migration, backup/restore, or live-data evidence only with explicit authority.

Local/synthetic evidence never substitutes for named live evidence. Freeze the
candidate before L3/L4 and do not edit it during the sweep. Preserve failed or
ambiguous evidence outside tracked history.

## Git Sequencing

Inspect status/diff before and after changes. Stage only intended files. Do not
commit or push without explicit user authority. Never integrate a rejected
candidate or remove a lane without exact cleanup authority and unique-work checks.
