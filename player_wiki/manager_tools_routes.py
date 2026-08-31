from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Flask, abort, make_response, render_template, url_for

from .campaign_combat_preset_service import (
    CampaignCombatPresetAuthorizationError,
)
from .session_readiness_presenter import (
    present_active_session,
    present_encounter_presets,
    present_session_characters,
    present_session_content,
    present_source_health,
    unavailable_row,
)


MANAGER_TOOLS_HTML_MAX_BYTES = 65_536
MANAGER_TOOLS_PRESET_SUMMARY_LIMIT = 26
SESSION_READINESS_CHARACTER_LIMIT = 50


@dataclass(frozen=True)
class ManagerToolsRouteDependencies:
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_campaign_context: Callable[[str], Any]
    can_manage_campaign_content: Callable[[str], bool]
    can_access_campaign_scope: Callable[[str, str], bool]
    can_manage_campaign_session: Callable[[str], bool]
    can_manage_campaign_combat: Callable[[str], bool]
    campaign_supports_native_character_tools: Callable[[Any], bool]
    campaign_supports_combat_tracker: Callable[[Any], bool]
    count_campaign_combat_presets: Callable[..., int]
    summarize_session_readiness_characters: Callable[..., Any]
    summarize_session_readiness_assignments: Callable[..., Any]
    get_session_readiness_summary: Callable[..., Any]
    build_source_health_report: Callable[..., Any]


def _present_preset_count(count: int) -> str:
    if count <= 0:
        return "No saved encounters"
    if count == 1:
        return "1 saved encounter"
    if count >= MANAGER_TOOLS_PRESET_SUMMARY_LIMIT:
        return "25+ saved encounters"
    return f"{count} saved encounters"


