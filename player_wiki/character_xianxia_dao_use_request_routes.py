from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterXianxiaDaoUseRequestRouteDependencies:
    run_character_definition_mutation: Callable[..., object]
    is_xianxia_system: Callable[..., bool]
    normalize_dm_player_wiki_int: Callable[..., int]
    request_xianxia_dao_immolating_use_definition: Callable[..., object]
    build_managed_character_import_metadata: Callable[..., object]


def register_character_xianxia_dao_use_request_route(
    app: Any,
    *,
    dependencies: CharacterXianxiaDaoUseRequestRouteDependencies,
) -> None:
    def character_xianxia_dao_immolating_use_request(
        campaign_slug: str, character_slug: str
    ):
        def _action(record):
            if not dependencies.is_xianxia_system(
                getattr(record.definition, "system", "")
            ):
                raise ValueError(
                    "Dao Immolating use requests are only available for Xianxia "
                    "character sheets."
                )
            raw_prepared_record_index = request.form.get(
                "dao_immolating_prepared_index", ""
            )
            prepared_record_index = None
            if str(raw_prepared_record_index or "").strip():
                prepared_record_index = dependencies.normalize_dm_player_wiki_int(
                    raw_prepared_record_index,
                    field_label="Prepared Dao Immolating Technique note",
                )
            request_result = (
                dependencies.request_xianxia_dao_immolating_use_definition(
                    record.definition,
                    request_name=request.form.get(
                        "dao_immolating_request_name", ""
                    ),
                    notes=request.form.get("dao_immolating_request_notes", ""),
                    prepared_record_index=prepared_record_index,
                )
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            return request_result.definition, import_metadata, {}

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-dao-immolating-use-request",
            success_message="Dao Immolating use request recorded.",
            action=_action,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "xianxia/dao-immolating-use-requests",
        endpoint="character_xianxia_dao_immolating_use_request",
        view_func=scope_required(character_xianxia_dao_immolating_use_request),
        methods=("POST",),
    )
