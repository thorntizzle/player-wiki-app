from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request, url_for

from .systems_access import (
    filter_accessible_systems_entries,
    list_accessible_campaign_source_entries,
)
from .systems_labels import (
    SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
    systems_entry_type_label,
    systems_entry_type_sort_key,
)
from .systems_service import SystemsPolicyValidationError


@dataclass(frozen=True)
class SystemsApiReadDependencies:
    systems_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    systems_source_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    systems_entry_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    build_systems_index_payload: Callable[..., dict[str, Any]]
    get_repository: Callable[[], Any]
    get_systems_service: Callable[[], Any]
    can_access_systems_source: Callable[[str, str], bool]
    can_access_systems_entry: Callable[[str, str], bool]
    can_manage_systems: Callable[[str], bool]
    serialize_campaign: Callable[[Any], dict[str, Any]]
    serialize_systems_library: Callable[[Any], dict[str, Any] | None]
    serialize_systems_source_state: Callable[[str, Any], dict[str, Any]]
    serialize_systems_entry_summary: Callable[[Any], dict[str, Any]]
    serialize_systems_entry_record: Callable[[str, Any], dict[str, Any]]
    serialize_systems_rules_reference_result: Callable[[Any], dict[str, Any]]


@dataclass(frozen=True)
class SystemsApiMutationDependencies:
    systems_management_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    get_current_user: Callable[[], Any]
    load_json_object: Callable[[], dict[str, Any]]
    get_systems_service: Callable[[], Any]
    get_auth_store: Callable[[], Any]
    coerce_bool: Callable[..., bool]
    serialize_datetime: Callable[[Any], str | None]
    serialize_systems_source_state: Callable[[str, Any], dict[str, Any]]
    serialize_systems_entry_record: Callable[[str, Any], dict[str, Any]]
    serialize_custom_systems_entry: Callable[[str, Any], dict[str, Any]]
    build_dm_content_systems_payload: Callable[[str], dict[str, Any]]
    json_error: Callable[..., Any]


