from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import ntpath
import os
import posixpath
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

import yaml

from .migrations import CURRENT_SCHEMA_SQL
from .sqlite_safety import SQLiteSnapshotError, snapshot_sqlite_database


FORMAT_IDENTITY = "campaign-player-wiki-cutover-package"
FORMAT_VERSION = 2
SCHEMA_VERSION = 1
DERIVATION_VERSION = 1
VERIFICATION_LEVEL = "verified_v2"

FAMILY_NAMES = (
    "accounts",
    "characters",
    "systems_sources",
    "systems_content",
    "campaign_pages",
    "session_history",
    "active_runtime",
    "assets",
    "campaign_system_policies",
    "campaign_enabled_sources",
    "campaign_entry_overrides",
)

DISPOSITIONS = (
    "typed_projection",
    "sealed_preservation",
    "verified_source_zero",
    "intentionally_deferred",
    "unsupported_quarantined",
)

EXTERNAL_MACHINE_PATH_SENTINEL = (
    "[cpw-cutover-v2:quarantined-external-machine-path]"
)

_HEX40 = re.compile(r"[0-9a-f]{40}")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_WINDOWS_DRIVE_PATH = re.compile(r"^[a-z]:[\\/]", re.IGNORECASE)
_WINDOWS_DRIVE_PATH_ANYWHERE = re.compile(
    r"(?<![a-z0-9])[a-z]:[\\/]", re.IGNORECASE
)
_WINDOWS_UNC_PATH_ANYWHERE = re.compile(
    r"(?:\\\\(?:[?.][\\/]|[^\\/\s]+[\\/])|(?<![:/])//(?:[?.]/|[^/\s]+/))"
)
_FILE_URI = re.compile(r"^file:", re.IGNORECASE)
_FILE_URI_ANYWHERE = re.compile(r"(?<![a-z0-9+.-])file:", re.IGNORECASE)
_POSIX_HOST_ROOTS = (
    "Applications",
    "Library",
    "System",
    "Users",
    "Volumes",
    "bin",
    "boot",
    "dev",
    "etc",
    "home",
    "lib",
    "lib64",
    "media",
    "mnt",
    "opt",
    "private",
    "proc",
    "root",
    "run",
    "sbin",
    "srv",
    "sys",
    "tmp",
    "usr",
    "var",
)
_POSIX_HOST_PATH = re.compile(
    rf"^/(?:{'|'.join(_POSIX_HOST_ROOTS)})(?:/|$)", re.IGNORECASE
)
_POSIX_HOST_PATH_ANYWHERE = re.compile(
    rf"(?<![a-z0-9:/])/(?:{'|'.join(_POSIX_HOST_ROOTS)})(?:/|$)", re.IGNORECASE
)
_LIVE_URL = re.compile(r"https?://", re.IGNORECASE)
_JSON_COLUMNS = frozenset(
    {
        "aliases_json",
        "audit_metadata_json",
        "body_json",
        "edited_fields_json",
        "metadata_json",
        "original_source_identity_json",
        "raw_link_targets_json",
        "state_json",
        "summary_json",
    }
)
_SECRET_COLUMNS = frozenset({"password_hash", "token_hash"})
_SECRET_KEY_NAMES = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "cookie",
        "password",
        "passwordhash",
        "privatekey",
        "refreshtoken",
        "secret",
        "sessionsecret",
        "tokenhash",
    }
)
_PATH_FIELD_NAMES = frozenset(
    {
        "directory",
        "dir",
        "file",
        "file_path",
        "file_uri",
        "filename",
        "filepath",
        "location",
        "parent",
        "path",
        "paths",
        "provenance",
        "root",
        "source",
        "source_path",
        "uri",
        "uris",
    }
)
_PACKAGE_FILE_BINDING_KEYS = frozenset(
    {"binding", "campaign_slug", "logical_path", "object_path", "sha256"}
)
_BLOB_COLUMNS = {"campaign_session_article_images": frozenset({"data_blob"})}
_OPERATIONAL_TABLES = frozenset(
    {
        "player_wiki_reconciliation_operations",
        "player_wiki_deletion_operations",
        "character_reconciliation_operations",
        "character_deletion_operations",
    }
)
_SECRET_TABLES = frozenset(
    {"invite_tokens", "password_reset_tokens", "sessions", "api_tokens"}
)
_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""

_WINDOWS_BROAD_SIDS = frozenset(
    {"WD", "AU", "BU", "S-1-1-0", "S-1-5-11", "S-1-5-32-545"}
)
_WINDOWS_TRUSTED_CUSTODY_SIDS = frozenset(
    {"OW", "SY", "BA", "S-1-5-18", "S-1-5-32-544"}
)
_WINDOWS_WRITE_RIGHT_TOKENS = frozenset(
    {"FA", "FW", "GA", "GW", "CC", "DC", "SW", "WP", "DT", "SD", "WD", "WO"}
)
_WINDOWS_WRITE_RIGHT_MASK = (
    0x00000002
    | 0x00000004
    | 0x00000010
    | 0x00000040
    | 0x00000100
    | 0x00010000
    | 0x00040000
    | 0x00080000
    | 0x10000000
    | 0x40000000
)

# These are the only historical declaration omissions accepted by v2.  The
# predicates remain frozen and every legacy row is independently evaluated.
_APPROVED_LEGACY_MISSING_CHECKS = {
    "users": frozenset({"status in ('invited','active','disabled')"}),
    "user_preferences": frozenset(
        {
            "frontend_mode in ('flask','gen2')",
            "session_chat_order in ('newest_first','oldest_first')",
        }
    ),
}


class CampaignCutoverExportError(RuntimeError):
    """A fail-closed, operator-safe cutover export refusal."""

    def __init__(self, code: str, message: str):
        if not _SAFE_ID.fullmatch(code.replace("_", "-")):
            raise ValueError("Cutover refusal codes must be stable identifiers.")
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class CampaignRoot:
    campaign_slug: str
    stable_id: str
    path: Path


@dataclass(frozen=True)
class CutoverExportSummary:
    format: str
    format_version: int
    content_root_sha256: str
    manifest_sha256: str
    family_counts: Mapping[str, int]
    table_count: int
    file_count: int
    blob_count: int


@dataclass(frozen=True)
class _TableRule:
    family: str | None
    scope: str
    excluded_columns: frozenset[str] = frozenset()


_TABLE_RULES: dict[str, _TableRule] = {
    "users": _TableRule("accounts", "selected_users", frozenset({"password_hash"})),
    "user_preferences": _TableRule("accounts", "selected_users"),
    "campaign_memberships": _TableRule("accounts", "campaign"),
    "character_assignments": _TableRule("accounts", "campaign"),
    "character_state": _TableRule("characters", "campaign"),
    "systems_libraries": _TableRule("systems_sources", "library"),
    "systems_sources": _TableRule("systems_sources", "library"),
    "systems_import_runs": _TableRule(
        "systems_sources", "library", frozenset({"source_path"})
    ),
    "systems_entries": _TableRule(
        "systems_content", "library", frozenset({"source_path"})
    ),
    "systems_entry_links": _TableRule("systems_content", "library"),
    "systems_shared_entry_edit_events": _TableRule(
        "systems_content",
        "campaign_and_library",
        frozenset({"audit_metadata_json", "original_source_identity_json"}),
    ),
    "campaign_pages": _TableRule("campaign_pages", "campaign"),
    "campaign_page_sync_state": _TableRule("campaign_pages", "campaign"),
    "campaign_visibility_settings": _TableRule("campaign_pages", "campaign"),
    "campaign_sessions": _TableRule("session_history", "campaign"),
    "campaign_session_articles": _TableRule("session_history", "campaign"),
    "campaign_session_messages": _TableRule("session_history", "campaign"),
    "campaign_dm_statblocks": _TableRule("session_history", "campaign"),
    "campaign_dm_condition_definitions": _TableRule("session_history", "campaign"),
    "campaign_session_states": _TableRule("active_runtime", "campaign"),
    "campaign_combat_trackers": _TableRule("active_runtime", "campaign"),
    "campaign_combatants": _TableRule("active_runtime", "campaign"),
    "campaign_combat_conditions": _TableRule("active_runtime", "combatant"),
    "campaign_combatant_resource_counters": _TableRule("active_runtime", "combatant"),
    "campaign_combatant_resource_notes": _TableRule("active_runtime", "combatant"),
    "campaign_session_article_images": _TableRule("assets", "article"),
    "campaign_system_policies": _TableRule("campaign_system_policies", "campaign"),
    "campaign_enabled_sources": _TableRule("campaign_enabled_sources", "campaign"),
    "campaign_entry_overrides": _TableRule("campaign_entry_overrides", "campaign"),
    "schema_migrations": _TableRule(None, "schema_evidence"),
    "auth_audit_log": _TableRule(None, "unsafe_audit"),
    "invite_tokens": _TableRule(None, "secret"),
    "password_reset_tokens": _TableRule(None, "secret"),
    "sessions": _TableRule(None, "secret"),
    "api_tokens": _TableRule(None, "secret"),
    "player_wiki_reconciliation_operations": _TableRule(None, "journal"),
    "player_wiki_deletion_operations": _TableRule(None, "journal"),
    "character_reconciliation_operations": _TableRule(None, "journal"),
    "character_deletion_operations": _TableRule(None, "journal"),
}


# This is a versioned contract, not a runtime reflection shortcut.  The exporter
# refuses a changed table or column set before it reads authorization rows.
_EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "api_tokens": ("id", "user_id", "label", "token_hash", "created_at", "last_used_at", "expires_at", "revoked_at", "created_by_user_id"),
    "auth_audit_log": ("id", "actor_user_id", "target_user_id", "campaign_slug", "character_slug", "event_type", "metadata_json", "created_at"),
    "campaign_combat_conditions": ("id", "combatant_id", "name", "duration_text", "created_at", "created_by_user_id"),
    "campaign_combat_trackers": ("campaign_slug", "round_number", "current_combatant_id", "revision", "updated_at", "updated_by_user_id"),
    "campaign_combatant_resource_counters": ("id", "combatant_id", "resource_key", "label", "current_value", "max_value", "reset_label", "source_label", "created_at", "updated_at", "created_by_user_id", "updated_by_user_id"),
    "campaign_combatant_resource_notes": ("id", "combatant_id", "label", "note", "source_label", "created_at", "created_by_user_id"),
    "campaign_combatants": ("id", "campaign_slug", "combatant_type", "character_slug", "player_detail_visible", "source_kind", "source_ref", "display_name", "turn_value", "initiative_bonus", "dexterity_modifier", "initiative_priority", "current_hp", "max_hp", "temp_hp", "movement_total", "movement_remaining", "has_action", "has_bonus_action", "has_reaction", "revision", "created_at", "updated_at", "created_by_user_id", "updated_by_user_id"),
    "campaign_dm_condition_definitions": ("id", "campaign_slug", "name", "description_markdown", "created_at", "updated_at", "created_by_user_id", "updated_by_user_id"),
    "campaign_dm_statblocks": ("id", "campaign_slug", "title", "body_markdown", "source_filename", "subsection", "armor_class", "max_hp", "speed_text", "movement_total", "initiative_bonus", "created_at", "updated_at", "created_by_user_id", "updated_by_user_id"),
    "campaign_enabled_sources": ("campaign_slug", "library_slug", "source_id", "is_enabled", "default_visibility", "updated_at", "updated_by_user_id"),
    "campaign_entry_overrides": ("campaign_slug", "library_slug", "entry_key", "visibility_override", "is_enabled_override", "updated_at", "updated_by_user_id"),
    "campaign_memberships": ("id", "user_id", "campaign_slug", "role", "status", "created_at", "updated_at"),
    "campaign_page_sync_state": ("campaign_slug", "seeded_at"),
    "campaign_pages": ("campaign_slug", "page_ref", "route_slug", "title", "section", "subsection", "page_type", "display_order", "published", "aliases_json", "summary", "image_path", "image_alt", "image_caption", "reveal_after_session", "source_ref", "metadata_json", "raw_link_targets_json", "searchable_text", "body_markdown", "created_at", "updated_at"),
    "campaign_session_article_images": ("article_id", "filename", "media_type", "alt_text", "caption", "data_blob", "updated_at"),
    "campaign_session_articles": ("id", "campaign_slug", "title", "body_markdown", "source_page_ref", "status", "created_at", "created_by_user_id", "revealed_at", "revealed_by_user_id", "revealed_in_session_id"),
    "campaign_session_messages": ("id", "session_id", "campaign_slug", "message_type", "body_text", "recipient_scope", "recipient_user_id", "author_user_id", "author_display_name", "article_id", "created_at"),
    "campaign_session_states": ("campaign_slug", "revision", "updated_at", "updated_by_user_id"),
    "campaign_sessions": ("id", "campaign_slug", "status", "started_at", "started_by_user_id", "ended_at", "ended_by_user_id"),
    "campaign_system_policies": ("campaign_slug", "library_slug", "status", "allow_dm_shared_core_entry_edits", "proprietary_acknowledged_at", "proprietary_acknowledged_by_user_id", "created_at", "updated_at", "updated_by_user_id"),
    "campaign_visibility_settings": ("campaign_slug", "scope", "visibility", "updated_at", "updated_by_user_id"),
    "character_assignments": ("id", "user_id", "campaign_slug", "character_slug", "assignment_type", "created_at", "updated_at"),
    "character_deletion_operations": ("operation_id", "campaign_slug", "character_slug", "operation_kind", "definition_present", "definition_digest", "definition_size", "definition_tombstone_name", "import_present", "import_digest", "import_size", "import_tombstone_name", "asset_present", "asset_ref", "asset_digest", "asset_size", "asset_tombstone_name", "previous_state_present", "previous_state_revision", "previous_state_digest", "previous_assignment_present", "previous_assignment_digest", "deleted_files", "deleted_state", "deleted_assignment", "deleted_assets", "audit_event_type", "audit_actor_user_id", "audit_target_user_id", "audit_metadata_json", "state", "error_code", "created_at", "updated_at"),
    "character_reconciliation_operations": ("operation_id", "campaign_slug", "character_slug", "operation_kind", "previous_definition_digest", "desired_definition_digest", "previous_import_digest", "desired_import_digest", "previous_state_digest", "desired_state_digest", "previous_state_revision", "desired_state_revision", "desired_definition_yaml", "desired_import_yaml", "previous_asset_ref", "desired_asset_ref", "previous_asset_digest", "desired_asset_digest", "desired_asset_bytes", "state", "error_code", "created_at", "updated_at"),
    "character_state": ("campaign_slug", "character_slug", "revision", "state_json", "updated_at", "updated_by_user_id"),
    "invite_tokens": ("id", "user_id", "token_hash", "expires_at", "used_at", "created_by_user_id", "created_at"),
    "password_reset_tokens": ("id", "user_id", "token_hash", "expires_at", "used_at", "created_by_user_id", "created_at"),
    "player_wiki_deletion_operations": ("operation_id", "campaign_slug", "page_ref", "source_ref", "tombstone_ref", "source_sha256", "source_size", "operation_kind", "audit_event_type", "audit_actor_user_id", "audit_metadata_json", "state", "error_code", "created_at", "updated_at"),
    "player_wiki_reconciliation_operations": ("operation_id", "campaign_slug", "page_ref", "operation_kind", "primary_authority", "desired_primary_ref", "previous_primary_digest", "desired_primary_digest", "previous_markdown_digest", "desired_markdown_digest", "desired_markdown", "audit_event_type", "audit_actor_user_id", "audit_metadata_json", "state", "error_code", "created_at", "updated_at"),
    "schema_migrations": ("version", "name", "checksum", "applied_at"),
    "sessions": ("id", "user_id", "token_hash", "created_at", "last_seen_at", "expires_at", "revoked_at", "user_agent", "ip_address"),
    "systems_entries": ("id", "library_slug", "source_id", "entry_key", "entry_type", "slug", "title", "source_page", "source_path", "search_text", "player_safe_default", "dm_heavy", "metadata_json", "body_json", "rendered_html", "created_at", "updated_at"),
    "systems_entry_links": ("id", "library_slug", "from_entry_key", "to_entry_key", "relation_type"),
    "systems_import_runs": ("id", "library_slug", "source_id", "status", "import_version", "source_path", "summary_json", "started_at", "completed_at", "started_by_user_id"),
    "systems_libraries": ("library_slug", "title", "system_code", "status", "created_at", "updated_at"),
    "systems_shared_entry_edit_events": ("id", "campaign_slug", "library_slug", "source_id", "entry_key", "entry_slug", "original_source_identity_json", "edited_fields_json", "actor_user_id", "audit_event_type", "audit_metadata_json", "created_at"),
    "systems_sources": ("id", "library_slug", "source_id", "title", "license_class", "license_url", "attribution_text", "public_visibility_allowed", "requires_unofficial_notice", "status", "created_at", "updated_at"),
    "user_preferences": ("user_id", "theme_key", "session_chat_order", "frontend_mode", "updated_at"),
    "users": ("id", "email", "display_name", "is_admin", "status", "password_hash", "auth_version", "created_at", "updated_at"),
}


