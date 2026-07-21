from __future__ import annotations

from typing import Any

from flask import url_for

from .auth import (
    can_access_campaign_scope,
    can_manage_campaign_combat,
    can_manage_campaign_session,
    can_manage_campaign_systems,
    can_manage_campaign_visibility,
    can_post_campaign_session_messages,
    get_campaign_role,
    get_current_user,
    get_effective_campaign_visibility,
)
from .campaign_visibility import (
    CAMPAIGN_VISIBILITY_SCOPE_LABELS,
    CAMPAIGN_VISIBILITY_SCOPES,
    VISIBILITY_LABELS,
)
from .system_policy import DND_5E_SYSTEM_CODE, supports_combat_tracker, supports_native_character_tools

SESSION_CHARACTER_ACTIVE_EDIT_SCOPE = (
    "Vitals and rests on Overview",
    "Tracked resource counts and spell slot usage",
    "Equipment state for equip/unequip, attunement, and weapon wielding",
    "Inventory quantities and currency totals",
    "Player notes",
)
SESSION_CHARACTER_ACTIVE_EDIT_SUMMARY = (
    "Vitals, rests, tracked resources, spell slots, equipment state, inventory quantities, currency, and player notes"
)
CHARACTER_SHEET_EDIT_FIRST_PASS_SCOPE = (
    "Current HP, temp HP, tracked resources, and spell slot usage",
    "Equipment state for equip/unequip, attunement, and weapon wielding",
    "Inventory quantities and currency totals",
    "Player notes",
)
CHARACTER_SHEET_EDIT_OUTSIDE_FIRST_PASS_SCOPE = (
    "Rests and other relative quick actions",
    "Spell-list changes and other non-slot spell management",
    "Profile text (physical description, background), Portrait page changes, and broader inventory/equipment maintenance",
    "Advanced character edit, level-up, retraining, and controls",
)
SESSION_CHARACTER_FULL_PAGE_ONLY_SCOPE = (
    "Portrait management on Character Portrait, and physical description/background in Advanced Editor",
    "Spell-list changes and other non-slot spell management",
    "Inventory add/remove work and other equipment maintenance beyond equipped, attuned, or wielding state",
    "Advanced character edit, level-up, retraining, and controls",
)
SESSION_CHARACTER_FULL_PAGE_ONLY_SUMMARY = (
    "Portrait page management, Advanced Editor reference text, spell-list changes, inventory add/remove work, and advanced maintenance"
)
CHARACTER_SHEET_EDIT_ACCESS_RULES = (
    "Assigned player owners can use inline Character-page state edits for their own characters.",
    "DMs can use the same inline state edits on managed characters.",
    "Admins can always use inline state edits and Advanced Editor. Owner assignment stays admin-only on Controls, and character deletion stays on Controls for DM/admin users.",
    "Observers and unassigned players stay on the standard Character page without inline state-edit affordances.",
)
COMBAT_AND_SESSION_COMBAT_SCOPE = (
    "Turn order and encounter context",
    "Movement and action economy",
    "Conditions and other tactical state",
)
COMBAT_AND_SESSION_SESSION_SCOPE = (
    "Chat, revealed articles, and wiki lookup on the main Session page",
    "HP, temp HP, tracked resources, spell slot usage, rests, inventory quantities, currency, and notes",
    "Broader in-play character reference outside the encounter view",
)
COMBAT_AND_SESSION_SESSION_SUMMARY = (
    "the broader live-session workflow, rests, inventory quantities, currency, and player notes, plus HP/temp HP, tracked resources, and spell slot usage"
)


def build_help_surface(
    *,
    anchor: str,
    label: str,
    summary: str,
    status_label: str,
    access_note: str,
    capabilities: list[str],
    limits: list[str],
    links: list[dict[str, str]] | None = None,
    guidance_cards: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "anchor": anchor,
        "label": label,
        "summary": summary,
        "status_label": status_label,
        "access_note": access_note,
        "capabilities": capabilities,
        "limits": limits,
        "links": list(links or []),
        "guidance_cards": list(guidance_cards or []),
    }


def format_help_label_list(labels: list[str]) -> str:
    normalized_labels = [str(label).strip() for label in labels if str(label).strip()]
    if not normalized_labels:
        return ""
    if len(normalized_labels) == 1:
        return normalized_labels[0]
    if len(normalized_labels) == 2:
        return f"{normalized_labels[0]} and {normalized_labels[1]}"
    return f"{', '.join(normalized_labels[:-1])}, and {normalized_labels[-1]}"


