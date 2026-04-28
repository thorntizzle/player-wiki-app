# Roadmap Automation Reference

Use this reference when you want to launch one of the Codex-driven roadmap runners from PowerShell.

These scripts live under `my_scripts\scripts\roadmaps` and drive focused Codex passes against the app roadmaps. Each run writes logs under `campaign_player_wiki\.local\roadmap-runs\...`.

## Base Setup

Run these commands from:

```text
C:\Users\thorn\Documents\my_scripts
```

Preferred Python:

```text
.\.venv\Scripts\python.exe
```

General notes:

- `scripts\roadmaps\run_systems_roadmap.py`, `scripts\roadmaps\run_ux_roadmap.py`, `scripts\roadmaps\run_character_needed_coverage_roadmap.py`, and `scripts\roadmaps\run_xianxia_roadmap.py` always start from the first unchecked checkbox in their roadmap.
- `scripts\roadmaps\run_feedback_roadmap.py` is selective by design. Use `--item`, `--items`, or `--all-items`.
- The roadmap runners now grant the nested Codex worker access to `C:\Users\thorn\.codex\skills` by default, so required skill-family doc updates can ship in the same pass instead of blocking on write scope.
- Nested workers default to `gpt-5.3-codex-spark`; pass `--model` to override that default per run.
- The default close-out mode is `ship`, which means the nested Codex pass is expected to commit and push verified tracked app changes unless the task ends with no tracked diff.
- When a shipped pass is only blocked by a transient Git write failure after the diff is already verified, the host wrapper can now finish the commit and push if the worker reports the intended commit subject on the `Commit:` line using the documented format. Host recovery stages tracked edits plus new untracked files under known app surfaces such as `player_wiki/`, `tests/`, and `docs/`; scratch output remains ignored and unknown untracked paths still stop the run for manual review.
- `--deploy-mode auto` tells the worker to deploy when the completed pass changes shipped app functionality.
- `--live-sync-mode auto` tells the worker to sync DB-backed or content changes that a code deploy would not carry.
- `--finish-mode local-only` keeps the pass local and suppresses commit, push, deploy, and live sync.

## Systems Roadmap

Script:

```text
.\scripts\roadmaps\run_systems_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\systems-roadmap.md
```

Common commands:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_systems_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_systems_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_systems_roadmap.py --max-tasks 2 --model gpt-5.3-codex-spark
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_systems_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_systems_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: build the next prompt and command without running Codex
- `--max-tasks N`: stop after `N` successful attempts
- `--note "..."`: append an extra instruction line to every generated prompt
- `--model <model>`: optional override for the nested model (default: `gpt-5.3-codex-spark`)

## UX Roadmap

Script:

```text
.\scripts\roadmaps\run_ux_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\ux-roadmap.md
```

Common commands:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_ux_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_ux_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_ux_roadmap.py --max-tasks 2 --model gpt-5.3-codex-spark
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_ux_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_ux_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: preview the next prompt and command
- `--max-tasks N`: stop after `N` targeted UX checkboxes
- `--note "..."`: append extra worker instructions
- `--model <model>`: optional override for the nested model (default: `gpt-5.3-codex-spark`)
- `--finish-mode local-only`: keep the whole pass local
- `--add-dir <path>`: add more writable/readable roots for the nested worker if a pass needs something beyond the default app workspace, vault root, and Codex skill tree

## Feedback Roadmap

Script:

```text
.\scripts\roadmaps\run_feedback_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\feedback-roadmap.md
```

This runner is selective. It ignores non-numbered sections like `Ongoing Intake` and only targets numbered feedback items.

List the available numbered items first:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --list-items
```

Target one item:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 35
```

Target multiple items or ranges:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --items 25,35-37
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 20 --item 35 --max-tasks 2
```

Preview the next selected pass without running it:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 35 --dry-run
```

