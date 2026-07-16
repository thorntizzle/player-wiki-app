from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterXianxiaDaoUseRecordRouteDependencies:
    run_character_definition_mutation: Callable[..., object]
    can_manage_campaign_session: Callable[..., bool]
    is_xianxia_system: Callable[..., bool]
    normalize_dm_player_wiki_int: Callable[..., int]
    record_xianxia_dao_immolating_use_definition: Callable[..., object]
    build_managed_character_import_metadata: Callable[..., object]


def register_character_xianxia_dao_use_record_route(
    app: Any,
    *,
    dependencies: CharacterXianxiaDaoUseRecordRouteDependencies,
) -> None:
    def character_xianxia_dao_immolating_use_record(
        campaign_slug: str, character_slug: str
    ):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        def _action(record):
            if not dependencies.is_xianxia_system(
                getattr(record.definition, "system", "")
            ):
                raise ValueError(
                    "Dao Immolating use records are only available for Xianxia "
                    "character sheets."
                )
            raw_use_record_index = request.form.get(
                "dao_immolating_use_index", ""
            )
            if not str(raw_use_record_index or "").strip():
                raise ValueError(
                    "Dao Immolating Technique use selection is required."
                )
            use_record_index = dependencies.normalize_dm_player_wiki_int(
                raw_use_record_index,
                field_label="Dao Immolating Technique use",
            )
            use_result = dependencies.record_xianxia_dao_immolating_use_definition(
                record.definition,
                use_record_index=use_record_index,
                notes=request.form.get("dao_immolating_use_notes", ""),
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            return use_result.definition, import_metadata, {}

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-approval-dao-immolating-use-records",
            success_message="Dao Immolating one-use history recorded.",
            action=_action,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "xianxia/dao-immolating-use-records",
        endpoint="character_xianxia_dao_immolating_use_record",
        view_func=scope_required(character_xianxia_dao_immolating_use_record),
        methods=("POST",),
    )
