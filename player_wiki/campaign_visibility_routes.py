from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from flask import Blueprint, Flask, abort, flash, jsonify, redirect, render_template, request, url_for


@dataclass(frozen=True)
class CampaignVisibilityBrowserDependencies:
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_campaign_context: Callable[[str], Any]
    can_manage_campaign_visibility: Callable[[str], bool]
    build_campaign_visibility_control_context: Callable[[str], dict[str, object]]
    get_current_user: Callable[[], Any | None]
    get_auth_store: Callable[[], Any]
    get_campaign_default_scope_visibility: Callable[[str, str], str]
    normalize_visibility_choice: Callable[[object], str]
    is_valid_visibility: Callable[[str], bool]
    clear_campaign_visibility_cache: Callable[[str], None]
    campaign_visibility_scopes: Sequence[str]
    campaign_visibility_scope_labels: Mapping[str, str]
    visibility_private: str


@dataclass(frozen=True)
class CampaignVisibilityApiDependencies:
    api_campaign_visibility_management_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    get_repository: Callable[[], Any]
    get_current_user: Callable[[], Any | None]
    serialize_campaign: Callable[[Any], dict[str, Any]]
    serialize_campaign_control_visibility_row: Callable[[str, str], dict[str, Any]]
    flask_campaign_href: Callable[[str, str], str]
    load_json_object: Callable[[], dict[str, Any]]
    json_error: Callable[..., Any]
    get_auth_store: Callable[[], Any]
    get_campaign_default_scope_visibility: Callable[[str, str], str]
    normalize_visibility_choice: Callable[[object], str]
    is_valid_visibility: Callable[[str], bool]
    clear_campaign_visibility_cache: Callable[[str], None]
    campaign_visibility_scopes: Sequence[str]
    campaign_visibility_scope_labels: Mapping[str, str]
    visibility_private: str


