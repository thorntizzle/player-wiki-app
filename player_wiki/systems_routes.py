from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .auth import (
    can_manage_campaign_systems,
    campaign_scope_access_required,
    campaign_systems_entry_access_required,
    campaign_systems_source_access_required,
    get_auth_store,
    get_current_user,
    login_required,
)
from .repository import normalize_lookup
from .systems_service import SystemsPolicyValidationError


systems = Blueprint("systems", __name__)


@dataclass(frozen=True)
class SystemsRouteDependencies:
    build_index_context: Callable[..., dict[str, object]]
    build_source_context: Callable[..., dict[str, object]]
    build_source_category_context: Callable[..., dict[str, object]]
    build_entry_context: Callable[..., dict[str, object]]
    load_campaign: Callable[[str], Any]
    get_service: Callable[[], Any]
    build_control_context: Callable[[str], dict[str, object]]
    build_dm_content_context: Callable[..., dict[str, object]]
    redirect_to_dm_content: Callable[..., Any]


@dataclass(frozen=True)
class SystemsSourcePolicyUpdateInput:
    source_id: str
    is_enabled: bool
    default_visibility: str


@dataclass(frozen=True)
class SystemsSourcePolicyFormInput:
    return_to_dm_content_systems: bool
    acknowledge_proprietary: bool
    updates: tuple[SystemsSourcePolicyUpdateInput, ...]


@dataclass(frozen=True)
class SystemsEntryOverrideFormInput:
    return_to_dm_content_systems: bool
    entry_key: str
    visibility_override: str | None
    is_enabled_override: bool | None


def _dependencies() -> SystemsRouteDependencies:
    return current_app.extensions["systems_route_dependencies"]


def _parse_source_policy_form(source_states: list[Any]) -> SystemsSourcePolicyFormInput:
    updates = []
    for state in source_states:
        source_id = state.source.source_id
        updates.append(
            SystemsSourcePolicyUpdateInput(
                source_id=source_id,
                is_enabled=request.form.get(f"source_{source_id}_enabled") == "1",
                default_visibility=request.form.get(
                    f"source_{source_id}_visibility",
                    state.default_visibility,
                ),
            )
        )
    return SystemsSourcePolicyFormInput(
        return_to_dm_content_systems=request.form.get("return_to") == "dm-content-systems",
        acknowledge_proprietary=request.form.get("acknowledge_proprietary") == "yes",
        updates=tuple(updates),
    )


def _parse_entry_override_form() -> SystemsEntryOverrideFormInput:
    raw_enabled_override = normalize_lookup(request.form.get("is_enabled_override", ""))
    enabled_override = None
    if raw_enabled_override == "enabled":
        enabled_override = True
    elif raw_enabled_override == "disabled":
        enabled_override = False
    return SystemsEntryOverrideFormInput(
        return_to_dm_content_systems=request.form.get("return_to") == "dm-content-systems",
        entry_key=request.form.get("entry_key", ""),
        visibility_override=request.form.get("visibility_override", "").strip() or None,
        is_enabled_override=enabled_override,
    )


@campaign_scope_access_required("systems")
def campaign_systems_index(campaign_slug: str):
    query = request.args.get("q", "").strip()
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_index_context(
        campaign_slug,
        query=query,
        reference_query=reference_query,
    )
    return render_template("systems_index.html", **context)


@campaign_scope_access_required("systems")
def campaign_systems_search(campaign_slug: str):
    query = request.args.get("q", "").strip()
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_index_context(
        campaign_slug,
        query=query,
        reference_query=reference_query,
    )
    return render_template("systems_index.html", **context)


@campaign_systems_source_access_required
def campaign_systems_source_detail(campaign_slug: str, source_id: str):
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_source_context(
        campaign_slug,
        source_id,
        reference_query=reference_query,
    )
    return render_template("systems_source_detail.html", **context)


@campaign_systems_source_access_required
def campaign_systems_source_type_detail(campaign_slug: str, source_id: str, entry_type: str):
    query = request.args.get("q", "").strip()
    context = _dependencies().build_source_category_context(
        campaign_slug,
        source_id,
        entry_type,
        query=query,
    )
    return render_template("systems_source_type_detail.html", **context)


