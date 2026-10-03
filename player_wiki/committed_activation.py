"""Private, one-way committed-source activation for a fully admitted local corpus."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from pathlib import PurePosixPath

from .backup_archive import (DEFAULT_LIMITS, BackupArchiveError, _is_reparse_point,
                             _scan_campaign_files,
                             create_backup_archive_v2, inspect_backup_archive)
from .committed_publication import CommittedSourceConflict, active
from .committed_source_store import (_classify, _decode_mapping,
                                     _legacy_enum_values_valid, _validate_config_payload,
                                     _validated_character_dir)
from .migrations import inspect_migration_ledger
from .snapshot_coherence import inspect_snapshot_coherence
from .campaign_content_service import validated_campaign_asset_media_type
from .character_assets import validate_character_portrait_asset_ref
from .managed_wiki_images import is_canonical_managed_wiki_image_ref
from .character_models import CharacterDefinition
from .character_source_authority import (MANUAL, VERIFIED,
                                         build_source_authority,
                                         numeric_target_values,
                                         numeric_target_owner_digest,
                                         numeric_value_digest,
                                         valid_numeric_authorization)
from .character_equipment_activation import effective_definition
from .character_source_repair import (load_verified_manual_actions,
                                      load_verified_numeric_actions,
                                      SourceRepairError)
from .campaign_visibility import is_valid_visibility, normalize_visibility_choice
from .campaign_page_store import CampaignPageStore
from .systems_service import BUILTIN_LIBRARY_CATALOG
from .systems_store import SystemsStore
from .system_policy import default_systems_library_slug
from .committed_character_publication import _create_source_links, _create_source_proof
from .runtime_lease import acquire_exclusive_state_lease, RuntimeStateLeaseError
from .snapshot_coherence import SnapshotCoherenceError
from .legacy_page_exclusion import proved_exclusions


class ActivationRefused(ValueError):
    pass


class ActivationUncertain(ActivationRefused):
    pass


def _paths(db_path: Path, campaigns_dir: Path, backup_root: Path | None = None):
    def inside_checkout(path: Path) -> bool:
        return any((parent / ".git").exists() for parent in (path, *path.parents))

    if (Path(db_path).is_symlink() or Path(campaigns_dir).is_symlink()
            or _is_reparse_point(Path(db_path)) or _is_reparse_point(Path(campaigns_dir))):
        raise ActivationRefused("Activation target paths must be regular paths.")
    db = Path(db_path).resolve(strict=True)
    campaigns = Path(campaigns_dir).resolve(strict=True)
    if not db.is_file() or not campaigns.is_dir() or db.is_relative_to(campaigns):
        raise ActivationRefused("Activation target paths are invalid.")
    if inside_checkout(db) or inside_checkout(campaigns):
        raise ActivationRefused("Activation targets must be outside the repository.")
    if backup_root is not None:
        if Path(backup_root).is_symlink() or _is_reparse_point(Path(backup_root)):
            raise ActivationRefused("Activation backup must be a regular path.")
        backup = Path(backup_root).resolve(strict=False)
        if inside_checkout(backup):
            raise ActivationRefused("Activation backup must be outside the repository.")
        if (backup == db or backup == campaigns or backup.is_relative_to(campaigns)
                or campaigns.is_relative_to(backup) or db.is_relative_to(backup)):
            raise ActivationRefused("Activation backup path overlaps its source.")
    return db, campaigns


def _connection(path: Path, *, readonly: bool):
    if readonly:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _rows_digest(rows) -> str:
    """Keep private evidence in the identity without exposing row content."""
    payload = [tuple(row) for row in rows]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


class _PinnedSystems:
    """Read-only Character source adapter over the inventory's SQLite snapshot."""

    def __init__(self, connection: sqlite3.Connection, slug: str, config: dict,
                 config_revision: int, config_sha256: str, *, projected: bool,
                 character_read: bool = False):
        self.slug = slug
        self.library_slug = default_systems_library_slug(
            config.get("systems_library") or config["system"])
        revision = connection.execute(
            "SELECT token FROM systems_revision WHERE singleton=1").fetchone()
        library = connection.execute(
            "SELECT * FROM systems_libraries WHERE library_slug=?", (self.library_slug,)
        ).fetchone()
        if revision is None or library is None:
            raise ValueError("Systems proof unavailable")
        self.revision = str(revision[0])
        self.config_sha256 = config_sha256
        self.config_revision = config_revision
        self.projected = projected
        self.character_read = character_read
        seeds = {str(item.get("source_id") or "").strip(): item for item in
                 config.get("systems_sources", []) if isinstance(item, dict)}
        self.defaults = tuple(sorted((source_id,
            bool(seed["enabled"]) if "enabled" in seed else None,
            (normalized if is_valid_visibility(normalized) else ""))
            for source_id, seed in seeds.items() if source_id
            for normalized in (normalize_visibility_choice(
                str(seed.get("default_visibility") or "")),)))
        builtin = {str(item["source_id"]): item for item in
                   BUILTIN_LIBRARY_CATALOG.get(self.library_slug, {}).get("sources", ())}
        configured = {row["source_id"]: row for row in connection.execute(
            "SELECT * FROM campaign_enabled_sources WHERE campaign_slug=? AND library_slug=?",
            (slug, self.library_slug))}
        sources = connection.execute(
            "SELECT * FROM systems_sources WHERE library_slug=?", (self.library_slug,)).fetchall()
        enabled = set()
        for source in sources:
            source_id = source["source_id"]
            override = configured.get(source_id)
            seed = seeds.get(source_id, {})
            is_enabled = (bool(override["is_enabled"]) if override is not None else
                          bool(seed["enabled"]) if "enabled" in seed else
                          bool(builtin.get(source_id, {}).get("enabled_by_default", False)))
            if is_enabled:
                enabled.add(source_id)
        disabled_entries = {row["entry_key"] for row in connection.execute(
            """SELECT entry_key FROM campaign_entry_overrides WHERE campaign_slug=?
               AND library_slug=? AND is_enabled_override=0""", (slug, self.library_slug))}
        store = SystemsStore()
        self.entries = tuple(store._map_entry(row) for row in connection.execute(
            "SELECT * FROM systems_entries WHERE library_slug=? ORDER BY title,id",
            (self.library_slug,)) if row["source_id"] in enabled
            and row["entry_key"] not in disabled_entries)
        self.by_key = {entry.entry_key: entry for entry in self.entries}
        self.by_slug = {entry.slug: entry for entry in self.entries}

    def get_builder_static_revision_for_character_read(self, campaign_slug, *, entry_types):
        self._campaign(campaign_slug)
        types = tuple(sorted({str(value or "").strip() for value in entry_types
                              if str(value or "").strip()}))
        if not types:
            return None
        context = (self.library_slug, self.defaults)
        if self.projected:
            context += (self.config_revision, self.config_sha256, self.revision)
        if self.character_read:
            context += ((),)
        return (self.library_slug, types, context, self.revision)

    def _campaign(self, slug):
        if slug != self.slug:
            raise ValueError("Systems campaign mismatch")

    def get_entry_for_campaign(self, slug, key):
        self._campaign(slug)
        return self.by_key.get(key)

    def get_entry_by_slug_for_campaign(self, slug, key):
        self._campaign(slug)
        return self.by_slug.get(key)

    def is_entry_enabled_for_campaign(self, slug, entry):
        self._campaign(slug)
        return self.by_key.get(entry.entry_key) is entry

    def list_enabled_entries_for_campaign(self, slug, *, entry_type=None, **_kwargs):
        self._campaign(slug)
        return [entry for entry in self.entries if entry_type is None or entry.entry_type == entry_type]


