from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, request

from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .character_reconciliation import CharacterPublicationConflict, PendingNativeLevelUpAuthority
from .character_source_repair import (load_verified_manual_actions, load_verified_numeric_actions,
                                      record_confirmed_native_level_up_witness)
from .committed_publication import active
from .character_source_authority import (build_reconciled_source_authority,
                                         prepare_native_level_up_resource_authorizations)


@dataclass(frozen=True)
class CharacterLevelUpApiDependencies:
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_level_up_target: Callable[[str, str], tuple[Any, Any, Any | None]]
    character_level_up_readiness: Callable[[str, Any, Any], dict[str, Any]]
    character_level_up_is_supported: Callable[[dict[str, Any]], bool]
    serialize_character_level_up_response: Callable[..., Any]
    normalize_character_level_up_values: Callable[[dict[str, Any]], dict[str, str]]
    build_character_level_up_context_parts: Callable[..., dict[str, Any]]
    list_visible_character_page_records: Callable[..., list[Any]]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    load_character_record: Callable[[str, str], Any]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    get_current_user: Callable[[], Any | None]
    build_native_level_up_character_definition: Callable[..., tuple[Any, Any, int]]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    character_publication_coordinator: object
    get_auth_store: Callable[[], object]


def register_character_level_up_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterLevelUpApiDependencies,
) -> None:
    def character_level_up_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_level_up_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, record
        )
        if not dependencies.character_level_up_is_supported(readiness):
            return dependencies.serialize_character_level_up_response(
                campaign_slug, campaign, record, readiness=readiness
            )
        form_values = dependencies.normalize_character_level_up_values(
            dict(request.args)
        )
        try:
            level_up_context = dependencies.build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
        except CharacterBuildError as exc:
            readiness = {"status": "unsupported", "message": str(exc)}
            return dependencies.serialize_character_level_up_response(
                campaign_slug, campaign, record, readiness=readiness
            )
        return dependencies.serialize_character_level_up_response(
            campaign_slug,
            campaign,
            record,
            readiness=readiness,
            level_up_context=level_up_context,
        )

    def character_level_up_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_level_up_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, record
        )
        if not dependencies.character_level_up_is_supported(readiness):
            return dependencies.json_error(
                str(
                    readiness.get("message")
                    or "This character is not ready for level-up."
                ),
                400,
                code="unsupported_campaign_system",
            )
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        try:
            payload = dependencies.load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = dependencies.normalize_character_level_up_values(payload)
            level_up_context = dependencies.build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            authority_page_records = dependencies.list_visible_character_page_records(
                campaign_slug, campaign
            )
            target_level = int(level_up_context.get("next_level") or 0)
            definition, import_metadata, hp_gain = (
                dependencies.build_native_level_up_character_definition(
                    campaign_slug,
                    record.definition,
                    level_up_context,
                    form_values,
                    current_import_metadata=record.import_metadata,
                    state=record.state_record.state or {},
                    state_revision=record.state_record.revision,
                    verified_manual_actions=(load_verified_manual_actions(campaign_slug, character_slug)
                                             if active() else ()),
                    verified_numeric_actions=(load_verified_numeric_actions(campaign_slug, character_slug)
                                              if active() else ()),
                    authority_page_records=authority_page_records,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug, definition
            )
            if active():
                manual_witnesses = load_verified_manual_actions(campaign_slug, character_slug)
                numeric_witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
                definition, new_markers, source_bases, simulated_witnesses, source_digest, authority_state = (
                    prepare_native_level_up_resource_authorizations(
                        prior_definition=record.definition, candidate_definition=definition,
                        prior_state=record.state_record.state or {},
                        state_revision=record.state_record.revision,
                        systems_service=current_app.extensions["systems_service"],
                        campaign_page_records=authority_page_records,
                        verified_manual_actions=manual_witnesses,
                        verified_numeric_actions=numeric_witnesses,
                    )
                )
                prospective_authority = build_reconciled_source_authority(
                    definition=definition, state=authority_state,
                    state_revision=record.state_record.revision,
                    systems_service=current_app.extensions["systems_service"],
                    campaign_page_records=authority_page_records,
                    verified_manual_actions=manual_witnesses,
                    verified_numeric_actions=simulated_witnesses,
                )
                merged_state = dependencies.merge_state_with_definition(
                    definition,
                    record.state_record.state,
                    source_authority=prospective_authority,
                    hp_delta=hp_gain,
                )
                def refresh_pending_authority():
                    fresh_campaign, fresh_record, access_error = dependencies.load_character_level_up_target(
                        campaign_slug, character_slug)
                    if access_error is not None or fresh_record is None:
                        raise CharacterStateConflictError("Character access changed before publication.")
                    return build_reconciled_source_authority(
                        definition=definition, state=authority_state,
                        state_revision=record.state_record.revision,
                        systems_service=current_app.extensions["systems_service"],
                        campaign_page_records=dependencies.list_visible_character_page_records(
                            campaign_slug, fresh_campaign),
                        verified_manual_actions=load_verified_manual_actions(campaign_slug, character_slug),
                        verified_numeric_actions=(load_verified_numeric_actions(campaign_slug, character_slug)
                                                  + tuple(witness for witness in simulated_witnesses
                                                          if witness not in numeric_witnesses)),
                    )
                pending_authority = (
                    PendingNativeLevelUpAuthority.from_proof(
                        prior_record=record, definition=definition, desired_state=merged_state,
                        authority=prospective_authority, markers=new_markers,
                        refresh=refresh_pending_authority,
                    ) if new_markers else None
                )
            else:
                new_markers = ()
                pending_authority = None
                merged_state = dependencies.merge_state_with_definition(
                    definition, record.state_record.state, hp_delta=hp_gain,
                )
            dependencies.character_publication_coordinator.update(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                operation_kind="interactive_update",
                pending_numeric_authority=pending_authority,
            )
            resource_witness_confirmed = not new_markers
            if new_markers:
                try:
                    readback_campaign, readback, readback_access_error = dependencies.load_character_level_up_target(
                        campaign_slug, character_slug)
                    if readback_access_error is not None or readback is None:
                        raise CharacterStateConflictError("Character access changed before source audit.")
                    current_source = build_reconciled_source_authority(
                        definition=readback.definition, state=readback.state_record.state or {},
                        state_revision=readback.state_record.revision,
                        systems_service=current_app.extensions["systems_service"],
                        campaign_page_records=dependencies.list_visible_character_page_records(campaign_slug, readback_campaign),
                        verified_manual_actions=manual_witnesses,
                        verified_numeric_actions=numeric_witnesses,
                    )
                    if (current_source.source_snapshot_digest == source_digest
                            and all(current_source.numeric_basis_digest(target_id) == basis
                                    for target_id, basis in source_bases.items())):
                        resource_witness_confirmed = record_confirmed_native_level_up_witness(
                            expected_definition=definition, readback_record=readback,
                            markers=new_markers, prior_revision=record.state_record.revision,
                            source_snapshot_digest=source_digest,
                            source_basis_digests=source_bases, actor_id=user.id,
                            auth_store=dependencies.get_auth_store(),
                        )
                except Exception:
                    resource_witness_confirmed = False
        except CharacterPublicationConflict:
            return dependencies.json_error(
                "The level-up update needs reconciliation. Its saved outcome is uncertain. Inspect the current Character before submitting again.",
                409,
                code="publication_conflict",
            )
        except CharacterStateConflictError:
            return dependencies.json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (
            CharacterBuildError,
            CharacterStateValidationError,
            TypeError,
            ValueError,
        ) as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        refreshed_record = dependencies.load_character_record(
            campaign_slug, character_slug
        )
        refreshed_readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, refreshed_record
        )
        refreshed_context = None
        if dependencies.character_level_up_is_supported(refreshed_readiness):
            refreshed_context = dependencies.build_character_level_up_context_parts(
                campaign_slug, campaign, refreshed_record
            )
        return dependencies.serialize_character_level_up_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            level_up_context=refreshed_context,
            message=(f"{definition.name} advanced to level {target_level}."
                     if resource_witness_confirmed else
                     f"{definition.name} advanced to level {target_level}. New resource totals need manager review before use."),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_read",
        view_func=dependencies.api_login_required(character_level_up_read),
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_submit",
        view_func=dependencies.api_login_required(character_level_up_submit),
        methods=("POST",),
    )
