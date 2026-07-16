from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class CharacterRestPreviewApiDependencies:
    api_login_required: Callable[..., object]
    load_character_record: Callable[..., object]
    has_session_mode_access: Callable[..., object]
    get_character_state_service: Callable[..., object]
    json_error: Callable[..., object]


def register_character_rest_preview_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterRestPreviewApiDependencies,
) -> None:
    def character_rest_preview(campaign_slug: str, character_slug: str, rest_type: str):
        record = dependencies.load_character_record(campaign_slug, character_slug)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            return dependencies.json_error(
                "You do not have permission to use rest actions for this character.",
                403,
                code="forbidden",
            )

        try:
            preview = dependencies.get_character_state_service().preview_rest(
                record, rest_type
            )
        except ValueError as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        return jsonify(
            {
                "ok": True,
                "preview": {
                    "rest_type": preview.rest_type,
                    "label": preview.label,
                    "changes": [
                        {
                            "label": change.label,
                            "from_value": change.from_value,
                            "to_value": change.to_value,
                        }
                        for change in preview.changes
                    ],
                    "adjustments": preview.adjustments,
                },
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>",
        endpoint="character_rest_preview",
        view_func=dependencies.api_login_required(character_rest_preview),
        methods=("GET",),
    )