def build_campaign_help_viewer_context(campaign_slug: str) -> dict[str, str]:
    current_user = get_current_user()
    role = get_campaign_role(campaign_slug)
    if current_user is not None and current_user.is_admin:
        return {
            "role_label": "Admin",
            "role_summary": (
                "Admins can open every campaign surface even when the normal visibility "
                "floor would hide it for other viewers."
            ),
        }
    if role == "dm":
        return {
            "role_label": "Dungeon Master",
            "role_summary": (
                "DMs can use the player-facing surfaces plus campaign management routes "
                "such as Session DM, Encounter status, Encounter controls, DM Content, "
                "and Control."
            ),
        }
    if role == "player":
        return {
            "role_label": "Player",
            "role_summary": (
                "Players can use the currently visible campaign surfaces, but write "
                "actions stay limited to the character and encounter workflows the app "
                "explicitly allows."
            ),
        }
    if role == "observer":
        return {
            "role_label": "Observer",
            "role_summary": (
                "Observers can read only the surfaces whose current visibility allows "
                "them, while live posting and GM management stay disabled."
            ),
        }
    if current_user is not None:
        return {
            "role_label": "Signed-in visitor",
            "role_summary": (
                "This account does not currently have an active membership in this "
                "campaign, so only the public surfaces are available."
            ),
        }
    return {
        "role_label": "Public visitor",
        "role_summary": (
            "You are viewing the public portion of this campaign. Member-only surfaces "
            "stay hidden until you sign in with the right campaign access."
        ),
    }


