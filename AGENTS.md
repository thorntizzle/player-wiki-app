# Campaign Player Wiki App Instructions

## Scope
- This project is the Campaign Player Wiki application repository.
- Use this project for app code, tests, frontend/backend behavior, sanitized fixtures, app documentation, local app ops, and Codex app implementation worktrees.
- Campaign canon and GM-facing source material live outside this repo. Treat the vault as an upstream source, not as app-owned code or tracked app data.
- Do not commit live SQLite files, local campaign mirrors, proprietary vault content, `campaigns/{campaign-slug}/` content, local secrets, or machine-local paths.

## Vault Bridge
- Use `LINDEN_VAULT_ROOT` when app tooling needs to read the local Linden Pass vault.
- Do not hard-code a personal vault path in tracked app files.
- Do not copy vault content into tracked app fixtures unless the content is sanitized, player-facing, and explicitly intended to become part of the app repo.
- Publication/import flows are downstream from vault to app. The app repo does not become the campaign canon source of truth.

## Worktrees
- Use permanent Codex worktrees for parallel app implementation lanes.
- Keep each worktree lane bounded to a feature, module cluster, or roadmap slice with clear file ownership.
- Before code work, start from `docs/current-state/INDEX.md` and the narrow current-state or specialist reference that owns the surface.
- Keep one active writer per module cluster. Do not revert unrelated edits from other threads, worktrees, or the user.
- For ignored app-local files that a Codex-managed worktree must copy, add only those ignored paths to `.worktreeinclude`.

## Validation And Git
- Verify app changes with the smallest realistic test, route/API check, frontend check, or local workflow that covers the touched behavior.
- Classify validation failures as touched-code regression, stale/brittle baseline, unrelated baseline failure, or tooling/environment failure.
- Before committing, confirm the repo root, inspect status and diff, and stage only files for the current slice.
- For verified app repo changes, committing and pushing are allowed as normal close-out unless the user asks for local-only or uncommitted work.
- Do not open PRs, merge, deploy, run live API writes, sync live SQLite data, or touch production/live data unless the user explicitly asks.
