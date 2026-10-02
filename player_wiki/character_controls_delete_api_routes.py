from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, url_for


@dataclass(frozen=True)
class CharacterControlsDeleteApiDependencies:
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_controls_target: Callable[..., tuple[Any, Any]]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    flask_campaign_href: Callable[..., str]
    can_manage_campaign_content: Callable[[str], bool]
    get_auth_store: Callable[[], Any]
    get_current_user: Callable[[], Any | None]
    delete_campaign_character_file: Callable[..., Any]


def register_character_controls_delete_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterControlsDeleteApiDependencies,
) -> None:
    def character_controls_delete(campaign_slug: str, character_slug: str):
        campaign, record = dependencies.load_character_controls_target(
            campaign_slug, character_slug
        )
        if not dependencies.can_manage_campaign_content(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to delete this character.",
                403,
                code="forbidden",
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )
        confirmation = str(payload.get("confirm_character_slug") or "").strip()
        if confirmation != character_slug:
            return dependencies.json_error(
                f"Type {character_slug} to confirm deletion.",
                400,
                code="validation_error",
            )

        from .committed_publication import active
        activated = active()
        expected_definition_revision = expected_state_revision = None
        if activated:
            expected_definition_revision = record.committed_revision
            expected_state_revision = record.state_record.revision
            if (type(expected_definition_revision) is not int or expected_definition_revision < 1
                    or type(expected_state_revision) is not int or expected_state_revision < 1):
                return dependencies.json_error("Character committed proof needs manager repair.", 409,
                                               code="state_conflict")
            for name, observed in (
                ("expected_definition_revision", expected_definition_revision),
                ("expected_state_revision", expected_state_revision),
                ("revision", expected_state_revision),
            ):
                if name not in payload:
                    continue
                supplied = payload[name]
                if type(supplied) is not int or supplied < 1:
                    return dependencies.json_error(f"{name} must be a positive integer.", 400,
                                                   code="validation_error")
                if supplied != observed:
                    return dependencies.json_error("Character changed before deletion confirmation.", 409,
                                                   code="state_conflict")

        store = dependencies.get_auth_store()
        actor = dependencies.get_current_user()
        try:
            deleted = dependencies.delete_campaign_character_file(
                current_app.config["CAMPAIGNS_DIR"],
                campaign_slug,
                character_slug,
                state_store=current_app.extensions["character_state_store"],
                auth_store=store,
                coordinator=current_app.extensions["character_deletion_coordinator"],
                operation_kind="character_controls_api",
                actor_user_id=actor.id if actor is not None else None,
                audit_source="character_controls_api",
                expected_definition_revision=expected_definition_revision,
                expected_state_revision=expected_state_revision,
            )
        except ValueError as exc:
            if not activated:
                raise
            return dependencies.json_error(str(exc), 409, code="state_conflict")
        if deleted is None:
            return dependencies.json_error(
                "That character no longer exists.", 404, code="not_found"
            )

        return jsonify(
            {
                "ok": True,
                "message": f"Deleted character {record.definition.name}.",
                "deleted_character_slug": character_slug,
                "deleted_character_name": record.definition.name,
                "links": {
                    "roster_url": dependencies.flask_campaign_href(
                        campaign_slug, "characters"
                    ),
                    "flask_roster_url": url_for(
                        "character_roster_view", campaign_slug=campaign.slug
                    ),
                },
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls",
        endpoint="character_controls_delete",
        view_func=dependencies.api_login_required(character_controls_delete),
        methods=("DELETE",),
    )
