from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, jsonify, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterEquipmentSearchRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    get_systems_service: Callable[..., object]
    format_character_systems_item_weight: Callable[..., str]
    has_session_mode_access: Callable[..., bool]


def register_character_equipment_search_route(
    app: Any,
    *,
    dependencies: CharacterEquipmentSearchRouteDependencies,
) -> None:
    def character_equipment_systems_item_search(
        campaign_slug: str, character_slug: str
    ):
        dependencies.load_character_context(campaign_slug, character_slug)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "results": [],
                    "message": "Type at least 2 letters to search enabled Systems items.",
                }
            )

        results = []
        for entry in dependencies.get_systems_service().search_entries_for_campaign(
            campaign_slug,
            query=query,
            entry_type="item",
            limit=20,
        ):
            subtitle_parts = [str(entry.source_id or "").strip()]
            weight_label = dependencies.format_character_systems_item_weight(
                (entry.metadata or {}).get("weight")
            )
            if weight_label:
                subtitle_parts.append(weight_label)
            subtitle = " - ".join(part for part in subtitle_parts if part)
            select_label = f"{entry.title} - {subtitle}" if subtitle else entry.title
            results.append(
                {
                    "entry_slug": entry.slug,
                    "title": entry.title,
                    "source_id": entry.source_id,
                    "subtitle": subtitle,
                    "select_label": select_label,
                }
            )

        return jsonify(
            {
                "results": results,
                "message": (
                    f"Found {len(results)} matching Systems items."
                    if results
                    else "No enabled Systems items matched that search."
                ),
            }
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/systems-items/search",
        endpoint="character_equipment_systems_item_search",
        view_func=campaign_scope_access_required("characters")(
            character_equipment_systems_item_search
        ),
        methods=("GET",),
    )