def export_campaign_cutover_package(
    *,
    database_path: Path,
    campaigns_parent: Path,
    campaigns: Sequence[CampaignRoot],
    output_dir: Path,
    source_stable_id: str,
    exporter_commit: str,
    exporter_tree: str,
) -> CutoverExportSummary:
    """Create one deterministic, self-verified cutover package.

    The function deliberately does not create a Flask app or import a store.  It
    snapshots SQLite once and all subsequent SQL is issued against that private
    snapshot.
    """

    database_path = Path(database_path)
    campaigns_parent = Path(campaigns_parent)
    output_dir = Path(output_dir)
    _validate_stable_id(source_stable_id, "source stable ID")
    _validate_git_identity(exporter_commit, "exporter commit")
    _validate_git_identity(exporter_tree, "exporter tree")
    normalized_campaigns = _validate_campaign_roots(campaigns_parent, campaigns)
    _validate_source_and_output_boundaries(
        database_path=database_path,
        campaigns_parent=campaigns_parent,
        campaigns=normalized_campaigns,
        output_dir=output_dir,
    )
    _reject_unapproved_dnd_campaigns(campaigns_parent, normalized_campaigns)

    output_parent = output_dir.parent
    if not output_parent.exists():
        raise CampaignCutoverExportError(
            "output_parent_missing",
            "The cutover package destination parent must already exist.",
        )
    _assert_physical_directory(output_parent, "output parent")
    if output_dir.exists():
        raise CampaignCutoverExportError(
            "output_exists", "The cutover package destination already exists."
        )
    _ensure_capacity(database_path, normalized_campaigns, output_parent)

    pre_database = _database_source_inventory(database_path)
    pre_topology = _campaign_topology_inventory(normalized_campaigns)
    pre_files, file_sources = _campaign_file_inventory(normalized_campaigns)
    public_files = _public_file_inventory(pre_files)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.cutover-stage-", dir=output_parent)
    )
    published = False
    try:
        _make_private(stage)
        sqlite_input = stage / ".sqlite-input"
        sqlite_input.mkdir()
        _make_private(sqlite_input)
        staged_source_database = _copy_sqlite_input_bundle(
            database_path=database_path,
            source_inventory=pre_database,
            destination_dir=sqlite_input,
        )
        snapshot_path = stage / "source" / "database.sqlite3"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        _make_private(snapshot_path.parent)
        try:
            snapshot_evidence = snapshot_sqlite_database(
                source_path=staged_source_database,
                destination_path=snapshot_path,
            )
        except (FileNotFoundError, SQLiteSnapshotError) as exc:
            raise CampaignCutoverExportError(
                "snapshot_refused", "The read-only SQLite snapshot could not be captured safely."
            ) from exc
        _make_private(snapshot_path)
        shutil.rmtree(sqlite_input)

        file_bindings = _copy_content_addressed_files(
            stage=stage,
            inventory=public_files,
            sources=file_sources,
        )
        host_path_bindings = _host_path_file_bindings(
            file_bindings=file_bindings,
            sources=file_sources,
        )
        approved_campaign_root_keys = _approved_campaign_root_keys(
            normalized_campaigns
        )
        projected = _project_snapshot(
            snapshot_path=snapshot_path,
            campaign_slugs={campaign.campaign_slug for campaign in normalized_campaigns},
            file_bindings=file_bindings,
            host_path_bindings=host_path_bindings,
            approved_campaign_root_keys=approved_campaign_root_keys,
        )
        expected_families = {
            name: _loads_strict_json(
                _canonical_json_bytes(projected["families"][name]).decode("utf-8")
            )
            for name in FAMILY_NAMES
        }

        for family_name in FAMILY_NAMES:
            _write_canonical_json(
                stage / "families" / f"{family_name}.json",
                projected["families"][family_name],
            )
        _write_canonical_json(stage / "inventory" / "schema.json", projected["schema"])
        _write_canonical_json(stage / "inventory" / "tables.json", projected["tables"])
        _write_canonical_json(stage / "inventory" / "files.json", public_files)
        _write_canonical_json(stage / "inventory" / "blobs.json", projected["blobs"])
        _write_canonical_json(
            stage / "inventory" / "dispositions.json", projected["dispositions"]
        )

        post_database = _database_source_inventory(database_path)
        post_topology = _campaign_topology_inventory(normalized_campaigns)
        post_files, _ = _campaign_file_inventory(normalized_campaigns)
        if (
            pre_database != post_database
            or pre_topology != post_topology
            or pre_files != post_files
        ):
            raise CampaignCutoverExportError(
                "source_drift", "The source changed while the cutover package was captured."
            )

        family_counts = {
            name: _family_record_count(projected["families"][name]) for name in FAMILY_NAMES
        }
        safe_summary = {
            "blob_count": len(projected["blobs"]),
            "campaign_count": len(normalized_campaigns),
            "disposition_totals": projected["dispositions"]["totals"],
            "family_counts": family_counts,
            "file_count": len(public_files),
            "source_unchanged": True,
            "table_count": len(projected["tables"]),
        }
        _write_canonical_json(stage / "evidence" / "safe-summary.json", safe_summary)

        _enforce_private_package_tree(stage)
        artifacts = _inventory_package_artifacts(stage)
        content_root = _digest_json(artifacts)
        root_descriptors = []
        for campaign in normalized_campaigns:
            records = [
                record for record in public_files if record["campaign_stable_id"] == campaign.stable_id
            ]
            root_descriptors.append(
                {
                    "campaign_slug": campaign.campaign_slug,
                    "campaign_stable_id": campaign.stable_id,
                    "file_count": len(records),
                    "content_sha256": _digest_json(records),
                }
            )
        manifest = {
            "artifacts": artifacts,
            "campaign_stable_ids": {
                campaign.campaign_slug: campaign.stable_id
                for campaign in normalized_campaigns
            },
            "campaigns": root_descriptors,
            "certification": {
                "format_version": FORMAT_VERSION,
                "manifest_hashes_verified": True,
                "verification_level": VERIFICATION_LEVEL,
            },
            "content_root_digest": content_root,
            "derivation_version": DERIVATION_VERSION,
            "disposition_totals": projected["dispositions"]["totals"],
            "exporter": {"commit": exporter_commit, "tree": exporter_tree},
            "families": [
                {
                    "name": name,
                    "path": f"families/{name}.json",
                    "record_count": family_counts[name],
                    "sha256": _artifact_hash(artifacts, f"families/{name}.json"),
                }
                for name in FAMILY_NAMES
            ],
            "format": FORMAT_IDENTITY,
            "format_version": FORMAT_VERSION,
            "schema_digest": _artifact_hash(artifacts, "inventory/schema.json"),
            "schema_version": SCHEMA_VERSION,
            "snapshot": {
                "byte_count": snapshot_evidence.byte_count,
                "path": "source/database.sqlite3",
                "sha256": snapshot_evidence.sha256,
            },
            "source_stable_id": source_stable_id,
        }
        expected_manifest_bytes = _canonical_json_bytes(manifest)
        _write_canonical_json(stage / "manifest.json", manifest)
        manifest_sha = _sha256_file(stage / "manifest.json")[1]
        _self_verify_package(
            stage,
            expected_manifest_bytes=expected_manifest_bytes,
            expected_schema=projected["schema"],
            expected_dispositions=projected["dispositions"],
            expected_families=expected_families,
            campaign_stable_ids={
                campaign.campaign_slug: campaign.stable_id
                for campaign in normalized_campaigns
            },
            campaign_slugs={
                campaign.campaign_slug for campaign in normalized_campaigns
            },
            host_path_bindings=host_path_bindings,
            approved_campaign_root_keys=approved_campaign_root_keys,
        )

        _publish_stage(stage, output_dir)
        published = True
        return CutoverExportSummary(
            format=FORMAT_IDENTITY,
            format_version=FORMAT_VERSION,
            content_root_sha256=content_root,
            manifest_sha256=manifest_sha,
            family_counts=family_counts,
            table_count=len(projected["tables"]),
            file_count=len(public_files),
            blob_count=len(projected["blobs"]),
        )
    except CampaignCutoverExportError:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        raise CampaignCutoverExportError(
            "capture_refused", "The cutover package could not be completed safely."
        ) from exc
    finally:
        if not published and stage.exists():
            _remove_owned_stage(stage, output_parent, output_dir.name)


def assert_final_cutover_eligible(
    *,
    format_identity: str,
    format_version: int,
    verification_level: str,
    manifest_hashes_verified: bool,
) -> None:
    """Refuse legacy/reference packages at the final-certification seam."""

    if (
        format_identity != FORMAT_IDENTITY
        or type(format_version) is not int
        or format_version != FORMAT_VERSION
        or verification_level != VERIFICATION_LEVEL
        or manifest_hashes_verified is not True
    ):
        raise CampaignCutoverExportError(
            "final_certification_ineligible",
            "This package is not eligible for final-cutover certification.",
        )


def _validate_git_identity(value: str, label: str) -> None:
    if _HEX40.fullmatch(value) is None:
        raise CampaignCutoverExportError(
            "invalid_exporter_identity", f"The {label} is not a frozen Git identity."
        )


def _validate_stable_id(value: str, label: str) -> None:
    if _SAFE_ID.fullmatch(value) is None:
        raise CampaignCutoverExportError(
            "invalid_stable_id", f"The {label} is not a portable stable identifier."
        )


def _validate_campaign_roots(
    campaigns_parent: Path, campaigns: Sequence[CampaignRoot]
) -> tuple[CampaignRoot, ...]:
    if not campaigns:
        raise CampaignCutoverExportError(
            "missing_campaigns", "At least one approved campaign root is required."
        )
    seen_slugs: set[str] = set()
    seen_ids: set[str] = set()
    result: list[CampaignRoot] = []
    for campaign in campaigns:
        _validate_stable_id(campaign.campaign_slug, "campaign slug")
        _validate_stable_id(campaign.stable_id, "campaign stable ID")
        if campaign.campaign_slug in seen_slugs or campaign.stable_id in seen_ids:
            raise CampaignCutoverExportError(
                "duplicate_campaign", "Approved campaign identities must be unique."
            )
        seen_slugs.add(campaign.campaign_slug)
        seen_ids.add(campaign.stable_id)
        result.append(
            CampaignRoot(campaign.campaign_slug, campaign.stable_id, Path(campaign.path))
        )
    return tuple(sorted(result, key=lambda item: (item.stable_id, item.campaign_slug)))


def _validate_source_and_output_boundaries(
    *,
    database_path: Path,
    campaigns_parent: Path,
    campaigns: Sequence[CampaignRoot],
    output_dir: Path,
) -> None:
    _assert_regular_single_link(database_path, "database")
    _assert_safe_directory(campaigns_parent, "campaigns parent")
    parent_resolved = campaigns_parent.resolve()
    output_resolved = output_dir.resolve(strict=False)
    database_resolved = database_path.resolve()
    if _paths_overlap(output_resolved, database_resolved):
        raise CampaignCutoverExportError(
            "source_output_overlap", "The source and destination boundaries overlap."
        )
    for campaign in campaigns:
        _assert_safe_directory(campaign.path, "approved campaign root")
        root_resolved = campaign.path.resolve()
        if root_resolved.parent != parent_resolved:
            raise CampaignCutoverExportError(
                "campaign_root_outside_approved_parent",
                "An approved campaign root is outside the campaigns parent.",
            )
        if root_resolved.name != campaign.campaign_slug:
            raise CampaignCutoverExportError(
                "campaign_root_identity_mismatch",
                "An approved campaign root does not match its campaign slug.",
            )
        if _paths_overlap(output_resolved, root_resolved):
            raise CampaignCutoverExportError(
                "source_output_overlap", "The source and destination boundaries overlap."
            )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _reject_unapproved_dnd_campaigns(
    campaigns_parent: Path, campaigns: Sequence[CampaignRoot]
) -> None:
    approved = {campaign.campaign_slug for campaign in campaigns}
    for child in sorted(campaigns_parent.iterdir(), key=lambda path: path.name.casefold()):
        if child.name in approved:
            continue
        try:
            details = child.stat(follow_symlinks=False)
        except OSError as exc:
            raise CampaignCutoverExportError(
                "unsafe_source_topology",
                "An unapproved campaign boundary is unavailable or unsafe.",
            ) from exc
        if child.is_symlink() or _is_reparse(details):
            raise CampaignCutoverExportError(
                "unsafe_source_topology",
                "An unapproved campaign boundary must not be a link or reparse point.",
            )
        if not stat.S_ISDIR(details.st_mode):
            continue
        _reject_broad_write_acl(child)
        config_path = child / "campaign.yaml"
        if not config_path.is_file():
            continue
        _assert_regular_single_link(config_path, "campaign metadata")
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise CampaignCutoverExportError(
                "ambiguous_unapproved_campaign",
                "An unapproved campaign could not be classified safely.",
            ) from exc
        system = str(payload.get("system") or payload.get("system_code") or "").strip().lower()
        if system in {"dnd-5e", "dnd5e", "d&d-5e", "dnd_5e"}:
            raise CampaignCutoverExportError(
                "additional_supported_dnd_campaign",
                "An additional supported DND campaign is outside the approved launch set.",
            )


def _assert_safe_directory(path: Path, label: str) -> None:
    _assert_physical_directory(path, label)
    _reject_broad_write_acl(path)


def _assert_physical_directory(path: Path, label: str) -> None:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise CampaignCutoverExportError(
            "unsafe_source_topology", f"The {label} is unavailable or unsafe."
        ) from exc
    if (
        not stat.S_ISDIR(details.st_mode)
        or path.is_symlink()
        or _is_reparse(details)
    ):
        raise CampaignCutoverExportError(
            "unsafe_source_topology", f"The {label} must be a physical directory."
        )


def _assert_regular_single_link(path: Path, label: str) -> os.stat_result:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise CampaignCutoverExportError(
            "unsafe_source_topology", f"The {label} is unavailable or unsafe."
        ) from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or path.is_symlink()
        or _is_reparse(details)
        or int(details.st_nlink) != 1
    ):
        raise CampaignCutoverExportError(
            "unsafe_source_topology",
            f"The {label} must be a regular, single-link physical file.",
        )
    _reject_broad_write_acl(path)
    return details


def _is_reparse(details: os.stat_result) -> bool:
    return bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)


