from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, render_template, request

from .auth import (
    can_manage_campaign_dm_content,
    campaign_scope_access_required,
    get_auth_store,
    get_current_user,
)
from .campaign_dm_content_service import (
    CampaignDMContentValidationError,
    build_statblock_parser_feedback,
)
from .input_limits import MAX_MARKDOWN_BYTES, read_bounded_upload
from .system_policy import DND_5E_SYSTEM_CODE, supports_dnd5e_statblock_upload


dm_content = Blueprint("dm_content", __name__)


@dataclass(frozen=True)
class DMContentRouteDependencies:
    load_campaign: Callable[[str], Any]
    get_service: Callable[[], Any]
    build_page_context: Callable[..., dict[str, object]]
    redirect_to_dm_content: Callable[..., Any]


def _dependencies() -> DMContentRouteDependencies:
    return current_app.extensions["dm_content_route_dependencies"]


@campaign_scope_access_required("dm_content")
def campaign_dm_content_upload_statblock(campaign_slug: str):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    dependencies = _dependencies()
    campaign = dependencies.load_campaign(campaign_slug)
    if not supports_dnd5e_statblock_upload(campaign.system):
        flash(
            f"Statblock upload is only implemented for {DND_5E_SYSTEM_CODE} right now.",
            "error",
        )
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="statblocks",
            anchor="dm-content-statblocks",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    markdown_file = request.files.get("statblock_file")
    filename = (markdown_file.filename or "").strip() if markdown_file is not None else ""
    subsection = request.form.get("subsection", "")
    try:
        data_blob = (
            read_bounded_upload(
                markdown_file,
                max_bytes=MAX_MARKDOWN_BYTES,
                message="DM Content statblock files must stay under 1 MB.",
            )
            if markdown_file is not None
            else b""
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="statblocks",
            anchor="dm-content-statblocks",
        )
    try:
        statblock = dependencies.get_service().create_statblock(
            campaign_slug,
            filename=filename,
            data_blob=data_blob,
            subsection=subsection,
            created_by_user_id=user.id,
        )
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
    else:
        parser_feedback = build_statblock_parser_feedback(statblock)
        flash(f"Statblock saved to DM Content. {parser_feedback['summary']}", "success")

    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="statblocks",
        anchor="dm-content-statblocks",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_update_statblock(campaign_slug: str, statblock_id: int):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    body_markdown = request.form.get("body_markdown", "")
    subsection = request.form.get("subsection", "")
    try:
        statblock = dependencies.get_service().update_statblock(
            campaign_slug,
            statblock_id,
            body_markdown=body_markdown,
            subsection=subsection,
            updated_by_user_id=user.id,
        )
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
        context = dependencies.build_page_context(
            campaign_slug,
            dm_content_subpage="statblocks",
            dm_statblock_form_overrides={
                statblock_id: {
                    "subsection": subsection,
                    "body_markdown": body_markdown,
                }
            },
        )
        return render_template("dm_content.html", **context), 400

    parser_feedback = build_statblock_parser_feedback(statblock)
    get_auth_store().write_audit_event(
        event_type="campaign_dm_statblock_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "statblock_id": statblock.id,
            "title": statblock.title,
            "subsection": statblock.subsection,
            "source": "dm_content_statblocks",
            "parsed": {
                "armor_class": statblock.armor_class,
                "max_hp": statblock.max_hp,
                "movement_total": statblock.movement_total,
                "initiative_bonus": statblock.initiative_bonus,
            },
        },
    )
    flash(f"Statblock {statblock.title} updated. {parser_feedback['summary']}", "success")
    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="statblocks",
        anchor=f"dm-statblock-{statblock.id}",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_delete_statblock(campaign_slug: str, statblock_id: int):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    dependencies = _dependencies()
    try:
        deleted_statblock = dependencies.get_service().delete_statblock(campaign_slug, statblock_id)
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Deleted {deleted_statblock.title} from DM Content.", "success")

    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="statblocks",
        anchor="dm-content-statblocks",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_add_condition_definition(campaign_slug: str):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    name = request.form.get("name", "")
    description_markdown = request.form.get("description_markdown", "")
    try:
        dependencies.get_service().create_condition_definition(
            campaign_slug,
            name=name,
            description_markdown=description_markdown,
            created_by_user_id=user.id,
        )
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Custom condition saved to DM Content.", "success")

    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="conditions",
        anchor="dm-content-conditions",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_update_condition_definition(campaign_slug: str, condition_definition_id: int):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    name = request.form.get("name", "")
    description_markdown = request.form.get("description_markdown", "")
    try:
        condition_definition = dependencies.get_service().update_condition_definition(
            campaign_slug,
            condition_definition_id,
            name=name,
            description_markdown=description_markdown,
            updated_by_user_id=user.id,
        )
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
        context = dependencies.build_page_context(
            campaign_slug,
            dm_content_subpage="conditions",
            dm_condition_form_overrides={
                condition_definition_id: {
                    "name": name,
                    "description_markdown": description_markdown,
                }
            },
        )
        return render_template("dm_content.html", **context), 400

    get_auth_store().write_audit_event(
        event_type="campaign_dm_condition_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "condition_definition_id": condition_definition.id,
            "name": condition_definition.name,
            "source": "dm_content_conditions",
        },
    )
    flash(f"Custom condition {condition_definition.name} updated.", "success")
    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="conditions",
        anchor=f"dm-condition-{condition_definition.id}",
    )


@campaign_scope_access_required("dm_content")
def campaign_dm_content_delete_condition_definition(campaign_slug: str, condition_definition_id: int):
    if not can_manage_campaign_dm_content(campaign_slug):
        abort(403)

    dependencies = _dependencies()
    try:
        deleted_definition = dependencies.get_service().delete_condition_definition(
            campaign_slug,
            condition_definition_id,
        )
    except CampaignDMContentValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Deleted custom condition {deleted_definition.name}.", "success")

    return dependencies.redirect_to_dm_content(
        campaign_slug,
        subpage="conditions",
        anchor="dm-content-conditions",
    )


@dm_content.record_once
def _register_legacy_endpoints(state: Any) -> None:
    registrations = (
        (
            "/campaigns/<campaign_slug>/dm-content/statblocks",
            "campaign_dm_content_upload_statblock",
            campaign_dm_content_upload_statblock,
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>",
            "campaign_dm_content_update_statblock",
            campaign_dm_content_update_statblock,
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>/delete",
            "campaign_dm_content_delete_statblock",
            campaign_dm_content_delete_statblock,
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/conditions",
            "campaign_dm_content_add_condition_definition",
            campaign_dm_content_add_condition_definition,
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>",
            "campaign_dm_content_update_condition_definition",
            campaign_dm_content_update_condition_definition,
        ),
        (
            "/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>/delete",
            "campaign_dm_content_delete_condition_definition",
            campaign_dm_content_delete_condition_definition,
        ),
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=("POST",))


def register_dm_content_routes(
    app: Any,
    *,
    load_campaign: Callable[[str], Any],
    get_service: Callable[[], Any],
    build_page_context: Callable[..., dict[str, object]],
    redirect_to_dm_content: Callable[..., Any],
) -> None:
    app.extensions["dm_content_route_dependencies"] = DMContentRouteDependencies(
        load_campaign=load_campaign,
        get_service=get_service,
        build_page_context=build_page_context,
        redirect_to_dm_content=redirect_to_dm_content,
    )
    app.register_blueprint(dm_content)