def build_campaign_help_context(campaign_slug: str, *, campaign: object) -> dict[str, object]:
    viewer_context = build_campaign_help_viewer_context(campaign_slug)
    current_user = get_current_user()

    wiki_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "wiki")]
    systems_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "systems")]
    session_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "session")]
    combat_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "combat")]
    dm_content_visibility_label = VISIBILITY_LABELS[
        get_effective_campaign_visibility(campaign_slug, "dm_content")
    ]
    characters_visibility_label = VISIBILITY_LABELS[
        get_effective_campaign_visibility(campaign_slug, "characters")
    ]

    can_view_wiki = can_access_campaign_scope(campaign_slug, "wiki")
    can_view_systems = can_access_campaign_scope(campaign_slug, "systems")
    can_view_session = can_access_campaign_scope(campaign_slug, "session")
    can_view_combat = can_access_campaign_scope(campaign_slug, "combat")
    can_view_dm_content = can_access_campaign_scope(campaign_slug, "dm_content")
    can_view_characters = can_access_campaign_scope(campaign_slug, "characters")

    can_manage_systems = can_manage_campaign_systems(campaign_slug)
    can_manage_session = can_manage_campaign_session(campaign_slug)
    can_manage_combat = can_manage_campaign_combat(campaign_slug)
    can_manage_visibility = can_manage_campaign_visibility(campaign_slug)

    native_character_tools_supported = supports_native_character_tools(getattr(campaign, "system", ""))
    combat_system_supported = supports_combat_tracker(campaign.system)
    system_label = str(getattr(campaign, "system", "") or "").strip() or "Unspecified"
    combat_source_seed_capability = (
        "NPC combatants can be seeded from Systems monsters and DM Content statblocks when those source libraries are available."
    )
    if can_view_systems and not can_view_dm_content:
        combat_source_seed_capability = (
            "Systems monsters can seed NPC combatants when that library is available to this viewer."
        )
    elif can_view_dm_content and not can_view_systems:
        combat_source_seed_capability = (
            "DM Content statblocks can seed NPC combatants when that library is available to this viewer."
        )
    elif not can_view_systems and not can_view_dm_content:
        combat_source_seed_capability = (
            "NPC combatants can be added from linked source libraries when those sources are available to this viewer."
        )
    character_guidance_cards: list[dict[str, object]] = [
        {
            "title": "Inline state edits on the Character page",
            "body": (
                "Use the normal Character page for quick session-backed field edits. "
                "These edits save immediately per form and stay on the Character page rather than opening a separate edit mode."
            ),
            "items": list(CHARACTER_SHEET_EDIT_FIRST_PASS_SCOPE),
            "meta": (
                "Use Advanced Editor for durable edits to spell lists and broader equipment or character maintenance."
            ),
        },
        {
            "title": "Keep the full character page for",
            "body": "",
            "items": list(CHARACTER_SHEET_EDIT_OUTSIDE_FIRST_PASS_SCOPE),
            "meta": "",
        },
    ]
    if can_view_session:
        character_guidance_cards.append(
            {
                "title": "Session Character",
                "body": "Use Session Character during an active session when you need live-play edits without leaving the Session feature.",
                "items": list(SESSION_CHARACTER_ACTIVE_EDIT_SCOPE),
                "meta": (
                    "Keep the full character page for "
                    f"{SESSION_CHARACTER_FULL_PAGE_ONLY_SUMMARY.lower()}."
                ),
            }
        )
    if can_view_combat:
        character_guidance_cards.append(
            {
                "title": "Combat",
                "body": "Use Combat when the character is in the tracker and encounter context matters.",
                "items": list(COMBAT_AND_SESSION_COMBAT_SCOPE),
                "meta": f"Keep Session for {COMBAT_AND_SESSION_SESSION_SUMMARY}.",
            }
        )
    character_guidance_cards.extend(
        [
            {
                "title": "Who can use inline state edits",
                "body": "",
                "items": list(CHARACTER_SHEET_EDIT_ACCESS_RULES),
                "meta": "",
            },
            {
                "title": "Compatibility note",
                "body": (
                    "`?mode=session` is a compatibility alias for the standard Character page. "
                    "Legacy links such as `?mode=session&page=...` still resolve to the requested Character-page view instead "
                    "of switching to a separate edit lane."
                ),
                "items": [],
                "meta": "",
            },
        ]
    )

    help_surfaces = [
        build_help_surface(
            anchor="campaign-home",
            label="Campaign Home",
            summary="Published player-facing wiki hub and header search.",
            status_label="Open" if can_view_wiki else "Limited",
            access_note=(
                f"You can browse published wiki content here. Current Wiki visibility: {wiki_visibility_label}."
                if can_view_wiki
                else (
                    "You can still open the campaign shell, but published wiki browsing "
                    f"currently requires {wiki_visibility_label} access."
                )
            ),
            capabilities=[
                "Browse published sections and article pages from the campaign hub.",
                "Use the header search to match titles, aliases, summaries, and page body text.",
                "Treat this as the safest player-facing starting point for campaign reference.",
            ],
            limits=[
                "Only published player-safe content appears here.",
                "GM vault notes, Inbox drafts, and other unpublished material do not surface here.",
                "This route is read-only; publishing and reveal timing happen on other surfaces.",
            ],
            links=[
                {
                    "label": "Open Campaign Home",
                    "href": url_for("campaign_view", campaign_slug=campaign.slug),
                }
            ],
        ),
        build_help_surface(
            anchor="systems",
            label="Systems",
            summary="Shared mechanics library for rules, creatures, spells, items, and other imported entries.",
            status_label="Open" if can_view_systems else "Hidden",
            access_note=(
                (
                    f"You can open Systems right now. Current Systems visibility: {systems_visibility_label}."
                    + (
                        " You can also adjust source visibility from Systems Policy."
                        if can_manage_systems
                        else ""
                    )
                )
                if can_view_systems
                else f"Systems currently requires {systems_visibility_label} access."
            ),
            capabilities=[
                "Browse enabled sources and categories without loading the whole rules library at once.",
                "Open linked mechanics from character sheets, combat sources, and campaign overlays.",
                "Use Rules Reference Search for chapter headings, aliases, formulas, and other curated rule metadata.",
            ],
            limits=[
                "Systems is currently a DND-5E-first shared library.",
                "Global Systems search matches title, entry type, and source rather than full body text.",
                "Rules Reference Search is metadata-driven instead of generic body-text search.",
            ],
            links=(
                [
                    {
                        "label": "Open Systems",
                        "href": url_for("campaign_systems_index", campaign_slug=campaign.slug),
                    }
                ]
                + (
                    [
                        {
                            "label": "Open Systems Policy",
                            "href": url_for(
                                "campaign_systems_control_panel_view",
                                campaign_slug=campaign.slug,
                            ),
                        }
                    ]
                    if can_manage_systems
                    else []
                )
            ),
        ),
        build_help_surface(
            anchor="session",
            label="Session",
            summary="Live play surface for chat, revealed articles, and in-session lookup.",
            status_label="Open" if can_view_session else "Hidden",
            access_note=(
                (
                    f"You can open Session right now. Current Session visibility: {session_visibility_label}."
                    + (
                        " This viewer can post chat during an active session."
                        if can_post_campaign_session_messages(campaign_slug)
                        else " This viewer can read the surface but cannot post live chat messages."
                    )
                )
                if can_view_session
                else f"Session currently requires {session_visibility_label} access."
            ),
            capabilities=[
                "Follow the live session feed for chat and DM-revealed articles.",
                "Use the wiki lookup widget to preview player-visible published pages without leaving Session.",
                (
                    "DMs can stage manual, upload, or wiki-backed articles, reveal them live, and convert session-only content into published wiki pages."
                    if can_manage_session
                    else "Assigned players, DMs, and admins can use the separate Session Character surface for in-play sheet access while chat and article tools stay on the main Session page."
                ),
            ],
            limits=[
                "Live updates use lightweight polling rather than websockets.",
                "Session-only articles stay out of the published wiki and search until a DM converts them.",
                "The Session Character surface intentionally keeps a smaller in-play slice than the full character page.",
            ],
            links=(
                [
                    {
                        "label": "Open Session",
                        "href": url_for("campaign_session_view", campaign_slug=campaign.slug),
                    }
                ]
                + (
                    [
                        {
                            "label": "Open DM Page",
                            "href": url_for(
                                "campaign_session_dm_view",
                                campaign_slug=campaign.slug,
                                dm_view="tools",
                            ),
                        }
                    ]
                    if can_manage_session
                    else []
                )
            ),
        ),
        build_help_surface(
            anchor="combat",
            label="Combat",
            summary="Encounter tracker and in-combat character workspace.",
            status_label=(
                "Open"
                if can_view_combat and combat_system_supported
                else "Limited"
                if can_view_combat
                else "Hidden"
            ),
            access_note=(
                (
                    f"You can open Combat right now. Current Combat visibility: {combat_visibility_label}."
                    + (
                        ""
                        if combat_system_supported
                        else f" This campaign uses {system_label}, so combat stays limited until non-{DND_5E_SYSTEM_CODE} support exists."
                    )
                )
                if can_view_combat
                else f"Combat currently requires {combat_visibility_label} access."
            ),
            capabilities=[
                "Track turn order, HP, conditions, movement, and encounter state during play.",
                (
                    "DMs split encounter work between Encounter status for selected-combatant state and Encounter controls for setup, seeding, structural edits, and cleanup."
                    if can_manage_combat
                    else "Players with a tracked combatant get a character-first workspace on the main Combat surface instead of only a tracker readout."
                ),
                combat_source_seed_capability,
            ],
            limits=[
                f"Combat is currently implemented for {DND_5E_SYSTEM_CODE} campaigns.",
                "Player edits stay limited to their own allowed combat-facing character state.",
                "NPC detail visibility remains DM-controlled.",
            ],
            links=(
                [
                    {
                        "label": "Open Combat",
                        "href": url_for("campaign_combat_view", campaign_slug=campaign.slug),
                    }
                ]
                + (
                    [
                        {
                            "label": "Open Encounter Status",
                            "href": url_for(
                                "campaign_combat_dm_view",
                                campaign_slug=campaign.slug,
                            ),
                        },
                        {
                            "label": "Open Encounter Controls",
                            "href": url_for(
                                "campaign_combat_dm_view",
                                campaign_slug=campaign.slug,
                                view="controls",
                            ),
                        },
                    ]
                    if can_manage_combat
                    else []
                )
            ),
        ),
        build_help_surface(
            anchor="dm-content",
            label="DM Content",
            summary=(
                "DM-facing content management for player wiki pages, Systems policy and custom entries, "
                "statblocks, staged articles, and custom conditions."
            ),
            status_label=(
                "Open"
                if can_view_dm_content and combat_system_supported
                else "Limited"
                if can_view_dm_content
                else "Hidden"
            ),
            access_note=(
                (
                    f"You can open DM Content right now. Current DM Content visibility: {dm_content_visibility_label}."
                    + (
                        ""
                        if combat_system_supported
                        else f" Statblock upload is currently built only for {DND_5E_SYSTEM_CODE} campaigns."
                    )
                )
                if can_view_dm_content
                else f"DM Content currently requires {dm_content_visibility_label} access."
            ),
            capabilities=[
                "Create, edit, attach images to, unpublish/archive, or safely hard-delete player wiki Markdown pages from the Player Wiki lane.",
                "Manage Systems source enablement, entry overrides, custom campaign entries, shared-source import review, and admin-only DND-5E ZIP imports from the Systems lane.",
                "Upload and edit DM statblock markdown for later encounter seeding.",
                "Prepare and revise unrevealed staged session articles before reveal or wiki publication.",
                "Maintain custom combat conditions alongside the built-in DND-5E list.",
            ],
            limits=[
                "Player wiki edits still need normal spoiler and reveal-safety judgment before publication.",
                "Inline wiki-page image uploads are copied into campaign assets and referenced from page frontmatter.",
                "Hard delete is blocked when a page still has wiki backlinks, character hooks, or session provenance.",
                "Imported shared-library Systems entries are not edited through campaign management; the shared/core editor is reserved for app admins and kept separate from source policy, entry overrides, and custom campaign entries.",
                "The statblock parser is currently implemented for DND-5E-style markdown.",
                "Statblock saves need recognizable Armor Class, Hit Points, and Speed lines when those values should feed Combat.",
                "Custom conditions augment the built-in list rather than replacing it.",
            ],
            links=(
                [
                    {
                        "label": "Open DM Content",
                        "href": url_for("campaign_dm_content_view", campaign_slug=campaign.slug),
                    },
                    {
                        "label": "Open Player Wiki",
                        "href": url_for(
                            "campaign_dm_content_subpage_view",
                            campaign_slug=campaign.slug,
                            dm_content_subpage="player-wiki",
                        ),
                    },
                    {
                        "label": "Open Systems",
                        "href": url_for(
                            "campaign_dm_content_subpage_view",
                            campaign_slug=campaign.slug,
                            dm_content_subpage="systems",
                        ),
                    },
                    {
                        "label": "Open Staged Articles",
                        "href": url_for(
                            "campaign_dm_content_subpage_view",
                            campaign_slug=campaign.slug,
                            dm_content_subpage="staged-articles",
                        ),
                    }
                ]
                if can_view_dm_content
                else []
            ),
            guidance_cards=[
                {
                    "title": "Browser and API boundary",
                    "body": "",
                    "items": [
                        "Browser Player Wiki saves use the content service so mirrored Markdown and the read model stay synchronized.",
                        "Browser Player Wiki hard delete adds usage checks before the low-level content delete runs.",
                        "The raw content API remains available for automation, but API clients need their own publish-safety and dependency checks.",
                    ],
                    "meta": "",
                },
                {
                    "title": "Character-linked content",
                    "body": "",
                    "items": [
                        "Player Wiki deletion checks include character hooks and sheet page references.",
                        "Character file API management is separate from native character create, edit, level-up, repair, and controls workflows.",
                    ],
                    "meta": "",
                },
            ],
        ),
        build_help_surface(
            anchor="characters",
            label="Characters",
            summary="Full read-mode character sheets plus the broader maintenance surface.",
            status_label=(
                "Open"
                if can_view_characters and native_character_tools_supported
                else "Limited"
                if can_view_characters
                else "Hidden"
            ),
            access_note=(
                (
                    f"You can open Characters right now. Current Characters visibility: {characters_visibility_label}."
                    + (
                        " Native create/edit/level-up tools are available for this campaign system."
                        if native_character_tools_supported
                        else f" Native authoring stays limited because this campaign is not using {DND_5E_SYSTEM_CODE}."
                    )
                )
                if can_view_characters
                else f"Characters currently requires {characters_visibility_label} access."
            ),
            capabilities=[
                "Browse full character sheets and their read-mode subpages.",
                (
                    "Use native DND-5E create, edit, level-up, and progression-repair flows where your role allows them."
                    if native_character_tools_supported
                    else "Use read-mode, Session Character, and combat-linked views for character reference even though native authoring is unavailable here."
                ),
                "Use the full character page for portraits, equipment state, spell-list maintenance, and broader sheet upkeep.",
            ],
            limits=[
                f"Native authoring tools are currently only supported for {DND_5E_SYSTEM_CODE} campaigns.",
                "Imported characters may need progression repair before native level-up is available.",
                "Session and Combat intentionally keep only a smaller quick-edit slice instead of replacing the full character page.",
            ],
            guidance_cards=character_guidance_cards,
            links=(
                [
                    {
                        "label": "Open Characters",
                        "href": url_for("character_roster_view", campaign_slug=campaign.slug),
                    }
                ]
                if can_view_characters
                else []
            ),
        ),
        build_help_surface(
            anchor="control",
            label="Control",
            summary="Visibility management for the campaign and each campaign-owned scope.",
            status_label="Open" if can_manage_visibility else "Hidden",
            access_note=(
                "You can open Control because this viewer can manage campaign visibility."
                if can_manage_visibility
                else "Only the campaign DM or an admin can open this surface."
            ),
            capabilities=[
                "Set the campaign-wide visibility floor and the per-scope defaults for wiki, systems, session, combat, DM Content, and characters.",
                "Review the effective visibility each scope currently resolves to.",
                "Use this page to decide which surfaces are public, player-visible, DM-only, or private.",
            ],
            limits=[
                "The more private value between Campaign and an individual scope wins.",
                "`Private` is reserved for admins.",
                "Changing visibility does not rewrite content; it only changes who can see the route.",
            ],
            links=(
                [
                    {
                        "label": "Open Control",
                        "href": url_for(
                            "campaign_control_panel_view",
                            campaign_slug=campaign.slug,
                        ),
                    }
                ]
                if can_manage_visibility
                else []
            ),
        ),
    ]

    visible_help_surfaces = [
        surface for surface in help_surfaces if surface["status_label"] in {"Open", "Limited"}
    ]

    visibility_rows = []
    for scope in CAMPAIGN_VISIBILITY_SCOPES:
        viewer_can_open = can_access_campaign_scope(campaign_slug, scope)
        if not viewer_can_open:
            continue
        visibility_rows.append(
            {
                "label": CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope],
                "visibility_label": VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, scope)],
                "viewer_can_open": viewer_can_open,
            }
        )

    available_surface_labels = [
        surface["label"]
        for surface in visible_help_surfaces
    ]

    help_cross_cutting_limits = [
        "Campaign visibility can hide a feature even when the route exists for other roles.",
    ]

    dnd5e_first_features: list[str] = []
    if can_view_characters:
        dnd5e_first_features.append("native character authoring")
    if can_view_combat:
        dnd5e_first_features.append("combat")
    if can_view_dm_content:
        dnd5e_first_features.append("DM Content statblocks")
    if can_view_combat and can_view_systems:
        dnd5e_first_features.append("Systems-backed combat seeding")
    if dnd5e_first_features:
        help_cross_cutting_limits.append(
            f"{format_help_label_list(dnd5e_first_features)} {'is' if len(dnd5e_first_features) == 1 else 'are'} currently DND-5E-first workflow{'s' if len(dnd5e_first_features) != 1 else ''}."
        )

    if can_view_systems:
        help_cross_cutting_limits.append(
            "Systems search is intentionally narrow: global search matches title, type, and source, while Rules Reference Search uses metadata."
        )

    if can_view_session or can_view_combat:
        live_surfaces: list[str] = []
        if can_view_session:
            live_surfaces.append("Session")
        if can_view_combat:
            live_surfaces.append("Combat")
        help_cross_cutting_limits.append(
            f"{format_help_label_list(live_surfaces)} refresh{'es' if len(live_surfaces) == 1 else ''} with polling instead of websockets."
        )

    if can_view_session and can_manage_session:
        help_cross_cutting_limits.append(
            "Session-only articles stay separate from the published wiki until a DM converts them."
        )

    return {
        "campaign": campaign,
        "help_surfaces": visible_help_surfaces,
        "help_viewer_role_label": viewer_context["role_label"],
        "help_viewer_role_summary": viewer_context["role_summary"],
        "help_campaign_system_label": system_label,
        "help_available_surface_labels": available_surface_labels,
        "help_cross_cutting_limits": help_cross_cutting_limits,
        "help_visibility_rows": visibility_rows,
        "help_account_note": (
            "Account settings let signed-in users change their color theme and preferred live Session chat order."
            if current_user is not None
            else "Sign in to save theme preferences, choose a live Session chat order, and open member-only surfaces."
        ),
        "active_nav": "help",
    }


__all__ = [
    "COMBAT_AND_SESSION_COMBAT_SCOPE",
    "COMBAT_AND_SESSION_SESSION_SCOPE",
    "build_campaign_help_context",
]