@campaign_systems_entry_access_required
def campaign_systems_entry_detail(campaign_slug: str, entry_slug: str):
    context = _dependencies().build_entry_context(campaign_slug, entry_slug)
    return render_template("systems_entry_detail.html", **context)


@login_required
def campaign_systems_control_panel_update_sources(campaign_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    systems_service = dependencies.get_service()
    form = _parse_source_policy_form(
        systems_service.list_campaign_source_states(campaign_slug)
    )
    try:
        changed_sources = systems_service.update_campaign_sources(
            campaign_slug,
            updates=[
                {
                    "source_id": update.source_id,
                    "is_enabled": update.is_enabled,
                    "default_visibility": update.default_visibility,
                }
                for update in form.updates
            ],
            actor_user_id=user.id,
            acknowledge_proprietary=form.acknowledge_proprietary,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        if form.return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **dependencies.build_dm_content_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                ),
            ), 400
        return render_template(
            "campaign_systems_control_panel.html",
            **dependencies.build_control_context(campaign_slug),
        ), 400

    if changed_sources:
        auth_store = get_auth_store()
        for source in changed_sources:
            state = systems_service.get_campaign_source_state(campaign_slug, source.source_id)
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
                    "source": "campaign_systems_control_panel",
                },
            )
        flash(
            f"Updated systems sources: {', '.join(source.source_id for source in changed_sources)}.",
            "success",
        )
    else:
        flash("Systems source settings already matched those values.", "success")

    if form.return_to_dm_content_systems:
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor="systems-source-enablement",
        )
    return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))


@login_required
def campaign_systems_control_panel_update_override(campaign_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    form = _parse_entry_override_form()
    try:
        override = dependencies.get_service().update_campaign_entry_override(
            campaign_slug,
            entry_key=form.entry_key,
            visibility_override=form.visibility_override,
            is_enabled_override=form.is_enabled_override,
            actor_user_id=user.id,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        if form.return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **dependencies.build_dm_content_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                ),
            ), 400
        return render_template(
            "campaign_systems_control_panel.html",
            **dependencies.build_control_context(campaign_slug),
        ), 400

    get_auth_store().write_audit_event(
        event_type="campaign_systems_entry_override_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": override.entry_key,
            "visibility": override.visibility_override or "inherit",
            "source": "campaign_systems_control_panel",
        },
    )
    flash("Saved systems entry override.", "success")
    if form.return_to_dm_content_systems:
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor="systems-entry-overrides",
        )
    return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))


@systems.record_once
def _register_legacy_endpoints(state: Any) -> None:
    """Register supported bare endpoint IDs without Blueprint aliases."""

    registrations = (
        (
            "/campaigns/<campaign_slug>/systems",
            "campaign_systems_index",
            campaign_systems_index,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/search",
            "campaign_systems_search",
            campaign_systems_search,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>",
            "campaign_systems_source_detail",
            campaign_systems_source_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
            "campaign_systems_source_type_detail",
            campaign_systems_source_type_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
            "campaign_systems_entry_detail",
            campaign_systems_entry_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/sources",
            "campaign_systems_control_panel_update_sources",
            campaign_systems_control_panel_update_sources,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/overrides",
            "campaign_systems_control_panel_update_override",
            campaign_systems_control_panel_update_override,
            ("POST",),
        ),
    )
    for rule, endpoint, view_func, methods in registrations:
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def register_systems_routes(
    app: Any,
    *,
    build_index_context: Callable[..., dict[str, object]],
    build_source_context: Callable[..., dict[str, object]],
    build_source_category_context: Callable[..., dict[str, object]],
    build_entry_context: Callable[..., dict[str, object]],
    load_campaign: Callable[[str], Any],
    get_service: Callable[[], Any],
    build_control_context: Callable[[str], dict[str, object]],
    build_dm_content_context: Callable[..., dict[str, object]],
    redirect_to_dm_content: Callable[..., Any],
) -> None:
    app.extensions["systems_route_dependencies"] = SystemsRouteDependencies(
        build_index_context=build_index_context,
        build_source_context=build_source_context,
        build_source_category_context=build_source_category_context,
        build_entry_context=build_entry_context,
        load_campaign=load_campaign,
        get_service=get_service,
        build_control_context=build_control_context,
        build_dm_content_context=build_dm_content_context,
        redirect_to_dm_content=redirect_to_dm_content,
    )
    app.register_blueprint(systems)
