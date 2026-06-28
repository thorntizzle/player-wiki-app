"""Guarded scaffolding for TypeScript staging rehearsal evidence.

The helper creates disposable transcript folders and captures deterministic
file/SQLite snapshots for copied-data rehearsal targets. It intentionally does
not mutate, restore, deploy, or sync data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


FAMILY_TABLES: dict[str, tuple[str, ...]] = {
    "content-character": (
        "character_state",
        "character_assignments",
        "audit_events",
    ),
    "combat": (
        "campaign_combat_trackers",
        "campaign_combatants",
        "campaign_combat_conditions",
        "campaign_combatant_resource_counters",
        "campaign_combatant_resource_notes",
        "character_state",
    ),
    "session": (
        "campaign_sessions",
        "campaign_session_states",
        "campaign_session_messages",
        "campaign_session_articles",
        "campaign_session_article_images",
    ),
    "systems": (
        "systems_libraries",
        "systems_sources",
        "systems_entries",
        "systems_import_runs",
        "systems_shared_entry_edit_events",
        "systems_entry_links",
        "campaign_system_policies",
        "campaign_enabled_sources",
        "campaign_entry_overrides",
    ),
    "dm-content": (
        "campaign_dm_statblocks",
        "campaign_dm_condition_definitions",
    ),
    "publishing": (
        "campaign_pages",
        "campaign_page_sync_state",
    ),
    "rollback-cutover": (
        "users",
        "user_preferences",
        "campaign_memberships",
        "campaign_visibility_settings",
        "character_assignments",
        "api_tokens",
        "auth_audit_log",
        "character_state",
        "campaign_sessions",
        "campaign_session_states",
        "campaign_session_messages",
        "campaign_session_articles",
        "campaign_session_article_images",
        "campaign_dm_statblocks",
        "campaign_dm_condition_definitions",
        "campaign_combat_trackers",
        "campaign_combatants",
        "campaign_combat_conditions",
        "campaign_combatant_resource_counters",
        "campaign_combatant_resource_notes",
        "systems_libraries",
        "systems_sources",
        "systems_entries",
        "systems_import_runs",
        "systems_shared_entry_edit_events",
        "systems_entry_links",
        "campaign_system_policies",
        "campaign_enabled_sources",
        "campaign_entry_overrides",
        "campaign_pages",
        "campaign_page_sync_state",
    ),
}


FAMILY_REHEARSAL_GUIDES: dict[str, dict[str, tuple[str, ...] | str]] = {
    "content-character": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "PUT /api/v1/campaigns/<slug>/content/characters/<characterSlug>",
            "DELETE /api/v1/campaigns/<slug>/content/characters/<characterSlug>",
            "Character Controls delete path if it reuses content-character deletion.",
        ),
        "baseline": (
            "Record selected character definition/import files and portrait asset manifests.",
            "Record character detail API samples for DND-5E and Xianxia characters when both are present.",
            "Record `character_state` JSON, revision, and system-specific mutable-state fields for selected characters.",
            "Record `character_assignments` rows for selected assigned and unassigned characters.",
            "Record any existing audit rows that the copied staging-equivalent snapshot already contains.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Update one DND-5E character definition or import field without inventing private campaign content.",
            "Update one Xianxia character field when present and record mutable-state preservation.",
            "Delete one disposable or operator-approved character and record state and assignment cleanup flags.",
            "Record response fields such as `state_created`, `deleted_state`, and `deleted_assignment`.",
        ),
        "equivalence": (
            "Restored character files, import files, portrait asset bytes, and manifests must match baseline.",
            "Restored `character_state` JSON and revision values must match baseline for sampled characters.",
            "Restored assignments and sampled character detail responses must match baseline or list exact accepted differences.",
            "Any missing portrait, orphaned assignment, unexpected state deletion, or changed source file keeps the gate blocked.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "combat": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "GET /api/v1/campaigns/<slug>/combat",
            "GET /api/v1/campaigns/<slug>/combat/live-state",
            "POST /api/v1/campaigns/<slug>/combat/player-combatants",
            "POST /api/v1/campaigns/<slug>/combat/npc-combatants",
            "POST /api/v1/campaigns/<slug>/combat/statblock-combatants",
            "POST /api/v1/campaigns/<slug>/combat/systems-monsters",
            "POST /api/v1/campaigns/<slug>/combat/advance-turn",
            "POST /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/set-current",
            "PATCH /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/turn",
            "PATCH /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/vitals",
            "PATCH /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/resources",
            "PATCH /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/npc-resources",
            "POST /api/v1/campaigns/<slug>/combat/combatants/<combatantId>/conditions",
            "PATCH /api/v1/campaigns/<slug>/combat/conditions/<conditionId>",
            "DELETE /api/v1/campaigns/<slug>/combat/conditions/<conditionId>",
            "DELETE /api/v1/campaigns/<slug>/combat/combatants/<combatantId>",
            "POST /api/v1/campaigns/<slug>/combat/clear",
        ),
        "baseline": (
            "Save player Combat, Combat live-state, DM Status, and DM Controls response samples.",
            "Record tracker row, ordered combatants, current turn, round, and revision values.",
            "Record selected player-character state rows that can be mirrored by vitals/resources writes.",
            "Record source-backed NPC resource counters and mechanic notes when present.",
            "Record condition rows and custom condition option payloads.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Add one player combatant and verify character-state initialization or mirror behavior.",
            "Add one manual NPC, then update vitals, action economy, and movement.",
            "Add one source-backed combatant from DM Content or Systems when the copied data supports it.",
            "Add, update, and delete one condition on a non-player combatant.",
            "Exercise set-current, advance-turn, and turn-value editing with revision guards.",
            "Delete one combatant and clear the tracker after post-mutation evidence is captured.",
        ),
        "equivalence": (
            "Restored tracker rows must match baseline round, current turn, and revision values.",
            "Restored combatants, conditions, counters, and notes must match baseline row counts and sampled rows.",
            "Restored linked character_state JSON and revision values must match baseline.",
            "Restored player Combat, DM Status, DM Controls, and live-state samples must match baseline or list exact accepted differences.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "session": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "GET /api/v1/campaigns/<slug>/session",
            "GET /api/v1/campaigns/<slug>/session/live-state",
            "POST /api/v1/campaigns/<slug>/session/start",
            "POST /api/v1/campaigns/<slug>/session/close",
            "POST /api/v1/campaigns/<slug>/session/messages",
            "POST /api/v1/campaigns/<slug>/session/articles",
            "PUT /api/v1/campaigns/<slug>/session/articles/<articleId>",
            "POST /api/v1/campaigns/<slug>/session/articles/<articleId>/reveal",
            "DELETE /api/v1/campaigns/<slug>/session/articles/<articleId>",
            "DELETE /api/v1/campaigns/<slug>/session/logs/<sessionId>",
        ),
        "baseline": (
            "Record live Session, DM Session, and closed-log API samples for active and closed sessions when present.",
            "Record `campaign_sessions`, `campaign_session_states`, and `campaign_session_messages` row counts and selected rows.",
            "Record staged/revealed article rows, image rows, and representative image byte hashes.",
            "Record current revision/view-token behavior for sampled player and DM views.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Start or close one operator-approved copied session and record state transition payloads.",
            "Send global, DM-only, and player-targeted messages with actor role and audience evidence.",
            "Create, update, reveal, delete, and clear staged articles only when copied data supports those actions.",
            "Delete one copied closed log only after baseline evidence and backup are recorded.",
        ),
        "equivalence": (
            "Restored sessions, state rows, messages, article rows, image rows, and image hashes must match baseline.",
            "Restored player and DM live-state samples must match baseline or list exact accepted differences.",
            "Audience filtering, revisions, and unchanged-response behavior must match baseline after restore.",
            "Any leaked DM-only message, missing image, orphaned article, or changed closed log keeps the gate blocked.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "systems": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "GET /api/v1/campaigns/<slug>/systems",
            "GET /api/v1/campaigns/<slug>/systems/sources/<sourceId>",
            "GET /api/v1/campaigns/<slug>/systems/entries/<entryKey>",
            "PUT /api/v1/campaigns/<slug>/systems/sources",
            "PUT /api/v1/campaigns/<slug>/systems/overrides/<entryKey>",
            "POST /api/v1/campaigns/<slug>/systems/custom-entries",
            "PUT /api/v1/campaigns/<slug>/systems/custom-entries/<entrySlug>",
            "POST /api/v1/campaigns/<slug>/systems/item-mechanics/import",
            "POST /api/v1/systems/import-dnd5e-source when explicitly approved for the copied snapshot.",
        ),
        "baseline": (
            "Record Systems landing, source, entry, and DM Content Systems API samples.",
            "Record libraries, sources, entries, import runs, entry links, policies, enabled sources, and overrides.",
            "Record custom entries, archived entries, campaign overrides, and proprietary acknowledgement state when present.",
            "Record shared-source import history and media-stripping expectations before any import action.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Update one source policy and verify public/private/proprietary visibility decisions.",
            "Create, update, archive, and restore one custom entry when copied data supports it.",
            "Apply and remove one entry override while preserving source entry identity.",
            "Run item mechanics import or shared DND-5E import only when the operator explicitly approved that copied snapshot action.",
        ),
        "equivalence": (
            "Restored library, source, entry, import-run, link, policy, enabled-source, and override rows must match baseline.",
            "Restored landing/source/entry/DM Content Systems samples must match baseline or list exact accepted differences.",
            "Shared-source import decisions and media stripping must be recorded before any staging snapshot label change.",
            "Any visibility regression, orphaned custom entry, changed source row, or unresolved import delta keeps the gate blocked.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "dm-content": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "GET /api/v1/campaigns/<slug>/dm-content",
            "POST /api/v1/campaigns/<slug>/dm-content/statblocks",
            "PUT /api/v1/campaigns/<slug>/dm-content/statblocks/<statblockId>",
            "DELETE /api/v1/campaigns/<slug>/dm-content/statblocks/<statblockId>",
            "POST /api/v1/campaigns/<slug>/dm-content/conditions",
            "PUT /api/v1/campaigns/<slug>/dm-content/conditions/<conditionDefinitionId>",
            "DELETE /api/v1/campaigns/<slug>/dm-content/conditions/<conditionDefinitionId>",
            "GET /api/v1/campaigns/<slug>/combat/setup choices that consume DM Content rows.",
        ),
        "baseline": (
            "Record DM Content payload samples and Combat setup choices that consume statblocks or conditions.",
            "Record `campaign_dm_statblocks` rows, parser output summaries, actor columns, and audit rows if present.",
            "Record `campaign_dm_condition_definitions` rows and custom condition option payloads.",
            "Record duplicate-condition and validation baselines when copied data already contains edge cases.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Create, update, and delete one copied statblock while recording parser output and actor metadata.",
            "Create, update, and delete one copied custom condition while recording duplicate/validation behavior.",
            "Verify Combat setup choices reflect copied mutations before restore and return to baseline after restore.",
        ),
        "equivalence": (
            "Restored statblock rows, condition rows, parser summaries, and actor/audit evidence must match baseline.",
            "Restored DM Content and Combat setup payloads must match baseline or list exact accepted differences.",
            "Any parser drift, stale Combat option, missing actor evidence, or unexpected condition duplicate keeps the gate blocked.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "publishing": {
        "label_before": "copied-data rollback ready",
        "label_after": "staging snapshot ready",
        "routes": (
            "GET /api/v1/campaigns/<slug>/wiki",
            "GET /api/v1/campaigns/<slug>/wiki/pages/<pageSlug>",
            "PATCH /api/v1/campaigns/<slug>/content/config",
            "PUT /api/v1/campaigns/<slug>/content/pages/<pageRef>",
            "DELETE /api/v1/campaigns/<slug>/content/pages/<pageRef>",
            "PUT /api/v1/campaigns/<slug>/content/assets/<assetRef>",
            "DELETE /api/v1/campaigns/<slug>/content/assets/<assetRef>",
            "GET protected asset byte-serving routes for selected copied assets.",
        ),
        "baseline": (
            "Record `campaign.yaml`, selected content Markdown files, selected assets, and file hashes.",
            "Record `campaign_pages` and `campaign_page_sync_state` rows and selected read-model payloads.",
            "Record wiki list/detail, DM Content Player Wiki, and protected asset response samples.",
            "Record provenance blockers such as character/session references when present in the copied snapshot.",
        ),
        "backup": (
            "Create a backup from the copied SQLite and copied campaigns directory only.",
            "Record archive path, command, contents summary, file count, and checksum.",
            "Confirm the backup archive path passed `check-paths` and stayed under `.task-temp/`.",
            "Record restore target path before mutation; stop if the restore target is not disposable.",
        ),
        "mutation": (
            "Patch content config and record read-model refresh behavior.",
            "Create, update, unpublish/republish, delete, and force-delete one copied page when blockers are intentionally present.",
            "Upload, read, and delete one copied-safe asset; record media type, base64 payload shape, raw bytes, and empty-dir cleanup.",
            "Record protected asset serving behavior before and after mutation.",
        ),
        "equivalence": (
            "Restored config, Markdown files, assets, file hashes, read-model rows, and sampled wiki/API responses must match baseline.",
            "Restored protected asset bytes and media types must match baseline or list exact accepted differences.",
            "Provenance blocker outcomes must be recorded before any forced delete can support a staging label.",
            "Any lost asset, stale read-model row, changed Markdown frontmatter, or unapproved image conversion delta keeps the gate blocked.",
        ),
        "safety_note": "This guide can support `staging snapshot ready` only when the source approval explicitly names a staging-equivalent snapshot and restore equivalence passes.",
    },
    "rollback-cutover": {
        "label_before": "staging snapshot ready",
        "label_after": "cutover rehearsal passed",
        "routes": (
            "Flask authority /healthz smoke before TypeScript routing changes.",
            "TypeScript /healthz smoke against copied or staging-equivalent data.",
            "Representative auth, Campaign Home, wiki, search, help, DM Content, Systems, Characters, Session, and Combat smoke paths.",
            "Rollback runtime repoint/redeploy command shape back to the last known-good Flask commit or image.",
            "Post-rollback Flask /healthz and representative player/DM smoke paths.",
        ),
        "baseline": (
            "Record the last known-good Flask commit SHA, image tag/id if available, branch, and build source.",
            "Record the TypeScript branch/commit and route snapshot/check status under rehearsal.",
            "Record pre-cutover SQLite backup command, archive path, contents summary, and checksum.",
            "Record pre-cutover campaign-content backup command, archive path, contents summary, and checksum.",
            "Record local or staging-equivalent runtime environment without real Fly app identifiers, tokens, secrets, or live paths.",
        ),
        "backup": (
            "Create both SQLite and campaign-content backups from copied or approved staging-equivalent inputs only.",
            "Record archive paths, commands, contents summaries, file counts, and checksums.",
            "Confirm every backup archive path passed `check-paths` and stayed under `.task-temp/` or an approved disposable staging scratch root.",
            "Record the Flask rollback target before TypeScript mutation begins.",
        ),
        "mutation": (
            "Run the full charter workflow smoke on copied or user-approved staging-equivalent data only.",
            "Record every TypeScript write accepted during the smoke with route/action, actor role, affected files/tables, and response payload.",
            "Classify each TypeScript data delta as revert, preserve, merge manually, or block rollback until operator decision.",
            "Record migration dry-run/startup schema evidence and any additive schema deltas before rollback.",
            "Do not run Fly deploy, live sync, live API writes, or commands pointed at production volumes in this harness.",
        ),
        "equivalence": (
            "Rollback command shape must name the Flask commit/image target and restore archive inputs, using placeholders for private app identity.",
            "Restored SQLite row counts, campaign-content hashes, and sampled API responses must match the pre-cutover baseline or list exact accepted differences.",
            "Post-rollback Flask health smoke must pass before the transcript can pass.",
            "The data-delta decision tree must resolve every TypeScript write accepted before rollback.",
            "Any unresolved delta, failed restore, failed Flask health smoke, or live-path dependency keeps the result blocked.",
        ),
        "safety_note": "This rehearsal result is not production cutover approval; PR, merge, deploy, Fly sync, and live cutover still require explicit user approval.",
    }
}


STAGING_SNAPSHOT_PREFLIGHT_DOCS: tuple[tuple[str, str], ...] = (
    (
        "docs/typescript-backend-rewrite/README.md",
        "rewrite evidence index and production-authority boundary",
    ),
    (
        "docs/typescript-backend-rewrite/cutover-readiness.md",
        "current staging-snapshot gate matrix",
    ),
    (
        "docs/typescript-backend-rewrite/staging-rehearsal-harness.md",
        "copied-data and staging-snapshot harness contract",
    ),
    (
        "docs/typescript-backend-rewrite/rollback-cutover-runbook.md",
        "rollback and full-cutover downstream evidence contract",
    ),
    (
        "docs/typescript-backend-rewrite/full-cutover-copied-workflow-smoke-2026-06-28.md",
        "latest no-live copied-data full workflow smoke limits",
    ),
    (
        "docs/current-state/ops-deploy.md",
        "local wrapper, SQLite volume, and verification boundaries",
    ),
    (
        "docs/current-state/workspace-boundaries.md",
        "app/vault/worktree split and tracked-data guardrails",
    ),
)


STAGING_SNAPSHOT_PREFLIGHT_GATES: tuple[dict[str, str], ...] = (
    {
        "family": "content-character",
        "current": "copied-data rollback ready",
        "required": "User-approved copied staging-equivalent snapshot with character files, portrait assets, character_state, and character_assignments.",
    },
    {
        "family": "session",
        "current": "copied-data rollback ready",
        "required": "Staging-equivalent session/chat/article/log/image rows plus restore equivalence for sampled player and DM responses.",
    },
    {
        "family": "combat",
        "current": "copied-data rollback ready",
        "required": "Staging-equivalent tracker, combatants, conditions, source-backed resources, linked character_state, and restore equivalence.",
    },
    {
        "family": "systems",
        "current": "copied-data rollback ready",
        "required": "Staging-equivalent Systems libraries, policies, imports, overrides, custom entries, and shared-source decision evidence.",
    },
    {
        "family": "dm-content",
        "current": "copied-data rollback ready",
        "required": "Staging-equivalent statblocks, conditions, parser outputs, Combat setup consumers, and restore equivalence.",
    },
    {
        "family": "publishing",
        "current": "copied-data rollback ready",
        "required": "Staging-equivalent content config, pages, assets, read-model rows, provenance blockers, and protected asset serving.",
    },
    {
        "family": "rollback-cutover",
        "current": "blocked until route-family staging snapshot gates pass",
        "required": "Downstream full workflow and rollback smoke only after every route-family staging-snapshot transcript is complete.",
    },
)


REHEARSAL_DIRS = ("input", "backup", "pre", "mutation", "post", "restore", "logs")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def assert_disposable_root(root: Path) -> Path:
    resolved = resolve_path(root)
    if ".task-temp" not in resolved.parts:
        raise ValueError(
            f"Rehearsal root must be inside a .task-temp directory: {resolved}"
        )
    return resolved


@dataclass(frozen=True)
class RehearsalPaths:
    root: str
    db_path: str | None = None
    campaigns_dir: str | None = None
    backup_archive: str | None = None


def validate_rehearsal_paths(
    *,
    root: Path,
    db_path: Path | None = None,
    campaigns_dir: Path | None = None,
    backup_archive: Path | None = None,
) -> RehearsalPaths:
    resolved_root = assert_disposable_root(root)
    resolved_db = resolve_path(db_path) if db_path else None
    resolved_campaigns = resolve_path(campaigns_dir) if campaigns_dir else None
    resolved_backup = resolve_path(backup_archive) if backup_archive else None

    for label, candidate in (
        ("database path", resolved_db),
        ("campaigns dir", resolved_campaigns),
        ("backup archive", resolved_backup),
    ):
        if candidate is not None and not is_relative_to(candidate, resolved_root):
            raise ValueError(
                f"{label} must resolve inside the rehearsal root {resolved_root}: {candidate}"
            )

    return RehearsalPaths(
        root=str(resolved_root),
        db_path=str(resolved_db) if resolved_db else None,
        campaigns_dir=str(resolved_campaigns) if resolved_campaigns else None,
        backup_archive=str(resolved_backup) if resolved_backup else None,
    )


def transcript_template(
    *,
    rehearsal_id: str,
    family: str,
    source_description: str,
    source_approval: str,
    root: Path,
) -> str:
    tables = "\n".join(f"- `{table}`" for table in FAMILY_TABLES[family])
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    family_guide = family_guide_markdown(family)
    return f"""# Rehearsal Transcript: {rehearsal_id}

