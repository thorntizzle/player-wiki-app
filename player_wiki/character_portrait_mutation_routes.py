from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, request, url_for

from .auth import campaign_scope_access_required
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError, CharacterStateUnavailableError
from .character_reconciliation import CharacterPublicationConflict


@dataclass(frozen=True)
class CharacterPortraitMutationRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    parse_expected_revision: Callable[..., int]
    validate_character_portrait_upload: Callable[..., tuple[str, bytes]]
    prepare_character_portrait_definition_for_write: Callable[..., object]
    redirect_to_character_mode: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    get_current_user: Callable[..., object | None]
    validate_character_portrait_text: Callable[..., tuple[str, str]]
    build_character_portrait_asset_ref: Callable[..., str]
    update_character_portrait_profile: Callable[..., object]
    build_managed_character_import_metadata: Callable[..., object]
    merge_state_with_definition: Callable[..., dict]
    publish_character_portrait: Callable[..., object]
    render_protected_character_conflict: Callable[..., object | None]


def _dependencies() -> CharacterPortraitMutationRouteDependencies:
    return current_app.extensions["character_portrait_mutation_route_dependencies"]


def register_character_portrait_mutation_routes(
    app: Any,
    *,
    load_character_context: Callable[..., tuple[object, object]],
    parse_expected_revision: Callable[..., int],
    validate_character_portrait_upload: Callable[..., tuple[str, bytes]],
    prepare_character_portrait_definition_for_write: Callable[..., object],
    redirect_to_character_mode: Callable[..., object],
    has_session_mode_access: Callable[..., bool],
    get_current_user: Callable[..., object | None],
    validate_character_portrait_text: Callable[..., tuple[str, str]],
    build_character_portrait_asset_ref: Callable[..., str],
    update_character_portrait_profile: Callable[..., object],
    build_managed_character_import_metadata: Callable[..., object],
    merge_state_with_definition: Callable[..., dict],
    publish_character_portrait: Callable[..., object],
    render_protected_character_conflict: Callable[..., object | None],
) -> None:
    app.extensions[
        "character_portrait_mutation_route_dependencies"
    ] = CharacterPortraitMutationRouteDependencies(
        load_character_context=load_character_context,
        parse_expected_revision=parse_expected_revision,
        validate_character_portrait_upload=validate_character_portrait_upload,
        prepare_character_portrait_definition_for_write=prepare_character_portrait_definition_for_write,
        redirect_to_character_mode=redirect_to_character_mode,
        has_session_mode_access=has_session_mode_access,
        get_current_user=get_current_user,
        validate_character_portrait_text=validate_character_portrait_text,
        build_character_portrait_asset_ref=build_character_portrait_asset_ref,
        update_character_portrait_profile=update_character_portrait_profile,
        build_managed_character_import_metadata=build_managed_character_import_metadata,
        merge_state_with_definition=merge_state_with_definition,
        publish_character_portrait=publish_character_portrait,
        render_protected_character_conflict=render_protected_character_conflict,
    )

    def protected_recovery(
        dependencies: CharacterPortraitMutationRouteDependencies,
        campaign_slug: str,
        character_slug: str,
        *,
        status_code: int,
        message: str,
        force: bool = False,
        upload: bool = False,
        publication_conflict: bool = False,
    ):
        return dependencies.render_protected_character_conflict(
            campaign_slug, character_slug,
            protected_conflict=force,
            recovery_draft_names=("portrait_alt", "portrait_caption") if upload else (),
            refresh_href=url_for("character_read_view", campaign_slug=campaign_slug, character_slug=character_slug, page="portrait", _anchor="character-portrait-manager"),
            recovery_message=message,
            status_code=status_code,
            reselect_portrait=upload,
            mutation_outcome="publication-conflict" if publication_conflict else "character-revision-conflict",
        )

    def character_personal_portrait(campaign_slug: str, character_slug: str):
        dependencies = _dependencies()
        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        portrait_upload = request.files.get("portrait_file")
        try:
            expected_revision = dependencies.parse_expected_revision()
            filename, data_blob = dependencies.validate_character_portrait_upload(
                portrait_upload
            )
            alt_text, caption = dependencies.validate_character_portrait_text(
                request.form.get("portrait_alt", ""),
                request.form.get("portrait_caption", ""),
            )

            next_asset_ref = dependencies.build_character_portrait_asset_ref(
                character_slug, filename
            )
            definition = dependencies.update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=alt_text,
                caption=caption,
            )
            definition = dependencies.prepare_character_portrait_definition_for_write(
                campaign_slug, definition, campaign=campaign
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            dependencies.publish_character_portrait(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                operation_kind="portrait_upsert",
                desired_asset_ref=next_asset_ref,
                desired_asset_bytes=data_blob,
            )
        except CharacterPublicationConflict:
            return protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=409,
                message="The portrait update needs reconciliation. Its saved outcome is uncertain. Keep a copy of the text below and have the Character reviewed before submitting again.",
                force=True, upload=True, publication_conflict=True,
            )
        except CharacterStateConflictError as exc:
            protected_response = protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=409,
                message="This Character is temporarily unavailable. Keep a copy of the portrait text, then refresh and review the current portrait before trying again.",
                force=isinstance(exc, CharacterStateUnavailableError), upload=True,
            )
            if protected_response is not None:
                return protected_response
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
        except (CharacterStateValidationError, ValueError) as exc:
            protected_response = protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=400,
                message=f"Review this input: {exc}. This Character is temporarily unavailable. Keep a copy of the portrait text, then refresh before trying again.",
                upload=True,
            )
            if protected_response is not None:
                return protected_response
            flash(str(exc), "error")
        else:
            flash("Portrait saved.", "success")

        return dependencies.redirect_to_character_mode(
            campaign_slug, character_slug, anchor="character-portrait-manager"
        )

    def character_personal_portrait_remove(
        campaign_slug: str, character_slug: str
    ):
        dependencies = _dependencies()
        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        existing_asset_ref = str(
            (record.definition.profile or {}).get("portrait_asset_ref") or ""
        ).strip()
        if not existing_asset_ref:
            protected_response = protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=409,
                message="This Character is temporarily unavailable. Refresh and review the current portrait before trying again.",
            )
            if protected_response is not None:
                return protected_response
            flash("That character does not currently have a portrait.", "error")
            return dependencies.redirect_to_character_mode(
                campaign_slug, character_slug, anchor="character-portrait-manager"
            )

        try:
            expected_revision = dependencies.parse_expected_revision()
            definition = dependencies.update_character_portrait_profile(
                record.definition
            )
            definition = dependencies.prepare_character_portrait_definition_for_write(
                campaign_slug, definition, campaign=campaign
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            dependencies.publish_character_portrait(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                operation_kind="portrait_remove",
            )
        except CharacterPublicationConflict:
            return protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=409,
                message="The portrait removal needs reconciliation. Its saved outcome is uncertain. Have the Character reviewed before submitting again.",
                force=True, publication_conflict=True,
            )
        except CharacterStateConflictError as exc:
            protected_response = protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=409,
                message="This Character is temporarily unavailable. Refresh and review the current portrait before trying again.",
                force=isinstance(exc, CharacterStateUnavailableError),
            )
            if protected_response is not None:
                return protected_response
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
        except (CharacterStateValidationError, ValueError) as exc:
            protected_response = protected_recovery(
                dependencies, campaign_slug, character_slug, status_code=400,
                message=f"Review this input: {exc}. This Character is temporarily unavailable. Refresh the portrait page before trying again.",
            )
            if protected_response is not None:
                return protected_response
            flash(str(exc), "error")
        else:
            flash("Portrait removed.", "success")

        return dependencies.redirect_to_character_mode(
            campaign_slug, character_slug, anchor="character-portrait-manager"
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait",
        endpoint="character_personal_portrait",
        view_func=campaign_scope_access_required("characters", own_character=True)(
            character_personal_portrait
        ),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait/remove",
        endpoint="character_personal_portrait_remove",
        view_func=campaign_scope_access_required("characters", own_character=True)(
            character_personal_portrait_remove
        ),
        methods=("POST",),
    )