def register_systems_api_read_routes(
    api: Blueprint,
    *,
    dependencies: SystemsApiReadDependencies,
) -> None:
    def systems_index(campaign_slug: str):
        query = request.args.get("q", "").strip()
        reference_query = request.args.get("reference_q", "").strip()
        return jsonify(
            {
                "ok": True,
                **dependencies.build_systems_index_payload(
                    campaign_slug,
                    query=query,
                    reference_query=reference_query,
                ),
            }
        )

    def systems_source_list(campaign_slug: str):
        systems_service = dependencies.get_systems_service()
        source_states = systems_service.list_campaign_source_states(campaign_slug)
        if not dependencies.can_manage_systems(campaign_slug):
            source_states = [
                state
                for state in source_states
                if state.is_enabled
                and dependencies.can_access_systems_source(
                    campaign_slug,
                    state.source.source_id,
                )
            ]

        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(
                    dependencies.get_repository().get_campaign(campaign_slug)
                ),
                "library": dependencies.serialize_systems_library(
                    systems_service.get_campaign_library(campaign_slug)
                ),
                "sources": [
                    dependencies.serialize_systems_source_state(campaign_slug, state)
                    for state in source_states
                ],
                "permissions": {
                    "can_manage_systems": dependencies.can_manage_systems(campaign_slug),
                },
            }
        )

    def systems_source_detail(campaign_slug: str, source_id: str):
        systems_service = dependencies.get_systems_service()
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)

        book_entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            systems_service=systems_service,
            can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
            entry_type="book",
            limit=None,
        )
        all_entry_groups = []
        for entry_type, _ in systems_service.list_entry_type_counts_for_campaign_source(
            campaign_slug,
            source_id,
        ):
            accessible_entries = list_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                systems_service=systems_service,
                can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
                entry_type=entry_type,
                limit=None,
            )
            if not accessible_entries:
                continue
            all_entry_groups.append(
                {
                    "entry_type": entry_type,
                    "entry_type_label": systems_entry_type_label(entry_type),
                    "count": len(accessible_entries),
                }
            )
        all_entry_groups.sort(
            key=lambda item: (
                item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
                *systems_entry_type_sort_key(item["entry_type"]),
            )
        )
        entry_groups = [
            item
            for item in all_entry_groups
            if item["entry_type"] not in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]
        raw_rules_reference_entries = systems_service.list_rules_reference_entries_for_campaign(
            campaign_slug,
            include_source_ids=[source_id],
            limit=None,
        )
        rules_reference_entries = filter_accessible_systems_entries(
            campaign_slug,
            raw_rules_reference_entries,
            can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
        )
        has_book_rules_reference_entries = any(
            entry.entry_type == "book" for entry in rules_reference_entries
        )
        has_rule_rules_reference_entries = any(
            entry.entry_type == "rule" for entry in rules_reference_entries
        )
        if has_book_rules_reference_entries and has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters and rules entries using curated metadata like chapter "
                "labels, section headings, aliases, formulas, and rule facets. It does not search full entry body text."
            )
        elif has_book_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters using curated metadata like chapter labels and section "
                "headings. It does not search full entry body text."
            )
        elif has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's rules entries using curated metadata like aliases, formulas, and rule "
                "facets. It does not search full entry body text."
            )
        else:
            rules_reference_search_meta = ""
        rules_reference_scope = systems_service.get_rules_reference_search_scope_for_source(
            state.source
        )
        rules_reference_scope_note = (
            "This DM-heavy source keeps chapter browse and rules-reference metadata search on this source page instead "
            "of surfacing those chapter matches in the landing-page Rules Reference Search."
            if rules_reference_entries and rules_reference_scope == "source_only"
            else ""
        )
        reference_query = request.args.get("reference_q", "").strip()
        rules_reference_results = (
            [
                dependencies.serialize_systems_rules_reference_result(entry)
                for entry in filter_accessible_systems_entries(
                    campaign_slug,
                    systems_service.search_rules_reference_entries_for_campaign(
                        campaign_slug,
                        query=reference_query,
                        include_source_ids=[source_id],
                        limit=None,
                    ),
                    can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
                    limit=100,
                )
            ]
            if reference_query
            else []
        )

        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(
                    dependencies.get_repository().get_campaign(campaign_slug)
                ),
                "source": dependencies.serialize_systems_source_state(campaign_slug, state),
                "entry_groups": entry_groups,
                "book_entries": [
                    dependencies.serialize_systems_entry_summary(entry)
                    for entry in book_entries
                ],
                "entry_count": sum(item["count"] for item in all_entry_groups),
                "browsable_entry_count": sum(item["count"] for item in entry_groups),
                "hidden_entry_types": [
                    item["entry_type"]
                    for item in all_entry_groups
                    if item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
                ],
                "has_rules_reference_search": bool(rules_reference_entries),
                "rules_reference_search_meta": rules_reference_search_meta,
                "rules_reference_scope_note": rules_reference_scope_note,
                "reference_query": reference_query,
                "rules_reference_results": rules_reference_results,
                "book_visibility_policy_note": (
                    systems_service.get_book_entry_policy_note_for_source(state.source)
                    if book_entries
                    else ""
                ),
                "permissions": {
                    "can_manage_systems": dependencies.can_manage_systems(campaign_slug),
                },
            }
        )

    def systems_source_category_detail(
        campaign_slug: str,
        source_id: str,
        entry_type: str,
    ):
        systems_service = dependencies.get_systems_service()
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)

        normalized_entry_type = str(entry_type or "").strip().lower()
        if not normalized_entry_type:
            abort(404)

        all_entry_groups = []
        for grouped_entry_type, _ in systems_service.list_entry_type_counts_for_campaign_source(
            campaign_slug,
            source_id,
        ):
            accessible_entries = list_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                systems_service=systems_service,
                can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
                entry_type=grouped_entry_type,
                limit=None,
            )
            if not accessible_entries:
                continue
            all_entry_groups.append(
                {
                    "entry_type": grouped_entry_type,
                    "entry_type_label": systems_entry_type_label(grouped_entry_type),
                    "count": len(accessible_entries),
                }
            )
        all_entry_groups.sort(
            key=lambda item: (
                item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
                *systems_entry_type_sort_key(item["entry_type"]),
            )
        )
        entry_groups = [
            item
            for item in all_entry_groups
            if item["entry_type"] not in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]

        all_entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            systems_service=systems_service,
            can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
            entry_type=normalized_entry_type,
            limit=None,
        )
        entry_count = len(all_entries)
        if entry_count <= 0:
            abort(404)

        query = request.args.get("q", "").strip()
        entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            systems_service=systems_service,
            can_access_campaign_systems_entry=dependencies.can_access_systems_entry,
            entry_type=normalized_entry_type,
            query=query,
            limit=None,
        )

        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(
                    dependencies.get_repository().get_campaign(campaign_slug)
                ),
                "source": dependencies.serialize_systems_source_state(campaign_slug, state),
                "entry_groups": entry_groups,
                "entry_type": normalized_entry_type,
                "entry_type_label": systems_entry_type_label(normalized_entry_type),
                "query": query,
                "entry_count": entry_count,
                "filtered_entry_count": len(entries),
                "entries": [
                    dependencies.serialize_systems_entry_summary(entry) for entry in entries
                ],
                "permissions": {
                    "can_manage_systems": dependencies.can_manage_systems(campaign_slug),
                },
            }
        )

    def systems_entry_detail(campaign_slug: str, entry_slug: str):
        entry = dependencies.get_systems_service().get_entry_by_slug_for_campaign(
            campaign_slug,
            entry_slug,
        )
        if entry is None:
            abort(404)

        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(
                    dependencies.get_repository().get_campaign(campaign_slug)
                ),
                "entry": dependencies.serialize_systems_entry_record(campaign_slug, entry),
                "permissions": {
                    "can_manage_systems": dependencies.can_manage_systems(campaign_slug),
                },
                "links": {
                    "flask_entry_url": url_for(
                        "campaign_systems_entry_detail",
                        campaign_slug=campaign_slug,
                        entry_slug=entry.slug,
                    ),
                    "flask_source_url": url_for(
                        "campaign_systems_source_detail",
                        campaign_slug=campaign_slug,
                        source_id=entry.source_id,
                    ),
                    "flask_source_category_url": url_for(
                        "campaign_systems_source_type_detail",
                        campaign_slug=campaign_slug,
                        source_id=entry.source_id,
                        entry_type=entry.entry_type,
                    ),
                    "dm_content_systems_url": (
                        url_for(
                            "campaign_dm_content_subpage_view",
                            campaign_slug=campaign_slug,
                            dm_content_subpage="systems",
                            entry_key=entry.entry_key,
                            _anchor="systems-entry-overrides",
                        )
                        if dependencies.can_manage_systems(campaign_slug)
                        else ""
                    ),
                },
            }
        )

    systems_index_view = dependencies.systems_scope_access_required(systems_index)
    systems_source_list_view = dependencies.systems_scope_access_required(
        systems_source_list
    )
    systems_source_detail_view = dependencies.systems_source_access_required(
        systems_source_detail
    )
    systems_source_category_detail_view = dependencies.systems_source_access_required(
        systems_source_category_detail
    )
    systems_entry_detail_view = dependencies.systems_entry_access_required(
        systems_entry_detail
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/search",
        endpoint="systems_index",
        view_func=systems_index_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems",
        endpoint="systems_index",
        view_func=systems_index_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/sources",
        endpoint="systems_source_list",
        view_func=systems_source_list_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/sources/<source_id>",
        endpoint="systems_source_detail",
        view_func=systems_source_detail_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
        endpoint="systems_source_category_detail",
        view_func=systems_source_category_detail_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
        endpoint="systems_entry_detail",
        view_func=systems_entry_detail_view,
        methods=("GET",),
    )


