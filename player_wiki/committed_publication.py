"""Activated config/page authority. Files are recoverable mirrors, never inputs.

The marker is proved against the exact trusted migration schema. The private
operator transition lives in committed_activation, never in a web route.
"""
from __future__ import annotations

import hashlib
import errno
import json
import os
import sqlite3
import stat
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from functools import lru_cache, wraps
from contextvars import ContextVar

import yaml
from flask import has_app_context

from .db import get_db
from .campaign_content_service import CampaignContentError


_projection_payload = ContextVar("committed_page_projection", default=None)


class CommittedSourceConflict(CampaignContentError):
    """The affected object needs manager repair or a fresh edit."""


class CommittedHardDeleteBlocked(CommittedSourceConflict):
    def __init__(self, blockers):
        self.blockers = tuple(blockers)
        super().__init__("Hard delete blocked for this content page.")


_ACTIVATION_TABLE = "committed_source_activation"
_ACTIVATION_TRIGGER_NAMES = tuple(
    f"{_ACTIVATION_TABLE}_{suffix}"
    for suffix in ("no_insert_active", "no_update_active", "no_delete")
)


@lru_cache(maxsize=2)
def _expected_activation_schema(version: int):
    """Reflect the trusted DDL with the same SQLite engine as the target."""
    from .migrations import SCHEMA_V17_SQL, CURRENT_SCHEMA_SQL

    with closing(sqlite3.connect(":memory:")) as reference:
        reference.executescript(CURRENT_SCHEMA_SQL if version >= 18 else SCHEMA_V17_SQL)
        rows = reference.execute(
            "SELECT type, name, tbl_name, sql FROM main.sqlite_schema "
            "WHERE name = ? OR tbl_name = ? ORDER BY type, name",
            (_ACTIVATION_TABLE, _ACTIVATION_TABLE),
        ).fetchall()
    expected = tuple(tuple(row) for row in rows)
    if (len(expected) != 4 or
            {row[:3] for row in expected} != {
                ("table", _ACTIVATION_TABLE, _ACTIVATION_TABLE),
                *(("trigger", name, _ACTIVATION_TABLE) for name in _ACTIVATION_TRIGGER_NAMES),
            } or any(not isinstance(row[3], str) for row in expected)):
        raise CommittedSourceConflict("Trusted activation schema is unavailable; repair required.")
    return expected


def _activation_schema_matches(connection, *, version=17, absent=False):
    expected = _expected_activation_schema(version)
    names = tuple(row[1] for row in expected)
    placeholders = ", ".join("?" for _ in names)
    actual = connection.execute(
        "SELECT type, name, tbl_name, sql FROM main.sqlite_schema "
        f"WHERE name IN ({placeholders}) OR tbl_name = ? ORDER BY type, name",
        (*names, _ACTIVATION_TABLE),
    ).fetchall()
    observed = tuple(tuple(row) for row in actual)
    return not observed if absent else observed == expected


def active(connection=None) -> bool:
    if connection is None and not has_app_context():
        # Standalone helpers must not silently bypass an activated configured DB.
        from .config import Config
        path = Path(Config.DB_PATH)
        if not path.exists():
            return False
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as standalone:
                if active(standalone):
                    raise CommittedSourceConflict("Activated publication requires the configured application context.")
        except sqlite3.Error:
            raise CommittedSourceConflict("Committed source activation proof is unavailable; repair required.") from None
        return False
    connection = connection or get_db()
    from .migrations import MigrationError, inspect_migration_ledger

    # Hold the ledger and marker observations in one snapshot. An existing caller
    # transaction remains the caller's to commit or roll back.
    try:
        owned = not connection.in_transaction
        if owned:
            connection.execute("BEGIN")
        try:
            shadow_names = (_ACTIVATION_TABLE, "schema_migrations", *_ACTIVATION_TRIGGER_NAMES)
            placeholders = ", ".join("?" for _ in shadow_names)
            shadow = connection.execute(
                "SELECT 1 FROM sqlite_temp_schema "
                f"WHERE name IN ({placeholders}) OR tbl_name IN (?, ?) LIMIT 1",
                (*shadow_names, _ACTIVATION_TABLE, "schema_migrations"),
            ).fetchone()
            if shadow is not None:
                raise CommittedSourceConflict("Committed source activation proof is shadowed; repair required.")
            ledger = inspect_migration_ledger(connection)
            table = connection.execute(
                "SELECT 1 FROM main.sqlite_schema WHERE type='table' AND name='committed_source_activation'"
            ).fetchone()
            if not ledger.ledger_exists:
                # An empty, not-yet-migrated database is closed. A populated
                # database without its ledger has no trustworthy version proof.
                existing = connection.execute(
                    "SELECT 1 FROM main.sqlite_schema WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
                ).fetchone()
                if existing is not None:
                    raise CommittedSourceConflict("Committed source activation proof is unavailable; repair required.")
                return False
            if ledger.applied_version < 15:
                if table is not None or not _activation_schema_matches(connection, absent=True):
                    raise CommittedSourceConflict("Committed source activation proof is inconsistent; repair required.")
                return False
            if table is None:
                raise CommittedSourceConflict("Committed source activation proof is missing; repair required.")
            if not _activation_schema_matches(connection, version=ledger.applied_version):
                raise CommittedSourceConflict("Committed source activation proof is malformed; repair required.")

            columns = connection.execute("PRAGMA main.table_info(committed_source_activation)").fetchall()
            shape = [(row[1], row[2].upper(), row[3], row[4], row[5]) for row in columns]
            if shape != [
                ("singleton", "INTEGER", 0, None, 1),
                ("activated", "INTEGER", 1, "0", 0),
                ("activated_at", "TEXT", 0, None, 0),
                ("coverage_version", "INTEGER", 1, "0", 0),
                ("schema_version", "INTEGER", 1, "15", 0),
            ]:
                raise CommittedSourceConflict("Committed source activation proof is malformed; repair required.")
            rows = connection.execute(
                "SELECT singleton, activated, activated_at, coverage_version, schema_version "
                "FROM main.committed_source_activation"
            ).fetchall()
            if len(rows) != 1:
                raise CommittedSourceConflict("Committed source activation proof is malformed; repair required.")
            singleton, activated, activated_at, coverage, schema = rows[0]
            if (type(singleton) is not int or singleton != 1 or
                    type(activated) is not int or activated not in (0, 1) or
                    type(coverage) is not int or type(schema) is not int or
                    schema != (18 if ledger.applied_version >= 18 else 15)):
                raise CommittedSourceConflict("Committed source activation proof is malformed; repair required.")
            if activated == 0:
                if activated_at is not None or coverage != 0:
                    raise CommittedSourceConflict("Committed source activation proof is inconsistent; repair required.")
                return False
            if ledger.applied_version < 18 or coverage != 1 or not isinstance(activated_at, str):
                raise CommittedSourceConflict("Committed source activation proof is inconsistent; repair required.")
            try:
                timestamp = datetime.fromisoformat(activated_at)
            except ValueError:
                raise CommittedSourceConflict("Committed source activation proof is inconsistent; repair required.") from None
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise CommittedSourceConflict("Committed source activation proof is inconsistent; repair required.")
            return True
        finally:
            if owned:
                connection.rollback()
    except (sqlite3.Error, MigrationError):
        raise CommittedSourceConflict("Committed source activation proof is unavailable; repair required.") from None


