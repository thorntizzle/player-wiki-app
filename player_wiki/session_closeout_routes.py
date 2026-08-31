from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Flask, abort, flash, make_response, redirect, render_template, request, url_for

from .campaign_session_service import (
    CampaignSessionCloseoutAuthorizationError,
    CampaignSessionCloseoutConflictError,
    CampaignSessionCloseoutValidationError,
)
from .session_closeout_presenter import (
    is_known_closeout_item_key,
    present_closeout,
    present_closeout_session,
    present_closeout_summaries,
)


SESSION_CLOSEOUT_HTML_MAX_BYTES = 65_536
SESSION_CLOSEOUT_SUMMARY_LIMIT = 26


@dataclass(frozen=True)
class SessionCloseoutRouteDependencies:
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_campaign_context: Callable[[str], Any]
    get_closeout_service: Callable[[], Any]
    get_session_service: Callable[[], Any]
    can_manage_campaign_content: Callable[[str], bool]
    can_manage_campaign_session: Callable[[str], bool]
    can_access_campaign_scope: Callable[[str, str], bool]
    can_manage_campaign_combat: Callable[[str], bool]
    can_manage_campaign_dm_content: Callable[[str], bool]
    campaign_supports_combat_tracker: Callable[[Any], bool]
    is_read_only_request: Callable[[], bool]
    has_real_actor: Callable[[], bool]
    render_session_log_detail: Callable[..., Any]