def register_systems_api_routes(
    api: Blueprint,
    *,
    read_dependencies: SystemsApiReadDependencies,
    mutation_dependencies: SystemsApiMutationDependencies,
) -> None:
    dependencies = mutation_dependencies

    def systems_source_update(campaign_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            updates = list(payload.get("updates") or [])
            acknowledge_proprietary = bool(payload.get("acknowledge_proprietary"))
            can_set_private = bool(user.is_admin)
            changed_sources = (
                dependencies.get_systems_service().update_campaign_sources(
                    campaign_slug,
                    updates=updates,
                    actor_user_id=user.id,
                    acknowledge_proprietary=acknowledge_proprietary,
                    can_set_private=can_set_private,
                )
            )
        except (SystemsPolicyValidationError, ValueError) as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        auth_store = dependencies.get_auth_store()
        systems_service = dependencies.get_systems_service()
        for source in changed_sources:
            state = systems_service.get_campaign_source_state(
                campaign_slug,
                source.source_id,
            )
            if state is None:
                continue
            auth_store.write_audit_event(
                event_type="campaign_systems_source_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "library_slug": source.library_slug,
                    "source_id": source.source_id,
                    "visibility": state.default_visibility,
                    "is_enabled": state.is_enabled,
                    "source": "api",
                },
            )

        return jsonify(
            {
                "ok": True,
                "sources": [
                    dependencies.serialize_systems_source_state(campaign_slug, state)
                    for state in systems_service.list_campaign_source_states(
                        campaign_slug
                    )
                ],
            }
        )

    def systems_entry_override_update(campaign_slug: str, entry_key: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            visibility_override = payload.get("visibility_override")
            is_enabled_override = payload.get("is_enabled_override")
            if is_enabled_override is not None:
                is_enabled_override = dependencies.coerce_bool(
                    is_enabled_override,
                    label="is_enabled_override",
                )
            override = (
                dependencies.get_systems_service().update_campaign_entry_override(
                    campaign_slug,
                    entry_key=entry_key,
                    visibility_override=(
                        str(visibility_override).strip()
                        if visibility_override not in (None, "")
                        else None
                    ),
                    is_enabled_override=is_enabled_override,
                    actor_user_id=user.id,
                    can_set_private=bool(user.is_admin),
                )
            )
        except (SystemsPolicyValidationError, ValueError) as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        dependencies.get_auth_store().write_audit_event(
            event_type="campaign_systems_entry_override_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": override.entry_key,
                "visibility": override.visibility_override or "inherit",
                "source": "api",
            },
        )
        entry = dependencies.get_systems_service().get_entry_for_campaign(
            campaign_slug,
            entry_key,
        )
        return jsonify(
            {
                "ok": True,
                "override": {
                    "entry_key": override.entry_key,
                    "visibility_override": override.visibility_override,
                    "is_enabled_override": override.is_enabled_override,
                    "updated_at": dependencies.serialize_datetime(override.updated_at),
                    "updated_by_user_id": override.updated_by_user_id,
                },
                "entry": (
                    dependencies.serialize_systems_entry_record(campaign_slug, entry)
                    if entry is not None
                    else None
                ),
            }
        )

    def systems_custom_entry_create(campaign_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            item_mechanics = payload.get("item_mechanics")
            entry = dependencies.get_systems_service().create_custom_campaign_entry(
                campaign_slug,
                title=str(payload.get("title") or ""),
                entry_type=str(payload.get("entry_type") or ""),
                slug_leaf=str(payload.get("slug_leaf") or ""),
                provenance=str(payload.get("provenance") or ""),
                visibility=str(payload.get("visibility") or ""),
                search_metadata=str(payload.get("search_metadata") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                source_page_ref=str(payload.get("source_page_ref") or ""),
                item_mechanics_review_status=(
                    payload.get("item_mechanics_review_status")
                    or payload.get("mechanics_review_status")
                    or ""
                ),
                item_mechanics=(
                    item_mechanics if isinstance(item_mechanics, dict) else None
                ),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")
        except SystemsPolicyValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        dependencies.get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_created",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "api",
            },
        )
        return jsonify(
            {
                "ok": True,
                "entry": dependencies.serialize_custom_systems_entry(
                    campaign_slug,
                    entry,
                ),
                "systems": dependencies.build_dm_content_systems_payload(
                    campaign_slug
                ),
            }
        )

    def systems_custom_entry_update(campaign_slug: str, entry_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            item_mechanics = payload.get("item_mechanics")
            entry = dependencies.get_systems_service().update_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                title=str(payload.get("title") or ""),
                entry_type=str(payload.get("entry_type") or ""),
                provenance=str(payload.get("provenance") or ""),
                visibility=str(payload.get("visibility") or ""),
                search_metadata=str(payload.get("search_metadata") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                source_page_ref=str(payload.get("source_page_ref") or ""),
                item_mechanics_review_status=(
                    payload.get("item_mechanics_review_status")
                    or payload.get("mechanics_review_status")
                    or ""
                ),
                item_mechanics=(
                    item_mechanics if isinstance(item_mechanics, dict) else None
                ),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")
        except SystemsPolicyValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        dependencies.get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "api",
            },
        )
        return jsonify(
            {
                "ok": True,
                "entry": dependencies.serialize_custom_systems_entry(
                    campaign_slug,
                    entry,
                ),
                "systems": dependencies.build_dm_content_systems_payload(
                    campaign_slug
                ),
            }
        )

    def systems_custom_entry_archive(campaign_slug: str, entry_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            entry = dependencies.get_systems_service().archive_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        dependencies.get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_archived",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "api",
            },
        )
        refreshed = (
            dependencies.get_systems_service().get_custom_campaign_entry_by_slug(
                campaign_slug,
                entry_slug,
            )
            or entry
        )
        return jsonify(
            {
                "ok": True,
                "entry": dependencies.serialize_custom_systems_entry(
                    campaign_slug,
                    refreshed,
                ),
                "systems": dependencies.build_dm_content_systems_payload(
                    campaign_slug
                ),
            }
        )

    def systems_custom_entry_restore(campaign_slug: str, entry_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            entry = dependencies.get_systems_service().restore_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        dependencies.get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_restored",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "api",
            },
        )
        refreshed = (
            dependencies.get_systems_service().get_custom_campaign_entry_by_slug(
                campaign_slug,
                entry_slug,
            )
            or entry
        )
        return jsonify(
            {
                "ok": True,
                "entry": dependencies.serialize_custom_systems_entry(
                    campaign_slug,
                    refreshed,
                ),
                "systems": dependencies.build_dm_content_systems_payload(
                    campaign_slug
                ),
            }
        )

    systems_source_update_view = dependencies.systems_management_required(
        dependencies.login_required(systems_source_update)
    )
    systems_entry_override_update_view = dependencies.systems_management_required(
        dependencies.login_required(systems_entry_override_update)
    )
    systems_custom_entry_create_view = dependencies.systems_management_required(
        dependencies.login_required(systems_custom_entry_create)
    )
    systems_custom_entry_update_view = dependencies.systems_management_required(
        dependencies.login_required(systems_custom_entry_update)
    )
    systems_custom_entry_archive_view = dependencies.systems_management_required(
        dependencies.login_required(systems_custom_entry_archive)
    )
    systems_custom_entry_restore_view = dependencies.systems_management_required(
        dependencies.login_required(systems_custom_entry_restore)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/sources",
        endpoint="systems_source_update",
        view_func=systems_source_update_view,
        methods=("PUT",),
    )
    register_systems_api_read_routes(api, dependencies=read_dependencies)
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/overrides/<path:entry_key>",
        endpoint="systems_entry_override_update",
        view_func=systems_entry_override_update_view,
        methods=("PUT",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/custom-entries",
        endpoint="systems_custom_entry_create",
        view_func=systems_custom_entry_create_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>",
        endpoint="systems_custom_entry_update",
        view_func=systems_custom_entry_update_view,
        methods=("PUT",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive",
        endpoint="systems_custom_entry_archive",
        view_func=systems_custom_entry_archive_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore",
        endpoint="systems_custom_entry_restore",
        view_func=systems_custom_entry_restore_view,
        methods=("POST",),
    )
