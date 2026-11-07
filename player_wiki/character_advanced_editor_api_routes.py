from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify

from .character_editor import CharacterEditValidationError, prepare_native_editor_inventory_note_overrides
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .character_reconciliation import CharacterPublicationConflict
from .character_source_repair import load_verified_manual_actions, load_verified_numeric_actions
from .character_source_authority import build_reconciled_source_authority
from .committed_publication import active
from . import character_external_proficiencies as external_proficiencies
from . import character_reference_notes as reference_notes


@dataclass(frozen=True)
class CharacterAdvancedEditorApiDependencies:
    api_campaign_scope_access_required: Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_advanced_editor_target: Callable[[str, str], tuple[Any, Any, Any | None]]
    character_advanced_editor_is_supported: Callable[[Any, Any], bool]
    build_character_advanced_editor_parts: Callable[..., tuple[Any, ...]]
    serialize_character_advanced_editor_response: Callable[..., Any]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    normalize_character_editor_values: Callable[[dict[str, Any]], dict[str, str]]
    load_character_record: Callable[[str, str], Any]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    get_current_user: Callable[[], Any | None]
    apply_native_character_edits: Callable[..., tuple[Any, Any, dict[str, int]]]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    character_publication_coordinator: object


def register_character_advanced_editor_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterAdvancedEditorApiDependencies,
) -> None:
    def character_advanced_editor_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_advanced_editor_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        if not dependencies.character_advanced_editor_is_supported(campaign, record):
            return dependencies.serialize_character_advanced_editor_response(
                campaign_slug, campaign, record
            )

        edit_context, *_ = dependencies.build_character_advanced_editor_parts(
            campaign_slug,
            campaign,
            record,
        )
        return dependencies.serialize_character_advanced_editor_response(
            campaign_slug,
            campaign,
            record,
            edit_context=edit_context,
        )

    def character_advanced_editor_update(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_advanced_editor_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        if not dependencies.character_advanced_editor_is_supported(campaign, record):
            return dependencies.json_error(
                "Advanced Editor is currently available only for DND-5E native character tools.",
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
            nested = payload.get("values")
            if isinstance(nested, dict) and reference_notes.ACTION in nested:
                raise ValueError("Use one flat reference-notes request, separately from ordinary editor values.")
            if reference_notes.ACTION in payload:
                _context, pages, *_ = dependencies.build_character_advanced_editor_parts(
                    campaign_slug, campaign, record)
                edit = reference_notes.prepare(record, payload,
                    systems_service=current_app.extensions["systems_service"], campaign_page_records=pages)
                if payload[reference_notes.ACTION] == reference_notes.PREVIEW:
                    return jsonify({"ok": True, "reference_notes_preview": edit.preview,
                                    "message": "Review the reference-note changes before saving."})
                reference_notes.publish(record, edit, dependencies.character_publication_coordinator)
                refreshed = dependencies.load_character_record(campaign_slug, character_slug)
                return dependencies.serialize_character_advanced_editor_response(campaign_slug, campaign, refreshed,
                    message="No reference-note changes needed." if edit.preview["no_changes"] else "Reference notes updated.")
            if isinstance(nested, dict) and external_proficiencies.ACTION in nested:
                raise ValueError("Use one flat acquisition request, separately from ordinary editor values.")
            if external_proficiencies.ACTION in payload:
                _context, pages, _optional, _spells, items, _linked = dependencies.build_character_advanced_editor_parts(
                    campaign_slug, campaign, record)
                edit = external_proficiencies.prepare(record, payload,
                    systems_service=current_app.extensions["systems_service"], item_catalog=items,
                    campaign_page_records=pages)
                if payload[external_proficiencies.ACTION] == external_proficiencies.PREVIEW:
                    return jsonify({"ok": True, "external_proficiency_preview": edit.preview,
                                    "message": "Review this acquired proficiency before saving."})
                external_proficiencies.publish(record, edit, dependencies.character_publication_coordinator)
                refreshed = dependencies.load_character_record(campaign_slug, character_slug)
                return dependencies.serialize_character_advanced_editor_response(campaign_slug, campaign, refreshed,
                    message="Acquired proficiency recorded; play state and prior choices preserved.")
            expected_revision = int(payload.get("expected_revision"))
            form_values = dependencies.normalize_character_editor_values(payload)
            note_overrides = prepare_native_editor_inventory_note_overrides(
                record.definition, record.state_record.state or {}, form_values,
            )
            (
                _edit_context,
                campaign_page_records,
                optionalfeature_catalog,
                spell_catalog,
                item_catalog,
                linked_feature_authoring,
            ) = dependencies.build_character_advanced_editor_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            definition, import_metadata, inventory_quantity_overrides = (
                dependencies.apply_native_character_edits(
                    campaign_slug,
                    record.definition,
                    record.import_metadata,
                    campaign_page_records=campaign_page_records,
                    form_values=form_values,
                    optionalfeature_catalog=optionalfeature_catalog,
                    spell_catalog=spell_catalog,
                    item_catalog=item_catalog,
                    systems_service=current_app.extensions["systems_service"],
                    linked_feature_authoring_support=linked_feature_authoring,
                    state=record.state_record.state or {},
                    state_revision=record.state_record.revision,
                    verified_manual_actions=(load_verified_manual_actions(campaign_slug, character_slug)
                                             if active() else ()),
                    verified_numeric_actions=(load_verified_numeric_actions(campaign_slug, character_slug)
                                              if active() else ()),
                    inventory_note_overrides=note_overrides,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug, definition
            )
            prospective_authority = build_reconciled_source_authority(
                definition=definition, state=record.state_record.state or {},
                state_revision=record.state_record.revision,
                systems_service=current_app.extensions["systems_service"],
                campaign_page_records=campaign_page_records,
                verified_manual_actions=load_verified_manual_actions(campaign_slug, character_slug),
                verified_numeric_actions=load_verified_numeric_actions(campaign_slug, character_slug),
            ) if active() else None
            removed_resource_ids: set[str] = set()
            source_type = str(
                (record.definition.source or {}).get("source_type") or ""
            ).strip()
            if source_type and source_type != "native_character_builder":
                previous_resource_ids = {
                    str(template.get("id") or "").strip()
                    for template in list(record.definition.resource_templates or [])
                    if str(template.get("id") or "").strip()
                }
                current_resource_ids = {
                    str(template.get("id") or "").strip()
                    for template in list(definition.resource_templates or [])
                    if str(template.get("id") or "").strip()
                }
                removed_resource_ids = previous_resource_ids - current_resource_ids
            merged_state = dependencies.merge_state_with_definition(
                definition,
                record.state_record.state,
                source_authority=prospective_authority,
                inventory_quantity_overrides=inventory_quantity_overrides,
                inventory_state_overrides=note_overrides,
                removed_resource_ids=removed_resource_ids,
            )
            if (
                "physical_description_markdown" in form_values
                or "background_markdown" in form_values
            ):
                notes_payload = dict(merged_state.get("notes") or {})
                notes_payload["physical_description_markdown"] = str(
                    form_values.get("physical_description_markdown") or ""
                )
                notes_payload["background_markdown"] = str(
                    form_values.get("background_markdown") or ""
                )
                merged_state["notes"] = notes_payload
            native_edit = (record.definition.system == "DND-5E"
                           and record.definition.source.get("source_type") == "native_character_builder")
            dependencies.character_publication_coordinator.update(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                audit_event_type="character_native_edited" if native_edit else None,
                audit_actor_user_id=user.id if native_edit else None,
                audit_metadata={"source": "native_edit_confirmed"} if native_edit else None,
            )
        except PermissionError as exc:
            return dependencies.json_error(str(exc), 403, code="forbidden")
        except CharacterPublicationConflict:
            return dependencies.json_error(
                "The Character update needs reconciliation. Its saved outcome is uncertain. Inspect the current Character before submitting again.",
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
            CharacterEditValidationError,
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
        edit_context, *_ = dependencies.build_character_advanced_editor_parts(
            campaign_slug,
            campaign,
            refreshed_record,
        )
        return dependencies.serialize_character_advanced_editor_response(
            campaign_slug,
            campaign,
            refreshed_record,
            edit_context=edit_context,
            message="Character details updated.",
        )

    character_advanced_editor_read_view = (
        dependencies.api_campaign_scope_access_required("characters", own_character=True)(
            dependencies.api_login_required(character_advanced_editor_read)
        )
    )
    character_advanced_editor_update_view = (
        dependencies.api_campaign_scope_access_required("characters", own_character=True)(
            dependencies.api_login_required(character_advanced_editor_update)
        )
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor",
        endpoint="character_advanced_editor_read",
        view_func=character_advanced_editor_read_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor",
        endpoint="character_advanced_editor_update",
        view_func=character_advanced_editor_update_view,
        methods=("PUT",),
    )