def _pinned_pages(connection: sqlite3.Connection, slug: str, config_revision: int,
                  current_session: int) -> list[object]:
    """Mirror activated eligible page projection without ambient DB or seeding."""
    store = CampaignPageStore()
    records = []
    for row in connection.execute("SELECT * FROM campaign_pages WHERE campaign_slug=?", (slug,)):
        current = connection.execute("""SELECT c.revision,g.tombstone,a.status,a.revision AS admitted_revision
            FROM committed_source_current c JOIN committed_source_generations g
            USING(campaign_slug,object_kind,object_ref,revision)
            JOIN committed_source_admission a USING(campaign_slug,object_kind,object_ref)
            WHERE c.campaign_slug=? AND c.object_kind='page' AND c.object_ref=?""",
            (slug, row["page_ref"])).fetchone()
        if (current is None or current["tombstone"] or current["status"] != "admitted"
                or current["revision"] != current["admitted_revision"]):
            continue
        record = store._map_record(row, include_body=False)
        page = record.page
        if (not page.published or page.is_deprecated_wiki_overview
                or page.reveal_after_session > current_session):
            continue
        page.committed_revision = current["revision"]
        page.committed_config_revision = config_revision
        records.append(record)
    return records


def _transition_targets(definition: CharacterDefinition, state: dict,
                        closed, projected, origins: tuple[dict, ...],
                        identity: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Prove a mode-only change for each presently effective source-bound owner."""
    values = numeric_target_values(definition, state)
    markers = list(dict(definition.source or {}).get("source_authorizations") or [])
    old_bases = dict(closed.resource_basis_digests)
    new_bases = dict(projected.resource_basis_digests)
    spellcasting = dict(definition.spellcasting or {})
    for rows, id_key in ((spellcasting.get("spells"), "id"),
                         (spellcasting.get("class_rows"), "class_row_id"),
                         (spellcasting.get("source_rows"), "source_row_id")):
        ids = [str(row.get(id_key) or "").strip() for row in list(rows or [])
               if isinstance(row, dict)]
        if len(ids) != len(list(rows or [])) or any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Spell identity ambiguous")
    if ([(row.kind,row.instance_id,row.status) for row in closed.statuses]
            != [(row.kind,row.instance_id,row.status) for row in projected.statuses]
            or closed.verified_class_rows != projected.verified_class_rows
            or closed.verified_source_rows != projected.verified_source_rows
            or [(row.grant_id,row.payload_json) for row in closed.grants]
            != [(row.grant_id,row.payload_json) for row in projected.grants]):
        raise ValueError("Projected source content changed")
    allowed_changes = {target for (kind,target,_metric) in values
                       if kind in {"spell_metric", "spell_choice"}
                       or kind == "resource" and target.startswith(
                           "resource:campaign-option-tracker:")}
    if any(old_bases.get(target) != new_bases.get(target)
           for target in set(old_bases) | set(new_bases) if target not in allowed_changes):
        raise ValueError("Unexpected numeric basis change")
    proofs: list[dict[str, object]] = []
    for (kind, target_id, metric), raw in values.items():
        if kind == "spell_choice":
            required = target_id.removeprefix("spell_choice:") in closed.verified_spell_choices
        elif kind == "spell_metric":
            required = isinstance(raw, dict) and raw.get("value") is not None
        elif kind == "resource":
            required = target_id.startswith("resource:campaign-option-tracker:")
        else:
            continue
        if not required:
            continue
        old_basis, new_basis = old_bases.get(target_id), new_bases.get(target_id)
        if not old_basis or not new_basis:
            raise ValueError("Source-bound basis unavailable")
        if old_basis == new_basis:
            continue
        matching = [row for row in markers if isinstance(row, dict)
                    and (row.get("target_kind"), row.get("target_id"), row.get("metric"))
                    == (kind, target_id, metric)]
        if len(matching) != 1:
            raise ValueError("Source-bound marker ambiguous")
        marker = matching[0]
        owner = numeric_target_owner_digest(definition, state, kind, target_id, metric)
        original = [row for row in origins if isinstance(row.get("witness"), dict)
                    and row["witness"].get("authorization") == marker
                    and row["witness"].get("source_basis_digest") == old_basis]
        if (len(original) != 1 or not valid_numeric_authorization(
                marker, character_slug=definition.character_slug, target_kind=kind,
                target_id=target_id, metric=metric, raw_value=raw,
                owner_digest=owner, verified_actions=(marker,))):
            raise ValueError("Source-bound audit ambiguous")
        if (marker.get("provenance") != "page_feature_update"
                and original[0].get("source_snapshot_digest") != closed.source_snapshot_digest):
            raise ValueError("Original source snapshot changed")
        if kind == "resource" and (marker.get("provenance") != "page_feature_update"
                                    or marker.get("source_snapshot_digest") != closed.source_snapshot_digest
                                    or marker.get("source_basis_digest") != old_basis):
            raise ValueError("Page source witness changed")
        if kind == "spell_metric" and target_id not in closed.verified_formula_rows:
            raise ValueError("Original formula is not effective")
        if kind == "resource" and not any(row.path == target_id and row.is_effective
                                          for row in closed.resource_statuses):
            raise ValueError("Original tracker is not effective")
        proof = {"schema_version": 1, "campaign_slug": definition.campaign_slug,
                 "character_slug": definition.character_slug, "target_kind": kind,
                 "target_id": target_id, "metric": metric, "authorization": marker,
                 "origin_audit_id": original[0]["audit_id"],
                 "origin_actor_user_id": original[0]["actor_user_id"],
                 "origin_event_type": original[0]["event_type"],
                 "origin_metadata_sha256": original[0]["metadata_sha256"],
                 "old_basis": old_basis, "new_basis": new_basis,
                 "old_snapshot": closed.source_snapshot_digest,
                 "new_snapshot": projected.source_snapshot_digest,
                 "value_digest": numeric_value_digest(raw), "owner_digest": owner,
                 "identity": identity}
        proofs.append(proof)
    return tuple(proofs)


def _inventory(connection: sqlite3.Connection, campaigns_dir: Path, *,
               include_proofs: bool = False) -> dict[str, object]:
    if not connection.in_transaction:
        raise ActivationRefused("Readiness needs a pinned SQLite snapshot.")
    try:
        ledger = inspect_migration_ledger(connection)
        if not ledger.is_current or ledger.applied_version != 18 or active(connection):
            raise ActivationRefused("The target is not a trusted closed v18 database.")
        if not _legacy_enum_values_valid(connection):
            raise ActivationRefused("Legacy enum proof is invalid.")
        files = _scan_campaign_files(campaigns_dir, DEFAULT_LIMITS)
        file_map = {item[0]: item for item in files}
        excluded = proved_exclusions(
            connection,
            {path: (size, digest) for path, _, size, digest, _ in files},
            source_files={path: source for path, source, _, _, _ in files},
        )
        coherence = inspect_snapshot_coherence(
            connection, files=((path, size, digest) for path, _, size, digest, _ in files),
            require_current=True,
        )
        issues: list[dict[str, str]] = []
        authority_evidence: list[tuple[str, str, str]] = []
        transition_proofs: list[dict[str, object]] = []
        def issue(slug: str, kind: str, ref: str, code: str):
            issues.append({"campaign_slug": slug, "kind": kind, "ref": ref, "reason_code": code})

        file_slugs = {p.name for p in campaigns_dir.iterdir() if p.is_dir()}
        source_file_paths: set[str] = set()
        db_slugs = set()
        for table in ("committed_source_current", "committed_source_admission",
                      "campaign_pages", "character_state", "campaign_memberships",
                      "campaign_visibility_settings"):
            db_slugs.update(row[0] for row in connection.execute(
                f"SELECT DISTINCT campaign_slug FROM {table}"))
        slugs = sorted(file_slugs | db_slugs)
        if not slugs:
            issue("", "config", "", "no_configured_campaign")
        pointers = {}
        configs: dict[str, tuple[dict, object]] = {}
        authority_sources: dict[str, tuple[_PinnedSystems, tuple[_PinnedSystems, ...],
                                            list[object], str, str]] = {}
        for row in connection.execute("""SELECT c.campaign_slug,c.object_kind,c.object_ref,
                c.revision,g.system_code,g.primary_bytes,g.secondary_bytes,
                g.primary_sha256,g.secondary_sha256,g.tombstone,a.status,a.revision AS admitted_revision
                FROM committed_source_current c LEFT JOIN committed_source_generations g
                USING(campaign_slug,object_kind,object_ref,revision)
                LEFT JOIN committed_source_admission a USING(campaign_slug,object_kind,object_ref)
                ORDER BY c.campaign_slug,c.object_kind,c.object_ref"""):
            pointers[(row["campaign_slug"], row["object_kind"], row["object_ref"])] = row
        for row in connection.execute("SELECT campaign_slug,object_kind,object_ref,status,reason_code FROM committed_source_admission"):
            key = (row["campaign_slug"],row["object_kind"],row["object_ref"])
            if key in excluded:
                continue
            if row["status"] != "admitted" or key not in pointers:
                issue(*key,"unresolved_admission")
        try:
            if connection.execute("""SELECT 1 FROM auth_audit_log
                    WHERE event_type='character_source_transition_confirmed' LIMIT 1""").fetchone():
                issue("","audit","","premature_transition_proof")
        except sqlite3.Error:
            issue("","audit","","audit_proof_unavailable")
        for slug in slugs:
            config = pointers.get((slug,"config",""))
            if config is None or config["tombstone"] or config["status"] != "admitted":
                issue(slug,"config","","missing_config")
                continue
            parsed = _decode_mapping(config["primary_bytes"])
            reason, settings = _validate_config_payload(parsed,slug)
            if reason or settings is None:
                issue(slug,"config","",reason or "invalid_config")
                continue
            configs[slug] = (parsed, settings)
            expected = {(slug,"config","")}
            source_file_paths.add(f"{slug}/campaign.yaml")
            for row in connection.execute("SELECT character_slug FROM character_state WHERE campaign_slug=?",(slug,)):
                expected.add((slug,"character",row[0]))
            for row in connection.execute("SELECT page_ref FROM campaign_pages WHERE campaign_slug=?",(slug,)):
                expected.add((slug,"page",row[0]))
            content_dir = _validated_character_dir(parsed.get("player_content_dir", "content"))
            if content_dir is None:
                issue(slug,"config","","unsafe_content_root")
                continue
            prefix = f"{slug}/{content_dir}/"
            for path in file_map:
                if path.startswith(prefix) and path.endswith(".md"):
                    expected.add((slug,"page",path[len(prefix):-3]))
            character_root = campaigns_dir/slug/settings.character_dir
            if character_root.is_dir():
                for child in character_root.iterdir():
                    if child.is_dir():
                        expected.add((slug,"character",child.name))
            for key in expected:
                if key[1] == "character":
                    source_file_paths.update((f"{slug}/{settings.character_dir}/{key[2]}/definition.yaml",
                                              f"{slug}/{settings.character_dir}/{key[2]}/import.yaml"))
                elif key[1] == "page":
                    source_file_paths.add(f"{slug}/{content_dir}/{key[2]}.md")
            for key in sorted(expected):
                if key in excluded:
                    continue
                row = pointers.get(key)
                if row is None:
                    issue(*key,"missing_committed_object")
                elif row["tombstone"]:
                    if key in expected:
                        issue(*key,"deleted_in_scope_object")
        for key,row in pointers.items():
            slug,kind,ref = key
            if slug not in slugs or row["tombstone"]:
                continue
            if (row["primary_bytes"] is None or row["status"] != "admitted"
                    or row["admitted_revision"] != row["revision"]):
                issue(*key,"unproved_current_generation")
                continue
            primary = bytes(row["primary_bytes"])
            secondary = bytes(row["secondary_bytes"]) if row["secondary_bytes"] is not None else None
            if (hashlib.sha256(primary).hexdigest() != row["primary_sha256"] or
                    (secondary is None) != (row["secondary_sha256"] is None) or
                    (secondary is not None and hashlib.sha256(secondary).hexdigest() != row["secondary_sha256"])):
                issue(*key,"invalid_generation_digest")
                continue
            reason = _classify(connection,slug,kind,ref,primary,secondary)
            if reason:
                issue(*key,reason)
            if kind == "page":
                page = connection.execute("SELECT image_path FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",(slug,ref)).fetchone()
                image_ref = page[0] if page else ""
                if image_ref and image_ref.startswith("wiki-managed"):
                    image = connection.execute("""SELECT sha256,image_bytes FROM committed_page_images
                        WHERE campaign_slug=? AND page_ref=? AND revision=? AND asset_ref=?""",
                        (slug,ref,row["revision"],image_ref)).fetchone()
                    if (not is_canonical_managed_wiki_image_ref(image_ref) or image is None or
                            hashlib.sha256(image[1]).hexdigest()!=image[0] or
                            validated_campaign_asset_media_type(PurePosixPath(image_ref),data_blob=image[1]) is None):
                        issue(*key,"invalid_current_image")
            elif kind == "character":
                state_row = connection.execute("SELECT revision,state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",(slug,ref)).fetchone()
                try:
                    if state_row is None:
                        raise ValueError("missing state")
                    definition = CharacterDefinition.from_dict(_decode_mapping(primary))
                    state = json.loads(state_row["state_json"])
                    if not isinstance(state,dict):
                        raise ValueError("invalid state")
                    if definition.system.lower() in {"dnd-5e","dnd5e","dnd_5e"}:
                        if slug not in authority_sources:
                            config_payload, settings = configs[slug]
                            config_pointer = pointers[(slug,"config","")]
                            systems = _PinnedSystems(connection,slug,config_payload,
                                config_pointer["revision"],config_pointer["primary_sha256"],
                                projected=False)
                            projected_systems = tuple(_PinnedSystems(connection,slug,config_payload,
                                config_pointer["revision"],config_pointer["primary_sha256"],
                                projected=True,character_read=read_view)
                                for read_view in (False,True))
                            pages = _pinned_pages(connection,slug,
                                pointers[(slug,"config","")]["revision"],settings.current_session)
                            pages_digest = _rows_digest(connection.execute(
                                "SELECT * FROM campaign_pages WHERE campaign_slug=? ORDER BY page_ref",(slug,)))
                            page_current_digest = _rows_digest(connection.execute(
                                """SELECT * FROM committed_source_current WHERE campaign_slug=?
                                   AND object_kind='page' ORDER BY object_ref""",(slug,)))
                            authority_sources[slug] = (systems,projected_systems,pages,
                                                       pages_digest,page_current_digest)
                        systems,projected_systems,pages,pages_digest,page_current_digest = authority_sources[slug]
                        audit_rows = connection.execute("""SELECT id,actor_user_id,event_type,metadata_json
                            FROM auth_audit_log WHERE campaign_slug=? AND character_slug=? ORDER BY id""",
                            (slug,ref)).fetchall()
                        manual = load_verified_manual_actions(slug,ref,connection=connection,strict=True)
                        numeric = load_verified_numeric_actions(slug,ref,connection=connection,strict=True)
                        origins = load_verified_numeric_actions(slug,ref,connection=connection,
                                                                strict=True,include_origin=True)
                        reconciled,_ = effective_definition(definition,state)
                        closed_authority = build_source_authority(
                            definition=reconciled,state=state,state_revision=state_row["revision"],
                            systems_service=systems,campaign_page_records=pages,
                            verified_manual_actions=manual,verified_numeric_actions=numeric,
                        ).bind_projected_numbers(reconciled)
                        projected_authorities = []
                        identity_inputs = {
                            "generation": (row["revision"],row["primary_sha256"]),
                            "state": (state_row["revision"],hashlib.sha256(
                                state_row["state_json"].encode()).hexdigest()),
                            "audit": _rows_digest(audit_rows),
                            "pages": pages_digest, "page_current": page_current_digest,
                            "systems": systems.revision,
                            "config": (pointers[(slug,"config","")]["revision"],
                                       pointers[(slug,"config","")]["primary_sha256"]),
                        }
                        for projected_system in projected_systems:
                            projected = build_source_authority(
                                definition=reconciled,state=state,
                                state_revision=state_row["revision"],
                                systems_service=projected_system,campaign_page_records=pages,
                                verified_manual_actions=manual,verified_numeric_actions=numeric,
                            )
                            proofs = _transition_targets(reconciled,state,closed_authority,
                                                          projected,origins,identity_inputs)
                            transition_proofs.extend(proofs)
                            transitioned = tuple({"authorization": proof["authorization"],
                                "source_basis_digest": proof["new_basis"],
                                "transition_proof": proof} for proof in proofs)
                            effective = build_source_authority(
                                definition=reconciled,state=state,
                                state_revision=state_row["revision"],
                                systems_service=projected_system,campaign_page_records=pages,
                                verified_manual_actions=manual,
                                verified_numeric_actions=(*numeric,*transitioned),
                            ).bind_projected_numbers(reconciled)
                            projected_authorities.append(effective)
                        authority = projected_authorities[-1]
                        authority_evidence.append((slug,ref,hashlib.sha256(json.dumps({
                            "generation":(row["revision"],row["primary_sha256"]),
                            "state":(state_row["revision"],state_row["state_json"]),
                            "audit":_rows_digest(audit_rows),
                            "pages":pages_digest,
                            "page_current":page_current_digest,
                            "systems":systems.revision,
                            "closed_authority":closed_authority.identity,
                            "projected_authorities":[item.identity for item in projected_authorities],
                        },sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()))
                        values = numeric_target_values(reconciled,state)
                        required_choices = closed_authority.verified_spell_choices
                        for authority in projected_authorities:
                            if any(status.status not in {VERIFIED,MANUAL} for status in authority.statuses
                                   if (status.kind in {"class_row","feature","item","source_row"}
                                       or status.kind == "spell" and status.instance_id in required_choices)):
                                raise ValueError("current source unproved")
                            if any(status.raw is not None and not status.is_effective
                                   for status in authority.field_statuses):
                                raise ValueError("numeric owner unproved")
                            if any(not status.path.startswith("item_charge:")
                                   and status.raw is not None and not status.is_effective
                                   for status in authority.resource_statuses):
                                raise ValueError("resource owner unproved")
                            if any(kind == "spell_metric" and isinstance(value,dict)
                                   and value.get("value") is not None and target not in authority.verified_formula_rows
                                   for (kind,target,_metric),value in values.items()):
                                raise ValueError("spell formula unproved")
                            if any(choice not in authority.verified_spell_choices
                                   for choice in required_choices):
                                raise ValueError("spell choice unproved")
                    pages,entries = _create_source_links(definition,state)
                    _create_source_proof(slug,pages,entries,connection=connection)
                except Exception:
                    issue(*key,"unproved_character_source")
                profile = (_decode_mapping(primary) or {}).get("profile") or {}
                portrait_ref = profile.get("portrait_asset_ref","") if isinstance(profile,dict) else ""
                portraits = connection.execute("""SELECT asset_ref,sha256,image_bytes FROM committed_character_portraits
                    WHERE campaign_slug=? AND character_slug=? AND revision=?""",
                    (slug,ref,row["revision"])).fetchall()
                if portrait_ref:
                    try:
                        validate_character_portrait_asset_ref(ref,portrait_ref)
                        valid_ref = True
                    except ValueError:
                        valid_ref = False
                    if (not valid_ref or len(portraits)!=1 or portraits[0][0]!=portrait_ref or
                            hashlib.sha256(portraits[0][2]).hexdigest()!=portraits[0][1] or
                            validated_campaign_asset_media_type(PurePosixPath(portrait_ref),data_blob=portraits[0][2]) is None):
                        issue(*key,"invalid_current_portrait")
                elif portraits:
                    issue(*key,"unexpected_current_portrait")
        for row in connection.execute("SELECT campaign_slug,character_slug,revision,state_json FROM character_state"):
            try:
                state = json.loads(row["state_json"])
                if type(row["revision"]) is not int or row["revision"] < 1 or not isinstance(state,dict):
                    raise ValueError
            except (ValueError,TypeError):
                issue(row["campaign_slug"],"character",row["character_slug"],"invalid_state")
        for key,row in pointers.items():
            if key[1] == "character" and not row["tombstone"] and connection.execute(
                    "SELECT 1 FROM character_state WHERE campaign_slug=? AND character_slug=?",(key[0],key[2])).fetchone() is None:
                issue(*key,"missing_state")
        if connection.execute("""SELECT 1 FROM campaign_visibility_settings
                WHERE visibility NOT IN ('public','players','dm','private') OR
                scope NOT IN ('campaign','wiki','systems','session','combat','characters','dm_content')
                LIMIT 1""").fetchone():
            issue("","visibility","","invalid_visibility")
        for table in ("character_reconciliation_operations","character_deletion_operations",
                      "player_wiki_reconciliation_operations","player_wiki_deletion_operations"):
            if connection.execute(f"SELECT 1 FROM {table} WHERE state IN ('prepared','repository_pending','conflict') LIMIT 1").fetchone():
                issue("","journal","",f"pending_{table}")
        for table in ("committed_source_publications","committed_source_outbox","committed_source_mirrors"):
            states = ("prepared","conflict") if table.endswith("publications") else (("pending","retry","conflict") if table.endswith("outbox") else ("pending","conflict","missing","unknown"))
            placeholders = ",".join("?" for _ in states)
            if connection.execute(f"SELECT 1 FROM {table} WHERE state IN ({placeholders}) LIMIT 1",states).fetchone():
                issue("","custody","",f"unresolved_{table}")
        for item in coherence["file_dispositions"]:
            if item["state"] in ("missing","recoverable_draft_conflict"):
                issue("","mirror",item["path"],item["state"])
        for path in file_map:
            if path in source_file_paths and not any(
                    x["path"] == path and x["state"] in {"matching", "excluded_legacy_page"}
                    for x in coherence["file_dispositions"]):
                issue("","source",path,"unadmitted_file_source")
        issues.sort(key=lambda x:(x["campaign_slug"],x["kind"],x["ref"],x["reason_code"]))
        basis = {"campaigns":slugs,"coherence":coherence["canonical_sha256"],
                 "excluded_legacy_pages": sorted((key, proof["path"], proof["sha256"],
                                                   proof["marker"]) for key, proof in excluded.items()),
                 "authority":authority_evidence,
                 "transition_proofs":transition_proofs,
                 "files":[(p,size,digest) for p,_,size,digest,_ in files],"issues":issues}
        identity = hashlib.sha256(json.dumps(basis,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        result = {"ready":not issues,"readiness_sha256":identity,"campaign_count":len(slugs),
                "object_count":len(pointers),"issue_count":len(issues),"issues":issues[:100],
                "issues_truncated":len(issues)>100}
        if include_proofs:
            result["_transition_proofs"] = tuple(transition_proofs)
        return result
    except (sqlite3.Error, CommittedSourceConflict, SnapshotCoherenceError, BackupArchiveError) as exc:
        raise ActivationRefused("Committed readiness proof is unavailable.") from exc


def inspect_activation(*, db_path: Path, campaigns_dir: Path) -> dict[str,object]:
    db,campaigns = _paths(db_path,campaigns_dir)
    with closing(_connection(db,readonly=True)) as connection:
        connection.execute("BEGIN")
        try:
            return _inventory(connection,campaigns)
        finally:
            connection.rollback()


def activate(*, db_path: Path, campaigns_dir: Path, backup_root: Path,
             confirmed_target: str, readiness_sha256: str) -> dict[str,object]:
    db,campaigns = _paths(db_path,campaigns_dir,backup_root)
    if confirmed_target != str(db) or len(readiness_sha256) != 64:
        raise ActivationRefused("Target confirmation or readiness identity differs.")
    try:
        with acquire_exclusive_state_lease(db):
            return _activate_locked(db,campaigns,Path(backup_root),readiness_sha256)
    except RuntimeStateLeaseError as exc:
        raise ActivationRefused("The application must be stopped before activation.") from exc


def _activate_locked(db: Path, campaigns: Path, backup_root: Path,
                     readiness_sha256: str) -> dict[str,object]:
    before = inspect_activation(db_path=db,campaigns_dir=campaigns)
    if not before["ready"] or before["readiness_sha256"] != readiness_sha256:
        raise ActivationRefused("Readiness is blocked or stale.")
    now = datetime.now(UTC).isoformat()
    try:
        archive = create_backup_archive_v2(db_path=db,campaigns_dir=campaigns,
            backup_root=backup_root,archive_basename=f"pre-activation-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.zip",
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),verified_committed=True)
        verified = inspect_backup_archive(archive.archive_path)
    except (BackupArchiveError, OSError) as exc:
        raise ActivationRefused("Verified preactivation backup is unavailable.") from exc
    if verified.archive_path != archive.archive_path or not verified.manifest_hashes_verified:
        raise ActivationRefused("Verified preactivation backup is unavailable.")
    with closing(_connection(db,readonly=False)) as connection:
        connection.execute("PRAGMA synchronous=FULL")
        if int(connection.execute("PRAGMA synchronous").fetchone()[0]) < 2:
            raise ActivationRefused("Durable SQLite activation is unavailable.")
        connection.execute("BEGIN IMMEDIATE")
        try:
            locked = _inventory(connection,campaigns,include_proofs=True)
            if not locked["ready"] or locked["readiness_sha256"] != readiness_sha256:
                raise ActivationRefused("Readiness changed before activation.")
            if _inventory(connection,campaigns)["readiness_sha256"] != readiness_sha256:
                raise ActivationRefused("Campaign files changed during activation reservation.")
            expected_proofs = []
            stored_proofs = []
            for proof in locked["_transition_proofs"]:
                stored = {**proof,"activated_at":now}
                connection.execute("""INSERT INTO auth_audit_log
                    (actor_user_id,target_user_id,campaign_slug,character_slug,
                     event_type,metadata_json,created_at)
                    VALUES (NULL,NULL,?,?,'character_source_transition_confirmed',?,?)""",
                    (proof["campaign_slug"],proof["character_slug"],
                     json.dumps(stored,sort_keys=True,separators=(",",":"),ensure_ascii=False),now))
                expected_proofs.append((proof["campaign_slug"],proof["character_slug"],
                                        hashlib.sha256(json.dumps(stored,sort_keys=True,
                                            separators=(",",":"),ensure_ascii=False).encode()).hexdigest()))
                stored_proofs.append(stored)
            cursor = connection.execute("""UPDATE committed_source_activation
                SET activated=1,activated_at=?,coverage_version=1
                WHERE singleton=1 AND activated=0 AND activated_at IS NULL
                AND coverage_version=0 AND schema_version=18""",(now,))
            if cursor.rowcount != 1 or not active(connection):
                raise ActivationRefused("One-way activation proof failed.")
            try:
                connection.commit()
            except sqlite3.Error as exc:
                raise ActivationUncertain("Activation transaction outcome is uncertain.") from exc
        except (sqlite3.Error, CommittedSourceConflict, SourceRepairError):
            connection.rollback()
            raise ActivationRefused("Activation transaction proof failed.") from None
        except BaseException:
            connection.rollback()
            raise
    try:
        with closing(_connection(db,readonly=True)) as readback:
            readback.execute("BEGIN")
            marker = readback.execute("""SELECT activated,activated_at,coverage_version,schema_version
                FROM committed_source_activation WHERE singleton=1""").fetchone()
            if (marker is None or tuple(marker)!=(1,now,1,18) or not active(readback)):
                raise ActivationUncertain("Activation committed but readback did not confirm it.")
            actual_proofs = [(row[0],row[1],hashlib.sha256(row[2].encode()).hexdigest())
                for row in readback.execute("""SELECT campaign_slug,character_slug,metadata_json
                    FROM auth_audit_log WHERE event_type='character_source_transition_confirmed'
                    ORDER BY id""")]
            if actual_proofs != expected_proofs:
                raise ActivationUncertain("Activation committed but transition readback did not confirm it.")
            for proof in stored_proofs:
                loaded = load_verified_numeric_actions(proof["campaign_slug"],
                    proof["character_slug"],connection=readback,strict=True)
                if sum(json.dumps(witness.get("transition_proof"),sort_keys=True,default=str)
                       == json.dumps(proof,sort_keys=True,default=str) for witness in loaded
                       if isinstance(witness,dict)) != 1:
                    raise ActivationUncertain("Activation committed but transition authority is unavailable.")
    except (sqlite3.Error, CommittedSourceConflict, SourceRepairError) as exc:
        raise ActivationUncertain("Activation committed but readback is unavailable.") from exc
    return {"activated":True,"readiness_sha256":readiness_sha256,
            "backup_path":str(archive.archive_path),"activated_at":now}