Generated: {created}

## Scope
- Write family: {family}
- Routes/actions:
- Readiness target:
- Source snapshot description: {source_description}
- Source snapshot approval: {source_approval}

## Safety Confirmation
- Rehearsal root: `{root}`
- Copied SQLite:
- Copied campaigns dir:
- Refused live paths:
- `.local` visibility:

## Baseline Evidence
- Flask authority commit:
- TypeScript commit:
- Route snapshot/check status:
- Pre-mutation file manifest: `pre/manifest.json`
- Pre-mutation SQL tables:
{tables}
- Baseline API samples:

## Backup
- Command:
- Archive path:
- Archive contents summary:
- Result:

## Mutation
- TypeScript runtime command:
- Environment:
- Request payloads:
- Response payloads:
- Expected changed files/tables:
- Observed changed files/tables:

## Restore
- Command:
- Target:
- Result:

## Equivalence
- File hash comparison:
- SQL row-count comparison:
- API response comparison:
- Known acceptable differences:
- Unexpected differences:

## Decision
- Result: pass | fail | blocked
- Label before:
- Label after:
- Follow-up required:
{family_guide}
"""


def bullet_list(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def family_guide_markdown(family: str) -> str:
    guide = FAMILY_REHEARSAL_GUIDES.get(family)
    if not guide:
        return ""
    return f"""

