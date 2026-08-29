from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Flask, abort, make_response, render_template, url_for

from .campaign_combat_preset_service import (
    CampaignCombatPresetAuthorizationError,
)


MANAGER_TOOLS_HTML_MAX_BYTES = 65_536
MANAGER_TOOLS_PRESET_SUMMARY_LIMIT = 26


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
        if (
            dependencies.can_access_campaign_scope(campaign_slug, "characters")
            and dependencies.can_manage_campaign_session(campaign_slug)
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

        if dependencies.can_manage_campaign_content(campaign_slug):
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

    app.add_url_rule(
        "/campaigns/<campaign_slug>/manager-tools",
        endpoint="campaign_manager_tools_view",
        view_func=dependencies.login_required(campaign_manager_tools_view),
        methods=("GET",),
    )