@lru_cache(maxsize=1)
def _windows_current_user_sid() -> str:
    if os.name != "nt":
        raise OSError("Windows token identity is unavailable")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    advapi32.GetTokenInformation.restype = ctypes.c_int
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = ctypes.c_int
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        required = ctypes.c_ulong()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        if not required.value:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token, 1, buffer, required, ctypes.byref(required)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        sid_pointer = ctypes.c_void_p.from_buffer(buffer).value
        sid_text = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(
            sid_pointer, ctypes.byref(sid_text)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            value = str(sid_text.value or "")
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if re.fullmatch(r"S-1-(?:\d+-)+\d+", value) is None:
            raise OSError("invalid Windows SID")
        return value
    finally:
        kernel32.CloseHandle(token)


def _windows_acl_sddl(path: Path) -> str:
    if os.name != "nt":
        raise OSError("Windows ACL evidence is unavailable")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = ctypes.c_ulong
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    security_descriptor = ctypes.c_void_p()
    status = advapi32.GetNamedSecurityInfoW(
        str(path),
        1,
        0x00000005,
        None,
        None,
        None,
        None,
        ctypes.byref(security_descriptor),
    )
    if status != 0:
        raise OSError(status, "Windows ACL evidence could not be collected")
    try:
        sddl_pointer = ctypes.c_wchar_p()
        length = ctypes.c_ulong()
        if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            security_descriptor,
            1,
            0x00000005,
            ctypes.byref(sddl_pointer),
            ctypes.byref(length),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            sddl = str(sddl_pointer.value or "")
        finally:
            kernel32.LocalFree(ctypes.cast(sddl_pointer, ctypes.c_void_p))
    finally:
        kernel32.LocalFree(security_descriptor)
    if "D:" not in sddl:
        raise OSError("Windows ACL has no DACL")
    return sddl


def _windows_acl_aces(sddl: str) -> list[dict[str, str]]:
    records = []
    dacl = sddl.split("D:", 1)[1]
    for encoded in re.findall(r"\(([^()]*)\)", dacl):
        fields = encoded.split(";")
        if len(fields) != 6:
            raise OSError("unsupported Windows ACE encoding")
        records.append(
            {
                "type": fields[0],
                "flags": fields[1],
                "rights": fields[2],
                "sid": fields[5],
            }
        )
    return records


def _windows_rights_include_write(rights: str) -> bool:
    if rights.lower().startswith("0x"):
        try:
            return bool(int(rights, 16) & _WINDOWS_WRITE_RIGHT_MASK)
        except ValueError as exc:
            raise OSError("invalid Windows rights encoding") from exc
    tokens = {rights[index : index + 2] for index in range(0, len(rights), 2)}
    return bool(tokens & _WINDOWS_WRITE_RIGHT_TOKENS)


def _verify_windows_private_acl(path: Path, user_sid: str) -> None:
    try:
        sddl = _windows_acl_sddl(path)
        dacl_flags = sddl.split("D:", 1)[1].split("(", 1)[0]
        if "P" not in dacl_flags:
            raise OSError("Windows DACL inheritance remains enabled")
        current_allows_full_control = False
        for ace in _windows_acl_aces(sddl):
            if ace["type"] == "D" and _windows_rights_include_write(
                ace["rights"]
            ):
                raise OSError("Windows DACL contains a write-affecting deny ACE")
            if ace["type"] == "A" and _windows_rights_include_write(
                ace["rights"]
            ):
                if ace["sid"] not in {user_sid, *_WINDOWS_TRUSTED_CUSTODY_SIDS}:
                    raise OSError("Windows DACL permits another principal to write")
            if ace["sid"] != user_sid:
                continue
            if ace["type"] == "A" and ace["rights"] in {"FA", "GA"}:
                current_allows_full_control = True
        if not current_allows_full_control:
            raise OSError("Windows DACL lacks full effective user custody")
    except OSError as exc:
        raise CampaignCutoverExportError(
            "private_storage_unavailable",
            "Private capture storage could not be established.",
        ) from exc


def _reject_broad_write_acl(path: Path) -> None:
    details = path.stat(follow_symlinks=False)
    if os.name != "nt":
        if stat.S_IMODE(details.st_mode) & 0o022:
            raise CampaignCutoverExportError(
                "permissive_acl", "A source boundary permits broad write access."
            )
        return
    try:
        sddl = _windows_acl_sddl(path)
    except OSError as exc:
        raise CampaignCutoverExportError(
            "acl_unavailable", "Source ACL evidence could not be collected."
        ) from exc
    for ace in _windows_acl_aces(sddl):
        if (
            ace["type"] == "A"
            and ace["sid"] in _WINDOWS_BROAD_SIDS
            and _windows_rights_include_write(ace["rights"])
        ):
            raise CampaignCutoverExportError(
                "permissive_acl", "A source boundary permits broad write access."
            )


def _make_private(path: Path) -> None:
    try:
        details = os.lstat(path)
        is_directory = stat.S_ISDIR(details.st_mode)
        is_regular = stat.S_ISREG(details.st_mode)
        if (
            not (is_directory or is_regular)
            or stat.S_ISLNK(details.st_mode)
            or _is_reparse(details)
        ):
            raise OSError("unsafe private-storage topology")
        private_mode = 0o700 if is_directory else 0o600
        if os.name == "posix":
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            if is_directory:
                flags |= getattr(os, "O_DIRECTORY", 0)
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if (
                    (int(opened.st_dev), int(opened.st_ino))
                    != (int(details.st_dev), int(details.st_ino))
                    or stat.S_IFMT(opened.st_mode) != stat.S_IFMT(details.st_mode)
                ):
                    raise OSError("private-storage identity changed")
                os.fchmod(descriptor, private_mode)
            finally:
                os.close(descriptor)
            confirmed = os.lstat(path)
            if (
                (int(confirmed.st_dev), int(confirmed.st_ino))
                != (int(details.st_dev), int(details.st_ino))
                or stat.S_IFMT(confirmed.st_mode) != stat.S_IFMT(details.st_mode)
                or stat.S_IMODE(confirmed.st_mode) != private_mode
            ):
                raise OSError("private-storage mode verification failed")
        else:
            os.chmod(path, private_mode)
        if os.name == "nt":
            user_sid = _windows_current_user_sid()
            result = subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"*{user_sid}:(OI)(CI)F" if path.is_dir() else f"*{user_sid}:F",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise OSError("private ACL application failed")
            _verify_windows_private_acl(path, user_sid)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CampaignCutoverExportError(
            "private_storage_unavailable", "Private capture storage could not be established."
        ) from exc


def _package_tree_entries_no_follow(
    root: Path,
) -> Iterable[tuple[Path, os.stat_result]]:
    try:
        root_details = os.lstat(root)
        if (
            not stat.S_ISDIR(root_details.st_mode)
            or stat.S_ISLNK(root_details.st_mode)
            or _is_reparse(root_details)
        ):
            raise OSError("unsafe package root topology")
        yield root, root_details
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                entries = sorted(children, key=lambda item: item.name)
            for entry in entries:
                details = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                if entry.is_symlink() or _is_reparse(details):
                    raise OSError("unsafe package link topology")
                if stat.S_ISDIR(details.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(details.st_mode):
                    if os.name == "posix" and int(details.st_nlink) != 1:
                        raise OSError("unsafe package file topology")
                else:
                    raise OSError("unsafe package entry topology")
                yield path, details
    except OSError as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "The package private-storage topology is invalid.",
        ) from exc


def _enforce_private_package_tree(stage: Path) -> None:
    for path, _ in _package_tree_entries_no_follow(stage):
        _make_private(path)


def _verify_private_package_tree(stage: Path) -> None:
    user_sid = _windows_current_user_sid() if os.name == "nt" else None
    for path, details in _package_tree_entries_no_follow(stage):
        if os.name == "posix":
            expected_mode = 0o700 if stat.S_ISDIR(details.st_mode) else 0o600
            if stat.S_IMODE(details.st_mode) != expected_mode:
                raise CampaignCutoverExportError(
                    "self_verification_failed",
                    "The package private-storage mode is invalid.",
                )
        elif os.name == "nt":
            _verify_windows_private_acl(path, str(user_sid))


def _acl_fingerprint(path: Path) -> str:
    details = path.stat(follow_symlinks=False)
    if os.name != "nt":
        return f"{details.st_uid}:{details.st_gid}:{stat.S_IMODE(details.st_mode):04o}"
    try:
        sddl = _windows_acl_sddl(path)
    except OSError as exc:
        raise CampaignCutoverExportError(
            "acl_unavailable", "Source ACL evidence could not be collected."
        ) from exc
    return hashlib.sha256(sddl.encode("ascii")).hexdigest()


def _source_file_record(path: Path) -> dict[str, Any]:
    details = _assert_regular_single_link(path, "source file")
    byte_count, sha256 = _sha256_file(path)
    confirmed = _assert_regular_single_link(path, "source file")
    identity = (
        int(details.st_dev),
        int(details.st_ino),
        int(details.st_size),
        int(details.st_mtime_ns),
        int(details.st_nlink),
        int(getattr(details, "st_file_attributes", 0)),
    )
    confirmed_identity = (
        int(confirmed.st_dev),
        int(confirmed.st_ino),
        int(confirmed.st_size),
        int(confirmed.st_mtime_ns),
        int(confirmed.st_nlink),
        int(getattr(confirmed, "st_file_attributes", 0)),
    )
    if identity != confirmed_identity or byte_count != details.st_size:
        raise CampaignCutoverExportError(
            "source_drift", "A source file changed during inventory."
        )
    return {
        "byte_count": byte_count,
        "file_identity": hashlib.sha256(repr(identity[:2]).encode("ascii")).hexdigest(),
        "mtime_ns": int(details.st_mtime_ns),
        "sha256": sha256,
        "acl_sha256": _acl_fingerprint(path),
    }


def _database_source_inventory(database_path: Path) -> list[dict[str, Any]]:
    if Path(f"{database_path}-journal").exists():
        raise CampaignCutoverExportError(
            "unsafe_sqlite_journal",
            "An active SQLite rollback journal cannot be captured safely.",
        )
    records = []
    for kind, path in (
        ("database", database_path),
        ("wal", Path(f"{database_path}-wal")),
        ("shm", Path(f"{database_path}-shm")),
    ):
        if not path.exists():
            continue
        record = _source_file_record(path)
        record["kind"] = kind
        records.append(record)
    if not records or records[0]["kind"] != "database":
        raise CampaignCutoverExportError(
            "database_missing", "The SQLite source database is unavailable."
        )
    return records


def _copy_sqlite_input_bundle(
    *,
    database_path: Path,
    source_inventory: Sequence[dict[str, Any]],
    destination_dir: Path,
) -> Path:
    by_kind = {str(item["kind"]): item for item in source_inventory}
    if "journal" in by_kind:
        raise CampaignCutoverExportError(
            "unsafe_sqlite_journal",
            "An active SQLite rollback journal cannot be captured safely.",
        )
    destination = destination_dir / "source.sqlite3"
    main = by_kind["database"]
    _copy_no_follow(database_path, destination, str(main["sha256"]), int(main["byte_count"]))
    _make_private(destination)
    if "wal" in by_kind:
        wal = by_kind["wal"]
        wal_destination = Path(f"{destination}-wal")
        _copy_no_follow(
            Path(f"{database_path}-wal"),
            wal_destination,
            str(wal["sha256"]),
            int(wal["byte_count"]),
        )
        _make_private(wal_destination)
    return destination


def _campaign_file_inventory(
    campaigns: Sequence[CampaignRoot],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], Path]]:
    records: list[dict[str, Any]] = []
    sources: dict[tuple[str, str], Path] = {}
    portable_names: dict[str, str] = {}
    physical_ids: dict[tuple[int, int], str] = {}
    for campaign in campaigns:
        root = campaign.path.resolve()
        for current_root, dir_names, file_names in os.walk(root, followlinks=False):
            current = Path(current_root)
            _assert_safe_directory(current, "campaign directory")
            dir_names.sort(key=lambda value: (unicodedata.normalize("NFC", value).casefold(), value))
            file_names.sort(key=lambda value: (unicodedata.normalize("NFC", value).casefold(), value))
            for directory in dir_names:
                _assert_safe_directory(current / directory, "campaign directory")
            for filename in file_names:
                source = current / filename
                details = _assert_regular_single_link(source, "campaign file")
                resolved = source.resolve()
                if resolved != root and root not in resolved.parents:
                    raise CampaignCutoverExportError(
                        "path_escape", "A campaign file escapes its approved root."
                    )
                relative = PurePosixPath(*source.relative_to(root).parts).as_posix()
                normalized = unicodedata.normalize("NFC", relative)
                disposition, owner, audience = _campaign_file_custody(normalized)
                collision_key = f"{campaign.stable_id}/{normalized}".casefold()
                previous = portable_names.get(collision_key)
                if previous is not None and previous != relative:
                    raise CampaignCutoverExportError(
                        "portable_path_collision",
                        "Campaign files collide under portable path normalization.",
                    )
                portable_names[collision_key] = relative
                physical_key = (int(details.st_dev), int(details.st_ino))
                if physical_key in physical_ids:
                    raise CampaignCutoverExportError(
                        "unsafe_hardlink", "Campaign files share an unsafe physical identity."
                    )
                physical_ids[physical_key] = collision_key
                source_record = _source_file_record(source)
                record = {
                    "campaign_slug": campaign.campaign_slug,
                    "campaign_stable_id": campaign.stable_id,
                    "logical_path": normalized,
                    "byte_count": source_record["byte_count"],
                    "sha256": source_record["sha256"],
                    "object_path": f"source/objects/sha256/{source_record['sha256'][:2]}/{source_record['sha256']}",
                    "owner": owner,
                    "audience": audience,
                    "disposition": disposition,
                    "source_identity_sha256": source_record["file_identity"],
                    "source_mtime_ns": source_record["mtime_ns"],
                    "source_acl_sha256": source_record["acl_sha256"],
                }
                records.append(record)
                sources[(campaign.stable_id, normalized)] = source
    records.sort(key=lambda item: (item["campaign_stable_id"], item["logical_path"].casefold(), item["logical_path"]))
    return records, sources


def _campaign_topology_inventory(
    campaigns: Sequence[CampaignRoot],
) -> list[dict[str, Any]]:
    """Capture directory identity and security metadata without host paths."""

    records: list[dict[str, Any]] = []
    for campaign in campaigns:
        root = campaign.path.resolve()
        for current_root, dir_names, _ in os.walk(root, followlinks=False):
            current = Path(current_root)
            details = current.stat(follow_symlinks=False)
            _assert_safe_directory(current, "campaign directory")
            relative = (
                "."
                if current == root
                else PurePosixPath(*current.relative_to(root).parts).as_posix()
            )
            identity = (
                int(details.st_dev),
                int(details.st_ino),
                int(details.st_mtime_ns),
                stat.S_IMODE(details.st_mode),
                int(getattr(details, "st_file_attributes", 0)),
            )
            records.append(
                {
                    "acl_sha256": _acl_fingerprint(current),
                    "campaign_stable_id": campaign.stable_id,
                    "directory_identity_sha256": hashlib.sha256(
                        repr(identity[:2]).encode("ascii")
                    ).hexdigest(),
                    "logical_path": relative,
                    "mode": identity[3],
                    "mtime_ns": identity[2],
                    "file_attributes": identity[4],
                }
            )
            dir_names.sort(
                key=lambda value: (
                    unicodedata.normalize("NFC", value).casefold(),
                    value,
                )
            )
    records.sort(
        key=lambda item: (
            item["campaign_stable_id"],
            item["logical_path"].casefold(),
            item["logical_path"],
        )
    )
    return records