## Family-Specific Rehearsal Guide

### Routes And Actions
{bullet_list(guide["routes"])}

### Baseline Evidence Checklist
{bullet_list(guide["baseline"])}

### Backup Evidence Checklist
{bullet_list(guide["backup"])}

### Mutation Sequence
{bullet_list(guide["mutation"])}

### Restore Equivalence Requirements
{bullet_list(guide["equivalence"])}

### Honest Label Transition
- Label before: `{guide["label_before"]}`
- Label after only if backup, mutation, restore, and equivalence all pass: `{guide["label_after"]}`
- {guide["safety_note"]}
"""


def staging_snapshot_preflight_markdown(*, family: str | None = None) -> str:
    if family is not None and family not in FAMILY_TABLES:
        raise ValueError(f"Unsupported write family: {family}")

    selected_gates = [
        gate
        for gate in STAGING_SNAPSHOT_PREFLIGHT_GATES
        if family is None or gate["family"] == family
    ]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    source_docs = "\n".join(
        f"- [ ] `{path}` - {purpose}"
        for path, purpose in STAGING_SNAPSHOT_PREFLIGHT_DOCS
    )
    gate_sections = "\n\n".join(
        staging_snapshot_gate_markdown(gate["family"], gate["current"], gate["required"])
        for gate in selected_gates
    )
    family_note = family if family is not None else "all staging/cutover families"
    return f"""# Staging Snapshot Preflight Checklist