def register_manager_tools_routes(
    app: Flask,
    *,
    dependencies: ManagerToolsRouteDependencies,
) -> None:
    def campaign_manager_tools_view(campaign_slug: str):
        campaign = dependencies.load_campaign_context(campaign_slug)
        if not dependencies.can_manage_campaign_content(campaign_slug):
            abort(403)

        cards: list[dict[str, str]] = []
        can_manage_session = dependencies.can_manage_campaign_session(campaign_slug)
        if (
            dependencies.can_access_campaign_scope(campaign_slug, "characters")
            and can_manage_session
            and dependencies.campaign_supports_native_character_tools(campaign)
        ):
            cards.append(
                {
                    "slug": "character-updates",
                    "title": "Character Updates",
                    "state": "Available for D&D 5E characters.",
                    "description": "Choose a character to open its available update tools.",
                    "action": "Choose a Character",
                    "href": url_for(
                        "character_roster_view",
                        campaign_slug=campaign_slug,
                    ),
                }
            )

        if can_manage_session:
            cards.append(
                {
                    "slug": "session-readiness",
                    "title": "Session Readiness",
                    "state": "Five independent checks",
                    "description": "Review current Session setup across each owning workflow.",
                    "action": "Review Session Readiness",
                    "href": url_for(
                        "campaign_session_readiness_view",
                        campaign_slug=campaign_slug,
                    ),
                }
            )
            cards.append(
                {
                    "slug": "session-closeouts",
                    "title": "Session Closeouts",
                    "state": "Available",
                    "description": "Resume post-Session checklists or review completed closeouts.",
                    "action": "Open Session Closeouts",
                    "href": url_for(
                        "campaign_session_closeouts_view",
                        campaign_slug=campaign_slug,
                    ),
                }
            )

        if (
            dependencies.can_manage_campaign_combat(campaign_slug)
            and dependencies.campaign_supports_combat_tracker(campaign)
        ):
            try:
                preset_count = dependencies.count_campaign_combat_presets(
                    campaign_slug,
                    limit=MANAGER_TOOLS_PRESET_SUMMARY_LIMIT,
                )
            except CampaignCombatPresetAuthorizationError:
                pass
            except Exception:
                cards.append(
                    {
                        "slug": "encounter-presets",
                        "title": "Encounter Presets",
                        "state": "Count unavailable",
                        "description": "Open saved encounters to inspect the current preset list.",
                        "action": "Open Encounter Presets",
                        "href": url_for(
                            "campaign_combat_dm_view",
                            campaign_slug=campaign_slug,
                            view="controls",
                            _anchor="saved-encounters",
                        ),
                    }
                )
            else:
                cards.append(
                    {
                        "slug": "encounter-presets",
                        "title": "Encounter Presets",
                        "state": _present_preset_count(preset_count),
                        "description": "Open saved encounters to inspect the current preset list.",
                        "action": "Open Encounter Presets",
                        "href": url_for(
                            "campaign_combat_dm_view",
                            campaign_slug=campaign_slug,
                            view="controls",
                            _anchor="saved-encounters",
                        ),
                    }
                )

        cards.append(
            {
                "slug": "source-health",
                "title": "Source Health",
                "state": "Available",
                "description": "Open the read-only source diagnostic when you need it.",
                "action": "Open Source Health",
                "href": url_for(
                    "campaign_source_health_view",
                    campaign_slug=campaign_slug,
                ),
            }
        )

        response = make_response(
            render_template(
                "manager_tools.html",
                campaign=campaign,
                manager_tool_cards=tuple(cards),
                active_nav="manager_tools",
            )
        )
        if len(response.get_data()) > MANAGER_TOOLS_HTML_MAX_BYTES:
            abort(500)
        return response

    def campaign_session_readiness_view(campaign_slug: str):
        campaign = dependencies.load_campaign_context(campaign_slug)
        if not dependencies.can_manage_campaign_content(campaign_slug):
            abort(403)
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        active_session_href = url_for(
            "campaign_session_dm_view",
            campaign_slug=campaign_slug,
            dm_view="tools",
        )
        session_characters_href = url_for(
            "campaign_session_character_view",
            campaign_slug=campaign_slug,
        )
        session_content_href = url_for(
            "campaign_session_dm_view",
            campaign_slug=campaign_slug,
            dm_view="staged",
        )
        source_health_href = url_for(
            "campaign_source_health_view",
            campaign_slug=campaign_slug,
        )
        encounter_presets_href = url_for(
            "campaign_combat_dm_view",
            campaign_slug=campaign_slug,
            view="controls",
            _anchor="saved-encounters",
        )

        try:
            session_summary = dependencies.get_session_readiness_summary(
                campaign_slug,
                count_limit=MANAGER_TOOLS_PRESET_SUMMARY_LIMIT,
            )
        except Exception:
            active_session_row = unavailable_row(
                slug="active-session",
                title="Active Session",
                action="Open Session controls",
                href=active_session_href,
            )
            session_content_row = unavailable_row(
                slug="session-content",
                title="Session content",
                action="Open Session content",
                href=session_content_href,
            )
        else:
            active_session_row = present_active_session(
                session_summary.active_started_at,
                href=active_session_href,
            )
            session_content_row = present_session_content(
                staged_count=session_summary.staged_count,
                revealed_count=session_summary.revealed_count,
                href=session_content_href,
            )

        if not dependencies.can_access_campaign_scope(campaign_slug, "characters"):
            session_characters_row = unavailable_row(
                slug="session-characters",
                title="Session Characters",
                action="Open Session Characters",
                href=session_characters_href,
            )
        else:
            try:
                character_summary = (
                    dependencies.summarize_session_readiness_characters(
                        campaign_slug,
                        limit=SESSION_READINESS_CHARACTER_LIMIT,
                        initialize_missing_state=False,
                    )
                )
                assignment_summary = (
                    dependencies.summarize_session_readiness_assignments(
                        campaign_slug,
                        available_character_slugs=(
                            character_summary.available_character_slugs
                        ),
                        limit=SESSION_READINESS_CHARACTER_LIMIT + 1,
                    )
                )
            except Exception:
                session_characters_row = unavailable_row(
                    slug="session-characters",
                    title="Session Characters",
                    action="Open Session Characters",
                    href=session_characters_href,
                )
            else:
                session_characters_row = present_session_characters(
                    available_count=len(
                        character_summary.available_character_slugs
                    ),
                    valid_assignment_count=(
                        assignment_summary.valid_assignment_count
                    ),
                    has_dangling_assignments=(
                        assignment_summary.has_dangling_assignments
                    ),
                    href=session_characters_href,
                )

        try:
            source_health_report = dependencies.build_source_health_report(
                campaign_slug,
            )
        except Exception:
            source_health_row = unavailable_row(
                slug="source-health",
                title="Source Health",
                action="Open Source Health",
                href=source_health_href,
            )
        else:
            source_health_row = present_source_health(
                report_state=source_health_report.state,
                complete=source_health_report.complete,
                href=source_health_href,
            )

        combat_supported = dependencies.campaign_supports_combat_tracker(campaign)
        if not combat_supported:
            encounter_presets_row = present_encounter_presets(
                count=0,
                supported=False,
                href=encounter_presets_href,
            )
        elif not dependencies.can_manage_campaign_combat(campaign_slug):
            encounter_presets_row = unavailable_row(
                slug="encounter-presets",
                title="Encounter Presets",
                action="Open Encounter Presets",
                href=encounter_presets_href,
            )
        else:
            try:
                preset_count = dependencies.count_campaign_combat_presets(
                    campaign_slug,
                    limit=MANAGER_TOOLS_PRESET_SUMMARY_LIMIT,
                )
            except Exception:
                encounter_presets_row = unavailable_row(
                    slug="encounter-presets",
                    title="Encounter Presets",
                    action="Open Encounter Presets",
                    href=encounter_presets_href,
                )
            else:
                encounter_presets_row = present_encounter_presets(
                    count=preset_count,
                    supported=True,
                    href=encounter_presets_href,
                )

        rows = (
            active_session_row,
            session_characters_row,
            session_content_row,
            source_health_row,
            encounter_presets_row,
        )
        response = make_response(
            render_template(
                "session_readiness.html",
                campaign=campaign,
                readiness_rows=rows,
                active_nav="manager_tools",
            )
        )
        if len(response.get_data()) > MANAGER_TOOLS_HTML_MAX_BYTES:
            abort(500)
        return response

    app.add_url_rule(
        "/campaigns/<campaign_slug>/manager-tools",
        endpoint="campaign_manager_tools_view",
        view_func=dependencies.login_required(campaign_manager_tools_view),
        methods=("GET",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/manager-tools/session-readiness",
        endpoint="campaign_session_readiness_view",
        view_func=dependencies.login_required(campaign_session_readiness_view),
        methods=("GET",),
    )
