from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, flash, redirect, request, url_for

from .auth import campaign_scope_access_required
from .character_path_safety import CharacterPathSafetyError
from .system_policy import CHARACTER_ROUTE_LANE_XIANXIA


@dataclass(frozen=True)
class CharacterXianxiaManualImportRouteDependencies:
    load_campaign_context: Callable[..., object]
    get_systems_service: Callable[..., object]
    render_xianxia_manual_import_page: Callable[..., object]
    can_manage_campaign_session: Callable[..., bool]
    native_character_create_lane: Callable[..., str]
    build_xianxia_manual_import_context: Callable[..., dict[str, object]]
    build_xianxia_manual_import_payload: Callable[..., dict[str, object]]
    build_xianxia_manual_import_character: Callable[..., tuple[object, object, dict]]
    validate_character_slug: Callable[..., None]
    build_xianxia_manual_import_preview: Callable[..., dict[str, object]]
    publish_new_character: Callable[..., object]


def register_character_xianxia_manual_import_route(
    app: Any,
    *,
    dependencies: CharacterXianxiaManualImportRouteDependencies,
) -> None:
    def character_import_xianxia_manual_view(campaign_slug: str):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = dependencies.load_campaign_context(campaign_slug)
        if (
            dependencies.native_character_create_lane(
                getattr(campaign, "system", "")
            )
            != CHARACTER_ROUTE_LANE_XIANXIA
        ):
            flash(
                "Manual Xianxia character import is only available for Xianxia campaigns.",
                "error",
            )
            return redirect(
                url_for("character_roster_view", campaign_slug=campaign_slug)
            )

        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        import_context = dependencies.build_xianxia_manual_import_context(
            systems_service=dependencies.get_systems_service(),
            campaign_slug=campaign_slug,
            values=form_values,
        )
        if request.method != "POST":
            return dependencies.render_xianxia_manual_import_page(
                campaign_slug, import_context
            )

        payload = dependencies.build_xianxia_manual_import_payload(form_values)
        try:
            definition, import_metadata, initial_state = (
                dependencies.build_xianxia_manual_import_character(
                    payload,
                    campaign_slug=campaign_slug,
                    martial_art_options=list(
                        import_context.get("martial_art_options") or []
                    ),
                )
            )
            dependencies.validate_character_slug(definition.character_slug)
        except ValueError as exc:
            flash(str(exc), "error")
            return dependencies.render_xianxia_manual_import_page(
                campaign_slug, import_context, status_code=400
            )

        preview = dependencies.build_xianxia_manual_import_preview(
            definition, initial_state
        )
        import_context = dependencies.build_xianxia_manual_import_context(
            systems_service=dependencies.get_systems_service(),
            campaign_slug=campaign_slug,
            values=form_values,
            preview=preview,
        )
        if not request.form.get("confirm_import"):
            flash(
                "Review the imported sheet summary, then confirm to create the character.",
                "info",
            )
            return dependencies.render_xianxia_manual_import_page(
                campaign_slug, import_context
            )

        try:
            dependencies.publish_new_character(
                definition,
                import_metadata,
                initial_state,
                operation_kind="manual_import",
            )
        except CharacterPathSafetyError as exc:
            flash(str(exc), "error")
            return dependencies.render_xianxia_manual_import_page(
                campaign_slug, import_context, status_code=400
            )
        except FileExistsError:
            flash(
                f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                "error",
            )
            return dependencies.render_xianxia_manual_import_page(
                campaign_slug, import_context, status_code=409
            )
        flash(f"{definition.name} imported.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=definition.character_slug,
            )
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/import/xianxia-manual",
        endpoint="character_import_xianxia_manual_view",
        view_func=campaign_scope_access_required("characters")(
            character_import_xianxia_manual_view
        ),
        methods=("GET", "POST"),
    )