def register_campaign_visibility_browser_routes(
    app: Flask,
    *,
    dependencies: CampaignVisibilityBrowserDependencies,
) -> None:
    def campaign_control_panel_view(campaign_slug: str):
        dependencies.load_campaign_context(campaign_slug)
        if not dependencies.can_manage_campaign_visibility(campaign_slug):
            abort(403)

        context = dependencies.build_campaign_visibility_control_context(campaign_slug)
        return render_template("campaign_control_panel.html", **context)

    def campaign_control_panel_update_visibility(campaign_slug: str):
        dependencies.load_campaign_context(campaign_slug)
        if not dependencies.can_manage_campaign_visibility(campaign_slug):
            abort(403)

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        auth_store_instance = dependencies.get_auth_store()
        changed_scopes: list[str] = []
        for scope in dependencies.campaign_visibility_scopes:
            current_visibility = auth_store_instance.get_campaign_visibility_setting(campaign_slug, scope)
            default_visibility = dependencies.get_campaign_default_scope_visibility(campaign_slug, scope)
            selected_visibility = dependencies.normalize_visibility_choice(
                request.form.get(
                    f"{scope}_visibility",
                    current_visibility.visibility if current_visibility is not None else default_visibility,
                )
            )
            if not dependencies.is_valid_visibility(selected_visibility):
                flash(
                    f"Choose a valid visibility for {dependencies.campaign_visibility_scope_labels[scope]}.",
                    "error",
                )
                return render_template(
                    "campaign_control_panel.html",
                    **dependencies.build_campaign_visibility_control_context(campaign_slug),
                ), 400
            if selected_visibility == dependencies.visibility_private and not user.is_admin:
                flash("Private visibility is reserved for app admins.", "error")
                return render_template(
                    "campaign_control_panel.html",
                    **dependencies.build_campaign_visibility_control_context(campaign_slug),
                ), 400

            if current_visibility is not None and current_visibility.visibility == selected_visibility:
                continue
            if current_visibility is None and default_visibility == selected_visibility:
                continue

            auth_store_instance.upsert_campaign_visibility_setting(
                campaign_slug,
                scope,
                visibility=selected_visibility,
                updated_by_user_id=user.id,
            )
            auth_store_instance.write_audit_event(
                event_type="campaign_visibility_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "scope": scope,
                    "visibility": selected_visibility,
                    "source": "campaign_control_panel",
                },
            )
            changed_scopes.append(dependencies.campaign_visibility_scope_labels[scope])

        dependencies.clear_campaign_visibility_cache(campaign_slug)
        if changed_scopes:
            flash(f"Updated visibility for {', '.join(changed_scopes)}.", "success")
        else:
            flash("Visibility settings already matched those values.", "success")
        return redirect(url_for("campaign_control_panel_view", campaign_slug=campaign_slug))

    app.add_url_rule(
        "/campaigns/<campaign_slug>/control-panel",
        endpoint="campaign_control_panel_view",
        view_func=dependencies.login_required(campaign_control_panel_view),
        methods=("GET",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/control-panel/visibility",
        endpoint="campaign_control_panel_update_visibility",
        view_func=dependencies.login_required(campaign_control_panel_update_visibility),
        methods=("POST",),
    )


def register_campaign_visibility_api_routes(
    api: Blueprint,
    *,
    dependencies: CampaignVisibilityApiDependencies,
) -> None:
    def campaign_control(campaign_slug: str):
        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        user = dependencies.get_current_user()
        include_private = bool(user and user.is_admin)
        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(campaign),
                "visibility_rows": [
                    dependencies.serialize_campaign_control_visibility_row(campaign_slug, scope)
                    for scope in dependencies.campaign_visibility_scopes
                ],
                "can_set_private_visibility": include_private,
                "rules": [
                    {"label": "Public", "description": "Anyone can see it."},
                    {"label": "Players", "description": "Only the DM and players in the campaign can see it."},
                    {"label": "DM", "description": "Only the campaign DM can see it."},
                    {"label": "Private", "description": "Only an app admin can see it."},
                ],
                "notes": [
                    "Campaign-level visibility acts as a floor for every campaign section.",
                    "Systems also apply source-level and article-level access rules on top of the Systems scope.",
                ]
                + (
                    []
                    if include_private
                    else ["Private visibility is reserved for admins even though admins can still access everything."]
                ),
                "links": {
                    "flask_control_url": url_for(
                        "campaign_control_panel_view",
                        campaign_slug=campaign_slug,
                    ),
                    "control_url": dependencies.flask_campaign_href(campaign_slug, "control-panel"),
                },
            }
        )

    def campaign_control_update_visibility(campaign_slug: str):
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        raw_visibility = payload.get("visibility")
        if not isinstance(raw_visibility, dict):
            return dependencies.json_error(
                "Visibility settings must be provided as an object.",
                400,
                code="validation_error",
            )

        auth_store_instance = dependencies.get_auth_store()
        changed_scopes: list[str] = []
        for scope in dependencies.campaign_visibility_scopes:
            current_visibility = auth_store_instance.get_campaign_visibility_setting(campaign_slug, scope)
            default_visibility = dependencies.get_campaign_default_scope_visibility(campaign_slug, scope)
            selected_visibility = dependencies.normalize_visibility_choice(
                str(
                    raw_visibility.get(
                        scope,
                        current_visibility.visibility if current_visibility is not None else default_visibility,
                    )
                    or ""
                )
            )
            if not dependencies.is_valid_visibility(selected_visibility):
                return dependencies.json_error(
                    f"Choose a valid visibility for {dependencies.campaign_visibility_scope_labels[scope]}.",
                    400,
                    code="validation_error",
                )
            if selected_visibility == dependencies.visibility_private and not user.is_admin:
                return dependencies.json_error(
                    "Private visibility is reserved for app admins.",
                    400,
                    code="validation_error",
                )

            if current_visibility is not None and current_visibility.visibility == selected_visibility:
                continue
            if current_visibility is None and default_visibility == selected_visibility:
                continue

            auth_store_instance.upsert_campaign_visibility_setting(
                campaign_slug,
                scope,
                visibility=selected_visibility,
                updated_by_user_id=user.id,
            )
            auth_store_instance.write_audit_event(
                event_type="campaign_visibility_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "scope": scope,
                    "visibility": selected_visibility,
                    "source": "campaign_control_api",
                },
            )
            changed_scopes.append(dependencies.campaign_visibility_scope_labels[scope])

        dependencies.clear_campaign_visibility_cache(campaign_slug)
        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(campaign),
                "visibility_rows": [
                    dependencies.serialize_campaign_control_visibility_row(campaign_slug, scope)
                    for scope in dependencies.campaign_visibility_scopes
                ],
                "changed_scopes": changed_scopes,
                "message": (
                    f"Updated visibility for {', '.join(changed_scopes)}."
                    if changed_scopes
                    else "Visibility settings already matched those values."
                ),
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/control",
        endpoint="campaign_control",
        view_func=dependencies.api_campaign_visibility_management_required(campaign_control),
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/control/visibility",
        endpoint="campaign_control_update_visibility",
        view_func=dependencies.api_campaign_visibility_management_required(
            campaign_control_update_visibility
        ),
        methods=("PATCH",),
    )