Run against every numbered feedback item explicitly:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --all-items --max-tasks 3
```

Useful options:

- `--list-items`: show numbered feedback items with checked and unchecked counts, then exit
- `--item N`: select one item number; repeatable
- `--items 35,37-39`: select comma-separated numbers or ranges
- `--all-items`: opt in to processing every numbered feedback item
- `--model <model>`: optional override for the nested model (default: `gpt-5.3-codex-spark`)
- `--max-tasks N`: stop after `N` targeted checklist passes across the selected item set
- `--finish-mode local-only`: keep the pass local
- `--add-dir <path>`: add more writable/readable roots when a feedback item needs extra local context beyond the default app workspace, vault root, and Codex skill tree

## Character Needed Coverage

Script:

```text
.\scripts\roadmaps\run_character_needed_coverage_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\character-needed-coverage-checklists.md
```

This runner is sequential like the Systems and UX runners. Each pass targets the first unchecked checkbox in the checklist.

Common commands:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_character_needed_coverage_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_character_needed_coverage_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_character_needed_coverage_roadmap.py --max-tasks 2 --model gpt-5.3-codex-spark
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_character_needed_coverage_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_character_needed_coverage_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: preview the next prompt and command
- `--max-tasks N`: stop after `N` targeted checklist passes
- `--model <model>`: optional override for the nested model (default: `gpt-5.3-codex-spark`)
- `--note "..."`: append extra worker instructions
- `--finish-mode local-only`: keep the whole pass local
- `--add-dir <path>`: add more writable/readable roots for the nested worker if a pass needs something beyond the default app workspace, vault root, and Codex skill tree

## Xianxia Roadmap

Script:

```text
.\scripts\roadmaps\run_xianxia_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\xianxia-implementation-roadmap.md
```

This runner is sequential and only targets unchecked items under `Milestone 1 Checklist`. The deferred `Milestone 2 Deferred Backlog` checkboxes are ignored.

Common commands:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_xianxia_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_xianxia_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_xianxia_roadmap.py --max-tasks 2 --model gpt-5.3-codex-spark
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_xianxia_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_xianxia_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: preview the next Milestone 1 prompt and command
- `--max-tasks N`: stop after `N` targeted Milestone 1 checklist passes
- `--model <model>`: optional override for the nested model (default: `gpt-5.3-codex-spark`)
- `--note "..."`: append extra worker instructions
- `--finish-mode local-only`: keep the whole pass local
- `--add-dir <path>`: add more writable/readable roots for the nested worker if a pass needs something beyond the default app workspace, vault root, and Codex skill tree

## Log Output

Each runner creates a timestamped run folder under:

- Systems: `campaign_player_wiki\.local\roadmap-runs\systems\`
- UX: `campaign_player_wiki\.local\roadmap-runs\ux\`
- Feedback: `campaign_player_wiki\.local\roadmap-runs\feedback\`
- Character Needed Coverage: `campaign_player_wiki\.local\roadmap-runs\character-needed-coverage\`
- Xianxia: `campaign_player_wiki\.local\roadmap-runs\xianxia\`

Typical run artifacts:

- `*-prompt.txt`: the exact prompt sent to the nested Codex worker
- `*-console.log`: streamed command output
- `*-last-message.md`: the worker's final message
- `events.jsonl`: per-attempt event log

If the nested worker verifies the change but gets stuck only on commit or push close-out, use this `Commit:` line format in the worker response so the host wrapper can recover it automatically on later runs:

```text
Commit: intended subject `Describe the shipped change`; local commit/push blocked by <exact error>
```

## Recommended Starting Pattern

When you want to inspect a run before letting it modify anything:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 35 --dry-run
```

When you want one bounded live pass:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 35 --max-tasks 1
```

When you want a local-only experiment:

```powershell
.\.venv\Scripts\python.exe .\scripts\roadmaps\run_feedback_roadmap.py --item 35 --max-tasks 1 --finish-mode local-only
```
