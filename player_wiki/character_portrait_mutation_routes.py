from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, request

from .auth import campaign_scope_access_required
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterPortraitMutationRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    parse_expected_revision: Callable[..., int]
    validate_character_portrait_upload: Callable[..., tuple[str, bytes]]
    finalize_character_definition_for_write: Callable[..., object]
    redirect_to_character_mode: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    get_current_user: Callable[..., object | None]
    validate_character_portrait_text: Callable[..., tuple[str, str]]
    build_character_portrait_asset_ref: Callable[..., str]
    update_character_portrait_profile: Callable[..., object]
    build_managed_character_import_metadata: Callable[..., object]
    merge_state_with_definition: Callable[..., dict]
    load_campaign_character_config: Callable[..., object]
    write_yaml: Callable[..., None]
    write_campaign_asset_file: Callable[..., object]
    delete_campaign_asset_file: Callable[..., object]


def _dependencies() -> CharacterPortraitMutationRouteDependencies:
    return current_app.extensions["character_portrait_mutation_route_dependencies"]


def register_character_portrait_mutation_routes(
    app: Any,
    *,
    load_character_context: Callable[..., tuple[object, object]],
    parse_expected_revision: Callable[..., int],
    validate_character_portrait_upload: Callable[..., tuple[str, bytes]],
    finalize_character_definition_for_write: Callable[..., object],
    redirect_to_character_mode: Callable[..., object],
    has_session_mode_access: Callable[..., bool],
    get_current_user: Callable[..., object | None],
    validate_character_portrait_text: Callable[..., tuple[str, str]],
    build_character_portrait_asset_ref: Callable[..., str],
    update_character_portrait_profile: Callable[..., object],
    build_managed_character_import_metadata: Callable[..., object],
    merge_state_with_definition: Callable[..., dict],
    load_campaign_character_config: Callable[..., object],
    write_yaml: Callable[..., None],
    write_campaign_asset_file: Callable[..., object],
    delete_campaign_asset_file: Callable[..., object],
) -> None:
    app.extensions[
        "character_portrait_mutation_route_dependencies"
    ] = CharacterPortraitMutationRouteDependencies(
        load_character_context=load_character_context,
        parse_expected_revision=parse_expected_revision,
        validate_character_portrait_upload=validate_character_portrait_upload,
        finalize_character_definition_for_write=finalize_character_definition_for_write,
        redirect_to_character_mode=redirect_to_character_mode,
        has_session_mode_access=has_session_mode_access,
        get_current_user=get_current_user,
        validate_character_portrait_text=validate_character_portrait_text,
        build_character_portrait_asset_ref=build_character_portrait_asset_ref,
        update_character_portrait_profile=update_character_portrait_profile,
        build_managed_character_import_metadata=build_managed_character_import_metadata,
        merge_state_with_definition=merge_state_with_definition,
        load_campaign_character_config=load_campaign_character_config,
        write_yaml=write_yaml,
        write_campaign_asset_file=write_campaign_asset_file,
        delete_campaign_asset_file=delete_campaign_asset_file,
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

            existing_asset_ref = str(
                (record.definition.profile or {}).get("portrait_asset_ref") or ""
            ).strip()
            next_asset_ref = dependencies.build_character_portrait_asset_ref(
                character_slug, filename
            )
            definition = dependencies.update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=alt_text,
                caption=caption,
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = dependencies.load_campaign_character_config(
                current_app.config["CAMPAIGNS_DIR"], campaign_slug
            )
            character_dir = config.characters_dir / character_slug
            dependencies.write_yaml(
                character_dir / "definition.yaml", definition.to_dict()
            )
            dependencies.write_yaml(
                character_dir / "import.yaml", import_metadata.to_dict()
            )
            dependencies.write_campaign_asset_file(
                campaign, next_asset_ref, data_blob=data_blob
            )
            if existing_asset_ref and existing_asset_ref != next_asset_ref:
                dependencies.delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
        except (CharacterStateValidationError, ValueError) as exc:
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
            flash("That character does not currently have a portrait.", "error")
            return dependencies.redirect_to_character_mode(
                campaign_slug, character_slug, anchor="character-portrait-manager"
            )

        try:
            expected_revision = dependencies.parse_expected_revision()
            definition = dependencies.update_character_portrait_profile(
                record.definition
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = dependencies.load_campaign_character_config(
                current_app.config["CAMPAIGNS_DIR"], campaign_slug
            )
            character_dir = config.characters_dir / character_slug
            dependencies.write_yaml(
                character_dir / "definition.yaml", definition.to_dict()
            )
            dependencies.write_yaml(
                character_dir / "import.yaml", import_metadata.to_dict()
            )
            dependencies.delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash("Portrait removed.", "success")

        return dependencies.redirect_to_character_mode(
            campaign_slug, character_slug, anchor="character-portrait-manager"
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait",
        endpoint="character_personal_portrait",
        view_func=campaign_scope_access_required("characters")(
            character_personal_portrait
        ),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait/remove",
        endpoint="character_personal_portrait_remove",
        view_func=campaign_scope_access_required("characters")(
            character_personal_portrait_remove
        ),
        methods=("POST",),
    )