def digest(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def read_snapshot(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        connection = kwargs.get("connection") or get_db()
        owned = not connection.in_transaction
        if owned:
            connection.execute("BEGIN")
        try:
            return function(*args, **kwargs)
        finally:
            if owned:
                connection.rollback()
    return wrapped


def current(campaign_slug, kind, ref="", *, connection=None, allow_tombstone=False):
    connection = connection or get_db()
    row = connection.execute(
        """SELECT g.* FROM committed_source_current c
        JOIN committed_source_generations g USING(campaign_slug, object_kind, object_ref, revision)
        JOIN committed_source_admission a USING(campaign_slug, object_kind, object_ref)
        WHERE c.campaign_slug=? AND c.object_kind=? AND c.object_ref=?
          AND a.status='admitted' AND a.revision=c.revision""", (campaign_slug, kind, ref)
    ).fetchone()
    if row is None:
        return None
    row = dict(row)
    if row["tombstone"]:
        return row if allow_tombstone else None
    if not isinstance(row["primary_bytes"], bytes) or len(row["primary_bytes"]) > 2*1024*1024 or digest(row["primary_bytes"]) != row["primary_sha256"]:
        raise CommittedSourceConflict("Committed source digest failed; manager repair required.")
    return row


def config(campaign_slug, *, connection=None):
    from .committed_source_store import _decode_mapping, _validate_config_payload
    row = current(campaign_slug, "config", connection=connection)
    if row is None:
        raise CommittedSourceConflict("Campaign settings need committed-source repair.")
    value = _decode_mapping(row["primary_bytes"])
    error, _ = _validate_config_payload(value, campaign_slug)
    if error:
        raise CommittedSourceConflict("Campaign settings proof is invalid; repair required.")
    return row, value


@read_snapshot
def page_row(campaign_slug, ref, *, connection=None):
    """Prove the full projection against the exact immutable generation."""
    from .campaign_page_refresh import build_page_payload
    from .repository import parse_frontmatter
    connection = connection or get_db()
    _, settings = config(campaign_slug, connection=connection)
    generation = current(campaign_slug, "page", ref, connection=connection)
    if generation is None:
        return None
    from .system_policy import normalize_system_code
    if normalize_system_code(generation["system_code"]) != normalize_system_code(settings["system"]):
        raise CommittedSourceConflict("Page and campaign system proof differ; manager repair required.")
    row = connection.execute("SELECT * FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",
                             (campaign_slug, ref)).fetchone()
    if row is None:
        raise CommittedSourceConflict("Committed page projection is missing; repair required.")
    metadata, body = parse_frontmatter(generation["primary_bytes"].decode("utf-8"))
    expected = build_page_payload(campaign_slug, ref, metadata=metadata, body_markdown=body,
                                  updated_at=row["updated_at"])
    if any(row[key] != value for key, value in expected.items()):
        raise CommittedSourceConflict("Committed page projection differs; repair required.")
    return row


@read_snapshot
def page_rows(campaign_slug):
    rows = get_db().execute("SELECT object_ref FROM committed_source_current WHERE campaign_slug=? AND object_kind='page'",
                            (campaign_slug,)).fetchall()
    result = []
    for row in rows:
        try:
            proved = page_row(campaign_slug, row[0])
        except (CommittedSourceConflict, ValueError, TypeError, UnicodeError, yaml.YAMLError, OverflowError, RecursionError):
            continue  # One unhealthy object cannot expose itself or suppress others.
        if proved is not None:
            result.append(proved)
    return result


def revision(campaign_slug, kind, ref=""):
    row = current(campaign_slug, kind, ref, allow_tombstone=True)
    return int(row["revision"]) if row else None


def _append(connection, campaign_slug, kind, ref, primary, *, expected, system, actor=None):
    from .committed_source_store import _now, _record_status
    prior = current(campaign_slug, kind, ref, connection=connection, allow_tombstone=True)
    actual = int(prior["revision"]) if prior else None
    # A blocked current pointer must not be mistaken for an unoccupied object.
    pointer = connection.execute("SELECT revision FROM committed_source_current WHERE campaign_slug=? AND object_kind=? AND object_ref=?",
                                 (campaign_slug, kind, ref)).fetchone()
    if pointer is not None and prior is None:
        raise CommittedSourceConflict("Source admission is blocked; manager repair required.")
    if actual != expected:
        raise CommittedSourceConflict("This source changed; reload before saving.")
    number = (actual or 0) + 1
    timestamp = _now()
    operation = uuid4().hex
    previous_digest = prior["primary_sha256"] if prior else None
    connection.execute("""INSERT INTO committed_source_generations
        (campaign_slug,object_kind,object_ref,revision,system_code,primary_bytes,primary_sha256,tombstone,actor_user_id,reason,committed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (campaign_slug,kind,ref,number,system,primary,digest(primary),
        int(primary is None),actor,"deletion" if primary is None else "publication",timestamp))
    connection.execute("""INSERT INTO committed_source_current VALUES (?,?,?,?)
        ON CONFLICT(campaign_slug,object_kind,object_ref) DO UPDATE SET revision=excluded.revision""",
        (campaign_slug,kind,ref,number))
    _record_status(connection,campaign_slug,kind,ref,"admitted","publication",number)
    connection.execute("""INSERT INTO committed_source_publications
        (operation_id,campaign_slug,object_kind,object_ref,state,expected_revision,expected_primary_sha256,
         desired_primary_bytes,desired_primary_sha256,committed_revision,actor_user_id,created_at,updated_at)
        VALUES (?,?,?,?,'committed',?,?,?,?,?,?,?,?)""",
        (operation,campaign_slug,kind,ref,expected,previous_digest,primary,digest(primary),number,actor,timestamp,timestamp))
    outstanding = connection.execute("""SELECT expected_primary_sha256 FROM committed_source_outbox
        WHERE campaign_slug=? AND object_kind=? AND object_ref=? AND state IN ('pending','retry')
        ORDER BY revision LIMIT 1""", (campaign_slug,kind,ref)).fetchone()
    mirror_basis = outstanding[0] if outstanding is not None else previous_digest
    connection.execute("""INSERT INTO committed_source_outbox
        (campaign_slug,object_kind,object_ref,revision,expected_primary_sha256,state,created_at,updated_at)
        VALUES (?,?,?,?,?,'pending',?,?)""", (campaign_slug,kind,ref,number,mirror_basis,timestamp,timestamp))
    return number


def _reserve(connection):
    from .committed_source_store import _legacy_enum_values_valid
    if connection.in_transaction:
        raise CommittedSourceConflict("Committed publication needs its own transaction.")
    # WAL NORMAL does not promise power-loss durability at acknowledgement.
    # Set this outside the transaction; SQLite FULL syncs the committed WAL.
    connection.execute("PRAGMA synchronous = FULL")
    if int(connection.execute("PRAGMA synchronous").fetchone()[0]) < 2:
        raise CommittedSourceConflict("Durable SQLite publication is unavailable.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        if not active(connection) or not _legacy_enum_values_valid(connection):
            raise CommittedSourceConflict("Committed publication proof is unavailable; repair required.")
    except BaseException:
        connection.rollback()
        raise


def publish_config(campaigns_dir, campaign_slug, updates):
    from .campaign_content_service import CampaignConfigRecord, _dump_yaml, _normalize_campaign_config_updates
    from .committed_source_store import _validate_config_payload
    if not isinstance(updates, dict):
        raise CommittedSourceConflict("Campaign config updates must be an object.")
    if any(key != "current_session" and not isinstance(value, str) for key, value in updates.items()):
        raise CommittedSourceConflict("Campaign text settings must be strings.")
    previous, value = config(campaign_slug)
    if "current_session" in updates and (isinstance(updates["current_session"], bool) or
            not isinstance(updates["current_session"], (int, str))):
        raise CommittedSourceConflict("current_session must be a nonnegative integer.")
    normalized = _normalize_campaign_config_updates(updates)
    for key in ("system", "systems_library", "source_wiki_root"):
        if key in normalized and normalized[key] != value.get(key, ""):
            raise CommittedSourceConflict("This settings change requires manager impact and compatibility review.")
    value = dict(value, **normalized)
    if _validate_config_payload(value,campaign_slug)[0]:
        raise CommittedSourceConflict("Campaign settings are invalid.")
    payload = (_dump_yaml(value)+"\n").encode("utf-8")
    if len(payload)>2*1024*1024:
        raise CommittedSourceConflict("Campaign settings are too large.")
    connection=get_db()
    _reserve(connection)
    try:
        locked = current(campaign_slug, "config", connection=connection)
        if locked is None or locked["revision"] != previous["revision"]:
            raise CommittedSourceConflict("Campaign settings changed; reload before saving.")
        _append(connection,campaign_slug,"config","",payload,expected=previous["revision"],system=value["system"])
        connection.commit()
    except BaseException:
        connection.rollback(); raise
    _attempt_replay(campaigns_dir, campaign_slug=campaign_slug)
    row,_ = config(campaign_slug)
    return CampaignConfigRecord(campaign_slug,Path(campaigns_dir)/campaign_slug/"campaign.yaml",value,row["committed_at"])


def publish_page(reconciler, campaign, prepared, *, operation_kind, prepared_image=None,
                 audit_event_type=None, audit_actor_user_id=None, audit_metadata=None,
                 expected_page_snapshot=None, guard_page_snapshot=False, delete_record=None,
                 force_delete=False):
    from .campaign_content_service import build_campaign_page_file_record, validated_campaign_asset_media_type
    from .managed_wiki_images import is_canonical_managed_wiki_image_ref
    from .player_wiki_reconciliation import capture_page_publication_snapshot, PlayerWikiCreateConflict, PlayerWikiStalePageConflict
    from .campaign_page_refresh import build_page_payload
    from .repository import parse_frontmatter
    connection = get_db()
    slug = campaign.slug
    ref = delete_record.page_ref if delete_record else prepared.page_ref
    from .campaign_page_refresh import normalize_page_ref
    if normalize_page_ref(ref) != ref:
        raise CommittedSourceConflict("Invalid canonical page reference.")
    config_generation, settings = config(slug)
    expected = prepared.committed_revision if prepared is not None else revision(slug,"page",ref)
    if prepared is not None and prepared.committed_config_revision != config_generation["revision"]:
        raise CommittedSourceConflict("Campaign settings changed during page preparation.")
    observed = capture_page_publication_snapshot(slug,ref)
    if observed is not None and page_row(slug,ref) is None:
        raise CommittedSourceConflict("Existing page needs committed-source repair.")
    if prepared is not None and prepared.expected_updated_at is not None and (
            observed is None or observed.updated_at != prepared.expected_updated_at):
        raise PlayerWikiStalePageConflict("This page changed; reload before saving.")
    if guard_page_snapshot and observed != expected_page_snapshot:
        raise PlayerWikiStalePageConflict("This page changed; reload before saving.")
    if delete_record and (observed is None or observed.updated_at != delete_record.updated_at):
        raise PlayerWikiStalePageConflict("This page changed; reload before deleting.")
    payload = None
    image = None
    if prepared is not None:
        if prepared.campaign_slug != slug or len(prepared.rendered_markdown)>2*1024*1024:
            raise CommittedSourceConflict("Invalid page publication input.")
        metadata,body = parse_frontmatter(prepared.rendered_markdown.decode("utf-8"))
        from .rich_text import sanitize_rich_markdown
        from .input_limits import validate_markdown_value
        validate_markdown_value(body)
        if sanitize_rich_markdown(body.strip()) != body.strip():
            raise CommittedSourceConflict("Page content must be sanitized before publication.")
        payload = build_page_payload(slug,ref,metadata=metadata,body_markdown=body,updated_at="")
        image_ref=payload["image_path"]
        if is_canonical_managed_wiki_image_ref(image_ref):
            if prepared_image is not None:
                if prepared_image.asset_ref != image_ref:
                    raise CommittedSourceConflict("Managed image does not match the page.")
                image=prepared_image.data_blob
            else:
                prior=current(slug,"page",ref)
                if prior:
                    row=connection.execute("SELECT image_bytes,sha256 FROM committed_page_images WHERE campaign_slug=? AND page_ref=? AND revision=? AND asset_ref=?",
                        (slug,ref,prior["revision"],image_ref)).fetchone()
                    if row and digest(row[0])==row[1]: image=row[0]
            if image is None:
                raise CommittedSourceConflict("Managed image lacks committed proof; manager repair required.")
            if not validated_campaign_asset_media_type(Path(image_ref), data_blob=image):
                raise CommittedSourceConflict("Managed image bytes are invalid.")
        elif prepared_image is not None or str(image_ref).startswith("wiki-managed"):
            raise CommittedSourceConflict("Managed image reference is invalid.")
    if operation_kind not in {"create", "update", "unpublish", "api_upsert", "browser_delete", "api_delete"}:
        raise CommittedSourceConflict("Invalid committed publication operation.")
    if delete_record and operation_kind not in {"browser_delete", "api_delete"}:
        raise CommittedSourceConflict("Invalid committed deletion operation.")
    if operation_kind == "browser_delete" and audit_event_type is None:
        raise CommittedSourceConflict("Browser deletion requires audit metadata.")
    audit = reconciler._prepare_audit(audit_event_type,audit_actor_user_id,audit_metadata)
    _reserve(connection)
    try:
        from .legacy_page_exclusion import has_exclusion_claim
        if has_exclusion_claim(connection, slug, ref):
            raise CommittedSourceConflict("The excluded legacy page cannot be changed.")
        locked=current(slug,"config",connection=connection)
        if locked is None or locked["revision"]!=config_generation["revision"] or capture_page_publication_snapshot(slug,ref)!=observed:
            raise PlayerWikiStalePageConflict("Publication inputs changed; reload before saving.")
        pointer = connection.execute(
            "SELECT revision FROM committed_source_current WHERE campaign_slug=? AND object_kind='page' AND object_ref=?",
            (slug, ref),
        ).fetchone()
        existing = current(slug, "page", ref, connection=connection, allow_tombstone=True)
        projection = connection.execute(
            "SELECT 1 FROM campaign_pages WHERE campaign_slug=? AND page_ref=?", (slug, ref)
        ).fetchone()
        if pointer is not None and existing is None:
            raise CommittedSourceConflict("Page admission is blocked; manager repair required.")
        if existing is not None and not existing["tombstone"]:
            page_row(slug, ref, connection=connection)
        elif projection is not None:
            raise CommittedSourceConflict("Page projection lacks current proof; manager repair required.")
        if delete_record is not None and not force_delete:
            try:
                blockers = _locked_hard_delete_blockers(reconciler.page_store, slug, ref)
            except CommittedHardDeleteBlocked:
                raise
            except (CommittedSourceConflict, ValueError, TypeError, UnicodeError, yaml.YAMLError) as exc:
                raise CommittedHardDeleteBlocked(("Reference proof is unavailable.",)) from exc
            if blockers:
                raise CommittedHardDeleteBlocked(blockers)
        if operation_kind=="create" and observed is not None:
            raise PlayerWikiCreateConflict("This page is already occupied.")
        if payload is not None:
            occupied=connection.execute("SELECT 1 FROM campaign_pages WHERE campaign_slug=? AND route_slug=? AND page_ref<>?",
                (slug,payload["route_slug"],ref)).fetchone()
            if occupied: raise PlayerWikiCreateConflict("That wiki page slug is already in use.")
            source=payload["source_ref"]
            if source.startswith("session-article:"):
                duplicate=connection.execute("SELECT 1 FROM campaign_pages WHERE campaign_slug=? AND source_ref=? AND page_ref<>?",(slug,source,ref)).fetchone()
                if duplicate: raise PlayerWikiCreateConflict("This session article already has a wiki page.")
        number=_append(connection,slug,"page",ref,prepared.rendered_markdown if prepared else None,
                       expected=expected,system=settings["system"],actor=audit_actor_user_id)
        if payload is None:
            reconciler.page_store._advance_page_revision(slug,delete_record.updated_at)
            connection.execute("DELETE FROM campaign_pages WHERE campaign_slug=? AND page_ref=?",(slug,ref))
        else:
            projection_token = _projection_payload.set((slug, tuple(sorted(payload.items()))))
            try:
                reconciler.page_store._persist_page_payload(slug,payload)
            finally:
                _projection_payload.reset(projection_token)
            if image is not None:
                mismatch = connection.execute("SELECT 1 FROM committed_page_images WHERE campaign_slug=? AND asset_ref=? AND sha256<>? LIMIT 1",
                                              (slug,payload["image_path"],digest(image))).fetchone()
                if mismatch:
                    raise CommittedSourceConflict("Managed image identity already belongs to different bytes.")
                connection.execute("INSERT INTO committed_page_images(campaign_slug,page_ref,revision,asset_ref,sha256,image_bytes) VALUES (?,?,?,?,?,?)",
                                   (slug,ref,number,payload["image_path"],digest(image),image))
        if audit[0]:
            reconciler.auth_store.insert_audit_event(event_type=audit[0],actor_user_id=audit[1],campaign_slug=slug,
                metadata=json.loads(audit[2]),commit=False)
        committed_row = connection.execute("SELECT * FROM campaign_pages WHERE campaign_slug=? AND page_ref=?", (slug,ref)).fetchone()
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    _attempt_replay(reconciler.repository_store.campaigns_dir,campaign_slug=slug)
    if delete_record:
        return delete_record
    # Return the acknowledged generation even if another writer immediately
    # updates or deletes it. Repository reads rebuild from canonical pointers.
    record=reconciler.page_store._map_record(committed_row,include_body=True)
    return build_campaign_page_file_record(campaign,record)


def _locked_hard_delete_blockers(page_store, campaign_slug, page_ref):
    """Read only admitted, current references under the caller's writer reservation."""
    from types import SimpleNamespace
    from .campaign_wiki_safety import build_dm_player_wiki_removal_safety_index
    from .committed_source_store import _decode_mapping
    connection = get_db()
    if not connection.in_transaction:
        raise CommittedSourceConflict("Deletion safety requires a writer reservation.")
    for kind in ("page", "character"):
        if connection.execute(
            "SELECT 1 FROM committed_source_admission WHERE campaign_slug=? AND object_kind=? AND status<>'admitted' LIMIT 1",
            (campaign_slug, kind),
        ).fetchone():
            raise CommittedHardDeleteBlocked((f"{kind.title()} reference proof is unavailable.",))
        if connection.execute(
            """SELECT 1 FROM committed_source_admission a LEFT JOIN committed_source_current c
               ON c.campaign_slug=a.campaign_slug AND c.object_kind=a.object_kind AND c.object_ref=a.object_ref
               WHERE a.campaign_slug=? AND a.object_kind=? AND a.status='admitted'
                 AND (c.revision IS NULL OR c.revision<>a.revision) LIMIT 1""",
            (campaign_slug, kind),
        ).fetchone():
            raise CommittedHardDeleteBlocked((f"{kind.title()} reference proof is unavailable.",))
    records = []
    page_pointers = connection.execute(
        "SELECT object_ref FROM committed_source_current WHERE campaign_slug=? AND object_kind='page'",
        (campaign_slug,),
    ).fetchall()
    for pointer in page_pointers:
        source = current(campaign_slug, "page", pointer[0], connection=connection, allow_tombstone=True)
        if source is None:
            raise CommittedHardDeleteBlocked(("Page reference proof is unavailable.",))
        if source["tombstone"]:
            continue
        row = page_row(campaign_slug, pointer[0], connection=connection)
        if row is None:
            raise CommittedHardDeleteBlocked(("Page reference proof is unavailable.",))
        records.append(page_store._map_record(row, include_body=True))
    article_rows = connection.execute(
        "SELECT id,title,status,source_page_ref FROM campaign_session_articles WHERE campaign_slug=?",
        (campaign_slug,),
    ).fetchall()
    if any(not isinstance(row["source_page_ref"], str) or not isinstance(row["status"], str)
           or not isinstance(row["title"], str) for row in article_rows):
        raise CommittedHardDeleteBlocked(("Session reference proof is unavailable.",))
    articles = [SimpleNamespace(**dict(row)) for row in article_rows]
    characters = []
    character_pointers = connection.execute(
        "SELECT object_ref FROM committed_source_current WHERE campaign_slug=? AND object_kind='character'",
        (campaign_slug,),
    ).fetchall()
    for pointer in character_pointers:
        source = current(campaign_slug, "character", pointer[0], connection=connection, allow_tombstone=True)
        if source is None:
            raise CommittedHardDeleteBlocked(("Character reference proof is unavailable.",))
        if source["tombstone"]:
            continue
        if (not isinstance(source["secondary_bytes"], bytes) or
                digest(source["secondary_bytes"]) != source["secondary_sha256"]):
            raise CommittedHardDeleteBlocked(("Character reference proof is unavailable.",))
        definition = _decode_mapping(source["primary_bytes"])
        if (definition is None or definition.get("campaign_slug") != campaign_slug or
                definition.get("character_slug") != pointer[0]):
            raise CommittedHardDeleteBlocked(("Character reference proof is unavailable.",))
        characters.append(SimpleNamespace(definition=SimpleNamespace(
            name=definition.get("name", ""), character_slug=pointer[0],
            to_dict=lambda value=definition: value,
        )))
    safety = build_dm_player_wiki_removal_safety_index(
        campaign_slug, None, records, session_articles=articles, character_records=characters,
    ).get(page_ref)
    if safety is None:
        raise CommittedHardDeleteBlocked(("Page reference proof is unavailable.",))
    return tuple(safety["hard_delete_blockers"])


def _attempt_replay(campaigns_dir, *, campaign_slug):
    # The committed generation is the success boundary. A postcommit mirror
    # failure remains retryable in the outbox, without returning a false failure.
    import sqlite3
    try:
        replay_mirrors(campaigns_dir, campaign_slug=campaign_slug)
    except (OSError, sqlite3.Error, CommittedSourceConflict):
        pass


def replay_mirrors(campaigns_dir, *, campaign_slug=None, limit=64, retry_conflicts=False):
    """Replay only committed generations. A changed disk file remains a draft.

    Serialize replay with publishers through SQLite so an older outbox item
    cannot overwrite a later generation. The filesystem compare also preserves
    an already-observed external draft; file edits never change source authority.
    """
    from .committed_source_store import _now
    from .file_publication import atomic_move_file, atomic_write_bytes_no_replace
    connection=get_db()
    if not active(connection):
        raise CommittedSourceConflict("Committed mirror replay requires activated authority.")
    if connection.in_transaction:
        raise CommittedSourceConflict("Mirror replay needs its own transaction.")
    limit=max(1,min(int(limit),64))
    rows=connection.execute("""SELECT id,state FROM committed_source_outbox
        WHERE (state IN ('pending','retry') OR (? AND state='conflict' AND object_kind='page'))
          AND (? IS NULL OR campaign_slug=?)
        ORDER BY CASE WHEN state='conflict' THEN 1 ELSE 0 END,id LIMIT ?""",
                            (int(bool(retry_conflicts)),campaign_slug,campaign_slug,limit)).fetchall()
    counts={"recovered":0,"conflict":0,"pending":0,"aborted":0}
    if retry_conflicts:
        counts["_conflict_retry_selected"] = sum(item["state"] == "conflict" for item in rows)
    for item in rows:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row=connection.execute("SELECT * FROM committed_source_outbox WHERE id=?",(item[0],)).fetchone()
            if row["state"] not in {"pending","retry"} and not (retry_conflicts and row["state"] == "conflict" and row["object_kind"] == "page"):
                connection.rollback(); continue
            slug,kind,ref=row["campaign_slug"],row["object_kind"],row["object_ref"]
            if kind not in {"config","page","character"}:
                connection.rollback(); continue
            if kind == "character":
                from .committed_character_publication import exact_character
                latest=exact_character(slug,ref,connection=connection,allow_tombstone=True)
            else:
                latest=current(slug,kind,ref,connection=connection,allow_tombstone=True)
            if latest is None:
                raise CommittedSourceConflict("Mirror source needs repair.")
            if latest["revision"]!=row["revision"]:
                connection.execute("UPDATE committed_source_outbox SET state='complete',error_code='superseded' WHERE id=?",(row["id"],))
                connection.commit(); continue
            _,settings=config(slug,connection=connection)
            if kind == "character":
                from .committed_character_publication import replay_character_mirror
                try:
                    state=replay_character_mirror(connection,campaigns_dir,row,latest,settings)
                    counts["recovered" if state=="complete" else "conflict"]+=1
                    connection.commit()
                except OSError:
                    connection.execute("UPDATE committed_source_outbox SET state='retry',attempt_count=attempt_count+1,error_code='mirror_io',updated_at=? WHERE id=?",(_now(),row["id"]))
                    connection.commit(); counts["pending"]+=1
                continue
            root=Path(campaigns_dir)/slug
            path=root/"campaign.yaml" if kind=="config" else root/settings.get("player_content_dir","content")/(ref+".md")
            desired=latest["primary_bytes"]
            try:
                # Move the old inode into deterministic retained custody before
                # comparing it. A later editor-created file wins the no-replace
                # publication and is never overwritten. A crash retains the old
                # inode and replay resumes using the same outbox identity.
                path = _safe_mirror_path(path, create_parents=True)
                retained = path.with_name(path.name + f".committed-{row['id']}.draft")
                actual=_mirror_bytes(path)
                state="complete"
                if digest(actual) != digest(desired):
                    if path.exists() and not retained.exists():
                        if digest(actual) != row["expected_primary_sha256"]:
                            state="conflict"
                        else:
                            atomic_move_file(path, retained)
                    captured = _mirror_bytes(retained) if retained.exists() else actual
                    if state != "conflict" and digest(captured) != row["expected_primary_sha256"]:
                        state="conflict"
                    if state == "conflict":
                        if not path.exists() and captured is not None:
                            atomic_write_bytes_no_replace(path, captured)
                        actual = _mirror_bytes(path) if path.exists() else captured
                    elif desired is not None:
                        path.parent.mkdir(parents=True,exist_ok=True)
                        try:
                            atomic_write_bytes_no_replace(path,desired)
                        except FileExistsError:
                            actual=_mirror_bytes(path)
                            if digest(actual)!=digest(desired): state="conflict"
                    elif path.exists():
                        actual=_mirror_bytes(path)
                        state="conflict"
                if kind == "page" and desired is not None:
                    from .managed_wiki_images import managed_wiki_image_path
                    image_conflict = False
                    for image in connection.execute("SELECT asset_ref,image_bytes,sha256 FROM committed_page_images WHERE campaign_slug=? AND page_ref=? AND revision=?",
                                                     (slug,ref,row["revision"])).fetchall():
                        if not _valid_committed_image(image):
                            raise CommittedSourceConflict("Committed image proof failed; manager repair required.")
                        asset_root=root/settings.get("asset_dir","assets")
                        reason=_image_mirror_reason(asset_root,image["asset_ref"],image["sha256"])
                        if reason == "missing":
                            try:
                                image_path=managed_wiki_image_path(asset_root,image["asset_ref"])
                                _safe_mirror_path(image_path,create_parents=True)
                                managed_wiki_image_path(asset_root,image["asset_ref"])
                                atomic_write_bytes_no_replace(image_path,image["image_bytes"])
                            except FileExistsError:
                                pass  # Compare the competing file below.
                            except (CampaignContentError, CommittedSourceConflict):
                                image_conflict = True
                            except OSError as exc:
                                try:
                                    managed_wiki_image_path(asset_root,image["asset_ref"])
                                except CampaignContentError:
                                    image_conflict = True
                                else:
                                    if exc.errno in {errno.ELOOP, errno.EISDIR, errno.ENOTDIR}:
                                        image_conflict = True
                                    else:
                                        raise
                            reason=_image_mirror_reason(asset_root,image["asset_ref"],image["sha256"])
                        image_conflict |= reason is not None
                    if image_conflict:
                        state="conflict"
                connection.execute("""INSERT INTO committed_source_mirrors
                    (campaign_slug,object_kind,object_ref,expected_primary_sha256,mirrored_revision,state,draft_primary_bytes,observed_primary_sha256,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(campaign_slug,object_kind,object_ref) DO UPDATE SET
                    expected_primary_sha256=excluded.expected_primary_sha256,mirrored_revision=excluded.mirrored_revision,state=excluded.state,
                    draft_primary_bytes=excluded.draft_primary_bytes,observed_primary_sha256=excluded.observed_primary_sha256,updated_at=excluded.updated_at""",
                    (slug,kind,ref,digest(desired),row["revision"],"matching" if state=="complete" else "conflict",
                     actual if state=="conflict" and digest(actual)!=digest(desired) else None,digest(actual),_now()))
                connection.execute("UPDATE committed_source_outbox SET state=?,attempt_count=attempt_count+1,error_code=NULL,updated_at=? WHERE id=?",(state,_now(),row["id"]))
                counts["recovered" if state=="complete" else "conflict"]+=1
                connection.commit()
            except OSError:
                connection.execute("UPDATE committed_source_outbox SET state='retry',attempt_count=attempt_count+1,error_code='mirror_io',updated_at=? WHERE id=?",(_now(),row["id"]))
                connection.commit(); counts["pending"]+=1
        except BaseException:
            connection.rollback(); raise
    return counts


@read_snapshot
def image_bytes(campaign_slug, asset_ref, *, manager=False):
    _,settings=config(campaign_slug)
    from .models import is_deprecated_wiki_identity
    for page in page_rows(campaign_slug):
        if page["image_path"] != asset_ref:
            continue
        if not manager and (not page["published"] or page["reveal_after_session"]>int(settings["current_session"])
                            or is_deprecated_wiki_identity(page["section"],page["page_type"])):
            continue
        source=current(campaign_slug,"page",page["page_ref"])
        if _image_repair_reason(campaign_slug, page, source) is None:
            row=get_db().execute("SELECT image_bytes FROM committed_page_images WHERE campaign_slug=? AND page_ref=? AND revision=? AND asset_ref=?",
                                 (campaign_slug,page["page_ref"],source["revision"],asset_ref)).fetchone()
            return row[0]
    return None


@read_snapshot
def page_image_payload(campaign_slug, page_ref, page_revision, config_revision, asset_ref):
    """Return only the selected page generation's proved managed image."""
    from .campaign_content_service import validated_campaign_asset_media_type
    from .input_limits import MAX_INGRESS_FILE_BYTES
    from .managed_wiki_images import is_canonical_managed_wiki_image_ref
    from .models import is_deprecated_wiki_identity

    if not is_canonical_managed_wiki_image_ref(asset_ref):
        raise CommittedSourceConflict("Managed image reference is invalid; manager repair required.")
    settings_source, settings = config(campaign_slug)
    source = current(campaign_slug, "page", page_ref)
    page = page_row(campaign_slug, page_ref)
    if (source is None or page is None or source["revision"] != page_revision
            or settings_source["revision"] != config_revision
            or page["image_path"] != asset_ref or not page["published"]
            or page["reveal_after_session"] > int(settings["current_session"])
            or is_deprecated_wiki_identity(page["section"], page["page_type"])):
        raise CommittedSourceConflict("Selected wiki page or image changed; refresh and retry.")
    row = get_db().execute(
        """SELECT image_bytes,sha256 FROM committed_page_images
           WHERE campaign_slug=? AND page_ref=? AND revision=? AND asset_ref=?""",
        (campaign_slug, page_ref, page_revision, asset_ref),
    ).fetchone()
    if (row is None or not isinstance(row["image_bytes"], bytes)
            or len(row["image_bytes"]) == 0 or len(row["image_bytes"]) > MAX_INGRESS_FILE_BYTES
            or not isinstance(row["sha256"], str)
            or digest(row["image_bytes"]) != row["sha256"]):
        raise CommittedSourceConflict("Committed page image proof failed; manager repair required.")
    media_type = validated_campaign_asset_media_type(Path(asset_ref), data_blob=row["image_bytes"])
    if media_type is None:
        raise CommittedSourceConflict("Committed page image bytes are invalid; manager repair required.")
    return bytes(row["image_bytes"]), media_type


def _image_repair_reason(campaign_slug, page, source):
    from .campaign_content_service import validated_campaign_asset_media_type
    from .managed_wiki_images import is_canonical_managed_wiki_image_ref
    asset_ref = str(page["image_path"] or "")
    if not asset_ref:
        return None
    if not is_canonical_managed_wiki_image_ref(asset_ref):
        return "managed_image_ref_invalid" if asset_ref.startswith("wiki-managed") else None
    row = get_db().execute(
        "SELECT asset_ref,sha256,image_bytes FROM committed_page_images WHERE campaign_slug=? AND page_ref=? AND revision=? AND asset_ref=?",
        (campaign_slug, page["page_ref"], source["revision"], asset_ref),
    ).fetchone()
    if row is None:
        other = get_db().execute(
            "SELECT 1 FROM committed_page_images WHERE campaign_slug=? AND page_ref=? AND revision=? LIMIT 1",
            (campaign_slug, page["page_ref"], source["revision"]),
        ).fetchone()
        return "managed_image_ref_mismatch" if other else "managed_image_proof_missing"
    if digest(row["image_bytes"]) != row["sha256"]:
        return "managed_image_digest_invalid"
    if not validated_campaign_asset_media_type(Path(asset_ref), data_blob=row["image_bytes"]):
        return "managed_image_bytes_invalid"
    return None


def _valid_committed_image(image):
    from .input_limits import MAX_INGRESS_FILE_BYTES
    value = image["image_bytes"]
    return (isinstance(value, bytes) and 0 < len(value) <= MAX_INGRESS_FILE_BYTES
            and isinstance(image["sha256"], str) and digest(value) == image["sha256"])


def _image_mirror_reason(asset_root, asset_ref, expected_sha256):
    """Classify one current managed file without returning its path or bytes."""
    from .input_limits import MAX_INGRESS_FILE_BYTES
    from .managed_wiki_images import managed_wiki_image_path

    try:
        path = _safe_mirror_path(managed_wiki_image_path(asset_root, asset_ref))
    except (CommittedSourceConflict, CampaignContentError, ValueError, RuntimeError):
        return "unsafe"
    try:
        flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                 getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        try:
            managed_wiki_image_path(asset_root, asset_ref)
        except CampaignContentError:
            return "unsafe"
        return "missing"
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EISDIR, errno.ENOTDIR}:
            return "unsafe"
        raise
    try:
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or
                int(getattr(before, "st_file_attributes", 0)) & 0x400 or
                before.st_size > MAX_INGRESS_FILE_BYTES):
            return "unsafe"
        observed = stream.read(MAX_INGRESS_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
    try:
        managed_wiki_image_path(asset_root, asset_ref)
        path = _safe_mirror_path(path)
        named = path.lstat()
        managed_wiki_image_path(asset_root, asset_ref)
    except FileNotFoundError:
        try:
            managed_wiki_image_path(asset_root, asset_ref)
        except CampaignContentError:
            return "unsafe"
        return "unsafe"
    except (CommittedSourceConflict, CampaignContentError):
        return "unsafe"
    if (len(observed) > MAX_INGRESS_FILE_BYTES or
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
            (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)):
        return "unsafe"
    return None if digest(observed) == expected_sha256 else "different"


def _current_page_image_mirror_reason(campaign_slug, ref, source, asset_root):
    if source is None or source["tombstone"]:
        return None
    images = get_db().execute(
        "SELECT asset_ref,image_bytes,sha256 FROM committed_page_images "
        "WHERE campaign_slug=? AND page_ref=? AND revision=? ORDER BY asset_ref",
        (campaign_slug, ref, source["revision"]),
    ).fetchall()
    for image in images:
        if not _valid_committed_image(image):
            return "managed_image_proof_invalid"
        reason = _image_mirror_reason(asset_root, image["asset_ref"], image["sha256"])
        if reason is not None:
            return "managed_image_mirror_" + reason
    return None


def inspect_page_mirrors(campaign_slug, content_dir, asset_root):
    """Return mismatched refs for manager diagnostics without importing drafts."""
    from .campaign_page_refresh import normalize_page_ref
    refs = {row[0] for row in get_db().execute(
        "SELECT object_ref FROM committed_source_current WHERE campaign_slug=? AND object_kind='page'", (campaign_slug,)).fetchall()}
    root = Path(content_dir)
    conflicts = []
    try:
        if root.is_dir():
            refs.update(normalize_page_ref(path.relative_to(root).as_posix()) for path in root.rglob("*.md"))
    except (OSError, ValueError):
        conflicts.append("content_root_unavailable")
    for ref in sorted(refs):
        try:
            source = current(campaign_slug, "page", ref, allow_tombstone=True)
            expected = source["primary_sha256"] if source else None
            path = root / (ref + ".md")
            observed = digest(_mirror_bytes(path))
            if expected != observed:
                conflicts.append(ref)
            elif source is not None and _current_page_image_mirror_reason(campaign_slug, ref, source, asset_root):
                conflicts.append(ref)
        except (OSError, ValueError, CommittedSourceConflict):
            conflicts.append(ref)
    return tuple(conflicts)


def _safe_mirror_path(path, *, create_parents=False):
    import stat
    path = Path(path).absolute()
    for parent in reversed(path.parents):
        try:
            details = parent.lstat()
        except FileNotFoundError:
            if not create_parents:
                continue
            parent.mkdir()
            details = parent.lstat()
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode) or int(getattr(details, "st_file_attributes", 0)) & 0x400:
            raise CommittedSourceConflict("Mirror path is unsafe; manager repair required.")
    try:
        details = path.lstat()
    except FileNotFoundError:
        return path
    if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode) or int(getattr(details, "st_file_attributes", 0)) & 0x400:
        raise CommittedSourceConflict("Mirror file is unsafe; manager repair required.")
    return path


