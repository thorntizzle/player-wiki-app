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

## Roadmap Authoring Pattern

Use this pattern when turning a new app feature into roadmap work for Codex-driven implementation.

The goal is not just to capture requirements. The goal is to shape the roadmap so each unchecked checkbox can become one precise worker assignment with a small file ownership surface, clear verification, and a clean close-out note.

### Feature Intake

Start each feature section with the durable product facts:

- Name the feature and the user-facing outcome.
- State the system lane or app surface it belongs to, such as Xianxia character sheets, Systems Wiki, live session, or DND-5E character tools.
- Record the key domain vocabulary and canonical values.
- Decide what is deliberately out of scope for this milestone.
- Call out compatibility boundaries, especially behavior that must not change in other systems.

### Checklist Shape

Write one unchecked checkbox per implementation step. Each checkbox should be small enough that a nested worker can implement it without solving the whole feature.

Prefer steps in this order:

- [ ] Vocabulary, constants, and normalization helpers.
- [ ] Policy helpers or capability gates.
- [ ] Storage schema, data shape, or migration/preservation behavior.
- [ ] Source, catalog, seed, or Systems-entry representation.
- [ ] Importer or legacy-data conversion behavior.
- [ ] Mutation routes, services, or command handlers.
- [ ] Presenter/context changes.
- [ ] Template or frontend controls.
- [ ] Focused tests and regression coverage.
- [ ] Skill docs, repo-map, and roadmap close-out updates.
- [ ] Explicit non-goals that keep later milestones from leaking into the current pass.

Do not bury several implementation phases under one checkbox. If a worker would need to touch unrelated modules, split the item.

### Worker-Sized Item Template

Use this sentence shape when a checklist item needs more precision:

```markdown
- [ ] Add <specific behavior> in <owned file/module/surface>, covering <inputs/state/UI>, preserving <compatibility boundary>, and validating with <focused test target>.
```

Good checklist items usually name at least one of these:

- The data contract or canonical vocabulary being introduced.
- The existing helper, route lane, presenter, template, or store that should own the change.
- The backward-compatibility or preservation requirement.
- The smallest realistic test or workflow check.
- The thing this item must not implement.

### Completion Notes

When a worker finishes a checkbox, leave the roadmap useful for the next worker:

- Mark only the completed checkbox.
- Add a short `Completed scope:` note under that item.
- Mention the important files, behavior, and intentionally deferred scope.
- Add the exact validation command and result when tests or workflow checks ran.
- If the implementation changed routing, ownership, or app architecture assumptions, update the relevant skill reference docs and repo map in the same pass.

### Scope Guardrails

Every feature roadmap should keep deferred work visible but separate. Use explicit boundary items when a feature sits next to tempting larger work, such as combat automation, deploy behavior, live sync, source-policy changes, or cross-system DND-5E behavior.

When a roadmap item is only planning or documentation, say so in its completion note. When it changes shipped app behavior, the worker should follow the normal ship close-out: tests, roadmap update, skill-doc maintenance when applicable, commit, and push unless the run is explicitly local-only.

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