def register_session_closeout_routes(
    app: Flask,
    *,
    dependencies: SessionCloseoutRouteDependencies,
) -> None:
    def authorize(campaign_slug: str, *, mutation: bool) -> None:
        if not dependencies.can_manage_campaign_content(campaign_slug):
            abort(403)
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)
        if mutation and (
            dependencies.is_read_only_request() or not dependencies.has_real_actor()
        ):
            abort(403)

    def owner_links(campaign_slug: str, campaign: Any) -> dict[str, dict[str, str]]:
        session_log_link = {
            "label": "View stored Session log",
            "unavailable": "The stored Session log is unavailable.",
        }
        characters = {
            "label": "Open Character roster",
            "unavailable": (
                "Character tools are not available to this viewer. Resolve this item at the table when needed."
            ),
        }
        if dependencies.can_access_campaign_scope(campaign_slug, "characters"):
            characters["href"] = url_for(
                "character_roster_view",
                campaign_slug=campaign_slug,
            )

        combat = {
            "label": "Open Combat DM controls",
            "unavailable": (
                "Combat DM controls are not available for this campaign or viewer. This item can still be resolved here."
            ),
        }
        if (
            dependencies.can_manage_campaign_combat(campaign_slug)
            and dependencies.campaign_supports_combat_tracker(campaign)
        ):
            combat["href"] = url_for(
                "campaign_combat_dm_view",
                campaign_slug=campaign_slug,
                view="controls",
                _anchor="combat-tracker",
            )

        dm_content = {
            "label": "Open DM Content Player Wiki",
            "unavailable": (
                "DM Content Player Wiki tools are not available to this viewer. This item can still be resolved here."
            ),
        }
        if dependencies.can_manage_campaign_dm_content(campaign_slug):
            dm_content["href"] = url_for(
                "campaign_dm_content_subpage_view",
                campaign_slug=campaign_slug,
                dm_content_subpage="player-wiki",
                _anchor="dm-content-player-wiki-pages",
            )
        return {
            "session_log": session_log_link,
            "characters": characters,
            "combat": combat,
            "dm_content": dm_content,
        }

    def render_detail(
        campaign_slug: str,
        session_id: int,
        *,
        status_code: int = 200,
        affected_item_key: str = "",
        draft_status: str = "",
        draft_note: str = "",
        item_error: str = "",
        stale_conflict: bool = False,
        lifecycle_error: str = "",
        lifecycle_focus: str = "",
    ):
        campaign = dependencies.load_campaign_context(campaign_slug)
        closeout_service = dependencies.get_closeout_service()
        try:
            closeout = closeout_service.get_closeout(campaign_slug, session_id)
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        if closeout is None:
            abort(404)
        session_record = dependencies.get_session_service().get_session_log(
            campaign_slug,
            session_id,
        )
        if session_record is None or session_record.is_active:
            abort(404)

        links = owner_links(campaign_slug, campaign)
        links["session_log"]["href"] = url_for(
            "campaign_session_log_view",
            campaign_slug=campaign_slug,
            session_id=session_id,
        )
        response = make_response(
            render_template(
                "session_closeout.html",
                campaign=campaign,
                session_header=present_closeout_session(session_record),
                closeout=present_closeout(
                    closeout,
                    owner_links=links,
                    read_only=dependencies.is_read_only_request(),
                    affected_item_key=affected_item_key,
                    draft_status=draft_status,
                    draft_note=draft_note,
                    item_error=item_error,
                    stale_conflict=stale_conflict,
                    lifecycle_error=lifecycle_error,
                    lifecycle_focus=lifecycle_focus,
                ),
                active_nav="manager_tools",
            ),
            status_code,
        )
        if len(response.get_data()) > SESSION_CLOSEOUT_HTML_MAX_BYTES:
            abort(500)
        return response

    def campaign_session_closeouts_view(campaign_slug: str):
        authorize(campaign_slug, mutation=False)
        campaign = dependencies.load_campaign_context(campaign_slug)
        try:
            summaries = dependencies.get_closeout_service().list_summaries(
                campaign_slug,
                limit=SESSION_CLOSEOUT_SUMMARY_LIMIT,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        response = make_response(
            render_template(
                "session_closeouts.html",
                campaign=campaign,
                closeout_summaries=present_closeout_summaries(
                    summaries,
                    detail_url_builder=lambda session_id: url_for(
                        "campaign_session_closeout_view",
                        campaign_slug=campaign_slug,
                        session_id=session_id,
                    ),
                ),
                read_only=dependencies.is_read_only_request(),
                active_nav="manager_tools",
            )
        )
        if len(response.get_data()) > SESSION_CLOSEOUT_HTML_MAX_BYTES:
            abort(500)
        return response

    def campaign_session_closeout_view(campaign_slug: str, session_id: int):
        authorize(campaign_slug, mutation=False)
        return render_detail(campaign_slug, session_id)

    def campaign_session_closeout_open(campaign_slug: str, session_id: int):
        authorize(campaign_slug, mutation=True)
        try:
            result = dependencies.get_closeout_service().open_or_create(
                campaign_slug,
                session_id,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        except CampaignSessionCloseoutValidationError:
            abort(404)
        flash(
            "Session closeout started." if result.created else "Session closeout opened.",
            "success",
        )
        return redirect(
            url_for(
                "campaign_session_closeout_view",
                campaign_slug=campaign_slug,
                session_id=session_id,
            ),
            code=303,
        )

    def campaign_session_closeout_item_update(
        campaign_slug: str,
        session_id: int,
        item_key: str,
    ):
        authorize(campaign_slug, mutation=True)
        if not is_known_closeout_item_key(item_key):
            abort(404)
        expected_revision = request.form.get("expected_revision", "")
        draft_status = request.form.get("status", "")
        draft_note = request.form.get("note", "")
        try:
            dependencies.get_closeout_service().update_item(
                campaign_slug,
                session_id,
                expected_revision=expected_revision,
                item_key=item_key,
                status=draft_status,
                note=draft_note,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        except CampaignSessionCloseoutConflictError:
            return render_detail(
                campaign_slug,
                session_id,
                status_code=409,
                affected_item_key=item_key,
                draft_status=draft_status,
                draft_note=draft_note,
                item_error=(
                    "This closeout changed in another tab. Compare the current saved value with your draft before saving again."
                ),
                stale_conflict=True,
            )
        except CampaignSessionCloseoutValidationError as exc:
            return render_detail(
                campaign_slug,
                session_id,
                status_code=400,
                affected_item_key=item_key,
                draft_status=draft_status,
                draft_note=draft_note,
                item_error=str(exc),
            )
        flash("Session closeout item saved.", "success")
        item_number = next(
            index
            for index, key in enumerate(
                (
                    "table_notes",
                    "character_rests",
                    "rewards_and_boons",
                    "encounter_disposition",
                    "session_article_publication",
                    "external_archive",
                ),
                start=1,
            )
            if key == item_key
        )
        return redirect(
            url_for(
                "campaign_session_closeout_view",
                campaign_slug=campaign_slug,
                session_id=session_id,
                _anchor=f"closeout-item-{item_number}",
            ),
            code=303,
        )

    def campaign_session_closeout_complete(campaign_slug: str, session_id: int):
        authorize(campaign_slug, mutation=True)
        expected_revision = request.form.get("expected_revision", "")
        try:
            dependencies.get_closeout_service().complete(
                campaign_slug,
                session_id,
                expected_revision=expected_revision,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        except CampaignSessionCloseoutConflictError:
            return render_detail(
                campaign_slug,
                session_id,
                status_code=409,
                lifecycle_error=(
                    "This closeout changed after you opened it. Review the current items before completing it."
                ),
                lifecycle_focus="complete",
            )
        except CampaignSessionCloseoutValidationError as exc:
            lifecycle_error = str(exc)
            if lifecycle_error == "Resolve every Session closeout item before completion.":
                lifecycle_error = "Resolve all six items before completion."
            return render_detail(
                campaign_slug,
                session_id,
                status_code=400,
                lifecycle_error=lifecycle_error,
                lifecycle_focus="complete",
            )
        flash("Session closeout completed.", "success")
        return redirect(
            url_for(
                "campaign_session_closeout_view",
                campaign_slug=campaign_slug,
                session_id=session_id,
                _anchor="closeout-lifecycle",
            ),
            code=303,
        )

    def campaign_session_closeout_reopen(campaign_slug: str, session_id: int):
        authorize(campaign_slug, mutation=True)
        expected_revision = request.form.get("expected_revision", "")
        try:
            dependencies.get_closeout_service().reopen(
                campaign_slug,
                session_id,
                expected_revision=expected_revision,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        except CampaignSessionCloseoutConflictError:
            return render_detail(
                campaign_slug,
                session_id,
                status_code=409,
                lifecycle_error=(
                    "This closeout changed after you opened it. Review the current state before reopening it."
                ),
                lifecycle_focus="reopen",
            )
        except CampaignSessionCloseoutValidationError as exc:
            return render_detail(
                campaign_slug,
                session_id,
                status_code=400,
                lifecycle_error=str(exc),
                lifecycle_focus="reopen",
            )
        flash("Session closeout reopened with its saved item values.", "success")
        return redirect(
            url_for(
                "campaign_session_closeout_view",
                campaign_slug=campaign_slug,
                session_id=session_id,
                _anchor="closeout-lifecycle",
            ),
            code=303,
        )

    def campaign_session_closeout_delete_session_history(
        campaign_slug: str,
        session_id: int,
    ):
        authorize(campaign_slug, mutation=True)
        acknowledgement = request.form.get("destructive_acknowledgement", "")
        expected_revision = request.form.get("expected_revision", "")
        if acknowledgement != "1":
            return dependencies.render_session_log_detail(
                campaign_slug,
                session_id,
                status_code=400,
                deletion_error=(
                    "Confirm that you understand this permanently deletes the closeout and stored Session history."
                ),
            )
        try:
            dependencies.get_closeout_service().delete_confirmed_session_history(
                campaign_slug,
                session_id,
                expected_revision=expected_revision,
            )
        except CampaignSessionCloseoutAuthorizationError:
            abort(403)
        except CampaignSessionCloseoutConflictError:
            return dependencies.render_session_log_detail(
                campaign_slug,
                session_id,
                status_code=409,
                deletion_error=(
                    "This closeout changed after you opened the confirmation. Review the current closeout before deleting it."
                ),
            )
        except CampaignSessionCloseoutValidationError as exc:
            return dependencies.render_session_log_detail(
                campaign_slug,
                session_id,
                status_code=400,
                deletion_error=str(exc),
            )
        flash("Session closeout and stored Session history deleted.", "success")
        return redirect(
            url_for(
                "campaign_session_closeouts_view",
                campaign_slug=campaign_slug,
            ),
            code=303,
        )

    registrations = (
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts",
            "campaign_session_closeouts_view",
            campaign_session_closeouts_view,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>",
            "campaign_session_closeout_view",
            campaign_session_closeout_view,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>/open",
            "campaign_session_closeout_open",
            campaign_session_closeout_open,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>/items/<item_key>",
            "campaign_session_closeout_item_update",
            campaign_session_closeout_item_update,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>/complete",
            "campaign_session_closeout_complete",
            campaign_session_closeout_complete,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>/reopen",
            "campaign_session_closeout_reopen",
            campaign_session_closeout_reopen,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/manager-tools/session-closeouts/<int:session_id>/delete-session-history",
            "campaign_session_closeout_delete_session_history",
            campaign_session_closeout_delete_session_history,
            ("POST",),
        ),
    )
    for rule, endpoint, handler, methods in registrations:
        app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=dependencies.login_required(handler),
            methods=methods,
        )
