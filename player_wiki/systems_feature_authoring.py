"""Finite registered feature authoring on the existing custom-entry surface.

This module never creates/enables a library/source/policy or adopts a Character.
The selected create has one owner for entry, override and its required audit.
Ordinary feature edits reuse their transport authorization and retain the
server-owned metadata under an owned snapshot; their outer audit stays separate.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from flask import has_request_context
import markdown

from .campaign_visibility import (
    build_default_campaign_visibility_by_scope, is_valid_visibility,
    most_private_visibility,
)
from .db import get_db
from .rich_text import sanitize_rich_html, sanitize_rich_markdown
from .system_policy import DND_5E_SYSTEM_CODE, default_systems_library_slug, normalize_system_code
from .systems_mutations import systems_transaction
from .systems_service import SystemsPolicyValidationError, _systems_service_cache_clear


REGISTERED_AVATAR_GRANT = "divine_avatar_forms@1/avatar_of_mourning@1"
_BODY_FIELDS = frozenset({"custom_campaign_slug", "provenance", "search_metadata",
                         "body_format", "body_markdown", "updated_by_user_id"})
_CREATE_FIELDS = frozenset({"registered_feature_grant", "title", "entry_type",
                           "slug_leaf", "provenance", "visibility",
                           "search_metadata", "body_markdown"})


def _fail(message):
    raise SystemsPolicyValidationError(message)


def registered_feature_effects(selection):
    """Strict authoring selection, never the legacy effect normalizer."""
    from .character_feature_composition import REGISTERED_WILD_GRANT, wild_replacement_effect
    if type(selection) is str and selection == REGISTERED_WILD_GRANT:
        return [wild_replacement_effect()]
    if type(selection) is not str or selection != REGISTERED_AVATAR_GRANT:
        _fail("Choose an exact supported registered feature grant.")
    from .divine_avatar_forms import (
        DIVINE_AVATAR_FORM_GRANT_KIND, DIVINE_AVATAR_MECHANIC_KEY,
        DIVINE_AVATAR_MECHANIC_VERSION, AVATAR_OF_MOURNING_FORM_KEY,
        AVATAR_OF_MOURNING_FORM_VERSION,
    )
    if (type(DIVINE_AVATAR_MECHANIC_VERSION) is not int or DIVINE_AVATAR_MECHANIC_VERSION != 1
            or type(AVATAR_OF_MOURNING_FORM_VERSION) is not int
            or AVATAR_OF_MOURNING_FORM_VERSION != 1):
        _fail("The selected registered feature version is not available.")
    return [{"kind": DIVINE_AVATAR_FORM_GRANT_KIND,
             "mechanic_key": DIVINE_AVATAR_MECHANIC_KEY,
             "mechanic_version": DIVINE_AVATAR_MECHANIC_VERSION,
             "form_key": AVATAR_OF_MOURNING_FORM_KEY,
             "form_version": AVATAR_OF_MOURNING_FORM_VERSION}]


@dataclass
class _FeatureWrite:
    service: object
    connection: object
    campaign_slug: str
    library: object
    source_id: str
    entry_key: str
    slug: str
    previous: object
    effects: object
    retain_visibility: bool = False
    previous_override: object = None
    active: bool = True


@contextmanager
def _feature_write(service, campaign_slug, library, source_id, entry_key, slug,
                   previous=None, effects=None, *, retain_visibility=False,
                   previous_override=None):
    connection = get_db()
    if not connection.in_transaction:
        raise RuntimeError("Feature save requires its owned transaction.")
    context = _FeatureWrite(service, connection, campaign_slug, library, source_id,
                            entry_key, slug, previous, deepcopy(effects),
                            retain_visibility, previous_override)
    try:
        yield context
    finally:
        context.active = False


def feature_write_library(context, service, campaign_slug, source, entry_key, slug):
    if (type(context) is not _FeatureWrite or not context.active
            or context.service is not service or context.connection is not get_db()
            or not context.connection.in_transaction
            or context.campaign_slug != campaign_slug
            or context.library.library_slug != source.library_slug
            or context.source_id != source.source_id
            or context.entry_key != entry_key or context.slug != slug):
        raise RuntimeError("Feature save context is no longer current or owned.")
    return context.library


def structured_feature_metadata(metadata):
    # Unknown server fields survive prose edits and cannot be silently grafted
    # onto another entry type. This does not classify them as positive mechanics.
    return type(metadata) is dict and bool(set(metadata) - _BODY_FIELDS)


def save_custom_feature_edit(service, campaign_slug, entry_slug, *, expected_entry=None, **values):
    """Same existing service/transport permissions; entry+override share ownership.

    The caller's ordinary custom-entry audit remains an independent operation.
    No new mechanics are accepted here, including through a body-only request.
    """
    if re.sub(r"[^a-z0-9_]+", "", str(values.get("entry_type") or "").strip().lower()) != "feature":
        _fail("The owned feature editor does not prepare another entry type.")
    with systems_transaction():
        library_slug = service.get_campaign_library_slug(campaign_slug)
        library = service.store.get_library(library_slug)
        previous = service.store.get_entry_by_slug(library_slug, entry_slug)
        if (library is None or previous is None or previous.entry_type != "feature"
                or previous.library_slug != library_slug):
            _fail("That custom feature changed; reload before editing.")
        identity_fields = ("id", "library_slug", "source_id", "entry_key", "entry_type", "slug")
        if (expected_entry is None
                or any(getattr(previous, field) != getattr(expected_entry, field)
                       for field in identity_fields)):
            _fail("That custom feature identity changed before the owned edit.")
        source = service.store.get_source(library_slug, previous.source_id)
        owner = dict(previous.metadata or {}).get("custom_campaign_slug", "")
        if (source is None or source.license_class != "custom_campaign"
                or owner not in ("", campaign_slug)):
            _fail("Choose a feature owned by this campaign.")
        override = service.store.get_campaign_entry_override(campaign_slug, previous.entry_key)
        if override is not None and override.library_slug != library_slug:
            _fail("That feature override belongs to another Systems library.")
        retain_visibility = not str(values.get("visibility") or "").strip()
        if retain_visibility:
            values["visibility"] = ((override.visibility_override if override is not None else None)
                                    or ("dm" if previous.dm_heavy else "players"))
        with _feature_write(service, campaign_slug, library, source.source_id,
                            previous.entry_key, previous.slug, previous,
                            retain_visibility=retain_visibility,
                            previous_override=override) as context:
            entry = service._save_custom_campaign_entry(
                campaign_slug, source=source, entry_key=previous.entry_key,
                slug=previous.slug, is_enabled_override=(
                    override.is_enabled_override if override is not None else None),
                _feature_write=context, **values,
            )
    _systems_service_cache_clear()
    return entry


def _request_manager(auth_store, campaign_slug, settings):
    from .auth import get_authenticated_user, get_current_user, get_current_auth_source
    if (not has_request_context()
            or get_current_auth_source() not in {"browser_session", "api_token"}):
        _fail("A genuine authenticated manager request is required.")
    actor, effective = get_authenticated_user(), get_current_user()
    if actor is None or effective is not actor or type(actor.id) is not int or actor.id < 1:
        _fail("View As or an unauthenticated actor cannot author registered mechanics.")
    current = auth_store.get_user_by_id(actor.id)
    if (current is None or current.status != "active"
            or current.auth_version != actor.auth_version
            or current.is_admin != actor.is_admin):
        _fail("The registered-feature actor is no longer current.")
    if not current.is_admin:
        membership = auth_store.get_membership(actor.id, campaign_slug)
        if membership is None or membership.status != "active" or membership.role != "dm":
            _fail("Current campaign DM access is required.")
    visibility = build_default_campaign_visibility_by_scope(settings.get("system", ""))
    for row in auth_store.list_campaign_visibility_settings(campaign_slug):
        if row.scope in {"campaign", "systems"}:
            if not is_valid_visibility(row.visibility):
                _fail("Current Systems visibility is invalid.")
            visibility[row.scope] = row.visibility
    effective_visibility = most_private_visibility(visibility["campaign"], visibility["systems"])
    if not current.is_admin and effective_visibility == "private":
        _fail("Current Systems scope is private.")
    return current


def _create_values(payload):
    if (type(payload) is not dict or any(type(key) is not str for key in payload)
            or set(payload) - _CREATE_FIELDS):
        _fail("Registered feature authoring accepts only its exact supported fields.")
    selection = payload.get("registered_feature_grant")
    effects = registered_feature_effects(selection)
    if type(payload.get("entry_type")) is not str or payload["entry_type"] != "feature":
        _fail("A registered feature grant requires entry type feature.")
    for key, value in payload.items():
        if type(value) is not str:
            _fail("Registered feature fields must be exact strings.")
    if payload.get("visibility", "dm") != "dm":
        _fail("This registered feature source requires explicit DM visibility.")
    title = payload.get("title", "").strip()
    provenance = payload.get("provenance", "").strip()
    search = payload.get("search_metadata", "").strip()
    raw_body = payload.get("body_markdown", "").strip()
    if (not title or len(title) > 200 or len(provenance) > 500
            or len(search) > 4000 or not raw_body or len(raw_body) > 100_000):
        _fail("Registered feature text exceeds the custom-entry limits.")
    body = sanitize_rich_markdown(raw_body).strip()
    if not body or len(body) > 100_000:
        _fail("Registered feature sources need a bounded rendered body.")
    html = sanitize_rich_html(markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]).convert(body))
    return selection, effects, title, provenance, search, body, html


def _projection(entry):
    return {field: deepcopy(getattr(entry, field)) for field in (
        "library_slug", "source_id", "entry_key", "entry_type", "slug", "title",
        "source_page", "source_path", "search_text", "player_safe_default",
        "dm_heavy", "metadata", "body", "rendered_html")}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _matches(entry, expected, *, reuse=False):
    actual = _projection(entry)
    compared = deepcopy(expected)
    if reuse:
        old_actor = actual["metadata"].get("updated_by_user_id")
        if type(old_actor) is not int or old_actor < 1:
            return False
        compared["metadata"]["updated_by_user_id"] = old_actor
    return _canonical(actual) == _canonical(compared)


def create_registered_campaign_feature(service, auth_store, campaign_slug, payload):
    """Called only by the existing authenticated custom-entry create endpoint."""
    selection, effects, title, provenance, search, body, html = _create_values(payload)
    from .committed_publication import active, config
    from .repository import slugify

    connection = get_db()
    # systems_transaction refuses ambient ownership and preserves cleanup errors.
    with systems_transaction():
        if get_db() is not connection or not active(connection):
            _fail("Registered features require current committed campaign settings.")
        _config_row, settings = config(campaign_slug, connection=connection)
        actor = _request_manager(auth_store, campaign_slug, settings)
        library_slug = default_systems_library_slug(settings.get("systems_library") or settings.get("system"))
        library = service.store.get_library(library_slug)
        if (normalize_system_code(settings.get("system")) != DND_5E_SYSTEM_CODE
                or library is None or library.status != "active"
                or library.library_slug != library_slug
                or normalize_system_code(library.system_code) != DND_5E_SYSTEM_CODE):
            _fail("Choose the existing active DND-5E Systems library.")
        source_id = service.get_campaign_custom_source_id(campaign_slug)
        source = service.store.get_source(library_slug, source_id)
        policy = service.store.get_campaign_policy(campaign_slug)
        enabled = service.store.get_campaign_enabled_source(campaign_slug, source_id)
        if (source is None or source.library_slug != library_slug or source.source_id != source_id
                or source.status != "active" or source.license_class != "custom_campaign"
                or policy is None or policy.status != "active" or policy.library_slug != library_slug
                or enabled is None or enabled.library_slug != library_slug
                or enabled.source_id != source_id or enabled.is_enabled is not True):
            _fail("The existing owned custom source must already be active and enabled.")
        leaf = slugify(payload.get("slug_leaf") or title).replace("/", "-").strip("-")
        if not leaf or len(leaf) > 200:
            _fail("Choose a bounded custom feature slug.")
        key = f"{library_slug.lower()}|custom|{campaign_slug}|{leaf}"
        slug = f"{source_id.lower()}-{leaf}"
        metadata = {"custom_campaign_slug": campaign_slug, "provenance": provenance,
                    "search_metadata": search, "body_format": "markdown",
                    "body_markdown": body, "updated_by_user_id": actor.id,
                    "mechanic_effects": effects}
        expected = {"library_slug": library_slug, "source_id": source_id,
                    "entry_key": key, "entry_type": "feature", "slug": slug,
                    "title": title, "source_page": "", "source_path": provenance,
                    "search_text": " ".join(part for part in
                        (title, "feature", source_id, provenance, search) if part).lower(),
                    "player_safe_default": False, "dm_heavy": True,
                    "metadata": metadata, "body": {"markdown": body}, "rendered_html": html}
        by_key = service.store.get_entry(library_slug, key)
        by_slug = service.store.get_entry_by_slug(library_slug, slug)
        override = service.store.get_campaign_entry_override(campaign_slug, key)
        created = by_key is None and by_slug is None
        if created:
            if override is not None:
                _fail("A conflicting feature override already occupies this identity.")
            with _feature_write(service, campaign_slug, library, source_id, key, slug,
                                effects=effects) as context:
                entry = service._save_custom_campaign_entry(
                    campaign_slug, source=source, entry_key=key, slug=slug,
                    title=title, entry_type="feature", provenance=provenance,
                    visibility="dm", search_metadata=search, body_markdown=body,
                    actor_user_id=actor.id, can_set_private=bool(actor.is_admin),
                    is_enabled_override=None, _feature_write=context,
                )
            if not _matches(entry, expected):
                raise RuntimeError("Registered feature readback differs from its exact candidate.")
        else:
            if (by_key is None or by_slug is None or by_key.id != by_slug.id
                    or not _matches(by_key, expected, reuse=True)
                    or override is None or override.library_slug != library_slug
                    or override.visibility_override != "dm"
                    or override.is_enabled_override is False):
                _fail("That custom feature key or slug conflicts with the reviewed content.")
            entry = by_key
        saved_override = service.store.get_campaign_entry_override(campaign_slug, key)
        if (saved_override is None or saved_override.library_slug != library_slug
                or saved_override.visibility_override != "dm"
                or saved_override.is_enabled_override is False):
            raise RuntimeError("Registered feature override readback failed.")
        audit = {"entry_key": key, "entry_slug": slug, "entry_type": "feature",
                 "registered_feature_grant": selection,
                 "source": "registered_feature_authoring", "created": created,
                 "entry_digest": sha256(_canonical(_projection(entry)).encode("utf-8")).hexdigest()}
        auth_store.insert_audit_event(
            event_type="campaign_systems_custom_feature_authored", actor_user_id=actor.id,
            campaign_slug=campaign_slug, metadata=audit, commit=False,
        )
        audit_row = connection.execute(
            "SELECT actor_user_id,campaign_slug,event_type,metadata_json FROM auth_audit_log WHERE id=last_insert_rowid()"
        ).fetchone()
        if (audit_row is None or audit_row["actor_user_id"] != actor.id
                or audit_row["campaign_slug"] != campaign_slug
                or audit_row["event_type"] != "campaign_systems_custom_feature_authored"
                or _canonical(json.loads(audit_row["metadata_json"]))
                    != _canonical(auth_store.sanitize_audit_metadata(audit))):
            raise RuntimeError("Registered feature audit readback failed.")
        final = service.store.get_entry(library_slug, key)
        if final is None or _canonical(_projection(final)) != _canonical(_projection(entry)):
            raise RuntimeError("Registered feature changed before commit.")
    # A failure below is postcommit, never proof of rollback or safe retry.
    _systems_service_cache_clear()
    return {"ok": True, "created": created,
            "registered_feature_grant": selection,
            "entry": {"id": final.id, "library_slug": final.library_slug,
                      "source_id": final.source_id, "entry_key": final.entry_key,
                      "slug": final.slug, "entry_type": final.entry_type,
                      "title": final.title, "visibility": "dm"}}
