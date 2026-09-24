"""Explicit owners for Systems saves and their required database history."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
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


def save_shared_core_entry(service, auth_store, campaign_slug, entry_slug, *, actor_user_id, **values):
    prepared = prepare_systems_mutation(service, campaign_slug)
    with systems_transaction():
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
    _finish_mutation()
    return entry