def _mirror_bytes(path):
    path = _safe_mirror_path(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(2*1024*1024 + 1)
    except FileNotFoundError:
        return None
    if len(data) > 2*1024*1024:
        raise CommittedSourceConflict("Mirror draft exceeds the retained payload bound; file preserved.")
    return data


@read_snapshot
def page_repairs(campaign_slug, asset_root):
    """Manager-only non-payload inventory, including unadmitted legacy rows."""
    refs = {row[0] for row in get_db().execute("SELECT page_ref FROM campaign_pages WHERE campaign_slug=?", (campaign_slug,)).fetchall()}
    refs.update(row[0] for row in get_db().execute("SELECT object_ref FROM committed_source_admission WHERE campaign_slug=? AND object_kind='page'", (campaign_slug,)).fetchall())
    result=[]
    for ref in sorted(refs):
        reason = "committed_source_repair_required"
        try:
            row=page_row(campaign_slug,ref)
            source=current(campaign_slug,"page",ref,allow_tombstone=True)
            if row is not None and source is not None:
                reason = _image_repair_reason(campaign_slug, row, source)
                if reason is None:
                    reason = _current_page_image_mirror_reason(campaign_slug, ref, source, asset_root)
                if reason is None:
                    outbox = get_db().execute(
                        "SELECT state FROM committed_source_outbox WHERE campaign_slug=? "
                        "AND object_kind='page' AND object_ref=? AND revision=? ORDER BY id DESC LIMIT 1",
                        (campaign_slug, ref, source["revision"]),
                    ).fetchone()
                    if outbox is not None and outbox["state"] in {"conflict", "retry"}:
                        reason = "mirror_" + outbox["state"]
                if reason is None:
                    continue
            elif source is not None and source["tombstone"]:
                continue
        except OSError:
            reason = "managed_image_mirror_unavailable"
        except (CommittedSourceConflict, ValueError, TypeError, UnicodeError, yaml.YAMLError, OverflowError, RecursionError):
            pass
        result.append({"page_ref":ref,"reason":reason})
    return result
