# Roadmap Automation Reference

Use this reference when you want to launch one of the Codex-driven roadmap runners from PowerShell.

These scripts live in the `my_scripts` root and drive focused Codex passes against the app roadmaps. Each run writes logs under `campaign_player_wiki\.local\roadmap-runs\...`.

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

- `run_systems_roadmap.py` and `run_ux_roadmap.py` always start from the first unchecked checkbox in their roadmap.
- `run_feedback_roadmap.py` is selective by design. Use `--item`, `--items`, or `--all-items`.
- The default close-out mode is `ship`, which means the nested Codex pass is expected to commit and push verified tracked app changes unless the task ends with no tracked diff.
- `--deploy-mode auto` tells the worker to deploy when the completed pass changes shipped app functionality.
- `--live-sync-mode auto` tells the worker to sync DB-backed or content changes that a code deploy would not carry.
- `--finish-mode local-only` keeps the pass local and suppresses commit, push, deploy, and live sync.

## Systems Roadmap

Script:

```text
.\run_systems_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\systems-roadmap.md
```

Common commands:

```powershell
.\.venv\Scripts\python.exe .\run_systems_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\run_systems_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\run_systems_roadmap.py --max-tasks 2 --model gpt-5.3-codex
.\.venv\Scripts\python.exe .\run_systems_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\run_systems_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: build the next prompt and command without running Codex
- `--max-tasks N`: stop after `N` successful attempts
- `--note "..."`: append an extra instruction line to every generated prompt
- `--model <model>`: override the model used by `run_codex_action.py`

## UX Roadmap

Script:

```text
.\run_ux_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\ux-roadmap.md
```

Common commands:

```powershell
.\.venv\Scripts\python.exe .\run_ux_roadmap.py --dry-run
.\.venv\Scripts\python.exe .\run_ux_roadmap.py --max-tasks 1
.\.venv\Scripts\python.exe .\run_ux_roadmap.py --max-tasks 2 --model gpt-5.3-codex
.\.venv\Scripts\python.exe .\run_ux_roadmap.py --max-tasks 1 --finish-mode local-only
.\.venv\Scripts\python.exe .\run_ux_roadmap.py --max-tasks 1 --deploy-mode auto --live-sync-mode auto
```

Useful options:

- `--dry-run`: preview the next prompt and command
- `--max-tasks N`: stop after `N` targeted UX checkboxes
- `--note "..."`: append extra worker instructions
- `--finish-mode local-only`: keep the whole pass local

## Feedback Roadmap

Script:

```text
.\run_feedback_roadmap.py
```

Roadmap:

```text
.\campaign_player_wiki\.local\feedback-roadmap.md
```

This runner is selective. It ignores non-numbered sections like `Ongoing Intake` and only targets numbered feedback items.

List the available numbered items first:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --list-items
```

Target one item:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 35
```

Target multiple items or ranges:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --items 25,35-37
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 20 --item 35 --max-tasks 2
```

Preview the next selected pass without running it:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 35 --dry-run
```

Run against every numbered feedback item explicitly:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --all-items --max-tasks 3
```

Useful options:

- `--list-items`: show numbered feedback items with checked and unchecked counts, then exit
- `--item N`: select one item number; repeatable
- `--items 35,37-39`: select comma-separated numbers or ranges
- `--all-items`: opt in to processing every numbered feedback item
- `--max-tasks N`: stop after `N` targeted checklist passes across the selected item set
- `--finish-mode local-only`: keep the pass local

## Log Output

Each runner creates a timestamped run folder under:

- Systems: `campaign_player_wiki\.local\roadmap-runs\systems\`
- UX: `campaign_player_wiki\.local\roadmap-runs\ux\`
- Feedback: `campaign_player_wiki\.local\roadmap-runs\feedback\`

Typical run artifacts:

- `*-prompt.txt`: the exact prompt sent to the nested Codex worker
- `*-console.log`: streamed command output
- `*-last-message.md`: the worker's final message
- `events.jsonl`: per-attempt event log

## Recommended Starting Pattern

When you want to inspect a run before letting it modify anything:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 35 --dry-run
```

When you want one bounded live pass:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 35 --max-tasks 1
```

When you want a local-only experiment:

```powershell
.\.venv\Scripts\python.exe .\run_feedback_roadmap.py --item 35 --max-tasks 1 --finish-mode local-only
```
