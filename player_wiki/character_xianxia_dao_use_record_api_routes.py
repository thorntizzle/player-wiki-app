from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint

from .character_models import CharacterRecord


@dataclass(frozen=True)
class CharacterXianxiaDaoUseRecordApiDependencies:
    api_login_required: Callable[..., object]
    can_manage_campaign_session: Callable[..., object]
    json_error: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    ensure_xianxia_character_definition: Callable[..., object]
    required_json_int: Callable[..., object]
    json_payload_value: Callable[..., object]
    managed_character_import_metadata: Callable[..., object]
    record_xianxia_dao_immolating_use_definition: Callable[..., object]


def register_character_xianxia_dao_use_record_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaDaoUseRecordApiDependencies,
) -> None:
    def character_xianxia_dao_immolating_use_record(
        campaign_slug: str,
        character_slug: str,
    ):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to record Dao Immolating use for this character.",
                403,
                code="forbidden",
            )

        def record_dao_use(record: CharacterRecord, payload: dict[str, Any], user_id: int):
            dependencies.ensure_xianxia_character_definition(
                record,
                "Dao Immolating use records are only available for Xianxia character sheets.",
            )
            use_result = dependencies.record_xianxia_dao_immolating_use_definition(
                record.definition,
                use_record_index=dependencies.required_json_int(
                    payload,
                    "use_record_index",
                    "dao_immolating_use_index",
                    field_label="Dao Immolating Technique use",
                ),
                notes=str(
                    dependencies.json_payload_value(
                        payload,
                        "notes",
                        "dao_immolating_use_notes",
                    )
                    or ""
                ),
            )
            return (
                use_result.definition,
                dependencies.managed_character_import_metadata(campaign_slug, record),
                {},
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            record_dao_use,
            forbidden_message=(
                "You do not have permission to record Dao Immolating use for this character."
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-records",
        endpoint="character_xianxia_dao_immolating_use_record",
        view_func=dependencies.api_login_required(
            character_xianxia_dao_immolating_use_record
        ),
        methods=("POST",),
    )
