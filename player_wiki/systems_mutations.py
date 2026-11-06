"""Explicit owners for Systems saves and their required database history."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from typing import Any

from .db import get_db


@dataclass(frozen=True)
class PreparedSystemsMutation:
    service: Any
    connection: Any
    campaign_slug: str
    library: Any
    source_states: tuple[Any, ...]


def prepare_systems_mutation(service, campaign_slug: str) -> PreparedSystemsMutation:
    """Complete committing catalog maintenance before business ownership starts."""
    connection = get_db()
    if connection.in_transaction:
        raise RuntimeError("Systems save requires explicit joining of the caller transaction.")
    library = service.get_campaign_library(campaign_slug)
    if library is None:
        from .systems_service import SystemsPolicyValidationError
        raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
    return PreparedSystemsMutation(
        service, connection, campaign_slug, library,
        tuple(service._build_campaign_source_states(campaign_slug, library)),
    )


def resolve_systems_mutation(service, campaign_slug, *, commit, prepared):
    if commit:
        if prepared is not None:
            raise RuntimeError("Prepared Systems context is only accepted when joining a transaction.")
        return prepare_systems_mutation(service, campaign_slug)
    if (prepared is None or prepared.service is not service
            or prepared.connection is not get_db()
            or prepared.campaign_slug != campaign_slug or not get_db().in_transaction):
        raise RuntimeError("Joined Systems save requires its prepared context and an active caller transaction.")
    return prepared


@contextmanager
def systems_transaction(*, commit=True):
    connection = get_db()
    if not commit:
        if not connection.in_transaction:
            raise RuntimeError("Joined Systems save requires an active caller transaction.")
        yield
        return
    if connection.in_transaction:
        raise RuntimeError("Systems save requires explicit joining of the caller transaction.")
    # The shared connection context owns failed-commit cleanup and preserves
    # attempted metrics and chained rollback failures. Join mode never enters it.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        yield


def _finish_mutation():
    from .systems_service import _systems_service_cache_clear
    _systems_service_cache_clear()


def save_campaign_sources(service, auth_store, campaign_slug, *, audit_source, **values):
    prepared = prepare_systems_mutation(service, campaign_slug)
    with systems_transaction():
        sources = service.update_campaign_sources(
            campaign_slug, **values, commit=False, prepared=prepared,
        )
        for source in sources:
            state = service.store.get_campaign_enabled_source(campaign_slug, source.source_id)
            if state is None:
                raise RuntimeError("Failed to reload saved Systems source for audit.")
            auth_store.insert_audit_event(
                event_type="campaign_systems_source_updated",
                actor_user_id=values["actor_user_id"], campaign_slug=campaign_slug,
                metadata={
                    "library_slug": source.library_slug, "source_id": source.source_id,
                    "visibility": state.default_visibility, "is_enabled": state.is_enabled,
                    "source": audit_source,
                }, commit=False,
            )
    _finish_mutation()
    return sources


def save_campaign_override(service, auth_store, campaign_slug, *, audit_source, **values):
    prepared = prepare_systems_mutation(service, campaign_slug)
    with systems_transaction():
        override = service.update_campaign_entry_override(
            campaign_slug, **values, commit=False, prepared=prepared,
        )
        auth_store.insert_audit_event(
            event_type="campaign_systems_entry_override_updated",
            actor_user_id=values["actor_user_id"], campaign_slug=campaign_slug,
            metadata={"entry_key": override.entry_key,
                      "visibility": override.visibility_override or "inherit",
                      "source": audit_source}, commit=False,
        )
    _finish_mutation()
    return override


def save_shared_core_permission(service, auth_store, campaign_slug, **values):
    prepared = prepare_systems_mutation(service, campaign_slug)
    with systems_transaction():
        policy = service.update_campaign_shared_core_entry_edit_permission(
            campaign_slug, **values, commit=False, prepared=prepared,
        )
        auth_store.insert_audit_event(
            event_type="campaign_systems_shared_core_edit_permission_updated",
            actor_user_id=values["actor_user_id"], campaign_slug=campaign_slug,
            metadata={"library_slug": policy.library_slug,
                      "allow_dm_shared_core_entry_edits": policy.allow_dm_shared_core_entry_edits,
                      "source": "campaign_systems_control_panel"}, commit=False,
        )
    _finish_mutation()
    return policy


def _original_source_identity(entry):
    return {field: getattr(entry, attribute) for field, attribute in (
        ("library_slug", "library_slug"), ("source_id", "source_id"),
        ("entry_key", "entry_key"), ("entry_slug", "slug"),
        ("entry_type", "entry_type"), ("title", "title"),
        ("source_page", "source_page"), ("source_path", "source_path"),
    )}


def _changed_fields(before, after):
    fields = ("title", "source_page", "source_path", "search_text",
              "player_safe_default", "dm_heavy", "metadata", "body", "rendered_html")
    def value(entry, field):
        raw = getattr(entry, field)
        if field in {"player_safe_default", "dm_heavy"}:
            return bool(raw)
        if field in {"metadata", "body"}:
            return dict(raw or {})
        return raw
    return [field for field in fields if value(before, field) != value(after, field)]


def _save_shared_core_entry(prepared, auth_store, entry_slug, actor_user_id, values):
    service, campaign_slug = prepared.service, prepared.campaign_slug
    before = service.store.get_entry_by_slug(prepared.library.library_slug, entry_slug)
    entry = service.update_shared_core_entry(
        campaign_slug, entry_slug, **values, commit=False, prepared=prepared,
    )
    original_identity = _original_source_identity(before)
    edited_fields = _changed_fields(before, entry)
    metadata = {
        "campaign_slug": campaign_slug, "library_slug": entry.library_slug,
        "source_id": entry.source_id, "entry_key": entry.entry_key,
        "entry_slug": entry.slug, "source": "campaign_systems_shared_entry_editor",
        "original_source_identity": original_identity, "edited_fields": edited_fields,
    }
    service.store.record_shared_entry_edit_event(
        campaign_slug=campaign_slug, library_slug=entry.library_slug,
        source_id=entry.source_id, entry_key=entry.entry_key, entry_slug=entry.slug,
        original_source_identity=original_identity, edited_fields=edited_fields,
        actor_user_id=actor_user_id, audit_event_type="campaign_systems_shared_entry_updated",
        audit_metadata=metadata, commit=False,
    )
    auth_store.insert_audit_event(
        event_type="campaign_systems_shared_entry_updated", actor_user_id=actor_user_id,
        campaign_slug=campaign_slug, metadata=metadata, commit=False,
    )
    return entry


def save_shared_core_entry(service, auth_store, campaign_slug, entry_slug, *, actor_user_id, **values):
    prepared = prepare_systems_mutation(service, campaign_slug)
    with systems_transaction():
        entry = _save_shared_core_entry(prepared, auth_store, entry_slug, actor_user_id, values)
    _finish_mutation()
    return entry


def save_shared_core_entries(service, auth_store, campaign_slug, *, actor_user_id,
                             expected_revision, updates):
    """Admin-only atomic CAS batch; callers qualify the returned commit separately.

    Each update contains the complete stored row as ``expected`` and the normal
    editor's nine ``values``. No entry identity can be changed. Catalog preparation
    retains the existing single-save contract and precedes business ownership.
    """
    from .systems_service import SystemsPolicyValidationError

    def refuse(message):
        raise SystemsPolicyValidationError(message)

    fields = {"title", "source_page", "source_path", "search_text", "player_safe_default",
              "dm_heavy", "metadata", "body", "rendered_html"}
    if (type(actor_user_id) is not int or not isinstance(expected_revision, str)
            or len(expected_revision) != 64 or type(updates) is not list
            or not 1 <= len(updates) <= 100):
        refuse("Supply an actor, expected Systems revision and 1–100 entry updates.")
    # Detach the request from mutable caller-owned dictionaries; reject non-JSON values.
    updates = json.loads(json.dumps(updates, allow_nan=False))
    seen = set()
    for update in updates:
        if (type(update) is not dict or set(update) != {"expected", "values"}
                or type(update["expected"]) is not dict or type(update["values"]) is not dict
                or set(update["values"]) != fields):
            refuse("Each update needs a complete expected row and all editor values.")
        expected, values = update["expected"], update["values"]
        slug = expected.get("slug")
        if not isinstance(slug, str) or not slug or slug in seen:
            refuse("Choose distinct existing entry slugs.")
        seen.add(slug)
        if (any(type(values[k]) is not str for k in fields - {"metadata", "body", "player_safe_default", "dm_heavy"})
                or any(type(values[k]) is not dict for k in ("metadata", "body"))
                or any(type(values[k]) is not bool for k in ("player_safe_default", "dm_heavy"))):
            refuse("Editor values have invalid JSON types.")
    from .committed_publication import active, config
    if not active():
        refuse("Atomic shared-entry batches require committed campaign settings.")
    user = auth_store.get_user_by_id(actor_user_id)
    if user is None or not user.is_active or not user.is_admin:
        refuse("Atomic shared-entry batches require an active app admin.")
    policy = dict(config(campaign_slug)[0])
    prepared = prepare_systems_mutation(service, campaign_slug)
    if prepared.library.status != "active":
        refuse("Choose an active Systems library.")
    with systems_transaction():
        user = auth_store.get_user_by_id(actor_user_id)
        if user is None or not user.is_active or not user.is_admin:
            refuse("Atomic shared-entry batches require an active app admin.")
        current_policy = dict(config(campaign_slug, connection=prepared.connection)[0])
        if (current_policy != policy
                or service.store.get_durable_revision() != expected_revision):
            refuse("Systems or campaign policy changed; obtain a fresh preview.")
        states = {state.source.source_id: state for state in prepared.source_states}
        for update in updates:
            expected = update["expected"]
            actual = service.store.get_entry_preimage(prepared.library.library_slug, expected["slug"])
            if (actual is None or json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True)):
                refuse("An entry changed; obtain a fresh preview.")
            state = states.get(actual["source_id"])
            override = service.store.get_campaign_entry_override(
                campaign_slug, actual["entry_key"],
            )
            if (state is None or not state.is_enabled or state.source.status != "active"
                    or (override is not None and override.is_enabled_override is False)):
                refuse("A selected entry is not currently enabled.")
        entries = [_save_shared_core_entry(prepared, auth_store, update["expected"]["slug"],
                                           actor_user_id, update["values"]) for update in updates]
        # Capture the final token before commit; later readback is not part of saving.
        revision = service.store.get_durable_revision()
    warning = None
    try:
        _finish_mutation()
    except Exception as error:
        warning = type(error).__name__
    return {"committed": True, "systems_revision": revision,
            "campaign_slug": campaign_slug, "actor_user_id": actor_user_id,
            "entry_keys": [entry.entry_key for entry in entries],
            "postcommit_cache_error": warning}
