from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint

from .character_models import CharacterRecord


@dataclass(frozen=True)
class CharacterXianxiaDaoUseRequestApiDependencies:
    api_login_required: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    ensure_xianxia_character_definition: Callable[..., object]
    json_payload_value: Callable[..., object]
    optional_json_int: Callable[..., object]
    managed_character_import_metadata: Callable[..., object]
    request_xianxia_dao_immolating_use_definition: Callable[..., object]


def register_character_xianxia_dao_use_request_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaDaoUseRequestApiDependencies,
) -> None:
    def character_xianxia_dao_immolating_use_request(
        campaign_slug: str,
        character_slug: str,
    ):
        def request_dao_use(record: CharacterRecord, payload: dict[str, Any], user_id: int):
            dependencies.ensure_xianxia_character_definition(
                record,
                "Dao Immolating use requests are only available for Xianxia character sheets.",
            )
            request_result = dependencies.request_xianxia_dao_immolating_use_definition(
                record.definition,
                request_name=str(
                    dependencies.json_payload_value(
                        payload,
                        "request_name",
                        "dao_immolating_request_name",
                    )
                    or ""
                ),
                notes=str(
                    dependencies.json_payload_value(
                        payload,
                        "notes",
                        "dao_immolating_request_notes",
                    )
                    or ""
                ),
                prepared_record_index=dependencies.optional_json_int(
                    payload,
                    "prepared_record_index",
                    "dao_immolating_prepared_index",
                    field_label="Prepared Dao Immolating Technique note",
                ),
            )
            return (
                request_result.definition,
                dependencies.managed_character_import_metadata(campaign_slug, record),
                {},
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            request_dao_use,
            forbidden_message=(
                "You do not have permission to request Dao Immolating use for this character."
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-requests",
        endpoint="character_xianxia_dao_immolating_use_request",
        view_func=dependencies.api_login_required(
            character_xianxia_dao_immolating_use_request
        ),
        methods=("POST",),
    )
