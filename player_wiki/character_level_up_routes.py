from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

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
class CharacterLevelUpRouteDependencies:
    get_repository: Callable[..., object]
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_native_character_advancement: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    list_visible_character_page_records: Callable[..., list[object]]
    get_systems_service: Callable[..., object]
    character_sheet_return_href: Callable[..., str]
    render_character_level_up_page: Callable[..., object]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    login_required: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    character_advancement_unsupported_message: Callable[..., str]
    native_level_up_readiness: Callable[..., dict[str, object]]
    can_manage_campaign_session: Callable[..., bool]
    build_native_level_up_context: Callable[..., dict[str, object]]
    get_current_user: Callable[..., object]
    build_native_level_up_character_definition: Callable[
        ..., tuple[object, object, int]
    ]
    merge_state_with_definition: Callable[..., dict[str, object]]
    character_publication_coordinator: object
    render_protected_character_conflict: Callable[..., object | None]
    get_auth_store: Callable[[], object]


def register_character_level_up_route(
    app: Any,
    *,
    dependencies: CharacterLevelUpRouteDependencies,
) -> None:
    def character_level_up_view(campaign_slug: str, character_slug: str):
        if dependencies.get_repository().get_campaign(campaign_slug) is None:
            abort(404)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.campaign_supports_native_character_advancement(campaign):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message=dependencies.character_advancement_unsupported_message(
                    campaign.system
                ),
            )
        campaign_page_records = dependencies.list_builder_campaign_page_records(
            campaign_slug, campaign
        )
        authority_page_records = dependencies.list_visible_character_page_records(
            campaign_slug, campaign
        )
        readiness = dependencies.native_level_up_readiness(
            dependencies.get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=campaign_page_records,
        )
        if readiness.get("status") == "repairable":
            flash(
                str(
                    readiness.get("message")
                    or "This imported character needs progression repair first."
                ),
                "error",
            )
            if not dependencies.can_manage_campaign_session(campaign_slug):
                return redirect(
                    dependencies.character_sheet_return_href(
                        campaign_slug, character_slug
                    )
                )
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") != "ready":
            flash(
                str(
                    readiness.get("message")
                    or "This character is not eligible for the current native level-up flow."
                ),
                "error",
            )
            return redirect(
                dependencies.character_sheet_return_href(
                    campaign_slug, character_slug
                )
            )

        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        try:
            level_up_context = dependencies.build_native_level_up_context(
                dependencies.get_systems_service(),
                campaign_slug,
                record.definition,
                form_values,
                campaign_page_records=campaign_page_records,
            )
            level_up_context["state_revision"] = record.state_record.revision
        except CharacterBuildError as exc:
            flash(str(exc), "error")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method != "POST":
            return dependencies.render_character_level_up_page(
                campaign_slug, character_slug, level_up_context
            )

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        draft_names = (
            "advancement_mode", "new_class_slug", "new_subclass_slug",
            "target_class_row_id", "hp_gain",
            *(
                field["name"]
                for section in level_up_context.get("choice_sections", ())
                for field in section.get("fields", ())
            ),
        )

        try:
            expected_revision = dependencies.parse_expected_revision()
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
                campaign_slug,
                definition,
                campaign=campaign,
            )
            if active():
                manual_witnesses = load_verified_manual_actions(campaign_slug, character_slug)
                numeric_witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
                definition, new_markers, source_bases, simulated_witnesses, source_digest, authority_state = (
                    prepare_native_level_up_resource_authorizations(
                        prior_definition=record.definition, candidate_definition=definition,
                        prior_state=record.state_record.state or {},
                        state_revision=record.state_record.revision,
                        systems_service=dependencies.get_systems_service(),
                        campaign_page_records=authority_page_records,
                        verified_manual_actions=manual_witnesses,
                        verified_numeric_actions=numeric_witnesses,
                    )
                )
                prospective_authority = build_reconciled_source_authority(
                    definition=definition, state=authority_state,
                    state_revision=record.state_record.revision,
                    systems_service=dependencies.get_systems_service(),
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
                    if not dependencies.has_session_mode_access(campaign_slug, character_slug):
                        raise CharacterStateConflictError("Character access changed before publication.")
                    fresh_campaign, _ = dependencies.load_character_context(campaign_slug, character_slug)
                    return build_reconciled_source_authority(
                        definition=definition, state=authority_state,
                        state_revision=record.state_record.revision,
                        systems_service=dependencies.get_systems_service(),
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
                    readback_campaign, readback = dependencies.load_character_context(campaign_slug, character_slug)
                    current_source = build_reconciled_source_authority(
                        definition=readback.definition, state=readback.state_record.state or {},
                        state_revision=readback.state_record.revision,
                        systems_service=dependencies.get_systems_service(),
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
            return dependencies.render_protected_character_conflict(
                campaign_slug, character_slug,
                protected_conflict=True,
                recovery_draft_names=draft_names,
                refresh_href=url_for("character_level_up_view", campaign_slug=campaign_slug, character_slug=character_slug),
                recovery_message="The level-up update needs reconciliation. Its saved outcome is uncertain. Keep a copy of your choices and inspect the current Character before submitting again.",
                status_code=409,
                mutation_outcome="publication-conflict",
            )
        except CharacterStateConflictError:
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
            return dependencies.render_character_level_up_page(
                campaign_slug,
                character_slug,
                level_up_context,
                status_code=409,
            )
        except (
            CharacterBuildError,
            CharacterStateValidationError,
            ValueError,
        ) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_level_up_page(
                campaign_slug,
                character_slug,
                level_up_context,
                status_code=400,
            )

        flash(
            f"{definition.name} advanced to level {int(level_up_context.get('next_level') or 0)}.",
            "success",
        )
        if not resource_witness_confirmed:
            flash("The new resource totals need manager review before use.", "warning")
        return redirect(
            dependencies.character_sheet_return_href(campaign_slug, character_slug)
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_view",
        view_func=dependencies.login_required(character_level_up_view),
        methods=("GET", "POST"),
    )