def _public_file_inventory(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    private_keys = {"source_acl_sha256", "source_identity_sha256", "source_mtime_ns"}
    return [
        {key: value for key, value in record.items() if key not in private_keys}
        for record in records
    ]


def _campaign_file_custody(relative: str) -> tuple[str, str, str]:
    """Classify every safe regular campaign file without shape-based omission."""

    parts = PurePosixPath(relative).parts
    if parts == ("campaign.yaml",):
        return "typed_projection", "campaign", "operator"
    if len(parts) >= 2 and parts[0].casefold() == "content":
        disposition = (
            "typed_projection"
            if relative.casefold().endswith(".md")
            else "sealed_preservation"
        )
        return disposition, "campaign_pages", "player"
    if (
        len(parts) == 3
        and parts[0].casefold() == "characters"
        and parts[2].casefold() in {"definition.yaml", "import.yaml"}
    ):
        return "typed_projection", "characters", "operator"
    first = parts[0].casefold() if parts else ""
    if first in {"characters", "character-imports"}:
        return "sealed_preservation", "characters", "operator"
    if first == "assets":
        return "sealed_preservation", "assets", "player"
    return "sealed_preservation", "campaign_files", "operator"


def _copy_content_addressed_files(
    *,
    stage: Path,
    inventory: Sequence[dict[str, Any]],
    sources: Mapping[tuple[str, str], Path],
) -> list[dict[str, Any]]:
    copied: set[str] = set()
    bindings: list[dict[str, Any]] = []
    for record in inventory:
        digest = str(record["sha256"])
        source = sources[(str(record["campaign_stable_id"]), str(record["logical_path"]))]
        object_path = stage / Path(*PurePosixPath(str(record["object_path"])).parts)
        if digest not in copied:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            _make_private(object_path.parent)
            _copy_no_follow(source, object_path, digest, int(record["byte_count"]))
            _make_private(object_path)
            copied.add(digest)
        bindings.append(
            {
                key: record[key]
                for key in (
                    "audience",
                    "byte_count",
                    "campaign_slug",
                    "campaign_stable_id",
                    "disposition",
                    "logical_path",
                    "object_path",
                    "owner",
                    "sha256",
                )
            }
        )
    return bindings


def _host_path_file_bindings(
    *,
    file_bindings: Sequence[dict[str, Any]],
    sources: Mapping[tuple[str, str], Path],
) -> dict[tuple[str, str], dict[str, str]]:
    """Index exact approved source files without publishing host identities."""

    bindings: dict[tuple[str, str], dict[str, str]] = {}
    for item in file_bindings:
        source = sources[
            (str(item["campaign_stable_id"]), str(item["logical_path"]))
        ]
        key = _canonical_host_path_key(str(source.resolve()), allow_any_posix=True)
        if key is None:
            raise CampaignCutoverExportError(
                "path_binding_refused",
                "An approved campaign file has no safe host-path identity.",
            )
        binding = {
            "binding": "campaign_file",
            "campaign_slug": str(item["campaign_slug"]),
            "logical_path": str(item["logical_path"]),
            "object_path": str(item["object_path"]),
            "sha256": str(item["sha256"]),
        }
        previous = bindings.get(key)
        if previous is not None and previous != binding:
            raise CampaignCutoverExportError(
                "path_binding_ambiguous",
                "Approved campaign files have an ambiguous host-path identity.",
            )
        bindings[key] = binding
    return bindings


def _approved_campaign_root_keys(
    campaigns: Sequence[CampaignRoot],
) -> frozenset[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for campaign in campaigns:
        key = _canonical_host_path_key(str(campaign.path.resolve()), allow_any_posix=True)
        if key is None:
            raise CampaignCutoverExportError(
                "path_binding_refused",
                "An approved campaign root has no safe host-path identity.",
            )
        keys.add(key)
    return frozenset(keys)


def _copy_no_follow(source: Path, destination: Path, expected_sha: str, expected_size: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as source_file, destination.open("xb") as target:
            digest = hashlib.sha256()
            byte_count = 0
            for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                byte_count += len(chunk)
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except OSError as exc:
        raise CampaignCutoverExportError(
            "file_capture_refused", "A campaign file could not be captured safely."
        ) from exc
    if byte_count != expected_size or digest.hexdigest() != expected_sha:
        raise CampaignCutoverExportError(
            "source_drift", "A campaign file changed during capture."
        )


def _ensure_capacity(
    database_path: Path, campaigns: Sequence[CampaignRoot], output_parent: Path
) -> None:
    source_bytes = database_path.stat().st_size
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{database_path}{suffix}")
        if sidecar.is_file():
            source_bytes += sidecar.stat().st_size
    file_bytes = 0
    for campaign in campaigns:
        for root, _, files in os.walk(campaign.path, followlinks=False):
            for filename in files:
                file_bytes += (Path(root) / filename).stat(follow_symlinks=False).st_size
    required = source_bytes * 2 + file_bytes + max(64 * 1024 * 1024, math.ceil((source_bytes + file_bytes) * 0.2))
    if shutil.disk_usage(output_parent).free < required:
        raise CampaignCutoverExportError(
            "insufficient_capacity", "The destination does not have enough free space."
        )


def _project_snapshot(
    *,
    snapshot_path: Path,
    campaign_slugs: set[str],
    file_bindings: Sequence[dict[str, Any]],
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    try:
        with closing(
            sqlite3.connect(f"{snapshot_path.resolve().as_uri()}?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            query_only = connection.execute("PRAGMA query_only").fetchone()
            if query_only is None or int(query_only[0]) != 1:
                raise CampaignCutoverExportError(
                    "query_only_unavailable", "The staged SQLite snapshot is not query-only."
                )
            schema = _inspect_schema(connection)
            dependencies = _collect_scope_dependencies(connection, campaign_slugs)
            return _build_projections(
                connection=connection,
                schema=schema,
                campaign_slugs=campaign_slugs,
                dependencies=dependencies,
                file_bindings=file_bindings,
                host_path_bindings=host_path_bindings,
                approved_campaign_root_keys=approved_campaign_root_keys,
            )
    except CampaignCutoverExportError:
        raise
    except sqlite3.Error as exc:
        raise CampaignCutoverExportError(
            "snapshot_query_refused", "The staged SQLite snapshot could not be queried safely."
        ) from exc


def _inspect_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    objects = []
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type ASC, name ASC
        """
    ).fetchall()
    tables_seen: set[str] = set()
    for row in rows:
        object_type = str(row["type"])
        name = str(row["name"])
        table_name = str(row["tbl_name"])
        if object_type not in {"table", "index"}:
            raise CampaignCutoverExportError(
                "unknown_schema_object", "The SQLite schema contains an unsupported object."
            )
        if table_name not in _EXPECTED_COLUMNS:
            raise CampaignCutoverExportError(
                "unknown_schema_table", "The SQLite schema contains an unknown table."
            )
        if object_type == "table":
            tables_seen.add(name)
        objects.append(
            {
                "name": name,
                "sql": " ".join(str(row["sql"] or "").split()),
                "table": table_name,
                "type": object_type,
            }
        )
    if tables_seen != set(_EXPECTED_COLUMNS):
        raise CampaignCutoverExportError(
            "missing_schema_table", "The SQLite schema is missing a required table."
        )

    tables = []
    for table_name in sorted(_EXPECTED_COLUMNS):
        columns = connection.execute(
            f"PRAGMA table_xinfo({_quote_identifier(table_name)})"
        ).fetchall()
        expected_names = _EXPECTED_COLUMNS[table_name]
        canonical_columns = _canonical_schema_columns(columns, expected_names)
        check_constraints = _validate_schema_contract(
            connection=connection,
            table_name=table_name,
            canonical_columns=canonical_columns,
        )
        primary_key = [
            str(column["name"])
            for column in sorted(canonical_columns, key=lambda item: int(item["pk"]))
            if int(column["pk"]) > 0
        ]
        if not primary_key:
            raise CampaignCutoverExportError(
                "missing_primary_key", "A tracked table has no stable primary key."
            )
        tables.append(
            {
                "columns": [
                    {
                        "name": str(column["name"]),
                        "not_null": bool(column["notnull"]),
                        "primary_key_order": int(column["pk"]),
                        "type": str(column["type"] or "").upper(),
                    }
                    for column in canonical_columns
                ],
                "check_constraints": check_constraints,
                "name": table_name,
                "primary_key": primary_key,
            }
        )
    return {
        "objects": objects,
        "schema_digest_basis": _digest_json({"objects": objects, "tables": tables}),
        "tables": tables,
        "version": SCHEMA_VERSION,
    }


def _canonical_schema_columns(
    columns: Sequence[Mapping[str, Any]], expected_names: Sequence[str]
) -> list[Mapping[str, Any]]:
    names = tuple(str(column["name"]) for column in columns)
    if len(names) != len(set(names)) or set(names) != set(expected_names):
        raise CampaignCutoverExportError(
            "schema_column_mismatch",
            "The SQLite schema has missing, duplicate, or extra columns.",
        )
    columns_by_name = {str(column["name"]): column for column in columns}
    return [columns_by_name[name] for name in expected_names]


def _validate_schema_contract(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    canonical_columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    expected = _expected_schema_contract()[table_name]
    actual = _table_schema_contract(
        connection,
        table_name,
        columns=canonical_columns,
    )
    if actual["columns"] != expected["columns"]:
        raise CampaignCutoverExportError(
            "schema_column_contract_mismatch",
            "The SQLite schema has incompatible column types, nullability, defaults, or keys.",
        )
    actual_constraints = dict(actual["constraints"])
    expected_constraints = dict(expected["constraints"])
    actual_checks = tuple(actual_constraints.pop("checks"))
    expected_checks = tuple(expected_constraints.pop("checks"))
    if actual_constraints != expected_constraints:
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "The SQLite schema has incompatible table constraints.",
        )
    if (
        len(expected_checks) != len(set(expected_checks))
        or len(actual_checks) != len(set(actual_checks))
        or not set(actual_checks).issubset(expected_checks)
    ):
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "The SQLite schema has incompatible CHECK constraints.",
        )

    check_evidence = []
    actual_check_set = set(actual_checks)
    for predicate in expected_checks:
        if predicate in actual_check_set:
            declaration_state = "present"
            validation = "physical_declaration"
        else:
            if predicate not in _APPROVED_LEGACY_MISSING_CHECKS.get(
                table_name, frozenset()
            ):
                raise CampaignCutoverExportError(
                    "schema_constraint_mismatch",
                    "The SQLite schema is missing an unapproved CHECK constraint.",
                )
            _validate_missing_check_predicate(
                connection=connection,
                table_name=table_name,
                predicate=predicate,
            )
            declaration_state = "missing_row_validated"
            validation = "all_rows_satisfy_frozen_predicate"
        check_evidence.append(
            {
                "declaration_state": declaration_state,
                "predicate": predicate,
                "validation": validation,
            }
        )
    return check_evidence


def _validate_missing_check_predicate(
    *, connection: sqlite3.Connection, table_name: str, predicate: str
) -> None:
    expected = _expected_schema_contract().get(table_name)
    if (
        expected is None
        or predicate not in expected["constraints"]["checks"]
        or table_name not in _EXPECTED_COLUMNS
    ):
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "A missing CHECK constraint could not be bound to the frozen schema.",
        )
    table_sql = _quote_identifier(table_name)
    try:
        violating_row = connection.execute(
            f"SELECT 1 FROM {table_sql} "
            f"WHERE ({predicate}) IS NOT NULL AND NOT ({predicate}) LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "A missing CHECK constraint could not be validated safely.",
        ) from exc
    if violating_row is not None:
        raise CampaignCutoverExportError(
            "schema_constraint_row_violation",
            "A row violates a missing frozen CHECK constraint.",
        )


@lru_cache(maxsize=1)
def _expected_schema_contract() -> dict[str, dict[str, Any]]:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(CURRENT_SCHEMA_SQL)
        connection.execute(_SCHEMA_MIGRATIONS_SQL)
        return {
            table_name: _table_schema_contract(connection, table_name)
            for table_name in sorted(_EXPECTED_COLUMNS)
        }


def _table_schema_contract(
    connection: sqlite3.Connection,
    table_name: str,
    *,
    columns: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if columns is None:
        reflected = connection.execute(
            f"PRAGMA table_xinfo({_quote_identifier(table_name)})"
        ).fetchall()
        columns = _canonical_schema_columns(reflected, _EXPECTED_COLUMNS[table_name])
    column_contract = [
        {
            "default": column["dflt_value"],
            "hidden": int(column["hidden"]),
            "name": str(column["name"]),
            "not_null": bool(column["notnull"]),
            "primary_key_order": int(column["pk"]),
            "type": str(column["type"] or "").upper(),
        }
        for column in columns
    ]
    foreign_key_groups: dict[int, list[tuple[Any, ...]]] = {}
    for row in connection.execute(
        f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
    ).fetchall():
        foreign_key_groups.setdefault(int(row["id"]), []).append(
            (
                int(row["seq"]),
                str(row["from"]),
                str(row["to"]),
                str(row["table"]),
                str(row["on_update"]).upper(),
                str(row["on_delete"]).upper(),
                str(row["match"]).upper(),
            )
        )
    foreign_keys = sorted(
        tuple(sorted(group)) for group in foreign_key_groups.values()
    )
    unique_keys = []
    for index in connection.execute(
        f"PRAGMA index_list({_quote_identifier(table_name)})"
    ).fetchall():
        if not bool(index["unique"]):
            continue
        index_columns = tuple(
            (
                str(row["name"]),
                str(row["coll"] or "").upper(),
                bool(row["desc"]),
            )
            for row in connection.execute(
                f"PRAGMA index_xinfo({_quote_identifier(str(index['name']))})"
            ).fetchall()
            if int(row["key"]) == 1
        )
        unique_keys.append((str(index["origin"]), index_columns, bool(index["partial"])))
    schema_row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if schema_row is None:
        raise CampaignCutoverExportError(
            "missing_schema_table", "The SQLite schema is missing a required table."
        )
    table_options = connection.execute(
        f"PRAGMA table_list({_quote_identifier(table_name)})"
    ).fetchone()
    return {
        "columns": column_contract,
        "constraints": {
            "checks": _extract_check_constraints(str(schema_row["sql"] or "")),
            "foreign_keys": foreign_keys,
            "strict": bool(table_options["strict"]) if table_options is not None else False,
            "unique_keys": sorted(unique_keys),
            "without_rowid": bool(table_options["wr"]) if table_options is not None else False,
        },
    }


def _extract_check_constraints(sql: str) -> tuple[str, ...]:
    checks: list[str] = []
    cursor = 0
    folded = sql.casefold()
    while True:
        match = re.search(r"\bcheck\s*\(", folded[cursor:])
        if match is None:
            break
        start = cursor + match.end() - 1
        depth = 0
        quote: str | None = None
        index = start
        while index < len(sql):
            char = sql[index]
            if quote is not None:
                if char == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
            elif char in {"'", '"', "`"}:
                quote = char
            elif char == "[":
                quote = "]"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    normalized = _normalize_sql_fragment(sql[start + 1 : index])
                    if not normalized:
                        raise CampaignCutoverExportError(
                            "schema_constraint_mismatch",
                            "The SQLite schema has an invalid CHECK constraint.",
                        )
                    checks.append(normalized)
                    cursor = index + 1
                    break
            index += 1
        else:
            raise CampaignCutoverExportError(
                "schema_constraint_mismatch",
                "The SQLite schema has an invalid CHECK constraint.",
            )
    normalized_checks = tuple(sorted(checks))
    if len(normalized_checks) != len(set(normalized_checks)):
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "The SQLite schema has ambiguous CHECK constraints.",
        )
    return normalized_checks


def _normalize_sql_fragment(value: str) -> str:
    result: list[str] = []
    whitespace = False
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote is not None:
            result.append(char)
            if char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    result.append(value[index + 1])
                    index += 1
                else:
                    quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            if whitespace and result and result[-1] not in "(,":
                result.append(" ")
            whitespace = False
            quote = char
            result.append(char)
        elif char == "[":
            if whitespace and result and result[-1] not in "(,":
                result.append(" ")
            whitespace = False
            quote = "]"
            result.append(char)
        elif char.isspace():
            whitespace = True
        else:
            if whitespace and result and result[-1] not in "(," and char not in "),":
                result.append(" ")
            whitespace = False
            result.append(char.casefold())
        index += 1
    if quote is not None:
        raise CampaignCutoverExportError(
            "schema_constraint_mismatch",
            "The SQLite schema has an invalid CHECK constraint.",
        )
    return "".join(result).strip()


def _collect_scope_dependencies(
    connection: sqlite3.Connection, campaign_slugs: set[str]
) -> dict[str, set[Any]]:
    users: set[Any] = set()
    libraries: set[Any] = set()
    articles: set[Any] = set()
    combatants: set[Any] = set()
    campaign_parameters = tuple(sorted(campaign_slugs))
    for table in (
        "campaign_system_policies",
        "campaign_enabled_sources",
        "campaign_entry_overrides",
        "systems_shared_entry_edit_events",
    ):
        libraries.update(
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT library_slug FROM {_quote_identifier(table)} "
                f"WHERE campaign_slug IN ({_placeholders(campaign_slugs)})",
                campaign_parameters,
            ).fetchall()
            if row[0] is not None
        )
    articles.update(
        row[0]
        for row in connection.execute(
            f"SELECT id FROM campaign_session_articles "
            f"WHERE campaign_slug IN ({_placeholders(campaign_slugs)})",
            campaign_parameters,
        ).fetchall()
    )
    combatants.update(
        row[0]
        for row in connection.execute(
            f"SELECT id FROM campaign_combatants "
            f"WHERE campaign_slug IN ({_placeholders(campaign_slugs)})",
            campaign_parameters,
        ).fetchall()
    )

    # Account closure is derived from every user FK in every selected projected
    # row, not merely membership and character assignment.  This includes
    # creators, updaters, actors, revealers, recipients, and policy approvers.
    dependencies: dict[str, set[Any]] = {
        "users": users,
        "libraries": libraries,
        "articles": articles,
        "combatants": combatants,
    }
    for table_name in sorted(_EXPECTED_COLUMNS):
        rule = _TABLE_RULES[table_name]
        if rule.family is None or rule.scope == "selected_users":
            continue
        user_columns = [
            column
            for column in _EXPECTED_COLUMNS[table_name]
            if column == "user_id" or column.endswith("_user_id")
        ]
        if not user_columns:
            continue
        selected_sql = ", ".join(
            _quote_identifier(column)
            for column in dict.fromkeys(
                [
                    *user_columns,
                    "campaign_slug" if "campaign_slug" in _EXPECTED_COLUMNS[table_name] else user_columns[0],
                    "library_slug" if "library_slug" in _EXPECTED_COLUMNS[table_name] else user_columns[0],
                    "article_id" if "article_id" in _EXPECTED_COLUMNS[table_name] else user_columns[0],
                    "combatant_id" if "combatant_id" in _EXPECTED_COLUMNS[table_name] else user_columns[0],
                ]
            )
        )
        for row in connection.execute(
            f"SELECT {selected_sql} FROM {_quote_identifier(table_name)}"
        ).fetchall():
            if not _row_matches_non_account_scope(
                rule=rule,
                row=row,
                campaign_slugs=campaign_slugs,
                dependencies=dependencies,
            ):
                continue
            users.update(
                row[column] for column in user_columns if row[column] is not None
            )
    return {"users": users, "libraries": libraries, "articles": articles, "combatants": combatants}


def _row_matches_non_account_scope(
    *,
    rule: _TableRule,
    row: Mapping[str, Any],
    campaign_slugs: set[str],
    dependencies: Mapping[str, set[Any]],
) -> bool:
    if rule.scope == "campaign":
        return row["campaign_slug"] in campaign_slugs
    if rule.scope == "library":
        return row["library_slug"] in dependencies["libraries"]
    if rule.scope == "campaign_and_library":
        return (
            row["campaign_slug"] in campaign_slugs
            and row["library_slug"] in dependencies["libraries"]
        )
    if rule.scope == "article":
        return row["article_id"] in dependencies["articles"]
    if rule.scope == "combatant":
        return row["combatant_id"] in dependencies["combatants"]
    return False


def _build_projections(
    *,
    connection: sqlite3.Connection,
    schema: dict[str, Any],
    campaign_slugs: set[str],
    dependencies: Mapping[str, set[Any]],
    file_bindings: Sequence[dict[str, Any]],
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> dict[str, Any]:
    schema_by_table = {item["name"]: item for item in schema["tables"]}
    families = {
        name: {"family": name, "tables": [], "version": DERIVATION_VERSION}
        for name in FAMILY_NAMES
    }
    families["assets"]["file_bindings"] = list(file_bindings)
    families["assets"]["blob_bindings"] = []
    table_inventory: list[dict[str, Any]] = []
    blob_inventory: list[dict[str, Any]] = []
    blob_disposition_records: list[dict[str, Any]] = []
    row_dispositions: list[dict[str, Any]] = []
    column_dispositions: list[dict[str, Any]] = []
    zero_dispositions: list[dict[str, Any]] = []
    check_constraint_dispositions: list[dict[str, Any]] = []
    field_quarantine_dispositions: list[dict[str, Any]] = []
    migration_ledger: list[dict[str, Any]] = []
    projected_foreign_keys: list[dict[str, Any]] = []

    for table_name in sorted(_EXPECTED_COLUMNS):
        rule = _TABLE_RULES[table_name]
        table_schema = schema_by_table[table_name]
        for check_constraint in table_schema["check_constraints"]:
            check_constraint_dispositions.append(
                {
                    "declaration_state": check_constraint["declaration_state"],
                    "disposition": "typed_projection",
                    "owner": "inventory",
                    "predicate": check_constraint["predicate"],
                    "table": table_name,
                    "validation": check_constraint["validation"],
                }
            )
        columns = list(_EXPECTED_COLUMNS[table_name])
        primary_key = list(table_schema["primary_key"])
        order_sql = ", ".join(_quote_identifier(column) for column in primary_key)
        selected_sql = ", ".join(_quote_identifier(column) for column in columns)
        rows = connection.execute(
            f"SELECT {selected_sql} FROM {_quote_identifier(table_name)} ORDER BY {order_sql}"
        ).fetchall()
        projected_rows: list[dict[str, Any]] = []
        sealed_count = 0
        quarantined_count = 0
        quarantined_field_count = 0
        row_digests: list[dict[str, Any]] = []
        for row in rows:
            locator = {column: _scalar_for_locator(row[column]) for column in primary_key}
            safe_row_evidence: dict[str, Any] = {
                "disposition": None,
                "locator": locator,
            }
            disposition, reason = _row_disposition(
                table_name=table_name,
                rule=rule,
                row=row,
                campaign_slugs=campaign_slugs,
                dependencies=dependencies,
            )
            source_blob_bindings = _row_blob_bindings(
                table_name=table_name,
                columns=columns,
                primary_key=primary_key,
                row=row,
                expose_content_digest=(
                    disposition == "typed_projection" and rule.family == "assets"
                ),
            )
            blob_inventory.extend(source_blob_bindings)
            for binding in source_blob_bindings:
                is_authorized_asset = (
                    disposition == "typed_projection" and rule.family == "assets"
                )
                blob_disposition_records.append(
                    {
                        "column": binding["column"],
                        "disposition": (
                            "typed_projection" if is_authorized_asset else "sealed_preservation"
                        ),
                        "owner": "assets" if is_authorized_asset else None,
                        "primary_key": binding["primary_key"],
                        "table": binding["table"],
                    }
                )
            if disposition == "typed_projection" and rule.family:
                projected_foreign_keys.extend(
                    _row_foreign_key_references(connection, table_name, row)
                )
                projection, bindings, field_quarantines = _project_row(
                    table_name=table_name,
                    family=rule.family,
                    columns=columns,
                    primary_key=primary_key,
                    row=row,
                    excluded_columns=rule.excluded_columns,
                    host_path_bindings=host_path_bindings,
                    approved_campaign_root_keys=approved_campaign_root_keys,
                )
                projected_rows.append(projection)
                safe_row_evidence["projection_sha256"] = _digest_json(projection)
                field_quarantine_dispositions.extend(field_quarantines)
                quarantined_field_count += len(field_quarantines)
                if bindings:
                    families["assets"]["blob_bindings"].extend(bindings)
            elif disposition == "typed_projection" and table_name == "schema_migrations":
                migration_projection = {
                        column: _project_value(
                            column,
                            row[column],
                            host_path_bindings=host_path_bindings,
                            approved_campaign_root_keys=approved_campaign_root_keys,
                        )
                        for column in columns
                    }
                migration_ledger.append(migration_projection)
                safe_row_evidence["projection_sha256"] = _digest_json(
                    migration_projection
                )
            elif disposition == "unsupported_quarantined":
                quarantined_count += 1
            else:
                sealed_count += 1
            safe_row_evidence["disposition"] = disposition
            row_digests.append(safe_row_evidence)
            row_disposition = {
                    "disposition": disposition,
                    "family": rule.family if disposition == "typed_projection" else None,
                    "locator": locator,
                    "reason": reason,
                    "table": table_name,
                }
            if "projection_sha256" in safe_row_evidence:
                row_disposition["projection_sha256"] = safe_row_evidence[
                    "projection_sha256"
                ]
            row_dispositions.append(row_disposition)
        if not rows:
            zero_dispositions.append(
                {
                    "family": rule.family,
                    "reason": "source_table_present_and_empty",
                    "table": table_name,
                }
            )
        if rule.family:
            family_columns = [
                column
                for column in columns
                if column not in rule.excluded_columns
            ]
            families[rule.family]["tables"].append(
                {"columns": family_columns, "rows": projected_rows, "table": table_name}
            )
        for column in columns:
            if column in rule.excluded_columns or column in _SECRET_COLUMNS:
                column_disposition = "sealed_preservation"
                owner = None
            elif rule.scope == "unsafe_audit":
                column_disposition = "unsupported_quarantined"
                owner = None
            elif rule.family:
                column_disposition = "typed_projection"
                owner = rule.family
            elif rule.scope == "schema_evidence":
                column_disposition = "typed_projection"
                owner = "inventory"
            else:
                column_disposition = "sealed_preservation"
                owner = None
            column_dispositions.append(
                {
                    "column": column,
                    "disposition": column_disposition,
                    "owner": owner,
                    "table": table_name,
                }
            )
        table_inventory.append(
            {
                "columns": columns,
                "primary_key": primary_key,
                "projected_row_count": len(projected_rows),
                "quarantined_field_count": quarantined_field_count,
                "quarantined_row_count": quarantined_count,
                "row_count": len(rows),
                "rows_sha256": _digest_json(row_digests),
                "sealed_row_count": sealed_count,
                "table": table_name,
                "verified_source_zero": not rows,
            }
        )

    blob_inventory.sort(key=lambda item: (item["table"], _canonical_json_bytes(item["primary_key"]), item["column"]))
    families["assets"]["blob_bindings"].sort(
        key=lambda item: (item["table"], _canonical_json_bytes(item["primary_key"]), item["column"])
    )
    table_dispositions = []
    for table in table_inventory:
        rule = _TABLE_RULES[table["table"]]
        if table["row_count"] == 0:
            disposition = "verified_source_zero"
            owner = rule.family
        elif rule.scope == "unsafe_audit":
            disposition = "unsupported_quarantined"
            owner = None
        elif rule.family or rule.scope == "schema_evidence":
            disposition = "typed_projection"
            owner = rule.family or "inventory"
        else:
            disposition = "sealed_preservation"
            owner = None
        table_dispositions.append(
            {"disposition": disposition, "owner": owner, "table": table["table"]}
        )
    schema_object_dispositions = [
        {
            "disposition": "typed_projection",
            "name": item["name"],
            "type": item["type"],
        }
        for item in schema["objects"]
    ]
    file_dispositions = [_file_disposition_record(item) for item in file_bindings]
    blob_dispositions = sorted(
        blob_disposition_records,
        key=lambda item: (
            item["table"],
            _canonical_json_bytes(item["primary_key"]),
            item["column"],
        ),
    )
    dispositions = {
        "blobs": blob_dispositions,
        "check_constraints": check_constraint_dispositions,
        "columns": column_dispositions,
        "field_quarantines": field_quarantine_dispositions,
        "files": file_dispositions,
        "rows": row_dispositions,
        "schema_objects": schema_object_dispositions,
        "tables": table_dispositions,
        "version": DERIVATION_VERSION,
        "zero_tables": zero_dispositions,
    }
    disposition_totals = {name: 0 for name in DISPOSITIONS}
    for collection_name in (
        "blobs",
        "check_constraints",
        "columns",
        "field_quarantines",
        "files",
        "rows",
        "schema_objects",
        "tables",
    ):
        for item in dispositions[collection_name]:
            disposition_totals[item["disposition"]] += 1
    dispositions["totals"] = disposition_totals
    schema["migration_ledger"] = migration_ledger
    _verify_projected_foreign_key_closure(
        references=projected_foreign_keys,
        row_dispositions=row_dispositions,
    )
    _verify_closure(
        schema=schema,
        tables=table_inventory,
        files=file_bindings,
        blobs=blob_inventory,
        dispositions=dispositions,
        families=families,
    )
    return {
        "blobs": blob_inventory,
        "dispositions": dispositions,
        "families": families,
        "schema": schema,
        "tables": table_inventory,
    }


def _row_disposition(
    *,
    table_name: str,
    rule: _TableRule,
    row: sqlite3.Row,
    campaign_slugs: set[str],
    dependencies: Mapping[str, set[Any]],
) -> tuple[str, str]:
    if table_name in _OPERATIONAL_TABLES:
        state = str(row["state"] or "").strip().lower()
        if state != "completed":
            raise CampaignCutoverExportError(
                "nonterminal_operational_journal",
                "A nonterminal operational journal requires carry-forward or retirement policy.",
            )
        return "sealed_preservation", "completed_operational_journal"
    if table_name in _SECRET_TABLES:
        return "sealed_preservation", "credential_or_session_custody_only"
    if table_name == "auth_audit_log":
        return "unsupported_quarantined", "audit_shape_not_authorized_for_projection"
    if table_name == "schema_migrations":
        return "typed_projection", "schema_capture_evidence"
    selected = False
    if rule.scope == "campaign":
        selected = row["campaign_slug"] in campaign_slugs
    elif rule.scope == "selected_users":
        key = "id" if table_name == "users" else "user_id"
        selected = row[key] in dependencies["users"]
    elif rule.scope == "library":
        selected = row["library_slug"] in dependencies["libraries"]
    elif rule.scope == "campaign_and_library":
        selected = (
            row["campaign_slug"] in campaign_slugs
            and row["library_slug"] in dependencies["libraries"]
        )
    elif rule.scope == "article":
        selected = row["article_id"] in dependencies["articles"]
    elif rule.scope == "combatant":
        selected = row["combatant_id"] in dependencies["combatants"]
    if selected:
        return "typed_projection", "approved_launch_scope"
    return "sealed_preservation", "outside_approved_launch_scope"


def _project_row(
    *,
    table_name: str,
    family: str,
    columns: Sequence[str],
    primary_key: Sequence[str],
    row: sqlite3.Row,
    excluded_columns: frozenset[str],
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    result: dict[str, Any] = {}
    blob_bindings: list[dict[str, Any]] = []
    field_quarantines: list[dict[str, Any]] = []
    locator = {key: _scalar_for_locator(row[key]) for key in primary_key}
    for column in columns:
        if column in excluded_columns or column in _SECRET_COLUMNS:
            continue
        value = row[column]
        if column in _BLOB_COLUMNS.get(table_name, frozenset()):
            if not isinstance(value, bytes):
                raise CampaignCutoverExportError(
                    "invalid_blob", "A required SQLite BLOB is missing or has an invalid type."
                )
            binding = {
                "byte_count": len(value),
                "column": column,
                "custody": "source/database.sqlite3",
                "primary_key": {
                    key: _scalar_for_locator(row[key]) for key in primary_key
                },
                "sha256": hashlib.sha256(value).hexdigest(),
                "table": table_name,
            }
            blob_bindings.append(binding)
            result[column] = {
                "binding_sha256": _digest_json(binding),
                "byte_count": len(value),
                "sha256": binding["sha256"],
            }
            continue
        if _is_quarantinable_external_machine_path(
            family=family,
            column=column,
            value=value,
            host_path_bindings=host_path_bindings,
            approved_campaign_root_keys=approved_campaign_root_keys,
        ):
            result[column] = EXTERNAL_MACHINE_PATH_SENTINEL
            field_quarantines.append(
                _field_quarantine_record(
                    family=family,
                    table_name=table_name,
                    field=column,
                    locator=locator,
                )
            )
            continue
        if (
            family == "session_history"
            and column == "body_markdown"
            and value == EXTERNAL_MACHINE_PATH_SENTINEL
        ):
            raise CampaignCutoverExportError(
                "reserved_quarantine_sentinel",
                "A source value conflicts with the reserved quarantine sentinel.",
            )
        converted = _project_value(
            column,
            value,
            host_path_bindings=host_path_bindings,
            approved_campaign_root_keys=approved_campaign_root_keys,
        )
        _reject_machine_path_value(converted)
        result[column] = converted
    _reject_secret_keys(result)
    return result, blob_bindings, field_quarantines


def _field_quarantine_record(
    *,
    family: str,
    table_name: str,
    field: str,
    locator: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "custody": "source/database.sqlite3",
        "disposition": "unsupported_quarantined",
        "family": family,
        "field": field,
        "locator": dict(locator),
        "original_value_emitted": False,
        "raw_snapshot_preserved": True,
        "reason": "external_machine_path",
        "table": table_name,
    }


def _row_blob_bindings(
    *,
    table_name: str,
    columns: Sequence[str],
    primary_key: Sequence[str],
    row: sqlite3.Row,
    expose_content_digest: bool,
) -> list[dict[str, Any]]:
    bindings = []
    for column in columns:
        value = row[column]
        if not isinstance(value, bytes):
            continue
        binding = {
                "column": column,
                "custody": "source/database.sqlite3",
                "primary_key": {
                    key: _scalar_for_locator(row[key]) for key in primary_key
                },
                "table": table_name,
            }
        if expose_content_digest:
            binding["byte_count"] = len(value)
            binding["sha256"] = hashlib.sha256(value).hexdigest()
        bindings.append(binding)
    return bindings


def _project_value(
    column: str,
    value: Any,
    *,
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> Any:
    if isinstance(value, bytes):
        raise CampaignCutoverExportError(
            "unbound_blob", "A SQLite BLOB has no declared custody binding."
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise CampaignCutoverExportError(
            "invalid_numeric_value", "A projected numeric value is not finite."
        )
    if column in _JSON_COLUMNS and value is not None:
        if not isinstance(value, str):
            raise CampaignCutoverExportError(
                "invalid_json", "A structured SQLite value is not encoded as JSON text."
            )
        value = _loads_strict_json(value)
    return _rewrite_projected_paths(
        value,
        host_path_bindings=host_path_bindings,
        approved_campaign_root_keys=approved_campaign_root_keys,
        path_context=_is_path_field_name(column),
    )


def _loads_strict_json(value: str) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, child in pairs:
            if key in result:
                raise CampaignCutoverExportError(
                    "duplicate_json_key", "A structured SQLite value has duplicate JSON keys."
                )
            result[key] = child
        return result

    try:
        return json.loads(
            value,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")),
        )
    except CampaignCutoverExportError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "invalid_json", "A structured SQLite value is invalid JSON."
        ) from exc


def _is_path_field_name(value: str) -> bool:
    folded = str(value).strip().casefold().replace("-", "_")
    return (
        folded in _PATH_FIELD_NAMES
        or folded.endswith("_path")
        or folded.endswith("_paths")
        or folded.endswith("_ref")
        or folded.endswith("_uri")
        or folded.endswith("_uris")
    )


def _file_uri_path(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() != "file" or parsed.query or parsed.fragment:
            return None
        authority = unquote(parsed.netloc, errors="strict")
        path = unquote(parsed.path, errors="strict")
    except (UnicodeError, ValueError):
        return None
    if "\x00" in authority or "\x00" in path:
        return None
    if authority and authority.casefold() != "localhost":
        if re.fullmatch(r"[a-z]:", authority, re.IGNORECASE):
            return f"{authority}{path}"
        return f"//{authority}{path}"
    if re.match(r"^/[a-z]:[\\/]", path, re.IGNORECASE):
        return path[1:]
    return path


def _canonical_host_path_key(
    value: str, *, allow_any_posix: bool = False
) -> tuple[str, str] | None:
    raw = str(value)
    text = unicodedata.normalize("NFC", raw)
    if not text or text != raw or text != text.strip() or "\x00" in text:
        return None
    if _FILE_URI.match(text):
        decoded = _file_uri_path(text)
        if decoded is None:
            return None
        text = decoded

    windows = text.replace("/", "\\")
    folded = windows.casefold()
    if folded.startswith(("\\\\?\\", "\\\\.\\")):
        return None
    if _WINDOWS_DRIVE_PATH.match(windows):
        parts = windows[3:].split("\\")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return None
        return ("windows", ntpath.normpath(windows))
    if windows.startswith("\\\\"):
        parts = windows[2:].split("\\")
        if len(parts) < 3 or any(part in {"", ".", ".."} for part in parts):
            return None
        return ("windows", ntpath.normpath(windows))

    if text.startswith("/"):
        parts = text[1:].split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return None
    if text.startswith("/") and (allow_any_posix or _POSIX_HOST_PATH.match(text)):
        return ("posix", posixpath.normpath(text))
    return None


def _whole_posix_path_has_ambiguous_segments(value: str) -> bool:
    text = unicodedata.normalize("NFC", str(value).strip())
    if _FILE_URI.match(text):
        decoded = _file_uri_path(text)
        if decoded is None:
            return False
        text = decoded
    return bool(
        text.startswith("/")
        and (
            any(part in {".", ".."} for part in text.split("/"))
            or (text != "/" and text.endswith("/"))
        )
    )


def _has_unsafe_path_grammar(value: str, *, path_context: bool) -> bool:
    raw = str(value)
    if "\x00" in raw:
        return True
    text = unicodedata.normalize("NFC", raw)
    if text != raw:
        return bool(path_context or "/" in raw or "\\" in raw or _FILE_URI.match(raw))
    if _is_web_reference(text):
        return False
    if path_context and (
        text.endswith(("/", "\\")) or re.search(r"[\\/]{2,}", text)
    ):
        return True
    if re.match(r"^[a-z]:", text, re.IGNORECASE):
        return True
    if text.startswith(("\\\\?\\", "\\\\.\\", "//?/", "//./")):
        return True
    if text.startswith("\\"):
        return True
    if (
        path_context or not any(character.isspace() for character in text)
    ) and any(segment in {".", ".."} for segment in re.split(r"[\\/]", text)):
        return True
    if path_context:
        if text.startswith(("/", "\\")) and not _is_logical_application_reference(
            text
        ):
            return True
        try:
            decoded = unquote(text, errors="strict")
        except (UnicodeError, ValueError):
            return True
        if decoded != text and _has_unsafe_path_grammar(
            decoded, path_context=path_context
        ):
            return True
    return False


def _is_web_reference(value: str) -> bool:
    text = unicodedata.normalize("NFC", str(value).strip())
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    if parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc):
        return True
    if not text.startswith("//") or "\\" in text or not parsed.netloc:
        return False
    hostname = parsed.hostname or ""
    return hostname.casefold() == "localhost" or "." in hostname or ":" in parsed.netloc


def _is_logical_application_reference(value: str) -> bool:
    text = unicodedata.normalize("NFC", str(value).strip())
    return (
        "\\" not in text
        and not _FILE_URI.match(text)
        and any(
            text == prefix or text.startswith(f"{prefix}/")
            for prefix in ("/app", "/campaigns")
        )
    )


def _contains_absolute_host_path(value: str, *, path_context: bool = False) -> bool:
    text = unicodedata.normalize("NFC", str(value).strip())
    if not text:
        return False
    if _is_web_reference(text):
        return False
    if _has_unsafe_path_grammar(value, path_context=path_context):
        return True
    if _whole_posix_path_has_ambiguous_segments(text):
        return True
    if _is_logical_application_reference(text):
        return False
    if _canonical_host_path_key(text, allow_any_posix=path_context) is not None:
        return True
    return bool(
        _WINDOWS_DRIVE_PATH_ANYWHERE.search(text)
        or _WINDOWS_UNC_PATH_ANYWHERE.search(text)
        or _FILE_URI_ANYWHERE.search(text)
        or _POSIX_HOST_PATH_ANYWHERE.search(text)
    )


def _host_path_is_within_approved_root(
    key: tuple[str, str], approved_root_keys: frozenset[tuple[str, str]]
) -> bool:
    kind, normalized = key
    for root_kind, root in approved_root_keys:
        if kind != root_kind:
            continue
        try:
            common = (
                ntpath.commonpath((root, normalized))
                if kind == "windows"
                else posixpath.commonpath((root, normalized))
            )
        except ValueError:
            continue
        if common == root:
            return True
    return False


def _host_path_is_approved_root_sibling(
    key: tuple[str, str], approved_root_keys: frozenset[tuple[str, str]]
) -> bool:
    kind, normalized = key
    for root_kind, root in approved_root_keys:
        if kind != root_kind:
            continue
        parent = ntpath.dirname(root) if kind == "windows" else posixpath.dirname(root)
        try:
            common = (
                ntpath.commonpath((parent, normalized))
                if kind == "windows"
                else posixpath.commonpath((parent, normalized))
            )
        except ValueError:
            continue
        if common == parent and normalized != root:
            return True
    return False


def _is_lexically_valid_windows_drive_leaf(value: str) -> bool:
    if not _WINDOWS_DRIVE_PATH.match(value) or value.endswith(("\\", "/")):
        return False
    parts = re.split(r"[\\/]", value[3:])
    if not parts or any(not part or part in {".", ".."} for part in parts):
        return False
    invalid_characters = frozenset('<>:"|?*')
    reserved_names = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{number}"
        for prefix in ("com", "lpt")
        for number in range(1, 10)
    }
    for part in parts:
        if (
            part.endswith((" ", "."))
            or any(ord(character) < 32 or character in invalid_characters for character in part)
            or part.split(".", 1)[0].casefold() in reserved_names
        ):
            return False
    return True


def _is_quarantinable_external_machine_path(
    *,
    family: str,
    column: str,
    value: Any,
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> bool:
    if (
        family != "session_history"
        or column != "body_markdown"
        or not isinstance(value, str)
    ):
        return False
    normalized = unicodedata.normalize("NFC", value)
    if normalized != normalized.strip() or not _is_lexically_valid_windows_drive_leaf(
        normalized
    ):
        return False
    key = _canonical_host_path_key(normalized)
    return bool(
        key is not None
        and key[0] == "windows"
        and key not in host_path_bindings
        and not _host_path_is_within_approved_root(key, approved_campaign_root_keys)
    )


def _rewrite_projected_paths(
    value: Any,
    *,
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
    path_context: bool = False,
) -> Any:
    if isinstance(value, str):
        if _is_web_reference(value):
            return value
        key = _canonical_host_path_key(value, allow_any_posix=True)
        if key is not None:
            binding = host_path_bindings.get(key)
            if binding is not None:
                return dict(binding)
        if _has_unsafe_path_grammar(value, path_context=path_context):
            raise CampaignCutoverExportError(
                "machine_path_leak",
                "A projected value contains an unsafe machine-path form.",
            )
        if _whole_posix_path_has_ambiguous_segments(value):
            raise CampaignCutoverExportError(
                "machine_path_leak",
                "A projected value contains an unbound machine-specific path.",
            )
        if key is not None:
            if _is_logical_application_reference(value):
                return value
            raise CampaignCutoverExportError(
                "machine_path_leak",
                "A projected value contains an unbound machine-specific path.",
            )
        if _contains_absolute_host_path(value, path_context=path_context):
            raise CampaignCutoverExportError(
                "machine_path_leak",
                "A projected value contains an unbound machine-specific path.",
            )
        return value
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            _reject_machine_path_value(str(key))
            result[key] = _rewrite_projected_paths(
                child,
                host_path_bindings=host_path_bindings,
                approved_campaign_root_keys=approved_campaign_root_keys,
                path_context=_is_path_field_name(str(key)),
            )
        return result
    if isinstance(value, list):
        return [
            _rewrite_projected_paths(
                child,
                host_path_bindings=host_path_bindings,
                approved_campaign_root_keys=approved_campaign_root_keys,
                path_context=path_context,
            )
            for child in value
        ]
    return value


def _reject_machine_path_value(value: Any, *, path_context: bool = False) -> None:
    if isinstance(value, str) and _contains_absolute_host_path(
        value, path_context=path_context
    ):
        raise CampaignCutoverExportError(
            "machine_path_leak", "A projected value contains a machine-specific path."
        )
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_machine_path_value(
                child,
                path_context=_is_path_field_name(str(key)),
            )
    elif isinstance(value, list):
        for child in value:
            _reject_machine_path_value(child, path_context=path_context)


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _normalized_security_key(str(key)) in _SECRET_KEY_NAMES:
                raise CampaignCutoverExportError(
                    "secret_leak", "An authorization family contains a secret-shaped field."
                )
            _reject_secret_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_keys(child)


def _normalized_security_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _scalar_for_locator(value: Any) -> Any:
    if value is None or isinstance(value, (str, int)) or type(value) is bool:
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise CampaignCutoverExportError(
        "invalid_primary_key", "A tracked row has an invalid primary-key value."
    )


def _verify_closure(
    *,
    schema: Mapping[str, Any],
    tables: Sequence[dict[str, Any]],
    files: Sequence[dict[str, Any]],
    blobs: Sequence[dict[str, Any]],
    dispositions: Mapping[str, Any],
    families: Mapping[str, Mapping[str, Any]],
) -> None:
    if len(tables) != len(schema["tables"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Table closure could not be proved."
        )
    if {item["table"] for item in tables} != {item["name"] for item in schema["tables"]}:
        raise CampaignCutoverExportError(
            "closure_failure", "Table closure could not be proved."
        )
    row_total = sum(int(item["row_count"]) for item in tables)
    if row_total != len(dispositions["rows"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Row closure could not be proved."
        )
    column_total = sum(len(item["columns"]) for item in schema["tables"])
    if column_total != len(dispositions["columns"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Column closure could not be proved."
        )
    if len(schema["objects"]) != len(dispositions["schema_objects"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Schema-object closure could not be proved."
        )
    expected_check_dispositions = _check_constraint_dispositions(schema)
    if dispositions["check_constraints"] != expected_check_dispositions:
        raise CampaignCutoverExportError(
            "closure_failure", "CHECK-constraint disposition closure could not be proved."
        )
    if len(tables) != len(dispositions["tables"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Table-disposition closure could not be proved."
        )
    expected_family_tables = {
        family: [
            table_name
            for table_name in sorted(_EXPECTED_COLUMNS)
            if _TABLE_RULES[table_name].family == family
        ]
        for family in FAMILY_NAMES
    }
    if tuple(families) != FAMILY_NAMES:
        raise CampaignCutoverExportError(
            "closure_failure", "Family closure could not be proved."
        )
    projected_total = 0
    family_membership: list[str] = []
    inventory_by_table = {item["table"]: item for item in tables}
    for family_name in FAMILY_NAMES:
        family = families[family_name]
        family_tables = family.get("tables")
        if not isinstance(family_tables, list) or [
            item.get("table") for item in family_tables if isinstance(item, dict)
        ] != expected_family_tables[family_name]:
            raise CampaignCutoverExportError(
                "closure_failure", "Family table closure could not be proved."
            )
        for table in family_tables:
            table_name = table["table"]
            family_membership.append(table_name)
            if table.get("columns") != [
                column
                for column in _EXPECTED_COLUMNS[table_name]
                if column not in _TABLE_RULES[table_name].excluded_columns
            ]:
                raise CampaignCutoverExportError(
                    "closure_failure", "Family column closure could not be proved."
                )
            if len(table.get("rows", [])) != inventory_by_table[table_name][
                "projected_row_count"
            ]:
                raise CampaignCutoverExportError(
                    "closure_failure", "Family row closure could not be proved."
                )
            projected_total += len(table["rows"])
    expected_membership = sorted(
        table_name
        for table_name, rule in _TABLE_RULES.items()
        if rule.family is not None
    )
    if sorted(family_membership) != expected_membership or len(
        family_membership
    ) != len(set(family_membership)):
        raise CampaignCutoverExportError(
            "closure_failure", "Family membership is not bijective."
        )
    projected_row_dispositions = sum(
        item["disposition"] == "typed_projection" and item["family"] is not None
        for item in dispositions["rows"]
    )
    if projected_total != projected_row_dispositions:
        raise CampaignCutoverExportError(
            "closure_failure", "Projected row closure could not be proved."
        )
    if len(files) != len(dispositions["files"]):
        raise CampaignCutoverExportError(
            "closure_failure", "File closure could not be proved."
        )
    if list(dispositions["files"]) != [
        _file_disposition_record(item) for item in files
    ]:
        raise CampaignCutoverExportError(
            "closure_failure", "File-disposition closure could not be proved."
        )
    if len(blobs) != len(dispositions["blobs"]):
        raise CampaignCutoverExportError(
            "closure_failure", "BLOB closure could not be proved."
        )
    quarantined_field_total = sum(
        int(item["quarantined_field_count"]) for item in tables
    )
    if quarantined_field_total != len(dispositions["field_quarantines"]):
        raise CampaignCutoverExportError(
            "closure_failure", "Field-quarantine closure could not be proved."
        )
    expected_zero_tables = [
        {
            "family": _TABLE_RULES[item["table"]].family,
            "reason": "source_table_present_and_empty",
            "table": item["table"],
        }
        for item in tables
        if item["row_count"] == 0
    ]
    if dispositions["zero_tables"] != expected_zero_tables:
        raise CampaignCutoverExportError(
            "closure_failure", "Zero-table evidence could not be rederived."
        )
    _assert_unique_entities(dispositions["rows"], ("table", "locator"), "row")
    _assert_unique_entities(dispositions["columns"], ("table", "column"), "column")
    _assert_unique_entities(dispositions["files"], ("campaign_stable_id", "logical_path"), "file")
    _assert_unique_entities(dispositions["blobs"], ("table", "primary_key", "column"), "BLOB")
    _assert_unique_entities(
        dispositions["field_quarantines"],
        ("table", "locator", "field"),
        "field quarantine",
    )
    _assert_unique_entities(
        dispositions["check_constraints"],
        ("table", "predicate"),
        "CHECK constraint",
    )


def _row_foreign_key_references(
    connection: sqlite3.Connection, table_name: str, row: Mapping[str, Any]
) -> list[dict[str, Any]]:
    groups: dict[int, list[Mapping[str, Any]]] = {}
    for foreign_key in connection.execute(
        f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
    ).fetchall():
        groups.setdefault(int(foreign_key["id"]), []).append(foreign_key)
    references = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: int(item["seq"]))
        values = [row[str(item["from"])] for item in ordered]
        if all(value is None for value in values):
            continue
        if any(value is None for value in values):
            raise CampaignCutoverExportError(
                "dependency_closure_failure",
                "A projected foreign-key reference is incomplete.",
            )
        references.append(
            {
                "locator": {
                    str(item["to"]): _scalar_for_locator(value)
                    for item, value in zip(ordered, values, strict=True)
                },
                "table": str(ordered[0]["table"]),
            }
        )
    return references


def _verify_projected_foreign_key_closure(
    *,
    references: Sequence[Mapping[str, Any]],
    row_dispositions: Sequence[Mapping[str, Any]],
) -> None:
    typed_rows = {
        _canonical_json_bytes([item["table"], item["locator"]])
        for item in row_dispositions
        if item["disposition"] == "typed_projection"
    }
    for reference in references:
        identity = _canonical_json_bytes([reference["table"], reference["locator"]])
        if identity not in typed_rows:
            raise CampaignCutoverExportError(
                "dependency_closure_failure",
                "A projected reference has no selected dependency.",
            )


def _check_constraint_dispositions(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for table in schema["tables"]:
        table_name = table["name"]
        for check_constraint in table["check_constraints"]:
            records.append(
                {
                    "declaration_state": check_constraint["declaration_state"],
                    "disposition": "typed_projection",
                    "owner": "inventory",
                    "predicate": check_constraint["predicate"],
                    "table": table_name,
                    "validation": check_constraint["validation"],
                }
            )
    return records


def _file_disposition_record(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "audience": item["audience"],
        "byte_count": item["byte_count"],
        "campaign_stable_id": item["campaign_stable_id"],
        "disposition": item["disposition"],
        "logical_path": item["logical_path"],
        "object_path": item["object_path"],
        "owner": item["owner"],
        "sha256": item["sha256"],
    }


def _assert_unique_entities(
    items: Sequence[Mapping[str, Any]], keys: Sequence[str], label: str
) -> None:
    identities = [
        _canonical_json_bytes([item[key] for key in keys]) for item in items
    ]
    if len(identities) != len(set(identities)):
        raise CampaignCutoverExportError(
            "closure_duplicate", f"{label} closure contains duplicate membership."
        )


def _family_record_count(family: Mapping[str, Any]) -> int:
    count = sum(len(table["rows"]) for table in family["tables"])
    count += len(family.get("file_bindings", []))
    count += len(family.get("blob_bindings", []))
    return count


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "noncanonical_value", "A package value cannot be encoded canonically."
        ) from exc


def _write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _make_private(path.parent)
    try:
        with path.open("xb") as output:
            output.write(_canonical_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        _make_private(path)
    except FileExistsError as exc:
        raise CampaignCutoverExportError(
            "stage_collision", "A staged package artifact already exists."
        ) from exc


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                byte_count += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise CampaignCutoverExportError(
            "file_hash_refused", "A file could not be hashed safely."
        ) from exc
    return byte_count, digest.hexdigest()


def _inventory_package_artifacts(stage: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(
        (candidate for candidate in stage.rglob("*") if candidate.is_file()),
        key=lambda item: PurePosixPath(*item.relative_to(stage).parts).as_posix(),
    ):
        relative = PurePosixPath(*path.relative_to(stage).parts).as_posix()
        if relative == "manifest.json":
            continue
        byte_count, sha256 = _sha256_file(path)
        artifacts.append({"byte_count": byte_count, "path": relative, "sha256": sha256})
    return artifacts


def _artifact_hash(artifacts: Sequence[Mapping[str, Any]], path: str) -> str:
    matches = [str(item["sha256"]) for item in artifacts if item["path"] == path]
    if len(matches) != 1:
        raise CampaignCutoverExportError(
            "artifact_missing", "A required package artifact is missing or duplicated."
        )
    return matches[0]


def _verify_projected_file_bindings(
    value: Any,
    *,
    file_bindings: set[tuple[str, str, str, str]],
) -> None:
    if isinstance(value, dict):
        if value.get("binding") == "campaign_file":
            if (
                set(value) != _PACKAGE_FILE_BINDING_KEYS
                or not all(isinstance(item, str) and item for item in value.values())
                or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                or (
                    value["campaign_slug"],
                    value["logical_path"],
                    value["object_path"],
                    value["sha256"],
                )
                not in file_bindings
            ):
                raise ValueError("projected file binding")
            return
        for child in value.values():
            _verify_projected_file_bindings(child, file_bindings=file_bindings)
    elif isinstance(value, list):
        for child in value:
            _verify_projected_file_bindings(child, file_bindings=file_bindings)


def _verify_field_quarantines_from_snapshot(
    *,
    snapshot_path: Path,
    schema: Mapping[str, Any],
    campaign_slugs: set[str],
    session_family: Mapping[str, Any],
    dispositions: Mapping[str, Any],
    tables_inventory: Sequence[Mapping[str, Any]],
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> None:
    try:
        schema_by_table = {item["name"]: item for item in schema["tables"]}
        family_tables = {
            item["table"]: item for item in session_family["tables"]
        }
        if len(family_tables) != len(session_family["tables"]):
            raise ValueError("duplicate family table")
        derived: list[dict[str, Any]] = []
        with closing(
            sqlite3.connect(f"{snapshot_path.resolve().as_uri()}?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            for table_name in sorted(_EXPECTED_COLUMNS):
                rule = _TABLE_RULES[table_name]
                if (
                    rule.family != "session_history"
                    or "body_markdown" not in _EXPECTED_COLUMNS[table_name]
                ):
                    continue
                primary_key = list(schema_by_table[table_name]["primary_key"])
                selected_columns = [*primary_key, "body_markdown"]
                order_sql = ", ".join(
                    _quote_identifier(column) for column in primary_key
                )
                rows = connection.execute(
                    f"SELECT {', '.join(_quote_identifier(column) for column in selected_columns)} "
                    f"FROM {_quote_identifier(table_name)} "
                    f"WHERE campaign_slug IN ({_placeholders(campaign_slugs)}) "
                    f"ORDER BY {order_sql}",
                    tuple(sorted(campaign_slugs)),
                ).fetchall()
                projected_table = family_tables[table_name]
                projected_rows = projected_table["rows"]
                for row in rows:
                    value = row["body_markdown"]
                    if not _is_quarantinable_external_machine_path(
                        family="session_history",
                        column="body_markdown",
                        value=value,
                        host_path_bindings=host_path_bindings,
                        approved_campaign_root_keys=approved_campaign_root_keys,
                    ):
                        continue
                    locator = {
                        column: _scalar_for_locator(row[column])
                        for column in primary_key
                    }
                    matches = [
                        candidate
                        for candidate in projected_rows
                        if all(candidate.get(key) == child for key, child in locator.items())
                    ]
                    if (
                        len(matches) != 1
                        or matches[0].get("body_markdown")
                        != EXTERNAL_MACHINE_PATH_SENTINEL
                    ):
                        raise ValueError("sentinel binding")
                    derived.append(
                        _field_quarantine_record(
                            family="session_history",
                            table_name=table_name,
                            field="body_markdown",
                            locator=locator,
                        )
                    )
        if dispositions["field_quarantines"] != derived:
            raise ValueError("field quarantine disposition")
        table_field_counts = {
            table_name: sum(
                1 for item in derived if item["table"] == table_name
            )
            for table_name in _EXPECTED_COLUMNS
        }
        if any(
            type(item.get("quarantined_field_count")) is not int
            or item["quarantined_field_count"] != table_field_counts[item["table"]]
            for item in tables_inventory
        ):
            raise ValueError("table field quarantine count")
        published_sentinels = sum(
            1
            for table in session_family["tables"]
            for row in table["rows"]
            if row.get("body_markdown") == EXTERNAL_MACHINE_PATH_SENTINEL
        )
        if published_sentinels != len(derived):
            raise ValueError("field quarantine count")
    except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "The package field-quarantine registry is invalid.",
        ) from exc


def _verify_manifest_relations(
    manifest: Any,
    *,
    actual_artifacts: Sequence[Mapping[str, Any]],
    trusted_campaign_stable_ids: Mapping[str, str],
) -> None:
    try:
        artifacts = manifest["artifacts"]
        if not isinstance(artifacts, list):
            raise TypeError("artifacts")
        artifact_paths = []
        for item in artifacts:
            if not isinstance(item, dict) or not _is_safe_relative_package_path(
                item.get("path")
            ):
                raise TypeError("artifact path")
            artifact_paths.append(item["path"])
        if len(set(artifact_paths)) != len(artifact_paths):
            raise ValueError("duplicate artifact path")
        actual_artifact_paths = [item["path"] for item in actual_artifacts]
        if set(artifact_paths) != set(actual_artifact_paths):
            raise ValueError("artifact path registry")

        campaign_stable_ids = manifest["campaign_stable_ids"]
        if (
            not isinstance(campaign_stable_ids, dict)
            or not campaign_stable_ids
            or campaign_stable_ids != dict(trusted_campaign_stable_ids)
            or any(
                not isinstance(slug, str)
                or not _SAFE_ID.fullmatch(slug)
                or not isinstance(stable_id, str)
                or not _SAFE_ID.fullmatch(stable_id)
                for slug, stable_id in campaign_stable_ids.items()
            )
            or len(set(campaign_stable_ids.values())) != len(campaign_stable_ids)
        ):
            raise ValueError("campaign stable ID mapping")

        campaigns = manifest["campaigns"]
        if not isinstance(campaigns, list) or not campaigns:
            raise TypeError("campaigns")
        campaign_slugs = []
        campaign_ids = []
        descriptor_mapping: dict[str, str] = {}
        for item in campaigns:
            if not isinstance(item, dict):
                raise TypeError("campaign descriptor")
            slug = item.get("campaign_slug")
            stable_id = item.get("campaign_stable_id")
            if (
                not isinstance(slug, str)
                or not _SAFE_ID.fullmatch(slug)
                or not isinstance(stable_id, str)
                or not _SAFE_ID.fullmatch(stable_id)
            ):
                raise TypeError("campaign identity")
            campaign_slugs.append(slug)
            campaign_ids.append(stable_id)
            descriptor_mapping[slug] = stable_id
        if (
            len(set(campaign_slugs)) != len(campaigns)
            or len(set(campaign_ids)) != len(campaigns)
            or descriptor_mapping != campaign_stable_ids
        ):
            raise ValueError("campaign descriptor mapping")
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "The package manifest relational registry is invalid.",
        ) from exc


def _self_verify_package(
    stage: Path,
    *,
    expected_manifest_bytes: bytes,
    expected_schema: Mapping[str, Any],
    expected_dispositions: Mapping[str, Any],
    expected_families: Mapping[str, Any],
    campaign_stable_ids: Mapping[str, str],
    campaign_slugs: set[str],
    host_path_bindings: Mapping[tuple[str, str], Mapping[str, str]],
    approved_campaign_root_keys: frozenset[tuple[str, str]],
) -> None:
    _verify_private_package_tree(stage)
    manifest_path = stage / "manifest.json"
    try:
        raw_manifest = manifest_path.read_bytes()
        manifest = _loads_strict_json(raw_manifest.decode("utf-8"))
        expected_manifest = _loads_strict_json(expected_manifest_bytes.decode("utf-8"))
    except (CampaignCutoverExportError, OSError, UnicodeError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package manifest could not be reinspected."
        ) from exc
    actual_artifacts = _inventory_package_artifacts(stage)
    _verify_manifest_relations(
        manifest,
        actual_artifacts=actual_artifacts,
        trusted_campaign_stable_ids=campaign_stable_ids,
    )
    if (
        raw_manifest != _canonical_json_bytes(manifest)
        or raw_manifest != expected_manifest_bytes
        or manifest != expected_manifest
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "The package manifest does not match its canonical invocation identity.",
        )
    required_manifest_keys = {
        "artifacts",
        "campaign_stable_ids",
        "campaigns",
        "certification",
        "content_root_digest",
        "derivation_version",
        "disposition_totals",
        "exporter",
        "families",
        "format",
        "format_version",
        "schema_digest",
        "schema_version",
        "snapshot",
        "source_stable_id",
    }
    if not isinstance(manifest, dict) or set(manifest) != required_manifest_keys:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package manifest has an invalid property set."
        )
    certification = manifest.get("certification")
    if certification != {
        "format_version": FORMAT_VERSION,
        "manifest_hashes_verified": True,
        "verification_level": VERIFICATION_LEVEL,
    } or type(certification.get("format_version")) is not int:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package certification identity is invalid."
        )
    if (
        manifest.get("format") != FORMAT_IDENTITY
        or type(manifest.get("format_version")) is not int
        or manifest.get("format_version") != FORMAT_VERSION
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != SCHEMA_VERSION
        or type(manifest.get("derivation_version")) is not int
        or manifest.get("derivation_version") != DERIVATION_VERSION
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package version identity is invalid."
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package artifact inventory is invalid."
        )
    if artifacts != actual_artifacts:
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "Package topology and bytes do not match the artifact registry.",
        )
    if len({item.get("path") for item in artifacts if isinstance(item, dict)}) != len(
        artifacts
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "Package artifact paths are not unique."
        )
    json_payloads: dict[str, Any] = {}
    for artifact in actual_artifacts:
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"byte_count", "path", "sha256"}
            or type(artifact.get("byte_count")) is not int
            or artifact["byte_count"] < 0
            or not isinstance(artifact.get("path"), str)
            or not isinstance(artifact.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
        ):
            raise CampaignCutoverExportError(
                "self_verification_failed", "A package artifact record is invalid."
            )
        relative = artifact["path"]
        path = _safe_artifact_path(stage, relative)
        byte_count, sha256 = _sha256_file(path)
        if byte_count != artifact["byte_count"] or sha256 != artifact["sha256"]:
            raise CampaignCutoverExportError(
                "self_verification_failed", "A package artifact failed hash verification."
            )
        if path.suffix == ".json":
            try:
                raw = path.read_bytes()
                payload = _loads_strict_json(raw.decode("utf-8"))
            except (CampaignCutoverExportError, OSError, UnicodeError) as exc:
                raise CampaignCutoverExportError(
                    "self_verification_failed", "A package JSON artifact is unreadable."
                ) from exc
            if raw != _canonical_json_bytes(payload):
                raise CampaignCutoverExportError(
                    "self_verification_failed", "A package JSON artifact is not canonical."
                )
            json_payloads[relative] = payload
    try:
        for payload in json_payloads.values():
            _reject_machine_path_value(payload)
    except CampaignCutoverExportError as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed",
            "A package JSON artifact contains an unsafe host identity.",
        ) from exc
    if _digest_json(actual_artifacts) != manifest["content_root_digest"]:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package content root is invalid."
        )

    expected_family_registry = []
    family_counts: dict[str, int] = {}
    try:
        for name in FAMILY_NAMES:
            relative = f"families/{name}.json"
            family = json_payloads[relative]
            family_keys = {"family", "tables", "version"}
            if name == "assets":
                family_keys |= {"blob_bindings", "file_bindings"}
            if (
                not isinstance(family, dict)
                or set(family) != family_keys
                or family.get("family") != name
                or type(family.get("version")) is not int
                or family.get("version") != DERIVATION_VERSION
                or not isinstance(family.get("tables"), list)
                or (name == "assets" and not isinstance(family.get("blob_bindings"), list))
                or (name == "assets" and not isinstance(family.get("file_bindings"), list))
                or family != expected_families.get(name)
            ):
                raise KeyError(name)
            record_count = _family_record_count(family)
            family_counts[name] = record_count
            expected_family_registry.append(
                {
                    "name": name,
                    "path": relative,
                    "record_count": record_count,
                    "sha256": _artifact_hash(actual_artifacts, relative),
                }
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package family registry is invalid."
        ) from exc
    if manifest.get("families") != expected_family_registry or any(
        type(item.get("record_count")) is not int
        for item in manifest.get("families", [])
        if isinstance(item, dict)
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package family registry is invalid."
        )

    if manifest.get("schema_digest") != _artifact_hash(
        actual_artifacts, "inventory/schema.json"
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package schema digest is invalid."
        )
    schema = json_payloads.get("inventory/schema.json")
    if schema != expected_schema:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package schema evidence is invalid."
        )
    snapshot = manifest.get("snapshot")
    snapshot_artifact = next(
        (
            artifact
            for artifact in actual_artifacts
            if artifact["path"] == "source/database.sqlite3"
        ),
        None,
    )
    if (
        snapshot_artifact is None
        or not isinstance(snapshot, dict)
        or set(snapshot) != {"byte_count", "path", "sha256"}
        or snapshot.get("path") != "source/database.sqlite3"
        or type(snapshot.get("byte_count")) is not int
        or snapshot.get("byte_count") != snapshot_artifact["byte_count"]
        or snapshot.get("sha256") != snapshot_artifact["sha256"]
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package snapshot identity is invalid."
        )

    dispositions = json_payloads.get("inventory/dispositions.json")
    disposition_keys = {
        "blobs",
        "check_constraints",
        "columns",
        "field_quarantines",
        "files",
        "rows",
        "schema_objects",
        "tables",
        "totals",
        "version",
        "zero_tables",
    }
    recomputed_totals = {name: 0 for name in DISPOSITIONS}
    try:
        if (
            not isinstance(dispositions, dict)
            or set(dispositions) != disposition_keys
            or type(dispositions.get("version")) is not int
            or dispositions.get("version") != DERIVATION_VERSION
        ):
            raise KeyError("dispositions")
        for collection_name in (
            "blobs",
            "check_constraints",
            "columns",
            "field_quarantines",
            "files",
            "rows",
            "schema_objects",
            "tables",
        ):
            collection = dispositions[collection_name]
            if not isinstance(collection, list):
                raise TypeError(collection_name)
            for item in collection:
                if not isinstance(item, dict) or item.get("disposition") not in DISPOSITIONS:
                    raise TypeError(collection_name)
                recomputed_totals[item["disposition"]] += 1
        if dispositions != expected_dispositions:
            raise TypeError("expected dispositions")
        if dispositions["check_constraints"] != _check_constraint_dispositions(schema):
            raise TypeError("CHECK constraints")
        check_identities = [
            _canonical_json_bytes([item["table"], item["predicate"]])
            for item in dispositions["check_constraints"]
        ]
        if len(check_identities) != len(set(check_identities)):
            raise TypeError("duplicate CHECK constraints")
        stored_totals = dispositions["totals"]
        if (
            not isinstance(stored_totals, dict)
            or set(stored_totals) != set(DISPOSITIONS)
            or any(type(value) is not int or value < 0 for value in stored_totals.values())
            or stored_totals != recomputed_totals
        ):
            raise TypeError("totals")
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package disposition registry is invalid."
        ) from exc
    manifest_totals = manifest.get("disposition_totals")
    if (
        not isinstance(manifest_totals, dict)
        or set(manifest_totals) != set(DISPOSITIONS)
        or any(type(value) is not int or value < 0 for value in manifest_totals.values())
        or manifest_totals != recomputed_totals
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The manifest disposition totals are invalid."
        )

    files = json_payloads.get("inventory/files.json")
    tables = json_payloads.get("inventory/tables.json")
    blobs = json_payloads.get("inventory/blobs.json")
    trusted_campaign_ids = dict(campaign_stable_ids)
    if (
        not isinstance(files, list)
        or not isinstance(tables, list)
        or not isinstance(blobs, list)
        or manifest.get("campaign_stable_ids") != trusted_campaign_ids
        or not trusted_campaign_ids
        or any(
            not isinstance(slug, str) or not isinstance(stable_id, str)
            for slug, stable_id in trusted_campaign_ids.items()
        )
        or len(set(trusted_campaign_ids.values())) != len(trusted_campaign_ids)
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package campaign identity registry is invalid."
        )
    file_keys = {
        "audience",
        "byte_count",
        "campaign_slug",
        "campaign_stable_id",
        "disposition",
        "logical_path",
        "object_path",
        "owner",
        "sha256",
    }
    artifact_by_path = {item["path"]: item for item in actual_artifacts}
    expected_object_paths: set[str] = set()
    try:
        for item in files:
            if (
                set(item) != file_keys
                or item["campaign_slug"] not in trusted_campaign_ids
                or item["campaign_stable_id"]
                != trusted_campaign_ids[item["campaign_slug"]]
                or item["disposition"]
                not in {"typed_projection", "sealed_preservation"}
                or not isinstance(item["owner"], str)
                or not item["owner"]
                or item["audience"] not in {"operator", "player"}
                or type(item["byte_count"]) is not int
                or item["byte_count"] < 0
                or not isinstance(item["logical_path"], str)
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            ):
                raise TypeError("file")
            if (
                not _is_safe_relative_package_path(item["logical_path"])
            ):
                raise ValueError("logical path")
            expected_object = (
                f"source/objects/sha256/{item['sha256'][:2]}/{item['sha256']}"
            )
            artifact = artifact_by_path.get(expected_object)
            if (
                item["object_path"] != expected_object
                or artifact is None
                or artifact["byte_count"] != item["byte_count"]
                or artifact["sha256"] != item["sha256"]
            ):
                raise ValueError("object binding")
            expected_object_paths.add(expected_object)
        actual_object_paths = {
            item["path"]
            for item in actual_artifacts
            if item["path"].startswith("source/objects/")
        }
        assets_family = json_payloads["families/assets.json"]
        if (
            actual_object_paths != expected_object_paths
            or assets_family["file_bindings"] != files
            or dispositions["files"]
            != [_file_disposition_record(item) for item in files]
        ):
            raise ValueError("file closure")
        binding_identities = {
            (
                item["campaign_slug"],
                item["logical_path"],
                item["object_path"],
                item["sha256"],
            )
            for item in files
        }
        for family_name in FAMILY_NAMES:
            _verify_projected_file_bindings(
                json_payloads[f"families/{family_name}.json"],
                file_bindings=binding_identities,
            )
        _verify_field_quarantines_from_snapshot(
            snapshot_path=stage / "source" / "database.sqlite3",
            schema=schema,
            campaign_slugs=campaign_slugs,
            session_family=json_payloads["families/session_history.json"],
            dispositions=dispositions,
            tables_inventory=tables,
            host_path_bindings=host_path_bindings,
            approved_campaign_root_keys=approved_campaign_root_keys,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package file custody registry is invalid."
        ) from exc
    expected_campaigns = []
    try:
        trusted_campaign_order = [
            item["campaign_slug"] for item in expected_manifest["campaigns"]
        ]
        if set(trusted_campaign_order) != set(trusted_campaign_ids):
            raise ValueError("campaign order")
        for slug in trusted_campaign_order:
            stable_id = trusted_campaign_ids[slug]
            records = [
                record
                for record in files
                if isinstance(record, dict)
                and record.get("campaign_stable_id") == stable_id
            ]
            if any(not isinstance(record, dict) for record in files):
                raise TypeError("files")
            expected_campaigns.append(
                {
                    "campaign_slug": slug,
                    "campaign_stable_id": stable_id,
                    "file_count": len(records),
                    "content_sha256": _digest_json(records),
                }
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package campaign descriptors are invalid."
        ) from exc
    campaigns = manifest.get("campaigns")
    if (
        campaigns != expected_campaigns
        or not isinstance(campaigns, list)
        or any(
            not isinstance(item, dict)
            or set(item)
            != {"campaign_slug", "campaign_stable_id", "content_sha256", "file_count"}
            or type(item.get("file_count")) is not int
            for item in campaigns
        )
        or len(
            {item.get("campaign_slug") for item in campaigns if isinstance(item, dict)}
        )
        != len(campaigns)
        or len(
            {
                item.get("campaign_stable_id")
                for item in campaigns
                if isinstance(item, dict)
            }
        )
        != len(campaigns)
        or {
            item["campaign_slug"]: item["campaign_stable_id"] for item in campaigns
        }
        != trusted_campaign_ids
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package campaign descriptors are invalid."
        )

    exporter = manifest.get("exporter")
    if (
        not isinstance(exporter, dict)
        or set(exporter) != {"commit", "tree"}
        or exporter != expected_manifest.get("exporter")
        or not all(
            isinstance(value, str) and _HEX40.fullmatch(value)
            for value in exporter.values()
        )
        or manifest.get("source_stable_id") != expected_manifest.get("source_stable_id")
        or not isinstance(manifest.get("source_stable_id"), str)
        or not _SAFE_ID.fullmatch(manifest["source_stable_id"])
    ):
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package invocation identity is invalid."
        )

    safe_summary = json_payloads.get("evidence/safe-summary.json")
    expected_safe_summary = {
        "blob_count": len(blobs),
        "campaign_count": len(trusted_campaign_ids),
        "disposition_totals": recomputed_totals,
        "family_counts": family_counts,
        "file_count": len(files),
        "source_unchanged": True,
        "table_count": len(tables),
    }
    if safe_summary != expected_safe_summary:
        raise CampaignCutoverExportError(
            "self_verification_failed", "The package safe summary is invalid."
        )


def _safe_artifact_path(stage: Path, relative: str) -> Path:
    if not _is_safe_relative_package_path(relative):
        raise CampaignCutoverExportError(
            "self_verification_failed", "A package artifact path is unsafe."
        )
    pure = PurePosixPath(relative)
    path = stage / Path(*pure.parts)
    resolved = path.resolve()
    stage_resolved = stage.resolve()
    if stage_resolved not in resolved.parents:
        raise CampaignCutoverExportError(
            "self_verification_failed", "A package artifact path escapes the package root."
        )
    _assert_regular_single_link(path, "package artifact")
    return path


def _is_safe_relative_package_path(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if (
        unicodedata.normalize("NFC", value) != value
        or "\x00" in value
        or "\\" in value
        or "%" in value
    ):
        return False
    if value.startswith("/") or re.match(r"^[a-z]:", value, re.IGNORECASE):
        return False
    parts = value.split("/")
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _publish_stage(stage: Path, output_dir: Path) -> None:
    _verify_private_package_tree(stage)
    if stage.parent.resolve() != output_dir.parent.resolve():
        raise CampaignCutoverExportError(
            "atomic_publication_unsupported",
            "The cutover package cannot be published atomically on this platform.",
        )
    if os.name == "nt":
        move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move_file.restype = ctypes.c_int
        if move_file(str(stage), str(output_dir), 0):
            return
        error = ctypes.get_last_error()
        if error in {80, 183}:
            raise CampaignCutoverExportError(
                "output_collision",
                "The cutover package destination was claimed concurrently.",
            )
        raise ctypes.WinError(error)
    if os.name == "posix" and sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename_at_2 = getattr(libc, "renameat2", None)
        if rename_at_2 is None:
            raise CampaignCutoverExportError(
                "atomic_publication_unsupported",
                "The cutover package cannot be published atomically on this platform.",
            )
        rename_at_2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_at_2.restype = ctypes.c_int
        if rename_at_2(
            -100,
            os.fsencode(stage),
            -100,
            os.fsencode(output_dir),
            1,
        ) == 0:
            return
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise CampaignCutoverExportError(
                "output_collision",
                "The cutover package destination was claimed concurrently.",
            )
        if error in {
            errno.EINVAL,
            errno.ENOSYS,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }:
            raise CampaignCutoverExportError(
                "atomic_publication_unsupported",
                "The cutover package cannot be published atomically on this platform.",
            )
        raise OSError(error, os.strerror(error), str(output_dir))
    raise CampaignCutoverExportError(
        "atomic_publication_unsupported",
        "The cutover package cannot be published atomically on this platform.",
    )


def _remove_owned_stage(stage: Path, parent: Path, output_name: str) -> None:
    try:
        resolved = stage.resolve()
        parent_resolved = parent.resolve()
        expected_prefix = f".{output_name}.cutover-stage-"
        if resolved.parent != parent_resolved or not resolved.name.startswith(expected_prefix):
            raise CampaignCutoverExportError(
                "private_residue_retained",
                "Private invocation residue was retained because ownership could not be proved.",
            )
        shutil.rmtree(resolved)
    except CampaignCutoverExportError:
        raise
    except OSError as exc:
        raise CampaignCutoverExportError(
            "private_residue_retained",
            "Private invocation residue was retained after cleanup failed.",
        ) from exc


def _placeholders(values: Iterable[Any]) -> str:
    count = len(tuple(values))
    if count <= 0:
        raise CampaignCutoverExportError(
            "missing_scope", "The approved campaign scope is empty."
        )
    return ",".join("?" for _ in range(count))


def _quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise CampaignCutoverExportError(
            "invalid_schema_identifier", "The SQLite schema contains an unsafe identifier."
        )
    return '"' + value + '"'
