"""Bounded, payload-free evidence for a committed-source SQLite snapshot.

All SQL reads use the caller's already pinned snapshot.  File records are
relative paths, byte counts and digests captured by the caller; this module
never reads a live campaign tree or treats a mirror as source authority.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import PurePosixPath
from typing import Iterable

import yaml

from .character_assets import validate_character_portrait_asset_ref
from .committed_source_store import (
    _decode_mapping, _page_parity, _validate_config_payload, _validated_character_dir,
)
from .system_policy import normalize_system_code
from .legacy_page_exclusion import proved_exclusions, is_exclusion_claim


class SnapshotCoherenceError(ValueError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_sha(value: object) -> str:
    return _sha((json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False) + "\n").encode("utf-8"))


def _safe_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if (not value or path.as_posix() == "." or path.as_posix() != value.replace("\\", "/")
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in path.parts)
            or ":" in value or "\x00" in value):
        raise SnapshotCoherenceError("An authoritative mirror path is unsafe.")
    return path.as_posix()


def _blob(value: object, label: str) -> bytes:
    if not isinstance(value, bytes):
        raise SnapshotCoherenceError(f"{label} is not exact SQLite BLOB bytes.")
    return value


def _check_digest(value: object, digest: object, label: str) -> None:
    if value is None:
        if digest is not None:
            raise SnapshotCoherenceError(f"{label} has a digest without bytes.")
    elif not isinstance(digest, str) or _sha(_blob(value, label)) != digest:
        raise SnapshotCoherenceError(f"{label} bytes do not match their digest.")


def inspect_snapshot_coherence(
    connection: sqlite3.Connection,
    *,
    files: Iterable[tuple[str, int, str]] = (),
    require_current: bool = False,
    visible_campaigns: set[str] | None = None,
) -> dict[str, object]:
    """Verify canonical rows, image bindings and source-to-mirror disposition.

    The returned evidence contains hashes, revisions and status only.  It can
    therefore be placed in an unsealed manifest without disclosing draft data.
    """
    version_row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
    version = int(version_row[0] or 0) if version_row else 0
    if version < 15:
        if require_current:
            raise SnapshotCoherenceError("Committed-source schema is required.")
        return {"version": 1, "schema_version": version, "mode": "legacy",
                "objects": [], "file_dispositions": [], "blob_bindings": [],
                "canonical_sha256": _json_sha([])}
    if version > 18:
        raise SnapshotCoherenceError("The snapshot schema is newer than this reader.")
    from .committed_publication import active, CommittedSourceConflict
    try:
        trusted_active = active(connection)
    except CommittedSourceConflict as exc:
        raise SnapshotCoherenceError("The activation schema is untrusted.") from exc
    connection.row_factory = sqlite3.Row
    file_map: dict[str, tuple[int, str]] = {}
    for path, size, digest in files:
        path = _safe_path(path)
        if path in file_map or type(size) is not int or size < 0 or not isinstance(digest, str):
            raise SnapshotCoherenceError("The file inventory is ambiguous.")
        file_map[path] = (size, digest)
    excluded = proved_exclusions(connection, file_map, visible_campaigns=visible_campaigns)

    activation = connection.execute(
        "SELECT activated,activated_at,coverage_version,schema_version "
        "FROM committed_source_activation WHERE singleton=1"
    ).fetchall()
    if len(activation) != 1 or activation[0]["schema_version"] != (18 if version >= 18 else 15):
        raise SnapshotCoherenceError("The activation marker is incompatible.")
    marker = activation[0]
    if marker["activated"] == 0:
        if marker["activated_at"] is not None or marker["coverage_version"] != 0:
            raise SnapshotCoherenceError("The closed activation marker is inconsistent.")
    elif marker["activated"] == 1:
        if version < 18 or marker["coverage_version"] != 1:
            raise SnapshotCoherenceError("The active marker has no trusted transition.")
        try:
            timestamp = datetime.fromisoformat(marker["activated_at"])
        except (TypeError, ValueError) as exc:
            raise SnapshotCoherenceError("The active marker has no timestamp proof.") from exc
        if (marker["coverage_version"] < 1 or timestamp.tzinfo is None or
                timestamp.utcoffset() is None):
            raise SnapshotCoherenceError("The active marker is inconsistent.")
    else:
        raise SnapshotCoherenceError("The activation marker has an invalid state.")
    if bool(marker["activated"]) != trusted_active:
        raise SnapshotCoherenceError("The activation marker differs from trusted authority.")
    generations: dict[tuple[str, str, str, int], sqlite3.Row] = {}
    max_revision: dict[tuple[str, str, str], int] = {}
    for row in connection.execute("SELECT * FROM committed_source_generations ORDER BY campaign_slug,object_kind,object_ref,revision"):
        key = (row["campaign_slug"], row["object_kind"], row["object_ref"], row["revision"])
        obj = key[:3]
        if key in generations or row["revision"] < 1:
            raise SnapshotCoherenceError("The generation identity is ambiguous.")
        generations[key] = row
        max_revision[obj] = max(max_revision.get(obj, 0), row["revision"])
        tombstone = row["tombstone"] == 1
        for part in ("primary", "secondary"):
            _check_digest(row[f"{part}_bytes"], row[f"{part}_sha256"], f"generation {part}")
        if tombstone:
            if any(row[field] is not None for field in
                   ("primary_bytes", "secondary_bytes", "primary_sha256", "secondary_sha256")):
                raise SnapshotCoherenceError("A tombstone carries source bytes.")
        elif row["primary_bytes"] is None or (
            (row["object_kind"] == "character") != (row["secondary_bytes"] is not None)
        ):
            raise SnapshotCoherenceError("A generation has incomplete source bytes.")

    current: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in connection.execute("SELECT * FROM committed_source_current ORDER BY campaign_slug,object_kind,object_ref"):
        obj = (row["campaign_slug"], row["object_kind"], row["object_ref"])
        key = (*obj, row["revision"])
        if obj in current or key not in generations or max_revision[obj] != row["revision"]:
            raise SnapshotCoherenceError("A current pointer is missing, stale or ambiguous.")
        current[obj] = generations[key]
    if set(max_revision) != set(current):
        raise SnapshotCoherenceError("A generation has no current pointer.")
    generation_proofs = [
        {"campaign_slug": key[0], "object_kind": key[1], "object_ref": key[2],
         "revision": key[3], "tombstone": bool(row["tombstone"]),
         "primary_sha256": row["primary_sha256"],
         "secondary_sha256": row["secondary_sha256"]}
        for key, row in sorted(generations.items())
        if visible_campaigns is None or key[0] in visible_campaigns
    ]

    blob_bindings = []
    for table, ref_field in (("committed_page_images", "page_ref"),
                             ("committed_character_portraits", "character_slug")):
        if version < (16 if ref_field == "page_ref" else 17):
            continue
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY campaign_slug,{ref_field},revision,asset_ref"):
            obj_kind = "page" if ref_field == "page_ref" else "character"
            key = (row["campaign_slug"], obj_kind, row[ref_field], row["revision"])
            _check_digest(row["image_bytes"], row["sha256"], table)
            if key not in generations or generations[key]["tombstone"]:
                raise SnapshotCoherenceError("An image binds a missing or deleted generation.")
            blob_bindings.append({"table": table, "campaign_slug": row["campaign_slug"],
                                  "object_ref": row[ref_field], "revision": row["revision"],
                                  "asset_ref": row["asset_ref"], "sha256": row["sha256"],
                                  "size": len(row["image_bytes"])})
    bound_assets = {
        (item["table"], item["campaign_slug"], item["object_ref"],
         item["revision"], item["asset_ref"])
        for item in blob_bindings
    }
    for (slug, kind, ref), source in current.items():
        if source["tombstone"]:
            if activation[0]["activated"] and kind == "page" and connection.execute(
                "SELECT 1 FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",
                (slug, ref),
            ).fetchone() is not None:
                raise SnapshotCoherenceError("A deleted page still has an indexed row.")
            continue
    for row in connection.execute("SELECT * FROM committed_source_admission_receipts"):
        if (row["campaign_slug"], row["object_kind"], row["object_ref"], row["revision"]) not in generations:
            raise SnapshotCoherenceError("An admission receipt has no generation.")
    admissions = {}
    for row in connection.execute("SELECT * FROM committed_source_admission"):
        obj = (row["campaign_slug"], row["object_kind"], row["object_ref"])
        admissions[obj] = row
        if row["status"] == "admitted" and (obj not in current or row["revision"] != current[obj]["revision"]):
            raise SnapshotCoherenceError("An admission points away from current source.")
        if (activation[0]["activated"] and is_exclusion_claim(row["reason_code"])
                and (visible_campaigns is None or obj[0] in visible_campaigns)
                and obj not in excluded):
            raise SnapshotCoherenceError("An excluded legacy page lost its sealed proof.")
    if activation[0]["activated"]:
        from .campaign_content_service import validated_campaign_asset_media_type
        from .managed_wiki_images import is_canonical_managed_wiki_image_ref

        effective = {obj: source for obj, source in current.items()
                     if obj in admissions and admissions[obj]["status"] == "admitted"
                     and admissions[obj]["revision"] == source["revision"]
                     and not source["tombstone"]}
        if any(len(source["primary_bytes"]) > 2 * 1024 * 1024 or
               (source["secondary_bytes"] is not None and
                len(source["secondary_bytes"]) > 2 * 1024 * 1024)
               for source in effective.values()):
            raise SnapshotCoherenceError("Effective source exceeds runtime limits.")
        configs = {}
        for (slug, kind, ref), source in effective.items():
            if kind != "config":
                continue
            if ref or source["secondary_bytes"] is not None:
                raise SnapshotCoherenceError("Effective config identity is invalid.")
            parsed = _decode_mapping(source["primary_bytes"])
            reason, config = _validate_config_payload(parsed, slug)
            if reason or config is None or normalize_system_code(source["system_code"]) != config.system_code:
                raise SnapshotCoherenceError("Effective config semantics are invalid.")
            configs[slug] = config
        for (slug, kind, ref), source in effective.items():
            if kind == "config":
                continue
            config = configs.get(slug)
            if config is None or normalize_system_code(source["system_code"]) != config.system_code:
                raise SnapshotCoherenceError("Effective source and config systems differ.")
            if kind == "page":
                if _page_parity(connection, slug, ref, source["primary_bytes"],
                                config.current_session):
                    raise SnapshotCoherenceError("Effective page projection is invalid.")
                page = connection.execute(
                    "SELECT image_path FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",
                    (slug, ref),
                ).fetchone()
                image_ref = page["image_path"] or ""
                if image_ref.startswith("wiki-managed"):
                    if (not is_canonical_managed_wiki_image_ref(image_ref) or
                            ("committed_page_images", slug, ref, source["revision"], image_ref)
                            not in bound_assets):
                        raise SnapshotCoherenceError("Effective page image binding is invalid.")
                    image = connection.execute(
                        "SELECT image_bytes FROM committed_page_images WHERE campaign_slug=? "
                        "AND page_ref=? AND revision=? AND asset_ref=?",
                        (slug, ref, source["revision"], image_ref),
                    ).fetchone()
                    if image is None or validated_campaign_asset_media_type(
                        PurePosixPath(image_ref), data_blob=image[0]
                    ) is None:
                        raise SnapshotCoherenceError("Effective page image bytes are invalid.")
            elif kind == "character":
                definition = _decode_mapping(source["primary_bytes"])
                imported = _decode_mapping(source["secondary_bytes"])
                if (definition is None or imported is None or
                        definition.get("campaign_slug") != slug or
                        definition.get("character_slug") != ref or
                        imported.get("campaign_slug") != slug or
                        imported.get("character_slug") != ref or
                        not isinstance(definition.get("name"), str) or not definition["name"].strip() or
                        not isinstance(definition.get("status"), str) or not definition["status"].strip() or
                        normalize_system_code(definition.get("system")) != config.system_code or
                        not all(isinstance(imported.get(key), str) for key in
                                ("source_path", "imported_at_utc", "parser_version", "import_status")) or
                        not isinstance(imported.get("warnings"), list) or
                        not all(isinstance(item, str) for item in imported["warnings"])):
                    raise SnapshotCoherenceError("Effective Character pair identity is invalid.")
                profile = definition.get("profile") or {}
                if not isinstance(profile, dict):
                    raise SnapshotCoherenceError("Effective Character portrait metadata is invalid.")
                portrait_ref = str(profile.get("portrait_asset_ref") or "").strip()
                portraits = connection.execute(
                    "SELECT asset_ref,image_bytes FROM committed_character_portraits "
                    "WHERE campaign_slug=? AND character_slug=? AND revision=?",
                    (slug, ref, source["revision"]),
                ).fetchall() if version >= 17 else []
                if portrait_ref:
                    try:
                        validate_character_portrait_asset_ref(ref, portrait_ref)
                    except ValueError as exc:
                        raise SnapshotCoherenceError("Effective Character portrait binding is invalid.") from exc
                    if (version < 17 or len(portraits) != 1 or
                            portraits[0]["asset_ref"] != portrait_ref or
                            ("committed_character_portraits", slug, ref, source["revision"], portrait_ref)
                            not in bound_assets or validated_campaign_asset_media_type(
                                PurePosixPath(portrait_ref), data_blob=portraits[0]["image_bytes"]
                            ) is None):
                        raise SnapshotCoherenceError("Effective Character portrait binding is invalid.")
                elif portraits:
                    raise SnapshotCoherenceError("Unexpected effective Character portrait proof.")
    for row in connection.execute("SELECT * FROM committed_source_publications"):
        for part in ("desired_primary", "desired_secondary"):
            _check_digest(row[f"{part}_bytes"], row[f"{part}_sha256"], "publication")
        if row["committed_revision"] is not None and (
            row["campaign_slug"], row["object_kind"], row["object_ref"], row["committed_revision"]
        ) not in generations:
            raise SnapshotCoherenceError("A publication references no generation.")
    for row in connection.execute("SELECT * FROM committed_source_mirrors"):
        for part in ("primary", "secondary"):
            _check_digest(row[f"draft_{part}_bytes"], row[f"observed_{part}_sha256"]
                          if row[f"draft_{part}_bytes"] is not None else None, "mirror draft")
        obj = (row["campaign_slug"], row["object_kind"], row["object_ref"])
        if row["mirrored_revision"] is not None and (obj not in current or row["mirrored_revision"] > current[obj]["revision"]):
            raise SnapshotCoherenceError("A mirror references a future generation.")
        if row["state"] == "matching" and row["mirrored_revision"] is not None:
            generation = generations.get((*obj, row["mirrored_revision"]))
            if generation is None or (
                row["expected_primary_sha256"], row["expected_secondary_sha256"]
            ) != (generation["primary_sha256"], generation["secondary_sha256"]):
                raise SnapshotCoherenceError("A matching mirror has stale source evidence.")
    for row in connection.execute("SELECT * FROM committed_source_outbox"):
        key = (row["campaign_slug"], row["object_kind"], row["object_ref"], row["revision"])
        if key not in generations:
            raise SnapshotCoherenceError("An outbox entry has no generation.")
        basis = (row["expected_primary_sha256"], row["expected_secondary_sha256"])
        earlier = {
            (generation["primary_sha256"], generation["secondary_sha256"])
            for identity, generation in generations.items()
            if identity[:3] == key[:3] and identity[3] < key[3]
        }
        if basis not in earlier | {(None, None)}:
            raise SnapshotCoherenceError("An outbox entry has no prior mirror basis.")

    operation_journals: dict[str, dict[str, int]] = {}
    for table in (
        "player_wiki_reconciliation_operations",
        "player_wiki_deletion_operations",
        "character_reconciliation_operations",
        "character_deletion_operations",
    ):
        scope = "" if visible_campaigns is None else " WHERE campaign_slug IN ({})".format(
            ",".join("?" for _ in visible_campaigns) or "NULL"
        )
        rows = connection.execute(
            f"SELECT state,COUNT(*) FROM {table}{scope} GROUP BY state ORDER BY state",
            tuple(sorted(visible_campaigns)) if visible_campaigns is not None else (),
        ).fetchall()
        if len(rows) > 16 or any(not isinstance(row[0], str) or len(row[0]) > 64 for row in rows):
            raise SnapshotCoherenceError("An operational journal has invalid state evidence.")
        operation_journals[table] = {row[0]: row[1] for row in rows}

    expected: dict[str, tuple[str, str, str, int, str]] = {}
    objects = []
    settings_by_slug: dict[str, dict[str, object]] = {}
    for obj, row in sorted(current.items()):
        slug, kind, ref = obj
        if visible_campaigns is not None and slug not in visible_campaigns:
            continue
        revision = row["revision"]
        objects.append({"campaign_slug": slug, "object_kind": kind, "object_ref": ref,
                        "revision": revision, "tombstone": bool(row["tombstone"]),
                        "primary_sha256": row["primary_sha256"],
                        "secondary_sha256": row["secondary_sha256"]})
        if row["tombstone"]:
            continue
        root = _safe_path(slug)
        if kind == "config":
            if ref != "":
                raise SnapshotCoherenceError("A config reference is nonempty.")
            path = f"{root}/campaign.yaml"
            expected[path] = (*obj, revision, row["primary_sha256"])
            try:
                parsed = yaml.safe_load(_blob(row["primary_bytes"], "config").decode("utf-8"))
            except (UnicodeError, yaml.YAMLError, ValueError) as exc:
                raise SnapshotCoherenceError("Committed config cannot locate mirrors.") from exc
            if not isinstance(parsed, dict):
                raise SnapshotCoherenceError("Committed config is not a mapping.")
            settings_by_slug[slug] = parsed
        elif kind == "character":
            ref = _safe_path(ref)
            if "/" in ref:
                raise SnapshotCoherenceError("A character reference is nested.")
            config = current.get((slug, "config", ""))
            settings = settings_by_slug.get(slug)
            if settings is None and config is not None and not config["tombstone"]:
                settings = _decode_mapping(_blob(config["primary_bytes"], "config"))
            character_dir = _validated_character_dir(
                settings.get("character_dir", "characters") if settings is not None else "characters"
            )
            # Dormant/closed historical rows keep their prior default disposition;
            # an effective invalid config has already failed the parity check.
            character_dir = character_dir or "characters"
            for leaf, digest in (("definition.yaml", row["primary_sha256"]),
                                 ("import.yaml", row["secondary_sha256"])):
                expected[f"{root}/{character_dir}/{ref}/{leaf}"] = (*obj, revision, digest)
        else:
            config = current.get((slug, "config", ""))
            if config is None or config["tombstone"]:
                raise SnapshotCoherenceError("A page has no committed config.")
            settings = settings_by_slug.get(slug)
            if settings is None:
                try:
                    settings = yaml.safe_load(_blob(config["primary_bytes"], "config").decode("utf-8"))
                except (UnicodeError, yaml.YAMLError, ValueError) as exc:
                    raise SnapshotCoherenceError("Committed config cannot locate page mirrors.") from exc
            if not isinstance(settings, dict) or not isinstance(settings.get("player_content_dir", "content"), str):
                raise SnapshotCoherenceError("Committed page content root is invalid.")
            content_dir = _safe_path(settings.get("player_content_dir", "content"))
            page_ref = _safe_path(ref)
            expected[f"{root}/{content_dir}/{page_ref}.md"] = (*obj, revision, row["primary_sha256"])
    for binding in blob_bindings:
        slug = binding["campaign_slug"]
        if visible_campaigns is not None and slug not in visible_campaigns:
            continue
        ref = binding["object_ref"]
        obj_kind = "page" if binding["table"] == "committed_page_images" else "character"
        source = current.get((slug, obj_kind, ref))
        if source is None or source["revision"] != binding["revision"]:
            continue
        asset_ref = _safe_path(binding["asset_ref"])
        if obj_kind == "page":
            settings = settings_by_slug.get(slug)
            if settings is None or not isinstance(settings.get("asset_dir", "assets"), str):
                raise SnapshotCoherenceError("Committed image root is invalid.")
            asset_dir = _safe_path(settings.get("asset_dir", "assets"))
        else:
            asset_dir = "assets"
        path = f"{_safe_path(slug)}/{asset_dir}/{asset_ref}"
        if path in expected:
            raise SnapshotCoherenceError("Committed mirror targets collide.")
        expected[path] = (slug, obj_kind, ref, binding["revision"], binding["sha256"])
    file_dispositions = []
    excluded_paths = {proof["path"]: proof for proof in excluded.values()}
    for path in sorted(set(file_map) | set(expected)):
        observed = file_map.get(path)
        source = expected.get(path)
        state = ("excluded_legacy_page" if path in excluded_paths and observed is not None
                 else "file_only_draft" if source is None else "missing" if observed is None
                 else "matching" if observed[1] == source[-1] else "recoverable_draft_conflict")
        file_dispositions.append({"path": path, "state": state,
                                  "size": observed[0] if observed else None,
                                  "sha256": observed[1] if observed else None,
                                  "canonical_sha256": (excluded_paths[path]["sha256"]
                                                       if path in excluded_paths else
                                                       source[-1] if source else None)})
    if visible_campaigns is not None:
        blob_bindings = [item for item in blob_bindings if item["campaign_slug"] in visible_campaigns]
    canonical = {"generations": generation_proofs, "objects": objects,
                 "blobs": blob_bindings, "files": file_dispositions,
                 "operation_journals": operation_journals}
    result = {"version": 1, "schema_version": version, "mode": "committed",
            "activation": {"activated": bool(activation[0]["activated"]),
                           "coverage_version": activation[0]["coverage_version"]},
            "operation_journals": operation_journals,
            "objects": objects, "generation_count": len(generation_proofs),
            "generations_sha256": _json_sha(generation_proofs),
            "file_dispositions": file_dispositions,
            "blob_bindings": blob_bindings,
            "canonical_sha256": ""}
    if excluded:
        evidence = [{"campaign_slug": key[0], "object_ref": key[2], **proof}
                    for key, proof in sorted(excluded.items())]
        result["excluded_legacy_pages"] = evidence
        canonical["excluded_legacy_pages"] = evidence
    result["canonical_sha256"] = _json_sha(canonical)
    return result