Generated: {generated}

Scope: {family_note}

This checklist is operator readiness scaffolding only. It does not approve a
staging snapshot, run a rehearsal, deploy, sync Fly, write live data, inspect
private campaign content, or move any readiness label.

## Source Docs To Recheck
{source_docs}

## No-Live Boundary
- [ ] Flask remains the production authority.
- [ ] No Fly command, deploy, live API write, live SQLite sync, or production volume access is part of this preflight.
- [ ] Snapshot source approval is recorded before any local copy is used.
- [ ] The staging-equivalent source has already been copied into `<repo-root>/.task-temp/<staging-snapshot-id>/input/`.
- [ ] Commands and transcript fields use placeholders for private app identity, private URLs, tokens, and secrets.
- [ ] No local absolute paths, real Fly app names, vault material, or `campaigns/<campaign-slug>/` content will be committed.

## Operator Intake
- [ ] Rehearsal id: `<staging-snapshot-id>`.
- [ ] Operator/thread:
- [ ] Approved source summary:
- [ ] Approval record:
- [ ] Copied SQLite path: `<repo-root>/.task-temp/<staging-snapshot-id>/input/player_wiki.sqlite3`.
- [ ] Copied campaigns dir: `<repo-root>/.task-temp/<staging-snapshot-id>/input/campaigns`.
- [ ] Backup archive path: `<repo-root>/.task-temp/<staging-snapshot-id>/backup/<archive>.zip`.
- [ ] TypeScript branch/commit:
- [ ] Flask authority branch/commit:
- [ ] `.local` roadmap visibility:

## Path Guard Before Mutation
- [ ] Run `check-paths` with the copied SQLite, copied campaigns dir, and intended backup archive.
- [ ] Stop if any resolved path is outside `<repo-root>/.task-temp/<staging-snapshot-id>/`.
- [ ] Stop if a command needs live Fly, production SQLite, production campaign content, an owner checkout, or vault source.

## Gate Checklist
{gate_sections}

## Transcript Decision Stub
- Result: blocked until an approved staging-snapshot rehearsal transcript passes.
- Label before: keep the current label from `cutover-readiness.md`.
- Label after: unchanged by this preflight.
- Follow-up required: run the family-specific rehearsal only after approval and copied-path guard pass.
"""


def staging_snapshot_gate_markdown(family: str, current: str, required: str) -> str:
    tables = "\n".join(f"  - [ ] `{table}`" for table in FAMILY_TABLES[family])
    return f"""### {family}
- Current readiness: {current}
- Required staging-snapshot evidence: {required}
- Tables to include when present:
{tables}
- [ ] Family-specific `guide --family {family}` reviewed.
- [ ] Baseline, mutation, restore, and equivalence artifacts remain under `.task-temp/`.
- [ ] Transcript explicitly says this gate is not complete unless restore equivalence passes."""


def init_rehearsal(
    *,
    rehearsal_id: str,
    family: str,
    root: Path | None = None,
    source_description: str = "",
    source_approval: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    if family not in FAMILY_TABLES:
        raise ValueError(f"Unsupported write family: {family}")
    rehearsal_root = assert_disposable_root(root or repo_root() / ".task-temp" / rehearsal_id)
    paths = [rehearsal_root / name for name in REHEARSAL_DIRS]
    transcript_path = rehearsal_root / "transcript.md"

    if dry_run:
        return {
            "created": False,
            "root": str(rehearsal_root),
            "directories": [str(path) for path in paths],
            "transcript": str(transcript_path),
            "transcript_preview": transcript_template(
                rehearsal_id=rehearsal_id,
                family=family,
                source_description=source_description,
                source_approval=source_approval,
                root=rehearsal_root,
            ),
        }

    if rehearsal_root.exists() and any(rehearsal_root.iterdir()):
        raise ValueError(f"Rehearsal root already exists and is not empty: {rehearsal_root}")
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        transcript_template(
            rehearsal_id=rehearsal_id,
            family=family,
            source_description=source_description,
            source_approval=source_approval,
            root=rehearsal_root,
        ),
        encoding="utf-8",
    )
    return {
        "created": True,
        "root": str(rehearsal_root),
        "directories": [str(path) for path in paths],
        "transcript": str(transcript_path),
    }


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(campaigns_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in iter_files(campaigns_dir):
        entries.append(
            {
                "path": path.relative_to(campaigns_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": hash_file(path),
            }
        )
    return entries


def sqlite_table_counts(db_path: Path, tables: Sequence[str]) -> dict[str, Any]:
    if not db_path.exists():
        return {"missing_database": True, "tables": {}, "missing_tables": list(tables)}
    counts: dict[str, int] = {}
    missing: list[str] = []
    with sqlite3.connect(db_path) as connection:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in tables:
            if table not in existing:
                missing.append(table)
                continue
            row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            counts[table] = int(row[0]) if row else 0
    return {"missing_database": False, "tables": counts, "missing_tables": missing}


def capture_snapshot(
    *,
    root: Path,
    label: str,
    family: str,
    db_path: Path,
    campaigns_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    if family not in FAMILY_TABLES:
        raise ValueError(f"Unsupported write family: {family}")
    if label not in {"pre", "post", "restore"}:
        raise ValueError("Snapshot label must be one of: pre, post, restore")

    paths = validate_rehearsal_paths(
        root=root,
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )
    output_path = Path(paths.root) / label / "manifest.json"
    manifest = {
        "label": label,
        "family": family,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "paths": asdict(paths),
        "files": file_manifest(Path(paths.campaigns_dir)) if paths.campaigns_dir else [],
        "sqlite": sqlite_table_counts(Path(paths.db_path), FAMILY_TABLES[family])
        if paths.db_path
        else {},
    }
    if dry_run:
        return {"would_write": str(output_path), "manifest": manifest}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"wrote": str(output_path), "manifest": manifest}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_manifests(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = {entry["path"]: entry for entry in before.get("files", [])}
    after_files = {entry["path"]: entry for entry in after.get("files", [])}
    all_files = sorted(set(before_files) | set(after_files))
    changed_files = [
        path for path in all_files if before_files.get(path) != after_files.get(path)
    ]

    before_sqlite = before.get("sqlite", {})
    after_sqlite = after.get("sqlite", {})
    sqlite_equal = before_sqlite == after_sqlite
    return {
        "equal": not changed_files and sqlite_equal,
        "changed_files": changed_files,
        "sqlite_equal": sqlite_equal,
        "before_sqlite": before_sqlite,
        "after_sqlite": after_sqlite,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold and verify disposable TypeScript write-family rehearsals."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create rehearsal folders and transcript.")
    init_parser.add_argument("--rehearsal-id", required=True)
    init_parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))
    init_parser.add_argument("--root", type=Path)
    init_parser.add_argument("--source-description", default="")
    init_parser.add_argument("--source-approval", default="")
    init_parser.add_argument("--dry-run", action="store_true")

    check_parser = subparsers.add_parser("check-paths", help="Validate copied-data paths.")
    check_parser.add_argument("--root", required=True, type=Path)
    check_parser.add_argument("--db", type=Path)
    check_parser.add_argument("--campaigns-dir", type=Path)
    check_parser.add_argument("--backup-archive", type=Path)

    snapshot_parser = subparsers.add_parser("snapshot", help="Capture file and SQLite evidence.")
    snapshot_parser.add_argument("--root", required=True, type=Path)
    snapshot_parser.add_argument("--label", required=True, choices=["pre", "post", "restore"])
    snapshot_parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))
    snapshot_parser.add_argument("--db", required=True, type=Path)
    snapshot_parser.add_argument("--campaigns-dir", required=True, type=Path)
    snapshot_parser.add_argument("--dry-run", action="store_true")

    compare_parser = subparsers.add_parser("compare", help="Compare two captured manifests.")
    compare_parser.add_argument("--before", required=True, type=Path)
    compare_parser.add_argument("--after", required=True, type=Path)

    guide_parser = subparsers.add_parser("guide", help="Print a family-specific transcript guide.")
    guide_parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))

    preflight_parser = subparsers.add_parser(
        "staging-snapshot-preflight",
        help="Print a sanitized staging snapshot preflight checklist.",
    )
    preflight_parser.add_argument("--family", choices=sorted(FAMILY_TABLES))

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "init":
            result = init_rehearsal(
                rehearsal_id=args.rehearsal_id,
                family=args.family,
                root=args.root,
                source_description=args.source_description,
                source_approval=args.source_approval,
                dry_run=args.dry_run,
            )
        elif args.command == "check-paths":
            result = asdict(
                validate_rehearsal_paths(
                    root=args.root,
                    db_path=args.db,
                    campaigns_dir=args.campaigns_dir,
                    backup_archive=args.backup_archive,
                )
            )
        elif args.command == "snapshot":
            result = capture_snapshot(
                root=args.root,
                label=args.label,
                family=args.family,
                db_path=args.db,
                campaigns_dir=args.campaigns_dir,
                dry_run=args.dry_run,
            )
        elif args.command == "compare":
            result = compare_manifests(load_manifest(args.before), load_manifest(args.after))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["equal"] else 1
        elif args.command == "guide":
            result = {
                "family": args.family,
                "guide_markdown": family_guide_markdown(args.family),
            }
        elif args.command == "staging-snapshot-preflight":
            print(staging_snapshot_preflight_markdown(family=args.family))
            return 0
        else:
            raise ValueError(f"Unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"staging rehearsal harness refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
