# Workspace Boundaries And Worktrees

Last updated: 2026-06-27

## Owns

- The split between the Campaign Player Wiki app project, the Linden Pass vault project, and the general DND tooling workspace.
- The app-side bridge contract for reading vault source material without turning the app repo into the canon source.
- Codex permanent worktree expectations for app implementation lanes.

## Current Workspace Split

- `campaign_player_wiki` is the app implementation project. Use it for app code, tests, frontend/backend behavior, sanitized fixtures, app docs, local app ops, and permanent Codex worktrees.
- The Linden Pass vault project is the campaign source project. Use it for canon, drafts, session prep, archives, Obsidian wiki maintenance, summaries, profiles, images, and non-canon campaign work.
- The broader `my_scripts` workspace remains the tooling and orchestration workspace for scripts, virtualenvs, generated helpers, and task scratch.

## App/Vault Bridge

- The vault is upstream of the app. App publication, import, or sync work should flow from vault source material into player-facing app data by an explicit workflow.
- Use `LINDEN_VAULT_ROOT` for local tooling that needs to read the vault.
- Keep machine-local vault paths in local environment configuration, shell profile state, or ignored local files. Do not hard-code those paths in tracked app files.
- Tracked app data should remain limited to app code, docs, tests, and sanitized fixtures. Do not track live SQLite files, proprietary vault material, local campaign mirrors, or `campaigns/{campaign-slug}/` content.
- If a workflow creates new campaign facts, promotes canon, publishes player-facing content, touches live data, or copies vault material into tracked app files, stop for an explicit user decision unless the current request already authorized that action.

## Permanent Worktree Contract

- Permanent app worktrees are long-lived implementation lanes for app work only.
- Give each lane a narrow feature, module cluster, or roadmap slice with clear file ownership.
- Keep app worktree threads rooted in the `campaign_player_wiki` project so they inherit the app repo instructions and use Git worktrees correctly.
- Use separate lanes for independent work such as frontend surfaces, backend/API changes, validation/review, or documentation cleanup when file ownership does not overlap.
- Do not use app worktrees for direct vault editing. Use the Linden Pass vault project for campaign content work.

## Local Setup Notes

- `LINDEN_VAULT_ROOT` is optional for ordinary app code work and required only for local tools that need to inspect or import vault source material.
- Codex-managed worktrees start from tracked files. Add a `.worktreeinclude` file only when an ignored app-local config file is actually required in every managed worktree.
- Do not list tracked files in `.worktreeinclude`.
- `.worktreeinclude` should copy only non-secret local config needed for setup. Prefer environment variables for sensitive values.

## Source Pointers

- `AGENTS.md`
- `.gitignore`
- `docs/current-state/INDEX.md`
- `docs/current-state/published-wiki.md`
- `docs/current-state/ops-deploy.md`
- `.local/roadmaps/*-backlog.md`
